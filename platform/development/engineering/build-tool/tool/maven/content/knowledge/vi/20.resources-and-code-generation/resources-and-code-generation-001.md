# Maven Resources Plugin và các bước resources, testResources

## 1. Resources là gì và tại sao Maven cần copy chúng?

Một dự án Java bao gồm nhiều thứ không phải source code: `application.properties`, `.yaml`, `.xml`, template, ảnh, tệp bản địa hóa, văn bản, metadata, fixtures dùng trong tests hoặc các file cần truy cập qua classpath. Những file này được gọi là **resources**. Maven Resources Plugin giúp **sao chép** chúng từ source tree vào output của build và **có thể lọc nội dung** để thay token theo các thuộc tính của Maven.

Hai goal cần phân biệt:

- **`resources:resources`**: xử lý **main resources**, thường đọc `src/main/resources` và copy vào **`target/classes`**; mặc định bind vào phase **`process-resources`**.
- **`resources:testResources`**: xử lý **test resources**, thường đọc `src/test/resources` và copy vào **`target/test-classes`**; mặc định bind vào phase **`process-test-resources`**.

Hai goal này không biên dịch Java và không chạy unit tests. Compilation được Maven Compiler Plugin thực hiện, unit tests thường được Maven Surefire Plugin thực hiện. Việc gọi `mvn test` trong dự án `jar` chuẩn sẽ chạy các phase cần thiết để xử lý main/test resources trước khi tests thực sự chạy.

**Tình huống:** ứng dụng cần đọc `banner.txt` và `app.properties` từ classpath; unit test cần thêm `fixtures/sample.txt` và `test.properties`. Bạn muốn Maven thay `@project.version@` bằng version hiện tại khi build, nhưng không được sửa placeholder `${spring.profiles.active}` dành cho runtime. Maven Resources Plugin giải quyết yêu cầu này, nếu cấu hình **nguồn**, **filtering** và **delimiter** đúng.

Sau bài học, người đọc có thể:

1. Giải thích phase, goal, main resources và test resources.
2. Phân biệt `target/classes`, `target/test-classes` và các resource roots trong POM.
3. Cấu hình `<resources>`, `<testResources>`, `filtering`, `includes/excludes` và `targetPath`.
4. Hiểu filtering theo `@...@` hoặc `${...}`, filters file và encoding.
5. Bảo vệ file nhị phân khỏi filtering, tránh leak secret và output trùng đường dẫn.
6. Đọc file bằng Java 17 ClassLoader và xác minh resource trong JAR.
7. Dùng đúng `resources:resources`, `resources:testResources` hoặc các lifecycle phases để debug.
8. Chạy ví dụ Java 17 + JUnit 5 hoàn chỉnh và tự kiểm chứng stdout, test output, artifact.

## 2. So sánh resources với testResources

| Câu hỏi | `resources:resources` | `resources:testResources` |
| --- | --- | --- |
| Mục đích | Copy resource dùng cho mã ứng dụng | Copy resource riêng cho tests |
| Nguồn mặc định | `src/main/resources` | `src/test/resources` |
| Khai báo nguồn trong POM | `build/resources` | `build/testResources` |
| Phase mặc định | `process-resources` | `process-test-resources` |
| Output mặc định | `${project.build.outputDirectory}` — thường `target/classes` | `${project.build.testOutputDirectory}` — thường `target/test-classes` |
| Được main JAR đóng gói mặc định? | Thường có, vì JAR lấy main output | Không, vì JAR thông thường không lấy test output |
| Có thể dùng filtering? | Có | Có |
| Có tự compile Java? | Không | Không |
| Có tự chạy JUnit tests? | Không | Không |

**Phân biệt rất quan trọng:** Maven không copy main resources vào test output chỉ vì unit test đọc được chúng. Test classpath thông thường chứa **cả `target/test-classes` và `target/classes`**, nên unit test có thể đọc `app.properties` ở `target/classes` và fixture ở `target/test-classes`. Không nên nhầm việc **có trên test classpath** với **được testResources copy**.

### 2.1. Goal khác lifecycle phase

Các lệnh này có semantics khác nhau:

~~~bash
mvn process-resources
mvn org.apache.maven.plugins:maven-resources-plugin:3.5.0:resources
mvn process-test-resources
mvn org.apache.maven.plugins:maven-resources-plugin:3.5.0:testResources
~~~

Lệnh bắt đầu bằng tên phase yêu cầu Maven chạy **default lifecycle đến phase đó**. Lệnh có tên plugin/goal chỉ gọi **một goal trực tiếp**, không tự chạy cả compilation và test lifecycle. Có thể gọi `resources:resources` để kiểm tra copy/filter nhanh mà không cần biên dịch, nhưng nếu dự án cần classes/test results thì vẫn phải gọi phase thích hợp.

Trong `jar` packaging, những binding mặc định thường đưa goal `resources` vào `process-resources` và goal `testResources` vào `process-test-resources`. Vì vậy nếu chỉ muốn chỉnh Resources Plugin configuration, **không cần thêm một execution mới cho cùng hai goals**; thêm execution khác ID vào cùng phase có thể làm công đoạn copy chạy hai lần.

## 3. Chuỗi bước chính trong Maven lifecycle

Sơ đồ rút gọn:

~~~text
validate
  |
generate-resources
  |
process-resources         -> resources:resources
  |                         -> main output (target/classes)
compile                   -> compiler:compile
  |
generate-test-resources
  |
process-test-resources    -> resources:testResources
  |                         -> test output (target/test-classes)
test-compile              -> compiler:testCompile
  |
test                      -> surefire:test
  |
package                   -> jar:jar
  |
verify
~~~

Đây chỉ là những phase liên quan, **không phải danh sách đầy đủ** mọi phase của default lifecycle. Maven execution plan phụ thuộc `packaging`, các plugins/executions được khai, parent POM và profiles.

Chạy `mvn clean verify` sẽ thực hiện clean lifecycle và default lifecycle đến `verify`. Với cấu hình thường gặp, file resources được copy trước khi source/test code cần đọc chúng, và `jar:jar` sẽ đóng gói main output sau compilation.

### 3.1. Main resources và source code cùng target/classes

