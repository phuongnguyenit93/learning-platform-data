# Loại interface bằng ignoredInterfaces

Một máy chạy ứng dụng Spring Cloud có thể có nhiều network interface: card mạng LAN, Wi-Fi, loopback, VPN, bridge của Docker, adapter ảo của Hyper-V hoặc interface do nền tảng container tạo ra. Khi ứng dụng tự xác định hostname và IP để đăng ký với service registry, interface được chọn có thể không phải interface mà các service khác truy cập được.

Spring Cloud Commons cung cấp `spring.cloud.inetutils.ignored-interfaces` để bỏ qua các interface có tên khớp với danh sách Java regular expression. Ví dụ, có thể bỏ qua `docker0` và các interface bắt đầu bằng `veth`. Thuộc tính này giúp `InetUtils` chọn địa chỉ phù hợp hơn khi xây dựng thông tin host cho ứng dụng.

Bài học thuộc chương **Định danh và mạng** của module **SPRING_CLOUD_CORE**. Ta sẽ xem cách `ignoredInterfaces` hoạt động trong `InetUtils`, cách viết regex đúng, cách phân biệt nó với `preferredNetworks`, cách quan sát interface thực tế trên máy và cách kiểm tra IP mà ứng dụng công bố.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một máy có nhiều interface có thể khiến ứng dụng đăng ký sai IP.
- Xác định vai trò của `InetUtils` và `InetUtilsProperties` trong Spring Cloud Commons.
- Cấu hình danh sách `spring.cloud.inetutils.ignored-interfaces` trong YAML hoặc properties.
- Viết Java regular expression để khớp tên interface chính xác hoặc theo tiền tố.
- Phân biệt tên interface với địa chỉ IP và hostname.
- Phân biệt `ignored-interfaces` với `preferred-networks` và `use-only-site-local-interfaces`.
- Kiểm tra interface, display name, trạng thái UP và các địa chỉ mà JVM nhìn thấy.
- Hiểu ảnh hưởng của network namespace trong Docker/Kubernetes và các adapter VPN/ảo.
- Nhận diện trường hợp fallback có thể vẫn trả về địa chỉ không mong muốn.
- Xác minh `spring.cloud.client.hostname` và `spring.cloud.client.ip-address` trước khi đăng ký dịch vụ.

## 2. Vấn đề khi máy có nhiều network interface

Một máy chủ có thể có nhiều adapter hoạt động đồng thời. Ví dụ:

| Interface | Mục đích thường gặp | Địa chỉ ví dụ |
| --- | --- | --- |
| `lo` | Loopback nội bộ | `127.0.0.1` |
| `eth0` hoặc `ens192` | Mạng chính của máy chủ | `10.20.1.15` |
| `docker0` | Bridge của Docker trên host | `172.17.0.1` |
| `veth8a1b2c` | Cặp virtual Ethernet cho container | `172.18.0.1` |
| `tun0` | VPN tunnel | `10.8.0.12` |
| `tailscale0` | Mạng overlay | `100.64.0.8` |
| `vEthernet (Default Switch)` | Adapter ảo trên Windows/Hyper-V | Phụ thuộc cấu hình |

Nếu ứng dụng chọn IP của interface chỉ dùng cho bridge nội bộ, service registry có thể lưu một địa chỉ mà các service ở mạng khác không truy cập được. Client tra cứu service sẽ nhận endpoint sai và kết nối thất bại.

Ví dụ, ứng dụng chạy trên host có:

- `eth0` với IP `10.20.1.15`, được các service trong VPC truy cập.
- `docker0` với IP `172.17.0.1`, chỉ phục vụ bridge Docker cục bộ.
- `tun0` với IP `10.8.0.12`, dành cho VPN quản trị.

Nếu `InetUtils` chọn `172.17.0.1`, Eureka/Consul hoặc một thành phần đăng ký khác có thể công bố sai địa chỉ cho service consumer.

### 2.1. Vì sao không thể mặc định dùng hostname của máy?

