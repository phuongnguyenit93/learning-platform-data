# ObservationFilter để thay đổi context

## Mục tiêu học tập

Trong chương **Observation API**, bài này tập trung vào cách dùng `ObservationFilter` của **Micrometer Observation** để điều chỉnh metadata của một observation trước khi hoàn tất. Đây là một phần của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**: sử dụng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation.

Sau bài học, bạn có thể:

1. Mô tả vai trò của `Observation`, `Observation.Context`, `ObservationRegistry`, `ObservationHandler` và vị trí của `ObservationFilter` trong vòng đời observation.
2. Viết bean `ObservationFilter` nhằm **thêm, sửa hoặc loại bỏ key-value** trong context khi kết thúc observation.
3. Chỉ áp dụng filter cho **module entry observations** bằng `ModulithContext`, tránh gắn nhãn lên toàn bộ HTTP/DB/Redis observations ngoài ý muốn.
4. Phân biệt rõ `ObservationFilter` với `ObservationConvention`, `ObservationPredicate`, `ObservationHandler` và cơ chế **context propagation** qua thread hoặc message broker.
5. Chọn **low-cardinality** và **high-cardinality** key-value phù hợp, hạn chế lộ dữ liệu nhạy cảm.
6. Kiểm chứng thay đổi trong context, metric và trace, đồng thời nhận ra giới hạn của filter chạy ở giai đoạn `stop`.
7. Biết khi nào nên dùng filter toàn cục, khi nào nên chọn `ModulithObservationConvention` hoặc đặt metadata tại nơi tạo observation.

> **Phạm vi:** Ví dụ sử dụng Java 17+, Spring Boot có Micrometer Observation, và Spring Modulith thuộc dòng hỗ trợ `ModulithContext`. Tên class/API và chi tiết dependency phải được kiểm tra với phiên bản Spring Boot, Spring Modulith và Micrometer được triển khai. `ObservationFilter` là API của **Micrometer**; Spring Modulith sử dụng nó trong cơ chế quan sát module nhưng không phát minh một interface filter riêng cùng tên.

---

## 1. Observation Context là gì và vì sao cần thay đổi nó?

Trong Micrometer, một `Observation` biểu diễn một hoạt động được theo dõi, chẳng hạn một HTTP request, một lời gọi qua API của application module, hoặc một đoạn xử lý đơn hàng do ứng dụng instrument. Nó có một **`Observation.Context`** chứa metadata để các `ObservationHandler` chuyển hóa thành metric, span hoặc tín hiệu quan sát khác.

Context là một đối tượng **mutable**, có thể mang:

- **Tên observation:** `name`, thường được dùng để gom các lần đo cùng loại.
- **Tên ngữ cảnh:** `contextualName`, giúp biểu diễn hoạt động trong trace.
- **Low-cardinality key-values:** các nhãn có tập giá trị hữu hạn như `module.identifier=orders` hoặc `shop.outcome=SUCCESS`.
- **High-cardinality key-values:** thuộc tính nhiều giá trị khác nhau, có thể dùng trong trace khi được cấu hình phù hợp; không thích hợp làm metric labels.
- **Thông tin sự kiện và lỗi** được ghi qua API Observation.
- **Dữ liệu tùy ý** trong map của context, dùng để trao đổi thông tin giữa instrumented code và các thành phần quan sát.

Ví dụ, một lời gọi vào module `inventory` được Spring Modulith instrument có thể mang:

~~~text
Observation name: <theo convention của Spring Modulith>
Context type:     ModulithContext
Low-cardinality:
  module.identifier = inventory
  module.name       = Inventory
  module.invocation-type = bean
High-cardinality:
  module.method     = InventoryFacade.reserve(...)
~~~

Đây là **hình dung khái niệm**. Tên observation, biểu diễn method và cách backend xuất attributes phải lấy từ telemetry của bản ứng dụng thực tế. Các trường này giúp phân tích hoạt động module; chúng không chứng minh yêu cầu giữ kho đã commit thành công.

### 1.1. Khi metadata có mặt muộn hơn thời điểm bắt đầu

Một số thuộc tính chỉ được biết **sau khi hoạt động kết thúc**:

- Kết quả cuối được phân loại thành `SUCCESS`, `REJECTED` hoặc `FAILED`.
- Lỗi đã được xác định và ánh xạ về một nhóm đã chuẩn hóa.
- Dữ liệu tạm trong context cần được làm sạch trước bước handler xử lý cuối.
- Nhãn vận hành phải được thêm có điều kiện tùy kiểu context.

`ObservationFilter` là một điểm mở rộng để xử lý kiểu nhu cầu này trong **giai đoạn hoàn tất observation**.

### 1.2. Ví dụ nghiệp vụ

Giả sử module `orders` gọi module `payments`. Nhóm vận hành muốn những **module entry observations** có thêm nhãn `architecture.component=application-module` để truy vấn riêng với HTTP hoặc JDBC spans. Nhãn này ổn định và không phải business ID.

Một filter có thể kiểm tra xem `context instanceof ModulithContext` rồi bổ sung nhãn đó. Các observations khác vẫn giữ nguyên.

Nếu muốn thêm nhãn `shop.outcome` dựa trên một giá trị được ghi trong quá trình xử lý, filter cũng có thể đọc giá trị từ `Observation.Context` khi observation kết thúc và chuẩn hóa thành một tập hữu hạn.

## 2. ObservationFilter nằm ở đâu trong vòng đời?

Micrometer phân biệt những thành phần:

| Thành phần | Trách nhiệm chính |
| --- | --- |
| `ObservationRegistry` | Quản lý cấu hình observation, handlers, filters, predicates và conventions. |
| `Observation` | Đại diện một đơn vị công việc được quan sát; có `start()`, `openScope()`, `error(...)`, `stop()`. |
| `Observation.Context` | Giữ metadata/trạng thái của observation; mutable. |
| `ObservationConvention` | Định nghĩa tên và các key-value theo loại context, trước hoặc trong quá trình tạo/khởi tạo metadata theo cơ chế instrumentation. |
| `ObservationPredicate` | Quyết định một observation có bị biến thành **no-op** khi được tạo hay không. |
| `ObservationFilter` | **Biến đổi context khi observation dừng**, trước khi các handler xử lý bước `onStop`. |
| `ObservationHandler` | Phản ứng với các sự kiện vòng đời, như `onStart`, `onError`, `onStop`; có thể tạo meter hoặc tracing span. |

Theo tài liệu Micrometer, khi gọi `Observation.stop()`, các `ObservationFilter` đã đăng ký được chạy **trước** các callback `ObservationHandler.onStop(...)`. Vì vậy filter có thể làm giàu context với thông tin có tại thời điểm kết thúc để handler sử dụng.

~~~mermaid
sequenceDiagram
    participant App as Code / Spring Modulith
    participant Obs as Observation
    participant Filter as ObservationFilter
    participant Handler as ObservationHandler

    App->>Obs: createNotStarted(...)
    App->>Obs: start()
    Obs->>Handler: onStart(context)
    App->>Obs: openScope(), thực thi logic
    App->>Obs: error(...) nếu lỗi
    Obs->>Handler: onError(context) nếu áp dụng
    App->>Obs: stop()
    Obs->>Filter: map(context)
    Filter-->>Obs: context đã chỉnh sửa
    Obs->>Handler: onStop(context)
    Note over Handler: Ghi nhận metadata theo handler/backend
~~~

Sơ đồ nhấn mạnh **vị trí filter trong giai đoạn stop**, không mô tả toàn bộ callback hoặc thứ tự nội bộ ở mọi implementation. `openScope()` và `close()` có lifecycle riêng; ở API `observation.observe(...)`, Micrometer hỗ trợ bao quanh một khối code và tự dừng observation.

### 2.1. Giới hạn quan trọng của thời điểm `stop`

- Filter **không chạy trước `onStart`**. Nếu handler quyết định tạo hoặc đặt tên span/timer ngay lúc start, sửa metadata ở stop không mặc nhiên thay đổi toàn bộ quyết định đã diễn ra.
- Filter **không thể sửa thời gian đã trôi qua**, trả về HTTP response khác, hoặc hủy tác dụng phụ nghiệp vụ.
- Nếu observation không được tạo, là no-op, hoặc không được dừng theo luồng mong đợi, filter có thể không được gọi theo cách bạn dự kiến.
- Một filter xóa nhãn nhạy cảm ở stop **không đảm bảo** dữ liệu đó chưa bị đọc, log hoặc xuất ở bước lifecycle trước. Biện pháp tốt nhất là **không đưa dữ liệu nhạy cảm vào telemetry ngay từ nguồn**.
- Một số handler có thể xử lý metadata ở `onStart`, `onEvent` và `onStop` khác nhau; luôn xác minh ở output thực thay vì chỉ dựa vào việc context cuối cùng đã đổi.

## 3. API cốt lõi của ObservationFilter

Interface đến từ Micrometer:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
~~~

Phương thức quan trọng:

~~~java
Observation.Context map(Observation.Context context);
~~~

Ý nghĩa hợp đồng:

1. Nhận context hiện tại.
2. Có thể đọc tên, thuộc tính hoặc kiểu cụ thể của context.
3. Có thể thêm/sửa/xóa key-values hoặc thay đổi một số metadata.
4. **Trả về context** để chuỗi filter/handler tiếp tục xử lý.

Một filter ngắn nhất:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationFilter;

ObservationFilter environmentFilter =
    context -> context.addLowCardinalityKeyValue(
        KeyValue.of("deployment.zone", "zone-a")
    );
~~~

Ví dụ chỉ minh họa lời gọi API. Khi dùng trong Spring Boot, nên đăng ký filter thành bean hoặc cấu hình trong `ObservationRegistry`. Nếu dùng giá trị chung, cố định cho toàn ứng dụng như region/environment, trước hết cân nhắc **common key-values** của Spring Boot thay vì tự viết filter.

### 3.1. Các thao tác phổ biến trên Context

~~~java
// Thêm hoặc cập nhật nhãn giá trị hữu hạn:
context.addLowCardinalityKeyValue(KeyValue.of("shop.outcome", "SUCCESS"));

// Thêm thuộc tính có cardinality cao vào context:
context.addHighCardinalityKeyValue(KeyValue.of("workflow.ref", "opaque-id"));

// Loại bỏ một nhãn theo tên:
context.removeHighCardinalityKeyValue("workflow.ref");

// Đổi tên observation nếu yêu cầu được xác định rõ:
context.setName("shop.checkout");
~~~

Những dòng này là **các thao tác API rời nhau**, không phải gợi ý chạy đồng thời cho mọi observation.

Việc thêm `workflow.ref` ở high-cardinality vẫn cần cân nhắc riêng về quyền truy cập và bảo mật dữ liệu. Ngay cả khi high-cardinality key thường dành cho tracing hơn là metrics, không nên dùng đó làm lý do đưa PII, token hoặc payload bí mật vào telemetry.

### 3.2. Đừng thay đổi tất cả observations vô điều kiện

Một `ObservationFilter` được đăng ký ở `ObservationRegistry` có thể áp dụng cho **nhiều loại observation**: HTTP server, HTTP client, database, messaging và module observations. Nếu code viết:

~~~java
@Bean
ObservationFilter broadFilter() {
    return context -> {
        context.setName("shop.operation"); // Không nên làm với mọi context.
        return context;
    };
}
~~~

