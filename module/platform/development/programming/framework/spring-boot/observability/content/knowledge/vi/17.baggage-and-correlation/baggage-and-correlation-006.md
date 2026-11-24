# Baggage trong gRPC metadata

Trong chương **Baggage và correlation** của mô-đun **SPRING_BOOT_OBSERVABILITY**, baggage là các cặp key–value gắn với trace context để mang một lượng metadata nhỏ qua ranh giới dịch vụ. Khi ứng dụng Spring Boot gọi một dịch vụ khác bằng **gRPC**, metadata của RPC là carrier phù hợp để truyền các baggage fields đã được cho phép. Nhờ vậy, các dịch vụ có thể giữ chung một số ngữ cảnh như vùng xử lý hoặc loại luồng request khi ghi log và phân tích trace.

Baggage không phải payload nghiệp vụ và cũng không phải cơ chế xác thực. Dữ liệu trong baggage có thể đi qua nhiều dịch vụ, interceptor, proxy và hệ thống telemetry. Vì thế, nội dung phải được allowlist, giới hạn kích thước và kiểm soát quyền riêng tư. Bài này hướng dẫn chuyển baggage qua **gRPC metadata**, kết hợp Micrometer Tracing/OpenTelemetry để giữ trace context và correlation trong hệ thống observability của Spring Boot.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt baggage, trace ID, span ID, gRPC metadata và protobuf message.
2. Mô tả cách W3C Baggage được biểu diễn qua metadata của một gRPC call.
3. Phân biệt metadata dạng ASCII với binary metadata có hậu tố **-bin**.
4. Cấu hình các baggage fields được phép truyền từ Spring Boot/Micrometer Tracing.
5. Dùng OpenTelemetry gRPC instrumentation để inject/extract context ở client và server.
6. Hiểu vai trò của interceptors và cách kiểm tra dữ liệu ở hai đầu.
7. Giới hạn baggage về số field, độ dài, cardinality và dữ liệu nhạy cảm.
8. Phân tích lỗi mất baggage, trace bị đứt, metadata quá lớn và log correlation không nhất quán.
9. Kết hợp baggage với metrics, logs và distributed tracing mà không biến baggage thành kênh truyền dữ liệu nghiệp vụ.

## 2. Baggage là gì?

**Baggage** là tập các cặp key–value gắn với context của trace và có thể được propagate từ dịch vụ này sang dịch vụ khác. Nó hữu ích cho metadata nhỏ liên quan đến nhiều bước xử lý, ví dụ:

- **region=ap-southeast-1** để hỗ trợ phân tích luồng đi qua các vùng.
- **request.class=interactive** để phân biệt một lớp traffic có số giá trị hữu hạn.
- **tenant.tier=standard** để phân nhóm xử lý theo policy đã được phê duyệt.

Baggage có thể được truy cập trong quá trình xử lý hiện tại và inject vào lời gọi downstream nếu propagator được cấu hình. Hệ thống phía nhận extract baggage từ carrier, ví dụ HTTP headers hoặc gRPC metadata, rồi đưa các giá trị vào context của request kế tiếp.

### Baggage không thay thế những gì?

| Khái niệm | Mục đích | Ví dụ |
| --- | --- | --- |
| **Trace ID** | Định danh một trace phân tán. | Một trace gồm nhiều spans trong nhiều service. |
| **Span ID** | Định danh một đơn vị công việc trong trace. | Span server xử lý RPC ReserveStock. |
| **Baggage** | Metadata nhỏ được propagate cùng context. | region=ap-southeast-1. |
| **gRPC metadata** | Carrier truyền key–value ở đầu request/response RPC. | baggage: region=ap-southeast-1. |
| **Request message** | Payload nghiệp vụ của RPC. | ReserveRequest chứa sku và quantity. |
| **Log correlation fields** | Trường giúp tìm và nhóm log. | traceId, spanId, tenantTier. |

Header W3C Trace Context chứa trace ID, parent span ID và flags; nó không chứa danh sách baggage. Baggage được truyền bằng header W3C riêng tên baggage. Khi chuyển sang gRPC, hai khái niệm này được chuyển thành metadata entries tương ứng, miễn là propagator và instrumentation được cấu hình.

**Không dùng baggage làm nơi lưu authorization token, session cookie hoặc quyền truy cập.** Baggage không được thiết kế để xác thực caller và có thể bị chuyển tiếp rộng hơn dự kiến.

## 3. gRPC metadata là carrier như thế nào?

