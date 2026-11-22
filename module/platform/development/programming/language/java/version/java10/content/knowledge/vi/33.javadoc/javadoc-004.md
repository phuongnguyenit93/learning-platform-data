# `--main-stylesheet` và kiểu dáng chính của Javadoc (Java 10+)

## 1. Mục tiêu bài học

Khi dùng `javadoc` để sinh tài liệu API HTML, công cụ **standard doclet** tạo các trang mô tả package, class, interface, constructor, method và field, kèm một **stylesheet mặc định**. Stylesheet này định nghĩa phần lớn cách trình duyệt hiển thị tài liệu: font chữ, màu sắc, bố cục, bảng, thanh điều hướng, phần chi tiết phương thức, code blocks và các trạng thái tương tác.

Từ Java 10, một cú pháp cấu hình quan trọng là:

~~~bash
javadoc --main-stylesheet styles/brand-main.css -d out/api-docs -sourcepath src demo.docs
~~~

Tùy chọn **`--main-stylesheet <file>`** yêu cầu standard doclet sử dụng **một CSS stylesheet chính do bạn cung cấp thay cho stylesheet mặc định**. Tính năng này vẫn được ghi nhận trong tài liệu `javadoc` của Oracle JDK 25. Nó khác đáng kể với **`--add-stylesheet`**, vốn **giữ stylesheet mặc định** và nạp thêm CSS để thay đổi chọn lọc.

Bài này thuộc nhóm **Javadoc** trong module **Java 10**; chỉ tập trung vào cách sử dụng còn hiệu lực của `--main-stylesheet`, có đối chiếu với tài liệu JDK 17/21/25 và các nguyên tắc HTML/CSS hiện hành. Không khuyến nghị những workflow legacy dựa trên output HTML dạng frames hoặc các công cụ/doclet cũ không còn phù hợp.

### Sau bài học, bạn có thể

1. Giải thích rõ **main stylesheet** là gì, nó nằm ở đâu trong pipeline sinh tài liệu Javadoc.
2. Viết đúng lệnh `javadoc --main-stylesheet` và phân biệt với alias `-stylesheetfile`.
3. Phân biệt **thay thế stylesheet chính** và **nạp stylesheet bổ sung**.
4. Hiểu tại sao một CSS quá ngắn có thể làm hỏng bố cục, search UI, navigation hoặc responsive layout.
5. Tạo một project Java 17+ chạy độc lập, sinh Javadoc mặc định, sao chép stylesheet mặc định của đúng JDK rồi tùy chỉnh.
6. Sử dụng CSS variables của Javadoc hiện đại khi phù hợp, thay vì sao chép selectors theo một bản JDK khác.
7. Xác nhận stylesheet có thực sự được đóng gói/link trong HTML sau khi sinh.
8. Chẩn đoán lỗi về file path, encoding, CSS cascade, cache, assets tương đối và khác biệt JDK.
9. Kiểm tra accessibility, responsive design, contrast, security và tính ổn định của tài liệu công bố.
10. Đưa Javadoc CSS vào quy trình build/CI một cách tái lập, có khả năng rollback.

**Thông điệp chính:** `--main-stylesheet` là cách **thay thế toàn bộ nền CSS** của standard doclet. Nếu bạn chỉ cần sửa vài màu hoặc font, **`--add-stylesheet` thường ít rủi ro hơn**.

## 2. Javadoc tạo HTML và CSS như thế nào?

Một pipeline đơn giản:

~~~text
src/demo/docs/Greeting.java
       │
       ▼
javadoc + standard doclet
       │
       ├── Đọc source/Javadoc comments
       ├── Phân tích API declarations
       ├── Sinh HTML pages
       ├── Chọn CSS chính
       │      ├── Không truyền --main-stylesheet
       │      │      → CSS mặc định của JDK
       │      └── Có --main-stylesheet custom.css
       │             → CSS chính từ custom.css
       └── Có thể nạp thêm --add-stylesheet
              → CSS bổ sung
       │
       ▼
out/api-docs/
       ├── index.html
       ├── demo/docs/Greeting.html
       ├── tệp CSS đã sinh/copy
       ├── script, index, search assets...
       └── các tài nguyên khác do doclet quản lý
       │
       ▼
Trình duyệt: render HTML + CSS + assets
~~~

**Javadoc ở đây là công cụ sinh tài liệu**, không phải `javac` đang thay đổi hành vi bytecode. Tùy chọn stylesheet chỉ ảnh hưởng các tệp tài liệu được tạo (và cách trình duyệt hiển thị), không làm thay đổi kiểu Java, class loading hoặc logic chương trình.

### “Kiểu dáng chính” là gì?

Trong HTML được tạo, các trang cần những CSS rules để đảm bảo:
- Cỡ chữ và tỷ lệ font cho nội dung/documentation code.
- Màu văn bản, màu link, màu khi hover và màu nền.
- Các nhóm navigation, tabs, breadcrumbs, sidebar.
- Bảng liệt kê API, method summary, field summary.
- Phân cấp headings và các vùng chi tiết.
- Spacing, borders, focus indicators, khả năng cuộn.
- Trải nghiệm màn hình nhỏ và in ấn.
- Tương thích giao diện do standard doclet của đúng JDK phát ra.

Stylesheet chính mặc định được xây dựng để phục vụ toàn bộ giao diện đó. Thay nó bằng một file chỉ có:

~~~css
body {
    color: navy;
}
~~~

**không tương đương** “giữ theme cũ và đổi màu text thành xanh”. Với `--main-stylesheet`, nhiều CSS rules mặc định sẽ **không còn**, khiến giao diện có thể bị thiếu bố cục và kiểu dáng thiết yếu.

## 3. Cú pháp chính xác và phạm vi hỗ trợ

Dạng cú pháp:

~~~bash
javadoc --main-stylesheet path/to/main.css [các-tùy-chọn-khác] [tên-package-hoặc-sourcefiles]
~~~

Ví dụ hoàn chỉnh:

~~~bash
javadoc -d out/docs --main-stylesheet styles/main.css -sourcepath src demo.docs
~~~

Ý nghĩa:

| Thành phần | Chức năng |
| --- | --- |
| `javadoc` | Chạy công cụ sinh API docs |
| `-d out/docs` | Thư mục output tài liệu |
| `--main-stylesheet styles/main.css` | Chọn CSS chính thay CSS mặc định |
| `-sourcepath src` | Tìm Java source theo package ở thư mục `src` |
| `demo.docs` | Package cần sinh tài liệu |

**File path** là đường dẫn tới tệp CSS đầu vào, thường được resolve tương đối với **working directory khi gọi `javadoc`**. Nó không được hiểu mặc định là đường dẫn tương đối với `-d` hoặc tương đối với thư mục chứa file Java.

Nếu đường dẫn chứa khoảng trắng, quote đúng theo shell:

~~~bash
javadoc -d out/docs --main-stylesheet "styles/Company Brand.css" -sourcepath src demo.docs
~~~

Tên file **không bắt buộc** phải là `stylesheet.css`; tài liệu Oracle cho phép các tên khác. Tuy nhiên phần mở rộng `.css` và tên dễ hiểu sẽ giúp vận hành và review thuận tiện.

### Aliases: `--main-stylesheet` và `-stylesheetfile`

Oracle JDK 25 còn mô tả:

~~~bash
javadoc --main-stylesheet styles/main.css demo.docs
javadoc -stylesheetfile styles/main.css demo.docs
~~~

Trong standard doclet, **hai dạng này nói về việc thay stylesheet mặc định**. Dạng **`--main-stylesheet` được Oracle khuyến nghị dùng hơn**. Không cần tuyên bố `-stylesheetfile` đã bị xóa hoàn toàn: tài liệu JDK hiện đại vẫn nhắc nó là dạng thay thế. Nhưng cho dự án mới, ưu tiên tên option dài rõ nghĩa.

**Phạm vi:** Đây là **option của standard doclet**. Nếu dùng `-doclet` để thay bộ sinh HTML bằng một custom doclet, các option và cách sinh CSS có thể khác. Không mặc định custom doclet phải tuân theo cơ chế CSS của standard doclet.

### Khi không cấu hình stylesheet

Ví dụ:

~~~bash
javadoc -d out/default -sourcepath src demo.docs
~~~

Standard doclet sẽ **tạo và dùng stylesheet mặc định**. Đây là điểm xuất phát an toàn, đặc biệt khi chưa cần branding phức tạp.

## 4. Phân biệt `--main-stylesheet` và `--add-stylesheet`

| Tiêu chí | `--main-stylesheet` | `--add-stylesheet` |
| --- | --- | --- |
| Bản chất | **Thay thế** stylesheet mặc định | **Bổ sung** stylesheet |
| CSS mặc định còn tự được áp dụng? | Không, CSS do bạn cung cấp phải làm nền | Có |
| Mức độ kiểm soát | Cao, có thể thay toàn bộ quy tắc | Phù hợp chỉnh chọn lọc |
| Rủi ro mất layout mặc định | Cao nếu CSS không đầy đủ | Thấp hơn |
| Use case phù hợp | Một theme tùy biến sâu, có hệ thống kiểm thử | Đổi màu, font, một số spacing |
| Yêu cầu khi nâng JDK | Rà soát toàn bộ nền CSS và HTML output | Rà soát overrides/selectors đang dùng |
| Số lần dùng | Thực tế nên có một stylesheet chính | Có thể nạp nhiều stylesheet bổ sung |
| Khuyến nghị mặc định | Chỉ dùng khi cần thay nền | **Ưu tiên** cho thay đổi nhỏ |

Ví dụ dùng CSS bổ sung:

~~~bash
javadoc -d out/added --add-stylesheet styles/overrides.css -sourcepath src demo.docs
~~~

Ở đây stylesheet mặc định **vẫn có vai trò nền**, còn rules từ `overrides.css` tham gia CSS cascade. Oracle Javadoc CSS Themes Guide khuyên dùng cách này khi chỉ muốn **đổi các CSS properties chọn lọc**.

Ví dụ dùng CSS chính:

~~~bash
javadoc -d out/main --main-stylesheet styles/complete-main.css -sourcepath src demo.docs
~~~

Ở đây file `complete-main.css` phải cung cấp **đủ rules thiết yếu cho cả bố cục**. Cách thực tế là **bắt đầu từ stylesheet mặc định do chính bản JDK đang dùng tạo ra**, rồi kiểm soát các phần đổi.

### Kết hợp cả hai option?

Ở các standard doclet hiện đại hỗ trợ hai option, bạn có thể có một **main stylesheet tùy chỉnh** và các **additional stylesheets** được nạp thêm để tách concerns (ví dụ một CSS nền và một CSS cho thương hiệu). Tuy nhiên:
- Quy tắc override cụ thể còn phụ thuộc **CSS cascade, specificity và thứ tự nạp**.
- Cấu hình được kiểm tra trên **đúng JDK build** đang sinh docs.
- Không đặt hai stylesheet “chính” cạnh tranh nhau như một mẹo chọn theme lúc runtime.

Nếu chỉ cần một ít thay đổi, bỏ `--main-stylesheet` và dùng `--add-stylesheet` thường đơn giản hơn.

## 5. Tạo một project minh họa có thể chạy bằng JDK 17+

Bài thực hành sau sử dụng những API Java đã có từ Java 10, nhưng chọn **JDK 17+** để có runtime được hỗ trợ hơn. Công cụ `javadoc` dùng chính JDK mà bạn cài; CSS mặc định **có thể khác giữa các JDK**, đó cũng là lý do bài yêu cầu lấy CSS nền từ **đúng JDK hiện dùng**.

### 5.1. Cấu trúc project

~~~text
javadoc-css-demo/
├── src/
│   └── demo/
│       └── docs/
│           └── Greeting.java
├── styles/
│   ├── brand-main.css       (sẽ tạo sau)
│   └── overrides.css        (tùy chọn, sẽ tạo sau)
└── out/
    ├── classes/             (khi compile)
    ├── default/             (Javadoc mặc định)
    ├── branded/             (Javadoc dùng main CSS)
    └── added/               (Javadoc dùng additional CSS)
~~~

