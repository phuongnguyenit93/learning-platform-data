# @PreAuthorize: kiểm tra quyền trước khi thực thi phương thức trong Spring Security

Một API có thể được bảo vệ ở tầng URL nhưng nghiệp vụ tương tự vẫn có thể được gọi từ nhiều nơi: REST Controller, tác vụ định kỳ, luồng xử lý sự kiện, hoặc một thành phần dịch vụ khác. Khi chỉ kiểm soát `GET /documents/**` hay `POST /documents/**`, chính sách dễ bị phân tán hoặc bỏ sót đường gọi không đi qua HTTP. **`@PreAuthorize`** của Spring Security gắn điều kiện cấp quyền với **lời gọi phương thức**, nhằm ngăn phần thân phương thức chạy khi người gọi chưa đủ quyền.

Ví dụ: `DocumentService.editDocument(100L)` chỉ được chạy khi người dùng có quyền `DOC_EDIT` **và** thực sự là chủ sở hữu tài liệu 100. Spring Security đánh giá điều kiện trước khi chuyển lời gọi vào phương thức đích. Nếu bị từ chối, thao tác ghi dữ liệu trong phần thân không được thực thi thông qua lời gọi đã được cơ chế bảo mật chặn.

Bài thuộc **Bảo vệ phương thức** của **Spring Security - fundamentals**. Ta sẽ tìm hiểu `@PreAuthorize` là gì, cách kích hoạt, cú pháp biểu thức, cơ chế proxy/interceptor, quyền theo tham số và bản ghi, kiểm thử hành vi thật và các đường gọi có thể làm mất tác dụng của annotation. Ví dụ chính dùng **Java 17+, Spring Boot 3.3.x và Spring Security 6.3.x**.

## 1. @PreAuthorize giải quyết vấn đề gì?

Hãy xét dịch vụ:

~~~java
public void deleteDocument(long id) {
    repository.deleteById(id);
}
~~~

Nếu lời gọi này chạy trước khi kiểm tra danh tính và quyền, thao tác xóa đã xảy ra. Ta có thể thêm logic `if` trực tiếp trong phương thức, nhưng khi nhiều thao tác sử dụng cùng một quy tắc, mã kiểm soát quyền có thể lặp lại và dễ bị bỏ sót.

Với method security:

~~~java
@PreAuthorize("hasAuthority('DOC_DELETE')")
public void deleteDocument(long id) {
    repository.deleteById(id);
}
~~~

Spring Security sẽ kiểm tra người đang gọi có `GrantedAuthority` bằng `DOC_DELETE` hay không **trước khi** cho phép phần thân phương thức chạy qua interceptor bảo mật. Cần lưu ý đoạn trên là **mã minh họa**, vì `repository` chưa được định nghĩa; ví dụ ứng dụng hoàn chỉnh xuất hiện ở phần sau.

Vì sao cần thêm tầng này khi đã có HTTP security?

| Kiểm soát quyền ở URL | Kiểm soát quyền bằng `@PreAuthorize` |
| --- | --- |
| Bảo vệ một request khớp method/path hoặc matcher khác | Bảo vệ lời gọi phương thức trên bean do Spring quản lý |
| Phù hợp để bảo vệ cửa vào HTTP | Phù hợp để bảo vệ ranh giới nghiệp vụ |
| Quy tắc thường đặt trong `SecurityFilterChain` | Quy tắc đặt ngay phương thức/lớp dịch vụ |
| Dễ nhìn các đường dẫn cho phép | Có thể dùng tham số như `#documentId`, `#owner` |
| Không tự bảo vệ lời gọi dịch vụ từ nơi không đi qua HTTP | Có thể bảo vệ lời gọi đi qua method-security proxy với `Authentication` thích hợp |

Hai tầng có thể **bổ sung lẫn nhau**. Không vì có `@PreAuthorize` mà bỏ xác thực HTTP, và không vì endpoint đã khai báo `hasRole` mà bỏ qua quyền thực hiện hành động trên dữ liệu cụ thể.

## 2. Điều kiện được kiểm tra vào thời điểm nào?

Mô hình cho ứng dụng Java/Spring MVC với method security dựa trên Spring AOP:

~~~text
Controller / bean A
      |
      | gọi documentService.editDocument(100)
      v
Spring-managed proxy của DocumentService
      |
      v
AuthorizationManagerBeforeMethodInterceptor
      |
      +--> Đọc Authentication hiện tại
      |
      +--> Đánh giá biểu thức @PreAuthorize
              |
              +--> true  -> gọi phương thức thật -> chạy nghiệp vụ
              |
              +--> false -> ném lỗi từ chối quyền
                             -> KHÔNG gọi phương thức thật
~~~

Spring Security 6.x sử dụng bộ chặn trước lời gọi (ví dụ `AuthorizationManagerBeforeMethodInterceptor` với bộ quản lý tương ứng cho `@PreAuthorize`). Biểu thức được tính trong ngữ cảnh chứa `Authentication`, tham số phương thức và các hàm kiểm tra quyền của Spring Security.

Các điểm quan trọng:

1. `@PreAuthorize` được đánh giá **mỗi khi một lời gọi phù hợp đi qua interceptor**. Nó không phải kiểm tra một lần lúc khởi động ứng dụng.
2. Nếu điều kiện là `true`, lời gọi được chuyển vào phần thân phương thức; phương thức vẫn có thể lỗi nghiệp vụ, lỗi dữ liệu hoặc bị kiểm tra bổ sung.
3. Nếu điều kiện là `false`, phần thân phương thức không chạy qua đường gọi được bảo vệ; Spring Security thường phát sinh `AccessDeniedException` hoặc một kiểu con tương ứng.
4. Nếu không có ngữ cảnh xác thực hợp lệ, kết quả có thể là lỗi chưa có thông tin xác thực hoặc lỗi từ chối, tùy đường thực thi và cơ chế xử lý. **Đừng gán cố định mọi trường hợp thành HTTP 403.**
5. Mọi phép tra cứu thực hiện **trong biểu thức hoặc bean chính sách** vẫn có thể đã chạy trước khi điều kiện trả về `false`. Khái niệm “chưa chạy phương thức đích” không có nghĩa “chưa xảy ra bất kỳ công việc nào”.

