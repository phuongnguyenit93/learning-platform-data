# Đóng tài nguyên đúng vòng đời Spring ApplicationContext

## 1. Vấn đề: ứng dụng chạy đúng nhưng dừng sai

Trong **Spring Data Couchbase**, một ứng dụng có thể khởi động thành công, dùng `CouchbaseRepository` và `CouchbaseTemplate` ổn định, nhưng vẫn gặp lỗi khi dừng hoặc triển khai phiên bản mới. Một số tình huống điển hình:

- Một service gọi `cluster.disconnect()` sau mỗi request, khiến các repository khác mất kết nối.
- Ứng dụng tạo `ClusterEnvironment` thủ công nhưng không gọi `shutdown()` khi dừng.
- Một tác vụ nền hoặc reactive pipeline vẫn ghi vào Couchbase sau khi `ApplicationContext` đã bắt đầu đóng.
- Dự án vừa để Spring Boot tạo SDK client, vừa đăng ký client riêng, làm khó xác định tài nguyên nào phải được đóng.
- Trong rolling deployment, pod dừng đột ngột trước khi xử lý hết thao tác ghi đang chạy.

Chủ đề của bài học trong chương **Cấu hình kết nối** là **đóng tài nguyên đúng vòng đời Spring `ApplicationContext`**. Đây là điều kiện để xây dựng tầng truy cập Couchbase có hiệu năng, nhất quán và khả năng vận hành, từ document mapping và repository đến SQL++, TTL, CAS, giao dịch và reactive API.

**Sau bài học**, bạn sẽ:

1. Phân biệt chủ sở hữu của `ClusterEnvironment`, `Cluster`, các handle `Bucket/Scope/Collection` và bean Spring Data.
2. Biết khi nào container tự hủy bean và khi nào ứng dụng phải khai báo rõ `destroyMethod`.
3. Thiết kế thứ tự đóng tài nguyên theo quan hệ phụ thuộc.
4. Tránh đóng sớm SDK client dùng chung từ controller/service/repository.
5. Phối hợp graceful shutdown với công việc đồng bộ, reactive và tác vụ nền.
6. Kiểm chứng cleanup bằng test nhỏ, log và quy trình rollout.

Các ví dụ minh họa cho **Spring Boot 3.x**, Spring Data Couchbase tương ứng và Couchbase Java SDK 3.x. Hành vi hủy bean, method trả về hoặc tên API có thể tùy phiên bản; cần xác nhận bằng dependency/version thực tế trước khi áp dụng vào production.

## 2. Phân biệt tài nguyên sở hữu và handle sử dụng

Sơ đồ sau là quan hệ phụ thuộc của một ứng dụng điển hình:

~~~mermaid
flowchart TD
    C["Spring ApplicationContext"] --> E["ClusterEnvironment"]
    C --> CL["Cluster"]
    E --> CL
    CL --> B["Bucket handle"]
    B --> S["Scope handle"]
    S --> K["Collection handle"]
    CL --> F["CouchbaseClientFactory"]
    B --> F
    F --> T["CouchbaseTemplate / Converter"]
    T --> R["CouchbaseRepository"]
    R --> SV["Service singleton"]
    SV --> REQ["Các request và tác vụ nền"]
~~~

**Mối liên hệ trên không có nghĩa mọi đối tượng đều là một kết nối riêng cần `close()`.**

| Thành phần | Thuộc thư viện | Vai trò | Chính sách đóng |
| --- | --- | --- | --- |
| `ClusterEnvironment` | Couchbase Java SDK | Môi trường cấu hình và tài nguyên nền SDK | Nếu tự tạo, phải `shutdown()` sau khi các cluster dùng nó ngừng hoạt động; nếu Spring sở hữu, để container đóng |
| `Cluster` | Couchbase Java SDK | Client đại diện cho một cluster | Nếu tự tạo, `disconnect()` khi không còn thao tác; nếu Spring sở hữu, không đóng trong service |
| `Bucket` | Couchbase Java SDK | Handle trỏ tới bucket | Không tự đóng như một client độc lập |
| `Scope` | Couchbase Java SDK | Handle trỏ tới scope | Theo client phía dưới |
| `Collection` | Couchbase Java SDK | Handle KV trong một collection | Theo client phía dưới |
| `CouchbaseClientFactory` | Spring Data Couchbase | Cấp các đối tượng SDK cho tầng Spring Data | Thuộc hạ tầng application context; không hủy từ request |
| `CouchbaseTemplate` và repository proxy | Spring Data Couchbase | Mapping và truy cập document/query | Bean dùng chung; không là chủ sở hữu độc lập của SDK client |
| `ProductDocument`, `JsonObject`, `GetResult` | Entity hoặc dữ liệu thao tác | Payload và kết quả từng request | Không phải tài nguyên mạng cần `disconnect()` |

Tùy hình thức tạo bean, **Spring Boot** có thể quản lý SDK environment và cluster, hoặc dự án phải tự định nghĩa. Quy tắc nền tảng:

> Tài nguyên được tạo ở tầng nào thì **tầng sở hữu** phải bảo đảm đóng nó khi không còn người dùng. Một đối tượng nhận tài nguyên qua dependency injection không được mặc nhiên tự nhận quyền hủy tài nguyên đó.

