# Sao lưu definitions, dữ liệu và ranh giới trách nhiệm vận hành

Một hệ thống **RabbitMQ và Spring AMQP** có thể hoạt động bình thường nhiều tháng, nhưng một sự cố xóa nhầm queue, mất volume, thay đổi sai policy hoặc hỏng cả cluster có thể đặt ra câu hỏi khó: **“Chúng ta thực sự đã sao lưu những gì, và ai chịu trách nhiệm khôi phục đến đâu?”**

Nhiều đội vận hành định kỳ xuất file `definitions.json` và tin rằng đã sao lưu toàn bộ RabbitMQ. Trên thực tế, **definitions chứa cấu hình logic** như virtual host, exchange, queue, binding và policy; **không chứa các message đang đợi trong queue**. Ngược lại, sao chép dữ liệu trên đĩa của một node mà không có chiến lược nhất quán cho cluster, định danh node và transaction nghiệp vụ cũng không phải một bản khôi phục chắc chắn có thể sử dụng.

Bài này thuộc chương **Triển khai và vận hành** của module **SPRING_AMQP**. Ta sẽ liên hệ topology `RabbitTemplate`/`@RabbitListener`/`RabbitAdmin`, exchange–queue–binding, publisher confirms, consumer ACK, retry, dead-letter, transactional outbox và idempotency để xây **chiến lược sao lưu, phục hồi và phân định trách nhiệm** có thể diễn tập, đo được RPO/RTO và kiểm chứng kết quả nghiệp vụ.

> **Nguyên tắc xuyên suốt:** **backup definitions ≠ backup message data ≠ backup trạng thái nghiệp vụ**. High availability, queue durability, dead-letter và backup cũng là những cơ chế khác nhau; cần kết hợp có chủ đích thay vì dùng một cơ chế thay thế tất cả.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **definitions**, **message/data store của RabbitMQ** và **system of record** của ứng dụng.
2. Giải thích những thành phần thường có/không có trong bản export definitions và rủi ro bảo mật của file đó.
3. Xác định RPO, RTO, phạm vi lỗi và cấp độ phục hồi cho từng queue/luồng nghiệp vụ.
4. Lựa chọn giữa **khôi phục topology**, **physical/data backup được hỗ trợ** và **replay từ nguồn sự kiện bền vững**.
5. Hiểu vì sao durable queue, persistent message, quorum replication và publisher confirms **không tương đương backup**.
6. Lập runbook khôi phục có kiểm tra vhost, permission, exchange, binding, consumer, message và business effect.
7. Phân định trách nhiệm giữa **application team**, **RabbitMQ/platform team**, **hạ tầng** và **nghiệp vụ/on-call**.
8. Kiểm thử thảm họa, mất message chưa ACK, rollback dữ liệu và xử lý trùng sau restore bằng outbox/inbox.

## 2. Ba lớp dữ liệu không được đánh đồng

Khi nói “backup RabbitMQ”, trước tiên cần hỏi **đang bảo vệ loại thông tin nào**.

| Lớp | Ví dụ | Nơi thuộc trách nhiệm lưu trữ | Nếu chỉ có lớp này |
| --- | --- | --- | --- |
| **Definitions/topology** | Vhost, user, permissions, exchange, queue, binding, policy, parameter | Broker cấu hình/management hoặc GitOps/IaC | Tạo lại cấu trúc, **không phục hồi message cũ** |
| **Message data ở broker** | Persistent message nằm trong queue, quorum log, stream segment, một phần metadata delivery | RabbitMQ storage/volume theo loại queue | Có thể lấy lại dữ liệu môi giới trong phạm vi bản backup **nếu cách sao lưu/restore được hỗ trợ** |
| **Business/system-of-record data** | Đơn hàng trong PostgreSQL, event outbox, payment ledger, processed-event inbox | Database và hệ thống nghiệp vụ | Có thể xây lại một số message/projection bằng replay nếu **nguồn sự kiện và chính sách giữ dữ liệu** còn đầy đủ |

Ngoài ba lớp chính còn có **configuration/infra**: file cấu hình broker, enabled plugins, TLS certificates, secrets, DNS, network policies, Kubernetes manifests, Terraform, monitoring và alert rules. Chúng cần quy trình lưu giữ/triển khai riêng; xuất definitions **không** tự chứa mọi cấu hình của container, hệ điều hành và hạ tầng.

~~~mermaid
flowchart TB
  APP["Ứng dụng Spring AMQP"] -->|"RabbitTemplate"| EX["Exchange / binding"]
  EX --> Q["Queue và message data"]
  Q -->|"@RabbitListener"| CON["Consumer + business commit"]
  DB["Database nguồn + outbox"] --> APP
  CON --> DEST["Database đích + inbox"]

  DEF["Definitions backup"] -. "Tạo lại topology" .-> EX
  DEF -. "Tạo lại queue trống" .-> Q
  DISK["Physical/data backup hợp lệ"] -. "Khôi phục dữ liệu theo runbook" .-> Q
  DBBK["DB backup / event log"] -. "Khôi phục và replay có đối soát" .-> DB
~~~

### 2.1. Ví dụ thất bại điển hình

Giả sử có một queue `billing.invoice.queue` chứa 25.000 lệnh chưa xử lý. Đội vận hành xuất `definitions.json` vào 10:00; 10:05 một thao tác xóa nhầm queue khiến toàn bộ message biến mất; 10:10 nhập definitions để tạo lại queue.

Kết quả: exchange, queue, binding có thể lại tồn tại với tên và chính sách tương ứng, nhưng **25.000 lệnh không xuất hiện chỉ nhờ import definitions**. Muốn phục hồi chúng, cần message backup hợp lệ, outbox/event source có thể replay, hệ thống đối soát hoặc một nguồn dữ liệu nghiệp vụ khác.

### 2.2. Phạm vi thảm họa phải xác định từ đầu

Các sự cố có mức độ khác nhau:

- Một consumer crash; queue và message vẫn tồn tại.
- Một RabbitMQ node mất kết nối tạm thời.
- Một disk/volume của một node bị mất.
- Một quorum queue mất quá nhiều replica để đạt đa số.
- Operator xóa queue/vhost hoặc policy sai.
- Cả cluster bị xóa hoặc toàn bộ storage bị hỏng.
- Ứng dụng hoặc DB bị rollback không đồng thời với RabbitMQ.
- Mất secrets hoặc khóa TLS làm cluster không khởi động/reconnect được.

Không dùng cùng một câu “RabbitMQ có 3 node nên không cần backup” để trả lời mọi trường hợp trên.

## 3. RPO, RTO và nguồn dữ liệu có thể tái tạo

Hai mục tiêu chuẩn của kế hoạch disaster recovery:

- **RPO — Recovery Point Objective:** khoảng mất dữ liệu tối đa chấp nhận được tính theo thời điểm nguồn; ví dụ có thể mất tối đa vài phút message, hoặc **RPO gần 0** cho lệnh thanh toán đã được DB commit.
- **RTO — Recovery Time Objective:** khoảng thời gian tối đa để khôi phục khả năng phục vụ nghiệp vụ ở mức được định nghĩa; ví dụ 15 phút cho queue đơn hàng, 4 giờ cho analytics batch.

Hai chỉ tiêu phải được gắn với **luồng nghiệp vụ**, không chỉ broker:

| Luồng | Mẫu RPO | Mẫu RTO | Cơ chế gợi ý |
| --- | --- | --- | --- |
| Lệnh thanh toán | Không mất lệnh đã ghi nhận bền vững | Vài chục phút | Transactional outbox, publisher confirms, idempotent consumer, reconciliation |
| Thông báo marketing | Có thể chấp nhận tái dựng trong một khoảng | Vài giờ | Recreate topology và replay từ campaign database |
| Event audit bắt buộc lưu | Theo quy định và hợp đồng | Theo mức ưu tiên nghiệp vụ | Event source bền vững, backup DB/ledger và đối soát |
| Analytics có thể xây lại | Có thể replay toàn bộ kỳ xử lý | Qua đêm | Reprocessing từ nguồn dữ liệu gốc, metrics để theo dõi tiến độ |
| Queue thử nghiệm tạm | Có thể mất | Không cam kết | Provision lại từ IaC |

