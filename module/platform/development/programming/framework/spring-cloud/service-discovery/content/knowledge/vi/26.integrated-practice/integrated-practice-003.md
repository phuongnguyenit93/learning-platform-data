# Đo thời gian từ đăng ký mới đến khi bên gọi nhìn thấy

Một instance mới có thể được registry chấp nhận nhưng consumer chưa nhìn thấy ngay. Registry phải ghi nhận registration và có thể đồng bộ tới node/agent khác; DiscoveryClient phía consumer cập nhật theo chu kỳ fetch, watch hoặc query; LoadBalancer còn có thể giữ danh sách instance trong cache. Vì vậy, thời điểm provider báo đăng ký xong không đồng nghĩa thời điểm caller có thể chọn instance mới.

Bài thực hành này đo thời gian từ lúc registry xác nhận registration mới đến lúc consumer nhìn thấy đúng instance ID, sau đó đo thêm thời điểm request qua Spring Cloud LoadBalancer thực sự tới instance đó. Quy trình áp dụng cho Eureka, Consul và ZooKeeper.

## Mục tiêu

Sau bài thực hành, người học có thể tạo registration mới với instance ID duy nhất, ghi thời điểm registry xác nhận, đo thời điểm health check passing nếu có, đo thời điểm DiscoveryClient trả về instance mới, đo thời điểm LoadBalancer gọi được instance mới, phân tách các lớp độ trễ và báo cáo median, p95, p99 cùng sai số.

Cần một registry, một provider có thể tạo instance mới và một consumer dùng discovery client của registry đó. Có thể chạy local hoặc Docker Compose. Nếu các thành phần chạy trên nhiều host, đồng bộ đồng hồ trước khi so sánh timestamp.

## Mô hình thời gian và các mốc đo

| Mốc | Ý nghĩa | Nơi ghi nhận |
|---|---|---|
| T_req | Bắt đầu gửi lệnh đăng ký | Registrar/test harness |
| T_ack | Registry xác nhận đã nhận registration | Registrar hoặc registry API response |
| T_pass | Health check chuyển passing, nếu có | Consul/registry health API |
| T_seen | DiscoveryClient của consumer lần đầu trả về đúng instance ID | Consumer process |
| T_route | Request qua LoadBalancer lần đầu được xử lý bởi đúng instance ID mới | Provider response + consumer |
| T_done | Kết thúc phép đo hoặc timeout | Test harness |

Các khoảng thời gian chính:

- Registration request latency = T_ack - T_req.
- Health readiness delay = T_pass - T_ack.
- Discovery propagation latency = T_seen - T_ack.
- End-to-end visibility latency = T_seen - T_req.
- Load-balanced reachability latency = T_route - T_ack.
- Độ trễ từ discovery tới route = T_route - T_seen.

Nếu registry không có health check, bỏ T_pass. Nếu mục tiêu chỉ là xác định consumer nhìn thấy instance, T_seen là mốc kết thúc chính; T_route là phép đo bổ sung.

Không dùng thời điểm process bắt đầu hoặc ApplicationReadyEvent làm T_ack. Ứng dụng có thể khởi động trước khi registration được gửi. Cũng không dùng thời điểm dashboard hiển thị service làm T_seen: dashboard và consumer có thể đọc dữ liệu từ các node/cache khác nhau.

### Phân biệt “thấy instance” và “gọi được instance”

DiscoveryClient trả về instance có nghĩa caller đã thấy bản ghi theo API discovery của nó. Request LoadBalanced thành công tới instance mới có nghĩa LoadBalancer đã chọn được instance đó, địa chỉ quảng bá có thể truy cập và provider đã xử lý request.

Một service có thể có nhiều instance cũ và mới. Request đầu tiên tới service có thể được xử lý bởi instance cũ; không thể dùng lần thành công đầu tiên đó làm T_route. Provider phải trả instance ID để consumer xác nhận response đến từ instance mới.

