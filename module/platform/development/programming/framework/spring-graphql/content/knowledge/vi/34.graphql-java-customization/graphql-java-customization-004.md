# ExecutionId

Mỗi lần GraphQL Java xử lý một operation, engine gắn một mã nhận diện vào execution đó. Mã này có kiểu `graphql.execution.ExecutionId` và thường được gọi là **execution ID**.

Trong Spring for GraphQL, execution ID giúp nối một request GraphQL với log, lỗi và dữ liệu quan sát của cùng lần thực thi. Khi một resolver phát sinh exception, Spring có thể ghi execution ID vào log để người vận hành tìm đúng request. Khi cần, ứng dụng cũng có thể thay đổi ID mặc định theo transport hoặc tự cấp ID cho từng request.

Bài học này giải thích ý nghĩa của `ExecutionId`, cách Spring for GraphQL tạo ID theo HTTP/WebFlux, Spring MVC và WebSocket, cách tùy biến bằng `ExecutionIdProvider` hoặc interceptor, cách đọc ID trong resolver và cách kiểm thử.

## 1. Vì sao cần ExecutionId?

Một GraphQL request có thể gọi nhiều resolver, truy vấn database, gọi service khác và phát sinh lỗi ở nhiều tầng. Chỉ nhìn vào tên operation như `GetBook` chưa đủ để biết log nào thuộc cùng một lần thực thi.

Ví dụ hai client cùng gửi operation:

~~~graphql
query GetBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Cả hai request đều có tên `GetBook`, nhưng một request có thể tải `book-10`, request còn lại tải `book-20`. Khi một resolver lỗi, đội vận hành cần một mã riêng để nối:

- Request nhận ở HTTP hoặc WebSocket.
- Lần thực thi bên trong GraphQL Java.
- Log do resolver và exception handler ghi ra.
- GraphQL error trả về client.
- Observation hoặc trace được tạo cho request.

`ExecutionId` cung cấp mã nhận diện cho một lần thực thi. Nó không thay thế operation name, user ID hoặc distributed trace ID; mỗi giá trị mô tả một khía cạnh khác nhau.

## 2. ExecutionId là gì?

`ExecutionId` là một kiểu dữ liệu của GraphQL Java trong package `graphql.execution`. Đây là một mã opaque dùng để nhận diện duy nhất một query execution.

Hai factory method thường dùng:

~~~java
import graphql.execution.ExecutionId;

ExecutionId generated = ExecutionId.generate();

ExecutionId supplied = ExecutionId.from("request-7f2a");
~~~

- `ExecutionId.generate()` tạo một ID mới.
- `ExecutionId.from(String)` bọc một chuỗi ID đã có.
- `toString()` trả về giá trị chuỗi để ghi log hoặc truyền qua API.
- `equals()` và `hashCode()` hỗ trợ so sánh ID.

Ví dụ:

~~~java
ExecutionId executionId = ExecutionId.generate();

log.info("GraphQL execution started: {}", executionId);
~~~

Không nên xem `ExecutionId` là một object chứa metadata của query. Nó chỉ đại diện cho mã nhận diện. Operation name, query document, variables và GraphQL context vẫn nằm ở những thành phần riêng.

## 3. Phân biệt ExecutionId với operation name và trace ID

Các loại ID sau thường xuất hiện cùng nhau nhưng có mục đích khác nhau:

| Giá trị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Operation name | Tên operation do client đặt trong GraphQL document | `GetBook` |
| ExecutionId | Mã nhận diện một lần GraphQL execution | `e9a8...` |
| HTTP request ID | Mã request do transport hoặc gateway cấp | `req-7f2a` |
| Distributed trace ID | Mã nối các span qua nhiều service | `4bf92f...` |
| User/tenant ID | Danh tính người dùng hoặc tenant | `user-42` |

Một operation `GetBook` có thể được gọi hàng nghìn lần. Vì vậy operation name không đủ duy nhất để tìm một request cụ thể.

Một distributed trace có thể chứa nhiều GraphQL execution hoặc nhiều request tới các service khác nhau. Trace ID mô tả toàn bộ hành trình phân tán, còn ExecutionId mô tả một lần thực thi GraphQL.