thì có thể làm mất tên observation do các instrumentation khác cung cấp và phá dashboard/timer/trace queries.

Thay vào đó, xác định điều kiện rõ ràng:

- `instanceof ModulithContext` khi mục tiêu là module entry.
- Một **context type cụ thể** khi nhắm đến một instrumentation của Spring.
- Tên observation **do ứng dụng sở hữu** khi cần xử lý custom observation.
- Trường nội bộ đã được định nghĩa rõ khi muốn đọc kết quả xử lý.

Ưu tiên loại context thay vì so khớp một tên display có thể đổi qua phiên bản nếu API cung cấp kiểu phù hợp.

## 4. Cấu hình trong Spring Boot và Spring Modulith

Spring Boot tự động đăng ký các bean `ObservationFilter`, `ObservationPredicate`, `GlobalObservationConvention` và `ObservationHandler` với `ObservationRegistry` được auto-configure. Vì vậy trong ứng dụng Spring Boot có hạ tầng Micrometer Observation, cách đơn giản là khai báo một bean.

### 4.1. Dependencies tối thiểu theo nhu cầu

Để dùng module instrumentation và code có tham chiếu `ModulithContext`:

~~~groovy
dependencies {
    // Ví dụ Gradle; Spring Modulith BOM đã được quản lý ở build.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Chỉ cần khi mã Java import trực tiếp kiểu ModulithContext:
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Trong các phiên bản Spring Modulith phân chia artifact API và core, `-api` cho phép code compile với `ModulithContext`; Insight starter hoặc `-core` cung cấp instrumentation lúc runtime. Tùy ứng dụng, cấu hình Micrometer/Actuator và tracing exporter phải có nếu muốn xem metrics/traces bên ngoài. **Không cần `-api` chỉ để tạo một ObservationFilter chung dùng các kiểu Micrometer** nếu các dependency quan sát của Spring Boot đã hiện diện.

Maven tương đương:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
        <!-- Maven compile scope mặc định -->
    </dependency>
</dependencies>
~~~

Các đoạn này giả định **BOM Spring Modulith phù hợp với bản Spring Boot**. Không tự phối các version `-api` và `-core` khác release. Nếu chỉ muốn observability mà không cần Modulith Actuator, có thể chọn `spring-modulith-observability-core` theo dependency setup tương ứng.

### 4.2. Tách nhu cầu common tags và context filter

Nếu mục tiêu là thêm một giá trị tĩnh như region hoặc stack cho mọi observation, cấu hình Spring Boot thường ngắn hơn:

~~~yaml
management:
  observations:
    key-values:
      region: "asia-southeast"
      stack: "shop"
~~~

Cấu hình này tạo common key-values cho observations theo hỗ trợ Spring Boot. Khi giá trị cần xác định **theo context type** hoặc chỉ biết ở cuối công việc, `ObservationFilter` là lựa chọn phù hợp hơn.

## 5. Ví dụ 1: gắn tag chỉ cho Module Entry Span

Đây là trường hợp gắn trực tiếp với Spring Modulith. Ta muốn mọi lời gọi được instrument vào application module mang thêm nhãn `architecture.component=application-module`. HTTP spans và những observation thông thường khác sẽ không bị sửa.

~~~java
package com.example.shop.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;

@Configuration(proxyBeanMethods = false)
public class ModuleObservationFilterConfiguration {

    @Bean
    ObservationFilter moduleObservationFilter() {
        return context -> {

            if (context instanceof ModulithContext) {
                context.addLowCardinalityKeyValue(
                    KeyValue.of("architecture.component", "application-module")
                );
            }

            return context;
        };
    }
}
~~~

### 5.1. Vì sao nên kiểm tra `instanceof ModulithContext`?

`ModulithContext` là một `Observation.Context` chuyên biệt cho các module invocations mà Spring Modulith instrument. Kiểm tra kiểu giúp giới hạn tác động:

| Observation được tạo từ | Kiểu context có thể có | Filter ví dụ có sửa không? |
| --- | --- | --- |
| Lời gọi qua API application module | `ModulithContext` | **Có** |
| HTTP request do Spring Web quan sát | HTTP observation context của Spring | **Không** |
| JDBC/HTTP client instrumentation | Context đặc thù thư viện | **Không** |
| Observation tùy chỉnh `shop.checkout` với context mặc định | `Observation.Context` thông thường | **Không** |

Điều kiện đúng với các observation có context theo type trên. Không nên mặc định mọi lời gọi method nội bộ trong module đều được instrument thành `ModulithContext`; phạm vi instrument của Spring Modulith tập trung vào **điểm vào API của application module** và cơ chế được framework hỗ trợ.

### 5.2. Dữ liệu trước và sau filter

Một context Module Entry có thể chứa:

~~~text
Trước:
  module.identifier = inventory
  module.name       = Inventory
  module.invocation-type = bean

Sau:
  module.identifier = inventory
  module.name       = Inventory
  module.invocation-type = bean
  architecture.component = application-module
~~~

Hai trạng thái ở trên là **minh họa** về nội dung context khi filter được gọi. Chúng không bảo đảm mọi backend xuất đúng từng attribute, vì handler/exporter mới quyết định phần nào đi vào metric/traces.

### 5.3. Những gì không nên làm trong filter này

Không nên ghi đè `module.identifier` thành một giá trị cố định, vì nó là chiều thông tin quan trọng để phân biệt application module. Nếu cần nhóm module vào domain rộng hơn (`commerce` hoặc `backoffice`), thêm một tag mới có tập giá trị hữu hạn như `architecture.domain`, và **lập quy tắc ánh xạ module rõ ràng**.

Không truy vấn database hoặc gọi API ngoài từ `map(...)` để xác định nhãn. Filter chạy trong đường hoàn tất observation; truy vấn I/O ở đây có thể tăng độ trễ, gây vòng quan sát lồng nhau hoặc làm kết quả telemetry phụ thuộc vào dịch vụ ngoài.

## 6. Ví dụ 2: đọc kết quả xử lý từ context tại thời điểm stop

Ví dụ thứ hai minh họa ý nghĩa của việc filter chạy **sau khi** logic ứng dụng đã có kết quả. Ta tạo một custom observation `shop.checkout` và lưu outcome vào context.

### 6.1. Filter đọc dữ liệu và chuẩn hóa

~~~java
package com.example.shop.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CheckoutOutcomeFilterConfiguration {

    private static final String OUTCOME_KEY = "shop.checkout.outcome";

    @Bean
    ObservationFilter checkoutOutcomeFilter() {
        return context -> {

            if (!"shop.checkout".equals(context.getName())) {
                return context;
            }

            Object raw = context.get(OUTCOME_KEY);
            String outcome = (raw instanceof String value)
                ? switch (value) {
                    case "SUCCESS" -> "SUCCESS";
                    case "REJECTED" -> "REJECTED";
                    case "FAILED" -> "FAILED";
                    default -> "OTHER";
                }
                : "UNKNOWN";

            context.addLowCardinalityKeyValue(
                KeyValue.of("shop.outcome", outcome)
            );

            return context;
        };
    }
}
~~~

Hàm trên chỉ tạo tối đa **5 giá trị** cho `shop.outcome`: `SUCCESS`, `REJECTED`, `FAILED`, `OTHER`, `UNKNOWN`. Đây là tập hữu hạn thích hợp cho metric tag; giá trị outcome không chứa ID đơn hàng.

**Lưu ý:** filter nhận `Observation.Context` của một observation do ứng dụng tự sở hữu, không phải tự lấy được trạng thái giao dịch. Ai tạo observation cũng phải ghi dữ liệu vào context tại đúng thời điểm.

### 6.2. Code nghiệp vụ đặt outcome lên context

~~~java
package com.example.shop.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ObservationRegistry registry;

    public CheckoutService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void checkout() {
        Observation observation =
            Observation.createNotStarted("shop.checkout", registry);

        observation.observe(() -> {
            try {
                // Minh họa: thay bằng logic checkout thật.
                validateAndSubmitOrder();
                observation.getContext()
                    .put("shop.checkout.outcome", "SUCCESS");
            } catch (IllegalArgumentException rejected) {
                observation.getContext()
                    .put("shop.checkout.outcome", "REJECTED");
                throw rejected;
            } catch (RuntimeException failed) {
                observation.getContext()
                    .put("shop.checkout.outcome", "FAILED");
                throw failed;
            }
        });
    }

    private void validateAndSubmitOrder() {
        // Cài đặt nghiệp vụ của dự án; cố ý lược bỏ ở ví dụ.
    }
}
~~~

