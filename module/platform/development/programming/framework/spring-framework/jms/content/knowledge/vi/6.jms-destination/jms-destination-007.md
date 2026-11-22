# Quy ước tên destination theo môi trường và miền nghiệp vụ trong Spring JMS

## 1. Mục tiêu

Khi hệ thống có nhiều Queue, Topic, dịch vụ và môi trường triển khai, tên destination thiếu nhất quán gây ra lỗi khó nhận biết: ứng dụng `dev` vô tình gửi vào queue của `prod`, hai nhóm nghiệp vụ dùng trùng tên, listener đăng ký sai loại đích, hoặc vận hành không biết ai sở hữu một destination. Một quy ước tên tốt giúp **định tuyến đúng, cô lập môi trường, phân quyền, quan sát và thay đổi hợp đồng có kiểm soát**.

Sau bài này, bạn có thể:
- Phân biệt tên **logic trong ứng dụng**, tên **physical destination** trên broker và tên **subscription**.
- Thiết kế tên theo môi trường (`dev`, `test`, `stg`, `prod`), miền nghiệp vụ, đối tượng và ý nghĩa thông điệp.
- Giải thích vì sao quy ước là **quyết định kiến trúc**, không phải yêu cầu bắt buộc từ chuẩn Jakarta Messaging.
- Cấu hình publisher và `@JmsListener` dùng chung một tên qua Spring Boot externalized configuration.
- Xây dựng nguyên tắc đặt tên cho retry/DLQ, version, multi-tenant, quyền truy cập và migration.
- Kiểm tra tên bằng Java 17, kiểm tra thực tế bằng Spring JMS và broker trước khi phát hành.

Bài nằm trong nhóm **Destination**. Trọng tâm là tên và vòng đời quản lý Queue/Topic, không đi sâu sang tối ưu giao nhận, transaction hay cấu hình cluster của từng broker.

## 2. Ba lớp tên cần phân biệt

~~~text
Ứng dụng Spring                                      Broker
┌─────────────────────────────────────┐            ┌──────────────────────────────┐
│ Khóa cấu hình logic                  │            │ Physical JMS destination     │
│ app.messaging.destinations.invoice-issue         │                              │
│              │                      │            │ dev.billing.invoice.issue.v1 │
│              ▼                      │            │    └─ Queue                  │
│           giá trị cấu hình ───────────────────────>│                              │
│              │                      │            │ prod.sales.order.created.v1  │
│  JmsTemplate / @JmsListener          │            │    └─ Topic                  │
└─────────────────────────────────────┘            └──────────────────────────────┘
~~~

1. **Tên logic:** khóa cấu hình hoặc ID nội bộ của ứng dụng, ví dụ `app.messaging.destinations.invoice-issue`. Tên này phản ánh trách nhiệm của code và nên ổn định giữa môi trường.
2. **Tên physical destination:** chuỗi mà JMS client chuyển cho provider khi tìm/tạo Queue hoặc Topic, ví dụ `dev.billing.invoice.issue.v1`. Broker hoặc cơ chế quản trị ánh xạ chuỗi này đến tài nguyên thật theo quy tắc của provider.
3. **Tên subscription:** tên định danh một đăng ký Topic (đặc biệt durable/shared), ví dụ `billing-reporting-v1`. Đây là **đối tượng khác tên Topic**; nhiều subscription độc lập có thể cùng đọc một Topic.

Theo Jakarta Messaging, `Queue` và `Topic` là hai kiểu `Destination`. Việc dùng tên chứa dấu chấm, gạch ngang, prefix môi trường hoặc phần version là **quy ước do đội phát triển tự chọn**, không phải cú pháp JMS bắt buộc. Tên do `Session.createQueue(String)` hoặc `Session.createTopic(String)` tạo ra không nhất thiết làm broker tự sinh physical resource: hành vi phụ thuộc provider, JNDI, cấu hình auto-create và quyền.

**Tên Queue và Topic không thay thế cho loại destination.** Với Spring JMS, publisher dùng `JmsTemplate` và listener container phải được cấu hình đúng Queue hoặc Topic (`pubSubDomain`), ngay cả khi tên vật lý giống nhau.

## 3. Đề xuất một mẫu tên chuẩn, dễ vận hành

Với tổ chức có nhiều ứng dụng/môi trường dùng chung broker, có thể bắt đầu từ mẫu:

~~~text
environment.domain.subject.action.vMAJOR
~~~

