# Đọc từng phần tệp log bằng HTTP Range và kiểm soát thông tin nhạy cảm

## 1. Hiểu đúng thứ đang được đọc

Một tệp log có thể lớn đến hàng trăm MB trong khi người vận hành chỉ cần xem vài KB quanh một sự cố. Nếu tải toàn bộ tệp mỗi lần, việc chẩn đoán vừa chậm vừa tạo thêm lưu lượng và thêm bản sao dữ liệu cần bảo vệ.

HTTP Range cho phép máy khách yêu cầu một khoảng **byte** của tài nguyên. Với Spring Boot Actuator, tài nguyên ở đây là tệp mà endpoint `logfile` đang phục vụ. Ví dụ, `Range: bytes=0-1023` yêu cầu tối đa 1.024 byte đầu tiên. Đây không phải câu lệnh lấy 1.024 dòng, truy vấn theo thời gian hay tìm theo mã yêu cầu.

Cần giữ hai câu hỏi tách biệt khi vận hành:

- **Đọc phần nào?** Range quyết định vị trí byte cần truyền.
- **Ai được đọc, và dữ liệu nào được phép xuất hiện?** Cấu hình bảo mật và chính sách ghi log quyết định điều này.

Chia nhỏ một tệp chứa mật khẩu thành nhiều phản hồi nhỏ vẫn làm lộ mật khẩu. Range là cơ chế truyền dữ liệu, không phải cơ chế che dữ liệu.

Bài dùng Spring Boot **3.3.x**, Spring MVC và Java 17 trở lên; JDK 21 phù hợp để thực hành. Spring Boot có tài liệu riêng cho `GET /actuator/logfile`; phần đọc bằng Range **không được hỗ trợ khi dùng Jersey**. Không suy rộng kết quả thí nghiệm MVC sang mọi bộ xử lý HTTP. [Tài liệu logfile của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/logfile.html).

## 2. Đọc Range theo vị trí byte

### 2.1. Điểm đầu bằng 0, điểm cuối được tính vào khoảng

Với `bytes=a-b`, byte ở cả vị trí `a` và `b` đều thuộc phần được yêu cầu. Khi khoảng nằm trong tệp, số byte là `b - a + 1`.

Dùng tệp mẫu có đúng nội dung sau, mã hóa UTF-8, xuống dòng bằng LF, không có BOM:

```text
alpha
beta
gamma
```

Tệp này có **17 byte**, kể cả ba ký tự LF:

```text
Vị trí:  0 1 2 3 4  5 6 7 8 9 10 11 12 13 14 15 16
Dữ liệu: a l p h a LF b e t a LF  g  a  m  m  a LF
```

| Header yêu cầu | Ý nghĩa trên tệp 17 byte | Phần nhận được khi xử lý thành công |
| --- | --- | --- |
| `Range: bytes=0-4` | Byte 0 đến 4 | `alpha`, 5 byte |
| `Range: bytes=6-9` | Byte 6 đến 9 | `beta`, 4 byte |
| `Range: bytes=11-` | Từ byte 11 đến cuối | `gamma` và LF, 6 byte |
| `Range: bytes=-6` | 6 byte cuối | `gamma` và LF, 6 byte |
| `Range: bytes=0-99` | Điểm cuối vượt cuối tệp | Khoảng được giới hạn đến byte 16 |
| `Range: bytes=99-` | Điểm đầu vượt cuối tệp | Không có khoảng phù hợp; xem phản hồi `416` |

Một khoảng hợp lệ có điểm cuối vượt cuối tệp không đồng nghĩa với lỗi: máy chủ có thể giới hạn điểm cuối theo độ dài hiện tại. Một suffix dài hơn tệp có thể bao trùm toàn bộ tệp. Không suy ra rằng “nhận đủ nội dung” luôn phải mang mã `200`.

