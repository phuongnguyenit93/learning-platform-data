# GraphQL observation convention

Trong Spring for GraphQL, observation convention quyết định tên observation, tên hiển thị trong trace và các key-value được gắn vào observation. Convention không tự đo thời gian hoặc tạo observation; phần instrumentation tạo observation trong lúc GraphQL xử lý request, còn convention mô tả cách ghi nhận metadata.

Spring for GraphQL cung cấp convention mặc định cho ba cấp: GraphQL request, data fetcher và DataLoader. Khi metadata mặc định chưa đủ cho dashboard hoặc tracing của hệ thống, có thể mở rộng convention để bổ sung thông tin như phiên bản API, nhóm resolver hoặc miền nghiệp vụ của batch loader.

Các observation chỉ được publish khi ứng dụng có `ObservationRegistry` được cấu hình. Convention chỉ định metadata cho observation; nó không thay thế registry hoặc instrumentation.

Với ứng dụng Spring Boot, cách tích hợp được khuyến nghị là đăng ký convention dưới dạng bean. Nếu tự cấu hình GraphQL runtime, có thể truyền convention trực tiếp vào `GraphQlObservationInstrumentation`. Bài này trình bày cả hai cách và các nguyên tắc giữ metadata ổn định, an toàn cho metrics.

## 1. Observation convention giải quyết việc gì?

Một observation ghi nhận một hoạt động đang diễn ra. Convention cung cấp thông tin mô tả hoạt động đó:

- Tên observation dùng để nhận diện meter hoặc span.
- Contextual name dùng làm tên dễ đọc cho span.
- Low-cardinality key-values dùng làm metric tags và cũng có thể xuất hiện trong trace.
- High-cardinality key-values dành cho trace, không được đưa vào metrics.

Ví dụ, observation request mặc định có tên `graphql.request`. Convention gắn loại operation và outcome để dashboard có thể phân tích tỷ lệ query, mutation, subscription thành công hoặc lỗi.

Khi ứng dụng có nhiều phiên bản API, có thể bổ sung key `graphql.api.version`. Khi cần phân tích resolver, có thể phân nhóm field thành `catalog`, `account` hoặc `other`. Các nhãn này giúp dashboard lọc dữ liệu mà không tạo một time series cho từng request hoặc từng người dùng.

## 2. Ba convention trong Spring for GraphQL

Spring for GraphQL có ba interface convention tương ứng với ba loại observation:

| Convention | Observation | Context | Phạm vi |
| --- | --- | --- | --- |
| `ExecutionRequestObservationConvention` | `graphql.request` | `ExecutionRequestObservationContext` | Toàn bộ GraphQL request |
| `DataFetcherObservationConvention` | `graphql.datafetcher` | `DataFetcherObservationContext` | Một thao tác lấy dữ liệu của field |
| `DataLoaderObservationConvention` | `graphql.dataloader` | `DataLoaderObservationContext` | Một lần batch load |

Mỗi interface mở rộng `ObservationConvention<T>` của Micrometer. Convention có thể cung cấp tên observation, contextual name và hai nhóm key-values.

Spring cung cấp các implementation mặc định tương ứng:

- `DefaultExecutionRequestObservationConvention`.
- `DefaultDataFetcherObservationConvention`.
- `DefaultDataLoaderObservationConvention`.

Nên mở rộng implementation mặc định nếu chỉ muốn bổ sung một vài key. Cách này giữ lại metadata chuẩn và giảm nguy cơ vô tình bỏ mất key mà dashboard hoặc công cụ giám sát đang sử dụng.

## 3. Metadata mặc định của từng observation

Trước khi tùy chỉnh, cần biết convention mặc định đang phát ra những key nào.

**`graphql.request`**

| Cardinality | Key | Ý nghĩa |
| --- | --- | --- |
| Low | `graphql.operation.type` | `query`, `mutation`, `subscription` hoặc `operation` nếu không phân tích được document |
| Low | `graphql.outcome` | `SUCCESS`, `REQUEST_ERROR` hoặc `INTERNAL_ERROR` |
| High | `graphql.execution.id` | ID của lần thực thi GraphQL |
| High | `graphql.operation.name` | Tên operation do client gửi |

**`graphql.datafetcher`**

| Cardinality | Key | Ý nghĩa |
| --- | --- | --- |
| Low | `graphql.error.type` | Tên class của lỗi data fetching |
| Low | `graphql.field.name` | Tên field đang được resolve |
| Low | `graphql.outcome` | `SUCCESS` hoặc `ERROR` |
| High | `graphql.field.path` | Đường dẫn đầy đủ tới field trong response |

