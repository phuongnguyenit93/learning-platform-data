# configuration và ánh xạ phần tử XML sang tham số plugin trong Maven

Trong Maven, nhiều cấu hình build trông giống các thẻ XML tùy ý:

```xml
<configuration>
    <release>17</release>
    <showWarnings>true</showWarnings>
</configuration>
```

Chúng **không phải phần tử POM chuẩn có ý nghĩa toàn cục** như `<dependencies>` hay `<version>`. Bên trong `<configuration>`, mỗi tên thẻ thường ánh xạ đến **tham số mà một goal (Mojo) của plugin hỗ trợ**. Maven đọc cấu hình, nội suy những biểu thức hợp lệ, chuyển dữ liệu XML sang kiểu Java tương ứng và truyền chúng cho Mojo khi goal được thực thi.

Hiểu cơ chế này giúp trả lời các câu hỏi thường gặp: vì sao tên thẻ phải là `<release>` chứ không phải `<javaVersion>`; vì sao `<includes>` có nhiều `<include>`; khi nào có thể dùng `-D...`; vì sao cấu hình plugin trong `pluginManagement` không tự kích hoạt goal; và làm sao xác minh plugin **thật sự nhận được giá trị mong muốn**.

Bài dùng cú pháp Maven 3.9.x, Java 17 và phiên bản plugin được chỉ định tường minh. Một số nội dung có tính khái niệm áp dụng tương tự Maven 4, nhưng chi tiết thực thi/plugin có thể thay đổi theo phiên bản.

## 1. Phân biệt POM, plugin, goal, Mojo và parameter

Maven tổ chức build theo nhiều lớp:

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| Project POM | `pom.xml`, `<build>` | Mô tả model dự án và cấu hình build |
| Maven plugin | `maven-compiler-plugin` | Gói các chức năng/goal liên quan |
| Goal | `compiler:compile` | Công việc được yêu cầu thực thi |
| Mojo | Lớp Java hiện thực goal `compile` | Nhận tham số và thực hiện hành động |
| Parameter | `release`, `showWarnings` | Giá trị điều chỉnh hành vi Mojo |
| Configuration XML | `<release>17</release>` | Cách khai báo giá trị parameter trong POM |
| CLI/user property | `-Dmaven.compiler.release=17` | Cách truyền giá trị qua property nếu plugin hỗ trợ hoặc cấu hình POM tham chiếu nó |

**Một plugin có thể cung cấp nhiều goal**, và mỗi goal có bộ tham số riêng. Chẳng hạn Maven Compiler Plugin có goal `compile` cho main sources và `testCompile` cho test sources; Maven Resources Plugin có `resources` và `testResources`. Một thẻ có ý nghĩa với goal A không chắc có ý nghĩa với goal B.

Ví dụ khái niệm của plugin tự viết:

```java
@Mojo(name = "announce")
public final class AnnounceMojo extends AbstractMojo {
    @Parameter(property = "announce.label", defaultValue = "default")
    private String label;

    @Parameter(defaultValue = "3")
    private int repeatCount;

    @Parameter
    private List<String> tags;

    @Override
    public void execute() throws MojoExecutionException {
        // Goal xử lý giá trị của các tham số đã được Maven inject.
    }
}
```

**Đây là đoạn Java mô tả cấu trúc Mojo, chưa phải file Java/plugin project độc lập**: nó cần import classes từ Maven Plugin API, Maven Plugin Annotations, cấu hình plugin descriptor và bộ build plugin riêng. Nó giúp nhìn thấy ánh xạ:

```xml
<configuration>
    <label>hello</label>
    <repeatCount>2</repeatCount>
    <tags>
        <tag>alpha</tag>
        <tag>beta</tag>
    </tags>
</configuration>
```

- `<label>` ánh xạ tới field/parameter `label`.
- `<repeatCount>` được chuyển từ text `2` sang `int`.
- `<tags>` gồm hai mục chuyển vào `List<String>`.
- `@Parameter(property = "announce.label")` cho biết tên property Maven/user property có thể cung cấp giá trị cho parameter; **nó không đổi tên XML thành `<announce.label>`**.
- `defaultValue` là mặc định mà plugin metadata cung cấp nếu không có giá trị áp dụng khác.

### 1.1. Cơ chế ánh xạ nằm ở đâu?

Plugin Maven thường được đóng gói dưới dạng JAR, chứa plugin descriptor (thường là `META-INF/maven/plugin.xml`). Plugin Tools sinh metadata từ khai báo Mojo và tham số, gồm tên goal, phase mặc định khi có, loại tham số, default values, yêu cầu/khả năng cấu hình.

Maven Core/Plugin Manager sử dụng metadata này và hệ thống Plexus/Sisu để cấu hình Mojo. Dữ liệu XML được ánh xạ tới field/setter/bean property và kiểu dữ liệu tương ứng. Vì vậy, **tài liệu tham số của đúng plugin và đúng goal/version là nguồn đáng tin nhất** khi chọn tên thẻ XML.

Không nên đoán từ tên Java class, tài liệu của phiên bản plugin khác hoặc một cấu hình lấy từ blog nhiều năm trước.

## 2. Vị trí khai báo configuration trong POM

### 2.1. Plugin-level configuration

Cấu hình áp dụng chung cho plugin trong project:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <showWarnings>true</showWarnings>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn XML phải được đặt bên trong `<project>` của POM**, không phải file POM độc lập. `release` và `showWarnings` là các tham số của Compiler Plugin; chúng không trở thành thẻ top-level thuộc POM model.

Plugin-level configuration thường là lựa chọn phù hợp khi các lần chạy của cùng plugin có cùng tùy chọn, hoặc khi goal được lifecycle mặc định gọi.

### 2.2. Execution-level configuration

