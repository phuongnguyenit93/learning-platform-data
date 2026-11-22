# Vòng đời hủy target và giải phóng tài nguyên

`@RefreshScope` cho phép Spring Cloud thay thế một bean đang giữ cấu hình cũ bằng một target được tạo lại từ cấu hình mới. Cơ chế này đặc biệt quan trọng với bean sở hữu tài nguyên như connection pool, HTTP client, scheduler, file watcher hoặc message consumer. Khi refresh diễn ra, Spring Cloud loại target hiện tại khỏi cache của scope và gọi các **destruction callback** đã đăng ký. Lần truy cập tiếp theo qua scoped proxy sẽ tạo target mới và chạy lại các bước khởi tạo bình thường.

Điểm cần hiểu kỹ là **proxy và target có vòng đời khác nhau**. Các bean khác thường giữ proxy được inject từ đầu; proxy vẫn tồn tại sau refresh. Đối tượng target cũ được hủy, tài nguyên do nó sở hữu được giải phóng, rồi một target mới được tạo khi cần. Bài học này tập trung vào thứ tự đó, cách đăng ký callback hủy, cách kiểm thử và các giới hạn khi refresh bean đang phục vụ request.

Bài thuộc chương **Refresh Scope** của module **SPRING_CLOUD_CORE**. Nội dung gắn với Spring Cloud Context, cấu hình bên ngoài và vận hành ứng dụng Spring Boot trong hệ thống phân tán.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt scoped proxy, target bean và cache của `RefreshScope`.
2. Mô tả trình tự refresh: loại target, gọi destruction callback, sau đó tạo target mới khi có lần truy cập.
3. Đăng ký giải phóng tài nguyên bằng `@PreDestroy`, `DisposableBean` hoặc `@Bean(destroyMethod = "...")`.
4. Thiết kế bean refreshable có ownership tài nguyên rõ ràng và callback đóng an toàn.
5. Dùng `RefreshScope.refresh(String)` và `refreshAll()` đúng phạm vi.
6. Phân biệt refresh target với cập nhật `Environment`, rebind `@ConfigurationProperties` và broadcast refresh tới nhiều instance.
7. Kiểm thử việc target cũ được hủy và target mới được tạo lại.
8. Nhận diện các giới hạn như HikariDataSource, `@Configuration` scope, bean immutable và AOT/native image.

## 2. Ba thành phần của Refresh Scope

### 2.1. Scoped proxy

Khi một bean được khai báo `@RefreshScope`, Spring tạo một proxy để các consumer inject và gọi. Proxy giữ điểm truy cập ổn định đến bean có scope `refresh`.

Ví dụ, `OrderService` inject `PartnerClient`. Thứ mà `OrderService` giữ là proxy của `PartnerClient`; nó không cần nhận lại một reference mới mỗi khi cấu hình thay đổi.

### 2.2. Target bean

Target là đối tượng thực thi phương thức, được tạo từ bean definition gốc. Target chứa trạng thái và tài nguyên thực tế, ví dụ:

- Endpoint, credential hoặc timeout đã đọc từ `Environment`.
- HTTP connection manager hoặc client transport.
- Connection pool.
- Scheduler, thread hoặc listener.
- Cache nội bộ được khởi tạo theo cấu hình.

Target có thể đăng ký callback khởi tạo và hủy như các bean Spring thông thường.

### 2.3. Target cache

`RefreshScope` lưu target đã khởi tạo trong cache theo tên bean. Khi proxy cần gọi một phương thức, scope tìm target trong cache:

- Có target: sử dụng target hiện tại.
- Chưa có target: tạo từ bean definition, áp dụng dependency injection và initialization callbacks, sau đó lưu vào cache.

Khi refresh, entry tương ứng bị loại khỏi cache. Nếu target đã tồn tại và có destruction callback, callback được chạy trong quá trình hủy. Lần gọi tiếp theo tạo một target mới.

~~~mermaid
flowchart TD
    A[Consumer gọi phương thức] --> B[Scoped proxy]
    B --> C{Target có trong cache?}
    C -- Có --> D[Chuyển lời gọi đến target hiện tại]
    C -- Không --> E[Tạo target từ bean definition]
    E --> F[Inject dependency và chạy init callbacks]
    F --> G[Lưu target vào cache]
    G --> D
    H[Refresh bean] --> I[Loại target khỏi cache]
    I --> J[Chạy destruction callbacks]
    J --> K[Proxy vẫn tồn tại]
    K --> A
~~~

Proxy và target không phải cùng một object. Đây là nền tảng để hiểu vì sao consumer không cần được tạo lại khi target refresh.

## 3. Trình tự hủy và tạo lại target

Một lần refresh cho bean đã được khởi tạo thường diễn ra theo trình tự:

1. Ứng dụng cập nhật nguồn cấu hình hoặc kích hoạt thao tác refresh theo cơ chế đang dùng.
2. `RefreshScope` xác định target cần làm mới.
3. Target hiện tại được loại khỏi cache của scope.
4. Spring chạy destruction callback đã đăng ký cho target đó.
5. Scope phát sự kiện refresh tương ứng.
6. Proxy vẫn được các consumer giữ lại.
7. Khi có lần gọi tiếp theo qua proxy, scope tạo target mới từ bean definition.
8. Dependency và giá trị cấu hình được resolve lại; initialization callbacks chạy cho target mới.
9. Target mới được lưu vào cache và phục vụ những lời gọi tiếp theo.

