# ObservationRegistry

Trong một ứng dụng Spring for GraphQL, một request có thể đi qua HTTP hoặc WebSocket, thực thi nhiều field resolver, gọi database, sử dụng DataLoader và trả về một phần dữ liệu kèm lỗi. Khi API chậm hoặc lỗi, chỉ nhìn log của controller thường không đủ để xác định request mất thời gian ở transport, GraphQL execution, một DataFetcher hay một lần batch load.

**ObservationRegistry** là thành phần trung tâm của Micrometer Observation. Nó giữ cấu hình và các handler xử lý vòng đời observation. Spring for GraphQL dùng **GraphQlObservationInstrumentation** để ghi nhận thời gian và metadata cho GraphQL request, các thao tác DataFetcher không tầm thường và DataLoader. Các observation này có thể được chuyển thành metrics và distributed traces thông qua handler tương ứng.

Bài này giải thích vai trò của ObservationRegistry, các building block của Micrometer Observation, cách Spring for GraphQL tích hợp instrumentation, cách bật observability trong Spring Boot, cách đọc observation mặc định, tùy biến convention, tạo custom observation, truyền context qua luồng đồng bộ và reactive, kiểm thử và xử lý các vấn đề thường gặp.

## 1. ObservationRegistry là gì?

**ObservationRegistry** thuộc package io.micrometer.observation. Đây là nơi quản lý cấu hình liên quan đến Observation, chẳng hạn:

- ObservationHandler: nhận các sự kiện trong vòng đời observation và tạo metrics, spans hoặc log.
- ObservationPredicate: quyết định có tạo observation hay thay bằng no-op observation.
- ObservationFilter: bổ sung hoặc điều chỉnh context trước khi observation dừng.
- ObservationConvention: định nghĩa tên observation và metadata cần thu thập.

ObservationRegistry cũng quản lý observation hiện tại và scope của nó. Nhờ vậy, các thành phần có thể liên kết công việc đang thực hiện với observation cha, thay vì tự tạo một cơ chế tracing riêng.

Có thể hình dung:

~~~text
GraphQL request
      |
      v
GraphQlObservationInstrumentation
      |
      v
ObservationRegistry
      |
      +--> ObservationHandler --> MeterRegistry --> Metrics backend
      |
      +--> ObservationHandler --> Tracer --------> Trace backend
      |
      +--> ObservationFilter
      |
      +--> ObservationPredicate
      |
      +--> ObservationConvention
~~~

ObservationRegistry không phải nơi lưu trữ tất cả metric samples và cũng không phải trace backend. Nó điều phối observation lifecycle. Các handler kết nối observation với hệ thống đo lường hoặc tracing.

## 2. Phân biệt ObservationRegistry, MeterRegistry và Tracer

Ba thành phần có vai trò khác nhau:

| Thành phần | Vai trò |
|---|---|
| ObservationRegistry | Quản lý Observation, context, handler, filter, predicate và convention |
| MeterRegistry | Lưu và xuất meter như Counter, Timer, Gauge |
| Tracer | Tạo và quản lý span trong distributed trace |

Ví dụ, một GraphQL request hoàn tất sau 120 ms:

- ObservationRegistry điều phối observation của request.
- Meter handler có thể ghi thời lượng vào Timer trong MeterRegistry.
- Tracing handler có thể tạo span tương ứng trong trace.

Ứng dụng không cần tự viết một đoạn code riêng để vừa đo Timer vừa tạo span cho cùng một thao tác. Micrometer Observation cung cấp lớp API chung để các handler xử lý hai loại dữ liệu này.

## 3. Các thành phần của Micrometer Observation

### Observation

**Observation** biểu diễn một hoạt động cần đo, ví dụ một GraphQL request hoặc một lần tải dữ liệu từ repository. Observation có tên, context, key-value metadata và vòng đời.

Một observation thường trải qua các bước:

1. Tạo observation.
2. Bắt đầu observation.
3. Mở scope để đặt observation thành hoạt động hiện tại.
4. Chạy công việc.
5. Ghi nhận exception hoặc event nếu có.
6. Đóng scope và dừng observation.

Phương thức observe(...) giúp thực hiện chu trình đó cho một đoạn code đồng bộ:

~~~java
Observation.createNotStarted("catalog.book.lookup", observationRegistry)
        .lowCardinalityKeyValue("result", "cache")
        .observe(() -> bookService.loadBook(bookId));
