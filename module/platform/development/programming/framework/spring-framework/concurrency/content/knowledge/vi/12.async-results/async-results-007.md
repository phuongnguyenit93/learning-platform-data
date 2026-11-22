# Trả về dữ liệu độc lập với tài nguyên đã đóng

## 1. Vấn đề: Future hoàn tất không có nghĩa tài nguyên còn mở

Trong Spring Framework, một tác vụ chạy qua `@Async`, `AsyncTaskExecutor` hoặc `CompletableFuture` có thể đọc database, tệp, HTTP response hay stream rồi trả kết quả cho caller. Điều dễ sai là **trả chính đối tượng còn phụ thuộc vào tài nguyên đang mở**: `ResultSet`, `InputStream`, JPA entity chứa lazy association, hoặc một `Stream` đọc dữ liệu theo yêu cầu.

Ví dụ: tác vụ đọc database trong transaction, trả một entity, kết thúc transaction; caller sau đó gọi `entity.getItems()`. Nếu `items` chưa được khởi tạo và persistence context không còn khả dụng, thao tác có thể ném `LazyInitializationException`. Tương tự, một `BufferedReader` được trả ra sau `try-with-resources` đã đóng reader không còn đọc tiếp được.

**Nguyên tắc:** tại thời điểm hoàn tất kết quả bất đồng bộ, dữ liệu được trả về phải **có quyền sở hữu và vòng đời độc lập** với những tài nguyên mà task đã đóng, trừ khi API chủ đích chuyển giao quyền sở hữu tài nguyên và định nghĩa rõ ai phải đóng nó.

Bất biến cần đạt với kết quả thông thường:

```text
worker mở tài nguyên
      |
      v
đọc đủ các giá trị cần thiết
      |
      v
chuyển thành dữ liệu sở hữu độc lập (DTO / value object / immutable copy)
      |
      v
đóng tài nguyên trong finally / try-with-resources
      |
      v
Future hoàn tất với DTO
      |
      v
caller dùng DTO: không truy cập lại tài nguyên đã đóng
```

Từ khóa là **độc lập với vòng đời**, không nhất thiết mọi dữ liệu phải là `String` hay `record`. Một DTO có thể chứa danh sách, map, giá trị thời gian và object con, miễn là không lén giữ JDBC cursor, JPA proxy chưa khởi tạo, session, stream hay đối tượng mutable đang bị task khác sửa.

## 2. Phân biệt dữ liệu thuần và handle gắn với tài nguyên

| Thứ muốn trả qua Future | Phụ thuộc vòng đời sau khi worker rời scope? | Cách xử lý phù hợp |
| --- | --- | --- |
| `String`, `long`, `BigDecimal`, `Instant` | Thông thường không | Trả trực tiếp nếu giá trị đã được tính xong |
| `record ReportDto(...)` chỉ chứa giá trị độc lập | Không, nếu các trường cũng độc lập | Trả DTO; sao chép collection/array mutable khi cần |
| `List<ReportDto>` đã materialize | Không phụ thuộc DB nếu phần tử là DTO độc lập | Có thể dùng `List.copyOf` để giữ cấu trúc bất biến |
| JPA entity có `LAZY` relationship | Có thể cần persistence context khi truy cập trường chưa load | Truy xuất và map thành DTO bên trong transaction |
| Hibernate proxy / `PersistentCollection` | Có thể cần session hoặc bị ảnh hưởng bởi detach | Không trả như kết quả dữ liệu đã hoàn tất |
| `java.sql.ResultSet` / `Statement` | Phụ thuộc statement/connection còn mở | Duyệt `ResultSet` và map thành giá trị trước khi đóng |
| `InputStream`, `Reader`, `Stream<T>` gắn file/DB | Phụ thuộc nguồn còn mở và thứ tự đọc | Materialize có giới hạn hoặc thiết kế streaming sở hữu tài nguyên rõ |
| `byte[]` mới được copy độc lập | Không phụ thuộc stream gốc, nhưng mutable | Cân nhắc defensive copy, dung lượng và quyền sửa |
| `Path` hoặc ID file trong object storage | Là locator, không phải handle đang mở | Có thể trả locator; nơi dùng phải tự mở nguồn mới và xử lý file thay đổi/xóa |
| `InputStreamResource` bao một stream đã mở | Có thể single-use, phụ thuộc stream sống | Không trả rồi đóng stream trước khi framework đọc |

**Không đánh đồng “object còn tồn tại trên heap” với “object vẫn sử dụng được”.** Java garbage collector giữ object còn được tham chiếu, nhưng không tự kéo dài transaction, database cursor, file descriptor hoặc HTTP connection mà object cần.

