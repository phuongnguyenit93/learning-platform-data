# Phân biệt endpoint chỉ cung cấp thông tin với endpoint thay đổi trạng thái

## 1. Từ quan sát đến điều khiển ứng dụng

Khi ứng dụng đang chạy, người vận hành có hai nhu cầu khác nhau: biết hệ thống đang như thế nào và chủ động làm cho hệ thống hoạt động khác đi. Xem mức ghi log hiện tại thuộc nhu cầu thứ nhất; đổi mức ghi log sang DEBUG thuộc nhu cầu thứ hai.

Trong Spring Boot Actuator, endpoint là một điểm quản trị có định danh, còn thao tác (operation) là hành động cụ thể được gọi trên điểm đó. Một endpoint có thể chứa nhiều thao tác. Vì vậy, cần xét **từng thao tác và tác động của nó**, thay vì gắn nhãn toàn bộ endpoint là “chỉ đọc” chỉ dựa vào tên.

Trong bài này, “trạng thái” bao gồm cả giá trị cấu hình đang có hiệu lực, dữ liệu tạm trong bộ nhớ, bộ đệm chẩn đoán và vòng đời ứng dụng. Thay đổi trạng thái không nhất thiết là cập nhật cơ sở dữ liệu hay sửa tệp cấu hình.

| Tiêu chí | Thao tác cung cấp thông tin | Thao tác thay đổi trạng thái |
| --- | --- | --- |
| Câu hỏi chính | Hiện tại hệ thống đang ra sao? | Hệ thống cần được điều chỉnh thế nào? |
| Mục đích | Quan sát, kiểm tra, chẩn đoán | Ra lệnh, cập nhật, xóa hoặc kích hoạt hành động quản trị |
| Ví dụ | Xem mức ghi log của một logger | Đặt mức ghi log mới cho logger đó |
| Bằng chứng cần xem | Dữ liệu trả về và phạm vi dữ liệu được quan sát | Giá trị trước/sau, tác động thật và cách khôi phục nếu có |
| Rủi ro cần đánh giá | Lộ thông tin, chi phí thu thập dữ liệu | Các rủi ro của việc đọc, cộng thêm thay đổi hành vi hoặc gián đoạn dịch vụ |

Ví dụ: việc đọc một biến `enabled` không đổi giá trị của nó. Việc gán `enabled = true` là thay đổi trạng thái dù không tạo một bản ghi dữ liệu nào.

## 2. Quan hệ giữa annotation, HTTP và hành vi thực tế

Với endpoint dùng `@Endpoint` và được công bố qua HTTP, Actuator ánh xạ loại thao tác như sau:

| Annotation | Phương thức HTTP | Vai trò dự kiến |
| --- | --- | --- |
| `@ReadOperation` | `GET` | Cung cấp thông tin |
| `@WriteOperation` | `POST` | Thay đổi trạng thái hoặc thực hiện lệnh |
| `@DeleteOperation` | `DELETE` | Xóa hoặc loại bỏ trạng thái theo hợp đồng đã thiết kế |

Ánh xạ này thuộc mô hình endpoint Actuator, không phải quy tắc rằng mọi API REST phải dùng POST để cập nhật. Với JMX, thao tác được gọi qua cơ chế quản trị JMX; không có phương thức HTTP.

Annotation giúp framework định tuyến lời gọi. Nó không tự ngăn thân phương thức đọc ghi dữ liệu, không làm phương thức ghi có giao dịch và không tự cấp quyền quản trị. Người viết vẫn chịu trách nhiệm bảo đảm hành vi đúng với hợp đồng.

Ví dụ lỗi thiết kế: một phương thức `@ReadOperation` trả về số phần tử nhưng đồng thời gọi `queue.clear()`. Dù được gọi bằng GET, nó đang xóa trạng thái. Một công cụ giám sát đọc định kỳ có thể vô tình làm mất dữ liệu. Cần tách việc lấy số liệu và việc xóa thành hai thao tác riêng.

