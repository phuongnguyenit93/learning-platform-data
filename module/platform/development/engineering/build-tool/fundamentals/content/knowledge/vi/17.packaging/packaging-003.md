# Manifest và khai báo điểm khởi chạy Main-Class

Một JAR có thể chứa bytecode, resource, metadata và các thư viện cần thiết cho một ứng dụng Java. Tuy nhiên, chỉ có các tệp `.class` bên trong JAR chưa đủ để Java launcher biết lớp nào cần được gọi đầu tiên khi người dùng chạy ứng dụng.

JAR có thể chứa một tệp metadata đặc biệt là `META-INF/MANIFEST.MF`. Manifest mô tả thông tin của archive và có thể khai báo điểm khởi chạy bằng thuộc tính **`Main-Class`**. Khi manifest được cấu hình đúng, người dùng có thể chạy ứng dụng theo dạng:

```bash
java -jar application.jar
```

`Main-Class` cho Java launcher biết tên lớp chứa phương thức `main` để bắt đầu ứng dụng. Thuộc tính này giúp JAR có thể được khởi chạy trực tiếp, nhưng không tự đóng gói các dependency bên ngoài, không tự tạo cấu hình runtime và cũng không biến mọi JAR thành ứng dụng độc lập.

## 1. Manifest là gì?

Manifest là tệp metadata nằm ở đường dẫn chuẩn trong JAR:

```text
META-INF/MANIFEST.MF
```

JAR là định dạng archive dựa trên ZIP. Manifest là một tệp văn bản theo định dạng quy định của Java, được lưu bên trong archive. Nó chứa các cặp thuộc tính và giá trị, chẳng hạn:

```text
Manifest-Version: 1.0
Created-By: 21.0.2 (Eclipse Adoptium)
Main-Class: com.example.Application
```

Một số thuộc tính manifest thường gặp:

| Thuộc tính | Mục đích |
|---|---|
| `Manifest-Version` | Phiên bản định dạng manifest |
| `Main-Class` | Tên lớp điểm vào khi chạy JAR bằng `java -jar` |
| `Class-Path` | Danh sách URL tương đối/đường dẫn tham chiếu tới các vị trí cần bổ sung vào class path của JAR |
| `Implementation-Title` | Tên sản phẩm hoặc implementation |
| `Implementation-Version` | Phiên bản implementation |
| `Implementation-Vendor` | Nhà cung cấp implementation |
| `Specification-Title` | Tên đặc tả mà package/lớp triển khai |
| `Specification-Version` | Phiên bản đặc tả |
| `Automatic-Module-Name` | Tên module tự động khi JAR không có module descriptor tường minh và được dùng như automatic module |
| `Multi-Release` | Đánh dấu JAR đa phiên bản khi có giá trị `true` |

Không phải mọi thuộc tính đều bắt buộc. Công cụ đóng gói có thể tự tạo `Manifest-Version` và một số metadata khác. Với ứng dụng chạy bằng `java -jar`, thuộc tính quan trọng nhất trong bài này là `Main-Class`.

## 2. Cấu trúc và quy tắc cơ bản của manifest

Manifest gồm các section. Main section nằm ở đầu tệp; sau một dòng trống, các section tiếp theo có thể mô tả từng entry hoặc nhóm tài nguyên cụ thể.

Ví dụ:

```text
Manifest-Version: 1.0
Main-Class: com.example.Application
Implementation-Title: Order Service
Implementation-Version: 2.4.0

Name: com/example/
Specification-Title: Order API
Specification-Version: 2.4
```

Các điểm cần nhớ:

- Mỗi thuộc tính có dạng `Tên: Giá trị`.
- Dòng trống phân tách main section với section tiếp theo.
- Tên thuộc tính không phân biệt chữ hoa/thường theo định dạng manifest; giá trị như tên lớp Java vẫn phải đúng chữ hoa/thường.
- Một dòng manifest dài có thể được nối tiếp ở dòng sau bằng một dấu cách ở đầu dòng tiếp theo. Đây là quy tắc continuation line của định dạng manifest.
- Manifest dùng encoding UTF-8 theo đặc tả hiện đại; khi tự tạo file, nên dùng công cụ JDK hoặc build plugin để tránh lỗi định dạng.
- `Manifest-Version` nếu có phải là thuộc tính đầu tiên trong main section.

