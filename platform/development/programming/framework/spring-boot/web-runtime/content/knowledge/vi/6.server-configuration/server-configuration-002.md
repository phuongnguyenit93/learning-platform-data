# Phân biệt localhost, địa chỉ cụ thể và mọi giao diện mạng khi cấu hình Spring Boot

## Mục tiêu bài học

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của địa chỉ **localhost/loopback**, một **địa chỉ IP cụ thể** và địa chỉ **wildcard** khi máy chủ HTTP mở cổng lắng nghe.
2. Cấu hình server.address và server.port trong ứng dụng Spring Boot 3.3.x.
3. Dự đoán request nào có thể đến được server từ cùng máy, máy khác trong LAN, container hoặc mạng bên ngoài.
4. Phân biệt địa chỉ server **bind** với hostname mà client dùng để **connect**, địa chỉ đích public, DNS, HTTP Host header và CORS.
5. Kiểm tra socket đang lắng nghe bằng curl, ss, netstat hoặc PowerShell; phát hiện lỗi bind sai IP, firewall, NAT và IPv4/IPv6.
6. Áp dụng cấu hình hợp lý cho phát triển tại máy, backend chạy sau reverse proxy, Docker và Kubernetes.

Kiến thức tập trung vào embedded HTTP server của **Spring Boot 3.3.x với Java 17+**. Các nguyên tắc TCP/IP áp dụng rộng hơn cho Tomcat, Jetty, Undertow và Reactor Netty. Ví dụ dùng cổng 8080; các địa chỉ 192.168.1.50 và 192.168.1.100 chỉ là địa chỉ minh họa trong mạng nội bộ, phải thay bằng IP thật thuộc môi trường của bạn.

## 1. Server thực sự “lắng nghe trên địa chỉ” nghĩa là gì?

Một HTTP server dùng TCP thường yêu cầu hệ điều hành tạo một listening socket gắn với **địa chỉ IP cục bộ và cổng**, ví dụ:

~~~text
127.0.0.1:8080
192.168.1.50:8080
0.0.0.0:8080
[::1]:8080
[::]:8080
~~~

Khi một client muốn kết nối, nó gửi gói mạng tới **IP đích và port đích**. Hệ điều hành nhận gói trên giao diện mạng thích hợp, xem có listening socket tương ứng hay không, rồi chuyển kết nối đã được chấp nhận cho server.

Hai khái niệm cần tách:

- **Bind address:** địa chỉ cục bộ mà server đăng ký để nhận kết nối, do server và hệ điều hành quyết định.
- **Destination address:** địa chỉ IP mà client thực sự gửi request đến sau khi phân giải hostname và lựa chọn route.

Ví dụ máy chạy Spring Boot có hai giao diện:

~~~text
Máy A chạy Spring Boot
  |
  +-- lo       127.0.0.1       (loopback, tự gọi chính mình)
  |
  +-- Wi-Fi    192.168.1.50    (mạng LAN)
  |
  +-- VPN      10.8.0.7        (mạng VPN)
~~~

Bind 127.0.0.1:8080 nghĩa là nhận kết nối hướng tới loopback; bind 192.168.1.50:8080 nghĩa là nhận kết nối hướng tới địa chỉ LAN đó; bind 0.0.0.0:8080 nghĩa là nhận kết nối trên các địa chỉ IPv4 cục bộ tương ứng, bao gồm loopback, Wi-Fi và VPN, nếu không có rào cản mạng khác.

**Bind thành công không bảo đảm có thể truy cập từ xa.** Client còn cần route tới IP, port được mở bởi firewall/security group, đường NAT hoặc proxy phù hợp và server thực sự đang chạy.

## 2. localhost và loopback: chỉ quay lại chính máy đang gọi

**localhost** là tên máy đặc biệt được hệ thống phân giải thành địa chỉ loopback, thường gồm:

- **127.0.0.1:** loopback IPv4, một địa chỉ thuộc khối 127.0.0.0/8.
- **::1:** loopback IPv6.

Dòng thử kết nối:

~~~text
Browser trên máy A -> http://localhost:8080
      |
      v
localhost -> 127.0.0.1 hoặc ::1 trên MÁY A
      |
      v
Server lắng nghe loopback trên máy A
~~~

Một máy B khác truy cập http://localhost:8080 sẽ tìm server trên **máy B**, không phải máy A.

Điều này cực kỳ quan trọng khi sử dụng:

- Điện thoại thật và máy laptop: localhost trên điện thoại là điện thoại.
- Docker container: localhost trong container là chính container đó.
- Kubernetes Pod: localhost là loopback thuộc network namespace của Pod.
- Máy ảo: localhost trong VM là VM.
- Reverse proxy ở một host khác: localhost từ proxy trỏ về host của proxy.

### Cấu hình loopback IPv4 rõ ràng

Trong src/main/resources/application.yml:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Hoặc application.properties:

~~~properties
server.address=127.0.0.1
server.port=8080
~~~

Khi ứng dụng bind thành công, request từ **cùng máy/network namespace** tới http://127.0.0.1:8080 có thể đi đến server. Client trên máy khác không thể đi tới loopback của máy A bằng cách gõ localhost của máy B.

Ưu điểm: giới hạn phạm vi tiếp nhận network ở mức hệ điều hành, phù hợp với bài tập local hoặc ứng dụng chỉ được reverse proxy cùng host truy cập.

Giới hạn: loopback không tự thay thế xác thực, phân quyền hay bảo mật dữ liệu. Các tiến trình khác trên **cùng host/network namespace** vẫn có thể kết nối nếu không có rào cản bổ sung.

