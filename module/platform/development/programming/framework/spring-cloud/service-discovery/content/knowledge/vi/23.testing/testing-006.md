# Chờ điều kiện hội tụ thay vì đặt thời gian ngủ cố định

Đăng ký và khám phá service là các thao tác bất đồng bộ. Provider có thể gửi registration thành công nhưng registry cần thêm thời gian để cập nhật catalog, đồng bộ sang node khác hoặc để consumer làm mới cache. Vì vậy, một bài test gọi DiscoveryClient.getInstances() ngay sau khi khởi động provider có thể nhận danh sách rỗng dù hệ thống đang hoạt động đúng.

Cách kiểm thử ổn định là chờ **một điều kiện có ý nghĩa** đạt được trong một khoảng thời gian giới hạn. Với Awaitility, test liên tục đánh giá điều kiện như “instance đã xuất hiện”, “health đã passing” hoặc “instance đã biến mất”. Cách này tránh việc đoán một số giây cố định bằng Thread.sleep().

Trong module SPRING_CLOUD_SERVICE_DISCOVERY, bài học này áp dụng cho integration test với Eureka, Consul, ZooKeeper và các discovery client khác. Trọng tâm là hiểu eventual consistency, chọn timeout/poll interval, chờ cả registry lẫn consumer cache, và tạo test có thể chạy ổn định trên máy developer lẫn CI.

## 1. Vì sao không nên dùng Thread.sleep cố định?

Một test thường được viết như sau:

    provider.start();
    Thread.sleep(5000);

    assertThat(discoveryClient.getInstances("payment-service"))
            .isNotEmpty();

Đoạn code giả định registration sẽ hoàn tất trong 5 giây. Nhưng thời gian thực tế phụ thuộc tốc độ khởi động ứng dụng, lịch heartbeat, chu kỳ fetch registry, watcher, network latency, container startup và tải CI.

Thread.sleep(5000) có hai vấn đề:

- Nếu điều kiện đạt sau 200 ms, test vẫn lãng phí gần 4,8 giây.
- Nếu điều kiện cần 6 giây trên CI chậm, test thất bại dù hệ thống cuối cùng vẫn hội tụ đúng.

Tăng sleep lên 30 giây chỉ làm suite chậm hơn và vẫn không tạo ra bảo đảm. Một lỗi đăng ký vĩnh viễn cũng khiến test chờ hết 30 giây mà không cho biết rõ điều kiện nào chưa đạt.

Thay vào đó, hãy đặt timeout tối đa và kiểm tra lại điều kiện theo chu kỳ:

    await()
            .atMost(Duration.ofSeconds(30))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances("payment-service"))
                            .isNotEmpty()
            );

Test kết thúc ngay khi assertion thành công. Nếu hết 30 giây mà điều kiện chưa đạt, Awaitility ném ConditionTimeoutException và báo test đã chờ quá hạn.

## 2. Eventual consistency trong service discovery

Registry và consumer không nhất thiết nhìn thấy cùng một trạng thái tại cùng một thời điểm. Một thay đổi có thể đi qua nhiều bước:

1. Provider tạo registration hoặc thay đổi health status.
2. Registry nhận và lưu thay đổi.
3. Registry replication hoặc catalog index được cập nhật nếu hệ thống có nhiều node.
4. Discovery client của consumer nhận event hoặc fetch dữ liệu mới.
5. Spring Cloud LoadBalancer làm mới danh sách ServiceInstance trong cache.
6. Request tiếp theo sử dụng danh sách mới.

    sequenceDiagram
        participant P as Provider
        participant R as Registry
        participant D as Consumer DiscoveryClient
        participant L as LoadBalancer
        P->>R: Register instance
        R-->>P: Acknowledge
        Note over R,D: Registry/client propagation có thể bất đồng bộ
        D->>R: Fetch hoặc nhận watch update
        R-->>D: Danh sách instance mới
        D-->>L: ServiceInstance list
        L->>L: Làm mới cache
        Note over L: Request tiếp theo mới thấy instance

