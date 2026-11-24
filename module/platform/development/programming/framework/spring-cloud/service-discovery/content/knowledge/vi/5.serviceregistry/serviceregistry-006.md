# Dùng đúng kiểu Registration cho Eureka, Consul và Zookeeper

Spring Cloud cung cấp `ServiceRegistry<R extends Registration>` để chuẩn hóa các thao tác đăng ký, hủy đăng ký và quản lý trạng thái của một service instance. Tuy nhiên, kiểu `R` không phải lúc nào cũng là `Registration` chung. Mỗi registry integration thường có lớp registration chuyên biệt mang dữ liệu và quy tắc riêng của nhà cung cấp.

Với các tích hợp phổ biến, kiểu tương ứng là `EurekaRegistration` cho Eureka, `ConsulRegistration` cho Consul và `ZookeeperRegistration` cho Zookeeper. Khi gọi `ServiceRegistry`, cần ghép đúng implementation với đúng registration type. Nếu trộn các kiểu này, Java có thể từ chối biên dịch; nếu cố ép kiểu hoặc dùng raw type, lỗi có thể chuyển thành lỗi runtime khó chẩn đoán.

Bài học thuộc chương `ServiceRegistry` trong module `SPRING_CLOUD_SERVICE_DISCOVERY`. Module giúp người học hiểu cơ chế khám phá instance theo service ID qua `DiscoveryClient`, `ServiceRegistry`, Eureka hoặc Consul, cùng vòng đời đăng ký, health check, load balancing, bảo mật và xử lý sai lệch registry. Trọng tâm bài này là generic type của `ServiceRegistry` và cách chọn đúng registration class khi làm việc với Eureka, Consul và Zookeeper.

## 1. Registration là gì?

Trong Service Discovery, một service có thể chạy nhiều instance. Mỗi instance cần công bố các thông tin để consumer tìm và kết nối, thường gồm:

- Service ID: tên logic của dịch vụ, ví dụ `order-service`.
- Instance ID: định danh một bản chạy cụ thể theo quy tắc của registry.
- Host và port: địa chỉ mà consumer có thể truy cập.
- URI hoặc giao thức: thông tin tạo địa chỉ HTTP/HTTPS tương ứng.
- Metadata: dữ liệu bổ sung như zone, version hoặc nhóm triển khai.
- Trạng thái hoặc thông tin health theo mô hình của registry.

Trong Spring Cloud Commons, `Registration` là abstraction đại diện cho instance được dùng trong quy trình đăng ký. Nó mở rộng `ServiceInstance`, do đó mang các thông tin chung về địa chỉ và metadata:

```java
package org.springframework.cloud.client.serviceregistry;

import org.springframework.cloud.client.ServiceInstance;

public interface Registration extends ServiceInstance {
}
```

`Registration` là interface chung, không phải lớp cụ thể để ứng dụng tùy ý khởi tạo. Các registry integration có thể cung cấp implementation riêng để giữ thêm dữ liệu mà registry của họ cần.

Ví dụ, cùng là một instance `order-service`, nhưng registration có thể cần chứa đối tượng Eureka `InstanceInfo`, cấu trúc service của Consul hoặc thông tin service node của Zookeeper. Các chi tiết này không thể thay thế lẫn nhau chỉ vì tất cả cùng mô tả một service instance.

## 2. Generic contract của ServiceRegistry

Hợp đồng cốt lõi của Spring Cloud Commons có dạng:

```java
package org.springframework.cloud.client.serviceregistry;

public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    void setStatus(R registration, Object status);

    Object getStatus(R registration);
}
```

Tham số kiểu `R extends Registration` có nghĩa là mỗi `ServiceRegistry` làm việc với một kiểu registration cụ thể, và kiểu đó phải triển khai `Registration`.

