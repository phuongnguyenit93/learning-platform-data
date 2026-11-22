# Javadoc `--add-stylesheet` và nhiều tệp CSS bổ sung (Java 10+)

## 1. Mục tiêu bài học

Khi dùng `javadoc` để sinh tài liệu API HTML, bạn có thể muốn đưa màu sắc thương hiệu, thay kiểu gạch chân liên kết hoặc định dạng cho bản in mà **không phải thay thế toàn bộ giao diện mặc định**. Từ **JDK 10**, standard doclet hỗ trợ tùy chọn **`--add-stylesheet`**, cho phép thêm nhiều tệp CSS bổ sung.

Cách dùng quan trọng nhất:

~~~bash
javadoc -d docs --add-stylesheet styles/brand.css --add-stylesheet styles/print.css src/com/example/api/Greeting.java
~~~

**Ba ý cần nhớ:**

1. `--add-stylesheet <file>` **bổ sung** CSS vào tài liệu do Javadoc tạo, không tự thay `stylesheet.css` mặc định.
2. Muốn thêm hai hay nhiều tệp, **lặp lại cả option** `--add-stylesheet` cho mỗi tệp.
3. Các stylesheet tương tác theo **CSS cascade**. Khi các khai báo có mức ưu tiên tương đương, thứ tự nạp có thể quyết định kết quả.

Bài tập trung vào Javadoc **standard doclet** trên các JDK còn áp dụng ngày nay, có ví dụ Java 10 được biên dịch bằng JDK 24, hai CSS riêng, output HTML đã kiểm tra, tình huống lỗi và hướng tích hợp build.

**Không nhầm** đây là một Java annotation, JavaFX CSS, runtime feature, hoặc API để thay đổi UI của ứng dụng Java. Nó chỉ ảnh hưởng **tài liệu HTML được Javadoc sinh ra**.

## 2. Nguồn gốc Java 10 và tính hiện hành

Oracle JDK 10 release notes ghi rõ **Javadoc Support for Multiple Stylesheets**: `--add-stylesheet` được bổ sung vào công cụ `javadoc` để có thể thêm nhiều stylesheets. Tên `--main-stylesheet` cũng xuất hiện để phân biệt **thay main stylesheet** với **bổ sung stylesheet**.

Trong **Java SE 26**, tài liệu `The javadoc Command` vẫn mô tả `--add-stylesheet` dùng được **một hoặc nhiều lần**. Oracle JavaDoc CSS Themes Guide hiện hành cũng khuyến nghị **thêm stylesheet** khi chỉ cần điều chỉnh nhỏ, bởi default stylesheet đã xử lý nhiều vấn đề về layout và accessibility.

Điều này có nghĩa tính năng **không bị bỏ sau Java 10**. Đã kiểm thử Javadoc **24.0.2**, trong khi tài liệu Java SE 26 xác nhận option vẫn được hỗ trợ.

### Compiler JDK và source release khác nhau

Ví dụ:

~~~bash
javadoc --release 10 -d docs --add-stylesheet styles/brand.css src/com/example/api/Greeting.java
~~~

- **JDK chứa `javadoc`** quyết định cách standard doclet tạo HTML, CSS và resource folders.
- **`--release 10`** yêu cầu kiểm tra source và các platform APIs theo Java 10, nếu compiler/Javadoc tool hỗ trợ release đó.
- Cùng một mã Java 10, HTML do Javadoc của JDK 24 sinh ra có thể khác HTML từ một JDK khác.

Vì vậy **không được xem tên CSS classes/DOM của Javadoc là một API HTML bất biến qua mọi JDK**. Kiểm thử CSS lại khi đổi JDK dùng trong build pipeline.

## 3. Standard doclet và default CSS

`javadoc` đọc khai báo Java, documentation comments `/** ... */` và những tags như `@param`, `@return`, `@since` để tạo HTML API docs. Nếu không cấu hình doclet khác, nó dùng **standard doclet**.

Output của một dự án có thể có:

~~~text
docs/
├── index.html
├── allclasses-index.html
├── allpackages-index.html
├── com/example/api/Greeting.html
├── com/example/api/package-summary.html
└── resource-files/
    ├── stylesheet.css
    ├── brand.css
    └── print.css
~~~

Đây là **cấu trúc minh họa dựa trên output JDK 24 đã kiểm thử**, không phải cam kết mọi JDK và custom doclet luôn dùng đúng các đường dẫn đó.

