# Đọc serviceId, instanceId, host, port, URI và metadata

Trong Spring Cloud Service Discovery, consumer tra cứu một service ID để nhận danh sách các instance đang được công bố. Mỗi instance chứa thông tin giúp consumer nhận diện dịch vụ, phân biệt từng bản chạy, xác định địa chỉ kết nối và hiểu thêm bối cảnh triển khai. Các trường thường cần đọc là service ID, instance ID, host, port, URI và metadata.

Những dữ liệu này là góc nhìn mà discovery client nhận được từ registry tại thời điểm truy vấn. Chúng có thể trễ so với trạng thái tiến trình hoặc mạng thực tế do heartbeat, health check, cache và chu kỳ đồng bộ. Vì vậy, cần đọc đúng ý nghĩa từng trường và xử lý trường hợp dữ liệu thiếu hoặc đã cũ.

## 1. serviceId và instanceId là hai cấp định danh khác nhau

### serviceId: tên logic của dịch vụ

`serviceId` là tên dùng để nhóm các instance cùng cung cấp một dịch vụ logic. Ví dụ:

- `inventory-service`: dịch vụ quản lý tồn kho.
- `payment-service`: dịch vụ xử lý thanh toán.
- `order-service`: dịch vụ quản lý đơn hàng.

Một dịch vụ có thể chạy nhiều replica. Các replica tương thích thường đăng ký dưới cùng một `serviceId` để consumer chỉ cần tra cứu một tên ổn định.

Trong ứng dụng Spring Boot, `spring.application.name` thường là nguồn mặc định để tạo tên dịch vụ khi discovery client đăng ký ứng dụng. Tuy nhiên, provider có thể cho phép override service name bằng cấu hình riêng. Tên mà consumer tra cứu phải khớp với tên thực tế được công bố trong registry.

### instanceId: định danh của một lần chạy cụ thể

`instanceId` phân biệt một instance với các instance khác thuộc cùng service ID. Ví dụ:

| serviceId | instanceId | host | port |
|---|---|---|---:|
| `inventory-service` | `inventory-pod-a81f` | `10.20.1.11` | 8080 |
| `inventory-service` | `inventory-pod-b92c` | `10.20.1.12` | 8080 |
| `inventory-service` | `inventory-pod-c73d` | `10.20.1.13` | 8080 |

Ba instance cùng phục vụ `inventory-service`, nhưng có ID và địa chỉ riêng. Registry dùng định danh instance để cập nhật heartbeat, trạng thái hoặc hủy đăng ký đúng bản chạy.

Cách tạo instance ID tùy provider và môi trường. Nó có thể dựa trên hostname, port, application name, IP, pod UID hoặc một giá trị được cấu hình riêng. Một instance ID nên đủ duy nhất trong phạm vi registry và ổn định trong suốt vòng đời của registration đó. Không nên mặc định instance ID luôn là hostname hoặc luôn có cùng định dạng giữa Eureka và Consul.

**Phân biệt quan trọng:** service ID trả lời “đây là dịch vụ logic nào?”, còn instance ID trả lời “đây là bản chạy cụ thể nào?”. Không dùng instance ID làm tên tra cứu chung khi muốn gọi toàn bộ replica.

## 2. DiscoveryClient đọc danh sách instance như thế nào?

Spring Cloud Commons cung cấp abstraction `DiscoveryClient` để consumer truy vấn registry. Hai thao tác thường dùng là:

- `getServices()`: lấy danh sách service ID mà discovery client hiện nhìn thấy.
- `getInstances(serviceId)`: lấy danh sách instance được công bố dưới service ID đó.

Ví dụ, một ứng dụng có thể kiểm tra các dịch vụ đang được khám phá:

```java
List<String> serviceIds = discoveryClient.getServices();

for (String serviceId : serviceIds) {
    List<ServiceInstance> instances =
        discoveryClient.getInstances(serviceId);

    log.info("serviceId={}, instanceCount={}",
        serviceId, instances.size());
}
```