### Vì sao không nên phụ thuộc mơ hồ vào tên localhost?

Khi đặt:

~~~yaml
server:
  address: localhost
~~~

Spring Boot chuyển địa chỉ này thành InetAddress, và kết quả phụ thuộc cơ chế phân giải tên, IPv4/IPv6 và môi trường. Nếu localhost được phân giải ưu tiên ::1 nhưng client cố truy cập 127.0.0.1, bạn có thể nhìn thấy hiện tượng cùng chữ localhost nhưng đường kết nối khác nhau.

Để thực hành có thể đoán trước, dùng **127.0.0.1** cho thử nghiệm thuần IPv4 hoặc **::1** cho thử nghiệm thuần IPv6. Có thể kiểm tra thêm bằng curl --ipv4 hoặc curl --ipv6.

## 3. Địa chỉ IP cụ thể: bind vào một IP cục bộ đã tồn tại

Máy A có địa chỉ LAN 192.168.1.50. Cấu hình:

~~~yaml
server:
  address: 192.168.1.50
  port: 8080
~~~

Ý nghĩa: socket nhận kết nối nhắm tới **192.168.1.50:8080**, không tự nhận kết nối nhắm tới 127.0.0.1:8080 hoặc một IP khác trên máy.

~~~text
Máy A có IP 192.168.1.50, server bind 192.168.1.50:8080

Từ máy A -> http://192.168.1.50:8080       Có thể tới
Từ máy A -> http://127.0.0.1:8080            Không tới listener này
Từ máy B -> http://192.168.1.50:8080         Có thể tới, nếu route/firewall cho phép
Từ máy B -> http://localhost:8080            Trỏ về máy B, không tới A
~~~

**Điều kiện tiên quyết:** IP được bind phải là địa chỉ đang có hiệu lực trên host hoặc network namespace tương ứng. Nếu đặt nhầm 192.168.1.50 trong khi host chỉ có 192.168.1.51, server có thể không khởi động và báo lỗi tương đương “Cannot assign requested address” hoặc “BindException”.

Trường hợp dùng địa chỉ cụ thể:

- Một server có nhiều network interface và bạn chỉ muốn lắng nghe ở một interface.
- Ứng dụng chỉ nhận kết nối qua NIC nội bộ, tách khỏi NIC public.
- Thiết bị có IP ổn định, ít thay đổi.

Điểm cần cân nhắc: IP Wi-Fi/VPN có thể đổi khi chuyển mạng, DHCP cấp lại, interface bị down hoặc chuyển máy. Cấu hình cố định địa chỉ LAN thường kém linh hoạt trong Docker, Kubernetes và triển khai cloud có IP động. Nếu server được đặt trong container, **IP cục bộ của container** khác IP của host; không thể giả định IP LAN của host tồn tại bên trong container.

## 4. Mọi giao diện mạng: 0.0.0.0 và ký hiệu IPv6 ::

Đối với IPv4, **0.0.0.0 là unspecified/wildcard bind address**. Khi server lắng nghe trên 0.0.0.0:8080, hệ điều hành có thể nhận kết nối gửi đến các **địa chỉ IPv4 cục bộ** trên port đó.

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Ví dụ:

~~~text
Server lắng nghe 0.0.0.0:8080
     |
     +-- 127.0.0.1:8080      (loopback IPv4)
     +-- 192.168.1.50:8080  (LAN IPv4)
     +-- 10.8.0.7:8080      (VPN IPv4)
~~~

Điều này không có nghĩa Internet tự động kết nối được tới máy chủ: router, firewall, cloud security group, địa chỉ private/public, inbound NAT và reverse proxy vẫn quyết định đường đến.

### Không dùng 0.0.0.0 như URL đích cho người dùng

0.0.0.0 có ý nghĩa đặc biệt **khi bind**. Khi muốn gửi HTTP request, hãy dùng địa chỉ đích thực tế:

~~~text
Ở cùng máy:             http://127.0.0.1:8080
Từ máy LAN khác:        http://192.168.1.50:8080
Qua DNS hợp lệ:         https://api.example.com
~~~

Không hướng dẫn người dùng truy cập http://0.0.0.0:8080 như địa chỉ chung của dịch vụ. Một số công cụ có thể xử lý URL đó theo cách đặc biệt, nhưng cách ấy không phải một địa chỉ máy chủ có ý nghĩa ổn định trên mạng.

### IPv6: :: là wildcard, ::1 là loopback

Các ký hiệu IPv6 tương đương về **vai trò**:

| Mục đích | IPv4 | IPv6 |
|---|---|---|
| Chỉ nhận loopback | 127.0.0.1 | ::1 |
| Mọi địa chỉ trên stack cùng họ | 0.0.0.0 | :: |
| Địa chỉ một giao diện cụ thể | 192.168.1.50 | Ví dụ fd00::50 |

Để bind vào loopback IPv6, thử:

~~~yaml
server:
  address: "::1"
  port: 8080
~~~

Để bind vào wildcard IPv6:

~~~yaml
server:
  address: "::"
  port: 8080
~~~

Đặt địa chỉ IPv6 trong dấu ngoặc kép ở YAML giúp dễ đọc và tránh nhập nhằng cú pháp. Khi URL chứa địa chỉ IPv6 dạng literal, bao phần địa chỉ bằng dấu ngoặc vuông:

~~~text
http://[::1]:8080
http://[fd00::50]:8080
~~~