Range đánh số byte, bao gồm cả byte xuống dòng. Với log tiếng Việt, một ký tự có thể chiếm nhiều byte UTF-8; với CRLF, mỗi lần xuống dòng thường chiếm hai byte. Không tính offset bằng số ký tự Java, số cột trên màn hình hoặc số dòng. [RFC 9110, mục 14: Range Requests](https://www.rfc-editor.org/rfc/rfc9110.html#section-14).

### 2.2. Phải đọc mã trạng thái và header phản hồi

Một phản hồi một khoảng có thể chứa:

```http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 6-9/17
Content-Length: 4
```

Ý nghĩa:

- `206`: máy chủ đang trả một phần tài nguyên.
- `Accept-Ranges: bytes`: máy chủ thông báo hỗ trợ đơn vị byte.
- `Content-Range`: phần thực tế là byte 6 đến 9; độ dài toàn bộ tài nguyên tại thời điểm xác định là 17 byte.
- `Content-Length`: độ dài phần thân phản hồi này, không phải độ dài toàn bộ tệp.

Không dùng `Content-Length: 4` để kết luận rằng tệp log chỉ có 4 byte.

Nếu yêu cầu `bytes=99-` trên tệp mẫu, phản hồi cần chú ý là:

```http
HTTP/1.1 416 Requested Range Not Satisfiable
Content-Range: bytes */17
```

Cụm từ sau số trạng thái có thể khác giữa máy chủ; điều cần xử lý là **mã 416** và tổng độ dài trong `Content-Range`. Không dựa vào định dạng phần thân lỗi để tính offset.

HTTP cho phép máy chủ bỏ qua Range và trả `200`. Vì vậy, máy khách phải kiểm tra phản hồi trước khi nối dữ liệu. Nếu đang chờ một đoạn 4 KB mà nhận `200`, không được coi phần thân đó là đoạn tiếp theo rồi nối vào tệp đã tải. [RFC 9110: 206](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.7), [416](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.17).

Bài chỉ dùng **một khoảng trong mỗi yêu cầu**. Nhiều khoảng có thể tạo phản hồi `multipart/byteranges`, cần bộ phân tích riêng và giới hạn tài nguyên; không ghép phần thân multipart như một đoạn văn bản thông thường.

## 3. Xác định đúng tệp mà Actuator phục vụ

### 3.1. Tệp log do hệ thống logging ghi

Trong ứng dụng dùng các starter thông thường, muốn ghi log ra tệp có thể cấu hình:

```yaml
logging:
  file:
    name: ./logs/application.log

management:
  endpoints:
    web:
      exposure:
        include: logfile
```

Đây là **đoạn cấu hình nguồn tệp**, chưa phải cấu hình bảo mật hoàn chỉnh để chạy trên mạng.

`logging.file.name` chỉ định tên tệp. Nếu dùng `logging.file.path` thay thế, cấu hình mặc định của Boot ghi `spring.log` trong thư mục đó. Khi đặt cả hai, `logging.file.name` được ưu tiên. Đường dẫn tương đối được hiểu theo thư mục làm việc của tiến trình, không mặc nhiên theo thư mục chứa mã nguồn. [Spring Boot 3.3: File Output](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.file-output).

Việc có log trên console không chứng minh rằng `logfile` có một tệp để trả về. Với container chỉ ghi stdout/stderr, cần xác định luồng thu thập log thực tế; không tạo thêm bản sao log chỉ để có endpoint.

### 3.2. Tệp được chỉ định bằng external-file

Spring Boot 3.3 có thuộc tính:

```yaml
management:
  endpoint:
    logfile:
      external-file: ./logs/range-demo.log
```

Thuộc tính này chỉ định tệp mà `logfile` đọc, hữu ích khi log được ghi qua chuyển hướng đầu ra hoặc qua một cơ chế khác. **Nó không cấu hình bộ ghi log và không tự tạo tệp.** Trong thí nghiệm dưới đây, ta dùng nó để phục vụ tệp cố định, tránh log khởi động làm thay đổi các offset. [Thuộc tính management.endpoint.logfile.external-file](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.logfile.external-file).

Endpoint phục vụ một tệp đã cấu hình, không cung cấp chức năng tùy ý chọn đường dẫn, liệt kê thư mục hay duyệt toàn bộ các tệp log đã xoay vòng. Không thêm tham số đường dẫn do người dùng điều khiển để biến nó thành trình đọc tệp của máy chủ.

## 4. Thí nghiệm có dữ liệu cố định và xác thực

### 4.1. Chuẩn bị ứng dụng

Dùng một ứng dụng Spring Boot 3.3.x có lớp `@SpringBootApplication` và ba dependency do cùng phiên bản Spring Boot quản lý:

```text
org.springframework.boot:spring-boot-starter-web
org.springframework.boot:spring-boot-starter-actuator
org.springframework.boot:spring-boot-starter-security
```

Các đoạn Spring bên dưới là mã **bổ sung vào ứng dụng này**, không phải chương trình có thể chạy bằng `javac` mà không có dependency Spring.

Tạo tệp `src/main/resources/application.yml` cho ứng dụng thực hành riêng:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: logfile
  endpoint:
    logfile:
      external-file: ./logs/range-demo.log

spring:
  security:
    user:
      name: log-reader
      password: "${LOG_READER_PASSWORD}"
      roles:
        - LOG_READER
```

Đặt biến môi trường `LOG_READER_PASSWORD` bằng một mật khẩu thử riêng trước khi khởi động. Không ghi mật khẩu vào YAML, lệnh mẫu có thể lưu trong lịch sử shell hoặc tệp log. Không để nguyên biến chưa được cấp giá trị.

Ứng dụng này chỉ lắng nghe trên loopback để thử cục bộ. Khi triển khai qua mạng, dùng HTTPS và kiểm soát đường truy cập; Basic Authentication không tự mã hóa thông tin xác thực. Không dùng tùy chọn bỏ kiểm tra chứng chỉ để giải quyết lỗi HTTPS.

### 4.2. Chỉ cho vai trò đọc log truy cập

Thêm `LogReadSecurity.java` trong package được ứng dụng quét:

```java
package example.logrange;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class LogReadSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("logfile"))
                    .hasRole("LOG_READER")
                .anyRequest().denyAll());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Trong ứng dụng thực hành, chuỗi lọc này áp dụng cho mọi yêu cầu: chỉ người có quyền `ROLE_LOG_READER` được đi tới endpoint `logfile`; các yêu cầu khác bị từ chối. `hasRole("LOG_READER")` tự dùng tiền tố `ROLE_`, tương ứng với `spring.security.user.roles` ở trên.

