# Actuator là gì và giải quyết bài toán vận hành ứng dụng như thế nào

## 1. Từ “chạy được” đến “vận hành được”

Bạn viết một dịch vụ đặt hàng, chạy ứng dụng thành công và gọi thử API tạo đơn. Kết quả đúng trong lần thử đó là bằng chứng tốt cho chức năng vừa viết. Sau khi triển khai, người vận hành còn phải trả lời những câu hỏi khác:

- Tiến trình vẫn tồn tại, nhưng ứng dụng có đang trả lời yêu cầu không?
- Khi người dùng báo chậm, độ trễ tăng ở mọi yêu cầu hay chỉ một nhóm?
- Bộ nhớ đang tăng, hay lượng yêu cầu đang tăng?
- Bản triển khai đang chạy có đúng bản mà đội phát triển vừa phát hành không?
- Thành phần nào đang báo tình trạng bất thường?
- Cần xem thêm nhật ký nào để tìm nguyên nhân?

Một thông báo khởi động thành công không trả lời được toàn bộ những câu hỏi đó. Chúng cũng khó được giải quyết bằng cách liên tục thêm các API tự viết như `/check-server`, `/memory` hoặc `/debug-config` vào từng dự án. Mỗi nhóm có thể đặt tên khác nhau, trả dữ liệu khác nhau và vô tình để lộ thông tin nội bộ.