**Không suy ra bind :: chắc chắn nhận cả IPv4.** Chế độ dual-stack và IPv4-mapped IPv6 phụ thuộc JVM, hệ điều hành và cấu hình socket/server. Với một hệ thống yêu cầu cả IPv4 lẫn IPv6, hãy kiểm tra listener và test request trên **cả hai họ địa chỉ**. Tương tự, 0.0.0.0 chỉ mô tả wildcard IPv4; không tự bảo đảm khả năng truy cập IPv6.

## 5. So sánh ba lựa chọn thường dùng

Giả sử host có loopback 127.0.0.1 và LAN 192.168.1.50, port 8080 còn trống, firewall cho phép LAN, server bind thành công:

| server.address | Truy cập từ 127.0.0.1 cùng máy | Truy cập từ 192.168.1.50 cùng máy | Truy cập qua LAN từ máy khác |
|---|---|---|---|
| 127.0.0.1 | Có | Không qua listener đó | Không |
| 192.168.1.50 | Không qua listener đó | Có | Có thể, nếu firewall/route cho phép |
| 0.0.0.0 | Có | Có | Có thể, nếu firewall/route cho phép |

Bảng áp dụng cho **IPv4 và một server đang lắng nghe**. Nếu máy có thêm server khác trên port hay proxy chuyển tiếp, kết quả kết nối ở toàn hệ thống có thể khác. Khái niệm bind mô tả nơi một listener nhận kết nối, không khẳng định độc quyền tuyệt đối mọi đường truyền đến ứng dụng.

Quy tắc lựa chọn thực tế:

- **Chỉ dùng trên máy phát triển:** 127.0.0.1 thường là mặc định giới hạn mạng rõ nhất.
- **Chỉ qua NIC nội bộ của host cố định:** địa chỉ cụ thể trên NIC đó.
- **Container, Pod hoặc host cần nhận traffic qua nhiều NIC:** 0.0.0.0 có thể hợp lý, nhưng phải dùng firewall, proxy, Service hoặc network policy để kiểm soát phạm vi truy cập.
- **Dịch vụ chỉ qua reverse proxy trên cùng host:** có thể bind backend vào 127.0.0.1 để proxy truy cập local.
- **Reverse proxy ở host/container khác:** backend thường cần bind vào địa chỉ reachable trên mạng giữa proxy và app.

Mỗi môi trường có một đường đi mạng khác nhau; không có một giá trị server.address là “an toàn nhất và dùng được mọi nơi”.

## 6. Cấu hình Spring Boot: server.address khác server.port

Trong Spring Boot 3.3.x, các property liên quan:

~~~properties
server.address=127.0.0.1
server.port=8080
~~~

- **server.address** quyết định địa chỉ mà server bind (được chuyển sang đối tượng địa chỉ mạng).
- **server.port** quyết định cổng TCP HTTP của embedded server; mặc định thường là 8080 nếu không thay.
- **server.port=0** yêu cầu hệ điều hành cấp một cổng động còn trống; nó **không có nghĩa** bind mọi interface.
- **server.address=0.0.0.0** có nghĩa wildcard IPv4; nó **không có nghĩa** port 0.
- Khi **không khai báo server.address**, embedded server thường lắng nghe trên các địa chỉ mạng được implementation và cấu hình JVM cho phép. Đừng dựa vào mặc định mơ hồ: kiểm tra listener thật, nhất là trên môi trường chỉ IPv4/IPv6.

YAML tương đương:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

### Spring MVC và Spring WebFlux

Cấu hình server.address, server.port là property ở tầng Spring Boot. Nó dùng cho embedded server tương ứng trong cả hai loại ứng dụng:

~~~text
Spring MVC / Servlet:
  server.address -> Tomcat/Jetty/Undertow servlet factory -> TCP listener

Spring WebFlux / Reactive:
  server.address -> Reactor Netty (hoặc reactive server khác) -> TCP listener
~~~

Cách tạo server bên trong khác nhau, nhưng ý nghĩa của IP và port bind ở tầng mạng là như nhau. Đừng tự gọi factory.getWebServer() để đổi địa chỉ; cấu hình qua property hoặc customizer server thích hợp.

### Nhiều nguồn cấu hình có thể ghi đè

Các giá trị từ command line, environment variable, profile, application.yml và nguồn cấu hình khác có thứ tự ưu tiên. Ví dụ có thể chạy:

~~~bash
./gradlew bootRun --args='--server.address=127.0.0.1 --server.port=8082'
~~~

Lệnh này phụ thuộc dự án có task bootRun được cấu hình. Trên Windows PowerShell có thể dùng:

~~~powershell
.\gradlew.bat bootRun --args="--server.address=127.0.0.1 --server.port=8082"
~~~

Khi thấy server bind khác application.yml, hãy kiểm tra profile và tham số runtime trước khi kết luận Boot bỏ qua property. Environment variable thường dùng cú pháp SERVER_ADDRESS và SERVER_PORT theo quy tắc relaxed binding.

## 7. Bind address, DNS, Host header, CORS và reverse proxy là những tầng khác nhau

Ví dụ client gọi:

~~~text
https://api.example.com/products
~~~

Một lần kết nối có thể đi như sau:

~~~text
Client
   |
   +-- DNS: api.example.com -> địa chỉ public của proxy/load balancer
   |
   +-- TCP/TLS tới IP public:443
   |
   v
Reverse proxy / load balancer
   |
   +-- Chuyển tiếp tới backend 10.1.0.20:8080
   |
   v
Spring Boot bind 10.1.0.20:8080 hoặc 0.0.0.0:8080
   |
   v
