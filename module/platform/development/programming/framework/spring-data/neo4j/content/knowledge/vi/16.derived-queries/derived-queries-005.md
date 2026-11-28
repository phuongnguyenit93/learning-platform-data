# IsNull, IsNotNull, True, False, In và NotIn

Spring Data Neo4j cho phép diễn đạt nhiều điều kiện lọc ngay trong tên phương thức repository. Các từ khóa `IsNull`, `IsNotNull`, `True`, `False`, `In` và `NotIn` giúp truy vấn dữ liệu thiếu, giá trị boolean và tập giá trị mà không phải viết Cypher cho từng trường hợp.

Để dùng đúng, cần hiểu cả quy tắc phân tích tên phương thức của Spring Data lẫn ngữ nghĩa của Cypher. Neo4j không lưu property có giá trị `null`; một property không tồn tại được xem là `null` khi so sánh. Vì vậy, kiểm tra null, boolean và membership trong danh sách có một số điểm khác với cách nhiều người quen viết SQL.

## 1. Ví dụ domain và repository

Giả sử ứng dụng quản lý người dùng. Một người có thể chưa cung cấp email, tài khoản có thể bật hoặc tắt, và trạng thái thuộc một tập giá trị xác định.

```java
public enum AccountStatus {
    PENDING,
    ACTIVE,
    SUSPENDED,
    CLOSED
}
```

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String personId;

    private String name;

    private String email;

    private Boolean enabled;

    private AccountStatus status;
}
```

`email` là property tùy chọn; `enabled` dùng `Boolean` để có thể biểu diễn cả `true`, `false` và trường hợp chưa xác định; `status` mô tả trạng thái tài khoản. Repository có thể khai báo các điều kiện sau:

```java
import java.util.Collection;
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    List<Person> findByEmailIsNull();

    List<Person> findByEmailIsNotNull();

    List<Person> findByEnabledTrue();

    List<Person> findByEnabledFalse();

    List<Person> findByStatusIn(Collection<AccountStatus> statuses);

    List<Person> findByStatusNotIn(Collection<AccountStatus> statuses);
}
```

Phần `findBy` xác định phương thức truy vấn. Phần tiếp theo được phân tích theo tên property (`email`, `enabled`, `status`) và từ khóa điều kiện ở cuối. Tên property phải khớp persistent property của entity Java; nếu field dùng `@Property` để ánh xạ sang tên khác trong Neo4j, tên phương thức vẫn dùng tên field Java.

## 2. `IsNull`: tìm node không có property

`IsNull` dùng để tìm những entity mà property tương ứng không có giá trị:

```java
List<Person> findByEmailIsNull();
```

Điều kiện Cypher tương ứng về mặt ngữ nghĩa:

```cypher
MATCH (p:Person)
WHERE p.email IS NULL
RETURN p
```

Trong Neo4j, property mang giá trị `null` không được lưu như một cặp key-value. Nếu property chưa từng được tạo, hoặc đã bị xóa bằng cách gán `null`, biểu thức `p.email IS NULL` sẽ đúng. Vì thế, `IsNull` thường được dùng để tìm hồ sơ chưa cung cấp email, bản ghi chưa được gán mã hoặc dữ liệu chưa hoàn thiện.

Ví dụ node:

```cypher
CREATE (:Person {personId: "P-01", name: "An"})
CREATE (:Person {personId: "P-02", name: "Bình", email: "binh@example.test"})
```

`findByEmailIsNull()` sẽ tìm `P-01` vì node này không có property `email`.

Spring Data cũng hỗ trợ cách viết ngắn `findByEmailNull()`. Tuy nhiên, `IsNull` thường dễ đọc hơn và thể hiện rõ ý định kiểm tra null.

Không dùng phép so sánh `= null` trong Cypher. Hãy dùng `IS NULL`; phép so sánh thông thường với `null` cho kết quả không xác định theo logic ba giá trị của Cypher.

## 3. `IsNotNull`: chỉ lấy node có property

`IsNotNull` là điều kiện ngược lại:

```java
List<Person> findByEmailIsNotNull();
```

Cypher tương ứng:

```cypher
MATCH (p:Person)
WHERE p.email IS NOT NULL
RETURN p
```

Phương thức chỉ trả về node có property `email` và giá trị khác null. Nó phù hợp khi cần tìm tài khoản đã cung cấp email, các node có mã nghiệp vụ hoặc những dữ liệu đã được điền.

Có thể viết ngắn `findByEmailNotNull()`. Cũng như `IsNull`, nên ưu tiên cách viết đầy đủ khi tên phương thức cần dễ hiểu trong code review.

Lưu ý: `IsNotNull` kiểm tra sự tồn tại của property, không kiểm tra email có đúng định dạng hay có thể nhận thư hay không. Kiểm tra định dạng, xác minh email và trạng thái xác thực vẫn là quy tắc nghiệp vụ riêng.

## 4. `True` và `False`: lọc giá trị boolean

Với property boolean, có thể đặt từ khóa ở cuối tên phương thức mà không cần truyền tham số:

```java
List<Person> findByEnabledTrue();

