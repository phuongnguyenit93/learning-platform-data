# Kiểm thử @PostAuthorize: kết quả đúng quyền, sai quyền và null

## 1. Mục tiêu bài học

Bài này thuộc phần **Kiểm thử phương thức** của module Spring Security – authorization. Sau khi thực hành, bạn có thể:

- Giải thích vì sao @PostAuthorize kiểm tra **giá trị trả về sau khi phương thức thực thi** và phân biệt nó với @PreAuthorize.
- Viết phép kiểm tra quyền sở hữu theo người dùng hiện tại bằng **returnObject** và **authentication.name**.
- Dùng JUnit 5 và **@WithMockUser** kiểm tra ba tình huống bắt buộc: kết quả thuộc quyền người gọi, kết quả không thuộc quyền và kết quả **null**.
- Phân biệt chính sách **từ chối null** với chính sách **cho phép null**, kiểm tra ngoại lệ/giá trị trả về tương ứng.
- Xác nhận rằng phương thức đã chạy dù kết quả bị từ chối; tránh những lỗi thường khiến kiểm thử method security cho kết quả sai.

Phạm vi ví dụ: ứng dụng Spring Boot dùng **servlet method security**, Java 17+, Spring Security 6.x (thông qua Spring Boot 3.5.x), JUnit Jupiter. Ví dụ kiểm thử trực tiếp Spring bean, không cần tạo HTTP controller hay cơ sở dữ liệu.

## 2. @PostAuthorize làm gì?

Khi bật @EnableMethodSecurity, Spring Security đăng ký interceptor dùng proxy để áp dụng @PostAuthorize cho phương thức của Spring bean. Với một lời gọi đi qua proxy, luồng cơ bản là:

1. Test thiết lập **Authentication** (ở đây dùng @WithMockUser).
2. Proxy gọi phương thức service; phương thức tạo hoặc truy vấn kết quả.
3. Interceptor đánh giá biểu thức SpEL trong @PostAuthorize. **returnObject** chính là kết quả vừa được phương thức trả về; **authentication.name** là tên người dùng hiện tại.
4. Biểu thức đúng: đối tượng được trả lại caller. Biểu thức sai: mặc định Spring Security ném ngoại lệ thuộc họ **AccessDeniedException**, caller không nhận được đối tượng.

Ví dụ quy tắc cho một tài liệu có thuộc tính owner:

~~~java
@PostAuthorize("returnObject != null and returnObject.owner == authentication.name")
public DocumentView findStrict(long id) {
    // Trả về tài liệu hoặc null.
}
~~~

Điều kiện gồm hai vế, đánh giá ngắn mạch: kết quả phải khác null **và** chủ sở hữu tài liệu trùng với người đã xác thực. SpEL có thể truy cập thuộc tính **owner** qua getter Java **getOwner()**.

Khác biệt về thời điểm:

| Annotation | Thời điểm quyết định | Khi không đủ quyền |
| --- | --- | --- |
| @PreAuthorize | Trước khi chạy thân phương thức | Thân phương thức không được thực thi |
| @PostAuthorize | Sau khi thân phương thức trả về | Thân phương thức đã chạy, nhưng kết quả bị chặn |

**Hệ quả quan trọng:** @PostAuthorize phù hợp để bảo vệ kết quả đọc đã tải về; không nên dựa vào nó để bảo vệ thao tác ghi/xóa có tác dụng phụ. Từ chối kết quả **không đồng nghĩa** tự động hoàn tác thay đổi đã thực hiện.

## 3. Chốt kỳ vọng cho từng trường hợp

Trong dữ liệu mẫu, tài liệu số 1 thuộc **alice**, tài liệu số 2 thuộc **bob**, ID 999 không tồn tại. Ta cố ý tạo hai phương thức với hai chính sách null:

- **findStrict**: kết quả null bị từ chối vì điều kiện bắt đầu bằng **returnObject != null**.
- **findAllowMissing**: kết quả null được phép trả về vì điều kiện bắt đầu bằng **returnObject == null**; kết quả có thật vẫn phải đúng chủ sở hữu.

| Người gọi | Phương thức | ID | Kết quả service tạo ra | Kỳ vọng caller quan sát được |
| --- | --- | ---: | --- | --- |
| alice | findStrict | 1 | DocumentView(owner=alice) | Nhận đúng tài liệu |
| bob | findStrict | 1 | DocumentView(owner=alice) | AccessDeniedException |
| alice | findStrict | 999 | null | AccessDeniedException |
| alice | findAllowMissing | 999 | null | Nhận null |
| alice | findAllowMissing | 2 | DocumentView(owner=bob) | AccessDeniedException |

Không có quy tắc mặc định rằng @PostAuthorize luôn cho phép hoặc luôn từ chối null; **biểu thức và chính sách nghiệp vụ** quyết định. Nếu viết biểu thức truy cập trực tiếp **returnObject.owner** mà không xử lý null, SpEL có thể lỗi khi truy cập thuộc tính null, khác với việc cố ý trả về quyết định từ chối. Hai biểu thức ở trên tránh vấn đề đó.