Các thư mục `styles` và `out` ban đầu có thể chưa tồn tại; ta sẽ tạo chúng trong các bước tương ứng. Phần sau có lệnh shell POSIX cho Linux/macOS và gợi ý tương đương PowerShell.

### 5.2. Tạo file Java đầy đủ

Tạo **`src/demo/docs/Greeting.java`**:

~~~java
package demo.docs;

/**
 * Utility for producing short greetings in API examples.
 *
 * <p>The class is intentionally small so that its generated
 * Javadoc is easy to inspect.
 *
 * @since 1.0
 */
public final class Greeting {

    private Greeting() {
        throw new AssertionError("No instances");
    }

    /**
     * Creates a greeting for the supplied name.
     *
     * @param name the name to greet
     * @return a non-empty greeting string
     * @throws IllegalArgumentException if the name is null or blank
     */
    public static String greet(String name) {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }

    /**
     * Runs a deterministic demonstration.
     *
     * @param args command-line arguments, not used
     */
    public static void main(String[] args) {
        System.out.println(greet("Javadoc"));
    }
}
~~~

Chương trình có:
- Package `demo.docs`.
- Class công khai `Greeting`, method `greet`.
- Javadoc comments ở class và methods.
- Các tags `@param`, `@return`, `@throws`, `@since`.
- Method `main` để chạy thử không cần thư viện ngoài.

`String.trim()` và `String.isEmpty()` đều đã có từ trước Java 10; ví dụ **không dùng API mới hơn Java 10**. Dù vậy việc sinh **HTML/CSS** sẽ phản ánh **bản JDK chạy `javadoc`**, không phản ánh mức source compatibility một cách tuyệt đối.

### 5.3. Biên dịch và chạy chương trình

Từ thư mục gốc `javadoc-css-demo`:

~~~bash
javac -encoding UTF-8 -d out/classes src/demo/docs/Greeting.java
java -cp out/classes demo.docs.Greeting
~~~

**Stdout chính xác của chương trình Java:**

~~~text
Hello, Javadoc!
~~~

Nếu bạn cần kiểm tra riêng khả năng biên dịch theo Java 10 trên một JDK có hỗ trợ target ấy:

~~~bash
javac --release 10 -encoding UTF-8 -d out/classes src/demo/docs/Greeting.java
java -cp out/classes demo.docs.Greeting
~~~

Lệnh này kiểm tra source/API compatible Java 10, **không** thay thế việc kiểm tra các CSS classes/stylesheet do JDK sinh docs. Một số JDK tương lai có thể không hỗ trợ mọi `--release` cũ; trong trường hợp đó, dùng JDK phù hợp với release cần kiểm tra.

## 6. Sinh Javadoc mặc định để có CSS nền đáng tin

Từ thư mục gốc:

~~~bash
javadoc -encoding UTF-8 -d out/default -sourcepath src demo.docs
~~~

Đọc kết quả:
- `-encoding UTF-8`: cách đọc Java source chứa ký tự Unicode.
- `-d out/default`: đặt tài liệu được sinh trong thư mục riêng.
- `-sourcepath src`: tìm package `demo.docs` ở `src/demo/docs`.
- `demo.docs`: package cần đưa vào tài liệu.

Sau khi lệnh thành công, mở:
- `out/default/index.html` — điểm vào API docs.
- `out/default/demo/docs/Greeting.html` — trang class.

**Không cung cấp “stdout chính xác” cho lệnh `javadoc`**: công cụ có thể in file names, warnings, diagnostic lines khác nhau theo JDK, locale và source. Kết quả xác minh đáng tin là **exit code thành công và các HTML/CSS files hợp lệ**.

### Kiểm tra CSS nền mà chính JDK tạo

Trong output của standard doclet, tài liệu thường có file CSS chính, ví dụ **`out/default/stylesheet.css`**. Trên những bản JDK được hỗ trợ, đây là nguồn khởi đầu thực tế cho theme thay thế.

~~~bash
ls -l out/default/stylesheet.css
~~~

Nếu đường dẫn này khác ở JDK/doclet của bạn, hãy **xem tệp CSS được các trang HTML tạo ra tham chiếu đến**, thay vì tự giả định một tên cứng. Tính năng `--main-stylesheet` có thể dùng tên input CSS khác `stylesheet.css`; đừng dựa vào filename để suy ra CSS đã được nạp.

### Tại sao cần làm bước mặc định trước?

Một file CSS ngắn viết từ đầu rất dễ bỏ sót:
- Thanh điều hướng và trạng thái active.
- Bảng summary/detail của class và methods.
- Breakpoints cho màn hình hẹp.
- Search input và các controls.
- Font/spacing cho code blocks.
- Print styles và focus states.

Lấy CSS nền từ **cùng JDK build** giúp bắt đầu với các selectors/variables gần với HTML mà build đó tạo ra, giảm nguy cơ giao diện vỡ.

## 7. Quy trình chính: tạo `brand-main.css` bằng cách chỉnh stylesheet nền

### 7.1. Sao chép stylesheet mặc định

Ví dụ trên Linux/macOS hoặc shell tương thích:

~~~bash
mkdir -p styles
cp out/default/stylesheet.css styles/brand-main.css
~~~

**Đây là bước quyết định:** `brand-main.css` ban đầu chứa toàn bộ những quy tắc mà standard doclet đã sinh. Ta sẽ chỉnh chọn lọc mà **không xóa nền**.

Trên Windows PowerShell, có thể dùng:

~~~powershell
New-Item -ItemType Directory -Force styles
Copy-Item out/default/stylesheet.css styles/brand-main.css
~~~

Cần chắc chắn bạn ở thư mục gốc project. Nếu copy sai path, sẽ không có CSS đầu vào hợp lệ cho bước sau.

### 7.2. Chỉnh quy tắc bằng CSS có kiểm soát

Ở cuối **`styles/brand-main.css`**, thêm:

~~~css
/* Brand overrides appended to the matching Javadoc base theme. */
:root {
    --body-background-color: #f6f9fc;
    --body-text-color: #243345;
    --link-color: #155eac;
    --navbar-background-color: #e1edfa;
    --navbar-text-color: #172f4d;
}

body {
    background-color: #f6f9fc;
    font-family: system-ui, -apple-system, "Segoe UI",
                 Arial, sans-serif;
}
~~~

