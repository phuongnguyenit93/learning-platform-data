# Đo latency theo field trong Spring for GraphQL

Một GraphQL request có thể phân giải nhiều field, gọi nhiều service và truy vấn nhiều nguồn dữ liệu. Khi response chậm, chỉ nhìn thời gian tổng của request không cho biết field nào đang chiếm phần lớn thời gian. Spring for GraphQL tích hợp Micrometer Observation để đo thời gian thực thi của từng DataFetcher không tầm thường bằng observation `graphql.datafetcher`.

Observation này cung cấp timer và trace span gắn với field đang được phân giải. Nhờ các tag mặc định như `graphql.field.name`, `graphql.outcome` và `graphql.error.type`, có thể thống kê field nào thường chậm hoặc lỗi. Với trace, `graphql.field.path` giúp xác định vị trí field trong object graph của một request cụ thể.

## 1. Vì sao cần đo latency theo field?

Giả sử client gửi query:

```graphql
query BookDetails($id: ID!) {
    bookById(id: $id) {
        id
        title
        author {
            id
            name
            profile {
                biography
            }
        }
        reviews {
            rating
            comment
        }
    }
}
```

Request này có thể gọi nhiều DataFetcher:

- `bookById` tải thông tin sách.
- `author` tải tác giả của sách.
- `profile` tải hồ sơ tác giả.
- `reviews` tải danh sách đánh giá.

Nếu tổng request mất 900 ms, chưa thể biết phần nào chậm. Có thể `bookById` mất 30 ms, `author` mất 40 ms, `profile` mất 760 ms và `reviews` mất 70 ms. Đo latency theo field cho phép tìm đúng resolver cần điều tra.

Những câu hỏi thường gặp:

- Field nào có p95/p99 latency cao?
- Field nào thường trả về lỗi?
- Một field chậm trên mọi request hay chỉ ở một nhánh object graph?
- Thời gian chậm nằm ở resolver, batch loader, database hay remote service?
- Sau khi tối ưu một resolver, latency của field và request thay đổi thế nào?

## 2. Phân biệt request latency và field latency

Spring for GraphQL cung cấp hai observation có vai trò khác nhau:

| Observation | Phạm vi | Mục đích |
|---|---|---|
| `graphql.request` | Toàn bộ GraphQL execution request | Đo thời gian xử lý request và outcome tổng thể. |
| `graphql.datafetcher` | Một hoạt động DataFetcher không tầm thường | Đo thời gian phân giải một field. |

Một request có thể tạo một observation `graphql.request` và nhiều observation `graphql.datafetcher`.

```text
HTTP server request
       |
       v
  graphql.request
       |
       +---- graphql.datafetcher: bookById
       |
       +---- graphql.datafetcher: author
       |
       +---- graphql.datafetcher: profile
       |
       +---- graphql.datafetcher: reviews
       |
       v
  GraphQL response
```

Không cộng thời gian của tất cả field để suy ra request latency. GraphQL có thể thực thi các field độc lập song song; các khoảng thời gian có thể chồng lấp. Request latency phản ánh thời gian toàn execution, còn field latency phản ánh thời gian của từng hoạt động fetch.

Request observation cũng không nhất thiết bao gồm toàn bộ thời gian mạng từ client tới client. Transport như HTTP có thể có observation riêng. Khi điều tra end-to-end latency, cần xem cả transport, GraphQL request và các span phía dưới.

## 3. `graphql.datafetcher` được tạo khi nào?

Spring for GraphQL tạo DataFetcher observation cho các hoạt động fetching được xem là không tầm thường. Ví dụ:

- Method dùng `@QueryMapping`, `@MutationMapping` hoặc `@SchemaMapping` gọi service/repository.
- DataFetcher được đăng ký trực tiếp và thực hiện công việc tải dữ liệu.
- Các hoạt động fetch dữ liệu có logic riêng cần được đo.

Property fetching đơn giản từ một Java object, chẳng hạn GraphQL Java đọc trực tiếp `book.title` qua `PropertyDataFetcher`, là thao tác trivial và không có `graphql.datafetcher` observation riêng.

