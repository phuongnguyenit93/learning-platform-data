# Nhận diện từ khóa không phù hợp hoặc thuộc tính không tồn tại

## Mục tiêu bài học

Spring Data Neo4j (SDN) có thể tạo truy vấn Cypher từ tên phương thức repository. Cách viết này giúp giảm lượng Cypher phải tự khai báo, nhưng tên phương thức phải tuân theo quy tắc phân tích của Spring Data và tham chiếu đúng các property trong domain model Java.

Khi tên phương thức chứa từ khóa không được hỗ trợ hoặc trỏ đến property không tồn tại, Spring Data có thể không tạo được truy vấn. Lỗi thường xuất hiện khi repository được khởi tạo, dưới dạng `QueryCreationException` hoặc lỗi phân tích property như `PropertyReferenceException`. Đây là lỗi cấu hình truy vấn, khác với trường hợp truy vấn hợp lệ nhưng không tìm thấy dữ liệu.

Bài học này hướng dẫn cách đọc tên derived query, kiểm tra property path, phân biệt tên property Java với tên lưu trong Neo4j, đọc thông báo lỗi và quyết định khi nào nên sửa tên phương thức, khi nào nên chuyển sang `@Query`.

## 1. Derived query được phân tích như thế nào?

Một derived query thường có phần mở đầu mô tả thao tác, từ khóa `By`, rồi đến điều kiện dựa trên property:

```java
Optional<Customer> findByEmail(String email);
List<Customer> findByStatusAndAgeGreaterThan(
        String status, int age);
```

Có thể đọc cấu trúc theo cách sau:

- `find` là từ khóa chỉ thao tác truy vấn.
- `By` bắt đầu phần điều kiện.
- `Email`, `Status`, `Age` là tên property của entity.
- `And` kết hợp các điều kiện.
- `GreaterThan` là toán tử so sánh được Spring Data nhận diện.

Spring Data phân tích tên phương thức thành các phần điều kiện (predicate), xác định property path từ domain type và chọn toán tử tương ứng để tạo truy vấn. Vì vậy, một tên phương thức hợp lệ phải thỏa cả hai điều kiện: property path tồn tại trong mô hình persistence và từ khóa toán tử được hỗ trợ bởi phiên bản module đang dùng.

Ví dụ:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String email;

    private String status;

    private int age;

    // Constructor, getter và setter được lược bỏ.
}
```

Các phương thức `findByEmail`, `findByStatus` và `findByAgeGreaterThan` có thể được phân tích dựa trên các property đã khai báo. Nếu phương thức tham chiếu `findByPhoneNumber` trong khi entity không có property `phoneNumber`, Spring Data không thể tạo truy vấn dựa trên mô hình đó.

## 2. Phân biệt từ khóa truy vấn và tên property

Một lỗi dễ gặp là viết một từ có vẻ giống toán tử nhưng Spring Data không nhận diện nó như toán tử trong vị trí đó. Khi không nhận ra hậu tố là keyword, parser có thể xem một phần tên đó như property path. Nếu property tương ứng không tồn tại, lỗi được báo dưới dạng không tìm thấy property.

Ví dụ, entity có property `name`:

```java
public class Customer {

    private String name;

    // ...
}
```

Một phương thức dùng toán tử được hỗ trợ có thể là:

```java
List<Customer> findByNameContaining(String fragment);
```

Nếu viết một hậu tố không được hỗ trợ cho derived query của phiên bản SDN đang dùng, chẳng hạn:

```java
List<Customer> findByNameFuzzy(String value);
```

parser có thể không hiểu `Fuzzy` là toán tử. Nó có thể cố phân giải một property path khác từ phần tên sau `By`, rồi thất bại vì entity không có property tương ứng. Thông báo lỗi cụ thể phụ thuộc cách tên được phân tích và phiên bản Spring Data.

Không nên kết luận mọi lỗi `PropertyReferenceException` đều do gõ sai tên field. Có thể tên property đúng nhưng phần keyword không phù hợp, khiến parser phân chia tên phương thức theo cách khác với ý định.

Một số toán tử thường gặp trong derived queries gồm:

| Ý định | Ví dụ hậu tố hoặc cấu trúc | Ví dụ phương thức |
|---|---|---|
| So khớp bằng | Không cần hậu tố | `findByStatus(String status)` |
| Lớn hơn | `GreaterThan` | `findByAgeGreaterThan(int age)` |
| Nhỏ hơn | `LessThan` | `findByAgeLessThan(int age)` |
| Nằm trong khoảng | `Between` | `findByAgeBetween(int min, int max)` |
| Bắt đầu bằng | `StartingWith` | `findByNameStartingWith(String prefix)` |
| Chứa chuỗi | `Containing` | `findByNameContaining(String part)` |
| Nằm trong tập giá trị | `In` | `findByStatusIn(Collection<String> values)` |
| Kết hợp điều kiện | `And`, `Or` | `findByStatusAndAgeGreaterThan(...)` |
| Kiểm tra null | `IsNull`, `IsNotNull` | `findByEmailIsNotNull()` |

Danh sách trên chỉ là các dạng thường dùng để minh họa, không phải cam kết rằng mọi keyword của mọi module Spring Data đều được SDN hỗ trợ giống nhau. Hãy kiểm tra tài liệu derived query của phiên bản SDN trong dự án trước khi dùng một toán tử đặc biệt. Khi cần chức năng không có trong query derivation, dùng `@Query` để viết Cypher tường minh.

## 3. Property path phải tồn tại trong domain model

Derived query tham chiếu property của entity Java, không trực tiếp tham chiếu tên label hoặc tên property lưu trong Cypher. Spring Data cần lần theo property path từ domain type của repository.

Ví dụ, entity khai báo:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    private String fullName;

    private String email;

    // ...
}
```