Một JPA entity đã detach **không nhất thiết luôn lỗi**: các thuộc tính đơn giản và association đã được tải có thể vẫn đọc được. Vấn đề là API phụ thuộc ngầm vào việc attribute nào đã fetch, session nào còn mở và người dùng gọi getter ở thời điểm nào. DTO rõ ràng giúp loại bỏ sự phụ thuộc khó kiểm soát đó.

## 3. Ranh giới thời gian và thread trong Spring concurrency

Giả sử controller gọi bean async và nhận `CompletableFuture<ReportDto>`:

```text
HTTP/caller thread                        Thread của reportExecutor
------------------                        -----------------------
request -> async proxy
           |
           +-- submit task ---------------> @Async method bắt đầu
           |                                      |
           |                                mở transaction riêng
           |                                      |
           |                                JPA query, lấy trường cần
           |                                      |
           |                                map ReportEntity -> ReportDto
           |                                      |
           |                                transaction kết thúc
           |                                      |
           |                             Future hoàn tất với ReportDto
           |
caller nhận handle  <------------------ kết quả sẵn sàng để get/join
           |
         get() / compose
           |
     dùng ReportDto độc lập
```

**Điểm quan trọng:** giao dịch imperative của Spring dùng `PlatformTransactionManager` thường được gắn với thread hiện tại. Transaction của HTTP caller **không tự truyền** sang thread worker chỉ vì `@Async` trả Future. Do đó truy vấn và mapping cần nằm trong một transactional boundary **thực sự chạy trên worker** (thông qua một lời gọi được Spring transactional advice áp dụng).

`Future.get()` của JDK cung cấp quan hệ *happens-before* giúp caller nhìn thấy các ghi dữ liệu trước khi task hoàn tất, nhưng **không mở lại transaction hay hồi sinh tài nguyên đã đóng**. Đừng dùng memory visibility để giải quyết lỗi lifetime.

Có hai ranh giới độc lập phải giải quyết:

1. **Concurrency boundary**: nhiều thread có thể truy cập cùng object → cần immutable snapshot hoặc đồng bộ phù hợp.
2. **Resource boundary**: tài nguyên mở trong phạm vi nào, ai đóng, ai còn quyền dùng → cần hoàn tất materialization hoặc chuyển ownership rõ ràng.

## 4. Ví dụ sai: trả JPA entity rồi mới truy cập lazy relationship

Đoạn sau là **mã minh họa trong ứng dụng Spring Data JPA**, không phải Java độc lập:

```java
@Service
public class BadAsyncReportService {
    private final ReportRepository repository;

    public BadAsyncReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @Async("reportExecutor")
    public CompletableFuture<ReportEntity> loadAsync(long id) {
        // Giả sử repository trả entity có collection LAZY.
        ReportEntity report = repository.findById(id).orElseThrow();
        return CompletableFuture.completedFuture(report);
    }
}
```

Caller:

```java
ReportEntity entity = reports.loadAsync(7L).get();
int count = entity.getItems().size(); // Có thể lỗi nếu collection chưa load.
```

Ở đây `findById` có thể chạy với transactional boundary do repository áp dụng; sau khi boundary kết thúc, association LAZY chưa load thường không còn được truy cập an toàn. Có hệ thống bật Open Session in View hoặc có cấu hình session khác làm lỗi **tạm thời không xuất hiện**; đó không phải một hợp đồng tốt cho kết quả bất đồng bộ. Đặc biệt, persistence context của request thread cũng không tự trở thành persistence context của worker.

Lỗi khác là trả `Stream<ReportEntity>` từ repository sau khi transaction truy vấn đã đóng. Stream có thể cần cursor/connection khi caller duyệt. Trả reference tới Stream chưa được tiêu thụ **không giống** trả danh sách dữ liệu đã hoàn tất.

## 5. Mẫu đúng: transactional reader tạo DTO trước khi rời scope

Thay vì đưa entity ra khỏi phạm vi quản lý persistence, hãy chuyển tất cả dữ liệu cần dùng sang một DTO độc lập **trước khi transaction kết thúc**.

Giả sử domain có `ReportEntity`, `ReportItem`, `ReportRepository`; đoạn dưới là **các lớp tích hợp Spring mang tính mẫu**, đặt trong các tệp Java và import phù hợp, không phải chương trình tự chạy bằng JDK thuần.

```java
public record ReportDto(
        long id,
        String ownerName,
        java.util.List<String> itemNames) {

    public ReportDto {
        itemNames = java.util.List.copyOf(itemNames);
    }
}
```

```java
@Service
public class ReportSnapshotReader {
    private final ReportRepository repository;

    public ReportSnapshotReader(ReportRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public ReportDto loadSnapshot(long id) {
        ReportEntity entity = repository.findById(id).orElseThrow();

        // Các getter có thể kích hoạt LAZY fetch: thực hiện bên trong
        // transactional boundary trên thread đang đọc.
        String owner = entity.getOwner().getName();
        java.util.List<String> names = entity.getItems().stream()
                .map(ReportItem::getName)
                .toList();

        return new ReportDto(entity.getId(), owner, names);
    }
}
```

