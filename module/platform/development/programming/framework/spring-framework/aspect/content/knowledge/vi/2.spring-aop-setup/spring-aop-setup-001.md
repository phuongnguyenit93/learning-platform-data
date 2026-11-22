# Các thư viện Spring AOP và AspectJ cần cho cấu hình được chọn

## 1. Mục tiêu: chọn đúng dependency theo kiểu cấu hình Spring

Khi thiết lập **Spring AOP**, câu hỏi quan trọng không chỉ là “đã thêm thư viện AOP chưa?” mà là **ứng dụng đang sử dụng cơ chế AOP nào**: Spring Boot auto-configuration, Spring Framework cấu hình bằng `@EnableAspectJAutoProxy`, cơ chế proxy thủ công của Spring, hay AspectJ weaving được tích hợp vào Spring. Mỗi lựa chọn có classpath và cách kích hoạt khác nhau.

Bài này chỉ xét việc **chọn và kiểm tra thư viện để sử dụng AOP trong ứng dụng Spring**. Kiến thức AOP tổng quát và kỹ thuật viết aspect bằng AspectJ độc lập với Spring không thuộc phạm vi ở đây.

**Đối với nhu cầu phổ biến nhất** — định nghĩa bean `@Aspect`, khai báo `@Before`, `@Around` và áp dụng advice vào phương thức của các bean Spring qua proxy — bộ thành phần cốt lõi là:

- **Spring AOP**, module `org.springframework:spring-aop`: tạo và vận hành proxy, advisor, interceptor trong Spring.
- **AspectJ weaver library**, module `org.aspectj:aspectjweaver`: cung cấp các kiểu AspectJ và khả năng phân tích, đối sánh biểu thức pointcut để Spring hiểu kiểu khai báo `@AspectJ`.
- **Spring container**, điển hình `org.springframework:spring-context` đối với Spring Framework thuần, hoặc các starter của Spring Boot: đăng ký bean, lifecycle và cấu hình.

Ở cấu hình này, Spring thực hiện **proxy-based AOP**. Tên thư viện `aspectjweaver` không có nghĩa ứng dụng tự động chạy AspectJ compile-time weaving (CTW) hay load-time weaving (LTW).

## 2. Phân biệt các artifact dễ nhầm

| Artifact | Nhóm | Vai trò trong cấu hình Spring | Khi nào cần |
| --- | --- | --- | --- |
| `org.springframework:spring-aop` | Spring Framework | API và hạ tầng proxy AOP, advisor, pointcut, auto-proxy | Cơ bản cho Spring AOP; thường được starter hoặc `spring-context` kéo theo. |
| `org.springframework:spring-context` | Spring Framework | ApplicationContext, quản lý bean và cấu hình Java `@Configuration` | Ứng dụng Spring thuần; thường đã có trong ứng dụng Spring Boot. |
| `org.aspectj:aspectjweaver` | AspectJ | Các class AspectJ và pointcut parser/matcher dùng cho Spring `@AspectJ` | Cần trên classpath khi khai báo Spring aspect bằng `@Aspect`/`@Before`/`@Around` và dùng `@EnableAspectJAutoProxy`. |
| `org.springframework.boot:spring-boot-starter-aop` | Spring Boot 3.x | Starter kéo những dependency cần cho Spring AOP dùng `@AspectJ` | Cách thêm AOP thông thường ở ứng dụng Boot 3.x. |
| `org.springframework.boot:spring-boot-starter-aspectj` | Spring Boot 4.x | Starter dành cho AOP với AspectJ, kéo `spring-aop` và `aspectjweaver` | Cách thêm AOP thông thường ở ứng dụng Boot 4.x. |
| `org.springframework:spring-aspects` | Spring Framework | Bộ aspect do Spring cung cấp cho các trường hợp sử dụng AspectJ weaving như `@Configurable` hoặc transaction aspect tương ứng | Chỉ khi cấu hình thật sự sử dụng các aspect này; **không cần** cho custom `@Aspect` proxy thông thường. |
| `org.springframework:spring-instrument` | Spring Framework | Instrumentation agent của Spring cho các cấu hình load-time weaving phù hợp | Chỉ khi chọn đường LTW dùng agent/instrumentation của Spring. |
| `org.aspectj:aspectjtools` | AspectJ | Công cụ compiler `ajc` cho AspectJ compile-time/post-compile weaving | Chỉ khi build được thiết kế để weaving; không cần cho Spring proxy AOP. |

