# Đối tượng mẫu, Example và ExampleMatcher

## 1. Query by Example giải quyết nhu cầu nào?

Một màn hình tìm kiếm thường có nhiều ô tùy chọn: họ khách hàng, thành phố, trạng thái hoạt động. Người dùng có thể nhập một, hai hoặc không nhập ô nào. Nếu mỗi tổ hợp đều cần một tên derived query riêng, repository dễ xuất hiện nhiều phương thức gần giống nhau.

Query by Example, viết tắt là QBE, cho phép mô tả một phần nhu cầu này bằng một đối tượng mẫu và các quy tắc so khớp. Ứng dụng đặt giá trị cần tìm vào đối tượng, tạo Example, rồi giao Example cho repository có hỗ trợ thực thi QBE.

Ba thành phần cốt lõi là:

| Thành phần | Vai trò | Câu hỏi nó trả lời |
| --- | --- | --- |
| Probe, tức đối tượng mẫu | Chứa các giá trị dùng làm đầu vào so khớp | Tìm theo giá trị nào? |
| ExampleMatcher | Quy định cách diễn giải các giá trị và thuộc tính | So khớp như thế nào? |
| Example<T> | Kết hợp probe với matcher thành đầu vào truy vấn | Giao cấu hình tìm kiếm nào cho executor? |

Trong phạm vi **SPRING_DATA_COMMONS**, các abstraction này thuộc hạ tầng chung. Mô-đun kho dữ liệu chịu trách nhiệm chuyển Example thành truy vấn cụ thể. Không mặc định mọi mô-đun hỗ trợ QBE hoặc mọi kiểu so khớp đều có cùng khả năng trên mọi kho dữ liệu.

## 2. Mô hình tư duy của một truy vấn QBE

Có thể hình dung quy trình:

```text
Đầu vào tìm kiếm
    → đặt giá trị vào probe
    → chọn quy tắc bằng ExampleMatcher
    → Example.of(probe, matcher)
    → QueryByExampleExecutor thực thi
    → kết quả theo hợp đồng repository
```

Ví dụ, probe chứa:

```text
lastName = "ng"
city     = "HCM"
active   = true
```

Matcher quy định:

```text
lastName: bắt đầu bằng, không phân biệt hoa thường
city:    so khớp chuỗi chính xác
active:  so khớp giá trị
null:    bỏ qua
kết hợp: tất cả điều kiện phải đúng
```

Ý định truy vấn là:

```text
lastName bắt đầu bằng "ng" theo quy tắc ignoreCase
AND city khớp "HCM"
AND active = true
```

Đây là mô tả logic để hiểu Example, không phải một chuỗi SQL mà Commons luôn sinh ra nguyên văn. Cách diễn đạt bằng SQL, query tài liệu hoặc cơ chế khác do mô-đun và kho dữ liệu quyết định.

## 3. Đối tượng mẫu là domain object chứa giá trị tìm kiếm

Giả sử domain type `Customer` đã được mapping với các thuộc tính và accessor tương ứng:

| Thuộc tính | Kiểu minh họa | Giá trị ban đầu giả định |
| --- | --- | --- |
| `id` | `Long` | `null` |
| `firstName` | `String` | `null` |
| `lastName` | `String` | `null` |
| `city` | `String` | `null` |
| `active` | `Boolean` | `null` |
| `age` | `Integer` | `null` |

Trong ví dụ, kiểu wrapper Boolean và Integer cho phép phân biệt chưa chỉ định điều kiện với những giá trị cụ thể như false hoặc 0.

Tạo probe:

```java
Customer probe = new Customer();
probe.setLastName("ng");
probe.setCity("HCM");
probe.setActive(Boolean.TRUE);
```

Probe là một instance Customer dùng làm mẫu. Tạo probe và đặt giá trị không tự gọi `save`, không tự thêm bản ghi vào database và không tự chạy query.

