# Ràng buộc về giá trị null và thuộc tính sắp xếp trong projection

## 1. Vì sao null và sort quan trọng với projection?

Projection giới hạn hình dạng dữ liệu repository trả về. Khi dùng interface projection hoặc DTO, cần xác định rõ trường nào có thể null, trường nào được dùng để sắp xếp và liệu các giá trị sort có được trả về cùng kết quả hay không.

Với truy vấn thông thường, một projection có thể bỏ qua nhiều thuộc tính Entity. Nhưng khi dùng scrolling theo keyset, Spring Data phải đọc các giá trị khóa sắp xếp từ từng kết quả để tạo vị trí tiếp theo. Vì vậy, các thuộc tính sort phải đáp ứng điều kiện chặt hơn: có giá trị khác null và được đưa vào projection.

Ba khái niệm cần tách biệt:

- **Nullability của projection:** getter có thể trả null hay dùng wrapper như `Optional` để biểu diễn giá trị vắng mặt.
- **Sort property:** tên thuộc tính mà `Sort` hoặc `ORDER BY` sử dụng phải được Spring Data/JPA phân giải được thành property của domain hoặc alias trong query.
- **Keyset scrolling:** các property dùng để tạo keyset phải non-null và xuất hiện trong kết quả projection để framework đọc được giá trị tiếp tục.

## 2. Giá trị null trong interface projection

Giả sử Entity `Customer` có `phone` và `lastContactAt` là các trường tùy chọn. Nếu cột database chứa NULL, accessor kiểu tham chiếu thông thường có thể trả về null:

```java
public interface CustomerContactView {
    Long getId();
    String getEmail();
    String getPhone();
    Instant getLastContactAt();
}
```

Caller phải kiểm tra null trước khi sử dụng:

```java
CustomerContactView view = repository.findContactById(id)
    .orElseThrow();

if (view.getPhone() != null) {
    sendSms(view.getPhone());
}
```

Cách an toàn hơn cho thuộc tính thực sự tùy chọn là dùng nullable wrapper. Spring Data hỗ trợ các wrapper sau trong getter của interface projection:

- `java.util.Optional`
- `com.google.common.base.Optional`
- `scala.Option`
- `io.vavr.control.Option`

Ví dụ với Java Optional:

```java
public interface CustomerContactView {
    Long getId();
    String getEmail();
    Optional<String> getPhone();
    Optional<Instant> getLastContactAt();
}
```

Nếu giá trị backing property khác null, getter trả wrapper ở trạng thái present. Nếu giá trị backing là null, getter trả wrapper rỗng, ví dụ `Optional.empty()`.

```java
view.getPhone().ifPresent(this::sendSms);

String phone = view.getPhone().orElse("Chưa cung cấp");
Instant lastContact = view.getLastContactAt().orElse(null);
```

Không gọi `get()` mà chưa kiểm tra `isPresent()` hoặc chưa có fallback phù hợp. `Optional` giúp biểu diễn null rõ ràng; nó không làm cho dữ liệu bắt buộc trở thành tùy chọn về mặt nghiệp vụ.

## 3. Null trong DTO projection

DTO class hoặc record nhận dữ liệu qua constructor. Nếu cột có thể NULL, dùng kiểu tham chiếu có thể chứa null, ví dụ `String`, `Long`, `Integer`, `BigDecimal` hoặc `Instant` thay vì primitive như `long`, `int` hay `boolean`.

```java
public record CustomerContactRow(
    Long id,
    String email,
    String phone,
    Instant lastContactAt
) {
}
```

Không nên khai báo `int age` nếu query có thể trả NULL cho age. Primitive không biểu diễn được null; tùy đường mapping, kết quả có thể lỗi khi khởi tạo hoặc không thể giữ đúng semantics. Dùng `Integer age` nếu trường đó tùy chọn.

