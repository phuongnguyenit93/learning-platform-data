# Luồng xuyên suốt: gửi yêu cầu, xử lý và ghi nhận kết quả với Spring JMS

## 1. Bức tranh tổng thể và mục tiêu

Giả sử người dùng gửi yêu cầu tạo một kết quả cần thời gian xử lý: kết xuất báo cáo, chuyển đổi tài liệu hoặc chuẩn bị dữ liệu. HTTP request không nhất thiết phải giữ kết nối cho tới khi công việc hoàn tất. Spring JMS giúp tách **nơi tiếp nhận yêu cầu** khỏi **nơi thực thi công việc** bằng cách đưa thông điệp qua message broker.

Một luồng đầy đủ cần trả lời được sáu câu hỏi:

1. Ai tiếp nhận yêu cầu và tạo mã định danh cho công việc?
2. Yêu cầu được gửi vào queue nào; broker giữ và chuyển thông điệp ra sao?
3. Consumer nào nhận thông điệp; xử lý nghiệp vụ như thế nào?
4. Khi nào thông điệp được xem là đã xử lý thành công và được xác nhận (acknowledge/commit)?
5. Kết quả cuối cùng lưu ở đâu và người yêu cầu xem kết quả bằng cách nào?
6. Nếu ứng dụng, broker hoặc cơ sở dữ liệu gặp lỗi, làm sao tránh thất lạc và xử lý trùng?

Trong bài này, **yêu cầu** là một công việc có mã jobId; **kết quả** được ghi vào cơ sở dữ liệu và tra cứu lại qua HTTP. Đây là kiểu **asynchronous request + status lookup**: phản hồi HTTP ban đầu chỉ xác nhận đã nhận/gửi yêu cầu, còn kết quả nghiệp vụ xuất hiện sau đó.

## 2. Các thành phần và trách nhiệm

| Thành phần | Trách nhiệm |
| --- | --- |
| Client | Gửi yêu cầu, nhận jobId, tra cứu trạng thái/kết quả. |
| API/Producer | Kiểm tra input, cấp jobId, lưu bản ghi ban đầu và gửi thông điệp bằng JmsTemplate. |
| Broker và Queue | Nhận, lưu/chuyển phát thông điệp theo cấu hình broker; giao cho consumer. |
| Listener container | Quản lý kết nối/session, nhận thông điệp, gọi phương thức gắn @JmsListener và thực hiện quy tắc ack/transaction. |
| Consumer/Service | Kiểm tra jobId, xử lý nghiệp vụ, chống xử lý trùng và lưu kết quả. |
| Result store | Lưu trạng thái PENDING, COMPLETED hoặc lỗi; cho phép truy vấn độc lập với vòng đời JMS message. |

Đối với **queue** kiểu point-to-point, mỗi lần giao một thông điệp thường hướng tới một consumer trong nhóm cạnh tranh; nếu nhiều instance cùng lắng nghe, chúng chia nhau công việc. **Topic** dùng khi nhiều subscription cần nhận cùng một sự kiện; không nên nhầm topic với hàng đợi xử lý một job duy nhất.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Client
    participant API as HTTP API / Producer
    participant DB as Result DB
    participant MQ as JMS Broker / Queue
    participant Worker as @JmsListener
    User->>API: POST /jobs, input
    API->>DB: INSERT jobId + PENDING
    API->>MQ: convertAndSend(jobId)
    API-->>User: HTTP 202 + jobId
    MQ->>Worker: deliver message
    Worker->>DB: SELECT job + kiểm tra trùng
    Worker->>Worker: xử lý nghiệp vụ
    Worker->>DB: UPDATE result + COMPLETED
    Worker-->>MQ: trả về thành công / commit session
    User->>API: GET /jobs/{jobId}
    API->>DB: SELECT trạng thái + kết quả
    API-->>User: COMPLETED + result
~~~

Sơ đồ biểu diễn **đường thành công**. Các bước ở consumer chạy sau khi broker giao thông điệp; thời điểm HTTP 202 không đồng nghĩa với việc consumer đã xử lý xong. Message broker không tự tạo bảng kết quả, cũng không tự biết công việc đã thành công theo nghiệp vụ: ứng dụng phải ghi nhận điều đó.