gRPC metadata là tập key–value gắn với RPC call. Metadata có thể được gửi từ client tới server dưới dạng request metadata (headers); server cũng có thể trả metadata ở response headers hoặc trailers.

Trong Java gRPC, metadata được biểu diễn bởi lớp Metadata. Một key khai báo kiểu marshaller cho giá trị:

~~~java
Metadata.Key<String> regionKey =
        Metadata.Key.of(
                "region",
                Metadata.ASCII_STRING_MARSHALLER);
~~~

Các quy tắc cần nhớ:

- Metadata keys là tên ASCII viết thường; không dùng chữ hoa trong key.
- Key dùng cho giá trị text thường là ASCII metadata.
- Key kết thúc bằng -bin dành cho dữ liệu binary và phải dùng marshaller tương ứng.
- Không tự thêm prefix grpc-; prefix đó dành cho giao thức.
- Metadata phải nhỏ; header quá lớn có thể bị từ chối bởi client, server, proxy hoặc giới hạn cấu hình hạ tầng.
- Nếu một field chỉ cho phép một giá trị, hãy xác định cách xử lý khi key xuất hiện nhiều lần.

Với W3C Baggage, propagator serialize danh sách baggage thành chuỗi text theo quy tắc W3C Baggage. Vì vậy key carrier là baggage dạng ASCII, không phải một key tự đặt cho từng field. Ví dụ minh họa:

~~~text
baggage: region=ap-southeast-1,request.class=interactive
~~~

Đây là biểu diễn minh họa. Khi có encoding hoặc nhiều giá trị, hãy để W3C propagator serialize/parse theo chuẩn thay vì tự nối chuỗi bằng dấu phẩy.

### Luồng qua gRPC

~~~mermaid
sequenceDiagram
    participant A as Spring Boot service A
    participant C as gRPC client interceptor
    participant M as gRPC Metadata
    participant S as gRPC server interceptor
    participant B as Spring Boot service B

    A->>C: Gọi RPC trong trace/baggage context
    C->>M: Inject trace context và baggage
    M->>S: Gửi request metadata
    S->>S: Extract context từ metadata
    S->>B: Chạy handler trong context đã khôi phục
    B-->>A: Trả kết quả RPC
~~~

Interceptors là điểm tích hợp thuận tiện vì chúng quan sát các RPC call trên channel/server mà chúng được gắn vào. Một interceptor tự viết phải chú ý exception, cancellation và lifecycle; dùng instrumentation thư viện đã được kiểm chứng thường ít lỗi hơn.

## 4. W3C Baggage và gRPC metadata

W3C Baggage định nghĩa header text tên baggage. Khi dùng OpenTelemetry propagator, baggage được serialize thành một giá trị text rồi đặt vào carrier. Trong gRPC, metadata là carrier tương ứng; key baggage được dùng để vận chuyển chuỗi này.

Ví dụ các field logic:

~~~text
region = ap-southeast-1
request.class = interactive
tenant.tier = standard
~~~

Không nên tự tạo metadata key riêng cho mọi baggage field nếu muốn tương thích với W3C Baggage. Dùng một key baggage và để propagator encode/decode danh sách field.

### Không phải mọi metadata đều là baggage

| Metadata | Vai trò | Có nên coi là baggage? |
| --- | --- | --- |
| authorization | Credentials/xác thực. | Không. |
| content-type | Định dạng message/protocol. | Không. |
| traceparent | W3C trace context. | Không; đây là trace propagation. |
| baggage | W3C baggage fields. | Có. |
| x-request-id | Request correlation theo quy ước ứng dụng. | Không mặc nhiên; đây là metadata riêng. |
| tenant.tier | Field nhỏ được cho phép propagate. | Chỉ khi được đưa vào W3C baggage theo policy. |

Không lấy toàn bộ gRPC metadata rồi tự động đưa vào baggage hoặc span attributes. Làm như vậy có thể sao chép credentials, dữ liệu cá nhân hoặc metadata nội bộ sang trace backend.

## 5. Cấu hình baggage trong Spring Boot

Ví dụ giả định Spring Boot 3.x, Micrometer Tracing và OpenTelemetry bridge được quản lý qua Spring Boot dependency management. Tên baggage fields cần được khai báo rõ; không propagate mọi giá trị mà ứng dụng có thể tạo.

Dependency minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'

    implementation 'io.grpc:grpc-netty-shaded'
    implementation 'io.grpc:grpc-protobuf'
    implementation 'io.grpc:grpc-stub'
}
~~~

