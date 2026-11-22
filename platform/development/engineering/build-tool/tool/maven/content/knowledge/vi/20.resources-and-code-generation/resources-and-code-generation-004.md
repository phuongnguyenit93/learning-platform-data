# Delimiters, escaping và xung đột với cú pháp cấu hình ứng dụng trong Maven

## 1. Vấn đề: một placeholder có thể thuộc Maven hoặc thuộc ứng dụng

Trong một Maven project Java, các tệp dưới thư mục tài nguyên có thể được sao chép vào classpath khi build. Nếu bật **resource filtering**, Maven còn tìm và thay các placeholder bằng giá trị của POM, properties hay filter files. Ví dụ một file nguồn chứa:

```properties
build.version=@project.version@
```

và POM có version `1.0.0` thì file đầu ra trong `target/classes` có thể thành:

```properties
build.version=1.0.0
```

Nhưng Spring Boot, hệ thống triển khai hoặc template của ứng dụng cũng có placeholder, chẳng hạn `${SERVICE_URL:http://localhost:8080}`. Chúng được thiết kế để xử lý **lúc chạy**, khi môi trường deployment đã có giá trị cần thiết. Nếu Maven nhận diện cả `${...}` lúc build, những token ấy có thể bị thay quá sớm khi trùng property của Maven, CLI hoặc máy CI.

Vì vậy cần phân biệt:

- **Build-time token:** dùng dữ liệu xác định ở thời điểm build như `project.version`, `project.artifactId` hoặc `build.label`.
- **Runtime placeholder:** được framework hoặc application xử lý khi chạy; không nên để Maven xử lý thay.
- **Text template riêng:** có thể chứa dấu `@...@` hoặc `${...}` nhưng là dữ liệu nguyên văn, cần tránh filtering.
- **Binary resource:** chỉ được copy dưới dạng bytes, không chạy text filtering.

**Quy tắc chủ đạo:** chọn delimiter riêng cho Maven và giới hạn đúng những file cần filtering. Đối với ứng dụng Spring, cấu hình Maven **chỉ dùng `@...@`** thường giúp bảo toàn runtime placeholder `${...}`.

Bài học giải thích delimiter mặc định và tùy chỉnh, `useDefaultDelimiters`, `escapeString`, xung đột giữa các format, giới hạn filtering, ví dụ đầy đủ Maven 3.9/Java 17 và quy trình QA trước khi đóng gói.

## 2. Resource filtering diễn ra ở phase nào?

Với project `packaging=jar`, lifecycle thông dụng chứa các bước:

```text
validate
   |
generate-resources
   |
process-resources        -> resources:resources
   |
compile                  -> compiler:compile
   |
process-test-resources   -> resources:testResources
   |
test-compile             -> compiler:testCompile
   |
test                    -> surefire:test
   |
package                 -> jar:jar
```

Đây là sơ đồ rút gọn, không liệt kê mọi phase. `resources:resources` đọc `project.build.resources`, copy tài nguyên chính vào `project.build.outputDirectory`, mặc định `target/classes`. `resources:testResources` dùng `project.build.testResources` và thường output `target/test-classes`.

**Maven Resources Plugin không biên dịch Java.** Compiler Plugin biên dịch mã nguồn chính/test sau khi các phase resources liên quan đã chạy. Nếu gọi goal `compiler:compile` trực tiếp, Maven không nhất thiết đã chạy `process-resources`. Muốn kiểm tra pipeline chuẩn, dùng `mvn process-resources`, `mvn compile` hoặc phase sau đó.

Filtering chỉ áp dụng khi resource được đánh dấu `<filtering>true</filtering>`, hoặc cấu hình parent/packaging/plugin có hiệu lực tương đương. Việc Maven biết một property không có nghĩa nó sẽ tự đi thay token trong mọi file nằm trong repository.

Ví dụ bật filtering cho một directory:

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

Đây là **đoạn POM**, không phải POM độc lập. Bật quá rộng có thể xử lý nhầm template, JSON, YAML, XML hoặc binary files. Một phương án tốt hơn thường là tách:

```text
src/main/resources-filtered/  -> filtering=true
src/main/resources/           -> filtering=false
```

Sau build, hãy kiểm tra **bản copy tại target/classes**, không chỉ source. Maven không cần sửa file nguồn để thực hiện filtering thành công.