## Kiến trúc thí nghiệm

Dùng một instance provider mới với ID duy nhất, ví dụ inventory-node-run-001. Provider có endpoint trả về instance ID hiện tại. Consumer có hai cách quan sát:

1. Gọi DiscoveryClient.getInstances(serviceId) để xem danh sách instance.
2. Gọi HTTP bằng RestClient có @LoadBalanced để xem LoadBalancer có chọn instance mới hay chưa.

Luồng đo:

    Test harness ghi T_req
        -> Gửi lệnh registration
        -> Registry xác nhận, ghi T_ack
        -> (Consul) chờ check passing, ghi T_pass
        -> Consumer polling DiscoveryClient
        -> Lần đầu thấy expectedInstanceId, ghi T_seen
        -> Consumer gọi qua LoadBalancer
        -> Provider trả instance ID
        -> Lần đầu nhận đúng ID mới, ghi T_route

Nếu muốn đo đúng cache của caller, phần DiscoveryClient và RestClient phải chạy trong chính process consumer đang được đánh giá. Một test harness riêng có DiscoveryClient riêng chỉ đo cache của harness đó, không chứng minh consumer production đã nhìn thấy instance.

## Chuẩn bị môi trường

### Cấu hình provider

Provider cần có service ID ổn định và instance ID riêng cho từng lần chạy. Đặt instance ID qua environment variable để mỗi run có registration mới, không trùng bản ghi cũ.

Ví dụ cấu hình:

    spring:
      application:
        name: inventory-service
    server:
      port: 8080
    app:
      instance-id: ${INSTANCE_ID:inventory-node-run-001}

Provider nên trả instance ID trong body hoặc response header. Ví dụ controller dùng biến môi trường:

    @RestController
    class InstanceInfoController {
        private final Environment environment;

        InstanceInfoController(Environment environment) {
            this.environment = environment;
        }

        @GetMapping("/internal/instance-id")
        String instanceId() {
            return environment.getProperty("app.instance-id");
        }
    }

Endpoint chỉ phục vụ môi trường lab/test. Trong production, không expose metadata nội bộ hoặc instance identifier nếu không có lý do vận hành rõ ràng.

Nếu dùng Eureka, đặt instance ID duy nhất trong cấu hình Eureka hoặc đảm bảo registration tạo ra instance ID không trùng. Nếu dùng Consul, service ID của từng instance phải khác nhau. Với ZooKeeper, mỗi ephemeral node/service instance cần một định danh riêng.

### Cấu hình consumer

Consumer cần dùng đúng discovery starter và registry endpoint của môi trường. Ví dụ Eureka:

    spring:
      application:
        name: order-service
      cloud:
        discovery:
          enabled: true
    eureka:
      client:
        register-with-eureka: true
        fetch-registry: true
        service-url:
          defaultZone: http://eureka-server:8761/eureka/

Ví dụ Consul:

    spring:
      application:
        name: order-service
      cloud:
        consul:
          host: consul-agent
          port: 8500
          discovery:
            enabled: true
            register: true

Ví dụ ZooKeeper:

    spring:
      application:
        name: order-service
      cloud:
        zookeeper:
          connect-string: zk-1:2181,zk-2:2181,zk-3:2181
          discovery:
            enabled: true
            register: true

Các cấu hình trên chỉ minh họa cách kết nối. Consumer phải dùng đúng starter và property của release train đang chạy. Trong Docker Compose, dùng service DNS và container port; không dùng localhost để gọi registry ở container khác.

Consumer cần discovery starter của provider tương ứng và Spring Cloud LoadBalancer nếu muốn dùng URI service ID qua client có @LoadBalanced. Quản lý phiên bản bằng Spring Cloud BOM tương thích với Spring Boot. RestClient chỉ phù hợp với các phiên bản Spring Framework/Spring Cloud có hỗ trợ tích hợp này; ở codebase cũ hơn, có thể dùng RestTemplate được đánh dấu @LoadBalanced và giữ nguyên cách đo T_seen/T_route.

