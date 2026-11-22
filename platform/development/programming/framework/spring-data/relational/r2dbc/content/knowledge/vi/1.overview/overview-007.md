# Giới hạn phạm vi: R2DBC không cung cấp đầy đủ cơ chế ORM

R2DBC được thiết kế để truy cập cơ sở dữ liệu quan hệ theo mô hình reactive, với các thao tác I/O không chặn. Tuy nhiên, cần phân biệt **truy cập cơ sở dữ liệu reactive**, **ánh xạ đối tượng sang dữ liệu quan hệ** và **một hệ thống ORM đầy đủ**. Ba khái niệm này có liên quan nhưng không đồng nghĩa.

R2DBC là một SPI (Service Provider Interface) cho phép ứng dụng làm việc với driver cơ sở dữ liệu thông qua các API reactive. Bản thân R2DBC không biết lớp Java nào đại diện cho bảng nào, không quản lý vòng đời của entity và không tự đồng bộ trạng thái object với database.

Spring Data R2DBC bổ sung lớp ánh xạ object-row, repository và template để ứng dụng thao tác với entity thuận tiện hơn. Dù vậy, Spring Data R2DBC được xây dựng theo mô hình ánh xạ dữ liệu quan hệ và aggregate, chứ không nhằm tái tạo toàn bộ cơ chế của JPA/Hibernate. Vì vậy, có thể gọi đây là giải pháp object mapping cho cơ sở dữ liệu quan hệ, nhưng không nên mặc định rằng nó có mọi tính năng ORM quen thuộc.

## 1. Những gì Spring Data R2DBC cung cấp

Spring Data R2DBC vẫn có nhiều chức năng ở tầng domain và persistence:

- **Ánh xạ hàng dữ liệu thành object:** các annotation như `@Table`, `@Id`, `@Column` và `@Transient` mô tả cách entity tương ứng với bảng và cột. Spring Data chuyển đổi giá trị giữa kiểu Java và kiểu dữ liệu mà driver trả về.
- **Repository reactive:** `ReactiveCrudRepository` cung cấp các thao tác CRUD trả về kiểu reactive như `Mono` và `Flux`. Spring Data cũng có thể tạo truy vấn từ tên phương thức trong những trường hợp được hỗ trợ.
- **Template và truy vấn tùy chỉnh:** `R2dbcEntityTemplate` cung cấp API thao tác entity ở mức thấp hơn repository. Khi cần kiểm soát câu SQL, có thể dùng `@Query` hoặc `DatabaseClient`.
- **Ánh xạ aggregate:** Spring Data Relational hỗ trợ mô hình aggregate root và các object thuộc về aggregate đó. `@MappedCollection` có thể dùng để ánh xạ collection các object phụ thuộc sang bảng riêng.
- **Một số tiện ích persistence:** tùy cấu hình, ứng dụng có thể dùng custom converter, auditing và optimistic locking thông qua trường có `@Version`.

Các chức năng trên giúp giảm lượng mã truy cập dữ liệu thủ công. Chúng không tự động biến một object graph bất kỳ thành một đồ thị entity được quản lý đầy đủ như trong ORM truyền thống.

## 2. Những cơ chế ORM không được cung cấp đầy đủ

### 2.1 Không có persistence context và identity map kiểu JPA

Trong JPA, `EntityManager` quản lý một persistence context. Trong phạm vi context đó, ORM theo dõi các entity đã được nạp và thường duy trì một instance đại diện cho cùng một định danh entity. Persistence context cũng là nơi ORM quản lý trạng thái của entity trong một đơn vị công việc.

Spring Data R2DBC không có `EntityManager` hay persistence context tương đương. Mỗi lần thực hiện một truy vấn, kết quả được ánh xạ thành object theo truy vấn đó. Ứng dụng không nên giả định rằng hai lần đọc cùng một hàng sẽ trả về cùng một instance Java, hoặc một object đã đọc sẽ được tự động theo dõi trong suốt một phiên làm việc.

Điều này ảnh hưởng đến cách viết nghiệp vụ: nếu một thao tác cần đọc, thay đổi và lưu dữ liệu, luồng xử lý phải thể hiện rõ các bước đó.

### 2.2 Không có dirty checking tự động

Với ORM như Hibernate, thay đổi thuộc tính của entity đang được quản lý có thể được phát hiện khi flush persistence context. Spring Data R2DBC không theo dõi mọi thay đổi trên object trong bộ nhớ.

Ví dụ, đoạn mã sau chỉ thay đổi object đã được nạp:

```java
repository.findById(orderId)
    .doOnNext(order -> order.setStatus("PAID"));
```