Trong một hệ thống, có thể tạo ExecutionId từ một request ID đáng tin cậy để dễ tra cứu. Tuy nhiên, nếu một trace bao gồm nhiều GraphQL request, không nên dùng cùng trace ID làm ExecutionId cho tất cả request vì sẽ mất khả năng phân biệt từng execution.

## 4. ExecutionId đi qua luồng xử lý như thế nào?

ExecutionId được gắn vào `ExecutionInput` trước khi GraphQL Java thực thi operation. Sau đó, các thành phần trong execution có thể truy cập ID này.

~~~mermaid
flowchart TD
    A["HTTP / WebSocket request"] --> B["Spring GraphQL transport"]
    B --> C["ExecutionGraphQlRequest"]
    C --> D["ExecutionInput"]
    D --> E["GraphQL Java execution"]
    E --> F["DataFetcher / resolver"]
    E --> G["Exception handling"]
    E --> H["Instrumentation / Observation"]
    F --> I["Log có ExecutionId"]
    G --> J["GraphQL error và server log"]
    H --> K["Trace / observation"]
~~~

Một luồng xử lý đơn giản:

1. Transport tiếp nhận request và có thể cấp một ID.
2. Spring tạo `ExecutionGraphQlRequest` cùng document, variables và ID.
3. Spring chuyển ID vào `ExecutionInput`.
4. GraphQL Java thực thi operation với ID đó.
5. Resolver, exception handler và instrumentation có thể đọc ID.
6. Log hoặc observation dùng ID để nối các sự kiện thuộc cùng execution.

`ExecutionId` không tự tạo distributed trace. Nó là một thuộc tính nhận diện trong GraphQL execution; việc truyền trace qua các service vẫn cần cơ chế tracing của Spring/Micrometer hoặc OpenTelemetry.

## 5. ID mặc định của GraphQL Java

Nếu ứng dụng không cung cấp ID riêng, GraphQL Java có `ExecutionIdProvider` mặc định để tạo ID cho mỗi execution. Provider mặc định tạo ID duy nhất, dựa trên cơ chế UUID.

Có thể truy cập provider mặc định:

~~~java
import graphql.execution.ExecutionIdProvider;

ExecutionIdProvider provider =
        ExecutionIdProvider.DEFAULT_EXECUTION_ID_PROVIDER;
~~~

`ExecutionIdProvider` là một functional interface. Method `provide` nhận:

- Query document dưới dạng chuỗi.
- Operation name, có thể là `null`.
- Context object của execution.

Method phải trả về một `ExecutionId` không null:

~~~java
ExecutionId provide(
        String query,
        String operationName,
        Object context
);
~~~

Trong Spring for GraphQL, ID do transport cấp thường được chuyển vào `ExecutionInput`. Vì vậy, ID thực tế của ứng dụng có thể khác với ID do GraphQL Java tự sinh khi chạy độc lập.

## 6. Spring for GraphQL tạo ID theo transport

Spring for GraphQL hỗ trợ nhiều transport. ID mặc định phụ thuộc vào transport đang nhận request:

| Transport | ID mặc định | Khả năng tương quan |
| --- | --- | --- |
| Spring WebFlux | ID của `ServerHttpRequest` | Có thể khớp với log của WebFlux; với Reactor Netty còn có thể khớp log server |
| Spring MVC | ID tạo bằng `AlternativeJdkIdGenerator` | Không mặc định tương quan với một ID log transport khác |
| WebSocket | ID của message `subscribe` theo GraphQL over WebSocket protocol | Dùng để phân biệt và tương quan từng operation trên cùng connection |

Điều này có nghĩa:

- Với WebFlux, thường nên giữ ID mặc định nếu mục tiêu là nối log GraphQL với log HTTP server.
- Với Spring MVC, ID mặc định vẫn nhận diện được execution nhưng không tự động nối với một request ID khác.
- Với WebSocket, một connection có thể chạy nhiều subscription đồng thời; mỗi message `subscribe` có ID riêng để phân biệt operation.

Không nhầm WebSocket connection ID với ExecutionId. Một connection có thể sống lâu và chứa nhiều execution khác nhau.

## 7. Đọc ExecutionId trong DataFetcher

GraphQL Java cung cấp `DataFetchingEnvironment.getExecutionId()`. Resolver có thể đọc ID hiện tại khi cần ghi log hoặc thêm metadata cho hoạt động nội bộ.

