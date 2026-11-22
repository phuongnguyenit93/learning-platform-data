# Quan sát GraphQL DataLoader trong Spring for GraphQL

DataLoader giúp gom nhiều lần tải dữ liệu liên quan thành các batch để giảm vấn đề N+1. Tuy nhiên, chỉ biết query đã trả đúng dữ liệu chưa đủ để đánh giá batching có hiệu quả hay không. Cần biết batch loader nào được gọi, mất bao lâu, trả về bao nhiêu phần tử và có lỗi hay không.

Spring for GraphQL tích hợp Micrometer Observation để ghi nhận hoạt động DataLoader bằng observation có tên `graphql.dataloader`. Observation này bao phủ các method `@BatchMapping` và các `DataLoader` được đăng ký thủ công. Nó bổ sung góc nhìn chuyên biệt cho batch loading bên cạnh observation của toàn GraphQL request và các DataFetcher không tầm thường.

## 1. Vì sao cần quan sát DataLoader?

Giả sử một query tải 40 đơn hàng và chọn thêm thông tin khách hàng của từng đơn:

```graphql
query Orders {
    orders {
        id
        customer {
            id
            name
        }
    }
}
```

Nếu mỗi field `Order.customer` gọi repository riêng, server có thể thực hiện một query tải danh sách đơn hàng và thêm 40 query tải customer. Đây là N+1.

Với `@BatchMapping` hoặc `DataLoader`, các customer ID được gom lại và tải theo batch. Khi quan sát đúng, trace cho thấy một hoạt động batch xử lý nhiều key thay vì hàng loạt hoạt động tải dữ liệu riêng lẻ.

Observability giúp trả lời các câu hỏi:

- Loader nào được sử dụng trong GraphQL request?
- Mỗi lần batch load mất bao lâu?
- Batch loader hoàn tất thành công hay lỗi?
- Có bao nhiêu phần tử được trả về trong lần batch load?
- Một request đang thực hiện nhiều batch nhỏ hay một batch lớn?
- Thời gian chậm đến từ GraphQL resolver, batch loader hay database phía sau?

## 2. Micrometer Observation trong Spring for GraphQL

Micrometer Observation là lớp trừu tượng để ghi nhận một hoạt động trong ứng dụng. Các `ObservationHandler` có thể chuyển observation thành metrics, traces hoặc cả hai.

Spring for GraphQL có ba observation chính ở phía server:

| Observation | Phạm vi | Dùng để quan sát |
|---|---|---|
| `graphql.request` | Toàn bộ GraphQL request | Thời gian request, operation type và outcome. |
| `graphql.datafetcher` | DataFetcher không tầm thường | Thời gian phân giải field và lỗi của resolver. |
| `graphql.dataloader` | Hoạt động batch loading | Thời gian gọi `@BatchMapping` hoặc DataLoader thủ công. |

Một request có thể tạo một observation `graphql.request` và nhiều observation con cho các hoạt động DataFetcher hoặc DataLoader. Điều này giúp truy từ request chậm xuống hoạt động cụ thể.

Từ Spring for GraphQL 1.4.0, DataLoader có observation riêng. Trước đó, việc phân biệt hoạt động DataFetcher thông thường với một lần batch loading chưa rõ ràng trong trace. Nếu cần `graphql.dataloader`, hãy kiểm tra phiên bản Spring for GraphQL đang được Spring Boot quản lý; phiên bản cũ hơn 1.4.0 không có observation này.

## 3. Observation `graphql.dataloader` ghi nhận điều gì?

Spring for GraphQL dùng `GraphQlObservationInstrumentation` để tạo observation. Với DataLoader, convention mặc định là `DefaultDataLoaderObservationConvention`, dựa trên `DataLoaderObservationContext`.

Observation `graphql.dataloader` được tạo khi có hoạt động tải dữ liệu của:

- Method controller dùng `@BatchMapping`.
- DataLoader được đăng ký thủ công, thường thông qua `BatchLoaderRegistry`.

