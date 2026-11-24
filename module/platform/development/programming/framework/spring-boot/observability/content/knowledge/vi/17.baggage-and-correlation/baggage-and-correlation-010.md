# Bảo vệ dữ liệu trong baggage khi triển khai distributed tracing

Trong một hệ thống Spring Boot nhiều service, **baggage** giúp mang một số thông tin ngữ cảnh qua các ranh giới xử lý để downstream có thể đọc. Chẳng hạn, `orders.channel=web` có thể giúp phân biệt luồng web và batch trong logs. Nhưng baggage cũng có thể trở thành một kênh phát tán dữ liệu ngoài ý muốn: một client gửi header tùy ý, service tin giá trị đó, rồi HTTP client tự động truyền tiếp qua nhiều service và cuối cùng metadata xuất hiện trong logs hoặc trace backend.

Vì vậy, câu hỏi không chỉ là “baggage có truyền được không?” mà là **“dữ liệu nào được phép truyền, ai có quyền đặt nó, service nào được đọc và những hệ thống nào có thể lưu nó?”**. Baggage phải được quản lý như dữ liệu đi qua nhiều trust boundary, có chính sách allowlist, kiểm tra nguồn, chuẩn hóa giá trị, giới hạn kích thước và quy tắc sử dụng ở từng đích.

Bài này thuộc chương **Baggage và correlation**, với chủ đề **Bảo vệ dữ liệu trong baggage** của module **SPRING_BOOT_OBSERVABILITY**. Nội dung đặt baggage trong tổng thể observability của Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; chú trọng propagation, span attributes, cardinality, exporter và cách điều tra sự cố mà không làm lộ dữ liệu nhạy cảm.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định rủi ro khi baggage được truyền qua HTTP, messaging, proxy và các service downstream.
2. Phân biệt dữ liệu định danh trace, baggage, span attributes, log fields và metric labels.
3. Thiết kế allowlist theo nguồn dữ liệu, trust boundary, quyền sử dụng và thời gian tồn tại.
4. Kiểm tra, chuẩn hóa, từ chối hoặc loại bỏ baggage không hợp lệ ngay tại ranh giới tin cậy.
5. Giới hạn kích thước baggage và xử lý header theo khả năng của client, proxy, gateway và server.
6. Cấu hình Spring Boot/Micrometer Tracing để chỉ propagate và correlate những field đã được duyệt.
7. Kiểm thử trường hợp giả mạo, PII, secrets, header quá lớn, async context và log leakage.
8. Điều tra sự cố lộ dữ liệu hoặc baggage propagation sai mà vẫn giữ được khả năng liên kết metrics, logs và traces.

## 1. Vì sao baggage là một ranh giới bảo mật?

W3C Baggage định nghĩa header `baggage` để mang các cặp key-value trong quá trình truyền trace context. Ví dụ:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: orders.channel=web,deployment.region=ap-southeast
~~~

Header có thể được inject vào HTTP request bởi instrumentation. Khi service nhận extract context, giá trị có thể trở thành baggage hiện hành và tiếp tục được propagate đến downstream nếu cấu hình cho phép.

Điều này hữu ích cho correlation, nhưng tạo ra một **đường di chuyển dữ liệu**:

~~~mermaid
flowchart LR
    Client["Client / upstream"] --> Gateway["API gateway"]
    Gateway --> A["order-service"]
    A --> B["inventory-service"]
    B --> C["payment-service"]
    A --> Collector["OTel Collector"]
    B --> Collector
    C --> Collector
    Collector --> Backend["Trace backend"]
    A --> Logs["Log backend"]
    B --> Logs
    C --> Logs
~~~

Một baggage field có thể xuất hiện ở nhiều hop, nhiều logs, spans hoặc hệ thống telemetry. Nếu giá trị không được kiểm soát, **mỗi service downstream có thể trở thành một điểm tiếp tục phát tán dữ liệu**.

### 1.1. Các nhóm rủi ro

| Rủi ro | Ví dụ | Hậu quả |
| --- | --- | --- |
| **PII leakage** | Email, số điện thoại, địa chỉ | Dữ liệu cá nhân lan vào logs/traces ở nhiều hệ thống |
| **Secret leakage** | Access token, cookie, API key | Người có quyền đọc telemetry có thể tiếp cận credential |
| **Header injection/spoofing** | Client gửi `tenant.tier=premium` | Downstream tin metadata do bên ngoài kiểm soát |
| **Cross-tenant contamination** | Baggage của request trước còn trong thread context | Dữ liệu tenant này xuất hiện trong xử lý tenant khác |
| **Header amplification** | Mỗi service thêm nhiều key-value | Request vượt giới hạn header hoặc làm tăng network overhead |
| **Cardinality explosion** | Request ID hoặc customer ID thành span/log/metric field | Tăng chi phí indexing và metrics series |
| **Untrusted control data** | Baggage làm thay đổi retry, routing hoặc quyền truy cập | Sai lệch hành vi và có thể tạo lỗ hổng logic |
| **Retention expansion** | Metadata được export sang nhiều backend | Tăng phạm vi lưu giữ, truy cập và xóa dữ liệu |