`observe(Runnable)` được Micrometer dùng để bao quanh một khối logic và quản lý vòng đời observation. Trong ví dụ, `ObservationFilter` đọc outcome đã được đặt vào context khi observation đi tới `stop()`.

Các nhánh `catch` chỉ minh họa phân loại lỗi ở tầng ứng dụng. Trong thực tế, `IllegalArgumentException` không mặc nhiên luôn là “đơn bị từ chối” trong mọi domain; nên thay bằng exception/decision cụ thể của ứng dụng. Một transaction bao ngoài có thể rollback sau thời điểm method trả về, nên `SUCCESS` ở ví dụ **chỉ biểu diễn kết quả của phần xử lý được instrument**, không phải bảo đảm toàn bộ giao dịch nghiệp vụ đã commit.

### 6.3. Tại sao không lấy ID làm low-cardinality tag?

Có thể người học muốn ghi:

~~~java
context.addLowCardinalityKeyValue(
    KeyValue.of("order.id", orderId.toString())
);
~~~

**Không nên làm:** mỗi `orderId` có thể trở thành một tổ hợp labels riêng trong meter backend, khiến cardinality và chi phí tăng mạnh. Để truy tìm một đơn cụ thể, dùng log có cấu trúc hoặc trace attributes theo chính sách dữ liệu phù hợp. Không cần đưa business ID vào mọi metric.

### 6.4. Nếu outcome được biết trước lúc bắt đầu?

Khi một giá trị đã có từ đầu và thuộc về định nghĩa của một loại observation, thêm trực tiếp qua `Observation.lowCardinalityKeyValue(...)` hoặc sử dụng `ObservationConvention` có thể đơn giản hơn. Filter đặc biệt hữu ích khi xử lý **metadata cuối vòng đời**, hoặc khi muốn áp dụng quy tắc chung cho nhiều nơi instrument theo một loại context.

## 7. Thêm, xóa, sửa key-value mà không làm hỏng metadata gốc

`ObservationFilter` có thể thao tác trên context, nhưng một thay đổi có thể ảnh hưởng đến cả metric và trace.

| Thao tác | Ví dụ | Cần cân nhắc |
| --- | --- | --- |
| **Thêm low-cardinality** | `component=application-module` | Có làm tăng số series? Có trùng key đã tồn tại? |
| **Thêm high-cardinality** | `internal.reference=...` | Có thực sự cần trace attribute? Có PII hoặc bí mật không? |
| **Xóa low-cardinality** | Xóa một tag lỗi thời | Có phá dashboard, alert, recording rule cũ? |
| **Xóa high-cardinality** | Bỏ trường chứa dữ liệu không nên xuất | Chỉ có hiệu lực trong giai đoạn filter; không thể bảo đảm chưa bị đọc trước đó. |
| **Đổi name** | `context.setName(...)` | Có làm thay đổi tên timer/observation series? Handler nào đã dùng tên cũ? |
| **Sửa dữ liệu map tùy chỉnh** | `context.put(...)` | Thành phần khác có cần loại/kiểu value cũ không? |