Default `stylesheet.css` xử lý typography, navigation, tables, code snippets, sections và nhiều thành phần khác. **Không nên copy main CSS từ JDK cũ để thay toàn bộ giao diện ở JDK mới** nếu chỉ cần đổi một số thuộc tính. Cách bảo trì an toàn hơn là **CSS bổ sung nhỏ, scoped rõ ràng**.

## 4. Cú pháp nhiều CSS

Cú pháp:

~~~text
javadoc --add-stylesheet <CSS_1> --add-stylesheet <CSS_2> ... <JAVA_SOURCES_OR_PACKAGES>
~~~

Ví dụ:

~~~bash
javadoc -d docs --add-stylesheet styles/brand.css --add-stylesheet styles/print.css src/com/example/api/Greeting.java
~~~

- `-d docs` chọn thư mục output.
- `--add-stylesheet styles/brand.css` chỉ định CSS số một.
- `--add-stylesheet styles/print.css` chỉ định CSS số hai.
- Tham số cuối là Java source được document.

**Không dùng dấu phẩy như một danh sách tự động tách**:

~~~text
--add-stylesheet styles/brand.css,styles/print.css
~~~

vì đây không phải cú pháp Oracle mô tả để nhận hai tệp. Cũng không bỏ option trước file thứ hai rồi kỳ vọng công cụ luôn hiểu đó là CSS:

~~~text
--add-stylesheet styles/brand.css styles/print.css
~~~

Để rõ ràng và dùng được trên các phiên bản hỗ trợ, hãy **lặp option đầy đủ**.

### Khi path có dấu cách

Sử dụng dấu nháy theo shell:

~~~bash
javadoc -d docs --add-stylesheet "styles/brand theme.css" --add-stylesheet "styles/print theme.css" src/com/example/api/Greeting.java
~~~

Lệnh này chỉ chạy khi các file theo đúng tên ví dụ tồn tại. Path có thể là tương đối theo working directory hoặc absolute path.

## 5. `--add-stylesheet` khác `--main-stylesheet` như thế nào?

| Option | Ý nghĩa | CSS mặc định còn dùng? | Khi nên dùng |
| --- | --- | --- | --- |
| `--add-stylesheet file.css` | **Bổ sung** một stylesheet | Có, trừ khi main bị thay bởi option khác | Đổi vài style nhỏ |
| Hai hoặc nhiều `--add-stylesheet` | Bổ sung nhiều CSS | Có | Brand + print + typography |
| `--main-stylesheet file.css` | **Thay thế** main stylesheet | Default main không được dùng | Chủ động thiết kế cả theme |
| `-stylesheetfile file.css` | Một tên vẫn được tài liệu Java SE 26 hỗ trợ cho main stylesheet | Tương đương thay main | Ưu tiên tên rõ nghĩa `--main-stylesheet` trong cấu hình mới |

**Chỉnh sửa nhỏ:** ưu tiên `--add-stylesheet` vì default CSS giữ lại giao diện phức tạp mà standard doclet đang cần.

**Muốn thay cả giao diện:** `--main-stylesheet` có thể dùng nhưng phải chịu trách nhiệm cho tất cả typography, navigation, layout, responsive và accessibility.

Hai option có thể kết hợp:

~~~bash
javadoc -d docs-custom --main-stylesheet styles/main-theme.css --add-stylesheet styles/brand.css src/com/example/api/Greeting.java
~~~

Trong thí nghiệm JDK 24, output trên dùng `main-theme.css` như stylesheet chính và thêm `brand.css` sau nó; `stylesheet.css` mặc định không còn là main CSS. **Một file main-theme.css chỉ có vài rule không đủ làm theme production hoàn chỉnh**.

## 6. Thư mục ví dụ hoàn chỉnh

Tạo các đường dẫn:

~~~text
javadoc-css-demo/
├── src/
│   └── com/
│       └── example/
│           └── api/
│               └── Greeting.java
├── styles/
│   ├── brand.css
│   └── print.css
├── out10/       (tạo khi chạy javac)
└── docs/        (tạo khi chạy javadoc)
~~~

Các tệp sau là nội dung hoàn chỉnh của lab. **Không bắt buộc tạo một dự án Maven/Gradle** để sử dụng option: một Java source file và hai CSS đã đủ.

## 7. Java source: `src/com/example/api/Greeting.java`

~~~java
package com.example.api;

/**
 * A small greeting API with documented methods.
 *
 * @since 10
 */
public final class Greeting {
    private Greeting() {
    }

    /**
     * Creates a greeting.
     *
     * @param name recipient name
     * @return a greeting message
     */
    public static String hello(String name) {
        var prefix = "Hello, ";
        return prefix + name;
    }

