# Vô hiệu hóa target và tạo lại khi được gọi tiếp

@RefreshScope của Spring Cloud cho phép một bean được tạo lại khi cấu hình thay đổi và quá trình refresh được kích hoạt. Cơ chế quan trọng nằm ở **target cache**: Spring giữ một proxy ổn định để các bean khác gọi tới, còn object thực thi phía sau proxy được lưu trong scope. Khi refresh, Spring hủy target đang được cache. Lần gọi tiếp theo qua proxy sẽ tạo target mới theo cấu hình hiện tại.

Vì vậy, refresh scope không nhất thiết tạo lại object ngay tại thời điểm nhận lệnh refresh. Nó **vô hiệu hóa target hiện tại**, sau đó trì hoãn việc tạo target mới đến lần truy cập tiếp theo. Hiểu đúng vòng đời này giúp tránh giữ reference cũ, dự đoán việc giải phóng tài nguyên và thiết kế refresh an toàn trong ứng dụng Spring Cloud.

## 1. Proxy và target là hai đối tượng khác nhau

Khi một bean được đặt trong refresh scope, bean mà các thành phần khác nhận được thường là một **scoped proxy**. Proxy giữ vai trò điểm truy cập ổn định. Mỗi lần gọi phương thức, proxy tìm target hiện tại trong refresh scope rồi chuyển tiếp lời gọi.

Có thể hình dung:

~~~text
CatalogService
     |
     | inject
     v
Refresh-scoped proxy
     |
     | resolve target khi gọi method
     v
RefreshScope target cache
     |
     +-- target hiện tại: RemoteCatalogClient #1
~~~

Hai khái niệm:

- **Proxy:** object được inject vào các bean phụ thuộc; thường tồn tại xuyên suốt vòng đời context.
- **Target:** object thật chứa trạng thái và logic của bean; scope quản lý target trong cache theo tên bean.

Nếu target đã được tạo, proxy chuyển lời gọi tới target đang cache. Nếu target chưa được tạo hoặc đã bị hủy, scope dùng object factory để tạo target mới rồi lưu lại.

### 1.1. Vì sao cần proxy?

Giả sử CatalogService được tạo một lần lúc ứng dụng khởi động và inject một client cần thay đổi endpoint theo cấu hình. Nếu service giữ trực tiếp object client cũ, thay đổi cấu hình không tự thay reference đó.

Refresh scope giải quyết bằng cách để service giữ proxy. Proxy có thể phân giải target mới mà không cần tạo lại toàn bộ CatalogService hoặc ApplicationContext.

~~~mermaid
sequenceDiagram
    participant S as CatalogService
    participant P as Scoped proxy
    participant R as RefreshScope
    participant T1 as Target #1

    S->>P: getCatalog()
    P->>R: Lấy target theo bean name
    R-->>P: Target #1 (cache hit)
    P->>T1: getCatalog()
    T1-->>S: Kết quả
~~~

Proxy giữ điểm gọi ổn định; target có thể thay đổi qua các lần refresh.

## 2. Target cache được tạo khi cần

Refresh scope hoạt động theo kiểu lazy target. Bean proxy có thể được inject vào một consumer trước khi target thực sự được khởi tạo. Khi method đầu tiên được gọi, scope mới tạo target nếu cache chưa có.

Vòng đời đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> ChuaTao: Bean proxy được tạo
    ChuaTao --> DaCache: Lần gọi đầu / tạo target
    DaCache --> BiVoHieuHoa: refresh(beanName)
    BiVoHieuHoa --> DaCacheMoi: Lần gọi kế tiếp / tạo target mới
    DaCacheMoi --> BiVoHieuHoa: refresh(beanName)
    DaCacheMoi --> DaHuy: Context đóng
~~~

Điều này dẫn đến một số hệ quả:

- Việc inject proxy không bảo đảm target đã được khởi tạo.
- Refresh một target chưa từng được tạo không cần xây dựng target mới ngay.
- Target mới thường chỉ xuất hiện khi có lời gọi tiếp theo.
- Nếu không có lời gọi sau refresh, target mới có thể chưa được tạo.
- Lỗi khi tạo target mới có thể xuất hiện ở request đầu tiên sau refresh, thay vì tại thời điểm phát lệnh refresh.

