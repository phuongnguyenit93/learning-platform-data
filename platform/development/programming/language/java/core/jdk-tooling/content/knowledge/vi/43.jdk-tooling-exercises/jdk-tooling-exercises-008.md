# Tạo tài liệu API bằng Javadoc

**Javadoc** là công cụ của JDK dùng để đọc documentation comments trong mã nguồn Java và tạo tài liệu HTML cho package, class, interface, record, module và các thành viên API. Một bộ Javadoc tốt giúp người dùng hiểu mục đích của API, cách gọi method, giá trị trả về, lỗi có thể phát sinh, giới hạn và yêu cầu tương thích mà không cần đọc toàn bộ implementation.

Javadoc không chỉ là việc chạy một lệnh để tạo HTML. Chất lượng tài liệu phụ thuộc vào cách viết comment trong source, cấu hình toolchain, kiểm tra liên kết, phát hiện lỗi HTML và đưa tài liệu vào quy trình build/release.

Bài thực hành này sử dụng Java 17+ và JDK 24 để tạo Javadoc trực tiếp bằng CLI, tích hợp Maven và Gradle, viết package/module documentation, kiểm tra bằng doclint và đóng gói Javadoc JAR.

## 1. Javadoc tạo ra những gì?

Javadoc đọc source files và tạo một tập HTML có cấu trúc:

~~~text
build/apidocs/
├── index.html
├── allclasses-index.html
├── allpackages-index.html
├── index-all.html
├── help-doc.html
├── overview-tree.html
└── com/
    └── acme/
        └── api/
            ├── package-summary.html
            ├── package-tree.html
            ├── Customer.html
            └── CustomerService.html
~~~

Tùy phiên bản JDK, cấu trúc có thể thêm search index, CSS, JavaScript, module summary và các trang usage.

Các thành phần được tài liệu hóa:

- Package: nhóm các kiểu liên quan.
- Module: tập package và dependency JPMS.
- Class/record: mục đích, trạng thái, cách tạo và invariant.
- Interface: contract mà implementation phải tuân thủ.
- Constructor: điều kiện đầu vào và exception.
- Method: tham số, kết quả, side effects, thread-safety và lỗi.
- Field/constant: ý nghĩa và đơn vị.
- Type parameter: giới hạn và vai trò của generic type.
- Deprecated API: lý do thay thế và hướng migration.

Javadoc thường được phát hành cùng thư viện dưới dạng Javadoc JAR để IDE hiển thị tài liệu ngay khi developer sử dụng dependency. Với một website API, thư mục HTML có thể được publish thành static site.

### Javadoc khác Java compiler như thế nào?

- javac kiểm tra và biên dịch source thành class files.
- javadoc đọc source và comment để tạo HTML.
- Javadoc có thể phát hiện lỗi trong reference, HTML và tag thông qua doclint.
- Tạo Javadoc không thay thế unit test hoặc kiểm tra hành vi runtime.

Có thể chạy javac và javadoc trong cùng pipeline, nhưng chúng là hai bước khác nhau.

## 2. Cú pháp documentation comment

Javadoc comment bắt đầu bằng /** và kết thúc bằng */. Comment phải nằm ngay trước declaration cần mô tả:

~~~java
/**
 * Looks up a customer by its stable identifier.
 */
public interface CustomerService {
}
~~~

Comment thường bắt đầu bằng một câu ngắn, đầy đủ ý. Câu đầu tiên được dùng làm summary trong trang package, class và method.

Nên viết summary có thể đứng độc lập:

~~~java
/**
 * Returns the customer associated with the given identifier.
 */
Optional<Customer> find(String id);
~~~

Tránh summary mơ hồ:

~~~java
/**
 * This method.
 */
Optional<Customer> find(String id);
~~~

Phần mô tả chi tiết có thể tiếp tục sau một dòng trống:

~~~java
/**
 * Returns the customer associated with the given identifier.
 *
 * <p>The lookup is case-sensitive and does not modify stored data.</p>
 */
Optional<Customer> find(String id);
~~~

### Javadoc comment và comment thông thường

~~~java
// Internal implementation note.

/*
 * Multi-line source comment.
 */

/**
 * Public API documentation.
 */
~~~

Chỉ documentation comment được Javadoc xử lý để tạo tài liệu API. Comment // và /* ... */ thông thường không xuất hiện trong HTML.

### Viết tài liệu theo contract

Một method nên trả lời được:

- Method làm gì?
- Tham số nào được chấp nhận?
- Có cho phép null không?
- Kết quả có thể vắng mặt không?
- Có thể ném exception nào và trong trường hợp nào?
- Có side effect không?
- Có thread-safe không?
- Có giới hạn hiệu năng hoặc thứ tự xử lý nào không?

