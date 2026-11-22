# JAR thường và JAR thực thi khác nhau ở nội dung và cách khởi động

Khi xây dựng ứng dụng Java, đặc biệt là Spring Boot, bạn có thể thấy hai tệp cùng có đuôi `.jar` nhưng hành vi rất khác nhau. Một tệp chỉ chứa các lớp đã biên dịch và tài nguyên của dự án; tệp khác đóng gói cả các dependency cần thiết và có thể khởi động trực tiếp bằng `java -jar`. Phân biệt đúng hai loại giúp tránh lỗi `no main manifest attribute`, `ClassNotFoundException` hoặc `NoClassDefFoundError` khi triển khai.

Trong bài này, **JAR thường** (plain/ordinary JAR) được hiểu là archive JAR chuẩn chủ yếu chứa class và resources của module, không được Spring Boot tái đóng gói để tự mang runtime dependencies. **JAR thực thi của Spring Boot** (Spring Boot executable JAR, còn gọi repackaged/boot JAR) là archive có cấu trúc và launcher riêng để chạy ứng dụng Spring Boot từ một tệp duy nhất. Đây là cách phân loại **theo cấu trúc và khả năng chạy thực tế**, không phải hai phần mở rộng file khác nhau.

**Mục tiêu sau bài học:** (1) giải thích `META-INF/MANIFEST.MF`, `Main-Class` và `Start-Class`; (2) đọc được cấu trúc `BOOT-INF/classes`, `BOOT-INF/lib` và Spring Boot loader; (3) hiểu khi nào dùng `java -cp` và khi nào dùng `java -jar`; (4) tạo và kiểm tra cả hai loại JAR bằng Maven hoặc Gradle; (5) phân biệt plain JAR, executable Boot JAR, shaded/uber JAR và runnable Java JAR thông thường.

## 1. Đuôi `.jar` không cho biết khả năng chạy

JAR (*Java ARchive*) dựa trên định dạng ZIP; nó có thể chứa `.class`, resources, `META-INF/MANIFEST.MF` và metadata khác. JAR có thể dùng làm thư viện, công cụ dòng lệnh hoặc ứng dụng. **Không phải cứ có đuôi `.jar` là chạy được bằng `java -jar`.**

Một JAR chỉ chứa một class có `public static void main(String[] args)` vẫn **chưa đủ** để `java -jar` biết chọn class nào, nếu manifest không khai báo entry point. Ngược lại, một JAR Java đơn giản không có dependency ngoài vẫn có thể chạy bằng `java -jar` chỉ với `Main-Class` trong manifest; nó không nhất thiết phải là “fat JAR”.

Ba trường hợp thường gặp:

| Trường hợp | Nội dung chính | Cách chạy điển hình |
| --- | --- | --- |
| Plain/library JAR | `.class` và resources của một module; không gộp dependency ngoài | Được đưa lên **classpath** của ứng dụng khác; hoặc chạy `java -cp` với main class và classpath đầy đủ |
| Runnable Java JAR truyền thống | Plain JAR có manifest `Main-Class`; dependency có thể phải để bên ngoài | `java -jar app.jar` nếu entry point và các thư viện cần thiết đều tìm được |
| Spring Boot executable JAR | Boot loader + `BOOT-INF/classes` + các JAR runtime trong `BOOT-INF/lib` | `java -jar app.jar`; Boot loader thiết lập classpath từ nested JARs |

Vì vậy, **“JAR thực thi” trong ngữ cảnh Boot không có nghĩa Java chỉ hỗ trợ Boot JAR**. Khác biệt của Boot nằm ở khả năng mang và nạp **nested dependency JARs** theo layout Boot, chứ không phải một phép màu biến `.jar` thành tệp thực thi hệ điều hành độc lập với JVM.

## 2. Nhìn trực tiếp cấu trúc hai archive

### 2.1. Plain JAR điển hình

Ví dụ một ứng dụng có main class `dev.example.jar.BootJarDemoApplication`:

```text
boot-jar-demo-1.0.0-plain.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── maven/                     (có thể có khi build bằng Maven)
└── dev/
    └── example/
        └── jar/
            └── BootJarDemoApplication.class
```

Lớp Java ứng dụng nằm **ở root theo package path**: `dev/example/jar/BootJarDemoApplication.class`. Nếu ứng dụng còn dùng Spring Framework, Jackson, Tomcat, logging..., những thư viện ấy **không được plain JAR tự động gộp vào**. Chúng phải được cấp qua classpath bên ngoài, cấu hình manifest thích hợp hoặc một cơ chế đóng gói khác.

Plain JAR có thể được dùng như một **thư viện** trong ứng dụng lớn hơn hoặc làm input cho một quy trình đóng gói/phân phối khác. Từ “plain” mô tả việc không được Spring Boot loader tái đóng gói; nó **không khẳng định** JAR không có entry point hay không thể chạy trong mọi trường hợp.

### 2.2. Spring Boot executable JAR

```text
boot-jar-demo-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/
│   └── launch/JarLauncher.class
├── BOOT-INF/
│   ├── classes/
│   │   └── dev/example/jar/
│   │       └── BootJarDemoApplication.class
│   └── lib/
│       ├── spring-boot-*.jar
│       ├── spring-web-*.jar
│       ├── jackson-*.jar
│       └── các dependency runtime khác
└── [metadata hỗ trợ lớp/layer, nếu có]
```