```java
@Service
public class AsyncReportService {
    private final ReportSnapshotReader reader;

    public AsyncReportService(ReportSnapshotReader reader) {
        this.reader = reader;
    }

    @Async("reportExecutor")
    public CompletableFuture<ReportDto> loadAsync(long id) {
        // Chạy trên worker; gọi sang bean reader qua Spring proxy.
        ReportDto value = reader.loadSnapshot(id);
        return CompletableFuture.completedFuture(value);
    }
}
```

Yêu cầu để mẫu hoạt động đúng:

- Có `@EnableAsync`, bean executor `reportExecutor`, Spring Data JPA và transaction management được cấu hình phù hợp.
- `ReportSnapshotReader` và `AsyncReportService` **là hai Spring-managed beans khác nhau**, được inject theo constructor. Nhờ vậy, lời gọi `reader.loadSnapshot(id)` từ worker có thể đi qua proxy `@Transactional`. Tránh `this.loadSnapshot(id)` trong cùng bean ở proxy mode vì self-invocation có thể bỏ qua advice.
- Các liên kết lazy cần dùng được truy cập/mapped khi transaction còn hoạt động. Nếu mô hình quan hệ nhiều tầng, chọn fetch plan, entity graph, projection hoặc truy vấn DTO thích hợp để tránh N+1 queries và tải quá nhiều dữ liệu.
- DTO chứa `long`, `String` và một danh sách `String` copy bất biến; nó không mang `EntityManager`, `Session` hoặc entity proxy ra ngoài transaction.
- `CompletableFuture.completedFuture(value)` được tạo **bên trong worker** sau khi reader đã tính xong. Spring async proxy trả handle cho caller; không có nghĩa caller buộc chạy method đồng bộ.

`@Transactional(readOnly = true)` là một chính sách giao dịch/read-only hint; nó **không tự biến entity thành immutable DTO**, cũng không thay thế việc mapping. Nếu mapping bất cẩn chép một `List<ReportEntity>` vào DTO, kết quả vẫn có thể chứa phụ thuộc vào session và state mutable.

## 6. Ví dụ Java 17+ chạy độc lập: kết quả sống lâu hơn reader

Để chứng minh mà không cần database thật, ví dụ dưới đây dùng `BufferedReader` đóng bởi `try-with-resources` và `ExecutorService` trả `Future`. Trường hợp tốt **đọc hết dữ liệu và trả record độc lập**; trường hợp sai **trả một reader đã bị đóng trong worker**.

Tạo tệp `DetachedDataDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class DetachedDataDemo {

    public record Snapshot(long id, String title, List<String> lines) {
        public Snapshot {
            lines = List.copyOf(lines); // Bản sao cấu trúc bất biến.
        }
    }

    static Snapshot readSnapshot() throws IOException {
        try (BufferedReader reader =
                     new BufferedReader(new StringReader("alpha\nbeta\n"))) {
            List<String> rows = new ArrayList<>();
            String line;
            while ((line = reader.readLine()) != null) {
                rows.add(line);
            }
            return new Snapshot(7L, "Q4", rows);
        } // reader đã đóng; Snapshot vẫn dùng được.
    }

    static BufferedReader brokenReader() throws IOException {
        BufferedReader reader =
                new BufferedReader(new StringReader("unread"));
        try (reader) {
            return reader; // Sai: Java đóng reader trước khi trả kết quả.
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<Snapshot> good = pool.submit(DetachedDataDemo::readSnapshot);
            Snapshot value = good.get(); // Worker đã hoàn tất và reader đã đóng.
            System.out.println("snapshot = " + value.id() + "/" + value.title());
            System.out.println("lines = " + String.join(",", value.lines()));

            try {
                value.lines().add("gamma");
                System.out.println("immutable = false");
            } catch (UnsupportedOperationException ex) {
                System.out.println("immutable = true");
            }

            Future<BufferedReader> bad =
                    pool.submit(DetachedDataDemo::brokenReader);
            try {
                bad.get().readLine();
                System.out.println("closed reader fails = false");
            } catch (IOException ex) {
                System.out.println("closed reader fails = true");
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac DetachedDataDemo.java
java DetachedDataDemo
```

Stdout xác định:

```text
snapshot = 7/Q4
lines = alpha,beta
immutable = true
closed reader fails = true
```

**Giải thích:**