**Quan trọng về phiên bản:**
- Các CSS custom properties như `--body-background-color`, `--link-color`, `--navbar-background-color` được **hướng dẫn chính thức của Javadoc CSS Themes trên JDK hiện đại (ví dụ JDK 21/25)** mô tả.
- CSS custom properties đã là công nghệ CSS hiện đại, nhưng **stylesheet mặc định của một Javadoc JDK 10 đời đầu có thể chưa sử dụng đúng bộ custom property names này**. Một biến CSS mà stylesheet không tham chiếu sẽ không tự làm thay đổi giao diện.
- Khi dùng JDK 10 hoặc một JDK khác, hãy **kiểm tra CSS mặc định của chính build** và sửa các quy tắc thực sự tồn tại, thay vì giả định CSS variables hiện nay có hiệu lực trên mọi phiên bản.
- Ví dụ `body` phía trên cung cấp một thay đổi trực tiếp (font/nền), nhưng theme thực có thể có selectors với specificity cao hơn; cần kiểm tra kết quả.

**CSS không phải Java source.** Nó phải nằm trong file `.css` riêng, không đặt nguyên vào Javadoc comments rồi mong tool tự chuyển thành stylesheet.

### 7.3. Sinh tài liệu với stylesheet chính thay thế

~~~bash
javadoc -encoding UTF-8 -d out/branded --main-stylesheet styles/brand-main.css -sourcepath src demo.docs
~~~

Sau khi chạy thành công:
1. Mở `out/branded/index.html`.
2. Mở `out/branded/demo/docs/Greeting.html`.
3. Kiểm tra thanh điều hướng, class summary, method detail, links và font.
4. Kiểm tra stylesheet được liên kết trong HTML có tồn tại trong **thư mục output công bố**.
5. So hình thức với `out/default` để đảm bảo bạn chỉ thay những phần mong muốn.

**Tại sao phải kiểm tra file được link?** Đường dẫn CSS đầu vào là `styles/brand-main.css`, nhưng HTML cuối phải tham chiếu tới tài nguyên **nằm trong cấu trúc output** mà bạn triển khai. Không nên publish HTML mà bỏ quên CSS do doclet tạo/copy.

### 7.4. Kiểm tra HTML bằng browser DevTools

Mở file class trong trình duyệt. Trong Developer Tools:
- Tab **Elements/Inspector**: tìm thẻ `<link rel="stylesheet" ...>`.
- Tab **Network**: xác minh CSS request thành công, không có 404.
- Tab **Computed styles**: xem rule nào đang quyết định `background-color`, font và màu links.
- Tab **Console**: chú ý lỗi tài nguyên hoặc script liên quan.

**Đừng kiểm tra chỉ riêng file CSS**: điều cần xác nhận là **HTML Javadoc đã tạo thực sự dùng file ấy và render đúng**.

## 8. Trường hợp chỉ cần thay vài màu: dùng `--add-stylesheet`

Đây là cách Oracle đề xuất trong CSS Themes Guide khi muốn giữ theme mặc định.

Tạo **`styles/overrides.css`**:

~~~css
/* Small, optional overrides for recent Javadoc default themes. */
:root {
    --body-background-color: #f6f9fc;
    --body-text-color: #243345;
    --link-color: #155eac;
    --navbar-background-color: #e1edfa;
}

body {
    font-family: system-ui, -apple-system, "Segoe UI",
                 Arial, sans-serif;
}
~~~

Chạy:

~~~bash
javadoc -encoding UTF-8 -d out/added --add-stylesheet styles/overrides.css -sourcepath src demo.docs
~~~

Ở `out/added`, **CSS mặc định vẫn là nền**. File `overrides.css` chỉ bổ sung những declarations bạn muốn điều chỉnh. Với các JDK hiện đại mà stylesheet mặc định dùng custom properties kể trên, đây thường là cách đơn giản và dễ bảo trì.

### Nếu chỉ muốn thay font và màu, sao không dùng main luôn?

Với `--main-stylesheet`, doclet không tự giữ nền cho bạn; nếu file chỉ có vài rules, các phần navigation/tables/layout có thể mất style. `--add-stylesheet` không có nhược điểm này vì CSS mặc định vẫn được nạp.

**Tóm lại:**
- `--main-stylesheet`: thay **nền** CSS.
- `--add-stylesheet`: thêm **lớp override**.

Không dùng hai option như synonyms; sự khác biệt là **thực chất kỹ thuật**, không chỉ tên gọi.

## 9. CSS cascade và thứ tự áp dụng rule

Javadoc sinh HTML, nhưng việc áp dụng CSS là trách nhiệm của **trình duyệt** theo quy tắc CSS cascade:
1. Stylesheet được liên kết hoặc khai báo hợp lệ.
2. Origin, importance, cascade layer (nếu dùng), specificity.
3. Thứ tự xuất hiện khi các quy tắc khác tương đương.
4. Kế thừa và CSS custom properties.
5. Media queries, trạng thái hover/focus, browser/OS preferences.

Ví dụ:

~~~css
a {
    color: #155eac;
}

a:hover {
    color: #0a3970;
}
~~~

Nếu Javadoc stylesheet có một selector **cụ thể hơn**, quy tắc `a` có thể không thắng. Vì thế khi “CSS không có tác dụng”, hãy xem **Computed styles** và **CSS specificity**, không vội thêm nhiều `!important`.

### Vì sao lạm dụng `!important` có hại?

Một rule:

~~~css
a {
    color: purple !important;
}
~~~

có thể thắng nhiều rules mặc định, nhưng cũng có thể ghi đè màu của:
- Navigation links;
- Disabled/inactive states;
- Selected tabs;
- Code links;
- Contrast/accessibility states.

**Nên ưu tiên** sửa đúng CSS variable hoặc selector có phạm vi phù hợp, rồi kiểm tra toàn bộ UI. Chỉ dùng `!important` khi có lý do được hiểu rõ và đã kiểm thử các trạng thái liên quan.

### CSS variables trong Javadoc hiện đại

Oracle JDK 25 Javadoc CSS Themes Guide mô tả các property names như:

| CSS variable | Mục đích |
| --- | --- |
| `--body-font-family` | Font nội dung |
| `--code-font-family` | Font code |
| `--body-font-size` | Cỡ chữ nền |
| `--code-font-size` | Cỡ chữ code |
| `--body-background-color` | Nền trang |
| `--body-text-color` | Màu chữ chính |
| `--section-background-color` | Nền vùng section |
| `--detail-background-color` | Nền vùng detail |
| `--navbar-background-color` | Nền thanh điều hướng |
| `--navbar-text-color` | Màu chữ trên thanh điều hướng |
| `--link-color` | Màu liên kết |
| `--link-color-active` | Màu liên kết khi active |
| `--border-color` | Màu viền |
| `--table-border-color` | Màu viền bảng |
| `--search-input-background-color` | Nền ô tìm kiếm |
| `--search-input-text-color` | Màu chữ ô tìm kiếm |

Khi biến được khai báo trong `:root`, những quy tắc tham chiếu qua `var(--...)` có thể nhận giá trị mới.

**Độ tương thích:** tên và số lượng CSS variables là một phần của **CSS theme theo bản Javadoc cụ thể**, không phải API bất biến của mọi JDK từ Java 10. Trước khi nâng build, đọc stylesheet mới được tạo và tài liệu theme tương ứng.

## 10. Tại sao stylesheet chính phải tương thích với HTML do doclet sinh?

Thay CSS là thay cách trình bày, nhưng bạn không quyết định được markup nội bộ do standard doclet sinh theo mọi phiên bản.

Ví dụ những thành phần cần style:
- Header, navbar, package/class lists.
- Class summary và method summary.
- Search box, filter tabs, focus/selected states.
- Inline code và code blocks.
- Bảng API có độ rộng lớn, cột chứa signatures dài.
- Notes về deprecated/since/annotations.
- Links tới inherited methods.
- Mobile/responsive layout.
- Print output và dark/light color preferences nếu dùng.

Một CSS “đẹp” trên `index.html` có thể khiến `Greeting.html` hiển thị bảng method bị tràn. Cần kiểm tra **nhiều loại trang**, không chỉ trang đầu.

### Không dựa vào CSS selector cũ một cách mù quáng

Javadoc HTML output có thể thay đổi giữa JDK 10, 17, 21, 25:
- Tên class hoặc cấu trúc HTML được cải tiến.
- Navigation/search UI thay đổi.
- Các CSS variables mới được thêm hoặc cũ thay cách dùng.
- Các selectors cụ thể có thể khác.

Do đó, **đừng lấy toàn bộ stylesheet cũ của JDK 10 rồi gắn vào HTML do JDK 25 sinh** và giả định mọi thành phần đúng. Với `--main-stylesheet`, nên giữ baseline CSS cùng JDK build hoặc phải kiểm tra kỹ toàn bộ trường hợp nếu chủ động phát triển theme riêng.

### Thay theme không thay nội dung Javadoc

`--main-stylesheet` không tự:
- Thêm/bớt classes trong documentation.
- Thay Java source parsing.
- Sửa nội dung `@param` hoặc `@return`.
- Chuyển Javadoc HTML thành PDF.
- Thay đổi Java bytecode đã được `javac` biên dịch.
- Tăng bảo mật của API hoặc làm private members được công bố.

Nó chỉ ảnh hưởng **CSS assets và cách HTML được trình duyệt render**.

## 11. Kiểm tra kết quả bằng dòng lệnh và trình duyệt

Sau khi tạo `out/branded`, quy trình xác minh gồm nhiều lớp.

### 11.1. Kiểm tra lệnh đã thành công

- `javadoc` có exit status thành công.
- Không có lỗi không đọc được CSS file đầu vào.
- Có HTML được sinh tại `-d`.
- Có CSS file được HTML tham chiếu.
- Có trang class/package cần công bố.

Một exit code thành công **chưa đủ** để kết luận giao diện đúng; CSS có thể hợp lệ cú pháp nhưng không áp dụng selector mong muốn.

### 11.2. Kiểm tra các liên kết tài nguyên

Mở **trang class** trong browser, tìm `<link rel="stylesheet" ...>`. Đường dẫn trong HTML là đường dẫn **theo cấu trúc output**, không nhất thiết giống absolute source path đã đưa vào `--main-stylesheet`.

Với một dự án Javadoc thông thường, stylesheet chính thường được đặt tại root output hoặc vị trí do doclet chọn. Thay vì hard-code tên cuối, kiểm tra chính HTML được sinh.

Các assets CSS tham chiếu qua `url(...)` còn cần được xem trong DevTools Network. Một CSS file vẫn có thể được tải nhưng ảnh/font của nó **404** nếu không được đóng gói đúng.

### 11.3. Đối chiếu trước và sau

So:
- `out/default/index.html` với `out/branded/index.html`.
- `out/default/demo/docs/Greeting.html` với `out/branded/demo/docs/Greeting.html`.
- `out/default` với `out/added` nếu có.

Đối chiếu bằng ảnh chụp hoặc manual review:
- Heading và body text có đọc dễ không?
- Các bảng summary có giữ layout không?
- Search/filter controls còn dùng được không?
- Links hover/focus nhìn rõ không?
- Nội dung trên màn hình nhỏ có bị tràn không?
- Các vùng code có bị che/cắt không?

### 11.4. Kiểm thử trên vài viewport

Một quy trình đơn giản:
1. Màn hình desktop rộng.
2. Tablet viewport.
3. Mobile viewport nhỏ.
4. Zoom 200%.
5. Tab/Shift+Tab để xem keyboard focus.
6. Print preview nếu người dùng in tài liệu.

**“Mở đẹp trên laptop của người viết CSS” không đủ để chứng minh stylesheet chính an toàn để phát hành.**

## 12. Lỗi thường gặp khi dùng `--main-stylesheet`

### Lỗi 1 — Đưa vào file CSS chỉ có một vài dòng

~~~bash
javadoc --main-stylesheet styles/colors-only.css -d out/docs -sourcepath src demo.docs
~~~

Nếu `colors-only.css` chỉ đổi màu, **CSS nền của standard doclet đã bị thay thế**, khiến nhiều thành phần mất style.

