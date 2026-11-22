# Chuẩn bị thư viện `spring-context` và phiên bản tương thích

## 1. Hiểu đúng nhiệm vụ thiết lập

Để viết ứng dụng Spring Core Container đầu tiên bằng Java 17+, bạn cần **JDK**, **công cụ build**, **dependency `spring-context`**, rồi một chương trình tạo `ApplicationContext`. Không cần Spring Boot, máy chủ HTTP hay database để thử IoC/DI.

Tọa độ dependency Maven thường dùng là:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-context</artifactId>
    <version>7.0.9</version>
</dependency>
~~~

Ở đây `org.springframework` là **groupId**, `spring-context` là **artifactId**, `7.0.9` là **version**. Ba phần này định vị một artifact đã phát hành trên repository như Maven Central. Tên artifact **khác** Java package `org.springframework.context` và **khác** tên class `ApplicationContext`.

Bản `7.0.9` được cố định làm ví dụ ổn định, đã có trong tài liệu chính thức của Spring Framework tại thời điểm soạn bài. Khi dùng sản phẩm thực tế, kiểm tra release đang được hỗ trợ, vá lỗi bảo mật và chạy test sau khi nâng; không coi một số phiên bản trong tài liệu học là phiên bản phải giữ mãi.

**Kết quả cần đạt:** biên dịch được import `org.springframework.context.annotation.*`, mở được `AnnotationConfigApplicationContext`, đăng ký `@Bean`, lấy bean qua `getBean`, kiểm tra dependency tree và biết xử lý lỗi JDK/classpath/version.

## 2. Vì sao chọn đúng `spring-context` thay vì tải mọi JAR?

Spring Framework có nhiều module tách riêng, được phát hành thành những artifact Maven/Gradle:

| Artifact | Trách nhiệm chính | API/khái niệm dễ gặp |
| --- | --- | --- |
| `spring-core` | Tiện ích cơ sở, resource abstraction và hạ tầng | `Resource`, `ClassPathResource` |
| `spring-beans` | Bean factory, bean definitions, cấu hình và dependency wiring | `BeanFactory`, `BeanDefinition` |
| **`spring-context`** | Container ở cấp ứng dụng và cấu hình annotation | `ApplicationContext`, `AnnotationConfigApplicationContext`, `@Configuration`, `@Bean` |
| `spring-expression` | Ngôn ngữ biểu thức SpEL | `ExpressionParser` |
| `spring-aop` | Các cơ chế proxy/AOP cần thiết khi chức năng liên quan được sử dụng | Proxy infrastructure |
| `spring-webmvc` | MVC theo Servlet cho ứng dụng HTTP | `DispatcherServlet` |
| `spring-tx` | Hạ tầng quản lý transaction | `PlatformTransactionManager` |

Với demo Core Container chỉ có Java configuration và DI, hãy khai báo **một dependency trực tiếp `spring-context`**. Maven/Gradle đọc metadata POM của artifact để tự resolve các **dependency transitive bắt buộc** (trong đó có các module hạ tầng như `spring-beans`, `spring-core`). Không cần tự liệt kê lại mọi module để “chắc ăn”, cũng không nên tự tải một vài JAR lẻ rồi tùy tiện ghép classpath.

**`spring-core` một mình không chứa API `ApplicationContext`.** `spring-context-support` cũng không phải artifact bắt buộc cho một demo `@Bean` thông thường. Spring không có một JAR `spring-all` chứa trọn mọi khả năng.

Những thư viện như `spring-webmvc`, `spring-jdbc`, `spring-security`, bộ database driver hoặc embedded server **không được mặc nhiên có mặt** chỉ vì bạn đã thêm `spring-context`.

### Dependency trực tiếp và dependency transitive

- **Direct dependency:** khai báo ngay trong `pom.xml` hoặc `build.gradle`.
- **Transitive dependency:** được artifact phụ thuộc khai báo và build tool giải quyết theo graph.
- **Resolved dependency:** phiên bản cuối cùng mà build tool chọn sau khi xét version, BOM, exclusions và xung đột.

Nhìn thấy `spring-beans` trong `dependency:tree` **không có nghĩa** bạn đã khai báo nó trực tiếp. Ngược lại, nhìn thấy JAR đã tải về máy **không đảm bảo** JAR nằm trên compile/runtime classpath của module đang làm.

