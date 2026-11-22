# Vai trò InetUtils và HostInfo

> **Chương:** Định danh và mạng  
> **Module:** SPRING_CLOUD_CORE

Trong một ứng dụng chạy trên máy có nhiều network interface, việc lấy địa chỉ IP bằng một lời gọi đơn giản như `InetAddress.getLocalHost()` không phải lúc nào cũng cho ra địa chỉ mà dịch vụ khác có thể sử dụng. Máy có thể đồng thời có loopback, card mạng LAN, VPN, interface Docker/Kubernetes và interface ảo. Nếu ứng dụng quảng bá nhầm địa chỉ, service registry có thể lưu một endpoint không thể truy cập, khiến service discovery tìm thấy instance nhưng request gọi tới instance đó thất bại.

Spring Cloud Commons cung cấp **`InetUtils`** để tìm thông tin host phù hợp từ các network interface và **`InetUtils.HostInfo`** để biểu diễn hostname cùng địa chỉ IP được chọn. Hai thành phần này hỗ trợ các tích hợp cần biết địa chỉ của ứng dụng. Chúng giúp chuẩn hóa việc nhận diện host, nhưng không tự đăng ký service, không tạo địa chỉ có thể định tuyến qua NAT và không thay thế cấu hình mạng của nền tảng triển khai.

## 1. Vì sao cần InetUtils?

Một máy chủ hoặc container có thể nhìn thấy nhiều địa chỉ mạng:

- `127.0.0.1` hoặc `::1`: loopback, chỉ dùng bên trong host/network namespace.
- Địa chỉ của card Ethernet hoặc Wi-Fi.
- Địa chỉ VPN.
- Địa chỉ interface Docker bridge hoặc Kubernetes CNI.
- Địa chỉ interface ảo do hypervisor hoặc phần mềm mạng tạo ra.
- Địa chỉ IPv4 hoặc IPv6 được gán cho cùng một interface.

Nếu ứng dụng chọn địa chỉ đầu tiên mà hệ điều hành trả về, kết quả có thể không phù hợp với mục đích quảng bá dịch vụ. Ví dụ, một instance trong container có thể chọn địa chỉ loopback hoặc IP bridge chỉ truy cập được từ một network cụ thể.

`InetUtils` cung cấp cách tìm một địa chỉ không phải loopback theo các chính sách cấu hình như bỏ qua interface, ưu tiên dải mạng và chỉ chấp nhận địa chỉ site-local. Nhờ đó, ứng dụng có thể lựa chọn thông tin host nhất quán hơn giữa các môi trường.

### 1.1. Không phải mọi địa chỉ IP đều có thể dùng làm service endpoint

Một địa chỉ IP hợp lệ trên máy chưa chắc có thể được client ở nơi khác truy cập.

| Loại địa chỉ | Ví dụ | Ý nghĩa khi quảng bá |
| --- | --- | --- |
| Loopback | `127.0.0.1`, `::1` | Chỉ trỏ về chính network namespace của instance; thường không dùng cho instance discovery |
| Private IPv4 | `10.20.1.15`, `192.168.10.8` | Có thể dùng trong mạng riêng nếu các client có route tới dải đó |
| Link-local | `169.254.x.x` | Phạm vi liên kết cục bộ; thường không phù hợp cho giao tiếp service thông thường |
| Public IPv4 | Một địa chỉ IP công khai | Có thể truy cập nếu firewall, routing và NAT cho phép |
| IPv6 global | Địa chỉ IPv6 định tuyến toàn cục | Cần client, registry và hạ tầng mạng hỗ trợ IPv6 |
| Container bridge IP | Ví dụ `172.18.0.4` | Có thể chỉ truy cập được trong bridge hoặc overlay network tương ứng |

Việc chọn địa chỉ cần gắn với topology triển khai. Trong Kubernetes, ứng dụng thường cần quảng bá địa chỉ Pod hoặc một địa chỉ do nền tảng cung cấp, tùy cách service registration được cấu hình. Một IP private không tự động đồng nghĩa với IP có thể truy cập từ mọi mạng.