Đây là khác biệt quan trọng giữa “refresh đã hoàn tất” và “mọi target mới đã được tạo thành công”. Refresh scope chỉ quản lý cache và vòng đời target theo nhu cầu truy cập.

## 3. Khai báo bean bằng @RefreshScope

Ví dụ một client gọi catalog service. Ta muốn thay đổi endpoint qua cấu hình mà không phải tạo lại toàn bộ service sử dụng client.

Cấu hình:

~~~yaml
catalog:
  api:
    base-url: https://catalog-v1.example.internal
    connect-timeout: 2s
~~~

Nhóm thuộc tính:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.api")
public class CatalogApiProperties {
    private String baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Đăng ký nhóm cấu hình này bằng `@ConfigurationPropertiesScan` trên class khởi động hoặc `@EnableConfigurationProperties(CatalogApiProperties.class)` trên một class cấu hình. Khi dùng Spring Cloud Config, quy trình refresh cần cập nhật Environment và rebind các bean cấu hình theo cơ chế của phiên bản trước khi target client được tạo lại.

Bean được đặt trong refresh scope:

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    @RefreshScope
    RemoteCatalogClient remoteCatalogClient(CatalogApiProperties properties) {
        return new RemoteCatalogClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout()
        );
    }
}
~~~

Client minh họa:

~~~java
import java.time.Duration;

public class RemoteCatalogClient {
    private final String baseUrl;
    private final Duration timeout;

    public RemoteCatalogClient(String baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    public String endpoint() {
        return baseUrl;
    }

    public Duration timeout() {
        return timeout;
    }

    public String getCatalog() {
        // Gửi request bằng baseUrl và timeout hiện tại.
        return "Catalog from " + baseUrl;
    }
}
~~~

Service phụ thuộc vào bean refresh-scoped:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final RemoteCatalogClient client;

    public CatalogService(RemoteCatalogClient client) {
        this.client = client;
    }

    public String loadCatalog() {
        return client.getCatalog();
    }
}
~~~

Spring inject scoped proxy vào CatalogService. Khi loadCatalog() gọi client.getCatalog(), proxy phân giải target hiện tại. Sau khi target bị invalidated, cùng reference proxy đó sẽ dẫn tới target mới ở lần gọi sau.

Ví dụ là mã minh họa; client thực tế cần cấu hình HTTP connection pool, timeout, TLS, authentication và xử lý lỗi phù hợp. Class target phải tương thích với loại proxy được dùng. Với proxy dựa trên subclass, tránh class hoặc method final; có thể thiết kế theo interface và cấu hình proxy mode thích hợp nếu cần.

## 4. Vô hiệu hóa một target bằng refresh(beanName)

Nếu chỉ một bean cần được tạo lại, có thể inject RefreshScope và gọi refresh(beanName):

~~~java
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.stereotype.Component;

@Component
public class CatalogRefreshManager {
    private final RefreshScope refreshScope;

    public CatalogRefreshManager(RefreshScope refreshScope) {
        this.refreshScope = refreshScope;
    }

    public void refreshCatalogClient() {
        refreshScope.refresh("remoteCatalogClient");
    }
}
~~~

Tên truyền vào là **bean name** được đăng ký trong ApplicationContext, không phải class name, property prefix hay tên Service ID. Với method @Bean tên mặc định thường là tên method; nếu khai báo tên bean tường minh bằng @Bean(name = "..."), hãy dùng đúng tên đó.

Khi refresh("remoteCatalogClient") được gọi, scope hủy target đang cache cho bean đó. Proxy không cần được inject lại. Lần gọi tiếp theo qua proxy sẽ yêu cầu scope tạo target mới.

### 4.1. Refresh một bean không đồng nghĩa refresh toàn bộ ứng dụng

Chỉ target có tên được chỉ định bị vô hiệu hóa. Các bean khác, kể cả bean refresh-scoped khác, vẫn giữ target hiện tại nếu chúng không bị refresh riêng hoặc không nằm trong một lần refresh toàn bộ.

Cách này hữu ích khi:
- Một client duy nhất cần đổi endpoint hoặc credential.
- Một cấu hình có phạm vi hẹp thay đổi độc lập.
- Muốn tránh tạo lại các target không liên quan.

