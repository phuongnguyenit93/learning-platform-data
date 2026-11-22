# Javadoc task trong quy trình Build Integration

**Javadoc task** là bước trong build tạo tài liệu HTML cho API Java từ source code và documentation comments. Khi được tích hợp vào Gradle hoặc Maven, task này giúp nhóm phát hành tài liệu API cùng phiên bản phần mềm, kiểm tra chất lượng Javadoc tự động và đóng gói tài liệu để chia sẻ với người dùng thư viện.

Javadoc hữu ích khi phát triển library, SDK, framework hoặc bất kỳ module nào có API công khai. Một build có thể biên dịch và chạy test thành công nhưng vẫn tạo tài liệu API thiếu mô tả, liên kết hỏng hoặc HTML sai. Tích hợp Javadoc task vào CI giúp phát hiện những vấn đề này trước khi phát hành.

## 1. Javadoc tool và Javadoc task khác nhau thế nào?

**Javadoc tool** là chương trình `javadoc` đi kèm JDK. Nó đọc khai báo Java, documentation comments và các tùy chọn đầu vào, sau đó dùng doclet để tạo tài liệu. Standard doclet mặc định sinh HTML cho package, class, interface, constructor, method và field thuộc phạm vi được chọn.

**Javadoc task** là đơn vị công việc do build tool quản lý. Task này chọn source set, classpath, JDK tool, tùy chọn Javadoc, thư mục đầu ra và quan hệ phụ thuộc với các task khác.

| Thành phần | Vai trò |
| --- | --- |
| `javadoc` | Công cụ của JDK để tạo HTML API documentation |
| Standard doclet | Bộ xử lý mặc định tạo các trang HTML |
| Documentation comment | Nội dung mô tả API nằm trong source Java |
| DocLint | Kiểm tra cú pháp, HTML, tham chiếu và các vấn đề trong Javadoc |
| Gradle `Javadoc` task | Tích hợp việc tạo tài liệu vào Gradle build |
| Maven Javadoc Plugin | Cung cấp các goal Javadoc cho Maven |

Javadoc không thay thế compiler hoặc unit test. Nó kiểm tra và xuất tài liệu từ source; các lỗi compile, dependency hoặc test vẫn thuộc trách nhiệm của những bước build tương ứng.

## 2. Vòng đời tạo tài liệu

Một quy trình tạo Javadoc thường gồm các bước:

1. Chọn source files hoặc package cần tài liệu hóa.
2. Cung cấp classpath/module path để phân giải các kiểu được tham chiếu.
3. Đọc declaration và documentation comments.
4. Kiểm tra tag, link, HTML và các quy tắc DocLint.
5. Tạo trang cho package, class, member, hierarchy, index và search.
6. Ghi HTML, CSS, JavaScript và resource vào thư mục đích.
7. Tùy build, đóng gói tài liệu thành Javadoc JAR hoặc đưa vào site.

Sơ đồ:

```text
Java source + Javadoc comments
            |
            v
Build tool selects sources and classpath
            |
            v
Javadoc tool + Standard Doclet + DocLint
            |
            v
HTML API documentation
            |
            +----> build/docs/javadoc or target/reports/apidocs
            |
            v
Optional Javadoc JAR / published documentation
```

Mặc định, Javadoc thường mô tả public và protected API. Có thể thay đổi phạm vi bằng `-public`, `-protected`, `-package` hoặc `-private`. Với thư viện, hãy cân nhắc công bố API mà người dùng thực sự được phép sử dụng; tài liệu hóa toàn bộ implementation có thể làm lộ chi tiết nội bộ và tạo gánh nặng duy trì.

## 3. Viết documentation comments đúng cách

Javadoc comment bắt đầu bằng `/**` và kết thúc bằng `*/`. Comment nên đặt ngay trước declaration cần mô tả.

Ví dụ:

```java
package com.example.api;

/**
 * Creates greeting messages for callers of the public API.
 *
 * <p>See {@link String} for the text representation used by this class.
 *
 * @since 1.0
 */
public final class Greeting {
    private final String prefix;

    /**
     * Creates a greeting service.
     *
     * @param prefix non-null text placed before each name
     * @throws IllegalArgumentException if {@code prefix} is blank
     */
    public Greeting(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalArgumentException("prefix must not be blank");
        }
        this.prefix = prefix;
    }

    /**
     * Builds a greeting for the supplied name.
     *
     * @param name the name to greet
     * @return a greeting beginning with the configured prefix
     * @throws IllegalArgumentException if {@code name} is null or blank
     * @since 1.0
     */
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return prefix + ", " + name + "!";
    }
}
```

