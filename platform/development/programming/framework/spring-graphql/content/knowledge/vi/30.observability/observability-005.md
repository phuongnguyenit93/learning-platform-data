# graphql.operation.type

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích `graphql.operation.type` là gì trong observability của Spring for GraphQL.
- Phân biệt operation type với operation name và tên field.
- Nhận biết ba giá trị chuẩn `query`, `mutation`, `subscription`.
- Hiểu giá trị dự phòng `operation` khi GraphQL document không parse được.
- Đọc metric `graphql.request` theo operation type và outcome.
- Phân biệt low-cardinality key với high-cardinality key.
- Cấu hình GraphQL observation trong Spring Boot và Micrometer.
- Thiết kế dashboard so sánh lưu lượng, độ trễ và lỗi theo loại operation.
- Tùy biến observation convention mà vẫn giữ dimension có cardinality thấp.
- Kiểm thử operation type và tránh làm lộ dữ liệu qua metrics hoặc traces.

## 1. graphql.operation.type là gì?

`graphql.operation.type` là một low-cardinality key trong observation của GraphQL server request do Spring for GraphQL cung cấp. Nó mô tả loại operation mà GraphQL engine đang xử lý.

Giá trị chuẩn của key này là:

- `query`: đọc dữ liệu.
- `mutation`: thay đổi dữ liệu.
- `subscription`: đăng ký nhận kết quả theo luồng sự kiện.

Nếu request document không parse được nên Spring không xác định được operation type, giá trị dự phòng là `operation`.

Đây là metadata observability do Spring for GraphQL ghi nhận. Nó không phải field trong GraphQL schema, không phải argument mà client truyền vào và cũng không phải tên resolver.

Ví dụ, ba request sau có cùng root field name khác nhau nhưng được phân loại theo operation type:

~~~graphql
query FindBook {
    book(id: "book-42") {
        id
        title
    }
}
~~~

~~~graphql
mutation RenameBook {
    renameBook(id: "book-42", title: "Spring GraphQL") {
        id
        title
    }
}
~~~

~~~graphql
subscription WatchBook {
    bookPriceChanged(bookId: "book-42") {
        bookId
        price
    }
}
~~~

Observation của chúng lần lượt mang `graphql.operation.type=query`, `graphql.operation.type=mutation` và `graphql.operation.type=subscription`.

## 2. Phân biệt operation type, operation name và field name

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Operation type | `query` | Loại operation GraphQL |
| Operation name | `FindBook` | Tên operation do client đặt |
| Field name | `book` | Field được chọn trong operation |

Ví dụ:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Trong document trên:

- Type là `query`.
- Name là `FindBook`.
- Root field là `book`.

Nếu document chứa nhiều operation, client dùng `operationName` để chọn operation cần chạy. `graphql.operation.type` phản ánh type của operation được chọn. Một document chỉ có một anonymous operation vẫn được phân loại theo type của operation đó.

Tên operation có ích khi đọc trace và tìm một operation cụ thể. Tuy nhiên, tên do client cung cấp có thể có rất nhiều giá trị khác nhau. Vì vậy Spring for GraphQL phân loại chúng thành hai nhóm observability khác nhau:

- `graphql.operation.type` là low cardinality.
- `graphql.operation.name` là high cardinality.

Không dùng operation name thay cho operation type khi xây dashboard tổng hợp. Một dashboard cần so sánh Query với Mutation nên nhóm theo `graphql.operation.type`.

## 3. Ba operation type chuẩn

### Query

Query đọc dữ liệu và thường không tạo side effect nghiệp vụ.

~~~graphql
query FindBooks {
    books {
        id
        title
    }
}
~~~

Observation ghi operation type là `query`. Có thể dùng dimension này để theo dõi lưu lượng và thời gian xử lý của các thao tác đọc.

### Mutation

Mutation thực hiện thay đổi trạng thái hoặc dữ liệu.

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
    }
}
~~~

Observation ghi operation type là `mutation`. Khi Mutation có độ trễ hoặc tỷ lệ lỗi tăng, nhóm vận hành có thể tách vấn đề ghi dữ liệu khỏi lưu lượng đọc.

### Subscription

Subscription đăng ký nhận các kết quả mới theo thời gian.

~~~graphql
subscription WatchOrder($orderId: ID!) {
    orderStatusChanged(orderId: $orderId) {
        orderId
        status
    }
}
~~~