## 2. InetUtils và HostInfo là gì?

`InetUtils` thuộc package `org.springframework.cloud.commons.util`. Nó cung cấp các thao tác tìm địa chỉ không phải loopback và chuyển thông tin địa chỉ thành một đối tượng host.

API thường dùng:

~~~java
InetUtils.HostInfo hostInfo =
        inetUtils.findFirstNonLoopbackHostInfo();
~~~

`InetUtils.HostInfo` là kiểu dữ liệu chứa thông tin host đã chọn, thường gồm:

- `hostname`: tên host được phân giải từ địa chỉ.
- `ipAddress`: địa chỉ IP được biểu diễn dưới dạng chuỗi.

Có thể đọc hai giá trị qua getter:

~~~java
String hostname = hostInfo.getHostname();
String ipAddress = hostInfo.getIpAddress();
~~~

Các API thường gặp của `InetUtils`:

| API | Vai trò |
| --- | --- |
| `findFirstNonLoopbackAddress()` | Tìm một địa chỉ mạng phù hợp, không phải loopback |
| `findFirstNonLoopbackHostInfo()` | Tìm địa chỉ và trả về thông tin host tương ứng |
| `close()` | Giải phóng tài nguyên nội bộ của InetUtils khi bean bị đóng |

Tên và chi tiết API có thể thay đổi theo phiên bản Spring Cloud Commons. Khi viết code theo một release train cụ thể, hãy đối chiếu Javadoc/source của đúng phiên bản dependency đang dùng.

### 2.1. Phân biệt InetUtils với InetAddress

`java.net.InetAddress` là API chuẩn của Java để biểu diễn địa chỉ IP và phân giải hostname. Nó không tự áp dụng chính sách lựa chọn network interface dành cho ứng dụng Spring Cloud.

`InetUtils` bổ sung chính sách lựa chọn host trên các interface của hệ thống. Có thể hiểu:

- `InetAddress` biểu diễn địa chỉ mạng và hỗ trợ phân giải tên.
- `InetUtils` tìm địa chỉ phù hợp theo chính sách cấu hình.
- `HostInfo` đóng gói hostname và IP được chọn để thành phần khác sử dụng.

Vì vậy, không nên thay `InetUtils` bằng `InetAddress.getLocalHost()` nếu yêu cầu là chọn địa chỉ non-loopback theo chính sách Spring Cloud.

## 3. Sử dụng InetUtils trong ứng dụng

Khi Spring Cloud Commons có mặt trên classpath và auto-configuration tương ứng hoạt động, ứng dụng có thể inject bean `InetUtils`.

Ví dụ một thành phần ghi nhận thông tin host sau khi ứng dụng khởi động:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.commons.util.InetUtils;
import org.springframework.stereotype.Component;

@Component
public class HostInfoReporter implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(HostInfoReporter.class);

    private final InetUtils inetUtils;

    public HostInfoReporter(InetUtils inetUtils) {
        this.inetUtils = inetUtils;
    }

    @Override
    public void run(ApplicationArguments args) {
        InetUtils.HostInfo hostInfo =
                inetUtils.findFirstNonLoopbackHostInfo();

        log.info("Selected host information: hostname={}, ipAddress={}",
                hostInfo.getHostname(), hostInfo.getIpAddress());
    }
}
~~~

Ví dụ này chỉ dùng để quan sát thông tin host. Nó không thay thế cấu hình địa chỉ quảng bá của service registration. Nếu ứng dụng cần đăng ký địa chỉ cụ thể, hãy kiểm tra cơ chế registration mà discovery client đang sử dụng và xác định nó lấy hostname/IP từ nguồn nào.

Không nên gọi lại việc dò interface trong mỗi request. Thông tin host thường được xác định ở giai đoạn khởi động hoặc khi cấu hình mạng thay đổi theo một quy trình triển khai có kiểm soát.

### 3.1. Không tự đóng InetUtils do container quản lý

