# POST refresh thành công nhưng bean vẫn giữ giá trị cũ

Một Config Client có thể trả HTTP 200 từ `POST /actuator/refresh` nhưng service vẫn xử lý request bằng giá trị cấu hình cũ. Tình huống này thường xảy ra vì refresh đã cập nhật Spring Environment nhưng bean đang sử dụng giá trị được capture từ trước, bean không thuộc cơ chế rebind/refresh, hoặc thành phần runtime như connection pool vẫn giữ tài nguyên được tạo bằng cấu hình cũ.

Muốn chẩn đoán chính xác, cần tách bốn trạng thái: Config Server đã có giá trị mới chưa; Config Client đã nạp giá trị mới vào Environment chưa; bean đã nhận giá trị mới chưa; và tài nguyên thực tế đã chuyển sang cấu hình mới chưa. Bài viết hướng dẫn kiểm tra theo thứ tự đó, giải thích vai trò của `@ConfigurationProperties`, `@Value`, `@RefreshScope`, cách xử lý dependency chain và cách viết integration test để tránh kết luận sai từ một response HTTP thành công.

## 1. HTTP 200 từ refresh chứng minh điều gì?

Endpoint `POST /actuator/refresh` thuộc Spring Cloud Context. Khi được gọi, client thực hiện quy trình làm mới Environment, phát sự kiện thay đổi thuộc tính và làm mới RefreshScope. Response thường là danh sách key được nhận diện là đã thay đổi; danh sách rỗng có thể có nghĩa không phát hiện thay đổi giữa các lần đọc cấu hình.

HTTP 200 cho biết request đã được xử lý thành công ở endpoint. Nó không chứng minh mọi singleton, mọi object được tạo thủ công, mọi connection pool hoặc mọi instance trong cụm đều đã sử dụng giá trị mới.

| Trạng thái | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Config Server | Nguồn đã có revision/giá trị mới chưa? | Environment endpoint, label, Git version |
| Config Client Environment | Client đã nạp property source mới chưa? | `/actuator/env/{property}`, refresh response |
| Spring bean | Bean đã rebind hoặc được tạo lại chưa? | `/actuator/configprops`, kiểm tra bean có kiểm soát |
| Runtime resource | Pool/client/cache đang hoạt động theo giá trị nào? | Kết nối mới, metric, hành vi thực tế |

Đừng bắt đầu bằng cách restart tất cả instance. Trước hết xác định trạng thái dừng ở lớp nào; điều đó giúp sửa đúng nguyên nhân và giữ lại bằng chứng chẩn đoán.

## 2. Luồng refresh từ Config Server đến bean

Với Config Client dùng Config Data import, luồng thường diễn ra như sau:

~~~mermaid
flowchart TD
    G[Git / Vault / Native backend] --> CS[Config Server]
    CS -->|Environment mới| E[Config Client Environment]
    R[POST /actuator/refresh] --> CR[ContextRefresher]
    CR --> E
    E --> EC[EnvironmentChangeEvent]
    EC --> RP[ConfigurationPropertiesRebinder]
    EC --> LR[LoggingSystem rebinder]
    CR --> RS[RefreshScope cache invalidation]
    RP --> B[Rebound configuration beans]
    RS --> T[RefreshScope target tạo lại khi được gọi]
    B --> A[Application service]
    T --> A
    A --> D[DataSource / HTTP client / cache]
~~~

Các bước có trách nhiệm khác nhau:

1. Config Client lấy cấu hình mới từ Config Server.
2. Spring Environment cập nhật property source.
3. Spring Cloud Context phát `EnvironmentChangeEvent`.
4. Các listener phù hợp, ví dụ rebinder, cập nhật bean được hỗ trợ.
5. RefreshScope xóa target bean khỏi cache; target mới được tạo khi proxy được gọi lần tiếp theo.
6. Các resource do bean quản lý cần xử lý vòng đời riêng.

Nếu Environment đã có giá trị mới nhưng bean vẫn cũ, tập trung kiểm tra bước 4 đến 6. Nếu Environment cũng cũ, quay lại Config Server, application/profile/label và property source precedence.

