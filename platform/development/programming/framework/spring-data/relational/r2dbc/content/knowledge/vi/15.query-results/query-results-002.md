# Phép chiếu dựa trên interface và điều kiện hỗ trợ

Trong Spring Data R2DBC, repository thường trả về entity đại diện cho aggregate được lưu trong database. Tuy nhiên, nhiều use case chỉ cần một phần thuộc tính, chẳng hạn danh sách đơn hàng chỉ hiển thị mã đơn, trạng thái và thời điểm tạo. Interface-based projection cho phép khai báo một interface chỉ gồm những accessor cần thiết; Spring Data tạo proxy cho interface đó và cung cấp dữ liệu từ kết quả truy vấn.

Projection giúp định nghĩa một góc nhìn chỉ đọc của dữ liệu, giảm việc trả toàn bộ entity cho tầng gọi và làm rõ trường nào được sử dụng trong một use case. Khả năng hỗ trợ phụ thuộc vào kiểu truy vấn và mapping của Spring Data R2DBC. Đặc biệt, interface projection thường dựa trên domain type trước khi tạo proxy, nên tên thuộc tính phải tương ứng với entity và mapping `@Column` của entity vẫn có ý nghĩa.

## 1. Projection là gì?

Projection là một kiểu trả về chỉ biểu diễn một phần dữ liệu của aggregate. Thay vì trả `OrderEntity` với tất cả thuộc tính, ứng dụng có thể trả `OrderListItem` chỉ chứa những giá trị cần cho danh sách.

Ví dụ entity:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        @Column("order_code") String orderCode,
        @Column("customer_id") Long customerId,
        String status,
        @Column("created_at") Instant createdAt,
        @Column("internal_note") String internalNote
) {
}
```

Danh sách đơn hàng không cần `internalNote` hay `customerId`. Có thể định nghĩa projection:

```java
public interface OrderListItem {
    Long getId();
    String getOrderCode();
    String getStatus();
    Instant getCreatedAt();
}
```

Mỗi phương thức getter tương ứng với một thuộc tính của `OrderEntity`. Spring Data tạo proxy thực thi interface và chuyển lời gọi getter tới dữ liệu của projection target. Code gọi repository làm việc với `OrderListItem` mà không cần biết proxy được tạo như thế nào.

### 1.1. Projection khác entity và DTO như thế nào?

| Kiểu | Mục đích | Cách tạo |
|---|---|---|
| Entity | Biểu diễn aggregate dùng cho persistence và thao tác ghi | Spring Data mapping từ hàng database |
| Interface projection | Cung cấp góc nhìn chỉ đọc qua các accessor đã khai báo | Spring Data tạo proxy tại runtime |
| DTO/class projection | Trả dữ liệu vào một kiểu cụ thể, thường dùng cho response hoặc kết quả truy vấn | Spring Data tạo instance qua constructor hoặc mapping trực tiếp của query |

Projection interface không phải entity mới và không nên được xem như đối tượng để gọi `save`. Nếu cần thay đổi dữ liệu, đọc entity phù hợp hoặc gọi một Service command để thực hiện nghiệp vụ. DTO projection cũng là kết quả truy vấn, không tự trở thành aggregate có vòng đời persistence.

### 1.2. Projection type phải nằm ngoài hệ phân cấp kiểu của entity

Projection được thiết kế như một kiểu trả về riêng, nằm ngoài type hierarchy của entity. Nếu entity đã implement một interface và repository trả về chính interface đó, Spring Data có thể trả instance entity đã materialize đầy đủ thay vì tạo projection proxy.

Do đó, hãy tạo interface projection riêng, không dùng một interface chung mà entity đã implement chỉ để giới hạn các getter được nhìn thấy.

## 2. Khai báo interface-based projection

### 2.1. Các getter khớp thuộc tính entity

Ví dụ projection cho đơn hàng:

```java
package com.example.store.order.query;

