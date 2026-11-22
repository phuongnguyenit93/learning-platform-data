# Phát hiện tên tham số: `-parameters`, `@P` và tương thích phiên bản trong Spring Security

> **Chủ đề:** Spring Security — Kiểm tra trước phương thức (`@PreAuthorize`). Bài này giải thích cách Spring Security đưa tham số Java vào ngữ cảnh SpEL, sự khác biệt giữa **biên dịch với `-parameters`**, gắn bí danh tường minh bằng **`@P`**, tùy chọn Spring Data `@Param`, các alias theo vị trí và các thay đổi quan trọng từ Spring Framework 6.1. Ví dụ dùng Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x và kiểm thử bảo mật.

## 1. Bài toán: SpEL cần biết `#owner` là tham số nào

Xét một service chỉ cho người gọi đọc dữ liệu của **chính họ**:

~~~java
@PreAuthorize("#owner == authentication.name")
public String readOwnProfile(String owner) {
    return "profile:" + owner;
}
~~~

Ở đây:

- `#owner` là **biến SpEL** được tạo từ tên tham số Java `owner` của method.
- `authentication.name` là tên danh tính **đã xác thực phía server**.
- Nếu Alice gọi `readOwnProfile("alice")` thì điều kiện đúng; nếu Alice gọi `readOwnProfile("bob")` thì phải bị từ chối.
- Điều kiện được kiểm **trước** khi target method chạy, miễn là `@EnableMethodSecurity` đã bật và lời gọi đi qua Spring-managed proxy.

Vấn đề nằm ở cách Spring biết rằng tham số đầu tiên thực sự tên là `owner`. **Tên tham số trong source code Java không luôn được giữ nguyên trong file `.class`**. Một method có thể được biên dịch và gọi bình thường dù reflection chỉ nhìn thấy tên `arg0`, không phải `owner`.

Nếu SpEL dùng `#owner` nhưng runtime không tìm được tên này, policy có thể đánh giá sai, từ chối, hoặc sinh lỗi SpEL tùy biểu thức/cấu hình. Không nên suy diễn rằng chỉ thấy **403** nghĩa là user thật sự thiếu quyền, cũng không được đổi sang `permitAll` để che lỗi tên tham số.

**Ba cách tiếp cận chính** sẽ được học:

1. Biên dịch Java bằng **`javac -parameters`** để giữ tên `owner` trong class metadata.
2. Dùng **`@P("alias")`** để công khai tên biến riêng cho Spring Security, không cần dựa vào tên gốc.
3. Dùng alias theo vị trí như **`#p0`**, **`#a0`** cho tham số đầu khi thật sự cần; bớt rõ nghĩa nếu chữ ký method thay đổi.

## 2. `@EnableMethodSecurity` và đường đi đến SpEL

Để kiểm tra `@PreAuthorize`, cần bật method-level authorization:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Trong Spring Security hiện đại, cấu hình trên đăng ký các interceptor của method security, trong đó có `AuthorizationManagerBeforeMethodInterceptor` cho `@PreAuthorize`. Khi controller/bean khác gọi service qua Spring AOP proxy:

~~~text
Caller → Spring proxy → @PreAuthorize
                               |
                               v
                    MethodInvocation (method, args)
                               |
                               v
                 MethodSecurityExpressionHandler
                               |
                               v
             EvaluationContext có authentication
               + các biến tham số được phát hiện
                               |
                     biểu thức SpEL
                         /         \
                       true        false
                        |             |
                        v             v
                   Target method   DENY
~~~

Spring Security sử dụng một `ParameterNameDiscoverer` để gán tên cho từng phần tử của mảng arguments. Thành phần mặc định được tài liệu gọi là **`DefaultSecurityParameterNameDiscoverer`**. Nó liên kết thông tin biên dịch hoặc annotation với các biến SpEL như `#owner`.

**Phân biệt hai lỗi:**

- *Lỗi phát hiện tên*: tham số đang có giá trị `"alice"`, nhưng `#owner` trong SpEL không được trỏ đúng.
- *Lỗi quyền thật*: `#owner` đã được resolve đúng thành `"bob"`, nhưng người gọi là Alice nên biểu thức từ chối.

Không dùng tên HTTP `@PathVariable` của controller để đoán tên của **tham số service**. Đó là **hai method khác nhau**, có bộ metadata/annotation khác nhau.

## 3. Thứ tự phát hiện tên tham số: ưu tiên nào được xét?

Theo tài liệu chính thức Spring Security 6.5, `DefaultSecurityParameterNameDiscoverer` sử dụng các cách sau:

| Cơ chế | Ví dụ | Ý nghĩa | Điều kiện |
| --- | --- | --- | --- |
| Spring Security **`@P`** | `@P("subject") String name` | Đặt tên biến SpEL `subject` | Dependency `spring-security-core` |
| Spring Data **`@Param`** | `@Param("subject") String name` | Đặt tên biến từ annotation Spring Data | Có Spring Data thích hợp trên classpath |
| Java Reflection **`-parameters`** | `String owner` → `#owner` | Giữ tên thực trong class metadata | Biên dịch class/interface bằng flag |
| Debug info cũ | Local variable table trong `-g` | Một số cơ chế legacy từng suy tên | **Không dựa vào cách này từ Spring Framework 6.1** |

**Chú ý ranh giới phiên bản:** Một số phần diễn giải cũ về method parameter discovery vẫn nhắc debug symbols như fallback. Nhưng migration guide của **Spring Security 6.5** nói rõ **Spring Framework 6.1 đã loại bỏ `LocalVariableTableParameterNameDiscoverer`**. Vì vậy với Spring Boot 3.2+/Spring Framework 6.1+ và các phiên bản mới hơn, **`-g` không thay cho `-parameters`** khi muốn SpEL dùng tên Java. Quy tắc an toàn khi nâng cấp: dùng `-parameters` hoặc annotation tên tường minh, đồng thời viết test.

