# Thứ tự với @Transactional và tác động của việc từ chối sau thực thi

> **Ngữ cảnh:** Spring Security **Servlet**, Spring Boot 3.x, Spring Security 6.x, Java 17+ và Spring transaction management (thường là JPA). Trọng tâm là tương tác giữa **method security** (`@PreAuthorize`, `@PostAuthorize`) và **transaction advice** (`@Transactional`): thứ tự AOP mặc định, thời điểm bắt đầu/commit/rollback, vì sao trả HTTP **403 sau khi phương thức chạy không chứng minh dữ liệu đã được rollback**, cách thiết kế thao tác ghi an toàn và cách kiểm thử trên database thực. Các đoạn Boot yêu cầu dự án đúng dependencies; phần Java SE cuối bài chạy độc lập bằng JDK 17.

## 1. Tình huống khó: “Đã trả 403, tại sao database vẫn thay đổi?”

Hãy xét phương thức nghiệp vụ sau (đây là **mảnh minh họa có chủ ý không an toàn**, không dùng làm API ghi dữ liệu thật):

~~~java
@Transactional
@PostAuthorize("returnObject.ownerName == authentication.name")
public DocumentEntity changeThenCheck(Long id, String text) {
    DocumentEntity document = repository.findById(id).orElseThrow();
    document.setBody(text);     // Ghi thay đổi trong persistence context.
    return document;           // Chỉ sau khi method trả về mới kiểm tra.
}
~~~

Giả sử tài liệu thuộc về `alice`; user `bob` xác thực đúng nhưng gọi cập nhật tài liệu đó. Điều gì xảy ra?

1. Phương thức được gọi qua **Spring proxy**, JPA nạp bản ghi.
2. Phương thức sửa nội dung tài liệu và trả entity.
3. Transaction advisor có thể **flush và commit** dữ liệu khi method hoàn tất.
4. `@PostAuthorize` sau đó mới kiểm tra `returnObject.ownerName` với `authentication.name`.
5. So sánh false; Spring Security ném từ chối truy cập và HTTP có thể trả **403**.
6. **Nhưng thay đổi trong database có thể đã commit trước đó.**

Với cấu hình advice mặc định phổ biến, đây là tình huống thực tế cần kiểm thử. **Không thể suy ngược “403 = không có side effect”.** Việc security check chặn response và việc database rollback là hai điều kiện khác nhau.

Nếu phương thức phát email, gửi event ra broker, gọi API thanh toán hoặc ghi sang hệ thống khác **trước khi bị @PostAuthorize từ chối**, transaction của JPA cũng không thể tự thu hồi các side effect ở hệ thống ngoài. Đó là lý do cơ bản không được lấy kiểm tra *sau thực thi* làm rào chắn chính cho thao tác ghi quan trọng.

### Hai mục tiêu bảo mật phải được tách

- **Không tiết lộ dữ liệu cho người không có quyền.** Một `@PostAuthorize` trên hàm đọc có thể chặn việc trả về object khi object chỉ được biết sau khi truy vấn.
- **Không cho thực hiện thao tác ghi ngoài quyền hạn.** Điều kiện này cần được kiểm tra **trước side effect** (và khi cần, xác nhận lại bên trong transaction tại thời điểm sử dụng dữ liệu).

Hai mục tiêu liên quan nhưng **không đồng nhất**. Một result bị chặn sau khi tính toán không làm quá trình tính toán trở về trạng thái trước đó.

## 2. Method security và transaction là hai lớp AOP

Spring dùng proxy/advisor/interceptor để thực thi nhiều hành vi khai báo quanh cùng một lời gọi phương thức.

| Annotation / cơ chế | Mục tiêu chính | Thời điểm quan trọng |
| --- | --- | --- |
| `@PreAuthorize` | Đánh giá điều kiện truy cập **trước khi** method body chạy. | Trước gọi method. |
| `@PostAuthorize` | Đánh giá biểu thức với `returnObject` **sau khi** method trả về. | Sau body, trước khi caller nhận kết quả. |
| `@PreFilter` | Lọc tham số dạng collection/array/map trước gọi nếu thích hợp. | Trước body; **không phải** transaction guard. |
| `@PostFilter` | Lọc các phần tử của kết quả sau lời gọi. | Sau body; không rollback side effect. |
| `@Transactional` | Thiết lập phạm vi transaction, commit hoặc rollback theo quy tắc. | Quanh invocation trong phạm vi advisor. |
| Spring MVC / servlet filters | Chuyển denial exception thành HTTP response. | Sau khi lỗi đi từ service lên HTTP layer. |

**Một phương thức Java không có thứ tự annotation vì bạn viết dòng nào trước.** Thứ tự `@PreAuthorize`, `@Transactional` và `@PostAuthorize` trong file source **không quyết định** thứ tự interceptors. Thứ tự thực tế phụ thuộc các **advisor order**, proxy chain, cấu hình bật method security/transaction và version tương thích.

Vì vậy, chỉ thay:

~~~java
@PreAuthorize("hasAuthority('EDIT')")
@Transactional
public void edit(...) { ... }
~~~

thành:

~~~java
@Transactional
@PreAuthorize("hasAuthority('EDIT')")
public void edit(...) { ... }
~~~

**không có ý nghĩa “đổi transaction ra ngoài”**. Hai ví dụ trên đều chỉ là mảnh code mô tả, cần method body/bean thật để dùng. Muốn điều chỉnh nesting phải can thiệp đúng order của Spring AOP hoặc thiết kế lại ranh giới method/transaction.

## 3. Thứ tự advice mặc định thường gặp

Khi bật Spring Security method security hiện đại bằng `@EnableMethodSecurity`, các interceptor có những giá trị order được định nghĩa để triển khai kiểm tra theo thời điểm khác nhau. Với cấu hình mặc định được công bố trong dòng Spring Security 6, một số mốc thường gặp là:

~~~text
@PreFilter     khoảng 100
@PreAuthorize  khoảng 200
@Secured       khoảng 300 (nếu bật)
@RolesAllowed  khoảng 400 (nếu bật JSR-250)
@PostAuthorize khoảng 500
@PostFilter    khoảng 600

Transaction advisor mặc định:
  @EnableTransactionManagement(order = LOWEST_PRECEDENCE)
  tức thứ tự rất thấp về mức ưu tiên
~~~

**Lưu ý phiên bản và cấu hình:** Đây là sơ đồ phục vụ đọc hiểu default advice trong các bản Spring Security 6.x, **không phải quy tắc vĩnh viễn** cho mọi release. Các offset, advisor bổ sung, proxy chain, override order hoặc kết hợp nhiều proxy có thể thay đổi hành vi. Khi kết quả giao dịch là ranh giới bảo mật, phải **kiểm chứng order thực tế của ứng dụng** chứ không chỉ tin một bảng số.