Với DTO, kiểm tra constructor có đúng số lượng, thứ tự và kiểu expression trong query. `Optional` thường hữu ích ở interface projection; với DTO record, các component tham chiếu nullable thường đơn giản và dễ tương thích hơn. Nếu muốn contract DTO luôn không null, hãy bảo đảm query/domain/schema cung cấp giá trị hợp lệ và validate tại tầng thích hợp.

## 4. Phân biệt nullability của Entity, projection và database

Ba lớp ràng buộc có vai trò khác nhau:

| Lớp | Ví dụ | Tác dụng |
| --- | --- | --- |
| Java/Entity | `String phone` hoặc `Optional` ở projection | Biểu diễn giá trị trong ứng dụng |
| Bean Validation | `@NotNull`, `@NotBlank` | Kiểm tra object ở thời điểm validation |
| Database | `NOT NULL`, `CHECK` | Bảo vệ dữ liệu tại nơi lưu trữ |

`@Column(nullable = false)` mô tả mapping/schema generation; với schema được quản lý bằng Flyway hoặc Liquibase, migration phải thực sự tạo constraint `NOT NULL`. `@NotNull` kiểm tra ở tầng ứng dụng khi validation được kích hoạt. Hai annotation không thay thế ràng buộc database.

Nếu một property được dùng làm keyset sort, nó cần không null ở tất cả bản ghi có thể xuất hiện trong scroll query. Chỉ đặt `@NotNull` trên DTO hoặc projection không sửa được dữ liệu null đã tồn tại trong database. Hãy kiểm tra dữ liệu, migration, constraint và mọi đường ghi dữ liệu.

## 5. Thuộc tính Sort phải phân giải được

Spring Data JPA yêu cầu mỗi property trong `Sort.Order` phải phân giải được thành property của domain model hoặc alias được dùng trong query. Không thể tùy ý truyền tên cột hoặc một biểu thức bất kỳ và mong framework tự hiểu.

Ví dụ Entity có property Java `createdAt` được ánh xạ xuống cột `created_at`. Sort phải dùng tên property Java:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);
```

Không dùng `Sort.by("created_at")` chỉ vì đó là tên cột vật lý. Với derived query, property path trong Sort phải thuộc domain model. Với `@Query`, property phải là state-field path hợp lệ hoặc alias được query khai báo.

## 6. Sort cùng interface projection

Giả sử projection chỉ trả về ID và email:

```java
public interface CustomerListView {
    Long getId();
    String getEmail();
}
```

Repository có thể nhận Sort:

```java
List<CustomerListView> findByStatus(
    CustomerStatus status,
    Sort sort
);
```

Với truy vấn thông thường, Sort có thể tham chiếu property của Entity như `createdAt` ngay cả khi getter `getCreatedAt()` không có trong interface projection. Database vẫn có thể sắp xếp theo property đó mà caller không nhận giá trị trong projection.

Điều này khác với keyset scrolling: keyset phải đọc các giá trị sort từ từng kết quả để tạo điều kiện cho window tiếp theo. Vì thế, nếu `createdAt` được dùng làm keyset property thì projection phải khai báo `getCreatedAt()` và query phải trả property đó. Một property chỉ được dùng để sort nhưng bị lược khỏi projection có thể khiến keyset extraction thất bại.

## 7. Alias trong JPQL projection

Khi query chọn scalar hoặc expression, đặt alias khớp với accessor của interface projection:

```java
public interface CustomerScoreView {
    Long getId();
    String getEmail();
    Integer getScore();
}
```

```java
@Query("""
    select c.id as id,
           c.email as email,
           c.score as score
    from Customer c
    where c.status = :status
    """)
