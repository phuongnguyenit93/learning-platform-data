# Lưu theo projection bằng Neo4jTemplate.saveAs

Bài học này thuộc chương **Projection và DTO** của module **SPRING_DATA_NEO4J**. Một entity trong ứng dụng có thể chứa nhiều property và relationship, nhưng mỗi thao tác cập nhật chỉ cần thay đổi một phần graph. Nếu gọi `save()` thông thường với toàn bộ entity, Spring Data Neo4j sẽ xử lý các property và quan hệ được ánh xạ trên entity đó. `Neo4jTemplate.saveAs()` cho phép giới hạn phần graph được ghi bằng một projection.

Projection trong trường hợp này đóng vai trò **bản thiết kế phạm vi ghi**. Nó chỉ ra những property và relationship nào được đưa vào thao tác save. Điều này hữu ích khi một use case chỉ cập nhật thông tin liên hệ, một use case khác cập nhật địa chỉ, hoặc khi muốn kiểm soát phần graph được persistence xử lý. Tuy nhiên, projection không tự tải dữ liệu còn thiếu và không thay thế việc quản lý transaction, kiểm tra quyền hay xác thực dữ liệu đầu vào.

## 1. save() và saveAs() khác nhau thế nào?

`Neo4jTemplate.save(entity)` lưu entity cùng các entity liên quan được mô tả trong graph mapping. `Neo4jTemplate.saveAs(entity, Projection.class)` lưu entity nhưng chỉ xét các property và relationship được khai báo trong projection.

| API | Phạm vi ghi | Kiểu kết quả |
|---|---|---|
| `save(entity)` | Entity và graph quan hệ theo mapping đầy đủ | Entity đã lưu |
| `saveAs(entity, Projection.class)` | Property và relationship có trong projection | Projection đã lưu |
| `saveAs(entity, includeProperty)` | Property được predicate chọn | Entity đã lưu theo kiểu domain |
| `saveAllAs(entities, Projection.class)` | Projection áp dụng cho từng entity trong collection | Danh sách projection đã lưu |

API `saveAs` có hai overload chính:

```java
<T, R> R saveAs(T instance, Class<R> resultType);

<T> T saveAs(
    T instance,
    BiPredicate<PropertyPath, Neo4jPersistentProperty> includeProperty
);
```

Overload thứ nhất dùng một kiểu projection tĩnh. Overload thứ hai dùng predicate để chọn property động theo từng đường dẫn. Cả hai đều điều khiển phạm vi graph được ghi.

## 2. Entity ví dụ

Giả sử ứng dụng quản lý khách hàng. Entity `Customer` có thông tin liên hệ, ghi chú nội bộ và quan hệ tới địa chỉ:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String name;

    private String email;

    private String internalNote;

    @Relationship(type = "LIVES_AT")
    private Address address;

    // constructors, getters and setters
}
```

Node `Address`:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Address")
public class Address {

    @Id
    private String id;

    private String street;

    private String city;

    private String postalCode;

    // constructors, getters and setters
}
```

Một entity có thể chứa nhiều dữ liệu hơn phạm vi cần cập nhật. Ví dụ, use case chỉnh email chỉ cần `name` và `email`; nó không cần thay đổi `internalNote`, địa chỉ hoặc relationship `LIVES_AT`.

## 3. Khai báo projection làm write blueprint

Tạo interface projection chỉ gồm các property cần lưu:

```java
public interface CustomerContactProjection {

    String getName();

    String getEmail();
}
```

Các accessor của interface cần tương ứng với property của domain entity. Trong ví dụ này, `getName()` ánh xạ tới `Customer.name` và `getEmail()` ánh xạ tới `Customer.email`.

Projection không phải entity mới và không tạo label Neo4j riêng. Nó chỉ mô tả phần dữ liệu mà thao tác persistence sẽ xét. Các annotation mapping trên domain type như `@Property` hoặc `@Relationship` vẫn cung cấp metadata để SDN ánh xạ đúng property trong graph.

## 4. Lưu entity theo projection bằng saveAs

Inject `Neo4jTemplate` và truyền domain object cùng kiểu projection. Trong cấu hình Spring Data Neo4j, `Neo4jTemplate` là implementation của `Neo4jOperations`; service có thể inject `Neo4jTemplate` trực tiếp như ví dụ hoặc phụ thuộc abstraction `Neo4jOperations` nếu muốn giảm phụ thuộc vào implementation:

```java
import com.example.graph.domain.Customer;
import com.example.graph.projection.CustomerContactProjection;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {

    private final Neo4jTemplate neo4jTemplate;

    public CustomerService(Neo4jTemplate neo4jTemplate) {
        this.neo4jTemplate = neo4jTemplate;
    }

    public CustomerContactProjection saveContact(Customer customer) {
        return neo4jTemplate.saveAs(
            customer,
            CustomerContactProjection.class
        );
    }
}
```

