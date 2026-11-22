# Kiểm tra nội dung JAR bằng `jar tf` và công cụ giải nén

Khi đóng gói một ứng dụng Spring Boot, Maven hoặc Gradle có thể báo `BUILD SUCCESS` trong khi file JAR cuối cùng lại thiếu class, tài nguyên, dependency runtime hoặc điểm khởi động chính xác. Vì vậy, **kiểm tra JAR sau build** là một bước độc lập với biên dịch và chạy test. Công cụ `jar` của JDK cùng các tiện ích ZIP như `unzip`, `zipinfo` và 7-Zip cho phép xem trực tiếp những gì đã được đưa vào artifact, không phải chỉ suy đoán từ cấu trúc `src` hoặc cấu hình build.

Bài này hướng dẫn từ `jar tf`, `jar tvf`, `jar xf` đến đọc `META-INF/MANIFEST.MF`, kiểm tra **Spring Boot executable JAR**, class/resource trong `BOOT-INF/classes`, dependency JAR lồng trong `BOOT-INF/lib`, các công cụ giải nén trên Linux/macOS/Windows và cách kiểm tra tự động trong CI. Có ví dụ Java 17 + Spring Boot 3.3.13 minh họa chạy được. Phiên bản này chỉ là mốc nhất quán cho bài học, không được hiểu là phiên bản mới nhất; hãy căn cứ vào công cụ và release của project thực tế.

## 1. JAR là gì và vì sao có thể mở bằng công cụ ZIP?

**JAR (Java ARchive)** là định dạng archive xây trên ZIP. Bên trong có thể chứa:
- Bytecode `.class` và các tệp resource (properties, JSON, template, ảnh, XML...).
- `META-INF/MANIFEST.MF`, metadata mô tả archive và, khi có, cách khởi chạy.
- Metadata Java như `META-INF/services/**` hoặc multi-release entries `META-INF/versions/**`.
- Với Spring Boot executable JAR: **Boot launcher**, class/resource ứng dụng và **các thư viện runtime dưới dạng nested JAR**.

Chức năng từng công cụ:

| Công cụ | Làm được | Không chứng minh được |
| --- | --- | --- |
| `jar tf file.jar` | Liệt kê tên và đường dẫn entry | Nội dung của entry, tính tương thích runtime |
| `jar tvf file.jar` | Liệt kê có thêm kích thước, timestamp | Tính xác thực, dependency có tương thích hay không |
| `jar xf file.jar [entry]` | Giải nén toàn bộ hoặc entry được chọn | Ứng dụng chạy thành công |
| `unzip -l file.jar` | Liệt kê entry và thông số ZIP | Main class đúng hay sai |
| `unzip -p file.jar entry` | In **nội dung** một entry ra stdout | Tính an toàn của code trong archive |
| `unzip -t file.jar` | Kiểm tra khả năng đọc/CRC của archive | Chữ ký mật mã/nguồn phát hành |
| `7z l file.jar` | Duyệt archive bằng 7-Zip khi đã cài | JDK và Spring Boot runtime đã đúng |

**`jar tf` không giải nén**; `jar xf` mới tạo file trên đĩa. `jar` thuộc **JDK**, không có gì bảo đảm mọi môi trường chỉ cài Java runtime tối giản đều có lệnh này. Thử:

```bash
java -version
jar --version
```

JDK 17 cũng hỗ trợ cú pháp dài:

```bash
jar --list --file path/to/application.jar
jar --extract --file path/to/application.jar META-INF/MANIFEST.MF
```

Ở cú pháp ngắn, `t` = table/list, `f` = file, `x` = extract, `v` = verbose. Đừng nhầm `jar tf` với `java -jar`: một lệnh **đọc archive**, lệnh còn lại **thực thi chương trình trong archive**.

## 2. Phân biệt các loại JAR trước khi kiểm tra

Không phải file `.jar` nào cũng có cùng layout hoặc chạy được độc lập.

| Loại | Đường dẫn class thường thấy | Dependency runtime | `java -jar` |
| --- | --- | --- | --- |
| Library JAR thông thường | `com/example/Library.class` ở gốc | Bên ngoài JAR | Không bắt buộc |
| Plain application JAR | `com/example/App.class` ở gốc | Thường nằm ngoài và cần classpath đúng | Chỉ nếu có entry point và classpath phù hợp |
| Spring Boot executable JAR | `BOOT-INF/classes/com/example/App.class` | Các nested JAR trong `BOOT-INF/lib` | Thường chạy được khi build đúng |
| Shaded/uber JAR | Class của app và thư viện được gộp ở gốc theo rules riêng | Nhiều dependency được bung/merge | Phụ thuộc manifest và cấu hình shade |
| Spring Boot executable WAR | `WEB-INF/classes` | `WEB-INF/lib`, có thể thêm `WEB-INF/lib-provided` | Có thể chạy hoặc deploy vào servlet container nếu cấu hình đúng |