Trong thực tế, nên để công cụ `jar`, Gradle hoặc Maven tạo manifest thay vì tự ghi file thủ công. Công cụ sẽ xử lý định dạng archive và thuộc tính đúng quy tắc.

## 3. `Main-Class` có ý nghĩa gì?

`Main-Class` là thuộc tính manifest chỉ ra lớp mà Java launcher sẽ sử dụng làm điểm khởi chạy khi chạy JAR theo dạng `java -jar`.

Ví dụ:

```text
Main-Class: com.example.Application
```

Giá trị phải là **binary name** của lớp Java, thường là tên package cộng tên lớp, phân tách bằng dấu chấm. Không thêm phần mở rộng `.class`, không dùng dấu `/` của đường dẫn và không ghi tên file JAR.

Giả sử mã nguồn:

```java
package com.example;

public class Application {
    public static void main(String[] args) {
        System.out.println("Application started");
    }
}
```

Tên đúng trong manifest là:

```text
Main-Class: com.example.Application
```

Các giá trị sau là sai:

```text
Main-Class: com/example/Application.class
Main-Class: Application.class
Main-Class: com.example.Application.class
```

Nếu lớp nằm trong package mặc định, giá trị chỉ là tên lớp, nhưng ứng dụng thực tế nên đặt lớp trong package có tên để tránh xung đột và hỗ trợ tổ chức mã nguồn tốt hơn.

## 4. Lớp Main-Class cần có phương thức main phù hợp

Trong mô hình ứng dụng Java truyền thống, lớp điểm vào thường cung cấp phương thức:

```java
public static void main(String[] args)
```

Ví dụ đầy đủ:

```java
package com.example;

public class Application {
    public static void main(String[] args) {
        System.out.println("Application started");

        for (String arg : args) {
            System.out.println("Argument: " + arg);
        }
    }
}
```

`main` là phương thức `static`, vì launcher cần gọi nó mà không phải tạo instance của lớp chính. `String[] args` chứa các đối số được truyền vào ứng dụng.

Các phiên bản Java mới đã mở rộng một số quy tắc khởi chạy trong các phiên bản ngôn ngữ/runtime tương ứng, nhưng dạng `public static void main(String[] args)` vẫn là lựa chọn phổ biến và tương thích rộng cho ứng dụng đóng gói truyền thống.

Khai báo `Main-Class` không làm compiler tự kiểm tra rằng lớp có phương thức `main` hợp lệ. Một JAR vẫn có thể được tạo với giá trị manifest sai; lỗi thường chỉ xuất hiện khi chạy.

## 5. Cấu trúc dự án và vị trí class file

Giả sử dự án có cấu trúc:

```text
application/
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── Application.java
├── build.gradle
└── settings.gradle
```

Sau khi biên dịch, class file thường nằm trong:

```text
build/classes/java/main/com/example/Application.class
```

Khi đóng gói, JAR cần chứa entry tương ứng:

```text
com/example/Application.class
```

Manifest không trỏ tới đường dẫn trên filesystem của máy phát triển. Nó lưu tên lớp logic để launcher tìm class qua classpath của ứng dụng.

Nếu manifest khai báo `com.example.Application` nhưng JAR không chứa lớp đó và class path cũng không có nguồn khác cung cấp lớp, launcher/JVM không thể nạp điểm vào.

## 6. Tạo executable JAR bằng công cụ `jar`

JDK cung cấp lệnh `jar` để tạo và thao tác với JAR.

Giả sử đã biên dịch lớp chính vào thư mục `out`:

```text
out/
└── com/example/Application.class
```

