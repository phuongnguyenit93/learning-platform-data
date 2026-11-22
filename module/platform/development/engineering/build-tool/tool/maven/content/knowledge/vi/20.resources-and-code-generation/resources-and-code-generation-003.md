# Resource filtering và thay thế giá trị bằng thuộc tính trong Apache Maven

## 1. Khái niệm và mục tiêu

Trong dự án Java, Maven xử lý không chỉ file `.java` mà còn các **resources (tài nguyên)** như `.properties`, `.xml`, `.yml`, `.txt`, ảnh hoặc dữ liệu tĩnh. Với packaging `jar`, resource chính thường nằm ở `src/main/resources`, được copy vào `target/classes` và sau đó có thể nằm trong JAR. Resource kiểm thử ở `src/test/resources` thường được copy vào `target/test-classes`.

**Resource filtering** là việc Maven **thay placeholder trong nội dung file text bằng giá trị thuộc tính có sẵn khi build**. Ví dụ file template:

```properties
app.name=@project.artifactId@
app.version=@project.version@
app.mode=@app.mode@
```

Nếu POM có artifactId `resource-filtering-demo`, version `1.0.0` và property `app.mode=local`, file output đã lọc sẽ thành:

```properties
app.name=resource-filtering-demo
app.version=1.0.0
app.mode=local
```

Phải phân biệt **file nguồn** (chứa token), **file output** (giá trị đã thay), **bản JAR cuối** (có thể chứa file output), và **nguồn property** (POM, profile, CLI, filter file hoặc Java/system properties).

**Maven mặc định thường chỉ copy tài nguyên; filtering không tự bật cho mọi resource.** Để thay giá trị, cần khai báo `<filtering>true</filtering>` cho resource set tương ứng.

Bài học hướng dẫn cách bật filtering, thay giá trị từ nhiều nguồn, chọn delimiter, bảo vệ binary, xử lý encoding, kiểm tra output và cách áp dụng an toàn trong build Java 17.

## 2. Filtering dùng để làm gì — và không nên dùng để làm gì?

Ứng dụng có thể cần file build-info thể hiện version thực tế từ POM, ví dụ:
- `project.version`: version của artifact đang build;
- `project.artifactId`: tên artifact;
- `app.mode`: mode không nhạy cảm của một bản build;
- `team.label`: nhãn tổ chức lấy từ file filter.

Những trường hợp này phù hợp vì giá trị được **chốt vào output tại thời điểm build**.

Resource filtering **không phải**:
1. Bộ sinh mã Java. Goal sinh source (OpenAPI, protobuf, ANTLR...) cần phase và source roots riêng; resource filtering chỉ thay text.
2. Hệ thống cấu hình runtime. Đổi `-Dapp.mode` của JVM sau khi JAR đã build **không sửa file build-info trong JAR**.
3. Công cụ phân giải dependencies/BOM/plugin versions. Nó không đổi artifact dependency chỉ vì template chứa tên thư viện.
4. Parser am hiểu cấu trúc YAML, JSON hay XML. Nó thay token text; bạn phải bảo đảm output vẫn đúng cú pháp của định dạng.
5. Cơ chế bảo mật secret. Mật khẩu/token lọc vào resource rồi đóng gói sẽ có thể bị đọc lại.

Nếu một giá trị phải đổi sau khi deploy mà không rebuild, thường nên chọn **runtime configuration**, environment variables hoặc secret manager. Nếu giá trị biểu thị identity của một build cụ thể, filtering là một cách hợp lý.

## 3. Nơi Maven xử lý resource trong lifecycle

Với `jar` packaging thông thường, Maven có những phase/goal quan trọng:

```text
validate
   |
process-resources        -> resources:resources     -> target/classes
   |
compile                  -> compiler:compile
   |
process-test-resources   -> resources:testResources -> target/test-classes
   |
test-compile             -> compiler:testCompile
   |
test                     -> surefire:test
   |
package                  -> jar:jar
```

