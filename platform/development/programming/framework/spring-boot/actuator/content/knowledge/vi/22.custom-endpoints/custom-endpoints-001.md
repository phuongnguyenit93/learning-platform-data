# Khi nào nên tạo endpoint Actuator thay vì controller nghiệp vụ

## 1. Hai loại endpoint trả lời hai câu hỏi khác nhau

Một ứng dụng nhập dữ liệu có thể cần trả lời:

- “Lần nhập dữ liệu của khách hàng A đã hoàn tất chưa?”
- “Tiến trình xử lý nhập dữ liệu của bản ứng dụng này đang tạm dừng hay đang chạy?”

Câu hỏi đầu thuộc chức năng sản phẩm: dữ liệu gắn với một khách hàng, một lần nhập và quyền truy cập nghiệp vụ. Câu hỏi sau phục vụ vận hành: người trực hệ thống cần biết trạng thái của bộ phận đang chạy bên trong ứng dụng.

**Endpoint Actuator tùy chỉnh** là một khả năng giám sát hoặc quản lý ứng dụng được tích hợp vào cơ chế Actuator. Nó phù hợp khi cần quan sát hoặc điều khiển một khía cạnh vận hành chưa được các endpoint có sẵn đáp ứng.

**Controller nghiệp vụ** là lớp tiếp nhận yêu cầu của một ca sử dụng thuộc sản phẩm hoặc miền nghiệp vụ: đặt hàng, tra cứu đơn, nộp hồ sơ, xem kết quả nhập dữ liệu, duyệt hoàn tiền. Nó vẫn là API nghiệp vụ khi chỉ nhân viên nội bộ hoặc quản trị viên được gọi.

Cả hai có thể trả JSON qua HTTP. Vì vậy, việc “có một URL”, “dùng GET”, “trả trạng thái” hay “chỉ cho admin gọi” không tự quyết định loại endpoint.

