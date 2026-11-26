# FetchableFluentQuery cho API đồng bộ

`FluentQuery.FetchableFluentQuery<T>` là abstraction của Spring Data Commons để cấu hình cách lấy kết quả truy vấn trong một API đồng bộ. Nó kết hợp những lựa chọn như sắp xếp, kiểu kết quả, tập thuộc tính cần lấy và thao tác kết thúc như `one()`, `all()` hoặc `page(...)`.

Một điểm sử dụng điển hình là phương thức `findBy(...)` của `QueryByExampleExecutor`. Probe và `ExampleMatcher` mô tả dữ liệu cần tìm; callback nhận `FetchableFluentQuery` để quyết định lấy dữ liệu theo hình thức nào. Implementation của từng Spring Data store chuyển các lựa chọn đó thành truy vấn thực tế.

Bài học tập trung vào API đồng bộ, ngữ nghĩa của từng dạng kết quả và cách giữ ranh giới giữa abstraction chung với khả năng của store.

## 1. “Fetchable” và “đồng bộ” có nghĩa gì?

Một fluent query cho phép nối tiếp các lựa chọn trước khi lấy kết quả:

```java
List<Customer> customers = repository.findBy(
    example,
    query -> query
        .sortBy(Sort.by("fullName").ascending())
        .all()
);
```

Trong đoạn mã:

- `example` mô tả điều kiện QBE.
- `query` là fluent query do repository implementation cung cấp cho callback.
- `sortBy(...)` bổ sung yêu cầu sắp xếp.
- `all()` lấy danh sách kết quả và quyết định kiểu trả về của callback.

API đồng bộ trả về các giá trị như `List<T>`, `Optional<T>`, `Page<T>`, `long` và `boolean`. Nó không trả về `Mono<T>` hoặc `Flux<T>` như một API reactive. Gọi phương thức này trong một ứng dụng reactive không tự làm thao tác truy cập dữ liệu trở thành không chặn.

Riêng `stream()` trả về Java `Stream<T>`. Stream có thể được đọc dần và có thể giữ tài nguyên của store; việc có Stream không đồng nghĩa với reactive streaming hoặc với bảo đảm sử dụng bộ nhớ hằng số.

## 2. Hợp đồng callback của `findBy`

Phương thức của `QueryByExampleExecutor<T>` có hình thức:

```java
<S extends T, R> R findBy(
    Example<S> example,
    Function<FluentQuery.FetchableFluentQuery<S>, R> queryFunction
);
```

Các kiểu liên quan thuộc các package:

```java
import java.util.function.Function;

import org.springframework.data.domain.Example;
import org.springframework.data.repository.query.FluentQuery;
import org.springframework.data.repository.query.QueryByExampleExecutor;
```

`S` là kiểu miền của probe, còn `R` là kiểu kết quả callback trả về. Vì vậy, cùng một `Example<Customer>` có thể được dùng để lấy nhiều dạng kết quả:

```java
List<Customer> rows = repository.findBy(example, query -> query.all());

Optional<Customer> first = repository.findBy(
    example,
    query -> query.sortBy(Sort.by("id").ascending()).first()
);

long total = repository.findBy(example, query -> query.count());

boolean present = repository.findBy(example, query -> query.exists());
```

Ở các đoạn mã này, cần import `List`, `Optional` từ `java.util` và `Sort` từ `org.springframework.data.domain`.

### Không tự tạo hay giữ fluent query để dùng sau

Thông thường ứng dụng không khởi tạo `FetchableFluentQuery` trực tiếp. Repository tạo implementation gắn với truy vấn hiện tại rồi truyền nó vào callback.

Callback phải hoàn tất việc chọn cấu hình và gọi thao tác lấy kết quả trong phạm vi `findBy(...)`. Không trả về chính query builder:

```java
// Sai cách sử dụng: làm fluent query thoát khỏi callback.
var query = repository.findBy(example, fluent -> fluent);
```

Tương tự, không gán `fluent` vào một field để tái sử dụng sau khi `findBy` đã kết thúc. Không dựa vào một loại exception cụ thể cho hành vi sai này trên mọi store; cần tuân thủ vòng đời mà API quy định.

Có thể tái sử dụng một hàm cấu hình và lấy kết quả, nhưng mỗi lần gọi phải nhận query mới do repository cung cấp. Không tái sử dụng instance query của lần gọi trước.

