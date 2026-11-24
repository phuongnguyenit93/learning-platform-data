# Kiểm thử nhiều instance, đổi trạng thái và hủy đăng ký

## 1. Mục tiêu kiểm thử vòng đời instance

Một service có thể có nhiều instance cùng đăng ký dưới một service ID. Client discovery cần nhận được danh sách instance phù hợp; trong khi đó, mỗi instance có vòng đời riêng: đăng ký, chuyển sang trạng thái không nhận traffic, rồi hủy đăng ký khi dừng.

Khi kiểm thử Spring Cloud Service Discovery, cần xác nhận hai nhóm hành vi:

- **Tra cứu:** DiscoveryClient trả danh sách nhiều ServiceInstance, danh sách rỗng hoặc lỗi truy vấn; lớp nghiệp vụ chọn và xử lý instance đúng cách.
- **Vòng đời đăng ký:** ServiceRegistry nhận đúng lệnh register, thay đổi trạng thái và deregister theo thứ tự mà ứng dụng yêu cầu.

DiscoveryClient là abstraction đọc danh sách service/instance. ServiceRegistry là abstraction ghi vòng đời đăng ký của instance cục bộ. Hai interface phục vụ hai hướng khác nhau, vì vậy test cần kiểm soát chúng riêng biệt.

## 2. Phân biệt DiscoveryClient và ServiceRegistry

| API | Trách nhiệm | Ví dụ thao tác |
|---|---|---|
| DiscoveryClient | Tra cứu service và instance | getServices(), getInstances(serviceId) |
| ServiceRegistry | Quản lý registration của instance hiện tại | register(), setStatus(), deregister() |
| ServiceInstance | Mô tả endpoint được tìm thấy | service ID, host, port, URI, metadata |
| Registration | Instance có thể được đăng ký với registry | Thông tin ServiceInstance dùng cho register/deregister |

DiscoveryClient thường trả về nhiều ServiceInstance vì service có thể chạy nhiều replica. ServiceRegistry làm việc với một registration cụ thể mà ứng dụng đang quản lý. Không gọi setStatus trên DiscoveryClient: API đó thuộc ServiceRegistry hoặc provider client tương ứng.

## 3. Chuẩn bị dependency kiểm thử

Ví dụ dùng JUnit 5, Mockito và AssertJ. Với dự án Spring Boot, spring-boot-starter-test thường cung cấp các thư viện này:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Spring Cloud Commons version nên được quản lý bởi Spring Cloud BOM tương thích với Spring Boot của dự án. Không tự ghép một version Commons khác release train.

Nếu dùng Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-commons")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

## 4. Tạo lớp đọc danh sách nhiều instance

Giả sử payment-service cần lấy tất cả endpoint của inventory-service để chuyển cho một chính sách chọn instance:

~~~java
package com.example.payment.discovery;

