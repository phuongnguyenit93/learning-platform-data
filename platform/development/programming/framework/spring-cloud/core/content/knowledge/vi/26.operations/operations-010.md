# Kiểm chứng hành vi khi mất mạng, registry hoặc nguồn cấu hình

Bài học thuộc chương **Vận hành** của module **SPRING_CLOUD_CORE**. Một ứng dụng Spring Cloud phụ thuộc vào nhiều thành phần nằm ngoài process: mạng, DNS, service registry, Config Server, message broker của Spring Cloud Bus và các service mà LoadBalancer gọi tới. Những dependency này có thể chậm, mất kết nối, trả dữ liệu cũ hoặc phục hồi không đồng thời. Ứng dụng cần được kiểm chứng trong các trạng thái đó trước khi triển khai production.

Kiểm thử lỗi vận hành không chỉ xác nhận request thất bại. Cần quan sát ứng dụng phản ứng như thế nào, thời gian phát hiện sự cố, giới hạn retry, khả năng phục vụ bằng dữ liệu đã cache, trạng thái readiness và khả năng phục hồi sau khi dependency hoạt động trở lại. Với nguồn cấu hình, phải xác định rõ cấu hình nào bắt buộc để khởi động, cấu hình nào có thể dùng giá trị local dự phòng và cách ứng dụng xử lý khi refresh trong lúc Config Server không sẵn sàng.

Bài học xây dựng các kịch bản có thể lặp lại cho ba nhóm sự cố: **mất mạng**, **registry không khả dụng** và **nguồn cấu hình bị gián đoạn**. Ví dụ dùng Testcontainers Toxiproxy để tạo latency, jitter và cắt kết nối trong môi trường kiểm thử cô lập; kết hợp với kiểm thử startup, runtime refresh, LoadBalancer cache, health/readiness và quy trình phục hồi.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Phân loại lỗi mạng thành DNS, connection refused, timeout, latency, kết nối bị ngắt và lỗi TLS.
2. Xây dựng failure scenario có điều kiện bắt đầu, thời gian duy trì và tiêu chí phục hồi.
3. Dùng Testcontainers Toxiproxy để mô phỏng gián đoạn TCP trong integration test.
4. Phân biệt registry outage với service instance outage và dữ liệu đăng ký cũ.
5. Kiểm tra hành vi DiscoveryClient và Spring Cloud LoadBalancer khi registry mất kết nối.
6. Hiểu ảnh hưởng của cache instance list và TTL tới request trong lúc registry lỗi.
7. Kiểm thử Config Client khi Config Server không khả dụng lúc startup.
8. Phân biệt `optional:configserver:` với config import bắt buộc.
9. Kiểm tra fail-fast, retry, backoff và connect/read timeout.
10. Kiểm thử nhiều Config Server endpoint và phân biệt lỗi mạng với lỗi xác thực.
11. Kiểm chứng refresh cấu hình khi nguồn remote bị gián đoạn.
12. Kiểm thử việc truyền refresh qua Spring Cloud Bus khi broker hoặc một số instance gặp lỗi.
13. Thiết kế fallback và last-known-good configuration có chủ đích.
14. Phân biệt health, readiness và liveness khi dependency bên ngoài bị lỗi.
15. Đo thời gian phát hiện, thời gian phục hồi, số lần retry và tỷ lệ request thất bại.
16. Chạy chaos test với blast radius nhỏ, điều kiện dừng và cách khôi phục rõ ràng.

## 2. Xây dựng hợp đồng hành vi trước khi gây lỗi

### 2.1. Không bắt đầu bằng cách tắt dependency ngẫu nhiên

Trước mỗi thử nghiệm, viết rõ điều gì cần được kiểm chứng. Ví dụ:

- Khi Config Server không truy cập được trong startup, ứng dụng phải dừng hay được phép dùng local configuration?
- Khi registry mất kết nối trong 20 giây, request đang có instance list trong cache được xử lý thế nào?
- Khi cache hết hạn mà registry vẫn lỗi, caller nhận lỗi nào?
- Khi registry phục hồi, ứng dụng cần bao lâu để nhìn thấy instance mới?
- Khi Bus broker ngắt kết nối, một instance có thể refresh local hay không?
- Khi refresh một bean thất bại, health indicator và request tiếp theo phản ánh trạng thái nào?

Một kịch bản chỉ có giá trị khi kết quả mong đợi được xác định trước. Không nên coi mọi exception là PASS; một exception đúng loại nhưng retry vô hạn, làm cạn connection pool hoặc khiến toàn bộ instance restart vẫn là lỗi vận hành.

### 2.2. Mẫu mô tả một failure scenario

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Dependency | Registry, Config Server, DNS, broker hay service downstream nào bị tác động? |
| Failure mode | Mất kết nối, latency, timeout, trả 401/403/404/500 hay dữ liệu cũ? |
| Injection point | Toxiproxy, container stop, mock server hay cấu hình test? |
| Duration | Lỗi kéo dài bao lâu hoặc đến khi điều kiện nào được thỏa mãn? |
| Expected behavior | Request fail, fallback, retry, cache, readiness đổi trạng thái hay startup dừng? |
| Recovery | Cần tạo kết nối mới, refresh cache, đăng ký lại instance hay restart? |
| Evidence | Log, metric, trace, health response và assertion nào chứng minh kết quả? |
| Stop condition | Khi nào phải dừng thử nghiệm để tránh ảnh hưởng môi trường? |

### 2.3. Tách ba thời điểm quan sát

Một dependency có thể hỏng ở ba giai đoạn khác nhau:

1. **Startup:** ứng dụng đang lấy cấu hình hoặc đăng ký service.
2. **Steady state:** ứng dụng đã hoạt động và đang xử lý request.
3. **Recovery:** dependency đã phục hồi nhưng client có thể vẫn giữ cache, connection hoặc trạng thái lỗi cũ.

Chỉ kiểm thử startup không chứng minh ứng dụng chịu được outage runtime. Chỉ kiểm thử request thất bại trong lúc outage cũng chưa chứng minh ứng dụng tự phục hồi sau đó.

## 3. Phân loại lỗi mạng

### 3.1. Các failure mode thường gặp

| Failure mode | Biểu hiện | Điều cần kiểm chứng |
| --- | --- | --- |
| DNS lookup failure | Không phân giải được hostname. | Retry DNS, cache DNS, thời gian phục hồi và thông báo lỗi. |
| Connection refused | Host có thể truy cập nhưng port không lắng nghe. | Connect timeout, retry budget và circuit breaker. |
| Connect timeout | TCP handshake không hoàn tất trong thời gian cho phép. | Client có deadline hữu hạn và không giữ thread quá lâu. |
| Read timeout | Kết nối được nhưng server không trả response đúng hạn. | Request bị hủy, connection được xử lý đúng và retry không nhân đôi side effect. |
| Latency/jitter | Response đến chậm và không ổn định. | Deadline, timeout, retry amplification và p95/p99 latency. |
| TCP interruption | Kết nối bị cắt giữa chừng. | Client phát hiện socket lỗi và tạo kết nối mới. |
| Bandwidth restriction | Dữ liệu truyền chậm hoặc bị nghẽn. | Backpressure, request queue và memory usage. |
| TLS handshake/certificate error | Kết nối thất bại ở lớp TLS. | Truststore, certificate expiry, hostname verification và phân loại lỗi. |
| Partial network impairment | Chỉ một chiều hoặc một tuyến mạng bị ảnh hưởng. | Hành vi bất đối xứng và khả năng timeout đúng. |

### 3.2. Không gộp mọi lỗi thành “network down”

Hai lỗi `Connection refused` và timeout không có cùng ý nghĩa. Tương tự, HTTP 401/403, 404 và 500 cần được phân loại riêng:

- Connection refused thường cho biết không có process nhận kết nối tại địa chỉ/port đó.
- Timeout có thể do packet drop, server quá tải, route lỗi hoặc deadline quá ngắn.
- HTTP 401/403 thường là lỗi credential hoặc authorization; retry như lỗi mạng có thể chỉ làm tăng tải.
- HTTP 404 có thể là sai application/profile/label hoặc tài nguyên chưa tồn tại.
- HTTP 5xx có thể là lỗi server, nhưng cần xem response và nguyên nhân trước khi quyết định retry.

Kịch bản kiểm thử nên tạo riêng từng loại lỗi để bảo đảm client phân loại và xử lý đúng.

### 3.3. Connect timeout và read timeout phải có giới hạn

Một client không có timeout hữu hạn có thể giữ request thread hoặc connection pool slot quá lâu. Với mỗi dependency, xác định:

- Connect timeout.
- Read/response timeout.
- Tổng deadline cho một operation.
- Retry count và backoff.
- Thời gian tối đa trước khi trả lỗi cho caller.

Tổng thời gian retry không nên vượt deadline mà caller hoặc gateway cho phép. Nếu mỗi lần retry có timeout dài và backoff lớn, một request tưởng như đơn giản có thể chiếm tài nguyên trong nhiều phút.

### 3.4. Thử lỗi một chiều

Một chiều request có thể đi được nhưng response không quay về. Tình huống này khác với việc cắt hoàn toàn kết nối. Nó có thể khiến client chờ đến read timeout và tạo cảm giác server đã xử lý request dù caller không nhận được kết quả.

Với thao tác có side effect, kiểm tra idempotency key hoặc cơ chế truy vấn trạng thái operation sau timeout. Không retry mù một lệnh có thể đã được server thực hiện.

## 4. Mô phỏng lỗi mạng bằng Testcontainers Toxiproxy

### 4.1. Toxiproxy dùng ở đâu?

Toxiproxy là TCP proxy có thể đặt giữa test code và container, hoặc giữa các container. Testcontainers cung cấp module Toxiproxy để kiểm tra các failure mode mạng trong integration test và CI.

Có thể dùng proxy cho:
- Ứng dụng kết nối tới service registry.
- Config Client kết nối Config Server.
- Service gọi một downstream TCP endpoint.
- Container ứng dụng kết nối tới message broker.
- Test code kết nối tới dependency chạy trong container.

Đặt proxy giữa client và dependency để test có thể thay đổi mạng trong lúc ứng dụng đang chạy, thay vì chỉ dừng container trước khi test bắt đầu.

### 4.2. Thêm dependency test

Với Gradle, khi dự án đã quản lý phiên bản Testcontainers bằng BOM:

~~~kotlin
dependencies {
    testImplementation("org.testcontainers:testcontainers-toxiproxy")
}
~~~

Với Maven, thêm artifact `org.testcontainers:testcontainers-toxiproxy` ở scope `test` và dùng version được quản lý bởi Testcontainers BOM của dự án.

Không tự nâng riêng module Toxiproxy lên một version khác với các module Testcontainers đang dùng.

### 4.3. Tạo network và proxy

Ví dụ dưới đây dùng một TCP service làm đích minh họa. Trong integration test Spring Cloud thực tế, thay container đích bằng image của registry, Config Server hoặc broker mà ứng dụng đang sử dụng.

~~~java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.Network;
import org.testcontainers.containers.ToxiproxyContainer;

import eu.rekawek.toxiproxy.ToxiproxyClient;
import eu.rekawek.toxiproxy.model.Proxy;

Network network = Network.newNetwork();

GenericContainer<?> dependency =
        new GenericContainer<>("redis:6-alpine")
                .withExposedPorts(6379)
                .withNetwork(network)
                .withNetworkAliases("dependency");

ToxiproxyContainer toxiproxy =
        new ToxiproxyContainer("ghcr.io/shopify/toxiproxy:2.5.0")
                .withNetwork(network)
                .withNetworkAliases("toxiproxy");

dependency.start();
toxiproxy.start();

ToxiproxyClient toxiproxyClient =
        new ToxiproxyClient(
                toxiproxy.getHost(),
                toxiproxy.getControlPort()
        );

Proxy proxy = toxiproxyClient.createProxy(
        "dependency-proxy",
        "0.0.0.0:8666",
        "dependency:6379"
);

String proxyHost = toxiproxy.getHost();
int proxyPort = toxiproxy.getMappedPort(8666);
~~~

Client chạy trên host phải kết nối tới `proxyHost:proxyPort`. Nếu ứng dụng chạy trong cùng Docker network, cấu hình ứng dụng kết nối tới hostname của Toxiproxy và port proxy nội bộ.

Trong test thật, bảo đảm toàn bộ request của client đi qua proxy. Nếu một số request vẫn kết nối trực tiếp tới registry hoặc Config Server, việc thêm toxic sẽ không tác động đến các request đó.

Quản lý vòng đời network và container bằng JUnit/Testcontainers extension hoặc đóng chúng trong khối cleanup. Không để proxy/container tồn tại sau test vì có thể làm ảnh hưởng các lần chạy tiếp theo.

### 4.4. Tạo latency và jitter

Toxiproxy cho phép thêm latency và jitter vào luồng TCP:

~~~java
import eu.rekawek.toxiproxy.model.ToxicDirection;

proxy.toxics()
        .latency(
                "registry-latency",
                ToxicDirection.DOWNSTREAM,
                1_100
        )
        .setJitter(100);
~~~

Với cấu hình trên, độ trễ downstream dao động quanh 1.100 ms, có jitter khoảng 100 ms theo mô hình của Toxiproxy. Có thể thêm toxic ở upstream để kiểm tra độ trễ hai chiều.

Kết quả cần đo:
- Request latency p50/p95/p99.
- Số request vượt deadline.
- Số lần retry.
- Số connection đang chờ.
- Tỷ lệ lỗi của caller.
- Thread/connection pool có tăng liên tục hay không.

### 4.5. Cắt kết nối hai chiều

Có thể chặn dữ liệu đi qua proxy bằng bandwidth toxic với giới hạn bằng 0:

~~~java
proxy.toxics().bandwidth(
        "cut-downstream",
        ToxicDirection.DOWNSTREAM,
        0
);

proxy.toxics().bandwidth(
        "cut-upstream",
        ToxicDirection.UPSTREAM,
        0
);
~~~

Khi muốn phục hồi đường truyền, xóa hai toxic:

~~~java
proxy.toxics().get("cut-downstream").remove();
proxy.toxics().get("cut-upstream").remove();
~~~

Testcontainers Toxiproxy cũng hỗ trợ timeout, slow close và các kiểu biến đổi luồng dữ liệu khác. Hãy chọn toxic theo failure mode cần mô phỏng.

### 4.6. Kiểm tra cả lỗi và phục hồi

Một test khái quát có thể thực hiện theo thứ tự:

~~~java
@Test
void clientRecoversAfterNetworkIsRestored() {
    assertThat(registryGateway.listServices())
            .contains("inventory-service");

    cutConnection(proxy);

    assertThatThrownBy(() -> registryGateway.listServices())
            .isInstanceOf(RegistryUnavailableException.class);

    restoreConnection(proxy);

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() ->
            assertThat(registryGateway.listServices())
                    .contains("inventory-service")
    );
}
~~~

`RegistryGateway` và `RegistryUnavailableException` là lớp wrapper do ứng dụng định nghĩa trong ví dụ. Exception thật phụ thuộc DiscoveryClient/provider; hãy kiểm tra loại lỗi thực tế và chuẩn hóa nó ở lớp ứng dụng nếu cần.

