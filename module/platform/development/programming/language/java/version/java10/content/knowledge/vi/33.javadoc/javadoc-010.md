# Java 10 — Javadoc: Tài nguyên HTML trong thư mục `doc-files`

## 1. Bài học tập trung vào điều gì?

Khi một Java library có tài liệu chi tiết hơn vài đoạn comment trên class hoặc method — ví dụ **hướng dẫn sử dụng, sơ đồ, giải thích thuật toán, quy ước dữ liệu, mô tả luồng xử lý hoặc ví dụ dài** — có thể đặt **trang HTML bổ sung** trong thư mục có tên chính xác là **`doc-files`** nằm dưới source directory của package.

**Điểm nhấn của Java 10:** bản cập nhật **JDK-8185985** trong JDK 10 bổ sung khả năng của **Standard Doclet**: các tệp HTML trong `doc-files` được xử lý thành những trang tài liệu có **header, footer và navigation** phù hợp với các trang API Javadoc, thay vì chỉ sao chép nguyên tệp như một asset thô. Các **Javadoc comment tags thích hợp bên trong HTML** cũng được xử lý.

Khả năng này **vẫn còn áp dụng trong JDK hiện đại**. Theo **JavaDoc Documentation Comment Specification của JDK 25**:

- Tài liệu bổ sung có thể nằm trong `doc-files/*.html` (và `*.md` trên các JDK mới hỗ trợ Markdown).
- Đối với HTML, nội dung của phần tử **`<main>`**, hoặc **`<body>` nếu không có `<main>`**, được xử lý như nội dung Javadoc truyền thống.
- Trang HTML độc lập trong `doc-files` nên bắt đầu với heading cấp **`<h1>`**.
- JavaDoc chuẩn tạo vỏ trang, điều hướng và áp dụng các tags phù hợp.
- Các assets phụ trợ như SVG/PNG/text có thể được chép cùng trang theo các quy tắc của Standard Doclet.

**Mục tiêu của bài:** tạo một trang HTML `doc-files/guide.html`, liên kết từ `package-info.java` và class `Widget`, tham chiếu ngược tới Java API bằng `{@link ...}`, chép SVG vào output và tự kiểm tra kết quả sau khi chạy `javadoc`.

Bài học sử dụng API và công cụ còn được hỗ trợ trên JDK 17+, đã thực nghiệm với **OpenJDK 24.0.2**; các tính năng hiện đại như Markdown trong `doc-files` được phân biệt đúng phiên bản, không coi là tính năng Java 10 ban đầu.

## 2. Khi nào cần một trang HTML riêng?

Javadoc comments của một class/method nên tập trung vào **contract, hành vi, tham số, giá trị trả về, ngoại lệ và các ràng buộc quan trọng**. Nếu cố nhét cả một hướng dẫn dài vào comment của method, phần tài liệu sinh ra khó đọc và khó bảo trì.

`doc-files` phù hợp khi cần:

1. **User guide** của package: ví dụ cấu hình và cách sử dụng library qua nhiều bước.
2. **Hướng dẫn kiến trúc**: pipeline, data flow, state machine và sequence diagrams.
3. **Quy ước file/protocol** có các ví dụ HTML, bảng, hình minh họa.
4. **Compatibility notes** dài, nhiều tình huống và link tới các API liên quan.
5. **Danh sách ví dụ** và tài nguyên bổ trợ cần xuất hiện bên cạnh API docs.
6. **Các hình SVG/PNG** được trang tài liệu hoặc API comment nhúng vào.
7. **Tài liệu dành riêng cho package** thay vì bắt người đọc mở một site khác.

Ví dụ: Javadoc của `Widget.render(String)` chỉ cần nói phương thức chuẩn hóa text thế nào, còn `doc-files/guide.html` có thể giải thích luồng xử lý và cho liên kết tới ví dụ minh họa.

### 2.1. Điều mà `doc-files` không làm

- Không thay thế `javac` hoặc đơn vị biên dịch Java.
- Không biến một tệp HTML thành một class/method trong Java.
- Không tự tạo liên kết điều hướng tới **mọi** tài nguyên nếu bạn không đưa link từ tài liệu đã được truy cập.
- Không tự đóng gói HTML vào Java runtime JAR nếu build tool không được cấu hình sao chép.
- Không phải một thư mục để lưu trữ mọi loại dữ liệu nội bộ hoặc bí mật.
- Không thay thế tài liệu package bằng `package-info.java` khi mục đích chỉ là mô tả package ngắn.
- Không bảo đảm JavaScript hoặc arbitrary HTML của người viết là an toàn.

## 3. Tại sao phải đặt đúng thư mục `doc-files`?

Đối với source layout phổ biến:

```text
project/
  src/
    com/
      acme/
        docs/
          package-info.java
          Widget.java
          doc-files/
            guide.html
            fallback.html
            assets/
              flow.svg
```

`doc-files` là **con của source package directory `com/acme/docs`**. Standard Doclet duyệt package được yêu cầu document và xử lý `doc-files` tương ứng.

Nếu package Java là `com.acme.docs` thì tài nguyên thường nằm tại:

```text
<source-root>/com/acme/docs/doc-files/guide.html
```

Không nên đặt nhầm:

```text
<source-root>/com/acme/doc-files/guide.html
```

rồi nghĩ đó là trang của package `com.acme.docs`. Thư mục `com/acme` là một vị trí khác; nếu không có package source tương ứng được document, bạn không được tự suy rằng tool sẽ tìm và chép tài nguyên như mong muốn.

### 3.1. Package-based, không phải classpath-based

`javadoc` thu thập source và file documentation theo các options như `-sourcepath`, `--module-source-path` hoặc danh sách source elements. Một tệp `guide.html` có trên **runtime classpath** không tự động trở thành trang documentation.

Nếu sử dụng Maven/Gradle, phải xác định chính xác source root nào mà **Javadoc task** đang dùng, không chỉ thư mục build resources.

### 3.2. Mối quan hệ với output

Nếu chạy:

```bash
javadoc -d out -sourcepath src com.acme.docs
```

trên một dự án dùng layout ở trên, output theo package thường là:

```text
out/
  index.html
  ...
  com/
    acme/
      docs/
        package-summary.html
        Widget.html
        doc-files/
          guide.html
          fallback.html
          assets/
            flow.svg
```

`package-summary.html` và `Widget.html` do Standard Doclet tạo từ Java source. Hai tệp `guide.html` và `fallback.html` xuất phát từ `doc-files`, nhưng nội dung HTML đã được **xử lý/đưa vào vỏ trang Javadoc**, không đơn thuần là copy byte-for-byte ở các JDK đang hỗ trợ tính năng.

Đường dẫn cụ thể và định dạng HTML bên trong trang sinh ra là **output của Standard Doclet**, không phải một Java SE runtime API; hãy luôn kiểm tra kết quả khi đổi JDK.

## 4. Cơ chế xử lý tệp HTML của Javadoc hiện đại

Theo specification JDK 25:

- File có đuôi **`.html`** được coi là tài liệu HTML.
- Nếu có một **`<main>`**, **phần nội dung của `<main>`** được dùng làm nội dung tài liệu.
- Nếu không có `<main>`, dùng nội dung của **`<body>`**.
- Nội dung ấy được xử lý tương tự một **traditional documentation comment**.
- JavaDoc Standard Doclet tạo trang hoàn chỉnh với navigation/layout của bộ tài liệu.

Minh họa:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Widget Guide</title>
</head>
<body>
<main>
  <h1>Widget usage guide</h1>
  <p>See {@link com.acme.docs.Widget} for its API.</p>
</main>
<footer>Outside the main content</footer>
</body>
</html>
```

Trên JDK hỗ trợ cơ chế trên, **nội dung giữa `<main>` và `</main>`** là nội dung tài liệu. Đừng kỳ vọng `<footer>` nằm ngoài `<main>` sẽ được giữ nguyên như footer bạn tự viết, vì Javadoc tạo chính footer/navigation của nó.

### 4.1. Dùng `<main>` để chỉ rõ nội dung

Ưu điểm của việc có `<main>`:
- Cho biết phần nào là nội dung thực sự của bài;
- Tránh nhầm các footer/nav tự viết là một phần của Javadoc;
- Giúp cấu trúc HTML5 rõ ràng;
- Làm kết quả dễ kiểm tra theo specification.

Với HTML ngắn chỉ có `<body>` mà không có `<main>`, JavaDoc có cơ chế **fallback** sang body. Ta sẽ kiểm chứng cả hai trường hợp bằng ví dụ.

### 4.2. Trang nguồn không được đảm bảo giữ nguyên mọi markup

Bởi Javadoc có bước **xử lý và tái tạo trang**, không nên:
- Đòi `<head>` hoặc `<footer>` tự viết xuất hiện y nguyên trong output;
- Đo hash input HTML với output và đòi khớp byte;
- Suy ra một class CSS nội bộ của Javadoc là ổn định mãi mãi;
- Đưa scripts hoặc navigation tự tùy biến mà không hiểu chính sách Standard Doclet.

**Đối tượng cần kiểm thử là nội dung/tính năng trang sau khi sinh**, bao gồm link, heading, assets và tính khả dụng của file.

## 5. Javadoc tags có thể hoạt động ngay trong HTML

Điểm cải tiến đáng chú ý ở JDK 10 là các **comment tags thích hợp** trong `doc-files/*.html` được xử lý.

Ví dụ một file HTML viết:

```html
<p>
  See {@link com.acme.docs.Widget#render(String)} for the API.
</p>
```

Trong output đã kiểm chứng bằng **javadoc 24.0.2**, phần này thành một liên kết tương ứng tới API:

```html
<p>See <a href="../Widget.html#render(java.lang.String)"><code>render(String)</code></a> for the API.</p>
```

Đây là đoạn **HTML output đã được rút gọn** theo phần mà chương trình test kiểm tra, không phải cam kết JavaDoc luôn dùng chính xác class/markup này ở mọi version.

### 5.1. Viết tham chiếu fully qualified khi cần

Trong một HTML file độc lập, không có `import java...` giống một Java source file. Khi sử dụng JavaDoc reference tags, cách an toàn/dễ review là ghi đầy đủ:

```text
{@link com.acme.docs.Widget}
{@link com.acme.docs.Widget#render(String)}
{@link java.util.List}
```

Đừng giả định mọi simple class name luôn được resolve chính xác trong các file HTML không có context của một source file Java.

### 5.2. Không phải mọi chuỗi chứa `@` đều là tag được xử lý

`{@link ...}` là cú pháp inline JavaDoc tag đúng. Nếu bạn muốn hiển thị chính chuỗi literal `{@link ...}` để giảng dạy cú pháp, phải dùng cách escape/định dạng phù hợp và kiểm tra output; nếu không Javadoc có thể xử lý nó thành liên kết.

Các block tags như `@see` có những vị trí hỗ trợ được specification quy định. Không chuyển tùy tiện mọi tag từ class comment sang HTML rồi đoán ngữ nghĩa; xem JavaDoc tag matrix của JDK đang dùng.

## 6. Liên kết tương đối giữa class/package và HTML `doc-files`

Giả sử output:

```text
out/com/acme/docs/Widget.html
out/com/acme/docs/package-summary.html
out/com/acme/docs/doc-files/guide.html
out/com/acme/docs/doc-files/assets/flow.svg
```

Từ **`Widget.html`** hoặc **`package-summary.html`**, liên kết tới guide là:

```html
<a href="doc-files/guide.html">HTML usage guide</a>
```

Từ guide quay lại class page:

```html
<a href="../Widget.html">Widget API page</a>
```

Từ guide tới asset trong thư mục con:

```html
<img src="assets/flow.svg" alt="Flowchart showing input to output">
```

Và liên kết tới một mục cụ thể trong guide:

```html
<a href="doc-files/guide.html#processing-steps">Processing steps</a>
```

### 6.1. Bảng đường dẫn cần nhớ

| Vị trí đang viết liên kết | Đường dẫn cần đi | URL tương đối |
|---|---|---|
| `Widget.java` Javadoc comment | `doc-files/guide.html` | `doc-files/guide.html` |
| `package-info.java` comment | `doc-files/guide.html` | `doc-files/guide.html` |
| `guide.html` trong `doc-files` | `Widget.html` cùng package | `../Widget.html` |
| `guide.html` trong `doc-files` | `assets/flow.svg` bên dưới | `assets/flow.svg` |
| `Widget.java` comment | heading trong guide | `doc-files/guide.html#processing-steps` |

Thư mục output là **quan trọng nhất** để suy ra đường dẫn tương đối. Hãy kiểm tra links sau khi chạy `javadoc`; không chỉ đoán bằng vị trí source file.

### 6.2. Đừng tạo absolute filesystem URLs

Không viết:

```html
<!-- Không portable khi tài liệu được publish -->
<a href="C:\work\src\com\acme\docs\doc-files\guide.html">Guide</a>
```

Đây là **anti-pattern**. Người khác mở documentation từ website hoặc JAR-published docs sẽ không có ổ `C:` của bạn. Dùng **relative URL** trong generated site.

### 6.3. Phân biệt URI và filesystem path

Trong HTML, URLs dùng dấu `/` ngay cả khi người phát triển chạy trên Windows. Khi tạo folders trong PowerShell có thể dùng `\`, nhưng trong `href`/`src` vẫn dùng slash theo URI path.

## 7. Dự án ví dụ hoàn chỉnh và cách tổ chức

Ta tạo một Java package tên **`com.acme.docs`** với một class có phương thức thật, hai trang HTML bổ sung, một SVG và một thư mục chỉ chứa tài liệu nội bộ để kiểm tra bộ lọc loại trừ.

```text
project/
  src/
    com/
      acme/
        docs/
          package-info.java
          Widget.java
          doc-files/
            guide.html
            fallback.html
            assets/
              flow.svg
            private-not-for-publication/
              draft.txt
  DocFilesOutputCheck.java
```

Mục đích từng file:

- `Widget.java`: mã Java chạy được, có liên kết Javadoc tới guide.
- `package-info.java`: nội dung tổng quan package và link trực tiếp tới guide.
- `guide.html`: trang HTML5 có `<main>`, `<h1>`, `{@link ...}` và ảnh SVG.
- `fallback.html`: trang có `<body>` nhưng **không có `<main>`**, kiểm tra fallback.
- `assets/flow.svg`: asset được chép vào generated documentation.
- `private-not-for-publication/draft.txt`: dữ liệu giả để kiểm tra exclude option.
- `DocFilesOutputCheck.java`: chương trình Java 17+ đọc generated output và kiểm tra các đặc điểm có thể dự đoán.

Tất cả là **dữ liệu demo**; không có thông tin riêng tư của người dùng, credentials hoặc tài nguyên production.

## 8. Tệp 1 — `package-info.java`

Đường dẫn: **`src/com/acme/docs/package-info.java`**.

```java
/**
 * Utilities documented with an
 * <a href="doc-files/guide.html">HTML usage guide</a>.
 *
 * <p>See
 * <a href="doc-files/guide.html#processing-steps">
 * processing steps</a>.
 */