**Cách sửa:** dùng `--add-stylesheet` nếu thay ít properties, hoặc sao chép đầy đủ default stylesheet và chỉnh nó.

### Lỗi 2 — Nhầm `--main-stylesheet` với `--add-stylesheet`

Hai option **không tương đương**. Một cái thay toàn bộ stylesheet mặc định, một cái thêm stylesheet mới.

**Cách sửa:** xác định mục tiêu: thay nền sâu hay override chọn lọc.

### Lỗi 3 — Đường dẫn CSS tương đối bị resolve sai

Ví dụ bạn chạy `javadoc` từ một thư mục khác nhưng vẫn ghi `styles/main.css`. Công cụ có thể không thấy file.

**Cách sửa:** chạy từ project root, dùng path chính xác hoặc absolute path phù hợp môi trường. Tránh ghép path theo file Java mà không biết working directory.

### Lỗi 4 — Copy stylesheet của JDK khác

Markup và CSS selectors có thể không còn đồng bộ, gây lỗi navigation/tables/search.

**Cách sửa:** tạo default Javadoc từ đúng JDK build rồi mới lấy CSS nền, hoặc kiểm thử toàn bộ khi chuyển theme.

### Lỗi 5 — Chỉ sửa CSS variables trên JDK chưa dùng các variables đó

Ví dụ đổi `--body-background-color` nhưng stylesheet của phiên bản đang dùng không tham chiếu biến. Kết quả có thể không đổi.

**Cách sửa:** đọc CSS mặc định thực tế và dùng selectors/variables tương ứng với JDK đó.

### Lỗi 6 — Có CSS trong thư mục source nhưng output HTML không link

Việc đặt CSS ở `src` không tự áp dụng cho Javadoc output.

**Cách sửa:** truyền đúng option khi gọi `javadoc`, kiểm tra HTML links và generated assets.

### Lỗi 7 — Browser vẫn hiển thị theme cũ

Có thể do cache, mở nhầm folder `out/default` thay vì `out/branded`, hoặc công cụ build chưa chạy lại.

**Cách sửa:** hard refresh, xem Network/Computed, kiểm tra output path và timestamp/size CSS.

### Lỗi 8 — Lạm dụng `!important` để ép mọi màu

Có thể phá trạng thái selected, focus, nav links hoặc contrast.

**Cách sửa:** dùng CSS variables hoặc selector đúng mục tiêu, kiểm tra accessibility.

### Lỗi 9 — Quên copy font/ảnh được CSS tham chiếu

CSS có `url("../images/logo.svg")` hoặc font ngoài nhưng publish chỉ HTML/CSS. Trình duyệt báo 404.

**Cách sửa:** quản lý assets cùng đường dẫn hợp lệ trong output/deployment; xem browser Network và quy trình package.

### Lỗi 10 — Styling xấu khi đổi phiên bản JDK

Build Javadoc thay đổi HTML/CSS structure hoặc variables, trong khi custom main CSS bị đóng băng.

**Cách sửa:** cố định JDK version cho việc sinh tài liệu và có regression testing khi nâng JDK.

### Lỗi 11 — Nhầm `-stylesheetfile` là cách duy nhất

Trên JDK mới, `--main-stylesheet` là dạng được ưu tiên. Alias cũ vẫn được manual mô tả nhưng tên dài dễ đọc hơn.

### Lỗi 12 — Cố tạo runtime theme switch bằng main stylesheet

`--main-stylesheet` là **tùy chọn lúc sinh tài liệu**, không phải một runtime Java API cho người dùng cuối đổi theme.

**Cách sửa:** muốn nhiều themes hoặc dark mode theo người dùng cần thiết kế CSS/browser riêng và test trên Javadoc output; đừng kỳ vọng option CLI tự cung cấp nút chuyển theme.

### Lỗi 13 — Chỉ xem `index.html`

Trang class và method detail có nhiều bảng, code blocks, navigation controls khác trang index. Thiếu CSS có thể không lộ trên index.

### Lỗi 14 — Chỉnh stylesheet trong output sau mỗi lần build

Lần sinh Javadoc kế tiếp có thể **ghi đè những thay đổi thủ công**.

**Cách sửa:** lưu CSS source trong version control và đưa `--main-stylesheet` vào build configuration.

### Lỗi 15 — Quên đối chiếu CSS file thực được HTML dùng

Chỉ vì lệnh có option không đủ chứng minh đúng CSS: cần inspect thẻ link/Network/Computed.

### Lỗi 16 — Dùng CSS ngoài từ nguồn không kiểm soát

`@import`, remote fonts hoặc background URLs có thể làm tài liệu phụ thuộc mạng ngoài hoặc tạo request ngoài ý muốn, ảnh hưởng privacy/security.

**Cách sửa:** review CSS và asset URLs, hạn chế tài nguyên từ domain không được phê duyệt.

## 13. Accessibility và chất lượng giao diện

Theme API documentation không chỉ cần “đẹp”. Các trang Javadoc thường được đọc trong thời gian dài, tìm kiếm nhanh và dùng bằng bàn phím.

### Độ tương phản màu

Kiểm tra:
- Body text trên background.
- Links bình thường, hover, focus.
- Navbar text và tab selected.
- Disabled/inactive labels.
- Code syntax hoặc các blocks.
- Table header và alternating row backgrounds.

Nếu đặt màu links rất nhạt trên nền sáng, người dùng khó đọc. **Đừng đánh giá contrast bằng cảm giác**, nên dùng công cụ kiểm tra theo WCAG hiện hành.

### Focus, keyboard và search

Không xóa `outline` hoặc các focus indicators mà không thay bằng thiết kế tương đương. Cần test:
- Tab navigation qua links/controls.
- Search input.
- Filter/sort tabs nếu có.
- Skip navigation hoặc các cơ chế trợ năng do doclet tạo.
- Keyboard activation.

### Responsive design

Trang method signatures có thể dài. Stylesheet cần:
- Không làm bảng vỡ ở viewport nhỏ.
- Giữ chiều rộng và wrapping hợp lý.
- Không ẩn nội dung quan trọng khi zoom.
- Không đặt kích cỡ font quá nhỏ hoặc khoảng cách quá chật.