**Hai ý dễ nhầm nhất:**

1. **Thêm `aspectjweaver` để Spring đọc `@Aspect` không đồng nghĩa bật weaving.** Spring vẫn gọi method thông qua proxy; self-invocation không tự được advice.
2. **`spring-aspects` khác `spring-aop`.** Đừng thêm `spring-aspects` chỉ vì cần `@Aspect`. Custom Spring aspect với `@Aspect` thường sử dụng `spring-aop` và `aspectjweaver` mà không cần `spring-aspects`.

Tùy phiên bản và dependency graph, một số thư viện đã có **bắc cầu (transitive)**. Mục tiêu là xác nhận **runtime classpath chứa đúng module cần thiết**, tránh thêm các phiên bản lẻ xung đột với hệ sinh thái Spring đang quản lý.

## 3. Chọn dependency theo kịch bản

| Cấu hình đã chọn | Dependency nên khai báo | Cách kích hoạt |
| --- | --- | --- |
| **Spring Boot 3.x + custom `@Aspect`** | `spring-boot-starter-aop` | Boot auto-configuration; đăng ký `@Aspect` thành bean `@Component` hoặc `@Bean`. |
| **Spring Boot 4.x + custom `@Aspect`** | `spring-boot-starter-aspectj` | Boot auto-configuration; đăng ký aspect bean. |
| **Spring Framework thuần + `@Aspect`** | `spring-context`, `spring-aop`, `aspectjweaver` (trực tiếp hoặc transitive theo dependency management) | `@EnableAspectJAutoProxy` trong cấu hình Spring; đăng ký aspect bean. |
| **Spring Framework thuần + Spring AOP API kiểu `ProxyFactory`/`MethodInterceptor`** | `spring-aop` cùng các module Spring mà ứng dụng thực sự dùng | Cấu hình proxy/advisor thủ công; có thể không cần `aspectjweaver` nếu không sử dụng parser hoặc annotation AspectJ. |
| **Spring + AspectJ weaving theo yêu cầu đặc biệt** | Spring AOP/integration và `aspectjweaver`; có thể thêm `spring-aspects`, `spring-instrument` hoặc công cụ biên dịch tương ứng | Có cấu hình weaving và agent/compiler riêng; thêm dependency là chưa đủ. |

**Quy tắc lựa chọn:** nếu chỉ cần advice trên **phương thức Spring bean được gọi qua proxy**, hãy chọn ba dòng đầu tùy nền tảng. Chỉ xét weaving khi có yêu cầu kỹ thuật đã xác nhận vượt quá mô hình proxy, chẳng hạn intercept self-invocation hoặc đối tượng ngoài Spring container.

## 4. Spring Boot 3.x: dùng `spring-boot-starter-aop`

Một ứng dụng đang dùng parent/BOM của **Spring Boot 3.x** thường chỉ cần bổ sung **một starter**, bởi starter quản lý chuỗi dependency cần thiết để Spring AOP làm việc. Không cần tự ghi version riêng cho `spring-aop` và `aspectjweaver` nếu chúng đã được Boot quản lý.

### Maven

Trong `pom.xml` có parent hoặc dependency management của Boot 3.x:

```xml
<dependencies>
    <!-- Các starter khác của ứng dụng -->

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
</dependencies>
```

### Gradle Groovy DSL

Trong `build.gradle` đã áp dụng Spring Boot plugin/BOM phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

### Gradle Kotlin DSL