~~~

Trong ví dụ, thời gian chạy của loadBook được đo trong observation catalog.book.lookup. Nếu lambda ném exception, Observation API có thể ghi nhận lỗi trước khi kết thúc.

### Observation.Context

**Observation.Context** là vùng dữ liệu có thể thay đổi gắn với một observation. Instrumentation và handler dùng context để chia sẻ metadata hoặc trạng thái trong suốt vòng đời.

Context có thể chứa thông tin về request, response, exception, field đang được resolve hoặc dữ liệu cần thiết để tạo key-value.

Context giúp truyền trạng thái giữa các handler mà không cần đặt mọi dữ liệu vào ThreadLocal.

### ObservationHandler

**ObservationHandler** phản ứng với các sự kiện như start, stop, error, event và scope lifecycle. Handler chỉ xử lý những context mà phương thức supportsContext(...) chấp nhận.

Ví dụ, meter handler tạo Timer từ thời gian observation; tracing handler tạo span và thêm các thuộc tính vào span.

Nhiều handler có thể cùng nhận một observation. Nhờ vậy một hoạt động có thể tạo cả metric lẫn trace.

### ObservationConvention

**ObservationConvention** tách việc đặt tên và metadata khỏi logic bắt đầu/dừng observation. Convention xác định:

- Tên observation.
- Contextual name hiển thị trong trace.
- Low-cardinality key-values.
- High-cardinality key-values.

Spring for GraphQL cung cấp convention mặc định cho request, DataFetcher và DataLoader. Ứng dụng có thể cung cấp convention riêng để bổ sung metadata phù hợp.

### ObservationPredicate và ObservationFilter

ObservationPredicate quyết định có tạo observation hay không. Có thể dùng predicate để loại một nhóm observation khỏi hệ thống.

ObservationFilter thay đổi context trước khi observation dừng. Ví dụ filter có thể thêm metadata đã được chuẩn hóa hoặc bổ sung thông tin môi trường.

Không dùng filter để gắn dữ liệu riêng tư vào mọi observation. Metadata phải có mục đích quan sát rõ ràng và tuân thủ quy tắc cardinality.

## 4. Low cardinality và high cardinality

Micrometer chia key-value metadata thành hai nhóm:

**Low cardinality** có số lượng giá trị hữu hạn hoặc bị giới hạn, ví dụ operation type có thể là query, mutation hoặc subscription. Các giá trị này có thể dùng làm tag cho metrics và cũng có thể xuất hiện trong traces.

**High cardinality** có thể có rất nhiều giá trị khác nhau, ví dụ execution ID, user ID hoặc đường dẫn chứa ID của từng resource. Các giá trị này chỉ nên được đưa vào traces, không nên trở thành metric tags.

| Loại | Ví dụ | Nơi sử dụng |
|---|---|---|
| Low cardinality | operation.type=query | Metrics và traces |
| Low cardinality | outcome=SUCCESS | Metrics và traces |
| High cardinality | execution.id=giá trị riêng từng request | Traces |
| High cardinality | field.path=/bookById/author | Traces |
| High cardinality | user.id hoặc resource.id | Chỉ khi thực sự cần trong traces và đã đánh giá riêng tư |

Nếu đưa một giá trị gần như duy nhất cho mỗi request vào metric tag, số lượng time series có thể tăng rất nhanh. Hệ quả là metrics backend tốn bộ nhớ, truy vấn chậm và chi phí lưu trữ cao.

Không đưa raw GraphQL document, variable values, email, token hoặc thông tin cá nhân vào metric tags. High cardinality không đồng nghĩa với việc dữ liệu nhạy cảm trở nên an toàn; trace vẫn có thể được lưu trữ và truy cập bởi nhiều người.

## 5. ObservationRegistry trong Spring for GraphQL

Spring for GraphQL tích hợp Micrometer Observation thông qua **GraphQlObservationInstrumentation** trong package org.springframework.graphql.observation.

Instrumentation này tạo observation trong quá trình GraphQL Java thực thi request. Nó có thể đo:

- Thời gian thực thi một GraphQL server request.
- Thời gian của DataFetcher không tầm thường.
- Thời gian của DataLoader, bao gồm các batch loader được đăng ký qua @BatchMapping hoặc DataLoader thủ công.

