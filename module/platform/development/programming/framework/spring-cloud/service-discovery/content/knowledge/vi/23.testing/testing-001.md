# Kiểm thử đơn vị với DiscoveryClient giả lập

## 1. Vì sao nên giả lập DiscoveryClient?

Một service Spring Cloud thường dùng DiscoveryClient để tìm các instance theo service ID. Khi kiểm thử logic của service gọi, ta cần xác nhận ứng dụng xử lý đúng các kết quả như có instance, không có instance hoặc provider discovery phát sinh lỗi.

Nếu mỗi unit test đều cần khởi động Eureka, Consul hoặc Kubernetes, bài kiểm thử sẽ chậm, phụ thuộc môi trường và khó tái lập lỗi. Có thể thay DiscoveryClient thật bằng một mock do Mockito điều khiển. Test chỉ tập trung vào hành vi của lớp đang kiểm thử:

- Service ID nào được truy vấn?
- Ứng dụng xử lý danh sách instance như thế nào?
- Điều gì xảy ra khi registry không có instance?
- Điều gì xảy ra khi DiscoveryClient ném exception?
- Ứng dụng có giữ đúng ranh giới giữa “không tìm thấy instance” và “không truy vấn được discovery” hay không?

Trong module Spring Cloud Service Discovery, DiscoveryClient là abstraction dùng chung cho Eureka, Consul, Kubernetes và các provider khác. Unit test dựa trên abstraction này không cần biết provider cụ thể nào đang chạy.

## 2. Phạm vi của unit test

Một unit test tốt kiểm tra một đơn vị logic với các dependency được kiểm soát. Trong bài này, lớp cần kiểm thử nhận DiscoveryClient qua constructor. Mockito tạo mock cho interface đó và trả kết quả được khai báo trong từng test.

| Thành phần | Trong unit test |
|---|---|
| Service đang kiểm thử | Đối tượng thật |
| DiscoveryClient | Mockito mock |
| ServiceInstance | Có thể là mock riêng |
| Eureka/Consul/Kubernetes | Không khởi động |
| Spring ApplicationContext | Không cần tạo |
| Network, DNS, registry | Không sử dụng |

Unit test xác nhận logic của ứng dụng khi DiscoveryClient trả về dữ liệu đã định trước. Nó không xác nhận cấu hình mạng, quyền truy cập Kubernetes API, kết nối Eureka Server hoặc cách provider đồng bộ registry. Những phần đó cần integration test riêng.

## 3. Chuẩn bị dependency kiểm thử

Ví dụ sử dụng JUnit 5, Mockito và AssertJ. Với dự án Spring Boot, dependency starter test thường đã cung cấp các thư viện này:

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

Các version nên được quản lý bởi Spring Boot parent/BOM và Spring Cloud release train tương thích. Không tự chọn một version Spring Cloud Commons độc lập với dependency management của dự án.

Nếu dự án Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-commons")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Spring Boot Starter Test cung cấp JUnit Jupiter, Mockito và AssertJ trong cấu hình phổ biến. Nếu dự án không dùng starter này, hãy khai báo riêng JUnit Jupiter, mockito-junit-jupiter và AssertJ với version tương thích.

## 4. Tạo lớp nghiệp vụ sử dụng DiscoveryClient

Giả sử payment-service cần tìm URI của một service khác trước khi gửi request. Ta tách thao tác discovery vào một lớp nhỏ:

~~~java
package com.example.payment.discovery;

