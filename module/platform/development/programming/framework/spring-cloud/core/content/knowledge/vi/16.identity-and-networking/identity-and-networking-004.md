# Chọn địa chỉ mạng khi máy có nhiều network interface

Một máy chủ có thể đồng thời có nhiều network interface: card Ethernet, Wi-Fi, VPN, loopback, bridge của Docker, interface của Kubernetes hoặc card dành riêng cho mạng quản trị. Mỗi interface có thể mang một hay nhiều địa chỉ IPv4/IPv6. Khi một ứng dụng Spring Cloud đăng ký với service registry, nó cần công bố đúng địa chỉ để các service khác có thể kết nối.

Nếu ứng dụng chọn nhầm địa chỉ, registry vẫn có thể nhận registration thành công nhưng client gọi tới địa chỉ không thể định tuyến. Một địa chỉ `127.0.0.1`, IP của Docker bridge hoặc IP chỉ truy cập được từ mạng quản trị đều có thể khiến discovery trả về instance không sử dụng được.

Spring Cloud Commons cung cấp `InetUtils` và nhóm cấu hình `spring.cloud.inetutils` để chọn thông tin host phù hợp. Tuy nhiên, cần phân biệt **địa chỉ mà web server bind để lắng nghe** với **địa chỉ mà ứng dụng quảng bá cho registry**. Hai địa chỉ này có mục đích khác nhau và không nhất thiết giống nhau.

Bài học thuộc chương **Định danh và mạng** của **SPRING_CLOUD_CORE**. Nội dung tập trung vào cách chọn địa chỉ khi có nhiều interface, cấu hình `preferred-networks` và `ignored-interfaces`, override địa chỉ theo provider, cùng cách kiểm tra registration trong môi trường thật.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt network interface, IP address, hostname, bind address và advertised address.
- Giải thích vì sao thứ tự interface của hệ điều hành có thể làm ứng dụng chọn nhầm IP.
- Mô tả vai trò của `InetUtils` và `InetUtilsProperties` trong Spring Cloud Commons.
- Cấu hình `spring.cloud.inetutils.preferred-networks` để ưu tiên dải IP mong muốn.
- Cấu hình `spring.cloud.inetutils.ignored-interfaces` để loại interface không phù hợp.
- Hiểu giới hạn của `use-only-site-local-interfaces` và các giá trị fallback.
- Phân biệt cấu hình host discovery chung với cấu hình riêng của Eureka hoặc provider khác.
- Phân biệt `server.address` với địa chỉ đăng ký dịch vụ.
- Chọn địa chỉ phù hợp trong Docker, Kubernetes, VPN, dual-stack IPv4/IPv6.
- Kiểm thử địa chỉ được chọn và xác minh client khác thực sự kết nối được.

## 2. Phân biệt các khái niệm mạng

Trước khi cấu hình Spring Cloud, cần xác định chính xác ứng dụng đang cần loại địa chỉ nào.

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Network interface | Thiết bị/giao diện mạng mà hệ điều hành cung cấp cho tiến trình | `eth0`, `ens160`, `wlan0`, `tun0`, `docker0` |
| IP address | Địa chỉ gắn với một interface | `10.20.5.18`, `192.168.1.30`, `2001:db8::18` |
| Hostname | Tên máy được phân giải qua DNS hoặc cơ chế name resolution khác | `checkout-01.internal` |
| Bind address | Địa chỉ local mà server mở socket để lắng nghe | `0.0.0.0`, `127.0.0.1`, `10.20.5.18` |
| Advertised address | Địa chỉ ứng dụng công bố cho registry hoặc client khác | `10.20.5.18:8080`, `checkout.internal:8080` |
| Outbound route/source address | Interface và IP nguồn do routing/socket của hệ điều hành chọn khi kết nối đi ra | VPN, NIC LAN hoặc route theo policy |
| Service ID | Tên logic mà client dùng để tìm dịch vụ | `checkout-service` |

`InetUtils` chủ yếu giúp Spring Cloud xác định thông tin host/IP của máy chạy ứng dụng. Nó không thay thế DNS, route table, firewall, service mesh hay cấu hình bind của web server.

### 2.1. Bind address khác advertised address

Ví dụ:

```yaml
server:
  address: 0.0.0.0
  port: 8080
```

`0.0.0.0` yêu cầu server lắng nghe trên tất cả địa chỉ IPv4 local phù hợp. Đây không phải địa chỉ để đăng ký cho service khác gọi tới. Client không thể dùng `0.0.0.0` như một đích kết nối cụ thể.

Trong khi đó, registry cần một địa chỉ có thể định tuyến từ mạng của các consumer, ví dụ:

```text
checkout-service -> 10.20.5.18:8080
```

Một ứng dụng có thể bind trên `0.0.0.0` nhưng advertise `10.20.5.18`. Đây là cấu hình phổ biến khi máy có nhiều interface.

### 2.2. Advertised address không quyết định NIC outbound

`spring.cloud.inetutils.preferred-networks` giúp Spring Cloud ưu tiên host/IP khi xây dựng thông tin host cho integration phù hợp. Thuộc tính này không sửa routing table, không thay đổi policy routing và không buộc mọi kết nối HTTP, JDBC, Kafka hoặc messaging phải đi ra qua interface đã chọn.

Khi cần ép traffic outbound qua VPN hoặc một NIC cụ thể, hãy cấu hình route ở hệ điều hành/container/network platform hoặc cấu hình socket/client tương ứng. Không dùng `InetUtils` như một cơ chế kiểm soát đường đi của packet. Sau khi chọn advertised address, vẫn phải kiểm tra route hai chiều, firewall, NAT và khả năng truy cập từ đúng network namespace của consumer.
### 2.3. Địa chỉ loopback không phù hợp cho service discovery liên máy

Các địa chỉ như `127.0.0.1` hoặc `::1` chỉ trỏ về chính network namespace của tiến trình. Nếu registry công bố `127.0.0.1:8080`, một service khác khi gọi địa chỉ đó sẽ kết nối tới loopback của chính nó, không phải máy chứa `checkout-service`.

Loopback hữu ích cho giao tiếp nội bộ trên cùng host, nhưng không nên là advertised address cho các service ở host/container khác.

## 3. Vì sao máy nhiều interface dễ chọn sai địa chỉ?

Một máy ảo hoặc server có thể có các interface như:

```text
lo       127.0.0.1
ens160   10.20.5.18
ens192   172.20.0.12
docker0  172.17.0.1
tailscale0 100.80.10.4
```

Các địa chỉ trên có thể phục vụ mục đích khác nhau:

- `ens160`: mạng ứng dụng mà các service nội bộ có thể truy cập.
- `ens192`: mạng backup hoặc quản trị.
- `docker0`: bridge giữa host và container.
- `tailscale0`: VPN overlay chỉ các node trong VPN truy cập.
- `lo`: loopback.

Nếu ứng dụng chọn IP đầu tiên không phải loopback theo thứ tự hệ điều hành trả về, nó có thể chọn `172.20.0.12` hoặc `100.80.10.4` thay vì `10.20.5.18`.

Thứ tự liệt kê interface không phải một hợp đồng ổn định giữa các máy hoặc giữa các lần triển khai. Không nên dựa vào giả định rằng interface có tên `eth0` luôn đứng trước interface khác, hoặc địa chỉ đầu tiên luôn là địa chỉ mà consumer sử dụng được.

### 3.1. Các nguồn gây nhầm lẫn thường gặp

- Nhiều card vật lý cùng hoạt động.
- VPN được bật sau khi ứng dụng khởi động.
- Docker hoặc container runtime tạo bridge interface.
- Máy có IPv4 và IPv6 đồng thời.
- Interface quản trị có địa chỉ private nhưng không mở route tới service network.
- Host có nhiều subnet hoặc nhiều default gateway.
- DNS trả về nhiều địa chỉ và mỗi client phân giải theo một đường mạng khác nhau.

Vấn đề cần giải quyết không đơn thuần là chọn một IP “đẹp”. Địa chỉ được quảng bá phải **có thể được các consumer thực tế định tuyến và truy cập**.

## 4. InetUtils trong Spring Cloud Commons

Spring Cloud Commons có utility `InetUtils` trong package:

```java
org.springframework.cloud.commons.util.InetUtils
```

Utility này giúp tìm thông tin host của máy chạy ứng dụng, bao gồm hostname và địa chỉ IP. Các cấu hình liên quan được bind từ nhóm:

```text
spring.cloud.inetutils
```

Các thành phần thường gặp:

| Property | Tác dụng |
| --- | --- |
| `spring.cloud.inetutils.preferred-networks` | Danh sách regex để ưu tiên địa chỉ thuộc các mạng mong muốn |
| `spring.cloud.inetutils.ignored-interfaces` | Danh sách regex để bỏ qua interface có tên phù hợp |
| `spring.cloud.inetutils.use-only-site-local-interfaces` | Chỉ xem xét địa chỉ được Java phân loại là site-local |
| `spring.cloud.inetutils.default-ip-address` | Địa chỉ fallback nếu không tìm được địa chỉ phù hợp |
| `spring.cloud.inetutils.default-hostname` | Hostname fallback trong trường hợp không xác định được host |
| `spring.cloud.inetutils.timeout-seconds` | Giới hạn thời gian liên quan tới thao tác xác định host theo implementation |

