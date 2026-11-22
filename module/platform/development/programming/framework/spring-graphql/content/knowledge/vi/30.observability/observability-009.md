# graphql.loader.name

Khi một GraphQL query trả về nhiều object có quan hệ, mỗi object có thể cần tải thêm dữ liệu liên quan. Nếu mỗi field resolver tự gọi repository hoặc service riêng, ứng dụng dễ gặp N+1 query. Spring for GraphQL hỗ trợ `DataLoader` và `@BatchMapping` để gom các lần tải dữ liệu thành batch.

Từ Spring for GraphQL 1.4.0, instrumentation tạo thêm DataLoader observation có tên `graphql.dataloader`. Observation này mang key `graphql.loader.name` để nhận diện DataLoader đã thực hiện batch. Đây là một low-cardinality key, phù hợp để phân nhóm metrics và traces theo loại loader.

Bài học này giải thích ý nghĩa của `graphql.loader.name`, cách Spring đặt tên DataLoader, cách đặt tên ổn định bằng `BatchLoaderRegistry`, cách đọc outcome và batch size, và cách dùng metadata đó để tìm nút thắt trong luồng batch loading.

## 1. Vì sao cần nhận diện từng DataLoader?

Giả sử API thư viện trả về danh sách sách và tác giả của từng cuốn:

```graphql
type Query {
  books: [Book!]!
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
```

Nếu resolver field `Book.author` gọi database cho từng cuốn sách, một query lấy 100 cuốn có thể tạo ra:

- Một query lấy danh sách sách.
- 100 query riêng để lấy tác giả.

Đây là N+1 problem. DataLoader trì hoãn các lần `load(key)`, gom keys trong cùng GraphQL execution và gọi batch loader một lần cho cả nhóm. Với ví dụ trên, thay vì 100 truy vấn tác giả, ứng dụng có thể tải các tác giả bằng một truy vấn có điều kiện `WHERE id IN (...)`.

Trong một API lớn, có thể có nhiều DataLoader khác nhau:

- `authorById` tải tác giả theo ID.
- `reviewsByBookId` tải review theo sách.
- `permissionsByUserId` tải quyền theo user.
- `inventoryBySku` tải tồn kho theo SKU.

Khi một GraphQL request chậm, chỉ biết tổng thời gian request chưa đủ để xác định batch loader nào chậm hoặc thường xuyên lỗi. `graphql.loader.name` giúp tách observation theo loader để điều tra chính xác hơn.

## 2. Phân biệt observation name và key graphql.loader.name

Hai giá trị này có vai trò khác nhau:

| Giá trị | Ý nghĩa |
| --- | --- |
| `graphql.dataloader` | Tên của DataLoader observation |
| `graphql.loader.name` | Key nhận diện tên DataLoader đang được quan sát |

Không nên nhầm `graphql.loader.name` với:

- Tên GraphQL operation như `BookDetails`.
- Tên GraphQL field như `author` hoặc `reviews`.
- Tên observation tổng thể `graphql.request`.
- Tên observation DataFetcher `graphql.datafetcher`.

Ví dụ một trace có thể chứa:

```text
graphql.request
  graphql.datafetcher
  graphql.dataloader [graphql.loader.name=authorById]
  graphql.dataloader [graphql.loader.name=reviewsByBookId]
```

Một request có thể tạo nhiều DataLoader observations. Mỗi observation đại diện cho một hoạt động batch loading được instrumentation theo dõi; key `graphql.loader.name` cho biết loader nào thực hiện hoạt động đó.

## 3. Các metadata mặc định của DataLoader observation

Spring for GraphQL sử dụng `DefaultDataLoaderObservationConvention` với `DataLoaderObservationContext` để tạo metadata cho `graphql.dataloader`.

Các key mặc định:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| `graphql.loader.name` | Low | Tên DataLoader được sử dụng |
| `graphql.outcome` | Low | Kết quả hoạt động: `SUCCESS` hoặc `ERROR` |
| `graphql.error.type` | Low | Tên class của lỗi DataLoader nếu có |
| `graphql.loader.size` | High | Kích thước danh sách phần tử được tải |

### Low-cardinality key

`graphql.loader.name` là low-cardinality key bắt buộc. Nó nên có một tập giá trị hữu hạn, ổn định và có thể dự đoán, ví dụ:

```text
authorById
reviewsByBookId
inventoryBySku
permissionsByUserId
```