## 3. Diễn giải chi tiết từng chặng

### Chặng A — Tiếp nhận và gửi yêu cầu

1. API xác thực/kiểm tra dữ liệu đầu vào và cấp jobId duy nhất, ví dụ UUID.
2. API lưu bản ghi jobId, nội dung cần xử lý và trạng thái PENDING. Bản ghi này là mốc để tra cứu, cũng là căn cứ phát hiện job đã hoàn tất khi thông điệp bị gửi lại.
3. Producer gửi thông điệp vào queue, chẳng hạn jobs.requests, qua JmsTemplate.convertAndSend(...).
4. Khi lời gọi gửi thông điệp hoàn tất theo giao ước của provider, API có thể trả HTTP 202 Accepted kèm jobId. **202 chỉ có nghĩa yêu cầu được chấp nhận để xử lý bất đồng bộ**, không phải đã xử lý thành công.

Phân biệt ba định danh: **jobId** là khóa nghiệp vụ do ứng dụng tự đặt; **JMSMessageID** do provider cấp cho JMS message; **JMSCorrelationID** có thể gắn để liên kết các thông điệp theo một cuộc trao đổi. Không dùng JMSMessageID thay cho khóa nghiệp vụ nếu hệ thống cần chống trùng qua các lần phát lại/tạo message mới.

### Chặng B — Broker và consumer

Broker quản lý queue, nhận thông điệp từ producer rồi giao cho consumer khi có session/consumer sẵn sàng. Cách lưu bền, TTL, ưu tiên, giới hạn queue, redelivery và dead-letter address/queue (DLQ) phụ thuộc provider và cấu hình thực tế. Không nên mặc định mọi message sẽ được giữ vô thời hạn hoặc đến theo thứ tự toàn cục khi có nhiều consumer.

Spring tạo listener container cho phương thức @JmsListener. Container thực hiện phần kết nối, nhận và dispatch; service chỉ tập trung vào nghiệp vụ. Consumer nhận jobId, đọc dữ liệu đã lưu, xử lý, cập nhật result và status. Với nhiều instance hoặc khi có redelivery, xử lý phải **idempotent**: cùng một jobId được nhận lại không tạo thêm tác dụng phụ.

### Chặng C — Ghi nhận kết quả và xác nhận thông điệp

Để xem kết quả sau khi JMS message đã được tiêu thụ, lưu dữ liệu vào nơi bền vững như bảng job, object storage hoặc một result service. Một trạng thái tối thiểu:

| Trạng thái | Ý nghĩa |
| --- | --- |
| PENDING | Đã lưu yêu cầu; đang chờ hoặc đang xử lý trong ví dụ đơn giản. |
| COMPLETED | Tác vụ đã ghi thành công kết quả nghiệp vụ. |
| DISPATCH_FAILED | Producer không gửi được thông điệp theo kết quả lỗi quan sát được. |
| FAILED (mở rộng) | Tác vụ thất bại vĩnh viễn; cần lưu lý do và quy trình xử lý lỗi rõ ràng. |

Nếu listener chạy trong **JMS session transacted**, việc listener hoàn tất bình thường cho phép commit session; lỗi chưa xử lý làm session rollback và broker có thể giao lại thông điệp. Đừng đồng nhất **JMS commit** với **DB commit**: transaction cục bộ của JMS không tự làm việc cập nhật JDBC và xác nhận message trở thành một transaction nguyên tử trên hai tài nguyên.

Một tình huống quan trọng: DB đã lưu COMPLETED nhưng process dừng ngay trước JMS commit. Broker có thể redeliver. Consumer kiểm tra jobId đã COMPLETED rồi trả về thành công, nhờ đó tránh ghi kết quả/tác dụng phụ lần nữa. Tình huống ngược lại, producer lưu PENDING rồi dừng trước khi gửi JMS, sẽ khiến job kẹt nếu không có cơ chế outbox/reconciliation.

### Chặng D — Người gọi lấy kết quả