Data fetcher observation chỉ được tạo cho thao tác lấy dữ liệu được xem là non-trivial. Việc đọc property đơn giản từ một Java object thường không tạo observation riêng.

**`graphql.dataloader`**

| Cardinality | Key | Ý nghĩa |
| --- | --- | --- |
| Low | `graphql.error.type` | Tên class của lỗi batch loading |
| Low | `graphql.loader.name` | Tên DataLoader |
| Low | `graphql.outcome` | `SUCCESS` hoặc `ERROR` |
| High | `graphql.loader.size` | Số key trong batch |

DataLoader observation theo dõi các lời gọi `@BatchMapping` và DataLoader đăng ký thủ công được instrumentation hỗ trợ. Convention cho DataLoader được bổ sung từ Spring for GraphQL 1.4.0.

## 4. Context cung cấp dữ liệu gì cho convention?

Convention không cần tự parse GraphQL document hoặc tự đo thời gian. Instrumentation truyền một context phù hợp vào convention.

**ExecutionRequestObservationContext**

Context request cung cấp:

- `getExecutionInput()`: input GraphQL của request.
- `getExecutionContext()`: execution context khi đã có.
- `getExecutionResult()`: kết quả thực thi khi đã có.

Có thể dùng context để đọc thông tin đã được đưa vào GraphQL execution input hoặc kết quả thực thi. Không nên lấy toàn bộ variables hay raw document rồi đưa vào metrics.

**DataFetcherObservationContext**

Context data fetcher cung cấp:

- `getEnvironment()`: `DataFetchingEnvironment` của field đang chạy.
- `getValue()`: giá trị được data fetcher trả về nếu có.

Từ `DataFetchingEnvironment`, convention có thể đọc field definition, field path, GraphQL context và thông tin execution liên quan. Chỉ chọn metadata có ích và có miền giá trị được kiểm soát.

**DataLoaderObservationContext**

Context DataLoader cung cấp:

- `getDataLoader()`: DataLoader đang thực hiện batch.
- `getEnvironment()`: batch loader environment.
- `getKeys()`: các key được yêu cầu trong batch.
- `getResult()`: danh sách kết quả đã resolve.

Không đưa trực tiếp key hoặc result vào metric tag. Các giá trị này thường là ID, mã tài khoản hoặc dữ liệu nghiệp vụ và có thể tạo cardinality rất cao.

## 5. Tùy chỉnh convention trong Spring Boot

Trong ứng dụng Spring Boot, hãy đăng ký bean có kiểu convention tương ứng. Spring GraphQL auto-configuration sử dụng convention bean khi tạo observation instrumentation.

Ví dụ cấu hình request convention:

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
    ExecutionRequestObservationConvention executionRequestConvention() {
        return new ApiVersionRequestConvention();
    }
}

class ApiVersionRequestConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.api.version", "v1"));
    }
}
~~~

Convention mặc định vẫn tạo `graphql.operation.type` và `graphql.outcome`. Convention tùy chỉnh chỉ thêm `graphql.api.version=v1`.

Key này phù hợp với low cardinality vì giá trị được kiểm soát bởi ứng dụng và chỉ thay đổi khi phiên bản API thay đổi. Nếu ứng dụng chỉ có một API version trong deployment, giá trị này có thể không thêm nhiều thông tin; hãy chỉ thêm tag khi nó hỗ trợ một truy vấn vận hành thực tế.

## 6. Phân loại operation bằng convention

Có thể bổ sung một nhãn nhóm operation để dashboard phân biệt những luồng quan trọng. Không dùng raw operation name do client tự gửi làm low-cardinality key vì client có thể tạo vô hạn tên khác nhau.

Một cách an toàn là duy trì allow-list các operation name đã biết và ánh xạ về một số nhóm cố định:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;

class OperationGroupRequestConvention
        extends DefaultExecutionRequestObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            ExecutionRequestObservationContext context) {

        String operationName = context.getExecutionInput().getOperationName();
        String group = operationGroup(operationName);

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.operation.group", group));
    }

    private String operationGroup(String operationName) {
        if (operationName == null) {
            return "unnamed";
        }

        return switch (operationName) {
            case "FindBook", "SearchBooks" -> "catalog-read";
            case "CreateBook", "UpdateBook" -> "catalog-write";
            case "SignIn", "RefreshSession" -> "identity";
            default -> "other";
        };
    }
}
~~~

