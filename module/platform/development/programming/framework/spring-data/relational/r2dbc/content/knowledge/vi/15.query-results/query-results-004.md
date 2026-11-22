# Phép chiếu động và lựa chọn kiểu kết quả

Trong Spring Data R2DBC, một truy vấn có thể trả về toàn bộ entity hoặc chỉ một phần dữ liệu cần cho màn hình, báo cáo hay API. Cách chỉ lấy một tập thuộc tính của entity được gọi là **projection (phép chiếu)**. Khi kiểu kết quả được xác định ngay trong khai báo repository, đó là projection tĩnh; khi caller truyền kiểu kết quả tại thời điểm gọi, đó là **dynamic projection**.

Projection giúp tách mô hình lưu trữ khỏi mô hình đọc dữ liệu. Một service có thể cần toàn bộ Customer để thực hiện nghiệp vụ, trong khi một màn hình danh sách chỉ cần tên và email. Trả về một kiểu kết quả phù hợp giúp API thể hiện đúng dữ liệu cần dùng và có thể giảm lượng dữ liệu phải đọc, chuyển đổi và truyền qua các tầng.

## 1. Projection là gì?

Giả sử entity Customer có nhiều thuộc tính:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    @Column("full_name") String fullName,
    String email,
    String phone,
    Boolean active,
    @Version Long version
) {}
~~~

Một trang danh sách có thể chỉ cần tên và email. Nếu luôn truy vấn Customer đầy đủ, ứng dụng nhận cả phone, active và version dù màn hình không sử dụng chúng.

Projection mô tả phần dữ liệu cần trả về:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

Hoặc dùng một DTO:

~~~java
public record CustomerSummary(
    String fullName,
    String email
) {}
~~~

Khi truy vấn trả về projection, Spring Data ánh xạ kết quả vào kiểu đó theo cơ chế phù hợp với interface hoặc constructor. Tên property projection phải tương ứng với property của entity hoặc alias của cột kết quả khi truy vấn SQL tùy chỉnh.

Projection thường hữu ích cho các trường hợp đọc dữ liệu. Nếu cần cập nhật aggregate, kiểm tra version hoặc gọi phương thức domain trên entity đầy đủ, hãy truy vấn entity thay vì dùng projection chỉ chứa một phần thuộc tính.

## 2. Các loại projection

Spring Data có một số cách biểu diễn projection. Trong ứng dụng Spring Data R2DBC, thường gặp nhất là interface-based projection, DTO/class-based projection và dynamic projection.

### 2.1. Interface-based projection

Interface projection khai báo các accessor cho property cần lấy:

~~~java
public interface CustomerNameView {
    String getFullName();
    String getEmail();
}
~~~

Repository có thể trả về trực tiếp interface:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerNameView> findByActiveTrue();
}
~~~

Caller chỉ nhìn thấy các accessor đã khai báo:

~~~java
Flux<CustomerNameView> customers =
    repository.findByActiveTrue();

return customers.map(view ->
    view.getFullName() + " <" + view.getEmail() + ">"
);
~~~

Interface projection phù hợp khi:

- Chỉ cần đọc một vài thuộc tính.
- Muốn giữ kiểu kết quả gọn và rõ nghĩa.
- Không cần một object DTO có logic nghiệp vụ riêng.
- Tên accessor có thể ánh xạ trực tiếp tới property của entity.

Một interface projection là kiểu đọc dữ liệu. Không nên xem nó như entity đầy đủ để gọi save hoặc thực hiện thay đổi aggregate.

### 2.2. Closed projection

Closed projection là interface chỉ khai báo accessor tương ứng với property của target entity. Spring Data biết chính xác những property nào được yêu cầu.

Ví dụ:

~~~java
public interface CustomerContact {
    String getFullName();
    String getEmail();
}
~~~

Vì các accessor ánh xạ trực tiếp vào property, framework có thể biết tập thuộc tính cần thiết và tối ưu việc lấy dữ liệu nếu store và loại truy vấn hỗ trợ. Việc cột thực tế được giới hạn trong SQL hay không phụ thuộc cách repository tạo truy vấn, module, driver và phiên bản. Khi hiệu năng quan trọng, hãy xem SQL được phát ra thay vì giả định mọi projection đều tự động tạo SELECT chỉ gồm hai cột.

### 2.3. Open projection

Open projection là interface có thể dùng biểu thức SpEL để tính giá trị từ target object, ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;

public interface CustomerLabel {

