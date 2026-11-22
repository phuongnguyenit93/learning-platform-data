# Đính kèm tài liệu API bằng Maven Javadoc Plugin

## 1. Vì sao một thư viện Java cần Javadoc JAR?

Khi phát hành một thư viện Java, file JAR thông thường chứa các lớp đã biên dịch (`.class`), resource và manifest. Người dùng thư viện cần biết **class nào là API công khai, mỗi method nhận tham số gì, trả về gì, có thể ném lỗi gì và cách sử dụng ra sao**. Nếu chỉ phát hành binary JAR, họ có thể biên dịch dựa trên các kiểu public nhưng khó đọc thiết kế của thư viện.

Javadoc là hệ thống tài liệu API của Java. Từ những comment `/** ... */`, công cụ `javadoc` của JDK sinh HTML có trang tổng quan, trang package, class, constructor, method và liên kết tham chiếu. **Maven Javadoc Plugin** gọi công cụ này và có thể đóng gói toàn bộ HTML thành một artifact JAR riêng để đi cùng binary JAR.

Ví dụ, một release có thể xuất ra:

~~~text
api-javadoc-demo-1.0.0.jar
api-javadoc-demo-1.0.0-javadoc.jar
~~~

Hai file phục vụ hai mục đích:

- `api-javadoc-demo-1.0.0.jar`: binary JAR của thư viện/ứng dụng, chứa các `.class`.
- `api-javadoc-demo-1.0.0-javadoc.jar`: archive của **tài liệu API HTML**, thường có `index.html` và trang từng kiểu như `vn/example/api/Greeter.html`.

Trong Maven, file thứ hai là một **attached artifact** cùng `groupId`, `artifactId` và `version` với project chính, thêm `classifier=javadoc`. Nó không thay thế và cũng không nằm mặc nhiên **bên trong** binary JAR.

### Mục tiêu của bài học

Sau khi học và thực hành, bạn có thể:

1. Giải thích sự khác biệt giữa binary JAR, Javadoc JAR và sources JAR.
2. Viết JavaDoc comments đúng cú pháp, dùng `@param`, `@return`, `@throws`, `@since` và inline `{@code ...}`, `{@link ...}`.
3. Khai Maven Javadoc Plugin trong `build/plugins`, ghim version và bind goal `jar` vào phase `package`.
4. Hiểu `javadoc:javadoc`, `javadoc:jar`, `javadoc:aggregate-jar` và `javadoc:test-jar` khác nhau ở đâu.
5. Tạo một project Maven **3.9.x + Java 17 + JUnit 5** với Javadoc Plugin **3.12.0**, build JAR chính và Javadoc JAR.
6. Dùng `jar tf`, `mvn install`, `help:effective-pom` và local Maven repository để xác nhận artifact tài liệu đã thực sự được đính kèm.
7. Phân biệt tạo HTML tạm thời với **attach** artifact vào project, rồi hiểu hệ quả khi `install`/`deploy`.
8. Biết cách tránh lỗi doclint, thiếu JDK, lỗi encoding, broken links, không có public API, thiếu package docs hoặc chạy sai goal.
9. Định hướng cấu hình parent/multi-module, aggregate Javadoc và chính sách phát hành tài liệu cho CI/repository.

Bài sử dụng **plugin version 3.12.0**, một phiên bản được tài liệu Apache Maven Javadoc Plugin mô tả rõ. Các version ví dụ là **version ghim để tái hiện bài học**, không khẳng định luôn mới nhất. Khi nâng Javadoc Plugin hãy xem release notes, yêu cầu Maven/JDK và khả năng tương thích với build pipeline hiện tại.

---

## 2. Javadoc là gì và Maven Plugin giải quyết bước nào?

Giả sử source Java chứa:

~~~java
/**
 * Tạo lời chào từ một tên không rỗng.
 *
 * @param name tên người nhận
 * @return câu chào đã chuẩn hóa
 * @throws IllegalArgumentException nếu tên rỗng
 */
public static String hello(String name) { /* ... */ }
~~~

Dòng `/** ... */` là **documentation comment** được javadoc tool đọc. Những comment bắt đầu `//` hay `/* ... */` thông thường không tự trở thành mô tả API theo cách này.

Cơ chế:

~~~text
pom.xml + src/main/java
           |
           v
Maven default lifecycle
  validate -> compile -> test -> package
                                |
                                +-- maven-jar-plugin:jar
                                |     -> binary .jar
                                |
                                +-- maven-javadoc-plugin:jar
                                      |
                                      +-- gọi JDK javadoc tool
                                      +-- sinh HTML cho public API
                                      +-- đóng HTML vào -javadoc.jar
                                      +-- attach artifact classifier=javadoc
~~~

Maven Javadoc Plugin **không thay compiler**. Goal của nó cần hiểu và phân tích mã nguồn, sử dụng JDK javadoc tool và classpath thích hợp. Khi mã nguồn hoặc comment có tham chiếu không hợp lệ, nó có thể thất bại **ngay cả lúc `javac` biên dịch thành công**.

### 2.1. Maven Javadoc Plugin và Maven JAR Plugin

| Thành phần | Goal thường gặp | Đầu ra |
| --- | --- | --- |
| Maven Compiler Plugin | `compiler:compile` | `target/classes/*.class` |
| Maven JAR Plugin | `jar:jar` | Binary JAR, ví dụ `api-javadoc-demo-1.0.0.jar` |
| Maven Javadoc Plugin | `javadoc:javadoc` | Thư mục HTML API |
| Maven Javadoc Plugin | `javadoc:jar` | Javadoc JAR, thường classifier `javadoc` |
| Maven Source Plugin | `source:jar-no-fork` | Sources JAR, classifier `sources` |

Đừng nhầm `maven-jar-plugin:jar` với `maven-javadoc-plugin:jar`: cả hai goal đều tên `jar`, nhưng chúng thuộc **hai plugin khác nhau** và đóng gói **những loại nội dung khác nhau**.

### 2.2. Ghi nhớ ba loại artifact

~~~text
vn.example:api-javadoc-demo:1.0.0:jar
vn.example:api-javadoc-demo:1.0.0:jar:javadoc
vn.example:api-javadoc-demo:1.0.0:jar:sources
~~~

Trong ba dạng trên:

- Dòng 1 là artifact chính.
- Dòng 2 là tài liệu Javadoc **nếu project đã tạo và attach**.
- Dòng 3 là sources JAR **chỉ khi có cấu hình/plugin sinh và attach sources**; Javadoc Plugin không tự tạo sources JAR.

Classifier thuộc tọa độ artifact Maven. Một classifier khác biểu thị **artifact phụ khác**, chứ không phải version mới của thư viện.

---

## 3. Bước quan trọng nhất: khai execution attach-javadocs

Đặt cấu hình sau vào `project/build/plugins` của POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.12.0</version>
    <executions>
        <execution>
            <id>attach-javadocs</id>
            <phase>package</phase>
            <goals>
                <goal>jar</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Đây là **một plugin snippet**, chưa phải POM độc lập. POM hoàn chỉnh ở mục 7.

### 3.1. Giải thích chính xác từng phần

- `groupId=org.apache.maven.plugins`: nhóm phát hành plugin chính thức.
- `artifactId=maven-javadoc-plugin`: artifact plugin tạo tài liệu API.
- `version=3.12.0`: ghim implementation của plugin để build có thể tái lập.
- `executions/execution/id=attach-javadocs`: định danh execution; không phải một Maven goal tên `attach-javadocs`.
- `phase=package`: khi build đi đến `package`, Maven thực thi goal được bind.
- `goals/goal=jar`: goal **`javadoc:jar`** của plugin này.
- `attach` là một tham số của goal Javadoc JAR, **mặc định true** trong 3.12.0.

Vì `javadoc:jar` có default phase `package`, ví dụ không nhất thiết phải ghi `<phase>package</phase>` nếu goal được cấu hình trong một execution hợp lệ theo default binding. Tuy nhiên, khai **tường minh** trong bài giúp xác minh lifecycle và tránh tưởng plugin tự chạy chỉ vì có trong POM.

