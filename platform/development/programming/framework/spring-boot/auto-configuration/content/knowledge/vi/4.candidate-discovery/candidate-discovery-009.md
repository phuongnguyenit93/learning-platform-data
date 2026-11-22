# Kiểm tra tệp đăng ký trong JAR thư viện đã đóng gói

## 1. Mục tiêu và mô hình kiểm tra

Trong Spring Boot, một class được đánh dấu `@AutoConfiguration` chưa chắc được ứng dụng khác phát hiện. Với thư viện được đóng gói thành JAR, Spring Boot 3.x dựa vào tài nguyên có đường dẫn chính xác:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tài nguyên này liệt kê **tên lớp đầy đủ** (fully qualified class name, FQCN) của các auto-configuration ứng viên, mỗi dòng một lớp. Ví dụ:

~~~text
edu.example.greeter.autoconfigure.GreeterAutoConfiguration
~~~

Spring Boot cho phép dùng dấu `#` để ghi chú trong file. Tên lớp lồng nhau, nếu có, dùng tên nhị phân với ký tự `$` giữa lớp ngoài và lớp trong; để tránh nhầm, ví dụ chính dùng lớp top-level.

**Mục tiêu bài học:** tự đóng gói thư viện mẫu, kiểm tra tệp imports trong **JAR thực tế** (không chỉ trong source), đọc nội dung, đối chiếu với `.class` đã biên dịch, kiểm tra JAR là runtime dependency và quan sát bean trong một ứng dụng tiêu thụ. Sau đó kiểm tra trường hợp executable Spring Boot JAR chứa dependency dưới dạng JAR lồng ở `BOOT-INF/lib`.

Ba câu hỏi phải được trả lời bằng ba loại bằng chứng khác nhau:

| Câu hỏi | Bằng chứng |
| --- | --- |
| Thư viện đã phát hành tên class ứng viên chưa? | Entry `AutoConfiguration.imports` trong JAR và nội dung FQCN |
| Spring Boot có thể nạp class trên runtime classpath không? | Class tương ứng và dependency có trong artifact/classpath thật |
| Bean tự động có được tạo trong lần chạy cụ thể không? | Condition Evaluation Report và `ApplicationContext` |

Luồng khái niệm:

~~~text
src/main/resources/META-INF/spring/...AutoConfiguration.imports
    |
    v
Build/publish -> library.jar có tài nguyên + class tương ứng
    |
    v
Ứng dụng thêm library.jar vào runtime classpath
    |
    v
@EnableAutoConfiguration đọc danh sách ứng viên từ các JAR
    |
    v
Lọc exclusions, conditions của cấu hình/phương thức bean
    |
    v
BeanDefinition và instance bean thực sự trong ApplicationContext
~~~

**Có file imports không đồng nghĩa bean chắc chắn xuất hiện.** Một auto-configuration vẫn có thể bị loại trừ hoặc không đạt `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`. Ngược lại, bean xuất hiện có thể do người dùng tự khai báo, không nhất thiết do auto-configuration.

## 2. Tên và vị trí file phải chính xác

Trong dự án thư viện Maven hoặc Gradle theo cấu trúc chuẩn:

~~~text
greeter-autoconfigure/
├── pom.xml
└── src/main/
    ├── java/
    │   └── edu/example/greeter/autoconfigure/
    │       └── GreeterAutoConfiguration.java
    └── resources/
        └── META-INF/
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Sau khi đóng gói thành **plain library JAR**, đường dẫn entry nằm ở **gốc JAR**:

~~~text
greeter-autoconfigure-1.0.0.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── edu/example/greeter/autoconfigure/
    └── GreeterAutoConfiguration.class
~~~

Không đặt file ở `META-INF/` mà thiếu thư mục `spring/`. Không thêm đuôi `.txt` hoặc `.properties`. Không đặt prefix `src/main/resources` ở bên trong archive. Tên tài nguyên phân biệt chữ hoa/chữ thường trong JAR.