Điều này giúp tránh tạo quá nhiều observation cho những field chỉ đọc property trong bộ nhớ. Nếu một field cần gọi database hoặc remote service, hãy ánh xạ nó bằng DataFetcher/annotated controller để có thể quan sát công việc đó.

## 4. Metadata mặc định của DataFetcher observation

Spring for GraphQL dùng `DefaultDataFetcherObservationConvention`, dựa trên `DataFetcherObservationContext`.

Các key mặc định:

| Key | Cardinality | Ý nghĩa |
|---|---|---|
| `graphql.field.name` | Low | Tên field đang được phân giải. |
| `graphql.outcome` | Low | Kết quả `SUCCESS` hoặc `ERROR`. |
| `graphql.error.type` | Low | Tên class của lỗi data fetching nếu có. |
| `graphql.field.path` | High | Đường dẫn field trong GraphQL execution. |

Ví dụ một field `author` có thể có metadata:

```text
observation: graphql.datafetcher
graphql.field.name: author
graphql.outcome: SUCCESS
graphql.field.path: /bookById/author
```

`graphql.field.name` phù hợp để nhóm metrics theo field. `graphql.field.path` có thể khác nhau theo nhánh và index của list, vì vậy thuộc nhóm high cardinality và chỉ nên dùng cho tracing.

## 5. Low cardinality và high cardinality

Low-cardinality key có số lượng giá trị hữu hạn, có thể dùng làm tag cho metrics. High-cardinality key có thể sinh rất nhiều giá trị khác nhau, thích hợp hơn cho traces.

Với DataFetcher observation:

- `graphql.field.name`, `graphql.outcome`, `graphql.error.type` là low cardinality.
- `graphql.field.path` là high cardinality.

Không thêm các giá trị như user ID, tenant ID, email, raw GraphQL variables, entity ID hoặc query text vào low-cardinality metrics. Nếu một tag tạo ra hàng triệu tổ hợp, hệ thống metrics sẽ có rất nhiều time series, làm tăng chi phí lưu trữ và truy vấn.

Nếu cần tìm một field chậm trong một request cụ thể, dùng trace và field path. Nếu cần thống kê p95 của field trên hàng nghìn request, dùng metrics với field name và một tập tag có giới hạn.

## 6. Cấu hình observability với Spring Boot

Với Spring Boot, GraphQL observation instrumentation được auto-configure khi ứng dụng có `ObservationRegistry` và các dependency cần thiết. Spring Boot đăng ký `GraphQlObservationInstrumentation` vào GraphQL source và dùng các convention mặc định nếu ứng dụng không cung cấp convention riêng.

Dependencies minh họa với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Spring Boot quản lý phiên bản Spring for GraphQL và Micrometer tương thích. `micrometer-registry-prometheus` chỉ cần khi muốn xuất metrics sang Prometheus; có thể dùng registry khác nếu hạ tầng monitoring đang sử dụng hệ thống khác.

Các điểm cần kiểm tra:

1. Ứng dụng có `ObservationRegistry`.
2. GraphQL observation auto-configuration được kích hoạt.
3. `GraphQlObservationInstrumentation` có trong GraphQL source.
4. Meter registry và observation handler được cấu hình để xuất metrics.
5. Query thực sự gọi DataFetcher không tầm thường.

Observation chỉ được publish khi có `ObservationRegistry` được cấu hình. Với ứng dụng Spring Boot dùng Actuator, các thành phần này thường được auto-configure.

## 7. Cấu hình endpoint Actuator

Để kiểm tra metrics và cho Prometheus scrape, expose các endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Trong môi trường production, endpoint metrics cần được bảo vệ bằng security policy và chỉ expose tới hệ thống monitoring được phép truy cập.

Sau khi ứng dụng nhận GraphQL request, xem danh sách meter:

```text
GET /actuator/metrics
```

Kiểm tra timer theo field:

```text
GET /actuator/metrics/graphql.datafetcher
```

Lọc riêng một field:

```text
GET /actuator/metrics/graphql.datafetcher?tag=graphql.field.name:bookById
```

Lọc field thành công:

```text
GET /actuator/metrics/graphql.datafetcher?tag=graphql.field.name:bookById&tag=graphql.outcome:SUCCESS
```

