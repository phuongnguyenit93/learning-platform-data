# Ảnh hưởng của dependency và lựa chọn loại ứng dụng đến nhánh cấu hình web

## 1. Mục tiêu và câu hỏi cốt lõi

Spring Boot có thể tự chọn nhánh cấu hình web dựa trên những thư viện hiện diện trên runtime classpath và loại ứng dụng mà `SpringApplication` sử dụng. Vì vậy, chỉ cần thêm hoặc bỏ một starter, ứng dụng có thể đi từ nhánh **Servlet/MVC** sang **Reactive/WebFlux**, hoặc thành context không-web. Tuy nhiên, classpath và lựa chọn loại ứng dụng là hai yếu tố khác nhau: một class có thể hiện diện nhưng nhánh cấu hình tương ứng vẫn không được áp dụng nếu loại ứng dụng đã được đặt rõ.

Bài học tập trung vào Spring Boot **3.3.13**, Spring Framework 6.1 và Java 17+. Sau bài này, bạn cần hiểu:

1. `spring-boot-starter-web` và `spring-boot-starter-webflux` mang những thành phần nào vào dependency graph.
2. Spring Boot suy luận `WebApplicationType` như thế nào khi có MVC, chỉ có WebFlux, có cả hai hoặc không có stack web.
3. Cách chọn tường minh `SERVLET`, `REACTIVE` hoặc `NONE` bằng property và Java API.
4. Cách `@ConditionalOnClass` phối hợp với `@ConditionalOnWebApplication` để chọn đúng nhánh auto-configuration.
5. Vì sao dependency server (Tomcat, Jetty, Undertow, Reactor Netty) là một quyết định khác với application type.
6. Cách kiểm thử từng nhánh mà không vô tình chạy nhầm loại context.

**Ý chính:** dependency ảnh hưởng đến những class có thể được phát hiện; `WebApplicationType` xác định loại môi trường web mà Boot chọn; các điều kiện auto-configuration quyết định cấu hình nào thực sự được áp dụng.

## 2. Ba khái niệm không được đánh đồng

### 2.1. Dependency và runtime classpath

Dependency là artifact mà Maven/Gradle giải quyết và đưa vào compile/runtime classpath theo scope/configuration. Ví dụ:

- `spring-webmvc` cung cấp Spring MVC và `DispatcherServlet`.
- `spring-webflux` cung cấp Spring WebFlux và `DispatcherHandler`.
- `spring-boot-starter-web` kéo các thành phần cho ứng dụng Servlet/MVC, bao gồm starter Tomcat mặc định.
- `spring-boot-starter-webflux` kéo các thành phần cho WebFlux, bao gồm Reactor Netty mặc định.

Khi thêm một starter, nhiều dependency chuyển tiếp có thể xuất hiện. Khi bỏ một starter, class tương ứng chỉ biến mất nếu không còn dependency khác kéo artifact đó vào. Do đó hãy kiểm tra dependency graph thực tế thay vì chỉ nhìn một dòng trong `pom.xml`.

### 2.2. Loại ứng dụng: `WebApplicationType`

Spring Boot 3.3 có ba giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `SERVLET` | Ứng dụng web dựa trên Servlet; Boot tạo servlet web application context và có thể khởi động embedded servlet server |
| `REACTIVE` | Ứng dụng web reactive; Boot tạo reactive web application context và có thể khởi động embedded reactive server |
| `NONE` | Ứng dụng không chạy như web application và không khởi động embedded web server |

`WebApplicationType` không phải tên server. `SERVLET` không đồng nghĩa bắt buộc dùng Tomcat; `REACTIVE` cũng không đồng nghĩa bắt buộc dùng Reactor Netty. Server có thể được thay thế bằng implementation được hỗ trợ.

### 2.3. Nhánh auto-configuration

Một auto-configuration có thể yêu cầu đồng thời:

- Class thư viện cần thiết tồn tại (`@ConditionalOnClass`).
- ApplicationContext là Servlet hoặc Reactive (`@ConditionalOnWebApplication`).
- Bean phù hợp đã tồn tại hoặc chưa tồn tại (`@ConditionalOnBean` / `@ConditionalOnMissingBean`).
- Property thỏa điều kiện (`@ConditionalOnProperty`).

