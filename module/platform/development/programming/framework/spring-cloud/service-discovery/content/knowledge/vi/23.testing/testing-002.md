# Kiểm thử hợp đồng ServiceInstance và dữ liệu metadata

Trong Spring Cloud, consumer thường nhận danh sách instance thông qua DiscoveryClient. Mỗi phần tử được biểu diễn bằng ServiceInstance, một abstraction của Spring Cloud Commons để che giấu cách registry lưu dữ liệu. Eureka, Consul, ZooKeeper hoặc một discovery client tùy chỉnh có thể dùng cấu trúc đăng ký khác nhau, nhưng consumer cần nhận được thông tin nhất quán về service, host, port, URI, trạng thái bảo mật và metadata.

Nếu adapter ánh xạ sai một trường, service discovery vẫn có thể trả về instance nhưng consumer định tuyến sai host/port, chọn nhầm zone hoặc hiểu sai phiên bản ứng dụng. Vì vậy, cần kiểm thử hợp đồng ở ranh giới giữa registry và ứng dụng, đồng thời kiểm tra metadata như một schema dữ liệu có quy tắc rõ ràng.

Bài này trình bày cách định nghĩa hợp đồng ServiceInstance, viết bộ kiểm thử dùng chung cho nhiều discovery client, xác minh metadata qua registry thật và kiểm thử chính sách consumer dựa trên metadata.

## 1. ServiceInstance là hợp đồng giữa registry và consumer

ServiceInstance mô tả một instance cụ thể của một dịch vụ logic. Consumer không cần biết registry lưu instance dưới application record, service entry hay znode. Consumer chỉ cần nhận được các trường có ý nghĩa và nhất quán.

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa | Ví dụ |
|---|---|---|
| serviceId | Tên logic của dịch vụ | inventory-service |
| instanceId | Định danh một instance cụ thể | inventory-node-a |
| host | Hostname hoặc IP mà consumer có thể truy cập | 10.20.1.11 |
| port | Cổng ứng dụng mà consumer gọi | 8081 |
| isSecure | Cho biết endpoint dùng kết nối bảo mật | true |
| getUri | URI kết hợp scheme, host và port | https://inventory-node-a:8443 |
| metadata | Dữ liệu bổ sung của instance | app.version=2.4.0 |

Trong Spring Cloud Commons, ServiceInstance cung cấp các phương thức như getServiceId(), getHost(), getPort(), isSecure(), getUri() và getMetadata(). Một số phiên bản còn có getInstanceId() với implementation mặc định có thể trả về null. Vì vậy, nếu ứng dụng cần instance ID ổn định để quan sát, chống trùng hoặc định tuyến, hãy quy định đó là yêu cầu hợp đồng của hệ thống và kiểm tra từng adapter.

ServiceInstance không phải bản sao nguyên trạng của record trong registry. Adapter có trách nhiệm chuyển đổi dữ liệu registry sang abstraction này. Contract test nên xác minh kết quả mà consumer thực sự nhận được, không phụ thuộc cấu trúc nội bộ của Eureka, Consul hay ZooKeeper.

## 2. Xác định hợp đồng trước khi viết test

Trước khi kiểm thử, hãy ghi rõ trường nào bắt buộc, trường nào tùy chọn và cách xử lý dữ liệu thiếu hoặc sai.

Ví dụ hợp đồng của inventory-service:

| Trường | Quy tắc của ứng dụng | Kiểm tra |
|---|---|---|
| serviceId | Không rỗng, đúng tên logic đã thống nhất | So sánh với serviceId fixture |
| instanceId | Không rỗng và duy nhất trong cùng service | Không null, không trùng |
| host | Không rỗng, truy cập được từ network của consumer | Kiểm tra định dạng và integration connectivity |
| port | Trong khoảng 1–65535 | Kiểm tra biên |
| isSecure | Phù hợp với endpoint được công bố | Đối chiếu scheme |
| URI | Có scheme, host và port nhất quán | Kiểm tra URI sau khi chuyển đổi |
| metadata | Map không null; khóa và giá trị theo schema | Kiểm tra khóa bắt buộc và kiểu giá trị |