### 3.1. Refresh không phải sửa field tại chỗ

Giả sử `PartnerClient` được tạo với endpoint `https://partner-v1.internal`. Sau khi cấu hình đổi thành `https://partner-v2.internal`, refresh scope có thể hủy target cũ và tạo target mới dùng endpoint mới.

Đối tượng `PartnerClient` cũ không bị sửa field `baseUrl` thành giá trị mới. Nó được hủy theo lifecycle; một đối tượng mới được tạo từ bean definition và cấu hình hiện tại.

### 3.2. Target mới thường chỉ được tạo khi được dùng

Refresh scope dùng scoped proxy và cache target. Sau khi cache entry bị xóa, refresh operation không cần tạo target thay thế ngay. Target mới được tạo khi proxy nhận lời gọi cần target. Ở thời điểm startup, việc target có được khởi tạo sớm hay không còn phụ thuộc cấu hình eager/lazy và phiên bản; việc thấy proxy trong context không tự chứng minh target đã được tạo.

Điều này có hai hệ quả vận hành:

- Refresh có thể hoàn tất trước khi target mới được khởi tạo.
- Lỗi khởi tạo target mới có thể chỉ xuất hiện ở lần sử dụng tiếp theo.

Một lần gọi `refreshAll()` thành công không tự chứng minh mọi target mới đã khởi tạo thành công hoặc mọi dependency đã kết nối được. Sau refresh, cần kiểm tra các bean quan trọng bằng health check hoặc thao tác xác minh phù hợp.

### 3.3. Bean chưa từng được khởi tạo

Nếu target chưa được tạo, không có instance cũ để giải phóng tài nguyên. Việc refresh cache entry chưa tồn tại không thể chạy callback hủy cho một target chưa từng được tạo.

Vì vậy, số lần callback hủy phụ thuộc vào số target thực tế đã được khởi tạo và đăng ký destruction callback, không đơn giản bằng số lần gọi refresh.

## 4. Destruction callback được đăng ký như thế nào?

Spring quản lý lifecycle của target bean. Khi target được tạo, container ghi nhận các callback hủy mà bean definition hoặc bean instance cung cấp. Refresh scope dùng các callback này khi target bị loại khỏi scope.

### 4.1. Dùng `@PreDestroy`

`@PreDestroy` phù hợp khi bean tự sở hữu tài nguyên và cần đóng chúng trước khi target bị hủy:

~~~java
import jakarta.annotation.PreDestroy;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class PartnerClient {

    private final PartnerTransport transport;

    public PartnerClient(PartnerProperties properties) {
        this.transport = PartnerTransport.open(properties.getBaseUrl());
    }

    public String call(String request) {
        return transport.exchange(request);
    }

    @PreDestroy
    public void close() {
        transport.close();
    }
}
~~~

`PartnerTransport` và `PartnerProperties` là các lớp ví dụ của ứng dụng. Khi target `PartnerClient` bị hủy, Spring gọi `close()` thông qua destruction callback đã đăng ký.

Với Spring Boot 3 trở lên, `@PreDestroy` thường được import từ `jakarta.annotation.PreDestroy`. Các dự án thế hệ cũ có thể dùng namespace `javax.annotation`; hãy theo dependency và phiên bản của dự án.

### 4.2. Dùng `@Bean(destroyMethod = "...")`

Với tài nguyên được tạo bằng Java configuration, có thể khai báo rõ phương thức hủy:

~~~java
@Configuration(proxyBeanMethods = false)
class PartnerClientConfiguration {

    @Bean(destroyMethod = "close")
    @RefreshScope
    PartnerTransport partnerTransport(PartnerProperties properties) {
        return PartnerTransport.open(properties.getBaseUrl());
    }
}
~~~

Khi target `partnerTransport` bị refresh, Spring gọi `close()` theo metadata `destroyMethod`. Cách này làm ownership và lifecycle của tài nguyên dễ nhìn ngay tại nơi khai báo bean.

Dùng `destroyMethod` khi cần kiểm soát rõ tên phương thức giải phóng. Nếu API tài nguyên có phương thức đóng tiêu chuẩn, đây thường là cách ngắn gọn và tường minh.

### 4.3. Implement `DisposableBean`

Bean cũng có thể triển khai `org.springframework.beans.factory.DisposableBean`:

~~~java
import org.springframework.beans.factory.DisposableBean;

public class PartnerTransport implements DisposableBean {

    @Override
    public void destroy() {
        closeTransportResources();
    }

    private void closeTransportResources() {
        // Đóng connection manager, executor hoặc tài nguyên do bean sở hữu.
    }
}
~~~

`DisposableBean` gắn lớp trực tiếp với Spring API. Với code ứng dụng mới, `@PreDestroy` hoặc `@Bean(destroyMethod = "...")` thường giảm coupling hơn. Tuy nhiên, `DisposableBean` vẫn hữu ích khi một lớp cần tích hợp lifecycle Spring rõ ràng.

### 4.4. Không có callback thì sao?

Nếu bean không khai báo destruction callback và không có lifecycle method được Spring nhận diện, Spring không thể tự đoán cách đóng một tài nguyên tùy biến.

Ví dụ, một lớp tự tạo `ExecutorService` trong constructor nhưng không có `shutdown()` được đăng ký sẽ có nguy cơ để lại thread khi target bị refresh. Cần thiết kế callback rõ ràng cho mọi tài nguyên có lifecycle.