### 3.1. Khi nào `@P` phù hợp nhất?

- Khi thư viện/service **không thể bảo đảm** bản build của module lưu tên Java.
- Khi muốn tên SpEL ổn định, độc lập với việc đổi tên tham số trong source.
- Khi interface do module khác biên dịch, cần gắn contract bảo mật tường minh.
- Khi cần đặt tên ngắn, rõ ý như `@P("document")` cho một object phức tạp.

### 3.2. Khi nào `-parameters` phù hợp nhất?

- Dự án Java mới do bạn kiểm soát hoàn toàn Maven/Gradle build.
- Muốn SpEL đọc được tên tự nhiên `#ownerId`, `#tenantId`, `#documentId`.
- Muốn giữ tên tham số cho nhiều framework cùng sử dụng Java reflection.
- Muốn tránh thêm `@P` vào hàng trăm method đã có tên diễn đạt tốt.

### 3.3. Spring Data `@Param` là lựa chọn có điều kiện

Nếu project đã có Spring Data, `org.springframework.data.repository.query.Param` có thể cung cấp tên cho Spring Security. **Đừng thêm Spring Data chỉ để thay `@P`** trong một service đơn giản. Dùng `@P` của Spring Security hoặc `-parameters` rõ ràng hơn, trừ khi dependency Spring Data đã là một phần của kiến trúc.

## 4. Java 17 thuần: chứng minh `-parameters` có tác dụng gì

Trước khi mở Spring Boot, hãy quan sát class metadata bằng Java Reflection. Chương trình này **biên dịch và chạy độc lập** bằng JDK 17+, không cần thư viện ngoài.

Tạo file **`ParameterNameProbe.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNameProbe {

    public static void findAccount(String account) {
        // Chỉ quan sát metadata, không chứa nghiệp vụ.
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterNameProbe.class.getDeclaredMethod(
            "findAccount", String.class
        );
        Parameter param = method.getParameters()[0];

        System.out.println("name=" + param.getName());
        System.out.println("present=" + param.isNamePresent());
    }
}
~~~

### 4.1. Biên dịch **có** `-parameters`

~~~bash
javac -parameters ParameterNameProbe.java
java ParameterNameProbe
~~~

**Stdout chính xác:**

~~~text
name=account
present=true
~~~

`javac` thêm attribute **`MethodParameters`** vào class file. Java reflection vì thế trả tên `account` mà source method khai báo.

### 4.2. Biên dịch **không có** `-parameters`

~~~bash
javac ParameterNameProbe.java
java ParameterNameProbe
~~~

**Stdout thông thường với JDK 17:**

~~~text
name=arg0
present=false
~~~

Nếu chỉ thêm `-g`:

~~~bash
javac -g ParameterNameProbe.java
java ParameterNameProbe
~~~

Java reflection vẫn **không** tự nhận `account` qua `Parameter#getName()` nếu thiếu `MethodParameters`. `-g` có thể thêm debug LocalVariableTable, nhưng đó là loại metadata **khác**. Đây chính là khác biệt dễ gây sự cố sau Spring Framework 6.1.

**Lưu ý chạy lại:** mỗi lần `javac` trong các lệnh trên sẽ ghi lại file `ParameterNameProbe.class`, rồi `java` chạy bản mới biên dịch. Không trộn kết quả từ một JAR/classpath cũ.

### 4.3. Phương pháp xem bytecode

Với class đã được biên dịch:

~~~bash
javap -v ParameterNameProbe
~~~

Tìm thuộc tính `MethodParameters` trong output. Khi có `-parameters`, thông tin tên `account` được ghi vào class file. Khi thiếu flag, chỉ nhìn bảng `LocalVariableTable` (nếu có) **không đủ** để kết luận Java reflection trong ứng dụng Spring Framework 6.1+ sẽ thấy tên tham số.

**Kết luận kỹ thuật:** `-parameters` là **compiler flag**, không phải JVM runtime option. Việc chạy `java -parameters ...` sẽ không sửa class file đã được biên dịch thiếu metadata.

## 5. Cấu hình Maven để giữ tên tham số

Nếu dùng parent **`spring-boot-starter-parent`** phiên bản Spring Boot 3.x, parent thường đã cấu hình biên dịch với `-parameters`. Tuy nhiên, **không nên đoán** nếu project chỉ import Boot BOM, dùng parent riêng, module Gradle khác, plugin bị override hoặc code đến từ JAR thứ ba.

### 5.1. Cấu hình rõ ràng trong Maven Compiler Plugin

Trong `pom.xml`, ví dụ fragment:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>17</release>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`<parameters>true</parameters>` yêu cầu Maven Compiler Plugin chuyển flag cần thiết vào compiler. `<release>17</release>` giữ API/bytecode tương thích với Java 17. Đây là **fragment build**; nếu POM đã có compiler plugin, **hợp nhất cấu hình**, không tạo bản plugin trùng.

Trong project dùng Boot parent mặc định, fragment này có thể không cần vì parent cung cấp mặc định. Với một **multi-module Maven** project, kiểm tra cả module chứa **interface/service đã được compile** chứ không chỉ module web cuối cùng.

### 5.2. Kiểm tra bản build hiệu lực

~~~bash
# Từ Maven project root (Linux/macOS):
./mvnw clean test

# Xem cấu hình Maven đã được kế thừa:
./mvnw help:effective-pom
~~~

Trên Windows có thể dùng `mvnw.cmd clean test` và `mvnw.cmd help:effective-pom`.

Sau đó kiểm tra class đã được compile bằng `javap` hoặc một test reflection. Một dấu hiệu an toàn hơn việc tìm chuỗi ở POM là:

~~~java
// Fragment trong JUnit test:
Method method = OwnerService.class.getMethod(
    "readNamed", String.class
);
assertTrue(method.getParameters()[0].isNamePresent());
assertEquals("account", method.getParameters()[0].getName());
~~~

Các tên `OwnerService`/`readNamed` khớp ứng dụng demo ở mục 10. Fragment cần imports `java.lang.reflect.Method` và `org.junit.jupiter.api.Assertions.*`, và dùng **class file thực** được test compile.

### 5.3. Vì sao cần `clean` khi debug?

Nếu module được biên dịch trước khi thêm `-parameters` rồi incremental build không biên dịch lại class, class cũ có thể vẫn thiếu attribute. Một lượt **clean build** giúp bạn biết metadata đang được tạo từ cấu hình mới. Đừng kỳ vọng thay compiler flag mà không rebuild các JAR thư viện phụ thuộc sẽ sửa tên tham số bên trong những JAR đó.

## 6. Gradle: bật flag đúng cho module Java

Với **Groovy DSL `build.gradle`**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

Nếu dùng Gradle Kotlin DSL `build.gradle.kts`:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Đây là **fragment** trong một project Gradle Java có plugin phù hợp và `JavaCompile` được import/tự có trong DSL. Cấu hình tác động lên các `JavaCompile` tasks thuộc module đang khai báo. Với multi-module, cần đặt ở từng module Java liên quan hoặc trong convention plugin phù hợp.

Sau khi sửa:

~~~bash
./gradlew clean test
~~~

Trên Windows dùng `gradlew.bat clean test`. Kiểm tra reflection với `Parameter#getName()` thay vì chỉ thấy build thành công.

### Không nhầm Java, Kotlin và Java records

- Java compiler flag `-parameters` dành cho **Java source**. Kotlin có cơ chế metadata và plugin riêng; không mặc định dùng `JavaCompile` để điều khiển toàn bộ Kotlin compilation.
- Java record có metadata riêng cho record components; **đừng suy từ record component names rằng mọi method Java đều có parameter names**.
- Với mixed-source Java/Kotlin và module libraries, kiểm tra compiler thực tế của từng source set, đặc biệt các service method có `@PreAuthorize`.
- Khi dùng interface và JDK dynamic proxy, metadata tại interface hoặc annotation `@P` có thể quyết định việc bind tên. Biên dịch mỗi module sở hữu interface một cách nhất quán.

## 7. Dùng `@P` khi muốn bí danh tham số tường minh

Import chính xác:

~~~java
import org.springframework.security.access.method.P;
~~~

Một service có thể dùng:

~~~java
@PreAuthorize("#subject == authentication.name")
public String readByAlias(@P("subject") String account) {
    return "subject:" + account;
}
~~~

Ở đây:

- Source parameter tên **`account`**.
- Spring Security `@P("subject")` khai báo tên biến SpEL là **`subject`**.
- Expression đọc `#subject`, **không** phải `#account`.
- Không cần dựa vào metadata `-parameters` để biết **bí danh** đó.

Có thể đổi tên tham số Java từ `account` thành `requestedAccount` mà biểu thức `#subject` vẫn đúng, miễn là annotation `@P("subject")` và method contract giữ nguyên.

### Lỗi sai bí danh

~~~java
// SAI: annotation đặt alias "subject" nhưng SpEL hỏi "user":
@PreAuthorize("#user == authentication.name")
public String read(@P("subject") String account) {
    return "private";
}
~~~

Trong ví dụ một tham số, `#user` không được annotation trên định nghĩa. Spring không tự đoán rằng `subject` và `user` cùng ý nghĩa. Khi SpEL không lấy được giá trị, kết quả có thể là DENY hoặc lỗi tùy biểu thức. **Không được sửa lỗi bằng cách bỏ annotation bảo mật**.

### Nhiều tham số với `@P`

~~~java
@PreAuthorize("#subject == authentication.name and #documentId.startsWith('DOC-')")
public String readDocument(
        @P("subject") String account,
        @P("documentId") String id
) {
    return account + ":" + id;
}
~~~

Với method có nhiều tham số, **chú thích đầy đủ những tham số được tham chiếu** để tên không phụ thuộc một fallback khác. Nếu một discoverer ưu tiên annotation đã có, một tham số còn lại không có alias có thể không được resolve theo cách bạn tưởng. Test mọi biến SpEL sau khi thêm/sửa tham số.

**`@P` của Spring Security không phải `@PathVariable` hay `@RequestParam` của Spring MVC**. Một cái đặt tên cho method-security evaluation context; hai cái còn lại bind dữ liệu HTTP cho tham số controller. Chúng không tự thay thế nhau.

## 8. Spring Data `@Param`: có ích nhưng không phải phụ thuộc bắt buộc

Tài liệu Spring Security cũng nêu cơ chế nhận biết `org.springframework.data.repository.query.Param` khi annotation đó có trên classpath:

~~~java
import org.springframework.data.repository.query.Param;

@PreAuthorize("#owner == authentication.name")
public String readOwner(@Param("owner") String account) {
    return "owner:" + account;
}
~~~

Đây là fragment cần dependency Spring Data tương ứng. Trong một repository/service đã sử dụng Spring Data, `@Param` có thể đồng thời là metadata cho truy vấn repository và cho security expression. Nhưng:

1. **Không thêm Spring Data chỉ để có một annotation tên**, vì `@P` đã nằm trong Spring Security.
2. Đừng nhầm `@Param` của Spring Data với `@Param` của một thư viện khác có cùng tên đơn giản.
3. Nếu cùng method đặt nhiều loại annotation cung cấp tên, cần biết thứ tự discoverer và test name mapping cụ thể.
4. Biểu thức SpEL không tự biết tên từ SQL placeholder hay JSON field; nó cần metadata của **method đang bị intercept**.

