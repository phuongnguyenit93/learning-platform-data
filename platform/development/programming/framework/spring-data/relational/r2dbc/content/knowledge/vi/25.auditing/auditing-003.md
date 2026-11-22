# Ánh xạ người tạo và người cập nhật

Trong ứng dụng Spring Data R2DBC, nhiều bảng cần lưu lại ai đã tạo một bản ghi và ai là người sửa bản ghi gần nhất. Ngoài thông tin người thực hiện, hệ thống thường cần thời điểm tạo và thời điểm cập nhật để hiển thị lịch sử, hỗ trợ điều tra sự cố hoặc phục vụ quy trình vận hành.

Spring Data cung cấp cơ chế auditing để tự động điền các thuộc tính này trong vòng đời lưu entity. Các annotation như `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate` và `@LastModifiedDate` mô tả metadata cần lưu; `@EnableR2dbcAuditing` bật cơ chế auditing cho R2DBC; `ReactiveAuditorAware<T>` cung cấp người dùng hiện tại theo cách reactive.

Auditing giúp tránh việc mỗi Service tự gán `createdBy`, `updatedBy` hoặc timestamp theo những quy tắc khác nhau. Tuy nhiên, ứng dụng vẫn phải xác định nguồn danh tính đáng tin cậy, xử lý request không có người dùng đăng nhập, cung cấp schema tương ứng và hiểu rằng các câu SQL ghi trực tiếp không tự động chạy entity auditing callback.

## 1. Thông tin auditing của một entity

Một bản ghi thường có bốn thuộc tính metadata:

| Annotation | Ý nghĩa | Khi nào được gán |
|---|---|---|
| `@CreatedBy` | Người tạo bản ghi | Khi entity được insert lần đầu |
| `@CreatedDate` | Thời điểm tạo bản ghi | Khi entity được insert lần đầu |
| `@LastModifiedBy` | Người cập nhật gần nhất | Khi insert và khi entity được cập nhật, tùy cấu hình `modifyOnCreate` |
| `@LastModifiedDate` | Thời điểm cập nhật gần nhất | Khi insert và khi entity được cập nhật, tùy cấu hình `modifyOnCreate` |

Ví dụ, một bản ghi khách hàng có thể được lưu như sau:

```text
id              = 42
email           = "an@example.com"
created_by      = 1008
created_date    = 2026-10-01T08:30:00Z
last_modified_by   = 1012
last_modified_date = 2026-10-05T14:12:00Z
```

Người tạo vẫn là user `1008`, trong khi người cập nhật gần nhất là user `1012`. Khi bản ghi được cập nhật lần nữa, `createdBy` và `createdDate` được giữ nguyên; `lastModifiedBy` và `lastModifiedDate` được cập nhật theo người thực hiện và thời điểm mới.

### 1.1. Auditing không phải nhật ký đầy đủ mọi thay đổi

Các thuộc tính `created...` và `lastModified...` chỉ lưu metadata tạo và cập nhật gần nhất. Chúng không lưu toàn bộ lịch sử thay đổi, giá trị trước/sau, lý do sửa hoặc mọi người từng chỉnh sửa.

Nếu nghiệp vụ cần lịch sử đầy đủ, hãy thiết kế bảng audit riêng, event log hoặc cơ chế temporal/history phù hợp. Không dùng `@LastModifiedBy` như một hệ thống audit trail append-only.

### 1.2. Danh tính người thực hiện phải đến từ nguồn đáng tin cậy

Không lấy `createdBy` hoặc `lastModifiedBy` từ request body rồi gán trực tiếp vào entity. Client có thể gửi ID của người khác. Auditor cần được lấy từ security context đã xác thực hoặc một ngữ cảnh hệ thống đáng tin cậy do ứng dụng thiết lập.

## 2. Khai báo auditing metadata trong entity

Ví dụ entity khách hàng:

```java
package com.example.store.customer.persistence;

import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record CustomerEntity(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @CreatedBy @Column("created_by") Long createdBy,
        @LastModifiedBy @Column("last_modified_by") Long lastModifiedBy,
        @CreatedDate @Column("created_date") Instant createdDate,
        @LastModifiedDate @Column("last_modified_date") Instant lastModifiedDate
) {
}
```