Một số quy tắc trên là hợp đồng cấp ứng dụng, không phải tất cả đều được interface ServiceInstance bắt buộc. Ví dụ, instanceId có thể không có ở implementation dùng giá trị mặc định. Nếu consumer không cần instance ID, không nên tự đặt điều kiện bắt buộc chỉ vì một adapter cụ thể có trường đó.

Hợp đồng cũng cần xác định cách chuẩn hóa serviceId. Một registry có thể hiển thị tên ứng dụng theo chữ hoa, chữ thường hoặc cách chuẩn hóa riêng. Không giả định mọi registry đều trả cùng cách viết. Hãy chọn quy tắc của ứng dụng và kiểm tra adapter chuyển đổi đúng quy tắc đó.

## 3. Metadata là schema dữ liệu, không phải vùng chứa tùy ý

Metadata thường chứa các thông tin phục vụ quan sát hoặc chính sách định tuyến. Ví dụ:

~~~yaml
app.version: "2.4.0"
app.build: "2026.11.24"
routing.zone: "zone-a"
routing.weight: "10"
routing.canary: "false"
contract.metadata-schema-version: "1"
~~~

Khi được chuyển thành ServiceInstance, metadata thường là Map<String, String>. Do đó, cả số và boolean cũng được biểu diễn dưới dạng chuỗi. Consumer cần parse theo quy tắc đã thống nhất, ví dụ weight có thể chuyển sang số nguyên và canary so sánh với chuỗi "true".

Nên đặt tên khóa có namespace như app.version, routing.zone hoặc contract.metadata-schema-version để tránh xung đột giữa các nhóm thông tin. Hãy thống nhất chính xác chữ hoa/chữ thường; Map metadata không tự bảo đảm rằng routing.Zone và routing.zone là cùng một khóa.

Metadata nên có các nhóm:

- **Bắt buộc:** consumer cần để thực hiện định tuyến hoặc tương thích API.
- **Tùy chọn:** chỉ phục vụ quan sát hoặc tính năng phụ.
- **Mở rộng:** khóa mới có thể xuất hiện mà consumer cũ cần bỏ qua an toàn.
- **Không được phép:** password, token, private key, credential hoặc dữ liệu nhạy cảm.

Không dùng metadata thay cho cơ chế xác thực và phân quyền. Một trường canary=true không chứng minh instance được phép nhận traffic canary; đó chỉ là dữ liệu đầu vào cho chính sách đã được cấu hình.

## 4. Phân biệt dữ liệu registration và ServiceInstance sau khi đọc

Luồng dữ liệu thường diễn ra như sau:

~~~mermaid
flowchart LR
    Provider["Provider đăng ký instance"]
    Registry["Eureka / Consul / ZooKeeper"]
    Adapter["DiscoveryClient adapter"]
    Instance["ServiceInstance"]
    Consumer["Consumer / LoadBalancer"]
    Provider -->|"serviceId, host, port, metadata"| Registry
    Registry -->|"Registry record"| Adapter
    Adapter -->|"Chuẩn hóa trường"| Instance
    Instance -->|"Instance list"| Consumer
~~~

Contract test nên kiểm tra ít nhất hai ranh giới:

1. Provider ghi đúng dữ liệu registration.
2. DiscoveryClient trả ServiceInstance đúng với dữ liệu đã đăng ký.

Nếu chỉ kiểm thử constructor của DefaultServiceInstance, ta mới kiểm tra object trong bộ nhớ. Điều đó không chứng minh adapter Eureka hoặc Consul ánh xạ đúng metadata từ registry.

Tương tự, nếu chỉ mock DiscoveryClient để trả một ServiceInstance hợp lệ, ta chưa kiểm tra được dữ liệu registration thực tế đã đi qua registry và quay lại consumer như thế nào.

## 5. Kiểm tra các trường cơ bản của ServiceInstance

Có thể tạo một helper dùng chung để xác minh các bất biến mà mọi adapter phải tuân thủ.