Lời gọi `new DocumentService()` thông thường không qua bean/proxy Spring, nên annotation không tự thi hành. Đây là điều quan trọng nhất để kiểm thử đúng `@PreAuthorize`.

## 3. Bắt buộc bật method security

Chỉ thêm dependency `spring-boot-starter-security` **chưa tự bật bảo vệ phương thức**. Trên Spring Security 6.x, hãy bật:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Sau khi có `@EnableMethodSecurity`, Spring Security tìm các phương thức/lớp có annotation phân quyền như `@PreAuthorize` và cấu hình cơ chế interceptor phù hợp. Ví dụ trên là một lớp cấu hình độc lập, có thể đặt trong package được Spring Boot quét.

Những lưu ý về phiên bản:

- Với Spring Security 6.x, ưu tiên `@EnableMethodSecurity`.
- Trong tài liệu/bài cũ có thể thấy `@EnableGlobalMethodSecurity(prePostEnabled = true)`; đây là cách cấu hình cũ, không nên áp dụng máy móc cho dự án 6.x.
- `@EnableMethodSecurity` mặc định hỗ trợ các annotation `@PreAuthorize`/`@PostAuthorize`; `@Secured` hoặc JSR-250 có lựa chọn bật riêng nếu cần. Bài này tập trung vào `@PreAuthorize`.
- Không cần thêm `@EnableMethodSecurity` trên mọi service; thông thường chỉ cần khai báo ở một lớp cấu hình được nạp vào `ApplicationContext`.

**Cách tự xác minh đã bật:** một phép thử gọi phương thức cần quyền qua bean Spring bằng người dùng không có quyền phải nhận lỗi; nếu vẫn trả kết quả, hãy kiểm tra cấu hình, vị trí annotation và việc phương thức có đi qua proxy không.

## 4. Cú pháp biểu thức @PreAuthorize

Annotation nhận một chuỗi **Spring Expression Language (SpEL)**, kết hợp các biểu thức bảo mật do Spring Security cung cấp:

~~~java
@PreAuthorize("isAuthenticated()")
public String getProfile() { /* ... */ }

@PreAuthorize("hasRole('ADMIN')")
public void rebuildIndex() { /* ... */ }

@PreAuthorize("hasAuthority('DOC_READ')")
public String readDocument(long id) { /* ... */ }

@PreAuthorize("hasAnyAuthority('DOC_READ', 'DOC_ADMIN')")
public String exportDocuments() { /* ... */ }
~~~

Các phương thức trên là đoạn minh họa cho **biểu thức**, không phải một tệp Java có thể biên dịch độc lập vì phần thân đang được rút gọn.

| Biểu thức | Ý nghĩa |
| --- | --- |
| `isAuthenticated()` | Người dùng được xác thực, không phải anonymous; trong cơ chế mặc định thường gồm cả remember-me |
| `isFullyAuthenticated()` | Xác thực đầy đủ, loại anonymous và remember-me theo bộ phân loại tin cậy |
| `isAnonymous()` | Danh tính được nhận diện là anonymous |
| `hasRole('ADMIN')` | Có authority `ROLE_ADMIN` theo tiền tố role mặc định |
| `hasAuthority('DOC_READ')` | Có authority đúng bằng `DOC_READ` |
| `hasAnyRole('ADMIN', 'EDITOR')` | Có ít nhất một trong các role tương ứng |
| `hasAnyAuthority('DOC_READ', 'DOC_ADMIN')` | Có ít nhất một authority được liệt kê |
| `authentication.name` | Tên của `Authentication` hiện tại |
| `principal` | Đối tượng principal trong ngữ cảnh xác thực |
| `#id` | Tham số phương thức có tên `id` (khi tên tham số được cung cấp/khám phá đúng) |
| `@documentPolicy.isOwner(authentication, #id)` | Gọi bean Spring tên `documentPolicy` để kiểm tra quyền theo dữ liệu |

Phân biệt quan trọng:

~~~text
hasRole('ADMIN')             thường xét ROLE_ADMIN
hasAuthority('ROLE_ADMIN')   xét đúng ROLE_ADMIN
hasAuthority('ADMIN')        xét đúng ADMIN
~~~

Nếu một người có authority `DOC_EDIT` nhưng không có `ROLE_DOC_EDIT`, `hasAuthority('DOC_EDIT')` có thể đạt trong khi `hasRole('DOC_EDIT')` không đạt. Không trộn role và authority chỉ vì tên hiển thị gần giống nhau.

### Kết hợp điều kiện

Dùng `and`, `or` và `!` trong SpEL:

~~~java
@PreAuthorize("hasAuthority('DOC_EDIT') and #owner == authentication.name")
public void editOwnedDocument(String owner) { /* ... */ }

@PreAuthorize("hasRole('ADMIN') or hasAuthority('REPORT_VIEW')")
public String viewReport() { /* ... */ }
~~~

Điều kiện thứ nhất yêu cầu **đồng thời** có quyền chỉnh sửa và `owner` bằng tên người dùng hiện tại. Nhưng nếu `owner` được truyền trực tiếp từ request do khách hàng kiểm soát, kẻ tấn công có thể tự điền tên mình. **Không dùng phép so sánh với giá trị do client khai báo làm bằng chứng chủ sở hữu tài nguyên.** Hãy tải chủ sở hữu từ nguồn dữ liệu tin cậy theo ID như ở ví dụ phần 6.

Dùng dấu nháy đơn cho chuỗi bên trong SpEL giúp mã Java dễ đọc. Không dùng biểu thức kiểu `hasRole(ADMIN)` với identifier chưa định nghĩa; chuẩn nhất là `hasRole('ADMIN')`.

## 5. Phạm vi áp dụng: bean, phương thức và vị trí annotation

Thực tế, `@PreAuthorize` cần được đặt trên phương thức hoặc lớp do Spring quản lý:

~~~java
@Service
public class BillingService {

    @PreAuthorize("hasAuthority('INVOICE_READ')")
    public String readInvoice(long id) {
        return "invoice:" + id;
    }
}
~~~