Test cần chờ ở đúng lớp đang được kiểm tra. Nếu mục tiêu là chứng minh registry đã lưu registration, chờ API native của registry. Nếu mục tiêu là chứng minh consumer đã khám phá được instance, chờ DiscoveryClient của consumer. Nếu mục tiêu là chứng minh request được định tuyến đúng, gửi request qua LoadBalancer sau khi danh sách consumer đã hội tụ.

## 3. Awaitility là gì?

Awaitility là thư viện Java giúp diễn đạt điều kiện bất đồng bộ theo dạng dễ đọc. Thay vì tự viết vòng lặp, đồng hồ và sleep, test mô tả:

- Điều kiện cần đạt.
- Thời gian tối đa chờ.
- Khoảng cách giữa các lần đánh giá điều kiện.
- Độ trễ trước lần đánh giá đầu tiên nếu cần.

Các phương thức thường dùng:

| API | Công dụng |
|---|---|
| await() | Bắt đầu khai báo một lần chờ. |
| atMost(...) | Giới hạn tổng thời gian chờ. |
| pollInterval(...) | Khoảng thời gian giữa các lần đánh giá điều kiện. |
| pollDelay(...) | Thời gian chờ trước lần đánh giá đầu tiên. |
| until(...) | Chờ một biểu thức trả về true hoặc giá trị mong muốn. |
| untilAsserted(...) | Chạy assertion lặp lại cho đến khi assertion thành công. |
| alias(...) | Đặt tên điều kiện để thông báo timeout dễ hiểu hơn. |

Awaitility không làm registry cập nhật nhanh hơn. Nó chỉ giúp test chờ đúng cách và dừng ngay khi trạng thái cần kiểm tra đã xuất hiện.

## 4. Thêm dependency Awaitility

Nếu dự án chưa có Awaitility, thêm dependency test và để dependency management của dự án quản lý phiên bản tương thích:

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>

Các import phổ biến:

    import java.time.Duration;
    import java.util.List;
    import java.util.concurrent.TimeUnit;

    import org.awaitility.Awaitility;
    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;

    import static org.assertj.core.api.Assertions.assertThat;
    import static org.awaitility.Awaitility.await;

Ví dụ trong bài dùng AssertJ để diễn đạt assertion. Có thể dùng JUnit assertions nếu dự án không sử dụng AssertJ.

## 5. Chọn giữa until và untilAsserted

### 5.1. Dùng until khi điều kiện trả về boolean

Khi chỉ cần kiểm tra một predicate, dùng until:

    await()
            .atMost(Duration.ofSeconds(20))
            .until(() -> !discoveryClient.getInstances("payment-service").isEmpty());

Biểu thức được đánh giá nhiều lần. Khi trả về true, test tiếp tục; nếu hết timeout mà vẫn false, Awaitility báo timeout.

### 5.2. Dùng untilAsserted khi cần kiểm tra nhiều thuộc tính

Nếu cần xác minh instance ID, host, port hoặc metadata, untilAsserted thường dễ đọc hơn:

    await()
            .alias("payment-service instance is registered")
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                List<ServiceInstance> instances =
                        discoveryClient.getInstances("payment-service");

                assertThat(instances).anySatisfy(instance -> {
                    assertThat(instance.getInstanceId()).isEqualTo("payment-01");
                    assertThat(instance.getHost()).isNotBlank();
                    assertThat(instance.getPort()).isEqualTo(8080);
                });
            });

Khi danh sách rỗng hoặc thuộc tính chưa đúng, assertion thất bại và được đánh giá lại ở lần poll tiếp theo. Khi instance xuất hiện với đầy đủ thông tin mong đợi, test đi tiếp.

### 5.3. Không đặt assertion sau một lần đọc duy nhất