import java.time.Instant;

public interface OrderListItem {
    Long getId();
    String getOrderCode();
    String getStatus();
    Instant getCreatedAt();
}
```

Các getter cần khớp với thuộc tính của aggregate root:

- `getId()` tương ứng thuộc tính `id`.
- `getOrderCode()` tương ứng thuộc tính `orderCode`.
- `getStatus()` tương ứng thuộc tính `status`.
- `getCreatedAt()` tương ứng thuộc tính `createdAt`.

Tên phương thức getter theo JavaBean được chuyển thành tên property. Nếu entity dùng `@Column("order_code")`, property Java vẫn là `orderCode`; interface nên khai báo `getOrderCode()`, không phải `getOrder_code()`.

Kiểu trả về phải tương thích với kiểu của thuộc tính sau khi Spring Data mapping và conversion. Nếu entity dùng enum `OrderStatus`, projection có thể khai báo `OrderStatus getStatus()`; nếu muốn trả chuỗi cho API, có thể chuyển sang response DTO ở tầng application/API.

### 2.2. Khai báo query method trong repository

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    Flux<OrderListItem> findByStatus(String status);

    Mono<OrderListItem> findFirstByCustomerIdOrderByCreatedAtDesc(
            Long customerId);
}
```

Repository method trả về `Flux<OrderListItem>` khi có thể có nhiều kết quả và `Mono<OrderListItem>` khi truy vấn trả tối đa một kết quả. Spring Data thực thi query method, ánh xạ kết quả và cung cấp proxy projection cho từng phần tử.

Tên method phải mô tả điều kiện hợp lệ theo thuộc tính entity. `findByStatus` tìm theo property `status`; `findFirstByCustomerIdOrderByCreatedAtDesc` lấy một kết quả đầu tiên theo thời gian tạo giảm dần. Nếu yêu cầu nghiệp vụ cần thứ tự ổn định khi nhiều bản ghi cùng thời điểm, nên bổ sung khóa duy nhất làm tiêu chí phụ bằng một query method hoặc câu truy vấn phù hợp.

### 2.3. Không đổi kiểu trả về của phương thức CRUD kế thừa

Một điều kiện hỗ trợ quan trọng: không nên khai báo lại phương thức CRUD đã có trong interface cơ sở chỉ để đổi kiểu trả về thành projection.

Ví dụ không nên dùng:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    // Không dùng cách này để biến findAll kế thừa thành projection.
    Flux<OrderListItem> findAll();
}
```

Các phương thức kế thừa từ `ReactiveCrudRepository` hoặc repository base interface được thực thi theo implementation cơ sở; việc khai báo lại với kiểu trả về projection không tự biến chúng thành query method mới. Hãy đặt tên query method riêng, ví dụ `findByStatus(...)`, `findAllProjectedBy...(...)` nếu cú pháp query derivation phù hợp, hoặc dùng `@Query` cho truy vấn cụ thể.

## 3. Closed projection và khả năng tối ưu

### 3.1. Closed projection

Một interface projection là *closed projection* khi tất cả accessor của nó ánh xạ tới thuộc tính có thật của aggregate root. Ví dụ:

```java
public interface CustomerNameView {
    String getFirstName();
    String getLastName();
}
```

Nếu entity `CustomerEntity` có đúng hai thuộc tính `firstName` và `lastName`, Spring Data biết trước những giá trị cần thiết để cung cấp projection. Điều này cho phép hệ thống tối ưu query execution và có thể chỉ materialize những thuộc tính cần cho projection.

Trong Spring Data R2DBC, interface projection thường dựa trên kết quả được map vào domain type trước để áp dụng mapping như `@Column`; proxy sau đó phơi bày dữ liệu từ entity có thể được materialize một phần. Vì vậy, không nên giả định mọi trường hợp đều tạo ra một câu SQL chỉ có đúng các cột getter. Hãy xem SQL/log hoặc kiểm thử trên phiên bản Spring Data đang dùng nếu việc giảm cột là yêu cầu hiệu năng quan trọng.

### 3.2. Lợi ích của closed projection

- Nêu rõ dữ liệu cần dùng ở nơi khai báo query method.
- Có thể giảm số thuộc tính được tải hoặc materialize khi module và kiểu query hỗ trợ tối ưu.
- Giảm nguy cơ tầng đọc vô tình phụ thuộc vào trường nội bộ không cần thiết.
- Có thể làm code service/controller dễ đọc hơn vì kiểu trả về thể hiện đúng mục đích của truy vấn.

Closed projection không thay thế thiết kế index, giới hạn kết quả hoặc tối ưu SQL. Nếu query trả về hàng triệu bản ghi, chỉ chọn ít cột vẫn không giải quyết vấn đề nếu thiếu điều kiện lọc và phân trang.

## 4. Open projection và giá trị tính toán

### 4.1. Open projection với @Value

Interface projection có thể khai báo accessor tính toán bằng `@Value` và SpEL:

```java
public interface CustomerNameView {

