# graphql.request observation

Spring for GraphQL tích hợp Micrometer Observation để ghi nhận thời gian xử lý và trạng thái của GraphQL request. Observation có thể được chuyển thành metrics, traces hoặc cả hai tùy cấu hình của ứng dụng. Tên observation cấp request là `graphql.request`.

Observation cấp request giúp trả lời các câu hỏi vận hành quan trọng: GraphQL query/mutation/subscription mất bao lâu, tỷ lệ request thành công hay có lỗi, operation nào thường chậm và request nào cần truy vết sâu hơn. Nó cũng tạo ngữ cảnh cha cho các observation chi tiết hơn ở data fetcher và DataLoader.

Bài này tập trung vào observation `graphql.request`, metadata mặc định, cách bật và đọc metrics/traces, tùy chỉnh convention và các nguyên tắc tránh cardinality cao hoặc làm lộ dữ liệu nhạy cảm. Trong module Spring for GraphQL, cơ chế này bổ sung góc nhìn runtime cho schema, resolver, DataLoader, lỗi và transport.

## 1. Observation là gì?

Micrometer Observation là abstraction ghi nhận một hoạt động trong ứng dụng. Một observation có context chứa dữ liệu về hoạt động đó và các key-value mô tả nó. Các handler đăng ký trong `ObservationRegistry` có thể chuyển observation thành timer/counter metrics hoặc span trong distributed trace.

Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `Observation` | Đại diện cho một hoạt động được đo |
| `ObservationRegistry` | Registry nhận và điều phối observation |
| `Observation.Context` | Giữ thông tin của hoạt động trong lúc ghi nhận |
| `ObservationConvention` | Xác định tên observation và metadata |
| `KeyValues` | Tập key-value được gắn vào observation |
| `ObservationHandler` | Chuyển observation thành metrics, trace hoặc xử lý khác |

Spring for GraphQL cung cấp instrumentation để tạo observation ngay trong quá trình GraphQL Java thực thi request. Ứng dụng không cần tự bọc từng resolver bằng timer chỉ để biết request nào đang chậm.

## 2. Vị trí của graphql.request trong request lifecycle

Một request GraphQL thường đi qua transport như HTTP, WebSocket hoặc RSocket, sau đó đến GraphQL execution service và GraphQL Java. Observation `graphql.request` bao quanh việc thực thi GraphQL operation ở lớp GraphQL.

~~~mermaid
flowchart TD
    A[Client] --> B[Transport: HTTP / WebSocket / RSocket]
    B --> C[Transport observation]
    C --> D[GraphQL handler]
    D --> E[graphql.request observation]
    E --> F[Parse và validate document]
    F --> G[Execute operation]
    G --> H[DataFetcher / resolver]
    H --> I[Service / repository]
    I --> J[GraphQL response]
    J --> K[Metrics và traces]
~~~

Observation transport và observation GraphQL đo các lớp khác nhau:

- Transport observation đo trao đổi HTTP hoặc kết nối tương ứng ở tầng giao thức.
- `graphql.request` đo việc GraphQL xử lý document và thực thi operation.
- `graphql.datafetcher` đo một số thao tác lấy dữ liệu không tầm thường.
- `graphql.dataloader` đo các lần gọi batch loader được hỗ trợ.

Vì vậy, một HTTP request có thể có observation `http.server.requests` và một observation `graphql.request`. Đây không phải hai bản ghi trùng nhau; chúng giúp phân biệt thời gian ở transport với thời gian ở GraphQL execution.

## 3. Bật Observation trong Spring Boot

Spring for GraphQL chỉ phát observation khi ứng dụng có `ObservationRegistry` được cấu hình. Với Spring Boot, cách phổ biến là dùng Actuator cùng GraphQL starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-graphql</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot auto-configure `ObservationRegistry` và GraphQL observation instrumentation khi các điều kiện cần thiết có mặt. Trong Spring Boot 3.x, auto-configuration nằm trong Actuator; ở Spring Boot 4.x, package auto-configuration được tổ chức lại. Ứng dụng Boot thông thường không cần tự tạo thêm một `GraphQlObservationInstrumentation` chỉ để bật observation.