QBE xét giá trị của các thuộc tính theo matcher. Nó không biết người dùng đã nhập một ô hay giá trị đó do constructor tự khởi tạo, trừ khi ứng dụng chủ động biểu đạt sự khác nhau bằng model và quy tắc bỏ qua.

Không cần tải một Customer có thật từ database để dùng làm probe. Với màn hình tìm kiếm, tạo một instance mới và đặt rõ những thuộc tính được phép tìm thường dễ kiểm soát hơn dùng lại một entity đầy trạng thái.

## 4. Example<T> gắn probe với matcher

Các kiểu chính nằm trong `org.springframework.data.domain`:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

ExampleMatcher matcher = ExampleMatcher.matchingAll();
Example<Customer> example = Example.of(probe, matcher);
```

Có thể dùng matcher mặc định:

```java
Example<Customer> example = Example.of(probe);
```

Khi đó cần hiểu hành vi mặc định thay vì cho rằng mọi giá trị sẽ được diễn giải giống một bộ lọc tùy ý.

Những điểm quan trọng:

- Mặc định bỏ qua thuộc tính có giá trị null.
- Các thuộc tính được xét thường được kết hợp theo yêu cầu tất cả cùng khớp.
- Giá trị khác null, kể cả false, 0 hoặc chuỗi rỗng, không tự có nghĩa là “không chọn điều kiện”.
- Chiến lược chuỗi mặc định và mức hỗ trợ phụ thuộc mô-đun. Nếu cần một kiểu so khớp cụ thể, nên khai báo rõ và xác nhận nó được hỗ trợ.

Example là một mô tả đầu vào; lệnh thực thi nằm ở repository. Việc tạo Example không chứng minh có dữ liệu phù hợp và không xác nhận query đã chạy thành công.

### 4.1. Không coi Example là bản sao sâu của probe

Example giữ tham chiếu tới probe; không nên giả định `Example.of` đã sao chép sâu toàn bộ domain object và đóng băng những giá trị đó.

```java
Example<Customer> example = Example.of(probe, matcher);

// Không nên làm sau khi đã chốt đầu vào truy vấn.
probe.setCity("HN");
```

Việc thay đổi probe có thể làm đầu vào của lần thực thi sau khác với ý định lúc tạo Example. Nên tạo và hoàn thiện probe cho từng yêu cầu, rồi giữ nó ổn định trong quá trình sử dụng Example.

Matcher có thể được tái sử dụng theo hợp đồng bất biến của nó; probe mutable thì không nên được chia sẻ tùy tiện giữa các yêu cầu đồng thời.

## 5. ExampleMatcher quy định cách so khớp

Một matcher cho ví dụ tìm khách hàng:

```java
import org.springframework.data.domain.ExampleMatcher;

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id")
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withMatcher(
                "lastName",
                ExampleMatcher.GenericPropertyMatchers
                        .startsWith()
                        .ignoreCase());
```

Ý nghĩa từng bước:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `matchingAll()` | Các điều kiện được đưa vào phải cùng khớp |
| `withIgnorePaths("id")` | Không dùng id làm điều kiện, dù probe có giá trị id |
| `withIgnoreNullValues()` | Bỏ qua các thuộc tính null |
| `withStringMatcher(EXACT)` | Đặt quy tắc chuỗi chung là so khớp chính xác theo khả năng mô-đun |
| `withMatcher("lastName", ...)` | Tùy chỉnh riêng lastName thành bắt đầu bằng và ignoreCase |

Cấu hình riêng cho thuộc tính có thể ghi đè các tùy chọn tương ứng ở mức chung. Vì vậy city vẫn dùng quy tắc chuỗi chung, còn lastName có cách so khớp riêng.

Tên đường dẫn thuộc tính cần phù hợp domain model. Dùng tên cột SQL hoặc tên field của một DTO tìm kiếm khác chưa chắc là đường dẫn hợp lệ cho probe Customer.

### 5.1. Matcher là bất biến

Các phương thức `with...` trả về matcher mới. Cần giữ lại kết quả:

```java
ExampleMatcher base = ExampleMatcher.matchingAll();

