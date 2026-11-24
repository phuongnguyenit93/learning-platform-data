# Quyền truy cập và bảo mật JMX

JMX (Java Management Extensions) cung cấp giao diện quản trị cho ứng dụng Java thông qua các MBean. Trong ứng dụng Spring Integration, JMX thường được dùng để quan sát trạng thái và số liệu của message channel, endpoint, adapter, handler hoặc các thành phần tích hợp khác. Một số MBean còn cung cấp thao tác quản trị như thay đổi thuộc tính hay điều khiển vòng đời thành phần.

Vì vậy, JMX là một phần của **management plane** (mặt phẳng quản trị), tách biệt với luồng message và giao thức kết nối tới hệ thống ngoài. Việc một adapter dùng HTTPS, SFTP, JMS, AMQP hay Kafka có xác thực tốt không tự động bảo vệ cổng JMX của JVM. Nếu JMX bị mở rộng quyền truy cập, người ngoài có thể đọc thông tin vận hành hoặc tác động đến các thành phần đang xử lý message. Cần thiết kế quyền JMX như quyền truy cập quản trị vào chính ứng dụng.

## JMX nằm ở đâu trong ứng dụng Spring Integration?

Một luồng tích hợp thường có adapter nhận hoặc gửi dữ liệu, các message channel, endpoint và handler. JMX không thay thế các thành phần đó và cũng không vận chuyển message nghiệp vụ. Nó cung cấp một giao diện để công cụ quản trị truy vấn hoặc gọi các thao tác được MBean công bố.

Với Spring Integration, `IntegrationMBeanExporter` và annotation `@EnableIntegrationMBeanExport` có thể đăng ký các thành phần Integration được hỗ trợ dưới dạng MBean. MBean cụ thể và các thuộc tính hoặc thao tác được công bố phụ thuộc loại component và phiên bản framework. Hãy kiểm tra danh sách MBean thực tế trong môi trường chạy, thay vì giả định mọi bean đều được xuất hoặc mọi thuộc tính nội bộ đều có thể truy cập.

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.EnableIntegrationMBeanExport;