Trong Spring AOP, advisor có **order ưu tiên cao hơn (giá trị số nhỏ hơn)** thường bao ngoài advisor ưu tiên thấp hơn (giá trị số lớn hơn). Trên đường đi vào method, advisor ngoài chạy trước; trên đường đi ra, logic “sau method” của advisor ngoài chạy **sau cùng**.

Với các mặc định trên, mô hình dễ gặp:

~~~text
Request / Controller
  |
  v
[PreAuthorize advisor, order ~200]          <- kiểm tra quyền trước
  |
  v
[PostAuthorize advisor, order ~500]         <- bao phía ngoài tx
  |
  v
[TransactionInterceptor, LOWEST_PRECEDENCE]
  | BEGIN transaction
  |      |
  |      v
  |   Target service method
  |      |
  |   JPA thay đổi entity
  |      |
  | COMMIT transaction
  v
[PostAuthorize kiểm tra returnObject]        <- có thể từ chối SAU commit
  |
  v
Caller / Controller / Servlet exception handling
~~~

Kết luận: **Một denied decision sau method có thể xảy ra *bên ngoài* phạm vi transaction đã commit.**

### Tại sao có hiện tượng này?

Advisor transaction nằm **bên trong** advice `@PostAuthorize`. Interceptor transaction nhận kết quả method, thực hiện commit rồi trả result cho interceptor ngoài. Lúc đó post-authorization mới đọc `returnObject` và có thể từ chối. Exception được ném ra **sau** khi transaction interceptor đã kết thúc thành công nên nó không có transaction ấy để rollback.

Ngược lại, `@PreAuthorize` thông thường chạy trước transaction advisor khi nó nằm bên ngoài: nếu thiếu quyền, method body không được gọi, transaction ghi tương ứng **chưa được bắt đầu** bởi advisor bên trong. Đây là hành vi mong muốn cho một chốt truy cập tổng quát.

### Không nhầm “advisor outer” với “transaction outer”

Khi ta nói **transaction outer**, nghĩa là transaction interceptor bao bên ngoài `@PostAuthorize`, ví dụ về mặt logic:

~~~text
TransactionInterceptor
  BEGIN
    PostAuthorize interceptor
      Target method sửa dữ liệu
      PostAuthorize kiểm tra kết quả -> DENY, ném runtime exception
  ROLLBACK khi exception đi ra khỏi transaction boundary
~~~

Trong sơ đồ này, một exception thuộc loại RuntimeException/AccessDeniedException đi xuyên qua transaction interceptor có thể kích hoạt **rollback theo default rules**. Tuy nhiên đó là **một cấu hình thứ tự khác**; không được mặc định cho rằng app đang chạy như vậy.

## 4. Quy tắc rollback của @Transactional không phải “mọi lỗi đều rollback”

Spring transaction management mặc định thường **rollback với `RuntimeException` và `Error`**, không tự rollback với mọi checked exception. Việc thay đổi rollback rules, bắt/suppress exception, nested transactions hay propagation làm thay đổi kết quả.

| Sự kiện | Khả năng rollback |
| --- | --- |
| `RuntimeException` đi ra khỏi method khi transaction **chưa commit** | Mặc định rollback transaction đó. |
| Checked exception đi ra và không có `rollbackFor` | Không mặc định rollback trong kiểu cấu hình cổ điển. |
| Exception bị catch rồi return bình thường | Transaction advisor có thể commit nếu không được đánh dấu rollback-only. |
| Exception được ném **sau khi transaction đã commit** | Không thể rollback transaction đã hoàn thành. |
| `@Transactional(noRollbackFor=...)` phù hợp exception | Có thể commit bất chấp exception nếu rule cấu hình vậy. |
| `REQUIRES_NEW` đã commit ở lời gọi khác | Không tự bị rollback bởi transaction ngoài về sau. |
| Email/HTTP call/event gửi ngoài transaction | Không được database rollback thu hồi. |
| Thay đổi DB chỉ nằm trong persistence context và chưa flush/commit | Có thể rollback nếu lỗi xảy ra **trong** transaction phù hợp. |

Trong Spring Security 6, lỗi thiếu quyền thường biểu hiện qua `AccessDeniedException` hoặc kiểu chuyên biệt có quan hệ thừa kế với nó. Đây là runtime exception, nhưng **chỉ thực sự kích hoạt rollback nếu nó đi qua một transaction advisor đang hoạt động**, với rollback rules cho phép.

**Không có sự tương đương** giữa “request trả status 403” và “Spring đã gọi transaction.rollback()”. HTTP exception translation là xử lý **giao thức**; transaction manager là xử lý **dữ liệu**.

### Flush khác commit

Với JPA:

- `entity.setBody(...)` trên một entity được quản lý thường khiến persistence context đánh dấu dirty; SQL UPDATE có thể được thực hiện lúc flush.
- `flush()` đẩy thay đổi xuống JDBC trong transaction nhưng **không đồng nghĩa transaction đã commit**. Nếu rollback đúng transaction, các update đã flush vẫn có thể bị hủy theo cơ chế DB.
- `commit()` hoàn tất transaction; sau khi commit thành công, việc post-authorize từ chối **không thể “quay lại” commit ấy**.
- Các side effect ở ngoài DB hoặc qua transaction riêng là chuyện khác; ngay cả rollback JPA thành công không thu hồi được một email đã gửi.

Vì vậy, đừng kết luận “database đã bị ghi vĩnh viễn” chỉ vì SQL UPDATE đã xuất hiện trong log. Cần **đọc lại trạng thái bằng một transaction mới** sau khi request hoàn tất, như các test tích hợp ở mục 9.

## 5. @PreAuthorize, @PostAuthorize: dùng đúng mục đích

### @PreAuthorize: chặn trước method body

~~~java
@PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
@Transactional
public void updateDocument(Long id, String body) {
    // Viết dữ liệu...
}
~~~

Đây là **mảnh code**, không tự biên dịch nếu thiếu class/import/method body. Với user không có `DOCUMENT_WRITE`, Spring Security chặn trước khi phương thức ghi chạy, nếu lời gọi đi qua proxy security.

Nhược điểm cần lưu ý: `hasAuthority("DOCUMENT_WRITE")` là **quyền chức năng chung**, chưa kiểm tra *có được sửa tài liệu ID này hay không*. Một người có quyền viết có thể vẫn không được sửa tài liệu thuộc tenant khác. Bạn phải thêm authorization theo tài nguyên phía server, không dựa vào ID do client gửi là “đã được xác minh”.

### @PostAuthorize: kiểm tra returnObject sau khi method chạy