Trong Boot 3.x, cơ chế đăng ký này khác với entry `org.springframework.boot.autoconfigure.EnableAutoConfiguration` kiểu cũ trong `META-INF/spring.factories`. Tệp `spring.factories` vẫn có thể cần cho các SPI khác; đừng xóa hàng loạt. Cũng không nhầm:

- `META-INF/spring-autoconfigure-metadata.properties`: metadata do annotation processor tạo để Boot lọc điều kiện sớm hiệu quả hơn; không thay tệp imports.
- `META-INF/spring-configuration-metadata.json`: metadata configuration properties phục vụ IDE và công cụ cấu hình; không liệt kê ứng viên auto-configuration.
- `META-INF/services/...`: tài nguyên cho `ServiceLoader` và SPI khác; không phải file này.

## 3. Ví dụ thư viện Spring Boot 3.3 / Java 17

Chúng ta dùng hai dự án Maven độc lập. Thư viện tạo **JAR thường**; ứng dụng tiêu thụ tạo **executable Spring Boot JAR**. Yêu cầu: JDK 17+, Maven 3.9+ và có thể tải dependency Maven.

~~~text
inspection-demo/
├── greeter-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/edu/example/greeter/
│       │   ├── api/Greeter.java
│       │   └── autoconfigure/GreeterAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── greeter-consumer/
    ├── pom.xml
    └── src/main/java/edu/example/app/
        └── DemoApplication.java
~~~

### 3.1. POM cho thư viện

File `greeter-autoconfigure/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <groupId>edu.example</groupId>
    <artifactId>greeter-autoconfigure</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-autoconfigure` cung cấp annotation `@AutoConfiguration` và các điều kiện của Boot. Thư viện này **không cần** `spring-boot-starter-web`, và không dùng `spring-boot-maven-plugin` để đóng gói lại thành JAR chạy được. Một thư viện auto-configuration nên được xuất bản dưới dạng classpath JAR thông thường.

### 3.2. Kiểu dịch vụ

File `greeter-autoconfigure/src/main/java/edu/example/greeter/api/Greeter.java`:

~~~java
package edu.example.greeter.api;

public interface Greeter {
    String message();
}
~~~

### 3.3. Lớp cấu hình tự động

File `greeter-autoconfigure/src/main/java/edu/example/greeter/autoconfigure/GreeterAutoConfiguration.java`:

~~~java
package edu.example.greeter.autoconfigure;

import edu.example.greeter.api.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "demo.greeter",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreeterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    public Greeter libraryGreeter() {
        return () -> "library";
    }
}
~~~

Cấu hình trên cung cấp bean mặc định kiểu `Greeter`. Nếu không có `demo.greeter.enabled`, cấu hình vẫn hợp lệ do `matchIfMissing=true`. Nếu ứng dụng đã có bean kiểu `Greeter`, `@ConditionalOnMissingBean` khiến bean mặc định nhường chỗ.

Annotation trên lớp Java **chưa đủ để Boot tự tìm thấy lớp**. Còn phải tạo file imports.

### 3.4. Tệp đăng ký ứng viên

File `greeter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` chỉ gồm:

~~~text
edu.example.greeter.autoconfigure.GreeterAutoConfiguration
~~~

Tên trong imports là FQCN **không kèm `.class`**, không có dấu `/`. Một file imports có thể liệt kê nhiều lớp, mỗi lớp một dòng. Nên để các class auto-configuration ngoài package mà ứng dụng tiêu thụ component scan, để việc nạp của chúng thực sự đến từ cơ chế auto-configuration.

## 4. Đóng gói thư viện và kiểm tra mục lục JAR

Trong thư mục `greeter-autoconfigure`:

~~~bash
java -version
mvn -version
mvn -q clean install
~~~

`mvn install` biên dịch, đóng gói và cài artifact vào Maven local repository, giúp ứng dụng consumer tham chiếu. Đây không phải hành động publish lên Maven Central.

File sẽ có đường dẫn:

~~~text
target/greeter-autoconfigure-1.0.0.jar
~~~

### 4.1. Liệt kê các entry bằng công cụ `jar` của JDK