import java.net.URI;
import java.util.Optional;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class ServiceEndpointResolver {

    private final DiscoveryClient discoveryClient;

    public ServiceEndpointResolver(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public Optional<URI> resolveFirstInstance(String serviceId) {
        try {
            return discoveryClient.getInstances(serviceId)
                    .stream()
                    .findFirst()
                    .map(ServiceInstance::getUri);
        } catch (RuntimeException exception) {
            throw new DiscoveryLookupException(serviceId, exception);
        }
    }
}
~~~

Exception của lớp ứng dụng:

~~~java
package com.example.payment.discovery;

public class DiscoveryLookupException extends RuntimeException {

    public DiscoveryLookupException(String serviceId, Throwable cause) {
        super("Cannot discover instances for service: " + serviceId, cause);
    }
}
~~~

Lớp resolver không khởi tạo EurekaClient hoặc Kubernetes API client. Nó chỉ phụ thuộc vào DiscoveryClient, vì vậy có thể thay provider mà không phải thay logic tìm URI.

Trong ví dụ, danh sách rỗng được biểu diễn bằng Optional.empty(). Exception khi truy vấn discovery được chuyển thành DiscoveryLookupException để caller phân biệt hai tình huống:

- Registry trả lời thành công nhưng hiện không có instance.
- Thao tác truy vấn discovery thất bại.

Không nên âm thầm chuyển exception thành danh sách rỗng. Làm vậy sẽ khiến lỗi mạng, lỗi quyền hoặc lỗi provider bị hiểu nhầm thành service chưa được đăng ký.

## 5. Viết unit test với Mockito

Tạo test cùng package với lớp đang kiểm thử, ví dụ:

~~~text
src/test/java/com/example/payment/discovery/ServiceEndpointResolverTest.java
~~~

Nội dung test:

~~~java
package com.example.payment.discovery;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@ExtendWith(MockitoExtension.class)
class ServiceEndpointResolverTest {

    private static final String SERVICE_ID = "inventory-service";

    @Mock
    private DiscoveryClient discoveryClient;

    private ServiceEndpointResolver resolver;

    @BeforeEach
    void setUp() {
        resolver = new ServiceEndpointResolver(discoveryClient);
    }

    @Test
    void shouldReturnUriWhenInstanceExists() {
        URI expectedUri = URI.create("http://10.0.0.12:8081");
        ServiceInstance instance = mock(ServiceInstance.class);

        when(instance.getUri()).thenReturn(expectedUri);
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Collections.singletonList(instance));

        Optional<URI> result = resolver.resolveFirstInstance(SERVICE_ID);

        assertThat(result).contains(expectedUri);
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldReturnEmptyWhenNoInstanceIsRegistered() {
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Collections.emptyList());

        Optional<URI> result = resolver.resolveFirstInstance(SERVICE_ID);

        assertThat(result).isEmpty();
        verify(discoveryClient).getInstances(SERVICE_ID);
    }

    @Test
    void shouldUseFirstInstanceFromReturnedList() {
        URI firstUri = URI.create("http://10.0.0.12:8081");
        URI secondUri = URI.create("http://10.0.0.13:8081");
        ServiceInstance first = mock(ServiceInstance.class);
        ServiceInstance second = mock(ServiceInstance.class);

        when(first.getUri()).thenReturn(firstUri);
        when(second.getUri()).thenReturn(secondUri);
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenReturn(Arrays.asList(first, second));

        Optional<URI> result = resolver.resolveFirstInstance(SERVICE_ID);

        assertThat(result).contains(firstUri);
    }

    @Test
    void shouldWrapDiscoveryFailureAndKeepOriginalCause() {
        RuntimeException providerFailure =
                new RuntimeException("registry connection failed");
        when(discoveryClient.getInstances(SERVICE_ID))
                .thenThrow(providerFailure);

        Throwable thrown = catchThrowable(
                () -> resolver.resolveFirstInstance(SERVICE_ID));

        assertThat(thrown).isInstanceOf(DiscoveryLookupException.class);
        assertThat(thrown.getCause()).isSameAs(providerFailure);
    }
}
~~~

Các test không tạo Spring ApplicationContext. MockitoExtension khởi tạo mock trước mỗi test, còn setUp tạo đối tượng ServiceEndpointResolver thật với mock được truyền qua constructor.

## 6. Hiểu từng kịch bản kiểm thử

### 6.1. Có instance

Test khai báo DiscoveryClient trả về một ServiceInstance. ServiceInstance cũng được mock để trả URI mong đợi. Sau khi gọi resolver, test kiểm tra Optional chứa đúng URI và DiscoveryClient được gọi với đúng service ID.