Trong ví dụ:

- `@CreatedBy` và `@LastModifiedBy` đánh dấu các thuộc tính lưu ID của actor.
- `@CreatedDate` và `@LastModifiedDate` đánh dấu các thuộc tính thời gian.
- `@Column` ánh xạ tên property Java sang tên cột cụ thể.
- `Instant` biểu diễn một thời điểm tuyệt đối, phù hợp khi hệ thống cần timestamp nhất quán giữa các múi giờ.

Kiểu của thuộc tính auditor phải tương thích với kiểu mà `ReactiveAuditorAware<T>` phát ra. Ở đây cả hai đều dùng `Long`. Nếu ứng dụng lưu username, UUID hoặc một kiểu ID khác, hãy dùng cùng kiểu đó cho provider và các thuộc tính auditing.

### 2.1. Có thể dùng class mutable

Nếu entity là class thông thường, có thể khai báo các trường auditing và getter/setter tương ứng. Spring Data sẽ cập nhật metadata thông qua cơ chế truy cập thuộc tính của entity. Với entity bất biến như record hoặc class có trường `final`, mapping infrastructure cần tạo instance mới khi thay đổi giá trị; record là một lựa chọn gọn nếu constructor thể hiện đầy đủ trạng thái.

Không thêm setter công khai chỉ để auditing hoạt động nếu mô hình đã dùng constructor mapping và cơ chế truy cập bất biến của Spring Data. Hãy kiểm thử insert/update trên phiên bản Spring Data thực tế của dự án.

## 3. Bật R2DBC auditing

Để Spring Data R2DBC tự động áp dụng các annotation auditing, bật cấu hình bằng `@EnableR2dbcAuditing`.

```java
package com.example.store.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorProvider")
public class R2dbcAuditingConfiguration {
}
```

`@EnableR2dbcAuditing` đăng ký hạ tầng auditing cho Spring Data R2DBC, bao gồm callback cần thiết để điền metadata trong vòng đời lưu entity. `auditorAwareRef` chỉ rõ bean cung cấp auditor hiện tại. Nếu ứng dụng chỉ có một bean `ReactiveAuditorAware` phù hợp, có thể để Spring tự chọn theo cấu hình; khai báo tên rõ ràng giúp tránh mơ hồ khi có nhiều provider.

Các tùy chọn thường dùng:

- `auditorAwareRef`: tên bean cung cấp người tạo/người cập nhật.
- `dateTimeProviderRef`: tên bean cung cấp thời gian hiện tại nếu muốn tùy chỉnh nguồn clock.
- `setDates`: bật/tắt việc điền các thuộc tính thời gian.
- `modifyOnCreate`: quyết định các trường `LastModified...` có được gán ngay khi insert hay không.

Mặc định, auditing thường tự điền các trường ngày và coi lần tạo cũng là lần sửa đầu tiên. Nếu đặt `modifyOnCreate = false`, các thuộc tính `LastModifiedBy`/`LastModifiedDate` không được gán trong lần tạo theo cấu hình đó. Chỉ thay đổi mặc định khi hợp đồng dữ liệu yêu cầu rõ ràng.

## 4. Cung cấp người dùng hiện tại bằng ReactiveAuditorAware

Trong R2DBC, thao tác truy cập dữ liệu là reactive. Người thực hiện cần được cung cấp bằng `ReactiveAuditorAware<T>`, trả về `Mono<T>`, thay vì dùng một provider đồng bộ có thể dựa trên ThreadLocal.

### 4.1. Interface ReactiveAuditorAware

`ReactiveAuditorAware<T>` nằm trong Spring Data Commons và có phương thức lấy auditor hiện tại dưới dạng `Mono<T>`. Khi có người dùng hợp lệ, provider phát ra ID hoặc đối tượng auditor; khi không có auditor, provider có thể hoàn tất rỗng.