~~~bash
jar tf target/greeter-autoconfigure-1.0.0.jar
~~~

`jar tf` chỉ **liệt kê entry**, không in nội dung của file. Trong output dài, kiểm tra ít nhất hai entry:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
edu/example/greeter/autoconfigure/GreeterAutoConfiguration.class
~~~

Đây là **hai dòng cần có**, không phải toàn bộ stdout. JAR còn có manifest, metadata Maven và các class khác.

Lọc trên Linux/macOS:

~~~bash
jar tf target/greeter-autoconfigure-1.0.0.jar |
  grep -F 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
~~~

Lọc trên PowerShell (Windows):

~~~powershell
jar tf .\target\greeter-autoconfigure-1.0.0.jar |
  Select-String -SimpleMatch 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
~~~

Nếu không thấy file, hãy kiểm tra lại `src/main/resources` và quy tắc copy resources khi build. Việc file hiện diện trong IDE chưa chứng minh nó được chép vào archive phát hành.

### 4.2. Đọc nội dung imports trong JAR

Nếu có `unzip` trên Linux/macOS:

~~~bash
unzip -p target/greeter-autoconfigure-1.0.0.jar \
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung mong đợi:

~~~text
edu.example.greeter.autoconfigure.GreeterAutoConfiguration
~~~

Tùy chọn chỉ dùng JDK, giải nén một entry vào thư mục riêng:

~~~bash
mkdir -p inspect-jar
cd inspect-jar
jar xf ../target/greeter-autoconfigure-1.0.0.jar \
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
cat META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
cd ..
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory .\inspect-jar -Force | Out-Null
Push-Location .\inspect-jar
jar xf ..\target\greeter-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
Get-Content .\META-INF\spring\org.springframework.boot.autoconfigure.AutoConfiguration.imports
Pop-Location
~~~

Làm trong thư mục riêng để không giải nén `META-INF` lẫn vào mã nguồn hiện có.

### 4.3. Đối chiếu FQCN với class đã biên dịch

FQCN trong imports sử dụng dấu chấm. Entry `.class` trong JAR sử dụng dấu gạch chéo:

~~~text
imports: edu.example.greeter.autoconfigure.GreeterAutoConfiguration
class:   edu/example/greeter/autoconfigure/GreeterAutoConfiguration.class
~~~

Có file imports nhưng thiếu class tương ứng là dấu hiệu phải kiểm tra build, tên package, version hoặc nơi class thực sự được phân phối. Với ví dụ này, class được chứa trong cùng JAR. Với thư viện thực tế, một imports có thể tham chiếu kiểu ở dependency khác; phải bảo đảm dependency cần thiết được phân phối phù hợp.

## 5. Kiểm tra JAR bằng một chương trình Java thuần

Nếu không có lệnh `unzip`, có thể dùng `java.util.jar.JarFile`. Đây là chương trình **độc lập, chạy bằng JDK 17**, không cần thêm thư viện nào.

Tạo `InspectImports.java` ở thư mục project thư viện:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

public class InspectImports {
    private static final String PATH =
        "META-INF/spring/" +
        "org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java InspectImports.java <jar-file>");
            System.exit(1);
        }

        try (JarFile jar = new JarFile(args[0])) {
            JarEntry entry = jar.getJarEntry(PATH);
            if (entry == null) {
                System.err.println("MISSING: " + PATH);
                System.exit(2);
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                        jar.getInputStream(entry), StandardCharsets.UTF_8))) {
                System.out.println("FOUND: " + PATH);
                reader.lines().forEach(System.out::println);
            }
        }
    }
}
~~~

Chạy:

~~~bash
java InspectImports.java target/greeter-autoconfigure-1.0.0.jar
~~~

Kết quả khi JAR đúng:

~~~text
FOUND: META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
edu.example.greeter.autoconfigure.GreeterAutoConfiguration
~~~