    @Value("#{target.fullName + ' <' + target.email + '>'}")
    String getLabel();
}
~~~

Open projection linh hoạt vì giá trị trả về có thể được tính từ nhiều property. Tuy nhiên, framework khó xác định chính xác tập cột cần đọc chỉ từ biểu thức. Ngoài ra, khả năng hỗ trợ và cách tối ưu projection có thể khác nhau giữa các Spring Data module và phiên bản.

Với Spring Data R2DBC, nên ưu tiên closed projection hoặc DTO có constructor rõ ràng cho truy vấn cần dự đoán được mapping và SQL. Chỉ sử dụng SpEL projection khi đã xác nhận module/phiên bản đang dùng hỗ trợ đúng trường hợp đó.

### 2.4. DTO/class-based projection

DTO projection dùng một class hoặc record làm kiểu kết quả. Spring Data tạo instance bằng constructor có các tham số tương ứng với property cần lấy.

Ví dụ record:

~~~java
public record CustomerSummary(
    String fullName,
    String email
) {}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerSummary> findByActiveTrue();
}
~~~

DTO phù hợp khi:

- Muốn kiểu kết quả cụ thể, độc lập với entity.
- Muốn dùng record để có dữ liệu bất biến và ít boilerplate.
- Cần trả về một read model cho service hoặc API.
- Không cần proxy interface projection.

Với class có nhiều constructor, cần chỉ rõ constructor persistence phù hợp bằng @PersistenceCreator. Tên tham số constructor phải khớp property mà Spring Data cần ánh xạ; hãy bảo đảm thông tin tên tham số được giữ trong quá trình biên dịch khi cơ chế mapping dựa vào chúng.

## 3. Dynamic projection là gì?

Với projection tĩnh, kiểu kết quả nằm cố định trong khai báo method:

~~~java
Flux<CustomerNameView> findByActiveTrue();
~~~

Nếu một use case muốn lấy CustomerNameView, còn use case khác muốn lấy CustomerSummary hoặc toàn bộ Customer, có thể tạo nhiều method riêng. Dynamic projection cho phép chọn kiểu kết quả bằng tham số Class<T> tại thời điểm gọi.

Ví dụ:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    <T> Flux<T> findByActiveTrue(Class<T> resultType);
}
~~~

Cùng một method có thể được gọi với nhiều kiểu kết quả:

~~~java
Flux<Customer> entities =
    repository.findByActiveTrue(Customer.class);

Flux<CustomerNameView> names =
    repository.findByActiveTrue(CustomerNameView.class);

Flux<CustomerSummary> summaries =
    repository.findByActiveTrue(CustomerSummary.class);
~~~

Khi caller truyền Customer.class, repository trả về entity đầy đủ. Khi truyền CustomerNameView.class, repository trả về interface projection. Khi truyền CustomerSummary.class, repository trả về DTO projection.

Dynamic projection hữu ích khi điều kiện truy vấn giống nhau nhưng mỗi caller cần một hình dạng dữ liệu khác nhau.

### 3.1. Cơ chế nhận diện tham số Class<T>

Spring Data nhận diện tham số dynamic projection khi method có tham số Class<T> tương ứng với generic type T của kiểu trả về.

~~~java
<T> Flux<T> findByActiveTrue(Class<T> resultType);
~~~

Trong trường hợp này, resultType được dùng để xác định projection. Nó không phải một giá trị điều kiện thông thường của truy vấn.

Nếu cần truyền một đối tượng Class như một tham số dữ liệu thật sự cho query, hãy dùng kiểu không khớp với generic projection parameter, ví dụ Class<?> theo quy tắc Spring Data, và khai báo binding tương ứng. Cần kiểm tra cách method parser nhận diện tham số trong phiên bản đang sử dụng.

### 3.2. Dynamic projection không làm thay đổi điều kiện lọc

Ví dụ:

~~~java
<T> Flux<T> findByFullNameContainingIgnoreCase(
    String fragment,
    Class<T> resultType
);
~~~

fragment vẫn là giá trị điều kiện tìm kiếm. resultType quyết định kiểu dữ liệu trả về.

Các lời gọi:

~~~java
Flux<Customer> allData =
    repository.findByFullNameContainingIgnoreCase(
        "An",
        Customer.class
    );

Flux<CustomerNameView> namesOnly =
    repository.findByFullNameContainingIgnoreCase(
        "An",
        CustomerNameView.class
    );
~~~