Một documentation comment tốt có:

- Câu đầu tiên tóm tắt hành vi để xuất hiện trong phần summary.
- Mô tả đầy đủ điều kiện đầu vào, kết quả, side effect và giới hạn.
- `@param` cho từng parameter.
- `@return` cho method có giá trị trả về.
- `@throws` cho exception có ý nghĩa với caller.
- `@since` cho phiên bản API được thêm vào.
- Link tới type hoặc method liên quan khi giúp người đọc hiểu nhanh.

Không chỉ chép lại tên method. Ví dụ `Gets the name` thường không hữu ích nếu tên method đã là `getName()`. Hãy mô tả contract mà người dùng API cần biết, bao gồm nullability, thứ tự, đơn vị, thread safety hoặc điều kiện lỗi khi có liên quan.

## 4. Các block tag và inline tag thường dùng

### Block tags

| Tag | Công dụng |
| --- | --- |
| `@param name description` | Mô tả parameter hoặc type parameter |
| `@return description` | Mô tả giá trị trả về |
| `@throws Type description` | Mô tả exception có thể được ném |
| `@since version` | Phiên bản API xuất hiện |
| `@deprecated description` | Cảnh báo API đã deprecated và gợi ý thay thế |
| `@see reference` | Thêm tham chiếu tới API hoặc tài liệu khác |
| `@author name` | Ghi tác giả khi dự án có chính sách sử dụng |
| `@version text` | Ghi phiên bản tài liệu nếu dự án cần |
| `@apiNote text` | Ghi chú dành cho người sử dụng API |
| `@implSpec text` | Mô tả yêu cầu/contract dành cho implementation |
| `@implNote text` | Ghi chú về cách triển khai cụ thể |

Ví dụ deprecated API:

```java
/**
 * Returns the old display label.
 *
 * @deprecated Use {@link #displayName()} instead.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String oldLabel() {
    return displayName();
}
```

Tag `@deprecated` mô tả lý do và hướng chuyển đổi; annotation `@Deprecated` đánh dấu API trong mã nguồn để compiler và IDE nhận biết. Nên giữ thông tin thay thế rõ ràng và đồng bộ giữa hai nơi.

### Inline tags

| Tag | Công dụng |
| --- | --- |
| `{@link Type#method()}` | Tạo liên kết có tên API làm nội dung |
| `{@linkplain Type#method()}` | Tạo liên kết trong văn bản thường |
| `{@code expression}` | Hiển thị code mà không diễn giải HTML |
| `{@literal text}` | Hiển thị ký tự nguyên văn |
| `{@inheritDoc}` | Kế thừa nội dung Javadoc từ declaration cha |
| `{@value}` | Hiển thị giá trị constant phù hợp |

Dùng `{@code}` cho tên class, method, biến và biểu thức. Dùng `{@link}` khi người đọc có thể muốn mở API được nhắc đến. Với generic hoặc biểu thức có dấu ngoặc nhọn, `{@code}` giúp tránh bị hiểu thành HTML.

## 5. Package documentation và module documentation

Có thể mô tả package bằng tệp `package-info.java`:

```java
/**
 * Public client APIs for the greeting service.
 *
 * <p>Types in this package are intended for application developers.
 */
package com.example.api;
```

Javadoc sẽ đưa mô tả package vào trang package summary.

Với project dùng Java modules, có thể đặt documentation comment trước khai báo `module` trong `module-info.java`:

```java
/**
 * Provides the greeting service API.
 */
module com.example.greeting {
    exports com.example.api;
}
```

Khi tạo tài liệu cho named modules, kiểm tra `--module`, `--module-path`, `--module-source-path` và chính sách export package. Tài liệu API của module thường tập trung vào các package được export; package nội bộ không nên trở thành contract công khai nếu không có chủ đích.

## 6. Chạy Javadoc trực tiếp bằng JDK

Có thể chạy Javadoc độc lập để kiểm tra source trước khi tích hợp build.

Ví dụ:

```bash
javadoc --release 17 -encoding UTF-8 -charset UTF-8 -docencoding UTF-8 -Xdoclint:all -Werror -link https://docs.oracle.com/en/java/javase/17/docs/api/ -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

Ý nghĩa các tùy chọn:

| Option | Vai trò |
| --- | --- |
| `--release 17` | Dùng API/platform phù hợp Java 17 khi xử lý source |
| `-encoding UTF-8` | Encoding của source files |
| `-charset UTF-8` | Charset khai báo trong HTML |
| `-docencoding UTF-8` | Encoding của HTML output |
| `-Xdoclint:all` | Bật các nhóm kiểm tra DocLint |
| `-Werror` | Biến warning thành lỗi |
| `-link URL` | Liên kết tới Javadoc bên ngoài |
| `-d directory` | Thư mục tạo HTML |
| `-sourcepath path` | Thư mục chứa source packages |
| `-subpackages name` | Tài liệu hóa package và các subpackage |

Với tài liệu có tiếng Việt, nên đặt encoding UTF-8 nhất quán cho source và output. Với API dùng type từ dependency bên ngoài, cung cấp classpath phù hợp để Javadoc có thể phân giải tham chiếu.

Có thể dùng danh sách source file trực tiếp thay cho `-subpackages`. Có thể dùng `-overview` để thêm trang giới thiệu, `-private` để đưa cả member private vào tài liệu hoặc `@files` để lưu danh sách tùy chọn trong một file.

### Liên kết Javadoc bên ngoài

`-link` tạo liên kết tới bộ tài liệu API đã được publish. Javadoc đọc `element-list` hoặc `package-list` từ URL đích để ánh xạ type.

Nếu build không có Internet, dùng `-linkoffline` và cung cấp thư mục chứa danh sách package/module tương ứng:

```bash
javadoc -linkoffline https://docs.oracle.com/en/java/javase/17/docs/api/ local-jdk17-docs -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

`local-jdk17-docs` phải chứa file danh sách mà Javadoc cần đọc. URL đầu tiên vẫn là URL sẽ được ghi vào các hyperlink trong HTML. Đảm bảo URL đích tồn tại và đúng phiên bản API mà project muốn tham chiếu.

## 7. DocLint và chất lượng tài liệu

DocLint kiểm tra những lỗi phổ biến trong documentation comments. Các nhóm kiểm tra gồm:

- `syntax`: cú pháp tag, dấu `<`, `>` và `&` không hợp lệ.
- `html`: cấu trúc HTML trong comment.
- `reference`: tham chiếu tới class, member hoặc tag không tồn tại.
- `accessibility`: vấn đề accessibility trong nội dung HTML như thiếu alt text.
- `missing`: comment hoặc tag cần thiết nhưng chưa được cung cấp.

Có thể bật rõ tất cả nhóm:

```bash
javadoc -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

`-Werror` khiến build thất bại nếu có warning. Điều này phù hợp với CI của thư viện có API ổn định. Khi mới bổ sung Javadoc cho codebase cũ, có thể bật DocLint trước để thống kê lỗi, sửa dần rồi bật `-Werror` làm quality gate.

Không nên tắt toàn bộ kiểm tra bằng `-Xdoclint:none` chỉ để build xanh. Nếu một nhóm kiểm tra không phù hợp với project, có thể loại trừ có chủ đích, ví dụ `-Xdoclint:all,-missing`, đồng thời giữ các kiểm tra cú pháp, HTML và reference.

DocLint không phải trình kiểm tra HTML toàn diện. Sau khi tạo docs, dự án vẫn có thể cần link checker, accessibility checker hoặc kiểm tra HTML đầu ra nếu yêu cầu chất lượng cao.

## 8. Tích hợp Javadoc task với Gradle

Khi áp dụng Java Plugin hoặc Java Library Plugin, Gradle tạo task `javadoc` kiểu `Javadoc` cho source set `main`. Task sử dụng source production và compile classpath của source set. Task mặc định tạo tài liệu trong `build/docs/javadoc`.

Cấu hình Groovy DSL:

```groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
    withJavadocJar()
}