Client có thể gửi GET /jobs/{jobId} sau khi nhận HTTP 202, poll với khoảng nghỉ phù hợp hoặc nhận callback/WebSocket/event nếu kiến trúc có hỗ trợ. Tài nguyên trạng thái nên trả lời rõ **đang chờ**, **đã hoàn thành**, **lỗi gửi**, **lỗi xử lý**; riêng HTTP 200 khi gọi API tra cứu chỉ phản ánh lần đọc API thành công, không thay thế trạng thái của job.

## 4. Ví dụ chạy được: Spring Boot 3.3.x + Artemis + H2

Ví dụ dùng Java 17+, Spring Boot 3.3.13, một ActiveMQ Artemis broker đang chạy và H2 lưu bản ghi vào tệp cục bộ. Công việc minh họa là đổi văn bản thành chữ hoa để tập trung vào cơ chế JMS. Mỗi file bên dưới thuộc cùng một Maven project và cùng package example.jmsflow; không thể biên dịch một class Spring riêng lẻ chỉ bằng javac mà thiếu dependency.

Cấu trúc:

~~~text
jms-flow/
├── pom.xml
└── src/main/
    ├── java/example/jmsflow/
    │   ├── JmsFlowApplication.java
    │   ├── JobController.java
    │   └── JobWorker.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 4.1. Dependency (pom.xml)

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
    <artifactId>jms-flow</artifactId>
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
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

spring-boot-starter-artemis mang JMS client/integration; Spring Boot tự cấu hình ConnectionFactory, JmsTemplate và listener container khi có các dependency phù hợp. H2 ở đây phục vụ demo cục bộ; hệ thống thực tế chọn DB, retention và backup theo yêu cầu nghiệp vụ.

### 4.2. Cấu hình (src/main/resources/application.properties)

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis

spring.datasource.url=jdbc:h2:file:./data/jms-flow;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Thông tin đăng nhập artemis/artemis là mặc định của lệnh chạy broker thử nghiệm bên dưới; hãy dùng secrets và tài khoản riêng cho môi trường thật. URL jdbc:h2:file giúp bản ghi không tự biến mất chỉ vì ứng dụng Spring Boot khởi động lại, nhưng nó không biến H2 thành một cơ sở dữ liệu phân tán.

### 4.3. Lược đồ kết quả (src/main/resources/schema.sql)

~~~sql
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR(36) PRIMARY KEY,
    request_text VARCHAR(1000) NOT NULL,
    status VARCHAR(32) NOT NULL,
    result_text VARCHAR(1000)
);
~~~

Khóa chính id giữ mỗi jobId một bản ghi. Bản ghi lưu cả input lẫn output, để message trên queue chỉ cần chứa jobId; cách này thuận tiện cho retry và chống xử lý trùng. Ở hệ thống lớn, message có thể chứa payload đã định phiên bản hoặc tham chiếu đến object storage tùy mục tiêu tách ghép và dữ liệu.

### 4.4. Khởi động ứng dụng (JmsFlowApplication.java)

~~~java
package example.jmsflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JmsFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(JmsFlowApplication.class, args);
    }
}
~~~

### 4.5. Producer và API đọc trạng thái (JobController.java)

~~~java
package example.jmsflow;

import java.util.List;
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.JmsException;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/jobs")
public class JobController {
    private final JdbcTemplate jdbc;
    private final JmsTemplate jms;

    public JobController(JdbcTemplate jdbc, JmsTemplate jms) {
        this.jdbc = jdbc;
        this.jms = jms;
    }

    public record NewJob(String text) {}
    public record Accepted(String id, String status) {}
    public record JobStatus(String id, String status, String result) {}

    @PostMapping
    public ResponseEntity<Accepted> submit(@RequestBody NewJob request) {
        if (request.text() == null || request.text().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "text must not be blank");
        }

        String id = UUID.randomUUID().toString();
        jdbc.update(
                "INSERT INTO jobs(id, request_text, status) VALUES (?, ?, ?)",
                id, request.text(), "PENDING");

