# Liên kết tài liệu ngoài và kiểm tra liên kết trong Javadoc mô-đun (Java 9+)

Từ Java 9, Javadoc hiểu **module** của JPMS (Java Platform Module System). Một bộ tài liệu API tốt cần dẫn người đọc tới type/method trong module, các API của JDK hoặc thư viện phụ thuộc, trang hướng dẫn bên ngoài và các mục ở trang HTML đã sinh. Nhưng **Javadoc sinh thành công không bảo đảm tất cả liên kết hoạt động**: URL ngoài có thể 404, một class bị đổi tên, một anchor biến mất sau refactor hoặc cách publish làm hỏng đường dẫn tương đối.

Bài này sử dụng Java 17+ để thực hành Javadoc cho một module Java 9+, tập trung vào `{@link}`, `{@linkplain}`, `@see`, `-link`, `-linkoffline`, DocLint và kiểm tra file/anchor/URL HTTP(S). Các API và quy trình này vẫn phù hợp với các JDK hiện đại.

## 1. Mục tiêu và nguyên tắc

Sau bài học, bạn sẽ biết:

1. Phân biệt **tham chiếu phần tử Java**, **URL web thông thường**, **liên kết tương đối** và **fragment** `#id`.
2. Sinh tài liệu cho `module-info.java`, `package-info.java` và lớp public.
3. Thiết lập `-link` để Javadoc tạo liên kết tới một bộ docs bên ngoài có metadata phù hợp.
4. Dùng `-linkoffline` với metadata cục bộ khi môi trường build không có mạng.
5. Dùng `-Xdoclint:all -Werror` để bắt lỗi bình luận và tham chiếu Java.
6. Quét HTML sau khi generate để tìm file/fragment hỏng, và phân loại link HTTP không truy cập được mà tránh báo lỗi giả.
7. Tách kiểm tra **mỗi PR**, kiểm tra **định kỳ** và kiểm tra **sau deploy**.

Đừng đồng nhất **đúng cú pháp**, **tồn tại trên máy chủ**, và **đúng nội dung/version**. Một URL có thể tạo thành công, trả HTTP `200` nhưng dẫn đến trang login hoặc phiên bản API sai. Ngược lại, HTTP `403` ở CI có thể do hệ thống chống bot, không chứng minh link của người dùng đã chết.

## 2. Chọn cú pháp link đúng đối tượng

| Đối tượng | Cú pháp | Tác dụng |
| --- | --- | --- |
| Type Java | `{@link java.util.List}` | Javadoc phân giải Java symbol và tạo hyperlink |
| Phương thức overload | `{@link #count(java.util.List)}` | Tham chiếu đúng chữ ký, tránh tự ghép URL anchor |
| Chú thích trong văn xuôi | `{@linkplain java.util.List List interface}` | Link symbol với nhãn thường |
| Mục “See Also” | `@see java.util.List` | Block tag tham chiếu class/API |
| Website thông thường | `<a href="https://...">Guide</a>` | Hyperlink HTML trực tiếp |
| Mục trong trang | `<a href="#examples">Examples</a>` | Cần `id="examples"` thật |
| File trong bộ docs | `<a href="../guide.html">Guide</a>` | Cần file đúng vị trí sau publish |

`{@link}` và `{@linkplain}` là **inline tags** dùng trong câu. `@see` là **block tag** đặt gần cuối Javadoc comment. Khi viết tham chiếu đến type/member Java, nên dùng symbol: việc đổi package/chữ ký có thể làm công cụ cảnh báo. Khi viết URL tới website bất kỳ, dùng HTML `<a href>`. `{@link https://example.com}` **không hợp lệ về ý nghĩa** vì `@link` mong đợi tham chiếu phần tử Java.

Ví dụ một comment minh họa, đặt trong mã Java:

```java
/**
 * Uses {@link java.util.List} for entries.
 * Read the {@linkplain java.util.List List interface} documentation.
 *
 * @see java.util.List
 * @see <a href="https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html">
 *      Javadoc tool guide</a>
 */
```

Một link ngoài trong `@see <a ...>` vẫn chỉ là HTML. Công cụ Javadoc **không tự kiểm tra HTTP response** của trang đó.

## 3. Tạo module mẫu có liên kết ngoài

Cấu trúc cần tạo:

```text
src/
└── com.example.catalog/
    ├── module-info.java
    └── com/
        └── example/
            └── catalog/
                └── api/
                    ├── package-info.java
                    └── Catalog.java
```