**Các số trên chỉ là ví dụ để thiết kế**. RPO/RTO thực tế phải được business owner phê duyệt cùng ngân sách storage, tần suất snapshot, retention, thời gian replay và khả năng chịu duplicate.

### 3.1. Ma trận “cái gì có thể phục hồi?”

| Nguồn còn tồn tại | Topology | Message chưa xử lý | Business state |
| --- | --- | --- | --- |
| Chỉ có `definitions.json` | Có thể tái tạo nếu definitions đầy đủ/tương thích | **Không** | Không |
| Chỉ có application code + `RabbitAdmin` | Chỉ những topology ứng dụng khai báo và có quyền tạo | **Không** | Không |
| Physical backup broker hợp lệ | Theo phạm vi storage và metadata được sao lưu | Có thể đến recovery point; phụ thuộc loại queue/cluster/quy trình | Không tự bao gồm DB ngoài broker |
| Outbox/event log bền vững | Không tự tạo topology | Có thể **phát lại** một phần/toàn bộ event còn lưu | Có thể tái tạo projection tùy tính đầy đủ của event |
| Database backup + quy trình reconciliation | Không tự tạo topology | Có thể tái tạo command/event có nguồn nghiệp vụ | Khôi phục được trong phạm vi DB snapshot/log |

**Khả năng replay là một bảo đảm do ứng dụng thiết kế**, không phải tính năng mặc định của mọi queue RabbitMQ.

## 4. Definitions backup thực sự chứa gì?

Một bản export definitions RabbitMQ thông thường có thể bao gồm những đối tượng logic:

- Virtual hosts.
- Users và phần metadata cần cho authentication (có thể gồm password hashes/tags, tùy phiên bản/cách export).
- Permissions và topic permissions.
- Exchanges.
- Queues và **thuộc tính khai báo** như durable, auto-delete, arguments, queue type.
- Bindings.
- Policies và operator policies.
- Parameters và global parameters.

Tập trường cụ thể có thể phụ thuộc phiên bản RabbitMQ, plugins và cách export. Vì vậy cần **kiểm tra nội dung JSON thực tế** và thử import trong staging, không mặc định mọi object ứng dụng cần đều được xuất giống nhau ở mọi phiên bản.

### 4.1. Những thứ definitions không bảo vệ

Một bản export definitions **không phải bản chụp runtime state**. Nó không khôi phục:

- **Bodies/properties của message đang nằm trong queue**, kể cả persistent messages.
- Delivery đang unacked, delivery tags, trạng thái ACK của từng consumer.
- Kết quả database transactions, outbox/inbox và external API.
- TCP connections, channels, active consumers, publisher confirm futures.
- Byte-level storage, quorum Raft logs, stream segments.
- Binary plugins, phiên bản Erlang/RabbitMQ, OS packages.
- Toàn bộ TLS private keys, secrets ngoài RabbitMQ, volume và node-specific config.
- Metrics history, dashboards/alerts và incident log ngoài broker.

Một queue `durable=true` được import lại **chỉ định rằng queue mới phải bền vững theo semantics broker**; không có nghĩa nó được khôi phục với số message ready/unacked trước lúc hỏng.

### 4.2. Bản export còn có rủi ro bảo mật

Definitions có thể chứa **thông tin nhạy cảm**, ví dụ password hashes, danh tính user, permission regex và tham số plugin/connection của hệ thống tích hợp. Không đăng nguyên file definitions lên wiki công khai hay commit vào repository không được phép chỉ vì đây là “JSON cấu hình”.

Cần áp dụng:

1. Mã hóa file backup ở nơi lưu trữ.
2. Phân quyền đọc/ghi tối thiểu; có retention và audit.
3. Không đưa nguyên export vào log hoặc CI artifacts công khai.
4. Kiểm tra các secret/connection parameters nhạy cảm theo plugin.
5. Quy định quy trình thu hồi credential khi bản backup bị lộ.
6. Bảo vệ khóa giải mã và đường truy cập backup **tách khỏi** cluster bị sao lưu.

## 5. Export/import definitions: thao tác minh họa

Với những phiên bản RabbitMQ có lệnh tương ứng, có thể thao tác từ môi trường vận hành được cấp quyền:

~~~sh
# Export cấu hình logic ra file JSON bảo vệ bằng quyền truy cập phù hợp.
rabbitmqctl export_definitions /secure-backups/rabbitmq-definitions.json

# Sau khi đã kiểm tra mục tiêu và runbook restore:
rabbitmqctl import_definitions /secure-backups/rabbitmq-definitions.json
~~~

Đây là lệnh **minh họa quy trình**. Cú pháp, công cụ quản trị (CLI, Management API, `rabbitmqadmin`), quyền cần thiết và thứ tự import phải kiểm tra theo phiên bản RabbitMQ thực tế. Đường dẫn `/secure-backups/...` chỉ là ví dụ: thực tế file phải được chuyển tới **kho backup tách biệt, mã hóa, có checksum và lịch kiểm tra restore**.

Có thể quản lý definitions qua giao diện Management UI/API trong môi trường cho phép. Dù dùng công cụ nào, đừng import trực tiếp một definitions export từ production vào một cluster production đang chạy mà không có kế hoạch về **xung đột tài nguyên và quyền**.

### 5.1. Các bước kiểm tra một bản definitions backup

1. Xác nhận nguồn là đúng broker/cluster và môi trường.
2. Ghi thời điểm export, RabbitMQ version, plugins liên quan, định danh backup và checksum.
3. Xác minh JSON hợp lệ, dung lượng không bằng 0 và các nhóm resource mong đợi có mặt.
4. Đếm vhosts, exchanges, queues, bindings, policies trước/sau; không dựa chỉ vào số byte.
5. Lưu bản backup vào kho độc lập với node/volume đang chạy.
6. Chạy thử **import vào môi trường tách biệt** với đúng quyền và công cụ.
7. Kiểm tra tên/loại queue, exchange type, routing key và permissions.
8. Lưu kết quả test cùng thời gian restore và những incompatibility phát hiện.

### 5.2. Import definitions không phải công cụ migration thần kỳ

Một object đã tồn tại nhưng không tương thích về arguments/type có thể gây lỗi khai báo hoặc cần thay thế theo migration plan. Ví dụ:

- Queue cùng tên nhưng classic vs quorum.
- Thay `x-dead-letter-exchange`, max length hoặc TTL bằng argument không tương đương.
- Exchange cùng tên nhưng type khác.
- User/vhost hoặc policy được quản trị bởi hệ thống khác.
- Plugin cần cho exchange type/parameter không có trên môi trường đích.

Vì vậy import definitions phải có **change plan, kiểm tra compatibility, quyền và rollback strategy**. Trên cluster trống, cũng cần xác minh broker/plugins/vhosts/credentials được khởi tạo đủ để nhận cấu hình.

## 6. Definitions as Code và RabbitAdmin: hai mức khai báo

Có thể chia trách nhiệm topology thành:

1. **Infrastructure/IaC quản lý nền tảng**: broker cluster, nodes, storage, vhost, user/permissions, TLS, plugins, policy/operator policy, backup jobs.
2. **Application declarables**: exchange, queue, binding mà ứng dụng sở hữu, khai báo bằng `RabbitAdmin` hoặc manifest/pipeline được phê duyệt.
3. **Definitions export**: bản ghi hiện trạng để phục hồi/kiểm tra drift; không nhất thiết là nguồn sự thật duy nhất.