Mỗi observation mô tả một lần thực thi batch loader. Nó không phải observation cho từng lần gọi `DataLoader.load(key)` của từng field.

Các key mặc định:

| Key | Cardinality | Ý nghĩa |
|---|---|---|
| `graphql.loader.name` | Low | Tên DataLoader đang được sử dụng. |
| `graphql.outcome` | Low | Kết quả hoạt động: `SUCCESS` hoặc `ERROR`. |
| `graphql.error.type` | Low | Tên class của lỗi data fetching nếu có. |
| `graphql.loader.size` | High | Số phần tử trong danh sách kết quả do DataLoader trả về. |

`graphql.loader.size` là số phần tử được phân giải/trả về, không nên mặc định coi đó là số lần gọi `load()`, số cache miss hay số dòng database đã đọc. Nếu batch loader bỏ qua key không có kết quả, số phần tử trả về có thể ít hơn số key đầu vào.

## 4. Low cardinality và high cardinality

Micrometer phân chia observation key-value thành hai nhóm:

- Low cardinality: số lượng giá trị có giới hạn và có thể dùng làm tag của metrics.
- High cardinality: số lượng giá trị có thể tăng rất lớn; chỉ nên đưa vào traces.

Với `graphql.dataloader`:

- `graphql.loader.name`, `graphql.outcome`, `graphql.error.type` là low cardinality.
- `graphql.loader.size` là high cardinality.

Vì vậy, có thể lọc metric theo tên loader và outcome, còn kích thước batch có thể xem trong trace. Không kỳ vọng `graphql.loader.size` xuất hiện như tag trên meter metrics mặc định.

Không đưa các giá trị như raw entity ID, user ID, tenant ID, danh sách key, GraphQL variables hoặc query text vào low-cardinality metrics. Các giá trị này có thể tạo hàng nghìn hoặc hàng triệu time series, làm tăng bộ nhớ và chi phí của hệ thống metrics; chúng cũng có thể chứa dữ liệu nhạy cảm.

## 5. Bật DataLoader observation với Spring Boot

Trong Spring Boot, GraphQL observation instrumentation được auto-configure khi có `ObservationRegistry` và các điều kiện cần thiết. Spring Boot 3.5 cung cấp `GraphQlObservationAutoConfiguration` và hỗ trợ bean `DataLoaderObservationConvention` để tùy biến metadata DataLoader.

Dependencies minh họa với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Spring Boot quản lý phiên bản Micrometer và Spring for GraphQL tương thích. Dependency Prometheus chỉ cần nếu muốn xuất metrics tới Prometheus; có thể thay bằng registry của hệ thống giám sát đang sử dụng.

Với Boot auto-configuration, không cần tự tạo thêm `GraphQlObservationInstrumentation` nếu Boot đã tạo bean này. Điều kiện quan trọng là ứng dụng có `ObservationRegistry`; Boot Actuator cung cấp hạ tầng observation và meter registry phù hợp.

## 6. Cấu hình endpoint metrics

Để kiểm tra metrics qua Actuator và cho Prometheus scrape, có thể expose các endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Sau khi ứng dụng có request GraphQL thực thi DataLoader, có thể kiểm tra danh sách meter tại:

```text
GET /actuator/metrics
```

Xem observation DataLoader:

```text
GET /actuator/metrics/graphql.dataloader
```

Lọc theo tên loader:

```text
GET /actuator/metrics/graphql.dataloader?tag=graphql.loader.name:com.example.Author
```

Giá trị tag của `graphql.loader.name` phụ thuộc tên loader thực tế. Với DataLoader đăng ký qua Spring `BatchLoaderRegistry`, tên mặc định thường dựa trên class của kiểu entity đích; nếu ứng dụng tùy chỉnh tên, dùng tên đã đăng ký.

Endpoint `metrics` dùng tên meter theo Micrometer, chẳng hạn `graphql.dataloader`. Tên xuất sang Prometheus có thể được chuẩn hóa theo quy tắc đặt tên của registry, ví dụ chuyển dấu chấm thành dấu gạch dưới và bổ sung đơn vị cho timer.

