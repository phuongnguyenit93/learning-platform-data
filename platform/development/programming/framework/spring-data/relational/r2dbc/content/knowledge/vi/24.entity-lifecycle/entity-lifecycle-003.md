# Chuẩn bị dữ liệu trước chuyển đổi bằng BeforeConvertCallback

## 1. Vị trí của BeforeConvertCallback trong vòng đời entity

Khi lưu một entity bằng Spring Data R2DBC, ứng dụng đưa object Java vào repository hoặc `R2dbcEntityTemplate`. Spring Data cần chuyển object đó thành các giá trị phù hợp với cột SQL trước khi tạo và thực thi câu lệnh INSERT hoặc UPDATE.

`BeforeConvertCallback` là một điểm mở rộng trong vòng đời entity, được gọi trước khi Spring Data chuyển entity thành dữ liệu ghi xuống database. Callback cho phép chuẩn bị hoặc chuẩn hóa object ngay trước bước mapping.

Ví dụ, trước khi lưu `Customer`, ứng dụng có thể:

- Chuẩn hóa email thành chữ thường và loại bỏ khoảng trắng ở hai đầu.
- Tạo slug hoặc mã nghiệp vụ nếu entity chưa có.
- Gán UUID do ứng dụng quản lý.
- Bổ sung timestamp do ứng dụng quản lý.
- Chuẩn hóa một giá trị enum hoặc value object trước khi converter xử lý.
- Bảo đảm một thuộc tính bắt buộc đã có giá trị theo quy tắc domain.

Callback phù hợp cho các biến đổi nhỏ, xác định và gắn trực tiếp với bước chuẩn bị entity để persistence. Những quy tắc nghiệp vụ phức tạp vẫn nên nằm trong domain model hoặc application service.

## 2. Vị trí callback trong luồng ghi

Một luồng ghi entity ở mức khái quát:

```mermaid
flowchart TD
    A[Repository.save(entity)] --> B[Nhận diện entity mới hay đã tồn tại]
    B --> C[BeforeConvertCallback]
    C --> D[Chuyển entity thành OutboundRow]
    D --> E[BeforeSaveCallback]
    E --> F[Tạo và bind SQL]
    F --> G[Thực thi INSERT hoặc UPDATE]
    G --> H[AfterSaveCallback]
    H --> I[Trả entity qua Mono]
```

`BeforeConvertCallback` chạy trước khi entity được chuyển thành `OutboundRow`. Đây là điểm phù hợp để thay đổi thuộc tính Java mà mapping layer sẽ đọc.

Trong luồng đọc, Spring Data chuyển dữ liệu từ hàng SQL thành entity; `BeforeConvertCallback` không phải callback đọc dữ liệu. Với thao tác đọc, có các callback khác như callback sau khi chuyển đổi tùy store và phiên bản.

Chi tiết thứ tự callback và các bước phụ thuộc implementation, nhưng nguyên tắc cần nhớ là: **BeforeConvert tác động lên entity trước mapping; BeforeSave tác động ở giai đoạn ngay trước khi lưu, khi dữ liệu outbound đã được tạo.**

## 3. BeforeConvertCallback trong Spring Data R2DBC

Với R2DBC, callback được thực thi trong luồng reactive. Callback nhận entity và định danh bảng, sau đó trả về một `Publisher` chứa entity đã chuẩn bị.

Ví dụ dạng callback reactive thường dùng trong Spring Data R2DBC:

```java
import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.stereotype.Component;

@Component
public class CustomerBeforeConvertCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        customer.setEmail(customer.getEmail().trim().toLowerCase(Locale.ROOT));
        return Mono.just(customer);
    }
}
```

Đoạn mã cần các import `Mono` và `Locale` tương ứng. Tên package/chữ ký callback cần khớp phiên bản Spring Data R2DBC của dự án; các phiên bản Spring Data Relational dùng callback imperative và callback reactive có thể có interface/package riêng. Với R2DBC, hãy chọn interface reactive dành cho store đang sử dụng, không triển khai nhầm callback đồng bộ của một module khác.

Điểm quan trọng trong ví dụ:

- Callback được đăng ký như một Spring bean bằng `@Component`.
- Generic type `Customer` giới hạn callback cho entity `Customer`.
- `SqlIdentifier table` cho biết định danh bảng đang được xử lý.
- `onBeforeConvert` trả publisher chứa entity sau khi chuẩn hóa.
- Không gọi `block()` hoặc tự `subscribe()` trong callback.