| Thành phần | Ý nghĩa |
|---|---|
| `R` | Kiểu registration mà implementation quản lý. |
| `register(R registration)` | Công bố instance được mô tả bởi registration. |
| `deregister(R registration)` | Gỡ đúng registration tương ứng khỏi registry. |
| `setStatus(R registration, Object status)` | Đặt trạng thái theo mô hình mà implementation hỗ trợ. |
| `getStatus(R registration)` | Đọc trạng thái theo cách implementation biểu diễn. |

Điểm quan trọng là tham số của `register` và `deregister` có kiểu `R`, không phải bất kỳ đối tượng nào implement `Registration`. Kiểu generic giúp ràng buộc registry với đúng registration class ngay từ lúc biên dịch.

## 3. Registration type theo từng registry

Các registry integration phổ biến cung cấp những cặp kiểu sau:

| Registry | Registration type | ServiceRegistry implementation | Package thường dùng |
|---|---|---|---|
| Eureka | `EurekaRegistration` | `EurekaServiceRegistry` | `org.springframework.cloud.netflix.eureka.serviceregistry` |
| Consul | `ConsulRegistration` | `ConsulServiceRegistry` | `org.springframework.cloud.consul.serviceregistry` |
| Zookeeper | `ZookeeperRegistration` | `ZookeeperServiceRegistry` | `org.springframework.cloud.zookeeper.serviceregistry` |

Về mặt kiểu dữ liệu, các cặp có quan hệ như sau:

```java
ServiceRegistry<EurekaRegistration> eurekaRegistry;
ServiceRegistry<ConsulRegistration> consulRegistry;
ServiceRegistry<ZookeeperRegistration> zookeeperRegistry;
```

Mỗi registration class đều đáp ứng hợp đồng `Registration`, nhưng mỗi registry implementation nhận đúng kiểu chuyên biệt của nó. Khi xem source hoặc API documentation của một phiên bản Spring Cloud cụ thể, hãy kiểm tra declaration của implementation để xác nhận package và generic type theo release train dự án đang sử dụng.

### 3.1. EurekaRegistration

Eureka integration dùng `EurekaRegistration` để đại diện cho thông tin đăng ký gắn với Eureka client. Kiểu này thuộc package:

```java
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaRegistration;
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaServiceRegistry;
```

`EurekaServiceRegistry` quản lý `EurekaRegistration`. Registration này gắn với các thành phần của Eureka client, chẳng hạn thông tin instance và cơ chế quản lý trạng thái ứng dụng của Eureka. Không nên tạo một registration Eureka bằng cách lấy registration của Consul hoặc Zookeeper rồi ép kiểu.

Ví dụ khai báo một thành phần phụ thuộc vào đúng kiểu Eureka:

```java
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaRegistration;
import org.springframework.cloud.netflix.eureka.serviceregistry.EurekaServiceRegistry;
import org.springframework.stereotype.Component;

@Component
public class EurekaRegistryOperations {

    private final EurekaServiceRegistry serviceRegistry;
    private final EurekaRegistration registration;

    public EurekaRegistryOperations(
            EurekaServiceRegistry serviceRegistry,
            EurekaRegistration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void unregister() {
        serviceRegistry.deregister(registration);
    }
}
```

Đây là ví dụ minh họa kiểu phụ thuộc; việc các bean registration và registry có sẵn hay không phụ thuộc starter, cấu hình và lifecycle của ứng dụng. Trong cấu hình Eureka thông thường, Spring Cloud có thể tự đăng ký và hủy đăng ký instance. Không gọi `register` lần nữa một cách tùy tiện nếu auto-registration đã quản lý lifecycle, vì có thể tạo thao tác trùng hoặc làm sai trạng thái.

### 3.2. ConsulRegistration

Consul integration dùng `ConsulRegistration`, thuộc package:

```java
import org.springframework.cloud.consul.serviceregistry.ConsulRegistration;
import org.springframework.cloud.consul.serviceregistry.ConsulServiceRegistry;
```

`ConsulServiceRegistry` làm việc với `ConsulRegistration`. Registration này gắn với thông tin service được công bố cho Consul, chẳng hạn service name, service ID, địa chỉ, port, tags và metadata theo cấu hình tích hợp.