base.withIgnoreCase(); // Matcher mới bị bỏ qua.

ExampleMatcher caseInsensitive = base.withIgnoreCase();
```

Biến base vẫn tham chiếu cấu hình trước đó. Quy tắc này giúp có thể tạo nhiều biến thể từ một matcher chung mà không vô tình sửa matcher đang dùng ở nơi khác.

## 6. Thực thi bằng QueryByExampleExecutor

Nếu implementation repository của mô-đun có hỗ trợ QBE, có thể kết hợp executor vào interface:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Khai báo interface không làm một mô-đun không hỗ trợ QBE tự có implementation. Cần xác nhận khả năng của mô-đun đang dùng.

Ví dụ sử dụng đầy đủ các thành phần:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setLastName("ng");
probe.setCity("HCM");
probe.setActive(Boolean.TRUE);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnorePaths("id")
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withMatcher(
                "lastName",
                ExampleMatcher.GenericPropertyMatchers
                        .startsWith()
                        .ignoreCase());

Example<Customer> example = Example.of(probe, matcher);

Iterable<Customer> customers = repository.findAll(example);

for (Customer customer : customers) {
    System.out.println(customer.getId());
}
```

Theo hợp đồng QueryByExampleExecutor, `findAll(example)` trả Iterable. Một repository cụ thể có thể cung cấp kiểu trả về thuận tiện hơn theo interface của mô-đun, nhưng không nên mặc định mọi executor đều trả List.

## 7. Đối chiếu kết quả bằng một tập dữ liệu nhỏ

Giả sử có các bản ghi:

| id | firstName | lastName | city | active | age |
| --- | --- | --- | --- | --- | --- |
| 101 | An | Nguyễn | HCM | true | 28 |
| 102 | Bình | Nguyễn | HCM | false | 35 |
| 103 | Chi | Ngô | HN | true | 30 |
| 104 | Dũng | Trần | HCM | true | 40 |
| 105 | Lan | Nguyễn | HN | true | 22 |

Với probe và matcher ở trên, ý định là nhận bản ghi 101:

- 101 khớp tiền tố họ, thành phố và active.
- 102 không khớp active.
- 103 và 105 không khớp city.
- 104 không khớp tiền tố lastName.

Ví dụ giả định mô-đun thực hiện được so khớp bắt đầu bằng và ignoreCase theo yêu cầu. Quy tắc collation và xử lý chuỗi thực tế vẫn cần được kiểm tra với kho dữ liệu đang dùng.

`ignoreCase` không đồng nghĩa bỏ dấu tiếng Việt hoặc chuẩn hóa mọi dạng Unicode. Không suy ra rằng tìm `nguyen` sẽ tự khớp `Nguyễn` chỉ vì đã bật ignoreCase.

## 8. Null, chuỗi rỗng và giá trị mặc định khác nhau

### 8.1. Null mặc định được bỏ qua

Trong probe chính, firstName và age null nên không trở thành điều kiện theo matcher đã chọn. Chúng không được hiểu là yêu cầu `firstName IS NULL` hoặc `age IS NULL`.

Đây là cách thuận tiện để biểu đạt ô tìm kiếm không được chọn, miễn là domain object không tự tạo thêm giá trị mặc định ngoài ý muốn.

### 8.2. Chuỗi rỗng không tự được bỏ qua

```java
probe.setCity("");
```

Đây là một giá trị khác null. Với matcher EXACT, ý định so khớp có thể trở thành tìm city rỗng theo cách mô-đun diễn giải, chứ không phải bỏ điều kiện thành phố.

Vì vậy đầu vào form nên có bước quyết định rõ ràng: chuỗi trắng được bỏ qua, được giữ nguyên hay được coi là không hợp lệ.