Vì vậy, “dependency đã có” không đủ để kết luận “auto-configuration đã chạy”. Một condition khác vẫn có thể không khớp.

## 3. Spring Boot suy luận WebApplicationType từ classpath

Theo tài liệu Spring Boot 3.3, khi `SpringApplication` tự chọn loại context, quy tắc khái quát là:

1. Nếu Spring MVC có mặt, Boot chọn **Servlet**.
2. Nếu Spring MVC không có và Spring WebFlux có mặt, Boot chọn **Reactive**.
3. Nếu cả hai không có, Boot chọn **Non-web**.

Nếu cả MVC và WebFlux đều hiện diện, **MVC được ưu tiên mặc định**. Trường hợp này thường xuất hiện khi ứng dụng MVC thêm WebFlux starter để sử dụng `WebClient`. Việc có `spring-webflux` trên classpath không tự động chuyển toàn bộ ứng dụng sang reactive.

### 3.1. Bảng quyết định theo dependency

| Thành phần trên runtime classpath | Loại được suy luận mặc định | Nhánh context thường được chọn |
| --- | --- | --- |
| Chỉ có Spring MVC / Servlet stack | `SERVLET` | Servlet web context |
| Chỉ có Spring WebFlux stack | `REACTIVE` | Reactive web context |
| Có cả MVC và WebFlux | **`SERVLET`** | MVC/Servlet; WebFlux vẫn có thể cung cấp API như WebClient |
| Không có MVC và WebFlux | `NONE` | Context Spring thông thường, không có web server |

Bảng trên mô tả việc suy luận mặc định của `SpringApplication`. Các ứng dụng có thể ghi đè loại ứng dụng; ngoài ra, điều kiện khác và cấu hình riêng vẫn ảnh hưởng đến bean cuối cùng.

### 3.2. Context tương ứng

Khi sử dụng factory mặc định của Spring Boot 3.3:

- `SERVLET` → `AnnotationConfigServletWebServerApplicationContext`.
- `REACTIVE` → `AnnotationConfigReactiveWebServerApplicationContext`.
- `NONE` → `AnnotationConfigApplicationContext`.

Đây là các loại context mặc định tương ứng. Ứng dụng có thể tùy biến `ApplicationContextFactory` nếu có nhu cầu đặc biệt, vì vậy không nên coi tên class context mặc định là cách duy nhất để tạo ứng dụng.

### 3.3. Ví dụ dễ nhầm: dùng WebClient trong ứng dụng MVC

Một dự án có thể dùng controller Spring MVC nhưng muốn gọi dịch vụ khác bằng `WebClient`. `WebClient` thuộc Spring WebFlux. Nếu thêm `spring-boot-starter-webflux` vào dự án vốn đã có `spring-boot-starter-web`, Boot mặc định vẫn chọn MVC vì cả hai stack có mặt và MVC được ưu tiên.

Điều đó cho phép ứng dụng dùng `WebClient` mà không nhất thiết chuyển controller, server và toàn bộ nhánh auto-configuration sang reactive. Cần phân biệt **dùng một API reactive làm HTTP client** với **chạy server theo reactive web application type**.

## 4. Dependency của server và application type là hai quyết định riêng

### 4.1. Starter mặc định mang theo embedded server

Theo Spring Boot 3.3:

- `spring-boot-starter-web` bao gồm `spring-boot-starter-tomcat` mặc định cho Servlet stack.
- `spring-boot-starter-webflux` bao gồm `spring-boot-starter-reactor-netty` mặc định cho reactive stack.

Boot cũng hỗ trợ thay embedded server:

| Stack | Server mặc định từ starter | Những lựa chọn khác được hỗ trợ |
| --- | --- | --- |
| Servlet/MVC | Tomcat | Jetty, Undertow |
| Reactive/WebFlux | Reactor Netty | Tomcat, Jetty, Undertow |

Vì thế, chọn `SERVLET` không phải là chọn Tomcat; chọn `REACTIVE` cũng không phải là chọn Reactor Netty. Application type xác định nhánh web; dependency server cung cấp server implementation tương ứng.

### 4.2. Thay Tomcat bằng Jetty trong Servlet stack

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