Test này xác nhận luồng dữ liệu từ kết quả discovery đến kết quả mà lớp nghiệp vụ công bố.

### 6.2. Không có instance

Khi DiscoveryClient trả danh sách rỗng, resolver trả Optional.empty(). Đây là một kết quả hợp lệ nếu registry truy vấn thành công nhưng service chưa có instance.

Kịch bản này cần được kiểm thử riêng với exception. Một danh sách rỗng không phải lỗi provider.

### 6.3. Có nhiều instance

Ví dụ resolver chọn phần tử đầu tiên của danh sách. Test khai báo hai instance và xác nhận URI của phần tử đầu tiên được sử dụng.

Thứ tự danh sách do provider trả về không nhất thiết là thứ tự ưu tiên nghiệp vụ. Trong ứng dụng thật, nếu cần chọn instance theo zone, metadata, weight hoặc load balancing, hãy kiểm thử chính sách chọn instance tương ứng thay vì mặc định phần tử đầu tiên luôn tốt nhất.

### 6.4. DiscoveryClient ném exception

Khi provider ném RuntimeException, resolver chuyển thành DiscoveryLookupException và giữ exception gốc làm cause. Nhờ vậy, lớp gọi có thể xử lý lỗi ở ranh giới nghiệp vụ trong khi log và tracing vẫn giữ được nguyên nhân ban đầu.

Không nên kiểm tra toàn bộ message của exception provider trong unit test nếu message phụ thuộc version hoặc implementation. Kiểm tra loại exception ứng dụng và cause thường ổn định hơn.

## 7. Mock getServices() và các API khác

Nếu lớp cần kiểm tra danh mục service thay vì instance, có thể mock getServices():

~~~java
when(discoveryClient.getServices())
        .thenReturn(Arrays.asList("payment-service", "inventory-service"));

List<String> services = discoveryClient.getServices();

assertThat(services)
        .contains("payment-service", "inventory-service");
~~~

Đoạn trên minh họa cách định nghĩa hành vi mock. Trong test thực tế, hãy gọi lớp nghiệp vụ đang sử dụng DiscoveryClient rồi kiểm tra kết quả của lớp đó. Gọi trực tiếp mock và assert lại chính giá trị đã cấu hình chỉ xác nhận Mockito hoạt động, không kiểm tra logic ứng dụng.

Các phương thức khác cũng được giả lập theo cùng nguyên tắc:

- getInstances(serviceId): trả danh sách ServiceInstance đã định nghĩa.
- getServices(): trả danh sách service ID.
- description(): trả mô tả nếu logic ứng dụng có sử dụng nó.
- probe(): có thể được giả lập ở phiên bản DiscoveryClient hỗ trợ phương thức này.

Chỉ stub những phương thức mà code đang kiểm thử thực sự gọi. Stub dư thừa làm test khó đọc và có thể khiến Mockito báo lỗi strict stubbing.

## 8. Khi nào nên mock ServiceInstance?

ServiceInstance là abstraction mô tả một endpoint đã được discovery tìm thấy. Khi lớp nghiệp vụ chỉ cần URI, có thể mock ServiceInstance và khai báo getUri() như ví dụ trên.

Nếu logic sử dụng nhiều thuộc tính, hãy stub rõ từng thuộc tính:

~~~java
import java.util.Collections;
import java.util.Map;

ServiceInstance instance = mock(ServiceInstance.class);

when(instance.getServiceId()).thenReturn("inventory-service");
when(instance.getHost()).thenReturn("10.0.0.12");
when(instance.getPort()).thenReturn(8081);
when(instance.isSecure()).thenReturn(false);
when(instance.getMetadata()).thenReturn(
        Collections.singletonMap("zone", "zone-a"));
~~~

Một lựa chọn khác là tạo implementation ServiceInstance thật như DefaultServiceInstance nếu API và constructor của phiên bản Spring Cloud Commons đang dùng phù hợp. Object thật có thể làm test dễ đọc hơn khi cần nhiều field; mock phù hợp khi chỉ cần một hoặc hai hành vi.