Ở đây `BOOT-INF/classes` chứa **lớp và resources của ứng dụng**; `BOOT-INF/lib` chứa **các JAR phụ thuộc**. Các JAR trong `BOOT-INF/lib` được giữ dưới dạng **JAR lồng trong JAR**, thay vì bung tất cả file `.class` của thư viện ra cùng một thư mục như một số cách làm shaded JAR.

`org.springframework.boot.loader.launch.JarLauncher` là lớp launcher của Spring Boot 3.3. Nó hiểu `BOOT-INF/classes` và `BOOT-INF/lib`, chuẩn bị classloader phù hợp, rồi gọi main method thật của ứng dụng. Java classpath loader thông thường không tự nạp tất cả JAR nằm bên trong một JAR khác theo cấu trúc này.

**Hệ quả quan trọng:** Hai JAR có thể chứa **cùng mã ứng dụng** nhưng có đường dẫn internal và chiến lược nạp dependency khác nhau. Vì thế thao tác chạy chúng không thể đơn giản đổi tên file mà giữ mọi đối số `java` như cũ.

## 3. Manifest quyết định entry point

Tệp `META-INF/MANIFEST.MF` là metadata chuẩn của JAR. Hai thuộc tính cần phân biệt trong bài:

- **`Main-Class`**: Java launcher dùng để xác định class có phương thức `public static void main(String[] args)` khi chạy `java -jar`.
- **`Start-Class`**: thuộc tính mà Spring Boot loader dùng để xác định **main class của ứng dụng**. Đây không phải tên thuộc tính Java launcher chuẩn dùng để chọn entry point.

Ví dụ plain runnable Java JAR:

```text
Manifest-Version: 1.0
Main-Class: dev.example.cli.Hello
```

Ví dụ Spring Boot 3.3 executable JAR:

```text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.jar.BootJarDemoApplication
Spring-Boot-Version: 3.3.13
```

Đây là các **dòng manifest minh họa**; build tool có thể bổ sung những attributes khác như classpath/layer indices hoặc build metadata. Đừng kỳ vọng nội dung manifest hoàn toàn giống từng byte giữa các dự án.

Trình tự khởi động của Boot:

```text
java -jar boot-jar-demo-1.0.0.jar
        |
        v
JVM đọc META-INF/MANIFEST.MF
        |
        v
Main-Class = org.springframework.boot.loader.launch.JarLauncher
        |
        v
Boot loader mở BOOT-INF/classes và BOOT-INF/lib/*.jar
        |
        v
Start-Class = dev.example.jar.BootJarDemoApplication
        |
        v
BootJarDemoApplication.main(args)
        |
        v
SpringApplication.run(...) -> Spring context -> web server
```

**Đừng sửa `Main-Class` thành application class trong Boot JAR** mà vẫn giữ cấu trúc `BOOT-INF`: ứng dụng sẽ mất launcher chịu trách nhiệm giải quyết nested classpath. Ngược lại, plain JAR không có Boot loader sẽ không biết lớp `JarLauncher` là gì. Plugin đóng gói sẽ đặt các attributes tương ứng; hãy cấu hình main class ở **Spring Boot plugin** hoặc metadata project thích hợp thay vì sửa manifest tay trong một JAR đã build.

## 4. Hai lệnh `java -cp` và `java -jar` thực sự khác nhau như thế nào?

### 4.1. `java -cp`: bạn tự cung cấp classpath và main class

Ví dụ:

```bash
java -cp "app.jar:lib/*" dev.example.jar.BootJarDemoApplication
```

Đây là ví dụ trên Linux/macOS; Windows dùng dấu `;` để phân tách classpath entries:

```powershell
java -cp "app.jar;lib/*" dev.example.jar.BootJarDemoApplication
```

Java tìm `dev/example/jar/BootJarDemoApplication.class` trong `app.jar`, còn thư viện nằm ở các JAR trong `lib/`. Dấu `*` sau thư mục trong classpath là cơ chế classpath wildcard của Java launcher, không phải cơ chế nhận nested JAR từ Boot. `java -cp` đặc biệt hữu ích khi bạn muốn chạy một **plain JAR** với dependency JARs đặt riêng.

Nếu class chỉ có trong JAR nhưng những thư viện nó import khi khởi động không có trên classpath, có thể phát sinh lỗi tải class. Với ứng dụng Spring Boot dùng `spring-boot-starter-web`, chỉ thêm plain application JAR vào `-cp` là **không đủ**.

### 4.2. `java -jar`: JVM đọc entry point từ manifest

```bash
java -jar boot-jar-demo-1.0.0.jar
```

Java launcher đọc manifest của JAR, gọi `Main-Class`, rồi chuyển các application arguments cho main method. Với Boot JAR, `Main-Class` là `JarLauncher` và launcher của Boot dựng classpath nội bộ từ `BOOT-INF`.

Khi dùng `-jar`, các classpath settings theo `-cp`/`CLASSPATH` **không có hiệu lực như cách chạy `-cp`**, nên đừng nghĩ:

```bash
java -cp "lib/*" -jar plain.jar
```

sẽ tự giải quyết thư viện ngoài nhờ `-cp`. Với plain runnable JAR cần external libraries, có thể khai báo `Class-Path` trong manifest cho các JAR có đường dẫn phù hợp, hoặc dùng `java -cp "plain.jar:lib/*" package.Main` trực tiếp. Với Spring Boot executable JAR, hãy dùng launcher theo `java -jar` như thiết kế.

### 4.3. Lỗi hay gặp khi chọn sai kiểu chạy

| Lệnh/thao tác | Kết quả có thể gặp | Vì sao |
| --- | --- | --- |
| `java -jar plain.jar` khi không có `Main-Class` | `no main manifest attribute` | Java launcher không biết main class |
| `java -jar plain.jar` có `Main-Class` nhưng thiếu Spring runtime libs | `ClassNotFoundException` hoặc `NoClassDefFoundError` | Classpath thiếu dependency |
| `java -cp plain.jar package.Main` nhưng không có libs cần thiết | Lỗi tải class lúc runtime | Plain JAR không gói sẵn dependencies |
| `java -cp boot.jar package.Main` | Không tìm thấy application main class | Classes của Boot JAR nằm dưới `BOOT-INF/classes`, không ở classpath root |
| `java -jar boot.jar` với manifest đúng và Boot loader đầy đủ | Khởi động được nếu ứng dụng/config hợp lệ | Loader mở nested dependency jars |
| Đổi tên `plain.jar` thành `boot.jar` | Không tự thay đổi khả năng chạy | Tên tệp không tái cấu trúc archive hay thêm loader |

## 5. Một thử nghiệm Java thuần để tách `Main-Class` khỏi “fat JAR”

Trước khi dùng Spring Boot, hãy kiểm chứng quy tắc của Java launcher với class không cần thư viện ngoài.

Tạo tệp `src/example/Hello.java`:

```java
package example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello JAR");
    }
}
```

Trên hệ thống có JDK 17+, tại thư mục chứa `src/`:

```bash
mkdir -p out
javac -d out src/example/Hello.java

# JAR thường, không khai báo Main-Class
jar --create --file hello-plain.jar -C out .

# Java biết main class nhờ -cp và tên class
java -cp hello-plain.jar example.Hello

# Thêm Main-Class khi tạo một JAR có entry point
jar --create --file hello-runnable.jar --main-class example.Hello -C out .

java -jar hello-runnable.jar
```

Hai lần in stdout:

```text
Hello JAR
```

Lệnh `java -jar hello-plain.jar` (không khai báo entry point) sẽ báo lỗi thiếu `Main-Class` tương tự:

```text
no main manifest attribute, in hello-plain.jar
```

Ví dụ này chứng minh một **JAR Java thông thường có thể chạy bằng `java -jar`** nếu có manifest `Main-Class` và các class phụ thuộc được tìm thấy. Nó không hề có `BOOT-INF` hay Spring Boot loader vì không cần dependency ngoài. Bản chất vấn đề Spring Boot phải giải quyết là **đóng gói ứng dụng có nhiều JAR phụ thuộc** thành một executable archive mà Java có thể khởi động.

Nếu thực hành trên Windows PowerShell, tạo thư mục bằng `New-Item -ItemType Directory out -Force` thay vì `mkdir -p out`. Lệnh `javac`, `jar` và `java` giữ nguyên; thư mục nguồn theo package phải tồn tại.

## 6. Ví dụ Spring Boot Maven hoàn chỉnh: cùng source, hai JAR khác layout

Dùng Maven 3.9.x và JDK 17. Tạo project:

```text
boot-jar-demo/
├── pom.xml
└── src/
    ├── main/java/dev/example/jar/BootJarDemoApplication.java
    └── test/java/dev/example/jar/BootJarDemoApplicationTests.java
```

### 6.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>boot-jar-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

**Vì sao có hai bước đóng gói?** Với `<packaging>jar</packaging>`, Maven JAR Plugin tạo plain JAR ở phase `package`. `spring-boot-starter-parent` đã cung cấp execution của goal `spring-boot:repackage` và việc khai báo `spring-boot-maven-plugin` ở `<plugins>` làm goal này được thực thi. Nó đọc JAR gốc, thêm launcher, đổi layout, nhúng runtime dependencies và tạo Boot executable JAR thay thế main artifact. Tập tin plain ban đầu thường được giữ lại với đuôi `.jar.original`.

BOM Spring Boot chọn dependency versions; **BOM import riêng lẻ không tự gắn goal `repackage`**. Nếu không dùng starter parent mà chỉ import BOM, bạn phải tự cấu hình Spring Boot Maven Plugin với phiên bản phù hợp và execution goal `repackage`.

### 6.2. Class ứng dụng

Tệp `src/main/java/dev/example/jar/BootJarDemoApplication.java`:

```java
package dev.example.jar;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class BootJarDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootJarDemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello executable JAR";
    }
}
```

Tệp `src/test/java/dev/example/jar/BootJarDemoApplicationTests.java`:

```java
package dev.example.jar;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BootJarDemoApplicationTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void endpointResponds() throws Exception {
        mvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello executable JAR"));
    }
}
```