Sơ đồ đã rút gọn, không phải toàn bộ default lifecycle. Goal `resources:resources` gắn với `process-resources`, còn `resources:testResources` với `process-test-resources`. Các output từ `target/classes` sẽ được đóng vào JAR chính khi packaging phù hợp.

| Lệnh | Công việc liên quan resource |
| --- | --- |
| `mvn process-resources` | Đi tới phase copy/filter main resources |
| `mvn process-test-resources` | Đi qua phase copy/filter main và test resources |
| `mvn compile` | Đã xử lý main resources rồi mới biên dịch Java chính |
| `mvn test` | Xử lý resources, biên dịch và chạy unit tests |
| `mvn clean package` | Dọn output cũ rồi tạo resources, classes và JAR |
| `mvn resources:resources` | Gọi trực tiếp goal copy/filter main resources, không yêu cầu compile |
| `mvn resources:testResources` | Gọi trực tiếp goal xử lý test resources |

**`mvn clean` không tự làm mới resource.** Nó thường chỉ xóa `target` theo clean lifecycle; cần gọi phase xử lý resources hoặc phase đứng sau để tạo file mới.

## 4. Hai cách viết placeholder

Maven Resources Plugin hỗ trợ hai delimiter phổ biến theo mặc định:

```text
${property.name}
@property.name@
```

Ví dụ:

| Placeholder | Giá trị đến từ đâu |
| --- | --- |
| `@project.artifactId@` | Maven artifactId |
| `${project.version}` hoặc `@project.version@` | Version Maven project |
| `${project.name}` | Tên project từ POM |
| `@app.mode@` | Custom property trong POM, profile hoặc CLI |
| `@team.label@` | Custom property trong filter file |
| `${java.version}` | Java system property của Maven process |
| `${env.HOME}` | Biến môi trường nếu có trong môi trường build |

`${...}` cũng được dùng để nội suy trong `pom.xml`, nhưng **resource interpolation** xảy ra khi Resources Plugin xử lý text. `@...@` chỉ là một delimiter, **không phải Java annotation**.

Nhiều framework Java dùng `${...}` để thay giá trị khi **ứng dụng chạy**. Vì vậy cách dùng `@project.version@` cho build metadata thường giảm nguy cơ Maven can thiệp vào những token runtime, đặc biệt với `application.properties` hoặc `application.yml`.

## 5. Bật filtering đúng phạm vi

Trong POM, khai báo:

```xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
</build>
```

Đây là **đoạn XML để chèn dưới `<project>`**, chưa phải POM hoàn chỉnh. Nó áp dụng filtering cho tài nguyên trong directory đã chọn.

Tuy nhiên, file binary có thể bị hỏng nếu được filtering như text. Cách an toàn hơn là tách hai thư mục:

```xml
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
```

Cấu hình này:
- Copy nguyên trạng file từ `src/main/resources`;
- Chỉ filtering các file `.properties` trong `src/main/resources-filtered`;
- Đưa output của hai resource sets về `target/classes` khi dùng output directory mặc định;
- Không tự filter những file nằm ngoài các resource sets đã khai báo.

`src/main/resources-filtered` là đường dẫn **do tác giả chọn**, không phải một folder được Maven tự quét. Cần tạo thư mục thật và khai báo rõ như trên.

## 6. Bài thực hành hoàn chỉnh Java 17

Chúng ta sẽ dùng một POM Java 17, một file filter cung cấp giá trị, một resource template được lọc, một resource không lọc và một Java class đọc kết quả trên classpath.

### 6.1. Cây thư mục

```text
resource-filtering-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/resources/App.java
        ├── resources/readme.txt
        ├── resources-filtered/build-info.properties
        └── filters/build.properties
```

Các đường dẫn dưới `src/main/java` phải khớp package Java. Thư mục `src/main/filters` chỉ chứa **giá trị cho Maven**, không tự được copy lên classpath.

