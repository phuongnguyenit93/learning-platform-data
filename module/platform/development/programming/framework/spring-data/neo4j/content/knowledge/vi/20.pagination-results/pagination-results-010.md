# Quản lý tài nguyên khi đọc kết quả lớn hoặc dạng luồng

Một truy vấn Neo4j có thể trả về vài chục bản ghi hoặc hàng triệu bản ghi. Nếu ứng dụng luôn dùng `List<T>` rồi giữ toàn bộ kết quả trong bộ nhớ, lượng heap tiêu thụ tăng theo số lượng và kích thước object được ánh xạ. Khi nhiều request chạy đồng thời, việc tải quá nhiều dữ liệu còn làm tăng thời gian phản hồi, số kết nối bị chiếm dụng và nguy cơ hết bộ nhớ.

Spring Data Neo4j (SDN) cung cấp nhiều cách đọc dữ liệu theo nhu cầu: `Page`, `Slice`, `List` kết hợp `Pageable`, `Stream`, `Flux` và `Window` để cuộn qua các nhóm kết quả. Mỗi cách có chi phí và vòng đời tài nguyên khác nhau. Chọn đúng kiểu kết quả giúp ứng dụng kiểm soát lượng dữ liệu được tải, thời gian giữ cursor/transaction và khả năng tiếp tục xử lý khi tập dữ liệu lớn.

## 1. Vì sao đọc toàn bộ kết quả có thể tốn tài nguyên?

Giả sử ứng dụng cần xuất danh sách phim đã phát hành. Repository có phương thức:

```java
List<Movie> findByStatus(String status);
```

Khi gọi `findByStatus("PUBLISHED")`, SDN trả về toàn bộ kết quả trong một collection. Với tập dữ liệu nhỏ, cách này đơn giản và dễ dùng. Với hàng trăm nghìn phim, ứng dụng có thể phải giữ hàng trăm nghìn entity và các relationship đã ánh xạ cùng lúc.

Các chi phí chính gồm:

- **Heap của JVM:** mỗi node, relationship, collection và object phụ trợ đều chiếm bộ nhớ.
- **Mạng:** nhiều record và property phải truyền từ Neo4j tới ứng dụng.
- **Ánh xạ object:** SDN phải chuyển record thành entity hoặc projection.
- **Kết nối và transaction:** truy vấn dạng cursor có thể giữ tài nguyên cho tới khi được tiêu thụ hoặc đóng.
- **Cạnh tranh tài nguyên:** nhiều truy vấn lớn đồng thời có thể gây áp lực lên connection pool, database và garbage collector.

Quản lý kết quả lớn không chỉ là giảm số object được trả về. Cần quyết định cách chia kết quả, thời gian giữ tài nguyên và cách xử lý từng phần dữ liệu.

## 2. Chọn kiểu kết quả phù hợp

SDN hỗ trợ các kiểu kết quả chính sau cho việc đọc nhiều bản ghi:

| Kiểu trả về | Cách lấy dữ liệu | Metadata | Khi nên dùng |
|---|---|---|---|
| `List<T>` | Tải toàn bộ kết quả | Không có thông tin phân trang | Tập kết quả nhỏ, có giới hạn rõ |
| `Page<T>` | Tải một trang theo offset | Có tổng số phần tử và số trang; có thể cần count query | Giao diện cần hiển thị tổng số trang |
| `Slice<T>` | Tải một lát kết quả, thường thêm một phần tử để kiểm tra còn trang tiếp theo | Biết có phần tiếp theo hay không | Giao diện chỉ cần nút Tiếp theo |
| `List<T>` + `Pageable` | Chỉ tải phạm vi được yêu cầu | Không tạo metadata Page và không cần count query tương ứng | Cần một nhóm kết quả có giới hạn |
| `Stream<T>` | Đọc tuần tự qua cursor hoặc theo lô tùy driver và cách tiêu thụ | Không có tổng số trang | Xử lý tuần tự một lượt và có thể đóng stream |
| `Flux<T>` | Phát kết quả theo luồng reactive, theo nhu cầu downstream | Không có tổng số trang | Ứng dụng dùng reactive stack và cần backpressure |
| `Window<T>` | Lấy từng nhóm và tiếp tục bằng `ScrollPosition` | Có vị trí để lấy nhóm kế tiếp | Batch job hoặc duyệt tập dữ liệu lớn theo từng cửa sổ |

