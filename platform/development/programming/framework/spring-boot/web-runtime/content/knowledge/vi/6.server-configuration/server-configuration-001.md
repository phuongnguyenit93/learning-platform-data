# Cấu hình server.port, server.address và địa chỉ mạng lắng nghe trong Spring Boot

## 1. Ba câu hỏi khác nhau khi chạy HTTP server

Một ứng dụng Spring Boot có embedded web server (Tomcat, Jetty, Undertow hoặc Reactor Netty, tùy web stack và dependencies). Khi server khởi động, nó cần mở một socket để nhận kết nối từ client. Hai thuộc tính quan trọng là **server.port** và **server.address**:

- **server.port**: server lắng nghe trên cổng TCP nào?
- **server.address**: server bind vào địa chỉ IP/interface nào của máy đang chạy ứng dụng?
- **Địa chỉ client dùng để truy cập**: client có thể kết nối bằng URL nào từ vị trí mạng của chính client?

Đây là ba câu hỏi có liên hệ nhưng không đồng nhất. Ví dụ server bind vào 0.0.0.0:8080 có nghĩa là nhận kết nối IPv4 trên các địa chỉ IPv4 cục bộ thích hợp. Client không dùng URL http://0.0.0.0:8080 để truy cập từ máy khác; client phải dùng IP hoặc hostname có thể định tuyến đến máy chủ, chẳng hạn http://192.168.1.20:8080.

Minh họa:

~~~text
Client A (cùng máy) -- http://127.0.0.1:8080 --> Spring Boot
Client B (máy khác) -- http://192.168.1.20:8080 --> Spring Boot

Spring Boot bind:
  127.0.0.1:8080  -> chỉ qua loopback của máy chạy process
  192.168.1.20:8080 -> qua một địa chỉ IPv4 cụ thể, nếu IP này thuộc máy
  0.0.0.0:8080    -> tất cả địa chỉ IPv4 cục bộ phù hợp

Khả năng client kết nối còn phụ thuộc route, firewall, NAT,
container/network namespace và cấu hình proxy.
~~~

**Bind address** là địa chỉ cục bộ mà hệ điều hành gán cho listener. **Destination address** trong URL của client là địa chỉ mà client có thể định tuyến đến. Còn hostname công khai, DNS, reverse proxy và TLS có thể nằm ở các tầng khác.

## 2. Cấu hình server.port

Trong ứng dụng Spring Boot web nhúng thông thường, server.port mặc định là **8080** nếu không bị thay đổi bởi cấu hình hoặc môi trường.

Cấu hình trong src/main/resources/application.yaml:

~~~yaml
server:
  port: 8085
~~~

Tương đương trong application.properties:

~~~properties
server.port=8085
~~~

Với cấu hình này, HTTP server dự kiến lắng nghe TCP port 8085, miễn là không có lỗi khởi động như port đã bị chiếm hoặc bind address không hợp lệ.

### Giá trị cổng thường gặp

| Giá trị | Ý nghĩa |
|---|---|
| Không khai báo | Thường dùng 8080 |
| 8085 | Yêu cầu server lắng nghe cổng TCP 8085 |
| 0 | Để hệ điều hành cấp một cổng đang rảnh; hữu ích cho kiểm thử tích hợp |
| -1 | Tắt việc mở HTTP endpoint lắng nghe trong ứng dụng web nhúng, nhưng vẫn có thể tạo WebApplicationContext |
| Số ngoài phạm vi cho phép | Cấu hình không hợp lệ hoặc không thể bind; không sử dụng |

**server.port=0** không có nghĩa server thực sự nghe tại cổng số 0. Số 0 là yêu cầu cấp cổng động; sau khi server khởi động, cổng thật thường là một số dương do hệ điều hành chọn. Vì thế, đừng tạo URL tới localhost:0.