Tên meter trong Actuator là `graphql.datafetcher`. Registry xuất metrics có thể chuẩn hóa tên này theo naming convention riêng; ví dụ Prometheus chuyển dấu chấm thành dấu gạch dưới.

## 8. Đọc timer theo field

Observation `graphql.datafetcher` được Micrometer ghi nhận thành timer khi observation hoàn tất. Timer có thể cung cấp:

- `count`: số lần field được thực thi.
- `totalTime`: tổng thời gian của các lần thực thi.
- `max`: thời gian lớn nhất trong cửa sổ thống kê được hỗ trợ.
- Percentiles hoặc histogram buckets nếu được cấu hình và registry hỗ trợ.

Ví dụ, một field có số liệu:

| Measurement | Giá trị minh họa | Ý nghĩa |
|---|---:|---|
| Count | 12.000 | Field được thực thi 12.000 lần trong phạm vi số liệu. |
| Total time | 720 giây | Tổng thời gian của các lần fetch. |
| Average | 60 ms | Trung bình mỗi lần fetch. |
| p95 | 180 ms | 95% lần fetch không vượt quá 180 ms. |
| p99 | 420 ms | 99% lần fetch không vượt quá 420 ms. |

Không dùng average làm chỉ số duy nhất. Một số ít request rất chậm có thể bị che khuất bởi nhiều request nhanh. p95/p99 thường hữu ích hơn khi đánh giá trải nghiệm thực tế và đặt SLO.

## 9. Bật percentile histogram và SLO boundary

Spring Boot cho phép cấu hình phân phối timer theo meter name. Ví dụ bật histogram cho `graphql.datafetcher` và đặt các ngưỡng SLO:

```properties
management.metrics.distribution.percentiles-histogram.graphql.datafetcher=true
management.metrics.distribution.slo.graphql.datafetcher=50ms,100ms,250ms
```

Histogram cho phép hệ thống monitoring tính percentile có thể tổng hợp giữa nhiều instance. SLO boundaries bổ sung bucket tại các ngưỡng mà ứng dụng quan tâm.

Nếu chỉ cấu hình `percentiles`, Micrometer tính percentile tại từng meter ID trong process; các percentile đó không thể cộng/gộp chính xác giữa nhiều instance. Với Prometheus, thường nên ưu tiên percentile histogram để dùng `histogram_quantile` trên bucket đã tổng hợp.

Histogram làm tăng số time series. Chỉ bật cho meter cần phân tích và giữ tag cardinality thấp.

## 10. Truy vấn percentile bằng Prometheus

Với timer Prometheus và percentile histogram được bật, có thể tính p95 theo field name:

```promql
histogram_quantile(
  0.95,
  sum by (le, graphql_field_name) (
    rate(graphql_datafetcher_seconds_bucket[5m])
  )
)
```

Prometheus naming convention thường chuyển `graphql.datafetcher` thành `graphql_datafetcher` và `graphql.field.name` thành `graphql_field_name`. Tên cụ thể phụ thuộc registry/exporter và cấu hình naming convention.

Tính latency trung bình theo field:

```promql
sum by (graphql_field_name) (
  rate(graphql_datafetcher_seconds_sum[5m])
)
/
sum by (graphql_field_name) (
  rate(graphql_datafetcher_seconds_count[5m])
)
```

Khi triển khai, hãy kiểm tra tên series thực tế tại Prometheus trước khi đưa query vào dashboard. Nếu không bật histogram, series `_bucket` sẽ không được xuất.

## 11. Dùng trace để tìm field chậm trong một request

Metrics cho biết xu hướng tổng thể. Trace giúp điều tra một request cụ thể.

Một trace có thể có cấu trúc:

```text
HTTP server request
  |
  +-- graphql.request
        |
        +-- graphql.datafetcher: bookById
        |
        +-- graphql.datafetcher: author
        |
        +-- graphql.datafetcher: profile
        |      |
        |      +-- database query
        |
        +-- graphql.datafetcher: reviews
```

Trong trace, xem:

- Field name để xác định resolver.
- Field path để xác định nhánh object graph.
- Thời lượng span để biết field mất bao lâu.
- Error event/exception để biết resolver thất bại ở đâu.
- Các span con của database hoặc HTTP client để xác định dependency chậm.