## 4. Dự án Maven có thể chạy độc lập

Tạo cấu trúc sau (tên package thống nhất với thư mục):

~~~text
post-authorize-demo/
├── pom.xml
├── src/main/java/com/example/authz/
│   ├── PostAuthorizeApplication.java
│   ├── DocumentView.java
│   └── DocumentService.java
└── src/test/java/com/example/authz/
    └── DocumentServiceSecurityTest.java
~~~

**pom.xml** — phiên bản cụ thể để có thể chạy lại; starter test cung cấp JUnit Jupiter, còn spring-security-test cung cấp @WithMockUser.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>post-authorize-demo</artifactId>
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
~~~

**PostAuthorizeApplication.java** — bật method security. Nếu thiếu @EnableMethodSecurity, annotation trên service có thể không được áp dụng và các phép kiểm thử từ chối sẽ thất bại.

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class PostAuthorizeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeApplication.class, args);
    }
}
~~~

**DocumentView.java** — một đối tượng trả về có getter công khai để SpEL đọc thuộc tính owner.

~~~java
package com.example.authz;

public final class DocumentView {
    private final long id;
    private final String owner;

    public DocumentView(long id, String owner) {
        this.id = id;
        this.owner = owner;
    }

    public long getId() {
        return id;
    }

    public String getOwner() {
        return owner;
    }
}
~~~

**DocumentService.java** — dữ liệu giả lập giúp kiểm thử tất định. Biến đếm chứng minh thân phương thức đã chạy, kể cả khi caller nhận AccessDeniedException.

~~~java
package com.example.authz;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {
    private final AtomicInteger invocations = new AtomicInteger();

    // Null bị từ chối: chỉ trả tài liệu thuộc về người gọi.
    @PostAuthorize("returnObject != null and returnObject.owner == authentication.name")
    public DocumentView findStrict(long id) {
        invocations.incrementAndGet();
        return load(id);
    }

    // Null được phép: "không tìm thấy" có thể được trả về cho caller.
    @PostAuthorize("returnObject == null or returnObject.owner == authentication.name")
    public DocumentView findAllowMissing(long id) {
        invocations.incrementAndGet();
        return load(id);
    }

    private DocumentView load(long id) {
        if (id == 1L) {
            return new DocumentView(1L, "alice");
        }
        if (id == 2L) {
            return new DocumentView(2L, "bob");
        }
        return null;
    }

    public void resetInvocationCount() {
        invocations.set(0);
    }

    public int invocationCount() {
        return invocations.get();
    }
}
~~~

Hai phương thức public được gọi từ **bean do Spring quản lý** nên lời gọi đi qua security proxy. Hàm private load chỉ làm nhiệm vụ cung cấp dữ liệu; nó không tự chứa chính sách phân quyền.

## 5. Bộ kiểm thử JUnit 5: đúng quyền, sai quyền, null

**DocumentServiceSecurityTest.java** — dùng @SpringBootTest để khởi tạo context thực và inject proxy của service. @WithMockUser đưa tên người dùng đã chỉ định vào SecurityContext cho từng test; không cần tài khoản tồn tại trong database.