Tên thư mục ngay dưới `src/` trùng tên module để `--module-source-path src` nhận diện được source.

**`src/com.example.catalog/module-info.java`:**

```java
/**
 * Module providing an example catalog API.
 *
 * <p>Start with {@link com.example.catalog.api.Catalog}.
 */
module com.example.catalog {
    exports com.example.catalog.api;
}
```

**`src/com.example.catalog/com/example/catalog/api/package-info.java`:**

```java
/**
 * Operations for read-only catalog entries.
 *
 * <p>The API is exported by {@code com.example.catalog}.
 */
package com.example.catalog.api;
```

**`src/com.example.catalog/com/example/catalog/api/Catalog.java`:**

```java
package com.example.catalog.api;

import java.util.List;

/**
 * Read-only catalog operations.
 *
 * <p>Entries use {@link java.util.List}; see the
 * {@linkplain java.util.List List interface}.
 *
 * <p>For Javadoc syntax, consult the
 * <a href="https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html">
 * Javadoc tool manual</a>.
 *
 * @see List
 * @see <a href="https://docs.oracle.com/en/java/javase/17/docs/api/">
 *      Java SE 17 API documentation</a>
 */
public final class Catalog {
    private Catalog() {
    }

    /**
     * Counts entries.
     *
     * @param entries entries to count
     * @return the number of entries
     * @throws NullPointerException if {@code entries} is null
     * @see java.util.List#size()
     */
    public static int count(List<String> entries) {
        return entries.size();
    }
}
```

`com.example.catalog` **exports** package API, còn class `Catalog` sử dụng `List` trong module `java.base` (được đọc ngầm). Không có thư viện ngoài cần cài đặt. URL trong Javadoc comment là nguồn tham khảo thực tế; trang riêng đó phải được xác minh bởi bước HTTP link checking nếu dự án cần bảo đảm nó tồn tại.

### 3.1. Biên dịch module theo Java 17

Đứng tại thư mục chứa `src/`:

```bash
javac --release 17 --module-source-path src \
  -d build/mods --module com.example.catalog
```

Trong PowerShell/CMD, dùng một dòng, không dùng `\` để nối dòng:

```text
javac --release 17 --module-source-path src -d build/mods --module com.example.catalog
```

`javac` exit code `0` là thành công, không có stdout cố định. Việc biên dịch kiểm tra cấu trúc module và Java source; nó chưa sinh Javadoc.

### 3.2. Sinh Javadoc có kiểm tra cảnh báo

```bash
javadoc --release 17 --module-source-path src \
  --module com.example.catalog -d build/docs \
  -Xdoclint:all -Werror -quiet
```

Trong PowerShell/CMD:

```text
javadoc --release 17 --module-source-path src --module com.example.catalog -d build/docs -Xdoclint:all -Werror -quiet
```

Khi thành công, một phần cấu trúc HTML:

```text
build/docs/index.html
build/docs/element-list
build/docs/com.example.catalog/module-summary.html
build/docs/com.example.catalog/com/example/catalog/api/package-summary.html
build/docs/com.example.catalog/com/example/catalog/api/Catalog.html
```

Đây chỉ là các file tiêu biểu; Javadoc còn sinh nhiều trang chỉ mục, stylesheet và script. Không xóa những file khác khi publish.

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--release 17` | Chọn API/platform version phù hợp để tạo docs |
| `--module-source-path` | Root của module source |
| `--module` | Module cần tạo tài liệu |
| `-d` | Nơi ghi HTML |
| `-Xdoclint:all` | Bật các nhóm kiểm tra Javadoc comment |
| `-Werror` | Có warning thì lệnh thất bại, thuận tiện cho CI |
| `-quiet` | Giảm log thường, **không tắt cảnh báo hoặc lỗi** |

Một lỗi Java reference do đổi tên method, `@param` không khớp hoặc HTML comment sai cần được sửa trong source. Không dùng `-Xdoclint:none` để che toàn bộ lỗi chỉ vì pipeline đang fail.

## 4. Liên kết tới Javadoc bên ngoài bằng `-link`

`-link` dành cho **một bộ tài liệu đã được Javadoc sinh**, chứ không dành cho mọi trang web. Đối số phải là **root URL** của bộ docs chứa `element-list` hoặc `package-list`, không phải URL một class như `List.html`.

Ví dụ pin vào JDK 17:

```bash
javadoc --release 17 --module-source-path src \
  --module com.example.catalog -d build/docs \
  -Xdoclint:all -Werror -quiet \
  -link https://docs.oracle.com/en/java/javase/17/docs/api/
```

Nhờ metadata và Java symbols, `{@link java.util.List}` có thể dẫn tới:

```text
https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html
```

Ở đây `java.base` là **tên module**, `java.util` là **package**. Cấu trúc này có thể khác tài liệu Java cũ không dùng module; đừng tự ghép đường dẫn dựa trên quy tắc package trước Java 9.

Bạn có thể dùng nhiều `-link` khi các API bên ngoài nằm ở nhiều bộ Javadoc. Mỗi root URL phải đúng version dependency đang dùng, đọc được metadata và thực sự publish các HTML đích. Nếu thư viện 2.0 đã bỏ một method của 1.0, việc dùng metadata sai phiên bản có thể sinh link không tồn tại.

### 4.1. `element-list` và `package-list`

| File | Mục đích |
| --- | --- |
| `element-list` | Danh mục module/package của Javadoc mới, đặc biệt liên quan đến module |
| `package-list` | Danh mục package trong bộ docs không theo module, vẫn được hỗ trợ để liên kết |

Đây là metadata **do Javadoc sinh**, dùng để xác định cách dẫn tới API bên ngoài. Nó **không** chứng minh từng trang class hay từng anchor method còn tồn tại trên HTTP server. `-link` có thể xác nhận đã đọc danh sách nhưng không crawl tất cả URL tương lai được tạo ra.

Từ Java 9, tài liệu module có thể chứa tiền tố module trong URL. Khi nâng JDK hoặc dependency, kiểm tra cả version metadata và public URL. Địa chỉ root nên dùng HTTPS và có phiên bản rõ ràng nếu bộ docs được version hóa.

### 4.2. Không dùng `-link` cho website không có metadata

Với bài viết, RFC, trang hướng dẫn, tài liệu Markdown hoặc website thường, dùng:

```java
/**
 * See the <a href="https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html">
 * official Javadoc guide</a>.
 */
```

`-link` cần một bộ **Javadoc** có metadata; `@see` + HTML có thể dẫn tới trang bất kỳ. URL trực tiếp phải tham gia quy trình link check sau này.

## 5. `-linkoffline`: giữ link công khai nhưng đọc metadata cục bộ

Có trường hợp máy chạy CI không được phép kết nối đến website Javadoc ngoài. Khi đó có thể dùng `-linkoffline`:

```text
-linkoffline <PUBLIC_JAVADOC_ROOT> <LOCAL_METADATA_DIRECTORY>
```

Đối số thứ nhất là URL gốc sẽ được **ghi vào HTML cho người đọc**. Đối số thứ hai là **thư mục local có `element-list`/`package-list`**, để Javadoc đọc trong quá trình build.

Ví dụ trên máy có mạng, lưu đúng metadata một lần:

```bash
mkdir -p cache/jdk17
curl -fL https://docs.oracle.com/en/java/javase/17/docs/api/element-list \
  -o cache/jdk17/element-list
```

Trên Windows PowerShell, dùng `curl.exe` nếu `curl` là alias của cmdlet. Kiểm tra nguồn file metadata và lưu vào cache được quản lý. Khi chạy offline:

```bash
javadoc --release 17 --module-source-path src \
  --module com.example.catalog -d build/docs \
  -Xdoclint:all -Werror -quiet \
  -linkoffline https://docs.oracle.com/en/java/javase/17/docs/api/ cache/jdk17
```

Lệnh tạo hyperlink bên ngoài nhưng **không tải toàn bộ trang tài liệu ngoài**. Người dùng đọc tài liệu vẫn cần mạng khi nhấp link HTTPS. Đừng nhầm `-linkoffline` với “đóng gói docs để đọc offline”. Nếu metadata cũ còn URL mới, có thể có link hỏng dù Javadoc build thành công; hãy pin/cache cùng version và review khi nâng API.

## 6. Đường dẫn tương đối và fragment trong HTML

Ví dụ một số thẻ có thể có trong HTML:

```html
<a href="../../../../index.html">Index</a>
<a href="Catalog.html#count(java.util.List)">count</a>
<a href="#method-summary">Methods</a>
<a href="https://docs.oracle.com/en/java/javase/17/docs/api/">JDK API</a>
```

