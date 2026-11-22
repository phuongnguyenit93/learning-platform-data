# Chọn bộ phiên bản tương thích giữa Java, Spring Boot và Spring Security

Khi bắt đầu một dự án Spring Security, câu hỏi đầu tiên thường là: “Dùng Java bao nhiêu, Spring Boot phiên bản nào và Spring Security phiên bản nào?” Ba con số này **không được chọn độc lập**. Một ứng dụng có thể dùng JDK rất mới nhưng vẫn không khởi động vì Spring Boot không hỗ trợ phiên bản đó; cũng có thể biên dịch thành công nhưng lỗi `NoSuchMethodError` vì vô tình trộn nhiều phiên bản Spring khác nhau.

Mục tiêu của bài là biết **chọn một bộ phiên bản đã được kiểm chứng**, tạo dự án có thể chạy, đọc được dependency tree, và biết khi nào cần nâng cấp. Tư duy quan trọng nhất: **chọn bản Spring Boot phù hợp, để Spring Boot quản lý phiên bản Spring Framework và Spring Security, rồi chọn JDK và build tool nằm trong phạm vi Boot hỗ trợ**.

Thông tin phiên bản cụ thể được đối chiếu với tài liệu chính thức ở thời điểm **04/11/2026**. Phiên bản bản vá và trạng thái hỗ trợ sẽ thay đổi, vì thế quy trình xác minh phía dưới quan trọng hơn việc ghi nhớ một con số.

## 1. Ba lớp phiên bản có vai trò khác nhau

| Thành phần | Nó quyết định điều gì? | Bạn chọn trực tiếp ở đâu? |
| --- | --- | --- |
| **Java/JDK** | Ngôn ngữ, trình biên dịch, JVM chạy ứng dụng và khả năng tương thích bytecode | Cài JDK, cấu hình Java toolchain và `java.version` hoặc `maven.compiler.release` |
| **Spring Boot** | Nền tảng tạo ứng dụng, auto-configuration, starter, plugin đóng gói, dependency management/BOM | `spring-boot-starter-parent` hoặc phiên bản plugin/BOM Spring Boot |
| **Spring Security** | Thư viện xác thực, phân quyền, security filter chain, OAuth2, bảo vệ request... | Thường **không ghi phiên bản riêng** khi dùng starter do Boot quản lý |

Còn một lớp quan trọng ở giữa là **Spring Framework**: Boot có một dải Framework thích hợp; Spring Security cũng phụ thuộc các module Framework. Thường bạn không cần tự chọn phiên bản Framework nếu đang dùng Boot đúng cách.

Một bộ hợp lệ phải thỏa **đồng thời**:

~~~text
JDK dùng để build/chạy được Boot hỗ trợ
          AND
Spring Framework tương thích với Boot
          AND
Spring Security tương thích với Framework và Boot
          AND
Build tool/plugin phù hợp
          AND
Các thư viện bổ sung (nếu có) không phá vỡ bộ dependency
~~~

Đừng kiểm tra chỉ mỗi `java -version` rồi coi như đã chứng minh toàn bộ hệ thống tương thích.

## 2. Hai bộ tham chiếu đã được công bố

Theo tài liệu chính thức tra cứu ngày 04/11/2026:

| Mục | Bộ Spring Boot 3.5 | Bộ Spring Boot 4.1 |
| --- | --- | --- |
| Spring Boot tham chiếu | **3.5.16** | **4.1.2** |
| Spring Security được BOM của Boot quản lý | **6.5.11** | **7.1.2** |
| Spring Framework | Nhánh **6.2**, yêu cầu ít nhất **6.2.19** | Nhánh **7.0**, yêu cầu ít nhất **7.0.10** |
| Java tối thiểu | **17** | **17** |
| Java được tài liệu Boot nêu là tương thích đến | **25** | **27** |
| Maven | **3.6.3+** | **3.6.3+** |
| Gradle được nêu hỗ trợ | **7.6.4+ thuộc nhánh 7.x** hoặc **8.4+ thuộc nhánh 8.x** | **8.14+ thuộc nhánh 8.x** hoặc **9.x** |
| Web MVC starter dùng trong ví dụ | `spring-boot-starter-web` | `spring-boot-starter-webmvc` |
| Security starter cơ bản | `spring-boot-starter-security` | `spring-boot-starter-security` |

Đây là **hai tổ hợp mẫu có cơ sở từ BOM và System Requirements**, không phải bảng tuyên bố mọi phiên bản 3.x/4.x đều tự tương thích với mọi bản 6.x/7.x. Bản vá Boot có thể đổi phiên bản Security mà nó quản lý; muốn biết chính xác, đọc **Managed Dependency Coordinates** của **đúng bản Boot dự định dùng**.