## 9. Alias theo vị trí: `#p0` và `#a0`

Ngữ cảnh đánh giá method của Spring có thể cung cấp tham số dưới alias theo vị trí:

| Biến | Nghĩa |
| --- | --- |
| `#p0` | Tham số thứ nhất (index 0) |
| `#a0` | Alias khác của tham số thứ nhất |
| `#p1` | Tham số thứ hai (index 1) |
| `#a1` | Alias khác của tham số thứ hai |
| `#owner` | Chỉ tồn tại khi metadata/annotation gán tên `owner` |

Ví dụ:

~~~java
@PreAuthorize("#p0 == authentication.name")
public String readByIndex(String account) {
    return "index:" + account;
}
~~~

Đoạn này không cần compiler giữ tên `account` để truy cập **tham số đầu**. Cần hiểu đây là **alias theo thứ tự**, không phải metadata đã được khôi phục.

**Mặt trái:** nếu đổi chữ ký thành:

~~~java
public String readByIndex(String locale, String account)
~~~

thì `#p0` giờ là `locale`, không còn `account`. Nếu quên đổi policy sang `#p1`, bạn có thể tạo lỗi chặn sai hoặc cấp quyền sai. Với policy nhạy cảm dài hạn, tên rõ nghĩa qua `-parameters` hoặc `@P` thường an toàn hơn.

Đừng nhầm `#p0` với `@P("p0")`; chúng thuộc hai cơ chế khác nhau. Các property `authentication.name` và `principal` thường xuất phát từ security expression root, **không** phải tham số Java của method.

## 10. Ứng dụng Spring Boot Java 17+ chạy được

### 10.1. Đặc tả bài toán

Ta sẽ xây một API có các đường:

| Request | Gọi service | Cách lấy tên tham số |
| --- | --- | --- |
| `GET /api/named/{account}` | `readNamed(String account)` | `-parameters` → `#account` |
| `GET /api/annotated/{account}` | `readAnnotated(@P("subject") String account)` | `@P` → `#subject` |
| `GET /api/positional/{account}` | `readPositional(String account)` | `#p0` |
| `GET /api/pair/{account}/{documentId}` | `readPair(@P...,...@P...)` | Hai alias tường minh |
| `GET /public/ping` | Public | Không cần method-security parameter |
| `GET /api/unknown` | Không có allow rule | HTTP default deny |

User mẫu:

| User | Authorities | Ý nghĩa |
| --- | --- | --- |
| `alice` | `ROLE_USER` | Được xem dữ liệu của chính Alice |
| `bob` | `ROLE_USER` | Được xem dữ liệu của chính Bob |
| `ops` | `owner:override` | Được vượt kiểm owner trên ba endpoint đơn giản, **không** tự vượt rule pair |

Khi Alice gọi `/api/named/alice`, service phải ALLOW. Khi Alice gọi `/api/named/bob`, service phải DENY. User `ops` được truy cập path của Alice/Bob qua authority `owner:override` ở ba rule có OR được khai báo.

### 10.2. Maven dependencies / compiler

Với project Maven Spring Boot **3.5.x**, Java 17+ chọn:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (test)
- `spring-security-test` (test)

Với Boot parent, `-parameters` thường được bật sẵn; vẫn phải kiểm bản build thực tế. Nếu dùng parent riêng, thêm `maven-compiler-plugin` với `<parameters>true</parameters>` như mục 5. Đây là điều kiện để ví dụ `readNamed` bind `#account` ổn định.

### 10.3. Mã application hoàn chỉnh

Tạo file **`src/main/java/com/example/parameters/ParameterBindingApplication.java`**:

~~~java
package com.example.parameters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class ParameterBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParameterBindingApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/named/**").authenticated()
                .requestMatchers("/api/annotated/**").authenticated()
                .requestMatchers("/api/positional/**").authenticated()
                .requestMatchers("/api/pair/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("USER")
            .build();

        UserDetails ops = User.withUsername("ops")
            .password(encoder.encode("demo789"))
            .authorities("owner:override")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, ops);
    }

    @Service
    public static class OwnerService {

        // Cần javac -parameters để #account có tên tương ứng.
        @PreAuthorize(
            "#account == authentication.name or hasAuthority('owner:override')"
        )
        public String readNamed(String account) {
            return "named:" + account;
        }

        // Bí danh "subject" không phụ thuộc tên Java "account".
        @PreAuthorize(
            "#subject == authentication.name or hasAuthority('owner:override')"
        )
        public String readAnnotated(@P("subject") String account) {
            return "annotated:" + account;
        }

        // Tham số thứ nhất, không cần metadata tên Java.
        @PreAuthorize(
            "#p0 == authentication.name or hasAuthority('owner:override')"
        )
        public String readPositional(String account) {
            return "positional:" + account;
        }

        // Hai tham số được gắn tên tường minh.
        @PreAuthorize(
            "#subject == authentication.name and #docId.startsWith('DOC-')"
        )
        public String readPair(
                @P("subject") String account,
                @P("docId") String documentId
        ) {
            return "pair:" + account + ":" + documentId;
        }
    }

    @RestController
    static class Api {

        private final OwnerService service;

        Api(OwnerService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/named/{account}")
        String named(@PathVariable("account") String account) {
            return service.readNamed(account);
        }

        @GetMapping("/api/annotated/{account}")
        String annotated(@PathVariable("account") String account) {
            return service.readAnnotated(account);
        }

        @GetMapping("/api/positional/{account}")
        String positional(@PathVariable("account") String account) {
            return service.readPositional(account);
        }

        @GetMapping("/api/pair/{account}/{documentId}")
        String pair(
                @PathVariable("account") String account,
                @PathVariable("documentId") String documentId
        ) {
            return service.readPair(account, documentId);
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "should not be reached";
        }
    }
}
~~~

### 10.4. Những gì mỗi phần thực sự chứng minh

1. `@EnableMethodSecurity` bật `@PreAuthorize`. HTTP filter chỉ kiểm người gọi đã đăng nhập trên bốn prefix API, còn **owner check** nằm ở service.
2. `readNamed(String account)` dùng `#account`: muốn nhận đúng tên Java cần `-parameters` ở class thực sự được compile.
3. `readAnnotated(@P("subject") String account)` dùng `#subject`, chứng minh **bí danh** có thể khác tên biến Java.
4. `readPositional(String account)` dùng `#p0`, chứng minh cách tham chiếu tham số **theo index**.
5. `readPair(...)` cho thấy hai annotation `@P` với tên khác nhau được dùng trong cùng một biểu thức.
6. `@PathVariable("account")` ở controller được khai báo tên **tường minh** để Spring MVC không phải suy đoán tên path variable. Nhưng nó **không tự bảo đảm** tên của tham số service.
7. Controller gọi qua `OwnerService` do Spring inject, nên AOP proxy có thể áp dụng annotation. Không gọi `new OwnerService()` hoặc `this.readNamed(...)` từ bên trong target service.
8. `UserDetailsService` cấp danh tính và authorities server-side. URL chứa `alice` do client chọn, nên **phải so với `authentication.name`**, không tin tham số path.
9. `anyRequest().denyAll()` chặn URL mới chưa có chính sách, kể cả nếu controller tồn tại.
10. Các endpoint đều dùng GET để tránh trộn lỗi CSRF với lỗi method-security parameter.

**An toàn demo:** mật khẩu hardcode chỉ để học; HTTP Basic cần HTTPS trong hệ thống thật. Kiểm tra `owner` theo tên trong ví dụ là mô phỏng đơn giản, không thay thế tenant/ACL/domain policy khi quản lý dữ liệu thật.

## 11. Ma trận yêu cầu và kết quả HTTP kỳ vọng

Giả sử build đã lưu `-parameters` đúng cách, không có custom filter/exception handler khác và HTTP Basic được sử dụng:

| HTTP request | Alice | Bob | Ops | Lý do |
| --- | :---: | :---: | :---: | --- |
| `GET /api/named/alice` | **200** | 403 | **200** | `#account` từ Java metadata |
| `GET /api/named/bob` | 403 | **200** | **200** | Owner hoặc authority override |
| `GET /api/annotated/alice` | **200** | 403 | **200** | `@P("subject")` |
| `GET /api/annotated/bob` | 403 | **200** | **200** | Alias `subject` |
| `GET /api/positional/alice` | **200** | 403 | **200** | `#p0` |
| `GET /api/positional/bob` | 403 | **200** | **200** | Tham số index 0 |
| `GET /api/pair/alice/DOC-42` | **200** | 403 | 403 | Cả hai điều kiện AND |
| `GET /api/pair/bob/DOC-42` | 403 | **200** | 403 | Owner và docId |
| `GET /api/pair/alice/IMG-42` | 403 | 403 | 403 | docId không có prefix DOC- |
| `GET /api/unknown` | 403 | 403 | 403 | HTTP default deny |

Anonymous gọi bốn endpoint bảo vệ thường nhận **401** trong ví dụ HTTP Basic; public ping trả **200**. Một người đã xác thực thiếu quyền thường nhận **403**. Nếu method SpEL không tìm được biến vì thiếu metadata, kết quả có thể là lỗi đánh giá expression hoặc DENY — **không khẳng định cứng sẽ luôn là 403**, hãy kiểm logs/tests.

### Chạy thử bằng curl

~~~bash
# macOS/Linux: khởi chạy ở root Maven project.
./mvnw spring-boot:run

# Windows:
mvnw.cmd spring-boot:run
~~~

Khi server chạy trên `http://localhost:8080`:

~~~bash
# Công khai:
curl -i http://localhost:8080/public/ping

# Alice xem dữ liệu chính mình ở ba cách binding:
curl -i -u alice:demo123 http://localhost:8080/api/named/alice
curl -i -u alice:demo123 http://localhost:8080/api/annotated/alice
curl -i -u alice:demo123 http://localhost:8080/api/positional/alice

# Alice không được giả làm Bob:
curl -i -u alice:demo123 http://localhost:8080/api/named/bob
curl -i -u alice:demo123 http://localhost:8080/api/annotated/bob

# Ops được phép trên ba rule có owner:override:
curl -i -u ops:demo789 http://localhost:8080/api/named/bob

# Hai @P: owner đúng và docId hợp lệ:
curl -i -u alice:demo123 http://localhost:8080/api/pair/alice/DOC-42
curl -i -u alice:demo123 http://localhost:8080/api/pair/alice/IMG-42

# Không có allow rule:
curl -i -u alice:demo123 http://localhost:8080/api/unknown
~~~

Body của các request được phép lần lượt là `pong`, `named:alice`, `annotated:alice`, `positional:alice`, `named:bob` (Ops), `pair:alice:DOC-42`. Các body khác do ứng dụng trả ra không phải bằng chứng riêng cho tính đúng của metadata; điều quan trọng là ma trận ALLOW/DENY và kiểm tra tên tham số qua reflection.

## 12. MockMvc/JUnit 5: kiểm security rule và metadata cùng lúc

### 12.1. Test dependencies

Trong `pom.xml`, các fragment dưới `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu có sẵn `spring-boot-starter-test`, không thêm bản trùng. Để test `@P` không cần thêm Spring Data.

### 12.2. Test class hoàn chỉnh

Tạo file **`src/test/java/com/example/parameters/ParameterBindingApplicationTests.java`**:

~~~java
package com.example.parameters;

import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ParameterBindingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void javacRetainsRealParameterName() throws Exception {
        Method method =
            ParameterBindingApplication.OwnerService.class.getMethod(
                "readNamed", String.class
            );
        assertTrue(method.getParameters()[0].isNamePresent());
        assertEquals("account", method.getParameters()[0].getName());
    }

    @ParameterizedTest
    @CsvSource({
        // user,password,path,expectedStatus
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/named/alice,401",

        "alice,demo123,/api/named/alice,200",
        "alice,demo123,/api/named/bob,403",
        "bob,demo456,/api/named/bob,200",
        "bob,demo456,/api/named/alice,403",
        "ops,demo789,/api/named/alice,200",

        "alice,demo123,/api/annotated/alice,200",
        "alice,demo123,/api/annotated/bob,403",
        "bob,demo456,/api/annotated/bob,200",
        "ops,demo789,/api/annotated/alice,200",

        "alice,demo123,/api/positional/alice,200",
        "alice,demo123,/api/positional/bob,403",
        "bob,demo456,/api/positional/bob,200",
        "ops,demo789,/api/positional/alice,200",

        "alice,demo123,/api/pair/alice/DOC-42,200",
        "alice,demo123,/api/pair/alice/IMG-42,403",
        "alice,demo123,/api/pair/bob/DOC-42,403",
        "bob,demo456,/api/pair/bob/DOC-42,200",
        "ops,demo789,/api/pair/alice/DOC-42,403",

        "alice,demo123,/api/unknown,403"
    })
    void parameterAuthorizationMatrix(
            String user, String password, String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder request = get(path);
        if (!"anonymous".equals(user)) {
            request.with(httpBasic(user, password));
        }
        mvc.perform(request).andExpect(status().is(expected));
    }

    @Test
    void aliasNameAndJavaParameterNameAreDistinct()
            throws Exception {
        mvc.perform(get("/api/annotated/alice")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("annotated:alice"));
    }

    @Test
    void namedParameterReallyReadsTheCorrectArgument()
            throws Exception {
        mvc.perform(get("/api/named/bob")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordFailsAuthentication() throws Exception {
        mvc.perform(get("/api/named/alice")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Bộ test này chứng minh hai việc độc lập:**

1. `javacRetainsRealParameterName()` kiểm **metadata thật trong class được compile**, không chỉ kiểm rằng ứng dụng trả 200/403.
2. `parameterAuthorizationMatrix(...)` kiểm **phép gắn biến SpEL có ảnh hưởng đúng lên quyết định quyền**, với cả trường hợp ALLOW và DENY.

Nếu một người đổi tên tham số `account` thành `username` nhưng quên sửa biểu thức `#account`, test sẽ phát hiện qua reflection hoặc hành vi. Nếu chỉ kiểm Alice gọi URL Alice được 200, có thể bỏ sót policy bị mở rộng; cần kiểm Alice gọi URL của Bob phải 403 và Ops override phải đúng theo yêu cầu.

### 12.3. Test trực tiếp service với `@WithMockUser`

Có thể test method security mà không qua HTTP bằng cách inject **Spring-managed bean**, thay vì tự `new`:

~~~java
// Fragment trong một @SpringBootTest class:
@Autowired
ParameterBindingApplication.OwnerService service;

@Test
@WithMockUser(username = "alice")
void explicitPWorksWhenCalledThroughProxy() {
    assertEquals("annotated:alice", service.readAnnotated("alice"));
}
~~~

Đây là fragment bổ sung, cần import `org.springframework.security.test.context.support.WithMockUser`. `@WithMockUser` đặt Authentication giả lập cho test; nó **không** kiểm HTTP Basic/UserDetailsService, trong khi `httpBasic` của MockMvc thì có.

### 12.4. Chạy test

~~~bash
# Linux/macOS:
./mvnw clean test

# Windows:
mvnw.cmd clean test
~~~

Kỳ vọng các test pass với source, dependencies và compiler flags đã mô tả. Output Maven/JUnit phụ thuộc môi trường; không khẳng định đã chạy thực tế nếu chưa thực thi. Chú ý compiler option phải áp dụng lên **module có OwnerService.class**.

## 13. Interface, proxy và module biên dịch riêng

Một vấn đề thường chỉ xuất hiện khi triển khai: service interface nằm trong thư viện A, implementation nằm ở ứng dụng B, cả hai được build khác cấu hình.

Ví dụ interface:

~~~java
public interface AccountReader {
    @PreAuthorize("#owner == authentication.name")
    String read(String owner);
}
~~~

Đây là fragment, cần import `PreAuthorize`. Nếu interface đã biên dịch **không có `-parameters`**, Spring có thể không lấy được tên `owner` từ **method/interface đang được phân tích**, dù implementation source nhìn thấy tên giống hệt. Một số proxy và annotation-placement patterns còn ảnh hưởng method nào được kiểm.

**Thực hành an toàn:**

- Biên dịch **cả module API/interface** và implementation bằng `-parameters` nếu biểu thức dựa vào tên.
- Hoặc công khai contract bằng `@P`:
  
~~~java
public interface AccountReader {
    @PreAuthorize("#subject == authentication.name")
    String read(@P("subject") String owner);
}
~~~

Đây là fragment cần import `P` và `PreAuthorize`; nếu implementation tùy chỉnh proxy hoặc security annotation placement, **integration test chính là bằng chứng**.
- Khi dùng JDK dynamic proxy, interface có thể là phương thức phản chiếu được xét; tên tham số implementation không phải lúc nào cũng đủ.
- Khi dùng class-based proxy, cần xem method final/private và self-invocation; chúng là vấn đề **proxy/interception**, không phải tên SpEL.
- Thư viện đóng gói thành JAR có metadata cũ sẽ **không tự được sửa** khi app tiêu thụ thư viện bật `-parameters`. Phải rebuild **module gốc** hoặc dùng annotation alias ở source cho phép chỉnh sửa.

## 14. Tương thích phiên bản: phải đọc đúng nguồn nào?

| Nền tảng | Điều đáng nhớ |
| --- | --- |
| Java 8 trở lên | `javac -parameters` tạo metadata tên tham số cho reflection |
| Spring Security legacy (trước các migration hiện đại) | Một số cấu hình từng dựa vào debug local variable metadata, không nên coi là hợp đồng lâu dài |
| Spring Framework **6.1+** | Đã **loại bỏ `LocalVariableTableParameterNameDiscoverer`** |
| Spring Security **6.5** | Tài liệu mô tả `@P`, Spring Data `@Param`, `-parameters` và mechanism discovery; migration guide **nhấn mạnh cần `-parameters`** |
| Spring Boot 3.x / Spring Framework 6.x | Kiểm đúng phiên bản Framework bên dưới và cấu hình Java compiler của từng module |
| Spring Security 7+ / Spring Framework 7+ | Không mặc định mọi hành vi/API giống 6.5; kiểm tài liệu phiên bản đang dùng và chạy lại test |

### Khi tài liệu cũ nói “debug symbols vẫn dùng được” nhưng migration guide bảo “cần -parameters”

Ưu tiên thông tin dành cho **phiên bản framework đang chạy**. Với Spring Framework 6.1+, migration guide xác nhận cơ chế khám phá tên từ local variable table cũ đã bị gỡ; do đó:

- **Không coi `javac -g` là phương án thay thế đáng tin.**
- Dùng `-parameters` cho source do bạn kiểm soát.
- Dùng `@P` tại boundary cần alias tường minh hoặc khi không kiểm soát được tên Java.
- Viết **reflection test** để phát hiện thiếu attribute trước khi chạy một loạt test phân quyền.
- Viết **integration test** cho cả ALLOW và DENY. Một test classpath/JAR ở CI không tương ứng với artifact triển khai vẫn có thể khiến production chạy khác.

Đừng đoán một flag là có từ việc “máy developer chạy được”. Hãy đọc **effective build** và kiểm tra class file/JAR cuối cùng.

## 15. Những lỗi thiết kế và chẩn đoán 403 thường gặp

| Sai lầm | Hậu quả | Cách kiểm/khắc phục |
| --- | --- | --- |
| SpEL viết `#owner` nhưng class thiếu `-parameters` | Biến không được resolve như dự tính | Reflection test, bật compiler flag |
| Chỉ thêm `-g` | Debug info không thay thế MethodParameters trong Spring Framework 6.1+ | Chuyển sang `-parameters` |
| Chạy với flag trên JVM thay vì compiler | Không sửa metadata của `.class` | Cấu hình Maven/Gradle javac |
| Sửa parent POM nhưng module con override plugin | Module chứa service vẫn thiếu flag | Kiểm effective POM và class file |
| Gắn `@P("subject")` nhưng expression dùng `#owner` | Alias không khớp | Dùng `#subject` hoặc sửa annotation |
| Chỉ @P một tham số rồi dựa vào tên Java của tham số khác | Discoverer có thể trả metadata không như giả định | Gắn tên rõ ràng cho mọi biến được tham chiếu |
| Dùng Spring Data `@Param` mà module không có dependency phù hợp | Lỗi import hoặc không có discoverer như dự tính | Dùng Spring Security `@P` |
| Tin `@PathVariable("owner")` của controller đặt tên tham số service | Hai method độc lập | Gắn metadata ở service |
| Thêm tham số đầu vào nhưng giữ `#p0` | Policy chuyển sang giá trị sai | Chọn tên rõ nghĩa hoặc cập nhật test |
| Interface/JAR biên dịch thiếu flag | Reflection trên interface không có tên | Build lại module hoặc annotation alias |
| Bật flag nhưng không clean build | Class cũ còn thiếu metadata | Clean/test và xác minh bytecode |
| `@PreAuthorize` không chạy vì method self-invocation | Guard bị bỏ qua dù tên đúng | Gọi qua Spring bean proxy |
| Chỉ test thành công, không test từ chối | Không thấy lỗ hổng quyền | Matrix ALLOW/DENY và kiểm side effect |
| SpEL so với tham số client mà không dùng authenticated identity | Có thể tin dữ liệu giả mạo | So với `authentication` server-side và domain policy |
| Kết luận mọi 403 là lỗi tên tham số | Có thể do thiếu quyền/CSRF/HTTP rule | Xác định filter/advisor và test đối chứng |

### Quy trình debug từng bước

1. **Xác định method bảo vệ** và expression chính xác, không chỉ URL hay controller.
2. **Bật `@EnableMethodSecurity`** và bảo đảm method đang chạy qua Spring AOP proxy; kiểm self-invocation.
3. **Xác nhận tên tham số**: dùng reflection `getParameters()[i].isNamePresent()` cho tên Java hoặc xem `@P`/`@Param` trên method được intercept.
4. **Xác nhận class/JAR đang chạy** được biên dịch từ đúng source và đúng module/compiler flags.
5. **Đánh giá SpEL đầu vào có thật**: owner, tenantId, documentId; không log plaintext token/secret.
6. **So sánh principal và authorities server-side**; nếu điều kiện không thỏa dù metadata đúng, đó có thể là DENY hợp lệ.
7. **Kiểm cả HTTP + method layers**. Nếu request POST thiếu CSRF, 403 có thể xuất hiện trước method security; bài này dùng GET để cô lập.
8. **Chạy test âm tính** cho tài khoản cố truy cập dữ liệu user khác và tác vụ không được phép.
9. **Không đổi policy thành `permitAll`** chỉ để làm test xanh. Việc thiếu metadata là lỗi build/config hoặc annotation contract, không phải lý do cấp thêm quyền.

### Tách loại lỗi trong môi trường thực

- Request chưa xác thực với HTTP Basic: thường **401**.
- User đã đăng nhập nhưng không được `@PreAuthorize` cho phép: thường **403**.
- Biểu thức SpEL thiếu biến hoặc lỗi truy cập property: **có thể có exception đánh giá**, mã HTTP cụ thể phụ thuộc exception translation/config.
- POST/PUT/PATCH/DELETE thiếu CSRF token: có thể **403 trước khi tới method security**.
- Proxy/interceptor không chạy: có thể **200 ngoài ý muốn**, nguy hiểm hơn 403.
- Domain policy deny: có thể **403/404 theo chính sách**, cần audit đúng điểm chặn.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `@PreAuthorize("#owner == authentication.name")` có thể hoạt động ở máy developer nhưng lỗi trên CI?  
**Đáp án:** Module có thể được biên dịch bằng compiler flags khác, class CI thiếu metadata `MethodParameters`, nên Spring không lấy được tên `owner` như dự tính.

**Câu 2.** `-parameters` là option của lệnh `javac` hay `java`?  
**Đáp án:** `javac`; nó thay đổi nội dung file `.class` tại thời điểm biên dịch.

**Câu 3.** `javac -g` có thay thế `-parameters` ở Spring Framework 6.1+ không?  
**Đáp án:** Không nên dựa vào. `LocalVariableTableParameterNameDiscoverer` đã bị loại bỏ.

**Câu 4.** Cần import `@P` từ đâu?  
**Đáp án:** `org.springframework.security.access.method.P`.

**Câu 5.** Method `read(@P("subject") String account)`, expression phải dùng tên nào?  
**Đáp án:** `#subject`, không phải tự động `#account`.

**Câu 6.** Khi dùng Spring Boot 3 Maven parent, có luôn cần thêm compiler plugin thủ công không?  
**Đáp án:** Không nhất thiết; Boot parent thường đã bật `-parameters`. Nhưng phải kiểm effective build và bytecode ở module service.

**Câu 7.** `#p0` có ý nghĩa gì?  
**Đáp án:** Tham số vị trí 0, không phụ thuộc tên, nhưng rất dễ sai nếu thay thứ tự tham số.

**Câu 8.** `@PathVariable("account")` trên controller có tự làm `#account` hoạt động trên service không?  
**Đáp án:** Không. Metadata service được xử lý độc lập.

**Câu 9.** Dùng `@P` trên interface method có ích không?  
**Đáp án:** Có thể đặt contract rõ ràng ngay ở interface; vẫn phải kiểm thử trên kiểu proxy và version của ứng dụng, vì method/annotation resolution phụ thuộc cấu hình.

**Câu 10.** Khi class được compile với `-parameters`, `Parameter#isNamePresent()` của `String account` trả gì?  
**Đáp án:** `true`; `getName()` là `account`.

**Câu 11.** Nếu `@PreAuthorize` không chạy do `this.readNamed(...)`, bật `-parameters` có đủ sửa không?  
**Đáp án:** Không. Đây là vấn đề self-invocation/proxy, không phải metadata tên tham số.

**Câu 12.** Làm sao phân biệt DENY hợp lệ với lỗi tên tham số?  
**Đáp án:** Kiểm metadata bằng reflection/annotation, xem method proxy, rồi test đối chứng user đúng owner và user sai owner với cùng code.

**Câu 13.** Có nên thêm Spring Data chỉ để sử dụng `@Param` không?  
**Đáp án:** Thường không; `@P` của Spring Security đủ để đặt alias tường minh.

**Câu 14.** Khi expression có hai tham số, một có `@P`, một chỉ dựa vào Java source name, rủi ro gì?  
**Đáp án:** Các discoverers có thứ tự ưu tiên và không nên giả định sẽ tự ghép tên từ mọi nguồn; nên gắn tên tường minh cho những tham số được dùng hoặc bảo đảm build metadata/test.

**Câu 15.** Lưu tên tham số đúng có tự bảo vệ được IDOR/BOLA không?  
**Đáp án:** Không. SpEL đọc đúng giá trị chỉ là bước đầu; vẫn phải kiểm owner, tenant, role, permission và chính sách tài nguyên từ server.

**Tóm tắt thực hành:** Với `@PreAuthorize` tham chiếu `#ownerId` hoặc `#tenantId`, hãy bảo đảm **metadata của đúng method** tồn tại: biên dịch module bằng **`-parameters`**, hoặc dùng **`@P`** tường minh; `#p0` phù hợp khi cần tham chiếu vị trí có chủ đích. Trên Spring Framework 6.1+, **không dựa vào debug symbols như giải pháp thay thế**. Xác nhận bằng reflection và test **cho phép đúng/từ chối đúng** trước khi triển khai.

## Tài liệu chính thức

- Spring Security 6.5 — Method Security, mục **Using Method Parameters**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorization Migrations, mục **Compile With -parameters** và Spring Framework 6.1: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html
- Spring Framework 6.2 — `MethodBasedEvaluationContext` (các alias `p0`, `a0`, tên tham số): https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/context/expression/MethodBasedEvaluationContext.html
- Spring Security 6.5 — `DefaultSecurityParameterNameDiscoverer` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/parameters/DefaultSecurityParameterNameDiscoverer.html
- Spring Security 6.5 — `P` annotation API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/method/P.html
- Spring Boot — Maven Plugin, `spring-boot-starter-parent` mặc định hỗ trợ `-parameters`: https://docs.spring.io/spring-boot/maven-plugin/using.html