Có thể tạo JAR và đặt Main-Class bằng tùy chọn `--main-class`:

```bash
jar --create \
    --file application.jar \
    --main-class com.example.Application \
    -C out .
```

Ý nghĩa:

- `--create`: tạo archive mới.
- `--file application.jar`: tên JAR đầu ra.
- `--main-class com.example.Application`: ghi thuộc tính Main-Class vào manifest.
- `-C out .`: chuyển working directory của thao tác `jar` sang `out` và thêm nội dung thư mục đó vào archive.

Cú pháp ngắn tương đương thường gặp:

```bash
jar cfe application.jar com.example.Application -C out .
```

Trong đó `c` là create, `f` chỉ định file archive và `e` khai báo điểm vào. Có thể xem trợ giúp của phiên bản JDK đang dùng bằng:

```bash
jar --help
```

Sau khi tạo, kiểm tra nội dung:

```bash
jar tf application.jar
```

Đọc manifest:

```bash
unzip -p application.jar META-INF/MANIFEST.MF
```

`unzip` là công cụ hệ thống phổ biến nhưng không nhất thiết được cài trên mọi máy. Có thể mở JAR bằng công cụ ZIP hoặc dùng API Java để đọc manifest nếu môi trường không có `unzip`.

Chạy ứng dụng:

```bash
java -jar application.jar
```

Truyền đối số cho `main`:

```bash
java -jar application.jar --port 8080 --profile local
```

Các đối số sau tên JAR được chuyển tới `String[] args`.

## 7. Chạy JAR bằng `java -jar` và bằng `-cp` khác nhau thế nào?

Có hai cách khởi chạy phổ biến:

### 7.1. Dùng `java -jar`

```bash
java -jar application.jar
```

Launcher đọc `Main-Class` từ manifest của JAR để xác định lớp điểm vào. Khi dùng `-jar`, các thiết lập classpath thông thường trên command line hoặc biến `CLASSPATH` không được dùng như trong chế độ `-cp`; JAR được chỉ định là nguồn lớp người dùng chính, cùng các vị trí được khai báo qua manifest `Class-Path` nếu có.

### 7.2. Dùng `-cp` và chỉ rõ lớp chính

```bash
java -cp "application.jar:lib/*" com.example.Application
```

Trên Windows, dùng dấu `;`:

```powershell
java -cp "application.jar;lib\*" com.example.Application
```

Ở chế độ này, người chạy chỉ định classpath và tên lớp chính trực tiếp. `Main-Class` trong manifest không được dùng để chọn điểm vào.

| Cách chạy | Điểm vào lấy từ đâu? | Classpath lấy từ đâu? |
|---|---|---|
| `java -jar application.jar` | Manifest `Main-Class` | JAR được chỉ định và manifest `Class-Path` |
| `java -cp ... com.example.Application` | Tên lớp ghi trên command line | Giá trị `-cp`/`-classpath` |

Nếu cần truyền classpath tùy chỉnh rõ ràng, `-cp` thường phù hợp. Nếu muốn người dùng chạy một JAR theo một lệnh đơn giản, `-jar` và manifest `Main-Class` thuận tiện hơn.

## 8. `Main-Class` không tự đóng gói dependency

Đây là điểm dễ gây nhầm: một JAR có `Main-Class` chỉ biết lớp nào cần gọi đầu tiên. Nó không tự chứa các thư viện bên ngoài mà ứng dụng sử dụng.

Ví dụ:

```text
application.jar
  └── com/example/Application.class

lib/
  ├── jackson-databind.jar
  └── logging-api.jar
```

Nếu `Application` sử dụng Jackson và logging API, chỉ chạy:

```bash
java -jar application.jar
```

có thể gây lỗi `NoClassDefFoundError` hoặc lỗi nạp lớp vì dependency không có trong runtime classpath.

Có một số cách giải quyết:

1. Khai báo dependency trong manifest `Class-Path`.
2. Chạy ứng dụng bằng script tạo classpath phù hợp.
3. Tạo fat/uber JAR chứa dependency (có cân nhắc resource và license).
4. Đóng gói ứng dụng theo cấu trúc distribution có thư mục `lib/` và script khởi chạy.

Chọn cách nào tùy mục tiêu phân phối, kích thước, khả năng cập nhật thư viện và yêu cầu triển khai.

## 9. Manifest `Class-Path`

Thuộc tính `Class-Path` trong manifest có thể bổ sung các vị trí JAR/thư mục mà ứng dụng cần. Giá trị là danh sách URL phân tách bằng khoảng trắng. Các tham chiếu tương đối được diễn giải tương đối với URL của JAR chứa manifest.

Ví dụ cấu trúc:

```text
distribution/
├── application.jar
└── lib/
    ├── jackson-databind.jar
    └── logging-api.jar
```

Manifest trong `application.jar`:

```text
Manifest-Version: 1.0
Main-Class: com.example.Application
Class-Path: lib/jackson-databind.jar lib/logging-api.jar
```

Khi người dùng chạy `java -jar application.jar` từ distribution này, launcher có thể tìm dependency qua các URL tương đối được khai báo trong `Class-Path`.

Một số điểm quan trọng:

- Các mục được phân tách bằng khoảng trắng, không dùng dấu `:` hoặc `;` như classpath command line.
- Tham chiếu được diễn giải tương đối với vị trí JAR chứa manifest.
- Đây là URL reference, vì vậy tên có ký tự đặc biệt hoặc khoảng trắng phải được biểu diễn theo quy tắc URL phù hợp.
- Không nên ghi đường dẫn tuyệt đối phụ thuộc máy như `C:\Users\...` hoặc `/home/alice/...` vào manifest phát hành.
- `Class-Path` không phải cơ chế quản lý dependency đầy đủ như Maven/Gradle; nó chỉ tham chiếu các vị trí runtime.

Khi cấu hình bằng build tool, nên để plugin tạo thuộc tính này thay vì tự ghép chuỗi phụ thuộc hệ điều hành.

### 9.1. `Class-Path` không phải wildcard

Không nên giả định rằng manifest hỗ trợ cú pháp wildcard như:

```text
Class-Path: lib/*
```

theo cùng cách launcher xử lý `-cp lib/*`. Manifest `Class-Path` dùng URL reference cụ thể. Nếu cần thêm nhiều JAR, hãy liệt kê từng JAR hoặc dùng script khởi chạy xây classpath phù hợp.

### 9.2. Đường dẫn dependency nên giữ tương đối

Với distribution:

```text
app/
├── bin/
│   ├── app
│   └── app.bat
├── lib/
│   ├── application.jar
│   └── dependency-a.jar
└── conf/
```

Script `bin/app` hoặc `bin/app.bat` có thể tính thư mục cài đặt và tạo classpath. Cách này thường linh hoạt hơn việc ghi đường dẫn tuyệt đối vào manifest, đặc biệt khi người dùng cài ứng dụng ở các vị trí khác nhau.

## 10. Tạo executable JAR với Gradle

Với Gradle Java plugin, có thể cấu hình manifest của task `jar` bằng `manifest.attributes`.

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'com.example.Application',
            'Implementation-Title': 'Example Application',
            'Implementation-Version': project.version
        )
    }
}
```

Khi chạy:

```bash
./gradlew jar
```

Gradle tạo JAR trong thư mục build, thường là:

```text
build/libs/<project-name>-1.0.0.jar
```

Kiểm tra manifest:

```bash
jar --list --file build/libs/application-1.0.0.jar
```

Để đọc nội dung manifest, có thể dùng `unzip -p` hoặc mở archive bằng công cụ ZIP. Chạy:

```bash
java -jar build/libs/application-1.0.0.jar
```

Tên file thực tế phụ thuộc `archiveBaseName`, version, classifier và cấu hình archive task.

### 10.1. Gradle Kotlin DSL

Với `build.gradle.kts`:

```kotlin
plugins {
    java
}

