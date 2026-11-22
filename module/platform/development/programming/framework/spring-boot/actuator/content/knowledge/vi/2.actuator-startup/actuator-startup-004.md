# Chạy ứng dụng mẫu và gọi endpoint health đầu tiên

## 1. Mục tiêu: lấy được một phản hồi có thể kiểm chứng

Sau khi thêm Actuator, điều đầu tiên cần làm là chạy một ứng dụng nhỏ và gọi đúng endpoint `health`. Bài thực hành này giúp bạn kiểm chứng cả chuỗi:

~~~text
Mã nguồn và cấu hình
    -> biên dịch, đóng gói
    -> tiến trình Java khởi động
    -> web server nhận yêu cầu
    -> health endpoint trả phản hồi
~~~

Ở cuối lượt chạy bình thường, lệnh kiểm tra sẽ cho:

~~~text
{"status":"UP"}
HTTP=200
~~~

Hai dòng có ý nghĩa khác nhau:

- `{"status":"UP"}` là nội dung JSON của phản hồi health.
- `HTTP=200` là mã HTTP do công cụ gọi hiển thị thêm.

Bạn sẽ biết cách tạo ra kết quả đó, đọc nó trong phạm vi phù hợp và phân biệt với các trường hợp sai đường dẫn, health báo `DOWN` hoặc ứng dụng không còn nhận kết nối.

Ví dụ dùng **Java 21**, **Spring Boot 3.3.13** và **Maven** trong một dự án độc lập. Đây là bài chạy ứng dụng và kiểm tra endpoint đầu tiên; không cần cơ sở dữ liệu, Docker, Prometheus hoặc tài khoản giám sát.

## 2. Chuẩn bị trước khi tạo dự án

### 2.1. Kiểm tra công cụ

Trong terminal, chạy:

~~~powershell
java -version
mvn -v
curl.exe --version
~~~

Kiểm tra các điểm sau thay vì đòi hỏi toàn bộ đầu ra phải giống một máy khác:

- `java -version` cho biết lệnh `java` đang dùng JDK 21.
- `mvn -v` cho biết Maven cũng đang chạy bằng JDK 21.
- `curl.exe --version` xác nhận chương trình cURL có thể được gọi.

Java trong `PATH` và Java mà Maven dùng có thể khác nhau. Nếu chúng không cùng môi trường dự kiến, hãy chỉnh cấu hình JDK trước khi tiếp tục.

Các lệnh của bài được viết cho **PowerShell trên Windows**. Gọi `curl.exe` giúp tránh nhầm với alias `curl` trong một số bản PowerShell. Trên Linux hoặc macOS, dùng `curl` cho các lệnh cURL tương ứng.

### 2.2. Chuẩn bị thư mục và hai terminal

Tạo một thư mục mới tên `first-health`. Không cần đặt nó bên trong một ứng dụng khác.

Bạn sẽ dùng:

- **Terminal A** để biên dịch và giữ ứng dụng chạy.
- **Terminal B** để gửi yêu cầu HTTP.

Ứng dụng mẫu lắng nghe tại `127.0.0.1:18080`. Nếu cổng này đã được dùng, phần xử lý lỗi bên dưới hướng dẫn đổi cổng.

Lần build đầu cần tải thư viện và plugin từ kho Maven. Việc Maven chưa tải được phụ thuộc là lỗi ở giai đoạn build; lúc đó chưa có health endpoint để kiểm tra.

## 3. Tạo dự án tối thiểu

Cấu trúc cần có:

~~~text
first-health/
├── pom.xml
└── src/main/
    ├── java/example/firsthealth/FirstHealthApplication.java
    └── resources/application.yml
~~~

### 3.1. Khai báo phụ thuộc trong pom.xml

Nội dung đầy đủ của `pom.xml`:

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
    <artifactId>first-health</artifactId>
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

Hai starter có nhiệm vụ khác nhau:

- `spring-boot-starter-web` cung cấp hạ tầng ứng dụng web cho ví dụ.
- `spring-boot-starter-actuator` cung cấp các khả năng quản trị và quan sát tương ứng.