Maven Compiler Plugin thường ghi `.class` chính vào `target/classes`. Maven Resources Plugin cũng đưa **main resources** vào thư mục đó, nên các file cùng nằm trên classpath root:

~~~text
target/classes/
├── dev/example/Main.class
├── banner.txt
└── config/app.properties
~~~

Ví dụ Java:

~~~java
InputStream input = Main.class.getClassLoader()
        .getResourceAsStream("config/app.properties");
~~~

Lệnh không truy cập trực tiếp `src/main/resources`; nó tìm trong classpath được cấu hình khi chạy. Đó là lý do resources vẫn đọc được trong JAR khi classpath phù hợp, dù source tree không hiện diện trên server.

### 3.2. Test resources không tự lọt vào release JAR

Trong `jar` packaging, JAR Plugin thông thường đóng gói `target/classes`, **không đóng gói `target/test-classes`**. Test fixtures nên đặt trong `src/test/resources` để tránh có mặt trong artifact ứng dụng. Tuy vậy Shade, Assembly, WAR hoặc Docker packaging có thể có cấu hình đặc biệt; kiểm tra **artifact thực tế** thay vì suy từ folder name.

## 4. Thư mục mặc định và cấu hình POM

Maven Standard Directory Layout:

~~~text
my-project/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   │       ├── config/app.properties
│   │       └── images/logo.png
│   └── test/
│       ├── java/
│       └── resources/
│           └── fixtures/example.txt
└── target/             (được Maven tạo)
~~~

Nếu không có yêu cầu đặc biệt, Maven đã biết hai thư mục resources tiêu chuẩn; bạn **không cần cấu hình tường minh** để chúng được copy.

Cấu hình main resource root khi cần:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>
    </resources>
</build>
~~~

Cấu hình test resource root:

~~~xml
<build>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
            <filtering>false</filtering>
        </testResource>
    </testResources>
</build>
~~~

Đây là **các fragment đặt dưới `<project>`**, không phải POM đầy đủ. Một khi khai `resources` hoặc `testResources` riêng, phải liệt kê đủ mọi source root muốn giữ; đừng giả định thư mục mặc định vẫn được tự thêm nếu đã thay danh sách bằng custom list.

### 4.1. Những field thường dùng trong resource

| Field | Ý nghĩa |
| --- | --- |
| `<directory>` | Thư mục nguồn tương đối với project basedir hoặc đường dẫn phù hợp |
| `<filtering>` | Có xử lý token trong nội dung hay không; mặc định false |
| `<includes>` | Những pattern file được copy |
| `<excludes>` | Những pattern file không được copy |
| `<targetPath>` | Đường dẫn con trong outputDirectory |
| `<build><filters>` | Các file chứa filter properties được dùng khi filtering |

Ví dụ includes/excludes:

~~~xml
<resource>
    <directory>src/main/resources</directory>
    <filtering>false</filtering>
    <includes>
        <include>**/*.xml</include>
        <include>**/*.properties</include>
        <include>**/*.txt</include>
    </includes>
    <excludes>
        <exclude>**/*-local-only.*</exclude>
        <exclude>**/private/**</exclude>
    </excludes>
</resource>
~~~

Pattern dùng cách biểu diễn kiểu Ant và là **tương đối với resource directory**. Một `include` không phủ định `exclude`: file bị exclude sẽ không được copy dù cũng khớp includes. Hãy kiểm tra path thực tế (ví dụ `secret/private/config.txt`) thay vì chỉ nhìn tên file.

### 4.2. targetPath đổi vị trí đích trong output

~~~xml
<resource>
    <directory>src/main/resources/legal</directory>
    <targetPath>META-INF/legal</targetPath>
    <filtering>false</filtering>
</resource>
~~~

Ví dụ `src/main/resources/legal/NOTICE.txt` sẽ được đưa tới `target/classes/META-INF/legal/NOTICE.txt` theo cấu hình main output mặc định. `targetPath` là **đường dẫn con** trong output, không phải đường dẫn để thay toàn bộ Maven build directory.

### 4.3. Nhiều resource roots

Một dự án cần main resources raw và filtered tách riêng:

~~~xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
    </resource>
    <resource>
        <directory>src/main/resources-filtered</directory>
        <filtering>true</filtering>
        <includes>
            <include>**/*.properties</include>
        </includes>
    </resource>
</resources>
~~~

Hai roots cùng copy vào main output, không tạo hai classpaths khác nhau. Nếu cả hai chứa `config/app.properties`, chúng có thể cùng ghi một đường `target/classes/config/app.properties`: **collision** khiến kết quả phụ thuộc thứ tự và change detection. Giải pháp an toàn là tránh relative paths trùng hoặc phân biệt `targetPath`.

## 5. Test resources với nhiều thư mục và fixture

Test resource roots cũng có thể gồm hai nhóm:

~~~xml
<testResources>
    <testResource>
        <directory>src/test/resources</directory>
        <filtering>false</filtering>
    </testResource>
    <testResource>
        <directory>src/test/resources-filtered</directory>
        <filtering>true</filtering>
        <includes>
            <include>**/*.properties</include>
        </includes>
    </testResource>
</testResources>
~~~

Điều này giúp:

- Đưa fixture `.json`, `.txt`, ảnh mẫu, tài liệu test vào `target/test-classes` **nguyên byte**.
- Lọc riêng một file `test.properties` khi cần tham số build-time.
- Giữ test-only data không bị lẫn vào main JAR.

### 5.1. Resource directory không tồn tại

Trong một số project không có `src/test/resources`, Maven có thể bỏ qua thư mục không tồn tại và vẫn `BUILD SUCCESS`. Đó không nhất thiết là lỗi. Nhưng nếu bạn **mong** một fixture ở đó, hãy đối chiếu spelling, working directory, profile và effective POM thay vì chỉ dựa vào build status.

### 5.2. Skip flags có tác dụng khác nhau

`-DskipTests` thường khiến Surefire **bỏ chạy tests**, nhưng không nhất thiết bỏ compilation/copy test resources. `-Dmaven.test.skip=true` có thể làm test lifecycle bị bỏ rộng hơn; ở Resources Plugin 3.5.0, goal `testResources` có tham số `skip` gắn với user property `maven.test.skip`. Khi thấy thiếu test fixtures, đọc log từng goal và skip property hiệu lực, không suy chỉ từ tên cờ.

## 6. Filtering: thay token trong resources khi build

Filtering là **text substitution** tại build time. Một file được khai `filtering=true` có thể chứa:

~~~properties
app.name=@app.display.name@
app.version=@project.version@
~~~

Trong POM:

~~~xml
<properties>
    <app.display.name>resource-lab</app.display.name>
</properties>
~~~

Với project version `1.0.0` và delimiter `@`, output:

~~~properties
app.name=resource-lab
app.version=1.0.0
~~~

Các nguồn của token có thể là Maven project properties, thông tin model, filter files, system/user properties hoặc giá trị `-D` trên CLI. **Không được nhầm filtering Maven với placeholder resolution của Spring hay một framework ở runtime**.

### 6.1. Default delimiters

Resources Plugin hỗ trợ các kiểu token thường gặp:

~~~text
${property.name}
@property.name@
~~~

Để tránh Maven xử lý `${...}` vốn có thể dành cho runtime framework, có thể tắt default delimiters và chỉ dùng `@...@`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.5.0</version>
    <configuration>
        <useDefaultDelimiters>false</useDefaultDelimiters>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
    </configuration>
</plugin>
~~~

Sau đó `@project.version@` được thay, còn `${spring.profiles.active}` **không phải token của Maven filtering** theo cấu hình này. Framework vẫn phải tự xử lý placeholder runtime khi ứng dụng hoạt động.

### 6.2. filtering=false thì không thay token

Dù plugin có delimiters hợp lệ, nếu resource root khai `<filtering>false</filtering>` thì nội dung `@project.version@` **vẫn nguyên văn**. Điều kiện `filtering=true` phải được bật tại resource root cần xử lý. Vì vậy debug bằng cách đọc **file đã copy** trong `target/classes` hoặc `target/test-classes`, không chỉ nhìn source file.

### 6.3. Filter files và build/filters

Bạn có thể đặt giá trị không nhạy cảm trong `src/main/filters/dev.properties`:

~~~properties
api.label=demo
endpoint.name=localhost
~~~

Và khai trong POM:

~~~xml
<build>
    <filters>
        <filter>src/main/filters/dev.properties</filter>
    </filters>
</build>
~~~

Khi resource được `filtering=true` và `useBuildFilters` cho phép, Maven có thể lấy giá trị từ filter file. Cũng có thể khai `<filters>` trong cấu hình plugin/execution nếu cần bộ giá trị khác nhau cho main và test.

**Không đặt password, token, private key hoặc credential thật vào filter file dùng để đóng gói.** Một token bị Maven thay có thể đi vào `target/classes` rồi JAR phát hành; `gitignore` không ngăn được rò rỉ nếu secret đã thành nội dung artifact.

### 6.4. Đừng coi filtering là parser

Maven filtering thay **chuỗi text**. Nó không hiểu đầy đủ ngữ pháp JSON/YAML/XML/Java properties. Nếu giá trị thay chứa dấu nháy, backslash, newline hoặc ký tự escape, output có thể không còn hợp lệ với file format. Hãy kiểm tra output bằng parser tương ứng khi cấu hình phức tạp. Đối với data động dạng phức tạp, dùng công cụ sinh file có hiểu định dạng thay vì thay token text thuần.

## 7. Encoding, tệp binary và placeholders cần giữ nguyên

### 7.1. Không lọc file binary

Maven chính thức cảnh báo filtering binary (ảnh, PDF, ZIP, JAR, font, keystore, v.v.) có thể làm **hỏng nội dung**. Cách an toàn nhất là:

1. Main/test resource roots chứa binary và text không cần substitution dùng `filtering=false`.
2. Một root khác chỉ chứa text cần lọc dùng `filtering=true`.
3. Dùng `<includes>` cụ thể, ví dụ `**/*.properties`.
4. Bổ sung `nonFilteredFileExtensions` để bảo vệ extension khác.

~~~xml
<configuration>
    <nonFilteredFileExtensions>
        <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
        <nonFilteredFileExtension>zip</nonFilteredFileExtension>
        <nonFilteredFileExtension>woff2</nonFilteredFileExtension>
    </nonFilteredFileExtensions>
</configuration>
~~~

Plugin mặc định có bảo vệ một số extension ảnh như `jpg`, `jpeg`, `gif`, `bmp` và `png`, nhưng **không** có một blacklist mặc định hoàn chỉnh cho mọi binary format. File binary không có extension càng dễ bị lọc sai khi bạn bật `filtering=true` trên cả folder.

### 7.2. Encoding và propertiesEncoding

`encoding` quyết định charset khi lọc text, mặc định thường dựa vào `project.build.sourceEncoding`. `propertiesEncoding` (Resources Plugin từ 3.2.0) chỉ định charset cho filtered `.properties`; nếu không có thì thường dùng `encoding`.

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <version>3.5.0</version>
            <configuration>
                <encoding>UTF-8</encoding>
                <propertiesEncoding>UTF-8</propertiesEncoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đây là **fragment**. Bạn còn phải bảo đảm file nguồn thực sự được lưu UTF-8 và Java/framework sử dụng output đọc với charset phù hợp.

**Bẫy Java:** `Properties.load(InputStream)` dùng cách xử lý ISO-8859-1/Unicode escapes truyền thống, trong khi `Properties.load(Reader)` dùng charset của Reader. Nếu `.properties` chứa tiếng Việt UTF-8 trực tiếp, hãy cân nhắc `load(new InputStreamReader(input, StandardCharsets.UTF_8))` thay vì `load(input)`, hoặc dùng cách đọc riêng của framework. Lab bên dưới dùng giá trị `.properties` ASCII để kết quả độc lập với console Windows/Linux.

### 7.3. escapeString

Tham số `escapeString` cho phép ngăn lọc một token riêng, ví dụ dấu backslash phía trước biểu thức khi delimiter tương ứng được bật. Tuy nhiên cách dễ quản lý hơn nếu toàn bộ `${...}` phải giữ cho runtime là cấu hình **chỉ delimiter `@`** và bật filtering chỉ ở các file cần build-time substitution.

### 7.4. fileNameFiltering

Theo mặc định plugin lọc **nội dung** chứ không tự đổi tên file. `fileNameFiltering` có thể bật để thay token trong tên tệp/thư mục, nhưng sẽ tăng rủi ro collision và sai đường dẫn cross-platform. Chỉ bật khi có nhu cầu có kiểm thử rõ ràng.

## 8. Lab Java 17 đầy đủ: main resources, testResources và filtering

Ta tạo một project Maven duy nhất:

- `src/main/resources/banner.txt`: file copy nguyên văn.
- `src/main/resources-filtered/app.properties`: file Maven lọc `@...@`.
- `src/test/resources/fixtures/sample.txt`: fixture riêng cho test.
- `src/test/resources-filtered/test.properties`: properties chỉ cho test, có filter.
- `Main.java`: Java 17 đọc main resources qua ClassLoader.
- `MainTest.java`: JUnit 5 đọc cả main/test resources và xác nhận kết quả.
- `mvn clean verify`: copy, compile, test, package.
- `jar tf`: kiểm tra nội dung JAR không chứa test fixtures.

### 8.1. Yêu cầu môi trường

JDK 17+, Maven 3.9.x và Internet/mirror để tải Maven plugins + JUnit lần đầu. Resources Plugin 3.5.0 yêu cầu Maven 3.6.3+ và JDK 8+ theo bảng tương thích chính thức, nên bộ Maven 3.9.x/JDK 17 thỏa điều kiện. Không cần Docker hoặc Spring Boot.

Cấu trúc:

~~~text
resources-lab/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/dev/example/resources/Main.java
│   │   ├── resources/banner.txt
│   │   └── resources-filtered/app.properties
│   └── test/
│       ├── java/dev/example/resources/MainTest.java
│       ├── resources/fixtures/sample.txt
│       └── resources-filtered/test.properties
└── target/                  (Maven tự tạo)
~~~

**Lưu ý:** `resources-filtered` là **custom source root** do bài học chọn để phân tách file. Maven không tự quét thư mục đó nếu bạn không khai trong POM.

### 8.2. POM đầy đủ

Tạo `resources-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>resources-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <app.display.name>resource-lab</app.display.name>
        <test.mode>unit</test.mode>
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
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
            </resource>
            <resource>
                <directory>src/main/resources-filtered</directory>
                <filtering>true</filtering>
                <includes>
                    <include>**/*.properties</include>
                </includes>
            </resource>
        </resources>

        <testResources>
            <testResource>
                <directory>src/test/resources</directory>
                <filtering>false</filtering>
            </testResource>
            <testResource>
                <directory>src/test/resources-filtered</directory>
                <filtering>true</filtering>
                <includes>
                    <include>**/*.properties</include>
                </includes>
            </testResource>
        </testResources>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <propertiesEncoding>UTF-8</propertiesEncoding>
                    <useDefaultDelimiters>false</useDefaultDelimiters>
                    <delimiters>
                        <delimiter>@</delimiter>
                    </delimiters>
                    <nonFilteredFileExtensions>
                        <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
                        <nonFilteredFileExtension>zip</nonFilteredFileExtension>
                    </nonFilteredFileExtensions>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Giải thích:

- `build/resources` và `build/testResources` có **mỗi nhóm một raw root + một filtered root**.
- Resource roots filtered chỉ đưa `.properties` qua filtering.
- `useDefaultDelimiters=false` và `@` giúp giữ `${...}` để runtime xử lý.
- `propertiesEncoding` và `encoding` được pin UTF-8.
- `jar` packaging đã bind các goal resources/testResources mặc định; không cần khai thêm custom execution.
- Surefire 3.5.2 có thể chạy JUnit Jupiter 5.11.4; test resource không bị đưa vào main JAR.
- Plugin versions được pin, giảm chênh lệch giữa máy developer và CI.

### 8.3. Tạo các resources nguồn

`src/main/resources/banner.txt`:

~~~text
HELLO_MAIN
~~~

`src/main/resources-filtered/app.properties`:

~~~properties
app.name=@app.display.name@
app.version=@project.version@
runtime.placeholder=${spring.profiles.active}
~~~

Sau `process-resources`, file `target/classes/app.properties` dự kiến:

~~~properties
app.name=resource-lab
app.version=1.0.0
runtime.placeholder=${spring.profiles.active}
~~~

`src/test/resources/fixtures/sample.txt`:

~~~text
fixture-42
~~~

`src/test/resources-filtered/test.properties`:

~~~properties
test.mode=@test.mode@
~~~

Sau `process-test-resources`, `target/test-classes/test.properties`:

~~~properties
test.mode=unit
~~~

Trong ví dụ này, **`@app.display.name@`, `@project.version@` và `@test.mode@` được thay** vì Maven biết các properties đó. `${spring.profiles.active}` được giữ vì delimiter `${...}` bị tắt ở Maven Resources Plugin.

### 8.4. Java Main.java đọc resource qua classpath

Tạo `src/main/java/dev/example/resources/Main.java`:

~~~java
package dev.example.resources;

import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties app = new Properties();
        try (InputStream stream = open("app.properties")) {
            app.load(stream);
        }

        String banner;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(open("banner.txt"),
                        StandardCharsets.UTF_8))) {
            banner = reader.readLine();
        }

        System.out.println(app.getProperty("app.name")
                + "|" + app.getProperty("app.version")
                + "|" + banner);
    }

    private static InputStream open(String path) throws IOException {
        InputStream in = Main.class.getClassLoader()
                .getResourceAsStream(path);
        if (in == null) {
            throw new FileNotFoundException(
                    "Classpath resource missing: " + path);
        }
        return in;
    }
}
~~~

Giải thích:

- `getResourceAsStream("app.properties")` tìm file trong **classpath root**, không ở current working directory.
- `Properties.load(InputStream)` trong lab chỉ đọc giá trị ASCII.
- `banner.txt` được đọc UTF-8.
- `try-with-resources` đóng stream, tránh rò rỉ tài nguyên.
- Không yêu cầu source tree `src/main/resources` còn tồn tại khi chạy class đã đóng gói, miễn runtime classpath chứa resource tương ứng.

### 8.5. JUnit 5 MainTest.java

Tạo `src/test/java/dev/example/resources/MainTest.java`:

~~~java
package dev.example.resources;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.junit.jupiter.api.Test;

class MainTest {

    @Test
    void mainResourcesAreCopiedAndFiltered() throws IOException {
        Properties app = new Properties();
        try (InputStream in = requireResource("app.properties")) {
            app.load(in);
        }

        assertEquals("resource-lab", app.getProperty("app.name"));
        assertEquals("1.0.0", app.getProperty("app.version"));
        assertEquals("${spring.profiles.active}",
                app.getProperty("runtime.placeholder"));

        try (InputStream in = requireResource("banner.txt")) {
            String content = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            assertEquals("HELLO_MAIN", content);
        }
    }

    @Test
    void testResourcesAreCopiedAndFiltered() throws IOException {
        Properties test = new Properties();
        try (InputStream in = requireResource("test.properties")) {
            test.load(in);
        }
        assertEquals("unit", test.getProperty("test.mode"));

        try (InputStream in = requireResource("fixtures/sample.txt")) {
            String fixture = new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).trim();
            assertEquals("fixture-42", fixture);
        }
    }

    private static InputStream requireResource(String path)
            throws IOException {
        InputStream in = MainTest.class.getClassLoader()
                .getResourceAsStream(path);
        if (in == null) {
            throw new IOException("Test classpath resource missing: " + path);
        }
        return in;
    }
}
~~~

Test đầu kiểm tra **main resources** trên test classpath; test sau kiểm tra **test resources**. Cả hai cùng dùng test classloader nhưng không có nghĩa file cùng nằm ở `target/test-classes`. Main resources được copy vào `target/classes`, test resources vào `target/test-classes`.

### 8.6. Build và kiểm chứng stdout

Đứng tại thư mục `resources-lab`:

~~~bash
java -version
mvn -version
mvn -B -ntp clean verify
~~~

Các phase/goal liên quan gồm:

~~~text
clean                  -> xóa output cũ
process-resources      -> resources:resources
compile                -> compiler:compile
process-test-resources -> resources:testResources
test-compile           -> compiler:testCompile
test                   -> surefire:test (2 unit tests)
package                -> jar:jar
verify
~~~

Đây là sơ đồ chức năng, không phải bản sao chính xác toàn bộ Maven log. Maven có thể ghi thêm thông tin phase, plugin, repository và thời gian.

Sau build thành công, tìm giá trị tương đương:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là các **thông tin cần đối chiếu**, không phải cam kết log chỉ có hai dòng.

Chạy main class:

~~~bash
java -cp target/classes dev.example.resources.Main
~~~

**Stdout chính xác của ứng dụng:**

~~~text
resource-lab|1.0.0|HELLO_MAIN
~~~

`resource-lab` đến từ `app.display.name`; `1.0.0` đến từ Maven `project.version`; `HELLO_MAIN` đọc nguyên văn từ `banner.txt`.

### 8.7. Kiểm tra thư mục output

Mong đợi:

~~~text
target/
├── classes/
│   ├── app.properties
│   ├── banner.txt
│   └── dev/example/resources/Main.class
├── test-classes/
│   ├── test.properties
│   ├── fixtures/sample.txt
│   └── dev/example/resources/MainTest.class
├── surefire-reports/
│   └── TEST-dev.example.resources.MainTest.xml
└── resources-lab-1.0.0.jar
~~~

Maven sẽ tạo thêm file/thư mục tùy plugin; đừng coi sơ đồ là danh sách đầy đủ.

Trên Linux/macOS:

~~~bash
cat target/classes/app.properties
cat target/test-classes/test.properties
cat target/classes/banner.txt
cat target/test-classes/fixtures/sample.txt
~~~

Trên Windows PowerShell:

~~~powershell
Get-Content .\target\classes\app.properties
Get-Content .\target\test-classes\test.properties
Get-Content .\target\classes\banner.txt
Get-Content .\target\test-classes\fixtures\sample.txt
~~~

File nguồn filtered và file output sẽ khác nhau ở token; file raw sẽ giữ nội dung nguyên. Kiểm tra **file đã copy** chứ không chỉ nhìn dữ liệu POM.

### 8.8. Kiểm chứng JAR không chứa test resources

Sau `mvn clean verify`:

~~~bash
jar tf target/resources-lab-1.0.0.jar
~~~

Trong JAR ứng dụng thông thường, tìm các entry:

~~~text
app.properties
banner.txt
dev/example/resources/Main.class
~~~

Không kỳ vọng có:

~~~text
test.properties
fixtures/sample.txt
dev/example/resources/MainTest.class
~~~

Vì JAR Plugin mặc định đóng gói main output chứ không phải test output. Nếu bạn dùng Shade/Assembly hoặc file packaging custom thì phải kiểm tra lại theo cấu hình thực tế.

### 8.9. Goal trực tiếp và phase

Để chỉ copy main resources:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-resources-plugin:3.5.0:resources
~~~

Để chỉ copy test resources:

~~~bash
mvn -B -ntp org.apache.maven.plugins:maven-resources-plugin:3.5.0:testResources
~~~

Để chạy theo lifecycle:

~~~bash
mvn -B -ntp process-resources
mvn -B -ntp process-test-resources
~~~

Một goal trực tiếp không tự compile/run test, do đó nó có thể tạo resource output mà chưa có class files. Đây là behavior bình thường, không phải compile failure.

## 9. Resource Plugin parameters quan trọng

| Tên | Mục đích |
| --- | --- |
| `encoding` | Charset dùng khi lọc text |
| `propertiesEncoding` | Charset dành cho filtered `.properties` |
| `delimiters` | Token syntax, ví dụ `@` hoặc `${*}` |
| `useDefaultDelimiters` | Quy định có dùng delimiters mặc định ngoài custom |
| `filters` / `useBuildFilters` | Các tệp properties cung cấp giá trị filtering |
| `nonFilteredFileExtensions` | Bảo vệ thêm extension binary |
| `escapeString` | Giữ token không bị thay khi có prefix escape |
| `fileNameFiltering` | Cho phép lọc tên file/thư mục; mặc định false |
| `addDefaultExcludes` | Loại các file SCM/editor phụ trợ; mặc định true |
| `includeEmptyDirs` | Copy empty folders; mặc định false |
| `skip` | Bỏ qua goal khi có lý do chính đáng |
| `changeDetection` | Chọn chiến lược xác định có overwrite file đích hay không trong Plugin 3.5.0 |