Đây là chính sách cho **ứng dụng thử chỉ phục vụ log**. Với ứng dụng có API nghiệp vụ và chuỗi lọc sẵn có, phải tích hợp quy tắc đọc log vào chính sách hiện hữu; không chép quy tắc từ chối mọi đường dẫn để thay thế toàn bộ quyền nghiệp vụ.

Khi tự khai báo `SecurityFilterChain`, người viết cấu hình chịu trách nhiệm bảo vệ các đường truy cập liên quan vì cấu hình bảo mật tự động của Boot sẽ nhường quyền. `exposure.include` chỉ làm endpoint có thể truy cập qua HTTP; nó không cấp quyền cho người dùng. Không cần tắt CSRF để thực hiện các yêu cầu `GET` trong bài. [Spring Boot 3.3: bảo mật Actuator](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Tài khoản đơn của Boot chỉ giúp thí nghiệm gọn. Hệ thống thực tế nên dùng danh tính cá nhân hoặc tài khoản dịch vụ được quản lý, có thu hồi quyền và ghi nhận truy cập phù hợp.

### 4.3. Tạo chính xác tệp 17 byte bằng Java

Lưu chương trình độc lập sau thành `LogFixture.java` trong thư mục làm việc của thí nghiệm. Chương trình **tạo hoặc ghi đè riêng** `./logs/range-demo.log`; không chạy nó trên tệp log vận hành.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LogFixture {
    public static void main(String[] args) throws IOException {
        Path log = Path.of("logs", "range-demo.log");
        Files.createDirectories(log.getParent());
        Files.writeString(log, "alpha\nbeta\ngamma\n", StandardCharsets.UTF_8);
        System.out.println("bytes=" + Files.size(log));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 LogFixture.java
java LogFixture
```

Stdout chính xác:

```text
bytes=17
```

Java dùng các ký tự `\n` đã chỉ định nên tệp này dùng LF cả trên Windows. `StandardCharsets.UTF_8` trong cách ghi trên không thêm BOM.

Khởi động ứng dụng Spring Boot từ **cùng thư mục làm việc** sau khi tạo tệp và cấp biến môi trường. Giữ tệp mẫu không thay đổi trong các lần đọc dưới đây. Không đồng thời cấu hình hệ thống logging ghi vào `range-demo.log`.

### 4.4. Lấy đúng bốn byte của dòng beta

Các lệnh sau dùng `curl` thực. Trong Windows PowerShell, dùng **`curl.exe`** để tránh nhầm với bí danh của `Invoke-WebRequest`. Nếu môi trường không có cú pháp xuống dòng kiểu Bash, viết lệnh trên một dòng.

```bash
curl --user log-reader --max-time 10 \
  -H 'Accept-Encoding: identity' \
  -H 'Range: bytes=6-9' \
  -D range.headers -o range.part \
  http://127.0.0.1:8080/actuator/logfile
```

`--user log-reader` yêu cầu curl hỏi mật khẩu trên terminal, thay vì đặt mật khẩu trực tiếp trong lệnh. `-D` lưu header riêng; `-o` lưu phần thân dưới dạng byte vào tệp riêng. Không trộn header vào nội dung bằng `-i` khi định nối các phần tải.

Với cấu hình và tệp mẫu ở trên, các header quan trọng là:

```http
HTTP/1.1 206
Accept-Ranges: bytes
Content-Range: bytes 6-9/17
Content-Length: 4
```

Đây là phần trích các trường cần kiểm tra, không phải toàn bộ header hoặc thứ tự header cố định. Tệp `range.part` có đúng bốn byte ASCII của `beta`, **không có LF ở cuối**.

Kiểm tra bằng PowerShell:

```powershell
(Get-Item -LiteralPath './range.part').Length
[System.Text.Encoding]::UTF8.GetString(
    [System.IO.File]::ReadAllBytes((Join-Path (Get-Location) 'range.part'))
)
```

Kết quả hiển thị:

```text
4
beta
```

### 4.5. Đọc đuôi tệp và thử khoảng vượt giới hạn

Lấy sáu byte cuối, lưu riêng để không ghi đè kết quả trước:

```bash
curl --user log-reader --max-time 10 \
  -H 'Accept-Encoding: identity' \
  -H 'Range: bytes=-6' \
  -D suffix.headers -o suffix.part \
  http://127.0.0.1:8080/actuator/logfile
```

Kết quả mong đợi:

```http
HTTP/1.1 206
Content-Range: bytes 11-16/17
Content-Length: 6
```

Phần thân là `gamma` theo sau bằng LF. **Sáu byte cuối không có nghĩa là sáu dòng cuối**; kết quả này trùng đúng một dòng vì cách tạo tệp mẫu.

Thử điểm đầu không tồn tại:

```bash
curl --user log-reader --max-time 10 \
  -H 'Accept-Encoding: identity' \
  -H 'Range: bytes=99-' \
  -D invalid.headers -o invalid.body \
  http://127.0.0.1:8080/actuator/logfile
```

Mong đợi `416` và `Content-Range: bytes */17`. Tệp `invalid.body` là phần thân phản hồi `416` nếu có; nó không phải phần tiếp theo của log. Không giả định phần thân này luôn trống hoặc luôn là JSON: một số đường xử lý có thể vẫn mang dữ liệu tệp. Bảo vệ nó như dữ liệu log và không nối nó vào các phần tải thành công.

curl thông thường có thể hoàn tất với mã thoát 0 dù HTTP là `416`. Khi viết công cụ tự động, phải kiểm tra mã HTTP; có thể dùng `--write-out '%{http_code}'` hoặc chọn `--fail-with-body` nếu phiên bản curl hỗ trợ. Không dùng riêng mã thoát mặc định để kết luận Range thành công.

Cuối cùng, thử cùng yêu cầu khi không gửi thông tin xác thực, rồi thử bằng một danh tính hợp lệ nhưng không có vai trò đọc log trong môi trường có nhiều tài khoản. Với chính sách Basic ở trên, hai trường hợp tương ứng cần bị chặn bằng `401` và `403`; không trường hợp nào được trả nội dung log.

## 5. Đọc nối tiếp mà không ghép sai dữ liệu

### 5.1. Cập nhật offset theo phản hồi thực tế

Ví dụ đang đọc một tệp ổn định:

1. Yêu cầu `bytes=0-4095`.
2. Chỉ chấp nhận dữ liệu sau khi kiểm tra mã `206`, đơn vị `bytes`, khoảng trả về và kích thước phần thân thực nhận.
3. Nếu `Content-Range` báo `bytes 0-4095/12000`, offset tiếp theo là **4096**.
4. Yêu cầu `bytes=4096-8191` khi cần đoạn kế tiếp, rồi tiếp tục theo điểm cuối thực nhận.

Không lấy offset tiếp theo bằng “số ký tự đã hiển thị”. Nếu lần đầu tệp chỉ dài 100 byte, phản hồi có thể kết thúc ở byte 99; phải đi tiếp từ 100, không nhảy cứng đến 4096.

Với log đang tăng, dữ liệu trong bộ đệm của bộ ghi có thể chưa xuất hiện trên đĩa. Một yêu cầu Range chỉ đọc phần hiện có tại lần xử lý đó, không chờ dữ liệu tương lai và không giữ kết nối để theo dõi như `tail -f`. Muốn theo dõi phải gửi các yêu cầu mới theo chu kỳ có giới hạn.

Máy khách thực tế còn cần giới hạn số byte được nhận và lưu, số yêu cầu đồng thời, thời gian chờ và tần suất đọc. Nếu máy chủ hoặc proxy trả `200` cho yêu cầu Range, ứng dụng khách cần dừng hoặc xử lý theo chính sách tải toàn tệp rõ ràng; riêng `--max-time` không phải giới hạn dung lượng.

### 5.2. Xoay vòng và cắt ngắn làm offset cũ mất ý nghĩa

Giả sử đã đọc tới byte 50.000 của `application.log`. Sau đó tệp bị xoay vòng: tên cũ trỏ tới một tệp mới chỉ có 2.000 byte. Yêu cầu `bytes=50000-` có thể nhận `416`.

Tuy nhiên, `416` còn có thể xuất hiện khi offset đang ở đúng cuối tệp và chưa có byte mới. Không kết luận “đã xoay vòng” chỉ từ một mã `416`.

Quy trình xử lý hợp lý:

- Đọc lại tổng độ dài nếu có, kiểm tra dấu hiệu đổi tệp và chính sách xoay vòng.
- Nếu xác định đã sang tệp mới, bắt đầu một phiên đọc mới; có thể lấy một suffix nhỏ để định hướng.
- Không nối byte từ hai phiên bản tệp vào cùng một bản sao rồi coi đó là một tệp nguyên vẹn.
- Không thử lại vô hạn cùng offset đang bị từ chối.

Chỉ so sánh kích thước cũng chưa đủ: tệp mới có thể bằng hoặc lớn hơn tệp cũ. Tên đường dẫn giữ nguyên không chứng minh tài nguyên giữ nguyên. Endpoint `logfile` không cung cấp cơ chế snapshot bất biến xuyên suốt nhiều yêu cầu.

HTTP có `If-Range` để gắn yêu cầu tiếp tục với bộ xác thực tài nguyên thích hợp. Chỉ dựa vào cơ chế đó khi đã kiểm chứng endpoint và hạ tầng thực sự cấp, xử lý validator phù hợp; không mặc định `logfile` luôn có ETag mạnh hoặc hỗ trợ nối tải an toàn qua xoay vòng. Cần bằng chứng đầy đủ thì nên xuất một bản log cố định được kiểm soát quyền truy cập, thay vì giả định tệp đang ghi là bất biến. [RFC 9110: If-Range](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5).

### 5.3. Giữ byte trước, giải mã và tách dòng sau

Một Range có thể bắt đầu giữa ký tự UTF-8 hoặc giữa một dòng. Nếu giải mã độc lập từng đoạn thành chuỗi, ký tự tiếng Việt ở ranh giới có thể bị thay bằng ký tự lỗi.

Khi xây dựng trình đọc nhiều đoạn:

- Ghép byte theo đúng thứ tự hoặc dùng bộ giải mã UTF-8 có giữ trạng thái.
- Giữ phần dòng chưa kết thúc để ghép với phần sau.
- Khi lấy suffix để xem nhanh, nhận biết rằng dòng đầu có thể bị cắt; chỉ bỏ dòng đó khi mục đích là hiển thị các dòng hoàn chỉnh.
- Nếu cần bảo toàn bằng chứng, giữ bản byte nguyên gốc trước khi tạo bản hiển thị.

`Accept-Encoding: identity` trong thí nghiệm giúp tránh nén nội dung làm việc đối chiếu byte phức tạp hơn. Không tự thêm `--compressed` rồi lấy số byte sau giải nén làm offset cho dữ liệu mã hóa. Khi qua proxy, kiểm tra cả `Content-Encoding` lẫn `Content-Range` và chính sách biến đổi nội dung.

## 6. Kiểm soát thông tin nhạy cảm từ lúc ghi đến lúc đọc

### 6.1. Không trông chờ logfile tự che bí mật

`logfile` trả nội dung tệp, bao gồm những chuỗi đã bị ghi nhầm vào đó. Cấu hình như `management.endpoint.env.show-values=never` điều khiển endpoint `env`; nó không biến các byte trong tệp log thành bản đã che dữ liệu. Tương tự, quy tắc che giá trị cấu hình không thể được coi là bộ lọc chung cho mọi endpoint.

**Người có quyền đọc logfile cần được xem là có quyền đọc toàn bộ tệp được phục vụ**, kể cả khi công cụ hiện tại chỉ yêu cầu một khoảng nhỏ. Họ có thể gửi nhiều Range hoặc một yêu cầu không có Range.

Nếu tệp chứa dữ liệu của nhiều khách hàng, vai trò “được đọc log” không tự tạo quyền đọc riêng theo từng khách hàng. Cần tách dữ liệu hoặc một dịch vụ truy vấn có kiểm tra quyền tương ứng; không dùng khoảng byte làm ranh giới phân quyền.

### 6.2. Ưu tiên không ghi dữ liệu nhạy cảm

Áp dụng chính sách dữ liệu tại nơi phát sinh sự kiện: chỉ ghi các trường đã được chọn, hạn chế định danh cá nhân, loại thông tin xác thực và làm sạch dữ liệu không tin cậy trước khi ghi. Đây cũng là hướng dẫn cốt lõi trong [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Ví dụ sự kiện tổng hợp, không chứa dữ liệu thật:

```text
Không nên:
login failed email=person@example.test password=demo-password token=demo-token

Nên:
login_failed requestId=req-demo-42 reason=invalid_credentials
```

Ví dụ thứ hai giữ thông tin phục vụ đối chiếu sự cố mà không ghi mật khẩu hay token. `requestId` cũng cần có quy tắc sinh và kiểm tra; không coi mọi giá trị do máy khách đưa vào là an toàn để ghi nguyên văn.

Các vị trí thường bị bỏ sót gồm bộ ghi toàn bộ request/response, interceptor, stack trace có thông tin kết nối và log DEBUG của thư viện. Một bộ lọc ở duy nhất lớp nghiệp vụ không bảo đảm mọi nguồn ghi đều đã tuân thủ.

Che dữ liệu sau khi đã ghi chỉ là lớp xử lý bổ sung: mẫu chuỗi có thể bỏ sót định dạng mới, và bản gốc nhạy cảm vẫn nằm trên đĩa, bản sao lưu hoặc kho thu thập log. Nếu một bí mật đã lộ, cần thu hồi hoặc thay bí mật theo quy trình sự cố, không chỉ sửa cách hiển thị.

### 6.3. Bảo vệ cả đường truyền và bản sao tải về

| Lớp kiểm soát | Việc cần xác minh |
| --- | --- |
| Điểm truy cập | Chỉ expose endpoint cần dùng; giới hạn mạng, danh tính và quyền đọc |
| Đường truyền | HTTPS với chứng chỉ hợp lệ; không để thông tin xác thực trong URL |
| Tệp nguồn | Tài khoản tiến trình chỉ có quyền tệp cần thiết; đường dẫn do cấu hình tin cậy quản lý |
| Cache và proxy | Không cache công khai phản hồi log; kiểm tra header thực tế qua toàn bộ hạ tầng |
| Bản tải cục bộ | Thư mục được bảo vệ; không tự đính kèm vào ticket, Git hay thư mục chia sẻ |
| Ghi nhận truy cập | Ghi danh tính, thời điểm, tài nguyên và kết quả cần thiết; không ghi lại Authorization hoặc toàn bộ phần thân log |
| Dung lượng | Giới hạn tốc độ, số yêu cầu và ngân sách truyền dữ liệu để tránh ảnh hưởng ứng dụng |

Spring Security có hỗ trợ header kiểm soát cache mặc định. Cần xác minh phản hồi cuối cùng vẫn có chính sách không lưu phù hợp, thường gồm `Cache-Control: no-store`; không để CDN hoặc reverse proxy ghi đè thành cache công khai. Header này cũng không ngăn người đã tải chủ động sao chép tệp. [Spring Security: Cache Control](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html#servlet-headers-cache-control).

Đổi cổng quản trị, đổi tên đường dẫn hoặc giới hạn CORS không thay thế xác thực và phân quyền. Đặc biệt, CORS không ngăn một máy khách như curl gọi trực tiếp nếu đường truy cập và quyền phía máy chủ đang mở.

## 7. Chẩn đoán các kết quả thường gặp

| Hiện tượng | Kiểm tra trước |
| --- | --- |
| Không tìm được endpoint hoặc nhận `404` | Đúng địa chỉ/base path chưa; endpoint có được bật, expose và có tệp nguồn đọc được không |
| `401` | Thông tin xác thực có được gửi và chấp nhận không |
| `403` khi GET | Danh tính đã xác thực có đúng vai trò và khớp đúng chính sách truy cập không |
| `200` dù đã gửi Range | Header có tới ứng dụng không; bộ xử lý có hỗ trợ không; có proxy biến đổi yêu cầu/phản hồi không |
| `206` nhưng chữ bị lỗi ở đầu/cuối | Khoảng có cắt giữa ký tự UTF-8 hoặc giữa dòng không |
| `416` | Offset có ở/vượt cuối tệp không; tệp có bị cắt ngắn, thay thế hay xoay vòng không |
| Nội dung không phải tệp mong đợi | `external-file`, cấu hình logging, thư mục làm việc và instance đang được gọi |
| Log mới chưa xuất hiện | Bộ ghi đã đẩy dữ liệu ra tệp chưa; có đang đọc đúng tệp/instance không |

Một mã lỗi không đủ để kết luận duy nhất nguyên nhân. Chuỗi lọc bảo mật có thể chặn yêu cầu trước khi Actuator xử lý, và cách xử lý lỗi của ứng dụng có thể thay đổi phản hồi cuối cùng.

Trong hệ thống có nhiều instance sau bộ cân bằng tải, hai yêu cầu liên tiếp có thể đọc hai tệp khác nhau. Không mang offset của instance A sang instance B rồi ghép dữ liệu; phải xác định được nguồn log hoặc dùng nền tảng tập trung có mô hình truy vấn phù hợp.

## 8. Bài thực hành tự kiểm tra

1. Trên tệp 17 byte, gửi `Range: bytes=0-4`. Dự đoán mã trạng thái, `Content-Range` và số byte trước khi chạy.
2. Đổi thành `bytes=0-99`. Giải thích vì sao điểm cuối vượt tệp vẫn có thể trả dữ liệu hợp lệ.
3. Đọc `bytes=-6`, rồi so sánh “6 byte cuối” với “6 dòng cuối”.
4. Gửi yêu cầu không có mật khẩu. Xác nhận không có byte log nào bị trả về.
5. Trong một bản sao thí nghiệm riêng, thay nội dung tệp sau lần đọc đầu. Giải thích vì sao không được nối mù quáng các đoạn qua hai phiên bản tệp.
6. Kiểm tra ứng dụng có nơi nào ghi toàn bộ header hoặc request body không; xác định cách ngăn thông tin xác thực đi vào tệp ngay từ đầu.

Đối chiếu với tệp mẫu: câu 1 là `206`, `bytes 0-4/17`, 5 byte; câu 2 có thể trả `206`, `bytes 0-16/17`, 17 byte trên cấu hình MVC của bài; câu 3 trả `gamma` và LF. Với mọi lần tải, kết luận phải dựa trên mã HTTP, header và byte thực nhận.

Nắm được bài này nghĩa là bạn có thể chọn đúng khoảng byte, đọc đúng phản hồi, giữ offset gắn với đúng nguồn tệp và giải thích được vì sao quyền đọc log cùng chính sách dữ liệu vẫn là điều kiện bắt buộc dù chỉ tải một phần nhỏ.