Observation chỉ được xuất bản khi instrumentation sử dụng một ObservationRegistry đã được cấu hình với các handler phù hợp. Chỉ thêm annotation vào resolver hoặc thêm dependency Micrometer không đảm bảo metrics và traces đã được xuất.

## 6. Ba nhóm GraphQL observation mặc định

Spring for GraphQL cung cấp ba nhóm observation với tên mặc định:

| Observation name | Phạm vi đo | Khi nào được tạo |
|---|---|---|
| graphql.request | Toàn bộ GraphQL operation ở server | Mỗi GraphQL request |
| graphql.datafetcher | Một thao tác lấy dữ liệu của field | Với DataFetcher không tầm thường |
| graphql.dataloader | Một lần batch load | Với @BatchMapping và DataLoader đăng ký thủ công; hỗ trợ từ Spring GraphQL 1.4 |

Một request có thể tạo một observation graphql.request và nhiều observation graphql.datafetcher. Nếu resolver dùng DataLoader, các lần batch load còn có thể tạo observation graphql.dataloader.

~~~mermaid
flowchart TD
    A[HTTP request observation] --> B[graphql.request]
    B --> C[graphql.datafetcher: Query.books]
    B --> D[graphql.datafetcher: Book.author]
    D --> E[graphql.dataloader: authorLoader]
    B --> F[GraphQL response]
~~~

### 6.1. GraphQL request observation

Observation có tên **graphql.request** đo thời gian thực thi một GraphQL request. Nó hoạt động với ứng dụng Servlet và Reactive, cùng các transport được hỗ trợ.

Convention mặc định là **DefaultExecutionRequestObservationConvention**, dựa trên **ExecutionRequestObservationContext**.

Các low-cardinality key mặc định:

| Key | Ý nghĩa |
|---|---|
| graphql.operation.type | Loại operation: query, mutation, subscription hoặc operation nếu không phân tích được document |
| graphql.outcome | Kết quả xử lý request |

Các high-cardinality key mặc định:

| Key | Ý nghĩa |
|---|---|
| graphql.execution.id | ExecutionId của GraphQL request |
| graphql.operation.name | Operation name do client cung cấp |

Giá trị của graphql.outcome:

| Outcome | Khi nào xảy ra |
|---|---|
| SUCCESS | Response GraphQL hợp lệ được gửi và không có errors |
| REQUEST_ERROR | Request không parse được hoặc response có errors, nhưng không có error thuộc INTERNAL_ERROR |
| INTERNAL_ERROR | Không tạo được response GraphQL hợp lệ hoặc response có ít nhất một error INTERNAL_ERROR |

Spring for GraphQL còn ghi nhận GraphQL errors dưới dạng Observation Event. Các event này thường được tracing handler thể hiện như span event hoặc annotation. Tên event phản ánh loại GraphQL error; contextual name có thể chứa thông điệp lỗi đầy đủ.

### 6.2. DataFetcher observation

Observation có tên **graphql.datafetcher** đo thời gian chạy của một thao tác lấy dữ liệu trong GraphQL execution. Spring for GraphQL không tạo observation cho mọi property fetcher đơn giản. Việc đọc property trực tiếp từ Java object được xem là thao tác trivial và thường không cần một span riêng.

Convention mặc định là **DefaultDataFetcherObservationConvention**, dựa trên **DataFetcherObservationContext**.

Các low-cardinality key mặc định:

| Key | Ý nghĩa |
|---|---|
| graphql.error.type | Tên class của lỗi khi DataFetcher thất bại |
| graphql.field.name | Tên field đang được resolve |
| graphql.outcome | SUCCESS hoặc ERROR |

High-cardinality key mặc định:

| Key | Ý nghĩa |
|---|---|
| graphql.field.path | Đường dẫn của field trong GraphQL response, ví dụ /bookById/author |

DataFetcher observation hữu ích để tìm field nào tiêu tốn nhiều thời gian. Ví dụ, tổng thời gian của query chỉ 100 ms nhưng field Book.author mất 80 ms, có thể cần kiểm tra repository hoặc remote service mà resolver gọi.

### 6.3. DataLoader observation

Từ Spring for GraphQL 1.4, **graphql.dataloader** observation đo hoạt động của DataLoader, bao gồm batch method được tạo từ @BatchMapping và DataLoader đăng ký thủ công.