Ví dụ một thành phần thao tác đúng kiểu Consul:

```java
import org.springframework.cloud.consul.serviceregistry.ConsulRegistration;
import org.springframework.cloud.consul.serviceregistry.ConsulServiceRegistry;
import org.springframework.stereotype.Component;

@Component
public class ConsulRegistryOperations {

    private final ConsulServiceRegistry serviceRegistry;
    private final ConsulRegistration registration;

    public ConsulRegistryOperations(
            ConsulServiceRegistry serviceRegistry,
            ConsulRegistration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void unregister() {
        serviceRegistry.deregister(registration);
    }
}
```

Consul có thể dùng agent và health check để cập nhật trạng thái service. Cấu trúc registration và cách tạo service record phụ thuộc cấu hình Consul integration. Không giả định rằng mọi trường metadata hoặc status có cách biểu diễn giống Eureka.

### 3.3. ZookeeperRegistration

Zookeeper integration dùng `ZookeeperRegistration`, thuộc package:

```java
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperRegistration;
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperServiceRegistry;
```

`ZookeeperServiceRegistry` làm việc với `ZookeeperRegistration`. Registration này chứa thông tin cần thiết để đăng ký service instance trong cây dữ liệu Zookeeper, thường liên quan đến service instance và cách tạo node theo cơ chế discovery của Spring Cloud Zookeeper.

Ví dụ:

```java
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperRegistration;
import org.springframework.cloud.zookeeper.serviceregistry.ZookeeperServiceRegistry;
import org.springframework.stereotype.Component;

@Component
public class ZookeeperRegistryOperations {

    private final ZookeeperServiceRegistry serviceRegistry;
    private final ZookeeperRegistration registration;

    public ZookeeperRegistryOperations(
            ZookeeperServiceRegistry serviceRegistry,
            ZookeeperRegistration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void unregister() {
        serviceRegistry.deregister(registration);
    }
}
```

Zookeeper thường biểu diễn service discovery bằng các node trong cây dữ liệu và có thể sử dụng ephemeral node gắn với session để phản ánh vòng đời client. Chi tiết node path, payload và lifecycle do integration quyết định. Vì vậy, `ZookeeperRegistration` không thể thay bằng `EurekaRegistration` hoặc `ConsulRegistration`.

## 4. Vì sao không dùng ServiceRegistry<Registration> cho mọi registry?

Một lỗi thường gặp là khai báo biến tổng quát như sau:

```java
ServiceRegistry<Registration> registry;
```

Sau đó gán một implementation cụ thể:

```java
EurekaServiceRegistry eurekaServiceRegistry = ...;

// Không hợp lệ về kiểu generic:
ServiceRegistry<Registration> registry = eurekaServiceRegistry;
```

Lý do là generic trong Java có tính bất biến (*invariant*). Dù `EurekaRegistration` là subtype của `Registration`, `ServiceRegistry<EurekaRegistration>` không phải subtype của `ServiceRegistry<Registration>`.

Nếu Java cho phép phép gán trên, đoạn code sau có thể truyền registration của registry khác vào Eureka:

```java
// Giả sử phép gán không hợp lệ phía trên được cho phép:
registry.register(consulRegistration);
```

Eureka registry không thể xử lý một `ConsulRegistration` chỉ vì cả hai cùng implement `Registration`. Generic invariant ngăn sai lầm này ở compile time.

### 4.1. Không giải quyết bằng raw type

Raw type bỏ qua kiểm tra generic:

```java
@SuppressWarnings("rawtypes")
ServiceRegistry registry = eurekaServiceRegistry;

// Compiler không còn kiểm tra đúng registration type tại điểm gọi.
registry.register(consulRegistration);
```

Code có thể biên dịch với cảnh báo, nhưng implementation có thể lỗi khi ép kiểu nội bộ hoặc xử lý registration. Không dùng raw `ServiceRegistry` để né lỗi generic.

