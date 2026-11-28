# Kết hợp And, Or và xử lý đường dẫn thuộc tính mơ hồ

Spring Data Neo4j cho phép tạo nhiều truy vấn từ tên phương thức repository. Thay vì viết Cypher cho mọi điều kiện đơn giản, ta có thể đặt tên phương thức theo thuộc tính và toán tử như `findByStatusAndAgeGreaterThanEqual`. Khi điều kiện kết hợp nhiều nhánh `And` và `Or`, hoặc khi entity có những đường dẫn thuộc tính lồng nhau dễ gây nhầm lẫn, cần hiểu cách Spring Data phân tích tên phương thức.

Bài học này giải thích cách nhóm điều kiện, cách thứ tự `And`/`Or` ảnh hưởng đến kết quả và cách dùng dấu gạch dưới để chỉ rõ đường dẫn property. Các ví dụ dùng entity `Person` và `Address`, trong đó `Person` có cả một property tên `addressZipCode` lẫn một relationship `address` dẫn đến `Address.zipCode`.

## 1. Truy vấn suy diễn từ tên phương thức

Trong Spring Data Neo4j, repository có thể khai báo phương thức truy vấn theo tên:

```java
public interface PersonRepository extends Neo4jRepository<Person, String> {
    List<Person> findByStatus(String status);
}
```

Spring Data phân tích phần tên sau tiền tố truy vấn (`findBy`) để xác định property và điều kiện. Từ ví dụ trên, framework tạo truy vấn tìm các node `Person` có property `status` bằng giá trị tham số.

Một số tiền tố thường gặp trong repository của Spring Data gồm `find…By`, `read…By`, `get…By`, `query…By`, `count…By` và `exists…By`. Khả năng cụ thể còn phụ thuộc loại repository và phiên bản Spring Data Neo4j đang dùng. Phần sau tập trung vào predicate sau `By`.

Ví dụ entity tối giản:

```java
@Node("Person")
public class Person {
    @Id
    private String personId;

    private String name;
    private String status;
    private Integer age;
    private Boolean vip;
}
```

Các phương thức có thể biểu diễn điều kiện trên những property này:

```java
List<Person> findByStatus(String status);
List<Person> findByAgeGreaterThan(Integer age);
List<Person> findByVipTrue();
```

Tên phương thức phải khớp với Java property của entity. Nó không dựa trên tên cột quan hệ hoặc cách đặt label trong Cypher.

## 2. Kết hợp điều kiện bằng And

`And` kết hợp các predicate sao cho tất cả điều kiện trong nhóm phải đúng. Ví dụ, tìm người có trạng thái `ACTIVE` và tuổi từ 18 trở lên:

```java
List<Person> findByStatusAndAgeGreaterThanEqual(
    String status,
    Integer minAge
);
```

Về logic, truy vấn tương đương:

```cypher
MATCH (p:Person)
WHERE p.status = $status
  AND p.age >= $minAge
RETURN p
```

Với phương thức trên, tham số được liên kết theo thứ tự xuất hiện của predicate: `status` rồi `minAge`. Tên biến tham số có thể đặt tùy ý, nhưng kiểu và thứ tự phải phù hợp với điều kiện trong tên phương thức.

Có thể kết hợp nhiều `And`:

```java
List<Person> findByStatusAndAgeGreaterThanEqualAndVip(
    String status,
    Integer minAge,
    Boolean vip
);
```

Phương thức này chỉ trả về người đồng thời thỏa cả ba điều kiện: trạng thái bằng giá trị truyền vào, tuổi lớn hơn hoặc bằng ngưỡng và cờ VIP bằng giá trị truyền vào.

## 3. Kết hợp điều kiện bằng Or

`Or` tạo các nhánh điều kiện thay thế nhau. Chỉ cần một nhánh đúng thì bản ghi có thể được trả về.

```java
List<Person> findByStatusOrVip(
    String status,
    Boolean vip
);
```

Ý nghĩa logic:

```cypher
MATCH (p:Person)
WHERE p.status = $status
   OR p.vip = $vip
RETURN p
```

Nếu gọi `findByStatusOrVip("ACTIVE", true)`, kết quả gồm người có `status = "ACTIVE"` hoặc có `vip = true`.

Khi property boolean cần tìm giá trị `true` cố định, có thể dùng keyword `True`:

```java
List<Person> findByStatusOrVipTrue(String status);
```

Phương thức này tương ứng với điều kiện `status = ? OR vip = true`, chỉ có một tham số cho property `status`.

## 4. Kết hợp And và Or trong cùng một tên phương thức

Spring Data phân tích tên truy vấn thành các nhóm `Or`. Bên trong mỗi nhóm `Or`, những predicate nối bằng `And` được kết hợp với nhau. Vì vậy, `And` có độ ưu tiên cao hơn `Or` trong cách phân nhóm của derived query.