Trong `build.gradle.kts` đã áp dụng Spring Boot plugin/BOM:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
```

**Điều kiện đi kèm:** aspect phải được Spring đăng ký thành bean; thường là `@Aspect` **kết hợp** `@Component` trong package nằm dưới component scan, hoặc khai báo bằng `@Bean`. Chỉ gắn `@Aspect` vào một class nhưng không đăng ký bean chưa đủ để Spring áp dụng nó.

Với Boot auto-configuration và thư viện AspectJ phù hợp có trên classpath, hạ tầng aspect auto-proxy được bật tự động. Trong trường hợp chuẩn này, không cần lặp lại `@EnableAspectJAutoProxy`. Boot mặc định sử dụng class-based proxy; có thể thay bằng cấu hình `spring.aop.proxy-target-class=false` khi cần chiến lược JDK interface proxy và đối tượng phù hợp.

## 5. Spring Boot 4.x: dùng `spring-boot-starter-aspectj`

**Tên starter thay đổi theo dòng Spring Boot.** Trong Boot 4.x, starter được tài liệu chính thức liệt kê là `spring-boot-starter-aspectj`, chứa các thành phần cho Spring AOP và AspectJ. Khi nâng cấp project từ Boot 3 lên Boot 4, phải rà lại tên dependency, không chép nguyên cấu hình chỉ dành cho Boot 3.

### Maven

Trong một ứng dụng có parent/BOM của **Boot 4.x**:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aspectj</artifactId>
</dependency>
```

### Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aspectj'
}
```

### Gradle Kotlin DSL

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aspectj")
}
```

Starter tên là `aspectj` **không tự biến `@Aspect` của Spring Boot thành AspectJ weaving**. Ứng dụng chỉ dùng hạ tầng proxy nếu không cấu hình thêm AspectJ weaving. Khả năng và giới hạn self-invocation/đối tượng không phải bean vẫn là của Spring proxy AOP.

**Không chọn starter bằng cách đoán từ chữ “AspectJ”.** Kiểm tra dòng Boot trong `pom.xml`, Gradle plugins hoặc BOM trước, rồi chọn artifact ứng với dòng đang sử dụng.

## 6. Spring Framework thuần: khai báo tường minh Spring AOP và AspectJ

Nếu ứng dụng sử dụng Spring Framework trực tiếp, không có Spring Boot auto-configuration, cần có **classpath phù hợp** và **bật auto-proxy bằng cấu hình Spring**.

Ví dụ `build.gradle` dưới đây là một **bộ phiên bản mẫu xác định** để người học thử Spring 6.1 trên JDK 17, không phải tuyên bố đây là bản mới nhất:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.14')

    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-aop'
    implementation 'org.aspectj:aspectjweaver:1.9.22.1'
}

application {
    mainClass = 'com.example.aopdemo.DemoApp'
}
```

Ở đây:

- `spring-context` cung cấp `AnnotationConfigApplicationContext`, `@Configuration` và quản lý bean.
- `spring-aop` được liệt kê trực tiếp cho mục đích học tập, dù trong một số dependency graph nó đã tới qua `spring-context`; Gradle có thể hợp nhất dependency trùng module.
- `aspectjweaver` cho phép xử lý `@Aspect` và biểu thức pointcut. Nó có version mẫu minh bạch vì **Spring Framework BOM không mặc nhiên là bộ quản lý phiên bản cho mọi thư viện bên ngoài Spring**.
- `@EnableAspectJAutoProxy` là cấu hình cần có cho ví dụ Spring thuần sử dụng `@AspectJ`, khác với Spring Boot được auto-configure.

Với Maven Spring thuần, nguyên tắc cũng như vậy: quản lý version Spring qua BOM hoặc project parent, khai báo các dependency Spring cần thiết và `org.aspectj:aspectjweaver` có version tương thích. Không trộn tùy tiện Spring Framework 6 và 7 hoặc các version do những BOM cạnh tranh quản lý.

### Cấu hình bật proxy trong Spring thuần

```java
package com.example.aopdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AopConfig {
    @Bean
    public TransferService transferService() {
        return new TransferService();
    }

    @Bean
    public TraceAspect traceAspect() {
        return new TraceAspect();
    }
}
```

Ở ví dụ này, `proxyTargetClass = true` dùng class-based proxy cho `TransferService` không triển khai interface; nếu bỏ tham số và bean có interface, chiến lược proxy có thể khác. `@Bean` bảo đảm bean aspect được đăng ký mà không yêu cầu `@ComponentScan`.

Tùy ứng dụng, XML tương đương cho kích hoạt kiểu `@AspectJ` là `<aop:aspectj-autoproxy />` trong namespace `aop`; nó cũng kích hoạt **Spring proxy auto-configuration**, không kích hoạt AspectJ weaving.

## 7. Ví dụ có thể chạy: kiểm chứng dependency thực sự hoạt động

Để dễ theo dõi cả nội dung dependency và đầu ra, ví dụ nhỏ sử dụng **Spring Boot 3.5.7, Java 17+**, có thể thay parent thành một bản Boot 3.x được dự án quản lý. Đây là một project Maven độc lập, không cần web server.

### Cấu trúc project

```text
spring-aop-dependencies/
├── pom.xml
└── src/main/java/com/example/aopdemo/
    ├── DemoApplication.java
    ├── TransferService.java
    └── TraceAspect.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-aop-dependencies</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### `src/main/java/com/example/aopdemo/DemoApplication.java`