Ví dụ dùng Awaitility cho assertion có thời hạn; thêm dependency test tương ứng nếu dự án chưa có. Khi phục hồi, client có thể cần mở connection mới. Nếu pool còn giữ socket đã hỏng, hãy kiểm tra cơ chế validation/eviction của pool. Không dùng `Thread.sleep` cố định để chờ phục hồi; dùng polling có deadline và assertion lặp lại.

### 4.7. Giới hạn của Toxiproxy

Toxiproxy tác động lên TCP stream. Nó phù hợp để tạo latency, jitter, bandwidth restriction, timeout và interruption. Nó không thay thế một bài test DNS resolver, certificate authority hoặc lỗi ở tầng ứng dụng HTTP.

Để kiểm tra DNS failure, dùng DNS server/container riêng hoặc môi trường test có thể điều khiển resolver. Để kiểm tra TLS, dùng test certificate hết hạn, sai hostname hoặc truststore không tin cậy. Để kiểm tra HTTP 401/404/500, dùng mock server hoặc test server trả status tương ứng.

## 5. Kiểm chứng hành vi khi registry mất kết nối

### 5.1. Tách registry outage khỏi instance outage

Hai tình huống này khác nhau:

- **Registry outage:** client không truy cập được hệ thống lưu trữ/tra cứu service registration.
- **Service instance outage:** registry vẫn hoạt động nhưng một hoặc nhiều instance không còn phục vụ.
- **Stale registration:** registry còn lưu instance đã chết hoặc client đang giữ danh sách instance cũ.
- **Registration delay:** instance mới đã khởi động nhưng chưa xuất hiện trong registry hoặc chưa được client nhìn thấy.

Mỗi tình huống ảnh hưởng tới một lớp khác nhau. Không dùng một test “registry down” để kết luận hệ thống xử lý tốt mọi lỗi service discovery.

### 5.2. Kiểm tra startup khi registry chưa sẵn sàng

Tạo test khởi động ứng dụng trong khi registry container chưa start hoặc proxy đang chặn kết nối.

Xác định trước policy:

| Policy | Expected behavior |
| --- | --- |
| Discovery là bắt buộc để phục vụ request | Startup có thể thất bại hoặc readiness chưa chuyển sang accepting traffic. |
| Discovery là tùy chọn | Ứng dụng có thể khởi động với local mode/fallback đã thiết kế. |
| Registry chỉ dùng cho đăng ký instance | Ứng dụng có thể chạy nhưng không được coi là đã đăng ký thành công. |
| Registry được dùng để tìm Config Server | Startup còn phụ thuộc khả năng discovery-first lookup và Config Client policy. |

Không để ứng dụng báo sẵn sàng khi một dependency bắt buộc chưa được kiểm chứng. Ngược lại, không để một registry phụ trợ làm restart loop toàn bộ instance nếu ứng dụng vẫn có khả năng phục vụ bằng cơ chế dự phòng đã được kiểm thử.

### 5.3. Kiểm tra registry mất kết nối sau khi ứng dụng đã chạy

Thực hiện test theo trình tự:

1. Khởi động registry và ứng dụng.
2. Đăng ký ít nhất hai instance của một service.
3. Gửi request để làm ấm cache instance list nếu LoadBalancer đang dùng cache.
4. Cắt kết nối giữa ứng dụng và registry.
5. Tiếp tục gửi request trong thời gian ngắn hơn TTL cache.
6. Gửi request sau khi cache hết hạn.
7. Khôi phục kết nối.
8. Xác minh client lấy lại danh sách instance mới và request thành công.

Mục đích là phân biệt hành vi với cache đã có dữ liệu và hành vi khi cache rỗng/hết hạn.

### 5.4. Cache không phải cam kết last-known-good

Spring Cloud LoadBalancer có cache cho `ServiceInstanceListSupplier`. Cấu hình mặc định hiện hành có TTL 35 giây. Cache giúp tránh truy vấn discovery ở mọi lần chọn instance, nhưng không phải một cam kết chung rằng client luôn trả danh sách cũ khi registry lỗi.

Kết quả sau khi cache hết hạn phụ thuộc supplier, provider, cache và cách exception được xử lý. Hãy kiểm thử cụ thể:
- Cache đã có instance trước outage.
- Cache chưa từng có dữ liệu.
- Cache hết hạn trong lúc registry vẫn down.
- Registry trả danh sách rỗng nhưng không ném exception.
- Registry phục hồi và danh sách instance thay đổi.

Nếu ứng dụng yêu cầu stale instance fallback, hãy thiết kế rõ TTL, giới hạn thời gian dùng dữ liệu cũ và điều kiện loại instance đã biết là không khỏe. Không dựa vào một hành vi cache ngầm chưa được kiểm thử.

### 5.5. Kiểm tra HealthCheckServiceInstanceListSupplier

`HealthCheckServiceInstanceListSupplier` có thể kiểm tra định kỳ các instance do delegate supplier cung cấp. Tài liệu Spring Cloud khuyến nghị cơ chế này đặc biệt hữu ích với `SimpleDiscoveryClient` hoặc service có ít instance; với registry thực, trạng thái healthy thường đã được registry cung cấp.

Một chi tiết cần kiểm chứng là khi không có instance nào vượt qua health check, supplier có thể trả lại toàn bộ danh sách đã truy xuất thay vì trả danh sách rỗng. Vì vậy, đừng mặc định health-check supplier sẽ luôn loại bỏ mọi instance lỗi trong mọi tình huống.

Nếu dùng `HealthCheckServiceInstanceListSupplier`, kiểm tra:
- Initial delay và interval.
- Health-check path theo service ID.
- Timeout cho mỗi health request.
- Hành vi khi endpoint health không phản hồi.
- Hành vi khi tất cả instance unhealthy.
- Cache của supplier và việc refetch instance list.

Không thêm health-check polling chồng lên registry-backed discovery một cách mặc định; nó có thể tạo request phụ mà không đem lại thông tin mới.

### 5.6. Kiểm tra đăng ký và hủy đăng ký

Spring Cloud Commons có abstraction `ServiceRegistry` với thao tác register/deregister. Test nên xác minh:

- Registry không sẵn sàng lúc instance đăng ký.
- Đăng ký thất bại được log/metric và retry theo policy.
- Instance không tự nhận rằng đã đăng ký khi provider trả lỗi.
- Registry phục hồi thì cơ chế đăng ký lại hoạt động.
- Khi shutdown bình thường, deregister được thực hiện.
- Khi process bị kill đột ngột, lease/heartbeat/TTL của provider loại instance cũ theo đúng cấu hình.

Giá trị `spring.cloud.service-registry.auto-registration.fail-fast` và các property của provider có thể ảnh hưởng startup. Kiểm tra BOM và provider cụ thể trước khi xác định expected behavior.

## 6. Kiểm chứng Config Server mất kết nối lúc startup

### 6.1. Phân biệt config import tùy chọn và bắt buộc

Với Spring Boot Config Data import, ví dụ tùy chọn:

~~~properties
spring.config.import=optional:configserver:
~~~

Prefix `optional:` cho phép ứng dụng tiếp tục startup khi Config Server không truy cập được. Nếu bỏ `optional:`, Config Client sẽ fail startup khi không thể lấy config server data.

Đây là một quyết định kiến trúc:

| Cấu hình | Expected behavior khi Config Server down |
| --- | --- |
| `optional:configserver:` | Startup có thể tiếp tục; ứng dụng phải có local defaults đủ an toàn. |
| `configserver:` | Startup thất bại nếu Config Server không thể cung cấp property source. |
| Legacy bootstrap với `spring.cloud.config.fail-fast=true` | Client dừng startup bằng exception khi không thể kết nối. |
| Legacy bootstrap với fail-fast false | Hành vi phụ thuộc bootstrap/config client và các tùy chọn retry/fallback. |

