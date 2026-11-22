# Interface projection đóng và ánh xạ tên thuộc tính

## 1. Interface projection là gì?

Spring Data JPA cho phép repository trả về một interface thay vì toàn bộ Entity. Framework tạo projection instance dựa trên dữ liệu truy vấn và cung cấp các giá trị qua accessor của interface. Cách này hữu ích khi màn hình hoặc API chỉ cần một phần thông tin của Entity.

Ví dụ Entity `Customer` có nhiều trường như `id`, `firstName`, `lastName`, `email`, `phone`, `address`, `createdAt` và `status`, nhưng danh sách khách hàng chỉ cần tên và email. Có thể định nghĩa interface:

```java
public interface CustomerListView {
    Long getId();
    String getFirstName();
    String getLastName();
    String getEmail();
}
```

Repository trả về projection:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerListView> findByStatus(CustomerStatus status);
}
```

Spring Data nhận ra kiểu trả về là projection interface và tạo các object đáp ứng interface đó. Caller chỉ nhìn thấy các accessor được khai báo, không cần nhận Entity đầy đủ.

## 2. Closed projection là gì?

Projection được xem là **closed** khi tất cả accessor của interface tương ứng với property có thật trên aggregate root (Entity hoặc đối tượng gốc được truy vấn). Framework biết chính xác những property nào cần thiết và có thể tối ưu query để chỉ lấy các cột liên quan.

Ví dụ:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();
}
```

Hai accessor ánh xạ tới `Customer.firstName` và `Customer.lastName`. Nếu query trả về `CustomerNameView`, Spring Data có thể giới hạn dữ liệu được chọn thay vì tải toàn bộ các cột của Customer.

Closed projection giúp:

- Giảm lượng dữ liệu cần đọc và chuyển từ database.
- Giảm dữ liệu cần materialize trong ứng dụng khi chỉ cần một số property.
- Làm rõ hợp đồng dữ liệu của một use case đọc.
- Tránh để tầng API phụ thuộc vào toàn bộ cấu trúc Entity.

Việc tối ưu thực tế còn phụ thuộc loại query, provider, mapping và cách projection được sử dụng. Hãy kiểm tra SQL sinh ra thay vì giả định mọi projection luôn chỉ chọn đúng các cột getter.

## 3. Ánh xạ tên accessor với property Java

Spring Data dựa trên tên property của đối tượng gốc, không dựa trên tên cột vật lý trong database.

| Accessor trong interface | Property Java trong Entity | Cột vật lý có thể dùng |
| --- | --- | --- |
| `getFirstName()` | `firstName` | `first_name` |
| `getLastName()` | `lastName` | `last_name` |
| `getEmail()` | `email` | `email_address` |
| `getCreatedAt()` | `createdAt` | `created_at` |

Nếu Entity khai báo `private String firstName;` và mapping `@Column(name = "first_name")`, projection vẫn phải dùng `getFirstName()`. Không đặt `getFirst_name()` chỉ vì tên cột là snake_case.

JavaBean accessor `getFirstName()` biểu diễn property `firstName`. Với boolean, accessor thường là `isActive()` hoặc `getActive()` tùy kiểu và quy ước bean. Giữ tên property rõ ràng và nhất quán giúp tránh lỗi mapping khó phát hiện.

## 4. Dùng projection với derived query

Ví dụ Entity:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private CustomerStatus status;

    @Column(name = "created_at")
    private Instant createdAt;
}
```

Projection interface:

```java
public interface CustomerListView {
    Long getId();
    String getFirstName();
    String getLastName();
    String getEmail();
}
```

Repository:

```java
public interface CustomerRepository extends JpaRepository<Customer, Long> {
    List<CustomerListView> findByStatus(CustomerStatus status);
}
```

Query derivation vẫn dùng property Java `status`. Kiểu trả về interface projection làm rõ các trường cần đọc. Không cần khai báo `@Query` nếu điều kiện đơn giản.

## 5. Dùng @Query và alias cho interface projection

Khi viết JPQL tường minh, nên đặt alias cho từng expression trùng với property mà projection cần:

```java
public interface CustomerCardView {
    Long getId();
    String getFirstName();
    String getLastName();
}
```

```java
@Query("""
    select c.id as id,
           c.firstName as firstName,
           c.lastName as lastName
    from Customer c
    where c.status = :status
    """)