### Print styles và color preferences

Nếu documentation được in/xuất PDF qua browser, kiểm tra print preview. Đừng tự đặt dark theme thuần túy mà bỏ qua print styles nếu đối tượng người đọc cần in.

Khi dùng CSS media queries như `prefers-color-scheme`, hãy kiểm tra cả light/dark, không làm mất contrast và không coi theme theo OS là tính năng `javadoc --main-stylesheet` tự cung cấp.

## 14. An toàn và bảo mật khi phát hành Javadoc đã tùy biến

### 14.1. Tài liệu và stylesheets là artifacts phải quản lý

Một CSS file có thể chứa:
- `@import` tới domain bên ngoài.
- `url(...)` tải hình/font ngoài.
- Dữ liệu URL vô tình chứa token hoặc thông tin nội bộ.
- CSS rules ẩn nội dung mà reviewer vẫn tưởng tài liệu đã an toàn.

**Không đưa secrets vào CSS URLs hoặc generated Javadoc**. Nếu tài liệu công khai, review các URLs và assets trước publish; nếu tài liệu nội bộ, bảo vệ đường dẫn truy cập và artifact pipeline.

### 14.2. CSS không thay thế cơ chế kiểm soát công khai API

`--main-stylesheet` không quyết định class/method nào được đưa vào docs. **Không dùng `display: none` để “ẩn” API nhạy cảm**: nội dung vẫn có thể tồn tại trong HTML và được tìm thấy bằng source hoặc search index.

Muốn kiểm soát phạm vi docs, dùng cấu hình Javadoc thích hợp và thiết kế API/publication policy, không dựa vào CSS.

### 14.3. Không lạm dụng script hoặc CSS hack

Standard doclet có những cơ chế riêng cho scripts/CSS, nhưng thêm script không đáng tin có thể gây rủi ro XSS/privacy hoặc phá UI. Với yêu cầu đổi màu/font, **CSS bổ sung là đủ**, không cần JavaScript.

### 14.4. Triển khai tĩnh đúng cách

Generated Javadoc có thể được host như static files; cần:
- Giữ đầy đủ HTML/CSS/scripts/assets tương ứng.
- Phục vụ đúng MIME types khi triển khai qua web server.
- Kiểm tra CSP/cache policy nếu có.
- Không đưa tệp nguồn chưa review vào public artifact.
- Có versioning và rollback của docs.

## 15. Tích hợp với CI/build tools

Nhiều dự án dùng **Maven Javadoc Plugin**, **Gradle Javadoc task** hoặc pipeline tùy chỉnh thay vì tự chạy `javadoc` trong terminal. Điểm bất biến là **standard doclet cần nhận đúng option và CSS input**.

### Dùng CLI trong CI

Một pipeline đơn giản có thể:

~~~bash
java --version
javadoc --version
javadoc -encoding UTF-8 -d out/default -sourcepath src demo.docs
javadoc -encoding UTF-8 -d out/branded --main-stylesheet styles/brand-main.css -sourcepath src demo.docs
~~~

Nếu CSS chính được sao chép từ default Javadoc ở build trước, đảm bảo bước chuẩn bị CSS diễn ra **trước** khi dùng nó. Một workflow ổn định hơn là lưu **bản custom main CSS đã review** trong repository, và update khi nâng JDK/doclet.

### Với Maven/Gradle

Không copy ngẫu nhiên một thuộc tính plugin từ bài viết cũ. Plugin versions và cấu hình API thay đổi theo thời gian. Hãy:
- Xác định plugin/toolchain đang chạy `javadoc` của JDK nào.
- Truyền option **`--main-stylesheet`** vào standard doclet theo cơ chế plugin đó hỗ trợ.
- Lưu CSS trong repository/config path ổn định.
- Kiểm tra command line thực tế và generated HTML.
- Pin Java toolchain/plugin version phù hợp và kiểm thử lại khi nâng cấp.

**Một build thành công không có nghĩa CSS đã được áp dụng**. Hãy thêm bước kiểm tra artifact có link CSS và smoke test giao diện.

### Tính tái lập

Ghi lại trong báo cáo build:
- JDK vendor/version/build dùng để sinh docs.
- Phiên bản plugin Maven/Gradle hoặc script.
- Hash/commit của CSS source.
- Đường dẫn `-d`, `--main-stylesheet` và các stylesheet bổ sung.
- Các options quan trọng của standard doclet.
- Kết quả kiểm tra links/assets/HTML.
- Những khác biệt có chủ đích so với default.

Khi nâng JDK:
1. Sinh docs mặc định bằng JDK mới.
2. So sánh stylesheet/classes/variables mới với custom main CSS cũ.
3. Cập nhật theme.
4. Chạy HTML/accessibility/visual tests.
5. Giữ phương án rollback nếu website bị regression.

## 16. Checklist từng bước trước khi publish

1. Đúng **JDK và standard doclet** chưa?
2. CSS `--main-stylesheet` có tồn tại, UTF-8 và được đọc đúng không?
3. Path được resolve đúng theo working directory của build?
4. Nếu chỉ cần overrides, đã cân nhắc `--add-stylesheet` chưa?
5. Nếu thay main CSS, đã bắt đầu từ stylesheet mặc định **cùng JDK build** chưa?
6. CSS variables/selectors có thực sự được default theme của bản JDK này hỗ trợ?
7. Generated HTML và CSS có được đặt trong `-d` đúng nơi không?
8. Tệp CSS mà HTML link tới có tồn tại và được publish không?
9. Browser Network có CSS/font/image 404 không?
10. Computed styles có phản ánh màu/font dự kiến không?
11. Package page, class page, method summary/detail có hiển thị đúng?
12. Navbar, search, tabs, links có dùng được?
13. Light/dark (nếu có), mobile và zoom 200% có đọc tốt?
14. Keyboard focus và color contrast có đạt tiêu chí accessibility?
15. Print preview có hợp lý?
16. CI có tái tạo được tài liệu từ source CSS, không sửa tay trong output?
17. Khi nâng JDK, có visual regression test cho theme?
18. Có quản lý remote CSS/assets, security và privacy?
19. Có test links/JS assets và định dạng output?
20. Có rollback hoặc giữ artifact docs phiên bản trước?

