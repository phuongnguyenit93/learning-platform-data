# Định danh tài nguyên với Long, UUID và kiểu ID tùy chỉnh trong Spring Data REST

## 1. Định danh trong database và định danh trên URI

Spring Data REST xuất repository thành tài nguyên HTTP. Với collection path `/orders`, một tài nguyên đơn có thể được truy cập qua `/orders/42` hoặc `/orders/550e8400-e29b-41d4-a716-446655440000`. Theo mặc định, phần cuối URI là ID của entity trong datastore. Kiểu ID của repository phải tương thích với kiểu ID được khai báo trong entity:

```java
interface LongOrderRepository extends CrudRepository<LongOrder, Long> {
}

interface UuidOrderRepository extends CrudRepository<UuidOrder, UUID> {
}

interface CustomOrderRepository extends CrudRepository<CustomOrder, OrderId> {
}
```

Khi thiết kế API, cần phân biệt ba khái niệm:

- **Database identifier:** khóa mà persistence layer dùng để nhận diện hàng/entity, thường được đánh dấu bằng `@Id` hoặc `@EmbeddedId`.
- **Domain identifier:** kiểu và quy tắc định danh mà domain model sử dụng. Nó có thể là `Long`, `UUID` hoặc value object như `OrderId`.
- **Public resource identifier:** giá trị nằm trong URI mà client sử dụng để truy cập tài nguyên. Mặc định Spring Data REST lấy từ ID của entity, nhưng có thể tùy chỉnh bằng `EntityLookup`.

Ba giá trị này có thể giống nhau, nhưng không bắt buộc. Database có thể dùng Long để join hiệu quả trong khi API công bố UUID hoặc một mã public bất biến. Cần xác định rõ giá trị nào là nội bộ, giá trị nào xuất hiện trong URI và giá trị nào client được phép gửi.

Một định danh tốt cần duy nhất trong phạm vi xác định, ổn định trong suốt vòng đời tài nguyên và không được tái sử dụng theo cách khiến URI cũ trỏ sang tài nguyên khác. ID kỹ thuật cũng không nên bị nhầm với mã nghiệp vụ có thể thay đổi, ví dụ số hóa đơn hiển thị, email hoặc username.

## 2. Dùng Long làm định danh

Với Spring Data JPA, khóa số nguyên 64-bit thường được khai báo bằng `Long`:

```java
import jakarta.persistence.*;

@Entity
class Order {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_seq"
    )
    @SequenceGenerator(
        name = "order_seq",
        sequenceName = "order_seq",
        allocationSize = 50
    )
    private Long id;

    protected Order() {
    }
}

interface OrderRepository extends JpaRepository<Order, Long> {
}
```

Nếu database và provider phù hợp, `GenerationType.IDENTITY` cũng có thể dùng cột identity/auto-increment. `SEQUENCE` sử dụng sequence của database; `allocationSize` cho phép provider cấp trước một nhóm giá trị để giảm số lần gọi sequence. `GenerationType.AUTO` để provider lựa chọn chiến lược, vì vậy hành vi có thể khác theo provider và database.

Khi entity có ID là `42L`, item URI mặc định có dạng:

```http
GET /orders/42
```

**Ưu điểm của Long**

- Giá trị nhỏ, dễ đọc và dễ gỡ lỗi.
- Chỉ chiếm 8 byte ở dạng số nguyên 64-bit; index và khóa ngoại thường gọn.
- Sequence/identity được nhiều hệ quản trị cơ sở dữ liệu hỗ trợ tốt.
- Dễ dùng trong log, truy vấn SQL và công cụ quản trị.

**Giới hạn cần cân nhắc**

- ID tuần tự có thể làm lộ tương quan về số lượng hoặc tốc độ tạo dữ liệu.
- Client có thể thử lần lượt các ID để dò tài nguyên. Điều này không phải lỗ hổng nếu authorization được kiểm tra đúng, nhưng ID khó đoán cũng không phải lớp bảo mật.
- Việc tạo ID thường phụ thuộc database hoặc một dịch vụ cấp số chung, nên khó tạo độc lập ở nhiều node trước khi ghi dữ liệu.
- Sequence có thể có khoảng trống do rollback, cache hoặc node khởi động lại. Không giả định ID liên tiếp và không dùng ID để đếm số bản ghi.

Long phù hợp khi database là nơi cấp ID tập trung, kích thước index và join quan trọng, và việc ID có thể dự đoán không gây vấn đề về sản phẩm. Nếu không muốn lộ khóa tuần tự ra API, có thể giữ Long ở persistence layer và công bố một public ID riêng.