Tên và hành vi cụ thể cần đối chiếu với phiên bản Spring Cloud Commons mà ứng dụng đang dùng. Nhóm property này điều khiển quá trình tìm host chung; provider discovery vẫn có thể có cấu hình override riêng.

### 4.1. InetUtils tìm địa chỉ như thế nào?

Ở mức khái niệm, quá trình tìm địa chỉ thường gồm:

1. Lấy danh sách interface mà network namespace của JVM nhìn thấy.
2. Bỏ qua interface không hoạt động hoặc interface không phù hợp theo các quy tắc lọc.
3. Bỏ qua loopback và interface khớp `ignored-interfaces`.
4. Xét các địa chỉ gắn với interface còn lại.
5. Áp dụng quy tắc site-local nếu được bật.
6. Ưu tiên địa chỉ khớp `preferred-networks`.
7. Nếu không tìm thấy địa chỉ phù hợp, sử dụng địa chỉ fallback được cấu hình.

Chi tiết duyệt interface và lựa chọn địa chỉ thuộc implementation của release đang dùng. Không nên dựa vào thứ tự enumeration của hệ điều hành nếu có nhiều địa chỉ cùng khớp.

### 4.2. HostInfo

`InetUtils` có thể trả về thông tin host thông qua `HostInfo`, bao gồm hostname và IP address. Spring Cloud sử dụng thông tin này ở các thành phần cần nhận diện host local.

Ví dụ minh họa:

```java
@Component
public class LocalHostReporter {

    private final InetUtils inetUtils;

    public LocalHostReporter(InetUtils inetUtils) {
        this.inetUtils = inetUtils;
    }

    public void report() {
        InetUtils.HostInfo hostInfo =
                inetUtils.findFirstNonLoopbackHostInfo();

        String hostname = hostInfo.getHostname();
        String ipAddress = hostInfo.getIpAddress();
        // Report only non-sensitive host metadata.
    }
}
```

Đoạn mã giúp quan sát kết quả của thuật toán chọn host. Nó không chứng minh IP đó có thể truy cập từ mọi consumer; vẫn phải kiểm tra route, firewall và provider registration.

## 5. Ưu tiên dải mạng bằng preferred-networks

Khi máy có nhiều địa chỉ, `preferred-networks` cho phép chỉ rõ các dải địa chỉ nên được ưu tiên. Các giá trị là regular expression dùng để so khớp địa chỉ mạng theo cơ chế của `InetUtils`.

Ví dụ máy có subnet ứng dụng `10.20.0.0/16`, còn bridge và VPN dùng các dải khác:

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '^10[.]20[.].*'
```

Ứng dụng sẽ ưu tiên địa chỉ khớp dải `10.20.*` nếu có địa chỉ phù hợp.

### 5.1. Ưu tiên nhiều dải

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '^10[.]20[.].*'
        - '^192[.]168[.]50[.].*'
```

Ví dụ này cho phép địa chỉ thuộc subnet ứng dụng `10.20.*` hoặc subnet `192.168.50.*` được xem là ứng viên ưu tiên.

Nếu nhiều interface cùng có địa chỉ khớp, không nên mặc định thứ tự các dòng YAML chính là thứ tự chọn cuối cùng. Kết quả còn phụ thuộc thuật toán duyệt interface/address của phiên bản đang chạy. Hãy cấu hình để chỉ có một dải phù hợp nếu việc chọn chính xác một NIC là yêu cầu bắt buộc.

### 5.2. Regex cụ thể hơn an toàn hơn

Một regex quá rộng:

```yaml
preferred-networks:
  - '^10.*'
```

có thể khớp nhiều subnet `10.0.0.0/8`, bao gồm cả mạng quản trị hoặc overlay không mong muốn.

Nên thu hẹp theo subnet:

```yaml
preferred-networks:
  - '^10[.]20[.]5[.].*'
```

Nếu địa chỉ có thể đổi trong một subnet nhưng subnet không đổi, regex theo subnet là lựa chọn cân bằng giữa tính ổn định và tính linh hoạt.

### 5.3. Regex và IPv6

Địa chỉ IPv6 có dạng chuỗi khác IPv4, ví dụ:

```text
2001:db8:20::18
fd20:5::18
fe80::1234
```

Nếu cần ưu tiên IPv6, regex phải phù hợp với cách địa chỉ được biểu diễn khi `InetUtils` so khớp. Tránh viết regex IPv4 rồi giả định nó cũng lọc được IPv6. Hãy xác minh trên đúng JVM, OS và release Spring Cloud.

## 6. Loại interface bằng ignored-interfaces