**Sai lầm phổ biến:** mở một plain JAR rồi kết luận “Spring Boot bị lỗi vì không thấy `BOOT-INF/classes`”. Trước tiên phải biết dự án dự kiến tạo loại artifact nào. Với Gradle Spring Boot plugin, `bootJar` tạo executable JAR, còn task `jar` thường tạo `*-plain.jar` nếu được bật. Với Maven và `spring-boot-maven-plugin`, goal `repackage` thường tái đóng gói JAR gốc, và có thể có file `*.jar.original`.

Với Boot executable JAR, không chạy ứng dụng bằng cách đoán `java -cp app.jar com.example.App`: class ứng dụng nằm dưới `BOOT-INF/classes` và dependency nằm trong nested JAR; classpath thông thường không tự giải Boot layout. Cách chạy chuẩn là `java -jar app.jar` thông qua Boot launcher.

## 3. Tạo artifact trước, chọn đúng file sẽ kiểm tra

### 3.1. Gradle

Trong project có Gradle Wrapper:

```bash
./gradlew clean bootJar
```

Sau build, mở `build/libs/` và chọn executable JAR thực tế. Nếu đã thay `archiveFileName`, `archiveClassifier` hoặc là project nhiều module, đường dẫn có thể khác.

### 3.2. Maven

Trong project có Maven Wrapper:

```bash
./mvnw clean package
```

Khi dùng Spring Boot starter parent cùng `spring-boot-maven-plugin`, phase `package` thường gọi `repackage` và tạo executable JAR trong `target/`. Nếu chỉ import Spring Boot BOM mà không kế thừa parent, việc quản lý version dependency **không tự động gắn goal `repackage` vào lifecycle**; phải cấu hình plugin/execution riêng.

Trong Windows PowerShell, dùng `.\gradlew.bat` hoặc `.\mvnw.cmd`. Nếu không có Wrapper, dùng bản `gradle` hoặc `mvn` cài sẵn khi tương thích với dự án.

**Đừng kiểm tra file đã build từ nhiều giờ trước** hoặc JAR khác classifier với JAR CI deploy. Nên ghi rõ đường dẫn artifact trong pipeline và chạy kiểm tra ngay sau build. Các ví dụ bên dưới dùng hai đường dẫn minh họa:
- Gradle: `build/libs/jar-inspect-demo-1.0.0.jar`.
- Maven: `target/jar-inspect-demo-1.0.0.jar`.

Tên này sẽ khớp nếu tạo dự án ví dụ ở mục 5.

## 4. Liệt kê nội dung bằng `jar tf`

### 4.1. Liệt kê toàn bộ entry

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar
```

Một đoạn danh sách của Spring Boot 3.3 executable JAR thường có hình thức:

```text
META-INF/
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/
BOOT-INF/classes/
BOOT-INF/classes/com/example/inspect/JarInspectApplication.class
BOOT-INF/classes/demo/marker.txt
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
```

**Đây là trích đoạn minh họa, không phải toàn bộ output thực tế.** Các entry index có thể vắng tùy cấu hình, và danh sách `BOOT-INF/lib` còn nhiều thư viện theo đồ thị dependency. Lấy tên/phiên bản thật bằng chính lệnh `jar tf` trên artifact của bạn.

Cấu trúc quan trọng:

```text
executable.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...  # Boot loader
└── BOOT-INF/
    ├── classes/                         # class/resource ứng dụng
    ├── lib/                             # dependency JAR lồng nhau
    ├── classpath.idx                    # tùy có
    └── layers.idx                       # tùy có
```

### 4.2. Chỉ tìm phần cần xem

Linux/macOS với `grep`:

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep '^BOOT-INF/classes/'
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep '^BOOT-INF/lib/'
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep 'MANIFEST.MF'
```

Windows PowerShell:

```powershell
$jar = '.\build\libs\jar-inspect-demo-1.0.0.jar'
jar tf $jar | Select-String '^BOOT-INF/classes/'
jar tf $jar | Select-String '^BOOT-INF/lib/'
jar tf $jar | Select-String 'MANIFEST.MF'
```

Những bộ lọc này **tìm trong tên entry**, không tìm trong nội dung. Nếu không khớp, kiểm tra bạn đã mở đúng executable JAR hay chưa, resource đã được copy chưa và prefix path có tương ứng layout không. Tên entry ZIP thường dùng dấu `/` kể cả khi host là Windows.

### 4.3. `jar tvf` có gì khác?

```bash
jar tvf build/libs/jar-inspect-demo-1.0.0.jar
```