Các nguồn tra cứu bảng:

- Spring Boot 4.1 — [System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) và [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html).
- Spring Boot 3.5 — [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html) và [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html).
- Spring Security — [Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html).

**Bản mới nhất không mặc nhiên phù hợp mọi hệ thống.** Nếu dự án hiện chạy ổn với Boot 3.5 và phụ thuộc thư viện chỉ hỗ trợ Framework 6, không được nâng Security lên 7 tùy tiện. Ngược lại, dự án mới muốn dùng Boot 4 cần kiểm tra các starter, Java/Jakarta, plugin và thư viện khác.

### Stable, preview và snapshot khác nhau

Ở ngày đối chiếu, nhánh Boot **4.2.0-RC1** và Security **7.2.0-RC1** là bản phát hành ứng viên (*release candidate*), không phải những bản ổn định được chọn cho ví dụ. Bản `SNAPSHOT` còn thay đổi thường xuyên. Với bài thực hành, CI hoặc production, nên chọn **bản stable đã phát hành**, rồi cập nhật patch có kiểm thử.

Ký hiệu `4.1.2` gồm major/minor/patch. Việc tăng patch thường an toàn hơn việc đổi major nhưng vẫn cần chạy test và kiểm tra release notes, nhất là với thư viện bảo mật có bản vá CVE.

## 3. Quy trình ra quyết định từ con số 0

### Bước 1 — Xác định ràng buộc của dự án

Trả lời trước các câu hỏi:

1. Đây là dự án **mới** hay hệ thống **đang bảo trì**?
2. Production có thể chạy JDK nào? JDK 17, 21 hoặc 25? Có bắt buộc phiên bản vì môi trường triển khai?
3. Ứng dụng dùng **Spring MVC/Servlet** hay **WebFlux/Reactive**?
4. Có phụ thuộc Spring Cloud, Spring Data, thư viện Spring của bên thứ ba, máy chủ ứng dụng bên ngoài, Jakarta API hay GraalVM không?
5. CI, Docker image và máy chạy thật có thể dùng Maven/Gradle phiên bản nào?
6. Bản được chọn còn nhận cập nhật và bản vá bảo mật theo yêu cầu dự án không?

Khi không có ràng buộc đặc biệt và bắt đầu dự án mới, Java **21 LTS** là một lựa chọn thực dụng để học: đủ mới cho nhiều tính năng Java và được cả hai bộ tham chiếu ở trên hỗ trợ. Java 17 vẫn là mức tối thiểu mà hai nhánh Boot này công bố; Java 25 cũng có thể phù hợp khi hạ tầng và các thư viện khác đã được thử nghiệm. Không có lý do phải chạy Java 27 chỉ vì Boot 4.1 liệt kê khả năng tương thích đến phiên bản đó.

### Bước 2 — Chọn một nhánh Spring Boot stable

- **Dự án mới và thư viện đã hỗ trợ hệ sinh thái Spring Framework 7:** có thể chọn Boot 4.1.2.
- **Dự án cần duy trì cách dùng Spring Framework 6 và phụ thuộc tương ứng:** có thể chọn Boot 3.5.16, đồng thời kiểm tra thời hạn hỗ trợ, bản vá và kế hoạch nâng cấp.
- **Hệ thống cũ dùng Java 8 hoặc 11:** không thể nâng nguyên trạng đến hai bộ tham chiếu trên, vì cả hai yêu cầu Java 17 trở lên. Cần kế hoạch nâng JDK và cập nhật mã/thư viện trước.
- **Có Spring Cloud:** phải chọn release train của Cloud tương thích với nhánh Boot đang dùng, theo bảng tương thích chính thức của Spring Cloud. BOM của Boot không thay thế bước này.

Đừng chọn một Security release cao nhất trên Maven Central rồi mới tìm cách ép Boot chạy theo. Với Boot, nên bắt đầu từ **một platform/BOM** rõ ràng.

### Bước 3 — Tra System Requirements của đúng nhánh

Đối chiếu **Java tối thiểu/tối đa đã kiểm thử**, Maven/Gradle, Spring Framework và các giới hạn phụ. Ví dụ Boot 4.1.2 yêu cầu Java 17+ và công bố tương thích đến Java 27, nhưng Gradle phải là 8.14+ trong nhánh 8 hoặc nhánh 9.x. Một Gradle 8.5 cũ hơn **không đáp ứng** yêu cầu build của Boot 4.1.2, dù JDK đã là 21.