Ví dụ ứng dụng dùng Spring Security WebFlux và principal chứa ID người dùng:

```java
package com.example.store.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

@Configuration
public class AuditorConfiguration {

    @Bean
    ReactiveAuditorAware<Long> auditorProvider() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getPrincipal)
                .filter(AppPrincipal.class::isInstance)
                .cast(AppPrincipal.class)
                .map(AppPrincipal::userId);
    }
}
```

`AppPrincipal` là kiểu principal của ứng dụng, ví dụ:

```java
public record AppPrincipal(Long userId, String username) {
}
```

Luồng xử lý:

1. `ReactiveSecurityContextHolder.getContext()` lấy security context từ Reactor Context.
2. Lấy `Authentication` hiện tại.
3. Chỉ chấp nhận authentication đã xác thực và loại bỏ anonymous authentication.
4. Lấy principal, kiểm tra đúng kiểu `AppPrincipal`.
5. Trả về `userId` làm auditor.

Trong ứng dụng thật, principal có thể là `UserDetails`, `Jwt`, `JwtAuthenticationToken` hoặc kiểu tùy chỉnh. Hãy ánh xạ từ principal thực tế của hệ thống sang ID actor. Không giả định mọi authentication đều có cùng kiểu principal.

### 4.2. Vì sao dùng ReactiveSecurityContextHolder?

Trong WebFlux, execution có thể chuyển qua nhiều thread. Thread hiện tại không đại diện ổn định cho request. `ReactiveSecurityContextHolder` đọc security context từ Reactor Context nên phù hợp với pipeline reactive.

Không dùng `SecurityContextHolder.getContext()` dựa trên ThreadLocal như nguồn mặc định cho reactive auditing. Cách đó có thể trả sai hoặc không có người dùng khi execution chuyển thread, trừ khi ứng dụng có cơ chế context propagation riêng được cấu hình rõ ràng.

### 4.3. Không có authentication thì sao?

`ReactiveAuditorAware` có thể trả `Mono.empty()` nếu không tìm thấy người dùng đã xác thực. Khi đó, auditing vẫn có thể điền thời gian, nhưng trường auditor không có giá trị mới để gán. Cách xử lý phụ thuộc schema và chính sách của ứng dụng:

- Cho phép `created_by`/`last_modified_by` null đối với thao tác không có người dùng.
- Yêu cầu mọi thao tác phải có actor và từ chối ghi nếu không có danh tính.
- Dùng một system actor rõ ràng cho tác vụ nền, migration hoặc job nội bộ.

Không tự động dùng ID người dùng mặc định cho mọi request anonymous. Điều đó có thể làm sai lịch sử kiểm toán và che giấu việc request chưa được xác thực.

### 4.4. Tác vụ nền và system actor

Scheduler, message consumer hoặc batch job có thể chạy ngoài HTTP security context. Nếu nghiệp vụ yêu cầu mọi bản ghi đều có `createdBy`/`lastModifiedBy`, hãy xác định actor hệ thống riêng và áp dụng trong ngữ cảnh tác vụ nền.

Ví dụ, một job có thể chạy trong một profile hoặc luồng điều phối riêng với auditor `SYSTEM_ACTOR_ID`. Chỉ dùng fallback hệ thống ở nơi đã xác định chắc chắn đó là công việc nội bộ. Không đặt `switchIfEmpty(Mono.just(SYSTEM_ACTOR_ID))` một cách toàn cục nếu điều đó cũng biến request không xác thực thành thao tác của system.

Nếu cần phân biệt nhiều loại actor, có thể lưu một kiểu định danh rộng hơn như `actor_type` cùng `actor_id`, hoặc dùng value object/enum có quy ước rõ ràng. Đừng dùng một số ID giả trùng với ID người dùng thật.

## 5. Ánh xạ thời điểm tạo và cập nhật

### 5.1. Dùng Instant cho thời điểm tuyệt đối

`Instant` biểu diễn thời điểm trên trục thời gian UTC. Nó phù hợp cho `createdDate` và `lastModifiedDate` khi nhiều service, người dùng hoặc hệ thống ở các múi giờ khác nhau.

