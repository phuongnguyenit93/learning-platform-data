# Projection đóng và các accessor khớp thuộc tính

## 1. Projection đóng mô tả một tập thuộc tính xác định

Một màn hình danh sách khách hàng có thể chỉ cần mã định danh, họ tên và trạng thái hoạt động. Nếu repository trả toàn bộ entity, bên gọi nhận một mô hình rộng hơn nhu cầu của màn hình đó.

Interface projection cung cấp một kiểu trả về dành cho dữ liệu cần đọc:

```java
public interface CustomerListItem {

    Long getId();

    String getFirstName();

    String getLastName();

    boolean isActive();
}
```

Khi mọi accessor đầu vào của interface đều khớp với thuộc tính của aggregate đích, đó là **projection đóng**. Tập thuộc tính cần cung cấp cho projection có thể được xác định trước. Đây là cơ sở để module store có khả năng tối ưu truy vấn. Xem [Spring Data Commons — Closed Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.interfaces.closed).

Trong ví dụ này, tập đầu vào là:

```text
id
firstName
lastName
active
```

Từ “đóng” nói về tập dữ liệu đầu vào có thể xác định từ projection. Nó không khẳng định mọi thuộc tính của entity đều phải xuất hiện trong interface.

Bài học này tập trung vào cách khai báo accessor và dùng projection trong repository. Ví dụ mapping cụ thể sử dụng JPA; các module store khác cần được đối chiếu theo khả năng riêng.

## 2. Accessor khớp thuộc tính như thế nào?

### 2.1. Tên property là hợp đồng quan trọng

Với kiểu accessor JavaBeans thông dụng, tên phương thức được diễn giải thành tên thuộc tính:

| Accessor | Thuộc tính được yêu cầu | Đánh giá khi domain có `firstName`, `lastName`, `active` |
|---|---|---|
| `String getFirstName()` | `firstName` | Khớp |
| `String getLastName()` | `lastName` | Khớp |
| `boolean isActive()` | `active` | Khớp với boolean của ví dụ |
| `String getFirstname()` | `firstname` | Khác `firstName` |
| `String getFirst_name()` | `first_name` | Không phải property `firstName` |
| `String getDisplayName()` | `displayName` | Cần property này hoặc một cách tính được khai báo rõ |
| `String firstName()` | Không theo dạng getter của ví dụ | Không dùng thay cho accessor JavaBeans trong mẫu này |

Tên gần giống nhau về mặt ngôn ngữ không tạo ra ánh xạ tự động. `firstName`, `firstname` và `givenName` là các tên khác nhau.

