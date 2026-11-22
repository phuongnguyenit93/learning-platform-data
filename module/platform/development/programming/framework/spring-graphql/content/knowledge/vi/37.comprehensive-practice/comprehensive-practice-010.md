# Đo observation của DataLoader

DataLoader giúp gom nhiều lần tải dữ liệu quan hệ thành một batch, nhưng chỉ nhìn vào code `load()` hoặc số query GraphQL chưa đủ để biết batching có thực sự hiệu quả hay không. Cần đo số lần batch được dispatch, thời gian xử lý, kết quả thành công/thất bại và kích thước dữ liệu được tải.

Spring for GraphQL tích hợp Micrometer Observation để quan sát GraphQL request, DataFetcher và DataLoader. Từ Spring for GraphQL 1.4.0, instrumentation bổ sung observation tên `graphql.dataloader`. Observation này bao phủ các lần gọi `@BatchMapping` và DataLoader được đăng ký thủ công. Bài thực hành sẽ tạo một quan hệ Book–Author, gửi query lấy nhiều sách cùng tác giả, rồi kiểm tra metric và trace để xác nhận batch loading hoạt động.

## 1. Mục tiêu đo lường

Giả sử client lấy 10 quyển sách và yêu cầu thông tin tác giả của từng quyển. Nếu mỗi field `Book.author` gọi repository riêng, server có thể thực hiện:

- Một truy vấn lấy danh sách sách.
- Mười truy vấn lấy từng tác giả.

Đây là N+1 select problem. DataLoader trì hoãn các lần `load(authorId)` trong cùng GraphQL execution, gom key và gọi batch loader một lần hoặc theo nhiều batch tùy giới hạn.

Sau bài thực hành, cần trả lời được:

1. DataLoader nào đang được gọi?
2. Mỗi GraphQL request tạo bao nhiêu batch observation?
3. Một batch mất bao lâu?
4. Batch thành công hay thất bại?
5. Batch trả về bao nhiêu phần tử?
6. Trên trace, batch observation nằm ở đâu trong GraphQL request?
7. Dữ liệu quan sát có chứng minh database chỉ chạy một câu SQL hay không?

Câu hỏi cuối rất quan trọng: observation đo lần thực thi batch loader. Nếu code bên trong batch loader vẫn gọi repository từng key, trace vẫn có thể chỉ có một batch observation nhưng database vẫn chạy N câu SQL. Cần đối chiếu thêm SQL log hoặc database metrics.

## 2. Điều kiện phiên bản

DataLoader observation được Spring for GraphQL bổ sung từ phiên bản `1.4.0`. Vì vậy, hãy dùng Spring for GraphQL 1.4 trở lên. Với Spring Boot, chọn dòng dependency management tương thích, chẳng hạn Spring Boot 3.5 trở lên hoặc Spring Boot 4.x.

Ở các phiên bản Spring for GraphQL trước 1.4, có thể đã có `graphql.request` và `graphql.datafetcher`, nhưng chưa có observation chuyên biệt `graphql.dataloader`. Nếu metric này không xuất hiện, hãy kiểm tra phiên bản thư viện trước khi tự viết instrumentation.

Spring Boot tự cấu hình `ObservationRegistry` và `GraphQlObservationInstrumentation` khi observability infrastructure có trên classpath và có `ObservationRegistry`. GraphQL Boot starter phát hiện các bean `Instrumentation` để thêm vào GraphQL runtime. Trong ứng dụng Spring Boot thông thường, không cần tự tạo instrumentation lần thứ hai.

## 3. Thêm dependency Micrometer và Actuator

Dùng Spring Boot dependency management để chọn phiên bản tương thích:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Vai trò của từng dependency:

- `spring-boot-starter-graphql` cung cấp GraphQL server và integration với GraphQL Java.
- `spring-boot-starter-actuator` cung cấp Micrometer Observation infrastructure và endpoint để đọc metrics.
- `micrometer-registry-prometheus` xuất meter sang định dạng Prometheus.
- `spring-graphql-test` cung cấp công cụ kiểm thử GraphQL execution.

