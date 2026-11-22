# Kiểm thử phương thức: gọi Spring bean qua proxy để xác nhận annotation bảo mật có hiệu lực

## 1. Mục tiêu và phạm vi

Khi gắn `@PreAuthorize` lên một phương thức, việc nhìn thấy annotation trong mã nguồn **chưa chứng minh** quyền truy cập đang được kiểm tra. Bài kiểm thử phải gọi phương thức qua **bean mà Spring quản lý**, để lời gọi đi qua proxy và bộ chặn của Spring Security.

Sau bài này, bạn có thể:

- Bật method security bằng `@EnableMethodSecurity`.
- Lấy bean thật của `ApplicationContext` bằng `@Autowired` và xác nhận nó được proxy.
- Dùng `@WithMockUser`/`@WithAnonymousUser` để thử cả trường hợp **được phép** và **bị từ chối**.
- Phân biệt kiểm thử security thực sự với lời gọi `new Service()`, Mockito thuần hoặc self-invocation làm bỏ qua proxy.
- Chẩn đoán một bài test vẫn chạy xanh dù annotation không được thực thi.

Phạm vi là **Spring Security servlet/method security** trên Java 17+, dùng ví dụ Spring Boot 3.5.7 và JUnit Jupiter. Không cần khởi tạo HTTP server hoặc gọi endpoint: chính ranh giới phương thức của Spring bean là đối tượng cần kiểm tra.

## 2. Cơ chế cần hiểu trước khi viết test

`@EnableMethodSecurity` đăng ký các thành phần kiểm tra quyền cho phương thức, trong đó `@PreAuthorize` được hỗ trợ mặc định. Chỉ thêm `spring-boot-starter-security` **không tự bật** method security.

Đối với cơ chế Spring AOP proxy mặc định, luồng gọi đúng là:

```text
JUnit test
    |
    | @Autowired ReportService
    v
Spring-managed proxy
    |
    | @PreAuthorize -> đọc Authentication trong SecurityContext
    |     + đủ quyền: đi tiếp
    |     + thiếu quyền: ném AccessDeniedException
    v
ReportService thực thi phương thức thật
```

Vì kiểm tra nằm tại proxy, hai lời gọi dưới đây không tương đương:

- `reportService.readReport()` với `reportService` **được inject từ Spring**: cơ chế bảo mật có cơ hội chặn.
- `new ReportService().readReport()`: chỉ gọi một đối tượng Java thông thường, không có advice của Spring AOP.

Khi test bằng `@WithMockUser`, Spring Security Test tạo `Authentication` trong `SecurityContextHolder` của luồng test. Username và quyền được mô phỏng; không cần tài khoản thật trong cơ sở dữ liệu. Điều này phù hợp để kiểm tra **quy tắc phân quyền ở phương thức**, nhưng không chứng minh toàn bộ quá trình đăng nhập, JWT hay HTTP filter hoạt động đúng.

**Hai nhóm assertion đều cần thiết:** trường hợp đủ quyền phải trả kết quả đúng; trường hợp thiếu quyền phải bị từ chối. Chỉ kiểm tra kết quả thành công có thể khiến test xanh ngay cả khi `@PreAuthorize` bị vô hiệu hóa.

## 3. Ví dụ hoàn chỉnh có thể chạy

Tạo một Maven project với cấu trúc:

```text
method-security-proxy-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/methodsecurity/
    │   ├── DemoApplication.java
    │   └── ReportService.java
    └── test/java/com/example/methodsecurity/
        └── ReportServiceTest.java
```

### 3.1. Khai báo dependency

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>method-security-proxy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
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

Ý nghĩa: starter security cung cấp cơ chế phân quyền; starter test cung cấp JUnit 5 và AssertJ; `spring-security-test` cung cấp `@WithMockUser`, `@WithAnonymousUser` và listener thiết lập security context cho test. Không cần `spring-boot-starter-web` vì ví dụ kiểm thử trực tiếp service.

### 3.2. Bật method security trong Spring context

Tệp `src/main/java/com/example/methodsecurity/DemoApplication.java`:

```java
package com.example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` tìm `@Service` trong cùng package và các package con. `@EnableMethodSecurity` kích hoạt interceptor cho `@PreAuthorize`. Trong dự án thực tế, annotation này cũng có thể đặt trên một class `@Configuration` thích hợp.

### 3.3. Tạo bean với quy tắc phân quyền rõ ràng

Tệp `src/main/java/com/example/methodsecurity/ReportService.java`:

```java
package com.example.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String readReport() {
        return "NOI_DUNG_BAO_CAO";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String approveReport() {
        return "APPROVED";
    }
}
```

Giải thích hai biểu thức:

- `hasAuthority('report:read')` yêu cầu authority có tên **chính xác** `report:read`.
- `hasRole('ADMIN')` theo quy ước mặc định kiểm tra authority `ROLE_ADMIN`. Với `@WithMockUser(roles = "ADMIN")`, test sẽ được cấp authority tương ứng; không cần viết `ROLE_` trong tham số `roles`.

Hai phương thức đều `public`, không `final`, để phù hợp với cách proxy của Spring AOP. Giá trị trả về là chuỗi cố định nhằm giúp ta tập trung vào việc phương thức được phép thực thi hay không.

### 3.4. Gọi bean đã được Spring tạo trong JUnit test

Tệp `src/test/java/com/example/methodsecurity/ReportServiceTest.java`:

```java
package com.example.methodsecurity;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(classes = DemoApplication.class)
class ReportServiceTest {
    @Autowired
    private ReportService reportService;

    @Test
    void injectedServiceIsAnAopProxy() {
        assertThat(AopUtils.isAopProxy(reportService)).isTrue();
    }

    @Test
    @WithMockUser(authorities = "report:read")
    void readerCanReadReport() {
        assertThat(reportService.readReport())
                .isEqualTo("NOI_DUNG_BAO_CAO");
    }

    @Test
    @WithMockUser(authorities = "report:write")
    void userWithoutReadAuthorityIsDenied() {
        assertThatThrownBy(() -> reportService.readReport())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithAnonymousUser
    void anonymousUserIsDenied() {
        assertThatThrownBy(() -> reportService.readReport())
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanApproveReport() {
        assertThat(reportService.approveReport())
                .isEqualTo("APPROVED");
    }

    @Test
    @WithMockUser(roles = "USER")
    void nonAdminCannotApproveReport() {
        assertThatThrownBy(() -> reportService.approveReport())
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

**Điểm quyết định:** trường `reportService` nhận từ `@Autowired`, không được khởi tạo bằng `new` và cũng không phải một mock thay thế. Vì test chạy với Spring context thật nên lời gọi đi qua proxy của bean.

Ý nghĩa từng nhóm test:

1. `injectedServiceIsAnAopProxy` kiểm chứng đối tượng được inject là proxy AOP. Đây là phép kiểm tra điều kiện cần trong ví dụ; **chưa đủ** để khẳng định một annotation cụ thể chặn được ai.
2. `readerCanReadReport` chứng minh authority hợp lệ không bị chặn oan.
3. `userWithoutReadAuthorityIsDenied` chứng minh authority khác không đủ để vượt qua `@PreAuthorize`.
4. `anonymousUserIsDenied` chứng minh người dùng ẩn danh không được đọc.
5. Hai test `approveReport` phân biệt đúng quy tắc role `ADMIN` và `USER`.

`AccessDeniedException` là lớp cha phù hợp để assertion: các phiên bản Spring Security có thể sử dụng kiểu con biểu diễn quyết định bị từ chối. Thử nghiệm trên dùng `@WithAnonymousUser` để tạo trạng thái ẩn danh rõ ràng; nếu để trống hoàn toàn `Authentication`, đường đi lỗi có thể khác, ví dụ `AuthenticationCredentialsNotFoundException`.

### 3.5. Chạy và đọc kết quả

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
java -version
mvn test
```

