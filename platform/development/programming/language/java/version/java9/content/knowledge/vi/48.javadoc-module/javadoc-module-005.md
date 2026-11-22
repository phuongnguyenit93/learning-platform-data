# Nội dung HTML hợp lệ trong phần chú thích Javadoc mô-đun (Java 9+)

## 1. Vì sao cần HTML trong Javadoc?

Khi viết Java module bằng JPMS (`module-info.java`), ta không chỉ khai báo `requires`, `exports`, `opens`, `uses` và `provides` mà còn có thể **tài liệu hóa mục đích, cách sử dụng, giới hạn và quan hệ dịch vụ của mô-đun**. Công cụ `javadoc` đọc chú thích tài liệu ngay trước khai báo `module` rồi tạo trang `module-summary.html` trong bộ HTML tài liệu API.

Ở cú pháp Javadoc truyền thống, chú thích bắt đầu bằng `/**` và kết thúc bằng `*/`. Phần mô tả có thể chứa **HTML5 hợp lệ**, ví dụ `<p>`, `<h2>`, `<ul>`, `<li>`, `<pre>`, `<table>`, liên kết và các thẻ Javadoc `{@code ...}`, `{@link ...}`. Những API/cách viết này **vẫn được hỗ trợ trong JDK hiện hành**, kể cả Java 17+, không phải một kỹ thuật lỗi thời.

Vì Javadoc tạo **cả trang HTML bao quanh** mô tả, người viết chú thích chỉ cung cấp **đoạn nội dung HTML phù hợp với vị trí chèn**, không tự tạo cấu trúc trang `<html><head><body>` bên trong `/** ... */`. Viết đúng cấu trúc giúp tài liệu dễ đọc, dễ truy cập bằng trình đọc màn hình và ít cảnh báo `doclint`.

### Ví dụ tối thiểu

Trong `src/m.docs/module-info.java`:

```java
/**
 * Mô-đun cung cấp API lời chào.
 *
 * <p>Dùng {@link demo.api.Greeter} để lấy lời chào.</p>
 *
 * <h2 id="module-usage">Hướng dẫn</h2>
 * <ul>
 *   <li>Nhập {@code "vi"} để lấy tiếng Việt.</li>
 *   <li>Nhập mã khác để lấy giá trị mặc định.</li>
 * </ul>
 *
 * @since 1.0
 */
module m.docs {
    exports demo.api;
}
```

Mô tả đầu tiên là **summary sentence**; `<p>` tạo đoạn mới; `<h2>` tạo đề mục; `<ul><li>` tạo danh sách; `{@link demo.api.Greeter}` tạo liên kết đến một kiểu Java. Mệnh đề `@since 1.0` là **block tag Javadoc**, không phải thẻ HTML.

## 2. Chú thích nào được Javadoc đọc?

Công cụ chuẩn nhận chú thích tài liệu **ngay trước khai báo** module, package, class/interface, constructor, method hoặc field. Chú thích văn bản thông thường `// ...` hoặc `/* ... */` **không thay thế được** `/** ... */` khi muốn tạo Javadoc theo cách truyền thống.

| Vị trí | Tệp/khai báo | Vai trò |
| --- | --- | --- |
| Mô-đun | `module-info.java` trước `module x.y { ... }` | Tạo phần mô tả của trang mô-đun, giải thích trách nhiệm, API, dịch vụ. |
| Gói | `package-info.java` trước `package x.y;` | Tài liệu cho package; có thể chứa HTML và liên kết Javadoc. |
| Kiểu công khai | Trước `public class`, `interface`, `record`, ... | Mô tả API, cách sử dụng, các bất biến. |
| Thành viên | Trước method/constructor/field | Mô tả contract, tham số, giá trị trả về, ngoại lệ. |
| Tài liệu bổ sung | `doc-files/*.html` trong cây nguồn package/module | Trang bổ sung, phục vụ giải thích dài và liên kết từ Javadoc. |

Ví dụ đúng về vị trí:

```java
/**
 * Mô-đun cung cấp các phép biến đổi văn bản.
 *
 * <p>Các API được xuất qua {@code exports}.</p>
 */
module example.text {
    exports example.text.api;
}
```

Chú thích được gắn trực tiếp với **khai báo `module`**. Nếu đặt chú thích ở chỗ khác hoặc có một chú thích tài liệu khác gần khai báo hơn, phần Javadoc muốn viết có thể không được dùng.

**Quan trọng:** với module, các chỉ thị `exports`/`requires`/`uses`/`provides` vẫn phải viết bằng **cú pháp JPMS bên trong `module { ... }`**. Ghi chữ HTML `<p>Module exports ...</p>` chỉ tạo tài liệu, **không** thay đổi quyền truy cập hoặc dependency khi biên dịch.