Ứng dụng vẫn là Servlet/MVC; dependency server được thay đổi. Hãy đảm bảo chỉ còn server implementation phù hợp trong dependency graph và kiểm tra lại runtime classpath.

### 4.3. Thay Reactor Netty trong Reactive stack

Ví dụ Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
```

Đây là minh họa thay server trong reactive stack, không phải cách biến ứng dụng thành Servlet/MVC. WebFlux có thể chạy trên các server được Spring Boot hỗ trợ, bao gồm một số Servlet containers.

**Lưu ý riêng về WebClient:** `spring-boot-starter-reactor-netty` cũng cung cấp Reactor Netty cần thiết cho `WebClient` trong một số cấu hình. Nếu đổi server nhưng ứng dụng vẫn cần `WebClient` với Reactor Netty, có thể vẫn cần giữ dependency Netty phù hợp. Không xóa dependency chỉ vì muốn thay embedded server.

## 5. Chọn loại ứng dụng tường minh

Khi cần ghi đè suy luận từ classpath, Spring Boot hỗ trợ hai cách.

### 5.1. Qua property

Trong `application.properties`:

```properties
spring.main.web-application-type=reactive
```

Các giá trị hợp lệ tương ứng với enum là `servlet`, `reactive` và `none`. Ví dụ YAML:

```yaml
spring:
  main:
    web-application-type: reactive
```

Một số tình huống:

- Muốn chạy WebFlux dù cả MVC và WebFlux cùng có mặt → `reactive`.
- Muốn chạy Servlet/MVC → `servlet`.
- Muốn context không-web và không khởi động server → `none`.

### 5.2. Qua SpringApplication API

```java
SpringApplication application =
    new SpringApplication(MyApplication.class);

application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Đây là cách Java tường minh, phù hợp khi logic khởi động cần quyết định loại ứng dụng theo môi trường hoặc một tham số do ứng dụng kiểm soát.

Có thể đọc giá trị được suy luận trước khi chạy:

```java
SpringApplication application =
    new SpringApplication(MyApplication.class);

System.out.println(application.getWebApplicationType());
```

`getWebApplicationType()` trả loại ứng dụng hiện tại mà `SpringApplication` sẽ sử dụng; nếu chưa được đặt tường minh, giá trị được suy luận từ classpath. Cả `setWebApplicationType` và `getWebApplicationType` đều có trong Spring Boot 3.3.13.

### 5.3. `NONE` khác với tắt HTTP port

Hai cấu hình này không tương đương:

```properties
spring.main.web-application-type=none
```

chọn non-web context. Trong khi đó:

```properties
server.port=-1
```

vẫn có thể tạo `WebApplicationContext` nhưng không mở HTTP port như ứng dụng thông thường. Cấu hình `server.port=-1` hữu ích khi cần một web context trong test nhưng không muốn lắng nghe cổng mạng. Nếu mục tiêu là không có web environment, chọn `WebApplicationType.NONE` hoặc property `none`.

## 6. Chọn đúng nhánh auto-configuration

### 6.1. Kiểm classpath và application type cùng lúc

Một auto-configuration chỉ dành cho MVC có thể viết:

```java
@AutoConfiguration
@ConditionalOnClass(
    name = "org.springframework.web.servlet.DispatcherServlet"
)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET
)
public class ServletClientAutoConfiguration {
    // Bean chỉ dành cho Servlet/MVC ...
}
```

Một auto-configuration dành cho WebFlux:

```java
@AutoConfiguration
@ConditionalOnClass(
    name = "org.springframework.web.reactive.DispatcherHandler"
)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE
)
public class ReactiveClientAutoConfiguration {
    // Bean chỉ dành cho WebFlux ...
}
```

Các ví dụ là snippet minh họa; bean và dependency cụ thể cần được định nghĩa trong starter thật.

Ý nghĩa hai điều kiện:

- `@ConditionalOnClass` hỏi class cần thiết có trên classpath không.
- `@ConditionalOnWebApplication` hỏi context hiện tại thuộc loại web nào.