## 3. Delimiters: Maven nhận token theo cú pháp nào?

### 3.1. Delimiter mặc định của Maven Resources Plugin 3.3.1

Hai dạng thường được dùng là:

```text
${property.name}
@property.name@
```

Ví dụ POM:

```xml
<properties>
    <build.label>demo</build.label>
</properties>
```

Nếu file có filtering và các delimiters đang hoạt động thì `@build.label@` hoặc `${build.label}` có thể được đổi thành `demo`.

Nguồn giá trị lọc có thể bao gồm Maven project properties, user/system properties, filter files và các giá trị phù hợp của project. Một token chưa được Maven thay ở local không bảo đảm nó sẽ nguyên ở CI; profile hoặc `-D` có thể thêm property trùng tên sau này.

### 3.2. Cú pháp custom delimiter

Resources Plugin mô tả quy cách:

```text
beginToken*endToken
```

Trong chuỗi cấu hình này, dấu `*` là dấu ngăn giữa tiền tố/hậu tố, không phải glob/regex wildcard. Ví dụ:

```xml
<delimiters>
    <delimiter>${*}</delimiter>
    <delimiter>@</delimiter>
</delimiters>
```

`${*}` quy định bắt đầu `${`, kết thúc `}`. Khi hai vế giống nhau, chỉ cần `@` thay vì `@*@`. Có thể tạo cặp tùy chỉnh như `<delimiter>[[*]]</delimiter>`, nhưng phải kiểm tra nó không trùng syntax của template engine khác.

### 3.3. `useDefaultDelimiters` — tham số quyết định

Trong Resources Plugin 3.3.1:

- `<useDefaultDelimiters>true</useDefaultDelimiters>` là default: **bổ sung** delimiter mặc định bên cạnh custom delimiters.
- `<useDefaultDelimiters>false</useDefaultDelimiters>`: chỉ dùng delimiters bạn khai báo.

Muốn Maven **chỉ thay token `@name@`** và không nhận `${name}`, cần cấu hình **cả hai**:

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

Đây là một plugin fragment nằm trong `<build><plugins>`. **Chỉ thêm `@` mà không đặt false là chưa đủ**, vì Maven vẫn có thể dùng default `${*}`. Đây là một trong các nguyên nhân phổ biến nhất làm Spring placeholder bị thay nhầm.

Ngay cả khi dùng `@`-only, file template có `@customer.name@` cũng có thể bị xử lý nếu file ấy bị filtering và Maven có property cùng tên. Không có delimiter nào thay thế được việc chọn **đúng phạm vi file**.

## 4. Vì sao Spring placeholders xung đột với Maven?

### 4.1. Build time và runtime có dữ liệu khác nhau

Maven thường biết `project.version`, `project.name`, property ở POM, user properties qua CLI và các giá trị filter. Spring hoặc ứng dụng runtime có thể đọc environment variables, system properties, configuration sources và defaults theo các quy tắc riêng.

Ví dụ Spring configuration:

```properties
service.url=${SERVICE_URL:http://localhost:8080}
message.template=${user.name}
```

Nếu Maven đang nhận delimiter `${*}`, nó có thể xử lý các token này như Maven properties. `user.name` có thể tồn tại trên máy build và biến thành username của CI; như vậy một placeholder được định dùng ở runtime đã bị thay thành literal quá sớm.

Với Maven `@`-only và file đã bật filtering, Spring placeholder `${...}` **không khớp delimiter Maven**, nên giữ nguyên trong output. Khi ứng dụng thật chạy, Spring mới có cơ hội xử lý.

### 4.2. Trường hợp YAML

Nguồn YAML:

```yaml
app:
  build-version: "@project.version@"
service:
  url: "${SERVICE_URL:http://localhost:8080}"
```

Khi Maven project version `1.0.0` và dùng `@`-only, output kỳ vọng:

```yaml
app:
  build-version: "1.0.0"
service:
  url: "${SERVICE_URL:http://localhost:8080}"
```

Nên đặt dấu nháy quanh `@project.version@` vì một YAML plain scalar bắt đầu bằng `@` có thể không hợp lệ. Với placeholder chứa dấu `:`, quotes cũng giúp tránh parser ambiguity.

### 4.3. Spring Boot parent và việc chạy ứng dụng