~~~java
@Transactional(readOnly = true)
@PostAuthorize("returnObject.ownerName == authentication.name")
public DocumentEntity readOwnedDocument(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Dùng **read-only method** để nạp tài liệu, sau đó kiểm tra owner của object trả về có thể phù hợp cho một số flow. Tuy nhiên:

- Phương thức và các interceptor bên trong đã chạy trước khi result bị từ chối.
- `readOnly=true` là hint/quản lý transaction read-only, **không nên coi là một tường bảo mật tự động**: code khác vẫn có thể tạo side effect (gửi event, gọi API, cache...) nếu lập trình sai.
- Với JPA lazy-loading, nếu `@PostAuthorize` chạy sau transaction và entity đã detached, việc truy cập một association chưa tải có thể gây lỗi. Dùng DTO chứa dữ liệu cần kiểm tra hoặc fetch các thuộc tính quan trọng trong transaction.
- Nếu method có logging/audit nhạy cảm trước khi kiểm tra, deny return value **không thu hồi log**.

**Đừng dùng @PostAuthorize làm điều kiện chính cho POST/PUT/PATCH/DELETE có side effect.** Dùng nó chủ yếu để **hạn chế giá trị trả về** trong những flow thuần đọc đã được thiết kế không phát side effect.

### @PostFilter không phải giải pháp hoàn tác

`@PostFilter` lọc phần tử của kết quả sau khi method đã chạy. Nó không thể undo các thay đổi trước đó, và cách filtering có thể tác động mạnh tới performance/memory. Nếu query trả quá nhiều dữ liệu rồi mới lọc, dữ liệu vẫn đã được nạp vào server. Với dữ liệu nhạy cảm lớn, ưu tiên **lọc ngay ở query** theo principal/tenant khi phù hợp.

## 6. Ranh giới “trước thực thi” và “ngay trước ghi” cũng khác nhau

Giả sử `@PreAuthorize("@policy.canEdit(authentication, #id)")` truy vấn bảng owner trước khi transaction của method bắt đầu. Trong thời gian giữa **check** và **use**, một tiến trình khác có thể thay đổi owner/quyền hoặc chuyển tài liệu sang tenant khác. Đây là dạng **TOCTOU (time-of-check to time-of-use)**.

Có ba mức bảo vệ thường dùng:

1. **Chặn quyền tổng quát trước method** bằng `@PreAuthorize`. Ví dụ bắt buộc `DOCUMENT_WRITE`.
2. **Xác minh quyền với dữ liệu thực** bên trong transaction, gần lúc thay đổi entity. Ví dụ sau khi nạp document từ DB, so owner/tenant đáng tin trước khi set dữ liệu.
3. Với race condition quan trọng, dùng **optimistic locking `@Version`, pessimistic locking, SQL UPDATE có điều kiện owner/tenant hoặc isolation phù hợp** để ràng buộc quyết định với trạng thái thực tại lúc ghi. Transaction tự nó không bảo đảm không có TOCTOU trên mọi isolation level.

**Nguyên tắc:** policy phải được thực thi trước side effect không thể thu hồi và trên dữ liệu nguồn tin cậy. Không so owner từ trường `owner` trong JSON client rồi coi đủ, vì attacker có thể sửa request body.

## 7. Dự án minh họa: một phương thức sai, hai chốt đúng

Ví dụ Spring Boot 3 với H2/JPA có mục đích **chứng minh khác biệt quan sát được**:

- Endpoint `POST /docs/{id}/post-only`: cố ý dùng `@PostAuthorize` **sau khi sửa entity**, cho thấy 403 có thể đi kèm **commit**. Đây là lỗ hổng demo, **không dùng trong production**.
- Endpoint `POST /docs/{id}/guarded`: có `@PreAuthorize` kiểm tra `DOCUMENT_WRITE` trước method và kiểm tra owner **trước khi sửa** bên trong transaction.
- Endpoint `GET /docs/{id}/own`: dùng `@PostAuthorize` trên **read-only method** để minh họa kiểm tra owner của result, không có side effect của nghiệp vụ.
- MockMvc kiểm tra user thiếu quyền, user không phải owner và user hợp lệ. Test sử dụng H2 in-memory **thật**, đọc lại DB sau request.

### Dependencies và phạm vi version

Dự án Java 17+ với:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-aop
spring-boot-starter-data-jpa
com.h2database:h2             (runtime)
spring-boot-starter-test      (test)
spring-security-test          (test)
~~~

`spring-boot-starter-aop` được khai báo rõ để tránh phụ thuộc ngầm ở các project có dependency khác nhau. `@EnableMethodSecurity` của Spring Security 6 dùng cơ chế proxy/interceptor; `@Transactional` cần transaction manager, được Boot/JPA autoconfigure trong ví dụ.

Các file nằm trong package `com.example.txsecurity`:

~~~text
src/main/java/com/example/txsecurity/
  TxSecurityApplication.java
  SecurityConfig.java
  DocumentEntity.java
  DocumentRepository.java
  DocumentService.java
  DocumentController.java
src/main/resources/
  application.properties
src/test/java/com/example/txsecurity/
  MethodSecurityTransactionTest.java
~~~

Bài demo không dùng service, security config, repository sẵn có trong hệ thống thật. Tất cả credential đều là **giả để test localhost**, tuyệt đối không copy vào production.

### 7.1. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:txlesson;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

H2 là DB in-memory cho học tập; `create-drop` xóa/khởi tạo schema khi app chạy/dừng, **không** được dùng với DB production. `open-in-view=false` giảm phụ thuộc JPA session vào HTTP request, giúp ranh giới transaction rõ hơn trong bài.

### 7.2. DocumentEntity.java

~~~java
package com.example.txsecurity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "owner_name", nullable = false)
    private String ownerName;

    @Column(name = "body", nullable = false)
    private String body;

    protected DocumentEntity() {
        // JPA cần constructor không đối số.
    }

    public DocumentEntity(String ownerName, String body) {
        this.ownerName = ownerName;
        this.body = body;
    }

    public Long getId() {
        return id;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public String getBody() {
        return body;
    }

    public void setBody(String body) {
        this.body = body;
    }
}
~~~

Entity dùng getter `getOwnerName()` để biểu thức `returnObject.ownerName` đọc được property `ownerName` theo quy ước JavaBean. Nó không lấy owner từ client khi sửa, mà lấy từ bản ghi ở DB.

Với production cần validation chiều dài, concurrency/version, tenancy, audit và chính sách update hợp lệ. Trong demo, chúng ta chỉ muốn làm rõ **order và rollback**.

### 7.3. DocumentRepository.java

~~~java
package com.example.txsecurity;

import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentRepository
        extends JpaRepository<DocumentEntity, Long> {
}
~~~

Spring Data JPA tạo implementation tự động vì interface ở package được Boot scan. Các thao tác `save` và `findById` đều đi qua Spring Data repository; trong service có transaction dài hơn, dirty checking sẽ flush khi transaction commit.

### 7.4. SecurityConfig.java