    /**
     * Runs the demo.
     *
     * @param args command line arguments, unused
     */
    public static void main(String[] args) {
        System.out.println(hello("Java 10"));
    }
}
~~~

Giải thích:

- `@since 10` là thông tin tác giả khai báo về mốc API, không tự buộc runtime Java 10.
- `@param` và `@return` sinh phần mô tả method trên Javadoc page.
- `var` là local-variable type inference được Java 10 bổ sung; compiler suy ra kiểu tĩnh `String`.
- `main` giúp chạy kiểm chứng output của source; **không cần main để sinh Javadoc**.

## 8. CSS bổ sung thứ nhất: `styles/brand.css`

~~~css
/* Brand: small visual changes without replacing the default theme. */
body {
    letter-spacing: 0.01em;
}

a {
    text-decoration-thickness: 2px;
}
~~~

File này bổ sung typography nhỏ và định dạng link. Nó **không chứa toàn bộ CSS** của Javadoc, vì default stylesheet tiếp tục được dùng.

**Lưu ý:** nếu default CSS có selector specificity cao hơn cho một loại link, hoặc browser không dùng underline trong trạng thái hiện tại, CSS trên không bảo đảm mọi link hiển thị dưới đúng dạng 2px. Hãy dùng **Computed Styles/Developer Tools** để kiểm tra.

## 9. CSS bổ sung thứ hai: `styles/print.css`

~~~css
/* Print-specific rules and a later link rule. */
@media print {
    nav {
        display: none;
    }
}

a {
    text-decoration-thickness: 1px;
}
~~~

- `@media print` giới hạn phần ẩn `nav` khi in/print preview, không ẩn trên màn hình thông thường.
- Quy tắc `a` có cùng selector với CSS thứ nhất nhưng đặt thuộc tính 1px.