~~~java
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public final class ServiceInstanceContractAssertions {

    private ServiceInstanceContractAssertions() {
    }

    public static void assertBaseContract(ServiceInstance instance) {
        assertThat(instance).isNotNull();
        assertThat(instance.getServiceId()).isNotBlank();
        assertThat(instance.getHost()).isNotBlank();
        assertThat(instance.getPort()).isBetween(1, 65535);
        assertThat(instance.getMetadata()).isNotNull();

        URI uri = instance.getUri();

        assertThat(uri).isNotNull();
        assertThat(uri.getScheme())
                .isEqualTo(instance.isSecure() ? "https" : "http");
        assertThat(uri.getHost()).isEqualTo(instance.getHost());
        assertThat(uri.getPort()).isEqualTo(instance.getPort());
        assertThat(uri.getUserInfo()).isNull();
    }
}
~~~

Helper này thể hiện hợp đồng cụ thể của ứng dụng: URI phải phản ánh host, port và secure; metadata phải là map không null; URI không được nhúng user info hoặc credential.

Nếu hệ thống dùng scheme khác HTTP/HTTPS, URI có base path, port mặc định được lược bỏ hoặc có proxy chuyển TLS, hãy điều chỉnh hợp đồng cho đúng endpoint mà consumer thực sự gọi. Không áp dụng máy móc các assertion này cho một kiến trúc có URI tùy chỉnh.

Cũng cần kiểm tra IPv6 nếu hệ thống hỗ trợ. Host IPv6 phải được mã hóa đúng trong URI, thường có dấu ngoặc vuông ở phần authority. Hãy tạo test với địa chỉ IPv6 thay vì tự ghép chuỗi host và port.

## 6. Kiểm tra instanceId và tính duy nhất

ServiceInstance có thể cung cấp getInstanceId(), nhưng interface có thể có implementation mặc định trả null. Nếu hệ thống cần phân biệt instance để log, trace, deduplicate hoặc lựa chọn endpoint, hãy đưa instanceId vào hợp đồng ứng dụng.

Ví dụ assertion bổ sung:

~~~java
public static void assertIdentifiedInstance(ServiceInstance instance) {
    assertBaseContract(instance);

    assertThat(instance.getInstanceId())
            .as("instanceId phải ổn định và không rỗng")
            .isNotBlank();
}
~~~

Khi service có nhiều replica, cần kiểm tra ID không trùng:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public class InstanceIdAssertions {

    public static void assertUniqueIds(List<ServiceInstance> instances) {
        List<String> ids = instances.stream()
                .map(ServiceInstance::getInstanceId)
                .collect(Collectors.toList());

        assertThat(ids).doesNotContainNull();
        assertThat(ids).doesNotHaveDuplicates();
    }
}
~~~

Đừng dùng host làm instanceId nếu nhiều tiến trình cùng host và port khác nhau. Một định danh thường kết hợp service name, hostname hoặc pod name và port, hoặc dùng ID do nền tảng triển khai cấp.

## 7. Kiểm tra metadata bắt buộc và metadata tùy chọn

Một helper kiểm tra metadata nên xác nhận các khóa mà consumer cần, đồng thời cho phép khóa mở rộng xuất hiện.

~~~java
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public final class MetadataContractAssertions {

    private MetadataContractAssertions() {
    }

    public static void assertInventoryMetadata(ServiceInstance instance) {
        Map<String, String> metadata = instance.getMetadata();

        assertThat(metadata)
                .containsEntry("app.version", "2.4.0")
                .containsEntry("routing.zone", "zone-a")
                .containsEntry("contract.metadata-schema-version", "1");
    }
}
~~~

Không nên so sánh toàn bộ metadata map bằng equals nếu ứng dụng cho phép registry hoặc adapter thêm các khóa mở rộng. So sánh các khóa bắt buộc giúp contract test chịu được việc bổ sung metadata mà không làm hỏng consumer cũ.

Với khóa tùy chọn, kiểm tra cả trường hợp không có khóa. Ví dụ, nếu routing.canary không tồn tại, consumer cần áp dụng mặc định đã định nghĩa hoặc từ chối instance theo chính sách. Không tự coi thiếu metadata là false, zone mặc định hoặc version mới nhất nếu hợp đồng chưa nói như vậy.

Với giá trị dạng số, kiểm tra cả trường hợp hợp lệ và sai định dạng:

~~~java
public static int readWeight(ServiceInstance instance) {
    String value = instance.getMetadata().get("routing.weight");

    if (value == null) {
        return 1;
    }

    try {
        int weight = Integer.parseInt(value);
        if (weight < 1) {
            throw new IllegalArgumentException("routing.weight phải lớn hơn 0");
        }
        return weight;
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("routing.weight không hợp lệ", ex);
    }
}
~~~

Giá trị mặc định 1 chỉ là chính sách ví dụ. Hãy chọn cách xử lý thiếu hoặc sai metadata phù hợp với nghiệp vụ: dùng mặc định an toàn, bỏ qua instance, hoặc báo lỗi cấu hình. Không để lỗi parse âm thầm biến thành giá trị routing không mong muốn.

## 8. Viết bộ contract test dùng chung cho DiscoveryClient

Khi có nhiều adapter registry, nên dùng chung một abstract test suite. Mỗi implementation chỉ cần cung cấp DiscoveryClient và fixture tương ứng.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

abstract class DiscoveryClientContractTest {

    protected abstract DiscoveryClient discoveryClient();

    protected abstract String serviceId();

    protected abstract Map<String, String> requiredMetadata();

    @Test
    void returnsInstancesThatFollowTheContract() {
        List<ServiceInstance> instances =
                discoveryClient().getInstances(serviceId());

        assertThat(instances).isNotNull().isNotEmpty();

        instances.forEach(instance -> {
            ServiceInstanceContractAssertions.assertIdentifiedInstance(instance);
            assertThat(instance.getServiceId()).isEqualTo(serviceId());
            assertThat(instance.getMetadata())
                    .containsAllEntriesOf(requiredMetadata());
        });

        List<String> ids = instances.stream()
                .map(ServiceInstance::getInstanceId)
                .collect(Collectors.toList());

        assertThat(ids).doesNotContainNull();
        assertThat(ids).doesNotHaveDuplicates();
    }

    @Test
    void returnsAnEmptyListForUnknownService() {
        List<ServiceInstance> instances =
                discoveryClient().getInstances("service-does-not-exist");

        assertThat(instances).isNotNull().isEmpty();
    }
}
~~~

Các lớp test cụ thể kế thừa suite này và chuẩn bị dữ liệu trong registry trước khi chạy. Ví dụ, Eureka contract test khởi động Eureka Server test profile; Consul contract test dùng Consul test container; ZooKeeper contract test tạo registration trong môi trường ZooKeeper test.

Không dùng một mock DiscoveryClient cho tất cả lớp con rồi coi đó là kiểm thử adapter. Mục tiêu của suite là chạy cùng assertion trên implementation thật hoặc adapter thật, để phát hiện sự khác biệt trong cách ánh xạ trường.

Nếu một registry không hỗ trợ instanceId hoặc metadata theo cùng cách, hãy định nghĩa adapter chuyển đổi hoặc điều chỉnh hợp đồng cấp ứng dụng. Không bỏ qua assertion chỉ để tất cả test đều xanh.

## 9. Kiểm thử metadata đi qua registry thật

Integration test cần xác minh vòng đi đầy đủ:

1. Khởi động registry thử nghiệm.
2. Đăng ký một provider với serviceId, instanceId, host, port và metadata fixture.
3. Chờ registration xuất hiện theo cơ chế của registry.
4. Gọi DiscoveryClient.getInstances(serviceId) từ consumer test.
5. Tìm instance theo ID thay vì dựa vào vị trí phần tử.
6. Chạy contract assertions trên ServiceInstance trả về.
7. Xác minh metadata bắt buộc giữ nguyên giá trị.
8. Deregister provider hoặc đóng session và dọn dữ liệu sau test.

Không assert thứ tự instance trong danh sách trừ khi adapter hoặc ứng dụng có cam kết rõ ràng về thứ tự. Registry thường không bảo đảm thứ tự ổn định. Hãy tìm instance bằng instanceId hoặc lọc theo thuộc tính duy nhất.

Một integration test nên kiểm tra cả hai hoặc nhiều instance cùng serviceId. Điều đó phát hiện lỗi adapter chỉ trả một instance, gộp nhầm metadata hoặc dùng chung instanceId.

