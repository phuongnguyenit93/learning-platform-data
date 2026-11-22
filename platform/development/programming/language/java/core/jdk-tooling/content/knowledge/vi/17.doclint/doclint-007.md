# DocLint trong CI

## Mục tiêu

Sau bài này, bạn có thể giải thích DocLint kiểm tra những gì trong documentation comment; bật đầy đủ các nhóm kiểm tra; biến cảnh báo Javadoc thành lỗi build; tích hợp kiểm tra vào Maven, Gradle và CI; xử lý lỗi HTML, reference, tag còn thiếu và khả năng truy cập; quản lý ngoại lệ có kiểm soát; đồng thời phân biệt kiểm tra tài liệu API với kiểm tra HTML, nội dung và ví dụ code.

## 1. DocLint là gì?

**DocLint** là bộ kiểm tra được tích hợp trong JDK để phát hiện những vấn đề phổ biến trong documentation comment của Java. Nó phân tích doc comment, các tag Javadoc, liên kết đến API và markup được dùng để tạo tài liệu.

DocLint giúp phát hiện sớm những lỗi như:

- Thiếu doc comment hoặc thiếu tag cần thiết trên API.
- Tên tham số trong @param không khớp khai báo method.
- @link hoặc @see trỏ đến class/member không tồn tại.
- Dùng tag Javadoc sai cú pháp.
- Ký tự <, > hoặc & chưa được escape.
- HTML lồng sai cấu trúc hoặc thiếu thẻ đóng.
- Hình ảnh không có mô tả thay thế hoặc bảng thiếu thông tin accessibility.

**DocLint trong CI** có nghĩa là mỗi lần build tự động đều chạy kiểm tra tài liệu API. Nếu tài liệu có lỗi hoặc cảnh báo thuộc chính sách chất lượng của dự án, pipeline sẽ thất bại. Nhờ vậy, lỗi documentation được phát hiện cùng pull request đã tạo ra nó, thay vì chỉ xuất hiện khi phát hành Javadoc.

DocLint không sửa source code, không tự viết nội dung còn thiếu và không chứng minh mô tả API đúng về mặt nghiệp vụ. Nó kiểm tra tính nhất quán, cú pháp và một số yêu cầu chất lượng có thể phân tích tự động.

## 2. DocLint kiểm tra những nhóm nào?

DocLint chia kiểm tra thành năm nhóm:

| Nhóm | Nội dung kiểm tra | Ví dụ |
|---|---|---|
| accessibility | Vấn đề ảnh hưởng khả năng truy cập | Thẻ img thiếu alt; bảng thiếu caption hoặc summary phù hợp |
| html | Cấu trúc HTML phổ biến | Đặt block element bên trong inline element; thiếu thẻ kết thúc bắt buộc |
| missing | Thiếu doc comment hoặc tag | Class chưa có mô tả; method thiếu @param hoặc @return |
| reference | Tham chiếu đến Java API | @link không tìm thấy method; tên trong @param hoặc @throws sai |
| syntax | Cú pháp cấp thấp của doc comment | Dấu <, >, & chưa escape; tag Javadoc không hợp lệ |

Ví dụ lỗi theo từng nhóm:

**accessibility**

~~~java
/**
 * <img src="diagram.png">
 */
public class DiagramView {
}
~~~

Ảnh không có alt text mô tả nội dung. Người dùng công nghệ hỗ trợ có thể không hiểu hình ảnh thể hiện điều gì.

**html**

~~~java
/**
 * <p><div>Invalid nesting for a paragraph.</div></p>
 */
public class HtmlExample {
}
~~~

Một phần tử block được đặt trong cấu trúc paragraph không phù hợp.

**missing**

~~~java
/**
 * Adds two numbers.
 */
public static int add(int left, int right) {
    return left + right;
}
~~~

Method có hai tham số nhưng tài liệu không mô tả chúng. Khi bật nhóm missing, DocLint có thể cảnh báo thiếu @param và @return.

**reference**

~~~java
/**
 * Uses {@link String#notExisting()}.
 */
public class LinkExample {
}
~~~

Method được liên kết không tồn tại trong kiểu String.

**syntax**

~~~java
/**
 * Returns a List<String> value.
 */
public class SyntaxExample {
}
~~~

Dấu ngoặc nhọn có thể bị hiểu là markup HTML. Trong doc comment, nên viết kiểu generic bằng {@code List<String>}.