### 7.1. Ví dụ xóa một high-cardinality key

~~~java
@Bean
ObservationFilter removeForbiddenAttribute() {
    return context -> {
        if (context instanceof ModulithContext) {
            context.removeHighCardinalityKeyValue("customer.email");
        }
        return context;
    };
}
~~~

Đây là **biện pháp phòng vệ bổ sung**, không phải chính sách che dữ liệu tuyệt đối. Vì filter chạy lúc stop, một handler có thể đã đọc context ở `onStart` hoặc một pipeline khác đã ghi dữ liệu trước khi filter xóa. Tốt hơn là ngăn `customer.email` được đưa vào telemetry tại nguồn.

### 7.2. Tránh va chạm với key của Spring Modulith

Spring Modulith cung cấp key như:

- `module.identifier`;
- `module.name`;
- `module.invocation-type`;
- `module.method`.

Đừng tùy ý gán lại các key này với ý nghĩa khác, vì chúng là hợp đồng nhận diện module entry spans. Khi muốn thêm nhãn riêng, dùng namespace tách biệt như `architecture.component` hoặc `shop.outcome`.

Nếu có nhiều filter cùng ghi một key, kết quả có thể phụ thuộc vào **thứ tự filter** và cách xử lý key của context/handler. Hãy tập trung chính sách gắn nhãn của một observation ở một nơi có chủ sở hữu rõ và kiểm tra kết quả cuối, thay vì giả định filter nào đó luôn chạy trước filter khác.

### 7.3. “Thay đổi context” không đồng nghĩa “thay đổi kết quả nghiệp vụ”

`Observation.Context` là dữ liệu phục vụ quan sát. Sửa `shop.outcome` trên đó không thay đổi trạng thái đơn đã lưu, bản ghi thanh toán hoặc kết quả giữ kho. Nếu phát hiện bất biến nghiệp vụ sai, phải sửa logic giao dịch hoặc workflow, không sửa một tag quan sát để dashboard trông có vẻ thành công.

## 8. ObservationFilter so với Convention, Predicate và Handler

Đây là bốn extension point dễ bị nhầm:

| Yêu cầu | Điểm mở rộng phù hợp | Lý do |
| --- | --- | --- |
| Đổi tên/key-value mặc định cho một **loại observation** có context xác định | `ObservationConvention` | Diễn đạt quy tắc đặt tên và metadata theo loại context. |
| Với Spring Modulith, tùy biến tên và key-value của module entry observations | `ModulithObservationConvention` | API chuyên biệt cho `ModulithContext`; dễ duy trì hợp đồng module spans. |
| Loại trừ observation khỏi hệ thống quan sát từ lúc tạo | `ObservationPredicate` | Quyết định observation có no-op hay không; filter không có nhiệm vụ đó. |
| Thêm/sửa/xóa metadata khi observation kết thúc | `ObservationFilter` | Post-processing của mutable context trước `onStop`. |
| Tạo/tích hợp metrics, tracing hoặc log từ lifecycle | `ObservationHandler` | Xử lý `onStart`, `onStop`, `onError` và các callback được hỗ trợ. |
| Tạo counter riêng cho từng domain event của Modulith | `ModulithEventMetricsCustomizer` | Đây là extension point event counter, không phải filter module span. |
| Truyền trace/baggage qua executor, async listener hoặc broker | Context propagation/instrumentation tương ứng | Filter chỉ biến đổi context hiện tại tại stop, không tự vận chuyển trace qua thread. |

### 8.1. Vì sao không luôn chọn ObservationFilter?

Nếu yêu cầu là “mọi module entry span phải tên `shop.module.entry` thay tên mặc định”, dùng `ModulithObservationConvention` thường diễn đạt ý định rõ hơn, vì convention chuyên trách tên và metadata của loại observation đó.

Filter hợp lý khi:

- cần **post-process** thông tin chỉ có ở cuối hoạt động;
- muốn thêm một nhãn ổn định theo context type;
- muốn áp dụng chính sách bảo vệ/chuẩn hóa cho context của một số observations;
- có một custom observation do ứng dụng sở hữu và muốn biến trạng thái trong context thành nhãn ở stop.

Filter **không thay thế** một convention đầy đủ khi cần kiểm soát tên và key của loại observation trong toàn vòng đời.

### 8.2. Đừng nhầm với Filter của HTTP servlet

`ObservationFilter` không phải `jakarta.servlet.Filter`, `OncePerRequestFilter` hay Spring WebFlux `WebFilter`. Nó không nhận `HttpServletRequest` để quyết định có cho request đi tiếp hay không, và không sửa response body. Nó chỉ nhận **Observation.Context** phục vụ observability.

## 9. Mối liên hệ với Spring Modulith và context propagation

Spring Modulith tạo observations tại những điểm vào API module được framework instrument. Khi sử dụng Micrometer tracing, các observations có thể trở thành spans để hình dung luồng xử lý giữa modules.

Trong Javadoc của Spring Modulith, lớp hỗ trợ `ModuleIdentifierPassingObservationFilter` được mô tả có trách nhiệm **truyền key module identifier từ parent observation sang child observation**. Đây là một ví dụ về việc framework cũng sử dụng filter như một phần của pipeline metadata.

**Lưu ý theo phiên bản:** Một số dòng Spring Modulith dùng tên `ModulePassingObservationFilter`; các bản khác dùng `ModuleIdentifierPassingObservationFilter`. Những class ở package `support` là thành phần triển khai framework; không nên tự tạo bean hoặc phụ thuộc trực tiếp vào implementation chỉ để dùng tính năng mặc định. Hãy kiểm tra đúng Javadoc của release đang dùng.