Với registry có cache hoặc eventual consistency, không dùng sleep cố định làm cơ chế chờ duy nhất. Dùng polling có timeout để chờ điều kiện registration xuất hiện; khi hết timeout, test phải báo rõ serviceId và trạng thái mong đợi.

## 10. Mapping metadata giữa các registry

Mỗi registry có mô hình metadata riêng. Contract test cần kiểm tra dữ liệu sau khi adapter chuẩn hóa sang ServiceInstance.

| Registry | Nơi lưu dữ liệu thường gặp | Điều cần kiểm thử |
|---|---|---|
| Eureka | Instance metadata map | Khóa và giá trị metadata được trả về đúng |
| Consul | Service metadata và tags | Metadata map có được giữ; tags có được ánh xạ theo quy ước ứng dụng không |
| ZooKeeper | Dữ liệu registration trong znode | Payload được giải mã và chuyển thành metadata đúng |
| Custom registry | Record riêng của adapter | Mapping không làm mất hoặc đổi kiểu dữ liệu |

Ví dụ cấu hình metadata cho Eureka:

~~~yaml
eureka:
  instance:
    metadata-map:
      app.version: "2.4.0"
      routing.zone: "zone-a"
      contract.metadata-schema-version: "1"
~~~

Ví dụ cấu hình metadata cho Consul:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        metadata:
          app.version: "2.4.0"
          routing.zone: "zone-a"
          contract.metadata-schema-version: "1"
~~~

Các property và cách ánh xạ phụ thuộc phiên bản Spring Cloud starter. Với Consul, tags và metadata là hai khái niệm khác nhau; không giả định tag tự động trở thành một entry trong metadata map. Với ZooKeeper, hãy xác minh cách starter lưu và đọc payload ở phiên bản đang dùng.

Contract test nên khẳng định dữ liệu cuối cùng mà consumer nhìn thấy, thay vì yêu cầu mọi registry lưu cùng một cấu trúc nội bộ.

## 11. Kiểm tra metadata có ảnh hưởng đến consumer policy

Metadata không tự động làm Spring Cloud LoadBalancer chọn instance theo zone, version hoặc canary. Nếu ứng dụng muốn dùng metadata để lọc hoặc xếp hạng, phải có chính sách cụ thể và kiểm thử riêng.

Ví dụ hàm lọc instance theo zone:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;

public class ZoneRoutingPolicy {

    public List<ServiceInstance> filterByZone(
            List<ServiceInstance> instances,
            String requiredZone) {

        return instances.stream()
                .filter(instance -> requiredZone.equals(
                        instance.getMetadata().get("routing.zone")))
                .collect(Collectors.toList());
    }
}
~~~

Test cho policy:

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.DefaultServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

class ZoneRoutingPolicyTest {

    @Test
    void selectsOnlyInstancesInRequestedZone() {
        ServiceInstance zoneA = new DefaultServiceInstance(
                "inventory-a",
                "inventory-service",
                "10.20.1.11",
                8081,
                false,
                Collections.singletonMap("routing.zone", "zone-a"));

        ServiceInstance zoneB = new DefaultServiceInstance(
                "inventory-b",
                "inventory-service",
                "10.20.2.12",
                8081,
                false,
                Collections.singletonMap("routing.zone", "zone-b"));

        List<ServiceInstance> selected =
                new ZoneRoutingPolicy().filterByZone(
                        Arrays.asList(zoneA, zoneB), "zone-a");

        assertThat(selected)
                .extracting(ServiceInstance::getInstanceId)
                .containsExactly("inventory-a");
    }
}
~~~

Ví dụ dùng DefaultServiceInstance để kiểm thử policy trong bộ nhớ. Nó không thay thế integration test xác minh metadata được đọc đúng từ registry. Trong thực tế, chính sách có thể được triển khai bằng ServiceInstanceListSupplier hoặc thành phần LoadBalancer tương ứng với phiên bản Spring Cloud.

Cần test thêm khi không có instance ở zone yêu cầu: ứng dụng có được fallback sang zone khác, trả lỗi hay chờ? Đây là quyết định nghiệp vụ, không nên để hành vi ngẫu nhiên của list quyết định.

## 12. Kiểm thử scheme, TLS và địa chỉ instance