### 9.1. Default excludes

Plugin mặc định bỏ qua một số file thuộc SCM, thư mục ẩn phụ trợ và file tạm, ví dụ `.git`, `.svn`, `.DS_Store` hay backup editor. Có thể thay đổi `addDefaultExcludes`, nhưng thường **không nên copy các file đó vào artifact**. `<excludes>` trên resource root là lớp chọn file riêng của bạn, không thay thế hoàn toàn default excludes.

### 9.2. changeDetection ở Resources Plugin 3.5.0

Plugin 3.5.0 hỗ trợ các giá trị:

- `content`: chỉ overwrite nếu nội dung khác; mặc định từ 3.4.0.
- `timestamp`: xét mốc thời gian sửa, từng là mặc định trước 3.4.0.
- `timestamp+content`: kết hợp thời gian và nội dung.
- `always`: luôn ghi đè output.
- `never`: không ghi đè file đã tồn tại.

Tham số `overwrite` cũ được đánh dấu deprecated ở 3.5.0; tài liệu khuyến nghị `changeDetection`. **Không suy đặc điểm đó áp cho bản 3.3.x** mà không kiểm tra. Nếu xây dựng pipeline tái lập, hãy pin phiên bản và ưu tiên kiểm thử clean build.

### 9.3. fileNameFiltering

Mặc định false. Khi bật, plugin có thể lọc cả tên file/thư mục theo token. Nó hữu ích nếu đang sinh file có tên động, nhưng có thể khiến hai nguồn cùng ra một tên hoặc tạo tên không hợp lệ trên một OS. Chỉ bật khi có test về output filenames.

## 10. Khi nào dùng resources:copy-resources?

Plugin còn goal **`resources:copy-resources`**, dùng khi bạn muốn copy một danh sách resource riêng sang output do bạn chỉ định, chẳng hạn file ví dụ cho bản phân phối:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <id>copy-distribution-files</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>copy-resources</goal>
            </goals>
            <configuration>
                <outputDirectory>${project.build.directory}/distribution</outputDirectory>
                <resources>
                    <resource>
                        <directory>src/distribution/files</directory>
                        <filtering>false</filtering>
                    </resource>
                </resources>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là fragment trong `build/plugins`. Goal `copy-resources` có nguồn và đích tự khai, không lấy `build/resources` hoặc `build/testResources` theo cách hai goal chính làm. Nó không được packaging `jar` tự bind vào `process-resources` hay `process-test-resources`. Muốn làm main resources xuất hiện trên classpath thường nên **cấu hình `build/resources`**, không dùng `copy-resources` tùy tiện.

## 11. Resources được sinh tự động và thứ tự phase

Một code generator có thể sinh resource ở `generate-resources`:

~~~text
generate-resources
  └── target/generated-resources/config/generated.properties
        |
process-resources
  └── resources:resources
        |
target/classes/config/generated.properties
~~~

Điều này chỉ hoạt động nếu thư mục generated được **đăng ký làm resource root** hoặc đưa vào `build/resources` và file được tạo **trước** khi Resources Plugin xử lý. Maven không tự quét tất cả thư mục tên `generated-resources` nếu model không biết chúng.

Nếu generator chạy sau `process-resources`, các file có thể vắng mặt trong JAR. Chạy lại `resources:resources` bằng tay có thể “chữa” trên laptop vì file đã được sinh từ lần trước, nhưng không giúp CI runner sạch. Hãy sửa phase/binding và kiểm chứng bằng `mvn clean verify`.

Không nên để generator ghi tùy tiện vào `src/main/resources`, làm source tree có file phát sinh không theo dõi. Ưu tiên đường `target/` và resource root được quản lý.

## 12. Multi-module, parent POM và profiles

Trong reactor:

~~~text
workspace/
├── pom.xml
├── api/pom.xml
└── service/pom.xml
~~~

Mỗi module có **basedir**, `target/classes`, `target/test-classes` và resource roots riêng, trừ khi cấu hình có chủ đích thay đổi chúng. Parent có thể định nghĩa chung plugin versions/filters, nhưng nếu parent đặt resource root bằng **đường dẫn chỉ hợp lệ ở root**, child có thể kế thừa một đường dẫn không đúng.

Một profile active cũng có thể thay resource roots, filter files hoặc properties. Vì vậy project build trên CI nhưng khác local cần đối chiếu:

~~~bash
mvn -version
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-pom.xml
~~~

Quan trọng:

- `<modules>` là reactor aggregation, `<parent>` là inheritance.
- Resource list sau inheritance/profile mới là cấu hình hiệu lực.
- Không bật `filtering=true` cho cả reactor mà không kiểm soát binary.
- Với module `packaging=pom` không có source files, thiếu resources có thể là bình thường.
- Khi profile tạo build-time values khác, cùng Git commit có thể tạo **artifact bytes khác**, ảnh hưởng tính tái lập.

## 13. An toàn và reproducibility

Những tình huống dễ bỏ sót:

1. **Rò rỉ secret**: lọc password/token vào `target/classes/app.properties`, rồi đóng gói và phát hành JAR. Không đưa secret vào build-time resources.
2. **Binary corruption**: filtering file ZIP/PDF/image/binary làm thay đổi byte.
3. **Runtime placeholder bị thay sớm**: Maven thay `${spring.profiles.active}` mà framework dự kiến xử lý lúc chạy.
4. **Encoding sai**: file nguồn UTF-8 nhưng plugin hoặc ứng dụng đọc bằng charset khác.
5. **Resource collision**: hai roots cùng sinh `config/app.properties`, kết quả phụ thuộc xử lý.
6. **Test data leak**: fixture nằm trong `src/main/resources` và bị đóng gói.
7. **File nguồn không tồn tại**: plugin có thể skip resource directory mà build vẫn xanh.
8. **Build không tái lập**: filter values lấy từ môi trường developer hoặc `-D` không được ghi nhận.
9. **File cũ còn trong target**: chạy goal trực tiếp không clean có thể khiến test nhìn nhầm output từ build trước.
10. **Tùy biến default goal trùng**: thêm execution copy vào cùng phase làm tốn I/O hoặc gây overwrite.
11. **SCM backup files lọt vào artifact**: vô tình tắt `addDefaultExcludes`.
12. **Resource path khác OS**: hard-code dấu phân cách/path Windows trong filtered properties khi ứng dụng chạy Linux.

