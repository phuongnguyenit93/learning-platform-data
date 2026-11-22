# Application Performance Monitoring và distributed tracing

Trong chương **Logs, metrics và tracing**, Application Performance Monitoring (APM) giúp đi từ dấu hiệu “ứng dụng chậm” đến một request cụ thể: request đi qua dịch vụ nào, mất thời gian ở bước nào và lỗi xuất hiện ở đâu. Với Oracle Cloud Infrastructure (OCI), dữ liệu này được gửi về một APM domain để tìm kiếm và phân tích.

Bài học đặt tracing vào bối cảnh vận hành OCI: tài nguyên thuộc compartment, người đọc dữ liệu có quyền IAM phù hợp, ứng dụng có đường mạng đến endpoint thu thập, và lượng telemetry nằm trong ngân sách. Lab sử dụng hai tiến trình Java để tạo một trace xuyên dịch vụ; phần triển khai thực tế liên hệ với Compute, OKE và các ứng dụng truy cập cơ sở dữ liệu Oracle.

Sau bài học, người học có thể:

- Phân biệt trace, span, parent span và context propagation.
- Chọn cách instrument ứng dụng Java và gửi trace đến OCI APM.
- Đọc một trace để phân biệt thời gian xử lý, thời gian chờ và lỗi downstream.
- Kết hợp trace với log, metric; đặt sampling và giám sát đường thu thập dữ liệu.

## 1. APM trả lời câu hỏi nào?

Giả sử API đặt hàng chạy trên OCI Compute hoặc OKE:

~~~text
Người dùng → checkout-service → inventory-service → Oracle Database
                           └→ payment-service → cổng thanh toán
~~~

Một cảnh báo cho biết độ trễ p95 tăng. CPU của máy vẫn thấp; log từng dịch vụ đều có những dòng “request completed”. Thông tin còn thiếu là **quan hệ giữa các thao tác trong cùng một request**.

| Tín hiệu | Câu hỏi thường giải quyết | Ví dụ trong luồng đặt hàng |
| --- | --- | --- |
| Metric | Vấn đề xảy ra từ lúc nào, trên phạm vi nào? | Tỷ lệ 5xx tăng trong 5 phút; p95 vượt mục tiêu |
| Log | Một thời điểm đã xảy ra sự kiện gì? | Kết nối bị timeout; validation từ chối yêu cầu |
| Trace | Request đi qua đâu, các bước liên hệ thế nào? | Checkout chờ inventory, inventory chờ JDBC |
| Profile hoặc dữ liệu JVM chuyên sâu | CPU, bộ nhớ hoặc thread đang tiêu tốn vào đâu? | Một vòng lặp tính phí chiếm CPU |

Trace cung cấp bằng chứng để khoanh vùng. Một JDBC span dài gợi ý phần gọi cơ sở dữ liệu cần được điều tra; muốn kết luận về execution plan hoặc lock trong Oracle Database, vẫn cần dữ liệu phía cơ sở dữ liệu.

OCI APM hỗ trợ quan sát ứng dụng bằng nhiều nguồn dữ liệu, gồm Java agent, browser agent, tracer và synthetic monitor. Browser agent phản ánh phiên tương tác thực; synthetic monitor chủ động chạy kiểm tra theo lịch. Hai cách nhìn bổ sung cho trace phía máy chủ. Tham khảo [các nguồn dữ liệu của OCI APM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-data-sources.html).

## 2. Trace, span và quan hệ nhân quả

### 2.1. Một trace gồm nhiều span

**Trace** biểu diễn hành trình của một request hoặc một công việc phân tán. **Span** biểu diễn một thao tác có thời điểm bắt đầu, kết thúc và ngữ cảnh.

Các trường cốt lõi:

| Thành phần | Ý nghĩa |
| --- | --- |
| Trace ID | Định danh chung của các span trong một trace |
| Span ID | Định danh của một span |
| Parent span ID | Span đã tạo ra thao tác hiện tại; root span không có parent |
| Name | Tên thao tác, nên ổn định như `POST /checkout` |
| Kind | Vai trò như `SERVER`, `CLIENT`, `INTERNAL`, `PRODUCER`, `CONSUMER` |
| Attributes | Cặp khóa–giá trị mô tả thao tác |
| Events, status | Sự kiện có timestamp và trạng thái thao tác |