Khi đặt tên có chữ viết tắt, nên kiểm tra quy tắc JavaBeans. Chẳng hạn, `Introspector.decapitalize("URL")` giữ nguyên `URL`, trong khi `FirstName` trở thành `firstName`. Để giảm bất ngờ, nên thống nhất cách viết property và accessor. Xem [Java Introspector — decapitalize](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html#decapitalize(java.lang.String)).

### 2.2. Tên cột khác với tên thuộc tính domain

Giả sử entity có mapping JPA:

```java
@Column(name = "first_name")
private String firstName;
```

Projection vẫn khai báo:

```java
String getFirstName();
```

Ở đây có ba tên thuộc ba lớp khác nhau:

| Lớp | Tên trong ví dụ |
|---|---|
| Thuộc tính domain | `firstName` |
| Accessor projection | `getFirstName()` |
| Cột database | `first_name` |

Annotation mapping trên entity giúp tầng persistence chuyển property sang tên cột. Không cần đổi getter thành `getFirst_name()` để chạy theo schema database.

Với MongoDB hoặc store có tên field lưu trữ khác tên property Java, nguyên tắc phân biệt hai lớp tên vẫn cần được giữ. Cách khai báo mapping và mức hỗ trợ projection thuộc về module store tương ứng.

### 2.3. Kiểu trả về cần phản ánh dữ liệu

Nếu property là `String firstName`, accessor `String getFirstName()` là lựa chọn trực tiếp. Không nên khai báo `int getFirstName()` rồi dựa vào một phép chuyển đổi ngẫu nhiên để xem tên người là số.

Kiểu không nhất thiết phải giống tuyệt đối trong mọi trường hợp: framework có các cơ chế như nullable wrapper và nested projection. Tuy nhiên, mỗi trường hợp phải có hợp đồng chuyển đổi phù hợp; tên đúng không bảo đảm mọi kiểu trả về đều dùng được.

Với giá trị có thể null, tránh chọn primitive nếu không có quy tắc xử lý null. Trong ví dụ chính, `active` là `boolean` không có trạng thái null nên `isActive()` phù hợp.

## 3. Ví dụ từ entity đến repository

### 3.1. Entity tối thiểu dùng trong ví dụ JPA

Các khai báo dưới đây được trình bày như những kiểu Java riêng. Giả sử chúng nằm trong package mà ứng dụng đã cấu hình quét entity và repository.

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "first_name")
    private String firstName;

    @Column(name = "last_name")
    private String lastName;

    private String email;

    private boolean active;

    protected Customer() {
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }
}
```

Entity có property `email`, nhưng projection `CustomerListItem` không yêu cầu nó. Đây là chủ đích của kiểu dữ liệu dành cho màn hình danh sách.

Trong ví dụ, `Customer` không triển khai `CustomerListItem`. Projection nằm ngoài hệ phân cấp kiểu của entity. Trả một interface mà entity vốn đã triển khai không có cùng ý nghĩa với yêu cầu projection riêng; tài liệu Commons lưu ý trường hợp supertype có thể trả entity được materialize đầy đủ.

### 3.2. Repository sử dụng kiểu projection

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.repository.Repository;

public interface CustomerRepository extends Repository<Customer, Long> {

    List<CustomerListItem>
    findByActiveOrderByLastNameAscFirstNameAscIdAsc(boolean active);

    Optional<CustomerListItem> findProjectedById(Long id);
}
```

Phương thức đầu có hai phần độc lập:

- `findByActive...` và phần `OrderBy...` mô tả điều kiện cùng thứ tự truy vấn.
- `CustomerListItem` mô tả hình dạng mỗi phần tử trả về.

Phương thức thứ hai dùng tên query riêng `findProjectedById`. Khi repository kế thừa các phương thức CRUD, không nên đổi kiểu trả về của phương thức base để kỳ vọng nó tự trở thành projection query. Commons có lưu ý riêng về phương thức override từ repository base; khả năng biến chúng thành query bằng annotation còn phụ thuộc store. Xem [Interface-based Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.interfaces).

`Repository<Customer, Long>` vẫn khai báo domain type là `Customer`. Không đổi domain type thành `CustomerListItem` chỉ vì một truy vấn trả projection.

### 3.3. Đọc kết quả

```java
List<CustomerListItem> items =
        repository.findByActiveOrderByLastNameAscFirstNameAscIdAsc(true);

for (CustomerListItem item : items) {
    System.out.println(
            item.getId() + ": "
            + item.getLastName() + " "
            + item.getFirstName());
}
```

Giả sử dữ liệu có:

| id | firstName | lastName | email | active |
|---|---|---|---|---|
| 11 | An | Nguyễn | an@example.test | true |
| 12 | Bình | Trần | binh@example.test | false |
| 13 | Chi | Lê | chi@example.test | true |

Kết quả chỉ chứa khách hàng 11 và 13 vì điều kiện `active = true`. Thứ tự cụ thể của chuỗi do quy tắc so sánh của database quyết định; phần `id` giúp phân biệt khi các khóa tên bằng nhau.

Trên mỗi phần tử, bên gọi đọc được các accessor đã khai báo. Hình dạng API này không cung cấp `getEmail()`.

## 4. Proxy và dữ liệu đầu vào của projection

Interface không cần một lớp `CustomerListItemImpl` do ứng dụng tự viết cho đường projection chuẩn. Framework tạo proxy tại runtime và xử lý lời gọi accessor dựa trên dữ liệu kết quả.

Có thể hình dung hợp đồng ở mức khái niệm:

```text
Customer có các property được ánh xạ
             |
             v
Query lấy dữ liệu theo kiểu trả về và khả năng store
             |
             v
Proxy triển khai CustomerListItem
             |
             +-- getId()        -> id
             +-- getFirstName() -> firstName
             +-- getLastName()  -> lastName
             +-- isActive()     -> active
```

Không nên suy từ sơ đồ rằng mọi store đều tải một entity hoàn chỉnh rồi mới bọc proxy. Ví dụ, Spring Data JPA thường sử dụng kết quả `Tuple` để tạo interface proxy. Cách lấy dữ liệu thực tế cần xem theo loại query và provider. Xem [Spring Data JPA — Using Projections with JPA](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.jpa).

Đối với người viết repository, điều cần giữ nhất quán là mỗi accessor phải có nguồn giá trị rõ ràng. Interface không phải nơi framework tự đoán tên khác, tự tính công thức hoặc tự tạo property còn thiếu.

### 4.1. Một accessor sai không tự trở thành phép tính

Ví dụ:

```java
public interface BrokenCustomerView {

    String getFirstName();

    String getFullName();
}
```

Nếu `Customer` không có property `fullName`, framework không tự ghép `firstName` với `lastName`.

Đây là một hợp đồng chưa được ánh xạ đúng. Không nên coi việc viết thêm getter là đã khai báo một open projection hợp lệ. Lỗi có thể xuất hiện khi tạo query, xử lý kết quả hoặc gọi accessor, tùy đường thực thi; không dựa vào một kiểu ngoại lệ duy nhất để nhận diện mọi trường hợp.

### 4.2. Metadata không thay thế việc xác minh query

