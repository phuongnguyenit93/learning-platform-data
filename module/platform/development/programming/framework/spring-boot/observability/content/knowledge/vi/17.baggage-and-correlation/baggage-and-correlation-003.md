# Remote baggage fields: truyền metadata có kiểm soát giữa các dịch vụ

> **Chương:** Baggage và correlation  
> **Bài:** Remote baggage fields  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Bài toán: dịch vụ phía sau cần biết một phần ngữ cảnh của request

Một request đi qua nhiều dịch vụ: api-gateway gọi order-service, rồi order-service gọi inventory-service. Mỗi dịch vụ có log và trace riêng, nhưng nhóm vận hành cần một vài thông tin xuyên suốt để điều tra, chẳng hạn mã khu vực vận hành, phiên bản luồng xử lý hoặc một mã correlation do hệ thống tạo ra.

Có thể truyền những thông tin ấy bằng cách đặt vào **baggage** trong tracing context. Baggage là tập cặp key–value có thể được inject vào header khi request đi qua ranh giới tiến trình, rồi được extract ở dịch vụ nhận nếu cả hai phía hỗ trợ cùng cơ chế propagation.

Trong Micrometer Tracing, **remote baggage fields** là những trường baggage được cấu hình để có thể truyền qua các dịch vụ. Chúng khác với dữ liệu chỉ tồn tại trong span hiện tại hoặc thông tin chỉ dùng để đưa vào MDC/log của một tiến trình.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as api-gateway
    participant Order as order-service
    participant Inventory as inventory-service
    Client->>Gateway: HTTP request
    Note over Gateway: Tạo trace context và baggage region
    Gateway->>Order: trace headers + baggage
    Note over Order: Extract context và đọc region
    Order->>Inventory: trace headers + baggage
    Note over Inventory: Extract field nếu được phép
    Inventory-->>Order: response
    Order-->>Gateway: response
    Gateway-->>Client: response
~~~

Remote baggage có thể hữu ích cho correlation theo mã kỹ thuật, truyền thuộc tính định tuyến/phân vùng đã được cho phép, giữ ngữ cảnh hỗ trợ điều tra xuyên nhiều service hoặc truyền thông tin thí nghiệm/phiên bản luồng xử lý.

Baggage không phải nơi gửi toàn bộ request, thông tin người dùng hay payload nghiệp vụ. Mỗi field được truyền thêm làm tăng header size, phạm vi chia sẻ dữ liệu và trách nhiệm bảo mật.

## 2. Phân biệt remote baggage, span attributes, trace context và MDC

Các loại metadata sau có thể cùng xuất hiện trong một trace nhưng mang semantics khác nhau:

| Cơ chế | Phạm vi | Được truyền sang service khác? | Ví dụ |
| --- | --- | --- | --- |
| **Trace context** | Định danh trace/span và quan hệ cha–con | Có, qua propagator | traceparent, B3 headers |
| **Baggage** | Key–value bổ sung gắn với tracing context | Có, nếu field được cấu hình remote và propagator hỗ trợ | region=ap-south |
| **Span attribute** | Metadata mô tả một span cụ thể | Không tự động | inventory.warehouse=wh-2 |
| **MDC/log correlation** | Context phục vụ log trong tiến trình | Không tự động | traceId, spanId, tenant_region |
| **Observation low-cardinality key-value** | Metadata phù hợp phân nhóm metrics | Không tự động | channel=web |
| **Observation high-cardinality key-value** | Metadata phân biệt từng lần thực thi, thường phù hợp span | Không tự động | order.attempt_id |

**Remote baggage không đồng nghĩa với span attribute.** Gắn một attribute lên span không tự động tạo header để downstream nhận. Ngược lại, baggage được truyền có thể được tích hợp vào span hoặc MDC tùy bridge/cấu hình, nhưng không nên giả định mapping đó luôn xảy ra.

Trace context tiêu chuẩn mang các trường định danh như trace ID, parent/span ID và sampling flags. Baggage là phần metadata bổ sung. Nếu chỉ cần nối các span trong một trace, trace context là đủ; không cần tạo baggage chứa trace ID lần nữa.

## 3. Remote field có nghĩa là gì?