Ví dụ:

```java
List<Person> findByStatusAndAgeGreaterThanEqualOrVip(
    String status,
    Integer minAge,
    Boolean vip
);
```

Logic được hiểu là:

\[
(status = ? \; AND \; age \geq ?) \; OR \; (vip = ?)
\]

Tức là một người được chọn nếu người đó vừa có trạng thái phù hợp vừa đủ tuổi, hoặc nếu cờ VIP bằng giá trị truyền vào.

Một ví dụ cụ thể:

```java
personRepository.findByStatusAndAgeGreaterThanEqualOrVip(
    "ACTIVE",
    18,
    true
);
```

Kết quả gồm:

- Người `ACTIVE` và có tuổi từ 18 trở lên; hoặc
- Người có `vip = true`, bất kể trạng thái và tuổi.

Đây là điểm dễ hiểu nhầm. Nếu đọc tên phương thức theo kiểu từ trái sang phải mà không nhóm điều kiện, có thể diễn giải sai thành `status AND (age OR vip)`. Hãy luôn tách tên phương thức thành từng nhánh `Or`, rồi đọc các điều kiện `And` trong từng nhánh.

### Bảng diễn giải nhanh

| Tên phương thức | Cách nhóm logic |
|---|---|
| `findByAAndB` | `A AND B` |
| `findByAOrB` | `A OR B` |
| `findByAAndBOrC` | `(A AND B) OR C` |
| `findByAOrBAndC` | `A OR (B AND C)` |
| `findByAAndBOrCAndD` | `(A AND B) OR (C AND D)` |

Tên `A`, `B`, `C`, `D` trong bảng chỉ đại diện cho các predicate trên property hợp lệ, không phải cú pháp literal của repository.

## 5. Khi cần biểu thức logic phức tạp hơn

Tên phương thức phù hợp với điều kiện rõ ràng và tương đối ngắn. Khi logic có nhiều nhóm lồng nhau, việc đặt tên có thể dài và khó đọc. Ví dụ nghiệp vụ cần biểu diễn:

\[
(status = ACTIVE \; AND \; age \geq 18)
\; OR \;
(status = PENDING \; AND \; vip = true)
\]

Có thể viết derived query:

```java
List<Person> findByStatusAndAgeGreaterThanEqualOrStatusAndVipTrue(
    String activeStatus,
    Integer minAge,
    String pendingStatus
);
```

Các tham số đi theo thứ tự predicate có tham số: `activeStatus`, `minAge`, rồi `pendingStatus`. `VipTrue` là điều kiện cố định nên không cần tham số.

Tuy nhiên, khi tên phương thức trở nên khó đọc hoặc có nhiều nhóm điều kiện, nên chuyển sang `@Query` để thể hiện Cypher tường minh:

```java
@Query("""
    MATCH (p:Person)
    WHERE (p.status = $activeStatus AND p.age >= $minAge)
       OR (p.status = $pendingStatus AND p.vip = true)
    RETURN p
    """)
List<Person> findEligiblePeople(
    @Param("activeStatus") String activeStatus,
    @Param("minAge") Integer minAge,
    @Param("pendingStatus") String pendingStatus
);
```

`@Query` giúp viết dấu ngoặc trực tiếp và làm rõ nhóm logic cho người đọc. Với truy vấn phức tạp, tên phương thức ngắn gọn có thể mô tả mục đích nghiệp vụ, còn Cypher đảm nhiệm chi tiết điều kiện.

## 6. Đường dẫn thuộc tính lồng nhau

Derived query không chỉ truy vấn property trực tiếp trên entity gốc. Nó còn có thể đi theo property path qua các entity được liên kết.

Giả sử `Person` có quan hệ đến một node `Address`:

```java
@Node("Person")
public class Person {
    @Id
    private String personId;

    private String name;

    @Relationship(type = "LIVES_AT", direction = Relationship.Direction.OUTGOING)
    private Address address;

    private String addressZipCode;
}

@Node("Address")
public class Address {
    @Id
    private String addressId;

    private String street;
    private String zipCode;
}
```

Mô hình có hai đường dữ liệu khác nhau:

- `Person.addressZipCode`: property trực tiếp trên node `Person`.
- `Person.address.zipCode`: property `zipCode` của node `Address` nối với `Person` qua relationship `LIVES_AT`.

Nếu khai báo:

```java
List<Person> findByAddressZipCode(String zipCode);
```

Spring Data trước tiên tìm cách khớp toàn bộ phần `AddressZipCode` với property của entity gốc. Vì `Person` có property trực tiếp `addressZipCode`, property này được chọn. Phương thức không tự động có nghĩa là đi qua `address` rồi đến `zipCode`.