### 3.2. Chỉ thêm plugin mà không có execution thì sao?

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.12.0</version>
        </plugin>
    </plugins>
</build>
~~~

Đoạn trên **không tự yêu cầu** một Javadoc JAR trong `mvn package` của mọi project. Nó chỉ khai plugin; muốn tự động có Javadoc JAR trong release, cần **lifecycle execution** như phần trước hoặc goal CLI thích hợp.

Khác biệt quan trọng:

- `javadoc:jar` **có default phase package khi goal được bind trong execution**.
- **Plugin không tự thêm execution** chỉ vì xuất hiện ở `build/plugins`.

### 3.3. Có nên ghi classifier và attach tường minh?

Có thể viết:

~~~xml
<configuration>
    <classifier>javadoc</classifier>
    <attach>true</attach>
</configuration>
~~~

Trong Maven Javadoc Plugin 3.12.0, đây là **các giá trị mặc định** của goal `javadoc:jar`. Ghi tường minh làm ý định dễ review, nhưng không bắt buộc.

Nếu đặt `<attach>false</attach>`, plugin có thể tạo file Javadoc JAR nhưng **không attach nó vào project** để install/deploy như artifact phụ. Vì vậy **có file `-javadoc.jar` ở `target` chưa đủ chứng minh artifact đã được publish**. Phải kiểm tra install/deploy hoặc metadata/artifact trên repository.

Nếu tùy chỉnh `<classifier>api-docs</classifier>`, artifact sẽ mang classifier `api-docs` thay vì convention `javadoc`. Những công cụ như IDE/repository viewer thường nhận biết classifier chuẩn `javadoc`, nên **không nên đổi classifier tùy tiện** trong thư viện phát hành công khai.

---

## 4. Các goal Javadoc và khi nào dùng

Maven Javadoc Plugin có nhiều goal, nhưng để đính kèm tài liệu API cho một thư viện Java thông thường, **`javadoc:jar`** là goal trọng tâm.

| Goal | Tác dụng | Dùng khi |
| --- | --- | --- |
| `javadoc:javadoc` | Sinh trang HTML Javadoc của source main | Xem tài liệu cục bộ hoặc tạo report |
| `javadoc:jar` | Sinh và đóng gói tài liệu main vào Javadoc JAR | Đính kèm Javadoc khi package/install/deploy |
| `javadoc:test-javadoc` | Sinh HTML từ test source | Cần tài liệu cho test APIs |
| `javadoc:test-jar` | Đóng tài liệu test vào artifact phụ | Có lý do phát hành test documentation |
| `javadoc:aggregate` | Tổng hợp tài liệu nhiều module vào HTML | Muốn một cổng API docs cho reactor |
| `javadoc:aggregate-jar` | Đóng tài liệu tổng hợp thành JAR | Cần artifact Javadoc chung cấp aggregator |
| `javadoc:javadoc-no-fork` | Sinh HTML không fork lifecycle generate-sources | Tình huống report/site phức tạp |
| `javadoc:aggregate-no-fork` | Aggregate HTML không chạy lại compile lifecycle | Cấu hình multi-module nâng cao |

### 4.1. Gọi goal trực tiếp

~~~bash
mvn javadoc:javadoc
mvn javadoc:jar
~~~

Các lệnh trên gọi **goal**, không gọi phase `package`. `javadoc:jar` sẽ tạo/đính kèm Javadoc artifact trong **Maven session đang chạy**, nhưng riêng lệnh đó **không đồng nghĩa Maven cũng đã chạy đầy đủ compile/test/package/install**.

Nếu mục tiêu là có **bộ artifact phát hành nhất quán**, dùng:

~~~bash
mvn clean package
mvn clean install
~~~

với execution trong POM. Khi đó các bước compile/test/package thông thường chạy theo lifecycle; goal `javadoc:jar` được kích hoạt tại `package`.

### 4.2. Đừng dùng javadoc:javadoc rồi nghĩ đã attach

`javadoc:javadoc` tạo tài liệu HTML để xem, nhưng nó **không tương đương** `javadoc:jar` tạo archive attached classifier. Một trang `index.html` có trên đĩa không đồng nghĩa `-javadoc.jar` đã tồn tại hoặc đã được gắn với project.

### 4.3. Đừng nhầm với report/site

Có thể khai Maven Javadoc Plugin dưới:

~~~xml
<reporting>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-javadoc-plugin</artifactId>
            <version>3.12.0</version>
        </plugin>
    </plugins>
</reporting>
~~~

Đoạn này giúp sinh Javadoc report khi chạy site/reporting lifecycle phù hợp. Nó **không thay thế** `<build><plugins><plugin>` với execution `javadoc:jar` nếu bạn muốn artifact tài liệu được attach vào release.

Vị trí `reporting/plugins` và `build/plugins` có cách áp dụng cấu hình khác nhau. Khi một POM dùng cả hai, cần hiểu goal nào đang chạy và lấy cấu hình ở đâu; không dựa vào việc “cùng plugin name” rồi cho rằng output và artifact sẽ giống hệt.

---

## 5. Viết comment Javadoc để API hữu ích

Tạo Javadoc JAR chỉ là bước đóng gói. Nếu source gần như không có documentation comments, tài liệu sinh ra có thể chỉ chứa tên class, signatures và ít mô tả thực sự. Đối với thư viện phát hành, chất lượng Javadoc là một phần của **hợp đồng API**.

### 5.1. Các thành phần quan trọng

~~~java
/**
 * Chuyển một tên hợp lệ thành câu chào.
 *
 * <p>Khoảng trắng hai đầu tên sẽ được loại bỏ.</p>
 *
 * @param name tên người nhận, không được null hoặc rỗng
 * @return câu chào đã chuẩn hóa
 * @throws IllegalArgumentException nếu name không hợp lệ
 * @since 1.0
 */
public static String hello(String name) {
    // ...
}
~~~

Các ý:

- **Câu đầu tiên** nên là tóm tắt ngắn dễ đọc, vì Javadoc dùng nó tại phần summary.
- `@param` mô tả tham số, không chỉ lặp tên/kiểu của method.
- `@return` mô tả kết quả của method có giá trị trả về.
- `@throws` mô tả exception có thể xuất hiện và điều kiện gây lỗi.
- `@since` nêu thời điểm API được giới thiệu theo quy ước version của project.
- Inline `{@code value}` tạo monospace text escaped thích hợp với đoạn code.
- Inline `{@link Type#method(...)}` tạo liên kết đến phần tử tài liệu có thể resolve.
- `<p>...</p>` dùng HTML đúng trong Javadoc comments nếu cần tách đoạn.

Một comment Javadoc sai tag, thiếu tham số hoặc link trỏ đến kiểu không tồn tại có thể khiến **doclint** tạo cảnh báo/lỗi. Việc Java code compile thành công không bảo đảm documentation compile thành công.

### 5.2. Javadoc không chỉ dành cho class

Nên viết documentation cho:

- Package (thông qua `package-info.java`).
- Public class/interface/record/enum.
- Public constructor và methods.
- Các input constraints, nullability, ordering, thread-safety khi ảnh hưởng client.
- Exceptions được mong đợi.
- Ví dụ sử dụng ngắn, rõ, có thể kiểm chứng.

Không nên tài liệu hóa một method bằng “This method returns result” nếu chưa giúp người dùng biết semantics của result.

### 5.3. Tránh công bố quá nhiều chi tiết private

Javadoc goal có tham số `show`, ví dụ `public`, `protected`, `package`, `private`. Mặc định của plugin 3.12.0 là `protected`. Đối với thư viện API công khai, bạn có thể chủ động chọn:

~~~xml
<show>public</show>
~~~

Điều này giảm các phần tử member được xuất vào tài liệu. Nhưng cần hiểu rằng **giới hạn visibility trong Javadoc không thay đổi binary API**, không xóa method khỏi file `.class`, không thiết lập chính sách access control khi Java runtime chạy.

---

## 6. Điều kiện môi trường: cần JDK thật, không chỉ JRE