**server.port=-1** không giống với spring.main.web-application-type=none. Cấu hình -1 vẫn cho phép tạo web application context nhưng tắt HTTP listener; còn web-application-type=none chọn loại ứng dụng không phải web, không khởi chạy web server nhúng theo mô hình thông thường.

Một cổng có thể bị process khác chiếm hoặc không được phép sử dụng. Trên một số hệ điều hành, bind vào các cổng đặc quyền như 80 hoặc 443 cần quyền hoặc cơ chế cấp capability phù hợp. Cài đặt server.port không tự mở firewall, NAT hay router.

## 3. Cấu hình server.address

Thuộc tính **server.address** điều khiển IP address mà web server bind vào; kiểu dữ liệu cấu hình được Spring Boot xử lý thành địa chỉ mạng.

Ví dụ chỉ nhận request trên loopback IPv4:

~~~yaml
server:
  port: 8080
  address: 127.0.0.1
~~~

Với cách này, client trên chính máy hoặc trong cùng network namespace có thể gọi http://127.0.0.1:8080. Máy khác trong LAN thường không thể truy cập listener này bằng IP LAN của máy chủ, kể cả khi biết cổng, vì listener không bind lên interface LAN.

Ví dụ nhận kết nối trên tất cả địa chỉ IPv4 cục bộ:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
~~~

0.0.0.0 ở đây là **IPv4 wildcard bind address**. Nó không phải hostname hoặc địa chỉ đích công khai của ứng dụng. Dù server đã bind wildcard, vẫn cần firewall và routing cho phép để client từ mạng khác kết nối.

Ví dụ chỉ bind lên IP LAN cụ thể của máy:

~~~yaml
server:
  port: 8080
  address: 192.168.1.20
~~~

Cấu hình này chỉ hợp lệ nếu địa chỉ 192.168.1.20 thực sự được gán cho một interface trong môi trường chạy process. Nếu máy không có địa chỉ đó, server thường thất bại với lỗi kiểu Cannot assign requested address, BindException hoặc lỗi bind tương đương.

### Bảng so sánh các địa chỉ thường dùng

| server.address | Listener | Điểm cần nhớ |
|---|---|---|
| Không khai báo | Thường bind wildcard theo mặc định của embedded server và hệ điều hành | Kiểm tra listener thực tế; mặc định có thể chịu ảnh hưởng bởi IPv4/IPv6 |
| 127.0.0.1 | Chỉ loopback IPv4 | Phù hợp khi HTTP chỉ cần truy cập nội bộ máy |
| 0.0.0.0 | Mọi địa chỉ IPv4 cục bộ phù hợp | Client ở máy khác phải dùng IP/hostname thực, không dùng 0.0.0.0 |
| 192.168.1.20 | IP IPv4 cụ thể | IP phải thuộc interface cục bộ của môi trường chạy |
| ::1 | Loopback IPv6 | Không đồng nghĩa với loopback IPv4 |
| :: | IPv6 wildcard | Hỗ trợ kết nối IPv4 song song hay không còn tùy dual-stack, OS và server |

Khi không khai báo server.address, cách bind cụ thể do embedded server, JVM và hệ điều hành quyết định. Một số môi trường ưu tiên IPv6 wildcard; cách nhận IPv4 song song phụ thuộc cấu hình dual-stack. Vì vậy, hãy quan sát socket thực tế nếu có yêu cầu bắt buộc về IPv4 hoặc IPv6.

**Không phải mọi chuỗi trông giống tên máy đều là địa chỉ bind thích hợp.** Nếu dùng hostname, nó phải được resolve thành địa chỉ IP mà máy thực sự sở hữu. Dùng IP literal thường dễ kiểm chứng hơn, nhất là khi deploy vào container hoặc môi trường nhiều interface.

## 4. Hiểu chính xác loopback, wildcard và interface cụ thể

### Loopback: 127.0.0.1 và ::1

Loopback là đường đi từ process tới chính network stack của máy hoặc namespace đó. 127.0.0.1 là loopback IPv4, còn ::1 là loopback IPv6.