Nếu `InetUtils` được Spring tạo và quản lý như một bean, ApplicationContext chịu trách nhiệm gọi destruction callback tương ứng. Không gọi `inetUtils.close()` thủ công sau mỗi lần đọc `HostInfo`. Đóng bean quá sớm có thể làm các thành phần khác không sử dụng được tài nguyên nội bộ của nó.

Nếu tự tạo `InetUtils` ngoài Spring container, code tạo ra instance phải chịu trách nhiệm đóng nó khi không còn sử dụng.

## 4. Cấu hình lựa chọn interface và địa chỉ

`InetUtils` có các thuộc tính cấu hình dưới prefix `spring.cloud.inetutils`. Các thuộc tính này giúp loại bỏ interface không phù hợp, ưu tiên dải IP mong muốn và định nghĩa giá trị dự phòng.

Ví dụ:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
        - br-.*
      preferred-networks:
        - '10\.20\..*'
        - '192\.168\.50\..*'
      use-only-site-local-interfaces: true
      timeout-seconds: 2
      default-hostname: localhost
      default-ip-address: 127.0.0.1
~~~

Các giá trị regex trong ví dụ được đặt trong dấu nháy đơn của YAML để giữ nguyên dấu gạch chéo ngược. Hãy điều chỉnh tên interface và dải mạng theo hạ tầng thật.

### 4.1. ignored-interfaces

`ignored-interfaces` là danh sách pattern dùng để bỏ qua interface theo tên. Ví dụ:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
        - tun.*
~~~

Có thể dùng để bỏ qua một bridge hoặc interface VPN không được phép dùng làm địa chỉ quảng bá. Pattern được dùng để so khớp tên interface; nó không phải danh sách địa chỉ IP.

Không nên bỏ qua mọi interface ảo một cách máy móc. Trong một số nền tảng, interface ảo hoặc CNI chính là đường mạng hợp lệ để các Pod giao tiếp. Trước khi thêm pattern, hãy xác định interface đó phục vụ traffic nào.

### 4.2. preferred-networks

`preferred-networks` cho phép ưu tiên các địa chỉ khớp với pattern mạng. Ví dụ:

~~~yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '10\.20\..*'
        - '192\.168\.50\..*'
~~~

Nếu host có nhiều interface, cấu hình này giúp chọn địa chỉ trong dải mong muốn. Các pattern là biểu thức chính quy, không phải CIDR notation. Ví dụ `10.20.0.0/16` không nên được đưa vào như thể InetUtils tự hiểu CIDR; hãy viết regex phù hợp hoặc dùng cơ chế cấu hình địa chỉ riêng của nền tảng nếu cần kiểm soát CIDR chính xác.

Nếu không có địa chỉ nào khớp preferred pattern, kết quả còn phụ thuộc các bộ lọc và logic fallback của phiên bản InetUtils đang dùng. Không nên giả định một dải preferred luôn tồn tại trong mọi môi trường; hãy xác minh kết quả khi khởi động.

### 4.3. use-only-site-local-interfaces

`use-only-site-local-interfaces` giới hạn lựa chọn vào địa chỉ được Java phân loại là site-local. Với IPv4, nhóm này thường bao gồm các dải private như `10.0.0.0/8`, `172.16.0.0/12` và `192.168.0.0/16`.

Thuộc tính này có thể hữu ích khi ứng dụng chỉ giao tiếp trong mạng riêng. Tuy nhiên, site-local không đồng nghĩa với “được mọi service khác truy cập”. Một địa chỉ private vẫn có thể bị cô lập bởi subnet, network policy, firewall hoặc routing.

Nếu ứng dụng cần quảng bá public IP, địa chỉ NAT hoặc địa chỉ do nền tảng cấp, đừng bật bộ lọc này mà không kiểm tra hành vi. Với yêu cầu mạng phức tạp, có thể cần cấu hình hostname/IP quảng bá trực tiếp ở discovery client hoặc platform.

### 4.4. timeout-seconds

`timeout-seconds` giới hạn thời gian chờ trong một số thao tác phân giải thông tin host, đặc biệt khi cần lấy hostname từ địa chỉ. DNS reverse lookup chậm có thể làm kéo dài quá trình tìm host.