tasks.named('javadoc', Javadoc) {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.source = '17'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
    options.links('https://docs.oracle.com/en/java/javase/17/docs/api/')
}
```

Chạy task:

```bash
./gradlew javadoc
```

Hoặc dùng Gradle đã cài:

```bash
gradle javadoc
```

Task `javadoc` phụ thuộc vào `classes`, do đó Gradle thực hiện các bước cần thiết trước khi tạo docs. Nếu task thành công, mở:

```text
build/docs/javadoc/index.html
```

`options.source = '17'` đặt mức source mà Javadoc chấp nhận trong Gradle. Để bảo đảm Javadoc dùng đúng platform API của phiên bản phát hành, nên chọn JDK toolchain tương ứng với target release. Với lệnh JDK trực tiếp hoặc Maven plugin có thể dùng `--release`/`release` để ràng buộc phiên bản API.

### Tạo Javadoc JAR bằng Gradle

Trong `java { ... }`, gọi:

```groovy
withJavadocJar()
```

Gradle đăng ký task `javadocJar` và tạo archive có classifier `javadoc`. Chạy:

```bash
./gradlew javadocJar
```

Archive thường nằm trong:

```text
build/libs/<project>-<version>-javadoc.jar
```

Javadoc variant được đăng ký cùng component Java. Khi sử dụng `maven-publish` hoặc `ivy-publish`, variant này có thể được đưa vào publication. Nhờ vậy, người dùng dependency có thể tải tài liệu API cùng binary artifact.

### Tạo task riêng cho test source

Khi cần tài liệu cho test utilities, có thể đăng ký task riêng:

```groovy
tasks.register('testJavadoc', Javadoc) {
    source = sourceSets.test.allJava
    classpath = sourceSets.test.compileClasspath
    destinationDirectory = layout.buildDirectory.dir('docs/testJavadoc')
}
```

Task tùy chỉnh cần chỉ rõ `source`; nếu không, nó không có source để tạo tài liệu. Cung cấp đúng classpath để tham chiếu tới test dependencies.

## 9. Tích hợp Javadoc với Maven

Maven dùng **Maven Javadoc Plugin** để chạy Javadoc tool. Nên khai báo version plugin tường minh để build có kết quả ổn định giữa các máy.

Ví dụ `pom.xml`:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>greeting-api</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-javadoc-plugin</artifactId>
        <version>3.12.0</version>
        <configuration>
          <release>17</release>
          <encoding>UTF-8</encoding>
          <charset>UTF-8</charset>
          <docencoding>UTF-8</docencoding>
          <failOnWarnings>true</failOnWarnings>
          <links>
            <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
          </links>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Các lệnh thường dùng:

```bash
mvn javadoc:javadoc
mvn javadoc:jar
```

| Maven goal | Kết quả |
| --- | --- |
| `javadoc:javadoc` | Tạo HTML API docs |
| `javadoc:jar` | Tạo docs và đóng gói thành Javadoc JAR |
| `javadoc:aggregate` | Tổng hợp Javadoc của nhiều module trong Maven reactor |
| `javadoc:aggregate-jar` | Tạo archive cho tài liệu aggregate |
| `javadoc:test-javadoc` | Tạo docs cho test source |

Với cấu hình thông thường, HTML nằm trong `target/reports/apidocs`. Javadoc JAR được tạo trong `target` với classifier `javadoc`, ví dụ `target/greeting-api-1.0.0-javadoc.jar`.

### Javadoc trong Maven Site

Nếu muốn tài liệu xuất hiện như một report trong `mvn site`, khai báo plugin trong phần `<reporting>`:

```xml
<reporting>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-javadoc-plugin</artifactId>
      <version>3.12.0</version>
    </plugin>
  </plugins>