Hostname có thể phân giải thành địa chỉ khác nhau tùy DNS, file hosts, network namespace hoặc cấu hình nhiều card mạng. Một máy cũng có thể có nhiều địa chỉ IPv4 và IPv6.

Spring Cloud Commons cung cấp abstraction `InetUtils` để tìm thông tin host phù hợp. Các tích hợp sử dụng `InetUtils` hoặc các thuộc tính host do Spring Cloud công bố có thể dùng kết quả này khi đăng ký service.

## 3. ignoredInterfaces là gì?

`ignoredInterfaces` là danh sách Java regular expression dùng để bỏ qua các network interface có tên khớp. Thuộc tính đầy đủ:

~~~text
spring.cloud.inetutils.ignored-interfaces
~~~

Spring Cloud Commons bind thuộc tính này vào `InetUtilsProperties.ignoredInterfaces`. Mặc định danh sách rỗng, nghĩa là không bỏ qua interface nào bằng bộ lọc này.

Ví dụ chính thức:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
~~~

Trong ví dụ:

- `docker0` khớp interface có display name chính xác là `docker0`.
- `veth.*` khớp tên bắt đầu bằng `veth` và có thể có thêm ký tự phía sau, ví dụ `veth0` hoặc `veth8a1b2c`.

Danh sách có ý nghĩa OR: nếu interface khớp bất kỳ pattern nào, `InetUtils` bỏ qua interface đó.

### 3.1. Regex được so khớp với giá trị nào?

Trong implementation hiện hành, `InetUtils` gọi `NetworkInterface.getDisplayName()` rồi so khớp display name đó với từng pattern bằng `String.matches(regex)`.

Điều này có ba hệ quả:

1. Đầu vào là **display name của interface**, không phải IP address.
2. `String.matches` yêu cầu toàn bộ chuỗi khớp regex; pattern không tự động được hiểu là tìm chuỗi con.
3. Tên và display name có thể khác nhau tùy hệ điều hành hoặc driver. Hãy kiểm tra giá trị JVM thực sự nhìn thấy trước khi viết pattern.

Ví dụ:

| Display name | Pattern | Kết quả |
| --- | --- | --- |
| `docker0` | `docker0` | Khớp |
| `veth1234` | `veth.*` | Khớp |
| `veth1234` | `veth` | Không khớp |
| `my-docker0` | `docker0` | Không khớp |
| `my-docker0` | `.*docker.*` | Khớp |
| `eth0` | `veth.*` | Không khớp |

Nếu muốn khớp chính xác, có thể viết `^docker0$`. Với `String.matches`, hai đầu chuỗi vốn đã phải khớp toàn bộ, nhưng dấu neo giúp ý định dễ đọc hơn.

### 3.2. Ví dụ pattern thường dùng

| Mục tiêu | Pattern | Giải thích |
| --- | --- | --- |
| Chỉ bỏ qua `docker0` | `^docker0$` | Tên chính xác |
| Bỏ qua mọi interface `veth` | `^veth.*$` | Tiền tố `veth` |
| Bỏ qua bridge tên `br-...` | `^br-[0-9a-f]+$` | Chuỗi hex phía sau `br-` |
| Bỏ qua adapter `virbr` có số | `^virbr\\d+$` | Một hoặc nhiều chữ số |
| Bỏ qua tên có chứa `docker` | `.*docker.*` | Tìm chuỗi con |

Chỉ đưa vào danh sách những interface thật sự không nên được dùng. Nếu bỏ qua nhầm interface mạng chính, ứng dụng có thể không tìm được IP mong muốn.

## 4. Cách InetUtils chọn địa chỉ

`ignoredInterfaces` là một bước trong quá trình chọn địa chỉ. Nó không tự quyết định toàn bộ địa chỉ cuối cùng.

Luồng khái quát trong `InetUtils.findFirstNonLoopbackAddress()`:

1. JVM liệt kê các `NetworkInterface` trên máy.
2. `InetUtils` xét các interface đang ở trạng thái UP.
3. Trước khi duyệt địa chỉ của interface, `InetUtils` kiểm tra display name với danh sách ignored pattern.
4. Nếu tên khớp, interface bị bỏ qua; các địa chỉ của interface đó không được xét làm candidate.
5. Với interface không bị bỏ qua, `InetUtils` duyệt các địa chỉ và xét điều kiện địa chỉ IPv4, không phải loopback và thỏa bộ lọc mạng.
6. Nếu tìm được địa chỉ phù hợp, `InetUtils` chuyển nó thành `HostInfo` gồm hostname và IP.
7. Nếu không tìm được candidate, implementation hiện hành thử `InetAddress.getLocalHost()` làm fallback.

~~~mermaid
flowchart TD
    A[Enumerate network interfaces] --> B{Interface is UP?}
    B -->|No| A
    B -->|Yes| C[Read display name]
    C --> D{Matches ignoredInterfaces?}
    D -->|Yes| A
    D -->|No| E[Enumerate interface addresses]
    E --> F{IPv4 and non-loopback?}
    F -->|No| E
    F -->|Yes| G{Pass preferredNetworks or site-local filter?}
    G -->|No| E
    G -->|Yes| H[Candidate host address]
    H --> I[Build HostInfo]
    E --> J{More addresses?}
    J -->|Yes| E
    J -->|No| A
    A --> K{Any candidate found?}
    K -->|Yes| I
    K -->|No| L[Fallback InetAddress.getLocalHost()]
~~~

Sơ đồ cho thấy ignored filter chạy trên interface trước khi địa chỉ được xét. Nếu interface bị bỏ qua, toàn bộ địa chỉ gắn với interface đó không tham gia bước chọn candidate.

### 4.1. ignoredInterfaces không phải bộ lọc địa chỉ IP

Pattern như `^10\\.20\\..*` không nên đặt trong `ignored-interfaces` nếu mục tiêu là lọc IP. Pattern này được so với tên interface, ví dụ `eth0`, chứ không so với địa chỉ `10.20.1.15`.

Muốn ưu tiên hoặc giới hạn dải IP, hãy dùng `preferred-networks` hoặc `use-only-site-local-interfaces`.

### 4.2. Fallback cần được hiểu đúng

Nếu tất cả interface đều bị bỏ qua hoặc không có địa chỉ thỏa điều kiện, `InetUtils` hiện hành thử `InetAddress.getLocalHost()`. Địa chỉ fallback được trả về không nhất thiết đã đi qua cùng bộ lọc ignored/preferred như candidate thông thường.

Vì vậy, `ignored-interfaces` là bộ lọc trong quá trình chọn địa chỉ, **không phải cam kết tuyệt đối rằng địa chỉ trả về không bao giờ thuộc interface đã bị bỏ qua**. Sau khi thay cấu hình, luôn kiểm tra `HostInfo` thực tế.

## 5. Cấu hình trong application.yml

### 5.1. Bỏ qua bridge và veth của Docker trên host

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
~~~

Đây là cấu hình phù hợp khi JVM chạy trên Docker host và các interface bridge/veth xuất hiện trong namespace của host. Tên interface thực tế có thể khác, nên cần xác minh bằng công cụ hệ điều hành và JVM.

### 5.2. Bỏ qua một nhóm adapter ảo cụ thể

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
        - '^virbr[0-9]+$'
        - '^br-[0-9a-f]+$'
      preferred-networks:
        - '10.20.'
        - '192.168.50.'
~~~

Trong ví dụ, ignored list bỏ qua interface có tên khớp các pattern. `preferred-networks` tiếp tục lọc theo địa chỉ IP để chỉ chấp nhận địa chỉ thuộc hai prefix mong muốn.

Trong implementation hiện hành, `preferredNetworks` kiểm tra địa chỉ bằng `address.matches(regex)` hoặc `address.startsWith(regex)`. Vì vậy, các giá trị như `10.20.` được dùng như prefix chuỗi cũng có thể hoạt động. Đây là cách xử lý khác với `ignoredInterfaces`, vốn dùng `interfaceName.matches(regex)`.