Nếu cả MVC và WebFlux cùng có mặt nhưng `WebApplicationType` là `SERVLET`, class WebFlux có thể tồn tại nhưng nhánh reactive vẫn không khớp `@ConditionalOnWebApplication(REACTIVE)`. Nếu ứng dụng được ép sang `REACTIVE`, nhánh reactive mới có cơ hội khớp; các điều kiện classpath và điều kiện bean khác vẫn phải thỏa.

### 6.2. `ANY` và `@ConditionalOnNotWebApplication`

`@ConditionalOnWebApplication` có các loại:

- `ANY`: bất kỳ loại web application nào.
- `SERVLET`: chỉ Servlet-based web application.
- `REACTIVE`: chỉ Reactive-based web application.

Ví dụ:

```java
@ConditionalOnWebApplication
class CommonWebConfiguration {
    // Dùng chung cho các web application.
}
```

Mặc định `type` là `ANY`. Với cấu hình chỉ dành cho ứng dụng không-web:

```java
@ConditionalOnNotWebApplication
class BatchOnlyConfiguration {
    // Cấu hình không dành cho web application.
}
```

Không dùng `@ConditionalOnClass` đơn lẻ để kết luận ứng dụng đang chạy MVC hay WebFlux. Class có thể tồn tại trong classpath của cả hai trường hợp.

### 6.3. Các nhánh auto-configuration thường gặp

Trong Spring Boot 3.3, có các lớp cấu hình riêng cho từng stack, chẳng hạn:

| Nhánh | Ví dụ auto-configuration |
| --- | --- |
| Servlet/MVC | `org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration` |
| WebFlux | `org.springframework.boot.autoconfigure.web.reactive.WebFluxAutoConfiguration` |
| Servlet embedded server | `org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration` |
| Reactive embedded server | `org.springframework.boot.autoconfigure.web.reactive.ReactiveWebServerFactoryAutoConfiguration` |

Đây là tên lớp để định hướng đọc tài liệu/source đúng phiên bản; đừng suy ra mọi bean web trong ứng dụng chỉ đến từ một trong các lớp này. Những auto-configuration khác cũng có thể bổ sung web support theo condition riêng.

## 7. Ví dụ Java 17+ chạy độc lập: kiểm tra classpath và loại ứng dụng

Ví dụ sau dùng Spring Boot **3.3.13** và thêm cả hai starter `spring-boot-starter-web` và `spring-boot-starter-webflux`. Chương trình chỉ tạo `SpringApplication` để xem loại ứng dụng được suy luận và giá trị sau khi đặt override; nó **không gọi `run()`**, do đó không mở cổng hay khởi động embedded server.

### 7.1. Cấu trúc thư mục

```text
web-application-type-demo/
├── pom.xml
└── src/main/java/demo/WebTypeProbe.java
```

### 7.2. File `pom.xml`

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

    <groupId>demo</groupId>
    <artifactId>web-application-type-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <!-- Cung cấp Spring MVC và Tomcat mặc định -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <!-- Cung cấp Spring WebFlux và Reactor Netty mặc định -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 7.3. File `src/main/java/demo/WebTypeProbe.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.util.ClassUtils;

@SpringBootApplication
public class WebTypeProbe {

    private static boolean classPresent(String className) {
        return ClassUtils.isPresent(
            className,
            WebTypeProbe.class.getClassLoader()
        );
    }

    private static void printType(
        String label,
        WebApplicationType explicitType
    ) {
        SpringApplication application =
            new SpringApplication(WebTypeProbe.class);

        if (explicitType != null) {
            application.setWebApplicationType(explicitType);
        }

        System.out.println(
            label + "=" + application.getWebApplicationType()
        );
    }

    public static void main(String[] args) {
        System.out.println(
            "mvcClass=" + classPresent(
                "org.springframework.web.servlet.DispatcherServlet"
            )
        );
        System.out.println(
            "webFluxClass=" + classPresent(
                "org.springframework.web.reactive.DispatcherHandler"
            )
        );

        // Không set type: Boot suy luận từ classpath.
        printType("default", null);

        // Ghi đè kết quả suy luận.
        printType("forcedServlet", WebApplicationType.SERVLET);
        printType("forcedReactive", WebApplicationType.REACTIVE);
        printType("forcedNone", WebApplicationType.NONE);
    }
}
```