Không dùng `optional:` chỉ để deployment luôn xanh. Nếu thiếu remote config khiến ứng dụng kết nối nhầm database, bỏ xác thực hoặc chạy sai chế độ, startup thành công là kết quả không an toàn.

### 6.2. Thiết kế local fallback rõ ràng

Khi Config Server là optional, các giá trị local phải được phân loại:

- **Bắt buộc:** database endpoint, security mode, credential reference, tenant hoặc encryption policy.
- **Có thể có default an toàn:** mức log, giới hạn cache, feature không ảnh hưởng tính toàn vẹn.
- **Không được tự tạo default:** secret, signing key, trust policy hoặc endpoint production nhạy cảm.

Test phải chứng minh rằng thiếu remote property không khiến ứng dụng dùng một giá trị mặc định nguy hiểm. Có thể dùng startup validation để fail nếu property bắt buộc vẫn thiếu.

### 6.3. Kiểm tra fail-fast và retry

Spring Cloud Config Client hỗ trợ fail-fast và retry. Với cấu hình retry theo tài liệu hiện hành:
- Bật `spring.cloud.config.fail-fast=true`.
- Thêm `spring-retry` và `spring-boot-starter-aop` vào classpath.
- Default retry là sáu lần, initial backoff 1.000 ms và multiplier 1.1.
- Có thể điều chỉnh `spring.cloud.config.retry.*`.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    config:
      fail-fast: true
      retry:
        max-attempts: 8
        initial-interval: 1000
        max-interval: 5000
        multiplier: 1.5
~~~

Đây là cấu hình minh họa; tổng thời gian startup còn phụ thuộc connect timeout, read timeout, số Config Server URL và thời gian phản hồi của server.

Với Config Data import, bỏ prefix `optional:` có tác dụng fail-fast tương đương. Nếu `spring.config.import` nằm trong profile-specific file, retry options có thể phải được đặt trong URL query của import theo hướng dẫn đúng version.

### 6.4. Kiểm tra connect và read timeout

Spring Cloud Config Client cung cấp:

~~~yaml
spring:
  cloud:
    config:
      request-connect-timeout: 2000
      request-read-timeout: 5000
~~~

Các giá trị trên tính bằng milliseconds:
- Connect timeout giới hạn thời gian thiết lập kết nối.
- Read timeout giới hạn thời gian chờ response sau khi kết nối được tạo.

Trong test, tạo ít nhất hai kịch bản riêng:
1. Config Server không chấp nhận TCP connection.
2. Config Server chấp nhận connection nhưng trì hoãn response vượt read timeout.

Nếu chỉ test server dừng hoàn toàn, bạn chưa kiểm chứng được read timeout.

### 6.5. Kiểm tra nhiều Config Server URL

Config Client có thể thử nhiều Config Server URL theo thứ tự. Với `spring.cloud.config.uri`, mặc định strategy là `always`; có thể chọn `connection-timeout-only` để chỉ failover trong một số lỗi kết nối/timeout. HTTP 401 hoặc 500 không tương đương một connection outage thông thường và không nhất thiết kích hoạt fallback sang URL tiếp theo.

Khi dùng nhiều URL qua `spring.config.import`, quy tắc xử lý khác với `spring.cloud.config.uri`; không áp dụng máy móc `multiple-uri-strategy` cho mọi dạng import.

Test cần xác minh:
- URL đầu tiên không kết nối được, URL thứ hai hoạt động.
- URL đầu tiên trả 401 do credential sai.
- URL đầu tiên trả 500.
- Cả hai URL đều lỗi.
- Config Server trả property source nhưng thiếu key bắt buộc.

### 6.6. Phân biệt Config Server outage với Git backend outage

Config Server có thể vẫn chạy và trả HTTP response trong khi Git repository dùng làm nguồn cấu hình không truy cập được. Đây là một failure mode riêng, vì Config Server có thể giữ local working copy sau lần clone thành công.

Với Git backend:
- Mặc định, Config Server clone repository khi có request đầu tiên. Vì vậy server có thể khởi động thành công dù Git URI sai hoặc Git server đang down; lỗi chỉ xuất hiện khi client yêu cầu cấu hình.
- Đặt `spring.cloud.config.server.git.clone-on-start=true` để kiểm tra repository ngay lúc startup và fail-fast nếu clone không thành công.
- Sau khi clone thành công, Config Server giữ local working copy. Nếu Git remote mất kết nối, server có thể tiếp tục phục vụ revision trong local copy khi branch và file được yêu cầu vẫn tồn tại.
- `spring.cloud.config.server.git.refresh-rate` mặc định là `0`, nghĩa là fetch Git khi có request. Giá trị dương đặt chu kỳ refresh tính bằng giây. Trong lúc remote down, fetch thất bại và local copy vẫn ở revision đã fetch gần nhất; khi remote phục hồi, lần fetch tiếp theo có thể cập nhật local copy.
- Nếu Config Server khởi động lại khi Git remote đang down và chưa có local clone, request cấu hình có thể thất bại. Client giữ cấu hình hiện tại trong lần refresh thất bại theo hành vi được tài liệu mô tả.

Kiểm thử riêng ba tình huống:
1. Config Server đã clone thành công, sau đó cắt kết nối Git remote và xác minh server còn phục vụ revision cũ.
2. Restart Config Server khi Git remote down và lazy clone được bật; xác minh request đầu tiên thất bại.
3. Bật `clone-on-start` rồi khởi động Config Server khi Git remote down; xác minh startup fail-fast.

Không nhầm local working copy của Config Server với cache ở Config Client. Chúng nằm ở hai process khác nhau, có vòng đời và thời điểm cập nhật khác nhau. Với backend Vault, filesystem hoặc custom EnvironmentRepository, thiết kế kịch bản tương ứng theo semantics của backend đó.

## 7. Kiểm chứng nguồn cấu hình bị mất sau startup

### 7.1. Startup thành công không chứng minh refresh sẽ thành công

Sau khi ứng dụng đã tải remote config, giá trị trong Environment và bean có thể tiếp tục được dùng khi Config Server tạm thời không truy cập được. Nhưng không nên giả định rằng lần refresh tiếp theo sẽ tự động dùng lại last-known-good configuration trong mọi version và mọi kiểu bootstrap.

Hãy kiểm tra đúng luồng mà ứng dụng đang sử dụng:
- Config Data import.
- Legacy bootstrap.
- Refresh endpoint.
- Spring Cloud Bus.
- Custom PropertySourceLocator hoặc nguồn cấu hình khác.

### 7.2. Config Client không mặc định polling Environment

Spring Cloud Config Client không mặc định liên tục polling Config Server để tìm thay đổi. Với ứng dụng nhiều instance, Spring Cloud khuyến nghị broadcast `EnvironmentChangeEvent` qua Spring Cloud Bus thay vì để mọi instance polling riêng.

Vì vậy, khi kiểm thử outage runtime, cần tạo hành động refresh thực sự hoặc phát event qua Bus. Chỉ dừng Config Server trong khi không có refresh/polling sẽ không chứng minh client đã xử lý refresh failure.

### 7.3. Kiểm tra /actuator/refresh

Spring Cloud Context cung cấp `RefreshScope` và endpoint `/actuator/refresh`. Refresh làm mới property source/bootstrap context theo cơ chế hiện hành, rebind một số `@ConfigurationProperties` và invalidate target cache của bean `@RefreshScope`.

Một test nên:
1. Khởi động Config Server với revision A.
2. Khởi động client và xác minh bean đang dùng giá trị A.
3. Thay remote config thành revision B.
4. Cắt kết nối Config Server.
5. Gọi refresh endpoint.
6. Ghi nhận response, exception, Environment và behavior của bean.
7. Khôi phục Config Server.
8. Thực hiện refresh lại.
9. Xác minh bean và property phản ánh revision B.