Trong Spring Boot, Actuator cung cấp các endpoint để giám sát và tương tác với ứng dụng; xem [tổng quan endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 2. Hiểu đúng các lớp khái niệm

| Khái niệm | Ý nghĩa |
| --- | --- |
| Endpoint theo nghĩa HTTP thông thường | Điểm truy cập bằng tổ hợp URL, phương thức và hợp đồng yêu cầu/phản hồi |
| `@RestController` | Thành phần Spring MVC xử lý các yêu cầu web bằng cơ chế mapping của controller |
| `@Endpoint` | Định nghĩa một endpoint trong hệ thống Actuator, có định danh và các thao tác |
| `@ReadOperation` | Thao tác đọc của Actuator; khi được công bố qua web, được ánh xạ thành GET |
| `@WriteOperation` | Thao tác ghi của Actuator; khi được công bố qua web, được ánh xạ thành POST |
| Exposure | Cấu hình công bố endpoint qua một công nghệ như HTTP hoặc JMX |
| Phân quyền | Quyết định người hoặc hệ thống nào được phép gọi thao tác |

Một lớp có `@RestController` và `@GetMapping("/actuator/importworker")` vẫn là controller web thông thường. Đặt đường dẫn giống Actuator không tự đưa nó vào cơ chế phát hiện endpoint, cấu hình exposure hoặc cổng quản lý của Actuator.

Theo [hợp đồng của annotation Endpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html), endpoint Actuator được thiết kế để có thể thích ứng với nhiều công nghệ công bố, trong đó có HTTP và JMX. `@Endpoint` cũng không tự biến một đối tượng chưa được đăng ký thành Spring bean.

Đối với controller, [mô hình annotated controller của Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html) cung cấp mapping yêu cầu, xử lý đầu vào và ngoại lệ theo nhu cầu web. Đây là lựa chọn tự nhiên cho hợp đồng HTTP nghiệp vụ.

## 3. Tiêu chí quyết định: mục đích, dữ liệu và vòng đời

Bảng sau là hướng dẫn thiết kế, không phải danh sách điều kiện mà framework tự kiểm tra:

| Tiêu chí | Nghiêng về Actuator tùy chỉnh | Nghiêng về controller nghiệp vụ |
| --- | --- | --- |
| Câu hỏi chính | Ứng dụng đang vận hành như thế nào? | Người dùng muốn thực hiện hoặc tra cứu việc gì? |
| Đối tượng được mô tả | Bộ xử lý, tài nguyên nội bộ, trạng thái tiến trình | Đơn hàng, hồ sơ, lần nhập dữ liệu, khách hàng |
| Bên sử dụng | Công cụ vận hành, người trực hệ thống, công cụ chẩn đoán | Giao diện sản phẩm, đối tác, dịch vụ dùng ca nghiệp vụ |
| Phạm vi dữ liệu | Một bản ứng dụng hoặc thành phần kỹ thuật được xác định rõ | Dữ liệu theo khách hàng, tài khoản, tổ chức hoặc quyền sở hữu |
| Vòng đời hợp đồng | Gắn với khả năng vận hành và tài liệu xử lý sự cố | Gắn với tính năng, phiên bản API và cam kết với bên sử dụng |
| Đầu vào | Thao tác vận hành nhỏ, tham số có ý nghĩa rõ | Yêu cầu nghiệp vụ, kiểm tra hợp lệ, quy tắc và lỗi theo miền |
| Cách triển khai | Đọc trạng thái hoặc gọi khả năng quản lý qua một service | Gọi service của ca sử dụng và áp dụng chính sách nghiệp vụ |

Không nên dùng một dấu hiệu riêng lẻ để phân loại. Ví dụ, một dịch vụ khác gọi API nội bộ để tạo hóa đơn vẫn đang dùng chức năng nghiệp vụ. Một trang quản trị nội bộ để nhân viên duyệt đơn cũng thuộc sản phẩm.

Ngược lại, công cụ vận hành tra cứu xem một bộ tiêu thụ thông điệp đang tạm dừng do bảo trì hay do lỗi là trường hợp phù hợp để cân nhắc Actuator.

### 3.1. Ba câu hỏi trước khi chọn

1. **Nếu bỏ đội vận hành ra khỏi bài toán, chức năng này còn cần cho người dùng hoặc luồng nghiệp vụ không?** Nếu còn, nhiều khả năng đây là controller hoặc API quản trị nghiệp vụ.
2. **Dữ liệu đang mô tả thực thể nghiệp vụ hay trạng thái vận hành của ứng dụng?** Một “trạng thái đơn hàng” và một “trạng thái bộ xử lý đơn hàng” là hai hợp đồng khác nhau.
3. **Nhu cầu đã có điểm mở rộng phù hợp trong Actuator chưa?** Nếu đã có, hãy mở rộng khả năng đó trước khi tạo thêm endpoint.

Nếu yêu cầu trộn cả hai mục đích, nên tách thành hai hợp đồng có phạm vi rõ. Không trả cả danh sách dữ liệu khách hàng và trạng thái luồng xử lý trong cùng một endpoint chỉ vì chúng dùng chung một service phía dưới.

## 4. Trước khi tạo mới: dùng đúng khả năng có sẵn

Một yêu cầu vận hành chưa chắc cần một endpoint mới.

| Nhu cầu | Hướng đáp ứng nên xem trước |
| --- | --- |
| Ứng dụng hoặc một phụ thuộc có sẵn sàng phục vụ không? | Health và một `HealthIndicator` phù hợp |
| Thông tin phiên bản, bản dựng, mô tả triển khai | Info và một `InfoContributor` phù hợp |
| Số công việc chờ, thông lượng, thời gian xử lý, tỷ lệ lỗi | Metric qua Micrometer và hệ thống giám sát |
| Chỉnh mức log khi chẩn đoán | Endpoint loggers có sẵn |
| Xem hoặc quản lý cache được hỗ trợ | Endpoint caches có sẵn |
| Một ảnh chụp trạng thái vận hành đặc thù chưa có hợp đồng phù hợp | Endpoint Actuator tùy chỉnh |
| Tra cứu chi tiết một đơn hàng hoặc kết quả nhập của khách hàng | Controller nghiệp vụ |

Health trả lời câu hỏi về sức khỏe ứng dụng và có quy tắc tổng hợp trạng thái; một endpoint trả JSON tùy ý với trường `status` không tự tham gia cơ chế đó. Có thể mở rộng bằng `HealthIndicator` thay vì tạo `/actuator/myhealth` có nội dung tương tự.

Với chuỗi số liệu theo thời gian, ví dụ số công việc chờ mỗi phút hoặc phân vị thời gian xử lý, nên đo bằng metric. Việc công cụ giám sát liên tục gọi một endpoint JSON tự viết thường dẫn tới việc phải xây lại khả năng thu thập và tổng hợp đã có trong hệ thống metric. Xem [tích hợp metric của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Một endpoint chẩn đoán vẫn có thể trả ảnh chụp trạng thái hiện tại giúp người trực điều tra. Nó có mục đích khác với biểu đồ, cảnh báo và phân tích lịch sử của metric.

## 5. Các tình huống dễ phân loại nhầm

### 5.1. Tra cứu trạng thái một lần nhập dữ liệu

Yêu cầu: “Khách hàng đăng nhập, xem lần nhập của mình có bao nhiêu dòng thành công và tải các dòng lỗi.”

Đây là controller nghiệp vụ, chẳng hạn một hợp đồng dưới `/api/imports/{importId}`. Cần kiểm tra quyền sở hữu, cách phân trang hoặc tải kết quả, trạng thái nghiệp vụ và xử lý lỗi phù hợp. Nó không trở thành dữ liệu vận hành chỉ vì công việc được thực hiện bất đồng bộ.

### 5.2. Tra cứu bộ xử lý nhập dữ liệu

Yêu cầu: “Người trực muốn biết bản ứng dụng này có đang tạm dừng, có bao nhiêu worker hoạt động và còn bao nhiêu việc đang chờ.”

Có thể cân nhắc endpoint Actuator nếu một ảnh chụp chẩn đoán là cần thiết và các khả năng có sẵn chưa đáp ứng đủ. Nếu chỉ cần theo dõi số lượng việc chờ theo thời gian, ưu tiên metric.

Cần ghi rõ “bản ứng dụng này”. Khi hệ thống có nhiều bản chạy, dữ liệu trong bộ nhớ của một bản không tự trở thành tổng số của toàn bộ cụm.

### 5.3. Quản trị viên duyệt hoàn tiền

Dù chỉ quản trị viên được gọi, đây vẫn là thao tác nghiệp vụ: có quy tắc hoàn tiền, hạn mức, quyền phê duyệt và lịch sử quyết định. Dùng API quản trị nghiệp vụ với service thích hợp.

Việc gọi API này bằng công cụ dòng lệnh thay vì giao diện cũng không đổi bản chất của ca sử dụng.

### 5.4. Tạm dừng một bộ tiêu thụ để bảo trì

Đây có thể là thao tác vận hành phù hợp với Actuator, nếu phạm vi điều khiển rõ và service hỗ trợ an toàn. Cần xác định tạm dừng một bản chạy, một nhóm hay toàn bộ cụm; công việc đang chạy có được hoàn tất không; yêu cầu gọi lại có tạo hiệu ứng khác không.

Nếu thao tác thực chất là “hủy tất cả đơn của khách hàng X”, nó đã chuyển sang nghiệp vụ. Không giấu hành động đó sau một tên kỹ thuật như `repair` hoặc `maintenance`.

### 5.5. Một màn hình hỗ trợ khách hàng

Màn hình này có thể cần hai nguồn:

- Chi tiết lần nhập của khách hàng lấy từ API nghiệp vụ.
- Trạng thái vận hành bộ xử lý lấy từ nguồn quản lý, chỉ khi người xem có quyền.

Không nên để trình duyệt gọi trực tiếp một endpoint quản lý nhạy cảm chỉ vì tiện lấy dữ liệu. Kiến trúc truy cập và quyền phải phù hợp với từng nguồn.

## 6. Actuator mang lại cơ chế gì cho lựa chọn này?

Một endpoint Actuator tùy chỉnh được khai báo bằng định danh và các thao tác. Định nghĩa trung lập với công nghệ có thể được thích ứng sang HTTP hoặc JMX khi được cấu hình tương ứng. Khi chỉ cần HTTP, có lựa chọn chuyên biệt như `@WebEndpoint`.

Các thao tác web dùng quy ước Actuator: `@ReadOperation` tương ứng GET, `@WriteOperation` tương ứng POST và `@DeleteOperation` tương ứng DELETE. Đây không phải cơ chế thay thế toàn bộ khả năng của controller REST.

Tham số đầu vào của endpoint trung lập với công nghệ cần tuân thủ hợp đồng kiểu dữ liệu được hỗ trợ; không lấy nguyên một phương thức controller dùng `@RequestBody` với đối tượng phức tạp rồi đổi annotation là xong. Việc trả về một đối tượng kết quả vẫn có thể được hỗ trợ, như record trong ví dụ dưới. Phân biệt **kiểu đầu vào** và **đối tượng trả về** khi đọc [hướng dẫn tạo endpoint tùy chỉnh](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom).

Nếu API cần một hợp đồng HTTP phong phú, kiểm tra hợp lệ theo ca sử dụng, điều khiển phản hồi và lỗi nghiệp vụ, controller thường diễn đạt rõ hơn. Với một nhu cầu vận hành cần khả năng web đặc thù, hãy cân nhắc điểm mở rộng dành riêng cho web thay vì ép mọi thứ vào `@Endpoint`.

Cả endpoint và controller nên là lớp tiếp nhận mỏng:

```text
Công cụ vận hành -> Endpoint Actuator -> Service trạng thái/điều khiển
Người dùng      -> Controller API   -> Service ca sử dụng nghiệp vụ
```

Có thể dùng chung một thành phần đọc dữ liệu phía dưới khi hợp lý, nhưng hai hợp đồng không cần trả cùng một DTO hoặc có cùng quyền truy cập.

## 7. Ví dụ chạy được: ảnh chụp trạng thái bộ xử lý

Ví dụ dùng Java 21, Maven và Spring Boot 3.3.0. Nó chỉ cung cấp thông tin vận hành mô phỏng, không triển khai nghiệp vụ nhập dữ liệu thực sự. Mục tiêu là thấy một endpoint được đăng ký, công bố và gọi như thế nào.

Cấu trúc thư mục:

```text
endpoint-choice-demo/
├── pom.xml
└── src/main/
    ├── java/example/endpointchoice/OperationsDemoApplication.java
    └── resources/application.properties
```

### 7.1. Khai báo phụ thuộc

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
    <artifactId>endpoint-choice-demo</artifactId>
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

Đây là một dự án ví dụ độc lập. Trong ứng dụng đã có cấu hình build, chỉ bổ sung thành phần phù hợp vào cấu trúc hiện có, không thay toàn bộ build bằng mẫu này.

### 7.2. Tách nguồn trạng thái khỏi lớp endpoint

Tệp `src/main/java/example/endpointchoice/OperationsDemoApplication.java`:

```java
package example.endpointchoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OperationsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(OperationsDemoApplication.class, args);
    }

    @Bean
    WorkerState workerState() {
        return new WorkerState();
    }

    @Bean
    ImportWorkerEndpoint importWorkerEndpoint(WorkerState state) {
        return new ImportWorkerEndpoint(state);
    }

    public record WorkerSnapshot(
            boolean paused, int activeWorkers, int pendingJobs) {
    }

    public static class WorkerState {
        public WorkerSnapshot snapshot() {
            return new WorkerSnapshot(false, 2, 7);
        }
    }

    @Endpoint(id = "importworker")
    public static class ImportWorkerEndpoint {
        private final WorkerState state;

        public ImportWorkerEndpoint(WorkerState state) {
            this.state = state;
        }

        @ReadOperation
        public WorkerSnapshot snapshot() {
            return state.snapshot();
        }
    }
}
```

Cách đọc ví dụ:

- `WorkerState` là nguồn trạng thái. Các số 2 và 7 là dữ liệu mô phỏng cố định.
- `WorkerSnapshot` chỉ chứa thông tin vận hành cần cho ví dụ; không có dữ liệu khách hàng hay nội dung từng công việc.
- `ImportWorkerEndpoint` chuyển khả năng đọc trạng thái thành một thao tác Actuator.
- `@Bean` đăng ký endpoint vào Spring; `@Endpoint(id = "importworker")` khai báo định danh.
- `@ReadOperation` đọc trạng thái, không lấy việc khỏi hàng đợi, không khởi động lại worker và không thay đổi dữ liệu.

Ứng dụng thực cần thay `WorkerState.snapshot()` bằng ảnh chụp trạng thái nhất quán, có chi phí phù hợp. Không nên quét toàn bộ bảng nghiệp vụ hoặc gọi nhiều phụ thuộc chậm mỗi lần hệ thống giám sát đọc endpoint.

### 7.3. Công bố đúng endpoint

Tệp `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoint.importworker.enabled=true
management.endpoints.web.exposure.include=health,importworker
```

Cấu hình này dùng cơ chế bật và exposure của Spring Boot 3.3.x. Nó chỉ công bố `health` và `importworker` qua web. Ví dụ không có thư viện Spring Security và chỉ lắng nghe trên loopback để thực hành tại máy.

**Bật endpoint, công bố endpoint và cho phép một chủ thể truy cập là ba quyết định khác nhau.** Đổi `enabled=true` không thay cho exposure. Thêm ID vào exposure cũng không phải một quy tắc xác thực hay phân quyền.

### 7.4. Chạy và quan sát

Từ thư mục có `pom.xml`, dùng JDK 21:

```shell
mvn spring-boot:run
```

Trong PowerShell ở cửa sổ khác:

```powershell
curl.exe -sS http://127.0.0.1:8080/actuator/importworker
```

Phần thân JSON phản hồi:

```json
{"paused":false,"activeWorkers":2,"pendingJobs":7}
```

Đây là dữ liệu của nguồn trạng thái trong ví dụ. Nó không có nghĩa Spring Boot tự đếm worker hoặc tự tìm hàng đợi của ứng dụng.

Thử dùng POST cho endpoint chỉ có thao tác đọc:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" -X POST http://127.0.0.1:8080/actuator/importworker
```

Với cấu hình ví dụ, kết quả mã trạng thái là `405`, vì không có thao tác POST tương ứng. Không dùng POST này để kết luận endpoint đã có khả năng tạm dừng worker.

Tiếp theo, đổi exposure thành:

```properties
management.endpoints.web.exposure.include=health
```

Khởi động lại ứng dụng rồi gọi lại URL trên. Trong ví dụ không có lớp bảo mật hoặc mapping khác, kết quả là `404` vì endpoint không được công bố qua web. Annotation vẫn nằm trong mã, nhưng điều đó không đủ để URL khả dụng.

Nếu áp dụng thử nghiệm vào ứng dụng có Spring Security, bộ lọc bảo mật có thể trả 401 hoặc 403 trước khi yêu cầu tới lớp mapping. Vì vậy, không suy luận nguyên nhân chỉ từ một mã lỗi mà bỏ qua cấu hình của ứng dụng thực tế.

## 8. Ranh giới công bố và bảo vệ truy cập

Một endpoint vận hành có thể tiết lộ cách ứng dụng hoạt động hoặc cho phép thay đổi hành vi kỹ thuật. Vì vậy, việc chọn Actuator cần đi cùng thiết kế truy cập phù hợp, không chỉ chọn annotation.

Những câu hỏi thực tế cần trả lời:

- Endpoint chỉ đọc hay có thể thay đổi trạng thái?
- Người trực, công cụ tự động nào được phép gọi? Quyền đọc và quyền điều khiển có cần tách không?
- Dữ liệu trả về có chứa nội dung công việc, thông tin khách hàng, đường dẫn nội bộ hoặc bí mật không?
- Thao tác có phạm vi một bản chạy hay toàn bộ hệ thống? Bên gọi có thể nhận biết phạm vi đó không?
- Một lệnh thay đổi trạng thái có cần ghi lại người thực hiện và kết quả không?

Trong Spring Boot 3.3, nếu có Spring Security và chưa khai báo `SecurityFilterChain` riêng, tự cấu hình bảo vệ các actuator ngoài health. Khi ứng dụng tự định nghĩa chuỗi bảo mật, phải kiểm tra lại quy tắc dành cho endpoint quản lý; không mặc định rằng cơ chế bảo vệ trước đó vẫn được giữ. Xem [bảo mật Actuator trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Có thể tách cổng quản lý, ví dụ thêm vào cấu hình:

```properties
management.server.port=8081
management.server.address=127.0.0.1
```

Khi đó, URL endpoint của ví dụ chuyển sang `http://127.0.0.1:8081/actuator/importworker`. Cấu hình địa chỉ quản lý riêng được hỗ trợ khi cổng quản lý khác cổng ứng dụng. Các lựa chọn này được mô tả trong [giám sát và quản lý qua HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).

Tách cổng hỗ trợ tổ chức đường truy cập vận hành. Nó không tự cấp quyền và cũng không tự bảo đảm cổng được chặn ở mọi môi trường triển khai. Controller nghiệp vụ thông thường không tự chuyển sang cổng quản lý chỉ vì URL bắt đầu bằng `/actuator`.

## 9. Những lỗi thiết kế cần tránh

| Cách làm dễ gặp | Vấn đề | Hướng điều chỉnh |
| --- | --- | --- |
| Đưa API cho nhân viên vào Actuator vì “chỉ admin dùng” | Trộn quyền người dùng với bản chất nghiệp vụ | Phân loại theo ca sử dụng và dữ liệu |
| Tạo endpoint health riêng trả trường `status` | Không tự tham gia tổng hợp sức khỏe và probe | Xem xét HealthIndicator và cấu hình health |
| Tạo endpoint JSON để thay toàn bộ metric | Phải tự xây thu thập, tổng hợp và lịch sử | Dùng metric cho số liệu theo thời gian |
| Đọc endpoint làm thay đổi hàng đợi hoặc chạy lại job | Thao tác đọc có hiệu ứng phụ ngoài dự kiến | Tách truy vấn và thao tác điều khiển |
| Trả danh sách đối tượng nghiệp vụ qua endpoint chẩn đoán | Khó kiểm soát dữ liệu và quyền sở hữu | Trả thông tin vận hành tối thiểu cần thiết |
| Dùng trạng thái trong bộ nhớ một bản chạy như số liệu toàn cụm | Kết luận sai khi có nhiều bản ứng dụng | Ghi rõ phạm vi hoặc xây nguồn tổng hợp riêng |
| Thêm `@Endpoint` rồi cho rằng URL đã tồn tại | Thiếu đăng ký bean, bật hoặc exposure | Kiểm tra từng điều kiện trong ứng dụng thực tế |
| Đổi đường dẫn controller sang `/actuator/...` | Không có cơ chế quản lý Actuator như mong đợi | Dùng đúng loại endpoint và xác minh mapping |
| Cho mọi thao tác kỹ thuật vào một endpoint “admin” | Hợp đồng và quyền quá rộng, khó hiểu | Tách theo khả năng vận hành có ý nghĩa |

Một thao tác quản lý dài cũng cần có giới hạn rõ. Nếu phải tạo công việc nền, cần hợp đồng tiếp nhận, theo dõi kết quả và xử lý gọi lại phù hợp. Annotation Actuator không tự cung cấp bộ điều phối công việc hoặc bảo đảm thao tác chỉ chạy một lần.

## 10. Bài tập quyết định và kiểm chứng

Với mỗi yêu cầu dưới đây, chọn khả năng có sẵn, endpoint Actuator tùy chỉnh hoặc controller nghiệp vụ. Giải thích mục đích, phạm vi dữ liệu và bên được phép gọi.

1. Người dùng xem kết quả nhập dữ liệu của tài khoản mình.
2. Người trực xem trạng thái tạm dừng và số worker đang hoạt động của một bản ứng dụng.
3. Hệ thống cảnh báo cần theo dõi số công việc chờ và thời gian xử lý trong 24 giờ.
4. Nhân viên hỗ trợ duyệt hoàn tiền theo hạn mức được giao.
5. Công cụ bảo trì muốn tạm dừng nhận việc mới, để công việc đang chạy được hoàn tất.
6. Hệ thống triển khai cần biết ứng dụng đã sẵn sàng nhận lưu lượng hay chưa.

Gợi ý đối chiếu:

- Yêu cầu 1 và 4 thuộc các ca sử dụng nghiệp vụ.
- Yêu cầu 2 có thể phù hợp với endpoint chẩn đoán tùy chỉnh nếu cần một ảnh chụp đặc thù.
- Yêu cầu 3 phù hợp với metric và hệ thống lưu trữ/hiển thị theo thời gian.
- Yêu cầu 5 có thể là khả năng vận hành; phải làm rõ phạm vi, trạng thái chuyển tiếp và quyền điều khiển trước khi triển khai.
- Yêu cầu 6 nên xem xét health/readiness thay vì tự tạo một endpoint trạng thái không tích hợp.

Sau đó, kiểm tra ví dụ ở mục 7 theo ba trường hợp: GET trả đúng ảnh chụp khi được expose; POST không tạo ra thao tác ghi; bỏ ID khỏi exposure thì URL không còn khả dụng trong cấu hình mẫu.

Quyết định thiết kế cần có lý do cụ thể: chức năng này mô tả hoặc điều khiển điều gì, ai dùng nó, dữ liệu thuộc phạm vi nào, và vì sao khả năng được chọn phù hợp với hợp đồng đó.