@Configuration
@EnableIntegration
@EnableIntegrationMBeanExport
public class IntegrationJmxConfiguration {
}
```

Khi bật exporter, ứng dụng có thể cho phép công cụ JMX quan sát các thành phần Integration. Việc bật exporter chỉ tạo khả năng quản trị; nó không tự thiết lập một chính sách bảo mật đầy đủ cho kết nối JMX từ xa. Xác thực, phân quyền, mã hóa đường truyền và giới hạn mạng vẫn phải được cấu hình ở tầng JVM hoặc connector JMX.

## Xác định tài nguyên và thao tác cần bảo vệ

Trước khi mở JMX, hãy lập danh sách dữ liệu và thao tác mà đội vận hành thực sự cần. Với một hệ thống adapter, các mục thường gặp gồm:

| Nhóm | Ví dụ | Rủi ro khi cấp quyền quá rộng |
|---|---|---|
| Quan sát | Trạng thái endpoint, số message, bộ đếm lỗi, thời gian xử lý | Lộ cấu trúc hệ thống, tên queue hoặc channel, nhịp xử lý và thông tin vận hành |
| Cấu hình | Thuộc tính MBean được phép đọc hoặc thay đổi | Lộ cấu hình kết nối; thay đổi sai có thể làm gián đoạn luồng tích hợp |
| Điều khiển | Thao tác start, stop hoặc các operation quản trị được công bố | Dừng endpoint, ngắt nhận/gửi message hoặc làm thay đổi trạng thái ứng dụng |
| MBean tùy chỉnh | Thông tin do ứng dụng tự công bố | Có thể lộ dữ liệu nhạy cảm nếu đưa token, thông tin xác thực, header hoặc payload vào thuộc tính quản trị |

Quyền đọc cũng cần được xem xét. Một tài khoản chỉ đọc vẫn có thể thu thập tên hệ thống, địa chỉ dịch vụ, thông tin trạng thái hoặc số liệu đủ để hỗ trợ một cuộc tấn công. Không đưa mật khẩu broker, private key, access token, nội dung message hay dữ liệu cá nhân vào thuộc tính MBean. Nếu cần chẩn đoán payload, hãy dùng một cơ chế được kiểm soát riêng, có giới hạn dữ liệu và thời gian lưu.

## Phân biệt JMX cục bộ và JMX từ xa

JMX cục bộ cho phép công cụ trên cùng máy hoặc cùng môi trường tiến trình kết nối tới JVM. Cơ chế này thường dựa vào quyền của hệ điều hành và khả năng attach vào tiến trình. Vì vậy, chỉ người dùng hệ điều hành đáng tin cậy mới nên có quyền chạy công cụ quản trị hoặc truy cập namespace chứa JVM. Không xem JMX cục bộ là ranh giới bảo mật nếu nhiều workload hoặc nhiều người dùng cùng chia sẻ máy chủ hay container host.

JMX từ xa thường dùng RMI connector của JDK. Khi bật remote JMX, JVM có thể mở cổng đăng ký RMI và cổng của RMI connector. Nếu chỉ cố định một cổng mà để cổng còn lại được cấp động, firewall và chính sách mạng sẽ khó kiểm soát. Hãy cấu hình cả hai cổng cố định, đặt địa chỉ RMI mà client có thể truy cập, rồi chỉ cho phép kết nối từ mạng quản trị hoặc máy bastion được phê duyệt.

Ví dụ cấu hình JVM cho một môi trường cần JMX từ xa:

```text
-Dcom.sun.management.jmxremote
-Dcom.sun.management.jmxremote.port=9010
-Dcom.sun.management.jmxremote.rmi.port=9011
-Djava.rmi.server.hostname=jmx-host.internal
-Dcom.sun.management.jmxremote.authenticate=true
-Dcom.sun.management.jmxremote.password.file=/run/secrets/jmxremote.password
-Dcom.sun.management.jmxremote.access.file=/etc/jmx/jmxremote.access
-Dcom.sun.management.jmxremote.ssl=true
```

Đây là ví dụ cho JMX agent quản lý của JDK; đường dẫn, hostname và cổng phải được thay bằng giá trị của môi trường triển khai. Cổng `9010` là cổng registry trong ví dụ, còn `9011` là cổng RMI connector. `java.rmi.server.hostname` phải là địa chỉ mà máy quản trị phân giải và truy cập được. Nếu ứng dụng chạy trong container hoặc sau NAT, cần kiểm tra đường đi của cả hai cổng từ client tới đúng JVM.

Nếu không có nhu cầu quản trị từ xa, đừng bật remote JMX. Trong môi trường production, ưu tiên truy cập qua mạng quản trị riêng, VPN hoặc bastion; không công khai cổng JMX trên Internet hay mạng người dùng. Nếu nền tảng triển khai có cơ chế quản trị thay thế đáp ứng yêu cầu, hãy cân nhắc dùng cơ chế đó thay cho việc mở thêm RMI connector.

## Xác thực và phân quyền

Với JMX remote agent của JDK, hãy bật xác thực một cách tường minh. Hai file thường dùng là password file và access file. Password file ánh xạ tên người dùng với mật khẩu; access file quy định mức quyền của từng người dùng.

Ví dụ access file:

```text
monitorUser readonly
operatorUser readwrite
```

`readonly` dành cho tài khoản giám sát chỉ cần đọc MBean. `readwrite` cho phép quyền rộng hơn, bao gồm thay đổi thuộc tính hoặc gọi operation được MBean công bố. Vì vậy, chỉ cấp `readwrite` cho nhóm vận hành có trách nhiệm rõ ràng; không dùng chung tài khoản quản trị cho dashboard hoặc tác vụ thu thập metrics.

Password file có thể chứa mật khẩu ở dạng văn bản rõ. Bảo vệ file bằng quyền hệ điều hành chặt chẽ: chỉ tài khoản chạy JVM hoặc tài khoản được chỉ định mới đọc được. Trên hệ thống Unix, thường cần quyền chỉ chủ sở hữu đọc/ghi; trên Windows, dùng ACL tương đương. Đặt file bên ngoài source control và image ứng dụng, lấy bí mật từ secret manager hoặc cơ chế mount secret của nền tảng, đồng thời có quy trình xoay vòng mật khẩu. Không ghi mật khẩu thật vào ví dụ, log, tham số triển khai được lưu công khai hoặc tài liệu vận hành.

Ví dụ trên minh họa phân quyền theo người dùng ở mức cơ bản. Access file không thay thế việc thiết kế quyền chi tiết cho từng MBean. Nếu một nhóm chỉ được xem một tập MBean nhất định hoặc chỉ được gọi một số operation cụ thể, cần thiết kế lớp xác thực và kiểm soát truy cập phù hợp, chẳng hạn connector với authenticator và `MBeanServerForwarder` tùy chỉnh. Phải kiểm thử các operation thực tế vì một MBean tùy chỉnh có thể cung cấp quyền mạnh hơn dự kiến.

## Mã hóa đường truyền và giới hạn mạng

Xác thực không mã hóa dữ liệu trên đường truyền. Bật TLS cho JMX remote connector và quản lý chứng thư bằng quy trình tương tự các dịch vụ quản trị khác. Khi yêu cầu bảo đảm danh tính cả hai phía, cấu hình xác thực chứng thư client (mutual TLS) và chỉ tin cậy CA hoặc chứng thư của các máy quản trị được phép.

Các nguyên tắc triển khai quan trọng:

- Chỉ mở các cổng JMX cố định trên interface hoặc vùng mạng cần thiết; firewall, security group và network policy phải giới hạn nguồn kết nối.
- Dùng chứng thư còn hiệu lực, kiểm tra hostname và chuỗi tin cậy; có kế hoạch gia hạn và thu hồi chứng thư.
- Không tắt xác thực hoặc TLS để xử lý nhanh lỗi kết nối trong production. Hãy xác định lỗi nằm ở DNS, cổng, firewall, chứng thư hay thông tin đăng nhập.
- Giữ quyền truy cập hệ điều hành vào tiến trình JVM và file bí mật ở mức tối thiểu.
- Ghi nhận hoạt động quản trị theo chính sách của nền tảng. Không ghi mật khẩu, token hoặc dữ liệu nhạy cảm vào log.

Nếu connector sử dụng RMI, TLS và firewall cần được cấu hình nhất quán cho cả registry lẫn connector. Việc chỉ mã hóa hoặc mở đúng một cổng có thể khiến client kết nối được registry nhưng thất bại khi gọi tới connector. Kiểm tra từ đúng mạng và máy client mà đội vận hành sẽ sử dụng.

## JMX của Spring Integration và JMX của Spring Boot Actuator

Hai cơ chế thường cùng xuất hiện trong một ứng dụng Spring Boot nhưng có mục đích khác nhau:

- Spring Integration JMX exporter công bố các MBean liên quan tới thành phần tích hợp, tùy component và cấu hình.
- Spring Boot Actuator JMX exposure công bố các endpoint Actuator dưới dạng MBean để công cụ JMX truy vấn.

Ví dụ cấu hình Actuator JMX trong `application.yml`:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    jmx:
      exposure:
        include: health,info,metrics
```