Đặt timeout hữu hạn để việc xác định host không làm startup chờ quá lâu. Giá trị nhỏ hơn giúp giảm thời gian chờ, nhưng có thể khiến hostname không được phân giải đầy đủ; IP vẫn là thông tin mạng riêng biệt và có thể được sử dụng để nhận diện endpoint.

Không dùng timeout này như một timeout tổng cho mọi request của ứng dụng hoặc cho toàn bộ service discovery.

### 4.5. default-hostname và default-ip-address

Khi không tìm được địa chỉ phù hợp hoặc không thể phân giải thông tin host theo cách mong đợi, các giá trị dự phòng có thể được dùng:

~~~yaml
spring:
  cloud:
    inetutils:
      default-hostname: localhost
      default-ip-address: 127.0.0.1
~~~

Giá trị dự phòng giúp ứng dụng có kết quả xác định thay vì nhận thông tin rỗng trong một số tình huống. Nhưng `localhost` và `127.0.0.1` thường không phải endpoint phù hợp để đăng ký trong môi trường nhiều instance. Nếu registry nhận địa chỉ loopback, các service khác có thể gọi nhầm chính máy của chúng.

Trong production, nên cấu hình để việc không tìm được địa chỉ quảng bá phù hợp trở thành tín hiệu cần xử lý, thay vì âm thầm đăng ký giá trị mặc định không thể truy cập.

## 5. Hostname và IP address có ý nghĩa khác nhau

Hostname là tên được phân giải từ địa chỉ hoặc được cung cấp theo môi trường; IP address là địa chỉ mạng. Hai giá trị có thể liên quan nhưng không thể thay thế cho nhau trong mọi tình huống.

Ví dụ:

| HostInfo field | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `hostname` | `order-7f8c9d.internal` | Tên host có thể được DNS hoặc hạ tầng nội bộ phân giải |
| `ipAddress` | `10.20.1.15` | Địa chỉ IP của interface được chọn |

Hostname có thể phụ thuộc DNS, search domain và reverse lookup. Một địa chỉ có thể không có bản ghi PTR phù hợp; hostname nhận được cũng có thể là tên không được các client khác phân giải.

IP có thể thay đổi khi container hoặc instance được tạo lại. Không nên dùng riêng IP làm định danh bền vững cho một instance nếu nền tảng cấp phát IP động.

### 5.1. Định danh service và định danh instance

Trong Spring Cloud, cần phân biệt:

| Thông tin | Ví dụ | Vai trò |
| --- | --- | --- |
| Application/service name | `order-service` | Tên logic để client tìm dịch vụ |
| Hostname | `order-7f8c9d.internal` | Tên host của instance |
| IP address | `10.20.1.15` | Địa chỉ mạng của instance |
| Port | `8080` | Cổng mà instance nhận traffic |
| Instance ID | `order-service:pod-7f8c9d` | Định danh một bản chạy cụ thể trong registry |

`InetUtils` và `HostInfo` cung cấp thông tin hostname/IP. Tên service, port, instance ID, metadata và trạng thái health thường do ứng dụng, discovery client hoặc nền tảng triển khai cung cấp.

Không dùng hostname hoặc IP làm thay thế cho `spring.application.name`. Một service có thể có nhiều instance với hostname/IP khác nhau nhưng cùng tên logic.

## 6. Quan hệ với service discovery và service registration

Spring Cloud Commons định nghĩa các abstraction chung cho service discovery và registration. Các implementation như Eureka, Consul hoặc một registry khác có thể cần hostname/IP khi đăng ký instance.

`InetUtils` có thể là nguồn cung cấp thông tin host cho một số tích hợp hoặc được ứng dụng dùng để thiết lập giá trị quảng bá. Tuy nhiên:

- `InetUtils` không tự đăng ký instance vào registry.
- `HostInfo` không chứa toàn bộ registration metadata.
- Việc chọn IP không mở firewall hoặc tạo route.
- Việc registry lưu endpoint không bảo đảm endpoint có thể truy cập từ mọi client.
- Cách discovery client chọn hostname/IP phụ thuộc implementation và cấu hình của nó.