Mức độ nghiêm trọng phụ thuộc loại vấn đề. Lỗi HTML hoặc cú pháp có thể khiến HTML được sinh ra không hợp lệ; thiếu mô tả thường được báo warning; tham chiếu sai có thể tạo tài liệu gây hiểu nhầm. Trong CI, có thể dùng -Werror để mọi warning đều làm lệnh Javadoc thất bại.

## 3. DocLint được bật như thế nào?

### Khi chạy javadoc

Javadoc bật các kiểm tra DocLint được khuyến nghị theo mặc định. Có thể chọn nhóm cụ thể hoặc yêu cầu tất cả nhóm.

| Tùy chọn | Ý nghĩa |
|---|---|
| -Xdoclint | Bật các kiểm tra được khuyến nghị |
| -Xdoclint:all | Bật cả năm nhóm |
| -Xdoclint:html,syntax | Chỉ bật hai nhóm được liệt kê |
| -Xdoclint:all,-missing | Bật tất cả trừ nhóm missing |
| -Xdoclint:none | Tắt DocLint |
| -Werror | Chuyển warning thành lỗi của lệnh Javadoc |

Khuyến nghị cho dự án mới là bật rõ ràng tất cả nhóm và coi warning là lỗi:

~~~bash
javadoc -Xdoclint:all -Werror -d build/apidocs src/main/java/com/example/api/*.java
~~~

Việc ghi rõ tùy chọn giúp chính sách CI dễ đọc và không phụ thuộc vào mặc định của một phiên bản JDK cụ thể.

Nhóm missing có thể phát hiện API chưa có documentation comment hoặc thiếu tag. Nếu dự án cũ chưa thể sửa hết ngay, có thể tạm dùng -Xdoclint:all,-missing trong giai đoạn chuyển đổi, sau đó đặt mục tiêu bật lại nhóm này. Không nên tắt toàn bộ DocLint để che các lỗi HTML hoặc reference.

### Khi chạy javac

javac cũng hỗ trợ DocLint, nhưng mặc định DocLint bị tắt trong compiler. Có thể bật khi biên dịch:

~~~bash
javac --release 17 -Xdoclint:all -Werror -d build/classes src/main/java/com/example/api/CountParser.java
~~~

Lệnh này kiểm tra documentation comment trong lúc biên dịch source. Nó không tạo website Javadoc.

Để xác minh tài liệu API và tạo HTML, hãy chạy công cụ javadoc. Một pipeline có thể chạy cả compile lẫn Javadoc để có hai lớp kiểm tra.

### Phạm vi declaration được kiểm tra

Javadoc kiểm tra documentation comment của những declaration thuộc phạm vi tài liệu được sinh. Mặc định, standard doclet chủ yếu sinh tài liệu cho public và protected API. Tùy chọn -package hoặc -private mở rộng phạm vi.

Nếu dự án muốn kiểm tra cả API package-private hoặc private, hãy cấu hình mức hiển thị phù hợp. Cần nhớ rằng bật -private sẽ đưa nhiều thành viên nội bộ vào tài liệu và có thể tạo thêm cảnh báo missing.

## 4. Chạy DocLint trực tiếp trong terminal

Tạo file src/main/java/com/example/api/CountParser.java:

~~~java
package com.example.api;

/**
 * Parses positive integer values for application configuration.
 *
 * <p>Leading and trailing whitespace is ignored.
 *
 * @since 1.0
 */
public final class CountParser {

    private CountParser() {
    }

    /**
     * Parses a positive integer from the supplied text.
     *
     * @param text text containing a base-10 integer
     * @return the parsed positive integer
     * @throws IllegalArgumentException if text is null, blank, invalid,
     *         or represents a value that is not positive
     */
    public static int parsePositive(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }

        final int value;
        try {
            value = Integer.parseInt(text.trim());
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(
                    "text must contain an integer", exception);
        }

        if (value <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }

        return value;
    }

    /**
     * Runs a small parsing example.
     *
     * @param args command-line arguments; not used
     */
    public static void main(String[] args) {
        System.out.println("count=" + parsePositive(" 42 "));
    }
}
~~~

### Biên dịch và chạy chương trình

Dùng JDK 17 trở lên:

~~~bash
javac --release 17 -d build/classes src/main/java/com/example/api/CountParser.java
java -cp build/classes com.example.api.CountParser
~~~

Output chính xác:

~~~text
count=42
~~~

### Tạo Javadoc và bật tất cả nhóm DocLint

~~~bash
javadoc --release 17 -Xdoclint:all -Werror -d build/apidocs src/main/java/com/example/api/CountParser.java
~~~