Trong một ứng dụng, baggage có thể được tạo và đọc trong phạm vi hiện tại. Để một field đi qua mạng, trường đó cần được đánh dấu là **remote field** trong cấu hình hoặc được quản lý bằng cơ chế propagation tương ứng.

Có ba khía cạnh cần tách biệt:

1. **Được phép propagate:** field nằm trong cấu hình remote baggage hoặc allowlist tương đương.
2. **Được inject/extract:** client propagator ghi field vào request headers và server propagator đọc field từ headers.
3. **Được sử dụng:** code downstream lấy giá trị và áp dụng vào nghiệp vụ/observability theo chính sách của service.

Một field có thể tồn tại trong process A nhưng không xuất hiện trong process B nếu cấu hình remote thiếu, propagation format không tương thích, header bị proxy loại bỏ hoặc request đi qua client không được instrument.

~~~mermaid
flowchart LR
    A["Tạo baggage field ở process A"] --> B{"Remote field được cho phép?"}
    B -->|Không| C["Chỉ tồn tại cục bộ"]
    B -->|Có| D["Propagator inject vào request"]
    D --> E["HTTP / messaging transport"]
    E --> F{"Downstream extract?"}
    F -->|Không| G["Không có baggage ở process B"]
    F -->|Có| H["Baggage field ở process B"]
    H --> I["Code / tracing / logging sử dụng"]
~~~

Cấu hình remote không có nghĩa mọi HTTP request ngoài hệ thống sẽ tự động chứa field đó. Chỉ các request chạy qua integration/propagator phù hợp mới inject header. Cũng cần kiểm tra gateway, load balancer, service mesh hoặc proxy ở giữa.

## 4. Spring Boot cấu hình remote baggage fields

Với Spring Boot 3.x và Micrometer Tracing, cấu hình có thể khai báo danh sách field được truyền giữa các dịch vụ:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
        - workflow-version
        - correlation-key
~~~

Nếu cần đưa một số field vào logging correlation trong tiến trình hiện tại, Spring Boot có cấu hình riêng:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
        - workflow-version
      correlation:
        fields:
          - region
          - workflow-version
~~~

Hai cấu hình có trách nhiệm khác nhau:

- `remote-fields`: cho biết những field nào có thể được propagate từ dịch vụ này sang dịch vụ khác.
- `correlation.fields`: yêu cầu tracing integration đưa các field được chọn vào logging correlation/MDC theo khả năng bridge.

Một field có thể được propagate nhưng không được đưa vào MDC; hoặc chỉ dùng cho correlation cục bộ mà không cần gửi đi. Chỉ thêm `correlation.fields` không tự động làm field trở thành remote baggage.

**Phạm vi phiên bản:** ví dụ nhắm Spring Boot 3.x với Micrometer Tracing được auto-configure. Hãy kiểm tra metadata cấu hình của phiên bản ứng dụng đang chạy nếu property namespace thay đổi. Không suy ra rằng Brave và OpenTelemetry có mọi chi tiết implementation giống hệt nhau.

## 5. Dependency và tracing integration

Baggage không tự hoạt động chỉ vì thêm YAML. Ứng dụng phải có tracing implementation/bridge, propagator phù hợp và HTTP client/server instrumentation để inject/extract context.

Ví dụ Maven cho ứng dụng Spring Boot 3.x dùng Brave:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-brave</artifactId>
    </dependency>
    <dependency>
        <groupId>io.zipkin.reporter2</groupId>
        <artifactId>zipkin-reporter-brave</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Đây là bộ dependency minh họa cho tracing/Zipkin. Nếu dùng OpenTelemetry bridge và exporter, dependency sẽ khác; không ghép nhiều bridge implementation một cách tùy tiện.

Đối với HTTP, hãy sử dụng client/builder mà Spring Boot có thể instrument. Nếu tạo client thô hoặc tự dựng request headers, không mặc định trace context và baggage tự động được inject. Ở phía server, framework cần được cấu hình để extract context và thiết lập span server từ incoming request.

## 6. Định dạng propagation: W3C Baggage và B3

Các định dạng truyền trace context và baggage có thể khác nhau.

### 6.1. W3C Trace Context và W3C Baggage

W3C Trace Context định nghĩa header như:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

W3C Baggage dùng header `baggage` để truyền các member key–value, ví dụ:

~~~http
baggage: region=ap-south,workflow-version=v2
~~~