Ký tự `v` thêm metadata như kích thước và timestamp. Không suy luận file có “mới” hay “cũ” hoàn toàn từ timestamp entry: reproducible build có thể chuẩn hóa timestamp. `jar tvf` cũng **không** in nội dung của `META-INF/MANIFEST.MF`.

## 5. Ví dụ Spring Boot Java 17 để kiểm chứng nội dung thật

Dự án mẫu sẽ có một main class Spring Boot và một file resource mang chuỗi nhận diện. Ta dùng **cùng mã Java** cho Gradle hoặc Maven, chọn một build tool để thử.

Cấu trúc:

```text
jar-inspect-demo/
├── settings.gradle     (phương án Gradle)
├── build.gradle        (phương án Gradle)
├── pom.xml             (phương án Maven)
└── src/main/
    ├── java/com/example/inspect/JarInspectApplication.java
    └── resources/demo/marker.txt
```

### 5.1. Mã Java

`src/main/java/com/example/inspect/JarInspectApplication.java`:

```java
package com.example.inspect;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class JarInspectApplication {

    public static void main(String[] args) throws IOException {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(JarInspectApplication.class, args)) {
            try (InputStream in = JarInspectApplication.class
                    .getClassLoader()
                    .getResourceAsStream("demo/marker.txt")) {
                if (in == null) {
                    throw new IOException("Missing classpath resource: demo/marker.txt");
                }
                String value = new String(in.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("archive-resource=" + value.strip());
            }
        }
    }
}
```

Trong `src/main/resources/demo/marker.txt`, ghi **một dòng**:

```text
archive-inspection-ok
```

`getResourceAsStream("demo/marker.txt")` đọc resource từ **classpath** chứ không phụ thuộc đường dẫn source filesystem. Code dùng Java 17 và đóng `ApplicationContext` để bài demo kết thúc sau khi in kết quả; không áp dụng kiểu tự đóng context ngay sau startup cho web server phục vụ lâu dài.

### 5.2. Build với Gradle Groovy DSL

`settings.gradle`:

```groovy
rootProject.name = 'jar-inspect-demo'
```

