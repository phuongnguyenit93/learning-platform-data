# withIncludeNullValues, withIgnoreNullValues và trường cần bỏ qua

Trong Query by Example (QBE), một đối tượng mẫu (*probe*) không chỉ cung cấp giá trị để so khớp. Các thuộc tính đang có giá trị `null`, giá trị mặc định của kiểu nguyên thủy và danh sách đường dẫn bị bỏ qua cũng quyết định truy vấn thực sự tìm những bản ghi nào.

Bài học này trình bày cách phối hợp `ExampleMatcher.withIgnoreNullValues()`, `withIncludeNullValues()` và `withIgnorePaths(...)` trong Spring Data Commons. Mục tiêu là tạo một `Example` thể hiện đúng yêu cầu tìm kiếm, đồng thời nhận biết giới hạn khi chuyển yêu cầu đó cho từng Spring Data store module.

## 1. Ba thành phần quyết định điều kiện QBE

Một truy vấn QBE dựa trên ba thành phần chính:

- **Probe:** đối tượng miền chứa các giá trị mẫu.
- **ExampleMatcher:** quy tắc chọn thuộc tính và cách so khớp.
- **Store module:** thành phần chuyển `Example` thành truy vấn cụ thể, chẳng hạn module dành cho cơ sở dữ liệu quan hệ hoặc tài liệu.

```java
Example<Customer> example = Example.of(probe, matcher);
Iterable<Customer> customers = repository.findAll(example);
```

`Example`, `ExampleMatcher` và `QueryByExampleExecutor` là các abstraction dùng chung trong Spring Data Commons. Commons không tự truy cập cơ sở dữ liệu và không bảo đảm mọi kho dữ liệu triển khai giống nhau.

Với một thuộc tính mà store module hỗ trợ truy vấn bằng QBE, có thể hình dung quá trình chọn điều kiện như sau:

```text
Thuộc tính nằm trong ignoredPaths?
    Có    -> bỏ qua thuộc tính.
    Không -> kiểm tra giá trị của thuộc tính.

Giá trị là null?
    Có    -> IGNORE: không tạo điều kiện cho thuộc tính.
             INCLUDE: đưa yêu cầu khớp null vào Example.
    Không -> dùng giá trị và quy tắc so khớp tương ứng.
```

Bỏ qua thuộc tính khác với yêu cầu thuộc tính phải có giá trị `null`. Nếu `phone` bị bỏ qua, một khách hàng có số điện thoại vẫn có thể khớp. Nếu `phone` tham gia với giá trị `null`, kết quả phải thỏa cách store module diễn giải yêu cầu khớp `null` đó.

## 2. Mô hình dùng trong các ví dụ

Xét một mô hình khách hàng với các thuộc tính sau. Tên trong bảng là tên thuộc tính Java, dùng khi gọi `withIgnorePaths`.

| Thuộc tính | Kiểu Java | Ý nghĩa |
| --- | --- | --- |
| `id` | `Long` | Định danh do kho dữ liệu quản lý |
| `email` | `String` | Email khách hàng |
| `phone` | `String` | Số điện thoại, có thể chưa có |
| `city` | `String` | Thành phố |
| `active` | `Boolean` | Trạng thái hoạt động |
| `loyaltyPoints` | `Integer` | Điểm tích lũy |

Các đoạn mã tiếp theo giả định `Customer` có constructor không tham số, getter và setter tương ứng. Khi triển khai, cần bổ sung mapping theo store đang dùng, ví dụ mapping thực thể cho JPA hoặc tài liệu cho MongoDB. Bài học tập trung vào cấu hình QBE, không quy định một mapping dùng chung cho mọi store.

Repository có thể công bố khả năng QBE qua interface dùng chung:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Interface này chỉ sử dụng được khi repository factory và store module tương ứng hỗ trợ QBE cho mô hình đó. Việc thêm một interface Commons không tự tạo ra khả năng truy vấn mà store chưa triển khai.