`getServices()` hữu ích cho quan sát hoặc công cụ quản trị. Trong luồng nghiệp vụ, ứng dụng thường biết trước service ID cần gọi và truy vấn trực tiếp `getInstances(serviceId)`.

Danh sách có thể rỗng nếu provider chưa đăng ký, consumer tra cứu sai tên, instance chưa healthy, dữ liệu chưa đồng bộ hoặc registry đang gặp sự cố. Không nên coi danh sách rỗng là bằng chứng duy nhất rằng ứng dụng provider đã tắt. Cần kiểm tra registry, log discovery client, health check và kết nối mạng.

## 3. ServiceInstance và các trường kết nối

`DiscoveryClient.getInstances()` trả về các đối tượng `ServiceInstance`. Đây là abstraction đại diện cho một instance, độc lập tương đối với Eureka, Consul hoặc discovery provider cụ thể.

| Thuộc tính | Ý nghĩa | Cách sử dụng |
|---|---|---|
| `getServiceId()` | Tên logic của dịch vụ | Kiểm tra instance thuộc dịch vụ nào |
| Instance ID | Định danh một registration cụ thể | Phân biệt replica và đối chiếu log |
| `getHost()` | Host/IP mà provider công bố | Chẩn đoán địa chỉ instance |
| `getPort()` | Cổng dịch vụ được công bố | Kết nối tới listener của ứng dụng |
| `isSecure()` | Instance dùng kết nối bảo mật theo registration | Xác định scheme HTTP/HTTPS |
| `getUri()` | URI cơ sở của instance | Dùng làm địa chỉ đích |
| `getMetadata()` | Thuộc tính bổ sung dạng key/value | Lọc hoặc định tuyến theo zone, version, tag |

Các phương thức phổ biến của `ServiceInstance` gồm `getServiceId()`, `getHost()`, `getPort()`, `isSecure()`, `getUri()` và `getMetadata()`. Khả năng đọc native instance ID phụ thuộc phiên bản Spring Cloud Commons và implementation của provider. Nếu API đang dùng có accessor instance ID, có thể đọc qua accessor đó; nếu không, dùng API cụ thể của provider hoặc quy ước metadata do hệ thống chủ động công bố. Không giả định mọi `ServiceInstance` đều có cùng cách lấy native instance ID.

### Host và port

`host` là địa chỉ mà provider quảng bá cho consumer. Nó không nhất thiết giống địa chỉ bind nội bộ mà tiến trình dùng để mở socket. Ví dụ, ứng dụng có thể bind vào `0.0.0.0` nhưng phải quảng bá địa chỉ IP của container hoặc hostname mà consumer có thể truy cập.

`port` là cổng dịch vụ của instance, không phải cổng registry server. Nếu ứng dụng chạy sau NAT, container network, reverse proxy hoặc port mapping, cần công bố đúng cổng mà consumer nhìn thấy được.

```text
Process bind:       0.0.0.0:8080
Advertised address: 10.20.1.11:8080
Consumer network:   10.20.1.11:8080
```

Nếu registry công bố `localhost` cho một instance ở máy khác, consumer sẽ kết nối tới chính máy consumer thay vì máy provider. Đây là lỗi cấu hình địa chỉ quảng bá thường gặp.

### URI và scheme

`getUri()` trả về URI kết nối được xây dựng từ thông tin instance, thường có dạng:

```text
http://10.20.1.11:8080
https://inventory.internal:8443
```

URI là địa chỉ cơ sở của instance. Nó thường chưa chứa path API nghiệp vụ như `/api/items/42`. Ứng dụng cần ghép path phù hợp với hợp đồng HTTP của provider.

Nên dùng `getUri()` khi cần địa chỉ kết nối hoàn chỉnh thay vì tự nối chuỗi host và port. Điều này giúp tôn trọng scheme bảo mật mà implementation công bố. Tuy nhiên, URI hợp lệ về cú pháp chưa bảo đảm địa chỉ có thể truy cập; DNS, routing, firewall, TLS và chính sách mạng vẫn phải cho phép kết nối.