## 3. Chuẩn bị một ví dụ QBE đồng bộ

### 3.1. Mô hình minh họa

Giả sử có mô hình `Customer` với các thuộc tính sau:

```java
public class Customer {

    private String id;
    private String fullName;
    private String email;
    private Boolean active;

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Boolean getActive() { return active; }
    public void setActive(Boolean active) { this.active = active; }
}
```

Đây là phần mô hình phục vụ minh họa abstraction chung. Khi tích hợp thực tế, cần bổ sung mapping, định danh và các yêu cầu của store. Một lớp Java không tự trở thành entity JPA hay document hợp lệ chỉ vì được dùng làm probe.

Repository sử dụng các abstraction Commons:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, String>,
                QueryByExampleExecutor<Customer> {
}
```

Store và implementation được chọn phải hỗ trợ QBE cùng các thao tác fluent cần dùng. Chỉ thêm interface vào khai báo không tự cung cấp một implementation cho store chưa hỗ trợ.

### 3.2. Tạo điều kiện tìm kiếm

Factory sau tìm khách hàng đang hoạt động có tên bắt đầu bằng tiền tố được nhập:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.ExampleMatcher.GenericPropertyMatchers;

public final class CustomerExamples {

    private CustomerExamples() {
    }

    public static Example<Customer> activeWithNamePrefix(String rawPrefix) {
        if (rawPrefix == null || rawPrefix.trim().isEmpty()) {
            throw new IllegalArgumentException("Tiền tố tên không được trống");
        }

        Customer probe = new Customer();
        probe.setFullName(rawPrefix.trim());
        probe.setActive(Boolean.TRUE);

        ExampleMatcher matcher = ExampleMatcher.matchingAll()
            .withIgnorePaths("id", "email")
            .withIgnoreNullValues()
            .withMatcher(
                "fullName",
                GenericPropertyMatchers.startsWith().ignoreCase()
            );

        return Example.of(probe, matcher);
    }
}
```

`active` dùng `Boolean` để mô hình có thể biểu diễn trạng thái vắng mặt khi cần; trong factory này nó được đặt rõ là `true`. `id` và `email` không thuộc bộ lọc nên được bỏ qua tường minh.

Trong các đoạn tiếp theo, giả sử service đã có `CustomerRepository repository` và tạo:

```java
Example<Customer> example = CustomerExamples.activeWithNamePrefix(" Linh ");

Sort stableSort = Sort.by(
    Sort.Order.asc("fullName"),
    Sort.Order.asc("id")
);
```

Các ví dụ lấy danh sách toàn bộ phù hợp với tập dữ liệu minh họa nhỏ. Với màn hình thực tế, nên chọn phân trang hoặc giới hạn tương ứng với yêu cầu sử dụng.

## 4. Chọn thao tác kết thúc theo đúng ngữ nghĩa

Các thao tác dưới đây không chỉ khác kiểu Java trả về. Chúng biểu đạt các kỳ vọng khác nhau về số lượng và cách tiêu thụ kết quả.

| Phương thức | Kết quả | Không có bản ghi | Có nhiều bản ghi |
| --- | --- | --- | --- |
| `one()` | `Optional<T>` | `Optional.empty()` | Lỗi do kết quả không duy nhất |
| `oneValue()` | `T` có thể null | `null` | Lỗi do kết quả không duy nhất |
| `first()` | `Optional<T>` | `Optional.empty()` | Lấy bản ghi đầu theo thứ tự áp dụng |
| `firstValue()` | `T` có thể null | `null` | Lấy bản ghi đầu theo thứ tự áp dụng |
| `all()` | `List<T>` | Danh sách rỗng | Lấy các bản ghi khớp |
| `page(Pageable)` | `Page<T>` | Trang không có nội dung | Lấy nội dung trang cùng metadata phân trang |
| `stream()` | `Stream<T>` | Stream không có phần tử | Tiêu thụ các phần tử theo cơ chế của store |
| `count()` | `long` | `0` | Đếm số bản ghi khớp |
| `exists()` | `boolean` | `false` | `true` nếu tồn tại ít nhất một bản ghi khớp |

### 4.1. `one()` kiểm tra kỳ vọng duy nhất