### 5.3. Bỏ qua loopback theo tên

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^lo$'
~~~

Loopback address vốn đã bị loại bởi kiểm tra `isLoopbackAddress()` khi chọn candidate IPv4. Thêm `lo` vào ignored list có thể làm rõ policy hoặc bỏ qua toàn bộ interface loopback trước khi duyệt địa chỉ. Thông thường không cần cấu hình này nếu chỉ muốn loại địa chỉ loopback.

### 5.4. Dùng application.properties

Có thể khai báo list bằng indexed properties:

~~~properties
spring.cloud.inetutils.ignored-interfaces[0]=^docker0$
spring.cloud.inetutils.ignored-interfaces[1]=^veth.*$
spring.cloud.inetutils.ignored-interfaces[2]=^virbr[0-9]+$
~~~

Spring Boot relaxed binding hỗ trợ cách viết kebab-case trong properties và YAML. Dùng một định dạng nhất quán trong dự án để tránh khó theo dõi.

## 6. Phân biệt ba thuộc tính chọn interface và địa chỉ

Ba thuộc tính thường được dùng cùng nhau nhưng giải quyết các vấn đề khác nhau:

| Thuộc tính | Đầu vào được xét | Tác dụng |
| --- | --- | --- |
| `spring.cloud.inetutils.ignored-interfaces` | Display name của network interface | Bỏ qua toàn bộ interface nếu tên khớp regex |
| `spring.cloud.inetutils.preferred-networks` | Địa chỉ IP của interface | Chỉ nhận các địa chỉ khớp regex hoặc prefix được cấu hình |
| `spring.cloud.inetutils.use-only-site-local-interfaces` | Địa chỉ IP | Chỉ nhận địa chỉ mà `InetAddress.isSiteLocalAddress()` trả về true |

Ví dụ kết hợp:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
      preferred-networks:
        - '10.20.'
        - '192.168.50.'
      use-only-site-local-interfaces: false
~~~

Không nên bật `use-only-site-local-interfaces` rồi kỳ vọng mọi địa chỉ private đều được chọn theo cùng một khái niệm với CIDR. Thuộc tính này dùng quy tắc `InetAddress.isSiteLocalAddress()` của JDK; nó không phải parser CIDR và không tương đương policy mạng của cloud provider.

### 6.1. Default hostname và IP khi không tìm được host

`InetUtilsProperties` còn có:

~~~yaml
spring:
  cloud:
    inetutils:
      default-hostname: localhost
      default-ip-address: 127.0.0.1
~~~

Hai giá trị này được dùng khi `InetUtils.findFirstNonLoopbackHostInfo()` không lấy được địa chỉ host. Chúng không phải cách thay thế cho cấu hình interface đúng. Nếu service registry công bố `127.0.0.1` cho các service ở máy khác, các client sẽ kết nối tới loopback của chính chúng và không thể tới service đã đăng ký.

## 7. Kiểm tra interface mà JVM thực sự nhìn thấy

Trước khi viết regex, hãy liệt kê interface trên đúng máy/container chạy ứng dụng. Lệnh `ip addr` hoặc `ip link` hữu ích trên Linux, nhưng kết quả từ JVM mới là cơ sở để đối chiếu `NetworkInterface.getDisplayName()`.

### 7.1. Java diagnostic

Tạo một chương trình nhỏ:

~~~java
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.util.Enumeration;

public class NetworkInterfaceReport {