List<Person> findByEnabledFalse();
```

Về ngữ nghĩa, hai phương thức tương ứng với:

```cypher
MATCH (p:Person)
WHERE p.enabled = true
RETURN p
```

```cypher
MATCH (p:Person)
WHERE p.enabled = false
RETURN p
```

Spring Data cũng cho phép cách viết `findByEnabledIsTrue()` và `findByEnabledIsFalse()`. `True`/`False` là từ khóa điều kiện, không phải một tham số boolean cần truyền vào phương thức.

### Phân biệt `False` với `NotTrue`

Với field `Boolean`, có thể tồn tại ba trạng thái:

| Giá trị trong graph | `findByEnabledTrue()` | `findByEnabledFalse()` |
| --- | --- | --- |
| `true` | Có kết quả | Không có kết quả |
| `false` | Không có kết quả | Có kết quả |
| Property không tồn tại | Không có kết quả | Không có kết quả |

`False` chỉ tìm giá trị boolean `false`; nó không có nghĩa là “không phải true” bao gồm cả dữ liệu thiếu. Trong Cypher, phép so sánh với property không tồn tại trả về `null` (unknown), và `WHERE` chỉ giữ những dòng có điều kiện đúng.

Nếu nghiệp vụ cần tìm cả `false` lẫn chưa xác định, hãy biểu diễn rõ điều kiện:

```cypher
MATCH (p:Person)
WHERE p.enabled = false OR p.enabled IS NULL
RETURN p
```

Có thể dùng `@Query` cho điều kiện tổng hợp này, hoặc tách thành các phương thức repository rồi hợp nhất kết quả ở service nếu cách đó phù hợp. Không thay `False` bằng `NotTrue` theo suy đoán về ngữ nghĩa.

Với field primitive `boolean`, Java chỉ có hai giá trị `true` và `false`; không biểu diễn được property thiếu. Dùng `Boolean` khi domain thực sự có trạng thái chưa xác định. Nếu property bắt buộc, nên xác thực khi ghi để tránh dữ liệu thiếu.

## 5. `In`: tìm giá trị thuộc một tập

`In` lọc các entity có property nằm trong collection tham số:

```java
List<Person> findByStatusIn(Collection<AccountStatus> statuses);
```

Gọi phương thức:

```java
List<Person> activeOrPending = repository.findByStatusIn(
    List.of(AccountStatus.ACTIVE, AccountStatus.PENDING)
);
```

Điều kiện Cypher tương ứng:

```cypher
MATCH (p:Person)
WHERE p.status IN $statuses
RETURN p
```

`$statuses` là tham số được bind từ collection; không nối trực tiếp các giá trị vào chuỗi Cypher. Cách này vừa rõ ràng vừa tránh lỗi escaping và rủi ro injection.

`In` phù hợp với các yêu cầu như:

- Tìm tài khoản thuộc một trong các trạng thái được phép.
- Lấy những người có mã nằm trong danh sách được chọn.
- Tìm sản phẩm thuộc một tập SKU do bộ lọc giao diện gửi lên.

Tham số thường dùng là `Collection<T>`, `Iterable<T>` hoặc một kiểu collection phù hợp với phiên bản Spring Data. Kiểu phần tử nên tương thích với kiểu property trong entity để conversion không gây lỗi.

## 6. `NotIn`: loại trừ một tập giá trị

`NotIn` trả về những entity có giá trị property không nằm trong collection:

```java
List<Person> findByStatusNotIn(Collection<AccountStatus> excludedStatuses);
```

Ví dụ:

```java
List<Person> notClosedOrSuspended = repository.findByStatusNotIn(
    List.of(AccountStatus.CLOSED, AccountStatus.SUSPENDED)
);
```

Điều kiện Cypher tương ứng:

```cypher
MATCH (p:Person)
WHERE p.status NOT IN $excludedStatuses
RETURN p
```

`NotIn` hữu ích khi cần loại một số trạng thái khỏi kết quả, chẳng hạn bỏ qua tài khoản đã đóng hoặc bị tạm ngưng. Tuy nhiên, nó không tự bao gồm node không có property `status`. Nếu `p.status` không tồn tại, kết quả `p.status NOT IN $excludedStatuses` là `null`, nên node bị loại khỏi `WHERE`.

Nếu cần lấy cả node chưa có trạng thái, hãy viết rõ:

```cypher
MATCH (p:Person)
WHERE p.status IS NULL
   OR p.status NOT IN $excludedStatuses