## 3. Xác nhận Config Server thực sự trả giá trị mới

Trước khi kiểm tra client, gọi trực tiếp Config Server với đúng application, profile và label:

~~~bash
curl --fail --silent --show-error \
  https://config.internal.example/orders-service/prod/main
~~~

Với Git backend, response Environment thường có các trường:

- `name`: application được yêu cầu.
- `profiles`: profile được áp dụng.
- `label`: branch, tag hoặc revision được yêu cầu.
- `version`: Git revision đã dùng.
- `propertySources`: các nguồn cung cấp thuộc tính.

Chỉ kiểm tra key không nhạy cảm hoặc metadata. Config Server có thể giải mã secret trước khi trả Environment; không lưu toàn bộ response vào ticket, terminal transcript hoặc log tập trung.

Nếu Config Server vẫn trả giá trị cũ:

1. Kiểm tra commit đã được merge/push lên đúng repository chưa.
2. Kiểm tra label có trỏ đến revision mới không.
3. Kiểm tra application name và profile có đúng không.
4. Kiểm tra Git backend đã fetch revision mới chưa.
5. Kiểm tra search paths và file cấu hình tương ứng.
6. Nếu dùng Vault hoặc composite backend, kiểm tra version của từng nguồn.

Refresh trên client không thể làm xuất hiện một giá trị mà Config Server chưa cung cấp. Khi server đã trả đúng giá trị, mới tiếp tục kiểm tra client.

## 4. Xác nhận Config Client Environment đã đổi

Dùng Actuator `env` cho một key không nhạy cảm:

~~~bash
curl --fail --silent --show-error \
  https://orders-1.internal/actuator/env/orders.http.read-timeout
~~~

Response của endpoint có thể cho biết giá trị hiệu lực, property source và origin tùy phiên bản Spring Boot. So sánh kết quả trước và sau refresh.

Nếu Environment vẫn giữ giá trị cũ, kiểm tra:

- Client có kết nối đúng Config Server không?
- Client có đúng `spring.application.name`, profile và label không?
- Config Data import có được cấu hình không?
- Có lỗi network, TLS, authentication hoặc authorization khi fetch không?
- Có biến môi trường, JVM system property, command line hoặc file local ghi đè remote không?
- Remote override policy có cho phép nguồn local thắng hay không?

Ví dụ key `orders.http.read-timeout` có thể bị biến môi trường `ORDERS_HTTP_READTIMEOUT` ghi đè tùy thứ tự ưu tiên và chính sách Config Server. Khi response Environment cho thấy local property source thắng, cần sửa nguồn override hoặc quy tắc precedence; gọi refresh lặp lại sẽ không thay đổi kết quả.

Actuator `env` có thể tiết lộ thông tin nhạy cảm. Chỉ expose trong mạng quản trị với authentication, authorization và sanitization. Không tắt sanitization để đọc password hoặc token.

## 5. Đọc danh sách key trong response refresh

Ví dụ gọi endpoint:

~~~bash
curl --fail --silent --show-error -X POST \
  https://orders-1.internal/actuator/refresh
~~~

Spring Cloud Context thường trả về danh sách key thay đổi trong Environment. Có thể diễn giải kết quả:

| Kết quả | Ý nghĩa cần kiểm tra |
| --- | --- |
| Có key trong danh sách | Context refresher nhận diện được thay đổi của key đó |
| Danh sách rỗng | Không phát hiện key thay đổi; có thể client đang nhận cùng giá trị hoặc property source không đổi |
| HTTP 401/403 | Request bị chặn bởi authentication/authorization |
| HTTP 404 | Endpoint chưa được expose hoặc Actuator không được cấu hình |
| HTTP 5xx | Có lỗi trong quá trình refresh; cần đọc log đã sanitize |

Danh sách key không phải danh sách bean đã được tạo lại. Một key có trong response không chứng minh mọi bean sử dụng key đó đã nhận giá trị mới. Cần kiểm tra bean và resource ở các bước tiếp theo.