Không nên đọc danh sách một lần rồi kiểm tra ngay:

    List<ServiceInstance> instances =
            discoveryClient.getInstances("payment-service");

    await().untilAsserted(() -> assertThat(instances).isNotEmpty());

Ở ví dụ này, instances là snapshot được lấy trước khi Awaitility bắt đầu. Mỗi lần poll vẫn kiểm tra cùng một danh sách cũ, nên nó không thể nhìn thấy registration mới.

Hãy đặt thao tác đọc dữ liệu bên trong lambda:

    await().untilAsserted(() ->
            assertThat(discoveryClient.getInstances("payment-service"))
                    .isNotEmpty()
    );

## 6. Chờ provider xuất hiện trong Consul

Giả sử provider đăng ký payment-service với instance ID payment-01. Consumer đã kết nối đến Consul bằng Spring Cloud Consul Discovery.

    private static final String SERVICE_ID = "payment-service";
    private static final String INSTANCE_ID = "payment-01";

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void waitsUntilPaymentInstanceIsDiscoverable() {
        await()
                .alias("Consul registration visible to consumer")
                .atMost(Duration.ofSeconds(30))
                .pollInterval(Duration.ofMillis(250))
                .untilAsserted(() -> {
                    List<ServiceInstance> instances =
                            discoveryClient.getInstances(SERVICE_ID);

                    assertThat(instances).anySatisfy(instance -> {
                        assertThat(instance.getInstanceId()).isEqualTo(INSTANCE_ID);
                        assertThat(instance.getHost()).isNotBlank();
                        assertThat(instance.getPort()).isPositive();
                    });
                });
    }

Điều kiện này xác nhận góc nhìn của consumer. Nếu cần chứng minh Consul Catalog đã lưu bản ghi, hãy chờ API /v1/catalog/service/{service} trả về đúng ServiceID, ServiceAddress và ServicePort. Nếu cần xác nhận health check passing, kiểm tra /v1/health/service/{service} và trạng thái check riêng.

Consul có thể dùng blocking query/watch để cập nhật discovery state. Dù provider đã đăng ký, consumer vẫn có thể cần thời gian nhận thay đổi. Polling DiscoveryClient giúp test đợi đến khi cache phía consumer phản ánh bản ghi.

## 7. Chờ Eureka client fetch registry

Eureka có nhiều trạng thái cần phân biệt:

- Eureka Server đã nhận registration.
- Eureka Client của consumer đã fetch registry mới.
- LoadBalancer của consumer đã làm mới danh sách instance.

Nếu chỉ gọi REST API Eureka Server, test chứng minh server có bản ghi nhưng chưa chứng minh local registry cache của consumer đã cập nhật.

Ví dụ chờ consumer nhìn thấy instance:

    await()
            .alias("Eureka consumer cache contains payment-01")
            .atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(500))
            .untilAsserted(() -> {
                List<ServiceInstance> instances =
                        consumerDiscoveryClient.getInstances("payment-service");

                assertThat(instances).anySatisfy(instance ->
                        assertThat(instance.getInstanceId()).isEqualTo("payment-01")
                );
            });

Timeout phải tương thích với eureka.client.registry-fetch-interval-seconds và thời gian khởi động client. Nếu test cần hội tụ nhanh, có thể giảm fetch interval trong profile test; không thay đổi cấu hình production chỉ để làm test chạy nhanh.

Nếu kiểm tra cả server và consumer, dùng hai điều kiện riêng: một điều kiện chờ Eureka REST API có instance, điều kiện tiếp theo chờ consumerDiscoveryClient. Điều này giúp xác định độ trễ nằm ở registration hay ở bước fetch/cache của consumer.

## 8. Chờ znode xuất hiện trong ZooKeeper

Spring Cloud Zookeeper Discovery thường lưu instance dưới một ephemeral znode. Có thể dùng Curator checkExists() để chờ node xuất hiện:

    String path = "/services/payment-service/payment-01";

    await()
            .alias("ZooKeeper ephemeral registration created")
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(200))
            .untilAsserted(() -> {
                Stat stat = curatorFramework.checkExists().forPath(path);

                assertThat(stat).isNotNull();
                assertThat(stat.getEphemeralOwner()).isNotZero();
            });