Nếu không dùng Spring Boot, cần cung cấp `ObservationRegistry` và đăng ký `GraphQlObservationInstrumentation` với GraphQL runtime/`GraphQlSource`. API tích hợp cụ thể phụ thuộc cách ứng dụng tự xây dựng `GraphQlSource`.

Chỉ thêm Actuator chưa có nghĩa là mọi metrics đã được export ra Prometheus hoặc mọi trace đã được gửi tới tracing backend. Cần có registry/exporter tương ứng và cấu hình endpoint hoặc exporter.

## 4. Observation mặc định graphql.request

Spring for GraphQL tạo observation tên `graphql.request` cho GraphQL server request trên các transport được hỗ trợ, trong cả ứng dụng servlet và reactive.

Instrumentation mặc định dùng `DefaultExecutionRequestObservationConvention` và `ExecutionRequestObservationContext`. Convention tạo các key-value sau:

| Cardinality | Key | Ý nghĩa |
| --- | --- | --- |
| Low | `graphql.operation.type` | Loại operation: `query`, `mutation`, `subscription` hoặc `operation` nếu không parse được |
| Low | `graphql.outcome` | Kết quả xử lý GraphQL request |
| High | `graphql.execution.id` | ID của lần GraphQL execution |
| High | `graphql.operation.name` | Tên operation do client cung cấp |

Hai low-cardinality key là metadata mặc định quan trọng để phân tích metrics. Hai high-cardinality key cung cấp chi tiết cho trace của từng execution.

Ví dụ document có tên operation:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Observation sẽ ghi nhận operation type là `query` và operation name là `FindBook`. Nếu client gửi document không có operation name, high-cardinality operation name có thể dùng giá trị mặc định theo convention.

## 5. Ý nghĩa của graphql.outcome

`graphql.outcome` mô tả kết quả ở cấp GraphQL execution, không đồng nghĩa với HTTP status code.

| Giá trị | Khi nào xuất hiện |
| --- | --- |
| `SUCCESS` | GraphQL response hợp lệ được tạo và không có GraphQL errors |
| `REQUEST_ERROR` | Request không parse được hoặc response có error không thuộc loại `INTERNAL_ERROR` |
| `INTERNAL_ERROR` | Không tạo được GraphQL response hợp lệ hoặc response có ít nhất một error loại `INTERNAL_ERROR` |

Ví dụ, một query hợp lệ nhưng field trả lỗi nghiệp vụ có thể nhận HTTP 200 theo GraphQL over HTTP, đồng thời observation `graphql.request` có outcome `REQUEST_ERROR`. Điều này giúp metrics phản ánh lỗi ở tầng GraphQL dù HTTP transport hoàn tất bình thường.

Không nên suy ra rằng `SUCCESS` nghĩa là mọi business rule đều được thỏa mãn theo cách sản phẩm mong muốn. Nó có nghĩa là GraphQL execution trả response hợp lệ và không có errors trong response.

## 6. GraphQL errors được ghi vào trace như thế nào?

Spring for GraphQL cũng thêm các GraphQL errors của response thành Observation Events. Các event này thường được chuyển thành span event hoặc annotation tùy tracing bridge/exporter.

Event có thể mang:

- Tên dựa trên loại lỗi GraphQL, ví dụ `InvalidSyntax`.
- Contextual name chứa message lỗi GraphQL.

Thông tin này giúp mở trace và xem lỗi cụ thể đã xuất hiện trong operation. Tuy nhiên, error message đôi khi chứa dữ liệu đầu vào, định danh tài khoản, tên resource hoặc thông tin nghiệp vụ nhạy cảm. Không đưa secret hoặc dữ liệu cá nhân vào message lỗi; chuẩn hóa lỗi trước khi gửi tới client và trace backend.