Một mẫu Spring AMQP:

~~~java
package com.example.rabbitmq.operations;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InvoiceTopology {

    public static final String EXCHANGE = "billing.commands";
    public static final String ROUTING_KEY = "invoice.generate";
    public static final String WORK_QUEUE = "billing.invoice.queue";

    @Bean
    DirectExchange billingExchange() {
        return new DirectExchange(EXCHANGE, true, false);
    }

    @Bean
    Queue invoiceQueue() {
        return QueueBuilder.durable(WORK_QUEUE).build();
    }

    @Bean
    Binding invoiceBinding() {
        return BindingBuilder.bind(invoiceQueue())
                .to(billingExchange())
                .with(ROUTING_KEY);
    }
}
~~~

`RabbitAdmin` có thể dùng connection factory của ứng dụng để khai báo những bean trên khi điều kiện phù hợp. Nhưng nó **không** thể tự khôi phục **message trước khi queue bị xóa**, và không thể mở connection nếu vhost/user/permission cần thiết chưa được nền tảng provision.

### 6.1. Ai nên có quyền tạo queue?

Có hai chính sách đều có thể hợp lý:

- **Ứng dụng tự khai báo**: phù hợp môi trường động, đội ứng dụng chủ động topology; phải hạn chế quyền và kiểm soát migration.
- **Nền tảng provision trước**: phù hợp production kiểm soát chặt, ứng dụng chỉ publish/consume; team platform giữ quyền configure, app chủ yếu cần write/read tương ứng.

Không để cả IaC và `RabbitAdmin` liên tục khai báo cùng một queue với **arguments khác nhau**. Nên chọn **chủ sở hữu duy nhất của topology** hoặc hợp đồng thay đổi rõ ràng.

### 6.2. Drift detection

Một khác biệt nhỏ giữa config mong muốn và thực tế có thể làm khôi phục sai:

| Drift | Hậu quả |
| --- | --- |
| Thiếu binding `invoice.generate` | Publisher có thể được confirm nhưng command không vào queue |
| Queue bị đổi TTL | Message hết hạn trước khi xử lý |
| DLX không tồn tại hoặc routing key sai | Poison message không tới DLQ mong muốn |
| Policy quorum/delivery-limit khác | Hành vi redelivery và độ bền đổi |
| Permission mới thiếu `write`/`read` | Publish/consume lỗi dù login thành công |
| Durable queue bị thay bằng auto-delete queue | Lifecycle và tính bền vững thay đổi |

Nên có kiểm tra **definitions hiện tại so với GitOps/IaC expected state**, đồng thời kiểm tra end-to-end publish/consume; chỉ so tên resource chưa đủ.

## 7. Durable queue, persistent messages và publisher confirms

Để lưu message bền vững trong RabbitMQ AMQP 0-9-1, cần hiểu nhiều yếu tố phối hợp:

- **Durable queue**: queue có thể tồn tại qua broker restart theo semantics loại queue và cấu hình.
- **Persistent message**: publisher đánh dấu delivery mode persistent khi publish.
- **Publisher confirms**: broker thông báo kết quả chấp nhận publish, cần xử lý ACK/NACK và unknown outcome.
- **Queue type, disk và replica health**: ảnh hưởng khả năng chống lỗi phần cứng/node.
- **Consumer ACK**: broker biết consumer đã xử lý delivery ở mức messaging.
- **Business commit**: database hoặc side effect đích đã hoàn tất.

Không có thành phần nào trên đây đơn độc tạo ra bản backup để phục hồi sau thao tác **xóa queue** hoặc sau khi **cả cluster mất storage**.

### 7.1. Sơ đồ các cửa sổ độ tin cậy

~~~mermaid
sequenceDiagram
    participant DB as Database nguồn
    participant P as Outbox relay / RabbitTemplate
    participant B as RabbitMQ
    participant C as @RabbitListener
    participant D as Database đích

    DB->>DB: COMMIT business + outbox(E42)
    P->>B: Publish E42 persistent
    B-->>P: Publisher confirm ACK
    B->>C: Deliver E42
    C->>D: COMMIT effect + inbox(E42)
    C-->>B: Consumer ACK
~~~

Nếu publisher không nhận confirm, event có thể đã vào broker hoặc chưa; khi retry phải giữ **`eventId` ổn định**. Nếu consumer commit rồi connection chết trước ACK, broker có thể giao lại cùng event; cần **idempotency**. Nếu **toàn bộ broker bị restore về snapshot cũ**, các event được chấp nhận **sau thời điểm snapshot** có thể không còn ở broker, dù relay đã đánh dấu published; phải có **replay hoặc reconciliation từ nguồn**.

### 7.2. Vì sao “durable + persistent” chưa phải exactly once?

Durable/persistent bảo vệ trong các điều kiện lưu trữ và restart mà broker hỗ trợ. Chúng không đảm bảo:

- Message sẽ không bị xóa do operator, TTL, max-length, policy hoặc auto-delete phù hợp.
- Consumer không nhận duplicate sau lỗi kết nối.
- Source DB và RabbitMQ commit nguyên tử.
- Bản tin còn tồn tại sau khi restore một snapshot cũ.
- External HTTP/payment side effect xảy ra đúng một lần.

**Exactly-once business effect** cần logic nghiệp vụ, idempotency key và đối soát; không phải là một thuộc tính của queue durable.

## 8. Quorum queues và streams: replication không thay thế backup

Trong RabbitMQ, **quorum queue** sử dụng replication/consensus để tăng khả năng chịu lỗi node theo cấu hình; streams có mô hình log/retention và cơ chế lưu trữ riêng. Nhưng:

- Nhiều replica có thể **cùng chấp nhận một thao tác xóa queue**; replication không cứu khỏi xóa logic hợp lệ.
- TTL, retention, max length hoặc consumer ACK có thể làm dữ liệu không còn trong queue dù cluster khỏe.
- Replica có thể mất đồng thời vì sự cố storage cùng miền lỗi, cấu hình sai hoặc cả cluster bị hỏng.
- Một bản snapshot lấy riêng từ **một node bất kỳ** không mặc định khôi phục được trạng thái nhất quán của cả quorum/stream.
- Khôi phục vật lý yêu cầu hiểu cluster identity, metadata, các node và phiên bản; không nên lấy một thư mục dữ liệu ra rồi gắn tùy tiện vào cluster mới.

Quorum replication là **high availability** trong những tình huống lỗi nhất định; backup là **khả năng quay lại trạng thái được bảo vệ theo recovery point**. Cả hai cần được thiết kế riêng.

### 8.1. DLQ và retry queue cũng là dữ liệu

Message trong **dead-letter queue** hoặc **delay/retry queue** vẫn là dữ liệu nghiệp vụ cần bảo vệ nếu đó là con đường duy nhất để điều tra/phục hồi. Khi export definitions, ta chỉ lấy được tên DLX, DLQ và bindings; **không lấy được nội dung DLQ**.

Nếu DLQ được đặt TTL ngắn hoặc bị purge khi restore, message lỗi chưa triage có thể biến mất. Phải có:

- Owner và retention policy cho DLQ.
- Quy trình export/quarantine/replay **khi yêu cầu RPO đòi hỏi**.
- Xác minh routing trên broker sau phục hồi.
- Giới hạn retry và tránh vòng DLX quay lại work queue.
- Khóa dedup giữ nguyên `eventId` khi replay.

## 9. Sao lưu message data: snapshot phải nhất quán và được hỗ trợ

Sao lưu các file dữ liệu RabbitMQ khác với export definitions. Broker lưu metadata và message state vào những cấu trúc riêng theo **loại queue, phiên bản và topology cluster**: message stores, quorum logs, stream segments và metadata nội bộ.