Header trên là ví dụ rút gọn, không chứa mọi trường hợp escaping/metadata. Không tự concatenate chuỗi tùy ý để tạo header khi có propagator/API chuyên dụng.

### 6.2. B3 propagation

B3 thường dùng header như `b3` hoặc các header multi-field `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled`. B3 chủ yếu mô tả trace context. Cách truyền baggage với Brave phụ thuộc cấu hình baggage fields và propagation integration; đừng nhầm B3 trace headers với W3C baggage header.

### 6.3. Hai hệ thống phải hiểu cùng giao thức

Nếu upstream gửi W3C baggage còn downstream chỉ extract B3 trace context và không đọc W3C baggage, trace có thể nối được nhưng baggage không có ở downstream.

Ngược lại, cùng một tên field trong code chưa bảo đảm wire representation giống nhau. Kiểm tra:

- Propagator nào inject ở phía gửi.
- Propagator nào extract ở phía nhận.
- Proxy/gateway có cho phép các header đó đi qua không.
- Field có được allowlist ở cả hai phía hay không.
- Field có bị đổi tên, encode, truncate hoặc drop không.

Khi tích hợp hệ thống đa ngôn ngữ, ưu tiên chuẩn propagation đã thống nhất, ví dụ W3C Trace Context/Baggage, thay vì dựa vào hành vi riêng của một implementation.

## 7. Tạo remote baggage bằng Micrometer Tracing BaggageManager

Ứng dụng có thể thao tác baggage qua API `BaggageManager` của Micrometer Tracing. Ví dụ service nhận giá trị khu vực đã được xác thực từ tầng nghiệp vụ rồi tạo baggage trong scope hiện tại:

~~~java
package example.orders;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.BaggageManager;
import org.springframework.stereotype.Service;

@Service
public class OrderRoutingService {
    private final BaggageManager baggageManager;

    public OrderRoutingService(BaggageManager baggageManager) {
        this.baggageManager = baggageManager;
    }

    public String route(String validatedRegion) {
        String region = normalizeRegion(validatedRegion);

        try (BaggageInScope ignored =
                     baggageManager.createBaggageInScope("region", region)) {
            return callInventory();
        }
    }

    private String callInventory() {
        // Gọi HTTP client đã được Spring instrument.
        return "inventory-accepted";
    }

    private static String normalizeRegion(String value) {
        if ("ap-south".equals(value)) return "ap-south";
        if ("eu-west".equals(value)) return "eu-west";
        return "default";
    }
}
~~~

Trong ví dụ:

- `BaggageManager` được inject; không tự tạo manager hoặc tracer riêng trong service.
- `createBaggageInScope(...)` đặt field vào baggage hiện hành trong phạm vi scope.
- `try-with-resources` đóng scope, khôi phục context trước đó khi method thoát.
- Giá trị được chuẩn hóa thành tập hữu hạn để giảm biến thiên và ngăn người gọi đưa chuỗi tùy ý vào headers.
- `callInventory()` cần HTTP client được instrument để propagator inject trace context và remote baggage.

API cụ thể và việc field có thực sự được gửi phụ thuộc cấu hình bridge, remote-field allowlist và context đang hoạt động. Nếu không có span/trace context hiện tại, việc tạo baggage trong scope không bảo đảm tạo trace mới hoặc gửi dữ liệu sang process khác.

Không giữ `BaggageInScope` trong field singleton hoặc đóng scope trên một thread khác. Baggage scope gắn với context thực thi; với async, phải dùng cơ chế context propagation phù hợp.

## 8. Đọc remote baggage ở service nhận

Nếu downstream đã extract baggage và dùng tracing integration phù hợp, code có thể đọc giá trị thông qua `BaggageManager`:

~~~java
package example.inventory;

import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.BaggageManager;
import org.springframework.stereotype.Service;

@Service
public class InventoryPolicyService {
    private final BaggageManager baggageManager;

    public InventoryPolicyService(BaggageManager baggageManager) {
        this.baggageManager = baggageManager;
    }

    public String selectPolicy() {
        Baggage baggage = baggageManager.getBaggage("region");

        if (baggage == null) {
            return "default-policy";
        }

        String region = baggage.get();
        if ("ap-south".equals(region)) {
            return "south-policy";
        }
        if ("eu-west".equals(region)) {
            return "west-policy";
        }
        return "default-policy";
    }
}
~~~