Một plugin có thể thực thi nhiều goal hoặc cùng goal nhiều lần với tham số khác nhau:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <executions>
        <execution>
            <id>copy-generated-docs</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>copy-resources</goal>
            </goals>
            <configuration>
                <outputDirectory>${project.build.directory}/docs</outputDirectory>
                <resources>
                    <resource>
                        <directory>src/package-docs</directory>
                        <filtering>false</filtering>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn plugin đặt trong `<build><plugins>`**. Nó liên kết goal `resources:copy-resources` với phase `prepare-package` và cấp tham số riêng cho execution `copy-generated-docs`.

- `<phase>` thuộc **Maven lifecycle binding**, không phải tùy chọn `copy-resources` nhận như một field.
- `<goals><goal>` xác định goal nào được chạy.
- `<id>` giúp phân biệt execution và tác động cách merge với parent POM.
- `<configuration>` nằm **bên trong execution** cấu hình goal khi execution đó được chạy.

Nếu POM có cả cấu hình cấp plugin và cấu hình cấp execution, Maven kết hợp chúng theo quy tắc merge; cấu hình cụ thể hơn có thể ghi đè hoặc bổ sung cấu hình chung. **Không phải cứ khai báo `<configuration>` là goal sẽ chạy**: cần lifecycle mapping, execution binding hoặc gọi goal trực tiếp.

### 2.3. pluginManagement khác plugins

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

`pluginManagement` là nơi **quản lý version/cấu hình được áp dụng khi plugin được sử dụng** bởi project/lifecycle/child. Nó **không tự buộc mọi goal của plugin chạy** chỉ vì có entry. Với packaging `jar`, Compiler Plugin vốn được lifecycle bind vào `compile` và `test-compile`, nên managed version/cấu hình có thể áp dụng ngay trong những phase đó.

Sử dụng parent POM để pin plugin versions là thực hành tốt, nhưng hãy nhìn cả `<build><plugins>`, `pluginManagement` và lifecycle binding khi giải thích nguồn tham số thực tế.

### 2.4. Build plugins và reporting plugins

Build plugin nằm trong `<build><plugins>`; reporting plugin thường được cấu hình trong `<reporting><plugins>` để tạo báo cáo/site. Cấu hình goal report và goal build có thể không hoàn toàn dùng cùng bộ tham số.

Không mang nguyên một đoạn `<reporting>` vào `<build>` mà không xem tài liệu plugin hỗ trợ cách gọi nào. Tương tự, parameter ở goal `report` không nhất thiết tồn tại ở `compile` dù cùng plugin.

## 3. Tên thẻ XML được chọn như thế nào?

### 3.1. Tên parameter, không phải tên plugin hoặc type

Với Maven Compiler Plugin, ví dụ:

```xml
<configuration>
    <release>17</release>
    <showWarnings>true</showWarnings>
</configuration>
```

`release` là tên tham số mà plugin khai báo; Maven không tự hiểu `<javaTargetVersion>17</javaTargetVersion>` là tương đương. XML phân biệt chữ hoa và chữ thường.

Tương tự:

- `<encoding>UTF-8</encoding>` có thể là parameter của Resources/Compiler Plugin khi tài liệu goal tương ứng cho biết.
- `<includes>` có thể là một collection, bên trong có `<include>`.
- `<archive>` có thể ánh xạ sang object cấu hình phức hợp chứa `<manifest>` và `<mainClass>`.
- `<systemPropertyVariables>` của Surefire ánh xạ tới cấu hình system properties truyền cho test JVM.

**Không có một từ điển thẻ `<configuration>` toàn Maven.** Mỗi plugin/goal quyết định những tên và kiểu parameter được hỗ trợ. Một plugin có thể dùng alias lịch sử, tên property ngoài CLI khác tên field hoặc thay đổi tên tham số giữa các release.

### 3.2. @Parameter, property, alias, defaultValue

Ví dụ minh họa:

```java
@Parameter(property = "demo.retry", defaultValue = "3")
private int retryCount;
```

Kết quả mong muốn:

- XML dùng tên parameter `<retryCount>5</retryCount>`, nếu plugin không có tên/alias khác.
- `-Ddemo.retry=5` là cách truyền thông qua **user property** khi plugin hỗ trợ property đó và cấu hình áp dụng không ghi đè theo cách khác.
- `defaultValue=3` được plugin dùng nếu không có giá trị ưu tiên áp dụng.
- `@Parameter(alias = "retries")` (nếu plugin khai báo) có thể chấp nhận thêm tên `<retries>` theo metadata và cách triển khai phiên bản plugin.

**Không dùng `-DretryCount=5` chỉ vì field Java có tên retryCount**. Maven không tự công bố một user property cho mọi Mojo field. Xem goal documentation, thông thường có dòng **User Property: ...**.

### 3.3. Parameter và user property có thể khác tên

Maven Compiler Plugin là ví dụ:

```xml
<configuration>
    <release>${maven.compiler.release}</release>
</configuration>
```

Trong POM:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Ở đây:

- XML element nhận bởi Mojo: `release`.
- Biểu thức nội suy từ POM/Maven session: `${maven.compiler.release}`.
- Property name: `maven.compiler.release`.

CLI có thể cung cấp property thích hợp bằng `-Dmaven.compiler.release=21` trong môi trường tương thích. Tuy nhiên, **đừng suy rằng CLI `-D...` luôn ghi đè một giá trị XML cứng** như `<release>17</release>`; kết quả tùy cấu hình và parameter expression. Cách rõ nhất là khai báo một property và tham chiếu nó trong `<configuration>`, hoặc dùng parameter user property đã được tài liệu plugin hỗ trợ.

### 3.4. Không thể tùy tiện invent parameter

Ví dụ sai:

```xml
<configuration>
    <javaVersion>17</javaVersion>
    <doCompilationFaster>true</doCompilationFaster>
</configuration>
```