Không có kiểu kết quả nào phù hợp cho mọi trường hợp. Ví dụ, `Page` thuận tiện cho giao diện cần tổng số trang nhưng count query có thể tốn kém. `Stream` giúp xử lý tuần tự nhưng phải quản lý vòng đời tài nguyên. `Window` thích hợp khi cần chia công việc thành các batch có thể tiếp tục từ vị trí trước.

## 3. Phân trang bằng Pageable

Giả sử entity `Movie` có `code`, `title`, `releaseYear` và `status`. Repository có thể khai báo truy vấn theo trạng thái:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Movie")
public class Movie {
    @Id
    private String code;

    private String title;
    private Integer releaseYear;
    private String status;

    protected Movie() {
    }
}
```

`code` là định danh ổn định, duy nhất và được ứng dụng cấp. Trong Neo4j, bảo vệ quy tắc này bằng unique constraint:

```cypher
CREATE CONSTRAINT movie_code_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.code IS UNIQUE;
```

```java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface MovieRepository extends Neo4jRepository<Movie, String> {
    // Chọn một kiểu trả về phù hợp với use case.
}
```

Các method `Page`, `Slice` và `List` bên dưới là những phương án thay thế cho cùng truy vấn; Java không cho phép khai báo nhiều method chỉ khác kiểu trả về. Trong repository thực tế, chọn một chữ ký phù hợp với use case.

### Page: khi cần tổng số phần tử

Chọn `Page<Movie>` nếu giao diện cần hiển thị tổng số phần tử hoặc tổng số trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

Page<Movie> findByStatus(String status, Pageable pageable);
```

Gọi repository:

```java
import java.util.List;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    50,
    Sort.by(
        Sort.Order.asc("releaseYear"),
        Sort.Order.asc("code")
    )
);

Page<Movie> page = movieRepository.findByStatus("PUBLISHED", pageable);

List<Movie> content = page.getContent();
long total = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

Số trang bắt đầu từ `0`. `Page` cung cấp nội dung của trang hiện tại, tổng số phần tử và tổng số trang. Để tính tổng, hạ tầng có thể thực hiện thêm count query. Với truy vấn graph phức tạp hoặc tập dữ liệu lớn, count query có thể tốn đáng kể thời gian.

### Slice: khi chỉ cần biết còn dữ liệu hay không

Nếu giao diện chỉ cần biết có trang tiếp theo, dùng `Slice<Movie>`:

```java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Movie> findByStatus(String status, Pageable pageable);
```

```java
Slice<Movie> slice = movieRepository.findByStatus("PUBLISHED", pageable);

List<Movie> content = slice.getContent();
boolean hasNext = slice.hasNext();
```

`Slice` không cần biết tổng số phần tử. Hạ tầng thường đọc thêm một phần tử ngoài page size để xác định còn dữ liệu hay không. Điều này tránh count query chỉ để hiển thị nút Tiếp theo.

### List kết hợp Pageable: lấy một đoạn mà không cần metadata

Nếu service chỉ cần một nhóm kết quả có giới hạn, có thể trả về `List<Movie>` cùng `Pageable`:

```java
import java.util.List;
import org.springframework.data.domain.Pageable;