Trước khi thay đổi `spring.cloud.inetutils`, hãy xác định discovery client đang dùng nguồn hostname/IP nào. Một số implementation cho phép cấu hình hostname hoặc IP quảng bá riêng; các thuộc tính cụ thể không giống nhau giữa Eureka, Consul và những registry khác.

### 6.1. Ví dụ cấu hình host và service name

Một ứng dụng có thể khai báo tên service riêng:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    inetutils:
      preferred-networks:
        - '10\.20\..*'
~~~

Ở đây `spring.application.name` xác định tên logic của ứng dụng, còn InetUtils tìm host theo chính sách mạng. Discovery client cần được cấu hình tương thích để đăng ký địa chỉ đúng. Chỉ đặt preferred network không có nghĩa mọi discovery client chắc chắn sẽ quảng bá IP được chọn theo cùng một cách.

Nếu môi trường có địa chỉ quảng bá do platform cung cấp, hãy dùng cấu hình tích hợp chính thức của discovery client hoặc biến môi trường được platform inject. Không ép InetUtils chọn một interface không thể truy cập chỉ vì địa chỉ đó có vẻ hợp lệ trên máy.

## 7. Tình huống nhiều network interface

Giả sử một VM có các interface:

| Interface | Địa chỉ | Mục đích |
| --- | --- | --- |
| `lo` | `127.0.0.1` | Loopback |
| `eth0` | `10.20.1.15` | Mạng service nội bộ |
| `tun0` | `10.8.0.2` | VPN quản trị |
| `docker0` | `172.18.0.1` | Docker bridge |

Nếu service trong cluster truy cập qua mạng `10.20.0.0/16`, ứng dụng có thể ưu tiên dải này và bỏ qua interface VPN hoặc Docker bridge:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - tun.*
        - docker0
      preferred-networks:
        - '10\.20\..*'
      use-only-site-local-interfaces: true
~~~

Cấu hình chỉ là ví dụ. Tên interface và địa chỉ thực tế có thể khác theo hệ điều hành, container runtime và network plugin. Cần kiểm tra trong đúng network namespace mà JVM đang chạy.

Nếu service chạy trong container, kết quả dò interface là kết quả nhìn thấy từ container. Nó không tự biết public IP của node hoặc địa chỉ load balancer bên ngoài. Khi cần quảng bá địa chỉ khác với địa chỉ interface cục bộ, hãy lấy giá trị đó từ platform hoặc cấu hình discovery client.

## 8. IPv4, IPv6, DNS và các giới hạn thực tế

### 8.1. IPv4 và IPv6

Một interface có thể có nhiều địa chỉ, gồm IPv4 và IPv6. Client, registry, DNS và network policy phải thống nhất loại địa chỉ mà chúng hỗ trợ.

Không nên giả định mọi địa chỉ IPv6 đều có thể đưa trực tiếp vào URL mà không cần xử lý dấu ngoặc vuông. Ví dụ địa chỉ IPv6 literal trong URL thường có dạng `http://[2001:db8::10]:8080`.

Nếu ứng dụng chỉ hỗ trợ IPv4, cần xác nhận địa chỉ được chọn và cấu hình discovery client phù hợp. Không nên tự cắt hoặc chuyển đổi chuỗi địa chỉ để ép một địa chỉ IPv6 thành IPv4.

### 8.2. DNS và reverse lookup

Hostname có thể được phân giải từ IP qua DNS hoặc cơ chế name service của hệ điều hành. Trong môi trường container, reverse DNS có thể không được cấu hình; kết quả hostname có thể là tên ngắn, tên nội bộ hoặc giá trị mặc định.

Hãy kiểm tra cả forward lookup (hostname sang IP) và reverse lookup (IP sang hostname) nếu hostname được dùng trong registration. Một hostname chỉ có thể reverse-resolve trong subnet nội bộ có thể không hữu ích cho client ở mạng khác.