Ví dụ Spring Boot bind 127.0.0.1:8080. Từ máy chủ:

~~~bash
curl -v http://127.0.0.1:8080/health
~~~

Request có thể đến ứng dụng nếu endpoint /health tồn tại. Từ một máy khác, dùng 127.0.0.1 lại trỏ về **máy client**, không trỏ về máy chạy Spring Boot.

Trong container, 127.0.0.1 là loopback bên trong container hoặc network namespace của process. Nó không phải loopback của host trong mô hình network container thông thường. Đây là nguyên nhân thường gặp của lỗi host đã publish port nhưng vẫn không kết nối được vào service trong container.

### Wildcard: 0.0.0.0 và ::

Bind vào 0.0.0.0:8080 thường cho phép socket nhận kết nối gửi tới bất kỳ địa chỉ IPv4 cục bộ phù hợp của process. Nếu máy có loopback, IP LAN và IP VPN, listener wildcard có thể nhận request qua các đường đó, với điều kiện firewall/routing cho phép.

0.0.0.0 là ký hiệu bind IPv4 wildcard, không phải một địa chỉ dành cho người dùng cuối. Một số công cụ local có thể chấp nhận http://0.0.0.0 như địa chỉ để kết nối, nhưng đây không phải cách mô tả public endpoint chính xác hoặc portable.

IPv6 wildcard :: có cách xử lý riêng. Một số hệ điều hành cấu hình socket IPv6 nhận cả IPv4 dạng IPv4-mapped, số khác bật IPv6-only. Đừng giả định :: luôn tương đương 0.0.0.0.

### IP của interface cụ thể

Bind vào 192.168.1.20:8080 chỉ nhận các kết nối phù hợp với địa chỉ đó. Cách này hữu ích khi server có nhiều interface và bạn muốn chỉ lắng nghe trên một mạng nhất định.

Tuy nhiên, địa chỉ riêng có thể thay đổi khi DHCP cấp lại IP, khi redeploy pod hoặc khi container chạy trên host mới. Vì vậy, hardcode IP cục bộ vào server.address thường không phù hợp với môi trường container được orchestration.

## 5. Kết nối đến listener từ client

Để một client truy cập được server, cần thỏa mãn đồng thời:

1. Ứng dụng thực sự khởi động và tạo socket lắng nghe.
2. Server bind vào một địa chỉ nhận được lưu lượng đến.
3. Cổng client dùng đúng với cổng của listener, hoặc có proxy/port mapping chuyển tiếp.
4. IP hoặc hostname client dùng được resolve và route tới đúng máy/network namespace.
5. Firewall, security group, network policy và proxy cho phép kết nối.
6. Nếu dùng HTTPS, TLS phải được cấu hình đúng ở server hoặc tại reverse proxy.

**server.address không đăng ký DNS** và **server.port không tự cấu hình NAT**. Một hostname có thể được công bố trên public DNS và reverse proxy có thể lắng nghe port 443, trong khi Spring Boot chỉ mở 127.0.0.1:8080 hoặc 0.0.0.0:8080 ở mạng nội bộ.

Ví dụ topology:

~~~text
Trình duyệt
https://shop.example.org:443
        |
        v
Load balancer / reverse proxy :443
        |
        v
Spring Boot :8080 (private network)
~~~

Trong mô hình này, client dùng cổng 443 và hostname công khai. Spring Boot lắng nghe port 8080. Hai cổng khác nhau không phải lỗi; đó là cách reverse proxy chuyển tiếp request. Bind address của Spring Boot phải phù hợp với kết nối nội bộ tới proxy.

Nếu muốn tạo HTTPS trực tiếp tại Spring Boot, cần cấu hình TLS (server.ssl.* hoặc cấu hình SSL bundle phù hợp với phiên bản Boot) cùng port mong muốn. Đổi server.port từ 8080 sang 443 **không tự biến HTTP thành HTTPS**.

