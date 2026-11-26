# Kích hoạt auditing bằng cơ chế riêng của từng store

## Mục tiêu và phạm vi

Trong Spring Data Commons, auditing là cơ chế tự gán metadata như thời điểm tạo, thời điểm sửa và người thực hiện thay đổi. Commons cung cấp annotation, hợp đồng lấy người thao tác và hạ tầng xử lý metadata. Việc đưa hạ tầng đó vào vòng đời ghi dữ liệu thuộc trách nhiệm của từng module lưu trữ, chẳng hạn Spring Data JPA, MongoDB, JDBC hoặc R2DBC.

Vì vậy, thêm `@CreatedDate` vào một thuộc tính chưa đủ để thuộc tính đó tự có giá trị. Ứng dụng cần kích hoạt auditing của đúng store và đi qua đường ghi dữ liệu có listener hoặc callback tương ứng. Không có một annotation `@EnableAuditing` chung của Commons để bật đồng thời auditing cho mọi loại kho dữ liệu.

Bài học tập trung vào ba câu hỏi thực hành:

- Store nào đang thực hiện thao tác ghi và cần cấu hình auditing nào?
- Listener hoặc callback nào chuyển metadata của Commons thành giá trị trên đối tượng?
- Làm thế nào kiểm tra rằng đường ghi thực tế của ứng dụng có đi qua cơ chế đó?

Các ví dụ dùng cấu hình Java. Ví dụ JPA sử dụng namespace `jakarta.persistence`; dự án thuộc thế hệ dùng `javax.persistence` phải dùng bộ import phù hợp với thế hệ dependency của mình.

## 1. Phân biệt hợp đồng chung và điểm tích hợp của store

Bốn annotation auditing thường dùng thuộc package `org.springframework.data.annotation`:

| Annotation | Ý nghĩa |
|---|---|
| `@CreatedDate` | Thời điểm đối tượng được nhận diện là mới và xử lý tạo dữ liệu |
| `@LastModifiedDate` | Thời điểm đối tượng được xử lý như một lần ghi thay đổi |
| `@CreatedBy` | Danh tính tác nhân tạo dữ liệu |
| `@LastModifiedBy` | Danh tính tác nhân thực hiện lần sửa |

Các thành phần liên quan có nhiệm vụ khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `AuditorAware<T>` | Cung cấp tác nhân hiện tại cho luồng đồng bộ |
| `ReactiveAuditorAware<T>` | Cung cấp tác nhân hiện tại dưới dạng publisher cho luồng reactive |
| `DateTimeProvider` | Cung cấp thời gian cho auditing khi cần tùy biến |
| Hạ tầng auditing của Commons | Nhận diện metadata và quyết định trường tạo/sửa cần điền |
| Module Spring Data của store | Đăng ký listener/callback, kết nối với mapping và vòng đời ghi |

Luồng xử lý có thể hình dung như sau:

```text
Ứng dụng yêu cầu ghi qua một API có hỗ trợ auditing
    -> store gọi listener hoặc callback
    -> hạ tầng xác định đối tượng mới hay đã tồn tại
    -> lấy thời gian và, nếu có cấu hình, tác nhân hiện tại
    -> gán các trường auditing phù hợp
    -> store tiếp tục chuyển đổi, persist hoặc cập nhật dữ liệu
```

Chi tiết thời điểm gọi khác nhau giữa các store. Không nên hiểu sơ đồ này là một thứ tự sự kiện JPA áp dụng nguyên vẹn cho MongoDB hay R2DBC.

Auditing metadata cũng khác với nhật ký lịch sử. Một hàng có `updatedAt` và `updatedBy` chỉ lưu thông tin của lần ghi gần nhất. Nó không tự lưu giá trị cũ, lý do sửa hoặc toàn bộ các phiên bản trước đó.

## 2. Chọn cấu hình theo store và mô hình thực thi