Theo tài liệu Spring Boot, `spring-boot-starter-parent` có thể cung cấp thiết lập filtering dùng `@...@` nhằm tránh xung đột với syntax `${...}` của Spring. Tuy nhiên, không nên giả định mọi project đã có parent ấy hoặc không override configuration. Hãy đọc **effective POM**.

Ngoài ra, một số cách chạy `spring-boot:run` có thể đưa `src/main/resources` trực tiếp lên classpath bằng tùy chọn `addResources`, **bỏ qua output đã filtering** để hỗ trợ hot reload. Nếu Maven package đúng nhưng khi chạy trong IDE lại thấy `@project.version@`, hãy kiểm tra classpath/run configuration trước khi đổ lỗi cho Resources Plugin.

### 4.4. Không để build-time và runtime cùng “sở hữu” một token

Một file application config có thể chủ ý dùng cả hai:

```properties
application.build-version=@project.version@
server.port=${PORT:8080}
```

Nếu namespace được phân chia, Maven chỉ đổi build-version, runtime vẫn nhận `${PORT:8080}`. Nếu để mặc định `${*}`, một profile/build property mới có thể bất ngờ đổi port ngay khi build. **Tốt nhất là loại bỏ xung đột từ thiết kế**, không mong rằng tất cả môi trường build đều thiếu các property tương ứng.

## 5. Escaping: giữ một expression nguyên vẹn trong file được lọc

### 5.1. `escapeString` là escape của Maven Resources Plugin

Nếu buộc phải giữ một token mà Maven có thể nhận diện, plugin cho phép escape prefix:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-resources-plugin</artifactId>
    <version>3.3.1</version>
    <configuration>
        <escapeString>\</escapeString>
    </configuration>
</plugin>
```

Với delimiter `${*}` đang hoạt động và version `1.0.0`:

```text
Resource input:
literal=\${project.version}
normal=${project.version}

Filtered output:
literal=${project.version}
normal=1.0.0
```

Escape prefix `\` được gỡ, token có escape được giữ nguyên; token không escape được nội suy. Đây là **Maven filtering**, không phải logic tự động của Spring hay parser Java.

### 5.2. Double backslash không phải “escape mạnh hơn”

Tài liệu plugin nêu ví dụ ý nghĩa khi escape prefix là một backslash:

```text
\${foo}    -> ${foo}
\\${foo}   -> \\value-of-foo
```

Dòng thứ hai mô tả trường hợp Maven biết giá trị `foo`; thêm backslash thứ hai có thể khiến interpolation diễn ra và tạo số backslash khác dự đoán. Đừng áp dụng trực giác của Java string literal cho raw resource text.

**Ba lớp escaping riêng biệt** có thể cùng tham gia:
1. Maven `escapeString` khi lọc source resource.
2. Cú pháp file sau lọc (`.properties`, YAML, JSON, XML).
3. Framework/parser/application khi runtime đọc file.

Vì vậy phải so sánh **input → target output → runtime value**, chứ không chỉ đọc source.

### 5.3. Khi nào không nên dùng escapeString?

Nếu có hàng trăm runtime placeholders `${...}` trong Spring configuration, yêu cầu thêm `\` trước tất cả là khó bảo trì. Một placeholder mới chưa escape có thể bị Maven xử lý; các parser khác còn có escape syntax riêng. Trong tình huống này **đổi Maven delimiter sang `@`-only** là phương án đơn giản và rõ ràng hơn.

Dùng `escapeString` cho một số ngoại lệ nhỏ trong file bắt buộc lọc cả hai dạng; không xem nó là biện pháp bảo vệ mặc định cho toàn bộ YAML/JSON/properties.

## 6. Những tham số liên quan cần hiểu

### 6.1. Windows path escaping

`escapeWindowsPaths` mặc định là `true` trong Resources Plugin 3.3.1, hỗ trợ escape dấu `\` và `:` trong Windows-style paths khi filtering. Nó **khác** `escapeString` để giữ token. Nếu một value `C:\work\data` được thay vào file properties rồi Java đọc sai, hãy kiểm tra bytes/text trong `target/classes` và cú pháp `Properties.load`; đừng sửa `escapeString` ngẫu nhiên.

Khi có thể, tránh đóng absolute path của máy build vào JAR; dùng relative path hoặc runtime configuration thích hợp.

### 6.2. Charset của filtered resources

Đặt encoding rõ ràng:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
```