## 3. Tập thẻ HTML5 thường dùng và cách dùng đúng

Trong chú thích Javadoc truyền thống, nội dung HTML nên tuân theo **HTML5** và tương thích với cấu trúc trang mà standard doclet tạo ra.

| Mục đích | Thẻ phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Đoạn văn | `<p>...</p>` | Chia các ý rõ ràng; không chỉ chèn dòng trống trong mã nguồn rồi mong HTML tự tạo đoạn. |
| Đề mục | `<h2>...</h2>`, `<h3>...</h3>` | Trong mô tả module/package/type, **bắt đầu bằng h2**, sau đó h3 khi cần. |
| Nhấn mạnh | `<em>...</em>`, `<strong>...</strong>` | Dùng theo ý nghĩa nội dung; không dùng chỉ để trang trí. |
| Danh sách không thứ tự | `<ul><li>...</li></ul>` | Mỗi mục có `<li>`; đóng/mở thẻ đúng cấu trúc. |
| Danh sách có thứ tự | `<ol><li>...</li></ol>` | Dành cho các bước theo trình tự. |
| Thuật ngữ/định nghĩa | `<dl><dt>...</dt><dd>...</dd></dl>` | Hữu ích khi giải thích từ vựng công khai của module. |
| Mã ngắn | `<code>...</code>` hoặc `{@code ...}` | Ưu tiên `{@code ...}` để không phải escape dấu `<` trong mã Java. |
| Mã nhiều dòng | `<pre>{@code ... }</pre>` | `<pre>` giữ dòng/indent, `{@code}` tránh hiểu nhầm ký tự mã thành HTML. |
| Bảng dữ liệu | `<table>`, `<caption>`, `<tr>`, `<th>`, `<td>` | Bảng có caption và header giúp truy cập/đọc tốt hơn. |
| Liên kết web | `<a href="https://...">...</a>` | Dùng URL đáng tin cậy, có text mô tả; không làm link rỗng. |
| Liên kết API Java | `{@link ...}` / `{@linkplain ...}` | Ưu tiên tag Javadoc vì được kiểm tra kiểu/thành viên và tạo liên kết phù hợp. |

### Cấp heading không phải tùy ý

Trang HTML do Javadoc sinh đã có các đề mục điều hướng. Theo đặc tả standard doclet hiện nay:

- **Tài liệu ở cấp module, package hoặc type:** bắt đầu với `<h2>`; nếu có đề mục con dùng `<h3>` rồi `<h4>` theo thứ bậc.
- **Chú thích cho method/constructor/field:** nếu cần heading trong phần mô tả, bắt đầu với `<h4>`.
- **Trang HTML độc lập trong `doc-files`:** heading bắt đầu với `<h1>`.
- **ID do người viết tự khai báo:** nên chứa dấu gạch nối như `id="module-usage"` để tránh xung đột tên neo do Javadoc tự sinh.

Ví dụ đúng ở cấp module:

```java
/**
 * <p>Thư viện xử lý hóa đơn.</p>
 *
 * <h2 id="invoice-usage">Sử dụng</h2>
 * <p>Gọi các API công khai được mô-đun xuất.</p>
 *
 * <h3 id="invoice-input">Định dạng dữ liệu đầu vào</h3>
 * <ul>
 *   <li>Mã hóa UTF-8.</li>
 *   <li>Mã hóa dữ liệu đặc biệt trước khi gửi.</li>
 * </ul>
 */
module example.invoice {
    exports example.invoice.api;
}
```

Đây là đoạn minh họa cho một module giả định có package `example.invoice.api`; để biên dịch độc lập cần có lớp/package tương ứng. Chú ý: vì mã ví dụ dùng tiếng Việt, nên các file Java nên lưu **UTF-8** và chạy `javac -encoding UTF-8`/`javadoc -encoding UTF-8`.

## 4. Escaping ký tự: lỗi phổ biến nhất trong Javadoc HTML

Trong nội dung HTML, ba ký tự có ý nghĩa đặc biệt cần xem xét là:

| Muốn hiển thị | Trong text HTML viết | Vì sao |
| --- | --- | --- |
| `<` | `&lt;` | Tránh bị hiểu là bắt đầu tên thẻ. |
| `>` | `&gt;` | Tránh nhập nhằng khi đặt trong biểu thức/văn bản HTML. |
| `&` | `&amp;` | Tránh trình phân tích cú pháp hiểu là đầu một entity. |
| `"` trong thuộc tính HTML được bao bởi `"` | `&quot;` | Tránh đóng giá trị attribute sớm. |

Ví dụ sai:

```java
/**
 * Điều kiện a < b && b > c phải đúng.
 */
```

Dấu `<` có thể được đọc như cú pháp HTML, khiến phần mô tả sai hoặc `doclint` cảnh báo. Có ba cách phổ biến để viết đúng:

**Cách 1 — HTML entity**, phù hợp cho văn bản thường:

```java
/**
 * Điều kiện a &lt; b &amp;&amp; b &gt; c phải đúng.
 */
```

**Cách 2 — `{@code ...}`**, phù hợp cho biểu thức/mã (khuyến nghị):

```java
/**
 * Kiểm tra biểu thức {@code a < b && b > c}.
 */
```

**Cách 3 — `{@literal ...}`**, hiển thị ký tự như văn bản thuần:

```java
/**
 * Định dạng biểu thức: {@literal <item> & <value>}.
 */
```

`{@code}` hiển thị ở kiểu chữ code, trong khi `{@literal}` không tự tạo định dạng code. **Bên trong hai tag này, chuỗi như `<item>` được hiển thị nguyên văn, không được diễn giải là tag HTML**. Ngược lại, viết `<code>List<String></code>` trực tiếp mà không escape dấu `<` sẽ dễ gây lỗi; dùng `{@code List<String>}` ngắn và rõ hơn.

Nếu muốn **nói về chuỗi mang ý nghĩa HTML**, hãy hiển thị nó như dữ liệu:

```java
/**
 * Mã HTML ví dụ: {@code <strong>Xin chào</strong>}.
 */
```

Nếu muốn **HTML thật được render đậm**, viết:

```java
/**
 * Chú ý: <strong>Không lưu mật khẩu trong source code.</strong>
 */
```

Hai đoạn trên mang ý nghĩa **khác nhau**: một đoạn in ký tự `<strong>`, đoạn kia áp dụng định dạng `<strong>`.

### Tránh hai lỗi không liên quan HTML nhưng xuất hiện trong Javadoc

- Dấu `@` ở đầu dòng có thể được phân tích như **block tag** `@since`, `@see`, `@param`... Nếu cần in một dòng bắt đầu bằng `@` như văn bản, dùng entity `&#064;` hoặc dạng diễn đạt khác.
- Chuỗi `*/` **kết thúc chú thích Java** bất kể đó là ví dụ nằm bên trong `<pre>` hay không. Với ví dụ có `*/`, chuyển sang snippet/tệp nguồn riêng, hoặc viết cách khác; không chèn nguyên chuỗi gây đóng comment vào `/** ... */`.

## 5. Phân biệt thẻ Javadoc và thẻ HTML

Cả hai có thể cùng xuất hiện trong phần mô tả, nhưng chúng được xử lý khác nhau.

| Cú pháp | Bên xử lý | Ví dụ |
| --- | --- | --- |
| `<p>`, `<ul>`, `<table>` | HTML của kết quả Javadoc | Tạo đoạn, danh sách, bảng. |
| `{@code text}` | Javadoc inline tag | Hiển thị ký tự literal có định dạng code. |
| `{@literal text}` | Javadoc inline tag | Hiển thị văn bản literal. |
| `{@link demo.api.Greeter}` | Javadoc inline tag | Liên kết tới một phần tử API. |
| `{@linkplain demo.api.Greeter mô tả}` | Javadoc inline tag | Như `link`, nhưng nhãn hiển thị dạng chữ thường. |
| `@since 1.0`, `@see ...` | Javadoc block tag | Tạo metadata hoặc mục See Also. |
| `@uses T`, `@provides T` | Javadoc block tag dành cho **module** | Mô tả dịch vụ JPMS đã khai báo trong module. |

Cú pháp `{@link ...}` có lợi hơn tự lắp `<a href=".../Greeter.html">` vì tool có thể kiểm tra tính hợp lệ của Java reference và tính đường dẫn đến trang đích. Đối với liên kết tới tài liệu web ngoài, dùng `<a href="https://example.org/spec">tài liệu chuẩn</a>`; text của link nên nêu đích đến rõ ràng.

### Block tag phải nằm sau mô tả chính

Phần mô tả Javadoc bắt đầu từ đầu comment đến trước block tag đầu tiên. Sau khi bắt đầu `@since`, `@see` hoặc `@uses`, **không tiếp tục viết đoạn mô tả chính như thể vẫn đang ở phần mở đầu**.

Cách đúng:

```java
/**
 * Module tính phí vận chuyển.
 *
 * <p>Chứa các API được công bố để tính phí.</p>
 *
 * @since 1.0
 * @see java.lang.Module
 */
module example.shipping {
    exports example.shipping.api;
}
```