### 6.2. POM đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>resource-filtering-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <name>Resource Filtering Demo</name>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <app.mode>local</app.mode>
    </properties>

    <build>
        <filters>
            <filter>src/main/filters/build.properties</filter>
        </filters>

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

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <encoding>UTF-8</encoding>
                    <propertiesEncoding>UTF-8</propertiesEncoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>ci</id>
            <properties>
                <app.mode>ci-profile</app.mode>
            </properties>
        </profile>
    </profiles>
</project>
```

Đây là **POM độc lập hoàn chỉnh**. Yêu cầu JDK 17+ và một bản Maven tương thích. Maven có thể phải tải các plugin từ repository trong lần build đầu.

Giải thích:
- `app.mode=local` là property tùy biến mặc định;
- `<filters>` cung cấp giá trị `team.label` qua file ngoài POM;
- resource set đầu **không filter**, resource set thứ hai **có filter**;
- `propertiesEncoding=UTF-8` điều khiển encoding cho file `.properties` được Resources Plugin lọc;
- `maven.compiler.release=17` dùng cho Java compile;
- profile `ci` thay giá trị `app.mode` trong các lượt có `-Pci`;
- Resources Plugin không cần execution riêng vì goal đã có binding mặc định ở `process-resources` của `jar` packaging.

### 6.3. File src/main/filters/build.properties

```properties
team.label=Platform Team
```

Đây là **filter file**: một nguồn `key=value` phục vụ build-time substitution. Nó **không tự được copy** vào `target/classes` chỉ vì được liệt kê trong `<filters>`.

### 6.4. File src/main/resources-filtered/build-info.properties

```properties
app.name=@project.artifactId@
app.version=@project.version@
app.mode=@app.mode@
team.label=@team.label@
```

File này là template. Khi Maven copy resource set có `filtering=true`, các token được thay bằng giá trị từ Maven project properties, `<properties>`/profile hoặc filter file.

### 6.5. File src/main/resources/readme.txt

```text
This file is copied without filtering: @app.mode@
```

Resource set này có `filtering=false`, vì vậy token `@app.mode@` **vẫn nằm nguyên trong file output**. Điều đó không phải lỗi; nó minh họa khác biệt giữa copy nguyên trạng và filtering.

### 6.6. File src/main/java/com/example/resources/App.java

```java
package com.example.resources;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws IOException {
        InputStream input = App.class.getResourceAsStream("/build-info.properties");
        if (input == null) {
            throw new IOException("build-info.properties not found");
        }

        Properties values = new Properties();
        try (Reader reader = new InputStreamReader(input, StandardCharsets.UTF_8)) {
            values.load(reader);
        }

        System.out.println("Name: " + values.getProperty("app.name"));
        System.out.println("Version: " + values.getProperty("app.version"));
        System.out.println("Mode: " + values.getProperty("app.mode"));
        System.out.println("Team: " + values.getProperty("team.label"));
    }
}
```

Đây là Java 17 hoàn chỉnh. `App.class.getResourceAsStream` tìm resource đã copy trên **classpath**, không đọc template trong source tree. `Properties.load(Reader)` phù hợp output UTF-8 được tạo bởi plugin.

### 6.7. Build và xem file kết quả

Tại thư mục chứa `pom.xml`:

```bash
mvn -version
mvn -B -ntp clean package
```

Sau build thành công, các đường dẫn thông thường là:

```text
target/classes/build-info.properties
target/classes/readme.txt
target/classes/com/example/resources/App.class
target/resource-filtering-demo-1.0.0.jar
```

Nội dung chính xác của `target/classes/build-info.properties`:

```properties
app.name=resource-filtering-demo
app.version=1.0.0
app.mode=local
team.label=Platform Team
```

Nội dung `target/classes/readme.txt`:

```text
This file is copied without filtering: @app.mode@
```

Chạy chương trình:

```bash
java -cp target/classes com.example.resources.App
```

**Stdout chính xác của lệnh Java**, không tính log Maven:

```text
Name: resource-filtering-demo
Version: 1.0.0
Mode: local
Team: Platform Team
```

Để kiểm tra nội dung artifact:

```bash
jar tf target/resource-filtering-demo-1.0.0.jar
```

JAR cần chứa `build-info.properties`, `readme.txt` và `com/example/resources/App.class`. Nó có thể chứa thêm manifest/metadata. POM mẫu chưa khai báo `Main-Class` nên không giả định `java -jar ...` chạy được; có thể dùng JAR làm classpath:

```bash
java -cp target/resource-filtering-demo-1.0.0.jar com.example.resources.App
```

Khi file đã filtering nằm trong JAR, chương trình đọc từ classpath cho kết quả tương tự như chạy bằng `target/classes`.

## 7. Ghi đè thuộc tính bằng -D khi build

Thay giá trị `app.mode` cho **một lượt Maven**:

```bash
mvn -B -ntp "-Dapp.mode=staging" clean package
java -cp target/classes com.example.resources.App
```

Lúc đó file đã lọc chứa `app.mode=staging` và dòng Java là:

```text
Mode: staging
```

Những dòng `Name`, `Version`, `Team` không đổi. File template nguồn vẫn chứa `@app.mode@`. Đây là khác biệt quan trọng: filtering **không chỉnh sửa source file**.

Nếu bạn chỉ truyền `-Dapp.mode=staging` vào **lệnh java chạy ứng dụng** sau khi build, resource đã đóng gói **không tự thay đổi**. Cờ `-D` của JVM và user property `-D` của Maven có thể giống cách viết nhưng tác động ở hai thời điểm khác nhau.

### Bật profile ci

POM mẫu khai báo:

```xml
<profile>
    <id>ci</id>
    <properties>
        <app.mode>ci-profile</app.mode>
    </properties>