`isSecure()` cho biết registration đánh dấu instance là bảo mật hay không. `getUri()` thường phản ánh thông tin này qua scheme `https` hoặc `http`. Một số phiên bản có thêm `getScheme()` để đọc scheme trực tiếp.

Không suy ra rằng TLS chắc chắn hoạt động chỉ vì `isSecure()` trả về `true`. Consumer vẫn cần trust store, chứng thư hợp lệ, hostname verification và cấu hình TLS phù hợp. Trạng thái secure trong registration là thông tin định tuyến; nó không thay thế xác thực kết nối.

## 4. Đọc metadata

`metadata` là tập hợp key/value do provider hoặc hệ thống triển khai gắn vào registration. Trong `ServiceInstance`, metadata thường được biểu diễn bằng `Map<String, String>`.

Ví dụ:

```yaml
metadata:
  zone: ap-southeast-1a
  version: v2
  region: ap-southeast-1
  canary: "false"
  protocol: http
```

Consumer có thể đọc metadata để ưu tiên instance cùng zone, chọn phiên bản tương thích, tách traffic canary, chọn instance có năng lực phù hợp hoặc phân tích phân bố instance theo vùng.

```java
Map<String, String> metadata = instance.getMetadata();

String zone = metadata.get("zone");
String version = metadata.get("version");
String canary = metadata.get("canary");
```

Metadata không có schema thống nhất giữa mọi provider. Eureka và Consul có thể hỗ trợ metadata nhưng cách cấu hình, giới hạn kích thước, kiểu dữ liệu và cách cập nhật phụ thuộc implementation. Hãy chuẩn hóa tên key, kiểu biểu diễn và ý nghĩa trong hệ thống của mình.

Một số nguyên tắc:

- Metadata nên chứa thông tin mô tả hoặc định tuyến, không chứa mật khẩu, token hay private key.
- Giá trị thường là chuỗi; nếu biểu diễn boolean hoặc số, consumer phải parse và xử lý giá trị thiếu.
- Không mặc định mọi instance đều có cùng key.
- Tránh dùng metadata thay cho service ID nếu thông tin đó thực chất là danh tính dịch vụ.
- Khi thay đổi metadata, xác định cách provider cập nhật registration và thời gian consumer nhận được dữ liệu mới.

Metadata là dữ liệu đầu vào của quyết định định tuyến. Nếu consumer tin metadata mà không kiểm soát nguồn ghi, một instance có thể tự khai báo zone hoặc version không đúng và làm sai chính sách chọn đích.

## 5. Ví dụ đọc đầy đủ thông tin bằng DiscoveryClient

Ví dụ sau truy vấn các instance của `inventory-service` và ghi lại thông tin kết nối. Đoạn mã xử lý trường hợp danh sách rỗng và metadata không có key tùy chọn.

```java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryInstanceInspector {

    private static final Logger log =
        LoggerFactory.getLogger(InventoryInstanceInspector.class);

    private final DiscoveryClient discoveryClient;

    public InventoryInstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void inspect() {
        String requestedServiceId = "inventory-service";

        List<ServiceInstance> instances =
            discoveryClient.getInstances(requestedServiceId);

        if (instances.isEmpty()) {
            log.warn("No instances found for serviceId={}",
                requestedServiceId);
            return;
        }

        for (ServiceInstance instance : instances) {
            String serviceId = instance.getServiceId();
            String host = instance.getHost();
            int port = instance.getPort();
            boolean secure = instance.isSecure();
            URI uri = instance.getUri();

            Map<String, String> metadata = instance.getMetadata();
            String zone = metadata.get("zone");
            String version = metadata.get("version");

            log.info(
                "serviceId={}, host={}, port={}, secure={}, uri={}, zone={}, version={}, metadata={}",
                serviceId, host, port, secure, uri, zone, version, metadata
            );
        }
    }
}
```