Maven Javadoc Plugin gọi **JDK javadoc tool**. Trên môi trường build, kiểm tra:

~~~bash
mvn -version
java -version
javac -version
javadoc --version
~~~

Ví dụ:

~~~text
mvn -version       -> Maven 3.9.x, Java 17
javac -version     -> javac 17.x
javadoc --version  -> javadoc 17.x
~~~

Những dòng trên là **giá trị minh họa**, không phải toàn bộ output bắt buộc. Một JRE tối giản, một Docker runtime image hoặc IDE run JRE có thể không cung cấp đủ công cụ để Javadoc Plugin hoạt động.

### 6.1. Maven JVM, javac và javadoc tool có thể khác nhau

Trong dự án thật, Maven Toolchains, `javadocExecutable` hoặc cấu hình forked tools có thể chọn JDK tool khác với JVM chạy Maven. Vì vậy:

- `mvn -version` cho biết Java đang khởi động Maven.
- `javac -version` ở terminal chỉ cho biết compiler trên PATH.
- `javadoc --version` ở terminal cho biết tool trên PATH.
- **Effective POM và plugin logs** giúp xác minh executable thật mà plugin dùng khi có cấu hình riêng.

Trong bài thực hành, không dùng toolchains hoặc executable override. Dùng một JDK 17 phù hợp cho toàn bộ pipeline để kết quả dễ dự đoán.

### 6.2. Java release cho Javadoc

Với Java 17:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Maven Javadoc Plugin 3.12.0 có tham số `release` (mặc định dựa trên `maven.compiler.release` nếu được cấu hình) để chỉ mức source/API theo Javadoc tool tương ứng. Trong POM runnable ở phần tiếp theo, ta cũng ghi rõ `<release>17</release>` trong cấu hình plugin Javadoc để giảm mơ hồ.

Khai `release=17` không cài JDK và không cho phép JDK 11 xử lý Java 17 language features. Nếu tool javadoc đang dùng quá cũ, có thể báo lỗi source/release không được hỗ trợ.

---

## 7. Dự án thực hành đầy đủ: API, Javadoc, binary JAR và unit tests

Ví dụ có thể dựng theo cây thư mục sau:

~~~text
api-javadoc-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/vn/example/api/
    │       ├── package-info.java
    │       ├── Greeter.java
    │       └── Main.java
    └── test/
        └── java/vn/example/api/
            └── GreeterTest.java
~~~

Ứng dụng in stdout xác định được; thư viện có API công khai với Javadoc `@param`, `@return`, `@throws`, `@since`, `{@code}` và `{@link}`. Test JUnit 5 kiểm tra hai hành vi cơ bản. Plugin Javadoc tạo archive tài liệu bằng chính source này.

### 7.1. pom.xml hoàn chỉnh

Tạo `api-javadoc-demo/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>api-javadoc-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <name>API Javadoc Demo</name>
    <description>Ví dụ đóng gói Javadoc JAR cùng binary JAR.</description>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.api.Main</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                    <docencoding>UTF-8</docencoding>
                    <charset>UTF-8</charset>
                    <show>public</show>
                    <classifier>javadoc</classifier>
                    <attach>true</attach>
                    <failOnError>true</failOnError>
                </configuration>
                <executions>
                    <execution>
                        <id>attach-javadocs</id>
                        <phase>package</phase>
                        <goals>
                            <goal>jar</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Đây là **một POM đầy đủ**, không phải trích đoạn. Các plugin versions được ghim để không phụ thuộc vào bản được Maven tự chọn từ metadata ở thời điểm build.

### 7.2. Vì sao cấu hình này hợp lý?

| Cấu hình | Ý nghĩa |
| --- | --- |
| `packaging=jar` | Binary artifact chính là JAR |
| `maven.compiler.release=17` | Biên dịch mã hướng tới Java 17 |
| `project.build.sourceEncoding=UTF-8` | Đọc source Java chứa tiếng Việt nhất quán |
| `project.reporting.outputEncoding=UTF-8` | Charset/encoding mặc định cho output báo cáo phù hợp |
| `maven-javadoc-plugin 3.12.0` | Công cụ sinh HTML và đóng Javadoc JAR |
| `javadoc:jar`, `phase=package` | Tạo và attach Javadoc trong `mvn package` |
| `classifier=javadoc` | Dùng classifier quy ước cho tài liệu API |
| `attach=true` | Gắn artifact phụ để đi cùng project khi install/deploy |
| `show=public` | Tạo tài liệu tập trung public members |
| `failOnError=true` | Không im lặng xem thành công khi Javadoc tool báo lỗi |
| `junit-jupiter`, `surefire` | Chạy unit test trước khi package |
| `maven-jar-plugin` | Sinh binary JAR có `Main-Class` |

`<show>public</show>` không làm `Greeter.class` mất protected/package-private members; chỉ chọn những phần được Javadoc tool trình bày. Trong mã mẫu, những API mà người dùng cần đọc đều `public`.

### 7.3. package-info.java: mô tả package

Tạo `src/main/java/vn/example/api/package-info.java`:

~~~java
/**
 * Cung cấp API đơn giản để tạo câu chào cho ứng dụng Java.
 *
 * <p>Client có thể sử dụng {@link vn.example.api.Greeter} mà không cần
 * khởi tạo một đối tượng nào.</p>
 *
 * @since 1.0
 */
package vn.example.api;
~~~

File `package-info.java` là cách chuẩn để tài liệu hóa package. Nó không chứa method `main` và không thay thế class Java thực thi. Công cụ Javadoc sẽ dùng nội dung này cho trang package summary.

### 7.4. Greeter.java: API công khai có hợp đồng rõ

Tạo `src/main/java/vn/example/api/Greeter.java`:

~~~java
package vn.example.api;

/**
 * API tạo câu chào bằng tên người nhận.
 *
 * <p>Lớp này không lưu trạng thái và chỉ cung cấp phương thức tĩnh.
 * Ví dụ: {@code Greeter.hello("Maven")} trả về
 * {@code "Xin chào, Maven!"}.</p>
 *
 * <p>Xem thêm {@link Greeter#hello(String)}.</p>
 *
 * @since 1.0
 */
public final class Greeter {
    private Greeter() {
        // Không tạo instance của utility class.
    }

    /**
     * Tạo câu chào sau khi loại khoảng trắng ở hai đầu tên.
     *
     * @param name tên người nhận, không được null hoặc chỉ gồm khoảng trắng
     * @return câu chào có dạng {@code "Xin chào, <tên>!"}
     * @throws IllegalArgumentException nếu {@code name} không hợp lệ
     * @since 1.0
     */
    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return "Xin chào, " + name.trim() + "!";
    }
}
~~~

**Giải thích API:**

- `Greeter` là `public final class`, không thể bị subclass.
- Constructor `private` ngăn tạo instance của utility class.
- `hello(String)` nhận tên, loại khoảng trắng hai đầu và trả về câu chào.
- `name==null` hoặc `name.isBlank()` dẫn đến `IllegalArgumentException`.
- `{@code ...}` in ký tự trong code theo cách phù hợp, **không phải HTML tag `<code>` viết trong Java string**.
- `{@link Greeter#hello(String)}` trỏ đến API method đang được Javadoc tạo trang.
- `@since 1.0` là thông tin version của API theo quy ước project; nó không tự làm compiler từ chối một version cũ hơn.

### 7.5. Main.java: mã chạy để kiểm chứng library

Tạo `src/main/java/vn/example/api/Main.java`:

~~~java
package vn.example.api;

/**
 * Chương trình trình diễn cách gọi {@link Greeter}.
 *
 * @since 1.0
 */
public final class Main {
    private Main() {
    }

    /**
     * In một câu chào cố định ra standard output.
     *
     * @param args tham số dòng lệnh, hiện chưa sử dụng
     */
    public static void main(String[] args) {
        System.out.println(Greeter.hello(" Maven "));
    }
}
~~~

Stdout **chính xác** khi chạy `Main.main`:

~~~text
Xin chào, Maven!
~~~

Đây là stdout của ứng dụng, không phải output của Javadoc Plugin. Việc sinh tài liệu HTML không cần gọi `Main.main`.

### 7.6. GreeterTest.java: hai unit tests

Tạo `src/test/java/vn/example/api/GreeterTest.java`:

~~~java
package vn.example.api;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreeterTest {
    @Test
    void greetsAfterTrimming() {
        assertEquals("Xin chào, Maven!", Greeter.hello(" Maven "));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeter.hello("   "));
    }
}
~~~