`ignored-interfaces` cho phép loại interface theo tên. Giá trị là danh sách regex, thường hữu ích khi máy có bridge, VPN hoặc interface quản trị mà service không nên quảng bá.

Ví dụ:

```yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^br-.*'
        - '^veth.*'
        - '^tun[0-9]+$'
```

Ý nghĩa:

- Bỏ qua bridge mặc định `docker0`.
- Bỏ qua interface bridge có tên bắt đầu bằng `br-`.
- Bỏ qua virtual Ethernet pair bắt đầu bằng `veth`.
- Bỏ qua interface tunnel có tên dạng `tun0`, `tun1`, ...

Tên interface khác nhau giữa Linux, Windows, macOS và môi trường cloud. Trên Windows, tên hiển thị có thể là `Ethernet`, `Wi-Fi`, hoặc tên adapter do hypervisor/VPN đặt. Hãy lấy đúng tên thực tế trước khi viết regex.

### 6.1. Kết hợp preferred-networks và ignored-interfaces

Trong ví dụ:

```yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^tailscale[0-9]*$'
      preferred-networks:
        - '^10[.]20[.]5[.].*'
```

Hai cấu hình giải quyết hai việc:

- `ignored-interfaces` loại interface không muốn sử dụng.
- `preferred-networks` ưu tiên địa chỉ thuộc subnet mong muốn trong số các địa chỉ còn lại.

Đừng xem hai danh sách này là danh sách route. Chúng không tạo route, không thay đổi gateway và không cấu hình firewall.

### 6.2. Không loại interface theo tên nếu tên không ổn định

Trong cloud hoặc container, tên interface có thể thay đổi theo nền tảng. Nếu tên không ổn định, lọc theo dải mạng bằng `preferred-networks` thường dễ quản lý hơn. Nếu cả tên lẫn subnet đều có thể thay đổi, hãy cân nhắc cấu hình IP/hostname quảng bá rõ ràng ở tầng provider hoặc nền tảng.

## 7. Chỉ sử dụng site-local interface

Có thể bật:

```yaml
spring:
  cloud:
    inetutils:
      use-only-site-local-interfaces: true
```

Thiết lập này giới hạn lựa chọn vào địa chỉ mà Java phân loại là site-local. Nó có thể hữu ích khi service chỉ giao tiếp trong mạng nội bộ và không muốn chọn địa chỉ public.

Tuy nhiên, không nên bật một cách máy móc:

- Một service có thể cần địa chỉ public hoặc địa chỉ overlay không được phân loại như mong đợi.
- Cách Java phân loại site-local không đồng nghĩa với mọi định nghĩa “private network” trong hạ tầng.
- Với IPv6, site-local theo API Java không nên bị đồng nhất với mọi địa chỉ Unique Local (`fc00::/7`).
- Một địa chỉ site-local vẫn có thể không có route hoặc bị firewall chặn từ consumer.

Hãy dùng `preferred-networks` để chọn subnet cụ thể khi biết rõ mạng cần quảng bá. `use-only-site-local-interfaces` là bộ lọc rộng hơn, không phải giải pháp thay thế cho thiết kế subnet.

## 8. Giá trị fallback không thay thế cấu hình mạng

Có thể cấu hình:

```yaml
spring:
  cloud:
    inetutils:
      default-hostname: checkout-fallback
      default-ip-address: 10.20.5.18
```

Fallback hữu ích khi không xác định được địa chỉ host phù hợp, nhưng cần hiểu giới hạn:

- Nó không gán IP lên interface của hệ điều hành.
- Nó không tạo route hoặc mở firewall.
- Nó không chứng minh địa chỉ còn tồn tại hoặc thuộc instance hiện tại.
- Nếu IP fallback bị stale, registry có thể công bố một địa chỉ không truy cập được.

Chỉ đặt fallback khi địa chỉ đó được quản lý ổn định bởi hạ tầng triển khai. Nếu không, nên để ứng dụng báo lỗi hoặc dùng cấu hình provider rõ ràng để tránh đăng ký sai địa chỉ.

## 9. Cấu hình host discovery chung và override theo provider

`spring.cloud.inetutils.*` ảnh hưởng đến quá trình xác định thông tin host chung. Nhưng mỗi discovery provider có thể cho phép khai báo hostname hoặc IP riêng.

### 9.1. Ví dụ với Eureka

Eureka có các thuộc tính instance riêng:

```yaml
eureka:
  instance:
    prefer-ip-address: true
    ip-address: 10.20.5.18
```

Các thuộc tính thường dùng:

| Property | Ý nghĩa |
| --- | --- |
| `eureka.instance.hostname` | Hostname mà Eureka instance sử dụng |
| `eureka.instance.ip-address` | IP address được chỉ định cho instance |
| `eureka.instance.prefer-ip-address` | Ưu tiên công bố URL dựa trên IP thay vì hostname |

Nếu đặt `ip-address` tường minh, hãy chắc chắn IP đó thuộc interface mà consumer có thể truy cập. `prefer-ip-address=true` không tự sửa route hoặc kiểm tra reachability.

### 9.2. Khi nào dùng InetUtils, khi nào override provider?

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Nhiều service dùng chung host discovery và cùng subnet ưu tiên | Cấu hình `spring.cloud.inetutils.preferred-networks` |
| Muốn bỏ bridge/VPN không phù hợp cho quá trình chọn host chung | Cấu hình `spring.cloud.inetutils.ignored-interfaces` |
| Chỉ một provider cần địa chỉ quảng bá khác | Dùng property hostname/IP riêng của provider |
| Hạ tầng cấp sẵn IP tĩnh cho từng instance | Override IP/hostname bằng cấu hình triển khai |
| Dùng DNS ổn định thay vì IP thay đổi | Công bố hostname mà consumer có thể phân giải |

Không giả định mọi provider đều dùng cùng một đường lấy host từ `InetUtils`. Kiểm tra tài liệu của starter/provider và xác minh registration thực tế.

## 10. Docker và container

Container thường có network namespace riêng. JVM nhìn thấy các interface của namespace đó, không nhất thiết nhìn thấy toàn bộ interface của host.

Ví dụ:

```text
Host:
  eth0       10.20.5.18
  docker0    172.17.0.1

Container:
  lo         127.0.0.1
  eth0       172.18.0.4
```

Trong bridge network, địa chỉ `172.18.0.4` có thể truy cập được từ container khác cùng network, nhưng không nhất thiết truy cập được từ service ở ngoài host.

### 10.1. Các lựa chọn phổ biến

- **Container cùng Docker network:** quảng bá IP hoặc DNS service name có thể truy cập trong network đó.
- **Consumer ở ngoài Docker network:** cần publish port và quảng bá địa chỉ host/DNS mà consumer có thể truy cập.
- **Host network mode:** container dùng network namespace của host; cần chọn interface host phù hợp và kiểm tra xung đột port.
- **Nhiều network Docker:** container có thể có nhiều interface; dùng preferred network hoặc cấu hình provider cụ thể.

### 10.2. Không quảng bá địa chỉ bridge của host cho consumer bên ngoài

Nếu registry trả `172.17.0.1:8080` nhưng consumer nằm ở một mạng không có route tới Docker bridge của host, kết nối sẽ thất bại. Địa chỉ có vẻ hợp lệ ở phía server không có nghĩa nó hợp lệ từ góc nhìn consumer.

Hãy kiểm tra địa chỉ từ đúng network namespace của client, không chỉ từ host đang chạy ứng dụng.

## 11. Kubernetes và service DNS

Trong Kubernetes, Pod có network namespace và Pod IP riêng. Tuy nhiên, client thường nên gọi service qua Kubernetes Service DNS thay vì lưu một Pod IP cố định trong cấu hình ứng dụng.

Ví dụ:

```text
inventory.default.svc.cluster.local
```

Một số nguyên tắc:

- Pod IP có thể thay đổi khi Pod được tạo lại.
- Service DNS ổn định hơn và trỏ tới các endpoint đủ điều kiện theo Service/EndpointSlice.
- `InetUtils` nhìn thấy interface trong Pod network namespace, không phải tất cả NIC của node.
- `server.address=0.0.0.0` có thể dùng để server lắng nghe trên interface trong Pod; địa chỉ quảng bá vẫn là Pod IP hoặc DNS phù hợp với cơ chế discovery.
- Khi dùng Kubernetes-native discovery, không nhất thiết cần đăng ký IP Pod qua Eureka/Consul cho cùng mục đích.

Nếu Spring Cloud discovery provider vẫn được sử dụng trong Kubernetes, hãy xác định consumer ở cùng cluster hay ngoài cluster, rồi chọn Pod IP, node/LoadBalancer address hoặc DNS theo topology thực tế.

## 12. Hostname hay IP address?

Quảng bá hostname thay vì IP có thể phù hợp khi DNS được quản lý ổn định:

```yaml
eureka:
  instance:
    hostname: checkout-01.internal
    prefer-ip-address: false
```

Hostname có lợi thế:

- Không phải cập nhật registration chỉ vì IP thay đổi nếu DNS được cập nhật đúng.
- Có thể hỗ trợ nhiều địa chỉ hoặc failover ở tầng DNS.
- Có thể thể hiện tên định danh dễ quan sát hơn.