~~~java
package com.example.authz;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class DocumentServiceSecurityTest {

    @Autowired
    private DocumentService service;

    @BeforeEach
    void resetCounter() {
        service.resetInvocationCount();
    }

    @Test
    @WithMockUser(username = "alice")
    void ownerCanReadMatchingDocument() {
        DocumentView actual = service.findStrict(1L);

        assertNotNull(actual);
        assertEquals(1L, actual.getId());
        assertEquals("alice", actual.getOwner());
        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "bob")
    void nonOwnerIsDeniedAfterMethodExecutes() {
        assertThrows(AccessDeniedException.class,
                () -> service.findStrict(1L));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void strictPolicyDeniesNullResult() {
        assertThrows(AccessDeniedException.class,
                () -> service.findStrict(999L));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void allowMissingPolicyReturnsNull() {
        assertNull(service.findAllowMissing(999L));

        assertEquals(1, service.invocationCount());
    }

    @Test
    @WithMockUser(username = "alice")
    void allowMissingStillDeniesAnotherOwnersDocument() {
        assertThrows(AccessDeniedException.class,
                () -> service.findAllowMissing(2L));

        assertEquals(1, service.invocationCount());
    }
}
~~~

**Vì sao mỗi assertion cần thiết?**

1. **Đúng quyền:** không chỉ kiểm tra không có exception; còn xác nhận ID và chủ sở hữu trả về đúng với dữ liệu dự định.
2. **Sai quyền:** assertThrows xác nhận lớp kết quả bị chặn; đếm lời gọi bằng 1 xác nhận việc từ chối diễn ra **sau khi** thân phương thức chạy.
3. **Null + chính sách strict:** không nhận một giá trị null im lặng; phải nhận AccessDeniedException theo biểu thức đã đặt.
4. **Null + chính sách allow-missing:** nhận chính xác null (không phải exception), bảo toàn ngữ nghĩa “không tìm thấy”.
5. **Chính sách allow-missing vẫn bảo vệ dữ liệu:** chấp nhận null không có nghĩa cho phép một đối tượng thuộc người khác đi qua.

Sử dụng **AccessDeniedException** trong assertThrows cho phép bắt cả subtype chuyên biệt của Spring Security; kiểm thử tập trung vào hợp đồng phân quyền thay vì phụ thuộc một lớp triển khai quá hẹp.

## 6. Chạy và đọc kết quả

Trong thư mục chứa pom.xml, cần JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

Nếu cấu hình và mã đúng, Maven Surefire sẽ chạy **5 bài kiểm thử**; kỳ vọng **5 pass, 0 failure, 0 error** (các dòng log khác phụ thuộc môi trường). Không cần chạy main application hay gọi HTTP để kiểm tra quyền tại service.

Hãy thử tạo lỗi có chủ đích để chắc chắn bài test thật sự bắt được thiếu sót: tạm bỏ @EnableMethodSecurity, chạy lại test. Các trường hợp mong đợi AccessDeniedException sẽ thất bại vì service không còn interceptor chặn kết quả. Khôi phục annotation sau thí nghiệm.

Có thể đổi **username="alice"** thành **username="bob"** trong kiểm thử đầu tiên: cùng tài liệu ID 1 bây giờ phải bị từ chối. Thử đổi biểu thức từ **and** thành **or** trong findStrict: trường hợp null sẽ được cho qua, khiến kiểm thử strict phát hiện hồi quy.

## 7. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Sai quyền vẫn đọc được tài liệu | Thiếu @EnableMethodSecurity, gọi đối tượng tạo bằng new hoặc bypass proxy | Inject Spring bean trong test; giữ phép kiểm thử negative |
| Null gây lỗi truy cập thuộc tính của SpEL | Dùng returnObject.owner mà không có nhánh null | Viết rõ returnObject != null and ... hoặc returnObject == null or ... |
| Kiểm thử luôn pass dù chưa bật security | Chỉ test nhánh được phép, hoặc mock chính service chứa annotation | Test cả ngoại lệ khi sai quyền; dùng service bean thật và giả lập dữ liệu phía dưới |
| Kỳ vọng sai cho null | Chưa thống nhất “không tồn tại” là null hợp lệ hay truy cập bị từ chối | Xác định chính sách nghiệp vụ rồi assertThrows hoặc assertNull |
| Đã bị từ chối nhưng dữ liệu vẫn thay đổi | @PostAuthorize kiểm tra sau khi thực thi, không chặn thao tác trước đó | Dùng @PreAuthorize trước thao tác có side effect; đặt phân quyền ở đúng boundary |
| Test đúng user trong service nhưng sai với principal thật | @WithMockUser tạo tên đăng nhập đơn giản, còn ứng dụng dùng JWT/custom principal | Kiểm thử thêm SecurityContext hoặc request với Authentication thực tế tương ứng |

**Lưu ý về proxy:** lời gọi nội bộ kiểu **this.findStrict(...)** trong cùng bean thường không đi qua proxy, nên không kích hoạt lại annotation của phương thức được gọi. Đặt lời gọi bảo vệ từ một bean khác hoặc inject đúng proxy khi cần test.

**Lưu ý về phạm vi kiểm thử:** @WithMockUser kiểm tra authorization tại service; nó **không** tự xác minh JWT, login, ánh xạ HTTP 403 hay Spring MVC exception handling. Khi cần những hợp đồng đó, thêm kiểm thử MockMvc riêng. Với kết quả **Optional.empty()**, giá trị returnObject là một Optional khác null; không dùng suy luận của bài test null để đánh giá Optional mà không điều chỉnh biểu thức.

## 8. Checklist nghiệm thu

- [ ] Test dùng Spring-managed **DocumentService** và đã bật **@EnableMethodSecurity**.
- [ ] Người đúng quyền nhận đúng DocumentView.
- [ ] Người sai quyền nhận **AccessDeniedException**, không nhận dữ liệu.
- [ ] Null được kiểm thử theo **hai chính sách explicit**: từ chối và cho phép.
- [ ] Cho phép null không làm lọt tài liệu của người khác.
- [ ] Có assertion xác nhận service **đã thực thi trước** khi @PostAuthorize từ chối.
- [ ] Mã, package, JDK, dependency và tên test khớp; chạy **mvn test** thành công.

## 9. Tài liệu chính thức

- Spring Security — Method Security, phần **Authorization Method Results with @PostAuthorize**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — **Testing Method Security**, phần **@WithMockUser**: https://docs.spring.io/spring-security/reference/servlet/test/method.html

**Ghi nhớ:** viết test theo ba kết quả quan sát được của caller (**nhận đúng đối tượng / bị từ chối / null**), đồng thời kiểm tra thời điểm thực thi. Một chính sách @PostAuthorize tốt phải nói rõ null được đối xử thế nào và phải được test bằng cả nhánh cho phép lẫn từ chối.