Convention mặc định là **DefaultDataLoaderObservationConvention**, dựa trên **DataLoaderObservationContext**.

Các low-cardinality key mặc định:

| Key | Ý nghĩa |
|---|---|
| graphql.error.type | Tên class của lỗi khi batch load thất bại |
| graphql.loader.name | Tên DataLoader đang được sử dụng |
| graphql.outcome | SUCCESS hoặc ERROR |

High-cardinality key mặc định:

| Key | Ý nghĩa |
|---|---|
| graphql.loader.size | Số phần tử trong danh sách được load |

Observation này giúp kiểm tra batch load có gom được nhiều key hay không. Nếu loader thường xuyên nhận batch size bằng 1, cần xem lại cách field được resolve, thời điểm DataLoader dispatch hoặc cách client xây selection set.

## 7. Bật GraphQL observations trong Spring Boot

Với Spring Boot, nên dùng auto-configuration để tạo ObservationRegistry, handlers và GraphQL instrumentation. Dependency thường dùng:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-graphql")
implementation("org.springframework.boot:spring-boot-starter-actuator")
runtimeOnly("io.micrometer:micrometer-registry-prometheus")
~~~

Starter Actuator cung cấp hạ tầng observability và quản lý metrics. Prometheus registry là một lựa chọn exporter; có thể thay bằng registry phù hợp với hệ thống monitoring đang dùng.

Ví dụ cấu hình endpoint quản lý:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Với Spring Boot 3 trở lên, GraphQL observation auto-configuration có thể đăng ký GraphQlObservationInstrumentation khi có GraphQL infrastructure và ObservationRegistry. Không cần tự thêm instrumentation lần nữa nếu auto-configuration đã làm việc đó.

Các bước kiểm tra:

1. Ứng dụng có Spring Boot Actuator và dependency GraphQL phù hợp.
2. Application context có ObservationRegistry.
3. GraphQL instrumentation được đăng ký vào GraphQlSource.
4. Có meter handler hoặc tracing handler phù hợp.
5. Có exporter hoặc endpoint để đọc kết quả.

Có thể kiểm tra danh sách metric qua endpoint /actuator/metrics và scrape Prometheus qua /actuator/prometheus nếu endpoint đã được expose và bảo vệ đúng cách.

Để có distributed traces, cần cấu hình thêm Micrometer Tracing bridge và exporter tương ứng, ví dụ hệ thống dựa trên OpenTelemetry hoặc Brave. Chỉ bật metrics registry không tự tạo trace backend.

## 8. Cấu hình thủ công khi không dùng Spring Boot

Nếu ứng dụng Spring Framework tự cấu hình GraphQlSource, có thể thêm GraphQlObservationInstrumentation vào GraphQlSource.Builder:

~~~java
GraphQlObservationInstrumentation instrumentation =
        new GraphQlObservationInstrumentation(observationRegistry);

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResource)
        .instrumentation(List.of(instrumentation))
        .build();
~~~

GraphQlObservationInstrumentation nhận ObservationRegistry và sử dụng convention mặc định nếu không truyền convention riêng.

Trong ứng dụng không dùng Boot, cần tự cấu hình ObservationHandler. Ví dụ, nếu muốn ghi Timer, đăng ký DefaultMeterObservationHandler với MeterRegistry; nếu muốn tạo span, đăng ký tracing handler tương ứng.

~~~java
ObservationRegistry observationRegistry = ObservationRegistry.create();
observationRegistry.observationConfig()
        .observationHandler(
                new DefaultMeterObservationHandler(meterRegistry));
~~~

Các import chính cho ví dụ này:

~~~java
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
~~~

Đoạn code trên chỉ đăng ký meter handler. Muốn xuất distributed traces cần tracing handler và tracer được cấu hình riêng.

Nếu GraphQlSource đã có instrumentation khác, cần giữ lại các instrumentation hiện có khi bổ sung GraphQlObservationInstrumentation. Không thay toàn bộ danh sách bằng một instrumentation mới nếu việc đó làm mất instrumentation cho tracing, security hoặc chức năng khác.

## 9. Tùy biến ObservationConvention

Convention mặc định cung cấp metadata chung cho mọi ứng dụng. Khi cần thêm thông tin có số lượng giá trị giới hạn, có thể cung cấp convention riêng.

