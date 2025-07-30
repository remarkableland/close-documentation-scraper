import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import os
from urllib.parse import urljoin, urlparse
import json
from datetime import datetime
import zipfile
from io import BytesIO

st.set_page_config(
    page_title="Close.com Documentation Scraper",
    page_icon="📚",
    layout="wide"
)

class CloseDocScraper:
    def __init__(self):
        self.base_url = "https://developer.close.com"
        self.scraped_urls = set()
        self.scraped_content = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
    def is_documentation_url(self, url):
        """Check if URL is part of Close documentation"""
        parsed = urlparse(url)
        
        # More permissive URL filtering for debugging
        is_close_domain = parsed.netloc == 'developer.close.com'
        is_not_file = not any(url.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.css', '.js', '.svg', '.ico'])
        is_not_external = not any(domain in url for domain in ['github.com', 'twitter.com', 'linkedin.com', 'mailto:', 'tel:'])
        
        return is_close_domain and is_not_file and is_not_external
    
    def clean_text(self, soup):
        """Extract and clean text from BeautifulSoup object"""
        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text and clean it up
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        return text
    
    def extract_code_examples(self, soup):
        """Extract code examples separately"""
        code_blocks = []
        for code in soup.find_all(['code', 'pre']):
            if code.get_text().strip():
                code_blocks.append({
                    'type': code.name,
                    'content': code.get_text().strip(),
                    'language': code.get('class', [''])[0] if code.get('class') else ''
                })
        return code_blocks
    
    def scrape_page(self, url, progress_bar=None, status_text=None):
        """Scrape a single page with Streamlit progress updates"""
        if url in self.scraped_urls:
            return []
        
        try:
            if status_text:
                status_text.text(f"Scraping: {url}")
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract page title
            title = soup.find('title')
            title_text = title.get_text().strip() if title else url.split('/')[-1]
            
            # Extract main content
            main_content = soup.find('main') or soup.find('div', class_='content') or soup
            
            # Clean text content
            clean_content = self.clean_text(main_content)
            
            # Extract code examples
            code_examples = self.extract_code_examples(main_content)
            
            # Store scraped content
            self.scraped_content[url] = {
                'title': title_text,
                'url': url,
                'content': clean_content,
                'code_examples': code_examples,
                'scraped_at': datetime.now().isoformat()
            }
            
            self.scraped_urls.add(url)
            
            # Find all links on this page - DEBUG VERSION
            links = []
            all_links_found = []
            
            for link in soup.find_all('a', href=True):
                absolute_url = urljoin(url, link['href'])
                all_links_found.append(absolute_url)
                if self.is_documentation_url(absolute_url):
                    links.append(absolute_url)
            
            # Debug info for Streamlit
            if status_text and url == self.base_url:
                status_text.text(f"DEBUG: Found {len(all_links_found)} total links, {len(links)} documentation links on main page")
            
            # Small delay to be respectful
            time.sleep(0.5)
            
            return links
            
        except Exception as e:
            if status_text:
                status_text.text(f"Error scraping {url}: {str(e)}")
            return []
    
    def crawl_documentation(self, start_url=None, progress_container=None):
        """Crawl all documentation with Streamlit progress tracking"""
        if not start_url:
            start_url = self.base_url
        
        urls_to_visit = [start_url]
        visited = set()
        
        if progress_container:
            progress_bar = progress_container.progress(0)
            status_text = progress_container.empty()
        else:
            progress_bar = None
            status_text = None
        
        while urls_to_visit:
            current_url = urls_to_visit.pop(0)
            
            if current_url in visited:
                continue
                
            visited.add(current_url)
            new_links = self.scrape_page(current_url, progress_bar, status_text)
            
            # Add new links to visit
            for link in new_links:
                if link not in visited and link not in urls_to_visit:
                    urls_to_visit.append(link)
            
            # Update progress
            total_discovered = len(visited) + len(urls_to_visit)
            progress = len(visited) / max(total_discovered, 1) if total_discovered > 0 else 1
            
            if progress_bar:
                progress_bar.progress(min(progress, 1.0))
            
            if status_text:
                status_text.text(f"Progress: {len(visited)} pages scraped, {len(urls_to_visit)} remaining")
    
    def create_organized_files(self):
        """Create organized documentation files and return as dict"""
        files = {}
        
        # Define categories based on URL patterns and titles
        categories = {
            'API_Overview': ['introduction', 'getting-started', 'authentication', 'api-clients'],
            'Resources': ['leads', 'contacts', 'opportunities', 'activities', 'tasks'],
            'Advanced_Features': ['webhooks', 'custom-fields', 'reporting', 'bulk-actions'],
            'Integration_Topics': ['rate-limits', 'errors', 'pagination', 'filtering'],
            'Custom_Objects': ['custom-activities', 'custom-objects', 'custom-fields']
        }
        
        # Create category files
        categorized_content = {cat: [] for cat in categories}
        uncategorized = []
        
        for url, content in self.scraped_content.items():
            categorized = False
            url_lower = url.lower()
            title_lower = content['title'].lower()
            
            for category, keywords in categories.items():
                if any(keyword in url_lower or keyword in title_lower for keyword in keywords):
                    categorized_content[category].append(content)
                    categorized = True
                    break
            
            if not categorized:
                uncategorized.append(content)
        
        # Write category files
        for category, contents in categorized_content.items():
            if contents:
                filename = f"Tech_Close_{category}.md"
                file_content = f"# Close.com {category.replace('_', ' ')} Documentation\n\n"
                file_content += f"**Purpose:** Close.com {category.replace('_', ' ')} reference documentation\n\n"
                file_content += f"**Last Updated:** {datetime.now().strftime('%B %d, %Y')}\n\n"
                file_content += "---\n\n"
                
                for content in contents:
                    file_content += f"## {content['title']}\n\n"
                    file_content += f"**URL:** {content['url']}\n\n"
                    file_content += f"{content['content']}\n\n"
                    
                    if content['code_examples']:
                        file_content += "### Code Examples\n\n"
                        for code in content['code_examples']:
                            file_content += f"```{code.get('language', '')}\n"
                            file_content += f"{code['content']}\n"
                            file_content += "```\n\n"
                    
                    file_content += "---\n\n"
                
                files[filename] = file_content
        
        # Write uncategorized content
        if uncategorized:
            filename = "Tech_Close_Additional.md"
            file_content = "# Close.com Additional Documentation\n\n"
            file_content += "**Purpose:** Additional Close.com documentation and references\n\n"
            file_content += f"**Last Updated:** {datetime.now().strftime('%B %d, %Y')}\n\n"
            file_content += "---\n\n"
            
            for content in uncategorized:
                file_content += f"## {content['title']}\n\n"
                file_content += f"**URL:** {content['url']}\n\n"
                file_content += f"{content['content']}\n\n"
                
                if content['code_examples']:
                    file_content += "### Code Examples\n\n"
                    for code in content['code_examples']:
                        file_content += f"```{code.get('language', '')}\n"
                        file_content += f"{code['content']}\n"
                        file_content += "```\n\n"
                
                file_content += "---\n\n"
            
            files[filename] = file_content
        
        # Create master index
        filename = "Tech_Close_Master_Index.md"
        file_content = "# Close.com Complete Documentation Index\n\n"
        file_content += "**Purpose:** Master index of all Close.com developer documentation\n\n"
        file_content += f"**Total Pages Scraped:** {len(self.scraped_content)}\n\n"
        file_content += f"**Last Updated:** {datetime.now().strftime('%B %d, %Y')}\n\n"
        file_content += "---\n\n"
        
        file_content += "## Documentation Structure\n\n"
        file_content += "This documentation has been organized into the following files:\n\n"
        
        for file_name in files.keys():
            if file_name != "Tech_Close_Master_Index.md":
                file_content += f"- **{file_name}**\n"
        
        file_content += "\n## Complete Page Index\n\n"
        
        sorted_pages = sorted(self.scraped_content.items(), key=lambda x: x[1]['title'])
        for url, content in sorted_pages:
            file_content += f"- **{content['title']}** - {url}\n"
        
        files[filename] = file_content
        
        # Add JSON backup
        files["complete_documentation.json"] = json.dumps(self.scraped_content, indent=2, ensure_ascii=False)
        
        return files

def create_zip_download(files_dict):
    """Create a ZIP file from the files dictionary"""
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files_dict.items():
            zip_file.writestr(filename, content)
    
    zip_buffer.seek(0)
    return zip_buffer

def main():
    st.title("📚 Close.com Documentation Scraper")
    st.markdown("### Comprehensive Close.com Developer Documentation Extractor")
    
    # Add reset button and session state management
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Reset & Clear Cache", type="secondary"):
            # Clear all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
    
    st.markdown("""
    This tool systematically scrapes the entire Close.com developer documentation 
    and organizes it into structured files perfect for AI training and reference.
    """)
    
    # Configuration section
    st.subheader("🔧 Configuration")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_url = st.text_input(
            "Starting URL", 
            value="https://developer.close.com",
            help="The URL to start scraping from"
        )
    
    with col2:
        st.metric("Estimated Time", "10-20 minutes")
    
    with col3:
        debug_mode = st.checkbox("🐛 Debug Mode", help="Show detailed scraping information")
    
    # Quick test section
    if debug_mode:
        st.subheader("🔍 Quick URL Test")
        if st.button("Test Starting URL"):
            with st.spinner("Testing URL accessibility..."):
                try:
                    test_session = requests.Session()
                    test_session.headers.update({
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    })
                    
                    response = test_session.get(start_url, timeout=10)
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Find all links
                    all_links = [urljoin(start_url, link.get('href', '')) for link in soup.find_all('a', href=True)]
                    
                    # Test URL filter
                    scraper_test = CloseDocScraper()
                    doc_links = [link for link in all_links if scraper_test.is_documentation_url(link)]
                    
                    st.success(f"✅ URL accessible! Status: {response.status_code}")
                    st.info(f"Found {len(all_links)} total links")
                    st.info(f"Found {len(doc_links)} documentation links")
                    
                    if len(doc_links) > 0:
                        with st.expander("Preview Documentation Links"):
                            for link in doc_links[:10]:  # Show first 10
                                st.write(f"- {link}")
                            if len(doc_links) > 10:
                                st.write(f"... and {len(doc_links) - 10} more")
                    else:
                        st.warning("⚠️ No documentation links found - this might explain the issue!")
                        with st.expander("All Links Found (for debugging)"):
                            for link in all_links[:20]:  # Show first 20
                                st.write(f"- {link}")
                                
                except Exception as e:
                    st.error(f"❌ Error testing URL: {str(e)}")
        
        st.divider()
    
    # Warning about rate limiting
    st.warning("""
    ⚠️ **Important Notes:**
    - This scraper is respectful (0.5s delays between requests)
    - It may take 10-20 minutes to complete
    - Large documentation sites can result in many files
    - The scraper will stop and organize results if interrupted
    """)
    
    # Start scraping button
    if st.button("🚀 Start Comprehensive Documentation Scrape", type="primary"):
        
        # Force create new scraper instance to clear any cached URLs
        scraper = CloseDocScraper()
        
        # Clear any existing session state
        if 'scraper_results' in st.session_state:
            del st.session_state['scraper_results']
        
        # Progress tracking
        progress_container = st.container()
        progress_container.write("**Scraping Progress:**")
        
        with st.spinner("Initializing scraper..."):
            time.sleep(1)
        
        # Start scraping
        try:
            scraper.crawl_documentation(start_url, progress_container)
            
            st.success(f"✅ Scraping complete! Found {len(scraper.scraped_content)} pages")
            
            # Organize files
            with st.spinner("Organizing documentation files..."):
                organized_files = scraper.create_organized_files()
            
            st.success(f"✅ Created {len(organized_files)} organized documentation files")
            
            # Display results
            st.subheader("📊 Scraping Results")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Pages", len(scraper.scraped_content))
            
            with col2:
                st.metric("Generated Files", len(organized_files))
            
            with col3:
                total_size = sum(len(content.encode('utf-8')) for content in organized_files.values())
                st.metric("Total Size", f"{total_size / 1024 / 1024:.1f} MB")
            
            # File download section
            st.subheader("📥 Download Documentation")
            
            # Create ZIP download
            zip_buffer = create_zip_download(organized_files)
            
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"close_documentation_{current_time}.zip"
            
            st.download_button(
                label="📦 Download All Files (ZIP)",
                data=zip_buffer.getvalue(),
                file_name=zip_filename,
                mime="application/zip"
            )
            
            # Individual file downloads
            st.subheader("📄 Individual File Downloads")
            
            for filename, content in organized_files.items():
                if filename.endswith('.md'):
                    st.download_button(
                        label=f"📄 {filename}",
                        data=content,
                        file_name=filename,
                        mime="text/markdown",
                        key=f"download_{filename}"
                    )
                elif filename.endswith('.json'):
                    st.download_button(
                        label=f"📄 {filename}",
                        data=content,
                        file_name=filename,
                        mime="application/json",
                        key=f"download_{filename}"
                    )
            
            # Preview section
            st.subheader("👀 Documentation Preview")
            
            selected_file = st.selectbox(
                "Select file to preview:",
                list(organized_files.keys())
            )
            
            if selected_file:
                if selected_file.endswith('.json'):
                    st.json(json.loads(organized_files[selected_file])[:3])  # Show first 3 entries
                else:
                    preview_content = organized_files[selected_file][:2000]  # First 2000 chars
                    st.text_area(
                        f"Preview of {selected_file}:",
                        value=preview_content + ("..." if len(organized_files[selected_file]) > 2000 else ""),
                        height=300,
                        disabled=True
                    )
            
            # Instructions for next steps
            st.subheader("🎯 Next Steps")
            st.markdown("""
            **To add this documentation to your AI projects:**
            
            1. **Download** the ZIP file or individual markdown files
            2. **Upload** the `.md` files to your Claude/ChatGPT projects
            3. **Reference** the `Tech_Close_Master_Index.md` for navigation
            4. **Use** the complete domain knowledge in your AI conversations
            
            **File Organization:**
            - `Tech_Close_API_Overview.md` - Core API concepts
            - `Tech_Close_Resources.md` - Leads, contacts, opportunities
            - `Tech_Close_Advanced_Features.md` - Webhooks, custom fields
            - `Tech_Close_Integration_Topics.md` - Technical implementation
            - `Tech_Close_Custom_Objects.md` - Extensibility features
            - `Tech_Close_Additional.md` - Miscellaneous documentation
            - `Tech_Close_Master_Index.md` - Complete navigation index
            """)
            
        except Exception as e:
            st.error(f"❌ Scraping failed: {str(e)}")
            st.info("Try reducing the scope or checking your internet connection.")
    
    # Additional information
    st.subheader("ℹ️ About This Tool")
    st.markdown("""
    This scraper follows best practices:
    - **Respectful**: 0.5-second delays between requests
    - **Smart**: Only scrapes documentation pages
    - **Organized**: Categorizes content logically
    - **Complete**: Captures text, code examples, and structure
    - **Backup**: Saves complete JSON for future processing
    """)

if __name__ == "__main__":
    main()