```java
package com.example.aopdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service) {
        return args -> service.transfer("TR-101");
    }
}
```

### `src/main/java/com/example/aopdemo/TransferService.java`

```java
package com.example.aopdemo;

import org.springframework.stereotype.Service;

@Service
public class TransferService {
    public void transfer(String transactionId) {
        System.out.println("[SERVICE] transfer " + transactionId);
    }
}
```

### `src/main/java/com/example/aopdemo/TraceAspect.java`

```java
package com.example.aopdemo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    @Before("execution(public * com.example.aopdemo.TransferService.transfer(..))")
    public void trace(JoinPoint joinPoint) {
        System.out.println("[AOP] before " + joinPoint.getSignature().getName());
    }
}
```

Chạy trong thư mục `spring-aop-dependencies` với JDK 17+ và Maven đã cài:

```bash
mvn spring-boot:run
```

Trong stdout sẽ có các dòng sau theo thứ tự (ngoài banner và log khởi động do Spring Boot sinh ra):

```text
[AOP] before transfer
[SERVICE] transfer TR-101
```

**Vì sao kết quả chứng minh đúng cấu hình?**

1. `spring-boot-starter-aop` cung cấp classpath phục vụ Spring AOP và hỗ trợ `@AspectJ`.
2. Spring Boot kích hoạt cấu hình proxy tương ứng; `TransferService` và `TraceAspect` đều là Spring beans do component scan nhận ra.
3. `@Before` khớp lời gọi từ `CommandLineRunner` đến phương thức `TransferService.transfer()` qua bean Spring, nên dòng `[AOP]` chạy trước dòng `[SERVICE]`.
4. Chương trình không cần Spring MVC, HTTP controller, AspectJ compiler hay weaving agent để minh họa cơ chế này.

Thí nghiệm đối chiếu: khi **tạm bỏ `@Aspect` hoặc bỏ bean aspect khỏi component scan**, code nghiệp vụ `[SERVICE]` vẫn chạy nhưng không còn dòng `[AOP]`. Nếu thay lời gọi `service.transfer(...)` bằng `new TransferService().transfer(...)`, lời gọi đến đối tượng được tạo ngoài container không đi qua proxy nên cũng không kích hoạt advice. Chỉ dùng thí nghiệm này để kiểm tra, rồi trả project về cấu hình ban đầu.

## 8. Khi nào cần `spring-aspects`, `spring-instrument` hoặc công cụ weaving?

Đây là nhánh nâng cao, **khác với setup Spring AOP thông thường**. Việc thêm `spring-aspects` hoặc agent không nên là hành động mặc định.

### 8.1. `spring-aspects` dành cho aspect có sẵn của Spring dùng weaving

`org.springframework:spring-aspects` chứa một số aspect tích hợp do Spring cung cấp, ví dụ hỗ trợ `@Configurable` cho đối tượng được tạo ngoài Spring container và một số mô hình transaction dựa trên AspectJ. Những trường hợp đó cần **cấu hình weaving thực sự** và cơ chế Spring phù hợp.