Hợp đồng ServiceInstance phải phản ánh endpoint mà consumer thực sự gọi. Nếu instance yêu cầu HTTPS, isSecure() và scheme của URI cần nhất quán.

Các trường hợp nên kiểm thử:

- HTTP instance: isSecure=false và URI dùng http.
- HTTPS instance: isSecure=true và URI dùng https.
- Port TLS tùy chỉnh: URI giữ đúng port đã đăng ký.
- Hostname: consumer phân giải được từ network của nó.
- IPv4/IPv6: URI được tạo hợp lệ.
- TLS termination: xác định rõ consumer kết nối đến proxy HTTPS hay provider HTTP nội bộ.

Không giả định mọi HTTPS đều dùng port 443 hoặc mọi HTTP đều dùng port 80. Registry cần trả đúng port thực tế mà consumer phải gọi.

Contract test cấp object chỉ xác nhận host/port/scheme nhất quán. Integration test mạng cần thử kết nối từ môi trường consumer để chứng minh địa chỉ quảng bá có route và firewall phù hợp.

## 13. Kiểm tra metadata tương thích khi nâng cấp phiên bản

Metadata là một schema có thể thay đổi theo thời gian. Nếu consumer và provider được triển khai độc lập, cần duy trì khả năng tương thích giữa phiên bản cũ và mới.

Một số quy tắc hữu ích:

- Thêm khóa tùy chọn mới thường an toàn nếu consumer cũ bỏ qua khóa chưa biết.
- Không đổi ý nghĩa của khóa hiện có mà vẫn giữ nguyên tên.
- Nếu đổi kiểu hoặc ý nghĩa dữ liệu, tăng metadata-schema-version.
- Khi xóa khóa, kiểm tra tất cả consumer còn sử dụng khóa đó.
- Với khóa bắt buộc, xác định hành vi khi thiếu hoặc sai định dạng.
- Không dùng metadata làm nơi truyền dữ liệu nghiệp vụ lớn hoặc thường xuyên thay đổi.

Ví dụ, consumer v1 chỉ cần app.version và routing.zone. Provider mới bổ sung routing.canary. Consumer v1 nên bỏ qua khóa mới; consumer v2 có thể sử dụng nó nếu policy đã được triển khai. Contract test cần xác nhận cả dữ liệu cũ và dữ liệu mở rộng.

Có thể duy trì fixture cho từng schema version:

| Schema | Khóa bắt buộc | Khóa tùy chọn |
|---|---|---|
| 1 | app.version, routing.zone | routing.weight |
| 2 | app.version, routing.zone, contract.metadata-schema-version | routing.weight, routing.canary |

Không để consumer tự đoán schema version từ việc một khóa có xuất hiện hay không. Khai báo version rõ ràng giúp kiểm thử và triển khai có kiểm soát hơn.

## 14. Kiểm tra metadata không chứa secret

Registry thường có nhiều consumer và công cụ quản trị có quyền đọc service metadata. Vì vậy, metadata không phải nơi lưu credential.

Có thể thêm một assertion kiểm tra tên khóa cấm:

~~~java
import java.util.Locale;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

import static org.assertj.core.api.Assertions.assertThat;

public class MetadataSecurityAssertions {

    public static void assertNoSecretKeys(ServiceInstance instance) {
        Map<String, String> metadata = instance.getMetadata();

        assertThat(metadata.keySet()).allSatisfy(key -> {
            String normalized = key.toLowerCase(Locale.ROOT);

            assertThat(normalized)
                    .doesNotContain("password")
                    .doesNotContain("secret")
                    .doesNotContain("token")
                    .doesNotContain("private-key")
                    .doesNotContain("credential");
        });
    }
}
~~~

Đây là lớp kiểm tra bổ sung dựa trên quy ước tên khóa, không thể chứng minh mọi giá trị đều vô hại. Cần giới hạn schema metadata theo allowlist và review dữ liệu đăng ký. Không đưa thông tin xác thực vào tag, hostname, serviceId hoặc URI.