Với Spring Boot, cách ưu tiên là khai báo bean triển khai convention tương ứng. GraphQL observation auto-configuration sẽ sử dụng bean đó thay cho convention mặc định.

Ví dụ thêm nhãn cố định để phân biệt nhóm API:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestConvention() {
        return new DefaultExecutionRequestObservationConvention() {
            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of("graphql.api", "catalog"));
            }
        };
    }
}
~~~

Các import chính:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;
~~~

Ở đây graphql.api luôn có giá trị catalog. Đây là low-cardinality key phù hợp cho metrics vì số lượng giá trị được giới hạn theo nhóm API.

Có thể tùy biến các nhóm convention khác:

- ExecutionRequestObservationConvention: metadata của toàn request.
- DataFetcherObservationConvention: metadata của field resolver.
- DataLoaderObservationConvention: metadata của batch load, có từ Spring GraphQL 1.4.

Khi tự tạo convention, hãy giữ các key bắt buộc của convention mặc định. Cách đơn giản là kế thừa default convention và mở rộng KeyValues, thay vì viết lại toàn bộ key-value logic.

### Khi không dùng Spring Boot

Có thể truyền convention trực tiếp vào GraphQlObservationInstrumentation. Từ Spring GraphQL 1.4, constructor đầy đủ nhận registry và ba convention:

~~~java
GraphQlObservationInstrumentation instrumentation =
        new GraphQlObservationInstrumentation(
                observationRegistry,
                requestConvention,
                dataFetcherConvention,
                dataLoaderConvention);
~~~

Constructor cũ chỉ nhận request và DataFetcher convention đã deprecated từ 1.4 để chuyển sang constructor có thêm DataLoader convention. Hãy dùng API phù hợp với phiên bản Spring for GraphQL đang có trong dự án.

## 10. Tạo custom observation trong resolver hoặc service

GraphQL instrumentation đo thời gian tổng thể của request và các thao tác DataFetcher. Tuy nhiên, một resolver có thể gọi nhiều bước bên trong, ví dụ đọc cache, gọi dịch vụ tìm kiếm và tải dữ liệu từ repository.

Có thể tạo observation riêng cho một bước nghiệp vụ cần theo dõi:

~~~java
@Service
public class BookEnrichmentService {

    private final ObservationRegistry observationRegistry;

    public BookEnrichmentService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public BookDetails enrich(Book book, boolean cacheHit) {
        return Observation.createNotStarted(
                        "catalog.book.enrichment",
                        this.observationRegistry)
                .lowCardinalityKeyValue(
                        "cache.result",
                        cacheHit ? "hit" : "miss")
                .observe(() -> loadDetails(book));
    }

    private BookDetails loadDetails(Book book) {
        // Load supplementary data for the book.
        return new BookDetails(book.getId(), book.getTitle());
    }
}
~~~

Observation catalog.book.enrichment có thể xuất hiện bên trong GraphQL request observation. Nhờ đó trace giúp phân biệt thời gian của toàn operation, thời gian resolver và thời gian riêng của bước enrichment.

Chỉ thêm metadata có tập giá trị nhỏ vào low-cardinality key. Ví dụ cache.result có hai giá trị hit và miss. Không đưa book ID hoặc user ID vào metric tags.

Phương thức observe(...) ở ví dụ phù hợp với công việc đồng bộ. Nếu service trả Mono hoặc Flux, không bọc việc tạo Publisher trong observe(...) rồi cho rằng toàn bộ công việc bất đồng bộ đã được đo; lambda đồng bộ có thể kết thúc ngay khi Publisher được tạo. Với reactive pipeline, hãy dùng cơ chế observation/context propagation tương thích Reactor hoặc để instrumentation của framework quản lý lifecycle.

## 11. Liên kết GraphQL observation với HTTP trace

GraphQL engine chạy phía trên transport. Khi client gửi HTTP request, Spring Framework có thể tạo HTTP server observation và trace context cho request đó. Spring for GraphQL tạo observation graphql.request cho phần GraphQL execution.

Khi context được truyền đúng, GraphQL request observation có thể trở thành child span của HTTP server span. DataFetcher và DataLoader observations tiếp tục nằm trong trace của GraphQL request.

