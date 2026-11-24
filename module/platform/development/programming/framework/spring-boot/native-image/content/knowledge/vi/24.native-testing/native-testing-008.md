# Kiểm thử hộp đen qua HTTP hoặc giao thức thực của binary đã build

Sau khi biên dịch Spring Boot thành GraalVM Native Image, cần kiểm thử **chính binary đã build qua giao thức mà client bên ngoài sử dụng**. Với web service, đó thường là HTTP/HTTPS; với ứng dụng khác, có thể là gRPC, WebSocket hoặc một giao thức TCP riêng. Bài kiểm thử gửi request thật, nhận response thật và xác nhận hành vi quan sát được từ bên ngoài process.

Đây là kiểm thử hộp đen (black-box): test không gọi trực tiếp Spring bean, không khởi tạo `ApplicationContext` trong cùng JVM và không phụ thuộc vào cấu trúc nội bộ của ứng dụng. Nó khởi động executable hoặc container image, đợi service sẵn sàng, gửi request qua socket mạng, rồi xác minh status, header, payload, lỗi và tác động nghiệp vụ.

Với Spring Boot Native Image, cách kiểm thử này phát hiện các lỗi mà unit test trên JVM hoặc test `MockMvc` có thể bỏ sót: thiếu reflection/serialization hints, resource không được đóng gói, cấu hình native khác JVM, JNI library không load, sai HTTP behavior, dependency bên ngoài không sẵn sàng hoặc binary không chạy được trong runtime image.

## 1. Kiểm thử hộp đen khác gì test trong JVM?

Các cấp kiểm thử giải quyết những câu hỏi khác nhau:

| Cấp kiểm thử | Cách thực hiện | Điều được xác nhận |
|---|---|---|
| Unit test | Gọi method/class trực tiếp | Logic nhỏ và quy tắc nghiệp vụ |
| Spring integration test | Khởi tạo ApplicationContext, có thể dùng mock web environment | Wiring, configuration, bean và framework integration |
| `MockMvc` / `WebTestClient` với mock server | Gọi lớp web trong test context | Mapping, validation, serialization ở tầng web trong JVM |
| Native executable black-box test | Khởi động binary và gửi request qua HTTP/socket | Hành vi của artifact native trong runtime thực |
| Container black-box test | Chạy final image rồi gọi cổng đã publish | Binary, OS libraries, image filesystem, user, network và giao thức |

Ví dụ, `MockMvc` có thể chứng minh controller trả HTTP 201 khi nhận một request hợp lệ. Nhưng nó không chứng minh executable native có thể khởi động, nạp JSON serializer, tìm resource, mở socket và trả response khi chạy trong container.

~~~mermaid
flowchart TD
    A["Build Spring Boot Native Image"] --> B["Đóng gói binary vào final image"]
    B --> C["Khởi động container hoặc executable"]
    C --> D["Đợi readiness qua giao thức thật"]
    D --> E["HTTP / gRPC / TCP client gửi request"]
    E --> F["Kiểm tra status, headers, payload"]
    F --> G["Kiểm tra tác động và dependency"]
    G --> H{"Contract thực tế đạt?"}
    H -->|Có| I["Lưu bằng chứng kiểm thử"]
    H -->|Không| J["Thu log và chẩn đoán native runtime"]
~~~

**Test phải kết nối tới cổng mà client thật sẽ dùng.** Không gọi controller method, không truy cập trực tiếp bean và không thay server connector bằng mock nếu mục tiêu là xác nhận binary đã build.

## 2. Xác định contract bên ngoài trước khi viết test

Một test hộp đen tốt bắt đầu từ contract của service. Với mỗi endpoint hoặc operation, ghi lại:

- HTTP method hoặc loại message/gRPC method.
- Đường dẫn, query parameter và header bắt buộc.
- Kiểu nội dung request và response.
- Status code cho thành công và từng loại lỗi.
- Quy tắc xác thực, phân quyền và tenant nếu có.
- Timeout, retry, idempotency và giới hạn payload.
- Tác động quan sát được như bản ghi được tạo, event được phát hoặc trạng thái thay đổi.