~~~java
import graphql.execution.ExecutionId;
import graphql.schema.DataFetchingEnvironment;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private static final Logger log =
            LoggerFactory.getLogger(BookController.class);

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id, DataFetchingEnvironment environment) {
        ExecutionId executionId = environment.getExecutionId();

        log.debug("Resolving book id={} executionId={}", id, executionId);

        return bookService.findById(id);
    }
}
~~~

Ở đây `DataFetchingEnvironment` cung cấp thông tin của field đang được resolve, bao gồm execution ID, arguments, source object, GraphQL context và selection set.

Chỉ ghi ID và metadata cần thiết. Tránh ghi toàn bộ query variables hoặc dữ liệu nhạy cảm chỉ để tiện điều tra.

Nếu resolver không cần tự ghi log, không cần đọc ExecutionId chỉ để truyền qua các method nội bộ. Spring đã dùng ID này trong một số log và error mặc định.

## 8. Tùy chỉnh ID toàn cục bằng ExecutionIdProvider

Nếu muốn mọi GraphQL execution dùng một chính sách ID thống nhất, có thể cung cấp `ExecutionIdProvider` cho GraphQL Java.

Trong Spring Boot, cách gọn là cấu hình qua `GraphQlSourceBuilderCustomizer`:

~~~java
import graphql.execution.ExecutionId;
import graphql.execution.ExecutionIdProvider;

import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer; // Spring Boot 3.x
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutionIdConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer executionIdCustomizer() {
        ExecutionIdProvider provider =
                (query, operationName, context) -> ExecutionId.generate();

        return builder ->
                builder.configureGraphQl(graphQlBuilder ->
                        graphQlBuilder.executionIdProvider(provider));
    }
}
~~~

Spring Boot tự phát hiện `GraphQlSourceBuilderCustomizer` bean và áp dụng cấu hình vào GraphQL builder.

Package import của `GraphQlSourceBuilderCustomizer` phụ thuộc Spring Boot major version. Với Spring Boot 3.x, package là `org.springframework.boot.autoconfigure.graphql`; với Spring Boot 4.x, package là `org.springframework.boot.graphql.autoconfigure`.

Trong ví dụ, provider tạo ID mới cho mỗi execution. Đây là lựa chọn phù hợp khi muốn dùng chính sách ID độc lập với transport.

Nếu mục tiêu là tương quan log WebFlux hoặc WebSocket protocol, hãy cân nhắc trước khi thay thế ID mặc định. Provider toàn cục có thể làm mất mối liên hệ với ID mà transport đã cấp.

## 9. Tạo ExecutionId từ dữ liệu có sẵn

Nếu ứng dụng đã có một request ID duy nhất từ gateway đáng tin cậy, có thể bọc chuỗi đó bằng `ExecutionId.from(...)`.

~~~java
ExecutionId executionId =
        ExecutionId.from("gateway-request-7f2a");
~~~

Điều này hữu ích khi:

- Gateway cấp một request ID duy nhất cho mỗi HTTP request.
- Nhiều log cần dùng cùng một mã để tra cứu.
- Hệ thống có quy ước correlation ID thống nhất giữa các tầng.

Tuy nhiên, `ExecutionId.from(...)` chỉ bọc chuỗi; nó không kiểm tra chuỗi có duy nhất, an toàn hoặc đáng tin cậy hay không.

Nếu nhận ID từ HTTP header:

- Chỉ tin giá trị do gateway đã xác thực hoặc một nguồn nội bộ đáng tin cậy cấp.
- Kiểm tra độ dài và tập ký tự cho phép.
- Đảm bảo ID duy nhất theo từng execution.
- Không dùng giá trị chứa token, email, số điện thoại hoặc thông tin nhạy cảm.
- Nếu không có ID hợp lệ, giữ ID transport mặc định hoặc sinh ID mới.

Không tạo ID bằng `query.hashCode()` hoặc chỉ bằng operation name. Hai request cùng query có thể chạy đồng thời và nhận cùng ID, khiến log bị trộn lẫn.

## 10. Override ExecutionId cho từng HTTP request

`ExecutionGraphQlRequest` cho phép đặt `ExecutionId` trực tiếp. Với HTTP và WebSocket, có thể làm điều đó qua `WebGraphQlInterceptor`.

Ví dụ chỉ sử dụng header `X-Request-ID` khi nó được cấp bởi gateway đáng tin cậy và đúng định dạng:

~~~java
import graphql.execution.ExecutionId;

import java.util.regex.Pattern;

import reactor.core.publisher.Mono;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;

@Component
public class ExecutionIdInterceptor implements WebGraphQlInterceptor {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request,
            Chain chain) {

        String requestId = request.getHeaders().getFirst("X-Request-ID");

        if (requestId != null && SAFE_ID.matcher(requestId).matches()) {
            request.executionId(ExecutionId.from(requestId));
        }

        return chain.next(request);
    }
}
~~~

Nếu header hợp lệ, ID đó sẽ được sử dụng cho `ExecutionInput` của request. Nếu header không có hoặc không đạt validation, request giữ ID do transport đã cấp.

Đây là ví dụ dành cho HTTP request có header riêng theo từng request. Với WebSocket, không nên lấy một header ở handshake rồi dùng lại cho mọi subscription trên connection; mỗi message `subscribe` có thể cần một execution ID khác nhau.

Nếu không có request ID từ gateway nhưng muốn chủ động tạo ID riêng cho mỗi request, có thể gọi `ExecutionId.generate()` trong interceptor:

~~~java
@Override
public Mono<WebGraphQlResponse> intercept(
        WebGraphQlRequest request,
        Chain chain) {

    request.executionId(ExecutionId.generate());
    return chain.next(request);
}
~~~

Chỉ nên làm vậy khi có lý do thay thế ID transport mặc định, chẳng hạn cần chuẩn hóa chính sách ID trên nhiều transport. Nếu không, giữ ID mặc định sẽ tận dụng được khả năng tương quan log sẵn có.

## 11. Khi nào dùng ExecutionIdProvider, khi nào dùng interceptor?

Hai cách tùy biến phục vụ hai phạm vi khác nhau:

| Cách | Phạm vi | Trường hợp phù hợp |
| --- | --- | --- |
| `ExecutionIdProvider` | Chính sách tạo ID ở GraphQL builder | Muốn áp dụng một cách sinh ID thống nhất cho các execution |
| `ExecutionGraphQlRequest.executionId(...)` | Một request cụ thể | Muốn dùng request ID từ gateway hoặc override theo điều kiện |
| Giữ ID transport mặc định | Theo transport | Muốn tương quan với WebFlux, Reactor Netty hoặc WebSocket protocol |

Không nên đồng thời cấu hình nhiều lớp cùng thay ID mà không có thứ tự rõ ràng. Hãy xác định nguồn ID có thẩm quyền và chỉ đặt lại ở một điểm.

Một quy tắc thực tế:

- Giữ mặc định nếu ID transport đã đáp ứng nhu cầu log.
- Dùng interceptor nếu chỉ một nhóm request cần ID riêng.
- Dùng provider nếu toàn ứng dụng cần chính sách ID thống nhất.
- Giữ trace ID trong hệ thống tracing; chỉ chuyển nó thành ExecutionId khi có lý do và hiểu rõ phạm vi duy nhất.

## 12. ExecutionId trong GraphQL error và log

Spring for GraphQL đăng ký cơ chế xử lý exception cho DataFetcher. Nếu exception không được resolver xử lý, lỗi mặc định được phân loại là `INTERNAL_ERROR` và thông điệp chung có chứa execution ID từ `DataFetchingEnvironment`.

Spring cũng ghi log exception chưa được resolve ở mức ERROR cùng ExecutionId để có thể đối chiếu với lỗi gửi cho client. Exception đã được resolve thường được ghi ở mức DEBUG.

Ví dụ tình huống:

~~~text
GraphQL executionId=webflux-req-91a2
DataFetcher failed while resolving Query.book
GraphQL response contains INTERNAL_ERROR
~~~

Khi nhận được mã ID từ log hoặc error message, đội vận hành có thể tìm các log cùng ID để xác định resolver nào gặp lỗi.

Không phải mọi GraphQL error đều chứa ExecutionId trong message. Lỗi parse hoặc validation có thể xảy ra trước khi DataFetcher được gọi. Do đó, không nên giả định mọi error response đều có field hoặc extension mang execution ID.

Nếu ứng dụng tự xây dựng `DataFetcherExceptionResolver`, có thể đọc execution ID từ `DataFetchingEnvironment` để ghi log nội bộ. Chỉ thêm ID vào error response khi API có chủ đích công bố nó; không đưa stack trace hoặc dữ liệu nội bộ ra client.