### 1.2. Baggage không phải kênh bảo mật

Baggage là metadata phục vụ context propagation, **không phải cơ chế authentication hoặc authorization**. Một giá trị `tenant.id` hay `tenant.tier` trong header không chứng minh request thực sự thuộc tenant đó. Tương tự, `user.role=admin` do client gửi không thể được dùng để cấp quyền.

Nếu một quyết định ảnh hưởng tới phân quyền, dữ liệu tài chính, giá, tenant isolation hoặc truy cập tài nguyên, ứng dụng phải lấy thông tin từ nguồn có thẩm quyền (authentication principal, token đã xác minh, database hoặc policy service) và kiểm tra độc lập. Baggage chỉ có thể mang bản sao ngữ cảnh đã được xác minh cho mục đích correlation, không thể trở thành nguồn sự thật.

## 2. Phân loại dữ liệu trước khi đưa vào baggage

Trước khi thêm field, xác định giá trị có thuộc nhóm nào và được phép đi qua những ranh giới nào.

| Loại dữ liệu | Ví dụ | Mặc định |
| --- | --- | --- |
| Context kỹ thuật ít nhạy cảm | `orders.channel=web`, `workflow.name=order-create` | Có thể cho phép nếu downstream cần |
| Deployment metadata | `deployment.region=ap-southeast` | Có thể cho phép, dùng tập giá trị chuẩn hóa |
| Phân nhóm nghiệp vụ | `experiment.variant=control` | Chỉ khi được phê duyệt và không tiết lộ thông tin nhạy cảm |
| Identifier giả danh | Mã correlation nội bộ ngẫu nhiên | Cân nhắc nhu cầu, thời hạn và khả năng liên kết lại |
| PII | Email, điện thoại, tên, địa chỉ | Không truyền mặc định |
| Secret/credential | Password, bearer token, cookie, API key | Không bao giờ đưa vào baggage |
| Payload nghiệp vụ | JSON body, danh sách sản phẩm, payment details | Không dùng baggage |
| Security decision | Role, permission, tenant privilege từ client | Không tin và không dùng làm căn cứ cấp quyền |

### 2.1. Dùng dữ liệu có tập giá trị hữu hạn

Một field `orders.channel` nên có tập giá trị được quy định, ví dụ `web`, `batch` hoặc `partner`. Không lấy chuỗi tùy ý từ HTTP header rồi ghi thẳng vào baggage. Việc chuẩn hóa giúp:

- ngăn giá trị có PII hoặc payload lọt vào context;
- tránh một field phát sinh vô hạn biến thể do khác chữ hoa/thường hoặc khoảng trắng;
- hạn chế kích thước headers;
- tạo cơ sở cho logs và metrics có thể tổng hợp.

### 2.2. Identifier giả danh vẫn có thể là dữ liệu nhạy cảm

Một UUID không chứa tên người dùng vẫn có thể liên kết tới một bản ghi cụ thể trong database hoặc hồ sơ khách hàng. Nếu tổ chức có thể liên kết ngược, giá trị đó vẫn cần được quản lý theo chính sách dữ liệu tương ứng. “Đã hash” hoặc “đã mã hóa” không mặc nhiên biến dữ liệu thành vô danh; giá trị ổn định có thể bị liên kết qua nhiều trace và nhiều hệ thống.

### 2.3. Không đưa request body vào baggage

Baggage phù hợp với một số ít cặp key-value ngắn. Request body có thể chứa thông tin thanh toán, địa chỉ, ghi chú cá nhân hoặc dữ liệu lớn. Đưa body hoặc một JSON tùy ý vào baggage vừa làm phình header, vừa nhân rộng phạm vi lưu trữ. Nếu cần điều tra payload, hãy dùng dữ liệu test giả lập hoặc cơ chế lưu trữ nghiệp vụ được kiểm soát; không biến telemetry thành kho payload.

## 3. Trust boundary và nguồn gốc dữ liệu

Không phải mọi baggage nhận được đều có cùng mức độ tin cậy. Một field được tạo trong service sau khi xác thực có nguồn gốc khác với một field do Internet client gửi trực tiếp.