Nếu callback không thay đổi entity, vẫn trả lại entity:

```java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {
    return Mono.just(customer);
}
```

Callback cần phát ra entity để quá trình mapping tiếp tục. Nếu trả `Mono.empty()`, pipeline có thể kết thúc mà không thực hiện thao tác lưu; không dùng empty như cách bỏ qua lỗi hoặc biểu diễn entity không hợp lệ.

## 4. Chuẩn hóa dữ liệu trước khi mapping

Một ứng dụng thường muốn email có cùng định dạng bất kể người dùng nhập chữ hoa, chữ thường hoặc khoảng trắng.

Entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Column("email_address")
    private String email;

    // getters and setters
}
```

Callback:

```java
@Component
public class NormalizeCustomerEmailCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        if (customer.getEmail() != null) {
            customer.setEmail(
                    customer.getEmail().trim().toLowerCase(Locale.ROOT));
        }

        return Mono.just(customer);
    }
}
```

Khi ứng dụng lưu:

```java
Customer customer = new Customer();
customer.setName("Lan Nguyen");
customer.setEmail("  LAN@EXAMPLE.COM  ");

return customerRepository.save(customer);
```

Callback chuẩn hóa email thành `lan@example.com` trước khi Spring Data tạo dữ liệu ghi. Vì vậy, database nhận giá trị đã chuẩn hóa.

### 4.1. Vì sao dùng Locale.ROOT?

`String.toLowerCase()` không tham số sử dụng locale mặc định của JVM. Kết quả chuyển chữ có thể khác giữa các locale, đặc biệt với một số ký tự. Với các mã kỹ thuật như email, slug hoặc identifier không phụ thuộc ngôn ngữ giao diện, `Locale.ROOT` giúp tránh phụ thuộc locale máy chủ.

Chuẩn hóa ở callback không thay thế unique constraint. Nếu email phải duy nhất sau khi chuẩn hóa, schema vẫn cần constraint phù hợp, ví dụ unique trên cột email đã lưu dạng chuẩn. Nhiều request đồng thời vẫn có thể cùng vượt qua một truy vấn kiểm tra tồn tại trước khi insert; database constraint mới là lớp bảo vệ cuối cùng.

## 5. Tạo UUID trước khi chuyển đổi

Nếu ứng dụng là nguồn có thẩm quyền cho ID, callback có thể bổ sung UUID khi entity chưa có ID:

```java
@Table("customer")
public class Customer {

    @Id
    private UUID id;