Ví dụ chuẩn hóa trước khi đặt vào probe:

```java
String normalizedCity = cityInput == null ? null : cityInput.trim();

if (normalizedCity != null && !normalizedCity.isEmpty()) {
    probe.setCity(normalizedCity);
}
```

Đây là chính sách của ứng dụng, không phải hành vi tự động của Example.

### 8.3. Primitive không có trạng thái chưa chọn

Nếu domain dùng:

```java
private boolean active;
private int age;
```

Một instance mới thường đã có active bằng false và age bằng 0. Chúng không phải null, nên có thể tham gia so khớp dù người dùng chưa chọn hai tiêu chí này.

Các hướng xử lý gồm:

- Bỏ qua đường dẫn tương ứng khi không muốn lọc thuộc tính đó.
- Thiết kế model với wrapper nếu phù hợp ý nghĩa dữ liệu và mapping.
- Dùng một DTO đầu vào riêng để theo dõi tiêu chí được chọn, rồi xây probe và matcher có chủ đích.

`withIgnoreNullValues()` không làm false hoặc 0 biến thành null.

### 8.4. Constructor và field initializer cũng có thể tạo điều kiện

Nếu entity tự gán city, trạng thái hoặc thời điểm khi tạo mới, giá trị ấy có thể xuất hiện trong probe. QBE không tự phân biệt đâu là giá trị do người dùng nhập và đâu là giá trị khởi tạo phục vụ thao tác tạo entity.

Đặc biệt, không nên dùng nguyên một entity đã tải hoặc một đối tượng đầu vào chứa nhiều metadata làm probe mà chưa xem xét các thuộc tính sẽ tham gia.

## 9. Khi muốn so khớp giá trị null

Có thể dùng `withIncludeNullValues()` để yêu cầu đưa các thuộc tính null vào logic so khớp. Trong mô-đun hỗ trợ, điều này tương ứng ý định kiểm tra giá trị thiếu hoặc null theo ngữ nghĩa của kho dữ liệu.

Cần nhớ đây là cấu hình rộng, không chỉ áp dụng cho một field mà người viết đang nghĩ đến.

Ví dụ với đúng model sáu thuộc tính trong bài:

```java
Customer probe = new Customer();
probe.setCity("HCM");

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIncludeNullValues()
        .withIgnorePaths("id", "firstName", "lastName", "age")
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT);

Example<Customer> example = Example.of(probe, matcher);
```

Các đường dẫn đã bỏ qua không tham gia. Hai thuộc tính còn lại là city có giá trị HCM và active đang null. Ý định là:

```text
city khớp "HCM"
AND active là null
```

Nếu không bỏ qua các thuộc tính khác, chúng có thể trở thành điều kiện null bổ sung. Trong kho tài liệu, còn cần hiểu cách mô-đun và database phân biệt hoặc kết hợp field không tồn tại với field có giá trị null.

Không bật include-null chỉ để “tìm kiếm đầy đủ hơn” mà chưa xác định rõ ý nghĩa những null trong probe.

## 10. Kết hợp điều kiện: matchingAll và matchingAny

`matchingAll()` yêu cầu tất cả điều kiện được đưa vào đều khớp. `matching()` là cách tạo matcher thông thường theo ý nghĩa khớp tất cả.

`matchingAny()` yêu cầu ít nhất một điều kiện khớp.

Vẫn dùng probe có lastName, city và active:

| Cách kết hợp | Ý định logic |
| --- | --- |
| matchingAll | Họ có tiền tố ng AND city HCM AND active true |
| matchingAny | Họ có tiền tố ng OR city HCM OR active true |

Với bộ dữ liệu mẫu, matchingAny có thể nhận cả năm bản ghi: mỗi bản ghi đều khớp ít nhất một trong ba tiêu chí. Nó không có nghĩa là chỉ thay AND bằng OR cho một nhóm field do người gọi tự nghĩ ra.

