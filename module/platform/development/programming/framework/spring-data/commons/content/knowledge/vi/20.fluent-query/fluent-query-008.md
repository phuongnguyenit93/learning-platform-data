# Thời điểm thực thi trong callback và giới hạn tái sử dụng đối tượng truy vấn

Fluent query trong Spring Data cho phép cấu hình và thực thi truy vấn bên trong một callback. Cách viết ngắn gọn này dễ tạo cảm giác đối tượng query là một builder có thể cất giữ, chuyển sang luồng khác hoặc gọi lại bất cứ lúc nào. Với `QueryByExampleExecutor.findBy`, đối tượng fluent query được cung cấp cho callback chỉ có phạm vi sử dụng trong lần gọi callback đó.

Điểm quan trọng là phân biệt **đối tượng cấu hình truy vấn**, **thao tác lấy kết quả** và **tài nguyên mà kết quả còn sử dụng**. Một `List` đã được lấy, một `Stream` còn gắn với cursor và một publisher reactive có vòng đời khác nhau. Không thể suy luận thời điểm đọc dữ liệu chỉ từ việc callback đã trả về.

Bài học tập trung vào abstraction của Spring Data Commons, sử dụng QBE đồng bộ làm ví dụ chính. Các chi tiết về transaction, cursor, projection và thời điểm gửi lệnh cụ thể cần được đối chiếu với store module đang dùng.

## 1. Hợp đồng sử dụng của findBy

Một cách sử dụng điển hình:

```java
List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").and(Sort.by("id")))
                .all());
```

Trong ví dụ:

- `example` mô tả điều kiện tìm kiếm.
- `q` là fluent query do repository cung cấp cho lần gọi hiện tại.
- `sortBy(...)` trả về cấu hình truy vấn có thứ tự tương ứng.
- `all()` là thao tác lấy danh sách.
- Callback trả danh sách kết quả, không trả đối tượng `q` để bên ngoài thực thi tiếp.

Đối với nhánh đồng bộ này, tham số hàm truy vấn làm việc với `FluentQuery.FetchableFluentQuery<S>`. Có thể hình dung vai trò của hàm là:

```text
FetchableFluentQuery<S> -> kết quả R
```

Hợp đồng không phải:

```text
FetchableFluentQuery<S> -> builder độc lập có thể dùng ở mọi nơi
```

Đối tượng query chỉ hợp lệ để sử dụng trong lần gọi hàm truy vấn. Các đối tượng mới được tạo ra bằng cách cấu hình từ `q` cũng thuộc quá trình thực thi đó; không coi chúng là cách thoát khỏi giới hạn phạm vi.

Java có thể cho phép một số cách trả về hoặc giữ tham chiếu query về mặt kiểu dữ liệu. Khả năng biên dịch không thay thế hợp đồng vòng đời của API.

## 2. Mô hình tối thiểu cho các ví dụ

Giả sử `Customer` có các thuộc tính:

| Thuộc tính Java | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `Long` | Định danh |
| `fullName` | `String` | Họ tên |
| `email` | `String` | Email |
| `city` | `String` | Thành phố |
| `active` | `Boolean` | Trạng thái hoạt động |
| `createdAt` | `Instant` | Metadata thời gian tạo |
| `version` | `Long` | Metadata phiên bản |

Các ví dụ giả định có constructor không tham số và getter/setter tương ứng. Mapping của `Customer` cần phù hợp với store; đây không phải một mapping lưu trữ dùng chung nguyên trạng cho mọi module.

Repository công bố khả năng QBE khi store hỗ trợ:

```java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.repository.query.QueryByExampleExecutor;

public interface CustomerRepository
        extends CrudRepository<Customer, Long>,
                QueryByExampleExecutor<Customer> {
}
```

Tạo một Example mới cho yêu cầu hiện tại:

```java
import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;

Customer probe = new Customer();
probe.setCity("Huế");
probe.setActive(true);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
        .withIgnoreNullValues()
        .withStringMatcher(ExampleMatcher.StringMatcher.EXACT)
        .withIgnorePaths("id", "createdAt", "version");

Example<Customer> example = Example.of(probe, matcher);
```