## 6. Ví dụ Spring Boot chạy được để quan sát bind

Dùng ứng dụng Spring Boot 3.x với Java 17+, dependency spring-boot-starter-web và file App.java:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class App {

    @GetMapping("/hello")
    public String hello() {
        return "hello";
    }

    public static void main(String[] args) {
        SpringApplication.run(App.class, args);
    }
}
~~~

Đặt file ở src/main/java/example/App.java và application.yaml ở src/main/resources/application.yaml:

~~~yaml
server:
  port: 8085
  address: 127.0.0.1
~~~

Chạy trong dự án Spring Boot Maven đã khai báo starter-web:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell, dùng:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Từ chính máy chạy ứng dụng:

~~~bash
curl -s http://127.0.0.1:8085/hello
~~~

Phần **HTTP response body** mong đợi là:

~~~text
hello
~~~

Đây là response body, không phải toàn bộ stdout khi khởi động Spring Boot. Log khởi động có thể thay đổi theo phiên bản server, cấu hình log và môi trường.

Nếu đổi address sang 0.0.0.0 rồi khởi động lại ứng dụng, cùng endpoint có thể được truy cập qua IP LAN thực sự của máy, chẳng hạn http://192.168.1.20:8085/hello, **nếu IP này thuộc máy chủ và đường mạng cho phép**. Không coi ví dụ 192.168.1.20 là IP thật của mọi máy.

Ví dụ này cần Spring Boot dependencies và Maven project; không thể biên dịch bằng lệnh javac trần chỉ với Java Standard Library, vì nó import các lớp Spring.

## 7. Cấu hình theo môi trường và độ ưu tiên

Thuộc tính server.* là externalized configuration, có thể đưa vào application.properties, application.yaml, profile-specific files, biến môi trường hoặc command-line arguments.

Ví dụ application.yaml cho giá trị dùng chung:

~~~yaml
server:
  port: 8080
~~~

Ví dụ application-dev.yaml cho development:

~~~yaml
server:
  port: 8085
  address: 127.0.0.1
~~~

Ví dụ application-prod.yaml cho deployment với network riêng:

~~~yaml
server:
  port: 8080
  address: 0.0.0.0
~~~

Khi kích hoạt profile dev, Spring Boot sử dụng các giá trị tương ứng theo thứ tự ưu tiên PropertySource. Cần hiểu rằng một profile đang active không có nghĩa mọi giá trị đều đến từ file đó: biến môi trường, command-line options hoặc nguồn cấu hình có độ ưu tiên cao hơn có thể override.

Ví dụ ghi đè cổng khi chạy:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=9090
~~~

Hoặc chạy file JAR:

~~~bash
java -jar app.jar --server.port=9090 --server.address=127.0.0.1
~~~

Biến môi trường thông dụng theo relaxed binding:

~~~bash
export SERVER_PORT=9090
export SERVER_ADDRESS=0.0.0.0
java -jar app.jar
~~~

Tùy môi trường shell, cú pháp đặt biến môi trường có thể khác nhau. Ví dụ PowerShell:

~~~powershell
$env:SERVER_PORT = "9090"
$env:SERVER_ADDRESS = "127.0.0.1"
java -jar app.jar
~~~

Trong dự án có cấu hình từ nhiều nguồn, hãy xác nhận giá trị hiệu lực ở runtime. Không đọc một file application.yaml rồi kết luận chắc chắn server đang dùng cổng đó nếu có profile, biến môi trường hoặc command-line override.

## 8. Server trong Docker và Kubernetes

### Docker: listen trong container và port publication trên host

Ví dụ chạy image ứng dụng:

~~~bash
docker run --rm -p 8085:8080 -e SERVER_PORT=8080 -e SERVER_ADDRESS=0.0.0.0 my-spring-app
~~~

Ở đây:

- Container process lắng nghe cổng 8080 và bind 0.0.0.0 trong network namespace của container.
- Docker publish cổng 8085 trên host và chuyển tiếp tới cổng 8080 của container.
- Client trên host thường dùng http://localhost:8085.
- Client từ máy khác muốn vào host phải dùng địa chỉ mạng của host và được firewall/routing cho phép.

Nếu ứng dụng trong container chỉ bind 127.0.0.1, published port có thể không truy cập được từ host qua bridge networking vì port forwarding đi vào địa chỉ mạng của container, không vào loopback nội bộ của nó.

Tránh nhầm hai cú pháp:

- **server.port**: cổng server bind **bên trong container**, ví dụ 8080.
- **docker -p 8085:8080**: ánh xạ **host port 8085** sang **container port 8080**.

Dockerfile EXPOSE 8080 chỉ mô tả cổng dự kiến; tự nó không publish cổng trên host. Một số môi trường có networking khác với bridge mặc định nên cần kiểm tra topology thực tế.

### Kubernetes: containerPort không tự mở endpoint công khai

Một container trong Pod có thể đặt:

~~~yaml
ports:
  - containerPort: 8080
    name: http
~~~

containerPort mô tả cổng mà process dự kiến lắng nghe; Kubernetes không tự biến dòng này thành listener. Spring Boot vẫn phải bind đúng địa chỉ và cổng.

Kubernetes Service có thể định tuyến tới Pod port thông qua targetPort. Ví dụ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: web-api
spec:
  selector:
    app: web-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Service này định tuyến port 80 nội bộ cluster sang port 8080 trên Pod được chọn. Nó không tự khởi động server, không thay đổi server.port của ứng dụng và không có nghĩa Service được truy cập từ Internet.

Kubernetes Pod IP thuộc môi trường mạng có thể thay đổi. Đối với ứng dụng container hóa, bind 0.0.0.0 với cổng do deployment cấu hình thường ổn định hơn hardcode Pod IP vào server.address. Kết nối vào Pod còn phụ thuộc Service, Ingress/Gateway, CNI và NetworkPolicy.

## 9. server.port=0 và cách lấy cổng thật

Đặt cổng bằng 0 hữu ích khi nhiều integration test chạy song song vì mỗi test server có thể được OS cấp cổng riêng.

~~~yaml
server:
  port: 0
~~~

Trong Spring Boot test dùng random port:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AppHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void respondsOnAssignedPort() {
        String body = restTemplate.getForObject(
                "http://localhost:" + port + "/hello",
                String.class
        );
        assertThat(body).isEqualTo("hello");
    }
}
~~~

Đây là mã test trong cùng dự án Spring Boot 3.x có spring-boot-starter-test và controller /hello ở ví dụ trước. Không phải đoạn Java độc lập; nó cần test context do Spring Boot khởi động.

Lưu ý: RANDOM_PORT có thể override cấu hình server.port trong các nguồn cấu hình thông thường theo cách Spring Boot test thiết lập environment. @LocalServerPort chỉ có giá trị đáng tin cậy sau khi server nhúng đã được khởi động trong môi trường test phù hợp.

Một cách khác để biết cổng đã bind là lắng nghe WebServerInitializedEvent khi web server sẵn sàng:

~~~java
package example;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class BoundPortReporter {

    @EventListener
    void afterServerStarted(WebServerInitializedEvent event) {
        int port = event.getWebServer().getPort();
        System.out.println("Actual server port: " + port);
    }
}
~~~

Ví dụ này dành cho Spring Boot 3.x. Giá trị port được in là cổng runtime thật, do đó không nên đưa ra stdout cố định khi server.port=0 vì mỗi lần chạy có thể khác nhau.

## 10. Kiểm tra địa chỉ và cổng đang thực sự lắng nghe

### Kiểm tra từ ứng dụng

Đọc log khởi động và kiểm tra ứng dụng có startup thành công không. Nếu server lỗi bind, khởi động có thể thất bại trước khi có endpoint.

### Kiểm tra listener ở hệ điều hành

Linux, ví dụ:

~~~bash
ss -ltnp
~~~

Có thể lọc port:

~~~bash
ss -ltnp 'sport = :8085'
~~~

Trên Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8085
~~~

Cột LocalAddress hoặc equivalent cho biết listener bind 127.0.0.1, 0.0.0.0, ::1, :: hoặc IP cụ thể. Giá trị hiển thị còn phụ thuộc OS và quyền quan sát process.

### Kiểm tra đường kết nối từ nhiều vị trí

Trên máy chạy Spring Boot:

~~~bash
curl -v --connect-timeout 3 http://127.0.0.1:8085/hello
~~~

Trên máy khác trong cùng LAN, thay bằng IP LAN thực của server:

~~~bash
curl -v --connect-timeout 3 http://192.168.1.20:8085/hello
~~~

Nếu localhost thành công nhưng LAN thất bại, các điểm cần kiểm tra gồm listener có bind vào loopback hay không, firewall, IP/port đúng chưa và có route đến server hay không. Nếu cả hai thất bại, kiểm tra server đã start, endpoint path và các lỗi startup.

Với hostname localhost có cả A record và AAAA record, client có thể thử 127.0.0.1 hoặc ::1. Khi muốn kiểm tra một họ địa chỉ cụ thể:

~~~bash
curl -4 -v http://localhost:8085/hello
curl -6 -v http://localhost:8085/hello
~~~

Lệnh IPv6 có thể thất bại nếu server chỉ bind IPv4, và điều đó không chứng minh server không chạy.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Port 8080 already in use | Process khác đã bind cùng địa chỉ/cổng hoặc có listener xung đột | Tìm process bằng ss/netstat/Get-NetTCPConnection; đổi port hoặc dừng process đúng |
| Cannot assign requested address | server.address trỏ tới IP không thuộc interface cục bộ | Dùng địa chỉ hiện có hoặc wildcard phù hợp |
| Kết nối từ localhost được nhưng máy khác không vào được | Bind 127.0.0.1, firewall hoặc không có route | Xác nhận listener, dùng địa chỉ bind phù hợp và kiểm tra network policy |
| Docker đã -p nhưng host không truy cập được | App chỉ bind 127.0.0.1 bên trong container, map port sai hoặc process chưa khởi động | Bind 0.0.0.0 trong container, kiểm tra container port và published host port |
| server.port=0 nhưng gọi localhost:0 | Nhầm giá trị yêu cầu cấp cổng với cổng runtime | Lấy cổng thật sau startup qua event/log hoặc @LocalServerPort |
| Dùng URL http://0.0.0.0:8080 từ máy khác | Nhầm wildcard bind với địa chỉ client truy cập | Dùng địa chỉ IP/hostname thực của host hoặc proxy |
| Đã đổi server.port nhưng vẫn chạy port cũ | Có biến môi trường, profile hoặc CLI override | Kiểm tra nguồn cấu hình và giá trị đang có hiệu lực |
| HTTP kết nối được nhưng HTTPS thất bại | Chưa cấu hình TLS hoặc proxy terminate TLS ở port khác | Kiểm tra scheme, port và server.ssl/reverse proxy |
| Chỉ một trong IPv4/IPv6 hoạt động | Bind vào 127.0.0.1 hoặc ::1, hoặc cấu hình dual-stack khác kỳ vọng | Xác nhận local listener và thử curl -4/-6 |
| Kubernetes Service không vào được Pod | App chưa bind đúng, sai targetPort/selector, readiness hoặc network policy | Xác minh Pod logs, listener, Service endpoints và targetPort |

Đọc thông báo lỗi thật trước khi thay đổi cấu hình. “Connection refused” thường chỉ ra không có listener phù hợp ở endpoint hoặc kết nối bị từ chối tức thì. “Connection timed out” thường cần kiểm tra đường mạng/firewall. HTTP 404 nghĩa là đã kết nối tới HTTP server nhưng đường dẫn chưa được xử lý như mong đợi; lúc này không nên vội kết luận là sai bind address.