### 7.4. Chạy chương trình

Yêu cầu: JDK 17+, Maven 3.6.3+ và quyền tải dependency. Trong thư mục `web-application-type-demo` chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.WebTypeProbe
```

Để Maven chạy được `exec:java`, thêm plugin `exec-maven-plugin` vào `build/plugins`:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
```

Với cả hai starter trong POM, các dòng do chương trình tự in là:

```text
mvcClass=true
webFluxClass=true
default=SERVLET
forcedServlet=SERVLET
forcedReactive=REACTIVE
forcedNone=NONE
```

Giải thích:

1. `mvcClass=true` vì starter web đưa Spring MVC/`DispatcherServlet` vào runtime classpath.
2. `webFluxClass=true` vì starter WebFlux đưa `DispatcherHandler` vào runtime classpath.
3. `default=SERVLET` vì khi hai stack cùng hiện diện, Spring Boot ưu tiên Spring MVC theo quy tắc mặc định.
4. `forcedServlet=SERVLET` xác nhận có thể chọn tường minh Servlet.
5. `forcedReactive=REACTIVE` xác nhận có thể chọn WebFlux dù MVC vẫn hiện diện.
6. `forcedNone=NONE` xác nhận có thể yêu cầu ứng dụng không chạy như web application.

**Giới hạn của demo:** chương trình kiểm tra việc suy luận/override của `SpringApplication` và khả năng tải class. Nó không refresh context, không khởi động server, không chứng minh toàn bộ bean MVC/WebFlux được tạo thành công. Muốn kiểm tra auto-configuration và endpoint thực tế, cần chạy context/application và viết test riêng.

### 7.5. Thử các dependency graph khác

Giữ nguyên file Java, thay đổi dependency trong POM và chạy lại:

| POM | `mvcClass` | `webFluxClass` | `default` kỳ vọng |
| --- | :---: | :---: | --- |
| Chỉ `spring-boot-starter-web` | true | false | `SERVLET` |
| Chỉ `spring-boot-starter-webflux` | false | true | `REACTIVE` |
| Cả hai starter | true | true | `SERVLET` |
| Chỉ `spring-boot-starter` | false | false | `NONE` |

Bảng này giả định runtime classpath không còn dependency khác kéo Spring MVC hoặc WebFlux vào. Nếu dependency khác mang class tương ứng vào, kết quả suy luận có thể khác. Đây là lý do cần kiểm dependency tree thay vì chỉ nhìn starter trực tiếp.

## 8. Kiểm thử đúng loại context và nhánh cấu hình

### 8.1. Kiểm thử ứng dụng MVC và WebFlux

Với `@SpringBootTest`, khi cả MVC và WebFlux cùng hiện diện, MVC được chọn mặc định. Nếu test cần WebFlux, đặt property:

```java
@SpringBootTest(
    properties = "spring.main.web-application-type=reactive"
)
class MyWebFluxTests {
    // Kiểm thử reactive application.
}
```

Nếu muốn test MVC trong cùng classpath, có thể dùng cấu hình mặc định hoặc đặt tường minh `servlet`:

```java
@SpringBootTest(
    properties = "spring.main.web-application-type=servlet"
)
class MyMvcTests {
    // Kiểm thử servlet/MVC application.
}
```

Không nên để test WebFlux chạy theo default khi cả hai starter đều nằm trong test runtime classpath rồi kết luận reactive auto-configuration bị lỗi. Trước tiên hãy xác nhận application type thực tế.

### 8.2. Chọn test slice phù hợp

- `@WebMvcTest` tập trung vào Spring MVC layer.
- `@WebFluxTest` tập trung vào Spring WebFlux layer.
- `@SpringBootTest` kiểm tra context của ứng dụng rộng hơn; `webEnvironment` xác định mock environment hay server thật.

Với `@SpringBootTest`:

| `webEnvironment` | Ý nghĩa |
| --- | --- |
| `MOCK` (mặc định) | Tạo web ApplicationContext và mock environment; không khởi động embedded server |
| `RANDOM_PORT` | Khởi động server thật trên cổng ngẫu nhiên |
| `DEFINED_PORT` | Khởi động server thật trên cổng đã cấu hình hoặc mặc định |
| `NONE` | Tạo ApplicationContext không có web environment |