Xem [mô hình thao tác và ánh xạ HTTP của Actuator 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

## 3. Nhận diện qua các endpoint có sẵn

| Endpoint / lời gọi | Phân loại thao tác | Điều cần nhận ra |
| --- | --- | --- |
| `GET /actuator/loggers/{name}` | Đọc | Xem cấu hình và mức ghi log đang có hiệu lực |
| `POST /actuator/loggers/{name}` | Ghi | Đặt hoặc xóa mức ghi log được cấu hình riêng |
| `GET /actuator/startup` | Đọc | Lấy ảnh chụp các bước khởi động đã thu thập |
| `POST /actuator/startup` | Ghi | Lấy dữ liệu và rút các sự kiện đã lấy khỏi bộ đệm |
| `POST /actuator/shutdown` | Ghi | Yêu cầu dừng ứng dụng |
| `GET /actuator/heapdump` | Đọc dữ liệu chẩn đoán | Lấy bản chụp heap; dữ liệu có thể lớn |

### 3.1. `loggers`: cùng một đường dẫn, khác ý nghĩa

GET trả lời “logger này đang có mức nào?”. POST với thuộc tính JSON `configuredLevel` thay đổi mức riêng của logger. Sau đó, các lần ghi log mới có thể chịu tác động của cấu hình vừa đặt.

`configuredLevel` là mức được đặt trực tiếp, còn `effectiveLevel` là mức thực sự áp dụng, có thể được kế thừa. Xóa mức riêng bằng POST với `{}` có nghĩa là quay về cơ chế kế thừa; không có nghĩa là khôi phục chắc chắn về INFO. [Hợp đồng REST của endpoint loggers](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

### 3.2. `startup`: có JSON trả về vẫn có thể là thao tác ghi

GET lấy ảnh chụp dữ liệu khởi động. POST vừa trả về các bước đã thu thập vừa rút chúng khỏi bộ đệm. Một phản hồi trông giống dữ liệu báo cáo vẫn có thể đi kèm thay đổi trạng thái.

Endpoint này cần ứng dụng được cấu hình thu thập bước khởi động bằng `BufferingApplicationStartup`; chỉ thêm tên endpoint vào danh sách công bố chưa đủ. Bài này dùng nó để phân biệt hành vi, không giả định endpoint luôn hiện diện trong mọi ứng dụng. [GET và POST của endpoint startup](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html).

### 3.3. `shutdown`: trạng thái bị thay đổi có thể là vòng đời

POST tới endpoint này yêu cầu dừng ứng dụng. Không có yêu cầu phải thay đổi một bảng dữ liệu thì mới được coi là thao tác ghi. Phản hồi thành công cũng không bảo đảm ứng dụng còn phục vụ được các yêu cầu tiếp theo. [Hợp đồng endpoint shutdown](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html).

### 3.4. `heapdump`: thao tác đọc vẫn cần kiểm soát

Endpoint trả về dữ liệu nhị phân của heap, có thể có kích thước lớn. Vì heap chứa các đối tượng đang nằm trong bộ nhớ, cần đánh giá khả năng lộ dữ liệu ứng dụng khi chia sẻ bản chụp. Việc tạo và truyền bản chụp cũng cần được đánh giá về tài nguyên; không nên đưa lời gọi này vào chu kỳ thăm dò dày chỉ vì nó dùng GET. Nhận định về dữ liệu nhạy cảm và chi phí vận hành ở đây là hệ quả cần đánh giá từ việc thu thập heap, không phải cam kết về một thời gian tạm dừng cố định của mọi JVM. [Dữ liệu trả về của endpoint heapdump](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html).

## 4. “Chỉ đọc”, an toàn và tính lũy đẳng

Trong ngữ nghĩa HTTP, tính an toàn (safe) nói về việc bên gọi không yêu cầu thay đổi trạng thái. Nó không có nghĩa là máy chủ không làm gì: một lần đọc vẫn có thể tạo bản ghi truy cập hoặc tiêu tốn tài nguyên. Tính lũy đẳng (idempotent) nói về tác động dự kiến khi thực hiện lặp lại cùng yêu cầu. [RFC 9110, mục 9.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2).

Có thể dùng các tình huống sau để tách hai khái niệm:

- Đọc cờ `enabled`: hai lần đọc liên tiếp không có mục đích đổi cờ. Giá trị trả về vẫn có thể khác nếu một tác nhân khác cập nhật cờ giữa hai lần.
- Đặt `enabled` thành `true`: hai lần gán cùng giá trị có thể cho cùng trạng thái cuối, nhưng đây vẫn là thao tác ghi.
- Đảo cờ bằng `enabled = !enabled`: gọi hai lần đưa cờ về giá trị cũ. Tự động thử lại khi không rõ lần đầu đã thực hiện chưa có thể tạo kết quả ngoài ý muốn.
- Xóa một cấu hình riêng: gọi lại có thể không làm thay đổi thêm trạng thái, nhưng điều đó không biến việc xóa thành thao tác đọc.

Các ví dụ về gán và đảo cờ là phân tích hành vi của chương trình, không phải bảo đảm chung cho mọi POST. Với thao tác quản trị, phải xét cả tính lặp lại, tác động phụ và tình huống nhiều bên gọi cùng lúc.

## 5. Thực nghiệm: một endpoint có cả đọc, ghi và đặt lại

Ví dụ nhỏ sau chạy với Java 21 và Spring Boot 3.3.0. Dự án độc lập dùng Maven để người học có thể sao chép và chạy đủ các tệp; cùng nguyên tắc áp dụng khi ứng dụng Boot được xây dựng bằng Gradle.

Endpoint `maintenance` giữ một cờ trong bộ nhớ của một tiến trình. Cờ này chỉ phục vụ thí nghiệm; nó chưa chặn yêu cầu nghiệp vụ hay đưa ứng dụng vào chế độ bảo trì thật. Khởi động lại ứng dụng sẽ tạo cờ mới có giá trị `false`.

### 5.1. Tạo dự án đầy đủ

Cấu trúc thư mục:

```text
actuator-operation-demo/
├── pom.xml
└── src/main/
    ├── java/example/demo/
    │   ├── EndpointDemoApplication.java
    │   └── MaintenanceEndpoint.java
    └── resources/
        └── application.properties
```

Tệp `pom.xml`:

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
    <artifactId>actuator-operation-demo</artifactId>
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
```

Tệp `src/main/java/example/demo/EndpointDemoApplication.java`:

```java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EndpointDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EndpointDemoApplication.class, args);
    }
}
```

Tệp `src/main/java/example/demo/MaintenanceEndpoint.java`:

```java
package example.demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "maintenance")
public class MaintenanceEndpoint {
    private final AtomicBoolean enabled = new AtomicBoolean(false);

