# Kiểm thử tên phương thức, từ khóa và đường dẫn thuộc tính

## 1. Tên phương thức là một phần của hợp đồng truy vấn

Với derived query, một tên như `findByStatusAndEmailIgnoreCase` mô tả nhiều quyết định cùng lúc: thuộc tính nào được đọc, điều kiện nào được áp dụng, cách kết hợp điều kiện và cách xử lý hoa thường. Một lỗi đánh máy có thể làm repository không khởi tạo được; một tên vẫn hợp lệ nhưng trỏ nhầm thuộc tính có thể trả kết quả sai mà ứng dụng vẫn chạy bình thường.

Trong phạm vi Spring Data Commons, kiểm thử cần phân biệt ba mức:

1. **Parser hiểu gì:** tên phương thức được phân tích thành các phần và đường dẫn thuộc tính nào?
2. **Module có tạo được truy vấn không:** chữ ký, kiểu tham số, mapping và từ khóa có được Spring Data module đang dùng hỗ trợ không?
3. **Store trả kết quả gì:** truy vấn thực thi trên dữ liệu thật có đúng điều kiện, thứ tự và giới hạn không?

Một test mock repository chỉ xác nhận service gọi phương thức mong muốn. Nó không thực thi parser hay query creator của Spring Data, nên không chứng minh tên phương thức tạo truy vấn đúng.

## 2. Tách các thành phần cần kiểm thử

Xét phương thức:

```java
List<Customer> findTop2ByStatusOrderByCreatedAtDescIdAsc(String status);
```

Có thể đọc theo các phần:

```text
find        -> dạng truy vấn tìm kiếm
Top2        -> giới hạn tối đa hai kết quả
By          -> bắt đầu predicate
Status      -> thuộc tính lọc
OrderBy     -> bắt đầu sắp xếp tĩnh
CreatedAtDesc, IdAsc -> thứ tự và tiêu chí phá hòa
```

Không phải mọi chữ trong tên đều là thuộc tính. Ví dụ, phần mô tả trong `findCustomerByEmail` nằm trước `By`; thuộc tính predicate là `email`. Ngược lại, `First` trong phần subject có thể biểu đạt giới hạn, trong khi `FirstName` trong predicate có thể là tên một thuộc tính thực tế.

Các tên khóa Java được suy ra từ mô hình đối tượng miền, không phải từ tên cột SQL hoặc field đã đổi tên trong document. Nếu Java có `emailAddress` nhưng mapping lưu dưới tên `email_address`, derived query vẫn được viết dựa trên `EmailAddress`.

## 3. Những từ khóa cần dữ liệu đối chứng

| Nhóm | Ví dụ | Điều cần kiểm chứng |
| --- | --- | --- |
| So sánh bằng | `findByStatus` | Lọc đúng thuộc tính và giá trị |
| Nối điều kiện | `findByStatusAndEmail` | Cả hai điều kiện cùng đúng |
| Nhánh lựa chọn | `findByStatusOrEmail` | Mỗi nhánh có thể đóng góp kết quả |
| Hoa thường | `findByEmailIgnoreCase` | Giá trị khác cách viết hoa vẫn khớp theo hỗ trợ của store |
| Tìm chuỗi con | `findByEmailContaining` | Khác với bằng, bắt đầu bằng hoặc kết thúc bằng |
| Null | `findByEmailIsNull` | Đúng dữ liệu null; không đồng nhất với chuỗi rỗng |
| Tập giá trị | `findByStatusIn` | Đúng tập lọc và kiểu tham số mà module hỗ trợ |
| Khoảng | `findByCreatedAtBetween` | Đúng hai mốc và semantics biên của query/store |
| Giới hạn và thứ tự | `findTop2ByStatusOrderByCreatedAtDescIdAsc` | Đúng tối đa hai phần tử và thứ tự ổn định |
| Projection đếm/tồn tại | `countByStatus`, `existsByEmail` | Đúng kiểu kết quả và ý nghĩa truy vấn |