Đừng lặp lại tên method bằng câu văn mà không giải thích contract. Ví dụ, “Gets the customer” chưa đủ; hãy nói rõ lookup theo ID, tính phân biệt hoa/thường và hành vi khi không tìm thấy.

## 3. Các block tag thường dùng

Block tag bắt đầu bằng ký tự @ và thường nằm sau phần mô tả.

| Tag | Mục đích |
|---|---|
| @param | Mô tả parameter hoặc type parameter |
| @return | Mô tả giá trị trả về |
| @throws | Mô tả exception có thể được ném |
| @exception | Tên thay thế của @throws |
| @see | Tham chiếu API hoặc tài liệu khác |
| @since | Phiên bản API được giới thiệu |
| @deprecated | Giải thích API đã deprecated và hướng thay thế |
| @author | Tác giả, nếu dự án cần hiển thị |
| @version | Version tài liệu/implementation nếu dự án dùng |
| @serial | Mô tả serialization của class/field |
| @serialField | Mô tả field trong serialized form |
| @serialData | Mô tả dữ liệu được ghi bởi serialization method |

### @param

Mô tả từng parameter theo tên:

~~~java
/**
 * Finds a customer.
 *
 * @param id stable customer identifier; must not be blank
 */
Optional<Customer> find(String id);
~~~

Với generic type, dùng dấu ngoặc nhọn trong tag:

~~~java
/**
 * Converts an input value.
 *
 * @param <T> type of the input value
 * @param input value to convert
 * @return converted value
 */
<T> String describe(T input);
~~~

### @return

Dùng cho method có giá trị trả về:

~~~java
/**
 * Returns the number of active customers.
 *
 * @return a non-negative count
 */
int count();
~~~

Không dùng @return cho method trả về void.

### @throws

Mô tả điều kiện phát sinh exception:

~~~java
/**
 * Finds a customer.
 *
 * @param id identifier to search for
 * @return matching customer, or an empty result
 * @throws IllegalArgumentException if id is blank
 */
Optional<Customer> find(String id);
~~~

Mô tả hành vi có thể quan sát được. Không liệt kê tất cả exception nội bộ không thuộc contract của API.

### @see

Tạo tham chiếu đến một class, method hoặc URL:

~~~java
/**
 * Provides customer lookup operations.
 *
 * @see Customer
 * @see java.util.Optional
 */
public interface CustomerService {
}
~~~

### @since

Dùng để ghi phiên bản API bắt đầu xuất hiện:

~~~java
/**
 * Returns the customer's display name.
 *
 * @return display name
 * @since 1.2
 */
String displayName();
~~~

Giữ format nhất quán với versioning policy của thư viện.

### @deprecated

Khi thay API cũ, giải thích lý do và cách thay thế:

~~~java
/**
 * Returns the old customer code.
 *
 * @deprecated since 2.0; use {@link #id()} instead.
 */
@Deprecated(since = "2.0", forRemoval = true)
public String oldCode() {
    return id;
}
~~~

Annotation @Deprecated ảnh hưởng compiler warnings và tooling. Block tag @deprecated giải thích cho người đọc. Dùng cả hai khi API thực sự deprecated.

### @inheritDoc

Khi override method, có thể kế thừa documentation từ method cha/interface:

~~~java
/**
 * {@inheritDoc}
 */
@Override
public Optional<Customer> find(String id) {
    // implementation
}
~~~

Dùng khi contract không thay đổi. Nếu implementation có thêm giới hạn hoặc hành vi cụ thể, bổ sung phần mô tả riêng thay vì chỉ sao chép một comment chung.

### Record components và constructor

Record có thể mô tả component ở cấp record:

~~~java
/**
 * An immutable customer record.
 *
 * @param id stable identifier
 * @param displayName name shown to users
 */
public record Customer(String id, String displayName) {
}
~~~

Nếu viết Javadoc riêng cho canonical constructor, cũng cần mô tả các parameter của constructor. Với doclint nghiêm ngặt, thiếu @param ở constructor có thể tạo warning dù record đã mô tả component ở cấp type.

## 4. Inline tag và cách định dạng nội dung

Inline tag nằm trong câu, có dạng {@tag ...}.

| Inline tag | Mục đích |
|---|---|
| {@code ...} | Hiển thị code inline và escape ký tự HTML |
| {@literal ...} | Hiển thị nội dung literal, không xử lý HTML |
| {@link ...} | Tạo hyperlink đến API |
| {@linkplain ...} | Tạo hyperlink với text thường |
| {@value ...} | Hiển thị giá trị constant |
| {@inheritDoc} | Kế thừa mô tả từ declaration cha |
| {@docRoot} | Đường dẫn tương đối tới root của bộ docs |