## 13. ExecutionId trong Micrometer Observation

Spring for GraphQL có thể tạo observation cho GraphQL request thông qua `GraphQlObservationInstrumentation` khi ứng dụng cấu hình `ObservationRegistry` và instrumentation tương ứng.

Observation request mặc định có các key như:

| Key | Loại | Ý nghĩa |
| --- | --- | --- |
| `graphql.operation.type` | Low cardinality | `query`, `mutation`, `subscription` hoặc `operation` |
| `graphql.outcome` | Low cardinality | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |
| `graphql.execution.id` | High cardinality | ExecutionId của request |
| `graphql.operation.name` | High cardinality | Operation name do client gửi |

`graphql.execution.id` là high-cardinality key vì mỗi execution có thể có một giá trị khác nhau.

Điều này phù hợp để tra cứu một trace hoặc observation cụ thể. Không nên đưa ExecutionId vào label của metric tổng hợp có số lượng chuỗi thời gian không giới hạn. Metric label nên ưu tiên các giá trị ít biến thiên như operation type và outcome.

Có thể dùng ExecutionId để nối log với trace, nhưng cần cấu hình trace propagation ở transport và instrumentation phù hợp. Chỉ ghi một ID trong log không tự động tạo distributed trace.

## 14. ExecutionId với WebSocket subscription

Một WebSocket connection có thể tồn tại lâu và mang nhiều subscription đồng thời. GraphQL over WebSocket protocol sử dụng message ID trong message `subscribe` để phân biệt operation.

Spring for GraphQL sử dụng ID của message `subscribe` làm ID cho execution tương ứng. Vì vậy:

- Một connection có thể có nhiều ExecutionId.
- Mỗi subscription có thể tồn tại lâu hơn một HTTP request thông thường.
- Khi client hủy một subscription, message `complete` được liên hệ với ID của subscription đó.
- Không dùng connection ID làm ExecutionId cho tất cả subscription.

Nếu ứng dụng tùy chỉnh ID cho WebSocket, cần bảo đảm mỗi operation vẫn có ID riêng và việc đối chiếu message `next`, `error`, `complete` theo protocol không bị nhầm lẫn.

## 15. Kiểm thử ExecutionId bằng ExecutionGraphQlServiceTester

Spring for GraphQL cung cấp `ExecutionGraphQlServiceTester` để kiểm thử trực tiếp server mà không cần gửi request qua HTTP, WebSocket hoặc RSocket.

Builder có `configureExecutionInput(...)`, cho phép đặt execution ID trước khi GraphQL Java thực thi operation.

Giả sử controller trả về ID hiện tại:

~~~java
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ExecutionIdController {

    @QueryMapping
    public String currentExecutionId(DataFetchingEnvironment environment) {
        return environment.getExecutionId().toString();
    }
}
~~~

Schema:

~~~graphql
type Query {
    currentExecutionId: String!
}
~~~

Test đặt ID cố định rồi xác minh resolver nhận đúng giá trị:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import graphql.execution.ExecutionId;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ExecutionIdTests {

    private final ExecutionGraphQlService graphQlService;

    @Autowired
    ExecutionIdTests(ExecutionGraphQlService graphQlService) {
        this.graphQlService = graphQlService;
    }

    @Test
    void passesConfiguredExecutionIdToDataFetcher() {
        ExecutionId expected = ExecutionId.from("test-execution-42");

        ExecutionGraphQlServiceTester tester =
                ExecutionGraphQlServiceTester.builder(graphQlService)
                        .configureExecutionInput((input, builder) ->
                                builder.executionId(expected).build())
                        .build();

        tester.document("{ currentExecutionId }")
                .execute()
                .path("currentExecutionId")
                .entity(String.class)
                .isEqualTo(expected.toString());
    }
}
~~~