    @ReadOperation
    public Map<String, Boolean> read() {
        return Map.of("enabled", enabled.get());
    }

    @WriteOperation
    public void write(boolean enabled) {
        this.enabled.set(enabled);
    }

    @DeleteOperation
    public void reset() {
        this.enabled.set(false);
    }
}
```

`read()` chỉ lấy giá trị. `write(boolean enabled)` gán giá trị được yêu cầu. `reset()` loại bỏ trạng thái tùy chỉnh bằng cách đặt cờ về mặc định `false`; đó là ý nghĩa DELETE do ví dụ này định nghĩa, không phải một quy tắc rằng DELETE luôn phải gán `false`.

`AtomicBoolean` giúp việc đọc và gán một cờ có khả năng hiển thị phù hợp giữa các luồng. Nó không giải quyết giao dịch nhiều bước, phân quyền, lưu trữ bền vững hoặc đồng bộ nhiều bản sao ứng dụng.

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,maintenance
management.endpoint.maintenance.cache.time-to-live=0ms
```

Mẫu không thêm Spring Security và chỉ lắng nghe trên loopback để thực nghiệm trên máy cá nhân. Cấu hình không công bố mọi endpoint. `cache.time-to-live=0ms` làm rõ ý định không giữ bản kết quả đọc cũ trong thí nghiệm.

Đầu vào JSON `enabled` được ánh xạ vào tham số cùng tên của phương thức ghi. Thông tin tên tham số cần được giữ khi biên dịch (`-parameters`); cấu hình Maven dùng `spring-boot-starter-parent` đã chuẩn bị việc này.

### 5.2. Khởi động và gọi tuần tự

Chọn JDK 21 cho `JAVA_HOME`, kiểm tra `java -version` và `mvn -version`, rồi chạy tại thư mục chứa `pom.xml`:

```shell
mvn spring-boot:run
```

Mở một cửa sổ dòng lệnh khác và gọi lần lượt các lệnh dưới đây. Trên PowerShell Windows, dùng `curl.exe` thay cho `curl` nếu tên `curl` đang là bí danh. Các lệnh không chứa JSON nên không phụ thuộc cách shell xử lý dấu nháy của JSON.

**Bước 1 — đọc trạng thái ban đầu:**

```shell
curl -sS http://127.0.0.1:8080/actuator/maintenance
```

Nội dung phản hồi:

```json
{"enabled":false}
```