## 3. Dùng UUID làm định danh

UUID có độ dài 128 bit và thường được biểu diễn thành chuỗi hex có dấu gạch nối. Ví dụ:

```text
550e8400-e29b-41d4-a716-446655440000
```

Với Jakarta Persistence 3.1 trở lên và provider hỗ trợ, có thể dùng chiến lược sinh UUID:

```java
import jakarta.persistence.*;
import java.util.UUID;

@Entity
class UuidOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    protected UuidOrder() {
    }
}

interface UuidOrderRepository extends JpaRepository<UuidOrder, UUID> {
}
```

`GenerationType.UUID` thuộc Jakarta Persistence 3.1. Với phiên bản JPA hoặc provider cũ hơn, cần kiểm tra cách hỗ trợ UUID của provider; một số provider có annotation hoặc generator riêng. Không nên sao chép annotation đặc thù của Hibernate sang dự án khác mà chưa xác nhận tương thích.

Item URI có dạng:

```http
GET /orders/550e8400-e29b-41d4-a716-446655440000
```

**Ưu điểm của UUID**

- Có thể tạo ID ở nhiều service hoặc node mà không cần xin số tiếp theo từ sequence trung tâm.
- Xác suất trùng cực thấp khi dùng generator đúng chuẩn.
- URI ít tiết lộ thứ tự tạo và khó dò tuần tự hơn ID Long.
- Hữu ích khi dữ liệu được tạo offline, đồng bộ hoặc hợp nhất từ nhiều nguồn.

**Chi phí và giới hạn**

- UUID chiếm nhiều byte hơn Long; index và khóa ngoại thường lớn hơn.
- UUID ngẫu nhiên như version 4 có thể làm insert kém tuần tự, ảnh hưởng locality/cache và hiệu năng index ở một số database.
- URI dài hơn, khó đọc và khó nhập thủ công.
- UUID không phải bí mật và không thay thế authorization. Ai có UUID vẫn phải vượt qua kiểm tra quyền như với bất kỳ ID nào khác.
- UUID theo thời gian như version 7 có thể cải thiện thứ tự ghi trong một số workload, nhưng cần xác nhận thư viện, database và provider hỗ trợ đúng định dạng.

Dùng kiểu `UUID` trong Java thay vì lưu và xử lý chuỗi tùy tiện nếu persistence provider hỗ trợ ánh xạ phù hợp. Cách lưu vật lý có thể là kiểu UUID native, binary hoặc ký tự tùy database/dialect. Kiểm tra schema và index thực tế trước khi quyết định.

## 4. Kiểu ID tùy chỉnh: value object có kiểu mạnh

Trong domain model lớn, dùng `Long` hoặc `UUID` trực tiếp ở mọi nơi dễ dẫn đến truyền nhầm ID. Một method nhận hai tham số UUID có thể vô tình nhận `customerId` ở vị trí `orderId`; compiler không phân biệt được ý nghĩa của chúng.

Value object như `OrderId` tạo ra kiểu riêng, gom quy tắc parse/format và làm rõ ý nghĩa tham số. Với JPA, có thể ánh xạ value object thành `@EmbeddedId`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

@Embeddable
public class OrderId implements Serializable {

    @Column(name = "value", nullable = false)
    private UUID value;

    protected OrderId() {
        // JPA cần constructor không tham số.
    }

    public OrderId(UUID value) {
        this.value = Objects.requireNonNull(value);
    }

    public static OrderId from(String text) {
        return new OrderId(UUID.fromString(text));
    }

    public UUID value() {
        return value;
    }

    @Override
    public String toString() {
        return value.toString();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderId that)) return false;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
```

Entity và repository sử dụng kiểu ID này:

```java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;

@Entity
class CustomOrder {

    @EmbeddedId
    private OrderId id;

    protected CustomOrder() {
    }

    CustomOrder(OrderId id) {
        this.id = id;
    }

    public OrderId getId() {
        return id;
    }
}

interface CustomOrderRepository
        extends JpaRepository<CustomOrder, OrderId> {
}
```

Embedded ID cần có quy tắc `equals` và `hashCode` ổn định; các thuộc tính tham gia định danh không được thay đổi sau khi entity đã được lưu. Ví dụ trên dùng UUID bên trong để giá trị lưu trữ vẫn là một định danh scalar. Với composite ID thực sự gồm nhiều trường, cần đánh giá kỹ cách biểu diễn chúng thành một path segment.

### Chuyển đổi ID trên URI

URI item chứa text, trong khi repository có thể cần một đối tượng `OrderId`. Spring Data REST cho phép đăng ký converter thông qua `RepositoryRestConfigurer.configureConversionService`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.support.ConfigurableConversionService;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
class RestIdConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureConversionService(
            ConfigurableConversionService conversionService) {

        conversionService.addConverter(
            String.class,
            OrderId.class,
            OrderId::from
        );

        conversionService.addConverter(
            OrderId.class,
            String.class,
            OrderId::toString
        );
    }
}
```