Để trace GraphQL được liên kết với HTTP request, cần transport instrumentation và context propagation phù hợp. Spring Framework có HTTP observation instrumentation; tracing exporter như OTLP có thể chuyển spans tới backend quan sát.

## 12. Ví dụ schema và controller có field cần đo

SDL:

```graphql
type Query {
    bookById(id: ID!): Book
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

Model minh họa:

```java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}
```

Controller:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

Trong ví dụ, `bookById` và `author` là các DataFetcher có logic riêng, do đó có thể được đo bằng `graphql.datafetcher`. Nếu `Book.author` chỉ là property Java được đọc trực tiếp và không có `@SchemaMapping`, property fetcher mặc định không tạo observation riêng.

Khi đo thấy `author` có p95 cao, trace có thể cho biết thời gian nằm ở `authorService.findById`, hoặc một span database/HTTP con. Nếu query chọn nhiều sách, cần xem thêm việc field này có bị gọi lặp lại cho từng parent và có nên chuyển sang `@BatchMapping` hay DataLoader.

## 13. Tùy chỉnh `DataFetcherObservationConvention`

Convention mặc định dùng field name, outcome và error type làm low-cardinality metadata; field path là high-cardinality metadata.

Nếu cần nhóm field theo domain, có thể cung cấp một `DataFetcherObservationConvention` bean. Ví dụ thêm nhãn `graphql.field.group` với tập giá trị cố định:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DataFetcherObservationContext;
import org.springframework.graphql.observation.DataFetcherObservationConvention;
import org.springframework.graphql.observation.DefaultDataFetcherObservationConvention;

@Configuration(proxyBeanMethods = false)
class GraphQlObservationConfiguration {

    @Bean
    DataFetcherObservationConvention dataFetcherObservationConvention() {
        return new DefaultDataFetcherObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    DataFetcherObservationContext context) {

                String fieldName = context.getEnvironment()
                    .getFieldDefinition()
                    .getName();

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("graphql.field.group", fieldGroup(fieldName)));
            }
        };
    }

    private String fieldGroup(String fieldName) {
        return switch (fieldName) {
            case "bookById", "books" -> "catalog";
            case "author", "profile" -> "identity";
            case "reviews" -> "feedback";
            default -> "other";
        };
    }
}
```

Spring Boot tự phát hiện convention bean và truyền vào `GraphQlObservationInstrumentation`. Việc kế thừa `DefaultDataFetcherObservationConvention` giữ lại các key mặc định và chỉ bổ sung một tag mới.

Các giá trị `catalog`, `identity`, `feedback`, `other` là tập hữu hạn nên phù hợp với low cardinality. Nếu đưa raw field path hoặc ID vào tag này, số lượng time series có thể tăng nhanh.

## 14. Khi nào cần phân biệt cùng tên field trên nhiều type?

`graphql.field.name` chỉ chứa tên field. Một schema có thể có nhiều type cùng khai báo field `id`, `name`, `status` hoặc `createdAt`. Khi gom metrics theo field name, các field cùng tên có thể nằm chung một nhóm.

Nếu cần phân biệt, có thể bổ sung nhãn parent type hoặc field group bằng custom convention. Ví dụ:

```java
import graphql.schema.GraphQLNamedType;
import graphql.schema.GraphQLType;

@Override
public KeyValues getLowCardinalityKeyValues(DataFetcherObservationContext context) {
    GraphQLType type = context.getEnvironment().getParentType();
    String parentType = (type instanceof GraphQLNamedType namedType)
        ? namedType.getName() : "unknown";

    return super.getLowCardinalityKeyValues(context)
        .and(KeyValue.of("graphql.parent.type", parentType));
}
```

Đây là phần bổ sung trong convention bean ở phần trước. `DataFetcherObservationContext.getEnvironment()` cung cấp `DataFetchingEnvironment` để đọc field definition, parent type và execution metadata.

Parent type thường được giới hạn bởi schema nên có cardinality hữu hạn. Tuy vậy, hãy kiểm soát schema và không đưa tên type được sinh động từ dữ liệu người dùng vào metrics tag.

Nếu cần phân tích chính xác một lần gọi cụ thể, `graphql.field.path` trong trace đã cung cấp ngữ cảnh chi tiết mà không làm phình metrics.