## Ghi nhận sự kiện registration

Tạo một run ID riêng cho mỗi lần thử, ví dụ run-001. Ghi các trường:

| Trường | Ví dụ | Mục đích |
|---|---|---|
| runId | run-001 | Nối log của một lần đo |
| serviceId | inventory-service | Service ID được tra cứu |
| instanceId | inventory-node-run-001 | Nhận diện đúng registration mới |
| registry | consul | Provider đang thử |
| t_req_utc | 2026-11-24T10:00:00.120Z | Thời điểm bắt đầu gửi registration |
| t_ack_utc | 2026-11-24T10:00:00.180Z | Thời điểm registry xác nhận |
| t_pass_utc | 2026-11-24T10:00:00.540Z | Thời điểm health check passing |
| t_seen_utc | 2026-11-24T10:00:01.020Z | Consumer lần đầu thấy instance |
| t_route_utc | 2026-11-24T10:00:01.240Z | Consumer lần đầu gọi đúng instance |

T_req và T_ack nên được ghi tại nơi thực hiện registration. Với API registration đồng bộ, T_ack là lúc nhận response thành công từ registry/agent. Nếu provider tự đăng ký qua lifecycle, lấy log/event registration thành công của client hoặc quan sát bản ghi qua registry API; không suy diễn T_ack từ thời điểm container start.

Với Consul, Agent API có thể chấp nhận service registration trước khi health check chuyển passing. Vì vậy phải ghi T_ack và T_pass riêng. Nếu consumer chỉ truy vấn instance passing, T_seen thường không thể sớm hơn T_pass.

Với Eureka, registry có thể chấp nhận registration trước khi các consumer fetch registry lần tiếp theo. Dashboard thấy instance không chứng minh mọi Eureka client đã cập nhật local registry.

Với ZooKeeper, ghi thời điểm tạo znode/ephemeral node được xác nhận và thời điểm consumer nhận watch event hoặc thấy node qua discovery API. Nếu consumer chưa thiết lập watch/session, thời gian chờ ban đầu có thể khác với các lần cập nhật sau.

## Đồng hồ và sai số đo

### Đo trong cùng một JVM

Nếu T_ack và T_seen được đo trong cùng process, dùng System.nanoTime() để tính duration. Đây là đồng hồ monotonic, không bị nhảy khi NTP chỉnh wall clock.

Ví dụ polling DiscoveryClient trong consumer:

    long startedNanos = System.nanoTime();
    long deadlineNanos = startedNanos + TimeUnit.SECONDS.toNanos(60);
    long pollIntervalMillis = 100;

    while (System.nanoTime() < deadlineNanos) {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("inventory-service");

        boolean found = instances.stream()
            .anyMatch(instance ->
                expectedInstanceId.equals(instance.getInstanceId()));

        if (found) {
            long elapsedNanos = System.nanoTime() - startedNanos;
            long elapsedMillis =
                TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

            log.info("runId={} instanceId={} event=DISCOVERY_SEEN elapsedMs={}",
                runId, expectedInstanceId, elapsedMillis);
            break;
        }

        Thread.sleep(pollIntervalMillis);
    }

Đoạn code giả định đã inject DiscoveryClient, expectedInstanceId và runId. Để duration này thực sự là T_seen - T_ack, startedNanos phải được ghi ngay sau khi cùng process nhận được xác nhận registration. Nếu T_ack đến từ process khác, không so sánh trực tiếp hai giá trị nanoTime.

Nếu consumer chỉ nhận được timestamp T_ack qua message/event, có thể lưu Instant để đối chiếu log; không chuyển giá trị System.nanoTime từ process registrar sang process consumer.

### Đo giữa nhiều process hoặc nhiều host