1. `readSnapshot()` mở reader bên trong worker, duyệt hết các dòng thành `ArrayList<String>`, tạo `Snapshot` với `List.copyOf`, rồi đóng reader tự động khi ra khỏi `try`.
2. Caller nhận `Snapshot` qua `Future.get()`. Lúc này không còn cần reader: dữ liệu nằm trong `String` và cấu trúc danh sách độc lập.
3. `List.copyOf` ngăn các thao tác thay đổi cấu trúc danh sách đã trả; ví dụ `add` ném `UnsupportedOperationException`. Vì phần tử là `String` bất biến, snapshot ở đây không chứa tham chiếu tới dữ liệu mutable bên ngoài.
4. `brokenReader()` trả reference tới reader nằm trong `try-with-resources`, nhưng Java đóng nó **trước khi caller nhận kết quả**. Sau `bad.get()`, `readLine()` ném `IOException`.
5. `Future.get()` đồng bộ hoàn tất phép tính nhưng **không giữ nguồn dữ liệu mở**. Chính điều này khiến hai nhánh có kết quả khác nhau.

Trong ví dụ, `StringReader` chỉ mô phỏng vòng đời của stream; code thật có thể là `Files.newBufferedReader`, `InputStream` từ HTTP hoặc một JDBC cursor. Quy tắc ownership vẫn như nhau. Trong production, shutdown executor nên theo vòng đời của ứng dụng/bean, không dừng pool dùng chung sau mỗi request.

## 7. Một lỗi tương tự với JDBC ResultSet

`java.sql.ResultSet` phụ thuộc vào `Statement` và `Connection`. Đoạn sau **sai về thiết kế**:

```java
public ResultSet loadRows(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT id, name FROM report")) {
        return statement.executeQuery(); // ResultSet phụ thuộc statement.
    } // Statement và Connection được đóng.
}
```

Đây là **mảnh Java JDBC**, cần import `javax.sql.DataSource` và các lớp `java.sql`; không phải chương trình độc lập. Việc trả về `ResultSet` không chuyển quyền sở hữu connection cho caller: `try-with-resources` đóng các resource ngay khi thoát scope.

Cách đúng là tạo dữ liệu kết quả ngay bên trong scope:

```java
public List<ReportRow> loadRows(DataSource ds) throws SQLException {
    List<ReportRow> rows = new ArrayList<>();

    try (Connection connection = ds.getConnection();
         PreparedStatement statement =
                 connection.prepareStatement("SELECT id, name FROM report");
         ResultSet rs = statement.executeQuery()) {

        while (rs.next()) {
            rows.add(new ReportRow(rs.getLong("id"), rs.getString("name")));
        }
    }
    return List.copyOf(rows);
}

public record ReportRow(long id, String name) {}
```

Đây là **mảnh minh họa**, cần `ArrayList`, `List`, JDBC imports và các khai báo trong cấu trúc Java hợp lệ. Khi code trả về, connection, statement và result set đã đóng; chỉ còn danh sách các giá trị `long` và `String`. Tránh quên đóng `ResultSet` trong mã dùng JDBC trực tiếp dù statement thường quản lý nó.

Khi bảng có hàng triệu dòng, **không materialize vô hạn**. Cân nhắc phân trang, chunking, ghi tệp có quản lý, hoặc stream dữ liệu trong đúng scope tài nguyên đang mở với cơ chế backpressure.

## 8. Vì sao Stream<T> đặc biệt dễ gây hiểu lầm?

`Stream<T>` trong Java mô tả một *pipeline có thể tính lười*, không phải một collection đã được đọc đầy đủ. Một stream từ `List<String>` thuần có thể không cần I/O, nhưng stream từ JPA repository, JDBC, file hoặc HTTP body có thể dựa trên connection/cursor/reader mở.

```java
// Mảnh minh họa: KHÔNG trả stream DB ra khỏi transactional scope.
@Transactional(readOnly = true)
public Stream<ReportEntity> streamReports() {
    return repository.streamAllReports();
}
```

Nếu caller gọi `stream.forEach(...)` sau khi transaction đã kết thúc, tài nguyên có thể không còn sử dụng được. Ngay cả khi stream còn hoạt động, người dùng phải biết ai có nghĩa vụ `close()`, khi nào transaction kết thúc và có được phép truy cập stream từ thread khác không.

Hai mô hình an toàn hơn:

- **Materialize có giới hạn:** mở nguồn, duyệt, map thành DTO và thu vào `List<DTO>` **trước khi transaction kết thúc**; đóng stream nếu API yêu cầu.
- **Stream thật có kiểm soát:** toàn bộ quá trình mở nguồn → đọc từng phần → ghi tới destination → đóng nguồn diễn ra trong một callback/hàm có ownership rõ ràng, không trả stream đang mở về caller chỉ để caller đọc sau.