Spring MVC / WebFlux xử lý request
~~~

Phân biệt rõ:

1. **DNS:** chuyển hostname thành IP (hoặc nhiều IP) cho client. Việc DNS trỏ tới IP không làm ứng dụng tự bind vào IP đó.
2. **Listening/bind IP:** quyết định socket cục bộ nào nhận kết nối mạng.
3. **HTTP Host header / HTTP/2 :authority:** định danh authority mà client muốn truy cập ở tầng HTTP; không đồng nghĩa địa chỉ mà socket bind.
4. **Reverse proxy:** có thể nhận ở IP public rồi kết nối backend ở IP private khác; từ phía Spring Boot, peer trực tiếp thường là proxy.
5. **CORS:** là cơ chế trình duyệt giới hạn JavaScript truy cập cross-origin responses; nó không mở hoặc đóng listening socket và không phải firewall.
6. **Authentication/authorization:** quyết định ai được sử dụng endpoint, ngay cả khi mạng đã cho phép kết nối.

Ví dụ server bind 0.0.0.0:8080 vẫn có thể chỉ được truy cập qua HTTPS ở reverse proxy do firewall chặn direct traffic. Ngược lại, đặt CORS nghiêm ngặt không ngăn curl, ứng dụng di động hoặc client không phải browser kết nối trực tiếp đến API nếu port được mở.

### server.address không phải “địa chỉ public của website”

Nếu public DNS trỏ về load balancer 203.0.113.10 còn ứng dụng chạy trên host private 10.1.0.20, **không** đặt server.address=203.0.113.10 trừ khi IP đó thật sự được gán trong network namespace của ứng dụng. Backend thường bind vào 10.1.0.20 hoặc wildcard, và load balancer sẽ chuyển lưu lượng đến IP private đó.

Địa chỉ public được client gọi và địa chỉ nội bộ được backend bind có thể hoàn toàn khác nhau.

## 8. Bài thực hành Spring Boot 3.3.x, Java 17+

Tạo một ứng dụng Spring Boot MVC mới hoặc thêm ví dụ này vào project Boot 3.3.x đã có. Phần dependency trong build.gradle của project Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Đây chỉ là phần dependencies, không phải toàn bộ file build.gradle có plugin và repository. Dùng JDK 17 trở lên.

Tạo file src/main/java/com/example/bind/BindAddressApplication.java:

~~~java
package com.example.bind;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BindAddressApplication {

    public static void main(String[] args) {
        SpringApplication.run(BindAddressApplication.class, args);
    }

    @RestController
    static class NetworkController {

        @GetMapping("/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/network")
        String network(HttpServletRequest request) {
            return "local=" + request.getLocalAddr()
                    + ":" + request.getLocalPort()
                    + "; remote=" + request.getRemoteAddr()
                    + ":" + request.getRemotePort();
        }
    }
}
~~~

Đây là một **class Java hoàn chỉnh trong project Spring Boot**. Nó không thể biên dịch bằng javac trần nếu thiếu thư viện Spring Boot, Spring Web và Jakarta Servlet trên classpath; dùng Gradle/Maven của project để chạy.

Giải thích:

- @SpringBootApplication cho Spring Boot khởi tạo context và embedded Tomcat từ starter-web.
- /ping có response body ổn định là pong, phù hợp để kiểm tra server có tiếp nhận request không.
- /network cho biết local address/port mà ServletRequest nhìn thấy cho **kết nối đã được chấp nhận**, và remote address/port của peer trực tiếp.
- Nếu bind 0.0.0.0 nhưng truy cập từ 127.0.0.1, local address được request báo thường là 127.0.0.1, không nhất thiết là chuỗi wildcard 0.0.0.0. Đây không phải lỗi cấu hình: wildcard mô tả listener, còn local address mô tả một kết nối cụ thể.
- Nếu đi qua proxy, remote address thường là proxy và local address là địa chỉ nội bộ của backend; đó không phải địa chỉ public hay IP gốc của người dùng.

Cấu hình ban đầu trong src/main/resources/application.yml:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Chạy tại root project:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Thử:

~~~bash
curl -4 -s http://127.0.0.1:8080/ping
~~~

Response body dự kiến, **chính xác**:

~~~text
pong
~~~

Kiểm tra thông tin kết nối:

~~~bash
curl -4 -s http://127.0.0.1:8080/network
~~~

Kết quả có dạng local=127.0.0.1:8080; remote=127.0.0.1:<port-nguồn>, trong đó cổng nguồn thay đổi theo mỗi lần kết nối. Không cố định stdout vì các cổng tạm được OS cấp phát động.

### Thí nghiệm A: chỉ localhost

Giữ:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Từ cùng host, /ping qua 127.0.0.1 hoạt động. Từ máy B trong LAN thử http://192.168.1.50:8080/ping thường không kết nối được **qua listener này** vì server chỉ bind loopback. Lưu ý địa chỉ 192.168.1.50 phải là IP đúng của host A; nếu host A dùng địa chỉ khác, thay cho phù hợp.

### Thí nghiệm B: bind vào một địa chỉ LAN

Đặt IP thực tế của host A, ví dụ:

~~~yaml
server:
  address: 192.168.1.50
  port: 8080
~~~

Khởi động lại. Khi bind thành công, test trực tiếp đến http://192.168.1.50:8080/ping từ máy A; sau đó thử từ máy B. Việc máy B kết nối được còn phụ thuộc subnet/route và firewall. Test http://127.0.0.1:8080/ping có thể thất bại vì listener đang gắn với LAN IP chứ không gắn loopback.