Nếu lệnh thành công, thư mục build/apidocs chứa tài liệu HTML của API. Có thể mở index.html hoặc trang com/example/api/CountParser.html bằng trình duyệt.

Giải thích tùy chọn:

- --release 17: dùng API Java SE của release 17 khi phân tích source.
- -Xdoclint:all: bật accessibility, html, missing, reference và syntax.
- -Werror: dừng với trạng thái lỗi nếu có warning.
- -d build/apidocs: chọn thư mục xuất tài liệu.
- Đường dẫn source: chỉ rõ file Java cần tạo tài liệu.

### Thử tạo một lỗi có chủ đích

Đổi tên tham số trong source thành input nhưng giữ tag cũ:

~~~java
/**
 * Parses a positive integer.
 *
 * @param text input text
 * @return parsed value
 */
public static int parsePositive(String input) {
    return Integer.parseInt(input);
}
~~~

Tag @param text không khớp tên tham số input. Nhóm reference có thể phát hiện sự không nhất quán này. Khi chạy Javadoc với -Werror, warning tương ứng làm lệnh thất bại.

Hãy sửa tag thành @param input rồi chạy lại. CI phải chỉ xanh khi source và tài liệu đã đồng bộ.

## 5. Tích hợp DocLint với Maven

Maven Javadoc Plugin tạo tài liệu API bằng công cụ javadoc của JDK. Với dự án Maven, có thể cấu hình plugin trong build/plugins để chạy lệnh javadoc:javadoc trực tiếp trong CI.

Ví dụ pom.xml:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>count-parser</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <doclint>all</doclint>
                    <failOnError>true</failOnError>
                    <failOnWarnings>true</failOnWarnings>
                    <encoding>UTF-8</encoding>
                    <docencoding>UTF-8</docencoding>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các cấu hình quan trọng:

- doclint = all yêu cầu tất cả nhóm DocLint.
- failOnError = true làm build thất bại khi Javadoc gặp lỗi.
- failOnWarnings = true làm build thất bại khi Javadoc phát ra warning.
- encoding và docencoding giữ source và HTML ở UTF-8.
- Phiên bản plugin được cố định để các máy CI dùng cùng cấu hình.

Maven Javadoc Plugin 3.12.0 mặc định không làm build thất bại chỉ vì warning; vì vậy cần bật failOnWarnings nếu chính sách yêu cầu warning phải được xử lý.

Chạy kiểm tra:

~~~bash
mvn --batch-mode --no-transfer-progress clean verify javadoc:javadoc
~~~

Mục tiêu javadoc:javadoc tạo tài liệu trong target/apidocs. Nếu muốn đóng gói Javadoc thành artifact riêng, có thể chạy:

~~~bash
mvn --batch-mode --no-transfer-progress clean verify javadoc:jar
~~~

Trong dự án nhiều module, có thể cân nhắc goal javadoc:aggregate để tạo tài liệu tổng hợp. Hãy kiểm tra classpath/module path và liên kết giữa các module trước khi dùng chế độ aggregate.

### Phân biệt build plugin và reporting plugin

Có thể khai báo Maven Javadoc Plugin trong build/plugins hoặc reporting/plugins:

- build/plugins dùng cho goal trực tiếp như mvn javadoc:javadoc hoặc mvn javadoc:jar.
- reporting/plugins được dùng khi tạo Maven Site bằng mvn site.

Hai vị trí này có hành vi cấu hình khác nhau. Nếu mục tiêu là chặn pull request khi tài liệu lỗi, cấu hình goal được gọi rõ ràng trong pipeline để kết quả không phụ thuộc việc một người có chạy mvn site hay không.

## 6. Tích hợp DocLint với Gradle

Gradle dùng task Javadoc để tạo API documentation. Có thể cấu hình mọi task Javadoc để kiểm tra toàn bộ nhóm và dừng build khi có warning/error.

### Groovy DSL: build.gradle

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Javadoc).configureEach {
    failOnError = true
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
}
~~~

### Kotlin DSL: build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.javadoc.Javadoc

plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<Javadoc>().configureEach {
    isFailOnError = true
    options.addBooleanOption("Xdoclint:all", true)
    options.addBooleanOption("Werror", true)
}
~~~

Gradle Javadoc task sử dụng Javadoc tool từ Java toolchain nếu được cấu hình. Điều này giúp giữ phiên bản tool nhất quán giữa developer machine và CI.

Chạy:

~~~bash
./gradlew clean check javadoc
~~~

Task check thường chạy test và các verification task khác; task javadoc được gọi rõ ràng để chắc chắn tài liệu API cũng được kiểm tra trong pipeline.

Không đặt failOnError = false trong CI bắt buộc. Cấu hình đó cho phép task bỏ qua lỗi Javadoc và làm mất mục đích kiểm tra chất lượng.

## 7. Ví dụ workflow GitHub Actions

Với dự án Maven, có thể tạo file .github/workflows/verify.yml:

~~~yaml
name: Verify Java API documentation

on:
  pull_request:
  push:
    branches:
      - main

jobs:
  verify:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run tests and DocLint
        run: mvn --batch-mode --no-transfer-progress clean verify javadoc:javadoc
~~~

Vì Maven Javadoc Plugin đã cấu hình doclint = all và failOnWarnings = true, lệnh trong CI sẽ thất bại nếu tài liệu có lỗi hoặc warning.

Một workflow tốt cần:

1. Checkout đúng commit của pull request.
2. Cài JDK đúng phiên bản dự án yêu cầu.
3. Chạy build và test.
4. Chạy Javadoc với DocLint.
5. Lưu log khi thất bại để tác giả sửa đúng file.
6. Chỉ cho phép merge khi job bắt buộc đã thành công.

Nếu dùng Gradle, thay bước cuối bằng:

~~~bash
./gradlew --no-daemon clean check javadoc
~~~

Nên dùng Gradle Wrapper và Maven Wrapper để CI chạy đúng phiên bản build tool mà dự án khóa.

## 8. Đọc và xử lý kết quả DocLint

Khi DocLint phát hiện vấn đề, thông báo thường cho biết:

- Tên file source.
- Số dòng và vị trí lỗi.
- Nhóm hoặc dạng vấn đề.
- Một phần dòng source liên quan.
- Dấu chỉ vị trí để xác định vùng cần sửa.

Quy trình xử lý:

1. Xác định file và declaration được báo.
2. Đọc doc comment cùng chữ ký class/method.
3. Xác định nhóm lỗi: accessibility, html, missing, reference hay syntax.
4. Sửa source comment hoặc class/member reference.
5. Chạy lại lệnh javadoc cục bộ.
6. Kiểm tra trang HTML được tạo nếu thay đổi ảnh hưởng markup hoặc link.
7. Commit source và để CI chạy lại.

### Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Invalid @param name | Tên tag khác tên tham số | Đồng bộ tên trong source và tag |
| Missing @return | Method có kiểu trả về nhưng thiếu tag | Mô tả giá trị trả về |
| Reference not found | Link sai hoặc thiếu dependency để resolve | Sửa reference, classpath hoặc module path |
| Invalid HTML | Tag lồng sai hoặc thiếu end tag | Sửa markup HTML |
| Unescaped angle bracket | Viết generic type trực tiếp trong HTML comment | Dùng {@code List<String>} |
| Missing alt | Hình ảnh không có mô tả thay thế | Bổ sung alt có ý nghĩa |
| Missing documentation | API nằm trong phạm vi sinh docs nhưng không có doc comment | Viết mô tả API và tag cần thiết |
| Unknown tag | Dùng sai tên tag hoặc custom tag chưa được khai báo | Sửa tag hoặc cấu hình taglet |
| External link unavailable | CI không truy cập được tài liệu tham chiếu | Dùng offline link hoặc cache tài liệu tham chiếu |

Nếu reference tới class bên ngoài không được tìm thấy, hãy kiểm tra Javadoc classpath hoặc module path. Đối với liên kết tới tài liệu API bên ngoài, cấu hình -link hoặc -linkoffline phù hợp. Không bỏ kiểm tra reference chỉ vì CI không có kết nối internet ổn định.

## 9. Xử lý dự án cũ có nhiều warning

Một codebase lâu năm có thể có hàng trăm API chưa có doc comment. Bật -Xdoclint:all -Werror ngay lập tức có thể khiến mọi pull request đều thất bại.

Có thể triển khai theo từng giai đoạn:

### Giai đoạn 1: đo baseline

Chạy DocLint và lưu danh sách warning hiện tại. Phân loại theo package và nhóm lỗi. Không xóa log hoặc tắt toàn bộ DocLint để làm pipeline xanh.

### Giai đoạn 2: bật nhóm lỗi quan trọng

Bật html, syntax, reference và accessibility trước nếu cần xử lý lỗi cấu trúc, link và khả năng truy cập. Giữ danh sách missing docs như backlog có owner.