</reporting>
```

`<build><plugins>` và `<reporting><plugins>` phục vụ hai mục tiêu cấu hình khác nhau. Phần build dùng khi gọi goal Javadoc trực tiếp; phần reporting tích hợp report vào Maven Site. Nếu cấu hình cả hai, cần hiểu rõ mỗi goal đang lấy cấu hình từ phần nào.

Đối với multi-module project, dùng `javadoc:aggregate` khi muốn một bộ tài liệu tổng hợp cho các module thay vì tạo các bộ HTML riêng lẻ.

## 10. Javadoc task trong CI/CD

Javadoc nên được kiểm tra trước khi đóng gói và publish library.

Một pipeline đơn giản có thể gồm:

1. Compile source.
2. Chạy unit tests.
3. Chạy Javadoc với DocLint.
4. Đóng gói binary JAR và Javadoc JAR.
5. Kiểm tra archive.
6. Publish artifacts.

Với Gradle:

```bash
./gradlew clean check javadoc javadocJar
```

Với Maven:

```bash
mvn clean verify javadoc:javadoc javadoc:jar
```

Lệnh trên minh họa các bước có thể chạy trong CI. Tùy project, có thể gắn goal Javadoc vào lifecycle hoặc giữ thành bước riêng để kiểm soát thời gian và điều kiện publish.

Các nguyên tắc nên áp dụng:

- Dùng JDK/toolchain nhất quán giữa local và CI.
- Cố định version Gradle wrapper và Maven plugin.
- Dùng UTF-8 cho source và HTML output.
- Bật DocLint; bật fail-on-warning khi API docs đạt mức sẵn sàng.
- Kiểm tra external links; dùng offline link list khi build không có mạng.
- Đóng gói Javadoc JAR cùng binary artifact.
- Không publish tài liệu chứa package hoặc implementation nội bộ ngoài chủ đích.
- Giữ source revision và binary revision đồng nhất để hyperlink và source line không lệch.

## 11. Tổ chức và phát hành tài liệu

Có nhiều cách cung cấp Javadoc:

| Cách phát hành | Khi phù hợp |
| --- | --- |
| HTML trong build directory | Developer xem cục bộ hoặc CI artifact |
| Javadoc JAR | Phát hành cùng thư viện trên Maven/Ivy repository |
| Maven Site | Dự án có portal tài liệu/report tập trung |
| Static web hosting | SDK/API docs cần URL công khai |
| Internal documentation server | API nội bộ cần kiểm soát truy cập |

Javadoc JAR thường có classifier `javadoc`, tách biệt với binary JAR. Điều này giúp Maven/Gradle repository lưu cả artifact chạy và artifact tài liệu. Không đưa HTML vào binary JAR nếu không có yêu cầu cụ thể; giữ classifier riêng giúp consumer chọn loại artifact phù hợp.

Khi publish library, kiểm tra rằng Javadoc JAR dùng cùng version với binary JAR. Nếu source thay đổi nhưng docs không được tạo lại, người dùng có thể đọc sai contract API.

## 12. Troubleshooting Javadoc task

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `No source files for Javadoc` | Task tùy chỉnh chưa khai báo source hoặc source set sai | Đặt `source` và kiểm tra source set |
| `package ... does not exist` | Thiếu dependency trong classpath/module path | Cấu hình compile classpath hoặc module path |
| `reference not found` | `@link` trỏ tới type/member sai hoặc dependency chưa được resolve | Sửa reference và kiểm tra classpath |
| `no @param` hoặc `no @return` | Comment thiếu block tag | Bổ sung mô tả tương ứng |
| `malformed HTML` | HTML trong comment không hợp lệ hoặc thiếu escape | Sửa markup, dùng `{@code}`/`{@literal}` |
| `invalid flag` | JDK và tùy chọn không tương thích hoặc build tool truyền option sai | Kiểm tra `javadoc --help` và option file của task |
| `Unknown tag` | Custom tag chưa được khai báo hoặc Taglet chưa được nạp | Dùng `-tag` hoặc cấu hình Taglet |
| External link không hoạt động | URL không có `element-list`/`package-list`, mạng bị chặn hoặc sai phiên bản | Kiểm tra URL; dùng `-linkoffline` khi phù hợp |
| Tiếng Việt hiển thị lỗi | Encoding source/output không thống nhất | Đặt UTF-8 cho encoding, charset và docencoding |
| Maven build thất bại vì warning | `failOnWarnings` đang bật | Sửa warning; chỉ nới rule có lý do rõ ràng |
| Gradle task không tạo docs | Task tùy chỉnh không có source hoặc output cấu hình sai | Kiểm tra source và destinationDirectory |
| Javadoc JAR không xuất hiện | Chưa gọi `javadoc:jar` hoặc chưa bật `withJavadocJar()` | Bật/đăng ký task đóng gói và chạy task đó |
| API docs khác binary đang publish | Javadoc và binary được tạo từ revision khác nhau | Dùng cùng source revision và version trong pipeline |

### Chẩn đoán từng bước

1. Chạy `javadoc --version` để xác định JDK đang dùng.
2. Chạy `javadoc --help` hoặc `javadoc -X` để kiểm tra option.
3. Chạy trực tiếp Javadoc với một source file để tách lỗi tool khỏi lỗi build integration.
4. Với Gradle, chạy `./gradlew javadoc --info` và kiểm tra generated Javadoc options file khi task lỗi.
5. Với Maven, chạy `mvn -e javadoc:javadoc` để xem stack trace.
6. Xem warning đầu tiên; sửa comment hoặc dependency gây lỗi trước khi xử lý các warning tiếp theo.
7. Kiểm tra `index.html` và trang class trong output directory.
8. Chạy lại task và xác nhận Javadoc JAR có đúng version/classifier.

## 13. Thực hành: tạo và kiểm tra API docs

Dùng class `Greeting` ở phần trên.

### Tạo docs bằng JDK

```bash
javadoc --release 17 -encoding UTF-8 -charset UTF-8 -docencoding UTF-8 -Xdoclint:all -Werror -d build/docs/javadoc -sourcepath src/main/java -subpackages com.example
```

Mở `build/docs/javadoc/index.html` và tìm package `com.example.api`, class `Greeting`, constructor và method `greet`.

### Tạo docs bằng Gradle

Thêm plugin `java-library`, cấu hình task `javadoc`, sau đó chạy:

```bash
gradle javadoc
gradle javadocJar
```

Xác nhận các tệp:

```text
build/docs/javadoc/index.html
build/libs/greeting-api-1.0.0-javadoc.jar
```

### Tạo docs bằng Maven

Khai báo `maven-javadoc-plugin`, sau đó chạy:

```bash
mvn javadoc:javadoc
mvn javadoc:jar
```

Xác nhận:

```text
target/reports/apidocs/index.html
target/greeting-api-1.0.0-javadoc.jar
```

Cuối cùng, thử sửa một comment để bỏ `@return` hoặc tạo một link tới method không tồn tại. Khi bật DocLint và fail-on-warning, task phải báo warning/error và build phải thất bại. Khôi phục comment đúng, chạy lại và xác nhận build thành công.

## 14. Ghi nhớ

- `javadoc` là công cụ JDK; Gradle `Javadoc` task và Maven Javadoc Plugin tích hợp nó vào build.
- Java Plugin tạo task `javadoc` cho source set `main`; task thường phụ thuộc vào `classes`.
- Standard doclet tạo HTML API docs từ declaration và documentation comments.
- Viết comment `/** ... */` có summary rõ ràng và block tags đầy đủ.
- Dùng `{@link}`, `{@code}` và `{@literal}` để tham chiếu API và trình bày code an toàn.
- `package-info.java` và `module-info.java` có thể mang tài liệu package/module.
- Dùng UTF-8, external links, output directory và DocLint một cách nhất quán.
- `-Xdoclint:all` và `-Werror` giúp đưa chất lượng Javadoc vào CI.
- Gradle `withJavadocJar()` tạo task `javadocJar` và đăng ký documentation variant.
- Maven `javadoc:javadoc` tạo HTML; `javadoc:jar` đóng gói tài liệu; `javadoc:aggregate` hỗ trợ multi-module.
- Maven `<build>` và `<reporting>` có vai trò cấu hình khác nhau.
- Javadoc JAR phải được tạo từ cùng revision và version với binary artifact.
- Khi task lỗi, kiểm tra source, classpath, JDK option, DocLint warning và external links trước.

Tích hợp Javadoc task biến tài liệu API thành một phần có thể kiểm tra, đóng gói và phát hành của build pipeline. Khi comment mô tả đúng contract và task chạy tự động trong CI, người dùng thư viện có tài liệu đáng tin cậy đồng thời nhóm phát triển phát hiện sớm các thay đổi làm tài liệu sai hoặc thiếu.

## Tài liệu tham khảo

- [The javadoc Command — JDK 24 Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Gradle: Building Java & JVM Projects — Generating API Documentation](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle Javadoc Task DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html)
- [Gradle JavaPluginExtension — withJavadocJar](https://docs.gradle.org/current/dsl/org.gradle.api.plugins.JavaPluginExtension.html)
- [Apache Maven Javadoc Plugin — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html)
- [Apache Maven Javadoc Plugin — Plugin Information](https://maven.apache.org/components/plugins-archives/maven-javadoc-plugin-LATEST/plugin-info.html)