### 9.1. “Truyền module identifier” khác “propagate trace context”

Hai khái niệm có tên tương tự nhưng khác phạm vi:

| Khái niệm | Dữ liệu liên quan | Mục tiêu |
| --- | --- | --- |
| **Module identifier passing/filter** | Key metadata như `module.identifier` trong các Observation.Context liên quan. | Giữ thông tin module trong một số observation theo cơ chế framework. |
| **Trace context propagation** | Trace/span context, baggage và thông tin cần qua ranh giới thực thi. | Duy trì tương quan giữa công việc trên nhiều thread/executor/message. |
| **Business correlation** | `orderId`, `eventId`, idempotency key. | Liên kết trạng thái và xử lý nghiệp vụ qua retry/thời gian. |

Một filter chạy ở stop **không thể tự bảo đảm** một `@Async` listener đang chạy ở thread khác nhận đúng trace context. Với executor, Spring Boot/Spring Framework có các hỗ trợ context propagation phù hợp, ví dụ sử dụng `ContextPropagatingTaskDecorator` ở những executor cần thiết và kiểm tra tương thích phiên bản. Với message broker hoặc giao tiếp giữa tiến trình, cần instrumentation và carrier propagation theo giao thức.

### 9.2. Những trường hợp filter không thể tự sửa

- Listener chạy ở trace khác vì context không được chuyển qua executor.
- Event đã publish nhưng message bị mất ở broker hoặc listener không được gọi.
- Transaction bị rollback sau khi span báo xử lý không lỗi.
- Một event được xử lý hai lần vì thiếu idempotency.
- Dashboard thiếu span vì sampling hoặc exporter sai.

Những vấn đề này cần kiểm tra đúng lớp: threading/messaging, event registry, transaction, metrics, exporter hoặc backend. Gắn thêm một tag trong `ObservationFilter` không giải quyết nguyên nhân.

## 10. Kiểm chứng filter trong ứng dụng

### 10.1. Mức 1: bean và registry

Trong Spring Boot có auto-configuration observability, một bean `ObservationFilter` sẽ được đăng ký với `ObservationRegistry`. Bắt đầu bằng kiểm tra:

1. Ứng dụng có hạ tầng Micrometer Observation chưa?
2. Filter bean có nằm trong component scan hoặc cấu hình `@Import`?
3. Với filter dùng `instanceof ModulithContext`, `spring-modulith-observability-api` có trên compile classpath?
4. Runtime có core/starter để tạo module observations?
5. Filter có được gọi với **loại context đúng** hay không?

Với Gradle, các lệnh kiểm tra classpath phổ biến:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Trong PowerShell trên Windows, có thể dùng `gradlew.bat` nếu build wrapper được tạo cho Windows. Lệnh chỉ kiểm tra dependencies, **không chứng minh** filter đã chạy với một module observation thực.

### 10.2. Mức 2: kiểm tra trực tiếp context ở cuối vòng đời

Một cách đơn giản để thử logic filter độc lập với Spring Modulith là tạo `ObservationRegistry` và một observation theo tên ứng dụng sở hữu.

**Ý tưởng kiểm thử:**

~~~java
// Pseudocode Java: trọng tâm là hành vi, không phải một bộ test hoàn chỉnh.
ObservationRegistry registry = ObservationRegistry.create();
registry.observationConfig()
    .observationFilter(context -> {
        if ("shop.example".equals(context.getName())) {
            context.addLowCardinalityKeyValue(
                KeyValue.of("test.marker", "present")
            );
        }
        return context;
    });

Observation observation =
    Observation.createNotStarted("shop.example", registry);

// Trong test tích hợp đầy đủ, đăng ký ObservationHandler tương ứng
// để kích hoạt/quan sát lifecycle và gọi stop thực sự.
observation.start();
observation.stop();

// Sau khi stop: kiểm tra observation.getContext()
// có low-cardinality key "test.marker" hay không.
~~~

Đoạn trên được ghi rõ là **pseudocode định hướng kiểm thử**: trong test thực, cần cấu hình handler/registry phù hợp, dùng assertions và xác minh callback đã chạy. Không suy từ một đoạn cấu hình filter rời rạc rằng metric hoặc span đã được export.

### 10.3. Mức 3: kiểm tra module entry thực tế

Một kịch bản integration hữu ích:

1. Trong `orders`, gọi một **Spring bean thuộc API** của module `inventory`, ví dụ `InventoryFacade.reserve(...)`.
2. Đảm bảo Modulith observability instrumentation được bật.
3. Tìm module entry observation/span của `inventory`.
4. Xác minh các metadata mặc định (`module.identifier`, `module.invocation-type`) vẫn có.
5. Kiểm tra nhãn mới `architecture.component=application-module` được filter thêm.
6. Gọi một HTTP route không đi qua API module được instrument và kiểm tra nhãn này không bị áp đặt lên HTTP observation chỉ vì lọc toàn cục.
7. Nếu kiểm tra trace backend, xem có bridge/exporter và sampling phù hợp không.

Đây là phép kiểm tra **phạm vi áp dụng filter** chứ không chỉ kiểm tra bean được Spring đăng ký.

### 10.4. Mức 4: kiểm tra metrics/traces qua hạ tầng

Đối với Spring Boot Actuator, có thể bật endpoint metrics ở môi trường được cấp quyền:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Sau đó xem danh sách metric:

~~~bash
curl --fail-with-body --silent --show-error \
  http://localhost:8080/actuator/metrics
~~~