`build.gradle` đầy đủ:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.inspect.JarInspectApplication'
}
```

Task `bootJar` sẽ đóng gói class, resource và runtime dependencies vào executable JAR. `mainClass` xác định entry point ngay cả khi project sau này có thêm lớp `main` khác.

```bash
./gradlew clean bootJar
jar tf build/libs/jar-inspect-demo-1.0.0.jar
java -jar build/libs/jar-inspect-demo-1.0.0.jar
```

Dòng do chương trình mẫu in ra:

```text
archive-resource=archive-inspection-ok
```

Ngoài dòng đó còn có thể có log Spring Boot tùy môi trường. Nếu file resource không có trên classpath, chương trình ném `IOException` thay vì in kết quả kỳ vọng.

### 5.3. Build với Maven

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>jar-inspect-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot parent cấu hình `repackage` cho plugin, vì thế `./mvnw clean package` tạo executable JAR. Sau đó:

```bash
./mvnw clean package
jar tf target/jar-inspect-demo-1.0.0.jar
java -jar target/jar-inspect-demo-1.0.0.jar
```

Dòng do chương trình in ra cũng là `archive-resource=archive-inspection-ok`. Lưu ý `target/jar-inspect-demo-1.0.0.jar.original` (nếu có) là file trước repackage, **không** phải executable artifact đang muốn kiểm tra.

## 6. Kiểm tra `META-INF/MANIFEST.MF`

Manifest là file **text nằm trong archive**. Dùng `jar tf` chỉ thấy tên entry. Muốn xem giá trị `Main-Class` hoặc `Start-Class`, phải **đọc nội dung**.

Khi có `unzip`:

```bash
unzip -p build/libs/jar-inspect-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Các trường tiêu biểu trong Spring Boot 3.3 executable JAR:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.inspect.JarInspectApplication
```

- **`Main-Class`**: Boot loader launcher nhận `java -jar`, thiết lập classpath cho nested JAR.
- **`Start-Class`**: lớp `main` của ứng dụng thật.
- Các field khác (`Spring-Boot-Version`, `Spring-Boot-Classes`...) có thể xuất hiện; thứ tự và nội dung phụ thuộc plugin/version.
- Spring Boot cũ hơn có thể dùng launcher package khác; **không hardcode tên `JarLauncher` của Boot 3.3 để đánh giá mọi phiên bản**.

Nếu `Start-Class` sai, kiểm tra `springBoot.mainClass` / `bootJar.mainClass` ở Gradle hoặc cấu hình `mainClass` của Spring Boot Maven plugin. Nếu `Main-Class` là class ứng dụng hoặc thiếu manifest entry point trong khi bạn mong đợi Boot JAR, có thể đã kiểm tra plain JAR hoặc plugin chưa chạy.

**Manifest có thể chứa continuation line** cho giá trị dài (dòng tiếp nối bắt đầu bằng dấu cách). Khi phân tích manifest tự động, cần tuân thủ quy tắc JAR manifest thay vì cắt từng dòng độc lập một cách ngây thơ.

## 7. `jar xf` và `unzip -p`: xem nội dung một entry

### 7.1. Giải nén bằng `jar xf`

```bash
jar xf build/libs/jar-inspect-demo-1.0.0.jar
```

Nếu không chỉ định entry, lệnh giải nén **toàn bộ** archive vào **thư mục hiện tại**. Điều này có thể tạo hàng nghìn file; không dùng trong thư mục source hoặc nơi chứa dữ liệu cần bảo vệ.

Phương án an toàn hơn:

```bash
mkdir -p jar-inspection
cd jar-inspection
jar xf ../build/libs/jar-inspect-demo-1.0.0.jar META-INF/MANIFEST.MF
jar xf ../build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/classes/demo/marker.txt
cat META-INF/MANIFEST.MF
cat BOOT-INF/classes/demo/marker.txt
```

Chỉ trích xuất hai file cần xem. Với Maven thì đổi `../build/libs/...` thành `../target/...`; thư mục `jar-inspection` được tạo ở gốc project. Trên Windows, có thể tạo thư mục bằng `New-Item -ItemType Directory` và dùng `Get-Content` để đọc file text.

### 7.2. Không cần ghi file nếu có `unzip -p`

```bash
unzip -p build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/classes/demo/marker.txt
```

Nội dung kỳ vọng:

```text
archive-inspection-ok
```

`unzip -p` xuất nội dung ra stdout; rất tiện cho manifest, properties hoặc text. **Đừng dùng pipeline text để trích xuất thư viện `.jar` hoặc file ảnh nhị phân trong mọi loại shell**: một số phiên bản PowerShell cũ có thể biến đổi byte/encoding khi redirect. Với binary, ưu tiên `jar xf` hoặc giải nén bằng công cụ chuyên dụng.

### 7.3. Các lựa chọn khác

```bash
unzip -l build/libs/jar-inspect-demo-1.0.0.jar
zipinfo -1 build/libs/jar-inspect-demo-1.0.0.jar
unzip -t build/libs/jar-inspect-demo-1.0.0.jar
```

`zipinfo` không phải công cụ có sẵn trên mọi hệ, và `unzip -t` chủ yếu kiểm tra tính đọc được/CRC của ZIP, **không kiểm tra tương thích JVM hay nhà phát hành có đáng tin hay không**. Khi đã cài 7-Zip, `7z l file.jar` cũng liệt kê entry; GUI 7-Zip cho phép duyệt/giải nén dưới dạng archive ZIP.

### 7.4. PowerShell không cần `unzip`

```powershell
$jar = '.\build\libs\jar-inspect-demo-1.0.0.jar'
jar tf $jar | Select-String 'BOOT-INF/classes/demo/marker.txt'
New-Item -ItemType Directory -Path .\jar-inspection -Force | Out-Null
Push-Location .\jar-inspection
try {
    jar xf ..\build\libs\jar-inspect-demo-1.0.0.jar META-INF/MANIFEST.MF
    jar xf ..\build\libs\jar-inspect-demo-1.0.0.jar BOOT-INF/classes/demo/marker.txt
    Get-Content .\META-INF\MANIFEST.MF
    Get-Content .\BOOT-INF\classes\demo\marker.txt
} finally {
    Pop-Location
}
```

Đây là lệnh **PowerShell với JDK đã cài**, không yêu cầu lệnh Unix. `jar xf` phải chạy trong thư mục kiểm tra được kiểm soát, vì nó sẽ tạo các thư mục con từ đường dẫn entry. Không trích xuất archive không đáng tin bằng quyền Administrator.

## 8. Kiểm tra class/resource của ứng dụng

Trong Spring Boot executable JAR, file `src/main/java/com/example/inspect/JarInspectApplication.java` trở thành class entry:

```text
BOOT-INF/classes/com/example/inspect/JarInspectApplication.class
```

Còn resource nguồn:

```text
src/main/resources/demo/marker.txt
```

trở thành:

```text
BOOT-INF/classes/demo/marker.txt
```

Bạn có thể kiểm tra từng entry:

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep 'JarInspectApplication.class'
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep 'BOOT-INF/classes/demo/marker.txt'
```

**Phân biệt các tầng đường dẫn:**

| Nơi | Đường dẫn file |
| --- | --- |
| Source Java | `src/main/java/com/example/inspect/JarInspectApplication.java` |
| Source resource | `src/main/resources/demo/marker.txt` |
| Gradle resource output | `build/resources/main/demo/marker.txt` |
| Maven resource output | `target/classes/demo/marker.txt` |
| Bên trong Boot executable JAR | `BOOT-INF/classes/demo/marker.txt` |
| Path dùng trong `ClassLoader.getResourceAsStream` | `demo/marker.txt` |