Nếu cả hai khai báo đều có thể áp dụng và các yếu tố CSS cascade khác tương đương, **rule ở file được nạp sau** ưu tiên cho cùng thuộc tính. Điều đó giúp hiểu vì sao thứ tự ``--add-stylesheet` có ý nghĩa.

Không dùng CSS để ẩn thông tin API thiết yếu hoặc outline focus của keyboard users. Khi tùy biến màu, cần kiểm tra contrast ở light/dark theme.

## 10. Compile và chạy ví dụ Java 10

Từ thư mục project, tạo output:

~~~bash
mkdir out10
~~~

Biên dịch bằng một JDK compiler còn hỗ trợ release 10:

~~~bash
javac --release 10 -encoding UTF-8 -d out10 src/com/example/api/Greeting.java
~~~

Chạy:

~~~bash
java -cp out10 com.example.api.Greeting
~~~

**Stdout đã kiểm thử trên JDK 24.0.2:**

~~~text
Hello, Java 10
~~~

`javac --release 10` kiểm tra Java 10 source language, target bytecode và platform APIs trong phạm vi tool hỗ trợ. **Bài lab thực thi bằng JDK 24, không phải bằng JVM Java 10 cũ**. Trong mục tiêu ứng dụng mới, nên dùng runtime có cập nhật bảo mật; Java 10 được dùng ở đây để giải thích nguồn gốc tính năng và cách document source tương thích.

`javadoc` có thể tạo tài liệu trực tiếp từ Java source; **không cần chạy `javac` trước** chỉ để document ví dụ này. Bước compile ở đây là phép kiểm thử độc lập rằng mã Java thực sự hợp lệ.

## 11. Lệnh Javadoc đã kiểm thử với hai CSS

Chạy trong thư mục project:

~~~bash
javadoc --release 10 -quiet -encoding UTF-8 -docencoding UTF-8 -d docs --add-stylesheet styles/brand.css --add-stylesheet styles/print.css src/com/example/api/Greeting.java
~~~

| Tham số | Vai trò |
| --- | --- |
| `--release 10` | Kiểm tra source/API theo release Java 10 |
| `-quiet` | Giảm thông báo thông thường, không bỏ qua warnings/errors |
| `-encoding UTF-8` | Source encoding |
| `-docencoding UTF-8` | Generated HTML encoding |
| `-d docs` | Thư mục tài liệu |
| `--add-stylesheet styles/brand.css` | Thêm CSS thương hiệu |
| `--add-stylesheet styles/print.css` | Thêm CSS thứ hai |
| `src/.../Greeting.java` | Java source file |

**Kết quả thực nghiệm:** `javadoc 24.0.2` trả **exit code 0**, có class page và các stylesheet được tạo/copy vào output.

Không khẳng định `javadoc -quiet` phải in một dòng stdout đặc biệt khi thành công. **Điều xác định** là exit code và sự tồn tại/nội dung của HTML/CSS.

## 12. Xác minh CSS có thực sự được đưa vào HTML

Trong lab JDK 24, thư mục `docs/resource-files/` chứa:

~~~text
stylesheet.css
brand.css
print.css
jquery-ui.min.css
... các tài nguyên khác
~~~

**Đã kiểm tra byte-for-byte:** `brand.css` và `print.css` trong output **giống hệt** hai file nguồn.

Trong `docs/com/example/api/Greeting.html`, các link đã quan sát:

~~~html
<link rel="stylesheet" type="text/css" href="../../../resource-files/jquery-ui.min.css" title="Style">
<link rel="stylesheet" type="text/css" href="../../../resource-files/stylesheet.css" title="Style">
<link rel="stylesheet" type="text/css" href="../../../resource-files/brand.css" title="Style">
<link rel="stylesheet" type="text/css" href="../../../resource-files/print.css" title="Style">
~~~

**Quan sát được:**

1. Default `stylesheet.css` vẫn có trong tài liệu.
2. `brand.css` và `print.css` nằm **sau** default CSS trong class page.
3. Thứ tự CSS bổ sung khớp thứ tự các lần chỉ định option.
4. Các URLs tương đối vì class page ở `com/example/api/`, thấp hơn `resource-files` ba cấp.

Đây là **kết quả JDK 24**. Tên resource khác như `jquery-ui.min.css`, cấu trúc thư mục hoặc relative paths **có thể thay đổi theo JDK/standard doclet**. Đừng hard-code đường dẫn do một release sinh ra vào build tool hoặc giả định mọi trang dùng đúng mẫu HTML trên.

**Đặc biệt:** một `index.html` có thể chỉ đóng vai trò entry point/redirect, nên **kiểm tra các trang nội dung thật** như class detail hoặc package summary khi xác nhận CSS links.

## 13. CSS cascade và thứ tự: hiểu đúng, tránh khẳng định tuyệt đối

Ví dụ:

**`brand.css`**

~~~css
a {
    text-decoration-thickness: 2px;
}
~~~

**`print.css`**

~~~css
a {
    text-decoration-thickness: 1px;
}
~~~

Nếu hai declarations cùng áp dụng cho một element, có **cùng origin, importance, layer và specificity** (và không có điều kiện cascade khác phân định), rule có **source order** phía sau thường thắng. Trong output đã kiểm thử, file `print.css` được link sau.

Nhưng **thứ tự file không tự thắng selector cụ thể hơn**:

~~~css
/* brand.css */
#main-content a {
    color: navy;
}

/* print.css */
a {
    color: teal;
}
~~~

Trong điều kiện hai selector cùng match và không có yếu tố cascade khác, `#main-content a` cụ thể hơn và có thể thắng dù file nằm trước.

Đừng lạm dụng `!important` để ép mọi thứ theo màu dự án. Hãy kiểm tra:

- **CSS origin và importance**.
- Cascade layers và những quy tắc có điều kiện.
- **Selector specificity**.
- **Source order**.
- Media query `@media`.
- Browser style computation.

Oracle JavaDoc CSS Themes Guide mô tả **CSS custom properties** để tùy biến theme. Đây thường là hướng tốt hơn việc copy toàn bộ `stylesheet.css`, nhưng tên selectors/custom properties phải được xem trong tài liệu và HTML/CSS thực tế của phiên JDK đang dùng.

## 14. Tùy biến main stylesheet: dùng đúng trách nhiệm

Nếu dùng:

~~~bash
javadoc -d docs-custom --main-stylesheet styles/main-theme.css --add-stylesheet styles/brand.css src/com/example/api/Greeting.java
~~~

trong JDK 24 lab đã xác minh:

- `docs-custom/resource-files/main-theme.css` được copy làm main stylesheet.
- `brand.css` được copy và link sau main.
- Default `stylesheet.css` **không** còn là main CSS.

**Không dùng một main stylesheet chỉ vài dòng cho tài liệu production**: Javadoc default CSS có nhiều style cho tabs, navigation, tables, method signatures và responsive layout. Thay main nghĩa là bạn cần xây dựng/duy trì phần còn thiếu, kiểm thử visual và accessibility.

Trong đa số trường hợp chỉ muốn thương hiệu, print và spacing, nên dùng **`--add-stylesheet`**.

## 15. Lỗi khi tệp CSS không tồn tại

Ví dụ:

~~~bash
javadoc -d docs --add-stylesheet styles/not-there.css src/com/example/api/Greeting.java
~~~

Khi path không tồn tại, Javadoc không thể đưa CSS đó vào output.

**JDK 24 thực nghiệm**: Javadoc trả **exit code 1** và diagnostic tương tự:

~~~text
error: File not found: .../notthere.css
~~~

Dấu `...` thay cho path cục bộ có thể khác từng máy. Không xem dòng đó là output path cố định.

Hướng xử lý:

1. Xem **working directory** của terminal/build.
2. Kiểm tra file được checkout/copied trước khi Javadoc chạy.
3. Dùng path tương đối đúng hoặc absolute path đã kiểm chứng.
4. Kiểm tra quyền đọc.
5. Cho CI fail khi Javadoc trả lỗi, không publish thư mục docs cũ.

**Không tạo một CSS rỗng để “sửa lỗi” khi sản phẩm thực sự cần một bộ theme bắt buộc**; hãy phục hồi CSS đúng nguồn.

## 16. Lỗi đặc biệt: hai CSS cùng tên ở hai thư mục

Giả sử:

~~~text
styles/brand/same.css
styles/print/same.css
~~~

Và chạy:

~~~bash
javadoc -d docs --add-stylesheet styles/brand/same.css --add-stylesheet styles/print/same.css src/com/example/api/Greeting.java
~~~

**Đã kiểm thử trên JDK 24:** command trả **exit code 0**, nhưng class page có **hai link tới cùng `resource-files/same.css`**, và tệp kết quả chứa **nội dung của file được xử lý sau**. Như vậy hai CSS đầu vào đã **không được xuất bản thành hai tài nguyên độc lập**, dù Javadoc báo thành công.

**Cách tránh:**

- Dùng basenames **khác nhau**: `brand.css`, `print.css`, `typography.css`.
- Không đặt hai stylesheet khác nội dung cùng tên file rồi dựa vào tên folder nguồn để phân biệt ở output.
- Kiểm tra HTML links **và file contents** sau build, không chỉ exit code.
- Nếu dùng Maven/Gradle, kiểm tra tên file thực tế sau plugin processing.

**Không coi hành vi ghi đè quan sát ở JDK 24 là đặc tả bắt buộc của JDK khác.** Naming convention riêng, không collision là cách an toàn lâu dài.

## 17. CSS tham chiếu images/fonts qua `url(...)`

Ví dụ:

~~~css
.api-note {
    background-image: url("images/note.svg");
}
~~~

Đây là **mảnh CSS minh họa**, không có `images/note.svg` trong lab chính.

Nếu stylesheet đã được copy vào:

~~~text
docs/resource-files/brand.css
~~~

thì URL tương đối `url("images/note.svg")` thường trỏ tới:

~~~text
docs/resource-files/images/note.svg
~~~

vì trình duyệt giải URL dựa trên vị trí **CSS trong output**, không dựa trên folder `styles/` của source.

**Không giả định `--add-stylesheet` tự động tìm/copy mọi ảnh, font hoặc tài nguyên được dẫn chiếu trong CSS.** Hãy copy đúng assets cùng với site được deploy, kiểm tra network responses và bảo đảm paths được bảo toàn.

Nên tránh stylesheet tải từ CDN không được kiểm soát hoặc CSS `@import` chỉ hoạt động khi có mạng. Nếu docs phải hoạt động offline, hãy dùng assets nội bộ và kiểm tra chế độ không kết nối.

## 18. Tích hợp Maven Javadoc Plugin hiện hành

Apache Maven Javadoc Plugin hỗ trợ **`addStylesheets`** từ phiên bản **3.3.0**, theo tài liệu Maven chính thức.

Bố trí ví dụ:

~~~text
project/
├── pom.xml
├── src/main/java/com/example/api/Greeting.java
└── src/main/javadoc/resources/
    ├── brand.css
    └── print.css
~~~

Đoạn **cấu hình để ghép vào `pom.xml`**:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.12.0</version>
      <configuration>
        <addStylesheets>
          <addStylesheet>resources/brand.css</addStylesheet>
          <addStylesheet>resources/print.css</addStylesheet>
        </addStylesheets>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

- Plugin nhận danh sách các tệp bổ sung, với path **tương đối với `javadocDirectory`** theo hướng dẫn plugin.
- `3.12.0` là phiên bản được tài liệu Maven đối chiếu trong bài, không phải yêu cầu phải giữ mãi một version cũ; cập nhật theo dự án và kiểm tra release/plugin docs hiện tại.
- Đây **không phải POM hoàn chỉnh**; vẫn cần thông tin project/group/artifact/version và cấu hình khác.
- Nếu chạy Maven với JDK khác terminal, hãy kiểm tra **Javadoc executable thực sự được gọi**.