Các kiểu thời gian khác như `LocalDateTime`, `OffsetDateTime` hoặc `java.util.Date` cũng có thể được hỗ trợ tùy mapping và database. Tuy nhiên, `LocalDateTime` không mang thông tin múi giờ/offset; nếu dùng, cần quy định rõ cách lưu và diễn giải. Không trộn lẫn timestamp local và UTC trong cùng một cột mà không có quy ước.

### 5.2. Dùng DateTimeProvider khi cần kiểm soát clock

Mặc định auditing lấy thời gian hiện tại từ provider của Spring Data. Nếu muốn thống nhất nguồn clock hoặc kiểm thử với thời điểm cố định, có thể cung cấp `DateTimeProvider` riêng.

```java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorProvider",
        dateTimeProviderRef = "auditingDateTimeProvider")
public class R2dbcAuditingConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(auditingClock.instant());
    }
}
```

`DateTimeProvider` trả về một `TemporalAccessor` trong `Optional`. Dùng `Clock` giúp kiểm thử có thể thay clock thật bằng clock cố định. Khi cấu hình cả `auditorAwareRef` và `dateTimeProviderRef`, bảo đảm hai bean có tên đúng với tham chiếu trong annotation.

Trong ví dụ hoàn chỉnh, bean `ReactiveAuditorAware<Long>` `auditorProvider` vẫn được khai báo như phần trước. Có thể gộp các bean vào cùng một lớp `@Configuration` nếu phù hợp với cấu trúc dự án.

### 5.3. Schema cột thời gian

Ví dụ PostgreSQL:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    created_by BIGINT,
    last_modified_by BIGINT,
    created_date TIMESTAMPTZ,
    last_modified_date TIMESTAMPTZ
);
```

`TIMESTAMPTZ` lưu một thời điểm có ngữ nghĩa timezone-aware của PostgreSQL. Quy tắc chuyển đổi Java/database cần được xác nhận theo driver và phiên bản đang dùng. Với database khác, chọn kiểu cột tương ứng và quy định timezone rõ ràng.

Nếu auditing bắt buộc cho mọi bản ghi, có thể đặt `NOT NULL` cho cột tương ứng sau khi migration đã backfill dữ liệu cũ và provider luôn trả auditor hợp lệ. Nếu một số tác vụ không có người dùng, hãy quyết định rõ có dùng system actor hay cho phép null trước khi áp dụng constraint.

### 5.4. Migration cho bảng đã tồn tại

Khi bổ sung auditing cho bảng đang có dữ liệu, không nên thêm ngay cột `NOT NULL` mà chưa có giá trị cho các hàng cũ. Một quy trình migration có thể là:

1. Thêm các cột auditing cho phép null hoặc có default phù hợp.
2. Backfill `created_date` cho dữ liệu cũ bằng timestamp có ý nghĩa đã biết; nếu không có nguồn chính xác, ghi nhận rõ đó là thời điểm migration hoặc một mốc không xác định theo chính sách dữ liệu.
3. Backfill `created_by`/`last_modified_by` bằng actor migration/system nếu chính sách yêu cầu.
4. Kiểm tra các hàng hiện tại.
5. Chỉ đặt `NOT NULL` khi mọi đường ghi đều cung cấp giá trị.

Không gán một người dùng giả làm người tạo cho dữ liệu cũ nếu không có bằng chứng. Nếu không biết actor ban đầu, giữ null hoặc dùng một giá trị sentinel được định nghĩa và tài liệu hóa rõ.

## 6. Auditing trong vòng đời lưu entity R2DBC

Khi bật `@EnableR2dbcAuditing`, Spring Data đăng ký callback auditing để điền metadata vào entity trong vòng đời lưu. Repository và `R2dbcEntityTemplate` sử dụng mapping infrastructure của Spring Data, vì vậy các annotation auditing được áp dụng trong những thao tác entity tương ứng.

Luồng khái quát:

```text
Repository.save(entity)
        |
        v