List<Movie> findByStatus(String status, Pageable pageable);
```

Hạ tầng chỉ lấy phạm vi mà `Pageable` yêu cầu, không tạo object `Page` và không cần count query tương ứng. Cách này phù hợp với một batch đơn giản, nhưng ứng dụng phải tự quản lý số trang hoặc offset nếu muốn lấy tiếp.

### Luôn sắp xếp ổn định

Khi phân trang, hãy chỉ định thứ tự rõ ràng. Nếu chỉ sắp xếp theo `releaseYear`, nhiều phim có thể cùng năm phát hành và thứ tự giữa chúng không được xác định duy nhất. Khi chuyển từ trang này sang trang khác, dữ liệu có thể lặp hoặc bị bỏ qua nếu thứ tự thay đổi.

Thêm một khóa duy nhất làm tiêu chí phụ, ví dụ `code`:

```java
Sort sort = Sort.by(
    Sort.Order.asc("releaseYear"),
    Sort.Order.asc("code")
);
```

Thứ tự ổn định giúp phân trang dễ dự đoán hơn. Tuy nhiên, nếu dữ liệu được thêm, xóa hoặc thay đổi trong lúc người dùng chuyển trang, kết quả giữa các lần gọi vẫn có thể thay đổi. Nếu cần duyệt dữ liệu lớn trong khi có ghi đồng thời, hãy cân nhắc keyset scrolling hoặc một quy tắc snapshot/checkpoint phù hợp.

## 4. Giới hạn kết quả bằng Top, First và Limit

Nếu chỉ cần một số lượng tối đa cố định, có thể dùng `Top` hoặc `First` trong tên phương thức:

```java
import java.util.List;
import java.util.Optional;

List<Movie> findTop20ByStatusOrderByReleaseYearDescCodeAsc(String status);

Optional<Movie> findFirstByStatusOrderByReleaseYearDescCodeAsc(String status);
```

Trong các phiên bản Spring Data hỗ trợ `Limit`, có thể truyền giới hạn động:

```java
import org.springframework.data.domain.Limit;

List<Movie> findByStatus(String status, Limit limit);
```

Ví dụ:

```java
List<Movie> newest = movieRepository.findByStatus(
    "PUBLISHED",
    Limit.of(20)
);
```

`Top`/`First` phù hợp khi giới hạn là một phần cố định của nghiệp vụ; `Limit` phù hợp khi số lượng cần lấy thay đổi theo lời gọi. Không kết hợp `Pageable` với `Sort` hoặc `Limit` trong cùng method vì `Pageable` đã chứa thông tin sắp xếp và giới hạn. Khả năng cụ thể phụ thuộc phiên bản Spring Data Neo4j/Spring Data Commons đang dùng.

## 5. Scrolling bằng Window

Phân trang offset rất dễ hiểu, nhưng càng đi tới trang sâu, database có thể phải bỏ qua nhiều kết quả trước khi trả về đoạn cần lấy. Spring Data hỗ trợ scrolling để duyệt từng `Window<T>` và dùng `ScrollPosition` lấy phần kế tiếp.

Repository khai báo method trả về một cửa sổ có tối đa 100 phim:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

Window<Movie> findFirst100ByStatusAndReleaseYearIsNotNullOrderByReleaseYearAscCodeAsc(
    String status,
    ScrollPosition position
);
```

Dùng `WindowIterator` để duyệt lần lượt:

```java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.support.WindowIterator;

WindowIterator<Movie> movies = WindowIterator
    .of(position -> movieRepository
        .findFirst100ByStatusAndReleaseYearIsNotNullOrderByReleaseYearAscCodeAsc(
            "PUBLISHED",
            position
        ))
    .startingAt(ScrollPosition.keyset());

while (movies.hasNext()) {
    Movie movie = movies.next();
    process(movie); // Xử lý một phim trong batch hiện tại.
}
```

`WindowIterator` tự gọi repository để lấy cửa sổ kế tiếp khi cần. Mỗi cửa sổ chỉ chứa một nhóm kết quả, nên ứng dụng không phải giữ toàn bộ tập phim trong bộ nhớ.

### Offset scrolling

Offset scrolling dùng vị trí dạng số, gần với phân trang truyền thống. Ví dụ:

```java
import org.springframework.data.domain.OffsetScrollPosition;
import org.springframework.data.domain.Window;

Window<Movie> findFirst100ByStatusOrderByCodeAsc(
    String status,
    OffsetScrollPosition position
);
```

Offset scrolling giảm lượng dữ liệu truyền về ứng dụng trong mỗi lần gọi, nhưng database vẫn có thể phải materialize nhiều kết quả rồi bỏ qua phần trước offset. Khi offset rất lớn, chi phí này tăng lên.

### Keyset scrolling

Keyset scrolling ghi nhớ giá trị của các trường sắp xếp ở phần tử cuối cùng của cửa sổ hiện tại. Khi lấy cửa sổ tiếp theo, điều kiện truy vấn được mở rộng để bắt đầu sau bộ khóa đó. Cách này tránh phải bỏ qua một offset rất lớn.

