# securedEnabled, jsr250Enabled và phạm vi annotation được kích hoạt

## 1. Vì sao một phương thức có annotation mà vẫn chạy được?

Trong Spring Security, đặt một annotation bảo mật lên service **chưa đủ** để kết luận phương thức đó đã được kiểm tra quyền. Annotation chỉ có hiệu lực khi **method security được bật**, loại annotation ấy **được cấu hình kích hoạt**, lời gọi **đi qua cơ chế interception** và ngữ cảnh xác thực/chính sách phù hợp.

Ví dụ ứng dụng có hai phương thức:

```java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView read(long id) { ... }

@Secured("ROLE_ADMIN")
public void rebuildAllIndexes() { ... }
```

Nếu ứng dụng chỉ khai báo `@EnableMethodSecurity` theo mặc định:

- `@PreAuthorize` được kích hoạt và có thể chặn người thiếu `invoice:read`.
- `@Secured` **chưa được kích hoạt**: riêng annotation này không tạo ra kiểm tra method security.
- Nếu phương thức `rebuildAllIndexes()` được gọi qua một đường không có chốt khác, nó có thể thực thi dù người dùng không phải admin.

Tương tự, nếu service gắn `@RolesAllowed("ADMIN")` hoặc `@DenyAll` nhưng `jsr250Enabled=false`, những annotation JSR-250 không được interceptor tương ứng xử lý. Đây là lỗi đặc biệt nguy hiểm với mã được chuyển từ một hệ thống Java EE/Jakarta EE hoặc một cấu hình Spring Security cũ.

**Bài học cốt lõi:** `securedEnabled` và `jsr250Enabled` không phải các quyền được cấp cho người dùng. Chúng là **công tắc bật nhóm cơ chế kiểm tra annotation** trong Spring Security. Tắt một công tắc có nghĩa là *loại kiểm tra tương ứng không được đăng ký*, chứ không có nghĩa phương thức trở thành “mặc định từ chối”.

## 2. Bảng chính xác ba nhóm cờ của @EnableMethodSecurity

Với `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity` trên Spring Security 6.5, các giá trị mặc định được JavaDoc xác nhận:

| Cờ | Mặc định | Nhóm annotation được kích hoạt khi true | Tác dụng khi false |
| --- | --- | --- | --- |
| `prePostEnabled` | `true` | `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter` | Không đăng ký các interceptor chuẩn của nhóm pre/post |
| `securedEnabled` | `false` | `@Secured` | Không đăng ký interceptor chuẩn cho `@Secured` |
| `jsr250Enabled` | `false` | `@RolesAllowed`, `@PermitAll`, `@DenyAll` | Không đăng ký interceptor chuẩn cho nhóm JSR-250 |

Hai biến quan trọng khác:

- `mode` mặc định là `AdviceMode.PROXY`: method security dùng mô hình proxy của Spring AOP, nên ranh giới lời gọi rất quan trọng.
- `proxyTargetClass` mặc định là `false`: chọn cách proxy theo quy tắc của Spring; bật CGLIB class proxy không tự giải quyết mọi lời gọi nội bộ.

Cấu hình phổ biến cho dự án mới:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Tương đương về ba cờ chính với:

```java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = false,
    jsr250Enabled = false
)
public class MethodSecurityConfig {
}
```

Nếu dự án có cả `@Secured` và JSR-250:

```java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfig {
}
```

**Phân biệt:** Spring Boot Starter Security **không tự động bật method security chỉ vì dependency đã có mặt**. Phải chủ động khai báo `@EnableMethodSecurity` (hoặc phương thức kích hoạt tương đương được hỗ trợ). Nếu ứng dụng không kích hoạt method security, không nên coi bất kỳ annotation method authorization nào là chốt bảo vệ mặc định.

### 2.1. Bốn cấu hình cần dự đoán được

| Khai báo | @PreAuthorize | @Secured | @RolesAllowed/@DenyAll |
| --- | --- | --- | --- |
| `@EnableMethodSecurity` | Hoạt động | Chưa bật | Chưa bật |
| `@EnableMethodSecurity(securedEnabled = true)` | Hoạt động | Hoạt động | Chưa bật |
| `@EnableMethodSecurity(jsr250Enabled = true)` | Hoạt động | Chưa bật | Hoạt động |
| `@EnableMethodSecurity(securedEnabled = true, jsr250Enabled = true)` | Hoạt động | Hoạt động | Hoạt động |
| `@EnableMethodSecurity(prePostEnabled = false, securedEnabled = true)` | Không đăng ký interceptor pre/post chuẩn | Hoạt động | Chưa bật |
| Không bật method security | Không có chốt method tương ứng mặc định | Không có | Không có |

Trong cột “chưa bật”, điều đó **không đồng nghĩa request chắc chắn được phép**: HTTP security, một annotation thuộc nhóm khác đang bật, chính sách dữ liệu hoặc kiểm tra thủ công vẫn có thể chặn. Nhưng **chính annotation chưa bật sẽ không chặn**.

### 2.2. Vì sao default pre/post được chọn?

`@PreAuthorize` có biểu thức SpEL, có thể kiểm tra permission, vai trò, tham số phương thức và bean chính sách. Nó linh hoạt hơn các annotation role-based cổ điển. Spring Security khuyến nghị `@PreAuthorize` cho phần lớn use case mới; `@Secured` và JSR-250 hữu ích khi tương thích mã cũ hoặc sử dụng quy ước annotation của hệ thống.

Việc bật cả ba nhóm có thể hợp lý trong migration, nhưng làm tăng số kiểu chính sách cần review. Nhóm nào không còn sử dụng nên được loại khỏi code và test theo lộ trình; **không tắt công tắc khi chưa tìm hết annotation đang phụ thuộc nó**.

## 3. Method security thực sự hoạt động bằng cách nào?

Trong cấu hình Servlet/ứng dụng Spring thông dụng, `@EnableMethodSecurity` đăng ký các advisor/interceptor của Spring AOP. Khi một lời gọi tới **Spring-managed bean** đi qua proxy/advice, interceptor phù hợp có thể lấy `Authentication` từ `SecurityContextHolder`, đánh giá chính sách và chỉ gọi phương thức thật nếu được phép.

```text
Controller / Service / Job
          |
          v
Spring-managed bean proxy
          |
          +-- Có advisor cho annotation đang dùng?
          |        |
          |       Không -> không có chốt method của nhóm đó
          |        |
          |        v
          |    Trước phương thức:
          |      @PreAuthorize / @Secured / @RolesAllowed /
          |      @DenyAll / @PermitAll
          |        |
          |        +-- DENY -> không chạy thân method
          |        |
          |        v
          |     Thực thi method
          |        |
          |        v
          |     Sau phương thức:
          |      @PostAuthorize / @PostFilter
          |
          v
     Kết quả hoặc lỗi
```

Sơ đồ trên là **mô hình khái niệm**, không phải cam kết thứ tự chính xác giữa mọi interceptor tùy biến. Trong Spring Security, nhóm pre/post và nhóm Secured/JSR-250 được xử lý bởi các `AuthorizationManager`/interceptor tương ứng.

### 3.1. Bản đồ interceptor theo nhóm