Đừng nghĩ `stream.toList()` tự xử lý mọi vấn đề: nó chỉ giải quyết **tính lười và materialization** nếu được gọi khi nguồn còn mở; các phần tử thu được vẫn có thể là entity/proxy còn phụ thuộc session. Cần map phần tử thành dữ liệu độc lập trước khi đưa vào danh sách trả về.

## 9. Trả kết quả qua CompletableFuture: giá trị phải sẵn sàng trước khi complete

Nếu tự dùng JDK `CompletableFuture.supplyAsync`, hãy tạo giá trị **bên trong tác vụ** rồi mới return:

```java
CompletableFuture<ReportDto> future =
        CompletableFuture.supplyAsync(
                () -> reportReader.loadSnapshot(reportId),
                executor
        );
```

Đây là **mảnh mã tích hợp** giả định `reportReader` là bean đã được inject, `reportId` là ID và `executor` là `java.util.concurrent.Executor` đã có. Nếu `loadSnapshot` được Spring quản lý transaction qua proxy, việc gọi nó trong lambda sẽ mở boundary trên worker. Nếu tự truy vấn JDBC thay vì gọi reader bean, lambda nên sở hữu tài nguyên và trả DTO sau khi `try-with-resources` kết thúc.

Ngược lại, không nên tạo Future từ một resource sẽ bị đóng trước khi xử lý tiếp:

```java
InputStream input = openInput();
try (input) {
    return CompletableFuture.supplyAsync(() -> parse(input), executor);
}
// Sai: input có thể bị đóng ngay khi method trên caller trả về,
// trong khi worker vẫn chưa bắt đầu parse.
```

Đây là **mã minh họa sai về ownership**, không phải phương thức độc lập; `openInput`, `parse`, `executor` cần được định nghĩa trong ứng dụng thật. Cách sửa: để `openInput()` xảy ra **bên trong** supplier và đóng ngay trong supplier sau khi parse, hoặc đọc dữ liệu đủ nhỏ thành snapshot độc lập **trước** khi submit.

`CompletableFuture.completedFuture(value)` không làm value được detach tự động: nếu `value` là một entity chứa lazy proxy hoặc một stream đã đóng, Future vẫn hoàn tất với chính object không an toàn đó.

## 10. Chuyển ownership tài nguyên: ngoại lệ có chủ đích

Không phải hệ thống nào cũng nên nạp toàn bộ dữ liệu vào RAM rồi trả DTO. Với file lớn hoặc video, streaming là hợp lý, nhưng phải thiết kế **ai mở, ai đọc, ai đóng**.

Ví dụ Spring MVC `StreamingResponseBody` (mảnh mã controller, cần imports, bean `exports` và cấu hình Spring Web MVC):

```java
@GetMapping("/exports/{id}")
public ResponseEntity<StreamingResponseBody> download(@PathVariable long id) {
    StreamingResponseBody body = output -> {
        // Mở nguồn TRONG callback thực hiện streaming.
        try (InputStream input = exports.open(id)) {
            input.transferTo(output);
        }
        // Không đóng output của framework tại đây.
    };

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .body(body);
}
```

Trong Spring MVC, callback viết response body có thể chạy sau khi controller method đã trả về và thường được xử lý qua async infrastructure. Việc mở nguồn **trong callback** bảo đảm stream được mở khi thực sự cần đọc. Cần cấu hình MVC async executor và timeout phù hợp, cùng chính sách khi client ngắt kết nối.

Sai lầm thường gặp là mở `InputStream` trong controller rồi đóng nó khi controller trả, trong khi callback mới bắt đầu đọc sau đó. Cũng không nên cho callback dùng trực tiếp một `EntityManager` hoặc transaction đã tồn tại ở HTTP caller thread: callback cần tự tạo ranh giới tài nguyên/transaction phù hợp.

Đây là **streaming với ownership rõ**, khác với trường hợp trả một DTO đã materialize. Các mẫu khác như trả locator tới object storage, URL có hạn dùng, hoặc ID của kết quả đã lưu bền vững cũng tách được quyền sở hữu nhưng cần xử lý version, TTL và tính sẵn có tại thời điểm caller sử dụng.

## 11. Dữ liệu đầu vào cũng có vòng đời

Bài toán không chỉ xảy ra với **kết quả trả về**; input truyền từ request sang tác vụ async cũng có thể phụ thuộc vào scope đã kết thúc.

Ví dụ không nên mặc định an toàn:

```java
// Mảnh minh họa trong HTTP controller:
executor.execute(() -> parse(request.getInputStream()));
```

`request` và stream request được servlet container quản lý theo lifecycle xử lý HTTP; task có thể chỉ bắt đầu sau khi response đã hoàn tất. Muốn xử lý bất đồng bộ, hãy copy dữ liệu cần thiết (có giới hạn dung lượng) trước khi rời request scope, hoặc lưu payload vào kho bền vững rồi gửi **ID bất biến** cho worker. `MultipartFile` tạm và các stream thuộc request cũng cần quy tắc tương tự.