Các đoạn mã tiếp theo sử dụng `repository`, `example`, `java.util.List` và `org.springframework.data.domain.Sort`. Ví dụ dùng record và `Stream.toList()` giả định Java 17 trở lên.

Một kiểu kết quả thuần dữ liệu để tách phần đã đọc khỏi entity:

```java
public record CustomerRow(Long id, String fullName, String email) {
    public static CustomerRow from(Customer customer) {
        return new CustomerRow(
                customer.getId(),
                customer.getFullName(),
                customer.getEmail());
    }
}
```

Ở mô hình minh họa, ba getter trên là các thuộc tính scalar đã được đọc cho thao tác tương ứng. Nếu mô hình thực tế có thuộc tính lazy hoặc tính toán cần truy cập kho dữ liệu, cần bảo đảm việc ánh xạ diễn ra khi tài nguyên cần thiết còn hợp lệ.

## 3. Cấu hình chưa đồng nghĩa với đọc kết quả

Bên trong callback, các phương thức như `sortBy`, `as` hoặc `project` lựa chọn cách lấy kết quả. Chúng không tự yêu cầu trả danh sách bản ghi cho ứng dụng.

```java
List<Customer> customers = repository.findBy(example, q -> {
    var ordered = q.sortBy(Sort.by("fullName").and(Sort.by("id")));
    return ordered.all();
});
```

Có thể chia diễn tiến thành các mốc:

| Mốc | Hành động | Điều cần hiểu |
| --- | --- | --- |
| T0 | Tạo probe, matcher và Example | Chưa gọi thao tác repository lấy kết quả |
| T1 | Gọi `findBy(example, callback)` | Repository chuẩn bị ngữ cảnh truy vấn và gọi callback |
| T2 | Callback gọi các phương thức cấu hình | Dùng đối tượng cấu hình được trả về cho bước sau |
| T3 | Callback gọi `all()`, `count()` hoặc thao tác kết thúc khác | Chọn và thực hiện hoặc thiết lập thao tác lấy kết quả theo loại API |
| T4 | Callback trả kết quả | Không tiếp tục sử dụng fluent query ở bên ngoài |
| T5 | Bên gọi sử dụng kết quả | Kết quả có thể đã được materialize hoặc còn cần tài nguyên, tùy loại |

Không nên dùng bảng này để khẳng định mọi implementation chỉ tạo đối tượng nội bộ ở T2 hoặc chỉ gửi đúng một lệnh vào T3. Việc xác thực đường dẫn, dựng truy vấn, tối ưu và truy cập dữ liệu cụ thể do store quyết định. Điểm cần giữ là ranh giới giữa cấu hình query và yêu cầu lấy kết quả.

### Phải dùng cấu hình được trả về

```java
List<Customer> customers = repository.findBy(example, q -> {
    q.sortBy(Sort.by("fullName"));
    return q.all();
});
```

Đoạn trên bỏ qua giá trị trả về của `sortBy`. Không dựa vào giả định phương thức đã sửa trực tiếp `q`. Cách viết đúng là tiếp tục dùng query đã được cấu hình:

```java
List<Customer> customers = repository.findBy(
        example,
        q -> q.sortBy(Sort.by("fullName").and(Sort.by("id")))
                .all());
```

## 4. Vì sao không trả fluent query ra khỏi callback?

Ví dụ sau vi phạm phạm vi sử dụng:

```java
// Ví dụ sai hợp đồng API, không dùng trong ứng dụng.
var escapedQuery = repository.findBy(example, q -> q);
var customers = escapedQuery.all();
```

Callback chưa trả kết quả của một thao tác truy vấn. Nó đưa đối tượng query ra khỏi ngữ cảnh mà repository cung cấp.

Implementation có thể phát hiện việc trả trực tiếp fluent query và từ chối lời gọi. Không dựa vào một loại exception hay thông báo cố định cho mọi store. Quan trọng hơn, không dựa vào việc một biến thể chưa bị phát hiện để cho rằng cách dùng đó hợp lệ.

Những cách giữ query gián tiếp cũng có cùng vấn đề:

- Gán `q` vào field của service.
- Đặt query vào một collection hoặc cache.
- Đưa query vào đối tượng response để thực thi ở controller.
- Trả một hàm hoặc method reference còn giữ tham chiếu `q`.
- Chuyển query cho một tác vụ sẽ chạy sau khi callback kết thúc.

Thêm một lớp wrapper không kéo dài vòng đời được API cho phép. Nếu cần thực thi một truy vấn mới ở thời điểm khác, hãy gọi repository mới với đầu vào và ngữ cảnh phù hợp.

## 5. Supplier và xử lý bất đồng bộ có thể làm query thoát phạm vi

Một ví dụ dễ bỏ sót là trả về `Supplier`:

```java
import java.util.function.Supplier;

// Ví dụ sai: việc dùng q bị trì hoãn ra ngoài callback.
Supplier<List<Customer>> later = repository.findBy(
        example,
        q -> () -> q.all());

List<Customer> customers = later.get();
```

Callback thực sự trả về một hàm. Hàm đó mới sử dụng `q` khi `get()` được gọi, lúc callback ban đầu đã kết thúc.

Tương tự, không chuyển query sang một worker thread:

```java
import java.util.concurrent.CompletableFuture;

// Ví dụ sai: query bị chuyển sang tác vụ khác.
CompletableFuture<List<Customer>> later = repository.findBy(
        example,
        q -> CompletableFuture.supplyAsync(q::all));
```

Thời điểm thread khác chạy là không xác định. Ngoài giới hạn phạm vi query, transaction dựa trên ngữ cảnh thread của nhánh đồng bộ cũng không tự được truyền chỉ vì có một method reference.

Nếu cần xử lý bất đồng bộ, tác vụ mới nên nhận dữ liệu đầu vào như thành phố, giới hạn hoặc định danh yêu cầu. Tác vụ đó gọi một phương thức service phù hợp, tạo probe và Example cho lần thực thi riêng rồi gọi repository trong ngữ cảnh của nó.

Có thể dùng một `Supplier` như một mô tả công việc mới nếu mỗi lần gọi của nó thực hiện một lời gọi repository mới. Điểm phân biệt là hàm đó gọi `repository.findBy(...)` để nhận query mới, thay vì giữ query của một callback đã kết thúc. Vẫn cần thiết kế transaction, dữ liệu đầu vào và khả năng gọi đồng thời theo yêu cầu thực tế.

## 6. Có thể tái sử dụng query trong cùng callback đến đâu?

Trong một callback, có thể tạo các cấu hình dẫn xuất và gọi nhiều thao tác khi API cùng store hỗ trợ. Giới hạn phạm vi không có nghĩa callback chỉ được chứa đúng một dòng.

Ví dụ lấy tổng số và danh sách:

```java
public record CustomerBatch(long total, List<CustomerRow> rows) {
}
```

```java
CustomerBatch batch = repository.findBy(example, q -> {
    long total = q.count();

    List<CustomerRow> rows = q
            .sortBy(Sort.by("fullName").and(Sort.by("id")))
            .all()
            .stream()
            .map(CustomerRow::from)
            .toList();

    return new CustomerBatch(total, rows);
});
```

Cả hai thao tác đều được yêu cầu khi callback còn đang chạy. Callback trả dữ liệu kết quả, không trả query.

Tuy nhiên, `count()` và `all()` là hai thao tác. Không coi fluent query là bộ nhớ đệm kết quả để khẳng định lần gọi thứ hai sử dụng dữ liệu đã lấy bởi lần đầu. Cũng không giả định hai thao tác sẽ tự dùng một snapshot nhất quán chỉ vì chúng nằm trong cùng lambda.

Dữ liệu có thể thay đổi giữa các thao tác, tùy transaction, mức isolation và store. Khi cần một trang có metadata, nên cân nhắc thao tác `page(...)` mà API hỗ trợ; nếu cần yêu cầu nhất quán mạnh hơn, cần thiết kế ở tầng giao dịch và kho dữ liệu.