JUnit 5 cho phép `@Test` methods package-private. Tên class kết thúc `Test`, được Maven Surefire Plugin nhận theo quy tắc mặc định. Với source và POM chính xác, dự kiến **2 tests PASS**.

**Không lẫn test documentation:** Javadoc goal `jar` thông thường tạo docs cho **source chính** ở `src/main/java`; nó không tự đưa `GreeterTest` vào API documentation JAR của main code. Nếu muốn Javadoc cho test sources, phải dùng goal chuyên biệt như `javadoc:test-javadoc` hoặc `javadoc:test-jar` khi thực sự cần.

---

## 8. Build và kiểm tra hai file JAR

### 8.1. Kiểm tra môi trường

Trong thư mục `api-javadoc-demo`:

~~~bash
mvn -version
javac -version
javadoc --version
~~~

Maven cần chạy trong môi trường có JDK phù hợp với source/release 17. Trong IDE, nhớ kiểm tra **Maven runner JDK** chứ không chỉ Project SDK.

### 8.2. Chạy build sạch

~~~bash
mvn clean package
~~~

Theo POM mẫu, Maven sẽ đi qua compile, test và package. Kỳ vọng **2 unit tests PASS**. Tại package, Maven JAR Plugin và execution `attach-javadocs` của Maven Javadoc Plugin tạo hai JAR:

~~~text
target/
├── api-javadoc-demo-1.0.0.jar
├── api-javadoc-demo-1.0.0-javadoc.jar
├── classes/
│   └── vn/example/api/
│       ├── Greeter.class
│       └── Main.class
├── test-classes/
│   └── vn/example/api/GreeterTest.class
└── surefire-reports/
    └── TEST-vn.example.api.GreeterTest.xml
~~~

Maven có thể tạo thêm thư mục Javadoc/report và metadata. Cây trên chỉ liệt kê những file trọng tâm; không giả định toàn bộ `target` chỉ có đúng các mục đó.

Dạng log mong đợi (cách hiển thị có thể khác):

~~~text
maven-compiler-plugin:3.14.1:compile
maven-surefire-plugin:3.5.4:test
maven-jar-plugin:3.4.2:jar
maven-javadoc-plugin:3.12.0:jar (attach-javadocs)
BUILD SUCCESS
~~~

**Dấu hiệu quan trọng:** goal `maven-javadoc-plugin:jar` được kích hoạt trong phase `package`. Nếu chỉ thấy compiler, Surefire và JAR Plugin, hãy kiểm tra execution `attach-javadocs` có thực sự nằm trong `build/plugins` và POM hiệu lực không.

### 8.3. Kiểm tra nội dung binary JAR

~~~bash
jar tf target/api-javadoc-demo-1.0.0.jar
~~~

Trong kết quả phải có những đường dẫn tương tự:

~~~text
META-INF/MANIFEST.MF
vn/example/api/Greeter.class
vn/example/api/Main.class
~~~

File `.class` có thể được JVM nạp để chạy. Javadoc Plugin không làm Java bytecode trong JAR chính biến thành HTML.

### 8.4. Kiểm tra nội dung Javadoc JAR

~~~bash
jar tf target/api-javadoc-demo-1.0.0-javadoc.jar
~~~

Các entry quan trọng cần tìm:

~~~text
index.html
vn/example/api/Greeter.html
vn/example/api/Main.html
vn/example/api/package-summary.html
~~~

JDK Javadoc tool có thể tạo thêm `stylesheet.css`, `search.js`, `element-list`, index files và nhiều assets. Không yêu cầu thứ tự entry cố định trong archive. Bằng chứng chính là **HTML API pages**, đặc biệt `Greeter.html`, nằm trong Javadoc JAR, không phải `Greeter.class`.

Kiểm tra nhanh trên Linux/macOS:

~~~bash
jar tf target/api-javadoc-demo-1.0.0-javadoc.jar | grep 'vn/example/api/Greeter.html'
~~~

Trên Windows PowerShell:

~~~powershell
jar tf target/api-javadoc-demo-1.0.0-javadoc.jar |
    Select-String 'vn/example/api/Greeter.html'
~~~

`jar tf` là command của **JDK jar tool**, không phải Maven goal. Nó đọc file JAR, không thay POM hoặc source.

### 8.5. Chạy chương trình và phân biệt output

~~~bash
java -jar target/api-javadoc-demo-1.0.0.jar
~~~

Stdout chính xác:

~~~text
Xin chào, Maven!
~~~

**Đừng chạy:**

~~~bash
java -jar target/api-javadoc-demo-1.0.0-javadoc.jar
~~~

với kỳ vọng chương trình chạy. Javadoc JAR chứa HTML, không phải binary executable application. Nó không nhất thiết có `Main-Class` và không chứa `Main.class` dùng cho launcher.

### 8.6. Xem HTML trong Javadoc JAR

Một Javadoc JAR là ZIP-compatible archive. Có thể giải nén nó vào một thư mục riêng rồi mở `index.html` bằng browser. Ví dụ từ thư mục project:

~~~bash
mkdir -p target/extracted-javadoc
cd target/extracted-javadoc
jar xf ../api-javadoc-demo-1.0.0-javadoc.jar
~~~

Đoạn trên là lệnh cho shell **Unix-like**. Với PowerShell, tạo thư mục bằng `New-Item -ItemType Directory -Force`, di chuyển vào đó rồi dùng `jar xf` với đường dẫn chính xác. Đây là thao tác đọc tài liệu **sau khi build**, không cần thay lại Maven Javadoc Plugin.

Không dùng `jar xf` trực tiếp ở project root nếu bạn không muốn tạo các thư mục HTML lẫn trong source tree.

---

## 9. Từ “tạo file” đến “attach artifact”: mvn install

**Tạo Javadoc JAR trong `target` chưa đủ để chứng minh được đính kèm vào hệ thống artifact của Maven.**

Khi goal `javadoc:jar` chạy với `attach=true`, nó đăng ký artifact phụ `classifier=javadoc` vào project hiện hành. Sau đó, Maven Install Plugin hoặc Maven Deploy Plugin có thể xử lý các artifact đã được attach cùng artifact chính.

### 9.1. Install vào local repository

Từ project root:

~~~bash
mvn clean install
~~~

Lệnh này chạy các phase đến `install`, bao gồm `package`, nên execution Javadoc vẫn được gọi. Sau khi install thành công, ở local repository mặc định bạn thường thấy:

~~~text
~/.m2/repository/vn/example/api-javadoc-demo/1.0.0/
├── api-javadoc-demo-1.0.0.pom
├── api-javadoc-demo-1.0.0.jar
└── api-javadoc-demo-1.0.0-javadoc.jar
~~~

Local repository có thể nằm ở đường dẫn khác nếu settings đã tùy chỉnh. Thư mục có thể chứa thêm metadata/checksum, không giới hạn vào ba file trên.

**Bằng chứng:** cùng version, binary JAR và `-javadoc.jar` đều được cài vào repository theo tọa độ của project. Trong Maven, Javadoc artifact không phải một dependency runtime cần thiết của ứng dụng; IDE hoặc công cụ tài liệu có thể tải nó riêng.

### 9.2. Kiểm tra artifact bằng Maven Dependency Plugin

Sau install, nếu plugin Dependency Plugin khả dụng, có thể yêu cầu artifact phụ tường minh:

~~~bash
mvn dependency:get \
    -Dartifact=vn.example:api-javadoc-demo:1.0.0:jar:javadoc
~~~