**Đừng nhầm `addStylesheets` với `stylesheetfile` của Maven**: cái đầu **bổ sung**, còn cái sau yêu cầu thay main stylesheet.

## 19. Gradle và các build tools khác

Với Gradle `Javadoc` task, cần cấu hình sao cho command thực tế chứa hai cặp option:

~~~text
--add-stylesheet styles/brand.css
--add-stylesheet styles/print.css
~~~

**Chú ý API của Gradle:** các helpers kiểu `addStringOption(name, value)` có thể quản lý options theo **tên option**. Đừng mặc định gọi cùng helper hai lần với cùng tên `--add-stylesheet` sẽ tự append hai occurrences; trường hợp một cấu hình ghi đè cấu hình trước cần được xác minh trên Gradle version đang dùng.

Cách làm phù hợp:

1. Đọc tài liệu **Gradle Javadoc task/options** theo version dự án.
2. Chọn đường truyền repeated flags được hỗ trợ (hoặc Javadoc argument file nếu build tool truyền đúng).
3. In/inspect effective Javadoc command hoặc args/options file.
4. Kiểm tra HTML class page thực tế có **hai links riêng**.

Không cần tự chế một snippet Gradle không kiểm thử rồi coi đó là công thức đúng cho mọi bản Gradle. Điều quan trọng là **cả hai occurrences đi tới standard doclet** và artifacts output đúng.

## 20. Những kiểm tra nên đưa vào CI

Một pipeline tạo docs nên có các bước:

1. Xác định **JDK/Javadoc version** đang chạy.
2. Check Java source và CSS files đã được checkout.
3. Chạy `javadoc`, yêu cầu **exit code 0**.
4. Kiểm tra thư mục `docs/` mới có class/package HTML.
5. Kiểm tra `brand.css` và `print.css` được copy vào vị trí Javadoc sinh ra.
6. Kiểm tra source file contents hoặc hash khớp generated CSS nếu pipeline cần tính toàn vẹn.
7. Kiểm tra HTML class page có **default CSS** và **hai CSS bổ sung**.
8. Kiểm tra các CSS URL không bị trùng do collision basename.
9. Kiểm tra resources tham chiếu bằng `url(...)` không 404.
10. Thử **dark/light mode, print preview, mobile viewport, keyboard focus và zoom**.
11. Xuất bản toàn bộ docs assets; không chỉ copy HTML mà bỏ `resource-files`.
12. Khi nâng JDK, chạy visual regression tests vì DOM/CSS classes có thể thay đổi.

### Lệnh kiểm tra cơ bản

Trên Linux/macOS:

~~~bash
ls docs/resource-files
grep -n "resource-files/.*css" docs/com/example/api/Greeting.html
~~~

Trên PowerShell:

~~~powershell
Get-ChildItem docs/resource-files -Filter *.css
Select-String -Path docs/com/example/api/Greeting.html -Pattern "resource-files/.*css"
~~~

**Không kiểm tra duy nhất `docs/index.html`**: entry point có thể khác trang nội dung. Mở trực tiếp `docs/com/example/api/Greeting.html` hoặc trang package để xác minh.

## 21. CSS selectors, dark mode và accessibility

Các style classes và HTML structure có thể thay đổi theo Javadoc JDK release. Ví dụ:

~~~css
.my-project-banner {
    border-bottom: 2px solid currentColor;
}
~~~

Rule trên không có tác dụng nếu HTML không có element với class `my-project-banner`. File CSS được link thành công **không chứng minh selector đã match**.

Nên ưu tiên:

- Selectors/variables được **JavaDoc CSS Themes Guide** hỗ trợ cho JDK đang dùng.
- Overrides nhỏ, scope rõ và kiểm tra computed styles.
- Màu có contrast tốt, focus outline còn rõ, links nhận biết được không chỉ nhờ màu.
- Bảng và signatures không bị cắt ở màn hình hẹp.
- Dark/light theme có mức tương phản hợp lý.
- Print CSS không che khuất API content quan trọng.
- Bộ font có fallback để hiển thị tiếng Việt và Unicode.

**Không tắt cảnh báo browser hoặc CSP chỉ để CSS “trông đúng”**. Với asset từ nguồn ngoài, cần xét privacy/security, quyền sử dụng và việc trang documentation có thể được công khai.

