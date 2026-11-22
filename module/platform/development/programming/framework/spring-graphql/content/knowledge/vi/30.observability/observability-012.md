# Trace request và resolver

Một GraphQL request có thể gọi nhiều resolver để tạo thành một response. Khi API chậm, chỉ nhìn thời gian HTTP tổng thể thường chưa đủ để biết phần nào đang tốn thời gian: truy vấn gốc, một field lồng nhau, DataLoader, hay lời gọi tới service bên ngoài. Distributed tracing giúp nối các hoạt động này thành một trace, từ lúc HTTP request đi vào ứng dụng cho tới khi GraphQL hoàn tất việc phân giải các field.

Spring for GraphQL tích hợp Micrometer Observation để ghi nhận thời gian và metadata của GraphQL request, data fetcher và DataLoader. Khi kết hợp với Micrometer Tracing trong Spring Boot, các observation có thể trở thành span trong hệ thống tracing như OpenTelemetry, Zipkin hoặc backend tương thích OTLP.

**Trace request và resolver** là cách theo dõi một GraphQL operation ở hai cấp độ:

- Request observation cho biết toàn bộ GraphQL execution mất bao lâu, operation thuộc loại nào và kết quả ra sao.
- DataFetcher observation cho biết từng resolver không tầm thường mất bao lâu, field nào đang được xử lý và có lỗi hay không.
- DataLoader observation cho biết batch loading được thực hiện ra sao, loader nào chạy và số phần tử được tải.

Nhờ đó, có thể lần theo đường đi của một query và xác định resolver hoặc batch loader đang tạo độ trễ.

## Observation, span và trace

Micrometer Observation là API thống nhất để ghi nhận một hoạt động trong ứng dụng. Tùy cấu hình, một observation có thể tạo metric, trace span hoặc cả hai. Nếu registry chỉ có metrics handler, observation tạo timer/metric; khi Micrometer Tracing được cấu hình, tracing-aware handler tạo thêm span.

Các khái niệm:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Observation | Một hoạt động được đo, ví dụ xử lý GraphQL request hoặc gọi resolver |
| ObservationRegistry | Registry tiếp nhận observation và chuyển chúng tới các handler |
| Span | Một đoạn công việc có thời gian bắt đầu, kết thúc, metadata và quan hệ cha/con trong trace |
| Trace | Tập hợp các span liên quan tới cùng một luồng xử lý |
| KeyValue | Metadata gắn với observation/span, ví dụ operation type hoặc outcome |
| ObservationConvention | Quy tắc tạo tên và metadata mặc định cho một loại observation |

Low cardinality key có số lượng giá trị hữu hạn, ổn định. Chúng phù hợp để đưa vào cả metrics và traces. High cardinality key có thể có rất nhiều giá trị khác nhau; chúng chỉ nên được đưa vào traces để tránh tạo quá nhiều time series trong hệ thống metrics.

Ví dụ:

- operation type chỉ có query, mutation hoặc subscription nên là low cardinality.
- operation name do client đặt có thể thay đổi rất nhiều nên là high cardinality.
- field name được giới hạn bởi schema nên là low cardinality.
- field path thay đổi theo cấu trúc và alias của query nên là high cardinality.

Phân biệt hai loại key này rất quan trọng khi quan sát GraphQL trong production.

## Một GraphQL request tạo ra những observation nào?

Spring for GraphQL cung cấp ba observation chính:

| Observation name | Phạm vi đo | Khi nào được tạo |
| --- | --- | --- |
| graphql.request | Toàn bộ GraphQL execution request | Cho Query, Mutation và Subscription trên các transport được hỗ trợ |
| graphql.datafetcher | Một hoạt động phân giải field | Chỉ cho data fetching operation không tầm thường |
| graphql.dataloader | Một lần batch loading | Cho @BatchMapping và DataLoader đăng ký thủ công |