Ví dụ contract tạo đơn hàng:

| Trường hợp | Request | Kết quả mong đợi |
|---|---|---|
| Tạo đơn hợp lệ | `POST /api/orders`, JSON hợp lệ | `201 Created`, có `Location` và JSON chứa ID |
| Thiếu trường bắt buộc | `POST /api/orders`, thiếu `customerId` | `400 Bad Request` |
| Không xác thực | Không gửi bearer token | `401 Unauthorized` |
| Không đủ quyền | Token hợp lệ nhưng thiếu role | `403 Forbidden` |
| Không tìm thấy | `GET /api/orders/{id}` với ID không tồn tại | `404 Not Found` |
| Gửi lại yêu cầu idempotent | Cùng idempotency key | Không tạo giao dịch trùng theo contract |

Đừng chỉ kiểm tra rằng server trả về 200. Status, header và payload đều là một phần của contract. Nếu client phụ thuộc vào `Location`, `ETag`, `Retry-After` hoặc `Content-Type`, test cần xác nhận chúng.

## 3. Chọn đúng artifact để kiểm thử

Một nguyên tắc quan trọng là **test đúng artifact sẽ phát hành**. Nếu production chạy container image, hãy kiểm thử final image. Nếu production chạy executable trực tiếp trên máy ảo, có thể khởi chạy chính executable trên một host tương đương.

Không nên build một binary riêng cho test rồi build lại binary khác cho release mà không kiểm tra sự khác nhau. Hai artifact có thể khác profile, environment, native hints, resource hoặc dependency.

Quy trình đề xuất:

1. Build native executable một lần cho target OS/architecture.
2. Đóng gói binary vào final container image theo cấu hình triển khai.
3. Gắn tag hoặc digest bất biến cho image.
4. Chạy black-box test trên đúng image đó.
5. Nếu test đạt, phát hành cùng image digest đã kiểm thử.

Với Gradle, task native thường dùng là:

~~~bash
./gradlew nativeCompile
~~~

Với Maven, tùy cấu hình Spring Boot và Native Build Tools:

~~~bash
./mvnw -Pnative package
~~~

Các task/goal phụ thuộc plugin và profile dự án. Đường dẫn output binary cũng thay đổi theo artifact name và build configuration; hãy dùng đúng output của dự án khi tạo image.

## 4. Chạy binary trực tiếp trên host

Nếu môi trường production chạy executable trực tiếp, có thể khởi động binary bằng shell:

~~~bash
SPRING_PROFILES_ACTIVE=blackbox \
SERVER_PORT=18080 \
./application
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "blackbox"
$env:SERVER_PORT = "18080"
.\application.exe
~~~

Mở một terminal khác và gọi endpoint:

~~~bash
curl --fail --include http://127.0.0.1:18080/actuator/health
~~~

Cách này kiểm tra native executable trên host hiện tại. Nó chưa kiểm tra final container image, filesystem container, user non-root hoặc network namespace. Nếu production dùng container, hãy chạy test trong container để bao phủ các yếu tố đó.

Đảm bảo process được dừng sau test và log stdout/stderr được lưu khi test thất bại. Tránh dùng một cổng cố định chung cho nhiều job CI chạy song song; cấu hình cổng riêng theo job hoặc dùng port mapping động.

## 5. Chạy trong final container image

Với Docker, khởi động image đã build và publish cổng HTTP:

~~~bash
docker run -d \
  --name orders-native-blackbox \
  --publish 127.0.0.1:18080:8080 \
  --env SPRING_PROFILES_ACTIVE=blackbox \
  orders-service:native-test
~~~

Trong ví dụ:

- Ứng dụng lắng nghe cổng 8080 bên trong container.
- Host test gọi cổng 18080.
- Profile `blackbox` nạp cấu hình dành cho môi trường kiểm thử.
- Image `orders-service:native-test` phải là image chứa native executable đã build.

Kiểm tra process và log:

~~~bash
docker ps --filter name=orders-native-blackbox
docker logs orders-native-blackbox
~~~

Gọi endpoint từ host:

~~~bash
curl --fail --include http://127.0.0.1:18080/actuator/health
~~~

Không kiểm thử bằng cách chạy binary trong builder image rồi suy ra final image hoạt động. Builder có thể chứa nhiều thư viện mà run image không có.

## 6. Đợi readiness thay vì sleep cố định

Native image thường khởi động nhanh, nhưng thời gian thực tế còn phụ thuộc CPU, filesystem, database migration và dependency bên ngoài. `sleep 2` không chứng minh service đã sẵn sàng; nó có thể quá ngắn trên runner chậm và lãng phí thời gian trên runner nhanh.

Hãy poll readiness endpoint với deadline:

~~~bash
set -euo pipefail

BASE_URL="http://127.0.0.1:18080"
READY_URL="$BASE_URL/actuator/health/readiness"
READY=false

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error "$READY_URL" >/dev/null 2>&1; then
    READY=true
    break
  fi
  sleep 1
done

if [ "$READY" != "true" ]; then
  echo "Application did not become ready"
  docker logs orders-native-blackbox
  exit 1
fi
~~~

`/actuator/health/readiness` cần được bật và expose trong cấu hình test. Nếu dự án không dùng Actuator readiness group, thay bằng endpoint readiness riêng của ứng dụng. Endpoint readiness nên phản ánh những điều kiện cần để nhận traffic, ví dụ database hoặc message broker đã sẵn sàng.

Phân biệt:

- **Liveness:** process còn hoạt động và không cần bị restart.
- **Readiness:** ứng dụng có thể nhận request nghiệp vụ.
- **Startup:** ứng dụng đã hoàn tất giai đoạn khởi động ban đầu.

Một HTTP 200 từ endpoint liveness chưa chắc database đã sẵn sàng. Chọn probe đúng với mục tiêu test.

## 7. Viết HTTP black-box test bằng Java HttpClient

Có thể dùng JUnit chạy trên JVM để điều khiển container native và gửi request qua HTTP. Test code chạy trên JVM, nhưng server được kiểm tra là native image thực sự.

Ví dụ dùng Testcontainers:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}
~~~

Các version nên được quản lý bằng dependency management/BOM tương thích của dự án.

Test khởi động image được truyền qua biến môi trường `NATIVE_TEST_IMAGE`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class OrdersNativeBlackBoxTests {

    private static final String IMAGE =
        System.getenv().getOrDefault(
            "NATIVE_TEST_IMAGE",
            "orders-service:native-test"
        );

    @Container
    static final GenericContainer<?> application =
        new GenericContainer<>(DockerImageName.parse(IMAGE))
            .withExposedPorts(8080)
            .withEnv("SPRING_PROFILES_ACTIVE", "blackbox")
            .waitingFor(
                Wait.forHttp("/actuator/health/readiness")
                    .forStatusCode(200)
                    .withStartupTimeout(Duration.ofSeconds(90))
            );

    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Test
    void createsOrderThroughRealHttpEndpoint() throws Exception {
        int port = application.getMappedPort(8080);
        URI uri = URI.create(
            "http://localhost:" + port + "/api/orders"
        );

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .header("Content-Type", "application/json")
            .header("Accept", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(
                """
                {
                  "customerId": "C-100",
                  "sku": "SKU-01",
                  "quantity": 2
                }
                """
            ))
            .build();

        HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(response.headers()
            .firstValue("content-type").orElse(""))
            .contains("application/json");
        assertThat(response.headers()
            .firstValue("location")).isPresent();
        assertThat(response.body()).contains("\"orderId\"");
    }
}
~~~

