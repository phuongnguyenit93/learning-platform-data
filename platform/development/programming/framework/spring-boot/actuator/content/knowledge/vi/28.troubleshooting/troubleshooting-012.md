# Xử lý trùng tên MBean, sai cổng quản trị và xung đột cấu hình theo môi trường

## 1. Hiểu ba lớp trước khi sửa sự cố

Một ứng dụng có thể chạy được API nghiệp vụ nhưng công cụ giám sát vẫn không truy cập được Actuator. Ngược lại, ứng dụng có thể dừng ngay khi khởi động do đăng ký MBean hoặc mở cổng thất bại. Cần xác định lỗi xảy ra ở lớp nào trước khi thay cấu hình.

- **JMX** là cơ chế quản trị đối tượng Java. **MBean** là đối tượng được đưa ra để giám sát hoặc quản trị; **MBeanServer** quản lý các đối tượng này; **ObjectName** là tên đăng ký của từng MBean.
- **HTTP quản trị** là đường truy cập các endpoint Actuator qua HTTP, chẳng hạn đường dẫn health. Nó có địa chỉ lắng nghe, cổng, giao thức và đường dẫn.
- **Cấu hình hiệu lực** là giá trị cuối cùng Spring Boot sử dụng sau khi xét tệp cấu hình, profile, biến môi trường và tham số khởi động. Giá trị nhìn thấy trong một tệp chưa chắc là giá trị đang có hiệu lực.

Hãy hình dung một dịch vụ đặt hàng có ba câu hỏi khác nhau: “Đối tượng quản trị này tên gì?”, “Công cụ giám sát phải kết nối vào đâu?” và “Ai đã quyết định những giá trị đó?”. Lỗi trùng MBean trả lời câu thứ nhất, sai cổng trả lời câu thứ hai, còn cấu hình theo môi trường giúp truy nguyên câu thứ ba.

Bài dùng Spring Boot 3.3.x cho các khóa cấu hình. Các đoạn YAML được áp dụng vào một ứng dụng web đã có Actuator; chúng không phải toàn bộ một dự án. Ví dụ JMX ở mục 3 là chương trình Java độc lập, chạy được bằng JDK 17 trở lên.

## 2. Phân loại bằng bằng chứng quan sát được

| Dấu hiệu | Nhánh cần kiểm tra đầu tiên | Bằng chứng cần lấy |
| --- | --- | --- |
| Chuỗi nguyên nhân có `InstanceAlreadyExistsException` | Hai lần đăng ký cùng tên trong một MBeanServer | ObjectName đầy đủ, thành phần đăng ký, vòng đời context |
| Khởi động báo cổng đã được sử dụng hoặc có `BindException` | Không mở được socket lắng nghe | Cổng thực tế, địa chỉ bind, tiến trình đang chiếm cổng |
| Máy khách báo connection refused | Không có nơi lắng nghe tại địa chỉ đang gọi, hoặc kết nối bị từ chối | Trạng thái ứng dụng, socket trong đúng máy/container |
| Kết nối hết thời gian chờ | Đường mạng, firewall, định tuyến hoặc máy đích | Thử từ gần ứng dụng trước rồi từ máy giám sát |
| HTTP 404 | Đường dẫn, cổng, endpoint được phơi bày hoặc dịch vụ đích | URL đầy đủ, cấu hình endpoint, định danh tiến trình |
| HTTP 401 hoặc 403 | Chính sách xác thực/phân quyền tại ứng dụng hoặc proxy | Thành phần tạo phản hồi, thông tin xác thực và quyền |
| HTTP 503 từ health | Endpoint đã trả lời nhưng báo trạng thái không khỏe theo ánh xạ trạng thái | Nội dung health và thành phần gây trạng thái |
| Chỉ lỗi ở một môi trường | Khác biệt cấu hình hoặc hạ tầng | Profile hiệu lực, tham số chạy, biến môi trường, ánh xạ cổng |

Các dấu hiệu HTTP là hướng điều tra, không phải kết luận tuyệt đối. Ví dụ 404 có thể do proxy trả về; 200 có thể đến từ một ứng dụng khác đang chiếm đúng cổng. Luôn kiểm tra cả nơi tạo phản hồi.

Không lấy dòng `BeanCreationException` ngoài cùng làm nguyên nhân cuối cùng. Đọc chuỗi `Caused by` để tìm ngoại lệ và tài nguyên cụ thể: tên MBean hay địa chỉ/cổng.