## 3. Vì sao SDK client nên có vòng đời dài?

Couchbase Java SDK quản lý kết nối, topology, I/O, retry và những tài nguyên nội bộ. Tạo rồi đóng một `Cluster` cho mỗi HTTP request phát sinh chi phí không cần thiết, đồng thời dễ gây lỗi khi một thao tác khác còn chạy.

**Anti-pattern**:

~~~java
// Ví dụ không nên làm trong controller/service HTTP.
public String loadSku(String id) {
    Cluster temporary = Cluster.connect(
            connectionString, username, password
    );
    try {
        return temporary.bucket("inventory")
                .scope("catalog")
                .collection("products")
                .get(id)
                .contentAsObject()
                .getString("sku");
    } finally {
        temporary.disconnect();
    }
}
~~~

Đoạn code có `finally` nhưng **sai phạm vi sử dụng lại**: nó liên tục bootstrap và dọn dẹp client. Thay vào đó, controller/service nên inject repository, template hoặc SDK handle do container quản lý.

**Mô hình phù hợp**:

~~~java
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Optional<ProductDocument> getById(String id) {
        return products.findById(id);
    }
}
~~~

`ProductRepository` là interface kế thừa `CouchbaseRepository<ProductDocument, String>`; entity được ánh xạ đến bucket/scope/collection qua cấu hình và mapping. Tầng nghiệp vụ không tạo `Cluster.connect()` và không đóng `Cluster` sau `findById()`.

## 4. Spring `ApplicationContext` quản lý vòng đời bean thế nào?

`ApplicationContext` khởi tạo, liên kết và quản lý các bean. Khi một context đóng bình thường, Spring kích hoạt quy trình shutdown để các bean có cơ hội giải phóng tài nguyên.

Các điểm mở rộng phổ biến:

| Cơ chế | Vai trò | Dùng khi |
| --- | --- | --- |
| `@Bean(destroyMethod = "...")` | Chỉ định phương thức hủy của bean do factory method tạo | SDK `disconnect()`, `shutdown()` hoặc API cleanup riêng |
| Suy luận destroy method của `@Bean` | Spring có thể phát hiện các phương thức hủy thông dụng theo quy tắc framework | Khi đối tượng có phương thức phù hợp; cần xác nhận behavior |
| `@PreDestroy` | Callback khi bean chuẩn bị bị hủy | Cleanup nội bộ của chính bean |
| `DisposableBean.destroy()` | Callback Spring-specific khi bean bị hủy | Cần triển khai hợp đồng Spring rõ ràng |
| `SmartLifecycle` | Start/stop theo pha, hỗ trợ dừng có điều phối | Worker, consumer hoặc tác vụ lâu sống |
| `ContextClosedEvent` | Sự kiện phát ra trong quá trình context đóng | Phối hợp logic dừng; không thay thế cleanup được framework quản lý |

**Quan trọng:** không phải callback nào cũng chạy trong mọi loại sự cố. Nếu tiến trình bị `SIGKILL`, máy tắt nguồn, JVM crash hoặc container bị cưỡng bức kill, ứng dụng **không được bảo đảm** có cơ hội chạy shutdown hooks/`@PreDestroy`. Vì vậy thiết kế ghi dữ liệu vẫn phải xử lý retry, idempotency, CAS và giao dịch phù hợp.

### 4.1. Ai thực sự sở hữu bean?

Một trường hợp cần phân biệt:

- **Bean do Spring tạo và quản lý**: container biết quan hệ phụ thuộc và gọi destroy callbacks khi context dừng.
- **Đối tượng được tạo bằng `new` trong code nghiệp vụ**: Spring không tự biết để đóng, trừ khi bạn chuyển quyền sở hữu vào một bean quản lý có thiết kế rõ.
- **Client được chia sẻ từ thư viện hoặc context khác**: không được đóng nếu nó còn người dùng ngoài context hiện tại.

Không nên coi “đã inject được `Cluster`” là bằng chứng service đó được phép gọi `disconnect()`. Dependency injection cấp khả năng **sử dụng**, không cấp quyền **sở hữu**.

## 5. Cách ưu tiên: để Spring Boot quản lý SDK và Spring Data

Trong ứng dụng Spring Boot thông thường, chỉ cần starter và properties tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-couchbase</artifactId>
</dependency>
~~~

~~~yaml
spring:
  couchbase:
    connection-string: "${COUCHBASE_CONNECTION_STRING:couchbase://127.0.0.1}"
    username: "${COUCHBASE_USERNAME}"
    password: "${COUCHBASE_PASSWORD}"
  data:
    couchbase:
      bucket-name: "${COUCHBASE_BUCKET:inventory}"
~~~

Với classpath và điều kiện auto-configuration phù hợp, Spring Boot cấu hình các bean liên quan tới Couchbase SDK và Spring Data. Service sử dụng repository/template; cơ chế quản lý bean chịu trách nhiệm dọn dẹp hạ tầng khi `ApplicationContext` đóng.

**Không bổ sung một `@PreDestroy` trong service chỉ để gọi `cluster.disconnect()`**. Việc đó có thể đóng client khi repository, event listener hoặc bean khác vẫn đang được Spring xử lý.