Observation ghi operation type là `subscription`. Subscription thường có vòng đời dài và sử dụng transport hỗ trợ streaming như WebSocket hoặc SSE. Khi phân tích số liệu, cần hiểu observation đang đo request/operation theo lifecycle của framework; không mặc định rằng mỗi event được gửi trong stream sẽ tạo một request observation mới.

## 4. Giá trị operation khi document không parse được

Nếu GraphQL document sai cú pháp và không thể parse, framework chưa thể xác định operation type. Khi đó `graphql.operation.type` dùng giá trị dự phòng `operation`.

Ví dụ document không hợp lệ:

~~~graphql
query FindBook {
    book(id: ) {
        id
    }
}
~~~

Giá trị `operation` là nhãn dự phòng của observation, không phải operation type thứ tư trong GraphQL specification.

Cần phân biệt hai tình huống:

- Document không parse được: operation type có thể dùng giá trị dự phòng `operation`.
- Document parse được nhưng execution trả lỗi: operation type vẫn có thể là `query`, `mutation` hoặc `subscription`; trạng thái lỗi được thể hiện riêng qua `graphql.outcome`.

Điều này giúp dashboard không gộp lỗi cú pháp vào cùng một nhóm với mọi lỗi khi thực thi.

## 5. graphql.operation.type nằm trong observation nào?

Spring for GraphQL tích hợp Micrometer Observation để ghi nhận hoạt động của GraphQL server.

Observation cho một GraphQL server request có tên:

`graphql.request`

Observation này được tạo cho các ứng dụng imperative và reactive, trên các transport được Spring for GraphQL hỗ trợ. Mặc định `GraphQlObservationInstrumentation` sử dụng `DefaultExecutionRequestObservationConvention` để thu thập metadata.

Các low-cardinality keys mặc định của server request gồm:

| Key | Vai trò | Ví dụ |
| --- | --- | --- |
| `graphql.operation.type` | Loại operation | `query`, `mutation`, `subscription`, `operation` |
| `graphql.outcome` | Kết quả request | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` |

Một request observation còn có các high-cardinality keys:

| Key | Ý nghĩa |
| --- | --- |
| `graphql.execution.id` | Execution ID của GraphQL request |
| `graphql.operation.name` | Operation name do client gửi |

Vì vậy `graphql.operation.type` là một dimension của observation `graphql.request`, không phải tên một meter riêng.

## 6. Đọc graphql.outcome cùng operation type

Chỉ biết operation type chưa đủ để đánh giá sức khỏe API. Nên phân tích cùng `graphql.outcome`.

Spring for GraphQL mặc định phân loại outcome như sau:

| Outcome | Ý nghĩa |
| --- | --- |
| `SUCCESS` | Có GraphQL response hợp lệ và response không chứa errors |
| `REQUEST_ERROR` | Request không parse được hoặc response có errors không thuộc `INTERNAL_ERROR` |
| `INTERNAL_ERROR` | Không tạo được GraphQL response hợp lệ hoặc response có ít nhất một error thuộc `INTERNAL_ERROR` |

Ví dụ cách đọc:

- `query + SUCCESS`: thao tác đọc hoàn tất không có GraphQL errors.
- `mutation + REQUEST_ERROR`: Mutation có lỗi request hoặc lỗi GraphQL được phân loại không phải internal.
- `subscription + INTERNAL_ERROR`: quá trình xử lý subscription gặp lỗi nội bộ theo quy tắc phân loại của instrumentation.

`REQUEST_ERROR` không đồng nghĩa với HTTP status 400 trong mọi trường hợp. GraphQL response có thể chứa `errors` trong khi transport vẫn trả một HTTP response hợp lệ. Hãy xem GraphQL outcome và HTTP transport observation như hai góc nhìn bổ sung.

## 7. Low cardinality và high cardinality

Cardinality là số lượng giá trị khác nhau mà một dimension có thể nhận.

**Low cardinality** có tập giá trị nhỏ và có giới hạn. `graphql.operation.type` là low cardinality vì chỉ có một số giá trị hữu hạn.

**High cardinality** có tập giá trị có thể tăng rất lớn. Execution ID và operation name là ví dụ trong GraphQL request observation.

Trong Micrometer Observation:

- Low-cardinality key values được dùng làm metric tags.
- High-cardinality key values không được đưa vào meters; chúng dành cho tracing hoặc logging backend có thể xử lý tập giá trị lớn.

Phân loại này quan trọng vì metrics thường được lưu theo chuỗi thời gian và mỗi tổ hợp tag tạo ra một time series. Số lượng tổ hợp tăng quá nhanh sẽ làm tăng bộ nhớ, chi phí lưu trữ và truy vấn monitoring backend.

Ví dụ, nếu metrics có ba operation types và ba outcomes, số tổ hợp cơ bản của hai dimension này vẫn nhỏ. Nếu thêm `userId` với hàng triệu giá trị, số time series có thể tăng đột biến.

Không chuyển các giá trị high-cardinality thành metric tags chỉ để tiện lọc dashboard.

## 8. Bật GraphQL observations trong Spring Boot

Spring for GraphQL chỉ publish observations khi ứng dụng có `ObservationRegistry` được cấu hình.

Trong ứng dụng Spring Boot, GraphQL observation auto-configuration có thể đăng ký `GraphQlObservationInstrumentation` khi `ObservationRegistry` có mặt. Spring Boot cũng cho phép cung cấp convention tùy chỉnh dưới dạng bean.

Một cấu hình thường dùng để xuất metrics là thêm Actuator và registry tương ứng, ví dụ Prometheus:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Cấu hình expose endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

Việc expose endpoint cần phù hợp với security policy của môi trường. Không công khai metrics endpoint cho mọi client Internet nếu chưa có kiểm soát truy cập phù hợp.

Nếu ứng dụng không dùng Spring Boot, cần cấu hình `ObservationRegistry` và thêm `GraphQlObservationInstrumentation` vào GraphQL instrumentation của ứng dụng. Constructor mặc định nhận registry và sử dụng các convention mặc định:

~~~java
import io.micrometer.observation.ObservationRegistry;

import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlObservationInstrumentation instrumentation =
        new GraphQlObservationInstrumentation(observationRegistry);
~~~

Đoạn code trên tạo instrumentation. Ứng dụng cần đưa instance đó vào GraphQL runtime khi cấu hình `GraphQlSource`/GraphQL Java.

## 9. Xem metric theo operation type

Khi instrumentation hoạt động và meter registry được kết nối, có thể tìm meter `graphql.request`.

Actuator metrics endpoint cho phép lọc theo tag. Ví dụ truy vấn các request Query:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:query
~~~

Lọc Query thành công:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:query&tag=graphql.outcome:SUCCESS
~~~

Lọc Mutation có lỗi request:

~~~http
GET /actuator/metrics/graphql.request?tag=graphql.operation.type:mutation&tag=graphql.outcome:REQUEST_ERROR
~~~

Tên meter và cách biểu diễn tag khi export có thể được chuyển đổi theo registry/backend. Dùng Actuator metrics endpoint hoặc scrape endpoint thực tế để xác minh tên và tag mà hệ thống đang xuất.

Với Prometheus, Micrometer chuyển tên meter và tag sang quy ước phù hợp của backend. Tránh hard-code tên đã chuẩn hóa từ một backend vào code ứng dụng; trong ứng dụng, convention gốc vẫn là `graphql.request` và `graphql.operation.type`.

## 10. Thiết kế dashboard theo operation type

`graphql.operation.type` giúp phân tách tải và chất lượng dịch vụ theo loại thao tác.

Một dashboard vận hành có thể có các panel:

| Panel | Dimension chính | Mục đích |
| --- | --- | --- |
| Request volume | `graphql.operation.type` | So sánh lượng Query, Mutation và Subscription |
| Request latency | `graphql.operation.type` | Phát hiện loại operation có thời gian xử lý tăng |
| Request errors | `graphql.operation.type`, `graphql.outcome` | Phân biệt lỗi theo loại thao tác |
| Subscription activity | `graphql.operation.type=subscription` | Theo dõi mức hoạt động của subscription |
| Parse/validation issues | `graphql.operation.type=operation`, outcome | Nhận biết request document không hợp lệ |

Ví dụ diễn giải dashboard:

- Query tăng đột biến có thể do client polling quá thường xuyên hoặc một luồng đọc mới được triển khai.
- Mutation chậm có thể liên quan đến transaction, lock hoặc downstream write service.
- Subscription tăng có thể làm tăng số kết nối lâu dài và nhu cầu tài nguyên.
- Nhóm `operation` tăng cùng `REQUEST_ERROR` có thể là dấu hiệu client gửi document sai cú pháp.

Đây là tín hiệu để điều tra, không phải bằng chứng duy nhất về nguyên nhân. Kết hợp thêm DataFetcher observations, DataLoader observations, HTTP server metrics và traces để tìm điểm nghẽn.

## 11. Kết hợp với DataFetcher và DataLoader observations

Một GraphQL request có thể gọi nhiều DataFetcher. Spring for GraphQL tạo observation riêng `graphql.datafetcher` cho các thao tác fetch được xem là non-trivial.

Một số low-cardinality keys của DataFetcher observation:

- `graphql.field.name`
- `graphql.outcome`
- `graphql.error.type`

DataLoader observation có tên `graphql.dataloader`, theo dõi `@BatchMapping` và DataLoader đăng ký thủ công. Các low-cardinality keys gồm:

- `graphql.loader.name`
- `graphql.outcome`
- `graphql.error.type`

Có thể dùng các observations này để đi sâu sau khi dashboard cho thấy một loại operation có vấn đề:

1. Xác định `graphql.operation.type` có latency hoặc error rate cao.
2. Mở trace tương ứng để xem các field fetching.
3. Tìm DataFetcher chậm hoặc lỗi.
4. Kiểm tra DataLoader và batch size nếu vấn đề liên quan tải quan hệ.
5. Đối chiếu với database hoặc downstream service spans.

Không gắn toàn bộ field path, ID người dùng hoặc dữ liệu đầu vào vào metric dimension chỉ để nối các tầng. Trace và correlation ID phù hợp hơn cho điều tra từng request.

## 12. Tùy chỉnh ExecutionRequestObservationConvention

Trong Spring Boot, có thể cung cấp `ExecutionRequestObservationConvention` bean để bổ sung metadata cho GraphQL request observation.

Ví dụ thêm một dimension cố định `application.component` mà vẫn giữ các key mặc định:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration
class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {

                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of("application.component", "catalog"));
            }
        };
    }
}
~~~

Convention mặc định vẫn cung cấp `graphql.operation.type` và `graphql.outcome`. Dimension mới có giá trị cố định `catalog`, nên vẫn giữ cardinality thấp.

Nếu muốn tùy chỉnh cách phân loại operation type, cần hiểu tác động tới dashboard và alert hiện tại. Giữ vocabulary hữu hạn, nhất quán và không thay giá trị chuẩn bằng operation name hoặc field name.

Không tạo tag từ query text, variables, user ID, email, tenant ID hoặc header tùy ý. Nếu cần những giá trị đó để điều tra, cân nhắc đưa vào trace sau khi đã đánh giá rủi ro bảo mật và chính sách dữ liệu.

## 13. Kiểm thử graphql.operation.type

Nên kiểm thử hai lớp:

- Convention trả đúng low-cardinality key.
- Metrics thực tế xuất hiện khi GraphQL request đi qua instrumentation.

Có thể kiểm thử convention bằng `ExecutionInput` và `ExecutionRequestObservationContext`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import graphql.ExecutionInput;

import io.micrometer.common.KeyValue;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;

class GraphQlOperationTypeConventionTests {

    static class ExposedConvention extends DefaultExecutionRequestObservationConvention {

        KeyValue operationTypeFor(ExecutionRequestObservationContext context) {
            return operationType(context);
        }
    }

    @Test
    void shouldClassifyQueryOperation() {
        ExecutionInput input = ExecutionInput.newExecutionInput()
                .query("query FindBooks { books { id } }")
                .build();

        ExecutionRequestObservationContext context =
                new ExecutionRequestObservationContext(input);

        KeyValue operationType = new ExposedConvention().operationTypeFor(context);

        assertThat(operationType.getKey()).isEqualTo("graphql.operation.type");
        assertThat(operationType.getValue()).isEqualTo("query");
    }
}
~~~

Có thể mở rộng test tương tự cho `mutation` và `subscription`. Với document không parse được, xác minh giá trị dự phòng `operation` theo phiên bản Spring for GraphQL đang dùng.

Ở integration test, gửi lần lượt các operation qua GraphQL endpoint, sau đó kiểm tra meter `graphql.request` có tag tương ứng. Dùng `SimpleMeterRegistry` hoặc registry test phù hợp và xác minh số lần ghi nhận tăng sau khi request hoàn tất.

Khi test metrics, cần chờ reactive execution hoàn tất trước khi đọc meter. Tránh chia sẻ registry hoặc trạng thái giữa các test song song nếu test có thể làm thay đổi cùng meter.

## 14. Cardinality và bảo mật dữ liệu

Những dimension sau thường không phù hợp với metric tags:

- `userId`, `accountId`, `tenantId`.
- Email, username hoặc số điện thoại.
- GraphQL query text và variables.
- Execution ID.
- Operation name nếu client có thể tạo tên động.
- Request ID hoặc correlation ID riêng cho từng request.

Một số giá trị này có thể hữu ích trong trace, nhưng vẫn cần đánh giá dữ liệu nhạy cảm và chính sách retention. High-cardinality không có nghĩa là mọi dữ liệu đều an toàn để ghi trace.

Các nguyên tắc:

1. Giữ `graphql.operation.type` ở vocabulary chuẩn.
2. Dùng `graphql.outcome` để phân loại kết quả request.
3. Giữ các ID riêng từng request ở trace/log có kiểm soát.
4. Không tạo metric tag từ input không tin cậy.
5. Redact thông tin nhạy cảm trước khi ghi trace hoặc log.
6. Giới hạn quyền truy cập Actuator và monitoring backend.
7. Theo dõi số lượng time series sau khi thêm convention tùy chỉnh.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy `graphql.request` | Chưa có `ObservationRegistry` hoặc instrumentation chưa được cấu hình | Kiểm tra Boot auto-configuration và GraphQL instrumentation |
| Meter có nhưng không có `graphql.operation.type` | Convention bị thay thế hoặc custom convention bỏ key mặc định | Kế thừa default convention và giữ low-cardinality keys |
| Giá trị operation type là `operation` | GraphQL document không parse được | Kiểm tra cú pháp document và client request |
| Dashboard gộp Query và Mutation | Đang nhóm theo outcome hoặc operation name thay vì operation type | Nhóm theo `graphql.operation.type` |
| Metrics tăng số time series bất thường | Có dimension tùy chỉnh nhận quá nhiều giá trị | Loại bỏ user ID, request ID và dữ liệu động khỏi metric tags |
| Query lỗi nhưng outcome không phải INTERNAL_ERROR | Lỗi được phân loại là request/GraphQL error | Đọc quy tắc `graphql.outcome` và error type |
| HTTP status thành công nhưng GraphQL có errors | GraphQL response và HTTP status là hai lớp khác nhau | Kiểm tra cả GraphQL outcome lẫn transport observation |
| Không thấy operation name trong metrics | `graphql.operation.name` là high-cardinality key | Xem trace thay vì kỳ vọng metric tag |
| Subscription có latency dài | Observation phản ánh lifecycle request/operation | Đọc semantics của transport và quan sát connection/event riêng |
| Actuator không expose Prometheus | Thiếu registry hoặc endpoint chưa được expose | Kiểm tra dependency và management endpoint configuration |

## 16. Quy trình sử dụng graphql.operation.type

Khi triển khai observability cho Spring for GraphQL, hãy thực hiện theo trình tự:

1. **Bật ObservationRegistry.** Xác minh GraphQL instrumentation được cấu hình.
2. **Xác nhận meter request.** Kiểm tra observation `graphql.request` được ghi nhận.
3. **Kiểm tra operation type.** Gửi Query, Mutation và Subscription; xác minh giá trị tương ứng.
4. **Kiểm tra parse failure.** Gửi document sai cú pháp và xác minh nhãn dự phòng `operation`.
5. **Kết hợp outcome.** Phân biệt `SUCCESS`, `REQUEST_ERROR` và `INTERNAL_ERROR`.
6. **Giữ cardinality thấp.** Chỉ dùng dimension có tập giá trị hữu hạn cho metrics.
7. **Xây dashboard.** So sánh request volume, latency và error rate theo operation type.
8. **Điều tra sâu bằng traces.** Dùng operation name, execution ID và field observations khi cần.
9. **Tùy chỉnh có kiểm soát.** Mở rộng convention nhưng giữ các key mặc định và tránh dữ liệu động.
10. **Kiểm thử định kỳ.** Xác minh metric tags sau khi nâng cấp Spring Boot hoặc Spring for GraphQL.

## 17. Tổng kết

`graphql.operation.type` là low-cardinality key của GraphQL server request observation trong Spring for GraphQL. Nó phân loại operation thành `query`, `mutation`, `subscription`, hoặc `operation` khi document không parse được. Key này giúp tổng hợp metrics theo loại tương tác mà không tạo một time series riêng cho từng operation name.

Hãy đọc `graphql.operation.type` cùng `graphql.outcome` trong observation `graphql.request`. Operation name và execution ID thuộc nhóm high-cardinality, phù hợp hơn với traces. Khi bật Micrometer Observation, xây dashboard theo operation type và giữ các tag tùy chỉnh ở vocabulary có giới hạn, bạn có thể theo dõi lưu lượng, latency và lỗi của GraphQL API mà không làm cardinality hoặc rủi ro lộ dữ liệu tăng ngoài kiểm soát.

## Tài liệu tham khảo

- [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL – GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring Boot – Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Framework – Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)