- Đường dẫn `../` được giải **từ file HTML chứa href**, không phải thư mục người dùng chạy lệnh Javadoc.
- Fragment `#count(java.util.List)` yêu cầu HTML đích có phần tử `id` phù hợp. Nhiều URL mã hóa ký tự bằng percent encoding, nên checker phải giải mã.
- URL bắt đầu bằng `/` thường là đường dẫn root website; nếu docs publish dưới `/docs/api/`, một link `/api/` có thể trỏ nhầm.
- Case của tên file có thể phân biệt trên server Linux ngay khi link chạy được ở filesystem Windows.
- URL bên ngoài có thể redirect, đòi đăng nhập, bị rate limit hoặc đã chết. HTTP `200` không chứng minh link đó có đúng nội dung/version.

Tốt nhất là kiểm tra **artifact HTML đã sinh**, sau đó smoke-test bản **đã publish** để phát hiện sai base path và thiếu file upload.

## 7. DocLint không phải trình kiểm tra URL HTTP

`-Xdoclint:all` phát hiện nhiều lỗi trong **source Javadoc comments** như HTML không hợp lệ, tham chiếu không giải được, sai một số Javadoc tag và các vấn đề accessibility. `-Werror` biến warning thành thất bại của build. Những kiểm tra này cần thiết nhưng có giới hạn.

DocLint **không tự**:

- Gửi request tới từng URL `<a href="https://...">` để nhận diện `404`/`410`.
- Đảm bảo mọi trang class/method từ `-link` hiện hữu trên HTTP server.
- Kiểm tra đầy đủ file và fragment của **output HTML** đã qua doclet, asset, template.
- Xác định một trang trả `200` có phải tài liệu đúng version không.
- Xác minh URL ngoài sau khi website đã được deploy sang domain/path khác.

Một Javadoc comment chứa `<a href="https://example.invalid/missing">` có HTML hợp lệ nhưng link không truy cập được. Điều đó đòi hỏi **hậu kiểm** độc lập.

Quy trình chất lượng:

```text
javac --release 17 → xác nhận source/module đúng
          ↓
javadoc -Xdoclint:all -Werror → symbol/comment có chất lượng
          ↓
kiểm tra href và #id nội bộ → artifact docs không thiếu đường dẫn
          ↓
kiểm tra HTTP(S) có kiểm soát → URL ngoài còn truy cập được
          ↓
publish và smoke-test URL thực → không sai base path/upload
```

## 8. Công cụ nhỏ để kiểm tra link/anchor sau khi tạo Javadoc

Để thấy rõ cách kiểm tra output, dùng script Python 3.9+ standard library bên dưới. Nó quét mọi file `.html` trong thư mục `build/docs`, thu thập `a[href]` và `id`, giải đường dẫn tương đối, xác nhận file/fragment nội bộ. Chế độ `--external` tùy chọn thử một **mẫu giới hạn** URL HTTP(S).

Đây là công cụ hỗ trợ bài học Java, không đòi thư viện Python ngoài. Tạo file **`check_javadoc_links.py`** ở thư mục chứa `src/`:

```python
#!/usr/bin/env python3
"""Check local Javadoc links and optionally sample external HTTP URLs."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "a":
            if values.get("name"):
                self.ids.add(values["name"])
            if values.get("href"):
                self.hrefs.append(values["href"])


def inspect(root, check_external=False, max_external=20):
    root = root.resolve()
    pages = sorted(root.rglob("*.html"))
    if not pages:
        return ["No generated HTML pages found"], [], 0

    index = {}
    for page in pages:
        parser = Page()
        parser.feed(page.read_text(encoding="utf-8"))
        parser.close()
        index[page.resolve()] = parser

    failures = []
    warnings = []
    remote = set()
    checked = 0

    for source, page in index.items():
        for href in page.hrefs:
            url = urlsplit(href)
            if url.scheme in ("https", "http") or href.startswith("//"):
                remote.add(("https:" + href) if href.startswith("//") else href)
                continue
            if url.scheme or url.netloc:
                # mailto:, tel:, javascript: etc. are not local files.
                continue

            relative = unquote(url.path)
            if relative.startswith("/"):
                failures.append(f"{source}: root-relative link: {href}")
                continue

            target = ((source.parent / relative) if relative else source).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.is_relative_to(root):
                failures.append(f"{source}: link leaves docs root: {href}")
                continue
            if not target.is_file():
                failures.append(f"{source}: missing file: {href}")
                continue

            checked += 1
            if url.fragment and target.suffix.lower() == ".html":
                ids = index.get(target)
                if ids is None or unquote(url.fragment) not in ids.ids:
                    failures.append(f"{source}: missing anchor: {href}")

    if check_external:
        urls = sorted(remote)
        if len(urls) > max_external:
            warnings.append(f"Only first {max_external} of {len(urls)} remote URLs sampled")
        for link in urls[:max_external]:
            address = link.split("#", 1)[0]
            try:
                req = Request(address, headers={"User-Agent": "JavadocLinkCheck/1.0"})
                with urlopen(req, timeout=8) as response:
                    response.read(1)
            except HTTPError as exc:
                if exc.code in (404, 410):
                    failures.append(f"Remote URL gone ({exc.code}): {link}")
                else:
                    warnings.append(f"Remote URL unverified ({exc.code}): {link}")
            except (URLError, TimeoutError, OSError) as exc:
                warnings.append(f"Remote URL unverified ({type(exc).__name__}): {link}")
    elif remote:
        warnings.append(f"{len(remote)} remote URLs not checked; use --external")

    return failures, warnings, checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("docs", type=Path)
    parser.add_argument("--external", action="store_true")
    parser.add_argument("--max-external", type=int, default=20)
    args = parser.parse_args()
    if args.max_external < 0:
        parser.error("--max-external must be >= 0")

    failures, warnings, checked = inspect(
        args.docs, args.external, args.max_external)
    for item in warnings:
        print("WARN:", item)
    for item in failures:
        print("BROKEN:", item)

    if failures:
        raise SystemExit(1)
    print(f"PASS: {checked} local links and anchors")


if __name__ == "__main__":
    main()
```

Sau khi tạo docs:

```bash
python check_javadoc_links.py build/docs
```

Khi không có lỗi file/anchor, dòng cuối stdout sẽ có dạng:

```text
PASS: <N> local links and anchors
```

`<N>` là số lượng được đếm **tại runtime**; nó phụ thuộc Javadoc/JDK và không được chụp cứng trong test. Nếu file HTML thiếu, file đích không tồn tại hoặc fragment sai, script in `BROKEN: ...` và trả exit code `1`.

Nếu muốn kiểm tra các URL HTTP(S) đầu tiên với timeout:

```bash
python check_javadoc_links.py build/docs --external --max-external 20
```

Script cố ý **không** quét Internet không giới hạn. Với remote: `404`/`410` báo link đã chết, còn `403`/`429`/timeout/lỗi mạng là **không xác minh được**, cần thử lại hoặc kiểm tra thủ công. Chế độ này không xác nhận fragment từ xa và chỉ tìm `<a href>`, không kiểm tra liên kết trong CSS, JavaScript hay nội dung trang phía máy chủ.

Dự án lớn nên sử dụng link checker chuyên dụng, có retry/backoff, giới hạn concurrency, cache kết quả và cấu hình domain/exclusion. Không biến mọi PR thành phụ thuộc mạng của hàng chục nhà cung cấp ngoài.

### 8.1. Kiểm chứng checker thật sự báo lỗi

Thực hành trên một **bản sao** của `build/docs`:

1. Di chuyển tạm một file có link tới nó, ví dụ `Catalog.html`.
2. Chạy `python check_javadoc_links.py <thu-muc-docs-ban-sao>`.
3. Kiểm tra thông báo `BROKEN: ... missing file` và mã thoát `1`.
4. Khôi phục file; thay một href fragment bằng `#khong-ton-tai`, rồi chạy lại để thấy `missing anchor`.

Các thao tác phá link chỉ dùng cho fixture; không sửa bản output chính rồi để vậy. Khi phát hiện lỗi thật, sửa Javadoc nguồn hoặc bước publish và generate lại.

## 9. Chính sách CI và kiểm tra sau deploy

Một pipeline điển hình:

```bash
javac --release 17 --module-source-path src \
  -d build/mods --module com.example.catalog

javadoc --release 17 --module-source-path src \
  --module com.example.catalog -d build/docs \
  -Xdoclint:all -Werror -quiet

python check_javadoc_links.py build/docs
```

Trong Bash có thể bật `set -e` để dừng khi lệnh lỗi; trong PowerShell/CMD cần kiểm tra exit code cho từng bước. Dùng `-linkoffline` trong pipeline không cho phép truy cập docs ngoài. Kiểm tra HTTP(S) có thể chuyển sang job định kỳ hoặc trước release, để tránh PR bị treo do rate limit.