Các phiên bản gRPC và OpenTelemetry instrumentation cần được quản lý nhất quán qua BOM/dependency management tương thích với ứng dụng. Dependency cụ thể còn phụ thuộc thư viện sinh code gRPC và phiên bản Java plugin của dự án.

Cấu hình baggage fields trong application.yml:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
    baggage:
      remote-fields:
        - region
        - request.class
        - tenant.tier
      correlation:
        fields:
          - region
          - request.class
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Giải thích:

- remote-fields khai báo các trường baggage được phép propagate qua ranh giới remote theo cơ chế Micrometer Tracing/Spring Boot của phiên bản đang dùng.
- correlation.fields yêu cầu các trường được chọn có thể được dùng làm correlation fields trong logs khi integration tương ứng hỗ trợ.
- sampling.probability quyết định sampling traces theo cấu hình; baggage được quản lý theo context request, còn spans có thể bị sample out.
- OTLP endpoint phục vụ xuất spans; nó không phải gRPC business endpoint mà service gọi.

Property names và cách bridge ánh xạ baggage phải được xác minh theo Spring Boot release đang triển khai. Nếu dùng Brave bridge, cấu hình baggage và propagation có thể khác; không copy nguyên cấu hình OTel sang implementation khác mà chưa kiểm tra.

### Local fields và remote fields

Một số metadata chỉ cần dùng trong service hiện tại, không cần gửi qua mạng:

- **Local baggage fields:** dùng trong context hiện tại nhưng không chủ động propagate tới downstream.
- **Remote baggage fields:** các field được phép inject vào carrier cho service khác.
- **Correlation fields:** các field có thể được đưa vào logging context/MDC để log dễ lọc.

Không đưa mọi field vào cả ba nhóm. Mỗi field phải có mục đích và owner rõ ràng. Với hệ thống đa tenant, tenant tier có thể hữu ích, nhưng không được làm lộ định danh khách hàng hoặc quyền truy cập.

## 6. Cách OpenTelemetry gắn baggage vào gRPC

Một cách được ưu tiên là dùng **OpenTelemetry gRPC instrumentation** với cùng OpenTelemetry instance/propagators mà tracing của ứng dụng sử dụng. Instrumentation tạo client/server interceptors để inject/extract context từ gRPC metadata, bao gồm trace context và baggage nếu propagators được cấu hình phù hợp.

Với các phiên bản OpenTelemetry gRPC instrumentation có API GrpcTelemetry, mã cấu hình có dạng:

~~~java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.instrumentation.grpc.v1_6.GrpcTelemetry;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Server;
import io.grpc.ServerBuilder;

public final class GrpcTracingConfiguration {

    private final GrpcTelemetry grpcTelemetry;

    public GrpcTracingConfiguration(OpenTelemetry openTelemetry) {
        this.grpcTelemetry = GrpcTelemetry.create(openTelemetry);
    }

    public ManagedChannel createClientChannel(String host, int port) {
        return ManagedChannelBuilder
                .forAddress(host, port)
                .usePlaintext() // Chỉ dùng trong lab/mạng thử nghiệm an toàn.
                .intercept(grpcTelemetry.newClientInterceptor())
                .build();
    }

    public Server createServer(int port,
                               io.grpc.BindableService service) {
        return ServerBuilder.forPort(port)
                .addService(service)
                .intercept(grpcTelemetry.newServerInterceptor())
                .build();
    }
}
~~~

Đây là ví dụ về cách gắn interceptors; trong dự án thực, nên quản lý channel/server bằng Spring beans hoặc thành phần có lifecycle rõ ràng, đóng channel/server khi ứng dụng shutdown, và cấu hình TLS thay cho usePlaintext() ngoài lab. API package/version của instrumentation phải khớp artifact opentelemetry-grpc-1.6 và OpenTelemetry instrumentation BOM mà dự án dùng.

**Quan trọng:** OpenTelemetry instance đưa vào GrpcTelemetry.create(...) phải là instance chia sẻ với pipeline tracing của ứng dụng, hoặc ít nhất dùng cùng cấu hình propagators/context. Nếu tự tạo SDK riêng, bạn có thể tạo trace không liên kết với Micrometer Tracing đang hoạt động trong Spring Boot.

### Propagator phải có W3C Baggage