## 5. Thiết kế callback giải phóng tài nguyên an toàn

Một callback hủy tốt phải có thể được gọi đúng thời điểm, đóng đúng tài nguyên và xử lý được lỗi trong quá trình shutdown.

### 5.1. Chỉ đóng tài nguyên do target sở hữu

Nếu `PartnerClient` tự tạo một HTTP connection pool, target có trách nhiệm đóng pool đó. Nhưng nếu pool là singleton dùng chung do parent context quản lý, target không nên đóng nó.

Quy tắc ownership:

| Tài nguyên | Ai nên đóng? |
| --- | --- |
| HTTP client được tạo bên trong target | Target sở hữu client |
| Connection pool singleton dùng chung | Bean/context sở hữu pool |
| Scheduler được tạo riêng cho target | Target sở hữu scheduler |
| Executor dùng chung nhiều service | Component quản lý executor |
| Listener đăng ký riêng cho target | Target hủy đăng ký listener |
| File watcher do target tạo | Target dừng watcher và đóng handle |

Đóng nhầm tài nguyên dùng chung có thể khiến những bean khác lỗi ngay sau refresh.

### 5.2. Callback nên có tính idempotent

Trong thực tế, việc đóng tài nguyên có thể được gọi trong nhiều luồng lifecycle hoặc wrapper khác nhau tùy cách bean được cấu hình. Nên thiết kế `close()` an toàn khi được gọi lặp:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

class ManagedTransport implements AutoCloseable {

    private final AtomicBoolean closed = new AtomicBoolean();
    private final NativeTransport delegate;

    ManagedTransport(NativeTransport delegate) {
        this.delegate = delegate;
    }

    @Override
    public void close() {
        if (closed.compareAndSet(false, true)) {
            delegate.close();
        }
    }
}
~~~

`AtomicBoolean` bảo đảm chỉ một lần gọi đi vào phần đóng tài nguyên. Nếu thư viện transport đã cung cấp `close()` idempotent, không cần bọc thêm chỉ để lặp lại chức năng đó.

### 5.3. Dừng tài nguyên theo thứ tự

Một target có thể sở hữu nhiều tài nguyên phụ thuộc nhau. Ví dụ một message consumer sử dụng executor và connection:

1. Ngừng nhận công việc mới.
2. Hủy đăng ký listener hoặc consumer.
3. Chờ công việc đang xử lý hoàn tất trong khoảng thời gian giới hạn.
4. Dừng executor.
5. Đóng connection hoặc client transport.
6. Xóa trạng thái nội bộ không còn cần thiết.

Thứ tự cụ thể phụ thuộc API. Nếu đóng connection trước khi consumer ngừng nhận message, ứng dụng có thể phát sinh lỗi hoặc mất khả năng xử lý graceful shutdown.

### 5.4. Callback phải có giới hạn thời gian

`refresh(String)` hoặc `refreshAll()` thực hiện việc hủy target và gọi destruction callback. Nếu callback chờ vô hạn một thread, đợi message không có deadline hoặc chờ connection trả về, thao tác refresh có thể bị treo.

Nên dùng:

- Timeout cho graceful shutdown.
- Giới hạn thời gian chờ executor.
- Chính sách cancel rõ ràng khi quá hạn.
- Log lỗi đóng tài nguyên có ngữ cảnh nhưng không chứa secret.
- Metrics cho thời gian shutdown và số lần callback thất bại.

Không nên bỏ qua exception trong callback mà không ghi nhận. Một tài nguyên không đóng được có thể dẫn tới rò rỉ connection, thread hoặc file descriptor.

## 6. Ví dụ đầy đủ: refresh một client có tài nguyên

Giả sử `PartnerClient` tạo một transport gắn với URL lấy từ cấu hình. Khi URL đổi, ứng dụng muốn đóng transport cũ và tạo transport mới.

### 6.1. Cấu hình

~~~yaml
partner:
  api:
    base-url: https://partner-v1.internal
    connect-timeout: 500ms
    read-timeout: 2s
~~~

### 6.2. Properties

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiProperties {

    private URI baseUrl;
    private Duration connectTimeout = Duration.ofMillis(500);
    private Duration readTimeout = Duration.ofSeconds(2);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

### 6.3. Bean refreshable

~~~java
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PartnerApiProperties.class)
class PartnerConfiguration {

    @Bean(destroyMethod = "close")
    @RefreshScope
    PartnerClient partnerClient(PartnerApiProperties properties) {
        return new PartnerClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout(),
                properties.getReadTimeout()
        );
    }
}
~~~

`PartnerClient` là target có vòng đời riêng. `destroyMethod = "close"` bảo đảm callback hủy được đăng ký cho target.

### 6.4. Target giữ và giải phóng transport

~~~java
public class PartnerClient implements AutoCloseable {

    private final PartnerTransport transport;

    public PartnerClient(
            URI baseUrl,
            Duration connectTimeout,
            Duration readTimeout
    ) {
        this.transport = PartnerTransport.open(
                baseUrl,
                connectTimeout,
                readTimeout
        );
    }

    public PartnerResponse send(PartnerRequest request) {
        return transport.send(request);
    }

    @Override
    public void close() {
        transport.close();
    }
}
~~~

`PartnerTransport` đại diện cho HTTP transport của ứng dụng. Trong dự án thật, nó có thể bọc HTTP client và connection manager cụ thể. `close()` phải đóng đúng tài nguyên mà target đã tạo.