Lặp lại GET vẫn thấy `false` nếu không có tác nhân khác cập nhật. Không nên chỉ so sánh hai phản hồi khác nhau rồi kết luận thao tác đọc đã ghi dữ liệu.

**Bước 2 — yêu cầu đổi cờ:**

```shell
curl -i -X POST -H "Content-Type: application/json" "http://127.0.0.1:8080/actuator/maintenance?enabled=true"
```

Trong cấu hình ví dụ, Actuator nhận tham số đơn giản từ query string và gọi `write(true)`. Header `Content-Type: application/json` đáp ứng điều kiện nhận dữ liệu của thao tác POST này, kể cả khi ví dụ truyền tham số qua URL. Phản hồi có mã `204 No Content`, không có nội dung thân vì phương thức Java trả về `void`. Các header phụ thuộc máy chủ nên không cần giống nhau từng byte.

Cũng có thể truyền giá trị qua JSON với `Content-Type: application/json` và thân `{"enabled":true}`. Cả hai cách đều là POST và đều yêu cầu thay đổi cờ; vị trí của tham số không quyết định đây là thao tác đọc hay ghi.

**Bước 3 — đọc lại để xác nhận tác động:**

```shell
curl -sS http://127.0.0.1:8080/actuator/maintenance
```

Nội dung phản hồi:

```json
{"enabled":true}
```

**Bước 4 — đặt lại trạng thái:**

```shell
curl -i -X DELETE http://127.0.0.1:8080/actuator/maintenance
curl -sS http://127.0.0.1:8080/actuator/maintenance
```

DELETE trả mã `204 No Content`; GET sau đó trả:

```json
{"enabled":false}
```

**Bước 5 — kiểm tra đầu vào không hợp lệ:**

```shell
curl -i -X POST -H "Content-Type: application/json" http://127.0.0.1:8080/actuator/maintenance
```

Vì thiếu tham số bắt buộc `enabled`, phản hồi là `400 Bad Request`; phương thức `write` không được gọi. Gọi GET để xác nhận cờ vẫn là `false` sau chuỗi thao tác trên. Không cần dựa vào một cấu trúc JSON báo lỗi cố định vì cấu trúc đó có thể thay đổi theo xử lý lỗi của ứng dụng.

Khi kết thúc, dừng ứng dụng bằng Ctrl+C tại cửa sổ đang chạy Maven.

### 5.3. Đọc kết quả theo tác động

| Lời gọi theo thứ tự | Giá trị cờ trước → sau | Kết quả chính |
| --- | --- | --- |
| GET | `false` → `false` | `200`, trả `{"enabled":false}` |
| POST với `enabled=true` | `false` → `true` | `204`, không có thân phản hồi |
| GET | `true` → `true` | `200`, trả `{"enabled":true}` |
| DELETE | `true` → `false` | `204`, không có thân phản hồi |
| POST thiếu `enabled` | `false` → `false` | `400`, chưa thực hiện phương thức ghi |

Phản hồi rỗng không có nghĩa là không có tác động: POST và DELETE trong ví dụ đều trả `204` nhưng đã đổi cờ. Ngược lại, trả một đối tượng JSON cũng không chứng minh thao tác chỉ đọc, như trường hợp POST của `startup`.

## 6. Áp dụng vào cấu hình vận hành