## 7. Quan sát trace của một GraphQL request

Khi có Micrometer Tracing và tracing exporter được cấu hình, observations có thể tạo spans trong distributed trace.

Một trace có thể có cấu trúc khái quát:

```text
HTTP server request
  |
  +-- graphql.request
        |
        +-- graphql.datafetcher (orders)
        |
        +-- graphql.dataloader (Customer loader)
        |
        +-- graphql.dataloader (Product loader)
```

Trong trace:

- `graphql.request` cho biết tổng thời gian GraphQL execution.
- `graphql.datafetcher` cho biết thời gian của các field resolver không tầm thường.
- `graphql.dataloader` cho biết thời gian batch loading, loader name, outcome và metadata batch size.

Với HTTP, Spring Framework có instrumentation riêng để tạo observation cho HTTP server request và truyền tracing context. Với transport khác, cần bảo đảm transport instrumentation và context propagation được cấu hình phù hợp.

## 8. Phân biệt DataFetcher observation và DataLoader observation

Không phải mọi field trong GraphQL đều tạo `graphql.datafetcher`. Spring for GraphQL chỉ tạo DataFetcher observations cho các hoạt động được xem là không tầm thường; việc đọc property đơn giản từ Java object không cần observation riêng.

Với `@BatchMapping` hoặc DataLoader thủ công, hãy quan sát `graphql.dataloader` để xem batch loading. Trong Spring for GraphQL 1.4 trở lên, hoạt động DataLoader có observation riêng, giúp trace thể hiện rõ một batch call thay vì chỉ thấy các field fetch.

Ví dụ:

| Cách triển khai | Dấu hiệu quan sát |
|---|---|
| `@SchemaMapping` truy vấn repository riêng cho từng parent | Nhiều hoạt động DataFetcher, có thể thấy pattern N+1. |
| `@BatchMapping` gom nhiều parent | Observation `graphql.dataloader` cho batch load. |
| DataLoader thủ công được đăng ký | Observation `graphql.dataloader` cho batch loader đã đăng ký. |
| Property fetcher đọc field Java đơn giản | Thường không có DataFetcher observation riêng. |

Khi so sánh trace trước và sau khi chuyển sang batching, hãy nhìn số lượng hoạt động và thời gian tổng thể, không chỉ một span riêng lẻ.

## 9. Dùng observation để phát hiện N+1

Giả sử query trả về 30 books và chọn `author` của từng book.

Nếu resolver tải author từng cuốn, trace có thể thể hiện nhiều lần fetch field `author`, mỗi lần thực hiện một thao tác tải dữ liệu. Khi chuyển sang `@BatchMapping`, các parent được gom lại và một batch loader tải các author cần thiết.

Quy trình điều tra:

1. Tìm các `graphql.request` có thời gian cao.
2. Mở trace và xác định các `graphql.datafetcher` hoặc `graphql.dataloader` chiếm nhiều thời gian.
3. Kiểm tra loader name để biết field/nhóm dữ liệu nào đang được tải.
4. So sánh số lần batch dispatch và `graphql.loader.size` trong trace.
5. Kiểm tra query database hoặc service phía sau để xác minh batch loader thực sự giảm round-trip.
6. Chạy lại cùng operation với cùng dữ liệu để so sánh.

Ví dụ bảng so sánh khái niệm:

| Chỉ số | Resolver riêng từng parent | Batch loading |
|---|---:|---:|
| Số parent books | 30 | 30 |
| Lần tải author riêng | Có thể 30 | Được gom theo batch dispatch |
| Số batch observation | Không có batch observation tương ứng | Có observation `graphql.dataloader` |
| Số truy vấn database | Có thể tăng theo số parent | Phụ thuộc cách batch loader triển khai |

Observation chứng minh batch loader được gọi và đo thời gian của hoạt động đó; nó không tự chứng minh câu SQL chỉ chạy một lần. Batch method vẫn có thể chứa vòng lặp truy vấn từng key. Cần kết hợp database metrics, query logs hoặc tracing của data access layer để xác nhận N+1 đã được loại bỏ thực sự.