    public static void main(String[] args) throws SocketException {
        Enumeration<NetworkInterface> interfaces =
                NetworkInterface.getNetworkInterfaces();

        while (interfaces.hasMoreElements()) {
            NetworkInterface networkInterface = interfaces.nextElement();

            System.out.printf(
                    "name=%s, displayName=%s, up=%s, index=%d%n",
                    networkInterface.getName(),
                    networkInterface.getDisplayName(),
                    networkInterface.isUp(),
                    networkInterface.getIndex());

            Enumeration<InetAddress> addresses =
                    networkInterface.getInetAddresses();

            while (addresses.hasMoreElements()) {
                InetAddress address = addresses.nextElement();
                System.out.printf(
                        "  address=%s, type=%s, loopback=%s, siteLocal=%s%n",
                        address.getHostAddress(),
                        address.getClass().getSimpleName(),
                        address.isLoopbackAddress(),
                        address.isSiteLocalAddress());
            }
        }
    }
}
~~~

Chú ý hai cột `name` và `displayName`. Implementation `InetUtils` hiện hành so khớp pattern với `displayName`. Nếu chỉ nhìn tên từ `ip link` rồi cấu hình theo tên đó, hãy xác minh display name của JVM có cùng giá trị.

### 7.2. Quan sát HostInfo của Spring Cloud

Trong ứng dụng Spring, có thể inject `InetUtils` để xem kết quả mà Spring Cloud tính toán:

~~~java
package com.example.networking;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.commons.util.InetUtils;
import org.springframework.stereotype.Component;

@Component
public class HostInfoReporter implements ApplicationRunner {

    private final InetUtils inetUtils;

    public HostInfoReporter(InetUtils inetUtils) {
        this.inetUtils = inetUtils;
    }

    @Override
    public void run(ApplicationArguments args) {
        InetUtils.HostInfo hostInfo =
                inetUtils.findFirstNonLoopbackHostInfo();

        System.out.println("hostname=" + hostInfo.getHostname());
        System.out.println("ipAddress=" + hostInfo.getIpAddress());
    }
}
~~~

Đoạn code minh họa việc kiểm tra kết quả trong ứng dụng có auto-configuration của Spring Cloud Commons. Không log thông tin mạng nội bộ vào log công khai nếu đó là dữ liệu hạ tầng nhạy cảm.

### 7.3. Bật TRACE log

Để thấy interface nào được thử, interface nào bị bỏ qua và địa chỉ nào được chọn, bật log trong môi trường local:

~~~yaml
logging:
  level:
    org.springframework.cloud.commons.util.InetUtils: TRACE
~~~

Implementation hiện hành ghi log trace khi kiểm tra interface, bỏ qua interface và tìm thấy non-loopback interface. Tắt TRACE sau khi chẩn đoán vì log có thể làm lộ cấu trúc mạng và tạo nhiều bản ghi khi khởi động.

## 8. HostInfoEnvironmentPostProcessor và service registration

Spring Cloud Commons có `HostInfoEnvironmentPostProcessor`. Trong implementation hiện hành, processor:

1. Tạo `InetUtilsProperties`.
2. Gắn configuration property sources vào Environment.
3. Dùng Spring Boot `Binder` bind prefix `spring.cloud.inetutils`.
4. Tạo `InetUtils` với các thuộc tính vừa bind.
5. Gọi `findFirstNonLoopbackHostInfo()`.
6. Thêm `spring.cloud.client.hostname` và `spring.cloud.client.ip-address` vào Environment.

Processor được sắp thứ tự sau `ConfigDataEnvironmentPostProcessor` trong code hiện hành. Điều đó cho phép cấu hình từ Config Data, chẳng hạn `application.yml`, được bind trước khi host info được tính.

Các discovery client hoặc auto-registration integration có thể sử dụng host info này khi xây dựng thông tin đăng ký. Tuy nhiên, từng registry có thể có thuộc tính override riêng như hostname, IP, prefer IP hoặc metadata. Nếu đã cấu hình override ở provider, hãy kiểm tra thứ tự ưu tiên giữa cấu hình provider và giá trị mặc định từ Spring Cloud.

### 8.1. Host info được tính khi nào?

`HostInfoEnvironmentPostProcessor` chạy trong giai đoạn khởi động ứng dụng để bổ sung hostname và IP vào Environment. Nó không liên tục quét lại interface khi VPN bật/tắt hoặc adapter thay đổi trạng thái sau khi ứng dụng đã chạy.