List<CustomerScoreView> findScoreViews(
    @Param("status") CustomerStatus status,
    Sort sort
);
```

`id`, `email` và `score` là alias cho tuple/projection. Khi sort theo property domain, dùng property hợp lệ của Entity. Nếu cần sort theo expression đã chọn, dùng alias mà query thực sự khai báo, ví dụ `score` trong ví dụ trên. Alias phải khớp chính xác tên được provider trả về; kiểm thử query với JPA provider/database thật.

Spring Data JPA kiểm tra các Order trong Sort để bảo đảm chúng là property hoặc alias tham chiếu được. Một path expression không hợp lệ có thể gây exception khi tạo/thực thi query.

## 8. Sort theo biểu thức và JpaSort.unsafe

Spring Data JPA mặc định từ chối các Sort expression chứa function call để tránh ghép biểu thức không an toàn vào query. Khi có nhu cầu thật sự, `JpaSort.unsafe` cho phép thêm biểu thức ORDER BY không qua kiểm tra property path thông thường:

```java
Sort sort = JpaSort.unsafe(
    Sort.Direction.ASC,
    "LENGTH(firstName)"
);
```

Chỉ dùng biểu thức cố định do developer kiểm soát. Không đưa tên cột, function hay chuỗi sort trực tiếp từ request người dùng vào `JpaSort.unsafe`; bind parameter chỉ dành cho giá trị, không bảo vệ cấu trúc ORDER BY được ghép vào query.

Nếu API cho phép sort động, tạo allow-list từ các lựa chọn được hỗ trợ rồi ánh xạ sang `Sort.by("createdAt")`, `Sort.by("email")` hoặc biểu thức đã kiểm soát. Không coi projection getter là một identifier SQL tùy ý.

## 9. Điều khiển vị trí NULL khi sắp xếp

Spring Data cung cấp null-handling hint cho `Sort.Order`: `nullsFirst()`, `nullsLast()` và `nullsNative()`.

```java
Sort sort = Sort.by(
    Sort.Order.asc("lastContactAt").nullsLast(),
    Sort.Order.asc("id")
);
```

Ý nghĩa:

| Cách khai báo | Ý định |
| --- | --- |
| `nullsFirst()` | Đề nghị giá trị NULL đứng trước giá trị có dữ liệu |
| `nullsLast()` | Đề nghị giá trị NULL đứng sau giá trị có dữ liệu |
| `nullsNative()` | Để datastore/database quyết định thứ tự mặc định |

Đây là hint cho datastore và có thể không được database/provider tôn trọng. Thứ tự NULL mặc định khác nhau theo database và chiều sort. Nếu thứ tự phải nhất quán, kiểm tra SQL sinh ra và chạy integration test trên database mục tiêu.

Với query JPQL cố định, có thể thể hiện null ordering tường minh bằng `CASE`:

```java
@Query("""
    select c
    from Customer c
    order by
      case when c.lastContactAt is null then 1 else 0 end asc,
      c.lastContactAt asc,
      c.id asc
    """)
List<Customer> findAllOrderedWithNullsLast();
```

Ở đây giá trị không null có khóa 0 và được xếp trước; giá trị null có khóa 1 và xếp sau. `id` là tie-breaker để thứ tự ổn định. Đây là sort cố định trong JPQL; không kết hợp thêm một Sort động mâu thuẫn mà không xác định rõ thứ tự cuối cùng.

## 10. Keyset scrolling yêu cầu sort property không null

Keyset scrolling dùng các giá trị sort của hàng cuối trong `Window` để tạo điều kiện WHERE cho lần đọc tiếp theo. Các phép so sánh và cách database xử lý NULL không đồng nhất; vì vậy Spring Data yêu cầu các keyset property phải non-nullable. Dùng `nullsFirst()` hoặc `nullsLast()` không khắc phục được giới hạn này.

Ví dụ một Entity có `createdAt` bắt buộc:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @Column(nullable = false)
    private Instant createdAt;

    private String email;
    private CustomerStatus status;
}
```

Projection phải chứa tất cả property được dùng làm sort key:

```java
public interface CustomerScrollView {
    Long getId();
    Instant getCreatedAt();
    String getEmail();
}
```