Nếu goal không khai báo những tham số trên, Maven/plugin có thể cảnh báo về parameter không được nhận, bỏ qua cấu hình hoặc báo lỗi tùy phiên bản/implementation; **không có cam kết nó sẽ hiểu ý định**. Một build thành công chưa chứng minh mọi thẻ XML đều có tác dụng.

Hãy dùng plugin help/documentation để kiểm tra tên parameter trước khi sửa.

## 4. Ánh xạ dữ liệu đơn giản: string, boolean, số, File, enum

Thông tin trong `<configuration>` ở dạng XML text, nhưng field Java có thể là kiểu khác. Maven/Plexus thực hiện chuyển đổi khi inject vào Mojo.

| Kiểu tham số Java (ví dụ) | XML | Điều cần chú ý |
| --- | --- | --- |
| `String` | `<encoding>UTF-8</encoding>` | Chuỗi được chuyển thành nội dung parameter |
| `boolean/Boolean` | `<showWarnings>true</showWarnings>` | Giá trị `true`/`false`, tránh typo hoặc để trống |
| `int/Integer` | `<retryCount>3</retryCount>` | Phải chuyển đổi được thành số phù hợp |
| `long/Long` | `<timeoutMillis>5000</timeoutMillis>` | Tên thẻ chỉ minh họa; phải thuộc goal cụ thể |
| `double/Double` | `<ratio>0.5</ratio>` | Chuyển từ string sang số |
| `java.io.File` | `<outputDirectory>${project.build.directory}/docs</outputDirectory>` | Đường dẫn tương đối thường được resolve theo project basedir |
| `java.net.URL/URI` | `<endpoint>https://example.org</endpoint>` | Đầu vào phải hợp lệ theo kiểu và plugin |
| `enum` | `<strategy>FAST</strategy>` | Phải khớp giá trị enum Java (thường phân biệt hoa/thường) |

**Lưu ý quan trọng:** các tên `retryCount`, `timeoutMillis`, `ratio`, `endpoint`, `strategy` là **minh họa cho kiểu dữ liệu**, không phải thông số được bảo đảm có trong Maven Compiler Plugin. Nếu dùng trên một goal thực, hãy kiểm tra goal docs.

Khi XML không chuyển được kiểu, có thể có thông báo kiểu `Cannot convert 'abc' to int`, lỗi cấu hình Mojo hoặc plugin failure. Không sửa lỗi này bằng cách đổi dependency version vô tội vạ; điều tra **parameter type và giá trị thực sau nội suy**.

### 4.1. File path và platform

Với parameter kiểu `File`, Maven/Plexus thường chuẩn hóa dấu phân tách và chuyển đường dẫn tương đối thành absolute dựa trên project directory. Nên dùng:

```xml
<outputDirectory>${project.build.directory}/generated</outputDirectory>
```

thay vì đường dẫn tuyệt đối chỉ đúng trên một máy. Khi phải dùng Windows paths, XML text không đòi escape dấu `\` như Java String; nhưng shell/CI có quy tắc escape riêng.

Maven có thể chạy trong multi-module build ở nhiều basedir khác nhau, do đó file relative path cần kiểm thử từ đúng module.

## 5. Ánh xạ collection: List, Set và array

Đây là lý do các tham số cấu hình thường có **thẻ cha số nhiều** và nhiều **thẻ con số ít**:

```xml
<configuration>
    <includes>
        <include>**/*Test.java</include>
        <include>**/*IT.java</include>
    </includes>
</configuration>
```

Giả sử goal hỗ trợ `List<String> includes` (ví dụ Surefire cho một số goal), Maven tạo collection chứa hai pattern. Tên child element trong collection thường dùng một tên mô tả; cơ chế mapping có thể dựa vào kiểu item, `implementation` hint và parameter metadata, không nhất thiết đòi mỗi thẻ phải có một Java field.

Ví dụ tương ứng với một Mojo tự viết:

```java
@Parameter
private List<String> names;
```

```xml
<configuration>
    <names>
        <name>Alice</name>
        <name>Bob</name>
    </names>