Nếu endpoint trả danh sách rỗng nhưng Config Server đã có revision mới, kiểm tra client có thật sự fetch đúng label không và property source có thay đổi đối với application/profile đó không. Một thay đổi trong file của service khác sẽ không nhất thiết tạo thay đổi ở client hiện tại.

## 6. Phân biệt @Value với @ConfigurationProperties

Hai cách binding phổ biến có hành vi khác nhau khi refresh.

### @Value trên singleton thông thường

Ví dụ:

~~~java
@Service
public class OrderService {

    private final Duration readTimeout;

    public OrderService(
            @Value("${orders.http.read-timeout}") Duration readTimeout) {
        this.readTimeout = readTimeout;
    }

    public Duration currentTimeout() {
        return readTimeout;
    }
}
~~~

Constructor chỉ chạy khi Spring tạo bean. Nếu `OrderService` là singleton thông thường, field `readTimeout` giữ giá trị đã capture lúc khởi tạo. Environment đổi không tự chạy lại constructor.

Đây là nguyên nhân phổ biến khiến endpoint refresh trả thành công nhưng service vẫn dùng giá trị cũ. Muốn thay đổi động, có thể đưa cấu hình vào một bean được hỗ trợ rebind hoặc đặt component phụ thuộc cấu hình trong RefreshScope để tạo target mới.

### @ConfigurationProperties mutable

Ví dụ:

~~~java
@Component
@ConfigurationProperties(prefix = "orders.http")
public class OrdersHttpProperties {

    private Duration readTimeout = Duration.ofSeconds(5);

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Spring Cloud Context có cơ chế rebind các bean `@ConfigurationProperties` được hỗ trợ khi Environment thay đổi. Tuy nhiên, cần xác nhận bean được đăng ký đúng, binder có thể bind lại các thuộc tính và code không giữ một bản sao cũ ở nơi khác.

Nếu service đã copy giá trị từ `OrdersHttpProperties` vào field lúc khởi tạo, việc rebind properties bean không tự cập nhật field copy đó. Service cần đọc properties bean khi sử dụng hoặc được tạo lại theo vòng đời phù hợp.

### Constructor-bound immutable properties

Record hoặc immutable configuration properties rất hữu ích để bảo đảm dữ liệu không bị sửa tùy tiện, nhưng không có setter để rebind từng thuộc tính. Không nên giả định mọi immutable bean tự cập nhật sau refresh. Hãy kiểm tra khả năng refresh của kiểu binding trong phiên bản đang dùng; nếu cần tạo lại object, đặt nó sau một proxy/bean có vòng đời refresh hoặc xây dựng snapshot mới bằng cơ chế rõ ràng.

## 7. Dùng @RefreshScope cho bean cần tạo lại

`@RefreshScope` tạo scoped proxy cho bean. Khi refresh scope, target hiện tại bị loại khỏi cache; lần gọi tiếp theo qua proxy sẽ tạo target mới với Environment hiện hành.

Ví dụ:

~~~java
@Component
@RefreshScope
public class DynamicOrderPolicy {

    private final Duration readTimeout;
    private final int maxAttempts;

    public DynamicOrderPolicy(
            @Value("${orders.http.read-timeout}") Duration readTimeout,
            @Value("${orders.retry.max-attempts}") int maxAttempts) {
        this.readTimeout = readTimeout;
        this.maxAttempts = maxAttempts;
    }

    public Duration readTimeout() {
        return readTimeout;
    }

