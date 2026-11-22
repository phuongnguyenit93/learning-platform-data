# SPRING_APPLICATION_JSON và vị trí của nguồn JSON trong thứ tự ưu tiên

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot thường nhận cấu hình từ nhiều nơi: `application.yml`, biến môi trường của hệ điều hành, thuộc tính JVM (`-D...`) và tham số dòng lệnh (`--...`). Cùng một khóa có thể xuất hiện ở nhiều nguồn, chẳng hạn `server.port` được khai báo trong tệp nhưng lại được đặt giá trị khác khi triển khai.

`SPRING_APPLICATION_JSON` cho phép truyền **nhiều thuộc tính cấu hình dưới dạng một chuỗi JSON** ngay khi khởi chạy ứng dụng. Spring Boot đọc chuỗi này, chuyển các trường JSON thành các khóa cấu hình có cấu trúc và thêm chúng vào `Environment` dưới dạng một nguồn thuộc tính (`PropertySource`).

Hai câu hỏi quan trọng là: JSON được chuyển thành các khóa nào và **giá trị JSON thắng hay thua những nguồn cấu hình khác**? Hiểu được hai điều này giúp dự đoán chính xác giá trị ứng dụng nhận khi cùng một khóa xuất hiện ở nhiều nơi.

## 2. SPRING_APPLICATION_JSON là gì?

Ví dụ biến môi trường sau chứa hai nhóm cấu hình:

```bash
export SPRING_APPLICATION_JSON='{"server":{"port":9090},"demo":{"message":"xin chào","retries":4}}'
java -jar app.jar
```

Spring Boot có thể truy cập các khóa tương đương:

| Khóa cấu hình | Giá trị nhận được |
| --- | --- |
| `server.port` | `9090` |
| `demo.message` | `xin chào` |
| `demo.retries` | `4` |

Đối tượng JSON lồng nhau được trải phẳng thành đường dẫn thuộc tính, ví dụ `demo.message`. Giá trị sau đó có thể được đọc qua `Environment`, `@Value` hoặc liên kết vào một lớp `@ConfigurationProperties`. JSON là **một nguồn cấu hình**, không phải tên của một tệp mà Spring Boot tự động tìm trên ổ đĩa.

Spring Boot còn có thể nhận chuỗi JSON qua thuộc tính hệ thống `spring.application.json`, đối số `--spring.application.json=...` hoặc mục JNDI phù hợp ở môi trường có JNDI. Dù chuỗi JSON được đưa vào bằng cách nào, các thuộc tính được trích xuất từ nó thuộc **nguồn JSON có vị trí ưu tiên riêng**, không đơn giản kế thừa độ ưu tiên của cách truyền chuỗi.

Ví dụ dùng tham số JVM:

```bash
java -Dspring.application.json='{"demo":{"message":"từ JSON"}}' -jar app.jar
```

Ở đây `-Dspring.application.json` cung cấp **toàn bộ chuỗi JSON**; khóa `demo.message` được tạo ra từ nội dung JSON. Cần phân biệt điều đó với `-Ddemo.message=...`, vốn tạo trực tiếp một thuộc tính JVM thông thường.

## 3. Vị trí của JSON trong thứ tự ưu tiên

Khi nhiều `PropertySource` cùng chứa một khóa, nguồn có **độ ưu tiên cao hơn** quyết định giá trị có hiệu lực. Đối với các nguồn thường gặp khi chạy Spring Boot 3.x, thứ tự từ cao xuống thấp là:

| Mức ưu tiên | Nguồn | Ví dụ cùng đặt `demo.message` |
| --- | --- | --- |
| 1 — cao nhất trong bảng | Đối số dòng lệnh | `--demo.message=cli` |
| 2 | Nguồn JSON của Spring Boot | `SPRING_APPLICATION_JSON='{"demo":{"message":"json"}}'` |
| 3 | Thuộc tính hệ thống Java | `-Ddemo.message=system` |
| 4 | Biến môi trường hệ điều hành | `DEMO_MESSAGE=env` |
| 5 — thấp nhất trong bảng | Dữ liệu cấu hình | `demo.message=file` trong `application.yml` |

**Quan hệ cần nhớ:**

```text
Đối số dòng lệnh
        > SPRING_APPLICATION_JSON
        > thuộc tính JVM (-D...)
        > biến môi trường thông thường
        > application.yml / application.properties
```