Bảng không cam kết tất cả từ khóa hoạt động trên mọi datastore. Parser có thể nhận diện một toán tử nhưng module không hỗ trợ chuyển nó thành truy vấn phù hợp. Các đặc tính như collation, regex, null, mảng hoặc so sánh chuỗi phải được kiểm thử theo store.

Đối với `In`, cần tách trường hợp tập rỗng khỏi tập có phần tử. Đối với tham số null của một phương thức thông thường, không tự suy ra rằng nó có cùng ý nghĩa với từ khóa `IsNull`; hành vi cần được xác định cho API và module đang dùng.

## 4. Đường dẫn thuộc tính: hợp lệ chưa chắc đúng ý định

### 4.1. Thuộc tính trực tiếp có thể che một đường dẫn lồng nhau

Giả sử mô hình có cả hai đường đọc:

```text
Customer.addressZipCode
Customer.address.zipCode
```

Với tên `findByAddressZipCode`, parser ưu tiên thử thuộc tính trực tiếp khớp toàn bộ tên. Khi `addressZipCode` tồn tại, tên đó có thể được phân giải thành thuộc tính trực tiếp, dù người viết đang muốn truy cập `address.zipCode`.

Dùng dấu gạch dưới để chỉ rõ điểm tách:

```java
List<Customer> findByAddress_ZipCode(String zipCode);
```

Hai phương thức có thể đều hợp lệ nhưng mang ý nghĩa khác nhau:

| Tên phương thức | Đường dẫn mong đợi trong mô hình này |
| --- | --- |
| `findByAddressZipCode` | `addressZipCode` |
| `findByAddress_ZipCode` | `address.zipCode` |

Không nên thêm dấu gạch dưới chỉ để trang trí tên. Trong property expression của Spring Data, nó có vai trò phân tách, nên việc đặt tên field theo quy ước Java thông thường giúp giảm nhập nhằng. Những mô hình có field chứa underscore hoặc cách viết hoa đặc biệt cần xem xét và kiểm thử riêng theo quy tắc parser đang dùng.

### 4.2. Phân tách theo camel case cũng có thể đi vào nhánh không mong muốn

Nếu không có thuộc tính trực tiếp khớp đầy đủ, parser thử các điểm tách để tìm thuộc tính lồng nhau. Một thuộc tính như `addressZip` có thể khiến tên `AddressZipCode` được hiểu theo nhánh `addressZip.code` thay vì `address.zipCode`, hoặc làm việc phân giải thất bại nếu nhánh đã chọn không có thuộc tính tiếp theo.

Khi gặp tình huống này, đổi tên có chủ đích hoặc dùng `Address_ZipCode` để thể hiện đường đi rõ ràng. Test nên kiểm tra `toDotPath()` hoặc kết quả truy vấn có dữ liệu đối chứng; chỉ kiểm tra ứng dụng khởi động thành công là chưa đủ.

### 4.3. Thêm field mới cũng có thể đổi cách hiểu một tên cũ

Một method từng đi theo đường lồng nhau có thể chuyển sang thuộc tính trực tiếp sau khi domain model được bổ sung field cùng tên ghép. Đây là dạng hồi quy đáng chú ý: không có lỗi chính tả, method vẫn chạy, nhưng điều kiện đã đổi ý nghĩa.

Vì vậy, khi refactor hoặc mở rộng đối tượng miền, cần xem các method dựa trên property traversal có nhập nhằng và giữ test hành vi cho những truy vấn quan trọng.

## 5. Kiểm thử parser bằng `PartTree`

### 5.1. Mô hình tối thiểu cho test phân tích tên

Test parser không nhất thiết phải dựng Spring context hoặc datastore. Mô hình sau đủ để minh họa đường dẫn và kiểu thuộc tính:

```java
class Customer {
    Long id;
    String email;
    String status;
    Address address;
    String addressZipCode;
    Instant createdAt;
}

class Address {
    String city;
    String zipCode;
}
```

Đây là lớp phục vụ test parser, chưa phải entity đã có mapping lưu trữ. Parser thấy đường dẫn Java không đồng nghĩa module sẽ cho phép truy vấn mọi field đó, đặc biệt khi mapping đánh dấu field không được lưu hoặc không hỗ trợ traversal tương ứng.