Để baggage được chuyển tiếp, OpenTelemetry propagators cần bao gồm W3C Baggage propagator (thường kết hợp W3C Trace Context). Nếu chỉ có trace context propagator, traceparent vẫn có thể được inject/extract nhưng baggage fields sẽ không được chuyển.

Khi dùng Spring Boot/Micrometer Tracing bridge, kiểm tra cấu hình propagation mà auto-configuration tạo ra và các remote baggage fields. Không tạo composite propagator cạnh tranh với pipeline do Boot quản lý; nếu phải tùy chỉnh, hãy cấu hình chính instance đang được gRPC instrumentation sử dụng.

## 7. Baggage được tạo và đọc ở đâu?

Baggage có thể được tạo ở điểm vào request hoặc trong service đã có context. Ví dụ dùng OpenTelemetry API trực tiếp:

~~~java
import io.opentelemetry.api.baggage.Baggage;
import io.opentelemetry.context.Context;

public final class RequestBaggage {

    public Context withRegion(String region) {
        Baggage baggage = Baggage.builder()
                .put("region", region)
                .put("request.class", "interactive")
                .build();

        return baggage.storeInContext(Context.current());
    }
}
~~~

Đoạn trên tạo OTel context mới với baggage, nhưng chưa tự động bảo đảm context đó trở thành current context cho toàn bộ request. Trong code tích hợp thực tế, cần mở scope/đặt context theo đúng lifecycle và dùng API Micrometer Tracing/Micrometer Baggage khi muốn giữ abstraction ở cấp ứng dụng. Không giữ scope mở qua nhiều thread.

Một cách đọc baggage trong context:

~~~java
Baggage baggage = Baggage.fromContext(Context.current());
String region = baggage.getEntryValue("region");
~~~

Nếu giá trị không có, region có thể là null. Code phải có fallback thích hợp thay vì giả định mọi request đều mang field này. Baggage từ remote caller là dữ liệu đầu vào cần kiểm tra/chuẩn hóa trước khi dùng vào logic.

### Không dùng baggage để thay payload

Nếu RPC cần biết SKU, quantity, account ID hay thông tin cần thiết để thực hiện nghiệp vụ, hãy truyền trong protobuf request message. Baggage chỉ nên chứa **metadata xuyên suốt** để correlation/observability hoặc một số policy context nhỏ đã được phê duyệt.

Đừng dựa vào baggage để quyết định người gọi có quyền truy cập tenant. Authorization phải dựa trên identity và policy đáng tin cậy đã được xác thực; baggage có thể do caller kiểm soát và không phải proof of identity.

## 8. Đặt một gRPC RPC trong trace

Khi gRPC client interceptor tạo client span và server interceptor extract context để tạo server span, trace có thể có dạng:

~~~text
Trace ID: 4f17c38a927d4b55a90714b02f8e6d19
└── SERVER order-api: POST /orders
    └── CLIENT inventory-api: Inventory.Reserve
        └── SERVER inventory-api: Inventory.Reserve
~~~

Trong thiết kế đúng, baggage có thể được đọc ở server handler và xuất hiện trên log/span nếu instrumentation được phép. Tuy nhiên, span client và server không tự chứng minh baggage đã tới nơi; phải kiểm tra metadata hoặc baggage context ở hai đầu.

Ví dụ logging có correlation:

~~~java
log.info("Calling inventory service with region={}", region);
~~~

Nếu logging correlation được cấu hình qua Micrometer Tracing/MDC, trace ID/span ID có thể được thêm tự động. Trường region chỉ xuất hiện nếu được đặt vào log context hoặc ghi rõ trong log. **Baggage không nhất thiết tự động trở thành MDC field**; cần cấu hình correlation fields hoặc cơ chế logging tương ứng và xác minh thực tế.

## 9. Kiểm tra baggage ở hai đầu gRPC

Một test hữu ích phải xác minh **client gửi, server nhận và context được khôi phục**. Có thể kiểm tra bằng instrumentation test hoặc gRPC integration test với server/client thật trong môi trường thử nghiệm.

| Vị trí | Bằng chứng |
| --- | --- |
| Trước lời gọi RPC ở client | Baggage context chứa field được allowlist. |
| Client interceptor | Metadata request có entry baggage sau khi inject. |
| Server interceptor | W3C propagator extract context từ metadata. |
| Server handler | Đọc được field từ current context hoặc API baggage tương ứng. |
| Logs | Có trace correlation; baggage fields chỉ xuất hiện nếu logging correlation được cấu hình. |
| Trace backend | Client/server spans cùng trace ID và baggage attributes nếu instrumentation/processor lưu chúng. |