Spring Data R2DBC mapping pipeline
        |
        v
Auditing entity callback
        |
        +--> xác định entity mới hay đã tồn tại
        +--> lấy auditor từ ReactiveAuditorAware
        +--> lấy thời gian từ DateTimeProvider
        +--> gán Created... / LastModified...
        |
        v
Convert entity và thực thi SQL
        |
        v
Database
```

### 6.1. Khi insert

Với cấu hình mặc định cho phép gán ngày và `modifyOnCreate`, lần insert có thể điền:

- `createdBy` từ auditor hiện tại.
- `createdDate` từ date/time provider.
- `lastModifiedBy` từ auditor hiện tại.
- `lastModifiedDate` từ date/time provider.

`modifyOnCreate` có thể được đặt thành `false` nếu ứng dụng muốn trường `LastModified...` chỉ xuất hiện sau lần cập nhật đầu tiên. Hãy thống nhất quy tắc này với schema và API.

### 6.2. Khi update

Khi một entity đã tồn tại được lưu qua đường persistence có auditing callback:

- `createdBy` được giữ nguyên.
- `createdDate` được giữ nguyên.
- `lastModifiedBy` được cập nhật theo auditor hiện tại nếu có.
- `lastModifiedDate` được cập nhật theo date/time provider.

Không lấy các trường audit từ request để ghi đè metadata hiện có. Hãy để callback quản lý các trường này.

### 6.3. Entity bất biến

Với record hoặc class bất biến, callback cần trả về trạng thái entity đã được cập nhật metadata thông qua cơ chế accessor/mapping của Spring Data. Record constructor hoặc wither phù hợp giúp framework tạo instance mới chứa các giá trị audit. Không giả định object đầu vào sẽ bị thay đổi tại chỗ; hãy dùng entity trả về từ `save` khi cần đọc metadata mới.

Ví dụ:

```java
return customerRepository.save(customer)
        .map(saved -> {
            // saved có createdBy, createdDate và version/metadata sau khi lưu.
            return saved;
        });
```

## 7. Những đường ghi không tự động chạy auditing callback

Auditing của Spring Data R2DBC gắn với entity mapping lifecycle. Không phải mọi câu lệnh SQL được chạy trong ứng dụng đều đi qua lifecycle đó.

### 7.1. DatabaseClient và SQL trực tiếp

Ví dụ:

```java
databaseClient.sql("""
        UPDATE customers
        SET display_name = :displayName
        WHERE id = :id
        """)
    .bind("displayName", displayName)
    .bind("id", id)
    .fetch()
    .rowsUpdated();
```

Đây là câu SQL trực tiếp. Nó không materialize entity rồi gọi auditing callback; do đó `lastModifiedBy` và `lastModifiedDate` không tự được cập nhật chỉ vì đã bật `@EnableR2dbcAuditing`.

Nếu đường ghi trực tiếp cần auditing, hãy đưa các giá trị vào SQL một cách tường minh:

```sql
UPDATE customers
SET display_name = :displayName,
    last_modified_by = :actorId,
    last_modified_date = :modifiedAt