## 3. Đối chiếu phiên bản Spring, Java và hệ sinh thái

Chọn version theo **toàn bộ ứng dụng**, không chỉ theo một con số trên Maven Central.

| Mục | Spring Framework 6.2 | Spring Framework 7.0 |
| --- | --- | --- |
| JDK baseline | Java 17 | **Java 17** |
| Bản GA có thể đối chiếu | `6.2.19` | `7.0.9` |
| Hệ tích hợp thường gặp | Spring Boot 3.x tương ứng | Spring Boot 4.x tương ứng |
| Jakarta | Thế hệ Jakarta của Framework 6.x | Baseline **Jakarta EE 11** |
| Cách chọn cho ví dụ | Có thể dùng nếu các module liên quan cùng dòng 6.2 | Dùng **7.0.9** với Java 17 |

Spring 7.0 vẫn hỗ trợ **Java 17 là mức tối thiểu**, dù dự án Spring khuyến nghị sử dụng JDK LTS mới hơn khi phù hợp. Vì vậy việc `maven.compiler.release=17` là hợp lệ với ví dụ API `ApplicationContext` trên Spring 7.0.

**Quy tắc tương thích quan trọng:**

1. Nếu thêm nhiều Spring artifacts trực tiếp (ví dụ `spring-context`, `spring-jdbc`, `spring-tx`), quản lý chúng bằng **cùng bản phát hành Framework** hoặc một **BOM** phù hợp.
2. **Không ép** `spring-beans:6.2.x` dưới `spring-context:7.0.9` chỉ để giải quyết một conflict Maven; có thể sinh lỗi linkage lúc chạy.
3. Khi nâng **6.2 → 7.0**, đọc migration/release notes, đối chiếu API được bỏ, Jakarta EE 11, servlet/integration libraries. “Đều chạy Java 17” **không chứng minh** toàn bộ dependency Java cũ tương thích.
4. Nếu dự án dùng **Spring Boot**, hãy để BOM/parent/plugin của Boot quản lý phiên bản Spring Framework tương ứng. Đừng tự thêm một version `spring-context` lệch dòng của Boot khi không hiểu toàn bộ hệ quả.
5. Bản GA phát hành lên Maven Central thường không cần cấu hình repository snapshot/milestone. Tránh `SNAPSHOT`, `-M...`, `-RC...` trong bài nhập môn trừ khi chủ đích thử bản preview.

**Framework khác Boot:** `spring-context` là module nền IoC của Spring Framework; `spring-boot-starter` là tập dependency cho một loại dự án Spring Boot. Bài này dùng Framework trực tiếp để thấy container được tạo ra như thế nào.

## 4. Kiểm tra JDK và công cụ build

Mở terminal mới và chạy:

~~~bash
java -version
javac -version
mvn -version
~~~

Kiểm tra `java` và `javac` thuộc một JDK **17 hoặc cao hơn**. `mvn -version` còn hiển thị Java home mà Maven thực tế sử dụng; không được kết luận Maven đang chạy Java 17 chỉ vì IDE đang chọn Java 17.

Trên Linux/macOS có thể kiểm tra:

~~~bash
echo "$JAVA_HOME"
which java
which javac
~~~

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

Output của các lệnh kiểm tra này **phụ thuộc máy**, không có stdout cố định. Khi sửa `JAVA_HOME` hoặc `PATH`, mở terminal mới và kiểm tra lại.

**JDK** là bộ công cụ/SDK; **Maven** là build tool; **Maven Compiler Plugin** gọi compiler Java; **JAR Spring** là thư viện được biên dịch sẵn; **Maven Central** là repository cung cấp artifact. Chúng không thay thế cho nhau.

Nên sử dụng Maven Wrapper (`mvnw`) hoặc Gradle Wrapper (`gradlew`) nếu dự án đã cung cấp: wrapper ghim phiên bản build tool cho cả nhóm. Vì ví dụ sau là dự án tạo mới, dùng lệnh `mvn` sau khi cài Maven 3.9+.

## 5. Project Maven Java 17 hoàn chỉnh với `spring-context`

Tạo đúng cấu trúc:

~~~text
spring-context-first/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringContextFirst.java
~~~

### 5.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-context-first</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.framework.version>7.0.9</spring.framework.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.framework.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SpringContextFirst</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích POM:**