`webEnvironment` là lựa chọn cho test; `spring.main.web-application-type` là lựa chọn loại ứng dụng. Đừng coi hai thuộc tính này là một khái niệm duy nhất. Khi cần kiểm thử reactive trong classpath có cả MVC, hãy đặt loại reactive một cách rõ ràng.

### 8.3. Kiểm thử auto-configuration riêng lẻ

`ApplicationContextRunner` mặc định phù hợp cho context non-web. Nếu auto-configuration phụ thuộc vào web application type, hãy dùng runner web tương ứng như `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` khi phù hợp với phiên bản và dependency của test.

Ngoài ra, kiểm tra report điều kiện bằng `ConditionEvaluationReport` hoặc chạy ứng dụng với `--debug` để biết vì sao một condition không khớp. Khi test, ưu tiên assertion bean và kết quả endpoint thay vì chỉ đọc log.

## 9. Chẩn đoán khi ứng dụng chạy nhầm nhánh

1. **Kiểm loại ứng dụng trước:** log/đọc `SpringApplication.getWebApplicationType()` trong một điểm khởi tạo phù hợp hoặc xem context type thực tế.
2. **Kiểm classpath:** xem `mvn dependency:tree` hoặc Gradle `runtimeClasspath` để xác định ai mang `spring-webmvc` hoặc `spring-webflux` vào.
3. **Kiểm condition report:** dùng `--debug` hoặc `ConditionEvaluationReport` để tìm điều kiện class, web application, property và bean không khớp.
4. **Kiểm override:** tìm `spring.main.web-application-type` trong file cấu hình, biến môi trường, tham số command line và các tùy chỉnh `SpringApplication`.
5. **Kiểm server dependency:** xác định Tomcat/Jetty/Undertow/Reactor Netty có được resolve đúng không và có bị exclude nhầm không.
6. **Kiểm loại test:** `ApplicationContextRunner` non-web có thể làm `@ConditionalOnWebApplication` không khớp; dùng test runner/context đúng stack.
7. **Kiểm bean tùy chỉnh:** bean do ứng dụng cung cấp có thể làm auto-configuration back off; không kết luận chỉ dựa vào loại context.
8. **Kiểm cấu hình của server:** port, SSL và embedded container có thể khiến khởi động thất bại sau khi application type đã được chọn đúng.

Các lệnh kiểm dependency:

```bash
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc,org.springframework:spring-webflux
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat,org.springframework.boot:spring-boot-starter-reactor-netty
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webmvc
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-webflux
```

Thực hiện trên đúng module ứng dụng; trong multi-project Gradle, dependency graph của module thư viện có thể khác module chạy ứng dụng.

## 10. Lỗi phổ biến và cách sửa

| Hiểu nhầm / lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Thêm WebFlux starter là ứng dụng tự chuyển sang Reactive | Nếu MVC và WebFlux cùng có mặt, Boot ưu tiên MVC | Đặt `spring.main.web-application-type=reactive` nếu thực sự muốn reactive server |
| Có `DispatcherHandler` là chắc chắn chạy WebFlux | Class có thể có mặt trong MVC app chỉ để dùng WebClient | Kiểm tra `WebApplicationType` và `@ConditionalOnWebApplication` |
| Chọn `REACTIVE` là bắt buộc dùng Reactor Netty | Application type và server implementation là hai lựa chọn khác nhau | Chọn server dependency riêng theo hướng dẫn Boot |
| Chọn `NONE` giống `server.port=-1` | `NONE` tạo non-web context; port -1 vẫn có thể giữ web context | Chọn đúng mục tiêu test/chạy |
| Chỉ kiểm dependency trực tiếp trong POM | Starter khác có thể kéo MVC/WebFlux qua dependency chuyển tiếp | Kiểm `runtimeClasspath` hoặc `dependency:tree` |
| Dùng `@ConditionalOnClass` để phân biệt Servlet/Reactive | Điều kiện class chỉ kiểm class có mặt, không kiểm application type | Kết hợp `@ConditionalOnWebApplication(type=...)` |
| Dùng ApplicationContextRunner thường để test nhánh web | Runner non-web không mô phỏng Servlet/Reactive web context | Dùng web runner hoặc `@SpringBootTest` với property phù hợp |
| Nghĩ đổi Tomcat sang Jetty sẽ chuyển sang WebFlux | Cả hai có thể là server cho Servlet stack | Giữ application type và thay server dependency theo stack |
| Nghĩ bỏ server dependency sẽ tự loại toàn bộ Spring Web | API web và embedded server là dependency khác nhau | Kiểm classpath và loại context; loại bỏ đúng artifact cần thiết |
| Test WebFlux nhưng không override khi có cả MVC | Boot chọn MVC theo mặc định | Đặt `spring.main.web-application-type=reactive` trong test |