### Thí nghiệm C: bind mọi giao diện IPv4

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Khởi động lại. Thử trên host A:

~~~bash
curl -4 -s http://127.0.0.1:8080/ping
curl -4 -s http://192.168.1.50:8080/ping
~~~

Cả hai có thể trả về pong khi mạng và firewall trên host phù hợp. Từ máy B trong LAN cũng thử http://192.168.1.50:8080/ping. Sự khác biệt giữa phép thử trên máy A và máy B giúp tách lỗi **bind** khỏi lỗi **route/firewall**.

### Thí nghiệm D: hostname localhost và IPv6

Nếu hệ điều hành/JVM hỗ trợ IPv6, đặt:

~~~yaml
server:
  address: "::1"
  port: 8080
~~~

Dùng:

~~~bash
curl -6 -s "http://[::1]:8080/ping"
~~~

Kết quả mong đợi là pong. Kết nối IPv4 tới 127.0.0.1:8080 không được coi là tương đương. Nếu lệnh thất bại, cần kiểm tra hỗ trợ IPv6 và listener thực tế trước khi kết luận server cấu hình sai.

**Lưu ý thực nghiệm:** Khi thay đổi address/port, cần khởi động lại ứng dụng để socket mới được bind. Chỉnh file YAML mà không restart server đang chạy không tự làm listening socket đổi địa chỉ.

## 9. Xác định IP thật và socket đang lắng nghe

Một lỗi phổ biến là chỉ đọc dòng log “Tomcat started on port 8080” rồi cho rằng server chắc chắn đang nghe mọi interface. Hãy kiểm tra **local address** của listening socket.

### Linux

Xem địa chỉ trên máy:

~~~bash
ip -br address
~~~

Xem listening TCP socket ở port 8080:

~~~bash
ss -ltnp 'sport = :8080'
~~~

Nếu một môi trường thiếu quyền xem tên process, ss vẫn có thể liệt kê listener nhưng không hiển thị PID/process. Các kiểu đầu ra thường gặp:

~~~text
127.0.0.1:8080     chỉ localhost IPv4
192.168.1.50:8080  chỉ địa chỉ LAN IPv4
0.0.0.0:8080       wildcard IPv4
[::1]:8080         loopback IPv6
[::]:8080          wildcard IPv6
~~~

Đây là **các giá trị mẫu**, không phải transcript thực tế của một phiên chạy. Ký hiệu có thể hiển thị là *:8080 hoặc dạng IPv6 tùy công cụ.

### Windows PowerShell

Xem IP và giao diện:

~~~powershell
Get-NetIPAddress -AddressFamily IPv4
~~~

Xem listener port 8080:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Kiểm tra từ máy khác:

~~~powershell
Test-NetConnection -ComputerName 192.168.1.50 -Port 8080
~~~

Nếu đang mở nhiều tiến trình, dùng OwningProcess để đối chiếu PID của JVM. Một địa chỉ wildcard trong output chỉ cho biết server **có thể** nhận kết nối trên interface tương ứng; nó không chứng minh firewall cho phép máy khác gọi tới.

### Kiểm tra cả request và route

~~~bash
curl -4 -v http://127.0.0.1:8080/ping
curl -4 -v http://192.168.1.50:8080/ping
~~~

Chạy lệnh thứ hai từ **máy khác** để xác minh kết nối LAN thật sự. Nếu chạy từ chính server, OS có thể định tuyến tới IP cục bộ mà không đi qua đường mạng ngoài, nên đó không phải bằng chứng LAN client đã truy cập được.

Trong môi trường dùng proxy HTTP do biến môi trường cấu hình, curl có thể đi qua proxy khác. Khi cần thử kết nối trực tiếp, dùng tùy chọn --noproxy '*' cho các lệnh curl và chú ý quy tắc escape của shell.

## 10. Docker: hai lớp bind khác nhau

Khi chạy Spring Boot trong container, có hai khâu riêng:

1. **Bind bên trong container:** địa chỉ mà JVM lắng nghe trong network namespace của container, do server.address.
2. **Publish trên Docker host:** cổng host ánh xạ đến cổng container qua Docker, do -p hoặc ports.

Ví dụ:

~~~text
Laptop (Docker host)              Container
192.168.1.50                      172.18.0.2 (ví dụ)
     |                                 |
Host port 8080 --Docker NAT--------> container port 8080
                                        |
                                   Spring Boot listener
~~~

### Lỗi: server.address=127.0.0.1 bên trong container

Nếu ứng dụng bind 127.0.0.1:8080 **trong container**, nó lắng nghe loopback của container. Docker publish tới IP mạng của container, nên host có thể không thể đi tới service dù đã dùng -p 8080:8080.

Để nhận kết nối được Docker chuyển tới, thường dùng:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Cấu hình này không bắt Docker mở cổng host; nó chỉ cho phép app nhận traffic trên các IPv4 interface **bên trong container**.

### Host publish toàn bộ địa chỉ hay chỉ localhost

Chạy một image đã build sẵn:

~~~bash
docker run --rm -p 8080:8080 my-spring-boot-app:latest
~~~

Trong cấu hình bridge mặc định thông thường, Docker publish host port 8080 trên mọi địa chỉ host, khiến client có đường mạng đến host có thể truy cập nếu firewall cho phép.

Chỉ publish tới loopback Docker host:

~~~bash
docker run --rm -p 127.0.0.1:8080:8080 my-spring-boot-app:latest
~~~