Các observation được tạo bởi GraphQlObservationInstrumentation. Lớp này có từ Spring for GraphQL 1.1.0. Observation cho DataLoader được bổ sung trong dòng 1.4.0.

Không phải mọi field đều tạo data fetcher span. Nếu GraphQL Java chỉ đọc một property có sẵn trên Java object, đó là thao tác trivial và không có graphql.datafetcher observation. Những field được phân giải bằng resolver thực hiện công việc như truy vấn repository, gọi service hoặc tính toán mới thường tạo observation.

## Quan hệ giữa HTTP request, GraphQL request và resolver

Với GraphQL chạy trên HTTP, Spring Framework tạo observation cho HTTP server request. Spring for GraphQL tạo observation graphql.request bên trong HTTP span. Các resolver và DataLoader tiếp tục tạo observation ở bên trong GraphQL request đó.

Một trace minh họa:

~~~mermaid
flowchart TD
    A["HTTP server request"] --> B["graphql.request"]
    B --> C["graphql.datafetcher: Query.book"]
    B --> D["graphql.datafetcher: Book.author"]
    B --> E["graphql.dataloader: Book.reviews"]
    D --> F["HTTP client request tới Author service"]
    E --> G["Database batch query"]
~~~

Trace giúp trả lời ba câu hỏi:

1. HTTP request nào chứa GraphQL operation đang chậm?
2. Trong GraphQL execution, resolver hoặc DataLoader nào tiêu tốn thời gian?
3. Nếu resolver gọi service khác, phần thời gian đó nằm ở span downstream nào?

GraphQL engine có thể thực thi các field độc lập song song. Vì vậy, các span con có thể chồng lấp thời gian; không cộng đơn giản thời lượng mọi resolver để suy ra tổng thời gian request.

## Cấu hình tracing với Spring Boot

Spring Boot tự cấu hình ObservationRegistry khi có observability infrastructure phù hợp. Với Spring for GraphQL, GraphQlObservationAutoConfiguration tự đăng ký GraphQlObservationInstrumentation khi ObservationRegistry và các lớp GraphQL cần thiết có trên classpath.

Vì vậy, ứng dụng Spring Boot thông thường không cần tự tạo GraphQlObservationInstrumentation. Nếu tự đăng ký thêm một instrumentation giống hệt, có thể tạo observation trùng lặp.

Ví dụ dependency cho Spring Boot 4.2 và OpenTelemetry với OTLP:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("org.springframework.boot:spring-boot-starter-opentelemetry")
}
~~~

Dependency exporter/tracer phụ thuộc phiên bản Spring Boot và backend đang dùng. Với Spring Boot 3.x, dùng dependency Micrometer Tracing và OpenTelemetry exporter tương ứng của dòng Boot đó; hãy để Spring Boot dependency management quản lý version.

Cấu hình endpoint OTLP và sampling trong application.yml:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
    resource-attributes:
      service.name: spring-graphql-catalog
~~~

Trong ví dụ, collector nhận trace qua OTLP HTTP tại localhost:4318. Thay endpoint bằng địa chỉ collector của môi trường triển khai. service.name giúp phân biệt service trong giao diện trace backend.

Spring Boot mặc định chỉ sample khoảng 10% trace để hạn chế lượng dữ liệu gửi tới backend. Đặt sampling probability thành 1.0 giúp lấy tất cả trace trong môi trường phát triển hoặc khi chẩn đoán có kiểm soát. Trong production, chọn tỷ lệ phù hợp với lưu lượng và chi phí lưu trữ.

Nếu dùng Zipkin, có thể chọn starter Zipkin của Spring Boot và cấu hình endpoint Zipkin thay cho exporter OTLP. Không bật nhiều exporter trùng nhau nếu không có nhu cầu gửi trace tới nhiều backend.

## Kiểm tra instrumentation đã được bật

Trong ứng dụng Spring Boot, GraphQlObservationAutoConfiguration tạo GraphQlObservationInstrumentation khi:

- Có ObservationRegistry.
- Có GraphQL Java và Spring GraphQL trên classpath.
- Ứng dụng chưa cung cấp một GraphQlObservationInstrumentation khác.

Spring Boot 3.5 có auto-configuration GraphQlObservationAutoConfiguration trong package org.springframework.boot.actuate.autoconfigure.observation.graphql. Spring Boot 4.x chuyển package sang org.springframework.boot.graphql.autoconfigure.observation.

Nếu ứng dụng tự tạo GraphQlSource, hãy kiểm tra custom GraphQlSource có nhận instrumentation cần thiết hay không. Việc tự thay thế GraphQlSource có thể khiến một số phần auto-configuration không còn được áp dụng.

Với ứng dụng không dùng Spring Boot, cần tự cấu hình GraphQlObservationInstrumentation vào GraphQlSource:

~~~java
import java.util.List;

import io.micrometer.observation.ObservationRegistry;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlSource graphQlSource =
        GraphQlSource.schemaResourceBuilder()
                .schemaResources(schemaResource)
                .instrumentation(List.of(
                        new GraphQlObservationInstrumentation(
                                observationRegistry)))
                .build();
~~~

Đoạn code trên minh họa cấu hình GraphQlSource trực tiếp. Trong ứng dụng Spring Boot đã có auto-configuration, không thêm instrumentation lần nữa nếu không có lý do tùy biến rõ ràng.

Để GraphQL request span trở thành span con của HTTP server span, transport vẫn phải truyền parent observation vào GraphQLContext bằng key micrometer.observation. Spring Framework có HTTP server instrumentation để thực hiện việc này. Chỉ thêm GraphQlObservationInstrumentation vào GraphQlSource chưa đủ để tự tạo trace propagation xuyên transport.

## Request observation: graphql.request

Observation graphql.request đo toàn bộ thời gian GraphQL execution. Nó được tạo cho ứng dụng Servlet và Reactive, không phụ thuộc một transport cụ thể.

Mặc định, request observation có các low cardinality key:

| Key | Ý nghĩa | Giá trị ví dụ |
| --- | --- | --- |
| graphql.operation.type | Loại operation | query, mutation, subscription |
| graphql.outcome | Kết quả GraphQL request | SUCCESS, REQUEST_ERROR, INTERNAL_ERROR |

Nếu GraphQL document không parse được, operation type có thể là operation thay vì query, mutation hoặc subscription.

Các high cardinality key mặc định:

| Key | Ý nghĩa |
| --- | --- |
| graphql.execution.id | ExecutionId của GraphQL request |
| graphql.operation.name | Tên operation do client gửi |

Tên operation giúp tìm một loại query cụ thể trong trace. Execution ID giúp phân biệt từng lần thực thi.

### Phân loại outcome

graphql.outcome có ba giá trị chính:

- SUCCESS: response GraphQL hợp lệ đã được gửi và không chứa errors.
- REQUEST_ERROR: request không parse được hoặc response chứa lỗi không thuộc INTERNAL_ERROR.
- INTERNAL_ERROR: không thể tạo response GraphQL hợp lệ hoặc response có ít nhất một lỗi INTERNAL_ERROR.

Vì vậy, REQUEST_ERROR không nhất thiết có nghĩa HTTP transport thất bại. Ví dụ resolver có thể trả lỗi nghiệp vụ trong GraphQL response, khiến outcome là REQUEST_ERROR trong khi HTTP request vẫn hoàn tất bình thường.

Spring for GraphQL cũng ghi GraphQL errors thành Observation Events. Các event này thường xuất hiện như span event hoặc annotation trong trace backend. Event có thể chứa error type và thông điệp lỗi, giúp xác định nguyên nhân mà không phải chỉ nhìn outcome tổng quát.

