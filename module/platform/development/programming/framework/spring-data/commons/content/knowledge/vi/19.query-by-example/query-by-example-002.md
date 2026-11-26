# matchingAll, matchingAny và cách kết hợp điều kiện

## 1. Chọn cách nối các điều kiện do probe tạo ra

Trong Query by Example (QBE), probe là một đối tượng domain được điền các giá trị muốn tìm. `ExampleMatcher` mô tả cách diễn giải những giá trị đó, còn `Example` kết hợp probe với matcher để repository thực thi.

Hai factory chính quyết định cách nối các predicate được tạo từ probe:

| Cách tạo matcher | Cách kết hợp | Ý nghĩa |
|---|---|---|
| `ExampleMatcher.matchingAll()` | AND | Bản ghi phải thỏa mọi predicate được đưa vào |
| `ExampleMatcher.matchingAny()` | OR | Bản ghi chỉ cần thỏa ít nhất một predicate được đưa vào |
| `ExampleMatcher.matching()` | Giống matchingAll | Mặc định yêu cầu tất cả predicate khớp |

Điểm cần chú ý là **predicate được đưa vào**, không phải mọi field tồn tại trên class. Field null mặc định bị bỏ qua; field thuộc ignore path cũng bị loại khỏi điều kiện.

Javadoc mô tả cả match mode và mặc định bỏ qua null tại [ExampleMatcher](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/ExampleMatcher.html).

Nếu tập predicate là `P1`, `P2`, `P3`, có thể hình dung:

```text
matchingAll: P1 AND P2 AND P3
matchingAny: P1 OR  P2 OR  P3
```

Các biểu thức trong bài minh họa điều kiện do probe tạo ra. Store có thể thêm các ràng buộc riêng như thông tin kiểu dữ liệu; không suy rằng mọi điều kiện nội bộ của store đều được nối OR.

## 2. Ví dụ cùng một probe nhưng khác kết quả

### 2.1. Domain và repository

Giả sử `Customer` đã được ánh xạ cho store đang dùng và có getter/setter cho các property:

| Property | Kiểu | Giá trị ban đầu khi tạo probe mới |
|---|---|---|
| `id` | `Long` | null |
| `name` | `String` | null |
| `email` | `String` | null |
| `tenantId` | `String` | null |
| `active` | `boolean` | false |

Ví dụ dùng repository đồng bộ của một module hỗ trợ QBE:

```java
import org.springframework.data.repository.Repository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends Repository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Trong hệ thống thực tế, cần đối chiếu việc hỗ trợ QBE và các tùy chọn matcher của đúng module store.

Dữ liệu mẫu:

| id | tenantId | name | email | active |
|---|---|---|---|---|
| 1 | A | An | an@example.test | true |
| 2 | A | An | other@example.test | true |
| 3 | B | Bình | an@example.test | false |
| 4 | A | Chi | chi@example.test | false |
| 5 | B | Dũng | null | true |

Probe dùng để tìm theo hai thuộc tính:

```java
Customer probe = new Customer();
probe.setName("An");
probe.setEmail("an@example.test");
```

Để tập trung vào hai thuộc tính này, các matcher dưới đây bỏ qua `id`, `tenantId` và `active`, đồng thời chọn so khớp chuỗi EXACT.

### 2.2. matchingAll yêu cầu cả hai cùng đúng

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Sort;

ExampleMatcher allMatcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id", "tenantId", "active")
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT);

Example<Customer> allExample =
        Example.of(probe, allMatcher);

Iterable<Customer> allMatches =
        repository.findAll(allExample, Sort.by("id"));
```

Điều kiện logic:

```text
name = "An"
AND email = "an@example.test"
```

Trong dữ liệu mẫu, chỉ khách hàng 1 đáp ứng cả hai điều kiện.

### 2.3. matchingAny chấp nhận một trong hai

```java
ExampleMatcher anyMatcher = ExampleMatcher.matchingAny()
        .withIgnorePaths("id", "tenantId", "active")
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT);

Example<Customer> anyExample =
        Example.of(probe, anyMatcher);

Iterable<Customer> anyMatches =
        repository.findAll(anyExample, Sort.by("id"));
```

Điều kiện logic:

```text
name = "An"
OR email = "an@example.test"
```

Kết quả mong đợi là các khách hàng 1, 2 và 3:

| id | Khớp tên? | Khớp email? | matchingAll | matchingAny |
|---|---|---|---|---|
| 1 | Có | Có | Có | Có |
| 2 | Có | Không | Không | Có |
| 3 | Không | Có | Không | Có |
| 4 | Không | Không | Không | Không |
| 5 | Không | Không | Không | Không |

Các kết quả này giả định cách so sánh chuỗi phù hợp với các giá trị đã trình bày. Chúng là kỳ vọng để thực hành, không phải kết quả chạy trên database của một dự án cụ thể.

## 3. Tập predicate hình thành trước khi được nối

Để hiểu một Example, cần lần lượt xác định:

1. Property nào bị bỏ qua bằng ignore path?
2. Giá trị null nào bị bỏ qua hoặc được đưa vào?
3. Property còn lại được so khớp bằng cách nào?
4. Những predicate đó được nối bằng AND hay OR?

Chỉ nhìn `matchingAll` hoặc `matchingAny` mà chưa biết tập predicate có thể dẫn tới kết luận sai.

### 3.1. Null mặc định là không tham gia điều kiện

Nếu probe chỉ có:

```java
Customer probe = new Customer();
probe.setName("An");
// email vẫn là null.
```

và matcher vẫn bỏ qua `id`, `tenantId`, `active`, điều kiện còn lại là:

```text
name = "An"
```

Cả hai match mode đều trả khách hàng 1 và 2 trong tập mẫu, vì chỉ còn một predicate.

Null ở đây có nghĩa “không đưa property vào tìm kiếm” theo cấu hình mặc định. Nó chưa có nghĩa “tìm bản ghi có email null”.

### 3.2. Include null làm xuất hiện thêm điều kiện

Nếu muốn xét null, có thể chọn:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny()
        .withIgnorePaths("id", "tenantId", "active")
        .withIncludeNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT);
```

Với `name = "An"` và `email = null`, trong cách diễn giải relational của JPA, điều kiện tương đương:

```text
name = "An" OR email IS NULL
```

Kết quả mong đợi trong tập mẫu là 1, 2 và 5.

Nếu đổi sang `matchingAll()`, điều kiện trở thành:

```text
name = "An" AND email IS NULL
```

Không có hàng nào trong tập mẫu thỏa biểu thức này.

Cần kiểm tra cả các property null khác trước khi bật include null. Nếu domain có thêm nhiều field chưa điền và chưa bỏ qua, chúng có thể tạo thêm predicate ngoài ý định.

Cách store diễn giải null có thể khác nhau. Chẳng hạn, tài liệu MongoDB lưu ý include null có thể ảnh hưởng cách so khớp embedded document; không coi một biểu thức SQL minh họa là query chung cho mọi store. Xem [MongoDB — Query by Example](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html#query-by-example).

### 3.3. Ignore path loại bỏ cả property có giá trị

Nếu probe có cả tên và email nhưng matcher khai báo:

```java
.withIgnorePaths("id", "tenantId", "active", "email")
```

email bị loại khỏi tập điều kiện. Điều đó đúng ngay cả khi `probe.getEmail()` khác null.

Ignore path có thể dùng để ngăn các field kỹ thuật hoặc mặc định ngoài ý định tham gia truy vấn. Tuy nhiên, nếu cố ý tìm theo một property, phải bảo đảm nó không nằm trong danh sách bị bỏ qua.

## 4. Primitive mặc định có thể thay đổi hẳn ý nghĩa truy vấn

Trong domain của ví dụ, `active` là `boolean`. Một `new Customer()` có `active = false` dù bên gọi chưa chủ động chọn trạng thái.

Nếu matcher chỉ bỏ qua:

```java
.withIgnorePaths("id", "tenantId")
```

thì `active` vẫn tham gia. Với probe ban đầu có tên và email:

```text
matchingAll:
name = "An"
AND email = "an@example.test"
AND active = false