checkExists() trả về null khi node chưa tồn tại. Khi node được tạo, ephemeralOwner khác 0 cho biết node gắn với một ZooKeeper session. Đường dẫn thực tế phụ thuộc spring.cloud.zookeeper.discovery.root, service ID, instance ID và phiên bản integration; dùng đúng path mà ứng dụng đã cấu hình.

Sau khi node xuất hiện, vẫn nên kiểm tra DiscoveryClient.getInstances() để xác minh abstraction Spring Cloud đọc được dữ liệu đó. Node tồn tại nhưng consumer không đọc được có thể do root path khác, cache chưa refresh hoặc ACL không cho phép đọc.

## 9. Chờ instance bị deregister hoặc biến mất

Khi provider dừng có kiểm soát, consumer không nhất thiết thấy instance biến mất ngay lập tức. Registry cần xử lý deregistration, client cần nhận thay đổi và LoadBalancer cache cần hết hạn hoặc được invalidation.

Ví dụ chờ instance ID không còn trong danh sách:

    await()
            .alias("payment-01 removed from consumer discovery view")
            .atMost(Duration.ofSeconds(30))
            .pollInterval(Duration.ofMillis(250))
            .untilAsserted(() -> {
                boolean stillVisible = discoveryClient
                        .getInstances("payment-service")
                        .stream()
                        .anyMatch(instance ->
                                "payment-01".equals(instance.getInstanceId()));

                assertThat(stillVisible).isFalse();
            });

Với ZooKeeper, có thể chờ ephemeral znode biến mất:

    await()
            .atMost(Duration.ofSeconds(30))
            .untilAsserted(() ->
                    assertThat(curatorFramework.checkExists().forPath(path)).isNull()
            );

Với Consul, kiểm tra Catalog API và Health API tùy mục tiêu: deregistration có thể xóa service record; một health check critical có thể vẫn để record tồn tại nhưng không còn passing. Với Eureka, graceful cancellation khác với việc client chết đột ngột và chờ lease expiration. Test phải khẳng định đúng semantics mà mình muốn kiểm tra.

## 10. Chờ health status chuyển trạng thái

Một service có thể đã đăng ký nhưng health check chưa passing. Không nên dùng điều kiện “có instance” để đại diện cho “instance khỏe mạnh”.

Ví dụ với Consul, khi consumer được cấu hình query-passing=true, có thể chờ danh sách instance theo cấu hình discovery hiện tại:

    await()
            .alias("Consul reports payment-01 as passing")
            .atMost(Duration.ofSeconds(45))
            .untilAsserted(() -> {
                List<ServiceInstance> passingInstances =
                        discoveryClient.getInstances("payment-service");

                assertThat(passingInstances)
                        .anySatisfy(instance ->
                                assertThat(instance.getInstanceId()).isEqualTo("payment-01")
                        );
            });

Điều kiện trên chỉ chứng minh consumer trả về instance theo cấu hình discovery hiện tại. Để chứng minh Consul check cụ thể ở trạng thái passing, nên truy vấn Health API và assert Checks[].Status tương ứng. Đừng suy ra health status từ việc service xuất hiện trong Catalog API.

Với Eureka, kiểm tra status mà client công bố như UP hoặc DOWN; không giả định Eureka Server chủ động gọi Actuator health URL của mọi instance. Với ZooKeeper, session còn sống chỉ chứng minh client duy trì session, không chứng minh endpoint HTTP của service đang khỏe.

## 11. Chờ cả registry lẫn consumer cache