package com.acme.docs;
```

`package-info.java` là nơi được khuyến nghị để mô tả package. Có thể thêm annotations/imports phù hợp nếu cần; ở ví dụ này chỉ có Javadoc comment và package declaration.

**Chú ý:**
- Đây là Java source **không có method `main`**; không dùng `java package-info`.
- `javadoc` tạo `package-summary.html` cho package từ phần mô tả này.
- Link `doc-files/guide.html` phải được duy trì cùng trang HTML tương ứng.
- Việc dùng `package-info.java` là lựa chọn hiện đại, thay vì dựa vào `package.html` theo lối lịch sử.

## 9. Tệp 2 — `Widget.java` (chương trình Java hoàn chỉnh)

Đường dẫn: **`src/com/acme/docs/Widget.java`**.

```java
package com.acme.docs;

import java.util.Objects;

/**
 * Example API with a
 * <a href="doc-files/guide.html">usage guide</a>.
 */
public final class Widget {
    private Widget() {
    }

    /**
     * Renders text after removing surrounding whitespace.
     *
     * @param text the text; must not be null
     * @return the normalized text
     * @throws NullPointerException if text is null
     */
    public static String render(String text) {
        return Objects.requireNonNull(text, "text").trim();
    }

    /**
     * Runs the example program.
     *
     * @param args ignored
     */
    public static void main(String[] args) {
        System.out.println(
                "rendered=" + render("  doc-files  "));
    }
}
```

Biên dịch ở project root:

```bash
javac --release 17 -encoding UTF-8 \
  -d classes \
  src/com/acme/docs/package-info.java \
  src/com/acme/docs/Widget.java
```

Chạy:

```bash
java -cp classes com.acme.docs.Widget
```

**Stdout chính xác đã kiểm chứng trên OpenJDK 24.0.2:**

```text
rendered=doc-files
```

### 9.1. Vì sao cần một chương trình thật?

Để chứng minh library chứa mã Java hợp lệ, không phải chỉ là một website HTML. `Widget.render(String)` có behavior rõ, test độc lập với `javadoc`. Sau đó `javadoc` biến comments thành tài liệu, còn `doc-files` bổ sung hướng dẫn cho người đọc.

### 9.2. Không nhầm tạo tài liệu với build runtime

Lệnh `javac` tạo `Widget.class`. Lệnh `javadoc` tạo HTML documentation. Hai nhiệm vụ khác nhau:

```text
Widget.java -- javac --> Widget.class
Widget.java -- javadoc --> Widget.html
guide.html  -- javadoc --> doc-files/guide.html (processed)
```

Một Java runtime không cần HTML documentation để thực thi `Widget.render`; HTML được build/publish riêng cho người đọc API.

## 10. Tệp 3 — `guide.html` chứa `<main>`, Javadoc tag và ảnh

Đường dẫn: **`src/com/acme/docs/doc-files/guide.html`**.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Widget Guide</title>
</head>
<body>
<main>
  <h1>Widget usage guide</h1>

  <p>
    See {@link com.acme.docs.Widget#render(String)}
    for the API.
  </p>

  <h2 id="processing-steps">Processing steps</h2>

  <p>
    <a href="../Widget.html">Widget API page</a>.
  </p>

  <p>
    <img src="assets/flow.svg"
         alt="Flowchart showing input to output">
  </p>
</main>
<footer>ORIGINAL_FOOTER_OUTSIDE_MAIN</footer>
</body>
</html>
```

Trang này có ba điểm cần quan sát:

1. **`<main>`** chỉ rõ phần nội dung để Javadoc xử lý.
2. **`{@link com.acme.docs.Widget#render(String)}`** là JavaDoc reference tag và sẽ được render thành hyperlink nếu resolve đúng symbol.
3. **`<img src="assets/flow.svg"...>`** dùng URL tương đối tới tài nguyên `doc-files` trong output.

### 10.1. `ORIGINAL_FOOTER_OUTSIDE_MAIN` để làm gì?

Chuỗi này là **dấu mốc kiểm thử** nằm ngoài `<main>`. Theo spec hiện đại, nội dung tài liệu lấy từ `<main>`, nên ta có thể kiểm tra rằng dấu mốc này **không** xuất hiện trong generated HTML.

Đây là dữ liệu không nhạy cảm, chỉ giúp hiểu chính xác phần nào của file input được Standard Doclet xử lý.

### 10.2. Tại sao heading bắt đầu `<h1>`?

Oracle JDK 25 doc-comment spec khuyến nghị **các standalone HTML pages trong `doc-files` bắt đầu ở heading level 1**. Điều này khác với heading bên trong Java class comment, nơi heading thường cần bắt đầu ở cấp thấp hơn để phù hợp cấu trúc trang API.

Sử dụng:

```html
<h1>Widget usage guide</h1>
<h2 id="processing-steps">Processing steps</h2>
```

vừa rõ nghĩa vừa tạo mục liên kết nội bộ `#processing-steps`.

### 10.3. Tại sao `id` có dấu gạch ngang?

Oracle docs khuyến nghị user-defined `id` nên có ký tự **không hợp lệ trong Java identifier**, chẳng hạn dấu `-`, giúp giảm nguy cơ trùng với IDs do Javadoc tự tạo cho những declaration/API sections.

`id="processing-steps"` là một lựa chọn dễ đọc và giảm rủi ro va chạm.

## 11. Tệp 4 — `fallback.html` chỉ có `<body>`

Đường dẫn: **`src/com/acme/docs/doc-files/fallback.html`**.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Fallback Guide</title>
</head>
<body>
  <h1>Fallback body example</h1>
  <p>See {@link com.acme.docs.Widget}.</p>