Giải nghĩa:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `environment` | Môi trường đang sở hữu message, không phải hostname hay pod. | `dev`, `test`, `stg`, `prod` |
| `domain` | Miền nghiệp vụ/bounded context chịu trách nhiệm về message. | `billing`, `sales`, `identity` |
| `subject` | Thực thể/khái niệm nghiệp vụ chính. | `invoice`, `order`, `user` |
| `action` | Lệnh cần thực thi hoặc sự kiện đã xảy ra. | `issue`, `created`, `paid` |
| `vMAJOR` | Phiên bản hợp đồng định tuyến lớn khi thực sự cần tách luồng không tương thích. | `v1`, `v2` |

**Ví dụ cụ thể** (đây là tên minh họa, không phải destination đang tồn tại trên broker):

| Loại | Tên physical | Mục đích |
|---|---|---|
| Queue | `dev.billing.invoice.issue.v1` | Yêu cầu phát hành hóa đơn ở dev; một consumer trong nhóm xử lý từng job. |
| Queue | `prod.fulfillment.shipment.dispatch.v1` | Lệnh điều phối giao hàng production. |
| Topic | `stg.sales.order.created.v1` | Phát sự kiện đơn hàng được tạo tới nhiều nhóm subscriber ở staging. |
| Topic | `prod.billing.invoice.paid.v2` | Sự kiện thanh toán hóa đơn, hợp đồng định tuyến phiên bản lớn 2. |

Đặt tên bằng **chữ thường ASCII**, thống nhất một dấu phân cách (`.`), tránh khoảng trắng, tiếng Việt có dấu và ký tự đặc biệt nếu chưa chứng minh broker/client cho phép. Ví dụ: `prod.sales.order.created.v1` rõ ràng hơn `ORDER_EVENT` hoặc `orders`. Các segment nên ngắn, chứa danh từ/ngữ nghĩa rõ ràng; không đổi qua lại giữa số ít/số nhiều hoặc giữa `order-created` và `order_created` nếu không có chính sách.

Tên không nên mang địa chỉ IP, hostname, mật khẩu, mã deploy, timestamp hoặc pod ID. Các thông tin ấy thay đổi cùng hạ tầng và làm mất ổn định contract. Nếu cần nhận diện nguồn gửi, dùng message property/header, tracing và metrics phù hợp thay vì tạo một destination mới cho mỗi instance.

### Có cần thêm `queue`/`topic` vào tên?

Có thể dùng kiểu `prod.queue.billing.invoice.issue.v1` để con người nhìn tên dễ hiểu hơn, nhưng không có chuẩn nào buộc phải làm thế. Nếu tổ chức đã quản lý **loại đích trong destination registry**, không cần lặp lại `queue` hoặc `topic` như một segment. Dù chọn phương án nào, trong review vẫn phải ghi rõ `kind=QUEUE` hay `kind=TOPIC`: broker có thể phân biệt bằng loại tài nguyên, routing type hoặc context riêng.

**Một quy ước phải nhất quán từ đầu đến cuối.** Không tự áp dụng mẫu mới lên các Queue legacy đang có consumer/ACL/monitoring phụ thuộc tên cũ nếu chưa có kế hoạch chuyển đổi.

## 4. Tách môi trường: prefix trong tên hay broker riêng?

Hai chiến lược đều hợp lý, tùy topology.

### Chiến lược A — Một broker/namespace dùng chung nhiều môi trường

Tên physical có prefix môi trường:

~~~text
dev.billing.invoice.issue.v1
stg.billing.invoice.issue.v1
prod.billing.invoice.issue.v1
~~~

Có lợi khi đội vận hành cần nhìn tên để phân biệt luồng. Tuy nhiên, prefix **không phải biện pháp cô lập bảo mật**. Một ứng dụng dev có credentials đủ quyền vẫn có thể gửi đến `prod.billing.invoice.issue.v1`. Cần ACL/service account riêng, namespace/virtual host nếu provider có, policy tài nguyên, quota và các guardrail ở deployment.

### Chiến lược B — Mỗi môi trường có broker/namespace độc lập

Cùng một tên logic/physical có thể sử dụng ở mỗi broker:

~~~text
Broker DEV: billing.invoice.issue.v1
Broker STG: billing.invoice.issue.v1
Broker PROD: billing.invoice.issue.v1
~~~

Sự tách biệt thực tế đến từ endpoint, account, hạ tầng mạng và quyền truy cập, không phải tiền tố `prod`. Phương án này có thể tránh duplicate environment trong tên và giúp ứng dụng dễ chuyển giữa môi trường qua cấu hình. Điều kiện là các pipeline/provisioning phải ánh xạ đúng broker và không tạo đường kết nối chéo.

**Không bắt buộc nhồi môi trường vào tên nếu namespace đã tách vật lý.** Quyết định một chuẩn áp dụng cho toàn bộ service trong cùng hệ thống. Nếu có shared broker và dedicated broker cùng tồn tại, ghi rõ mapping theo môi trường trong registry để không nhầm.

