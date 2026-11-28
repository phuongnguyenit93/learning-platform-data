# Projection interface đóng và projection mở

Trong Spring Data Neo4j (SDN), projection interface cho phép trả về một góc nhìn được chọn lọc từ entity, thay vì luôn tải và đưa toàn bộ aggregate root cho tầng gọi. Interface projection được SDN hiện thực bằng proxy tại runtime; các getter của interface truy cập property trên entity đích.

Có hai dạng cần phân biệt. **Closed projection** chỉ khai báo các accessor tương ứng với property đã biết của entity. Vì SDN biết trước tập dữ liệu mà projection cần, framework có thể tối ưu truy vấn và giới hạn property hoặc relationship được tải. **Open projection** dùng `@Value` cùng SpEL để tính property mới từ đối tượng đích. Biểu thức có thể truy cập bất kỳ property nào, nên SDN không thể dựa vào danh sách getter để thu hẹp dữ liệu an toàn như với closed projection.

## 1. Projection interface dùng để làm gì?

Giả sử entity `Person` có nhiều dữ liệu: mã định danh, tên, email, số điện thoại, địa chỉ và các relationship khác. Một màn hình danh sách chỉ cần tên và email. Nếu repository luôn trả `Person`, tầng ứng dụng nhận cả entity cùng graph được ánh xạ theo query và mapping metadata, dù màn hình chỉ dùng hai field.

Projection mô tả đúng góc nhìn mà use case cần:

```java
import java.util.Optional;

public interface PersonContact {

    String getFirstName();

    String getLastName();

    Optional<String> getEmail();
}
```

Repository có thể trả về projection thay vì entity:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    List<PersonContact> findByLastName(String lastName);
}
```

Khi gọi `findByLastName`, Spring Data tạo proxy `PersonContact` cho mỗi kết quả. Lời gọi `getFirstName()` được chuyển tới property `firstName` của entity đích; `getEmail()` đọc property `email`. Interface projection là kiểu trả về mô tả dữ liệu cần đọc, không phải một node entity mới trong Neo4j.

## 2. Closed projection: accessor khớp property của entity

Một interface là closed projection khi tất cả accessor của nó khớp với property có trong domain type. Ví dụ:

```java
public interface PersonName {

    String getFirstName();

    String getLastName();
}
```

Các getter chỉ tham chiếu hai property đã biết của `Person`. SDN có thể xác định trước projection cần gì và tối ưu query execution. Trong SDN, projection ảnh hưởng trực tiếp đến những property và relationship được truyền từ database về ứng dụng; lợi ích này đặc biệt rõ khi entity có nhiều property hoặc graph có nhiều nhánh relationship mà use case hiện tại không cần.

Ví dụ domain entity:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Property;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Person")
public class Person {

    @Id
    private String personId;

    @Property("first_name")
    private String firstName;

    @Property("last_name")
    private String lastName;

    private String email;

    private String phoneNumber;

    @Relationship(type = "HAS_ADDRESS")
    private Address address;

    public String getFirstName() { return firstName; }
    public String getLastName() { return lastName; }
    public String getEmail() { return email; }
}
```

Trong ví dụ nested projection bên dưới, `Address` là node được nối với `Person` qua relationship `HAS_ADDRESS` và có các property `city`, `country`.

Projection vẫn dùng tên property Java (`getFirstName`, `getLastName`), dù tên lưu trong Neo4j lần lượt là `first_name` và `last_name`. SDN dùng metadata `@Property` của entity để ánh xạ đúng tên property database. Không đặt tên getter theo tên key trong Cypher nếu tên đó khác persistent property của domain type.

### Tại sao closed projection có thể nhanh hơn?

Khi chỉ cần hai property, việc giới hạn dữ liệu đọc có thể giảm:

- Số property phải lấy và chuyển đổi từ Neo4j.
- Số relationship cần mở rộng hoặc ánh xạ nếu projection không yêu cầu chúng.
- Lượng object được tạo và dữ liệu truyền qua driver.
- Bộ nhớ cần dùng ở tầng ứng dụng khi xử lý danh sách lớn.

Mức cải thiện thực tế phụ thuộc cấu trúc graph, query và phiên bản SDN. Projection không thay thế index, giới hạn kết quả hoặc việc thiết kế truy vấn tốt; nó giúp mô tả chính xác dữ liệu mà use case cần.

## 3. Nested closed projection: chọn dữ liệu ở nhiều cấp

Closed projection có thể lồng nhau để chỉ lấy một phần thông tin từ property phức hợp hoặc relationship. Ví dụ màn hình hồ sơ chỉ cần tên người và thành phố của địa chỉ:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Address")
public class Address {

    @Id
    private String addressId;

    private String city;

    private String country;
}
```

Projection nhiều cấp:

```java
public interface PersonProfile {

    String getFirstName();

    String getLastName();

    AddressSummary getAddress();

    interface AddressSummary {
        String getCity();
        String getCountry();
    }
}
```

Khi gọi `getAddress()`, projection trả về một proxy lồng nhau cho property `address`; các getter của `AddressSummary` chỉ đọc `city` và `country`. Cách này giúp giữ cấu trúc kết quả gần với domain graph nhưng vẫn giới hạn phần dữ liệu được phơi bày.

Với relationship, nguyên tắc tương tự áp dụng: projection lồng nhau phải trỏ tới property/relationship có trong domain type, và chỉ khai báo các getter thực sự cần. SDN hỗ trợ projection nhiều cấp; các relationship properties cũng được tính đến trong quá trình áp dụng projection.

Không nên tạo projection lồng nhau quá sâu hoặc đi vòng qua những quan hệ có chu trình trong graph. SDN giới hạn việc tạo query để tránh đi theo vòng lặp projection vô hạn, nhưng thiết kế projection quá rộng vẫn có thể tạo query phức tạp và tải nhiều dữ liệu.

## 4. Open projection: tính property bằng `@Value` và SpEL

Open projection cho phép khai báo một accessor không tương ứng trực tiếp với property lưu trong entity. Dùng `@Value` để tính giá trị từ đối tượng đích (`target`):

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplayFromAccessors {

    String getFirstName();

    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
```

`getFullName()` không yêu cầu entity có property `fullName`. Spring đánh giá biểu thức SpEL khi accessor được gọi; `target` là entity đích của projection. Đây là open projection vì expression có thể tham chiếu bất kỳ property nào của target, kể cả những property không xuất hiện dưới dạng getter trong interface.

Open projection phù hợp với phép biến đổi nhỏ, ví dụ ghép tên hoặc định dạng một giá trị hiển thị. Tuy nhiên, vì SpEL có thể truy cập toàn bộ target, SDN không thể dựa vào các accessor đã khai báo để giới hạn query như closed projection. Nếu mục tiêu chính là giảm dữ liệu đọc, ưu tiên closed projection.

## 5. Dùng default method khi chỉ cần kết hợp accessor có sẵn

Không phải phép tính nào cũng cần `@Value`. Nếu giá trị mới chỉ được tạo từ các accessor đã khai báo, có thể dùng default method:

```java
public interface PersonDisplay {

    String getFirstName();

    String getLastName();

    default String getFullName() {
        return getFirstName() + " " + getLastName();
    }
}
```

Các accessor dữ liệu vẫn là `getFirstName()` và `getLastName()`. `getFullName()` gọi lại chính các accessor này để tính kết quả, không cần truy cập thêm property khác trên target. Vì vậy, projection có thể giữ đặc tính closed và vẫn hưởng khả năng tối ưu dựa trên tập property đã biết.