## 7. Phân biệt graphql.request, graphql.datafetcher và graphql.dataloader

`graphql.request` cho biết toàn operation mất bao lâu và kết thúc ra sao. Khi cần tìm resolver hoặc batch loader cụ thể gây chậm, hai observation chi tiết hơn sẽ hữu ích.

| Observation | Đo gì? | Khi nào được tạo? |
| --- | --- | --- |
| `graphql.request` | GraphQL operation ở cấp request | Mỗi GraphQL request được instrumentation xử lý |
| `graphql.datafetcher` | Một thao tác data fetching | Với data fetcher không tầm thường; đọc property đơn giản từ Java object thường không được đo |
| `graphql.dataloader` | Một lần gọi batch loader | Với `@BatchMapping` và DataLoader đăng ký thủ công được hỗ trợ |

Các key mặc định:

**`graphql.datafetcher`**

- Low-cardinality: `graphql.error.type`, `graphql.field.name`, `graphql.outcome`.
- High-cardinality: `graphql.field.path`.

**`graphql.dataloader`**

- Low-cardinality: `graphql.error.type`, `graphql.loader.name`, `graphql.outcome`.
- High-cardinality: `graphql.loader.size`.

Các observation này được tạo bởi GraphQL observation instrumentation. Khả năng quan sát DataLoader phụ thuộc phiên bản Spring for GraphQL đang dùng; hãy kiểm tra tài liệu API của nhánh tương ứng khi dự án dùng phiên bản cũ.

Ví dụ: nếu `graphql.request` chậm, `graphql.datafetcher` có thể cho thấy field `author` chiếm phần lớn thời gian. Nếu field đó gọi batch loader, `graphql.dataloader` có thể giúp quan sát tên loader, kích thước batch và lỗi.

## 8. Low cardinality và high cardinality

Cardinality là số lượng giá trị khác nhau mà một key có thể nhận.

- **Low cardinality** có số lượng giá trị hữu hạn và nhỏ, phù hợp để làm tag metrics.
- **High cardinality** có thể có rất nhiều giá trị khác nhau, phù hợp để ghi trong traces hơn là metrics.

Micrometer chỉ đưa low-cardinality key-value vào metrics; high-cardinality key-value được dành cho traces. Đây là ranh giới quan trọng để tránh tạo hàng trăm nghìn time series.

Ví dụ:

| Dữ liệu | Phân loại nên dùng | Lý do |
| --- | --- | --- |
| Operation type: query/mutation/subscription | Low | Tập giá trị nhỏ, cố định |
| Outcome: SUCCESS/REQUEST_ERROR/INTERNAL_ERROR | Low | Tập trạng thái hữu hạn |
| Operation name do client tự đặt | High | Client có thể gửi vô số tên |
| Execution ID | High | Mỗi request có ID riêng |
| Field path | High | Có thể thay đổi theo cấu trúc query |
| Raw GraphQL document | Không nên thêm vào metrics | Nội dung đa dạng, dễ chứa dữ liệu nhạy cảm |
| Variable value, user ID, email | Không nên dùng làm metric tag | Cardinality cao và có rủi ro lộ dữ liệu |

Không tự đưa operation name, user ID, tenant ID, GraphQL variables hoặc raw document vào low-cardinality convention chỉ vì muốn lọc dashboard theo các trường đó. Nếu thực sự cần truy vết, cân nhắc đưa metadata đã được kiểm soát vào trace với chính sách dữ liệu rõ ràng.

## 9. Xem metrics qua Actuator

Nếu ứng dụng dùng Micrometer registry và expose Actuator metrics endpoint, có thể truy vấn meter theo tên observation:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Ví dụ truy vấn:

~~~http
GET /actuator/metrics/graphql.request
~~~