Nhưng hostname cũng có điều kiện:

- Consumer phải phân giải được hostname.
- DNS record phải trỏ tới địa chỉ có route phù hợp từ consumer.
- DNS cache và TTL có thể làm chậm quá trình thay đổi.
- TLS certificate phải khớp hostname nếu dùng HTTPS.
- Split-horizon DNS có thể trả địa chỉ khác nhau tùy mạng của client.

IP tường minh phù hợp khi địa chỉ ổn định và topology đơn giản. Hostname phù hợp khi có DNS vận hành tốt và cần tách định danh khỏi IP vật lý.

## 13. IPv4, IPv6 và nhiều địa chỉ trên cùng interface

Một interface có thể có nhiều địa chỉ, ví dụ IPv4 private, IPv6 global và IPv6 link-local. Không phải địa chỉ nào cũng phù hợp để đăng ký dịch vụ.

| Loại địa chỉ | Ví dụ | Lưu ý |
| --- | --- | --- |
| IPv4 loopback | `127.0.0.1` | Chỉ dùng trong cùng network namespace |
| IPv4 private | `10.20.5.18` | Có thể dùng trong mạng nội bộ nếu có route |
| IPv4 public | `203.0.113.18` | Cần kiểm tra firewall/NAT và chính sách công bố |
| IPv6 loopback | `::1` | Chỉ local |
| IPv6 link-local | `fe80::1234` | Chỉ có ý nghĩa trên link; thường cần zone/interface scope |
| IPv6 global | `2001:db8::18` | Có thể định tuyến nếu mạng hỗ trợ |
| IPv6 unique-local | `fd20:5::18` | Dùng trong phạm vi mạng riêng theo thiết kế IPv6 |

### 13.1. IPv6 link-local không phải địa chỉ quảng bá chung

Địa chỉ `fe80::/10` chỉ có ý nghĩa trên một link. Một client ở link khác không thể dùng nó như địa chỉ dịch vụ toàn cục. Nếu buộc phải dùng IPv6, hãy chọn global hoặc unique-local address phù hợp với topology và bảo đảm mọi consumer có route.

### 13.2. URI có IPv6 cần dấu ngoặc vuông

Khi ghép IPv6 literal vào URL, cú pháp thường cần dấu ngoặc vuông:

```text
http://[2001:db8::18]:8080
```

Không ghép chuỗi `host + ":" + port` một cách đơn giản nếu host có thể là IPv6. Dùng `URI`, `InetAddress` và API chuẩn để xử lý địa chỉ.

## 14. Quy trình lựa chọn địa chỉ thực tế

Trước khi cấu hình, hãy trả lời các câu hỏi sau:

1. Consumer nằm ở đâu: cùng host, cùng Docker network, cùng Kubernetes cluster, cùng VPC hay ngoài mạng?
2. Địa chỉ nào có route từ consumer tới server?
3. Có interface nào chỉ dành cho management, backup hoặc VPN không?
4. Ứng dụng cần quảng bá IP hay hostname?
5. Provider có tự dùng `InetUtils` hay có property override riêng?
6. Có cần một địa chỉ duy nhất hay nhiều địa chỉ hợp lệ?
7. Địa chỉ có thay đổi sau khi process khởi động không?
8. Registry/consumer có hỗ trợ IPv6 và DNS policy đang dùng không?

Sau đó:

- Liệt kê interface và địa chỉ trên host/container.
- Xác định subnet ứng dụng.
- Dùng `ignored-interfaces` để loại NIC không phù hợp nếu tên ổn định.
- Dùng `preferred-networks` để ưu tiên subnet cụ thể.
- Nếu hạ tầng cấp địa chỉ tĩnh hoặc DNS ổn định, cân nhắc override ở provider.
- Xác minh địa chỉ được đăng ký thực tế.
- Thử kết nối từ ít nhất một consumer đại diện.

## 15. Ví dụ cấu hình hoàn chỉnh

Giả sử máy chạy `checkout-service` có:

```text
ens160     10.20.5.18       mạng service
ens192     192.168.50.12   mạng backup
docker0    172.17.0.1      Docker bridge
tun0       100.80.10.4     VPN
```

Consumer trong hệ thống chỉ truy cập subnet `10.20.5.0/24`. Cấu hình Spring Cloud:

```yaml
spring:
  application:
    name: checkout-service
  cloud:
    inetutils:
      ignored-interfaces:
        - '^docker0$'
        - '^tun[0-9]+$'
      preferred-networks:
        - '^10[.]20[.]5[.].*'

server:
  address: 0.0.0.0
  port: 8080
```

Nếu dùng Eureka và muốn công bố IP:

```yaml
eureka:
  instance:
    prefer-ip-address: true
```

Trong trường hợp này:

- Server bind trên mọi địa chỉ IPv4 local phù hợp.
- `InetUtils` ưu tiên subnet `10.20.5.*` và bỏ qua Docker bridge/VPN.
- Provider discovery sử dụng host information theo cơ chế tích hợp của nó.
- Consumer nhìn thấy địa chỉ dịch vụ thuộc mạng service.

Nếu cần bảo đảm tuyệt đối IP `10.20.5.18`, có thể cấu hình `eureka.instance.ip-address` tường minh, nhưng phải cập nhật khi IP thay đổi. Đừng vừa dùng override cố định vừa giả định `preferred-networks` sẽ thay thế override đó.

## 16. Chẩn đoán khi registry công bố sai địa chỉ

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Registry hiển thị `127.0.0.1` | Không tìm được non-loopback address hoặc provider bị override | Kiểm tra interface, fallback và cấu hình provider |
| Registry hiển thị IP Docker bridge | `InetUtils` chọn interface bridge | Kiểm tra `ignored-interfaces` và `preferred-networks` |
| Registry hiển thị IP VPN | VPN interface được xem là ứng viên hợp lệ | Loại interface hoặc ưu tiên subnet service |
| IP đăng ký đúng nhưng consumer không gọi được | Route/firewall/NAT không phù hợp | Thử kết nối từ đúng network namespace của consumer |
| Hostname đăng ký đúng nhưng không resolve | DNS record hoặc split-horizon DNS sai | Kiểm tra phân giải từ máy consumer |
| Chỉ một số consumer kết nối được | Các client nằm ở network segment khác nhau | Kiểm tra route, ACL và DNS theo từng segment |
| Sau khi đổi NIC, registry vẫn giữ IP cũ | Host info/registration không tự cập nhật theo thay đổi NIC | Xác minh lifecycle re-registration hoặc restart |
| IPv6 đăng ký nhưng client không gọi được | Client/provider không hỗ trợ hoặc địa chỉ link-local | Kiểm tra loại IPv6, URI và network policy |
| Đã đổi preferred-networks nhưng IP không đổi | Provider có IP/hostname override riêng hoặc config không được nạp | Kiểm tra Environment và registration object cuối cùng |

### 16.1. Công cụ hệ điều hành

Trên Linux:

```bash
ip addr
ip route
ip route get 10.20.5.25
```

Trên Windows:

```powershell
Get-NetIPConfiguration
Get-NetIPAddress
Get-NetRoute
```

Trên macOS:

```bash
ifconfig
netstat -rn
```

Các lệnh này giúp xác định địa chỉ gắn với interface và route tới mạng consumer. Một IP tồn tại trên máy không có nghĩa route hai chiều đã được thiết lập.

### 16.2. Kiểm tra từ phía consumer

Sau khi registry trả về địa chỉ:

1. Lấy host và port chính xác mà discovery client nhận được.
2. Thử DNS resolution nếu host là hostname.
3. Kiểm tra route tới địa chỉ đó.
4. Kiểm tra TCP connection tới port.
5. Kiểm tra TLS/SNI/certificate nếu dùng HTTPS.
6. Gọi health endpoint hoặc một API kiểm thử có xác thực phù hợp.

Không kết luận thành công chỉ từ việc `register()` trả về không có exception. Registration thành công và reachability là hai kết quả khác nhau.

## 17. Kiểm thử lựa chọn địa chỉ

Kiểm thử nên xác minh cấu hình được bind và địa chỉ cuối cùng được provider công bố.

### 17.1. Kiểm tra property binding

Với Spring Boot test, xác minh các property:

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '^10[.]20[.]5[.].*'
      ignored-interfaces:
        - '^docker0$'