Tương tự, gọi `all()` hai lần trong cùng callback là hai yêu cầu lấy danh sách, không phải cách đọc lại một biến `List` đã có. Nếu muốn dùng lại cùng dữ liệu đã đọc, lưu danh sách kết quả vào biến cục bộ và xử lý biến đó.

## 7. Ranh giới callback và ranh giới transaction khác nhau

Hai phạm vi cần được phân biệt:

| Phạm vi | Điều được quản lý |
| --- | --- |
| Lần gọi callback | Khi nào được dùng fluent query do repository cung cấp |
| Transaction, session hoặc cursor | Khi nào các tài nguyên cần cho việc đọc dữ liệu còn hợp lệ |

Một callback có thể chạy trong transaction đã được mở từ service. Khi callback trả về, transaction của service có thể vẫn tiếp tục cho đến khi phương thức service hoàn tất.

Ngược lại, chỉ vì callback đã tạo được một đối tượng kết quả không có nghĩa mọi tài nguyên mà kết quả cần sẽ còn sống sau khi phương thức repository hoặc transaction kết thúc.

Với `List<Customer>` từ `all()`, danh sách phần tử của thao tác lấy dữ liệu đã được nhận khi nhánh đồng bộ trả về. Điều đó không có nghĩa toàn bộ đồ thị quan hệ lazy của từng entity đã được nạp. Nếu truy cập quan hệ hoặc thuộc tính lazy sau khi persistence context đóng, hành vi phụ thuộc cơ chế của store và có thể phát sinh lỗi hoặc truy vấn bổ sung khi còn ngữ cảnh phù hợp.

Một cách kiểm soát đầu ra là ánh xạ những thuộc tính cần dùng sang DTO thuần dữ liệu trong service khi tài nguyên còn hợp lệ. Việc chọn DTO không tự giải quyết mọi truy vấn dư thừa; cần thiết kế phần dữ liệu được nạp cho đúng nhu cầu.

`@Transactional(readOnly = true)` cũng không đồng nghĩa với cam kết tự động có snapshot cố định hoặc mọi lời gọi sẽ dùng một câu lệnh duy nhất. Ngữ nghĩa cụ thể cần được hiểu theo transaction manager, store và mức isolation.

## 8. Stream là kết quả, nhưng có thể còn giữ tài nguyên

Một `Stream<T>` trả từ thao tác fluent `stream()` là kết quả được API thiết kế để xử lý tuần tự. Nó khác đối tượng fluent query. Tuy vậy, stream có thể gắn với cursor, connection hoặc session và cần được đóng.

Không suy luận rằng toàn bộ dữ liệu đã được đọc chỉ vì `q.stream()` được gọi trong callback. Tùy implementation, việc mở truy vấn và đọc từng phần tử có thể diễn ra ở các thời điểm khác nhau. Phần tiêu thụ stream cần diễn ra trong phạm vi tài nguyên thích hợp.

### Ví dụ đọc stream trong service giao dịch

Ví dụ sau dành cho bối cảnh store đồng bộ có hỗ trợ streaming và transaction tương ứng, chẳng hạn cấu hình JPA phù hợp:

```java
import java.util.function.Consumer;
import java.util.stream.Stream;

import org.springframework.data.domain.Example;
import org.springframework.data.domain.ExampleMatcher;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerExportService {

    private final CustomerRepository repository;

    public CustomerExportService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public void exportActiveCustomers(Consumer<CustomerRow> sink) {
        Customer probe = new Customer();
        probe.setActive(true);

        Example<Customer> example = Example.of(
                probe,
                ExampleMatcher.matchingAll()
                        .withIgnoreNullValues()
                        .withIgnorePaths("id", "createdAt", "version"));

        try (Stream<Customer> customers = repository.findBy(
                example,
                q -> q.sortBy(Sort.by("id"))
                        .stream())) {

            customers.forEach(customer ->
                    sink.accept(CustomerRow.from(customer)));
        }
    }
}
```

Phương thức service cần được gọi theo cơ chế để transaction thực sự có hiệu lực, ví dụ qua Spring proxy trong cấu hình transaction thông thường. Không coi annotation là bằng chứng đủ nếu cách gọi thực tế bỏ qua cơ chế đó.