Trong kiểm thử đơn vị cho carrier adapter tùy biến, có thể khởi tạo Metadata, inject context qua propagator, rồi extract và so sánh baggage values. Dùng propagator thật từ OpenTelemetry SDK để kiểm tra serialization; đừng tự viết parser CSV cho W3C Baggage vì chuẩn có quy tắc encoding và escaping riêng.

### Ví dụ carrier adapter để kiểm thử round-trip

Đoạn dưới minh họa nguyên tắc kiểm thử carrier. Nó dùng TextMapPropagator đã được cấu hình có W3C Baggage và một carrier Metadata:

~~~java
import io.grpc.Metadata;
import io.opentelemetry.context.propagation.TextMapPropagator;
import io.opentelemetry.context.propagation.TextMapSetter;
import io.opentelemetry.context.propagation.TextMapGetter;
import io.opentelemetry.context.Context;

public final class GrpcMetadataCarrier {

    static final TextMapSetter<Metadata> SETTER = (carrier, key, value) -> {
        Metadata.Key<String> metadataKey =
                Metadata.Key.of(
                        key.toLowerCase(java.util.Locale.ROOT),
                        Metadata.ASCII_STRING_MARSHALLER);
        carrier.put(metadataKey, value);
    };

    static final TextMapGetter<Metadata> GETTER = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(Metadata carrier) {
            return java.util.List.of("traceparent", "tracestate", "baggage");
        }

        @Override
        public String get(Metadata carrier, String key) {
            Metadata.Key<String> metadataKey =
                    Metadata.Key.of(
                            key.toLowerCase(java.util.Locale.ROOT),
                            Metadata.ASCII_STRING_MARSHALLER);
            return carrier.get(metadataKey);
        }
    };

    public static void inject(TextMapPropagator propagator,
                              Context context,
                              Metadata metadata) {
        propagator.inject(context, metadata, SETTER);
    }

    public static Context extract(TextMapPropagator propagator,
                                  Context context,
                                  Metadata metadata) {
        return propagator.extract(context, metadata, GETTER);
    }
}
~~~

Đây là ví dụ carrier adapter cho các key W3C ASCII thông dụng, không phải interceptor đầy đủ để thay thế gRPC instrumentation. Với custom propagators, getter cần công bố đúng danh sách keys mà propagator hỗ trợ; nếu có binary metadata, phải dùng marshaller phù hợp và không đưa binary field qua ASCII_STRING_MARSHALLER. Trong production, ưu tiên gRPC instrumentation thư viện để bảo toàn span lifecycle, cancellation và context propagation.

Test round-trip nên tạo W3C propagator (Trace Context + Baggage), đưa một baggage entry vào context, gọi inject, sau đó extract từ metadata mới và assert giá trị. Với Spring Boot, cần kiểm tra propagator đó tương thích với instance đang được ứng dụng sử dụng.

## 10. Giới hạn kích thước và độ an toàn của baggage

Baggage được propagate qua nhiều RPC nên mỗi field làm tăng kích thước metadata của request. gRPC, HTTP/2, proxy, service mesh và server có thể có giới hạn header/metadata khác nhau. Metadata quá lớn có thể khiến request bị từ chối hoặc tăng memory/CPU khi parse.

Áp dụng những nguyên tắc sau:

- **Allowlist field names:** chỉ propagate các field có mục đích rõ ràng.
- **Giới hạn chiều dài:** đặt giới hạn cho từng value và tổng baggage; tránh field có chuỗi rất dài.
- **Giới hạn số field:** không biến baggage thành map tự do chứa toàn bộ request context.
- **Giá trị hữu hạn:** ưu tiên region, request class hoặc tier có tập giá trị nhỏ; không dùng UUID và user IDs tùy tiện.
- **Không chứa secrets/PII:** token, cookie, email, số tài khoản, nội dung request không được đưa vào baggage theo mặc định.
- **Trust boundary:** chỉ chấp nhận hoặc chuyển tiếp field từ nguồn đã xác định; có thể loại baggage do client công khai gửi.
- **Retention và access:** baggage có thể xuất hiện trên logs và traces, do đó chịu chính sách quyền truy vấn và lưu trữ tương ứng.

Không có một giới hạn byte an toàn duy nhất cho mọi triển khai. Hãy xác minh giới hạn cấu hình của gRPC client/server, proxy và hạ tầng cụ thể. Đừng dựa vào mức trần tối đa của transport như ngân sách baggage được khuyến nghị.