Đoạn mã này không tự tạo lệnh `UPDATE`. Muốn ghi thay đổi, ứng dụng phải gọi thao tác lưu và nối thao tác đó vào reactive chain:

```java
repository.findById(orderId)
    .flatMap(order -> {
        order.setStatus("PAID");
        return repository.save(order);
    });
```

`save` là một thao tác persistence tường minh. Nó không phải tín hiệu để một persistence context âm thầm quét và phát hiện mọi thay đổi trên các object liên quan.

### 2.3 Không có lazy loading qua proxy

Một ORM truyền thống có thể tạo proxy cho quan hệ và chỉ truy vấn dữ liệu liên quan khi ứng dụng truy cập thuộc tính đó. Spring Data R2DBC không cung cấp cơ chế lazy loading kiểu này.

Khi một entity chứa mã định danh của entity khác, việc đọc entity thứ hai phải được thể hiện bằng một truy vấn riêng hoặc bằng một câu SQL có join. Việc gọi một getter không tự phát sinh truy vấn mạng để tải quan hệ.

Đây là khác biệt quan trọng khi chuyển một domain model từ JPA sang R2DBC. Một thuộc tính từng được dùng để truy cập lazy relationship trong JPA không thể được giữ nguyên với kỳ vọng rằng Spring Data R2DBC sẽ tự tải dữ liệu tương ứng.

### 2.4 Không quản lý mọi quan hệ và cascade như ORM đầy đủ

Spring Data Relational khuyến khích thiết kế dữ liệu theo aggregate. Aggregate root là điểm vào để lưu một nhóm object thuộc cùng một ranh giới nhất quán. Với quan hệ sở hữu bên trong aggregate, `@MappedCollection` có thể mô tả các object phụ thuộc được lưu cùng aggregate root.

Ví dụ minh họa:

```java
@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private String customerId;

    @MappedCollection(idColumn = "order_id")
    private List<OrderLine> lines;
}

public class OrderLine {
    private String productCode;
    private int quantity;
}
```

Trong mô hình này, các dòng hàng là thành phần của đơn hàng. `@MappedCollection` mô tả cách ánh xạ collection phụ thuộc; nó không tạo ra một hệ thống quản lý quan hệ tổng quát với đầy đủ cascade, proxy và đồng bộ trạng thái như JPA.

Với một aggregate khác, chẳng hạn `Customer`, đơn hàng thường giữ định danh tham chiếu đến khách hàng. Ứng dụng chủ động tải `Customer` khi cần và quyết định cách lưu thay đổi của từng aggregate. Spring Data R2DBC không tự đi qua toàn bộ object graph để nạp và lưu mọi entity được tham chiếu.

Vì vậy, cần xác định rõ object nào thuộc cùng aggregate, object nào chỉ được tham chiếu bằng ID, và thao tác nào chịu trách nhiệm lưu từng aggregate.

### 2.5 Không dùng JPQL/HQL để truy vấn object graph

Spring Data R2DBC hỗ trợ derived query và truy vấn tùy chỉnh, nhưng truy vấn tùy chỉnh được viết bằng SQL của cơ sở dữ liệu. Không có `JPQL` hoặc `HQL` tương đương để mô tả truy vấn trên một mô hình entity trừu tượng như JPA/Hibernate.

Khi cần kết hợp dữ liệu từ nhiều bảng, ứng dụng thường viết `JOIN` trong SQL bằng `@Query`, `DatabaseClient` hoặc API thích hợp của `R2dbcEntityTemplate`. Kết quả có thể được ánh xạ vào entity hoặc DTO/projection phù hợp.

Ví dụ, truy vấn lấy thông tin đơn hàng cùng tên khách hàng có thể được viết rõ ràng như sau:

```java
public record OrderSummary(Long orderId, String customerName) {}

@Query("""
    SELECT o.id AS orderId, c.name AS customerName
    FROM purchase_order o
    JOIN customer c ON c.id = o.customer_id
    WHERE o.id = :id
    """)
Mono<OrderSummary> findSummaryById(Long id);
```

SQL cho biết chính xác bảng nào được kết hợp và cột nào được trả về. Cách làm này cho phép kiểm soát truy vấn, nhưng trách nhiệm chọn join, projection và chiến lược tải dữ liệu thuộc về người phát triển.

### 2.6 Không tự quản lý schema như một ORM có DDL generation

Spring Data R2DBC tập trung vào ánh xạ và truy cập dữ liệu. Không nên kỳ vọng các annotation entity sẽ tự động tạo và tiến hóa schema theo kiểu DDL generation thường gặp trong một số cấu hình ORM.