Các phương thức sau tham chiếu đúng property:

```java
Optional<Customer> findByFullName(String fullName);

Optional<Customer> findByEmail(String email);
```

Nếu viết `findByFullname`, `findByName` hoặc `findByDisplayName` trong khi các property đó không tồn tại, query derivation có thể thất bại. Java phân biệt chữ hoa và chữ thường trong tên identifier; hãy đối chiếu chính xác tên property trong entity.

Tên label Neo4j không quyết định tên property trong derived query. Ví dụ `@Node("Customer")` khai báo label, còn `fullName` là property Java được truy vấn. Đổi label không có nghĩa phải đổi tên phương thức nếu property Java không thay đổi.

### Property được đổi tên khi lưu trong Neo4j

Có thể dùng `@Property` để ánh xạ một property Java sang tên khác trong graph:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    @Property("full_name")
    private String fullName;

    // ...
}
```

Phương thức derived query vẫn dùng tên property Java:

```java
Optional<Customer> findByFullName(String fullName);
```

Không dùng `findByFull_name` chỉ vì Neo4j lưu property là `full_name`. `@Property("full_name")` điều khiển tên lưu trữ; tên property trong domain model vẫn là `fullName`.

## 4. Kiểm tra property lồng nhau và relationship path

Property path có thể đi qua một property liên kết hoặc cấu trúc domain được SDN ánh xạ. Khi tên phương thức mô tả nhiều cấp, hãy xác nhận từng đoạn của đường dẫn tồn tại và có thể được phân giải từ entity gốc.

Ví dụ, khách hàng có một địa chỉ:

```java
@Node("Customer")
public class Customer {

    @Id
    private String id;

    @Relationship(type = "HAS_ADDRESS")
    private Address address;

    // ...
}

@Node("Address")
public class Address {
    private String city;
    private String postalCode;