~~~mermaid
flowchart TD
    External["External client<br/>untrusted headers"] --> Gateway["API Gateway / ingress"]
    Gateway --> Strip["Strip baggage keys<br/>không được phép"]
    Strip --> Authenticate["Authenticate + authorize"]
    Authenticate --> Normalize["Tạo context từ nguồn tin cậy"]
    Normalize --> Order["order-service"]
    Order --> Downstream["Downstream services<br/>chỉ propagate allowlist"]
    Downstream --> Telemetry["Logs / traces / backend"]
~~~

### 3.1. Quy tắc tại ingress

Tại điểm tiếp nhận từ bên ngoài:

1. Xác định baggage fields nào được phép nhận từ đối tác đã thỏa thuận; mặc định không tin các field không khai báo.
2. Loại bỏ hoặc ghi đè các giá trị do client tự gửi nếu chúng trùng với field nội bộ.
3. Authenticate và authorize request như bình thường.
4. Tạo baggage từ dữ liệu đã xác minh và chuẩn hóa; ví dụ lấy channel từ route/API credential hoặc integration configuration.
5. Chỉ propagate field được duyệt sang downstream.

Ví dụ, một client gửi `orders.channel=internal` không có nghĩa request là luồng internal. Ứng dụng nên tự xác định channel theo hợp đồng nguồn gọi.

### 3.2. Phân biệt context bên ngoài và context nội bộ

Trong hệ thống có nhiều đối tác, có thể xác định một số field public được chấp nhận, nhưng phải quy định nguồn nào được đặt field nào, giá trị nào hợp lệ và service nào có thể tin nó. Không có khái niệm “nội bộ nên đáng tin” chỉ vì request đến từ một subnet private; credentials/service identity và trust relationship vẫn phải xác thực.

Một policy nên mô tả ít nhất:

| Thuộc tính policy | Câu hỏi |
| --- | --- |
| Key | Field nào được phép? |
| Owner/source | Ai được tạo hoặc cập nhật? |
| Allowed values | Tập giá trị nào được chấp nhận? |
| Trust level | Dữ liệu đã xác thực hay chỉ do caller gửi? |
| Propagation scope | Qua những service/region nào? |
| Sinks | Có được đưa vào span, logs hoặc metrics không? |
| Retention | Lưu ở backend bao lâu? |
| Removal | Khi sai, hết hạn hoặc có sự cố thì loại bỏ ở đâu? |

### 3.3. Không sử dụng baggage để mang authorization

Không thiết kế:

~~~http
baggage: user.role=admin,tenant.access=all
~~~

để downstream quyết định quyền. Nếu một service muốn tránh xác thực lặp lại, hãy dùng identity propagation và token/delegation mechanism được thiết kế cho security, có chữ ký, audience, expiry và policy phù hợp. Baggage không có các bảo đảm đó.

## 4. Allowlist, validation và normalization

Một chính sách an toàn nên **deny by default**: field không có trong allowlist không được propagate. Không dùng cách “cho phép tất cả trừ một số key xấu” vì danh sách dữ liệu nhạy cảm luôn khó liệt kê hết.

Ví dụ allowlist:

| Key | Allowed values | Nguồn | Được propagate? | Được log? |
| --- | --- | --- | --- | --- |
| `orders.channel` | `web`, `batch`, `partner` | Gateway sau xác thực | Có | Có |
| `deployment.region` | Tập region triển khai | Runtime config | Có | Có |
| `experiment.variant` | `control`, `treatment` | Experiment assignment service | Có, nếu được duyệt | Có điều kiện |
| `customer.email` | Không áp dụng | Không được nhận | Không | Không |
| `authorization` | Không áp dụng | Security layer | Không | Không |
| `request.body` | Không áp dụng | Request payload | Không | Không |

### 4.1. Ví dụ validator cho channel

Một validator Java nhỏ có thể biến dữ liệu đầu vào không tin cậy thành tập giá trị hợp lệ:

~~~java
package com.example.orders.tracing;

import java.util.Locale;
import java.util.Set;

public final class BaggageValuePolicy {
    private static final Set<String> ALLOWED_CHANNELS =
            Set.of("web", "batch", "partner");

    private BaggageValuePolicy() {
    }

    public static String normalizeChannel(String candidate) {
        if (candidate == null || candidate.isBlank()) {
            return "unknown";
        }

        String normalized = candidate.trim().toLowerCase(Locale.ROOT);
        if (!ALLOWED_CHANNELS.contains(normalized)) {
            return "unknown";
        }
        return normalized;
    }
}
~~~

Không nên đưa nguyên chuỗi đầu vào nếu không hợp lệ vào baggage để “dễ debug”. Giá trị `unknown` có tập hữu hạn và không tiết lộ input. Nếu cần điều tra một request vi phạm, ghi **một sự kiện bảo mật đã được làm sạch** theo policy, không echo raw header.