| Annotation | Interceptor/manager điển hình | Thời điểm |
| --- | --- | --- |
| `@PreAuthorize` | `AuthorizationManagerBeforeMethodInterceptor.preAuthorize()`, `PreAuthorizeAuthorizationManager` | Trước khi method chạy |
| `@PostAuthorize` | `AuthorizationManagerAfterMethodInterceptor.postAuthorize()`, `PostAuthorizeAuthorizationManager` | Sau khi method chạy |
| `@PreFilter` | Interceptor pre-filter của method security | Trước khi method xử lý tập đầu vào |
| `@PostFilter` | Interceptor post-filter của method security | Sau khi method trả tập kết quả |
| `@Secured` | `AuthorizationManagerBeforeMethodInterceptor.secured()`, `SecuredAuthorizationManager` | Trước method |
| `@RolesAllowed`, `@PermitAll`, `@DenyAll` | `AuthorizationManagerBeforeMethodInterceptor.jsr250()`, `Jsr250AuthorizationManager` | Trước method |

Khi nhóm bị tắt, những interceptor **chuẩn** tương ứng không được đăng ký bởi công tắc đó. Nếu ứng dụng tự tạo advisor hoặc AspectJ advice riêng, phải xem cấu hình thực tế; không nên suy ra toàn bộ hệ thống không có kiểm tra khác.

### 3.2. “Annotation được kích hoạt” có phạm vi nào?

Cờ bật theo **ApplicationContext/configuration method security**, không phải theo từng class hay mỗi HTTP route. Một service không tự bật `@Secured` chỉ vì import class annotation. Một controller khác cũng không được bật riêng JSR-250 nếu không có cơ chế cấu hình tương ứng trong ứng dụng.

Lời gọi có được chặn hay không còn phụ thuộc:

1. Class/method có annotation thuộc nhóm được bật.
2. Bean nằm dưới sự quản lý Spring và có advice phù hợp.
3. Lời gọi thực sự đi qua proxy/weaving.
4. Có `Authentication`/ngữ cảnh quyền phù hợp hoặc manager xử lý thiếu danh tính theo chính sách.
5. Không có cơ chế khác cố ý thay thế/tắt advisor.
6. Cách kế thừa annotation giữa interface, class và method được framework giải quyết không nhập nhằng.

Công tắc bật **khả năng áp dụng** nhóm annotation, không phải lời hứa mọi method trong app đều được bảo vệ. Một public method không có annotation và không có pointcut/chốt khác vẫn có thể được gọi bình thường.

## 4. @Secured: kiểm tra quyền kiểu cổ điển

### 4.1. Import và cú pháp

`@Secured` thuộc Spring Security:

```java
import org.springframework.security.access.annotation.Secured;

@Secured("ROLE_ADMIN")
public void rebuildIndexes() {
    // Chỉ role admin theo chính sách.
}
```

Muốn annotation ấy hoạt động với `@EnableMethodSecurity`:

```java
@Configuration
@EnableMethodSecurity(securedEnabled = true)
class SecuredConfiguration {
}
```

Từ khóa `securedEnabled` **không có nghĩa** “mọi service được bảo vệ”; nó chỉ kích hoạt interceptor dành cho `@Secured`.

### 4.2. Một hoặc nhiều authority

Ví dụ:

```java
@Secured({"ROLE_ADMIN", "ROLE_SUPPORT"})
public String readSupportOverview() {
    return "support-overview";
}
```

Các giá trị trong `@Secured` thường được đánh giá theo kiểu **một trong các authority được liệt kê là đủ** (OR), không phải người dùng phải có tất cả. Người dùng có `ROLE_SUPPORT` được phép dù không có `ROLE_ADMIN`, khi không bị chốt khác từ chối.

Cần lưu ý:

- `@Secured` nhận **tên authority dạng chuỗi**, không phải biểu thức SpEL.
- Viết `@Secured("hasRole('ADMIN')")` là sai ý định: nó không chạy biểu thức `hasRole`.
- Theo convention Spring Security, `ROLE_ADMIN` khác với chuỗi `ADMIN`; không dự đoán role prefix nếu dự án tùy biến.
- `@Secured` không tự kiểm tra `invoice.tenantId` hay chủ sở hữu object. Nó thường phù hợp rule quyền chức năng đơn giản.
- Nếu có role hierarchy, cần xác minh manager dành cho `@Secured` được cấu hình với graph tương ứng theo phiên bản; đừng chỉ kiểm tra bean hierarchy tồn tại.

### 4.3. Vì sao có @Secured vẫn có thể “không tác dụng”?

Những nguyên nhân thường gặp:

1. `securedEnabled=false` (mặc định).
2. Không bật `@EnableMethodSecurity`.
3. Gọi phương thức qua `this.method()` bên trong cùng bean, không đi qua Spring AOP proxy.
4. Tự tạo object với `new` thay vì dùng Spring bean.
5. Annotation đặt lên private/final method hoặc loại proxy không thể intercept đúng.
6. Có rule HTTP khác cho phép hoặc từ chối, khiến test không thực sự chứng minh method security.
7. Principal mang `ROLE_USER` trong khi annotation cần `ROLE_ADMIN`.
8. Cấu hình class/interface annotation bị ghi đè hoặc nhập nhằng; cần test theo method thực được gọi.

Phân biệt lỗi **annotation không kích hoạt** với lỗi **annotation đã kích hoạt nhưng deny đúng vì thiếu quyền**. Hai tình huống đều cần cách sửa khác nhau.

## 5. JSR-250: @RolesAllowed, @PermitAll và @DenyAll

### 5.1. Cần bật cả nhóm bằng jsr250Enabled

Với Spring Boot 3.x / Spring Security 6.x dựa trên Jakarta:

```java
import jakarta.annotation.security.RolesAllowed;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.DenyAll;
```

Bật nhóm:

```java
@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
class Jsr250Configuration {
}
```

Khi đó Spring Security đăng ký interceptor cho cả ba annotation JSR-250. **Không có ba công tắc riêng** theo kiểu `rolesAllowedEnabled`, `permitAllEnabled`, `denyAllEnabled` trong `@EnableMethodSecurity`. Cờ chung là `jsr250Enabled`.

Với dự án Java EE/Spring Security 5 cũ có thể gặp import `javax.annotation.security.*`. Trong hệ Spring Boot 3/Jakarta, dùng `jakarta.annotation.security.*` và dependency phù hợp; **đừng trộn tên package khác đời** rồi đoán rằng annotation sẽ được Spring nhận biết.

### 5.2. @RolesAllowed

```java
@RolesAllowed({"ADMIN", "MANAGER"})
public List<String> listTeamMetrics() {
    return List.of("team:summary");
}
```

Ý nghĩa:

- Một trong hai role được liệt kê có thể đáp ứng rule (OR).
- Với tiền tố mặc định `ROLE_` của `Jsr250AuthorizationManager`, `"ADMIN"` tương ứng `ROLE_ADMIN`, `"MANAGER"` tương ứng `ROLE_MANAGER`.
- Nếu ứng dụng thay role prefix, phải kiểm chứng tên `GrantedAuthority` thật và cấu hình manager. Không đoán prefix theo một tutorial khác phiên bản.
- `@RolesAllowed` không thể tự viết điều kiện owner, tenant hoặc tham số method như một biểu thức SpEL.

Ví dụ người dùng có:

```text
Authentication authorities = [ROLE_MANAGER]
@RolesAllowed({"ADMIN", "MANAGER"})
=> Được phép ở chốt JSR-250 này nếu đã kích hoạt và không có chốt khác deny.
```

Nhưng nếu `jsr250Enabled=false`, câu chuyện không phải là “bị deny vì thiếu role”; **chốt JSR-250 không được đăng ký**, và hành vi còn lại do những cơ chế khác quyết định.

### 5.3. @PermitAll

```java
@PermitAll
public String publicCatalogBanner() {
    return "Welcome";
}
```

Khi `jsr250Enabled=true` và lời gọi đi qua interceptor, `@PermitAll` thể hiện **cho phép tại kiểm tra JSR-250 của method đó**. Nó **không** có nghĩa:

- Tự chuyển tất cả HTTP `/public/**` sang `permitAll()`.
- Bỏ qua một `@PreAuthorize` khác đang hoạt động.
- Bỏ qua CSRF, authentication filters hay authorization của URL.
- Tự biến dữ liệu nhạy cảm được truy vấn trong service thành công khai.
- Cho phép gọi qua bất kỳ route nào trong mọi `SecurityFilterChain`.

Đặc biệt trong ứng dụng web, nếu đường dẫn HTTP bị `denyAll()` thì lời gọi sẽ không tới method, dù method có `@PermitAll`.

Nếu `jsr250Enabled=false`, `@PermitAll` không được xử lý bởi interceptor JSR-250. Khi đó việc method chạy hay không có thể do các lớp bảo vệ khác; không nên ghi nhận đây là một lời cho phép có hiệu lực của JSR-250.

### 5.4. @DenyAll

```java
@DenyAll
public void permanentlyDisabledOperation() {
    throw new IllegalStateException("Should not be invoked");
}
```

Khi JSR-250 được bật và lời gọi đi qua proxy, `@DenyAll` từ chối lời gọi tại interceptor này, kể cả người dùng có `ROLE_ADMIN`. Nó phù hợp để khóa một operation hoặc xác định điểm chưa được phép gọi, nhưng:

- Nếu `jsr250Enabled=false`, **annotation không còn là chốt chặn**; method có thể chạy nếu không có kiểm soát khác.
- Nếu method bị gọi nội bộ qua self-invocation không qua proxy, chốt có thể bị bỏ qua.
- Không nên xem `@DenyAll` là lựa chọn thay thế cho việc loại bỏ hoàn toàn một tính năng nguy hiểm hoặc đóng endpoint ở HTTP.

**Bài kiểm thử quan trọng nhất khi bật/tắt JSR-250:** method có `@DenyAll` phải từ chối khi cờ bật; một bài kiểm thử chỉ dùng user không có quyền trên route HTTP không chứng minh điều đó.

### 5.5. Tránh đặt annotation JSR-250 mâu thuẫn cùng vị trí

Đừng gắn đồng thời `@PermitAll` và `@DenyAll` lên cùng một method rồi mong framework tự đoán ý định ưu tiên. Không gắn `@RolesAllowed` khác nhau lên nhiều interface cha để “hợp quyền” một cách ngầm định. Giữ một nguồn chính sách rõ ràng cho cùng một loại annotation và test hành vi kế thừa.

## 6. Pre/Post annotations và cờ prePostEnabled

### 6.1. @PreAuthorize: mạnh hơn vì biết ngữ cảnh method

```java
@PreAuthorize("hasAuthority('invoice:read')")
public InvoiceView readInvoice(long invoiceId) {
    // Có thể tiếp tục kiểm tra tenant/owner ở repository.
}
```

`@PreAuthorize` dùng biểu thức quyền trước khi method chạy. Ngoài authority, có thể tham chiếu tham số hoặc policy bean để phân quyền theo đối tượng, ví dụ:

```java
@PreAuthorize(
    "hasAuthority('invoice:read') and @invoicePolicy.canRead(authentication, #invoiceId)"
)
public InvoiceView readInvoice(long invoiceId) {
    // Chỉ trả dữ liệu đã được kiểm chứng theo tenant.
}
```

Đây là **fragment tích hợp**, giả sử bean `invoicePolicy` đã được định nghĩa và method `canRead(...)` có hợp đồng/hiệu năng/bảo mật phù hợp. Việc sử dụng tên tham số trong biểu thức phụ thuộc khả năng phát hiện tên tham số khi biên dịch; có thể cần `-parameters` hoặc annotation chỉ tên.

Nếu `prePostEnabled=false`, cả hai đoạn trên **không được interceptor pre/post mặc định thực thi**. Bật `securedEnabled=true` không làm `@PreAuthorize` sống lại.

### 6.2. @PostAuthorize: kết quả trả về cũng tham gia quyết định

```java
@PostAuthorize("returnObject.owner == authentication.name")
public InvoiceView findInvoice(long id) {
    return repository.loadView(id);
}
```

`@PostAuthorize` có thể kiểm tra dữ liệu **sau khi method trả kết quả**. Chỉ sử dụng khi việc gọi method trước khi kiểm tra là phù hợp: dữ liệu có thể đã được đọc hoặc thao tác bên ngoài đã xảy ra.

**Không dùng riêng `@PostAuthorize` để bảo vệ một lệnh chuyển tiền, xóa bản ghi hoặc gửi email**: đến lúc quyết định từ chối, side effect có thể đã được thực thi. Với hành động thay đổi trạng thái, dùng kiểm tra trước cùng transaction/điều kiện dữ liệu phù hợp.

### 6.3. @PreFilter và @PostFilter

```java
@PreFilter("filterObject.owner == authentication.name")
public void submitOwnedInvoices(List<InvoiceCommand> commands) {
    // Các phần tử không phù hợp có thể bị lọc trước.
}
```

```java
@PostFilter("filterObject.owner == authentication.name")
public List<InvoiceView> listVisibleInvoices() {
    return repository.findAllVisibleCandidates();
}
```

Đây là **mã tích hợp mang tính ý tưởng**, cần kiểu dữ liệu thật, collection được hỗ trợ và cấu hình Spring Security phù hợp. Cả hai annotation chỉ được xử lý khi `prePostEnabled=true`.

Với dữ liệu lớn hoặc nhiều tenant, lọc tập ở memory sau khi truy vấn **không nên là chốt bảo vệ dữ liệu duy nhất**; truy vấn xuống database phải giới hạn tenant/owner/phạm vi. `@PostFilter` có thể có chi phí cao và vẫn đọc dữ liệu ngoài phạm vi vào bộ nhớ.

### 6.4. Khi nào tắt prePostEnabled?

Chỉ nên tắt có chủ đích khi:

- Dự án muốn thay thế interceptor chuẩn bằng advisor/custom manager riêng được kiểm chứng.
- Ứng dụng migration chỉ cho phép một nhóm annotation cụ thể và đã xử lý toàn bộ `@PreAuthorize`/`@PostAuthorize` cũ.
- Test security xác nhận mọi hành động nhạy cảm vẫn có chốt khác.

Một cấu hình như:

```java
@EnableMethodSecurity(
    prePostEnabled = false,
    securedEnabled = true,
    jsr250Enabled = false
)
```

sẽ kích hoạt `@Secured` nhưng không tự kích hoạt các annotation pre/post hoặc JSR-250. Đây là thay đổi chính sách **toàn ứng dụng**, không phải tối ưu hiệu năng vô hại.