QBE không phải một bộ xây biểu thức Boolean tùy ý. Không dùng một matcher để mặc định biểu đạt:

```text
active = true
AND (lastName bắt đầu bằng "ng" OR city = "HCM")
```

Cấu trúc có nhóm điều kiện như trên cần cơ chế truy vấn phù hợp khác, chẳng hạn query tường minh hoặc API predicate mà mô-đun hỗ trợ.

Nếu một điều kiện bắt buộc luôn phải đúng, không được giả định `matchingAny()` sẽ vẫn giữ riêng điều kiện đó ở dạng AND với các điều kiện còn lại.

## 11. Các lựa chọn so khớp chuỗi

ExampleMatcher cung cấp các chiến lược chuỗi để mô tả ý định tìm kiếm:

| Chiến lược | Ý định |
| --- | --- |
| DEFAULT | Dùng cách xử lý mặc định do mô-đun quyết định |
| EXACT | So khớp toàn bộ giá trị chuỗi |
| STARTING | Chuỗi bắt đầu bằng giá trị probe |
| ENDING | Chuỗi kết thúc bằng giá trị probe |
| CONTAINING | Chuỗi chứa giá trị probe |
| REGEX | So khớp theo biểu thức chính quy nếu mô-đun hỗ trợ |

Không phải mọi store hỗ trợ toàn bộ bảng. Chẳng hạn, khả năng regex không được suy ra từ việc enum có giá trị REGEX.

Có thể cấu hình chung cho các thuộc tính chuỗi hoặc tùy chỉnh riêng từng đường dẫn. Cần chọn phạm vi phù hợp:

```java
ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withMatcher(
                "lastName",
                ExampleMatcher.GenericPropertyMatchers.contains().ignoreCase());
```

Trong ví dụ này, lastName dùng chứa và ignoreCase; các thuộc tính chuỗi khác vẫn theo cấu hình chung. Cách này thường rõ hơn bật CONTAINING cho mọi chuỗi khi một vài field như mã hoặc trạng thái cần so khớp chính xác.

Collation, khả năng dùng index và cách xử lý ký tự của kho dữ liệu có thể ảnh hưởng kết quả và hiệu năng. Một matcher linh hoạt hơn không mặc định là truy vấn rẻ hơn.

## 12. Đọc một, đọc nhiều, đếm và kiểm tra tồn tại

QueryByExampleExecutor cung cấp các thao tác có ý nghĩa khác nhau:

```java
Iterable<Customer> matches = repository.findAll(example);

long total = repository.count(example);

boolean exists = repository.exists(example);

Optional<Customer> single = repository.findOne(example);
```

`Optional` thuộc `java.util.Optional`. Mỗi dòng trên là một lời gọi thực thi riêng; không phải bốn cách xem miễn phí trên cùng một kết quả đã tải.

| Thao tác | Khi phù hợp | Điều cần nhớ |
| --- | --- | --- |
| findAll | Cần các bản ghi phù hợp | Kết quả có thể lớn |
| count | Chỉ cần số lượng | Không cần tải toàn bộ entity chỉ để đếm ở ứng dụng |
| exists | Chỉ cần biết có bản ghi phù hợp không | Không thay thế hợp đồng đọc dữ liệu |
| findOne | Điều kiện được kỳ vọng khớp tối đa một bản ghi | Nhiều kết quả là lỗi về số lượng, không tự lấy phần tử đầu |

`findOne` có thể ném `IncorrectResultSizeDataAccessException` nếu có nhiều hơn một kết quả. Tạo probe không tự làm điều kiện trở thành duy nhất.

## 13. Thêm sort và phân trang

Example mô tả điều kiện so khớp. Sort và Pageable là các đầu vào riêng để điều khiển thứ tự và phân trang.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("lastName"),
                Sort.Order.asc("firstName"),
                Sort.Order.asc("id")));