### 4.2. Không chỉ kiểm tra tên key

Allowlist key là cần thiết nhưng chưa đủ. Giá trị cũng phải:

- được giới hạn độ dài;
- được chuẩn hóa theo quy tắc cố định;
- nằm trong tập giá trị cho phép hoặc đúng định dạng đã định;
- không chứa control characters/chuỗi gây log injection;
- không chứa dữ liệu nhạy cảm;
- không làm tăng cardinality ngoài dự kiến.

Ví dụ `orders.channel` có allowlist key nhưng nếu nhận bất cứ chuỗi nào từ caller, attacker có thể gửi email hoặc một giá trị ngẫu nhiên dài làm tăng kích thước header và log volume.

### 4.3. Kiểm soát metadata W3C Baggage

W3C Baggage cho phép member có metadata kèm theo. Không mặc định rằng các metadata fields đó được mọi service, proxy hoặc backend xử lý giống nhau. Nếu hệ thống không có use case cụ thể, **không sử dụng metadata tùy ý**. Cần xem xét cả key, value và metadata trong tổng ngân sách kích thước và policy; không coi metadata là nơi cất bí mật.

## 5. Giới hạn kích thước và chống header amplification

Baggage được serialize thành HTTP header, nên chịu giới hạn của:

- HTTP client;
- API gateway/ingress;
- reverse proxy/load balancer;
- HTTP server/container;
- service mesh hoặc sidecar;
- các hop tiếp theo.

Một upstream cho phép header lớn không có nghĩa mọi downstream đều chấp nhận cùng kích thước. Khi baggage quá lớn, request có thể bị từ chối (ví dụ 400, 413 hoặc 431 tùy thành phần), bị strip hoặc bị log lỗi.

### 5.1. Ngân sách baggage

Hãy định nghĩa ngân sách ở cấp tổ chức/ứng dụng thay vì dựa vào giới hạn lớn nhất của một proxy đơn lẻ:

| Quy tắc | Ví dụ chính sách nội bộ |
| --- | --- |
| Số members | Chỉ vài field đã được phê duyệt |
| Key length | Ngắn và có namespace |
| Value length | Chỉ vài chục ký tự cho field phân loại |
| Tổng header size | Dưới giới hạn thấp nhất trong chuỗi gateway/client/server |
| Character set | Theo W3C Baggage và contract của ứng dụng |
| Metadata | Tắt hoặc chỉ cho phép key cụ thể |
| Repeated fields | Chuẩn hóa và loại duplicate theo policy |

Các con số cụ thể cần được xác định theo môi trường; bảng trên là nguyên tắc, không phải giới hạn bắt buộc từ chuẩn. **Đừng thiết lập max-size bằng đúng ngưỡng cao nhất của gateway**, vì header còn chứa `traceparent`, cookies, authentication và các header khác.

### 5.2. Không nối header thủ công

Không nên làm:

~~~java
request.header("baggage",
        request.getHeader("baggage") + ",orders.channel=web");
~~~

Đoạn này có thể tạo duplicate keys, encoding sai, giữ lại các field không đáng tin và vượt giới hạn kích thước. Hãy sử dụng API baggage/propagator của tracing stack, chỉ inject các field allowlist và áp dụng policy tại trust boundary.

### 5.3. Xử lý field không hợp lệ

Khi baggage đầu vào không hợp lệ:

1. Không propagate nguyên giá trị.
2. Xóa field vi phạm hoặc thay bằng giá trị đã chuẩn hóa nếu use case cho phép.
3. Không log raw value.
4. Ghi metric tổng hợp số lần bị loại nếu cần theo dõi, dùng nhãn nguyên nhân có tập giá trị nhỏ.
5. Nếu vi phạm policy bảo mật, ghi sự kiện audit an toàn ở nơi thích hợp.

Không nhất thiết từ chối toàn bộ request nghiệp vụ chỉ vì một field baggage tùy chọn sai định dạng. Quyết định reject request phải dựa trên hợp đồng API/security, không chỉ trên tiện ích observability.

## 6. Cấu hình Spring Boot/Micrometer Tracing có kiểm soát

Với Spring Boot 3.x và Micrometer Tracing bridge phù hợp, dependency minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Các phiên bản nên được quản lý theo Spring Boot BOM. Baggage configuration là một phần của tracing integration, không phải setting của Prometheus registry.

### 6.1. Khai báo field được phép propagate và log correlate

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    baggage:
      remote-fields:
        - orders.channel
        - deployment.region
      correlation:
        fields:
          - orders.channel
          - deployment.region
    sampling:
      probability: 0.1