Ví dụ cách truyền dữ liệu nhỏ có chủ đích:

```java
byte[] payload = request.getInputStream().readAllBytes();
byte[] snapshot = payload.clone();
executor.execute(() -> process(snapshot));
```

Đây là **mảnh tích hợp**, không phải hướng dẫn đọc upload không giới hạn vào RAM. Trong thực tế phải giới hạn kích thước và validate input trước, tránh truyền mảng mutable cho nhiều writer; có thể thay `byte[]` bằng một value object/DTO. Với payload lớn, lưu ra tệp/object storage hoặc hàng đợi và truyền reference có lifecycle kiểm soát.

Một lỗi tương tự: gửi entity đang gắn với persistence context của caller cho worker và mong worker gọi lazy getter được, hoặc mong `@Transactional` ở caller tự truyền transaction sang worker. Với Spring imperative transactions, đó không phải bảo đảm hợp lệ.

## 12. Độ bất biến: List.copyOf chỉ là bước đầu

DTO không chứa resource đã đóng mới giải quyết một nửa vấn đề. Nửa còn lại là tránh trạng thái mutable bị sửa đồng thời sau khi Future trả kết quả.

`List.copyOf(source)` tạo danh sách **không cho sửa cấu trúc**, nhưng là *shallow copy*: nếu phần tử là `MutableReportLine` có trường thay đổi được, caller khác vẫn có thể sửa phần tử và ảnh hưởng người đọc. Tương tự, Java `record` không tự deep copy `List`, `Map`, mảng hoặc custom mutable object.

Ví dụ cần defensive copy đối với `byte[]`:

```java
public final class DocumentBytes {
    private final byte[] content;

    public DocumentBytes(byte[] content) {
        this.content = content.clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
```

Đây là **class độc lập** (cần lưu `DocumentBytes.java` nếu chạy riêng), minh họa rằng cả đầu vào constructor lẫn đầu ra accessor đều phải được copy nếu không muốn caller có quyền sửa mảng nội bộ. Với file rất lớn, copy lặp có thể đắt: ưu tiên mô hình ownership theo phần, buffer có lifetime rõ, hoặc locator tới tệp đã lưu.

Thực hiện đầy đủ:

1. Chỉ chọn các trường mà caller thật sự cần.
2. Map thành giá trị độc lập khi tài nguyên còn sống.
3. Copy collection/map/mảng và các phần tử mutable khi có yêu cầu chia sẻ an toàn.
4. Đóng resource trước hoặc trong quá trình hoàn tất boundary, truyền ra ngoài chỉ dữ liệu kết quả.
5. Kiểm soát kích thước kết quả để tránh OOM hoặc tạo backlog lớn trong executor.

## 13. Kết quả lớn: đừng đổi lỗi resource-closed lấy OutOfMemoryError

Một `List.copyOf` chứa vài trăm item là chuyện khác với truy vấn vài triệu row hoặc đọc tệp nhiều GB. Nếu materialize vô hạn, một tác vụ có thể chiếm heap, gây GC dài và làm giảm throughput của toàn bộ `ThreadPoolTaskExecutor`.

Các chiến lược khi dữ liệu lớn:

| Cần làm gì? | Thiết kế phù hợp | Điều kiện cần |
| --- | --- | --- |
| Trả vài trăm record | DTO/record với danh sách giới hạn | Có pagination/limit rõ |
| Trả báo cáo lớn nhưng có thể download | Worker ghi kết quả ra tệp/object storage, Future trả ID/URI | Có lifecycle/TTL/version/ACL; không trả stream đã đóng |
| Gửi từng phần qua HTTP | Streaming response mở resource trong callback | Timeout, client disconnect, executor và backpressure |
| Xử lý hàng triệu row trong batch | Paging/chunking trong scope transaction ngắn; ghi output theo phần | Checkpoint, retry/idempotency, memory bound |
| Đọc file theo cursor | Một đối tượng quản lý lifetime và quyền đóng cursor có API rõ | Caller nhận trách nhiệm đóng; không nhầm với DTO đã hoàn tất |

Với kết quả lưu bền vững, Future có thể trả `ExportReady(fileId, size, checksum)` thay vì `InputStream`. Khi caller cần đọc file, service mở một stream **mới** dựa trên locator. Độc lập resource không nhất thiết đồng nghĩa dữ liệu luôn tồn tại: file có thể bị xóa hoặc thay phiên bản; do đó cần xử lý not-found, TTL, object version, kiểm tra quyền truy cập và retry.

## 14. Lỗi và hủy tác vụ ảnh hưởng ra sao tới đóng resource?