Hãy đảm bảo property mà bean mới cần đọc đã được cập nhật trong Environment trước khi invalidating target. Nếu chỉ gọi refresh(beanName) mà Environment vẫn giữ giá trị cũ, target mới sẽ được tạo từ cấu hình cũ.

## 5. Vô hiệu hóa tất cả target bằng refreshAll()

Khi cần invalidating mọi target đang được quản lý bởi refresh scope, có thể gọi:

~~~java
refreshScope.refreshAll();
~~~

Lệnh này hủy các target hiện có trong refresh scope. Các proxy vẫn là điểm truy cập của consumer. Target mới được tạo lại khi các bean tương ứng được gọi tiếp.

So sánh:

| API | Phạm vi | Hành vi |
| --- | --- | --- |
| refresh("remoteCatalogClient") | Một bean theo tên | Hủy target cache của bean đó |
| refreshAll() | Tất cả target trong refresh scope | Hủy toàn bộ target cache thuộc scope |
| ContextRefresher.refresh() | Quy trình refresh cấu hình ở cấp ứng dụng | Làm mới Environment theo cơ chế được cấu hình rồi yêu cầu refresh scope |

refreshAll() chỉ tác động refresh-scoped targets. Nó không khởi động lại JVM, không tạo lại toàn bộ ApplicationContext và không tự cập nhật dữ liệu ở Config Server.

## 6. Hủy target cũ và tạo target mới diễn ra thế nào?

Khi target bị invalidated, scope thực hiện quá trình hủy object đang quản lý và gọi các callback destruction mà bean hỗ trợ. Sau đó target được loại khỏi cache.

Luồng chi tiết:

~~~mermaid
sequenceDiagram
    participant Ops as Refresh trigger
    participant Scope as RefreshScope
    participant Cache as Target cache
    participant Proxy as Scoped proxy
    participant Factory as Bean factory

    Ops->>Scope: refresh("remoteCatalogClient")
    Scope->>Cache: Xóa target đã cache
    Scope->>Scope: Chạy destruction callbacks
    Scope-->>Ops: Refresh target hoàn tất
    Note over Proxy,Cache: Proxy vẫn tồn tại, cache chưa có target
    Proxy->>Scope: Lời gọi tiếp theo
    Scope->>Factory: Tạo target mới
    Factory-->>Scope: RemoteCatalogClient mới
    Scope->>Cache: Lưu target mới
    Scope-->>Proxy: Trả target mới
    Proxy->>Proxy: Chuyển tiếp method invocation
~~~

Một target có thể giải phóng tài nguyên qua @PreDestroy, DisposableBean hoặc destroy method nếu được cấu hình đúng. Ví dụ, target tự quản lý một HTTP client hoặc connection cần đóng khi bị hủy.

Không nên để target tạo tài nguyên bên ngoài mà không khai báo cách giải phóng. Nếu target cũ không đóng connection pool, thread hoặc file handle, việc refresh nhiều lần có thể gây rò rỉ tài nguyên.

### 6.1. Target cũ và lời gọi đang chạy

Refresh không làm cho một lời gọi đang thực thi giữa chừng chuyển sang target mới. Một request đã bắt đầu dùng target cũ có thể tiếp tục cho đến khi method hoàn tất; thao tác invalidation ảnh hưởng đến việc phân giải target cho các lần truy cập sau.

Trong hệ thống có lưu lượng đồng thời, cần thiết kế target có lifecycle an toàn:
- Tránh đóng tài nguyên khi còn request đang sử dụng nếu lifecycle của client không bảo đảm điều đó.
- Đặt timeout hợp lý cho request.
- Kiểm tra thư viện client hỗ trợ close/drain hay không.
- Có thể dùng chiến lược graceful shutdown/connection pool phù hợp cho việc thay target.

Không nên coi refresh scope là cơ chế chuyển đổi nguyên tử mọi request đang chạy sang một cấu hình mới.

## 7. Refresh target khác với cập nhật Environment

Đây là điểm dễ nhầm nhất.

RefreshScope.refresh(name) hoặc refreshAll() **vô hiệu hóa target cache**. Chúng không tự lấy cấu hình mới từ Config Server, không sửa property source và không thay đổi giá trị trong Environment.