Đây là một bean `@Service`; khi bean khác inject `BillingService` rồi gọi `readInvoice` qua proxy, điều kiện được kiểm tra. Nếu một class không được Spring khởi tạo (tạo bằng `new`), không có điều gì bảo đảm interceptor Spring AOP được gọi.

Có thể đặt annotation ở mức class để áp dụng mặc định cho các phương thức thích hợp:

~~~java
@Service
@PreAuthorize("hasRole('AUDITOR')")
public class AuditService {
    public String inspect(long id) {
        return "audit:" + id;
    }
}
~~~

Khi trộn quy tắc mức lớp, interface và phương thức, cần xét cách kế thừa/ưu tiên annotation của phiên bản Spring Security và tránh các quy tắc gây nhập nhằng. Với quyền khác nhau cho từng hành động, **đặt annotation rõ tại từng phương thức** thường dễ kiểm tra hơn.

Không trông chờ proxy Spring AOP bảo vệ các lời gọi tới phương thức `private`, `static`, `final` hoặc các lời gọi đi thẳng trên `this`. Với class hoặc method `final`, còn tùy kiểu proxy mà ứng dụng có thể không tạo được proxy hoặc không chặn được lời gọi; hãy thiết kế ranh giới bảo mật ở phương thức có thể được proxy và kiểm thử thực tế.

## 6. Ví dụ hoàn chỉnh: bảo vệ quyền chỉnh sửa tài liệu theo chủ sở hữu

Dự án học tập sẽ kiểm tra ba quy tắc:

1. Người có `DOC_READ` được gọi `readDocument(id)`.
2. Người có `DOC_EDIT` **và** là chủ sở hữu thực sự của tài liệu mới được gọi `editDocument(id)`.
3. Người có role `ADMIN` được gọi `audit()`.

Ví dụ dùng kho chủ sở hữu trong bộ nhớ để dễ chạy, minh họa rõ **quyền từ ngữ cảnh xác thực + quyền theo bản ghi từ nguồn dữ liệu đáng tin cậy**. Nó không triển khai cơ sở dữ liệu, controller hoặc xác thực đăng nhập thực tế.

### 6.1. Cấu trúc mã nguồn

~~~text
method-security-demo/
├── build.gradle
├── settings.gradle
├── src/main/java/example/methodsecurity/
│   ├── MethodSecurityApplication.java
│   ├── DocumentPolicy.java
│   └── DocumentService.java
└── src/test/java/example/methodsecurity/
    └── DocumentServiceSecurityTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'method-security-demo'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ví dụ sử dụng một bản Spring Boot 3.3.x cụ thể để minh họa API. Dự án có thể dùng wrapper Gradle tương thích và Java 17+. Đối với dự án Spring Boot hiện có, chỉ ghép các dependency/cấu hình cần thiết; không tạo thêm một bộ plugin quản lý version khi dự án đã có sẵn.

### 6.4. MethodSecurityApplication.java

~~~java
package example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class MethodSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodSecurityApplication.class, args);
    }
}
~~~

Lớp chính vừa khởi động Spring Boot vừa bật method security. Vì đây là ứng dụng ví dụ không có web starter, phép thử tập trung vào **lời gọi dịch vụ**, không khởi động HTTP server.

### 6.5. DocumentPolicy.java: quyền theo nguồn dữ liệu

~~~java
package example.methodsecurity;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    // Dữ liệu mô phỏng lấy từ kho tài liệu phía máy chủ.
    private final Map<Long, String> ownerById =
            Map.of(100L, "lan", 200L, "minh");

    public boolean isOwner(Authentication auth, long id) {
        if (auth == null || !auth.isAuthenticated()) {
            return false;
        }

        String recordedOwner = ownerById.get(id);
        return recordedOwner != null
                && recordedOwner.equals(auth.getName());
    }
}
~~~

Trong ứng dụng thật, `ownerById` sẽ là kết quả tra cứu kho dữ liệu được bảo vệ và nhất quán, không dựa trên tham số `owner` do client tự khai báo. Biểu thức bảo mật ở `DocumentService` còn kiểm tra `DOC_EDIT`, nên danh tính anonymous không thể đi qua chỉ nhờ trùng tên. Nếu tái sử dụng `DocumentPolicy` làm cơ chế phân quyền độc lập ở nơi khác, cần thêm kiểm tra mức tin cậy xác thực (chẳng hạn bằng `AuthenticationTrustResolver`) và chính sách tài nguyên phù hợp.

Một ID không tồn tại trả về `false`. Đây là lựa chọn an toàn cho ví dụ; hệ thống thật còn cần xác định chính sách trả 404/403 và tránh tiết lộ sự tồn tại của tài nguyên.

### 6.6. DocumentService.java: bảo vệ phần thân phương thức

~~~java
package example.methodsecurity;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final AtomicInteger editCounter = new AtomicInteger();

    @PreAuthorize("hasAuthority('DOC_READ')")
    public String readDocument(long id) {
        return "document:" + id;
    }

    @PreAuthorize(
        "hasAuthority('DOC_EDIT') and @documentPolicy.isOwner(authentication, #id)"
    )
    public String editDocument(@P("id") long id) {
        editCounter.incrementAndGet();
        return "edited:" + id;
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String audit() {
        return "audit:allowed";
    }

    public int editCount() {
        return editCounter.get();
    }

    public void resetEditCount() {
        editCounter.set(0);
    }
}
~~~

Giải thích các điểm cần chú ý:

- `@Service` khiến Spring khởi tạo đối tượng và có thể tạo proxy chứa interceptor.
- `@PreAuthorize("hasAuthority('DOC_READ')")` bảo vệ thao tác đọc.
- `editDocument` chỉ chạy khi vừa có `DOC_EDIT`, vừa có kết quả `true` từ bean `documentPolicy`.
- `@documentPolicy` trong SpEL tham chiếu bean Spring tên `documentPolicy`, không phải cú pháp Java gọi phương thức tĩnh.
- `authentication` trong biểu thức là đối tượng `Authentication` hiện tại. `#id` là tham số `id` của phương thức, được gắn tên rõ ràng bằng `@P("id")`.
- `@P` sử dụng package `org.springframework.security.core.parameters.P`. Đây là cách tránh lệ thuộc cấu hình biên dịch giữ tên tham số và tránh dùng import `org.springframework.security.access.method.P` cũ đã được đánh dấu deprecated.
- `AtomicInteger` chỉ để phép thử chứng minh **phần thân không chạy** khi thiếu quyền. Trong ứng dụng sản xuất, không nên dùng bộ đếm trong bộ nhớ như bằng chứng an ninh hoặc trạng thái nghiệp vụ.
- `editCount` và `resetEditCount` là các điểm quan sát **chỉ phục vụ bài kiểm thử**; khi xây dịch vụ thật không nên phơi bày những phương thức này.

Nếu `@PreAuthorize` từ chối, bộ đếm **không tăng** vì dòng `editCounter.incrementAndGet()` nằm trong phần thân phương thức đích.

### 6.7. DocumentServiceSecurityTest.java: kiểm thử thực sự qua proxy