Một mẫu resource ownership đúng phải làm việc cả khi **task thất bại**, **timeout** hoặc **cancel**:

- **Success:** tạo đủ DTO, đóng resource, complete Future với giá trị.
- **Exception:** `try-with-resources` đóng resource; Future hoàn tất exceptional. Caller lấy nguyên nhân qua `get()`/`ExecutionException.getCause()` hoặc `CompletableFuture.handle/exceptionally`.
- **Caller `get(timeout)` hết thời hạn:** đây chỉ là timeout của **lượt chờ**, task vẫn có thể chạy và giữ resource. Không tự giả định tài nguyên đã đóng.
- **`future.cancel(true)`:** Future thử yêu cầu ngắt worker nếu implementation hỗ trợ; không bảo đảm một JDBC call hoặc thao tác I/O lập tức dừng. Resource nên được đóng ở `finally` khi code thực sự thoát scope.
- **`cancel(false)`:** Future có thể chuyển trạng thái hủy nhưng task đang chạy vẫn có thể tiếp tục; không xem `isDone()` là bằng chứng mọi resource đã được giải phóng.
- **Task bị từ chối ngay khi submit:** resource **không nên được mở trước rồi bỏ mặc** nếu việc gửi thất bại. Tốt nhất mở resource bên trong task sau khi được executor nhận.

Trong JDK, `Future.get()` tạo quan hệ đồng bộ kết quả; còn `CompletableFuture.cancel(...)` theo hợp đồng implementation không sử dụng interruption để điều khiển công việc. Vì vậy đừng đặt đóng tài nguyên phụ thuộc duy nhất vào `isCancelled()`: phải dựa vào `try-with-resources`/`finally` và thiết kế dừng hợp tác.

Lưu ý chi tiết: `close()` cũng có thể ném exception. Nếu task đã tạo DTO nhưng đóng resource thất bại trên đường thoát `try-with-resources`, Future có thể **hoàn tất bằng lỗi** thay vì trả DTO, tùy cách xử lý exception. Tránh nuốt lỗi đóng resource nếu nó có ý nghĩa với tính toàn vẹn công việc.

## 15. Cách kiểm tra kết quả thực sự độc lập

Một kiểm thử tốt cần **đọc dữ liệu sau khi scope tài nguyên đã đóng** chứ không chỉ assert khi transaction đang mở.

Kịch bản gợi ý cho một service `loadAsync(id)`:

1. Tạo dữ liệu thử có association LAZY và collection cần đọc, chạy task qua executor thực (không chỉ gọi target method trực tiếp).
2. `Future.get()` đợi task đã hoàn tất. Nếu dùng Spring JPA, kiểm tra service đã rời method transactional trước lúc đánh giá kết quả.
3. Ở caller **không có persistence context phục vụ việc đọc**, truy cập mọi trường của DTO, duyệt collection, serialize JSON. Không được cần thêm query hoặc mở session mới ngầm.
4. Kiểm tra danh sách, map, array không bị thay đổi khi object gốc hoặc collection gốc bị sửa sau đó.
5. Với JDBC/file, dùng test fake có cờ `closed` hoặc thực sự đóng resource rồi xác nhận caller vẫn đọc được DTO.
6. Thử nhánh exception/cancellation/timeout; kiểm tra `close` chạy đúng và không rò rỉ connection/file descriptor.
7. Thử kích thước gần giới hạn, concurrency nhiều task, heap và thời gian queue để phát hiện phản ứng xấu khi materialize số lượng lớn.

Nếu ứng dụng có Open Session in View, hãy cân nhắc tắt nó trong bài kiểm tra boundary hoặc chủ động xác nhận truy vấn/serialization không xảy ra sau khi service đã tạo DTO; nếu không, session mở ở request có thể che một bug lazy-loading. Đừng khẳng định chỉ cần test `@Transactional` trên test method là đủ: transaction của test có thể làm dữ liệu trông hợp lệ trong khi production đã đóng scope.

## 16. Những lỗi thiết kế thường gặp

