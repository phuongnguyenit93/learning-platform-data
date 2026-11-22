# Đọc metrics Tomcat và điều kiện kích hoạt các chỉ số liên quan

Một ứng dụng Servlet có thể vẫn phục vụ HTTP bình thường nhưng chưa hiển thị các chỉ số thread và connector của Tomcat. Ngược lại, thấy một vài chỉ số session chưa chứng minh mọi nhóm Tomcat metrics đã được kích hoạt đầy đủ.

Muốn đọc đúng, cần biết Tomcat đang giữ những tài nguyên nào, phép đo lấy dữ liệu từ đâu và ứng dụng đã đáp ứng điều kiện nào. Bài này giải thích theo Spring Boot 3.3.0, Micrometer 1.13.0 và Tomcat nhúng 10.1.24, với ví dụ Java 17 chạy được trên JDK 21.

## 1. Tomcat metrics trả lời câu hỏi gì?

Trong ứng dụng Spring MVC dùng Tomcat nhúng, Tomcat tiếp nhận kết nối, phân phối yêu cầu tới servlet và quản lý các tài nguyên của container Servlet. Metrics giúp quan sát những tài nguyên đó, chẳng hạn số kết nối, worker đang bận và session đang tồn tại.

Phân biệt bốn khái niệm trước khi đọc số:

| Khái niệm | Vai trò | Vì sao không đếm thay cho nhau? |
| --- | --- | --- |
| Kết nối (connection) | Kênh giao tiếp giữa client và server | Một kết nối keep-alive có thể phục vụ nhiều yêu cầu; HTTP/2 còn có nhiều luồng yêu cầu trên cùng kết nối |
| Yêu cầu HTTP (request) | Một lần giao tiếp theo HTTP | Số yêu cầu không phải số kết nối hay số người dùng |
| Worker thread | Luồng thực thi công việc của bộ xử lý | Kết nối đang mở không có nghĩa luôn chiếm riêng một worker đang bận |
| HTTP session | Trạng thái phiên do ứng dụng/container quản lý | Một session có thể đi qua nhiều yêu cầu và kết nối; ứng dụng không dùng session vẫn có lưu lượng |

Vì vậy, `connections.current=100` không có nghĩa 100 yêu cầu đang xử lý, còn `sessions.active.current=10` không có nghĩa đúng 10 người đang sử dụng ứng dụng tại giây đó.

### Luồng dữ liệu quan sát

```text
Tomcat thực sự đang chạy
    -> trạng thái của Manager và các MBean liên quan
    -> bộ đăng ký phép đo Tomcat của Micrometer
    -> MeterRegistry
    -> endpoint kiểm tra Actuator hoặc nơi xuất dữ liệu
```

MBean là đối tượng quản lý trong hạ tầng JMX. Các MBean nội bộ có thể cung cấp thông tin về bộ kết nối (connector), nhóm luồng (thread pool) và bộ xử lý yêu cầu. Việc đăng ký chúng là một lớp khác với việc mở endpoint HTTP để đọc metrics.

## 2. Điều kiện cần xét theo từng lớp

| Lớp điều kiện | Điều cần xác nhận |
| --- | --- |
| Máy chủ và kiểu ứng dụng | Ứng dụng đang chạy với Tomcat, không chỉ có một tệp cấu hình mang chữ `tomcat` |
| Thư viện và tự cấu hình | Có Actuator/Micrometer, registry và phần tích hợp Tomcat phù hợp |
| Nguồn quản lý Tomcat | MBean registry được bật cho những nhóm cần đọc từ MBean |
| Vòng đời | Tomcat và các thành phần liên quan đã được khởi tạo |
| Bộ lọc meter | Không có cấu hình hoặc filter chặn các tên cần đọc |
| Cách truy cập | Muốn đọc qua HTTP thì endpoint `metrics` phải được cho phép cung cấp và truy cập |

Một cấu hình đúng ở lớp cuối không sửa được điều kiện thiếu ở lớp trước. Mở `/actuator/metrics` không tự tạo các MBean Tomcat; bật MBean registry cũng không tự mở endpoint HTTP.

### 2.1. Phải xác nhận server thực sự được dùng

Starter web tiêu chuẩn trong ví dụ sử dụng Tomcat nhúng. Nhưng một dự án có thể đã thay server, dùng kiểu ứng dụng khác hoặc triển khai theo cách có cấu hình container riêng.