Dấu `>` nghĩa là “có độ ưu tiên cao hơn”. Bảng này chỉ tập trung vào **năm nguồn thường gặp**, không phải danh mục toàn bộ nguồn mà Spring Boot hỗ trợ. Trong ứng dụng web hoặc khi chạy kiểm thử còn có các nguồn khác như tham số khởi tạo Servlet, JNDI, các nguồn thuộc tính dành cho kiểm thử và cấu hình DevTools. Cấu hình theo hồ sơ, chẳng hạn `application-prod.yml`, vẫn thuộc nhóm dữ liệu cấu hình; các quy tắc ưu tiên **bên trong nhóm tệp cấu hình** là một chủ đề riêng.

Một trường hợp cần chú ý: nếu ứng dụng chủ động tắt việc thêm thuộc tính dòng lệnh vào `Environment`, ví dụ bằng `SpringApplication.setAddCommandLineProperties(false)`, thì không thể áp dụng nguyên xi dòng ưu tiên dành cho `--demo.message=...`.

## 4. Thử nghiệm: nhiều nguồn cùng đặt một khóa

Giả sử `src/main/resources/application.yml` chứa:

```yaml
demo:
  message: "file"
  retries: 1
```

Để quan sát giá trị khi ứng dụng chạy, có thể thêm thành phần minh họa sau:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DemoConfigurationPrinter implements ApplicationRunner {
    private final Environment environment;

    public DemoConfigurationPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("demo.message = "
                + environment.getProperty("demo.message"));
        System.out.println("demo.retries = "
                + environment.getProperty("demo.retries", Integer.class));
    }
}
```

Sau khi đóng gói ứng dụng thành `app.jar`, chạy trong Bash hoặc một shell tương thích POSIX:

```bash
DEMO_MESSAGE=env \
SPRING_APPLICATION_JSON='{"demo":{"message":"json","retries":4}}' \
java -Ddemo.message=system -jar app.jar --demo.message=cli
```

Kết quả đáng chú ý từ phần in cấu hình:

```text
demo.message = cli
demo.retries = 4
```

Giải thích theo từng khóa:

- `demo.message` có ở cả năm nguồn. Đối số `--demo.message=cli` ưu tiên cao nhất trong ví dụ nên giá trị là `cli`.
- `demo.retries` chỉ được khai báo trong tệp cấu hình và trong JSON. Nguồn JSON có ưu tiên cao hơn tệp nên kết quả là `4`.
- Nếu bỏ riêng đối số `--demo.message=cli`, `demo.message` sẽ là `json`; nó **không** trở về `system` hoặc `env` vì JSON vẫn đang có hiệu lực.
- Nếu sau đó bỏ `SPRING_APPLICATION_JSON`, `-Ddemo.message=system` sẽ thắng biến `DEMO_MESSAGE` và tệp cấu hình.

Dấu `\` ở cuối dòng trong ví dụ Bash có tác dụng nối các dòng lệnh cho dễ đọc. Có thể viết tất cả trên một dòng. Khi sử dụng Windows PowerShell, đặt biến môi trường theo cú pháp PowerShell:

```powershell
$env:SPRING_APPLICATION_JSON = '{"demo":{"message":"json","retries":4}}'
java -jar app.jar
Remove-Item Env:SPRING_APPLICATION_JSON
```

Lệnh `Remove-Item` xóa biến khỏi phiên PowerShell hiện tại sau khi thử nghiệm. Cách đặt dấu nháy khác nhau giữa Bash, PowerShell, CMD, Docker và trình khai báo biến môi trường trên nền tảng triển khai; cần bảo đảm **giá trị thực tế đến ứng dụng là một chuỗi JSON hợp lệ**.

## 5. Spring Boot đọc và liên kết JSON như thế nào?

Xét cấu hình:

```json
{
  "demo": {
    "message": "hello",
    "retry": {
      "max-attempts": 3
    },
    "servers": ["alpha", "beta"]
  }
}
```

Các đường dẫn có thể được biểu diễn dưới dạng `demo.message`, `demo.retry.max-attempts`, `demo.servers[0]` và `demo.servers[1]`. Bộ liên kết cấu hình (`Binder`) của Spring Boot có thể chuyển chúng sang các kiểu Java phù hợp.

Ví dụ một cấu hình có kiểu:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String message,
        Retry retry
) {
    public record Retry(int maxAttempts) {}
}
```