Endpoint metrics có thể trả về số liệu tổng hợp như count, total time và các statistic được registry hỗ trợ. Có thể lọc theo tag low-cardinality, ví dụ operation type:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:query
~~~

Đường dẫn và định dạng metrics phụ thuộc registry và cấu hình Actuator. Với Prometheus, expose endpoint `/actuator/prometheus` để hệ thống Prometheus scrape. Tên metric được chuyển đổi theo quy ước của backend, vì vậy tên hiển thị trong Prometheus có thể khác tên observation gốc `graphql.request`.

Bảo vệ Actuator endpoint bằng Spring Security hoặc giới hạn truy cập mạng. Không expose metrics và trace metadata ra public internet nếu chưa có chính sách truy cập phù hợp.

## 10. Tracing và liên kết với transport observation

Metrics cho biết xu hướng và tỷ lệ trên nhiều request. Trace cho phép đi theo một request cụ thể qua các thành phần của hệ thống.

Một trace GraphQL có thể có cấu trúc khái quát:

~~~text
HTTP server request
└── graphql.request
    ├── graphql.datafetcher: book
    │   └── database/client observation
    ├── graphql.datafetcher: author
    │   └── graphql.dataloader: authorLoader
    └── graphql response
~~~

Đây là quan hệ minh họa; span con cụ thể phụ thuộc instrumentation có mặt trong ứng dụng và cách context được truyền.

`graphql.request` giả định parent observation được đặt vào GraphQL context bằng key chuẩn `micrometer.observation`. Trace propagation qua ranh giới mạng do instrumentation của transport đảm nhiệm. Với HTTP, Spring Framework có instrumentation riêng để nhận và truyền trace context.

Vì thế, khi thấy trace bị tách rời, hãy kiểm tra cả HTTP server/client instrumentation, ObservationRegistry và context propagation. Chỉ bật GraphQL instrumentation không tự đảm bảo trace ID được truyền xuyên qua mọi service.

## 11. Tùy chỉnh convention cho graphql.request

Trong Spring Boot, cách khuyến nghị là cung cấp một bean kiểu `ExecutionRequestObservationConvention`. Có thể mở rộng `DefaultExecutionRequestObservationConvention` để giữ nguyên metadata mặc định và thêm một low-cardinality key có tập giá trị nhỏ.

Ví dụ thêm phiên bản API cố định:

~~~java
package com.example.graphql.observability;

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
    ExecutionRequestObservationConvention graphQlRequestConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("graphql.api.version", "v1"));
            }
        };
    }
}
~~~

Spring Boot auto-configuration sẽ sử dụng convention bean này cho request observation. Các key mặc định như operation type và outcome vẫn được giữ lại vì code gọi `super.getLowCardinalityKeyValues(context)`.

Chỉ thêm key có giá trị hữu hạn, được kiểm soát bởi ứng dụng. Nếu muốn phân loại theo một thuộc tính request, hãy chuẩn hóa giá trị đầu vào về một tập enum nhỏ trước khi đưa vào low-cardinality metadata.

## 12. Khi nào cần custom instrumentation?

Trong ứng dụng Spring Boot thông thường, custom convention bean là đủ cho phần lớn nhu cầu. Không nên tự tạo một `GraphQlObservationInstrumentation` thứ hai nếu Boot đã auto-configure instrumentation.

Custom instrumentation chỉ phù hợp khi cần thay đổi sâu cách GraphQL Java phát observation hoặc ứng dụng tự xây dựng GraphQL runtime không dùng auto-configuration. Khi đó, cần bảo đảm chỉ có một instrumentation tương ứng và registry được cấu hình đúng.

Các constructor của `GraphQlObservationInstrumentation` đã được mở rộng theo thời gian để hỗ trợ convention cho request, data fetcher và DataLoader. Một số constructor cũ đã deprecated ở nhánh mới. Hãy dùng API theo version Spring for GraphQL đang quản lý bởi Spring Boot BOM, thay vì sao chép cấu hình từ bài viết của phiên bản cũ.