        try {
            jms.convertAndSend("jobs.requests", id);
        } catch (JmsException ex) {
            jdbc.update(
                    "UPDATE jobs SET status = 'DISPATCH_FAILED' WHERE id = ?",
                    id);
            throw new ResponseStatusException(
                    HttpStatus.SERVICE_UNAVAILABLE, "JMS send failed", ex);
        }
        return ResponseEntity.accepted().body(new Accepted(id, "PENDING"));
    }

    @GetMapping("/{id}")
    public JobStatus get(@PathVariable String id) {
        List<JobStatus> rows = jdbc.query(
                "SELECT id, status, result_text FROM jobs WHERE id = ?",
                (rs, rowNum) -> new JobStatus(
                        rs.getString("id"),
                        rs.getString("status"),
                        rs.getString("result_text")),
                id);
        if (rows.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Unknown job");
        }
        return rows.get(0);
    }
}
~~~

Các câu lệnh JDBC là thao tác DB riêng biệt. Vì INSERT chạy xong trước convertAndSend, consumer có thể tìm thấy jobId khi nhận message. Tuy nhiên cặp thao tác “INSERT rồi gửi message” vẫn có khoảng trống khi crash; mục 6 giải thích cách giải quyết trong production.

### 4.6. Consumer và ghi nhận kết quả (JobWorker.java)

~~~java
package example.jmsflow;

import java.util.List;
import java.util.Locale;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class JobWorker {
    private final JdbcTemplate jdbc;

    public JobWorker(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record JobRow(String requestText, String status) {}

    @JmsListener(destination = "jobs.requests")
    public void handle(String id) {
        List<JobRow> rows = jdbc.query(
                "SELECT request_text, status FROM jobs WHERE id = ?",
                (rs, rowNum) -> new JobRow(
                        rs.getString("request_text"),
                        rs.getString("status")),
                id);

        if (rows.isEmpty()) {
            throw new IllegalStateException("Unknown job: " + id);
        }

        JobRow job = rows.get(0);
        if ("COMPLETED".equals(job.status())) {
            return; // Thông điệp được giao lại: job đã có kết quả.
        }

        String result = job.requestText().trim().toUpperCase(Locale.ROOT);
        jdbc.update(
                "UPDATE jobs SET result_text = ?, status = 'COMPLETED' " +
                "WHERE id = ? AND status <> 'COMPLETED'",
                result, id);
    }
}
~~~

String mà listener nhận là phần text trong JMS message do JmsTemplate chuyển đổi. Nếu lỗi JDBC hoặc lỗi nghiệp vụ không được bắt, phương thức ném exception; với container dùng JMS transaction, session bị rollback để broker có cơ hội giao lại. Demo dùng phép biến đổi thuần và câu UPDATE có điều kiện nên việc giao lại ít nguy hiểm. Nếu tác vụ thật có gửi email, gọi API thanh toán hay thay đổi hệ thống khác, việc kiểm tra COMPLETED trước khi gọi chưa đủ để bảo đảm chính xác một lần trong mọi trường hợp: phải có idempotency key và cơ chế xác nhận kết quả từ hệ thống đích.

### 4.7. Chạy và quan sát

Cần Java 17+, Maven, Docker đang hoạt động và cổng 61616/8080 khả dụng. Dùng image chính thức của Apache Artemis:

~~~bash
docker run --detach --rm --name jms-flow-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Chạy lệnh sau tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Khi broker đã sẵn sàng, gửi HTTP request:

~~~http
POST /jobs HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"text":"xin chào jms"}
~~~

API trả **HTTP 202** với JSON gồm id (UUID phát sinh lúc chạy) và status ban đầu là PENDING. Dùng id vừa nhận để gọi:

~~~http
GET /jobs/{id} HTTP/1.1
Host: localhost:8080
~~~

Trong ví dụ thành công, trạng thái sau cùng là COMPLETED và result là XIN CHÀO JMS. Không dựa vào thứ tự log để suy ra trình tự chính xác: worker có thể xử lý rất nhanh, thậm chí trước khi client đọc hết HTTP 202. Nếu GET khi worker chưa hoàn tất, sẽ thấy PENDING; đây là hành vi hợp lệ.