Một test tốt có thể tách hai giai đoạn để chỉ ra điểm hội tụ:

    // Giai đoạn 1: Consul Catalog đã lưu registration.
    await()
            .alias("Consul catalog contains payment-01")
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() -> {
                JsonNode[] records = consulCatalog.findService(SERVICE_ID);
                assertThat(records)
                        .anySatisfy(record ->
                                assertThat(record.path("ServiceID").asText())
                                        .isEqualTo(INSTANCE_ID)
                        );
            });

    // Giai đoạn 2: Consumer DiscoveryClient đã nhìn thấy registration.
    await()
            .alias("consumer discovery cache contains payment-01")
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances(SERVICE_ID))
                            .anySatisfy(instance ->
                                    assertThat(instance.getInstanceId()).isEqualTo(INSTANCE_ID)
                            )
            );

consulCatalog.findService là phương thức helper do test tự viết để gọi Catalog API. Tách điều kiện giúp phân biệt registry chưa nhận đăng ký với consumer chưa cập nhật cache. Với Eureka, thay helper bằng REST API Eureka; với ZooKeeper, thay bằng Curator checkExists() hoặc đọc znode payload.

Nếu chỉ cần một điều kiện cuối cùng, không cần chờ mọi lớp riêng. Nhưng khi test thất bại hoặc đo propagation delay, việc chia giai đoạn làm nguyên nhân rõ ràng hơn.

## 12. Chọn timeout phù hợp

Timeout là giới hạn tổng thời gian test chấp nhận chờ. Không nên chọn tùy ý hoặc đặt quá sát thời gian lý tưởng trên laptop.

Một cách ước lượng là lập ngân sách từ các bước có thể nối tiếp:

    T_timeout >= T_register + T_replication + T_refresh + T_cache + T_margin

Các thành phần có thể gồm:

- Thời gian provider khởi động và gửi registration.
- Thời gian registry ghi nhận hoặc replicate thay đổi.
- Chu kỳ fetch/watch của discovery client.
- Thời gian LoadBalancer cache làm mới.
- Độ trễ scheduler, network và tải của CI.

Đây là cách lập ngân sách bảo thủ; một số bước diễn ra song song hoặc không tồn tại trong registry đang dùng. Hãy đo thực tế rồi chọn timeout có headroom thay vì cộng máy móc mọi giá trị.

| Môi trường | Timeout minh họa | Ghi chú |
|---|---:|---|
| Unit test bất đồng bộ trong process | 1–3 giây | Không có registry network; chỉ dùng cho tác vụ cục bộ nhanh. |
| Registry container cục bộ | 15–30 giây | Phụ thuộc thời gian container readiness và cấu hình client. |
| Eureka với registry fetch interval mặc định | 30–60 giây hoặc theo cấu hình | Cần tính chu kỳ fetch và khởi động client. |
| CI dùng container/network chậm | 30–90 giây hoặc theo số đo | Không dùng timeout quá rộng để che lỗi thật. |
| ZooKeeper session expiration | Theo session timeout đã cấu hình cộng margin | Session expiration có thể lâu hơn watcher notification bình thường. |

Các khoảng thời gian trên chỉ là điểm bắt đầu để thiết kế test. Timeout production-like phải được suy ra từ cấu hình và số đo của hệ thống cụ thể.

## 13. Chọn poll interval và poll delay

pollInterval là khoảng thời gian giữa các lần kiểm tra. pollDelay là thời gian chờ trước lần kiểm tra đầu tiên.

    await()
            .alias("service registration appears")
            .pollDelay(Duration.ZERO)
            .pollInterval(Duration.ofMillis(250))
            .atMost(Duration.ofSeconds(30))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances("payment-service"))
                            .isNotEmpty()
            );

Một số hướng dẫn lựa chọn:

- Poll quá dày không làm registry hội tụ nhanh hơn; nó chỉ tăng số lần test đọc điều kiện.
- Poll quá thưa làm test phát hiện trạng thái muộn hơn dù điều kiện đã đạt.
- Với container cục bộ, khoảng 100–300 ms thường đủ để phát hiện thay đổi mà không tạo tải đáng kể.
- Với registry từ xa hoặc query tốn kém, cân nhắc 500 ms đến vài giây.
- Dùng pollDelay khi biết trước tác vụ có một giai đoạn khởi tạo tối thiểu; không thêm delay chỉ để che một race condition chưa hiểu rõ.

Nếu registry client chỉ refresh mỗi 30 giây, poll mỗi 50 ms không giúp consumer nhìn thấy dữ liệu mới sớm hơn. Khi đó, nên giảm chu kỳ refresh trong test profile hoặc tăng timeout phù hợp.

## 14. Xử lý exception tạm thời có chủ đích

Một điều kiện có thể tạm thời ném exception trong lúc registry hoặc ứng dụng đang khởi động. Tuy nhiên, không nên bỏ qua mọi exception vì có thể che lỗi cấu hình hoặc lỗi lập trình.

Ưu tiên các cách sau:

1. Chờ registry readiness trước khi khởi động provider/consumer.
2. Viết predicate an toàn với trạng thái chưa có dữ liệu, ví dụ danh sách rỗng hoặc znode chưa tồn tại.
3. Nếu có một exception tạm thời được xác định rõ, chỉ ignore đúng loại exception đó và vẫn đặt timeout.
4. Để exception không mong đợi làm test thất bại ngay, thay vì nuốt mọi lỗi.

Ví dụ predicate an toàn:

    await()
            .atMost(Duration.ofSeconds(20))
            .until(() -> {
                List<ServiceInstance> instances =
                        discoveryClient.getInstances("payment-service");
                return instances.stream().anyMatch(instance ->
                        "payment-01".equals(instance.getInstanceId()));
            });

Không nên lạm dụng ignoreExceptions() cho mọi lỗi. Nếu registry URL sai, ACL trả 403, hoặc client dùng sai serializer, việc bỏ qua exception đến hết timeout chỉ khiến log kém rõ ràng. Chỉ dùng ignoreException(...) hoặc ignoreExceptionsMatching(...) khi đã xác định loại lỗi đó là trạng thái tạm thời được chấp nhận trong giai đoạn hội tụ.

## 15. Chờ điều kiện ổn định trong một khoảng thời gian

Đôi khi điều kiện đạt một lần chưa đủ. Ví dụ, instance có thể xuất hiện rồi biến mất do registration bị ghi đè hoặc health check chuyển critical. Khi đó, test cần xác minh trạng thái ổn định trong một khoảng thời gian.

Có thể dùng API during(...) của Awaitility nếu phiên bản đang dùng hỗ trợ:

    await()
            .during(Duration.ofSeconds(3))
            .atMost(Duration.ofSeconds(20))
            .untilAsserted(() ->
                    assertThat(discoveryClient.getInstances("payment-service"))
                            .anySatisfy(instance ->
                                    assertThat(instance.getInstanceId())
                                            .isEqualTo("payment-01")
                            )
            );

Điều kiện phải tiếp tục đúng trong khoảng during. Cấu hình này hữu ích để phát hiện trạng thái dao động, nhưng làm test lâu hơn và không nên dùng cho mọi assertion. Với đa số registration test, chờ điều kiện xuất hiện một lần là đủ; kiểm tra ổn định nên dành cho test health hoặc lifecycle có yêu cầu rõ ràng.

## 16. Không nhầm Awaitility với cơ chế đồng bộ của ứng dụng

Awaitility chỉ là công cụ kiểm thử. Nó không thay thế:

- Eureka heartbeat, registry fetch hoặc lease expiration.
- Consul blocking query, watch, TTL check hoặc health check.
- ZooKeeper watcher, session state hoặc ephemeral node lifecycle.
- Kubernetes watch, EndpointSlice update hoặc DNS TTL.
- Spring Cloud LoadBalancer cache invalidation.