</body>
</html>
```

Trang này **không có `<main>`**. Theo doc-comment spec hiện hành, Javadoc sẽ lấy nội dung từ **`<body>`** làm tài liệu, vẫn xử lý JavaDoc tags thích hợp.

Trong thử nghiệm OpenJDK 24.0.2:
- `fallback.html` được sinh ra;
- Dòng `Fallback body example` tồn tại trong generated HTML;
- `{@link ...}` trong body được xử lý, không còn nguyên chuỗi tag.

**Khuyến nghị:** vẫn ưu tiên dùng `<main>` cho trang HTML dài, nhưng hiểu fallback `<body>` khi đọc và bảo trì tài liệu đang có.

## 12. Tệp 5 — ảnh SVG trong thư mục con

Đường dẫn: **`src/com/acme/docs/doc-files/assets/flow.svg`**.

```xml
<svg xmlns="http://www.w3.org/2000/svg"
     width="140" height="40"
     viewBox="0 0 140 40"
     role="img" aria-label="Input to output">
  <rect width="140" height="40" fill="#f8f8f8"/>
  <text x="8" y="25" fill="#222" font-size="12">
    input to output
  </text>
</svg>
```

Tài nguyên này là một **SVG độc lập**. Trong `guide.html` đã có:

```html
<img src="assets/flow.svg"
     alt="Flowchart showing input to output">
```

Nếu sử dụng `-docfilessubdirs` trên JDK24/25, doclet sẽ chép thư mục con `assets` cùng tài liệu theo cấu hình. Trong output được kiểm chứng, file tồn tại tại:

```text
out/com/acme/docs/doc-files/assets/flow.svg
```

### 12.1. Accessibility

Nên:
- Có `alt` mô tả mục đích ảnh;
- Giữ SVG đọc được, không nhúng mã không cần thiết;
- Đảm bảo nội dung hữu ích không **chỉ** nằm trong ảnh;
- Sử dụng màu sắc có tương phản phù hợp;
- Có `width`/`height` hợp lý và kiểm tra hiển thị trên màn hình hẹp.

### 12.2. Không chỉ SVG mới được chép

`doc-files` có thể chứa PNG, JPEG, GIF, CSS, text example, tài liệu bổ trợ và các loại asset phù hợp. Nhưng **file được chép không mặc nhiên được Javadoc hiểu thành cú pháp chuyên biệt**:
- `*.html` được doclet xử lý như tài liệu HTML;
- Một số JDK mới xử lý `*.md` như Markdown docs;
- SVG/PNG là tài nguyên để browser sử dụng;
- Text/binary resources có thể chỉ được copy, không tự thành navigation page.

Chỉ đưa vào tài liệu publish những files **được phép công khai**. Không đưa keys, tokens hoặc internal-only documents vào `doc-files`.

## 13. Tùy chọn tạo tài liệu với `javadoc`

Sau khi tạo đủ files trong project root:

```bash
javadoc \
  -quiet \
  -Xdoclint:all \
  -encoding UTF-8 \
  -charset UTF-8 \
  -docfilessubdirs \
  -excludedocfilessubdir private-not-for-publication \
  -d out \
  -sourcepath src \
  com.acme.docs
```

**Đây là lệnh đã kiểm chứng trên Javadoc 24.0.2** (chuyển sang dòng lệnh phù hợp với shell: Bash dùng dấu `\` để nối dòng, PowerShell có cách nối dòng khác).

### 13.1. Giải thích cờ

| Option | Ý nghĩa |
|---|---|
| `-d out` | Thư mục lưu HTML output |
| `-sourcepath src` | Nơi tìm Java source packages |
| `com.acme.docs` | Package cần document |
| `-encoding UTF-8` | Mã ký tự đầu vào cho Java source/docs |
| `-charset UTF-8` | Charset ghi trong HTML output |
| `-Xdoclint:all` | Bật nhóm kiểm tra documentation, HTML, reference, accessibility, missing và syntax |
| `-docfilessubdirs` | Cho phép/chỉ rõ chép các thư mục con của `doc-files` theo Javadoc đang hỗ trợ |
| `-excludedocfilessubdir private-not-for-publication` | Bỏ qua một thư mục con đã định danh |
| `-quiet` | Giảm thông báo tiến độ; errors/warnings vẫn phải được xem xét |

### 13.2. Cú pháp một dòng, dùng được cả Windows shell và Bash

```bash
javadoc -quiet -Xdoclint:all -encoding UTF-8 -charset UTF-8 -docfilessubdirs -excludedocfilessubdir private-not-for-publication -d out -sourcepath src com.acme.docs
```

Dùng một dòng nếu bạn muốn tránh khác biệt nối dòng `\`/backtick ở Windows PowerShell.

### 13.3. Lưu ý về `-docfilessubdirs` trong các JDK mới

JDK 25 vẫn tài liệu hóa `-docfilessubdirs` cho **deep copying**. Ở một số bản phát triển JDK về sau, đệ quy có thể trở thành mặc định và option không còn cần thiết. Vì vậy:
- **Không lấy một giả định về default từ JDK khác** để bỏ qua kiểm thử;
- Dùng option được tool hiện tại hỗ trợ;
- Kiểm tra `javadoc --help` của runtime thật;
- Xác minh asset trong output.

### 13.4. Cách chặn tài liệu nội bộ lọt vào output

Trong ví dụ có file:

```text
src/com/acme/docs/doc-files/private-not-for-publication/draft.txt
```

Ta chạy:

```bash
-excludedocfilessubdir private-not-for-publication
```

để chỉ **exclude đúng thư mục được cấu hình**. Trong test, `draft.txt` không xuất hiện ở generated documentation.

**Cảnh báo bảo mật:** exclude option không được thay thế bằng việc cất secrets vào source documentation tree rồi hy vọng Javadoc luôn bỏ qua. Nếu file là private/internal, tốt hơn **không lưu nó trong cây tài liệu được publish**.

## 14. Kết quả đã kiểm thử với Java 17+ và Javadoc 24

Trên **OpenJDK 24.0.2**:
- Biên dịch `Widget.java` và `package-info.java` bằng **`javac --release 17`** thành công.
- Chạy `Widget.main`: `rendered=doc-files`.
- Chạy `javadoc -Xdoclint:all`: exit code **0**, không có lỗi tài liệu.
- Tệp HTML và SVG được tạo/copy theo đúng cấu trúc.
- Thẻ inline Javadoc `{@link ...}` được chuyển thành link API.
- Nội dung `<main>` xuất hiện, phần footer ngoài `<main>` bị bỏ theo behavior kiểm chứng.
- Trang chỉ có `<body>` được xử lý bằng fallback.
- Thư mục `private-not-for-publication` không được copy khi dùng exclude option.

Kết quả là **hành vi của bản build đã chạy thực tế**, không bảo đảm từng byte HTML/CSS sẽ giữ nguyên khi lên JDK 25/27.

## 15. Chương trình hoàn chỉnh 2 — kiểm tra output của `javadoc` bằng Java

Ta không chỉ nhìn log “javadoc done” mà còn đọc các tệp sinh ra để kiểm chứng. Tạo file **`DocFilesOutputCheck.java`** tại project root:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DocFilesOutputCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: DocFilesOutputCheck <javadoc-output>");
        }

        Path docs = Path.of(args[0]);
        Path pkg = docs.resolve("com/acme/docs");

        Path guide = pkg.resolve("doc-files/guide.html");
        Path fallback = pkg.resolve("doc-files/fallback.html");
        Path image = pkg.resolve("doc-files/assets/flow.svg");
        Path excluded = pkg.resolve(
                "doc-files/private-not-for-publication/draft.txt");

        String html = Files.readString(
                guide, StandardCharsets.UTF_8);

        String packageHtml = Files.readString(
                pkg.resolve("package-summary.html"),
                StandardCharsets.UTF_8);

        String classHtml = Files.readString(
                pkg.resolve("Widget.html"),
                StandardCharsets.UTF_8);

        String fallbackHtml = Files.readString(
                fallback, StandardCharsets.UTF_8);

        System.out.println("guideGenerated=" +
                Files.isRegularFile(guide));

        System.out.println("navigationAdded=" +
                html.contains("nav-bar"));

        System.out.println("mainHeadingPresent=" +
                html.contains("Widget usage guide"));

        System.out.println("inlineTagRendered=" +
                (html.contains(
                    "../Widget.html#render(java.lang.String)") &&
                 !html.contains("{@link")));

        System.out.println("outsideMainOmitted=" +
                !html.contains(
                    "ORIGINAL_FOOTER_OUTSIDE_MAIN"));

        System.out.println("bodyFallbackProcessed=" +
                (fallbackHtml.contains(
                    "Fallback body example") &&
                 !fallbackHtml.contains("{@link")));

        System.out.println("svgCopied=" +
                Files.isRegularFile(image));

        System.out.println("privateExcluded=" +
                !Files.exists(excluded));

        System.out.println("packageLinkPresent=" +
                packageHtml.contains("doc-files/guide.html"));

        System.out.println("classLinkPresent=" +
                classHtml.contains("doc-files/guide.html"));
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 -d classes DocFilesOutputCheck.java
```