    private String name;
}
```

```java
@Component
public class CustomerIdCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        if (customer.getId() == null) {
            customer.setId(UUID.randomUUID());
        }

        return Mono.just(customer);
    }
}
```

Khi ID đã tồn tại, callback giữ nguyên ID. Điều này giúp thao tác lặp trên cùng entity không tạo ID mới mỗi lần save.

### 5.1. Phối hợp với newness detection

Việc callback gán ID trước khi mapping có thể ảnh hưởng đến cơ chế nhận diện entity mới. Spring Data thường dùng ID hoặc `@Version`/`Persistable.isNew()` để xác định entity mới. Nếu ID ban đầu là `null` nhưng callback gán UUID trước khi framework quyết định insert/update, cần xác nhận thứ tự xử lý của phiên bản Spring Data đang dùng.

Với ID do ứng dụng gán trước, nên thiết kế newness detection rõ ràng thay vì giả định ID có giá trị luôn có nghĩa entity đã tồn tại. Có thể dùng `Persistable<ID>` để cung cấp `isNew()` hoặc một thuộc tính version nullable theo mô hình phù hợp.

Nếu không cần callback, tạo UUID trong factory method/domain constructor thường dễ hiểu hơn vì ID đã có ngay từ khi tạo aggregate. Chỉ đặt logic sinh ID trong `BeforeConvertCallback` khi đây thực sự là chính sách persistence chung cho entity.

### 5.2. Không ghi đè ID do database quản lý

Nếu ID được database sinh bằng identity hoặc sequence, không tự tạo giá trị khác trong callback. Hãy để ID chưa có giá trị và dùng cơ chế generated ID của Spring Data/driver. Gán ID trong callback có thể khiến database không dùng default/identity hoặc làm Spring Data chọn nhầm đường update.

## 6. Bổ sung timestamp trước khi lưu

Callback có thể gán thời điểm tạo hoặc cập nhật nếu ứng dụng là nguồn có thẩm quyền cho timestamp.

Ví dụ dùng `Clock` để kiểm thử được:

```java
@Component
public class CustomerTimestampCallback
        implements BeforeConvertCallback<Customer> {

    private final Clock clock;

    public CustomerTimestampCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        Instant now = clock.instant();

        if (customer.getCreatedAt() == null) {
            customer.setCreatedAt(now);
        }
        customer.setUpdatedAt(now);

        return Mono.just(customer);
    }
}
```

`Clock` có thể được cấu hình thành bean:

```java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
```

Trong ví dụ, `createdAt` chỉ được gán nếu chưa có giá trị; `updatedAt` được cập nhật mỗi lần callback chạy. Vì callback có thể chạy cho cả insert và update, không nên gán lại `createdAt` vô điều kiện.

### 6.1. Chọn nguồn thời gian

Nếu timestamp phải phản ánh thời điểm database ghi nhận transaction, dùng default hoặc expression của database có thể phù hợp hơn:

```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
```

Trong trường hợp đó, không gán `createdAt` trong callback nếu muốn database áp dụng default. Nếu callback gán giá trị Java và mapping gửi cột đó trong INSERT, database sẽ nhận giá trị tường minh thay vì dùng default.

Nếu timestamp biểu diễn thời điểm ứng dụng nhận sự kiện hoặc thời điểm domain tạo command, `Clock` ở Java có thể là nguồn phù hợp. Hãy xác định rõ ý nghĩa của timestamp trước khi chọn nơi gán.

## 7. Tạo slug hoặc mã nghiệp vụ

Một callback có thể tạo slug từ tên khi entity chưa có slug:

```java
@Component
public class ArticleSlugCallback
        implements BeforeConvertCallback<Article> {

    @Override
    public Publisher<Article> onBeforeConvert(
            Article article,
            SqlIdentifier table) {

        if (article.getSlug() == null || article.getSlug().isBlank()) {
            article.setSlug(toSlug(article.getTitle()));
        }

        return Mono.just(article);
    }

    private String toSlug(String value) {
        return Normalizer.normalize(value, Normalizer.Form.NFD)
                .replaceAll("\\p{M}+", "")
                .toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9]+", "-")
                .replaceAll("^-|-$", "");
    }
}
```

Đây là ví dụ đơn giản; xử lý tiếng Việt, Unicode, dấu câu và ký tự ngoài ASCII có thể cần quy tắc slug riêng theo sản phẩm.

Callback chỉ tạo giá trị từ dữ liệu hiện có. Nếu slug phải duy nhất, không nên truy vấn kiểm tra tồn tại rồi tự thêm hậu tố trong callback mà không có cơ chế chống race condition. Hai request có thể cùng sinh một slug. Hãy dùng unique constraint và một chiến lược retry/tạo mã duy nhất ở application service hoặc database.

## 8. BeforeConvertCallback và BeforeSaveCallback khác nhau thế nào?

Spring Data Relational cung cấp nhiều callback ở các điểm khác nhau trong lifecycle. Hai callback dễ nhầm là `BeforeConvertCallback` và `BeforeSaveCallback`.

| Callback | Thời điểm | Dữ liệu callback nhận | Mục đích phù hợp |
| --- | --- | --- | --- |
| `BeforeConvertCallback` | Trước khi entity được chuyển thành dữ liệu outbound | Entity và table identifier | Chuẩn hóa hoặc bổ sung thuộc tính Java |
| `BeforeSaveCallback` | Sau khi entity đã được chuyển thành outbound representation, trước khi lưu | Entity, outbound row và table identifier | Điều chỉnh dữ liệu outbound trước khi SQL được thực thi |
| `AfterSaveCallback` | Sau thao tác lưu | Entity và dữ liệu liên quan theo API | Quan sát hoặc xử lý sau khi lưu |
| Callback sau convert/đọc | Sau khi row được chuyển thành entity | Entity đã đọc | Bổ sung trạng thái sau khi mapping đọc |

Ví dụ, nếu muốn chuẩn hóa `customer.email` trên object để các tầng sau cũng nhìn thấy giá trị chuẩn, `BeforeConvertCallback` phù hợp. Nếu cần chỉnh trực tiếp giá trị trong `OutboundRow` sau mapping, `BeforeSaveCallback` phù hợp hơn.

Không dùng `BeforeSaveCallback` để thay thế mọi việc của `BeforeConvertCallback`; hai điểm mở rộng có dữ liệu đầu vào và mục đích khác nhau.

## 9. Callback không phải nơi thay thế domain logic

Callback được gọi tự động trong quá trình persistence. Vì vậy, nếu đưa quá nhiều nghiệp vụ vào callback, hành vi của entity có thể khó đoán khi đọc code service.

Nên đặt trong `BeforeConvertCallback`:

- Chuẩn hóa biểu diễn dữ liệu trước khi lưu.
- Bổ sung giá trị kỹ thuật được xác định từ entity.
- Gán timestamp theo chính sách persistence.
- Tạo identifier kỹ thuật khi entity chưa có.
- Áp dụng một quy tắc mapping chung cho mọi đường ghi của entity.

Nên đặt trong domain model/application service:

- Kiểm tra một đơn hàng có được phép xác nhận không.
- Tính tổng tiền, thuế hoặc chiết khấu theo nhiều quy tắc.
- Kiểm tra tồn kho từ một aggregate khác.
- Gọi dịch vụ thanh toán hoặc dịch vụ từ xa.
- Phát domain event theo một quyết định nghiệp vụ.
- Quyết định trạng thái dựa trên quyền người dùng hoặc ngữ cảnh request.

Callback không nên trở thành nơi ẩn chứa quy trình nghiệp vụ nhiều bước. Người đọc `repository.save(entity)` cần có thể hiểu rằng callback chuẩn bị dữ liệu persistence, chứ không bất ngờ thực hiện một use case lớn.

## 10. Tránh truy vấn database hoặc gọi dịch vụ từ callback

Callback reactive có thể trả `Publisher`, nhưng điều đó không có nghĩa nên dùng nó để thực hiện các thao tác mạng tùy ý trước mỗi lần lưu.

Ví dụ không nên thiết kế callback gọi repository khác để tìm slug trùng, tải customer, gọi HTTP lấy tỷ giá rồi mới lưu entity. Các vấn đề có thể phát sinh:

- Mỗi lần save tạo thêm nhiều round-trip database.
- Callback có thể gây vòng phụ thuộc giữa repository và bean callback.
- Một callback áp dụng ngầm cho nhiều use case khiến chi phí khó quan sát.
- Gọi dịch vụ ngoài có thể kéo dài thời gian giữ transaction/connection.
- Lỗi từ hệ thống khác làm thao tác save thất bại theo cách khó dự đoán.
- Kiểm tra trước khi ghi vẫn có race condition nếu không có constraint.

Nếu cần dữ liệu từ hệ thống khác để quyết định entity, hãy lấy dữ liệu ở application service trước khi gọi repository, sau đó truyền kết quả vào domain object. Callback nên tập trung vào biến đổi cục bộ và có thể dự đoán.

Nếu một callback thực sự cần asynchronous computation, hãy giữ nó non-blocking, trả publisher đúng cách và đánh giá tác động tới lifecycle, transaction cùng latency. Không gọi `.block()` trong callback reactive.

## 11. Callback phải ổn định khi chạy nhiều lần

Không nên giả định callback chỉ chạy đúng một lần trong vòng đời object. Một entity có thể được lưu nhiều lần; retry hoặc thao tác persistence khác cũng có thể làm callback được gọi lại.

Ví dụ không an toàn:

```java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    customer.setReference(UUID.randomUUID().toString());
    return Mono.just(customer);
}
```

Mỗi lần save tạo reference mới, có thể làm thay đổi định danh nghiệp vụ dù entity đã có reference.

Nên kiểm tra trước khi gán:

```java
if (customer.getReference() == null || customer.getReference().isBlank()) {
    customer.setReference(UUID.randomUUID().toString());
}
```

Callback có tính idempotent khi chạy lại không làm thay đổi kết quả đã được chuẩn hóa hoặc đã được tạo ở lần trước. Tính idempotent giúp retry và thao tác save lặp dễ dự đoán hơn.

## 12. Không ghi đè giá trị do database quản lý

Một số cột được database sinh hoặc quản lý:

- Identity/sequence ID.
- `created_at DEFAULT CURRENT_TIMESTAMP`.
- Generated column.
- Cột tính toán từ trigger.
- Giá trị được database gán khi INSERT.

Nếu callback gán giá trị cho những cột này trước khi mapping, câu INSERT có thể gửi giá trị tường minh và làm database không áp dụng default. Ví dụ:

```java
customer.setCreatedAt(clock.instant());
```

Nếu schema có `created_at DEFAULT CURRENT_TIMESTAMP`, việc gán trong callback có thể làm default không được sử dụng.

Hãy phân định nguồn có thẩm quyền:

| Nguồn quản lý | Cách làm |
| --- | --- |
| Ứng dụng | Callback hoặc domain factory gán giá trị trước mapping |
| Database | Để thuộc tính không được ghi, dùng default/generated value và cơ chế đọc lại nếu cần |
| Cần cả hai như lớp dự phòng | Giữ chính sách Java và schema đồng nhất, kiểm tra câu SQL thực tế |

Đối với thuộc tính database quản lý hoàn toàn, có thể cân nhắc mapping read-only phù hợp như `@ReadOnlyProperty` và cấu hình generated value theo khả năng của database/driver.

## 13. Thứ tự khi có nhiều callback

Ứng dụng có thể có nhiều callback cho cùng entity hoặc cùng lifecycle. Ví dụ một callback chuẩn hóa email và callback khác tạo slug.

Khi thứ tự có ảnh hưởng, hãy xác định thứ tự callback rõ ràng bằng cơ chế ordering của Spring, chẳng hạn `@Order` hoặc `Ordered` nếu callback infrastructure của phiên bản đang dùng hỗ trợ:

```java
@Component
@Order(10)
public class NormalizeNameCallback
        implements BeforeConvertCallback<Customer> {
    // ...
}