</profile>
```

Đây là đoạn profile đã nằm trong POM hoàn chỉnh. Chạy:

```bash
mvn -B -ntp -Pci clean package
java -cp target/classes com.example.resources.App
```

Dòng output lúc này:

```text
Mode: ci-profile
```

Muốn xác minh profile đang hoạt động, dùng `mvn -Pci help:active-profiles`. Cần truyền lại `-Pci` vì lệnh kiểm tra là một phiên Maven mới. Không đoán giá trị cuối nếu bạn đồng thời có nhiều profile và `-D` ghi đè cùng property; hãy kiểm tra effective model và resource output.

**Cảnh báo tái lập:** cùng source commit và artifact version nhưng filtering bằng các giá trị `app.mode` khác nhau có thể tạo các JAR **khác bytes**. Với release yêu cầu immutability/reproducible build, nên quyết định rõ thuộc tính nào được bake trong artifact và thuộc tính nào thuộc runtime.

## 8. Filter files và lựa chọn nguồn giá trị

Tệp filter `src/main/filters/build.properties` có thể chứa:

```properties
team.label=Platform Team
release.channel=training
```

Trong phần `<build>` của POM:

```xml
<filters>
    <filter>src/main/filters/build.properties</filter>
</filters>
```

Và trong resource đã bật filtering:

```properties
team.label=@team.label@
release.channel=@release.channel@
```

Maven đọc filter file để lấy các key phục vụ thay token. **Filter file là nguồn dữ liệu**, còn **filtered resource là tệp đích chứa template**. Chỉ vì một file có trong `<filters>` không có nghĩa file đó tự nằm trong JAR.

### Chọn filter file theo profile

Giả sử dự án có `dev.properties` và `ci.properties`. Có thể đặt đường dẫn filter file trong property và override bằng profile:

```xml
<properties>
    <active.filter>src/main/filters/dev.properties</active.filter>
</properties>

<build>
    <filters>
        <filter>${active.filter}</filter>
    </filters>
</build>