~~~mermaid
flowchart TD
    A[HTTP client span] --> B[HTTP server observation]
    B --> C[graphql.request]
    C --> D[graphql.datafetcher]
    D --> E[graphql.dataloader]
    D --> F[Database client observation]
    D --> G[Remote service client observation]
~~~

Spring for GraphQL dùng key context đã quy ước **micrometer.observation** trong GraphQL context để xác định parent observation hiện tại. Instrumentation ở tầng transport chịu trách nhiệm truyền trace context qua ranh giới mạng. Với HTTP, Spring Framework có instrumentation riêng để xử lý trace propagation.

GraphQlObservationInstrumentation không tự thay thế HTTP instrumentation. Nếu chỉ đăng ký GraphQL instrumentation mà transport không truyền parent context, trace có thể không có quan hệ cha-con như mong muốn.

### Context propagation với WebFlux và tác vụ bất đồng bộ

Với Spring MVC, context thường đi cùng request thread. Với WebFlux, một request có thể chuyển qua nhiều thread trong Reactor pipeline, nên không thể giả định ThreadLocal luôn có mặt ở mọi operator.

Micrometer Context Propagation hỗ trợ chuyển thông tin context giữa các cơ chế thực thi. Trong Spring Boot, có thể bật automatic Reactor context propagation bằng:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Với AsyncTaskExecutor do Spring Boot auto-configure, có thể bật truyền context cho tác vụ @Async:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Nếu tự cấu hình executor, có thể dùng ContextPropagatingTaskDecorator:

~~~java
@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Context propagation cần được cấu hình theo đúng phiên bản Spring Boot và cách tạo executor của ứng dụng. Khi context bị mất, trace có thể bị tách thành nhiều trace rời hoặc custom observation không còn là child của request.

ContextPropagatingTaskDecorator thuộc Spring Framework 6.1 trở lên. Các property truyền context cũng phụ thuộc phiên bản Spring Boot; hãy kiểm tra configuration metadata của phiên bản dự án trước khi bật.

## 12. Tùy biến ObservationRegistry

Spring Boot có thể tự đăng ký các bean có kiểu:

- ObservationHandler.
- ObservationPredicate.
- ObservationFilter.
- GlobalObservationConvention.

Các bean này được đăng ký với ObservationRegistry auto-configured. Có thể dùng ObservationRegistryCustomizer nếu cần cấu hình trực tiếp registry.

### ObservationPredicate

Predicate cho phép bỏ qua một nhóm observation theo tên hoặc context. Ví dụ, nếu ứng dụng có một observation nội bộ không cần xuất bản, có thể trả false cho observation đó.

Không nên vô hiệu hóa toàn bộ graphql.request chỉ để giảm chi phí metrics nếu nhóm vận hành vẫn cần biết request nào chậm hoặc lỗi.

### ObservationFilter

Filter chạy trước khi observation dừng và có thể thêm metadata vào context. Chỉ thêm key-value có ý nghĩa ổn định và không chứa dữ liệu nhạy cảm.

### ObservationHandler

Handler nhận các lifecycle callback. Spring Boot thường tự cấu hình handler cho metrics và tracing dựa trên dependency có trên classpath. Khi tự cấu hình handler, cần bảo đảm nó hỗ trợ đúng loại Observation.Context.

Nếu một handler không hỗ trợ context GraphQL, nó sẽ không xử lý observation GraphQL dù handler đã được đăng ký trên registry.

## 13. Kiểm thử ObservationRegistry

Micrometer cung cấp **TestObservationRegistry** trong artifact micrometer-observation-test. Registry này lưu lại observation được tạo trong test để có thể kiểm tra tên, key-value, lỗi và event.

Dependency test:

~~~gradle
testImplementation("io.micrometer:micrometer-observation-test")
~~~

Ví dụ kiểm tra custom observation:

~~~java
class BookEnrichmentServiceTest {

    private final TestObservationRegistry observationRegistry =
            TestObservationRegistry.create();

    @Test
    void shouldRecordBookEnrichmentObservation() {
        Observation.createNotStarted(
                        "catalog.book.enrichment",
                        observationRegistry)
                .lowCardinalityKeyValue("cache.result", "hit")
                .observe(() -> {
                    // Execute the operation under test.
                });

        assertThat(observationRegistry)
                .hasAnObservation(context -> {
                    context.hasNameEqualTo("catalog.book.enrichment");
                    context.hasLowCardinalityKeyValue(
                            "cache.result", "hit");
                });
    }
}
~~~