group = "com.example"
version = "1.0.0"

tasks.jar {
    manifest {
        attributes(
            mapOf(
                "Main-Class" to "com.example.Application",
                "Implementation-Title" to "Example Application",
                "Implementation-Version" to project.version
            )
        )
    }
}
```

Hai ví dụ Groovy/Kotlin chỉ khác DSL; cả hai cấu hình manifest của archive JAR.

### 10.2. Cấu hình `Class-Path` trong Gradle

Nếu distribution đặt dependency trong thư mục `lib/` cạnh JAR ứng dụng, có thể thêm thuộc tính `Class-Path`:

```groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Main-Class': 'com.example.Application',
            'Class-Path': configurations.runtimeClasspath.files
                .collect { "lib/${it.name}" }
                .join(' ')
        )
    }
}
```

Đoạn trên minh họa cách tạo danh sách tên JAR tương đối. Nó chỉ đúng nếu quá trình phân phối thật sự chép các dependency vào `lib/` với đúng tên file và vị trí tương ứng. Trong build phức tạp, nên dùng application/distribution plugin hoặc cấu hình archive/publication rõ ràng thay vì giả định tên file và đường dẫn.

Không nên ghi `configurations.runtimeClasspath.files` trực tiếp thành đường dẫn tuyệt đối trên máy build. Những đường dẫn đó không có ý nghĩa khi JAR được chuyển sang máy khác.

### 10.3. Application plugin của Gradle

Gradle Application plugin cho phép khai báo lớp chính:

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'com.example.Application'
}
```

Plugin này hỗ trợ:

- Task `run` để chạy ứng dụng trong môi trường phát triển.
- Tạo application distribution có thư mục `bin/` và `lib/`.
- Sinh script khởi chạy cho Unix-like và Windows.
- Đưa main class vào script khởi chạy.

Ví dụ:

```bash
./gradlew run
./gradlew installDist
```

Sau `installDist`, distribution thường nằm trong `build/install/<application-name>/`. Người dùng có thể chạy script trong `bin/`.

`application.mainClass` cấu hình điểm vào cho task `run` và application start scripts. Nếu mục tiêu là tạo một JAR đơn lẻ chạy bằng `java -jar`, vẫn cần bảo đảm manifest của JAR được cấu hình phù hợp và dependency được xử lý. Application plugin không tự biến JAR thông thường thành fat JAR chứa mọi dependency.

## 11. Tạo executable JAR với Maven

Maven JAR Plugin cho phép đặt `Main-Class` trong manifest qua cấu hình `archive/manifest/mainClass`.

Ví dụ `pom.xml`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <version>3.4.2</version>
      <configuration>
        <archive>
          <manifest>
            <mainClass>com.example.Application</mainClass>
          </manifest>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Chạy:

```bash
mvn package
```

Artifact thường được tạo tại:

```text
target/<artifactId>-<version>.jar
```

Kiểm tra manifest bên trong JAR, sau đó chạy:

```bash
java -jar target/application-1.0.0.jar
```

Tên file thực tế phụ thuộc `artifactId`, version và cấu hình final name của Maven.

### 11.1. Thêm thuộc tính manifest khác trong Maven

Có thể cấu hình các thuộc tính bổ sung:

```xml
<archive>
  <manifest>
    <mainClass>com.example.Application</mainClass>
  </manifest>
  <manifestEntries>
    <Implementation-Title>Example Application</Implementation-Title>
    <Implementation-Version>${project.version}</Implementation-Version>
    <Implementation-Vendor>Example Team</Implementation-Vendor>
  </manifestEntries>
</archive>
```

`manifestEntries` cho phép thêm các entry tùy chỉnh. Không nên đưa thông tin bí mật, token hoặc mật khẩu vào manifest vì manifest nằm trong artifact và người nhận có thể đọc được.

## 12. Maven Assembly và executable archive có dependency

Maven JAR Plugin tạo JAR thông thường từ output của project. Nếu ứng dụng cần dependency bên ngoài, có thể dùng một số cách đóng gói:

- Manifest `Class-Path` trỏ tới thư mục `lib/` trong distribution.
- Maven Assembly Plugin tạo ZIP/TAR chứa ứng dụng và thư viện.
- Maven Shade Plugin tạo uber/fat JAR bằng cách hợp nhất nội dung dependency vào một archive.

### 12.1. Dùng manifest Class-Path với Maven

Maven JAR Plugin có thể thêm dependency classpath vào manifest thông qua cấu hình `addClasspath` và `classpathPrefix`:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-jar-plugin</artifactId>
  <version>3.4.2</version>
  <configuration>
    <archive>
      <manifest>
        <mainClass>com.example.Application</mainClass>
        <addClasspath>true</addClasspath>
        <classpathPrefix>lib/</classpathPrefix>
      </manifest>
    </archive>
  </configuration>
</plugin>
```

Plugin tạo thuộc tính `Class-Path` dựa trên dependency classpath theo cấu hình. Nhưng chỉ tạo manifest chưa đủ: distribution phải chép các dependency tới đúng thư mục `lib/` và giữ tên tương ứng.

Vì vậy, trong dự án thật thường kết hợp với Assembly/Distribution plugin để tạo cấu trúc:

```text
application-distribution/
├── application.jar
└── lib/
    ├── dependency-a.jar
    └── dependency-b.jar
```

### 12.2. Dùng fat/uber JAR

Fat JAR (còn gọi là uber JAR) chứa class và resource của ứng dụng cùng dependency bên trong một archive. Khi đó, ứng dụng thường chỉ cần một file JAR để chạy, miễn là archive được đóng gói đúng và không cần native library/tài nguyên ngoài khác.

Maven Shade Plugin là một công cụ phổ biến để tạo uber JAR. Cấu hình thường bao gồm:

- Chọn artifact đầu vào.
- Hợp nhất nội dung dependency.
- Đặt `Main-Class` trong manifest qua manifest transformer.
- Xử lý resource trùng, service descriptor và chữ ký JAR.

Ví dụ cấu hình rút gọn:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-shade-plugin</artifactId>
  <version>3.6.0</version>
  <executions>
    <execution>
      <phase>package</phase>
      <goals>
        <goal>shade</goal>
      </goals>
      <configuration>
        <transformers>
          <transformer implementation="org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
            <mainClass>com.example.Application</mainClass>
          </transformer>
        </transformers>
      </configuration>
    </execution>
  </executions>
</plugin>
```

Version plugin trong ví dụ là một version minh họa; dự án cần đồng bộ version theo chính sách build. Shade có nhiều tùy chọn khác và cần được cấu hình cẩn thận khi dependency có resource cùng tên.

### 12.3. Rủi ro khi tạo fat JAR

Không phải cứ giải nén mọi dependency rồi gộp file vào một JAR là an toàn:

- Nhiều thư viện có cùng resource path.
- `META-INF/services` có thể cần được merge thay vì ghi đè.
- File chữ ký trong `META-INF` có thể không còn hợp lệ sau khi nội dung archive thay đổi.
- Package/class trùng nhau có thể gây che khuất hoặc lỗi liên kết.
- License và notice của dependency cần được giữ theo yêu cầu phân phối.
- Native library hoặc file cần nằm ngoài archive có thể không hoạt động như dự kiến.

Vì vậy, cần kiểm thử artifact sau shading, đặc biệt với service loading, logging provider, JDBC driver và các framework dùng metadata trong resource.

## 13. Manifest và Java module system (JPMS)

Một JAR có thể là JAR trên classpath hoặc modular JAR có `module-info.class`. Hai cách khởi chạy cần được phân biệt.

Với ứng dụng classpath truyền thống:

```bash
java -jar application.jar
```

launcher sử dụng `Main-Class` trong manifest.

Với ứng dụng modular, launcher có thể dùng module path và chỉ rõ module/điểm vào:

```bash
java --module-path mods -m com.example.app/com.example.Application
```

`-m`/`--module` chỉ định module và có thể kèm tên lớp chính sau dấu `/`. Module descriptor khai báo module name, `requires`, `exports` và các thông tin liên quan.

JAR modular có thể chứa metadata main class của module khi được tạo/cấu hình phù hợp. `Main-Class` trong manifest và thông tin điểm vào module có liên quan nhưng không nên nhầm lẫn với việc khai báo `module-info.java`. Nếu phát hành modular application, hãy kiểm tra cách đóng gói và lệnh launch theo JPMS, không chỉ kiểm tra `Main-Class`.

## 14. Kiểm tra manifest sau khi đóng gói

Không nên chỉ nhìn cấu hình build script rồi mặc định manifest đã đúng. Hãy kiểm tra archive được tạo.

### 14.1. Liệt kê nội dung JAR

```bash
jar tf application.jar
```

Đảm bảo có:

```text
META-INF/MANIFEST.MF
com/example/Application.class
```

### 14.2. Đọc manifest

Có thể dùng:

```bash
unzip -p application.jar META-INF/MANIFEST.MF
```

Hoặc giải nén archive và mở file `META-INF/MANIFEST.MF` bằng trình soạn thảo văn bản.

Kiểm tra:

- Có `Main-Class` hay không.
- Tên lớp có đúng package và chữ hoa/thường không.
- Có bị ghi đè bởi cấu hình plugin khác không.
- `Class-Path` có trỏ đúng vị trí dependency được phân phối không.
- Không có thuộc tính chứa thông tin bí mật.

### 14.3. Kiểm tra lớp chính

```bash
javap -classpath application.jar -public com.example.Application
```

Lệnh này giúp xem class có tồn tại và phương thức public nào được khai báo. Để xác nhận `main` có chữ ký phù hợp, xem output và kiểm tra dạng `public static void main(java.lang.String[])`.

### 14.4. Chạy thử artifact

```bash
java -jar application.jar
```

Kiểm tra exit code, log khởi động và hành vi cơ bản. Nếu ứng dụng cần biến môi trường hoặc cấu hình runtime, cung cấp môi trường kiểm thử tương ứng.

## 15. Các lỗi thường gặp khi chạy executable JAR

| Thông báo/hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | Manifest không có `Main-Class` | Cấu hình manifest trong Gradle/Maven hoặc tạo lại bằng `jar --main-class` |
| `Could not find or load main class` | Tên lớp sai, class không nằm trong JAR/classpath hoặc package không khớp | Kiểm tra `Main-Class`, `jar tf` và tên binary class |
| `Main method not found` hoặc lỗi điểm vào | Lớp tồn tại nhưng không có phương thức main phù hợp với launcher | Kiểm tra chữ ký `public static void main(String[] args)` và JDK đang dùng |
| `NoClassDefFoundError` | Thiếu dependency runtime | Thêm dependency qua manifest Class-Path, script distribution hoặc fat JAR |
| `ClassNotFoundException` | Class loader không tìm thấy lớp được yêu cầu lúc chạy | Kiểm tra runtime classpath và dependency |
| Chạy được trong IDE nhưng không chạy bằng `java -jar` | IDE tự tạo classpath đầy đủ, còn JAR chỉ chứa output project | Đóng gói dependency hoặc tạo distribution có `lib/` |
| Manifest có `Class-Path` nhưng vẫn thiếu JAR | Đường dẫn tương đối không khớp vị trí archive hoặc dependency chưa được copy | Kiểm tra layout distribution và URL trong manifest |
| JAR chạy sai version thư viện | Runtime classpath có JAR cũ hoặc trùng class | Kiểm tra class origin và dependency graph |
| Service provider biến mất sau khi tạo fat JAR | `META-INF/services` bị ghi đè | Dùng transformer/merge strategy phù hợp và kiểm thử ServiceLoader |
| `Invalid signature file digest` hoặc lỗi chữ ký | File chữ ký cũ còn trong archive sau khi shading | Xử lý chữ ký theo hướng dẫn plugin và ký lại artifact cuối nếu cần |
| Ứng dụng modular báo lỗi module | Nhầm classpath với module path hoặc module descriptor không hợp lệ | Kiểm tra `module-info`, module path và lệnh `-m` |