Không cần `application.yml` để ví dụ chạy tại cổng HTTP mặc định 8080 nếu môi trường không ghi đè `server.port`. Test dùng MockMvc nên không cần khởi động HTTP server riêng trên cổng 8080.

### 6.3. Build và xác nhận hai tệp

```bash
mvn -version
mvn clean verify
ls -lh target/boot-jar-demo-1.0.0.jar*
```

Trong cấu hình mặc định:

```text
target/boot-jar-demo-1.0.0.jar
target/boot-jar-demo-1.0.0.jar.original
```

- Tệp `.jar` là **Spring Boot executable JAR** sau `repackage`.
- Tệp `.jar.original` là **plain JAR trước `repackage`**. Dù phần mở rộng kết thúc bằng `.original`, nội dung vẫn là archive JAR/ZIP hợp lệ; nó chỉ là backup output của plugin.

Kiểm tra các entry:

```bash
jar tf target/boot-jar-demo-1.0.0.jar
jar tf target/boot-jar-demo-1.0.0.jar.original
```

Trong Boot JAR, tìm các entry:

```text
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/jar/BootJarDemoApplication.class
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/spring-boot-autoconfigure-3.3.13.jar
```

Trong plain JAR, tìm:

```text
dev/example/jar/BootJarDemoApplication.class
```

Plain JAR không chứa cả bộ `BOOT-INF/lib` như Boot JAR. Danh sách trên chỉ trích các entry nổi bật; JAR thực tế còn nhiều class/resources/library khác và thứ tự liệt kê không cố định.

### 6.4. Chạy Boot JAR trực tiếp

```bash
java -jar target/boot-jar-demo-1.0.0.jar
```

Sau khi khởi động thành công, terminal khác:

```bash
curl -s http://localhost:8080/hello
```

Body:

```text
Hello executable JAR
```

Đây là mô hình phổ biến cho container, VM hoặc deployment pipeline. JAR đã có application classes, runtime dependencies và Boot loader; máy chạy vẫn cần **JVM tương thích**, và vẫn có thể cần database, network, environment variables hoặc external services theo cấu hình ứng dụng. Từ “self-contained” ở đây không có nghĩa một tệp JAR tự mang cả hệ điều hành/JDK và mọi dịch vụ bên ngoài.

## 7. Chạy plain JAR Spring Boot: bổ sung classpath ngoài

Plain JAR vẫn chứa `BootJarDemoApplication.class` và có thể thực hiện main method, nhưng nó **không tự mang các Spring runtime JAR cần thiết**. Vì thế nếu gọi:

```bash
java -cp target/boot-jar-demo-1.0.0.jar.original dev.example.jar.BootJarDemoApplication
```

ứng dụng thường không khởi động vì thiếu Spring Boot/Spring Framework trên classpath. Hãy cung cấp tất cả dependencies runtime.

Đầu tiên dùng Maven Dependency Plugin sao chép chúng vào thư mục riêng:

```bash
mvn dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/dependency
```

Để có file đuôi `.jar` dễ dùng trong Java classpath, sao chép JAR gốc:

```bash
cp target/boot-jar-demo-1.0.0.jar.original target/plain.jar
```

Rồi chạy trên Linux/macOS:

```bash
java -cp "target/plain.jar:target/dependency/*" dev.example.jar.BootJarDemoApplication
```

Trên PowerShell/Windows, thay hai lệnh cuối bằng:

```powershell
Copy-Item target/boot-jar-demo-1.0.0.jar.original target/plain.jar
java -cp "target/plain.jar;target/dependency/*" dev.example.jar.BootJarDemoApplication
```

Nếu hệ thống có đầy đủ dependencies và không ghi đè cổng, endpoint `/hello` vẫn trả `Hello executable JAR`. Đó là **cùng logic ứng dụng** nhưng classpath được cung cấp bên ngoài bởi `-cp`.

**Đây là bài thực hành để hiểu cơ chế**, không nhất thiết là cách triển khai ưu tiên. Trong production, chọn một packaging strategy rõ ràng: executable Boot JAR, container image, WAR phù hợp hoặc phân phối classpath bên ngoài có kiểm soát. Tránh trộn các phương pháp khiến thư viện bị thiếu/trùng phiên bản.

**Không dùng `java -jar target/plain.jar -cp ...` để giải quyết classpath**. Khi `-jar` được dùng, hãy nhớ Java launcher ưu tiên main entry từ manifest của JAR và không lấy classpath theo cách `java -cp`. Đối với plain archive thiếu Main-Class, cách chắc chắn là gọi class có main method như trên cùng với đủ dependency.

## 8. Gradle: `jar` và `bootJar` là hai task khác nhau

Với Spring Boot Gradle Plugin 3.3, khi áp dụng Java plugin:

- **`jar`**: tạo plain JAR thông thường, mặc định có classifier `plain`, ví dụ `boot-jar-demo-1.0.0-plain.jar`.
- **`bootJar`**: tạo Spring Boot executable JAR, mặc định ví dụ `boot-jar-demo-1.0.0.jar`.
- **`build`** có thể tạo cả các outputs theo lifecycle/task dependencies; ở ví dụ dưới sẽ gọi rõ `bootJar` và `jar` để dễ kiểm tra.