Tên span nên mô tả loại thao tác; đưa mã đơn hàng vào tên sẽ tạo rất nhiều tên khác nhau. Cấu trúc trace được mô tả trong [OpenTelemetry Traces](https://opentelemetry.io/docs/concepts/signals/traces/).

Ví dụ cây span do một ứng dụng có thể tạo:

~~~text
checkout: SERVER POST /checkout
├── checkout: INTERNAL validate-order
├── checkout: CLIENT GET inventory/stock
│   └── inventory: SERVER GET /stock
│       └── inventory: CLIENT SELECT stock...
└── checkout: CLIENT POST payment/authorize
    └── payment: SERVER POST /authorize
~~~

Span client và span server của cùng một lần gọi là hai phép đo ở hai phía. Chúng chia sẻ trace, nhưng có Span ID khác nhau. Ứng dụng chỉ tạo được các nhánh có instrumentation; việc triển khai database hoặc load balancer không tự làm xuất hiện đầy đủ span tương ứng.

### 2.2. Context phải đi qua ranh giới dịch vụ

Khi A gọi B, instrumentation phía A inject context vào request; B extract context rồi tạo span con. Nếu header bị loại bỏ hoặc thư viện không được instrument, B có thể tạo một trace mới. Hai dịch vụ vẫn có dữ liệu, nhưng hành trình bị đứt.

Cùng vấn đề có thể xảy ra ở executor, callback hoặc message broker. Cần chuyển context qua ranh giới thực thi, rồi đóng scope đúng lúc để tránh gắn nhầm request. Xem [OpenTelemetry Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/).

W3C Trace Context định nghĩa header `traceparent`. Với định dạng phiên bản `00`:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

- `00`: phiên bản.
- Nhóm 32 ký tự hex: Trace ID.
- Nhóm 16 ký tự hex: parent ID của thao tác gửi context.
- `01`: sampled flag được bật.

`tracestate` mang trạng thái bổ sung dành cho hệ thống tracing. Sampled flag truyền quyết định lấy mẫu; nó không bảo đảm mọi span đã được backend lưu thành công. Context do bên ngoài gửi đến cũng không phải bằng chứng xác thực người dùng. Chi tiết định dạng nằm trong [W3C Trace Context](https://www.w3.org/TR/trace-context/).

Trong một hệ thống có nhiều loại agent, cần thống nhất propagator. Nếu browser dùng B3 còn backend chỉ đọc W3C, phải cấu hình tương thích tại ranh giới đó; không suy luận rằng mọi agent có cùng mặc định.

### 2.3. Công việc bất đồng bộ cần cách diễn giải riêng

Request HTTP có thể trả về trước khi consumer xử lý xong message. Khi đó, latency phía người dùng và thời gian hoàn tất nghiệp vụ là hai đại lượng khác nhau. Lưu cả timestamp phát message, thời gian chờ và thời gian xử lý nếu cần đánh giá toàn bộ quy trình.

Khi một thao tác có nhiều nguồn kích hoạt, mô hình OpenTelemetry có thể sử dụng span links. Tuy nhiên, tài liệu endpoint OpenTelemetry của OCI APM hiện nêu **span links chưa được hỗ trợ**. Vì vậy, cần kiểm tra khả năng backend trước khi thiết kế cách điều tra dựa vào links; bài lab sử dụng quan hệ parent–child qua HTTP. Xem [cấu hình OpenTelemetry cho OCI APM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-opentelemetry.html).

## 3. Các thành phần OCI phải chuẩn bị

### 3.1. APM domain, compartment và region

APM domain là tài nguyên tập hợp dữ liệu giám sát ứng dụng. Domain này khác với IAM identity domain dùng quản lý danh tính.

Ví dụ bố trí cho bài thực hành:

~~~text
Tenancy
└── Compartment ObservabilityLab
    ├── APM domain oci-java-tracing-lab
    └── Compute instance chạy hai tiến trình Java
~~~

Chọn region trước khi tạo domain và giữ region đó khi mở Trace Explorer. Trong Console, đi đến **Observability & Management → Application Performance Monitoring → Administration**, chọn compartment rồi tạo APM domain. Chờ tài nguyên sẵn sàng trước khi lấy endpoint.

Oracle cung cấp lựa chọn Free Tier hoặc paid domain khi tạo. Hãy đọc lựa chọn thực tế, giới hạn và thời gian lưu dữ liệu được công bố cho loại domain định dùng; không coi thao tác tạo domain là mặc định miễn phí. Xem [Create an APM Domain](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/create-apm-domain.html).

### 3.2. IAM cho người quản trị và người phân tích

Ví dụ policy cho identity domain `Default` và compartment `ObservabilityLab`:

~~~text
Allow group Default/ApmAdmins to manage apm-domains in compartment ObservabilityLab
Allow group Default/ApmReaders to read apm-domains in compartment ObservabilityLab
~~~

Thay identity domain, group và compartment bằng tên thực; đặt policy ở phạm vi có thể cấp quyền cho compartment đó.

Nhóm quản trị tạo và quản lý domain; nhóm phân tích đọc trace. Với resource type `apm-domains`, quyền `use` còn bao gồm các thao tác quản lý data key, nên không cấp quyền này chỉ để giải quyết nhu cầu xem dữ liệu. Bảng quyền chi tiết nằm tại [OCI APM policy reference](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/apmpolicyreference.htm).

Nếu cần đọc metric trong Metrics Explorer, phải có quyền Monitoring tương ứng, ví dụ:

~~~text
Allow group Default/ApmReaders to read metrics in compartment ObservabilityLab
~~~

Quyền tạo alarm, dùng Notifications và quản lý dashboard là các nhu cầu bổ sung. Xem [các quyền chuẩn bị cho APM](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/perform-oracle-cloud-infrastructure-prerequisite-tasks.html).

### 3.3. Endpoint và data key

Từ trang chi tiết domain, lấy:

- **Data Upload Endpoint**: địa chỉ nhận observations của domain.
- **Private Data Key**: dùng cho đường gửi dữ liệu phía server trong bài này.
- **Public Data Key**: dùng cho browser agent theo mô hình triển khai tương ứng.

Mỗi domain có endpoint và data key riêng. Data key phục vụ ingestion; nó không thay thế danh tính IAM để mở Console hoặc truy vấn dữ liệu. Cách lấy các giá trị được mô tả trong [Obtain Data Upload Endpoint and Data Keys](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/obtain-data-upload-endpoint-and-data-keys.html).

Giữ private key trong cơ chế cấp secret của môi trường chạy; hạn chế người đọc và có kế hoạch thay key. Không nhúng private key vào JavaScript, image container công khai, repository hoặc log khởi động.

### 3.4. Đường mạng từ ứng dụng đến APM

Tách hai đường đi khi thiết kế mạng:

~~~mermaid
flowchart LR
    U["Request kiểm thử"] --> C["checkout-service"]
    C --> I["inventory-service"]
    C -. "HTTPS telemetry" .-> A["OCI APM domain"]
    I -. "HTTPS telemetry" .-> A
    R["Người vận hành + IAM"] --> T["Trace Explorer"]
    A --> T
~~~

Đối với upload endpoint công khai dùng trong lab:

1. Máy chạy Java phải phân giải được DNS và kết nối HTTPS đến endpoint.
2. Private subnet cần đường egress phù hợp, chẳng hạn NAT Gateway đến Internet hoặc proxy được tổ chức cho phép.
3. Route table, NSG/security list và firewall hệ điều hành phải cho phép lưu lượng cần thiết.
4. Trust store JVM phải tin cậy chuỗi chứng thư; kiểm tra cấu hình TLS inspection nếu có proxy.
5. Không mở inbound từ Internet vào ứng dụng chỉ để agent gửi telemetry.

Service Gateway không phải tuyến thay thế chung cho mọi hostname OCI. Chọn tuyến dựa trên endpoint và dịch vụ thực sự được hỗ trợ. Khi chuyển lab sang OKE, kiểm tra thêm network policy và đường egress từ pod.

## 4. Chọn một đường instrumentation

| Phương án | Phù hợp khi | Việc cần quản lý |
| --- | --- | --- |
| Oracle APM Java Agent | Muốn dùng bộ instrumentation và cấu hình agent của Oracle | Bộ cài, môi trường Java được hỗ trợ, phiên bản và cấu hình agent |
| OpenTelemetry Java Agent | Muốn instrument Java theo hệ sinh thái OpenTelemetry và xuất OTLP | Tương thích thư viện, exporter, propagator, sampling |
| Instrumentation thủ công bằng API | Cần span nghiệp vụ mà auto instrumentation chưa mô tả được | Vòng đời span, context và attributes |
| OpenTelemetry Collector | Cần tập trung routing, filtering hoặc xử lý trước khi gửi backend | Tài nguyên Collector, queue, secret, tính sẵn sàng |

Collector là thành phần của pipeline; nó không tự thêm span vào mã Java chưa được instrument.

Lab chọn **OpenTelemetry Java Agent → OCI APM qua OTLP/HTTP**, không cần Collector. Agent hỗ trợ Java HTTP Server và Java HTTP Client được sử dụng bên dưới; đối với ứng dụng riêng, đối chiếu đúng thư viện và phiên bản trong [danh sách hỗ trợ của OpenTelemetry Java instrumentation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/docs/supported-libraries.md).

Mỗi JVM trong lab chỉ gắn một tracing agent. Khi ứng dụng đã có SDK hoặc starter observability, cần xác định thành phần nào khởi tạo SDK để tránh tạo span trùng và xuất dữ liệu hai lần.

## 5. Lab: gửi distributed trace từ hai tiến trình Java về OCI APM

### 5.1. Mục tiêu và điều kiện

Luồng thực hành:

~~~text
curl → checkout-service :8080 → inventory-service :8081
          SERVER span          SERVER span
                 └ CLIENT span ──────┘
~~~

Hai tiến trình dùng cùng APM domain nhưng có `service.name` khác nhau. Khi instrumentation và propagation hoạt động, một lần gọi checkout tạo được trace chứa các thao tác của cả hai dịch vụ.

Chuẩn bị:

- Một máy Linux hoặc OCI Compute có Bash, `curl` và JDK 17 phù hợp với phiên bản agent đã chọn.
- APM domain sẵn sàng; đã lấy Data Upload Endpoint và Private Data Key.
- Quyền đọc trace, cùng kết nối HTTPS outbound từ máy thực hành.
- File `opentelemetry-javaagent.jar` từ bản phát hành chính thức, đặt trong thư mục thực hành.

Lấy agent theo [OpenTelemetry Java Agent Getting started](https://opentelemetry.io/docs/zero-code/java/agent/getting-started/). Ghi lại phiên bản dùng trong lab để lần triển khai sau tái lập được cấu hình.

Các lệnh dưới đây là hướng dẫn chạy trên máy thực hành Linux. Hai dịch vụ bind vào loopback và mô phỏng kho hàng bằng bộ nhớ; lab không tạo cơ sở dữ liệu hoặc tài nguyên OCI tự động.

### 5.2. Mã ứng dụng

Tạo `Demo.java` trong thư mục thực hành:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.Executors;

public class Demo {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

    public static void main(String[] args) throws IOException {
        if (args.length != 1
                || !(args[0].equals("inventory") || args[0].equals("checkout"))) {
            throw new IllegalArgumentException(
                    "Usage: java Demo inventory|checkout");
        }

        boolean inventory = args[0].equals("inventory");
        int port = inventory ? 8081 : 8080;
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", port), 0);

        server.setExecutor(Executors.newFixedThreadPool(8));
        if (inventory) {
            server.createContext("/stock", Demo::stock);
        } else {
            server.createContext("/checkout", Demo::checkout);
        }

        server.start();
        System.out.println(args[0] + " listening on 127.0.0.1:" + port);
    }

    private static void stock(HttpExchange exchange) throws IOException {
        String traceparent = exchange.getRequestHeaders()
                .getFirst("traceparent");
        System.out.println("inventory received traceparent=" + traceparent);

        long delayMs = Long.parseLong(
                System.getenv().getOrDefault("STOCK_DELAY_MS", "50"));

        try {
            Thread.sleep(delayMs);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            respond(exchange, 503, "inventory interrupted");
            return;
        }

        boolean fail = Boolean.parseBoolean(
                System.getenv().getOrDefault("STOCK_FAIL", "false"));
        respond(exchange, fail ? 503 : 200,
                fail ? "inventory unavailable" : "stock available");
    }

    private static void checkout(HttpExchange exchange) throws IOException {
        int responseStatus;
        String responseBody;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:8081/stock"))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        try {
            HttpResponse<String> response = CLIENT.send(
                    request, HttpResponse.BodyHandlers.ofString());
            responseStatus = response.statusCode() >= 500 ? 502 : 200;
            responseBody = "inventory status=" + response.statusCode();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            responseStatus = 502;
            responseBody = "checkout interrupted";
        } catch (IOException exception) {
            responseStatus = 502;
            responseBody = "inventory request failed";
        }

        respond(exchange, responseStatus, responseBody);
    }

    private static void respond(
            HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders()
                .set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }
}
~~~

Biên dịch:

~~~bash
javac --add-modules jdk.httpserver Demo.java
~~~

Mã không tự inject `traceparent` và không gọi API tracing. Agent sẽ instrument HTTP server/client. Dòng in header ở inventory là điểm quan sát đơn giản; nó chưa phải cơ chế gắn Trace ID và Span ID đầy đủ vào log production.

### 5.3. Cấu hình exporter

Trong **mỗi terminal chạy dịch vụ**, thực hiện khối cấu hình sau. Thay `APM_UPLOAD_BASE` bằng Data Upload Endpoint thực, có `https://` và không có dấu `/` cuối:

~~~bash
export APM_UPLOAD_BASE='https://<data-upload-endpoint-host>'

read -r -s -p 'Private Data Key: ' apm_private_data_key
printf '\n'
export OTEL_EXPORTER_OTLP_TRACES_HEADERS="authorization=dataKey $apm_private_data_key"
unset apm_private_data_key

export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="$APM_UPLOAD_BASE/20200101/opentelemetry/private/v1/traces"

export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export OTEL_PROPAGATORS=tracecontext
export OTEL_TRACES_SAMPLER=parentbased_always_on
export OTEL_RESOURCE_ATTRIBUTES='deployment.environment.name=lab,service.version=1.0.0'
~~~

OCI APM nhận trace trên đường dẫn private OTLP với header `Authorization: dataKey ...`. Đây là cấu hình traces; hai exporter còn lại được tắt để giữ lab tập trung vào tracing. Xem [ví dụ OpenTelemetry Java agent của Oracle](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/configure-opentelemetry.html).

Các điểm dễ nhầm:

- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` là URL riêng cho traces; cung cấp đầy đủ path một lần.
- `OTEL_EXPORTER_OTLP_ENDPOINT` là cấu hình endpoint chung; với OTLP/HTTP, exporter có cơ chế tạo URL cho từng signal. Không đổi qua lại hai biến mà giữ nguyên giả định về suffix. Xem [OTLP exporter configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/).
- Agent có thể nhận system properties, biến môi trường hoặc file cấu hình; system properties có độ ưu tiên cao hơn biến môi trường. Khi chạy trong container hoặc service manager, kiểm tra tham số JVM thực nhận. Xem [Java agent configuration](https://opentelemetry.io/docs/zero-code/java/agent/configuration/).

Khối lệnh dùng nhập key ẩn để tránh gõ key trực tiếp vào shell history. Giá trị sau đó vẫn tồn tại trong environment của tiến trình; môi trường production cần cơ chế secret và phân quyền tiến trình phù hợp.

`parentbased_always_on` thuận tiện cho lưu lượng nhỏ của lab: root request được lấy mẫu, span con kế thừa quyết định từ parent. Không mặc định áp dụng tỷ lệ này cho toàn bộ production.

### 5.4. Chạy inventory và checkout

Terminal 1, sau khối cấu hình exporter:

~~~bash
OTEL_SERVICE_NAME=inventory-service \
STOCK_DELAY_MS=50 \
STOCK_FAIL=false \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo inventory
~~~

Terminal 2, cũng đã có khối cấu hình exporter:

~~~bash
OTEL_SERVICE_NAME=checkout-service \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo checkout
~~~

Terminal 3 gửi lưu lượng:

~~~bash
for i in {1..10}; do
  curl -sS -o /dev/null \
    -w 'http=%{http_code} total=%{time_total}s\n' \
    http://127.0.0.1:8080/checkout
  sleep 0.2
done
~~~

Đầu ra mong đợi:

- HTTP status từ checkout là `200` khi inventory hoạt động bình thường.
- Terminal inventory thấy `traceparent` với giá trị hợp lệ.
- Sau khi exporter gửi batch và backend xử lý, Trace Explorer có dữ liệu của hai service.

Không yêu cầu latency chính xác bằng 50 ms: thời gian khởi động JVM, warm-up, instrumentation và lập lịch cũng ảnh hưởng. Nếu ứng dụng chạy được nhưng chưa thấy trace, kiểm tra log exporter và pipeline trước khi thay đổi mã nghiệp vụ.

### 5.5. Tạo một request chậm

Dừng riêng inventory bằng `Ctrl+C`. Giữ cấu hình exporter trong terminal đó và khởi động lại:

~~~bash
OTEL_SERVICE_NAME=inventory-service \
STOCK_DELAY_MS=800 \
STOCK_FAIL=false \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo inventory
~~~

Chạy lại vòng curl. Khoảng thời gian bổ sung phải thể hiện ở inventory server span và khoảng checkout chờ lời gọi inventory. Đây là độ trễ giả lập bằng sleep, nên nó minh họa thời gian chờ; không chứng minh inventory tiêu tốn nhiều CPU.

### 5.6. Tạo lỗi downstream

Dừng inventory và chạy lại với:

~~~bash
OTEL_SERVICE_NAME=inventory-service \
STOCK_DELAY_MS=50 \
STOCK_FAIL=true \
java --add-modules jdk.httpserver \
  -javaagent:./opentelemetry-javaagent.jar \
  -cp . Demo inventory
~~~

Lần gọi tiếp theo trả `503` tại inventory và `502` tại checkout. Quan sát HTTP status và error status trên các span tương ứng. Số span lỗi có thể nhiều hơn số request lỗi vì cùng một sự cố được ghi nhận tại nhiều tầng.

Sau thử nghiệm, đưa `STOCK_FAIL=false` và `STOCK_DELAY_MS=50` để tạo lại luồng thành công. Một trace thành công sau thay đổi là bằng chứng khôi phục cho request đó; cần metric trên một khoảng thời gian để đánh giá toàn bộ lưu lượng.

### 5.7. Tìm trace trong OCI

Mở **Application Performance Monitoring → Trace Explorer**, chọn đúng region, compartment, APM domain và khoảng thời gian vừa chạy lab. Trace Explorer cho phép tìm, lọc và mở chi tiết traces/spans; xem [Monitor Traces in Trace Explorer](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/monitor-traces-trace-explorer.html).

Tìm các checkout trace có thời gian dài nhất:

~~~sql
show (traces)
  TraceId,
  ServiceName,
  OperationName,
  TraceDuration,
  ErrorCount
where ServiceName = 'checkout-service'
order by TraceDuration desc
first 20 rows
~~~

Lấy Trace ID từ một kết quả rồi xem các span của trace đó:

~~~sql
show (spans)
  TraceId,
  SpanId,
  ServiceName,
  OperationName,
  SpanDuration
where TraceId = '<trace-id-tu-ket-qua>'
order by SpanDuration desc
first 50 rows
~~~

Đây là ngôn ngữ truy vấn của Trace Explorer; không chạy hai đoạn này trên Oracle Database. Giá trị trong bộ lọc phải khớp dữ liệu thực. Sử dụng query assist hoặc xem attributes của span khi cần xác định dimension đã được ingestion. Cú pháp và các clause được mô tả tại [Work with Queries in Trace Explorer](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/work-queries-trace-explorer.html).

Mở chi tiết trace để xác minh:

1. Có span phía checkout và inventory trong cùng Trace ID.
2. Span client của checkout là parent của server span inventory.
3. Kịch bản chậm có thời gian tăng ở nhánh inventory.
4. Kịch bản lỗi cho thấy status tương ứng ở hai phía.
5. Không xuất hiện hai bộ span tương đương do gắn hai agent.

Tên operation, số lượng span bổ sung và cách hiển thị attributes có thể thay đổi theo phiên bản instrumentation. Tiêu chí chính là quan hệ parent–child và hành vi đã chủ động tạo.

## 6. Đọc waterfall để khoanh vùng vấn đề

### 6.1. Thời gian lồng nhau không cộng trực tiếp

Giả sử quan sát được số liệu minh họa:

| Span | Bắt đầu tương đối | Duration |
| --- | ---: | ---: |
| Checkout server | 0 ms | 910 ms |
| Checkout gọi inventory | 40 ms | 850 ms |
| Inventory server | 55 ms | 810 ms |

Không cộng `910 + 850 + 810` để tính latency request. Hai span phía dưới nằm trong khoảng hoạt động của span phía trên. Phần lớn thời gian checkout đang chờ inventory.

Chênh lệch giữa span client và span server có thể gồm kết nối, truyền dữ liệu, proxy, queue ở một số vị trí và chi phí xử lý bên ngoài phạm vi server span. Không gán toàn bộ phần chênh lệch cho network khi chưa có bằng chứng.

### 6.2. Theo đường quyết định thời điểm hoàn tất

Nếu checkout gọi inventory và payment song song, latency của request phụ thuộc nhánh kết thúc muộn cần thiết cho response cùng các bước tuần tự khác. Cộng duration của hai nhánh song song sẽ phóng đại thời gian người dùng chờ.

Khi điều tra:

1. Chọn trace chậm có cùng operation và điều kiện với trace bình thường.
2. So sánh cấu trúc nhánh, thời điểm bắt đầu và khoảng chờ.
3. Kiểm tra retry: có nhiều lời gọi nối tiếp đến cùng dependency hay không.
4. Kiểm tra khoảng trống chưa có span; đó có thể là công việc chưa được instrument.
5. Đối chiếu đồng hồ các máy nếu timeline lệch bất thường.

Span dài chỉ cho biết thao tác mất nhiều thời gian. Muốn phân biệt CPU, lock, connection pool hoặc I/O, lấy thêm metric JVM, pool và dữ liệu của dependency.

### 6.3. Trường hợp truy cập Oracle Database

Khi thêm JDBC vào inventory, Java instrumentation có thể tạo client span quanh truy vấn được hỗ trợ. Dùng nó để tìm lời gọi chậm, tần suất gọi và dấu hiệu N+1, sau đó đối chiếu dữ liệu từ Oracle Database.

Ba câu hỏi cần tách riêng:

- Ứng dụng có chờ lấy connection trước khi bắt đầu JDBC span không?
- Thời gian span bao gồm những bước nào của thư viện đang dùng?
- Phía database có CPU, I/O, lock hoặc execution plan bất thường không?

Một JDBC span không thay cho quan sát bên trong database. Đồng thời, cần rà soát cơ chế thu thập SQL để tránh đưa literal, bind value hoặc thông tin nghiệp vụ nhạy cảm vào telemetry.

## 7. Bổ sung span nghiệp vụ hoặc dùng Oracle APM Java Agent

### 7.1. Span nghiệp vụ có mục đích rõ ràng

Auto instrumentation thường mô tả HTTP, JDBC và các thư viện được hỗ trợ. Với bước như giữ tồn kho hoặc tính hạn mức, có thể cần span nghiệp vụ.

Đoạn mở rộng sau dành cho ứng dụng đã có dependency `io.opentelemetry:opentelemetry-api` phù hợp với bộ dependency đang dùng và chạy cùng OpenTelemetry Java Agent. Nó không phải phần bắt buộc để biên dịch `Demo.java` ở lab:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;

public final class BusinessTracing {
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("inventory-business");

    public static void reserve(Runnable action) {
        Span span = TRACER.spanBuilder("inventory.reserve").startSpan();

        try (Scope scope = span.makeCurrent()) {
            span.setAttribute("inventory.operation", "reserve");
            action.run();
        } catch (RuntimeException exception) {
            span.addEvent("reservation.failed");
            span.setStatus(StatusCode.ERROR, "reservation failed");
            throw exception;
        } finally {
            span.end();
        }
    }
}
~~~

`makeCurrent()` đặt span vào context hiện tại trong phạm vi scope; `end()` kết thúc phép đo dù thao tác thành công hay thất bại. Khi gọi từ HTTP handler đã được instrument, span mới kế thừa parent hiện tại. API riêng lẻ không tự cấu hình exporter. Xem [OpenTelemetry Java API](https://opentelemetry.io/docs/languages/java/api/).

Ví dụ chỉ ghi sự kiện lỗi trung tính. Nếu dùng `recordException`, kiểm soát nội dung exception vì message và stack trace có thể mang dữ liệu nhạy cảm. Khi công việc chuyển sang thread khác, cần truyền context cho thread thực thi thay vì giữ scope mở tùy ý trên thread cũ.

Ưu tiên span cho ranh giới nghiệp vụ có giá trị chẩn đoán. Tạo span cho mọi getter hoặc mỗi phần tử trong một vòng lặp lớn sẽ tăng overhead và lượng ingestion mà khó cải thiện việc điều tra.

### 7.2. Đường triển khai bằng Oracle APM Java Agent

Với hệ thống chọn agent của Oracle, tải bộ cài từ APM domain và kiểm tra môi trường được hỗ trợ. Ví dụ provisioning minh họa:

~~~bash
java -jar ./apm-java-agent-installer-<version>.jar provision-agent \
  -service-name=checkout-service \
  -destination=/opt/checkout \
  -private-data-key=<private-data-key> \
  -data-upload-endpoint=<data-upload-endpoint>
~~~

Đây là template; thay placeholders và cấp key qua quy trình triển khai bảo mật trước khi sử dụng. Bốn tham số xác định service, nơi cài agent, key và endpoint. Xem [Provision the APM Java Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/provision-apm-java-agent.html).

Sau provisioning, thêm agent vào lệnh khởi động JVM:

~~~bash
java \
  -javaagent:/opt/checkout/oracle-apm-agent/bootstrap/ApmAgent.jar \
  -jar checkout.jar
~~~

`checkout.jar` ở đây là ứng dụng đã đóng gói, không phải artifact của lab `Demo.java`. Với WebLogic, Tomcat, Spring Boot hoặc container, sửa đúng cấu hình khởi động và restart theo môi trường. Xem [Deploy the APM Java Agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/deploy-apm-java-agent.html).

Cấu hình `OTEL_*` ở lab không phải bộ tham số thay thế chung cho Oracle APM Java Agent. Oracle agent có các cơ chế sampling, abridging và circuit breaker riêng; đối chiếu [các tùy chọn thu thập của Oracle agent](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/introduction-apm-java-agent.html) khi vận hành đường này.

## 8. Liên kết trace với log, metric và cảnh báo

### 8.1. Log cần mang context thực tế

Định dạng log có thể bao gồm:

~~~json
{
  "timestamp": "2026-11-21T03:20:00Z",
  "level": "WARN",
  "service": "inventory-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "7a3f82c9d10e456b",
  "message": "inventory dependency unavailable"
}
~~~

Đây là dữ liệu minh họa. Ứng dụng phải lấy context của span hiện tại hoặc dùng cơ chế log correlation phù hợp với agent và logging framework. Trường `span_id` cần là span đang xử lý sự kiện, không phải chép nguyên parent ID từ header request.

Luồng điều tra thực tế có thể là:

~~~text
Alarm về lỗi hoặc latency
  → xác định service, operation và thời gian
  → tìm trace đại diện
  → lấy Trace ID
  → tìm log tương ứng trong OCI Logging hoặc hệ thống log đã cấu hình
  → đối chiếu metric dependency
~~~

Cài Java tracing agent không mặc nhiên thiết lập toàn bộ việc thu thập application log vào OCI Logging. Phải có pipeline log và cấu trúc field tương ứng. Một log vẫn có thể chứa Trace ID dù trace bị loại bởi sampling hoặc ingestion lỗi; vì vậy tìm không thấy trace không đồng nghĩa log không hợp lệ.

### 8.2. Dùng metric để đánh giá phạm vi ảnh hưởng

Một trace là một quan sát chi tiết. Để xác định mức độ ảnh hưởng, theo dõi:

- Request rate theo service và operation.
- Tỷ lệ lỗi ở ranh giới phục vụ người dùng.
- Phân phối latency, gồm p50, p95 hoặc p99 khi có dữ liệu phù hợp.
- Saturation như pool connection, thread pool, queue, CPU và bộ nhớ.

Ví dụ mục tiêu nội bộ của một API là “ít nhất 99% request hợp lệ hoàn thành dưới 1 giây”. Khi định nghĩa SLI, phải xác định request nào được tính, khoảng thời gian và nguồn dữ liệu. Không lấy số span lỗi chia cho tổng span để thay thế tỷ lệ request lỗi.

Nếu giữ ưu tiên trace chậm và trace lỗi, tập trace đã lưu không đại diện cho toàn bộ traffic. Tính tỷ lệ lỗi và percentile từ tập này có thể lệch. Ưu tiên metric phục vụ SLI được thu thập trên tập request xác định rõ, và dùng trace để giải thích những request cụ thể.

### 8.3. Quan sát cả đường ingestion

APM có metric tình trạng ingestion trong namespace `oci_apm`, gồm `SpanIngestions` và `PayloadRejections`. Rejection có thể gắn với nguyên nhân như data key không hợp lệ, payload quá lớn hoặc bị throttling. Xem [APM Metrics](https://docs.oracle.com/en-us/iaas/application-performance-monitoring/doc/application-performance-monitoring-metrics.html).

Thiết kế cảnh báo theo hành vi dự kiến:

| Dấu hiệu | Việc cần xác minh |
| --- | --- |
| Traffic ứng dụng ổn định nhưng span giảm mạnh | Agent, sampling, exporter và đường mạng |
| Span tăng nhanh sau release | Instrumentation trùng, retry, vòng lặp hoặc operation mới |
| Payload bị từ chối | Key, định dạng, kích thước và giới hạn ingestion |
| Không có dữ liệu từ một service | Cấu hình riêng của JVM/pod và service name |
| Collector queue tăng liên tục | Tốc độ export, lỗi backend, tài nguyên và giới hạn queue |

Một dịch vụ không có người dùng vào ban đêm có thể không tạo span. Ngưỡng “không có dữ liệu” cần tính đến traffic hoặc dùng synthetic traffic có chủ đích, thay vì coi mọi khoảng trống là sự cố.

## 9. Sampling và kiểm soát chi phí

### 9.1. Head sampling và tail sampling

| Cách lấy mẫu | Thời điểm quyết định | Đánh đổi |
| --- | --- | --- |
| Head sampling | Gần lúc bắt đầu trace | Giảm dữ liệu sớm, chưa biết request có lỗi về sau |
| Tail sampling | Sau khi thu được phần lớn hoặc toàn bộ span | Có thể ưu tiên trace lỗi/chậm, cần buffer và xử lý thêm |

Sampling nên có quyết định nhất quán theo trace. Tail sampling không phục hồi span đã bị head sampling loại trước đó. Xem [OpenTelemetry Sampling](https://opentelemetry.io/docs/concepts/sampling/).

Ví dụ cấu hình head sampling cho OpenTelemetry Java, chỉ dùng sau khi đánh giá lưu lượng:

~~~bash
export OTEL_TRACES_SAMPLER=parentbased_traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1
~~~

Đây là lấy mẫu khoảng 10% root traces theo Trace ID, còn span con tuân theo quyết định parent. Nó không phải quy tắc “giữ mọi lỗi”. Các giá trị sampler Java nằm trong [Configure the SDK](https://opentelemetry.io/docs/languages/java/configuration/).

Nếu cần chính sách tail sampling, có thể bổ sung OpenTelemetry Collector với processor phù hợp. Các span cùng Trace ID phải đi đến cùng instance thực hiện quyết định; cần tính đến bộ nhớ, thời gian chờ và span đến muộn. Đây là yêu cầu thiết kế pipeline Collector, không phải một tùy chọn mặc định của domain trong lab. Xem [Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md).

### 9.2. Ước lượng volume trước khi chọn tỷ lệ

Một ước lượng dung lượng theo số span:

~~~text
spans/ngày ≈ requests/giây × 86.400 × spans/request × tỷ lệ giữ lại
~~~

Ví dụ tự tính cho kế hoạch năng lực:

~~~text
100 requests/giây
× 86.400 giây/ngày
× 8 spans/request
× 0,10
= 6.912.000 spans/ngày
~~~

Con số này chưa gồm background jobs, synthetic traffic, retry, fan-out hoặc thay đổi số span theo request. Nó cũng chưa phải hóa đơn: chi phí thực phụ thuộc loại domain, cách tính sử dụng, lựa chọn dịch vụ và giá hiện hành.

Sau khi triển khai, so sánh ước lượng với ingestion thực tế. Nếu số span/request tăng gấp nhiều lần sau một thay đổi nhỏ, kiểm tra instrumentation và hành vi ứng dụng trước khi chỉ giảm sampling.

### 9.3. Giảm dữ liệu ít giá trị

Các lựa chọn cần cân nhắc theo nhu cầu điều tra:

- Giảm hoặc loại trace cho health check có tần suất cao và ít giá trị.
- Giữ tên operation ổn định, như `GET /orders/{id}` thay cho URL mang từng mã đơn.
- Chỉ thêm attributes có mục đích; hạn chế dữ liệu quá dài.
- Không dùng Trace ID, email hoặc order ID làm metric dimension.
- Đặt cơ chế theo dõi ingestion và ngân sách trước khi mở rộng số service.

Cardinality cao có thể làm dữ liệu khó tìm và metric khó tổng hợp, ngay cả khi kích thước một span nhỏ. Tỷ lệ lấy mẫu nên đủ để điều tra luồng hiếm quan trọng, đồng thời phù hợp năng lực thu thập và lưu giữ.

## 10. Bảo mật, tính sẵn sàng và triển khai có kiểm soát

### 10.1. Telemetry cũng là dữ liệu cần quản trị

Rà soát những dữ liệu agent thực sự xuất:

| Nguồn rủi ro | Cách xử lý |
| --- | --- |
| Header Authorization, cookie hoặc session token | Loại khỏi dữ liệu được thu thập |
| Query string, request body | Chỉ cho phép trường cần thiết; tránh thu mặc định toàn bộ |
| SQL và exception message | Kiểm tra thông tin người dùng, literal và secret |
| Private Data Key | Hạn chế truy cập, thay key và cập nhật nơi dùng |
| Trace của nhiều môi trường | Tách domain hoặc phạm vi truy cập theo nhu cầu |
| Attributes nhận từ bên ngoài | Giới hạn giá trị, kích thước và độ tin cậy |

Sampling giảm số lượng quan sát; nó không phải biện pháp khử dữ liệu nhạy cảm. Khi một private key bị lộ, xử lý cả việc thay key lẫn những bản sao trong cấu hình, artifact và log.

### 10.2. Đo overhead bằng triển khai canary

Trước khi áp dụng rộng:

1. Chọn một service hoặc một phần replica làm canary.
2. Ghi nhận baseline latency, CPU, heap và throughput dưới tải tương đương.
3. Bật agent với cấu hình dự kiến, đo lại và theo dõi ingestion.
4. Kiểm tra trace xuyên service, dữ liệu nhạy cảm và khả năng rollback.
5. Mở rộng dần, theo dõi chênh lệch giữa nhóm canary và phần còn lại.

Version của agent, cấu hình sampler và service identity nên nằm trong quy trình triển khai có kiểm soát. Secret được cấp riêng qua cơ chế quản lý secret của nền tảng.

Khi telemetry backend chậm hoặc mất kết nối, mục tiêu vận hành là bảo vệ luồng nghiệp vụ bằng giới hạn tài nguyên và timeout phù hợp. Không giả định exporter có thể buffer vô hạn hoặc bảo đảm không mất span.

### 10.3. Khi bổ sung Collector trên OKE hoặc Compute

Collector có thể giúp gom endpoint và áp dụng chính sách chung, nhưng bổ sung một thành phần phải vận hành:

- Đặt resource request/limit và giới hạn bộ nhớ, queue.
- Theo dõi refused/dropped telemetry và lỗi export.
- Cấu hình retry có giới hạn, đồng thời tính khả năng mất dữ liệu khi restart.
- Bảo vệ endpoint nhận OTLP trong mạng ứng dụng.
- Nếu dùng nhiều replica với tail sampling, bảo đảm routing theo Trace ID.
- Thử kịch bản mất endpoint để biết tác động đến ứng dụng và lượng dữ liệu mất.

Một Collector khỏe không chứng minh trace đầy đủ: có thể thiếu context ở ứng dụng, SDK không export hoặc span bị loại trước khi đến Collector.

## 11. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Hướng kiểm tra theo bằng chứng |
| --- | --- |
| JVM không khởi động sau khi thêm agent | Đường dẫn JAR, quyền đọc, cú pháp tham số và tương thích phiên bản |
| Ứng dụng chạy nhưng không có trace | Agent đã load chưa; có traffic không; endpoint, key, exporter và sampling |
| Chỉ thấy một service | Instrumentation thư viện phía còn lại, cấu hình của từng process và region/domain |
| Cùng request thành nhiều trace | Header bị proxy bỏ; propagator không khớp; context mất khi qua async boundary |
| Inventory không nhận `traceparent` trong lab | Lệnh `-javaagent` của checkout, HTTP client support và `OTEL_PROPAGATORS` |
| Lỗi HTTP 401/403 khi export | Xem response/log thực; kiểm tra key, domain, header và private/public path |
| Lỗi HTTP 404 khi export | Kiểm tra hostname, path OTLP và suffix bị thiếu hoặc lặp |
| Lỗi HTTP 429 hoặc dữ liệu bị throttling | Kiểm tra giới hạn và ingestion metrics; điều chỉnh volume/retry |
| TLS hoặc timeout khi export | DNS, route, egress, proxy, chứng thư và trust store JVM |
| Có span nhưng quan hệ thời gian bất thường | Đồng bộ clock, parent ID và span bắt đầu/kết thúc sai |
| Tỷ lệ lỗi từ trace khác metric | Sampling, tập request, cửa sổ thời gian và việc một lỗi tạo nhiều span |
| Span tăng đột biến | Hai agent/SDK, instrumentation trùng, retry hoặc fan-out |

Status HTTP từ endpoint chỉ là một dấu hiệu. Đọc thêm thông báo lỗi và metric rejection trước khi kết luận nguyên nhân. Khi chia sẻ log hỗ trợ, loại data key và các thông tin nhạy cảm.

Trong trường hợp lab không có trace, giữ thứ tự điều tra đơn giản:

~~~text
Ứng dụng có phục vụ request?
→ Agent có khởi động?
→ Agent có tạo span?
→ Exporter có gửi và nhận phản hồi?
→ Đang mở đúng domain, region và thời gian?
→ Context có nối được giữa hai service?
~~~

## 12. Kết thúc thực hành

Trước khi dừng lab, lưu các bằng chứng cần thiết cho chính lần thực hành:

- Trace ID của một request bình thường có cả hai service.
- Trace chậm thể hiện khoảng chờ inventory.
- Trace lỗi tương ứng với `503` ở inventory và `502` ở checkout.
- Phiên bản JDK, agent và cấu hình sampling; không lưu private key.
- Nhận xét dựa trên span: bước nào tăng thời gian, lỗi phát sinh từ đâu, cần dữ liệu gì để điều tra tiếp.

Dừng các JVM bằng `Ctrl+C`. Với máy thực hành dùng chung, xóa biến chứa key khỏi terminal sau khi tiến trình dừng:

~~~bash
unset OTEL_EXPORTER_OTLP_TRACES_HEADERS
unset APM_UPLOAD_BASE
~~~

Nếu đã tạo tài nguyên OCI chỉ phục vụ lab, dọn hoặc dừng tài nguyên theo kế hoạch của môi trường, sau khi lưu bằng chứng cần thiết. Kiểm tra cả Compute, lưu trữ và thành phần mạng có tính phí; việc không còn request không đồng nghĩa mọi chi phí đã dừng.

Kết quả cần đạt là giải thích được một request bằng quan hệ giữa các span, nhận ra giới hạn của dữ liệu đang quan sát và vận hành pipeline gửi dữ liệu đến OCI APM với quyền truy cập, volume và tài nguyên được kiểm soát.
