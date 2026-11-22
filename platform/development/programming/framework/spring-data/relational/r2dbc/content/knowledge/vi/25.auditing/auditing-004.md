# Cung cấp người dùng hiện tại bằng ReactiveAuditorAware

Spring Data Relational R2DBC có thể tự động ghi nhận ai đã tạo hoặc cập nhật một entity thông qua auditing. Các annotation như **@CreatedBy** và **@LastModifiedBy** đánh dấu những thuộc tính lưu người thực hiện thao tác. Để Spring biết người dùng hiện tại là ai trong ứng dụng reactive, ta cung cấp một bean triển khai **ReactiveAuditorAware<T>**.

Trong ứng dụng Spring WebFlux kết hợp Spring Security, danh tính xác thực được truyền qua **Reactor Context**. Vì vậy, ReactiveAuditorAware cần đọc security context theo cách reactive và trả về một **Mono<T>**. Không nên lấy người dùng bằng **SecurityContextHolder** kiểu imperative hoặc chặn luồng bằng **block()**, vì các cách đó không phù hợp với vòng đời reactive.

Bài học này trình bày cách kết nối ReactiveAuditorAware với Spring Security, chọn kiểu định danh, cấu hình auditing cho R2DBC, xử lý request chưa đăng nhập và tác vụ nền, cách kiểm thử và các trường hợp auditing tự động không được áp dụng.

## 1. Auditing cần biết ai đang thực hiện thao tác

Auditing lưu thông tin về thời điểm và tác nhân tạo hoặc sửa dữ liệu. Một entity có thể có các trường:

- Người tạo: **createdBy**.
- Thời điểm tạo: **createdDate**.
- Người sửa gần nhất: **lastModifiedBy**.
- Thời điểm sửa gần nhất: **lastModifiedDate**.

Ví dụ bảng đơn hàng:

~~~text
purchase_order
+----+-------------+---------------------+-----------------+---------------------+
| id | order_no    | created_at          | created_by      | last_modified_by   |
+----+-------------+---------------------+-----------------+---------------------+
| 10 | ORD-001     | 2026-10-01 09:00:00 | 42              | 42                  |
| 11 | ORD-002     | 2026-10-02 10:30:00 | 57              | 81                  |
+----+-------------+---------------------+-----------------+---------------------+
~~~

Các trường thời gian cho biết lúc nào thao tác xảy ra. Các trường auditor cho biết tài khoản nào thực hiện thao tác.

Spring Data cung cấp annotation để đánh dấu thuộc tính auditing:

| Annotation | Ý nghĩa |
|---|---|
| **@CreatedBy** | Auditor của lần tạo entity |
| **@CreatedDate** | Thời điểm tạo entity |
| **@LastModifiedBy** | Auditor của lần sửa gần nhất |
| **@LastModifiedDate** | Thời điểm sửa gần nhất |

Các annotation này chỉ mô tả metadata. Để chúng được xử lý, ứng dụng phải bật auditing và cung cấp nguồn thời gian/người dùng phù hợp. Với R2DBC, nguồn người dùng reactive được khai báo bằng **ReactiveAuditorAware<T>**.

## 2. ReactiveAuditorAware là gì?

**ReactiveAuditorAware<T>** là interface của Spring Data, thuộc package **org.springframework.data.domain**. Nó cung cấp auditor hiện tại theo kiểu reactive:

~~~java
public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
~~~

Kiểu generic **T** là kiểu định danh của auditor. Ví dụ:

- **Long** nếu hệ thống lưu ID người dùng dạng số.
- **UUID** nếu user ID là UUID.
- **String** nếu hệ thống dùng username hoặc mã tài khoản.

Phương thức **getCurrentAuditor()** trả về **Mono<T>** vì người dùng hiện tại được xác định trong reactive execution context. Publisher có thể phát một auditor hoặc hoàn tất rỗng nếu không có auditor.

ReactiveAuditorAware không tự xác thực người dùng, không tạo security context và không truy vấn user database một cách mặc định. Nó chỉ đọc danh tính đã có trong context hoặc từ một nguồn reactive mà ứng dụng chủ động cấu hình.