- `spring-context` dùng scope Maven mặc định là **compile**: Spring API có mặt khi biên dịch và runtime.
- `maven.compiler.release=17` yêu cầu compiler nhắm API/bytecode Java 17, tránh vô tình gọi API JDK mới hơn trong mã source.
- Property `spring.framework.version` gom version Framework về một chỗ. Khi có nhiều Spring module, BOM còn phù hợp hơn việc sao chép version.
- `maven-compiler-plugin` thực thi bước biên dịch; `exec-maven-plugin` khởi chạy main class cùng dependency classpath.
- Không bỏ `version` trong dependency này trừ khi POM thực sự kế thừa/import **dependency management** thích hợp.

Không cần khai báo riêng `spring-core`, `spring-beans` hoặc `spring-expression` trong demo nếu Maven giải quyết được graph qua `spring-context`.

### 5.2. `src/main/java/demo/SpringContextFirst.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class SpringContextFirst {
    private SpringContextFirst() {
    }

    interface Formatter {
        String greet(String name);
    }

    static final class EnglishFormatter implements Formatter {
        @Override
        public String greet(String name) {
            return "Hello, " + name + "!";
        }
    }

    static final class GreetingService {
        private final Formatter formatter;

        GreetingService(Formatter formatter) {
            this.formatter = formatter;
        }

        String greet(String name) {
            return formatter.greet(name);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        Formatter formatter() {
            return new EnglishFormatter();
        }

        @Bean
        GreetingService greetingService(Formatter formatter) {
            return new GreetingService(formatter);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            GreetingService first =
                    context.getBean(GreetingService.class);

            System.out.println("message=" + first.greet("An"));
            System.out.println("sameSingleton="
                    + (first == context.getBean(GreetingService.class)));
            System.out.println("context="
                    + context.getClass().getSimpleName());
        }
    }
}
~~~

**Vì sao đây là kiểm chứng thực sự?** Khi thiếu `spring-context`, compiler không tìm được các import Spring. Khi đã cấu hình đúng, `AnnotationConfigApplicationContext` đọc `AppConfig`, đăng ký `formatter` và `greetingService`; Spring resolve bean `Formatter` để truyền cho `@Bean greetingService(...)`. Scope mặc định singleton khiến hai lần lookup trả cùng reference trong context này.

`@Configuration(proxyBeanMethods=false)` dùng được vì hai factory methods không tự gọi trực tiếp nhau. `try-with-resources` đóng context đúng cách. Không cần Spring Boot, HTTP server, `@Autowired` field hoặc component scan cho demo Java configuration có khai báo `@Bean` tường minh.

### 5.3. Build và chạy

Đứng ở thư mục `spring-context-first` chứa `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

Maven tải dependency (ở lần đầu), dùng Maven Compiler Plugin gọi **`javac`** và chạy chương trình với classpath Spring. Lệnh `javac SpringContextFirst.java` trực tiếp **không đủ** nếu bạn chưa tự cung cấp đầy đủ classpath JAR Spring.

**Ba dòng stdout do chính code ứng dụng in** (không tính log Maven hoặc logging backend):

~~~text
message=Hello, An!
sameSingleton=true
context=AnnotationConfigApplicationContext
~~~

Nếu ứng dụng in thêm log thư viện trong môi trường riêng, phân biệt log đó với đúng ba lệnh `System.out.println` trong `main`.

## 6. Setup bằng Gradle thay cho Maven

Nếu dự án dùng Gradle, không cần đồng thời tạo `pom.xml` và `build.gradle`. Ví dụ sau sử dụng **nguyên `SpringContextFirst.java` ở mục 5.2** làm source, nên output ứng dụng giống mục 5.3.

~~~text
spring-context-gradle/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SpringContextFirst.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'spring-context-gradle'
~~~

Tệp `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:7.0.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SpringContextFirst'
}
~~~

Dùng bản Gradle hỗ trợ Java 17 và cấu hình JDK/toolchain tương thích. Nếu **đã có Gradle Wrapper**, trên Linux/macOS chạy:

~~~bash
./gradlew run
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat run
~~~

Nếu project mới **chưa có wrapper**, hãy cài Gradle tương thích rồi chạy `gradle run` hoặc tạo wrapper; không giả định file `gradlew` tự xuất hiện. Task `run` của Application Plugin thiết lập runtime classpath gồm dependency direct/transitive của dự án.