## 16. Quy trình tạo và phát hành executable JAR

Một quy trình đáng tin cậy có thể gồm:

1. **Xác định điểm vào:** chọn lớp chính và bảo đảm có phương thức main phù hợp.
2. **Biên dịch:** tạo class file đúng package và phiên bản bytecode mục tiêu.
3. **Cấu hình manifest:** khai báo `Main-Class` cùng metadata cần thiết.
4. **Quyết định dependency packaging:** JAR thường với manifest Class-Path, application distribution hay fat JAR.
5. **Đóng gói:** dùng Gradle/Maven hoặc JDK `jar` để tạo artifact.
6. **Kiểm tra archive:** xác nhận manifest, class entry, resource và dependency layout.
7. **Chạy smoke test:** chạy artifact bằng đúng lệnh mà người dùng sẽ sử dụng.
8. **Kiểm tra tính di động:** chạy trên môi trường tương tự máy đích, không dựa vào đường dẫn tuyệt đối của máy build.
9. **Phát hành:** publish artifact và tài liệu lệnh khởi chạy, cấu hình runtime và yêu cầu JDK.

## 17. Ví dụ hoàn chỉnh tối giản

Giả sử mã nguồn:

```text
src/main/java/com/example/Application.java
```

Nội dung:

```java
package com.example;

public class Application {
    public static void main(String[] args) {
        String environment = args.length == 0 ? "local" : args[0];
        System.out.println("Starting application in " + environment);
    }
}
```

Với Gradle:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

tasks.named('jar') {
    manifest {
        attributes('Main-Class': 'com.example.Application')
    }
}
```

Build và chạy:

```bash
./gradlew clean jar
java -jar build/libs/<project-name>-1.0.0.jar staging
```

Với Maven, thêm cấu hình `maven-jar-plugin` có `mainClass` như phần trên, rồi:

```bash
mvn clean package
java -jar target/<artifactId>-1.0.0.jar staging
```

Kết quả ví dụ:

```text
Starting application in staging
```

Ví dụ tối giản này không có dependency bên ngoài. Nếu thêm thư viện, cần thiết kế runtime classpath hoặc distribution tương ứng.

## 18. Nguyên tắc cần ghi nhớ

- Manifest nằm trong JAR tại `META-INF/MANIFEST.MF`.
- `Main-Class` là binary name của lớp điểm vào, không phải đường dẫn `.class`.
- Lớp chính cần có phương thức main phù hợp với cách launcher được sử dụng.
- `java -jar app.jar` đọc điểm vào từ manifest; `java -cp ... MainClass` lấy điểm vào từ command line.
- `Main-Class` không tự đóng gói dependency.
- `Class-Path` trong manifest dùng URL reference phân tách bằng khoảng trắng và được diễn giải tương đối với JAR chứa manifest.
- Gradle có thể cấu hình manifest của `jar` task; Maven JAR Plugin có thể cấu hình `mainClass`.
- Gradle Application plugin tạo task `run` và application distribution/start scripts; không nên mặc định JAR đơn lẻ đã chứa toàn bộ dependency.
- Fat JAR cần xử lý resource trùng, service descriptor, chữ ký và license.
- Luôn kiểm tra manifest và chạy thử artifact đã đóng gói, không chỉ chạy ứng dụng từ IDE.

Manifest là nơi mô tả metadata cần thiết để launcher và công cụ khác hiểu JAR. Khi khai báo `Main-Class` đúng, người dùng có thể khởi chạy JAR theo một lệnh thống nhất. Để ứng dụng chạy được trên máy khác, build còn phải bảo đảm dependency, resource, cấu hình và môi trường runtime được phân phối đúng cách.