## 13. Tách biệt lỗi GraphQL và lỗi HTTP

GraphQL response có thể trả HTTP 200 nhưng chứa `errors`. Ngược lại, lỗi xảy ra trước khi GraphQL execution, ví dụ authentication bị từ chối ở HTTP security filter, có thể không tạo `graphql.request` observation vì request chưa đi vào GraphQL runtime.

| Tình huống | Observation cần xem |
| --- | --- |
| Request GraphQL hợp lệ, không có errors | `graphql.request` outcome SUCCESS |
| Query parse/validation lỗi | `graphql.request` outcome REQUEST_ERROR nếu GraphQL instrumentation xử lý request |
| Resolver trả GraphQL error nghiệp vụ | `graphql.request` outcome REQUEST_ERROR và có thể có data fetcher error |
| Internal GraphQL execution error | `graphql.request` outcome INTERNAL_ERROR |
| HTTP authentication từ chối trước GraphQL | HTTP server/security observation và security logs |
| HTTP connection timeout hoặc lỗi mạng | HTTP transport/client observation |

Khi điều tra incident, không chỉ xem HTTP status. Hãy đối chiếu outcome GraphQL với outcome transport để biết lỗi xảy ra trước hay trong quá trình thực thi operation.

## 14. Bảo vệ dữ liệu và giới hạn chi phí observability

GraphQL document và variables có thể chứa dữ liệu người dùng, bộ lọc tìm kiếm hoặc thông tin nghiệp vụ. Không ghi toàn bộ document, variables hay token vào metrics hoặc trace mặc định.

Các nguyên tắc nên áp dụng:

- Dùng operation name đã được kiểm soát nếu muốn dùng cho tracing; mặc định operation name là high-cardinality.
- Không thêm raw query hoặc variable values vào metrics tags.
- Không đưa email, access token, session ID hay dữ liệu cá nhân vào low-cardinality key.
- Giữ GraphQL error message không chứa bí mật vì lỗi có thể trở thành span event.
- Cân nhắc sampling trace theo lưu lượng và mức độ quan trọng.
- Giới hạn quyền truy cập metrics, traces và Actuator endpoints.
- Không thay đổi tên observation tùy tiện nếu dashboard/alert đang phụ thuộc tên hiện tại.

Instrumentation chi tiết có thể tạo nhiều spans nếu operation có nhiều field resolver. Bật đủ để chẩn đoán nhưng theo dõi chi phí CPU, bộ nhớ, lưu trữ và ingest của hệ thống observability.

## 15. Kiểm thử GraphQL observations

Nên kiểm tra cả hai điều kiện: GraphQL operation thực sự chạy và observation được ghi vào registry. Có thể dùng `SimpleMeterRegistry` trong test context để kiểm tra timer, hoặc `TestObservationRegistry` để kiểm tra observation lifecycle và key-value.

Ví dụ ý tưởng kiểm thử bằng meter registry:

~~~java
@Test
void recordsGraphQlRequestObservation() {
    // Arrange: GraphQL test application có ObservationRegistry
    // và SimpleMeterRegistry được kết nối với observation handlers.

    graphQlTester.document("""
            query FindBook {
                book(id: "book-42") {
                    id
                }
            }
            """)
        .execute()
        .path("book.id")
        .entity(String.class)
        .isEqualTo("book-42");

    Timer timer = meterRegistry.find("graphql.request")
        .tag("graphql.operation.type", "query")
        .tag("graphql.outcome", "SUCCESS")
        .timer();

    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
}
~~~

Đoạn test giả định application test đã cấu hình ObservationRegistry, meter handler và GraphQL test client. Tên meter và tag cần xác nhận theo registry/version thực tế. Với Prometheus, metric name có thể đã được chuyển đổi theo naming convention.