Luồng tổng quát:

~~~text
HTTP request
    |
    v
Spring Security WebFlux xác thực
    |
    v
Authentication trong Reactor Context
    |
    v
ReactiveAuditorAware.getCurrentAuditor()
    |
    v
Mono<AuditorId>
    |
    v
Spring Data auditing callback
    |
    +---- @CreatedBy
    |
    +---- @LastModifiedBy
    |
    v
R2DBC INSERT / UPDATE
~~~

## 3. Bật auditing cho Spring Data R2DBC

Khai báo **@EnableR2dbcAuditing** trong cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
public class R2dbcAuditingConfiguration {
}
~~~

Thuộc tính **auditorAwareRef** trỏ tới tên bean cung cấp auditor. Bean đó phải triển khai **ReactiveAuditorAware<T>**.

Nếu không khai báo auditorAwareRef, Spring có thể tìm bean ReactiveAuditorAware phù hợp theo cơ chế cấu hình của phiên bản đang dùng. Đặt tên rõ ràng giúp tránh mơ hồ khi ứng dụng có nhiều nguồn auditor hoặc nhiều cấu hình persistence.

Ví dụ cấu hình trên chỉ bật auditing. Ta vẫn cần khai báo bean **auditorProvider** để Spring biết ID người dùng hiện tại.

## 4. Lấy người dùng hiện tại từ Spring Security WebFlux

Trong Spring Security reactive, **ReactiveSecurityContextHolder** đọc **SecurityContext** từ Reactor Context. Ta có thể lấy Authentication, sau đó lấy principal và chuyển thành ID auditor.

Giả sử ứng dụng có principal riêng:

~~~java
public record AppUserPrincipal(
        Long id,
        String username) {
}
~~~

Bean ReactiveAuditorAware:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration
public class AuditorConfiguration {

    @Bean
    ReactiveAuditorAware<Long> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(authentication ->
                        authentication.isAuthenticated()
                                && !(authentication
                                        instanceof AnonymousAuthenticationToken))
                .map(Authentication::getPrincipal)
                .ofType(AppUserPrincipal.class)
                .map(AppUserPrincipal::id);
    }
}
~~~

Các bước thực hiện:

1. **ReactiveSecurityContextHolder.getContext()** lấy SecurityContext theo reactive context hiện tại.
2. **map(SecurityContext::getAuthentication)** lấy đối tượng Authentication.
3. **filter(...)** chỉ giữ authentication đã xác thực và loại anonymous token.
4. **map(Authentication::getPrincipal)** lấy principal.
5. **ofType(AppUserPrincipal.class)** chỉ nhận principal đúng kiểu mà ứng dụng mong đợi.
6. **map(AppUserPrincipal::id)** chuyển principal thành ID auditor.

Kết quả là **Mono<Long>**. Nếu không có SecurityContext, authentication chưa xác thực, principal là anonymous hoặc principal không phải AppUserPrincipal, publisher hoàn tất rỗng.

### 4.1. Vì sao cần loại AnonymousAuthenticationToken?

Trong Spring Security, anonymous authentication có thể có **isAuthenticated() == true**. Do đó chỉ kiểm tra:

~~~java
.filter(Authentication::isAuthenticated)
~~~

chưa đủ để khẳng định đây là người dùng đã đăng nhập. Một anonymous token có thể vượt qua điều kiện này.

Có thể loại rõ **AnonymousAuthenticationToken**, như ví dụ ở trên. Một lựa chọn khác là chỉ chấp nhận principal thuộc kiểu ứng dụng đã định nghĩa bằng **ofType(AppUserPrincipal.class)**. Dùng cả hai điều kiện giúp hợp đồng rõ ràng hơn.

Không nên ép principal thành kiểu cụ thể mà không kiểm tra. Principal có thể là chuỗi **anonymousUser**, một **UserDetails**, một **Jwt**, hoặc một lớp riêng do ứng dụng cung cấp.

## 5. Kiểu auditor phải khớp với kiểu trường entity