~~~java
package example.methodsecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DocumentServiceSecurityTest {

    @Autowired
    private DocumentService documents;

    @BeforeEach
    void reset() {
        documents.resetEditCount();
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_READ")
    void readerCanRead() {
        assertEquals("document:100", documents.readDocument(100L));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_EDIT")
    void editorCannotReadWithoutReadAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readDocument(100L));
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_EDIT")
    void ownerCanEditWithCorrectAuthority() {
        assertEquals("edited:100", documents.editDocument(100L));
        assertEquals(1, documents.editCount());
    }

    @Test
    @WithMockUser(username = "minh", authorities = "DOC_EDIT")
    void nonOwnerCannotEditEvenWithEditAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> documents.editDocument(100L));
        assertEquals(0, documents.editCount());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_READ")
    void ownerCannotEditWithoutEditAuthority() {
        assertThrows(AccessDeniedException.class,
                () -> documents.editDocument(100L));
        assertEquals(0, documents.editCount());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "DOC_EDIT")
    void unknownDocumentIsNotEditable() {
        assertThrows(AccessDeniedException.class,
                () -> documents.editDocument(999L));
        assertEquals(0, documents.editCount());
    }

    @Test
    @WithAnonymousUser
    void guestCannotReadDocument() {
        assertThrows(AccessDeniedException.class,
                () -> documents.readDocument(100L));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminRoleCanAudit() {
        assertEquals("audit:allowed", documents.audit());
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void normalRoleCannotAudit() {
        assertThrows(AccessDeniedException.class, documents::audit);
    }
}
~~~

Trong phép thử, `@Autowired DocumentService` là bean do Spring cung cấp, nên lời gọi `documents.editDocument(...)` đi qua cơ chế kiểm tra quyền. `@WithMockUser` dựng một danh tính giả trong ngữ cảnh kiểm thử; `@WithAnonymousUser` mô phỏng khách ẩn danh. Không cần tạo người dùng trong cơ sở dữ liệu chỉ để thử điều kiện quyền ở tầng method security.

Chạy từ thư mục có Gradle wrapper tương thích:

~~~bash
./gradlew test --tests '*DocumentServiceSecurityTest'
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "*DocumentServiceSecurityTest"
~~~

**Kết quả kỳ vọng từ đoạn mã:** cả **9 phép thử** đạt. Trong hai phép thử thiếu quyền và một phép thử sai chủ sở hữu, `editCount()==0` chứng minh phần thân `editDocument` chưa chạy. Đây là **kết quả mong đợi dựa trên hợp đồng Spring Security 6.3.x**, không phải một stdout/test report đã được chạy tại đây. Muốn kiểm tra trên dự án thật, cần có dependencies và wrapper phù hợp rồi thực thi lệnh.

Nếu kiểm thử thất bại, cần xác định lỗi từ proxy, annotation, biểu thức, thông tin xác thực thử nghiệm hoặc thiết lập `ApplicationContext`; không chỉ nhìn vào HTTP status vì bài kiểm thử này gọi trực tiếp service bean.

## 7. Giải thích chính xác chuỗi kiểm tra quyền theo tham số

Biểu thức quan trọng:

~~~java
@PreAuthorize(
    "hasAuthority('DOC_EDIT') and @documentPolicy.isOwner(authentication, #id)"
)
public String editDocument(@P("id") long id) {
    // ...
}
~~~

Hãy giả sử yêu cầu sửa tài liệu 100:

| Người gọi | Authority | Chủ sở hữu được lưu | ID yêu cầu | Kết quả |
| --- | --- | --- | --- | --- |
| `lan` | `DOC_EDIT` | `lan` | 100 | Cho gọi phương thức |
| `minh` | `DOC_EDIT` | `lan` | 100 | Từ chối, sai chủ sở hữu |
| `lan` | `DOC_READ` | `lan` | 100 | Từ chối, thiếu `DOC_EDIT` |
| `lan` | `DOC_EDIT` | Không có tài liệu 999 | 999 | Từ chối, chính sách trả false |
| Anonymous | Không có `DOC_EDIT` | `lan` | 100 | Từ chối |

Phép `and` yêu cầu cả hai vế đúng. Quyền chỉ cho phép **loại hành động** (sửa tài liệu), còn bộ phận `DocumentPolicy` kiểm tra **tài nguyên cụ thể**. Nếu chỉ dùng `hasAuthority('DOC_EDIT')`, một người biên tập có thể sửa tài liệu của người khác; nếu chỉ dùng `#owner == authentication.name` với `owner` do client gửi, kẻ tấn công có thể tự khai tên mình là chủ.

Một chính sách có thể cần nhiều điều kiện hơn, chẳng hạn tài liệu chưa khóa, người dùng thuộc cùng tổ chức, tài khoản còn hiệu lực và phương thức xác thực đủ mạnh. Với điều kiện nhiều bước hoặc đòi hỏi database, hãy tách thành bean chính sách có tên rõ ràng để dễ kiểm thử và tránh biểu thức SpEL quá dài.

### Khám phá tên tham số trong SpEL

Tên `#id` chỉ có giá trị nếu hệ thống biết tham số tương ứng. Spring Security hỗ trợ nhiều nguồn:

- `@P("id")` của Spring Security trên tham số.
- Thông tin tên tham số biên dịch với cờ Java `-parameters`.
- Một số metadata/debug information theo kiểu class; không nên dựa vào cách này khi giao diện hoặc môi trường build thay đổi.

Có thể sử dụng tham số theo chỉ số như `#p0` hoặc `#a0` trong các ngữ cảnh được hỗ trợ, nhưng tên tường minh dễ đọc và dễ bảo trì hơn. Ví dụ chính sử dụng `@P("id")`, giúp biểu thức `#id` ít phụ thuộc thiết lập compiler.

Nếu biểu thức gọi `#id` nhưng cơ chế nhận diện tham số không thấy tên, phần so sánh/quyền có thể cho kết quả sai hoặc việc đánh giá SpEL lỗi. Phải kiểm thử nhánh tham số thực tế, không kết luận chỉ vì Spring Boot khởi động thành công.

## 8. Kiểm tra biểu thức theo danh tính và vai trò

Một số mẫu thường dùng:

~~~java
// Người đăng nhập hợp lệ.
@PreAuthorize("isAuthenticated()")
public String accountOverview() { /* ... */ }

// Chỉ quản trị viên với quy ước ROLE_ADMIN.
@PreAuthorize("hasRole('ADMIN')")
public void reconfigureSystem() { /* ... */ }

// Có một trong hai quyền đọc hoặc quản lý.
@PreAuthorize("hasAnyAuthority('DOC_READ', 'DOC_ADMIN')")
public String viewLibrary() { /* ... */ }

// Đã xác thực và có quyền chỉnh sửa.
@PreAuthorize("isAuthenticated() and hasAuthority('DOC_EDIT')")
public void createDraft() { /* ... */ }
~~~

Đây là các **chữ ký minh họa**; thay `/* ... */` bằng phần thân thực tế và đặt trong bean Spring khi sử dụng. `hasRole('ADMIN')` với cấu hình tiền tố mặc định kiểm tra `ROLE_ADMIN`; `hasAuthority('DOC_ADMIN')` kiểm tra chuỗi `DOC_ADMIN` chính xác.

`isAuthenticated()` và `isFullyAuthenticated()` không hoàn toàn đồng nghĩa trong cấu hình Spring Security có remember-me. Với thao tác nhạy cảm, cần quyết định có cho phép phiên remember-me không; `isFullyAuthenticated()` **không** chứng minh người dùng vừa thực hiện MFA hoặc xác thực lại trong vài phút gần đây. Chính sách xác thực tăng cường phải kiểm tra bằng chứng riêng nếu nghiệp vụ yêu cầu.

## 9. Ngăn lỗi self-invocation: gọi nội bộ không đi qua proxy

Đây là bẫy thường gặp nhất khi áp dụng method security bằng Spring AOP:

~~~java
@Service
public class UnsafeReportService {

    public void runReport() {
        exportSensitiveReport(); // Gọi nội bộ trên this.
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void exportSensitiveReport() {
        // Giả sử đây là thao tác nhạy cảm.
    }
}
~~~

Một bean khác gọi `runReport()` qua proxy, nhưng lời gọi `this.exportSensitiveReport()` từ bên trong đối tượng thường **không quay lại proxy**. Vì vậy annotation trên `exportSensitiveReport` có thể **không được kiểm tra** trong đường gọi đó. Việc chú thích phương thức nhạy cảm không tự bảo vệ mọi đường gọi nội bộ.

Cách tổ chức rõ ràng hơn là đưa phương thức cần bảo vệ sang **bean khác** và gọi qua bean được inject:

~~~java
@Service
public class ReportOperations {

    @PreAuthorize("hasRole('ADMIN')")
    public void exportSensitiveReport() {
        // Thao tác cần quyền ADMIN.
    }
}

@Service
public class ReportCoordinator {

    private final ReportOperations operations;

    public ReportCoordinator(ReportOperations operations) {
        this.operations = operations;
    }

    public void runReport() {
        operations.exportSensitiveReport();
    }
}
~~~

Hai class trên là hai tệp nguồn Java minh họa; cần thêm `package` và các import `@Service` theo ứng dụng. Ở đây `ReportCoordinator` gọi **bean `ReportOperations` do Spring inject**, cho phép interceptor áp dụng `@PreAuthorize`. Có thể chọn AspectJ weaving nếu thật sự cần bảo vệ cả self-invocation, nhưng đó là một mô hình triển khai khác, đòi hỏi cấu hình và kiểm thử riêng.

Các tình huống dễ bỏ sót tương tự:

- Gọi bean bằng `new` thay vì inject bean Spring.
- Gọi trực tiếp phương thức `private` hoặc `final` trên đối tượng đích.
- Gọi phương thức có annotation qua một đường không được proxy/woven.
- Đặt `@PreAuthorize` trên interface hoặc lớp kế thừa với cơ chế nhận diện annotation không đúng như mong đợi.
- Test tạo đối tượng thủ công và suy ra annotation đang có hiệu lực.

**Phép thử nên gọi đúng đường vào mà ứng dụng sử dụng thực tế**, qua bean Spring, và xác nhận trạng thái nghiệp vụ không thay đổi khi thiếu quyền.

## 10. Khác biệt với @PostAuthorize, @Secured và kiểm tra URL

| Cơ chế | Thời điểm/tầng kiểm tra | Trường hợp thích hợp |
| --- | --- | --- |
| `@PreAuthorize` | Trước lời gọi phương thức đích qua interceptor | Quyền theo danh tính, role, tham số, quyền trên bản ghi |
| `@PostAuthorize` | Sau khi phương thức đích hoàn thành, có thể xét kết quả trả về | Quyền cần nhìn thấy kết quả của phương thức |
| `@Secured` | Kiểm tra role/authority theo cơ chế annotation đơn giản | Trường hợp không cần SpEL phức tạp |
| `authorizeHttpRequests(...)` | Khi HTTP request đi qua chuỗi lọc bảo mật | Bảo vệ method/path, điểm vào HTTP |
| Kiểm tra nghiệp vụ trong service | Khi service chạy logic nghiệp vụ | Các ràng buộc trạng thái, chủ sở hữu, chính sách giao dịch động |

`@PostAuthorize` không thay thế được `@PreAuthorize` đối với thao tác tạo/sửa/xóa có tác dụng phụ: nếu chỉ kiểm tra sau khi phần thân đã chạy, có thể đã ghi dữ liệu trước khi phát hiện không đủ quyền. Vì vậy, **dùng `@PreAuthorize` trước thao tác có tác dụng phụ** khi điều kiện quyền có thể quyết định trước.

`@PreAuthorize` cũng không loại bỏ nhu cầu validation, giao dịch, ràng buộc dữ liệu và kiểm toán. Quyền có thể thay đổi giữa lúc kiểm tra và lúc ghi dữ liệu; đối với các thao tác quan trọng, phải xem xét tính nhất quán giao dịch, việc kiểm tra lại trong cùng phạm vi giao dịch hoặc ràng buộc dữ liệu thích hợp.

## 11. Khi nào việc kiểm tra quyền thực sự chặn thao tác?

Để phân biệt **từ chối bởi @PreAuthorize** với **lỗi trong thân phương thức**, xét các ví dụ:

~~~java
@PreAuthorize("hasAuthority('PAYMENT_APPROVE')")
public void approvePayment() {
    validatePayment();
    transferMoney();
}
~~~

Lời gọi qua proxy có hai tình huống:

1. Không có `PAYMENT_APPROVE`: phần thân `approvePayment` không được gọi; `validatePayment` và `transferMoney` cũng không chạy qua đường gọi đó.
2. Có `PAYMENT_APPROVE`: phần thân được gọi, nhưng `validatePayment` vẫn có thể báo lỗi hoặc `transferMoney` vẫn có thể thất bại. `@PreAuthorize` **không bảo đảm giao dịch nghiệp vụ thành công**.

Nếu đưa kiểm tra quyền vào phần thân sau khi đã làm việc:

~~~java
public void approvePayment() {
    transferMoney();   // Đã gây tác dụng phụ.
    checkPermission(); // Kiểm tra quá muộn.
}
~~~

thì dù `checkPermission()` báo lỗi, một số tác dụng phụ có thể đã xảy ra và không phải mọi hệ thống bên ngoài đều hỗ trợ rollback. Dùng `@PreAuthorize` trước lời gọi giúp đặt ranh giới kiểm soát rõ ràng hơn, nhưng khi có logic bảo mật phụ thuộc trạng thái thay đổi cần kết hợp kiểm soát giao dịch và các ràng buộc dữ liệu.

Lưu ý thêm: bản thân bean được gọi trong biểu thức `@documentPolicy...` vẫn có thể chạy truy vấn/logic để quyết định quyền; không nên cho bean này thực hiện thao tác tạo/xóa không thể hoàn tác.

## 12. Mã HTTP khi @PreAuthorize từ chối: 401 hay 403?

`@PreAuthorize` là **kiểm tra ở tầng phương thức**, không trực tiếp tạo response HTTP. Khi lời gọi bắt nguồn từ một HTTP request, ngoại lệ có thể được xử lý bởi chuỗi Spring Security hoặc bộ xử lý ngoại lệ khác.

| Tình trạng | Phản hồi thường gặp khi gọi HTTP | Vì sao |
| --- | --- | --- |
| Chưa xác thực và cố gọi hành động yêu cầu quyền | 401 với HTTP Basic/Bearer, hoặc chuyển hướng đăng nhập | `AuthenticationEntryPoint`/cấu hình đăng nhập quyết định |
| Đã xác thực nhưng thiếu authority | 403 | `AccessDeniedException` được xử lý như từ chối quyền |
| Đã xác thực, có authority và chính sách tài nguyên cho phép | Request tiếp tục tới phần thân phương thức | Controller/Service quyết định phản hồi cuối |
| Có quyền nhưng nghiệp vụ phát lỗi | 4xx/5xx khác tùy nguyên nhân/xử lý | Không phải kết quả của `@PreAuthorize` |
| Phương thức bị gọi từ worker/scheduler không qua HTTP | Có thể xuất hiện ngoại lệ tại lời gọi | Không có HTTP response để quy ra mã |

Đừng thiết kế kiểm thử unit bằng cách chỉ mong đợi `HTTP 403`, vì phép thử gọi trực tiếp bean nên nhận **ngoại lệ Java**. Muốn kiểm tra status, cần thêm phép thử HTTP của Controller cùng bộ lọc và bộ xử lý ngoại lệ thật.

Khi tích hợp HTTP, phải xét cả thứ tự: URL security hoặc CSRF có thể từ chối request **trước** khi Controller gọi đến service. Một request trả 403 không chứng minh chính `@PreAuthorize` là lớp đã từ chối.

## 13. Sử dụng với Controller và nhiều cửa vào

Giả sử Controller REST gọi vào service đã bảo vệ:

~~~java
@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService documents;

    public DocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping("/{id}")
    public String read(@PathVariable long id) {
        return documents.readDocument(id);
    }

    @PutMapping("/{id}")
    public String edit(@PathVariable long id) {
        return documents.editDocument(id);
    }
}
~~~

Đây là **đoạn mã tích hợp Servlet/MVC**, không phải một phần của ứng dụng không-web ở phần 6. Để dùng cần thêm `spring-boot-starter-web`, import annotation Controller thích hợp và khai báo `SecurityFilterChain` theo chiến lược đăng nhập cụ thể.

Lợi ích là những đường gọi **thực sự đi qua bean `DocumentService`** đều áp dụng cùng chính sách:

~~~text
HTTP Controller ──┐
                  ├──> DocumentService proxy ──> @PreAuthorize ──> method body
Message handler ──┤
                  │
Other Spring bean ┘
~~~

Tuy nhiên, nếu tác vụ định kỳ, message consumer hoặc CLI không có `Authentication` thích hợp trong ngữ cảnh, lời gọi có thể bị từ chối. Không được tắt method security chỉ để các tác vụ nội bộ chạy. Hãy phân quyền tài khoản dịch vụ/luồng hệ thống rõ ràng hoặc tách nghiệp vụ cần có và không cần danh tính một cách có chủ đích.

Một điểm khác: caller có thể không chạm tới `DocumentService` mà gọi thẳng repository hoặc một bean khác để sửa dữ liệu. Annotation trên `DocumentService` không thể kiểm soát mọi thao tác đó. Thiết kế kiến trúc phải đặt đúng ranh giới nghiệp vụ và hạn chế các đường ghi dữ liệu đi vòng qua ranh giới.

## 14. @PreAuthorize trong WebFlux: cùng mục đích, khác ngữ cảnh

Trên Spring WebFlux, có **reactive method security** với cách cấu hình và lấy ngữ cảnh bảo mật tương ứng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

Dịch vụ reactive có thể bảo vệ một phương thức trả `Mono<T>` hoặc `Flux<T>`:

~~~java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<String> readDocument(long id) {
    return reactiveRepository.findById(id).map(Document::content);
}
~~~

Đoạn trên là **minh họa** và cần bean repository/kiểu `Document` cùng ứng dụng WebFlux thực tế. Ở reactive, việc đánh giá/thi hành gắn với chuỗi Publisher và ngữ cảnh Reactor; không dùng `SecurityContextHolder` kiểu `ThreadLocal` như thể ngữ cảnh tự đi theo mọi luồng. Đặc biệt, một `Mono` chỉ được dựng nhưng không được subscribe không đồng nghĩa tác vụ reactive đã chạy.

Để kiểm thử reactive method security, dùng `@EnableReactiveMethodSecurity`, `StepVerifier` và thiết lập ngữ cảnh xác thực reactive phù hợp. Không lấy nguyên cấu hình `@EnableMethodSecurity` của Servlet rồi mặc định mọi cơ chế tương thích với WebFlux.

## 15. Kiểm thử những lỗ hổng mà phép thử “đủ quyền” thường bỏ qua

Một bộ kiểm thử method security tốt nên kiểm tra ít nhất:

| Tình huống | Mục tiêu |
| --- | --- |
| Có authority phù hợp | Phương thức trả dữ liệu đúng |
| Thiếu authority | Ném từ chối, phần thân không chạy |
| Có role ADMIN | Đúng mapping `ROLE_ADMIN` |
| Không có role ADMIN | Không thể gọi hành động quản trị |
| Đúng quyền loại hành động, sai chủ tài liệu | Không thể sửa tài liệu của người khác |
| Đúng chủ tài liệu, thiếu quyền chỉnh sửa | Không được chỉ dựa vào ownership |
| ID tài nguyên không tồn tại | Quy tắc chính sách rõ ràng và an toàn |
| Anonymous | Không vô tình được cấp quyền |
| Gọi qua bean Spring ở đúng đường thực tế | Annotation thật sự được interceptor áp dụng |
| Self-invocation | Phát hiện đường gọi có khả năng bỏ qua proxy |
| Cùng nghiệp vụ qua HTTP và message | Không có đường vào nào vô tình bỏ qua chính sách |

Trong các phép thử, ưu tiên quan sát **trạng thái dữ liệu hoặc dấu hiệu phần thân đã chạy** bên cạnh ngoại lệ. Một exception ở tầng HTTP có thể đến từ CSRF hoặc URL filter trước khi phương thức được gọi; phép thử service nên chứng minh riêng ranh giới `@PreAuthorize`.

Tránh dùng `@WithMockUser` trong phép thử HTTP chạy tới server thật ở một luồng/process khác rồi mặc định danh tính thử nghiệm sẽ tự truyền sang server. Với HTTP end-to-end, hãy thực hiện xác thực trong request thực tế (HTTP Basic, Bearer token, cookie...).

## 16. Các lỗi phổ biến và hướng khắc phục

**Lỗi 1 — Quên `@EnableMethodSecurity`.** Spring Boot có thể khởi động bình thường và phương thức vẫn chạy dù thiếu quyền. Bật method security và bổ sung phép thử từ chối thực tế.

**Lỗi 2 — Khởi tạo service bằng `new`.** Annotation không tự thi hành với đối tượng nằm ngoài Spring. Inject bean từ `ApplicationContext` và kiểm thử đúng bean này.

**Lỗi 3 — Self-invocation.** Phương thức công khai A trong cùng class gọi B có `@PreAuthorize`. Lời gọi nội bộ qua `this` thường bỏ qua proxy. Tách B sang bean khác hoặc chọn mô hình interception được chứng minh bằng test.

**Lỗi 4 — Nhầm `hasRole` với `hasAuthority`.** `hasRole('ADMIN')` mặc định tìm `ROLE_ADMIN`; `hasAuthority('ADMIN')` tìm đúng `ADMIN`. Đối chiếu chuỗi thực tế trong `GrantedAuthority`.

**Lỗi 5 — Dùng thông tin khách hàng tự khai làm chứng cứ chủ sở hữu.** `#owner == authentication.name` sẽ không an toàn nếu `owner` do client gửi. Tải thông tin chủ sở hữu thực từ database theo ID rồi đối chiếu.

**Lỗi 6 — Sai tên tham số SpEL.** `#documentId` không được nhận diện nếu code/compile metadata không cung cấp tên tương ứng. Dùng `@P` hoặc cấu hình `-parameters`, sau đó thử điều kiện theo từng ID.

**Lỗi 7 — Đặt annotation trên method không thể proxy.** Các phương thức private/final/static hoặc class final có thể không được intercept trong kiểu proxy đang sử dụng. Chuyển kiểm tra vào ranh giới public/proxyable và kiểm thử.

**Lỗi 8 — Xem `@PreAuthorize` là thay thế hoàn toàn quyền HTTP.** HTTP entry point vẫn cần xác thực, lọc request, CSRF/CORS tùy ứng dụng; phương thức có thể được gọi từ ngoài HTTP.

**Lỗi 9 — Chỉ dùng `@PostAuthorize` cho thao tác ghi.** Kiểm tra sau khi thực thi có thể quá muộn. Dùng `@PreAuthorize` cho điều kiện xác định được trước khi thao tác, kết hợp giao dịch và kiểm tra trạng thái phù hợp.

**Lỗi 10 — Xem `fullyAuthenticated` là bằng chứng MFA.** Nó phân loại trạng thái xác thực theo Spring Security, không tự xác nhận việc xác thực lại gần đây hoặc nhiều yếu tố.

**Lỗi 11 — Viết biểu thức quá dài hoặc có tác dụng phụ.** Di chuyển kiểm tra dữ liệu vào policy bean có phương thức rõ ràng, không ghi dữ liệu trong bước đánh giá quyền.

**Lỗi 12 — Test qua Controller mà không biết ai chặn.** Nếu đã có bộ lọc URL, CSRF và method security, hãy thử riêng service bean trước, sau đó mới viết kiểm thử HTTP.

**Lỗi 13 — Không xét thay đổi dữ liệu giữa lúc kiểm tra và lúc ghi.** Dữ liệu chủ sở hữu hoặc trạng thái tài liệu có thể đổi. Với hành động quan trọng cần cơ chế giao dịch/khóa/ràng buộc dữ liệu phù hợp để tránh sai lệch theo thời gian.

## 17. Câu hỏi tự kiểm tra

**1.** Spring Boot có dependency `spring-boot-starter-security`, service có `@PreAuthorize` nhưng chưa bật `@EnableMethodSecurity`. Có thể tin rằng annotation chắc chắn đã chạy không?

**Đáp án:** Không. Method security không được bật mặc định chỉ bằng starter; cần cấu hình `@EnableMethodSecurity` và kiểm thử một lời gọi qua bean Spring.

**2.** Người dùng có `ROLE_ADMIN` nhưng thiếu `DOC_EDIT`. Biểu thức `hasRole('ADMIN')` có thể đúng còn `hasAuthority('DOC_EDIT')` sai không?

**Đáp án:** Có. Chúng kiểm tra hai authority khác nhau. Mỗi yêu cầu nghiệp vụ phải dùng điều kiện phù hợp.

**3.** Vì sao `@PreAuthorize("hasAuthority('DOC_EDIT')")` chưa đủ để giới hạn sửa tài liệu theo chủ sở hữu?

**Đáp án:** Authority chỉ cho biết người dùng có quyền chỉnh sửa loại tài nguyên. Muốn giới hạn bản ghi cụ thể, phải kiểm tra quan hệ ownership/quyền trên ID bằng dữ liệu đáng tin cậy.

**4.** Nếu một service gọi chính phương thức có `@PreAuthorize` của nó qua `this`, annotation có luôn thi hành không?

**Đáp án:** Không. Với Spring AOP proxy thông thường, self-invocation không đi qua proxy. Phải thay đổi ranh giới bean hoặc cơ chế interception.

**5.** `@PreAuthorize` từ chối thì phần thân đã tăng bộ đếm/ghi dữ liệu hay chưa?

**Đáp án:** Nếu lời gọi được proxy bảo vệ đúng và bị từ chối **trước khi gọi phương thức đích**, phần thân chưa chạy. Nhưng các phép tra cứu trong chính biểu thức phân quyền có thể đã thực hiện công việc.

**6.** Kiểm thử service trực tiếp nên mong HTTP 403 hay ngoại lệ Java?

**Đáp án:** Ngoại lệ Java (thường là `AccessDeniedException` khi đã có danh tính nhưng thiếu quyền). HTTP status chỉ xuất hiện khi có request HTTP và bộ xử lý ngoại lệ phù hợp.

**7.** Có thể dùng `@PreAuthorize` để kiểm tra `#id` không?

**Đáp án:** Có, nếu tên tham số được khám phá đúng, ví dụ gắn `@P("id")` hoặc biên dịch với `-parameters`; nên kiểm thử với các ID khác nhau.

**8.** `@PreAuthorize` có bảo đảm phần thân không gặp lỗi hoặc rollback mọi tác dụng phụ không?

**Đáp án:** Không. Nó kiểm soát điều kiện trước lời gọi; các lỗi sau đó và tính nhất quán giao dịch vẫn thuộc trách nhiệm nghiệp vụ.

## 18. Tóm lược mô hình vận hành

~~~text
Người gọi có Authentication thích hợp?
        |
        v
Gọi method qua Spring-managed bean/proxy?
        |
        v
Method security đã bật và annotation được nhận diện?
        |
        v
Đánh giá biểu thức @PreAuthorize
   - Quyền chung: hasAuthority, hasRole...
   - Quyền cụ thể: @documentPolicy.isOwner(..., #id)
        |
        +--> TỪ CHỐI: ngoại lệ; không gọi thân phương thức đích
        |
        +--> CHO PHÉP: chuyển lời gọi tới phần thân
                       kiểm tra nghiệp vụ, giao dịch, xử lý dữ liệu
~~~

**Quy tắc nhớ:** `@PreAuthorize` bảo vệ **lời gọi tới phương thức do Spring quản lý** bằng một **điều kiện được đánh giá trước khi chạy phần thân**. Việc bảo vệ đáng tin cậy đòi hỏi cả ba yếu tố: **bật interceptor**, **gọi qua đúng bean/proxy**, và **viết biểu thức dựa trên quyền cùng dữ liệu xác thực đáng tin cậy**.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/method-security.html): kích hoạt, lời gọi `@PreAuthorize`, tham số và các giới hạn proxy.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/6.3/servlet/test/method.html): `@WithMockUser`, `@WithAnonymousUser` và kiểm thử qua bean Spring.
- [Spring Security — Method Authorization API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authorization/method/PreAuthorizeAuthorizationManager.html): bộ quản lý phân quyền trước phương thức.
- [Spring Security — @PreAuthorize API](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/access/prepost/PreAuthorize.html): annotation và điều kiện SpEL.
- [Spring Security — Annotation @P](https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/core/parameters/P.html): đặt tên tham số cho biểu thức.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): ý nghĩa proxy và self-invocation trong Spring AOP.