## 5. Gắn tên với đúng miền nghiệp vụ và ownership

Miền nghiệp vụ nên được xác định theo **người/nhóm sở hữu contract** thay vì vị trí triển khai của consumer. Ví dụ `sales.order.created` là sự kiện do Sales phát; Billing và Notification là các subscriber độc lập. Không đặt `billing.sales.order.created` chỉ vì Billing đọc Topic đó.

Với command Queue như `billing.invoice.issue`, tên thường mô tả **năng lực được gọi** và owner nhận lệnh; sender có thể là Order Service nhưng destination vẫn do Billing chịu trách nhiệm. Điều này giúp xác định ai được quyền tạo, thay đổi schema, thiết lập DLQ và dọn queue.

Nên lưu một **destination registry** có thể kiểm toán; mỗi entry tối thiểu gồm:

| Trường | Giá trị ví dụ |
|---|---|
| Logical key | `invoice-issue` |
| Physical name | `prod.billing.invoice.issue.v1` |
| Kind | `QUEUE` |
| Owner | `billing` |
| Producer | `order-service` |
| Consumer group | `invoice-worker` |
| Environment / broker namespace | `prod / finance-mq` |
| Message contract | `InvoiceIssueCommand v1` |
| Retry/DLQ policy | `invoice-issue-dlq-policy` |
| Security | Producer send; worker consume; ops administer |
| Lifecycle | Active, replacement, cutover, retired |

Những tên ứng dụng, miền và registry trong bảng chỉ minh họa. Các trường bảo mật ở đây biểu diễn **vai trò cần cấp**; quyền thật do broker quản lý. Với Topic có nhiều subscriber, ghi thêm tên subscription, durable/shared, client identity nếu có và chính sách retention.

### Không để consumer tự quyết tên nguồn sự kiện

Khi nhiều service quan tâm đến `order.created`, owner domain phát hành một destination contract, các consumer đăng ký theo contract đó. Nếu mỗi consumer tự đặt tên Topic riêng, publisher phải biết tất cả consumer và lợi ích decoupling của pub/sub sẽ giảm đáng kể.

## 6. Queue, Topic và subscription đặt tên khác nhau

**Queue**: một message thường được giao cho một consumer trong nhóm cạnh tranh. Tên nên là một **công việc hoặc command rõ nghĩa**, ví dụ `prod.billing.invoice.issue.v1`. Các consumer của cùng Queue dùng chung physical destination; nếu thêm replica để chia tải thì **không tạo Queue mới theo tên replica**.

**Topic**: một message có thể đến nhiều subscription độc lập. Tên thường thể hiện **sự kiện đã xảy ra**, ví dụ `prod.sales.order.created.v1`. Một Topic không đại diện cho một consumer cụ thể.

**Subscription**: nếu dùng durable/shared subscription, đặt identity gắn với **consumer group và mục đích sử dụng**, ví dụ `billing-revenue-projection-v1` hoặc `notification-order-email-v1`. Trong JMS, định danh durable unshared còn phụ thuộc `clientId` và `subscriptionName` theo API/provider. Đổi tên subscription một cách tùy tiện có thể khiến broker coi đó là subscription mới, mất liên kết backlog cũ hoặc tạo tồn đọng.

~~~text
Topic: prod.sales.order.created.v1
    ├── Subscription: billing-revenue-projection-v1
    │      └── Billing consumers
    └── Subscription: notification-order-email-v1
           └── Notification consumers
~~~

Nếu Billing tăng số replica, kiểm tra dùng **shared subscription** thay vì dựng mỗi replica một subscription độc lập (vốn sẽ khiến mọi replica nhận cùng một sự kiện). Nhà cung cấp broker và JMS API phải hỗ trợ kiểu subscription đã chọn.

## 7. Dùng tên cấu hình thay vì hard-code trong Spring JMS

Điểm thực hành quan trọng nhất: **mã Java gọi logical key ổn định, còn physical name đến từ cấu hình**.

Ví dụ Spring Boot 3 + Java 17 sử dụng **Queue** để thực thi một command phát hành hóa đơn. Tại `application.yml`:

~~~yaml
app:
  messaging:
    destinations:
      invoice-issue: "${JMS_INVOICE_ISSUE_QUEUE:dev.billing.invoice.issue.v1}"
~~~

- Nếu biến môi trường `JMS_INVOICE_ISSUE_QUEUE` chưa được đặt, tên là `dev.billing.invoice.issue.v1`.
- Ở staging/production, pipeline triển khai cấp tên đã được đăng ký cho môi trường tương ứng, ví dụ `prod.billing.invoice.issue.v1` nếu dùng chiến lược prefix.
- Khóa `app.messaging.destinations.invoice-issue` **giữ nguyên trong code**, còn giá trị physical thay đổi theo deployment. Khóa cấu hình và tên broker là hai lớp khác nhau.
- Với production nghiêm ngặt, có thể **bỏ default dev** để thiếu biến môi trường sẽ gây lỗi fail-fast; mặc định dev chỉ giúp lab dễ chạy.