Danh sách endpoint thực tế phụ thuộc phiên bản Spring Boot và endpoint có trong ứng dụng. Chỉ đưa vào danh sách những endpoint cần thiết; tránh dùng wildcard `*` trong production nếu chưa đánh giá toàn bộ dữ liệu mà mỗi endpoint công bố. Nếu ứng dụng bật cả Integration exporter và Actuator JMX, hãy rà soát cả hai tập MBean. Bảo vệ connector JMX ở tầng JVM vẫn áp dụng cho kết nối remote, nhưng việc bật một exporter không tự động giới hạn tập MBean do exporter còn lại công bố.

## Quy trình kiểm tra trước khi đưa vào production

1. **Xác định nhu cầu:** ghi rõ nhóm vận hành cần xem số liệu nào và operation nào thực sự cần thiết. Tắt remote JMX nếu không có nhu cầu.
2. **Rà soát MBean:** liệt kê MBean và thuộc tính hoặc operation được công bố trong môi trường thử nghiệm. Kiểm tra MBean tùy chỉnh để chắc chắn không lộ credential, payload hoặc dữ liệu cá nhân.
3. **Tạo danh tính riêng:** dùng tài khoản chỉ đọc cho giám sát; tách tài khoản có quyền thay đổi hoặc điều khiển cho người vận hành. Không chia sẻ một tài khoản giữa nhiều hệ thống.
4. **Cấu hình kết nối:** cố định cổng registry và connector, bật xác thực và TLS, giới hạn nguồn kết nối ở lớp mạng.
5. **Kiểm thử quyền:** kết nối bằng tài khoản giám sát và xác nhận có thể đọc đúng dữ liệu cần thiết nhưng không thể thay đổi thuộc tính hoặc gọi operation quản trị. Dùng tài khoản vận hành để kiểm tra riêng các thao tác được phép.
6. **Kiểm thử lỗi:** thử thông tin đăng nhập sai, chứng thư không hợp lệ, kết nối từ mạng không được phép và tình huống RMI trả về địa chỉ không thể truy cập. Các trường hợp này phải thất bại an toàn.
7. **Theo dõi sau triển khai:** giám sát lỗi kết nối JMX, thay đổi quyền, thao tác điều khiển endpoint và việc sử dụng tài khoản quản trị. Xoay vòng hoặc thu hồi thông tin xác thực khi người dùng thay đổi vai trò.