Repository dùng Window và KeysetScrollPosition:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Window<CustomerScrollView> findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus status,
        KeysetScrollPosition position
    );
}
```

`createdAt` và `id` đều xuất hiện trong projection. `createdAt` phải non-null trong mọi hàng có thể được đọc. Khóa chính giúp xác định thứ tự duy nhất khi nhiều khách hàng có cùng timestamp. Spring Data có thể bổ sung khóa chính hoặc các thành phần khóa chính còn thiếu vào thứ tự keyset; khai báo rõ `id` trong ví dụ giúp hợp đồng sort dễ hiểu.

## 11. Duyệt các Window theo keyset

Ví dụ dùng `WindowIterator` để xử lý từng window:

```java
WindowIterator<CustomerScrollView> customers = WindowIterator
    .of(position -> repository.findFirst100ByStatusOrderByCreatedAtAscIdAsc(
        CustomerStatus.ACTIVE, position
    ))
    .startingAt(ScrollPosition.keyset());

while (customers.hasNext()) {
    CustomerScrollView customer = customers.next();
    process(customer.getId(), customer.getEmail());
}
```

Ví dụ cần các import từ Spring Data tương ứng, gồm `WindowIterator`, `ScrollPosition` và `Window`. API scrolling phụ thuộc phiên bản Spring Data đang dùng. Query method trả `Window<T>` và nhận `KeysetScrollPosition` là dạng thường dùng cho keyset scrolling.

Không được lược `createdAt` khỏi projection chỉ vì ứng dụng không hiển thị timestamp. Framework vẫn cần giá trị đó để tạo vị trí tiếp theo. Nếu không muốn trả trường sort cho client, giữ nó trong projection nội bộ rồi map sang DTO response khác ở service.

## 12. Nếu sort property có thể null thì chọn cách nào?

Keyset scrolling không phù hợp với sort key nullable. Có một số lựa chọn:

1. **Dùng offset-based scrolling hoặc pagination** nếu cần sắp xếp cả giá trị NULL. Có thể dùng `nullsFirst()`/`nullsLast()` như hint và kiểm thử hành vi thực tế.
2. **Chọn một sort key khác luôn non-null**, chẳng hạn `createdAt` hoặc ID, nếu vẫn đáp ứng thứ tự nghiệp vụ.
3. **Tạo thuộc tính sort đã chuẩn hóa và lưu không null** nếu nghiệp vụ cần thứ tự dựa trên giá trị tùy chọn. Ví dụ persist một `sortTimestamp` được tính theo quy tắc rõ ràng và có NOT NULL constraint.
4. **Tách tập dữ liệu null và non-null** thành các luồng riêng nếu yêu cầu nghiệp vụ cần xử lý hai nhóm theo thứ tự cụ thể.

Không chỉ dùng `COALESCE` trong ORDER BY rồi giả định keyset scrolling sẽ hoạt động: keyset cần các property được ánh xạ và đọc lại từ kết quả để tái tạo predicate. Expression tùy ý hoặc alias tính toán có thể không đáp ứng các yêu cầu này.

## 13. Sort ổn định và index

Scroll cần một thứ tự ổn định. Nếu sort chỉ theo timestamp có nhiều bản ghi cùng thời điểm, thứ tự giữa các bản ghi đó không được xác định đầy đủ. Thêm khóa duy nhất làm tie-breaker:

```java
Sort sort = Sort.by(
    Sort.Order.asc("createdAt"),
    Sort.Order.asc("id")
);
```

Keyset mechanism có thể tự bổ sung primary key hoặc phần còn thiếu của composite key để tạo thứ tự duy nhất. Tuy vậy, khai báo rõ tie-breaker giúp người đọc hiểu thứ tự mong muốn và dễ kiểm thử.

Keyset scrolling hiệu quả nhất khi database có index phù hợp với các trường lọc và sort. Với query lọc theo status rồi sort theo `createdAt, id`, cân nhắc index ghép tương ứng theo workload và database. Không tạo index chỉ dựa trên tên property; xem execution plan và số liệu truy vấn.

## 14. Stream và tài nguyên

Projection cũng có thể là kiểu phần tử của repository method trả `Stream<T>`. Stream cho phép xử lý lần lượt thay vì materialize toàn bộ kết quả thành collection, nhưng nó có trạng thái và có thể giữ cursor/resource của provider hoặc JDBC.

```java
@Transactional(readOnly = true)
public void exportActiveCustomers() {
    try (Stream<CustomerContactView> stream =
            repository.streamByStatus(CustomerStatus.ACTIVE)) {
        stream.forEach(this::writeCustomerRow);
    }
}
```

Đảm bảo stream được đóng bằng try-with-resources và được tiêu thụ trong transaction phù hợp. `Stream<T>` không tự bảo đảm driver thực sự tải dữ liệu theo từng phần nhỏ; fetch size và hành vi provider/driver ảnh hưởng việc buffering. Với dữ liệu rất lớn, đo bộ nhớ và kiểm tra cấu hình JDBC.

Projection nhẹ giúp giảm dữ liệu mỗi row, nhưng nếu stream projection chứa các association hoặc getter kích hoạt lazy loading, vẫn có thể phát sinh N+1. Chỉ chọn các trường cần thiết và kiểm tra SQL.

## 15. Lỗi thường gặp

**Optional getter vẫn trả null.** Kiểm tra interface projection thực sự được Spring Data tạo, accessor trả đúng wrapper được hỗ trợ và query alias/property khớp.

**Sort báo không tìm thấy property.** Dùng tên property Java của Entity hoặc alias thực sự được query khai báo; không dùng tên cột vật lý trừ khi đó là alias phù hợp.

**Sort theo getter projection không có trong Entity.** Getter không tự tạo property domain. Với query projection, khai báo alias phù hợp; với derived query, sort phải phân giải được theo domain model.

**Keyset scrolling lỗi khi projection bỏ trường sort.** Thêm mọi sort property và ID cần thiết vào interface/DTO projection.

**Keyset trả thiếu hoặc bỏ sót hàng có NULL.** Keyset sort property phải non-null. Dùng offset scrolling hoặc chọn sort key không null.

**`nullsLast()` không cho kết quả giống mọi database.** Đây chỉ là hint. Kiểm tra SQL/provider/dialect; dùng CASE trong JPQL cố định nếu cần semantics rõ và portable hơn.

**Window lặp hoặc bỏ qua hàng khi có cùng giá trị sort.** Bổ sung khóa duy nhất làm tie-breaker và kiểm tra các giá trị sort có thay đổi trong lúc scroll hay không.

**Stream giữ connection lâu hoặc dùng nhiều bộ nhớ.** Đóng stream, giới hạn thời gian xử lý, kiểm tra transaction/fetch size và cân nhắc Window-based scrolling.

## 16. Checklist thiết kế projection có sort/scroll

- Xác định property nào nullable và biểu diễn rõ bằng wrapper/kiểu tham chiếu phù hợp.
- Không dùng primitive cho giá trị có thể null.
- Với interface projection, accessor phải khớp property Java; query scalar cần alias đúng.
- Với Sort, chỉ dùng property domain hoặc alias được query hỗ trợ.
- Chỉ dùng `JpaSort.unsafe` với expression cố định do developer kiểm soát.
- Xem `nullsFirst`, `nullsLast`, `nullsNative` là hint và kiểm thử trên database mục tiêu.
- Với keyset scrolling, mọi sort property phải non-null và xuất hiện trong projection.
- Bao gồm ID hoặc các thành phần khóa chính cần thiết để định vị kết quả; bảo đảm thứ tự ổn định.
- Nếu sort key nullable, chọn offset scrolling hoặc một sort key không null.
- Đóng Stream và kiểm tra fetch size, transaction, N+1 và bộ nhớ.

Nullability của projection quyết định cách caller xử lý dữ liệu thiếu; thuộc tính Sort quyết định thứ tự truy vấn; keyset scrolling còn cần các giá trị sort không null và có mặt trong projection. Thiết kế đúng ba phần này giúp projection vừa gọn cho ứng dụng vừa đủ dữ liệu để phân trang/cuộn ổn định.