</configuration>
```

Trong các Maven version hỗ trợ, với collection/array có phần tử đơn giản, một số cấu hình còn có dạng danh sách phân cách dấu phẩy như `<names>Alice,Bob</names>`. **Không áp dụng mặc định cho mọi plugin hoặc mọi kiểu collection**, đặc biệt khi item là object phức tạp; ưu tiên cấu trúc XML được minh họa trong plugin docs.

Những điều cần tránh:

- `<includes>**/*Test.java</includes>` có thể hợp lệ cho một số List, nhưng không bảo đảm các goal khác tự chia chuỗi.
- `<include>` đặt ngang hàng với `<includes>` thường không đúng vì Mojo nhận parameter tên `includes` chứ không nhận một parameter `include`.
- Thứ tự item quan trọng với nhiều plugin (filter, search path, compiler options); không tự sắp xếp lại khi tối ưu POM.
- Đừng trộn `combine.children=append` với suy nghĩ rằng Maven sẽ loại duplicate items; append có thể giữ phần tử trùng.

## 6. Ánh xạ Map và Properties: nhìn giống XML nhưng kiểu khác nhau

### 6.1. Map<String, String>

Một parameter Java:

```java
@Parameter
private Map<String, String> labels;
```

thường dùng XML:

```xml
<configuration>
    <labels>
        <service>orders</service>
        <owner>platform</owner>
    </labels>
</configuration>
```

Hai thẻ `<service>`, `<owner>` là **keys của map**, còn nội dung là values. Trong mapping Maven thông dụng, Map key là String, và value type được rút từ generic parameter type (fallback có thể là String).

Ví dụ thực tế, Surefire Plugin cung cấp `systemPropertyVariables`:

```xml
<configuration>
    <systemPropertyVariables>
        <demo.test.mode>strict</demo.test.mode>
        <feature.enabled>true</feature.enabled>
    </systemPropertyVariables>
</configuration>
```

Đây là system properties được truyền vào test JVM **khi Surefire chạy goal test**. Cách đặt dấu chấm trong tên key là hợp lệ trong XML element name. Không được suy từ XML này rằng Maven tự đặt `System.setProperty(...)` cho **mọi Java process** hoặc ứng dụng production được gọi bằng `java -jar`; nó thuộc phạm vi Surefire test.

### 6.2. java.util.Properties

Một parameter kiểu `Properties` có thể dùng cấu trúc khác với Map:

```xml
<configuration>
    <myProperties>
        <property>
            <name>color</name>
            <value>blue</value>
        </property>
        <property>
            <name>size</name>
            <value>large</value>
        </property>
    </myProperties>
</configuration>
```

Đây là cấu trúc minh họa mapping `java.util.Properties` của Maven Plugin Configuration Guide. **Không thay thế mọi cấu hình `systemPropertyVariables` của Surefire bằng mẫu `<property><name>...`**, vì mỗi plugin parameter có kiểu và schema thực tế riêng.

Map và Properties thường không có cú pháp chuyển trực tiếp từ một string CLI `-DsomeMap=...` theo cơ chế mapping phổ quát. Nếu plugin hỗ trợ cách nhập khác, đó phải là hành vi cụ thể có tài liệu.

## 7. Ánh xạ object lồng nhau: nested beans và plugin-specific model

Một số tham số là một object phức hợp thay vì một giá trị đơn giản. Maven dùng XML lồng nhau:

```xml
<configuration>
    <archive>
        <manifest>
            <mainClass>vn.example.mapping.App</mainClass>
        </manifest>
    </archive>
</configuration>
```

Với Maven JAR Plugin, `archive` là tham số cấu hình Maven Archiver; `manifest` là object con và `mainClass` là thuộc tính của manifest configuration. XML này không có nghĩa Mojo class phải trực tiếp chứa field `mainClass` — nó có thể nằm **bên trong object được truyền vào parameter `archive`**.

Đây là khác biệt lớn giữa:

```xml
<configuration>
    <mainClass>vn.example.mapping.App</mainClass>
</configuration>
```

và cấu trúc đúng mà goal JAR Plugin yêu cầu (`archive/manifest/mainClass`). Nếu plugin chỉ nhận `archive`, việc đưa `mainClass` lên cấp ngoài có thể bị bỏ qua hoặc gây lỗi cấu hình.

Một số plugin cho phép attribute `implementation` để chỉ định class Java của nested object khi cơ chế tự suy kiểu không đủ. **Chỉ sử dụng khi plugin docs nói rõ**, vì nó phụ thuộc class có mặt trong plugin realm và API internal; không phải cơ chế tiêm arbitrary class không giới hạn.

## 8. Plugin-level, execution-level và CLI: cùng goal có thể nhận cấu hình khác nhau

Đặt:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <encoding>UTF-8</encoding>
    </configuration>
    <executions>
        <execution>
            <id>copy-extra-resources</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>copy-resources</goal>
            </goals>
            <configuration>
                <outputDirectory>${project.build.directory}/extra</outputDirectory>
                <resources>
                    <resource>
                        <directory>src/extra</directory>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đoạn này dùng `UTF-8` làm cấu hình chung và cấu hình output cụ thể của execution `copy-extra-resources`.

Nếu chạy `mvn package`, Maven đi qua phase `prepare-package` nên execution này có cơ hội chạy, miễn file structure và plugin resolution hợp lệ. Nếu chạy `mvn resources:copy-resources` trực tiếp, goal được gọi trong **ngữ cảnh command-line execution**; không nên giả định nó tự chọn execution `copy-extra-resources`.

Khi cần gọi một execution theo ID trên Maven 3.3.1+, cú pháp có thể là:

```bash
mvn resources:copy-resources@copy-extra-resources
```

Để tránh nhập nhằng về plugin prefix, có thể gọi plugin đầy đủ bằng `groupId:artifactId:version:goal@execution-id` khi được hỗ trợ bởi Maven version tương ứng.

Một số execution IDs đặc biệt gắn với lifecycle/default command-line, như `default-compile` hoặc `default-cli`, có quy tắc ghép riêng. Tài liệu chính thức **Guide to Configuring Default Mojo Executions** trình bày rõ hai cấp cấu hình. Nguyên tắc học tập: **kiểm tra execution thực sự được gọi**, không chỉ đọc có `<configuration>` ở một vị trí nào đó.

## 9. Một ví dụ Java 17 hoàn chỉnh kiểm chứng bốn kiểu mapping

Mục tiêu thực hành:

- `maven-compiler-plugin` nhận **scalar** `release` (version Java) và `showWarnings` (boolean).
- `maven-resources-plugin` nhận **String encoding**, collection `delimiters` và boolean `useDefaultDelimiters` để lọc file text.
- `maven-surefire-plugin` nhận **List includes** và **Map systemPropertyVariables** để cấu hình test.
- `maven-jar-plugin` nhận **nested object** `archive/manifest/mainClass` để tạo JAR có thể chạy bằng `java -jar`.

Dự án chỉ cần **JDK 17+**, Maven 3.9.x, kết nối để resolve Maven plugins/JUnit lần đầu và các tệp bên dưới.

### 9.1. Cấu trúc file

```text
plugin-config-mapping/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/mapping/App.java
    │   └── resources/banner.properties
    └── test/
        └── java/vn/example/mapping/AppTest.java
```

### 9.2. POM đầy đủ

File `plugin-config-mapping/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>plugin-config-mapping</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.banner>configuration-ok</demo.banner>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
            </resource>
        </resources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>${maven.compiler.release}</release>
                    <showWarnings>true</showWarnings>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <includes>
                        <include>**/*Test.java</include>
                    </includes>
                    <systemPropertyVariables>
                        <demo.test.mode>strict</demo.test.mode>
                    </systemPropertyVariables>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
                <configuration>
                    <archive>
                        <manifest>
                            <mainClass>vn.example.mapping.App</mainClass>
                        </manifest>
                    </archive>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Những điều cần để ý khi đọc POM:**