### 5.2. Kiểm tra thuộc tính, loại điều kiện và hoa thường

Ví dụ dùng JUnit Jupiter và API parser của Spring Data Commons:

```java
import org.junit.jupiter.api.Test;
import org.springframework.data.repository.query.parser.Part;
import org.springframework.data.repository.query.parser.PartTree;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CustomerMethodParsingTest {

    @Test
    void parsesStatusAndEmailIgnoringCase() {
        PartTree tree = new PartTree(
            "findByStatusAndEmailIgnoreCase",
            Customer.class
        );

        var parts = tree.getParts().toList();

        assertEquals(2, parts.size());
        assertEquals("status", parts.get(0).getProperty().toDotPath());
        assertEquals(Part.Type.SIMPLE_PROPERTY, parts.get(0).getType());
        assertEquals("email", parts.get(1).getProperty().toDotPath());
        assertEquals(
            Part.IgnoreCaseType.ALWAYS,
            parts.get(1).shouldIgnoreCase()
        );
    }
}
```

Test này chứng minh parser chọn đúng hai thuộc tính và nhận diện `IgnoreCase` trên phần email. Nó chưa chứng minh database có collation mong muốn hoặc query creator của module hỗ trợ điều kiện đó cho kiểu dữ liệu cụ thể.

### 5.3. Khóa ý nghĩa của đường dẫn dễ nhập nhằng

Các test sau có thể đặt trong cùng lớp test; những import thông dụng được lược bỏ:

```java
@Test
void distinguishesDirectAndNestedZipCode() {
    PartTree direct = new PartTree(
        "findByAddressZipCode", Customer.class
    );
    PartTree nested = new PartTree(
        "findByAddress_ZipCode", Customer.class
    );

    assertEquals(
        "addressZipCode",
        direct.getParts().toList().get(0).getProperty().toDotPath()
    );
    assertEquals(
        "address.zipCode",
        nested.getParts().toList().get(0).getProperty().toDotPath()
    );
}
```

Đây là assertion về ý định đường dẫn, hữu ích khi mô hình tồn tại cả field trực tiếp và field lồng nhau. Không nên chỉ kiểm tra số lượng part, vì cả hai cách hiểu đều có thể tạo đúng một part.

### 5.4. Kiểm tra nhóm `And` và `Or`

Tên sau biểu đạt hai nhánh OR:

```text
findByStatusAndEmailOrAddress_City

(status = ? AND email = ?) OR address.city = ?
```

Parser chia theo OR, rồi mỗi nhánh chứa các phần AND. Không nên đọc nó thành `status = ? AND (email = ? OR address.city = ?)`.

```java
@Test
void preservesOrGroups() {
    PartTree tree = new PartTree(
        "findByStatusAndEmailOrAddress_City",
        Customer.class
    );

    List<List<String>> groups = new ArrayList<>();

    for (PartTree.OrPart orPart : tree) {
        List<String> properties = new ArrayList<>();
        for (Part part : orPart) {
            properties.add(part.getProperty().toDotPath());
        }
        groups.add(properties);
    }

    assertEquals(
        List.of(
            List.of("status", "email"),
            List.of("address.city")
        ),
        groups
    );
}
```

Nếu nghiệp vụ cần nhóm điều kiện khác, không thêm dấu ngoặc tùy ý vào tên method. Có thể viết lại biểu thức tương đương khi còn dễ đọc, hoặc dùng cơ chế truy vấn tường minh mà module hỗ trợ.

### 5.5. Kiểm tra giới hạn, sắp xếp và lỗi chính tả

```java
@Test
void parsesLimitAndStableSort() {
    PartTree tree = new PartTree(
        "findTop2ByStatusOrderByCreatedAtDescIdAsc",
        Customer.class
    );

    assertTrue(tree.isLimiting());
    assertEquals(Integer.valueOf(2), tree.getMaxResults());
    assertEquals(
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("id")
        ),
        tree.getSort()
    );
}
```

```java
@Test
void rejectsUnknownProperty() {
    assertThrows(
        PropertyReferenceException.class,
        () -> new PartTree("findByEamil", Customer.class)
    );
}
```