Đoạn code giả định field `region` đã được cấu hình, extract và có trong baggage context hiện hành. Khi không có baggage, code có fallback rõ ràng.

**Không dùng baggage làm nguồn xác thực hoặc nguồn quyết định quyền hạn.** Header từ request có thể do client bên ngoài gửi hoặc bị thay đổi trên đường truyền. Nếu `region` ảnh hưởng đến quyền truy cập hoặc tenancy, server phải xác thực nó từ nguồn tin cậy và chỉ sau đó mới dùng giá trị đã xác nhận cho quyết định quan trọng.

Với dữ liệu đầu vào không tin cậy, không lấy nguyên giá trị baggage để ghép SQL, tạo đường dẫn file, chọn endpoint tùy ý hoặc thay đổi quyền người dùng.

## 9. Remote baggage và propagation xuyên nhiều hop

Một field được truyền từ A sang B có thể tiếp tục được truyền từ B sang C nếu B giữ context hiện hành và outgoing propagator được cấu hình field tương ứng. Điều này không có nghĩa mọi service tự động nhận mọi field.

~~~mermaid
flowchart TD
    A["api-gateway: region=ap-south"] -->|"inject"| B["order-service: extract region"]
    B --> C{"B có cho phép propagate tiếp?"}
    C -->|Có| D["Outgoing request inject field"]
    D --> E["inventory-service: extract field"]
    C -->|Không| F["Field dừng tại order-service"]
~~~

Một chuỗi propagation có thể bị đứt bởi:

- Một service không khai báo remote field.
- Client không được instrument hoặc không dùng propagator.
- Gateway chỉ forward một danh sách header được phép và loại bỏ baggage.
- Một giao thức messaging cần carrier/injector/extractor riêng.
- Context bị mất khi chuyển thread hoặc chạy async.
- Giá trị vượt giới hạn header của proxy/server.
- Một service chủ động loại bỏ field vì không cần hoặc không được phép chia sẻ tiếp.

Hãy lập danh sách service nào được phép **nhận**, service nào được phép **forward**, và service nào **phải loại bỏ** field. Không để baggage lan truyền vô hạn đến hệ thống không liên quan.

## 10. Baggage với logging correlation/MDC

Một nhu cầu phổ biến là thấy một số field trên log của nhiều service. Spring Boot có thể cấu hình baggage correlation fields để tích hợp với logging context khi bridge hỗ trợ.

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - region
        - workflow-version
      correlation:
        fields:
          - region
          - workflow-version
~~~

Khi tracing integration cập nhật MDC theo cấu hình, log pattern có thể hiển thị các field:

~~~text
INFO  [order-service, traceId=..., spanId=..., region=ap-south] Starting checkout
INFO  [inventory-service, traceId=..., spanId=..., region=ap-south] Reserving stock
~~~

Đây là định dạng log minh họa; key MDC thực tế và pattern phụ thuộc logging stack/bridge. Không mặc định chỉ thêm YAML là mọi logger tùy chỉnh hoặc executor đều tự giữ MDC.

Phân biệt:

- `traceId`/`spanId` thường được tracing integration đưa vào correlation context.
- `region`/`workflow-version` là baggage correlation fields nếu được cấu hình.
- Các trường MDC chỉ phục vụ log trong process; để truyền sang process khác vẫn cần remote propagation.
- Khi thread thay đổi, MDC có thể không được sao chép nếu không có cơ chế context propagation phù hợp.

MDC không phải nguồn sự thật nghiệp vụ. Nếu một field ảnh hưởng đến xử lý, code phải dùng dữ liệu đã được xác minh trong context nghiệp vụ, không đọc lại từ chuỗi log-format.

## 11. Bảo mật: chỉ propagate những field thật sự cần

Remote baggage có thể đi qua nhiều service, proxy và hệ thống bên ngoài. Một field được gửi đi có thể xuất hiện trong request headers, logs, span attributes, collector payload và tracing backend. Vì vậy hãy thiết kế nó như một **giao diện chia sẻ dữ liệu**.

### 11.1. Không gửi dữ liệu nhạy cảm

Không đưa vào baggage:

- Password, API key, bearer token, cookie phiên hoặc credential.
- Số thẻ, dữ liệu thanh toán nhạy cảm hoặc thông tin xác thực.
- Email, số điện thoại, địa chỉ hoặc thông tin nhận dạng cá nhân nếu không có mục đích và chính sách cho phép.
- Nội dung request/response hoặc chuỗi exception tự do.
- Dữ liệu bí mật nội bộ chỉ có một service được phép biết.

Baggage header thường đi qua nhiều thành phần hơn một span attribute nội bộ. Phạm vi rủi ro có thể lớn hơn dự kiến nếu dùng tùy tiện.

### 11.2. Allowlist và chuẩn hóa value

Chỉ khai báo remote fields theo allowlist rõ ràng. Với mỗi field, định nghĩa:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Tên | Có ổn định và không chứa dữ liệu riêng không? |
| Mục đích | Service nhận dùng nó để làm gì? |
| Giá trị hợp lệ | Tập enum/hạn chế nào được chấp nhận? |
| Độ dài tối đa | Giới hạn byte/character là bao nhiêu? |
| Propagation scope | Qua những service nào được phép truyền? |
| Retention | Log/trace backend lưu trong bao lâu? |
| Owner | Nhóm nào chịu trách nhiệm versioning và loại bỏ? |

Chuẩn hóa value trước khi đưa vào baggage. Với region, chỉ cho phép các giá trị cố định như `ap-south`, `eu-west` và `default`; không nhận nguyên chuỗi tùy ý từ URL hay header bên ngoài.

### 11.3. Không đặt high-cardinality vào metrics

Baggage là metadata cho context propagation; không vì vậy mà phù hợp làm metric tag. Một correlation key khác nhau theo từng request sẽ tạo cardinality cao nếu custom handler/meter đưa nó thành label.

Dùng metrics với low-cardinality dimensions như region/outcome/service; baggage/span attribute/log correlation cho một số ID kỹ thuật được phê duyệt; hệ thống audit/business store cho dữ liệu sự kiện cần lưu bền vững.

## 12. Kích thước header, giới hạn và hiệu năng

Mỗi baggage field thêm bytes vào header trên các request được propagate. Nếu có nhiều key dài hoặc value chứa payload, request có thể vượt giới hạn header của client, proxy, gateway hoặc server.

Hậu quả có thể gồm:

- HTTP 400/431 hoặc lỗi request header quá lớn.
- Proxy loại bỏ header hoặc chỉ forward một phần.
- Tăng chi phí serialize/parse ở mỗi hop.
- Tăng dữ liệu trong logs/traces.
- Làm lỗi tương thích với service ngoài không hiểu baggage.

Không có một giới hạn header duy nhất áp dụng cho mọi sản phẩm. Mỗi HTTP client, reverse proxy, server và mesh có giới hạn cấu hình riêng. Đo kích thước request thực tế trên toàn tuyến và giữ baggage nhỏ, ổn định.

### 12.1. Không truyền baggage bằng chuỗi tùy ý

Đừng tự tạo header bằng cách nối chuỗi:

~~~java
// Không nên: tự dựng header tracing bằng cách nối chuỗi.
request.header("baggage", "region=" + region + ",user=" + userInput);
~~~

Sử dụng tracing propagator/BaggageManager của stack phù hợp. Propagator xử lý việc inject/extract theo format; ứng dụng chịu trách nhiệm allowlist và kiểm tra dữ liệu.

### 12.2. Baggage không phải kho dữ liệu lớn

Không gửi danh sách ID, JSON payload hay thông tin cấu hình đầy đủ trong baggage. Nếu downstream cần một bản ghi nghiệp vụ, gửi qua body/request contract hoặc truy vấn hệ thống lưu trữ phù hợp; baggage chỉ nên chứa metadata nhỏ dùng xuyên request.

## 13. Baggage trong HTTP client, messaging và async

### 13.1. HTTP

Với HTTP, tracing instrumentation thường inject trace context và baggage vào outbound carrier. Ở server nhận, instrumentation extract trước khi thiết lập span server. Dùng HTTP client builder do framework quản lý để giữ đúng instrumentation.

Khi gọi một dịch vụ không thuộc hệ thống hoặc đối tác bên ngoài, rà soát headers gửi ra. Không mặc định mọi baggage fields nội bộ đều được phép chuyển cho bên thứ ba. Có thể cần outbound policy loại bỏ baggage nhạy cảm hoặc chỉ forward field cụ thể.