Trong ví dụ:

1. Query được cấu hình và thao tác `stream()` được chọn bên trong callback.
2. Repository trả stream kết quả, không trả fluent query.
3. Stream được tiêu thụ khi phương thức service giao dịch còn đang chạy.
4. `try-with-resources` đóng stream cả khi xử lý thành công lẫn khi có exception.
5. Dữ liệu chuyển cho `sink` là `CustomerRow` chỉ chứa các giá trị scalar cần dùng.

Không chuyển stream sang một thread khác hoặc lưu vào field để dùng sau. Cũng không gọi `parallel()` với kỳ vọng tài nguyên truy cập dữ liệu tự trở nên an toàn cho nhiều thread.

### Trả stream khỏi service có thể làm mất phạm vi cần thiết

Một phương thức có transaction nhưng trả stream ngay lập tức có thể kết thúc transaction trước khi bên gọi bắt đầu duyệt stream. Khi đó việc đã gọi `stream()` trong callback không bảo đảm cursor hoặc session còn hợp lệ.

Nếu kiến trúc cần công bố stream ra ngoài một ranh giới, phải quy định rõ ai giữ tài nguyên, ai đóng nó và transaction bao trùm quá trình tiêu thụ như thế nào. Với API chỉ cần dữ liệu kích thước vừa phải, trả kết quả đã materialize hoặc một page thường có vòng đời dễ quản lý hơn.

## 9. Tái sử dụng hàm truy vấn, không giữ đối tượng query

Phần có thể tái sử dụng là logic cấu hình và ánh xạ. Mỗi lần gọi repository sẽ cung cấp một đối tượng query cho callback của lần đó.

```java
import java.util.List;

import org.springframework.data.domain.Sort;
import org.springframework.data.repository.query.FluentQuery.FetchableFluentQuery;

final class CustomerQueries {

    private CustomerQueries() {
    }

    static List<CustomerRow> orderedRows(
            FetchableFluentQuery<Customer> query) {

        return query
                .sortBy(Sort.by("fullName").and(Sort.by("id")))
                .all()
                .stream()
                .map(CustomerRow::from)
                .toList();
    }
}
```

Áp dụng trong một lời gọi:

```java
List<CustomerRow> rows = repository.findBy(
        example,
        CustomerQueries::orderedRows);
```

Method reference tái sử dụng công thức xử lý. Nó không chứa một query cũ; tham số `query` được cung cấp cho từng lần thực thi.

Cũng có thể dùng một `Function` không giữ trạng thái thay đổi dùng chung. Tránh để callback giữ probe của một yêu cầu trước, trạng thái tenant có thể thay đổi hoặc dữ liệu có thể bị nhiều thread sửa cùng lúc.

### Kiểm soát đầu vào của mỗi lần gọi

Matcher có thể dùng làm cấu hình nền vì các thao tác cấu hình của `ExampleMatcher` trả về matcher mới. Tuy nhiên, đối tượng probe vẫn có thể thay đổi.

Không coi `Example.of(probe, matcher)` là thao tác sao chép sâu toàn bộ probe và đồ thị liên quan. Nếu một thread sửa probe trong khi một lần truy vấn khác đang sử dụng nó, điều kiện tìm kiếm có thể không còn như mong đợi.

Cách dễ kiểm soát là tạo probe và Example mới cho mỗi yêu cầu, đồng thời tái sử dụng các cấu hình hoặc hàm không giữ trạng thái thay đổi. Một Example chỉ nên được chia sẻ khi ứng dụng thực sự bảo đảm dữ liệu nó tham chiếu không bị sửa theo cách gây xung đột.

## 10. Những đối tượng nào có thể dùng lại?

