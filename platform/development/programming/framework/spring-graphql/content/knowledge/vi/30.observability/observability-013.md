# High-cardinality key trong Spring GraphQL

High-cardinality key là metadata có số lượng giá trị khác nhau rất lớn hoặc không thể giới hạn trước, ví dụ execution ID, tên operation do client gửi, đường dẫn field có alias/index và kích thước batch. Trong observability, những giá trị này rất hữu ích khi điều tra một request cụ thể, nhưng không phù hợp làm tag của metric vì mỗi tổ hợp tag mới có thể tạo thêm một time series.

Spring for GraphQL dùng Micrometer Observation để ghi nhận request, data fetching và DataLoader. Các convention mặc định phân loại metadata thành **low cardinality** và **high cardinality**. Low-cardinality values có thể được dùng làm metric dimensions; high-cardinality values được giữ cho trace/span để tìm đúng request hoặc field cần điều tra.

## Cardinality là gì?

Cardinality của một key là số lượng giá trị khác nhau mà key đó có thể nhận. Ví dụ:

| Key | Giá trị có thể có | Phân loại thường dùng |
| --- | --- | --- |
| `graphql.operation.type` | `query`, `mutation`, `subscription` | Low cardinality |
| `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR`, `INTERNAL_ERROR` | Low cardinality |
| `graphql.field.name` | Tập field đã khai báo trong schema | Low cardinality |
| `graphql.loader.name` | Tập DataLoader được đăng ký trong ứng dụng | Low cardinality |
| `graphql.execution.id` | ID riêng cho từng lần thực thi request | High cardinality |
| `graphql.operation.name` | Tên operation do client đặt, có thể rất đa dạng | High cardinality |
| `graphql.field.path` | Đường dẫn field, có thể chứa alias và vị trí phần tử list | High cardinality |
| `graphql.loader.size` | Số key trong một batch, thay đổi theo request | High cardinality |

Key name thường là cố định; phần tạo ra cardinality là các value khác nhau. Ví dụ, `graphql.execution.id` chỉ là một key, nhưng gần như mỗi request có một value riêng.

## Vì sao high cardinality nguy hiểm với metrics?

Các hệ thống metrics lưu time series theo metric name và tập tag. Nếu thêm `userId`, `requestId` hoặc full field path vào tag, mỗi giá trị mới có thể tạo một time series riêng. Khi có nhiều request và nhiều tổ hợp tag, số series tăng rất nhanh, làm tăng RAM, CPU, dung lượng lưu trữ và chi phí truy vấn.

Ví dụ một metric có các chiều `field`, `tenant`, `requestId` và `outcome`. `field` và `outcome` thường có tập giá trị nhỏ, còn `tenant` có thể có hàng nghìn giá trị và `requestId` gần như thay đổi theo từng request. Tổ hợp của các chiều này làm số time series tăng theo phép nhân, không phải phép cộng.

Vì vậy, cần tách mục đích của hai loại dữ liệu:

- **Metrics:** tổng hợp request bao nhiêu, tỷ lệ lỗi, thời gian trung bình/p95, field nào thường chậm và loader nào thường lỗi.
- **Traces:** một request cụ thể đã đi qua operation nào, field path nào chậm, execution ID nào và batch đó chứa bao nhiêu key.

Không đưa high-cardinality value vào metric tag chỉ để tiện lọc dashboard. Nếu cần truy vết một trường hợp cụ thể, dùng trace ID hoặc execution ID để tìm trace tương ứng.

## Low và high cardinality trong Micrometer Observation

Một `Observation` có thể chứa hai nhóm `KeyValues`: low cardinality và high cardinality. Convention quyết định metadata nào thuộc nhóm nào.

| Nhóm | Metrics | Traces |
| --- | --- | --- |
| Low cardinality | Được dùng làm metric dimensions/tags. | Có thể được giữ trên span để lọc và nhóm trace. |
| High cardinality | Không được thêm vào metric tags mặc định. | Được giữ làm span attributes để điều tra chi tiết. |

Phân loại này là một hợp đồng quan trọng của instrumentation. Nếu tự viết convention, không đưa ID người dùng, request ID, raw argument hoặc giá trị không giới hạn vào `getLowCardinalityKeyValues(...)`. Hãy dùng `getHighCardinalityKeyValues(...)` nếu dữ liệu thực sự cần có trong trace và không chứa thông tin nhạy cảm.

## Các high-cardinality key mặc định của Spring for GraphQL

`GraphQlObservationInstrumentation` tạo ba loại observation chính trong các phiên bản Spring for GraphQL hiện đại:

| Observation | Mục đích | High-cardinality keys mặc định |
| --- | --- | --- |
| `graphql.request` | Đo toàn bộ quá trình thực thi GraphQL request. | `graphql.execution.id`, `graphql.operation.name` |
| `graphql.datafetcher` | Đo các data fetching operation không tầm thường. | `graphql.field.path` |
| `graphql.dataloader` | Đo lần gọi batch loader. | `graphql.loader.size` |

Các key low-cardinality đi kèm giúp tổng hợp metrics:

| Observation | Low-cardinality keys mặc định |
| --- | --- |
| `graphql.request` | `graphql.operation.type`, `graphql.outcome` |
| `graphql.datafetcher` | `graphql.error.type`, `graphql.field.name`, `graphql.outcome` |
| `graphql.dataloader` | `graphql.error.type`, `graphql.loader.name`, `graphql.outcome` |

`graphql.outcome` của request có các giá trị `SUCCESS`, `REQUEST_ERROR` và `INTERNAL_ERROR`. DataFetcher và DataLoader dùng `SUCCESS` hoặc `ERROR`. `graphql.operation.type` là `query`, `mutation`, `subscription`, hoặc `operation` nếu document không parse được.

`graphql.datafetcher` chỉ được ghi cho thao tác fetch không tầm thường. Việc đọc một property đơn giản trên Java object thường không tạo observation riêng. `graphql.dataloader` theo dõi các method `@BatchMapping` và DataLoader được đăng ký thủ công. Observation riêng cho DataLoader được bổ sung từ Spring for GraphQL 1.4; nếu đang dùng bản cũ, tập observation và cách phân biệt batch có thể khác.

## Hiểu từng high-cardinality key

### `graphql.execution.id`

Execution ID nhận diện một lần thực thi GraphQL. Nó hữu ích khi một request có nhiều field fetch song song và cần gom các span thuộc cùng một lần chạy.

Ví dụ một request tìm kiếm sách có thể tạo một execution ID duy nhất, sau đó tạo span cho root query, các data fetcher và batch loader. Khi điều tra request đó, execution ID giúp tìm đúng trace trong backend tracing.

Không dùng execution ID làm metric tag. Mỗi request mới thường tạo một ID mới, khiến số time series tăng theo số request.

### `graphql.operation.name`

Operation name là tên client đặt trong document:

```graphql
query BookCatalogPage {
  books(first: 50) {
    id
    title
    author {
      name
    }
  }
}
```

Tên `BookCatalogPage` giúp người vận hành nhận ra operation trong trace. Tuy nhiên, GraphQL client có thể gửi nhiều tên operation khác nhau, thậm chí tên được tạo động. Vì vậy Spring for GraphQL xem operation name là high cardinality.

Metrics nên nhóm theo `graphql.operation.type` để biết tỷ lệ query, mutation và subscription. Trace có thể giữ `graphql.operation.name` để xác định document cụ thể. Nếu ứng dụng chỉ chấp nhận một danh sách operation cố định, vẫn nên giữ phân loại mặc định để tránh thay đổi hợp đồng metrics khi client mới được triển khai.

### `graphql.field.path`

Field name chỉ cho biết tên field, còn field path cho biết vị trí của field trong cây response. Với một query có list và alias, path có thể khác nhau theo từng nhánh hoặc phần tử:

```graphql
query AuthorDashboard {
  featured: books(first: 20) {
    id
    writer: author {
      name
    }
  }
}
```

`graphql.field.name` có thể cho biết field đang fetch là `author`; `graphql.field.path` giúp xác định nó nằm dưới alias `featured` và `writer`, hoặc thuộc một phần tử cụ thể của list. Chi tiết này rất hữu ích khi một resolver chỉ chậm với một nhánh query.

Field path có thể chứa alias, index list hoặc các đoạn đường dẫn phụ thuộc cấu trúc response. Vì vậy, dùng path trong trace để chẩn đoán; dùng `graphql.field.name` để tổng hợp metrics.

### `graphql.loader.size`

Loader size là số phần tử được gom vào một lần gọi batch. Trong trace, giá trị này giúp trả lời batch có thực sự gom nhiều key hay chỉ nhận một key mỗi lần.

Ví dụ query lấy 50 sách và mỗi sách cần thông tin tác giả. Một batch có thể nhận nhiều author ID thay vì gọi repository 50 lần. `graphql.loader.size` cho thấy số key thực tế của lần batch đó.

Đây là dữ liệu số có thể thay đổi theo kích thước trang, số quan hệ trùng lặp, `maxBatchSize` và số đợt dispatch. Không thêm mỗi kích thước cụ thể làm metric tag. Nếu cần phân tích phân phối batch size theo thời gian, hãy ghi riêng một `DistributionSummary` với tag loader cố định, như phần sau.

## Quan sát một GraphQL trace

Giả sử client gọi operation `BookCatalogPage` để lấy 50 sách và tác giả. Một trace có thể thể hiện cấu trúc tương tự:

```text
HTTP POST /graphql
└── graphql.request
    ├── graphql.operation.type = query
    ├── graphql.operation.name = BookCatalogPage
    ├── graphql.execution.id = <unique execution id>
    ├── graphql.datafetcher
    │   ├── graphql.field.name = books
    │   └── graphql.field.path = /books
    └── graphql.dataloader
        ├── graphql.loader.name = authors
        └── graphql.loader.size = 37
```

Đây là sơ đồ minh họa. Một request có thể tạo nhiều DataFetcher span và nhiều batch span do query có nhiều field, nhiều nhánh hoặc giới hạn kích thước batch. Không giả định một GraphQL request luôn chỉ có một lần batch.

Trong trace backend, có thể lọc operation name để tìm nhóm request, mở execution ID để xem một lần chạy, sau đó xem field path hoặc loader size trên từng span. Cách này giúp chuyển từ dấu hiệu tổng hợp trong metrics sang nguyên nhân ở một request cụ thể.

## Đưa high-cardinality data vào traces

Trong Spring Boot, Spring GraphQL starter và observability auto-configuration có thể cấu hình `GraphQlObservationInstrumentation` khi `ObservationRegistry` sẵn có. Với ứng dụng không dùng Spring Boot, cần đăng ký instrumentation này khi xây dựng `GraphQlSource`:

```java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.data.method.annotation.support.AnnotatedControllerConfigurer;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

@Configuration(proxyBeanMethods = false)
public class GraphQlObservabilityConfiguration {

    @Bean
    GraphQlSource graphQlSource(
            ObservationRegistry observationRegistry,
            AnnotatedControllerConfigurer controllerConfigurer) {
        return GraphQlSource.schemaResourceBuilder()
                .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
                .configureRuntimeWiring(controllerConfigurer)
                .configureGraphQl(builder -> builder.instrumentation(
                        new GraphQlObservationInstrumentation(observationRegistry)))
                .build();
    }
}
```

Đây là cấu hình tối thiểu cho ứng dụng tự quản lý `GraphQlSource`. Trong ứng dụng thực tế, bổ sung các `RuntimeWiringConfigurer`, exception resolver và cấu hình schema còn lại của ứng dụng. `ObservationRegistry` cũng cần được nối với meter/tracing handlers phù hợp để dữ liệu được xuất ra backend. Nếu Spring Boot đã cấu hình instrumentation, không đăng ký thêm một bản trùng lặp.

Observation có thể tạo metrics và/hoặc traces tùy `ObservationRegistry` và các handler được cấu hình. Có `ObservationRegistry` cho phép ghi observation; để xem span phân tán, ứng dụng còn cần Micrometer Tracing bridge và exporter tương ứng với hệ thống tracing đang dùng. Chỉ bật metrics registry không tự tạo trace backend.

## Thêm high-cardinality metadata bằng convention

Khi cần thêm thông tin động vào trace, hãy mở rộng observation convention và đặt dữ liệu vào nhóm high cardinality. Ví dụ sau thêm alias của field vào span DataFetcher:

```java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DataFetcherObservationContext;
import org.springframework.graphql.observation.DataFetcherObservationConvention;
import org.springframework.graphql.observation.DefaultDataFetcherObservationConvention;

@Configuration(proxyBeanMethods = false)
public class GraphQlObservationConventionConfiguration {

    @Bean
    DataFetcherObservationConvention dataFetcherObservationConvention() {
        return new DefaultDataFetcherObservationConvention() {
            @Override
            public KeyValues getHighCardinalityKeyValues(
                    DataFetcherObservationContext context) {
                KeyValues values = super.getHighCardinalityKeyValues(context);
                String alias = context.getEnvironment().getField().getAlias();
                return (alias != null)
                        ? values.and(KeyValue.of("graphql.field.alias", alias))
                        : values;
            }
        };
    }
}
```

Ví dụ này chỉ phù hợp khi alias thực sự giúp điều tra trace. Alias là dữ liệu client có thể thay đổi; không chuyển nó sang `getLowCardinalityKeyValues(...)`. Trong Spring Boot, cung cấp convention dưới dạng bean là cách tích hợp được khuyến nghị. Nếu không cần metadata riêng, giữ convention mặc định sẽ đơn giản và ổn định hơn.

Không thêm raw GraphQL document, toàn bộ variables, email, access token hoặc dữ liệu cá nhân vào span attributes. High cardinality không đồng nghĩa với việc dữ liệu nhạy cảm được phép xuất hiện trong hệ thống tracing. Trace backend cần quyền truy cập và thời gian lưu trữ phù hợp.

## Khi cần thống kê batch size bằng metrics