### 13.2. Messaging

Với queue/message broker, propagation đi qua message headers/properties theo carrier và integration của messaging framework. Không áp dụng giả định HTTP baggage header một cách máy móc cho Kafka/RabbitMQ/JMS. Producer phải inject; consumer phải extract; message có thể được xử lý sau nhiều phút hoặc bởi một tiến trình khác.

Nếu message được lưu lâu, cần xem retention và việc baggage cũ còn hợp lệ ở thời điểm consumer xử lý hay không.

### 13.3. Async executor và Reactor

Context của thread hiện tại không tự động trở thành context của mọi thread mới. Một tác vụ được gửi vào executor có thể mất trace/baggage nếu context không được capture và restore.

- Dùng cơ chế context propagation được hỗ trợ bởi Spring/Micrometer cho executor hoặc reactive chain.
- Không giữ `BaggageInScope` rồi đóng nó ở một thread khác.
- Trong Reactor, dùng context-aware instrumentation phù hợp, không dựa vào ThreadLocal thuần túy.
- Kiểm tra trace ID và baggage field tại điểm nhận callback thực tế.

Khi context bị mất, hệ thống có thể tạo trace mới hoặc span root rời rạc, khiến correlation xuyên service không còn đúng.

## 14. Kiểm thử remote baggage end-to-end

Một unit test của BaggageManager chỉ cho biết code tạo/đọc field. Để chứng minh remote propagation, cần kiểm thử **hai process hoặc hai HTTP boundaries**.

### 14.1. Kịch bản kiểm thử

Giả sử:

- gateway-service nhận request và đặt region=ap-south trong baggage scope.
- order-service nhận request và đọc region.
- Hai service dùng tracing bridge/propagator tương thích.
- region được khai báo là remote field theo cấu hình phù hợp.

~~~mermaid
sequenceDiagram
    participant Test
    participant Gateway as gateway-service
    participant Order as order-service
    Test->>Gateway: GET /checkout
    Gateway->>Gateway: Set baggage region=ap-south
    Gateway->>Order: HTTP request + baggage
    Order->>Order: Extract region
    Order-->>Gateway: region observed
    Gateway-->>Test: Response
~~~

### 14.2. Checklist kiểm chứng

1. Tạo request test với một giá trị allowlist đã biết.
2. Ở gateway, xác nhận baggage có trong context trước khi gọi HTTP client.
3. Kiểm tra outbound request có header propagation tương ứng trong môi trường test, che thông tin nhạy cảm.
4. Ở order-service, đọc baggage qua API tracing trong context request.
5. Xác nhận giá trị đúng và không lấy từ một header tùy ý chưa xác thực.
6. Thử bỏ field khỏi remote-fields hoặc dùng propagation format không tương thích trong môi trường test; field cần ngừng xuất hiện ở downstream.
7. Thử một giá trị không hợp lệ; service phải fallback hoặc từ chối theo policy.
8. Kiểm tra log correlation nếu đã cấu hình; so sánh với trace ID/span ID.
9. Kiểm tra metrics không có label chứa correlation ID hoặc value thay đổi theo từng request.

### 14.3. Phân biệt lỗi baggage với lỗi trace propagation

Nếu downstream có cùng traceId nhưng không có region, trace context đã được propagate nhưng baggage có thể chưa được cấu hình/forward/extract.

Nếu downstream có một trace ID khác, vấn đề có thể nằm ở trace context propagation, sampling flags, client instrumentation hoặc proxy headers. Đừng chẩn đoán mọi trường hợp như nhau.