| Module/luồng ghi | Annotation kích hoạt | Điểm tích hợp cần hiểu |
|---|---|---|
| Spring Data JPA | `@EnableJpaAuditing` | `AuditingEntityListener` gắn vào vòng đời entity của JPA |
| Spring Data MongoDB đồng bộ | `@EnableMongoAuditing` | Callback auditing của hạ tầng mapping MongoDB |
| Spring Data MongoDB reactive | `@EnableReactiveMongoAuditing` | Callback reactive và `ReactiveAuditorAware` |
| Spring Data JDBC | `@EnableJdbcAuditing` | Callback của quá trình lưu aggregate bằng JDBC |
| Spring Data R2DBC | `@EnableR2dbcAuditing` | Callback reactive của quá trình mapping/ghi R2DBC |

Các annotation trên nằm trong module store tương ứng. Thêm riêng dependency Spring Data Commons không cung cấp toàn bộ các cấu hình đó.

Cần phân biệt store với loại cơ sở dữ liệu. Cùng làm việc với một cơ sở dữ liệu quan hệ, ứng dụng dùng JPA và ứng dụng dùng R2DBC có điểm tích hợp khác nhau. Không dùng `@EnableJpaAuditing` cho một repository R2DBC chỉ vì cả hai đều truy cập PostgreSQL.

Với store khác ngoài các ví dụ trong bài, hãy kiểm tra khả năng auditing và cơ chế kích hoạt của chính module đó. Việc một module cung cấp `Repository` hoặc hiểu một số annotation của Commons không chứng minh rằng nó hỗ trợ mọi tính năng auditing theo cùng cách.

## 3. Chuẩn bị nguồn tác nhân cho luồng đồng bộ

Nếu chỉ cần ngày giờ, ứng dụng có thể chỉ khai báo `@CreatedDate` và `@LastModifiedDate`, không cần cung cấp `AuditorAware`. Nếu có các trường người tạo/người sửa, kiểu giá trị mà auditor trả về phải phù hợp với kiểu thuộc tính.

Ví dụ dưới đây lấy tên đăng nhập từ Spring Security. Đoạn cấu hình giả định dự án đã có Spring Security và cơ chế xác thực phù hợp.

```java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

@Configuration
public class ImperativeAuditorConfiguration {

    @Bean
    AuditorAware<String> currentAuditor() {
        return () -> Optional
                .ofNullable(SecurityContextHolder.getContext().getAuthentication())
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
    }
}
```

Tên bean trong ví dụ là `currentAuditor`. Các cấu hình đồng bộ ở phần sau tham chiếu trực tiếp tới bean này để tránh chọn nhầm khi có nhiều nguồn auditor.

Một số điểm cần quyết định theo nghiệp vụ:

- Nếu cần mã người dùng bất biến, hãy lấy mã đó từ principal thay vì mặc định dùng tên đăng nhập có thể thay đổi.
- Nếu công việc chạy nền không có người đăng nhập, hãy quy định rõ tác nhân hệ thống và cách truyền tác nhân vào ngữ cảnh công việc.
- Nếu `Optional.empty()` là kết quả hợp lệ, các trường người thao tác có thể không được điền trong lần xử lý đó. Cần tính đến ràng buộc `NOT NULL` nếu có.
- Không dùng giá trị `createdBy` hoặc `updatedBy` do client gửi lên làm nguồn danh tính có thẩm quyền.

`isAuthenticated()` một mình chưa loại trừ được mọi trường hợp anonymous của Spring Security. Ví dụ lọc riêng `AnonymousAuthenticationToken` để thể hiện chính sách này.

Nguồn auditor không thực hiện việc phân quyền. Ứng dụng vẫn phải kiểm tra quyền trước khi chấp nhận thao tác ghi.

## 4. Spring Data JPA: bật hạ tầng và gắn entity listener

### 4.1. Cấu hình kích hoạt

Dự án phải có module Spring Data JPA, JPA provider và các dependency hỗ trợ của bộ phiên bản đang dùng. Với cấu hình auditing JPA, cần bảo đảm `spring-aspects` có trên classpath theo yêu cầu tích hợp của Spring Data JPA.