## 7. Cấu hình mẫu tích hợp Spring Boot 3 và Spring Security 6

Ví dụ cho thấy cả ba nhóm annotation hoạt động trên những method khác nhau. Các ví dụ này là **mã tích hợp**, không phải một file độc lập chạy bằng `javac`; chúng cần dependency Spring Boot, Spring Security, Jakarta Annotation API và cấu hình xác thực thực tế.

### 7.1. Một lớp bật toàn bộ nhóm cần dùng

```java
package demo.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
```

Đây là nơi dễ review nhất: những phương thức đang sử dụng `@Secured` và JSR-250 **được kích hoạt tường minh** thay vì bị bỏ sót mặc định.

### 7.2. Service có các loại annotation khác nhau

```java
package demo.security;

import jakarta.annotation.security.DenyAll;
import jakarta.annotation.security.PermitAll;
import jakarta.annotation.security.RolesAllowed;
import org.springframework.security.access.annotation.Secured;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class InvoiceSecurityExamples {

    @PreAuthorize("hasAuthority('invoice:read')")
    public String readInvoice() {
        return "invoice-readable";
    }

    @Secured("ROLE_ADMIN")
    public String adminReindex() {
        return "admin-reindex";
    }

    @RolesAllowed({"MANAGER", "ADMIN"})
    public String managerSummary() {
        return "manager-summary";
    }

    @PermitAll
    public String publicBanner() {
        return "public-banner";
    }

    @DenyAll
    public String disabledLegacyAction() {
        return "should-never-run";
    }

    @Secured("ROLE_ADMIN")
    @PreAuthorize("hasAuthority('invoice:approve')")
    public String approveInvoice() {
        return "invoice-approved";
    }
}
```

Giải thích từng method:

1. `readInvoice()` cần `invoice:read` nhờ nhóm pre/post.
2. `adminReindex()` cần `ROLE_ADMIN` nhờ `securedEnabled=true`.
3. `managerSummary()` cho phép `ROLE_MANAGER` **hoặc** `ROLE_ADMIN` nhờ JSR-250 và role prefix mặc định.
4. `publicBanner()` được cho phép bởi chốt JSR-250 của nó, nhưng HTTP route hoặc interceptor độc lập khác vẫn có thể chặn.
5. `disabledLegacyAction()` bị từ chối bởi JSR-250 khi lời gọi qua proxy; chỉ an toàn khi `jsr250Enabled=true` và đường gọi thực sự được intercept.
6. `approveInvoice()` chứa hai nhóm đang bật: cả điều kiện `ROLE_ADMIN` lẫn `invoice:approve` phải thỏa. Chỉ có admin role không đủ; chỉ có approve permission cũng không đủ.

Ví dụ cuối cố ý để minh họa **nhiều interceptor cùng áp dụng**. Trong code sản xuất, có thể ưu tiên một `@PreAuthorize("hasRole('ADMIN') and hasAuthority('invoice:approve')")` để biểu thức dễ nhìn, giảm rủi ro sai khác khi migration.

### 7.3. HTTP security là lớp khác, không thay công tắc method