    public int maxAttempts() {
        return maxAttempts;
    }
}
~~~

Khi `DynamicOrderPolicy` được gọi qua proxy sau refresh, target mới được tạo và constructor đọc giá trị mới.

Có một số lưu ý:

- Bean phải được Spring quản lý và được inject qua proxy, không tự gọi `new DynamicOrderPolicy(...)`.
- Caller không nên giữ reference tới target nội bộ cũ hoặc copy các field cấu hình ra nơi khác.
- Target mới thường được tạo lười ở lần gọi tiếp theo, không nhất thiết ngay trong request refresh.
- Nếu target quản lý resource cần đóng, hãy xác định destroy lifecycle và request đang sử dụng target cũ.
- Không phải mọi bean đều phù hợp để refresh; connection pool và thread pool cần chiến lược thay thế riêng.

Đặt `@RefreshScope` trên một class `@Configuration` không đồng nghĩa mọi bean được khai báo bên trong đều tự động trở thành refresh-scoped. Nếu một bean cụ thể cần tạo lại, hãy đặt scope trên chính bean đó hoặc thiết kế dependency chain để bean tiêu thụ được tạo lại cùng lúc.

## 8. Kiểm tra bean thực sự có đi qua proxy

Một lỗi thường gặp là code gọi bean từ reference không qua Spring proxy. Ví dụ:

~~~java
// Không nên tự tạo bean cấu hình
DynamicOrderPolicy policy = new DynamicOrderPolicy(
        Duration.ofSeconds(5), 3);
~~~

Đối tượng tạo bằng `new` không thuộc ApplicationContext, nên Spring không quản lý RefreshScope cho nó.

Hãy inject bean qua constructor:

~~~java
@Service
public class OrderFacade {

    private final DynamicOrderPolicy policy;

    public OrderFacade(DynamicOrderPolicy policy) {
        this.policy = policy;
    }

    public Duration readTimeout() {
        return policy.readTimeout();
    }
}
~~~

Trong Spring AOP, proxy được inject vào `OrderFacade`. Khi gọi method sau refresh, proxy phân giải target hiện hành. Nếu caller tự unwrap proxy hoặc giữ target reference nội bộ, cơ chế thay target có thể bị bỏ qua.

Không cần log toàn bộ object hoặc proxy metadata trong production. Có thể xác minh trong integration test bằng cách đọc giá trị qua chính service đang sử dụng bean.

## 9. Dependency chain có thể giữ giá trị cũ

Giả sử `OrderFacade` phụ thuộc vào `HttpClientFactory`, và factory tạo một `WebClient` lúc khởi động:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    WebClient orderWebClient(
            @Value("${orders.http.base-url}") String baseUrl,
            @Value("${orders.http.read-timeout}") Duration timeout) {
        // Tạo WebClient với base URL và timeout.
        return WebClient.builder()
                .baseUrl(baseUrl)
                .build();
    }
}
~~~

Ngay cả khi một bean properties đã rebind, `WebClient` được tạo trước đó có thể giữ timeout cũ. Nếu `OrderFacade` giữ WebClient singleton, nó tiếp tục sử dụng object cũ.

Có thể đặt refresh scope lên bean tạo client:

~~~java
@Bean
@RefreshScope
WebClient orderWebClient(
        @Value("${orders.http.base-url}") String baseUrl,
        @Value("${orders.http.read-timeout}") Duration timeout) {
    HttpClient httpClient = HttpClient.create()
            .responseTimeout(timeout);

    return WebClient.builder()
            .baseUrl(baseUrl)
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
}
~~~

Ví dụ dùng Reactor Netty: `HttpClient` được cấu hình response timeout rồi gắn vào WebClient qua `ReactorClientHttpConnector`. Cần có Reactor Netty trên classpath; nếu dự án dùng connector khác, cấu hình timeout bằng API của connector đó. Khi làm mới client có resource, phải kiểm tra cách đóng connection pool và tài nguyên native.

Với dependency chain dài, xác định object nào đã capture cấu hình và object nào phải được tạo lại. Có thể chỉ cần refresh-scoped factory hoặc client, nhưng caller phải tiếp tục gọi qua proxy thay vì giữ một instance cũ được tạo thủ công.

## 10. Connection pool và DataSource cần xử lý riêng

DataSource thường tạo connection pool khi bean được khởi tạo. Pool có thể giữ username/password, JDBC URL, maximum pool size và timeout đã đọc trước đó. Environment thay đổi không tự thay đổi những thông số đã được truyền vào pool.

Đối với credential hoặc endpoint thay đổi, quy trình an toàn thường là:

1. Tạo pool mới bằng cấu hình mới.
2. Kiểm tra pool mới mở được connection.
3. Chuyển request mới sang pool mới.
4. Chờ transaction và request đang dùng pool cũ hoàn tất.
5. Đóng pool cũ sau khi drain.
6. Thu hồi credential cũ sau khi không còn kết nối cần nó.

Không nên mặc định đánh dấu HikariDataSource là refreshable rồi để Spring đóng pool cũ ngay khi refresh. Một số loại bean được đánh dấu never-refreshable theo mặc định vì việc tạo lại không an toàn. Cần kiểm tra danh sách refreshable/never-refreshable trong phiên bản Spring Cloud đang dùng và thiết kế pool replacement có kiểm soát.

Nếu chỉ thay đổi `maximum-pool-size`, kiểm tra xem pool implementation có API runtime để cập nhật thuộc tính đó an toàn không. Có thể cập nhật trực tiếp một số thuộc tính được hỗ trợ thay vì tạo lại toàn bộ pool. Không áp dụng chung một cách cho mọi datasource.

## 11. Kiểm tra @ConfigurationProperties bằng Actuator

Actuator `configprops` giúp kiểm tra giá trị đã bind vào các bean `@ConfigurationProperties`:

~~~bash
curl --fail --silent --show-error \
  https://orders-1.internal/actuator/configprops
~~~

Chỉ expose endpoint trong môi trường quản trị với authentication/authorization và sanitization. Tập trung vào bean prefix liên quan, ví dụ `orders.http`, và so sánh giá trị không nhạy cảm trước/sau refresh.

Kết hợp với `env`:

~~~bash
curl --fail --silent --show-error \
  https://orders-1.internal/actuator/env/orders.http.read-timeout
~~~

Có thể diễn giải:

- Environment mới, configprops mới: binding đã cập nhật.
- Environment mới, configprops cũ: kiểm tra rebinder, registration và kiểu binding.
- Environment mới, configprops mới, hành vi cũ: kiểm tra service đã copy giá trị hay resource giữ cấu hình cũ.
- Environment cũ: quay lại Config Server, fetch và precedence.

Không tắt sanitization để xem secret. Với credential, xác minh bằng kết nối thử hoặc metric, không trả password ra endpoint.

## 12. Ví dụ test chứng minh singleton giữ giá trị cũ

Một test đơn giản có thể thể hiện vì sao constructor-injected singleton không tự cập nhật:

~~~java
@SpringBootTest
class RefreshBehaviorTest {

    @Autowired
    Environment environment;

    @Autowired
    OrderService orderService;

    @Test
    void demonstratesEnvironmentAndSingletonCanDiffer() {
        Duration environmentValue = environment.getProperty(
                "orders.http.read-timeout",
                Duration.class);

        Duration capturedValue = orderService.currentTimeout();

        assertThat(environmentValue).isEqualTo(Duration.ofSeconds(10));
        assertThat(capturedValue).isEqualTo(Duration.ofSeconds(5));
    }
}
~~~

Đây là test minh họa cho một tình huống trong đó Environment đã đổi nhưng bean singleton vẫn giữ giá trị cũ. Trong dự án thật, cần điều khiển Config Server/test property source và gọi refresh trong test; không giả định Spring Test tự thay Environment nếu không có thao tác cập nhật.

Một integration test đầy đủ nên xác nhận cả trước và sau:

1. Khởi động client với `read-timeout=5s`.
2. Xác nhận Environment và bean ban đầu đều là 5s.
3. Thay Config Server test source thành 10s.
4. Gọi `POST /actuator/refresh`.
5. Xác nhận Environment là 10s.
6. Xác nhận bean mutable properties hoặc RefreshScope target là 10s.
7. Xác nhận singleton không refresh vẫn là 5s nếu thiết kế giữ giá trị đã capture.
8. Chuyển service sang bean refresh-aware và xác nhận request mới dùng 10s.
9. Kiểm tra request đang chạy trước refresh hoàn tất theo policy cũ nếu thiết kế cho phép.
10. Xác nhận không có secret xuất hiện trong assertion message hoặc log.

## 13. Ví dụ test RefreshScope với Awaitility