Nếu bean trả **Mono<Long>**, các trường **@CreatedBy** và **@LastModifiedBy** nên nhận kiểu Long hoặc kiểu có conversion được cấu hình rõ ràng.

Entity ví dụ:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    @CreatedBy
    @Column("created_by")
    private Long createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private Long lastModifiedBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;
}
~~~

Với entity này, auditor ID là **Long**. Nếu principal cung cấp UUID, có thể đổi bean thành **ReactiveAuditorAware<UUID>** và các trường auditor thành UUID, đồng thời schema database phải dùng kiểu tương ứng.

Không nên lưu username vào trường được thiết kế cho numeric user ID. Cũng không nên dựa vào conversion ngầm giữa các kiểu không tương thích.

### 5.1. Nên lưu ID ổn định thay vì tên hiển thị

Tên đăng nhập, email hoặc tên hiển thị có thể thay đổi. ID nội bộ ổn định thường phù hợp hơn cho các trường createdBy/lastModifiedBy.

Nếu cần hiển thị tên người tạo trong màn hình, có thể join hoặc truy vấn bảng user theo ID. Lịch sử auditing sẽ vẫn giữ nguyên danh tính kể cả khi người dùng đổi username.

Với hệ thống có yêu cầu lưu lịch sử sau khi tài khoản bị xóa, cần quyết định cách giữ auditor ID: soft delete, lưu snapshot tên hiển thị, hoặc dùng bảng danh tính lịch sử. Foreign key trực tiếp tới bảng user có thể khiến thao tác xóa user bị chặn hoặc làm mất khả năng giữ lịch sử theo thiết kế.

## 6. Cấu hình đầy đủ cho auditing ngày giờ

Auditing có thể tự điền cả người dùng và thời gian. Một cấu hình đầy đủ:

~~~java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorProvider",
        dateTimeProviderRef = "auditingDateTimeProvider",
        modifyOnCreate = true)
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<Long> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(authentication ->
                        authentication.isAuthenticated()
                                && !(authentication
                                        instanceof AnonymousAuthenticationToken))
                .map(Authentication::getPrincipal)
                .ofType(AppUserPrincipal.class)
                .map(AppUserPrincipal::id);
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }
}
~~~

Cấu hình này dùng **Clock** để tạo thời điểm hiện tại và cung cấp qua **DateTimeProvider**. Trong test có thể thay Clock bằng một clock cố định để kiểm tra giá trị thời gian một cách xác định.

**modifyOnCreate = true** yêu cầu các trường modified được cập nhật ngay khi tạo entity. Khi đó cả created và last modified time/auditor có thể được thiết lập trong lần insert đầu tiên. Nếu nghiệp vụ chỉ muốn điền trường modified sau lần cập nhật đầu tiên, cân nhắc cấu hình false và xác nhận hành vi với phiên bản Spring Data đang dùng.

Nếu không cần tùy chỉnh nguồn thời gian, có thể bỏ **dateTimeProviderRef** và để auditing sử dụng provider mặc định.

Imports cho ví dụ:

~~~java
import java.time.Clock;
import java.util.Optional;

import org.springframework.data.auditing.DateTimeProvider;
~~~

## 7. Auditing xảy ra ở đâu trong vòng đời lưu entity?

Spring Data Relational sử dụng entity callback để áp dụng auditing trong quá trình chuẩn bị entity cho persistence. Khi entity được lưu qua repository hoặc các API Spring Data hỗ trợ callback, auditing infrastructure có thể cập nhật các trường trước khi dữ liệu được ghi.

Luồng minh họa:

~~~text
repository.save(entity)
       |
       v
Xác định entity mới hay đã tồn tại
       |
       v
Auditing entity callback
       |
       +---- lấy auditor hiện tại
       |
       +---- lấy thời gian hiện tại
       |
       +---- gán Created/LastModified fields
       |
       v
Mapping entity thành SQL parameters
       |
       v
R2DBC driver thực thi INSERT / UPDATE
~~~

Về nguyên tắc:

- Khi tạo entity, Spring điền **@CreatedBy** và **@CreatedDate**.
- Khi cập nhật entity, Spring giữ thông tin tạo và cập nhật **@LastModifiedBy**, **@LastModifiedDate**.
- Với **modifyOnCreate = true**, các trường modified cũng được điền khi tạo.

Auditing không phải cơ chế database trigger. Nó là logic của Spring Data chạy trong quy trình persistence của Spring.

### 7.1. Entity phải được nhận diện đúng là mới hoặc cũ

Spring Data cần xác định thao tác là insert hay update. Việc nhận diện entity mới thường dựa vào ID và/hoặc trường version, hoặc cơ chế **Persistable.isNew()** nếu entity triển khai interface đó.

Nếu entity bị nhận diện sai trạng thái, các trường Created có thể không được áp dụng như mong muốn. Hãy kiểm tra chiến lược ID, version và lifecycle của entity.

Không tự gán ID trước khi insert nếu chiến lược mới/cũ của ứng dụng dựa vào ID null mà chưa cấu hình cơ chế nhận diện phù hợp.

## 8. Không có người dùng hiện tại: Mono.empty() có nghĩa gì?

ReactiveAuditorAware có thể trả về **Mono.empty()**. Điều này có nghĩa tại thời điểm lưu entity không có auditor nào được cung cấp.

Các trường **@CreatedBy** hoặc **@LastModifiedBy** khi đó không được gán auditor mới. Các trường thời gian vẫn có thể được điền nếu date auditing được bật.

Tình huống không có auditor có thể xảy ra khi:

- Request chưa đăng nhập hoặc được phép truy cập anonymous.
- Tác vụ chạy theo lịch.
- Consumer xử lý message nền không có security context.
- Migration hoặc batch job chạy ngoài request.
- Test không thiết lập SecurityContext.
- Một publisher bị tách khỏi reactive context có chứa Authentication.

Hành vi này phải phù hợp với schema và chính sách auditing. Nếu cột created_by là NOT NULL nhưng auditor có thể rỗng, insert sẽ thất bại do constraint.

Có ba hướng thiết kế thường gặp:

1. Cho phép auditor null nếu nghiệp vụ chấp nhận bản ghi không gắn với người dùng.
2. Cung cấp system actor rõ ràng cho những tác vụ nền được phép dùng danh tính hệ thống.
3. Từ chối thao tác nếu nghiệp vụ bắt buộc phải có người dùng và không có auditor hợp lệ.

Không nên tự động gán một user mặc định cho mọi trường hợp thiếu SecurityContext. Cách đó có thể khiến request chưa đăng nhập bị ghi nhận nhầm là thao tác của tài khoản hệ thống.

## 9. Cung cấp system auditor cho tác vụ nền

Tác vụ scheduler hoặc message consumer thường không có Authentication của người dùng. Nếu các bản ghi do job tạo bắt buộc phải có createdBy, cần xác định rõ danh tính của actor hệ thống.

Ví dụ có một ID dành riêng cho tài khoản hệ thống:

~~~java
private static final Long SYSTEM_AUDITOR_ID = 1L;
~~~

Có thể dùng fallback, nhưng chỉ khi ứng dụng đã xác định đây là execution context của tác vụ hệ thống. Không nên dùng fallback toàn cục cho tất cả request thiếu authentication.

Một cách rõ ràng hơn là cung cấp auditor qua Reactor Context cho các job:

~~~java
private static final String AUDITOR_ID_CONTEXT_KEY = "auditorId";

@Bean
ReactiveAuditorAware<Long> auditorProvider() {
    return () -> Mono.deferContextual(context ->
            Mono.justOrEmpty(
                    context.<Long>getOrEmpty(AUDITOR_ID_CONTEXT_KEY)));
}
~~~

Khi chạy job:

~~~java
Mono<Void> runImport(Long systemActorId) {
    return importService.importData()
            .then()
            .contextWrite(context ->
                    context.put(AUDITOR_ID_CONTEXT_KEY, systemActorId));
}
~~~

Trong ví dụ này, auditor được đưa vào context một cách tường minh. Key và kiểu dữ liệu phải được thống nhất trong ứng dụng. Chỉ job được phép mới thêm system actor vào context.