Cách kiểm soát thường hiệu quả là giữ phần **build-time metadata không nhạy cảm** trong filtered resources, dùng **runtime configuration/secret manager** cho giá trị nhạy cảm, và có test xác minh output artifact cuối.

## 14. Khắc phục sự cố

### 14.1. Main resource không có ở target/classes

**Kiểm tra:** source path tồn tại không, `build/resources` đã được khai đủ chưa, file có bị includes/excludes loại không, profile nào active, goal `resources:resources` đã chạy chưa. Nếu bạn khai custom resource list, đừng mặc định source `src/main/resources` vẫn được thêm tự động.

Chạy:

~~~bash
mvn -B -ntp clean process-resources
mvn -B -ntp org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Doutput=effective-pom.xml
~~~

### 14.2. Test đọc được app.properties nhưng không có ở target/test-classes

Điều này **có thể hoàn toàn đúng**: `app.properties` nằm ở `target/classes`, nhưng cả main/test outputs đều có trên test classpath. `resources:testResources` không tự copy main resources vào test output.

### 14.3. @project.version@ vẫn giữ nguyên

Có thể file nằm trong root `filtering=false`, delimiter `@` bị tắt, plugin chưa chạy, filter token không được định nghĩa, đang nhìn source file thay vì output hoặc hai roots ghi trùng destination. Hãy xem `target/classes/app.properties` sau clean build và xác nhận `filtering=true` ở root chứa file đó.

### 14.4. Placeholder runtime bị Maven thay

Nếu `${...}` là delimiter đang bật và resource lọc text, Maven có thể thay giá trị sớm. Dùng custom delimiter `@`, `useDefaultDelimiters=false` hoặc escape token theo mục đích. Tránh cách sửa “xóa mọi placeholder” mà chưa xác định người xử lý cuối.

### 14.5. Ảnh/PDF/ZIP bị lỗi

Thông thường binary bị filter như text. Chuyển vào root `filtering=false` và thêm extension phù hợp ở `nonFilteredFileExtensions`. Dùng checksum/byte compare để chứng minh nguyên vẹn; không hy vọng đổi encoding có thể khôi phục bytes đã hỏng.

### 14.6. Ký tự tiếng Việt bị sai

Kiểm tra source charset, `project.build.sourceEncoding`, `encoding`, `propertiesEncoding` và Java/framework đọc output. Nếu dùng `Properties.load(InputStream)` với UTF-8 Unicode, xem cách đọc qua `Reader UTF-8`.

### 14.7. Goal testResources không chạy khi dùng skip test

Xem `maven.test.skip`, `skipTests`, các plugin executions và phase thực thi. Không mặc định `skipTests` bỏ luôn `process-test-resources`; không mặc định `maven.test.skip` chỉ có tác dụng lên Surefire.

### 14.8. Main test fail vì không thấy fixture

File test phải nằm trong `src/test/resources` hoặc test resource root phù hợp, sau đó `process-test-resources` cần chạy. Gọi `resources:resources` chỉ xử lý main resource, không phải test resource. Test source có thể compile nhưng vẫn fail runtime khi fixture thiếu.

### 14.9. JAR chứa nhầm test fixtures hoặc thiếu main properties

Chạy `jar tf` và kiểm tra packaging plugin. `src/test/resources` trong config chuẩn không được đưa vào main JAR. Nếu có, có thể là custom build config hoặc test fixture đã đặt sai trong main root. Nếu thiếu main properties, xem file có ở `target/classes` trước package không.

### 14.10. Chỉ thấy BUILD SUCCESS nhưng file output sai

Resource copy có thể hoàn thành mà không có file nào được chọn. `BUILD SUCCESS` chứng minh goal đã kết thúc không lỗi theo điều kiện hiện tại, không chứng minh file bạn mong đợi đã được tạo. Luôn kiểm tra đường output, nội dung filtered và artifact.

### 14.11. Output stale hoặc thay đổi khi nâng plugin

Bản Resources Plugin 3.5.0 có `changeDetection` khác một số bản cũ. Khi nghi lỗi cache/copy, pin plugin version và dùng `mvn clean verify` để loại tác động của output tồn dư. Không sửa local repository cache hoặc xóa source files như bước đầu.

### 14.12. Lọc một tệp XML/JSON khiến file không còn hợp lệ

Filtering chỉ thay text. Nếu token có dấu nháy, xuống dòng hoặc backslash không escape đúng, parser runtime có thể báo lỗi. Dùng validator cho file sau filtering hoặc code generation hiểu định dạng, tránh coi Maven filtering là một serializer.

## 15. Quy trình kiểm tra có thể lặp lại

Khi nhận lỗi thiếu/sai resource:

1. Xác nhận `mvn -version`, JDK, project/module và working directory.
2. Xem source roots thật (`src/main/resources`, `src/test/resources`, custom roots).
3. Kiểm tra `build/resources` và `build/testResources` trong effective POM.
4. Xác nhận `filtering` và delimiter thật của file nghi vấn.
5. Kiểm tra profile active và filter file/CLI property.
6. Dùng `mvn clean process-resources` để thấy main output mới.
7. Dùng `mvn process-test-resources` để thấy test output mới.
8. Mở file trong `target/classes` và `target/test-classes`, đối chiếu byte/text.
9. Chạy `mvn clean verify` để kiểm tra compiler, test runner và package.
10. Dùng `jar tf` xác nhận artifact cuối; với binary, so hash nếu cần.
11. Nếu local khác CI, so Maven Wrapper, plugin versions, profiles, file encodings và build properties; không gán lỗi cho “Maven cache” khi chưa có bằng chứng.
12. Sau khi sửa, ghi lại cấu hình và output cần thiết vào test/CI để phát hiện tái diễn.

## 16. Bài tập và đáp án

**Bài A — Phase.** Goal `resources:resources` và `resources:testResources` mặc định gắn vào đâu?