Nếu file tồn tại ở `src/main/resources` nhưng thiếu trong JAR, xem `processResources` (Gradle), `process-resources` (Maven), các quy tắc `include/exclude` và task archive. Nếu file nằm trong JAR nhưng classloader không đọc được, kiểm tra path gọi runtime: thường phải truyền `demo/marker.txt`, **không** truyền `BOOT-INF/classes/demo/marker.txt`.

**`jar tf` không chứng minh Java class có phương thức `main` hợp lệ.** Nó chỉ biết tên entry. Để xác nhận sâu hơn có thể dùng `javap` trên bytecode đã trích xuất, nhưng với Spring Boot cách hiệu quả nhất là vừa xem manifest vừa chạy `java -jar` và quan sát hành vi.

## 9. Nested JAR: vì sao không thấy class từ thư viện khi `jar tf`?

Spring Boot đóng gói dependency runtime dưới dạng những **file JAR nằm trong một JAR khác**:

```text
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-context-<version>.jar
BOOT-INF/lib/spring-core-<version>.jar
...
```

`<version>` ở đây là mô tả minh họa, không phải chuỗi file thật. Lệnh `jar tf outer.jar` chỉ thấy mỗi nested `*.jar` như **một entry**, không liệt kê tiếp `.class` bên trong nó.

### 9.1. Liệt kê nested JAR

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | grep '^BOOT-INF/lib/.*[.]jar$'
```

Trên PowerShell:

```powershell
jar tf .\build\libs\jar-inspect-demo-1.0.0.jar |
    Select-String '^BOOT-INF/lib/.*[.]jar$'
```

### 9.2. Trích xuất và kiểm tra một thư viện cụ thể

Sau khi lấy **tên đúng từ danh sách thật**, tạo thư mục riêng và dùng `jar xf`. Ví dụ với `spring-boot-3.3.13.jar`:

```bash
mkdir -p jar-inspection
cd jar-inspection
jar xf ../build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/lib/spring-boot-3.3.13.jar
jar tf BOOT-INF/lib/spring-boot-3.3.13.jar
```

Lệnh cuối mới liệt kê class/resource **bên trong dependency JAR**. Nếu cần tìm `org/springframework/boot/SpringApplication.class`, bạn tìm trên nested `spring-boot-3.3.13.jar` chứ không kỳ vọng thấy class này trong `BOOT-INF/classes` của ứng dụng.

Hai thư viện khác nhau có thể cùng chứa `META-INF/services/...` mà không tạo ra duplicate **entry name** trong outer JAR; đây là những archive riêng được Boot loader đưa vào classpath.

### 9.3. So sánh với dependency graph

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Maven:

```bash
./mvnw dependency:tree
```

Dependency graph cho biết **thư viện/phiên bản nào đã resolve và vì sao**; `jar tf` xác nhận **artifact nào thật sự được đóng gói**. Một dependency có thể không xuất hiện trong production JAR do test/provided scope, exclusions, classifier hoặc custom packaging. Đừng đưa `junit-jupiter-engine`, `mockito-core` vào `BOOT-INF/lib` production chỉ để “đủ thư viện”: test dependency thường không được đóng gói.

## 10. Kiểm tra `classpath.idx` và `layers.idx`

Một số Spring Boot executable JAR có:

- `BOOT-INF/classpath.idx`: danh sách/thứ tự nested JAR được thêm vào runtime classpath khi chạy executable JAR bằng `java -jar`.
- `BOOT-INF/layers.idx`: mô tả cách chia thành layer phục vụ xây container image/cache.

Xem bằng `jar tf`, rồi đọc khi chúng **thật sự tồn tại**:

```bash
unzip -p build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/classpath.idx
unzip -p build/libs/jar-inspect-demo-1.0.0.jar BOOT-INF/layers.idx
```

Ví dụ dạng `classpath.idx`:

```text
- "BOOT-INF/lib/spring-boot-3.3.13.jar"
- "BOOT-INF/lib/spring-context-6.1.20.jar"
```

Tên/version ở đây chỉ là minh họa. Lưu ý `jar tf` trả về **thứ tự entry trong archive**, không nhất thiết là thứ tự classpath runtime; nếu có `classpath.idx`, hãy đọc quy ước tương ứng phiên bản Boot.

Ví dụ rút gọn về layer:

```text
- "dependencies":
  - "BOOT-INF/lib/"
- "application":
  - "BOOT-INF/classes/"