Vì event có thể chứa thông điệp lỗi, không đưa token, mật khẩu, thông tin cá nhân hoặc nội dung nhạy cảm vào exception message. Hãy giữ thông điệp lỗi đủ hữu ích cho chẩn đoán nhưng không tiết lộ dữ liệu nghiệp vụ.

## DataFetcher observation: graphql.datafetcher

Observation graphql.datafetcher đo thời gian của một hoạt động data fetching không tầm thường. Đây là phần quan trọng nhất khi cần xác định resolver nào làm GraphQL request chậm.

Mặc định có các low cardinality key:

| Key | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| graphql.error.type | Class name của lỗi data fetching | IllegalStateException |
| graphql.field.name | Tên field đang được phân giải | author |
| graphql.outcome | Kết quả data fetching | SUCCESS hoặc ERROR |

High cardinality key:

| Key | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| graphql.field.path | Đường dẫn tới field trong response | /book/author |

Field path hữu ích khi cùng một resolver được gọi từ nhiều vị trí hoặc nhiều phần tử trong danh sách. Không đưa field path vào metrics vì một query có thể tạo ra rất nhiều path khác nhau.

## Ví dụ theo dõi resolver trong một GraphQL query

Giả sử schema có Book, Author và Review:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
}

type Review {
  id: ID!
  rating: Int!
}
~~~

Controller:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            BookService bookService,
            AuthorService authorService,
            ReviewService reviewService) {
        this.bookService = bookService;
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Client gửi:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
    reviews {
      rating
    }
  }
}
~~~

Một trace có thể hiển thị:

1. HTTP server span cho POST /graphql.
2. graphql.request cho operation BookDetails.
3. graphql.datafetcher cho Query.book.
4. graphql.datafetcher cho Book.author.
5. graphql.datafetcher cho Book.reviews.
6. Các span downstream nếu service gọi database hoặc một HTTP service đã được instrument.

Nếu title được đọc trực tiếp từ property của Book, có thể không thấy datafetcher span riêng cho title. Đây là hành vi bình thường vì property fetching là thao tác trivial.

Ví dụ trên chỉ minh họa cấu trúc trace. Thứ tự hiển thị các resolver có thể khác nhau vì GraphQL có thể phân giải field song song.

## DataLoader observation: graphql.dataloader

Khi dùng @BatchMapping hoặc DataLoader đăng ký thủ công, Spring for GraphQL tạo observation graphql.dataloader cho batch loading operation.

Mặc định có các low cardinality key:

| Key | Ý nghĩa |
| --- | --- |
| graphql.error.type | Class name của lỗi batch loading |
| graphql.loader.name | Tên DataLoader đang được dùng |
| graphql.outcome | SUCCESS hoặc ERROR |

High cardinality key:

| Key | Ý nghĩa |
| --- | --- |
| graphql.loader.size | Số phần tử được tải trong batch |

Ví dụ:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;

@BatchMapping(typeName = "Book", field = "reviews")
public Map<Book, List<Review>> reviews(List<Book> books) {
    Set<String> bookIds = books.stream()
            .map(Book::id)
            .collect(Collectors.toSet());

    Map<String, List<Review>> reviewsByBook =
            reviewService.findByBookIds(bookIds);

    Map<Book, List<Review>> result = new HashMap<>();
    for (Book book : books) {
        result.put(
                book,
                reviewsByBook.getOrDefault(book.id(), List.of()));
    }
    return result;
}
~~~

Khi batch loader chạy, trace có thể hiển thị graphql.dataloader với tên loader và số phần tử được tải. Đây là cách kiểm tra batching có hoạt động như kỳ vọng hay không.

Nếu GraphQL request có 20 Book nhưng loader chỉ tải reviews một lần cho 20 book ID, trace sẽ giúp thấy batch operation thay vì nhiều truy vấn lặp lại. Nếu loader chạy nhiều batch nhỏ, kiểm tra maxBatchSize, cách DataLoader được dispatch và nơi resolver gọi load.