~~~

Ý nghĩa:

- `remote-fields` là nhóm field được cấu hình cho việc propagate qua ranh giới service theo tích hợp Spring Boot tương ứng.
- `correlation.fields` là nhóm field được dùng cho log correlation/MDC khi logging integration hỗ trợ.
- Sampling xác định phần traces được ghi nhận; **không phải bộ lọc dữ liệu baggage**.

Hai danh sách cần được review độc lập. Một field có thể được propagate nhưng không được đưa vào log; field được correlate trong local logs cũng không mặc nhiên phải gửi qua mọi service. Không thêm `customer.email` hoặc `authorization` vào bất kỳ danh sách nào.

Property có thể thay đổi theo Spring Boot/Micrometer version. Trước khi nâng cấp, kiểm tra binding và test output ở đúng version đang dùng.

### 6.2. Tạo baggage sau khi dữ liệu đã xác minh

Ví dụ service đã nhận channel từ một nguồn có thẩm quyền và chuẩn hóa:

~~~java
package com.example.orders.tracing;

import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class OrderContextService {
    private final Tracer tracer;

    public OrderContextService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void process(String verifiedChannel) {
        String channel =
                BaggageValuePolicy.normalizeChannel(verifiedChannel);

        try (BaggageInScope ignored =
                     tracer.createBaggageInScope("orders.channel", channel)) {
            processOrder();
        }
    }

    private void processOrder() {
        // Gọi downstream đã được instrument phù hợp.
    }
}
~~~

Điểm bảo mật nằm ở **nguồn của `verifiedChannel`**: nó phải đến từ context đã xác thực hoặc server-side routing/configuration, không phải raw baggage header chưa xác minh. Scope đóng khi kết thúc xử lý giúp tránh để giá trị còn active trong thread được tái sử dụng.

### 6.3. Không đọc baggage để phân quyền

Một service có thể đọc `orders.channel` nhằm thêm log field hoặc chọn dashboard filter. Không dùng `tenant.role` hoặc `user.permission` trong baggage để quyết định có cho phép gọi API. Quyết định security phải dựa trên principal/authorization context có thể xác minh.

### 6.4. Correlation sang MDC/logs

Khi correlation fields được cấu hình, Spring Boot/Micrometer logging integration có thể đưa baggage vào MDC. Kiểm tra log event thật để xác nhận key names và format; không giả định MDC luôn chứa tên key nguyên văn.

Ví dụ log an toàn:

~~~text
INFO service=inventory-service traceId=4bf92f...
spanId=00f067... orders.channel=web event=reservation_started
~~~

Ví dụ log không an toàn:

~~~text
INFO traceId=... baggage=customer.email=alice@example.com
authorization=Bearer eyJ... request.body={...}
~~~

Log correlation phải có allowlist riêng. Nếu một field baggage được propagate tới downstream nhưng không cần cho log, đừng tự động log tất cả baggage members.

## 7. Bảo vệ dữ liệu tại các sink: traces, logs và metrics

Baggage chỉ là nguồn context. Sau khi được extract, code hoặc instrumentation có thể copy values sang các hệ thống khác. Mỗi sink cần chính sách riêng.

| Sink | Rủi ro | Quy tắc |
| --- | --- | --- |
| HTTP baggage header | Phát tán qua nhiều service/hop | Remote allowlist, kiểm tra nguồn và giới hạn size |
| Span attributes | Trace backend lưu/index giá trị qua thời gian | Chỉ gắn thuộc tính cần thiết, loại PII/secrets |
| Logs/MDC | Dễ bị nhiều người truy cập và retention lâu | Correlation allowlist, masking/redaction, retention |
| Metrics labels | Cardinality bùng nổ và dữ liệu bị nhân thành series | Chỉ dùng giá trị hữu hạn, không đưa request/customer IDs |
| Collector processors | Dữ liệu có thể bị transform/export sang hệ khác | Kiểm tra filter/redaction trước khi export |
| Dashboard/alert | Người dùng rộng hơn có thể nhìn thấy fields | Quyền truy cập và query không làm lộ dữ liệu |

### 7.1. Low/high cardinality vẫn cần bảo vệ

Trong Micrometer Observation:

- **Low-cardinality key-values** thường có thể đi vào metrics và span attributes.
- **High-cardinality key-values** được dùng cho metadata span theo policy, không phù hợp làm metric labels.

Nhưng high-cardinality không có nghĩa là an toàn. Một `customer.id` có thể là high cardinality và vẫn là dữ liệu định danh. Cần cả **cardinality review** và **privacy/security review**.

### 7.2. Trace ID cũng là dữ liệu cần quản lý