### 6.5. Consumer giữ proxy

~~~java
import org.springframework.stereotype.Service;

@Service
public class OrderPartnerGateway {

    private final PartnerClient partnerClient;

    public OrderPartnerGateway(PartnerClient partnerClient) {
        this.partnerClient = partnerClient;
    }

    public PartnerResponse submit(PartnerRequest request) {
        return partnerClient.send(request);
    }
}
~~~

`OrderPartnerGateway` được tạo một lần và giữ reference tới scoped proxy. Sau refresh, gateway vẫn gọi cùng reference đó; proxy sẽ chuyển lời gọi tới target hiện tại của scope.

### 6.6. Điều gì xảy ra khi endpoint thay đổi?

~~~mermaid
sequenceDiagram
    participant Admin as Refresh trigger
    participant Env as Environment
    participant Scope as RefreshScope
    participant Proxy as PartnerClient proxy
    participant Old as Target v1
    participant New as Target v2
    Admin->>Env: Cập nhật base-url
    Admin->>Scope: refresh("partnerClient")
    Scope->>Old: Chạy destruction callback close()
    Scope-->>Admin: Cache entry đã bị loại
    Note over Proxy: Proxy vẫn được OrderPartnerGateway giữ
    OrderPartnerGateway->>Proxy: send(request)
    Proxy->>Scope: Lấy target hiện tại
    Scope->>New: Tạo target với base-url mới
    New-->>Proxy: Target đã khởi tạo
    Proxy->>New: send(request)
~~~

Sơ đồ mô tả một bean được refresh riêng. Với `refreshAll()`, mọi target thuộc refresh scope có trong cache sẽ được xử lý tương tự.

## 7. Refresh một bean hoặc toàn bộ scope

Spring Cloud cung cấp bean `RefreshScope` để điều khiển cache target.

### 7.1. `refresh(String beanName)`

Phương thức:

~~~java
boolean refreshed = refreshScope.refresh("partnerClient");
~~~

Tên truyền vào là bean name thông thường. `RefreshScope` xử lý việc ánh xạ sang scoped target name khi cần.

- `true`: target tương ứng đã có trong cache và được hủy khỏi scope.
- `false`: không có target đã cache với tên đó để hủy.

Giá trị `true` không có nghĩa target mới đã được tạo hoặc kết nối tới dependency thành công. Nó cho biết target hiện tại đã được loại khỏi cache.

### 7.2. `refreshAll()`

~~~java
refreshScope.refreshAll();
~~~

Phương thức này hủy các target hiện có trong toàn bộ refresh scope của context. Proxy vẫn tồn tại; target được tạo lại khi các proxy được sử dụng sau đó.

Chỉ dùng `refreshAll()` khi nhiều bean thật sự cần nhận cấu hình mới. Nếu chỉ một endpoint thay đổi, refresh bean cụ thể giúp giới hạn phạm vi ảnh hưởng và giảm chi phí khởi tạo lại.

### 7.3. Sự kiện `RefreshScopeRefreshedEvent`

Sau khi refresh một bean hoặc toàn bộ scope, Spring Cloud phát `RefreshScopeRefreshedEvent`. Listener có thể dùng sự kiện này để ghi nhận hoạt động, cập nhật metrics hoặc kích hoạt một tác vụ điều phối phù hợp.

Không xem sự kiện này là bằng chứng target mới đã được tạo thành công. Nó phản ánh hoạt động refresh scope; việc tạo target mới có thể xảy ra ở lần gọi proxy sau đó.

## 8. Kích hoạt refresh qua Actuator

Nếu ứng dụng có Spring Boot Actuator và Spring Cloud Context, chức năng refresh có thể được expose qua endpoint quản trị.

Ví dụ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
~~~

Endpoint refresh thường được gọi bằng HTTP `POST`:

~~~http
POST /actuator/refresh
~~~

Endpoint này kích hoạt quá trình refresh context: cập nhật Environment theo cơ chế của ứng dụng, rebind các bean cấu hình phù hợp và làm mới refresh scope.

Cần có dependency Actuator và các thành phần Spring Cloud phù hợp. Không expose endpoint chỉ bằng cách viết YAML nếu endpoint implementation không có trên classpath.

### 8.1. Bảo vệ endpoint

Endpoint refresh có thể thay đổi cấu hình runtime và khiến tài nguyên được tạo lại. Vì vậy:

- Chỉ expose trên management interface cần thiết.
- Bảo vệ bằng authentication và authorization.
- Giới hạn mạng truy cập.
- Không cho client công khai gọi refresh.
- Ghi audit về người gọi, thời điểm và kết quả.
- Không đưa nội dung secret hoặc toàn bộ cấu hình vào log.

Nếu dùng Spring Cloud Bus để phát refresh tới nhiều instance, cần kiểm soát quyền publish event và theo dõi kết quả trên từng instance. Refresh một instance không tự động refresh mọi replica.

## 9. Refresh target và giải phóng tài nguyên trong môi trường nhiều request

Trong production, target có thể đang phục vụ nhiều request khi một refresh được kích hoạt. Cần hiểu cơ chế proxy và thiết kế resource cleanup phù hợp.

### 9.1. Lời gọi đồng bộ qua scoped proxy