Ví dụ service **không nên**:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class WrongCouchbaseCleanup {

    private final Cluster sharedCluster;

    public WrongCouchbaseCleanup(Cluster sharedCluster) {
        this.sharedCluster = sharedCluster;
    }

    @PreDestroy
    public void closeSharedCluster() {
        // SAI: service không sở hữu cluster bean dùng chung.
        sharedCluster.disconnect();
    }
}
~~~

Nếu Spring Boot đã đăng ký bean với cleanup thích hợp, callback của service này vừa thừa vừa có thể làm thứ tự shutdown khó đoán.

### 5.1. Đừng đăng ký lại client chỉ để truy cập SDK trực tiếp

Nếu một service cần thao tác JSON/KV SDK thấp hơn repository, có thể inject `CouchbaseClientFactory`:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import org.springframework.data.couchbase.core.CouchbaseClientFactory;
import org.springframework.stereotype.Service;

@Service
public class RawProductReader {

    private final Collection products;

    public RawProductReader(CouchbaseClientFactory factory) {
        this.products = factory.getBucket()
                .scope("catalog")
                .collection("products");
    }

    public JsonObject getRaw(String id) {
        return products.get(id).contentAsObject();
    }
}
~~~

Ứng dụng đang **tái sử dụng client do Spring Data dùng**. Không cần gọi `Cluster.connect()` thêm hoặc tự đóng factory/cluster trong `getRaw()`. Việc dùng SDK trực tiếp ở đây không tự động áp dụng converter và `@Version` của entity Spring Data.

## 6. Khi tự đăng ký bean SDK: chỉ định destroy method rõ ràng

Có những ứng dụng SDK độc lập tích hợp vào Spring mà **cố ý tự tạo** environment và cluster. Trong trường hợp đó, có thể khai báo hai bean tương ứng để Spring sở hữu cả hai.

Ví dụ **minh họa một cấu hình SDK do Spring quản lý**:

~~~java
package com.example.inventory.config;

import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.env.ClusterEnvironment;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ManagedSdkConfiguration {

    @Bean(destroyMethod = "shutdown")
    public ClusterEnvironment sdkEnvironment() {
        return ClusterEnvironment.builder().build();
    }

    @Bean(destroyMethod = "disconnect")
    public Cluster sdkCluster(
            ClusterEnvironment sdkEnvironment,
            @Value("${app.cb.endpoint}") String endpoint,
            @Value("${app.cb.username}") String username,
            @Value("${app.cb.password}") String password) {

        return Cluster.connect(
                endpoint,
                ClusterOptions.clusterOptions(username, password)
                        .environment(sdkEnvironment)
        );
    }
}
~~~

Các property `app.cb.*` trong ví dụ là **property do ứng dụng tự định nghĩa**, cần cấp từ cấu hình/secrets thích hợp. Chúng không thay thế `spring.couchbase.*` nếu ứng dụng đang dùng auto-configuration của Boot.

Điểm cốt lõi:

1. `sdkEnvironment` do Spring tạo nên Spring sẽ gọi `shutdown()` khi hủy bean.
2. `sdkCluster` phụ thuộc vào `sdkEnvironment` thông qua tham số factory method.
3. Spring biết quan hệ phụ thuộc và có cơ sở hủy bean sử dụng trước bean cung cấp tài nguyên.
4. `destroyMethod` thể hiện rõ ý định; không phụ thuộc vào suy luận mặc định của framework.
5. Không gọi `disconnect()` trong service trước khi đóng context.

**Lưu ý xung đột:** trong ứng dụng đã có starter Couchbase và auto-configuration, đăng ký một `Cluster`/`ClusterEnvironment` khác có thể khiến auto-configuration lùi bước hoặc hạ tầng Spring Data sử dụng bean không như dự kiến. Chỉ thêm cấu hình trên khi thiết kế lại ownership/wiring một cách chủ đích; nếu chỉ cần thay timeout/TLS, ưu tiên Boot properties hoặc customizer được hỗ trợ.

### 6.1. Chỉ rõ quan hệ phụ thuộc, không giả định thứ tự ngẫu nhiên

Với phương thức `sdkCluster(ClusterEnvironment sdkEnvironment, ...)`, Spring biết cluster phụ thuộc environment. Khi context được đóng theo lifecycle bình thường, bean phụ thuộc được dọn trước bean mà nó sử dụng.

Không dựa vào:

- Thứ tự khai báo hai `@Bean` trong file Java.
- Tên bean xếp theo alphabet.
- Thứ tự service nhận được callback `@PreDestroy`.
- Thời gian request kết thúc “thường là ngắn”.

Nếu không thể thể hiện dependency qua constructor hoặc tham số bean method, phải thiết kế quan hệ phụ thuộc rõ theo cơ chế Spring hỗ trợ. `@DependsOn` có thể giúp biểu thị phụ thuộc trong tình huống thích hợp, nhưng không thay thế thiết kế constructor injection khi có thể dùng.

## 7. `@PreDestroy` nên dùng cho tài nguyên nào?