## 12. Phân biệt cổng ứng dụng với các cổng liên quan

Các thuộc tính dễ nhầm:

- **server.port**: cổng HTTP của ứng dụng embedded server.
- **server.address**: địa chỉ local bind của server đó.
- **management.server.port**: có thể cấu hình management/Actuator HTTP endpoints trên cổng riêng nếu ứng dụng có Actuator và cấu hình phù hợp.
- **server.servlet.context-path**: đổi URL path prefix của ứng dụng servlet; không đổi địa chỉ hoặc cổng.
- **spring.webflux.base-path**: tương ứng với base path của WebFlux khi được hỗ trợ bởi cấu hình web stack; không phải bind address.
- **server.forward-headers-strategy**: xử lý forwarded headers từ proxy trong các trường hợp phù hợp; không quyết định socket bind.

Khi chạy phía sau proxy, HTTP Host hoặc X-Forwarded-Host có thể khác địa chỉ server đang bind. Không dùng hostname trong HTTP header để suy ra local IP của listener. Cũng không suy luận public URL từ server.address vì địa chỉ đó thuộc tầng hạ tầng máy chủ.

## 13. Quy trình chọn cấu hình cho từng môi trường

**Máy phát triển, chỉ cần truy cập từ chính máy:** dùng 127.0.0.1 với cổng không xung đột như 8080 hoặc 8085. Cách này giảm việc vô tình mở dịch vụ ra LAN.

**Máy thử nghiệm trong LAN:** dùng 0.0.0.0 hoặc IP interface LAN cụ thể; truy cập qua IP LAN thực. Kiểm tra firewall và không mặc định rằng mạng cho phép mọi client.

**Docker hoặc Kubernetes:** thông thường để app bind 0.0.0.0 trong container và mở một container port nhất quán. Publish port hoặc dùng Service/Ingress ở lớp hạ tầng. Không hardcode Pod IP hay dùng 127.0.0.1 trong container nếu thành phần khác phải truy cập qua network.

**Production phía sau reverse proxy:** có thể bind interface riêng hoặc 0.0.0.0 trên mạng hạn chế, đặt firewall/network policy và chỉ public qua proxy. TLS, DNS, rate limiting, authentication và public port thường do kiến trúc triển khai quyết định.

**Integration test:** dùng random port (server.port=0 hoặc @SpringBootTest RANDOM_PORT) và lấy cổng thật sau startup. Tránh hardcode cùng một port cho nhiều test server chạy song song.

## 14. Checklist xác minh trước khi triển khai

1. Web stack và embedded server đúng với dependencies đang dùng.
2. server.port là cổng dự kiến; nếu dùng 0 thì test/client đọc cổng runtime.
3. server.address trỏ tới địa chỉ thực sự có thể bind trong network namespace.
4. Không nhầm 0.0.0.0 và :: với hostname hoặc public URL.
5. Client sử dụng địa chỉ/cổng có thể định tuyến tới server hoặc proxy.
6. Firewall, NAT, container port mapping, Service/Ingress và TLS phù hợp với topology.
7. Đã kiểm tra cấu hình có hiệu lực sau khi áp dụng profile, biến môi trường và CLI.
8. Đã thử request từ đúng nơi client thực tế chạy, không chỉ từ localhost của server.
9. Đã phân biệt lỗi connect, lỗi HTTP status và lỗi route/endpoint.
10. Với môi trường có nhiều interface hoặc IPv4/IPv6, đã xác nhận socket listener thực tế.

Ghi nhớ: **server.port chọn cổng**, **server.address chọn local IP/interface để bind**, còn **client URL phụ thuộc vào DNS, route và lớp hạ tầng phía trước**. Hiểu ba vai trò này giúp cấu hình ứng dụng Spring Boot đúng khi chạy local, trên server nhiều card mạng, trong container và sau reverse proxy.