Các trường hợp nên kiểm tra:

1. Query thành công tạo request observation có operation type query và outcome SUCCESS.
2. Mutation và subscription có operation type tương ứng.
3. GraphQL errors làm outcome chuyển sang REQUEST_ERROR hoặc INTERNAL_ERROR theo error type.
4. Request document không parse được được phân loại đúng.
5. Custom convention giữ key mặc định và thêm key mong muốn.
6. Không có user ID hoặc raw variable xuất hiện trong metric tags.
7. Observation HTTP và GraphQL có trace context liên kết khi transport hỗ trợ.

## 16. Lỗi thường gặp khi triển khai

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy meter graphql.request | Không có ObservationRegistry hoặc instrumentation chưa được cấu hình | Kiểm tra Actuator, GraphQL auto-configuration và registry |
| Có HTTP metrics nhưng không có GraphQL metrics | Chỉ có transport instrumentation | Kiểm tra GraphQL observation auto-configuration |
| Có metrics nhưng không có traces | Chưa có tracing bridge/exporter hoặc sampling loại bỏ trace | Kiểm tra Micrometer Tracing và exporter |
| Request có HTTP 200 nhưng GraphQL outcome là REQUEST_ERROR | GraphQL response chứa errors | Kiểm tra GraphQL error list và resolver |
| Metrics tăng số time series rất nhanh | Đưa operation name, ID hoặc field path vào low-cardinality tags | Chuyển metadata không giới hạn sang high-cardinality hoặc loại bỏ |
| Trace bị tách thành nhiều trace | Transport context propagation không hoạt động | Kiểm tra HTTP instrumentation và key micrometer.observation |
| DataFetcher observation không xuất hiện cho mọi field | Property fetcher đơn giản không được xem là non-trivial | Đây là hành vi dự kiến; quan sát resolver tốn công thực thi |
| Custom convention không được sử dụng | Bean sai interface hoặc custom instrumentation thay thế auto-config | Kiểm tra bean type và điều kiện auto-configuration |
| Trace chứa dữ liệu nhạy cảm | GraphQL error message hoặc custom key-value chứa thông tin riêng tư | Chuẩn hóa lỗi và loại bỏ dữ liệu nhạy cảm |

## 17. Checklist triển khai

- Ứng dụng có `ObservationRegistry` được cấu hình?
- Spring Boot có auto-configure GraphQL observation instrumentation?
- Observation `graphql.request` xuất hiện khi gửi query?
- `graphql.operation.type` và `graphql.outcome` được ghi nhận đúng?
- High-cardinality metadata được giữ khỏi metrics?
- `graphql.datafetcher` và `graphql.dataloader` được bật nếu cần phân tích sâu?
- HTTP transport và GraphQL observation được liên kết trong trace?
- Custom convention giữ key mặc định và chỉ thêm key có cardinality hữu hạn?
- GraphQL error message không chứa token hoặc dữ liệu nhạy cảm?
- Metrics/traces được export và có sampling phù hợp?
- Actuator endpoint được bảo vệ?
- Có test xác minh observation và outcome cho request thành công/lỗi?

Observation `graphql.request` cung cấp góc nhìn ở cấp GraphQL operation: thời gian xử lý, loại operation, outcome và định danh execution. Kết hợp nó với `graphql.datafetcher`, `graphql.dataloader` và transport observations giúp lần theo nguyên nhân chậm hoặc lỗi từ giao thức tới resolver và batch loading. Trong Spring Boot, hãy tận dụng auto-configuration và tùy chỉnh bằng convention bean; giữ low-cardinality key-value nhỏ, không đưa dữ liệu nhạy cảm vào trace/metrics và kiểm thử để bảo đảm observation phản ánh đúng hành vi của API.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring for GraphQL — GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring for GraphQL — DefaultExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DefaultExecutionRequestObservationConvention.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)