RefreshScope target thường được tạo lại ở lần gọi proxy tiếp theo. Có thể kiểm tra giá trị qua service được inject:

~~~java
import static org.awaitility.Awaitility.await;

@SpringBootTest
class RefreshScopeIntegrationTest {

    @Autowired
    OrderFacade orderFacade;

    @Autowired
    ConfigTestSupport configTestSupport;

    @Test
    void refreshScopeUsesNewEnvironmentValue() {
        assertThat(orderFacade.readTimeout())
                .isEqualTo(Duration.ofSeconds(5));

        configTestSupport.updateReadTimeout(Duration.ofSeconds(10));
        configTestSupport.refreshClient();

        await().atMost(Duration.ofSeconds(20)).untilAsserted(() ->
                assertThat(orderFacade.readTimeout())
                        .isEqualTo(Duration.ofSeconds(10)));
    }
}
~~~

`ConfigTestSupport` là helper của dự án test, chịu trách nhiệm cập nhật backend và gọi endpoint refresh. Nó không phải class có sẵn của Spring. Nếu refresh diễn ra đồng bộ trong test, assertion có thể chạy ngay sau response; Awaitility hữu ích khi backend, event hoặc test harness xử lý bất đồng bộ.

Không dùng `Thread.sleep()` để đoán thời điểm target mới xuất hiện. Dùng điều kiện quan sát được và timeout rõ ràng.

## 14. Khi nào cần @RefreshScope, khi nào cần restart?

Không phải mọi bean đều nên refresh.

| Thành phần | Cách xử lý thường phù hợp |
| --- | --- |
| Mutable `@ConfigurationProperties` được hỗ trợ rebind | Kiểm tra rebinding sau refresh |
| Singleton dùng `@Value` trong constructor | Đưa cấu hình vào bean refresh-aware hoặc restart |
| HTTP client được tạo từ URL/timeout | Tạo lại client có kiểm soát hoặc dùng client hỗ trợ cập nhật |
| DataSource/connection pool | Pool replacement, drain hoặc rolling restart |
| Thread pool/executor | Xem API runtime hoặc tạo lại với lifecycle an toàn |
| Static final field | Không thể cập nhật bằng refresh thông thường; thay thiết kế hoặc restart |
| Cache chứa kết quả từ cấu hình cũ | Invalidate/rebuild cache theo policy |
| Bean không hỗ trợ refresh | Rolling restart nếu không có cơ chế cập nhật riêng |

Restart là lựa chọn hợp lý khi resource không thể thay thế an toàn hoặc ứng dụng chưa được thiết kế để refresh động. Trong cụm nhiều instance, dùng rolling restart để giữ khả năng phục vụ; xác nhận Config Server đã có revision đích trước khi tạo process mới.

## 15. Kiểm tra property source precedence và override

Một nguyên nhân khác là client đã refresh nhưng giá trị hiệu lực vẫn không đổi vì một nguồn có ưu tiên cao hơn remote.

Ví dụ:

| Nguồn | Giá trị |
| --- | --- |
| Config Server | `10s` |
| `application.yml` local | `5s` |
| Environment variable | `3s` |
| Command line | `2s` |

Giá trị cuối cùng phụ thuộc vị trí ưu tiên và remote override flags mà Config Server gửi. Nếu client được phép override remote, biến môi trường hoặc command line có thể tiếp tục thắng sau refresh.

Kiểm tra origin/property source trong `/actuator/env/{key}`. Nếu giá trị cũ đến từ local source, sửa nguồn đó hoặc điều chỉnh chính sách override. Đừng tiếp tục gọi refresh vì endpoint không thể thay đổi thứ tự ưu tiên đã cấu hình.

## 16. Phân biệt refresh một instance với refresh toàn cụm

`POST /actuator/refresh` chỉ refresh instance nhận request. Nếu có nhiều replica, gọi endpoint trên một pod không làm các pod khác tự cập nhật.

Có thể dùng Spring Cloud Bus:

~~~bash
curl --fail --silent --show-error -X POST \
  https://orders-1.internal/actuator/busrefresh
~~~