**Đáp án:** `process-resources` và `process-test-resources` trong default lifecycle, với packaging/binding thông thường.

**Bài B — Thư mục output.** `src/main/resources/banner.txt` và `src/test/resources/fixtures/sample.txt` đi tới đâu?

**Đáp án:** `target/classes/banner.txt` và `target/test-classes/fixtures/sample.txt`.

**Bài C — Test classpath.** Unit test đọc được `app.properties` nhưng không thấy nó trong `target/test-classes`. Có lỗi không?

**Đáp án:** chưa. Main resources ở `target/classes`, nhưng test classpath có thể chứa cả main output.

**Bài D — Token.** `app.version=@project.version@` với project version 1.0.0, filtering true và delimiter `@` cho kết quả gì?

**Đáp án:** `app.version=1.0.0`.

**Bài E — Filtering false.** Có cấu hình delimiter `@` nhưng file nằm trong resource root filtering false. Token có bị thay không?

**Đáp án:** không.

**Bài F — Runtime placeholder.** Vì sao `${spring.profiles.active}` giữ nguyên trong lab?

**Đáp án:** plugin chỉ dùng delimiter `@`, `useDefaultDelimiters=false`.

**Bài G — Binary.** Tại sao không filter `.pdf`/`zip`?

**Đáp án:** filtering đọc/ghi text có thể thay hoặc hỏng bytes nhị phân. Dùng root không lọc và/hoặc `nonFilteredFileExtensions`.

**Bài H — Test fixture.** JSON fixture chỉ dùng trong test nên đặt ở đâu?

**Đáp án:** `src/test/resources` hoặc test root tương ứng; tránh main artifact chứa fixtures.

**Bài I — copy-resources.** `resources:copy-resources` có cần để copy main resources chuẩn không?

**Đáp án:** thường không; `resources:resources` với `build/resources` đã hỗ trợ.

**Bài J — Goal trực tiếp.** `mvn resources:testResources` có tự chạy JUnit tests không?

**Đáp án:** không, goal này copy test resources. Dùng `mvn test` để đi tới test phase và chạy Surefire theo cấu hình.

**Bài K — XML/encoding.** Vì sao source UTF-8 đã filter đúng nhưng Java `Properties.load(InputStream)` vẫn có thể đọc sai ký tự?

**Đáp án:** Java API này có semantics ISO-8859-1 cho properties truyền thống; dùng UTF-8 Reader hoặc framework parsing tương ứng.

**Bài L — Reproducibility.** Cùng Git commit nhưng build với filter file khác nhau có thể tạo JAR khác byte không?

**Đáp án:** có, vì nội dung đã được thay ở build time. Ghi nhận build properties/profiles và tránh nhét secrets vào JAR.

**Bài M — Generated resources.** Generator sinh file ở `target/generated-resources` trước `process-resources` nhưng file không vào JAR. Thiếu gì?

**Đáp án:** cần đăng ký/thêm resource root cho thư mục output của generator hoặc copy nó bằng goal phù hợp, và kiểm tra thứ tự phase.

## 17. Checklist trước khi sử dụng trong dự án thật

- [ ] Phân biệt main vs test resource roots và output directories.
- [ ] Hiểu `resources:resources`/`resources:testResources` là goals, `process-...` là phases.
- [ ] Không thêm execution trùng default lifecycle binding khi chỉ muốn đổi config.
- [ ] Nếu khai custom resource roots, đã liệt kê đầy đủ những thư mục cần copy.
- [ ] `filtering=true` chỉ bật cho những text files thực sự cần.
- [ ] Dùng delimiter rõ ràng; giữ runtime placeholders nguyên nếu cần.
- [ ] Tách binary và filtered text, có includes/nonFilteredFileExtensions thích hợp.
- [ ] `project.build.sourceEncoding`, `encoding` và `propertiesEncoding` đã được kiểm tra.
- [ ] Không chuyển secret thật thành nội dung JAR thông qua filtering.
- [ ] Test fixtures được đặt trong test resources, không ở main resources.
- [ ] Không có hai resource roots ghi trùng relative path ngoài ý muốn.
- [ ] Đã kiểm tra `target/classes` và `target/test-classes` sau build.
- [ ] Đã chạy Java main hoặc test để đọc resources bằng classpath.
- [ ] Đã dùng `jar tf` để kiểm tra nội dung sản phẩm phát hành.
- [ ] Đã pin Maven Resources Plugin version và kiểm tra change detection.
- [ ] Đã so Maven/JDK/profiles/filter files giữa local và CI.
- [ ] Generated resource roots được đăng ký đúng trước phase copy.
- [ ] Build sạch có thể tái lập và không có binary corruption.

## 18. Tài liệu chính thức

1. [Apache Maven Resources Plugin — Introduction](https://maven.apache.org/plugins/maven-resources-plugin/) — vai trò, ba goals và main/test resources.
2. [resources:resources](https://maven.apache.org/plugins/maven-resources-plugin/resources-mojo.html) — `process-resources`, `project.build.resources` và options.
3. [resources:testResources](https://maven.apache.org/plugins/maven-resources-plugin/testResources-mojo.html) — `process-test-resources`, `project.build.testResources` và options.
4. [Resources Plugin — Usage](https://maven.apache.org/plugins/maven-resources-plugin/usage.html) — cách gọi goal.
5. [Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html) — tokens, filter files và binary caution.
6. [Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html) — cấu hình filtering.
7. [Resources Plugin — Binary Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html) — extension được bỏ qua filtering.
8. [Resources Plugin — Includes/Excludes](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html) — patterns.
9. [Resources Plugin — Copy Resources](https://maven.apache.org/plugins/maven-resources-plugin/examples/copy-resources.html) — goal `copy-resources`.
10. [Resources Plugin — FAQ](https://maven.apache.org/plugins/maven-resources-plugin/faq.html) — main/test separation.
11. [Resources Plugin 3.5.0 — testResources parameters](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.5.0/testResources-mojo.html) — `skip`, `propertiesEncoding`, `changeDetection`.
12. [Apache Maven POM Reference](https://maven.apache.org/pom.html) — `resources`, `testResources`, `targetPath`.
13. [Maven Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html) — source/resource directories.
14. [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — lifecycle phases và default goal bindings.