Lệnh docker trên chỉ minh họa môi trường học tập, xóa container khi dừng và không mount volume dữ liệu broker. Khi muốn thử khả năng khôi phục qua restart broker, cần cấu hình persistence/volume đúng cách. Nếu broker vô hiệu tự tạo destination, phải tạo queue jobs.requests theo cấu hình Artemis. H2 file cũng chỉ nằm trên máy chạy ứng dụng.

## 5. Điều gì xảy ra khi lỗi hoặc gửi lặp?

| Điểm lỗi | Hiện tượng có thể xảy ra | Cách thiết kế/kiểm tra |
| --- | --- | --- |
| API nhận dữ liệu không hợp lệ | Không tạo job hoặc không gửi message | Trả 400 và thông báo kiểm tra input. |
| DB INSERT thất bại | Chưa có bản ghi job | Dừng trước JMS send; trả lỗi phù hợp. |
| DB INSERT xong, ứng dụng crash trước JMS send | PENDING có thể tồn tại mãi | Transactional outbox và dispatcher/reconciliation. |
| Broker không kết nối được khi gửi | Producer ném exception; kết quả gửi có thể không rõ nếu lỗi mạng xảy ra quanh thời điểm xác nhận | Lưu trạng thái, retry có kiểm soát và jobId/idempotency key. |
| Consumer xử lý lỗi tạm thời | JMS session rollback; broker có thể redeliver | Giới hạn số lần retry, backoff, DLQ và cảnh báo. |
| DB ghi COMPLETED rồi listener crash trước JMS commit | Broker có thể giao lại cùng job | Kiểm tra jobId và cập nhật idempotent. |
| Input bị lỗi vĩnh viễn | Retry vô hạn có thể chiếm queue | Phân loại lỗi, chuyển DLQ hoặc ghi FAILED theo chính sách rõ ràng. |
| Client GET quá sớm | Chỉ thấy PENDING | Truy vấn lại theo backoff; không tuyên bố hoàn thành từ HTTP 202. |
| Nhiều consumer chạy song song | Thứ tự toàn cục không được đảm bảo | Dùng khóa nghiệp vụ, điều kiện cập nhật/locking và nhóm message khi cần. |

**Ack không phải bằng chứng tất cả side effect đều an toàn.** Với listener transacted, commit JMS xác nhận việc tiêu thụ message trong tài nguyên JMS. Database, external HTTP call và broker có thể commit ở các thời điểm khác nhau. Vì vậy thiết kế thực tế thường chấp nhận **at-least-once processing** và làm handler idempotent, thay vì giả định “exactly once end-to-end”.

**Không nuốt exception sai cách.** Nếu consumer bắt mọi exception, log rồi return, container có thể coi message đã xử lý thành công và commit; công việc mất cơ hội retry. Chỉ return bình thường khi kết quả/việc thất bại vĩnh viễn đã được xử lý theo chính sách. Lỗi tạm thời cần được ném ra để kích hoạt rollback khi cấu hình cho phép.

**DLQ không tự cập nhật trạng thái job.** Broker chuyển message qua DLQ vẫn không khiến bản ghi trong DB thành FAILED. Muốn API phản ánh chính xác, cần một tiến trình/handler đọc DLQ, ghi lỗi và công bố sự cố theo chính sách.

## 6. Những điểm cần nâng cấp khi áp dụng thực tế

### 6.1. Transactional outbox chống khoảng trống giữa DB và JMS

Ví dụ demo thực hiện **INSERT jobs** rồi **JMS send** bằng hai thao tác riêng. Nếu ứng dụng dừng giữa hai thao tác, job đã có trong DB nhưng không có message.

Transactional outbox xử lý bằng cách, trong **cùng một DB transaction**, ghi bản ghi job và bản ghi outbox chứa sự kiện “JobRequested”. Một dispatcher riêng đọc outbox, gửi JMS, rồi đánh dấu đã gửi. Dispatcher vẫn có thể gửi lại nếu lỗi sau send trước đánh dấu, nên consumer vẫn cần idempotent. Outbox làm tránh mất ý định gửi; không tự tạo ra exactly-once khi có hai tài nguyên độc lập.

### 6.2. JMS transaction, DB transaction và XA