Keyset scrolling cần chú ý:

- Các property dùng để sắp xếp phải không null. Giá trị null có thể làm điều kiện so sánh không xác định và gây bỏ sót kết quả.
- Nên có index phù hợp với điều kiện lọc và các trường sắp xếp.
- Các trường sắp xếp phải được trả về và ánh xạ trong entity hoặc projection để Spring Data xác định vị trí tiếp tục.
- Spring Data bổ sung khóa chính vào keyset để phân biệt các kết quả có cùng giá trị sắp xếp.
- Dùng thứ tự ổn định và hạn chế thay đổi các trường sắp xếp trong lúc job đang chạy.

Trong ví dụ trên, `releaseYear` và `code` cần có giá trị cho mọi phim thuộc tập kết quả. Nếu `releaseYear` có thể null, hãy chọn một trường khác không null hoặc chuẩn hóa dữ liệu trước khi dùng keyset.

## 6. Đọc tuần tự bằng Stream

`Stream<T>` phù hợp khi cần xử lý từng kết quả trong một lượt, chẳng hạn xuất dữ liệu, tính toán tổng hợp hoặc gửi bản ghi sang một hệ thống khác. SDN có thể sử dụng cursor/driver streaming thay vì tạo một `List` chứa toàn bộ kết quả.

Repository:

```java
import java.util.stream.Stream;

Stream<Movie> findByStatus(String status);
```

Tiêu thụ stream trong service:

```java
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieExportService {
    private final MovieRepository movieRepository;

    public MovieExportService(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }

    @Transactional(readOnly = true)
    public void exportPublishedMovies() {
        try (Stream<Movie> movies =
                 movieRepository.findByStatus("PUBLISHED")) {
            movies.forEach(this::writeRecord);
        }
    }

    private void writeRecord(Movie movie) {
        // Ghi từng bản ghi ra đích xuất dữ liệu.
    }
}
```

Hai quy tắc bắt buộc:

1. **Đóng stream:** stream có thể giữ cursor và tài nguyên của driver. Dùng `try-with-resources` để đóng ngay cả khi xử lý phát sinh exception.
2. **Tiêu thụ trong transaction phù hợp:** giữ stream trong ranh giới service có `@Transactional(readOnly = true)` để quá trình đọc diễn ra trong cùng transaction. Không trả stream ra khỏi service rồi để controller hoặc tác vụ khác tiêu thụ sau khi transaction đã kết thúc.

Không nên giữ stream mở trong khi chờ người dùng, gọi dịch vụ ngoài lâu hoặc thực hiện công việc không liên quan. Một stream đang mở có thể giữ transaction và kết nối lâu hơn cần thiết. Với công việc có thời gian xử lý dài, chia thành `Window` hoặc batch có thể giúp giải phóng tài nguyên giữa các lượt.

Không dùng `parallel()` trên stream được cấp bởi repository nếu chưa hiểu rõ giới hạn của cursor, transaction và thread-bound context. Hãy tiêu thụ tuần tự trong transaction; nếu cần xử lý song song, chuyển từng batch hữu hạn sang một cơ chế xử lý có giới hạn concurrency sau khi đã đóng/giải phóng phần đọc tương ứng.

## 7. Reactive streaming bằng Flux

Nếu ứng dụng dùng reactive stack, repository có thể kế thừa `ReactiveNeo4jRepository` và trả về `Flux<T>`:

```java
import org.springframework.data.neo4j.repository.ReactiveNeo4jRepository;
import reactor.core.publisher.Flux;

public interface ReactiveMovieRepository
        extends ReactiveNeo4jRepository<Movie, String> {

    Flux<Movie> findByStatus(String status);
}
```

`Flux` là publisher phát ra không, một hoặc nhiều kết quả. Việc truy vấn và tiêu thụ diễn ra khi publisher được subscribe. Reactive Streams hỗ trợ backpressure: downstream điều khiển lượng phần tử mà nó yêu cầu, giúp điều tiết tốc độ giữa nguồn dữ liệu và consumer.