Trong integration test của Spring Boot, có thể cung cấp TestObservationRegistry làm bean để GraphQL observation auto-configuration sử dụng registry đó. Sau khi gửi một GraphQL request bằng GraphQlTester, xác minh registry có observation graphql.request. Với Spring GraphQL 1.4 trở lên, có thể kiểm tra thêm graphql.dataloader khi operation đi qua DataLoader.

Nên kiểm tra:

1. GraphQL request tạo observation graphql.request.
2. Request thành công có outcome SUCCESS.
3. Request có GraphQL errors có outcome tương ứng REQUEST_ERROR hoặc INTERNAL_ERROR.
4. DataFetcher không tầm thường tạo graphql.datafetcher.
5. Property fetcher đơn giản không tạo quá nhiều observation không cần thiết.
6. DataLoader observation xuất hiện khi dùng @BatchMapping hoặc DataLoader thủ công, nếu phiên bản hỗ trợ.
7. Observation có đủ các low-cardinality key bắt buộc.
8. Error được gắn vào observation hoặc span phù hợp.
9. Observation scope được đóng sau khi request kết thúc.
10. Parent context được truyền đúng qua transport và reactive pipeline.

TestObservationRegistry phù hợp để xác minh instrumentation ở cấp ứng dụng. Để kiểm tra exporter thực tế, cần integration test với MeterRegistry hoặc trace exporter phù hợp.

## 14. Kiểm tra metrics và traces khi ứng dụng chạy

Sau khi cấu hình Actuator và exporter, có thể kiểm tra metrics trong runtime.

Ví dụ:

- /actuator/metrics/graphql.request: xem số lượng và thời gian GraphQL request.
- /actuator/metrics/graphql.datafetcher: xem hoạt động DataFetcher nếu có meter tương ứng.
- /actuator/metrics/graphql.dataloader: xem hoạt động DataLoader nếu phiên bản hỗ trợ và có batch load.
- /actuator/prometheus: đọc metrics theo định dạng Prometheus nếu registry và endpoint đã được cấu hình.

Tên metric hiển thị thực tế có thể được chuẩn hóa bởi MeterRegistry. Với Prometheus, tên metric có thể khác tên observation ban đầu do quy tắc chuyển đổi tên và đơn vị.

Trong trace backend, tìm span graphql.request và xem các child span như graphql.datafetcher, graphql.dataloader hoặc database client. Nếu chỉ thấy HTTP server span mà không có GraphQL span, hãy kiểm tra GraphQlObservationInstrumentation và ObservationRegistry. Nếu có GraphQL span nhưng thiếu parent HTTP span, hãy kiểm tra transport instrumentation và context propagation.

### Câu hỏi cần trả lời khi điều tra request chậm

| Câu hỏi | Dấu hiệu cần xem |
|---|---|
| Request chậm ở toàn bộ GraphQL hay trước khi vào GraphQL? | So sánh HTTP server observation và graphql.request |
| Field nào tốn thời gian nhất? | graphql.datafetcher theo field name/path |
| Batch loader có gom nhiều key không? | graphql.dataloader và loader size |
| Request thất bại ở tầng nào? | graphql.outcome, error type và span event |
| Có gọi dịch vụ ngoài chậm không? | Child span của HTTP/database client |
| Có mất trace context không? | Parent-child relationship và trace ID |

## 15. Bảo vệ metadata và tránh cardinality explosion

GraphQL request có thể chứa dữ liệu nhạy cảm trong document, variables và error message. Không đưa toàn bộ request vào observation metadata.

Các nguyên tắc:

- Không thêm raw GraphQL document vào metric tags.
- Không thêm variable values như email, token, password hoặc thông tin cá nhân.
- Không dùng user ID, order ID hoặc book ID làm low-cardinality key.
- Chỉ dùng operation type, outcome, loader name hoặc field name khi số lượng giá trị được kiểm soát.
- Giữ operation name, execution ID và field path ở high-cardinality metadata theo convention mặc định.
- Kiểm tra quyền truy cập trace backend vì high-cardinality values vẫn có thể chứa dữ liệu nhận diện.
- Chỉ ghi lỗi đầy đủ vào trace khi chính sách log và bảo mật cho phép.