Không nên mock sâu nhiều tầng đối tượng nếu có thể dùng một value object đơn giản. Mục tiêu là kiểm soát dependency bên ngoài, không biến test thành bản sao của implementation.

## 9. Kiểm tra tương tác với DiscoveryClient

Mockito cho phép xác nhận lớp đang kiểm thử gọi đúng API:

~~~java
verify(discoveryClient).getInstances("inventory-service");
~~~

Có thể kiểm tra không gọi discovery khi đầu vào không hợp lệ, nếu lớp nghiệp vụ có quy tắc validation:

~~~java
import static org.mockito.Mockito.verifyNoInteractions;

verifyNoInteractions(discoveryClient);
~~~

Chỉ dùng verify khi tương tác là một phần của hành vi cần bảo đảm, ví dụ service ID chính xác hoặc tránh gọi registry trong trường hợp không cần thiết. Tránh xác minh mọi lời gọi nội bộ không có ý nghĩa với contract của lớp; test sẽ dễ vỡ khi refactor.

Nếu phương thức được gọi nhiều lần là một phần của yêu cầu, có thể dùng:

~~~java
import static org.mockito.Mockito.times;

verify(discoveryClient, times(1)).getInstances("inventory-service");
~~~

Không cần xác minh số lần gọi nếu kết quả và contract đã đủ chứng minh hành vi.

## 10. Dùng fake tự viết hay Mockito mock?

Hai cách có mục đích gần nhau nhưng khác nhau:

| Cách | Đặc điểm | Phù hợp khi |
|---|---|---|
| Mockito mock | Khai báo hành vi và xác minh tương tác tại từng test | Logic đơn giản, cần mô phỏng exception hoặc nhiều kết quả |
| Fake implementation | Tạo lớp giả có trạng thái và dữ liệu trong bộ nhớ | Nhiều test dùng chung một hành vi discovery giả ổn định |
| DiscoveryClient thật | Gọi provider thật hoặc môi trường test | Integration test, xác minh cấu hình và giao tiếp thực tế |

Tên bài dùng từ “giả lập” theo nghĩa thay dependency discovery thật bằng đối tượng kiểm soát được. Với unit test nhỏ, Mockito thường ngắn gọn. Khi nhiều test cần cùng một registry giả có thể cập nhật dữ liệu, một fake implementation riêng có thể dễ quản lý hơn.

Nếu tự implement DiscoveryClient, hãy triển khai đầy đủ các phương thức abstract của đúng version Spring Cloud Commons. Interface có thể thay đổi giữa các phiên bản; vì vậy không nên sao chép fake implementation từ một dự án dùng release train khác mà chưa kiểm tra API.

## 11. Vì sao không dùng @SpringBootTest cho unit test này?

@SpringBootTest tạo ApplicationContext và có thể kích hoạt auto-configuration của provider discovery. Nếu mục tiêu chỉ là kiểm tra một lớp nhận DiscoveryClient qua constructor, việc khởi tạo toàn bộ context không đem lại giá trị tương ứng.

Có thể dùng @ExtendWith(MockitoExtension.class) để tạo mock và new trực tiếp lớp cần kiểm thử. Cách này:

- Chạy nhanh và không cần registry.
- Không phụ thuộc profile hoặc file cấu hình môi trường.
- Dễ mô phỏng lỗi provider.
- Chỉ kiểm tra hành vi của lớp đang quan tâm.

Nếu muốn kiểm tra Spring wiring, bean condition, auto-configuration hoặc cấu hình Eureka/Consul/Kubernetes, hãy tạo integration test hoặc context test riêng. Không nên gọi một test khởi động context là unit test chỉ vì nó có một mock.