List<CustomerCardView> findCardsByStatus(
    @Param("status") CustomerStatus status
);
```

JPQL dùng Entity name và property Java. Alias `firstName` phải khớp property mà `getFirstName()` biểu diễn; alias `lastName` khớp `getLastName()`. Nếu alias sai hoặc thiếu, projection có thể nhận giá trị null hoặc lỗi mapping tùy provider và kiểu query.

Với interface projection từ query trả về scalar/tuple, alias là hợp đồng giữa query và accessor. Đặt alias rõ ràng và kiểm thử từng getter để tránh projection tạo thành công nhưng dữ liệu không được ánh xạ như mong muốn.

## 6. Interface projection với native SQL

Native query dùng tên bảng và cột vật lý. Alias nên chuyển tên cột database về đúng tên property mà interface yêu cầu:

```java
@Query(
    value = """
        select c.id as id,
               c.first_name as firstName,
               c.last_name as lastName
        from customer c
        where c.status = ?1
        """,
    nativeQuery = true
)
List<CustomerCardView> findCardsNative(CustomerStatus status);
```

Trong ví dụ, `first_name` và `last_name` là tên cột; `firstName` và `lastName` là alias cho projection. Positional parameter `?1` thường là lựa chọn native query dễ di động hơn giữa các provider. Kiểm tra kiểu enum `status` được driver/database mong đợi; nếu mapping lưu enum dưới dạng string hoặc ordinal, giá trị bind phải tương thích schema.

Quy tắc viết hoa/thường và cách driver trả về column label có thể khác nhau giữa database. Với native projection, hãy kiểm tra alias thực tế và test trên database mục tiêu. Không giả định alias camelCase luôn được giữ nguyên nếu dialect tự chuyển đổi identifier không quote.

## 7. Nested projection

Projection có thể khai báo interface con để biểu diễn property lồng nhau:

```java
public interface AddressView {
    String getCity();
    String getPostalCode();
}
```

```java
public interface CustomerDetailView {
    String getFirstName();
    String getLastName();
    AddressView getAddress();
}
```

Nếu `Customer.address` là association hoặc property lồng nhau, Spring Data có thể tạo nested projection cho `address`. Cách này tiện cho object graph đọc đơn giản.

Tuy nhiên, nested projection không đảm bảo query chỉ chọn đúng các leaf property bên trong. Với nested property phải đi qua join, Spring Data JPA có thể materialize toàn bộ property được join thay vì chỉ các trường con mà interface lồng khai báo. Nếu cần kiểm soát chính xác cột và join, dùng JPQL DTO constructor expression hoặc query trả về DTO.

Tránh tạo nested projection sâu và vòng lặp giữa các interface. Giữ cấu trúc nhỏ, phù hợp với response cần trả.

## 8. Default method trong closed projection

Projection interface có thể thêm default method để tính giá trị từ các accessor đã khai báo:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Default method không cần property mới từ Entity; nó kết hợp dữ liệu đã có qua accessor. Vì vậy projection vẫn có thể được xem là closed nếu các accessor lấy dữ liệu đều ánh xạ tới property của aggregate root.

Nếu logic tính toán cần service, truy vấn khác hoặc dữ liệu ngoài projection, đừng đặt dependency nghiệp vụ vào default method. Chuyển phần xử lý đó sang service hoặc mapper.

## 9. Phân biệt closed và open projection

Open projection dùng `@Value` với SpEL để tính giá trị từ target hoặc bean khác:

```java
public interface CustomerDisplayView {
    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Vì expression có thể truy cập nhiều property của target, Spring Data không thể xác định chắc chắn tập property cần lấy chỉ từ accessor. Do đó open projection thường không được tối ưu giới hạn cột như closed projection.

Nếu chỉ cần ghép hai property, default method trên closed projection thường rõ và dễ tối ưu hơn. Dùng `@Value` khi thực sự cần SpEL hoặc logic expression mà default method không đáp ứng.

| Đặc điểm | Closed projection | Open projection |
| --- | --- | --- |
| Accessor | Ánh xạ property rõ ràng | Có thể dùng SpEL `@Value` |
| Framework biết tập property cần đọc | Có thể xác định | Không thể xác định chắc chắn |
| Khả năng tối ưu chọn cột | Có thể tối ưu | Thường bị hạn chế |
| Phù hợp | View đọc đơn giản, trường xác định | Computed expression cần truy cập target/bean |

## 10. Nullable wrapper và property không có giá trị

Projection có thể dùng `Optional` cho property có khả năng null:

```java
public interface CustomerContactView {
    Long getId();
    String getEmail();
    Optional<String> getPhone();
}
```

Nếu `phone` là null, accessor trả về `Optional.empty()` thay vì null. Spring Data hỗ trợ một số wrapper nullable phổ biến; `java.util.Optional` là lựa chọn quen thuộc trong Java.

Wrapper không thay thế validation hay quy tắc nghiệp vụ. Nếu property bắt buộc, vẫn cần ràng buộc ở domain/validation/schema. Khi dùng projection, kiểm tra cách provider ánh xạ null và kiểu dữ liệu thực tế.

## 11. Projection interface khác DTO class thế nào?

| Tiêu chí | Interface projection | DTO class/record |
| --- | --- | --- |
| Cách định nghĩa | Interface với accessor | Constructor hoặc record component |
| Cách tạo kết quả | Spring Data tạo proxy/implementation | Provider tạo instance từ constructor query hoặc mapper |
| Alias | Quan trọng với query tuple/scalar | Constructor expression dựa trên thứ tự và kiểu tham số |
| Tính toán | Default method hoặc SpEL | Constructor, method hoặc mapper |
| Phù hợp | View đọc đơn giản, property rõ | Response có cấu trúc độc lập hoặc mapping phức tạp |

JPQL DTO projection thường dùng constructor expression:

```java
public record CustomerCard(Long id, String firstName, String email) {
}
```

```java
@Query("""
    select new com.example.customer.CustomerCard(
        c.id, c.firstName, c.email
    )
    from Customer c
    where c.status = :status
    """)
List<CustomerCard> findCards(
    @Param("status") CustomerStatus status
);
```

Constructor expression không dùng alias cho từng constructor argument; thứ tự, số lượng và kiểu expression phải khớp constructor. Chọn interface projection khi muốn contract accessor gọn; chọn DTO khi cần object kết quả độc lập với Entity và kiểm soát mapping rõ.

## 12. Projection và phân trang

Interface projection có thể kết hợp `Pageable`:

```java
@Query("""
    select c.id as id,
           c.firstName as firstName,
           c.lastName as lastName
    from Customer c
    where c.status = :status
    """)
Page<CustomerNameView> findPageByStatus(
    @Param("status") CustomerStatus status,
    Pageable pageable
);
```

Spring Data áp dụng pagination và có thể cần count query để tính tổng. Với JPQL query đơn giản, framework thường có thể suy ra count query; với distinct, group hoặc join phức tạp, khai báo `countQuery` rõ ràng và kiểm tra số phần tử tổng.

Projection không tự loại bỏ vấn đề phân trang khi join collection. Nếu query join một collection làm nhân hàng, cần kiểm tra distinct, count và thứ tự trang; cân nhắc query hai bước hoặc DTO phù hợp.

## 13. Lỗi thường gặp và cách chẩn đoán

**Accessor trả null dù Entity có dữ liệu.** Kiểm tra tên property trong interface, alias của `@Query` và column label của native SQL. `getFirstName()` ánh xạ property `firstName`, không phải `first_name`.

**Không tìm thấy alias hoặc projection không khớp.** Đặt alias JPQL/native trùng tên property projection; kiểm tra case folding của database/driver.

**Đổi tên Entity property làm projection lỗi.** Cập nhật accessor, query alias, derived method và test. Tên projection phụ thuộc property Java.

**Native projection hoạt động trên máy dev nhưng lỗi trên production.** Kiểm tra tên cột vật lý, alias trả về, kiểu dữ liệu và provider/database thật.

**Projection nested vẫn lấy nhiều dữ liệu.** Nested property qua association có thể khiến join materialize toàn bộ property liên quan; chuyển sang DTO query nếu cần chọn cột chính xác.

**Closed projection không được tối ưu như mong đợi.** Kiểm tra có `@Value`/SpEL hoặc nested association không, rồi xem SQL thực tế.

**Page tổng số sai.** Kiểm tra count query, join, distinct và group.

**Muốn truy cập method không có trong interface.** Projection chỉ cung cấp accessor đã khai báo; nếu cần nhiều thao tác Entity hoặc cập nhật dữ liệu, truy vấn Entity đầy đủ hoặc dùng service/DTO phù hợp.

## 14. Checklist thiết kế interface projection đóng

- Mỗi getter ánh xạ tới một property Java thực tế của Entity.
- Dùng camelCase property name, không dùng tên cột snake_case trong accessor.
- Với `@Query`, đặt alias trùng tên property projection.
- Với native SQL, alias cột vật lý về tên projection và kiểm thử trên database mục tiêu.
- Giữ projection closed: tránh `@Value`/SpEL nếu cần tối ưu chọn cột.
- Dùng default method cho phép tính đơn giản dựa trên accessor đã có.
- Cẩn thận nested projection vì join có thể materialize nhiều dữ liệu hơn dự kiến.
- Chọn DTO constructor projection khi cần kiểm soát kết quả và mapping rõ ràng.
- Kiểm thử null, pagination, count query và SQL sinh ra.

Closed interface projection cho phép repository trả về đúng view dữ liệu mà use case cần. Tên accessor phải bám theo property Java; với query tường minh, alias phải khớp hợp đồng projection. Giữ interface đóng và kiểm tra SQL thực tế giúp tận dụng khả năng tối ưu mà vẫn kiểm soát được dữ liệu trả về.