Ví dụ:

~~~java
/**
 * Use {@code Optional.empty()} when no value exists.
 * See {@link java.util.Optional} for the result container.
 * The expression {@literal <T>} represents a type parameter.
 */
~~~

Dùng {@code} cho tên class, method, constant, option và biểu thức code. Dùng {@literal} khi cần in ký tự đặc biệt như <, > hoặc { mà không muốn Javadoc hiểu đó là HTML/tag.

### Link đến method cụ thể

~~~java
/**
 * Uses {@link CustomerService#find(String)} for lookup.
 */
~~~

Reference phải trỏ đến declaration tồn tại và đúng signature. Nếu method overload, ghi parameter types để tránh liên kết mơ hồ.

### Link có nhãn dễ đọc

~~~java
/**
 * See {@linkplain CustomerService customer lookup API}.
 */
~~~

{@link} thường hiển thị tên API theo kiểu code. {@linkplain} hiển thị nhãn theo văn bản thông thường.

### Hiển thị constant bằng @value

~~~java
public final class Limits {
    /** Default retry count: {@value}. */
    public static final int DEFAULT_RETRIES = 3;

    private Limits() {
    }
}
~~~

Javadoc sẽ thay {@value} bằng giá trị constant. Có thể tham chiếu constant khác bằng qualified name.

## 5. HTML trong Javadoc

Javadoc hiện đại tạo HTML5. Có thể dùng các thẻ HTML hợp lệ như:

- <p> cho đoạn văn.
- <ul> và <li> cho danh sách.
- <pre> và <code> cho ví dụ.
- <strong> hoặc <b> để nhấn mạnh.
- <a> cho liên kết ngoài khi cần.
- <table>, <tr>, <th>, <td> cho bảng.

Ví dụ:

~~~java
/**
 * Validates the request.
 *
 * <p>Validation occurs in this order:</p>
 * <ol>
 *   <li>Check the identifier.</li>
 *   <li>Check the payload.</li>
 *   <li>Check authorization.</li>
 * </ol>
 */
~~~

Không đặt block tag như @param bên trong một thẻ HTML chưa đóng. Đóng thẻ đúng cấu trúc và tránh HTML lỗi thời như <font> hoặc <center>.

### Code block tương thích Java 17

~~~java
/**
 * Example:
 * <pre>{@code
 * CustomerService service = createService();
 * service.find("C-100").ifPresent(System.out::println);
 * }</pre>
 */
~~~

{@code} escape các ký tự HTML bên trong code block.

### Snippet tag từ JDK 18+

JDK 18 trở lên hỗ trợ {@snippet} để hiển thị source snippet có syntax highlighting và khả năng đánh dấu vùng code:

~~~java
/**
 * Example:
 * {@snippet :
 * CustomerService service = ...;
 * service.find("C-100").ifPresent(System.out::println);
 * }
 */
~~~

Có thể đặt snippet trong file riêng rồi tham chiếu bằng thuộc tính file, sử dụng --snippet-path để chỉ định thư mục tìm snippet.

Nếu dự án phải tạo tài liệu bằng Javadoc của JDK 17, dùng <pre>{@code ...}</pre> thay cho {@snippet} vì JDK 17 chưa hỗ trợ snippet tag.

Snippet được hiển thị trong tài liệu; nó không tự thay thế compile test cho ví dụ. Nếu ví dụ phải chạy được, hãy giữ code sample trong source/test và xác minh bằng build.

## 6. Tài liệu cho package, module và toàn bộ dự án

### package-info.java

Tạo file package-info.java trong package source:

~~~java
/**
 * Public API for customer lookup and validation.
 *
 * <p>Types in this package are intended for application integration.</p>
 *
 * @since 1.0
 */
package com.acme.api;
~~~

Javadoc tạo package-summary.html. Đây là nơi giải thích mục đích package, mối quan hệ giữa các type và các quy ước chung.

Đừng chỉ mô tả từng class riêng lẻ; package documentation giúp người đọc hiểu API như một nhóm.

### module-info.java

Với JPMS, có thể viết Javadoc comment trước module declaration:

~~~java
/**
 * Customer API module.
 *
 * <p>Exports the public customer lookup contract.</p>
 */
module com.acme.customer.api {
    exports com.acme.api;
}
~~~

Javadoc có thể tạo module-summary.html và các trang package bên trong module.

### overview.html

Một file overview có thể mô tả toàn bộ library:

~~~html
<!doctype html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Customer API</title>
</head>
<body>
    <h1>Customer API</h1>
    <p>Public API for customer data access.</p>
</body>
</html>
~~~

Truyền bằng -overview overview.html khi chạy javadoc. File này bổ sung phần tổng quan cấp dự án.

### doc-files

Có thể đặt hình ảnh, sơ đồ hoặc tài liệu tĩnh trong thư mục doc-files của package source. Javadoc sẽ copy tài nguyên đó vào output tương ứng. Dùng -docfilessubdirs nếu muốn copy sâu các thư mục con.

Giữ đường dẫn tương đối trong HTML để tài nguyên hoạt động sau khi publish.

## 7. Tạo Javadoc trực tiếp bằng CLI

Giả sử cấu trúc project:

~~~text
javadoc-demo/
├── src/
│   └── main/
│       └── java/
│           └── com/acme/api/
│               ├── package-info.java
│               ├── Customer.java
│               └── CustomerService.java
├── overview.html
└── build/
~~~

Lệnh cơ bản:

~~~bash
javadoc -d build/apidocs src/main/java/com/acme/api/*.java
~~~

Với project có package con, dùng -sourcepath và -subpackages:

~~~bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -notimestamp -d build/apidocs -sourcepath src/main/java -subpackages com.acme.api
~~~

Giải thích:

| Option | Ý nghĩa |
|---|---|
| --release 17 | Dùng API/source model tương thích Java 17 |
| -encoding UTF-8 | Encoding source files |
| -docencoding UTF-8 | Encoding file HTML được tạo |
| -charset UTF-8 | Charset khai báo trong HTML |
| -Xdoclint:all | Kiểm tra HTML, reference và tag |
| -Werror | Xem warning là lỗi |
| -notimestamp | Không ghi timestamp ẩn vào output |
| -d | Thư mục output |
| -sourcepath | Nơi tìm Java source |
| -subpackages | Tạo docs cho package và subpackage |

JDK 24 có thể tạo tài liệu theo release 17 bằng --release 17. Điều này không làm source được biên dịch thành class files; nó chọn API/release context cho công cụ.

### Chọn visibility

Các tùy chọn phổ biến:

- -public: chỉ public API.
- -protected: public và protected, thường là mặc định.
- -package: thêm package-private.
- -private: bao gồm cả private members.

Với tài liệu phát hành cho consumer, dùng public hoặc protected theo contract. Chỉ dùng -private cho tài liệu nội bộ vì nó có thể làm lộ implementation details không phải public API.

### Classpath và module path

Nếu source phụ thuộc vào thư viện ngoài:

~~~bash
javadoc --class-path "lib/customer-model.jar;lib/validation.jar" ...
~~~

Trên Windows, dấu chấm phẩy phân cách path entries. Linux/macOS dùng dấu hai chấm.

Với modular project:

~~~bash
javadoc --release 17 --module-source-path src --module com.acme.customer.api -d build/apidocs
~~~

Nếu cần document nhiều module, liệt kê module bằng --module hoặc cấu hình module source path phù hợp.

### Liên kết tới JDK và thư viện ngoài

Có thể liên kết Javadoc của dependency:

~~~bash
javadoc -link https://docs.oracle.com/en/java/javase/17/docs/api/ ...
~~~

Với môi trường offline, dùng -linkoffline và package list đã tải sẵn:

~~~bash
javadoc -linkoffline https://docs.oracle.com/en/java/javase/17/docs/api/ local-jdk17-docs ...
~~~

Đảm bảo URL và package list đúng phiên bản. Link ngoài giúp người đọc chuyển từ API của dự án sang tài liệu dependency mà không phải copy toàn bộ docs vào project.

### Overview và option file

Có thể dùng:

~~~bash
javadoc -overview overview.html ...
~~~

Khi command dài, lưu option và source paths trong file rồi gọi:

~~~bash
javadoc @javadoc.options
~~~

Cách này giúp build script dễ đọc và tránh giới hạn command line trên một số shell.

## 8. Doclint và chất lượng tài liệu

Doclint kiểm tra documentation comments, bao gồm HTML và các liên kết/tags. Với JDK hiện đại, bật rõ ràng:

~~~bash
-Xdoclint:all
~~~

Kết hợp:

~~~bash
-Werror
~~~

để build thất bại nếu còn warning. Đây là cách tốt để ngăn tài liệu lỗi được publish.

Các vấn đề thường bị phát hiện:

- HTML tag không đóng hoặc lồng sai.
- @param không khớp parameter.
- Thiếu mô tả return hoặc exception trong tài liệu nghiêm ngặt.
- {@link} trỏ đến symbol không tồn tại.
- Reference method sai signature.
- Tag không được nhận diện.
- Comment chứa markup không hợp lệ.

### Tách warning về nội dung và warning về build

Một số dự án có thể chưa thể sửa toàn bộ warning ngay. Có thể bắt đầu bằng doclint phù hợp, sau đó nâng dần mức kiểm tra. Tuy nhiên, đừng tắt toàn bộ doclint để che lỗi link hoặc HTML.

-Xdoclint:all,-missing có thể bỏ qua một số kiểm tra documentation completeness trong giai đoạn migration, nhưng vẫn giữ các kiểm tra khác. Chỉ dùng khi có kế hoạch bổ sung comment còn thiếu.

### Custom tags

Không phải mọi tag bắt đầu bằng @ đều được Standard Doclet nhận tự động. Nếu dự án dùng custom tag, đăng ký bằng -tag hoặc triển khai Taglet.

Ví dụ đăng ký hai block tag tùy chỉnh:

~~~bash
javadoc -tag 'apiNote:a:API Note:' -tag 'implSpec:a:Implementation Requirements:' ...
~~~

Cú pháp gồm tên tag, vị trí áp dụng và heading hiển thị. Với logic phức tạp hơn, viết Taglet và cung cấp qua -taglet/-tagletpath.

Nếu tag không được đăng ký, Javadoc có thể báo unknown tag. Với dự án nhỏ, heading HTML hoặc đoạn văn thông thường thường dễ portable hơn.

## 9. Tích hợp Javadoc với Maven

Maven Javadoc Plugin tạo HTML và Javadoc JAR.

### Cấu hình plugin

Trong pom.xml:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
        </plugin>

        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.11.2</version>
            <configuration>
                <release>17</release>
                <doclint>all</doclint>
                <failOnWarnings>true</failOnWarnings>
                <encoding>UTF-8</encoding>
                <docencoding>UTF-8</docencoding>
                <charset>UTF-8</charset>
                <notimestamp>true</notimestamp>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### Tạo HTML

~~~bash
mvn clean javadoc:javadoc
~~~

Mặc định, plugin tạo HTML trong:

~~~text
target/reports/apidocs/
~~~

Mở target/reports/apidocs/index.html để xem kết quả.

### Tạo Javadoc JAR

~~~bash
mvn javadoc:jar
~~~

Artifact được attach vào Maven project:

~~~text
target/javadoc-demo-1.0.0-javadoc.jar
~~~

Có thể publish Javadoc JAR cùng binary JAR trong release/deploy workflow:

~~~bash
mvn clean verify
mvn deploy
~~~

Để mvn deploy luôn attach Javadoc JAR, cấu hình execution của goal jar trong lifecycle thích hợp hoặc gọi goal trong release pipeline. Không giả định mvn package tự tạo Javadoc JAR nếu plugin chưa được bind.

### Liên kết JDK API

Có thể cấu hình:

~~~xml
<configuration>
    <links>
        <link>https://docs.oracle.com/en/java/javase/17/docs/api/</link>
    </links>
</configuration>
~~~

Kiểm tra mạng build agent hoặc sử dụng offline link package list nếu build chạy trong môi trường không có Internet.

## 10. Tích hợp Javadoc với Gradle

Gradle Java Plugin tạo task javadoc. Với java-library, có thể attach Javadoc JAR vào component publication.

### Cấu hình build.gradle

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.acme'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withJavadocJar()
}

tasks.withType(Javadoc).configureEach {
    options.encoding = 'UTF-8'
    options.charSet = 'UTF-8'
    options.docEncoding = 'UTF-8'
    options.addBooleanOption('Xdoclint:all', true)
    options.addBooleanOption('Werror', true)
}
~~~

### Chạy Javadoc

~~~bash
./gradlew clean javadoc
~~~

HTML output:

~~~text
build/docs/javadoc/index.html
~~~

Tạo Javadoc JAR:

~~~bash
./gradlew javadocJar
~~~

Output:

~~~text
build/libs/javadoc-demo-1.0.0-javadoc.jar
~~~

withJavadocJar() tạo task Javadoc JAR và gắn artifact vào Java component.

### Publish bằng Maven Publish Plugin

~~~groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.acme'
version = '1.0.0'

java {
    withSourcesJar()
    withJavadocJar()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java
        }
    }
}
~~~

from components.java có thể publish binary, sources và Javadoc variants được attach vào component. Cấu hình repository/credentials theo release environment riêng.

### Kiểm tra task

~~~bash
./gradlew tasks --all
./gradlew javadoc --info
~~~

Nếu task bị NO-SOURCE, kiểm tra source nằm đúng src/main/java hoặc source set đã được cấu hình. Đừng kết luận Javadoc thành công nếu project không có source để document.

## 11. Thiết kế Javadoc cho API công khai

### Mô tả behavior, không chỉ signature

Signature:

~~~java
Optional<Customer> find(String id);
~~~

Comment hữu ích nên nói rõ:

- Lookup có case-sensitive không?
- Không tìm thấy thì trả Optional.empty hay ném exception?
- Null có được phép không?
- Có cache hay side effect không?
- Có đảm bảo kết quả nhất quán giữa các lần gọi không?

### Mô tả units và boundary

Với numeric API, ghi rõ đơn vị và phạm vi:

~~~java
/**
 * Sets the timeout.
 *
 * @param timeoutMillis timeout in milliseconds; must be positive
 */
void setTimeout(long timeoutMillis);
~~~

Đừng để người dùng phải đoán millisecond hay second, inclusive hay exclusive.

### Mô tả thread-safety

Nếu class được chia sẻ giữa nhiều thread, nói rõ:

- Thread-safe.
- Immutable.
- Not thread-safe.
- Caller must synchronize.
- Method có thể gọi đồng thời hay không.

Không tuyên bố thread-safe nếu implementation hoặc dependency không bảo đảm.

### Mô tả exception theo điều kiện

Thay vì chỉ viết:

~~~text
@throws IllegalArgumentException on error
~~~

hãy viết:

~~~text
@throws IllegalArgumentException if the identifier is blank
~~~

Điều này giúp caller biết cách xử lý lỗi.

### Tài liệu cho generic và callback

Giải thích type parameter và callback contract, bao gồm nullability, invocation count, thread context và exception propagation nếu các yếu tố đó thuộc API.

### Public API và internal API

Tài liệu public cần ổn định, dễ hiểu và không phụ thuộc chi tiết implementation. Tài liệu nội bộ có thể dùng -private hoặc một site riêng; không publish private implementation details một cách vô tình.

## 12. Phát hành và lưu trữ Javadoc

Có hai cách phân phối phổ biến:

1. **Javadoc JAR:** publish cùng thư viện trong Maven repository để IDE có thể tải tự động.
2. **HTML site:** publish toàn bộ thư mục HTML lên static hosting, internal developer portal hoặc website documentation.

Với Javadoc JAR, kiểm tra file chứa index.html, package pages, search index, stylesheet và tài nguyên cần thiết.

Với HTML site:

- Giữ nguyên cấu trúc thư mục.
- Publish đúng root có index.html.
- Đảm bảo relative links không bị rewrite sai.
- Cấu hình URL/version riêng cho từng release.
- Giữ docs của version cũ nếu consumer vẫn dùng API đó.
- Không thay nội dung tài liệu của release cũ bằng tài liệu của version mới.

### Versioned documentation

Có thể publish:

~~~text
docs/
├── 2.3/
│   └── index.html
├── 2.4/
│   └── index.html
└── latest/
    └── index.html
~~~

latest nên trỏ đến release đã được xác nhận. Nếu cần giữ tính reproducible, build tài liệu từ Git tag và lưu Javadoc artifact cùng binary release.

## 13. Tạo Javadoc có thể tái lập trong CI

Đưa Javadoc vào pipeline:

~~~text
Checkout source/tag
       |
       v
Compile + tests
       |
       v
Javadoc + doclint
       |
       v
Verify links and snippets
       |
       v
Create Javadoc JAR
       |
       v
Publish binary + documentation
~~~

Các nguyên tắc:

- Pin JDK và Maven/Gradle plugin versions.
- Dùng encoding UTF-8 nhất quán.
- Bật doclint.
- Dùng -Werror hoặc failOnWarnings khi đã xử lý warning.
- Dùng -notimestamp nếu cần output không chứa timestamp ẩn.
- Không phụ thuộc tài liệu ngoài có thể thay đổi không kiểm soát.
- Giữ external links và offline package list đúng phiên bản.
- Build docs từ đúng commit/tag của binary.
- Lưu Javadoc JAR cùng checksum/provenance.

### Javadoc và API compatibility check

Javadoc giúp con người hiểu contract nhưng không tự phát hiện mọi breaking API change. Với library, có thể bổ sung binary/API compatibility checker trong CI. Release process cần kiểm tra cả signature và documentation để đảm bảo behavior/compatibility claims chính xác.

### Không để lỗi tài liệu lọt vào release

CI nên fail nếu có broken link nội bộ, malformed HTML hoặc tag không hợp lệ. Nếu build đang có warning cũ, ghi nhận và giảm dần warning theo package thay vì tắt kiểm tra toàn bộ.

## 14. Lab Java 17+: tạo tài liệu cho Customer API

Tạo project:

~~~text
javadoc-demo/
├── pom.xml
└── src/main/java/com/acme/api/
    ├── package-info.java
    ├── Customer.java
    └── CustomerService.java
~~~

File package-info.java:

~~~java
/**
 * Public API for customer lookup and validation.
 *
 * <p>Types in this package are intended for application integration.</p>
 *
 * @since 1.0
 */
package com.acme.api;
~~~

File Customer.java:

~~~java
package com.acme.api;

import java.util.Objects;

/**
 * An immutable customer record.
 *
 * @param id stable customer identifier
 * @param displayName name shown to users
 * @since 1.0
 */
public record Customer(String id, String displayName) {
    /**
     * Creates a customer after validating its fields.
     *
     * @param id stable customer identifier
     * @param displayName name shown to users
     * @throws NullPointerException if either field is {@code null}
     * @throws IllegalArgumentException if either field is blank
     */
    public Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(displayName, "displayName");

        if (id.isBlank() || displayName.isBlank()) {
            throw new IllegalArgumentException(
                "Customer fields must not be blank"
            );
        }
    }
}
~~~