Đây là ví dụ cấu trúc; package `example.shipping.api` cần tồn tại khi biên dịch thật. Các block tag `@param`, `@return`, `@throws` dùng cho **method/constructor phù hợp**, không đặt chúng ở mô tả `module-info.java`. Với module, `@uses` và `@provides` được phép khi tài liệu hóa dịch vụ; mỗi tag phải phù hợp với `uses`/`provides` thực tế của module.

Ví dụ minh họa **một mô-đun sử dụng dịch vụ**:

```java
/**
 * Dùng bộ nạp bản dịch do các module khác cung cấp.
 *
 * <p>Tra cứu bản dịch qua {@link java.util.ServiceLoader}.</p>
 *
 * @uses java.util.spi.ResourceBundleProvider
 *     Provider cung cấp ResourceBundle cho ứng dụng.
 */
module example.client {
    uses java.util.spi.ResourceBundleProvider;
}
```

Đây là ví dụ về mặt **cú pháp tag và chỉ thị module**; ứng dụng thật cần kiểm tra đúng service interface/phạm vi sử dụng theo API cụ thể. Javadoc `@uses` bổ sung mô tả ở tài liệu, còn chỉ thị `uses` mới là lời khai báo dịch vụ khi chạy. Không nhầm hai dòng này với nhau.

## 6. Ví dụ hoàn chỉnh: tạo Javadoc HTML từ named module

Mô-đun mẫu tên `m.docs` cung cấp API `demo.api.Greeter`. Ví dụ sử dụng:

- `<p>`, `<h2>`, `<ul><li>` trong `module-info.java`.
- `{@link}`, `{@code}`, `{@literal}`, entity `&lt;`.
- `<pre>{@code ...}</pre>` để trình bày ví dụ code nhiều dòng trong Javadoc type.
- Bảng `<table>` có `<caption>` và `<th scope="col">` để thể hiện dữ liệu rõ ràng.
- `@param` và `@return` trong mô tả method; `@since` trong mô tả module.

**Cấu trúc thư mục:**

```text
src/
└── m.docs/
    ├── module-info.java
    └── demo/
        └── api/
            └── Greeter.java
```

### 6.1. File `src/m.docs/module-info.java`

```java
/**
 * Module minh họa Javadoc HTML5.
 *
 * <p>Xem {@link demo.api.Greeter}.</p>
 * <h2 id="usage-guide">Cách sử dụng</h2>
 * <ul><li>Nhập {@code "vi"} để lấy lời chào.</li></ul>
 * <p>Điều kiện: {@literal 2 < 5 && 3 > 1}.</p>
 * @since 1.0
 */
module m.docs {
    exports demo.api;
}
```

Ở đoạn này, `{@literal 2 < 5 && 3 > 1}` tạo text biểu thức mà không làm parser HTML hiểu nhầm ký tự. `@since` xuất hiện sau phần mô tả; heading bắt đầu ở `h2`; giá trị `id="usage-guide"` có dấu `-` để tránh trùng tên neo do doclet sinh.

### 6.2. File `src/m.docs/demo/api/Greeter.java`

```java
package demo.api;

/**
 * API minh họa.
 *
 * <h2 id="examples-list">Ví dụ</h2>
 * <pre>{@code
 * System.out.println(Greeter.greet("vi"));
 * }</pre>
 * <table>
 * <caption>Kết quả</caption>
 * <tr><th scope="col">Đầu vào</th><th scope="col">Đầu ra</th></tr>
 * <tr><td>vi</td><td>Xin chào</td></tr>
 * </table>
 */
public final class Greeter {
    private Greeter() {}

    /**
     * Trả về lời chào.
     *
     * @param code mã ngôn ngữ
     * @return lời chào
     */
    public static String greet(String code) {
        return "vi".equals(code) ? "Xin chào" : "Hello";
    }

    /**
     * In lời chào.
     *
     * @param args đối số chưa dùng
     */
    public static void main(String[] args) {
        System.out.println(greet("vi"));
    }
}
```

Javadoc của lớp bắt đầu heading ở `<h2>`; đoạn code nhiều dòng dùng `<pre>{@code ...}</pre>`. Bảng dùng caption và header semantic thay vì giả định rằng người đọc tự đoán mỗi cột có nghĩa gì. `@param` chỉ dành cho tham số thực của method; thêm `@return` cho method có giá trị trả về.

### 6.3. Biên dịch và chạy Java 17+

Trong thư mục chứa `src`, dùng Bash/Zsh:

```bash
mkdir -p mods/m.docs

javac -encoding UTF-8 --release 17 -d mods/m.docs \
  src/m.docs/module-info.java \
  src/m.docs/demo/api/Greeter.java

java --module-path mods --module m.docs/demo.api.Greeter
```