Chạy **sau** khi sinh tài liệu:

```bash
java -cp classes DocFilesOutputCheck out
```

**Stdout chính xác đã kiểm thử trên JDK 24.0.2:**

```text
guideGenerated=true
navigationAdded=true
mainHeadingPresent=true
inlineTagRendered=true
outsideMainOmitted=true
bodyFallbackProcessed=true
svgCopied=true
privateExcluded=true
packageLinkPresent=true
classLinkPresent=true
```

### 15.1. Các điều kiện kiểm tra có ý nghĩa gì?

- **`guideGenerated`**: file `out/com/acme/docs/doc-files/guide.html` tồn tại.
- **`navigationAdded`**: trang có markup navigation theo cấu trúc doclet được thử.
- **`mainHeadingPresent`**: nội dung hướng dẫn đúng được render.
- **`inlineTagRendered`**: symbol reference đã được resolve thành link và không còn raw `{@link`.
- **`outsideMainOmitted`**: nội dung ngoài `<main>` không bị chép nhầm vào tài liệu.
- **`bodyFallbackProcessed`**: trang HTML thiếu `<main>` vẫn xử lý được từ `<body>`.
- **`svgCopied`**: ảnh tham chiếu có ở output.
- **`privateExcluded`**: thư mục nội bộ đã được loại trừ.
- **`packageLinkPresent`**: trang package có link tới guide.
- **`classLinkPresent`**: trang class có link tới guide.

### 15.2. Test output HTML cần chống “brittle assertions”

Chuỗi `nav-bar` và URL fragment `render(java.lang.String)` là điều quan sát trên **OpenJDK 24.0.2**, không phải contract HTML nội bộ bất biến của mọi JDK. Khi nâng cấp Javadoc, có thể cần cập nhật verifier để kiểm tra **hành vi** thay vì chỉ string literal.

Ví dụ test mạnh hơn trong CI thực tế có thể:
- Parse HTML DOM bằng HTML parser thích hợp;
- Kiểm tra href targets tồn tại và anchor hợp lệ;
- Kiểm tra status code khi publish docs;
- Kiểm tra accessibility;
- Phát hiện broken links của nội bộ dự án;
- So sánh những nội dung quan trọng thay vì CSS classes của Javadoc.

Chương trình demo cố ý đơn giản để có kết quả quyết định và dễ học.

## 16. Những khác biệt giữa `doc-files` và các nguồn tài liệu khác

| Cơ chế | Đặt ở đâu? | Dùng cho việc gì? |
|---|---|---|
| `/** ... */` | Ngay trước class/method/field | Contract của API declaration |
| `package-info.java` | Trong source package directory | Mô tả package và những links quan trọng |
| `doc-files/*.html` | Dưới source package directory | Bài HTML độc lập, hướng dẫn chuyên sâu, hình, bảng |
| `doc-files/*.md` | Dưới package directory trên JDK hỗ trợ Markdown | Bài Markdown độc lập được xử lý thành HTML |
| `snippet-files` | Theo package hoặc snippet search path | Nguồn code cho `{@snippet}`, không phải trang HTML hướng dẫn |
| `README.md` ở repository root | Root của repository | Hướng dẫn dự án cho Git hosting/tooling, không tự động vào API docs |
| `site docs` hoặc tài liệu web ngoài | Hệ thống docs riêng | Hướng dẫn toàn sản phẩm, versioning/site search chuyên biệt |

### 16.1. `package.html` vẫn gặp trong dự án cũ nhưng không phải cách ưu tiên

Oracle JDK 25 specification mô tả `package.html` **để tương thích lịch sử**, đồng thời khuyến nghị `package-info.java` cho package descriptions mới.

Với tài liệu dài, dùng `doc-files/guide.html` và từ `package-info.java` đặt link tới đó. Không dồn bài 10 trang vào một package comment.

### 16.2. Markdown trong `doc-files` là tính năng mới hơn Java 10

**JEP 467** đưa Markdown documentation comments vào **JDK 23+**. Oracle JDK 25 specification cho phép các tệp `doc-files/*.md` được xử lý như Markdown docs, bao gồm tags và links tương ứng.

Điều này **không thay thế trọng tâm** của bài: **HTML trong `doc-files` đã được trang trí và xử lý bởi Javadoc từ JDK 10**, trong khi Markdown standalone support là một bổ sung về sau. Nếu dự án chạy JDK 17/21, không viết hướng dẫn yêu cầu tool tự xử lý `*.md` như JDK 25 mà chưa xác minh version.

### 16.3. `snippet-files` phục vụ code snippets, không phải hướng dẫn HTML

Java 18+ có `{@snippet}` (JEP 413) và `--snippet-path` dành cho external snippets. `snippet-files` được Standard Doclet tìm theo một cơ chế riêng.

Không nhầm:
- `doc-files/guide.html`: một trang HTML độc lập;
- `snippet-files/Sample.java`: nguồn code được hiển thị bằng `{@snippet}` trong trang API.

Có thể liên kết hai hệ thống trong một tài liệu thực tế, nhưng file/command behavior khác nhau.

## 17. Quy tắc viết HTML5 đúng cho Javadoc

### 17.1. Cấu trúc trang

Nên có:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Guide</title>
</head>
<body>
<main>
  <h1>Guide</h1>
  <p>Readable HTML5 content.</p>