Micrometer dùng low-cardinality values cho metrics tags và cũng có thể đưa chúng vào trace metadata. Vì vậy, tên loader có thể dùng để nhóm số lần gọi, thời gian xử lý và số lỗi theo từng loại batch loader.

### High-cardinality key

`graphql.loader.size` là high-cardinality key. Nó mô tả số lượng phần tử được tải trong batch. Giá trị này hữu ích khi đọc từng trace để biết một lần batch đã xử lý bao nhiêu phần tử.

Không nên coi `graphql.loader.size` là một metrics tag tương đương `graphql.loader.name`. High-cardinality values không được dùng làm meter tags theo cách thông thường vì mỗi giá trị khác nhau có thể tạo thêm time series. Nếu cần phân phối batch size trong metrics, hãy thiết kế histogram hoặc meter riêng với giới hạn cardinality rõ ràng.

## 4. Tên DataLoader được tạo như thế nào?

Spring for GraphQL quản lý batch loader qua `BatchLoaderRegistry`. Với cách đăng ký theo cặp kiểu:

```java
registry.forTypePair(Long.class, Author.class)
        .registerMappedBatchLoader((authorIds, environment) -> {
            // Return Mono<Map<Long, Author>>.
        });
```

Tên DataLoader mặc định dựa trên class name của kiểu giá trị đích, trong ví dụ này là `Author`. Điều này cho phép `@SchemaMapping` nhận một tham số `DataLoader<Long, Author>` theo generic type mà không cần tự chỉ định tên trong trường hợp thông thường.

Có thể đặt tên tường minh qua `RegistrationSpec.withName(String)` hoặc bắt đầu registration bằng `BatchLoaderRegistry.forName(String)`. Khi đặt tên thủ công, tên cần nhất quán với cách DataLoader được tìm và inject vào resolver.

### Đăng ký bằng tên tường minh

Ví dụ đặt tên `authorById`:

```java
@Configuration
public class AuthorBatchConfiguration {

    public AuthorBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.<Long, Author>forName("authorById")
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds)
                                .collectMap(Author::id));
    }
}
```

Resolver dùng cùng tên làm tên tham số:

```java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorById) {

        return authorById.load(book.authorId());
    }
}
```

`forName("authorById")` đăng ký loader bằng tên cụ thể. Spring for GraphQL dùng tên đó để tìm loader tương ứng trong request-scoped `DataLoaderRegistry`. Với cách inject theo tên, tên tham số của `DataLoader` trong handler cần khớp với tên đã đăng ký; bảo đảm compiler giữ parameter names hoặc cấu hình tên tham số phù hợp.

### Đăng ký theo type pair và đổi tên

Nếu muốn đăng ký theo kiểu key/value nhưng vẫn kiểm soát tên:

```java
registry.forTypePair(Long.class, Author.class)
        .withName("authorById")
        .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findAllByIds(authorIds)
                        .collectMap(Author::id));
```

Tên tùy chỉnh giúp metadata rõ ràng hơn tên class đầy đủ như `com.example.library.Author`. Khi đổi package hoặc refactor class, một tên logic ổn định giúp dashboard và truy vấn metrics không bị thay đổi ngoài ý muốn.

## 5. @BatchMapping cũng tạo DataLoader observation

Với trường hợp đơn giản, `@BatchMapping` là cách viết ngắn hơn so với việc tự đăng ký loader và viết resolver gọi `DataLoader.load`:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        return authorService.findByBooks(books)
                .collectMap(AuthorEntry::book, AuthorEntry::author);
    }
}
```

Spring for GraphQL đăng ký batch loading function và DataFetcher tương ứng cho field `Book.author`. Instrumentation theo dõi cả các lời gọi `@BatchMapping` lẫn DataLoader đăng ký thủ công, vì vậy chúng có thể tạo `graphql.dataloader` observations.

`@BatchMapping` có thể tự tạo tên loader từ thông tin kiểu và mapping. Nếu muốn kiểm soát tên DataLoader tường minh để dễ quan sát, cân nhắc đăng ký qua `BatchLoaderRegistry`. Dù dùng cách nào, hãy kiểm tra giá trị `graphql.loader.name` thực tế trong trace hoặc meter sau khi chạy một request mẫu.

## 6. Bật DataLoader observations

DataLoader observation được cung cấp bởi `GraphQlObservationInstrumentation`. Observation chỉ được phát khi ứng dụng có `ObservationRegistry` và instrumentation được gắn vào GraphQL runtime.

### Spring Boot

Với Spring Boot starter, hãy bảo đảm Micrometer Observation infrastructure đã được cấu hình và `ObservationRegistry` có mặt trong application context. Boot có thể tích hợp instrumentation vào GraphQL source theo auto-configuration của phiên bản đang dùng. Nếu ứng dụng đã có cấu hình `GraphQlSource` tùy chỉnh, xác nhận instrumentation không bị bỏ qua khi tự dựng source.

### Standalone GraphQlSource

Với ứng dụng tự dựng GraphQL source, có thể thêm instrumentation:

```java
import java.util.List;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .configureRuntimeWiring(runtimeWiringConfigurer)
        .instrumentation(List.of(
                new GraphQlObservationInstrumentation(observationRegistry)))
        .build();