Hai chiều chuyển đổi có hai vai trò:

- `String → OrderId`: phân tích path segment của request để tìm entity.
- `OrderId → String`: tạo giá trị định danh khi Spring Data REST dựng URI cho item resource.

Nếu chỉ đăng ký một chiều, một số luồng đọc có thể hoạt động trong khi việc tạo link hoặc dựng URI lại gặp lỗi chuyển đổi. Nếu chuỗi đầu vào sai định dạng, converter phải từ chối rõ ràng; không âm thầm chuyển chuỗi sai thành ID mặc định hoặc ID rỗng.

Converter của Spring không thay thế mapping persistence. Trong ví dụ trên, `@EmbeddedId` quyết định cách JPA lưu khóa; converter của Spring Data REST xử lý biểu diễn ID qua ranh giới URI. Nếu muốn đưa custom ID vào JSON body, Jackson còn có quy tắc serializer/deserializer riêng. Đây là các ranh giới khác nhau.

Nếu chỉ cần kiểu mạnh trong code mà không cần thay đổi kiểu ID persistence, có thể giữ database ID là Long/UUID và tạo value object ở application/domain layer. Chỉ thêm custom mapping vào JPA khi lợi ích về an toàn kiểu đủ bù chi phí mapping, truy vấn và bảo trì.

## 5. Dùng public ID hoặc slug thay cho khóa database

Entity có thể dùng database ID là Long nhưng API muốn URI dễ đọc hoặc ổn định theo một khóa công khai khác. Ví dụ, khách hàng được truy cập qua `/customers/acme-vn` thay vì `/customers/73`. Đây là thay đổi cách định danh tài nguyên công khai; nó khác với việc đổi kiểu khóa chính của database.

Spring Data REST cung cấp `EntityLookup` và API `withEntityLookup()` để ánh xạ giá trị dùng trong URI sang entity. Giả sử `Customer` có `publicId` duy nhất và repository có `Optional<Customer> findByPublicId(String publicId)`:

```java
@Component
class CustomerResourceLookup implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.withEntityLookup()
            .forRepository(CustomerRepository.class)
            .withIdMapping(Customer::getPublicId)
            .withLookup(CustomerRepository::findByPublicId);
    }
}
```

Trong cấu hình này:

- `withIdMapping` lấy public ID từ entity để tạo item URI.
- `withLookup` dùng giá trị trên URI để tìm entity qua repository.
- Database vẫn có thể dùng Long làm khóa chính và khóa ngoại.
- Repository method tra cứu phải tìm duy nhất một entity; public ID cần unique constraint ở database.

Có thể dùng username, slug hoặc mã public được sinh riêng. Tuy nhiên, giá trị dùng trong URI cần ổn định và không đổi tùy ý. Nếu username có thể đổi, dùng username làm URI identity có thể làm URL cũ mất hiệu lực và phá bookmark, cache hoặc liên kết đã lưu. Với API dài hạn, public ID bất biến thường an toàn hơn thuộc tính nghiệp vụ có thể đổi.

`EntityLookup` không tự tạo tính duy nhất hoặc index. Cần khai báo unique constraint/index, xử lý xung đột khi tạo mới và quyết định cách migration nếu public ID thay đổi. Nếu cần hỗ trợ URI cũ, phải thiết kế alias/redirect hoặc endpoint tương thích riêng.

## 6. ID có xuất hiện trong JSON không?

Spring Data REST thường ẩn thuộc tính ID khỏi representation JSON mặc định. Client vẫn nhận được self link trong HAL, ví dụ:

```json
{
  "orderNumber": "SO-2026-001",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    }
  }
}
```

URI self link là định danh tài nguyên mà client nên lưu và theo dõi. Không cần lặp lại ID trong body chỉ để client có thể nhận diện item.

Nếu thực sự cần ID như một thuộc tính JSON, có thể cấu hình rõ domain type được phép lộ ID:

```java
@Configuration
class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.exposeIdsFor(Order.class);
    }
}
```

`exposeIdsFor(Order.class)` làm ID xuất hiện như thuộc tính thông thường trong representation của kiểu đó. Đây là quyết định về representation, không phải điều kiện để URI item hoạt động. Chỉ bật cho những domain type cần thiết; không nên bật toàn cục theo thói quen.