Để cập nhật cấu hình từ xa, một quy trình đầy đủ thường cần:
1. Nguồn cấu hình được cập nhật, ví dụ Config Server hoặc property source khác.
2. Config Client/ContextRefresher tải hoặc áp dụng giá trị mới vào Environment.
3. Cơ chế refresh scope invalidates target đang cache.
4. Lần gọi tiếp theo tạo target mới và đọc property hiện hành.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Config Server / nguồn cấu hình thay đổi"] --> B["Config Client / ContextRefresher"]
    B --> C["Cập nhật Environment và PropertySource"]
    C --> D["RefreshScope.refreshAll()"]
    D --> E["Target cache bị invalidated"]
    E --> F["Proxy nhận lời gọi tiếp theo"]
    F --> G["Tạo target mới từ cấu hình hiện hành"]
~~~

Nếu bỏ qua bước cập nhật Environment, target mới vẫn có thể dùng giá trị cũ. Nếu cập nhật Environment nhưng không refresh bean cần đọc lại property, bean đã giữ trạng thái cũ có thể tiếp tục hoạt động với cấu hình trước đó.

### 7.1. Kích hoạt qua ContextRefresher

Trong các ứng dụng dùng Spring Cloud Context, ContextRefresher điều phối việc refresh Environment và refresh scope theo cơ chế của phiên bản. Có thể gọi từ một thành phần quản trị nội bộ khi thật sự cần:

~~~java
import org.springframework.cloud.context.refresh.ContextRefresher;
import org.springframework.stereotype.Component;

@Component
public class ApplicationRefreshManager {
    private final ContextRefresher contextRefresher;

    public ApplicationRefreshManager(ContextRefresher contextRefresher) {
        this.contextRefresher = contextRefresher;
    }

    public void refreshConfiguration() {
        contextRefresher.refresh();
    }
}
~~~

Cách tải lại property phụ thuộc các PropertySourceLocator, Config Client, Config Data/Bootstrap mode và phiên bản Spring Cloud. Đừng giả định gọi phương thức này sẽ đọc lại mọi nguồn tùy ý hoặc tự đồng bộ mọi replica trong cluster.

### 7.2. Endpoint Actuator và bảo mật

Một số phiên bản Spring Cloud cung cấp refresh endpoint qua Actuator để kích hoạt quy trình refresh. Khi sử dụng, cần:
- Chọn dependency và cấu hình endpoint phù hợp phiên bản.
- Expose endpoint có chủ đích qua management configuration.
- Bảo vệ bằng authentication/authorization và giới hạn network access.
- Ghi audit cho thao tác thay đổi cấu hình.
- Tránh cho người dùng bên ngoài tùy ý kích hoạt refresh.
- Kiểm tra endpoint trả về và trạng thái cấu hình sau khi gọi.

Không nên expose /actuator/refresh công khai. Đây là thao tác quản trị có thể thay đổi hành vi runtime và làm target tạo lại ở lần truy cập tiếp theo.

## 8. Những gì refresh scope không tự làm

Refresh scope chỉ quản lý lifecycle target cho bean thuộc scope. Nó không tự:
- Thay đổi file cấu hình hoặc giá trị ở Config Server.
- Tải property mới từ mọi hệ thống bên ngoài.
- Làm mới tất cả singleton bean không thuộc refresh scope.
- Khởi động lại embedded web server hoặc đổi server.port.
- Cập nhật DNS, registry, load balancer hay cấu hình mạng.
- Chuyển đổi request đang chạy từ target cũ sang target mới.
- Đồng bộ trạng thái cache hoặc object mutable giữa các replica.
- Bảo đảm mọi loại bean/tài nguyên có thể được khởi tạo lại an toàn.

Nếu một property thay đổi nhưng được dùng để tạo tài nguyên không thể thay đổi trong runtime, cần đánh giá restart/redeploy hoặc một cơ chế cập nhật riêng.

## 9. Chọn bean nào nên đặt trong Refresh Scope?

Nên đặt refresh scope cho bean có thể tạo lại an toàn và thực sự cần đọc lại cấu hình trong runtime. Ví dụ:
- HTTP client wrapper có endpoint hoặc timeout thay đổi.
- Một adapter chứa policy có thể tái tạo.
- Một bean cung cấp thông tin cấu hình được dùng qua proxy.
- Một client không giữ trạng thái nghiệp vụ lâu dài và có lifecycle cleanup rõ ràng.