`@PreDestroy` phù hợp khi bean **thật sự sở hữu** một tài nguyên không được Spring tự quản lý độc lập, chẳng hạn subscription/timer do chính bean đó tạo.

Ví dụ về một publisher/consumer nền tự quản lý Reactor subscription:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;
import reactor.core.Disposable;

@Component
public class InventorySyncWorker {

    private Disposable runningSubscription;

    public void register(Disposable subscription) {
        this.runningSubscription = subscription;
    }

    @PreDestroy
    public void stopOwnedSubscription() {
        Disposable subscription = runningSubscription;
        if (subscription != null && !subscription.isDisposed()) {
            subscription.dispose();
        }
    }
}
~~~

Đây là ví dụ **về quyền sở hữu subscription**, không phải một triển khai worker hoàn chỉnh. Nếu nhiều luồng cùng đăng ký/dừng subscription, cần cơ chế đồng bộ phù hợp; production nên dùng lifecycle điều phối rõ hơn thay vì ghi đè field `runningSubscription` tùy tiện.

Trong ví dụ, worker dừng tài nguyên nó sở hữu nhưng **không gọi `Cluster.disconnect()`**. Spring sẽ tiếp tục điều phối hủy những bean SDK theo quan hệ phụ thuộc.

**Cần phân biệt:**

- Subscription cancellation báo hiệu dừng nhận kết quả/công việc theo ngữ nghĩa Reactor.
- Cancellation **không bảo đảm** một lệnh ghi Couchbase đã gửi sẽ bị rollback hay chưa được server xử lý.
- Với công việc dài, phải thiết kế quiesce/drain, timeout và trạng thái nghiệp vụ, không chỉ dispose rồi coi như đã hoàn thành.

## 8. `SmartLifecycle`: khi việc dừng cần một trình tự

Một số ứng dụng có consumer, scheduler, queue worker hoặc luồng đồng bộ dữ liệu chạy lâu hơn một HTTP request. Các bean đó cần **ngừng nhận công việc mới** trước khi client Couchbase bị đóng.

Spring cung cấp `SmartLifecycle` để các thành phần có thể tham gia lifecycle start/stop có điều phối theo pha.