**Không có quy tắc an toàn chung là “copy thư mục dữ liệu của một node đang chạy rồi restore vào broker bất kỳ”.** Cần có runbook phù hợp với phiên bản RabbitMQ, queue type, storage backend và cấu trúc cluster; runbook đó phải được **diễn tập thành công** trước khi coi là khả năng DR thực tế.

### 9.1. Điều kiện của backup vật lý

| Điều kiện | Ý nghĩa vận hành |
| --- | --- |
| **Consistency** | Các file và metadata thuộc cùng recovery point nhất quán |
| **Cluster scope** | Với quorum/stream, hiểu dữ liệu trên các replica; một volume không đại diện toàn bộ cluster |
| **Node identity** | Tên node, cookie, cluster membership và đường dẫn có thể ảnh hưởng restore |
| **Version compatibility** | RabbitMQ/Erlang, plugins, feature flags và schema phải được hỗ trợ |
| **Storage integrity** | Checksum, quyền file, mã hóa, khả năng đọc lại |
| **Downtime/coordination** | Offline backup có thể cần dừng; online snapshot phải có cơ chế nhất quán được chứng minh |
| **Restore drill** | Có thể dựng môi trường cô lập, mở queue và thực sự consume message |
| **Security** | Backup có thể chứa payload nhạy cảm; cần bảo vệ như dữ liệu production |

### 9.2. Offline copy, volume snapshot và snapshot đang chạy

**Offline backup nhất quán** dừng hoặc cô lập các thành phần liên quan theo runbook được hỗ trợ, lấy bản sao tại trạng thái ổn định rồi cho cluster hoạt động lại. Nó có thể cần cửa sổ bảo trì.

**Storage snapshot** dùng snapshot của VM, filesystem, cloud volume hoặc CSI. Snapshot của **một volume** không tự chứng minh tính nhất quán của **nhiều node RabbitMQ**, nhất là quorum queues và streams. Nếu snapshot trực tuyến, cần quy trình phối hợp/quiesce hay giải pháp đã được kiểm chứng.

Sao chép file bằng `rsync` trong khi broker đang ghi liên tục **không mặc định** tạo bản backup khôi phục được: các file được đọc ở thời điểm khác nhau và trạng thái cluster có thể đổi giữa chừng.

### 9.3. Tuyệt đối tránh suy luận “clone một node là backup cluster”

- Không gắn thư mục data của node A thành node B mà thiếu quy trình được hỗ trợ.
- Không ghép snapshot từ nhiều ngày khác nhau thành một quorum queue.
- Không tự chỉnh dữ liệu nội bộ để đổi node name hoặc cluster identity.
- Không reset/xóa volume để cluster “xanh” khi dữ liệu chưa được bảo vệ.
- Không import chồng definitions tùy tiện lên physical restore đã có metadata.

Nếu chưa từng phục hồi thử bản backup vật lý với cấu hình tương đương, **chưa có bằng chứng RPO/RTO**.

## 10. Replay từ nguồn nghiệp vụ: phương án phục hồi cấp ứng dụng

Nhiều hệ thống event-driven có **system of record** ngoài RabbitMQ: bảng Order trong PostgreSQL, transactional outbox, event store hoặc business ledger. Khi nguồn dữ liệu còn đầy đủ, có thể tái tạo message thay vì phụ thuộc vào việc lấy lại từng byte message store.

Một chiến lược:

1. Dựng cluster/vhost/topology sạch bằng IaC + definitions.
2. Khôi phục credentials, quyền và các service kết nối.
3. Xác định **recovery point của broker** và khoảng event bị thiếu.
4. Lấy event từ outbox/event archive/ledger với `eventId` gốc.
5. Publish có kiểm soát tới exchange đúng, theo dõi confirms và returns.
6. Consumer dùng inbox/idempotency, version guard và rate limit.
7. Đối soát kết quả DB đích, DLQ và các lệnh có side effect ngoài hệ thống.

### 10.1. Tùy nguồn, replay có giới hạn khác nhau

| Nguồn | Có thể làm gì? | Điều kiện/rủi ro |
| --- | --- | --- |
| Outbox còn payload | Phát lại event đã commit | Retention đủ dài, ID không thay đổi |
| Event store append-only | Replay stream theo checkpoint | Schema evolution, ordering và capacity |
| Bảng nghiệp vụ hiện tại | Tạo lại projection/command có thể suy ra | Không phải lúc nào tái tạo được event lịch sử |
| Business ledger | Reconcile payment/invoice | Phải tránh lặp side effect tiền bạc |
| Chỉ có broker definitions | Tạo queue/exchange rỗng | **Không có message để replay** |

### 10.2. Cửa sổ nguy hiểm: đã SENT nhưng broker restore về trước đó

~~~text
09:00  Broker snapshot S0
09:05  DB commit OrderPaid E42 + outbox E42
09:06  Relay publish E42, nhận publisher confirm ACK
09:07  Relay cập nhật outbox E42 = SENT
09:10  Broker mất dữ liệu; restore về snapshot S0
09:11  Queue ở broker không còn E42
~~~

Nếu relay chỉ đọc `state='NEW'` thì **E42 không được gửi lại**, dù source DB vẫn còn trạng thái OrderPaid. **Outbox giữ event trước publish không mặc định cứu được message đã SENT nhưng broker bị rollback về snapshot cũ.**

Biện pháp:

- Retain event history đủ lâu và **replay một khoảng gồm cả SENT** theo recovery point.
- Có downstream checkpoint/consumer ledger để đối chiếu sự kiện đã commit.
- Chạy business reconciliation để tìm command/event thực sự thiếu.
- Dùng physical restore nếu phù hợp rồi reconcile delta với source.
- Với payment và side effect không idempotent, **không replay mù quáng**.

### 10.3. Retention liên quan trực tiếp đến recovery

Thời gian giữ outbox SENT, event archive và inbox phải xét:

- Tần suất snapshot và điểm rollback xa nhất.
- Thời gian phát hiện sự cố bị thiếu message.
- Thời gian khôi phục cluster và xả backlog.
- Thời gian đối soát với downstream/đối tác.
- TTL của idempotency keys và yêu cầu audit/retention.

Nếu outbox bị xóa vài phút sau khi publish nhưng DR có thể cần phục hồi về snapshot một ngày trước, **không có đủ dữ liệu để replay** trừ khi đã có nguồn khác.

## 11. Broker và database có thể được phục hồi ở thời điểm khác nhau

RabbitMQ và business database có backup/replication riêng. Vì vậy cùng một sự cố có thể tạo hai trạng thái không đồng nhất:

| Trường hợp | Điều có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Broker về 09:00, DB nguồn ở 09:15 | Những event đã publish sau snapshot biến mất khỏi broker | Replay/reconcile nguồn → đích |
| Broker về 09:00, DB đích ở 09:15 | Message đã ACK trước sự cố có thể xuất hiện lại | Inbox/idempotency, không lặp side effect |
| DB đích lùi nhưng broker hiện tại | Broker đã xóa message sau ACK, DB đích mất kết quả | Business reconciliation và backfill |
| DB nguồn lùi nhưng broker hiện tại | Broker có event không còn trạng thái nguồn tương ứng | Đối chiếu system-of-record, không xử lý mù |
| Nhiều hệ thống phục hồi ở các điểm khác nhau | Missing event và duplicate cùng tồn tại | Đối soát bằng ID/version/ledger |

**Queue depth=0 không chứng minh DR hoàn tất**. Có thể broker chưa nhận message đã mất trong DB, hoặc message đã xử lý và ACK nhưng DB đích bị rollback.

### 11.1. Inbox để chịu được redelivery/replay

Ví dụ trong PostgreSQL:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer lưu marker với unique constraint và cập nhật nghiệp vụ trong **cùng DB transaction**. Khi replay cùng `eventId`, duplicate được phát hiện và bỏ qua side effect; listener vẫn có thể xác nhận delivery thành công.