Ví dụ giả định ứng dụng có Actuator readiness endpoint và API tạo đơn hàng trả `201`, `Location`, JSON có `orderId`. Hãy thay endpoint, payload và assertion bằng contract thực tế. Nếu API trả `202 Accepted` hoặc dùng response schema khác, test cần phản ánh đúng contract đó.

Điểm quan trọng là request đi qua TCP socket tới cổng container được map. Test không gọi controller hoặc Spring bean trong JVM test.

## 8. Kiểm tra response contract đầy đủ

Không nên dừng ở status code. Một response test có thể xác nhận:

~~~java
assertThat(response.statusCode()).isEqualTo(201);

assertThat(response.headers()
    .firstValue("content-type").orElse(""))
    .startsWith("application/json");

assertThat(response.headers()
    .firstValue("location"))
    .isPresent();

assertThat(response.body())
    .contains("\"orderId\"")
    .contains("\"status\":\"CREATED\"");
~~~

Với contract JSON ổn định, nên parse JSON bằng Jackson hoặc JSON assertion library thay vì so sánh toàn bộ chuỗi. So sánh chuỗi dễ lỗi do thứ tự field hoặc whitespace thay đổi dù nội dung JSON tương đương.

Các trường cần kiểm tra:

- Field bắt buộc có mặt và có đúng kiểu.
- Field nhạy cảm không bị trả ra ngoài.
- Null/omitted field đúng quy tắc.
- Decimal, timestamp và timezone đúng định dạng.
- `Content-Type`, charset và content negotiation đúng.
- Header `Location`, `ETag`, cache hoặc correlation ID đúng khi contract yêu cầu.

Một lợi ích của HTTP black-box test là nó kiểm tra cả quá trình serialize response của native executable. Nếu reflection hints cho DTO bị thiếu, lỗi có thể chỉ xuất hiện khi một endpoint trả về một kiểu dữ liệu ít gặp.

## 9. Kiểm thử validation và error response

Một API production phải trả lỗi có cấu trúc ổn định. Gửi request không hợp lệ:

~~~bash
curl --include \
  --header "Content-Type: application/json" \
  --data '{"customerId":"","quantity":0}' \
  http://127.0.0.1:18080/api/orders
~~~

Kiểm tra:

- Status là `400 Bad Request` theo contract.
- Response có mã lỗi hoặc `type/title/detail` nếu dùng Problem Details.
- Không lộ stack trace, đường dẫn filesystem, secret hoặc SQL.
- Field validation được chỉ rõ nếu API hỗ trợ.
- Content type vẫn đúng.
- Request malformed JSON được xử lý có kiểm soát.

Native image có thể khác JVM nếu serializer, validation metadata hoặc reflection access bị thiếu. Vì vậy hãy test cả request hợp lệ, thiếu field, sai kiểu, giá trị ngoài giới hạn và payload JSON lỗi cú pháp.

## 10. Kiểm tra authentication và authorization qua HTTP

Nếu endpoint yêu cầu token, test phải gửi request như client thực:

~~~bash
curl --include \
  --header "Authorization: Bearer $TEST_ACCESS_TOKEN" \
  http://127.0.0.1:18080/api/orders
~~~

Tối thiểu nên có các trường hợp:

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Không gửi token | `401` |
| Token sai/hết hạn | `401` |
| Token hợp lệ nhưng thiếu quyền | `403` |
| Token có quyền phù hợp | Response nghiệp vụ theo contract |
| Token có tenant khác | Không đọc/ghi dữ liệu ngoài tenant |

Dùng credential dành riêng cho test, có thời hạn và quyền tối thiểu. Nếu ứng dụng dùng OAuth2/OIDC, có thể chạy identity provider test trong container hoặc dùng một issuer test có thể kiểm soát. Không phụ thuộc vào tài khoản production trong CI.