### 4.2. Không ép kiểu registration của registry khác

Ví dụ sau là sai:

```java
Registration registration = consulRegistration;
EurekaRegistration eurekaRegistration = (EurekaRegistration) registration;
```

Ép kiểu chỉ thay đổi cách compiler nhìn tham chiếu; nó không biến đối tượng Consul thành đối tượng Eureka. Nếu hai class không có quan hệ kế thừa phù hợp, cast sẽ thất bại ở runtime với `ClassCastException`.

## 5. Cách viết hàm dùng chung mà vẫn an toàn kiểu

Nếu muốn tái sử dụng logic gọi `ServiceRegistry`, hãy giữ generic type `R` xuyên suốt hàm. Ví dụ:

```java
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public final class RegistryActions {

    private RegistryActions() {
    }

    public static <R extends Registration> void register(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        serviceRegistry.register(registration);
    }

    public static <R extends Registration> void deregister(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        serviceRegistry.deregister(registration);
    }
}
```

Compiler suy luận `R` từ cặp đối số. Các cách gọi hợp lệ:

```java
RegistryActions.register(eurekaServiceRegistry, eurekaRegistration);
RegistryActions.register(consulServiceRegistry, consulRegistration);
RegistryActions.register(zookeeperServiceRegistry, zookeeperRegistration);
```

Mỗi lời gọi vẫn giữ cặp kiểu tương ứng. Cặp sai kiểu sẽ bị từ chối khi biên dịch:

```java
// Không hợp lệ: registry Eureka không nhận ConsulRegistration.
RegistryActions.register(eurekaServiceRegistry, consulRegistration);
```

Generic method giúp tái sử dụng thao tác chung mà không xóa thông tin kiểu cụ thể. Không cần chuyển mọi registration về `Registration` rồi cast ngược trở lại.

## 6. Khi có nhiều registry trong cùng ứng dụng

Một ứng dụng có thể phụ thuộc nhiều registry vì lý do migration, tích hợp hệ thống cũ hoặc chia vùng. Trong trường hợp đó, cần phân biệt rõ bean và registration tương ứng.

Có thể inject theo generic type:

```java
public class MultiRegistryCoordinator {

    private final ServiceRegistry<EurekaRegistration> eurekaRegistry;
    private final ServiceRegistry<ConsulRegistration> consulRegistry;

    public MultiRegistryCoordinator(
            ServiceRegistry<EurekaRegistration> eurekaRegistry,
            ServiceRegistry<ConsulRegistration> consulRegistry) {
        this.eurekaRegistry = eurekaRegistry;
        this.consulRegistry = consulRegistry;
    }
}
```

Spring có thể dùng generic type khi phân giải dependency. Nếu ứng dụng có nhiều bean cùng generic type hoặc có wrapper tùy chỉnh, hãy dùng `@Qualifier` với bean name thực tế trong cấu hình để tránh mơ hồ. Không đặt tên qualifier theo ví dụ nếu dự án chưa khai báo bean đó.

Nếu cần quản lý một tập registry không đồng nhất, `ServiceRegistry<?>` có thể giữ tham chiếu để quan sát metadata hoặc chuyển tiếp tới logic chỉ đọc phù hợp. Tuy nhiên, wildcard không cho phép truyền một `Registration` tùy ý vào `register`, vì compiler không biết kiểu registration cụ thể mà registry đó chấp nhận. Với thao tác ghi, hãy giữ generic type `R` và registration tương ứng trong cùng một abstraction.

## 7. Auto-registration và thao tác thủ công

Trong các ứng dụng Spring Cloud thông thường, registry starter thường tích hợp đăng ký service vào lifecycle Spring Boot. Khi ứng dụng khởi động, integration tạo registration và đăng ký; khi ứng dụng dừng, integration hủy đăng ký hoặc để cơ chế lease/health của registry xử lý theo cấu hình.