Nếu response dùng DTO hoặc projection, hãy xác định rõ trường ID nào được trả về và vì sao. Không để ID persistence xuất hiện trong hợp đồng công khai chỉ vì entity có field đó.

## 7. Quy tắc thiết kế URI và bảo mật

ID trở thành một phần của path, do đó cần lưu ý cách biểu diễn:

- Dùng một dạng canonical duy nhất. UUID nên dùng định dạng chuẩn; slug nên có quy tắc chữ hoa/thường và chuẩn hóa Unicode rõ ràng.
- Tránh ID chứa dấu gạch chéo `/`, dấu hỏi `?`, dấu thăng `#` hoặc ký tự điều khiển. Những ký tự này có ý nghĩa đặc biệt trong URI và có thể gây lỗi phân tách path hoặc encoding.
- Nếu dùng chuỗi có ký tự đặc biệt, để framework URI encode/decode đúng cách; không tự nối chuỗi path bằng phép cộng.
- Không lấy ID bằng cách cắt chuỗi URL thủ công. Client nên theo self link và các link quan hệ do server trả về.
- Giữ ID bất biến. Không tái sử dụng ID đã xóa cho một tài nguyên khác.
- Kiểm tra quyền truy cập ở mỗi request. ID Long tuần tự hay UUID ngẫu nhiên đều không thay thế authentication/authorization.
- Nếu cần một liên kết chia sẻ bí mật, hãy tạo token riêng có entropy đủ lớn, phạm vi quyền và thời hạn; đừng coi database ID hoặc UUID tài nguyên là bearer secret.

Một URI khó đoán có thể giảm việc dò tuần tự, nhưng không ngăn người dùng có quyền thấp truy cập tài nguyên của người dùng khác nếu server thiếu kiểm tra quyền. Kiểm thử cả trường hợp ID hợp lệ nhưng người gọi không có quyền, không chỉ trường hợp ID không tồn tại.

## 8. Kiểm thử và lựa chọn loại ID

Khi triển khai ID cho repository được xuất, hãy kiểm tra ít nhất các trường hợp sau:

1. Tạo entity và xác nhận server trả URI item đúng định dạng; nếu response có `Location`, giá trị phải trỏ tới tài nguyên vừa tạo.
2. Đọc collection và item; xác nhận self link dùng đúng ID và có thể theo được.
3. Đọc item với ID sai định dạng, ID không tồn tại và ID tồn tại nhưng người gọi không có quyền. Ba trường hợp này có ý nghĩa khác nhau và cần phản hồi nhất quán.
4. Với UUID/custom ID, kiểm tra chuyển đổi hai chiều giữa path segment và kiểu Java.
5. Với `EntityLookup`, xác nhận URI được tạo từ public key và lookup tìm đúng một entity.
6. Kiểm tra ID có được ẩn hoặc xuất trong JSON đúng theo cấu hình.
7. Kiểm tra association link, repository query method và endpoint liên quan vẫn hoạt động sau khi thay đổi kiểu ID.
8. Kiểm tra database schema, unique constraint, index, khóa ngoại và migration trên database thật dùng trong môi trường triển khai.

| Nhu cầu | Lựa chọn thường phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| Database cấp số tập trung, cần khóa gọn | `Long` | Không dựa vào tính liên tiếp; authorization phải độc lập. |
| Sinh ID ở nhiều node hoặc đồng bộ dữ liệu | `UUID` | Kích thước index, cách lưu và generator của provider. |
| Muốn phân biệt kiểu ID trong domain code | Value object như `OrderId` | JPA mapping, equals/hashCode và converter URI. |
| Muốn URI dùng mã công khai thay khóa database | `EntityLookup` với public ID/slug | Tính duy nhất, bất biến, index và tương thích URL cũ. |
| Có khóa ghép nhiều thành phần | `@EmbeddedId` hoặc public ID scalar | Cách mã hóa một giá trị URI rõ ràng; tránh phơi cấu trúc khóa nội bộ. |

Không có một kiểu ID tốt nhất cho mọi ứng dụng. Hãy chọn theo cách tạo dữ liệu, yêu cầu lưu trữ, ranh giới domain, mức độ ổn định của API và nhu cầu tích hợp. Spring Data REST có thể xuất Long, UUID hoặc kiểu ID tùy chỉnh, miễn repository, persistence mapping, conversion service và quy tắc URI cùng thống nhất về một cách biểu diễn.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing item resource URIs and EntityLookup](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Data Commons — Custom conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html)
- [Jakarta Persistence — Specification](https://jakarta.ee/specifications/persistence/)