Nếu cấu trúc mạng thay đổi sau startup:

- Xác minh registry có hỗ trợ cập nhật registration host/metadata runtime hay không.
- Nếu không có cơ chế cập nhật an toàn, restart/rollout instance để tính lại host info.
- Không giả định chỉ sửa `application.yml` hoặc refresh một bean sẽ làm `spring.cloud.client.ip-address` tự động tính lại.

## 9. Docker và Kubernetes: network namespace rất quan trọng

Tên interface nhìn thấy trên host có thể khác tên interface bên trong container.

Ví dụ trên Docker host:

~~~text
Host network namespace:
  eth0
  docker0
  vethA1B2
  vethC3D4

Container network namespace:
  lo
  eth0
~~~

Ứng dụng chạy bên trong container thường chỉ nhìn thấy các interface thuộc network namespace của container. Nó có thể không nhìn thấy `docker0` hoặc các đầu `veth` nằm ở host namespace. Vì vậy, cấu hình:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^veth.*$'
~~~

có tác dụng khi những tên đó thực sự xuất hiện trong namespace của JVM. Nếu container chỉ nhìn thấy `eth0` và `lo`, pattern `docker0` và `veth.*` không khớp interface nào.

### 9.1. Không bỏ qua eth0 một cách máy móc

Trong nhiều container, `eth0` là interface chính mà service khác có thể truy cập qua network overlay hoặc bridge. Nếu thêm:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^eth0$'
~~~

ứng dụng có thể bỏ qua đúng interface mạng cần dùng. Chỉ làm vậy khi đã xác minh có một interface khác phù hợp và registry/consumer thực sự có thể định tuyến tới địa chỉ đó.

### 9.2. Kubernetes CNI

Tên interface trong Pod phụ thuộc CNI, runtime và cấu hình node. Pod thường có interface mặc định như `eth0`, còn interface phụ có thể được tạo bởi Multus hoặc plugin khác. Không suy luận tên interface từ tên CNI; hãy chạy diagnostic bên trong Pod hoặc in danh sách từ JVM của ứng dụng.

Nếu service registry cần địa chỉ Pod, hãy xác minh địa chỉ được chọn thuộc network mà các consumer có thể định tuyến tới. Trong Kubernetes, Service/Endpoint và DNS nội bộ thường là abstraction phù hợp hơn cho giao tiếp service-to-service; IP Pod không nên được dùng thay thế cho Service nếu ứng dụng không có chủ đích đăng ký trực tiếp Pod.

## 10. Kiểm tra regex độc lập

Vì implementation dùng `String.matches`, có thể kiểm tra pattern trước khi triển khai:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class IgnoredInterfacePatternTest {

    @Test
    void matchesExactDockerBridgeAndVethPrefix() {
        assertThat("docker0".matches("^docker0$")).isTrue();
        assertThat("veth8a1b2c".matches("^veth.*$")).isTrue();
        assertThat("eth0".matches("^veth.*$")).isFalse();
        assertThat("my-docker0".matches("^docker0$")).isFalse();
        assertThat("my-docker0".matches(".*docker.*")).isTrue();
    }
}
~~~

Test này kiểm tra ngữ nghĩa regex của Java. Nó không chứng minh máy production thực sự có display name như trong test. Muốn kiểm tra đầy đủ, cần chạy diagnostic trong đúng OS/container và đối chiếu log `InetUtils`.

### 10.1. Test binding của cấu hình

Khi viết integration test cho ứng dụng, kiểm tra list đã được bind vào `InetUtilsProperties`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.commons.util.InetUtilsProperties;

@SpringBootTest(properties = {
    "spring.cloud.inetutils.ignored-interfaces[0]=^docker0$",
    "spring.cloud.inetutils.ignored-interfaces[1]=^veth.*$"
})
class InetUtilsPropertiesBindingTest {

    @Autowired
    InetUtilsProperties properties;