Các ví dụ dưới đây sử dụng:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
```

Để dễ quan sát hai thuộc tính `phone` và `city`, một số ví dụ chủ động bỏ qua `id`, `active` và `loyaltyPoints`. Việc bỏ qua này là lựa chọn của từng truy vấn minh họa, không phải quy tắc luôn bỏ qua các thuộc tính ấy trong mọi ứng dụng.

## 3. withIgnoreNullValues: null nghĩa là không thêm bộ lọc

Mặc định, `ExampleMatcher` bỏ qua các giá trị `null`. Gọi `withIgnoreNullValues()` làm ý định này rõ ràng hơn khi đọc mã.

```java
Customer probe = new Customer();
probe.setEmail("lan@example.com");
// phone, city và các thuộc tính tham chiếu khác vẫn là null.

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id", "active", "loyaltyPoints");

Example<Customer> example = Example.of(probe, matcher);
Iterable<Customer> result = repository.findAll(example);
```

Trong mô hình trên, `phone` và `city` không sinh điều kiện. Điều kiện về mặt ý nghĩa chỉ còn:

```text
email khớp "lan@example.com"
```

Ví dụ này không yêu cầu khách hàng phải có `phone` hoặc `city` rỗng. Nó cũng không yêu cầu hai thuộc tính đó phải khác `null`.

Đây là cấu hình phù hợp cho biểu mẫu tìm kiếm có nhiều bộ lọc tùy chọn: người dùng không nhập thành phố thì hệ thống không lọc theo thành phố. Tuy nhiên, cần xử lý riêng trường hợp biểu mẫu chuyển dữ liệu không nhập thành chuỗi rỗng thay vì `null`.

### null, chuỗi rỗng và khoảng trắng là ba giá trị khác nhau

```java
probe.setPhone(null);   // Bị bỏ qua khi IGNORE null.
probe.setPhone("");     // Giá trị không null, có thể tạo điều kiện.
probe.setPhone("   ");  // Vẫn là giá trị không null.
```

`withIgnoreNullValues()` không tự trim chuỗi và không tự đổi chuỗi rỗng thành `null`. Nếu giao diện quy ước chuỗi chỉ chứa khoảng trắng là không có bộ lọc, cần chuẩn hóa ở bước ánh xạ đầu vào:

```java
static String optionalText(String value) {
    if (value == null) {
        return null;
    }
    String normalized = value.trim();
    return normalized.isEmpty() ? null : normalized;
}
```

Chỉ áp dụng phép chuẩn hóa này khi đúng với nghiệp vụ. Nếu người dùng cần tìm chính xác chuỗi rỗng, chuyển chuỗi rỗng thành `null` sẽ làm mất ý định đó.

## 4. withIncludeNullValues: mọi null còn được xét đều có ý nghĩa

`withIncludeNullValues()` thay đổi cách xử lý `null` của matcher sang `INCLUDE`.

```java
Customer probe = new Customer();
probe.setEmail("lan@example.com");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("id", "active", "loyaltyPoints");

Example<Customer> example = Example.of(probe, matcher);
Iterable<Customer> result = repository.findAll(example);
```

Trong mô hình ví dụ, ý nghĩa dự kiến là:

```text
email khớp "lan@example.com"
AND phone khớp null
AND city khớp null
```

Đây là điểm dễ nhầm: `withIncludeNullValues()` không chỉ chọn một thuộc tính `null` mà lập trình viên đang quan tâm. Nó áp dụng chính sách `INCLUDE` cho các giá trị `null` còn được matcher và store module xét tới.

Với JPA và các thuộc tính cơ bản được hỗ trợ, điều kiện khớp `null` thường được biểu diễn bằng `IS NULL`, không phải phép so sánh SQL `= NULL`. Có thể dùng biểu thức sau để giải thích ý nghĩa của ví dụ, nhưng không coi đó là câu SQL chính xác được sinh ra:

```sql
WHERE email = :email
  AND phone IS NULL
  AND city IS NULL