## 15. Phân biệt field latency với DataLoader latency

Khi field dùng `@BatchMapping` hoặc DataLoader đăng ký thủ công, cần xem cả hai lớp quan sát:

| Observation | Đo gì? | Khi dùng |
|---|---|---|
| `graphql.datafetcher` | DataFetcher không tầm thường | Resolver như query root hoặc field mapping. |
| `graphql.dataloader` | Lần thực thi batch loader | `@BatchMapping` và DataLoader thủ công. |

Một field được giải quyết bằng batch loader có thể có hoạt động `graphql.dataloader` riêng. Không cộng thời gian của hai observation như hai công việc độc lập nếu chúng bao phủ cùng một luồng xử lý.

Khi field latency cao, hãy xác định resolver có đang gọi backend từng parent hay không. Nếu có N+1, chuyển sang batch loading có thể giảm số round-trip. Sau thay đổi, so sánh cả field timing, DataLoader timing và database metrics.

## 16. Phân tích lỗi theo field

DataFetcher observation có `graphql.outcome` với giá trị `SUCCESS` hoặc `ERROR`. Khi có lỗi, `graphql.error.type` cho biết class của data fetching error.

Ví dụ:

```text
observation: graphql.datafetcher
graphql.field.name: author
graphql.outcome: ERROR
graphql.error.type: AuthorServiceException
```

Metrics có thể cho biết field nào thường lỗi, còn trace/log giúp xác định request và nguyên nhân. Nên thống kê theo error type thay vì thêm exception message tự do vào metrics tag.

Nếu exception được ánh xạ thành GraphQL error qua `DataFetcherExceptionResolver`, vẫn cần kiểm tra cách ứng dụng xử lý và phân loại lỗi trong execution. Không ghi thông tin nhạy cảm hoặc stack trace vào GraphQL response chỉ để dễ quan sát.

## 17. Kiểm thử field observation bằng `MeterRegistry`