Dùng timestamp UTC như Instant.now() ở mỗi thành phần và đồng bộ đồng hồ bằng NTP/chrony hoặc cơ chế time synchronization của nền tảng. Ghi lại trạng thái đồng bộ và ước lượng clock offset trước thí nghiệm.

System.nanoTime() chỉ dùng để tính duration trong cùng JVM/process. Không trừ nanoTime của hai container hoặc hai máy khác nhau.

Nếu độ lệch đồng hồ tối đa là 20 ms, báo cáo kết quả chéo host phải nêu sai số đồng hồ tối thiểu ±20 ms, ngoài sai số do polling và scheduling. Nếu clock offset không được kiểm soát, không đưa ra kết luận chính xác tới từng mili giây.

### Sai số do polling interval

Nếu consumer polling mỗi 100 ms, instance có thể đã xuất hiện ngay sau lần poll thất bại cuối cùng và trước lần poll thành công đầu tiên. T_seen thực nằm trong khoảng:

    last_not_seen < T_seen <= first_seen

Vì vậy, số đo first_seen có sai số do polling tối đa xấp xỉ một poll interval, cộng thêm scheduler delay và thời gian gọi DiscoveryClient. Ghi cả thời điểm miss cuối cùng và hit đầu tiên để báo cáo khoảng đo, không chỉ một con số.

Poll quá dày làm tăng tải lên discovery client/registry và có thể ảnh hưởng chính phép đo. Bắt đầu với 100-250 ms trong lab, sau đó thử 500 ms hoặc 1 giây để xem kết quả có thay đổi đáng kể không.

## Quan sát từ DiscoveryClient

Consumer cần kiểm tra đúng instance ID, không chỉ kiểm tra danh sách có phần tử. Ví dụ:

    List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

    for (ServiceInstance instance : instances) {
        log.info(
            "serviceId={} instanceId={} host={} port={} uri={} metadata={}",
            instance.getServiceId(),
            instance.getInstanceId(),
            instance.getHost(),
            instance.getPort(),
            instance.getUri(),
            instance.getMetadata()
        );
    }

Một số provider có thể không trả instance ID qua ServiceInstance hoặc biểu diễn ID trong metadata. Khi đó, chọn một định danh ổn định và duy nhất, ví dụ metadata instance-id hoặc cặp host/port trong lab. Đừng dùng tên service chung để nhận diện instance mới.

Ghi lại danh sách instance ở mỗi lần poll hoặc ít nhất ghi danh sách tại lần miss cuối cùng và lần hit đầu tiên. Điều này giúp phát hiện trường hợp consumer đã thấy service ID nhưng chưa thấy đúng instance ID mới.

Không chỉ dựa vào dashboard registry. Dashboard thường đọc dữ liệu ở server/catalog; DiscoveryClient trả dữ liệu theo cache, watch hoặc truy vấn mà chính consumer sử dụng.

## Đo đường gọi thực tế qua Spring Cloud LoadBalancer

DiscoveryClient có thể nhìn thấy instance trước khi LoadBalancer cache được cập nhật. Để đo T_route, tạo RestClient có LoadBalancer integration:

    @Configuration
    class ClientConfiguration {
        @Bean
        @LoadBalanced
        RestClient.Builder loadBalancedRestClientBuilder() {
            return RestClient.builder();
        }
    }

Consumer gọi endpoint trả instance ID:

    String instanceId = restClient.get()
        .uri("http://inventory-service/internal/instance-id")
        .retrieve()
        .body(String.class);

Lặp lời gọi GET có giới hạn cho đến khi response chứa expectedInstanceId. Ghi thời điểm đó là T_route. Endpoint phải là thao tác đọc an toàn; không dùng POST ghi dữ liệu chỉ để thăm dò instance.

Nếu service có nhiều instance, lần gọi đầu tiên có thể tới instance cũ. Tiếp tục gọi theo poll interval cho tới khi response đúng instance ID mới hoặc hết deadline. Ghi riêng:

- T_first_service_response: lần đầu gọi service có bất kỳ instance nào thành công.
- T_route: lần đầu response đến từ instance mới.
- Số request cần gửi để LoadBalancer chọn instance mới.

Nếu LoadBalancer dùng round-robin và có N instance, số lần gọi tới khi chọn được instance mới phụ thuộc thứ tự chọn và các lỗi phát sinh. Đây là chỉ số route selection, không phải độ trễ discovery thuần túy.

## Thí nghiệm theo từng lớp

### Thí nghiệm A: Đo registry acknowledge

1. Khởi động registry và consumer.
2. Đảm bảo service ID thử nghiệm chưa có instance ID sắp dùng.
3. Sinh một instance ID mới cho run hiện tại.
4. Ghi T_req ngay trước khi gửi registration.
5. Ghi T_ack ngay sau response xác nhận từ registry/agent.
6. Đọc registry API để xác nhận đúng instance ID tồn tại.
7. Lưu registration latency = T_ack - T_req.

Nếu registration do Spring Cloud auto-registration thực hiện, bật log có kiểm soát cho provider client và xác định event/log tương ứng với response thành công. Không dùng thời điểm log Started application làm T_ack.

### Thí nghiệm B: Đo health readiness

Với Consul, sau khi T_ack được ghi, truy vấn Agent API hoặc Health API cho tới khi check của instance chuyển passing. Ghi T_pass.

    health_ready_delay = T_pass - T_ack

Nếu check critical vì sai path/port/auth, phép đo discovery sẽ bị kéo dài hoặc consumer lọc instance đó hoàn toàn. Ghi nguyên nhân check và không coi thời gian này là cache propagation.

Với Eureka, ghi trạng thái instance và xem consumer có lọc status/health metadata hay không. Với ZooKeeper, nếu không có health check tương đương, bỏ mốc T_pass hoặc ghi health signal riêng của ứng dụng.

### Thí nghiệm C: Đo consumer discovery visibility

1. Bắt đầu probe bên trong consumer process.
2. Ghi T_ack hoặc gửi sự kiện chứa T_ack tới probe.
3. Poll DiscoveryClient theo service ID.
4. Chỉ đánh dấu seen khi tìm thấy đúng expectedInstanceId.
5. Ghi T_seen và last_not_seen.
6. Tính T_seen - T_ack cùng khoảng sai số do polling.

Không tạo một DiscoveryClient mới chỉ dành cho phép đo nếu mục tiêu là biết cache của consumer thật. Hãy inject chính bean mà luồng gọi nghiệp vụ sử dụng.

### Thí nghiệm D: Đo LoadBalancer reachability

1. Bắt đầu gọi GET qua RestClient có @LoadBalanced.
2. Đọc instance ID trong response.
3. Ghi T_first_service_response khi bất kỳ instance nào phản hồi thành công.
4. Ghi T_route khi response đến từ expectedInstanceId.
5. Tính T_route - T_ack và T_route - T_seen.
6. Nếu T_seen đã xảy ra nhưng T_route lâu hơn, điều tra LoadBalancer cache, lựa chọn instance, địa chỉ quảng bá hoặc kết nối tới instance.

Nếu request không bao giờ tới instance mới, kiểm tra LoadBalancer cache và service instance list supplier. DiscoveryClient có thể đã cập nhật trong khi supplier/cache vẫn đang giữ danh sách cũ.

## Các lớp cache và propagation cần phân biệt

Một registration mới có thể đi qua nhiều lớp trước khi caller nhìn thấy:

| Lớp | Điều cần xác minh | Dấu hiệu độ trễ |
|---|---|---|
| Provider registration client | Request được gửi và được chấp nhận lúc nào? | T_req tới T_ack |
| Registry node/agent | Bản ghi đã xuất hiện ở nơi consumer truy vấn chưa? | T_ack tới registry visible |
| Registry replication | Peer/server khác đã nhận dữ liệu chưa? | Khác biệt giữa node/agent |
| DiscoveryClient | Client đã nhận dữ liệu mới qua fetch/watch/query chưa? | Registry visible tới T_seen |
| Discovery cache | Cache local còn giữ danh sách cũ không? | T_seen thay đổi theo cache refresh |
| LoadBalancer supplier/cache | Danh sách instance mà LoadBalancer chọn đã cập nhật chưa? | T_seen tới T_route |
| Network/provider | Instance được chọn có kết nối được không? | T_route bị kéo dài bởi timeout/connect failure |

Không gộp tất cả thành một chỉ số registry latency. Nếu có thể, ghi thêm timestamp khi registry API đã trả instance và khi consumer DiscoveryClient thấy instance. Khoảng chênh giữa hai mốc giúp định vị phần propagation/cache.

## Khác biệt cần quan sát theo từng registry

### Eureka

Eureka Client đăng ký instance với Eureka Server; consumer thường lấy registry qua cơ chế fetch định kỳ và giữ local registry/cache. Vì vậy, registration có thể được server chấp nhận trước khi consumer fetch lần tiếp theo.

Kiểm tra các property liên quan:

- eureka.client.register-with-eureka: provider có gửi registration hay không.
- eureka.client.fetch-registry: consumer có tải registry hay không.
- eureka.client.registry-fetch-interval-seconds: chu kỳ fetch registry của client.
- eureka.client.service-url.defaultZone: server/peer mà client đang dùng.
- Instance status và instance ID trong registry.

Giá trị mặc định và hành vi cụ thể phụ thuộc phiên bản Spring Cloud Netflix/Eureka Client. Không mặc định rằng tất cả consumer fetch cùng thời điểm hoặc cùng node. Nếu dùng Eureka cluster, kiểm tra registration replication và consumer đang đọc server nào.

Eureka dashboard hiển thị instance không có nghĩa consumer local cache đã nhận. Đo T_seen từ DiscoveryClient trong consumer process. Nếu server nhận registration ngay nhưng T_seen tăng theo chu kỳ fetch, fetch interval có thể là phần trễ chính.

### Consul

Consul service registration thường được gửi tới local agent. Agent có thể nhận registration trước khi health check passing hoặc catalog/consumer query thấy instance phù hợp.

Ghi riêng:

- T_ack: local agent/API xác nhận registration.
- T_pass: check chuyển passing.
- T_seen: consumer discovery client thấy instance theo health query đang sử dụng.

Nếu consumer chỉ yêu cầu passing instance, T_seen phụ thuộc cả T_pass. Kiểm tra ACL, datacenter, namespace, partition, query filter và địa chỉ Consul agent/server mà consumer đang truy cập.

Nếu có nhiều agent hoặc server, đừng giả định kết quả local agent và catalog query ở server luôn xuất hiện đồng thời. Ghi rõ API được dùng để lấy dữ liệu và node/agent đang quan sát.

### ZooKeeper

ZooKeeper discovery thường lưu thông tin service trong znode, thường dùng ephemeral node cho instance sống theo session. Consumer có thể dùng watch để nhận thay đổi hoặc đọc dữ liệu qua discovery client.

Đo:

- T_ack: thao tác tạo znode/registration được xác nhận.
- T_seen: consumer nhận watch event hoặc DiscoveryClient trả về instance.
- Thời gian reconnect/session recovery nếu consumer mất kết nối trong lúc registration xảy ra.

Watch có thể được đăng ký lại sau session expiration; nếu chỉ đo lần đầu sau khi consumer khởi động, kết quả khác với update trên một watch đã ổn định. Ghi rõ consumer cold-start hay warm-watch.

## Thiết kế ma trận thí nghiệm