WHERE id = :id
```

Các giá trị `actorId` và `modifiedAt` phải đến từ context đáng tin cậy của ứng dụng. Dùng bind parameter; không nối dữ liệu vào chuỗi SQL.

### 7.2. Modifying query trong Repository

Một câu `@Query` thực hiện update/delete trực tiếp cũng không nên được giả định là chạy đầy đủ entity auditing callback như `save(entity)`. Nếu dùng modifying query, hãy kiểm tra hành vi của phiên bản Spring Data đang dùng và tự quản lý audit columns trong câu SQL nếu cần.

### 7.3. Database trigger

Nếu nhiều ứng dụng hoặc công cụ ngoài Spring Data cùng ghi vào bảng, auditing callback của một ứng dụng không thể quan sát các lần ghi đó. Có thể dùng database trigger hoặc một cơ chế audit ở database để bao phủ mọi writer.

Không nên đồng thời để cả callback và trigger ghi cùng một cột theo hai quy tắc thời gian khác nhau mà không có chủ sở hữu rõ ràng. Chọn một nguồn chính cho mỗi trường audit để tránh giá trị bị ghi đè khó dự đoán.

## 8. Tách auditing metadata khỏi API model

Các trường `createdBy`, `lastModifiedBy`, `createdDate` và `lastModifiedDate` là metadata do server quản lý. Request tạo hoặc cập nhật không nên cho client tự quyết định các giá trị này.

Ví dụ request:

```java
public record UpdateCustomerRequest(
        String displayName
) {
}
```

Response có thể công khai một phần metadata theo hợp đồng API:

```java
public record CustomerResponse(
        Long id,
        String email,
        String displayName,
        Long createdBy,
        Long lastModifiedBy,
        Instant createdDate,
        Instant lastModifiedDate
) {
}
```

Tầng Service map entity sang response. Không bind request trực tiếp vào entity có trường audit vì client có thể gửi thêm `createdBy`, `createdDate` hoặc các trường nội bộ khác nếu cơ chế binding cho phép.

Nếu không muốn lộ ID người dùng nội bộ, response có thể chỉ trả timestamp hoặc tên hiển thị đã được phép công khai. Việc có trả metadata hay không là quyết định của hợp đồng API và chính sách quyền truy cập.

## 9. Auditing và thời điểm thực hiện nghiệp vụ

`@LastModifiedDate` phản ánh thời điểm entity được cập nhật qua persistence lifecycle. Nó không nhất thiết là thời điểm một nghiệp vụ cụ thể bắt đầu, được phê duyệt hoặc hoàn tất.

Ví dụ đơn hàng có thể được sửa metadata nhiều lần do cập nhật ghi chú, trong khi thời điểm thanh toán cần lưu riêng là `paidAt`. Không dùng `lastModifiedDate` để thay thế các timestamp nghiệp vụ như:

- `submittedAt` — thời điểm gửi đơn.
- `approvedAt` — thời điểm phê duyệt.
- `paidAt` — thời điểm thanh toán.
- `cancelledAt` — thời điểm hủy.
- `shippedAt` — thời điểm giao cho đơn vị vận chuyển.

Những trường này nên được gán trong hành vi nghiệp vụ tương ứng. Auditing metadata cung cấp dấu thời gian chung cho lần tạo và lần sửa cuối cùng của entity.

## 10. Kiểm thử auditing

Kiểm thử nên xác nhận cả cấu hình provider lẫn kết quả thực tế sau insert/update. Mock `ReactiveAuditorAware` có thể giúp kiểm tra Service, nhưng integration test cần xác nhận callback được đăng ký và cột database được ghi đúng.

### 10.1. Kiểm thử ReactiveAuditorAware

Có thể kiểm tra provider trả đúng actor khi Reactor Security Context có authentication. Ví dụ dùng principal giả trong test:

```java
AppPrincipal principal = new AppPrincipal(1008L, "an");
Authentication authentication =
        new UsernamePasswordAuthenticationToken(principal, "n/a");
SecurityContext context = new SecurityContextImpl(authentication);

StepVerifier.create(auditorProvider.getCurrentAuditor()
        .contextWrite(ReactiveSecurityContextHolder.withSecurityContext(
                Mono.just(context))))
        .expectNext(1008L)
        .verifyComplete();
```

Ví dụ minh họa cách đặt security context vào Reactor Context. Trong test thực tế, cần dùng constructor authentication phù hợp và principal đúng kiểu ứng dụng.

### 10.2. Kiểm thử insert

Với `@DataR2dbcTest` hoặc integration test có `ConnectionFactory` thật, thực hiện insert qua repository rồi kiểm tra:

- ID được sinh đúng.
- `createdBy` và `lastModifiedBy` bằng auditor test.
- `createdDate` và `lastModifiedDate` có giá trị.
- Giá trị cột trong database khớp entity trả về.

Có thể dùng `StepVerifier` để kiểm tra publisher:

```java
StepVerifier.create(repository.save(newCustomer))
        .assertNext(saved -> {
            assertThat(saved.createdBy()).isEqualTo(1008L);
            assertThat(saved.lastModifiedBy()).isEqualTo(1008L);
            assertThat(saved.createdDate()).isNotNull();
            assertThat(saved.lastModifiedDate()).isNotNull();
        })
        .verifyComplete();