matchingAny:
name = "An"
OR email = "an@example.test"
OR active = false
```

Đối chiếu tập dữ liệu:

| Cấu hình | Kết quả mong đợi |
|---|---|
| matchingAll, bỏ qua active | 1 |
| matchingAll, giữ active mặc định false | Không có |
| matchingAny, bỏ qua active | 1, 2, 3 |
| matchingAny, giữ active mặc định false | 1, 2, 3, 4 |

Với AND, điều kiện mặc định có thể loại mất kết quả cần tìm. Với OR, nó có thể thêm nhiều kết quả chỉ vì trạng thái false.

Commons lưu ý property primitive luôn được đưa vào trừ khi matcher bỏ qua path. Đây cũng là vấn đề với `int = 0`, `double = 0.0` và các giá trị khởi tạo khác. Xem [Commons — Query by Example](https://docs.spring.io/spring-data/commons/reference/query-by-example.html).

Một mô hình nhập liệu tìm kiếm nên phân biệt được “không chọn điều kiện” với “chọn false” hoặc “chọn số không”. Có thể dùng DTO đầu vào với kiểu boxed như `Boolean`, rồi ánh xạ rõ sang probe và cấu hình ignore path.

Không cần đổi toàn bộ domain chỉ để hỗ trợ một màn hình tìm kiếm. Điều cần thiết là kiểm soát property nào thực sự tham gia Example.

## 5. Match mode khác cách so khớp từng property

`matchingAll` và `matchingAny` quyết định phép nối. `contains`, `startsWith`, `exact`, `ignoreCase` quyết định hình dạng của từng predicate.

Ví dụ:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAny()
        .withIgnorePaths("id", "tenantId", "active")
        .withIgnoreNullValues()
        .withMatcher("name",
                match -> match.contains().ignoreCase())
        .withMatcher("email",
                match -> match.exact().ignoreCase());
```

Với probe chứa `name = "an"` và `email = "an@example.test"`, ý nghĩa mong muốn là:

```text
name chứa "an", không phân biệt hoa thường
OR
email bằng "an@example.test", không phân biệt hoa thường
```

Đổi factory sang `matchingAll()` sẽ yêu cầu cả hai predicate đúng. Nó không đổi `contains` thành `exact`.

Cấu hình ở property path có ưu tiên cao hơn thiết lập mặc định tương ứng của matcher. Ví dụ, một matcher mặc định EXACT vẫn có thể khai báo riêng `name` dùng CONTAINING.

Cần đối chiếu khả năng so khớp chuỗi của store. JPA và MongoDB có thể tạo query khác nhau cho cùng ý định; regex, xử lý ký tự đặc biệt, collation và index không có cùng hành vi ở mọi database.

Ngoài chuỗi, QBE chủ yếu dùng so khớp chính xác cho các kiểu thuộc tính khác theo khả năng được công bố. Không dùng match mode để diễn đạt điều kiện như `age >= 18` hoặc một khoảng thời gian.

### 5.1. Chuỗi rỗng không tự bị loại như null

`name = ""` vẫn là giá trị khác null. Nếu dùng exact matching, nó tạo điều kiện tìm chuỗi rỗng.

Nếu màn hình coi ô nhập rỗng là “không lọc”, hãy chuẩn hóa thành null hoặc bỏ qua property theo chính sách của màn hình trước khi tạo Example. Không dựa vào `matchingAny()` để tự bỏ những ô trống.

## 6. matchingAll và matchingAny không tạo cây điều kiện có ngoặc

QBE phù hợp khi các predicate của Example được nối thống nhất bằng AND hoặc OR. Nó không phải một bộ dựng tùy ý cho những nhóm Boolean lồng nhau.

Giả sử cần:

```text
tenantId = "A"
AND (
    name = "An"
    OR email = "an@example.test"
)
```

Nếu đưa cả ba giá trị vào probe với `matchingAny()`, các predicate từ probe sẽ có ý nghĩa:

```text
tenantId = "A"
OR name = "An"
OR email = "an@example.test"
```

Khách hàng 3 ở tenant B vẫn có thể khớp email. Tất cả khách hàng của tenant A cũng khớp điều kiện tenant mà không cần khớp tên hoặc email.

Nếu dùng `matchingAll()`, biểu thức lại thành:

```text
tenantId = "A"
AND name = "An"
AND email = "an@example.test"
```

Biểu thức này chặt hơn yêu cầu ban đầu. Cả hai mode đều không thể hiện đúng nhóm điều kiện đã nêu.

Các điều kiện bắt buộc như tenant, trạng thái chưa bị xóa hoặc phạm vi được phép truy cập phải được tổ chức thành ràng buộc đúng của đường query. Không đặt chúng vào cùng nhóm OR rồi coi đó là cách giới hạn kết quả.