Đoạn mã này đọc các thuộc tính mà abstraction `ServiceInstance` cung cấp. Nó không tự giả định native instance ID có mặt trong metadata. Nếu ứng dụng cần ghi instance ID vào log, hãy lấy từ accessor được phiên bản/provider hỗ trợ hoặc bổ sung một metadata key theo quy ước đã thống nhất.

Trong production, tránh log toàn bộ metadata nếu provider có thể đưa dữ liệu nhạy cảm vào đó. Nên chọn các key được phép quan sát và che giá trị nhạy cảm trước khi ghi log.

## 6. Đọc native instanceId đúng cách

Native instance ID được tạo và quản lý bởi discovery provider. Nó có thể xuất hiện trong dashboard hoặc API của registry nhưng không nhất thiết được chuẩn hóa giống nhau giữa các provider.

- **Eureka:** instance ID nằm trong thông tin instance của Eureka; định dạng thường do Eureka client và cấu hình instance quyết định.
- **Consul:** mỗi service registration có ID riêng do agent/client cung cấp hoặc tạo theo cấu hình; service name và registration ID là hai khái niệm khác nhau.
- **Provider khác:** có thể dùng UUID, hostname, pod UID hoặc định danh riêng.

Khi cần native ID, hãy dùng API/adapter cụ thể của provider đang triển khai và kiểm tra đúng phiên bản dependency. Tránh ép kiểu mọi đối tượng `ServiceInstance` sang class Eureka hoặc Consul trong mã nghiệp vụ chung, vì điều đó làm ứng dụng phụ thuộc nhà cung cấp.

Nếu cần một định danh portable để consumer đọc được qua mọi implementation, có thể quy ước thêm metadata key như `instance-key` trong registration. Giá trị này do hệ thống quản lý và phải được ghi nhất quán ở mọi provider. Tuy nhiên, `instance-key` là metadata do ứng dụng quy ước, không nhất thiết trùng native ID mà registry dùng để hủy đăng ký registration.

Ví dụ đọc metadata key đã được chuẩn hóa:

```java
Map<String, String> metadata = instance.getMetadata();
String instanceKey = metadata.get("instance-key");

if (instanceKey == null || instanceKey.isBlank()) {
    log.warn("Instance has no portable instance-key");
} else {
    log.info("portableInstanceKey={}", instanceKey);
}
```

Đoạn mã trên đọc ID do ứng dụng quy ước, không khẳng định đó là native ID của Eureka hoặc Consul. Khi cần ID native để gọi API quản trị hoặc hủy registration, hãy dùng đúng adapter và API của provider.

## 7. Đối chiếu dữ liệu giữa provider, registry và consumer

Một instance có thể có ba góc nhìn:

1. **Cấu hình provider:** địa chỉ và metadata mà ứng dụng dự định công bố.
2. **Bản ghi registry:** registration mà registry hiện lưu và trạng thái health/lease của nó.
3. **Kết quả consumer:** danh sách `ServiceInstance` mà discovery client trả về, có thể chịu ảnh hưởng của cache hoặc refresh interval.

Ba góc nhìn không nhất thiết giống nhau ngay lập tức. Ví dụ, ứng dụng đã đổi port nhưng registration cũ chưa được thay thế; registry đã cập nhật nhưng client cache vẫn chứa địa chỉ trước đó; hoặc host được quảng bá không thể truy cập từ network của consumer.

Khi điều tra, hãy đối chiếu cùng một instance ID và service ID qua cả ba nơi. Kiểm tra các trường theo thứ tự:

- Service ID có trùng tên mà consumer yêu cầu không?
- Instance ID có duy nhất và thuộc đúng service không?
- Host có phải địa chỉ mà consumer có thể route tới không?
- Port có đúng cổng ứng dụng đang lắng nghe và được expose không?
- URI có đúng scheme và port không?
- Metadata có key/value đúng quy ước và phản ánh đúng môi trường không?
- Trạng thái health có cho phép instance xuất hiện trong kết quả discovery không?

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `getInstances()` trả danh sách rỗng | Sai service ID, chưa đăng ký, health check lỗi hoặc registry chưa đồng bộ | Kiểm tra tên trong registry, log client và health |
| Hai instance có cùng instance ID | Cấu hình ID không duy nhất hoặc nhiều replica dùng chung giá trị cố định | Tạo ID riêng cho từng registration |
| Host trả về là `localhost` | Client quảng bá loopback thay vì địa chỉ có thể truy cập từ consumer | Cấu hình advertised host/IP phù hợp |
| Port trả về không kết nối được | Công bố sai port, port mapping hoặc network policy | Đối chiếu listener, container port và service port |
| URI dùng sai scheme | Trạng thái secure hoặc cấu hình HTTPS không đúng | Kiểm tra registration và cấu hình TLS |
| Metadata thiếu key | Provider không công bố key hoặc registration cũ chưa refresh | Xử lý null/default và kiểm tra cấu hình provider |
| Metadata khác giữa các replica | Các replica dùng cấu hình/profile khác nhau | Chuẩn hóa cấu hình và kiểm tra rollout |
| Consumer vẫn gọi địa chỉ cũ | Cache hoặc refresh discovery chưa cập nhật | Kiểm tra cache, refresh interval và trạng thái registry |

Đừng dùng giá trị metadata tùy chọn mà không kiểm tra null. Ví dụ, nếu code parse `metadata.get("weight")` thành số mà key chưa tồn tại hoặc chứa chuỗi không hợp lệ, consumer có thể phát sinh lỗi ngay trong luồng chọn instance.

## 9. An toàn khi sử dụng thông tin instance

Thông tin từ registry là đầu vào cho quyết định kết nối. Cần áp dụng các nguyên tắc:

- Chỉ tin registry được bảo vệ và các client có quyền đăng ký hợp lệ.
- Không đưa bí mật vào metadata hoặc log.
- Xác thực kết nối tới instance bằng TLS và cơ chế xác thực dịch vụ phù hợp; không coi service ID là bằng chứng danh tính.
- Không cho phép client tùy ý chọn host/port từ metadata chưa được kiểm chứng, tránh biến dữ liệu registry thành đường kết nối tới địa chỉ ngoài dự kiến.
- Giới hạn timeout và xử lý lỗi kết nối vì instance có thể biến mất sau khi được khám phá.
- Khi dùng metadata để chọn phiên bản hoặc zone, kiểm tra giá trị và có fallback an toàn nếu không có instance phù hợp.

Danh sách instance là một ảnh chụp tại thời điểm truy vấn, không phải cam kết instance sẽ còn sống đến lúc request hoàn tất. Consumer vẫn phải có timeout, retry có giới hạn, circuit breaker hoặc cơ chế phục hồi phù hợp.

## 10. Checklist đọc ServiceInstance

Trước khi dùng dữ liệu discovery trong mã ứng dụng, hãy kiểm tra:

1. Đã tra cứu đúng service ID chưa?
2. Có xử lý danh sách instance rỗng không?
3. Có phân biệt service ID với instance ID không?
4. Có hiểu host và port là địa chỉ được quảng bá cho consumer không?
5. Có dùng URI và scheme đúng cách không?
6. Có xử lý metadata thiếu hoặc không hợp lệ không?
7. Có tránh phụ thuộc API provider-specific trong mã nghiệp vụ chung không?
8. Có đối chiếu registry với dữ liệu consumer khi điều tra lỗi không?
9. Có bảo vệ metadata và log khỏi dữ liệu nhạy cảm không?
10. Có timeout và xử lý trường hợp instance biến mất sau khi tra cứu không?

Khi đọc đúng service ID, instance ID, host, port, URI và metadata, consumer có đủ ngữ cảnh để hiểu một instance đang đại diện cho dịch vụ nào, kết nối tới đâu và có thể áp dụng quy tắc định tuyến nào. Những trường này cũng là dữ liệu quan trọng để chẩn đoán sai lệch giữa provider, registry và consumer trong hệ thống Spring Cloud Service Discovery.