Cấu hình auditing:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing(auditorAwareRef = "currentAuditor")
public class JpaAuditingConfiguration {
}
```

Cấu hình này phải được Spring nạp. Ví dụ, đặt nó trong vùng component scan của ứng dụng hoặc import rõ ràng vào application context.

Sự hiện diện của Spring Boot hay một bean `JpaRepository` không thay thế cho việc kích hoạt auditing một cách có chủ đích.

### 4.2. Gắn listener cho entity

```java
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@Table(name = "purchase_order")
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String customerName;

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String customerName) {
        this.customerName = customerName;
    }

    public void renameCustomer(String customerName) {
        this.customerName = customerName;
    }
}
```

Trong ví dụ này:

- `@EnableJpaAuditing` đăng ký hạ tầng xử lý auditing.
- `@EntityListeners(AuditingEntityListener.class)` nối entity với hạ tầng đó.
- Các annotation Commons mô tả trường cần gán.
- `@Column(updatable = false)` giới hạn việc đưa trường tạo vào SQL cập nhật của JPA; nó không phải quyền truy cập ở cấp cơ sở dữ liệu.

Có thể đặt metadata và listener trên một `@MappedSuperclass` để tái sử dụng cho nhiều entity, hoặc đăng ký listener qua cấu hình JPA phù hợp. Hãy chọn một cách tổ chức nhất quán, tránh đăng ký chồng chéo không cần thiết.

### 4.3. Nhận diện đúng thời điểm hoạt động

Với JPA, auditing gắn với lifecycle callback như persist và update. Thời điểm callback chạy phụ thuộc vòng đời persistence context và flush.

Do đó:

- Thay đổi một entity đang managed có thể được ghi khi flush theo cơ chế dirty checking, dù không gọi lại `save()`.
- Khi lưu một entity detached, kết quả của `save()` có thể là đối tượng managed khác với đối tượng truyền vào. Hãy sử dụng kết quả trả về.
- Một phép đọc đơn thuần không phải sự kiện sửa dữ liệu.
- Một thao tác không phát sinh cập nhật thực tế không nên bị mặc định coi là sẽ làm đổi `updatedAt`.
- `@LastModifiedDate` không biểu diễn thời điểm transaction commit.

JPQL bulk update, native SQL hoặc thay đổi từ ứng dụng khác không đi qua listener của từng entity. Ví dụ cập nhật trực tiếp bằng `@Modifying @Query` không được bảo đảm tự gán đầy đủ các trường auditing như khi cập nhật entity qua lifecycle của JPA.

Nếu nghiệp vụ cần metadata cho đường bulk update, phải thiết kế việc gán metadata trong chính đường ghi đó hoặc áp dụng cơ chế riêng ở database, đồng thời xác định rõ bên nào sở hữu từng trường.

## 5. Spring Data MongoDB: auditing qua callback của mapping

### 5.1. Cấu hình đồng bộ

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableMongoAuditing;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "currentAuditor")
public class MongoAuditingConfiguration {
}
```

Không gắn `AuditingEntityListener` của JPA vào MongoDB document. MongoDB sử dụng cơ chế callback của hạ tầng Spring Data MongoDB.

Document ví dụ:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("purchase_orders")
public class PurchaseOrderDocument {

    @Id
    private String id;

    private String customerName;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    public PurchaseOrderDocument(String customerName) {
        this.customerName = customerName;
    }
}
```

Các trường auditing vẫn sử dụng annotation của Commons. Annotation `@Document` và cách ánh xạ ID thuộc module MongoDB.

Khi ghi document qua những API mapping có callback auditing, metadata được gán trong quá trình xử lý đối tượng trước khi dữ liệu được ghi xuống store.

Không suy ra rằng mọi phép cập nhật MongoDB đều đi qua cùng đường xử lý. Một lệnh cập nhật theo điều kiện chỉ gửi `$set` cho vài trường có thể không materialize document và không chạy callback auditing trên đối tượng như một lần `save(document)`.

### 5.2. Cấu hình reactive

Nếu đường ghi sử dụng `ReactiveMongoRepository` hoặc hạ tầng reactive tương ứng, dùng cấu hình reactive:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.EnableReactiveMongoAuditing;

@Configuration
@EnableReactiveMongoAuditing(
        auditorAwareRef = "reactiveCurrentAuditor"
)
public class ReactiveMongoAuditingConfiguration {
}
```