Không đưa vòng lặp Awaitility vào code production để chờ service xuất hiện. Trong ứng dụng thật, hãy dùng discovery abstraction, timeout/retry, circuit breaker và cơ chế event/watch phù hợp. Awaitility thuộc test code.

Nếu ứng dụng dùng Reactor, StepVerifier phù hợp để kiểm tra publisher/stream và thời gian phát event. Awaitility phù hợp khi điều kiện được quan sát qua API đồng bộ, registry client hoặc trạng thái bên ngoài. Chọn công cụ theo dạng dữ liệu đang kiểm tra; không cần lồng Thread.sleep vào publisher test.

## 17. Chẩn đoán timeout có hệ thống

Khi Awaitility timeout, đừng chỉ tăng timeout. Hãy kiểm tra theo thứ tự:

1. Registry container/server có thật sự ready không?
2. Provider có gửi registration thành công không?
3. Registry-native API có bản ghi đúng service ID và instance ID không?
4. Hostname/IP và port có được công bố đúng không?
5. Consumer có kết nối đến cùng registry, namespace/root path và credentials không?
6. Discovery client của consumer có fetch/watch dữ liệu mới không?
7. LoadBalancer cache có giữ danh sách cũ không?
8. Health query có lọc instance vì trạng thái non-passing không?
9. Test có đang đọc snapshot/list cũ bên ngoài lambda Awaitility không?
10. Poll timeout có ngắn hơn fetch interval hoặc session timeout không?

Gắn alias cho từng điều kiện và log service ID, instance ID, registry endpoint, host/port cùng trạng thái. Không log token, password hoặc secret. Khi cần, tách chờ registry-native state và consumer state để xác định chính xác bước nào chưa hội tụ.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Test thất bại ngay | Exception không được xem là trạng thái chờ hoặc registry chưa ready. | Chờ readiness và kiểm tra exception gốc. |
| Test luôn timeout dù instance có trong registry | Consumer dùng sai registry, cache chưa fetch hoặc service ID sai. | Kiểm tra consumer context và DiscoveryClient riêng. |
| Test pass trên máy cá nhân nhưng fail CI | Timeout quá sát, Docker/network chậm hoặc port/hostname không reachable. | Tăng margin theo số đo, dùng mapped port và advertised address đúng network. |
| Test mất nhiều giây dù điều kiện có sớm | Poll interval lớn hoặc có pollDelay không cần thiết. | Giảm poll interval/delay phù hợp. |
| Test tạo tải registry cao | Polling API native quá dày hoặc nhiều test chạy song song. | Poll thưa hơn, dùng client cache cho điều kiện consumer và cô lập test. |
| Instance xuất hiện rồi biến mất | ID trùng, health check fail hoặc provider context bị đóng. | Kiểm tra registration lifecycle và check status. |
| Deregistration timeout | Client chưa deregister, lease/session chưa hết hạn hoặc consumer cache chưa refresh. | Phân biệt graceful shutdown với failure detection; chờ đúng lớp. |
| Exception bị che đến hết timeout | Dùng ignoreExceptions() quá rộng. | Chỉ bỏ qua exception tạm thời cụ thể; để lỗi cấu hình fail ngay. |
| Assertion luôn kiểm tra dữ liệu cũ | Lấy snapshot trước lambda Awaitility. | Đưa thao tác đọc vào bên trong lambda. |

## 18. Một mẫu helper dùng lại trong test suite