```

### Chỉ tìm phone null nhưng không lọc theo city

Nếu yêu cầu là “tìm email này, số điện thoại chưa có, không quan tâm thành phố”, cần bỏ qua `city`:

```java
Customer probe = new Customer();
probe.setEmail("lan@example.com");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("id", "city", "active", "loyaltyPoints");

Example<Customer> example = Example.of(probe, matcher);
Iterable<Customer> result = repository.findAll(example);
```

Khi đó `phone` vẫn tham gia với `null`, còn `city` không tham gia. Một bản ghi có `city = "Huế"` vẫn có thể khớp nếu thỏa hai điều kiện còn lại.

## 5. withIgnorePaths: loại thuộc tính khỏi Example

`withIgnorePaths(...)` nhận các đường dẫn thuộc tính của đối tượng miền:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id", "phone");
```

Khi một đường dẫn bị bỏ qua, giá trị của nó không trở thành điều kiện, kể cả khi giá trị đó khác `null`:

```java
Customer probe = new Customer();
probe.setEmail("lan@example.com");
probe.setPhone("0900000000");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id", "phone");

Example<Customer> example = Example.of(probe, matcher);
// phone không được dùng để lọc dù probe.phone đang có giá trị.
```

### Tên thuộc tính Java, không phải tên cột

Nếu mapping khai báo thuộc tính Java `phoneNumber` tương ứng với cột `phone_number`, đường dẫn bỏ qua phải là:

```java
.withIgnorePaths("phoneNumber")
```

Không lấy tên cột SQL hoặc tên field đã đổi qua mapping thay cho tên thuộc tính miền. Nếu tên thuộc tính đổi khi refactor, các chuỗi đường dẫn cũng cần được cập nhật. Không dựa vào việc một đường dẫn sai sẽ luôn gây lỗi rõ ràng; cách xử lý có thể phụ thuộc module và đường đi thực thi.

Với thuộc tính lồng nhau, có thể dùng đường dẫn như `address.city` khi store module hỗ trợ cấu trúc đó. Khả năng duyệt quan hệ, truy vấn collection và cách xử lý một đối tượng cha đang `null` không được suy ra chỉ từ cú pháp dấu chấm. Cần kiểm tra theo mapping và store cụ thể.

### Các thuộc tính thường cần cân nhắc bỏ qua

| Nhóm thuộc tính | Rủi ro khi đi vào probe | Cách cân nhắc |
| --- | --- | --- |
| `id` | Thu hẹp tìm kiếm vào một định danh; với INCLUDE có thể yêu cầu id null | Bỏ qua nếu tìm theo tiêu chí nghiệp vụ |
| `version` | Giá trị mặc định hoặc giá trị cũ làm sai phạm vi tìm kiếm | Bỏ qua nếu version không phải bộ lọc |
| Metadata auditing như `createdAt`, `updatedBy` | Sao chép entity làm kéo theo thời gian hoặc người sửa | Chỉ đưa vào khi người dùng thực sự lọc theo chúng |
| Thuộc tính kỹ thuật dạng primitive | `false` hoặc `0` trở thành điều kiện ngoài ý muốn | Bỏ qua hoặc thiết kế probe phù hợp |
| Quan hệ và collection | Khả năng QBE không đồng đều giữa các store | Xác định hỗ trợ và nhu cầu truy vấn trước |
| `tenantId`, quyền truy cập | Bỏ qua có thể mở rộng dữ liệu sang phạm vi khác | Giữ hoặc áp đặt ràng buộc trong cơ chế phù hợp |

Auditing chỉ cung cấp hoặc cập nhật metadata theo cấu hình ứng dụng. Nó không tự biến các thuộc tính đó thành đường dẫn bị bỏ qua trong QBE. Tương tự, QBE không thay thế cơ chế phân quyền hoặc cô lập tenant.

## 6. Bảng đối chiếu ba cấu hình

Với từng thuộc tính được hỗ trợ, có thể đọc cấu hình như sau:

| Giá trị trong probe | Xử lý null | Có trong ignoredPaths? | Ý nghĩa |
| --- | --- | --- | --- |
| `null` | IGNORE | Không | Không tạo điều kiện từ thuộc tính |
| `null` | INCLUDE | Không | Yêu cầu khớp null theo store module |
| `"Huế"` | IGNORE hoặc INCLUDE | Không | So khớp giá trị theo quy tắc tương ứng |
| `null` | IGNORE hoặc INCLUDE | Có | Bỏ qua thuộc tính |
| `"Huế"` | IGNORE hoặc INCLUDE | Có | Bỏ qua thuộc tính |
| `false` kiểu `boolean` | IGNORE hoặc INCLUDE | Không | Giá trị không null, có thể tạo điều kiện false |
| `0` kiểu `int` | IGNORE hoặc INCLUDE | Không | Giá trị không null, có thể tạo điều kiện bằng 0 |

`ignoredPaths` là quyết định loại thuộc tính ra khỏi phép so khớp. Còn xử lý `null` quyết định ý nghĩa của giá trị `null` trong những thuộc tính vẫn được xét.

## 7. Giá trị mặc định của primitive không được coi là null

Một nguồn lỗi phổ biến là dùng các trường primitive trong đối tượng tìm kiếm:

```java
class CustomerProbe {
    private boolean active; // Mặc định false.
    private int loyaltyPoints; // Mặc định 0.
    // Getter/setter lược bỏ.
}
```

Dù không gọi setter, hai giá trị này vẫn tồn tại. `withIgnoreNullValues()` không loại chúng vì chúng không phải `null`.

Ví dụ trên chỉ minh họa hành vi kiểu dữ liệu. `Example` phải dùng kiểu miền mà repository hỗ trợ; không thể mặc nhiên đưa một DTO `CustomerProbe` độc lập vào `CustomerRepository` dành cho `Customer`.

Trong mô hình `Customer` của bài, dùng `Boolean` và `Integer` cho phép biểu diễn “không cung cấp bộ lọc” bằng `null`. Nếu mô hình thực tế dùng primitive và không thể thay đổi, cần bỏ qua đường dẫn khi bộ lọc tương ứng không được yêu cầu:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withIgnorePaths("id", "active", "loyaltyPoints");
```

Chỉ bỏ qua các trường này trong truy vấn không cần lọc chúng. Khi yêu cầu là “khách hàng chưa hoạt động”, `active = false` là điều kiện hợp lệ và phải được giữ lại.

Ngoài primitive, giá trị khởi tạo trong constructor cũng có thể gây điều kiện ngoài ý muốn, chẳng hạn `active = true` hoặc `city = "Hà Nội"`. Probe mới không đồng nghĩa với probe không có giá trị lọc.

## 8. Đầu vào tìm kiếm cần phân biệt ba trạng thái

Một yêu cầu tìm kiếm thường cần biểu diễn ba ý định khác nhau:

| Ý định | Ví dụ với phone | Cách thể hiện |
| --- | --- | --- |
| Không lọc | Lấy cả người có và chưa có số điện thoại | Bỏ qua đường dẫn hoặc dùng null với IGNORE |
| Lọc theo giá trị | Tìm số `0900000000` | Gán giá trị và giữ đường dẫn |
| Tìm giá trị null | Tìm người chưa có số điện thoại | INCLUDE null và giữ đường dẫn |

Một field `String phone` trong DTO, với `null` được dùng đồng thời cho “không truyền” và “tìm null”, không đủ để phân biệt ba ý định. Cần thêm trạng thái ở tầng API hoặc service.

Ví dụ dưới đây mô hình hóa yêu cầu lọc `phone`, đồng thời cho phép lọc `city` khi có giá trị. `null` của `city` trong hàm này được quy ước rõ ràng là không lọc theo thành phố.

```java
enum PhoneMode {
    ANY,
    EQUALS,
    IS_NULL
}
```

```java
static Example<Customer> customerExample(
        PhoneMode phoneMode,
        String phone,
        String city) {

    if (phoneMode == null) {
        throw new IllegalArgumentException("phoneMode là bắt buộc");
    }

    Customer probe = new Customer();
    probe.setCity(city);

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnorePaths("id", "email", "active", "loyaltyPoints");

    if (city == null) {
        matcher = matcher.withIgnorePaths("city");
    }

    switch (phoneMode) {
        case ANY:
            matcher = matcher.withIgnoreNullValues()
                    .withIgnorePaths("phone");
            break;
        case EQUALS:
            if (phone == null) {
                throw new IllegalArgumentException(
                        "phone phải có giá trị khi dùng EQUALS");
            }
            probe.setPhone(phone);
            matcher = matcher.withIgnoreNullValues();
            break;
        case IS_NULL:
            // phone của probe vẫn là null.
            matcher = matcher.withIncludeNullValues();
            break;
        default:
            throw new IllegalArgumentException("PhoneMode không hợp lệ");
    }

    return Example.of(probe, matcher);
}
```

Các lần gọi minh họa:

```java
// Lọc thành phố, không lọc số điện thoại.
Example<Customer> first = customerExample(PhoneMode.ANY, null, "Huế");