### 8.3. NAT và địa chỉ quảng bá

Nếu instance nằm sau NAT, địa chỉ private trên interface có thể khác địa chỉ mà client bên ngoài nhìn thấy. InetUtils chỉ quan sát interface trong môi trường của tiến trình; nó không truy vấn router để tự suy ra public/NAT address.

Trong trường hợp đó, cần một nguồn sự thật rõ ràng cho advertised address: cấu hình platform, DNS, service mesh, load balancer hoặc thuộc tính riêng của discovery provider.

### 8.4. Địa chỉ động và vòng đời instance

Trong container orchestration, IP của Pod có thể đổi sau khi reschedule. Registry cần cập nhật registration khi instance dừng và instance mới khởi động. HostInfo không phải cơ chế theo dõi thay đổi địa chỉ mạng liên tục.

Nếu địa chỉ interface thay đổi trong khi JVM vẫn chạy, không nên giả định một giá trị HostInfo đã đọc lúc khởi động tự cập nhật. Cần cơ chế refresh/re-registration được discovery integration hỗ trợ hoặc restart/rolling replacement theo quy trình platform.

## 9. Kiểm tra thông tin host trong môi trường chạy

Khi một instance đăng ký sai địa chỉ, hãy kiểm tra từ chính môi trường mà JVM chạy:

1. Liệt kê interface và địa chỉ thực tế.
2. Xác định interface nào dùng cho traffic giữa các service.
3. Kiểm tra các pattern ignored và preferred.
4. Kiểm tra bộ lọc site-local.
5. Xác nhận hostname có phân giải được trong DNS cần thiết.
6. So sánh HostInfo với địa chỉ mà discovery client thực sự đăng ký.
7. Kiểm tra route, firewall và network policy từ một client ở mạng đích.

Trên Linux, các lệnh thường dùng để xem interface:

~~~bash
ip address
ip route
hostname
getent hosts "$(hostname)"
~~~

Các lệnh này chỉ phục vụ chẩn đoán trên môi trường Linux; container tối giản có thể không cài đủ công cụ. Không chạy các lệnh trên trong Java code hoặc ở mỗi request.

### 9.1. Ghi log HostInfo có kiểm soát

Có thể ghi lại hostname và IP đã chọn lúc startup:

~~~java
InetUtils.HostInfo hostInfo =
        inetUtils.findFirstNonLoopbackHostInfo();

log.info("Host selected for diagnostics: hostname={}, ipAddress={}",
        hostInfo.getHostname(), hostInfo.getIpAddress());
~~~

Thông tin này giúp đối chiếu với registration metadata. Nếu IP nội bộ hoặc hostname tiết lộ topology nhạy cảm, giới hạn quyền truy cập log và tránh đưa dữ liệu này vào log công khai.

## 10. Kiểm thử cấu hình InetUtils

Không nên viết test phụ thuộc vào interface của máy developer hoặc CI rồi mong đợi một IP cố định. Địa chỉ mạng thay đổi theo runner, VPN, container và hệ điều hành.

Có thể kiểm thử phần cấu hình được bind vào `InetUtilsProperties` trong một Spring context có các giá trị tường minh:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.commons.util.InetUtilsProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.cloud.inetutils.ignored-interfaces[0]=docker0",
        "spring.cloud.inetutils.preferred-networks[0]=10\\.20\\..*",
        "spring.cloud.inetutils.use-only-site-local-interfaces=true",
        "spring.cloud.inetutils.timeout-seconds=2"
})
class InetUtilsPropertiesTest {

    @Autowired
    InetUtilsProperties properties;

    @Test
    void bindsNetworkSelectionPolicy() {
        assertThat(properties.getIgnoredInterfaces())
                .contains("docker0");
        assertThat(properties.getPreferredNetworks())
                .contains("10\\.20\\..*");
        assertThat(properties.isUseOnlySiteLocalInterfaces()).isTrue();
        assertThat(properties.getTimeoutSeconds()).isEqualTo(2);
    }
}
~~~