```

Ví dụ dùng constructor một tham số để áp dụng các default observation conventions. Nếu tự cấu hình instrumentation, hãy kiểm tra ứng dụng không đồng thời thêm một instrumentation tương đương ở nơi khác khiến quan sát bị lặp.

### Phiên bản hỗ trợ

`DataLoaderObservationContext` và `DataLoaderObservationConvention` được giới thiệu từ Spring for GraphQL 1.4.0. Với phiên bản cũ hơn, không có mặc định `graphql.dataloader` và `graphql.loader.name`. Hãy kiểm tra phiên bản thực tế trước khi tạo dashboard hoặc alert dựa trên key này.

## 7. Đọc metrics theo graphql.loader.name

Vì `graphql.loader.name` là low-cardinality key, Micrometer có thể dùng nó làm tag để nhóm timer/counter của DataLoader observations. Tên meter và cách chuẩn hóa tag phụ thuộc registry/exporter, vì vậy hãy xem output thực tế từ Prometheus, OTLP hoặc backend đang dùng.

Một chuỗi metric minh họa về mặt khái niệm:

```text
graphql.dataloader
  graphql.loader.name = authorById
  graphql.outcome = SUCCESS
```

Khi nhóm metrics theo loader, có thể trả lời:

- Loader nào được gọi thường xuyên nhất?
- Loader nào có thời gian xử lý trung bình hoặc percentile cao?
- Loader nào có tỷ lệ `ERROR` lớn?
- Sau một lần deploy, thời gian batch của loader nào tăng rõ rệt?
- Một query thường dùng những loader nào?

Không nên chỉ nhìn số lần gọi. Một loader có thể được gọi ít lần nhưng mỗi batch tải rất nhiều dữ liệu hoặc chờ downstream lâu. Hãy kết hợp thời gian, outcome và trace để hiểu nguyên nhân.

### Ví dụ đọc dữ liệu

Giả sử dashboard có kết quả:

| Loader | Observations | Errors | p95 duration |
| --- | ---: | ---: | ---: |
| `authorById` | 2.400 | 3 | 18 ms |
| `reviewsByBookId` | 800 | 72 | 240 ms |
| `inventoryBySku` | 1.100 | 2 | 35 ms |

`reviewsByBookId` có số lỗi và p95 cao hơn hẳn. Đây là tín hiệu để mở trace tương ứng, xem batch size, query database, cache hit rate và dependency phía sau loader.

Các con số chỉ minh họa cách đọc dashboard. Chúng không phải giá trị mặc định hay benchmark của Spring GraphQL.

## 8. Dùng graphql.loader.size trong trace

`graphql.loader.size` là high-cardinality key mô tả số lượng phần tử được tải trong một batch. Nó giúp phân biệt các tình huống:

- Batch nhỏ nhưng chậm: có thể backend chậm, connection pool thiếu hoặc query plan kém.
- Batch lớn và chậm: có thể payload lớn, query quá rộng hoặc giới hạn batch chưa phù hợp.
- Batch size bằng 0: có thể không tìm thấy dữ liệu tương ứng với các keys, tùy loại batch loader và kết quả trả về.
- Batch size thay đổi mạnh giữa các request: có thể query shape hoặc page size của client không ổn định.

Với `DataLoaderObservationContext`, instrumentation có thể truy cập DataLoader đang chạy, keys được yêu cầu, batch environment và danh sách kết quả. Default convention dùng thông tin đó để tạo metadata.

Không nên đưa `graphql.loader.size` thành label/tag của mọi metrics time series. Nếu muốn thống kê phân phối batch size, hãy tạo một histogram riêng với bucket hữu hạn, ví dụ `1–10`, `11–50`, `51–100` và `100+`. Cách này cho phép theo dõi kích thước batch mà không tạo một time series mới cho mỗi giá trị.

## 9. Hiểu outcome và error type

DataLoader observations có hai low-cardinality keys bổ sung:

| Key | Giá trị |
| --- | --- |
| `graphql.outcome` | `SUCCESS` hoặc `ERROR` |
| `graphql.error.type` | Tên class của lỗi khi batch loading thất bại |

Ví dụ:

```text
graphql.dataloader
  graphql.loader.name = authorById
  graphql.outcome = ERROR
  graphql.error.type = DataAccessResourceFailureException