### 6.1. Chọn cơ chế biểu đạt được đúng nhóm điều kiện

Với JPA, một query khai báo rõ có thể diễn đạt yêu cầu trên:

```java
import java.util.List;

import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

// Phương thức bổ sung trong repository JPA.
@Query("""
        select c
        from Customer c
        where c.tenantId = :tenantId
          and (
              c.name = :name
              or c.email = :email
          )
        order by c.id
        """)
List<Customer> searchWithinTenant(
        @Param("tenantId") String tenantId,
        @Param("name") String name,
        @Param("email") String email);
```

Ví dụ này dùng các tham số tên và email có giá trị; nếu cho phép thiếu từng tham số, cần thiết kế thêm cách xây dựng predicate tương ứng.

Các lựa chọn khác có thể là JPA Specification, Querydsl hoặc Criteria API phù hợp với store. Điểm cần giữ là cây điều kiện có nhóm bắt buộc bên ngoài nhóm lựa chọn.

Tài liệu QBE nêu giới hạn với grouped property constraints. Xem [JPA 3.5 — Query by Example](https://docs.spring.io/spring-data/jpa/reference/3.5/repositories/query-by-example.html).

### 6.2. Nested property path không phải nhóm Boolean

Một path như `address.city` xác định thuộc tính ở bên trong một đối tượng. Nó không có nghĩa tự tạo được nhóm:

```text
(address.city = ... AND address.zipCode = ...) OR ...
```

Việc hỗ trợ path lồng phụ thuộc store và mapping. Cấu hình matcher cho path lồng không loại bỏ giới hạn về nhóm điều kiện. Tài liệu JPA còn nêu giới hạn QBE đối với collection và map; không suy từ một property đơn giản sang mọi cấu trúc quan hệ.

## 7. Xây dựng Example từ dữ liệu tìm kiếm một cách rõ ràng

Ví dụ sau tạo probe mới cho mỗi lần tìm, chuẩn hóa ô trống thành null và yêu cầu có ít nhất một điều kiện tên/email.

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

static Example<Customer> buildNameEmailExample(
        String name,
        String email,
        boolean matchAny) {

    String normalizedName = normalize(name);
    String normalizedEmail = normalize(email);

    if (normalizedName == null && normalizedEmail == null) {
        throw new IllegalArgumentException(
                "At least one search criterion is required");
    }

    Customer probe = new Customer();
    probe.setName(normalizedName);
    probe.setEmail(normalizedEmail);

    ExampleMatcher matcher = matchAny
            ? ExampleMatcher.matchingAny()
            : ExampleMatcher.matchingAll();

    matcher = matcher
            .withIgnorePaths("id", "tenantId", "active")
            .withIgnoreNullValues()
            .withStringMatcher(ExampleMatcher.StringMatcher.EXACT);

    return Example.of(probe, matcher);
}

static String normalize(String value) {
    if (value == null) {
        return null;
    }

    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
}
```

Các hàm trên là ví dụ đặt trong service hoặc lớp xây dựng tiêu chí. Chúng giả định domain chỉ có các property đã liệt kê; nếu domain có thêm giá trị mặc định hoặc field kỹ thuật, phải đánh giá chúng khi tạo Example.

Chính sách từ chối cả hai ô trống là lựa chọn của màn hình. Một màn hình quản trị có thể chủ động cho phép liệt kê toàn bộ, nhưng đó phải là hành vi được quyết định rõ.

Không dùng tên `matchingAny` để suy rằng probe không có predicate sẽ tự trở thành “không khớp bản ghi nào”. Cần biết hành vi store và chủ động xử lý tập tiêu chí rỗng.

Trong ví dụ này, `tenantId` được bỏ qua nên hàm không giới hạn tenant. Chỉ dùng nó cho đường đọc có phạm vi phù hợp. Nếu nghiệp vụ cần ràng buộc tenant kết hợp nhóm OR, hãy dùng cách dựng query ở phần 6.

### 7.1. Giữ lại matcher mới từ các phương thức with...

`ExampleMatcher` bất biến; các phương thức `with...` trả một cấu hình mới.

Cách đúng:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();
matcher = matcher.withIgnorePaths("active");
```

Nếu chỉ gọi:

```java
matcher.withIgnorePaths("active");
```

rồi tiếp tục dùng biến cũ, cấu hình mới đã không được giữ lại.

Có thể tái sử dụng matcher đã cấu hình cho nhiều probe. Với probe là domain object mutable, nên tạo đối tượng riêng cho mỗi yêu cầu và tránh sửa dữ liệu tiêu chí trong lúc chuẩn bị hoặc thực thi query.

## 8. Phép nối không thay đổi hợp đồng thực thi kết quả

Repository có thể dùng cùng Example cho các nhu cầu khác nhau:

```java
Example<Customer> example =
        buildNameEmailExample("An", "an@example.test", true);

boolean found = repository.exists(example);
long total = repository.count(example);

Iterable<Customer> matches =
        repository.findAll(example, Sort.by("id"));
```

`exists`, `count` và `findAll` cùng dựa trên tập điều kiện của Example. Chúng khác cách trả kết quả; chúng không đổi OR thành AND.

`Sort` quy định thứ tự, không bổ sung một điều kiện bắt buộc. Tương tự, phân trang hoặc chọn projection không tự sửa một nhóm Boolean đã mô tả sai.

Nếu dùng `findOne(example)`, hợp đồng yêu cầu tối đa một kết quả. Một `matchingAny` rộng có thể khớp nhiều bản ghi và gây lỗi số lượng kết quả, thay vì chọn ngẫu nhiên một hàng. Xem [QueryByExampleExecutor](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/query/QueryByExampleExecutor.html).

Các lời gọi trên là những query riêng. Nếu dữ liệu thay đổi giữa các lần gọi, không mặc định `exists`, `count` và danh sách quan sát được luôn phản ánh cùng một snapshot.

## 9. Các tình huống thực hành cần quan sát

Có thể dùng tập dữ liệu ở phần 2 để kiểm tra từng thay đổi nhỏ trong cấu hình.

| Tình huống | Kỳ vọng hoặc điều cần quan sát |
|---|---|
| Hai giá trị tên/email, matchingAll, bỏ qua active | Chỉ ID 1 |
| Cùng probe, matchingAny, bỏ qua active | ID 1, 2, 3 |
| Chỉ tên khác null, mặc định bỏ qua null | Hai mode đều dựa trên điều kiện tên |
| Email null được include trong OR | Có thể thêm các hàng email null |
| Email nằm trong ignore path | Không còn predicate email |
| Giữ primitive active mặc định false | Có thêm predicate trạng thái ngoài ý định nếu chưa thiết kế rõ |
| Tên là chuỗi rỗng | Không tự có nghĩa là bỏ lọc |
| Thêm tenant vào matchingAny | Quan sát nguy cơ tenant trở thành một nhánh OR |
| Có path address.city | Phân biệt đường thuộc tính với nhóm Boolean |
| Không còn tiêu chí có hiệu lực | Thực hiện chính sách màn hình, không dựa vào phỏng đoán |
| count và findAll dùng cùng Example | Cùng ý nghĩa predicate, khác hình dạng kết quả |
| Tìm một kết quả nhưng OR khớp nhiều hàng | Xử lý đúng hợp đồng findOne |

Đây là các kỳ vọng thực hành, không phải kết quả kiểm thử đã chạy cho ứng dụng hiện tại. Khi đưa vào dự án, cần xác nhận trên đúng phiên bản Spring Data, loại repository và database đích.

Một cách rà soát hữu ích là viết lại Example thành biểu thức logic trước khi chạy. Nếu biểu thức đó đã khác yêu cầu nghiệp vụ, thay đổi sort, projection hay cách đọc kết quả sẽ không khắc phục được.

## 10. Chọn mode theo ý nghĩa của màn hình tìm kiếm

Dùng `matchingAll` khi các ô đã nhập là những điều kiện phải đồng thời đúng, chẳng hạn tên và email cùng xác định một khách hàng.

Dùng `matchingAny` khi các predicate là những cách thay thế nhau để tìm kết quả, chẳng hạn tên khớp hoặc email khớp. Khi đó, mọi điều kiện tham gia nhóm OR đều phải được chọn có chủ đích.

Trước khi quyết định mode, hãy xác định đầy đủ tập predicate: null, ignore path, giá trị primitive và cách so khớp từng property. Khi cần tổ hợp có ngoặc như `A AND (B OR C)`, chuyển sang cơ chế query biểu đạt được đúng cấu trúc đó.