Ví dụ:

~~~bash
javadoc -Xdoclint:html,syntax,reference,accessibility -Werror -d build/apidocs src/main/java/com/example/api/*.java
~~~

### Giai đoạn 3: chỉ định phạm vi package

Có thể dùng tùy chọn package để áp dụng kiểm tra cho package API mới hoặc loại trừ một package legacy có kế hoạch xử lý riêng. Ví dụ:

~~~bash
javadoc -Xdoclint/package:com.example.api.*,-com.example.legacy.* -Xdoclint:all -d build/apidocs src/main/java/com/example/api/*.java
~~~

Hãy kiểm tra cú pháp package selector theo JDK được dùng. Mọi ngoại lệ cần có lý do và thời hạn xử lý.

### Giai đoạn 4: bật missing và warning-as-error

Sau khi baseline được giảm, bật đầy đủ:

~~~bash
javadoc -Xdoclint:all -Werror -d build/apidocs src/main/java/com/example/api/*.java
~~~

Đặt đây làm quality gate bắt buộc. Từ thời điểm đó, API mới không thể thêm documentation thiếu hoặc sai mà vẫn merge.

Không nên duy trì danh sách ngoại lệ rộng vô thời hạn. Hãy ghi rõ package, nhóm được loại trừ, lý do, người chịu trách nhiệm và mốc gỡ ngoại lệ.

## 10. Suppress warning có kiểm soát

DocLint hiểu annotation SuppressWarnings với giá trị doclint hoặc doclint:<group>. Có thể dùng để bỏ qua một cảnh báo cụ thể khi có lý do thực tế:

~~~java
/**
 * Legacy entry point retained for binary compatibility.
 */
@SuppressWarnings("doclint:missing")
public void legacyOperation() {
}
~~~

Các giá trị nhóm hợp lệ gồm accessibility, html, missing, reference và syntax. Có thể chỉ định nhiều nhóm trong cùng annotation.

Suppress chỉ bỏ thông báo kiểm tra; nó không sửa nội dung hoặc làm tài liệu trở nên đầy đủ hơn. Chỉ dùng khi:

- Warning không thể sửa mà không phá tương thích hoặc thay đổi API ngoài phạm vi.
- Có lý do kỹ thuật rõ ràng.
- Phạm vi suppress được giới hạn ở declaration cần thiết.
- Có giải thích để reviewer hiểu tại sao ngoại lệ tồn tại.

Không dùng @SuppressWarnings("doclint") trên package hoặc class lớn để che hàng loạt vấn đề. Tránh suppress lỗi HTML, syntax hoặc reference mà có thể sửa trực tiếp.

## 11. DocLint không thay thế những kiểm tra nào?

DocLint rất hữu ích nhưng có giới hạn.

| Công việc | DocLint có làm không? | Công cụ/quy trình bổ sung |
|---|---|---|
| Kiểm tra tag Javadoc | Có | Javadoc/DocLint |
| Kiểm tra reference đến API | Có | Classpath/module path đúng |
| Kiểm tra một số lỗi HTML | Có | HTML validator |
| Kiểm tra accessibility cơ bản | Có | Accessibility audit |
| Kiểm tra mọi quy tắc HTML Living Standard | Không | HTML validator |
| Xác nhận mô tả đúng hành vi code | Không | Code review và test |
| Chạy ví dụ trong doc comment | Không bảo đảm | Unit test hoặc snippet test |
| Kiểm tra link website còn hoạt động | Không | Link checker |
| Kiểm tra chất lượng nội dung, ngữ pháp | Không | Review tài liệu |
| Đảm bảo API được mô tả đầy đủ về nghiệp vụ | Không | Review thiết kế API |

Javadoc có thể tạo HTML thành công nhưng nội dung vẫn sai hoặc thiếu ví dụ. Ngược lại, một trang HTML hợp lệ cũng chưa chắc giải thích đúng cách dùng API.

Với thư viện công khai, nên kết hợp DocLint với test cho ví dụ, kiểm tra liên kết ngoài, kiểm tra HTML/accessibility và review tài liệu trong pull request.

## 12. Tích hợp với multi-module và generated source

Trong dự án nhiều module:

- Chạy Javadoc cho từng module để xác định module nào gây lỗi.
- Dùng goal aggregate khi cần một bộ tài liệu chung.
- Đảm bảo module path và dependency resolution đầy đủ để Javadoc tìm thấy type.
- Cấu hình liên kết giữa các module để link tới API của nhau.
- Không bỏ qua module chỉ vì module đó không có trang Javadoc riêng nếu nó vẫn cung cấp API được public module sử dụng.