## 3. Trùng tên MBean: xung đột nằm trong sổ đăng ký

### 3.1. ObjectName không phải tên Spring bean

Một tên MBean có dạng:

```text
com.example.orders:type=Endpoint,name=Health
```

`com.example.orders` là miền tên (domain); phần sau dấu hai chấm là các cặp khóa–giá trị. Hai MBean không thể đăng ký cùng một ObjectName trong cùng một MBeanServer. Việc đảo thứ tự các cặp khóa–giá trị không tạo ra tên mới. Có thể dùng `getCanonicalName()` để so sánh tên ở dạng chuẩn hóa. Xem [ObjectName của Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html).

Phạm vi này giúp tránh một suy luận sai: hai JVM độc lập có thể có MBean cùng tên mà không xung đột đăng ký với nhau. Ngược lại, hai Spring ApplicationContext trong cùng JVM có thể cùng dùng một MBeanServer và đăng ký tên giống nhau.

Các tình huống cần phân biệt:

1. Hai context hợp lệ cùng xuất một endpoint và chưa phân biệt tên.
2. Một đối tượng bị hai cơ chế xuất MBean cùng đăng ký.
3. Context cũ hoặc cơ chế đăng ký thủ công chưa giải phóng MBean khi kết thúc.
4. MBean thuộc thư viện khác có quy tắc đặt tên riêng, không chịu sự điều khiển của cấu hình Actuator.

Đổi `server.port` không sửa được các tình huống trên. Cổng HTTP không tham gia định danh ObjectName.

### 3.2. Thí nghiệm Java độc lập

Lưu toàn bộ mã sau thành `MBeanCollisionDemo.java`. Chương trình tự tạo một MBeanServer riêng để thí nghiệm không phụ thuộc các MBean đã có trong JVM.

```java
import javax.management.InstanceAlreadyExistsException;
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

public class MBeanCollisionDemo {
    public interface CounterMBean {
        int getValue();
    }

    public static class Counter implements CounterMBean {
        private final int value;

        public Counter(int value) {
            this.value = value;
        }

        @Override
        public int getValue() {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.createMBeanServer();
        ObjectName first =
                new ObjectName("com.example.lab:type=Counter,name=shared");
        ObjectName reordered =
                new ObjectName("com.example.lab:name=shared,type=Counter");
        ObjectName second =
                new ObjectName("com.example.lab:type=Counter,name=worker-2");

        try {
            System.out.println("same-name=" + first.equals(reordered));
            server.registerMBean(new Counter(1), first);

            try {
                server.registerMBean(new Counter(2), reordered);
            } catch (InstanceAlreadyExistsException exception) {
                System.out.println(exception.getClass().getSimpleName());
            }

            System.out.println("first-value="
                    + server.getAttribute(first, "Value"));

            server.registerMBean(new Counter(2), second);
            System.out.println("second-value="
                    + server.getAttribute(second, "Value"));

            server.queryNames(
                    new ObjectName("com.example.lab:type=Counter,*"), null)
                    .stream()
                    .map(ObjectName::getCanonicalName)
                    .sorted()
                    .forEach(System.out::println);
        } finally {
            if (server.isRegistered(second)) {
                server.unregisterMBean(second);
            }
            if (server.isRegistered(first)) {
                server.unregisterMBean(first);
            }
            MBeanServerFactory.releaseMBeanServer(server);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 MBeanCollisionDemo.java
java MBeanCollisionDemo
```

Stdout:

```text
same-name=true
InstanceAlreadyExistsException
first-value=1
second-value=2
com.example.lab:name=shared,type=Counter
com.example.lab:name=worker-2,type=Counter
```

Có ba điều cần rút ra từ đầu ra:

- Đảo thứ tự `type` và `name` vẫn là cùng tên.
- Đăng ký lần hai thất bại không tự thay đối tượng thứ nhất; giá trị của MBean đầu vẫn là 1.
- Đổi định danh của đối tượng thứ hai cho phép cả hai tồn tại trong cùng sổ đăng ký.