Một cấu hình HTTP minh họa:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpRules {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public/banner")
                .permitAll()
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

Giả sử controller gọi `InvoiceSecurityExamples` qua Spring bean. Khi request đi vào `/api/**`, nó phải qua HTTP rule **và** method rule tương ứng. Việc HTTP chỉ yêu cầu `authenticated()` không làm mất tác dụng của `@Secured` hoặc `@RolesAllowed` khi các nhóm được bật.

Ngược lại, không thể chữa lỗi `securedEnabled=false` bằng cách tin rằng mọi API hiện đều có `hasRole("ADMIN")`: một service có thể được gọi từ job, message consumer hoặc một HTTP route mới.

### 7.4. Dependency và package theo phiên bản

Trong Spring Boot 3 / Spring Security 6:

- `@EnableMethodSecurity`: `org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity`.
- `@PreAuthorize`: `org.springframework.security.access.prepost.PreAuthorize`.
- `@Secured`: `org.springframework.security.access.annotation.Secured`.
- `@RolesAllowed`, `@PermitAll`, `@DenyAll`: `jakarta.annotation.security.*`, phải có API Jakarta Annotation phù hợp trong dependencies.
- `@WithMockUser` cho test: `org.springframework.security.test.context.support.WithMockUser` từ `spring-security-test`.

Trong tài liệu Spring 5 hoặc Java EE cũ, có thể thấy `javax.annotation.security.*`. Không sao chép import cũ vào dự án đã chuyển sang Jakarta mà không xác nhận dependency/phiên bản.

## 8. Java 17 chạy độc lập: công tắc bật/tắt làm thay đổi chốt nào?

Để nhìn rõ **khác biệt giữa annotation có mặt và interceptor có được bật hay không**, chương trình sau mô phỏng logic bật các nhóm, không phụ thuộc Spring Framework.

Cảnh báo: đây là **mô hình học tập của riêng bài**, không dùng annotation Spring thật, không tạo proxy và không giải thích toàn bộ HTTP/security context của ứng dụng. Khi một nhóm tắt, mô hình cho thấy **chốt thuộc nhóm ấy không kiểm tra quyền**; trong ứng dụng thực vẫn có thể có chốt khác.

Lưu file `MethodSecurityFlagsDemo.java`:

```java
import java.util.Set;

public class MethodSecurityFlagsDemo {

    enum Rule {
        PRE_READ,
        SECURED_ADMIN,
        JSR_MANAGER,
        JSR_DENY,
        MIXED
    }

    record Flags(
        boolean prePostEnabled,
        boolean securedEnabled,
        boolean jsr250Enabled
    ) {}

    record Actor(
        boolean authenticated,
        Set<String> authorities
    ) {}

    static boolean has(Actor actor, String authority) {
        return actor != null
            && actor.authenticated()
            && actor.authorities() != null
            && actor.authorities().contains(authority);
    }

    static boolean allowed(Flags flags, Rule rule, Actor actor) {
        return switch (rule) {
            case PRE_READ ->
                !flags.prePostEnabled()
                    || has(actor, "invoice:read");

            case SECURED_ADMIN ->
                !flags.securedEnabled()
                    || has(actor, "ROLE_ADMIN");

            case JSR_MANAGER ->
                !flags.jsr250Enabled()
                    || has(actor, "ROLE_MANAGER")
                    || has(actor, "ROLE_ADMIN");

            case JSR_DENY ->
                !flags.jsr250Enabled();

            // Hai annotation thuộc hai nhóm cùng đang bật:
            // tất cả các chốt thực sự hoạt động đều phải qua.
            case MIXED ->
                (!flags.prePostEnabled()
                    || has(actor, "invoice:read"))
                && (!flags.securedEnabled()
                    || has(actor, "ROLE_ADMIN"));
        };
    }

    static void show(String label, boolean value) {
        System.out.println(label + ": " + value);
    }

    public static void main(String[] args) {
        Flags defaults = new Flags(true, false, false);
        Flags all = new Flags(true, true, true);
        Flags securedOnly = new Flags(false, true, false);

        Actor admin = new Actor(
            true, Set.of("ROLE_ADMIN", "invoice:read")
        );
        Actor manager = new Actor(
            true, Set.of("ROLE_MANAGER", "invoice:read")
        );
        Actor viewer = new Actor(
            true, Set.of("invoice:read")
        );
        Actor anonymous = new Actor(
            false, Set.of()
        );

        show("default pre viewer",
            allowed(defaults, Rule.PRE_READ, viewer));
        show("default pre anonymous",
            allowed(defaults, Rule.PRE_READ, anonymous));
        show("default secured ignored",
            allowed(defaults, Rule.SECURED_ADMIN, viewer));
        show("default jsr roles ignored",
            allowed(defaults, Rule.JSR_MANAGER, viewer));
        show("default jsr deny ignored",
            allowed(defaults, Rule.JSR_DENY, viewer));

        show("all secured viewer",
            allowed(all, Rule.SECURED_ADMIN, viewer));
        show("all secured admin",
            allowed(all, Rule.SECURED_ADMIN, admin));
        show("all jsr manager",
            allowed(all, Rule.JSR_MANAGER, manager));
        show("all jsr viewer",
            allowed(all, Rule.JSR_MANAGER, viewer));
        show("all jsr deny admin",
            allowed(all, Rule.JSR_DENY, admin));
        show("all mixed admin",
            allowed(all, Rule.MIXED, admin));
        show("all mixed manager",
            allowed(all, Rule.MIXED, manager));

        show("secured only pre ignored",
            allowed(securedOnly, Rule.PRE_READ, viewer));
        show("secured only admin",
            allowed(securedOnly, Rule.SECURED_ADMIN, admin));
    }
}
```

Biên dịch và chạy:

```bash
javac MethodSecurityFlagsDemo.java
java MethodSecurityFlagsDemo
```

Stdout dự kiến:

```text
default pre viewer: true
default pre anonymous: false
default secured ignored: true
default jsr roles ignored: true
default jsr deny ignored: true
all secured viewer: false
all secured admin: true
all jsr manager: true
all jsr viewer: false
all jsr deny admin: false
all mixed admin: true
all mixed manager: false
secured only pre ignored: true
secured only admin: true
```

**Phân tích quan trọng:**

- Với cờ mặc định, `PRE_READ` còn hoạt động, nhưng `SECURED_ADMIN` và `JSR_MANAGER/JSR_DENY` bị bỏ qua ở mô hình.
- Dòng “default jsr deny ignored: true” **không khuyến nghị cho phép** hành động bị đánh dấu `@DenyAll`. Nó phơi bày nguy cơ: nếu `jsr250Enabled=false` thì chốt JSR-250 không tự chặn.
- Khi bật cả ba cờ, user chỉ có `invoice:read` không qua `SECURED_ADMIN`; user manager qua `JSR_MANAGER`; `JSR_DENY` chặn cả admin.
- Ở rule `MIXED`, admin cần **cả** `ROLE_ADMIN` và `invoice:read`; manager chỉ có permission read không đủ.
- Cấu hình `securedOnly` bật `@Secured` nhưng tắt pre/post: rule `PRE_READ` bị bỏ qua trong mô hình.
- Chương trình không mô phỏng role hierarchy, JSR-250 `@PermitAll`, AOP, 401/403, CSRF hay object security. Nó chỉ minh họa hiệu ứng của **bật/tắt nhóm interceptor**.

## 9. Phạm vi annotation trên class, method và interface

### 9.1. Class-level annotation

Spring Security method security hỗ trợ annotation ở class level. Ví dụ:

```java
@PreAuthorize("hasRole('USER')")
@Service
public class UserOperations {

    public String readOwnSummary() {
        return "own-summary";
    }

    @PreAuthorize("hasRole('ADMIN')")
    public String resetAnotherUser() {
        return "reset-done";
    }
}
```

Trong nhóm `@PreAuthorize`, annotation ở method cụ thể **ghi đè** quy tắc class-level cùng loại: `resetAnotherUser()` dùng điều kiện admin thay vì mặc định user. Vì vậy, nếu muốn **cả hai** yêu cầu, phải diễn đạt rõ trong biểu thức hoặc policy; không trông chờ framework tự kết hợp class và method cùng một annotation.

### 9.2. Interface và nhiều nguồn annotation

Spring Security có thể xử lý annotation đặt trên interface/class/method; với proxy, điều kiện kế thừa phải tương thích kiểu lời gọi và cách framework tìm metadata. Tài liệu nêu khi một class kế thừa annotation mâu thuẫn từ **hai interface khác nhau**, việc xác định chính sách có thể nhập nhằng và quá trình khởi động có thể thất bại. Cách giải quyết là chỉ rõ annotation ở method concrete.

Không dựa vào nhiều interface với role khác nhau như một cách “hợp” quyền:

```java
interface Readable {
    @PreAuthorize("hasAuthority('doc:read')")
    String view();
}

interface AdminOnly {
    @PreAuthorize("hasRole('ADMIN')")
    String view();
}
```

Nếu class implement cả hai, phải khai báo chính sách không nhập nhằng trên implementation. Nên ưu tiên một policy bean hoặc biểu thức tổng hợp khi có nhiều điều kiện thực sự bắt buộc.

### 9.3. Nhiều nhóm annotation trên cùng một method

Ví dụ:

```java
@Secured("ROLE_ADMIN")
@PreAuthorize("hasAuthority('invoice:approve')")
public void approve(long invoiceId) {
    // Kiểm tra người tạo khác người duyệt và trạng thái DRAFT.
}
```

Nếu `securedEnabled=true` và `prePostEnabled=true`, hai loại interceptor có thể cùng kiểm tra và việc thực thi chỉ diễn ra nếu **không loại nào từ chối**. Đừng giả định `@Secured` “thắng” `@PreAuthorize` hoặc ngược lại theo một thứ tự ưu tiên ngầm.

Nếu `securedEnabled=false`, chỉ phần `@PreAuthorize` đang hoạt động. Điều này có thể **mở rộng quyền ngoài ý định**: người có `invoice:approve` nhưng không có `ROLE_ADMIN` sẽ không còn bị @Secured chặn. Trước khi tắt một cờ, phải rà soát các method có nhiều nhóm annotation và viết regression test.

Nếu `@PermitAll` và `@PreAuthorize` cùng xuất hiện, đừng coi `@PermitAll` là cách vượt các điều kiện khác. Tốt nhất tránh ghi chính sách mơ hồ, chọn một biểu thức rõ ràng cho một mục đích.

### 9.4. Proxy, self-invocation, private/final và đối tượng tạo thủ công

Với `mode=PROXY` thông dụng:

```java
@Service
class BillingService {

    public void runBatch() {
        cancelAll(); // Lời gọi nội bộ trong cùng instance.
    }

    @Secured("ROLE_ADMIN")
    public void cancelAll() {
        // Hành động nhạy cảm.
    }
}
```

Lời gọi từ `runBatch()` tới `cancelAll()` trên chính instance có thể **bỏ qua Spring AOP proxy**, nên annotation `@Secured` không được thực thi như mong muốn dù `securedEnabled=true`.

Tương tự:

- Bean tự tạo bằng `new BillingService()` không được Spring tự động gắn interceptor.
- Private method không thể là ranh giới proxy đáng tin cho method security; cần điểm vào public/khả dụng và được intercept.
- Final class/final method có hạn chế với class-based proxy; proxy interface và class cũng có các điều kiện khác nhau.
- Kotlin class/method có thể final mặc định; cần xem cơ chế open/proxy hoặc AspectJ phù hợp.
- `@Async`, task nền hoặc message consumer không tự mang `SecurityContext` từ HTTP request; phải xác định principal/service identity rõ.

Nếu có yêu cầu intercept self-invocation, Spring Security có chế độ AspectJ qua `@EnableMethodSecurity(mode = AdviceMode.ASPECTJ)` khi đã cấu hình weaving và dependency phù hợp. **Chỉ đổi flag sang ASPECTJ không tự bổ sung weaving**.

### 9.5. Bật annotation nào cũng không thay được bảo vệ dữ liệu

Một phương thức `@Secured("ROLE_ADMIN")` nhưng chỉ gọi `repository.findById(id)` có thể lộ dữ liệu tenant khác nếu admin thực tế chỉ có phạm vi tenant A. Chốt method phải được bổ sung bằng kiểm tra owner/tenant, trạng thái và phạm vi query. Role chức năng không phải object authorization.

## 10. Kiểm thử thực tế: xác nhận nhóm nào đang thực thi

### 10.1. Ma trận test cho ba cờ

| Cấu hình | Method | Principal | Kỳ vọng riêng chốt method |
| --- | --- | --- | --- |
| Mặc định | `@PreAuthorize("hasAuthority('invoice:read')")` | Có `invoice:read` | Cho qua |
| Mặc định | Cùng method | Không có quyền | Từ chối |
| Mặc định | `@Secured("ROLE_ADMIN")` | Không có admin | Annotation này không tạo chốt |
| Mặc định | `@DenyAll` | Có admin | Annotation JSR-250 chưa tạo chốt |
| `securedEnabled=true` | `@Secured("ROLE_ADMIN")` | `ROLE_USER` | Từ chối |
| `securedEnabled=true` | Cùng method | `ROLE_ADMIN` | Cho qua |
| `jsr250Enabled=true` | `@RolesAllowed("MANAGER")` | `ROLE_MANAGER` | Cho qua |
| `jsr250Enabled=true` | Cùng method | `ROLE_USER` | Từ chối |
| `jsr250Enabled=true` | `@DenyAll` | `ROLE_ADMIN` | Từ chối |
| Cả ba bật | `@Secured` + `@PreAuthorize` | Chỉ có một trong hai | Từ chối |
| `prePostEnabled=false` | `@PreAuthorize` | Không có quyền | Không có chốt pre/post chuẩn |
| Mọi cờ bật, self-invocation | Method nhạy cảm được gọi nội bộ | Bất kỳ | Có thể bỏ qua proxy, cần sửa thiết kế |

**Chú ý:** “Annotation chưa tạo chốt” không được dịch thành “được phép HTTP”. Test riêng method trực tiếp qua Spring bean/proxy, tạo fixture có thể phân biệt lớp HTTP với lớp service.

### 10.2. Test tích hợp method bằng JUnit 5 và Spring Security Test

Một bài test đầy đủ nên load cấu hình `@EnableMethodSecurity` và bean service thật, sau đó gọi **qua Spring bean**:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class InvoiceMethodSecurityTest {

    @Autowired
    InvoiceSecurityExamples invoices;

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanRunSecuredMethod() {
        assertEquals("admin-reindex", invoices.adminReindex());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotRunSecuredMethod() {
        assertThrows(
            AccessDeniedException.class,
            () -> invoices.adminReindex()
        );
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void deniedForEveryone() {
        assertThrows(
            AccessDeniedException.class,
            () -> invoices.disabledLegacyAction()
        );
    }

    @Test
    @WithMockUser(authorities = "invoice:read")
    void readerCanUsePreAuthorize() {
        assertEquals("invoice-readable", invoices.readInvoice());
    }
}
```

Đây là **mã test tích hợp cần dự án Spring Boot thật**, không phải file Java độc lập. Test đầu giả định đã import `InvoiceSecurityExamples` và class cấu hình bật cả nhóm. Khi test `@RolesAllowed`, thêm `@WithMockUser(roles="MANAGER")` và một user chỉ có `ROLE_USER` để xác nhận permit/deny.

Lưu ý `@WithMockUser(roles="ADMIN")` tạo authority `ROLE_ADMIN`; còn `@WithMockUser(authorities="invoice:read")` dùng tên authority chính xác. Test helper **không chứng minh** cơ chế xác thực thực tế từ JWT/password/IdP đã hoạt động. Cần test xác thực riêng.

### 10.3. Test rằng annotation tắt thật sự không được kiểm tra

Dành một cấu hình test riêng chỉ bật mặc định:

```java
@Configuration
@EnableMethodSecurity
class DefaultOnlyMethodSecurityConfig {
}
```

Khi đó gọi bean có `@Secured("ROLE_ADMIN")` bằng một user chỉ có `ROLE_USER`, nếu không có chốt method khác, lời gọi vẫn có thể chạy. Test này là **negative control** giúp chứng minh cấu hình thiếu `securedEnabled` nguy hiểm thế nào. Tương tự với `@DenyAll` và `jsr250Enabled=false`.

Không trộn nhiều `@EnableMethodSecurity` của các cấu hình đối lập vào cùng một ApplicationContext rồi suy luận kết quả. Tách test context/profile cho từng biến thể, hoặc dùng integration tests khởi động ứng dụng với một cấu hình rõ ràng.

### 10.4. MockMvc chứng minh HTTP và method phối hợp

Trong ứng dụng MVC:

- Dùng `MockMvc` để chứng minh người chưa đăng nhập không qua route bảo vệ.
- Dùng user đăng nhập thiếu role để chứng minh service `@Secured` chặn ngay cả khi HTTP matcher chỉ yêu cầu `authenticated()`.
- Dùng user đủ role nhưng thiếu quyền tenant/owner để chứng minh policy đối tượng chặn.
- Với POST/PATCH/DELETE, nếu CSRF bật, phải cung cấp token CSRF hợp lệ khi muốn test **method authorization**; nếu không, 403 có thể do CSRF trước khi service được gọi.
- Kiểm tra **không có side effect** khi method bị từ chối: dữ liệu không thay đổi, không phát sinh message/thanh toán.

Đừng chỉ khẳng định response 403 là method security đã chạy. Cần quan sát hoặc test riêng service để biết chốt nào thực sự từ chối.

## 11. Migration từ EnableGlobalMethodSecurity và JSR-250 cũ

### 11.1. Hai annotation kích hoạt không hoàn toàn tương đương

Dòng Spring Security 5 và code cũ có thể dùng:

```java
@EnableGlobalMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
```

Trong hệ Spring Security hiện đại, tài liệu khuyến nghị chuyển sang:

```java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
```

`@EnableMethodSecurity` sử dụng kiến trúc `AuthorizationManager`, Spring AOP và các cơ chế cấu hình hiện đại hơn; không đơn giản chỉ đổi tên annotation rồi bỏ qua test. Đặc biệt, **pre/post được bật mặc định** ở cấu hình mới, còn `securedEnabled` và `jsr250Enabled` mặc định false. Khi migrate, bảo toàn rõ các nhóm annotation mà code cũ thực sự dùng.

### 11.2. Kế hoạch migration an toàn

1. Kiểm kê toàn bộ `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, `@Secured`, `@RolesAllowed`, `@PermitAll`, `@DenyAll` trong **code của dự án đang được migration**.
2. Kiểm tra các cấu hình `@EnableGlobalMethodSecurity` cũ, bean expression handler, custom voter, pointcut hoặc AspectJ.
3. Chọn đúng cờ cho `@EnableMethodSecurity` mới. Nếu đang dùng `@Secured`/JSR-250, khai báo cờ true tường minh.
4. Chuyển import `javax.annotation.security.*` sang `jakarta.annotation.security.*` khi nâng lên Spring Boot 3/Spring Framework 6 theo dependency tương thích.
5. Kiểm tra cách map role prefix, authority từ IdP/JWT và role hierarchy vào manager đang dùng.
6. Viết test role đủ/thiếu, anonymous, class-level và method-level, giao thoa nhiều annotation.
7. Test self-invocation, proxy, các phương thức gọi từ background job, message consumer.
8. Kiểm tra HTTP filter chain và object-level authorization độc lập.
9. Chạy regression tests trước/sau nâng phiên bản; không tắt cờ để sửa một lỗi startup khi chưa rõ ảnh hưởng.
10. Ghi lại việc bật/tắt annotation trong tài liệu kiến trúc để người sau không suy luận từ annotation nằm trong source code.

### 11.3. Spring Security 6.x và 7.x

Spring Security 6.x và 7.x đều hỗ trợ mô hình method authorization với `@EnableMethodSecurity` và các nhóm annotation. Tuy nhiên, API nội bộ/custom manager và các tùy biến như `AuthorizationManagerFactory` có thể thay đổi theo phiên bản.

Nội dung bài này dùng các cờ `prePostEnabled`, `securedEnabled`, `jsr250Enabled` được JavaDoc Spring Security 6.5 xác nhận. Khi chuyển sang Spring Security 7.x hoặc cấu hình nâng cao, cần đối chiếu JavaDoc phiên bản đã khóa, đặc biệt nếu tự tạo interceptor hoặc manager. Tránh trộn ví dụ cấu hình cũ `@EnableGlobalMethodSecurity` với manager 7.x mà không rà soát tương thích.

## 12. Troubleshooting: có 403 hoặc không có 403 ngoài ý định

### 12.1. Checklist chẩn đoán

```text
Method được gọi trên Spring bean hay new object?
  |
  v
Đã bật @EnableMethodSecurity chưa?
  |
  v
Annotation thuộc nhóm nào?
  |
  +-- @PreAuthorize / @PostAuthorize / @PreFilter / @PostFilter
  |        cần prePostEnabled=true
  |
  +-- @Secured
  |        cần securedEnabled=true
  |
  +-- @RolesAllowed / @PermitAll / @DenyAll
           cần jsr250Enabled=true
  |
  v
Lời gọi có đi qua proxy / advice không?
  |
  v
Có nhiều annotation/class/interface cùng ảnh hưởng không?
  |
  v
Authentication có authority/role prefix nào?
  |
  v
RoleHierarchy/ExpressionHandler có được áp dụng đúng không?
  |
  v
HTTP matcher/CSRF hoặc object policy có từ chối trước/sau không?
  |
  v
Kiểm tra result + side effects, không chỉ mã response
```

### 12.2. Bảng lỗi và cách khắc phục

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `@Secured("ROLE_ADMIN")` bị bỏ qua | `securedEnabled=false` | Kiểm tra `@EnableMethodSecurity` |
| `@RolesAllowed` không chặn | `jsr250Enabled=false` hoặc import sai đời | Kiểm tra cờ và `jakarta.annotation.security.*` |
| `@DenyAll` vẫn chạy vào thân method | JSR-250 không bật, self-invocation hoặc ngoài proxy | Test method qua Spring bean |
| `@PreAuthorize` không chặn | Chưa bật method security hoặc `prePostEnabled=false` | Kiểm tra config/test context |
| `@Secured` deny user có role | Authority thực khác `ROLE_ADMIN` hoặc hierarchy không áp dụng | In danh sách authority đã lọc bí mật |
| `@RolesAllowed("ADMIN")` không match | Prefix hoặc mapper không thống nhất | Kiểm tra `ROLE_ADMIN` trong Authentication |
| Chỉ một method trong class có hành vi khác | Method-level override class-level cùng nhóm | Rà soát vị trí annotation |
| Hai interface có annotation mâu thuẫn | Metadata không rõ, có thể lỗi startup | Đặt policy concrete method |
| Method public từ ngoài an toàn, gọi nội bộ bỏ qua | Self-invocation qua `this` | Refactor ranh giới proxy |
| `@PostAuthorize` từ chối sau khi đã ghi | Dùng after-check cho thao tác có side effect | Chuyển kiểm tra trước và transaction |
| Test 403 nhưng không rõ nguyên nhân | CSRF, HTTP rule, method hoặc data | Test từng chốt riêng |
| Bật hết các cờ rồi user bị từ chối nhiều hơn | Nhiều interceptor cùng hoạt động | Review các điều kiện kết hợp |
| Tắt JSR-250 rồi app bớt 403 | Đã vô hiệu hóa `@RolesAllowed/@DenyAll` | Khôi phục và sửa chính sách gốc |
| Method chạy từ job không có principal | Context không truyền hoặc task identity thiếu | Thiết kế identity của job/service |
| Chuyển Boot 2→3 nhưng thiếu annotation | Chưa migrate `javax`/`jakarta` | Kiểm tra imports/dependency |
| Tưởng `@PermitAll` mở được route HTTP denyAll | Lẫn tầng bảo vệ | Tách HTTP và method security |

### 12.3. Ghi log an toàn

Trong môi trường debug/staging, có thể theo dõi method, interceptor hoạt động, principal đã xác minh, authority liên quan và quyết định. Không log raw password/JWT/cookie, toàn bộ dữ liệu tài chính hoặc hồ sơ riêng tư. Ghi correlation ID và loại rule đủ để nối log HTTP với service; tránh lộ nội dung biểu thức chứa dữ liệu nhạy cảm.

Nếu phải giải thích 401/403:

- 401 thường liên quan yêu cầu chưa được xác thực.
- 403 thường liên quan thiếu quyền hoặc có thể do CSRF.
- Exception method security có thể được bộ xử lý HTTP chuyển thành status tương ứng.
- Một lời gọi từ job không có HTTP response, nên có thể thấy exception thay vì mã HTTP.

Không suy luận “annotation đúng” chỉ từ status; hãy nhìn chốt nào chạy và hệ quả thật.

## 13. Bài tập thực hành

### Bài 1 — Điền bảng công tắc

Với `@EnableMethodSecurity` mặc định, dự đoán hiệu lực của `@PreAuthorize`, `@Secured`, `@RolesAllowed`, `@PermitAll` và `@DenyAll`. Sau đó bật lần lượt `securedEnabled` và `jsr250Enabled`, dùng test trên Spring bean để chứng minh điểm khác nhau.

### Bài 2 — Chạy Java 17

Biên dịch `MethodSecurityFlagsDemo.java`, dự đoán mọi dòng stdout trước khi chạy. Thêm một rule `JSR_PERMIT`; giải thích vì sao cả khi chốt ấy cho phép, một HTTP rule hoặc policy dữ liệu khác vẫn có thể từ chối.

### Bài 3 — Sửa lỗ hổng annotation chưa bật

Cho service chứa `@Secured("ROLE_ADMIN")` trên thao tác xóa dữ liệu. Ứng dụng chỉ có `@EnableMethodSecurity` mặc định. Thiết kế test mà user `ROLE_USER` vẫn gọi được (trong môi trường test giả lập không có chốt khác), sau đó bật `securedEnabled=true` và xác nhận AccessDeniedException.

### Bài 4 — Migration Jakarta

Một dự án cũ có `@RolesAllowed("ADMIN")` import `javax.annotation.security.RolesAllowed`. Nâng lên Boot 3, chọn dependency Jakarta và import phù hợp, bật `jsr250Enabled=true`, kiểm tra principal có `ROLE_ADMIN`. Chứng minh method được bảo vệ khi gọi qua Spring bean.

### Bài 5 — Giao thoa annotation

Một method có `@Secured("ROLE_ADMIN")` và `@PreAuthorize("hasAuthority('invoice:approve')")`. Thử admin không có approve, approver không phải admin và admin có đủ cả hai. Sau đó tắt `securedEnabled` ở test context riêng và giải thích vì sao tập người được phép có thể mở rộng.

### Bài 6 — Tìm đường qua proxy

Viết service có `public run()` gọi `this.deleteAll()` được `@DenyAll` bảo vệ. Test lời gọi trực tiếp qua bean proxy và lời gọi nội bộ. Thiết kế lại để hành động nhạy cảm không thể được gọi mà thiếu chốt service/data.

### Bài 7 — Bảo vệ theo tenant

Tạo hai tenant. User có `ROLE_ADMIN` của tenant A gọi service có `@Secured("ROLE_ADMIN")` để sửa tài liệu tenant B. Thêm object policy dựa trên tenant được xác minh và test deny. Chứng minh bật cờ method security không tự tạo quyền liên tenant.

## 14. Checklist triển khai

- [ ] Có một cấu hình `@EnableMethodSecurity` rõ, đã kiểm tra đúng ApplicationContext.
- [ ] `prePostEnabled`/`securedEnabled`/`jsr250Enabled` tương thích các annotation đang có trong code.
- [ ] Nếu dùng `@Secured`, cờ `securedEnabled=true` và role strings được kiểm chứng.
- [ ] Nếu dùng `@RolesAllowed/@PermitAll/@DenyAll`, cờ `jsr250Enabled=true` và import Jakarta đúng phiên bản.
- [ ] Không coi “annotation bị tắt” là “mặc định deny”.
- [ ] Có kiểm thử qua Spring bean/proxy, không chỉ gọi object tạo bằng `new`.
- [ ] Đã kiểm tra self-invocation, private/final methods và interface metadata.
- [ ] Method có nhiều nhóm annotation không vô tình mở rộng quyền khi tắt một cờ.
- [ ] `@PostAuthorize` không là chốt duy nhất trước side effect nhạy cảm.
- [ ] HTTP request authorization, CSRF và object/data policy được kiểm tra độc lập.
- [ ] Role prefix và nguồn `GrantedAuthority` từ IdP/JWT/session được chuẩn hóa.
- [ ] Job/background task có mô hình principal và quyền thực thi riêng.
- [ ] Test cả trường hợp cho phép và từ chối, quan sát side effect.
- [ ] Migration `@EnableGlobalMethodSecurity` và `javax→jakarta` có test hồi quy.
- [ ] Thay đổi flags được review như thay đổi chính sách bảo mật, không phải cấu hình nhỏ.

## 15. Câu hỏi tự kiểm tra

1. **Mặc định `@EnableMethodSecurity` bật nhóm nào?** Nhóm pre/post gồm `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`.
2. **`securedEnabled` mặc định?** False.
3. **`jsr250Enabled` mặc định?** False.
4. **Để `@Secured` được đánh giá cần gì?** Method security được bật, `securedEnabled=true` và lời gọi đi qua interceptor tương ứng.
5. **Nhóm `jsr250Enabled` gồm ba annotation nào?** `@RolesAllowed`, `@PermitAll`, `@DenyAll`.
6. **Nếu `@DenyAll` nằm trong code nhưng JSR-250 tắt thì sao?** Annotation đó không tạo chốt method của JSR-250; kiểm tra khác có thể còn, nhưng không được dựa riêng vào nó.
7. **`@Secured({"ROLE_ADMIN","ROLE_SUPPORT"})` yêu cầu cả hai?** Không; một trong các authority được chấp nhận là đủ cho chốt này.
8. **`@RolesAllowed("ADMIN")` thường so với authority nào?** `ROLE_ADMIN` khi dùng tiền tố mặc định `ROLE_`.
9. **Có thể dùng SpEL trong `@Secured("hasRole('ADMIN')")` không?** Không; `@Secured` không đánh giá biểu thức SpEL như `@PreAuthorize`.
10. **`@PermitAll` có vượt `anyRequest().denyAll()` HTTP không?** Không.
11. **Tại sao bật `securedEnabled=true` có thể khiến app phát sinh 403 mới?** Các chốt `@Secured` trước đó chưa hoạt động nay bắt đầu thực thi; phải xem chính sách thật.
12. **Vì sao self-invocation nguy hiểm?** Lời gọi nội bộ trong cùng instance có thể bỏ qua proxy và các interceptor bảo mật.
13. **`@PostAuthorize` có phù hợp làm chốt duy nhất cho thao tác chuyển tiền?** Không; kiểm tra sau có thể quá muộn.
14. **Nếu method có cả `@PreAuthorize` và `@Secured` được bật thì sao?** Các điều kiện được áp dụng đều phải cho qua; tắt một nhóm có thể làm thiếu chốt.
15. **Bật method security có tự bảo vệ mọi service method không?** Không; cần annotation/pointcut phù hợp và lời gọi đi qua interception.
16. **Tại sao cần kiểm thử thẳng service ngoài HTTP?** Để chứng minh method advice thực sự chạy, không lẫn với HTTP matcher/CSRF.
17. **Sang Spring Boot 3, JSR-250 import thường dùng package nào?** `jakarta.annotation.security.*`.
18. **Một user admin có thể sửa mọi tenant vì `@RolesAllowed("ADMIN")` không?** Không mặc định; tenant/object policy vẫn độc lập.

**Ghi nhớ:** ba cờ của `@EnableMethodSecurity` quyết định **những nhóm annotation nào được Spring Security thực sự đăng ký interceptor**. `prePostEnabled=true` là mặc định; `securedEnabled=false` và `jsr250Enabled=false` là mặc định. Vì vậy, những annotation `@Secured`, `@RolesAllowed` hoặc thậm chí `@DenyAll` xuất hiện trong source code **không phải bằng chứng quyền đã được kiểm tra**. Hãy bật đúng nhóm cần dùng, hiểu giới hạn Spring AOP, kiểm thử từng chốt và tiếp tục bảo vệ hành động/tài nguyên ở tầng nghiệp vụ.

### Tài liệu chính thức

- [Spring Security 6.5 – EnableMethodSecurity JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Security 6.5 – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring Security – Method Security (current)](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Servlet Authorization and HTTP rules](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Jakarta Annotations – @RolesAllowed, @PermitAll, @DenyAll](https://jakarta.ee/specifications/annotations/)