Page<Customer> page = repository.findAll(example, pageable);
```

Ví dụ giả định mô-đun hỗ trợ dạng thực thi này. Khóa id làm tiêu chí phụ giúp thứ tự rõ hơn khi nhiều khách hàng có cùng họ và tên.

Cần phân biệt:

- Matcher không tự định nghĩa thứ tự kết quả.
- `withIgnorePaths("id")` chỉ bỏ id khỏi điều kiện so khớp; không tự cấm dùng id trong sort và không xóa id khỏi dữ liệu trả về.
- Page chứa metadata phân trang, có thể đi kèm chi phí truy vấn đếm tùy implementation.
- Example không phải projection. Bỏ qua email hoặc tuổi trong điều kiện không có nghĩa chỉ lấy những trường còn lại từ database.

Nếu cần projection kết hợp QBE, phải sử dụng cơ chế mà mô-đun và phiên bản hỗ trợ, chẳng hạn khả năng fluent query tương ứng. Không đổi kiểu probe sang một DTO tùy ý rồi giả định QBE sẽ tự truy vấn entity bằng DTO đó.

## 14. Xây probe từ đầu vào tìm kiếm

Một cách tổ chức rõ ràng là tách dữ liệu tìm kiếm của giao diện khỏi domain object. DTO tìm kiếm biểu đạt tiêu chí được chọn; service chuyển nó thành probe và matcher.

Ngay cả khi không tạo DTO riêng trong ví dụ, có thể gom logic thành một hàm:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

public Example<Customer> customerExample(
        String lastNamePrefix,
        String city,
        Boolean active) {

    Customer probe = new Customer();

    String prefix = lastNamePrefix == null
            ? null : lastNamePrefix.trim();
    String normalizedCity = city == null ? null : city.trim();

    if (prefix != null && !prefix.isEmpty()) {
        probe.setLastName(prefix);
    }

    if (normalizedCity != null && !normalizedCity.isEmpty()) {
        probe.setCity(normalizedCity);
    }

    if (active != null) {
        probe.setActive(active);
    }

    ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnorePaths("id", "firstName", "age")
            .withIgnoreNullValues()
            .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
            .withMatcher(
                    "lastName",
                    ExampleMatcher.GenericPropertyMatchers
                            .startsWith()
                            .ignoreCase());

    return Example.of(probe, matcher);
}
```

Hàm giả định các thuộc tính còn lại của Customer có trạng thái ban đầu như bảng model. Nó chủ động chọn ba tiêu chí tìm kiếm, thay vì đưa mọi field từ một đối tượng đầu vào vào query.

`active = false` vẫn là một tiêu chí hợp lệ và được đặt vào probe. `active = null` có nghĩa không lọc trạng thái trong hợp đồng hàm này.

Nếu cả ba tiêu chí đều không được chọn, Example có thể không có điều kiện giới hạn nào theo cấu hình này. Ứng dụng phải quyết định đó là yêu cầu xem tất cả có phân trang hay là đầu vào chưa hợp lệ. QBE không tự áp đặt chính sách sản phẩm cho trường hợp form trống.

## 15. Ranh giới khả năng của QBE

QBE phù hợp với các điều kiện dựa trên giá trị thuộc tính, đặc biệt là tìm kiếm có nhiều tiêu chí tùy chọn đơn giản. Nó không thay thế toàn bộ ngôn ngữ truy vấn.

Các giới hạn cần hiểu:

1. **Không có biểu thức nhóm Boolean tùy ý.** matchingAll và matchingAny không phải một cây AND/OR có thể lồng tự do.
2. **Không tự biểu đạt khoảng giá trị.** Đặt age bằng 18 không có nghĩa age lớn hơn hoặc bằng 18. Các kiểu không phải chuỗi thường được so khớp giá trị chính xác theo khả năng mô-đun.
3. **Không tự tạo IN từ mọi collection.** So khớp collection và map không phải khả năng tổng quát của QBE.
4. **Không có một bộ API join và aggregation đầy đủ.** Yêu cầu nhóm, tổng hợp, join đặc biệt hoặc điều kiện phức tạp có thể cần công cụ khác.
5. **Khả năng chuỗi phụ thuộc store.** Bắt đầu bằng, chứa, ignoreCase và regex phải được xác nhận cụ thể.