cùng tìm những khách hàng có tên chứa An, nhưng trả về hai hình dạng dữ liệu khác nhau.

### 3.3. Dynamic projection có giới hạn theo truy vấn

Dynamic projection phù hợp nhất với derived query mà Spring Data có thể phân tích từ method signature. Với @Query chứa SQL viết sẵn, không nên giả định framework sẽ tự viết lại mọi SELECT list tùy theo Class<T>.

Nếu dùng truy vấn SQL tùy chỉnh, hãy bảo đảm SQL chọn các cột cần thiết và alias khớp với kiểu kết quả. Khi mỗi projection cần một tập cột hoặc cấu trúc join khác nhau, nên dùng method riêng, custom repository fragment, R2dbcEntityTemplate hoặc DatabaseClient.

## 4. Chọn kiểu kết quả trong Repository

Kiểu trả về của repository thể hiện cả hai vấn đề:

1. **Hình dạng dữ liệu**: entity, interface projection, DTO, scalar hoặc kiểu kết quả khác.
2. **Số lượng kết quả và cách phát dữ liệu**: không có/một kết quả hay nhiều kết quả trong luồng reactive.

Hai vấn đề này độc lập. Ví dụ, Flux<CustomerSummary> là một luồng có thể chứa nhiều DTO; Mono<CustomerNameView> là một kết quả interface projection có thể không tồn tại.

### 4.1. Trả về entity đầy đủ

~~~java
Mono<Customer> findById(Long id);

Flux<Customer> findByActiveTrue();
~~~

Dùng entity khi caller cần toàn bộ trạng thái persistent, ID/version và mô hình aggregate.

### 4.2. Trả về interface projection

~~~java
Flux<CustomerNameView> findByActiveTrue();
~~~

Dùng interface khi caller chỉ cần một tập accessor nhỏ và không cần DTO độc lập.

### 4.3. Trả về DTO hoặc record

~~~java
Flux<CustomerSummary> findByActiveTrue();
~~~

Dùng DTO khi cần kiểu dữ liệu đọc cụ thể, dễ truyền qua các tầng hoặc trả về API.

### 4.4. Trả về một kết quả hoặc nhiều kết quả

| Kiểu reactive | Ý nghĩa thường dùng |
|---|---|
| Mono<T> | Không có hoặc tối đa một kết quả |
| Flux<T> | Không có, một hoặc nhiều kết quả |
| Mono<Long> | Một giá trị đếm |
| Mono<Boolean> | Một giá trị kiểm tra tồn tại/điều kiện |
| Mono<Void> | Chỉ quan tâm hoàn tất, không cần dữ liệu kết quả |

Nếu method trả về Mono<T> nhưng truy vấn thực tế trả nhiều hàng, thao tác có thể thất bại do số lượng kết quả không phù hợp. Dùng Flux<T> khi điều kiện có thể khớp nhiều hàng.

Không gọi block() chỉ để chuyển Mono hoặc Flux thành kiểu đồng bộ bên trong service reactive. Hãy kết hợp publisher với map, flatMap, filter hoặc trả publisher lên controller.

## 5. Ví dụ hoàn chỉnh với interface và DTO projection

Giả sử entity Customer có nhiều property nhưng trang danh sách chỉ cần tên và email.

Interface projection:

~~~java
public interface CustomerContactView {
    String getFullName();
    String getEmail();
}
~~~

DTO projection:

~~~java
public record CustomerContactDto(
    String fullName,
    String email
) {}
~~~

Repository có thể khai báo cả hai kiểu trả về:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<CustomerContactView> findByActiveTrue();

    Flux<CustomerContactDto> findDtoByActiveTrue();
}
~~~

Cách đặt tên method cần tránh trùng chữ ký Java. Ví dụ trên dùng findByActiveTrue cho interface và findDtoByActiveTrue cho DTO; phần predicate mà Spring Data phân tích phải hợp lệ với convention của phiên bản. Nếu tên method dẫn đến parser hiểu sai, có thể dùng tên method rõ ràng hơn với @Query hoặc custom fragment.

Trong service:

~~~java
public Flux<CustomerContactDto> listContacts() {
    return repository.findDtoByActiveTrue();
}
~~~

Service chỉ phát ra kiểu dữ liệu mà use case cần. Các tầng phía trên không cần biết Customer có những trường khác như phone hoặc version.

## 6. Ví dụ dynamic projection trong Repository