<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <active.filter>src/main/filters/ci.properties</active.filter>
        </properties>
    </profile>
</profiles>
```

Đây **chỉ là mẫu cấu trúc**, không phải POM độc lập và không phải khối cần chèn thêm nguyên xi vào POM mục 6. Khi áp dụng, chỉnh các khối `<properties>`, `<build><filters>` và `<profiles>` hiện có, đồng thời **tạo hai file filter thật**. Đừng thêm hai khối `<build>` song song trong một POM.

### Không lưu secrets trong file filter để đóng JAR

Nếu filter chứa mật khẩu hoặc API token và template tham chiếu token ấy, artifact/JAR có thể **lộ giá trị**. Không sử dụng filtering để đóng gói secrets. Hãy dùng runtime injection, secret manager hoặc cơ chế cấu hình phù hợp, đồng thời tránh in các giá trị nhạy cảm vào Maven debug logs.

## 9. Chỉ filter file text; bảo vệ binary bằng includes/excludes

Maven Resources Plugin thực hiện biến đổi text. Ảnh, PDF, ZIP, font hoặc binary khác có thể hỏng nếu bị xử lý như text.

Một resource set giới hạn loại file:

```xml
<resource>
    <directory>src/main/resources-filtered</directory>
    <filtering>true</filtering>
    <includes>
        <include>**/*.properties</include>
        <include>**/*.xml</include>
    </includes>
</resource>
```

Đây là **đoạn thay cho một `<resource>`**, không phải POM hoàn chỉnh. Các patterns kiểu Ant như `**/*.properties` và `**/*.xml` chọn file ở nhiều cấp thư mục. Có thể thêm `<excludes>` để loại những file riêng cần giữ nguyên.

Resources Plugin mặc định bảo vệ một số extension thường gặp như `jpg`, `jpeg`, `gif`, `bmp`, `png`. Có thể bổ sung `pdf` và `zip`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <nonFilteredFileExtensions>
            <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
            <nonFilteredFileExtension>zip</nonFilteredFileExtension>
        </nonFilteredFileExtensions>
    </configuration>
</plugin>
```

Đây là **mẫu cần ghép vào khai báo plugin Resources hiện có**, không nên thêm plugin trùng trong `<plugins>`. Tách thư mục filtered/unfiltered vẫn là lựa chọn dễ bảo trì hơn khi project có nhiều định dạng file.

**Tránh hai nguồn ghi cùng output:** nếu cả `src/main/resources/config.properties` và `src/main/resources-filtered/config.properties` đều được copy tới `target/classes/config.properties`, chúng có thể cạnh tranh; kết quả phụ thuộc thứ tự copy/overwrite. Đổi tên, tách path bằng `targetPath` hoặc dùng include/exclude để mỗi đích có một nguồn.

## 10. Chọn delimiter để không đụng placeholder runtime

Khi framework cần giữ nguyên `${...}` đến runtime, có thể yêu cầu Maven **chỉ thay `@...@`**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <delimiters>
            <delimiter>@</delimiter>
        </delimiters>
        <useDefaultDelimiters>false</useDefaultDelimiters>
    </configuration>
</plugin>
```

Trong cấu hình này, `<delimiter>@</delimiter>` nhận token `@key@`, còn `useDefaultDelimiters=false` tránh Maven tự thêm lại delimiter `${...}`.

Ví dụ resource nguồn:

```properties
build.version=@project.version@
runtime.region=${RUNTIME_REGION:local}
```

Sau Maven filtering:

```properties
build.version=1.0.0
runtime.region=${RUNTIME_REGION:local}
```

Token `${RUNTIME_REGION:local}` được giữ nguyên. **Framework** quyết định có hỗ trợ cú pháp `:local` hay không; Resources Plugin không phải parser của framework. Nếu file thuộc Spring hoặc hệ thống cấu hình khác, nên kiểm tra tài liệu framework và file output để tránh thay sai thời điểm.

## 11. Escape những token cần giữ nguyên

Resources Plugin hỗ trợ `escapeString` khi một file đã bật filtering nhưng có token riêng cần giữ nguyên. Cấu hình ví dụ:

```xml
<configuration>
    <escapeString>\</escapeString>