// Lọc số điện thoại, không lọc thành phố.
Example<Customer> second = customerExample(
        PhoneMode.EQUALS, "0900000000", null);

// Lọc thành phố và yêu cầu phone null.
Example<Customer> third = customerExample(PhoneMode.IS_NULL, null, "Huế");
```

Ở nhánh `IS_NULL`, các thuộc tính không phục vụ truy vấn được bỏ qua tường minh để tránh `INCLUDE` biến chúng thành điều kiện khớp `null`. Nếu sau này thêm thuộc tính mới vào `Customer`, cần xem lại bộ dựng Example này: danh sách bỏ qua không tự cập nhật theo thay đổi mô hình.

Khi số lượng trường có ba trạng thái tăng lên, cách ghép danh sách bỏ qua có thể trở nên khó bảo trì. Khi đó nên đánh giá cơ chế truy vấn khác mà store hỗ trợ, thay vì cố biểu diễn mọi yêu cầu bằng QBE.

## 9. Matcher trả về cấu hình mới; probe cần được quản lý riêng

Các phương thức cấu hình của `ExampleMatcher` trả về matcher mới. Cần dùng giá trị trả về:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll();

matcher.withIncludeNullValues(); // Không cập nhật biến matcher.

matcher = matcher.withIncludeNullValues(); // Cập nhật đúng.
```

Hai phương thức xử lý `null` thay thế cùng một cấu hình. Lời gọi sau cùng quyết định chính sách của matcher kết quả:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnoreNullValues();
// Matcher kết quả dùng IGNORE null.
```

Không thể diễn giải chuỗi trên là “include null cho phone, ignore null cho city”. `withIgnoreNullValues()` và `withIncludeNullValues()` là cấu hình xử lý `null` ở mức matcher. Để giữ yêu cầu khớp `null` cho một đường dẫn mà không xét đường dẫn khác, cần dùng danh sách bỏ qua thích hợp hoặc một cơ chế truy vấn khác.

Có thể tái sử dụng matcher làm cấu hình nền, nhưng nên tạo probe riêng cho mỗi yêu cầu. Không coi `Example.of(probe, matcher)` là thao tác sao chép sâu probe: nếu tiếp tục sửa đối tượng probe, ý nghĩa truy vấn sử dụng nó có thể thay đổi. Việc dùng chung probe có thể sửa đổi giữa nhiều yêu cầu cũng dễ gây lỗi dữ liệu và lỗi đồng thời.

## 10. matchingAll, matchingAny và ràng buộc phạm vi

Các ví dụ trước dùng `matchingAll()`: các điều kiện tham gia được kết hợp theo ý nghĩa đồng thời thỏa mãn.

Với `matchingAny()`, việc tham gia của một giá trị `null` có thể mở rộng kết quả:

```java
Customer probe = new Customer();
probe.setCity("Huế");