Điều này khác hẳn việc đặt server.address=127.0.0.1 **bên trong container**. Tình huống thường muốn: Spring Boot bind 0.0.0.0 trong container, Docker host chỉ publish 127.0.0.1 nếu service phục vụ phát triển local.

| Tầng | Lựa chọn ví dụ | Ý nghĩa |
|---|---|---|
| Spring Boot bên trong container | server.address=0.0.0.0 | Nghe trên các interface IPv4 của container |
| Docker publish trên host | -p 127.0.0.1:8080:8080 | Chỉ map host port ở loopback |
| Docker publish trên host | -p 8080:8080 | Thường map port trên mọi interface host |
| Firewall của host | Cho phép/chặn TCP 8080 | Kiểm soát gói từ mạng ngoài vào host |

**Chú ý phiên bản Docker:** Tài liệu Docker nêu một số phiên bản cũ trước 28.0.0 có trường hợp host cùng L2 có thể truy cập port publish localhost. Vì vậy đừng coi host port bind thay thế hoàn toàn cho firewall và phân tách mạng.

### Compose

Cấu hình mẫu:

~~~yaml
services:
  api:
    image: my-spring-boot-app:latest
    environment:
      SERVER_ADDRESS: "0.0.0.0"
      SERVER_PORT: "8080"
    ports:
      - "127.0.0.1:8080:8080"
~~~

Environment variable SERVER_ADDRESS và SERVER_PORT được Spring Boot chuyển vào property tương ứng. Với Compose này, backend nghe trong container, còn cổng public của host giới hạn ở loopback. Khi muốn thiết bị LAN truy cập để demo, phải thay host publish binding có chủ đích và đồng thời quản lý firewall.

Không gán server.address bằng **IP LAN của Docker host** bên trong container, vì thông thường IP đó không thuộc network namespace container.

## 11. Kubernetes và cloud: socket bind khác với service exposure

Trong Kubernetes, Pod thường có IP riêng. Kubelet, Service hoặc Ingress liên lạc với Pod qua mạng Pod; vì vậy ứng dụng web trong container thường phải lắng nghe trên IP Pod hoặc 0.0.0.0.

Ví dụ container có cấu hình:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Một Service có thể chuyển traffic từ ClusterIP/port tới Pod IP:8080. **Pod nghe trên 0.0.0.0 không có nghĩa Internet gọi trực tiếp được Pod**; khả năng truy cập phụ thuộc Kubernetes Service type, Ingress/Gateway, routing và NetworkPolicy.

Nếu app chỉ bind 127.0.0.1 trong Pod, một Service thông thường truy cập qua Pod IP có thể không kết nối được. Trừ một số cơ chế sidecar hoặc cùng network namespace dùng loopback có chủ đích, nên tránh bind loopback cho ứng dụng cần nhận traffic từ ngoài Pod.

### Cloud VM và load balancer

Một VM có private IP 10.1.0.20 và public IP 203.0.113.10 có thể dùng NAT ở nền tảng cloud. 203.0.113.10 có thể không được gán trực tiếp lên NIC trong VM. Nếu đặt server.address=203.0.113.10 khi địa chỉ đó không có trên VM, socket bind sẽ lỗi.

Cách thường gặp: server bind 0.0.0.0 hoặc private NIC IP; security group/firewall và load balancer kiểm soát inbound.

### Bảo đảm đúng đường health/readiness probe

Một HTTP health check trỏ tới Pod IP hoặc private VM IP sẽ không đi qua localhost của chính tiến trình probe nếu probe chạy ở node khác. Khi kiểm tra failed readiness, cần xét:

- App có nghe trên IP mà probe sử dụng không?
- Probe dùng port và scheme (HTTP/HTTPS) đúng không?
- Container/Pod đã hoàn tất startup chưa?
- Có firewall/NetworkPolicy ngăn kết nối không?
- Endpoint có trả về mã phù hợp hay không?

Không nên sửa lỗi này bằng cách tắt readiness hay mở tất cả cổng một cách mù quáng; xác định chính xác đường mạng mà probe đang đi.

## 12. Reverse proxy và Actuator: cần tách bề mặt public/internal

Một triển khai phổ biến:

~~~text
Internet -> HTTPS 443 trên Nginx
                     |
                     v
              Spring Boot :8080
~~~

Nếu Nginx và Spring Boot chạy **cùng host**, backend có thể bind 127.0.0.1:8080 để Nginx proxy_pass đến 127.0.0.1:8080. Việc này giúp giảm bề mặt mạng phải công khai.

Nếu Nginx chạy **container khác hoặc server khác**, 127.0.0.1 ở phía Nginx trỏ về Nginx, không trỏ tới app. Khi đó dùng hostname/IP nội bộ có thể route tới Spring Boot và cho backend bind đúng interface.

### Management endpoints có thể có listener riêng

Khi có Spring Boot Actuator và muốn management endpoint chỉ nghe localhost với port riêng, Spring Boot 3.3 hỗ trợ ví dụ:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

management:
  server:
    port: 8081
    address: 127.0.0.1
~~~

Ý nghĩa: app thông thường lắng nghe trên port 8080, management web server ở port 8081 bind loopback. Theo tài liệu Spring Boot, **management.server.address cần một management.server.port tùy chỉnh** để sử dụng địa chỉ bind khác với server chính.

Cấu hình này không thay thế phân quyền Actuator. Quyền truy cập endpoints còn phụ thuộc exposure, Spring Security, proxy, firewall và topology triển khai. Trong container, management bind loopback có thể làm kubelet hoặc monitoring bên ngoài Pod không gọi được; hãy thiết kế probe và mạng quản trị phù hợp.