`encoding` của plugin điều khiển filtered text; `propertiesEncoding` từ plugin 3.2.0 điều khiển filtered `.properties`. Nếu muốn cấu hình tường minh:

```xml
<configuration>
    <encoding>UTF-8</encoding>
    <propertiesEncoding>UTF-8</propertiesEncoding>
</configuration>
```

Nhưng **Maven ghi UTF-8 không bảo đảm ứng dụng tự đọc UTF-8**. Java `Properties.load(InputStream)` theo API truyền thống xử lý ISO-8859-1 và Unicode escapes; dùng `Properties.load(Reader)` với `InputStreamReader(..., UTF_8)` nếu file thực sự là UTF-8. Ví dụ Java phía dưới cố tình dùng Reader để tránh lẫn lộn hai lớp này.

### 6.3. Không filter binary assets

Maven filtering là text substitution, không phù hợp để chạy qua PDF, ZIP, JAR, font, image hay binary data khác. Plugin mặc định bỏ filtering với một số đuôi ảnh như `jpg`, `jpeg`, `gif`, `bmp`, `png`, và có thể bổ sung:

```xml
<nonFilteredFileExtensions>
    <nonFilteredFileExtension>pdf</nonFilteredFileExtension>
    <nonFilteredFileExtension>zip</nonFilteredFileExtension>
    <nonFilteredFileExtension>woff2</nonFilteredFileExtension>
</nonFilteredFileExtensions>
```

Cách mạnh hơn là tách các binary files, email templates và files chứa runtime tokens sang **resource directory không filtering**. Ngay cả một SVG/JSON/XML text hợp lệ cũng có thể chứa `@...@` quan trọng, nên không filter chỉ vì nó là text.

### 6.4. Filename và multiline tokens

`fileNameFiltering` (default `false`) điều khiển khả năng xử lý token trong **tên file hoặc folder**; đừng nghĩ bật filtering nội dung sẽ đổi filename `@version@.txt`. `supportMultiLineFiltering` (default `false`) ảnh hưởng tìm end token qua newline. Với cấu hình đơn giản, dùng token một dòng và filenames cố định để tránh hành vi khó đoán.

## 7. Ví dụ Java 17 đầy đủ: @...@ được thay, ${...} được giữ

### 7.1. Mục tiêu

Chúng ta tạo một project có:
- hai file properties **được filtering**;
- một template text **không filtering**;
- một class Java đọc output files từ classpath;
- Maven `@`-only với `useDefaultDelimiters=false`.

Không cần Spring Boot runtime: mục tiêu của demo là xác minh **điều Maven Resources Plugin ghi ra**, không giả vờ Java tự phân giải Spring placeholders.

### 7.2. Cấu trúc thư mục

```text
resource-token-lab/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/filtering/App.java
        ├── resources-filtered/
        │   ├── build-info.properties
        │   └── application.properties
        └── resources/
            └── templates/prompt.txt
```

`src/main/resources-filtered` không phải default directory của Maven: nó hoạt động nhờ khai báo trong POM. Không có hai input files trùng đường dẫn tương đối, nên không có nguy cơ overwrite mơ hồ.

### 7.3. POM hoàn chỉnh

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>resource-token-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <build.label>demo</build.label>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources-filtered</directory>
                <filtering>true</filtering>
            </resource>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>false</filtering>
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
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Trong POM này, `build.label=demo` là property Maven; `project.version` bằng 1.0.0. Chỉ `resources-filtered` được text filtering, còn `src/main/resources` được copy nguyên. Mặc định packaging JAR đã bind Resources Plugin vào `process-resources`; không cần thêm một plugin execution trùng.

### 7.4. File build-info.properties

Tạo `src/main/resources-filtered/build-info.properties`:

```properties
build.version=@project.version@
build.label=@build.label@
```

Hai token thuộc Maven và được thay khi lọc.

### 7.5. File application.properties

Tạo `src/main/resources-filtered/application.properties`:

```properties
service.url=${SERVICE_URL:http://localhost:8080}
message.template=${user.name}
```