“Có thể chạy ở một máy” chưa đủ để kết luận là **tổ hợp được hỗ trợ**. Phiên bản Java, hệ điều hành, framework, JVM flags, container và plugin ảnh hưởng tới kết quả.

### Bước 4 — Tra Boot BOM và giữ nguyên phiên bản Security được quản lý

Spring Boot cung cấp Bill of Materials (`spring-boot-dependencies`) ghi các version đã được tuyển chọn. Các starter Boot (trong đó có `spring-boot-starter-security`) nhận phiên bản từ **parent/BOM**. Nếu bạn dùng đúng cơ chế dependency management, không cần ghi `<version>` cho Spring Security module.

Ví dụ:

~~~text
Spring Boot 4.1.2
  -> BOM Boot 4.1.2
      -> Spring Security 7.1.2
      -> Spring Framework 7.0.x tương ứng
      -> các thư viện hỗ trợ khác trong tập quản lý
~~~

Đây là quan hệ phiên bản, không phải sơ đồ gọi hàm lúc runtime. Boot BOM giúp thống nhất các module; nó không tự chứng minh mọi dependency bên ngoài đều phù hợp.

### Bước 5 — Tạo dự án, build và chạy kiểm thử

Bắt đầu bằng [Spring Initializr](https://start.spring.io/) hoặc POM/Gradle có platform rõ ràng. Build và chạy bằng **JDK thực tế của CI/production**, không chỉ JDK của IDE. Kiểm tra dependency graph xem Security và Framework thực sự được resolve ra phiên bản nào, rồi smoke-test endpoint bảo mật.

## 4. Ví dụ Maven hoàn chỉnh: Java 21 + Boot 4.1.2 + Security do BOM quản lý

Đây là một dự án servlet rất nhỏ. Mục tiêu của mã nguồn chỉ là chứng minh **bộ dependency được chọn có thể build và khởi động**, và một endpoint có thể truy cập với chính sách Spring Security. Không triển khai login/authorization nghiệp vụ đầy đủ.

Tạo cấu trúc:

~~~text
compatibility-lab/
  pom.xml
  src/
    main/
      java/
        com/
          example/
            compatibility/
              CompatibilityApplication.java
~~~

Nội dung `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>compatibility-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
~~~

**Điều cần quan sát:** POM chỉ nêu phiên bản Boot ở `<parent>`. Không có dòng nào ghi cứng `spring-security-core=7.1.2`, `spring-security-web=7.1.2` hoặc phiên bản Spring Framework. Parent quản lý các dependency này; bạn chỉ chọn *starter* phù hợp.

Tạo tệp `src/main/java/com/example/compatibility/CompatibilityApplication.java`:

~~~java
package com.example.compatibility;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CompatibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(CompatibilityApplication.class, args);
    }

    @GetMapping("/status")
    public String status() {
        return "compatible";
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/status").permitAll()
                .anyRequest().authenticated());
        return http.build();
    }
}
~~~

Đoạn trên sử dụng API cấu hình Java hiện đại: tạo `SecurityFilterChain` thay vì dựa vào `WebSecurityConfigurerAdapter` đã bị loại bỏ ở các nhánh mới. Đây là chương trình ứng dụng Spring Boot **đầy đủ về class chính**, không yêu cầu một cơ sở dữ liệu hay controller khác để trả endpoint `/status`.

Yêu cầu trước khi chạy: đã cài JDK 21, Maven phù hợp, Maven Central truy cập được lần đầu để lấy dependency.

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Trong terminal thứ hai, gọi:

~~~bash
curl -s http://localhost:8080/status
~~~

Nội dung body kỳ vọng:

~~~text
compatible
~~~

Không nên khẳng định toàn bộ log khởi động sẽ giống nhau ở mọi máy; log còn phụ thuộc phiên bản JVM, hệ điều hành và cấu hình. Nếu có ứng dụng khác giữ port 8080, cần đổi port trước khi chạy. Các endpoint ngoài `/status` vẫn đi qua quy tắc `authenticated()`.

**Không đặt mật khẩu đăng nhập cố định vào source chỉ để thử tương thích.** Spring Security có thể tạo người dùng/mật khẩu thử nghiệm theo cấu hình auto-configuration, nhưng việc chứng minh compatibility trong bài này chỉ cần endpoint công khai đã khai báo và dependency graph.

### Kiểm tra đúng Security version trong Maven

Trong thư mục có POM, chạy:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

Tìm các artifact Spring Security như `spring-security-core`, `spring-security-config` và `spring-security-web`. Với bộ Boot 4.1.2 tham chiếu, những module Spring Security được Boot BOM quản lý ở **7.1.2**. Không cần học thuộc từng dòng log; điều đáng kiểm tra là **các module cùng nhánh và không bị một dependency khác kéo phiên bản lạc lõng**.

Bạn cũng có thể xem cấu hình POM được Maven tổng hợp:

~~~bash
mvn help:effective-pom
~~~

Nếu dùng parent Boot đúng, thông tin dependencyManagement trong effective POM sẽ xuất hiện dù bạn không tự viết danh sách này trong POM gốc.

## 5. Ví dụ Gradle: cùng bộ phiên bản với Maven

Gradle dùng cách khai báo khác; quy tắc vẫn giống nhau: chọn Java toolchain, plugin Boot, và **BOM** để các module Spring Security nhận version thống nhất.

Một `build.gradle` mẫu cho cùng ứng dụng Java 21 và Boot 4.1.2:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ở đây `platform(...BOM_COORDINATES)` chủ động nhập BOM vào dependency configurations của Gradle. Nếu dự án dùng plugin `io.spring.dependency-management` theo hướng dẫn Boot, plugin ấy cũng có thể dùng BOM, nhưng cần tránh trộn nhiều cấu hình override không có chủ ý.

**Chọn Gradle wrapper** được Boot 4.1.2 hỗ trợ: nhánh 8.x từ 8.14 trở lên hoặc 9.x. Kiểm tra:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew bootRun
~~~

Trên Windows, dùng `gradlew.bat` thay cho `./gradlew`. Các lệnh giả định wrapper đã được tạo. Nếu không có wrapper, tạo dự án từ Spring Initializr hoặc sinh wrapper bằng Gradle phù hợp.

Lệnh `dependencyInsight` hữu ích khi cần biết **vì sao** một phiên bản được chọn: nó hiển thị quan hệ dependency và các constraint/selection reason theo cấu hình. Quan sát kết quả thực tế quan trọng hơn việc nhìn duy nhất dòng `implementation`.

### Maven parent và Maven BOM khác nhau thế nào?

- Kế thừa `spring-boot-starter-parent`: nhận **dependency management** cùng nhiều cấu hình plugin/build mặc định của Boot.
- Chỉ `import` `spring-boot-dependencies` làm BOM: nhận **quản lý phiên bản dependency**, không tự kế thừa toàn bộ cấu hình plugin của starter parent.
- Gradle: Boot plugin hỗ trợ đóng gói/chạy; việc đồng bộ dependency có thể dùng dependency-management plugin hoặc cơ chế Gradle `platform` rõ ràng. Không mặc định rằng bất kỳ dòng `plugins { id 'org.springframework.boot' }` nào cũng tự áp tất cả BOM constraints trong mọi cách cấu hình.

Nếu công ty yêu cầu dùng parent riêng, có thể nhập Boot BOM qua `dependencyManagement`, nhưng cần quản lý Maven plugin versions và packaging riêng cho đúng.

## 6. Spring Initializr: chọn đúng một lần, kiểm tra nhiều lần

Tại [https://start.spring.io/](https://start.spring.io/), một quy trình thông dụng:

1. Chọn **Maven** hoặc **Gradle**, ngôn ngữ **Java**.
2. Chọn **Spring Boot stable** trong danh sách; với bài này có thể đối chiếu Boot 4.1.2.
3. Chọn **Java 21** và tạo project có JDK tương ứng trên máy.
4. Thêm dependency **Spring Security** và **Spring Web MVC** (tên hiển thị trong giao diện có thể khác theo nhánh).
5. Sinh dự án, giải nén, kiểm tra `pom.xml`/`build.gradle`.
6. Chạy `java -version`, `mvn -version` hoặc wrapper Gradle để xác nhận tool thực tế.
7. Build và kiểm tra dependency graph như ở trên.

Initializr giúp tạo cấu hình có tính nhất quán ở thời điểm sinh project, nhưng **không tự bảo đảm các thư viện bạn thêm về sau luôn tương thích**. Khi copy một dependency từ tutorial cũ vào project, phải xem nó đã được Boot quản lý chưa và liệu nó có buộc đổi phiên bản Spring Framework hay Security không.

Nếu dùng `spring-boot-starter-webflux` cho hệ reactive thay vì Web MVC, bạn phải chọn security configuration theo mô hình WebFlux (`SecurityWebFilterChain`) chứ không bê nguyên `HttpSecurity`/servlet filter vào.

## 7. Những chỗ dễ “lệch phiên bản” dù POM nhìn có vẻ hợp lệ

### 7.1. Khóa phiên bản Security riêng khi đã dùng Boot BOM

Ví dụ cần cảnh giác:

~~~xml
<!-- Không đặt riêng bản này nếu chưa có lý do và kiểm tra tương thích. -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>7.2.0-RC1</version>
</dependency>
~~~

Nếu phần còn lại do Boot 4.1.2 quản lý ở 7.1.2, project có nguy cơ trộn bản 7.2 RC và 7.1 stable. Maven có thể chọn một version dựa vào dependency mediation; việc compile được không chứng minh API và hành vi runtime đồng nhất.

Khi thật sự cần phiên bản Security khác do yêu cầu vá lỗ hổng hoặc tính năng, nên xem hướng dẫn override chính thức, thay đổi **nhất quán toàn bộ module liên quan**, chạy integration tests và cân nhắc nâng lên patch Boot có BOM mới hơn. Không vá một module rời rạc rồi đoán là đủ.

### 7.2. Nâng JDK nhưng không nâng Gradle/Maven/plugin

Có thể `java -version` báo Java 21 nhưng `./gradlew --version` đang dùng JVM khác, wrapper quá cũ hoặc plugin thiếu hỗ trợ. Kiểm tra cả:

~~~bash
java -version
javac -version
mvn -version
./gradlew --version
~~~

Chỉ chạy lệnh phù hợp với build tool được chọn. IDE có thể dùng một JDK để chạy Gradle daemon và một JDK khác để biên dịch; vì vậy cần xem cấu hình IDE, `JAVA_HOME`, Java toolchain và runner của CI.

### 7.3. Trộn namespace và stack giữa major version

Ứng dụng Spring Boot 3+ nằm trong hệ Jakarta EE, sử dụng nhiều API `jakarta.*` thay cho `javax.*` cũ. Spring Boot 4 nâng lên thế hệ Spring Framework 7 và servlet container/API mới hơn. Một thư viện vẫn chỉ phụ thuộc API Servlet cũ hoặc namespace `javax.servlet.*` có thể gây lỗi build/runtime.

Đừng hiểu rằng đổi import là đủ để nâng một ứng dụng lớn: cấu hình plugin, Jakarta API, mã custom Security, thư viện phản xạ, Servlet filters, test và annotation đều có thể cần chỉnh sửa.

### 7.4. Dựa vào tutorial thuộc nhánh khác

Ví dụ tutorial Spring Security 5 dùng `WebSecurityConfigurerAdapter` hoặc `authorizeRequests()`/API cũ. Copy mã như vậy vào Spring Security 7 có thể không biên dịch hoặc có hành vi không mong muốn. Khi học, nên mở tài liệu đúng major version của ứng dụng và chú ý tên API trong ví dụ.

### 7.5. Có bản stable mới nhưng không kiểm tra bảo mật

“Boot 4.1.2” là **ảnh chụp tại một ngày**, không phải lời hứa rằng bản đó luôn mới nhất. Spring phát hành các bản vá Security cho CVE và có thể cập nhật Boot BOM sau đó. Khi đưa dự án lên production, hãy kiểm tra thông báo bảo mật, thời hạn hỗ trợ, scan dependency và kế hoạch cập nhật patch.

## 8. Phân biệt ba kiểu Java version thường bị nhầm

| Khái niệm | Nó là gì? | Ví dụ |
| --- | --- | --- |
| **JDK chạy build tool** | JVM khởi động Maven/Gradle/IDE plugin | Máy CI chạy Maven bằng JDK 21 |
| **Java source/bytecode target** | Phiên bản ngôn ngữ và class file mà compiler tạo ra | `<java.version>21</java.version>` hoặc Gradle toolchain 21 |
| **JVM production** | Máy ảo thật chạy JAR sau deploy | Container image cung cấp Java 21 |

Nếu bytecode biên dịch cho Java 21 rồi chạy trên JVM 17, bạn có thể gặp `UnsupportedClassVersionError`, dù cả hai phiên bản Java đều được Boot hỗ trợ khi dùng **đúng riêng từng cấu hình**. Một bộ “Boot hỗ trợ Java 17+” không có nghĩa ứng dụng được build cho Java 21 sẽ chạy ngược trên Java 17.

Java toolchain giúp chọn compiler nhất quán, nhưng không tự xác nhận Docker image cũng đúng JVM. Trong Docker/CI, dùng image JDK phù hợp lúc build và image runtime có phiên bản đủ mới; chạy smoke test sau khi đóng gói.

Chọn JDK cho production còn liên quan thời hạn LTS của nhà phân phối, security patches, hỗ trợ của container base image, bộ nhớ và hiệu năng thực tế. Ưu tiên runtime được tổ chức cập nhật bản vá đều đặn.

## 9. Kiểm thử tương thích và chẩn đoán lỗi

Một bộ kiểm tra tối thiểu trước khi chốt stack:

| Kiểm tra | Lệnh / phương pháp | Ý nghĩa |
| --- | --- | --- |
| JDK được dùng | `java -version`, `mvn -version` / `./gradlew --version` | Có đúng JVM cho build không |
| Compile/package | `mvn clean package` hoặc `./gradlew build` | Mã và plugin có phù hợp không |
| Dependency graph | `mvn dependency:tree` / `./gradlew dependencyInsight` | Có bị trộn các module Security/Framework không |
| Boot start | `mvn spring-boot:run` / `./gradlew bootRun` | Auto-configuration có khởi tạo được không |
| Public endpoint | `curl` tới `/status` trong ví dụ | Request web cơ bản có hoạt động không |
| Protected endpoint | Gọi URL cần xác thực | Security filter chain có được đăng ký không |
| Security tests | MockMvc/WebTestClient, authentication/authorization tests | Kiểm tra quy tắc bảo mật, không chỉ việc app chạy |
| Dependency & CVE audit | Công cụ scan dependency và advisories chính thức | Có dùng bản vá an toàn không |
| Staging runtime | Chạy JAR trong image/VM production | Có lệch JDK, OS, proxy hoặc container không |

Một số lỗi điển hình và cách tìm đúng nguyên nhân:

| Triệu chứng | Nguyên nhân cần kiểm tra trước |
| --- | --- |
| `UnsupportedClassVersionError` | Java bytecode mới hơn JVM dùng lúc chạy |
| `NoClassDefFoundError`, `ClassNotFoundException` | Thiếu module hoặc đổi package/namespace, runtime classpath không đồng nhất |
| `NoSuchMethodError` | Phiên bản thư viện runtime khác phiên bản mà mã đã biên dịch với nó; kiểm tra dependency tree |
| `Failed to introspect Class` hoặc lỗi autoconfiguration | Dependency phụ thuộc Spring/Jakarta không còn tương thích |
| Maven báo “release version 21 not supported” | Compiler/JDK thực tế quá cũ so với release được yêu cầu |
| Gradle plugin không nạp hoặc wrapper lỗi | Gradle/Java/plugin không đáp ứng version matrix |
| Endpoint bảo mật trả 401/302 | Có thể là **hành vi đúng** của Spring Security; kiểm tra AuthenticationEntryPoint, đừng coi mặc nhiên là lỗi tương thích |

Không sửa các lỗi thư viện bằng cách xóa phần Security hoặc tắt CSRF chỉ để ứng dụng khởi động. Chúng là vấn đề khác với tính tương thích phiên bản.

## 10. Cách nâng cấp từng lớp mà không phá vỡ dự án

Khi ứng dụng đang chạy một bộ cũ và cần nâng cấp, hãy làm theo thứ tự có kiểm soát:

1. **Chốt phiên bản hiện có**: ghi rõ JDK build/runtime, Boot, Security thực tế được resolve, Framework, Gradle/Maven, container và các thư viện Spring khác.
2. **Đọc migration guide của các major version sẽ đi qua**, đặc biệt khi đổi Boot 3 → 4 hoặc Security 6 → 7. Kiểm tra các API bị bỏ, Jakarta, cấu hình bảo mật, OAuth2, method security và starters.
3. **Chọn Boot đích và bộ quản lý dependency** theo tài liệu System Requirements/BOM; kiểm tra Java và build tool trước.
4. **Nâng patch của nhánh hiện tại nếu cần** để có trạng thái ổn định/bản vá trước khi đổi major.
5. **Cập nhật Java/toolchain, parent/plugin/BOM và starter** theo một thay đổi có thể kiểm thử; hạn chế việc ép phiên bản Security riêng.
6. **Chạy compile, unit/integration/security tests**; kiểm tra dependency tree và các test xác thực, phân quyền, session, CSRF, OAuth2 hoặc JWT tùy ứng dụng.
7. **Triển khai thử trên staging** với JVM và container tương đương production, đo startup, latency, login flow và health endpoint.
8. **Theo dõi và có cách rollback** nếu có thay đổi behavior hoặc dependency không tương thích.

Không phải mọi dự án đều cần nâng major ngay. Nhưng khi có lỗ hổng hoặc hết hỗ trợ, việc giữ mã cũ không được biện minh bằng câu “ứng dụng vẫn chạy”.

### Vì sao không nâng Spring Security một mình?

Spring Security tương tác chặt với Spring Framework, Spring Boot auto-configuration, servlet/webflux runtime, authentication, HTTP headers, method interception và các dependency khác. Nếu để Boot quản lý Security, bạn nhận được tổ hợp đã được Boot kiểm tra. Nếu vượt khỏi BOM, bạn đang chủ động nhận trách nhiệm thử nghiệm khả năng tương thích và kiểm soát rủi ro.

Đối với một bản vá bảo mật cấp bách, có trường hợp override là cần thiết. Tuy nhiên đó phải là quyết định có nguồn và được kiểm thử; không nên coi việc thêm `<version>` theo hướng dẫn trên mạng là phương pháp nâng cấp chuẩn.

## 11. Ba tình huống để tự chọn bộ phiên bản

**Tình huống A — Dự án mới, máy lập trình và production có JDK 21, Maven 3.9, chỉ cần REST API servlet và bảo mật cơ bản.**

Có thể chọn Boot **4.1.2**, Security **7.1.2** theo Boot BOM, `spring-boot-starter-webmvc` và `spring-boot-starter-security`. Sử dụng Java 21, Maven parent Boot; không ghi riêng version của Spring Security. Tạo smoke test, kiểm tra JDK runtime/container trước khi deploy.

**Tình huống B — Ứng dụng đang dùng Spring Boot 3.5, phụ thuộc một thư viện nội bộ đã kiểm thử với Spring Framework 6.2 và JDK 17.**

Ưu tiên kiểm tra bản Boot 3.5 patch đang được bảo trì, dùng Security tương ứng từ BOM. Bộ tham chiếu ở ngày soạn bài là Boot **3.5.16** + Security **6.5.11**, chạy Java 17. Nếu muốn nâng Boot 4, phải kiểm tra thư viện nội bộ và tác động của Spring Framework 7, Jakarta/Servlet, test; không thay mỗi Security version thành 7.1 rồi giả định tương thích.

**Tình huống C — Máy development đã cài Java 27 nhưng dự án còn Boot 3.5.16.**

Tài liệu Boot 3.5.16 công bố tương thích đến **Java 25**, nên **không thể kết luận Java 27 là tổ hợp được hỗ trợ** chỉ vì chạy được vài lệnh. Có thể dùng JDK trong phạm vi đã công bố, hoặc chuẩn bị nâng nhánh Boot sau khi kiểm tra các ràng buộc và dependency.

**Tình huống D — Bài hướng dẫn trên mạng yêu cầu Spring Security 5.8 còn hệ thống mới dùng Boot 4.1.**

Không copy nguyên POM/API từ tutorial đó. Tìm hướng dẫn cùng major Spring Security 7, sử dụng starter/BOM và API cấu hình hiện đại. Nếu gặp một dependency cũ, hãy kiểm tra phiên bản mới hoặc loại bỏ dependency không cần thiết.

## 12. Checklist chọn stack và các sai lầm thường gặp

Trước khi ghi nhận một bộ là “tương thích”, hãy tự trả lời:

- [ ] Đã đọc **System Requirements của chính Spring Boot version** định dùng.
- [ ] Java build và Java runtime đều nằm trong phạm vi được hỗ trợ; bytecode không vượt quá JVM production.
- [ ] Maven/Gradle wrapper và plugin phù hợp version.
- [ ] Đã dùng Boot parent hoặc BOM nhất quán; các Spring modules được resolve thống nhất.
- [ ] Đã kiểm tra phiên bản Spring Security trong **Managed Dependency Coordinates**, không đoán từ tên starter.
- [ ] Đã chọn đúng Web MVC/Servlet hoặc WebFlux/Reactive và security API tương ứng.
- [ ] Có Spring Cloud thì đã chọn Cloud release train tương thích.
- [ ] Không vô ý kéo một Security/Framework bản RC, SNAPSHOT hoặc khác major vào stable project.
- [ ] Đã chạy build, startup, security tests và kiểm tra dependency graph.
- [ ] Đã xem release notes, security advisories và vòng đời hỗ trợ trước production.

Các lỗi dễ mắc nhất:

1. **“Spring Boot 4 luôn cần Java 21.”** Không đúng đối với Boot 4.1.2: tài liệu chính thức ghi tối thiểu Java 17.
2. **“Java 27 chạy được mọi Spring Boot 3.x.”** Không được suy từ phiên bản Java cao hơn; Boot 3.5.16 chỉ công bố tương thích tới Java 25.
3. **“Chọn Boot 4.1.2 rồi tự gắn Security 6.5 là tối ưu.”** Có nguy cơ lệch major/framework. Theo BOM mặc định Boot 4.1.2 quản lý Security 7.1.2.
4. **“Dùng `spring-boot-starter-security` phải ghi version Security riêng.”** Khi parent/BOM Boot được áp dụng đúng, không cần.
5. **“Chỉ thêm Boot Gradle plugin thì mọi dependency tự thống nhất.”** Cần kiểm tra cơ chế BOM/dependency management đang áp dụng trong Gradle.
6. **“Build thành công chứng minh bảo mật đã đúng.”** Không: còn cần kiểm thử authentication, authorization và cấu hình production.
7. **“Có bản major mới nhất thì tất cả thư viện cũ đều tương thích.”** Không: thư viện ngoài Boot BOM có thể cần nâng cấp.
8. **“Bản RC có tên phiên bản cao hơn nên luôn nên dùng.”** Không: RC dùng cho kiểm thử khả năng nâng cấp, không mặc nhiên là lựa chọn stable.
9. **“Bị 401 sau khi thêm Spring Security tức version sai.”** Có thể chỉ là cơ chế bảo vệ mặc định đang hoạt động.
10. **“Maven parent và BOM là cùng một thứ.”** Parent còn quản lý plugin/build defaults; BOM chủ yếu quản lý dependency versions.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Dự án dùng Boot 4.1.2, Java 21, `spring-boot-starter-security`. Có cần ghi thêm `<version>7.1.2</version>` cho `spring-security-core`?

*Trả lời:* Không nếu đã dùng parent/BOM Boot đúng cách. Boot 4.1.2 quản lý Spring Security 7.1.2. Chỉ override khi có lý do đặc biệt, tài liệu tương thích và kiểm thử.

**Câu 2.** Muốn làm ứng dụng Spring Boot 4.1.2 nhưng Gradle wrapper đang là 8.5. Java 21 đã cài. Đã đủ chưa?

*Trả lời:* Chưa. Boot 4.1.2 công bố Gradle nhánh 8.x phải từ 8.14 trở lên, hoặc dùng Gradle 9.x. Cần cập nhật wrapper phù hợp trước.

**Câu 3.** Tại sao Boot 3.5.16 và Security 6.5.11 là một bộ có cơ sở, còn Boot 3.5.16 + Security 7.1.2 không nên tự giả định?

*Trả lời:* Vì Managed Dependency Coordinates của Boot 3.5.16 quản lý Security 6.5.11 cùng Framework 6.2; Security 7 thuộc thế hệ khác và cần kiểm tra tương thích chính thức.

**Câu 4.** Một ứng dụng build bằng Java 21, chạy JAR trên Java 17 bị `UnsupportedClassVersionError`. Đây có thể là vấn đề gì?

*Trả lời:* Bytecode target mới hơn JVM runtime. Boot hỗ trợ cả hai JDK khi dùng độc lập không đồng nghĩa bytecode Java 21 chạy trên JVM 17.

**Câu 5.** Điều gì chứng minh phiên bản Security thực sự được resolve là 7.1.2 thay vì bản bị kéo từ thư viện khác?

*Trả lời:* Dependency graph/effective BOM của build thực tế, ví dụ `mvn dependency:tree` hoặc Gradle `dependencyInsight`; không chỉ một bảng tham khảo hay tên starter.

**Câu 6.** Vì sao một project Boot 4.1 lại dùng `spring-boot-starter-webmvc` trong ví dụ, còn Boot 3.5 dùng `spring-boot-starter-web`?

*Trả lời:* Boot 4 tổ chức lại các module/starter web với lựa chọn rõ Web MVC; khi chuyển nhánh cần theo tài liệu và metadata của đúng phiên bản, không ghép vô điều kiện artifact cũ vào ví dụ mới.

**Câu 7.** Nếu cần sửa CVE Spring Security thì chỉ cần thêm phiên bản mới nhất cho mỗi module có báo lỗi?

*Trả lời:* Không. Cần đọc advisory, chọn bản vá tương thích với stack, ưu tiên cập nhật Boot BOM/patch khi có, bảo đảm các module Security cùng thế hệ và chạy kiểm thử đầy đủ.

Khi bắt đầu dự án, hãy coi bộ **Java → Spring Boot → Spring Security** là một quyết định kỹ thuật được xác minh từ **System Requirements + Boot BOM + dependency graph + kiểm thử thực tế**. Bộ phiên bản tốt là bộ phù hợp với môi trường, có đường nâng cấp và nhận bản vá, chứ không đơn giản là ba số lớn nhất trên các trang tải xuống.

### Nguồn chính thức để cập nhật

- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html)
- [Spring Security — Hello Spring Security (Servlet)](https://docs.spring.io/spring-security/reference/servlet/getting-started.html)
- [Spring Security Advisories](https://spring.io/security/)
- [Spring Boot release notes](https://github.com/spring-projects/spring-boot/wiki)