</main>
</body>
</html>
```

Thực hiện:
- `<h1>` là heading của standalone page;
- `<h2>`, `<h3>` theo thứ tự logic, không nhảy cấp vô cớ;
- Tables có headers phù hợp;
- Images có `alt`;
- Links có văn bản mô tả mục tiêu.

### 17.2. Tránh IDs xung đột

Sử dụng ids như `processing-steps`, `error-cases`, `configuration-details` thay vì các tên một từ có thể trùng với identifiers Java hoặc những vị trí mà Standard Doclet sinh ra.

Đảm bảo mỗi `id` là duy nhất trong trang được render. Khi đổi id, cập nhật links trỏ tới fragment ấy.

### 17.3. Mã ví dụ trong HTML

Dùng semantic elements:

```html
<pre><code class="language-java">int n = 42;</code></pre>
```

Không đặt ký tự `<` hoặc `&` thô trong nội dung HTML nếu chúng cần được escape; dùng `&lt;`, `&amp;` hoặc cách được Javadoc hỗ trợ.

Ví dụ:

```html
<pre><code class="language-java">List&lt;String&gt; names;</code></pre>
```

Với ví dụ nhiều dòng phức tạp, cân nhắc `{@snippet}` trên JDK có hỗ trợ hoặc dẫn người đọc tới source code được kiểm thử. Không giấu code sample chỉ trong screenshot.

### 17.4. HTML validator và DocLint

`-Xdoclint:all` giúp tìm các lỗi HTML/reference/accessibility phổ biến nhưng **không phải bộ kiểm tra HTML đầy đủ**. Oracle Javadoc Guide nhấn mạnh doclet không tự sửa mọi HTML errors; output sai có thể không đạt chuẩn.

Vì vậy:
- Xem kết quả Javadoc warnings/errors;
- Dùng HTML validator nếu cần;
- Kiểm tra generated site thật;
- Test broken links và accessibility;
- Xem thử tài liệu trên màn hình nhỏ.

## 18. Character encoding và tiếng Việt

Nếu tài liệu viết tiếng Việt, nhất quán UTF-8 từ:
- Editor và repository files;
- Java source Javadoc comments;
- Input `guide.html` và `fallback.html`;
- Javadoc output HTML;
- HTTP server khi publish.

Lệnh minh họa:

```bash
javadoc -encoding UTF-8 -charset UTF-8 -d out -sourcepath src com.acme.docs
```

Trong HTML source nên có:

```html
<meta charset="utf-8">
```

Nếu thấy dấu tiếng Việt lỗi như `Ã¡` hoặc ký tự thay thế:
1. Kiểm tra file input thực sự lưu UTF-8;
2. Kiểm tra option `-encoding`;
3. Kiểm tra output HTML `-charset`;
4. Kiểm tra web server headers và browser;
5. Không “sửa” bằng cách chuyển toàn bộ tài liệu sang một encoding cũ nếu hệ thống đã dùng UTF-8.

**Phân biệt `-encoding`** (đọc input) với **`-charset`** (khai báo encoding output theo tool docs).

## 19. Tài nguyên HTML phải được liên kết và công bố có chủ đích

### 19.1. Không có navigation link tự động cho từng tài nguyên

Một tệp `doc-files/extra.html` được sinh ra không đồng nghĩa Javadoc tự đặt nó trong thanh menu API chính. Trong source class/package cần đặt links:

```java
/**
 * More detail: <a href="doc-files/guide.html">usage guide</a>.
 */
public final class Example {
}
```

Đây là **mảnh code class minh họa**, không phải phần của `Widget.java` đã kiểm thử. Dùng links có mô tả để người đọc khám phá được trang.

### 19.2. Không dùng đường dẫn phụ thuộc máy build

Không xuất bản links tới `file:///C:/...` hoặc đường dẫn tuyệt đối `/home/user/...`. Chúng chỉ hoạt động trên một máy build cụ thể.

Trong tài liệu publish từ `out/` lên web, kiểm tra URL relative sau khi upload; một reverse proxy đổi base path có thể làm assets hoặc links absolute sai.

### 19.3. Không tự tin vào external references

Nếu HTML guide dẫn tới tài liệu Java SE ngoài bằng `https://...`:
- Dùng đường dẫn HTTPS chính thức/đáng tin khi có thể;
- Không nhúng nội dung remote nguy hiểm;
- Có chiến lược chống broken external links;
- Không tải assets từ domain không tin cậy trong tài liệu API nếu có risk về tracking/CSP.

Nếu muốn tạo Java API link với `{@link java.util.List}`, Javadoc có các options `-link` và platform links; cần xem behavior của JDK/doclet đang dùng để bảo đảm link đúng.

## 20. Bảo mật: `doc-files` là nội dung được publish

Một lỗi có thể nguy hiểm là copy nhầm các file nội bộ vào generated documentation:

```text
doc-files/
  guide.html
  api-example.svg
  production-credentials.txt   <-- tuyệt đối không
  private-key.pem              <-- tuyệt đối không
  internal-incident-report.md  <-- không đưa vào site công khai
```

**Không** lưu secrets/PII/tài liệu private vào `doc-files` của tài liệu public. Dù có exclude option, nên **không để asset nguy hiểm trong input tree** ngay từ đầu.

### 20.1. JavaScript trong documentation comments

Javadoc 25 có option `--allow-script-in-comments` để cho phép scripts trong documentation comments. **Không bật option này cho tài liệu chứa input từ nguồn không tin cậy**.

Rủi ro:
- Cross-site scripting (XSS) trong documentation website;
- External scripts có thể theo dõi người đọc;
- Giảm độ an toàn của các trang API được nhiều developer mở;
- Phá Content Security Policy của website publish.

**Khuyến nghị:** dùng HTML5 tĩnh, CSS được kiểm soát và liên kết nội bộ, không yêu cầu chạy script tùy ý trong `doc-files`.

### 20.2. SVG cũng là một tài nguyên cần review

SVG là XML và có thể chứa nội dung phức tạp/active tùy cách sử dụng và browser context. Chỉ đưa lên site SVG từ nguồn đáng tin, kiểm tra trước khi publish, không coi file ảnh là an toàn tuyệt đối vì có đuôi `.svg`.

### 20.3. Giới hạn file có quyền chỉnh sửa

Trên repository:
- Review thay đổi `*.html`, `*.svg` và CSS như source code;
- Yêu cầu code owners nếu docs public có phạm vi rộng;
- Không để pipeline lấy arbitrary HTML từ issue descriptions hoặc CMS không kiểm soát mà đưa thẳng vào doclet;
- Bảo vệ deployment permissions của website tài liệu;
- Có CI kiểm tra links/HTML/accessibility.

## 21. Build bằng Maven hoặc Gradle: cùng nguyên lý source tree

Với Maven standard layout:

```text
src/main/java/com/acme/docs/Widget.java
src/main/java/com/acme/docs/package-info.java
src/main/java/com/acme/docs/doc-files/guide.html
src/main/java/com/acme/docs/doc-files/assets/flow.svg
```

Các plugins tạo Javadoc thường dùng source directory của Java project. **Cần xác minh** plugin đã bao gồm `doc-files` và options mong muốn; không mặc định mọi plugin version hoặc multi-module build giống nhau.

Với Gradle:
- Javadoc task thường tham chiếu các Java source files/source sets;
- Đặt `doc-files` dưới package source tree phù hợp;
- Xem task options/doctitle/doclet arguments khi cần;
- Chạy task và kiểm tra **output directory thực tế**.