Ví dụ dùng thêm `org.springframework.data.domain.Sort`, `org.springframework.data.mapping.PropertyReferenceException` và các assertion JUnit tương ứng. Lỗi viết `Eamil` thay vì `Email` nên bị phát hiện mà không cần chạy datastore.

Không cần cố định toàn bộ nội dung exception message, vì nó có thể chứa gợi ý hoặc chi tiết thay đổi theo phiên bản. Kiểm tra loại lỗi và ý nghĩa quan trọng thường bền hơn việc so sánh nguyên văn thông báo.

## 6. Kiểm thử khởi tạo repository và chữ ký phương thức

`PartTree` nhận chuỗi tên cùng domain class. Nó không tự kiểm tra toàn bộ hợp đồng repository thực tế, như số lượng tham số của Java method, kiểu trả về, query lookup strategy hoặc query creator của module.

Với repository thật, cần kiểm tra:

- Module được chọn đúng và repository gắn với domain mapping đúng.
- Kiểu và số tham số phù hợp toán tử, chẳng hạn `Between` có hai giá trị, `IsNull` không nhận giá trị predicate và `In` cần dạng tham số được module chấp nhận.
- Các tham số đặc biệt như `Pageable` hoặc `Sort` không bị hiểu nhầm là giá trị predicate.
- Từ khóa có được store hỗ trợ trên kiểu thuộc tính đó không.
- Có named query hoặc `@Query` nào khiến method dùng đường truy vấn khác với derived query hay không.

Một test context có thể phát hiện nhiều lỗi tạo query. Tuy nhiên, thời điểm lỗi xuất hiện phụ thuộc cách bootstrap và khởi tạo repository. Với chế độ lazy hoặc cơ chế trì hoãn của module, chỉ dựng context chưa chắc đã tạo mọi query; cần gọi method liên quan để xác nhận đường thực thi.

Nếu đang kiểm tra một repository cố ý khai báo sai để chứng minh startup failure, hãy tách nó khỏi phạm vi scanning thông thường. Không đặt repository sai cạnh các test khác rồi để nó làm hỏng toàn bộ context ngoài ý muốn.

## 7. Kiểm thử hành vi bằng dữ liệu phân biệt được các cách hiểu

### 7.1. Bộ dữ liệu đối chứng

Một fixture tốt khiến truy vấn sai cũng có cơ hội trả dữ liệu, để test phân biệt được sai và đúng. Giả sử có các khách hàng sau; các thời điểm đều ở UTC:

| Nhãn | Email | Status | `address.city` | `address.zipCode` | `addressZipCode` | `createdAt` |
| --- | --- | --- | --- | --- | --- | --- |
| A | `LAN@EXAMPLE.TEST` | ACTIVE | HCM | 70000 | 10000 | 2026-01-01 |
| B | `lan2@example.test` | BLOCKED | HN | 10000 | 70000 | 2026-01-02 |
| C | `minh@example.test` | ACTIVE | HN | 70000 | 99999 | 2026-01-03 |
| D | `other@example.test` | BLOCKED | HCM | 30000 | 30000 | 2026-01-04 |
| E | null | ACTIVE | null | null | 70000 | 2026-01-05 |

Bản ghi E không có address. Không giả định rằng truy vấn nested luôn xử lý address null giống nhau trên mọi module; đó là một trường hợp cần kiểm chứng theo mapping và query thực tế.

Với bộ dữ liệu này:

- Query nested zip `70000` phải phân biệt A, C với B, E có mã trực tiếp `70000`.
- Query equality bỏ qua hoa thường với `lan@example.test` có đối chứng chuỗi dài hơn là `lan2@example.test`.
- Query chuỗi con bỏ qua hoa thường với `lan` có thể phân biệt nó với equality.
- Query có OR phải giữ được D dù D không ACTIVE.
- Query `Top2` theo thời gian giảm dần với ACTIVE có kết quả E rồi C.

### 7.2. Repository minh họa

Đối với một module hỗ trợ các thao tác tương ứng, repository có thể khai báo:

```java
interface CustomerRepository extends CrudRepository<Customer, Long> {

    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findByAddressZipCode(String zipCode);

    List<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByEmailContainingIgnoreCase(String text);

    List<Customer> findByStatusAndEmailOrAddress_City(
        String status, String email, String city
    );

    List<Customer> findTop2ByStatusOrderByCreatedAtDescIdAsc(String status);
}
```

Đoạn interface thể hiện hợp đồng cần kiểm thử; domain class của integration test phải được ánh xạ theo datastore. Với JPA có thể dùng `@Embedded` cho `Address`; với document store, cấu trúc lồng nhau và mapping cần theo module đó. Mô hình trần của test parser ở trên không tự đủ để chạy integration test.

### 7.3. Ví dụ assertion cho đường dẫn và nhóm điều kiện

Giả sử fixture A–E đã được lưu và `repository` là bean thật, có thể dùng JUnit cùng AssertJ:

```java
@Test
void readsNestedZipCodeInsteadOfDirectZipCode() {
    var result = repository.findByAddress_ZipCode("70000");

    assertThat(result)
        .extracting(Customer::getEmail)
        .containsExactlyInAnyOrder(
            "LAN@EXAMPLE.TEST",
            "minh@example.test"
        );
}
```

```java
@Test
void appliesAndInsideEachOrBranch() {
    var result = repository.findByStatusAndEmailOrAddress_City(
        "ACTIVE", "minh@example.test", "HCM"
    );

    assertThat(result)
        .extracting(Customer::getEmail)
        .containsExactlyInAnyOrder(
            "LAN@EXAMPLE.TEST",
            "minh@example.test",
            "other@example.test"
        );
}
```

Dữ liệu D là đối chứng quan trọng. Nếu chỉ có khách hàng ACTIVE trong fixture, cả cách nhóm đúng và cách nhóm sai có thể cùng vượt qua test.

Các ví dụ giả định `Customer` cung cấp getter tương ứng trong mô hình chạy thật. Chúng minh họa phần assertion và cần được đặt trong test harness của module đã chọn, không phải một bộ test tự chạy chỉ từ các đoạn rời.

### 7.4. Kiểm tra `IgnoreCase`, giới hạn và thứ tự

```java
@Test
void matchesEmailWithoutRequiringExactLetterCase() {
    var result = repository.findByEmailIgnoreCase("lan@example.test");

    assertThat(result)
        .extracting(Customer::getEmail)
        .containsExactly("LAN@EXAMPLE.TEST");
}
```

```java
@Test
void returnsNewestTwoActiveCustomersInOrder() {
    var result = repository
        .findTop2ByStatusOrderByCreatedAtDescIdAsc("ACTIVE");

    assertThat(result)
        .extracting(Customer::getEmail)
        .containsExactly(null, "minh@example.test");
}
```

Đối với assertion thứ tự, dùng `containsExactly` thay vì assertion không xét vị trí. Với query không có thứ tự cam kết, kiểm tra tập kết quả theo cách không phụ thuộc thứ tự.

Để kiểm tra tiêu chí `IdAsc` khi thời gian bằng nhau, cần bổ sung ít nhất hai bản ghi có cùng `createdAt` và kiểm tra ID của chúng. Fixture A–E chỉ kiểm tra được phần thời gian giảm dần và giới hạn, chưa đủ để chứng minh tiêu chí phá hòa hoạt động.

Một store có collation mặc định không phân biệt hoa thường có thể làm cả truy vấn không gắn `IgnoreCase` cũng khớp. Khi mục tiêu là chứng minh chính từ khóa thay đổi query generation, cần kết hợp test parser hoặc quan sát truy vấn với cấu hình phù hợp; không ép một kết quả case-sensitive trái với collation đã chọn.

## 8. Cạm bẫy của các phương thức dành riêng như `findById`

Các phương thức có sẵn như `findById`, `existsById` hoặc `deleteById` có hợp đồng làm việc với định danh entity của repository. Không nên coi chúng luôn giống một derived query thông thường dựa trên field tên `id`.

Ví dụ riêng cho JPA, giả sử entity có:

```java
@jakarta.persistence.Id
private Long pk;

private Long id;
```

Repository:

```java
interface CustomerRepository extends CrudRepository<Customer, Long> {
    Optional<Customer> findCustomerById(Long id);
}
```

Ở đây, `findById()` kế thừa từ `CrudRepository` nhắm tới định danh `pk`. Phương thức `findCustomerById()` được khai báo để tạo derived query theo thuộc tính Java `id`.

Fixture phân biệt hai hành vi:

| Entity | `pk` | `id` |
| --- | --- | --- |
| X | 1 | 9 |
| Y | 9 | 1 |

Khi gọi với giá trị 1, test cần xác nhận `findById(1L)` trả X, còn `findCustomerById(1L)` trả Y, theo mapping và hợp đồng repository này.

Chỉ tạo `PartTree("findById", Customer.class)` không mô phỏng toàn bộ việc chọn phương thức dành riêng trong repository. Đây là một lý do cần integration test bên cạnh test parser.

## 9. Chọn môi trường kiểm thử đúng với bảo đảm cần có

| Mức test | Nên chứng minh | Giới hạn |
| --- | --- | --- |
| Unit test service với mock repository | Service gọi đúng phương thức và xử lý kết quả/lỗi | Không kiểm tra parser, mapping hay query thực tế |
| Unit test `PartTree` | Part, property path, nhóm điều kiện, giới hạn và sort | Không xác nhận toàn bộ query creator hoặc semantics của store |
| Test repository với module thật | Repository được tạo và method thực thi đúng trên fixture | Phụ thuộc datastore và cấu hình của môi trường test |
| Test với datastore tương ứng môi trường triển khai | Các khác biệt quan trọng về collation, null, kiểu dữ liệu và query | Cần quản lý vòng đời dữ liệu và tài nguyên |

Với Spring Boot và JPA, một test slice như `@DataJpaTest` có thể cung cấp context phù hợp để kiểm thử repository. Annotation và cấu hình test phải theo phiên bản ứng dụng đang sử dụng. Các module khác có test support riêng; không dùng test slice JPA để kết luận về MongoDB hoặc R2DBC.

Nếu dùng database thay thế trong bộ nhớ, cần hiểu những khác biệt so với database triển khai. Một query vượt qua test không đồng nghĩa collation, xử lý chuỗi rỗng, toán tử hoặc cú pháp của store thật đã được kiểm chứng. Có thể dùng instance test hoặc container phù hợp khi cần xác nhận các khác biệt đó.

### Tránh test chỉ đọc lại đối tượng đã lưu trong bộ nhớ

Trong JPA, persistence context có thể giữ entity đã được lưu. Khi mục tiêu là kiểm chứng mapping và dữ liệu thực sự được ghi, có thể flush và clear ở bước thiết lập phù hợp trước khi chạy query/assertion. Đây là kỹ thuật riêng của JPA, không phải thao tác áp dụng nguyên xi cho mọi repository.

Test transaction có rollback giúp cách ly trong một số cấu hình, nhưng không tự bao phủ mọi tác vụ bất đồng bộ, transaction độc lập hoặc datastore khác. Với reactive repository, assertion phải đăng ký vào publisher và chờ kết quả/lỗi theo test support phù hợp; tạo publisher mà không tiêu thụ chưa chứng minh truy vấn đã chạy.

## 10. Thiết kế test chịu được refactor

Một bộ test hữu ích không cần đóng băng mọi chi tiết nội bộ. Nên ưu tiên:

- Assertion trực tiếp về đường dẫn dễ nhập nhằng hoặc toán tử quan trọng.
- Fixture có bản ghi khớp và bản ghi chỉ khác đúng điều kiện cần phân biệt.
- Assertion về tập kết quả chính xác, cùng thứ tự khi query có cam kết thứ tự.
- Tên test mô tả hành vi, chẳng hạn `readsNestedZipCodeInsteadOfDirectZipCode`.
- Test biên cho null, tập rỗng, chuỗi có ký tự đặc biệt hoặc mốc thời gian khi chúng thuộc hợp đồng.