</configuration>
```

Nếu `app.mode=local` và text nguồn có:

```text
Literal token: \${app.mode}
```

thì Maven có thể sinh:

```text
Literal token: ${app.mode}
```

Dấu escape bị loại, token không được nội suy. Nhưng `\` cũng có ý nghĩa riêng trong `.properties` và nhiều DSL khác; nên kiểm tra file output và cách runtime parser đọc. Nếu bạn đã cấu hình Maven chỉ filter `@...@`, token `${app.mode}` không cần escape vì vốn không match delimiter.

## 12. Encoding và Java .properties

Resource filtering đọc/ghi **text**, nên phải thống nhất charset nguồn và output. Resources Plugin 3.3.1 hỗ trợ:
- `encoding`: dùng để đọc/ghi filtered text, thường nhận mặc định từ `${project.build.sourceEncoding}`;
- `propertiesEncoding`: charset riêng cho filtered `.properties`, hỗ trợ từ plugin 3.2.0 và thường mặc định theo `encoding`.

POM thực hành đã cấu hình:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

và:

```xml
<configuration>
    <encoding>UTF-8</encoding>
    <propertiesEncoding>UTF-8</propertiesEncoding>
</configuration>
```

Hai đoạn này để giải thích **cấu hình đã tồn tại**, không phải bảo người học thêm khối POM trùng.

**Quan trọng với Java:** `Properties.load(InputStream)` theo truyền thống đọc theo ISO-8859-1/Unicode escapes, không tự đọc UTF-8 chỉ vì Maven output là UTF-8. Vì vậy `App.java` ví dụ dùng `Properties.load(Reader)` với `InputStreamReader(StandardCharsets.UTF_8)`. Đó là lựa chọn phù hợp cho file `.properties` UTF-8 do project kiểm soát.

`ResourceBundle` ở Java 9+ có cơ chế ưu tiên UTF-8 cho properties bundles, khác với `Properties.load(InputStream)`. Khi gặp tiếng Việt hiển thị sai, cần kiểm tra:
1. encoding của file nguồn;
2. `encoding/propertiesEncoding` của Resources Plugin;
3. encoding file output;
4. API Java/framework đọc file;
5. encoding terminal khi in ra console.

Đừng đổ lỗi cho Maven nếu file output thật là UTF-8 hợp lệ nhưng ứng dụng đang đọc bằng API/charset khác.

## 13. Filtering riêng cho test resources

`src/test/resources` phục vụ bài test, output thông thường là `target/test-classes`, không phải `target/classes`. Nếu muốn filter riêng:

```xml
<build>
    <testResources>
        <testResource>
            <directory>src/test/resources</directory>
            <filtering>true</filtering>
        </testResource>
    </testResources>