RETURN p
```

Trong repository, có thể dùng `@Query` cho trường hợp kết hợp này để thể hiện chính xác quy tắc nghiệp vụ.

## 7. Ngữ nghĩa null trong `In` và `NotIn`

Cypher sử dụng logic ba giá trị: một biểu thức có thể là `true`, `false` hoặc `null` (unknown). Trong mệnh đề `WHERE`, chỉ dòng có giá trị `true` được giữ lại. Vì vậy, giá trị thiếu và phần tử null trong danh sách có thể làm kết quả khác với kỳ vọng nếu chỉ nghĩ theo logic đúng/sai thông thường.

Các trường hợp cần lưu ý:

| Tình huống | `value IN $values` | `value NOT IN $values` |
| --- | --- | --- |
| Giá trị có trong danh sách, danh sách không có null | `true` | `false` |
| Giá trị không có trong danh sách, danh sách không có null | `false` | `true` |
| `value` không tồn tại hoặc là null | `null` | `null` |
| Giá trị không khớp và danh sách có phần tử null | `null` | `null` |

Ví dụ, danh sách `['ACTIVE', null]` không phải là cách biểu diễn “ACTIVE hoặc một giá trị bất kỳ”. Nếu giá trị node không bằng `ACTIVE`, phép `IN` có thể trả về `null` do phần tử null chưa thể so sánh. Trong `WHERE`, kết quả đó không được giữ lại.

Vì vậy:

- Không truyền collection có phần tử null nếu nghiệp vụ không chủ ý xử lý logic unknown.
- Không truyền chính collection là null để thay thế cho danh sách rỗng.
- Kiểm tra và loại bỏ giá trị null ở tầng service trước khi gọi repository.
- Nếu cần bao gồm node thiếu property, thêm nhánh `IS NULL` tường minh.

## 8. Collection rỗng và đầu vào tùy chọn

Collection rỗng có ý nghĩa riêng trong Cypher:

```cypher
"ACTIVE" IN []       // false
"ACTIVE" NOT IN []   // true
```

Vì thế, `findByStatusIn(List.of())` thường không trả về node nào có trạng thái khác null. `findByStatusNotIn(List.of())` có thể trả về mọi node có `status` khác null. Node không có `status` vẫn bị loại vì phép so sánh cho kết quả null.

Đừng mặc định rằng danh sách rỗng có nghĩa là “bỏ qua bộ lọc”. Nếu giao diện không chọn trạng thái và nghiệp vụ muốn trả tất cả kết quả, hãy xử lý rõ ở service:

```java
public List<Person> searchByStatuses(Collection<AccountStatus> statuses) {
    if (statuses == null || statuses.isEmpty()) {
        return personRepository.findAll();
    }
    return personRepository.findByStatusIn(statuses);
}
```

Nếu danh sách rỗng phải có nghĩa “không có trạng thái nào được chấp nhận”, hãy giữ ngữ nghĩa `In` và có thể trả danh sách rỗng sớm để tránh truy vấn không cần thiết. Quyết định phải theo hợp đồng API, không dựa vào cách người dùng suy đoán tên phương thức.

## 9. Kết hợp nhiều từ khóa trong một derived query

Các điều kiện có thể kết hợp bằng `And` và `Or` theo quy tắc đặt tên repository:

```java
List<Person> findByEnabledTrueAndEmailIsNotNull();