- **JMS local transaction:** receipt/response trên JMS session có thể rollback hoặc commit cùng nhau; không gộp DB transaction mặc định.
- **DB transaction:** bảo vệ nhiều câu lệnh JDBC cùng tài nguyên DB, ví dụ kiểm tra/chuyển trạng thái có điều kiện.
- **XA/JTA:** có thể phối hợp nhiều tài nguyên tương thích trong một distributed transaction, đổi lấy cấu hình, log coordinator và chi phí vận hành phức tạp hơn.
- **Outbox + idempotency:** thường là hướng phù hợp khi không muốn distributed transaction; cần thiết kế retry, deduplication và reconciliation rõ ràng.

Với Spring Boot 3.3 và JMS listener container mặc định, Spring Boot cấu hình session transacted khi không có JTA manager. Tuy nhiên khi tự tạo factory hoặc đổi phiên bản/configuration, cần kiểm tra lại cơ chế acknowledge và transaction thực tế. Đặt @Transactional cho JDBC **không tự biến hai tài nguyên thành một transaction nguyên tử**.

### 6.3. Theo dõi, bảo mật và hiệu năng

- Theo dõi số message chờ trong queue, tuổi message cũ nhất, số lần redelivery, DLQ, lỗi producer, thời gian xử lý và tỷ lệ COMPLETED/FAILED.
- Đặt correlation theo jobId xuyên suốt log/API/DB; không log payload chứa thông tin nhạy cảm.
- Giới hạn kích thước message, TTL, retry/backoff, concurrency và quyền truy cập queue; sử dụng TLS và credentials an toàn khi triển khai.
- Với job lâu, tránh giữ DB transaction suốt quá trình tính toán/gọi mạng; xác định thời gian xử lý tối đa và khả năng hủy.
- Thiết kế trạng thái rõ ràng cho timeout/FAILED và chính sách dọn dữ liệu; đừng để PENDING tồn tại vô hạn mà không giám sát.
- Khi scaling nhiều worker, đảm bảo xử lý trùng an toàn và cân nhắc thứ tự theo từng business key thay vì kỳ vọng thứ tự toàn queue.

## 7. Tự kiểm tra hiểu bài

1. **Vì sao HTTP 202 không chứng minh job đã hoàn thành?** Vì 202 được trả sau chặng tiếp nhận/gửi yêu cầu; xử lý nghiệp vụ chạy bất đồng bộ.
2. **Vì sao vẫn phải lưu kết quả vào DB nếu JMS đã có queue?** Queue dùng chuyển giao công việc; sau khi message được consume, kết quả cần tồn tại độc lập để client tra cứu và audit.
3. **Nếu DB đã lưu COMPLETED nhưng JMS chưa commit thì sao?** Broker có thể redeliver; consumer cần nhận biết job đã hoàn tất và tránh lặp side effect.
4. **Điểm mất message nằm ở đâu trong demo?** DB INSERT thành công rồi crash trước send; giải bằng outbox/reconciliation.
5. **Nếu lỗi nào cũng bị catch rồi return thì sao?** Container có thể commit/ack dù công việc thất bại; phải phân loại lỗi tạm thời và vĩnh viễn.
6. **Khi nào dùng JMSReplyTo/JMSCorrelationID?** Khi cần một response message đi lại qua JMS; trong mẫu này client tra cứu kết quả qua HTTP bằng jobId nên không cần JMS reply queue. Mẫu request-reply đồng bộ qua JMS là thiết kế khác và cần timeout/correlation rõ ràng.

Một bài thực hành có giá trị: gửi job, tạm tắt consumer để quan sát message nằm trong queue, khởi động lại để thấy status thay đổi; sau đó thử làm listener ném exception trước khi UPDATE, quan sát redelivery; cuối cùng mô phỏng lỗi sau UPDATE và kiểm tra cơ chế chống trùng. Đối chiếu log, queue metrics và bảng jobs, không chỉ dựa vào HTTP response.

## 8. Tài liệu chuẩn để đào sâu

- Spring Framework — Receiving a Message: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework — Using Spring JMS/Transaction Management: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot — JMS (3.3): https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html
- Apache Artemis — Docker image chính thức: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