Test black-box cũng giúp xác nhận cấu hình security filter, JWT decoder, TLS và các resource key/certificate đã có trong native runtime.

## 11. Kiểm thử trạng thái và tác động nghiệp vụ

Một response 201 không đủ để chứng minh giao dịch đã được lưu đúng. Hãy kiểm tra trạng thái thông qua API công khai hoặc dependency test:

1. Gửi `POST /api/orders`.
2. Lấy ID từ response hoặc `Location`.
3. Gửi `GET /api/orders/{id}`.
4. Xác nhận các field nghiệp vụ được lưu đúng.
5. Gửi thao tác cập nhật/hủy nếu contract hỗ trợ.
6. Xác nhận trạng thái sau thao tác.

Ví dụ:

~~~bash
curl --fail \
  http://127.0.0.1:18080/api/orders/ORDER-100
~~~

Nếu cần kiểm tra database, có thể truy vấn database test sau khi request hoàn tất. Tuy nhiên, API-level assertion nên là bằng chứng chính về contract bên ngoài; truy cập database là bằng chứng bổ sung cho persistence/integration.

Với message-driven service, HTTP response có thể chỉ xác nhận event đã được nhận. Khi đó cần đợi và xác minh kết quả qua consumer/API hoặc test broker, không giả định event được xử lý đồng bộ.

## 12. Chạy dependency thật trong môi trường test

Một binary có thể trả health 200 nhưng thất bại khi gọi database, Redis, broker hoặc dịch vụ HTTP khác. Hãy chạy các dependency cần thiết trong môi trường test cô lập.

Các lựa chọn:

- Testcontainers cho PostgreSQL, Redis, Kafka, RabbitMQ hoặc service phụ trợ.
- WireMock/MockServer cho HTTP service bên ngoài.
- Docker Compose cho môi trường tích hợp nhiều container.
- Database/schema riêng cho từng job CI.
- Network riêng và alias DNS nội bộ cho các container.

Với Testcontainers, ứng dụng native có thể nhận URL database qua environment:

~~~java
.withEnv(
    "SPRING_DATASOURCE_URL",
    "jdbc:postgresql://orders-db:5432/orders"
)
.withEnv("SPRING_DATASOURCE_USERNAME", "test")
.withEnv("SPRING_DATASOURCE_PASSWORD", "test-only")
~~~

Tên `orders-db` cần là network alias mà container ứng dụng có thể phân giải. Cần tạo Docker network dùng chung và gắn database container cùng application container vào network đó. Ví dụ trên chỉ minh họa cấu hình; không dùng password test trong môi trường ngoài test.

Kiểm tra các tình huống:

- Database có sẵn trước khi ứng dụng nhận readiness.
- Migration chạy thành công.
- Connection pool hoạt động.
- Database restart hoặc mất kết nối được xử lý theo contract.
- Message broker nhận/gửi message đúng.
- HTTP client gọi đúng downstream service và timeout phù hợp.

## 13. Kiểm thử timeout, retry và idempotency

Một black-box test có thể gửi request với deadline rõ ràng:

~~~bash
curl --max-time 5 \
  --fail \
  http://127.0.0.1:18080/api/orders/ORDER-100
~~~

Với thao tác có retry, test cần phân biệt:

- Client retry do timeout.
- Server đã xử lý request nhưng response bị mất.
- Server trả lỗi tạm thời như `503`.
- Request được gửi lại với cùng idempotency key.
- Giao dịch có bị tạo trùng hay không.

Không kiểm tra retry bằng cách chỉ xác nhận cuối cùng nhận được 200. Hãy xác nhận số lần side effect xảy ra, trạng thái cuối và mã response ở từng tình huống.

Các test timeout nên có giới hạn tổng thời gian để CI không treo vô hạn. Ghi rõ timeout kết nối, timeout request và deadline của cả kịch bản.

## 14. Kiểm thử HTTPS, TLS và proxy