```

Khi một batch loader lỗi, kiểm tra:

1. Loader nào phát sinh lỗi qua `graphql.loader.name`.
2. Lỗi thuộc nhóm nào qua `graphql.error.type`.
3. Lỗi xuất hiện trong trace nào và GraphQL request cha nào.
4. Batch size có bất thường không.
5. Dependency nào nằm phía sau batch loader.

`graphql.error.type` là tên class, không phải nội dung exception. Không nên thay thế nó bằng exception message chứa SQL, ID, tenant hoặc dữ liệu đầu vào động trong metrics tags.

## 10. Tên loader và cardinality

Tên DataLoader thường trở thành giá trị tag trên metrics. Vì vậy, tên cần ổn định theo thời gian và có số lượng hữu hạn.

### Nên dùng

```text
authorById
reviewsByBookId
inventoryBySku
permissionsByUserId
```

### Không nên dùng

```text
authorById-user-839102
reviews-book-2026-11-20T10:15:00Z
inventory-tenant-<tenant-id>
loader-<random-uuid>
```

Không đưa các giá trị sau vào loader name:

- User ID, tenant ID hoặc account ID.
- Request ID, trace ID hoặc UUID ngẫu nhiên.
- Book ID, SKU hoặc danh sách keys của một batch.
- Timestamp, query string hoặc GraphQL variables.
- Tên bảng/database được ghép từ input không kiểm soát.

Các giá trị động làm cardinality tăng nhanh. Mỗi giá trị mới có thể tạo thêm time series, khiến Prometheus hoặc metrics backend tốn bộ nhớ và chi phí xử lý. Nếu cần truy vết một request cụ thể, dùng trace ID và high-cardinality trace attributes theo chính sách bảo mật của hệ thống; không nhúng chúng vào `graphql.loader.name`.

### Đặt tên theo nghiệp vụ

Tên như `authorById` thể hiện mục đích tải dữ liệu. Tên như `com.example.persistence.AuthorEntity` phản ánh implementation và có thể thay đổi khi refactor. Ưu tiên tên logic ngắn, ổn định và phân biệt được các batch loader khác nhau.

Nếu hai loader có hành vi hoặc dependency khác nhau, đừng dùng chung tên chỉ vì chúng trả cùng một Java type. Dùng tên riêng để dashboard tách được latency và error rate.

## 11. Tùy chỉnh DataLoaderObservationConvention

Nếu quy ước đặt tên hiện tại chưa phù hợp, Spring for GraphQL cho phép thay đổi metadata bằng `DataLoaderObservationConvention`. Default implementation là `DefaultDataLoaderObservationConvention`.

Với Spring Boot, cách tích hợp được ưu tiên là cung cấp custom convention dưới dạng bean để GraphQL observation instrumentation sử dụng. Với cấu hình standalone, truyền convention vào `GraphQlObservationInstrumentation`.

Từ Spring for GraphQL 1.4.0, constructor đầy đủ của instrumentation nhận bốn convention:

```java
new GraphQlObservationInstrumentation(
        observationRegistry,
        requestObservationConvention,
        dataFetcherObservationConvention,
        dataLoaderObservationConvention);