| Nhóm | Consumer state | Registration | Mục tiêu |
|---|---|---|---|
| Cold consumer | Consumer vừa khởi động, cache/watch chưa ổn định | Tạo instance mới | Đo chi phí khởi tạo và lần fetch/watch đầu |
| Warm consumer | Consumer đã hoạt động ổn định | Tạo instance mới | Đo propagation bình thường |
| Registry peer | Consumer truy vấn qua peer/server khác | Tạo instance mới | Đo replication và đường đọc |
| Health delayed | Check cố ý chậm hoặc chưa passing | Tạo instance mới | Tách health readiness khỏi discovery |
| LB cache | Discovery đã thấy instance nhưng LB cache còn warm | Tạo instance mới | Đo độ trễ tới route thực tế |
| Consumer reconnect | Consumer ngắt rồi kết nối lại | Tạo instance trong lúc reconnect | Đo phục hồi watch/cache |

Mỗi run cần instance ID mới và run ID mới. Dọn registration cũ sau khi kết thúc để tránh kết quả của run trước làm sai phép đo.

Thực hiện tối thiểu vài chục lần để có median và p95 đáng tin cậy hơn một mẫu đơn. Nếu cần p99 có ý nghĩa, tăng số lần chạy lên hàng trăm hoặc hàng nghìn; p99 từ tập mẫu rất nhỏ không ổn định.

## Bảng log kết quả

Ghi một dòng cho mỗi run, ví dụ CSV:

    run_id,registry,consumer_mode,instance_id,t_req_ms,t_ack_ms,t_pass_ms,t_seen_ms,t_route_ms,poll_ms,clock_error_ms
    run-001,eureka,warm,inventory-node-001,1000,1040,,31800,32050,100,2
    run-002,consul,warm,inventory-node-002,2000,2030,2180,2290,2410,100,2
    run-003,zookeeper,warm,inventory-node-003,3000,3040,,3120,3290,100,2

Các số trên chỉ là dữ liệu minh họa, không phải benchmark hay default của bất kỳ registry nào. Giá trị trống ở T_pass nghĩa là provider không dùng health check hoặc mốc đó không áp dụng.

Có thể tính các cột duration:

    registration_ms = t_ack_ms - t_req_ms
    health_delay_ms = t_pass_ms - t_ack_ms
    discovery_ms = t_seen_ms - t_ack_ms
    end_to_end_visibility_ms = t_seen_ms - t_req_ms
    loadbalanced_reachability_ms = t_route_ms - t_ack_ms
    route_after_discovery_ms = t_route_ms - t_seen_ms

Nếu dùng UTC wall-clock từ nhiều host, chỉ tính duration sau khi xác nhận clock offset và ghi sai số. Nếu có thể, tính duration chính trong cùng process bằng monotonic clock rồi dùng UTC chỉ để đối chiếu log.

## Phân tích kết quả

Tính ít nhất:

- min: lần nhanh nhất, chỉ để tham khảo.
- median/p50: trải nghiệm điển hình.
- p95: phần lớn lần chạy hoàn thành trong ngưỡng này.
- p99: đuôi phân phối, cần đủ mẫu.
- max: lần chậm nhất và các lỗi ngoại lệ.
- Số lần timeout hoặc không thấy instance trong deadline.

| Quan sát | Khả năng cần kiểm tra |
|---|---|
| T_ack lớn | Registry API, network, auth hoặc provider registration client chậm |
| T_pass - T_ack lớn | Health check interval, endpoint readiness, timeout hoặc dependency chưa sẵn sàng |
| Registry đã thấy nhưng T_seen lớn | Replication, fetch interval, watch, discovery cache hoặc consumer đang đọc node khác |
| T_seen nhanh nhưng T_route lớn | LoadBalancer cache/supplier, chọn instance, stale address hoặc kết nối provider |
| Dashboard thấy nhưng consumer không thấy | Dashboard và consumer dùng nguồn/node/cache khác nhau |
| Kết quả thay đổi mạnh giữa cold và warm | Khởi tạo client, fetch đầu, watch registration hoặc cache warm-up |
| T_route có lúc rất lâu dù T_seen ổn định | LoadBalancer lựa chọn instance cũ, retry, timeout hoặc phân phối request |