**Stdout chính xác:**

```text
Xin chào
```

Phần thực thi Java không cần biết nội dung `javadoc`: HTML/comment chỉ phục vụ người đọc và công cụ tài liệu, không tạo logic runtime.

### 6.4. Sinh Javadoc và kiểm tra HTML

```bash
javadoc -quiet -Xdoclint:all \
  -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 \
  --module-source-path src \
  -d docs \
  --module m.docs
```

Nếu không có lỗi, đầu ra bao gồm (tùy giao diện phiên bản JDK):

```text
docs/
└── m.docs/
    ├── module-summary.html
    └── demo/
        └── api/
            └── Greeter.html
```

Mở `docs/m.docs/module-summary.html` bằng trình duyệt để xem mô tả module và link sang API. Mở `docs/m.docs/demo/api/Greeter.html` để kiểm tra bảng, caption, đoạn code và `@param`/`@return`. Tùy bản JDK, Javadoc sinh thêm tài nguyên HTML/CSS/JS/index ở thư mục `docs`; sơ đồ trên chỉ trình bày **hai trang quan trọng**, không phải danh sách toàn bộ file đầu ra.

Các tham số:

| Tùy chọn | Tác dụng |
| --- | --- |
| `--module-source-path src` | Cho Javadoc biết cây source chứa module có thư mục theo tên module. |
| `--module m.docs` | Chỉ ra mô-đun cần sinh tài liệu. |
| `-d docs` | Đặt thư mục HTML đầu ra. |
| `-encoding UTF-8` | Đọc file nguồn Javadoc bằng UTF-8. |
| `-docencoding UTF-8`, `-charset UTF-8` | Tạo văn bản HTML/khai báo charset UTF-8. |
| `-Xdoclint:all` | Kiểm tra một nhóm lỗi Javadoc như cú pháp HTML, liên kết, tính đầy đủ và tính truy cập; giúp phát hiện lỗi trước khi phát hành. |
| `-quiet` | Giảm thông báo tiến độ, **không** có nghĩa tắt cảnh báo quan trọng. |

**Kết quả kiểm thử:** ví dụ này đã được biên dịch ở chế độ `--release 17` và sinh Javadoc thành công bằng `-Xdoclint:all` trên OpenJDK 24.0.2; `module-summary.html` thực sự được tạo. Vì vậy các đoạn Java và HTML chính của ví dụ đã được kiểm chứng, không phải kết quả dự đoán.

**Windows PowerShell:** có thể đặt hai lệnh `javac` và `javadoc` trên **một dòng** hoặc sử dụng backtick PowerShell để xuống dòng; ký tự `\` nối dòng trong ví dụ Bash không phải cú pháp tiếp dòng của PowerShell. Không dùng `--module-path` để thay thế nhầm cho `--module-source-path` khi Javadoc cần đọc source module.

## 7. Kiểm tra HTML bằng doclint mà không hiểu sai kết quả

`javadoc -Xdoclint:all` là lựa chọn thích hợp cho CI khi muốn kiểm tra chất lượng tài liệu API. Một số loại vấn đề điển hình:

- **HTML:** tên thẻ không hợp lệ, lỗi đóng/mở thẻ, cấu trúc lồng nhau sai, entity không hợp lệ.
- **Reference:** `{@link ...}`/`@see` tham chiếu đến phần tử không được phân giải đúng.
- **Missing:** các phần mô tả bắt buộc trong phạm vi mà doclint kiểm tra, ví dụ tài liệu tham số cho method công khai.
- **Accessibility:** một số thiếu sót về cấu trúc dễ làm tài liệu khó truy cập, ví dụ heading không hợp lệ hoặc bảng thiếu semantic phù hợp.

Tuy nhiên, doclint **không phải bộ xác minh đầy đủ toàn bộ chuẩn HTML5**, cũng không thay thế việc mở trang trong trình duyệt hoặc kiểm tra bằng công cụ accessibility. Một file Javadoc không báo lỗi **chưa chứng minh** rằng nội dung diễn đạt đúng nghiệp vụ, mọi liên kết bên ngoài còn sống, hình có alt hữu ích, hoặc giao diện tài liệu dễ đọc trên điện thoại.

Ví dụ HTML cần tránh:

```java
/**
 * <p>Phần một.
 * <ul><li>Mục A
 * <li>Mục B</ul>
 * <h5>Chi tiết</h5>
 */
```

Tài liệu có thể gặp cảnh báo về cấu trúc hoặc heading. Dùng thẻ đóng rõ ràng và cấp heading phù hợp:

```java
/**
 * <p>Phần một.</p>
 * <h2 id="section-details">Chi tiết</h2>
 * <ul>
 *   <li>Mục A</li>
 *   <li>Mục B</li>
 * </ul>
 */