Trong Boot 3.3, `enabled` quyết định endpoint có được bật; cấu hình `exposure` quyết định công bố qua HTTP/JMX. Chỉ `health` được công bố mặc định qua hai kênh này; `shutdown` bị tắt mặc định. Bật hoặc công bố endpoint không thay thế việc xác thực và phân quyền. Nếu có Spring Security, các yêu cầu ghi còn chịu kiểm tra CSRF theo cấu hình bảo mật. [Cấu hình và bảo mật endpoint trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Khi quyết định cấp quyền, nên bắt đầu từ nhu cầu thực tế:

1. Công cụ giám sát cần những dữ liệu nào và có cần dữ liệu chi tiết không?
2. Người trực vận hành cần những lệnh nào, phạm vi tác động đến một tiến trình hay cả hệ thống?
3. Sau lệnh ghi, cách kiểm tra tác động và cách khôi phục là gì?
4. Lệnh có thể bị gọi lại do hết thời gian chờ, hoặc được gọi đồng thời, thì điều gì xảy ra?

Với endpoint có cả đọc và ghi như `loggers`, việc cho một nhóm quyền xem chưa có nghĩa nhóm đó cần quyền đổi mức log. Chính sách nên phân biệt thao tác. Đây là định hướng thiết kế quyền; danh sách `exposure.include` tự nó không biểu đạt đầy đủ chính sách đọc/ghi.

Các mã lỗi cũng cần được hiểu theo ngữ cảnh. `404` có thể do endpoint chưa được công bố hoặc đường dẫn không khớp; `401`/`403` có thể liên quan xác thực, phân quyền hoặc CSRF; `400` có thể do đầu vào không hợp lệ; `415` có thể do `Content-Type` không được chấp nhận. Một mã lỗi đơn lẻ chưa đủ chứng minh endpoint là chỉ đọc hay có khả năng ghi. Phải đối chiếu cấu hình và hợp đồng thao tác.

## 7. Lỗi thường gặp và cách sửa

| Hiểu sai | Cách kiểm tra hoặc sửa |
| --- | --- |
| “Actuator chỉ để xem thông tin” | Kiểm tra từng thao tác; có cả lệnh đổi cấu hình và lệnh quản lý vòng đời |
| “Tên endpoint trông như báo cáo thì không ghi” | Xem hợp đồng của từng phương thức; POST `startup` còn rút dữ liệu khỏi bộ đệm |
| “Có `@ReadOperation` thì framework cấm thay đổi dữ liệu” | Kiểm tra thân phương thức; annotation không bảo đảm tính thuần đọc |
| “Không sửa cơ sở dữ liệu thì không thay đổi trạng thái” | Kiểm tra cả bộ nhớ, cấu hình có hiệu lực, dữ liệu tạm và vòng đời |
| “Nhận 204 là chưa làm gì” | Dùng thao tác đọc hoặc bằng chứng quan sát khác để kiểm tra trạng thái sau lệnh |
| “Mọi thao tác ghi đều trả 204” | Trong ví dụ, 204 đi cùng phương thức trả `void`; thao tác có dữ liệu kết quả có thể trả 200 |
| “GET luôn nhẹ và có thể công khai” | Đánh giá riêng độ nhạy cảm dữ liệu và chi phí thu thập |
| “Gọi lại lệnh chắc chắn không sao” | Phân tích đặt giá trị, đảo giá trị, xóa và tác động phụ trước khi thêm cơ chế thử lại |
| “POST thành công thì mọi bản sao ứng dụng đều đổi” | Xác định nơi lưu trạng thái; cờ trong ví dụ chỉ nằm ở tiến trình nhận lệnh |

## 8. Tự kiểm tra

**Câu 1.** Một thao tác trả số phần tử trong hàng đợi rồi xóa các phần tử đó. Có thể xem là chỉ cung cấp thông tin không?

**Đáp án:** Không. Nó còn làm mất trạng thái đã tồn tại. Nếu cần đọc mà không làm mất dữ liệu, tách thao tác quan sát khỏi thao tác lấy và loại bỏ dữ liệu.

**Câu 2.** Hai lần đặt cờ thành `true` có cùng trạng thái cuối. Vì sao vẫn là thao tác ghi?

**Đáp án:** Bên gọi yêu cầu cập nhật giá trị. Việc lặp lại có thể cho cùng kết quả cuối liên quan tính lũy đẳng của hành vi được thiết kế; không làm thay đổi mục đích ghi.

**Câu 3.** Sau POST đổi cờ, GET trả một giá trị khác với trước. Cần kiểm tra gì trước khi kết luận thí nghiệm thành công?

**Đáp án:** Xác nhận gọi đúng tiến trình, đúng đường dẫn, không có tác nhân khác cập nhật, và không đọc một bản kết quả được lưu tạm. Ví dụ đặt thời gian lưu kết quả bằng 0 để làm rõ việc quan sát.

**Câu 4.** Một tài khoản chỉ cần xem mức log có nên được mặc nhiên cấp quyền đặt DEBUG không?

**Đáp án:** Không. Quan sát và điều khiển là hai nhu cầu quyền khác nhau. Quyền điều khiển có thể làm đổi khối lượng log và tác động đến việc vận hành.

**Câu 5.** Trong ví dụ, DELETE có xóa endpoint `maintenance` khỏi Actuator không?

**Đáp án:** Không. Nó gọi `reset()` để đặt cờ về `false`; endpoint vẫn tồn tại và GET vẫn dùng được. Ý nghĩa xóa do hợp đồng của thao tác quy định.