Nếu baggage tồn tại trong process nhận nhưng log không hiện field, vấn đề có thể nằm ở correlation/MDC config chứ không phải remote propagation.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Baggage có ở gateway nhưng thiếu ở downstream | Field chưa được khai báo remote, không inject/extract, header bị drop | Kiểm tra remote-fields, propagator và carrier |
| Trace nối được nhưng baggage thiếu | Trace context hoạt động, baggage format/allowlist chưa phù hợp | Kiểm tra W3C Baggage/B3 integration và remote field config |
| Baggage đọc được trong một method nhưng mất trong callback | Context không được truyền qua thread/async boundary | Kiểm tra context propagation của executor/Reactor |
| Field đã propagate nhưng không có trong logs | Chưa khai báo correlation field hoặc MDC integration không hoạt động | Kiểm tra correlation.fields, logging pattern |
| Log hiện field nhưng service khác không nhận | Chỉ có local correlation, không phải remote propagation | Kiểm tra remote fields và outgoing headers |
| Một số service nhận field, một số không | Gateway/proxy allowlist hoặc từng service dùng cấu hình khác | So sánh request headers và cấu hình từng hop |
| Request lỗi header too large | Quá nhiều baggage fields hoặc value quá dài | Đo header size, cắt allowlist và giới hạn value |
| Baggage có giá trị không hợp lệ | Tin cậy trực tiếp dữ liệu client gửi | Validate/normalize tại trust boundary |
| Metrics time series tăng bất thường | Baggage value được custom handler đưa thành metric tag | Loại high-cardinality tag khỏi metrics |
| Field vẫn xuất hiện sau khi bỏ code set | Có upstream inject giá trị hoặc propagation config ở service khác | Xác định nguồn gốc field theo từng hop |
| Service ngoài nhận được baggage nội bộ | Outbound policy forward quá rộng | Chặn hoặc allowlist field tại ranh giới ra ngoài |

### Quy trình điều tra

1. Ghi tên field và giá trị kiểm thử đã được chuẩn hóa.
2. Kiểm tra context tại nơi set.
3. Kiểm tra cấu hình remote field của service gửi.
4. Kiểm tra propagator và header thực tế trước khi rời service.
5. Kiểm tra proxy/gateway có forward header không.
6. Kiểm tra extract và baggage context ở service nhận.
7. Phân biệt vấn đề logging correlation, trace context và baggage.
8. Kiểm tra header size, security policy và cardinality trước khi mở rộng sang các service khác.

Không log toàn bộ baggage headers trên production chỉ để debug. Có thể ghi trạng thái có/không của field hoặc giá trị đã được che/chuẩn hóa theo chính sách.

## 16. Tình huống thực tế: correlation key qua ba dịch vụ

**Bối cảnh.** Một luồng xử lý đơn đi qua gateway-service, order-service và inventory-service. Khi khách hàng báo một lần đặt hàng chậm, người trực vận hành cần tìm log của các service bằng một mã correlation kỹ thuật.

### Bước 1 — tạo correlation key tin cậy

Gateway tạo một ID ngẫu nhiên hoặc nhận một ID từ hệ thống nội bộ đã xác thực. Không mặc định dùng giá trị X-Correlation-ID từ client mà chưa kiểm tra, và không cho phép giá trị chứa dữ liệu cá nhân.

### Bước 2 — đặt vào baggage scope

Gateway tạo baggage field correlation-key trong context của request, với cấu hình remote allowlist phù hợp. Nếu tracing context chưa được thiết lập, cần đảm bảo instrumentation/context lifecycle phù hợp trước khi mong propagation hoạt động.

### Bước 3 — forward qua HTTP client

Gateway gọi order-service bằng client được instrument. Propagator thêm trace context và baggage. Order-service extract field và có thể đưa nó vào logging correlation nếu correlation.fields cho phép.

### Bước 4 — propagate tiếp có chủ đích

Order-service gọi inventory-service. Nếu policy cho phép field đi tiếp, outgoing propagator tiếp tục inject field. Nếu inventory không cần correlation key, service có thể bỏ field ở boundary thay vì lan rộng không cần thiết.

### Bước 5 — điều tra

Người trực dùng metrics để khoanh vùng thời gian/instance; trace ID để xem waterfall; correlation key để tìm các log đã được phép ghi. Baggage không thay thế trace ID và cũng không cần làm metric label.

**Bài học:** một remote baggage field có thể giữ ngữ cảnh qua nhiều process, nhưng chỉ khi mỗi hop có cấu hình, instrumentation và policy phù hợp. Cần quản lý nguồn gốc, phạm vi chia sẻ và độ nhạy cảm của field.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — cấu hình allowlist

Tạo hai Spring Boot service dùng tracing integration tương thích. Khai báo region và workflow-version trong management.tracing.baggage.remote-fields. Khai báo region trong correlation.fields.

- Gọi service A với một luồng đã được instrument.
- Đặt region=ap-south trong baggage scope.
- Gọi service B qua HTTP client đã instrument.
- Kiểm tra B đọc được field trong context và log correlation hiển thị field theo cấu hình.