Trace ID thường là định danh kỹ thuật ngẫu nhiên, không phải credential, nhưng khi được liên kết với log hoặc thông tin người dùng nó có thể trở thành khóa tra cứu dẫn tới dữ liệu nhạy cảm. Giới hạn quyền xem telemetry và tránh đưa trace ID vào metric labels.

### 7.3. Không dùng baggage thay cho log context cần thiết

Nếu một field chỉ cần trong log của một service, có thể thêm nó vào structured log tại service đó thay vì propagate toàn hệ thống. Mỗi hop bổ sung một header và một bản sao metadata. Chỉ truyền nếu downstream thực sự cần.

## 8. Context propagation, async và vòng đời dữ liệu

Baggage gắn với execution/tracing context. Khi xử lý đồng bộ, scope giúp field hiện hành trong khoảng thao tác. Khi chuyển sang executor, Reactor, messaging hoặc batch, cần đảm bảo context được capture/restore đúng.

### 8.1. Thread pool có thể gây rò rỉ context

Nếu scope không được đóng, thread pool có thể tái sử dụng thread với baggage của request trước. Kịch bản nguy hiểm:

~~~text
Request A: orders.channel=partner
  -> worker thread 3
  -> scope không được close

Request B: orders.channel=web
  -> worker thread 3 được tái sử dụng
  -> có thể nhìn thấy context cũ nếu propagation/cleanup sai
~~~

Luôn quản lý scope bằng `try-with-resources` hoặc API lifecycle tương ứng. Với executor, chỉ dùng cơ chế context propagation được hỗ trợ; kiểm thử cả **context được truyền** và **context được dọn/restore**.

### 8.2. ContextPropagatingTaskDecorator