## 10. `@BatchMapping` và DataLoader thủ công đều được quan sát

Ví dụ `@BatchMapping`:

```java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    Mono<Map<Book, Author>> author(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findByIds(authorIds)
            .collectMap(Author::id)
            .map(authors -> {
                Map<Book, Author> result = new LinkedHashMap<>();
                for (Book book : books) {
                    Author author = authors.get(book.authorId());
                    if (author != null) {
                        result.put(book, author);
                    }
                }
                return result;
            });
    }
}
```

`@BatchMapping` là cách khai báo batch mapping ngắn gọn; Spring for GraphQL tạo DataLoader cần thiết cho field đó. Observation `graphql.dataloader` được tạo cho hoạt động batch tương ứng.

Với DataLoader đăng ký thủ công qua `BatchLoaderRegistry`, observation cũng được tạo khi loader được dispatch. Điều này cho phép theo dõi cùng một loại tín hiệu dù ứng dụng dùng annotation hay DataLoader API trực tiếp.

## 11. Hiểu `graphql.loader.size`

`graphql.loader.size` là high-cardinality key mô tả số phần tử trong danh sách kết quả được DataLoader trả về.

Ví dụ batch loader nhận 20 author IDs nhưng chỉ tìm thấy 18 authors:

```text
Input keys:       20
Resolved values:  18
graphql.loader.size: 18
```

Giá trị này hữu ích để xem kích thước kết quả batch trong trace, nhưng không phải lúc nào cũng bằng số key đầu vào. Để hiểu đầy đủ, cần biết:

- Số key đã được đưa vào batch.
- Số giá trị loader trả về.
- Các key không có kết quả được xử lý ra sao.
- Loader có dùng mapped batch loader hay ordered batch loader.
- Có giới hạn `maxBatchSize` làm một tập key được chia thành nhiều dispatch hay không.

`DataLoaderObservationContext` cung cấp `getKeys()`, `getResult()`, `getDataLoader()` và `getEnvironment()` để convention có thể đọc thông tin chi tiết hơn nếu cần. Tránh đưa chính raw key hoặc dữ liệu nhạy cảm vào metrics/traces.

## 12. Observation không phải cache hit/miss metric

DataLoader có cache theo request. Nếu một key được yêu cầu nhiều lần trong cùng execution, DataLoader có thể trả kết quả đã cache mà không gọi batch loader lần nữa.

`graphql.dataloader` quan sát hoạt động batch loader khi nó thực thi. Nó không phải counter cho mọi lệnh `load(key)` và không mặc định cung cấp các chỉ số:

- Tổng số lần gọi `DataLoader.load()`.
- Cache hit count.
- Cache miss count.
- Số key bị deduplicate.
- Số query SQL thực tế.

Vì vậy, không thể chỉ nhìn số `graphql.dataloader` observations rồi suy ra chính xác cache hit ratio. Nếu cần cache hit/miss, hãy bổ sung instrumentation phù hợp ở lớp DataLoader/cache hoặc ghi nhận số liệu bằng custom metric có cardinality được kiểm soát.

## 13. Tùy chỉnh metadata bằng `DataLoaderObservationConvention`

Spring for GraphQL dùng `DefaultDataLoaderObservationConvention` để tạo key-value mặc định. Từ Spring for GraphQL 1.4.0, có thể cung cấp `DataLoaderObservationConvention` riêng để thêm hoặc thay đổi metadata.

Trong Spring Boot, khai báo bean convention là cách phù hợp để auto-configuration sử dụng convention đó. Ví dụ sau thêm một nhãn cố định mô tả nhóm loader của ứng dụng:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DataLoaderObservationContext;
import org.springframework.graphql.observation.DataLoaderObservationConvention;
import org.springframework.graphql.observation.DefaultDataLoaderObservationConvention;

@Configuration(proxyBeanMethods = false)
class GraphQlObservationConfiguration {