Không kết luận chỉ từ HTTP response của endpoint. Hãy gọi consumer hoặc kiểm tra bean/config properties để xác minh giá trị đã áp dụng.

### 7.4. Rebind và RefreshScope có semantics khác nhau

`EnvironmentChangeEvent` có thể khiến `@ConfigurationProperties` được rebind. `@RefreshScope` dùng proxy và cache target; refresh sẽ invalidate cache để bean được khởi tạo lại ở lần sử dụng tiếp theo.

Trong test outage, quan sát riêng:
- Bean singleton không refresh.
- Bean `@ConfigurationProperties` được rebind.
- Bean `@RefreshScope` được khởi tạo lại.
- Bean không thể refresh hoặc bị cấu hình vào `never-refreshable`.
- Constructor-bound configuration properties, bao gồm Java record, không được refresh theo cùng cơ chế.

Một refresh event không có nghĩa mọi object trong ApplicationContext đều được thay thế.

### 7.5. Kiểm tra cấu hình bị xóa

Khi remote property bị xóa rồi refresh, presence của property không nhất thiết được cập nhật giống như thay đổi value. Spring Cloud Context có lưu ý rằng việc loại bỏ một configuration value rồi refresh không tự cập nhật sự hiện diện của key theo mọi trường hợp.

Test riêng:
- Thay value A thành B.
- Xóa key khỏi remote config.
- Đặt key thành empty hoặc null nếu source hỗ trợ.
- Refresh và kiểm tra consumer.

Nếu logic phụ thuộc vào sự vắng mặt của key, hãy thiết kế semantics rõ ràng và kiểm thử theo version đang dùng.

## 8. Kiểm chứng Spring Cloud Bus khi broker gián đoạn

### 8.1. Bus thêm một dependency khác

`/actuator/busrefresh` và `/actuator/busenv` dùng Spring Cloud Bus để truyền thay đổi tới nhiều instance. Ngoài Config Server, luồng này còn phụ thuộc broker và binder (ví dụ RabbitMQ hoặc Kafka).

Do đó cần tách:
- Config Server down.
- Message broker down.
- Client không kết nối broker.
- Một instance tạm thời mất kết nối broker.
- Message đã dispatch nhưng consumer chưa nhận.
- Consumer nhận message nhưng refresh thất bại.

### 8.2. Kiểm tra từng giai đoạn

| Giai đoạn | Bằng chứng cần có |
| --- | --- |
| Admin gửi lệnh | Request được xác thực và được nhận. |
| Bus publish | Producer gửi message thành công theo contract của binder. |
| Broker nhận message | Message được broker accept/persist theo cấu hình. |
| Instance consume | Consumer nhận event có correlation ID. |
| Instance refresh | Environment/bean của instance phản ánh config revision mới. |
| Toàn bộ rollout | Các instance mục tiêu đã báo trạng thái applied hoặc failure. |

HTTP response 2xx từ endpoint bus không tự chứng minh mọi instance đã áp dụng config. Cần theo dõi event và revision ở từng instance.

### 8.3. Kịch bản broker outage

1. Khởi động broker và nhiều service instance.
2. Gửi một bus refresh bình thường để tạo baseline.
3. Ngắt kết nối broker.
4. Gửi lệnh bus refresh.
5. Xác minh lệnh thất bại hoặc được báo trạng thái phù hợp với binder.
6. Khôi phục broker.
7. Kiểm tra consumer reconnect và channel/binding được phục hồi.
8. Phát một refresh mới hoặc thực hiện reconciliation.
9. Xác minh tất cả instance mục tiêu đã áp dụng revision mong đợi.

Không giả định message gửi trong thời gian broker down chắc chắn được phát lại sau khi broker phục hồi. Điều đó phụ thuộc producer retry, broker durability, consumer offset/ack và binder configuration.

## 9. Thiết kế fallback và last-known-good configuration

### 9.1. Phân loại cấu hình theo mức độ bắt buộc

| Nhóm cấu hình | Khi nguồn remote lỗi | Chính sách gợi ý |
| --- | --- | --- |
| Security-critical | Không được dùng giá trị mặc định lỏng lẻo. | Fail startup hoặc từ chối operation phụ thuộc cấu hình. |
| Connection-critical | Có thể cần để kết nối database/registry. | Chỉ fallback sang endpoint đã được phê duyệt. |
| Business-critical | Có thể ảnh hưởng giá, hạn mức hoặc routing. | Dùng revision đã kiểm chứng hoặc ngừng xử lý nghiệp vụ tương ứng. |
| Operational tuning | Có thể có local default an toàn. | Cho phép chạy với cảnh báo và ghi nhận config revision. |
| Optional feature | Có thể tắt feature khi thiếu config. | Degrade có giới hạn và thể hiện trạng thái rõ ràng. |

### 9.2. Ghi nhận config revision

Khi ứng dụng tải cấu hình, nên có metadata revision không nhạy cảm như:
- Git commit/label.
- Config bundle version.
- Environment/profile.
- Thời điểm tải gần nhất.
- Nguồn cấu hình.
- Kết quả refresh gần nhất.

Không ghi giá trị secret vào log/metric. Revision giúp xác định instance nào còn chạy cấu hình cũ khi remote source hoặc Bus gặp sự cố.

### 9.3. Không biến fallback thành trạng thái ẩn

Nếu ứng dụng tiếp tục dùng last-known-good config, cần thể hiện:
- Revision đang sử dụng.
- Nguồn config hiện không truy cập được.
- Thời điểm lần tải thành công gần nhất.
- Có bao nhiêu instance đang dùng revision cũ.
- Thời hạn tối đa được phép tiếp tục dùng config cũ.

Khi quá thời hạn cho phép, có thể chuyển readiness sang refusing traffic hoặc từ chối các operation nhạy cảm. Không tự động đánh dấu health UP chỉ vì process vẫn chạy.

### 9.4. Không tự động fallback khi credential sai

Config Server trả 401/403 thường cho biết vấn đề authentication/authorization. Dùng một config source khác hoặc local defaults trong trường hợp này có thể che giấu credential hết hạn hoặc cấu hình sai. Chỉ failover sang endpoint khác khi policy xác định đó là replica tương đương và quy tắc credential đã được kiểm thử.

## 10. Failure matrix cho ba nhóm dependency

| ID | Sự cố | Điểm bắt đầu | Expected behavior cần kiểm tra |
| --- | --- | --- | --- |
| N1 | DNS không phân giải được | Trước startup | Startup/retry/fail-fast theo policy. |
| N2 | Registry port connection refused | Runtime | Request timeout hữu hạn, log/metric có phân loại. |
| N3 | Registry latency cao | Runtime | Deadline, retry budget và pool không bị cạn. |
| N4 | TCP bị cắt | Runtime | Client nhận lỗi và có thể kết nối lại sau recovery. |
| N5 | Kết nối chỉ lỗi upstream | Runtime | Client không treo vô hạn, không nhân đôi side effect. |
| R1 | Registry down trước startup | Startup | Registration/readiness theo policy. |
| R2 | Registry down sau khi cache ấm | Runtime | Xác minh hành vi cache trong TTL. |
| R3 | Registry down sau khi cache hết hạn | Runtime | Xác minh supplier/provider behavior khi không lấy được instance list. |
| R4 | Registry trả danh sách rỗng | Runtime | Caller xử lý no-instance rõ ràng. |
| R5 | Instance chết nhưng registration còn | Runtime | Phát hiện stale instance và retry/fallback. |
| R6 | Registry phục hồi | Recovery | Instance list cập nhật và request trở lại bình thường. |
| C1 | Config Server down, import bắt buộc | Startup | Startup thất bại trong giới hạn timeout/retry. |
| C2 | Config Server down, import optional | Startup | Startup chỉ tiếp tục nếu local config đủ an toàn. |
| C3 | Config Server chậm | Startup | Read timeout và retry budget được tuân thủ. |
| C4 | Config Server trả 401 | Startup | Lỗi authentication được báo rõ, không giả thành network outage. |
| C5 | Config Server trả 500 | Startup | Xác minh failover/retry theo policy. |
| C6 | Config Server down khi refresh | Runtime | Giá trị cũ/mới và lỗi refresh được quan sát rõ. |
| C7 | Config Server phục hồi | Recovery | Refresh tiếp theo tải đúng revision. |
| B1 | Bus broker down | Runtime | Publish/consume failure được nhận diện. |
| B2 | Một consumer offline | Runtime | Xác minh delivery/reconciliation cho instance đó. |
| B3 | Bus phục hồi | Recovery | Instance reconnect và áp dụng revision đúng. |