| Đối tượng | Cách dùng phù hợp |
| --- | --- |
| Cấu hình `ExampleMatcher` | Có thể dùng làm cấu hình nền, giữ giá trị mới khi cấu hình thêm |
| Giá trị `Sort` | Có thể dùng làm mô tả thứ tự khi được quản lý như cấu hình không thay đổi |
| Kiểu projection, DTO và hàm ánh xạ | Có thể tái sử dụng theo khả năng store và ứng dụng |
| Callback không giữ trạng thái thay đổi | Có thể gọi lại với query mới do từng lời gọi repository cung cấp |
| Probe có setter hoặc đồ thị mutable | Nên tạo riêng cho mỗi yêu cầu; kiểm soát mọi thay đổi nếu chia sẻ |
| `Example` tham chiếu probe | Không mặc nhiên là bản chụp sâu, bất biến của dữ liệu mẫu |
| Fluent query được cung cấp trong callback | Chỉ dùng trong lần gọi callback tương ứng |
| `Stream` từ thao tác truy vấn | Tiêu thụ trong phạm vi tài nguyên hợp lệ, dùng một lần và đóng đúng cách |
| Danh sách DTO đã materialize | Có thể truyền cho bước sau theo hợp đồng dữ liệu và cache của ứng dụng |
| Entity hoặc projection còn phụ thuộc tải lazy | Cần xem trạng thái persistence context và dữ liệu đã được nạp |

Bảng này phân biệt khả năng dùng lại cấu hình với khả năng dùng lại kết quả. Cache một danh sách DTO đã có dữ liệu là quyết định của ứng dụng về độ mới và quyền truy cập. Cache một fluent query giữ ngữ cảnh thực thi cũ lại vi phạm phạm vi sử dụng của query.

Việc gọi lại một callback stateless cũng không có nghĩa dữ liệu lần sau giống lần trước. Mỗi lần truy vấn vẫn chịu ảnh hưởng của dữ liệu hiện tại, transaction, mức isolation và cơ chế cache mà store thực sự sử dụng.

## 11. Nhánh reactive có thời điểm thực thi khác

Các ví dụ chính trong bài dùng `QueryByExampleExecutor` đồng bộ. Với API reactive tương ứng, thao tác kết thúc có thể tạo một publisher thay vì chặn để lấy ngay danh sách.

Cần phân biệt:

```text
Trong callback:
    cấu hình fluent query
    gọi thao tác lấy kết quả để tạo publisher theo API reactive
    trả publisher kết quả

Khi có subscription:
    thực hiện quá trình đọc dữ liệu theo publisher và store
```

Vì vậy, phát biểu “mọi dữ liệu bắt buộc phải được đọc xong trước khi callback trả về” không áp dụng chung cho cả reactive và streaming.

Tuy nhiên, việc một publisher được thiết kế để thực thi muộn không cho phép cất đối tượng fluent query để tự gọi ở bất cứ đâu. Callback nên trả publisher kết quả do thao tác của API tạo ra. Không dùng một hàm trì hoãn tự tạo để giữ `q` rồi truy cập lại nó sau khi phạm vi callback đã kết thúc.

Reactive transaction sử dụng ngữ cảnh phù hợp với chuỗi reactive; không coi nó giống việc giữ một transaction đồng bộ trên ThreadLocal. Subscription, hủy subscription và việc giải phóng tài nguyên phải được quản lý theo API và store reactive đang dùng.

Một publisher cũng không mặc nhiên là bộ nhớ đệm. Subscription lại có thể dẫn đến thực thi lại, tùy loại publisher và cách ứng dụng cấu hình. Đây là vấn đề khác với việc giữ lại fluent query.

## 12. Exception có thể xuất hiện ở những ranh giới khác nhau

Một lỗi cấu hình có thể được phát hiện khi dựng query, khi gọi thao tác kết thúc hoặc khi store thực sự truy cập dữ liệu. Với kết quả lazy, lỗi đọc dữ liệu còn có thể xuất hiện trong quá trình tiêu thụ.

| Loại thao tác | Vị trí lỗi cần dự tính |
| --- | --- |
| `all()`, `first()`, `one()` của nhánh đồng bộ | Trong lời gọi thao tác và quá trình repository trả kết quả |
| `page(...)` | Trong quá trình lấy dữ liệu hoặc metadata theo triển khai |
| `stream()` | Khi mở stream hoặc khi duyệt các phần tử |
| Publisher reactive | Trong quá trình dựng nếu lỗi đầu vào được kiểm tra sớm, hoặc được phát ra khi thực thi |