Nếu chỉ muốn kiểm tra metric trong Actuator, có thể dùng meter registry phù hợp đã được ứng dụng cấu hình. Nếu muốn xem trace, cần thêm Micrometer Tracing bridge và exporter tương ứng với backend quan sát đang sử dụng, ví dụ OpenTelemetry với OTLP. Metrics và tracing là hai đầu ra khác nhau của cùng Observation API.

## 4. Cấu hình Actuator và Prometheus

Mở các endpoint cần dùng trong `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus

  endpoint:
    health:
      show-details: never

  metrics:
    distribution:
      percentiles-histogram:
        graphql.dataloader: true
~~~

`metrics` cho phép đọc một meter cụ thể qua Actuator. `prometheus` xuất các meter dưới dạng Prometheus scrape format. Histogram giúp backend Prometheus tính phân vị và phân bố thời gian thay vì chỉ nhìn trung bình.

Chỉ expose các endpoint cần thiết và bảo vệ chúng theo môi trường triển khai. Không mở endpoint metrics hoặc Prometheus công khai nếu chúng tiết lộ thông tin vận hành nội bộ.

## 5. Observation được tạo ở đâu?

Spring for GraphQL có ba nhóm observation chính:

| Observation | Phạm vi đo | Khi nào hữu ích |
| --- | --- | --- |
| `graphql.request` | Toàn bộ GraphQL execution | Tổng thời gian và outcome của request |
| `graphql.datafetcher` | Một data fetching operation không tầm thường | Tìm field resolver chậm |
| `graphql.dataloader` | Một lần batch loading được dispatch | Đo hiệu quả DataLoader |

Property fetcher mặc định chỉ đọc thuộc tính Java từ source object được xem là thao tác tầm thường, nên không nhất thiết tạo `graphql.datafetcher` observation.

Từ Spring for GraphQL 1.4, các data fetching operation chỉ chuyển tiếp việc tải dữ liệu qua DataLoader không còn tạo `graphql.datafetcher` observation riêng như trước. Thay vào đó, batch loading có `graphql.dataloader` observation. Điều này giúp trace phản ánh công việc thực sự xảy ra ở batch loader và giảm số span lặp theo từng phần tử.

## 6. Các key của graphql.dataloader

Default convention tạo các key sau:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| `graphql.loader.name` | Low | Tên DataLoader đang được dùng |
| `graphql.outcome` | Low | Kết quả `SUCCESS` hoặc `ERROR` |
| `graphql.error.type` | Low | Tên class của lỗi nếu batch thất bại |
| `graphql.loader.size` | High | Kích thước danh sách phần tử được load |

Low-cardinality key có tập giá trị hữu hạn, phù hợp làm metric tag. High-cardinality key có thể có rất nhiều giá trị khác nhau; key này được đưa vào trace nhưng không dùng làm metric tag mặc định.

Vì vậy, `graphql.loader.size` giúp xem kích thước batch trên trace. Đừng mong đợi Actuator metrics hoặc Prometheus có một time series riêng cho từng kích thước batch mặc định. Cách phân tách này bảo vệ hệ thống metrics khỏi việc tạo quá nhiều time series.

`graphql.loader.size` là kích thước danh sách giá trị được DataLoader load/trả về. Với loader ánh xạ một key sang một entity, con số này thường gần bằng số key duy nhất. Tuy nhiên, nếu key trùng do cache, entity không tồn tại hoặc batch loader bỏ qua kết quả, số phần tử có thể khác số lần gọi `load()`.

## 7. Tạo schema Book–Author

Tạo schema trong `src/main/resources/graphql/book.graphqls`:

~~~graphql
type Query {
    books(limit: Int = 10): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
~~~

Một `Book` lưu `authorId` để tham chiếu đến tác giả. Field `author` là field quan hệ được resolve qua DataLoader.

Ví dụ model:

~~~java
package com.example.books.domain;

public record Book(Long id, String title, Long authorId) {
}
~~~

~~~java
package com.example.books.domain;

public record Author(Long id, String name) {
}
~~~

Application service có hai thao tác: tìm sách và tìm nhiều tác giả theo tập ID.

~~~java
package com.example.books.application;

import com.example.books.domain.Author;
import com.example.books.domain.Book;

import java.util.List;
import java.util.Map;
import java.util.Set;

import reactor.core.publisher.Mono;

public interface BookService {
    List<Book> findBooks(int limit);
}

public interface AuthorService {
    Mono<Map<Long, Author>> findByIds(Set<Long> authorIds);
}
~~~

Mỗi public interface được đặt trong file Java riêng theo tên interface. Ví dụ dùng `Mono<Map<Long, Author>>` để minh họa batch loader reactive. Nếu ứng dụng dùng JPA/JDBC đồng bộ, có thể trả `Map<Long, Author>` và dùng batch loader imperative phù hợp.

## 8. Đăng ký DataLoader và sử dụng trong SchemaMapping

Đăng ký batch loader qua `BatchLoaderRegistry`:

~~~java
package com.example.books.graphql;

import com.example.books.application.AuthorService;
import com.example.books.domain.Author;

import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;

@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findByIds(authorIds)
            );
    }
}
~~~

`BatchLoaderRegistry` đăng ký loader theo kiểu key/value và Spring tạo DataLoader theo GraphQL execution. Theo mặc định, key đăng ký dùng tên class đầy đủ của kiểu value, vì vậy controller có thể nhận DataLoader với generic type phù hợp mà không cần chỉ định tên riêng.

Controller gọi `load()` cho từng sách:

~~~java
package com.example.books.graphql;

import com.example.books.application.BookService;
import com.example.books.domain.Author;
import com.example.books.domain.Book;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

import java.util.List;
import java.util.concurrent.CompletableFuture;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument Integer limit) {
        return bookService.findBooks(limit == null ? 10 : limit);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
~~~

Các lần gọi `authorLoader.load()` được xếp hàng trong cùng execution. Khi GraphQL Java dispatch DataLoader, batch function nhận tập ID và gọi `AuthorService.findByIds` một lần cho batch đó.

Nếu muốn đơn giản hóa phần resolver, có thể dùng `@BatchMapping`. Spring for GraphQL cũng tạo DataLoader observation cho các lần gọi `@BatchMapping`, nên không bắt buộc phải đăng ký DataLoader thủ công để đo.

Ví dụ thay cho `@SchemaMapping` và `BatchLoaderRegistry` ở trên:

~~~java
package com.example.books.graphql;

import com.example.books.application.AuthorService;
import com.example.books.domain.Author;
import com.example.books.domain.Book;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findByIds(authorIds).map(authorsById -> {
            Map<Book, Author> result = new HashMap<>();
            for (Book book : books) {
                result.put(book, authorsById.get(book.authorId()));
            }
            return result;
        });
    }
}
~~~

Ví dụ dùng `Book` record nên đã có `equals` và `hashCode`, phù hợp làm key của map trong `@BatchMapping`. Chọn một trong hai cách triển khai field `Book.author` cho cùng schema; không đăng ký đồng thời cả hai resolver.

## 9. Gửi một query tạo batch

Gửi query có nhiều sách và yêu cầu tác giả:

~~~graphql
query MeasureAuthorBatch {
    books(limit: 10) {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Để kết quả dễ đọc, hãy tạo fixture có 10 sách và 10 `authorId` khác nhau. Nếu nhiều sách dùng chung một tác giả, DataLoader cache có thể gộp các key trùng; số key duy nhất khi dispatch khi đó thấp hơn số sách.

Với query này, các field `Book.author` cùng gọi một DataLoader trong một execution. Nếu tất cả key được xếp hàng trước lần dispatch và không vượt giới hạn batch size, thường sẽ có một batch observation cho loader tác giả.

Một GraphQL request có thể tạo nhiều batch observation nếu có nhiều DataLoader, nhiều đợt dispatch hoặc cấu hình `maxBatchSize` khiến tập key được chia nhỏ. Do đó, không nên mặc định mỗi request luôn có đúng một `graphql.dataloader` observation.

Có thể gửi query qua HTTP để tạo mẫu đo:

~~~bash
curl -i -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query MeasureAuthorBatch { books(limit: 10) { id title author { id name } } }"}'
~~~

## 10. Đọc metric bằng Actuator

Sau khi gửi query, xem danh sách meter:

~~~bash
curl -i http://localhost:8080/actuator/metrics
~~~

Tìm meter `graphql.dataloader`, sau đó đọc chi tiết:

~~~bash
curl -i http://localhost:8080/actuator/metrics/graphql.dataloader
~~~

Actuator trả về các phép đo như `COUNT`, `TOTAL_TIME`, `MAX` cùng danh sách tag có sẵn. `COUNT` là số lần batch observation được ghi nhận, tức số lần batch dispatch được đo; nó không phải số lần gọi `load()` và cũng không phải số key trong batch. `TOTAL_TIME` là tổng thời gian của các batch observation. `MAX` là thời gian lớn nhất trong tập quan sát của meter.

Muốn lọc theo loader, hãy xem `availableTags` để lấy giá trị thật của `graphql.loader.name`, rồi truyền tag đó:

~~~bash
curl --get "http://localhost:8080/actuator/metrics/graphql.dataloader" ^
  --data-urlencode "tag=graphql.loader.name:<loader-name>"
~~~

Thay `<loader-name>` bằng giá trị thực tế mà endpoint trả về. Với DataLoader đăng ký theo kiểu, tên có thể dựa trên class value type; với mapping hoặc registration tùy chỉnh, hãy luôn kiểm tra tag thay vì đoán.

Nếu meter không xuất hiện:

- Xác nhận Spring for GraphQL là 1.4.0 trở lên.
- Xác nhận có `ObservationRegistry`.
- Xác nhận GraphQL observation instrumentation đã được thêm vào GraphQL runtime.
- Xác nhận request thực sự gọi `DataLoader` hoặc `@BatchMapping`.
- Kiểm tra metric exporter và Actuator endpoint đã được expose.

## 11. Đọc Prometheus và tính thời gian trung bình

Khi có Prometheus registry, scrape endpoint:

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Timer có thể được xuất dưới dạng các series có hậu tố như `_count`, `_sum` và histogram buckets tùy cấu hình registry. Tên metric và label được chuyển đổi theo quy tắc naming của Prometheus.

Ví dụ minh họa:

~~~text
graphql_dataloader_seconds_count{graphql_loader_name="com.example.books.domain.Author",graphql_outcome="SUCCESS"} 25
graphql_dataloader_seconds_sum{graphql_loader_name="com.example.books.domain.Author",graphql_outcome="SUCCESS"} 0.425
~~~

Trong ví dụ này:

- `count = 25`: có 25 batch observation.
- `sum = 0.425`: tổng thời gian batch là 0,425 giây.
- Thời gian trung bình xấp xỉ `0.425 / 25 = 0.017` giây, tức 17 ms.

Đây là số liệu minh họa; label và tên meter thực tế phụ thuộc convention, registry và naming convention. Nếu bật histogram, có thể dùng bucket để theo dõi phân vị thời gian và phát hiện batch chậm ở tail latency.

## 12. Xem batch size trong trace

Metrics trả lời câu hỏi tổng hợp theo thời gian. Trace giúp xem một GraphQL request cụ thể đã tạo batch nào và batch đó chứa bao nhiêu kết quả.

Để có trace, cấu hình Micrometer Tracing cùng bridge/exporter phù hợp, ví dụ OpenTelemetry và OTLP, rồi xem trace trong backend quan sát của hệ thống.

Một trace thường có cấu trúc khái quát:

~~~text
HTTP server request
└── graphql.request
    ├── graphql.datafetcher (Query.books)
    └── graphql.dataloader
        ├── graphql.loader.name = Author
        ├── graphql.outcome = SUCCESS
        └── graphql.loader.size = 10
~~~

Tên loader và các thuộc tính hiển thị thực tế phụ thuộc convention. Điểm cần quan sát là batch span nằm bên trong GraphQL request, có outcome và batch size cụ thể. Nếu request tạo nhiều batch, trace giúp xác định chúng xảy ra ở dispatch nào và mất bao lâu.

`graphql.loader.size` là high-cardinality key nên được dùng trong trace. Không chuyển trực tiếp từng giá trị size thành metric tag, vì mỗi batch size có thể tạo thêm một time series và làm tăng cardinality.

## 13. Thêm batch-size bucket vào metrics (nâng cao)

Nếu cần xem phân bố batch size trên dashboard metrics, có thể bổ sung một low-cardinality bucket thay vì dùng số nguyên batch size làm tag. Spring Boot ưu tiên nhận `DataLoaderObservationConvention` dưới dạng bean; convention tùy chỉnh dưới đây mở rộng convention mặc định:

~~~java
package com.example.books.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DataLoaderObservationContext;
import org.springframework.graphql.observation.DefaultDataLoaderObservationConvention;
import org.springframework.stereotype.Component;

@Component
public class BatchSizeBucketConvention
        extends DefaultDataLoaderObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            DataLoaderObservationContext context) {

        int size = context.getResult().size();

        String bucket;
        if (size == 0) {
            bucket = "0";
        } else if (size <= 10) {
            bucket = "1-10";
        } else if (size <= 50) {
            bucket = "11-50";
        } else {
            bucket = "51+";
        }

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.loader.size.bucket", bucket));
    }
}
~~~

Các bucket có số lượng giá trị hữu hạn nên phù hợp làm metric tag. Vì class này là một `DataLoaderObservationConvention` bean, Spring Boot dùng nó thay cho convention mặc định khi tạo GraphQL observation instrumentation.

Chỉ đăng ký một convention tùy chỉnh cho DataLoader nếu muốn thay convention mặc định. Đừng đăng ký thêm một instrumentation thứ hai chỉ để thêm tag. Hãy giữ bucket đủ rộng và ổn định; không tạo bucket theo từng kích thước chính xác như `1`, `2`, `3`, ... vì cardinality sẽ tăng theo dữ liệu.

## 14. So sánh trước và sau khi dùng DataLoader

Dùng cùng một query `MeasureAuthorBatch` và cùng bộ dữ liệu để so sánh.

| Tín hiệu | Không dùng DataLoader | Dùng DataLoader |
| --- | --- | --- |
| Truy vấn lấy sách | Một truy vấn | Một truy vấn |
| Truy vấn lấy tác giả | Có thể N truy vấn riêng | Một batch query hoặc vài batch theo giới hạn |
| `graphql.datafetcher` cho field author | Có thể xuất hiện N lần | Các thao tác chỉ delegate sang DataLoader được thể hiện bằng DataLoader observation |
| `graphql.dataloader` | Không có batch observation | Có observation cho từng batch dispatch |
| Trace | Nhiều field fetch lặp lại | Thấy batch operation và loader size |
| Database query count | Có thể tăng theo số sách | Nên giảm về số batch query |

Đừng kết luận batching thành công chỉ vì `graphql.dataloader` có một observation. Hãy kiểm tra batch function có thật sự truy vấn theo tập ID, ví dụ một câu SQL `WHERE author_id IN (...)`, và đối chiếu SQL query count.

Một batch observation có thể mất ít thời gian nhưng database vẫn thực hiện nhiều câu SQL tuần tự bên trong. Ngược lại, batch size lớn có thể làm giảm query count nhưng tăng thời gian và bộ nhớ. Cần cân bằng batch size, `maxBatchSize`, cache theo request và chi phí truy vấn.

## 15. Diễn giải kết quả và xử lý sự cố

| Quan sát | Cách diễn giải | Hướng kiểm tra |
| --- | --- | --- |
| Không có `graphql.dataloader` | Chưa dùng DataLoader, instrumentation chưa bật hoặc phiên bản cũ | Kiểm tra version, registry và GraphQL runtime |
| Một request có nhiều batch observation | Có nhiều loader hoặc nhiều dispatch wave | Kiểm tra loader name, query shape và dispatch |
| Batch size thường bằng 1 | Query chỉ cần một key, các key được dispatch rời rạc hoặc batch bị chia nhỏ | Kiểm tra luồng thực thi và `maxBatchSize` |
| Batch size thấp hơn số parent | Key trùng được cache, thiếu entity hoặc batch result không đủ | Kiểm tra key set và kết quả mapping |
| `graphql.outcome=ERROR` | Batch loader thất bại | Xem `graphql.error.type` và exception log |
| Batch duration tăng | Truy vấn DB, remote call hoặc xử lý mapping chậm | Xem trace, SQL log và dependency metrics |
| Batch duration thấp nhưng request vẫn chậm | Chậm ở query root, resolver khác, transport hoặc nhiều batch | Mở trace `graphql.request` đầy đủ |
| Metrics không có batch size | Batch size là high-cardinality key, mặc định chỉ có trong trace | Dùng trace hoặc convention bucket |

Khi đo trong production, cần lọc theo `graphql.loader.name` và `graphql.outcome`. Đừng gắn ID người dùng, tenant ID, raw GraphQL query hoặc từng entity key vào low-cardinality metric tag. Những giá trị này vừa có nguy cơ chứa dữ liệu nhạy cảm vừa làm nổ cardinality.

Để quan sát nhánh lỗi trong môi trường test, có thể tạm cho batch service ném một exception có kiểm soát rồi gửi lại query. Kiểm tra `graphql.outcome=ERROR`, `graphql.error.type` và exception log tương ứng; khôi phục batch service sau phép thử. Không dùng cách cố tình làm lỗi dependency trong production để kiểm tra metric.

## 16. Checklist hoàn thành bài thực hành

- Spring for GraphQL đang dùng phiên bản 1.4.0 trở lên?
- Ứng dụng có `ObservationRegistry`?
- GraphQL runtime đã dùng `GraphQlObservationInstrumentation`?
- Actuator metrics endpoint đã được expose an toàn?
- Query thực hành đã tải nhiều parent cùng một field quan hệ?
- Batch loader nhận tập key và truy vấn theo batch?
- Có `graphql.dataloader` observation sau khi gửi query?
- Đã đọc `COUNT`, `TOTAL_TIME`, `MAX` theo loader?
- Đã xem `graphql.loader.size` trong trace?
- Đã phân biệt low-cardinality metric tags với high-cardinality trace attributes?
- Đã so sánh batch observations với SQL query count?
- Đã kiểm tra outcome và error type khi batch thất bại?

Đo DataLoader observation giúp nhìn thấy chi phí của batch dispatch trong một GraphQL request. Metrics cho biết tần suất, thời gian và outcome theo loader; trace cho biết batch size và vị trí của batch trong request. Kết hợp hai góc nhìn với SQL metrics/logs sẽ xác nhận DataLoader vừa gom đúng các key vừa giảm số lần truy cập database.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring for GraphQL — DataLoaderObservationContext API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationContext.html)
- [Spring for GraphQL 1.4 — DataLoader observations](https://github.com/spring-projects/spring-graphql/wiki/Spring-for-GraphQL-1.4)