## 11. Đo khả năng chịu lỗi và phục hồi

### 11.1. Chỉ số cần thu thập

| Chỉ số | Ý nghĩa |
| --- | --- |
| Failure detection time | Thời gian từ khi bắt đầu lỗi đến khi ứng dụng nhận biết. |
| Recovery time | Thời gian từ khi dependency phục hồi đến khi ứng dụng hoạt động lại. |
| Retry attempts | Số lần thử lại cho mỗi operation. |
| Retry exhaustion | Số operation hết retry budget. |
| Request error rate | Tỷ lệ request lỗi trong và sau outage. |
| Request latency | p50/p95/p99 khi dependency chậm. |
| Connection pool saturation | Số connection đang dùng/chờ và số lần acquire timeout. |
| Cache age | Tuổi của instance list/config revision đang được dùng. |
| Config revision lag | Chênh lệch revision giữa các instance. |
| Registry registration lag | Thời gian từ startup đến khi instance xuất hiện trong registry. |

### 11.2. Retry phải có budget

Retry có thể tăng khả năng thành công khi lỗi ngắn hạn, nhưng retry đồng thời từ hàng trăm instance có thể tạo retry storm khi dependency vừa phục hồi.

Kiểm tra:
- Exponential backoff.
- Jitter.
- Maximum attempts.
- Maximum elapsed time.
- Retry chỉ với lỗi tạm thời.
- Không retry lỗi validation hoặc authorization.
- Không retry operation không idempotent nếu không có idempotency key.

Với Config Client, dùng retry properties mà Spring Cloud Config cung cấp. Với các service call khác, kiểm tra retry policy của client, Spring Cloud CircuitBreaker hoặc cơ chế resilience mà ứng dụng đã tích hợp.

### 11.3. Circuit breaker và bulkhead

Nếu caller có circuit breaker, kiểm thử:
- Circuit chuyển OPEN sau ngưỡng lỗi.
- Request mới được fail-fast hoặc fallback.
- Circuit chuyển HALF_OPEN sau thời gian chờ.
- Probe thành công làm circuit CLOSED.
- Probe thất bại giữ circuit OPEN.
- Một dependency lỗi không chiếm toàn bộ thread/connection pool của ứng dụng.

Bulkhead có thể giới hạn số request đồng thời tới dependency. Kiểm tra queue không tăng vô hạn khi dependency chậm.

### 11.4. Kiểm tra retry amplification

Ví dụ nếu mỗi request retry bốn lần và 100 instance cùng gửi 50 request/giây, dependency có thể nhận số lần gọi lớn hơn nhiều so với lưu lượng gốc. Khi thử nghiệm, đo tổng số request tới registry/Config Server, không chỉ số request từ caller.

Khi dependency phục hồi, theo dõi xem backlog có tạo đợt tải tăng đột biến hay không.

## 12. Health, readiness và liveness trong lúc outage

### 12.1. Health endpoint không tự định nghĩa chính sách traffic

Actuator có thể hiển thị trạng thái các health contributor. Nhưng việc một dependency down có làm instance ngừng nhận traffic hay không phụ thuộc health group và orchestration policy.

Không thêm mọi dependency bên ngoài vào mọi health group. Hãy xác định dependency nào thực sự cần thiết để instance nhận request mới.

### 12.2. Không đưa registry hoặc Config Server vào liveness một cách máy móc

Liveness nên phản ánh process có thể tiếp tục chạy hay không. Nếu registry hoặc Config Server tạm thời mất kết nối mà liveness chuyển DOWN, Kubernetes có thể restart hàng loạt instance và làm sự cố nặng hơn.

Readiness có thể bao gồm một dependency nếu thiếu nó khiến instance không thể xử lý request mới. Nếu ứng dụng có cache/fallback/circuit breaker và vẫn phục vụ được, có thể không nên đưa dependency đó vào readiness.

### 12.3. Kiểm tra health groups

Spring Boot cung cấp các health group:
- `/actuator/health/liveness`
- `/actuator/health/readiness`

Có thể cấu hình readiness group bao gồm một custom contributor hoặc contributor hiện có:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,discoveryComposite
~~~

`discoveryComposite` ở ví dụ là contributor ID cần được xác minh từ response thực tế của ứng dụng. Nếu ID khác, dùng đúng ID mà Actuator đang công bố.

### 12.4. Kiểm tra cả management port và application port

Nếu Actuator chạy trên management port riêng, health check có thể thành công trong khi application port hoặc connection pool chính đã hỏng. Với Kubernetes, cân nhắc expose probe path trên main server port và kiểm tra đúng connector mà traffic thật sử dụng.

## 13. Kiểm thử Config Client và Config Server theo cấp độ

### 13.1. Unit test cho policy

Dùng unit test để kiểm tra:
- Cách phân loại lỗi transient và permanent.
- Retry count.
- Backoff calculation.
- Fallback decision.
- Config revision validation.
- Không áp dụng cấu hình thiếu property bắt buộc.

Không cần khởi chạy registry hoặc Config Server thật cho các logic thuần này.

### 13.2. Integration test với Config Server thật

Dùng container hoặc test server để kiểm tra:
- Config Client lấy được property từ Config Server.
- Application/profile/label đúng.
- Server down trước startup.
- Server chậm hơn read timeout.
- Server phục hồi sau một số lần retry.
- Config revision thay đổi và refresh áp dụng đúng.

Nếu dùng `spring.config.import`, test nên khởi chạy `SpringApplication` hoặc process/container ứng dụng thực tế. `ApplicationContextRunner` thông thường không tự mô phỏng đầy đủ Config Data bootstrap phase nếu chưa cấu hình environment processing tương ứng.

### 13.3. Kiểm tra sai profile và label

Một số lỗi bị nhầm với network outage:
- Sai `spring.application.name`.
- Sai active profile.
- Label/branch không tồn tại.
- Property source không có key mong đợi.
- Config Server trả 404 vì repo/label không tìm thấy.

Hãy tạo test riêng cho lỗi cấu hình định danh. Không retry vô hạn một label sai.

### 13.4. Kiểm tra refresh runtime

Với `/actuator/refresh`, kiểm tra cả:
- Config Server đang hoạt động.
- Config Server down.
- Config Server trả config cũ.
- Config Server trả revision mới.
- Bean refresh thành công.
- Bean refresh/rebind thất bại.
- Lần refresh tiếp theo sau khi server phục hồi.

Kiểm tra bean consumer thực tế, không chỉ kiểm tra HTTP response của endpoint.

## 14. Kịch bản kiểm thử thực hành: registry outage và recovery

### 14.1. Mục tiêu