Nếu không có entry, chương trình in `MISSING: ...` ra stderr và thoát với mã `2`. Điều này phù hợp đưa vào kiểm tra build. `JarFile` chỉ mở archive được chỉ định; với executable JAR có dependency lồng nhau cần trích xuất thư viện trước, xem mục 8.

## 6. Dùng thư viện trong ứng dụng consumer

Để chứng minh file imports có tác dụng, tạo ứng dụng Spring Boot thứ hai.

File `greeter-consumer/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>edu.example</groupId>
    <artifactId>greeter-consumer</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>edu.example</groupId>
            <artifactId>greeter-autoconfigure</artifactId>
            <version>1.0.0</version>
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
~~~

Tạo `greeter-consumer/src/main/java/edu/example/app/DemoApplication.java`:

~~~java
package edu.example.app;

import edu.example.greeter.api.Greeter;
import java.util.Arrays;
import org.springframework.boot.Banner;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    @Bean
    @ConditionalOnProperty(
        name = "demo.override",
        havingValue = "true"
    )
    Greeter userGreeter() {
        return () -> "user";
    }

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 new SpringApplicationBuilder(DemoApplication.class)
                     .web(WebApplicationType.NONE)
                     .bannerMode(Banner.Mode.OFF)
                     .run(args)) {
            String[] names =
                context.getBeanNamesForType(Greeter.class);
            Arrays.sort(names);

            Greeter greeter =
                context.getBeanProvider(Greeter.class).getIfAvailable();

            System.out.println("greeterBeans=" +
                Arrays.toString(names));
            System.out.println("message=" +
                (greeter == null ? "none" : greeter.message()));
        }
    }
}
~~~

Cơ chế trong demo:

- Main class ở `edu.example.app`, class auto-configuration ở `edu.example.greeter.autoconfigure` nên không bị component scan từ main class quét.
- `WebApplicationType.NONE` tắt việc tạo web application context, tránh cần HTTP server; auto-configuration vẫn hoạt động.
- Mặc định class auto-configuration cung cấp `libraryGreeter`.
- Khi `demo.override=true`, ứng dụng cung cấp bean `userGreeter` khiến mặc định nhường chỗ do `@ConditionalOnMissingBean`.
- Khi `demo.greeter.enabled=false`, điều kiện class auto-config không khớp; bean mặc định vắng mặt.

### 6.1. Chạy và xem bean thực tế

Sau khi đã `mvn -q clean install` trong thư viện, từ thư mục consumer chạy:

~~~bash
mvn -q spring-boot:run
~~~

Hai dòng do chương trình in ra:

~~~text
greeterBeans=[libraryGreeter]
message=library
~~~

Có thể có thêm log Spring Boot; đây là hai dòng `System.out.println` từ main, không phải toàn bộ stdout/stderr.

Cho người dùng tự khai báo bean:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.override=true
~~~

Kết quả:

~~~text
greeterBeans=[userGreeter]
message=user
~~~

Tắt điều kiện property của auto-configuration:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.greeter.enabled=false
~~~

Kết quả:

~~~text
greeterBeans=[]
message=none
~~~

Loại trừ auto-configuration bằng tên:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.autoconfigure.exclude=edu.example.greeter.autoconfigure.GreeterAutoConfiguration
~~~

Kết quả:

~~~text
greeterBeans=[]
message=none
~~~

Hai trường hợp cuối giống nhau ở tập bean nhưng **khác nguyên nhân**: một trường hợp không khớp condition; trường hợp kia bị exclude khỏi tập cấu hình cần xử lý.

### 6.2. Quan sát vì sao điều kiện khớp hoặc không khớp

Bật `--debug`:

~~~bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Tìm `GreeterAutoConfiguration` và `libraryGreeter` trong *Condition Evaluation Report*. Nếu bật `--demo.override=true` cùng `--debug`, class có thể khớp ở mức property, còn điều kiện `@ConditionalOnMissingBean` trên method không khớp do bean người dùng có mặt.

Báo cáo điều kiện trả lời câu hỏi **vì sao cấu hình hoặc method được chấp nhận/bỏ qua**. Kiểm tra `ApplicationContext` trả lời câu hỏi **bean nào đang tồn tại**. Cả hai không thể thay cho việc kiểm tra file imports trong artifact.

## 7. Executable Spring Boot JAR chứa thư viện ở đâu?

Một JAR thư viện thuần có tệp imports tại root `META-INF/spring/...`. Nhưng ứng dụng đóng gói bằng `spring-boot-maven-plugin` thường có dạng:

~~~text
greeter-consumer-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/edu/example/app/DemoApplication.class
    └── lib/
        ├── greeter-autoconfigure-1.0.0.jar
        ├── spring-boot-....jar
        └── ...
~~~

Khi đó, file imports của thư viện **không bắt buộc xuất hiện tại root của JAR ngoài**. Nó nằm trong **JAR lồng** ở `BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar`. Công cụ `jar tf` bình thường chỉ liệt kê entry của archive đang mở, không tự liệt kê toàn bộ tệp bên trong các JAR con.

Spring Boot Loader hỗ trợ nạp nested JAR khi chạy executable bằng `java -jar`. Vì vậy **không thấy file imports ở root của executable JAR** chưa phải bằng chứng thư viện thiếu đăng ký.

## 8. Kiểm tra imports của nested JAR trong ứng dụng đóng gói

Trong thư mục `greeter-consumer`:

~~~bash
mvn -q clean package
jar tf target/greeter-consumer-1.0.0.jar
~~~

Trên Linux/macOS, tìm dependency JAR:

~~~bash
jar tf target/greeter-consumer-1.0.0.jar |
  grep -F 'BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar'
~~~

Trên PowerShell:

~~~powershell
jar tf .\target\greeter-consumer-1.0.0.jar |
  Select-String -SimpleMatch 'BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar'
~~~

Dòng dự kiến:

~~~text
BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar
~~~

Trích xuất JAR thư viện, rồi mở **JAR con**. Linux/macOS:

~~~bash
mkdir -p inspect-executable
cd inspect-executable
jar xf ../target/greeter-consumer-1.0.0.jar \
  BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar
jar tf BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar |
  grep -F 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
unzip -p BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar \
  META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
cd ..
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory .\inspect-executable -Force | Out-Null
Push-Location .\inspect-executable
jar xf ..\target\greeter-consumer-1.0.0.jar BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar
jar tf .\BOOT-INF\lib\greeter-autoconfigure-1.0.0.jar |
  Select-String -SimpleMatch 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
jar xf .\BOOT-INF\lib\greeter-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
Get-Content .\META-INF\spring\org.springframework.boot.autoconfigure.AutoConfiguration.imports
Pop-Location
~~~

Nội dung đọc từ JAR lồng vẫn là:

~~~text
edu.example.greeter.autoconfigure.GreeterAutoConfiguration
~~~

Cuối cùng, từ thư mục consumer chạy:

~~~bash
java -jar target/greeter-consumer-1.0.0.jar
~~~

Hai dòng ứng dụng sẽ in:

~~~text
greeterBeans=[libraryGreeter]
message=library
~~~

Nếu `mvn spring-boot:run` hoạt động còn `java -jar` không hoạt động, hãy kiểm tra version của JAR lồng, cách plugin đóng gói executable và dependency runtime. Có thể hai lần chạy dùng artifact khác nhau.

### Không nhầm các loại JAR

| Loại | Nơi cần tìm imports của thư viện |
| --- | --- |
| Plain JAR thư viện | `META-INF/spring/...AutoConfiguration.imports` ngay tại gốc JAR |
| Boot executable JAR | Mở dependency trong `BOOT-INF/lib/*.jar`, rồi tìm entry tại root của dependency JAR |
| Boot executable WAR | Dependency thường ở `WEB-INF/lib` hoặc `WEB-INF/lib-provided` |
| Shaded/uber JAR gộp nhiều thư viện | Kiểm tra entry imports sau gộp; cần bảo đảm các tài nguyên trùng đường dẫn không bị ghi đè, mất tên lớp |

Không nên đóng gói auto-configuration library thành một executable Boot JAR có class ở `BOOT-INF/classes` rồi mong người tiêu thụ dùng nó như classpath JAR thường. Các cơ chế tải class/resource có bố cục khác nhau.

## 9. Các lỗi thường gặp và quy trình xử lý

### 9.1. Có file trong source nhưng thiếu trong JAR

Kiểm tra `src/main/resources`, cấu hình Maven/Gradle resources, source set đúng, plugin đóng gói và artifact cuối. Có thể xem `target/classes` như bằng chứng trung gian, nhưng kết luận phải dựa vào **JAR phát hành**.

### 9.2. File imports có, nhưng sai FQCN

Đối chiếu từng dòng với class thực tế: `edu.example.greeter.autoconfigure.GreeterAutoConfiguration` tương ứng với `edu/example/greeter/autoconfigure/GreeterAutoConfiguration.class`. Khi đổi tên/move class, cập nhật imports rồi build lại. Nếu class phụ thuộc vào kiểu không có trên runtime classpath, ứng dụng vẫn có thể lỗi khi nạp hoặc xử lý cấu hình.

### 9.3. Class có mặt nhưng bean không có

Không vội sửa packaging. Xem điều kiện `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnMissingBean`, exclusion, bean người dùng và lỗi tạo bean. Dùng `--debug` và `ApplicationContext` để xác định bước nào làm bean vắng mặt.

### 9.4. Chỉ tìm trong executable JAR ngoài

`jar tf app.jar` cho thấy `BOOT-INF/lib/greeter-autoconfigure-1.0.0.jar` nhưng không liệt kê từng entry bên trong JAR con. Trích xuất dependency rồi kiểm tra JAR con như mục 8. Không kết luận thiếu file chỉ vì không thấy nó ở gốc archive ngoài.

### 9.5. Dùng lại bản build cũ

Bản source đã đổi nhưng local Maven repository, Gradle cache, dependency version hoặc executable JAR vẫn dùng bản cũ. Xác minh tên/version và artifact thực tế. Trong bài thực hành, sau khi sửa thư viện chạy lại `mvn -q clean install`, rồi build lại consumer.

### 9.6. Shading làm mất resource

Khi gộp nhiều JAR thành một bằng shading plugin, các thư viện có thể cùng chứa đường dẫn `AutoConfiguration.imports`. Nếu quá trình merge chỉ giữ một entry, danh sách class từ các thư viện khác sẽ mất. Cần cấu hình resource transformer phù hợp và kiểm tra **nội dung file sau khi shade** có đủ tên class.

### 9.7. Đổi tên auto-configuration đã phát hành

Ngoài sửa imports trong bản mới, Spring Boot còn hỗ trợ `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` để thể hiện việc thay tên class khi có liên quan đến thứ tự `before/after` và exclusion cũ. Đây là tình huống tương thích thư viện nâng cao, không bắt buộc trong thí nghiệm một class.

### 9.8. Nhầm tệp metadata

`spring-autoconfigure-metadata.properties` là metadata tối ưu lọc điều kiện; `spring-configuration-metadata.json` mô tả properties; `spring.factories` còn được dùng cho một số SPI. Không tệp nào thay thế đường dẫn chính `AutoConfiguration.imports` trong Boot 3.x.

## 10. Checklist kiểm tra artifact trước khi phát hành

| Bước | Cần xác minh | Bằng chứng |
| --- | --- | --- |
| 1 | Đúng JAR, đúng version | Tên artifact, Maven/Gradle dependency coordinates |
| 2 | Đúng loại đóng gói | Plain dependency JAR hay Boot executable JAR |
| 3 | Imports đúng đường dẫn và có trong artifact | `jar tf` hoặc `JarFile.getJarEntry` |
| 4 | Nội dung FQCN đúng và đầy đủ | `jar xf`, `unzip -p` hoặc `InspectImports.java` |
| 5 | Class/dependency có thể nạp | Entry `.class` và dependency runtime |
| 6 | Consumer đang dùng artifact đó | Dependency graph, `BOOT-INF/lib` nếu đóng gói Boot |
| 7 | Class auto-config không bị scan nhầm | Package riêng và phạm vi component scan |
| 8 | Conditions khớp theo kịch bản | Condition Evaluation Report |
| 9 | Bean có hoặc vắng mặt đúng ý | `getBeanNamesForType`, `containsBean`, injection thực tế |

Trong CI có thể tối thiểu kiểm tra sau build:

~~~bash
mvn -q clean package
jar tf target/greeter-autoconfigure-1.0.0.jar |
  grep -F 'META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports'
~~~

Đoạn trên dành cho Unix. Trên Windows dùng `Select-String`; để kiểm tra thoát lỗi khi thiếu entry trên mọi OS, có thể dùng chương trình `InspectImports.java` ở mục 5 (mã thoát `2` nếu không có entry).

## 11. Tự luyện tập và kiểm chứng

1. **Bỏ file imports:** xóa tài nguyên đăng ký trong project thư viện, chạy lại `mvn -q clean install` và consumer. Giải thích vì sao code vẫn biên dịch nhưng bean `libraryGreeter` không còn được nhập tự động. Khôi phục file sau thử nghiệm.
2. **Đổi FQCN trong imports:** cố ý viết sai tên class và build lại. Kiểm tra nội dung JAR, class entry và lỗi startup. Phân biệt lỗi tên class với lỗi điều kiện.
3. **Tắt bean bằng property:** giữ JAR đúng, chạy `--demo.greeter.enabled=false` rồi bật `--debug`. Tại sao imports vẫn tồn tại nhưng không có bean?
4. **Ưu tiên bean người dùng:** chạy `--demo.override=true`; chứng minh class vẫn được xem xét, nhưng method `libraryGreeter` không tạo bean mặc định.
5. **Thử exclusion:** chạy tham số `spring.autoconfigure.exclude` rồi so với `demo.greeter.enabled=false`. Cùng thiếu bean nhưng hai đường xử lý có gì khác nhau?
6. **Mở nested JAR:** build consumer bằng `mvn -q clean package`, kiểm tra `BOOT-INF/lib`, trích xuất JAR thư viện rồi đọc file imports; so với JAR thư viện độc lập.
7. **So artifact cũ và mới:** thay đổi imports, build/cài lại thư viện, nhưng chưa build lại executable consumer. Đối chiếu version/timestamp và chỉ ra tại sao cần kiểm tra artifact cuối.
8. **Thử hai ứng viên:** thêm một class `@AutoConfiguration` khác và một dòng FQCN vào imports. Kiểm tra cả hai dòng được đóng gói; xem các condition trong report.

### Câu hỏi tự đánh giá

- Tên tệp imports chính xác trong Spring Boot 3.x là gì?
- Vì sao cần kiểm tra **JAR đóng gói** thay vì chỉ nhìn `src/main/resources`?
- `jar tf` khác `jar xf` và `unzip -p` ở đâu?
- Dấu chấm trong FQCN biến thành dạng nào khi đối chiếu với đường dẫn `.class`?
- Vì sao không thấy imports ở root executable JAR vẫn có thể là kết quả đúng?
- Tệp imports chứng minh được điều gì về ứng viên, và không chứng minh được điều gì về bean?
- Khi nào cần xem Condition Evaluation Report?
- Khi shade nhiều thư viện, vì sao tài nguyên trùng đường dẫn có thể mất?

**Tiêu chí hoàn thành:** từ một JAR thư viện thực tế, bạn tự tìm được entry `AutoConfiguration.imports`, đọc FQCN và đối chiếu với class; kiểm tra JAR đã hiện diện trên runtime classpath; thử ứng dụng tiêu thụ để giải thích đúng cả trường hợp có bean và trường hợp bean bị điều kiện ngăn.

## 12. Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html)
- [Spring Boot 3.3 — Nested JARs](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html)
- [Spring Boot 3.3 — Maven Plugin packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [JDK 17 — jar tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html)