Kỳ vọng: Maven Surefire chạy **6 test**, không có failure hoặc error. Dòng tổng kết thường có dạng:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
```

Đây là kết quả kỳ vọng của ví dụ, không phải log được sao chép từ một lần chạy thực tế. Không cần chạy ứng dụng web, gửi token, hoặc đăng nhập để thực hiện sáu test này.

Để tự chứng minh test đủ nhạy, hãy thử **tạm thời** bỏ `@EnableMethodSecurity` rồi chạy lại `mvn test`: các assertion mong chờ từ chối sẽ thất bại vì không còn interceptor phân quyền. Sau đó khôi phục annotation. Tương tự, nếu tạm xóa `@PreAuthorize` của `readReport`, test thiếu authority phải thất bại. Đây là cách tránh test “xanh giả”.

## 4. Vì sao gọi trực tiếp thường tạo ra kết quả sai?

### 4.1. `new` bỏ qua Spring proxy

Đoạn sau **chỉ minh họa lỗi thiết kế test**, không thay cho test ở mục 3:

```java
// Minh họa: đoạn mã này nằm bên trong một phương thức Java.
ReportService manuallyCreated = new ReportService();
String result = manuallyCreated.readReport();
// Lời gọi trên không đi qua Spring Security AOP proxy.
```

Bản thân một annotation không tự chạy khi JVM gọi phương thức. `new` tạo instance thông thường; Spring không có cơ hội áp interceptor, vì thế một bài kiểm thử chỉ xác nhận `result` sẽ không phát hiện việc thiếu bảo mật.

### 4.2. Self-invocation cũng bỏ qua advice

Giả sử thêm vào `ReportService` một phương thức không được bảo vệ:

```java
// Chỉ là đoạn minh họa trong ReportService, KHÔNG thêm vào ứng dụng thật.
public String insecureInternalCall() {
    return this.readReport();
}
```

Nếu bên ngoài gọi `reportService.insecureInternalCall()`, lời gọi ban đầu đi qua proxy. Nhưng `this.readReport()` chạy **bên trong target object**, không quay lại proxy để áp `@PreAuthorize` của `readReport`. Việc này có thể trở thành lỗ hổng phân quyền nếu phương thức bên ngoài được gọi bởi người không đủ quyền.

Cách thiết kế dễ kiểm soát nhất là chuyển thao tác bảo vệ sang **một bean riêng** rồi để bean gọi nó thông qua dependency do Spring inject. Ví dụ, `ReportFacade` inject `ReportService` và gọi `reportService.readReport()`; tại ranh giới giữa hai bean, lời gọi đi qua proxy của `ReportService`. Đừng cố chữa self-invocation chỉ bằng cách thêm `@WithMockUser` vào test.

### 4.3. Mock và unit test thuần có mục đích khác

Nếu dùng `@Mock`/`@InjectMocks` của Mockito để thử logic nội bộ, bạn thường chỉ chạy code Java hoặc hành vi stub, không dựng cấu hình bảo mật của Spring. Những test đó có giá trị để kiểm tra logic nghiệp vụ, nhưng **không thể thay** test method security qua Spring context.

Nếu mock **chính service cần bảo vệ** trong context, lời gọi có thể không đi qua phương thức/annotation thật. Muốn kiểm tra authorization annotation, hãy để bean chứa annotation là bean thật; mock repository hoặc phụ thuộc bên dưới khi cần. Trong ví dụ này, không cần mock nào.

## 5. Những điều kiện và lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Người thiếu quyền vẫn nhận được dữ liệu | Quên `@EnableMethodSecurity` hoặc gọi đối tượng bằng `new` | Kiểm tra cấu hình, dùng `@Autowired`, assert denied và kiểm tra proxy |
| Test chỉ có case được phép luôn xanh | Không kiểm tra nhánh từ chối | Thêm `@WithMockUser` thiếu quyền + `assertThatThrownBy` |
| Có annotation nhưng self-invocation vẫn đi qua | `this.method()` bypass proxy | Chuyển lời gọi bảo vệ sang bean được inject khác |
| `hasRole('ADMIN')` không khớp | Nhầm role và authority, sai tiền tố `ROLE_` | Dùng `roles = "ADMIN"` cho `hasRole`; dùng `authorities` cho `hasAuthority` |
| Test bị lỗi security context hoặc annotation test không tác dụng | Thiếu `spring-security-test` hoặc test không có Spring Test integration | Thêm dependency test và dùng `@SpringBootTest`/`@ContextConfiguration` thích hợp |
| Bean không được inject hoặc không được proxy | Service không nằm trong component scan, dùng mock, annotation chưa được bật | Kiểm tra package, `@Service`, `@EnableMethodSecurity`, `AopUtils.isAopProxy` |
| Proxy kiểu JDK không cast được về class triển khai | Bean có interface, proxy có thể chỉ expose interface | Inject kiểu interface phù hợp; cân nhắc chế độ class proxy khi thực sự cần |
| `final`/`private` không bị chặn như mong đợi | Giới hạn của proxy dựa trên subclass và visibility | Đưa policy lên phương thức public có thể được proxy, tránh final/private tại điểm chặn |

Lưu ý thêm:

- Spring AOP thường dùng **JDK dynamic proxy** với các bean có interface và **class-based proxy** với bean không có interface; chi tiết còn tùy cấu hình. Đừng viết test phụ thuộc cứng vào tên lớp proxy (chẳng hạn tên chứa `$$SpringCGLIB$$`). `AopUtils.isAopProxy` ổn định hơn cho mục tiêu đang học.
- `@WithMockUser` đặt security context trên **luồng test**. Nó không tự xác thực một HTTP request chạy ở luồng khác (`@SpringBootTest(webEnvironment = RANDOM_PORT)`, ví dụ); khi test qua HTTP phải cung cấp credentials/token cho request đó.
- `@PreAuthorize` kiểm tra trước khi method body chạy. Nếu dùng `@PostAuthorize`, logic có thể chạy rồi mới từ chối trả kết quả; cần thiết kế test phụ thuộc vào điểm chặn tương ứng.
- Nếu cấu hình dự án cố tình dùng AspectJ weaving thay vì Spring AOP proxy, cơ chế áp advice và phép kiểm tra proxy có thể khác; bài này tập trung vào cấu hình proxy thông thường.

## 6. Quy trình kiểm thử áp dụng cho code thật

1. Xác định đúng bean/phương thức mang annotation cần kiểm tra, và biểu thức quyền mong muốn.
2. Khởi động Spring Test context có `@EnableMethodSecurity`; inject bean từ context.
3. Nếu dùng proxy mode, xác nhận đối tượng inject có proxy hoặc kiểm tra bằng đặc điểm tương đương; **không xem bước này thay thế assertion hành vi**.
4. Tạo ít nhất một test **được phép** và một test **bị từ chối** với principal/authorities rõ ràng, ví dụ `@WithMockUser`.
5. Chạy đối chứng khi vô hiệu hóa annotation hoặc cấu hình method security (chỉ trong môi trường test) để chắc chắn test thật sự phát hiện sự cố.

Một bài kiểm thử có giá trị phải thất bại khi bạn vô tình làm mất quy tắc phân quyền. Đó là tiêu chí thực tế để biết annotation đang **có hiệu lực ở đường gọi Spring bean**, thay vì chỉ tồn tại trong mã nguồn.

## 7. Bài tập tự kiểm tra

1. Đổi biểu thức của `readReport` thành `hasAnyAuthority('report:read', 'report:audit')`. Thêm một test với `@WithMockUser(authorities = "report:audit")` và một test thiếu cả hai authority; giải thích kết quả.
2. Tạo `ReportFacade` được Spring quản lý, inject `ReportService` và gọi `readReport()` từ facade. Viết test thiếu quyền gọi qua facade và xác nhận vẫn bị từ chối. So sánh với ví dụ `this.readReport()` để thấy ranh giới proxy.

## Tài liệu đối chiếu

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): bật `@EnableMethodSecurity`, biểu thức `@PreAuthorize` và luồng interceptor.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser` và security context trong test.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK/CGLIB proxy và hiện tượng self-invocation bypass.