Đây là cấu hình cho đường ghi reactive. Nó không thay thế vai trò của cấu hình đồng bộ nếu ứng dụng đồng thời có một đường ghi MongoDB đồng bộ riêng.

Bean auditor reactive có thể lấy danh tính từ Reactor Context của Spring Security:

```java
import reactor.core.publisher.Mono;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

@Configuration
public class ReactiveAuditorConfiguration {

    @Bean
    ReactiveAuditorAware<String> reactiveCurrentAuditor() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
    }
}
```

Một chuỗi reactive có thể chuyển thread trong quá trình thực thi. Nguồn danh tính dựa trên thread hiện tại không tự trở thành nguồn danh tính đúng cho Reactor Context.

Không gọi `block()` để biến auditor reactive thành auditor đồng bộ. Hãy dùng hợp đồng phù hợp với đường thực thi và truyền ngữ cảnh xác thực đúng cách.

## 6. Spring Data JDBC: auditing khi lưu aggregate

Kích hoạt bằng annotation của JDBC:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "currentAuditor")
public class JdbcAuditingConfiguration {
}
```

Ví dụ aggregate root:

```java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrderRow {

    @Id
    private Long id;

    @Version
    private Long version;

    private String customerName;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    public PurchaseOrderRow(String customerName) {
        this.customerName = customerName;
    }
}
```

Schema phải có những cột tương ứng với mapping, ví dụ `created_at`, `updated_at`, `created_by`, `updated_by` nếu dùng quy ước tên mặc định tương ứng. Bật auditing không tự bổ sung các cột còn thiếu vào database.

Khác với JPA, JDBC không có persistence context để theo dõi mọi thay đổi bằng dirty checking. Việc sửa một object trong bộ nhớ cần được nối với thao tác lưu phù hợp thì mới có đường ghi và callback.

Nên đặt metadata của aggregate trên aggregate root. Nếu cần auditing riêng cho từng thành phần con, hãy xác minh mapping và callback của mô hình đó; không mặc định mọi object lồng nhau đều nhận cùng một lifecycle callback.

`@Version` trong ví dụ phục vụ optimistic locking và cũng có ảnh hưởng đến việc xác định entity mới theo quy tắc của Spring Data. Nó không phải annotation bắt buộc để bật auditing.

Dùng `JdbcTemplate` chạy SQL trực tiếp hoặc dùng một câu SQL cập nhật chuyên biệt không tự đi qua auditing callback của quá trình lưu aggregate.

## 7. Spring Data R2DBC: callback reactive cho dữ liệu quan hệ

Cấu hình R2DBC sử dụng annotation và nguồn auditor reactive:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;

@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "reactiveCurrentAuditor"
)
public class R2dbcAuditingConfiguration {
}
```

Có thể dùng mô hình thuộc tính tương tự `PurchaseOrderRow` với các annotation mapping quan hệ phù hợp. Ví dụ JDBC và R2DBC ở đây là những lựa chọn triển khai độc lập; chúng không yêu cầu cùng bật trong một ứng dụng.

Với repository reactive, lời gọi:

```java
Mono<PurchaseOrderRow> result =
        repository.save(new PurchaseOrderRow("Nguyễn An"));
```

chỉ tạo publisher cho thao tác lưu. Việc thực thi đường ghi và các callback liên quan diễn ra khi publisher được subscribe. Trong ứng dụng WebFlux, thông thường service trả publisher lên controller để framework quản lý subscription, thay vì tự gọi `subscribe()` trong service.

Nếu publisher bị bỏ đi, không có cơ sở để kỳ vọng metadata đã được ghi xuống database. Nếu chuỗi được thực thi lại do retry hoặc subscription khác, cần xét lại tác động của đường ghi đó đến thời gian và số lần cập nhật.