```

### 10.3. Kiểm thử update

Sau insert, thay đổi một thuộc tính nghiệp vụ rồi gọi `save`:

```java
StepVerifier.create(repository.findById(id)
        .flatMap(current -> repository.save(current.withDisplayName("Anh An"))))
        .assertNext(saved -> {
            assertThat(saved.createdBy()).isEqualTo(originalCreatedBy);
            assertThat(saved.createdDate()).isEqualTo(originalCreatedDate);
            assertThat(saved.lastModifiedBy()).isEqualTo(1012L);
            assertThat(saved.lastModifiedDate())
                    .isAfterOrEqualTo(originalLastModifiedDate);
        })
        .verifyComplete();
```

Ví dụ giả định entity có phương thức `withDisplayName` trả về instance mới và test context cung cấp auditor `1012`. Nếu dùng clock cố định, có thể so sánh timestamp chính xác thay vì chỉ kiểm tra không nhỏ hơn.

### 10.4. Kiểm thử không có auditor

Kiểm tra trường hợp security context rỗng, anonymous hoặc principal không đúng kiểu. Xác định rõ ứng dụng cho phép audit actor null hay yêu cầu system actor. Test cần phản ánh đúng chính sách đã chọn, không để hành vi mặc định ngoài ý muốn.

### 10.5. Kiểm thử đường SQL trực tiếp

Nếu có `DatabaseClient` hoặc modifying query, kiểm tra rằng audit columns được cập nhật tường minh hoặc trigger database thực hiện đúng quy tắc. Không kỳ vọng callback tự chạy trong đường SQL trực tiếp.

### 10.6. Kiểm thử clock

Nếu dùng `DateTimeProvider` tùy chỉnh, inject `Clock` để test có thể dùng thời điểm cố định:

```java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-10-05T14:12:00Z"),
        ZoneOffset.UTC);