**Spring Boot Actuator bổ sung các khả năng phục vụ quan sát và quản trị ứng dụng đang chạy.** Nó cung cấp những điểm truy cập quản trị và tích hợp với cơ chế tự cấu hình của Spring Boot. Người vận hành và công cụ giám sát có một cách nhất quán hơn để lấy thông tin vận hành. Cách thêm tính năng được Spring Boot khuyến nghị là dùng `spring-boot-starter-actuator`. [Tài liệu kích hoạt Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

Có thể hình dung một dịch vụ như một chiếc xe: chức năng đặt hàng là khả năng di chuyển và chuyên chở; dữ liệu vận hành giống đồng hồ tốc độ, mức nhiên liệu và đèn cảnh báo. Đồng hồ giúp người lái nhận biết tình trạng xe. Việc sửa chữa và quyết định tiếp tục hành trình vẫn cần con người hoặc cơ chế điều khiển phù hợp.

Bài này dùng Spring Boot **3.3.13** và Java **21** để cố định ví dụ. Các giá trị mặc định được trình bày trong phạm vi dòng 3.3; khi dùng phiên bản khác, cần đối chiếu tài liệu tương ứng.

## 2. Những thuật ngữ cần nắm trước

### Điểm truy cập quản trị — endpoint

Một endpoint của Actuator là một khả năng quản trị có định danh, chẳng hạn `health` hoặc `metrics`. Với ứng dụng web trong cấu hình thông thường, chúng được truy cập qua các đường dẫn như `/actuator/health`.

Cần phân biệt **định danh endpoint** với **địa chỉ HTTP**. `health` là định danh; `/actuator/health` là đường dẫn trong một cách công bố cụ thể. Tiền tố và cổng quản trị có thể được cấu hình. HTTP cũng không phải cách tiếp cận duy nhất: Actuator hỗ trợ công bố endpoint qua JMX, cơ chế quản lý ứng dụng Java. [Tài liệu đường dẫn và cổng quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### Tình trạng ứng dụng — health

Health là kết quả đánh giá dựa trên các phép kiểm tra đã tham gia vào hệ thống. Một `HealthIndicator` đóng góp kết quả của một phép kiểm tra; `HealthEndpoint` tập hợp thông tin để công bố cho bên đọc.

Ví dụ về mặt ý tưởng: một phép kiểm tra trả lời “tài nguyên mà tôi phụ trách có dùng được không?”, rồi kết quả đó được đưa vào bức tranh chung. Chỉ những gì thực sự được kiểm tra mới có thể đóng góp bằng chứng. Actuator không tự biết mọi quy tắc đặt hàng hoặc mọi dịch vụ bên ngoài mà hệ thống sử dụng. [Hợp đồng HealthIndicator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthIndicator.html), [HealthEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

### Số đo vận hành — metrics

Metrics biểu diễn hoạt động bằng số: lượng yêu cầu, thời gian xử lý, mức sử dụng bộ nhớ hoặc những đại lượng khác đã được ghi nhận. Một lần đọc giúp biết giá trị hiện tại; nhiều lần đọc theo thời gian mới giúp thấy xu hướng.

Micrometer là lớp thư viện đo lường mà Spring Boot tích hợp. `MeterRegistry` quản lý các đối tượng đo. Nhãn (tag) giúp phân biệt các nhóm số liệu, chẳng hạn theo phương thức HTTP hoặc đường dẫn. Một hệ thống bên ngoài có thể thu thập và lưu các số liệu này để phân tích lâu dài.

### Khả năng quan sát — observability

Khả năng quan sát là khả năng suy luận về trạng thái bên trong từ những tín hiệu thu được. Ba nhóm tín hiệu thường được dùng cùng nhau là:

| Tín hiệu | Câu hỏi phù hợp | Ví dụ |
| --- | --- | --- |
| Số đo (metrics) | Có vấn đề ở quy mô nào, xuất hiện lúc nào? | Tỷ lệ lỗi tăng trong khoảng 5 phút |
| Nhật ký (logs) | Sự kiện nào đã xảy ra và có thông tin gì? | Một lần gọi nhà cung cấp thanh toán bị từ chối |
| Dấu vết phân tán (traces) | Một yêu cầu đã đi qua đâu và mất thời gian ở đâu? | Yêu cầu đi qua dịch vụ đơn hàng rồi tới dịch vụ thanh toán |

Bảng mô tả cách dùng tín hiệu để suy luận, không khẳng định mọi ứng dụng đã có sẵn cả ba. Spring Boot dùng Micrometer Observation cho phần đo lường và dấu vết; muốn gửi dấu vết ra hệ thống lưu trữ còn cần thành phần tích hợp thích hợp. [Tài liệu Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html), [tài liệu Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

## 3. Actuator nằm ở đâu trong hệ thống?

Hãy tách hai luồng suy nghĩ:

~~~text
Người dùng
    -> API nghiệp vụ
    -> xử lý nghiệp vụ
    -> kết quả nghiệp vụ

Người vận hành / công cụ
    -> thông tin quản trị và tín hiệu vận hành
    -> đánh giá tình trạng
    -> cảnh báo hoặc hành động theo quy trình
~~~

API nghiệp vụ trả lời “người dùng muốn làm gì?”. Giao diện quản trị trả lời “hệ thống đang hoạt động ra sao và có thể quản lý những gì?”.

Chẳng hạn:

- `POST /orders` tạo đơn hàng theo quyền của khách hàng.
- `GET /actuator/health` trả thông tin tình trạng theo những phép kiểm tra được cấu hình.
- `GET /actuator/metrics` cho phép xem tên các số đo đang có khi endpoint đó được công bố.

Việc tách hai luồng giúp thiết kế quyền truy cập và đối tượng sử dụng rõ ràng. Một người được phép mua hàng chưa chắc được phép xem thông tin cấu hình bên trong ứng dụng.

Một cách triển khai giám sát thường gặp là:

~~~text
Ứng dụng ghi nhận số liệu
    -> registry / bộ xuất số liệu phù hợp
    -> hệ thống thu thập và lưu trữ
    -> truy vấn / biểu đồ / quy tắc cảnh báo
    -> người trực vận hành
~~~

Ở đây, Actuator và Micrometer thuộc phía cung cấp, ghi nhận và tích hợp tín hiệu. Kho dữ liệu lịch sử, màn hình theo dõi và chính sách cảnh báo là các phần cần được thiết kế thêm.

Ví dụ, khi chọn Prometheus, cần registry phù hợp và cấu hình cho hệ thống thu thập tới đọc. Khi chọn Grafana để hiển thị, cần nguồn dữ liệu và biểu đồ. Chỉ thêm starter vào ứng dụng chưa tạo ra toàn bộ chuỗi đó. [Tài liệu tích hợp metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 4. Từ một sự cố đến bằng chứng cần thu thập

Giả sử người dùng báo “tạo đơn rất chậm”. Nếu chỉ biết tiến trình Java còn tồn tại, đội vận hành chưa có đủ dữ liệu để chọn hành động.

Có thể bắt đầu bằng ba lớp câu hỏi:

1. **Tiếp cận được không?** Kiểm tra đường truy cập, mã HTTP và khả năng nhận phản hồi.
2. **Ảnh hưởng rộng tới đâu?** Xem số lượng yêu cầu, tỷ lệ lỗi và thời gian xử lý theo nhóm.
3. **Vì sao xảy ra?** Đối chiếu nhật ký, dấu vết hoặc dữ liệu chẩn đoán có liên quan.

Đây là một quy trình suy luận minh họa, không phải thuật toán mà Actuator tự thực hiện.

| Quan sát | Kết luận có cơ sở | Bước điều tra tiếp theo |
| --- | --- | --- |
| Không kết nối được tới địa chỉ quản trị | Từ vị trí kiểm tra hiện tại chưa lấy được phản hồi | Kiểm tra địa chỉ, mạng, cổng và tiến trình |
| Health trả `UP` nhưng người dùng vẫn thấy chậm | Các phép kiểm tra hiện có chưa chỉ ra tình trạng xấu | Kiểm tra độ trễ và lỗi của luồng người dùng |
| Bộ nhớ tăng cùng lượng yêu cầu | Hai biến đang tăng trong cùng khoảng quan sát | So sánh thêm theo thời gian, tải và mức thu hồi bộ nhớ |
| Chỉ một nhóm API tăng lỗi | Ảnh hưởng có vẻ tập trung ở nhóm đó | Xem nhật ký và thành phần mà nhóm API sử dụng |

Không nên biến một tương quan thành nguyên nhân. Bộ nhớ tăng chưa đủ chứng minh rò rỉ bộ nhớ. Một endpoint trả được `200` cũng chưa đủ chứng minh khách hàng hoàn tất được giao dịch.

Giá trị thực tế của Actuator là giúp thu thập bằng chứng theo cách có hệ thống. Chất lượng kết luận vẫn phụ thuộc vào việc đặt đúng câu hỏi và hiểu phạm vi của tín hiệu.

## 5. Những khả năng nên nhận diện ở mức tổng quan

Một vài định danh thường gặp:

| Endpoint | Vai trò chính |
| --- | --- |
| `health` | Thông tin tình trạng |
| `info` | Thông tin ứng dụng do các nguồn đóng góp cung cấp |
| `metrics` | Tra cứu số đo phục vụ chẩn đoán |
| `loggers` | Xem hoặc thay đổi mức ghi nhật ký |
| `conditions` | Xem kết quả đánh giá điều kiện tự cấu hình |
| `threaddump` | Lấy thông tin luồng phục vụ điều tra |

Không phải endpoint nào cũng có dữ liệu hữu ích ngay khi ứng dụng khởi động. Khả năng cụ thể còn phụ thuộc thư viện, cấu hình và thành phần được tạo. [Danh mục endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Ở bài nhập môn, mục tiêu là chọn được loại thông tin phù hợp với câu hỏi vận hành. Việc thuộc toàn bộ endpoint hoặc mở tất cả chúng sẽ không giúp bạn hiểu vấn đề nhanh hơn.

Đặc biệt, cần nhận diện rằng một số thao tác quản trị **có thể thay đổi trạng thái**. Một yêu cầu đọc tình trạng và một yêu cầu thay đổi mức ghi nhật ký có hậu quả khác nhau. Quy trình phân quyền cần phản ánh sự khác biệt đó.

## 6. Muốn truy cập được cần qua những lớp nào?

Với cách cấu hình của Spring Boot 3.3, hãy kiểm tra riêng từng lớp:

1. **Thành phần cần thiết có tồn tại không?** Ví dụ, phải có thư viện và điều kiện tự cấu hình phù hợp.
2. **Endpoint có được bật không?** Thuộc tính dạng `management.endpoint.<id>.enabled` điều khiển việc bật endpoint.
3. **Endpoint có được công bố qua HTTP không?** `management.endpoints.web.exposure.include` chọn các định danh được công bố qua web.
4. **Yêu cầu có được phép đi qua không?** Mạng, cơ chế xác thực và phân quyền vẫn có thể chặn truy cập.

Trong dòng 3.3, mặc định chỉ `health` được công bố qua HTTP. Cấu hình `include` không tự cấp quyền bảo mật cho người gọi. [Quy tắc bật và công bố endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

Ví dụ ở phần sau dùng danh sách cụ thể:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Danh sách này nói rằng bài thực hành cần công bố ba endpoint đó. Nó giúp người đọc thấy rõ phạm vi đang mở mà không phải suy đoán ý nghĩa của ký tự đại diện.

Đường dẫn không truy cập được cũng cần được đọc trong ngữ cảnh:

- `404`: kiểm tra địa chỉ, tiền tố và việc công bố endpoint.
- `401` hoặc `403`: kiểm tra cơ chế bảo mật và quyền của yêu cầu.
- Lỗi kết nối hoặc hết thời gian chờ: trước hết kiểm tra khả năng đi tới địa chỉ đích.

Đây là hướng điều tra, không phải phép suy ngược tuyệt đối: proxy và quy tắc bảo mật tùy chỉnh có thể thay đổi phản hồi.

## 7. Thực hành: ứng dụng tối thiểu có API nghiệp vụ và Actuator

Ví dụ là **một dự án độc lập**. Bạn cần JDK 21, Maven và kết nối tới kho thư viện trong lần tải đầu. Không cần cơ sở dữ liệu, Docker hoặc hệ thống giám sát bên ngoài.

Dùng cấu trúc sau:

~~~text
actuator-intro/
├── pom.xml
└── src/main/
    ├── java/example/actuator/ActuatorIntroApplication.java
    └── resources/application.yml
~~~

### 7.1. Khai báo thư viện

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>actuator-intro</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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
~~~

Starter web cung cấp nền tảng cho ví dụ HTTP; starter Actuator bổ sung các khả năng quản trị. Parent quản lý phiên bản của những thư viện liên quan, nên không cần tự gán phiên bản riêng cho từng starter.

### 7.2. Viết một API đơn giản

Tệp `src/main/java/example/actuator/ActuatorIntroApplication.java`:

~~~java
package example.actuator;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ActuatorIntroApplication {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorIntroApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Xin chao Actuator";
    }
}
~~~

`/hello` đại diện cho API phục vụ người dùng trong ví dụ. Không có controller tự viết cho `/actuator/health` hoặc `/actuator/metrics`: các khả năng đó do Actuator cung cấp theo cấu hình.

### 7.3. Cấu hình phạm vi thực hành

Tệp `src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: actuator-intro

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
  endpoint:
    health:
      show-details: never
~~~

Ví dụ chỉ lắng nghe trên địa chỉ loopback `127.0.0.1` để thực hành từ cùng máy. Nó không chứa thư viện Spring Security và chưa thiết lập cơ chế đăng nhập. Trong một môi trường thông thường, các tiến trình khác truy cập được địa chỉ này cũng có thể gọi các đường dẫn đang mở; cần tính đến cả proxy, chuyển tiếp cổng và cách triển khai nếu thay đổi môi trường.

`show-details: never` yêu cầu không đưa chi tiết health ra phản hồi. Giảm chi tiết phản hồi không thay thế cho việc phân quyền truy cập.

### 7.4. Biên dịch và khởi chạy

Mở terminal tại thư mục chứa `pom.xml`:

~~~powershell
mvn clean package
java -jar target/actuator-intro-1.0.0.jar
~~~

Lệnh đầu tạo JAR thực thi. Lệnh sau giữ ứng dụng chạy trong terminal; chờ hoàn tất khởi động rồi mở terminal thứ hai để gọi thử. Nếu cổng `8080` đã bị sử dụng, dừng ứng dụng đang chiếm cổng hoặc đổi `server.port` và sửa URL thử nghiệm tương ứng.

Vì chương trình dùng thư viện Spring Boot và cần đóng gói cùng các phụ thuộc, chạy trực tiếp một lệnh `javac` trên tệp nguồn sẽ không đủ. Maven đảm nhiệm biên dịch và đóng gói; `java -jar` thực thi sản phẩm đã tạo.

## 8. Đọc kết quả và giới hạn của từng phép thử

Các lệnh bên dưới dùng PowerShell trên Windows. `curl.exe` gọi chương trình cURL, tránh nhầm với alias `curl` trong một số phiên bản PowerShell. Trên Linux hoặc macOS, dùng lệnh `curl` tương ứng.

### 8.1. API người dùng trả lời gì?

~~~powershell
curl.exe --silent http://127.0.0.1:8080/hello
~~~

Nội dung phản hồi:

~~~text
Xin chao Actuator
~~~

Kết quả chứng minh yêu cầu vừa gửi tới `/hello` đã được xử lý theo mã ví dụ. Nó không chứng minh mọi API của một ứng dụng lớn đều hoạt động.

### 8.2. Health cho biết gì?

~~~powershell
curl.exe --silent http://127.0.0.1:8080/actuator/health
~~~

Với các phép kiểm tra mặc định đang đạt, nội dung phản hồi là:

~~~json
{"status":"UP"}
~~~

Không nên đọc `UP` thành “mọi giao dịch nghiệp vụ chắc chắn thành công”. Trong ví dụ không có kết nối cơ sở dữ liệu, nên kết quả này không cung cấp bằng chứng về một cơ sở dữ liệu nào. Một nhà cung cấp thanh toán cũng chưa được đánh giá chỉ vì API health trả `UP`.

Nếu môi trường khiến một phép kiểm tra trả tình trạng khác, hãy điều tra phép kiểm tra đó thay vì sửa kỳ vọng để luôn thấy `UP`. Tình trạng health có ý nghĩa khi hiểu rõ nó đang kiểm tra điều gì.

### 8.3. Vì sao info có thể rỗng?

~~~powershell
curl.exe --silent http://127.0.0.1:8080/actuator/info
~~~

Với đúng dự án tối thiểu này, nội dung phản hồi là:

~~~json
{}
~~~

Đây là ví dụ cụ thể cho việc **mở endpoint** và **cung cấp nội dung cho endpoint** là hai việc khác nhau. Khai báo `spring.application.name` không tự biến giá trị đó thành nội dung của `/actuator/info`.

Muốn dùng info để nhận diện bản triển khai, cần chủ động chọn và cung cấp nguồn thông tin phù hợp. Bài này giữ phản hồi rỗng để bạn quan sát rõ giới hạn của cấu hình ban đầu.

### 8.4. Yêu cầu vừa gọi có được đo không?

Spring MVC được tích hợp đo thời gian yêu cầu với tên mặc định `http.server.requests`. Có thể đọc số đo đó sau khi đã gọi `/hello`:

~~~powershell
curl.exe --silent "http://127.0.0.1:8080/actuator/metrics/http.server.requests?tag=uri:/hello&tag=method:GET"
~~~

Dữ liệu trả về gồm các phép đo và nhãn liên quan. Thời gian xử lý phụ thuộc máy, lần chạy và tải; không nên chép một giá trị thời gian cố định làm kết quả bắt buộc.

Để chỉ lấy số lần gọi trong nhóm đã chọn:

~~~powershell
$metric = Invoke-RestMethod -Uri "http://127.0.0.1:8080/actuator/metrics/http.server.requests?tag=uri:/hello&tag=method:GET"
$count = $metric.measurements | Where-Object { $_.statistic -eq "COUNT" }
[int]$count.value
~~~

Nếu ứng dụng vừa được khởi động và chỉ có đúng một yêu cầu `GET /hello` hoàn tất, dòng kết quả là:

~~~text
1
~~~

Gọi lại `/hello` một lần, đợi yêu cầu hoàn tất rồi chạy lại đoạn đọc số đo. Kết quả khi đó là `2`. Các lần đọc health hoặc metrics không thuộc nhóm `uri:/hello` đã lọc.

Bộ đếm thuộc tiến trình đang chạy; khởi động lại ví dụ sẽ bắt đầu một chu kỳ ghi nhận mới. Việc lưu lịch sử qua nhiều lần khởi động thuộc thiết kế thu thập bên ngoài. [Tài liệu tên số đo HTTP và truy vấn theo tag](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported.spring-mvc).

### 8.5. Endpoint không được công bố

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:8080/actuator/beans
~~~

Với đúng cấu hình của dự án tối thiểu, mã HTTP in ra là:

~~~text
404
~~~

`beans` không nằm trong danh sách công bố của ví dụ. Thử nghiệm này giúp phân biệt “starter đã có trong dự án” với “mọi endpoint đều truy cập được qua web”.

`NUL` là thiết bị bỏ nội dung phản hồi trên Windows; trên Linux hoặc macOS dùng `/dev/null`.

## 9. Từ bài thực hành tới bài toán vận hành thật

Từ những phép thử trên, có thể hình thành cách tiếp cận theo nhu cầu:

| Nhu cầu | Thiết kế cần bổ sung |
| --- | --- |
| Nhận biết mất khả năng phục vụ | Chọn phép kiểm tra phù hợp và cách bên ngoài đánh giá kết quả |
| Phát hiện suy giảm hiệu năng | Thu thập độ trễ, lưu lịch sử, đặt ngưỡng và xem phân bố |
| Phát hiện lỗi nghiệp vụ quan trọng | Chọn tín hiệu phản ánh đúng kết quả nghiệp vụ |
| Biết bản đang triển khai | Cung cấp thông tin phiên bản có nguồn rõ ràng |
| Điều tra yêu cầu đi qua nhiều dịch vụ | Thiết lập truyền ngữ cảnh, ghi nhận và lưu dấu vết |
| Báo cho người trực | Cấu hình quy tắc cảnh báo, nơi nhận và quy trình phản ứng |

Đây là các quyết định thiết kế cần đưa ra cho hệ thống cụ thể, không phải lời hứa rằng starter sẽ hoàn thành thay bạn.

Ví dụ, nếu “tạo đơn thất bại” vẫn trả HTTP `200` với một mã lỗi trong nội dung, đếm riêng mã HTTP `5xx` sẽ bỏ sót dạng thất bại đó. Đội phát triển cần thống nhất cách biểu diễn kết quả và lựa chọn số đo có ý nghĩa với nghiệp vụ.

Tương tự, một đồ thị độ trễ trung bình có thể che khuất một nhóm nhỏ người dùng phải chờ rất lâu. Khi cần đánh giá trải nghiệm, phải chọn cách đo và cách tổng hợp phản ánh mục tiêu thực tế; đừng coi một con số trung bình là toàn bộ câu chuyện.

## 10. Quyền truy cập cũng là một phần của thiết kế vận hành

Dữ liệu quản trị có thể làm lộ cấu trúc và đặc điểm nội bộ. Những thao tác thay đổi cấu hình còn có thể ảnh hưởng tới ứng dụng đang chạy. Vì vậy, trước khi triển khai cần xác định **ai được đọc gì, ai được thay đổi gì và họ truy cập từ đâu**.

Trong dòng Spring Boot 3.3, khi có Spring Security và chưa khai báo `SecurityFilterChain` riêng, tự cấu hình bảo mật của Boot bảo vệ các actuator ngoài health. Nếu ứng dụng tự khai báo chuỗi bảo mật, đội phát triển chịu trách nhiệm cấu hình đầy đủ các quy tắc truy cập. [Tài liệu bảo mật endpoint](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Đối với bài thực hành, hãy giữ phạm vi local đã cấu hình. Khi áp dụng cho hệ thống triển khai, cần đưa endpoint vào thiết kế truy cập quản trị thực tế. Việc đổi tiền tố hoặc tách cổng giúp tổ chức đường truy cập; bản thân thao tác đó không xác thực danh tính người gọi.

Cũng cần đặt ranh giới dữ liệu: một phép kiểm tra tình trạng không nên tùy tiện trả mật khẩu, mã truy cập hoặc dữ liệu khách hàng trong phần chi tiết. Người viết phép kiểm tra hiểu dữ liệu nghiệp vụ và phải quyết định thông tin nào phù hợp để công bố.

## 11. Những cách hiểu dễ dẫn tới kết luận sai

### “Có Actuator là đã có hệ thống giám sát hoàn chỉnh”

Starter mới tạo nền tảng trong ứng dụng. Còn phải chọn cách thu thập, lưu trữ, hiển thị và phản ứng. Hãy lần theo luồng tín hiệu tới tận nơi người trực nhận được thông tin có thể hành động.

### “Health UP thì không cần thử luồng người dùng”

Health phản ánh những điều đã được kiểm tra. Một kiểm tra giao dịch từ góc nhìn người dùng cung cấp loại bằng chứng khác. Nên chọn cả hai theo mức độ quan trọng của dịch vụ.

### “Metrics endpoint là kho lịch sử”

Trong ví dụ, bạn đang hỏi một tiến trình về số đo nó quản lý. Muốn so sánh hôm nay với hôm qua hoặc trước và sau triển khai, cần hệ thống lưu lịch sử phù hợp.

### “Bật exposure là đã giải quyết quyền truy cập”

Công bố một đường truy cập và cho phép một chủ thể sử dụng đường đó là hai quyết định riêng. Luôn kiểm tra bằng yêu cầu thật từ vị trí và danh tính dự kiến sử dụng.

### “Có số liệu là đã biết nguyên nhân”

Số liệu giúp thu hẹp giả thuyết. Nguyên nhân cần thêm bằng chứng. Nếu độ trễ tăng cùng lỗi gọi dịch vụ ngoài, hãy đối chiếu thời điểm, nhật ký và dấu vết trước khi kết luận.

### “Thực hành càng nhiều endpoint càng tốt”

Ở giai đoạn nhập môn, hãy chọn một câu hỏi và một bằng chứng kiểm chứng được. Mở rộng khi đã hiểu dữ liệu mới sẽ giúp trả lời câu hỏi vận hành nào.

## 12. Tự kiểm tra bằng ba tình huống

**Tình huống 1:** Ứng dụng trả `UP` nhưng chức năng thanh toán thất bại. Điều đó có mâu thuẫn không?

Gợi ý trả lời: chưa đủ cơ sở nói có mâu thuẫn. Cần xem phép kiểm tra hiện tại có đánh giá khả năng thanh toán không, rồi kiểm tra luồng giao dịch thực tế. Tín hiệu health có thể đúng trong phạm vi hẹp của nó.

**Tình huống 2:** Bạn đã thêm starter, gọi `/actuator/metrics` và nhận `404`. Việc đầu tiên cần xác minh là gì?

Gợi ý trả lời: xác minh đúng ứng dụng, đường dẫn và cấu hình công bố web. Trong dòng 3.3, mặc định không công bố metrics qua HTTP. Sau đó mới lần lượt xem điều kiện tạo thành phần, bảo mật và tầng trung gian.

**Tình huống 3:** Người vận hành muốn biết số lần `/hello` được gọi trong ngày hôm qua, nhưng ứng dụng đã khởi động lại sáng nay. Chỉ đọc bộ đếm hiện tại có đủ không?

Gợi ý trả lời: không. Cần dữ liệu lịch sử được thu thập và lưu bên ngoài, cùng cách truy vấn xử lý việc tiến trình khởi động lại.

Sau khi thực hiện bài, bạn cần tự giải thích được ba quan hệ: **API nghiệp vụ với giao diện quản trị; health với phạm vi phép kiểm tra; số đo trong ứng dụng với hệ thống giám sát bên ngoài**. Đây là nền tảng để học tiếp từng khả năng Actuator mà vẫn hiểu nó phục vụ bài toán vận hành nào.