Dòng này dùng cú pháp nhiều dòng **Bash/Unix shell**. Trên Windows PowerShell hoặc CMD, dùng **một dòng**:

~~~bash
mvn dependency:get "-Dartifact=vn.example:api-javadoc-demo:1.0.0:jar:javadoc"
~~~

Thứ tự trong `-Dartifact` của Dependency Plugin là:

~~~text
groupId:artifactId:version:packaging:classifier
~~~

Nếu artifact Javadoc đã install, Maven thường có thể giải quyết nó từ local repository. Cần lưu ý phiên bản và hành vi của Dependency Plugin có thể khác; `dependency:get` không thay thế việc xác nhận goal install đã attach trong đúng session.

### 9.3. Deploy sang remote repository

Khi project có deployment repository đã cấu hình, credentials đúng và policy cho phép, lệnh:

~~~bash
mvn clean deploy
~~~

sẽ chạy lifecycle đến `deploy`, gồm bước tạo Javadoc JAR. Maven Deploy Plugin có thể publish artifact chính và các attached artifacts như `javadoc`. **Không chạy deploy vào repository thật chỉ để học**; bài tập không cung cấp server hay credentials và không yêu cầu bạn đăng artifact công khai.

Một release tốt nên xác minh từ repository rằng **đúng version** có:

- Binary JAR.
- Javadoc JAR.
- POM metadata.
- Sources JAR nếu quy trình phát hành yêu cầu và đã cấu hình riêng.

### 9.4. -DskipTests không đồng nghĩa skip Javadoc

Nếu sử dụng:

~~~bash
mvn -DskipTests package
~~~

Surefire có thể bỏ thực thi test, nhưng Javadoc execution vẫn có thể chạy vì nó là **plugin khác**. Ngược lại, nếu dùng:

~~~bash
mvn -Dmaven.javadoc.skip=true package
~~~

Maven Javadoc Plugin có tham số skip, nên Javadoc generation có thể bị bỏ qua; các bước compile/test của plugin khác không tự đổi theo.

**Chỉ dùng skip cho tình huống được phép**. Trong pipeline release bắt buộc có Javadoc JAR, skip có thể tạo bộ artifact thiếu documentation; phải có check trên output/repository.

---

## 10. Tại sao classifier=javadoc quan trọng?

Maven nhận diện một artifact bằng các trường như:

~~~text
groupId       = vn.example
artifactId    = api-javadoc-demo
version       = 1.0.0
type/extension= jar
classifier    = javadoc
~~~

Với binary JAR, classifier thường **không có**. Với Javadoc JAR, classifier mặc định là `javadoc`. Vì vậy tên file thông thường thêm hậu tố:

~~~text
api-javadoc-demo-1.0.0-javadoc.jar
~~~

Không phải:

~~~text
api-javadoc-demo-javadoc-2.0.0.jar
~~~

trừ khi artifactId/version thực sự đã được thay đổi một cách khác. `javadoc` là classifier, không phải một release version riêng.

### 10.1. Consumer khai dependency thế nào?

Người dùng thư viện thường chỉ khai:

~~~xml
<dependency>
    <groupId>vn.example</groupId>
    <artifactId>api-javadoc-demo</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Maven đưa **binary JAR** vào compile/runtime classpath theo scope. IDE hoặc công cụ có thể nhận diện tài liệu bằng artifact `javadoc` theo tọa độ liên quan.

**Không cần** khai:

~~~xml
<classifier>javadoc</classifier>
~~~

trong dependency thông thường của ứng dụng để “bật Javadoc”. Làm vậy có thể khiến Maven đưa **HTML JAR** thay cho binary JAR vào classpath và làm mất `Greeter.class` mà compiler cần.

### 10.2. Khi nào cần trực tiếp tải Javadoc artifact?

Khi build tài liệu offline, kiểm tra release, mirror repository hoặc dùng một công cụ nhận artifact classifier `javadoc`. Khi đó lấy qua Dependency Plugin/repository browser đúng artifact; **không coi nó là application dependency**.

### 10.3. Vì sao không cho HTML vào binary JAR?

Về kỹ thuật, JAR có thể chứa arbitrary resources. Nhưng convention Maven phân biệt binary, sources và javadoc artifacts để:

- Runtime dependency không phải tải các trang HTML không cần thiết.
- IDE và repository tools có thể tìm từng loại theo classifier chuẩn.
- Người phát hành có thể cập nhật quy trình kiểm tra docs riêng.
- Build output và release provenance dễ đối chiếu.

Với thư viện công khai, tuân theo convention giúp người tiêu dùng dùng công cụ phổ biến ít cấu hình hơn.

---

## 11. Phân biệt Javadoc JAR và Sources JAR

Hai artifact bổ sung khác nhau:

| Khía cạnh | Javadoc JAR | Sources JAR |
| --- | --- | --- |
| Classifier chuẩn | `javadoc` | `sources` |
| Nội dung | HTML API docs, stylesheets, index | `.java`, source resources phù hợp |
| Plugin | Maven Javadoc Plugin | Maven Source Plugin |
| Goal thường gặp | `javadoc:jar` | `source:jar-no-fork` |
| Công dụng | Đọc API và điều hướng documentation | IDE mở source, debug, tham khảo implementation |
| Có thể chạy bằng `java -jar`? | Không | Không |
| Có tự sinh khi gọi JAR Plugin `jar`? | Không | Không |

Nếu project chỉ cấu hình Javadoc Plugin, **không giả định có `-sources.jar`**. Muốn phát hành cả hai, cấu hình Maven Source Plugin riêng ở một execution/profile phù hợp và kiểm tra cả hai artifact.

Ví dụ **snippet bổ sung** cho sources, đặt trong `build/plugins` nếu chính sách release cần:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-source-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>attach-sources</id>
            <phase>package</phase>
            <goals>
                <goal>jar-no-fork</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Mẫu project runnable **không bắt buộc** thêm snippet này; nó chỉ giải thích cách phát hành sources nếu cần. `source:jar-no-fork` tránh một số vấn đề fork lifecycle không cần thiết so với goal khác trong tình huống attach khi package.

---

## 12. Xác minh tài liệu có thực sự hữu ích

Một file Javadoc JAR tồn tại chưa chắc nội dung tốt. Khi làm code review, hãy xác minh:

1. Có `index.html` và trang package/class đúng.
2. Trang `Greeter.html` hiển thị chữ tiếng Việt chính xác, không bị lỗi encoding.
3. Method `hello(String)` có phần mô tả input, return và lỗi.
4. Link từ package page tới `Greeter` hoạt động.
5. Link `Greeter#hello(String)` được resolve.
6. API nội bộ không chủ ý công khai có bị lọt vào docs không?
7. Generated HTML có quá nhiều broken links hoặc warnings không?
8. Javadoc JAR được đóng từ **cùng revision và version** với binary JAR không?

### 12.1. Lỗi encoding

Trong POM mẫu:

~~~xml
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
<project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
~~~

Cùng với Javadoc Plugin:

~~~xml
<encoding>UTF-8</encoding>
<docencoding>UTF-8</docencoding>
<charset>UTF-8</charset>
~~~

`encoding` liên quan cách đọc source; `docencoding` là encoding HTML output; `charset` khai charset trong HTML. Maven Javadoc Plugin 3.12.0 có hỗ trợ các tham số này. Việc thiết lập đồng nhất tránh hiển thị tiếng Việt thành ký tự lỗi khi build trên Windows/CI có locale khác.

Đừng chữa lỗi encoding bằng cách thay nội dung tài liệu tiếng Việt bằng ASCII không dấu; sửa cấu hình và đảm bảo file source thực tế được lưu UTF-8.

### 12.2. Lỗi @link

Ví dụ đúng trong class `Greeter`:

~~~java
/**
 * Xem {@link Greeter#hello(String)}.
 */
~~~

Nếu bạn viết một class/method không tồn tại hoặc signature sai, javadoc tool có thể báo:

~~~text
reference not found
~~~