## 13. Những điểm bảo mật và vận hành cần hiểu đúng

### Wildcard bind có thể mở rộng bề mặt kết nối

Khi chạy laptop có Wi-Fi, VPN và Docker bridge, server.address=0.0.0.0 có thể khiến app nhận request qua nhiều interface bạn không chủ định. Nếu project đang có endpoint thử nghiệm hoặc API quản trị thiếu bảo vệ, các máy trên mạng có thể thử truy cập khi firewall cho phép.

Nguyên tắc:

- Với development chỉ cần local, dùng 127.0.0.1/::1 nếu không cần remote access.
- Với public service, để gateway/reverse proxy chịu trách nhiệm TLS, authentication và rate limit theo kiến trúc.
- Hạn chế inbound bằng firewall, cloud security group hoặc Kubernetes NetworkPolicy; không dựa vào CORS.
- Không công khai Actuator nhạy cảm hay debug endpoint chỉ vì cấu hình server.address tiện lợi.

### Bind address không phải chính sách xác thực

server.address=192.168.1.50 chỉ giới hạn socket nhận traffic hướng tới IP đó; mọi client có đường mạng tới IP:port có thể kết nối nếu firewall cho phép. User nào được dùng API phải do authentication/authorization quyết định.

### TLS và hostname vẫn độc lập

Một ứng dụng HTTPS có certificate cho api.example.com có thể bind ở 0.0.0.0:8443. Certificate được xác minh theo hostname client dùng để truy cập, không theo chữ wildcard ở listening socket. Thay đổi server.address không sửa lỗi TLS certificate mismatch.

### Không đồng nhất 0.0.0.0 với 0 hoặc localhost

- **0.0.0.0**: địa chỉ wildcard IPv4 khi bind.
- **0** trong server.port=0: yêu cầu chọn port động.
- **127.0.0.1**: loopback IPv4.
- **localhost**: hostname được resolve ở phía máy đang gọi/đang chạy.
- **::**: wildcard IPv6; dual-stack tùy môi trường.
- **::1**: loopback IPv6.

## 14. Quy trình chẩn đoán lỗi kết nối

Khi client không vào được ứng dụng, kiểm tra theo thứ tự từ gần tới xa:

1. **Ứng dụng đã khởi động thành công?** Xem exception bind, startup log và cổng thực tế. Nếu server.port=0, tìm cổng OS đã cấp.
2. **Địa chỉ nào đang lắng nghe?** Dùng ss -ltnp hoặc Get-NetTCPConnection, phân biệt 127.0.0.1, IP cụ thể và wildcard.
3. **IP đó có thuộc máy/container hiện tại?** Dùng ip address hoặc Get-NetIPAddress. Nếu không thuộc host, sửa server.address.
4. **Từ cùng network namespace có gọi được không?** Dùng curl -4 http://127.0.0.1:port hoặc đúng IP server đang bind.
5. **Từ client khác có route tới IP đích không?** Xem DNS resolve, private/public IP, VPN, subnet và route.
6. **Firewall/security group có cho TCP port đó không?** Kiểm tra host firewall, cloud network policy và container publish.
7. **Có proxy, NAT hay load balancer ở giữa không?** Kiểm tra upstream target IP/port, service discovery và TLS termination.
8. **Có lẫn IPv4 và IPv6 không?** Kiểm tra curl -4/curl -6 và listener theo từng address family.
9. **Đã kết nối TCP nhưng HTTP trả lỗi?** Khi đó phân tích route/controller, context path, Host header, HTTPS scheme, security filters và application logs; vấn đề có thể ở tầng HTTP chứ không còn là bind.
10. **Ứng dụng có restart sau khi đổi config?** Listening socket không tự cập nhật khi chỉ sửa application.yml.

### Nhận diện một số triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| localhost chạy, máy LAN khác không vào | App chỉ bind 127.0.0.1; hoặc firewall/route chặn | Kiểm tra listener rồi mở đúng interface và firewall |
| IP LAN chạy, localhost IPv4 không chạy | App bind vào IP LAN cụ thể | Dùng đúng IP, hoặc wildcard nếu cần cả hai |
| Startup báo Cannot assign requested address | Bind vào IP không tồn tại ở host/container | Xác định local IP thật và sửa server.address |
| Startup báo Address already in use | IP:port bị process khác chiếm; xung đột IPv4/IPv6 | Xem PID listener, đổi port hoặc dừng process cũ |
| curl localhost chạy không đều giữa IPv4/IPv6 | localhost resolve sang ::1 hoặc 127.0.0.1 khác với listener | Ép curl -4 / -6, đặt bind address rõ ràng |
| Docker -p đã khai báo nhưng host không vào | App bên trong container chỉ bind 127.0.0.1 | Bind 0.0.0.0 trong container, kiểm tra host publish |
| Container gọi localhost để kết nối database chạy trên host | localhost trong container là container | Dùng hostname/route dành cho host hoặc network nội bộ |
| Kubernetes Service timeout | App chỉ bind loopback Pod hoặc NetworkPolicy/Service sai | Kiểm tra Pod IP, targetPort, endpoint, policy |
| Curl vào IP được nhưng browser JS báo CORS | Kết nối HTTP đã đến server; chính sách origin khác | Cấu hình CORS phù hợp, không đổi bind để sửa CORS |
| Nginx báo 502 | Nginx không tới được upstream hoặc app chưa sẵn sàng | Kiểm tra upstream IP:port và network namespace |