```

Dù HTML5 có những thẻ có thể được phép bỏ thẻ kết thúc theo quy tắc HTML, **nên viết tường minh trong Javadoc** để người bảo trì dễ đọc và giảm lỗi khi thay đổi tài liệu.

## 8. Bảng, liên kết và khả năng tiếp cận (accessibility)

Đối với bảng diễn giải API, nên có `<caption>` mô tả mục đích và `<th>` xác định tiêu đề cột/hàng:

```java
/**
 * <h2 id="module-capabilities">Năng lực</h2>
 * <table>
 *   <caption>Các API công khai</caption>
 *   <tr>
 *     <th scope="col">Package</th>
 *     <th scope="col">Chức năng</th>
 *   </tr>
 *   <tr>
 *     <td>{@code demo.api}</td>
 *     <td>Tra cứu lời chào</td>
 *   </tr>
 * </table>
 */
```

Bảng trên là **đoạn minh họa nội dung Javadoc**. Với dữ liệu quan hệ phức tạp, cân nhắc thêm `scope="row"` cho header hàng. Không dùng bảng chỉ để chia cột trang trí; nên để CSS do standard doclet quyết định trình bày chung.

Liên kết đến tài liệu Java ưu tiên:

```java
/**
 * Xem {@link java.util.ServiceLoader ServiceLoader}.
 * <p>Thông tin chi tiết ở
 * <a href="https://docs.oracle.com/en/java/">
 * trang tài liệu Java chính thức</a>.</p>
 */
```

`{@link}` giúp kiểm tra Java reference; `<a>` phù hợp khi liên kết ra trang web ngoài. **Không** tự nối đường dẫn nội bộ Javadoc bằng chuỗi hardcode như `../../api/Type.html` nếu `{@link}` có thể biểu đạt; đường dẫn HTML có thể thay đổi khi mô-đun/package được tổ chức lại.

Nếu tài liệu có ảnh (chẳng hạn sơ đồ quan hệ module), cần văn bản thay thế mô tả ý nghĩa của ảnh:

```html
<img src="doc-files/architecture.png"
     alt="Mô-đun m.docs xuất gói demo.api cho ứng dụng khách">
```

Đây là **fragment HTML**, ảnh thực tế phải được cung cấp tại đường dẫn mà Javadoc sẽ xuất/đóng gói. Tên `doc-files/architecture.png` chỉ là ví dụ về file tài nguyên, không mặc định tồn tại trong dự án mẫu.

## 9. HTML trong module-info.java khác tài liệu package/class thế nào?

`module-info.java` là entry point tài liệu cho toàn bộ mô-đun. Nó nên trả lời: mô-đun dùng để làm gì, export API gì, ai nên gọi, cần module/dịch vụ nào, có hạn chế nào cần biết. Dù `javadoc` có thể tự liệt kê directives JPMS, phần mô tả bằng HTML vẫn hữu ích để giải thích **ý nghĩa** của chúng.

| Nơi ghi chú | Nên tập trung vào |
| --- | --- |
| `module-info.java` | Vai trò module, tổng quan, hướng dẫn khởi đầu, mối quan hệ `requires`/`exports`/`uses`/`provides`. |
| `package-info.java` | Phạm vi chức năng của package, quy ước dữ liệu, luồng sử dụng giữa các type. |
| Chú thích `class`/`interface` | Contract của type, điều kiện sử dụng, ví dụ nhỏ và liên kết liên quan. |
| Chú thích `method` | Ý nghĩa tham số, kết quả, ngoại lệ, precondition/postcondition. |
| `doc-files/*.html` | Hướng dẫn dài, sơ đồ, giải thích thuật toán hoặc cấu trúc nhiều phần. |

Một module nên có mô tả ngắn gọn ở phần đầu và đưa nội dung dài xuống các heading `h2/h3` hoặc tài liệu bổ sung. Tránh sao chép từng method vào module Javadoc vì khiến tài liệu lặp và dễ lệch khi code đổi; liên kết từ module tới type bằng `{@link}` là đủ trong nhiều trường hợp.

### Ví dụ rõ ràng cho requires/exports nhưng không lẫn cú pháp

```java
/**
 * Module xử lý hóa đơn.
 *
 * <h2 id="invoice-dependencies">Phụ thuộc</h2>
 * <p>Module dùng API logging của {@link java.logging/}.</p>
 *
 * <h2 id="invoice-api">API công khai</h2>
 * <p>Chỉ export package chứa contract dành cho client.</p>
 */