```java
Optional<Customer> single = repository.findBy(
    example,
    query -> query.one()
);
```

Nếu tiền tố tên khớp nhiều khách hàng, `one()` không tự chọn một người. Nó báo lỗi kết quả không đúng kích thước mong đợi, thường được biểu đạt bằng `IncorrectResultSizeDataAccessException` trong abstraction truy cập dữ liệu của Spring.

Dùng `one()` khi trường hợp sử dụng thực sự kỳ vọng tối đa một kết quả. Không dùng nó với bộ lọc rộng chỉ để tránh xử lý danh sách.

`one()` cũng không tạo ràng buộc duy nhất trong kho dữ liệu và không khóa bản ghi. Nếu nghiệp vụ đòi hỏi một giá trị là duy nhất, cần ràng buộc hoặc cơ chế dữ liệu phù hợp ngoài lựa chọn phương thức đọc.

### 4.2. `first()` chấp nhận nhiều kết quả

```java
Optional<Customer> first = repository.findBy(
    example,
    query -> query.sortBy(stableSort).first()
);
```

`first()` phù hợp khi nghiệp vụ chủ động chọn phần tử đứng đầu, chẳng hạn khách hàng có tên đứng trước theo thứ tự đã định.

Thêm `sortBy(...)` trước `one()` không biến `one()` thành `first()`. Một truy vấn đã sắp xếp vẫn có thể có nhiều kết quả và vẫn vi phạm kỳ vọng duy nhất.

Nên ưu tiên `one()` và `first()` khi phía gọi cần biểu diễn rõ việc không có dữ liệu bằng `Optional`. Dùng biến thể `oneValue()` hoặc `firstValue()` khi hợp đồng của tầng tích hợp thực sự cần giá trị nullable và phía gọi xử lý null đầy đủ.

## 5. Sắp xếp rõ ràng và giữ cấu hình trả về

Các phương thức cấu hình fluent trả về một fluent query đã được cấu hình. Hãy nối chuỗi hoặc giữ giá trị trả về, thay vì giả định mọi lời gọi đều sửa instance hiện có.

```java
List<Customer> customers = repository.findBy(
    example,
    query -> query.sortBy(stableSort).all()
);
```

Không nên viết theo giả định mutation:

```java
// Tránh dựa vào việc sortBy sửa trực tiếp biến query.
List<Customer> customers = repository.findBy(example, query -> {
    query.sortBy(stableSort);
    return query.all();
});
```

Tên trường trong `Sort` là property path của mô hình miền. Không tự thay bằng tên cột SQL, tên alias của DTO hoặc cú pháp riêng của kho dữ liệu.

### Vì sao cần khóa phụ như ID?

Nếu chỉ sắp xếp theo `fullName`, nhiều khách hàng có thể cùng tên. Phần thứ tự giữa họ chưa được xác định duy nhất. Thêm `id` làm khóa phụ giúp thứ tự có tính xác định trên tập dữ liệu đang xét, với giả định ID duy nhất và có thể sắp xếp trong store.

Điều này hữu ích cho `first()` và phân trang. Tuy nhiên, thứ tự xác định không tự tạo snapshot nhất quán giữa nhiều request: dữ liệu được thêm, xóa hoặc sửa trong lúc người dùng chuyển trang vẫn có thể làm các trang thay đổi.

Cấu hình bỏ qua hoa thường trong `ExampleMatcher` thuộc điều kiện tìm kiếm. Nó không tự cấu hình cùng một quy tắc cho `Sort`. Collation và khả năng sắp xếp hoa thường của store cần được xem riêng.

## 6. `as(...)` và `project(...)` giải quyết hai việc khác nhau

### 6.1. `as(...)` chọn kiểu kết quả

Một interface projection có thể chỉ mô tả những giá trị cần hiển thị:

```java
public interface CustomerSummary {
    String getId();
    String getFullName();
    String getEmail();
}
```

Lấy projection qua fluent query:

```java
List<CustomerSummary> summaries = repository.findBy(
    example,
    query -> query
        .as(CustomerSummary.class)
        .sortBy(stableSort)
        .all()
);
```

Sau `as(CustomerSummary.class)`, kiểu phần tử của fluent query chuyển sang `CustomerSummary`, nên `all()` trả về `List<CustomerSummary>`.