Nếu annotation processor hoặc plugin tạo Java source, hãy bảo đảm generated source đã tồn tại trước khi Javadoc chạy. Khi Javadoc chạy quá sớm, nó có thể báo thiếu type hoặc reference dù compile task cuối cùng thành công.

Trong Maven, chạy Javadoc sau generate-sources và bảo đảm plugin có source root cần thiết. Trong Gradle, thêm generated source vào source set và để task Javadoc phụ thuộc đúng task sinh source.

Đối với module Java, Javadoc cần đọc được module-info.java và module path tương ứng. Lỗi module không được giải quyết bằng cách tắt DocLint; hãy sửa cấu hình module/source path.

## 13. Bảo đảm build có thể tái lập

Để kết quả DocLint ổn định giữa máy cá nhân và CI:

- Khóa JDK version và vendor được dùng để chạy Javadoc.
- Khóa phiên bản Maven/Gradle bằng wrapper.
- Khai báo source encoding UTF-8.
- Giữ nguyên Javadoc options giữa local và CI.
- Không phụ thuộc vào file trên máy developer.
- Cấu hình external API links có phương án offline nếu cần.
- Lưu log và artifact HTML khi kiểm tra thất bại.
- Không dùng tùy chọn skip để vượt qua quality gate trong nhánh phát hành.

Javadoc của JDK 23 trở lên hỗ trợ Markdown documentation comments; JDK cũ hơn có thể không hiểu cú pháp đó. Nếu source dùng /// Markdown comments, CI phải dùng JDK tương thích. Toolchain khác phiên bản có thể tạo ra cảnh báo hoặc lỗi mà máy local không gặp.

## 14. Checklist DocLint trong CI

- [ ] Chọn JDK/toolchain phù hợp với source và tài liệu.
- [ ] Dùng Maven Wrapper hoặc Gradle Wrapper.
- [ ] Đặt source encoding là UTF-8.
- [ ] Chạy Javadoc trong mọi pull request.
- [ ] Bật -Xdoclint:all để kiểm tra đủ năm nhóm.
- [ ] Bật -Werror hoặc failOnWarnings để warning làm build thất bại.
- [ ] Đảm bảo Javadoc có đúng source set, dependency và module path.
- [ ] Kiểm tra public/protected API hoặc phạm vi cần tài liệu.
- [ ] Chạy test cho code example quan trọng.
- [ ] Kiểm tra HTML và accessibility bằng công cụ bổ sung khi cần.
- [ ] Chỉ suppress warning ở phạm vi nhỏ và có lý do.
- [ ] Lưu log và HTML artifact để reviewer có thể kiểm tra.
- [ ] Xóa dần ngoại lệ legacy và bật nhóm missing đầy đủ.
- [ ] Không bỏ qua lỗi bằng cách tắt toàn bộ DocLint.

## 15. Tài liệu tham khảo chính thức

- [The javadoc Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html) — tùy chọn -Xdoclint, nhóm kiểm tra, -Werror và phạm vi tạo tài liệu.
- [The javac Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — bật DocLint trong quá trình biên dịch và cú pháp các nhóm kiểm tra.
- [Apache Maven Javadoc Plugin 3.12.0](https://maven.apache.org/plugins/maven-javadoc-plugin/) — cấu hình doclint, failOnError, failOnWarnings và các goal Javadoc.
- [Maven Javadoc Plugin Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html) — cấu hình plugin trong build/reporting và chạy các goal tạo tài liệu.
- [Gradle Javadoc DSL](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.javadoc.Javadoc.html) — Javadoc task, toolchain, options và failOnError.
- [Gradle CoreJavadocOptions API](https://docs.gradle.org/current/javadoc/org/gradle/external/javadoc/CoreJavadocOptions.html) — cấu hình option như Xdoclint và Werror.
- [JavaDoc Guide, Java SE 26](https://docs.oracle.com/en/java/javase/26/javadoc/index.html) — hướng dẫn tạo tài liệu API bằng Javadoc.

DocLint biến chất lượng documentation comment thành một kiểm tra tự động trong build. Hãy bật đủ nhóm kiểm tra, xử lý warning tại source và giữ JDK/toolchain nhất quán để pull request chỉ được thông qua khi tài liệu API có cấu trúc và tham chiếu đáng tin cậy.