Hoặc destination có chọn lọc theo service/instance nếu phiên bản hỗ trợ:

~~~bash
curl --fail --silent --show-error -X POST \
  https://orders-1.internal/actuator/busrefresh/orders-service:**
~~~

Bus event được xử lý bất đồng bộ. Cần kiểm tra từng instance sau event; HTTP 200 chỉ cho biết endpoint đã tiếp nhận lệnh phát sự kiện. Nếu client không kết nối broker hoặc không nhận event, instance đó có thể tiếp tục dùng giá trị cũ.

Không dùng Bus để che giấu lỗi bean lifecycle. Nếu tất cả instance nhận event nhưng cùng một singleton vẫn giữ giá trị cũ, nguyên nhân nằm ở cách bean capture cấu hình, không phải phạm vi event.

## 17. Log và metric phục vụ chẩn đoán

Trong môi trường test hoặc staging, có thể bật log có mục tiêu cho Spring Cloud Context, Config Client và binding. Chỉ tăng log level trong thời gian ngắn, tránh log request body hoặc secret.

Các tín hiệu hữu ích:

| Tín hiệu | Điều cần quan sát |
| --- | --- |
| Refresh request count/result | Endpoint có được gọi và xử lý không |
| Changed key count | Environment có phát hiện thay đổi không |
| Config fetch status/duration | Client lấy Environment thành công không |
| Active config release ID | Instance đang dùng release nào |
| RefreshScope target generation | Target mới đã được tạo chưa |
| Bean binding validation failure | Binding/rebind có lỗi không |
| Pool/client generation | Resource đang dùng cấu hình nào |
| Last successful application time | Khi nào runtime xác nhận áp dụng thành công |

Không đưa giá trị secret, token, password hoặc user-specific data vào metric label. Release ID và generation nên là metadata không nhạy cảm. Nếu cần xác minh một secret đã đổi, kiểm tra kết nối hoặc trạng thái xác thực mà không in giá trị.

## 18. Bảo vệ endpoint refresh và dữ liệu chẩn đoán

Endpoint `refresh`, `env` và `configprops` có thể ảnh hưởng hoặc tiết lộ trạng thái ứng dụng.

- Chỉ expose endpoint cần thiết trong `management.endpoints.web.exposure.include`.
- Bảo vệ POST refresh bằng authentication và authorization.
- Giới hạn truy cập Actuator qua mạng quản trị hoặc gateway nội bộ.
- Giữ sanitization của `env` và `configprops`.
- Không log plaintext secret hoặc toàn bộ Environment.
- Ghi audit người gọi refresh, thời điểm, service và release ID.
- Dùng HTTPS giữa Config Client và Config Server.
- Nếu dùng Bus, bảo vệ broker credential và quyền publish/consume.

Ví dụ chỉ expose endpoint cần cho môi trường kiểm thử:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,refresh
~~~

Không dùng danh sách expose này mặc định cho production. Chỉ mở `env` và `configprops` khi có yêu cầu chẩn đoán, với quyền truy cập chặt và sanitization được xác minh.

## 19. Playbook chẩn đoán theo thứ tự

Khi `POST /actuator/refresh` trả thành công nhưng bean vẫn giữ giá trị cũ, thực hiện:

1. **Kiểm tra nguồn**: gọi Config Server bằng đúng application/profile/label; xác nhận revision và key không nhạy cảm.
2. **Kiểm tra client fetch**: xem log và response refresh; xác nhận client đã lấy đúng Environment.
3. **Kiểm tra Environment**: đọc `/actuator/env/{key}`; xác định property source thắng.
4. **Kiểm tra binding**: đọc `configprops` hoặc kiểm tra bean trong test.
5. **Kiểm tra bean lifecycle**: bean có phải singleton capture `@Value`, mutable properties hay RefreshScope target?
6. **Kiểm tra proxy**: caller có inject bean qua Spring proxy hay đang giữ object tạo thủ công?
7. **Kiểm tra dependency chain**: client, pool, cache hoặc executor nào đã capture giá trị cũ?
8. **Kiểm tra phạm vi**: endpoint refresh được gọi trên một instance hay Bus đã gửi đến tất cả instance?
9. **Kiểm tra runtime**: request mới hoặc connection mới có dùng giá trị đích không?
10. **Chọn cách phục hồi**: sửa binding, thêm refresh scope, thay resource có kiểm soát hoặc rolling restart.
11. **Xác minh hội tụ**: kiểm tra từng instance và ghi nhận release ID sau khi áp dụng.