```

Constructor ba tham số cũ đã deprecated từ 1.4.0 để chuyển sang constructor có thêm `DataLoaderObservationConvention`. Khi tự cấu hình instrumentation, dùng API mới để có thể tùy chỉnh cả DataLoader metadata.

`DataLoaderObservationContext` cung cấp thông tin cho convention:

| Method | Thông tin |
| --- | --- |
| `getDataLoader()` | DataLoader đang thực hiện operation |
| `getKeys()` | Danh sách keys được yêu cầu |
| `getResult()` | Danh sách giá trị được resolve, hoặc danh sách rỗng nếu không có kết quả |
| `getEnvironment()` | BatchLoaderEnvironment được truyền vào batch function |

Convention có thể dùng các thông tin này để chuẩn hóa loader name hoặc bổ sung metadata. Tuy nhiên, giữ `graphql.loader.name` ổn định và low-cardinality là yêu cầu quan trọng nhất nếu muốn dùng key này cho metrics.

Không thay key `graphql.loader.name` bằng request ID hoặc tên động. Nếu cần thêm thông tin riêng cho trace, dùng high-cardinality metadata và kiểm soát dữ liệu nhạy cảm.

## 12. Từ DataLoader observation đến chẩn đoán N+1

DataLoader observations giúp nhìn thấy batch loading riêng biệt với những field fetch thông thường. Từ Spring for GraphQL 1.4, các hoạt động DataFetcher chỉ ủy quyền sang DataLoader không còn tạo cùng loại `graphql.datafetcher` observation như trước; thay vào đó, batch load được thể hiện bằng `graphql.dataloader`. Điều này giảm các span lặp theo từng child field và làm trace phản ánh đúng batch operation hơn.

Khi điều tra N+1 hoặc hiệu năng, có thể làm theo quy trình:

1. Tìm `graphql.request` có duration cao.
2. Mở trace và liệt kê các `graphql.dataloader` child observations.
3. Nhóm chúng theo `graphql.loader.name` để biết loader nào chạy.
4. So sánh duration, `graphql.outcome` và `graphql.error.type`.
5. Đọc `graphql.loader.size` để biết mỗi batch xử lý bao nhiêu phần tử.
6. Mở code của batch loader tương ứng và kiểm tra SQL, remote call, cache, connection pool và batch limit.

Ví dụ:

```text
graphql.request  920 ms
  graphql.dataloader [loader=authorById, size=40]       28 ms
  graphql.dataloader [loader=reviewsByBookId, size=40]  710 ms
  graphql.dataloader [loader=inventoryBySku, size=40]    45 ms