Convention đọc operation name từ `ExecutionInput`, ánh xạ nó về một nhóm được allow-list rồi thêm key mới. Luôn giữ nhánh `other` để tên operation mới không làm tăng cardinality. Nếu document không có operation name, nhãn sẽ là `unnamed`.

Đây là một lựa chọn thay thế cho `ApiVersionRequestConvention` ở phần trước. Chọn convention request phù hợp với nhu cầu; không đăng ký cả hai bean cùng kiểu trong cùng application context.

Một lựa chọn đơn giản hơn là chỉ thêm API version hoặc service name cố định. Không cần thêm tag chỉ vì convention cho phép làm điều đó.

## 7. Tùy chỉnh DataFetcherObservationConvention

Data fetcher convention hữu ích khi muốn phân nhóm resolver theo miền nghiệp vụ. Ví dụ, API có các nhóm catalog và people. Field name được ánh xạ về một nhãn cố định:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DataFetcherObservationContext;
import org.springframework.graphql.observation.DataFetcherObservationConvention;
import org.springframework.graphql.observation.DefaultDataFetcherObservationConvention;

class FieldDomainDataFetcherConvention
        extends DefaultDataFetcherObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            DataFetcherObservationContext context) {

        String fieldName =
            context.getEnvironment().getFieldDefinition().getName();

        String fieldDomain = switch (fieldName) {
            case "book", "books", "searchBooks" -> "catalog";
            case "author", "authors" -> "people";
            default -> "other";
        };

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.field.domain", fieldDomain));
    }
}
~~~

Đăng ký class này bằng một bean kiểu `DataFetcherObservationConvention` trong cấu hình Spring Boot.

Convention mặc định tiếp tục cung cấp field name, outcome và error type. Key mới `graphql.field.domain` có đúng ba giá trị: `catalog`, `people` và `other`.

Không đưa nguyên field path vào low-cardinality key. Một field lồng trong list có thể tạo path chứa index hoặc cấu trúc thay đổi theo request; metadata đó phù hợp với high-cardinality trace hơn.

Cũng không đưa argument của field như `bookId`, email hoặc filter value vào convention. Chúng có thể là dữ liệu nhạy cảm và không phù hợp làm metric tag.

## 8. Tùy chỉnh DataLoaderObservationConvention

Từ Spring for GraphQL 1.4.0, có thể tùy chỉnh convention cho DataLoader observation. Ví dụ sau thêm một nhãn domain dùng chung cho các loader thuộc catalog service:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DataLoaderObservationContext;
import org.springframework.graphql.observation.DataLoaderObservationConvention;
import org.springframework.graphql.observation.DefaultDataLoaderObservationConvention;

class CatalogDataLoaderConvention
        extends DefaultDataLoaderObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            DataLoaderObservationContext context) {

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.loader.domain", "catalog"));
    }
}
~~~

Đăng ký class này bằng một bean kiểu `DataLoaderObservationConvention` trong cấu hình Spring Boot.

Convention mặc định vẫn ghi tên loader, outcome và error type. Key mới `graphql.loader.domain` phân nhóm các batch loader thuộc miền catalog.

Ví dụ này giả định convention bean chỉ áp dụng cho một nhóm loader thuộc cùng domain. Nếu ứng dụng có nhiều miền nghiệp vụ, hãy ánh xạ loader vào một tập nhãn nhỏ như `catalog`, `identity` hoặc `other`. Không đưa danh sách key, ID của entity hoặc nội dung result vào low-cardinality key.

`DataLoaderObservationContext` cho phép đọc danh sách key và result, nhưng không có nghĩa các giá trị đó nên xuất hiện trong metrics. Thông tin kích thước batch đã được convention mặc định cung cấp qua high-cardinality key `graphql.loader.size`.

## 9. Đăng ký cả ba convention trong một cấu hình

Một ứng dụng có thể cung cấp cả ba bean trong cùng cấu hình:

~~~java
@Configuration
public class AllGraphQlObservationConventionsConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestConvention() {
        return new ApiVersionRequestConvention();
    }

    @Bean
    DataFetcherObservationConvention dataFetcherConvention() {
        return new FieldDomainDataFetcherConvention();
    }

    @Bean
    DataLoaderObservationConvention dataLoaderConvention() {
        return new CatalogDataLoaderConvention();
    }
}
~~~

`ApiVersionRequestConvention`, `FieldDomainDataFetcherConvention` và `CatalogDataLoaderConvention` là các class đã được định nghĩa trong những phần trước. Tách class giúp unit test từng convention độc lập và tránh một cấu hình quá dài.