1. `<resources><resource><filtering>true</filtering>` ở cấp `<build>` là **POM build model** chỉ định nguồn resource cần lọc; còn `<delimiters>` trong `maven-resources-plugin/<configuration>` là **Mojo parameter** xác định ký hiệu nội suy.
2. `<release>${maven.compiler.release}</release>` là **plugin parameter** nhận một string đã được nội suy từ POM property; không phải mọi thẻ dưới `<properties>` đều tự trở thành parameter của plugin.
3. `<includes>` là List pattern; `systemPropertyVariables` là Map, tạo test JVM property `demo.test.mode`.
4. `<archive><manifest><mainClass>...` tạo manifest có `Main-Class`, cho phép JAR chạy bằng `java -jar` với project không có runtime library ngoài JDK.
5. Các plugin versions được pin, không phụ thuộc ngẫu nhiên vào phiên bản tìm được mới nhất từ repository.
6. `junit-jupiter` ở scope `test` chỉ cần cho unit test; không phải runtime dependency cần đóng chung vào JAR.

### 9.3. Resource template có delimiter @

File `src/main/resources/banner.properties`:

```properties
banner=@demo.banner@
```

Giá trị `@demo.banner@` được Maven Resources Plugin thay thế khi chạy goal `resources:resources` trong phase `process-resources`. Vì `<filtering>true</filtering>` và `<delimiters><delimiter>@</delimiter></delimiters>`, kết quả tại `target/classes/banner.properties` là:

```properties
banner=configuration-ok
```

Đây là **file trong thư mục output**, không phải file nguồn bị chỉnh sửa. Plugin copy/filter resources vào target; `src/main/resources/banner.properties` vẫn giữ placeholder.

Không nên bật resource filtering tùy tiện cho ảnh, zip, PDF hoặc các file nhị phân: nội suy text có thể làm hỏng bytes. Trong project thực, tách thư mục resources cần filtering khỏi binary resources.

### 9.4. File Java chính

File `src/main/java/vn/example/mapping/App.java`:

```java
package vn.example.mapping;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class App {
    private App() {
    }

    public static String banner() {
        try (InputStream in = App.class.getResourceAsStream("/banner.properties")) {
            if (in == null) {
                throw new IllegalStateException("Missing /banner.properties");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).strip();
        } catch (IOException e) {
            throw new IllegalStateException("Cannot read /banner.properties", e);
        }
    }

    public static void main(String[] args) {
        System.out.println("Resource: " + banner());
    }
}
```

Class dùng các API Java có sẵn. `getResourceAsStream("/banner.properties")` tìm resource ở root classpath trong JAR hoặc `target/classes`. `strip()` bỏ xuống dòng/whitespace ở đầu và cuối để stdout không phụ thuộc line ending của file resource. Nếu resource chưa được copy, chương trình báo lỗi rõ ràng thay vì im lặng.

### 9.5. Unit test cho resource filtering và Surefire property

File `src/test/java/vn/example/mapping/AppTest.java`:

```java
package vn.example.mapping;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void readsFilteredResource() {
        assertEquals("banner=configuration-ok", App.banner());
    }

    @Test
    void receivesSurefireProperty() {
        assertEquals("strict", System.getProperty("demo.test.mode"));
    }
}
```

Test đầu xác nhận Resources Plugin đã chuyển placeholder thành giá trị đúng. Test thứ hai xác nhận **Map `systemPropertyVariables` trong Surefire** đã truyền property đến test runtime. Nếu bỏ cấu hình systemPropertyVariables mà không có nguồn property khác, test thứ hai sẽ không còn nhận `strict` như mong đợi.

Không đánh đồng Java system property ở test VM với property tài nguyên `demo.banner` trong Maven model; đó là hai nguồn và thời điểm sử dụng khác nhau.

### 9.6. Build và stdout kiểm chứng

Đứng trong thư mục `plugin-config-mapping`:

```bash
java -version
mvn --version
mvn -B clean verify
java -jar target/plugin-config-mapping-1.0.0.jar
```

**Điều kiện:** Maven chạy bằng JDK 17+ (theo `mvn --version`) và có thể tải các plugin/JUnit từ repository cấu hình. `clean verify` đi qua resources, compile, test, jar và verify phase.

Stdout **chính xác của lệnh `java -jar`** là:

```text
Resource: banner=configuration-ok
```

Đây không phải toàn bộ log `mvn clean verify`. Maven/Surefire sẽ in test summary và plugin log khác nhau theo version, môi trường và flags. Thành công của build cùng stdout trên giúp kiểm chứng một số tham số đã hoạt động:

- Resources Plugin lọc `@demo.banner@` ra `configuration-ok`.
- Compiler Plugin biên dịch theo release 17.
- Surefire chạy hai JUnit tests, trong đó test đọc property `demo.test.mode=strict`.
- JAR Plugin ghi Main-Class vào manifest, cho phép `java -jar`.

### 9.7. Kiểm tra artifact và cấu hình thực tế

```bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
jar tf target/plugin-config-mapping-1.0.0.jar
```

Tìm hai entry trong output của `jar tf`:

```text
vn/example/mapping/App.class
banner.properties
```

Đây là các entry cần tìm, **không phải toàn bộ stdout của `jar tf`**. File JAR còn có metadata `META-INF` và manifest.

Để xem manifest:

```bash
unzip -p target/plugin-config-mapping-1.0.0.jar META-INF/MANIFEST.MF
```

`unzip` chỉ có sẵn khi máy đã cài utility này; Windows không mặc nhiên có `unzip`. Có thể dùng `jar xf` trong một thư mục kiểm thử riêng để trích manifest nếu không có unzip.