    // ...
}
```

Một phương thức có thể diễn tả việc tìm theo thành phố của địa chỉ nếu kiểu dữ liệu và cách ánh xạ đó được SDN hỗ trợ:

```java
List<Customer> findByAddressCity(String city);
```

Tên property lồng nhau đôi khi có thể mơ hồ nếu các entity có property tên gần nhau. Dùng dấu gạch dưới để chỉ rõ ranh giới property path:

```java
List<Customer> findByAddress_City(String city);
```

Dấu gạch dưới ở đây là dấu phân tách đường dẫn trong tên phương thức, không phải tên property trong Neo4j. Chỉ dùng property path lồng nhau khi mô hình và phiên bản SDN hỗ trợ kiểu quan hệ đó; nếu đường đi phức tạp hoặc qua nhiều relationship, custom Cypher thường dễ đọc và dễ kiểm soát hơn.

Với relationship, hãy kiểm tra:

- Trường `@Relationship` có tồn tại trên entity gốc không.
- Kiểu node đích và property cần lọc có đúng không.
- Hướng relationship trong domain mapping có khớp graph không.
- Property cần truy vấn có được ánh xạ và lưu trong domain model không.

Không suy ra tên property path chỉ từ tên relationship type. Ví dụ, relationship type `PLACED` có thể được ánh xạ vào trường Java `orders`; tên trường và tên type là hai khái niệm riêng.

## 5. Nhận diện lỗi khi repository được khởi tạo

Giả sử repository có phương thức sai:

```java
public interface CustomerRepository
        extends Neo4jRepository<Customer, String> {

    Optional<Customer> findByPhoneNumber(String phoneNumber);
}
```

Trong khi `Customer` không có property `phoneNumber`. Spring Data có thể phát hiện lỗi khi khởi tạo repository proxy và báo một chuỗi exception. Những exception thường gặp gồm:

- `QueryCreationException`: Spring Data không thể tạo query cho phương thức repository.
- `PropertyReferenceException`: parser không tìm được property path được tham chiếu.
- Một exception khởi tạo bean như `BeanCreationException` có thể bọc lỗi query bên trong.

Tên exception ngoài cùng có thể khác nhau tùy thời điểm lỗi được phát hiện và phiên bản framework. Hãy đọc phần `Caused by` sâu nhất và tên phương thức được nhắc trong thông báo.

Ví dụ thông báo có thể cho biết không tìm thấy property `phoneNumber` trên kiểu `Customer`. Điều đó gợi ý kiểm tra entity và tên method trước khi kiểm tra kết nối Neo4j.

Một lỗi query derivation thường xuất hiện khi context khởi tạo, trước khi phương thức được gọi trong request. Tuy vậy, thời điểm chính xác có thể phụ thuộc cấu hình khởi tạo repository lazy/eager và đường đi thực thi. Không nên giả định mọi lỗi đều xuất hiện ngay lúc ứng dụng khởi động hoặc chỉ xuất hiện khi truy vấn được gọi.

## 6. Phân biệt lỗi cấu hình với kết quả rỗng

Hai tình huống có cách xử lý hoàn toàn khác nhau:

| Tình huống | Điều xảy ra | Cách kiểm tra |
|---|---|---|
| Property không tồn tại | Không tạo được query từ tên method | Kiểm tra entity và property path |
| Keyword không được hỗ trợ hoặc đặt sai vị trí | Parser không phân tích được predicate theo ý định | Kiểm tra keyword và cú pháp derived query |
| Property tồn tại, query hợp lệ nhưng không có node phù hợp | Repository trả `Optional.empty()` hoặc collection rỗng | Kiểm tra dữ liệu và giá trị tham số |
| Query trả nhiều kết quả nhưng method chỉ cho phép một | Lỗi kích thước kết quả khi thực thi | Kiểm tra cardinality, constraint và kiểu trả về |
| Cypher custom sai cú pháp | Neo4j báo lỗi khi thực thi query | Kiểm tra câu Cypher và thông tin lỗi từ database |

Ví dụ, `findByEmail("nobody@example.com")` là một phương thức hợp lệ nếu property `email` tồn tại. Nếu không có node nào khớp, kết quả là `Optional.empty()`. Đây không phải lỗi property reference.

Ngược lại, `findByPhoneNumber(...)` sẽ không trở thành một truy vấn hợp lệ chỉ vì database hiện không có khách hàng nào có số điện thoại. Nếu entity không khai báo property đó, query derivation không có cơ sở để tạo truy vấn.

## 7. Quy trình sửa lỗi theo từng bước

Khi thấy lỗi query creation hoặc property reference, hãy xử lý theo trình tự sau:

1. **Xác định repository method.** Tìm đúng tên phương thức trong exception, không bắt đầu bằng việc thay đổi kết nối database.
2. **Tách tên method.** Xác định phần mở đầu, vị trí `By`, property predicate, toán tử và các modifier như `OrderBy`, `Top` hoặc `First`.
3. **Đối chiếu domain type.** Kiểm tra repository đang quản lý entity nào và property có thực sự tồn tại trên entity hoặc đường dẫn lồng nhau không.
4. **Đối chiếu tên Java.** Nếu có `@Property`, dùng tên property Java trong method, không dùng tên vật lý trong Neo4j.
5. **Kiểm tra keyword.** Xác nhận toán tử có được SDN phiên bản dự án hỗ trợ và được đặt đúng sau property hay không.
6. **Rút gọn method để cô lập lỗi.** Thử một method đơn giản như `findByEmail`, sau đó thêm từng điều kiện hoặc keyword một.
7. **Chuyển sang `@Query` khi cần.** Nếu điều kiện vượt khả năng query derivation, viết Cypher rõ ràng thay vì tạo method name dài và khó phân tích.

Ví dụ, thay vì một tên method phức tạp khó đọc:

```java
List<Customer> findTop20ByStatusInAndAgeGreaterThanOrderByCreatedAtDesc(
        Collection<String> statuses, int age);
```

có thể viết custom query khi cần thêm điều kiện graph hoặc quy tắc lọc cụ thể:

```java
@Query("MATCH (c:Customer) " +
       "WHERE c.status IN $statuses AND c.age > $age " +
       "RETURN c " +
       "ORDER BY c.createdAt DESC " +
       "LIMIT 20")