module example.invoice {
    requires java.logging;
    exports example.invoice.api;
}
```

Ví dụ trên minh họa đúng **ranh giới giữa mô tả và khai báo**; để biên dịch thực tế cần có package `example.invoice.api`. Tên tham chiếu `java.logging/` trong `{@link}` dùng cú pháp reference module của Javadoc. Không ghi `requires java.logging;` **chỉ** trong HTML rồi mong JPMS tự có dependency.

## 10. HTML5 Javadoc và cú pháp Markdown mới: chọn phù hợp phiên bản JDK

Từ **JDK 23**, standard doclet còn hỗ trợ tài liệu dạng Markdown bằng các dòng chú thích **`///`** liên tiếp; đây là lựa chọn **hiện hành**, có thể viết Markdown và một số HTML khi cần. Tuy nhiên, các dự án còn hỗ trợ Java 9/11/17/21 không thể mặc nhiên dùng cú pháp Markdown mới và vẫn sinh tài liệu bằng các phiên bản `javadoc` cũ đó.

Ví dụ **chỉ dành cho `javadoc` JDK 23+**:

```java
/// Module cung cấp API lời chào.
///
/// ## Cách dùng
///
/// Gọi [Greeter][demo.api.Greeter] để lấy lời chào.
module m.docs {
    exports demo.api;
}
```

Đây là **minh họa về cú pháp Javadoc Markdown**, không ghép đồng thời vào module của ví dụ Java 17. Khi phải tương thích với JDK 17/21, dùng `/** ... */` chứa HTML5 và các inline tags `{@code}`/`{@link}` như ví dụ đã kiểm thử; đây vẫn là phương pháp tiêu chuẩn. Trong Markdown `///`, heading Markdown bắt đầu ở mức `#`, khác quy tắc heading HTML truyền thống cấp module là `<h2>`; standard doclet sẽ chuyển các heading Markdown phù hợp với bố cục kết quả.

Đối với **đoạn code phức tạp**, JDK 18+ còn hỗ trợ `{@snippet ...}` cho Javadoc. Nếu cần tài liệu phải sinh với JDK 17, dùng `<pre>{@code ...}</pre>` và kiểm tra escaping; không đưa `{@snippet}` vào pipeline Javadoc 17 rồi kỳ vọng hỗ trợ. Chọn syntax theo phiên bản **công cụ sinh tài liệu**, có thể khác JDK runtime dùng triển khai ứng dụng.

## 11. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `javadoc` báo `unexpected end tag`/`element not closed` | Lồng thẻ/đóng thẻ sai. | Kiểm tra cấu trúc HTML5, đóng `<p>`, `<li>`, `<table>`, `<pre>` rõ ràng. |
| Chuỗi `List<String>` mất một phần | Đã viết raw `<String>` như HTML. | Dùng `{@code List<String>}` hoặc `List&lt;String&gt;`. |
| Văn bản `&&` bị hiển thị bất thường | `&` có ý nghĩa mở HTML entity. | Dùng `{@code a && b}` hoặc `&amp;&amp;`. |
| Mục lục/phần heading rối | Dùng `<h1>` ở cấp module hoặc nhảy cấp `h2 → h5`. | Ở module/type bắt đầu `h2`, tăng `h3` khi cần. |
| Link Java type không hoạt động | Viết hardcoded `href` sai hoặc tham chiếu type không được giải quyết. | Dùng `{@link ...}`; bật `doclint` và cấu hình module/source path đúng. |
| Không thấy mô tả module | Comment không nằm ngay trước `module`, chọn sai module hoặc thiếu source. | Đặt `/** ... */` đúng vị trí; chạy `javadoc --module-source-path ... --module ...`. |
| Tài liệu tiếng Việt bị lỗi dấu | Sai mã hóa file hoặc encoding của tool/output. | Lưu UTF-8; dùng `-encoding`/`-docencoding`/`-charset UTF-8`. |
| Javadoc báo lỗi tag `@param` ở module | Block tag dùng sai phạm vi. | `@param` thuộc method/constructor/type parameter; module dùng `@since`/`@uses`/`@provides` phù hợp. |
| Bảng đọc khó bằng screen reader | Thiếu caption/header có ý nghĩa. | Thêm `<caption>`, `<th scope="col">` và quan hệ hàng/cột rõ. |
| Chèn HTML hoạt động trong trình duyệt nhưng không phù hợp Javadoc | Nội dung dùng `<html>/<body>` hoặc thay đổi layout toàn trang. | Viết fragment HTML5 trong comment; để doclet sinh template trang. |
| `javadoc -Xdoclint:all` thành công nhưng trang vẫn khó đọc | Doclint không kiểm hết bố cục, UX/accessibility. | Mở file HTML trong trình duyệt và kiểm tra bằng công cụ accessibility. |
| Dùng `///` trên JDK 17 mà không tạo mô tả | Cú pháp Markdown comment được hỗ trợ từ JDK 23. | Với Javadoc 17 dùng `/** ... */` HTML5 truyền thống. |
| Javadoc dài có nhiều mã chứa `*/` | `*/` đóng comment Java trước khi parser Javadoc xử lý. | Đưa code phức tạp ra ví dụ riêng hoặc đổi cách trích dẫn an toàn. |