**Stdout của code ứng dụng**:

~~~text
message=Hello, An!
sameSingleton=true
context=AnnotationConfigApplicationContext
~~~

Gradle có thể in thêm trạng thái task và build ngoài ba dòng trên.

## 7. Quan sát dependency graph và BOM

Sau khi build Maven thành công, xem Spring artifacts mà dự án resolve:

~~~bash
mvn dependency:tree -Dincludes=org.springframework
~~~

Bạn thường nhìn thấy `spring-context` và một số modules nền kéo theo. **Không khóa cứng danh sách/count transitives** vì graph có thể đổi theo patch và tính năng. Dùng:

~~~bash
mvn help:effective-pom
~~~

để xem model POM sau parent/dependency management/plugins. Khi nghi version conflict, đọc `dependency:tree` để xem module nào kéo tới dependency sai version. Trên Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-context --configuration runtimeClasspath
~~~

Tập lệnh `./gradlew` chỉ áp dụng nếu dự án có wrapper; trên Windows đổi sang `gradlew.bat`.

### Khi dự án cần nhiều Spring artifacts

Một cách kiểm soát version trong **dự án Framework không dùng Boot** là import `spring-framework-bom`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>7.0.9</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
    </dependency>
</dependencies>
~~~

**Đây là phương án thay thế**, không phải phần bắt buộc phải chèn thêm vào POM mục 5.1. BOM chỉ **quản lý phiên bản** cho dependency bạn khai báo; BOM **không** tự thêm mọi Spring module vào classpath.

Khi ứng dụng dùng **Spring Boot**, ưu tiên BOM/parent/plugin Boot để Spring Framework, web, data và thư viện tích hợp được đồng bộ. Không trộn một bản Framework 7 với những Spring modules 6.2 được ép version riêng rồi xem đó là một dependency set hợp lệ.

## 8. Chẩn đoán lỗi ngay khi thiết lập

| Triệu chứng | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `package org.springframework.context... does not exist` | Thiếu `spring-context` trên compile classpath hoặc IDE chưa sync | Khai báo đúng dependency, reload Maven/Gradle, dùng build tool compile |
| `Could not find artifact org.springframework:...` | Artifact/version sai, mạng, mirror, proxy, offline | Soát GAV, Maven Central, `settings.xml` hoặc repository nội bộ |
| `release version 17 not supported` | Maven compiler chạy JDK cũ hơn 17 | Kiểm tra `mvn -version`, `JAVA_HOME`, toolchain |
| `UnsupportedClassVersionError` | Java runtime quá cũ so với class file | Đồng bộ runtime và bytecode/JDK |
| `NoClassDefFoundError` | Runtime classpath thiếu JAR hoặc dependency | Xem resolved graph và lệnh chạy |
| `NoSuchMethodError` | Có thể trộn versions hoặc binary mismatch | Kiểm tra dependency tree, BOM và exclusions |
| `NoSuchBeanDefinitionException` | Class hoặc bean chưa được đăng ký trong context | Xem `@Bean`, scan, type và context |
| `NoUniqueBeanDefinitionException` | Nhiều bean candidates cùng type | Xem `@Qualifier`, `@Primary`, bean names |
| IDE đỏ import nhưng Maven build tốt | IDE index/config module chưa reload | Refresh Maven/Gradle, xem source root/module |
| Console app thoát ngay | `main` kết thúc, context đã được đóng | Có thể là hành vi đúng; DI demo không cần HTTP server |

**Phân biệt rõ:** lỗi Maven download khác lỗi `javac` thiếu package; lỗi classpath runtime khác lỗi Spring không resolve được bean. Đừng xóa toàn bộ Maven cache theo thói quen; hãy xác định lỗi thuộc tầng nào trước khi đổi version hay cleanup.

Nếu chỉ cài `spring-core` mà import `ApplicationContext` vẫn lỗi, hãy chọn đúng **`spring-context`**, không phải sửa tên package Java một cách tùy ý.

### Tải JAR thủ công và JPMS

Có thể dùng `javac`/`java` với `-classpath` và mọi JAR cần thiết, nhưng phải tải **đúng transitives** và quản lý cách phân cách đường dẫn classpath (`;` trên Windows, `:` trên Linux/macOS). Điều này dễ thiếu JAR và khó nâng version; học Spring bằng Maven/Gradle an toàn hơn.