Khi gọi `saveContact(customer)`, SDN chỉ xét `name` và `email` theo projection `CustomerContactProjection`. Các property khác như `internalNote` và relationship `address` nằm ngoài projection nên không thuộc phạm vi cập nhật của lần gọi này.

Giả sử database đang có:

```text
(:Customer {
    id: 'cus-100',
    name: 'Lan',
    email: 'old@example.com',
    internalNote: 'VIP customer'
})-[:LIVES_AT]->(:Address {city: 'Đà Nẵng'})
```

Ứng dụng sửa `customer.email` thành `lan@example.com` rồi gọi `saveAs`. Thao tác chỉ cập nhật các property trong projection. `internalNote` và relationship `LIVES_AT` không bị đưa vào phạm vi ghi của projection này.

## 5. Giá trị trả về là projection

Khác với `save(entity)`, overload `saveAs(entity, Projection.class)` trả về kiểu projection `R`, không trả về nguyên kiểu domain `T`.

```java
CustomerContactProjection saved = neo4jTemplate.saveAs(
    customer,
    CustomerContactProjection.class
);

String savedName = saved.getName();
String savedEmail = saved.getEmail();
```

Giá trị trả về phù hợp để dùng trong luồng cần đúng phần dữ liệu đã chọn. Không nên xem nó là một `Customer` đầy đủ. Projection có thể không chứa ID, ghi chú hoặc quan hệ địa chỉ nếu các trường đó không được khai báo.

Nếu cần tiếp tục xử lý toàn bộ aggregate, hãy tải lại entity đầy đủ bằng repository hoặc `Neo4jTemplate.findById(...)`. Tài liệu API cảnh báo instance được trả về từ thao tác save theo projection có thể chưa hydrate đầy đủ; tái sử dụng instance đó trong một thao tác save thông thường có thể gây mất dữ liệu.

## 6. Lưu cả relationship khi projection khai báo association

Projection có thể bao gồm relationship và projection lồng nhau cho node liên quan. Ví dụ, một use case cần cập nhật tên khách hàng và thành phố của địa chỉ:

```java
public interface CustomerAddressProjection {

    String getName();

    AddressProjection getAddress();

    interface AddressProjection {
        String getCity();
    }
}
```

Lưu bằng projection:

```java
CustomerAddressProjection saved = neo4jTemplate.saveAs(
    customer,
    CustomerAddressProjection.class
);
```

Projection trên bao gồm property `name`, association `address` và property `city` của node địa chỉ. Vì association `address` được khai báo, nó thuộc phạm vi graph mà thao tác save xét. Các property `street` và `postalCode` của địa chỉ không nằm trong projection lồng nhau.

Khi muốn cập nhật property của node liên quan, phải đưa chính association vào projection. Chỉ khai báo các trường scalar của root không khiến SDN tự cập nhật các node liên quan. Với relationship có thuộc tính riêng, lớp `@RelationshipProperties` cũng được xem là một entity trong projection nhiều cấp; hãy mô tả cả property trên relationship và projection của `@TargetNode` khi use case cần ghi chúng.

## 7. Cẩn thận khi projection bao gồm collection relationship

Giả sử `Customer` có nhiều địa chỉ giao hàng:

```java
import java.util.List;

import org.springframework.data.neo4j.core.schema.Relationship;

@Relationship(type = "DELIVERS_TO")
private List<Address> deliveryAddresses;
```

Projection có thể khai báo:

```java
public interface CustomerDeliveryProjection {

    String getName();

    List<AddressProjection> getDeliveryAddresses();

    interface AddressProjection {
        String getCity();
    }
}
```

Khi `deliveryAddresses` nằm trong projection, collection relationship thuộc phạm vi ghi. Nếu entity đầu vào chỉ chứa một phần địa chỉ do trước đó được tải bằng truy vấn lọc hoặc phân trang, thao tác save theo projection có thể làm mất các relationship không có trong collection đó.

Ví dụ, database có ba địa chỉ A, B và C. Ứng dụng chỉ tải A và B, sau đó truyền entity vào `saveAs` với projection có `deliveryAddresses`. SDN chỉ nhận được hai phần tử từ object. Nếu projection được dùng để ghi toàn bộ association, relationship tới C có thể bị loại bỏ theo trạng thái collection được gửi vào.

Để tránh xóa dữ liệu ngoài ý muốn, hãy tải ít nhất toàn bộ dữ liệu thuộc association sẽ được ghi. Nếu chỉ muốn cập nhật một địa chỉ, hãy dùng một thao tác nhắm đúng node/relationship đó hoặc dùng một projection chỉ chứa những phần cần ghi mà không đưa collection chưa đầy đủ vào phạm vi save.