Một bài kiểm tra quyền tối thiểu có thể dùng JConsole hoặc công cụ JMX tương đương từ máy thuộc mạng quản trị. Thử kết nối bằng từng vai trò, đọc một MBean được cho phép, sau đó thử một thao tác ghi hoặc điều khiển trong môi trường kiểm thử. Kết quả mong đợi là tài khoản chỉ đọc bị từ chối thao tác thay đổi, tài khoản quản trị chỉ hoạt động từ nguồn mạng được phép và kết nối không có chứng thư hoặc thông tin xác thực hợp lệ bị từ chối.

## Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không kết nối được tới JMX | JVM chưa bật remote agent, sai hostname, sai cổng registry, firewall chặn hoặc client không tới được cổng RMI connector |
| Registry kết nối được nhưng truy vấn MBean thất bại | Cổng connector chưa được mở, RMI quảng bá hostname không thể truy cập hoặc NAT/network policy chưa ánh xạ đúng |
| Bị từ chối đăng nhập | Sai tên người dùng/mật khẩu, password file không đúng định dạng hoặc JVM không đọc được file |
| Đăng nhập được nhưng không gọi được operation | Tài khoản chỉ có `readonly`, hoặc MBean không công bố operation đó |
| Client báo lỗi SSL | Truststore/keystore, hostname, chứng thư hết hạn hoặc cấu hình xác thực client không khớp |
| Không thấy MBean mong đợi | Exporter chưa được bật, component không thuộc nhóm được exporter hỗ trợ, cấu hình domain/server khác hoặc MBean chưa được đăng ký |

Không khắc phục lỗi bằng cách tắt xác thực, tắt TLS hoặc cấp `readwrite` cho tất cả người dùng. Hãy dùng thông báo lỗi và log phía JVM để xác định đúng lớp đang thất bại, sau đó sửa hostname, cổng, chứng thư, quyền file hoặc cấu hình exporter tương ứng.

## Nguyên tắc cần duy trì

JMX cho phép vận hành quan sát và điều khiển ứng dụng Spring Integration ở mức JVM. Bảo vệ nó bằng cách chỉ công bố MBean cần thiết, tách tài khoản giám sát khỏi tài khoản quản trị, bật xác thực và TLS cho remote connector, giới hạn mạng truy cập và bảo vệ bí mật bằng quyền hệ điều hành. Khi thay đổi adapter hoặc thêm MBean tùy chỉnh, hãy rà soát lại dữ liệu và operation được công bố như một phần của thay đổi đó. Nhờ vậy, công cụ quản trị có thể hỗ trợ theo dõi message flow mà không trở thành một đường truy cập không kiểm soát vào ứng dụng.