    String getFirstName();
    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
```

Projection dùng `@Value` được gọi là *open projection*. Biểu thức có thể truy cập bất kỳ thuộc tính nào của target thông qua biến `target`, vì vậy Spring Data không thể biết trước chính xác những trường cần thiết để tối ưu query execution. Với truy vấn lớn, open projection có thể làm mất lợi ích giảm thuộc tính của closed projection.

Không nên đặt biểu thức SpEL quá phức tạp. Nếu cần logic nhiều bước, hãy chuyển nó sang một Spring bean hoặc application service. Projection nên chủ yếu mô tả cách đọc dữ liệu.

### 4.2. Default method cho phép tính đơn giản

Nếu giá trị tính toán chỉ phụ thuộc vào các accessor đã khai báo, có thể dùng default method:

```java
public interface CustomerNameView {

    String getFirstName();
    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Default method không cần truy cập thuộc tính ẩn của target; nó chỉ sử dụng các getter đã khai báo. Cách này giữ interface đơn giản và tránh viết biểu thức SpEL dưới dạng chuỗi.

### 4.3. Gọi Spring bean từ SpEL

Nếu phép tính cần logic có thể tái sử dụng, có thể gọi bean từ biểu thức:

```java
@Component
public class CustomerLabelFormatter {
    public String format(CustomerEntity customer) {
        return customer.getFirstName() + " " + customer.getLastName();
    }
}

public interface CustomerNameView {

    @Value("#{@customerLabelFormatter.format(target)}")
    String getDisplayLabel();
}
```

Đây vẫn là open projection vì biểu thức có thể sử dụng toàn bộ target. Bean nên chứa logic định dạng đơn giản, không nên dùng projection để thực hiện truy vấn database bổ sung hoặc điều phối nghiệp vụ.

## 5. Giá trị NULL và nullable wrapper

Nếu một thuộc tính có thể `NULL`, getter projection có thể sử dụng `Optional` để biểu diễn sự vắng mặt:

```java
public interface CustomerContactView {
    Long getId();
    String getName();
    Optional<String> getPhoneNumber();
}
```

Khi giá trị nền khác null, getter trả `Optional` có giá trị; khi giá trị nền là null, getter trả `Optional.empty()`. Spring Data hỗ trợ `java.util.Optional` cùng một số nullable wrapper khác tùy cấu hình và module.

Nếu dùng kiểu trả về trực tiếp như `String`, cần chấp nhận rằng getter có thể trả `null` khi cột database nullable. Không dùng primitive như `long` hoặc `boolean` cho cột có thể null nếu không có quy tắc mặc định rõ ràng, vì mapping có thể không biểu diễn được giá trị null.

Nullable wrapper ở thuộc tính projection khác với reactive wrapper của toàn bộ query:

- `Mono<CustomerContactView>` biểu diễn không hoặc một kết quả truy vấn.
- `Flux<CustomerContactView>` biểu diễn không hoặc nhiều kết quả.
- `Optional<String> getPhoneNumber()` biểu diễn một thuộc tính nullable bên trong mỗi projection.

## 6. Projection lồng nhau và giới hạn của mô hình quan hệ

Spring Data Commons cho phép khai báo projection lồng nhau khi một property của aggregate chứa một object khác. Ví dụ:

```java
public interface CustomerSummary {
    String getFirstName();
    String getLastName();
    AddressSummary getAddress();

    interface AddressSummary {
        String getCity();
        String getPostalCode();
    }
}
```

Projection lồng nhau chỉ áp dụng trên property thực sự có trong object graph được mapping. Trong Spring Data Relational/R2DBC, nó không tạo cơ chế lazy loading hoặc tự join một aggregate độc lập chỉ vì interface khai báo `getCustomer()` hay `getAddress()`.

Nếu `OrderEntity` chỉ lưu `customerId`, việc khai báo `CustomerSummary getCustomer()` không khiến Spring Data tự truy vấn bảng `customers`. Muốn lấy dữ liệu từ aggregate khác, hãy:

- Thực hiện truy vấn riêng và kết hợp publisher trong Service/query service.
- Viết SQL join bằng `@Query` hoặc `DatabaseClient` rồi map sang DTO phù hợp.
- Dùng một projection/query result có cấu trúc phù hợp với dữ liệu thực tế được truy vấn.

Không nhầm projection lồng nhau với quan hệ ORM. R2DBC theo mô hình relational aggregate và không cung cấp lazy relationship loading kiểu JPA.

## 7. Interface projection với @Query

Có thể khai báo truy vấn SQL cố định bằng `@Query` và trả về interface projection:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    @Query("""
        SELECT id, order_code, status, created_at
        FROM orders
        WHERE status = :status
        ORDER BY created_at DESC, id DESC
        """)
    Flux<OrderListItem> findListItemsByStatus(String status);
}
```

Với interface projection trong R2DBC, kết quả thường được mapping qua domain type trước khi proxy projection được tạo. Vì vậy, các cột trả về cần tương thích với mapping của entity: tên cột phải khớp schema hoặc alias phù hợp, và thuộc tính projection phải tồn tại trong domain type. Nếu entity có `@Column("order_code") String orderCode`, kết quả cần cung cấp cột `order_code` để Spring Data có thể map vào property `orderCode`.

Không nên dùng interface projection để yêu cầu các giá trị tổng hợp không tồn tại trong entity, chẳng hạn `COUNT(order_lines.id) AS lineCount`, rồi kỳ vọng nó được ánh xạ như một property entity thông thường. Với kết quả SQL có trường tính toán, join hoặc alias hoàn toàn riêng, DTO projection trên `@Query` thường phù hợp hơn.

### 7.1. Khi DTO projection phù hợp hơn với SQL tùy chỉnh

R2DBC xử lý DTO projection tùy theo loại query:

- Derived query tạo DTO từ các thuộc tính có sẵn trong domain type.
- Với query dạng chuỗi được khai báo bằng `@Query`, DTO có thể được map trực tiếp từ kết quả query. Các alias và trường được select có thể được thiết kế theo DTO; mapping field của domain type không nhất thiết được áp dụng theo cách của interface projection.

Ví dụ truy vấn join:

```java
public record OrderSummary(
        Long id,
        String orderCode,
        String customerName,
        Long lineCount
) {
}
```

```java
@Query("""
    SELECT o.id AS id,
           o.order_code AS orderCode,
           c.display_name AS customerName,
           COUNT(ol.id) AS lineCount
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    LEFT JOIN order_lines ol ON ol.order_id = o.id
    WHERE o.status = :status
    GROUP BY o.id, o.order_code, c.display_name
    """)
Flux<OrderSummary> findSummariesByStatus(String status);
```

DTO cho phép biểu diễn `customerName` và `lineCount` dù chúng không phải thuộc tính của `OrderEntity`. Hãy bảo đảm alias và kiểu dữ liệu kết quả phù hợp với constructor DTO, đồng thời kiểm thử trên database/driver mục tiêu.

## 8. Dynamic projection

Spring Data repository có thể cho phép caller chọn projection type tại thời điểm gọi bằng tham số `Class<T>`:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<CustomerEntity, Long> {

    <T> Flux<T> findByLastName(String lastName, Class<T> projectionType);
}
```

Có thể gọi cùng query method với entity hoặc interface projection:

```java
Flux<CustomerEntity> entities =
        repository.findByLastName("Nguyen", CustomerEntity.class);

Flux<CustomerNameView> names =
        repository.findByLastName("Nguyen", CustomerNameView.class);
```

Spring Data nhận diện `Class<T>` là tham số chọn projection khi kiểu generic của nó tương ứng với kiểu trả về tổng quát của method. Trong trường hợp đó, tham số `Class<T>` được dùng làm projection selector, không còn là query parameter thông thường để bind vào SQL hoặc dùng trong SpEL. Nếu thực sự cần truyền một `Class` như dữ liệu truy vấn, hãy dùng kiểu generic khác, ví dụ `Class<?>`, theo quy tắc của Spring Data Commons.

Dynamic projection hữu ích khi cùng một bộ lọc có nhiều góc nhìn trả về. Tuy nhiên, không nên để API bên ngoài truyền tên class tùy ý. Hãy chọn projection type trong code theo use case hoặc whitelist kiểu được phép để giữ hợp đồng rõ ràng.

## 9. Điều kiện hỗ trợ và các giới hạn cần nhớ

### 9.1. Thuộc tính projection phải khớp domain type

Interface projection thông thường chỉ truy cập property đã được định nghĩa trên aggregate root. Getter không khớp tên property, sai kiểu dữ liệu hoặc trỏ tới property không được mapping có thể khiến kết quả không đúng hoặc phát sinh lỗi khi materialize.

### 9.2. Mapping của @Column vẫn có hiệu lực

Interface getter dùng tên property Java, còn hàng database dùng tên cột. Spring Data R2DBC xem xét mapping của domain type trước khi tạo projection proxy, do đó phải giữ mapping nhất quán giữa entity, SQL alias và projection interface.

### 9.3. Base repository method không trở thành projection method chỉ bằng cách đổi return type

Không override `findAll`, `findById` hoặc phương thức CRUD kế thừa với kiểu trả về projection và mong đợi Spring Data tạo query projection. Tạo query method riêng hoặc dùng `@Query` khi cần.

### 9.4. Open projection làm hạn chế tối ưu

`@Value` cho phép truy cập target tùy ý, nên Spring Data không thể biết chính xác tập thuộc tính cần thiết. Dùng closed projection hoặc default method khi có thể.

### 9.5. Projection không tự join aggregate khác

Projection lồng nhau chỉ nhìn vào property được mapping. R2DBC không tự tải quan hệ độc lập hoặc tạo lazy query như ORM JPA.

### 9.6. Interface projection không phải DTO tùy ý

Nếu truy vấn trả thêm cột tổng hợp hoặc alias không thuộc entity, hãy cân nhắc DTO projection trực tiếp qua `@Query`, custom query mapping hoặc `DatabaseClient` thay vì ép vào interface dựa trên entity.

### 9.7. Khả năng tối ưu phụ thuộc loại query và phiên bản

Closed projection có thể giúp giới hạn dữ liệu cần materialize, nhưng cách sinh SQL và mapping phụ thuộc Spring Data R2DBC version, loại query (derived hay string-based) và dialect. Nếu cần tối ưu số cột, hãy kiểm tra SQL được thực thi thay vì suy luận chỉ từ interface.

## 10. Projection và phân tách API model

Projection thường phù hợp với tầng đọc dữ liệu bên trong ứng dụng. Tuy nhiên, không bắt buộc phải trả trực tiếp projection interface ra HTTP. API response là hợp đồng với client và có thể cần tên trường, cấu trúc hoặc định dạng khác với entity.

Có thể chuyển projection sang response DTO:

```java
public record OrderResponse(
        Long id,
        String code,
        String state,
        Instant createdAt
) {
}
```

```java
public Mono<OrderResponse> getOrder(Long id) {
    return repository.findFirstById(id)
            .map(view -> new OrderResponse(
                    view.getId(),
                    view.getOrderCode(),
                    view.getStatus(),
                    view.getCreatedAt()));
}
```

Ví dụ minh họa ý tưởng chuyển đổi; trong repository thực tế, dùng một query method không xung đột với method CRUD kế thừa. Việc mapping sang DTO cho phép API thay đổi độc lập với cách truy vấn persistence.

Không dùng projection làm đối tượng cập nhật. Nếu client gửi request thay đổi trạng thái đơn hàng, hãy gọi Service command để tải entity hoặc thực hiện một lệnh update được thiết kế rõ ràng, áp dụng kiểm tra quyền và transaction cần thiết.

## 11. Kiểm thử interface projection

Kiểm thử nên xác nhận cả cấu trúc interface lẫn mapping kết quả thực tế.

### 11.1. Kiểm thử repository với StepVerifier

```java
StepVerifier.create(orderRepository.findByStatus("PAID"))
        .assertNext(view -> {
            assertThat(view.getId()).isNotNull();
            assertThat(view.getOrderCode()).startsWith("ORD-");
            assertThat(view.getStatus()).isEqualTo("PAID");
        })
        .verifyComplete();
```

Test cần chuẩn bị dữ liệu có thể dự đoán và xác nhận projection getter trả đúng giá trị. Với `Flux`, kiểm tra số lượng và thứ tự nếu thứ tự là một phần của query contract.

### 11.2. Kiểm tra @Column và alias

Nếu entity ánh xạ `orderCode` sang `order_code`, integration test phải xác nhận getter `getOrderCode()` nhận đúng giá trị. Đối với `@Query`, kiểm tra alias và danh sách cột trả về để domain mapping có thể tạo target cho projection.

### 11.3. Kiểm tra null và open projection

Thêm trường hợp cột nullable để xác nhận `Optional` trả empty hoặc getter nullable trả null theo thiết kế. Nếu dùng `@Value`, kiểm tra SpEL và các dependency bean được gọi đúng; cân nhắc quan sát SQL để hiểu chi phí truy vấn.

### 11.4. Kiểm tra đúng loại query

Derived query, `@Query` và dynamic projection có thể có cách mapping khác nhau. Tạo integration test riêng cho từng kiểu được sử dụng trong ứng dụng, đặc biệt khi `@Query` trả DTO có trường tổng hợp hoặc interface projection phụ thuộc entity mapping.

Nên chạy integration test với cùng loại database và driver dự kiến triển khai. Mock repository chỉ kiểm tra logic gọi service; nó không xác nhận Spring Data có tạo proxy và ánh xạ cột đúng hay không.

## 12. Lỗi thường gặp

### Getter không khớp tên property

Nếu entity có `orderCode`, interface nên dùng `getOrderCode()`. `getOrder_code()` tạo một property khác và không tự khớp với `@Column("order_code")`.

### Projection interface kế thừa từ entity interface

Nếu interface projection đã nằm trong type hierarchy của entity, Spring Data có thể trả entity đầy đủ. Tạo một interface projection độc lập ngoài hierarchy của entity.

### Đổi kiểu trả về findAll để lấy projection

Phương thức CRUD kế thừa vẫn được xử lý như base method. Hãy tạo query method riêng hoặc khai báo `@Query`.

### Dùng @Value cho phép tính đơn giản

SpEL khiến projection thành open projection và hạn chế tối ưu. Dùng default method nếu phép tính chỉ cần các getter đã khai báo.

### Mong đợi projection tự tải quan hệ

Interface lồng nhau không tạo join hoặc lazy loading cho aggregate khác. Viết truy vấn join/projection phù hợp nếu cần dữ liệu nhiều bảng.

### Dùng interface projection cho cột tổng hợp ngoài entity

Interface projection thông thường dựa trên domain mapping. Dùng DTO projection cho kết quả SQL có alias, aggregate hoặc cột không thuộc entity.

### Cho rằng closed projection luôn chỉ select đúng các cột getter

R2DBC có thể map qua domain type trước và dùng entity materialize một phần. Xác nhận SQL thực tế theo phiên bản và loại query nếu cần tối ưu projection ở mức cột.

## 13. Quy trình áp dụng

1. Xác định use case chỉ cần một phần thuộc tính của aggregate.
2. Kiểm tra các thuộc tính đó có tồn tại trong domain type và mapping entity hay không.
3. Tạo interface projection riêng với getter đúng tên property Java và kiểu dữ liệu tương thích.
4. Khai báo query method mới trả về `Mono<Projection>` hoặc `Flux<Projection>`; không override CRUD method chỉ để đổi kiểu trả về.
5. Ưu tiên closed projection; dùng default method cho phép tính dựa trên getter có sẵn.
6. Dùng open projection với `@Value` khi thực sự cần SpEL và chấp nhận giới hạn tối ưu.
7. Với join, aggregate hoặc cột không thuộc entity, cân nhắc DTO projection hoặc SQL mapping riêng.
8. Kiểm tra cách `@Column` và alias ảnh hưởng tới result mapping.
9. Viết integration test cho derived query, `@Query`, nullable field và dynamic projection nếu có.
10. Quan sát SQL và đo hiệu năng trước khi kết luận projection đã giảm lượng dữ liệu đọc.

## 14. Checklist ghi nhớ

- [ ] Interface projection là kiểu trả về riêng, nằm ngoài type hierarchy của entity.
- [ ] Getter khớp tên property Java của aggregate root.
- [ ] Kiểu getter tương thích với kiểu thuộc tính sau mapping/conversion.
- [ ] Query method mới trả về `Mono` hoặc `Flux` projection phù hợp với cardinality.
- [ ] Không override phương thức CRUD kế thừa chỉ để thay return type thành projection.
- [ ] Closed projection chỉ gồm getter ánh xạ trực tiếp tới property của entity.
- [ ] Open projection dùng `@Value`/SpEL và có thể hạn chế tối ưu truy vấn.
- [ ] Default method phù hợp với phép tính chỉ dựa trên getter đã khai báo.
- [ ] `Optional` được dùng khi cần biểu diễn thuộc tính nullable.
- [ ] Projection lồng nhau không tự join hoặc lazy-load aggregate độc lập.
- [ ] Dùng DTO cho query có cột tổng hợp hoặc kết quả không thuộc domain type.
- [ ] Kiểm thử mapping thực tế trên database/driver và quan sát SQL khi cần tối ưu.

Interface-based projection cung cấp một cách khai báo gọn cho các góc nhìn chỉ đọc của aggregate trong Spring Data R2DBC. Khi getter khớp property của entity, query method được khai báo đúng và hiểu rõ khác biệt giữa closed/open projection cùng result mapping của R2DBC, projection có thể làm tầng truy vấn rõ ràng hơn mà vẫn giữ được ranh giới giữa dữ liệu lưu trữ và mô hình API.

## Tài liệu tham khảo

- [Spring Data Relational – Projections](https://docs.spring.io/spring-data/relational/reference/repositories/projections.html)
- [Spring Data Relational – R2DBC Repositories, Result Mapping](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