Ví dụ xử lý từng batch 200 phim, tuần tự gọi một writer reactive:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveMovieExportService {
    private final ReactiveMovieRepository repository;
    private final MovieBatchWriter batchWriter;

    public ReactiveMovieExportService(
            ReactiveMovieRepository repository,
            MovieBatchWriter batchWriter) {
        this.repository = repository;
        this.batchWriter = batchWriter;
    }

    public Mono<Void> exportPublishedMovies() {
        return repository.findByStatus("PUBLISHED")
            .buffer(200)
            .concatMap(batchWriter::write)
            .then();
    }
}
```

Trong ví dụ, `MovieBatchWriter.write(List<Movie>)` trả về `Mono<Void>`; interface có thể được khai báo như sau:

```java
import java.util.List;
import reactor.core.publisher.Mono;

public interface MovieBatchWriter {
    Mono<Void> write(List<Movie> batch);
}
```

`buffer(200)` giữ tối đa một batch 200 phần tử trước khi chuyển tiếp; `concatMap` xử lý từng batch theo thứ tự và chỉ chuyển sang batch kế tiếp sau khi batch hiện tại hoàn tất. Cách này giới hạn số object được gom trong mỗi batch.

Không gọi `collectList()` trên một luồng có thể rất lớn nếu mục tiêu là tiết kiệm bộ nhớ, vì thao tác đó gom toàn bộ kết quả thành một `List`. Tránh gọi `subscribe()` tùy tiện bên trong service; hãy trả publisher cho WebFlux hoặc thành phần ở biên ứng dụng để nó quản lý subscription, lỗi và vòng đời xử lý.

Reactive repository và imperative repository sử dụng hạ tầng khác nhau. Dùng `ReactiveNeo4jRepository`, `ReactiveNeo4jClient` và reactive transaction manager trong luồng reactive; không chỉ đổi kiểu trả về của một repository imperative từ `List` sang `Flux`.

Nếu nhiều thao tác Neo4j trong cùng pipeline cần một transaction, dùng reactive transaction manager và giữ các thao tác trong cùng Reactor chain để transaction context được truyền tiếp. Tránh gọi `block()` hoặc tách publisher khỏi chain trong WebFlux. Với job lớn, cân nhắc transaction theo từng batch để không giữ một transaction và connection quá lâu cho toàn bộ quá trình.

## 8. Neo4jClient: imperative và reactive

`Neo4jClient` là lớp truy cập query mức thấp hơn, phù hợp khi cần tự viết Cypher và ánh xạ record theo ý muốn. Hai biến thể có hành vi khác nhau:

- `Neo4jClient` imperative: `.fetch().all()` thực thi query và trả về một collection; do đó vẫn có thể tải toàn bộ kết quả vào bộ nhớ.
- `ReactiveNeo4jClient`: `.fetch().all()` trả về `Flux`; query chỉ được thực thi khi publisher được subscribe và kết quả có thể được tiêu thụ theo nhu cầu.

Ví dụ reactive client:

```java
import java.util.Map;

import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import reactor.core.publisher.Flux;

public class MovieQueryService {
    private final ReactiveNeo4jClient client;

    public MovieQueryService(ReactiveNeo4jClient client) {
        this.client = client;
    }