Đây là tình huống mơ hồ của property path: cùng một chuỗi tên có thể được hiểu là một property trực tiếp hoặc nhiều property lồng nhau.

## 7. Dùng dấu gạch dưới để phân định property path

Để buộc Spring Data đi qua relationship `address` rồi đến property `zipCode`, dùng dấu gạch dưới `_` làm dấu phân cách:

```java
List<Person> findByAddress_ZipCode(String zipCode);
```

Tên phương thức này thể hiện rõ đường dẫn:

```text
Person.address.zipCode
```

Về ý nghĩa truy vấn, nó tương đương pattern:

```cypher
MATCH (p:Person)-[:LIVES_AT]->(a:Address)
WHERE a.zipCode = $zipCode
RETURN p
```

Trong khi đó, truy vấn property trực tiếp có thể viết rõ bằng:

```java
List<Person> findByAddressZipCode(String zipCode);
```

Hai phương thức khác nhau dù phần tên gần giống nhau:

| Phương thức | Property path được nhắm tới |
|---|---|
| `findByAddressZipCode` | `Person.addressZipCode` |
| `findByAddress_ZipCode` | `Person.address.zipCode` |

Khi entity có nhiều property với tiền tố giống nhau hoặc nhiều tầng quan hệ, nên dùng `_` để làm ranh giới rõ ràng. Cách này cũng giúp người bảo trì hiểu ngay truy vấn đang đi qua relationship nào.

## 8. Cách Spring Data phân giải tên property

Khi phân tích một property path không có dấu phân cách tường minh, Spring Data thường thực hiện theo hướng:

1. Thử khớp toàn bộ tên phần property với một property trên entity hiện tại.
2. Nếu không có, thử tách tên theo ranh giới chữ hoa trong camel case từ bên phải.
3. Tìm property đầu tiên trên entity gốc, sau đó tiếp tục phân giải phần còn lại trên kiểu của property đó.
4. Nếu nhiều cách phân giải có thể xảy ra, cách khớp trực tiếp hoặc cách tách khác có thể khiến đường dẫn không như người viết dự định.

Dấu gạch dưới `_` đánh dấu ranh giới tường minh giữa các phần của property path và giúp loại bỏ sự mơ hồ.

Ví dụ khác, giả sử entity `Order` có property trực tiếp `customerName` và relationship `customer` đến node `Customer` có property `name`:

```java
List<Order> findByCustomerName(String name);
List<Order> findByCustomer_Name(String name);
```

Nếu tồn tại property trực tiếp `customerName`, phương thức đầu có thể nhắm tới property đó. Phương thức thứ hai chỉ rõ đường dẫn `customer.name` qua relationship.

Quy ước nên áp dụng trong dự án:

- Dùng tên property Java chính xác, đúng chữ hoa/chữ thường theo camel case.
- Dùng `_` tại ranh giới mỗi khi truy vấn đi qua property lồng nhau và có khả năng mơ hồ.
- Tránh đặt tên property trực tiếp trùng với cách ghép tên của một đường dẫn lồng nhau nếu không cần thiết.
- Khi method name khó đọc, dùng `@Query` và đặt tên phương thức theo mục đích nghiệp vụ.

## 9. Kết hợp And/Or với property path

Các predicate trên property lồng nhau có thể kết hợp với `And` và `Or` như property trực tiếp.

Ví dụ tìm người ở một mã bưu chính cụ thể và đang hoạt động, hoặc là VIP:

```java
List<Person> findByAddress_ZipCodeAndStatusOrVipTrue(
    String zipCode,
    String status
);
```

Logic được phân nhóm:

\[
(address.zipCode = ? \; AND \; status = ?) \; OR \; (vip = true)
\]

Trong đó `address.zipCode` là property path được chỉ rõ bằng `_`. `And` nối mã bưu chính và trạng thái trong nhánh đầu; `Or` mở nhánh thay thế kiểm tra VIP.

Nếu ý định nghiệp vụ là chỉ tìm người VIP trong cùng mã bưu chính, tức:

\[
address.zipCode = ? \; AND \; (status = ? \; OR \; vip = true)
\]

thì tên phương thức suy diễn không thể biểu đạt trực tiếp dấu ngoặc theo cách đọc tự nhiên như trên. Có thể biến đổi đại số Boolean thành hai nhánh `And` nối bằng `Or` nếu biểu thức tương đương và dễ hiểu, hoặc dùng `@Query` để giữ nguyên dấu ngoặc:

```java
@Query("""
    MATCH (p:Person)-[:LIVES_AT]->(a:Address)
    WHERE a.zipCode = $zipCode
      AND (p.status = $status OR p.vip = true)
    RETURN p
    """)
List<Person> findPeopleForZipCode(
    @Param("zipCode") String zipCode,
    @Param("status") String status
);
```