## 22. Một số lỗi phổ biến

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `File not found` khi chạy Javadoc | CSS path không tồn tại | Kiểm tra cwd, file path, checkout |
| CSS có trong output nhưng style không đổi | Selector không match, specificity thấp | Inspect DOM/computed styles |
| CSS file tải thành công nhưng 404 ảnh | Relative `url(...)` sau khi copy CSS | Copy ảnh/font vào đúng output folder |
| Chỉ thấy một CSS | Build tool không truyền repeated option | Kiểm tra effective command và HTML |
| Hai CSS khác folder nhưng link trùng | Cùng basename ở output | Đặt tên riêng |
| Mất layout default | Dùng `--main-stylesheet` thiếu các rules | Dùng `--add-stylesheet` cho thay đổi nhỏ |
| Style khác trên JDK mới | Standard doclet HTML/CSS thay đổi | Review selectors và visual regression |
| Link màu không rõ trên dark mode | CSS hard-code màu chưa xét theme | Dùng variables và kiểm tra contrast |
| CSS chỉ áp dụng khi in | Rule nằm trong `@media print` | Đổi media nếu muốn cả màn hình |
| Build báo thành công nhưng docs vẫn cũ | Cache/publish sai artifact | Clean/rebuild đúng output và kiểm tra hash |
| Dự án Maven không lấy được CSS | Path không khớp javadocDirectory | Sửa cấu hình theo plugin docs |
| Nhiều options Gradle bị ghi đè | API cấu hình option theo key | Dùng repeated flags được hỗ trợ |
| CSS bị trình duyệt chặn | Content-Type, CSP, URL, server config | Sửa deployment và headers hợp lệ |

**Không sửa trực tiếp từng trang generated HTML sau mỗi lần build** nếu có thể sửa từ Javadoc options và CSS sources. Generated files sẽ bị ghi đè khi tạo tài liệu lại.

## 23. Bài tập tự kiểm tra

### Câu 1 — cú pháp đúng

**Hỏi:** Muốn thêm `brand.css` và `print.css` nhưng giữ default theme?

**Đáp án:** Dùng `--add-stylesheet brand.css --add-stylesheet print.css` (đúng paths thực tế).

### Câu 2 — thay main

**Hỏi:** `--main-stylesheet main.css` có tương đương `--add-stylesheet main.css` không?

**Đáp án:** Không. Tùy chọn thứ nhất **thay CSS chính**; tùy chọn thứ hai **bổ sung** CSS.

### Câu 3 — CSS cascade

**Hỏi:** Hai file cùng selector `a`, cùng thuộc tính và cùng độ ưu tiên, file nào thường thắng?

**Đáp án:** File xuất hiện **sau trong source order**, nếu tất cả yếu tố cascade khác tương đương.

### Câu 4 — specificity

**Hỏi:** File trước có `#main-content a` còn file sau chỉ có `a`. File sau luôn thắng không?

**Đáp án:** Không. Selector đầu cụ thể hơn và có thể thắng dù xuất hiện trước.

### Câu 5 — JDK 10 và JDK 26

**Hỏi:** `--add-stylesheet` chỉ tồn tại ở Java 10 và bị bỏ sau đó không?

**Đáp án:** Không. Nó được giới thiệu trong Java 10 và vẫn được tài liệu Java SE 26 hỗ trợ.

### Câu 6 — tên trùng

**Hỏi:** Có thể truyền `a/same.css` và `b/same.css` để dùng hai style riêng không?

**Đáp án:** Không an toàn. JDK 24 đã kiểm thử tạo hai links tới một output `same.css` và ghi đè một nội dung.

### Câu 7 — nguồn gốc asset

**Hỏi:** Sau khi Javadoc copy `styles/brand.css` vào `docs/resource-files/brand.css`, CSS `url("images/x.svg")` được giải tương đối ở đâu?

**Đáp án:** Tương đối với **vị trí CSS trong output**: `docs/resource-files/images/x.svg`.

### Câu 8 — compile và Javadoc

**Hỏi:** Có cần chạy `java com.example.api.Greeting` để Javadoc tạo HTML không?

**Đáp án:** Không. `javadoc` đọc Java source/comments; chạy main chỉ để kiểm thử chương trình.

### Câu 9 — kiểm tra HTML

**Hỏi:** Chỉ xem root `index.html` không thấy `brand.css` đã đủ kết luận Javadoc bỏ CSS không?

**Đáp án:** Không. Hãy kiểm tra class/package page và `resource-files/`.

### Câu 10 — Maven