Khai báo một method generic:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    <T> Flux<T> findByActiveTrue(Class<T> projectionType);

    <T> Flux<T> findByFullNameContainingIgnoreCase(
        String fragment,
        Class<T> projectionType
    );
}
~~~

Gọi theo entity:

~~~java
Flux<Customer> customers =
    repository.findByActiveTrue(Customer.class);
~~~

Gọi theo interface:

~~~java
Flux<CustomerContactView> contacts =
    repository.findByActiveTrue(CustomerContactView.class);
~~~

Gọi theo DTO:

~~~java
Flux<CustomerContactDto> summaries =
    repository.findByActiveTrue(CustomerContactDto.class);
~~~

Đây là điểm khác biệt chính giữa static và dynamic projection:

| Tiêu chí | Static projection | Dynamic projection |
|---|---|---|
| Kiểu kết quả | Cố định trong method signature | Caller truyền Class<T> |
| Method | Có thể cần method riêng cho từng kiểu | Một method có thể phục vụ nhiều kiểu |
| Khả năng đọc API | Rõ kiểu trả về ngay tại declaration | Linh hoạt, kiểu cụ thể thể hiện ở call site |
| Độ phức tạp | Đơn giản | Generic method và Class<T> cần được hiểu đúng |
| Khi nên dùng | Use case có read model cố định | Điều kiện giống nhau nhưng nhiều caller cần kiểu kết quả khác nhau |

Không nên dùng dynamic projection chỉ để giảm số lượng method nếu các projection có ý nghĩa nghiệp vụ khác nhau hoặc cần các truy vấn SQL khác nhau. Tách method riêng có thể làm API repository dễ hiểu hơn.

## 7. Ánh xạ DTO constructor và tên cột

Với derived query, Spring Data có thể dựa trên metadata entity và constructor của DTO để ánh xạ các property cần thiết.

Ví dụ:

~~~java
public record CustomerContactDto(
    String fullName,
    String email
) {}
~~~

Property Java là fullName và email. Nếu entity ánh xạ fullName vào cột full_name qua @Column, Spring Data dùng metadata mapping để liên hệ property với cột.

Với @Query, SQL do ứng dụng viết nên cần bảo đảm tên cột/alias khớp với property DTO:

~~~java
import org.springframework.data.r2dbc.repository.Query;
import reactor.core.publisher.Flux;

@Query("""
    SELECT full_name AS full_name,
           email AS email
    FROM customer
    WHERE active = TRUE
    """)
Flux<CustomerContactDto> findActiveContacts();
~~~

Alias giúp kết quả có tên cột rõ ràng cho quá trình mapping. Tên alias cần phù hợp với quy tắc converter và database về chữ hoa/thường của identifier.

Nếu DTO có nhiều constructor, hãy chỉ rõ constructor persistence bằng @PersistenceCreator. Nếu dùng Java class thay vì record, bảo đảm tên tham số constructor có thể được khám phá và tương ứng với property.

## 8. Projection và SQL được chọn

Một mục tiêu của projection là chỉ đọc những cột cần thiết. Closed projection giúp Spring Data xác định property cần thiết, nhưng mức tối ưu SELECT phụ thuộc loại truy vấn và khả năng của module.

Với derived query, framework có thể tối ưu trường được lấy dựa trên projection metadata khi có hỗ trợ. Với @Query viết SQL cố định, danh sách cột do câu SQL quyết định. Dynamic projection không tự bảo đảm rằng SQL tùy chỉnh sẽ được viết lại theo từng projection.

Hãy phân biệt:

- **Projection mapping**: chuyển dữ liệu truy vấn thành kiểu kết quả.
- **Column selection**: quyết định database trả về cột nào.
- **Query execution**: database thực thi SQL và trả về các hàng.

Projection mapping thành công không nhất thiết có nghĩa SQL chỉ lấy đúng số cột cần thiết. Nếu hiệu năng phụ thuộc vào việc giảm cột, hãy kiểm tra SQL log hoặc execution trace.

## 9. Chọn projection với R2dbcEntityTemplate

R2dbcEntityTemplate thường được dùng khi cần xây dựng Query động ở mức entity:

~~~java
Query query = Query.query(
    Criteria.where("active").is(true)
);

Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

API select theo kiểu entity phù hợp khi kết quả cần ánh xạ thành entity Customer. Nếu muốn một read model hoàn toàn khác hoặc cần chọn cột, join và phép tính riêng, hãy cân nhắc DatabaseClient để tự định nghĩa SQL và map Row.

Ví dụ DTO với DatabaseClient:

~~~java
public record CustomerContactDto(
    String fullName,
    String email
) {}

Flux<CustomerContactDto> contacts =
    databaseClient.sql("""
            SELECT full_name, email
            FROM customer
            WHERE active = :active
            """)
        .bind("active", true)
        .map((row, metadata) ->
            new CustomerContactDto(
                row.get("full_name", String.class),
                row.get("email", String.class)
            )
        )
        .all();
~~~

Ở đây, kiểu kết quả được chọn trực tiếp trong callback map. Đây là cách phù hợp khi SQL và cấu trúc DTO cần được kiểm soát tường minh.

## 10. Projection không phải entity để cập nhật

Một projection có thể thiếu ID, version hoặc property cần thiết cho một thao tác update. Không nên lấy một DTO chỉ có tên/email rồi xem nó là Customer đầy đủ.

Ví dụ:

~~~java
CustomerContactDto contact =
    new CustomerContactDto("Nguyen An", "an@example.com");
~~~

DTO này không có ID và version. Nó không thể đại diện an toàn cho một aggregate Customer để gọi save.

Nếu cần cập nhật, hãy dùng ID để tải entity đầy đủ, áp dụng thay đổi domain rồi lưu entity:

~~~java
Mono<Customer> rename(
        Long customerId,
        String newName) {

    return repository.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalArgumentException("Customer not found")
        ))
        .map(customer -> new Customer(
            customer.id(),
            newName,
            customer.email(),
            customer.phone(),
            customer.active(),
            customer.version()
        ))
        .flatMap(repository::save);
}
~~~

Đây là ví dụ với immutable record. Repository trả về entity được lưu; hãy tiếp tục sử dụng giá trị phát ra từ save để nhận ID/version cập nhật nếu có.

## 11. Lựa chọn kiểu kết quả theo use case

| Nhu cầu | Kiểu kết quả nên cân nhắc | Lý do |
|---|---|---|
| Đọc và xử lý toàn bộ aggregate | Entity | Có đầy đủ trạng thái cần cho nghiệp vụ |
| Trang danh sách chỉ hiển thị vài trường | Closed interface projection | Khai báo đúng các accessor cần đọc |
| API cần read model rõ ràng | DTO/record | Kiểu kết quả độc lập với entity |
| Cùng điều kiện nhưng nhiều caller cần các cấu trúc khác nhau | Dynamic projection | Chọn Class<T> tại call site |
| Báo cáo có join và phép tính | DTO qua @Query hoặc DatabaseClient | Kiểm soát SQL và cột kết quả |
| Truy vấn động ở mức entity | R2dbcEntityTemplate | Dùng Criteria và mapping của Spring Data |
| Chỉ cần số lượng | Mono<Long> | Không cần tải toàn bộ entity |
| Chỉ cần biết có bản ghi hay không | Mono<Boolean> | Trả kết quả tồn tại |
| Có thể có nhiều hàng | Flux<T> | Phát nhiều kết quả reactive |
| Tối đa một hàng | Mono<T> | Biểu diễn 0 hoặc 1 kết quả |

Chọn kiểu trả về theo đúng cardinality. Một projection DTO không quyết định truy vấn có một hay nhiều hàng; đó là lý do Mono và Flux vẫn cần được lựa chọn riêng.

## 12. Những giới hạn và trường hợp cần thận trọng

### 12.1. Nested projection không tự động tạo join

Một accessor lồng nhau không có nghĩa Spring Data R2DBC sẽ tự tạo join hoặc tải aggregate khác. Spring Data Relational không hoạt động như ORM tự động lazy-load object graph.

Nếu cần dữ liệu từ bảng khác, hãy viết truy vấn join phù hợp bằng @Query hoặc DatabaseClient, hoặc thực hiện các truy vấn riêng và kết hợp publisher trong service.

### 12.2. Open projection khó tối ưu cột

Biểu thức SpEL có thể tham chiếu nhiều property nên framework khó xác định chính xác tập cột cần đọc. Closed projection và DTO constructor rõ ràng thường dễ dự đoán hơn.

### 12.3. Dynamic projection không thay thế query design

Class<T> chỉ chọn kiểu kết quả. Nó không làm một truy vấn phức tạp trở nên đơn giản hơn, không tạo join tự động và không thêm điều kiện lọc.

Nếu hai kiểu kết quả cần SQL khác nhau đáng kể, hãy tách query method hoặc custom repository fragment.

### 12.4. Constructor mapping phụ thuộc tên property