Nếu dùng cả Spring Security và custom context, cần xác định thứ tự ưu tiên. Ví dụ: ưu tiên authenticated user; nếu không có thì chỉ dùng system actor khi có cờ hoặc context marker xác nhận đây là tác vụ nền. Không dùng giá trị context do client tùy ý gửi lên làm auditor ID nếu chưa kiểm tra quyền.

## 10. Reactive Context và vì sao không dùng SecurityContextHolder

Trong ứng dụng imperative, Spring Security thường cung cấp SecurityContext qua ThreadLocal và có thể đọc bằng **SecurityContextHolder.getContext()**.

Trong WebFlux, một request có thể chuyển qua nhiều thread. ThreadLocal không phải cơ chế đáng tin cậy để giữ trạng thái request qua toàn bộ reactive pipeline. Spring Security reactive lưu context trong Reactor Context và cung cấp **ReactiveSecurityContextHolder** để đọc nó.

Không nên viết:

~~~java
@Bean
ReactiveAuditorAware<Long> auditorProvider() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return Mono.just(((AppUserPrincipal)
                authentication.getPrincipal()).id());
    };
}
~~~

Các vấn đề của cách này:

- Đọc ThreadLocal có thể không tìm thấy context trên thread hiện tại.
- Anonymous hoặc context rỗng có thể gây ClassCastException hoặc NullPointerException.
- Việc đọc principal diễn ra đồng bộ và không tôn trọng reactive context.
- Dễ làm sai danh tính khi request chuyển thread hoặc chạy scheduler.

Hãy dùng:

~~~java
ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication);
~~~

Reactor Context được truyền cùng subscription. Các operator như **publishOn** hoặc **subscribeOn** thay đổi thread thực thi nhưng không có nghĩa context bị mất theo cách ThreadLocal thường gặp. Tuy vậy, khi tự tạo subscription độc lập hoặc dùng thư viện không giữ reactive context, auditor có thể không còn nhìn thấy security context ban đầu.

## 11. Principal có thể là UserDetails, JWT hoặc kiểu riêng

Không phải ứng dụng nào cũng dùng **AppUserPrincipal**. Cần ánh xạ principal theo cơ chế xác thực thực tế.

### 11.1. Principal triển khai UserDetails

Nếu custom principal triển khai **UserDetails**, có thể lấy kiểu cụ thể:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getPrincipal)
        .ofType(AppUserDetails.class)
        .map(AppUserDetails::getUserId);
~~~

Vẫn cần loại anonymous authentication nếu cấu hình Security có anonymous access.

### 11.2. JWT resource server

Với JWT, principal thường là đối tượng **Jwt**. Có thể lấy subject hoặc claim chứa user ID:

~~~java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(authentication ->
                authentication.isAuthenticated()
                        && !(authentication
                                instanceof AnonymousAuthenticationToken))
        .map(Authentication::getPrincipal)
        .ofType(Jwt.class)
        .map(jwt -> jwt.getClaimAsString("user_id"))
        .filter(Objects::nonNull)
        .map(Long::valueOf);
~~~

Ví dụ này giả định claim **user_id** luôn là chuỗi biểu diễn số. Nếu claim có thể chứa UUID hoặc kiểu khác, cần chuyển đổi tương ứng và xử lý giá trị không hợp lệ.

Không nên mặc định **Authentication.getName()** luôn là ID database. Với JWT, getName có thể trả subject; với UserDetails, nó thường trả username. Hãy xác định contract của principal và kiểu dữ liệu auditor một cách rõ ràng.

## 12. Phân biệt auditor với tenant và người sở hữu dữ liệu

Auditor trả lời câu hỏi: **ai đã thực hiện thao tác?**

Tenant trả lời câu hỏi: **dữ liệu thuộc không gian/khách hàng nào?**

Owner trả lời câu hỏi: **ai sở hữu bản ghi theo nghiệp vụ?**

Ba khái niệm này có thể trùng một giá trị trong một use case nhưng không nên gộp làm một.

Ví dụ:

- Nhân viên hỗ trợ cập nhật đơn hàng của khách hàng.
- Auditor là ID nhân viên hỗ trợ.
- Owner/customer là ID khách hàng.
- Tenant là tổ chức mà đơn hàng thuộc về.

Nếu dùng customer ID làm auditor trong trường hợp trên, lịch sử sẽ không cho biết nhân viên nào thực sự sửa dữ liệu.

Có thể lưu cả ba trường riêng:

~~~java
@CreatedBy
@Column("created_by")
private Long createdBy;

@Column("customer_id")
private Long customerId;

@Column("tenant_id")
private Long tenantId;
~~~

Tenant và owner thường cần được lấy từ context/authorization riêng và phải được kiểm tra quyền truy cập. Không tin tenant ID hoặc auditor ID chỉ vì client gửi trong request body.

## 13. Những thao tác không tự chạy auditing callback

Auditing annotation không có nghĩa mọi câu SQL thay đổi dữ liệu đều tự động cập nhật các trường audit.

Các đường persistence như **repository.save(...)** hoặc API Spring Data entity/template có thể chạy entity callbacks theo cấu hình. Nhưng SQL cập nhật trực tiếp qua **DatabaseClient**, R2DBC SPI, stored procedure hoặc bulk modifying query không nhất thiết tạo và lưu entity qua auditing callback.

Ví dụ cập nhật trực tiếp:

~~~java
databaseClient.sql("""
        UPDATE purchase_order
        SET status = :status
        WHERE id = :id
        """)
        .bind("status", status.name())
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
~~~

Lệnh này không tự biết auditor hiện tại để gán **last_modified_by**. Nếu dùng cách truy vấn trực tiếp, hãy cập nhật trường audit trong SQL:

~~~java
databaseClient.sql("""
        UPDATE purchase_order
        SET status = :status,
            last_modified_by = :auditorId,
            last_modified_at = :modifiedAt
        WHERE id = :id
        """)
        .bind("status", status.name())
        .bind("auditorId", auditorId)
        .bind("modifiedAt", modifiedAt)
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
~~~

Hoặc dùng database trigger nếu chính sách auditing phải áp dụng cho mọi đường ghi, kể cả ứng dụng khác. Khi kết hợp trigger và Spring auditing, cần tránh hai nơi cùng ghi giá trị không thống nhất.

Với bulk update/delete, không giả định entity callback được gọi cho từng hàng. Kiểm tra contract của API và cập nhật audit metadata tường minh nếu cần.

## 14. Kiểu thời gian và nguồn thời gian

Các trường auditing ngày giờ có thể dùng những kiểu Java được Spring Data hỗ trợ, ví dụ **Instant**, **LocalDateTime** hoặc **OffsetDateTime**, tùy converter và database.

Chọn kiểu theo semantics:

| Kiểu | Ý nghĩa |
|---|---|
| **Instant** | Một thời điểm tuyệt đối trên timeline |
| **OffsetDateTime** | Thời điểm kèm UTC offset |
| **LocalDateTime** | Ngày giờ địa phương không mang timezone/offset |

Đối với hệ thống phân tán, **Instant** thường là lựa chọn rõ ràng cho created/modified timestamp. Database column nên được chọn với độ chính xác và timezone semantics phù hợp.

Dùng UTC cho timestamp giúp giảm nhầm lẫn khi service chạy ở nhiều timezone. Không dùng giờ máy client làm thời gian auditing; server hoặc database nên là nguồn thời gian có kiểm soát.

Custom **DateTimeProvider** và **Clock** giúp:

- Đồng bộ nguồn thời gian giữa các service.
- Kiểm thử timestamp xác định.
- Mô phỏng thời điểm trong quá khứ/tương lai cho test.
- Tránh phụ thuộc trực tiếp vào system clock trong entity/service.

## 15. Kiểm thử ReactiveAuditorAware độc lập

Có thể kiểm thử bean auditor bằng **StepVerifier** và đặt Authentication vào Reactor Context.

Ví dụ:

~~~java
@Test
void returnsAuthenticatedUserId() {
    AppUserPrincipal principal =
            new AppUserPrincipal(42L, "an");

    Authentication authentication =
            new UsernamePasswordAuthenticationToken(
                    principal,
                    "n/a",
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));

    StepVerifier.create(
            auditorProvider.getCurrentAuditor()
                    .contextWrite(
                            ReactiveSecurityContextHolder
                                    .withAuthentication(authentication)))
            .expectNext(42L)
            .verifyComplete();
}
~~~

Test này xác nhận auditor đọc được ID từ reactive security context.

### 15.1. Kiểm thử khi không có context

~~~java
@Test
void returnsEmptyWhenNoSecurityContextExists() {
    StepVerifier.create(auditorProvider.getCurrentAuditor())
            .verifyComplete();
}
~~~

Đây là hành vi hợp lệ nếu ứng dụng cho phép tác vụ không có người dùng hoặc đã có chính sách xử lý riêng cho trường hợp đó.

### 15.2. Kiểm thử anonymous authentication

~~~java
@Test
void doesNotUseAnonymousUserAsAuditor() {
    Authentication anonymous =
            new AnonymousAuthenticationToken(
                    "key",
                    "anonymousUser",
                    List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

    StepVerifier.create(
            auditorProvider.getCurrentAuditor()
                    .contextWrite(
                            ReactiveSecurityContextHolder
                                    .withAuthentication(anonymous)))
            .verifyComplete();
}
~~~

Test này giúp bảo đảm auditor không nhận chuỗi **anonymousUser** hoặc một principal không đại diện người dùng đã xác thực.

## 16. Kiểm thử auditing khi lưu entity

Test bean độc lập chưa chứng minh entity callback và database mapping cùng hoạt động. Nên có integration test dùng repository thật và database/driver mục tiêu.

Một kịch bản:

1. Tạo Authentication cho user ID 42.
2. Đưa Authentication vào Reactor Context.
3. Gọi repository.save(entity mới).
4. Đọc entity đã lưu.
5. Xác nhận createdBy là 42.
6. Xác nhận createdDate có giá trị.
7. Cập nhật entity trong context của user ID 57.
8. Xác nhận createdBy vẫn là 42 và lastModifiedBy là 57.
9. Xác nhận lastModifiedDate được cập nhật.

Ví dụ kiểm tra publisher:

~~~java
StepVerifier.create(
        orderRepository.save(newOrder)
                .contextWrite(
                        ReactiveSecurityContextHolder
                                .withAuthentication(authenticationForUser42)))
        .assertNext(saved -> {
            assertThat(saved.getCreatedBy()).isEqualTo(42L);
            assertThat(saved.getCreatedDate()).isNotNull();
            assertThat(saved.getLastModifiedBy()).isEqualTo(42L);
        })
        .verifyComplete();
~~~

Nếu dùng **modifyOnCreate = false**, điều chỉnh kỳ vọng cho các trường modified khi insert. Nếu cột auditor cho phép null và context không có Authentication, test cần xác nhận hành vi đó đúng với schema và chính sách.

Với Clock cố định, có thể xác nhận timestamp chính xác thay vì chỉ kiểm tra not null.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Không bật **@EnableR2dbcAuditing** | Annotation auditing không được áp dụng | Bật auditing trong cấu hình |
| Không đăng ký ReactiveAuditorAware bean hoặc sai bean ref | Spring không lấy được auditor | Khai báo bean và kiểm tra auditorAwareRef |
| Dùng **SecurityContextHolder** trong WebFlux | Không đọc được context ổn định qua các thread | Dùng ReactiveSecurityContextHolder |
| Chỉ kiểm tra **isAuthenticated()** | Anonymous token có thể được xem là authenticated | Loại AnonymousAuthenticationToken và kiểm tra principal |
| Ép principal sang kiểu không chắc chắn | ClassCastException hoặc lỗi khi có JWT/anonymous | Dùng ofType và mapping theo principal thực tế |
| Bean trả **Mono<UUID>** nhưng field là Long | Mapping auditor không tương thích | Thống nhất generic type và kiểu cột |
| Không có context nhưng cột created_by là NOT NULL | Insert thất bại do constraint | Cung cấp actor hợp lệ hoặc thiết kế chính sách null/system actor |
| Gán system user cho mọi request thiếu authentication | Audit ghi nhận sai người thực hiện | Chỉ dùng system auditor trong execution context đã xác định |
| Gọi subscribe() tách rời trong service | Reactive security context có thể bị mất | Nối publisher trong cùng chain |
| Dùng auditor như tenant hoặc owner | Lịch sử và quyền sở hữu bị nhầm | Lưu actor, tenant và owner riêng |
| Dùng DatabaseClient raw SQL nhưng mong callback tự chạy | Trường lastModified không được cập nhật | Gán audit field trong SQL hoặc dùng callback phù hợp |
| Không kiểm tra entity new/existing | Created/modified fields được áp dụng sai | Kiểm tra ID, version và isNew strategy |
| Lưu username thay vì ID ổn định | Lịch sử bị ảnh hưởng khi username đổi | Ưu tiên immutable user ID |
| Không kiểm thử anonymous/job context | Tác vụ nền ghi auditor null hoặc sai | Kiểm thử từng execution context |

## 18. Quy trình triển khai ReactiveAuditorAware

Khi tích hợp auditing với người dùng hiện tại, hãy đi theo trình tự:

1. Xác định kiểu định danh người dùng ổn định mà database sẽ lưu.
2. Đánh dấu entity fields bằng **@CreatedBy**, **@LastModifiedBy** và các annotation thời gian cần thiết.
3. Bật **@EnableR2dbcAuditing** và trỏ tới bean auditor.
4. Triển khai **ReactiveAuditorAware<T>** với kiểu generic khớp field entity.
5. Nếu dùng WebFlux/Spring Security, đọc Authentication bằng **ReactiveSecurityContextHolder**.
6. Loại anonymous authentication và kiểm tra kiểu principal trước khi lấy ID.
7. Quyết định hành vi khi không có auditor: cho phép null, system actor có điều kiện hoặc từ chối thao tác.
8. Cấu hình **DateTimeProvider** nếu cần kiểm soát nguồn thời gian.
9. Xác nhận repository/entity callback thực sự chạy trên đường persistence đang dùng.
10. Với raw SQL hoặc bulk update, cập nhật audit fields tường minh hoặc dùng database trigger.
11. Kiểm thử authenticated user, anonymous, không có context, system job, insert và update.
12. Kiểm thử trên đúng R2DBC driver/database để xác nhận schema và kiểu dữ liệu.

## 19. Ghi nhớ

- **ReactiveAuditorAware<T>** cung cấp auditor hiện tại qua **Mono<T>**.
- **@EnableR2dbcAuditing** bật auditing và **auditorAwareRef** trỏ tới bean cung cấp người dùng.
- Trong WebFlux, đọc người dùng bằng **ReactiveSecurityContextHolder**, vì SecurityContext được truyền qua Reactor Context.
- Không dùng **SecurityContextHolder** kiểu imperative hoặc **block()** trong reactive pipeline.
- Chỉ kiểm tra **isAuthenticated()** là chưa đủ vì anonymous token có thể được đánh dấu authenticated.
- Kiểm tra principal đúng kiểu trước khi lấy user ID; không giả định mọi Authentication đều có cùng principal.
- Generic type của ReactiveAuditorAware phải khớp kiểu **@CreatedBy** và **@LastModifiedBy**.
- **Mono.empty()** có nghĩa không có auditor; các trường auditor có thể không được gán và schema phải cho phép hoặc ứng dụng phải có chính sách khác.
- Tác vụ nền có thể cần system actor, nhưng chỉ gán khi execution context được xác định rõ.
- Auditor, tenant và owner là ba khái niệm khác nhau.
- Auditing callback hoạt động trên đường persistence Spring Data hỗ trợ; raw SQL, bulk query và SPI trực tiếp cần cập nhật audit metadata riêng.
- Kiểm thử cả auditor bean lẫn repository integration, gồm tạo mới, cập nhật, anonymous và job không có security context.