API `ProjectionInformation` mô tả các property đầu vào và cho biết việc cung cấp chúng có đủ để tạo proxy hoạt động hay không. Xem [ProjectionInformation](https://docs.spring.io/spring-data/relational/reference/data-commons/api/java/org/springframework/data/projection/ProjectionInformation.html).

Thông tin projection cần được đặt cạnh metadata của domain và kết quả query. Chỉ nhìn danh sách getter của interface chưa xác minh được rằng database, alias hoặc nguồn object thật sự cung cấp đúng các giá trị đó.

## 5. Thêm hành vi tính toán mà vẫn giữ đầu vào rõ ràng

### 5.1. Default method dựa trên accessor đã có

Có thể tạo nhãn hiển thị từ các giá trị đã khai báo:

```java
public interface CustomerNameView {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        String first = getFirstName() == null ? "" : getFirstName();
        String last = getLastName() == null ? "" : getLastName();

        return (last + " " + first).trim();
    }
}
```

`getDisplayName()` có thân phương thức Java và chỉ sử dụng hai accessor đầu vào. Nó không yêu cầu thêm property lưu trữ `displayName`.

Đối với cách này, tập dữ liệu cần để tính nhãn vẫn là `firstName` và `lastName`. Quy tắc đặt họ trước tên là lựa chọn hiển thị của ví dụ, không phải quy tắc chung cho mọi người dùng.

### 5.2. Phân biệt với @Value

Nếu sử dụng `@Value` cùng SpEL để đọc target hoặc gọi bean, đó là cơ chế open projection. Framework không thể áp dụng cách tối ưu dựa trên tập property đóng như trước, vì biểu thức có thể truy cập thêm dữ liệu. Tài liệu cũng đưa default method như một lựa chọn cho phép tính chỉ dựa trên accessor đã khai báo. Xem [JPA — Open Projections](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html#projections.interfaces.open).

Với bài toán chỉ ghép hai trường tên, default method giữ quan hệ phụ thuộc dữ liệu dễ quan sát. Các phép tính có truy vấn, tác động phụ hoặc cần ngữ cảnh nghiệp vụ phức tạp nên được tổ chức ở nơi phù hợp hơn trong ứng dụng.

## 6. Null và nullable wrapper

Nếu property có thể null, projection có thể dùng `Optional` tại getter:

```java
import java.util.Optional;

public interface CustomerContactView {

    Long getId();

    Optional<String> getEmail();
}
```

Property được đọc vẫn là `email`; không cần sửa entity thành `Optional<String> email` chỉ để có kiểu trả về này. Khi backing value có giá trị, wrapper chứa giá trị đó; khi backing value null, wrapper rỗng. Xem [Commons — Nullable Wrappers](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html#projections.interfaces.nullable-wrappers).

Cần phân biệt hai tầng rỗng:

```java
Optional<CustomerContactView> customer =
        repository.findContactById(id);
```

Giả sử repository đã khai báo query method `findContactById` trả đúng kiểu trên:

| Tình huống | Biểu diễn |
|---|---|
| Không tìm thấy khách hàng | `Optional<CustomerContactView>` bên ngoài rỗng |
| Tìm thấy khách hàng, email null | Projection tồn tại, `getEmail()` rỗng |
| Tìm thấy khách hàng, email có giá trị | Cả projection và email đều có giá trị |

Đây là hai thông tin khác nhau. Một khách hàng không có email không đồng nghĩa với việc không có khách hàng.

Nullable wrapper cũng không nên được dùng để che một getter sai tên. Nếu `getEmai()` yêu cầu property `emai` không tồn tại, phải sửa mapping thay vì diễn giải giá trị thiếu thành “khách hàng chưa nhập email”.

## 7. Nested accessor và alias: hai biên cần chú ý

### 7.1. Lồng projection theo cấu trúc thuộc tính

Giả sử mở rộng mô hình với `Customer.address`, trong đó `Address` có property `city`. Đây là phần mở rộng ngoài entity tối thiểu ở phần 3.

Một hình dạng đọc phù hợp là:

```java
public interface CustomerLocationView {

    String getFirstName();

    AddressView getAddress();

    interface AddressView {
        String getCity();
    }
}
```

Mỗi cấp khớp với property tại cấp đó:

```text
CustomerLocationView.getAddress() -> Customer.address
AddressView.getCity()            -> Address.city
```

Không tự đổi sang `getAddressCity()` nếu domain không có property `addressCity` và query không cung cấp một kết quả được ánh xạ rõ. Quy tắc phân tích đường thuộc tính trong tên derived query không có nghĩa mọi tên getter ghép lại đều tự hoạt động như cùng một đường query.

Nếu `address` có thể null, bên gọi phải xử lý trường hợp không có đối tượng lồng. Đồng thời, một interface lồng nhỏ không bảo đảm dữ liệu liên quan được tải ít tương ứng.

### 7.2. Query khai báo cần các tên đầu ra phù hợp

Với query tự khai báo, cần theo dõi thêm tên của dữ liệu trả về. Ví dụ riêng cho JPA, có thể chọn và đặt alias rõ ràng:

```java
import java.util.List;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Phương thức đặt trong CustomerRepository.
@Query("""
        select c.id as id,
               c.firstName as firstName,
               c.lastName as lastName,
               c.active as active
        from Customer c
        where c.active = :active
        order by c.lastName, c.firstName, c.id
        """)
List<CustomerListItem> findListItems(
        @Param("active") boolean active);
```

Ví dụ dùng Java text block và JPQL. `c.firstName` là property entity; `firstName` sau `as` là tên đầu ra dùng để khớp accessor.

Với native SQL, phải kiểm tra thêm cách database và driver xử lý alias, cùng khả năng chuyển đổi kiểu của phiên bản đang dùng. Tên cột vật lý không tự thay thế mọi yêu cầu ánh xạ của interface.

Đổi alias để có một tên hiển thị khác là thiết kế của query khai báo; nó không thay đổi định nghĩa property trên domain trong derived projection thông thường.

## 8. Projection đóng tạo cơ hội tối ưu, cần kiểm chứng ở store

Khi biết tập property đầu vào, store có thể giới hạn dữ liệu cần lấy. Với ví dụ danh sách, hình dạng truy vấn mong muốn có thể được minh họa như sau:

```sql
-- Minh họa đọc toàn bộ entity:
select id, first_name, last_name, email, active
from customers
where active = ?;

-- Minh họa tập thuộc tính của CustomerListItem:
select id, first_name, last_name, active
from customers
where active = ?;
```

Đây là SQL minh họa mục tiêu, không phải log truy vấn đã chạy và không phải cam kết về số cột mà mọi provider luôn chọn.

Cần xem cả đường truy vấn:

| Trường hợp | Điều cần đánh giá |
|---|---|
| Derived query với property đơn giản | Store có giới hạn trường/cột theo projection không |
| Query khai báo sẵn | Phần `select` và alias có phù hợp không |
| Nested projection | Có join, tải thêm object hoặc phát sinh truy vấn khác không |
| Property không được ánh xạ để truy vấn | Metadata và store có biểu đạt được cách đọc không |
| Trả supertype mà entity đã triển khai | Có đang nhận entity đầy đủ thay vì projection riêng không |
| Nâng phiên bản hoặc đổi store | Hành vi lấy dữ liệu có còn đúng giả định ban đầu không |

Tài liệu JPA lưu ý rằng projection giới hạn việc chọn ở property cấp trên; nested property dẫn tới join có thể làm toàn bộ nested property được chọn. Vì vậy, cần xem SQL và dữ liệu liên quan khi đánh giá projection lồng. Xem [JPA 3.5 — Derived Queries and Projections](https://docs.spring.io/spring-data/data-jpa/reference/3.5/repositories/projections.html#projections.jpa.queries).

Ngoài việc giảm dữ liệu đọc, projection giúp hình dạng trả về phù hợp với nhu cầu của bên gọi. Tuy vậy, nó không thay thế điều kiện tenant, phân quyền hay quy tắc bảo vệ dữ liệu ở tầng truy vấn và service.

## 9. Tình huống thực hành khi đưa vào dự án

Các tình huống dưới đây giúp xác định một projection đang khớp đúng property, thay vì chỉ trông hợp lý trong mã nguồn.

| Tình huống | Điều cần quan sát |
|---|---|
| Truy vấn khách hàng hoạt động | Mỗi phần tử trả đúng `id`, `firstName`, `lastName`, `active` |
| Đổi getter thành `getFirstname()` | Phát hiện khác biệt tên property, không coi là tên tương đương |
| Cột là `first_name`, property là `firstName` | Getter vẫn dùng tên property Java |
| Không có kết quả trong truy vấn danh sách | Nhận danh sách rỗng theo hợp đồng repository |
| Query đơn theo ID không tìm thấy | `Optional` ngoài rỗng |
| Email null trên một khách hàng tồn tại | `Optional` của getter rỗng |
| Default method tạo nhãn | Chỉ phụ thuộc accessor đã công bố và xử lý null đúng quy tắc |
| Query JPQL có alias | Mỗi accessor đọc đúng giá trị từ tên đầu ra tương ứng |
| Bổ sung projection lồng | Kiểm tra cả giá trị null, join và số truy vấn |
| Quan sát truy vấn của store | Xác minh dữ liệu được lấy phù hợp với kỳ vọng tối ưu |

Các kết quả cụ thể phải được kiểm chứng trong ứng dụng đích. Việc Java biên dịch được interface không xác nhận mapping runtime, mức tải dữ liệu hay tính đúng của alias.

Khi cần đổi tên thuộc tính domain, hãy xem projection như một phần của hợp đồng cần cập nhật cùng repository và query khai báo. Một getter cũ còn sót lại có thể khiến luồng đọc thất bại dù entity đã được refactor thành công.

## 10. Tiêu chí của một projection đóng rõ ràng

Một projection đóng tốt bắt đầu từ nhu cầu đọc cụ thể và một bảng ánh xạ ngắn giữa accessor với property domain. Các getter có tên nhất quán, kiểu trả về phù hợp và quy tắc null dễ hiểu.

Ví dụ `CustomerListItem` yêu cầu bốn property phục vụ danh sách; `CustomerContactView` yêu cầu thông tin liên hệ; `CustomerNameView` tạo nhãn từ hai property tên. Mỗi kiểu có phạm vi đọc riêng, giúp repository thể hiện rõ dữ liệu mà bên gọi cần.

Khi triển khai, cần xác định được ba điều: accessor lấy giá trị từ đâu, query trả đúng tập dữ liệu nào và store có tối ưu theo tập thuộc tính đó hay không. Đây là cơ sở để dùng interface projection có chủ đích trong Spring Data Commons.