Xác minh một service client vẫn xử lý đúng khi registry bị gián đoạn, cache đã ấm và cache hết hạn; sau đó xác minh request phục hồi khi registry hoạt động lại.

### 14.2. Chuẩn bị

- Một registry test instance.
- Một service có ít nhất hai instance đăng ký.
- Một client dùng Spring Cloud LoadBalancer.
- Toxiproxy nằm giữa client và registry.
- Một endpoint downstream có thể trả response xác định.
- Metric/log cho request, retry và discovery.

### 14.3. Thực hiện

1. Khởi động registry và provider instances.
2. Xác minh hai instance xuất hiện trong registry.
3. Gửi request qua LoadBalancer để làm ấm instance list cache.
4. Cắt kết nối giữa client và registry bằng Toxiproxy.
5. Gửi request liên tục trong một khoảng ngắn.
6. Ghi lại instance được chọn và tỷ lệ request thành công.
7. Chờ cache TTL hết hạn theo cấu hình test.
8. Gửi request tiếp và ghi lại lỗi/no-instance/fallback.
9. Khôi phục kết nối registry.
10. Chờ client lấy được instance list mới.
11. Gửi request và xác minh kết quả thành công.
12. Kiểm tra cache age, retry count và recovery time.

### 14.4. Tiêu chí PASS

- Không có request treo vô hạn.
- Retry không vượt budget.
- Khi cache còn hiệu lực, hành vi khớp policy đã chọn.
- Khi cache hết hạn và registry vẫn down, lỗi được trả về trong deadline.
- Khi registry phục hồi, client lấy lại danh sách instance.
- Không cần restart ứng dụng nếu policy yêu cầu tự phục hồi.
- Log/metric đủ để phân biệt registry outage và downstream instance outage.

Không quy định một kết quả chung cho mọi provider. Một số DiscoveryClient có cache riêng hoặc có semantics khác nhau; expected result phải gắn với provider và cấu hình thực tế.

## 15. Kịch bản kiểm thử thực hành: Config Server outage

### 15.1. Mục tiêu

Xác minh chính sách startup khi Config Server không truy cập được và xác minh ứng dụng có thể tải revision mới sau khi nguồn cấu hình phục hồi.

### 15.2. Các biến thể cần chạy

| Biến thể | Cấu hình | Kết quả mong đợi |
| --- | --- | --- |
| A | `optional:configserver:` và local config đầy đủ | App khởi động, ghi nhận remote source unavailable. |
| B | `configserver:` bắt buộc, server down | App fail startup trong timeout/retry budget. |
| C | Config import bắt buộc, server phục hồi trong retry window | App khởi động sau khi fetch thành công. |
| D | Config import bắt buộc, server phục hồi sau retry window | Startup thất bại; deployment retry theo policy. |
| E | Server trả 401 | Lỗi authentication được báo rõ, không giả thành network outage. |
| F | Server trả 404 do label sai | Báo lỗi resource/profile/label. |
| G | Server chậm hơn read timeout | Client timeout theo cấu hình. |
| H | Server phục hồi sau khi app đã chạy | Refresh tiếp theo lấy được revision mới. |

### 15.3. Tiêu chí PASS

- Optional và mandatory import có behavior khác nhau đúng thiết kế.
- Không có secret/default nguy hiểm khi remote config thiếu.
- Retry dừng trong budget.
- Timeout connect/read được áp dụng.
- Lỗi 401/404 không bị ghi nhận nhầm là lỗi DNS.
- Config revision mới được áp dụng sau recovery.
- Các instance có thể được đối chiếu revision sau khi refresh.

## 16. Kịch bản kiểm thử thực hành: Bus và refresh trên nhiều instance

### 16.1. Mục tiêu

Xác minh một thay đổi cấu hình được truyền tới các instance mục tiêu và phát hiện được instance chưa áp dụng.

### 16.2. Thực hiện

1. Khởi động broker và ba service instance.
2. Xác minh mỗi instance đang dùng config revision A.
3. Cập nhật Config Server sang revision B.
4. Gửi bus refresh.
5. Ghi nhận dispatch ID/correlation ID.
6. Ngắt kết nối broker hoặc tạm dừng một consumer.
7. Quan sát instance nào đã áp dụng B và instance nào vẫn dùng A.
8. Khôi phục broker/consumer.
9. Gửi refresh/reconciliation theo policy.
10. Xác minh mọi instance mục tiêu đã áp dụng B hoặc được đánh dấu chưa đồng bộ.

### 16.3. Tiêu chí PASS

- Có thể phân biệt message dispatch thành công với instance applied.
- Instance offline không bị âm thầm xem là đã cập nhật.
- Consumer reconnect theo policy.
- Có cách reconciliation cho instance bị bỏ lỡ event.
- Config revision cuối cùng nhất quán hoặc có cảnh báo drift rõ ràng.

## 17. Quan sát và chẩn đoán trong khi kiểm thử

### 17.1. Log

Log nên thể hiện:
- Dependency/service ID.
- Operation và request ID.
- Failure category: DNS, connect timeout, read timeout, HTTP status, TLS.
- Retry attempt và backoff.
- Config revision hoặc registry cache age.
- Kết quả recovery.

Không ghi password, token, private key hoặc toàn bộ configuration value vào log. Dùng reason code và metadata đã được allowlist.

### 17.2. Metrics

Theo dõi:
- Request count/error count theo dependency.
- Latency histogram.
- Retry count.
- Circuit breaker state.
- Connection pool active/idle/pending.
- LoadBalancer selected instance và no-instance result.
- Cache hit/miss/eviction nếu implementation cung cấp.
- Config refresh success/failure.
- Config revision lag giữa các instance.

Không tạo metric tag có giá trị cardinality cao như request ID, trace ID hoặc full URL.

### 17.3. Tracing

Trace có thể cho biết thời gian ở discovery lookup, Config Server request, broker publish/consume và downstream call. Khi fault injection, so sánh trace bình thường với trace có latency để xác định phần thời gian tăng thêm.

Sampling có thể làm mất một số trace; dùng metric và log để bổ sung bằng chứng. Không đưa secret vào baggage hoặc span attributes.

### 17.4. Health và condition report

Actuator health giúp quan sát trạng thái hiện tại. Condition report hữu ích khi bean discovery/config client không được auto-configure như mong đợi. Tuy nhiên, health UP không chứng minh mọi service ID có instance hoặc mọi config property đã đồng bộ.

Đọc health cùng với config revision, registry status và request behavior.

## 18. Quy trình chạy chaos test an toàn

1. Chạy trước trong local hoặc CI với dependency/container cô lập.
2. Chọn một service instance hoặc một đường kết nối duy nhất làm blast radius ban đầu.
3. Xác định baseline trước khi inject lỗi.
4. Đặt thời lượng lỗi ngắn và có giới hạn.
5. Thiết lập stop condition: error rate, latency, queue hoặc resource usage vượt ngưỡng.
6. Có lệnh phục hồi proxy/container và xác nhận kết nối được khôi phục.
7. Chạy một loại failure mode mỗi lần trước khi kết hợp nhiều lỗi.
8. Lưu test input, toxic parameters, thời điểm bắt đầu/kết thúc và kết quả.
9. Chạy lại cùng scenario để xác minh tính lặp lại.
10. Chỉ mở rộng sang staging/production khi có phê duyệt, monitoring và rollback phù hợp.