import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class ServiceInstanceDirectory {

    private final DiscoveryClient discoveryClient;

    public ServiceInstanceDirectory(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findUris(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(ServiceInstance::getUri)
                .collect(Collectors.toList());
    }
}
~~~

Lớp này chỉ chuyển danh sách ServiceInstance thành danh sách URI. Nó không tự kiểm tra health endpoint và không tự bảo đảm URI có thể kết nối được. Provider chịu trách nhiệm trả danh sách theo discovery semantics của nó; lớp gọi vẫn cần xử lý lỗi kết nối khi gửi request.

## 5. Kiểm thử khi có nhiều instance

Tạo file test:

~~~text
src/test/java/com/example/payment/discovery/ServiceInstanceDirectoryTest.java
~~~

Ví dụ JUnit 5 và Mockito:

~~~java
package com.example.payment.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@ExtendWith(MockitoExtension.class)
class ServiceInstanceDirectoryTest {

    private static final String SERVICE_ID = "inventory-service";

    @Mock
    private DiscoveryClient discoveryClient;

    private ServiceInstanceDirectory directory;

    @BeforeEach
    void setUp() {
        directory = new ServiceInstanceDirectory(discoveryClient);
    }

    @Test
    void shouldReturnEveryDiscoveredInstanceInProviderOrder() {
        URI firstUri = URI.create("http://10.0.0.12:8081");
        URI secondUri = URI.create("http://10.0.0.13:8081");
        ServiceInstance first = mock(ServiceInstance.class);
        ServiceInstance second = mock(ServiceInstance.class);

        when(first.getUri()).thenReturn(firstUri);
        when(second.getUri()).thenReturn(secondUri);
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Arrays.asList(first, second));

        List<URI> result = directory.findUris(SERVICE_ID);

        assertThat(result).containsExactly(firstUri, secondUri);
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldReturnEmptyListWhenServiceHasNoInstances() {
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Collections.emptyList());

        List<URI> result = directory.findUris(SERVICE_ID);

        assertThat(result).isEmpty();
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldPropagateDiscoveryFailure() {
        RuntimeException failure =
                new RuntimeException("registry query failed");
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenThrow(failure);

        org.assertj.core.api.Assertions.assertThatThrownBy(
                () -> directory.findUris(SERVICE_ID))
                .isSameAs(failure);
    }
}
~~~

Test đầu tiên xác nhận cả hai URI được giữ lại và thứ tự kết quả không bị thay đổi bởi lớp directory. Test thứ hai phân biệt trường hợp truy vấn thành công nhưng service chưa có instance. Test thứ ba xác nhận lỗi từ provider không bị biến thành danh sách rỗng một cách âm thầm.

Thứ tự trong ví dụ chỉ là thứ tự DiscoveryClient trả về. Không nên mặc định phần tử đầu tiên luôn có ưu tiên cao nhất; thuật toán chọn instance có thể thuộc Spring Cloud LoadBalancer hoặc một policy riêng.

## 6. Kiểm thử chính sách chọn instance

Nếu ứng dụng có chính sách chọn instance riêng, hãy kiểm thử chính sách đó thay vì kiểm tra thứ tự ngẫu nhiên của provider. Ví dụ đơn giản dưới đây chọn luân phiên giữa các URI:

~~~java
package com.example.payment.discovery;

import java.net.URI;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class RoundRobinUriSelector {

    private final ServiceInstanceDirectory directory;
    private final AtomicInteger sequence = new AtomicInteger();

    public RoundRobinUriSelector(ServiceInstanceDirectory directory) {
        this.directory = directory;
    }

    public URI choose(String serviceId) {
        List<URI> uris = directory.findUris(serviceId);
        if (uris.isEmpty()) {
            throw new IllegalStateException(
                    "No instances found for " + serviceId);
        }
        int index = Math.floorMod(sequence.getAndIncrement(), uris.size());
        return uris.get(index);
    }
}
~~~

Test cho selector có thể mock ServiceInstanceDirectory:

~~~java
package com.example.payment.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RoundRobinUriSelectorTest {

    @Mock
    private ServiceInstanceDirectory directory;

    private RoundRobinUriSelector selector;

    @BeforeEach
    void setUp() {
        selector = new RoundRobinUriSelector(directory);
    }

    @Test
    void shouldRotateAcrossAvailableInstances() {
        URI first = URI.create("http://10.0.0.12:8081");
        URI second = URI.create("http://10.0.0.13:8081");
        when(directory.findUris("inventory-service"))
                .thenReturn(Arrays.asList(first, second));

        assertThat(selector.choose("inventory-service")).isEqualTo(first);
        assertThat(selector.choose("inventory-service")).isEqualTo(second);
        assertThat(selector.choose("inventory-service")).isEqualTo(first);
    }

    @Test
    void shouldFailClearlyWhenNoInstanceIsAvailable() {
        when(directory.findUris("inventory-service"))
                .thenReturn(Collections.emptyList());

        assertThatThrownBy(() -> selector.choose("inventory-service"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("inventory-service");
    }
}
~~~

Đây là thuật toán minh họa cho logic ứng dụng. Khi dùng Spring Cloud LoadBalancer, nên kiểm thử ServiceInstanceListSupplier, ReactorLoadBalancer hoặc policy thực tế của ứng dụng thay vì thay thế chúng bằng selector riêng không được dùng trong production.

## 7. Mô hình hóa thay đổi trạng thái và hủy đăng ký

ServiceRegistry có generic type R extends Registration. Mỗi provider có registration type cụ thể; do đó, code dùng registry nên giữ đúng generic type của provider thay vì ép mọi registration thành một kiểu raw.

Ví dụ một lớp điều phối generic:

~~~java
package com.example.payment.discovery;

import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

public class RegistrationLifecycle<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;
    private final String unavailableStatus;

    public RegistrationLifecycle(
            ServiceRegistry<R> serviceRegistry,
            String unavailableStatus) {
        this.serviceRegistry = serviceRegistry;
        this.unavailableStatus = unavailableStatus;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void markUnavailable(R registration) {
        serviceRegistry.setStatus(registration, unavailableStatus);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

Lớp này tách ba thao tác để ứng dụng có thể điều phối quá trình dừng:

1. Đăng ký instance khi khởi động.
2. Đổi trạng thái để ngừng nhận request mới.
3. Chờ khoảng drain phù hợp ở tầng ứng dụng hoặc load balancer.
4. Hủy đăng ký sau khi hoàn tất hoặc hết thời hạn drain.

Status string phụ thuộc provider. Ví dụ Eureka có trạng thái OUT_OF_SERVICE; Consul thường dựa vào health check passing/critical; Kubernetes Service discovery thường dựa vào readiness và EndpointSlice. Không sao chép chuỗi trạng thái của Eureka sang provider khác rồi kỳ vọng cùng semantics.

## 8. Kiểm thử register, đổi trạng thái và deregister

Có thể mock cả ServiceRegistry và Registration:

~~~java
package com.example.payment.discovery;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

@ExtendWith(MockitoExtension.class)
class RegistrationLifecycleTest {

    private static final String UNAVAILABLE = "OUT_OF_SERVICE";

    @Mock
    private ServiceRegistry<Registration> serviceRegistry;

    @Mock
    private Registration registration;

    private RegistrationLifecycle<Registration> lifecycle;

    @BeforeEach
    void setUp() {
        lifecycle = new RegistrationLifecycle<>(
                serviceRegistry, UNAVAILABLE);
    }

    @Test
    void shouldRegisterInstance() {
        lifecycle.register(registration);

        verify(serviceRegistry).register(registration);
    }

    @Test
    void shouldChangeStatusWithoutDeregisteringImmediately() {
        lifecycle.markUnavailable(registration);

        verify(serviceRegistry).setStatus(registration, UNAVAILABLE);
    }

    @Test
    void shouldDeregisterTheRequestedRegistration() {
        lifecycle.deregister(registration);

        verify(serviceRegistry).deregister(registration);
    }

    @Test
    void shouldAllowDrainSequenceBeforeDeregistration() {
        lifecycle.register(registration);
        lifecycle.markUnavailable(registration);
        // Ứng dụng chờ drain ở đây; unit test không sleep.
        lifecycle.deregister(registration);

        InOrder order = inOrder(serviceRegistry);
        order.verify(serviceRegistry).register(registration);
        order.verify(serviceRegistry).setStatus(registration, UNAVAILABLE);
        order.verify(serviceRegistry).deregister(registration);
    }
}
~~~

Test xác nhận ứng dụng gửi đúng thao tác tới registry và giữ đúng thứ tự. Comment drain biểu thị điểm mà ứng dụng có thể chờ request đang chạy kết thúc; unit test không cần Thread.sleep vì mục tiêu của test này là thứ tự tương tác.

Trong dự án Eureka, registration thực tế thường có kiểu cụ thể như EurekaRegistration. Khi tích hợp bean thật, hãy dùng đúng generic type do provider cung cấp. Ví dụ trên dùng Registration mock để minh họa contract chung của ServiceRegistry.

## 9. Vì sao status change và deregistration là hai bước?

Đổi status thường dùng để báo instance tạm thời không nhận traffic mới. Deregister loại registration khỏi registry. Trong một quy trình graceful shutdown:

1. Ứng dụng chuyển instance sang trạng thái không phục vụ.
2. Registry hoặc client nhận thay đổi theo cơ chế cập nhật của provider.
3. Load balancer ngừng chọn instance cho request mới.
4. Ứng dụng hoàn tất request đang chạy trong thời hạn cho phép.
5. Ứng dụng deregister và đóng tài nguyên.

Không phải provider nào cũng có cùng mô hình status. Với Eureka, OUT_OF_SERVICE có semantics rõ ràng trong registry. Với Consul, service health thường được điều khiển bởi check; cập nhật check hoặc deregister có thể phù hợp hơn. Với Kubernetes, readiness false và quá trình terminating/EndpointSlice thường điều khiển endpoint. Unit test generic chỉ xác nhận ứng dụng gọi abstraction; integration test phải xác nhận provider thật chuyển trạng thái đúng.

Một số provider có thể không hỗ trợ setStatus theo cùng cách hoặc có thể triển khai thao tác này bằng cập nhật health check. Nếu provider không có status setter phù hợp, hãy dùng adapter/provider API tương ứng và kiểm thử contract đó riêng.

## 10. Kiểm thử nhiều registration

Một service ID có thể có nhiều instance. Nếu lớp ứng dụng quản lý một tập registration, test nên xác nhận từng registration được xử lý độc lập:

~~~java
@Test
void shouldRegisterEachLocalRegistration() {
    Registration first = mock(Registration.class);
    Registration second = mock(Registration.class);

    lifecycle.register(first);
    lifecycle.register(second);

    verify(serviceRegistry).register(first);
    verify(serviceRegistry).register(second);
}
~~~

Đoạn test này có thể đặt trong RegistrationLifecycleTest. Nó không chứng minh hai instance đã xuất hiện trong registry hoặc DiscoveryClient đã nhìn thấy chúng; nó chỉ xác nhận hai registration được gửi tới ServiceRegistry.

Nếu ứng dụng chỉ chạy một registration cục bộ, không cần tạo nhiều registration giả để mô phỏng replica ở các process khác. Hãy mô phỏng nhiều replica ở phía DiscoveryClient bằng danh sách ServiceInstance như phần trước.

## 11. Kiểm tra thay đổi trạng thái có lan tới DiscoveryClient không

Một unit test mock ServiceRegistry và một mock DiscoveryClient không tự đồng bộ dữ liệu với nhau. Khi gọi:

~~~java
serviceRegistry.setStatus(registration, "OUT_OF_SERVICE");
~~~

mock DiscoveryClient sẽ không tự loại instance khỏi getInstances(). Đó là hai mock độc lập, mỗi mock chỉ trả hành vi đã được stub.

Để kiểm tra trạng thái sau khi đổi status:

- Unit test: xác nhận ServiceRegistry nhận đúng setStatus/deregister.
- Integration test: dùng Eureka, Consul hoặc Kubernetes provider thật trong môi trường kiểm thử để xác nhận trạng thái được ghi và lookup trả kết quả phù hợp.
- End-to-end test: gửi request qua LoadBalancer/gateway và xác nhận instance đã drain không còn được chọn cho request mới.

Không assert rằng DiscoveryClient lập tức bỏ instance ngay sau setStatus. Peer replication, registry fetch, health check interval và cache của client có thể tạo độ trễ quan sát.

## 12. Kiểm thử deregistration và shutdown

Khi ứng dụng dừng bình thường, lifecycle callback hoặc provider integration có thể gọi deregister. Có thể kiểm thử lớp điều phối shutdown bằng mock ServiceRegistry và xác minh:

- Registration đúng được truyền vào deregister.
- Status được đổi trước deregister nếu chính sách yêu cầu.
- Không deregister registration của service khác.
- Lỗi ở bước đổi status và lỗi deregister được xử lý theo chính sách shutdown.

Không nên giả định mọi shutdown đều gửi được deregister. Nếu tiến trình bị kill -9, host mất điện hoặc mạng bị phân vùng, lệnh deregister có thể không chạy hoặc không đến registry. Khi đó provider dùng lease, heartbeat timeout, health check hoặc session expiration để dọn bản ghi.

Test unit có thể mô phỏng exception của registry:

~~~java
import static org.mockito.Mockito.doThrow;

doThrow(new RuntimeException("registry unavailable"))
        .when(serviceRegistry)
        .deregister(registration);
~~~

Sau đó kiểm tra lớp shutdown ghi nhận hoặc truyền lỗi theo contract. Nếu ứng dụng cần shutdown tiếp dù deregister thất bại, logic xử lý phải thể hiện rõ điều đó thay vì nuốt exception ngoài ý muốn.

## 13. Những tình huống cần có trong bộ test

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| DiscoveryClient trả một instance | URI/instance được đọc đúng |
| DiscoveryClient trả nhiều instance | Tất cả instance được giữ hoặc policy chọn đúng |
| Danh sách instance rỗng | Trả empty hoặc lỗi nghiệp vụ có chủ đích |
| DiscoveryClient ném exception | Không bị hiểu nhầm thành danh sách rỗng |
| Register thành công | Đúng Registration được gửi tới ServiceRegistry |
| Đổi trạng thái | Status provider-specific được truyền đúng |
| Bắt đầu drain | Instance được đánh dấu không phục vụ trước khi hoàn tất drain |
| Deregister | Đúng Registration được hủy |
| Nhiều registration | Thao tác trên từng registration không nhầm lẫn |
| Deregister thất bại | Shutdown xử lý lỗi theo chính sách |
| Mất mạng khi shutdown | Không giả định lệnh deregister luôn được thực hiện |

## 14. Lỗi kiểm thử thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra một instance | Test data không mô phỏng nhiều replica | Stub getInstances với nhiều ServiceInstance |
| Cho rằng đổi status làm mock DiscoveryClient thay đổi | Hai mock không chia sẻ trạng thái | Dùng fake chung hoặc integration test |
| Dùng status Eureka cho mọi provider | Status string không có semantics chung | Cấu hình status theo provider |
| Kiểm tra instance biến mất ngay lập tức | Bỏ qua replication/fetch/cache | Kiểm tra eventual propagation trong integration test |
| Dùng Thread.sleep trong unit test | Cố chờ propagation không có thật giữa mock | Verify thứ tự; dùng polling có timeout trong integration test |
| Dùng raw ServiceRegistry | Mất type safety và dễ truyền sai registration | Dùng generic type của provider |
| Chỉ test graceful shutdown | Bỏ qua crash hoặc network partition | Test thêm timeout, lease, session và stale entry ở tầng integration |
| Verify quá nhiều chi tiết nội bộ | Test phụ thuộc implementation | Chỉ verify tương tác thuộc contract cần bảo đảm |

## 15. Unit test và integration test

| Nội dung | Unit test | Integration test |
|---|---|---|
| DiscoveryClient trả nhiều instance | Mockito stub | Provider trả danh sách thật |
| Logic chọn instance | Test với dữ liệu cố định | Kiểm tra LoadBalancer/provider tích hợp |
| Gọi register/setStatus/deregister | Mock ServiceRegistry | Registry thật ghi nhận thay đổi |
| Status có đúng semantics provider | Không đủ | Cần |
| Instance bị loại khỏi lookup sau deregister | Không đủ | Cần |
| Độ trễ replication/cache | Không kiểm tra | Cần đo |
| Shutdown khi mất mạng | Mô phỏng exception | Kiểm tra timeout và cleanup thực tế |

Unit test nhanh và tập trung vào logic ứng dụng. Integration test xác nhận provider và hệ thống phân tán phối hợp đúng. Cả hai đều cần thiết khi triển khai vòng đời instance.

## 16. Quy trình viết test

1. Xác định logic đọc danh sách instance và logic quản lý registration.
2. Inject DiscoveryClient và ServiceRegistry qua constructor hoặc seam phù hợp.
3. Mock DiscoveryClient để trả một, nhiều hoặc không có instance.
4. Kiểm tra kết quả và policy chọn instance.
5. Mock ServiceRegistry với generic registration type phù hợp.
6. Xác nhận register, setStatus và deregister nhận đúng đối tượng và status.
7. Dùng InOrder khi thứ tự chuyển trạng thái là một phần contract.
8. Kiểm thử exception khi provider không truy cập được.
9. Không dùng sleep để chờ cache hoặc replication trong unit test.
10. Viết integration test riêng để xác nhận trạng thái thật lan tới lookup và LoadBalancer.

~~~mermaid
flowchart TD
    A[Chuẩn bị DiscoveryClient mock] --> B[Stub một hoặc nhiều ServiceInstance]
    B --> C[Assert danh sách và policy chọn]
    C --> D[Chuẩn bị ServiceRegistry mock]
    D --> E[Register registration]
    E --> F[Set status không phục vụ]
    F --> G[Drain request đang chạy]
    G --> H[Deregister registration]
    H --> I[Verify đối tượng, status và thứ tự]
    I --> J[Integration test với provider thật]
~~~

## 17. Tổng kết

Kiểm thử nhiều instance cần mô phỏng DiscoveryClient trả về danh sách ServiceInstance có nhiều endpoint, rồi xác nhận lớp nghiệp vụ giữ hoặc chọn instance theo đúng policy. Kiểm thử vòng đời đăng ký cần mô phỏng ServiceRegistry và xác nhận register, setStatus, deregister được gọi với đúng registration và status.

DiscoveryClient là phía tra cứu; ServiceRegistry là phía quản lý registration. Thay đổi status và hủy đăng ký là hai thao tác riêng, thường được sắp xếp để instance ngừng nhận request mới trước khi hoàn tất drain. Unit test không chứng minh trạng thái đã lan qua peer replication, health check, client cache hoặc EndpointSlice; cần integration test với provider thật để kiểm tra propagation và hành vi của LoadBalancer.