Cần thận trọng với:
- Bean chứa state nghiệp vụ đang thay đổi.
- Transaction manager, connection pool hoặc resource có vòng đời phức tạp.
- Bean được nhiều thành phần giữ trực tiếp target reference thay vì proxy.
- Bean tạo ra side effect khi constructor chạy.
- Bean cần đồng bộ với các replica khác.

Một số loại bean không thể refresh an toàn hoặc được Spring Cloud loại khỏi danh sách refresh mặc định tùy phiên bản. Ví dụ, HikariDataSource thường được cấu hình là never-refreshable trong Spring Cloud. Nếu muốn thay datasource, hãy dùng quy trình quản lý connection pool phù hợp thay vì mặc định gắn @RefreshScope là đủ.

### 9.1. Constructor có side effect

Vì target mới được tạo ở lần truy cập tiếp theo, constructor/factory method có thể chạy ở thời điểm request đầu tiên sau refresh. Nếu constructor thực hiện kết nối mạng, tải metadata hoặc khởi tạo tài nguyên chậm, request đó có thể bị tăng latency.

Có thể cân nhắc:
- Giữ constructor/factory method nhẹ.
- Tách bước khởi tạo nặng khỏi đường request nếu phù hợp.
- Kiểm tra readiness trước khi cho traffic sử dụng target mới.
- Theo dõi lỗi tạo target và latency của request đầu sau refresh.

## 10. Reference cũ có thể làm mất tác dụng refresh

Consumer nên giữ scoped proxy được Spring inject. Nếu code tự lấy target thật, unwrap proxy hoặc lưu target vào một field/static cache khác, reference đó có thể tiếp tục trỏ tới object cũ sau khi scope invalidates cache.

Ví dụ không nên làm:

~~~java
// Ý tưởng minh họa anti-pattern:
RemoteCatalogClient target = unwrapScopedProxy(client);
this.cachedTarget = target;
~~~

Khi scope hủy target cũ và proxy trỏ tới target mới, cachedTarget vẫn có thể giữ object cũ. Tránh:
- Unwrap scoped proxy để lưu target.
- Copy các dependency target vào static field.
- Truyền target thật sang một object sống lâu hơn proxy.
- Tự cache reference target bên ngoài scope.

Hãy inject proxy và gọi qua proxy ở mỗi lần cần sử dụng. Nếu một thư viện buộc phải giữ target trực tiếp, cần thiết kế adapter có thể thay reference sau refresh hoặc dùng cơ chế lifecycle khác.

## 11. Kiểm thử target bị invalidated và tạo lại

Một test có thể đếm số lần factory method tạo target. Sau lần gọi đầu, refresh bean theo tên rồi gọi lại qua proxy; generation mới phải tăng.