Các lần gọi DataLoader không được thể hiện như datafetcher observation thông thường cho cùng hoạt động batch. Hãy tìm graphql.dataloader để phân tích thời gian batch loading.

## Phân tích trace trong hệ thống tracing

Khi mở một trace, nên đọc theo thứ tự từ span cha tới span con:

1. Tìm HTTP server span để biết request đến từ đâu và mất tổng cộng bao lâu.
2. Mở graphql.request để xem GraphQL operation name, operation type, outcome và error events.
3. So sánh thời gian của graphql.datafetcher để tìm field có thời lượng cao.
4. Mở graphql.dataloader nếu field đó dùng batch loading.
5. Mở các span HTTP client, database hoặc messaging bên dưới resolver để xem thời gian nằm ở hệ thống nào.

Ví dụ bảng phân tích minh họa:

| Span | Thời lượng minh họa | Cách diễn giải |
| --- | ---: | --- |
| HTTP server request | 820 ms | Tổng thời gian HTTP endpoint xử lý |
| graphql.request | 790 ms | Tổng thời gian GraphQL execution |
| graphql.datafetcher: Query.book | 55 ms | Tải Book gốc |
| graphql.datafetcher: Book.author | 420 ms | Resolver author có độ trễ cao |
| graphql.dataloader: Book.reviews | 90 ms | Batch loading reviews |
| HTTP client request: author-service | 360 ms | Phần lớn thời gian author nằm ở service bên ngoài |

Trong ví dụ này, nên điều tra author-service trước. Tối ưu GraphQL schema hoặc DataLoader cho reviews sẽ không giải quyết nguyên nhân chính.

Các span con có thể chạy song song, nên tổng duration của chúng có thể lớn hơn duration của graphql.request. Hãy xem quan hệ thời gian và parent-child thay vì cộng duration một cách máy móc.

## Kết nối trace giữa resolver và service bên ngoài

Nếu resolver gọi một service qua HTTP, Spring Boot có thể tạo HTTP client observation và truyền trace context sang service tiếp theo.

Với WebClient, hãy dùng WebClient.Builder do Spring Boot auto-configure:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ClientConfiguration {

    @Bean
    WebClient authorWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://author-service")
                .build();
    }
}
~~~

Với RestClient, dùng RestClient.Builder được inject từ Spring Boot. Các builder được auto-configure để thêm trace propagation interceptor.

Không tạo WebClient bằng WebClient.create() hoặc RestClient bằng constructor thủ công nếu muốn dùng trace propagation tự động. Client tự tạo có thể thiếu instrumentation và khiến trace bị đứt giữa các service.

Khi downstream service cũng dùng tracing và nhận W3C traceparent hoặc B3 header tương ứng, trace backend có thể hiển thị span của service đó trong cùng trace.

## Context propagation trong Spring MVC và WebFlux

GraphQL Java có thể thực thi data fetcher trên thread khác với thread nhận HTTP request. Với WebFlux, công việc còn có thể chuyển qua nhiều reactive operator. Nếu context không được truyền đúng, resolver span có thể mất parent hoặc log không còn trace ID.

Spring for GraphQL sử dụng Micrometer Context Propagation để truyền context:

- Spring MVC: ThreadLocal context từ Servlet request thread được propagate tới thread mà GraphQL Java dùng để gọi data fetcher.
- Spring WebFlux: Reactor Context từ WebFlux request pipeline được truyền tới reactive data fetcher.

Với custom executor hoặc asynchronous code do ứng dụng tự quản lý, cần bảo đảm context được truyền tiếp. Với AsyncTaskExecutor do Spring Boot auto-configure, có thể bật propagate-context. Nếu tự tạo executor, dùng ContextPropagatingTaskDecorator:

~~~yaml
spring:
  reactor:
    context-propagation: auto
  task:
    execution:
      propagate-context: true
~~~