Ví dụ tối giản:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class ImportConsumerLifecycle implements SmartLifecycle {

    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        running.set(true);
        // Bắt đầu nhận công việc khi các dependency đã sẵn sàng.
    }

    @Override
    public void stop() {
        running.set(false);
        // Ngừng lấy công việc mới và điều phối drain nếu cần.
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Bean trên chỉ mô tả **điểm móc vòng đời**, chưa triển khai message broker hoặc draining. Những công việc thực tế có thể cần `stop(Runnable callback)` để thông báo dừng bất đồng bộ theo hợp đồng `SmartLifecycle`.

### 8.1. Hiểu `phase` trước khi đặt số

Với các `SmartLifecycle` bean:

- **Khởi động:** các bean ở pha thấp hơn thường được start trước.
- **Dừng:** các bean ở pha cao hơn thường được stop trước.

Đây là lý do một worker nhận việc mới có thể được dừng trước các thành phần hạ tầng mà nó phụ thuộc, nếu mọi thành phần liên quan tham gia lifecycle đúng cách.

Tuy nhiên, **`Cluster` và `ClusterEnvironment` không tự động là `SmartLifecycle` bean** chỉ vì chúng là SDK objects. Không giả định rằng `getPhase() = 100` sẽ điều khiển trực tiếp thời điểm Spring gọi `destroyMethod = "disconnect"` của cluster. Bạn phải phân biệt pha stop của lifecycle với giai đoạn destroy singleton beans diễn ra sau đó.

Nếu cần dừng producer/consumer bất đồng bộ và chờ in-flight jobs hoàn tất, hãy dùng cơ chế điều phối/phạm vi chờ rõ ràng, được kiểm chứng bằng test.

## 9. Graceful shutdown từ HTTP server tới Couchbase

Một rolling deployment tốt cần hạn chế nhận request mới và xử lý request còn chạy trước khi đóng backend client.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant H as HTTP Server
    participant S as Spring Service
    participant DB as Couchbase SDK
    O->>H: Yêu cầu dừng instance
    H->>H: Ngừng nhận request mới
    Note over H,S: Dành ngân sách cho request đang chạy
    S->>DB: Kết thúc thao tác KV/SQL++
    DB-->>S: Response hoặc lỗi có xử lý
    S-->>H: Hoàn tất HTTP response
    H->>O: Server đã dừng nhận việc
    Note over S,DB: Container bắt đầu destroy beans
    S->>DB: Không tạo yêu cầu mới
    DB->>DB: disconnect / environment shutdown
~~~

Trong Spring Boot có thể bật graceful shutdown và đặt time budget cho các lifecycle phase theo phiên bản:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Ngưỡng `30s` minh họa; phải cân đối với thời hạn termination của orchestrator, độ dài request, transaction và khả năng drain. Spring Boot phiên bản và HTTP server được dùng sẽ quyết định chi tiết cách graceful shutdown thực thi.

**Điểm giới hạn quan trọng:** graceful shutdown của HTTP server **không tự bảo đảm** mọi scheduler, task nền, `CompletableFuture` hoặc subscription reactive tự dừng và hoàn tất. Các thành phần đó cần lifecycle riêng.

### 9.1. Shutdown có deadline

Không thể luôn chờ vô hạn một SQL++ query, durable mutation hoặc transaction. Cần có ngân sách cho:

1. Dừng tiếp nhận công việc mới.
2. Cho in-flight công việc thời gian hoàn tất.
3. Xử lý những công việc quá hạn theo hợp đồng nghiệp vụ.
4. Đóng các tài nguyên SDK khi không còn công việc được phép sử dụng.

Nếu orchestrator cưỡng bức dừng tiến trình, các callback còn lại có thể không chạy. Vì vậy mọi nghiệp vụ quan trọng phải có cơ chế khôi phục sau restart, không trông chờ `@PreDestroy` như một transaction commit.

## 10. Tác vụ reactive và subscription kéo dài qua request

API reactive vẫn dựa trên `ClusterEnvironment` và `Cluster`. Một `Mono`/`Flux` đại diện pipeline thao tác, trong khi client là tài nguyên dùng chung.

Ví dụ một service reactive có API trả về pipeline:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductService {

    private final ReactiveProductRepository repository;

    public ReactiveProductService(ReactiveProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductDocument> get(String id) {
        return repository.findById(id);
    }
}
~~~

Service này **không tự subscribe** và không đóng cluster; controller/subscriber quản lý việc tiêu thụ luồng theo ứng dụng.

### 10.1. Phân biệt pipeline của request với luồng nền

- **Pipeline request-scoped:** framework và subscriber có thể ngừng tiêu thụ khi HTTP request bị hủy, nhưng một lệnh ghi đã gửi có thể vẫn được server thực hiện.
- **Subscription nền do ứng dụng tạo:** ứng dụng sở hữu subscription đó, cần cơ chế dừng và theo dõi tiến độ.
- **Công việc transaction/reactive đang thực hiện:** cần quản lý commit/rollback và deadline theo hợp đồng transaction, không giả định dispose sẽ hủy mọi side effect.

Không gọi `block()` trên event-loop WebFlux chỉ để bảo đảm “đã chờ xong” khi shutdown. Hãy dùng cơ chế điều phối bất đồng bộ phù hợp và ngân sách thời gian rõ.

### 10.2. Retry có thể gây công việc phát sinh trong lúc shutdown

Một pipeline có `retryWhen` hoặc một scheduler tự động retry sẽ có nguy cơ phát sinh request mới ngay khi ứng dụng đang dừng. Khi shutdown bắt đầu, cần có dấu hiệu quiesce hoặc cơ chế tạm ngừng nhận/schedule công việc mới.

Đối với mutation, một `AmbiguousTimeoutException` hoặc hủy subscription **không chứng minh** document chưa được ghi. Các thao tác như tăng tồn kho, tạo đơn hàng và trừ tiền cần idempotency key, CAS, `@Version` hoặc đối soát theo nghiệp vụ; không retry mù chỉ vì phía client không nhận được kết quả trước shutdown.

## 11. Tự quản lý SDK ngoài Spring: ownership vẫn phải rõ

Một chương trình console hoặc service thuần Couchbase Java SDK có thể không cần `ApplicationContext`. Khi tự tạo tài nguyên:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.ClusterOptions;
import com.couchbase.client.java.env.ClusterEnvironment;

ClusterEnvironment environment = ClusterEnvironment.builder().build();
Cluster cluster = null;

try {
    cluster = Cluster.connect(
            connectionString,
            ClusterOptions.clusterOptions(username, password)
                    .environment(environment)
    );

    // Các thao tác KV/Query trong phạm vi program này.
} finally {
    try {
        if (cluster != null) {
            cluster.disconnect();
        }
    } finally {
        environment.shutdown();
    }
}
~~~

**Cluster đóng trước, environment đóng sau**, vì cluster sử dụng environment. Mẫu `finally` lồng nhau giúp shutdown environment ngay cả khi disconnect phát sinh lỗi. Đây là ví dụ SDK độc lập; nếu client được Spring container quản lý, không sao chép đoạn đóng này vào mỗi service.

### 11.1. Environment dùng chung bởi nhiều cluster

Trong hệ thống có nhiều cluster và một environment dùng chung, không được shutdown environment khi **một** cluster dừng nhưng cluster khác vẫn hoạt động. Owner chung cần quản lý thứ tự:

~~~text
ClusterEnvironment (shared)
├── Cluster A
└── Cluster B

Khi dừng toàn bộ:
1. Ngừng producers/consumers của A và B.
2. Disconnect Cluster A và Cluster B.
3. Shutdown environment sau cùng.
~~~

Điều này khác với một `CouchbaseClientFactory` mặc định phục vụ một bucket. Nhiều bucket trong cùng cluster không có nghĩa phải tạo nhiều `ClusterEnvironment`.

## 12. Nhiều ApplicationContext hoặc context dùng chung client

Trong ứng dụng lớn, có thể có parent/child application contexts, test contexts hoặc các module/plugin sử dụng những tài nguyên bên ngoài cùng một SDK client.

Cần xác định:

| Trường hợp | Vấn đề sở hữu | Cách xử lý |
| --- | --- | --- |
| Một Boot `ApplicationContext` duy nhất | Container sở hữu các bean do nó tạo | Dựa vào auto-configuration/destroy method |
| Context con inject bean của context cha | Bean thuộc context cha | Không đóng client từ context con |
| Hai context tự tạo hai cluster riêng | Mỗi context sở hữu một client riêng | Mỗi context đóng bean nó tạo |
| Hai context dùng chung một client ngoại sinh | Một tài nguyên có nhiều người dùng | Chỉ owner độc lập được đóng, cần hợp đồng lifecycle rõ |
| Test context cache giữa nhiều test | Tài nguyên sống theo cache/context | Không đóng client dùng chung trong test method |

Tránh coi `@DirtiesContext` là “reset repository” vô hại; nó có thể làm đóng toàn bộ context, kéo theo SDK clients và tác vụ phụ thuộc. Nếu test cần cô lập trạng thái dữ liệu, dùng keyspace/test data phù hợp thay vì tắt context không cần thiết.

### 12.1. Không để container đóng một client không do nó sở hữu

Nếu một bean method chỉ **trả về một `Cluster` có sẵn** thuộc sở hữu hệ thống bên ngoài, cần xác định rõ có cho Spring quyền gọi destroy hay không. Có thể không muốn Spring tự suy luận `close()/shutdown` nếu chủ sở hữu của tài nguyên nằm ở nơi khác. Thiết kế này cần cấu hình destroy phù hợp và documentation rành mạch; tránh đăng ký bean ngoại sinh như một bean có ownership đầy đủ khi không có quyền dọn.

Ngược lại, nếu Spring tự tạo `Cluster` qua bean factory method, phải có cơ chế cleanup rõ. Không lựa chọn mơ hồ tùy vào việc bean được cung cấp từ đâu.

## 13. Timeout và retry khi tiến trình sắp dừng

Trong quá trình shutdown, một request Couchbase còn chờ có thể kết thúc bằng timeout. Hãy phân biệt:

- **Connect timeout**: SDK không thiết lập được liên lạc với cluster trong thời hạn.
- **KV timeout**: thao tác theo document ID không hoàn tất đúng thời hạn.
- **Query timeout**: truy vấn SQL++ chưa hoàn tất trong ngân sách.
- **Shutdown deadline**: thời gian mà application/orchestrator cho phép drain.
- **Transaction deadline**: giới hạn hoạt động/commit riêng theo cơ chế giao dịch.

Nếu timeout SDK dài hơn termination grace period của pod, nhiều thao tác có thể chưa kịp trả kết quả trước khi JVM bị cưỡng bức tắt.

Ví dụ ngân sách giả định:

~~~text
Pod termination grace:       45 giây
├── Stop nhận công việc mới:  5 giây
├── Drain in-flight work:     30 giây
└── SDK cleanup + buffer:     10 giây
~~~

Đây chỉ là ví dụ tổ chức thời gian, không phải thông số mặc định của Spring Boot hoặc Kubernetes. Phải đo đạc thực tế, hiểu quy tắc termination signal và cấu hình deadline phù hợp.

**Không retry vô hạn khi shutdown đã bắt đầu.** Một luồng nền cứ retry làm ứng dụng không đạt trạng thái quiescent, trong khi SDK resources sắp đóng. Dừng schedule/retry mới và quyết định rõ những thao tác còn dang dở cần lưu trạng thái ra đâu.

## 14. Xác minh destroy order bằng test không cần Couchbase thật

Để kiểm tra tư duy về lifecycle, có thể viết một test Spring nhỏ dùng các bean minh họa thay cho SDK. Test này **không mở kết nối mạng**, chỉ kiểm chứng bean phụ thuộc được hủy trước bean mà nó sử dụng.

~~~java
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SpringDestroyOrderTest {

    static final List<String> EVENTS = new ArrayList<>();

    static class EnvironmentResource {
        void shutdown() {
            EVENTS.add("environment");
        }
    }

    static class ClusterResource {
        void disconnect() {
            EVENTS.add("cluster");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean(destroyMethod = "shutdown")
        EnvironmentResource env() {
            return new EnvironmentResource();
        }

        @Bean(destroyMethod = "disconnect")
        ClusterResource cluster(EnvironmentResource env) {
            return new ClusterResource();
        }
    }

    @Test
    void dependentResourceClosesFirst() {
        EVENTS.clear();

        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            assertThat(context.containsBean("cluster")).isTrue();
        }

        assertThat(EVENTS).containsExactly("cluster", "environment");
    }
}
~~~

**Mục tiêu của test** là kiểm chứng quan hệ dependency `ClusterResource → EnvironmentResource` và cách Spring gọi destroy methods. Trong dự án thực tế, tránh dùng static mutable state trong test song song hoặc test suite lớn; ở đây nó chỉ làm nhật ký tối giản để nhìn thấy thứ tự.

Test trên **không xác nhận** Couchbase SDK thật sẽ đóng đúng trên mọi phiên bản. Với cấu hình production, cần thêm kiểm thử tích hợp khởi tạo/đóng ApplicationContext, quan sát log resource cleanup và dùng môi trường thử riêng nếu muốn xác nhận mạng/cluster.

## 15. Kiểm tra ứng dụng Spring Boot bằng runtime metrics và log

Khi triển khai, ngoài việc nhìn thấy ứng dụng trả response, cần quan sát:

1. Sau khi gửi lệnh shutdown, HTTP server có ngừng tiếp nhận việc mới?
2. Tác vụ `@Scheduled`, queue consumer và background subscriptions có ngừng tạo request?
3. Những thao tác KV/SQL++ đang chạy có cơ hội hoàn tất trong deadline?
4. Có lỗi `cluster disconnected` hoặc `environment shutdown` xảy ra **trước** khi công việc đang xử lý kết thúc không?
5. Sau khi context đóng, có còn non-daemon threads hoặc tài nguyên SDK giữ process không?
6. Với rolling deployment, instance mới đã đạt readiness trước khi instance cũ ngừng phục vụ?
7. Các mutation timeout quanh thời điểm dừng có được xử lý theo idempotency/đối soát thay vì coi là chắc chắn thất bại?

### 15.1. Đọc lỗi đúng tầng

| Triệu chứng | Nguyên nhân cần kiểm tra | Gợi ý sửa |
| --- | --- | --- |
| Repository cùng lúc báo SDK đã ngắt kết nối | Một service/controller đóng cluster dùng chung | Dời cleanup về owner `ApplicationContext` |
| JVM không thoát dù HTTP server đã dừng | Worker tự tạo hoặc resource không được quản lý | Kiểm tra subscription, executor, custom SDK environment |
| Lỗi xuất hiện khi pod đang terminate | In-flight jobs vẫn dùng SDK trong giai đoạn destroy | Dừng/đợi jobs trước khi đóng client |
| Test sau thất bại vì client bị đóng | Test trước gọi `disconnect()` trên bean cache | Không đóng tài nguyên chia sẻ trong test method |
| Có hai bean SDK và chỉ một được dọn | Tạo client ngoài context hoặc custom config trùng | Kiểm kê ownership và dependency injection |
| KV hoạt động, SQL++ timeout trước khi dừng | Query/index chậm hoặc deadline không phù hợp | Phân biệt Query timeout với lifecycle |
| Mutation có dữ liệu dù client báo timeout | Kết quả ghi mơ hồ | Đối soát trạng thái, CAS/idempotency |
| Rolling restart làm mất việc nền | Worker không drain hoặc không persist checkpoint | Thiết kế lifecycle của task và recovery |

### 15.2. Quan sát đừng làm lộ secrets

Log có thể ghi tên component, trạng thái shutdown, số request in-flight, loại lỗi, thời gian drain và tính sẵn sàng của client. Không log password, private key, token hay nội dung document nhạy cảm. Cũng tránh dùng `System.exit()` tùy tiện trong code nghiệp vụ để ép dừng; cách đó làm khó kiểm soát lifecycle và có thể cắt ngang shutdown.

## 16. Một tình huống điển hình: hệ thống đặt hàng

Ứng dụng `order-service` dùng bucket `commerce`, scope `sales`, collection `orders`. Nó cung cấp ba chức năng:

- API đồng bộ đọc order theo ID bằng repository.
- API reactive cập nhật trạng thái order.
- Background worker đồng bộ order sang một hệ thống khác.

Một đề xuất thiếu an toàn là đặt `@PreDestroy` trong repository service để gọi `cluster.disconnect()` ngay khi nhận sự kiện dừng. Nhưng worker có thể vẫn xử lý batch và một transaction đang commit.

Thiết kế cải thiện:

~~~mermaid
flowchart TD
    A["Nhận tín hiệu shutdown"] --> B["Dừng nhận HTTP/queue jobs mới"]
    B --> C["Drain in-flight API + background work"]
    C --> D{"Công việc hoàn tất trong deadline?"}
    D -- "Có" --> E["Kết thúc business handlers"]
    D -- "Không" --> F["Checkpoint / trạng thái phục hồi<br/>theo thiết kế nghiệp vụ"]
    E --> G["Spring hủy repository/template dependencies"]
    F --> G
    G --> H["SDK Cluster disconnect"]
    H --> I["ClusterEnvironment shutdown"]
~~~

Sơ đồ mô tả **trình tự mong muốn**, không khẳng định Spring tự cung cấp mọi bước drain/checkpoint. Đội phát triển phải tích hợp lifecycle cho queue consumer và background jobs.

### 16.1. Vai trò của TTL, CAS, transaction và SQL++ ở thời điểm dừng

- **TTL:** document có thể hết hạn theo chính sách ngay cả khi ứng dụng dừng; shutdown không “đóng băng” TTL.
- **CAS/`@Version`:** xử lý xung đột ghi giữa instance cũ/mới khi rolling deployment, khác với việc đóng socket.
- **Transaction:** phải tôn trọng hợp đồng commit/rollback và deadline; không coi `@PreDestroy` là nơi tự commit mọi transaction.
- **SQL++:** query đang chạy có thể timeout nếu thời gian drain ngắn; index/Query service vẫn là vấn đề của truy vấn, không phải của destroy order.
- **Reactive:** cancellation không phải bằng chứng mutation đã được rollback.

Nhờ phân biệt đúng các lớp này, chiến lược shutdown có thể nhất quán với chính sách xử lý đơn hàng và retry thay vì chỉ chạy một phương thức `disconnect()`.

## 17. Bài tập thực hành: phát hiện quyền sở hữu sai

**Tình huống:** một ứng dụng Spring Boot khai báo starter Couchbase và các properties kết nối. Một developer thêm đoạn sau trong `ProductService`:

~~~java
@PreDestroy
void cleanup() {
    cluster.disconnect();
    environment.shutdown();
}
~~~

Service này chỉ nhận `Cluster` và `ClusterEnvironment` qua constructor injection từ Spring, không tự tạo chúng. Ứng dụng còn có `InventoryJob` chạy định kỳ, `ReactiveOrderRepository` và các HTTP requests đang xử lý.

**Yêu cầu:**

1. Phân tích hai lỗi ownership trong callback trên.
2. Giải thích tại sao gọi `disconnect()` từ service có thể gây lỗi cho các bean khác.
3. Xác định ai nên đóng các bean nếu Boot tạo chúng.
4. Đề xuất cách dừng `InventoryJob` trước khi SDK resources bị hủy.
5. Nếu không dùng Boot và cần bean SDK tùy chỉnh, viết `@Bean(destroyMethod = "shutdown")` cho environment và `@Bean(destroyMethod = "disconnect")` cho cluster với dependency qua tham số factory method.
6. Phân biệt grace period của pod với timeout KV/SQL++ và deadline của nghiệp vụ.
7. Thiết kế một test không kết nối Couchbase thật để xác nhận destroy order.
8. Giải thích cách xử lý mutation có kết quả mơ hồ khi pod bị terminate lúc ghi.

**Hướng trả lời:**

- Service chỉ là người **dùng** cluster/environment nên không được tự ý hủy hai đối tượng đó.
- Nếu Boot quản lý các bean, container chịu trách nhiệm destroy theo lifecycle.
- Background job phải ngừng sinh công việc mới, sau đó drain trong một giới hạn xác định.
- Với cấu hình SDK thủ công, thể hiện ownership và dependency rõ trong `@Bean` methods.
- Đối với mutation, không kết luận “chưa ghi” chỉ từ timeout/hủy request; phải dùng idempotency, CAS/đối soát hoặc chiến lược transaction tương ứng.

**Tiêu chí hoàn thành:** chỉ ra được owner của từng tài nguyên, mô tả đúng thứ tự dừng, tránh đóng client từ service, và đề xuất kiểm thử phù hợp trước rolling deployment.

## 18. Checklist trước khi đưa ứng dụng lên production

- [ ] Có một chiến lược cấu hình Couchbase rõ ràng: Boot auto-configuration **hoặc** cấu hình thủ công có ownership minh bạch.
- [ ] Không có `Cluster.connect()` hoặc `ClusterEnvironment.builder().build()` chạy trong mỗi request.
- [ ] Service/repository/template không gọi `disconnect()` hay `shutdown()` trên bean dùng chung.
- [ ] Bean SDK tự tạo có `destroyMethod` hoặc cơ chế cleanup phù hợp.
- [ ] Quan hệ bean dependency giúp cluster được đóng trước environment khi cả hai thuộc cùng owner.
- [ ] Producer, scheduler và consumer ngừng phát sinh việc mới trước khi SDK resources bị hủy.
- [ ] Reactive subscription chạy nền có cơ chế dispose/drain và recovery phù hợp.
- [ ] Graceful HTTP shutdown và termination grace period đủ hợp lý so với deadline nghiệp vụ.
- [ ] Có chính sách xử lý mutation timeout mơ hồ, CAS và transaction khi thay instance.
- [ ] Có test xác minh destroy order và quan sát thực tế khi rolling restart.
- [ ] Không giả định `@PreDestroy` chạy trong tình huống kill/crash.
- [ ] Không log secrets khi chẩn đoán các lỗi shutdown.

## 19. Tổng kết

Trong Spring Data Couchbase, các đối tượng `ClusterEnvironment` và `Cluster` là tài nguyên SDK có chi phí và vòng đời dài; các handle `Bucket`, `Scope`, `Collection` và hạ tầng `CouchbaseClientFactory`, `CouchbaseTemplate`, repository phục vụ nhiều thao tác trong cùng `ApplicationContext`. Những đối tượng được inject để sử dụng **không mặc nhiên là nơi sở hữu quyền đóng**.

Với Spring Boot, ưu tiên để container quản lý kết nối và destroy callbacks. Khi tự đăng ký SDK beans, khai báo phương thức hủy rõ ràng, thể hiện dependency và bảo đảm **cluster dừng trước environment**. Với server, scheduler và reactive pipelines, cần ngừng nhận việc mới rồi xử lý công việc đang chạy trong deadline trước khi hủy client.

Một shutdown đúng không chỉ giúp giải phóng tài nguyên; nó còn bảo vệ tính nhất quán dữ liệu khi rolling deployment và tạo nền vận hành tốt cho repository, `CouchbaseTemplate`, SQL++, TTL, CAS, giao dịch và lựa chọn API reactive.