Với Spring Framework 6.1+ và Micrometer Context Propagation, executor Spring có thể sử dụng `ContextPropagatingTaskDecorator` khi các context accessors phù hợp được đăng ký:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class SecureContextExecutorConfiguration {
    @Bean
    ThreadPoolTaskExecutor contextAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Decorator giúp capture/restore những context đã đăng ký; **không phải cơ chế allowlist dữ liệu**. Nếu baggage có field không an toàn, decorator vẫn có thể truyền context đó. Hãy làm sạch/kiểm soát baggage trước khi submit task.

### 8.3. Messaging và batch

Với Kafka/RabbitMQ, propagator hoặc instrumentation có thể inject/extract trace context và baggage trong message headers. Một message có thể nằm trong queue lâu hơn request ban đầu; baggage không nên chứa dữ liệu tạm thời hoặc secret vì nó sẽ tồn tại trong broker headers và có thể được lưu cùng message.

Batch xử lý nhiều messages từ nhiều traces không thể mặc nhiên gom tất cả baggage vào một context duy nhất. Hãy định nghĩa quan hệ span links/parent theo semantics, không trộn baggage của một message lên mọi message còn lại.

## 9. Kiểm thử chính sách bảo vệ baggage

Test cần xác minh **giá trị không hợp lệ bị loại**, **giá trị hợp lệ được propagate đúng**, và **không rò rỉ qua log/async**. Chỉ test getter/setter của baggage không đủ để chứng minh policy an toàn.

### 9.1. Unit test validator

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class BaggageValuePolicyTest {

    @Test
    void normalizesAllowedChannel() {
        assertEquals("web",
                BaggageValuePolicy.normalizeChannel(" WEB "));
        assertEquals("batch",
                BaggageValuePolicy.normalizeChannel("batch"));
    }

    @Test
    void rejectsUnknownOrUntrustedValues() {
        assertEquals("unknown",
                BaggageValuePolicy.normalizeChannel("internal-admin"));
        assertEquals("unknown",
                BaggageValuePolicy.normalizeChannel("alice@example.com"));
        assertEquals("unknown",
                BaggageValuePolicy.normalizeChannel(null));
    }
}
~~~

Test này bảo vệ tập giá trị cho channel. Ứng dụng vẫn cần kiểm tra nguồn dữ liệu và các field khác; một validator đơn lẻ không thể thay thế toàn bộ policy.

### 9.2. Test allowlist propagation qua HTTP

Một integration test với HTTP client/server đã được tracing instrument nên:

1. Tạo baggage hợp lệ `orders.channel=web` trong scope.
2. Thêm một field không được phép vào input thử nghiệm (ví dụ `customer.email`).
3. Gửi request tới server test.
4. Kiểm tra server nhận được field allowlist theo API baggage đã parse.
5. Kiểm tra field cấm không xuất hiện trong context downstream hoặc log.
6. Kiểm tra trace context vẫn được nối nếu propagation W3C được bật.

Test nên dùng API parser/context accessor, không chỉ so sánh raw header, vì header có thể được encode hoặc sắp xếp khác nhau.

### 9.3. Test log redaction và MDC cleanup

Capture log events trong test:

- Ghi log khi baggage hợp lệ đang active; xác nhận chỉ field được duyệt xuất hiện.
- Đưa input chứa email/token vào ranh giới; xác nhận raw value không xuất hiện trong log.
- Đóng scope và ghi log event tiếp theo trên cùng thread; xác nhận baggage của request trước không còn.
- Kiểm tra exception message cũng không chứa token, payload hoặc dữ liệu nhạy cảm.

### 9.4. Test header size và duplicate keys

Tạo baggage với số members/values vượt ngân sách đã định; policy phải loại, từ chối hoặc giới hạn theo hành vi ứng dụng, và không propagate header phình to. Thử duplicate key và giá trị có ký tự bất thường; xác định quy tắc nhận một giá trị, từ chối hay normalize. Không để mỗi service tự chọn cách xử lý khác nhau.

### 9.5. Test async context isolation

Sử dụng một executor có một worker thread để dễ tái sử dụng:

1. Task A đặt baggage đã chuẩn hóa `orders.channel=partner`.
2. Task A kết thúc; scope phải đóng.
3. Task B không được truyền baggage; nó không được nhìn thấy giá trị của A.
4. Task C có context riêng `orders.channel=web`; nó phải chỉ thấy giá trị C.
5. Chạy test lặp để phát hiện race/contamination.

Nếu có context propagation decorator, test cả đường có propagation và đường không có propagation để xác nhận policy mong đợi. Đừng coi việc task đọc được baggage là đủ nếu chưa chứng minh cleanup.

## 10. Troubleshooting và ứng phó sự cố

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Downstream nhận email trong baggage | Ingress không strip/validate field | Dừng propagation, sửa allowlist và loại field |
| Baggage của client ghi đè context nội bộ | Không phân biệt nguồn và trust level | Strip/overwrite tại trust boundary |
| Logs xuất token hoặc PII | Log correlation quá rộng, raw baggage được log | Ngừng export, redaction, xử lý logs đã lưu |
| Header 431/400 | Baggage quá dài hoặc encoding/duplicates sai | Giới hạn size/members và chuẩn hóa parser |
| Baggage cũ xuất hiện trong request sau | Scope không close hoặc context không restore | Kiểm tra try-with-resources và executor propagation |
| Baggage biến mất qua một gateway | Header bị strip hoặc giới hạn | Kiểm tra cấu hình gateway và contract |
| Metric series tăng đột biến | Baggage values bị copy thành labels | Loại field động khỏi metric tags |
| Traces thiếu attributes sau khi lọc | Policy/processor loại field hoặc backend giới hạn | Kiểm tra từng sink và exporter/Collector |
| Baggage có nhưng trace không thấy | Sampling/exporter/backend lỗi | Kiểm tra tracing pipeline riêng |
| Channel khác giữa logs hai service | Service tự normalize khác nhau hoặc propagation sai | Chuẩn hóa một nơi và kiểm tra extraction |

### 10.1. Quy trình phản ứng khi baggage làm lộ dữ liệu

1. **Khoanh vùng field:** xác định key/value nào đã bị phát tán, bắt đầu từ service nào và thời điểm nào.
2. **Chặn phát tán:** tạm thời remove key khỏi remote allowlist/correlation list hoặc cấu hình strip tại ingress và downstream boundary.
3. **Ngăn ghi thêm:** tắt instrumentation/logging path liên quan nếu cần, nhưng giữ telemetry vận hành an toàn để quan sát tác động.
4. **Xác định hệ thống nhận:** gateway logs, service logs, Collector, trace backend, metrics backend, broker headers và bản lưu/export.
5. **Đánh giá phạm vi truy cập:** ai có thể đọc dữ liệu, thời gian retention và bản sao downstream.
6. **Xử lý credential nếu có:** thu hồi/rotate token hoặc API key đã lộ theo quy trình quản lý secrets.
7. **Xóa/expire dữ liệu:** áp dụng chính sách retention, deletion và incident response của từng backend; không giả định xóa một trace sẽ xóa mọi bản sao logs.
8. **Kiểm tra lại:** thêm test regression xác nhận dữ liệu bị chặn ở trust boundary và mọi sink.

Nếu dữ liệu cá nhân hoặc credential đã được phát tán, áp dụng quy trình security/privacy incident của tổ chức và nghĩa vụ pháp lý tương ứng. Không xóa dấu vết audit cần thiết khi chưa phối hợp với người phụ trách incident.

### 10.2. Metrics an toàn để quan sát policy

Có thể ghi nhận số lần baggage field bị từ chối bằng counter với label nguyên nhân hữu hạn, ví dụ `reason=unknown_key`, `reason=invalid_value`, `reason=too_large`. Không ghi raw key/value đầu vào thành label. Metric này giúp phát hiện client gửi header bất thường mà không nhân bản dữ liệu nhạy cảm vào hệ thống giám sát.

## 11. Checklist production

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Có inventory baggage fields | Mỗi key có owner, use case và dữ liệu nguồn |
| Deny by default | Chỉ remote allowlist field được duyệt |
| Trust boundary được xác định | External baggage được strip/validate trước khi tin |
| Values chuẩn hóa | Enum/format/length được kiểm tra |
| Không có secrets/PII | Security review và test log/headers |
| Không dùng baggage cho authorization | Quyền lấy từ nguồn xác thực, không từ caller metadata |
| Header size nằm trong ngân sách | Có giới hạn thấp hơn chuỗi proxy/client/server |
| Correlation fields tách riêng | Chỉ field đã duyệt được ghi vào logs |
| Span attributes có policy | Không auto-copy toàn bộ baggage |
| Metric labels cardinality thấp | Không có request/customer IDs hoặc giá trị tự do |
| Async/messaging isolation đã test | Không mất context và không rò rỉ sang task khác |
| Exporter/backend được kiểm tra | Biết nơi traces/logs được lưu và thời hạn retention |
| Có incident response | Có cách chặn, rotate secrets, tìm và xử lý bản sao |
| Có regression tests | Spoofing, PII, header size, duplicate keys, cleanup |

## 12. Bài thực hành: harden baggage cho order-service

**Bối cảnh:** `order-service` nhận request từ web và partner, sau đó gọi `inventory-service` và `payment-service`. Gần đây nhóm phát hiện header baggage có thể chứa field do client gửi tùy ý và các field đó đôi khi xuất hiện trong logs.

**Nhiệm vụ:**

1. Lập inventory các baggage fields cần dùng, chỉ giữ `orders.channel` và `deployment.region` trong ví dụ.
2. Xác định nguồn đáng tin của channel (gateway/API integration config), không sử dụng raw value do caller gửi.
3. Viết validator cho tập channel `web`, `batch`, `partner`; giá trị khác trở thành `unknown` hoặc bị loại theo policy.
4. Cấu hình `management.tracing.baggage.remote-fields` và `correlation.fields` riêng biệt.
5. Tạo baggage bằng `Tracer.createBaggageInScope` trong service sau khi đã xác thực/chuẩn hóa.
6. Gọi inventory-service bằng HTTP client instrument, kiểm tra header baggage chỉ có field được duyệt và trace context vẫn nối.
7. Thử gửi `customer.email`, `authorization` và chuỗi rất dài từ client; chứng minh các giá trị này không tới downstream/logs.
8. Capture log event, xác minh MDC chỉ chứa trace/span ID và channel được duyệt; scope đóng xong không còn context cũ.
9. Chạy hai tác vụ trên cùng executor thread để kiểm tra async context isolation.
10. Tạo metrics counter về số baggage bị loại theo reason hữu hạn; không gắn raw key/value thành labels.
11. Mô phỏng sự cố field nhạy cảm đã tới Collector, viết các bước chặn propagation, xử lý credential và tìm bản sao theo retention policy.

**Kết quả mong đợi:** policy allowlist, code validation, Spring configuration, propagation test, log redaction test, async isolation test và playbook xử lý sự cố.

## 13. Ghi nhớ

**Baggage là một kênh truyền context, không phải kênh tin cậy hoặc kho secrets.** Mỗi field có thể đi qua nhiều service, proxy, Collector và backend logs/traces. Vì vậy cần xác định nguồn tạo, trust level, giá trị hợp lệ, phạm vi propagation, sink được phép và thời gian lưu.

Áp dụng **deny-by-default allowlist**, validate/normalize values, giới hạn số member và kích thước, strip dữ liệu ngoài tại trust boundary, đóng scope đúng vòng đời và không dùng baggage để cấp quyền. Span attributes, MDC/log fields và metric labels cần policy riêng: không copy tất cả baggage sang mọi sink, không đưa PII/secrets vào telemetry và không dùng high-cardinality values làm metric labels.

Bảo vệ baggage hiệu quả phải được kiểm thử ở cả **creation, injection, extraction, async propagation, logging, metrics và export**. Khi có sự cố, chặn phát tán trước, xác định các backend đã nhận dữ liệu, xử lý credential/retention theo incident policy và bổ sung regression tests để ngăn tái diễn.

**Tài liệu tham khảo:**

- [W3C — Baggage](https://www.w3.org/TR/baggage/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