```

Không dùng `layers.idx` để quyết định main class hoặc kết luận thiếu resource. **Thiếu index không mặc nhiên là lỗi**: tùy phiên bản, plugin và cấu hình, index có thể được tạo hoặc không. Chức năng trọng tâm của JAR vẫn phải được kiểm tra qua manifest, lớp/resource, dependency và việc chạy thực tế.

## 11. Kiểm tra duplicate entries và phân biệt trùng classpath

Một ZIP/JAR có thể chứa nhiều entry cùng tên nếu có quy trình đóng gói đặc biệt hoặc duplicate strategy không chặn. Phát hiện entry name lặp lại:

```bash
jar tf build/libs/jar-inspect-demo-1.0.0.jar | sort | uniq -d
```

PowerShell:

```powershell
jar tf .\build\libs\jar-inspect-demo-1.0.0.jar |
    Group-Object |
    Where-Object { $_.Count -gt 1 } |
    Select-Object Name, Count
```

Nếu không có output, danh sách **outer archive** không có entry tên lặp lại theo phép so sánh này. Nhưng điều đó **không** loại trừ resource/class cùng tên nằm trong **hai nested dependency JAR khác nhau**. Cũng có thể ứng dụng có cả main resource lẫn test resource trùng đường dẫn nguồn; `src/test/resources` thường không vào production JAR, nhưng trên test classpath có thể xuất hiện.

Nếu Gradle ném `DuplicateFileCopyingException`, cần xem `processResources`, `bootJar`, `DuplicatesStrategy` và các source root. Trong Maven, xem `<resources>`, `includes/excludes`, `targetPath` và plugin packaging. **Không chỉnh sửa trực tiếp artifact đã đóng gói để giấu duplicate**; hãy sửa rule từ source/build rồi build lại và kiểm tra lại.

## 12. Kiểm tra bằng Java 17 không cần công cụ ZIP bên ngoài

Ngoài `jar tf`, JDK có API `java.util.jar.JarFile` để kiểm tra entry theo tên. Ví dụ chương trình **Java 17 độc lập**, không cần Spring Boot dependency:

Tạo file `JarEntryCheck.java` ở một thư mục riêng:

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.jar.JarFile;

public class JarEntryCheck {

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Expected path to a JAR file");
        }

        try (JarFile jar = new JarFile(Path.of(args[0]).toFile())) {
            System.out.println("manifest=" +
                    (jar.getJarEntry("META-INF/MANIFEST.MF") != null));
            System.out.println("app-class=" +
                    (jar.getJarEntry(
                            "BOOT-INF/classes/com/example/inspect/JarInspectApplication.class"
                    ) != null));
            System.out.println("resource=" +
                    (jar.getJarEntry("BOOT-INF/classes/demo/marker.txt") != null));
        }
    }
}
```

Biên dịch và chạy với JDK 17, từ thư mục chứa `JarEntryCheck.java`:

```bash
javac JarEntryCheck.java
java JarEntryCheck build/libs/jar-inspect-demo-1.0.0.jar
```

**Chỉnh đường dẫn** trong lệnh nếu đang đứng ở thư mục khác, hoặc dùng đường dẫn tuyệt đối tới artifact. Với JAR mẫu đúng cấu trúc ở mục 5, stdout chính xác của **chương trình kiểm tra**:

```text
manifest=true
app-class=true
resource=true
```

Đây là một kiểm tra **sự hiện diện của entry**, không đọc nội dung manifest, không xác thực runtime dependencies và không chạy ứng dụng. Nó có giá trị khi muốn viết assertion đơn giản mà không cần Bash `grep` hay `unzip`. Với plain JAR, các path `BOOT-INF/classes/**` không tồn tại; phải đổi expectation cho đúng loại artifact.

Bạn cũng có thể dùng `JarFile.getManifest()` để đọc attributes `Main-Class` và `Start-Class`, nhưng cần xử lý trường hợp manifest không tồn tại và xác minh đúng launch layout. Ví dụ trên cố ý giữ phép thử đơn giản, dễ chạy độc lập.

## 13. Tính toàn vẹn, checksum, chữ ký và an toàn giải nén

### 13.1. ZIP CRC không thay thế chữ ký

```bash
unzip -t build/libs/jar-inspect-demo-1.0.0.jar
```

Lệnh kiểm tra khả năng đọc nội dung nén và CRC của các entry. Nó **không bảo đảm artifact từ nguồn đáng tin hay an toàn khi thực thi**. `jar tf` thậm chí chỉ liệt kê tên entry, không kiểm tra tất cả nội dung class.

### 13.2. So sánh checksum SHA-256

Linux/macOS khi có tiện ích `sha256sum`:

```bash
sha256sum build/libs/jar-inspect-demo-1.0.0.jar
```

Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\build\libs\jar-inspect-demo-1.0.0.jar
```

Checksum có ý nghĩa khi được **đối chiếu với hash tham chiếu lấy qua kênh đáng tin** hoặc khi cần chứng minh file kiểm tra chính là file đã deploy. Một hash vừa tự tính không tự xác thực nhà phát hành.

### 13.3. JAR ký số và nested libraries

Đối với **thư viện JAR thực sự được ký số**, JDK có:

```bash
jarsigner -verify -verbose -certs path/to/signed-library.jar
```

Đừng nhầm việc kiểm tra chữ ký của **outer executable JAR** với việc kiểm tra mọi nested dependency JAR: chúng là các artifact riêng, có thể có cơ chế signing/trust khác nhau. Nếu cần xác minh nguồn gốc phần mềm, dùng quy trình supply-chain và policy của tổ chức thay vì nhìn `META-INF/*.SF` rồi tự kết luận tin cậy.

### 13.4. An toàn khi thao tác JAR lạ

JAR từ nguồn không tin cậy có thể chứa path lạ, quá nhiều entry hoặc dữ liệu khiến công cụ giải nén tiêu tốn tài nguyên lớn. Hãy **liệt kê trước**, tạo thư mục tạm trống, không chạy bằng quyền quản trị và cẩn trọng với path traversal. Đừng chạy `java -jar` cho chương trình không rõ nguồn chỉ để “xem bên trong”; việc **đọc entry** và việc **thực thi code** là hai hành động khác nhau.

Không nhúng private key, access token hoặc mật khẩu vào `src/main/resources`: nếu build đóng gói chúng, người có JAR có thể dùng `jar xf`/`unzip -p` để đọc dữ liệu. Việc minify hoặc đổi tên file không bảo vệ secret.

## 14. Kiểm tra artifact tự động trong CI

Một pipeline có thể **fail sớm** nếu executable JAR thiếu entry bắt buộc. Ví dụ Bash chạy từ gốc **project mẫu**:

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR='build/libs/jar-inspect-demo-1.0.0.jar'
test -s "$JAR"

jar tf "$JAR" > jar-entry-list.txt
grep -Fx 'META-INF/MANIFEST.MF' jar-entry-list.txt
grep -Fx 'BOOT-INF/classes/com/example/inspect/JarInspectApplication.class' jar-entry-list.txt
grep -Fx 'BOOT-INF/classes/demo/marker.txt' jar-entry-list.txt
grep -E '^BOOT-INF/lib/.*[.]jar$' jar-entry-list.txt

java -jar "$JAR" > jar-run.log
grep -Fx 'archive-resource=archive-inspection-ok' jar-run.log
```

`grep -Fx` yêu cầu **toàn bộ dòng bằng đúng path**. Ví dụ này phù hợp vì chương trình demo tự chạy rồi kết thúc; nếu JAR là **web server chạy lâu dài**, cần dùng health/smoke test với vòng đời process và timeout được quản lý, **không** chạy `java -jar` đồng bộ rồi chờ nó tự thoát.

Một kiểm tra PowerShell đơn giản:

```powershell
$jar = '.\build\libs\jar-inspect-demo-1.0.0.jar'
if (-not (Test-Path -LiteralPath $jar)) {
    throw 'Executable JAR not found'
}
$entries = @(jar tf $jar)
if ($LASTEXITCODE -ne 0) {
    throw 'jar tf failed'
}
$required = @(
    'META-INF/MANIFEST.MF',
    'BOOT-INF/classes/com/example/inspect/JarInspectApplication.class',
    'BOOT-INF/classes/demo/marker.txt'
)
foreach ($name in $required) {
    if ($entries -notcontains $name) {
        throw "Missing archive entry: $name"
    }
}
Write-Output 'Required JAR entries found'
```

Các scripts này chỉ là **mẫu cho cấu trúc JAR cụ thể của bài**, không nên áp dụng nguyên xi cho plain JAR hay WAR. Có thể tăng cường bằng cách đọc manifest, so sánh checksum với bản release, tìm file nhạy cảm và chạy artifact trong container kiểm thử. Nhớ giữ log/report phù hợp trong CI.

## 15. Gỡ lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `jar: command not found` | Chưa cài JDK hoặc `PATH` sai | `JAVA_HOME`, `jar --version` |
| `NoSuchFileException` khi `jar tf` | Sai file name/path, chưa build | Mở `build/libs` hoặc `target` |
| Không thấy `BOOT-INF/classes` | Đang mở plain JAR, shaded JAR, WAR hoặc layout khác | Xác định đúng artifact loại nào |
| Maven tạo `*.jar.original` | Bản gốc trước `repackage` | Kiểm tra executable JAR không có hậu tố này |
| Gradle có `-plain.jar` | Task `jar` tạo plain JAR cạnh `bootJar` | Chọn đúng classifier để deploy |
| `jar tf` thấy manifest nhưng không có nội dung | `t` chỉ liệt kê entry | `unzip -p` hoặc `jar xf` |
| `java -jar` báo thiếu main | Manifest thiếu/sai `Main-Class` hoặc build chưa repackage | Đọc manifest, log plugin packaging |
| `Start-Class` đúng tên nhưng startup lỗi | Thiếu class/runtime dependency, cấu hình hoặc lỗi startup | `jar tf`, nested JAR, stack trace |
| Không tìm thấy class Spring Framework trong outer listing | Class nằm trong `BOOT-INF/lib/*.jar` lồng nhau | Trích xuất nested JAR rồi chạy `jar tf` trên nó |
| `getResourceAsStream` trả `null` | Sai classpath path, resource bị exclude | So sánh source, output và `BOOT-INF/classes` |
| Test classes/JUnit xuất hiện trong production JAR | Scope/configuration/packaging sai | Xem `testImplementation` / Maven `test` scope |
| Một thư viện thiếu | Đã bị exclude hoặc sai scope/version | Đối chiếu dependency graph và `BOOT-INF/lib` |
| `jar xf` làm rơi nhiều file vào project | Giải nén toàn bộ ở current directory | Tạo thư mục tạm, chỉ extract entry cần xem |
| `unzip -p` đọc binary ra file rồi file hỏng | Shell/encoding/redirection ảnh hưởng binary stream | Dùng `jar xf` hoặc công cụ ZIP extract byte nguyên bản |
| Resource trong JAR đúng mà cấu hình runtime khác | Spring Boot property precedence/profile/config ngoài | Kiểm tra môi trường runtime, không chỉ archive |
| File JAR đúng nhưng container chạy phiên bản cũ | CI/CD deploy sai artifact/tag/cached image | Đối chiếu path, checksum và bản image |
| `unzip -t` PASS mà ứng dụng vẫn hỏng | CRC khác với tính tương thích/chạy được | Chạy `java -jar`, xem log và dependency |
| Không thấy `layers.idx` | Không được tạo trong cấu hình này | Không mặc nhiên là lỗi; kiểm tra yêu cầu build |
| JAR lớn bất thường | Dependency dư, file resource lớn, test data bị mang vào | Duyệt `BOOT-INF/lib`, resource và archive sizes |

## 16. Checklist trước khi phát hành

- [ ] Biết **chính xác artifact** được deploy: plain/shaded JAR, `bootJar`, Maven `repackage` hay WAR.
- [ ] `jar tf` đọc được đúng file mới build, không phải file cũ/classifier sai.
- [ ] Với Boot executable JAR, thấy `META-INF/MANIFEST.MF`, loader, `BOOT-INF/classes` và `BOOT-INF/lib` nếu ứng dụng cần runtime dependencies.
- [ ] Đã **đọc nội dung manifest**, xác nhận `Main-Class` và `Start-Class` đúng.
- [ ] Class ứng dụng quan trọng nằm trong archive ở đúng package path.
- [ ] Resource/config/template/static asset cần thiết nằm ở đúng entry path.
- [ ] Đã đọc một resource bên trong archive để xác nhận **nội dung**, không chỉ tên file.
- [ ] Biết mở nested JAR khi cần kiểm tra class hay resource thuộc thư viện phụ thuộc.
- [ ] Đã so sánh nested dependencies với `runtimeClasspath` (Gradle) hoặc `dependency:tree` (Maven).
- [ ] Không vô tình mang test dependency, file tạm, secret và dữ liệu riêng vào production archive.
- [ ] Đã kiểm tra tính toàn vẹn/checksum theo yêu cầu và thao tác giải nén trong vùng an toàn.
- [ ] `java -jar`/smoke test chạy **đúng artifact sẽ triển khai**, không chỉ source từ IDE.
- [ ] Pipeline fail nếu thiếu entry quan trọng và ghi nhận kết quả đủ để truy tìm lỗi.

**Ghi nhớ:** `jar tf` trả lời “**có những entry nào trong JAR?**”; `jar tvf` thêm metadata; `jar xf` và `unzip -p` cho biết “**file thực sự chứa gì?**”; manifest xác định cơ chế launch; `BOOT-INF/classes` chứa ứng dụng/resource; `BOOT-INF/lib` chứa nested runtime dependencies. Kết hợp **xem danh sách → đọc manifest/resource → kiểm tra thư viện → chạy artifact thật** mới kiểm chứng đầy đủ một Spring Boot executable JAR.

## Tài liệu tham khảo

- [Oracle JDK 17 — jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
- [Oracle JDK 17 — JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html)
- [Spring Boot 3.3 — Developing Your First Spring Boot Application](https://docs.spring.io/spring-boot/3.3/tutorial/first-application/)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot — Executable JAR Format / Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)