File này **vẫn có filtering=true**, nhưng Maven chỉ nhận `@...@`, nên hai placeholder `${...}` được bảo toàn. Một Spring application thật có thể tiếp tục xử lý chúng ở runtime; demo Java chỉ in giá trị raw.

### 7.6. File template không filtering

Tạo `src/main/resources/templates/prompt.txt`:

```text
Template @should.stay@ and ${runtime.name}
```

Do directory này `filtering=false`, nội dung được copy nguyên ngay cả khi Maven có property trùng `should.stay`.

### 7.7. Class Java 17 runnable

Tạo `src/main/java/com/example/filtering/App.java`:

```java
package com.example.filtering;

import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class App {
    private App() {
    }

    private static Properties loadProperties(String path)
            throws IOException {
        try (InputStream in = App.class.getClassLoader()
                .getResourceAsStream(path)) {
            if (in == null) {
                throw new FileNotFoundException(path);
            }
            Properties props = new Properties();
            props.load(new InputStreamReader(
                    in, StandardCharsets.UTF_8));
            return props;
        }
    }

    private static String loadText(String path)
            throws IOException {
        try (InputStream in = App.class.getClassLoader()
                .getResourceAsStream(path)) {
            if (in == null) {
                throw new FileNotFoundException(path);
            }
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    public static void main(String[] args) throws IOException {
        Properties build = loadProperties("build-info.properties");
        Properties app = loadProperties("application.properties");

        System.out.println("build.version="
                + build.getProperty("build.version"));
        System.out.println("build.label="
                + build.getProperty("build.label"));
        System.out.println("service.url="
                + app.getProperty("service.url"));
        System.out.println("message.template="
                + app.getProperty("message.template"));
        System.out.println("template="
                + loadText("templates/prompt.txt"));
    }
}
```

Class này chỉ dùng Java Standard Library, đọc files từ classpath và không cần dependency ngoài. `Properties.load(Reader)` dùng UTF-8 qua Reader. `readAllBytes` và `strip` có trong Java 17. Những dòng in cố định, không phụ thuộc tên người dùng, thời gian, network hoặc biến môi trường trên máy build.

### 7.8. Process resources rồi kiểm tra output

Trong thư mục `resource-token-lab`:

```bash
mvn -version
mvn clean process-resources
```

Sau khi hoàn tất, cần có:

```text
target/classes/build-info.properties
target/classes/application.properties
target/classes/templates/prompt.txt
```

File `target/classes/build-info.properties`:

```properties
build.version=1.0.0
build.label=demo
```

File `target/classes/application.properties`:

```properties
service.url=${SERVICE_URL:http://localhost:8080}
message.template=${user.name}
```

File `target/classes/templates/prompt.txt`:

```text
Template @should.stay@ and ${runtime.name}
```

Source dưới `src/main` không cần bị sửa. Đó là phân biệt quan trọng giữa **input resource** và **copy đã được filter**.

### 7.9. Compile và chạy app

```bash
mvn clean compile
java -cp target/classes com.example.filtering.App
```

**Stdout chính xác của Java:**

```text
build.version=1.0.0
build.label=demo
service.url=${SERVICE_URL:http://localhost:8080}
message.template=${user.name}
template=Template @should.stay@ and ${runtime.name}
```

Đây là năm dòng từ `App.main()`, không phải toàn bộ log của `mvn clean compile`. Log Maven còn có goal/plugin info và trạng thái build.

### 7.10. Đóng gói JAR

```bash
mvn clean package
jar tf target/resource-token-lab-1.0.0.jar
```

Các entries chính mong đợi trong JAR:

```text
build-info.properties
application.properties
templates/prompt.txt
com/example/filtering/App.class
```

Có thể còn các entries `META-INF`. POM chưa cấu hình manifest Main-Class nên `java -jar` không phải cách chạy demo; dùng `java -cp target/classes com.example.filtering.App` như trên.

## 8. Thí nghiệm trước–sau: khi bật default delimiters

### 8.1. Thử làm token runtime bị thay

Tạm đổi:

```xml
<useDefaultDelimiters>true</useDefaultDelimiters>
```

và thay một dòng trong `application.properties`:

```properties
message.template=${build.label}
```

Sau:

```bash
mvn clean process-resources
```

Maven nay nhận `${*}` và biết `build.label=demo`, nên dòng có thể thành:

```properties
message.template=demo
```