Khi tự cấu hình AsyncTaskExecutor, có thể dùng ContextPropagatingTaskDecorator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration
public class AsyncConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Nếu dùng executor tự tạo mà không propagate context, observation có thể trở thành root span mới hoặc bị mất liên kết với trace ban đầu. Kiểm tra cả ThreadLocal và Reactor Context theo web stack đang sử dụng.

## Log correlation với traceId và spanId

Spring Boot kết hợp Micrometer Tracing để thêm traceId và spanId vào MDC của log. Khi xem log và trace cùng lúc, có thể tìm log của đúng request hoặc resolver đang điều tra.

Ví dụ correlation pattern:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

Với cấu hình mặc định, Spring Boot đã thêm correlation ID dựa trên traceId và spanId vào log. Chỉ cần tùy chỉnh pattern nếu muốn format riêng hoặc đang dùng logging configuration tùy biến.

Trong log của resolver, không cần ghi toàn bộ GraphQL document hoặc variables. Trace ID và span ID đã đủ để liên kết log với trace; dữ liệu request có thể chứa token, thông tin cá nhân hoặc business data nhạy cảm.

## Tùy biến metadata của GraphQL observation

Spring for GraphQL dùng ObservationConvention để tạo metadata cho request, data fetcher và DataLoader. Với Spring Boot, cách ưu tiên là cung cấp convention bean; GraphQlObservationAutoConfiguration sẽ sử dụng bean tương ứng.

Ví dụ thêm low cardinality key cố định cho GraphQL request:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration
public class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
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

Key graphql.api luôn có giá trị catalog, vì vậy cardinality thấp. Có thể dùng convention riêng để chuẩn hóa metadata theo domain hoặc theo nhóm API.

Không thêm các giá trị thay đổi theo từng request như user ID, order ID, email, raw query hoặc field path vào low cardinality keys. Nếu thật sự cần tìm một request cụ thể, dùng high cardinality attribute trong trace và bảo đảm giá trị không chứa dữ liệu nhạy cảm.

Khi tùy biến DataFetcherObservationConvention hoặc DataLoaderObservationConvention, vẫn giữ các key mặc định cần thiết để dashboard và quy tắc cảnh báo hiện có tiếp tục hoạt động.

## Phân biệt metrics và traces

Metrics cho biết xu hướng và tỷ lệ tổng thể. Traces giúp đi sâu vào một request cụ thể.

| Câu hỏi | Nên xem |
| --- | --- |
| GraphQL request p95 tăng trong 15 phút vừa qua? | Metric từ graphql.request |
| Resolver nào thường xuyên lỗi? | Metric graphql.datafetcher theo field name và outcome |
| Một request cụ thể chậm ở resolver nào? | Trace với graphql.request và graphql.datafetcher |
| Batch loader có gom được nhiều key không? | graphql.dataloader trace và loader size |
| Một GraphQL request có lỗi parse hoặc validation? | graphql.request outcome và error events |
| Một downstream service nào làm resolver chậm? | HTTP client span và trace của service đó |

Low cardinality keys được đưa vào metrics và traces. High cardinality keys chỉ được đưa vào traces. Điều này giúp metrics có thể tổng hợp theo operation type, field name và outcome mà không tạo hàng triệu time series.

## Sampling và giới hạn dữ liệu trace

Không nên luôn sample 100% request trong production có lưu lượng lớn. Sampling 100% hữu ích khi phát triển hoặc điều tra một lỗi tái hiện được, nhưng có thể làm tăng chi phí lưu trữ và tải collector.

Các nguyên tắc:

- Chọn sampling probability dựa trên lưu lượng và mục tiêu điều tra.
- Giữ parent-based sampling để các span con tuân theo quyết định sampling của trace cha khi dùng OpenTelemetry sampler tương ứng.
- Giới hạn số attribute và event nếu trace có nhiều field.
- Không ghi raw query, variables, access token hoặc thông tin cá nhân vào span.
- Dùng operation name có quy ước ổn định để tìm loại query trong trace.
- Chỉ đưa metadata cần thiết vào custom convention.