**Hỏi:** Maven Javadoc Plugin cấu hình nhiều file bổ sung bằng thuộc tính gì?

**Đáp án:** `addStylesheets` gồm các `addStylesheet` entries (plugin 3.3.0+).

### Câu 11 — test runtime

**Hỏi:** Lệnh Java demo in gì?

**Đáp án:** `Hello, Java 10`, đã kiểm thử JDK 24. Đây là stdout của Java program, không phải Javadoc tool.

### Câu 12 — nâng JDK

**Hỏi:** Vì sao phải kiểm tra CSS khi nâng Javadoc JDK từ 17 lên 26 dù option vẫn giống nhau?

**Đáp án:** HTML/CSS structure của standard doclet có thể thay đổi, khiến selectors và layouts cần cập nhật.

## 24. Checklist áp dụng thực tế

- [ ] Dùng `javadoc` phiên bản JDK hiện hành và xác định đúng tool đang chạy.
- [ ] Nếu dùng `--release 10`, hiểu rằng nó ràng buộc Java source chứ không giữ nguyên layout Javadoc JDK 10.
- [ ] Dùng `--add-stylesheet` để tinh chỉnh, không tự thay main CSS không cần thiết.
- [ ] Lặp option một lần cho mỗi CSS.
- [ ] Mỗi CSS bổ sung có **basename riêng**.
- [ ] Các file tồn tại và accessible từ working directory của build.
- [ ] Đã kiểm tra `javadoc` exit code và generated class/package HTML.
- [ ] Default `stylesheet.css` vẫn được dùng khi không thay main.
- [ ] Các additional CSS links xuất hiện sau main CSS ở output được kiểm tra.
- [ ] Nội dung assets trong output giống đúng input.
- [ ] Selectors thật sự match và cascade như dự định.
- [ ] Không lạm dụng `!important` hoặc CSS phụ thuộc class không được document.
- [ ] Images/fonts tham chiếu bởi CSS được publish và không 404.
- [ ] Light/dark, responsive, keyboard focus, zoom và print view hợp lệ.
- [ ] Maven/Gradle truyền đủ repeated options và không âm thầm override.
- [ ] JDK upgrade có visual regression test.
- [ ] Không có dependencies CSS không đáng tin hoặc lộ internal URLs.
- [ ] Site docs được publish cùng toàn bộ `resource-files`.

## 25. Tổng kết và nguồn chính thức

**`--add-stylesheet` là tùy chọn Javadoc từ Java 10 và vẫn được dùng trong JDK hiện hành để thêm nhiều stylesheet vào API documentation.** Muốn thêm nhiều CSS, hãy **lặp lại option**. Khác với `--main-stylesheet`, kiểu bổ sung này **giữ CSS mặc định**, giúp giảm rủi ro phá giao diện.

Thực nghiệm JDK 24 xác nhận hai CSS được sao chép vào `resource-files` và HTML class page link theo thứ tự; file CSS thiếu làm build lỗi, còn CSS trùng basename có thể ghi đè mà không báo lỗi. Vì vậy cần kiểm tra **cả Javadoc exit code, generated links, nội dung assets và hình thức thực tế**.

### Tài liệu chính thức còn hiệu lực

1. [Oracle Java SE 26 — The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): `--add-stylesheet`, `--main-stylesheet`, `--release`, `-d` và encoding.
2. [Oracle Java SE 26 — JavaDoc CSS Themes Guide](https://docs.oracle.com/en/java/javase/26/javadoc/javadoc-guide.pdf): sử dụng CSS bổ sung, thay main stylesheet và custom properties.
3. [Oracle JDK 10 — Release Notes](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): giới thiệu hỗ trợ nhiều Javadoc stylesheets trong Java 10.
4. [Apache Maven Javadoc Plugin — Configuring Stylesheets](https://maven.apache.org/plugins/maven-javadoc-plugin/examples/stylesheet-configuration.html): khuyến nghị `addStylesheets` cho thay đổi nhỏ.
5. [Apache Maven Javadoc Plugin — javadoc goal](https://maven.apache.org/plugins/maven-javadoc-plugin/javadoc-mojo.html): `addStylesheets` từ 3.3.0 và paths theo javadocDirectory.
6. [Gradle — Javadoc Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html): Javadoc toolchain và options.
7. [Gradle — CoreJavadocOptions](https://docs.gradle.org/current/javadoc/org/gradle/external/javadoc/CoreJavadocOptions.html): lập cấu hình options cần kiểm tra repeated values.
8. [MDN — CSS cascade](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_cascade/Cascade): specificity, origin, importance, source order, media.