Khối `finally` giải phóng đúng các MBean của thí nghiệm. Trong ứng dụng thật, thành phần tạo đăng ký cần sở hữu cả việc hủy đăng ký; không tùy tiện hủy MBean của thư viện khác. Hợp đồng đăng ký và ngoại lệ được mô tả tại [MBeanServer.registerMBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html#registerMBean(java.lang.Object,javax.management.ObjectName)).

### 3.3. Chọn cách sửa đúng thành phần gây lỗi

Với endpoint Actuator, cấu hình sau chủ động bật JMX, đặt miền tên và yêu cầu tên duy nhất:

```yaml
spring:
  jmx:
    enabled: true
    unique-names: true

management:
  endpoints:
    jmx:
      domain: com.example.orders
      exposure:
        include: health,info
```

Spring Boot 3.3 hỗ trợ `spring.jmx.unique-names` để tránh xung đột tên khi có nhiều context; miền endpoint được điều chỉnh bằng `management.endpoints.jmx.domain`. Chi tiết tại [quản trị qua JMX của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Sau khi sửa, kiểm tra trong công cụ JMX rằng các MBean mong muốn đều tồn tại. Khi tên có thành phần được sinh lúc chạy, không sao chép cứng phần định danh đó vào cấu hình giám sát dài hạn; cần truy vấn tên phù hợp rồi xác nhận đúng đối tượng.

Nếu đang có hai ứng dụng/context cần được nhận biết riêng, có thể cấp miền endpoint khác nhau, chẳng hạn `com.example.orders.blue` và `com.example.orders.green`. Nếu hai bên vẫn nhận cùng miền tên từ cấu hình triển khai thì việc thêm khóa domain chưa giải quyết được xung đột.

Nếu lỗi thuộc MBean tự viết, xem quy tắc đặt tên của chính cơ chế xuất MBean và thuộc tính `objectName` trên `@ManagedResource` khi có dùng. Nếu lỗi thuộc thư viện bên thứ ba, tra cấu hình đặt tên của thư viện đó. Quy tắc đặt tên của Spring được giải thích tại [Controlling ObjectName Instances](https://docs.spring.io/spring-framework/reference/integration/jmx/naming.html).

Nếu cùng đối tượng bị xuất hai lần, sửa việc đăng ký trùng hoặc vòng đời. Thêm tên duy nhất vào mọi nơi có thể làm ứng dụng khởi động được nhưng vẫn để hai bản quản trị cho cùng một tài nguyên. Nếu chạy thử đi chạy thử lại trong một JVM mới xuất hiện lỗi, kiểm tra việc đóng context và giải phóng tài nguyên thay vì chỉ thử đổi domain.

### 3.4. Khi không cần JMX

Nếu ứng dụng chỉ dùng Actuator qua HTTP, có thể chủ động không bật cơ chế xuất MBean của Spring:

```yaml
spring:
  jmx:
    enabled: false
```

Nếu vẫn cần các MBean khác của Spring nhưng không muốn xuất endpoint Actuator qua JMX:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        exclude: "*"
```

Hai lựa chọn có phạm vi khác nhau. `spring.jmx.enabled` không tắt toàn bộ hạ tầng JMX của JVM và không bảo đảm ngăn thư viện tự đăng ký MBean. Cấu hình loại trừ endpoint JMX cũng không loại trừ endpoint HTTP. Những giới hạn này được nêu trong [tài liệu JMX của Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

Không bật `spring.main.allow-bean-definition-overriding` để chữa lỗi ObjectName: nó liên quan đến định nghĩa Spring bean, không phải đăng ký trong MBeanServer. Cũng không đổi sang chính sách bỏ qua/thay thế MBean có sẵn chỉ để che ngoại lệ khi chưa rõ đối tượng nào đang được giữ lại.

## 4. Sai cổng quản trị: dựng lại địa chỉ từ phía máy khách

### 4.1. Phân biệt cổng ứng dụng, cổng Actuator và cổng JMX từ xa

| Cấu hình | Vai trò | Ví dụ |
| --- | --- | --- |
| `server.port` | Cổng HTTP của ứng dụng web | 8080 |
| `management.server.port` | Cổng HTTP quản trị nếu tách riêng | 9091 |
| `com.sun.management.jmxremote.port` | Thuộc cấu hình JMX từ xa của JVM | Không phải cổng HTTP health |

Bật `spring.jmx.enabled=true` không đồng nghĩa đã mở một cổng JMX từ xa. Việc kết nối JMX từ xa còn phụ thuộc connector, cấu hình JVM và mạng. Không dùng `curl` đến cổng JMX/RMI để kiểm tra một endpoint HTTP.

Nếu không tách cổng quản trị, Actuator dùng cổng HTTP của ứng dụng. Nếu tách, công cụ giám sát phải truy cập cổng quản trị và đường dẫn tương ứng. Hai tiến trình độc lập vẫn có thể tranh chấp cùng địa chỉ/cổng trong một không gian mạng, dù không thể xung đột ObjectName với nhau.

### 4.2. Cấu hình tách cổng và thay đường dẫn

Ví dụ dưới dành cho một ứng dụng Servlet chạy trực tiếp trên máy phát triển:

```yaml
server:
  port: 8080
  servlet:
    context-path: /orders

management:
  server:
    port: 9091
    address: 127.0.0.1
    base-path: /internal
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,info
```

Trong ví dụ, không cấu hình TLS hoặc remap riêng endpoint health:

- Cổng nghiệp vụ là 8080, với context path `/orders`.
- Health quản trị nằm tại `http://127.0.0.1:9091/internal/manage/health`.
- Không tự gắn thêm `/orders` vào URL quản trị đã tách cổng.

Quan hệ đường dẫn khi dùng chung/tách cổng được quy định tại [Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Kiểm tra từ chính máy chạy ứng dụng, dùng `curl.exe` trên Windows:

```powershell
curl.exe -i http://127.0.0.1:9091/internal/manage/health
```

Không cam kết toàn bộ JSON hay mã HTTP giống nhau ở mọi ứng dụng: health phụ thuộc các bộ kiểm tra đang có, còn truy cập có thể bị Spring Security hoặc proxy kiểm soát. Hãy ghi lại status, nội dung phản hồi và log tương ứng.

Nếu không đặt `management.server.port`, trong cùng ví dụ Servlet, URL theo cấu hình dùng chung cổng sẽ được xây từ context path ứng dụng và base path Actuator, chẳng hạn `http://127.0.0.1:8080/orders/manage/health`; đồng thời bỏ các thiết lập dành riêng cho management server tách biệt. Với WebFlux, kiểm tra `spring.webflux.base-path` thay vì dùng khóa context path của Servlet.

### 4.3. Những giá trị cổng cần đọc đúng nghĩa

- Không đặt cổng quản trị riêng: dùng cổng web chính.
- Đặt một cổng khác cổng chính: mở HTTP quản trị riêng nếu ứng dụng và cấu hình hỗ trợ.
- Đặt `management.server.port=0`: yêu cầu chọn cổng còn trống; phải lấy cổng thực tế từ log/sự kiện khởi động hoặc cơ chế hỗ trợ kiểm thử. Số 0 trong cấu hình không phải cổng để máy khách gọi.
- Đặt `management.server.port=-1`: tắt truy cập quản trị qua HTTP; không dùng giá trị này khi muốn health HTTP vẫn hoạt động.

`management.server.address` dùng địa chỉ riêng khi cổng quản trị khác cổng chính. Cấu hình loopback trong ví dụ phù hợp cho việc gọi trên cùng máy; nó không làm endpoint tự truy cập được từ máy khác.

Tra các khóa cổng và địa chỉ tại [danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

### 4.4. Kiểm tra socket và ánh xạ mạng

Nếu ứng dụng không khởi động được vì 9091 đang bị sử dụng, trên Windows có thể xem tiến trình lắng nghe:

```powershell
Get-NetTCPConnection -LocalPort 9091 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

Tra tiếp tiến trình bằng mã PID thực tế nhận được. Không dừng tiến trình chỉ vì nó đang giữ cổng: trước hết xác định đó có phải bản cũ của ứng dụng hay một dịch vụ khác.

Đối với container, viết rõ đường đi theo từng chặng. Ví dụ một container lắng nghe ở 9091 và được ánh xạ `19091:9091`:

```text
Máy chủ:19091 -> container:9091 -> /internal/manage/health
```

Máy khách trên máy chủ gọi cổng 19091; tiến trình trong container sử dụng cổng 9091. Ánh xạ cổng không tự đổi `management.server.port`.

Nếu ứng dụng trong container chỉ bind `127.0.0.1`, lưu lượng đi vào địa chỉ mạng của container có thể không đến được listener. Chọn địa chỉ bind theo mô hình mạng triển khai, đồng thời cập nhật chính sách truy cập phù hợp. Khi chỉ gọi được từ trong container nhưng không gọi được qua máy chủ, kiểm tra ánh xạ và bind trước khi sửa endpoint.

Với Kubernetes hoặc reverse proxy, đối chiếu tiếp Service `targetPort`, đường dẫn probe, giao thức HTTP/HTTPS và quy tắc viết lại đường dẫn. Một container khai báo cổng không có nghĩa mọi lớp mạng đã tự định tuyến đến đó.

## 5. Xung đột môi trường: tìm giá trị thắng, rồi tìm nguồn tạo nó

### 5.1. Một tệp đúng chưa chứng minh ứng dụng đang dùng nó

Giả sử cùng một khóa xuất hiện ở các nguồn:

| Nguồn | `management.server.port` |
| --- | --- |
| `application.yml` trong JAR | 9091 |
| `application-prod.yml` trong JAR | 9191 |
| Biến môi trường `MANAGEMENT_SERVER_PORT` | 9291 |
| Tham số chạy `--management.server.port=9391` | 9391 |

Trong khởi chạy Spring Boot tiêu chuẩn, với profile `prod` đang hoạt động, không có nguồn ưu tiên cao hơn hay tùy biến cách nạp tham số, giá trị hiệu lực là **9391**. Xóa tham số dòng lệnh thì biến môi trường 9291 vẫn có thể thắng giá trị 9191 trong tệp profile.

Trong các nguồn thường gặp, tham số dòng lệnh có thể ghi đè `SPRING_APPLICATION_JSON`, Java system properties, biến môi trường và config data. Đây là lát cắt phục vụ chẩn đoán, không phải toàn bộ thứ tự cho mọi bài kiểm thử hay môi trường Servlet. Xem [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 5.2. Thực hành với một cấu hình chung và một profile

Giả sử ứng dụng web Actuator đã được đóng gói thành `actuator-lab.jar`. Hai tệp dưới được đặt trong tài nguyên của dự án trước khi đóng gói.

`application.yml`:

```yaml
spring:
  application:
    name: actuator-lab
  jmx:
    enabled: false

server:
  port: 8080

management:
  server:
    port: 9091
  endpoints:
    web:
      exposure:
        include: health,info
```

`application-prod.yml`:

```yaml
management:
  server:
    port: 9191
```

Ở một cửa sổ PowerShell riêng cho thí nghiệm, đặt biến môi trường rồi chạy:

```powershell
$env:MANAGEMENT_SERVER_PORT = '9291'
java -jar actuator-lab.jar --spring.profiles.active=prod --management.server.port=9391
```

Với điều kiện nêu ở mục 5.1, log phải phản ánh HTTP quản trị dùng cổng 9391. Trong cửa sổ khác, gọi:

```powershell
curl.exe -i http://127.0.0.1:9391/actuator/health
```

Dừng ứng dụng bằng Ctrl+C, bỏ tham số cổng rồi chạy lại:

```powershell
java -jar actuator-lab.jar --spring.profiles.active=prod
```

Lần này chờ cổng 9291. Để loại nguồn biến môi trường khỏi lần thử kế tiếp:

```powershell
Remove-Item Env:MANAGEMENT_SERVER_PORT
java -jar actuator-lab.jar --spring.profiles.active=prod
```

Khi không có nguồn khác ghi đè, cổng quản trị trở về 9191. Cửa sổ PowerShell dành riêng giúp thí nghiệm không làm thay đổi môi trường của phiên làm việc khác. Nếu các cổng dự kiến đang bị chiếm, giải quyết xung đột socket trước khi đánh giá kết quả.

Bài thực hành này thay đổi từng nguồn để chứng minh thứ tự; nó không yêu cầu mở thêm `env` hoặc `configprops` ra mạng.

### 5.3. Profile chọn cấu hình, không bảo đảm giá trị cuối cùng

Kiểm tra tên profile đang hoạt động qua log khởi động. Các tình huống dễ bỏ sót:

- Máy phát triển dùng `local`, hệ thống triển khai dùng `prod`, còn tác vụ kiểm thử kích hoạt profile khác.
- Tham số khởi động chọn lại profile so với giá trị trong tệp.
- Nhiều profile cùng hoạt động và có các khóa trùng nhau.
- Profile group hoặc include làm xuất hiện thêm cấu hình ngoài profile đang được nghĩ tới.

Đặt `spring.profiles.active` ở nguồn chung hoặc nguồn khởi động thích hợp; không đặt nó trong chính `application-prod.yml` để tự kích hoạt profile prod. Xem [Profiles của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html).

Nếu cần nhiều profile, ghi rõ thứ tự và phạm vi trách nhiệm của từng profile. Một profile về chức năng giám sát không nên âm thầm đổi cổng nghiệp vụ nếu hợp đồng triển khai không yêu cầu điều đó.

## 6. Các bẫy cấu hình khiến sửa mãi không có tác dụng

### 6.1. Nhầm tên thuộc tính hoặc tên biến môi trường

| Thuộc tính dạng chuẩn | Biến môi trường tương ứng |
| --- | --- |
| `server.port` | `SERVER_PORT` |
| `management.server.port` | `MANAGEMENT_SERVER_PORT` |
| `management.server.address` | `MANAGEMENT_SERVER_ADDRESS` |
| `management.endpoints.web.base-path` | `MANAGEMENT_ENDPOINTS_WEB_BASEPATH` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |
| `spring.jmx.enabled` | `SPRING_JMX_ENABLED` |
| `spring.jmx.unique-names` | `SPRING_JMX_UNIQUENAMES` |

Quy tắc chuyển từ tên chuẩn sang biến môi trường là thay dấu chấm bằng gạch dưới, bỏ dấu gạch nối và viết hoa. Với hệ thống quản lý triển khai, cần xem giá trị cuối cùng được đưa vào tiến trình, không chỉ biểu mẫu cấu hình trên giao diện.

Không nhầm khóa quản trị HTTP với JMX, và không lấy khóa của một phiên bản Spring Boot khác rồi giả định nó còn hiệu lực. Một khóa viết sai có thể chỉ trở thành thuộc tính không được thành phần nào sử dụng.

### 6.2. Đặt Java system property sai vị trí

Ví dụ dùng Java system property:

```shell
java -Dmanagement.server.port=9291 -jar actuator-lab.jar
```

Ví dụ dùng tham số của Spring Boot:

```shell
java -jar actuator-lab.jar --management.server.port=9391
```

`-D...` phải được Java launcher xử lý trước `-jar`. Đặt `-Dmanagement.server.port=9291` sau tên JAR không còn là cách truyền Java system property. Nếu có cả hai nguồn như ví dụ và cơ chế dòng lệnh tiêu chuẩn đang bật, tham số `--...` có ưu tiên cao hơn.

Trong container, kiểm tra cả lệnh khởi chạy cuối cùng và các biến như `JAVA_TOOL_OPTIONS` nếu hệ thống có sử dụng chúng; một cờ Java cũ có thể vẫn được chèn vào mà không xuất hiện trong YAML ứng dụng.

### 6.3. Nạp nhầm tệp ngoài JAR

Một thư mục cấu hình được gắn vào container có thể khác nội dung trong mã nguồn. Khi thay tệp, cần xác nhận đường dẫn bên trong container và phiên bản triển khai thực sự đang chạy.

Đọc kỹ `spring.config.location` vì nó thay các vị trí tìm cấu hình mặc định; `spring.config.additional-location` bổ sung vị trí. Nếu cần chứng minh tệp nào đã được nạp, có thể tạm tăng log của `org.springframework.boot.context.config` trong môi trường chẩn đoán được kiểm soát. Báo cáo auto-configuration với `--debug` giúp xem điều kiện cấu hình tự động nhưng không thay việc truy nguyên mọi giá trị thuộc tính.

### 6.4. Sai cấu trúc YAML và loại trừ endpoint

Hai khối `management:` cùng cấp trong cùng một tài liệu YAML không phải cách an toàn để ghép cấu hình. Giữ một cây thống nhất và kiểm tra thụt lề.

Nếu dùng ký tự đại diện, đặt trong dấu nháy:

```yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
```

Cấu hình này chủ động loại các endpoint khỏi HTTP; đổi cổng không đưa chúng trở lại. Nếu vừa include vừa exclude một endpoint, kiểm tra quy tắc exposure trước khi suy luận endpoint chưa được khởi tạo.

Phân biệt ba câu hỏi: endpoint có được bật không, có được phơi bày qua kênh đang dùng không, và máy khách có được phép truy cập không. Chỉ tăng `include` chưa đủ để trả lời hai câu còn lại.

## 7. Xác minh cấu hình mà không mở rộng bề mặt quản trị

Cần ít nhất hai loại bằng chứng:

1. **Giá trị cấu hình hiệu lực:** khóa cổng, địa chỉ, đường dẫn, profile, JMX.
2. **Hành vi đã xảy ra:** socket thực tế, URL trả lời, MBean đã đăng ký.

Nếu ứng dụng khởi động được, dùng debugger hoặc một đoạn chẩn đoán tạm chỉ đọc danh sách khóa đã chọn từ Spring `Environment`. Không in toàn bộ môi trường tiến trình vì có thể chứa thông tin bí mật.

Đoạn sau minh họa một Spring component, đặt trong package được ứng dụng quét. Nó cần dependency Spring Boot, không chạy độc lập bằng `javac` với chỉ JDK.

```java
package com.example.actuatorlab;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ManagementConfigProbe implements ApplicationRunner {
    private final Environment environment;

    public ManagementConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("activeProfiles="
                + Arrays.toString(environment.getActiveProfiles()));

        String[] keys = {
                "server.port",
                "management.server.port",
                "management.server.address",
                "management.server.base-path",
                "management.endpoints.web.base-path",
                "spring.jmx.enabled",
                "spring.jmx.unique-names",
                "management.endpoints.jmx.domain"
        };

        for (String key : keys) {
            System.out.println(key + "="
                    + environment.getProperty(key, "<not explicitly set>"));
        }
    }
}
```

Khi một khóa không được đặt trực tiếp trong Environment, giá trị thông báo trên không có nghĩa thành phần Spring Boot không có mặc định. Ví dụ base path HTTP vẫn có thể dùng mặc định của đối tượng cấu hình. Đoạn mã cũng không cho biết cổng đã được hệ điều hành cấp khi đặt 0.

Để biết **nguồn thắng**, xem property sources và thông tin origin bằng debugger, hoặc dùng `env`/`configprops` trong một kênh quản trị đã được bảo vệ và cho phép. Endpoint có thể che giá trị, bị loại khỏi exposure hoặc yêu cầu quyền; không coi việc thấy dấu che là bằng chứng rằng giá trị gốc bị mất. Không bật tất cả endpoint chỉ để tìm một khóa cổng.

Để biết **hành vi thật**, đọc log mở web server, xem socket trong đúng không gian mạng, gọi health từ vị trí của công cụ giám sát và đối chiếu MBean bằng công cụ JMX. Nếu ứng dụng dừng trước khi `ApplicationRunner` chạy, dùng log khởi động và cấu hình triển khai để điều tra; đoạn probe không thể báo cáo cho một ứng dụng chưa khởi động xong.

Gỡ đoạn chẩn đoán tạm hoặc đưa nó vào cơ chế được kiểm soát sau khi tìm được nguyên nhân.

## 8. Quy trình xử lý một sự cố từ đầu đến cuối

### Bước 1: Ghi nhận danh tính lần chạy

Ghi phiên bản ứng dụng, phiên bản Spring Boot, môi trường, profile, PID/container/pod và thời điểm lỗi. Phân biệt lỗi của bản đang triển khai với log của bản cũ.

### Bước 2: Chọn nhánh theo lỗi gốc

Nếu có `InstanceAlreadyExistsException`, lấy ObjectName và tìm hai chủ thể đăng ký. Nếu có lỗi bind, lấy địa chỉ/cổng và tiến trình chiếm chỗ. Nếu ứng dụng chạy nhưng máy giám sát thất bại, bắt đầu từ URL và kết quả kết nối.

### Bước 3: Đối chiếu cấu hình hiệu lực với dự kiến

Lập bảng ngắn cho các khóa liên quan:

| Khóa/tài nguyên | Dự kiến | Đang hiệu lực/quan sát | Nguồn hoặc bằng chứng |
| --- | --- | --- | --- |
| Profile | prod | prod | Log lần khởi động |
| Cổng quản trị | 9191 | 9291 | Biến môi trường và log listener |
| URL giám sát | Cổng 9291 | Máy giám sát vẫn gọi 9191 | Cấu hình probe |
| ObjectName | Một MBean cho mỗi đối tượng | Hai lần đăng ký cùng tên | Chuỗi nguyên nhân và cấu hình exporter |

Đây là ví dụ một tập quan sát để luyện cách ghi nhận; khi điều tra thật, thay bằng bằng chứng của hệ thống đang xét.

### Bước 4: Thay đổi nhỏ nhất có thể giải thích được

- Đăng ký trùng không chủ ý: bỏ cơ chế đăng ký dư hoặc sửa vòng đời.
- Hai context hợp lệ: đặt định danh/miền thích hợp, cân nhắc tên duy nhất và cách giám sát.
- Cổng bị nguồn ngoài ghi đè: sửa nguồn triển khai đang thắng, không lặp lại cùng một giá trị trong nhiều tệp.
- Máy giám sát gọi địa chỉ cũ: cập nhật probe/routing theo listener thực tế.
- Endpoint bị loại khỏi HTTP: sửa exposure của đúng endpoint nếu hợp đồng vận hành cần nó.

### Bước 5: Khởi động lại đúng đối tượng và kiểm tra hai phía

Xác nhận cấu hình mới đã vào tiến trình, ứng dụng khởi động thành công, MBean mong muốn có mặt và URL quản trị trả lời từ đúng vị trí mạng. Kiểm tra API nghiệp vụ để phát hiện thay đổi ngoài ý muốn, chẳng hạn vô tình đổi cổng chính.

Nếu đổi tên MBean, kiểm tra truy vấn giám sát còn chọn đúng MBean. Nếu đổi cổng, cập nhật cả kiểm tra sức khỏe, Service, proxy và tác vụ thu thập liên quan.

### Bước 6: Ghi nguyên nhân và gỡ biện pháp tạm

Một kết luận hữu ích là: “Biến môi trường cũ đặt cổng 9291, trong khi probe gọi 9191; đã sửa giá trị triển khai và xác minh probe tới đúng listener”. “Đã khởi động lại thì hết” chưa chỉ ra nguyên nhân hay cách phòng tránh.

Giữ lại nơi sở hữu cấu hình rõ ràng cho từng môi trường. Nếu dùng nhiều nguồn có chủ ý, ghi rõ nguồn nào có quyền ghi đè khóa nào.

## 9. Bài tập kiểm tra khả năng chẩn đoán

### Tình huống 1: Đổi cổng vẫn trùng MBean

Hai ApplicationContext dùng chung MBeanServer và cùng đăng ký endpoint. Người vận hành đổi cổng từ 8080 sang 8082 nhưng ngoại lệ vẫn còn.

**Giải thích:** địa chỉ HTTP đã thay, ObjectName trong cùng sổ đăng ký chưa thay. Cần xác định hai context có chủ ý hay do khởi tạo trùng. Với hai context hợp lệ, xử lý tên/domain và cách nhận diện; với khởi tạo dư, loại bỏ việc đăng ký dư.

### Tình huống 2: Local gọi được, hệ thống giám sát không gọi được

Ứng dụng trong container báo quản trị ở 9091, nhưng máy chủ chỉ ánh xạ 8080. Health được gọi thành công từ bên trong container.

**Giải thích:** chưa có bằng chứng đường đi từ máy giám sát tới 9091. Kiểm tra bind, port mapping hoặc Service/proxy. Không đổi JMX để sửa một đường HTTP bị thiếu.

### Tình huống 3: Đổi application-prod.yml không đổi cổng

Tệp profile đặt 9191, biến môi trường đặt 9291 và lệnh chạy có `--management.server.port=9391`.

**Giải thích:** trong khởi chạy tiêu chuẩn của ví dụ, 9391 thắng. Bỏ tham số chưa đủ để quay về 9191 vì vẫn còn biến môi trường. Phải xử lý đúng nguồn đang có ưu tiên.

### Tình huống 4: HTTP health tốt nhưng một MBean thư viện vẫn báo trùng

Ứng dụng đã đặt `management.endpoints.jmx.exposure.exclude="*"`, nhưng lỗi MBean của thư viện vẫn xuất hiện.

**Giải thích:** loại trừ endpoint Actuator qua JMX không điều khiển mọi cơ chế đăng ký JMX của thư viện. Lấy đúng ObjectName và thành phần đăng ký để xử lý; không suy ra Actuator chưa đọc cấu hình.

### Tình huống 5: Gọi đúng cổng nhưng nhận 401

Sau khi sửa port mapping, máy giám sát nhận 401 thay vì timeout.

**Giải thích:** đã có tiến triển ở lớp kết nối, nhưng cần xác minh phản hồi đến từ đúng ứng dụng/proxy rồi xử lý xác thực. Không tiếp tục đổi cổng chỉ vì health chưa trả 200.

Trước khi đóng một sự cố, hãy tự trả lời được: tên nào bị trùng, ai sở hữu đăng ký; listener nào đang chạy và ai kết nối tới nó; giá trị nào có hiệu lực và nguồn nào đã quyết định giá trị đó.