Để xem trace, cần Micrometer tracing bridge và exporter tới Zipkin/Tempo/Jaeger hoặc backend tương ứng. **Actuator metrics không phải API trả toàn bộ spans của Spring Modulith**. Tên meter/span và việc low-cardinality key trở thành metric label cần được kiểm chứng ở registry/backend đang dùng.

### 10.5. Những tiêu chí kiểm tra hữu ích

| Tiêu chí | Kỳ vọng |
| --- | --- |
| Filter được Spring đăng ký | Có bean `ObservationFilter` và registry áp dụng. |
| Đúng context type | `ModulithContext` được chỉnh, HTTP/DB context khác không bị chạm vào. |
| Không làm mất key framework | `module.identifier`, `module.name` vẫn giữ ý nghĩa. |
| Tag có cardinality hữu hạn | `architecture.component` chỉ một vài giá trị; `shop.outcome` thuộc enum. |
| Tính đúng theo lifecycle | Outcome lấy từ dữ liệu có khi observation dừng. |
| Output hữu ích | Meter/trace có metadata kỳ vọng **nếu handler/exporter hỗ trợ**. |
| Không làm lệch nghiệp vụ | Filter không được dùng để quyết định thanh toán, đặt hàng hoặc tồn kho. |

## 11. Các lỗi thường gặp

### 11.1. Filter không bao giờ chạy

**Triệu chứng:** thêm bean nhưng không thấy callback `map(...)` được gọi.

**Kiểm tra:** bean có trong Spring context không; observation có được tạo với registry phù hợp không; observation có thực sự `stop()` không; instrumentation có dùng registry khác không; observation có phải no-op hoặc bị predicate loại trừ không.

Đừng sửa bằng cách khai báo thêm một filter giống hệt ở nhiều cấu hình. Hãy truy nguyên **registry và lifecycle**.

### 11.2. Filter chạy, nhưng backend không có nhãn mới

Có thể filter đã thay context khi stop nhưng handler/backend dùng metadata khác hoặc đã quyết định một phần dữ liệu ở start. Cũng có thể export pipeline chưa cấu hình, mất dữ liệu do sampling hoặc thay đổi tên tag khi chuyển định dạng.

**Cách điều tra:** kiểm tra context ngay sau stop; tiếp theo kiểm tra Micrometer registry/handler, cuối cùng là exporter và dashboard. **Không giả định một key trong context chắc chắn hiện thành một metric label trên mọi backend.**

### 11.3. Mọi metric và trace đều có cùng tên

Nguyên nhân thường là filter gọi `context.setName(...)` cho mọi context. Đây là thay đổi global, có thể phá việc phân loại HTTP/database/module observations. Chỉ đổi tên khi đã xác định đúng context và có yêu cầu quản lý hợp đồng telemetry.

### 11.4. Metric tăng cardinality đột ngột

Nguyên nhân phổ biến là lấy `orderId`, `userId`, raw URL hoặc exception message làm **low-cardinality key-value**.

**Cách sửa:** chuẩn hóa thành tập trạng thái hữu hạn, ví dụ `SUCCESS/REJECTED/FAILED/OTHER`. Không dùng high-cardinality như phương án tự động an toàn cho dữ liệu nhạy cảm; xử lý chính sách dữ liệu tại nguồn.

### 11.5. Filter cố xóa thông tin nhạy cảm nhưng trace cũ vẫn có

Filter chạy trước `onStop`, nhưng không thể thu hồi telemetry đã ghi trước đó. Cần sửa nơi tạo/đưa dữ liệu vào observation, cấu hình handler/exporter bảo vệ thông tin, và thực hiện quy trình xử lý dữ liệu đã lưu theo chính sách của tổ chức.

### 11.6. Tracing bị đứt ở listener bất đồng bộ

Filter thêm metadata không đồng nghĩa trace context được chuyển qua thread. Kiểm tra executor, context propagation setup, message instrumentation và sampling. Không sửa bằng cách thêm `traceId` làm low-cardinality tag, vì traceId là giá trị gần như duy nhất và không phải cách propagation hoạt động.

### 11.7. Hai filter ghi đè cùng một tag

Nếu nhiều filter hoặc convention cùng thêm `shop.outcome` với các ý nghĩa khác nhau, số liệu có thể thiếu nhất quán. Đặt một **nguồn sở hữu nhãn**, phân chia trách nhiệm và viết integration test với tất cả thành phần đã đăng ký. Tránh phụ thuộc vào thứ tự không được tài liệu hóa.

## 12. Tình huống thực tế: nhận diện Module Entry trong tracing dashboard

**Mục tiêu:** nhóm vận hành muốn phân biệt spans ở ranh giới module với HTTP spans để kiểm tra kiến trúc khi chạy.

**Giải pháp phù hợp:**

- Spring Modulith instrument API modules.
- Filter kiểm tra `context instanceof ModulithContext` rồi thêm `architecture.component=application-module`.
- Tracing pipeline giữ lại thuộc tính tương ứng nếu handler/exporter hỗ trợ.
- Dashboard lọc module entry spans bằng nhãn mới và nhóm theo `module.identifier` hoặc `module.invocation-type`.

**Bằng chứng cần xem:**

- Luồng `orders → inventory` có module span với `module.identifier=inventory`.
- Span được phân loại bằng `architecture.component=application-module`.
- Các span HTTP/DB không tự mang nhãn đó chỉ vì filter.
- Khi `orders` phát event khiến listener `payments` được gọi, module span có thể có `module.invocation-type` tương ứng.
- Nếu listener bất đồng bộ không cùng trace, kiểm tra propagation; đừng tự gán lại trace ID.

**Giới hạn:** trace và nhãn module giúp tìm tương tác runtime, không chứng minh mọi module dependency đều hợp lệ hoặc một nghiệp vụ đã commit. Kiểm tra cấu trúc bằng Spring Modulith module verification/module graph; kiểm tra nghiệp vụ bằng state machine, transaction, test và đối soát.