```

Nhờ vậy test không phụ thuộc thời gian hệ thống và có thể xác nhận chính xác giá trị được lưu.

## 11. Lỗi thường gặp

### Chỉ thêm annotation mà quên bật auditing

Nếu không bật `@EnableR2dbcAuditing`, callback auditing không được đăng ký theo cấu hình đó. Kiểm tra cấu hình Spring và bean provider.

### Dùng AuditorAware đồng bộ trong R2DBC

R2DBC cần `ReactiveAuditorAware<T>` để lấy auditor theo reactive context. Dùng provider đồng bộ dựa trên ThreadLocal có thể không nhìn thấy security context khi execution chuyển thread.

### Dùng sai kiểu auditor

Nếu provider phát `Long` nhưng thuộc tính `@CreatedBy` là `String`, mapping có thể thất bại hoặc conversion không như mong muốn. Giữ kiểu generic của provider và kiểu thuộc tính audit nhất quán.

### Chấp nhận anonymous authentication như người dùng thật

Một số hệ thống đánh dấu anonymous authentication là authenticated theo API của Spring Security. Chỉ kiểm tra `isAuthenticated()` có thể chưa đủ; loại bỏ anonymous token hoặc xác định rõ principal hợp lệ.

### Dùng system actor mặc định cho mọi request

Fallback global có thể ghi sai rằng request chưa xác thực là tác vụ hệ thống. Chỉ dùng system actor trong ngữ cảnh job/service nội bộ được xác định rõ.

### Cho client gửi createdBy hoặc lastModifiedBy

Đây là metadata do server quản lý. Lấy actor từ security context hoặc system context, không tin giá trị do client gửi.

### Nghĩ DatabaseClient tự chạy auditing callback

SQL trực tiếp không đi qua entity lifecycle như `save(entity)`. Nếu cần cập nhật audit fields, bind giá trị rõ ràng hoặc dùng trigger database theo một chính sách thống nhất.

### Ghi đè thời gian auditing bằng database default/trigger

Nếu cả ứng dụng và database cùng ghi timestamp, giá trị cuối cùng phụ thuộc thứ tự và cấu hình. Chọn một nguồn thời gian chính cho mỗi cột hoặc quy định rõ cách phối hợp.

### Dùng LastModifiedDate cho thời điểm nghiệp vụ

Thời điểm entity được lưu không đồng nghĩa thời điểm thanh toán, phê duyệt hoặc hoàn tất. Tạo các trường nghiệp vụ riêng.

### Coi auditing là lịch sử đầy đủ

`created...` và `lastModified...` chỉ giữ người tạo và người sửa gần nhất. Nếu cần toàn bộ lịch sử, thiết kế audit log/event history riêng.

## 12. Quy trình áp dụng auditing cho một bảng

1. Xác định có cần lưu actor, thời điểm tạo, thời điểm cập nhật hay cả bốn trường.
2. Chọn kiểu actor ổn định, ví dụ ID người dùng dạng `Long` hoặc UUID.
3. Khai báo `@CreatedBy`, `@LastModifiedBy`, `@CreatedDate`, `@LastModifiedDate` trong entity.
4. Tạo các cột tương ứng trong schema và migration dữ liệu hiện có.
5. Bật `@EnableR2dbcAuditing` và khai báo `ReactiveAuditorAware<T>`.
6. Lấy actor từ `ReactiveSecurityContextHolder` hoặc ngữ cảnh hệ thống đáng tin cậy.
7. Xác định chính sách cho anonymous request, background job và system actor.
8. Chọn `Instant` hoặc kiểu thời gian phù hợp với schema/timezone.
9. Dùng `DateTimeProvider`/`Clock` nếu cần kiểm soát thời gian và test ổn định.
10. Đảm bảo các thao tác ghi đi qua Repository/Template entity lifecycle hoặc tự gán audit fields cho SQL trực tiếp.
11. Giữ audit fields khỏi request model và kiểm soát trường nào được công khai trong response.
12. Kiểm thử insert, update, actor rỗng, tác vụ nền, raw SQL và migration.

## 13. Checklist ghi nhớ

- [ ] Entity có các annotation auditing đúng mục đích.
- [ ] `@EnableR2dbcAuditing` được bật trong cấu hình.
- [ ] Bean `ReactiveAuditorAware<T>` trả về đúng kiểu actor.
- [ ] Provider lấy danh tính từ reactive security context hoặc system context đáng tin cậy.
- [ ] Anonymous authentication được xử lý theo chính sách rõ ràng.
- [ ] Background job có quy tắc actor riêng nếu cần audit đầy đủ.
- [ ] `createdBy`/`lastModifiedBy` không lấy trực tiếp từ request body.
- [ ] Schema có các cột tương ứng và migration đã xử lý dữ liệu cũ.
- [ ] Timestamp có quy ước timezone nhất quán.
- [ ] `modifyOnCreate` phù hợp với ý nghĩa của trường LastModified.
- [ ] Dùng entity trả về từ `save` khi entity bất biến.
- [ ] SQL trực tiếp tự cập nhật audit columns hoặc dùng database trigger có chủ đích.
- [ ] Audit metadata được tách khỏi thời điểm nghiệp vụ và audit trail đầy đủ.
- [ ] Có integration test cho insert/update và trường hợp không có auditor.

Auditing trong Spring Data R2DBC giúp tự động ghi nhận người tạo, người cập nhật và các mốc thời gian thông qua entity lifecycle. Khi bật `@EnableR2dbcAuditing`, cung cấp `ReactiveAuditorAware` đúng kiểu và lấy actor từ reactive context đáng tin cậy, Repository/Template có thể quản lý các trường audit nhất quán. Những đường ghi SQL trực tiếp, tác vụ nền và yêu cầu lưu lịch sử đầy đủ vẫn cần được thiết kế riêng để bảo đảm dữ liệu kiểm toán phản ánh đúng người thực hiện và thời điểm thực tế.