Không dùng `spring-aspects` để “sửa” vấn đề custom `@Aspect` không chạy. Trước tiên hãy kiểm tra bean registration, proxy, pointcut và đường gọi. Thêm jar `spring-aspects` riêng lẻ sẽ không tự biến custom aspect thành weaving.

### 8.2. `spring-instrument` dành cho đường Spring load-time weaving phù hợp

Khi chủ động chọn **load-time weaving**, có thể cần `org.springframework:spring-instrument` nếu dùng agent instrumentation do Spring cung cấp. Một số cấu hình lại dùng trực tiếp AspectJ weaving agent với `aspectjweaver`. Lựa chọn agent thuộc kiến trúc runtime, không phải bước thiết lập mặc định của Spring AOP.

Nếu chọn LTW, còn phải xem xét `META-INF/aop.xml`, classloader, cách gắn agent vào JVM và quy trình kiểm thử. **Classpath có `aspectjweaver` không đủ để khẳng định LTW đang hoạt động.**

### 8.3. Khi chỉ dùng Spring proxy, không cần `aspectjtools`

`org.aspectj:aspectjtools` chứa compiler `ajc`; đây là công cụ cho build/weaving của AspectJ. Một project chỉ dùng Spring AOP annotation và proxy không cần đưa `aspectjtools` vào runtime dependencies.

Trên một ứng dụng Spring, chỉ cân nhắc bộ công cụ weaving khi đã có yêu cầu thực tế như pointcut không thể biểu đạt bằng Spring proxy AOP, đối tượng phải được can thiệp ngoài container, hoặc cơ chế `@Configurable`/transaction weaving chuyên dụng.

## 9. Kiểm tra dependency graph và classpath thay vì đoán

### Maven

Tại root project:

```bash
mvn dependency:tree
```

Với **Boot 3.x**, kỳ vọng cây dependency có `spring-boot-starter-aop`, `spring-aop` và `aspectjweaver` thông qua các dependency trực tiếp hoặc bắc cầu.

Với **Boot 4.x**, tìm `spring-boot-starter-aspectj`, `spring-aop` và `aspectjweaver`.

Kiểm tra tiếp version được chọn khi thấy nhiều dependency cùng nhóm Spring:

```bash
mvn dependency:tree -Dverbose
```

Đầu ra chính xác tùy phiên bản Maven dependency plugin; `mvn dependency:tree` thường là đủ để xác định artifact có nằm trên cây classpath hay không.

### Gradle