Ví dụ ở trên dùng **classpath thông thường**, không tạo `module-info.java`. JPMS/module path là chủ đề riêng; không tự chuyển các JAR và reflection/proxy của Spring sang module path rồi kỳ vọng hành vi giống hệt mà chưa kiểm tra metadata và module openness.

## 9. Quy trình đề xuất cho dự án thực tế

1. Chọn phiên bản Java được runtime/CI hỗ trợ, đồng bộ IDE/Maven/Gradle.
2. Chọn một release line Spring đang được hỗ trợ và một phương án quản lý dependency (Framework BOM hoặc Boot BOM tương ứng).
3. Thêm đúng artifact theo chức năng — Core Container trước hết là `spring-context`.
4. Tạo demo console nhỏ có `@Configuration`, `@Bean`, `ApplicationContext` và kiểm chứng stdout.
5. Xem dependency graph, kiểm tra có nhiều major versions Spring lẫn nhau không.
6. Thêm JUnit/tests, CI và upgrade notes khi đưa web/data/AOP/transaction vào dự án.
7. Dùng wrapper để tái hiện build trên máy khác; nâng patch bảo mật có test và rollback plan.

**Không nhất thiết tạo Spring Boot project** chỉ để thử `AnnotationConfigApplicationContext`. Nhưng nếu xây app web/data lớn, Boot có thể giảm công cấu hình. Hai đường đi đều sử dụng container của Spring Framework, không phải hai hệ DI độc lập.

## 10. Bài tập và câu hỏi tự kiểm tra

- **Đổi implementation:** thêm `VietnameseFormatter` trả `"Xin chao, " + name + "!"`, thay bean `formatter()`. Dự đoán `message=Xin chao, An!` mà không sửa `GreetingService`.
- **Xóa dependency trên bản sao:** tạm bỏ `spring-context` trong POM, chạy `mvn compile` và ghi lại lỗi `package org.springframework... does not exist`. Khôi phục POM ngay sau thử nghiệm.
- **Đổi version sai:** thử một version không tồn tại trên bản sao và quan sát Maven resolution failure, không nhầm với Java compiler error.
- **Thêm bean thứ hai:** tạo thêm `Formatter`, quan sát khả năng ambiguous injection và học cách dùng `@Qualifier`/`@Primary`.
- **Đổi scope:** đặt `GreetingService` là prototype, lấy bean hai lần, dự đoán `sameSingleton=false`; sửa tên nhãn thành `sameInstance` cho đúng ngữ nghĩa.
- **Kiểm JDK:** xem `java -version`, `javac -version`, `mvn -version`; giải thích tại sao JVM của build tool khác runtime sẽ gây lỗi.
- **Đọc dependency tree:** tìm artifact khai báo trực tiếp và module transitive, kiểm tra version Spring đang được resolve.
- **Thử Gradle:** chạy cùng class Java qua `application` plugin; so sánh ba dòng stdout với Maven.

Bạn đã nắm bài nếu trả lời được: `spring-context` khác `spring-core` ở đâu; artifact `org.springframework:spring-context:7.0.9` có ba thành phần gì; vì sao Java 17 phù hợp với Spring 7; khi nào nên dùng BOM; và cách chứng minh container đã inject được một dependency.

## 11. Tóm tắt và tài liệu tham khảo

**Ghi nhớ:** thiết lập Spring Core Container không chỉ là tải một JAR. Hãy chọn đúng **module `spring-context`**, một **dòng phiên bản tương thích với JDK và dependency khác**, dùng Maven/Gradle để resolve transitives, rồi kiểm chứng bằng chương trình tạo `ApplicationContext` thực sự.

Tài liệu chính thức:

- [Spring Framework Artifacts](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Artifacts)
- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/)
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes)
- [Spring IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html)
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle Dependency Management](https://docs.gradle.org/current/userguide/dependency_management.html)

**Kết luận:** Nếu `mvn -q clean compile exec:java` biên dịch được và in đúng ba dòng theo mục 5.3, bạn đã có môi trường Core Container hoạt động, đủ cơ sở để học tiếp đăng ký bean, DI, scope và lifecycle.