Nếu binary tự kết thúc TLS, hãy gọi endpoint bằng HTTPS với certificate test và kiểm tra handshake, protocol version, hostname verification và trust chain.

Nếu TLS được kết thúc ở ingress/reverse proxy, có thể cần hai lớp test:

- Gọi trực tiếp HTTP vào container để kiểm tra contract ứng dụng.
- Gọi HTTPS qua proxy/ingress để kiểm tra TLS, forwarded headers, redirect, cookie và URL công khai.

Một số lỗi chỉ xuất hiện khi ứng dụng nhận `X-Forwarded-Proto`, `X-Forwarded-For` hoặc `Forwarded`. Hãy kiểm tra link được tạo trong response, redirect URI và secure cookie theo cấu hình proxy thực tế.

Không tắt certificate verification trong test rồi kết luận TLS hoạt động. Dùng CA test được tin cậy trong test client và xác nhận hostname đúng.

## 15. Kiểm thử giao thức khác HTTP

Nếu service không cung cấp REST API, black-box test vẫn dùng client thật của giao thức:

| Giao thức | Cách kiểm thử | Điều cần xác nhận |
|---|---|---|
| gRPC | Stub sinh từ `.proto`, gọi qua HTTP/2 channel | RPC status, metadata, deadline, TLS và serialization Protobuf |
| WebSocket | Client mở handshake HTTP Upgrade rồi gửi frame | Handshake, subprotocol, message, ping/pong và close code |
| TCP tùy biến | `Socket`/client protocol thật gửi byte frame | Framing, encoding, timeout, connection lifecycle và lỗi |
| AMQP | AMQP client kết nối broker test | Publish/consume, routing key, ack/nack và redelivery |
| MQTT | MQTT client kết nối broker test | Connect, subscribe, QoS, retained message và reconnect |

Ví dụ gRPC test cần dùng generated stub và channel tới cổng được expose của native container:

~~~java
ManagedChannel channel = ManagedChannelBuilder
    .forAddress("localhost", mappedPort)
    .usePlaintext()
    .build();

try {
    OrdersGrpc.OrdersBlockingStub stub =
        OrdersGrpc.newBlockingStub(channel)
            .withDeadlineAfter(5, TimeUnit.SECONDS);

    OrderReply reply = stub.createOrder(
        CreateOrderRequest.newBuilder()
            .setCustomerId("C-100")
            .setSku("SKU-01")
            .setQuantity(2)
            .build()
    );

    assertThat(reply.getOrderId()).isNotBlank();
}
finally {
    channel.shutdownNow();
}
~~~

Đây là ví dụ gRPC không TLS cho mạng test nội bộ. Trong môi trường có TLS, cấu hình channel bằng test certificate và xác minh hostname. Không gửi HTTP/1.1 request thông thường tới một cổng chỉ phục vụ HTTP/2 gRPC rồi coi lỗi đó là lỗi native.

## 16. Kiểm tra concurrency và giới hạn tải

Native image có thể thay đổi startup time và memory footprint, nhưng vẫn cần kiểm thử hành vi khi nhiều client gọi đồng thời.

Có thể dùng k6, Gatling hoặc JMeter để:

- Gửi nhiều request đồng thời tới endpoint quan trọng.
- Xác nhận không mất hoặc tạo trùng dữ liệu.
- Kiểm tra latency percentile và error rate.
- Quan sát memory, CPU, thread và connection pool.
- Kiểm tra giới hạn payload, rate limit và backpressure.
- Kiểm tra server vẫn phục vụ request sau burst traffic.

Đây là kiểm thử tải ở mức giao thức; cần tách khỏi smoke test chức năng để kết quả dễ đọc. Không đặt ngưỡng latency tùy ý. Hãy lấy SLO hoặc baseline của service làm tiêu chí và chạy trên hạ tầng có cấu hình xác định.

## 17. Thu thập log và chẩn đoán khi black-box test thất bại