## 11. Baggage, cardinality và metrics

Một lỗi thiết kế thường gặp là dùng baggage như nguồn tự động cho metric tags. Baggage có thể chứa giá trị biến đổi theo request; nếu chuyển thẳng mọi field sang metrics, nó có thể gây cardinality bùng nổ.

| Field | Baggage? | Metric low-cardinality tag? | Ghi chú |
| --- | --- | --- | --- |
| region=ap-southeast-1 | Có thể | Có thể nếu số vùng được kiểm soát | Chỉ thêm khi giúp phân tích. |
| request.class=interactive | Có thể | Thường phù hợp | Tập giá trị hữu hạn. |
| tenant.tier=standard | Có thể theo policy | Có thể nếu chỉ có vài tier | Không gửi tenant ID. |
| request.id=UUID | Chỉ khi có yêu cầu correlation đặc biệt | Không | Dùng logs hoặc trace attributes theo policy. |
| user.email=... | Không | Không | Dữ liệu cá nhân. |
| authorization=Bearer ... | Tuyệt đối không | Tuyệt đối không | Bí mật xác thực. |

Với Micrometer Observation, tags có thể được chia thành low-cardinality và high-cardinality key-values. Không tự động copy toàn bộ baggage vào low-cardinality tags. Nếu cần dùng một baggage field trong metrics, hãy ánh xạ **chỉ field đã được allowlist và có số lượng giá trị hữu hạn**.

Baggage cũng không thay thế service/resource attributes. service.name mô tả dịch vụ; region có thể mô tả request nếu thực sự là metadata của request, nhưng cần tránh nhầm với deployment region của process.

## 12. Bảo mật và quyền tin cậy

gRPC metadata là dữ liệu do caller có thể gửi. Baggage inbound cần được coi là **untrusted input** cho đến khi được validate và policy chấp nhận.

Ví dụ nguy cơ:

1. Client gửi tenant.tier=premium để cố làm log hoặc dashboard hiểu nhầm request thuộc nhóm được ưu tiên.
2. Một field dài hoặc nhiều field làm metadata phình to và tăng tải.
3. Dữ liệu nhạy cảm được propagate tới dịch vụ thứ ba hoặc backend tracing.
4. Baggage được log ở nhiều dịch vụ, tạo thêm bản sao dữ liệu.
5. Một field có cardinality cao được dùng làm metric tag và làm tăng series.

Biện pháp xử lý:

- Xác thực gRPC caller trước khi tin metadata ảnh hưởng policy.
- Tạo/ghi đè baggage tại gateway hoặc dịch vụ tin cậy nếu cần metadata đã xác minh.
- Chỉ cho phép keys đã đăng ký, giới hạn value length và charset.
- Không dùng baggage thay authorization, tenant isolation hoặc kiểm tra quyền.
- Dùng TLS/mTLS cho gRPC khi đi qua network cần bảo vệ.
- Không log toàn bộ metadata, vì có thể bao gồm thông tin xác thực hoặc dữ liệu không dành cho logs.
- Rà soát Collector processors và trace backend để bảo đảm attributes được lưu theo chính sách.

Một tenant.tier do caller gửi không phải bằng chứng caller có quyền dùng tier đó. Nếu giá trị ảnh hưởng nghiệp vụ, phải lấy từ danh tính/claim đã xác thực hoặc dữ liệu phía server, không tin trực tiếp baggage.