    @Bean
    DataLoaderObservationConvention dataLoaderObservationConvention() {
        return new DefaultDataLoaderObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    DataLoaderObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("graphql.loader.group", "catalog"));
            }
        };
    }
}
```

Đây là ví dụ cho một ứng dụng có nhóm loader catalog. Giá trị `catalog` được cố định nên có cardinality thấp. Nếu cần phân nhóm nhiều loader, hãy ánh xạ chúng vào một số nhóm được kiểm soát như `catalog`, `identity` hoặc `billing`.

Không thêm `userId`, `tenantId`, email, raw entity ID hoặc key list vào low-cardinality key. Nếu muốn thêm thông tin không giới hạn vào trace, cân nhắc high-cardinality key và chính sách che dữ liệu trước khi ghi.

## 14. Tùy chỉnh convention có cần thay `GraphQlObservationInstrumentation` không?

Khi dùng Spring Boot, convention bean được auto-configuration phát hiện. Thông thường không cần tự tạo `GraphQlObservationInstrumentation` chỉ để thay metadata DataLoader.

Với ứng dụng tự cấu hình `GraphQlSource`, có thể đăng ký instrumentation trên `GraphQlSource.Builder`:

```java
GraphQlObservationInstrumentation instrumentation =
    new GraphQlObservationInstrumentation(observationRegistry);

graphQlSourceBuilder.instrumentation(List.of(instrumentation));
```

Nếu tự tạo instrumentation trong ứng dụng Boot đã có auto-configuration, hãy kiểm tra danh sách instrumentation trước khi thêm để tránh cấu hình trùng lặp. Constructor hỗ trợ custom conventions từ Spring for GraphQL 1.4.0 có đủ bốn tham số: `ObservationRegistry`, request convention, DataFetcher convention và DataLoader convention.

## 15. Kết hợp DataLoader observation với database metrics

Observation `graphql.dataloader` đo hoạt động batch loading ở tầng GraphQL. Database metrics đo hoạt động ở tầng persistence. Hai góc nhìn bổ sung nhau:

| Tín hiệu | Câu hỏi trả lời |
|---|---|
| `graphql.request` | GraphQL request mất bao lâu? |
| `graphql.datafetcher` | Resolver field nào chậm hoặc lỗi? |
| `graphql.dataloader` | Batch loader nào chậm, thành công hay thất bại? |
| JDBC/R2DBC metrics | Database connection và thao tác truy cập dữ liệu có vấn đề gì? |
| SQL/query tracing | Batch loader thực hiện bao nhiêu câu SQL và câu nào chậm? |

Nếu `graphql.dataloader` mất 300 ms nhưng database query chỉ mất 10 ms, phần còn lại có thể nằm ở mapping, xử lý dữ liệu, remote service hoặc logic trong batch method. Nếu batch observation nhanh nhưng GraphQL request chậm, hãy xem các resolver khác, serialization, network hoặc các field không dùng DataLoader.

Không đoán nguyên nhân chỉ từ một timer. Đối chiếu trace cùng request, loader name và database spans để xác định phần tốn thời gian.

## 16. Kiểm tra metrics trong test

Có thể kiểm tra observation đã được ghi bằng một `MeterRegistry` trong test tích hợp. Test cần thực thi GraphQL query có field batch, sau đó đọc timer `graphql.dataloader` và lọc theo loader name.

Ví dụ ý tưởng với `MeterRegistry`:

```java
Timer timer = meterRegistry.find("graphql.dataloader")
    .tag("graphql.loader.name", Author.class.getName())
    .tag("graphql.outcome", "SUCCESS")
    .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isPositive();