Nếu cần theo dõi một nhóm khách hàng hoặc tenant, hãy cân nhắc dùng nhãn phân loại ổn định, không dùng ID riêng của từng khách hàng làm metric dimension.

## 16. Những lỗi thường gặp với ObservationRegistry

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có graphql.request | GraphQlObservationInstrumentation chưa được đăng ký | Kiểm tra Spring Boot auto-configuration hoặc GraphQlSource |
| Có registry nhưng không thấy metrics | Không có meter handler hoặc MeterRegistry exporter | Kiểm tra Actuator, registry và handler |
| Có metrics nhưng không có traces | Chưa cấu hình Micrometer Tracing bridge hoặc exporter | Cấu hình tracing handler và backend |
| Có HTTP span nhưng không có GraphQL span | GraphQL instrumentation chưa hoạt động | Kiểm tra ObservationRegistry và GraphQlObservationInstrumentation |
| GraphQL span không có HTTP parent | Transport chưa truyền parent observation | Kiểm tra HTTP instrumentation và context propagation |
| Không thấy graphql.datafetcher cho mọi field | Property fetcher trivial không được instrument | Đây là hành vi dự kiến; chỉ thao tác không tầm thường mới có observation |
| Không thấy graphql.dataloader | Dùng Spring GraphQL trước 1.4 hoặc operation không gọi DataLoader | Kiểm tra phiên bản và batch loader |
| Metric backend có quá nhiều time series | Dùng ID hoặc giá trị thay đổi liên tục làm metric tag | Chuyển dữ liệu đó sang trace hoặc bỏ khỏi metadata |
| Custom convention không được dùng | Bean sai interface hoặc auto-configuration không nhận được bean | Kiểm tra đúng convention type và GraphQL auto-configuration |
| Trace bị tách khi chạy async | Context không được truyền qua executor hoặc Reactor | Cấu hình Context Propagation phù hợp |
| Thời gian custom observation quá ngắn | Bọc Publisher reactive trong observe đồng bộ | Dùng reactive-aware instrumentation hoặc lifecycle |
| Observation xuất hiện hai lần | Vừa auto-configure vừa đăng ký instrumentation thủ công | Chỉ giữ một cấu hình instrumentation cho GraphQL |

## 17. Quy trình triển khai ObservationRegistry cho GraphQL

Khi bật observability cho Spring for GraphQL:

1. Xác định cần metrics, traces hay cả hai.
2. Thêm Spring Boot Actuator và registry/exporter tương ứng.
3. Xác minh ObservationRegistry được tạo trong application context.
4. Xác minh GraphQlObservationInstrumentation được đăng ký.
5. Gửi một query, mutation và subscription đại diện.
6. Kiểm tra graphql.request và outcome.
7. Kiểm tra graphql.datafetcher ở các resolver có truy cập service hoặc database.
8. Nếu dùng DataLoader, kiểm tra graphql.dataloader và batch size; cần Spring GraphQL 1.4 trở lên.
9. Bổ sung convention riêng chỉ khi cần metadata mới.
10. Kiểm tra low-cardinality và high-cardinality trước khi đưa vào backend.
11. Kiểm tra context propagation giữa HTTP, GraphQL, Reactor và executor.
12. Viết integration test xác minh observation và error path.
13. Kiểm tra dashboard hoặc trace backend để xác nhận dữ liệu được xuất đúng.

ObservationRegistry là điểm kết nối giữa instrumentation của Spring for GraphQL và hạ tầng metrics/tracing của Micrometer. GraphQlObservationInstrumentation tạo observation cho toàn request, các DataFetcher không tầm thường và DataLoader; ObservationHandler chuyển vòng đời đó thành Timer hoặc span. Hãy cấu hình registry và handler, giữ low-cardinality metadata ổn định, truyền trace context đúng qua transport và reactive pipeline, đồng thời kiểm thử cả request thành công lẫn request có lỗi. Khi có đủ ba lớp request, field và loader observation, đội vận hành có thể xác định rõ GraphQL chậm ở operation nào, resolver nào hoặc batch load nào.

## Tài liệu tham khảo

- Spring for GraphQL — Observability: https://docs.spring.io/spring-graphql/reference/observability.html
- Spring for GraphQL — GraphQlObservationInstrumentation API: https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Micrometer — Observation introduction: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
- Micrometer — Observation components: https://docs.micrometer.io/micrometer/reference/observation/components.html