~~~java
package com.example.txsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement // Sử dụng order mặc định.
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .authorities("DOCUMENT_WRITE", "DOCUMENT_READ")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo-bob"))
            .authorities("DOCUMENT_WRITE")
            .build();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo-reader"))
            .authorities("DOCUMENT_READ")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, reader);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/docs/**")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/docs/**")
                    .authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        // CSRF mặc định bật cho POST; test phải gửi token đúng.
        return http.build();
    }
}
~~~

**Đọc kỹ:**

- `@EnableMethodSecurity` bật xử lý `@PreAuthorize` và `@PostAuthorize`. Không có nó thì các annotations method security có thể không được áp dụng.
- `@EnableTransactionManagement` minh họa bật transaction proxy với **order mặc định**, không chủ động đổi thứ tự để “được rollback”.
- HTTP rule chỉ yêu cầu **authenticated**; các check `DOCUMENT_WRITE` và owner được áp dụng ở service. Nếu thiếu `@EnableMethodSecurity` hoặc gọi bypass proxy, route có thể trở nên nguy hiểm. Production nên kết hợp kiểm tra HTTP policy và service/resource policy có defense-in-depth.
- `httpBasic` là lựa chọn demo. HTTP Basic thực tế chỉ phù hợp trên TLS và theo threat model.
- `alice` và `bob` đều có `DOCUMENT_WRITE`; nhưng chỉ Alice là owner của tài liệu fixture. `reader` chỉ có `DOCUMENT_READ` để chứng minh chốt pre-authorize chặn người thiếu quyền tổng quát.
- CSRF không bị tắt, vì vậy POST thiếu token bị chặn trước khi tới service; không được nhầm một 403 do thiếu CSRF với rollback của service.

### 7.5. DocumentService.java — mã quan trọng nhất

~~~java
package com.example.txsecurity;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {

    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    // CỐ TÌNH KHÔNG AN TOÀN: chỉ kiểm tra sau khi sửa.
    // Dùng để chứng minh 403 vẫn có thể đi kèm commit.
    @Transactional
    @PostAuthorize("returnObject.ownerName == authentication.name")
    public DocumentEntity editPostOnly(Long id, String newBody) {
        DocumentEntity doc = repository.findById(id).orElseThrow();
        doc.setBody(newBody);
        return doc;
    }

    // Phù hợp hơn: chặn quyền chung trước khi method chạy.
    @Transactional
    @PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
    public DocumentEntity editGuarded(Long id, String newBody) {
        DocumentEntity doc = repository.findById(id).orElseThrow();

        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        // Kiểm tra owner/tenant từ record server-side TRƯỚC sửa.
        if (auth == null || !doc.getOwnerName().equals(auth.getName())) {
            throw new AccessDeniedException(
                    "Access denied for this document");
        }

        doc.setBody(newBody);
        return doc;
    }

    // Một use case hợp lý hơn cho PostAuthorize: đọc, không sửa.
    @Transactional(readOnly = true)
    @PostAuthorize("returnObject.ownerName == authentication.name")
    public DocumentEntity readOwn(Long id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

**Phân tích từng method:**

**`editPostOnly`:** Không có `@PreAuthorize` và không check owner trước khi thay dữ liệu. Transaction interceptor có thể commit thay đổi, rồi `@PostAuthorize` mới từ chối khi thấy `returnObject.ownerName != authentication.name`. Đây là lỗi chủ ý để học, **không cho traffic production truy cập**.

**`editGuarded`:** Một user thiếu `DOCUMENT_WRITE` bị chặn trước method. Một user có `DOCUMENT_WRITE` nhưng không phải owner sẽ vào method, nạp record, kiểm tra owner trong transaction rồi ném `AccessDeniedException` **trước khi `setBody`**. Nếu dữ liệu bị thay đổi trước khi exception, runtime exception vẫn có thể đánh dấu transaction rollback; nhưng điều quan trọng là không thực hiện side effect ngay từ đầu.

**`readOwn`:** Dùng `@PostAuthorize` sau khi nạp record ở một read-only transaction. Method chỉ đọc DB, không thay đổi nội dung. Nếu Bob đọc tài liệu Alice, result bị từ chối trước khi HTTP controller trả nội dung. Điều kiện này không thay thế quyền đọc ở tầng SQL/tenant; với dữ liệu nhạy cảm đặc biệt hoặc truy vấn lớn, nên filter ngay tại query.

**Không lấy danh tính từ body hay query:** `SecurityContextHolder.getContext().getAuthentication()` đến từ Spring Security, khác với `request.getParameter("username")` do client tự đặt. Phải bảo đảm authentication provider của app đã xác minh credential đúng và không tự cấp authorities từ input client.

**Không coi mọi truy vấn bên trong transaction là race-free:** Nếu owner bị thay đổi đồng thời sau khi nạp record, isolation/locking/optimistic version mới quyết định kết quả. Trong nghiệp vụ quan trọng, có thể cần SQL UPDATE có điều kiện `owner_id` và `tenant_id`, lock hoặc optimistic concurrency control.

### 7.6. DocumentController.java

~~~java
package com.example.txsecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @PostMapping("/docs/{id}/post-only")
    public String unsafeUpdate(
            @PathVariable Long id,
            @RequestParam("text") String body) {
        return service.editPostOnly(id, body).getBody();
    }

    @PostMapping("/docs/{id}/guarded")
    public String guardedUpdate(
            @PathVariable Long id,
            @RequestParam("text") String body) {
        return service.editGuarded(id, body).getBody();
    }

    @GetMapping("/docs/{id}/own")
    public String readOwn(@PathVariable Long id) {
        return service.readOwn(id).getBody();
    }
}
~~~

**Đường dẫn `/post-only` cố tình không an toàn chỉ để test.** Dù HTTP response trả 403, side effect đã commit có thể xuất hiện. Trong app thực, **bỏ endpoint này** và chỉ triển khai những đường được phép gọi policy trước khi ghi.

Controller chỉ gọi **public methods trên một service bean khác**, nhờ đó lời gọi đi qua Spring AOP proxy. Nếu controller tự `new DocumentService(...)` hoặc service tự gọi `this.editGuarded(...)` trong nội bộ chính nó, proxy interception có thể bị bỏ qua.

### 7.7. TxSecurityApplication.java

~~~java
package com.example.txsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxSecurityApplication.class, args);
    }
}
~~~

Đặt main class trong package cha của các component. Với một project đã có main class, không thêm main thứ hai ngoài phạm vi demo.

## 8. Dòng thời gian của ba tình huống

### 8.1. Alice là owner, được phép ghi

~~~text
HTTP POST /docs/123/guarded + CSRF hợp lệ
  |
  | HTTP authentication: alice
  |
  v
@PreAuthorize: có DOCUMENT_WRITE -> PASS
  |
  v
Transaction: BEGIN
  |
  | Load document #123, ownerName=alice
  | ownerName == authentication.name -> PASS
  | setBody("allowed")
  |
  v
Transaction: FLUSH + COMMIT
  |
  v
HTTP 200, body "allowed"
~~~

### 8.2. Reader thiếu quyền chức năng

~~~text
HTTP POST /docs/123/guarded + CSRF hợp lệ
  |
  | HTTP authentication: reader
  |
  v
@PreAuthorize: không có DOCUMENT_WRITE -> DENY
  |
  x Method body không chạy
  x Không có setBody
  x Không commit thay đổi tài liệu
  |
  v
HTTP thường 403
DB body giữ "original"
~~~

### 8.3. Bob có quyền chức năng nhưng không phải owner — kiểm tra sau quá muộn

~~~text
HTTP POST /docs/123/post-only + CSRF hợp lệ
  |
  | HTTP authentication: bob
  |
  v
PostAuthorize advisor (sẽ kiểm tra SAU)
  |
  v
Transaction: BEGIN
  |
  | Load #123: ownerName=alice
  | setBody("unauthorized-change")
  |
  v
Transaction: COMMIT
  |
  v
@PostAuthorize:
  returnObject.ownerName == authentication.name ?
  "alice" == "bob" -> FALSE
  |
  v
AccessDeniedException -> HTTP 403
  |
  v
Đọc lại DB: body vẫn là "unauthorized-change"
~~~

Cốt lõi của failure: **denied response được tạo sau DB commit**, vì advisor có thứ tự nested như vậy. Đây không phải lỗi database rollback, mà là **đặt điểm kiểm tra quyền sai vị trí trong vòng đời ghi dữ liệu**.

## 9. Kiểm thử tích hợp MockMvc + H2: quan sát cả HTTP và DB

Tạo `src/test/java/com/example/txsecurity/MethodSecurityTransactionTest.java`:

~~~java
package com.example.txsecurity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityTransactionTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DocumentRepository repository;

    private Long documentId;

    @BeforeEach
    void resetDatabase() {
        // Các thao tác repository được commit trước mỗi test.
        repository.deleteAll();
        documentId = repository.saveAndFlush(
                new DocumentEntity("alice", "original")).getId();
    }

    private String databaseBody() {
        // Gọi repository sau khi request đã hoàn tất.
        return repository.findById(documentId)
                .orElseThrow().getBody();
    }

    @Test
    void postAuthorizeCanDenyAfterTransactionCommitted()
            throws Exception {
        mvc.perform(post("/docs/{id}/post-only", documentId)
                .with(csrf())
                .with(httpBasic("bob", "demo-bob"))
                .param("text", "unauthorized-change"))
            .andExpect(status().isForbidden());

        // Điểm cần chứng minh: 403 KHÔNG ngăn được commit trước đó.
        assertEquals("unauthorized-change", databaseBody());
    }

    @Test
    void preAuthorizeStopsUserWithoutWritePermission()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(csrf())
                .with(httpBasic("reader", "demo-reader"))
                .param("text", "should-not-write"))
            .andExpect(status().isForbidden());

        assertEquals("original", databaseBody());
    }

    @Test
    void inTransactionOwnerCheckStopsNonOwner()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(csrf())
                .with(httpBasic("bob", "demo-bob"))
                .param("text", "should-not-write"))
            .andExpect(status().isForbidden());

        assertEquals("original", databaseBody());
    }

    @Test
    void ownerWithWritePermissionMayUpdate()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(csrf())
                .with(httpBasic("alice", "demo-alice"))
                .param("text", "allowed"))
            .andExpect(status().isOk())
            .andExpect(content().string("allowed"));

        assertEquals("allowed", databaseBody());
    }

    @Test
    void postAuthorizeIsUsefulForReadOnlyResult()
            throws Exception {
        mvc.perform(get("/docs/{id}/own", documentId)
                .with(httpBasic("bob", "demo-bob")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/docs/{id}/own", documentId)
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(content().string("original"));

        assertEquals("original", databaseBody());
    }

    @Test
    void csrfDeniedBeforeServiceIsDifferentFailure()
            throws Exception {
        mvc.perform(post("/docs/{id}/guarded", documentId)
                .with(httpBasic("alice", "demo-alice"))
                .param("text", "not-saved"))
            .andExpect(status().isForbidden());

        // 403 có thể do thiếu CSRF chứ không phải method security.
        assertEquals("original", databaseBody());
    }
}
~~~

### Cách hiểu từng test

- `postAuthorizeCanDenyAfterTransactionCommitted` là bài test quan trọng nhất: **HTTP 403 nhưng DB là giá trị đã sửa** dưới advisor order mặc định. Một assertion chỉ nhìn 403 sẽ bỏ qua lỗi bảo mật này.
- `preAuthorizeStopsUserWithoutWritePermission` chứng minh người thiếu `DOCUMENT_WRITE` bị từ chối **trước khi service body chạy**.
- `inTransactionOwnerCheckStopsNonOwner` chứng minh user có quyền tổng quát nhưng không sở hữu object vẫn bị từ chối trước mutation; transaction kết thúc không lưu update.
- `ownerWithWritePermissionMayUpdate` là positive case để tránh cấu hình quá chặt khiến mọi yêu cầu đều bị 403.
- `postAuthorizeIsUsefulForReadOnlyResult` kiểm tra quyền theo object khi chỉ đọc; Bob bị từ chối, Alice được nhận nội dung.
- `csrfDeniedBeforeServiceIsDifferentFailure` cho thấy một 403 phát sinh ở `CsrfFilter`, không phải tại transaction hoặc method annotation. Khi test POST method security phải dùng `csrf()` nếu web chain bật CSRF.

**Rất quan trọng:** test class trên **không** gắn `@Transactional`. Nếu đặt `@Transactional` ở test khiến test và service vô tình dùng cùng một transaction/cùng thread theo cách không đại diện cho HTTP runtime, bạn có thể **che giấu mốc commit** mà bài học cần quan sát. Sau request, test dùng repository operation riêng đọc lại DB để chứng minh kết quả được commit hoặc không.

Chạy bằng Maven Wrapper:

~~~bash
./mvnw test
~~~

Đây là mã test/kỳ vọng có thể tái hiện khi app dùng đúng dependencies, transaction advisor order mặc định và Spring Boot 3/Security 6 tương thích. **Không khẳng định đã chạy trên mọi minor version.** Nếu test “403 nhưng commit” không tái hiện, đầu tiên kiểm tra interceptor/advisor order, method security đã được bật chưa, method có đi qua proxy không, test có transaction bao ngoài không, môi trường JPA transaction/flush và các tùy biến rollback rules.

### Kiểm thử ngoài MockMvc

MockMvc đi qua Servlet filter chain, nhưng không mô phỏng toàn bộ hành vi production của connection pool, distributed transactions, queue, browser/proxy. Với hành động thanh toán/hoàn tiền, cần integration tests chống race, transaction propagation, side effect external và audit/idempotency.

## 10. Nếu đổi order để transaction nằm ngoài @PostAuthorize?

Có thể điều chỉnh thứ tự của transaction advisor. Ví dụ minh họa ở cấp cấu hình toàn ứng dụng:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(order = 0)
class TransactionAdvisorPriorityExample {
}
~~~

**Đây là phương án/thí nghiệm THAY THẾ**, không thêm trực tiếp bên cạnh `@EnableTransactionManagement` hiện có của `SecurityConfig` ở mục 7 rồi mong không có xung đột. Cấu hình này thay đổi **thứ tự transaction advisor trên toàn ứng dụng**, không chỉ một method, và có thể tác động tới transaction bắt đầu sớm hơn (kể cả trước pre-authorize) hoặc mối quan hệ với caching/retry/audit advisors.

Nếu order transaction là `0` (ưu tiên hơn các method-security advisors với order dương theo cấu hình tương ứng), transaction có thể bao ngoài cả `@PostAuthorize`:

~~~text
Transaction: BEGIN
  |
  v
PreAuthorize check
  |
  v
Target method ghi dữ liệu
  |
  v
PostAuthorize check:
  DENY -> RuntimeException
  |
  v
Transaction: ROLLBACK theo rollback rules
~~~

Nhờ vậy, denied exception được truyền **qua** transaction boundary trước commit nên database write có thể rollback. Nhưng điều này **không phải lời giải duy nhất hoặc tốt nhất** để giữ một lỗ hổng “edit rồi mới check”:

1. Transaction mở trước pre-authorization, tăng phạm vi transaction và ảnh hưởng hiệu năng/locks.
2. `@Transactional(noRollbackFor = AccessDeniedException.class)`, rollback configuration khác, lỗi bị catch, hoặc inner `REQUIRES_NEW` có thể khiến DB vẫn commit.
3. Email, message đã publish ra ngoài transaction hoặc remote API call **không rollback được**.
4. Có thể có nhiều proxies, advisors bổ sung hoặc một số method không được transaction intercept do gọi sai đường.
5. Chỉ một cấu hình global order thay đổi không chứng minh policy theo owner được áp dụng **trước side effect**.
6. Nếu trả về object có lazy association, transaction outer có thể giúp evaluation, nhưng cũng làm thay đổi thời điểm lazy load và performance; cần test rõ.

**Khuyến nghị chính:** với lệnh ghi, hãy kiểm tra quyền trước mutation; dùng transaction order như **tùy chọn kỹ thuật được đo/test** cho các trường hợp cần rollback khi post checks thất bại, không dùng nó để hợp thức hóa viết mã ghi dữ liệu trước khi kiểm tra quyền.

## 11. Tự gọi method trong cùng bean: proxy không chạy

Spring method security và transaction thường dùng AOP proxies. Một call từ bên ngoài vào public bean method có thể được intercept; một call nội bộ cùng đối tượng qua `this.method()` thường **không đi qua proxy**.

~~~java
@Service
public class ExampleService {

    public void entry(Long id) {
        this.protectedAction(id); // BỎ QUA proxy interception phổ biến.
    }

    @PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
    @Transactional
    public void protectedAction(Long id) {
        // Mutating operation...
    }
}
~~~

Đây là **mảnh minh họa**, không độc lập: cần import `@Service`, `@PreAuthorize`, `@Transactional`, method body thực tế. Nếu Spring dùng proxy-based AOP, `this.protectedAction` không kích hoạt advice cho lần gọi nội bộ đó. Kết quả có thể là **bỏ qua cả method security lẫn transaction** dù annotations đặt đúng trên method.

Cách tổ chức an toàn hơn:

- Để caller khác bean gọi một public service method qua Spring bean/proxy.
- Phân tách logic nội bộ không annotated vào method riêng (trong cùng bean) nhưng chỉ expose **một entrypoint đã được bảo vệ**.
- Nếu có nested operations cần transaction khác, tạo bean riêng với hợp đồng rõ và gọi qua bean đã được quản lý; đừng dùng self-injection như cách chữa mặc định mà không hiểu proxy.
- Không dựa vào private/final methods hoặc direct object construction để được interceptor bảo vệ; sự hỗ trợ tùy proxy type, visibility và version. Test việc advice có chạy thật.

### Hai transaction không tự gom lại vì cùng request

Một service method gọi một bean có `@Transactional(propagation = Propagation.REQUIRES_NEW)` sẽ có thể tạo transaction độc lập. Nếu inner method đã commit, outer transaction rollback khi `@PostAuthorize` từ chối **không hoàn tác inner commit**. Những thao tác như gửi email, push notification, RPC hoặc gọi gateway thanh toán còn nằm ngoài transaction database.

Với side effect quan trọng, ưu tiên: **authorize trước**, thay đổi DB có điều kiện, **transactional outbox** khi phát message sau commit, và idempotency/compensation cho external systems. Đừng mặc định JPA transaction là “undo everything”.

## 12. Lỗi thường gặp và cách phân tích

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| POST trả 403 nhưng DB đã đổi | `@PostAuthorize` nằm ngoài transaction advice; commit trước denial. | Đọc DB sau request bằng transaction mới; kiểm tra advisor order. |
| `@PreAuthorize` không chặn | Chưa bật `@EnableMethodSecurity`, self-invocation, gọi qua object tự new hoặc method không được proxy intercept. | Test service bean qua caller khác; kiểm tra proxy. |
| Có `@Transactional` nhưng rollback không xảy ra | Exception ngoài tx/đã commit, bị catch, rollback rules thay đổi, hoặc transaction khác đã commit. | Kiểm tra tx boundaries và rule rollback. |
| Thay đổi thứ tự annotation không giải quyết | Thứ tự annotation trong source không quyết định advice order. | Kiểm tra advisor orders, proxy chain. |
| Chỉ unit test mock repository thấy an toàn | Mock không có flush/commit thật. | Dùng H2/Testcontainers và assert database state sau HTTP request. |
| Test bị ảnh hưởng bởi transaction của test | Test `@Transactional` bao ngoài khiến commit deferred. | Tránh `@Transactional` tại test cần quan sát commit, hoặc tách execution thread/transaction. |
| GET bị denied sau @PostAuthorize | Result owner khác authentication. | Với read method, kiểm tra dữ liệu/SpEL và quyền theo tài nguyên. |
| POST thiếu CSRF trả 403 | `CsrfFilter` từ chối trước method. | Dùng `csrf()` để test method security riêng. |
| User có DOCUMENT_WRITE nhưng sửa record tenant khác | Chỉ kiểm tra quyền chức năng, chưa check owner/tenant. | Kiểm tra object state trong transaction, conditional update. |
| Một service ghi DB rồi gửi email trước denial | External side effect không rollback. | Di chuyển authorization lên trước; dùng outbox và idempotency. |
| Thêm transaction order 0 làm hệ thống chậm | Transaction mở sớm hơn quanh security checks. | Đo lock/time/latency; cân nhắc thiết kế lại call graph. |
| Đổi owner trong race sau pre-check | TOCTOU giữa check và update. | Lock, version, conditional update và tenant policy. |
| `@PostAuthorize` ném LazyInitializationException | Expression đọc lazy association sau tx kết thúc. | Fetch/DTO/tx boundary phù hợp, không tắt security. |

### Khi debug, xác nhận năm câu hỏi

1. **Method security đã thật sự bật chưa?** Có `@EnableMethodSecurity`, policy annotation có được intercept không?
2. **Call có đi qua proxy?** Controller → Spring bean service hay `this.method()`/`new`?
3. **Advisor order thực tế?** Transaction advice bao ngoài hay bên trong `@PostAuthorize`?
4. **Exception đi qua transaction boundary nào?** Lỗi RuntimeException có được ném trước commit, được catch ở đâu, có nested/REQUIRES_NEW không?
5. **DB có thực sự giữ thay đổi sau request?** Kiểm tra trong một transaction mới thay vì suy từ HTTP status hoặc SQL flush log.

Nếu chỉ thay thứ tự annotations rồi test một trường hợp HTTP 403, bạn chưa trả lời được câu hỏi 3–5.

## 13. Java 17 độc lập: mô phỏng advisor ngoài/trong và kết quả rollback

Chương trình sau chỉ **mô phỏng thứ tự**; không sử dụng Spring, JDBC hoặc Spring AOP. Mục đích là nhìn rõ điều kiện đơn giản “post-check chạy sau commit” so với “post-check chạy bên trong transaction”.

Tạo `TransactionOrderDemo.java`:

~~~java
public final class TransactionOrderDemo {

    private static final class State {
        String persisted = "original";
    }

    private static void transactionInnerThenDeny(State db) {
        System.out.println("CASE 1: transaction inner");
        System.out.println("BEGIN");
        db.persisted = "changed";
        System.out.println("COMMIT");
        // Bây giờ post-check từ chối, đã quá muộn để rollback.
        System.out.println("DENY after commit");
        System.out.println("db=" + db.persisted);
    }

    private static void transactionOuterAndDeny(State db) {
        System.out.println("CASE 2: transaction outer");
        System.out.println("BEGIN");
        String before = db.persisted;
        db.persisted = "changed";
        System.out.println("DENY before commit");
        // Mô phỏng ROLLBACK trong transaction bao ngoài post-check.
        db.persisted = before;
        System.out.println("ROLLBACK");
        System.out.println("db=" + db.persisted);
    }

    public static void main(String[] args) {
        transactionInnerThenDeny(new State());
        transactionOuterAndDeny(new State());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac TransactionOrderDemo.java
java TransactionOrderDemo
~~~

Stdout **chính xác**:

~~~text
CASE 1: transaction inner
BEGIN
COMMIT
DENY after commit
db=changed
CASE 2: transaction outer
BEGIN
DENY before commit
ROLLBACK
db=original
~~~

**Không hiểu nhầm:** Chương trình này chỉ thao tác một field trong bộ nhớ để mô phỏng transaction, không có DB engine, JPA dirty checking hay Spring `@PostAuthorize`. Nó không chứng minh hành vi advisor của một Spring Boot version cụ thể. Bài test MockMvc + H2 ở mục 9 mới trực tiếp kiểm tra **quy tắc chạy cùng Spring Security / JPA** của demo.

## 14. Nếu cần kiểm soát quyền phụ thuộc returnObject thì làm sao cho an toàn?

Có những trường hợp trước truy vấn không thể biết owner của object. Một số lựa chọn hợp lý:

**A. Read-only: query rồi kiểm tra sau, tránh side effect.**

~~~java
@Transactional(readOnly = true)
@PostAuthorize("returnObject.ownerName == authentication.name")
public DocumentEntity readOne(Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Phù hợp khi bạn muốn chặn trả object cho caller. Cần đảm bảo logic đọc không gửi dữ liệu đi nơi khác trước khi post-check và xử lý lazy loading đúng.

**B. Write: nạp object + kiểm tra trước mutation trong cùng transaction.**

~~~java
@Transactional
@PreAuthorize("hasAuthority('DOCUMENT_WRITE')")
public void updateOne(Long id, String text) {
    var doc = repository.findById(id).orElseThrow();
    if (!doc.getOwnerName().equals(
            SecurityContextHolder.getContext()
                .getAuthentication().getName())) {
        throw new AccessDeniedException("Forbidden");
    }
    doc.setBody(text);
}
~~~

Đây là mảnh code, với `repository` và imports từ service đã định nghĩa. Nó không dùng client-supplied owner. Với transaction isolation không đủ để đảm bảo owner không đổi đồng thời, thêm optimistic lock hoặc conditional update.

**C. Database conditional UPDATE theo user/tenant.**

Ý tưởng câu SQL:

~~~sql
UPDATE documents
   SET body = :new_body
 WHERE id = :id
   AND owner_name = :authenticated_actor;
~~~

Giá trị `:authenticated_actor` phải lấy từ authentication đã xác minh phía server, không lấy từ query/body của client. Nếu affected rows = 0, có thể xem như không tìm thấy/không được phép theo response policy tránh leak existence. Đây là ý tưởng SQL, syntax named parameter phụ thuộc JDBC/JPA adapter; trong ứng dụng thật cần transaction/repository, version/concurrency, tenant và data validation.

**D. Authorization policy bean dùng @PreAuthorize, rồi xác minh thêm khi dùng.**

~~~java
@PreAuthorize(
    "hasAuthority('DOCUMENT_WRITE') and " +
    "@documentPolicy.mayEdit(authentication, #id)")
@Transactional
public void edit(Long id, String text) {
    // Query, kiểm tra state/tenant một lần nữa nếu cần,
    // rồi cập nhật...
}
~~~

Đây là mảnh phương thức minh họa, `documentPolicy` phải là Spring bean tin cậy. Pre-check có thể diễn ra **trước transaction** của method theo mặc định và tạo TOCTOU; không dựa vào pre-check DB ngoài transaction như bằng chứng vĩnh viễn khi quyền/owner có thể đổi.

**E. Nếu vẫn cần @PostAuthorize cho mutation?**

Chỉ khi có lý do thiết kế được review nghiêm ngặt, cần kiểm chứng advisor nesting, transaction rollback, exception propagation, side effects, queuing, retries, các giao dịch con và coverage test. Hãy xem đây là **ngoại lệ khó chứng minh an toàn**, không phải lựa chọn mặc định cho endpoint ghi.

## 15. HTTP 403, AccessDeniedException và transaction event là ba tín hiệu khác nhau

Trong Spring Security Servlet:

~~~text
Controller gọi service
  |
  v
Method security denial
  |
  v
AccessDeniedException / AuthorizationDeniedException
  |
  v
ExceptionTranslationFilter / AccessDeniedHandler
  |
  v
HTTP 403 (thường với user đã xác thực)
~~~

Trong đường này, việc HTTP response là 403 xảy ra **sau** hoặc **trong** call stack của service tùy thời điểm exception. Nếu transaction đã commit, ExceptionTranslationFilter không có chức năng “undo JPA transaction”.

Mặt khác:

~~~text
HTTP POST thiếu CSRF
  |
  v
CsrfFilter -> 403
  |
  x Controller không chạy
  x @PreAuthorize/@PostAuthorize service không được thực thi
  x Không phát sinh mutation của service này
~~~

Vậy chỉ nhìn access log thấy 403 không nói rằng “method security đã hoạt động” hoặc “transaction đã rollback”. Cần tách **authentication failure**, **CSRF failure**, **authorization denied**, **transaction commit/rollback** và **business audit**. Các hệ thống observability có thể dùng event, metrics, trace và database audit thích hợp để kết nối, không log raw token/password/cookie.

### Kiểm thử phủ nhận kết luận sai

Một bộ security test tốt có cả:

- **Positive write:** đúng user, đúng quyền, đúng owner → 200, DB đổi.
- **Negative write trước method:** thiếu quyền tổng quát → 403, DB không đổi.
- **Negative write trong transaction:** có quyền chung nhưng không phải owner → 403, DB không đổi.
- **Negative post-only intentionally unsafe:** sau khi ghi bị deny → 403, DB **đã đổi** (để phát hiện anti-pattern).
- **Negative CSRF:** POST không token → 403, service không chạy.
- **Read-only post-check:** user không phải owner → 403, không có mutation.
- **Race/concurrency:** document ownership/tenant/version thay đổi khi hai request cạnh tranh.
- **External side effect:** email/message/payment không được phát cho request bị từ chối.

Khi pipeline đã sửa bỏ phương thức unsafe, **không** giữ production test kỳ vọng 403 đi kèm commit như hành vi mong muốn. Giữ nó như một test giáo dục/anti-pattern trong module riêng, hoặc thay bằng regression test khẳng định **từ chối không có side effect**.

## 16. Câu hỏi tự kiểm tra

**Q1. Thứ tự annotation trong file có quyết định @Transactional chạy trước @PostAuthorize không?** Không. Spring AOP advisor order/proxy chain mới quyết định.

**Q2. Vì sao @PostAuthorize nguy hiểm cho method ghi?** Vì check chạy sau method body và có thể sau khi transaction bên trong đã commit; 403 không thể undo commit.

**Q3. @PreAuthorize giải quyết được việc gì?** Nó chặn caller thiếu quyền trước method. Với quyền theo object, vẫn cần check owner/tenant tin cậy và xử lý concurrency khi ghi.

**Q4. @Transactional rollback khi HTTP trả 403 hay khi exception đi qua transaction interceptor?** Khi transaction interceptor nhận failure phù hợp rollback rules **trước khi commit**; HTTP status tự nó không điều khiển rollback.

**Q5. Nếu chuyển transaction advisor ra ngoài @PostAuthorize, có chắc mọi side effect được rollback?** Không. Chỉ transaction resources nằm trong phạm vi phù hợp mới được rollback; REQUIRES_NEW, email/RPC, exception rules và interception bypass vẫn có thể làm side effect tồn tại.

**Q6. Có nên dùng @PostAuthorize cho read-only query không?** Có thể có giá trị để hạn chế object trả về, nếu query không gây side effect và xử lý lazy loading đúng. Với dữ liệu rất nhạy cảm/lớn, tốt hơn lọc quyền tại truy vấn.

**Q7. Một test POST nhận 403 có chứng minh @PreAuthorize từ chối không?** Không. CsrfFilter có thể đã trả 403 trước khi service chạy. Với CSRF bật, phải gửi token hợp lệ để test quyền.

**Q8. Vì sao test không nên gắn @Transactional khi muốn kiểm tra commit thật?** Nó có thể làm test và service dùng một transaction khác với request thực, trì hoãn commit và che kết quả đã persist.

**Q9. Transaction đã flush có chắc commit chưa?** Không. Flush đẩy SQL trong transaction; rollback vẫn có thể hủy thay đổi nếu chưa commit.

**Q10. Lời gọi `this.securedMethod()` trong cùng service có chạy method-security proxy không?** Với Spring proxy-based AOP thường **không**. Dùng caller qua Spring bean/proxy hoặc refactor entrypoint.

**Q11. Nếu quyền theo document có thể thay đổi trong lúc request chạy thì cần gì?** Xác minh gần lúc mutation, dùng transaction và cơ chế concurrency (optimistic lock, pessimistic lock, conditional UPDATE) theo yêu cầu hệ thống.

**Q12. Nếu sau denial database không đổi thì app chắc an toàn chưa?** Chưa. Có thể đã gửi email, message, RPC hoặc ghi vào giao dịch độc lập; phải kiểm tra toàn bộ side effects.

## 17. Checklist cho code review và phát hành

- [ ] `@EnableMethodSecurity` đã bật, các method cần bảo vệ thực sự được Spring proxy intercept.
- [ ] Có test chứng minh user thiếu quyền không chạy mutation.
- [ ] Phân biệt `@PreAuthorize` (before) và `@PostAuthorize` (after).
- [ ] Không dùng `@PostAuthorize` làm rào chắn chính cho method có side effect.
- [ ] Nếu cần check owner/tenant, dùng dữ liệu server-side, không tin client-supplied owner.
- [ ] Check quyền được thực hiện **trước** database update, message publish, email hoặc remote call.
- [ ] Với thay đổi trạng thái cạnh tranh, dùng locking/version/conditional UPDATE phù hợp.
- [ ] Đã hiểu advisor ordering thực tế của method security và `@Transactional` ở version đang dùng.
- [ ] Không thay thứ tự annotations rồi coi là đã sửa nesting.
- [ ] Không gắn `@EnableTransactionManagement(order=0)` tùy tiện mà chưa đánh giá ảnh hưởng tới toàn ứng dụng.
- [ ] Các rollback rules không loại trừ access denial một cách ngoài ý muốn.
- [ ] Kiểm tra propagation `REQUIRES_NEW` hoặc nested transactions có commit trước khi bị deny không.
- [ ] Tránh self-invocation, private method, object tự `new` hoặc proxy bypass làm mất security advice.
- [ ] Không nhận “403” là bằng chứng transaction rollback; test database state từ transaction mới.
- [ ] POST tests có CSRF token khi cần đánh giá method security, và có test thiếu token riêng.
- [ ] Không gắn `@Transactional` bừa bãi lên test sẽ che mốc commit thật.
- [ ] Có kiểm thử ownership, tenant isolation, idempotency và external side effects theo threat model.
- [ ] Có audit/metrics phân biệt authorization denial, transaction rollback và side-effect execution.
- [ ] Không log raw credentials, token, session cookie, payload nhạy cảm hoặc dữ liệu của user bị từ chối.

**Kết luận:** `@Transactional` và `@PreAuthorize`/`@PostAuthorize` đều là **AOP advices**, không tự động phối hợp thành “bị từ chối thì chắc chắn rollback”. Với advisor order mặc định thường gặp, `@PostAuthorize` có thể chạy **sau khi transaction đã commit**. Hãy dùng **@PreAuthorize và kiểm tra đối tượng trước khi ghi** làm rào chắn chính, giữ `@PostAuthorize` chủ yếu cho việc kiểm soát **kết quả đọc**, và xác minh an toàn bằng kiểm thử **HTTP + transaction + trạng thái database + side effects** chứ không chỉ một status 403.