List<Customer> findRecentCustomers(
        @Param("statuses") Collection<String> statuses,
        @Param("age") int age);
```

Tên method lúc này thể hiện mục đích nghiệp vụ, còn Cypher thể hiện rõ cách truy vấn. Dù dùng `@Query`, các tham số và kiểu dữ liệu trả về vẫn cần khớp với query và mapping entity.

## 8. Dùng kiểm thử để phát hiện lỗi sớm

Repository nên được kiểm tra ngay trong test khởi tạo application context hoặc slice test dành cho Neo4j. Việc tạo context sẽ giúp phát hiện nhiều lỗi query derivation trước khi triển khai.

Ví dụ:

```java
@DataNeo4jTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void shouldFindCustomerByEmail() {
        // Tạo một Customer có email cụ thể.
        // Lưu qua repository.
        // Gọi findByEmail(email).
        // Xác nhận đúng Customer được trả về.
    }
}
```

Test trên kiểm tra cả khả năng tạo repository lẫn việc thực thi derived query. Nếu method chứa property không tồn tại, lỗi có thể xảy ra khi context được tạo, trước khi test method chạy.

Nên bổ sung một checklist review cho mỗi method:

- Domain type của repository đã xác định đúng.
- Mọi property trong tên method đều tồn tại trong persistent entity model.
- Tên property dùng theo Java domain model, kể cả khi có `@Property`.
- Keyword được SDN phiên bản dự án hỗ trợ.
- Số lượng tham số và kiểu tham số khớp với predicate.
- Kiểu trả về phù hợp với số lượng kết quả dự kiến.
- Nếu truy vấn qua relationship, property path và hướng graph được xác nhận.
- Có test cho trường hợp có kết quả và không có kết quả.

Không nên cố tình thêm một method sai vào production chỉ để xem ứng dụng báo lỗi gì. Có thể dùng một nhánh test riêng hoặc kiểm tra context trong bài thử nghiệm nhỏ, sau đó xóa method sai trước khi merge.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `PropertyReferenceException` | Property path không tồn tại hoặc parser phân tách tên method ngoài ý định | Đối chiếu domain entity và keyword |
| `QueryCreationException` | Spring Data không tạo được truy vấn cho method | Đọc nguyên nhân gốc trong `Caused by` |
| Dùng tên property Neo4j trong method | Nhầm `@Property("full_name")` với tên Java `fullName` | Dùng `findByFullName` |
| Dùng keyword không được hỗ trợ | Giả định mọi toán tử Spring Data đều có ở SDN | Kiểm tra tài liệu phiên bản hoặc viết `@Query` |
| Sai đường dẫn property lồng nhau | Một đoạn trong property path không tồn tại hoặc mơ hồ | Kiểm tra từng cấp và dùng `_` để phân tách khi cần |
| Nhầm relationship type với tên trường Java | Dùng type của cạnh làm property path | Kiểm tra trường `@Relationship` trên entity |
| Nghĩ lỗi property reference là do database rỗng | Nhầm lỗi tạo query với kết quả không tìm thấy | Phân biệt exception khởi tạo với Optional/collection rỗng |
| Dùng derived query cho điều kiện graph phức tạp | Tên method khó đọc và vượt khả năng query derivation | Chuyển sang Cypher tường minh bằng `@Query` |

## 10. Tự kiểm tra

1. Một derived query gồm những phần chính nào?
2. Vì sao `findByFullName` có thể đúng dù Neo4j lưu property thành `full_name`?
3. `PropertyReferenceException` thường cho biết điều gì?
4. `QueryCreationException` khác với một truy vấn hợp lệ trả về `Optional.empty()` như thế nào?
5. Vì sao một hậu tố không được nhận diện có thể khiến parser hiểu nhầm nó là một phần tên property?
6. Dấu gạch dưới trong `findByAddress_City` có tác dụng gì?
7. Khi nào nên dừng việc mở rộng tên method và dùng `@Query`?
8. Vì sao kiểm thử khởi tạo repository giúp phát hiện lỗi derived query sớm?

Hãy tạo một entity `Customer` có `fullName`, `email` và `age`. Viết các method hợp lệ để tìm theo email, tìm tên có chứa chuỗi và lọc theo tuổi. Sau đó thử một method dùng property không tồn tại và một method dùng hậu tố không phù hợp. Quan sát exception lúc khởi tạo repository, sửa từng lỗi và xác nhận trường hợp truy vấn hợp lệ nhưng không có dữ liệu trả về `Optional.empty()` hoặc collection rỗng.

## Tài liệu tham khảo

- [Spring Data Commons — Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j — Repository support](https://docs.spring.io/spring-data/neo4j/reference/repositories.html)