Cấu hình tổng hợp này thay thế cấu hình request-only ở phần 5. Khi dùng nó, hãy bỏ bean request convention riêng ở cấu hình trước để application context chỉ có một bean cho mỗi loại convention.

Mỗi loại convention có một trách nhiệm và context riêng. Không đăng ký cùng lúc nhiều bean cùng loại nếu không có chủ đích thay thế convention mặc định; việc chọn bean có thể trở nên mơ hồ hoặc làm auto-configuration không khởi tạo như mong đợi.

Nếu chỉ cần tùy chỉnh request observation, chỉ đăng ký request convention. Data fetcher và DataLoader có thể tiếp tục dùng convention mặc định.

## 10. Tùy chỉnh contextual name và observation name

Ngoài key-value, convention còn kiểm soát:

- `getName()`: tên observation được dùng làm tên meter.
- `getContextualName(context)`: tên dễ đọc cho span trong trace.

Thông thường nên giữ tên mặc định `graphql.request`, `graphql.datafetcher` và `graphql.dataloader`. Dashboard, alert và truy vấn Prometheus thường phụ thuộc vào các tên này. Đổi tên có thể làm hệ thống giám sát coi observation mới là một meter khác.

Nếu muốn span dễ đọc hơn, có thể override contextual name trong convention:

~~~java
@Override
public String getContextualName(
        ExecutionRequestObservationContext context) {
    return "graphql request";
}
~~~

Contextual name nên ngắn, ổn định và không chứa ID người dùng, ID entity hoặc toàn bộ GraphQL document. Có thể giữ nguyên implementation mặc định nếu tên trace hiện tại đã đủ rõ.

## 11. Tự cấu hình GraphQlObservationInstrumentation

Với ứng dụng không dùng Spring Boot auto-configuration, có thể tạo `GraphQlObservationInstrumentation` và truyền các convention vào constructor:

~~~java
import io.micrometer.observation.ObservationRegistry;

import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlObservationInstrumentation instrumentation =
    new GraphQlObservationInstrumentation(
        observationRegistry,
        requestConvention,
        dataFetcherConvention,
        dataLoaderConvention
    );
~~~

Sau đó đăng ký instrumentation này với GraphQL Java builder được dùng bởi `GraphQlSource`. Ví dụ về điểm tích hợp:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
    .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
    .configureGraphQl(builder ->
        builder.instrumentation(instrumentation)
    )
    .build();
~~~

Đây là cấu hình thủ công cho ứng dụng tự quản lý GraphQL runtime. Cần cung cấp `ObservationRegistry` và các bean/dependency cần thiết theo cách ứng dụng được xây dựng.

Không thêm instrumentation thủ công nếu Spring Boot đã cấu hình GraphQL observation instrumentation. Nếu cả auto-configuration và cấu hình thủ công cùng đăng ký instrumentation, observation có thể bị ghi nhận trùng hoặc pipeline trở nên khó kiểm soát.

## 12. Lưu ý constructor theo phiên bản Spring for GraphQL

API constructor của `GraphQlObservationInstrumentation` đã thay đổi khi DataLoader observation được bổ sung:

| Phiên bản API | Constructor | Trạng thái |
| --- | --- | --- |
| Trước 1.4.0 | `GraphQlObservationInstrumentation(ObservationRegistry)` | Dùng convention mặc định |
| Từ 1.1.0 | Constructor 3 tham số: registry, request convention, data fetcher convention | Đã deprecated từ 1.4.0, dự kiến loại bỏ |
| Từ 1.4.0 | Constructor 4 tham số có thêm data loader convention | Dùng khi cần truyền convention thủ công cho cả ba loại |

`DataLoaderObservationConvention` và `DataLoaderObservationContext` được giới thiệu từ Spring for GraphQL 1.4.0. Nếu dự án đang dùng nhánh cũ hơn, API DataLoader convention có thể chưa tồn tại.

Với ứng dụng Spring Boot, hãy để Spring Boot quản lý version Spring for GraphQL qua dependency management/BOM và đăng ký convention bằng bean. Cách này tránh phải tự gọi constructor instrumentation trong phần lớn ứng dụng.

## 13. Khi nào nên mở rộng default convention, khi nào implement interface?

Mở rộng class mặc định phù hợp khi:

- Muốn thêm một hoặc vài key-value.
- Muốn giữ các key chuẩn và cách tính outcome của Spring.
- Chỉ cần điều chỉnh một phần metadata.
- Muốn giảm code phải tự bảo trì khi framework thay đổi.