Nếu xử lý gọi HTTP/payment bên ngoài DB, cần **idempotency key tại hệ thống đích**, lưu trạng thái công việc và đối soát khi kết quả không rõ. Retention của marker phải phù hợp với khoảng thời gian có thể replay event cũ.

## 12. Hai runbook phục hồi không nên trộn lẫn

### 12.1. Runbook A — dựng cluster trống và replay

Dùng khi nguồn nghiệp vụ có thể dựng lại message và không cần/không thể restore vật lý.

1. Provision broker cluster, storage, TLS, plugins, network từ IaC.
2. Tạo vhost, user/permissions và import definitions bằng công cụ tương thích.
3. Kiểm tra exchanges, queue type, durable, bindings, policy, DLX/DLQ.
4. Tạm giảm hoặc đóng băng live traffic nếu cần để tránh lẫn replay.
5. Xác minh publisher confirms/returns và consumer readiness.
6. Chọn replay window từ event archive/outbox/ledger theo checkpoint.
7. Phát lại với **eventId gốc**, theo thứ tự/partition thích hợp và rate limit.
8. Bật consumer có kiểm soát, quan sát ACK, DLQ, duplicates, processing lag.
9. Reconcile kết quả nghiệp vụ, thiếu/trùng event và external side effects.
10. Mở traffic bình thường khi tiêu chí RTO/SLO được phê duyệt.

**Đặc điểm:** definitions tạo topology mới, **message chỉ có khi replay**.

### 12.2. Runbook B — physical/data restore đã được hỗ trợ

Dùng khi có backup và quy trình restore đã **được kiểm chứng trên đúng version, queue type và cluster**.

1. Xác định backup ID, recovery point, checksum, version và phạm vi node.
2. Cô lập môi trường đích; ngăn live producers/consumers ghi thêm trong khi phục hồi.
3. Khôi phục đúng tập storage, metadata và node identities theo runbook được hỗ trợ.
4. Khởi động cluster, kiểm tra membership/quorum, feature flags và dữ liệu đọc được.
5. Không import definitions chồng lên metadata đã restore nếu chưa rà soát conflict.
6. Kiểm tra queue count, ready/unacked, queue types, policies, DLX và replica health.
7. Smoke test publish/consume cô lập với confirms và ACK.
8. Tính delta giữa broker recovery point và DB/event source hiện tại.
9. Replay/reconcile delta với ID gốc; chấp nhận duplicates qua inbox.
10. Phê duyệt kết quả nghiệp vụ, khôi phục traffic rồi giám sát hậu kiểm.

**Không triển khai B nếu mới chỉ “backup thành công” nhưng chưa có bài diễn tập restore thành công.**

### 12.3. Tại sao không ghép A+B tùy ý?

Physical restore có thể đã chứa metadata và message data; import definitions từ một thời điểm khác có nguy cơ thay đổi queue arguments, permissions và policies. Ngược lại, chỉ import definitions vào cluster mới sẽ tạo topology nhưng **không có bản tin cũ**.

Cần có **decision gate**: RPO/RTO yêu cầu gì, backup nào hợp lệ, dữ liệu nguồn có thể replay tới đâu, và ai có thẩm quyền chọn phương án.

## 13. RabbitMQ trên Kubernetes và phạm vi hạ tầng

Trong Kubernetes/StatefulSet/operator, một phần thông tin là **manifest**, phần khác là **dữ liệu thật trên PVC**:

| Thành phần | Nguồn quản lý thường gặp | Có chứa message không? |
| --- | --- | --- |
| Operator CRD, StatefulSet, service, DNS | GitOps/IaC | Không |
| RabbitMQ definitions | Export/GitOps | Không |
| Secrets, certificates, Erlang cookie | Secret Manager hoặc Kubernetes Secret bảo vệ | Không chứa message nhưng thiết yếu cho kết nối/identity |
| PVC/PV, snapshot | Storage/CSI/cloud backup | Có thể chứa data store, **chỉ khả dụng khi consistency/restore được hỗ trợ** |
| Broker config/plugins/feature flags | Config-as-code và image | Không tự chứa message |
| Business DB/PITR | Database backup/WAL | Chứa system-of-record, outbox/inbox nếu được lưu |
| Metrics/alert rules | Monitoring/IaC | Không, nhưng cần để kiểm chứng DR |

**Một CSI snapshot của một PVC không đồng nghĩa snapshot hợp lệ của RabbitMQ cluster có nhiều node.** Cần ghi lại node names, membership, plugin/feature flag version, restore network và phương án dữ liệu phù hợp. Không vô tình để cluster restore staging gia nhập production.

### 13.1. Backup phải ở ngoài miền lỗi

Một volume snapshot đặt cùng vùng/storage với broker có thể cũng mất trong thảm họa. Cần:

- Kho tách miền lỗi theo RPO/RTO.
- Mã hóa in transit/at rest và khóa giải mã được bảo vệ.
- Retention/versioning, audit và giới hạn quyền xóa; có thể dùng immutable backups.
- Checksum/integrity tests.
- Cách truy cập backup và giải mã khi vùng chính không còn hoạt động.
- Thời gian tải/restore thực tế nằm trong RTO.

## 14. Ma trận trách nhiệm ứng dụng – nền tảng – nghiệp vụ

Đừng giả định “RabbitMQ do platform quản lý” đồng nghĩa platform chịu trách nhiệm **mọi message bị mất** hoặc **mọi payment được tạo hai lần**.

| Hạng mục | Application team | RabbitMQ/Platform team | Infra/Security/DB team | Business/SRE |
| --- | --- | --- | --- | --- |
| Event schema, `eventId`, semantics | **Chủ trì** | Phối hợp | — | Phê duyệt invariant |
| Exchange/queue/binding app-owned | Định nghĩa và kiểm thử | Provision/review theo policy | IAM/quyền | Phê duyệt thay đổi quan trọng |
| Node/cluster/queue-type/version | Hiểu contract | **Chủ trì** | Compute/storage | Change coordination |
| Definitions export và kiểm thử import | Xác nhận topology mình dùng | **Chủ trì runbook** | Offsite storage | Kiểm thử DR |
| Physical backup/restore nếu được hỗ trợ | Xác định RPO cần đạt | **Consistency và procedure** | Snapshots, backup security | Phê duyệt RPO/RTO |
| Outbox, inbox, replay, idempotency | **Chủ trì** | Capacity hỗ trợ replay | DB backup/PITR | Reconciliation |
| Consumer ACK, retry, DLQ | **Chủ trì** | Queue policies, DLX semantics | — | Replay authorization |
| TLS, secret, vhost permissions | Client config đúng | Broker auth và quyền | Identity/secrets lifecycle | Audit |
| Broker monitoring | Queue-level app signals | Node/resource alarms | Host/storage alarms | Điều phối incident |
| Business validation sau restore | So sánh source/đích | Xác nhận broker healthy | DB integrity | **Phê duyệt hoàn thành** |

Đây là **mẫu phân vai**, không phải quy định cứng. Từng tổ chức cần chỉ định tên người accountable, người thực thi và người được phép approve các thao tác delete, purge, restore hoặc replay.

### 14.1. Bảy câu hỏi bàn giao bắt buộc

1. Ai là **owner** của từng queue, binding, DLQ và retention policy?
2. Ai có quyền **delete/purge**? Có guardrail, audit và approval không?
3. Ai đảm bảo definitions được export, lưu và **test restore**?
4. Ai bảo vệ message data nếu không thể replay từ business DB?
5. Ai bảo vệ event đã `SENT` sau broker snapshot và chọn replay window?
6. Ai cho phép replay lệnh có thể gửi email, xuất hóa đơn hoặc thu tiền lần nữa?
7. Khi broker “green” nhưng dữ liệu nghiệp vụ thiếu/trùng, ai xác nhận DR hoàn tất?

### 14.2. Hợp đồng vận hành cho từng queue

Một runbook tối thiểu nên liệt kê:

- Broker, virtual host, exchange, routing key, queue, queue type và owner.
- Durable, auto-delete, TTL, max length, DLX/DLQ, chính sách retry.
- PII/data classification, encryption và retention.
- Business SLO, RPO/RTO và điều kiện mất dữ liệu chấp nhận.
- Source-of-truth, eventId/aggregate key và replay/compensation procedure.
- Backup location, integrity check, test restore date, runbook version.
- Dashboard, alert owner, escalation path và dấu hiệu hoàn thành.

## 15. Backup database và dữ liệu nguồn replay

Ví dụ hai bảng trong PostgreSQL:

~~~sql
CREATE TABLE outbox_events (
    event_id       UUID PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    event_type     VARCHAR(100) NOT NULL,
    payload        JSONB NOT NULL,
    status         VARCHAR(20) NOT NULL DEFAULT 'NEW',
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at   TIMESTAMPTZ
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

**Outbox** là nguồn sự kiện có thể publish; **inbox** giúp consumer tránh side effect trùng. Cả hai thuộc **database ứng dụng**, không nằm trong definitions export. Chúng phải nằm trong chính sách backup/PITR của database và retention đủ dài so với replay window.

### 15.1. Đừng xóa SENT quá sớm

Nếu event được xóa ngay sau confirm, nhưng broker có thể được restore về một ngày trước, application có thể không còn payload để replay. Có thể tách bảng outbox vận hành khỏi **event archive** có retention phù hợp hoặc giữ business ledger khác.

### 15.2. Reconciliation phải dựa trên ID, không chỉ số lượng

Một số nguồn đối soát:

| Nguồn | Dữ liệu kiểm tra |
| --- | --- |
| Order DB | Danh sách OrderPaid có eventId |
| Outbox/event store | Event đã tạo, payload, thời điểm, version |
| RabbitMQ/consumer logs | Publish confirms, delivery, retry, DLQ |
| Billing DB | Hóa đơn đã được tạo với eventId/commandId |
| Inbox | Event mà consumer đã xử lý |
| External payment provider | Idempotency keys và kết quả payment thực tế |

Tổng số event nguồn bằng tổng số hóa đơn đích **không chứng minh từng event khớp**: có thể một event thiếu và một event khác bị tạo hai lần. Cần đối chiếu **eventId, aggregate version, status và side effect đích**.

## 16. Ví dụ Spring AMQP: kiểm chứng đường publish và consume sau restore

Khôi phục exchange/queue/binding là điều kiện cần nhưng chưa đủ. Một bài smoke test cần xác minh **producer được broker xác nhận**, **message route tới queue đúng**, **consumer xử lý** và **business database commit**.

### 16.1. Command có ID ổn định

~~~java
package com.example.rabbitmq.operations;

import java.time.Instant;
import java.util.UUID;

public record GenerateInvoice(
        UUID commandId,
        String orderId,
        long orderVersion,
        Instant occurredAt
) {}
~~~

Khi replay sau disaster recovery, `commandId` của cùng một command phải **giữ nguyên**. Nếu phát lại với UUID mới, downstream khó nhận ra lệnh cũ, đặc biệt với các nghiệp vụ như xuất hóa đơn hoặc thanh toán.

### 16.2. Publisher confirms và returns

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.internal
    virtual-host: /orders

    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true

    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 4
        prefetch: 20
~~~

Ví dụ dùng Spring Boot/Spring AMQP AMQP 0-9-1 truyền thống. Credentials/TLS phải nằm trong secret store. Khi dùng DTO JSON, cần message converter thích hợp.

~~~java
package com.example.rabbitmq.operations;

import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ConfirmedInvoicePublisher {

    private final RabbitTemplate template;

    public ConfirmedInvoicePublisher(RabbitTemplate template) {
        this.template = template;
    }

    public void publish(GenerateInvoice command) throws Exception {
        String id = command.commandId().toString();
        var correlation = new CorrelationData(id);

        template.convertAndSend(
                InvoiceTopology.EXCHANGE,
                InvoiceTopology.ROUTING_KEY,
                command,
                message -> {
                    message.getMessageProperties().setMessageId(id);
                    message.getMessageProperties().setDeliveryMode(
                            MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                correlation);

        var confirm = correlation.getFuture()
                .get(5, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            throw new IllegalStateException(
                    "RabbitMQ NACK: " + confirm.getReason());
        }
        if (correlation.getReturned() != null) {
            throw new IllegalStateException(
                    "Invoice command không route được");
        }
    }
}
~~~

Mẫu này chỉ minh họa một publish có confirm, **không thay thế transactional outbox relay**. Nếu chờ confirm timeout, outcome có thể chưa rõ: broker đã nhận hoặc chưa. Không phát lại bằng command ID khác; giữ event nguồn để retry an toàn.

### 16.3. Listener có idempotency

~~~java
package com.example.rabbitmq.operations;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceConsumer {

    private final InvoiceApplicationService service;

    public InvoiceConsumer(InvoiceApplicationService service) {
        this.service = service;
    }

    @RabbitListener(queues = InvoiceTopology.WORK_QUEUE)
    public void receive(GenerateInvoice command) {
        service.applyOnce(command);
        // Chỉ return khi DB transaction nghiệp vụ đã commit.
    }
}
~~~

`InvoiceApplicationService` cần triển khai transaction và unique key theo `commandId`. Spring `AcknowledgeMode.AUTO` ACK khi listener hoàn tất thành công theo lifecycle container; nếu DB commit trước ACK rồi connection chết, command có thể redeliver. Idempotency phải ngăn side effect lặp lại.

Một smoke test sau restore đạt yêu cầu khi:

1. Producer dùng đúng connection/vhost và exchange đã tồn tại.
2. Publisher confirm được xác minh, không có returned message ngoài dự kiến.
3. Binding route đúng command vào queue đích.
4. Listener hoạt động, xử lý và commit DB trước ACK.
5. Replaying cùng `commandId` không tạo hóa đơn thứ hai.
6. Monitoring ghi lại kết quả và end-to-end latency.

## 17. Backup cadence và bằng chứng phục hồi

Backup job trả exit code 0 **không đồng nghĩa** có khả năng restore. Cần lưu lịch và kết quả thử thực tế.

| Hạng mục | Khi nào nên thực hiện | Bằng chứng |
| --- | --- | --- |
| Definitions export | Sau thay đổi topology và theo lịch | Checksum, vhost/queue/binding count, test import |
| GitOps/IaC snapshot | Mỗi thay đổi được phê duyệt | Có thể dựng cluster sạch |
| DB backup/PITR | Theo RPO hệ thống nghiệp vụ | Restore và WAL/PITR thành công |
| RabbitMQ data backup hợp lệ | Theo RPO nếu dùng phương án vật lý | Consistent snapshot + restore drill |
| Outbox/event archive | Theo replay window và retention policy | Payload/ID cũ còn truy cập được |
| DLQ/quarantine retention | Theo thời gian cần triage/replay | Message lỗi không biến mất trước khi xử lý |
| DR exercise | Định kỳ và sau thay đổi nền tảng lớn | Đo RPO/RTO, xác minh business commit |

### 17.1. Metadata đi kèm mỗi backup

~~~yaml
backup:
  id: rabbit-orders-2026-11-26-001
  environment: production
  source_cluster: orders-rabbitmq
  capture_time_utc: "2026-11-26T02:00:00Z"
  backup_kind: definitions
  rabbitmq_version: "example-version"
  checksum: "sha256:example-checksum"
  encrypted: true
  restore_test_status: pending
~~~

Đây là **schema minh họa** do đội vận hành tự định nghĩa, không phải cấu hình RabbitMQ. Với physical backup, bổ sung node/volume identity, queue types, consistency method, plugin versions, recovery point và phiên bản runbook đã được thử nghiệm.

### 17.2. Kho backup phải dùng được trong thảm họa

Kiểm tra không chỉ khả năng **ghi** backup mà còn:

- Backup được mã hóa, có quyền đọc/giải mã khi site chính không hoạt động.
- Checksum/integrity hợp lệ.
- Kho tách miền lỗi, không bị xóa theo cùng production volume.
- Versioning/retention giữ đủ lịch sử để quay về bản trước nếu bản mới hỏng.
- Chống xóa nhầm/ransomware theo chính sách bảo mật.
- Thời gian lấy và đọc backup thực tế nằm trong RTO.

## 18. Monitoring sau restore: broker khỏe chưa chắc nghiệp vụ đúng

Sau restore, cần hai lớp dashboard.

**Broker health:**

- Node readiness, cluster membership, quorum/stream availability.
- Exchange/queue/binding/policy/DLX trong đúng vhost.
- `messages_ready`, `messages_unacknowledged`, consumer count.
- Publish rate, publisher confirms/NACK/returns, consumer ACK/redelivery.
- Memory/disk resource alarms, storage errors và connection failures.

**Business recovery:**

- Outbox pending/oldest age, tổng event trong recovery window.
- Event IDs đã phát, IDs đã commit ở đích, IDs thiếu theo reconciliation.
- Duplicate suppression, version conflicts, business error rate.
- DLQ chưa triage, retry attempts, kết quả external payment/invoice.
- Độ trễ từ event được tạo đến business commit.

### 18.1. Các kết luận sai thường gặp

| Thấy trên dashboard | Chưa thể kết luận | Cần xem |
| --- | --- | --- |
| Queue ready=0 | Mọi event đều đã đến queue | Outbox, publisher returns, source IDs |
| Consumer count>0 | Consumer đang commit thành công | Handler duration, DB commits |
| ACK rate cao | Nhiều event mới thực sự thành công | Dedup count, business goodput |
| DLQ=0 | Không có message lỗi mất mát | DLX route, error logs, drop policy |
| Broker node healthy | DR hoàn tất | Cross-system reconciliation |
| Outbox NEW=0 | Không có event thiếu | SENT sau broker snapshot, event archive |

**Đừng tắt hết alerts trong lúc DR.** Có thể silence có thời hạn những cảnh báo backlog được dự báo, nhưng cần giữ resource alarms, publisher timeout, consumer lost, DLQ và reconciliation mismatch.

## 19. Runbook điều phối một sự cố DR

1. **Ngăn thao tác phá hủy:** không purge, reset node, xóa volume trước khi có bằng chứng và approval.
2. **Phân loại:** lỗi node, quorum thiếu, xóa queue, hỏng storage, mất cluster hay sai definitions?
3. **Xác định recovery point và RPO/RTO:** backup nào hợp lệ, event archive còn từ đâu?
4. **Chọn runbook A hoặc B:** dựng topology + replay, hoặc physical restore đã được kiểm chứng.
5. **Cô lập đích phục hồi:** tránh live traffic làm trộn dữ liệu trước khi hoàn tất restore.
6. **Khôi phục nền tảng:** broker nodes, storage, TLS, plugins, vhosts, permissions, topology.
7. **Kiểm tra kỹ thuật:** publish confirm/return, listener, queue routing, DLX và consumer ACK.
8. **Tính delta nghiệp vụ:** nguồn/đích có recovery points khác nhau; tìm event thiếu/trùng.
9. **Replay có rate limit:** cùng eventId, thứ tự/partition phù hợp, theo dõi downstream capacity.
10. **Xác minh dữ liệu:** business ledger, invoice/payment outcomes, inbox/outbox/DLQ.
11. **Phê duyệt khôi phục traffic:** application/platform/business/SRE đồng ý theo ownership.
12. **Hậu kiểm:** đo RPO/RTO thật, backup integrity, script/runbook gaps, alert rules và controls.

Nếu mất dữ liệu vượt RPO vì backup hoặc replay source thiếu, cần **báo minh bạch phạm vi mất và kế hoạch đối soát**, không đánh dấu thành công chỉ vì RabbitMQ process đã lên.

## 20. Diễn tập backup/restore và failure injection

Mọi thử nghiệm phá hủy chỉ chạy trên **staging cô lập**, dữ liệu giả lập, broker/vhost và database thử nghiệm. Không chạy `reset`, `purge`, delete queue hoặc ghi đè backup production ngoài change window và approval.

### Kịch bản A — Export/import definitions trên cluster trống

1. Tạo vhost, exchange, queue, binding và policy trong môi trường test.
2. Export definitions, lưu checksum và metadata.
3. Dựng cluster mới tách biệt, nhập definitions.
4. So lại queue type, durable flag, arguments, binding và quyền.
5. Publish/consume một event thử có ID rõ ràng.

**Kỳ vọng:** topology được tạo lại nhưng **message cũ không tự xuất hiện**.

### Kịch bản B — Queue có 1.000 message, chỉ có definitions backup

1. Publish 1.000 message vào durable queue thử.
2. Export definitions, không sao lưu message store.
3. Tạo cluster trống và import definitions.
4. Quan sát queue tồn tại nhưng không còn 1.000 message trước đó.
5. Xem event archive/outbox có đủ payload để replay không.

**Kỳ vọng:** người học chứng minh được giới hạn của definitions backup.

### Kịch bản C — Binding bị xóa nhầm

1. Trong staging, bỏ binding giữa exchange và work queue.
2. Publish có mandatory/returns đã bật.
3. Kiểm tra returned message hoặc kết quả routing theo broker.
4. Khôi phục binding từ nguồn cấu hình được phê duyệt.
5. Kiểm tra event đã publish trong khoảng lỗi có cần replay không.

**Kỳ vọng:** sửa topology không tự khôi phục event từng bị unroutable.

### Kịch bản D — Physical backup khôi phục thật

1. Dùng cơ chế snapshot đã được kiểm chứng cho loại queue/version đang thử.
2. Ghi recovery point, cluster identities và checksum.
3. Khôi phục ở cluster hoàn toàn cô lập.
4. Kiểm tra node membership/quorum, message count và dữ liệu đọc được.
5. Publish/consume, kiểm tra publisher confirm và consumer ACK.
6. Đo RTO thực tế và chênh lệch dữ liệu so với recovery point.

**Kỳ vọng:** bản backup **thực sự** có thể restore, không chỉ được copy ra file.

### Kịch bản E — Broker lùi thời gian, outbox đã SENT

1. Chụp snapshot test ở `t0`.
2. Sau `t0`, ghi `E42` vào outbox, publish và mark SENT.
3. Restore broker về `t0`, giữ database nguồn hiện tại.
4. Kiểm tra E42 vắng ở broker nhưng đã SENT trong DB.
5. Reconciliation xác định E42 thiếu, replay với **cùng eventId**.
6. Xác minh downstream commit hoặc bỏ qua duplicate an toàn.

**Kỳ vọng:** replay window không chỉ gồm outbox NEW.

### Kịch bản F — Broker restore làm xuất hiện message đã ACK

1. Snapshot broker khi `E43` vẫn đang ở queue.
2. Consumer xử lý E43, commit DB và ACK.
3. Restore broker test về snapshot chứa E43.
4. Cho E43 redeliver.
5. Inbox unique constraint phát hiện event đã xử lý.

**Kỳ vọng:** không tạo duplicate business effect sau rollback broker.

### Kịch bản G — Database đích restore lùi, broker không lùi

1. Consumer xử lý và ACK `E44`.
2. Restore riêng DB đích về trước thời điểm commit của E44.
3. Xác minh broker không còn E44.
4. Reconciliation tìm nghiệp vụ thiếu, quyết định replay/compensation.
5. Kiểm tra nguồn và đích nhất quán trở lại.

**Kỳ vọng:** broker healthy không đồng nghĩa business state đầy đủ.

### Kịch bản H — Definitions xung đột khi import

1. Tạo queue test với queue type/TTL/DLX hiện tại.
2. Thử import definitions có arguments khác hoặc plugin chưa sẵn sàng.
3. Ghi lại lỗi và hành vi của công cụ quản trị.
4. Áp dụng migration plan hợp lệ, không tự xóa queue có message.
5. So lại topology và smoke test.

**Kỳ vọng:** import definitions không tự migrate mọi queue/policy.

### Kịch bản I — DLQ bị mất trong một lần tái dựng topology

1. Đưa message lỗi vào terminal DLQ test.
2. Export definitions và dựng cluster mới.
3. Kiểm tra DLQ tồn tại nhưng message cũ không xuất hiện.
4. Thử khôi phục từ nguồn đã bảo vệ riêng hoặc event archive.
5. Replay có chọn lọc khi nguyên nhân lỗi đã được sửa.

**Kỳ vọng:** DLQ cũng cần chính sách retention/backup dữ liệu.

### Kịch bản J — Cluster khởi động nhưng app không vào được

1. Dựng broker mới từ IaC/definitions.
2. Cố tình thiếu quyền vhost hoặc truststore trên application test.
3. Kiểm tra auth/TLS/authorization failures.
4. Khôi phục credential/permission theo quy trình.
5. Xác minh publisher, listener và RabbitAdmin chỉ có quyền cần thiết.

**Kỳ vọng:** cluster boot không phải mốc hoàn thành DR.

### Kịch bản K — Replay quá nhanh gây resource alarm

1. Tạo một tập event archive test lớn.
2. Relay replay nhanh hơn khả năng consumer xử lý.
3. Đo queue bytes, disk/memory watermark, publisher confirmations.
4. Thêm rate limit/bulkhead và giảm concurrency nếu downstream quá tải.
5. Kiểm tra backlog được xả, không có mất/trùng business effect.

**Kỳ vọng:** DR cần backpressure, không chỉ phát lại nhanh nhất có thể.

### Kịch bản L — Backup bị hỏng hoặc không giải mã được

1. Trong bài diễn tập, giả lập thiếu một backup hoặc không lấy được khóa giải mã.
2. Kiểm tra preflight phát hiện lỗi integrity/access.
3. Chuyển phương án dự phòng đã xác định, không thử thao tác phá hủy mù quáng.
4. Ghi lại RPO/RTO thực tế sau khi đổi phương án.
5. Cập nhật backup alerts, quyền truy cập và kiểm thử restore.

**Kỳ vọng:** quy trình DR có đường dự phòng và phát hiện lỗi sớm.

## 21. Sai lầm vận hành thường gặp

| Sai lầm | Hậu quả | Hành động đúng |
| --- | --- | --- |
| Gọi export definitions là full backup | Không khôi phục message | Tách cấu hình, broker data và business source |
| Coi quorum replication là backup | Xóa logic hoặc mất cluster vẫn làm mất data | HA + backup/replay có kiểm chứng |
| Copy data dir node đang chạy rồi coi là snapshot nhất quán | Rủi ro file/metadata không đồng bộ | Quy trình snapshot được hỗ trợ và DR drill |
| Lấy snapshot một replica để restore toàn quorum | Cluster state không hợp lệ | Cluster-aware procedure |
| Import definitions chồng physical restore vô điều kiện | Xung đột queue arguments/policies | Chọn đúng restore path |
| Chỉ replay bản ghi outbox NEW | Event SENT sau broker snapshot bị mất | Giữ archive và replay/reconcile theo recovery point |
| Chỉ so tổng số message/event | Thiếu và trùng có thể cùng tồn tại | Đối soát theo eventId/version |
| Phục hồi broker nhưng bỏ qua DB recovery point | Missing/duplicate side effect | Cross-system reconciliation |
| Replay message với ID mới | Không chặn được duplicate | Stable ID, inbox và idempotency |
| Không bảo vệ DLQ | Message lỗi chưa triage biến mất | DLQ retention/quarantine |
| Lưu backup cùng volume broker | Mất nguồn là mất cả backup | Offsite/cross-fault-domain storage |
| Không chạy restore drill | Backup có thể sai version hoặc thiếu key | Diễn tập định kỳ |
| Tắt hết monitoring khi DR | Không thấy resource alarm hoặc replay errors | Giữ critical alerts |
| Tuyên bố xong vì “broker green” | Business có thể còn thiếu hóa đơn | Chữ ký nghiệm thu dựa trên reconciliation |

## 22. Checklist trước production

- [ ] Có inventory của cluster/vhost/exchange/queue/binding/DLQ/policy và owner.
- [ ] Có RPO/RTO theo từng business flow và phương án backup/replay tương ứng.
- [ ] Definitions được export, mã hóa, lưu ngoài miền lỗi, có checksum và test import.
- [ ] IaC/GitOps chứa cấu hình broker, plugin, TLS, policy, permissions phù hợp.
- [ ] Nếu có physical data backup, đã xác minh consistency và restore trên đúng version/queue type.
- [ ] Hiểu quorum/stream replication là high availability, không phải backup.
- [ ] Không coi durable queue/persistent message là bảo đảm chống xóa logic.
- [ ] Business DB có backup/PITR, ghi được recovery point rõ ràng.
- [ ] Outbox/event archive giữ payload và event SENT đủ lâu cho replay window.
- [ ] Consumer có stable event ID, inbox, transaction và ACK sau commit.
- [ ] Side effect ngoài DB có idempotency key và reconciliation.
- [ ] Có retention/quarantine cho DLQ và retry queues quan trọng.
- [ ] Hai runbook logical rebuild và physical restore tách biệt, có decision gate.
- [ ] Backup có mã hóa, integrity test và khóa giải mã tiếp cận được trong DR.
- [ ] Có dashboard broker lẫn business reconciliation, theo dõi confirms/returns/ACK/DLQ.
- [ ] Đã thử queue deletion, binding missing, broker rollback, DB rollback và replay duplicate.
- [ ] Đã đo RTO đến **business commit**, không chỉ lúc broker boot.
- [ ] Có owner/approval cho purge/delete/replay và quy trình hậu kiểm.

## 23. Tài liệu đối chiếu và tổng kết

Khi xây runbook, cần kiểm tra tài liệu chính thức theo **RabbitMQ version, queue type và công cụ vận hành** đang triển khai:

- [RabbitMQ — Definitions](https://www.rabbitmq.com/docs/definitions)
- [RabbitMQ — Backup and Restore](https://www.rabbitmq.com/docs/backup)
- [RabbitMQ — Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability)
- [RabbitMQ — Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx)
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/)

**Definitions backup** tái dựng cấu hình nhưng **không chứa message cũ**. **Broker data backup** cần consistency và cluster-aware restore được kiểm chứng. **Replay từ outbox/event store** có thể tái tạo những event bị thiếu khi còn nguồn dữ liệu, nhưng phải xét cả event đã đánh dấu SENT và database restore khác thời điểm. **Quorum replication, durable queue, publisher confirms, consumer ACK và DLQ** hỗ trợ độ tin cậy trong các phạm vi khác nhau, không thay thế hoàn toàn backup.

Trong **SPRING_AMQP**, đội ứng dụng chịu trách nhiệm message identity, transaction, inbox/outbox, replay và business reconciliation; đội platform chịu trách nhiệm hạ tầng RabbitMQ, topology/definitions và runbook broker restore; đội infra/security bảo vệ storage/secrets; business owner phê duyệt RPO/RTO và kết quả nghiệp vụ.

Câu hỏi sau một thảm họa không chỉ là **“RabbitMQ đã chạy lại chưa?”**, mà là: **“Topology đã đúng chưa, message nào còn/thiếu so với nguồn, tác dụng nghiệp vụ nào đã commit, event nào cần replay, và ai xác nhận dữ liệu đã nhất quán trở lại?”**