```

Để test ổn định:

1. Dùng registry riêng cho test hoặc kiểm soát registry được Spring Boot inject.
2. Thực thi operation có chọn field `@BatchMapping`.
3. Đợi GraphQL execution hoàn tất trước khi đọc timer.
4. Lọc theo tên loader và outcome để tránh nhầm observation của operation khác.
5. Không assert chính xác duration vì thời gian phụ thuộc môi trường test.

Nếu test dùng một registry dùng chung giữa nhiều test, cần reset registry hoặc cô lập context để tránh số liệu cũ làm test pass sai.

## 17. Những câu hỏi chẩn đoán thường gặp

**Không thấy `graphql.dataloader`:** kiểm tra Spring for GraphQL có phiên bản từ 1.4.0 trở lên không; `ObservationRegistry` đã có chưa; `GraphQlObservationInstrumentation` có được cấu hình không; query có thực sự chọn field batch không.

**Có `graphql.datafetcher` nhưng không có `graphql.dataloader`:** field có thể đang dùng `@SchemaMapping` thông thường thay vì `@BatchMapping` hoặc DataLoader; hoặc batch loader chưa được đăng ký/dispatch.

**`graphql.loader.size` không xuất hiện trong metric:** đây là high-cardinality key, mặc định chỉ được đưa vào trace. Xem span hoặc trace thay vì tìm tag metrics.

**Batch observation có outcome `ERROR`:** kiểm tra exception từ batch method, database/service phụ thuộc và error type. Đối chiếu với `graphql.request` để xem lỗi có làm request thất bại hay chỉ ảnh hưởng field.

**Loader name không như mong đợi:** kiểm tra tên DataLoader trong `BatchLoaderRegistry` hoặc tên được tạo từ `@BatchMapping`; loader có thể được tùy chỉnh tên.

**Batch size nhỏ hơn số parent:** kiểm tra số key duy nhất, cache theo request, `maxBatchSize`, số lần dispatch và việc batch loader trả thiếu kết quả.

**Request chậm dù batch observation nhanh:** điều tra query root, các DataFetcher khác, database connection pool, network và response serialization.

## 18. Lỗi thường gặp khi thiết kế DataLoader observation

**Nhầm observation với số lần gọi `load(key)`.** Observation mô tả batch loader execution; nhiều key có thể được xử lý trong cùng một observation.

**Coi `graphql.loader.size` là low-cardinality metric tag.** Đây là high-cardinality key và chỉ dành cho trace theo convention mặc định.

**Dùng batch size để kết luận số SQL query.** Batch loader có thể chạy nhiều câu SQL hoặc gọi remote service; cần quan sát tầng persistence riêng.

**Không kiểm tra phiên bản Spring GraphQL.** DataLoader observation có từ 1.4.0. Ứng dụng dùng bản cũ không thể mong đợi observation này.

**Tự thêm instrumentation trong khi Boot đã auto-configure.** Có thể tạo cấu hình trùng hoặc làm khó kiểm tra kết quả. Ưu tiên convention bean khi chỉ cần thay metadata.

**Thêm ID hoặc key vào metrics tag.** Cardinality tăng nhanh và có nguy cơ lộ dữ liệu. Chỉ dùng low-cardinality label được kiểm soát.

**Chỉ xem metrics mà không xem trace.** Metrics cho biết xu hướng tổng thể; trace giúp tìm batch cụ thể trong một request chậm.

## Kết luận

Spring for GraphQL cung cấp observation `graphql.dataloader` để đo hoạt động của `@BatchMapping` và DataLoader đăng ký thủ công. Observation mặc định ghi loader name, outcome, error type và kích thước danh sách kết quả; trong đó `graphql.loader.size` là high-cardinality key dành cho trace. Khi bật `ObservationRegistry` và GraphQL instrumentation, ứng dụng có thể dùng metrics để theo dõi tần suất/thời gian/lỗi batch và dùng traces để tìm loader gây chậm hoặc phát hiện pattern N+1. Observation không đếm từng lệnh `load`, cache hit/miss hay SQL query, vì vậy hãy kết hợp với database metrics, query tracing và custom instrumentation khi cần những số liệu đó.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Request Execution and Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL API — `DataLoaderObservationContext`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationContext.html)
- [Spring for GraphQL API — `DataLoaderObservationConvention`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationConvention.html)
- [Spring Boot 3.5 — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