```

Trace cho thấy batch review chiếm phần lớn thời gian. Nếu chỉ nhìn tổng request, khó xác định ngay dependency cần tối ưu.

DataLoader observations không tự chứng minh rằng ứng dụng đã loại bỏ hoàn toàn N+1. Một resolver có thể vẫn gọi repository trực tiếp, hoặc batch loader có thể phát nhiều batch nhỏ do query shape, dispatch boundaries hoặc max batch size. Hãy kết hợp trace với query log và số lần gọi database.

## 13. Thiết kế dashboard và alert

Một dashboard theo `graphql.loader.name` nên tập trung vào những câu hỏi vận hành:

| Panel | Nhóm theo | Mục đích |
| --- | --- | --- |
| Batch duration | `graphql.loader.name` | Tìm loader có latency cao |
| Batch call rate | `graphql.loader.name` | Nhận biết loader hoạt động bất thường |
| Error rate | `graphql.loader.name`, `graphql.outcome` | Phát hiện loader lỗi tăng |
| Error class | `graphql.loader.name`, `graphql.error.type` | Nhận diện nhóm lỗi downstream |
| Batch size distribution | Trace hoặc histogram riêng | Nhìn batch nhỏ/lớn và phân bố kích thước |

Alert nên có ngưỡng theo baseline của từng loader. Một batch loader đọc cache có thể có latency kỳ vọng khác loader gọi service bên ngoài. Không áp dụng một ngưỡng duration giống nhau cho tất cả loader.

Ví dụ quy tắc vận hành:

- Báo động khi error rate của `reviewsByBookId` tăng vượt baseline trong một khoảng thời gian.
- Điều tra khi p95 của `authorById` tăng sau deploy.
- Theo dõi batch size khi một thay đổi pagination khiến số phần tử mỗi batch tăng đột biến.
- So sánh tổng GraphQL request duration với thời gian của các DataLoader observations để phát hiện phần thời gian nằm ngoài batch loading.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy `graphql.dataloader` | Spring GraphQL cũ hơn 1.4.0 hoặc instrumentation không hoạt động | Kiểm tra version và `ObservationRegistry`/GraphQL instrumentation |
| Có `graphql.request` nhưng không có DataLoader observation | Request không thực sự dùng DataLoader, hoặc custom GraphQlSource bỏ qua instrumentation | Kiểm tra batch registration và GraphQlSource |
| `graphql.loader.name` là tên class dài | Dùng tên mặc định theo target type | Đặt tên logic qua `withName` hoặc `forName` |
| Không tìm thấy DataLoader theo tên trong resolver | Tên registration và tên tham số DataLoader không khớp | Đồng bộ tên loader và tên tham số handler |
| Metric series tăng nhanh | Loader name chứa ID hoặc giá trị động | Dùng tên cố định theo nghiệp vụ |
| Không thấy batch size trên metrics | `graphql.loader.size` là high-cardinality key | Đọc trong trace hoặc tạo histogram có bucket hữu hạn |
| Trace có nhiều field spans nhưng thiếu batch span | Chưa dùng instrumentation tương thích hoặc hoạt động không đi qua DataLoader | Kiểm tra phiên bản và batch execution path |
| `graphql.outcome=ERROR` nhưng không rõ nguyên nhân | Chưa phân tích `graphql.error.type` và trace | Mở trace, xem error type và dependency phía sau loader |
| @BatchMapping có tên loader khó đoán | Framework tạo loader từ mapping/type | Kiểm tra giá trị thực tế; dùng BatchLoaderRegistry nếu cần tên chủ động |

## 15. Nguyên tắc sử dụng graphql.loader.name

- Hiểu `graphql.dataloader` là observation name và `graphql.loader.name` là low-cardinality key.
- Dùng tên loader ổn định, có ý nghĩa nghiệp vụ và hữu hạn.
- Dùng `BatchLoaderRegistry.withName` hoặc `forName` khi muốn tên tường minh.
- Giữ tên registration đồng bộ với cách inject DataLoader trong handler.
- Dùng `graphql.outcome` và `graphql.error.type` để phân tích thành công/lỗi.
- Dùng `graphql.loader.size` trong trace để hiểu batch size; tránh biến nó thành tag không giới hạn.
- Nhớ DataLoader observations được giới thiệu trong Spring for GraphQL 1.4.0.
- Kiểm tra `GraphQlObservationInstrumentation` và `ObservationRegistry` có hoạt động trong runtime.
- Đối chiếu trace với SQL/query log để xác nhận hiệu quả giảm N+1.
- Không đưa ID, tenant, user, request hoặc UUID vào loader name.
- Đặt alert theo baseline của từng loader thay vì dùng chung một ngưỡng.
- Kiểm tra lại dashboard khi đổi tên DataLoader hoặc refactor target type.

## 16. Bài tập thực hành

Xây dựng observability cho batch loading trong API thư viện:

1. Tạo query trả danh sách sách cùng tác giả và review.
2. Đăng ký DataLoader `authorById` và `reviewsByBookId` qua `BatchLoaderRegistry`.
3. Dùng `withName` hoặc `forName` để đặt tên ổn định.
4. Tạo `@SchemaMapping` dùng các DataLoader đó.
5. Cấu hình Micrometer Observation và GraphQL observation instrumentation.
6. Gửi một GraphQL request lấy nhiều sách.
7. Xác nhận có `graphql.dataloader` observations.
8. Đọc `graphql.loader.name` để phân biệt author và reviews loader.
9. Tạo một lỗi giả lập trong reviews batch loader và kiểm tra `graphql.outcome` cùng `graphql.error.type`.
10. Mở trace và kiểm tra `graphql.loader.size`.
11. Đổi tên một loader thành giá trị có request ID, quan sát cardinality tăng trong môi trường thử nghiệm; sau đó thay bằng tên cố định.
12. So sánh trace trước và sau khi chuyển resolver N+1 sang batch loading.

Sau bài tập, bạn cần giải thích được vì sao `graphql.loader.name` là low-cardinality key, cách nó liên hệ với DataLoader registration, và cách dùng nó để xác định batch loader gây chậm hoặc lỗi.

## 17. Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — DataLoaderObservationContext API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationContext.html)
- [Spring for GraphQL — DefaultDataLoaderObservationConvention API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DefaultDataLoaderObservationConvention.html)
- [Spring for GraphQL — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL — BatchLoaderRegistry API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/execution/BatchLoaderRegistry.html)

DataLoader observation và convention có từ Spring for GraphQL 1.4.0. Hãy kiểm tra Javadoc khớp với dependency thực tế của ứng dụng, nhất là khi dùng custom instrumentation hoặc custom observation convention.