</build>
```

Đây là đoạn XML minh họa: **bổ sung `<testResources>` vào `<build>` hiện có**, không chèn một `<build>` thứ hai vào POM mẫu. Goal `resources:testResources` thường chạy tại `process-test-resources`.

Main JAR thông thường **không tự chứa test resources**. Test resource filtering cũng không có nghĩa JUnit tests đã chạy: cần `mvn test` hoặc phase phía sau và kiểm tra Surefire reports.

## 14. Dùng Maven Help Plugin để kiểm tra cấu hình

Nếu một token không được thay, trước hết kiểm tra **mô hình có hiệu lực**:

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Trong effective POM, tìm:
- `<app.mode>` và profile liên quan;
- `<build><filters>`;
- `<resources>`, directories và `filtering`;
- version và configuration Maven Resources Plugin.

Khi bật profile, phải truyền **cùng -P** cho lệnh kiểm tra:

```bash
mvn -Pci help:effective-pom -Doutput=effective-ci.xml
```

Để xem property hiện tại:

```bash
mvn -q help:evaluate -Dexpression=app.mode -DforceStdout
mvn -q -Pci help:evaluate -Dexpression=app.mode -DforceStdout
mvn -q "-Dapp.mode=staging" help:evaluate -Dexpression=app.mode -DforceStdout
```

Với POM mẫu, các giá trị cần thấy lần lượt là `local`, `ci-profile` và `staging`.

Tuy nhiên, **effective POM và help:evaluate không chứng minh output resource đã được ghi**. Để kiểm chứng hành vi, chạy:

```bash
mvn -B -ntp clean process-resources
```

Rồi mở `target/classes/build-info.properties` và `target/classes/readme.txt`, so từng dòng với template. Lệnh này chưa biên dịch Java từ một build sạch, nên nếu muốn chạy `App`, cần tiếp tục đến `compile` hoặc `package`.

Nếu còn lỗi, có thể xem thêm log:

```bash
mvn -X -B -ntp process-resources
```

Debug log có thể chứa đường dẫn và property nhạy cảm; không đăng nguyên log công khai. Một dòng “Copying resources” **không bảo đảm** mọi placeholder đã được thay đúng.

## 15. Lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `@app.mode@` còn nguyên trong output | Filtering chưa bật, sai delimiter hoặc property thiếu | Kiểm tra `filtering=true`, nguồn property, delimiter |
| Không thấy file trong `target/classes` | Directory/include sai hoặc chưa tới process-resources | Kiểm tra resource set, chạy `clean process-resources` |
| `@team.label@` không được thay | Filter file chưa nạp, key sai hoặc file không tồn tại | Kiểm tra `<filters>` và file `build.properties` |
| `src/main/resources/readme.txt` giữ nguyên token | Resource set có `filtering=false` | Đây là hành vi đúng theo POM mẫu |
| File `application.properties` bị Maven thay token runtime | Maven và framework cùng dùng `${...}` | Chuyển sang `@...@` hoặc giới hạn delimiter |
| Resource binary bị hỏng | Đã thử filter binary như text | Tách folders hoặc dùng nonFilteredFileExtensions |
| JAR còn file cấu hình cũ | Mới chạy process-resources, chưa package lại | Chạy `mvn clean package` và kiểm tra JAR |
| Đổi POM nhưng chạy Java vẫn đọc mode cũ | Chạy classpath/JAR từ build cũ | Rebuild và xác nhận đúng artifact/path |
| Dùng `-Dapp.mode` ở lệnh Java thay vì Maven | Runtime property không sửa resource đã bake | Đặt `-D` ở lệnh Maven build, hoặc chuyển sang runtime config |
| Profile ci không có tác dụng | Quên `-Pci` trong lượt build | Kiểm tra help:active-profiles và output |
| Tiếng Việt thành ký tự lạ | Charset nguồn/output/reader không thống nhất | Cấu hình encoding và dùng Reader phù hợp |
| Hai resource cùng đè `config.properties` | Resource sets có cùng output path | Đổi tên/path, thêm includes/excludes |
| Secret vô tình nằm trong JAR | Đã filter secret vào file đóng gói | Loại khỏi artifact, dùng secret manager |
| Test không thấy resource | Đặt file nhầm main/test directory | Kiểm tra `target/classes` và `target/test-classes` |
| Maven tải plugin lỗi | Repository/mirror/proxy/quyền tải gặp vấn đề | Sửa dependency/plugin resolution, không phải lỗi filtering |
| File output giữ placeholder thiếu giá trị | Không có source property khớp | Kiểm tra exact key trong template/POM/filter file |
| Build nhiều module cho ra version/name khác | `project.*` được tính theo module | Đây có thể là hành vi đúng; kiểm tra đúng module |

### Quy trình debug

1. Xác nhận đường dẫn template và POM thực tế.
2. Kiểm tra `mvn -version`, profile/CLI flags.
3. Xem `help:effective-pom` và `help:evaluate`.
4. Chạy `mvn -B -ntp clean process-resources`.
5. So sánh template nguồn với output ở `target/classes`.
6. Kiểm tra binary safety, delimiter và encoding.
7. Build `mvn clean package` rồi kiểm tra nội dung JAR.
8. Chạy Java class và xem stdout đúng artifact.
9. Rà soát secret hoặc giá trị nhạy cảm trước khi publish.

## 16. Multi-module, code generation và reproducible builds

**Multi-module:** `@project.artifactId@` và `@project.version@` lấy giá trị từ Maven project đang build, nên các module có thể sinh những file build-info khác nhau. Parent POM có thể quản lý version Resources Plugin qua `pluginManagement`, nhưng từng module vẫn cần đúng resource directory và cấu hình filtering. Xem effective POM của **đúng module** trước khi kết luận.

**Code generation:** Goal sinh Java sources thường chạy ở `generate-sources` và thêm source root riêng. Resource filtering không tự chạy generator, không tự tạo source root. Nếu generator tạo file `target/generated-resources/config.properties`, việc filtering file đó chỉ thành công khi generator **đã chạy trước phase/goal copy** và resource set trỏ đúng thư mục.

**Reproducible builds:** Filter các giá trị không ổn định như timestamp, đường dẫn home hay environment-specific secrets có thể khiến cùng source/version tạo artifact khác bytes. Nếu tổ chức yêu cầu reproducible release, giới hạn filtering vào metadata có kiểm soát và đưa cấu hình deploy ra runtime. Đừng coi “build xanh” là bằng chứng hai artifact cùng version có cùng nội dung.

## 17. Bài tập tự kiểm tra

1. `filtering=true` khác `filtering=false` như thế nào?
2. Vì sao file nguồn `build-info.properties` vẫn giữ `@app.mode@` sau build?
3. Sau `mvn process-resources`, resource chính xuất hiện ở thư mục nào?
4. File `src/main/filters/build.properties` có tự được đóng vào JAR không?
5. Vì sao `Properties.load(InputStream)` không tự hiểu file đã lọc bằng UTF-8?
6. Nếu chạy `mvn -Dapp.mode=staging clean package`, dòng mode Java là gì?
7. Làm sao giữ `${RUNTIME_REGION}` cho framework runtime nhưng vẫn thay `@project.version@`?
8. Vì sao nên tránh filter ảnh/ZIP/PDF?
9. `process-test-resources` khác `process-resources` ở file nguồn/output nào?
10. Lệnh `help:effective-pom` có thay thế kiểm tra file output được không?
11. Vì sao thay biến môi trường sau khi build không tự sửa resource đã nằm trong JAR?
12. Nếu hai resource sets sinh cùng `target/classes/config.properties`, nên thay thiết kế ra sao?

**Tổng kết:** Resource filtering là **thay giá trị trong file text khi Maven build**, thông qua `${...}` hoặc `@...@`. Bật `<filtering>true</filtering>` ở đúng resource set, lấy giá trị từ POM/profile/CLI/filter file, chạy `process-resources` hoặc phase sau rồi **mở output thật để xác nhận**. Phải tránh binary, secrets, placeholder runtime bị thay sớm và các lỗi encoding.

## Nguồn Apache Maven chính thức

- [Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Resources Plugin 3.3.1 — resources:resources](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/resources-mojo.html)
- [Resources Plugin — Filtering Properties Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/filtering-properties-files.html)
- [Resources Plugin — Escape Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/escape-filtering.html)
- [Resources Plugin — Binaries Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/binaries-filtering.html)
- [Resources Plugin — Include/Exclude](https://maven.apache.org/plugins/maven-resources-plugin/examples/include-exclude.html)
- [Maven — POM Reference](https://maven.apache.org/pom.html)
- [Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