Đây là minh họa xung đột: cùng syntax đang được Maven xử lý trước runtime framework. Token khác có thể vẫn nguyên nếu Maven thiếu property, nhưng điều đó **không làm cấu hình an toàn** cho build trên máy khác.

Khôi phục `useDefaultDelimiters=false` và `message.template=${user.name}`.

### 8.2. Thí nghiệm escapeString

Tạm bật default `${*}` và thêm vào plugin configuration:

```xml
<escapeString>\</escapeString>
```

Trong một **filtered** resource thử nghiệm:

```text
literal=\${project.version}
expanded=${project.version}
```

Sau process-resources với project version 1.0.0:

```text
literal=${project.version}
expanded=1.0.0
```

Đây chỉ là thử nghiệm phụ, **không phải POM runnable gốc**. Sau khi học xong hãy khôi phục delimiter `@`-only để tránh nguy cơ cho hàng trăm runtime tokens.

### 8.3. Đổi property build.label

Tại POM gốc, thay `<build.label>demo</build.label>` bằng `<build.label>qa</build.label>`, giữ `useDefaultDelimiters=false`. Chạy `mvn clean compile` rồi Java. `build.label` trên stdout sẽ thành `qa`, còn các placeholder `${SERVICE_URL:...}`, `${user.name}` và template không filtering sẽ giữ nguyên. Khôi phục `demo` sau thử nghiệm.

## 9. Giới hạn filtering theo includes và excludes

Một phương án khác là dùng **hai resource entries cùng thư mục**, với những tập files không trùng:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>true</filtering>
        <includes>
            <include>build-info.properties</include>
        </includes>
    </resource>
    <resource>
        <directory>src/main/resources</directory>
        <filtering>false</filtering>
        <excludes>
            <exclude>build-info.properties</exclude>
        </excludes>
    </resource>
</resources>
```

Đây là **thay thế cấu hình resources**, không dán thêm vào POM demo đồng thời. Nó giúp filter đúng `build-info.properties`, trong khi YAML, XML, JSON, email templates và binary còn lại chỉ được copy. Tránh hai entries cùng copy một đường dẫn file gây overwrite không rõ.

`filtering=false` **không có nghĩa file không được đóng gói**; nó chỉ không xử lý token. Muốn loại file khỏi artifact cần `excludes`/packaging rules phù hợp.

## 10. Nguồn giá trị và nguy cơ build khác nhau

### 10.1. POM và CLI

Ví dụ:

```xml
<properties>
    <build.label>demo</build.label>
</properties>
```

Resource `label=@build.label@` được Maven thay theo giá trị đã phân giải. CLI có thể truyền:

```bash
mvn -Dbuild.label=release-candidate clean process-resources
```

Kết quả phụ thuộc nguồn properties và precedence trong model của lần build; nếu muốn reproducibility, hãy kiểm soát POM, parent/profiles, filters và `-D`. Không thiết kế nhiều nguồn cùng key rồi dựa vào suy đoán; tốt hơn là có một nguồn quản lý rõ ràng và test output.

### 10.2. Filter files

Maven có thể đọc file properties bổ sung thông qua:

```xml
<build>
    <filters>
        <filter>src/main/filters/build.properties</filter>
    </filters>
</build>
```

Với file:

```properties
build.banner=Demo Application
```

resource `banner=@build.banner@` có thể được thay khi filtering. Đây là **ví dụ bổ sung** ngoài bộ file runnable. Nếu thêm đoạn POM, phải tạo filter file trước; tránh để secrets trong đó.

### 10.3. Không filter credentials vào artifact

Không nên viết resource chứa `password=@db.password@` rồi để build Maven chèn password production. Giá trị sẽ nằm trong `target/classes` và JAR/WAR, dễ bị trích xuất. Thay vì đóng gói secrets trong artifact, dùng environment hoặc secret manager **ở runtime**. Khi log debug có in property, phải bảo vệ/cắt bỏ giá trị nhạy cảm trước khi chia sẻ.

## 11. Các loại cấu hình dễ bị lỗi

**Spring application.properties:** dùng `@project.version@` cho build metadata, giữ `${PORT:8080}` cho runtime. Nếu tự chỉnh Maven parent, kiểm tra effective POM và output thay vì mặc định setup đúng.

**YAML:** quote token `"@project.version@"`; quote placeholder chứa dấu colon; Maven không tự validate YAML. Value thay có dấu nháy hoặc newline có thể phá cú pháp.

**JSON:** một input như:

```json
{
  "buildVersion": "@project.version@",
  "endpoint": "${API_URL}"
}
```

có thể xử lý đúng với `@`-only. Nhưng Maven không tự JSON-escape value có dấu `"` hoặc newline; với value phức tạp cần JSON serializer/template engine chuyên dụng.