Không nên chỉ kiểm tra `result` khác null hoặc số lượng lớn hơn 0. Những assertion đó có thể vẫn đúng khi thiếu một predicate, dùng sai đường dẫn hoặc giới hạn sai.

Cũng không nên luôn so sánh nguyên văn SQL sinh ra. Alias và chi tiết query generation có thể thay đổi mà hành vi không đổi. Nếu cần kiểm tra hiệu năng hoặc dạng query, hãy làm thành mục tiêu riêng có bằng chứng phù hợp; test hành vi của tên phương thức vẫn phải xác định kết quả mong đợi.

Khi tên method quá dài, nhiều nhánh hoặc khó tạo dữ liệu đối chứng, đó có thể là dấu hiệu nên dùng truy vấn tường minh hoặc API truy vấn khác mà module hỗ trợ. Việc đổi cách biểu đạt không loại bỏ nhu cầu kiểm thử predicate và đường dẫn thuộc tính.

## 11. Quy trình áp dụng cho một repository method mới

1. Viết ra predicate mong muốn bằng lời hoặc biểu thức có nhóm rõ ràng.
2. Xác định thuộc tính Java, mapping và store thực thi.
3. Chọn tên method, từ khóa và kiểu tham số phù hợp.
4. Dùng test parser nếu có điểm nhập nhằng đáng bảo vệ.
5. Dựng fixture có thể phân biệt truy vấn đúng với những cách hiểu sai dễ xảy ra.
6. Chạy method trên repository thật trong môi trường test của module.
7. Kiểm tra chính xác kết quả, thứ tự, giới hạn và trường hợp biên thuộc hợp đồng.

Ví dụ, với yêu cầu “khách hàng ACTIVE có email chỉ định, hoặc khách hàng ở HCM”, bản ghi BLOCKED ở HCM là đối chứng bắt buộc để phát hiện việc nhóm sai thành `ACTIVE AND (email OR city)`.

Với yêu cầu “mã bưu chính trong địa chỉ”, cần dữ liệu mà mã lồng nhau khác mã trực tiếp. Nếu hai field luôn được fixture điền giống nhau, test không phát hiện được việc query trỏ nhầm field.

## 12. Bài tập vận dụng

Một mô hình có `profile.regionCode` và `profileRegionCode`. Repository khai báo:

```java
List<Customer> findByStatusAndEmailOrProfileRegionCode(
    String status, String email, String regionCode
);
```

Yêu cầu nghiệp vụ là: khách hàng có trạng thái ACTIVE và đồng thời có email chỉ định hoặc thuộc vùng trong `profile`.

Hãy thực hiện các bước phân tích:

1. Viết nhóm điều kiện mà tên method hiện tại thực sự biểu đạt.
2. Xác định `ProfileRegionCode` có thể trỏ vào field trực tiếp nào.
3. Đề xuất cách biểu đạt đúng, dùng phân tách đường dẫn hoặc cơ chế truy vấn khác khi cần.
4. Thiết kế ít nhất một bản ghi BLOCKED thuộc vùng và một bản ghi có hai mã vùng khác nhau để làm đối chứng.
5. Xác định điều gì kiểm tra bằng `PartTree`, điều gì cần repository/store thật.

Đáp án cần chứng minh cả cách nhóm điều kiện và cách chọn đường dẫn. Chỉ sửa tên cho dài hơn hoặc thấy context khởi tạo thành công chưa đủ để xác nhận yêu cầu nghiệp vụ.

## 13. Điểm cần nhớ

Kiểm thử tên phương thức phải xác nhận parser chọn đúng từ khóa, đúng nhóm điều kiện và đúng đường dẫn thuộc tính. Test repository thật bổ sung bằng chứng rằng module tạo được query và datastore trả kết quả đúng trên dữ liệu phân biệt được sai và đúng.

Trong Spring Data Commons, cấu trúc tên được phân tích theo abstraction chung, còn khả năng toán tử, mapping và semantics truy vấn phụ thuộc từng loại kho dữ liệu. Bộ test tốt giữ rõ ranh giới đó và bảo vệ những ý định dễ bị thay đổi khi refactor mô hình miền.