Test này xác minh ID được đặt trên `ExecutionInput` có thể được đọc từ `DataFetchingEnvironment`. Nó không kiểm tra ID mặc định của WebFlux hoặc WebSocket; muốn kiểm tra hành vi transport, hãy dùng tester tương ứng và kiểm tra interceptor/handler ở đúng lớp.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai request có cùng ID | Dùng operation name hoặc query hash làm ID | Tạo ID duy nhất cho từng execution |
| Log GraphQL không khớp log HTTP | Thay ID transport mặc định bằng provider toàn cục | Giữ transport ID hoặc truyền correlation ID đáng tin cậy |
| WebSocket có nhiều subscription nhưng log không phân biệt | Dùng chung connection ID cho mọi operation | Giữ ID của từng message `subscribe` |
| `ExecutionId.from(...)` nhận chuỗi không an toàn | Tin trực tiếp header do client gửi | Chỉ nhận ID từ nguồn tin cậy và validate định dạng |
| Không tìm thấy ID trong một GraphQL error | Lỗi xảy ra trước DataFetcher hoặc error handler tùy chỉnh | Kiểm tra transport log và request-level error |
| Metric tăng số lượng time series liên tục | Dùng ExecutionId làm metric label | Chuyển ID sang trace/log; metric dùng low-cardinality tags |
| ID khác nhau giữa các lần chạy test | Test dùng ID tự sinh | Đặt ID cố định bằng `ExecutionGraphQlServiceTester` |
| ID không còn liên kết với log transport | Override ID ở interceptor hoặc provider | Xác định rõ ID nào là nguồn correlation chính |
| Trace ID và ExecutionId bị nhầm lẫn | Dùng một mã cho cả trace và execution mà không xét phạm vi | Giữ hai giá trị riêng hoặc xác định quy tắc mapping rõ ràng |

## 17. Quy trình lựa chọn và cấu hình ExecutionId

Khi triển khai ExecutionId trong Spring for GraphQL, có thể làm theo trình tự:

1. Xác định transport đang dùng: WebFlux, Spring MVC, WebSocket hoặc RSocket.
2. Kiểm tra ID mặc định của transport có đủ để tra cứu log hay không.
3. Nếu ID mặc định phù hợp, giữ nguyên để tận dụng khả năng tương quan sẵn có.
4. Nếu cần chính sách ID toàn cục, cấu hình `ExecutionIdProvider`.
5. Nếu chỉ một request cần ID riêng, đặt `ExecutionGraphQlRequest.executionId(...)` qua interceptor.
6. Nếu dùng ID từ gateway, xác thực nguồn, kiểm tra định dạng và bảo đảm duy nhất theo execution.
7. Đọc ID trong `DataFetchingEnvironment` khi resolver thực sự cần ghi log.
8. Kết hợp ID với GraphQL error log và Micrometer observation.
9. Không dùng ID làm metric label hoặc chứa dữ liệu nhạy cảm.
10. Kiểm thử ID được chuyển vào `ExecutionInput` bằng `ExecutionGraphQlServiceTester`.
11. Kiểm thử riêng hành vi HTTP/WebSocket nếu ứng dụng override ID ở transport layer.

## 18. Những điểm cần ghi nhớ

- `ExecutionId` nhận diện một lần thực thi GraphQL trong GraphQL Java.
- `ExecutionId.generate()` tạo ID mới; `ExecutionId.from(String)` bọc một ID có sẵn.
- Operation name không phải ExecutionId vì nhiều request có thể cùng tên operation.
- Spring for GraphQL thường dùng ID do transport cấp: WebFlux request ID, MVC generated ID hoặc WebSocket subscribe message ID.
- `ExecutionGraphQlRequest.executionId(...)` cho phép override ID theo từng request.
- `ExecutionIdProvider` cho phép cấu hình chính sách tạo ID ở GraphQL builder.
- `DataFetchingEnvironment.getExecutionId()` cho phép resolver đọc ID hiện tại.
- Spring dùng ID để hỗ trợ log và error correlation; Micrometer observation có key `graphql.execution.id` dạng high cardinality.
- ExecutionId không tự thay thế distributed trace ID.
- ID cần duy nhất theo execution, không chứa dữ liệu nhạy cảm và không nên dùng làm metric label.

ExecutionId là một phần nhỏ trong GraphQL execution nhưng có giá trị lớn khi vận hành. Khi giữ đúng ID transport hoặc tùy chỉnh nó tại một điểm có chủ đích, ứng dụng có thể nối request, resolver, lỗi và observation thành một luồng dễ truy vết.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Server Transports and Interception](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — ExecutionGraphQlRequest API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/ExecutionGraphQlRequest.html)
- [GraphQL Java — ExecutionId API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ExecutionId.html)
- [GraphQL Java — ExecutionIdProvider API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ExecutionIdProvider.html)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