Ứng dụng WebFlux dùng Reactor Netty không có các tài nguyên Tomcat giống mô hình Servlet ở đây. Đặt `server.tomcat.mbeanregistry.enabled=true` không biến Netty thành Tomcat.

Với ứng dụng triển khai lên Tomcat bên ngoài, quản lý MBean và vòng đời container còn do môi trường triển khai sở hữu. Không mặc định thuộc tính cho Tomcat nhúng sẽ cấu hình thay toàn bộ container bên ngoài.

### 2.2. Điều kiện MBean registry

Spring Boot 3.3 mô tả việc bật Tomcat instrumentation qua MBean registry. Thuộc tính cần chú ý là:

```yaml
server:
  tomcat:
    mbeanregistry:
      enabled: true
```

Giá trị mặc định của thuộc tính là `false`. [Tomcat metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [thuộc tính cấu hình](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

`spring.jmx.enabled` và `server.tomcat.mbeanregistry.enabled` có trách nhiệm khác nhau; không dùng một tên thuộc tính thay cho tên còn lại. Để Micrometer đọc MBean nội bộ theo tích hợp này, không cần mở cổng JMX Remote cho máy khác truy cập.

### 2.3. Điểm cần đối chiếu với phần hiện thực của phiên bản

Mô tả tài liệu về MBean registry không nên được biến thành kết luận rằng mọi tên `tomcat.*` đều phải biến mất khi tắt thuộc tính.

Thí nghiệm với Boot 3.3.0 và Micrometer 1.13.0 xác nhận:

- Khi bật MBean registry, có các nhóm thread, connection và global request từ connector.
- Khi tắt, các nhóm connector này không xuất hiện trong cấu hình thí nghiệm.
- Nhóm session vẫn xuất hiện và số session đã tạo vẫn tăng khi ứng dụng chủ động tạo session.

Lý do là binder của phiên bản này có thể đọc các chỉ số session trực tiếp từ `Manager`, trong khi các nhóm khác tìm dữ liệu qua MBean. Đây là phân biệt theo nguồn dữ liệu, không phải mâu thuẫn giữa việc Tomcat có chạy và HTTP có hoạt động hay không.

Khi kiểm tra một phiên bản khác hoặc một cách triển khai khác, xác minh từng nhóm thực sự có trong registry. Không dùng sự hiện diện của một tên session để chứng minh nhóm connector đã sẵn sàng.

## 3. Nhận diện các nhóm chỉ số

Các tên dưới đây đã xuất hiện trong thí nghiệm của bài. Danh sách thực tế còn phụ thuộc phiên bản, thành phần Tomcat và cấu hình đang dùng.

### 3.1. Thread và kết nối

| Meter | Cách đọc ở cấp khái niệm | Điều cần giữ khi diễn giải |
| --- | --- | --- |
| `tomcat.threads.current` | Số thread hiện có mà nguồn quản lý báo | Không phải số thread đang bận |
| `tomcat.threads.busy` | Số thread đang bận theo nguồn đo | Là trạng thái tại thời điểm đọc, có thể bỏ lỡ đợt bận ngắn |
| `tomcat.threads.config.max` | Giá trị max thread mà thuộc tính quản lý của connector cung cấp | Có thể có giá trị đánh dấu như `-1`; không mặc định luôn là một giới hạn dương dùng được |
| `tomcat.connections.current` | Số kết nối hiện tại | Kết nối không tương đương yêu cầu đang thực thi |
| `tomcat.connections.keepalive.current` | Số kết nối keep-alive theo nguồn quản lý | Kết nối có thể đang chờ lần dùng tiếp theo |
| `tomcat.connections.config.max` | Giới hạn kết nối mà nguồn quản lý cung cấp | Khác với giới hạn thread và số kết nối hiện tại |

Các meter connector thường có tag `name`. Giá trị tag phụ thuộc giao thức, địa chỉ, cổng và cách tạo connector, chẳng hạn các tên bắt đầu bằng `http-nio-...`. Không giả định luôn có một nhãn cố định `http-nio-8080`.

### 3.2. Số yêu cầu, lỗi và byte

| Meter | Loại số liệu trong ví dụ | Cách đọc |
| --- | --- | --- |
| `tomcat.global.request` | FunctionTimer | Số yêu cầu và tổng thời gian do bộ xử lý Tomcat cung cấp |
| `tomcat.global.request.max` | Gauge thời gian | Thời gian xử lý lớn nhất do thuộc tính Tomcat báo |
| `tomcat.global.error` | FunctionCounter | Lượng lỗi do nguồn thống kê Tomcat ghi nhận |
| `tomcat.global.received` | FunctionCounter, đơn vị byte | Lượng byte nhận mà nguồn Tomcat thống kê |
| `tomcat.global.sent` | FunctionCounter, đơn vị byte | Lượng byte gửi mà nguồn Tomcat thống kê |

FunctionCounter/FunctionTimer đọc một hàm hoặc bộ thống kê đã tồn tại, thay vì yêu cầu mã nghiệp vụ tự gọi `increment()` cho từng sự kiện. Khi truy vấn, vẫn cần đọc đúng `COUNT`, tổng thời gian, đơn vị và vòng đời của nguồn dữ liệu.

Không mặc định một lỗi nghiệp vụ trong nội dung phản hồi luôn tương ứng một lỗi container. Metrics Tomcat cũng không tự cho biết nguyên nhân nghiệp vụ của mọi lần thất bại.

`tomcat.global.request.max` là một tên riêng; không suy ra nó luôn nằm trong mảng thống kê của `tomcat.global.request`. Các tổng và max cũng không đủ để phục hồi p95 hoặc p99.

### 3.3. Session

| Meter | Ý nghĩa thường dùng |
| --- | --- |
| `tomcat.sessions.active.current` | Số session đang hoạt động theo Manager |
| `tomcat.sessions.active.max` | Mức cao nhất của số session hoạt động theo thống kê nguồn |
| `tomcat.sessions.created` | Tổng session đã được tạo theo nguồn đo |
| `tomcat.sessions.expired` | Tổng session hết hạn theo nguồn đo |
| `tomcat.sessions.rejected` | Tổng session bị từ chối theo nguồn đo |
| `tomcat.sessions.alive.max` | Thời gian sống lớn nhất của session theo thống kê nguồn |

Micrometer mô tả nhóm session và cách liên kết binder với Manager của Tomcat. [Tomcat instrumentation của Micrometer](https://docs.micrometer.io/micrometer/reference/reference/tomcat.html).

Một ứng dụng không gọi tạo session có thể có các giá trị session bằng 0 dù phục vụ nhiều yêu cầu. Session cũng không phải số lần đăng nhập, số tài khoản hay số người dùng trực tuyến.

### 3.4. Servlet và cache

Trong cấu hình thí nghiệm còn có `tomcat.servlet.request`, `tomcat.servlet.request.max`, `tomcat.servlet.error`, cùng các chỉ số `tomcat.cache.access` và `tomcat.cache.hit`.

Nhóm servlet có thể được lọc theo tên servlet như `dispatcherServlet`. Cache ở đây thuộc tài nguyên của container được binder theo dõi, không mặc nhiên là cache nghiệp vụ dùng Spring Cache. Hãy xác nhận nguồn của meter trước khi dùng nó để kết luận về một hệ thống cache khác.

## 4. Đọc tag và thống kê trước khi tính tỷ lệ

### 4.1. Tìm tên rồi lọc đúng connector

Trong ứng dụng web đã mở endpoint:

```http
GET /actuator/metrics
GET /actuator/metrics/tomcat.threads.busy
GET /actuator/metrics/tomcat.global.request
```

Đọc `availableTags` để lấy giá trị `name` thực tế. Sau đó lọc bằng chính giá trị đó.

Ví dụ PowerShell, thay giá trị biến bằng nhãn thực tế vừa đọc:

```powershell
$connectorName = 'http-nio-127.0.0.1-8080'
curl.exe --get 'http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy' --data-urlencode "tag=name:$connectorName"
```

Nhãn trong lệnh là ví dụ, không phải bảo đảm cho mọi lần chạy. Connector dùng cổng tự chọn hoặc địa chỉ khác có thể có tên khác.

Đặt cùng điều kiện lọc khi so sánh busy, current và max. Nếu có nhiều connector hoặc một executor chia sẻ, gộp các gauge mà chưa xác định phạm vi có thể dẫn tới đếm lặp hoặc một tổng không đúng ý nghĩa.

### 4.2. Không chia cho một max không hợp lệ

Với cùng một pool có giới hạn dương và các phép đo tương thích, có thể xét tỷ lệ như:

```text
busy ratio = busy / max
```

Nhưng phải xác nhận mẫu số thật sự là giới hạn có nghĩa của pool đang xét.

Tomcat nêu rõ: khi connector được gắn một bộ thực thi (executor) riêng, thuộc tính `maxThreads` của connector không còn điều khiển pool nội bộ; qua JMX nó có thể được báo là `-1` để thể hiện không được dùng. [Thuộc tính HTTP Connector của Tomcat](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html).

Trong thí nghiệm của bài, connector dùng `StandardThreadExecutor` và meter `tomcat.threads.config.max` nhận giá trị `-1`. Không đổi nó thành 1, không lấy busy chia cho -1 và không kết luận pool có công suất âm. Cần xem executor thực sự đang thực thi công việc và các phép đo phù hợp với executor đó.

Chế độ luồng ảo (virtual thread) cũng làm việc diễn giải theo mô hình nhóm luồng nền tảng (platform thread) cần được xét lại. Đừng dùng một công thức busy/max chỉ vì hai tên metric tồn tại. Ví dụ dưới đây tắt luồng ảo để giữ phạm vi thí nghiệm rõ ràng, nhưng điều đó không tự bảo đảm thuộc tính max của connector phải là số dương.

### 4.3. Mẫu tại một thời điểm không chứng minh trạng thái của cả khoảng

`busy=0` ở một lần đọc không chứng minh không có yêu cầu trong phút vừa qua. Các yêu cầu ngắn có thể đã hoàn tất giữa hai mẫu.

Ngược lại, một lần đọc busy cao chưa tự chứng minh nguyên nhân nghẽn là thiếu thread; thread có thể đang chờ cơ sở dữ liệu, dịch vụ bên ngoài hoặc công việc khác. Cần đối chiếu thời gian xử lý, lỗi, tài nguyên và các nguồn quan sát phù hợp.

## 5. Ví dụ ứng dụng nhúng để kiểm chứng

Ứng dụng có một endpoint thử nghiệm `/probe`. Bình thường nó chỉ trả `ok`; thêm `session=true` thì nó chủ động tạo hoặc lấy HTTP session.

Endpoint này giúp kiểm chứng nguồn số liệu của Tomcat bằng yêu cầu thật. Ứng dụng không tự tạo các meter có tên `tomcat.*`; việc đo đến từ tích hợp có sẵn.

### 5.1. Cấu trúc

```text
tomcat-metrics-demo/
├── pom.xml
└── src/main/
    ├── java/example/tomcatmetrics/TomcatMetricsApplication.java
    └── resources/application.yml
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>tomcat-metrics-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Phiên bản được cố định để tái lập hành vi của ví dụ. Starter web tiêu chuẩn đưa Tomcat nhúng vào dự án; starter Actuator cung cấp phần tích hợp metrics. Không tự trộn các phiên bản Spring và Tomcat khác với tập phụ thuộc nếu mục tiêu là tái lập thí nghiệm này.

### 5.2. Cấu hình

`src/main/resources/application.yml`:

```yaml
spring:
  threads:
    virtual:
      enabled: false

server:
  address: 127.0.0.1
  port: 8080
  tomcat:
    mbeanregistry:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Ứng dụng mẫu lắng nghe trên loopback. Cấu hình mở endpoint `metrics` để quan sát trong thí nghiệm; việc cung cấp endpoint và quyền truy cập trong ứng dụng thật cần theo cấu hình của ứng dụng đó.

Không cần thêm `spring.jmx.enabled=true` chỉ để thay cho cờ MBean registry của Tomcat. Hai cấu hình không đồng nghĩa.

### 5.3. Mã Java

`src/main/java/example/tomcatmetrics/TomcatMetricsApplication.java`:

```java
package example.tomcatmetrics;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication(proxyBeanMethods = false)
@RestController
public class TomcatMetricsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TomcatMetricsApplication.class, args);
    }

    @GetMapping("/probe")
    public String probe(HttpServletRequest request,
                        @RequestParam(name = "session",
                                defaultValue = "false") boolean session) {
        if (session) {
            request.getSession(true);
        }
        return "ok";
    }
}
```

Tham số `session` chỉ phục vụ thí nghiệm. Khi bằng `false`, mã không chủ động tạo session. Khi bằng `true`, `request.getSession(true)` tạo session nếu yêu cầu chưa có một session hợp lệ.

### 5.4. Biên dịch và chạy

Cần Maven và JDK 17 trở lên; mã có thể chạy với JDK 21.

```shell
mvn -q package
java -jar target/tomcat-metrics-demo-1.0.0.jar
```

Lần đầu Maven cần tải plugin và phụ thuộc nếu máy chưa có. Ứng dụng tiếp tục chạy để nhận yêu cầu; mở một terminal khác để thực hiện các lệnh đọc. Dừng tiến trình bằng `Ctrl+C` khi kết thúc thí nghiệm.

Log khởi động chứa thời gian, thông tin môi trường và giá trị có thể khác nhau giữa các máy. Không có một bộ số thread, kết nối hoặc thời gian xử lý cố định đúng cho mọi lần chạy.

Gửi yêu cầu:

```shell
curl "http://127.0.0.1:8080/probe"
```

Nội dung phản hồi chính xác của endpoint mẫu:

```text
ok
```

Trong PowerShell, nếu `curl` là alias của một lệnh khác, gọi `curl.exe`.

## 6. Thí nghiệm đọc và so sánh

### 6.1. Kiểm tra tên trước khi tạo session

Sau khi ứng dụng khởi động, đọc:

```shell
curl "http://127.0.0.1:8080/actuator/metrics"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.sessions.created"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.threads.busy"
```

Đọc tên, đơn vị, thống kê và tag. Session có thể vẫn bằng 0; không sửa endpoint để giả tạo hoạt động chỉ vì đang thấy một giá trị 0.

Các yêu cầu tới Actuator cũng đi qua server. Do đó, việc quan sát bằng HTTP có thể tự tạo thêm hoạt động mà các bộ đếm request hoặc byte của connector nhìn thấy.

### 6.2. Chủ động tạo một session

Ghi lại số session đã tạo, rồi gọi:

```shell
curl "http://127.0.0.1:8080/probe?session=true"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.sessions.created"
```

Với lần gọi mới chưa có cookie session hợp lệ, số session đã tạo phải tăng theo hoạt động vừa thực hiện. Không áp đặt một giá trị tuyệt đối như luôn bằng 1 nếu ứng dụng đã nhận yêu cầu khác trước đó.

Nếu gửi lại cookie của một session hợp lệ, một lần gọi `getSession(true)` có thể lấy session cũ thay vì tạo mới. Khi dùng curl không giữ cookie, nhiều lần gọi có thể tạo nhiều session. Đó không phải bằng chứng có từng ấy người dùng.

### 6.3. Đọc request và đơn vị thời gian

Truy vấn:

```shell
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.global.request"
curl "http://127.0.0.1:8080/actuator/metrics/tomcat.global.request.max"
```

Ở nhóm request, kiểm tra `COUNT`, tổng thời gian và đơn vị được phản hồi. `COUNT` là lượng yêu cầu mà nguồn Tomcat thống kê, không tự là số yêu cầu/giây.

Nếu cần thời gian trung bình, chỉ chia tổng thời gian cho count khi cùng phạm vi và count dương. Không chia nhầm tổng của nhiều connector cho count của một connector.

Ở meter max riêng, không suy từ một max ra toàn bộ phân bố hoặc độ trễ mà người dùng đầu cuối cảm nhận. Phạm vi đo của container có thể khác phạm vi ở proxy, client hoặc các phép đo trong ứng dụng.

### 6.4. Tắt MBean registry rồi khởi động lại

Dừng tiến trình cũ, chạy lại:

```shell
java -jar target/tomcat-metrics-demo-1.0.0.jar --server.tomcat.mbeanregistry.enabled=false
```

Trong thí nghiệm Boot 3.3.0, thread và global request metrics từ connector không còn có trong registry, nhưng session metrics vẫn được đăng ký và vẫn phản ánh thao tác tạo session.

HTTP vẫn phục vụ `/probe`. Thiếu một nhóm meter không có nghĩa Tomcat đã dừng; ngược lại, HTTP hoạt động không chứng minh nguồn MBean của mọi nhóm đã sẵn sàng.

### 6.5. Phân biệt không mở endpoint và không có meter

Với MBean registry bật, thử chỉ mở health khi khởi động:

```shell
java -jar target/tomcat-metrics-demo-1.0.0.jar --management.endpoints.web.exposure.include=health
```

Trong cấu hình này, `/actuator/metrics` không được cung cấp qua HTTP dù meter có thể đã có bên trong registry. Đây là thay đổi của cách truy cập, không phải bằng chứng tích hợp Tomcat đã mất dữ liệu.

Muốn làm phép kiểm tra riêng đối với filter, trong một lần chạy khác có thể đặt:

```shell
java -jar target/tomcat-metrics-demo-1.0.0.jar --management.metrics.enable.tomcat=false
```

Filter theo tiền tố này chặn các meter Tomcat trong phạm vi cấu hình của thí nghiệm, trong khi server vẫn có thể xử lý HTTP và các nhóm không bị chặn vẫn hoạt động. Không nhầm nó với cờ bật MBean registry.

## 7. Đối chiếu với http.server.requests

`http.server.requests` và `tomcat.*` là hai lớp quan sát khác nhau.

| Nhóm | Phạm vi chính | Câu hỏi phù hợp |
| --- | --- | --- |
| `http.server.requests` | Phép quan sát HTTP của Spring ở các thành phần được tích hợp | Yêu cầu theo URI, method, status đang có đặc điểm gì? |
| `tomcat.threads.*`, `tomcat.connections.*` | Tài nguyên connector/pool của Tomcat | Tài nguyên server đang ở trạng thái nào? |
| `tomcat.global.*` | Thống kê của bộ xử lý yêu cầu Tomcat | Nguồn container đã ghi nhận lượng và thời gian ra sao? |
| `tomcat.sessions.*` | Session của Manager mà binder theo dõi | Session được tạo, giữ hoặc hết hạn thế nào? |

Sau yêu cầu `/probe`, ứng dụng mẫu có thể ghi `http.server.requests` cho route này ngay cả khi cờ MBean registry Tomcat đang tắt. Thí nghiệm của bài đã kiểm tra điều đó.

Không cần bật MBean Tomcat để biến `http.server.requests` thành một meter hợp lệ, và sự có mặt của HTTP meter cũng không thay thế chỉ số pool hay connector.

Hai count không bắt buộc bằng nhau trong mọi lần đọc: phạm vi, thời điểm hoàn tất phép đo, yêu cầu Actuator và các điều kiện lọc có thể khác nhau. Trước khi so sánh, xác định cùng route hay toàn connector, cùng khoảng thời gian và cùng instance.

## 8. Các giới hạn khi diễn giải

### 8.1. Số âm và giá trị không hữu hạn

Giá trị đánh dấu như `-1` hoặc giá trị không hữu hạn từ một nguồn quản lý không nên bị ép thành 0 hoặc đưa thẳng vào công thức phần trăm. Đọc tài liệu của thuộc tính nguồn và kiểm tra executor, giao thức cùng phiên bản đang dùng.

Không thay việc tìm nguyên nhân bằng cách tăng max thread trong cấu hình. Trước hết phải biết thuộc tính nào đang có hiệu lực với bộ thực thi thực tế.

### 8.2. Session bằng 0 trong ứng dụng không trạng thái

Ứng dụng không dùng HTTP session có thể liên tục phục vụ lưu lượng mà các chỉ số tạo và hoạt động session vẫn bằng 0. Đó có thể là hành vi đúng của thiết kế.

Một session hoạt động cũng không bảo đảm người dùng đang gửi yêu cầu tại thời điểm lấy mẫu; nó có thể còn tồn tại trong thời gian chờ hết hạn.

### 8.3. Phạm vi instance và vòng đời

Số liệu Tomcat thường thuộc container và instance đang cung cấp dữ liệu. Khởi động lại hoặc tạo lại thành phần có thể làm các thống kê nguồn bắt đầu vòng đời mới.

Truy cập qua bộ cân bằng tải có thể đưa các lần đọc tới các instance khác nhau. Đừng coi một thay đổi giữa hai phản hồi là reset hoặc lỗi của cùng một bộ đếm nếu chưa xác nhận nguồn.

### 8.4. Không mặc định mọi thành phần tồn tại

Một servlet, cache tài nguyên hoặc connector chưa tồn tại hay không dùng trong cấu hình có thể không cung cấp cùng bộ tên như một môi trường khác. Một số meter cũng chỉ có ý nghĩa sau hoạt động liên quan.

Nhóm tên và tag cần được khám phá trên môi trường chạy thực tế. Không tạo thủ công meter giả mang tên `tomcat.*` để làm danh sách giống một ảnh chụp tài liệu.

## 9. Quy trình chẩn đoán khi thiếu chỉ số

Kiểm tra theo thứ tự:

1. Xác nhận ứng dụng đang dùng Tomcat nhúng hay một máy chủ/cách triển khai khác.
2. Xác nhận có registry và phần tự cấu hình Actuator/Micrometer tương ứng; kiểm tra điều kiện tự cấu hình nếu đã bị thay hoặc loại bỏ.
3. Kiểm tra giá trị hiệu lực của `server.tomcat.mbeanregistry.enabled`, kể cả profile và đối số khởi động.
4. Chờ ứng dụng khởi động hoàn tất và xác định nhóm đang cần: session, thread, connector, servlet hay HTTP observation.
5. Kiểm tra `management.metrics.enable.*` và các filter tùy chỉnh có chặn meter không.
6. Nếu đọc qua HTTP, phân biệt endpoint chưa mở, không có quyền, sai cổng/base path với việc không có meter trong registry.
7. Từ danh sách tên hiện có, đọc tag và đơn vị thực tế rồi mới lọc hoặc tính toán.

| Hiện tượng | Cách hiểu cần kiểm tra |
| --- | --- |
| Có `tomcat.sessions.*` nhưng thiếu thread/global request | Session có thể được đọc trực tiếp trong khi nguồn MBean của connector chưa được bật |
| Có `http.server.requests` nhưng không có thread Tomcat | Hai nhóm có đường tích hợp khác nhau |
| `/actuator/metrics` không truy cập được | Có thể là cấu hình exposure hoặc quyền, chưa đủ để kết luận meter không tồn tại |
| Max thread bằng `-1` | Có thể là thuộc tính connector không được dùng vì executor riêng |
| Busy bằng 0 sau một loạt yêu cầu ngắn | Có thể các yêu cầu đã hoàn tất trước lúc lấy mẫu |
| Session vẫn bằng 0 | Ứng dụng có thực sự tạo session không? |
| Count Tomcat tăng khi chỉ đọc Actuator | Yêu cầu quản lý cũng có thể đi qua connector đang đo |
| Số không giống môi trường khác | Kiểm tra phiên bản, loại server, executor, connector, tag và vòng đời |

Việc kiểm tra JMX Remote là một hướng khác với nguồn MBean nội bộ dùng cho metrics. Không mở thêm một cổng quản lý từ xa chỉ để thử sửa một điều kiện đăng ký meter chưa được xác minh.

## 10. Thực hành

Thực hiện từng thay đổi trong một lần chạy rõ ràng, giữ kết quả trước–sau:

1. Chạy ví dụ với MBean registry bật, đọc danh sách các tên `tomcat.*` và nhóm theo session, connector, servlet.
2. Gọi `/probe` nhiều lần mà không tạo session. So sánh request metrics với session metrics và giải thích vì sao chúng không cùng tăng theo một quy tắc.
3. Gọi `/probe?session=true` với một yêu cầu chưa có cookie session hợp lệ. Kiểm tra số tạo session tăng, rồi giải thích vì sao số đó không phải số người dùng.
4. Tắt MBean registry, khởi động lại và đối chiếu các nhóm tên. Không áp đặt rằng mọi tên `tomcat.*` đều phải biến mất.
5. Bật lại MBean registry nhưng chỉ expose health. Phân biệt dữ liệu trong registry với khả năng truy cập endpoint metrics qua HTTP.
6. Với một connector cụ thể, đọc busy, current và config max. Chỉ tính tỷ lệ khi các mẫu tương thích và max dương, có ý nghĩa; nếu gặp `-1`, xác định cơ chế executor trước.
7. So sánh `tomcat.global.request` với `http.server.requests` đã lọc URI `/probe`. Ghi rõ khác nhau về phạm vi trước khi nhận xét hai số có khớp không.

Khi trình bày kết quả, nêu tên meter, tag connector hoặc servlet, loại thống kê, đơn vị và điều kiện MBean registry. Một số đo Tomcat chỉ có ý nghĩa khi gắn với đúng nguồn và cấu hình của máy chủ đang chạy.