## 12. Checklist rà soát trước khi phát hành tài liệu mô-đun

1. Đặt đúng `/** ... */` ngay trước `module` trong `module-info.java`, và phần mở đầu có **một câu summary ngắn, đủ ý**.
2. Dùng **HTML5 fragment**, chia đoạn bằng `<p>` và heading bắt đầu `h2`; tránh tùy tiện nhảy cấp.
3. Với generic/biểu thức, dùng `{@code}` hoặc `{@literal}`; ở text HTML phải escape `<` và `&`.
4. Với code nhiều dòng, dùng `<pre>{@code ...}</pre>` và kiểm tra nội dung không tự kết thúc comment `*/`.
5. Liên kết Java qua `{@link}`/`{@linkplain}`; liên kết web qua `<a href>` có text mô tả.
6. Bảng có `<caption>` và `<th>`; ảnh có `alt`; tránh heading chỉ để trang trí.
7. Đặt block tags `@since`, `@see`, `@uses`/`@provides` sau mô tả chính và đúng loại phần tử.
8. Chạy `javac` cho source module; chạy `javadoc -Xdoclint:all` để kiểm tra nội dung Javadoc.
9. Mở `module-summary.html`, điều hướng link, kiểm tra UTF-8, heading, bảng và preformatted code.
10. Nếu dự án dùng các JDK khác nhau, chọn cú pháp tương thích **JDK chạy công cụ javadoc**, không nhầm với JDK runtime.

## 13. Tự kiểm tra kiến thức

1. **Trong `module-info.java`, mô tả HTML nên bắt đầu heading từ mức nào?**  
   Từ `<h2>` theo đặc tả standard doclet khi dùng chú thích truyền thống.

2. **Vì sao `/** Định dạng List<String> */` dễ gây lỗi?**  
   Vì `<String>` có thể bị hiểu như thẻ HTML. Viết `{@code List<String>}` hoặc escape `List&lt;String&gt;`.

3. **Làm thế nào để sinh liên kết tới một type Java?**  
   Dùng `{@link package.Type}` hoặc `{@linkplain package.Type nhãn}` trong comment và bảo đảm type tham chiếu được phân giải bởi công cụ.

4. **Chú thích `/** ... */` đặt ngay trước `module` có thay đổi quyền `exports` hay phụ thuộc `requires` không?**  
   Không. Nó mô tả; chỉ các directives trong thân module mới cấu hình JPMS.

5. **Bảng Javadoc cần gì để dễ hiểu và phù hợp accessibility?**  
   Ít nhất nên có caption mô tả và header semantic `<th>`; dùng `scope` khi thích hợp.

6. **Vì sao cần `-Xdoclint:all` nếu trình duyệt vẫn có thể hiển thị trang?**  
   Vì trình duyệt có thể tự sửa lỗi HTML; doclint phát hiện sớm nhiều lỗi markup, links, thiếu mô tả hoặc cấu trúc mà đọc bằng mắt khó thấy.

7. **Có thể dùng `///` để thay thế hoàn toàn `/** ... */` khi build tài liệu bằng JDK 17 không?**  
   Không. Cú pháp Javadoc Markdown comment `///` được hỗ trợ từ JDK 23 trở đi; trên JDK 17 nên dùng chú thích truyền thống.

## 14. Tài liệu tham khảo chính thức còn hiệu lực

- [JDK 26 — JavaDoc Documentation Comment Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): HTML5, heading, escaping, inline/block tags, tài liệu mô-đun và cú pháp Markdown `///`.
- [JDK 26 — Hướng dẫn công cụ javadoc](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): `--module-source-path`, `--module`, `-Xdoclint`, encoding và lựa chọn sinh tài liệu.
- [JDK 26 — javadoc Tool Guide](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/javadoc.html): cấu trúc nội dung, hướng dẫn tạo tài liệu API với standard doclet.
- [JDK 26 — Module System, java.lang.Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html): module và API phản chiếu runtime (không nhầm với nội dung Javadoc).
- [JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): cú pháp `///` đã được đưa vào JDK 23; dùng khi phiên bản công cụ đáp ứng yêu cầu.