Không chạy chaos test trên registry, Config Server hoặc broker dùng chung của production khi chưa giới hạn được tác động. Một thử nghiệm mạng có thể ảnh hưởng mọi service cùng dùng dependency đó.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test không bị ảnh hưởng khi cắt proxy | Client còn kết nối trực tiếp tới dependency. | Kiểm tra URL và toàn bộ network path có đi qua proxy. |
| Test timeout kéo dài hơn dự kiến | Connect/read timeout hoặc retry budget chưa được giới hạn. | Tách timeout từng lớp và tính tổng deadline. |
| Request vẫn thành công khi registry down | LoadBalancer đang dùng instance list cache còn hiệu lực. | Kiểm tra cache warm/cold và TTL riêng. |
| Request thất bại ngay dù registry mới down | Cache chưa có dữ liệu, đã hết hạn hoặc provider không cache. | Kiểm tra cache config và provider behavior. |
| Registry phục hồi nhưng client vẫn lỗi | Connection pool giữ socket cũ hoặc cache chưa được refresh. | Kiểm tra reconnect, cache eviction và request mới. |
| Health UP nhưng không tìm thấy service | Health check chỉ chứng minh discovery API gọi được, không xác minh service ID cụ thể. | Kiểm tra service registration và tạo dependency check riêng nếu cần. |
| App startup thành công nhưng thiếu property quan trọng | Config import là optional hoặc local fallback không đủ validation. | Phân loại required property và fail startup khi thiếu. |
| App fail startup dù Config Server đã phục hồi | Retry window đã hết hoặc client không retry theo cấu hình hiện tại. | Kiểm tra fail-fast, retry dependency, import URL params và timeout. |
| Config Server 401 bị retry như outage | Retry/failover policy không phân biệt lỗi auth. | Kiểm tra credential, multiple URI strategy và phân loại status. |
| Refresh trả thành công nhưng bean dùng value cũ | Bean không thuộc RefreshScope, không rebind hoặc consumer giữ reference cũ. | Kiểm tra bean scope, configuration binding và consumer lifecycle. |
| Một số instance không nhận bus refresh | Consumer offline, broker delivery/ack hoặc event routing không đúng. | Theo dõi từng instance và bổ sung reconciliation. |
| Readiness không đổi khi dependency down | Contributor chưa nằm trong readiness group hoặc policy không yêu cầu dependency đó. | Kiểm tra health group và quyết định dependency có bắt buộc nhận traffic hay không. |
| Kubernetes restart tất cả instance khi registry lỗi | External dependency bị đưa vào liveness. | Bỏ external dependency khỏi liveness; cân nhắc readiness. |
| Toxiproxy test flaky | Dùng sleep cố định, chưa chờ container ready hoặc connection reuse. | Dùng readiness check, polling deadline và tạo connection mới sau recovery. |
| Latency test không tái hiện read timeout | Chỉ thêm latency thấp hơn read timeout. | Tạo latency vượt timeout và kiểm tra cả upstream/downstream. |
| DNS failure không được mô phỏng | Toxiproxy chỉ tác động TCP sau khi hostname đã được resolve. | Dùng DNS server/container riêng hoặc test resolver. |
| Retry tạo tải lớn khi dependency phục hồi | Nhiều instance retry đồng thời, thiếu jitter hoặc retry budget. | Thêm backoff/jitter, giới hạn concurrency và theo dõi retry amplification. |
| Config revision giữa các instance không đồng nhất | Bus message bị bỏ lỡ hoặc refresh thất bại cục bộ. | Theo dõi revision per instance và chạy reconciliation. |

## 20. Nguyên tắc vận hành

1. **Định nghĩa expected behavior trước.** Mỗi failure scenario phải có kết quả mong đợi và tiêu chí PASS.
2. **Phân biệt startup và runtime.** Ứng dụng có thể xử lý hai giai đoạn khác nhau.
3. **Tách lỗi mạng khỏi lỗi HTTP.** 401, 404 và 500 không phải cùng một loại outage.
4. **Giới hạn timeout và retry.** Mọi dependency call cần deadline có thể dự đoán.
5. **Kiểm thử cache warm và cold.** Cache có thể che giấu outage trong một khoảng thời gian.
6. **Không coi cache là fallback vô hạn.** Xác định TTL và policy dùng dữ liệu cũ.
7. **Phân loại config required và optional.** Thiếu cấu hình quan trọng phải có phản ứng rõ.
8. **Ghi nhận config revision.** Biết instance nào đang dùng cấu hình cũ.
9. **Kiểm thử refresh thật.** Gọi operation refresh và xác minh bean consumer.
10. **Phân biệt Bus dispatch và apply.** Theo dõi trạng thái trên từng instance.
11. **Không đưa external dependency vào liveness một cách máy móc.** Tránh restart storm.
12. **Đo recovery time.** Dependency phục hồi chưa có nghĩa ứng dụng đã phục hồi.
13. **Dùng fault injection cô lập.** Toxiproxy/test container giúp scenario lặp lại được.
14. **Giữ blast radius nhỏ.** Có thời hạn và stop condition.
15. **Quan sát log, metric, trace và health cùng nhau.** Không kết luận từ một tín hiệu.
16. **Đối chiếu release train.** Retry, bootstrap, cache và health behavior có thể khác giữa các version Spring Cloud/Spring Boot.

## 21. Checklist hoàn thành

- [ ] Phân biệt DNS, connection refused, connect timeout, read timeout, latency và TCP interruption.
- [ ] Viết được failure scenario có expected behavior, recovery và evidence.
- [ ] Đặt Toxiproxy giữa client và dependency trong integration test.
- [ ] Mô phỏng latency/jitter và cắt kết nối hai chiều.
- [ ] Khôi phục proxy và xác minh client tạo kết nối mới.
- [ ] Kiểm tra registry outage trước startup và sau startup.
- [ ] Kiểm tra LoadBalancer với cache warm, cache cold và cache hết TTL.
- [ ] Phân biệt registry outage, stale registration và service instance outage.
- [ ] Kiểm tra startup với optional và mandatory Config Server import.
- [ ] Kiểm tra fail-fast, retry, backoff, connect timeout và read timeout.
- [ ] Kiểm tra Config Server 401, 404, 500 và network timeout riêng biệt.
- [ ] Kiểm tra refresh khi Config Server down và sau khi server phục hồi.
- [ ] Xác minh `@ConfigurationProperties` và `@RefreshScope` consumer.
- [ ] Kiểm tra Bus broker outage và từng instance consumer.
- [ ] Theo dõi config revision trên từng instance.
- [ ] Phân biệt health, readiness và liveness.
- [ ] Đo retry amplification, request latency, failure detection time và recovery time.
- [ ] Có stop condition, rollback và blast radius cho chaos test.
- [ ] Có log/metric/trace đủ để chẩn đoán và không làm lộ secret.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, optional/fail-fast, retry, timeout và nhiều Config Server URL.
- [Spring Cloud Config – Git Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/git-backend.html): lazy clone, clone-on-start, local working copy, refresh rate và hành vi khi Git remote không truy cập được.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): child context theo service ID, caching, TTL, health-check supplier và service instance selection.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ServiceRegistry, auto-registration và registry lifecycle.
- [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): EnvironmentChangeEvent, rebinding, RefreshScope và refresh endpoint.
- [Spring Cloud Bus – Bus Endpoints](https://docs.spring.io/spring-cloud-bus/reference/spring-cloud-bus/bus-endpoints.html): busrefresh, busenv và cập nhật trên nhiều instance.
- [Spring Boot Actuator – Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): health groups, readiness/liveness và cách kiểm tra external state.
- [Testcontainers for Java – Toxiproxy Module](https://java.testcontainers.org/modules/toxiproxy/): tạo TCP proxy, latency/jitter, bandwidth restriction, timeout và ngắt kết nối trong test.

Mỗi release train có thể thay đổi property, retry semantics hoặc implementation cache. Hãy dùng Spring Boot/Spring Cloud BOM của dự án, chạy các scenario trên đúng dependency version và ghi lại kết quả thực tế trước khi đặt policy vận hành cho production.