`graphql.loader.size` mặc định là high cardinality và chỉ phục vụ trace. Nếu dashboard cần biết batch size trung bình, phân phối hoặc p95 theo loader, có thể ghi một `DistributionSummary` riêng với tag `loader` là tập tên cố định:

```java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class AuthorBatchMetrics {

    private final DistributionSummary batchSize;

    public AuthorBatchMetrics(MeterRegistry registry) {
        this.batchSize = DistributionSummary.builder("graphql.dataloader.batch.size")
                .description("Số key trong mỗi lần batch load tác giả")
                .baseUnit("keys")
                .tag("loader", "authors")
                .register(registry);
    }

    public void recordBatchSize(int size) {
        this.batchSize.record(size);
    }
}
```

Gọi `recordBatchSize(keys.size())` tại đầu method batch loader. `loader=authors` là tag có tập giá trị hữu hạn; kích thước được ghi như sample của DistributionSummary thay vì tag value. Với nhiều loader, dùng một bean hoặc meter cho mỗi loader đã đăng ký, không dùng request ID hay user ID làm tag.

## Kiểm tra và tìm high cardinality bất thường

Khi metrics tăng nhanh ngoài dự kiến, kiểm tra các tag của meter và convention tùy chỉnh:

1. Xác định metric name có số lượng time series tăng đột biến.
2. Kiểm tra các tag value có phải request ID, user ID, tenant ID, operation name, full path hoặc giá trị từ GraphQL arguments hay không.
3. Kiểm tra custom `ObservationConvention`, `ObservationFilter`, `MeterRegistryCustomizer` và code tự ghi meter.
4. Chuyển giá trị động sang high-cardinality span attribute nếu thực sự cần để điều tra; hoặc bỏ hẳn nếu không có giá trị vận hành.
5. Dùng category hữu hạn hoặc route/field template cho metric dimensions.

Micrometer có `HighCardinalityTagsDetector` để cảnh báo khi một meter name tạo ra quá nhiều meter. `MeterFilter.maximumAllowableTags(...)` có thể làm hàng rào bảo vệ cuối cùng cho một meter tùy chỉnh, nhưng không thay thế việc phân loại metadata đúng ngay từ convention.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Số time series tăng liên tục | Đưa request ID, user ID, execution ID hoặc full path vào metric tags. | Bỏ tag động hoặc chuyển thành high-cardinality span attribute. |
| Không thấy `graphql.execution.id` trong `/actuator/metrics` | Đây là high-cardinality key, không được xuất thành metric tag mặc định. | Tìm execution ID trong trace backend. |
| Không lọc được theo field path trong Prometheus | `graphql.field.path` chỉ dành cho trace theo convention mặc định. | Dùng `graphql.field.name` cho metric; mở trace để xem path đầy đủ. |
| Không thấy `graphql.loader.size` trên dashboard metrics | Loader size là high cardinality và chỉ được thêm vào trace mặc định. | Dùng span attribute hoặc ghi DistributionSummary với tag loader cố định. |
| Có metrics nhưng không có trace | Chưa cấu hình Micrometer Tracing bridge/exporter hoặc tracing handler. | Kiểm tra tracing dependency, exporter và sampling. |
| Trace không có span GraphQL | ObservationRegistry hoặc `GraphQlObservationInstrumentation` chưa được cấu hình, hoặc instrumentation bị ghi trùng/ghi sai. | Kiểm tra Boot auto-configuration hoặc cấu hình `GraphQlSource` thủ công. |
| Field path không xuất hiện ở một số field | Property fetcher đơn giản trên Java object là thao tác trivial và không được quan sát riêng. | Dùng trace của các DataFetcher không tầm thường hoặc instrumentation riêng khi có lý do. |
| Alias làm số giá trị tăng mạnh | Client tạo alias động và alias/path được thêm vào metric tag. | Chỉ giữ alias trong trace; metrics dùng field name. |

## Ghi nhớ

High-cardinality key chứa giá trị có thể thay đổi rất nhiều, chẳng hạn execution ID, operation name, field path và loader size. Spring for GraphQL phân loại sẵn các key này để dùng trong traces, trong khi các key có tập giá trị hữu hạn như operation type, field name, loader name và outcome phù hợp cho metrics.

Giữ dynamic identifiers và full paths trong trace để điều tra từng request. Dùng metrics để tổng hợp tốc độ, độ trễ và lỗi theo những chiều ổn định. Nếu cần đo phân phối batch size, ghi giá trị bằng DistributionSummary thay vì biến mỗi kích thước thành một tag. Khi mở rộng observation convention, luôn phân biệt low và high cardinality, đồng thời loại bỏ thông tin nhạy cảm khỏi cả metrics lẫn traces.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — `GraphQlObservationInstrumentation` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Spring Boot — Metrics and Tracing](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