Hãy chọn cách đơn giản nhất:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Chỉ lấy property có sẵn | Closed projection |
| Tính giá trị từ các accessor đã có | Default method trong closed projection |
| Dùng SpEL để truy cập target hoặc gọi logic ngoài interface | Open projection với `@Value` |
| Logic nghiệp vụ dài hoặc cần tái sử dụng | Service hoặc Spring bean chuyên trách |

## 6. Dùng Spring bean trong open projection

Khi biểu thức trở nên phức tạp, không nên viết toàn bộ logic trong chuỗi SpEL. Có thể chuyển xử lý sang Spring bean và gọi bean từ `@Value`:

```java
import org.springframework.stereotype.Component;

@Component
public class PersonFormatter {

    public String format(Person person) {
        return person.getLastName() + ", " + person.getFirstName();
    }
}
```

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonDisplay {

    @Value("#{@personFormatter.format(target)}")
    String getDisplayName();
}
```

SpEL gọi bean `personFormatter` và truyền entity đích qua biến `target`. Cách này giúp logic Java dễ kiểm thử và dễ tái sử dụng hơn. Tuy nhiên, projection vẫn là open projection: bean có thể đọc bất kỳ property nào trên entity, vì vậy không nên kỳ vọng SDN chỉ tải các property được khai báo bằng getter.

Method của open projection cũng có thể nhận tham số. Các tham số đó có thể được truy cập qua mảng `args` trong SpEL:

```java
import org.springframework.beans.factory.annotation.Value;

public interface PersonGreeting {

    @Value("#{args[0] + ' ' + target.firstName + '!'}")
    String getGreeting(String prefix);
}
```

Trong ví dụ, `args[0]` là giá trị `prefix` truyền vào `getGreeting`. Hãy giữ expression ngắn và dễ đọc; nếu logic có nhiều nhánh hoặc phụ thuộc nghiệp vụ, chuyển nó sang bean hoặc service.

## 7. Xử lý property có thể null

Getter của projection interface có thể dùng wrapper nullable để biểu diễn dữ liệu không có:

```java
import java.util.Optional;

public interface PersonContactNullable {

    String getFirstName();