### 8.1. `settings.gradle` và `build.gradle`

Tạo `settings.gradle`:

```groovy
rootProject.name = 'boot-jar-demo'
```

Tạo `build.gradle` (Groovy DSL), sử dụng cùng hai tệp Java ở mục 6:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.register('copyRuntimeLibs', Copy) {
    from configurations.runtimeClasspath
    into layout.buildDirectory.dir('external-libs')
}
```

Với project Gradle riêng, đặt hai tệp nguồn Java đúng `src/main/java/dev/example/jar/BootJarDemoApplication.java` và `src/test/java/dev/example/jar/BootJarDemoApplicationTests.java`; **không đồng thời dùng `pom.xml` nếu không có chủ đích duy trì hai build definitions**.

Gradle build sử dụng `org.springframework.boot` plugin để tạo task `bootJar`. Dependency Management Plugin phối hợp cùng Boot plugin để import BOM version tương ứng. Task `copyRuntimeLibs` là phần **tự thêm vào chỉ nhằm minh họa việc chạy plain JAR**: nó sao chép các JAR từ `runtimeClasspath` ra một thư mục, không cần cho Boot executable JAR.

### 8.2. Tạo và xem hai tệp

Nếu đã có Gradle Wrapper tương thích với Spring Boot plugin, chạy (Windows dùng `gradlew.bat`):

```bash
./gradlew clean test bootJar jar copyRuntimeLibs
ls -lh build/libs/
jar tf build/libs/boot-jar-demo-1.0.0.jar
jar tf build/libs/boot-jar-demo-1.0.0-plain.jar
```

Tên tệp trong cấu hình ví dụ:

```text
build/libs/boot-jar-demo-1.0.0.jar        -> executable Boot JAR
build/libs/boot-jar-demo-1.0.0-plain.jar  -> plain JAR
```

Thực tế tên archive có thể khác khi project đổi `archiveBaseName`, `archiveVersion`, `archiveClassifier` hoặc custom task. Đừng suy từ phần mở rộng `.jar`; xác minh bằng manifest và nội dung.

Khởi động Boot JAR:

```bash
java -jar build/libs/boot-jar-demo-1.0.0.jar
```

Hoặc chạy plain JAR với các dependency ngoài do task minh họa sao chép:

```bash
java -cp "build/libs/boot-jar-demo-1.0.0-plain.jar:build/external-libs/*" dev.example.jar.BootJarDemoApplication
```

Windows:

```powershell
java -cp "build/libs/boot-jar-demo-1.0.0-plain.jar;build/external-libs/*" dev.example.jar.BootJarDemoApplication
```

Chỉ chạy **một phiên bản mỗi lần** nếu cả hai muốn sử dụng cổng 8080. Cả hai cách có thể phục vụ cùng endpoint `/hello` nếu runtime classpath và configuration chính xác.

### 8.3. Thay đổi classifier và tránh publish nhầm

Spring Boot Gradle Plugin thường đặt `plain` làm classifier cho `jar` để output không ghi đè `bootJar`. Nếu nhóm muốn thay convention, phải điều chỉnh task tương ứng và kiểm tra mọi nơi tiêu thụ artifact:

```groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}
tasks.named('jar') {
    archiveClassifier = ''
}
```

Đây là **fragment minh họa thay đổi tên output**, không cần cho ví dụ ở trên. Sau khi cấu hình như vậy, plain JAR không có classifier, còn executable JAR có hậu tố `-boot.jar`. Vì vậy CI không được hard-code “file không có hậu tố luôn là executable JAR” nếu project cho phép thay classifier.

Trong dự án library, nhiều lúc chỉ muốn plain JAR để module khác phụ thuộc bằng classpath chuẩn. Trong dự án triển khai Spring Boot service, thường cần `bootJar`. Nếu xuất bản lên Maven repository, phải kiểm tra task/publication lựa chọn artifact nào; việc nhìn thấy hai tệp trong `build/libs` chưa xác nhận tệp nào đã publish.

## 9. Vì sao không chỉ bung tất cả dependencies vào một JAR?

Có nhiều cách đưa ứng dụng Java nhiều dependency vào một artifact. Spring Boot executable JAR là **một cách cụ thể**:

| Kiểu đóng gói | Cách tổ chức | Cách khởi động | Ưu điểm/điểm cần cân nhắc |
| --- | --- | --- | --- |
| Plain JAR + external libs | App JAR và thư mục `lib/*.jar` tách rời | `java -cp ... package.Main`, hoặc manifest `Class-Path` đúng | Rõ ràng các JAR riêng; phải phân phối và quản lý classpath |
| Plain runnable JAR không có dependency ngoài | Class của ứng dụng + `Main-Class` | `java -jar file.jar` | Nhẹ và đơn giản; chỉ phù hợp khi mọi class cần thiết đã có |
| Shaded/uber JAR | Thường **bung** class/resources của dependencies vào một archive | `java -jar file.jar` nếu có main manifest | Có thể cần xử lý trùng resources/service descriptors, xung đột class |
| Spring Boot executable JAR | App classes ở `BOOT-INF/classes`; JAR thư viện **lồng trong `BOOT-INF/lib`**; Boot loader | `java -jar file.jar` | Dễ theo dõi nested libraries; cần launcher hiểu layout Boot |
| Spring Boot executable WAR | App ở `WEB-INF/classes`, libs ở `WEB-INF/lib`/`lib-provided` theo packaging | `java -jar file.war` nếu executable; hoặc deploy web container tùy cấu hình | Phục vụ bài toán WAR/container, không giống JAR layout |

Không gọi mọi fat JAR là “đóng gói y hệt Spring Boot”. **Shaded JAR** thường bung class của dependency ra root; Spring Boot **nested JAR** giữ mỗi dependency là một JAR riêng. Các kiểu này ảnh hưởng resource lookup, classloader, bảo mật dependency scanning và cách debug.

Một ứng dụng có nhiều thư viện đôi khi vẫn có thể chạy với plain JAR và external `lib`, miễn khớp classpath. Do đó sự khác biệt không nằm ở “plain JAR không bao giờ chạy được” mà nằm ở **độ tự chứa và cách Java/Boot tìm những class cần thiết**.

## 10. Kiểm tra manifest và nội dung thay vì đoán theo tên tệp

Một checklist kỹ thuật có thể thực hiện trên JAR sản phẩm:

**Bước 1: xác nhận artifact thực tế.**

```bash
ls target/*.jar*
# Hoặc với Gradle:
ls build/libs/*.jar
```

**Bước 2: liệt kê nội dung và tìm dấu hiệu Boot layout.**

```bash
jar tf target/boot-jar-demo-1.0.0.jar
```

Dấu hiệu của Boot executable JAR:

```text
BOOT-INF/classes/dev/example/jar/BootJarDemoApplication.class
BOOT-INF/lib/
org/springframework/boot/loader/launch/JarLauncher.class
```

Bản plain tương ứng thường chỉ có `dev/example/jar/BootJarDemoApplication.class` ở root, không có cả cấu trúc trên.

**Bước 3: đọc manifest.**

Nếu có lệnh `unzip`, dùng:

```bash
unzip -p target/boot-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Hoặc dùng JDK `jar` trong một thư mục làm việc tách biệt:

```bash
mkdir -p target/manifest-inspect
cd target/manifest-inspect
jar xf ../boot-jar-demo-1.0.0.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
```

Bản Boot 3.3 cần có `Main-Class` trỏ tới Boot launcher phù hợp và `Start-Class` trỏ tới application main class. Nếu đặt cả hai thuộc tính đúng nhưng thư viện/loader đã bị xóa hoặc cấu trúc archive bị thay đổi, JAR vẫn có thể không chạy; **manifest đúng là điều kiện cần, không phải chứng minh đủ**.

**Bước 4: khởi động một cách thực tế.**

```bash
java -version
java -jar target/boot-jar-demo-1.0.0.jar
```

Kiểm tra startup log và HTTP endpoint, không chỉ dựa vào `BUILD SUCCESS`. Với Spring Boot 3.3, project trong bài dùng Java 17, nên JVM cũ hơn Java target có thể báo `UnsupportedClassVersionError` dù JAR đóng gói hoàn toàn đúng.

**Bước 5: so sánh kích thước một cách có ý nghĩa.**

Boot executable JAR thường lớn hơn plain JAR vì chứa thư viện runtime, nhưng **không dùng kích thước file làm tiêu chí duy nhất**. Một plain/shaded JAR, embedded resources hoặc các đặc điểm nén có thể khiến kích thước không phản ánh khả năng chạy. Kết luận theo manifest + layout + thử chạy mới chắc chắn.

## 11. JAR nào nên dùng cho library, application và CI/CD?

### Module thư viện

Một library cung cấp các kiểu Java, helper hoặc API cho những module khác thường xuất bản **plain JAR** để dependency resolver (Maven/Gradle) tự giải quyết các thư viện liên quan. Nếu phát hành Spring Boot executable JAR làm dependency thông thường, consumer có thể không tìm thấy class do nó nằm dưới `BOOT-INF/classes` thay vì root.

**Quy tắc:** không gắn một Spring Boot executable JAR vào `<dependencies>` rồi kỳ vọng Maven dùng nó giống một library JAR chuẩn.

Trong dự án multi-module, module `common` có thể tạo plain JAR, còn module `web-app` tạo Boot executable JAR. Module ứng dụng dùng `common` như dependency và đóng gói nó vào `BOOT-INF/lib` hoặc theo cấu hình packaging hợp lệ.

### Module dịch vụ Spring Boot

Một Spring Boot service triển khai bằng JVM thường ưu tiên executable Boot JAR. Pipeline:

```text
source + pinned build config
            |
            v
compile -> test -> package/bootJar
            |
            v
verify archive structure and runtime dependencies
            |
            v
smoke test: java -jar ...
            |
            v
publish EXACT checked artifact
            |
            v
deploy on target JVM/container
```

Không xây một JAR để kiểm thử rồi build lại một JAR khác bằng cấu hình profile/dependency khác ngay trước deploy mà không kiểm tra. Dùng artifact identity (version, checksum hoặc digest) để biết môi trường production chạy **chính output đã qua gate**.

### Container image

Có thể dùng executable JAR làm input cho container image, hoặc Spring Boot build-image workflows. **JAR không tự bao gồm JDK**, nên container base image phải có runtime Java tương thích hoặc build công cụ đóng gói image có runtime phù hợp. Một command kiểu `java -jar /app/app.jar` vẫn dựa trên cơ chế Boot loader và classpath bên trong JAR.

### Layered JAR

Spring Boot có hỗ trợ **layers** và metadata như `BOOT-INF/layers.idx` để thuận tiện tạo container layers. Layers không biến Boot JAR thành plain JAR: classes vẫn ở `BOOT-INF/classes`, dependencies vẫn ở `BOOT-INF/lib`. Layer index có thể được build plugin thêm khi bật cơ chế layered archive phù hợp; không nên tự áp dụng `java -cp` cho file `layers.idx`.

## 12. Các lỗi thực tế và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `java -jar ...jar` → `no main manifest attribute` | Plain JAR không có `Main-Class` | Chạy bằng `java -cp ... Main` hoặc đóng gói executable JAR đúng cách |
| `java -jar ...jar` → `ClassNotFoundException` | Manifest trỏ sai main/loader hoặc classes không ở vị trí mong đợi | Xem `META-INF/MANIFEST.MF` và `jar tf` |
| `NoClassDefFoundError: org/springframework/...` khi chạy plain JAR | Thiếu Spring libraries trên classpath | Cấp runtime JARs theo dependency resolver, dùng `-cp` hoặc Boot JAR |
| `java -cp boot.jar app.Main` không tìm ra main class | Boot đặt app classes trong `BOOT-INF/classes` | Dùng `java -jar` với Boot launcher |
| `java -jar` tìm thấy Main-Class nhưng thiếu embedded server | Dependency/packaging thiếu web starter hoặc scope sai | Xem `BOOT-INF/lib`, POM/Gradle runtime graph và Spring configuration |
| Maven chỉ tạo `.jar` plain dù đã import BOM | Chưa áp dụng/repackage Spring Boot Maven Plugin | Khai báo plugin/execution phù hợp, xem effective POM |
| Maven `.jar.original` nhỏ hơn `.jar` rất nhiều | Đúng vì là plain archive trước repackage | Giữ phân biệt; không deploy nhầm `.original` |
| Gradle tạo `-plain.jar` lẫn JAR không classifier | `jar` và `bootJar` cùng tồn tại | Chọn đúng output; không upload dựa duy nhất vào glob |
| `UnsupportedClassVersionError` | JVM target quá cũ cho bytecode đã biên dịch | Dùng Java runtime tương thích với `java.version`/toolchain |
| App chạy local nhưng production thiếu lớp | Local IDE classpath chứa dependency mà artifact không đóng gói | Kiểm tra dependency scopes, `BOOT-INF/lib`, artifact cuối và môi trường deploy |
| Servlet app chạy rồi báo port 8080 in use | Một process khác đang dùng cổng | Dừng process trước hoặc dùng `--server.port=8081` cho instance mới |
| JAR bị “not a valid jar” sau xử lý thủ công | ZIP/archive bị cắt hỏng, đổi nội dung không đúng định dạng | Rebuild từ source; xác minh hash và `jar tf` |
| Dùng plain JAR làm dependency mà đã chạy qua Spring Boot repackage | Consumer không thấy class dưới classpath root | Publish plain classifier/JAR của library hoặc tách module |
| Dùng shaded JAR nhưng mất service provider/resource | Xung đột file `META-INF/services` hoặc resources khi bung archive | Cấu hình shade transformers hoặc chọn Boot nested-JAR packaging |

### Quy trình sửa lỗi có thứ tự

1. **Xem chính xác command đã chạy**: `java -jar` hay `java -cp`? Lệnh có truyền main class không?
2. **Kiểm tra JDK:** `java -version` và `mvn -version`/Gradle toolchain.
3. **Xác định artifact:** đúng module, đúng version, đúng classifier, đúng file vừa build?
4. **Đọc archive:** `jar tf` có `BOOT-INF` và loader không? Application classes ở root hay `BOOT-INF/classes`?
5. **Đọc manifest:** `Main-Class` và, nếu là Boot JAR, `Start-Class` có hợp lý không?
6. **Xem runtime dependency graph:** Maven `dependency:tree` hoặc Gradle `dependencies --configuration runtimeClasspath`. So sánh với JAR đóng gói.
7. **Thử khởi động và smoke test:** đừng kết luận chỉ từ việc build thành công.
8. **Sửa tại build script/POM, không vá thủ công archive đã xuất bản**, rồi rebuild và kiểm tra artifact mới.

## 13. Bài tập tự kiểm tra

**Tình huống A.** Một JAR chứa `example/Hello.class` với main method nhưng không có `Main-Class`. Có chạy `java -jar` được không?

*Đáp án:* Không theo cơ chế `java -jar` thông thường. Chạy `java -cp hello.jar example.Hello` hoặc tạo lại JAR với manifest có `Main-Class: example.Hello`.

**Tình huống B.** Maven build Spring Boot xuất hai tệp `demo.jar` và `demo.jar.original`. File nào chạy trực tiếp theo chuẩn Boot?

*Đáp án:* `demo.jar` là main executable archive sau `repackage`; `.jar.original` là plain JAR gốc thường không chứa dependency runtime. Kiểm tra manifest và `jar tf` để chắc chắn output thực tế.

**Tình huống C.** Gradle xuất `demo-1.0.0.jar` và `demo-1.0.0-plain.jar`. Nên publish tệp nào làm ứng dụng chạy qua `java -jar`?

*Đáp án:* Theo convention Spring Boot Gradle Plugin mặc định, file **không có `-plain`** là executable Boot JAR. Nếu task classifier đã được custom, kiểm tra `bootJar` output thay vì dựa vào tên.

**Tình huống D.** Một đồng nghiệp thêm `Main-Class: dev.example.jar.BootJarDemoApplication` vào Spring Boot nested JAR và xóa Boot launcher để “đơn giản hóa”. Điều gì sai?

*Đáp án:* Application class nằm dưới `BOOT-INF/classes`, dependencies dưới `BOOT-INF/lib`; Java launcher chuẩn không tự nạp nested JARs theo layout Boot. Cần giữ Boot loader và manifest đúng thay vì sửa tay.

**Tình huống E.** Plain JAR có manifest `Main-Class`, nhưng khởi động báo không tìm thấy `org.springframework.boot.SpringApplication`. Tệp `Main-Class` có sai không?

*Đáp án:* Không nhất thiết. Main method có thể đúng, nhưng thiếu Spring Boot runtime dependencies trên classpath. Cần bổ sung thư viện hoặc đóng gói Boot executable JAR.

**Tình huống F.** Cùng ứng dụng khi chạy `java -cp "plain.jar:lib/*" dev.example.jar.BootJarDemoApplication` và `java -jar boot.jar` đều trả `Hello executable JAR`. Hai file có “cùng nội dung” không?

*Đáp án:* Không. Chúng có thể chứa cùng app code/behavior, nhưng Boot JAR mang nested dependencies và loader; plain JAR cần các JAR ngoài trên classpath. “Chạy cùng kết quả” không chứng minh layout hay dependency content giống nhau.

**Tình huống G.** Có người cho rằng “JAR thực thi” phải chạy khi double-click trên mọi hệ điều hành mà không cài Java. Kết luận?

*Đáp án:* Sai. `java -jar` yêu cầu một JVM tương thích; khả năng double-click/phân phối native launcher là chủ đề khác. Có thể dùng container runtime hoặc native image trong workflow riêng, nhưng JAR không tự biến thành binary máy.

**Tình huống H.** Build `mvn clean package` thành công, vì sao vẫn cần kiểm tra `jar tf` và chạy smoke test?

*Đáp án:* Thành công ở build chỉ xác nhận các goal được cấu hình đã chạy; có thể package sai classifier, thiếu runtime dependency hoặc có cấu hình runtime lỗi. Archive inspection và chạy thật xác minh đúng output định deploy.

## 14. Checklist quyết định loại JAR cho dự án

- **Loại module:** library tiêu thụ qua Maven/Gradle hay Spring Boot application deploy độc lập?
- **Packaging goal/task:** Maven `jar:jar` hay `spring-boot:repackage`? Gradle `jar` hay `bootJar`?
- **Main class:** có `main` không, và manifest `Main-Class` trỏ tới ứng dụng hay Boot `JarLauncher`?
- **Layout:** lớp ứng dụng tại package root hay `BOOT-INF/classes`? Dependency runtime ở ngoài hay `BOOT-INF/lib`?
- **Cách chạy:** `java -cp ... Main` cần external libs hay `java -jar ...` dùng Boot launcher?
- **JDK:** runtime target có tương thích Java 17 hoặc toolchain được chọn không?
- **Smoke test:** application có khởi động và phục vụ endpoint theo cấu hình mong đợi không?
- **Truy vết:** artifact version/checksum đã được kiểm tra và được deploy đúng tệp chưa?
- **Phát hành:** module library publish plain JAR, application publish executable Boot JAR nếu đó là mục tiêu.
- **Không tự suy đoán:** không dựa duy nhất vào `.jar`, `-plain` hoặc kích thước; kiểm tra **manifest + archive layout + runtime behavior**.

**Quy tắc ghi nhớ:** **Plain JAR** thường chỉ mang compiled classes/resources của module, cần classpath đúng nếu ứng dụng có dependency ngoài. **Spring Boot executable JAR** mang application classes trong `BOOT-INF/classes`, dependency JARs trong `BOOT-INF/lib` và Boot `JarLauncher` để `java -jar` chạy được. Một Java JAR đơn giản có `Main-Class` cũng có thể “executable” mà không phải Spring Boot; vì thế luôn nói rõ **kiểu archive cụ thể**.

### Tài liệu chính thức

- Spring Boot 3.3 — Developing Your First Spring Boot Application (Creating an Executable Jar): https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot 3.3.13 API — JarLauncher: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/loader/launch/JarLauncher.html
- Spring Boot — Executable Jar Specification, Launching Executable Jars: https://docs.spring.io/spring-boot/specification/executable-jar/launching.html
- Spring Boot — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/maven-plugin/packaging.html
- Spring Boot — Gradle Plugin, Packaging Executable and Plain Archives: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html
- Oracle JDK 17 — Java launcher: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17 — JAR tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html