Nếu nhiều test cần chờ một instance, có thể tạo helper để tránh lặp cấu hình Awaitility:

    import java.time.Duration;
    import java.util.List;

    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;

    import static org.assertj.core.api.Assertions.assertThat;
    import static org.awaitility.Awaitility.await;

    public final class DiscoveryTestWaits {

        private DiscoveryTestWaits() {
        }

        public static ServiceInstance awaitInstance(
                DiscoveryClient discoveryClient,
                String serviceId,
                String instanceId,
                Duration timeout) {

            await()
                    .alias("instance " + instanceId + " appears in " + serviceId)
                    .atMost(timeout)
                    .pollInterval(Duration.ofMillis(200))
                    .untilAsserted(() -> {
                        List<ServiceInstance> instances =
                                discoveryClient.getInstances(serviceId);

                        assertThat(instances).anySatisfy(instance ->
                                assertThat(instance.getInstanceId()).isEqualTo(instanceId)
                        );
                    });

            return discoveryClient.getInstances(serviceId).stream()
                    .filter(instance -> instanceId.equals(instance.getInstanceId()))
                    .findFirst()
                    .orElseThrow();
        }
    }

Helper trả về instance sau khi điều kiện đã đạt. Việc đọc lại sau Awaitility là cần thiết để lấy đối tượng hiện tại; không lưu một biến snapshot trước khi chờ. Nếu danh sách có thể thay đổi ngay sau khi điều kiện đạt, caller vẫn cần xử lý lỗi kết nối như một tình huống runtime bình thường.

Không nên tạo helper quá tổng quát với nhiều callback và cờ cấu hình khó hiểu. Helper tốt nên biểu diễn một điều kiện cụ thể, có alias rõ và timeout do caller truyền vào.

## 19. Checklist viết test hội tụ ổn định

- Chọn trạng thái cuối cần xác minh: registration, health passing, consumer discovery hay deregistration.
- Xác định đúng nguồn dữ liệu cần đọc: registry API, DiscoveryClient, LoadBalancer hoặc endpoint thực tế.
- Đưa thao tác đọc trạng thái vào bên trong lambda Awaitility.
- Dùng until cho predicate boolean và untilAsserted cho nhiều assertion.
- Đặt timeout dựa trên heartbeat/fetch/watch/session/cache interval và số đo CI.
- Chọn poll interval đủ nhanh nhưng không truy vấn registry quá dày.
- Chỉ dùng pollDelay khi có lý do rõ ràng.
- Chỉ ignore exception tạm thời đã xác định; không nuốt mọi exception.
- Dùng service ID và instance ID riêng để tránh dữ liệu từ test khác.
- Kiểm tra riêng registry-native state và consumer state khi cần chẩn đoán propagation.
- Chờ deregistration theo semantics thật của Eureka, Consul hoặc ZooKeeper.
- Đóng provider context và registry container sau test.
- Dùng alias để timeout chỉ ra điều kiện đang chờ.
- Không dùng Awaitility trong code production thay cho discovery/retry mechanism.

## Kết luận

Service registration, health update và deregistration đều có thể hội tụ bất đồng bộ qua registry, discovery client và LoadBalancer cache. Thread.sleep() cố định không chứng minh điều kiện đã đạt; nó chỉ làm test chờ một khoảng thời gian được đoán trước. Awaitility cho phép test kiểm tra lại trạng thái đến khi assertion thành công hoặc timeout, nhờ đó test nhanh hơn khi điều kiện đến sớm và dễ chẩn đoán hơn khi điều kiện không bao giờ đến.

Hãy chờ đúng lớp mà test cần xác minh: registry-native API để kiểm tra bản ghi, DiscoveryClient để kiểm tra góc nhìn consumer, health API để kiểm tra trạng thái và request thật để kiểm tra data plane. Chọn timeout theo chu kỳ cập nhật của hệ thống, đặt poll interval hợp lý, tránh bỏ qua exception quá rộng và luôn dọn dẹp registration sau test.

## Tài liệu tham khảo

- Awaitility — Usage and DSL: https://github.com/awaitility/awaitility/wiki/Usage
- Awaitility — Javadoc: https://javadoc.io/doc/org.awaitility/awaitility/latest/index.html
- Spring Cloud Commons — DiscoveryClient: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud Netflix — Eureka Client: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Spring Cloud Consul — Service Discovery: https://docs.spring.io/spring-cloud-consul/reference/discovery.html
- Spring Cloud Zookeeper — Service Discovery: https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html