Các lệnh dùng `DatabaseClient` để chạy SQL trực tiếp không tự nhận auditing callback của entity. Với API template, phải phân biệt thao tác insert/save có xử lý entity với thao tác update theo điều kiện; không coi mọi method của template là một cam kết auditing giống nhau.

## 8. Đối tượng mới hay đã tồn tại quyết định metadata được gán

Auditing cần biết đối tượng có được coi là mới hay không. Cách nhận diện liên quan đến metadata của store, ID, version và, khi được áp dụng, hợp đồng `Persistable.isNew()`.

Điều cần nhớ là “có ID” không luôn đồng nghĩa “đã được lưu”. Ví dụ, ứng dụng có thể cấp UUID trước khi insert. Nếu chỉ dựa vào ID mà nhận diện sai trạng thái mới, ứng dụng có thể thấy trường sửa được gán trong khi trường tạo vẫn thiếu.

Một số tình huống cần xem xét:

| Tình huống | Vấn đề cần xác minh |
|---|---|
| Store cấp ID khi tạo | Đối tượng mới có trạng thái ID/version phù hợp trước khi ghi không? |
| Ứng dụng tự cấp ID | Store dựa vào ID, version hay một cơ chế khác để xác định mới? |
| Entity triển khai `Persistable` | `isNew()` có phản ánh đúng trạng thái ở các thời điểm lưu không? |
| Import dữ liệu đã tồn tại | Đường import đang insert mới hay cập nhật; cần giữ metadata gốc hay tạo metadata mới? |
| Dùng JPA merge | Đối tượng nào được quản lý và callback nào thực sự chạy? |

Không triển khai `isNew()` bằng cách luôn trả `true` để ép có `createdAt`. Cách đó có thể làm sai lựa chọn insert/update và phá vỡ hành vi lưu dữ liệu.

Đối với JPA, còn phải phân biệt quyết định `persist`/`merge` của repository với lifecycle callback mà provider thực sự phát sinh. Không mang nguyên quy tắc của một store sang store khác.

## 9. Tùy biến thời gian và hành vi khi tạo

### 9.1. Cung cấp thời gian qua `DateTimeProvider`

Dùng `Instant` giúp biểu diễn một thời điểm mà không gắn trực tiếp với múi giờ hiển thị. Việc hiển thị theo múi giờ người dùng có thể xử lý ở lớp trình bày.