Đây không phải một bộ chuyển đổi Java tùy ý như `stream.map(...)`. Projection phải phù hợp với metadata, tên thuộc tính và cơ chế ánh xạ mà implementation hỗ trợ. Không suy ra rằng `as(AnyClass.class)` có thể tự ánh xạ sang mọi DTO hoặc lớp không liên quan.

Nếu dùng DTO dạng class, cần đáp ứng yêu cầu về constructor, tên và kiểu dữ liệu theo cơ chế projection của store. Các quy tắc đó không được một mình Spring Data Commons bảo đảm cho mọi implementation.

### 6.2. `project(...)` chọn tập thuộc tính

`project(...)` mô tả những property path cần lấy theo khả năng của store. Ví dụ dùng overload nhận collection:

```java
List<CustomerSummary> summaries = repository.findBy(
    example,
    query -> query
        .as(CustomerSummary.class)
        .project(Arrays.asList("id", "fullName", "email"))
        .sortBy(stableSort)
        .all()
);
```

Đoạn mã cần `import java.util.Arrays;`. Chỉ áp dụng tổ hợp này khi store hỗ trợ projection và việc chọn thuộc tính tương ứng.

Phân biệt hai lựa chọn:

| Lựa chọn | Câu hỏi được trả lời |
| --- | --- |
| `as(CustomerSummary.class)` | Kết quả Java được biểu diễn bằng kiểu nào? |
| `project(...)` | Những thuộc tính nào được yêu cầu lấy trong truy vấn? |

Không coi `project(...)` là một lời bảo đảm chung về câu SQL `SELECT` hoặc số byte được đọc. Store có thể cần thêm định danh, metadata hay các giá trị phục vụ ánh xạ; một số kiểu projection cũng cần nhiều dữ liệu hơn dự kiến. Hiệu quả thực tế phải được đối chiếu với store.

Nếu chọn một phần thuộc tính nhưng vẫn nhận đối tượng kiểu entity, đừng dùng đối tượng đó như một entity đầy đủ để ghi ngược. Thuộc tính không được lấy không có cùng ý nghĩa với một thay đổi nghiệp vụ chủ động đặt thành null.

## 7. Phân trang bằng `page(Pageable)`

`page(...)` phù hợp khi giao diện cần nội dung trang cùng thông tin như tổng số phần tử hoặc tổng số trang.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable pageable = PageRequest.of(0, 20, stableSort);

Page<CustomerSummary> page = repository.findBy(
    example,
    query -> query
        .as(CustomerSummary.class)
        .page(pageable)
);

List<CustomerSummary> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
```

Chỉ số trang của `PageRequest` bắt đầu từ `0`, nên trang đầu là `PageRequest.of(0, ...)`. Kích thước trang phải dương; ở biên API cần kiểm tra và giới hạn kích thước người dùng yêu cầu theo chính sách của ứng dụng.

Trong ví dụ, toàn bộ cấu hình sắp xếp cho phân trang nằm trong `Pageable`. Cách làm này tránh đặt nhiều yêu cầu sort ở các vị trí khác nhau rồi dựa vào suy đoán về thứ tự ưu tiên hoặc cách hợp nhất của implementation.

### Không mặc định mỗi Page luôn có đúng hai truy vấn

Để cung cấp tổng số phần tử, implementation có thể thực hiện một thao tác count bổ sung. Tuy nhiên, một số tình huống có thể suy ra tổng số hoặc tối ưu việc đếm. Vì thế:

- Không cam kết rằng `page(...)` luôn chỉ có một lần truy cập dữ liệu.
- Cũng không khẳng định mọi lần gọi đều có chính xác hai truy vấn.
- Cân nhắc chi phí tổng số phần tử trên tập dữ liệu lớn.

`Page` không bảo đảm một snapshot xuyên nhiều lần gọi phân trang. Nếu cần tính nhất quán mạnh hơn hoặc duyệt tập dữ liệu lớn theo cursor, phải chọn cách truy vấn, giao dịch và API mà store thực sự hỗ trợ.

## 8. Dùng `stream()` với vòng đời tài nguyên rõ ràng

Một đoạn xuất dữ liệu có thể lấy Stream:

```java
import java.util.stream.Stream;