    @Test
    void bindsIgnoredInterfacePatterns() {
        assertThat(properties.getIgnoredInterfaces())
                .containsExactly("^docker0$", "^veth.*$");
    }
}
~~~

Đoạn test giả định test source có AssertJ, JUnit Jupiter và auto-configuration của Spring Cloud Commons. Nếu ứng dụng tự tạo `InetUtilsProperties` hoặc tắt auto-configuration, cần kiểm tra bean registration theo cấu hình thực tế.

## 11. Những điều ignoredInterfaces không làm

`ignored-interfaces` chỉ điều khiển bước chọn interface của `InetUtils`. Nó không:

- Tắt network interface ở hệ điều hành.
- Xóa interface khỏi Docker, Kubernetes, Hyper-V hoặc VPN.
- Thay đổi routing table, firewall, NAT hoặc policy của cloud network.
- Ngăn ứng dụng bind socket vào địa chỉ thuộc interface bị bỏ qua.
- Chặn kết nối outbound đi qua interface đó.
- Tự cấu hình địa chỉ IP mà Eureka/Consul hoặc registry khác phải công bố nếu provider có override riêng.
- Bảo đảm fallback host address không thuộc interface đã bị bỏ qua.

Nếu mục tiêu là bảo vệ mạng hoặc chặn traffic, hãy dùng firewall, network policy, security group hoặc cấu hình network của nền tảng. Không dùng `ignoredInterfaces` như một biện pháp bảo mật.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Cấu hình có `docker0` nhưng interface vẫn được chọn | JVM không thấy display name chính xác là `docker0` hoặc regex không khớp toàn chuỗi | In `getDisplayName()` và thử pattern bằng `String.matches()` |
| `veth` không bị bỏ qua | Pattern `veth` không khớp tên như `veth1234` | Dùng `^veth.*$` |
| Địa chỉ vẫn là IP bridge sau khi bỏ qua interface | Không còn candidate khác nên fallback `InetAddress.getLocalHost()` trả địa chỉ đó | Kiểm tra log và fallback; cấu hình interface/host IP phù hợp hoặc dùng override của registry |
| Container không có `docker0` | JVM ở network namespace riêng | Liệt kê interface bên trong container; cấu hình theo interface thực tế |
| Ứng dụng đăng ký IP VPN | VPN interface không bị ignore hoặc preferred network cho phép IP VPN | Bỏ qua display name VPN hoặc điều chỉnh `preferred-networks` |
| Bỏ qua `eth0` khiến không có IP hợp lệ | `eth0` là interface chính của container | Gỡ pattern và kiểm tra network namespace |
| Sửa cấu hình nhưng `spring.cloud.client.ip-address` không đổi | Host info đã được tính trong startup | Restart/rollout hoặc dùng cơ chế cập nhật registration riêng của registry |
| Pattern có dấu chấm hoặc ngoặc không khớp | Regex metacharacter chưa được escape | Escape ký tự đặc biệt hoặc kiểm thử `String.matches()` |
| TRACE log không thấy interface mong muốn | Interface DOWN hoặc JVM không nhìn thấy interface đó | Kiểm tra trạng thái và namespace từ chính process/container |

### 12.1. Quy trình chẩn đoán đề xuất

1. Liệt kê interface trong đúng môi trường chạy ứng dụng.
2. Ghi cả `getName()` và `getDisplayName()`.
3. Ghi trạng thái UP/DOWN và các địa chỉ gắn với interface.
4. Bật TRACE cho `InetUtils`.
5. Kiểm tra từng pattern bằng Java `String.matches()`.
6. Xác minh địa chỉ mà `InetUtils.findFirstNonLoopbackHostInfo()` trả về.
7. Kiểm tra địa chỉ thực tế trong service registry.
8. Nếu không khớp, xem provider-specific override và fallback behavior.

## 13. Bài tập thực hành

### Bài 1 — Nhận diện interface

Chạy chương trình `NetworkInterfaceReport` trên máy phát triển và ghi lại:

- Tên interface.
- Display name.
- Trạng thái UP/DOWN.
- Danh sách IPv4/IPv6.
- Địa chỉ loopback và site-local.

Chỉ ra interface nào thuộc mạng ứng dụng, interface nào thuộc VPN/bridge/adapter ảo.

### Bài 2 — Viết ignoredInterfaces

Tạo cấu hình bỏ qua:

- Interface Docker bridge có display name `docker0`.
- Mọi interface có display name bắt đầu bằng `veth`.
- Một interface ảo khác mà bạn xác định từ kết quả diagnostic.

Giải thích từng regex và kiểm tra bằng `String.matches()`.

### Bài 3 — So sánh với preferredNetworks

Giữ nguyên ignored list, thêm `preferred-networks` chỉ chấp nhận prefix IP của mạng ứng dụng. Quan sát sự khác nhau giữa:

- Bỏ qua interface theo display name.
- Lọc địa chỉ theo IP.
- Chỉ chọn địa chỉ site-local.

### Bài 4 — Kiểm tra trong container

Chạy cùng ứng dụng trên host và trong container. So sánh danh sách interface JVM nhìn thấy. Xác định vì sao một pattern có thể khớp trên host nhưng không khớp trong container.

### Bài 5 — Xác minh service registration

Khởi động ứng dụng với cấu hình mới, lấy `spring.cloud.client.ip-address` và đối chiếu địa chỉ được đăng ký trong registry. Thử thay đổi một pattern và khởi động lại để xác nhận kết quả.

**Tiêu chí hoàn thành:** bạn có thể viết regex khớp đúng display name, giải thích vì sao một interface bị bỏ qua, phân biệt lọc interface với lọc địa chỉ IP và xác minh host info mà service discovery sử dụng.

## 14. Tổng kết

`spring.cloud.inetutils.ignored-interfaces` là danh sách Java regex dùng để bỏ qua network interface trong quá trình `InetUtils` tìm địa chỉ host. Implementation hiện hành so khớp regex với `NetworkInterface.getDisplayName()` bằng `String.matches`, nên pattern phải khớp toàn bộ display name. Danh sách có ý nghĩa OR: một pattern khớp là interface bị bỏ qua.

Để chọn đúng IP, hãy xác minh interface trong network namespace của JVM, kết hợp ignored list với `preferred-networks` hoặc `use-only-site-local-interfaces` khi phù hợp, rồi kiểm tra `HostInfo` và giá trị host được công bố. `ignoredInterfaces` không tắt adapter hoặc thay đổi routing; nếu không còn candidate, fallback có thể trả về địa chỉ khác với kỳ vọng. Vì host info thường được tính trong startup, thay đổi network hoặc cấu hình sau đó cần một quy trình cập nhật registration hoặc restart phù hợp.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions, Ignore Network Interfaces](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): ví dụ `docker0`, `veth.*`, `preferredNetworks` và site-local interfaces.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): thuộc tính `spring.cloud.inetutils.ignored-interfaces`, `preferred-networks`, `default-hostname`, `default-ip-address` và timeout.
- [InetUtils.java source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/commons/util/InetUtils.java): cách so khớp display name, lọc địa chỉ, fallback và tạo HostInfo.
- [InetUtilsProperties.java source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/commons/util/InetUtilsProperties.java): prefix `spring.cloud.inetutils` và các thuộc tính cấu hình.
- [HostInfoEnvironmentPostProcessor.java source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/HostInfoEnvironmentPostProcessor.java): bind cấu hình và công bố `spring.cloud.client.hostname` cùng `spring.cloud.client.ip-address`.
- [Java NetworkInterface API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/NetworkInterface.html): tên, display name, trạng thái và địa chỉ của network interface.

Hãy đối chiếu implementation với release train Spring Cloud đang triển khai. Chi tiết chọn địa chỉ và thời điểm nạp cấu hình có thể thay đổi theo phiên bản, OS và network namespace.