## 8. Dùng predicate để chọn property động

Nếu phạm vi ghi thay đổi theo điều kiện runtime, có thể dùng overload `saveAs` nhận `BiPredicate<PropertyPath, Neo4jPersistentProperty>`.

Ví dụ chọn hai property cấp root:

```java
import java.util.Set;

import com.example.graph.domain.Customer;
import org.springframework.data.neo4j.core.Neo4jTemplate;

Set<String> includedPaths = Set.of("name", "email");

Customer saved = neo4jTemplate.saveAs(
    customer,
    (path, property) -> includedPaths.contains(path.toDotPath())
);
```

Predicate nhận đường dẫn property và metadata của property. `path.toDotPath()` cho phép phân biệt đường dẫn lồng nhau, ví dụ `address.city`, thay vì chỉ so sánh tên field cuối cùng. Ví dụ trên chỉ chọn `name` và `email` ở root.

Nếu muốn cập nhật `address.city`, phải đưa association `address` vào phạm vi ghi và chọn property lồng nhau theo đường dẫn phù hợp. Tài liệu API nhấn mạnh rằng muốn ghi property của association, predicate phải bao gồm cả property association đó. Không chỉ chọn `address.city` mà bỏ `address` khỏi phạm vi.

Predicate là một cách tạo dynamic projection. Hãy giữ quy tắc chọn property rõ ràng, có kiểm thử cho từng đường dẫn và tránh viết điều kiện quá rộng như “mọi property không null” nếu không muốn cập nhật toàn bộ graph.

## 9. Lưu nhiều entity theo cùng projection

Khi nhiều entity cần cùng một write mask, dùng `saveAllAs`:

```java
import java.util.List;

import com.example.graph.projection.CustomerContactProjection;

List<CustomerContactProjection> savedCustomers =
    neo4jTemplate.saveAllAs(
        customers,
        CustomerContactProjection.class
    );
```

API collection có hai dạng tương tự:

```java
List<R> saveAllAs(Iterable<T> instances, Class<R> resultType);

List<T> saveAllAs(
    Iterable<T> instances,
    BiPredicate<PropertyPath, Neo4jPersistentProperty> includeProperty
);
```

`saveAllAs` áp dụng cùng projection hoặc predicate cho từng entity. Nó không tự bảo đảm một câu Cypher, một network round trip hoặc một transaction có kích thước phù hợp. Cần đánh giá riêng batching và transaction theo khối lượng graph cần lưu.

## 10. Phân biệt projection dùng để đọc và projection dùng để ghi

Một projection có thể được sử dụng khi đọc để giới hạn dữ liệu truyền về ứng dụng, và cũng có thể dùng làm blueprint cho persistence. Nhưng hai use case có mục tiêu khác nhau:

| Khía cạnh | Projection đọc | Projection ghi qua saveAs |
|---|---|---|
| Mục tiêu | Chỉ tải dữ liệu cần hiển thị/xử lý | Chỉ ghi property và relationship được chọn |
| Đầu vào | Query và kiểu projection | Domain object và kiểu projection/predicate |
| Kết quả | DTO hoặc interface projection | Projection đã lưu hoặc entity theo overload |
| Rủi ro chính | Thiếu dữ liệu nếu dùng projection như aggregate đầy đủ | Ghi thiếu hoặc xóa association nếu dữ liệu đầu vào không đầy đủ |
| Phạm vi | Đọc | Persistence |

Một interface projection thường là proxy đọc dữ liệu và không thể sửa trực tiếp như DTO mutable. Nếu cần thay đổi dữ liệu từ interface projection, hãy sao chép các giá trị cần thiết sang domain entity hoặc DTO có thể chỉnh sửa, áp dụng logic nghiệp vụ, rồi gọi `saveAs` với projection ghi phù hợp.

Ví dụ domain entity có thể cung cấp phương thức nhận dữ liệu đầu vào:

```java
public void updateContact(String name, String email) {
    this.name = name;
    this.email = email;
}
```

Service tải entity, cập nhật qua method domain rồi lưu theo projection:

```java
Customer customer = customerRepository.findById(customerId)
    .orElseThrow();

customer.updateContact(command.name(), command.email());

CustomerContactProjection saved = neo4jTemplate.saveAs(
    customer,
    CustomerContactProjection.class
);
```

## 11. Projection không phải cơ chế phân quyền

Projection giới hạn property và relationship mà một thao tác persistence xử lý. Nó không thay thế xác thực, phân quyền hoặc kiểm tra quyền sở hữu dữ liệu.