| Giai đoạn | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Mỗi PR | Javac, Javadoc DocLint, link/anchor local | Fail nếu source hoặc docs artifact hỏng |
| Định kỳ | HTTP(S) external với timeout/retry/throttle | Báo cáo link 404/410 và nhóm chưa xác minh |
| Khi nâng dependency/JDK | Root docs và `element-list`/`package-list` đúng version | Cross-link sang API tương ứng |
| Trước release | Review các link trọng yếu và các redirect | Tài liệu dẫn tới bản chính xác |
| Sau deploy | Kiểm tra URL website thật, base path, case, asset được upload | Link hoạt động tại môi trường người đọc |

Đừng phụ thuộc số lượng file HTML/anchor tuyệt đối vì Javadoc có thể thay layout qua các phiên bản. Bắt những bất biến có ích: **API biên dịch, Javadoc warning-free, không thiếu file/fragment, URL công khai đúng version**.

## 10. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Dùng `{@link https://...}` | `@link` chỉ dùng cho Java symbols | Dùng `<a href>` |
| `-link` trỏ `List.html` | Đầu vào không phải Javadoc root | Trỏ thư mục chứa metadata |
| Có metadata nhưng class HTTP 404 | Version không khớp hoặc website thiếu file | Pin đúng phiên bản và kiểm tra URL thật |
| `-linkoffline` thiếu đối số | Thiếu đường dẫn metadata local | Truyền cả public root và local dir |
| DocLint PASS nhưng URL website 404 | DocLint không kiểm tra HTTP | Thêm kiểm tra ngoài sau generation |
| Tắt DocLint để tránh warning | Che lỗi source dễ sửa | Giữ `-Xdoclint:all -Werror` và sửa tài liệu |
| Đường dẫn chạy ở Windows, hỏng ở Linux | Case sensitivity hoặc base path | Kiểm tra artifact/hosting mục tiêu |
| Method link sai fragment | Chữ ký/anchor đã đổi | Dùng symbol link thay tự ghép URL |
| HTTP 403/429 từ CI | Rate limit/bot/auth | Đánh dấu chưa xác minh, retry/backoff |
| File được generate nhưng chưa upload | Pipeline publish thiếu asset | Kiểm tra sau deploy |
| Không kiểm tra anchor | Trang trả 200 nhưng mục đã bị xóa | Quét `#id` và smoke-test remote cần thiết |

## 11. Checklist trước khi xuất bản

- [ ] Source có `module-info.java`, `exports` đúng package API.
- [ ] `javac --release` và `javadoc --release` phù hợp phiên bản được hỗ trợ.
- [ ] Java symbol dùng `{@link}`/`{@linkplain}`/`@see`; URL web dùng `<a href>`.
- [ ] External `-link` trỏ đúng root Javadoc và version có `element-list`/`package-list`.
- [ ] Nếu offline, cache metadata đáng tin cậy và được cập nhật có review.
- [ ] `-Xdoclint:all -Werror` chạy thành công, không che mọi cảnh báo.
- [ ] Link nội bộ và fragment được kiểm tra trong toàn bộ HTML đã sinh.
- [ ] Remote URLs được kiểm tra với giới hạn, phân biệt link chết và lỗi mạng.
- [ ] URL tương đối, chữ hoa/thường, base path và file được kiểm tra trên bản publish.
- [ ] Link quan trọng được review khi nâng dependency/JDK hoặc thay hosting.

## Tài liệu tham khảo

- [Javadoc Command, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html) — `-link`, `-linkoffline`, module options, DocLint.
- [Documentation Comment Specification, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html) — `{@link}`, `{@linkplain}`, `@see`.
- [Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/) — bộ docs module JDK.
- [OpenJDK JEP 261](https://openjdk.org/jeps/261) — Java Platform Module System.
- [Javadoc Manual, Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html) — khả năng và giới hạn của DocLint.

**Ghi nhớ:** `javadoc` giúp tạo liên kết API theo symbol và metadata; DocLint kiểm tra tài liệu đầu vào; kiểm tra HTML và HTTP sau khi sinh giúp giữ các liên kết thực sự sử dụng được. Khi phát hành module Java, cần bảo đảm **đúng phiên bản API, đúng root docs và đúng artifact đã publish**.