Nếu cần chủ động kiểm soát nguồn thời gian, có thể khai báo:

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditingTimeConfiguration {

    @Bean
    Clock auditingClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditingDateTimeProvider(Clock auditingClock) {
        return () -> Optional.of(Instant.now(auditingClock));
    }
}
```

Sau đó tham chiếu bean trên annotation kích hoạt của store, ví dụ với JPA:

```java
@EnableJpaAuditing(
        auditorAwareRef = "currentAuditor",
        dateTimeProviderRef = "auditingDateTimeProvider"
)
```

Đây là cách điều chỉnh cấu hình JPA đã có, không phải yêu cầu tạo thêm một cấu hình `@EnableJpaAuditing` thứ hai.

Trong kiểm thử, có thể cung cấp `Clock.fixed(...)` để kiểm soát thời gian thay vì chờ một khoảng thời gian thực. Nếu muốn xác minh `updatedAt` thay đổi giữa hai lần lưu, nguồn thời gian phải cung cấp hai mốc khác nhau theo kịch bản.

Ngay cả với cấu hình reactive, `DateTimeProvider` vẫn là hợp đồng cung cấp thời gian đồng bộ. Việc đọc một đồng hồ cục bộ không đòi hỏi gọi một dịch vụ từ xa hay chặn reactive thread.

### 9.2. Các lựa chọn liên quan đến tạo và sửa

Các annotation kích hoạt trong những store minh họa cung cấp lựa chọn như `setDates` và `modifyOnCreate`. Cần hiểu ý nghĩa trước khi thay đổi mặc định:

- `setDates`: cho phép hạ tầng auditing tự gán thời gian.
- `modifyOnCreate`: quyết định có gán metadata sửa ngay trong lần tạo hay không.

Với cấu hình mặc định thông thường, một đối tượng mới có thể có cả `createdAt` lẫn `updatedAt`. Điều này không chứng minh rằng nó đã trải qua một lần sửa nghiệp vụ sau khi tạo.

Nếu yêu cầu nghiệp vụ muốn trường sửa chỉ xuất hiện từ lần cập nhật tiếp theo, cấu hình phù hợp, chẳng hạn:

```java
@EnableMongoAuditing(
        auditorAwareRef = "currentAuditor",
        modifyOnCreate = false
)
```

Lựa chọn này cũng ảnh hưởng cách hiểu các trường người sửa, không chỉ trường thời gian. Schema, DTO và kiểm thử phải thống nhất với chính sách đã chọn.

Thời gian auditing lấy từ ứng dụng có thể khác thời gian database. Nếu database trigger hoặc default cũng ghi cùng một trường, cần quyết định cơ chế nào là nguồn dữ liệu chính và cách đọc lại giá trị cuối cùng.

## 10. Ứng dụng có nhiều store hoặc nhiều loại auditor

Một ứng dụng có thể dùng JPA để lưu giao dịch và MongoDB để lưu document. Mỗi module cần cấu hình auditing của nó, cùng các vùng repository và mapping được tổ chức rõ ràng.

Có thể dùng chung một bean `AuditorAware<String>` cho hai đường đồng bộ nếu chính sách danh tính giống nhau. Điều đó không làm mất yêu cầu bật auditing riêng của JPA và MongoDB.

Nếu ứng dụng vừa có luồng đồng bộ vừa có luồng reactive, nên thể hiện rõ hai hợp đồng:

```text
currentAuditor
    -> AuditorAware<String>
    -> cấu hình auditing của đường đồng bộ

reactiveCurrentAuditor
    -> ReactiveAuditorAware<String>
    -> cấu hình auditing của đường reactive