Một số mô-đun hỗ trợ truy cập thuộc tính lồng qua đường dẫn như `address.city` với quan hệ hoặc cấu trúc thích hợp. Điều này không đồng nghĩa hỗ trợ mọi phép duyệt collection hoặc nhóm logic lồng nhau. Cũng cần đánh giá dữ liệu được lấy và cách query thực hiện khi có thuộc tính lồng.

Khi yêu cầu vượt các giới hạn trên, nên chuyển sang cơ chế query phù hợp với mô-đun, thay vì gán giá trị giả vào probe hoặc cố diễn giải matcher thành toán tử mà nó không cung cấp.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Hướng kiểm tra |
| --- | --- | --- |
| Không có kết quả dù dữ liệu tưởng như đúng | Primitive, initializer hoặc field khác đã thành điều kiện | Liệt kê toàn bộ giá trị probe và đường dẫn không bị bỏ qua |
| Form trống lại trả rất nhiều bản ghi | Các giá trị đều bị bỏ qua nên không còn điều kiện | Xác định chính sách form trống và giới hạn kết quả |
| Muốn bỏ thành phố nhưng query tìm chuỗi rỗng | Đặt city bằng chuỗi rỗng thay vì null hoặc ignore path | Chuẩn hóa đầu vào và quy tắc chọn tiêu chí |
| Bật include-null rồi mất kết quả | Nhiều field null cùng trở thành điều kiện | Kiểm tra toàn bộ thuộc tính null và ignore paths |
| Bật ignoreCase nhưng không có tác dụng như mong muốn | Bỏ qua matcher mới hoặc kỳ vọng cả bỏ dấu | Kiểm tra phép gán, cấu hình theo property và collation |
| matchingAny cho kết quả quá rộng | Mọi tiêu chí tham gia OR | Viết lại biểu thức logic mong muốn trước khi chọn matcher |
| findOne báo nhiều kết quả | Điều kiện không bảo đảm duy nhất | Chọn findAll hoặc bổ sung tiêu chí đúng nghiệp vụ |
| Bỏ field khỏi matcher nhưng dữ liệu vẫn có field đó | Nhầm điều kiện so khớp với projection | Tách thiết kế query condition và hình dạng kết quả |
| Thay probe làm lần query sau đổi kết quả | Dùng chung đối tượng mutable | Tạo probe theo từng yêu cầu và giữ ổn định |
| REGEX không chạy | Mô-đun không hỗ trợ chiến lược đó | Kiểm tra khả năng store hoặc dùng cơ chế query khác |

## 17. Các ca kiểm chứng khi tích hợp

Một bộ dữ liệu đại diện nên có cả giá trị null, false, 0, chuỗi rỗng, tên có dấu và nhiều bản ghi cùng khớp một phần tiêu chí.

| Ca | Điều cần xác nhận |
| --- | --- |
| Một tiêu chí có giá trị | Query chỉ áp dụng đúng tiêu chí đã chọn |
| Nhiều tiêu chí với matchingAll | Các điều kiện được kết hợp AND |
| Cùng probe với matchingAny | Kết quả thể hiện OR theo đúng phạm vi |
| Thuộc tính null với ignore-null | Thuộc tính đó không làm điều kiện |
| Thuộc tính null với include-null | So khớp giá trị null theo ngữ nghĩa store |
| active false và age 0 | Không bị bỏ qua như giá trị chưa chọn |
| Chuỗi trắng từ form | Tuân thủ chính sách chuẩn hóa đầu vào |
| Giá trị id có trong probe nhưng bị ignore | Không vô tình lọc theo id |
| Phương thức with được gọi | Matcher mới thực sự được sử dụng |
| Nhiều kết quả với findOne | Không âm thầm lấy một kết quả bất kỳ |
| Có sort và nhiều trang | Nội dung, thứ tự và metadata phù hợp |
| Store có quy tắc chuỗi riêng | Kết quả đúng với collation và hỗ trợ thực tế |