Với OpenTelemetry, Spring Boot hỗ trợ giới hạn số attributes, events, links và độ dài giá trị attribute thông qua management.opentelemetry.tracing.limits.*.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chỉ thấy HTTP span, không thấy graphql.request | GraphQL observation instrumentation chưa được đăng ký hoặc không có ObservationRegistry | Kiểm tra Actuator, ObservationRegistry và GraphQlObservationAutoConfiguration |
| Có graphql.request nhưng không có resolver span | Field dùng property access trivial, field không được chọn hoặc resolver không được gọi | Kiểm tra query selection set và cách field được resolve |
| Resolver span không có parent | Context propagation bị đứt khi đổi thread hoặc executor | Kiểm tra Micrometer Context Propagation và executor |
| Không thấy DataLoader span | Loader chạy qua đường custom chưa được instrument hoặc instrumentation chưa gắn vào GraphQL source | Kiểm tra BatchLoaderRegistry và GraphQlObservationInstrumentation |
| Có nhiều GraphQL span giống nhau | Instrumentation bị đăng ký hai lần | Kiểm tra custom GraphQlSource và auto-configuration |
| Có trace nhưng không gửi tới backend | Exporter chưa được cấu hình, collector không sẵn sàng hoặc sampling loại trace | Kiểm tra endpoint OTLP, exporter, sampling và collector |
| Resolver gọi WebClient nhưng trace bị đứt | WebClient được tạo thủ công, không dùng auto-configured builder | Inject WebClient.Builder từ Spring Boot |
| Metrics tạo quá nhiều time series | Đưa operation name, execution ID hoặc field path vào low cardinality key | Chuyển dữ liệu biến động sang high cardinality trace key |
| Trace có error nhưng metric chỉ báo request error | GraphQL errors được phân loại trong graphql.outcome và error event | Mở span event để xem error type và message |
| Log không có traceId/spanId | Logging pattern hoặc context propagation không đúng | Kiểm tra Micrometer Tracing, MDC và logging pattern |

## Nguyên tắc đọc trace request và resolver

Khi điều tra GraphQL request chậm, hãy:

1. Tìm HTTP server span để xác định request và tổng thời gian.
2. Mở graphql.request để đọc operation type, operation name, outcome và error events.
3. So sánh các graphql.datafetcher span để xác định field chậm.
4. Kiểm tra graphql.dataloader nếu field dùng batch loading.
5. Mở span downstream để phân biệt thời gian resolver với thời gian service hoặc database.
6. Kiểm tra context propagation nếu span con bị tách khỏi trace cha.
7. Dùng low cardinality key cho metrics và high cardinality key cho traces.
8. Giữ trace metadata an toàn, tránh ghi query variables và dữ liệu nhạy cảm.
9. Dùng sampling phù hợp với lưu lượng production.
10. Kiểm tra instrumentation chỉ được đăng ký một lần.

Trace request và resolver cho phép quan sát một GraphQL operation từ transport tới từng data fetcher và batch loader. Spring for GraphQL tạo graphql.request, graphql.datafetcher và graphql.dataloader observations bằng Micrometer. Khi Spring Boot cấu hình ObservationRegistry và Micrometer Tracing, các observation trở thành span có thể xem trong trace backend. Kết hợp request outcome, field path, loader name, context propagation và log correlation giúp xác định resolver gây chậm, lỗi downstream hoặc batching chưa hiệu quả mà không cần ghi lại toàn bộ nội dung GraphQL request.

## Tài liệu tham khảo

- [Spring for GraphQL - Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL - GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot - Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot 3.5 - GraphQlObservationAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring Boot 4.x - GraphQL Auto-configuration classes](https://docs.spring.io/spring-boot/appendix/auto-configuration-classes/spring-boot-graphql.html)
- [Spring Guide - Observing GraphQL in action](https://spring.io/guides/topicals/observing-graphql-in-action/)