Không kết luận chỉ dựa trên một lần chạy. So sánh cùng cấu hình, cùng registry topology, cùng poll interval và cùng consumer code path.

## Kiểm soát biến gây nhiễu

Giữ ổn định các yếu tố sau:

- Cùng phiên bản Spring Boot, Spring Cloud và registry giữa các lần so sánh.
- Cùng số registry node/agent và cùng datacenter/namespace.
- Cùng cấu hình polling, cache TTL, fetch interval và health check.
- Cùng network path và mức tải nền.
- Không chạy song song nhiều registration test vào cùng service ID.
- Dùng instance ID riêng và xác minh không có bản ghi stale.
- Không để retry của HTTP client làm sai số lần gọi hoặc thời điểm T_route.
- Ghi rõ consumer đã warm cache/watch hay vừa khởi động.
- Đồng bộ clock nếu log nằm trên nhiều host.

Khi cần đo baseline propagation, có thể tạm tắt hoặc giảm các cache trong môi trường lab để hiểu từng lớp. Sau đó chạy lại với cấu hình production. Không tắt cache trong production chỉ để làm số đo đẹp hơn; cache là một phần của hành vi hệ thống cần đánh giá.

## Tiêu chí hoàn thành bài thực hành

Bài thực hành đạt yêu cầu khi có đủ:

1. Một service instance mới với ID duy nhất.
2. Timestamp T_req và T_ack có nguồn ghi nhận rõ ràng.
3. T_pass nếu registry có health check.
4. T_seen được đo từ DiscoveryClient của đúng consumer process.
5. T_route được xác minh bằng instance ID trả về từ provider.
6. Sai số clock và poll interval được ghi trong báo cáo.
7. Có nhiều lần chạy và kết quả p50/p95; p99 nếu đủ mẫu.
8. Có giải thích lớp nào đóng góp độ trễ lớn nhất.
9. Có so sánh cold/warm hoặc ít nhất hai cấu hình cache/fetch khác nhau.
10. Có ghi lại cấu hình registry/client để người khác tái lập phép đo.

## Câu hỏi tự đánh giá

1. Vì sao T_ack không đồng nghĩa với T_seen?
2. Vì sao dashboard hiển thị instance chưa đủ chứng minh consumer đã nhìn thấy?
3. Với Consul, tại sao cần đo T_pass riêng?
4. Vì sao T_seen có thể nhỏ hơn T_route?
5. Khi polling 100 ms, sai số của T_seen được diễn giải như thế nào?
6. Vì sao không được trừ System.nanoTime() từ hai process khác nhau?
7. Khi Eureka fetch registry theo chu kỳ, property nào ảnh hưởng trực tiếp đến thời điểm consumer cập nhật?
8. Nếu consumer thấy instance nhưng request vẫn đi tới instance cũ, cần kiểm tra lớp nào?
9. Tại sao instance ID phải duy nhất cho từng run?
10. Vì sao cần báo cáo p95 thay vì chỉ báo cáo một lần chạy nhanh nhất?

## Kết luận

Độ trễ từ registration tới caller visibility là tổng hợp của thời gian registry chấp nhận và đồng bộ dữ liệu, health readiness, discovery fetch/watch/cache và LoadBalancer cache. Hãy đo riêng T_ack, T_pass, T_seen và T_route; dùng instance ID duy nhất để xác nhận đúng bản ghi, đo duration bằng monotonic clock trong cùng process hoặc dùng UTC với clock sync khi đo chéo host. Khi tách được các mốc này, nhóm vận hành có thể xác định độ trễ nằm ở registry, health check, discovery client hay load balancer thay vì chỉ nhìn dashboard và phỏng đoán.