    Optional<String> getEmail();
}
```

Nếu property `email` có giá trị, getter trả về `Optional` có dữ liệu; nếu property không tồn tại hoặc null, getter trả `Optional.empty()`. Tài liệu Spring Data cũng liệt kê một số wrapper khác như Guava `Optional`, Scala `Option` và Vavr `Option`; hãy kiểm tra dependency và phiên bản đang sử dụng trước khi chọn chúng.

Dùng wrapper giúp người gọi nhận biết rõ property là tùy chọn. Với dữ liệu bắt buộc, vẫn nên xác thực ở tầng nghiệp vụ và bảo vệ tính toàn vẹn dữ liệu trong database khi có thể.

## 8. Những giới hạn cần hiểu trước khi dùng projection

**Projection phải nằm ngoài type hierarchy của entity.** Theo quy tắc Spring Data, nếu một phương thức repository trả về superclass hoặc interface mà entity đã triển khai, kết quả là entity được materialize đầy đủ, không phải projection. Muốn tạo projection, hãy khai báo một interface riêng chỉ mô tả các accessor cần đọc.

**Accessor phải khớp property của domain type.** Với closed projection, `getFirstName()` tương ứng property Java `firstName`. Nếu property trong Neo4j có alias qua `@Property`, mapping metadata của entity sẽ xử lý tên database. Projection không thể tự tạo property tùy ý bằng cách đặt getter mới; getter tính toán cần default method hoặc `@Value`.

**Không dùng projection interface như entity để cập nhật trực tiếp.** Interface projection là proxy đọc từ entity đích. Nếu cần thay đổi dữ liệu, hãy tải entity phù hợp, cập nhật entity rồi lưu qua repository/template. SDN có cơ chế lưu projection thông qua `Neo4jTemplate`, nhưng cần hiểu projection được dùng như blueprint cho những field/relationship nào được ghi và phải tải đủ dữ liệu cần giữ để tránh loại bỏ relationship ngoài ý muốn.

**Không tùy tiện override CRUD method để đổi kiểu trả về.** Các method kế thừa như `findById` có thể tiếp tục gọi implementation cơ sở thay vì trở thành query method projection chỉ vì thay return type. Hãy tạo query method riêng với tên phù hợp hoặc dùng `@Query` theo quy tắc của SDN.

**Open projection có chi phí và rủi ro phụ thuộc dữ liệu rộng hơn.** SpEL có thể truy cập property ngoài interface. Giữ expression ngắn, tránh side effect và không đặt truy vấn bổ sung trong getter. Nếu cần logic phức tạp, dùng service/bean chuyên trách.

## 9. Chọn closed hay open projection?

| Tiêu chí | Closed projection | Open projection |
| --- | --- | --- |
| Cách khai báo | Getter khớp property domain type | Getter có thể tính bằng `@Value`/SpEL |
| Biết trước tập property cần dùng | Có | Không chắc, vì expression có thể truy cập target rộng hơn |
| Tối ưu query theo property được chọn | Có thể | Không thể áp dụng tối ưu tương tự một cách an toàn |
| Logic tính toán | Default method dựa trên accessor đã khai báo | SpEL, method arguments hoặc Spring bean |
| Phù hợp | API đọc danh sách, màn hình chi tiết gọn, response ổn định | Giá trị hiển thị tính nhanh từ entity hoặc tích hợp formatter nhỏ |

Ví dụ quyết định:

- Màn hình danh sách chỉ cần tên và email: dùng `PersonContact` closed projection.
- Cần ghép `firstName` và `lastName`: thêm default method vào closed projection.
- Cần gọi formatter để tạo nhãn hiển thị từ nhiều field của target: dùng open projection hoặc chuyển formatter sang service.
- Cần truy vấn thống kê, aggregate hoặc DTO có field không thuộc entity: cân nhắc DTO projection hoặc custom query thay vì ép logic vào interface projection.

## 10. Kiểm tra projection trong ứng dụng

Khi thêm projection, hãy kiểm tra cả nội dung lẫn query được thực thi:

1. Getter của closed projection khớp persistent property trong domain type.
2. Getter nested trỏ tới property hoặc relationship thực sự có trong mapping.
3. Property tùy chọn được khai báo bằng kiểu nullable phù hợp như `Optional<T>`.
4. Open projection chỉ chứa biểu thức ngắn, không có side effect hoặc truy vấn ẩn.
5. Method repository không vô tình override CRUD method với kỳ vọng đổi return type.
6. Integration test xác nhận kết quả projection đúng và không đọc thiếu relationship cần thiết.
7. Với truy vấn lớn, kiểm tra query/execution plan và so sánh dữ liệu được tải giữa entity đầy đủ và closed projection.

## Kết luận

Closed projection là lựa chọn ưu tiên khi cần một tập property xác định: các getter khớp property của domain type và SDN có thể tối ưu truy vấn theo tập dữ liệu đó. Open projection dùng `@Value`/SpEL để tính property mới từ `target`, nhưng vì expression có thể truy cập bất kỳ property nào nên không có cùng khả năng tối ưu. Nếu chỉ cần tính giá trị từ accessor đã khai báo, dùng default method để giữ projection đóng; nếu logic phức tạp, chuyển sang Spring bean hoặc service. Chọn đúng loại projection giúp API rõ ràng, hạn chế dữ liệu không cần thiết và giữ mapping Neo4j dễ bảo trì.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.2.0 — Projections](https://docs.spring.io/spring-data/neo4j/reference/repositories/projections.html)
- [Spring Data Neo4j 8.2.0 — Projection mapping specifics](https://docs.spring.io/spring-data/neo4j/reference/projections/sdn-projections.html)
- [Spring Data Neo4j 6.2.5 — Closed and Open Projections](https://docs.spring.io/spring-data/neo4j/docs/6.2.5/reference/html/)