List<Person> findByStatusInAndEnabledTrue(Collection<AccountStatus> statuses);

List<Person> findByEmailIsNullOrEnabledFalse();
```

Ví dụ đầu tiên tìm người đang bật tài khoản và đã có email. Ví dụ thứ hai lọc theo danh sách trạng thái đồng thời yêu cầu `enabled = true`. Ví dụ thứ ba lấy người chưa có email hoặc tài khoản bị tắt.

Khi điều kiện trở nên dài, có nhiều nhóm `Or`/`And`, hoặc cần kết hợp null với danh sách theo logic phức tạp, hãy cân nhắc `@Query`. Một câu Cypher tường minh có thể dễ kiểm tra hơn một tên method quá dài và khó đọc.

## 10. Bảng tra cứu từ khóa

| Từ khóa | Ví dụ tên phương thức | Ngữ nghĩa Cypher |
| --- | --- | --- |
| `IsNull` / `Null` | `findByEmailIsNull()` | `email IS NULL` |
| `IsNotNull` / `NotNull` | `findByEmailIsNotNull()` | `email IS NOT NULL` |
| `True` / `IsTrue` | `findByEnabledTrue()` | `enabled = true` |
| `False` / `IsFalse` | `findByEnabledFalse()` | `enabled = false` |
| `In` | `findByStatusIn(statuses)` | `status IN $statuses` |
| `NotIn` | `findByStatusNotIn(statuses)` | `status NOT IN $statuses` |

Tên property trong phương thức là tên Java property. Ví dụ, nếu entity có `@Property("account_status") private AccountStatus status;`, tên method vẫn là `findByStatusIn(...)`, không phải `findByAccount_statusIn(...)`.

## 11. Kiểm thử các trường hợp biên

Khi kiểm thử derived query, đừng chỉ tạo một node khớp điều kiện. Hãy tạo dữ liệu cho từng trường hợp để xác nhận null semantics và collection semantics.

| Dữ liệu kiểm thử | Kỳ vọng |
| --- | --- |
| `email` không tồn tại | Khớp `IsNull`, không khớp `IsNotNull` |
| `email` có chuỗi hợp lệ | Khớp `IsNotNull`, không khớp `IsNull` |
| `enabled = true` | Khớp `True` |
| `enabled = false` | Khớp `False` |
| `enabled` không tồn tại | Không khớp `True` hoặc `False` |
| `status` thuộc danh sách | Khớp `In`, không khớp `NotIn` |
| `status` ngoài danh sách | Không khớp `In`, khớp `NotIn` |
| `status` không tồn tại | Không khớp `In` hoặc `NotIn` |
| Collection đầu vào rỗng | Xác minh đúng hợp đồng API với `In` và `NotIn` |
| Collection có phần tử null | Loại bỏ hoặc kiểm thử logic unknown có chủ đích |

Nếu một derived query trả kết quả khác mong đợi, hãy kiểm tra lần lượt tên property, kiểu tham số, dữ liệu thực tế và ngữ nghĩa Cypher. Có thể viết một câu Cypher tương đương để so sánh với kết quả repository. Với truy vấn quan trọng về hiệu năng, kiểm tra execution plan bằng `EXPLAIN` hoặc `PROFILE` và tạo index cho property lọc thường xuyên khi phù hợp.

## Kết luận

`IsNull` và `IsNotNull` kiểm tra property thiếu hay đang tồn tại; `True` và `False` lọc đúng giá trị boolean tương ứng; `In` và `NotIn` so sánh property với collection tham số. Trong Neo4j, property không tồn tại được xem là null khi so sánh, và Cypher dùng logic ba giá trị, nên `False` không bao gồm null, `NotIn` không tự lấy node thiếu property, còn collection chứa null có thể làm điều kiện thành unknown. Hãy xác định rõ ngữ nghĩa đầu vào rỗng/null, kết hợp từ khóa đúng mục đích và kiểm thử các trường hợp biên để derived query dễ đọc và cho kết quả dự đoán được.