try (Stream<CustomerSummary> stream = repository.findBy(
        example,
        query -> query
            .as(CustomerSummary.class)
            .sortBy(stableSort)
            .stream())) {

    stream.forEach(exporter::writeRow);
}
```

`exporter` ở đây là thành phần xuất dữ liệu của ứng dụng, có phương thức nhận một `CustomerSummary` để ghi một dòng.

Lời gọi `stream()` được thực hiện bên trong callback theo đúng hợp đồng fluent query. Giá trị trả ra là Stream kết quả, không phải query builder. Dù vậy, việc tiêu thụ dữ liệu có thể tiếp tục sau khi callback đã trả về, nên tài nguyên liên quan phải còn hiệu lực.

Các điểm cần giữ:

- Đóng Stream bằng try-with-resources, kể cả khi xử lý gặp lỗi.
- Giữ giao dịch, session hoặc connection cần thiết còn hiệu lực trong suốt lúc tiêu thụ theo yêu cầu của store.
- Với JPA, chú ý giao dịch bao quanh cả thao tác mở và đọc Stream theo cấu hình của ứng dụng.
- Không trả một Stream phụ thuộc connection ra khỏi service sau khi giao dịch cần thiết đã kết thúc.
- Không gọi `parallel()` với kỳ vọng session, cursor hoặc connection sẽ tự an toàn cho nhiều luồng.

Một implementation có thể thực hiện streaming bằng cursor; implementation khác có thể materialize dữ liệu trước. Vì vậy, `stream()` không tự bảo đảm dữ liệu không được nạp toàn bộ vào bộ nhớ.

Nếu ngay sau đó gọi `collect(...)` để tạo một danh sách lớn, ứng dụng vẫn phải giữ toàn bộ danh sách ấy trong bộ nhớ. Cách tiêu thụ dữ liệu quan trọng không kém kiểu kết quả mà repository trả về.

## 9. Dùng `count()` và `exists()` đúng mục đích

Nếu chỉ cần tổng số, lấy trực tiếp giá trị count:

```java
long total = repository.findBy(example, query -> query.count());
```

Nếu chỉ cần kiểm tra có dữ liệu:

```java
boolean hasMatch = repository.findBy(example, query -> query.exists());
```

Tránh tải toàn bộ kết quả chỉ để trả lời hai câu hỏi trên:

```java
// Không cần thiết khi mục tiêu chỉ là đếm hoặc kiểm tra tồn tại.
int total = repository.findBy(example, query -> query.all()).size();
boolean hasMatch = !repository.findBy(example, query -> query.all()).isEmpty();
```

`count()` có kiểu trả về `long`, phù hợp với số lượng có thể vượt giới hạn của `int`. `exists()` diễn đạt đúng việc chỉ cần biết có ít nhất một bản ghi; implementation có thể tối ưu theo khả năng store.

Không cam kết rằng `exists()` ở mọi store dùng cùng một câu truy vấn hoặc luôn có cùng chi phí. Tương tự, count trên điều kiện phức tạp và tập dữ liệu lớn vẫn có thể tốn tài nguyên.

Kết quả count hoặc exists chỉ phản ánh lần đọc đó. Chúng không tự bảo đảm điều kiện vẫn đúng ở một thao tác ghi tiếp theo, không cấp quyền cập nhật và không thay thế ràng buộc duy nhất trong dữ liệu.

## 10. Giữ trách nhiệm của callback hẹp và rõ

Callback phù hợp nên gồm việc chọn hình thức kết quả rồi thực thi một thao tác lấy kết quả có chủ ý:

```java
Page<CustomerSummary> result = repository.findBy(
    example,
    query -> query.as(CustomerSummary.class).page(pageable)
);
```

Tránh biến callback thành nơi điều phối nhiều tác vụ không liên quan như ghi entity, gọi API từ xa hoặc thay đổi probe. Những tác vụ đó khiến số lần truy cập dữ liệu, vòng đời giao dịch và lỗi thực thi khó dự đoán.

Cũng không cần tự gọi count rồi lấy trang chỉ để ghép lại metadata mà `Page` đã cung cấp:

```java
// Hai thao tác kết thúc được gọi tường minh trong cùng callback.
// Không mặc định đây là một lần truy vấn hoặc một snapshot chung.
return repository.findBy(example, query -> {
    long total = query.count();
    List<Customer> rows = query.sortBy(stableSort).all();
    return buildResponse(total, rows);
});
```

`buildResponse(...)` trong đoạn minh họa là hàm của ứng dụng. Nếu thực sự cần hai thao tác, phải chấp nhận và thiết kế cho chi phí cùng khả năng dữ liệu thay đổi giữa chúng. Nếu mục tiêu là phân trang tiêu chuẩn, ưu tiên `page(...)`.

## 11. Giới hạn của abstraction và khả năng từng store

`FetchableFluentQuery` chuẩn hóa cách diễn đạt lựa chọn lấy kết quả. Nó không đồng nhất mọi khả năng truy vấn của JPA, MongoDB hay các store khác.

Trước khi áp dụng một lựa chọn, cần đối chiếu:

| Khía cạnh | Điều cần xác định ở implementation |
| --- | --- |
| QBE | Store có hỗ trợ repository executor và matcher đang dùng không? |
| Property path | Đường dẫn thuộc tính lồng nhau có được ánh xạ và truy vấn như mong muốn không? |
| Projection | Interface hoặc DTO được chuyển thành kết quả bằng cơ chế nào? |
| Chọn thuộc tính | `project(...)` có được hỗ trợ và tác động đến dữ liệu lấy ra ra sao? |
| Sort | Kiểu thuộc tính, collation và thứ tự null được xử lý thế nào? |
| Phân trang | Nội dung trang và tổng số phần tử được lấy với chi phí nào? |
| Stream | Có giữ cursor hoặc connection không, cần giao dịch gì và đóng ở đâu? |

Các lựa chọn mở rộng như giới hạn, slice hoặc scroll phải được dùng theo API mà phiên bản thư viện và store của dự án cung cấp. Không suy ra khả năng hỗ trợ chỉ từ việc nhìn thấy một tên phương thức trong tài liệu của module khác.

Fluent query cũng không biến QBE thành ngôn ngữ truy vấn tùy ý. Nếu cần nhóm Boolean phức tạp, điều kiện khoảng, join hoặc tìm kiếm toàn văn ngoài khả năng QBE của store, hãy chọn một cơ chế truy vấn phù hợp. Việc đổi từ `all()` sang `page(...)` chỉ đổi cách lấy kết quả, không bổ sung những điều kiện mà QBE chưa diễn đạt được.

## 12. Tình huống tự thực hành

Dùng một store hỗ trợ các thao tác đã chọn và chuẩn bị dữ liệu có nhiều khách hàng cùng tiền tố tên, một số người trùng tên nhưng khác ID.

| Tình huống | Hành vi cần đối chiếu |
| --- | --- |
| Không có bản ghi khớp | `one()` và `first()` trả Optional rỗng; `all()` trả danh sách rỗng |
| Có đúng một bản ghi khớp | Phân biệt kiểu kết quả của `one()`, `oneValue()` và `all()` |
| Có nhiều bản ghi khớp | `one()` báo lỗi kỳ vọng duy nhất; `first()` vẫn chọn được phần tử đầu |
| Nhiều bản ghi trùng tên | Sort có ID làm khóa phụ tạo thứ tự xác định trên tập dữ liệu cố định |
| Chuyển sang `CustomerSummary` | Tên và kiểu accessor được ánh xạ đúng theo projection của store |
| Phân trang với kích thước nhỏ | Nội dung, số trang và tổng số phần tử có ý nghĩa đúng |
| Xử lý Stream gặp lỗi giữa chừng | Stream được đóng và tài nguyên không bị giữ ngoài phạm vi cần thiết |
| Chỉ cần biết có kết quả | Dùng `exists()` thay cho tải danh sách |
| Query builder bị trả ra khỏi callback | Nhận biết đây là cách dùng không hợp lệ, không thiết kế luồng phụ thuộc vào nó |

Lựa chọn phương thức kết thúc nên bắt đầu từ câu hỏi nghiệp vụ: cần một kết quả duy nhất, phần tử đầu, một trang, một luồng xử lý hay chỉ số lượng. Sau đó mới cấu hình sort, projection và tập thuộc tính phù hợp. Cách tổ chức này giúp API đồng bộ thể hiện rõ ý định mà vẫn giữ đúng trách nhiệm của repository implementation và kho dữ liệu.