@Component
@Order(20)
public class CustomerSearchKeyCallback
        implements BeforeConvertCallback<Customer> {
    // ...
}
```

Ví dụ này giả định callback thứ hai cần giá trị đã được chuẩn hóa bởi callback thứ nhất. Nếu các callback độc lập, không nên tạo phụ thuộc thứ tự không cần thiết.

Các callback reactive được thực thi theo chuỗi mà framework quản lý. Mỗi callback cần trả publisher của entity đã xử lý để callback tiếp theo và bước mapping nhận được kết quả tương ứng. Hãy kiểm tra quy tắc ordering của phiên bản Spring Data đang sử dụng.

## 14. Callback áp dụng cho những thao tác nào?

`BeforeConvertCallback` gắn với bước chuyển entity thành dữ liệu ghi. Thông thường, nó được gọi trong luồng insert/update khi entity được lưu qua các API Spring Data Relational tương ứng.

Không nên mặc định callback được gọi cho:

- Mọi câu SQL tùy chỉnh viết bằng `DatabaseClient`.
- Câu UPDATE/DELETE bulk bằng `@Modifying`.
- Các câu SQL chạy trực tiếp qua R2DBC `Connection`.
- Thao tác đọc entity.
- Một entity được chuyển đổi thủ công ngoài mapping pipeline của Spring Data.

Các API persistence cấp thấp có thể bỏ qua entity lifecycle callbacks vì chúng không đi qua cùng luồng mapping của repository/template. Nếu ứng dụng dùng nhiều đường ghi, hãy quyết định nơi áp dụng chuẩn hóa để không có đường ghi nào bỏ qua quy tắc cần thiết.

Đặc biệt, `DatabaseClient.sql("UPDATE ...")` không tự gọi callback cho từng entity vì câu lệnh làm việc trực tiếp với SQL. Nếu cần cùng quy tắc, hãy gọi logic chuẩn hóa từ service hoặc dùng một persistence adapter dùng chung.

## 15. Đăng ký callback trong Spring

Callback thường được đăng ký như Spring bean:

```java
@Component
public class CustomerBeforeConvertCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        // Prepare customer here
        return Mono.just(customer);
    }
}
```

Khi ứng dụng dùng Spring Boot với Spring Data R2DBC auto-configuration, callback bean có thể được phát hiện và đăng ký vào entity callback infrastructure. Với cấu hình thủ công hoặc custom `R2dbcEntityTemplate`, cần bảo đảm template sử dụng `ReactiveEntityCallbacks` tương ứng.

Không tạo callback bằng `new` bên trong service cho mỗi lần save; làm vậy khiến callback không được quản lý bởi Spring và có thể bỏ qua dependency injection hoặc ordering.

### 15.1. Dependency injection

Callback có thể nhận dependency thuần như `Clock` hoặc một component chuyển đổi không truy cập persistence:

```java
@Component
public class CustomerTimestampCallback
        implements BeforeConvertCallback<Customer> {

    private final Clock clock;

    public CustomerTimestampCallback(Clock clock) {
        this.clock = clock;
    }

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {
        if (customer.getCreatedAt() == null) {
            customer.setCreatedAt(clock.instant());
        }
        return Mono.just(customer);
    }
}
```

Dependency được inject một lần khi Spring tạo bean. Callback nên stateless hoặc chỉ giữ dependency thread-safe; không lưu entity hiện tại vào field của callback vì nhiều request có thể chạy đồng thời.

## 16. Callback với entity immutable

Không phải entity nào cũng dùng setter. Với Java record hoặc immutable class, callback nên tạo instance mới chứa giá trị đã chuẩn bị:

```java
public record Customer(
        @Id UUID id,
        String name,
        String email) {

    public Customer withEmail(String normalizedEmail) {
        return new Customer(id, name, normalizedEmail);
    }
}
```

Callback:

```java
@Component
public class ImmutableCustomerCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalized = customer.email() == null
                ? null
                : customer.email().trim().toLowerCase(Locale.ROOT);

        return Mono.just(customer.withEmail(normalized));
    }
}
```

Spring Data cần dùng entity được callback trả về cho bước mapping tiếp theo. Với immutable entity, không được tạo instance mới rồi bỏ qua bằng cách trả lại object cũ.

## 17. Callback và auditing

Spring Data Relational có cơ chế auditing cho các trường như người tạo, thời điểm tạo, người cập nhật và thời điểm cập nhật. Nếu yêu cầu chỉ là auditing chuẩn, hãy cân nhắc dùng auditing infrastructure thay vì tự viết nhiều callback timestamp.

Ví dụ entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
```

