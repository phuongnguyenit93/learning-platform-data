# graphql.outcome trong Spring for GraphQL

`graphql.outcome` là low-cardinality key của Micrometer Observation, cho biết kết quả xử lý GraphQL. Spring for GraphQL ghi nhận key này ở ba phạm vi: toàn bộ GraphQL request, từng data fetcher không tầm thường và từng lần DataLoader batch được thực thi. Nhờ đó, dashboard có thể phân biệt request thành công, request có lỗi GraphQL và lỗi nội bộ, đồng thời quan sát field hoặc batch loader nào thường xuyên thất bại.

Điểm cần nhớ là `graphql.outcome` mô tả kết quả ở tầng GraphQL. Nó không đồng nghĩa với HTTP status. Một HTTP response có thể trả `200 OK` nhưng GraphQL response vẫn có `errors`, khiến request observation mang outcome `REQUEST_ERROR` hoặc `INTERNAL_ERROR`.

## 1. Observation và graphql.outcome

Spring for GraphQL tích hợp Micrometer Observation để ghi nhận metrics và traces. Một Observation có thể tạo timer metric, span trace hoặc cả hai, tùy cấu hình `ObservationRegistry` và các handler được đăng ký.

`graphql.outcome` được đóng góp bởi các observation convention mặc định của Spring for GraphQL. Đây là key có số lượng giá trị hữu hạn, nên có thể dùng làm tag metric để nhóm request theo kết quả.

Các observation chính:

| Observation name | Phạm vi | Khi nào được ghi |
| --- | --- | --- |
| `graphql.request` | Toàn bộ GraphQL execution request | Mỗi GraphQL request được xử lý |
| `graphql.datafetcher` | Một data fetcher | Các data fetching operation không tầm thường |
| `graphql.dataloader` | Một lần DataLoader batch | `@BatchMapping` và DataLoader được đăng ký thủ công |

Một request có thể tạo nhiều observation `graphql.datafetcher` và `graphql.dataloader`. Vì vậy, khi phân tích lỗi, cần xem cả request outcome lẫn field/batch outcome.

## 2. Ba giá trị của graphql.outcome ở cấp request

Với observation `graphql.request`, Spring for GraphQL sử dụng ba giá trị:

| Giá trị | Khi nào được gán |
| --- | --- |
| `SUCCESS` | GraphQL response hợp lệ được tạo và không chứa error |
| `REQUEST_ERROR` | Request không parse được, hoặc response có error nhưng không có error nào thuộc `ErrorType.INTERNAL_ERROR` |
| `INTERNAL_ERROR` | Không thể tạo GraphQL response hợp lệ, hoặc response có ít nhất một error thuộc `ErrorType.INTERNAL_ERROR` |

Có thể hình dung quy tắc phân loại như sau:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B{Có GraphQL response hợp lệ?}
    B -->|Không| C[INTERNAL_ERROR]
    B -->|Có| D{Response có errors?}
    D -->|Không| E[SUCCESS]
    D -->|Có| F{Có error type INTERNAL_ERROR?}
    F -->|Có| C
    F -->|Không| G[REQUEST_ERROR]
~~~

`REQUEST_ERROR` không chỉ dành cho lỗi cú pháp hoặc validation trước khi resolver chạy. Một execution có thể trả partial data và errors; nếu các error không thuộc `INTERNAL_ERROR`, outcome của toàn request vẫn là `REQUEST_ERROR`.

Ngược lại, chỉ cần có ít nhất một error `INTERNAL_ERROR`, outcome request được phân loại `INTERNAL_ERROR`, kể cả khi các field khác đã trả dữ liệu thành công.

## 3. Ví dụ phân loại outcome

Giả sử schema có query lấy sách và tác giả:

~~~graphql
type Query {
    book(id: ID!): Book
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

Các tình huống có thể xảy ra:

| Tình huống | GraphQL response | `graphql.outcome` |
| --- | --- | --- |
| Query hợp lệ, mọi field resolve thành công | Có `data`, không có `errors` | `SUCCESS` |
| Document sai cú pháp | Không có execution data, response có parse error | `REQUEST_ERROR` |
| Input không qua GraphQL validation | Request bị từ chối trước khi resolver chạy | `REQUEST_ERROR` |
| Resolver trả lỗi nghiệp vụ được phân loại `NOT_FOUND` | Có thể có partial data và error | `REQUEST_ERROR` |
| Resolver trả lỗi được phân loại `FORBIDDEN` hoặc `BAD_REQUEST` | Có thể có partial data và error | `REQUEST_ERROR` |
| Resolver phát sinh lỗi được ánh xạ thành `INTERNAL_ERROR` | Có error nội bộ trong response | `INTERNAL_ERROR` |
| Không thể tạo response GraphQL hợp lệ | Không có valid GraphQL response | `INTERNAL_ERROR` |

Ví dụ resolver tác giả bị lỗi nhưng field sách vẫn thành công:

~~~json
{
    "data": {
        "book": {
            "id": "book-1",
            "title": "Spring GraphQL",
            "author": null
        }
    },
    "errors": [
        {
            "message": "Author is not available",
            "path": ["book", "author"],
            "extensions": {
                "classification": "NOT_FOUND"
            }
        }
    ]
}
~~~

Nếu error được ánh xạ thành `ErrorType.NOT_FOUND`, request observation mang `REQUEST_ERROR`. Nếu error được ánh xạ thành `ErrorType.INTERNAL_ERROR`, request observation mang `INTERNAL_ERROR`. Cần xem classification thực tế mà exception resolver tạo ra, không suy outcome chỉ từ nội dung message.

Ví dụ exception handler phân loại lỗi nghiệp vụ:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class BookGraphQlExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleNotFound(
            BookNotFoundException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.NOT_FOUND)
                .message("Book was not found")
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleUnexpected(
            IllegalStateException exception,
            DataFetchingEnvironment environment
    ) {
        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.INTERNAL_ERROR)
                .message("An unexpected error occurred")
                .build();
    }
}
~~~

Handler đầu tiên tạo GraphQL error thuộc nhóm nghiệp vụ `NOT_FOUND`, vì vậy request outcome là `REQUEST_ERROR`. Handler thứ hai tạo `INTERNAL_ERROR`, khiến request outcome là `INTERNAL_ERROR`. Trong ứng dụng thực tế, hãy phân loại exception có chủ đích và không trả nguyên văn exception message nếu nó có thể tiết lộ chi tiết nội bộ.

## 4. Phân biệt request outcome với data fetcher outcome

Observation `graphql.datafetcher` đo một hoạt động resolve field riêng lẻ. Ở phạm vi này, `graphql.outcome` chỉ có hai giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `SUCCESS` | Data fetcher hoàn tất mà không phát sinh lỗi |
| `ERROR` | Data fetcher phát sinh lỗi |

Ví dụ một request có ba field resolver:

- `Query.book` thành công.
- `Book.author` thất bại.
- `Book.reviews` thành công.

Request có thể có một observation `graphql.request` với `REQUEST_ERROR`, trong khi các observation data fetcher lần lượt có outcome `SUCCESS`, `ERROR`, `SUCCESS`.

Không lấy outcome của một field để suy ra outcome của cả request. Request outcome được tính từ toàn bộ kết quả GraphQL và error classification.

## 5. Phân biệt DataLoader outcome

Observation `graphql.dataloader` theo dõi mỗi lần thực thi batch loader. Key `graphql.outcome` có hai giá trị:

- `SUCCESS`: batch loader hoàn tất thành công.
- `ERROR`: batch loader phát sinh lỗi.

Điều này giúp nhận diện batch loader đang gặp vấn đề dù một số field trong GraphQL response vẫn có thể được resolve thành công.

Ví dụ:

| Request | DataFetcher | DataLoader | Ý nghĩa |
| --- | --- | --- | --- |
| `SUCCESS` | `SUCCESS` | `SUCCESS` | Request, field và batch đều thành công |
| `REQUEST_ERROR` | `ERROR` | `ERROR` | Một batch thất bại và tạo GraphQL error không phải internal |
| `INTERNAL_ERROR` | `ERROR` | `ERROR` | Batch thất bại và error được phân loại internal |
| `REQUEST_ERROR` | `ERROR` | Không có | Lỗi xảy ra ở data fetcher không sử dụng DataLoader |

Không phải mọi field đều có DataLoader observation. Observation này chỉ được tạo cho `@BatchMapping` hoặc DataLoader đã đăng ký và được instrument.