Với Gradle Groovy hoặc Kotlin DSL:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-aop --configuration runtimeClasspath
./gradlew dependencyInsight --dependency aspectjweaver --configuration runtimeClasspath
```

Trên Windows PowerShell, thay `./gradlew` bằng `.\gradlew.bat`. `dependencyInsight` cho biết module được chọn theo đường dependency và cơ chế quản lý version nào.

**Đọc kết quả đúng cách:** thấy một artifact ở `compileClasspath` chưa chứng minh nó có mặt tại thời điểm ứng dụng chạy; cần kiểm tra **`runtimeClasspath`**, đặc biệt khi project có custom configurations, excludes hoặc executable packaging.

## 10. Lỗi phổ biến khi chọn thư viện Spring AOP

| Triệu chứng | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy package `org.aspectj.lang.annotation` khi biên dịch | Có thiếu `aspectjweaver`/dependency chứa API AspectJ trên compile classpath? | Thêm đúng starter theo Boot đang dùng hoặc khai báo AspectJ dependency cho Spring thuần; reload dependency. |
| Khởi động lỗi class liên quan `org.aspectj.weaver` hoặc pointcut parser | `aspectjweaver` có thực sự ở runtime classpath? | Kiểm tra tree/insight, exclusions và dependency scope; sửa đúng version do project quản lý. |
| `@Aspect` có nhưng advice không chạy | Aspect có là **Spring bean**? Đã bật auto-proxy với Spring thuần? Pointcut có khớp? Lời gọi đi qua proxy? | Kiểm tra lần lượt bean registration → enablement → pointcut → proxy boundary. |
| Boot 3 lên Boot 4 nhưng khai báo starter cũ | Artifact và version có thuộc cùng dòng Boot hiện tại? | Dùng starter và hướng dẫn chính thức của đúng dòng Boot. |
| Thêm `spring-aspects` nhưng custom advice vẫn không hoạt động | Có đang nhầm thư viện aspect weaving chuyên dụng với Spring proxy? | Quay về `spring-aop` + `aspectjweaver` và kiểm tra enablement/registration. |
| Thêm `aspectjweaver` mà self-invocation vẫn không được advice | Đang dùng Spring proxy hay AspectJ weaving thật sự? | Hiểu giới hạn Spring proxy, ưu tiên tách lời gọi sang bean khác khi phù hợp. |
| `NoSuchMethodError`, `ClassNotFoundException` sau nâng cấp | Có dependency Spring/AspectJ bị ép version không tương thích? | Đối chiếu BOM, dependency graph và loại bỏ override không cần thiết; không đoán nguyên nhân chỉ từ tên exception. |
| Advice chạy hai lần hoặc xuất hiện proxy ngoài dự kiến | Có nhiều cấu hình advisor, aspect hoặc proxy creator cùng tham gia? | Xem lại các bean `@Aspect`, cấu hình giao dịch/AOP, pointcut và thứ tự tạo proxy. |

**Phân biệt lỗi thư viện với lỗi kích hoạt:** nếu code `@Aspect` đã biên dịch, không thể kết luận ngay dependency đủ để advice chạy. Việc advice được thực thi còn cần bean aspect tồn tại trong context, Spring proxy được tạo, pointcut khớp và có lời gọi đi qua proxy.

## 11. Quy trình quyết định cho một project Spring đang có

1. **Xác định môi trường chạy:** Spring Boot 3.x, Boot 4.x, hay Spring Framework thuần. Kiểm tra parent/BOM/plugin mà project thực sự sử dụng.
2. **Xác định mô hình AOP:** Spring proxy `@Aspect` thường gặp, Spring AOP API tự dựng, hay AspectJ weaving được chọn có chủ đích.
3. **Chọn dependency tối thiểu:** Boot 3.x → `spring-boot-starter-aop`; Boot 4.x → `spring-boot-starter-aspectj`; Spring thuần + `@Aspect` → container, `spring-aop`, `aspectjweaver`.
4. **Để dependency management quản lý version:** giữ module Spring cùng hệ version được project/BOM công bố. Tránh trộn version Spring Framework 6/7 hoặc override AspectJ tùy tiện.
5. **Kích hoạt đúng hạ tầng:** Boot auto-configuration; Spring thuần dùng `@EnableAspectJAutoProxy` hay XML tương ứng.
6. **Đăng ký aspect thành Spring bean:** dùng `@Aspect` kết hợp `@Component`/component scan, hoặc `@Bean`.
7. **Kiểm tra runtime classpath và một lời gọi thật:** chạy ví dụ ngắn có thể đối chiếu stdout; nếu advice không chạy, lần lượt kiểm tra bean → pointcut → proxy thay vì thêm thư viện bừa.
8. **Chỉ mở rộng sang weaving nếu có nhu cầu:** ghi rõ cơ chế agent/compiler, thư viện bổ sung và kiểm thử riêng cho đường weaving.

### Nguồn chính thức để đối chiếu theo phiên bản

- Spring Framework — @AspectJ support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html
- Spring Framework — Enabling @AspectJ Support: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/aspectj-support.html
- Spring Framework — Using AspectJ with Spring Applications: https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html
- Spring Boot — Aspect-Oriented Programming: https://docs.spring.io/spring-boot/reference/features/aop.html
- Spring Boot 3.x — Build Systems/starters: https://docs.spring.io/spring-boot/3.4/reference/using/build-systems.html
- Spring Boot 4.x — Build Systems/starters: https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html

Với **Spring AOP áp dụng vào các bean thông thường**, kết quả thiết lập đúng được xác nhận bằng ba dấu hiệu: classpath chứa thư viện cần thiết, Spring đăng ký và proxy các bean phù hợp, và một lần gọi qua proxy thực sự chạy advice đúng yêu cầu. Thư viện chỉ là điều kiện đầu tiên; cấu hình Spring và đường gọi quyết định hành vi cuối cùng.