Auditing cần được bật và cấu hình `DateTimeProvider`/auditor phù hợp theo phiên bản Spring Data. Nếu cần ghi người thực hiện, có thể cấu hình `ReactiveAuditorAware` để lấy auditor theo ngữ cảnh reactive thay vì dựa vào `ThreadLocal` trong request.

`BeforeConvertCallback` vẫn có thể dùng cho quy tắc chuẩn bị dữ liệu khác. Tránh để callback tự gán timestamp cùng lúc với auditing cho cùng thuộc tính vì hai cơ chế có thể ghi đè nhau.

## 18. Xử lý lỗi trong callback

Nếu dữ liệu không thể được chuẩn bị, callback có thể phát lỗi:

```java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.getEmail() == null || customer.getEmail().isBlank()) {
        return Mono.error(new IllegalArgumentException(
                "Email must not be blank"));
    }

    customer.setEmail(customer.getEmail().trim().toLowerCase(Locale.ROOT));
    return Mono.just(customer);
}
```

Khi callback phát lỗi, bước mapping/ghi tiếp theo không được thực hiện bình thường; lỗi được truyền qua publisher của thao tác save.

Tuy nhiên, validation dữ liệu đầu vào thường nên nằm trong Bean Validation, domain constructor/factory hoặc application service để caller nhận lỗi ở đúng ranh giới nghiệp vụ. Callback thích hợp cho các điều kiện chuẩn bị persistence mà mọi đường ghi qua mapping cần tuân theo.