## 13. Checklist trước khi dùng ObservationFilter trong production

- [ ] Xác định rõ observation nào cần thay đổi: module entry, HTTP, custom observation hay tất cả?
- [ ] Chọn `ObservationFilter` vì cần post-processing ở giai đoạn stop, không chỉ vì muốn đổi tên thông thường?
- [ ] Đã giới hạn bằng context type hoặc tên observation do ứng dụng sở hữu?
- [ ] Có hạ tầng Micrometer Observation/ObservationRegistry và filter bean đã đăng ký?
- [ ] Nếu dùng `ModulithContext` trong code, có artifact API ở compile scope và runtime instrumentation phù hợp?
- [ ] Không ghi đè những key quan trọng như `module.identifier` hoặc tên metric của framework ngoài ý muốn?
- [ ] Low-cardinality keys có whitelist và số lượng giá trị giới hạn?
- [ ] Không đưa dữ liệu người dùng, ID duy nhất hoặc bí mật vào telemetry?
- [ ] Đã hiểu filter chạy ở stop và không sửa được quyết định handler trước đó?
- [ ] Đã xác minh context sau stop trong test?
- [ ] Đã xác minh handler/exporter/backend nhận được metadata như kỳ vọng?
- [ ] Đã kiểm tra trường hợp observation lỗi, no-op, không dừng hoặc bị predicate loại trừ?
- [ ] Đã tách biệt context propagation qua async thread/message?
- [ ] Dashboard/alert được kiểm tra sau khi thay đổi tên hoặc tag?
- [ ] Đã có người sở hữu và tài liệu hóa ý nghĩa từng key mới?

## 14. Bài tập tự luyện

1. **Vòng đời:** `ObservationFilter.map(...)` chạy trước hay sau `ObservationHandler.onStart(...)`? Vì sao điều này làm giới hạn khả năng đổi tên span đã được tạo?
2. **Viết filter:** Tạo một bean chỉ thêm `architecture.domain=commerce` cho `ModulithContext`, để nguyên context HTTP.
3. **Cardinality:** Một kỹ sư thêm `orderId` vào low-cardinality key trong filter. Hãy giải thích tác động tới số time series và đề xuất một nhãn thay thế.
4. **Kết quả muộn:** Thiết kế một custom observation `shop.refund`, đặt kết quả `SUCCESS/FAILED` vào context và dùng filter để tạo `refund.outcome` ở stop.
5. **Bảo mật:** Vì sao xóa `customer.email` khỏi high-cardinality keys ở stop không đảm bảo toàn bộ telemetry chưa từng chứa email?
6. **So sánh API:** Với yêu cầu đổi tên và bộ key mặc định của module entry spans, vì sao `ModulithObservationConvention` có thể phù hợp hơn filter?
7. **Phân tán:** Listener chạy qua `@Async` làm trace bị tách. Dùng `ObservationFilter` có đủ giải quyết không? Hãy nêu công cụ cần kiểm tra.
8. **Kiểm thử:** Filter được gọi nhưng dashboard không có nhãn mới. Hãy lần theo thứ tự context → handler → registry → exporter → backend.
9. **Nhập vai reviewer:** Một pull request thêm filter global đổi `context.setName("operation")` cho mọi observation. Bạn sẽ yêu cầu sửa gì?
10. **Kiến trúc:** Module entry span có đủ tag nhưng một đơn vẫn bị tính tiền hai lần. Bạn sẽ tìm bằng chứng nghiệp vụ ở đâu?

## 15. Tổng kết

`ObservationFilter` là extension point của Micrometer dùng để **biến đổi `Observation.Context` ở giai đoạn dừng observation**, trước các `ObservationHandler.onStop(...)`. Trong ứng dụng Spring Boot sử dụng Spring Modulith, filter đặc biệt hữu ích khi cần bổ sung metadata có điều kiện cho **Module Entry Spans** hoặc chuyển một trạng thái chỉ được biết ở cuối công việc thành nhãn có ý nghĩa rõ ràng.

Lựa chọn đúng extension point giúp giữ hệ thống quan sát dễ hiểu:

- **`ModulithObservationConvention`:** định nghĩa tên và key-values của loại module observation.
- **`ObservationFilter`:** post-process context ở stop.
- **`ObservationPredicate`:** chọn có tạo observation hay không.
- **`ObservationHandler`:** xử lý lifecycle thành metrics/traces/logs.
- **Context propagation:** chuyển thông tin trace qua ranh giới thread/process, một vấn đề riêng.

Hãy kiểm soát cardinality, tránh sửa các key framework định nghĩa và kiểm chứng kết quả trên cả context lẫn backend. Module graph, Actuator, event metrics và tracing phối hợp giúp kiểm chứng kiến trúc mô-đun khi vận hành; còn tính đúng đắn nghiệp vụ cần kiểm thử, ràng buộc lưu trữ, idempotency và đối soát.

### Tài liệu tham khảo

1. [Micrometer — Observation Components: Context, Filter, Predicate và lifecycle](https://docs.micrometer.io/micrometer/reference/observation/components.html).
2. [Micrometer — Observation Introduction: các building blocks](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
3. [Spring Boot — Observability: đăng ký ObservationFilter bean, common key-values và context propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
4. [Spring Framework — Observability Support: ObservationFilter và các context chuyên biệt](https://docs.spring.io/spring-framework/reference/integration/observability.html).
5. [Spring Modulith — Production-ready Features: quan sát application modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
6. [Spring Modulith Javadoc — ModulithContext](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html).
7. [Spring Modulith Javadoc — ModuleIdentifierPassingObservationFilter và các class hỗ trợ](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/support/package-summary.html).