    public Flux<Map<String, Object>> findPublishedRows() {
        return client.query("""
                MATCH (m:Movie {status: $status})
                RETURN m.code AS code,
                       m.title AS title,
                       m.releaseYear AS releaseYear
                ORDER BY m.releaseYear, m.code
                """)
            .bind("PUBLISHED").to("status")
            .fetch()
            .all();
    }
}
```

Query chỉ trả về các trường cần dùng thay vì toàn bộ node và graph lân cận. Điều này giảm khối lượng dữ liệu truyền và công việc ánh xạ. Publisher của reactive client chỉ nên được subscribe một lần theo vòng đời truy vấn; nếu cần kết quả nhiều lần, hãy tạo query/publisher mới theo cách phù hợp.

## 9. Quản lý transaction, connection và batch

Các cách đọc theo luồng thường giữ tài nguyên lâu hơn một truy vấn trả về `List` đã hoàn tất. Khi thiết kế job đọc lớn, hãy cân nhắc:

1. **Giới hạn thời gian xử lý mỗi phần:** đọc một batch, xử lý, ghi checkpoint hoặc kết quả, rồi tiếp tục.
2. **Không giữ connection trong lúc chờ:** tránh gọi dịch vụ mạng chậm hoặc đợi thao tác tương tác trong khi cursor đang mở.
3. **Giới hạn concurrency:** nhiều stream hoặc Flux chạy đồng thời có thể chiếm connection pool và làm tăng tải Neo4j.
4. **Chọn kích thước batch theo dữ liệu thực tế:** batch lớn giảm số lần gọi nhưng tăng heap; batch nhỏ giảm bộ nhớ nhưng tăng round trip.
5. **Tách đọc và xử lý khi cần:** nếu xử lý từng record tốn nhiều thời gian, có thể đọc một window nhỏ, đóng lượt đọc rồi xử lý batch riêng.
6. **Đặt transaction đúng phạm vi:** dùng read-only transaction cho luồng chỉ đọc; nếu mỗi batch có thao tác ghi, cân nhắc transaction theo batch thay vì giữ một transaction rất dài cho toàn bộ job.

Không có kích thước batch tối ưu cho mọi ứng dụng. Hãy đo thời gian truy vấn, heap, số connection đang sử dụng và thời gian xử lý từng batch trong môi trường gần với production.

## 10. Tối ưu truy vấn trước khi tăng kích thước batch

Phân trang không làm một truy vấn graph kém chọn lọc trở nên rẻ. Trước khi tăng page size hoặc batch size, hãy kiểm tra truy vấn:

- Lọc theo thuộc tính có tính chọn lọc và có index phù hợp, chẳng hạn `status` hoặc `code`.
- Chỉ trả về property cần thiết; dùng projection khi không cần toàn bộ entity.
- Tránh tải relationship sâu hoặc nhiều nhánh không được sử dụng.
- Sắp xếp theo tập trường ổn định và có thể tận dụng index.
- Dùng `EXPLAIN` để xem kế hoạch và `PROFILE` để đo operator, số hàng trung gian và DB hits.
- Với keyset scrolling, tạo index phù hợp với các trường lọc/sắp xếp và kiểm tra query plan.

Ví dụ tạo index cho bộ lọc theo trạng thái và năm phát hành:

```cypher
CREATE INDEX movie_status_release_year_code IF NOT EXISTS
FOR (m:Movie) ON (m.status, m.releaseYear, m.code);
```

Index trên chỉ là điểm bắt đầu. Hãy kiểm tra kế hoạch thực thi với dữ liệu thật; index không đảm bảo mọi truy vấn đều dùng nó hoặc mọi thứ tự sắp xếp đều được phục vụ tối ưu.

## 11. Chọn chiến lược theo tình huống

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Trang danh sách cần tổng số trang | `Page<T>` | Có `totalElements` và `totalPages` |
| Trang danh sách chỉ cần nút tiếp theo | `Slice<T>` | Tránh count query chỉ để biết còn dữ liệu |
| Một batch hữu hạn, không cần metadata | `List<T>` + `Pageable` | Lấy đúng phạm vi cần xử lý |
| Xuất tuần tự một tập kết quả, consumer xử lý nhanh | `Stream<T>` trong transaction và try-with-resources | Không cần gom toàn bộ kết quả vào List |
| WebFlux hoặc pipeline reactive | `Flux<T>` với backpressure | Điều tiết nhu cầu giữa nguồn và consumer |
| Job duyệt hàng triệu bản ghi, cần checkpoint | `Window<T>` với keyset scrolling | Chia thành nhóm và tiếp tục từ khóa cuối |
| Truy vấn tùy chỉnh chỉ trả vài cột | Projection hoặc reactive `Neo4jClient` | Giảm payload và chi phí ánh xạ |

Với tác vụ chạy lâu, keyset scrolling theo từng window thường dễ chia batch, ghi checkpoint và retry hơn một stream giữ cursor mở liên tục. Với giao diện người dùng, `Page` hoặc `Slice` thường dễ tích hợp hơn. Với pipeline reactive, dùng `Flux` xuyên suốt thay vì chuyển qua lại giữa reactive và imperative.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| JVM tăng heap khi xuất dữ liệu | Dùng `List` hoặc `collectList()` cho toàn bộ kết quả | Dùng `Stream`, `Flux` hoặc `Window` theo từng phần |
| Connection bị giữ lâu | Stream chưa được đóng hoặc consumer xử lý quá chậm | Dùng try-with-resources, rút ngắn thời gian xử lý trong lúc cursor mở |
| Truy vấn trang sâu ngày càng chậm | Offset lớn phải bỏ qua nhiều kết quả | Cân nhắc keyset scrolling với thứ tự ổn định và index phù hợp |
| Count query làm trang phản hồi chậm | `Page` cần tổng số phần tử | Dùng `Slice` nếu không cần tổng số trang |
| Bản ghi lặp hoặc bị bỏ qua giữa các trang | Sắp xếp không ổn định hoặc dữ liệu thay đổi trong khi duyệt | Thêm khóa phụ duy nhất và chọn chiến lược snapshot/checkpoint phù hợp |
| Keyset scrolling bỏ sót dữ liệu | Trường sắp xếp có giá trị null hoặc không được trả về | Dùng trường không null và bảo đảm sort fields được ánh xạ |
| Reactive pipeline giữ quá nhiều object | Dùng `collectList`, `flatMap` concurrency quá lớn hoặc buffer quá rộng | Dùng backpressure, batch giới hạn và `concatMap` khi cần tuần tự |
| Reactive query không chạy | Publisher chưa được subscribe | Trả publisher tới thành phần tiêu thụ hoặc subscribe ở biên ứng dụng |
| Transaction đóng trước khi stream được đọc hết | Stream được trả khỏi service transaction | Tiêu thụ stream bên trong phương thức service có transaction |

## 13. Quy trình triển khai đọc dữ liệu lớn

1. Ước lượng số lượng bản ghi, kích thước mỗi entity và số relationship cần ánh xạ.
2. Xác định giao diện cần metadata tổng số hay chỉ cần biết còn kết quả.
3. Chọn `Page`, `Slice`, `List + Pageable`, `Stream`, `Flux` hoặc `Window` theo cách tiêu thụ.
4. Đặt thứ tự ổn định; với keyset, bảo đảm sort fields không null và có index phù hợp.
5. Giới hạn property và relationship được tải bằng projection khi có thể.
6. Đặt transaction, đóng stream và giới hạn concurrency đúng cách.
7. Chọn kích thước page/window/batch dựa trên số liệu đo.
8. Kiểm tra heap, connection pool, thời gian truy vấn và kế hoạch `PROFILE`.
9. Thử trường hợp consumer lỗi giữa chừng, dữ liệu thay đổi và job phải chạy tiếp từ checkpoint.

## 14. Tự kiểm tra

1. Vì sao `List<Movie>` có thể gây áp lực heap khi truy vấn trả về hàng trăm nghìn node?
2. Khác biệt giữa `Page` và `Slice` là gì? Khi nào count query được thực hiện?
3. Vì sao `List<Movie>` kết hợp `Pageable` có thể phù hợp hơn `Page<Movie>` cho một batch nội bộ?
4. Vì sao phải đóng `Stream<T>` bằng try-with-resources?
5. Tại sao nên tiêu thụ stream bên trong transaction thay vì trả stream ra khỏi service?
6. Reactive `Flux` giúp điều tiết dữ liệu bằng backpressure như thế nào?
7. Vì sao `collectList()` có thể làm mất lợi ích quản lý bộ nhớ của reactive streaming?
8. Khác biệt giữa offset scrolling và keyset scrolling là gì?
9. Những điều kiện nào cần được bảo đảm cho keyset properties?
10. Khi nào nên dùng `Window` theo batch thay vì giữ một stream mở trong suốt job?

## Tài liệu tham khảo

- [Spring Data Neo4j — Paging, Iterating Large Results, Sorting & Limiting](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j — Scrolling](https://docs.spring.io/spring-data/neo4j/reference/repositories/scrolling.html)
- [Spring Data Neo4j — Repository Query Return Types](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-return-types-reference.html)
- [Spring Data Neo4j — Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