Có những khác biệt giữa link tới type ở package khác, nested type, generics và overloads. Khi gặp lỗi, hãy kiểm tra **fully qualified type name** hoặc signature method theo tài liệu Javadoc tool; đừng tắt toàn bộ doclint chỉ để che broken link.

### 12.3. Không nên công khai secret, path nội bộ

Javadoc có thể được phát hành công khai lên Maven Central hoặc repository chia sẻ. Không đưa credentials, API keys, hostnames bí mật, customer data hoặc endpoint production nội bộ vào comments hay output HTML. Một Javadoc JAR đã deploy có thể bị cache và sao chép lâu dài.

### 12.4. Public API là một cam kết thiết kế

Nếu nhiều team dùng thư viện, Javadoc cần mô tả các quy tắc như nullability, thread safety, exception conditions, behavior của empty inputs, backward compatibility và semantics của version. Tài liệu đúng nhưng thiếu các contract này có thể gây lỗi tích hợp dù method signatures hợp lệ.

---

## 13. Các lỗi Javadoc thường gặp: compile PASS nhưng package FAIL

Maven Javadoc Plugin dùng công cụ khác với javac compile thông thường. Vì vậy:

~~~text
mvn test             -> BUILD SUCCESS
mvn package          -> Javadoc generation FAILED
~~~

có thể xảy ra trong POM mẫu, vì `mvn test` chưa đến phase `package` có execution `javadoc:jar`.

Những nguyên nhân có thể gồm:

- Javadoc comment chứa `{@link ...}` không resolve được.
- Thiếu `@param` hoặc `@return` theo doclint checks đang bật.
- Comment có HTML không hợp lệ, thẻ không đóng.
- JDK javadoc tool khác mức source/release được yêu cầu.
- Thiếu type/classpath khi Javadoc phân tích source.
- Một annotation processor hoặc generated source chưa tạo kịp phase.
- Charset hoặc source encoding sai.
- Cấu hình plugin goal/execution không hợp lệ.
- Remote Javadoc links không truy cập được trong môi trường offline.

### 13.1. Đọc đúng lỗi thay vì tắt failOnError

Maven Javadoc Plugin có:

~~~xml
<failOnError>true</failOnError>
<failOnWarnings>false</failOnWarnings>
~~~

`failOnError` mặc định true; `failOnWarnings` mặc định false trong 3.12.0. Lỗi nghiêm trọng khi generate docs sẽ làm build fail theo thiết lập mặc định. Khi bật `failOnWarnings=true` trong CI, cảnh báo có thể trở thành fail để nâng chất lượng docs, nhưng cần review warnings hợp lệ và tránh flaky remote links.

Không đặt `failOnError=false` vĩnh viễn chỉ để pipeline xanh. Nó có thể che Javadoc không sinh được tài liệu đúng hoặc artifact bị thiếu.

### 13.2. doclint có tác dụng gì?

JDK Javadoc tool có kiểm tra documentation (doclint) với các nhóm như syntax, HTML, missing tags, references và accessibility tùy JDK. Maven Javadoc Plugin hỗ trợ tham số `doclint`, ví dụ:

~~~xml
<doclint>all</doclint>
~~~

Khi bật những checks nghiêm ngặt, code có Javadoc thiếu tags có thể bị cảnh báo/lỗi. Đối với một library API thực, hãy sửa comments; chỉ tắt một nhóm checks khi hiểu rõ lý do và ghi chú chính sách. Không khuyên dùng `-Xdoclint:none` như giải pháp mặc định.

Trong POM runnable, chúng ta **không cấu hình `doclint` đặc biệt**; JDK 17/Javadoc Plugin áp dụng hành vi mặc định của tool. Các public methods đã được document để hạn chế lỗi missing documentation.

### 13.3. Javadoc không có public class

Nếu module chỉ có package-private classes, Javadoc Plugin với `show=public` có thể không tạo những trang public API như kỳ vọng. Cần xác định module có **API công khai đáng document** hay không. Đừng lấp đầy archive bằng public dummy class chỉ để tạo một Javadoc file.

### 13.4. Missing JDK tool

Một Docker runtime image có thể chứa chỉ `java` mà không có `javadoc`. Build release thường cần một **JDK image**, còn runtime deployment có thể dùng JRE/runtime image. Nếu Maven đang chạy trong runtime image, Javadoc goal có thể fail trước khi tạo archive.

Cách điều tra:

~~~bash
mvn -version
javadoc --version
~~~

Nếu tool nằm trong JDK khác với Maven runtime, xem `JAVA_HOME`, PATH và plugin toolchain/executable settings. Không copy bừa binary `javadoc` từ JDK khác mà không có các thư viện cần thiết của bộ JDK đó.

---

## 14. Lỗi khi Javadoc được tạo nhưng không xuất hiện ở repository

Tình huống:

~~~text
target/api-javadoc-demo-1.0.0-javadoc.jar    CÓ
~/.m2/repository/.../-javadoc.jar           KHÔNG
~~~

Một số nguyên nhân:

1. Bạn mới chạy `mvn package`, chưa chạy `install`. Artifact chỉ nằm trong `target` là bình thường.
2. `<attach>false</attach>` khiến Javadoc archive không đăng ký vào attached artifacts.
3. Javadoc execution được chạy bằng một lời gọi goal riêng, sau đó `install` chạy ở **Maven invocation khác** không kích hoạt goal; attachment của invocation trước **không tự tồn tại qua Maven sessions**.
4. Plugin bị skip trong lần `install`/`deploy`.
5. Bạn đang kiểm tra nhầm local repository hoặc nhầm artifactId/version.
6. POM/effective execution khác giữa command, profile hoặc module.
7. Install/deploy thất bại trước khi xử lý artifacts.

### 14.1. Lệnh đáng tin cho demo

~~~bash
mvn clean install
~~~

Vì execution `attach-javadocs` nằm ở package, nó chạy **trong cùng Maven lifecycle invocation** với install. Đây là phương án đơn giản để đảm bảo attachment sẵn cho Install Plugin.

### 14.2. Kiểm tra version và classifier ở đúng đường dẫn

Với project mẫu:

~~~text
groupId     vn.example
artifactId  api-javadoc-demo
version     1.0.0
classifier  javadoc
~~~

Đường dẫn trong local repository chuẩn hóa dấu chấm của groupId thành thư mục:

~~~text
vn/example/api-javadoc-demo/1.0.0/
~~~

Một Javadoc JAR ở thư mục của version khác **không chứng minh** artifact `1.0.0` vừa được attach. Nếu đang điều tra release, kiểm tra build log, local repository và remote repository theo **cùng tọa độ chính xác**.

### 14.3. Không tự tạo dependency classifier để xác minh API Java

Đặt `classifier=javadoc` trong `dependencies` của ứng dụng sẽ không làm IDE “bật tooltip Javadoc” theo cách Maven API thông thường. Nó yêu cầu artifact HTML được resolve như dependency, gây classpath sai. Hãy để IDE/Dependency Plugin lấy Javadoc như **auxiliary artifact**.

---

## 15. Sử dụng Javadoc Plugin trong parent POM và multi-module

Một hệ thống có thể có:

~~~text
company-parent/
├── pom.xml                  packaging=pom
├── api-core/
│   └── pom.xml              packaging=jar
├── api-client/
│   └── pom.xml              packaging=jar
└── app/
    └── pom.xml              packaging=jar
~~~

Nếu parent chỉ quản lý **version/configuration**:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-javadoc-plugin</artifactId>
                <version>3.12.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <docencoding>UTF-8</docencoding>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

đó là configuration được **quản lý**, không tự tạo Javadoc JAR cho mọi module. Muốn module nào attach docs, khai plugin/execution ở module ấy hoặc áp dụng chính sách parent inheritance được review rõ.

### 15.1. Version management khác goal execution

Parent `pluginManagement` giúp child kế thừa version chuẩn nếu child sử dụng plugin tương ứng. Nhưng khi mục tiêu là **tạo Javadoc JAR tự động ở package**, bạn còn cần một execution `jar` được bind trong build của module có API.

Một cách rõ ràng:

- Parent quản lý Javadoc Plugin version.
- Modules có library API khai `build/plugins` + execution attach.
- App-only modules quyết định có phát hành Javadoc hay không.
- Parent aggregator `packaging=pom` không tùy tiện tạo Javadoc JAR rỗng cho chính nó.

### 15.2. Chặn kế thừa execution khi cần

Nếu parent có một Javadoc execution chỉ dành cho parent, có thể dùng:

~~~xml
<execution>
    <id>attach-javadocs</id>
    <inherited>false</inherited>
    <phase>package</phase>
    <goals>
        <goal>jar</goal>
    </goals>
</execution>
~~~

Đây là snippet: `inherited=false` ở execution ngăn nó truyền xuống child, không tắt goal chạy ở parent nếu nó được kích hoạt. Cần xem effective POM của từng module để biết nơi nào thực sự phát hành Javadoc.

### 15.3. Build reactor và -pl

Ví dụ (khi artifactId module đúng là `api-core`):

~~~bash
mvn -pl :api-core clean package
~~~

Lệnh chỉ build module được chọn. Nếu module phụ thuộc artifact reactor khác chưa install, có thể cần `-am` để build dependencies. Dù vậy, các module được kéo vào bởi `-am` cũng có lifecycle của riêng chúng; nếu đã khai Javadoc executions, chúng có thể sinh Javadoc JAR. Phải tính đến thời gian build và attachment policy của từng module.

### 15.4. Javadoc aggregate khác các Javadoc JAR riêng

Mỗi module sinh `-javadoc.jar` riêng giúp user truy cập docs theo artifact cụ thể. Nhưng tổ chức cũng có thể muốn **một bộ tài liệu tổng hợp** qua `javadoc:aggregate` hoặc `javadoc:aggregate-jar`.

- `javadoc:jar`: Javadoc main của **một project không aggregate**, thông thường.
- `javadoc:aggregate-jar`: đóng Javadoc **tổng hợp nhiều module** thành archive theo cơ chế aggregator.
- `javadoc:aggregate`: sinh trang HTML aggregate, không tự giống attached Javadoc JAR riêng cho từng child.

Đừng copy `aggregate-jar` vào mọi child POM mà không hiểu aggregator scope. Một aggregate execution thường cần chạy ở POM/phase được thiết kế cho aggregator, với đúng reactor và source dependency relationships. Trong nhiều dự án, **module Javadoc JAR riêng + một site aggregate** là phương án dễ quản lý hơn.

---

## 16. Chất lượng tài liệu và tương thích API

### 16.1. @param/@return/@throws là một phần review API

Một API comment tốt nên trả lời những điều mà method signature chưa thể hiện:

- Null input được phép hay bị từ chối?
- String có được trim/canonicalize không?
- Method có side effect hoặc I/O không?
- Giá trị trả về có null không?
- Exception được ném ở điều kiện cụ thể nào?
- Có thread-safe không?
- Method thuộc API version nào?
- Có deprecated API cần migration path không?

Ví dụ trong `Greeter` có câu trả lời cho input, output và exception. Đó mới là giá trị của Javadoc JAR; **đóng gói HTML tự thân không làm API trở nên dễ dùng**.

### 16.2. Deprecated APIs

Khi thay thế một method:

~~~java
/**
 * Cách cũ để tạo lời chào.
 *
 * @return câu chào kiểu cũ
 * @deprecated dùng {@link Greeter#hello(String)}
 */
@Deprecated(since = "1.1", forRemoval = false)
public static String oldHello() {
    return "Hi";
}
~~~

Đoạn này **chỉ là minh họa**, không thuộc source runnable ở mục 7. Nếu thực sự thêm vào class `Greeter`, cần cập nhật version/API contract và tests tương ứng. Javadoc tool có thể hiển thị thông tin deprecated; annotations như `@Deprecated` và Javadoc `@deprecated` bổ sung ý nghĩa cho nhau.

### 16.3. Giữ tài liệu gắn với đúng code version

Nếu binary version 1.0.0 nhưng documentation lấy từ code đã thay đổi ở version 1.1.0, người dùng có thể thấy methods không tồn tại trong JAR họ đang dùng. Bind `javadoc:jar` trong cùng `package` của build tạo binary giúp giảm rủi ro, nhưng CI vẫn cần kiểm tra artifact provenance, build revision và deployment coordinates.

Không tạo documentation JAR bằng cách copy HTML thủ công của version trước rồi đổi tên file thành version mới.

---

## 17. Bài tập xử lý lỗi và kiểm chứng

### Bài tập A — Phân biệt các goal

Trả lời: `jar:jar`, `javadoc:javadoc` và `javadoc:jar` khác gì? Tại sao chỉ chạy `javadoc:javadoc` không chứng minh `classifier=javadoc` đã được attach?

### Bài tập B — Dựng source có documentation comments

Dùng `package-info.java`, `Greeter.java` và `Main.java` ở mục 7. Giải thích vai trò của `@param`, `@return`, `@throws`, `@since`, `{@code}` và `{@link}`. Vì sao một comment `// hello` không sinh mô tả method Javadoc?

### Bài tập C — Build phát hành lần đầu

Chạy `mvn clean package`, kiểm tra **2 unit tests PASS**, có binary JAR và Javadoc JAR. Dùng `jar tf` chứng minh binary chứa `Greeter.class`, documentation JAR chứa `Greeter.html`.

### Bài tập D — Xác minh stdout

Chạy:

~~~bash
java -jar target/api-javadoc-demo-1.0.0.jar
~~~

Stdout phải là:

~~~text
Xin chào, Maven!
~~~

Giải thích vì sao Javadoc JAR không phải executable JAR.

### Bài tập E — Xác minh attachment

Chạy:

~~~bash
mvn clean install
~~~

Kiểm tra local repository có cùng version của binary JAR, POM và `-javadoc.jar`. Nếu chỉ tìm được JAR trong `target`, hãy phân biệt package với install và kiểm tra `attach`.

### Bài tập F — Tắt attach để hiểu khác biệt

Trong **bản sao dự án**, đổi `<attach>true</attach>` thành `<attach>false</attach>`, chạy `mvn clean install` và đối chiếu artifact của build mới trong một local repository sandbox riêng. **Lưu ý:** nếu local repo đã có `-javadoc.jar` từ lần trước, file cũ có thể còn, gây kết luận sai. Không xóa toàn bộ `~/.m2/repository`; hãy chọn version/sandbox khác rồi so sánh bằng log và artifact mới.

### Bài tập G — Lỗi Javadoc link

Trong bản sao `Greeter.java`, thay `{@link Greeter#hello(String)}` bằng một method không có thật. Dự đoán Javadoc tool có thể báo invalid reference. Khôi phục link và chạy build. Tại sao `javac` và `javadoc` có yêu cầu khác nhau đối với documentation comments?

### Bài tập H — Sai encoding

Lưu source Java chứa chữ `Xin chào` theo UTF-8 nhưng giả định tool đọc bằng charset khác. Quan sát lỗi/hiển thị HTML và sửa `encoding/docencoding/charset` đúng. Không dùng cách xóa toàn bộ dấu tiếng Việt khỏi comment.

### Bài tập I — Chỉ khai plugin, không bind goal

Xóa tạm phần `<executions>` của Javadoc Plugin, vẫn để `build/plugins`. Chạy `mvn clean package` và so sánh output. Sau đó gọi trực tiếp `mvn javadoc:jar` và giải thích vì sao “goal chạy trực tiếp” khác “tự động attach khi package”.

### Bài tập J — Parent/pluginManagement

Thiết kế parent quản lý version 3.12.0, child `api-core` dùng goal `jar` tại package. Tại sao chỉ có pluginManagement trong parent không bảo đảm mọi child có Javadoc artifact?

### Bài tập K — Multi-module aggregate

Một reactor có ba thư viện API. Đề xuất khi nào nên sinh Javadoc JAR riêng cho từng module, khi nào sinh aggregate docs và vì sao không bind `aggregate-jar` vô điều kiện trong mọi child.

### Bài tập L — Chính sách CI