Trong `META-INF/MANIFEST.MF`, phải tìm một dòng tương ứng:

```text
Main-Class: vn.example.mapping.App
```

Tương tự, kiểm tra `target/classes/banner.properties` sau resources phase để xác nhận filter; dùng trình đọc text, không phải sửa file output bằng tay.

**Giới hạn của effective POM:** nó hiển thị cấu hình đã merge và nội suy theo model, nhưng **không phải một bản dump chính xác mọi field Java sau khi Mojo được inject**. Đối với parameter runtime, kết hợp tài liệu goal, log Maven/plugin và kết quả chạy/test.

## 10. Lệnh kiểm tra plugin parameter và tên XML chính xác

### 10.1. Help goal của plugin

Nhiều plugin Maven chính thức có goal `help` hỗ trợ `-Ddetail` và `-Dgoal`. Ví dụ:

```bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:help -Ddetail -Dgoal=compile
mvn org.apache.maven.plugins:maven-resources-plugin:3.3.1:help -Ddetail -Dgoal=resources
mvn org.apache.maven.plugins:maven-surefire-plugin:3.5.2:help -Ddetail -Dgoal=test
mvn org.apache.maven.plugins:maven-jar-plugin:3.4.2:help -Ddetail -Dgoal=jar
```

Những lệnh này cần repository có plugin tương ứng. Tài liệu từng goal thường cung cấp:

- **Parameter name**: tên thẻ XML trong `<configuration>`.
- **Type**: `String`, `boolean`, `List`, `File`, object...
- **Required**: có bắt buộc hay không.
- **Default Value**: giá trị mặc định của goal/version đó.
- **User Property**: `-D...` tương ứng nếu được hỗ trợ.
- **Since/Read-only**: tham số có từ phiên bản nào hoặc có được cấu hình hay không.

Không nên lấy tài liệu `maven-compiler-plugin` mới nhất rồi áp dụng vô điều kiện cho bản `3.6.1` của dự án cũ. Tham số có thể được thêm, đổi default hoặc không tồn tại ở version cũ.

### 10.2. Maven Help Plugin

Một cách khác:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
```

Goal `help:describe` hiển thị mô tả plugin/goal dựa trên plugin descriptor. Nếu muốn khóa version, xem option mô tả plugin theo tọa độ đầy đủ được Help Plugin version tương ứng chấp nhận hoặc gọi help goal của plugin với version tường minh như mục 10.1.

### 10.3. Khi nào dùng -X?

```bash
mvn -B -X compile
```

Debug log có thể in phần **Mojo configuration** và các giá trị đã được resolve. Đây là cách hữu ích khi một XML parameter không có tác dụng. Tuy nhiên:

- Log debug có thể rất dài và phụ thuộc plugin/version/transport.
- Có thể lộ đường dẫn, URL repository, token hoặc thông tin hạ tầng; **lọc secrets trước khi chia sẻ**.
- Đừng coi mọi giá trị xuất hiện trong log đều đã được plugin sử dụng đúng ý nghĩa; vẫn cần test hành vi.
- Khi goal không chạy, sẽ không có Mojo configuration tương ứng để quan sát; trước hết kiểm tra lifecycle/execution.

## 11. Interpolation: biểu thức Maven, profile và khả năng tái lập

Các tham số có thể dùng giá trị nội suy:

```xml
<configuration>
    <release>${maven.compiler.release}</release>
    <encoding>${project.build.sourceEncoding}</encoding>
</configuration>
```

Các biểu thức này chỉ có ý nghĩa **với những goal thực sự có parameter `release` hoặc `encoding`**. Maven không yêu cầu một plugin bất kỳ hiểu cả hai thẻ.

Nguồn giá trị có thể gồm:

- POM `<properties>` và những properties được kế thừa từ parent.
- Properties do profiles đang active cung cấp.
- Maven session/user properties qua CLI `-Dname=value`.
- Thông tin model như `${project.build.directory}`, `${project.basedir}`.
- Những expressions đặc thù mà Plugin Parameter Expression Evaluator hỗ trợ.

**Không nên nhét secret vào POM plugin configuration**, kể cả thông qua `${env.SECRET}`, nếu nó có thể xuất hiện trong log/debug/build output. Dùng settings credentials, CI secret store và cơ chế plugin được thiết kế cho bí mật.

Với parent, profiles hoặc `-D`, cùng source POM có thể cho **effective configuration khác nhau**. Để build tái lập, pin versions, ghi nhận Maven/JDK/profile/CLI options, và tránh để parameter quan trọng phụ thuộc biến môi trường vô tình có mặt trên laptop.

### 11.1. Hardcoded value và property được phép override

Nếu mục tiêu là cố định Java 17 cho toàn tổ chức, có thể để:

```xml
<configuration>
    <release>17</release>
</configuration>
```

Nếu mục tiêu cho phép từng CI pipeline chọn target được duyệt:

```xml
<configuration>
    <release>${maven.compiler.release}</release>
</configuration>
```

và quản lý `maven.compiler.release` ở parent/child/CI. Cách sau linh hoạt nhưng làm tăng yêu cầu test và policy enforcement. Nhất là khi test trên JDK 17 mà truyền compiler release 21, compilation sẽ thất bại vì JDK 17 không có khả năng sinh target 21; property không tự cài JDK mới.

### 11.2. Phân biệt property của Maven với system properties của test JVM

`${demo.banner}` được Maven Resources Plugin resolve khi copy/filter resource. Ngược lại, `systemPropertyVariables` của Surefire được chuyển cho JVM chạy test theo cấu hình Surefire. Không nên mong `System.getProperty("demo.banner")` luôn tồn tại chỉ vì POM có:

```xml
<properties>
    <demo.banner>configuration-ok</demo.banner>