```

Kiểm tra bean cấu hình tương ứng có chứa danh sách regex như mong đợi. Đây là test binding, không phải test thuật toán chọn IP của hệ điều hành.

### 17.2. Kiểm tra InetUtils trên môi trường kiểm thử

Có thể gọi `findFirstNonLoopbackHostInfo()` và xác minh IP trả về khớp subnet được ưu tiên. Tuy nhiên, test phụ thuộc các interface thực của máy chạy test; cùng một test có thể cho kết quả khác nhau trên laptop developer, CI runner và container.

Để test ổn định:

- Chạy trong container/network namespace có interface được kiểm soát.
- Ghi nhận danh sách interface và địa chỉ trước khi đánh giá kết quả.
- Không hard-code IP của máy developer.
- Tách test cấu hình regex khỏi integration test phụ thuộc OS.

### 17.3. Kiểm tra Registration thực tế

Với provider discovery:

1. Khởi động application context với cấu hình mạng đã chọn.
2. Chờ auto-registration hoàn tất.
3. Đọc `Registration` hoặc truy vấn registry.
4. Xác minh host/IP/port/metadata được công bố.
5. Dùng consumer test gọi địa chỉ đã đăng ký.
6. Xác minh deregistration khi context đóng nếu provider hỗ trợ.

Đây là kiểm thử quan trọng nhất vì nó kiểm tra kết quả cuối cùng sau khi `InetUtils`, provider configuration và lifecycle registration phối hợp.

## 18. Bảo mật và vận hành

Chọn sai interface không chỉ gây lỗi kết nối mà còn có thể làm lộ service trên mạng không mong muốn.

- Không quảng bá interface quản trị hoặc backup nếu consumer không được phép truy cập.
- Không bind `0.0.0.0` nếu ứng dụng chỉ nên lắng nghe trên một NIC cụ thể.
- Dùng firewall và network policy để giới hạn traffic; `ignored-interfaces` không phải cơ chế bảo mật.
- Kiểm tra địa chỉ được đăng ký không tiết lộ topology nội bộ ngoài phạm vi cần thiết.
- Với HTTPS, bảo đảm certificate SAN khớp hostname/IP mà client sử dụng.
- Khi đổi NIC hoặc subnet, có kế hoạch cập nhật registration và kiểm tra các consumer.
- Không dùng fallback IP tùy tiện để che giấu lỗi phát hiện interface.
- Theo dõi registration có địa chỉ không hợp lệ hoặc không thể kết nối.

## 19. Nguyên tắc thiết kế

- Xác định consumer network trước khi chọn địa chỉ quảng bá.
- Phân biệt rõ bind address và advertised address.
- Dùng `preferred-networks` khi có subnet ứng dụng rõ ràng.
- Dùng `ignored-interfaces` khi interface không phù hợp có tên ổn định.
- Không dựa vào thứ tự interface do hệ điều hành trả về.
- Chỉ bật `use-only-site-local-interfaces` khi semantics site-local phù hợp với topology.
- Xem `default-ip-address` và `default-hostname` là fallback, không phải cấu hình NIC.
- Kiểm tra provider có dùng `InetUtils` hay có override riêng.
- Trong Kubernetes, ưu tiên service DNS khi phù hợp thay vì giữ Pod IP cố định.
- Kiểm thử từ network namespace của consumer, không chỉ từ host server.
- Đảm bảo TLS, firewall, routing và service registration cùng sử dụng một định danh nhất quán.

## 20. Tổng kết

Khi máy có nhiều network interface, việc chọn IP đầu tiên không phải lúc nào cũng cho kết quả đúng. Spring Cloud Commons cung cấp `InetUtils` và các property `spring.cloud.inetutils` để ưu tiên subnet, loại interface và thiết lập fallback. `preferred-networks` giúp chọn địa chỉ thuộc mạng ứng dụng; `ignored-interfaces` loại những NIC như bridge hoặc VPN không phù hợp; `use-only-site-local-interfaces` giới hạn theo phân loại địa chỉ của Java.

Điều quan trọng là phân biệt địa chỉ bind của server với địa chỉ được công bố cho registry. `server.address=0.0.0.0` có thể giúp server lắng nghe trên nhiều interface nhưng không phải địa chỉ để consumer kết nối. Provider như Eureka có thể có hostname/IP override riêng; Kubernetes có thể phù hợp hơn với Service DNS thay vì quảng bá IP của một interface.

Một địa chỉ chỉ đúng khi consumer thực tế có thể phân giải và định tuyến tới nó. Vì vậy, sau khi cấu hình `InetUtils`, hãy kiểm tra registration cuối cùng, route, firewall, DNS và kết nối từ phía consumer. Đây là cách bảo đảm discovery trả về một endpoint có thể sử dụng trong hệ thống phân tán.

## 21. Tài liệu tham khảo

- [Spring Cloud Commons — Ignore Network Interfaces](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/host-info.html)
- [Spring Cloud Commons — InetUtils API](https://docs.spring.io/spring-cloud-commons/docs/current/javadoc-api/org/springframework/cloud/commons/util/InetUtils.html)
- [Spring Cloud Commons — InetUtilsProperties API](https://docs.spring.io/spring-cloud-commons/docs/current/javadoc-api/org/springframework/cloud/commons/util/InetUtilsProperties.html)
- [Spring Cloud Netflix — Eureka Instance Configuration](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot Reference — Embedded Web Server Configuration](https://docs.spring.io/spring-boot/reference/web/servlet.html)
- [Java API — NetworkInterface](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/NetworkInterface.html)
- [Java API — InetAddress](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html)