### Publisher: lấy physical name từ cùng property

`src/main/java/example/jms/InvoicePublisher.java`:

~~~java
package example.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoicePublisher {
    private final JmsTemplate jmsTemplate;
    private final String invoiceIssueDestination;

    public InvoicePublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.messaging.destinations.invoice-issue}")
            String invoiceIssueDestination) {
        this.jmsTemplate = jmsTemplate;
        this.invoiceIssueDestination = invoiceIssueDestination;
    }

    public void issueInvoice(String invoiceId) {
        jmsTemplate.convertAndSend(invoiceIssueDestination, invoiceId);
    }
}
~~~

`JmsTemplate` mặc định sử dụng mô hình Queue khi `pubSubDomain=false`; ở đây tên `invoiceIssueDestination` là tên của **Queue**. Không tự nối thêm `prod.` trong Java, vì môi trường đã được quyết định bằng cấu hình.

### Listener: tham chiếu cùng property

`src/main/java/example/jms/InvoiceListener.java`:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceListener {
    @JmsListener(destination =
            "${app.messaging.destinations.invoice-issue}")
    public void handle(String invoiceId) {
        System.out.println("processed invoice=" + invoiceId);
    }
}
~~~

Spring xử lý placeholder cấu hình trong thuộc tính `destination` của `@JmsListener` khi đăng ký listener endpoint. Publisher và listener vì thế dùng cùng một nguồn cấu hình. Nếu thay tên tại môi trường triển khai, cả hai tham chiếu đến cùng Queue **khi chạy cùng cấu hình**. Khi các dịch vụ được deploy độc lập, registry/provisioning phải cung cấp mapping khớp nhau cho cả producer và consumer.

**Không dùng một Queue name làm Topic chỉ bằng cách đổi từ khóa trong tài liệu.** Với Topic, phải cấu hình `JmsTemplate#setPubSubDomain(true)` và listener container factory `setPubSubDomain(true)` (hoặc sử dụng `Topic` đích tường minh), rồi xác nhận broker routing/subscription. Producer/consumer không cùng loại destination có thể “gửi thành công” nhưng không có listener mong muốn nhận được.

## 8. Demo Spring Boot chạy được: một physical Queue cho cả gửi và nhận

Phần này xây dựng ứng dụng nhỏ có thể gọi HTTP để gửi JMS message và xác nhận listener nhận đúng Queue. Dùng Spring Boot 3.3.5, Java 17+, Gradle 8.x tương thích và Artemis embedded phục vụ **lab**. Nếu đã dùng broker ngoài, thay Artemis embedded bằng cấu hình connection tới broker thật; production không nên dựa vào demo để chứng minh độ bền hay HA.

Cấu trúc:

~~~text
destination-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/
    │   ├── DestinationDemoApplication.java
    │   ├── InvoicePublisher.java
    │   ├── InvoiceListener.java
    │   └── InvoiceController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'destination-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  artemis:
    mode: embedded
    embedded:
      queues: dev.billing.invoice.issue.v1
      persistent: false

app:
  messaging:
    destinations:
      invoice-issue: "${JMS_INVOICE_ISSUE_QUEUE:dev.billing.invoice.issue.v1}"
~~~

Ở lab, broker embedded tạo queue `dev.billing.invoice.issue.v1`, đúng default của ứng dụng. Nếu đổi biến môi trường `JMS_INVOICE_ISSUE_QUEUE`, phải **provision queue tương ứng trên broker**; đừng chỉ thay property ở client. Với một broker từ xa, nên quản lý destination qua IaC/admin và hạn chế auto-create khi thích hợp.

`src/main/java/example/jms/DestinationDemoApplication.java`:

~~~java
package example.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class DestinationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DestinationDemoApplication.class, args);
    }
}
~~~

Dùng hai class `InvoicePublisher` và `InvoiceListener` đã trình bày ở mục 7 (lưu đúng package `example.jms`). Thêm controller:

`src/main/java/example/jms/InvoiceController.java`:

~~~java
package example.jms;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InvoiceController {
    private final InvoicePublisher publisher;

    public InvoiceController(InvoicePublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/invoices/{id}/issue")
    public ResponseEntity<String> issue(@PathVariable String id) {
        publisher.issueInvoice(id);
        return ResponseEntity.accepted().body("queued invoice=" + id);
    }
}
~~~

Chạy từ thư mục `destination-demo`. Nếu có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Hoặc nếu chưa có Wrapper, dùng Gradle cài sẵn tương thích:

~~~bash
gradle bootRun
~~~

Sau khi ứng dụng và listener đã khởi động, gọi HTTP từ terminal khác:

~~~bash
curl -X POST http://localhost:8080/invoices/42/issue
~~~

HTTP response body:

~~~text
queued invoice=42
~~~

Trong console Spring Boot xuất hiện:

~~~text
processed invoice=42
~~~

Đây là hai đường quan sát khác nhau: HTTP trả về khi `convertAndSend` hoàn thành theo provider, còn consumer xử lý bất đồng bộ nên dòng console có thể xuất hiện **sau** response. Không xem status `202 Accepted` là bằng chứng việc phát hành hóa đơn nghiệp vụ đã hoàn tất.

Khi đổi physical name qua environment config, producer và listener dùng cùng property; broker phải có Queue đó. Phép thử này xác minh naming và mapping trong một môi trường lab; không xác minh TLS, failover, transaction với database, độ bền qua broker restart hay khả năng một client dev bị chặn gửi message prod.

## 9. Kiểm tra quy tắc bằng Java 17 độc lập

Bộ kiểm tra dưới đây không cần Spring/broker và **thực sự chạy được với `javac`/`java`**. Nó kiểm tra một **quy ước tự chọn**: môi trường phải nằm trong danh sách, các segment domain/subject/action chỉ dùng ASCII thường với dấu gạch ngang nội bộ, version lớn tối thiểu 1. `Kind` được lưu riêng với tên; tên không tự chứng minh Queue hay Topic trên broker.

Tạo file `DestinationConvention.java`:

~~~java
import java.util.Set;
import java.util.regex.Pattern;

public final class DestinationConvention {
    enum Kind { QUEUE, TOPIC }

    record Definition(Kind kind, String physicalName) {}

    private static final Set<String> ENVIRONMENTS =
            Set.of("dev", "test", "stg", "prod");
    private static final Pattern SEGMENT =
            Pattern.compile("[a-z][a-z0-9-]*");

    private DestinationConvention() {}

    static Definition define(
            Kind kind, String environment, String domain,
            String subject, String action, int majorVersion) {

        if (kind == null) {
            throw new IllegalArgumentException("kind is required");
        }
        if (!ENVIRONMENTS.contains(environment)) {
            throw new IllegalArgumentException(
                    "invalid environment: " + environment);
        }
        for (String segment : new String[] {domain, subject, action}) {
            if (segment == null || !SEGMENT.matcher(segment).matches()) {
                throw new IllegalArgumentException(
                        "invalid segment: " + segment);
            }
        }
        if (majorVersion < 1) {
            throw new IllegalArgumentException(
                    "major version must be positive");
        }

        String name = String.join(".", environment, domain,
                subject, action, "v" + majorVersion);
        return new Definition(kind, name);
    }

    public static void main(String[] args) {
        Definition command = define(
                Kind.QUEUE, "dev", "billing", "invoice", "issue", 1);
        Definition event = define(
                Kind.TOPIC, "prod", "sales", "order", "created", 2);

        System.out.println(command.kind() + " " + command.physicalName());
        System.out.println(event.kind() + " " + event.physicalName());

        try {
            define(Kind.QUEUE, "production", "billing",
                    "invoice", "issue", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 DestinationConvention.java
java DestinationConvention
~~~

Đầu ra **xác định chính xác**:

~~~text
QUEUE dev.billing.invoice.issue.v1
TOPIC prod.sales.order.created.v2
rejected: invalid environment: production
~~~

Đoạn kiểm tra này hữu ích trong unit test hoặc pipeline khi cần tạo tên một cách nhất quán. Tuy vậy, regex chỉ là policy ở cấp ứng dụng; **không bảo đảm rằng mọi vendor broker chấp nhận tên đó**. Đặc biệt, giới hạn độ dài, reserved names và dấu phân cách của provider cần thêm kiểm tra riêng. Việc class có thể render tên `TOPIC` không tự provision Topic trên broker.

## 10. Ràng buộc đặt tên phụ thuộc JMS provider

Các ví dụ `dev.billing.invoice.issue.v1` được chọn theo nguyên tắc tương đối an toàn, nhưng tính hợp lệ thực tế phụ thuộc provider:

| Provider | Lưu ý đặt tên |
|---|---|
| **Apache ActiveMQ Artemis** | Phân biệt address/queue và routing `anycast` (thường tương ứng Queue) / `multicast` (thường tương ứng Topic). Một số tình huống dùng fully-qualified queue name với cú pháp `address::queue`; tránh dùng `::` trong tên thông thường. |
| **IBM MQ** | Local queue name giới hạn **48 ký tự**; `SYSTEM.` là prefix tên dành cho tài nguyên do queue manager quản lý. Dấu phân cách không tạo hierarchy ACL tự động; kiểm tra tài liệu IBM cho platform và object type cụ thể. |
| **ActiveMQ Classic** | Có thể có quy ước destination kiểu phân đoạn; wildcard/composite destination và cách tạo destination là **tính năng broker-specific**, không phải quy tắc chung của JMS. |
| **Provider dùng JNDI** | Tên JNDI để lookup có thể **khác tên physical** trên broker. Registry phải nêu cả JNDI name và đích broker đã được ánh xạ. |

Với IBM MQ, ví dụ `prod.fulfillment.shipment.dispatch.v1` vẫn có chiều dài phù hợp, nhưng tên rất dài nhiều segment có thể vượt giới hạn. Đừng lấy tên Topic hoặc Queue của Artemis rồi giả định sử dụng nguyên xi trên IBM MQ. Dấu chấm trong một số sản phẩm là ký tự đặt tên hợp lệ, **không tự động phân quyền hoặc tạo thư mục**.

### Đặc biệt với Artemis

Trong Artemis, address và queue có thể là hai đối tượng riêng. Một physical name phù hợp khi gửi bằng JMS Queue không đồng nghĩa địa chỉ đó có routing type `anycast` hoặc queue được tạo đúng như dự tính. Đối với Topic, kiểm tra `multicast` và subscription queues. Tên chứa `::` có ngữ nghĩa FQQN ở những ngữ cảnh có hỗ trợ; **không dùng nó làm dấu ngăn cách domain**, vốn sẽ gây nhập nhằng giữa quy ước ứng dụng và cú pháp provider.

## 11. Version: khi nào đổi tên destination?

Không thay tên physical mỗi lần sửa payload nhỏ. Cần phân biệt:

- **Phiên bản payload/schema**: thay đổi trường, kiểu dữ liệu, quy tắc tương thích của thông điệp.
- **Phiên bản hợp đồng destination**: thay đổi mà các consumer cũ không thể tiếp tục xử lý hoặc thay đổi ý nghĩa/đường routing.

Nếu thay đổi tương thích ngược, thường giữ `prod.sales.order.created.v1` và tiến hóa schema có kiểm soát; schema có thể có version riêng trong header/payload. Nếu thay đổi không tương thích, cần đánh giá mở song song `prod.sales.order.created.v2` và quy trình cutover.

Ví dụ một migration có kiểm soát:

1. Đăng ký destination mới (Topic `v2`) và owner/ACL/retention tương ứng trong registry.
2. Triển khai consumer hiểu hợp đồng mới; tạo durable subscription trước khi phát nếu cần bắt backlog.
3. Tạm thời dual-publish hoặc bridge `v1` sang `v2` **chỉ khi có chiến lược chống gửi/nhận trùng** và xác định source of truth rõ ràng.
4. Theo dõi consumer lag, backlog, message lỗi, tỷ lệ xử lý thành công.
5. Chuyển publisher và consumer theo lịch; xác minh không còn consumer phụ thuộc `v1`.
6. Chỉ retire/delete destination cũ sau khi có bằng chứng backlog và retention đã xử lý, được owner phê duyệt và chính sách lưu trữ cho phép.

**Đổi tên trực tiếp** trong `@JmsListener` hoặc biến môi trường không tự di chuyển message đang nằm ở Queue cũ. Với durable Topic subscription, đổi tên Topic/subscription có thể tạo một luồng backlog khác. Migration phải xem là thay đổi contract, không chỉ refactor chuỗi.

## 12. Retry, DLQ, delayed message và temporary destination

Tên destination chính nên tách bạch với destination vận hành khi provider hoặc kiến trúc yêu cầu:

~~~text
prod.billing.invoice.issue.v1          (Queue xử lý chính)
prod.billing.invoice.issue.v1.retry    (Queue retry, nếu thiết kế dùng queue riêng)
prod.billing.invoice.issue.v1.dlq      (Dead-letter queue, nếu có)
~~~

Đây là **một phương án quy ước**, không phải broker sẽ tự động tạo `.retry` hoặc `.dlq` từ tên chính. Nhiều broker dùng dead-letter address, redelivery delay hoặc một DLQ chung; tên và mapping phải khớp policy thực tế. Với một broker có tên bị giới hạn 48 ký tự, cần kiểm tra cả tên dài nhất sau khi thêm hậu tố; có thể rút gọn có kiểm soát và ghi alias trong registry.

Không tạo Queue riêng cho mỗi lần retry hay mỗi attempt nếu broker đã hỗ trợ backoff/delivery count phù hợp. Giới hạn số lần thử, thiết kế poison-message handling và quan sát DLQ thường quan trọng hơn cách gắn suffix.

**TemporaryQueue/TemporaryTopic** được tạo động cho request/reply ngắn hạn, có vòng đời gắn với connection. Không áp dụng máy móc quy ước physical name dài hạn cho loại đích này; có thể log logical request ID và trace thay vì giả định tên tạm ổn định.

## 13. Multi-tenant, vùng dữ liệu và chính sách bảo mật

Có hai lựa chọn để tách tenant:

- **Destination riêng theo tenant**, ví dụ `prod.eu.sales.order.created.v1` khi mỗi vùng/tenant có chính sách độc lập. Cách này tăng số resource, ACL và quota, chỉ phù hợp khi có nhu cầu isolation thực sự.
- **Destination dùng chung** với tenant ID trong message property/payload và kiểm soát phân quyền/isolating ở tầng cần thiết. Khi đó người dùng không được chọn tùy ý một tên Topic/Queue chỉ bằng tenant ID.

Không tự thêm tenant ID, mã khách hàng hay thông tin cá nhân trực tiếp vào physical name nếu không cần thiết, vì tên dễ xuất hiện trong metric, log, dashboard và công cụ quản trị. Tham số hóa destination name bằng dữ liệu nhận từ API cần whitelist/authorization; nếu không, client có thể tạo destination ngoài vùng được phép hoặc gửi dữ liệu vào đích nhạy cảm (tùy ACL broker).

Trong broker dùng chung, prefix môi trường/domain nên kết hợp **quyền send/consume/manage riêng**. Ví dụ `billing-worker` chỉ được consume `prod.billing.invoice.issue.v1`; `order-service` chỉ được send, và service `dev` không có quyền trên destination `prod`. Kiểm tra ACL ở broker, không dùng regex tên như rào chắn bảo mật duy nhất.

## 14. Provisioning, kiểm thử và quan sát

Một destination contract nên tồn tại trong repository cấu hình hoặc nền tảng IaC, được review cùng code. Các tài nguyên broker cần thiết có thể được provision trước khi ứng dụng lên phiên bản mới. Với môi trường cần kiểm soát nghiêm ngặt, cân nhắc tắt hoặc giới hạn `auto-create` trên broker để một lỗi chính tả không âm thầm tạo Queue “mồ côi”.

Các lớp kiểm thử hữu ích:

| Kiểm thử | Cần xác minh |
|---|---|
| **Tên và logic** | Regex/allowed environments, domain owner, version, độ dài và reserved names theo provider. |
| **Cấu hình** | Giá trị logical key và broker endpoint khớp `dev`/`stg`/`prod`; thiếu config quan trọng sẽ fail-fast. |
| **Provisioning** | Physical Queue/Topic và routing type đã tồn tại đúng; số lượng subscriptions/DLQ/retention đúng. |
| **Round-trip** | Publisher gửi đến đúng destination, listener nhận và có đúng Queue/Topic semantics. |
| **Isolation** | Credential dev không thể gửi/consume từ prod; tenant/region policy không bị vượt qua. |
| **Migration** | Không bỏ sót message còn ở destination cũ; nhận trùng được xử lý an toàn. |
| **Monitoring** | Metric theo environment/domain/physical destination, backlog, redelivery, DLQ, subscription lag và owner. |

Đối với log/tracing, ghi **logical destination key**, physical name, broker alias, message ID/correlation ID, owner domain và kết quả xử lý khi phù hợp. Không log credentials hoặc toàn bộ payload nhạy cảm. Trong metrics, cẩn thận số lượng nhãn (cardinality): nếu destination có ID người dùng hoặc ID pod biến đổi liên tục, hệ thống monitoring dễ bị quá tải.

### Checklist review trước khi triển khai

- [ ] Tên phản ánh **nghiệp vụ**, rõ Queue/Topic và owner.
- [ ] Đã chọn một chiến lược cô lập môi trường: prefix, broker riêng hoặc namespace rõ ràng.
- [ ] Phân biệt logical key, physical name và subscription identity.
- [ ] Producer và consumer đọc cùng contract từ cấu hình/registry, không nối prefix tùy tiện.
- [ ] Đã xác minh giới hạn ký tự, reserved names và routing của provider.
- [ ] Đã provision destination và ACL đúng môi trường.
- [ ] Đã có retry/DLQ/retention policy và tên phụ nếu dùng.
- [ ] Đã thử round-trip, authorization failure, migration và rollback kế hoạch.
- [ ] Thay đổi tên contract có owner duyệt và lịch loại bỏ destination cũ.

## 15. Những sai lầm phổ biến

| Sai lầm | Hậu quả và cách sửa |
|---|---|
| Tên `orders` dùng cho mọi môi trường | Dễ gửi nhầm hoặc khó phân quyền; tách namespace, broker hoặc prefix môi trường. |
| Mọi service tự tạo Topic `order-created` của riêng mình | Publisher bị gắn với consumer; chuẩn hóa event contract theo domain owner. |
| Đặt tên theo pod, instance, hostname | Tạo Queue/Topic không ổn định và làm mất backlog/monitoring; tên theo nghiệp vụ, instance là metric/tag. |
| Hard-code `prod...` trực tiếp trong Java | Dễ chạy sai môi trường; externalize physical name. |
| Tưởng thêm `.dlq` làm broker tự retry | Chưa chắc; phải cấu hình dead-letter/routing policy thật. |
| Đổi `v1` thành `v2` mà không migrate backlog | Consumer cũ không nhận hết message; tổ chức cutover và kiểm tra backlog. |
| Dùng cùng physical string cho Queue và Topic rồi mặc định tương đương | JMS loại đích và routing khác; cần explicit Queue/Topic config. |
| Coi prefix môi trường là cơ chế ACL | Credential vẫn có thể được cấp nhầm quyền; kiểm tra broker authorization. |
| Tạo tên quá dài hoặc có ký tự provider không cho phép | Lỗi provisioning/runtime; kiểm tra provider constraints sớm trong CI. |
| Áp dụng naming policy cho TemporaryQueue như tài nguyên bền vững | Sai vòng đời; dùng request/reply dynamic destinations đúng API. |

## 16. Bài tập tự kiểm tra

**Bài 1.** Đội Sales phát sự kiện “đơn hàng đã được tạo”. Billing và Notification cùng cần nhận sự kiện, mỗi nhóm có thể tăng replica riêng. Chọn loại destination, tên và cách đặt subscription.

**Đáp án gợi ý:** Dùng Topic `prod.sales.order.created.v1`; Billing và Notification có **hai subscription độc lập** được định danh theo group/ý nghĩa, mỗi nhóm có thể dùng shared subscription để các replica chia message trong nhóm. Không tạo Topic riêng cho từng replica.

**Bài 2.** Dev và Prod dùng chung broker. Dev gửi nhầm `prod.billing.invoice.issue.v1` dù code đã có quy ước prefix. Vì sao?

**Đáp án gợi ý:** Prefix chỉ là tên; application vẫn có thể cấu hình sai hoặc credential có quyền quá rộng. Cần binding môi trường rõ ràng, ACL chặn dev trên prod, kiểm tra deployment và cảnh báo khi routing cross-environment.

**Bài 3.** Thay property `app.messaging.destinations.invoice-issue` từ `prod.billing.invoice.issue.v1` sang `prod.billing.invoice.issue.v2`. Những message tồn trong Queue `v1` sẽ ra sao?

**Đáp án gợi ý:** Không tự di chuyển. Chúng vẫn thuộc Queue `v1` nếu broker chưa có quy tắc chuyển riêng. Phải có chiến lược drain/bridge/cutover, kiểm tra backlog và duy trì consumer cũ đủ lâu.

**Bài 4.** Một nhóm đặt tên `prod.billing.invoice.issue.v1.dlq` nhưng sau khi listener lỗi, DLQ vẫn trống. Điều này chứng minh gì?

**Đáp án gợi ý:** Chỉ có tên thì không có routing/retry policy. Kiểm tra transaction/acknowledgement, số lần redelivery, cấu hình dead-letter address, Queue binding và quyền của broker.

**Bài 5.** Vì sao destination mang tên `prod.sales.order.created.v1` vẫn có thể hoạt động sai nếu mã sender dùng Queue còn receiver dùng Topic?

**Đáp án gợi ý:** Tên là chuỗi, còn Queue/Topic là ngữ nghĩa định tuyến. Spring `pubSubDomain` và routing type/provider phải thống nhất; cùng chuỗi không đảm bảo cùng physical destination hoặc cùng tập consumer.

## 17. Tài liệu chính thức

- [Jakarta Messaging specification — Destinations, Queue, Topic và subscriptions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1).
- [Spring Framework — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring Framework — Annotation-driven JMS listeners](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Boot — Externalized Configuration và property placeholders](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — JMS Artemis và ActiveMQ Classic](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html).
- [Apache ActiveMQ Artemis — Address model, anycast/multicast và FQQN](https://activemq.apache.org/components/artemis/documentation/latest/address-model.html).
- [IBM MQ — Naming restrictions for queues](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=reference-naming-restrictions-queues).
- [IBM MQ — Rules for naming MQ objects](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=objects-rules-naming-mq).