Không cần tự viết một custom compiler plugin chỉ để hỗ trợ `doc-files`. Dùng Standard Doclet khi nó đáp ứng yêu cầu.

### 21.1. Multi-module builds

Trong JPMS/module-oriented source layout, có thể có `doc-files` liên quan package/module. JDK 25 specification nói documentation từ `doc-files` có thể thuộc module hoặc package directory. Nhưng **sơ đồ và lệnh trong bài** cố ý dùng package `com.acme.docs` đơn giản.

Nếu muốn document nhiều modules, dùng đúng `--module-source-path`, `--module-path` và danh sách modules theo build, sau đó kiểm tra output paths. Không lấy một path của ví dụ single-package rồi áp cứng cho tất cả module structures.

### 21.2. JAR chứa compiled classes khác Javadoc artifact

Thông thường:
- `.jar` của library chứa compiled classes/resources;
- Javadoc artifact có thể xuất bản riêng hoặc thành `-javadoc.jar`;
- `doc-files/guide.html` cần nằm trong **Javadoc output** khi build/publish tài liệu.

Không suy rằng app runtime `ClassLoader.getResource("doc-files/guide.html")` sẽ đọc được file chỉ vì Javadoc đã xuất HTML. Đó là **hai loại artifact** và quy trình đóng gói khác nhau.

## 22. Các lỗi phổ biến và cách khắc phục

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra/khắc phục |
|---|---|---|
| `guide.html` không có trong output | Đặt sai package `doc-files` hoặc không document package | Kiểm tra source path/package và `-d` output |
| Trang có file nhưng không tìm thấy qua menu | Chưa đặt link trong class/package comments | Thêm `href="doc-files/guide.html"` |
| Link từ `guide.html` về class trả 404 | Dùng `Widget.html` thay vì `../Widget.html` | So cấu trúc output thực tế |
| Ảnh không tải | Sai relative `assets/flow.svg` hoặc không deep-copy subdir | Kiểm tra `-docfilessubdirs` và file output |
| `{@link ...}` bị lỗi/không resolve | Reference không đúng package/signature | Dùng fully qualified name, xem DocLint |
| `{@link ...}` còn nguyên | HTML không được Standard Doclet xử lý theo điều kiện hiện tại | Kiểm tra JDK/doclet và vị trí `<main>/<body>` |
| Trang bị duplicated header/footer | Tự nhúng layout trong HTML input | Để Standard Doclet tạo vỏ và nav |
| Nội dung ngoài `<main>` biến mất | Spec ưu tiên nội dung `<main>` | Đặt nội dung cần hiển thị vào `<main>` |
| CSS giống phiên bản cũ bị lệch | Phụ thuộc DOM class của Standard Doclet | Dùng CSS được hỗ trợ, QA khi đổi JDK |
| Tiếng Việt lỗi encoding | Input/output charset không thống nhất | Dùng UTF-8, kiểm tra `-encoding`/`-charset` |
| `private` file bị copy | File nằm trong `doc-files` và chưa exclude | Xóa khỏi publication tree hoặc exclude có kiểm chứng |
| Javadoc chạy nhưng link sai | Không test generated site | Dùng verifier/link checker |
| Đổi JDK khiến snapshot HTML khác | Standard Doclet cập nhật markup/layout | Kiểm thử semantic behavior, không đòi hash y hệt |
| Thêm `-html5` không có hiệu ứng | Trên JDK 25 option là **no-op** | Viết HTML5 đúng, không phụ thuộc flag cũ |
| `package.html` gây workflow cũ khó sửa | Legacy package description style | Dùng `package-info.java` cho tài liệu mới |
| `.md` không được xử lý trên JDK 17 | Markdown docs support được thêm từ JDK 23 | Giữ `.html` cho project phải hỗ trợ JDK 17/21 |
| Có HTML file nhưng một custom doclet không copy | Không dùng Standard Doclet hoặc khác behavior | Đọc documentation của doclet đang dùng |

## 23. Checklist trước khi publish Javadoc

- [ ] `doc-files` nằm đúng dưới source package directory?
- [ ] Package được đưa vào lệnh `javadoc`/build plugin?
- [ ] Trang `*.html` có HTML5 structure hợp lệ?
- [ ] Nội dung cần publish nằm trong `<main>` hoặc `<body>` phù hợp?
- [ ] Standalone page dùng `<h1>`, headings theo thứ tự?
- [ ] IDs có ý nghĩa và đủ tránh trùng lặp?
- [ ] `{@link ...}` trỏ tới Java declaration có thật?
- [ ] Trang được link từ `package-info.java` hoặc API class tương ứng?
- [ ] Relative links dùng đúng `../` và `doc-files/`?
- [ ] Hình có `alt` và tồn tại trong output?
- [ ] Tệp `assets` nằm trong subtree được copy?
- [ ] `-docfilessubdirs`/excluded options phù hợp Javadoc runtime?
- [ ] Không có secrets/private files trong cây tài liệu public?
- [ ] Không bật `--allow-script-in-comments` tùy tiện?
- [ ] Mã ký tự UTF-8 từ source đến output?
- [ ] `javadoc -Xdoclint:all` chạy thành công?
- [ ] Có kiểm tra generated HTML bằng browser/DOM/link test?
- [ ] CI phân biệt lỗi code compile và lỗi documentation build?
- [ ] Khi nâng JDK, có kiểm tra HTML structure và links thực tế?
- [ ] Không dựa vào những options cũ đã no-op/unsupported?
- [ ] Trang vẫn dễ đọc trên mobile, có headings và accessibility?

## 24. Câu hỏi ôn tập và đáp án

**1.** `doc-files` dùng để làm gì trong Javadoc?

**Đáp án:** Chứa tài liệu và tài nguyên bổ sung gắn với package/module, ví dụ HTML hướng dẫn và ảnh được copy/xử lý khi tạo documentation.

**2.** Điều đáng chú ý ở Java 10 liên quan HTML trong `doc-files` là gì?

**Đáp án:** **JDK-8185985** làm Standard Doclet xử lý các trang HTML trong `doc-files` thành trang có Javadoc header/footer/navigation và xử lý các comment tags thích hợp.

**3.** Trong JDK 25, nội dung HTML được lấy từ đâu nếu có `<main>`?

**Đáp án:** Nội dung bên trong `<main>`.

**4.** Nếu file HTML không có `<main>` thì sao?

**Đáp án:** Dùng nội dung của `<body>` theo specification.

**5.** Heading đầu tiên của trang HTML độc lập `doc-files` nên là gì?

**Đáp án:** **`<h1>`**, theo hướng dẫn của Javadoc specification.

**6.** `{@link ...}` có thể được xử lý trong `doc-files/guide.html` không?

**Đáp án:** Có, nếu reference hợp lệ và doclet/JDK hỗ trợ.

**7.** Từ `Widget.html` muốn tới guide, dùng relative URL nào?

**Đáp án:** `doc-files/guide.html`.

**8.** Từ `doc-files/guide.html` quay lại `Widget.html`?

**Đáp án:** `../Widget.html`.