Có thể kích hoạt cơ chế quét lớp `@ConfigurationProperties` qua `@ConfigurationPropertiesScan` ở lớp ứng dụng. Khi dùng ví dụ này, trường JSON `max-attempts` được liên kết với thành phần Java `maxAttempts` theo quy tắc liên kết tên thuộc tính của Spring Boot.

Điều quan trọng: cơ chế liên kết và thứ tự ưu tiên **là hai công đoạn khác nhau**. Trước tiên Spring Boot chọn giá trị có hiệu lực cho từng khóa theo các nguồn cấu hình; sau đó ứng dụng đọc hoặc liên kết các giá trị đó vào đối tượng Java.

Đừng mặc định các danh sách khai báo ở nhiều nguồn sẽ tự nối phần tử. Với cấu hình danh sách, cần kiểm tra quy tắc ghi đè của Binder cho trường hợp cụ thể.

## 6. Trường hợp đặc biệt: giá trị JSON null

Một chi tiết dễ gây nhầm lẫn là `null` trong JSON **không xóa giá trị ở nguồn có ưu tiên thấp hơn**.

Giả sử `application.yml` có:

```yaml
demo:
  message: "từ tệp"
```

Và biến môi trường là:

```bash
export SPRING_APPLICATION_JSON='{"demo":{"message":null}}'
```

Khi ứng dụng gọi `environment.getProperty("demo.message")`, thuộc tính có thể vẫn nhận giá trị `từ tệp`. Lý do: bộ phân giải thuộc tính xem giá trị `null` từ nguồn JSON như **không có giá trị có thể sử dụng** cho khóa ấy, nên tiếp tục tìm ở nguồn có mức ưu tiên thấp hơn.

Phân biệt ba trạng thái:

| Trường hợp | Ý nghĩa khi phân giải thuộc tính |
| --- | --- |
| JSON không chứa `demo.message` | Tìm ở nguồn khác |
| JSON chứa `"message": null` | Vẫn có thể tìm thấy giá trị ở nguồn thấp hơn |
| JSON chứa `"message": ""` | Chuỗi rỗng là một giá trị được cung cấp; tác động khi liên kết phụ thuộc kiểu đích |

Vì vậy không dùng `null` trong `SPRING_APPLICATION_JSON` để “xóa” một cấu hình ở `application.yml`. Nếu muốn tắt một tính năng, nên chọn cách biểu diễn mà ứng dụng thực sự hỗ trợ, ví dụ `demo.enabled=false`, và xử lý giá trị đó rõ ràng trong mã ứng dụng.

## 7. Khi nào dùng JSON, khi nào dùng nguồn khác?

`SPRING_APPLICATION_JSON` hữu ích khi môi trường triển khai cho phép truyền một biến cấu hình duy nhất nhưng ứng dụng cần nhiều khóa lồng nhau. Nó cũng thuận tiện cho chạy thử nhanh một tổ hợp giá trị mà không sửa `application.yml` hoặc tạo thêm tệp cấu hình.

Tuy nhiên, các lựa chọn có vai trò khác nhau:

| Cách cấu hình | Phù hợp khi |
| --- | --- |
| `application.yml` hoặc `application.properties` | Cấu hình mặc định có cấu trúc, dễ đọc và quản lý cùng ứng dụng |
| Biến môi trường riêng lẻ như `SERVER_PORT` | Cần ghi đè một vài giá trị khi triển khai |
| `SPRING_APPLICATION_JSON` | Cần truyền một nhóm thuộc tính có cấu trúc trong một giá trị JSON |
| `--server.port=...` | Cần ghi đè trực tiếp cho một lần khởi chạy |
| `spring.config.import` | Cần nạp thêm nguồn dữ liệu cấu hình bằng cơ chế config data |

Không nên nhầm `SPRING_APPLICATION_JSON` với `spring.config.import`: một bên **chứa trực tiếp các giá trị JSON**, bên kia **chỉ định nguồn cấu hình bổ sung cần nạp**. Đặt đường dẫn tệp vào `SPRING_APPLICATION_JSON` không khiến Spring Boot tự hiểu đó là nội dung một tệp JSON.