```

Nếu có nhiều bean cùng loại, dùng `auditorAwareRef` để chọn bean đúng theo tên. Không dựa vào thứ tự đăng ký bean để quyết định nguồn danh tính.

Ngoài ra, một entity của store này không tự trở thành entity của store khác chỉ vì có cùng các trường auditing. Mapping, kiểu ID, cơ chế tạo ID và lifecycle vẫn thuộc từng store.

## 11. Xác minh bằng đường ghi thật của ứng dụng

Kiểm tra chỉ bằng reflection để thấy `@CreatedDate` chưa chứng minh được auditing hoạt động. Cần đi qua repository hoặc API ghi mà ứng dụng thực tế sử dụng và đọc lại kết quả.

Một kịch bản hữu ích:

1. Tạo đối tượng mới dưới tác nhân A, với nguồn thời gian T1.
2. Ghi bằng đúng repository hoặc template dự kiến.
3. Hoàn tất thao tác ghi; với JPA, flush khi cần để bảo đảm lifecycle đã chạy.
4. Đọc lại dữ liệu từ store, tránh chỉ dựa vào object đang được giữ trong bộ nhớ hoặc persistence context.
5. Thay đổi một thuộc tính nghiệp vụ dưới tác nhân B, với nguồn thời gian T2.
6. Lưu và đọc lại; kiểm tra metadata tạo được giữ, metadata sửa phản ánh lần ghi mới.

Những trường hợp nên bao phủ theo cấu hình thực tế:

| Kịch bản | Điều cần quan sát |
|---|---|
| Tạo mới | Trường tạo có giá trị; trường sửa tuân theo `modifyOnCreate` |
| Cập nhật dữ liệu nghiệp vụ | Trường tạo được giữ; trường sửa phản ánh tác nhân/thời gian phù hợp |
| Chỉ theo dõi thời gian | Không cần auditor nhưng thời gian vẫn được gán |
| Không có người đăng nhập | Hành vi phù hợp chính sách rỗng hoặc tác nhân hệ thống |
| Entity có ID cấp trước | Không nhận diện sai đối tượng mới |
| Publisher reactive không được thực thi | Chưa có kết quả ghi xuống store để đọc lại |
| Cập nhật bằng SQL, JPQL bulk hoặc update theo điều kiện | Hành vi đúng với cơ chế riêng đã thiết kế cho đường ghi đó |

Nếu có optimistic locking hoặc transaction rollback, phải đánh giá trạng thái đã được lưu thành công. Metadata trên một object sau callback không chứng minh transaction đã commit.

## 12. Chẩn đoán khi annotation có mặt nhưng metadata vẫn rỗng

| Hiện tượng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Tất cả trường auditing đều rỗng | Cấu hình đúng store có được nạp không? | Bật đúng annotation và đưa configuration vào context |
| Chỉ JPA không có metadata | Entity có listener và đủ hạ tầng hỗ trợ không? | Kiểm tra `AuditingEntityListener`, classpath và lifecycle ghi |
| Có ngày giờ nhưng thiếu người thao tác | Auditor có trả giá trị, đúng kiểu và đúng ngữ cảnh không? | Kiểm tra principal, bean được chọn và chính sách anonymous |
| Reactive thiếu người thao tác | Đang dùng hợp đồng reactive và Reactor Context chưa? | Dùng `ReactiveAuditorAware`, kiểm tra ngữ cảnh tại lúc thực thi |
| `createdAt` thiếu khi tạo với ID tự cấp | Trạng thái mới có bị nhận diện sai không? | Kiểm tra ID/version/`Persistable` theo store |
| `updatedAt` không thay đổi sau lệnh bulk | Đường ghi có bỏ qua callback entity không? | Gán metadata trong đường ghi chuyên biệt theo chính sách |
| Giá trị có trong object nhưng thiếu trong database | Mapping cột/trường và transaction có đúng không? | Kiểm tra schema, conversion, flush và kết quả commit |
| Tạo mới đã có `updatedAt` | `modifyOnCreate` đang là gì? | Đối chiếu kỳ vọng với cấu hình hiện hành |
| Bean auditor không được chọn đúng | Có nhiều bean hoặc sai tên tham chiếu không? | Đặt `auditorAwareRef` rõ ràng |
| Gọi repository reactive nhưng không có dữ liệu | Publisher có được subscribe và hoàn tất không? | Kiểm tra chuỗi trả về và nơi framework thực thi nó |

Không giải quyết mọi lỗi bằng cách tự gán thời gian trong service. Trước hết cần biết lỗi nằm ở cấu hình, lifecycle, mapping, nguồn tác nhân hay đường ghi đã bỏ qua auditing. Nếu chủ động dùng metadata thủ công cho một đường ghi đặc biệt, hãy mô tả và kiểm thử chính sách đó rõ ràng.

## 13. Bài thực hành áp dụng

Chọn đúng một store đang dùng trong dự án và thực hiện bài sau:

1. Tạo một đối tượng đơn hàng với hai trường thời gian và hai trường người thao tác.
2. Bật auditing bằng annotation riêng của store đó; nếu là JPA, gắn entity listener.
3. Cấu hình nguồn tác nhân phù hợp mô hình thực thi, sử dụng mã người dùng ổn định.
4. Tạo đơn hàng bởi người dùng A, sau đó sửa một thuộc tính nghiệp vụ bởi người dùng B.
5. Đọc lại dữ liệu và giải thích bốn trường metadata.
6. Thử một đường cập nhật trực tiếp bỏ qua lifecycle entity, rồi xác định chính sách metadata cần có cho đường đó.
7. Nếu chạy tác vụ nền hoặc dùng reactive, lặp lại kịch bản trong chính ngữ cảnh thực thi ấy.

Kết quả cần giải thích được chuỗi: **annotation Commons mô tả metadata → cấu hình store đăng ký hạ tầng → listener/callback tham gia đường ghi → metadata được lưu và đọc lại**. Việc chọn đúng cơ chế của store là điều kiện để các abstraction chung của Spring Data hoạt động đúng trong ứng dụng cụ thể.