Khi test thất bại, giữ lại đủ bằng chứng để xác định lỗi ở startup, network, native runtime hay contract.

Thông tin nên lưu:

- Image tag và digest.
- OS, architecture và runtime image.
- Environment/profile test đã dùng, loại bỏ secret.
- Container exit code và thời gian khởi động.
- stdout/stderr hoặc `docker logs`.
- Request method, path, status, response header và body đã lọc dữ liệu nhạy cảm.
- Correlation ID/trace ID.
- Log của dependency container như database hoặc broker.

Các dấu hiệu thường gặp:

| Triệu chứng | Hướng điều tra |
|---|---|
| Container thoát ngay khi start | Đọc startup log, dynamic library, native initialization và config |
| Health endpoint không đạt | Kiểm tra readiness, migration, dependency và port binding |
| Connection refused | Kiểm tra port mapping, server bind address và process |
| HTTP 404 | Kiểm tra context path, route và profile |
| HTTP 415 | Kiểm tra `Content-Type` |
| HTTP 406 | Kiểm tra `Accept` và content negotiation |
| HTTP 401/403 | Kiểm tra token, role, issuer và security config |
| HTTP 500 chỉ trên native | Kiểm tra reflection/serialization hints, resource và stack trace |
| Response JSON thiếu field | Kiểm tra serializer, DTO metadata và cấu hình inclusion |
| Timeout khi gọi downstream | Kiểm tra DNS, network, TLS, connection pool và timeout |
| Chỉ lỗi trong container | Kiểm tra environment, filesystem, user, certificate và native libraries |

Nếu có thể, lưu log ngay cả khi container test bị dừng. Trong CI, dùng `finally` hoặc cleanup hook để thu log trước khi xóa container.

## 18. Dọn dẹp tài nguyên test

Test cần dừng container và đóng connection dù assertion thành công hay thất bại.

Với shell:

~~~bash
cleanup() {
  docker logs orders-native-blackbox || true
  docker rm -f orders-native-blackbox >/dev/null 2>&1 || true
}
trap cleanup EXIT
~~~

Với Testcontainers, annotation `@Container` cùng extension JUnit quản lý vòng đời container. Với gRPC, WebSocket hoặc raw TCP client, đóng channel/socket trong `finally` hoặc try-with-resources.

Tránh dùng container name cố định khi nhiều job chạy đồng thời. Dùng tên duy nhất theo CI run hoặc để Testcontainers tự quản lý container. Test nên độc lập và có thể chạy lặp lại mà không để lại database, port hoặc file tạm làm ảnh hưởng lần sau.

## 19. Tổ chức black-box test trong CI

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A["Compile và test JVM"] --> B["Spring AOT processing"]
    B --> C["Build Native Image"]
    C --> D["Build final container image"]
    D --> E["Ghi image digest"]
    E --> F["Start native image"]
    F --> G["Wait readiness"]
    G --> H["HTTP/protocol contract tests"]
    H --> I["Integration tests với dependencies"]
    I --> J["Lưu logs và test reports"]
    J --> K{"Tất cả đạt?"}
    K -->|Có| L["Phát hành đúng image digest"]
    K -->|Không| M["Giữ artifact và chẩn đoán"]
~~~

Ví dụ lệnh pipeline:

~~~bash
# Build native executable
./gradlew nativeCompile

# Đóng gói final image chứa binary vừa build
docker build -f Dockerfile.native \
  -t orders-service:native-test .

# Chạy black-box test với chính image này
NATIVE_TEST_IMAGE=orders-service:native-test \
  ./gradlew test
~~~

Trong dự án thực tế, nên tách source set/task black-box khỏi unit test JVM để có thể chạy độc lập và gắn đúng image. Đảm bảo Docker image build xong trước khi test bắt đầu; không để test vô tình lấy một tag cũ còn trên máy runner.