Việc tạo bảng, thêm cột, tạo index và quản lý phiên bản schema nên được thực hiện bằng migration tool hoặc quy trình quản trị schema của dự án. Các annotation ánh xạ cần nhất quán với schema thực tế.

## 3. So sánh phạm vi với JPA/Hibernate

| Khả năng | JPA/Hibernate điển hình | Spring Data R2DBC |
|---|---|---|
| Ánh xạ object với bảng và cột | Có | Có |
| Repository và CRUD | Có, qua Spring Data JPA hoặc EntityManager | Có, qua reactive repository và template |
| Persistence context / identity map | Có | Không có cơ chế tương đương |
| Dirty checking tự động | Có với entity được quản lý | Không; cần gọi `save` tường minh |
| Lazy loading bằng proxy | Có thể cấu hình cho quan hệ phù hợp | Không hỗ trợ theo cách đó |
| Quản lý quan hệ và cascade tổng quát | Có nhiều cơ chế association và cascade | Tập trung vào aggregate và object phụ thuộc |
| Truy vấn tùy chỉnh | JPQL/HQL và SQL native | SQL |
| I/O reactive không chặn | API JPA/Hibernate truyền thống là blocking | API truy cập dữ liệu reactive |
| Quản lý schema | Có thể có DDL generation tùy cấu hình | Thường dùng migration hoặc công cụ riêng |

Bảng trên mô tả các mô hình sử dụng phổ biến. Khả năng cụ thể của JPA/Hibernate phụ thuộc mapping và cấu hình; còn Spring Data R2DBC có các tiện ích mapping riêng nhưng không cung cấp persistence context kiểu JPA.

## 4. Hệ quả khi thiết kế ứng dụng

Những giới hạn trên ảnh hưởng trực tiếp đến cách tổ chức domain model và truy vấn:

1. **Thiết kế aggregate có ranh giới rõ ràng.** Đặt các object cần được lưu như một đơn vị nhất quán bên trong aggregate root. Tránh gom mọi quan hệ trong database thành một object graph lớn.
2. **Dùng ID để tham chiếu aggregate khác.** Khi cần thông tin của aggregate được tham chiếu, tải nó bằng một thao tác repository hoặc query rõ ràng.
3. **Lưu thay đổi một cách tường minh.** Không trông chờ dirty checking. Đưa `save` vào reactive chain và xử lý kết quả reactive của thao tác đó.
4. **Thiết kế truy vấn theo nhu cầu đọc.** Nếu màn hình cần dữ liệu từ nhiều bảng, cân nhắc SQL join và DTO/projection thay vì tải từng entity rồi giả định quan hệ sẽ tự được nạp.
5. **Quản lý transaction trong reactive flow.** Khi nhiều thao tác phải cùng thành công hoặc thất bại, cấu hình reactive transaction manager và giữ các thao tác trong cùng reactive chain hoặc phạm vi transaction thích hợp.
6. **Quản lý schema riêng.** Dùng migration để kiểm soát thay đổi bảng và index, đồng thời kiểm tra mapping có khớp schema đã triển khai hay không.

Ngoài ra, cần giữ đúng tính chất reactive của API. Không gọi `block()` tùy tiện trong luồng xử lý reactive vì việc chặn thread có thể làm mất lợi ích của mô hình non-blocking và gây nghẽn tài nguyên.

## 5. Khi nào nên chọn Spring Data R2DBC?

Spring Data R2DBC phù hợp khi ứng dụng cần truy cập cơ sở dữ liệu quan hệ theo mô hình reactive, domain model có thể tổ chức thành aggregate rõ ràng, và nhóm phát triển chấp nhận chủ động viết SQL cho những truy vấn kết hợp dữ liệu phức tạp.

Nếu nghiệp vụ phụ thuộc nhiều vào persistence context, dirty checking, lazy loading, cascade trên object graph lớn hoặc JPQL/HQL, cần cân nhắc một ORM như JPA/Hibernate. Tuy nhiên, API JPA/Hibernate truyền thống là blocking; việc đưa nó vào ứng dụng reactive cần một quyết định kiến trúc riêng, không thể chỉ thay repository JPA bằng repository R2DBC rồi mong giữ nguyên hành vi.

Điểm cần ghi nhớ là: **Spring Data R2DBC cung cấp object mapping và các abstraction persistence trên R2DBC, nhưng không phải ORM đầy đủ theo mô hình JPA/Hibernate.** Khi thiết kế với R2DBC, hãy chủ động xác định aggregate boundary, truy vấn SQL, thao tác lưu và transaction. Làm rõ những trách nhiệm này ngay từ đầu giúp mô hình dữ liệu phù hợp với khả năng thực tế của công nghệ.