## 13. Lỗi thường gặp khi truyền baggage qua gRPC

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Trace ID tới server nhưng baggage trống | Chỉ bật Trace Context propagator, thiếu W3C Baggage propagator hoặc field không nằm trong remote allowlist. | Kiểm tra composite propagator, Micrometer baggage config và metadata baggage. |
| Baggage có trong client context nhưng không có metadata | gRPC client interceptor chưa được gắn hoặc dùng OpenTelemetry instance khác. | Kiểm tra channel builder/interceptor và shared SDK. |
| Metadata có baggage nhưng server không đọc được | Server interceptor chưa extract, getter/propagator sai hoặc handler không chạy trong extracted context. | Kiểm tra server instrumentation/context. |
| HTTP propagation hoạt động nhưng gRPC không | HTTP instrumented nhưng gRPC chưa cài client/server instrumentation. | Gắn gRPC interceptors và kiểm tra carrier metadata. |
| gRPC trả lỗi metadata quá lớn | Quá nhiều field hoặc values quá dài; proxy/server giới hạn nhỏ hơn. | Giảm field/length, không dùng baggage cho payload. |
| Một số field bị mất sau nhiều hop | Service trung gian không propagate field hoặc allowlist khác nhau. | So sánh remote-fields và propagators ở từng service. |
| Logs không có baggage | Correlation fields chưa cấu hình hoặc logging context không active. | Kiểm tra MDC/correlation config; baggage không tự luôn thành log field. |
| Metrics có quá nhiều series | Baggage được copy thành metric tags với giá trị biến đổi. | Gỡ high-cardinality tags, chỉ ánh xạ field hữu hạn. |
| Traces chứa token/email | Baggage hoặc metadata bị ghi vào span/log không lọc. | Xóa nguồn dữ liệu, thêm allowlist/filter và rà soát retention/access. |
| Hai service có trace ID khác nhau | Trace context propagation bị đứt dù baggage có thể còn hoặc ngược lại. | Kiểm tra traceparent/propagator riêng với baggage. |

**Trace context và baggage có thể thất bại riêng biệt.** Một request có thể giữ cùng trace ID nhưng mất baggage, hoặc baggage được chuyển tiếp qua custom interceptor trong khi trace context bị tách. Kiểm tra cả hai loại metadata, không chỉ nhìn một trace ID.

## 14. Quy trình kiểm chứng end-to-end

Một bài kiểm thử phù hợp nên thực hiện trong environment cục bộ hoặc integration test có thể kiểm soát:

1. Cấu hình Spring Boot và OTel bridge/propagator dùng W3C Trace Context + Baggage.
2. Khai báo một vài remote baggage fields, ví dụ region và request class.
3. Tạo baggage context có region=ap-southeast-1 trước khi gọi một gRPC method.
4. Gắn gRPC client interceptor dùng cùng OpenTelemetry instance với ứng dụng.
5. Gắn server interceptor tương ứng trên server nhận RPC.
6. Trong handler, đọc baggage từ current OTel context và kiểm tra giá trị đúng.
7. Trong Collector/backend, xác nhận client/server spans liên kết theo trace ID và metadata được xử lý theo policy.
8. Kiểm tra logs có trace correlation fields; chỉ kiểm tra baggage trong log khi correlation fields đã được cấu hình.
9. Gửi request không có baggage để xác nhận code có fallback và không ném lỗi.
10. Gửi field không nằm trong allowlist hoặc value vượt giới hạn để xác minh policy từ chối/loại bỏ đúng cách.
11. Kiểm tra metrics không tự phát sinh series theo request ID hoặc tenant ID.
12. Ghi nhận kích thước metadata và các lỗi gRPC trong lúc thử tải.

### Kiểm thử trường hợp không có baggage

Không nên viết code giả định region luôn tồn tại:

~~~java
Baggage baggage = Baggage.fromContext(Context.current());
String region = baggage.getEntryValue("region");

if (region == null || region.isBlank()) {
    region = "unknown";
}
~~~

unknown chỉ là fallback minh họa cho logging/diagnostics; không dùng nó để thay quyết định phân vùng hoặc authorization. Nếu service không yêu cầu region, tốt hơn là để field vắng mặt thay vì tự tạo giá trị giả.

## 15. Gắn correlation vào logs và traces

Baggage có thể giúp thêm metadata liên quan đến request trong logs hoặc spans nếu cấu hình cho phép. Ví dụ log:

~~~text
INFO inventory-service traceId=4f17c38a927d4b55a90714b02f8e6d19 spanId=3a9c31cdb4dcbd74 region=ap-southeast-1 request.class=interactive reserved stock
~~~

Các giá trị trace ID và span ID thường đến từ tracing/MDC integration. Region và request class chỉ có mặt nếu baggage correlation được bật hoặc ứng dụng ghi vào log. Không giả định mọi baggage fields tự động được đưa vào MDC.

Dùng traces để xem parent/child spans và dependency time; dùng logs để xem thông điệp cụ thể; dùng metrics để đánh giá xu hướng tổng hợp. Baggage hỗ trợ liên kết ngữ cảnh giữa các tín hiệu nhưng không phải nguồn thống kê. Ví dụ, dùng request class làm dimension metrics chỉ khi tập giá trị hữu hạn, được kiểm soát và có ý nghĩa phân tích.

## 16. Bài tập tự kiểm tra

### Bài 1 — Chọn metadata đúng