Do đó, một `try-catch` chỉ bao quanh việc lấy stream nhưng nằm ngoài phần duyệt stream có thể không bao phủ lỗi phát sinh khi tiêu thụ. `try-with-resources` cần bao trùm cả quá trình duyệt để tài nguyên được đóng ngay cả khi gặp lỗi.

Không diễn giải lỗi do query thoát phạm vi thành “không có dữ liệu” rồi trả danh sách rỗng. Không có kết quả và không thể thực thi truy vấn là hai trạng thái khác nhau mà service cần xử lý đúng theo hợp đồng ứng dụng.

## 13. Các lỗi thường gặp và cách điều chỉnh

| Hiện tượng | Nguyên nhân có thể gặp | Cách điều chỉnh |
| --- | --- | --- |
| Trả trực tiếp q từ findBy rồi bị từ chối | Callback trả query thay vì kết quả | Chọn thao tác kết thúc trong callback |
| Dùng Supplier trả từ callback rồi lỗi khi gọi get | Supplier giữ query đã ra ngoài phạm vi | Mỗi lần chạy công việc mới phải gọi repository mới |
| Đưa q vào CompletableFuture | Query và ngữ cảnh bị chuyển sang thread khác | Truyền đầu vào, tạo truy vấn mới trong tác vụ phù hợp |
| Gọi sortBy nhưng thứ tự không đổi | Bỏ đối tượng cấu hình được trả về | Tiếp tục chuỗi hoặc giữ biến query mới |
| Stream chỉ lỗi khi bắt đầu duyệt | Tài nguyên đã đóng hoặc lỗi được phát hiện khi đọc | Tiêu thụ và đóng stream trong phạm vi hợp lệ |
| all trả về được nhưng đọc quan hệ ở ngoài service bị lỗi | Phần tử là entity còn dữ liệu lazy | Nạp đúng dữ liệu và ánh xạ đầu ra ở phạm vi thích hợp |
| count và danh sách không khớp về thời điểm | Là các thao tác riêng, không có snapshot tự động | Thiết kế yêu cầu nhất quán theo transaction và store |
| Truy vấn của các yêu cầu ảnh hưởng nhau | Giữ probe hoặc callback có trạng thái mutable dùng chung | Tách dữ liệu từng yêu cầu và tái sử dụng hàm stateless |
| Gọi lại query vì nghĩ nó đã cache dữ liệu | Nhầm cấu hình với kết quả materialize | Lưu kết quả đã đọc nếu muốn dùng lại cùng dữ liệu |

## 14. Cách kiểm tra một thiết kế sử dụng callback

Khi viết hoặc đọc code fluent query, hãy lần theo vòng đời của từng đối tượng:

1. Probe và Example được tạo ở đâu? Có ai còn sửa chúng trong lúc truy vấn dùng chúng không?
2. Đối tượng fluent query có chỉ xuất hiện trong callback và các hàm được gọi đồng bộ bên trong callback không?
3. Callback trả danh sách, DTO, page, stream hoặc publisher kết quả, hay trả một wrapper còn giữ query?
4. Nếu kết quả còn giữ tài nguyên, quá trình tiêu thụ và đóng tài nguyên được bao trùm bởi phạm vi nào?
5. Phần được tái sử dụng là một công thức không giữ trạng thái hay một đối tượng gắn với lần thực thi trước?
6. Nếu có nhiều thao tác, yêu cầu về độ mới và tính nhất quán đã được quyết định ở tầng phù hợp chưa?

Giữ đối tượng query trong phạm vi callback giúp lời gọi repository có điểm thực thi rõ ràng. Tái sử dụng cấu hình, hàm truy vấn và kiểu kết quả giúp giảm lặp mà vẫn tạo ngữ cảnh mới cho từng lần gọi. Với kết quả streaming hoặc reactive, cần tiếp tục quản lý vòng đời tài nguyên theo chính loại kết quả đó, thay vì coi việc callback trả về là dấu hiệu mọi truy cập dữ liệu đã hoàn tất.