ExampleMatcher matcher = ExampleMatcher.matchingAny()
        .withIncludeNullValues()
        .withIgnorePaths("id", "email", "active", "loyaltyPoints");

Example<Customer> example = Example.of(probe, matcher);
```

Trong mô hình minh họa, hai điều kiện còn lại có ý nghĩa:

```text
city khớp "Huế" OR phone khớp null
```

Khách hàng ở thành phố khác vẫn có thể khớp vì `phone` đang `null`. Thay đổi `matchingAll()` thành `matchingAny()` không phải thao tác làm các bộ lọc trở nên tùy chọn; nó thay đổi cách kết hợp điều kiện.

Nếu ứng dụng cần điều kiện dạng:

```text
 tenantId = tenant hiện tại
 AND (city = "Huế" OR phone khớp null)
```

thì không thể chỉ đưa cả ba giá trị vào `matchingAny()`. Cấu trúc đó có nhóm AND/OR lồng nhau, vượt quá phép kết hợp phẳng của matcher. Cần cơ chế phù hợp với store, chẳng hạn Specification trong bối cảnh JPA hoặc truy vấn được khai báo rõ, đồng thời thực thi ràng buộc quyền truy cập ở tầng thích hợp.

Một trường hợp khác cần kiểm soát là đầu vào không tạo ra điều kiện nào: probe có toàn `null` dưới IGNORE, hoặc mọi đường dẫn đều bị bỏ qua. Không nên mặc định trường hợp này sẽ trả danh sách rỗng. Tùy store và cách triển khai, truy vấn có thể rất rộng. Tầng service nên quy định rõ có cho phép tìm không bộ lọc hay phải từ chối đầu vào đó.

## 11. Hiểu null theo khả năng của từng kho dữ liệu

Cấu hình Commons diễn đạt ý định ở mức abstraction; ý nghĩa lưu trữ cần được kiểm tra theo store.

| Bối cảnh | Điểm cần hiểu |
| --- | --- |
| Store quan hệ, ví dụ Spring Data JPA | Với thuộc tính cơ bản được hỗ trợ, khớp null thường thành điều kiện `IS NULL`; quan hệ và kiểu dữ liệu đặc biệt cần xem riêng |
| Store tài liệu, ví dụ Spring Data MongoDB | Field không tồn tại và field lưu giá trị null là hai trạng thái lưu trữ khác nhau; cần kiểm tra truy vấn QBE được sinh ra và ngữ nghĩa của phép so khớp |
| Đối tượng lồng nhau | Không suy luận rằng cha null sẽ luôn được chuyển thành mọi thuộc tính con null |
| Collection, map hoặc điều kiện trên phần tử | Không giả định QBE hỗ trợ chỉ vì đối tượng miền biểu diễn được cấu trúc đó |
| Store module khác | Xác nhận hỗ trợ QBE và cách xử lý mapping trước khi dựa vào các ví dụ |

Đặc biệt, với dữ liệu tài liệu, không nên tuyên bố `withIncludeNullValues()` luôn phân biệt được “field tồn tại và bằng null” với “field không tồn tại”. Nếu nghiệp vụ cần phân biệt hai trạng thái, có thể phải dùng toán tử hoặc API truy vấn riêng của store.

Tương tự, `withIgnoreNullValues()` không có nghĩa là “chỉ lấy bản ghi mà thuộc tính khác null”. Muốn truy vấn `IS NOT NULL`, kiểm tra field tồn tại, so sánh khoảng hoặc biểu thức phức tạp, cần chọn API đáp ứng đúng yêu cầu. Không gán các ý nghĩa đó cho chính sách bỏ qua `null`.

## 12. Dữ liệu minh họa để tự kiểm tra kết quả

Giả sử các bản ghi sau đã tồn tại và các trường khác đều được bỏ qua trong Example:

| id | email | phone | city |
| --- | --- | --- | --- |
| 1 | `lan@example.com` | `null` | `Huế` |
| 2 | `lan@example.com` | `null` | `null` |
| 3 | `lan@example.com` | `0900000000` | `Huế` |
| 4 | `minh@example.com` | `null` | `Huế` |

Với ngữ nghĩa null thông thường của các thuộc tính cơ bản trong store quan hệ, các cấu hình cho kết quả kỳ vọng như sau:

| Probe và matcher | id kỳ vọng | Giải thích |
| --- | --- | --- |
| email = Lan; IGNORE null; matchingAll | 1, 2, 3 | Chỉ email tham gia |
| email = Lan; INCLUDE null; matchingAll | 2 | Cả phone và city phải null |
| email = Lan; INCLUDE null; bỏ qua city; matchingAll | 1, 2 | Phone phải null, city không tham gia |
| city = Huế; INCLUDE null; bỏ qua email; matchingAll | 1, 4 | City khớp và phone null |
| city = Huế; INCLUDE null; bỏ qua email; matchingAny | 1, 2, 3, 4 | City khớp hoặc phone null |

Trong bảng, “email = Lan” là cách viết gọn cho `email = "lan@example.com"`. Tập id là kỳ vọng về thành viên kết quả, không hàm ý thứ tự trả về. Nếu cần thứ tự ổn định hoặc phân trang, phải yêu cầu sắp xếp và phân trang bằng API repository mà store hỗ trợ; cấu hình null của matcher không cung cấp các khả năng đó.

Khi đưa ví dụ vào ứng dụng, nên quan sát truy vấn thực tế và kết quả trên chính store đang dùng. Đặc biệt kiểm tra dữ liệu có giá trị null, chuỗi rỗng, field bị thiếu và giá trị mặc định primitive để xác nhận yêu cầu nghiệp vụ được giữ nguyên sau mapping.

## 13. Các lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể gặp | Cách sửa |
| --- | --- | --- |
| Bật INCLUDE rồi không có kết quả | Nhiều thuộc tính chưa gán cùng trở thành yêu cầu khớp null, kể cả id | Giữ lại các đường dẫn cần lọc, bỏ qua phần còn lại |
| Không nhập số điện thoại nhưng kết quả bị lọc | Đầu vào là chuỗi rỗng hoặc có khoảng trắng | Chuẩn hóa theo quy ước API trước khi tạo probe |
| IGNORE null nhưng vẫn chỉ thấy active = false | Mô hình dùng primitive boolean hoặc giá trị khởi tạo | Bỏ qua trường khi không có bộ lọc hoặc thiết kế biểu diễn phù hợp |
| Gọi withIncludeNullValues nhưng hành vi không đổi | Không dùng matcher mới được trả về | Gán lại biến hoặc xây dựng chuỗi cấu hình |
| Có bản ghi từ thành phố khác | matchingAny cho phép một điều kiện khác, như phone null, khớp | Dùng matchingAll nếu mọi điều kiện đều bắt buộc |
| Tên đường dẫn bỏ qua không có tác dụng như dự kiến | Dùng tên cột hoặc tên field sau mapping | Dùng tên thuộc tính Java và xác minh đường dẫn |
| Không phân biệt được thiếu field và null | Yêu cầu vượt quá cách QBE của store diễn đạt | Dùng API truy vấn riêng có điều kiện tồn tại field |
| Sau khi thêm thuộc tính, truy vấn INCLUDE trả ít kết quả hơn | Thuộc tính mới có null và chưa bị bỏ qua | Rà lại bộ dựng Example khi thay đổi mô hình |

Khi xây dựng một Example, hãy bắt đầu từ danh sách điều kiện nghiệp vụ cần có: thuộc tính nào không lọc, thuộc tính nào so khớp giá trị và thuộc tính nào phải khớp `null`. Sau đó chọn chính sách null và các đường dẫn bỏ qua để thể hiện danh sách ấy. Cách làm này giúp việc mở rộng repository, sử dụng metadata và chuyển giữa các store không làm thay đổi âm thầm ý nghĩa tìm kiếm.