Với mật khẩu, khóa API và thông tin nhạy cảm, hãy cân nhắc cơ chế quản lý bí mật của nền tảng triển khai. Biến môi trường và tham số khởi chạy vẫn có thể bị lộ qua công cụ giám sát tiến trình, lịch sử lệnh, nhật ký hoặc cấu hình triển khai nếu quản lý không cẩn thận. Không in toàn bộ `Environment` chỉ để kiểm tra một thuộc tính.

## 8. Chẩn đoán khi kết quả khác dự đoán

Khi một khóa nhận giá trị bất ngờ, hãy kiểm tra theo trình tự:

1. **Khóa thực sự được đọc** là gì? Ví dụ `demo.message` khác `demo.messages`; tên biến môi trường `DEMO_MESSAGE` được ánh xạ theo quy tắc liên kết thuộc tính.
2. **Chuỗi JSON có hợp lệ không?** JSON chuẩn yêu cầu nháy kép cho tên trường và chuỗi, không chấp nhận dấu phẩy dư ở cuối đối tượng.
3. **Có nguồn ưu tiên cao hơn không?** Một tham số `--demo.message=...` có thể che giá trị JSON dù JSON đã được nạp thành công.
4. **Giá trị JSON có phải `null` không?** Nếu có, khóa có thể nhận giá trị của nguồn thấp hơn.
5. **Shell có truyền đúng chuỗi không?** Dấu nháy bị xử lý sai có thể làm chuỗi JSON bị biến đổi trước khi đến JVM.
6. **Ứng dụng có tự thay đổi nguồn thuộc tính không?** Mã khởi tạo có thể thêm nguồn cấu hình hoặc tắt việc sử dụng thuộc tính dòng lệnh.

Trong môi trường phát triển được kiểm soát, Spring Boot Actuator có endpoint `env` giúp xem thông tin về nguồn thuộc tính nếu endpoint này được cấu hình cho phép truy cập. Hãy hạn chế truy cập và tránh lộ dữ liệu cấu hình nhạy cảm. Cách kiểm chứng đơn giản nhất cho một bài thử nhỏ vẫn là in **đúng khóa cần kiểm tra** qua `Environment#getProperty`.

## 9. Bài tập tự kiểm tra

Cho bốn nguồn cấu hình sau cùng tồn tại:

```yaml
# application.yml
demo:
  color: blue
  retries: 2
```

```text
Biến môi trường thường: DEMO_COLOR=green
Thuộc tính JVM:        -Ddemo.color=yellow
SPRING_APPLICATION_JSON={"demo":{"color":"red","retries":5}}
Đối số dòng lệnh:     --demo.color=black
```

Hãy dự đoán kết quả trước khi chạy:

| Trạng thái | `demo.color` | `demo.retries` |
| --- | --- | --- |
| Tất cả nguồn còn tồn tại | `black` | `5` |
| Bỏ đối số `--demo.color` | `red` | `5` |
| Bỏ tiếp nguồn JSON | `yellow` | `2` |
| Bỏ tiếp thuộc tính JVM | `green` | `2` |
| Bỏ tiếp biến môi trường | `blue` | `2` |

Bài tập giúp rút ra nguyên tắc: **thứ tự ưu tiên được áp dụng theo từng khóa**, không phải chọn một nguồn cho toàn bộ đối tượng cấu hình. JSON có thể thắng ở `demo.retries` trong khi đối số dòng lệnh lại thắng ở `demo.color`.

## 10. Điều cần ghi nhớ

- `SPRING_APPLICATION_JSON` chứa **chuỗi JSON**, được Spring Boot chuyển thành các thuộc tính có tên phân cấp trong `Environment`.
- Với các nguồn triển khai thông thường ở Spring Boot 3.x: **đối số dòng lệnh > JSON > thuộc tính JVM > biến môi trường > dữ liệu cấu hình**.
- Khi truyền JSON qua `spring.application.json` của JVM hoặc dòng lệnh, các khóa được trích ra vẫn được xử lý trong **nguồn JSON** riêng.
- Một thuộc tính đặt thành JSON `null` không có nghĩa là xóa hay vô hiệu hóa giá trị của nguồn thấp hơn.
- Muốn biết cấu hình có hiệu lực, hãy xét **từng khóa**, kiểm tra cú pháp JSON và xem có nguồn nào ưu tiên cao hơn đang ghi đè hay không.