### Trường hợp không thể kết luận chỉ từ một phép thử

Nếu local curl tới http://192.168.1.50:8080 chạy được, bạn **chưa chứng minh** máy LAN khác kết nối được. Local OS có thể đưa gói đến IP sở hữu bởi chính máy đó mà không qua đường truyền ra LAN. Cần chạy request từ client bên ngoài host và xem firewall/route.

Nếu thấy 0.0.0.0:8080 trong ss, bạn **chưa chứng minh** dịch vụ được công khai tới Internet. NAT, route, security group, ingress rule và listener khác vẫn có thể chặn hoặc thay đổi đường đi.

Nếu thấy server local báo remote address=127.0.0.1, bạn **chưa chứng minh** người dùng cuối truy cập từ localhost. Một reverse proxy trên cùng máy có thể là peer trực tiếp của server, nên log backend nhìn thấy proxy.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Máy A chạy Spring Boot ở 127.0.0.1:8080. Máy B dùng http://localhost:8080. Liệu B đã gọi đến A chưa?

**Đáp án:** Chưa. localhost trên B trỏ về B. Cần backend lắng nghe trên IP mà B có đường mạng tới, chẳng hạn LAN IP của A, và firewall cho phép.

**Câu 2.** Server bind 0.0.0.0:8080. Trong trình duyệt của máy B, nên gõ URL nào?

**Đáp án:** IP hoặc hostname thực sự của A, ví dụ http://192.168.1.50:8080. 0.0.0.0 là wildcard bind, không phải địa chỉ dịch vụ client nên sử dụng.

**Câu 3.** Máy A có 192.168.1.50 và 10.8.0.7, nhưng Spring Boot bind 192.168.1.50. Client ở VPN gọi 10.8.0.7:8080 có dùng listener này không?

**Đáp án:** Không qua socket đã bind vào 192.168.1.50. Muốn nhận theo VPN IP, phải bind theo IP đó, dùng wildcard phù hợp hoặc thiết lập proxy chuyển tiếp hợp lệ.

**Câu 4.** Docker image chạy app với server.address=127.0.0.1, Docker host đã map -p 8080:8080. Vì sao máy host không nhận response?

**Đáp án:** Listener của app chỉ có trên loopback container; mapping từ host thường đi tới địa chỉ mạng container. Cần để app lắng nghe trên interface container như 0.0.0.0 và quyết định host publish binding riêng.

**Câu 5.** Chạy curl http://localhost:8080 thất bại nhưng curl http://127.0.0.1:8080 thành công. Điều gì đáng kiểm tra?

**Đáp án:** localhost có thể được phân giải ưu tiên IPv6 ::1, trong khi server chỉ nghe IPv4. Kiểm tra DNS/hosts, curl -4/-6, và listening sockets.

**Câu 6.** Một ứng dụng bind wildcard có tự động bảo đảm HTTP endpoint chỉ được người trong công ty dùng không?

**Đáp án:** Không. Bảo vệ truy cập phụ thuộc vào route, VPN, firewall, authentication/authorization và các chính sách mạng khác.

**Câu 7.** Ứng dụng có public URL https://api.example.com nhưng backend chỉ có private IP 10.1.0.20. Có nên đặt server.address=IP public của load balancer không?

**Đáp án:** Không, trừ khi địa chỉ public thật sự tồn tại trên NIC/backend namespace. Thông thường backend bind private IP hoặc wildcard và load balancer chuyển request đến backend.

**Câu 8.** Nếu management.server.address=127.0.0.1 nhưng management.server.port vẫn dùng cùng port với app, cấu hình có ý nghĩa mong muốn không?

**Đáp án:** Không. Để management endpoint bind một địa chỉ riêng, Spring Boot yêu cầu khai báo management.server.port riêng.

## 16. Checklist khi cấu hình trên môi trường mới

- [ ] Xác định IP của **host hoặc network namespace chạy JVM**, không nhầm IP của laptop, Docker host, reverse proxy hay load balancer.
- [ ] Quyết định service chỉ dùng local, chỉ dùng một NIC hay cần nghe nhiều interface.
- [ ] Chọn 127.0.0.1, IP cụ thể hoặc 0.0.0.0 cho nhu cầu IPv4; xem riêng IPv6 nếu có.
- [ ] Đặt server.port và kiểm tra port có đang bị chiếm không.
- [ ] Kiểm tra listener sau khi start bằng ss/netstat/PowerShell.
- [ ] Dùng IP/hostname thật khi gọi từ client khác; localhost luôn mang nghĩa theo máy của client.
- [ ] Đối với Docker, kiểm tra **cả** server.address bên trong container **và** host publish mapping.
- [ ] Đối với Kubernetes/cloud, kiểm tra Pod/VM IP, Service, ingress, route, security group và network policy.
- [ ] Với reverse proxy, xác nhận upstream URL reachable từ vị trí chạy proxy.
- [ ] Với Actuator, phân biệt management binding, port và phân quyền.
- [ ] Kiểm tra IPv4/IPv6 độc lập khi môi trường hỗ trợ dual-stack.
- [ ] Kiểm chứng từ một client thật bên ngoài host trước khi công bố dịch vụ reachable.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Common Application Properties: server.address, server.port, management.server.address](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Boot 3.3 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Docker Docs — Port publishing and mapping](https://docs.docker.com/engine/network/port-publishing/)
- [Kubernetes — Services, Load Balancing and Networking](https://kubernetes.io/docs/concepts/services-networking/)