## 12. Các lỗi thường gặp khi kiểm thử

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Test gọi registry thật | Dùng provider bean thật hoặc khởi tạo Spring context | Inject mock DiscoveryClient trực tiếp |
| Kết quả luôn rỗng | Chưa stub getInstances(serviceId) | Khai báo when(...).thenReturn(...) |
| Stub không được dùng | Service gọi service ID khác hoặc API khác | Kiểm tra argument và verify lời gọi |
| NullPointerException trong test | Mock ServiceInstance chưa stub getUri() | Stub thuộc tính mà code sử dụng |
| Nuốt lỗi provider | Code chuyển exception thành danh sách rỗng | Giữ riêng nhánh lỗi và nhánh không có instance |
| Test phụ thuộc thứ tự registry | Giả định instance đầu tiên luôn có ưu tiên | Kiểm thử policy chọn instance rõ ràng |
| Test chậm và khó ổn định | Dùng @SpringBootTest không cần thiết | Dùng MockitoExtension và constructor injection |
| Strict stubbing failure | Khai báo stub nhưng code không sử dụng | Xóa stub dư hoặc sửa đầu vào test |

## 13. Những gì unit test không chứng minh

Mock DiscoveryClient không kiểm tra:

- Eureka Client có kết nối và fetch registry thành công hay không.
- Consul có trả service passing theo health check hay không.
- Kubernetes ServiceAccount có quyền list/watch Service hoặc EndpointSlice hay không.
- DNS, TLS, NetworkPolicy và port của instance có đúng hay không.
- Registry cache có mới hay đã stale.
- LoadBalancer thực tế có chọn instance theo zone hoặc retry policy như cấu hình hay không.

Các nội dung đó cần integration test với provider hoặc môi trường Kubernetes thử nghiệm. Unit test và integration test bổ sung cho nhau: unit test kiểm tra logic của ứng dụng, integration test kiểm tra sự phối hợp với hệ thống discovery thật.

## 14. Quy trình viết unit test

1. Xác định lớp nghiệp vụ đang gọi DiscoveryClient.
2. Bảo đảm DiscoveryClient được inject qua constructor hoặc một seam có thể thay thế.
3. Tạo test bằng JUnit 5 và kích hoạt MockitoExtension.
4. Mock DiscoveryClient và chỉ stub phương thức được code sử dụng.
5. Tạo ServiceInstance mock hoặc value object phù hợp.
6. Kiểm tra kết quả khi có một instance, nhiều instance và danh sách rỗng.
7. Kiểm tra cách ứng dụng xử lý exception từ provider.
8. Xác minh service ID hoặc tương tác quan trọng bằng verify.
9. Chạy test độc lập, bảo đảm không cần Eureka, Consul, Kubernetes hay network.
10. Viết integration test riêng nếu cần xác nhận provider và cấu hình thật.

~~~mermaid
flowchart TD
    A[Chọn lớp nghiệp vụ cần test] --> B[Inject DiscoveryClient]
    B --> C[Mock DiscoveryClient bằng Mockito]
    C --> D[Stub kết quả getInstances]
    D --> E[Thực thi phương thức nghiệp vụ]
    E --> F{Kết quả mong đợi?}
    F -->|Có instance| G[Assert URI hoặc dữ liệu trả về]
    F -->|Danh sách rỗng| H[Assert Optional.empty]
    F -->|Provider exception| I[Assert lỗi ứng dụng và cause]
    G --> J[Verify tương tác cần thiết]
    H --> J
    I --> J
~~~

## 15. Tổng kết

Giả lập DiscoveryClient giúp kiểm thử logic tìm service mà không cần khởi động registry thật. Với JUnit 5 và Mockito, ta có thể kiểm soát kết quả getInstances, tạo ServiceInstance mock, kiểm tra danh sách rỗng, nhiều instance và exception từ provider.

Hãy giữ ranh giới giữa không có instance và không truy vấn được discovery. Dùng constructor injection để thay dependency dễ dàng, chỉ stub các phương thức thực sự được gọi và tránh khởi tạo Spring context khi mục tiêu chỉ là unit test một lớp. Những hành vi liên quan đến mạng, quyền, registry cache và provider cụ thể cần được xác minh bằng integration test riêng.