Vì vậy, trước khi gọi `register` hoặc `deregister` thủ công, cần xác định:

1. Auto-registration có đang bật không?
2. Thành phần nào sở hữu vòng đời registration?
3. Registration object được tạo từ bean nào và có phải đúng instance đang chạy không?
4. Có đang vô tình đăng ký trùng hoặc hủy registration trước khi graceful shutdown hoàn tất không?
5. Registry implementation có hỗ trợ status operation theo cách ứng dụng mong đợi không?

Thao tác thủ công có thể hữu ích trong công cụ quản trị hoặc luồng lifecycle tùy chỉnh. Nhưng nếu Spring Cloud đã quản lý registration, nên để một thành phần duy nhất chịu trách nhiệm để tránh các lệnh register/deregister cạnh tranh nhau.

## 8. Khác biệt về status và health giữa các registry

`ServiceRegistry` cung cấp `setStatus` và `getStatus` ở mức abstraction, nhưng tham số status là `Object`. Điều này cho thấy hợp đồng chung không áp đặt một enum hoặc một tập trạng thái giống nhau cho mọi nhà cung cấp.

| Registry | Điều cần kiểm tra |
|---|---|
| Eureka | Kiểu status mà Eureka integration chấp nhận và quan hệ giữa instance status, heartbeat, health và self-preservation. |
| Consul | Cách trạng thái service được phản ánh bởi health check, check status, tags và catalog; không giả định một status object có cùng ý nghĩa với Eureka. |
| Zookeeper | Cách registration tồn tại trong cây dữ liệu, session/ephemeral node và hành vi của implementation với các phương thức status. |

Không nên giả định rằng gọi `setStatus(registration, "DOWN")` sẽ có cùng tác dụng ở cả ba registry. Một implementation có thể yêu cầu enum hoặc object riêng, một implementation khác có thể dựa chủ yếu vào health check hoặc vòng đời node. Hãy kiểm tra API của đúng phiên bản starter và kiểm thử hành vi thực tế.

Cũng cần phân biệt:

- **Registration:** bản ghi cho biết instance được công bố như thế nào.
- **Health check:** phép kiểm tra endpoint hoặc tiến trình có đáp ứng điều kiện sức khỏe không.
- **Heartbeat/lease:** tín hiệu cho biết client còn hoạt động hoặc gia hạn quyền tồn tại của bản ghi.
- **Readiness:** instance đã sẵn sàng nhận traffic nghiệp vụ chưa.
- **Load balancing:** lựa chọn một instance trong các instance được xem là đủ điều kiện.

Các khái niệm này phối hợp với nhau nhưng không đồng nhất. Registry có bản ghi không chứng minh endpoint đang khỏe; trạng thái khỏe cũng không tự động bảo đảm request sẽ kết nối thành công.

## 9. Kiểm tra dependency và import

Khi một registration class không được tìm thấy hoặc không inject được, hãy kiểm tra dependency của registry integration. Mỗi starter cung cấp package và bean riêng:

| Integration | Dependency starter thường gặp | Các kiểu cần nhận diện |
|---|---|---|
| Eureka | `spring-cloud-starter-netflix-eureka-client` | `EurekaRegistration`, `EurekaServiceRegistry` |
| Consul | `spring-cloud-starter-consul-discovery` | `ConsulRegistration`, `ConsulServiceRegistry` |
| Zookeeper | `spring-cloud-starter-zookeeper-discovery` | `ZookeeperRegistration`, `ZookeeperServiceRegistry` |

Tên artifact và cách cấu hình có thể thay đổi theo release train. Dùng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án và tránh tự trộn version của các starter. Nếu ứng dụng chỉ dùng một registry, không cần thêm dependency của hai registry còn lại chỉ để lấy registration class.

Khi kiểm tra compile error, hãy xem:

- Import có trỏ tới đúng package của integration không?
- Biến registry có khai báo generic type tương ứng không?
- Đối tượng registration có cùng loại với generic parameter không?
- Starter có nằm trên classpath và có phiên bản tương thích không?
- Có bean registration/service registry được tạo bởi auto-configuration không?
- Có nhiều bean cùng kiểu khiến Spring không phân giải được dependency không?

## 10. Lỗi thường gặp và cách xử lý

### `ServiceRegistry<Registration>` không nhận implementation cụ thể

Nguyên nhân là generic invariant. Khai báo đúng `ServiceRegistry<EurekaRegistration>`, `ServiceRegistry<ConsulRegistration>` hoặc `ServiceRegistry<ZookeeperRegistration>` theo implementation.

### `register` nhận sai registration class

Đối chiếu generic parameter của implementation với đối tượng truyền vào. Không dùng cast để biến registration của registry này thành registration của registry khác.

### Spring báo không tìm thấy bean registration

Kiểm tra starter, auto-configuration, điều kiện bật discovery và cách ứng dụng đang tắt/bật auto-registration. Một số bean chỉ tồn tại khi cấu hình registry tương ứng được bật.

### Spring báo có nhiều bean phù hợp

Kiểm tra các registry starter được thêm vào cùng lúc. Dùng generic type để phân biệt khi Spring hỗ trợ; nếu vẫn mơ hồ, dùng `@Qualifier` theo tên bean thực tế hoặc inject implementation cụ thể phù hợp với thiết kế.

### Instance xuất hiện hai lần hoặc bị hủy đăng ký sai thời điểm

Kiểm tra xem auto-registration và mã thủ công có cùng thao tác lên một registration không. Chọn một nơi sở hữu lifecycle và bảo đảm registration object đúng với instance hiện tại.

### Status không thay đổi như mong đợi

Kiểm tra kiểu status, semantics của integration và health check. Không giả định chuỗi `UP` hoặc `DOWN` được chấp nhận đồng nhất. Quan sát dữ liệu trong registry và kết quả discovery sau thao tác.

## 11. Checklist chọn đúng Registration type

| Câu hỏi | Điều kiện đúng |
|---|---|
| Ứng dụng đang dùng registry nào? | Xác định starter và integration thực tế. |
| Registry implementation có generic type gì? | Đọc khai báo `ServiceRegistry<R>` của implementation. |
| Registration object là class nào? | Phải khớp đúng `R` của registry đó. |
| Có dùng raw type hoặc unchecked cast không? | Loại bỏ và giữ generic type cụ thể. |
| Có nhiều registry bean không? | Dùng generic-aware injection hoặc `@Qualifier` khi cần. |
| Ai sở hữu lifecycle đăng ký? | Xác định auto-registration hay mã tùy chỉnh; tránh thao tác trùng. |
| Status có cùng semantics không? | Kiểm tra kiểu và hành vi riêng của từng integration. |
| Starter có tương thích không? | Kiểm tra Spring Boot, Spring Cloud release train và BOM. |

## Kết luận

`Registration` là abstraction chung, còn `EurekaRegistration`, `ConsulRegistration` và `ZookeeperRegistration` là các kiểu chuyên biệt cho từng registry integration. Các implementation `EurekaServiceRegistry`, `ConsulServiceRegistry` và `ZookeeperServiceRegistry` ràng buộc generic `ServiceRegistry<R>` với registration class tương ứng. Vì generic Java có tính bất biến, `ServiceRegistry<EurekaRegistration>` không thể được dùng như `ServiceRegistry<Registration>`.

Hãy giữ đúng cặp registry và registration từ khai báo dependency tới constructor injection và lời gọi `register`/`deregister`. Khi cần tái sử dụng logic, dùng generic method `<R extends Registration>` để bảo toàn quan hệ kiểu. Đồng thời, xác định rõ auto-registration, lifecycle và semantics status của từng nhà cung cấp. Cách làm này giúp phát hiện sai kiểu ngay khi biên dịch, giảm cast không an toàn và giữ cho vòng đời Service Discovery nhất quán.