Spring Cloud sử dụng cơ chế scope và scoped proxy để phối hợp việc truy cập target với việc tạo/hủy target. Các phiên bản có cơ chế khóa theo bean để tránh việc destruction callback chạy đồng thời với một lời gọi phương thức đang được bảo vệ trên target có callback hủy.

Cơ chế này giúp bảo vệ vòng đời của lời gọi đồng bộ qua proxy trong phạm vi implementation tương ứng. Tuy nhiên, nó không thay thế mọi cơ chế drain hoặc shutdown của tài nguyên bên dưới.

### 9.2. Công việc bất đồng bộ có thể sống lâu hơn lời gọi

Ví dụ một phương thức target gửi công việc sang executor rồi trả về ngay:

~~~java
public CompletableFuture<Result> submitAsync(Request request) {
    return executor.submit(request);
}
~~~

Lời gọi qua proxy có thể kết thúc khi `CompletableFuture` vẫn đang chạy. Nếu callback hủy đóng executor hoặc connection mà công việc async còn sử dụng, công việc có thể thất bại.

Đối với tác vụ bất đồng bộ, cần một chính sách riêng:

1. Dừng nhận công việc mới.
2. Theo dõi số tác vụ đang chạy.
3. Chờ tác vụ hoàn tất trong giới hạn thời gian.
4. Hủy tác vụ còn lại theo chính sách.
5. Đóng tài nguyên khi không còn công việc phụ thuộc.

Có thể dùng lifecycle manager riêng cho executor hoặc thiết kế target để `close()` thực hiện graceful shutdown. Không dựa vào scoped proxy như một distributed lock hay một cơ chế quản lý mọi thread ngoài phạm vi method invocation.

### 9.3. Không giữ target bên ngoài proxy

Consumer nên inject proxy và gọi qua proxy. Tránh lấy target thật, lưu vào static field hoặc truyền target ra một component không được quản lý bởi Spring.

Nếu một consumer giữ reference trực tiếp đến target cũ, nó có thể tiếp tục gọi object đã bị hủy sau refresh. Điều này phá vỡ mục tiêu của scoped proxy.

### 9.4. Callback có thể làm chậm thao tác refresh

Nếu callback đóng connection pool cần thời gian chờ lớn, `refreshAll()` có thể mất nhiều thời gian. Đo thời gian hủy target và tránh callback có thao tác network không giới hạn.

Nếu tài nguyên yêu cầu shutdown kéo dài, cân nhắc cơ chế drain ngoài luồng được điều phối rõ ràng, nhưng vẫn phải bảo đảm target không bị dùng sau khi tài nguyên đã đóng.

## 10. Các trường hợp không tự động refresh

### 10.1. `@RefreshScope` trên `@Configuration` không lan xuống mọi `@Bean`

Ví dụ:

~~~java
@Configuration
@RefreshScope
class PartnerConfiguration {

    @Bean
    PartnerClient partnerClient(PartnerProperties properties) {
        return new PartnerClient(properties.getBaseUrl());
    }

    @Bean
    PartnerMetrics partnerMetrics() {
        return new PartnerMetrics();
    }
}
~~~

Đánh dấu lớp cấu hình không có nghĩa tất cả bean do các phương thức `@Bean` tạo ra đều nằm trong refresh scope.

Nếu `PartnerClient` cần được tạo lại, hãy đặt `@RefreshScope` trực tiếp trên bean method hoặc bean class tương ứng:

~~~java
@Bean(destroyMethod = "close")
@RefreshScope
PartnerClient partnerClient(PartnerProperties properties) {
    return new PartnerClient(properties.getBaseUrl());
}
~~~

Nếu bean khác phụ thuộc vào một bean được tạo từ cấu hình thay đổi, bean phụ thuộc cũng có thể cần refresh hoặc cần một thiết kế đọc cấu hình động khác.

### 10.2. Bean không được hỗ trợ refresh

Một số bean có thể bị loại khỏi cơ chế refresh do implementation hoặc lifecycle đặc biệt. Tài liệu Spring Cloud hiện hành nêu `HikariDataSource` là ví dụ mặc định trong `spring.cloud.refresh.never-refreshable`.

Không cố ép một connection pool vào refresh scope chỉ bằng annotation nếu implementation không hỗ trợ. Hãy xem danh sách `never-refreshable`, cách auto-configuration tạo bean và khả năng đóng pool an toàn. Nếu cần thay đổi datasource runtime, phải có thiết kế pool replacement và drain connection được kiểm chứng cho implementation đang dùng.

### 10.3. `extra-refreshable` và `never-refreshable`

Một số bean do auto-configuration tạo ra không thể trực tiếp gắn annotation trong mã ứng dụng. Spring Cloud có các thuộc tính:

| Thuộc tính | Vai trò |
| --- | --- |
| `spring.cloud.refresh.extra-refreshable` | Thêm bean name hoặc class name cần được đưa vào refresh scope |
| `spring.cloud.refresh.never-refreshable` | Khai báo bean name hoặc class name không được refresh/rebind |

Ví dụ cấu hình minh họa:

~~~yaml
spring:
  cloud:
    refresh:
      extra-refreshable:
        - com.example.PartnerTransport
      never-refreshable:
        - com.zaxxer.hikari.HikariDataSource
~~~

Các danh sách này phải được dùng theo đúng semantics của phiên bản Spring Cloud. Không thêm một class vào `extra-refreshable` chỉ để né lỗi lifecycle. Trước tiên phải xác nhận proxy có thể được tạo, bean có thể tái khởi tạo và tài nguyên cũ có callback đóng đúng.