## 17. Hỏi đáp ngắn

**Câu 1. `--main-stylesheet` có tác dụng gì?**  
Nó chỉ định file CSS **thay thế stylesheet mặc định** cho HTML được sinh bởi Javadoc standard doclet.

**Câu 2. Không truyền option thì sao?**  
Standard doclet tự sinh và sử dụng CSS mặc định của bản JDK đang chạy.

**Câu 3. `--add-stylesheet` có giống `--main-stylesheet` không?**  
Không. Nó thêm CSS trên nền stylesheet mặc định, phù hợp overrides chọn lọc.

**Câu 4. Chỉ đổi màu nền thì nên dùng gì?**  
Thường dùng **`--add-stylesheet`**, vì không phải sao chép và bảo trì toàn bộ CSS nền.

**Câu 5. Nếu bắt buộc thay stylesheet chính, bắt đầu từ đâu?**  
Sinh Javadoc mặc định bằng đúng JDK build, sao chép default `stylesheet.css` rồi chỉnh một cách có kiểm soát.

**Câu 6. CSS file bắt buộc tên `stylesheet.css` không?**  
Không. `--main-stylesheet` nhận một path tới stylesheet file với tên do bạn chọn.

**Câu 7. `-stylesheetfile` có bị xóa khỏi JDK hiện đại không?**  
Tài liệu Oracle JDK 25 vẫn ghi nhận nó như dạng thay thế; **`--main-stylesheet` được ưu tiên dùng**.

**Câu 8. Có thể dùng `:root` variables để đổi màu không?**  
Có trên các theme Javadoc hiện đại dùng chúng. Nhưng phải kiểm tra tên biến và phiên bản default stylesheet cụ thể.

**Câu 9. Vì sao CSS chỉ có vài dòng làm mất bố cục?**  
Vì với `--main-stylesheet`, CSS mặc định đã bị thay thế; file ít rules không còn đủ CSS cho navbar/tables/layout.

**Câu 10. CSS có tác động tới file .class hoặc logic Java không?**  
Không. Nó ảnh hưởng generated documentation assets và browser rendering.

**Câu 11. CSS của JDK 17 có luôn dùng tốt cho JDK 25 không?**  
Không được bảo đảm. HTML structure/selectors/variables có thể thay đổi khi standard doclet cải tiến.

**Câu 12. Có cần mở trang class để test không?**  
Có. `index.html` có thể đơn giản hơn class/method documentation.

**Câu 13. CSS được truyền theo path nguồn hay path output?**  
Option nhận path CSS **đầu vào**; doclet sinh/copy tài nguyên cho output. Luôn kiểm tra link trong HTML output.

**Câu 14. `--main-stylesheet` có tự tạo dark mode switch không?**  
Không. Muốn runtime switch theo browser hoặc theme cần thiết kế CSS/UI riêng.

**Câu 15. Có thể chỉ dùng CSS ẩn API nhạy cảm khỏi docs không?**  
Không an toàn. HTML/source/index có thể vẫn chứa API đó; phải dùng cơ chế lọc publication.

**Câu 16. Vì sao màu links vẫn không đổi dù CSS đã được nạp?**  
Có thể selector specificity, order, CSS variable không được theme dùng hoặc cache. Kiểm tra DevTools Computed/Network.

**Câu 17. Javadoc đã chạy thành công có đảm bảo không có lỗi giao diện?**  
Không. Cần inspect HTML assets, visual QA và accessibility test.

**Câu 18. Dùng Maven hoặc Gradle có làm thay đổi ý nghĩa option không?**  
Không thay đổi định nghĩa của standard doclet, nhưng cách plugin truyền option và đường dẫn CSS phải đúng phiên bản cấu hình build.

## 18. Tổng kết

- **`--main-stylesheet`** của Javadoc standard doclet **thay thế CSS mặc định** bằng stylesheet do bạn cung cấp. Đây là tính năng đã có ở Java 10 và vẫn được tài liệu hóa ở JDK hiện đại.
- **`--add-stylesheet`** giữ CSS mặc định và nạp thêm CSS để override, thường phù hợp hơn khi chỉ đổi vài thuộc tính.
- **`-stylesheetfile`** là dạng tương đương còn được manual nhắc, nhưng **`--main-stylesheet`** là dạng được ưu tiên.
- Nếu thay main CSS, **bắt đầu từ stylesheet mặc định của đúng JDK build**, không viết một file tối giản rồi mong toàn bộ Javadoc UI vẫn hoạt động.
- Với JDK mới, nhiều thay đổi màu/font có thể thực hiện qua **CSS custom properties** như `--body-background-color`, `--link-color`; cần kiểm tra phiên bản theme tương ứng.
- Tạo một ví dụ Java đầy đủ, sinh default docs, copy CSS nền, chỉnh CSS, sinh branded docs và kiểm tra **generated HTML, asset links, browser rendering**.
- Styling không ảnh hưởng Java code/bytecode, không bảo vệ API nhạy cảm và không tự tạo chức năng chuyển theme lúc runtime.
- Khi phát hành, kiểm tra **contrast, keyboard focus, responsiveness, print, CSS assets, security** và tái kiểm thử mỗi khi nâng JDK.
- Với CI/production, lưu CSS source, cố định toolchain, review khác biệt với default và luôn có kế hoạch rollback.

**Tài liệu chính thức, còn áp dụng:**
- [Oracle Java SE 10 — javadoc tool, `--main-stylesheet` và `--add-stylesheet`](https://docs.oracle.com/javase/10/tools/javadoc.htm).
- [Oracle Java SE 17 — The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html).
- [Oracle Java SE 25 — The javadoc Command: main stylesheet và additional stylesheets](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html).
- [Oracle Java SE 25 — JavaDoc CSS Themes Guide](https://docs.oracle.com/en/java/javase/25/javadoc/javadoc-css-themes.html).
- [Oracle Java SE 21 — Programmer’s Guide to JavaDoc CSS Themes](https://docs.oracle.com/en/java/javase/21/javadoc/javadoc-css-themes.html).
- [Dev.java — Javadoc, the Documentation Generator](https://dev.java/learn/jvm/core-tools/javadoc/).