**9.** Vì sao cần `-docfilessubdirs` trong command thử nghiệm?

**Đáp án:** Để xử lý deep copying những assets trong subdirectories như `assets/flow.svg` trên Javadoc được test.

**10.** Có thể exclude một thư mục con của `doc-files` bằng option nào?

**Đáp án:** `-excludedocfilessubdir`, với tên thư mục cần loại trừ.

**11.** Vì sao không nên chứa secrets trong `doc-files` ngay cả khi có exclude option?

**Đáp án:** Vì cây nguồn có thể được copy/publish ngoài ý muốn trong build khác; loại bỏ dữ liệu nhạy cảm khỏi publication tree là tốt nhất.

**12.** `package-info.java` và `doc-files/guide.html` có vai trò giống nhau không?

**Đáp án:** Không. `package-info.java` mô tả package, còn `guide.html` là trang hướng dẫn độc lập được dẫn tới bằng link.

**13.** `-Xdoclint:all` có bảo đảm HTML 100% đạt chuẩn không?

**Đáp án:** Không. Nó kiểm tra các nhóm lỗi phổ biến; vẫn cần browser/HTML/link/accessibility QA.

**14.** JDK 17 có xử lý `doc-files/*.md` như JDK 25 không?

**Đáp án:** Không được suy như vậy. Markdown documentation support là tính năng **JDK 23+**, cần kiểm tra tool đang dùng.

**15.** `snippet-files` dùng cho việc gì?

**Đáp án:** Nguồn external snippets cho `{@snippet}`, khác tài liệu HTML `doc-files`.

**16.** Có cần đưa tất cả trang HTML vào Java runtime JAR không?

**Đáp án:** Không. Javadoc HTML thường là documentation artifact riêng, không phải bytecode runtime.

**17.** Vì sao một asset xuất hiện trên máy build nhưng broken khi publish?

**Đáp án:** Có thể do không copy subtree, path phân biệt hoa/thường, base URL khác hoặc reference tuyệt đối không portable.

**18.** Nếu `javadoc` đổi layout CSS giữa các JDK, có nhất thiết là lỗi không?

**Đáp án:** Không. Kiểm chứng nội dung, links và accessibility, không phụ thuộc internal HTML markup.

**19.** `--allow-script-in-comments` có nên bật để nhúng JavaScript tùy ý không?

**Đáp án:** Không. Chỉ xem xét trong môi trường có review bảo mật và nguồn tài liệu đáng tin; thường không cần script để viết API guide.

**20.** Kết quả nào xác nhận ví dụ trong bài thành công?

**Đáp án:** `javac --release 17` và `javadoc -Xdoclint:all` exit code 0, main in `rendered=doc-files` và chương trình `DocFilesOutputCheck` in 10 dòng kết thúc bằng `true`.

## 25. Bài tập thực hành nâng cao

### Bài tập 1: trang HTML mới

Tạo `doc-files/errors.html` có:
- `<main>` và `<h1>`;
- Mục `<h2 id="invalid-input">`;
- Một `{@link com.acme.docs.Widget#render(String)}`;
- Một link quay về `../Widget.html`.

Cập nhật `package-info.java` thêm link tới `doc-files/errors.html` và chạy `javadoc`. Kiểm tra file có trong output và không có raw Javadoc tag.

### Bài tập 2: link checker

Viết một Java program dùng `Files.readString`/HTML parser phù hợp để tìm links `doc-files/*.html` trong `Widget.html` và `package-summary.html`. Xác nhận link target tồn tại trong docs output.

Gợi ý: chương trình `DocFilesOutputCheck` có sẵn là bước đầu. Nên mở rộng parser thay vì dùng chuỗi `contains` cho ứng dụng lớn.

### Bài tập 3: kiểm thử fallback

Bỏ `<main>` khỏi một bản sao `guide.html` nhưng giữ `<body>`. Sinh docs lại và đối chiếu nội dung theo specification. Không bỏ `<body>` rồi tự giả định Javadoc có thể tìm main content.

### Bài tập 4: exclude asset

Tạo một file giả `doc-files/private-not-for-publication/example.txt` và chạy docs với/không với `-excludedocfilessubdir` trong **test workspace**. So sánh output. Sau đó **loại hẳn file private khỏi source documentation tree**, thay vì coi exclude option là hàng rào bảo mật đủ mạnh.

### Bài tập 5: nâng toolchain

Chạy dự án với hai JDK versions có hỗ trợ. Kiểm tra:
- `javadoc --version`;
- Số lượng trang được tạo;
- Link methods trong `{@link ...}`;
- Hình có được copy;
- Accessibility warnings;
- Thay đổi DOM/css mà chương trình test có thể phụ thuộc.

Đừng chỉ diff byte-to-byte toàn bộ generated HTML rồi gán mọi thay đổi là regression.

## 26. Nguồn tài liệu chính thức

- [Oracle JDK 10 Release Notes — HTML Files in doc-files Subdirectories Wrapped with Standard javadoc Decorations (JDK-8185985)](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): mốc Java 10 bổ sung standard page wrapping và xử lý Javadoc comment tags trong HTML.
- [Oracle JDK 25 — JavaDoc Documentation Comment Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): `doc-files/*.{html,md}`, `<main>`/`<body>` extraction, HTML5 và heading guidance.
- [Oracle JDK 25 — The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): `-d`, `-sourcepath`, `-docfilessubdirs`, `-excludedocfilessubdir`, `-encoding`, `-charset`, `-Xdoclint`, `--allow-script-in-comments`.
- [Oracle JDK 25 — JavaDoc Tool Guide](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-tool.html): Standard Doclet, HTML support, DocLint và giới hạn sửa lỗi HTML.
- [Oracle JDK 23 — Markdown in Documentation Comments](https://docs.oracle.com/en/java/javase/23/javadoc/using-markdown-documentation-comments.html): Markdown docs và file `doc-files/*.md` được hỗ trợ từ JDK 23.
- [OpenJDK JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): bối cảnh Markdown bổ sung, phân biệt với HTML doc-files đã có từ Java 10.
- [Oracle JDK 25 — Snippets](https://docs.oracle.com/en/java/javase/25/javadoc/snippets.html): `{@snippet}` và external snippets; không nhầm với HTML pages.
- [JDK 25 — StandardDoclet Java API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.javadoc/jdk/javadoc/doclet/StandardDoclet.html): official Standard Doclet tạo HTML documentation.

**Ghi nhớ cuối bài:** `doc-files` là nơi phù hợp để đặt **HTML documentation và assets của một Java package**. Kể từ cải tiến của **Java 10 (JDK-8185985)**, Standard Doclet có thể xử lý các trang HTML này thành **trang Javadoc có navigation/header/footer**, đồng thời resolve các comment tags thích hợp. Trên JDK hiện đại, hãy đặt nội dung vào **`<main>`** (hoặc `<body>` nếu không có `<main>`), dùng `<h1>`, links tương đối đúng, `-Xdoclint:all`, kiểm tra assets và loại bỏ nội dung private. **Luôn xác minh generated output thực tế**, không chỉ kiểm tra rằng command `javadoc` đã chạy.