Nếu phát hiện cấu hình mới không hợp lệ, không ép refresh bean bằng cách xóa cache liên tục. Khôi phục cấu hình hợp lệ hoặc giữ target hiện tại theo policy, sửa nguồn rồi thử lại.

## 20. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Refresh trả 200, danh sách key rỗng | Client không nhận giá trị khác hoặc không fetch đúng nguồn | Kiểm tra Config Server, label và profile |
| Environment mới nhưng `@Value` vẫn cũ | Singleton đã capture giá trị trong constructor/field | Đưa cấu hình vào bean rebind/RefreshScope hoặc restart |
| `configprops` cũ | Bean không được đăng ký/bind lại hoặc kiểu binding không hỗ trợ | Kiểm tra annotation, registration và constructor binding |
| Properties bean mới nhưng service cũ | Service đã copy giá trị vào field | Đọc properties động hoặc tạo lại service |
| Bean refresh nhưng HTTP client cũ | Client được giữ trong singleton khác | Refresh-aware client factory hoặc thay resource |
| DataSource không đổi credential | Pool giữ credential khi được tạo | Tạo pool mới, kiểm tra kết nối, drain pool cũ |
| Một pod đổi, pod khác không đổi | Chỉ gọi refresh local hoặc Bus event không tới | Gọi Bus có chọn lọc và kiểm tra từng pod |
| Giá trị remote vẫn bị local ghi đè | Environment variable/CLI/file local có ưu tiên cao | Kiểm tra origin và remote override flags |
| Target cũ vẫn chạy sau refresh | Request đang thực thi hoặc caller giữ target reference | Chờ request hoàn tất, kiểm tra proxy và reference |
| Restart lại có giá trị cũ | Label/deployment vẫn trỏ revision cũ | Kiểm tra Config Client label và Config Server revision |

## 21. Nguyên tắc thiết kế

- Coi HTTP 200 là kết quả của endpoint, không phải bằng chứng bean đã cập nhật.
- Xác nhận Config Server trước, rồi Environment, bean và runtime resource.
- Dùng `@ConfigurationProperties` cho nhóm thuộc tính có cấu trúc; xác minh rebinding thực tế.
- Dùng `@RefreshScope` cho bean có thể tạo lại an toàn và được gọi qua proxy.
- Tránh copy cấu hình vào static field hoặc singleton không có lifecycle refresh.
- Thiết kế dependency chain để client/pool được tạo lại hoặc cập nhật đúng cách.
- Với DataSource, executor và resource dài hạn, dùng handover/drain hoặc rolling restart.
- Kiểm tra property source precedence trước khi lặp lại refresh.
- Phân biệt refresh local và Bus refresh nhiều instance.
- Kiểm tra từng client instance bằng release ID và hành vi không nhạy cảm.
- Bảo vệ Actuator, log và mọi dữ liệu chẩn đoán có thể chứa secret.

Một lần refresh chỉ thực sự hữu ích khi giá trị đi từ backend đến Environment, được bean nhận và được tài nguyên runtime sử dụng. Nếu bean vẫn giữ giá trị cũ, hãy xác định nó đã capture cấu hình ở đâu, có hỗ trợ rebind hoặc được tạo lại không, và caller có đang đi qua proxy hay không. Kiểm tra theo từng lớp giúp xử lý đúng nguyên nhân, tránh refresh lặp vô ích và bảo đảm các Config Client trong hệ thống Spring Boot dùng cùng cấu hình mong muốn.

## Tài liệu tham khảo

- [Spring Cloud Context – Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config – Client Configuration](https://docs.spring.io/spring-cloud-config/reference/client.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)