### 10.4. `@ConfigurationProperties` và constructor binding

Spring Cloud có cơ chế rebind cho các bean `@ConfigurationProperties`. Rebind thường cập nhật object cấu hình theo cơ chế riêng; nó không đồng nghĩa thay target object của mọi bean đang giữ cấu hình.

Nếu cần một object có trạng thái nhất quán qua refresh, có thể cân nhắc đặt bean vào `@RefreshScope`. Các object dùng constructor binding, bao gồm Java record được bind theo constructor, có giới hạn refresh và không nên mặc định có thể rebind như bean mutable thông thường.

## 11. Vòng đời khi ApplicationContext đóng

Refresh scope cũng tham gia lifecycle shutdown của ứng dụng. Khi context đóng:

- Các target còn được cache và có destruction callback được hủy.
- Callback đóng tài nguyên được thực hiện theo lifecycle của Spring.
- Scoped proxy không cần consumer tự đóng target.
- Những tài nguyên dùng chung ở context khác phải do context sở hữu chúng đóng.

Với hierarchy có parent/child context, cần xác định bean thuộc context nào và context nào quản lý lifecycle của target. Không để child đóng một tài nguyên singleton mà parent hoặc sibling còn sử dụng.

Khi shutdown production, cần phối hợp với readiness/load balancer:

1. Đưa instance ra khỏi trạng thái nhận traffic mới.
2. Chờ request hiện tại hoàn tất theo grace period.
3. Đóng ApplicationContext.
4. Để Spring gọi callback hủy các target còn sống.
5. Xác nhận connection, executor và listener đã dừng.

Đóng context không thay thế quy trình drain traffic trước đó.

## 12. Kiểm thử destruction callback và target recreation

Kiểm thử nên chứng minh ba điều: target đầu tiên được tạo, callback hủy chạy khi refresh và target mới được tạo khi proxy được sử dụng lần tiếp theo.

### 12.1. Bean kiểm thử có bộ đếm lifecycle

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class LifecycleCounters {
    final AtomicInteger created = new AtomicInteger();
    final AtomicInteger destroyed = new AtomicInteger();
}

class RefreshableResource implements AutoCloseable {

    private final int id;
    private final LifecycleCounters counters;

    RefreshableResource(LifecycleCounters counters) {
        this.counters = counters;
        this.id = counters.created.incrementAndGet();
    }

    int id() {
        return id;
    }

    @Override
    public void close() {
        counters.destroyed.incrementAndGet();
    }
}
~~~

### 12.2. Đăng ký bean refreshable

~~~java
@TestConfiguration(proxyBeanMethods = false)
class RefreshLifecycleTestConfiguration {

    @Bean
    LifecycleCounters lifecycleCounters() {
        return new LifecycleCounters();
    }

    @Bean(destroyMethod = "close")
    @RefreshScope
    RefreshableResource refreshableResource(
            LifecycleCounters lifecycleCounters
    ) {
        return new RefreshableResource(lifecycleCounters);
    }
}
~~~

Spring Cloud Context cần có trong test runtime để đăng ký scope `refresh`. Test context cũng cần import cấu hình này.

### 12.3. Kiểm thử refresh từng bean

~~~java
@SpringBootTest
@Import(RefreshLifecycleTestConfiguration.class)
class RefreshLifecycleTest {

    @Autowired
    RefreshScope refreshScope;

    @Autowired
    RefreshableResource resource;

    @Autowired
    LifecycleCounters counters;

    @Test
    void destroysOldTargetAndCreatesNewTargetOnNextCall() {
        int firstId = resource.id();

        assertThat(counters.created.get()).isEqualTo(1);
        assertThat(counters.destroyed.get()).isEqualTo(0);

        assertThat(refreshScope.refresh("refreshableResource")).isTrue();

        assertThat(counters.destroyed.get()).isEqualTo(1);
        assertThat(counters.created.get()).isEqualTo(1);

        int secondId = resource.id();

        assertThat(secondId).isNotEqualTo(firstId);
        assertThat(counters.created.get()).isEqualTo(2);
        assertThat(counters.destroyed.get()).isEqualTo(1);
    }
}
~~~

Điểm quan trọng trong test:

- Lần gọi `resource.id()` đầu tiên làm proxy lấy target.
- `refresh("refreshableResource")` hủy target cũ và chạy `close()`.
- Bộ đếm `created` chưa tăng ngay sau refresh vì target mới chưa được yêu cầu.
- Lần gọi `resource.id()` kế tiếp làm scope tạo target mới.
- ID khác nhau chứng minh proxy đã chuyển sang target mới.

Đây là ví dụ test minh họa; dự án cần thêm import JUnit, AssertJ, Spring Boot Test và cấu hình context tương thích với release train đang dùng.

### 12.4. Kiểm thử refreshAll

Có thể mở rộng test để tạo hai bean trong refresh scope, gọi `refreshAll()` và xác nhận callback của cả hai target đã được gọi. Sau đó gọi qua từng proxy và xác nhận mỗi bean được tạo lại khi cần.

### 12.5. Kiểm thử lỗi khi đóng tài nguyên

Nên có test cho:

- Callback đóng được gọi đúng một lần cho target đã khởi tạo.
- Target chưa được khởi tạo không có tài nguyên cần đóng.
- `close()` xử lý an toàn khi tài nguyên đã đóng.
- Lỗi đóng một tài nguyên được log/ghi nhận.
- Target mới không được tạo nếu consumer chưa truy cập proxy.
- Nếu target mới không thể khởi tạo, lỗi xuất hiện ở lần gọi proxy và được quan sát qua health/log.

Không chỉ kiểm tra `refreshScope.refresh(...)` trả về `true`; phải kiểm tra callback và lần tạo target mới.

## 13. Quan sát và vận hành refresh scope

Trong production, nên theo dõi:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Số lần refresh theo bean | Biết bean nào thường xuyên bị làm mới |
| Thời gian destruction callback | Phát hiện callback đóng tài nguyên chậm |
| Số target tạo mới | Phát hiện target được tạo lại nhiều lần |
| Lỗi khởi tạo target | Biết cấu hình mới có tạo được client/pool hay không |
| Lỗi đóng resource | Phát hiện connection/thread/file handle không giải phóng |
| Health của refresh scope | Quan sát lỗi liên quan rebind hoặc reinitialize nếu health indicator được bật |
| Readiness và request error rate | Phát hiện ảnh hưởng lên lưu lượng khi refresh |

Spring Cloud có `RefreshScopeHealthIndicator` trong các phiên bản hiện hành để theo dõi một số lỗi refresh/rebind. Có thể cấu hình tắt health indicator nếu cần:

~~~yaml
management:
  health:
    refresh:
      enabled: false
~~~

Chỉ tắt khi đã có cơ chế quan sát thay thế. Khi refresh bean quan trọng, nên kiểm tra readiness hoặc thực hiện probe sau khi target mới được khởi tạo.

### 13.1. Event không thay thế metrics

`RefreshScopeRefreshedEvent` hữu ích để ghi nhận hoạt động refresh. Tuy nhiên, một event không cho biết đầy đủ thời gian close, số kết nối đã giải phóng hoặc chất lượng target mới. Nên bổ sung metrics và log có cấu trúc quanh quá trình tạo/hủy target.

### 13.2. Phân biệt refresh thành công và ứng dụng sẵn sàng

Một refresh có thể đã xóa cache và chạy destruction callback, nhưng target mới chưa được khởi tạo. Nếu target mới cần kết nối remote service và endpoint mới không hợp lệ, request tiếp theo có thể thất bại.

Với bean trọng yếu, quy trình vận hành nên có bước xác minh sau refresh: gọi một thao tác kiểm tra, kiểm tra health hoặc quan sát lỗi khởi tạo target mới trước khi kết luận instance đã nhận cấu hình thành công.

## 14. Giới hạn theo môi trường và phiên bản

- Refresh scope thuộc Spring Cloud Context; cần dependency và auto-configuration phù hợp.
- `spring.cloud.refresh.enabled=false` tắt auto-configuration refresh scope và các tính năng liên quan.
- Context refresh không được hỗ trợ cho Spring AOT transformations và native images trong tài liệu hiện hành; với AOT/native, cần đặt `spring.cloud.refresh.enabled=false`.
- Một số loại bean như HikariDataSource nằm trong danh sách mặc định không refresh.
- `@RefreshScope` trên lớp `@Configuration` không tự đưa tất cả bean được khai báo trong lớp vào scope.
- Các API, danh sách bean không refresh và hành vi auto-configuration cần đối chiếu release train Spring Cloud tương thích với Spring Boot.
- Không giả định refresh ở một instance sẽ phát tán đến toàn bộ replica; cần Spring Cloud Bus hoặc cơ chế điều phối tương ứng.

Khi nâng cấp Spring Boot hoặc Spring Cloud, kiểm tra lại proxy strategy, callback destruction, các thuộc tính `spring.cloud.refresh.*` và cách Actuator expose endpoint.

## 15. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Target cũ không giải phóng connection | Không đăng ký destruction callback hoặc target không sở hữu rõ tài nguyên | Dùng `@PreDestroy` hoặc `@Bean(destroyMethod = "close")`; kiểm tra ownership |
| Refresh xong nhưng target mới chưa xuất hiện | Chưa có lời gọi qua proxy sau khi cache bị xóa | Gọi probe/health check để kích hoạt và xác minh target |
| Consumer vẫn dùng cấu hình cũ | Consumer giữ target trực tiếp thay vì proxy hoặc bean phụ thuộc không refresh | Inject scoped proxy và xem lại dependency graph |
| `close()` không được gọi | Bean không có callback được đăng ký hoặc implementation bị loại khỏi refresh | Kiểm tra bean definition, scope và `never-refreshable` |
| Refresh làm gián đoạn tác vụ async | Tác vụ sống lâu hơn method call và vẫn dùng resource cũ | Dừng nhận tác vụ, drain và đóng resource theo lifecycle riêng |
| `@RefreshScope` trên config class không refresh bean mong muốn | Annotation không lan sang mọi `@Bean` method | Đánh dấu trực tiếp từng bean cần refresh |
| HikariDataSource không được làm mới | Nằm trong `spring.cloud.refresh.never-refreshable` mặc định | Thiết kế chiến lược datasource/pool khác và kiểm thử kỹ |
| `refresh(name)` trả về false | Không có target đã cache dưới bean name đó | Xác minh bean name và target đã từng được khởi tạo |
| Endpoint refresh không tồn tại | Thiếu Actuator/Context hoặc endpoint chưa được expose | Kiểm tra dependency và management exposure |
| Refresh xong request mới lỗi | Target mới khởi tạo thất bại hoặc cấu hình mới không hợp lệ | Kiểm tra exception, property source và health sau lần truy cập |
| Shutdown treo | Callback đóng tài nguyên chờ vô hạn | Đặt timeout và graceful shutdown có giới hạn |