## 11. Bài tập tự kiểm tra

**Câu 1.** POM có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`. Nếu không override, loại ứng dụng mặc định là gì?  
**Đáp án:** `SERVLET`. Spring MVC được ưu tiên khi cả hai cùng có mặt.

**Câu 2.** Ứng dụng MVC cần dùng `WebClient`. Có bắt buộc đổi application type thành `REACTIVE` không?  
**Đáp án:** Không. Có thể dùng WebFlux client API trong ứng dụng MVC; Boot vẫn mặc định chọn Servlet khi MVC và WebFlux cùng có mặt.

**Câu 3.** `@ConditionalOnClass(DispatcherHandler.class)` khớp. Có đủ chứng minh reactive branch được áp dụng không?  
**Đáp án:** Không. Class có thể hiện diện trong classpath MVC; cần kiểm thêm `@ConditionalOnWebApplication(type = REACTIVE)` và các điều kiện khác.

**Câu 4.** Muốn ép ứng dụng chạy WebFlux dù MVC vẫn ở runtime classpath, chọn gì?  
**Đáp án:** `spring.main.web-application-type=reactive` hoặc `SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)`.

**Câu 5.** `spring.main.web-application-type=none` và `server.port=-1` khác nhau thế nào?  
**Đáp án:** none chọn non-web context; port -1 vẫn có thể tạo web context nhưng không mở HTTP port.

**Câu 6.** Chọn `SERVLET` có đồng nghĩa server phải là Tomcat?  
**Đáp án:** Không. Có thể dùng Tomcat, Jetty hoặc Undertow theo dependency phù hợp.

**Câu 7.** Vì sao test `@ConditionalOnWebApplication` có thể không khớp khi dùng `ApplicationContextRunner`?  
**Đáp án:** Runner thường tạo non-web context. Dùng runner web tương ứng hoặc `@SpringBootTest` với application type phù hợp.

## 12. Ghi nhớ và tài liệu tham khảo

- **Dependency** quyết định những class/server implementation có thể xuất hiện trên runtime classpath.
- **`WebApplicationType`** quyết định Spring Boot chọn context non-web, Servlet hay Reactive.
- Mặc định: MVC có mặt → Servlet; MVC không có nhưng WebFlux có → Reactive; cả hai không có → None.
- Khi cả MVC và WebFlux cùng có mặt, MVC được ưu tiên; muốn reactive phải đặt rõ `spring.main.web-application-type=reactive` hoặc dùng API tương đương.
- **Server implementation** (Tomcat, Jetty, Undertow, Reactor Netty) là quyết định riêng với application type.
- `@ConditionalOnClass` kiểm classpath; `@ConditionalOnWebApplication` kiểm loại web context. Dùng cả hai khi nhánh cấu hình phụ thuộc cả thư viện lẫn môi trường.
- Test phải chọn đúng loại context; log condition giúp chẩn đoán nhưng assertion mới xác nhận hành vi.

Tài liệu chính thức Spring Boot 3.3.13:

1. [SpringApplication — Web Environment và `setWebApplicationType`/`getWebApplicationType` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html).
2. [Testing Spring Boot Applications — Detecting Web Application Type](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).
3. [Reactive Web Applications — WebFlux và MVC precedence](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html).
4. [Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html).
5. [Embedded Web Servers — thay server và tắt web server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html).
6. [`WebApplicationType` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html).
7. [`@ConditionalOnWebApplication` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html).
8. [Spring Boot 3.3.13 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html).