1. **Trả `ResultSet` ra khỏi `try-with-resources`.** Statement/connection đã đóng, ResultSet không còn hợp đồng sử dụng hợp lệ.
2. **Trả JPA entity có LAZY association qua Future.** Caller có thể truy cập khi session/transaction đã kết thúc.
3. **Tạo DTO nhưng field vẫn là entity hoặc PersistentCollection.** “Đổi tên kiểu ngoài cùng” không tạo snapshot độc lập.
4. **Trả `Stream<T>` rồi mới định duyệt ở caller.** Stream có thể cần connection/file chưa được duy trì và đóng đúng cách.
5. **Tưởng Future giữ transaction sống tới lúc `get()`.** Future chỉ giữ handle kết quả/trạng thái; không quản lý transaction lifecycle.
6. **Dùng `@Transactional` ở HTTP caller và cho rằng worker dùng chung transaction.** Imperative transaction mặc định gắn với thread; phải tạo boundary đúng trong worker.
7. **Tự gọi `this.readTransactional()` bên trong cùng bean.** Trong proxy mode mặc định có thể bỏ qua transactional advice; tách bean và gọi qua proxy.
8. **Chỉ serialize JPA entity sau khi Future kết thúc.** Serializer có thể đụng getter LAZY trong lúc session đã đóng.
9. **Mở `InputStream` trong caller rồi đóng trước khi worker/callback dùng.** Đưa thao tác mở/đóng về scope chủ sở hữu thực sự.
10. **Tin rằng `List.copyOf` deep-copy mọi phần tử.** Nó không copy nội dung mutable bên trong.
11. **Đọc mọi bản ghi vào RAM để tránh lazy.** Có thể gây OOM; cần limit, pagination, chunking hoặc streaming có kiểm soát.
12. **Đọc request body hoặc `MultipartFile` trên worker sau khi request scope kết thúc.** Không giả định tài nguyên do servlet/container quản lý còn mở.
13. **Đánh đồng `cancel(true)` với đóng connection ngay lập tức.** Hủy có tính hợp tác, cần `finally` và chính sách timeout downstream.
14. **Trả file path rồi coi file không thể thay đổi.** Locator độc lập với stream, nhưng vẫn cần quản lý quyền, version và thời gian tồn tại.
15. **Không kiểm thử sau khi tài nguyên đã đóng.** Test chỉ chạy trong transaction thường bỏ sót lỗi xuất hiện ở caller khác thread.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Task `@Async` trả `Future<ReportEntity>`; caller `get()` thành công nhưng `entity.getItems()` sau đó ném lỗi. Vì sao?  
**Đáp án:** Future đã hoàn tất nhưng association LAZY vẫn phụ thuộc persistence context/session không còn dùng được. Cần map dữ liệu cần thiết thành DTO trong transactional scope của worker.

**Câu 2.** Nếu `ResultSet` được trả từ method trong `try(Connection c=...)`, caller có nên tiếp tục `rs.next()`?  
**Đáp án:** Không. `ResultSet` có vòng đời phụ thuộc Statement/Connection; nên đọc hết hoặc chia trang trong scope rồi trả giá trị độc lập.

**Câu 3.** `Future.get()` có kéo dài vòng đời của `InputStream` mà task đã đóng không?  
**Đáp án:** Không. Nó chỉ đợi/nhận trạng thái kết quả và tạo quan hệ đồng bộ bộ nhớ.

**Câu 4.** `record ReportDto(List<MutableItem> items)` với `List.copyOf(items)` có bất biến sâu không?  
**Đáp án:** Không. Danh sách không thể thay đổi cấu trúc, nhưng từng `MutableItem` vẫn có thể bị sửa nếu chia sẻ tham chiếu.

**Câu 5.** File 4 GB cần được phục vụ qua HTTP. Nên trả một `byte[]` 4 GB từ Future không?  
**Đáp án:** Thường không. Ưu tiên trả locator tới nguồn lưu bền vững hoặc streaming với ownership mở/đóng và giới hạn tài nguyên rõ ràng.

**Câu 6.** Trong Spring MVC streaming, nên mở `InputStream` trước khi controller trả về hay trong callback `StreamingResponseBody`?  
**Đáp án:** Thường mở trong callback thực sự tiêu thụ dữ liệu, rồi đóng khi callback kết thúc; không giả định stream mở trước đó vẫn sống.

**Câu 7.** Task bị `get(timeout)` timeout. Có thể khẳng định JDBC connection đã được đóng không?  
**Đáp án:** Không. Worker có thể còn đang chạy; phải có deadline, chính sách hủy hợp tác và `try-with-resources`/`finally` để giải phóng đúng thời điểm.

**Kết luận:** hãy để tác vụ bất đồng bộ **sở hữu và đóng** các resource mà nó mở, rồi trả về **một giá trị đã hoàn tất, độc lập và an toàn để dùng ở thread khác**. Nếu dữ liệu quá lớn để materialize, hãy chuyển sang thiết kế có **ownership rõ ràng** cho streaming hoặc tệp lưu bền vững; đừng chuyển ngầm một cursor/stream/session đã hết hạn qua `Future`.

### Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling (@Async, Future)](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Declarative Transaction Management, thread-bound transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Data JPA — DTO and projection queries](https://docs.spring.io/spring-data/jpa/reference/repositories/projections.html)
- [Spring Framework — StreamingResponseBody](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/StreamingResponseBody.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java SE 17 — BufferedReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