## 15. Các lỗi thường gặp trong contract test

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ServiceInstance có serviceId đúng nhưng host sai | Adapter lấy địa chỉ node hoặc địa chỉ nội bộ không truy cập được | Kiểm tra mapping advertised address và thử từ consumer |
| URI dùng HTTP dù instance yêu cầu HTTPS | isSecure hoặc scheme bị ánh xạ sai | Kiểm tra registration và URI contract |
| Metadata bị mất sau khi đọc registry | Adapter không ánh xạ metadata hoặc dùng nhầm tags | Kiểm tra registry record và mapping |
| Metadata có khóa nhưng giá trị sai kiểu | Registry chuyển số/boolean thành chuỗi hoặc consumer parse không đúng | Chuẩn hóa schema string và test parser |
| Hai instance có cùng ID | Registration tạo ID không duy nhất | Tạo ID theo host/pod và port hoặc ID nền tảng |
| Test phụ thuộc thứ tự danh sách | Registry không cam kết thứ tự instance | Tìm theo instanceId và assert tập kết quả |
| Test mock pass nhưng production fail | Chưa kiểm tra adapter và registry thật | Bổ sung integration test |
| Consumer không lọc theo zone/version | Metadata không tự kích hoạt routing policy | Kiểm thử ServiceInstanceListSupplier hoặc policy tùy chỉnh |
| Test thất bại ngẫu nhiên | Registry cache hoặc eventual consistency | Chờ điều kiện bằng polling có timeout |
| Metadata lộ credential | Không có schema/allowlist | Cấm secret và kiểm tra security contract |

## 16. Quy trình xây dựng bộ kiểm thử

Thực hiện theo thứ tự sau:

1. Xác định serviceId, instanceId và metadata schema mà ứng dụng yêu cầu.
2. Viết helper assertion cho các trường cơ bản của ServiceInstance.
3. Viết assertion riêng cho metadata bắt buộc, tùy chọn và dữ liệu cấm.
4. Tạo abstract contract test cho DiscoveryClient.
5. Viết lớp test cho từng adapter Eureka, Consul, ZooKeeper hoặc custom registry.
6. Chạy integration test với registry thử nghiệm và đăng ký nhiều instance.
7. Xác minh metadata đi từ provider registration qua registry đến consumer.
8. Kiểm thử URI, TLS, host/port và khả năng kết nối từ network của consumer.
9. Kiểm thử policy lọc instance theo zone, version hoặc canary nếu ứng dụng sử dụng metadata.
10. Kiểm thử dữ liệu thiếu, sai định dạng, khóa mở rộng và schema version cũ/mới.
11. Kiểm thử deregistration và xác nhận instance không còn trong kết quả sau khi registry cập nhật.
12. Chạy contract suite trong CI cho mọi adapter được hỗ trợ.

Có thể chạy unit contract test ở mỗi pull request. Integration test với registry thật có thể chạy theo profile riêng hoặc trong pipeline phù hợp. Test cần dọn registration sau khi chạy để không làm nhiễu các lần kiểm thử tiếp theo.

## 17. Checklist hoàn tất

Trước khi coi ServiceInstance contract đã được bảo vệ, xác nhận:

1. serviceId là tên logic ổn định và có quy tắc chuẩn hóa rõ ràng.
2. instanceId được kiểm tra nếu ứng dụng yêu cầu định danh từng replica.
3. host và port là địa chỉ mà consumer có thể truy cập.
4. isSecure và URI scheme nhất quán.
5. metadata không null theo hợp đồng ứng dụng và tuân theo schema.
6. Khóa bắt buộc có giá trị chính xác; khóa tùy chọn có quy tắc mặc định rõ ràng.
7. Metadata mở rộng không làm hỏng consumer cũ.
8. Metadata không chứa secret hoặc credential.
9. Mỗi adapter registry chạy cùng một contract test suite.
10. Integration test xác minh dữ liệu đi qua registry thật.
11. Consumer policy dựa trên metadata được kiểm thử riêng.
12. Test không phụ thuộc thứ tự instance hoặc thời điểm cập nhật ngẫu nhiên.

Điểm cốt lõi là: **ServiceInstance là hợp đồng dữ liệu mà consumer nhận được sau khi discovery adapter chuyển đổi record của registry; metadata là một schema cần được quản lý và kiểm thử như API.** Hãy kiểm tra cả trường cơ bản, metadata và hành vi định tuyến để thay đổi registry không âm thầm làm sai consumer.