Có thể dùng integration test để thực thi một GraphQL query rồi xác minh timer của field đã được ghi nhận. Ví dụ với Spring Boot:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class GraphQlFieldObservationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void recordsLatencyForBookById() {
        graphQlTester.document("""
                query {
                    bookById(id: "book-1") {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("bookById.id")
            .entity(String.class)
            .isEqualTo("book-1");

        Timer timer = meterRegistry.find("graphql.datafetcher")
            .tag("graphql.field.name", "bookById")
            .tag("graphql.outcome", "SUCCESS")
            .timer();

        assertThat(timer).isNotNull();
        assertThat(timer.count()).isPositive();
    }
}
```

Ví dụ giả định ứng dụng đã có schema, resolver trả về `book-1`, Actuator/Micrometer observation được cấu hình và `@AutoConfigureHttpGraphQlTester` thuộc phiên bản Spring Boot đang dùng. Cần import `MeterRegistry`, `Timer` và assertion library tương ứng trong test.

Imports trên dùng Spring Boot 3.x. Với Spring Boot 4.x, package của test auto-configuration được chuyển sang `org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureHttpGraphQlTester`.

Không assert duration bằng một con số chính xác vì thời gian phụ thuộc máy chạy test và tải hệ thống. Hãy xác minh timer tồn tại, count tăng và tag đúng. Nếu test dùng registry chung giữa nhiều test, reset hoặc cô lập context để tránh dữ liệu cũ làm test pass sai.

## 18. Quy trình điều tra field chậm

Khi dashboard cho thấy field `profile` có p95 tăng, có thể điều tra theo thứ tự:

1. Lọc `graphql.datafetcher` theo `graphql.field.name=profile` và `graphql.outcome=SUCCESS` để xem latency của các lần thành công.
2. Xem thêm `graphql.outcome=ERROR` và `graphql.error.type` để xác định lỗi có tăng cùng lúc hay không.
3. Mở trace của request chậm để xem `graphql.field.path` và các span con.
4. Kiểm tra span database hoặc HTTP client để xác định dependency chậm.
5. Nếu field nằm trong list lớn, kiểm tra số lần fetch và khả năng N+1.
6. Cân nhắc batch loading, pagination, projection hoặc cache phù hợp.
7. Triển khai thay đổi và so sánh p50/p95/p99 trước và sau.

Ví dụ bảng điều tra:

| Dấu hiệu | Hướng kiểm tra |
|---|---|
| Field p95 tăng, database span cũng tăng | Query plan, index, lock, connection pool. |
| Field p95 tăng, database span bình thường | Mapping, xử lý trong service, remote call hoặc CPU. |
| Field count tăng theo số parent object | Kiểm tra N+1 và `@BatchMapping`. |
| Field error tăng | Exception resolver, dependency failure, timeout. |
| Request chậm nhưng các field đều nhanh | Parse/validation, transport, serialization hoặc scheduling. |

## 19. Lưu ý về subscription và field được resolve nhiều lần

Subscription là một luồng event kéo dài. Observation của DataFetcher đo hoạt động fetching được GraphQL instrumentation bao quanh; nó không tự thay thế metric về thời gian chờ giữa hai event, tốc độ phát event hoặc thời gian client nhận event.

Nếu cần quan sát subscription, hãy kết hợp:

- `graphql.request` cho execution/operation theo cách transport hỗ trợ.
- DataFetcher observation cho hoạt động fetch field.
- `graphql.dataloader` nếu subscription dùng batch loading.
- Transport metrics và custom metrics cho số event, thời gian giữa event, số stream đang hoạt động và cancellation.

Một field có thể được phân giải nhiều lần trong một request, ví dụ khi nằm trong danh sách nhiều parent object. Metrics theo field name sẽ tổng hợp các lần gọi; trace path giúp phân biệt vị trí cụ thể trong object graph.

## 20. Lỗi thường gặp

**Chỉ xem `graphql.request` để tìm field chậm.** Request timer chỉ cho biết tổng thời gian; cần `graphql.datafetcher` để phân tích từng resolver.

**Cho rằng mọi field đều có DataFetcher observation.** Property fetcher đơn giản trên Java object là thao tác trivial và không được đo riêng.

**Dùng `graphql.field.path` làm metrics tag.** Đây là high-cardinality key, nên dành cho trace. Dùng `graphql.field.name` hoặc nhóm field có giới hạn cho metrics.

**Cộng tất cả field duration để suy ra request duration.** Các field có thể chạy song song và thời gian bị chồng lấp.

**Nhầm DataFetcher latency với SQL latency.** Field observation bao gồm công việc trong DataFetcher; cần database instrumentation để tách thời gian query và connection.

**Không cấu hình `ObservationRegistry`.** Nếu registry/instrumentation không hoạt động, sẽ không có `graphql.datafetcher` observation.

**Tùy chỉnh convention nhưng ghi đè mất tag mặc định.** Khi kế thừa default convention, hãy gọi `super.getLowCardinalityKeyValues(context)` rồi bổ sung tag.

**Bật histogram cho mọi meter.** Histogram tạo thêm time series. Chỉ bật cho meter cần percentile/SLO.

**Đưa user ID, tenant ID hoặc query text vào metrics tag.** Cardinality và nguy cơ lộ dữ liệu tăng cao. Chỉ dùng các nhãn có tập giá trị hữu hạn.

## Kết luận

Đo latency theo field trong Spring for GraphQL được thực hiện qua Micrometer observation `graphql.datafetcher`, được tạo cho các DataFetcher không tầm thường. Tag mặc định `graphql.field.name`, `graphql.outcome` và `graphql.error.type` phù hợp với metrics; `graphql.field.path` là high-cardinality và phù hợp với tracing. Spring Boot có thể tự cấu hình `GraphQlObservationInstrumentation` khi có `ObservationRegistry`; Actuator cung cấp endpoint để kiểm tra timer và Micrometer hỗ trợ percentile histogram/SLO. Khi điều tra field chậm, hãy kết hợp request timer, field timer, trace span, DataLoader observation và database metrics để xác định đúng tầng gây latency.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL API — `GraphQlObservationInstrumentation`](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL API — `DataFetcherObservationContext`](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/observation/DataFetcherObservationContext.html)
- [Spring for GraphQL API — `DataFetcherObservationConvention`](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/observation/DataFetcherObservationConvention.html)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot 3.5 — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