Ví dụ minh họa với Spring Boot test:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class RefreshScopeTestApplication {

    static final AtomicInteger generations = new AtomicInteger();

    @Bean
    @RefreshScope
    VersionedClient versionedClient() {
        return new VersionedClient(generations.incrementAndGet());
    }

    public static class VersionedClient {
        private final int generation;

        VersionedClient(int generation) {
            this.generation = generation;
        }

        public int generation() {
            return generation;
        }
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.scope.refresh.RefreshScope;

@SpringBootTest(classes = RefreshScopeTestApplication.class)
class RefreshScopeLifecycleTest {

    @Autowired
    RefreshScopeTestApplication.VersionedClient client;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void targetIsRecreatedOnNextInvocation() {
        int first = client.generation();

        refreshScope.refresh("versionedClient");

        int second = client.generation();

        assertThat(second).isGreaterThan(first);
    }
}
~~~

Test này xác nhận proxy vẫn được sử dụng và target mới xuất hiện sau invalidation. Trong test suite thực tế, cần quản lý trạng thái static AtomicInteger giữa các context/test, tránh test chạy song song làm thay đổi thứ tự generation. Có thể dùng factory counter riêng theo context hoặc reset counter trong setup.

### 11.1. Kiểm thử destruction callback

Ngoài việc xác nhận target mới được tạo, nên kiểm tra target cũ được hủy nếu có tài nguyên cần giải phóng. Một target có thể tăng bộ đếm khi @PreDestroy chạy; sau khi gọi refresh(beanName), test xác nhận callback đã được thực hiện.

Điều này giúp phát hiện rò rỉ connection, thread hoặc resource khi refresh lặp lại.

### 11.2. Kiểm thử cập nhật Environment

Test vòng đời target không tự xác nhận Config Client lấy được cấu hình mới. Một integration test riêng nên:
1. Cung cấp giá trị property ban đầu.
2. Khởi tạo và gọi bean refresh-scoped để tạo target.
3. Thay đổi property source theo cơ chế test.
4. Kích hoạt quy trình refresh phù hợp.
5. Gọi proxy lần nữa.
6. Xác nhận target mới đọc giá trị mới.

Tách test scope khỏi test Config Server giúp xác định rõ lỗi nằm ở cập nhật Environment hay ở lifecycle target.

## 12. Theo dõi và vận hành refresh

Khi refresh xảy ra trong production, nên quan sát:
- Bean name nào được refresh.
- Thời điểm bắt đầu/kết thúc invalidation.
- Target cũ có giải phóng tài nguyên thành công không.
- Target mới có được tạo ở request kế tiếp không.
- Request đầu tiên sau refresh có latency hoặc lỗi tăng không.
- Các replica có nhận cùng cấu hình và cùng trigger không.
- Có property nào bị thiếu khiến target mới không thể khởi tạo không.

Không log credential hoặc nội dung secret khi theo dõi refresh. Chỉ ghi tên bean, version/config revision, trạng thái và correlation ID phù hợp.

Nếu nhiều replica chạy độc lập, gọi refresh trên một instance không tự làm mới các instance còn lại. Cần một cơ chế phát tán trigger hoặc orchestrate refresh tới từng instance; đồng thời bảo đảm mọi instance lấy được cùng phiên bản cấu hình mong muốn.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Gọi refresh nhưng giá trị không đổi | Environment chưa được cập nhật; target mới đọc lại giá trị cũ | Kiểm tra property source và giá trị hiệu lực trước/sau refresh |
| Proxy vẫn tồn tại sau refresh | Đây là hành vi mong đợi; proxy là điểm truy cập ổn định | Kiểm tra target generation thay đổi qua lần gọi tiếp theo |
| Target mới chưa được tạo ngay sau refresh | Refresh scope tạo target lazy khi có lời gọi tiếp theo | Gửi lời gọi qua proxy và quan sát factory |
| Request đầu sau refresh bị lỗi | Target mới được tạo ở thời điểm đó và cấu hình/resource không hợp lệ | Kiểm tra exception khởi tạo target, property bắt buộc và kết nối |
| Bean không được refresh | Bean không thuộc refresh scope hoặc tên bean truyền vào sai | Kiểm tra @RefreshScope, bean name và scope registration |
| Bean cũ vẫn được dùng | Consumer giữ reference target trực tiếp ngoài proxy | Tránh unwrap proxy hoặc cache target |
| Resource bị rò rỉ sau nhiều lần refresh | Target không có destruction callback/cleanup đúng | Kiểm tra @PreDestroy, destroy method và tài nguyên sở hữu |
| Refresh một replica nhưng replica khác không đổi | Trigger chỉ chạy ở một tiến trình | Thiết kế broadcast/orchestration và kiểm tra từng instance |
| Một số bean không thể refresh | Bean/resource nằm trong danh sách không refresh được hoặc không an toàn để tái tạo | Kiểm tra cấu hình refresh và hướng dẫn của release train |
| Refresh làm request tăng latency | Target mới khởi tạo lười ở request đầu tiên | Đo latency, giảm side effect trong factory hoặc warm-up có chủ đích |

## Ghi nhớ

Refresh scope giữ một proxy ổn định và cache target phía sau proxy. Khi gọi refresh(beanName) hoặc refreshAll(), Spring hủy target đang cache; lần gọi tiếp theo qua proxy mới tạo target mới. Cơ chế này không tự cập nhật Environment, không refresh mọi singleton và không chuyển request đang chạy sang target mới. Muốn áp dụng cấu hình ngoài, hãy cập nhật Environment trước, invalidates target sau, bảo đảm target cũ giải phóng tài nguyên và kiểm thử lần gọi đầu tiên sau refresh.