</properties>
```

Nếu muốn test JVM nhận nó, phải truyền theo cơ chế plugin phù hợp (ví dụ Surefire `systemPropertyVariables`), đồng thời kiểm tra cách properties được merge và precedence từ CLI.

## 12. Kế thừa và merge configuration giữa parent, child và profile

Cấu hình plugin có thể đến từ parent POM, `pluginManagement`, child POM và profiles đang active. Maven merge XML configuration theo quy tắc cụ thể, **không phải một phép thay thế toàn bộ mọi node**.

### 12.1. Giá trị child có thể override giá trị parent

Parent:

```xml
<configuration>
    <release>17</release>
    <showWarnings>true</showWarnings>
</configuration>
```

Child của cùng plugin:

```xml
<configuration>
    <showWarnings>false</showWarnings>
</configuration>
```

Sau merge, cấu hình hiệu lực của child có thể giữ `release=17` và ghi đè `showWarnings=false`. Điều này phù hợp khi tổ chức muốn chia sẻ mặc định nhưng cho project tùy chỉnh một số tham số.

Không nên khẳng định mọi node parent đều bị child ghi đè, vì cách merge phụ thuộc cấu trúc/ID và điều kiện inheritance. Xem effective POM của chính module.

### 12.2. combine.children="append" cho collection

Ví dụ từ POM Reference: parent có:

```xml
<configuration>
    <includes>
        <include>parent-a</include>
        <include>parent-b</include>
    </includes>
</configuration>
```

Child định nghĩa:

```xml
<configuration>
    <includes combine.children="append">
        <include>child-c</include>
    </includes>
</configuration>
```

Khi merge, collection có thể có ba item theo thứ tự parent-a, parent-b, child-c. `combine.children="append"` là **attribute điều khiển merge POM**, không phải parameter Java của plugin.

Nếu child chỉ muốn **thay thế** parent list/section, dùng:

```xml
<configuration>
    <includes combine.self="override">
        <include>child-only</include>
    </includes>