Không bắt mọi exception rồi trả lại entity như không có lỗi. Cách đó có thể khiến dữ liệu chưa được chuẩn bị vẫn được lưu.

## 19. Kiểm thử BeforeConvertCallback

Có thể kiểm thử callback trực tiếp để xác nhận phép biến đổi:

```java
@Test
void shouldNormalizeEmailBeforeConvert() {
    Customer customer = new Customer();
    customer.setEmail("  LAN@EXAMPLE.COM  ");

    CustomerBeforeConvertCallback callback =
            new CustomerBeforeConvertCallback();

    StepVerifier.create(callback.onBeforeConvert(
                    customer,
                    SqlIdentifier.unquoted("customer")))
            .assertNext(result ->
                    assertEquals("lan@example.com", result.getEmail()))
            .verifyComplete();
}
```

Ví dụ giả định callback trả `Publisher<Customer>` và constructor/field phù hợp. Nếu callback dùng dependency như `Clock`, inject clock cố định trong test để kết quả xác định.

### 19.1. Kiểm thử callback được gọi khi repository save

Unit test callback trực tiếp chỉ xác nhận logic của callback. Integration test cần lưu entity qua repository rồi đọc lại để xác nhận callback thực sự được đăng ký vào Spring Data R2DBC mapping infrastructure:

```java
StepVerifier.create(customerRepository.save(customer)
        .flatMap(saved -> customerRepository.findById(saved.getId())))
        .assertNext(loaded ->
                assertEquals("lan@example.com", loaded.getEmail()))
        .verifyComplete();
```

Các test nên kiểm tra:

- Callback được gọi cho entity đúng type.
- Entity đã được chuẩn hóa trước khi mapping.
- Giá trị đã có không bị ghi đè ngoài ý muốn.
- Callback được áp dụng khi insert và update theo yêu cầu.
- Entity immutable trả về instance mới được dùng.
- Callback phát lỗi thì không có dữ liệu được ghi.
- Nhiều callback chạy theo ordering mong muốn.
- Đường ghi bằng `DatabaseClient` hoặc `@Modifying` có hành vi riêng, không mặc định đi qua callback.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Callback không chạy | Bean chưa được đăng ký hoặc template không dùng callback infrastructure | Đăng ký Spring bean và kiểm tra `ReactiveEntityCallbacks` của template |
| Callback không compile | Dùng nhầm interface imperative/reactive hoặc sai package theo version | Dùng interface dành cho Spring Data R2DBC và kiểm tra chữ ký phiên bản |
| Thay đổi trong callback không được lưu | Callback tạo instance mới nhưng trả lại entity cũ | Trả đúng publisher chứa entity đã thay đổi |
| Save hoàn tất nhưng không có INSERT/UPDATE | Callback trả publisher rỗng | Phát entity bằng `Mono.just(...)` hoặc lỗi rõ ràng |
| Callback làm mỗi lần save tạo ID khác | Gán ID mới vô điều kiện | Chỉ tạo khi ID chưa có và xử lý newness detection |
| Database default không được dùng | Callback gán giá trị vào cột database quản lý | Để cột không được ghi hoặc dùng mapping generated/read-only phù hợp |
| Email vẫn bị trùng | Chỉ kiểm tra ở callback hoặc service | Thêm unique constraint và xử lý lỗi cạnh tranh |
| Save chậm bất thường | Callback thực hiện query hoặc HTTP call | Chuyển việc lấy dữ liệu sang application service |
| Timestamp bị ghi đè | Callback và auditing cùng quản lý một field | Chọn một nguồn có thẩm quyền |
| Callback gây lỗi không rõ nguyên nhân | Nuốt lỗi hoặc không phân loại lỗi chuẩn bị dữ liệu | Phát lỗi có ý nghĩa và xử lý ở đúng tầng |
| Bulk SQL không áp dụng chuẩn hóa | `DatabaseClient`/`@Modifying` bỏ qua entity lifecycle callback | Tái sử dụng logic chuẩn hóa ở tầng phù hợp |

## 21. Quy trình thiết kế BeforeConvertCallback

Khi cần chuẩn bị entity trước khi chuyển đổi trong Spring Data R2DBC, hãy xác định:

1. Thuộc tính nào cần chuẩn hóa hoặc bổ sung trước khi mapping?
2. Giá trị đó do ứng dụng hay database quản lý?
3. Quy tắc có phải invariant domain cần nằm trong constructor/factory/service không?
4. Callback có thể chạy lặp mà không tạo thay đổi ngoài ý muốn không?
5. Entity mutable hay immutable, và callback có trả đúng instance đã thay đổi không?
6. Callback reactive có trả publisher non-blocking, không gọi `block()` hoặc `subscribe()` không?
7. Callback có được đăng ký như bean và áp dụng cho đúng entity type không?
8. Có callback khác cùng lifecycle cần ordering không?
9. Các đường ghi bằng SQL tùy chỉnh có cần dùng chung quy tắc chuẩn hóa không?
10. Integration test đã xác nhận callback được gọi trong repository/template flow thực tế chưa?

`BeforeConvertCallback` là điểm mở rộng để chuẩn bị entity trước khi Spring Data R2DBC chuyển nó thành dữ liệu ghi. Callback phù hợp cho chuẩn hóa và bổ sung giá trị kỹ thuật có tính lặp an toàn, còn quy tắc domain phức tạp nên được thể hiện trong domain model hoặc application service. Khi callback được đăng ký đúng, trả publisher hợp lệ và không ghi đè giá trị do database quản lý, ứng dụng có thể thống nhất dữ liệu trước mapping mà vẫn giữ pipeline reactive rõ ràng.