Nếu phát hành multi-architecture, chạy test trên runner phù hợp với từng OS/architecture. Một image tag có thể trỏ tới manifest nhiều platform; cần kiểm tra từng platform thực tế, không chỉ test một kiến trúc rồi suy ra tất cả đều hoạt động.

## 20. Phân biệt test binary với test toàn bộ deployment

Black-box test trực tiếp tới binary kiểm tra contract mà process cung cấp. Nó chưa tự động xác nhận mọi thành phần triển khai production:

| Phạm vi | Cần test ở đâu? |
|---|---|
| HTTP handler, JSON, validation, security trong app | Gọi trực tiếp native binary/container |
| JNI và shared libraries | Chạy binary trong runtime image đích |
| Database, broker, downstream API | Chạy cùng dependency test hoặc service sandbox |
| TLS termination, ingress, routing | Gọi qua reverse proxy/ingress |
| DNS, service discovery, network policy | Test trong network/platform tương đương deployment |
| Secret/config injection | Chạy với cơ chế cấu hình giống production nhưng dùng giá trị test |
| Rolling update, readiness, shutdown | Test ở tầng orchestrator/deployment |

Hãy xác định phạm vi test theo rủi ro và contract. Không cần triển khai cả production stack cho mỗi unit test, nhưng trước khi phát hành cần có ít nhất một lượt kiểm thử tích hợp trên môi trường gần với deployment thực.

## 21. Checklist nghiệm thu black-box test

Trước khi đánh dấu native artifact đạt, xác minh:

- [ ] Test chạy đúng binary/image đã build và dự định phát hành.
- [ ] OS, architecture và runtime image khớp target.
- [ ] Process khởi động và readiness đạt trong deadline.
- [ ] Client gửi request qua HTTP hoặc giao thức thực.
- [ ] Status, headers, content type và payload đúng contract.
- [ ] Request hợp lệ, invalid input và error response đã được kiểm tra.
- [ ] Authentication/authorization đã được kiểm tra nếu có.
- [ ] Serialization, resource và JNI path quan trọng đã chạy thật.
- [ ] Database, broker và downstream dependency đã được kiểm tra khi cần.
- [ ] Timeout, retry và idempotency được xác minh theo contract.
- [ ] Log và artifact digest được lưu khi test thất bại.
- [ ] Container/process, port và network test được dọn dẹp.

## 22. Ghi nhớ

Kiểm thử hộp đen qua HTTP hoặc giao thức thực xác nhận **hành vi quan sát được của binary đã build**. Test phải khởi động chính executable hoặc final container image, đợi readiness, gửi request qua socket thật và kiểm tra response cùng tác động nghiệp vụ.

Dùng `MockMvc` hoặc unit test vẫn hữu ích cho logic và web layer, nhưng chúng không thay thế kiểm thử native runtime. Với Spring Boot Native Image, black-box test đặc biệt quan trọng để phát hiện thiếu hints, serializer/resource lỗi, JNI không load, sai cấu hình và dependency không sẵn sàng.

Trong CI, build artifact một lần, test đúng artifact đó, lưu image digest và log, rồi phát hành cùng digest đã vượt qua contract/integration tests. Nếu ứng dụng dùng gRPC, WebSocket, AMQP hoặc TCP riêng, hãy dùng client của giao thức tương ứng để xác minh hành vi từ góc nhìn consumer.

### Tài liệu tham khảo

- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/
- Spring Boot — Actuator Endpoints: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Container Images: https://docs.spring.io/spring-boot/reference/packaging/container-images/
- Testcontainers for Java — JUnit 5 Quickstart: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Testcontainers for Java — Wait Strategies: https://java.testcontainers.org/features/startup_and_waits/
- Java — java.net.http.HttpClient: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html

API, task build và cấu hình Actuator phụ thuộc phiên bản Spring Boot, GraalVM, JDK và Testcontainers. Hãy dùng dependency management và tài liệu đúng version mà dự án pin.