Không cố tạo method name thật dài để thay thế một biểu thức Cypher cần dấu ngoặc phức tạp. Độ rõ ràng và khả năng kiểm tra logic quan trọng hơn việc tránh viết `@Query`.

## 10. Một số keyword thường dùng trong predicate

Các keyword phổ biến của Spring Data repository query derivation gồm:

| Keyword | Ví dụ | Ý nghĩa |
|---|---|---|
| `Is`, `Equals` | `findByStatusIs` | Bằng giá trị tham số |
| `GreaterThan` | `findByAgeGreaterThan` | Lớn hơn |
| `GreaterThanEqual` | `findByAgeGreaterThanEqual` | Lớn hơn hoặc bằng |
| `LessThan` | `findByAgeLessThan` | Nhỏ hơn |
| `Between` | `findByAgeBetween` | Nằm trong khoảng |
| `In` | `findByStatusIn` | Thuộc một tập giá trị |
| `NotIn` | `findByStatusNotIn` | Không thuộc tập giá trị |
| `Containing` | `findByNameContaining` | Chuỗi có chứa giá trị |
| `StartingWith` | `findByNameStartingWith` | Chuỗi bắt đầu bằng giá trị |
| `EndingWith` | `findByNameEndingWith` | Chuỗi kết thúc bằng giá trị |
| `IsNull` | `findByAddressZipCodeIsNull` | Property không có giá trị |
| `IsNotNull` | `findByAddressZipCodeIsNotNull` | Property có giá trị |
| `True`, `False` | `findByVipTrue` | Boolean bằng true hoặc false |

Danh sách keyword được hỗ trợ và cách chuyển đổi cụ thể phụ thuộc phiên bản Spring Data Neo4j. Khi dùng keyword ít phổ biến, hãy kiểm tra tài liệu phiên bản đang sử dụng và kiểm thử câu truy vấn được tạo ra.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Kết quả có vẻ áp dụng sai điều kiện | Hiểu nhầm cách nhóm `And` và `Or` | Tách tên thành các nhóm `Or`; các `And` nằm trong từng nhóm. |
| Truy vấn đọc property trực tiếp thay vì property lồng nhau | Tên ghép khớp một property trên entity gốc | Dùng `_` để chỉ rõ ranh giới, ví dụ `Address_ZipCode`. |
| Method name quá dài và khó bảo trì | Nhiều nhóm logic và property path | Chuyển sang `@Query` với Cypher có dấu ngoặc rõ ràng. |
| Sai số lượng tham số hoặc thứ tự tham số | Tham số Java không khớp các predicate có tham số | Đối chiếu thứ tự property trong tên phương thức và kiểu dữ liệu. |
| Không tìm thấy property path | Sai tên property hoặc kiểu trung gian không có property tiếp theo | Kiểm tra entity gốc, relationship và entity đích. |
| Query method không hỗ trợ biểu thức mong muốn | Keyword hoặc cấu trúc không được hỗ trợ trong phiên bản hiện tại | Dùng `@Query` hoặc `Neo4jClient` cho Cypher tùy chỉnh. |

## 12. Quy trình thiết kế derived query dễ đọc

1. Xác định điều kiện nghiệp vụ dưới dạng biểu thức logic trước khi đặt tên method.
2. Chia biểu thức thành các nhóm `Or`; xác định những predicate cần nối bằng `And` trong mỗi nhóm.
3. Liệt kê các property được truy vấn và xác định property nào là trực tiếp, property nào đi qua relationship.
4. Dùng `_` cho property path lồng nhau khi có khả năng phân giải mơ hồ.
5. Sắp xếp tham số Java theo thứ tự predicate có tham số trong tên method và chọn kiểu phù hợp.
6. Kiểm thử trường hợp thỏa từng nhánh riêng, trường hợp thỏa nhiều nhánh và trường hợp không thỏa nhánh nào.
7. Chuyển sang `@Query` nếu tên phương thức không còn thể hiện rõ biểu thức nghiệp vụ.

## 13. Ghi nhớ

`And` kết hợp các điều kiện trong cùng một nhóm; `Or` tách thành các nhánh thay thế. Trong derived query, các predicate `And` được nhóm bên trong từng nhánh `Or`, nên cần đọc method name theo cấu trúc logic thay vì chỉ đọc lần lượt các từ.

Với property path, Spring Data cố gắng khớp tên property trực tiếp trước khi tách thành các phần lồng nhau. Khi một tên ghép có thể trỏ đến property trực tiếp hoặc đường dẫn qua relationship, dùng dấu gạch dưới để chỉ rõ ranh giới, ví dụ `findByAddress_ZipCode`. Nếu logic có nhiều nhóm lồng nhau hoặc method name trở nên khó hiểu, `@Query` với Cypher tường minh là lựa chọn dễ kiểm tra và bảo trì hơn.