DTO projection cần tham số constructor phù hợp với property/alias. Tên sai hoặc dữ liệu không đủ có thể gây lỗi mapping hoặc nhận giá trị thiếu.

Cách xử lý: đối chiếu property Java, tên cột và alias SQL; với class nhiều constructor, chỉ rõ constructor persistence.

### 12.5. Projection một phần không mang đủ trạng thái persistence

DTO có thể không chứa ID hoặc version. Dùng nó cho read path; nếu cần ghi, hãy tải entity đầy đủ hoặc thực hiện lệnh update chuyên biệt với điều kiện rõ ràng.

### 12.6. Không phải mọi query method đều tối ưu SELECT giống nhau

Derived query, @Query và custom repository có đường tạo SQL khác nhau. Hãy xem câu SQL thực tế nếu cần bảo đảm chỉ chọn các cột cần thiết.

## 13. Các lỗi thường gặp

**Dùng sai kiểu Class trong dynamic projection**

Method cần generic type phù hợp:

~~~java
<T> Flux<T> findByActiveTrue(Class<T> type);
~~~

Nếu kiểu Class không khớp với generic return type, Spring Data có thể không nhận diện nó là tham số projection.

**Tên DTO không khớp property**

DTO có component name nhưng entity property là fullName; converter có thể không ánh xạ như mong muốn. Hãy đổi tên component hoặc dùng SQL alias phù hợp.

**Projection thiếu cột cần cho constructor**

Nếu constructor DTO yêu cầu ba property nhưng query chỉ trả hai cột, mapping có thể thất bại. Chọn đủ dữ liệu hoặc thay DTO cho phù hợp.

**Dùng projection để save**

Projection không nhất thiết chứa ID/version hoặc trạng thái aggregate. Không xem nó như entity đầy đủ.

**Giả định interface projection luôn giảm số cột**

Projection mô tả kiểu kết quả; SQL thực tế phụ thuộc query path và module. Kiểm tra câu SQL nếu tối ưu cột là yêu cầu.

**Dùng Mono cho truy vấn nhiều hàng**

Nếu query có thể trả nhiều hàng, dùng Flux. Mono biểu diễn tối đa một phần tử.

**Dùng dynamic projection cho các query khác nhau**

Nếu mỗi kiểu kết quả cần join hoặc điều kiện khác nhau, một method generic không còn làm API rõ ràng. Tách method hoặc dùng custom repository.

## 14. Nguyên tắc thiết kế

- Dùng entity đầy đủ cho thao tác nghiệp vụ cần trạng thái aggregate.
- Dùng closed interface projection cho view đọc nhỏ, đơn giản.
- Dùng DTO/record khi muốn read model có kiểu dữ liệu độc lập.
- Dùng dynamic projection khi cùng điều kiện truy vấn thực sự phục vụ nhiều kiểu kết quả.
- Đặt tên accessor và constructor parameter tương ứng với property hoặc alias.
- Với @Query, kiểm soát SELECT list và alias tường minh.
- Không giả định nested projection tự tạo join.
- Không dùng projection một phần để cập nhật entity.
- Chọn Mono cho tối đa một kết quả và Flux cho nhiều kết quả.
- Kiểm tra SQL thực tế nếu cần xác nhận tối ưu cột.
- Dùng DatabaseClient cho join, aggregate và mapping đặc thù.
- Giữ việc chọn kiểu kết quả trong repository/service contract rõ ràng, tránh generic hóa chỉ để giảm số method.

## 15. Ghi nhớ

Projection xác định hình dạng dữ liệu mà truy vấn trả về. Interface projection mô tả các accessor cần thiết; DTO/record projection tạo kiểu kết quả cụ thể qua constructor; dynamic projection cho phép truyền Class<T> để chọn kiểu kết quả tại thời điểm gọi repository.

Dynamic projection hữu ích khi cùng một điều kiện tìm kiếm cần phục vụ nhiều caller với các read model khác nhau. Nó không tự tạo join, không thay đổi điều kiện lọc và không bảo đảm SQL tùy chỉnh sẽ tự chọn đúng cột cho mọi kiểu kết quả. Khi cần truy vấn cố định, dùng derived query hoặc @Query; khi cần điều kiện động ở mức entity, dùng R2dbcEntityTemplate; khi cần SQL và projection tùy chỉnh, dùng DatabaseClient. Chọn đúng result type và Mono/Flux giúp repository contract thể hiện chính xác dữ liệu mà mỗi use case cần.