File CustomerService.java:

~~~java
package com.acme.api;

import java.util.Optional;

/**
 * Looks up customer records.
 *
 * <p>Implementations must be safe for concurrent calls.</p>
 *
 * @since 1.0
 */
public interface CustomerService {
    /**
     * Finds a customer by its stable identifier.
     *
     * @param id identifier to search for; must not be {@code null}
     * @return the customer if it exists, otherwise {@link Optional#empty()}
     * @throws IllegalArgumentException if {@code id} is blank
     */
    Optional<Customer> find(String id);

    /**
     * Returns the number of known customers.
     *
     * @return a non-negative count
     * @since 1.1
     */
    int count();
}
~~~

### Compile source

~~~bash
javac --release 17 -d build/classes src/main/java/com/acme/api/*.java
~~~

### Generate HTML bằng CLI

~~~bash
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -notimestamp -d build/apidocs -sourcepath src/main/java -subpackages com.acme.api
~~~

Output chính:

~~~text
build/apidocs/index.html
build/apidocs/com/acme/api/package-summary.html
build/apidocs/com/acme/api/Customer.html
build/apidocs/com/acme/api/CustomerService.html
~~~

Mở build/apidocs/index.html và kiểm tra:

- Package summary có mô tả package.
- Customer hiển thị record component.
- Constructor hiển thị param và throws.
- CustomerService hiển thị method summary/detail.
- {@link Optional#empty()} dẫn đến API Java tương ứng.
- Không còn doclint warning/error.

### Generate bằng Maven

~~~bash
mvn clean javadoc:javadoc javadoc:jar
~~~

Kiểm tra:

~~~text
target/reports/apidocs/index.html
target/javadoc-demo-1.0.0-javadoc.jar
~~~

### Generate bằng Gradle

~~~bash
./gradlew clean javadoc javadocJar
~~~

Kiểm tra:

~~~text
build/docs/javadoc/index.html
build/libs/javadoc-demo-1.0.0-javadoc.jar
~~~

Các lệnh trên tạo tài liệu từ cùng source. Khi dùng JDK 24 với --release 17, output được tạo bằng Javadoc 24 nhưng API/source model được giới hạn theo Java 17.

## 15. Troubleshooting

### Javadoc không tìm thấy package

Kiểm tra -sourcepath, -subpackages, package declaration và source folder. Đảm bảo truyền package name đầy đủ, ví dụ com.acme.api, thay vì đường dẫn file system.

### Không tìm thấy symbol trong @link

Kiểm tra class/package có trong source hoặc classpath/module path không. Với overload, khai báo đầy đủ parameter types:

~~~java
{@link CustomerService#find(String)}
~~~

Nếu API ở dependency khác, thêm dependency vào classpath/module path và cấu hình external link khi cần.

### Unknown tag

Tag có thể là custom tag chưa đăng ký. Dùng -tag cho block tag đơn giản hoặc Taglet cho logic tùy chỉnh. Kiểm tra spelling và tag location.

### Missing @param warning

Tên trong @param phải khớp parameter. Với generic type, ghi @param <T>. Với record canonical constructor có Javadoc riêng, mô tả parameter của constructor.

### Missing @return warning

Method trả về giá trị cần có @return rõ nghĩa. Không dùng tag cho void.

### HTML invalid hoặc malformed

Kiểm tra thẻ mở/đóng, thứ tự lồng và ký tự < hoặc > trong prose. Dùng {@code} hoặc {@literal} để escape ký tự đặc biệt.

### Javadoc không hiện private members

Mặc định Javadoc tập trung vào public/protected API. Dùng -private cho tài liệu nội bộ, nhưng kiểm tra trước khi publish để không lộ implementation details.

### Snippet tag không được nhận diện

{@snippet} yêu cầu Javadoc từ JDK 18 trở lên. Nếu project tạo docs bằng JDK 17, thay bằng <pre>{@code ...}</pre> hoặc nâng doc toolchain.

### Maven tạo HTML nhưng không tạo Javadoc JAR

Chạy goal javadoc:jar hoặc bind goal vào lifecycle release. Kiểm tra plugin execution và output trong target.

### Gradle task báo NO-SOURCE

Kiểm tra source set và thư mục src/main/java. Với project multi-module, chạy task đúng subproject và kiểm tra source được khai báo.

### Javadoc links không hoạt động

Kiểm tra URL external docs, version và package list/element-list. Trong CI offline, dùng -linkoffline với tài liệu đã tải sẵn.

### Build fail do -Werror

Đọc warning cụ thể, sửa comment, tag hoặc link. Không xóa -Werror chỉ để build xanh nếu warning phản ánh lỗi tài liệu công khai.

### HTML hoạt động local nhưng hỏng sau publish

Kiểm tra relative paths, base path của hosting, doc-files, case-sensitive filename và cấu trúc thư mục. Giữ nguyên toàn bộ generated site thay vì chỉ copy index.html.

## 16. Checklist trước khi phát hành Javadoc

- Public API có documentation comment đầy đủ.
- Summary sentence rõ nghĩa và đứng độc lập.
- Parameter, return value và exceptions được mô tả.
- Generic type parameter được giải thích.
- Record component và canonical constructor được tài liệu hóa.
- Links đến API đúng symbol/signature.
- HTML tags hợp lệ.
- Code snippets đúng phiên bản JDK.
- package-info.java có mô tả package.
- module-info.java có mô tả module nếu dùng JPMS.
- Encoding UTF-8 được cấu hình.
- Doclint được bật.
- Warning được xử lý trước release.
- Maven/Gradle plugin versions được pin.
- HTML output được kiểm tra từ index.html.
- Javadoc JAR được tạo và có nội dung.
- External links được kiểm tra hoặc có offline fallback.
- Tài liệu được build từ cùng Git tag/commit với binary.
- Checksum và release metadata được lưu.
- Versioned documentation không ghi đè tài liệu release cũ.

## 17. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Javadoc | Công cụ tạo API documentation từ Java source |
| Documentation comment | Comment dạng /** ... */ |
| Standard Doclet | Bộ xử lý mặc định tạo HTML |
| Doclint | Kiểm tra HTML, tags và references |
| Block tag | Tag bắt đầu bằng @ trong comment |
| Inline tag | Tag dạng {@tag ...} nằm trong câu |
| @param | Mô tả parameter/type parameter |
| @return | Mô tả kết quả |
| @throws | Mô tả exception |
| @deprecated | Hướng dẫn API đã deprecated |
| @inheritDoc | Kế thừa documentation từ API cha |
| {@link} | Liên kết tới API |
| {@code} | Hiển thị code inline |
| {@snippet} | Hiển thị source snippet, JDK 18+ |
| package-info.java | Tài liệu package |
| module-info.java | Module declaration và module documentation |
| Javadoc JAR | Archive chứa HTML API documentation |
| Taglet | Extension để xử lý custom Javadoc tags |
| -sourcepath | Nơi tìm Java source |
| -link | Liên kết tới external Javadoc |
| -Xdoclint:all | Bật toàn bộ doclint checks |
| -Werror | Biến warning thành lỗi |

Javadoc có giá trị khi nó giải thích đúng contract mà consumer cần hiểu. Viết comment gần declaration, mô tả rõ parameter/result/exception, tổ chức package và module docs, tạo HTML bằng JDK toolchain, bật doclint và publish Javadoc JAR cùng binary. Khi tài liệu được tạo từ cùng source tag và kiểm tra trong CI, API docs trở thành một phần đáng tin cậy của artifact release.

## Tài liệu tham khảo

- Oracle JDK 24 — The javadoc Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html
- Oracle JDK 24 — Javadoc Tool Guide: https://docs.oracle.com/en/java/javase/24/javadoc/index.html
- Oracle JDK 24 — Documentation Comment Specification: https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html
- Apache Maven — Maven Javadoc Plugin: https://maven.apache.org/plugins/maven-javadoc-plugin/
- Gradle — Javadoc Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle — Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
- OpenJDK — JEP 413: Code Snippets in Java API Documentation: https://openjdk.org/jeps/413