Thiết kế job kiểm tra:

1. Maven/JDK versions hợp lệ.
2. `mvn clean verify` thành công và unit tests thực thi.
3. Cả binary và Javadoc JAR được tạo.
4. Javadoc JAR chứa ít nhất `index.html` và `Greeter.html`.
5. Không còn Javadoc errors; warning policy phù hợp.
6. `mvn install` hoặc release staging chứng minh attached artifact đúng version.
7. Trước deploy, xác minh không có thông tin nhạy cảm trong tài liệu và dùng đúng repository credentials.

---

## 18. Bảng chẩn đoán nhanh

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra/sửa |
| --- | --- | --- |
| Không có `-javadoc.jar` sau `mvn package` | Thiếu execution `javadoc:jar` tại package | Xem `build/plugins` và effective POM |
| Có HTML nhưng không có Javadoc JAR | Chạy `javadoc:javadoc` thay vì `javadoc:jar` | Dùng goal `jar` hoặc execution attach |
| Có `-javadoc.jar` ở target nhưng không ở repository | Chưa install/deploy, hoặc `attach=false` | Chạy `mvn clean install` và xem artifact |
| Javadoc JAR rỗng/không có Greeter.html | Source/package không được scan, cấu hình `show` hoặc excludes | Kiểm tra sources và Javadoc output |
| Javadoc báo invalid reference | `{@link ...}` sai tên/signature | Sửa link, kiểm tra package/class |
| Javadoc báo missing @param/@return | Comment thiếu tag hoặc doclint nghiêm | Bổ sung documentation đúng |
| Compilation PASS nhưng package FAIL | Javadoc goal chạy ở package và có lỗi docs | Đọc Maven Javadoc Plugin error, đừng tắt gate |
| `javadoc:jar` báo không có javadoc tool | JVM/JDK tool thiếu hoặc executable khác | `mvn -version`, `javadoc --version`, toolchain |
| Chữ tiếng Việt lỗi trong HTML | Encoding mismatch | Đồng bộ source/report/output UTF-8 |
| Main JAR không chạy với `java -jar` | Manifest thiếu Main-Class | Kiểm tra Maven JAR Plugin; không phải lỗi Javadoc |
| Javadoc JAR không chạy bằng `java -jar` | Nó là HTML archive, không phải executable | Đọc `index.html` sau khi giải nén |
| Test không có trong Javadoc JAR | Goal `javadoc:jar` dùng main sources | Xem `javadoc:test-jar` nếu cần |
| Không có sources JAR | Javadoc Plugin không tạo sources JAR | Cấu hình Maven Source Plugin riêng |
| Parent có Javadoc Plugin nhưng child không có docs | PluginManagement chỉ quản lý, không tự kích hoạt execution | Khai plugin/exec ở đúng module |
| Reactor sinh nhiều docs hoặc docs nhầm module | Plugin execution inherited ngoài ý muốn | Effective POM theo từng module, inherited config |
| `mvn site` tạo docs nhưng package không attach | Reporting và build execution khác | Khai `build/plugins` + `javadoc:jar` |
| CI offline không resolve external link | Javadoc links ngoài không truy cập được | Kiểm tra `links/offlineLinks` và log, giảm phụ thuộc mạng |
| Remote repo thiếu artifact classifier | Deploy policy/config chưa publish attached artifact | Kiểm tra staging repository, version, classifier |

### 18.1. Quy trình debug theo thứ tự

1. Xác định project, module và command thật (`package`, `install`, `deploy` hay goal trực tiếp).
2. Xem POM hiệu lực, tìm execution `attach-javadocs`, phase và goal `jar`.
3. Xem Maven log xác nhận `maven-javadoc-plugin:jar` đã chạy.
4. Kiểm tra JDK/Javadoc tool, encoding và lỗi comment/source.
5. Kiểm tra file `target/*-javadoc.jar` bằng `jar tf`.
6. Kiểm tra `attach=true` và artifact classifier đúng.
7. Sau install/deploy, xem local/remote repository theo tọa độ chính xác.
8. Đối chiếu HTML nội dung có đúng version API và không chứa secrets.

Có thể hỗ trợ bằng:

~~~bash
mvn help:effective-pom
mvn help:effective-pom -Dverbose
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-javadoc-plugin:3.12.0 -Dgoal=jar -Ddetail=true
~~~

`help:describe` cho tham số và defaults của đúng goal/plugin version; nếu Help Plugin cần tải thêm từ repository, lỗi network/resolution của nó không tự chứng minh Javadoc Plugin bị cấu hình sai.

---

## 19. Checklist trước khi phát hành thư viện

- [ ] Mỗi public API quan trọng có Javadoc mô tả hành vi, tham số, kết quả và lỗi.
- [ ] Không có broken `{@link}` hoặc HTML comments sai làm doclint fail.
- [ ] `package-info.java` mô tả package công khai, nếu cần.
- [ ] Dùng UTF-8 nhất quán để hiển thị tiếng Việt chính xác.
- [ ] Maven/JDK version phù hợp, có `javadoc` tool.
- [ ] Maven Javadoc Plugin version được ghim và dễ truy vết.
- [ ] Goal `javadoc:jar` được bind vào `package` ở module cần phát hành docs.
- [ ] `classifier=javadoc` theo convention, `attach=true`.
- [ ] Binary JAR chứa classes, Javadoc JAR chứa HTML, không nhầm vai trò.
- [ ] Test/compile/package đã PASS, Javadoc generation không báo lỗi.
- [ ] `jar tf` cho thấy `index.html` và API class pages quan trọng.
- [ ] `mvn install` hoặc release staging có attached Javadoc artifact đúng tọa độ/version.
- [ ] Sources JAR được cấu hình riêng nếu release policy yêu cầu.
- [ ] Đã kiểm tra trong multi-module để không attach docs rỗng hoặc trùng.
- [ ] Không có secrets, data nhạy cảm hoặc links nội bộ không được phép chia sẻ.
- [ ] CI xác thực kết quả thực tế, không chỉ dòng `BUILD SUCCESS` chung chung.

**Kết luận:** Maven Javadoc Plugin dùng goal **`javadoc:jar`** để tạo Javadoc HTML, đóng thành **`-javadoc.jar`** và, với `attach=true`, gắn file đó vào project như artifact **classifier `javadoc`**. Muốn việc này xảy ra tự động trong một lần Maven package/install/deploy, hãy **bind execution `jar` vào phase `package`**. Đây là cách phát hành tài liệu API nhất quán với binary JAR, không phải thao tác nhúng HTML vào binary artifact.

## 20. Tài liệu Apache Maven và JDK chính thức

- [Apache Maven Javadoc Plugin — Introduction](https://maven.apache.org/plugins/maven-javadoc-plugin/): mục tiêu plugin, các goal chính, HTML và archive.
- [Apache Maven Javadoc Plugin — Usage](https://maven.apache.org/plugins/maven-javadoc-plugin/usage.html): ví dụ khai plugin trong build/reporting và gọi `javadoc:javadoc`, `javadoc:jar`.
- [Apache Maven Javadoc Plugin 3.12.0 — javadoc:jar](https://maven.apache.org/plugins/maven-javadoc-plugin/jar-mojo.html): default phase `package`, classifier `javadoc`, attach default, release/encoding/doclint/visibility và các parameters.
- [Apache Maven Javadoc Plugin — FAQ](https://maven.apache.org/plugins/maven-javadoc-plugin/faq.html): triển khai Javadoc artifact, links và encoding.
- [Apache Maven Javadoc Plugin — Aggregating Javadocs](https://maven.apache.org/plugins/maven-javadoc-plugin/examples/aggregate.html): Javadoc đa module.
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): ý nghĩa của phase `package`/`install`/`deploy`.
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): cấu hình plugin/execution và `pluginManagement`.
- [Java 17 Documentation — Documentation Comment Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): Javadoc syntax, block/inline tags và semantics.
- [Java 17 Javadoc Tool Documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): các lựa chọn của JDK `javadoc` tool, access visibility, doclint, linking.