## 6. Low cardinality và high cardinality

Micrometer phân chia key thành hai nhóm:

| Loại key | Được đưa vào | Ví dụ |
| --- | --- | --- |
| Low cardinality | Metrics và traces | `graphql.outcome`, `graphql.operation.type`, `graphql.field.name` |
| High cardinality | Traces, không dùng làm metric tag | `graphql.execution.id`, `graphql.operation.name`, `graphql.field.path` |

Low-cardinality key có số lượng giá trị hữu hạn hoặc được giới hạn. Điều này giúp số lượng time series trong hệ thống metrics không tăng không kiểm soát.

High-cardinality key có thể có rất nhiều giá trị khác nhau. Ví dụ operation name do client đặt, execution ID hoặc field path chứa chỉ số list. Chúng hữu ích khi điều tra một trace cụ thể nhưng không phù hợp làm tag metrics.

Đừng chuyển `graphql.operation.name`, user ID, request ID hoặc field path sang low-cardinality tag chỉ để truy vấn dashboard dễ hơn. Việc đó có thể tạo hàng nghìn hoặc hàng triệu time series.

## 7. Các key mặc định của graphql.request

Observation `graphql.request` sử dụng `DefaultExecutionRequestObservationConvention`.

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| `graphql.operation.type` | Low | `query`, `mutation`, `subscription` hoặc `operation` khi document không parse được |
| `graphql.outcome` | Low | Kết quả request: `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| `graphql.execution.id` | High | ID của GraphQL execution |
| `graphql.operation.name` | High | Operation name do client gửi |

Operation name là giá trị do client đặt và có thể thay đổi tùy query. Nếu cần nhóm metric theo loại operation, dùng `graphql.operation.type` thay vì `graphql.operation.name`.

## 8. Các key mặc định của graphql.datafetcher

Observation `graphql.datafetcher` chỉ được tạo cho data fetching operation không tầm thường. Việc đọc trực tiếp một property trên Java object thường được xem là trivial và không tạo observation riêng.

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| `graphql.field.name` | Low | Tên field đang được resolve |
| `graphql.outcome` | Low | `SUCCESS` hoặc `ERROR` |
| `graphql.error.type` | Low | Tên class của lỗi data fetching, nếu có |
| `graphql.field.path` | High | Đường dẫn đến field trong response, ví dụ `/bookById` |

`graphql.field.name` hữu ích để thống kê field nào thường chậm hoặc lỗi. `graphql.field.path` hữu ích hơn khi xem trace của một request cụ thể.

## 9. Các key mặc định của graphql.dataloader

Observation `graphql.dataloader` theo dõi việc gọi DataLoader:

| Key | Cardinality | Ý nghĩa |
| --- | --- | --- |
| `graphql.loader.name` | Low | Tên DataLoader |
| `graphql.outcome` | Low | `SUCCESS` hoặc `ERROR` |
| `graphql.error.type` | Low | Tên class của lỗi batch, nếu có |
| `graphql.loader.size` | High | Số lượng phần tử được load trong batch |

`graphql.loader.name` giúp so sánh các loader khác nhau. `graphql.loader.size` giúp điều tra batch quá lớn hoặc batch nhỏ bất thường trong trace.

## 10. Bật GraphQL observations bằng Spring Boot Actuator

Với Spring Boot 3.x, GraphQL observation auto-configuration được cung cấp qua Actuator. Khi `ObservationRegistry` có mặt, Boot đăng ký `GraphQlObservationInstrumentation` và đưa instrumentation vào `GraphQlSource`.

Thêm dependency:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
~~~

Để xuất metrics sang Prometheus, thêm registry tương ứng:

~~~groovy
runtimeOnly("io.micrometer:micrometer-registry-prometheus")
~~~

Cấu hình expose các endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Actuator và registry giúp tạo, lưu trữ hoặc export metrics. Muốn có traces, ứng dụng còn cần Micrometer Tracing bridge/exporter tương ứng. Chỉ thêm Actuator không tự gửi trace đến Zipkin, Tempo hoặc backend tracing khác.

Nếu không dùng Spring Boot, có thể đăng ký `GraphQlObservationInstrumentation` thủ công với `ObservationRegistry`:

~~~java
import java.util.List;

import graphql.execution.instrumentation.Instrumentation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.graphql.observation.GraphQlObservationInstrumentation;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.core.io.ClassPathResource;

GraphQlSource.SchemaResourceBuilder builder = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"));

Instrumentation instrumentation =
        new GraphQlObservationInstrumentation(observationRegistry);

GraphQlSource graphQlSource = builder
        .instrumentation(List.of(instrumentation))
        .build();
~~~

Trong ứng dụng Boot đã có GraphQL observation auto-configuration, không đăng ký thêm một instrumentation giống hệt nếu không có chủ đích. Tránh tạo observation trùng cho cùng một execution.

## 11. Xem graphql.outcome qua Actuator metrics endpoint

Sau khi gửi một số GraphQL request, có thể xem timer metrics qua endpoint:

~~~http
GET /actuator/metrics/graphql.request
~~~

Lọc theo outcome:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.outcome:SUCCESS
GET /actuator/metrics/graphql.request?tag=graphql.outcome:REQUEST_ERROR
GET /actuator/metrics/graphql.request?tag=graphql.outcome:INTERNAL_ERROR
~~~

Tương tự, kiểm tra field và DataLoader:

~~~http
GET /actuator/metrics/graphql.datafetcher
GET /actuator/metrics/graphql.dataloader
~~~

Actuator trả về thông tin timer như count, total time và các statistic có sẵn. Tên metric và định dạng tag khi export có thể được chuyển đổi theo naming convention của registry. Khi dùng Prometheus, metric timer thường được biểu diễn thành các series count/sum/bucket với tên đã chuẩn hóa.

Không expose Actuator endpoints công khai mà không có kiểm soát truy cập. Trong production, giới hạn endpoint bằng Spring Security, network policy hoặc cấu hình management port phù hợp.

## 12. Đọc metric outcome để tìm lỗi

Một dashboard cơ bản có thể theo dõi số request theo outcome:

| Metric cần quan sát | Câu hỏi cần trả lời |
| --- | --- |
| `graphql.request` theo `graphql.outcome` | Tỷ lệ request thành công, request error và internal error thay đổi thế nào? |
| `graphql.request` theo `graphql.operation.type` | Query, mutation hay subscription đang có vấn đề? |
| `graphql.datafetcher` theo `graphql.field.name` và outcome | Field nào thường phát sinh lỗi hoặc thời gian xử lý cao? |
| `graphql.dataloader` theo `graphql.loader.name` và outcome | Batch loader nào đang thất bại? |
| `graphql.dataloader` duration và loader size trong trace | Batch lớn có làm tăng latency không? |

Một số tình huống điển hình:

- `REQUEST_ERROR` tăng nhưng `INTERNAL_ERROR` ổn định: kiểm tra client gửi query sai, validation, input hoặc lỗi nghiệp vụ được trả về có chủ đích.
- `INTERNAL_ERROR` tăng: kiểm tra exception chưa được xử lý, lỗi database, downstream service hoặc lỗi resolver được phân loại internal.
- `graphql.datafetcher` có `ERROR` ở một field cụ thể: xem trace và `graphql.error.type` để tìm resolver/service liên quan.
- `graphql.dataloader` có `ERROR`: kiểm tra batch service, query theo tập key, timeout và lỗi mapping.
- Request duration tăng nhưng outcome vẫn `SUCCESS`: có thể là vấn đề hiệu năng, không nhất thiết là lỗi. Kiểm tra data fetcher và dependency spans.

Không dùng tỷ lệ `REQUEST_ERROR` như một chỉ số tương đương tỷ lệ HTTP 4xx. GraphQL request error có thể được trả qua HTTP 200, tùy transport và cách server xử lý.

## 13. Tùy biến observation convention nhưng giữ semantics của outcome

Spring for GraphQL cho phép thêm metadata bằng custom observation convention. Với Spring Boot, convention có thể được đăng ký thành bean. Nên kế thừa convention mặc định và giữ các key mặc định, đặc biệt là `graphql.outcome`:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.stereotype.Component;

@Component
public class ApplicationGraphQlObservationConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context
    ) {
        return super.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("graphql.application", "catalog"));
    }
}
~~~

Key `graphql.application` trong ví dụ có một số giá trị cố định nên phù hợp làm low-cardinality key. Convention mặc định vẫn chịu trách nhiệm tạo `graphql.outcome` và `graphql.operation.type`.

Nếu muốn tùy chỉnh data fetcher hoặc DataLoader observations, có thể cung cấp `DataFetcherObservationConvention` hoặc `DataLoaderObservationConvention` tương ứng. Với Spring GraphQL 1.4+, constructor đầy đủ của `GraphQlObservationInstrumentation` hỗ trợ cả ba convention: request, data fetcher và DataLoader. Spring Boot có thể tự nhận convention beans để cấu hình instrumentation.

Không ghi user ID, email, token, raw query, request ID hoặc tenant ID có số lượng giá trị không giới hạn vào low-cardinality key. Nếu thực sự cần metadata chi tiết để điều tra, cân nhắc high-cardinality trace attribute sau khi đánh giá quyền riêng tư và chính sách lưu trữ.

## 14. Error events trong traces

Ngoài key `graphql.outcome`, Spring for GraphQL còn ghi nhận GraphQL errors như Observation events của request. Các event này có tên dựa trên error type; contextual name có thể chứa đầy đủ error message.

Điều này hữu ích khi mở trace để xem vì sao request mang `REQUEST_ERROR` hoặc `INTERNAL_ERROR`. Tuy nhiên, error message có thể chứa dữ liệu đầu vào, thông tin cá nhân hoặc chi tiết hạ tầng nếu ứng dụng trả exception message trực tiếp.

Hãy chuẩn hóa error message trước khi đưa vào GraphQL response và trace. Không đưa access token, password, SQL, connection string hoặc dữ liệu cá nhân vào message hay extensions.

## 15. Phân biệt graphql.outcome với HTTP outcome

Một HTTP request và một GraphQL execution là hai tầng quan sát khác nhau:

| Tầng | Observation | Ví dụ outcome/status |
| --- | --- | --- |
| HTTP server | `http.server.requests` | HTTP 200, 400, 500 |
| GraphQL request | `graphql.request` | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| GraphQL field | `graphql.datafetcher` | `SUCCESS`, `ERROR` |
| GraphQL batch | `graphql.dataloader` | `SUCCESS`, `ERROR` |

Ví dụ server trả HTTP 200 với body chứa `data` một phần và `errors`. Khi đó HTTP observation có thể ghi nhận status 200, còn GraphQL request observation ghi `REQUEST_ERROR` hoặc `INTERNAL_ERROR` theo error classification.

Nếu chỉ nhìn HTTP status, dashboard có thể bỏ sót lỗi nghiệp vụ và lỗi field-level. Nếu chỉ nhìn `graphql.outcome`, bạn không biết request bị lỗi ở tầng network/transport trước khi GraphQL execution bắt đầu. Nên đặt hai loại observation cạnh nhau khi điều tra.

## 16. Kiểm thử outcome trong ứng dụng

Có thể kiểm tra observation ở hai lớp:

1. **Integration test:** gửi GraphQL operation qua `GraphQlTester` hoặc HTTP tester, sau đó kiểm tra response và metric được ghi nhận.
2. **Observation convention test:** tạo `ExecutionRequestObservationContext` phù hợp và kiểm tra các key convention sinh ra.

Với Spring Boot, một integration test có thể dùng `@SpringBootTest`, `@AutoConfigureObservability` hoặc cấu hình test registry phù hợp với phiên bản Boot. Sau khi thực thi request, lấy timer từ `MeterRegistry` và kiểm tra tag `graphql.outcome`.

Ví dụ ý tưởng assertion với Micrometer registry:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import static org.assertj.core.api.Assertions.assertThat;

Timer successTimer = meterRegistry.find("graphql.request")
        .tag("graphql.outcome", "SUCCESS")
        .timer();

assertThat(successTimer).isNotNull();
assertThat(successTimer.count()).isGreaterThan(0);
~~~

Test này giả định đã gửi một query hợp lệ không có errors và `MeterRegistry` được dùng bởi `ObservationRegistry`. Với các test chạy song song hoặc dùng chung context, nên cô lập registry hoặc so sánh count trước và sau request để tránh phụ thuộc dữ liệu từ test khác.

Các scenario nên có:

| Test scenario | Kỳ vọng request outcome |
| --- | --- |
| Query hợp lệ, không có errors | `SUCCESS` |
| Document sai cú pháp | `REQUEST_ERROR` |
| Input validation error được trả dưới dạng GraphQL error không phải internal | `REQUEST_ERROR` |
| Field error có classification `NOT_FOUND` | `REQUEST_ERROR` |
| Field error có classification `INTERNAL_ERROR` | `INTERNAL_ERROR` |
| Không thể tạo GraphQL response hợp lệ | `INTERNAL_ERROR` |

Đối với data fetcher và DataLoader, kiểm tra observation riêng có outcome `ERROR` khi resolver hoặc batch loader thất bại. Không chỉ assert request timer, vì request-level outcome không chỉ ra chính xác field hoặc loader nào gây lỗi.

## 17. Lỗi thường gặp khi đọc graphql.outcome

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có metric `graphql.request` | Observation instrumentation chưa được cấu hình hoặc không có `ObservationRegistry` | Kiểm tra Actuator/Observation auto-configuration và GraphQL instrumentation |
| Chỉ thấy `http.server.requests` | Transport có instrumentation nhưng GraphQL execution chưa được instrument | Bật `GraphQlObservationInstrumentation` |
| Request có partial data nhưng outcome là `REQUEST_ERROR` | Response có errors không thuộc `INTERNAL_ERROR` | Đây là semantics mặc định; kiểm tra error classification |
| HTTP 200 nhưng GraphQL outcome là error | HTTP status và GraphQL outcome đo hai tầng khác nhau | Theo dõi cả transport và GraphQL observations |
| Data fetcher error nhưng request outcome không phải `INTERNAL_ERROR` | Error được phân loại `BAD_REQUEST`, `NOT_FOUND`, `FORBIDDEN` hoặc loại không internal | Kiểm tra `ErrorType` trong exception resolver |
| Metric có quá nhiều time series | Đưa operation name, path, ID hoặc dữ liệu người dùng vào low-cardinality tags | Giữ key không giới hạn ở high-cardinality trace attributes hoặc bỏ chúng |
| Không có `graphql.dataloader` | Không có DataLoader instrumentation hoặc không có batch loader execution | Kiểm tra GraphQlObservationInstrumentation và cách đăng ký DataLoader |
| Trace không liên kết HTTP và GraphQL | Context observation không được truyền qua transport | Kiểm tra transport instrumentation và Micrometer context propagation |
| Error message lộ thông tin nội bộ trong trace | Exception message được đưa nguyên văn vào GraphQL error event | Chuẩn hóa message và loại bỏ dữ liệu nhạy cảm |

## 18. Quy trình vận hành với graphql.outcome

Khi triển khai monitoring cho Spring for GraphQL:

1. Thêm Spring Boot Actuator và cấu hình Micrometer registry phù hợp.
2. Bảo đảm `ObservationRegistry` và `GraphQlObservationInstrumentation` được cấu hình.
3. Thu thập `graphql.request` và nhóm theo `graphql.outcome` cùng `graphql.operation.type`.
4. Theo dõi `graphql.datafetcher` để tìm field chậm hoặc lỗi.
5. Theo dõi `graphql.dataloader` để phát hiện batch lỗi, batch size bất thường và vấn đề N+1.
6. Giữ low-cardinality tags ở tập giá trị nhỏ, ổn định.
7. Dùng high-cardinality attributes trong traces khi cần điều tra một execution cụ thể.
8. So sánh GraphQL outcome với HTTP status để phân biệt lỗi execution và lỗi transport.
9. Kiểm thử cả `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` và field/batch `ERROR`.
10. Bảo vệ Actuator endpoints và loại bỏ dữ liệu nhạy cảm khỏi error message, tags và traces.

`graphql.outcome` là tín hiệu tổng hợp hữu ích để theo dõi chất lượng xử lý GraphQL. Khi kết hợp với operation type, data fetcher observations, DataLoader observations và HTTP transport metrics, đội vận hành có thể biết request thất bại ở cấp nào và bắt đầu điều tra từ field hoặc batch loader phù hợp.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL 1.4 — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL 1.4 — GraphQlObservationDocumentation API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationDocumentation.html)
- [Spring Boot 3.5 — GraphQlObservationAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