## 16. Checklist thiết kế trước khi đưa bean vào Refresh Scope

Trước khi gắn `@RefreshScope`, hãy trả lời:

- Bean có thực sự giữ trạng thái hoặc tài nguyên phụ thuộc cấu hình cần thay đổi không?
- Consumer có inject qua scoped proxy không?
- Tài nguyên nào do target sở hữu và cần đóng?
- Destruction callback đã được đăng ký chưa?
- `close()` có idempotent và có timeout không?
- Tác vụ async có thể tiếp tục dùng resource sau khi method trả về không?
- Có dependency nào bên ngoài scope vẫn giữ cấu hình cũ không?
- Bean có nằm trong danh sách `never-refreshable` không?
- Có cần dùng `extra-refreshable` cho bean do auto-configuration tạo không?
- Cấu hình mới có thể tạo target mới thành công không?
- Đã có test xác nhận callback hủy và target recreation chưa?
- Refresh có được bảo vệ và quan sát trong production không?

Nếu không có tài nguyên hoặc trạng thái cần tạo lại, có thể `@RefreshScope` không phải giải pháp phù hợp. Hãy dùng cơ chế cấu hình có kiểu/rebind hoặc thiết kế một client đọc cấu hình động nếu yêu cầu đơn giản hơn.

## 17. Bài tập vận dụng

**Bài tập 1 — Vẽ lifecycle.** Vẽ trình tự từ lúc consumer gọi proxy, target được tạo, cấu hình thay đổi, refresh được gọi, destruction callback chạy và target mới được tạo.

**Bài tập 2 — Đóng tài nguyên.** Tạo một bean refreshable sở hữu `ExecutorService`. Viết callback dừng nhận tác vụ, chờ hoàn tất trong thời hạn và đóng executor. Kiểm thử số lần shutdown.

**Bài tập 3 — Callback của bean method.** Tạo `@Bean(destroyMethod = "close") @RefreshScope`. Gọi `refresh(beanName)` và chứng minh `close()` được gọi trước khi target mới được tạo.

**Bài tập 4 — Proxy và target.** Inject bean refreshable vào một singleton consumer. Gọi qua consumer trước và sau refresh; chứng minh consumer giữ cùng proxy nhưng target ID thay đổi.

**Bài tập 5 — Async work.** Tạo phương thức target gửi task vào executor rồi trả về. Refresh trong lúc task chạy; quan sát rủi ro và thiết kế graceful drain.

**Bài tập 6 — Bean bị loại trừ.** Kiểm tra hành vi của một HikariDataSource trong cấu hình refresh. Đọc `spring.cloud.refresh.never-refreshable` và đề xuất chiến lược cập nhật datasource an toàn.

**Bài tập 7 — Endpoint vận hành.** Expose `/actuator/refresh` trong môi trường local, gọi bằng HTTP POST, sau đó kiểm tra callback và health. Thiết kế authentication/authorization trước khi đưa endpoint vào môi trường thật.

**Bài tập 8 — Refresh toàn scope.** Tạo hai bean refreshable có tài nguyên riêng, gọi `refreshAll()` và đo thời gian hủy. Kiểm tra target mới chỉ được tạo khi từng proxy được gọi lại.

## 18. Ghi nhớ và nguồn tra cứu

- `@RefreshScope` đặt bean trong scope `refresh` và cung cấp scoped proxy cho consumer.
- Target được cache; refresh loại target khỏi cache và chạy destruction callback đã đăng ký.
- Proxy tiếp tục tồn tại. Target mới được tạo từ bean definition khi proxy được truy cập sau refresh.
- Dùng `@PreDestroy`, `DisposableBean` hoặc `@Bean(destroyMethod = "...")` để giải phóng tài nguyên.
- Target chỉ nên đóng tài nguyên do chính nó sở hữu; tài nguyên dùng chung phải do component sở hữu chúng quản lý.
- `refresh(String)` làm mới một bean; `refreshAll()` làm mới toàn bộ target trong scope.
- Refresh cache thành công chưa chứng minh target mới đã được tạo hoặc kết nối thành công.
- Tác vụ async, connection pool và resource có shutdown dài cần chính sách drain/timeout riêng.
- HikariDataSource là ví dụ mặc định không refreshable; AOT/native image không hỗ trợ Context Refresh trong tài liệu hiện hành.
- Khi vận hành, theo dõi cả thời gian hủy, lỗi callback, lỗi tạo target mới và readiness sau refresh.

Nguồn chính thức để đối chiếu theo phiên bản Spring Cloud/Spring Boot của dự án:

1. [Spring Cloud Context – Refresh Scope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Javadoc – `RefreshScope`](https://docs.spring.io/spring-cloud-commons/docs/current/apidocs/org/springframework/cloud/context/scope/refresh/RefreshScope.html)
3. [Spring Cloud Javadoc – `GenericScope`](https://docs.spring.io/spring-cloud-commons/docs/current/apidocs/org/springframework/cloud/context/scope/GenericScope.html)
4. [Spring Framework Reference – Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
5. [Spring Boot Reference – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
6. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