Implement trực tiếp interface phù hợp khi:

- Cần kiểm soát toàn bộ tên observation và key-value.
- Muốn định nghĩa một quy ước metadata hoàn toàn khác.
- Có lý do rõ ràng để thay đổi contextual name hoặc cách phân loại outcome.

Khi implement trực tiếp, cần cung cấp đầy đủ hợp đồng của Micrometer convention: tên observation, contextual name, low-cardinality key-values và high-cardinality key-values. Cũng cần bảo đảm convention chỉ áp dụng cho đúng context type.

Không implement lại toàn bộ convention chỉ để thêm một tag. Mở rộng default class thường dễ đọc, ít lỗi và giữ được tính tương thích hơn.

## 14. Phân biệt convention và ObservationFilter

`ObservationConvention` xác định metadata ban đầu cho một loại observation cụ thể. `ObservationFilter` là bước hậu xử lý trên registry, có thể thay đổi tên hoặc key-value sau khi convention đã chạy.

| Tiêu chí | ObservationConvention | ObservationFilter |
| --- | --- | --- |
| Phạm vi | Một loại observation có context cụ thể | Các observation đi qua registry |
| Vai trò | Định nghĩa tên và metadata chuẩn | Sửa hoặc bổ sung metadata sau đó |
| Phù hợp khi | Tùy chỉnh GraphQL request/data fetcher/DataLoader | Chuẩn hóa metadata dùng chung toàn ứng dụng |
| Nguy cơ | Có thể làm mất key mặc định nếu tự implement thiếu | Có thể vô tình tác động tới HTTP, database hoặc messaging observations |

Nếu chỉ muốn thêm `graphql.api.version` vào request GraphQL, hãy dùng request convention. Không nên dùng filter toàn cục để kiểm tra nhiều context type và tự thêm logic GraphQL vào một nơi vốn được chia sẻ bởi toàn ứng dụng.

## 15. Cardinality và bảo vệ dữ liệu

Khi thêm key mới, phải quyết định rõ nó là low hay high cardinality.

**Nên dùng low cardinality cho:**

- Phiên bản API trong một tập nhỏ.
- Nhóm operation đã allow-list.
- Miền nghiệp vụ như catalog, identity hoặc billing.
- Loại resolver được chuẩn hóa.
- Nhóm DataLoader đã được kiểm soát.

**Không dùng low cardinality cho:**

- User ID, tenant ID hoặc account ID.
- Email, username hoặc session ID.
- ID sách, ID đơn hàng hoặc ID tác giả.
- GraphQL arguments và variables.
- Raw operation name do client tự đặt.
- Raw field path hoặc GraphQL document.

High-cardinality key chỉ phù hợp cho traces, không phải metrics. Nhưng high cardinality không có nghĩa là dữ liệu tự động an toàn: trace vẫn có thể được lưu lâu, truy vấn hoặc chia sẻ rộng. Chỉ đưa metadata thật sự cần thiết vào trace và tuân theo chính sách dữ liệu của hệ thống.

Không dùng key name khác nhau cho cùng một ý nghĩa ở các service nếu có thể thống nhất. Quy ước tên nhất quán giúp dashboard, alert và truy vấn trace dễ bảo trì.

## 16. Kiểm thử convention tùy chỉnh

Có thể unit test convention trực tiếp mà không cần khởi động HTTP server. Ví dụ kiểm tra request convention giữ key mặc định và thêm API version:

~~~java
package com.example.graphql.observability;

import static org.assertj.core.api.Assertions.assertThat;

import graphql.ExecutionInput;
import io.micrometer.common.KeyValue;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;

class ApiVersionRequestConventionTests {

    private final ExecutionRequestObservationConvention convention =
        new ApiVersionRequestConvention();

    @Test
    void keepsDefaultKeysAndAddsApiVersion() {
        ExecutionInput input = ExecutionInput.newExecutionInput(
            "{ books { id } }"
        ).build();

        ExecutionRequestObservationContext context =
            new ExecutionRequestObservationContext(input);

        assertThat(convention.getLowCardinalityKeyValues(context))
            .contains(KeyValue.of("graphql.api.version", "v1"));
    }
}
~~~

Test này tập trung vào contract của convention. Có thể bổ sung test để xác minh:

- Các low-cardinality key mặc định vẫn tồn tại.
- Key mới chỉ nhận giá trị trong tập đã quy định.
- High-cardinality key không bị chuyển nhầm sang low cardinality.
- Field lạ được ánh xạ thành `other`.
- DataLoader convention không đưa key hoặc result vào metrics.
- Observation name vẫn giữ nguyên nếu dashboard đang sử dụng tên mặc định.

Ngoài unit test, nên có integration test với GraphQL runtime và `SimpleMeterRegistry` hoặc registry test phù hợp. Integration test xác minh convention thực sự được Spring Boot auto-configuration sử dụng và meter xuất hiện sau khi gửi GraphQL operation.

## 17. Lỗi thường gặp khi tùy chỉnh convention

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Convention tùy chỉnh không được dùng | Bean sai interface hoặc GraphQL instrumentation được tự cấu hình ở nơi khác | Kiểm tra bean type và auto-configuration |
| Mất key mặc định sau khi tùy chỉnh | Override trả về KeyValues mới mà không gọi super | Kết hợp `super.getLowCardinalityKeyValues(context)` |
| DataLoader convention không compile | Spring for GraphQL thấp hơn 1.4.0 | Nâng version phù hợp hoặc chỉ tùy chỉnh các convention có sẵn |
| Dùng constructor 3 tham số trên version mới | Constructor đã deprecated từ 1.4.0 | Dùng constructor 4 tham số nếu tự cấu hình instrumentation |
| Metrics tạo quá nhiều time series | Đưa ID, field path hoặc operation name vào low cardinality | Ánh xạ về tập nhãn hữu hạn hoặc chuyển sang high cardinality nếu thực sự cần |
| GraphQL metrics bị ghi trùng | Auto-configuration và instrumentation thủ công cùng hoạt động | Chỉ giữ một cấu hình instrumentation |
| Dashboard không còn thấy meter cũ | Đổi tên observation | Giữ tên mặc định hoặc lập kế hoạch migration dashboard |
| Trace lộ dữ liệu người dùng | Thêm variables hoặc key vào contextual name | Chỉ ghi metadata đã chuẩn hóa và được phép |
| DataFetcher observation không có cho mọi field | Field chỉ đọc property đơn giản | Đây là hành vi instrumentation dự kiến |
| Convention đọc context quá sớm | Dữ liệu execution result chưa có ở thời điểm đó | Dùng dữ liệu sẵn có tại lifecycle tương ứng và kiểm tra nullability |

## 18. Checklist triển khai

- Đã xác định cần tùy chỉnh request, data fetcher hay DataLoader convention?
- Đã kiểm tra các key mặc định trước khi bổ sung metadata?
- Đã mở rộng default convention khi chỉ cần thêm key?
- Spring Boot đã nhận convention thông qua bean đúng interface?
- Ứng dụng tự cấu hình đã truyền đúng convention vào instrumentation?
- Tên observation có được giữ ổn định để dashboard không bị gián đoạn?
- Low-cardinality key chỉ nhận giá trị hữu hạn và có kiểm soát?
- ID, arguments, variables và dữ liệu cá nhân không bị đưa vào metric tags?
- DataLoader convention chỉ dùng API có từ Spring for GraphQL 1.4.0 trở lên?
- Constructor instrumentation có tương thích version và không dùng API deprecated?
- Unit test kiểm tra key mặc định và key tùy chỉnh?
- Integration test xác minh Spring thực sự ghi meter/trace theo convention?
- Không có instrumentation trùng lặp giữa auto-configuration và cấu hình thủ công?

GraphQL observation convention là nơi định nghĩa cách Spring for GraphQL mô tả request, data fetcher và DataLoader trong metrics/traces. Hãy bắt đầu từ convention mặc định, chỉ bổ sung metadata có ích và giữ low-cardinality key trong một tập giá trị hữu hạn. Với Spring Boot, đăng ký convention bằng bean; với GraphQL runtime tự cấu hình, truyền chúng vào constructor bốn tham số của `GraphQlObservationInstrumentation` trên Spring for GraphQL 1.4.0 trở lên. Kiểm thử cả key mặc định, key mới và việc auto-configuration thực sự sử dụng convention sẽ giúp metadata nhất quán mà không làm dashboard phình cardinality.

## Tài liệu tham khảo

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [ExecutionRequestObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/ExecutionRequestObservationConvention.html)
- [DataFetcherObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DataFetcherObservationConvention.html)
- [DataLoaderObservationConvention API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/DataLoaderObservationConvention.html)
- [GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Micrometer Observation — Concepts](https://docs.micrometer.io/micrometer/reference/observation.html)