### Bài tập B — so sánh ba loại metadata

Với cùng một request, ghi:

- Span attribute inventory.warehouse=wh-2.
- Remote baggage region=ap-south.
- Local MDC field debug-mode=true.

Xác minh dữ liệu nào đi sang process khác, dữ liệu nào chỉ nằm trên span, và dữ liệu nào chỉ ảnh hưởng log trong process hiện tại. Giải thích vì sao span attribute không tự inject thành baggage.

### Bài tập C — propagation bị đứt

Trong môi trường test, cấu hình service gửi dùng một propagation format nhưng service nhận không extract format tương ứng. Quan sát trace ID và baggage ở downstream; sau đó đồng bộ propagator và kiểm chứng lại. Nếu trace nối được nhưng baggage mất, xác định cấu hình riêng cần kiểm tra.

### Bài tập D — bảo mật và header size

Thiết kế allowlist tối đa ba field:

- region: một trong ba giá trị cố định.
- workflow-version: version ngắn.
- correlation-key: opaque ID có giới hạn độ dài.

Từ chối hoặc bỏ giá trị dài/không hợp lệ. Xác nhận không có token, email, user ID hay request payload trong headers/logs/metrics. Thử request có baggage dài trong môi trường test để hiểu giới hạn của HTTP stack/proxy.

### Câu hỏi tự kiểm tra

1. Remote baggage field khác span attribute ở chỗ nào?
2. management.tracing.baggage.remote-fields có vai trò gì?
3. correlation.fields có tự động làm field được gửi sang service khác không?
4. Trace context nối được nhưng baggage thiếu cho biết cần kiểm tra phần nào?
5. Vì sao B3 trace headers không đồng nghĩa W3C baggage header?
6. BaggageManager.createBaggageInScope(...) cần lifecycle thế nào?
7. Vì sao không nên đặt token, email hoặc payload vào baggage?
8. Tại sao remote baggage không nên làm metric label?
9. Một field có thể bị mất ở proxy dù cả hai service đã cấu hình remote fields không? Vì sao?
10. Khi async callback chạy thread khác, cần bảo đảm điều gì với tracing context?
11. Tại sao không dùng baggage làm nguồn xác thực/authorization?
12. Làm thế nào phân biệt lỗi propagation với lỗi logging correlation/MDC?

**Tiêu chí hoàn thành:** giải thích được remote baggage, span attributes, trace context và MDC; cấu hình remote fields và correlation fields; tạo/đọc baggage bằng API phù hợp; xác minh propagation qua HTTP hoặc messaging; kiểm soát header size, security, allowlist và cardinality.

## 18. Ghi nhớ

- **Remote baggage fields** là những key–value được phép truyền theo tracing context qua ranh giới dịch vụ; chúng cần cấu hình và propagator hỗ trợ.
- Trong Spring Boot 3.x, `management.tracing.baggage.remote-fields` khai báo field được propagate; `correlation.fields` điều khiển việc đưa field được chọn vào logging correlation theo bridge.
- **Trace context, baggage, span attributes và MDC là các lớp khác nhau.** Một span attribute không tự thành header; log correlation không tự lan sang process khác.
- `BaggageManager` tạo/đọc baggage trong context hiện hành. Dùng scope đúng lifecycle và đảm bảo context propagation khi làm việc async.
- W3C Baggage và B3 trace context không phải cùng một chuẩn. Các service phải tương thích về inject/extract và proxy phải forward header phù hợp.
- Baggage là giao diện chia sẻ dữ liệu: allowlist field, chuẩn hóa value, giới hạn kích thước và không truyền credential hoặc payload nhạy cảm.
- Không dùng baggage high-cardinality làm metric labels; dùng metrics để tổng hợp, traces/logs để điều tra một lần thực thi.
- Kiểm chứng end-to-end trên từng hop. Nếu trace ID nối được nhưng baggage thiếu, kiểm tra riêng baggage configuration/propagator; nếu baggage có nhưng log thiếu, kiểm tra MDC correlation.

## Tài liệu tham khảo

- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Tracing — Baggage](https://docs.micrometer.io/tracing/reference/api.html)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [W3C Baggage](https://www.w3.org/TR/baggage/)
- [OpenTelemetry — Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)