Thêm Actuator không thay thế điều kiện phải có hạ tầng web nếu muốn gọi endpoint qua HTTP. Cách kích hoạt Actuator bằng starter được mô tả trong [tài liệu chính thức](https://docs.spring.io/spring-boot/3.3/reference/actuator/enabling.html).

Parent quản lý phiên bản thư viện và cấu hình build chung. Với parent này, khai báo `spring-boot-maven-plugin` giúp bước đóng gói tạo JAR chạy được bằng `java -jar`. [Spring Boot Maven Plugin: đóng gói ứng dụng](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html).

### 3.2. Tạo lớp khởi động

Tệp `src/main/java/example/firsthealth/FirstHealthApplication.java`:

~~~java
package example.firsthealth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FirstHealthApplication {
    public static void main(String[] args) {
        SpringApplication.run(FirstHealthApplication.class, args);
    }
}
~~~

Tên tệp phải khớp lớp `FirstHealthApplication` và đường dẫn thư mục phải phù hợp với package `example.firsthealth`.

`@SpringBootApplication` bật cấu hình ứng dụng Boot thông thường. `SpringApplication.run(...)` tạo context và khởi động các thành phần cần thiết theo phụ thuộc cùng cấu hình.

Không cần tự viết `HealthController` hoặc phương thức `@GetMapping("/actuator/health")`. `HealthEndpoint` là khả năng do Actuator cung cấp. [API HealthEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/HealthEndpoint.html).

Ví dụ cũng không tạo một API nghiệp vụ giả chỉ để chạy health. Mục đích của ứng dụng là chứng minh endpoint quản trị có thể hoạt động.

### 3.3. Tạo cấu hình

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: first-health

server:
  address: 127.0.0.1
  port: 18080

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
~~~

Ý nghĩa của cấu hình:

| Thuộc tính | Vai trò trong bài |
| --- | --- |
| `spring.application.name` | Đặt tên ứng dụng |
| `server.address` | Chỉ lắng nghe trên địa chỉ loopback `127.0.0.1` |
| `server.port` | Chọn cổng `18080` |
| `management.endpoints.web.exposure.include` | Chỉ chọn `health` để công bố qua web |
| `management.endpoint.health.show-details` | Không đưa chi tiết health ra phản hồi |

Trong dòng Boot 3.3, health vốn đã thuộc danh sách công bố HTTP mặc định. Bài ghi rõ `include: health` để người đọc nhìn thấy phạm vi thực hành. Nó không phải danh sách mọi endpoint được bật trong toàn ứng dụng. [Cấu hình endpoint và exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

YAML dùng dấu cách để thụt lề. Đặt tệp đúng trong `src/main/resources` để nó được đưa vào JAR.

Ví dụ chỉ phục vụ từ cùng máy theo địa chỉ đã chọn và không thêm Spring Security. Khi đưa endpoint quản trị vào một ứng dụng triển khai, cần áp dụng thiết kế truy cập quản trị của môi trường đó; việc giảm chi tiết JSON không thay thế phân quyền.

## 4. Biên dịch và khởi chạy ứng dụng

### 4.1. Đóng gói trong Terminal A

Mở Terminal A tại thư mục `first-health`, nơi có `pom.xml`, rồi chạy:

~~~powershell
mvn clean package
~~~

`clean` loại sản phẩm build cũ; `package` thực hiện các giai đoạn cần thiết để tạo sản phẩm mới.

Đợi Maven hoàn tất. Khi build thành công, nhật ký kết thúc có thông báo:

~~~text
BUILD SUCCESS
~~~

Đây là dấu hiệu của **bước build**, chưa phải bằng chứng ứng dụng đang nhận HTTP.

Có thể xác nhận tệp được tạo bằng:

~~~powershell
Test-Path target/first-health-1.0.0.jar
~~~

Kết quả:

~~~text
True
~~~

Đừng chọn nhầm tệp có hậu tố `.jar.original`. Plugin có thể giữ JAR ban đầu dưới tên đó; JAR bạn cần chạy trong bài là `first-health-1.0.0.jar`.

### 4.2. Khởi chạy JAR

Tiếp tục trong Terminal A:

~~~powershell
java -jar target/first-health-1.0.0.jar
~~~

Lệnh này giữ ứng dụng chạy ở phía trước terminal. Để nguyên terminal đó trong khi thử HTTP.

Trong nhật ký khởi động bình thường của ví dụ, tìm những thông báo chứa các đoạn:

~~~text
Tomcat started on port 18080
Started FirstHealthApplication
~~~

Đây là các đoạn nhận diện trong dòng log, không phải toàn bộ stdout cố định. Dấu thời gian, PID, thời gian khởi động và phần định dạng sẽ khác theo lần chạy.

Nếu ứng dụng báo lỗi rồi kết thúc, hãy sửa lỗi trước khi chuyển sang gọi endpoint. Một dòng log xuất hiện sớm trong quá trình khởi động chưa chắc đã có nghĩa toàn bộ ứng dụng khởi động thành công.

### 4.3. Vì sao bài dùng Maven thay cho một lệnh javac?

Tệp Java cần các thư viện Spring Boot, Spring Framework và Actuator. Biên dịch bằng `javac` đòi hỏi classpath đầy đủ, rồi còn cần đóng gói các phụ thuộc để chạy.

Trong bài, Maven xử lý những bước đó bằng cấu hình đã cho; `java -jar` chạy sản phẩm hoàn chỉnh. Không nên chép riêng tệp Java rồi mong lệnh `java FirstHealthApplication` tự tìm được toàn bộ thư viện.

## 5. Gọi endpoint health đầu tiên

### 5.1. Gửi một yêu cầu GET từ Terminal B

Mở Terminal B và chạy:

~~~powershell
curl.exe --silent --show-error --max-time 5 http://127.0.0.1:18080/actuator/health
~~~

Nếu ứng dụng đang chạy đúng cấu hình và các phép kiểm tra hiện có đều đạt, nội dung phản hồi là:

~~~json
{"status":"UP"}
~~~

Đây là phản hồi HTTP được cURL in tại Terminal B, không phải một dòng log của tiến trình Java trong Terminal A.

Các tùy chọn giúp việc kiểm tra dễ đọc:

- `--silent` bỏ thanh tiến độ.
- `--show-error` vẫn hiển thị thông báo khi có lỗi truyền.
- `--max-time 5` giới hạn thời gian của lượt gọi ở 5 giây.

Không có tùy chọn gửi dữ liệu hoặc chọn phương thức khác, nên yêu cầu ở đây dùng GET. [Tài liệu cURL](https://curl.se/docs/manpage.html).

### 5.2. Tách URL để tránh gọi nhầm

~~~text
http://127.0.0.1:18080/actuator/health
|       |         |       |       |
giao thức       cổng     tiền tố  định danh endpoint
        địa chỉ máy
~~~

Trong dự án này:

- Giao thức là `http` vì chưa cấu hình HTTPS.
- Địa chỉ là `127.0.0.1` của máy đang chạy lệnh.
- Cổng là `18080` theo cấu hình.
- Tiền tố mặc định là `/actuator`.
- Định danh endpoint là `health`.

Nếu gửi từ một container hoặc máy khác, `127.0.0.1` chỉ chính môi trường gửi đó. Nó không tự trỏ về tiến trình Java trên máy phát triển.

Đường dẫn Actuator có thể thay đổi khi ứng dụng cấu hình tiền tố hoặc context path khác. Bài mẫu giữ đường dẫn mặc định để lần gọi đầu tiên dễ kiểm chứng. [Cấu hình đường dẫn HTTP quản trị](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

### 5.3. Xem cả JSON và mã HTTP

Dùng một lệnh có thêm `--write-out`:

~~~powershell
curl.exe --silent --show-error --max-time 5 --write-out '\nHTTP=%{http_code}\n' http://127.0.0.1:18080/actuator/health
~~~

Đầu ra khi health đang `UP`:

~~~text
{"status":"UP"}
HTTP=200
~~~

Trong chuỗi truyền cho cURL, `\n` yêu cầu công cụ xuống dòng. Nhờ đó nội dung JSON và mã HTTP được tách rõ.

Mã `200` cho biết yêu cầu này được xử lý thành công theo phản hồi HTTP. Trường `status` là đánh giá health của ứng dụng trong phản hồi đó. Khi kiểm tra tình trạng, nên xem cả hai.

### 5.4. Đọc JSON bằng PowerShell

Có thể dùng PowerShell để lấy trường dữ liệu thay vì chỉ nhìn chuỗi JSON:

~~~powershell
$health = Invoke-RestMethod -Uri "http://127.0.0.1:18080/actuator/health"
$health.status
~~~

Kết quả trong lượt chạy đang đạt:

~~~text
UP
~~~

`Invoke-RestMethod` chuyển JSON thành đối tượng để đọc thuộc tính. Khi server trả mã lỗi như `503`, hành vi báo lỗi của lệnh khác với lệnh cURL đang dùng ở trên. Khi mới kiểm tra trường hợp lỗi, hãy dùng lệnh cURL có mã HTTP để giữ cách quan sát nhất quán.

Bạn cũng có thể mở địa chỉ health trong trình duyệt trên cùng máy. Trình duyệt có thể hiển thị hoặc định dạng JSON; việc đó không làm đổi ý nghĩa của `status`.

## 6. Hiểu đúng kết quả UP

Health biểu diễn tình trạng dựa trên các thành phần kiểm tra đang tham gia. Mỗi kết quả `Health` có trạng thái và có thể có chi tiết về thành phần được đánh giá. [API Health](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/Health.html).

Với ứng dụng nhỏ này, bạn chưa cấu hình cơ sở dữ liệu hoặc một dịch vụ thanh toán. Vì vậy:

~~~text
UP trong mẫu này
    -> những phép kiểm tra đang có không báo tình trạng xấu

UP trong mẫu này
    -> không phải bằng chứng về một hệ thống thanh toán chưa được tích hợp
~~~

Phép gọi đầu tiên cho bạn bằng chứng rằng tại thời điểm kiểm tra:

1. Từ Terminal B có thể đi tới địa chỉ HTTP đang dùng.
2. Ứng dụng nhận và xử lý yêu cầu tới health endpoint.
3. Health trả trạng thái như trong nội dung phản hồi.

Nó chưa đánh giá tải cao, độ trễ của API nghiệp vụ hoặc mọi phụ thuộc có thể được thêm về sau.

Không nên sửa JSON thành `UP` bằng một controller tự viết chỉ để vượt qua một phép kiểm tra. Khi kết quả khác dự kiến, cần tìm hiểu phép kiểm tra và điều kiện thực tế.

## 7. Hai phép thử giúp tránh kết luận nhầm

### 7.1. Trang gốc có thể trả 404 trong khi health vẫn hoạt động

Ứng dụng này không có controller hoặc trang chủ cho `/`. Kiểm tra mã HTTP của đường dẫn gốc:

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:18080/
~~~

Với đúng dự án mẫu, kết quả là:

~~~text
404
~~~

Sau đó gọi lại `/actuator/health` vẫn có thể nhận `UP` và `200`.

Không có trang chủ không đồng nghĩa web server chưa khởi động. Hãy kiểm tra đúng đường dẫn mà bạn muốn đánh giá.

`NUL` bỏ phần nội dung phản hồi trên Windows. Trên Linux hoặc macOS, dùng `/dev/null` thay cho `NUL`.

### 7.2. Metrics không tự được mở chỉ vì đã gọi được health

~~~powershell
curl.exe --silent --output NUL --write-out "%{http_code}" http://127.0.0.1:18080/actuator/metrics
~~~

Với danh sách công bố chỉ có `health` của bài này, kết quả là:

~~~text
404
~~~

Phép thử xác nhận phạm vi HTTP của mẫu. Không cần mở tất cả endpoint để làm cho bài thực hành “đầy đủ hơn”; mục tiêu hiện tại là chạy và hiểu health đầu tiên.

## 8. Thử có kiểm soát: server còn chạy nhưng health báo DOWN

Phần này là một phép thử tùy chọn, ngắn, nhằm phân biệt **không nhận được kết nối** với **nhận được phản hồi tình trạng xấu**.

### 8.1. Tạo điều kiện kiểm tra không đạt bằng cấu hình

Dừng ứng dụng ở Terminal A bằng `Ctrl+C`. Chạy lại cùng JAR với ngưỡng dung lượng đĩa cố ý rất cao:

~~~powershell
java -jar target/first-health-1.0.0.jar --management.health.diskspace.threshold=9223372036854775807B
~~~

Ngưỡng này cao hơn dung lượng trống trên máy thực hành thông thường. Phép thử thay đổi điều kiện đánh giá dung lượng đĩa; nó không ghi dữ liệu để làm đầy ổ đĩa.

Ứng dụng vẫn có thể khởi động. Đợi nó chạy xong rồi gọi lại ở Terminal B:

~~~powershell
curl.exe --silent --show-error --max-time 5 --write-out '\nHTTP=%{http_code}\n' http://127.0.0.1:18080/actuator/health
~~~

Với phép kiểm tra đĩa không đạt và cấu hình ánh xạ mặc định của mẫu:

~~~text
{"status":"DOWN"}
HTTP=503
~~~

Bạn đã nhận được phản hồi HTTP, tức server vẫn tiếp nhận và xử lý yêu cầu này. Tình trạng `DOWN` nói về kết quả kiểm tra; nó không đồng nghĩa tiến trình đã biến mất.

Việc ánh xạ trạng thái health sang mã HTTP có cơ chế phụ trách riêng. Kết quả trên thuộc cấu hình Boot 3.3 của mẫu, không phải quy tắc cho mọi trường dữ liệu có chữ `DOWN` ở mọi API. [Cơ chế ánh xạ mã HTTP của health](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/health/SimpleHttpCodeStatusMapper.html).

Lệnh cURL của bài không dùng `--fail`. Do đó, nhận được mã `503` không tự làm mã thoát của cURL thành lỗi truyền. Mã HTTP và mã thoát của chương trình là hai loại kết quả cần phân biệt.

### 8.2. Khôi phục điều kiện ban đầu

Dừng lượt chạy vừa thử bằng `Ctrl+C` rồi khởi động lại không có tham số ngưỡng:

~~~powershell
java -jar target/first-health-1.0.0.jar
~~~

Gọi lại health. Khi các phép kiểm tra mặc định đều đạt, bạn nhận `UP` và `200`.

Tham số ngưỡng chỉ áp dụng cho lượt chạy đã truyền nó. Bạn không chỉnh `application.yml` nên không cần sửa tệp để hoàn tác phép thử này.

### 8.3. So với trường hợp ứng dụng đã dừng

Dừng ứng dụng rồi gọi lại health. Nếu không có tiến trình khác nhận trên địa chỉ/cổng đó, cURL báo lỗi kết nối thay vì nhận JSON health.

Nếu `--write-out` in `HTTP=000` trong một lỗi truyền, `000` không phải mã HTTP do health endpoint gửi. Điều cần điều tra trước là khả năng kết nối tới server.

Đừng chờ một ứng dụng đã ngừng chạy tự trả `{"status":"DOWN"}`. Phản hồi JSON chỉ được tạo khi vẫn có thành phần tiếp nhận yêu cầu và tạo phản hồi.

## 9. Xử lý lỗi theo giai đoạn

| Biểu hiện | Giai đoạn cần kiểm tra trước | Hướng kiểm tra |
| --- | --- | --- |
| `mvn` không được nhận diện | Công cụ build | Cài/khai báo Maven và mở lại terminal phù hợp |
| Maven dùng JDK khác dự kiến | Công cụ build | Đối chiếu `mvn -v` với `java -version` |
| Không tải được phụ thuộc | Build | Kiểm tra kết nối, proxy và cấu hình kho Maven |
| Không tìm thấy JAR | Chạy chương trình | Đứng đúng thư mục, kiểm tra build thành công và tên tệp |
| JAR không có main manifest | Đóng gói/chọn sản phẩm | Kiểm tra plugin và tránh chạy `.jar.original` |
| Cổng đã được sử dụng | Khởi động web server | Xác định ứng dụng đang dùng cổng hoặc chọn cổng khác |
| Connection refused hoặc hết thời gian chờ | Kết nối | Kiểm tra tiến trình, địa chỉ, cổng và nhật ký khởi động |
| HTTP `404` | Định tuyến/công bố | Kiểm tra URL và cấu hình đang thực sự được chạy |
| HTTP `401` hoặc `403` | Truy cập | Kiểm tra cơ chế bảo mật và ứng dụng đích |
| JSON `DOWN` với HTTP `503` | Phép kiểm tra tình trạng | Kiểm tra các điều kiện health, gồm tham số đã truyền |

Bảng là hướng điều tra cho bài mẫu, không phải cách suy ngược tuyệt đối cho mọi hệ thống có proxy hoặc quy tắc tùy chỉnh.

### 9.1. Đổi cổng khi cần

Ví dụ, nếu `18080` đã bị chiếm:

~~~powershell
java -jar target/first-health-1.0.0.jar --server.port=18081
~~~

URL kiểm tra phải đổi theo:

~~~powershell
curl.exe --silent --show-error --max-time 5 http://127.0.0.1:18081/actuator/health
~~~

Nếu vẫn gọi `18080`, bạn có thể đang gọi một ứng dụng khác. Nhận được một JSON hợp lệ chưa đủ chứng minh bạn đang kiểm tra đúng tiến trình vừa khởi động.

### 9.2. Chạy lại sau khi sửa tệp

Khi đổi mã Java hoặc `application.yml` rồi tiếp tục chạy JAR đã đóng gói trước đó, JAR không tự lấy bản sửa trong thư mục nguồn.

Để kiểm tra bản mới:

1. Dừng tiến trình đang chạy.
2. Chạy `mvn clean package`.
3. Chạy lại JAR và chờ hoàn tất khởi động.
4. Gọi đúng URL theo cấu hình mới.

Ngược lại, tham số dòng lệnh như `--server.port=18081` được đưa trực tiếp vào lượt chạy, không cần build lại chỉ để truyền giá trị đó.

### 9.3. Một dự án tối thiểu bất ngờ yêu cầu đăng nhập

Đúng `pom.xml` của bài không thêm Spring Security. Nếu bạn gặp màn hình đăng nhập hoặc `401/403`, hãy kiểm tra có đang chạy đúng JAR, đúng cổng và đúng tập phụ thuộc không.

Nếu thực hiện trên ứng dụng đã có bảo mật, cần đọc quy tắc của chính ứng dụng đó. Mở health bằng cách bỏ toàn bộ bảo mật không phải bước bắt buộc của bài thực hành này.

## 10. Tự xác nhận đã hoàn thành bài

Bạn đã hoàn thành vòng thực hành khi có thể tự làm lại và giải thích:

- Build thành công tạo đúng JAR; ứng dụng thực sự được chạy từ JAR đó.
- Gọi `GET /actuator/health` tại đúng địa chỉ/cổng.
- Đọc riêng nội dung `status` và mã HTTP.
- Giải thích vì sao `UP` chỉ phản ánh các phép kiểm tra đang có.
- Phân biệt `404` của một đường dẫn khác, `503` của health và lỗi không có kết nối.
- Dừng ứng dụng rồi nhận ra endpoint không còn tự trả JSON.

**Bài tập ngắn:** Chạy ứng dụng trên cổng `18081`, gọi health bằng cả cURL và PowerShell, rồi dừng nó. Với mỗi lượt kiểm tra, ghi lại bạn đã nhận phản hồi HTTP hay mới gặp lỗi truyền.

Câu hỏi cần tự trả lời là: **“Tôi có bằng chứng gì rằng đúng ứng dụng của mình đang nhận yêu cầu và health đang đánh giá điều gì?”** Trả lời rõ câu đó sẽ giúp bạn dùng endpoint đầu tiên như một công cụ kiểm chứng thực tế, thay vì chỉ tìm một chuỗi `UP`.