Ví dụ, việc một projection không chứa `internalNote` không có nghĩa mọi người dùng đều được phép cập nhật `name` hoặc `email`. Service vẫn cần xác minh người dùng có quyền thay đổi customer tương ứng, kiểm tra dữ liệu đầu vào và áp dụng quy tắc nghiệp vụ trước khi gọi `saveAs`.

Không nhận tên projection tùy ý từ client rồi dùng reflection để chọn kiểu ghi. Hãy để server xác định projection theo use case và quyền đã được kiểm tra.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Property không được cập nhật | Field không có trong projection | Thêm accessor tương ứng vào projection ghi |
| Association không được lưu | Projection không khai báo association | Thêm association property và projection lồng nhau |
| Mất relationship ngoài ý muốn | Collection được ghi chỉ chứa một phần dữ liệu | Tải đầy đủ association trước khi lưu hoặc loại association khỏi projection |
| Dùng sai kiểu kết quả | Nghĩ `saveAs(entity, Projection.class)` trả về entity gốc | Nhận giá trị bằng kiểu projection `R` |
| Lưu lại object trả về và mất dữ liệu | Projection trả về chưa hydrate đầy đủ | Tải lại entity đầy đủ trước thao tác save tiếp theo |
| Predicate chọn nhầm field lồng nhau | Chỉ so sánh tên property cuối | Dùng đường dẫn đầy đủ như `path.toDotPath()` |
| Cập nhật node liên quan không thành công | Predicate chọn field con nhưng bỏ association cha | Bao gồm cả association trong predicate |
| Dùng projection như phân quyền | Nhầm write mask với access control | Kiểm tra quyền và validate command ở service |

## 13. Kiểm thử saveAs

Nên dùng Neo4j Test Harness hoặc Testcontainers để kiểm tra kết quả thật trong graph. Một bộ test nên xác nhận:

1. `saveAs` với projection scalar chỉ cập nhật các field đã khai báo.
2. Property không nằm trong projection giữ nguyên giá trị hiện tại.
3. Projection có association cập nhật đúng node và relationship liên quan.
4. Projection lồng nhau chỉ ghi các property được khai báo ở từng cấp.
5. Predicate động chọn đúng property path và association cha.
6. `saveAllAs` áp dụng cùng write mask cho nhiều entity.
7. Collection association đầy đủ được ghi đúng; collection lọc không bị dùng nhầm như trạng thái đầy đủ.
8. Instance trả về từ `saveAs` không được tái sử dụng như aggregate đã hydrate đầy đủ nếu projection không chứa toàn bộ graph cần thiết.

Sau thao tác ghi, có thể đọc lại bằng một query đầy đủ hoặc kiểm tra bằng Cypher để xác nhận property và relationship ngoài projection vẫn còn. Kiểm thử không chỉ xác nhận projection trả đúng giá trị mà còn phải xác nhận phần graph không thuộc phạm vi ghi không bị thay đổi.

## 14. Nguyên tắc lựa chọn

- Dùng `saveAs(entity, Projection.class)` khi một use case có phạm vi ghi tĩnh, rõ ràng.
- Dùng `saveAs(entity, predicate)` khi cần chọn property theo điều kiện runtime.
- Dùng `saveAllAs` khi nhiều entity có chung write mask.
- Khai báo association trong projection nếu muốn cập nhật node/relationship liên quan.
- Khi association là collection, tải đầy đủ các phần tử thuộc phạm vi sẽ ghi để tránh xóa relationship ngoài ý muốn.
- Xem giá trị trả về là projection hoặc entity theo overload, không mặc định nó là aggregate đã hydrate đầy đủ.
- Tải lại entity trước lần save tiếp theo nếu cần làm việc với toàn bộ graph.
- Duy trì validation, authorization và transaction ở tầng service theo yêu cầu nghiệp vụ.

`Neo4jTemplate.saveAs()` cho phép giới hạn phần graph được ghi theo một projection tĩnh hoặc predicate động. Khi xác định đúng property và association cần cập nhật, ứng dụng có thể thực hiện các thao tác ghi có phạm vi rõ ràng. Điều quan trọng là phải hiểu projection đang bao gồm những gì, dữ liệu association đã được tải đầy đủ hay chưa và kiểu kết quả trả về có đủ dữ liệu cho bước xử lý tiếp theo hay không.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2.0 – Projections and persistence of projections](https://docs.spring.io/spring-data/neo4j/reference/8.2/projections/sdn-projections.html)
- [Spring Data Neo4j 8.2.0 – Neo4jTemplate API](https://docs.spring.io/spring-data/neo4j/reference/8.2/api/java/org/springframework/data/neo4j/core/Neo4jTemplate.html)
- [Spring Data Neo4j 8.2.0 – Neo4jOperations API](https://docs.spring.io/spring-data/neo4j/reference/8.2/api/java/org/springframework/data/neo4j/core/Neo4jOperations.html)