Ví dụ kiểm tra binding policy thay vì kiểm tra một IP cố định. Tên getter và khả năng inject `InetUtilsProperties` phụ thuộc phiên bản Spring Cloud Commons; nếu phiên bản đang dùng thay đổi API hoặc đăng ký properties khác, hãy điều chỉnh test theo đúng dependency.

### 10.1. Kiểm thử tích hợp trên môi trường đại diện

Ngoài test binding, nên có smoke test trên container hoặc staging để xác nhận:

- HostInfo không trả loopback ngoài dự kiến.
- IP được chọn thuộc dải mạng được phép.
- Hostname có thể phân giải từ các client cần truy cập.
- Registry nhận đúng advertised address và port.
- Client từ subnet thực tế kết nối thành công.
- Khi không có interface phù hợp, giá trị fallback không làm instance đăng ký sai mà không có cảnh báo.

Test tích hợp mạng nên xác nhận khả năng kết nối từ phía client, không chỉ xác nhận chuỗi IP có dạng hợp lệ.

## 11. Lỗi thường gặp và cách tránh

1. **Chọn loopback:** kiểm tra interface và policy; không quảng bá `127.0.0.1` hoặc `::1` cho client ở instance khác.
2. **Chọn nhầm Docker bridge/VPN:** dùng ignored interface hoặc preferred network sau khi xác định đúng interface của traffic service.
3. **Dùng CIDR như regex:** preferred network dùng pattern; chuyển sang regex phù hợp hoặc dùng cơ chế cấu hình mạng khác.
4. **Bật site-local nhưng cần public address:** site-local lọc theo loại địa chỉ, không thay thế advertised address do platform cung cấp.
5. **Cho rằng IP private luôn truy cập được:** kiểm tra route, firewall, subnet và network policy.
6. **Dựa vào reverse DNS không ổn định:** kiểm tra forward/reverse lookup và cấu hình hostname rõ ràng nếu discovery cần tên ổn định.
7. **Nhầm HostInfo với service identity:** tên service, port và instance ID cần được cung cấp riêng.
8. **Cho rằng InetUtils tự đăng ký service:** discovery client hoặc registration integration mới chịu trách nhiệm gửi metadata tới registry.
9. **Dùng fallback localhost trong production:** xác thực địa chỉ quảng bá trước khi cho instance đăng ký.
10. **Giả định HostInfo tự cập nhật khi network đổi:** xác định lại host và thực hiện re-registration hoặc thay instance theo lifecycle triển khai.

## 12. Quy trình lựa chọn địa chỉ cho Spring Cloud service

Khi triển khai một dịch vụ trong module `SPRING_CLOUD_CORE`, hãy thực hiện:

1. Xác định client nào cần truy cập instance và chúng nằm trong subnet/network nào.
2. Xem các network interface từ bên trong đúng VM hoặc container.
3. Quyết định có chỉ dùng site-local address hay không.
4. Bỏ qua interface không phục vụ traffic service.
5. Ưu tiên dải mạng mà client có thể định tuyến tới.
6. Đặt timeout và giá trị fallback có chủ đích.
7. Đọc HostInfo và đối chiếu với hostname/IP mà discovery client đăng ký.
8. Kiểm tra kết nối thực tế từ một client trong mạng đích.
9. Xác định cách xử lý khi IP thay đổi hoặc instance được tạo lại.
10. Ghi log/metric đủ để chẩn đoán nhưng không công khai topology nhạy cảm.

**Điểm ghi nhớ:** `InetUtils` giúp tìm địa chỉ host phù hợp từ các network interface theo chính sách cấu hình; `InetUtils.HostInfo` đóng gói hostname và IP được chọn. Chúng hỗ trợ nhận diện host trong hệ sinh thái Spring Cloud Commons, còn service name, instance ID, port, registration và khả năng định tuyến thuộc các phần khác của hệ thống. Muốn service discovery hoạt động đúng, phải chọn địa chỉ mà client thực sự truy cập được trong topology mạng của **SPRING_CLOUD_CORE**.