**XML:** một resource XML có attribute `version="@project.version@"`, nhưng value chứa `&` hoặc `<` có thể khiến XML không hợp lệ nếu chưa escape. Filtering là text substitution, không phải XML writer.

**Shell, Compose, environment, template files:** syntax `${VAR}`, `@NAME@` hoặc các ký hiệu tương tự có thể thuộc chính công cụ runtime. Hãy để chúng trong unfiltered directory nếu không chủ động cần Maven thay.

**Test resources:** `resources:testResources` đọc cấu hình `<build><testResources>` riêng. Đừng giả định thay đổi `<build><resources>` cho main sẽ áp dụng giống hệt các golden files/test snapshots.

## 12. Lỗi thường gặp và quy trình chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `@project.version@` không đổi | File chưa filtering, thiếu delimiter, sai directory | Kiểm tra resources config và `target/classes` |
| `${user.name}` bị thay bằng tên CI user | Default delimiter `${*}` vẫn hoạt động | Dùng `@` và `useDefaultDelimiters=false` |
| Đã thêm `@` mà Spring placeholder vẫn bị xử lý | Quên `useDefaultDelimiters=false` | Sửa config, build sạch |
| Token chưa bị thay ở local nhưng bị thay trên CI | Property trùng xuất hiện ở môi trường khác | Tách namespace, kiểm soát inputs |
| `\${foo}` giữ nguyên backslash ngoài ý muốn | `escapeString` chưa cấu hình hoặc sai | Kiểm tra plugin config, target output |
| Double slash khiến token được nội suy | Nhiều lớp escaping | Test input, Maven output và runtime parser |
| Template `@name@` bị thay | Template nằm trong filtered directory | Chuyển sang unfiltered resource |
| Tiếng Việt bị lỗi | Encoding Maven/reader không khớp | Đặt UTF-8, load bằng Reader |
| Windows path sai | `escapeWindowsPaths` và parser properties tương tác | Xem file target và runtime value |
| Binary/JAR/font bị hỏng | Filtering áp vào bytes không phải text | Tách directory và loại extension |
| JSON/YAML/XML không parse được | Value thay không được format-escape | Quote, encode, validate format |
| Source còn token, target đã đổi | Đúng: Maven chỉ filter bản copy | Không sửa source để kiểm chứng |
| IDE chạy thấy token khác package | IDE dùng raw resources hoặc classpath khác | Kiểm tra run config, build output |
| Secrets lộ trong JAR | Dùng filtering cho credentials | Chuyển sang runtime secrets; xử lý lộ lọt |
| Resource không xuất hiện trong artifact | Includes/excludes/path sai | Kiểm tra target/classes, JAR entries |

### Kiểm tra theo thứ tự

1. Xác định file source và file output tương ứng, không xem nhầm.
2. Chạy `mvn clean process-resources` để bỏ output cũ.
3. Kiểm tra `<resource>` đúng directory, `<filtering>`, includes/excludes.
4. Kiểm tra `maven-resources-plugin` version và `<delimiters>`.
5. Kiểm tra `useDefaultDelimiters`, `escapeString`, `escapeWindowsPaths`.
6. Kiểm tra `encoding` và `propertiesEncoding` cùng runtime reader.
7. Xem `target/classes` và nội dung artifact phát hành.
8. So POM, parent, profiles, CLI/filter files giữa CI và local.
9. Thêm automated test đảm bảo runtime placeholders còn nguyên.

Lệnh tra metadata và cấu hình:

```bash
mvn -version
mvn clean process-resources
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:describe "-Dplugin=org.apache.maven.plugins:maven-resources-plugin:3.3.1" -Dgoal=resources -Ddetail=true
mvn clean package
jar tf target/resource-token-lab-1.0.0.jar
```