</configuration>
```

`combine.self="override"` yêu cầu node child thay node parent. Đừng đặt cả `combine.self="override"` và `combine.children="append"` trên cùng node rồi mong cả hai cùng có tác dụng; override sẽ ưu tiên.

### 12.3. Cấu hình trong executions được merge theo ID

Hai POM ở chuỗi parent–child có execution cùng `<id>` có thể được merge với cấu hình child ưu tiên theo quy tắc; execution khác ID được giữ như những execution riêng biệt. Vì vậy:

- Thay đổi `execution.id` có thể làm một goal bị chạy hai lần thay vì override execution cũ.
- Cấu hình ở execution A không tự áp dụng cho execution B.
- `inherited=false` có thể dùng để giới hạn kế thừa plugin/execution khi thích hợp.
- Profile ở parent khi active có thể thêm execution vào model mà child kế thừa, nhưng profile definition bản thân không tự được inherited.

Trong hệ thống multi-module, một thay đổi nhỏ ở parent có thể ảnh hưởng toàn bộ children. Khi sửa plugin config, kiểm tra cả modules khác, đặc biệt khi parameter là List/Map hay execution có phase binding.

## 13. Lỗi phổ biến khi ánh xạ XML sang parameter

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Plugin không nhận `<javaVersion>17</javaVersion>` | Tên parameter không tồn tại | Xem goal help: tên đúng có thể là `release` |
| `-Dtimeout=10` không tác dụng | Property CLI khác tên parameter hoặc XML hardcode ghi đè | Xem **User Property** trong goal docs, effective configuration |
| Sửa `pluginManagement` mà goal vẫn không chạy | Chỉ khai báo management, chưa có execution/lifecycle mapping | Xem `<build><plugins>`, phase, packaging |
| List thiếu item parent hoặc bị nhân đôi | Quy tắc merge XML khác mong đợi | Xem `combine.children`, effective POM |
| Map `systemPropertyVariables` không đến Java app production | Surefire truyền property cho test process, không phải mọi process | Kiểm tra phạm vi test JVM và launch command |
| Nested `<mainClass>` không có tác dụng | Sai cấp XML so với plugin archiver model | Dùng `archive/manifest/mainClass` |
| `Cannot convert ...` | Không đổi được từ string sang kiểu parameter | Sửa giá trị đúng kiểu, xem docs |
| POM đọc được nhưng test không chạy | Surefire includes pattern sai, class không đúng tên hoặc JUnit provider | Xem Surefire report, goal config và test files |
| `mvn compiler:compile` khác `mvn compile` | Khác execution/lifecycle context | So sánh plugin-level và execution-level config |
| Chạy `mvn package` nhưng goal `verify` không chạy | `package` dừng trước phase `verify` | Gọi `mvn verify` khi cần |
| XML chứa ký tự `&` thô | XML parsing yêu cầu `&amp;` | Escape XML entities đúng cách |
| Resource giữ nguyên `@demo.banner@` | `filtering=false`, delimiter sai hoặc property thiếu | Kiểm tra target/classes và Resources Plugin config |
| Maven build thành công nhưng option typo không có tác dụng | Unknown parameter có thể bị cảnh báo/bỏ qua | Đọc log và plugin docs, test output |
| Hai plugin versions khác nhau giữa máy | Plugin version không pin hoặc parent/profiles khác | Pin versions; `help:effective-pom` |
| Maven Debug log lộ nội bộ | `-X` in configuration/paths/repositories | Hạn chế log, lọc secrets và quyền truy cập |

### 13.1. Chẩn đoán theo thứ tự

1. **Đọc lỗi và xác định plugin + goal + version** thật sự chạy.
2. **Xác minh phase/execution**: goal có được gọi không? Từ CLI hay từ lifecycle?
3. **Mở tài liệu tham số của đúng goal/version**, đọc Type, Default, User Property.
4. **Kiểm tra vị trí thẻ XML**: plugin-level, execution-level, build vs reporting, POM model vs Mojo parameter.
5. **Kiểm tra effective POM** để thấy inheritance/merge/profile và interpolation.
6. **Kiểm tra plugin log hoặc `-X`** trong môi trường được phép nếu nghi giá trị injected sai.
7. **Thử hành vi quan sát được**: file output, manifest, JUnit assertion, Java stdout.
8. **Chỉ sửa đúng một nguyên nhân**, build lại để chứng minh; không thay plugin version hoặc xóa cache theo phản xạ.

## 14. Checklist thiết kế plugin configuration dễ bảo trì

- Pin `groupId/artifactId/version` của plugin; đừng phụ thuộc bản ngẫu nhiên.
- Dùng tham số đúng tên và đúng XML nesting theo goal docs.
- Đặt giá trị chung cấp plugin; giá trị khác theo lần chạy ở cấp execution.
- Dùng `pluginManagement` cho policy/version chung, nhưng nhớ rằng nó không tự bật mọi goal.
- Ghim Java compiler release phù hợp JDK chạy Maven và môi trường deploy.
- Ưu tiên properties rõ ràng để quản lý giá trị cần override; không đặt nhiều nguồn cấu hình trùng tên không kiểm soát.
- Giữ `List/Map/Properties` đúng format và kiểm tra merge khi có parent-child.
- Tránh dùng `combine.children="append"` khi mục đích là thay thế một danh sách.
- Test plugin output thực tế, không chỉ quan sát POM hợp lệ.
- Tách credentials khỏi POM/CI logs; các tham số chứa secret cần quản lý bằng secret store và plugin mechanism phù hợp.
- Khi plugin upgrade, xem changelog và help của **bản mới**, chạy test trên những module dùng goal đó.
- Với multi-module builds, kiểm tra effective POM của **từng module bị ảnh hưởng**.
- Phân biệt build configuration trong POM với cài đặt môi trường Maven trong `settings.xml`: mirror/servers/proxy không phải Mojo parameters.

## 15. Câu hỏi tự luyện có đáp án

**Câu 1.** Trong Compiler Plugin, vì sao `<release>17</release>` có tác dụng còn `<javaVersion>17</javaVersion>` có thể không có tác dụng?

**Đáp án:** Maven inject XML child theo tên parameter mà goal hỗ trợ; tên đúng là `release` cho compiler goal tương ứng. `javaVersion` không phải tên thay thế phổ quát. Kiểm tra help của đúng plugin version.

**Câu 2.** Mojo có `@Parameter(property="demo.label") private String label`. XML và CLI đặt giá trị thế nào?

**Đáp án:** XML dùng `<label>hello</label>` trong `<configuration>`; CLI có thể dùng `-Ddemo.label=hello` khi plugin hỗ trợ user property đó và precedence/cấu hình không cản trở. Không tự động dùng `-Dlabel` chỉ vì field tên `label`.

**Câu 3.** Surefire khai báo `<systemPropertyVariables><feature.enabled>true</feature.enabled></systemPropertyVariables>`. Một lệnh `java -jar app.jar` có tự nhận property này không?

**Đáp án:** Không. Đây là cấu hình của Surefire khi chạy tests; JVM ứng dụng chạy độc lập không tự nhận system property chỉ vì POM đã cấu hình Surefire.

**Câu 4.** Parent plugin có `<includes>` hai phần tử; child muốn giữ chúng và thêm một phần tử. Cần xem gì?

**Đáp án:** Xem cách Maven merge `<configuration>` và dùng `combine.children="append"` trên node collection khi phù hợp. Xác minh effective POM để chắc chắn danh sách đã được nối theo ý định.

**Câu 5.** Muốn JAR chạy bằng `java -jar` nhờ Main-Class, nên đặt XML thế nào trong Maven JAR Plugin?

**Đáp án:** Trong `<configuration>` dùng `<archive><manifest><mainClass>...</mainClass></manifest></archive>` theo Maven Archiver model. Đừng đoán `<mainClass>` là parameter root của Mojo.

**Câu 6.** Một plugin có `<configuration>` nhưng không thực thi khi chạy `mvn package`. Vì sao?

**Đáp án:** Configuration chỉ cung cấp tham số; còn goal phải được bind vào phase đi qua hoặc gọi trực tiếp. Nếu execution bind ở `verify` thì `mvn package` chưa tới phase đó; nếu chỉ có `pluginManagement`, goal không tự chạy trừ khi lifecycle hoặc plugin declaration gọi nó.

**Câu 7.** Có thể xác nhận tham số đã được dùng chỉ bằng `mvn help:effective-pom` không?

**Đáp án:** Chưa đủ. Effective POM cho cấu hình đã merge; cần thêm goal docs và kiểm tra output/test/plugin log để chứng minh Mojo sử dụng tham số đúng ý định.

## Tài liệu chính thức

- [Apache Maven — Guide to Configuring Plug-ins: Generic Configuration, Mapping Value Objects, Collections, Maps, Properties, Executions](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — POM Reference: Plugin Configuration Inheritance, combine.children, combine.self](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
- [Apache Maven Plugin Tools — @Parameter Annotation API](https://maven.apache.org/plugin-tools/apidocs/org/apache/maven/plugins/annotations/Parameter.html)
- [Apache Maven Compiler Plugin — compiler:compile Parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Apache Maven Resources Plugin — resources:resources Parameters](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html)
- [Apache Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven Surefire Plugin — Using System Properties](https://maven.apache.org/surefire/maven-surefire-plugin/examples/system-properties.html)
- [Apache Maven JAR Plugin — Executable JAR](https://maven.apache.org/plugins/maven-jar-plugin/examples/executable-jar.html)
- [Apache Maven Help Plugin — describe](https://maven.apache.org/plugins/maven-help-plugin/describe-mojo.html)