Một gRPC call cần truyền ba thông tin: trace context, region=ap-southeast-1 và protobuf field quantity=5. Nên đặt chúng ở đâu?

**Đáp án:** Trace context được truyền bằng metadata như traceparent/tracestate; region có thể là W3C baggage qua metadata key baggage nếu được cho phép; quantity là dữ liệu nghiệp vụ nên nằm trong protobuf request message.

### Bài 2 — Baggage bị mất nhưng trace còn

Service A gọi B qua gRPC; backend cho thấy cùng trace ID nhưng server B không đọc được region. Điều gì cần kiểm tra?

**Đáp án:** Kiểm tra W3C Baggage propagator có được bật cùng Trace Context không, region có nằm trong remote fields không, client/server gRPC interceptors có dùng cùng OpenTelemetry context và server handler có chạy trong context đã extract không.

### Bài 3 — Metadata quá lớn

Một nhóm đưa 80 trường thông tin user/request vào baggage để mọi service đều có thể đọc. Đây có phải thiết kế phù hợp?

**Đáp án:** Không. Baggage không phải payload context tổng quát. Chỉ giữ metadata nhỏ, allowlist và thực sự cần xuyên dịch vụ; dữ liệu nghiệp vụ nằm trong request message, dữ liệu điều tra riêng nằm trong logs/traces theo chính sách phù hợp.

### Bài 4 — Baggage và quyền truy cập

Caller gửi tenant.tier=premium trong baggage. Service B có nên cho phép request dùng tính năng premium dựa vào field đó không?

**Đáp án:** Không. Baggage là input có thể do caller kiểm soát, không phải chứng cứ quyền. Service phải xác minh identity/claims và policy từ nguồn đáng tin cậy.

### Bài 5 — Baggage có phải metric tag?

Một nhóm muốn gắn UUID request vào baggage rồi dùng UUID đó làm low-cardinality metric tag. Vấn đề là gì?

**Đáp án:** UUID gần như duy nhất mỗi request, tạo high cardinality. Không dùng nó làm metric label. Dùng logs hoặc trace attributes có kiểm soát để điều tra từng request.

### Bài 6 — ASCII hay binary metadata?

Một field W3C baggage text được tạo bằng Metadata.ASCII_STRING_MARSHALLER hay Metadata.BINARY_BYTE_MARSHALLER?

**Đáp án:** W3C baggage là text nên dùng ASCII metadata key baggage. Binary metadata dùng key có hậu tố -bin và marshaller dạng bytes; không dùng binary marshaller cho field text W3C.

## 17. Checklist triển khai

- [ ] Phân biệt trace context, baggage, custom gRPC metadata và protobuf payload.
- [ ] Chỉ đưa baggage fields đã allowlist vào remote propagation.
- [ ] W3C Baggage propagator được bật cùng Trace Context trong OpenTelemetry instance đang sử dụng.
- [ ] gRPC client/server instrumentation dùng chung tracing context với Spring Boot.
- [ ] W3C baggage được truyền qua metadata ASCII key baggage; binary keys dùng -bin khi thực sự cần.
- [ ] Metadata có số field và tổng kích thước được giới hạn theo hạ tầng.
- [ ] Không có secrets, credentials, email, request body hoặc dữ liệu nhạy cảm trong baggage.
- [ ] Inbound baggage được xem là untrusted và không dùng để cấp quyền.
- [ ] Async/reactive execution giữ context đúng lifecycle.
- [ ] Logs chỉ thêm baggage correlation fields khi đã cấu hình và có policy.
- [ ] Metrics không copy baggage high-cardinality thành labels.
- [ ] Integration test xác minh client inject, server extract, handler đọc và trace parentage đúng.
- [ ] Test cả trường hợp baggage thiếu, field không được phép và metadata quá lớn.
- [ ] Collector/backend có giới hạn, retention và access control phù hợp cho span attributes.

**Ghi nhớ:** Trong gRPC, **Metadata là carrier**, còn **W3C Baggage là định dạng context metadata** cần được propagator serialize/extract. Hãy dùng gRPC instrumentation và OpenTelemetry propagator phù hợp để đưa baggage qua client/server interceptors; giới hạn trường được truyền, kích thước và dữ liệu nhạy cảm. Khi kết hợp đúng với Micrometer Tracing, metrics và logs, baggage giúp các dịch vụ giữ chung ngữ cảnh correlation mà không biến metadata thành payload hay kênh xác thực.