`help:effective-pom` phản ánh POM sau inheritance/profile, `help:describe` phản ánh metadata plugin goal. Cả hai **không thay thế việc đọc file sau filtering**. Debug `-X` có thể chứa hạ tầng/secret; chỉ sử dụng và chia sẻ khi đã bảo vệ dữ liệu nhạy cảm.

## 13. Bài tập tự đánh giá

**Bài 1.** Chỉ thêm `<delimiter>@</delimiter>` mà không khai báo `useDefaultDelimiters`; token `${user.name}` có an toàn khỏi Maven không? **Không chắc**, vì mặc định vẫn là true.

**Bài 2.** POM version 1.0.0, filtering `@`-only. File có `version=@project.version@` và `url=${API_URL}`. Output là gì? **`version=1.0.0`, `url=${API_URL}`**.

**Bài 3.** Có `escapeString=\`, delimiter `${*}`. `\${project.version}` trở thành gì? **`${project.version}`**, không còn backslash escape.

**Bài 4.** File email template có `@customer.name@`. Maven POM cũng có property `customer.name`. Làm sao tránh thay ngoài ý muốn? **Đặt template trong unfiltered resources**.

**Bài 5.** Tại sao quote `"@project.version@"` trong YAML? Vì plain scalar bắt đầu `@` có thể không hợp lệ với YAML parser.

**Bài 6.** Resource `.woff2` trong thư mục filtering bị hỏng. Hướng xử lý? **Không text-filter binary; tách directory hoặc dùng nonFiltered extensions**.

**Bài 7.** Maven filtering UTF-8 nhưng Java `Properties.load(InputStream)` đọc sai Unicode. Vì sao? Vì API này dùng encoding theo hợp đồng khác; dùng `Properties.load(Reader)` với UTF-8.

**Bài 8.** Maven không thay source `@project.version@` nhưng target có 1.0.0. Đúng không? **Đúng**, filtering làm trên bản copy.

**Bài 9.** Có nên điền password production vào `@db.password@` trong JAR? **Không**, dùng runtime secret injection.

**Bài 10.** Vì sao `filtering=false` không ngăn file secret vào JAR? Vì nó **chỉ tắt text substitution**, không tự exclude file khỏi copying.

## 14. Checklist trước khi merge

- [ ] Xác định những files thực sự cần build-time values.
- [ ] Chọn delimiter Maven khác runtime placeholders.
- [ ] Đặt `useDefaultDelimiters` tường minh.
- [ ] Giới hạn `<resources>` và includes/excludes, không lọc toàn bộ nếu không cần.
- [ ] Kiểm tra escaping và parser của file sau Maven.
- [ ] Không lọc binary assets, email templates và runtime fixtures.
- [ ] Đồng bộ charset filtering với charset runtime reader.
- [ ] Không đóng gói secrets nhờ Maven token substitution.
- [ ] Ghim plugin versions và kiểm tra effective POM.
- [ ] Kiểm tra `target/classes` và file nằm trong JAR.
- [ ] Có test xác nhận runtime placeholders phải giữ nguyên.

**Ghi nhớ:** Maven Resources Plugin làm **text substitution tại build time**. Nếu ứng dụng dùng `${...}` ở runtime, bật lọc cả `${*}` dễ gây xung đột. Cấu hình `<delimiter>@</delimiter>` cùng `<useDefaultDelimiters>false</useDefaultDelimiters>` và **phạm vi resources được lọc có chủ đích** là một thiết kế dễ hiểu, dễ kiểm chứng. `escapeString` giúp xử lý ngoại lệ; kiểm tra output thực tế luôn cần thiết.

### Tài liệu chính thức

- [Apache Maven — Guide to Filtering Resources](https://maven.apache.org/guides/mini/guide-filtering-resources.html)
- [Apache Maven Resources Plugin 3.3.1 — resources:resources](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/resources-mojo.html)
- [Apache Maven Resources Plugin 3.3.1 — Escape Filtering](https://maven.apache.org/plugins-archives/maven-resources-plugin-3.3.1/examples/escape-filtering.html)
- [Apache Maven Resources Plugin — Filtering Properties Files](https://maven.apache.org/plugins/maven-resources-plugin/examples/filtering-properties-files.html)
- [Spring Boot — Automatic Property Expansion Using Maven](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