Một đoạn mã chỉ tạo Example thành công trong bộ nhớ chưa chứng minh query của mô-đun đúng. Cần kiểm chứng thực thi với kho dữ liệu và cấu hình đại diện khi đưa vào ứng dụng.

## 18. Tình huống tự đánh giá

### A. Vì sao chỉ tìm khách hàng không hoạt động?

Domain dùng boolean active, instance probe mới có active bằng false. Người dùng chỉ nhập thành phố nhưng kết quả toàn là khách hàng không hoạt động.

Giải thích cách giá trị mặc định trở thành điều kiện và nêu hai cách biểu đạt trường hợp chưa chọn active.

### B. Include-null làm truy vấn quá chặt

Nhóm muốn tìm khách hàng chưa có tuổi nên bật withIncludeNullValues, nhưng đồng thời probe còn nhiều thuộc tính null khác.

Liệt kê các điều kiện có thể đã được thêm ngoài ý muốn. Thiết kế matcher hoặc cơ chế query phù hợp để thể hiện đúng yêu cầu.

### C. Muốn AND với một nhóm OR

Yêu cầu là khách hàng active và có họ bắt đầu bằng ng hoặc ở HCM. Người viết chọn matchingAny cho cả ba field.

Viết biểu thức thực tế mà matcher đang mô tả. Giải thích vì sao cần một cơ chế khác nếu muốn active luôn là điều kiện bắt buộc.

### D. Chuỗi tìm kiếm không được bỏ qua

Giao diện gửi city bằng ba dấu cách. Service đặt nguyên giá trị vào probe rồi dùng EXACT.

Xác định chính sách đầu vào cần được quyết định trước khi tạo Example và sự khác nhau giữa null, chuỗi trắng với một thành phố thật.

### E. Probe bị dùng lại

Một service giữ probe trong một field dùng chung và thay các thuộc tính theo từng yêu cầu tìm kiếm.

Phân tích tác động của trạng thái mutable và việc Example giữ probe. Đề xuất cách tạo đầu vào truy vấn ổn định cho từng yêu cầu.

### F. Muốn tìm tuổi từ 18 đến 30

Nhóm đặt age bằng 18 và kỳ vọng ExampleMatcher tự hiểu đó là giá trị cận dưới.

Giải thích ý nghĩa thực tế của giá trị probe và chọn loại cơ chế query cần xem xét cho khoảng tuổi.

## 19. Quy trình thực hành

1. Xác định tiêu chí tìm kiếm được phép và ý nghĩa của giá trị chưa chọn.
2. Tạo probe mới với những giá trị nguồn có chủ đích.
3. Chọn matchingAll hoặc matchingAny theo biểu thức logic thực sự cần.
4. Cấu hình null, ignore paths và so khớp chuỗi ở đúng phạm vi.
5. Tạo Example và giữ probe ổn định trong quá trình sử dụng.
6. Thực thi bằng QueryByExampleExecutor mà mô-đun hỗ trợ.
7. Thêm sort, phân trang hoặc cơ chế kết quả khác theo hợp đồng riêng.
8. Đối chiếu kết quả với dữ liệu có null, giá trị mặc định và các trường hợp chỉ khớp một phần.

Probe cung cấp giá trị, ExampleMatcher cung cấp quy tắc, còn Example gắn hai phần đó thành đầu vào truy vấn. Hiểu rõ ba vai trò này giúp dùng QBE đúng cho tìm kiếm đơn giản và nhận ra lúc yêu cầu cần một công cụ truy vấn khác.