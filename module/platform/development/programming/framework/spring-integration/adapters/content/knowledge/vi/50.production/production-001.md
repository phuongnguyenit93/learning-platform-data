# Checklist cấu hình adapter trước triển khai production trong Spring Integration

> **Chương:** Production  
> **Bài học:** Checklist cấu hình adapter trước triển khai  
> **Module:** Spring Integration Adapters  
> **Phạm vi:** Inbound/outbound adapter, gateway, poller, MessageChannel và kết nối File, SFTP, HTTP, JMS, AMQP, Kafka, cơ sở dữ liệu.

## 1. Mục tiêu và kết quả đầu ra

Sau bài học, bạn có thể:

1. Phân biệt chức năng và hành vi vận hành của inbound adapter, outbound adapter, gateway, poller và MessageChannel.
2. Review các cấu hình tối thiểu về message contract, timeout, retry, idempotency, acknowledgement, transaction, dead-letter và backpressure.
3. Xây checklist riêng cho các adapter File, SFTP, HTTP, JMS, AMQP, Kafka và JDBC.
4. Kiểm tra TLS, xác thực, secret, quyền truy cập, giới hạn tài nguyên, khởi động/dừng và triển khai nhiều replica.
5. Chứng minh xử lý an toàn trong các failure window: xử lý thành công nhưng chưa ack, timeout sau side effect, upload file dở hoặc pod chết giữa transaction.
6. Xây test plan, dashboard, runbook, tiêu chí go/no-go và phương án rollback có bằng chứng.

**Bài toán xuyên suốt:** Dịch vụ Spring Boot nhận file đơn hàng qua SFTP, chuẩn hóa thành message, ghi database và phát sự kiện Kafka. Một số luồng khác gọi API đối tác qua HTTP, đọc hàng đợi JMS/AMQP hoặc poll JDBC. Local chạy được, nhưng production có nhiều pod, mạng không ổn định và downstream chậm. Checklist cần bảo đảm không làm mất dữ liệu, không xử lý trùng nghiệp vụ và có thể điều tra, phục hồi.

**Phạm vi phiên bản:** Bài trình bày các nguyên tắc có thể áp dụng rộng rãi. Tên lớp, method, thuộc tính Spring Integration DSL và khả năng của broker/client có thể thay đổi theo phiên bản Spring Integration, Spring Boot và hệ đích. Ví dụ minh họa phải được kiểm tra lại với **phiên bản thực tế của dự án** trước khi đưa vào production.

## 2. Cổng kiểm tra go/no-go trước khi triển khai

Mỗi mục cần có **owner, bằng chứng kiểm thử, trạng thái PASS/FAIL hoặc ngoại lệ được phê duyệt**.

| Cổng | Câu hỏi review | Bằng chứng |
|---|---|---|
| **G1 — Contract** | Payload/header/schema/giới hạn dữ liệu có rõ? | Schema, ví dụ và contract test |
| **G2 — Delivery** | Message được xem là nhận/xử lý/ack thành công lúc nào? | Sơ đồ commit/ack và crash test |
| **G3 — Idempotency** | Retry và replay có tạo side effect lặp? | Business key, unique constraint, test |
| **G4 — Timeout** | Connect, read, gateway reply, session và poll timeout có giới hạn? | Cấu hình và timeout drill |
| **G5 — Retry** | Có retry owner, backoff, max attempt, phân loại lỗi? | Retry plan, test rate limit/network |
| **G6 — Error path** | Message lỗi đi đâu, ai có thể replay, khi nào alert? | Error flow, DLQ/quarantine, runbook |
| **G7 — Transaction** | Đã xác định ranh giới DB/broker/file/API? | Transaction diagram và failure matrix |
| **G8 — Capacity** | Queue, thread, poller, connection pool có giới hạn? | Load test, sizing, backlog policy |
| **G9 — Security** | TLS, host key, secret, ACL và PII có được bảo vệ? | Security signoff, rotation test |
| **G10 — Observability** | Có log/correlation, metrics, dashboard và alert? | Dashboard và alert drill |
| **G11 — Lifecycle** | Rolling deploy/restart/shutdown có giữ message? | Graceful shutdown và crash test |
| **G12 — Operations** | Có owner, canary, pause/resume, rollback và runbook? | Biên bản vận hành và go/no-go |

Ba câu hỏi phải trả lời được trước production: **(a) message được giữ bền vững ở đâu; (b) ai chịu trách nhiệm retry nếu lỗi; (c) khi retry, điều gì ngăn tác động nghiệp vụ bị nhân đôi?**

Không nên cho phép triển khai nếu các rủi ro cốt lõi như mất dữ liệu không kiểm soát, credential không an toàn hoặc không xác định được ranh giới ack/commit còn tồn tại.

## 3. Xác định đúng loại endpoint và MessageChannel

Spring Integration ghép **Message** (payload + headers), **MessageChannel** và endpoint thành luồng tích hợp.

| Thành phần | Vai trò | Checklist vận hành |
|---|---|---|
| **Inbound channel adapter** | Chuyển sự kiện/tài nguyên từ hệ ngoài thành message; không có reply theo hợp đồng một chiều | Nguồn, checkpoint, poller/listener, filter, retry |
| **Outbound channel adapter** | Gửi message ra hệ ngoài, thường một chiều | Timeout, xác nhận kết quả, idempotency, side effect |
| **Inbound gateway** | Nhận request và trả reply qua IntegrationFlow | Reply timeout, status/error, giới hạn request |
| **Outbound gateway** | Gọi endpoint ngoài và chờ reply | Correlation, timeout, retry, duplicate request |
| **Poller** | Đọc nguồn theo lịch, có thể theo batch | Scheduling, max messages, transaction, pause |
| **Transformer** | Chuyển message contract | Schema, charset, type, header propagation |
| **Filter/Router** | Lọc/chọn nhánh xử lý | Rule, fallback, discarded message, audit |
| **Service activator/handler** | Chạy nghiệp vụ và side effect | Idempotency, transaction, error boundary |
| **Error flow** | Nhận và xử lý lỗi theo cơ chế đã cấu hình | ErrorMessage, retry, quarantine, alert |

### 3.1. Channel và ranh giới xử lý

| Channel | Đặc tính | Rủi ro cần kiểm thử |
|---|---|---|
| \`DirectChannel\` | Gọi handler đồng bộ qua thread đang gửi | Handler chậm giữ thread nguồn, exception có thể truyền về caller |
| \`ExecutorChannel\` | Chuyển xử lý qua TaskExecutor | Transaction context không tự đi qua thread; queue/thread saturation, ordering |
| \`QueueChannel\` | Buffer để poller/consumer lấy message | Queue in-memory không tự bền vững qua restart; capacity/MessageStore |
| \`PublishSubscribeChannel\` | Gửi tới nhiều subscriber | Tình trạng khi một nhánh lỗi, khả năng phát trùng/thiếu nhánh |
| \`PriorityChannel\` | Ưu tiên theo giá trị đã xác định | Starvation, thứ tự thực thi khác input |

**Không nhầm bất đồng bộ với bền vững.** Một ExecutorChannel hoặc QueueChannel in-memory có thể giúp tách tốc độ nhưng không mặc định bảo đảm message vẫn còn sau process crash. Nếu cần durability, thiết kế MessageStore bền vững hoặc broker/transaction phù hợp và chứng minh bằng test.

### 3.2. Sơ đồ review một flow

~~~mermaid
flowchart LR
    EXT["File / SFTP / HTTP / JMS / AMQP / Kafka / JDBC"] --> IN["Inbound endpoint"]
    IN --> CH["MessageChannel"]
    CH --> VALID["Validate / normalize"]
    VALID --> DEDUPE["Idempotency check"]
    DEDUPE --> BIZ["Business transaction"]
    BIZ --> OUT["Outbound adapter / gateway"]
    OUT --> DEST["Hệ đích"]
    VALID -. "Payload invalid" .-> Q["Quarantine / DLQ"]
    BIZ -. "Temporary error" .-> RETRY["Retry + backoff có giới hạn"]
    RETRY -. "Hết lượt" .-> Q
    Q --> OPS["Alert / replay runbook"]
    IN --> OBS["Metrics / tracing"]
    DEST --> OBS
~~~

Sơ đồ này mô tả trách nhiệm **logic**, không hàm ý toàn bộ file, HTTP, DB và broker nằm trong một transaction ACID. Review phải xác định chính xác điểm “đã nhận”, “đã lưu bền vững”, “đã xử lý”, “đã gửi” và “đã được đích xác nhận”.

## 4. Hợp đồng message và idempotency

### 4.1. Checklist hợp đồng

- [ ] Payload được định nghĩa: JSON/XML/CSV/binary/file reference/POJO và encoding.
- [ ] Có schema/version, required fields, null/absent/empty semantics và giới hạn kích thước.
- [ ] Xác định business key, correlation ID, trace context, source, tenant, timestamp.
- [ ] Chọn **idempotency key ổn định qua retry/replay**, không mặc định dùng \`MessageHeaders.ID\` được tạo mới.
- [ ] Validate trước khi phát sinh side effect nghiệp vụ.
- [ ] Header propagation giữa HTTP/JMS/AMQP/Kafka/file được thiết kế rõ; không mặc định mọi transport giữ nguyên header.
- [ ] Có hợp đồng về ordering, timestamp, version và xử lý event đến muộn.
- [ ] Có quy định dữ liệu nhạy cảm được phép log/truyền đi.
- [ ] Producer và consumer đã chạy contract test khi schema thay đổi.

Ví dụ envelope của **ứng dụng**, không phải schema mặc định của Spring Integration:

~~~json
{
  "schemaVersion": "1.0",
  "eventId": "evt-order-98765-v3",
  "eventType": "OrderSubmitted",
  "source": "partner-sftp",
  "occurredAt": "2026-11-23T08:00:00Z",
  "tenantId": "tenant-a",
  "correlationId": "corr-101",
  "payload": {
    "orderId": "ORD-98765",
    "revision": 3,
    "amount": 500000,
    "currency": "VND"
  }
}
~~~

Một khóa dedupe có thể là \`(source, eventId)\` hoặc \`(tenant, orderId, revision)\` **nếu hợp đồng nghiệp vụ bảo đảm duy nhất**. File name hoặc correlation ID không mặc nhiên đáp ứng điều đó.

### 4.2. Delivery semantics

| Mức bảo đảm | Ý nghĩa | Biện pháp |
|---|---|---|
| **At-most-once** | Không cố giao lại trong đường xử lý; có thể mất khi lỗi | Chỉ dùng nếu nghiệp vụ chấp nhận mất |
| **At-least-once** | Có thể giao lại nếu chưa được xác nhận | Consumer idempotent, retry có giới hạn |
| **Effectively once về nghiệp vụ** | Tác động nghiệp vụ không lặp dù message được giao lại | Unique key, transaction, bảng processed events |
| **Exactly-once trong phạm vi cụ thể** | Một số nền tảng hỗ trợ giao dịch và semantics đặc biệt | Nêu rõ phạm vi; không tự suy rộng qua HTTP/DB/file |

**Failure window phải thử:** Consumer ghi DB thành công rồi chết trước khi commit Kafka offset hoặc acknowledge JMS/AMQP. Nguồn giao lại; nếu DB không có idempotency, một đơn hàng có thể được tạo hai lần.

### 4.3. Mẫu xử lý idempotent

~~~text
handle(message):
    validateContract(message)
    key = stableBusinessKey(message)

    begin db transaction
        if key already processed:
            commit
            return ALREADY_DONE
        applyBusinessChange(key)
        recordProcessedKeyWithUniqueConstraint(key)
        appendOutboxEvent(key, outputEvent)
    commit db transaction

    # Outbox publisher gửi sự kiện theo retry policy.
    # Ack/checkpoint nguồn theo hợp đồng đã xác định.
~~~

Mã giả bỏ qua chi tiết transaction isolation và race condition. Trong production cần **unique constraint** hoặc khóa thích hợp, không chỉ SELECT trước INSERT. Nếu DB commit nhưng Kafka publish lỗi, transactional outbox giúp ghi nhận nghĩa vụ phát sau này. Một local database transaction không tự gộp cả HTTP, SFTP và broker.

### 4.4. Checklist transaction/ack

- [ ] Xác định ai ack/commit và khi nào.
- [ ] Có xử lý crash **trước side effect**, **sau side effect nhưng trước ack**, **sau ack**.
- [ ] Không ack trước khi điều kiện hoàn thành nghiệp vụ được đáp ứng.
- [ ] Side effect outbound có idempotency hoặc cơ chế đối soát/bù trừ.
- [ ] Có per-target outcome nếu một message đi tới nhiều hệ ngoài.
- [ ] Test retry, replay và duplicate cùng lúc từ nhiều consumer.
- [ ] Không ghi “exactly-once end-to-end” nếu không chứng minh được toàn bộ phạm vi.

## 5. Poller, scheduler và giới hạn tài nguyên

### 5.1. Checklist poller

- [ ] Chọn fixed delay, fixed rate hoặc cron theo nhịp dữ liệu và sức chịu hệ nguồn.
- [ ] Đặt giới hạn message mỗi lượt như \`maxMessagesPerPoll\` khi endpoint hỗ trợ.
- [ ] Poller không busy-loop khi nguồn rỗng hoặc lỗi mạng.
- [ ] Kiểm soát concurrency, scheduler pool, thời gian quét và tổng số inflight.
- [ ] Nếu nhiều replica, có phân vùng nguồn, distributed claim/lock hoặc giải pháp tương đương.
- [ ] Đã kiểm tra transaction boundary khi poll và khi xử lý downstream.
- [ ] Có exception handling, retry, alert và khả năng pause/resume.
- [ ] Có trạng thái checkpoint/metadata sống sót qua restart nếu luồng yêu cầu.
- [ ] Thử network timeout, source không phản hồi, batch lớn và poison input.
- [ ] Có graceful shutdown để ngừng lấy mới mà vẫn xử lý inflight an toàn.

**Fixed delay** và **fixed rate** có khác biệt về cách lên lịch; phải kiểm tra scheduler/phiên bản của ứng dụng. Không dùng poller quá nhanh để che lỗi throughput: khi downstream chậm, batch sẽ dồn và tăng áp lực tài nguyên.

### 5.2. Ví dụ Java DSL nhập file

~~~java
@Configuration
class FileIngressConfig {

    @Bean
    MessageChannel incomingFiles() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow fileIngressFlow() {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(new File("/srv/orders/ready"))
                         .patternFilter("*.ready"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofSeconds(5))
                               .maxMessagesPerPoll(10)
                    )
                )
                .channel("incomingFiles")
                .get();
    }
}
~~~

Ví dụ cho thấy quan hệ **inbound adapter → poller → MessageChannel**; chưa đủ production. Cần import và xác minh API theo phiên bản, bổ sung persistent filter/claim, kiểm tra file tải xong, handler, retry, error flow, archive, metrics và kiểm soát nhiều replica. \`DirectChannel\` không phải hàng đợi bền vững.

### 5.3. Checklist channel và executor

| Câu hỏi | Tiêu chí review |
|---|---|
| Handler xử lý CPU-bound hay I/O-bound? | Chọn concurrency theo tải và connection pool |
| Có ranh giới thread mới? | Không giả định transaction từ DirectChannel tự truyền qua ExecutorChannel |
| Queue có bounded capacity? | Tránh tràn bộ nhớ khi downstream chậm |
| Queue in-memory hay persistent? | Có test restart và recovery theo loại MessageStore |
| Khi queue đầy thì xử lý gì? | Backpressure, pause, reject có kiểm soát |
| Có yêu cầu ordering? | Không để async concurrency phá thứ tự nghiệp vụ |
| Khi handler lỗi thì ai retry? | Ghi rõ synchronous exception vs error flow bất đồng bộ |
| Có giới hạn thời gian chờ? | Tránh thread bị block vô hạn |

## 6. Retry, error flow và DLQ/quarantine

### 6.1. Phân loại lỗi

| Loại | Ví dụ | Cách phản ứng |
|---|---|---|
| **Transient** | Timeout mạng, reset connection, 503, broker reconnect | Retry có giới hạn, backoff và jitter |
| **Overload** | HTTP 429, DB pool đầy, broker throttling | Giảm tốc, tôn trọng chính sách Retry-After khi áp dụng |
| **Permanent** | Payload sai schema, business rule không hợp lệ | Quarantine/DLT; không retry mãi |
| **Authentication/security** | 401/403, certificate lỗi, SFTP host key sai | Alert và sửa cấu hình/quyền; không bypass |
| **Duplicate** | Event đã xử lý với cùng business key | Idempotent no-op hoặc xử lý conflict |
| **Poison message** | Record gây exception lặp | Bounded retry, dead-letter và runbook replay |

**Tránh retry nhân tầng.** Nếu HTTP client, retry advice và broker đều retry nhiều lần, số side effect có thể lớn hơn dự tính. Chỉ định **owner chính của retry** và tính tổng số lần gọi tối đa.

### 6.2. Cơ chế lỗi của Spring Integration

Spring Integration hỗ trợ \`ErrorMessage\`, error channel và các handler/advice tùy endpoint, nhưng **không bảo đảm mọi exception tự đi qua cùng một errorChannel**:

- Với \`DirectChannel\`, exception có thể nổi về sender và quyết định rollback/ack tại nguồn.
- Với \`ExecutorChannel\`, poller hoặc listener bất đồng bộ, cần xác định error flow và error handler đang sử dụng.
- Error handler chỉ log rồi nuốt lỗi có thể khiến upstream xem thao tác thành công, tùy đường xử lý.
- \`errorChannel\` không tự tạo DLQ, không tự có retry và không tự bảo đảm lưu message.
- Cần chỉ rõ khi nào exception được rethrow để nguồn redeliver, khi nào được recover sau khi đã lưu bền vững vào quarantine.

### 6.3. Checklist DLQ/quarantine

- [ ] Có nơi lưu message lỗi với retention và ACL phù hợp.
- [ ] Ghi business key, source, failed handler, reason, attempts, timestamp, correlation ID.
- [ ] Tách lỗi dữ liệu khỏi lỗi hạ tầng để tránh replay sai.
- [ ] Không lưu Authorization header, password, raw token hay PII không cần thiết.
- [ ] Có metric size, age, arrival rate, alert và owner.
- [ ] Có runbook replay batch nhỏ, kiểm tra idempotency và ordering.
- [ ] Có quy trình xóa/retention và audit thao tác vận hành.
- [ ] Đã thử poison message không gây retry storm.

## 7. Bảo mật và quản lý cấu hình dùng chung

### 7.1. Checklist bảo mật

- [ ] Không hard-code secret/token/private key vào source code, file cấu hình commit hoặc container image.
- [ ] Dùng secret manager hoặc mount an toàn; quyền đọc file chỉ cho service identity cần thiết.
- [ ] Có owner, rotation, expiry và revoke workflow cho từng credential.
- [ ] TLS certificate/hostname/chain được validate; không tắt kiểm tra vì môi trường production khó cấu hình.
- [ ] Với SFTP, xác minh server host key theo trusted known-hosts hoặc cơ chế đã phê duyệt.
- [ ] Mỗi adapter chỉ có quyền tối thiểu tới path, queue, exchange, topic, database hoặc API cụ thể.
- [ ] Kiểm soát network ingress/egress và rate limit thích hợp.
- [ ] Không log full payload chứa PII, password, cookie, Authorization header hoặc private key.
- [ ] Cấu hình theo môi trường, kiểm tra property bắt buộc trước startup.
- [ ] Có kiểm thử credential rotation và certificate hết hạn/mismatch.

### 7.2. Ví dụ property do ứng dụng tự định nghĩa

~~~yaml
app:
  integration:
    ingress:
      enabled: true
      fixed-delay: 5s
      max-messages-per-poll: 10
      max-inflight: 50
    retry:
      max-attempts: 4
      initial-backoff: 1s
      max-backoff: 15s
    timeout:
      connect: 5s
      read: 20s
      request: 30s
    quarantine:
      enabled: true
      retention: 7d
    sftp:
      host: SFTP_HOST_FROM_ENV_OR_SECRET
      username: SFTP_USER_FROM_ENV_OR_SECRET
      private-key-path: /etc/app/ssh/id_ed25519
      known-hosts: /etc/app/ssh/known_hosts
~~~

**Quan trọng:** Đây là cấu trúc property **minh họa của ứng dụng**, không phải danh sách cấu hình Spring Integration/Spring Boot tự nhận. Cần có lớp bind/validate và kết nối các trường với adapter/client thực tế. Các con số ở trên cũng không phải chuẩn SLO cho mọi hệ.

## 8. Adapter File: checklist trước production

### 8.1. File inbound

- [ ] Thư mục có owner, quyền, mount, dung lượng, inode và retention rõ.
- [ ] Producer ghi file tạm rồi rename/đặt marker chỉ khi hoàn thành; consumer không đọc file đang ghi dở.
- [ ] File pattern, charset, max file size, row count và schema được kiểm tra.
- [ ] Có cơ chế dedupe; **filter chỉ in-memory không đủ** nếu cần sống sót qua restart hoặc nhiều replica.
- [ ] Có persistent metadata store hoặc claim/lock phân tán theo thiết kế.
- [ ] Có business idempotency key để xử lý lại file sau crash không tạo tác động lặp.
- [ ] Có trạng thái ready/processing/done/failed hoặc cơ chế tương đương.
- [ ] File chỉ được archive/delete khi nghĩa vụ xử lý và khả năng khôi phục đã được đáp ứng.
- [ ] File lỗi/không hợp lệ được quarantine, có runbook replay.
- [ ] Đã thử producer ghi chậm, file quá lớn, tên trùng, cùng file được sửa lại, pod restart.
- [ ] Nếu dùng shared volume, rename/lock semantics được thử với filesystem thực tế.

### 8.2. File outbound

- [ ] Tên file, đường dẫn, quyền ghi và hành vi khi file đã tồn tại được định nghĩa.
- [ ] Có tên tạm + rename nếu consumer chỉ được đọc file đầy đủ.
- [ ] Có checksum/record count hoặc manifest nếu nghiệp vụ yêu cầu.
- [ ] Retry không ghi ra hai phiên bản file trùng tác động nghiệp vụ.
- [ ] Kiểm tra ổ đĩa đầy, permission denied, I/O error và khả năng cleanup.
- [ ] Phân biệt “file đã ghi” với “message nguồn đã được ack”.

**Failure drill:** Ghi file thành công nhưng app chết trước commit DB/ack. Sau restart phải có cơ chế xác định file có cần ghi lại hay không, không giả định một transaction chung bảo vệ cả hai.

## 9. Adapter SFTP: checklist trước production

### 9.1. SFTP inbound

- [ ] Remote host/port/user/path, local cache/path và owner được externalize.
- [ ] Host key được xác minh, known-hosts có quy trình cập nhật/rotate.
- [ ] Private key/credential quản lý qua secret store, không log hoặc đóng gói trong image.
- [ ] Có connect/session/read timeout, reconnect/backoff có giới hạn.
- [ ] Session factory/cache/pool phù hợp concurrent transfers.
- [ ] Có remote và local file filter; dùng persistent metadata khi cần chống lặp qua restart.
- [ ] Có protocol xác nhận upload hoàn tất (temporary extension → rename, marker hoặc manifest).
- [ ] Nếu nhiều replica cùng poll, có distributed claim, lock hoặc phân vùng nguồn.
- [ ] Có quy tắc file cùng tên nhưng nội dung thay đổi: version/hash/business ID.
- [ ] Có remote archive/failed/done và retention rõ; không xóa từ nguồn sớm.
- [ ] Khi download thành công nhưng xử lý nghiệp vụ lỗi, file vẫn có đường replay/recover.
- [ ] Đã thử transfer đứt giữa chừng, host key sai, remote disk đầy và credential hết hạn.
- [ ] Có metric oldest pending file, failure count và tuổi local cache.

**Lưu ý:** Persistent accept-once filter có thể đánh dấu file **đã được quan sát/tải** trước khi business transaction hoàn thành. Không coi kết quả filter như biên nhận nghiệp vụ; cần record xử lý và cơ chế retry sau crash.

### 9.2. SFTP outbound

- [ ] Có target directory, temporary name, rename và xác minh độ dài/checksum khi phù hợp.
- [ ] Xác định hành vi khi remote file đã tồn tại.
- [ ] Retry timeout sau upload có nguy cơ gửi trùng; dùng versioned name/idempotency/manifest.
- [ ] Giới hạn concurrent session, bandwidth và reconnect.
- [ ] Test permission denied, không đủ disk, rename lỗi và response timeout.
- [ ] Không xóa file local trước khi hoàn tất hợp đồng bàn giao.
- [ ] Atomic rename và server filesystem semantics được thử với SFTP server thật.

## 10. Cửa kiểm tra kết thúc phần nền tảng

Trước khi chuyển sang từng adapter có broker/API/database, reviewer cần trả lời:

- [ ] Có sơ đồ message flow và **ranh giới commit/ack**.
- [ ] Có idempotency key và bài test duplicate/crash.
- [ ] Poller/channel/executor có giới hạn concurrency/buffer.
- [ ] Retry/backoff không trùng lặp vô hạn giữa nhiều tầng.
- [ ] Error flow đưa message lỗi tới recovery có owner.
- [ ] Bảo mật kết nối và secret đúng production.
- [ ] File/SFTP chưa tải xong không bị xử lý.
- [ ] Có metric, log/correlation và pause/resume phù hợp.

**Nếu một câu trả lời còn mơ hồ, đừng suy đoán rằng Spring Integration tự xử lý thay ứng dụng.** Ghi lại quyết định và bằng chứng kiểm thử trước khi go-live.

## 11. Adapter HTTP: inbound và outbound gateway

### 11.1. HTTP inbound gateway

HTTP inbound thường có hợp đồng **request/reply**; ngoài xử lý nghiệp vụ, phải quản lý request thread, response timeout và phản hồi API.

- [ ] Path, HTTP method, content type, request/response schema và API version rõ ràng.
- [ ] Có authentication/authorization phù hợp, TLS và network access policy.
- [ ] Request size/headers giới hạn; validate JSON/XML và chống payload bất thường.
- [ ] Giới hạn rate, concurrency và thời gian chờ qua reverse proxy/load balancer.
- [ ] Nếu xử lý dài, dùng cơ chế nhận yêu cầu/báo tiến độ được thiết kế, thay vì chờ synchronous vô hạn.
- [ ] Map lỗi validation, authentication, conflict, timeout, throttling và internal failure về response hợp đồng.
- [ ] Nếu client retry POST, yêu cầu idempotency key hoặc cơ chế kiểm tra request đã xử lý.
- [ ] Correlation ID và trace được giữ qua inbound flow mà không log bearer token/cookie.
- [ ] Có test client disconnect, timeout, duplicate request, payload quá lớn và request không hợp lệ.
- [ ] Không trả success khi business side effect chưa đạt điều kiện hợp đồng.

### 11.2. HTTP outbound gateway

- [ ] Cấu hình connect timeout, response/read timeout và tổng request timeout.
- [ ] Connection pool và giới hạn connection theo host/route phù hợp capacity đối tác.
- [ ] Xác minh TLS certificate/hostname, proxy, mTLS hoặc OAuth credentials nếu dùng.
- [ ] Phân loại lỗi 400/401/403/404/409/429/5xx, timeout và network reset.
- [ ] Retry có giới hạn, backoff/jitter, tôn trọng tín hiệu rate limit của đối tác khi có.
- [ ] **Không retry mù POST/PUT không idempotent** khi không biết side effect đã xảy ra chưa.
- [ ] Có idempotency key phía đối tác, API tra cứu trạng thái hoặc reconciliation workflow.
- [ ] Giới hạn response size, kiểm tra content type/schema, tránh parse dữ liệu không tin cậy.
- [ ] Có error mapping, dashboard, alert và trace/correlation ID.
- [ ] Đã thử 429, 503, response sai schema, timeout sau khi phía nhận xử lý xong.

**Tình huống điển hình:** HTTP POST tạo lệnh thanh toán đã thành công nhưng response về client bị mất. Một retry không có idempotency key có thể tạo lệnh thứ hai. Đây là lỗi **side-effect ambiguity**, không chỉ là lỗi timeout.

## 12. Adapter JMS: acknowledgement và redelivery

JMS cung cấp abstraction nhắn tin, còn chi tiết transaction, DLQ, prefetch/concurrency và failover phụ thuộc broker/JMS provider và listener container.

- [ ] Destination queue/topic, tên, owner và subscription mode (durable/shared khi thích hợp) đã rõ.
- [ ] Connection factory, credential, TLS, pool, reconnect và timeout được cấu hình.
- [ ] Acknowledge mode / session transacted / transaction manager được lựa chọn có chủ đích.
- [ ] Có sơ đồ khi nào broker xem message đã xử lý.
- [ ] Khi handler exception, biết message có được redeliver, vào DLQ hay bị coi đã hoàn tất.
- [ ] Có giới hạn redelivery, backoff và xử lý poison message.
- [ ] Consumer concurrency, prefetch/consumer window và ordering được load test.
- [ ] Message converter, payload serialization và JMS properties/header mapping đã được kiểm tra.
- [ ] Nếu dùng request/reply gateway, có correlation ID, reply destination và reply timeout.
- [ ] Handler idempotent khi message được giao lại sau DB commit.
- [ ] Có metric queue depth, oldest message age, redelivery rate, DLQ, số consumer.
- [ ] Đã thử broker restart, listener crash trước/sau transaction, credential hết hạn.
- [ ] Có runbook replay DLQ, kiểm soát quyền service account và audit.

**Lưu ý:** Local JMS transaction thường **không tự bao trùm** database, HTTP hoặc hệ khác. Dùng XA/distributed transaction chỉ khi thực sự có kiến trúc, hạ tầng và thử nghiệm hỗ trợ; với các luồng thông thường, ưu tiên idempotency cùng cách xử lý failure window rõ ràng.

### 12.1. Drill JMS bắt buộc

1. Consumer đọc message.
2. Business handler commit database thành công.
3. Process bị kill **trước khi message được acknowledge**.
4. Listener được khởi động lại.
5. Message được giao lại theo broker semantics.
6. Hệ không tạo business record thứ hai nhờ stable key và unique constraint.

Nếu không giải thích được kết quả ở bước 5–6, chưa thể xác nhận luồng đủ an toàn.

## 13. Adapter AMQP: publisher confirms, ack và DLQ

Đối với Spring AMQP/RabbitMQ, cần hiểu exchange, queue, routing, publisher confirms, acknowledgement và dead-letter.

- [ ] Exchange, queue, binding/routing key được quản trị và khớp topology môi trường.
- [ ] Durability của queue và persistence/durability message phù hợp yêu cầu; không đồng nhất hai cấu hình.
- [ ] Chọn auto/manual ack đúng listener container và failure policy.
- [ ] Với manual ack, ack chỉ xảy ra sau khi đạt điều kiện xử lý được định nghĩa.
- [ ] Consumer concurrency và prefetch có giới hạn, tránh quá nhiều unacked messages.
- [ ] Có DLX/DLQ hoặc cơ chế error routing, retention và quy trình replay.
- [ ] Tránh requeue liên tục poison message gây redelivery storm.
- [ ] Producer xử lý publisher confirms/returns hoặc unroutable message nếu nghiệp vụ yêu cầu xác nhận gửi.
- [ ] Có idempotency khi broker redeliver hoặc producer gửi lại do không nhận confirm.
- [ ] Connection/heartbeat/TLS/authentication và recovery được kiểm tra.
- [ ] Có dashboard ready queue depth, unacked count, publish/ack rate, consumer count và DLQ.
- [ ] Đã thử broker failover, lỗi routing key, consumer crash sau DB commit nhưng trước ack.

**Manual ack không phải exactly-once.** Nếu ack quá sớm, side effect có thể mất khi handler lỗi. Nếu DB đã commit nhưng ack thất bại, broker có thể giao lại. Thiết kế phải có câu trả lời cho cả hai cửa sổ.

### 13.1. Publisher confirm và xử lý kết quả mơ hồ

Nếu producer gửi message nhưng mất kết nối trước khi nhận confirm, không thể khẳng định broker chưa lưu message. Retry có thể tạo bản trùng; consumer downstream cần idempotency. Confirm/return/routing test giúp phát hiện trường hợp không được broker hoặc queue nhận như kỳ vọng, nhưng không thay thế contract và reconciliation.

## 14. Adapter Kafka: offset, partition và xử lý record lỗi

- [ ] Topic, partition count, retention, cleanup policy và ACL được phê duyệt.
- [ ] Kafka bootstrap servers, TLS/SASL/credentials được cấu hình theo môi trường.
- [ ] Producer key/partition routing phù hợp yêu cầu ordering theo business key.
- [ ] Serializer/deserializer, schema version và compatibility đã test.
- [ ] Producer retry, acknowledgement và idempotent producer được thiết lập theo mức bảo đảm yêu cầu.
- [ ] Consumer \`group.id\` có owner; hiểu tác động khi đổi group hoặc tái triển khai.
- [ ] \`auto.offset.reset\` có quyết định rõ cho group chưa có offset, không chọn tùy tiện.
- [ ] Ack/offset commit xảy ra tại điểm hợp đồng đã xác định.
- [ ] Có error handler, retry/backoff, DLT/recovery và chính sách với poison record.
- [ ] Consumer concurrency phù hợp partition count; không kỳ vọng ordering toàn topic.
- [ ] Có kiểm tra \`max.poll.interval.ms\`, processing duration, batch size và rebalance.
- [ ] Đã thử consumer crash sau DB commit nhưng trước offset commit.
- [ ] Có idempotent consumer và unique business key khi cập nhật DB.
- [ ] Nếu dùng Kafka transactions/exactly-once, phạm vi được ghi rõ; **không tự mở rộng tới HTTP và database ngoài Kafka**.
- [ ] Giám sát consumer lag, rebalance, retry rate, DLT size và lỗi commit.

### 14.1. Thứ tự và poison record

Kafka bảo toàn thứ tự **theo partition**; với nhiều partition, không có thứ tự toàn cục. Nếu partition key dựa trên orderId, các bản sửa cùng order nên theo cùng quy tắc phân vùng nếu cần ordering.

Đẩy record lỗi vào DLT rồi tiếp tục với record sau có thể phá ràng buộc nghiệp vụ “revision 3 phải được xử lý sau revision 2”. Cần định nghĩa chính sách **block partition, quarantine cả chuỗi, replay hoặc bỏ qua có phê duyệt** trước production.

### 14.2. Drill Kafka

~~~text
Kafka record -> consumer -> DB transaction commit
                              |
                              +-- process bị kill
                                  trước offset commit
                              |
restart -> record được giao lại
        -> idempotency key xác định ALREADY_PROCESSED
        -> offset được commit theo policy
~~~

Nếu consumer group bị đổi hoặc offset bị reset, số record được replay có thể lớn; runbook phải biết **business side effect đã được commit tới đâu** trước khi seek/replay.

## 15. Adapter JDBC: polling và database operations

### 15.1. JDBC inbound polling

- [ ] SELECT/filter chỉ lấy row đủ điều kiện, có giới hạn batch và ORDER BY khi cần.
- [ ] Có index phù hợp, execution plan được thử với dữ liệu production-like.
- [ ] Có cơ chế claim/lock/mark row để hai instance không cùng xử lý một bản ghi ngoài thiết kế.
- [ ] Trạng thái row có thể dùng NEW/PROCESSING/DONE/FAILED hoặc mô hình tương đương.
- [ ] Nếu PROCESSING có lease, có expiry và job recovery cho row mắc kẹt sau crash.
- [ ] Transaction isolation và lock semantics phù hợp database cụ thể.
- [ ] Không giữ DB lock/transaction trong thời gian gọi remote HTTP lâu nếu không có lý do thiết kế rõ.
- [ ] Watermark theo ID/timestamp có cơ chế xử lý update muộn và concurrency.
- [ ] Có query timeout, connection pool, giới hạn transaction và retry/bảo vệ deadlock.
- [ ] Đã thử two-poller concurrent claim, row lỗi dữ liệu và pod restart giữa transaction.
- [ ] Có metric row pending age, in-progress lease age, query latency và pool saturation.

Ví dụ **pseudo-SQL** thể hiện tư duy claim; cú pháp phải điều chỉnh theo database:

~~~sql
BEGIN TRANSACTION;

SELECT id
FROM integration_inbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;

-- Giới hạn số dòng theo dialect cụ thể.
-- UPDATE đúng ID đã claim sang PROCESSING.
-- Có thể ghi lease_owner và lease_until.

COMMIT;
~~~

\`SKIP LOCKED\` và cú pháp pagination không giống nhau ở mọi cơ sở dữ liệu. Chỉ sử dụng sau khi kiểm tra isolation, deadlock và transaction ở hệ thật. Khi claim xong, vẫn cần idempotency của **tác động nghiệp vụ**, bởi worker có thể chết sau commit.

### 15.2. JDBC outbound/gateway

- [ ] SQL dùng bind parameters; không nối chuỗi dữ liệu người dùng vào query.
- [ ] Có transaction boundary, isolation, timeout và autocommit policy.
- [ ] Có unique constraint/upsert/locking phù hợp để ngăn side effect lặp.
- [ ] Giới hạn result rows, fetch size, cursor lifetime và memory usage.
- [ ] Connection pool có max size, borrow timeout, max lifetime theo capacity DB.
- [ ] Phân loại constraint/validation error khác transient deadlock/timeout.
- [ ] Đã test DB failover, pool exhaustion, commit conflict, rollback và partial failure.
- [ ] Không log credential hoặc dữ liệu nhạy cảm trong SQL parameters.

### 15.3. Ghi DB và phát broker message

Nếu handler vừa commit DB rồi gửi Kafka/JMS/AMQP, hai side effect thường **không cùng transaction ACID**. Transactional outbox có thể giúp ghi record nghiệp vụ và “nghĩa vụ phát event” trong một transaction DB; publisher riêng retry gửi outbox. Consumer downstream vẫn cần idempotency vì có thể nhận duplicate.

## 16. Connection lifecycle, deployment và nhiều replica

### 16.1. Startup/readiness

- [ ] Cấu hình bắt buộc được validate sớm; thiếu secret/endpoint quan trọng phải có phản ứng rõ.
- [ ] Phân biệt **liveness** của process với **readiness** nhận traffic/công việc.
- [ ] Dependency outage tạm thời có reconnect/backoff; không restart vô hạn không cần thiết.
- [ ] Có cơ chế gating endpoint nếu schema hoặc remote resource chưa sẵn sàng.
- [ ] Health check không tự gọi side effect nghiệp vụ.
- [ ] Poller/listener có thể pause/resume qua quy trình được phép.
- [ ] Có kiểm thử rotation credential/certificate khi process đang chạy.

### 16.2. Graceful shutdown và rolling deployment

- [ ] Khi dừng, endpoint ngừng nhận message mới theo thiết kế.
- [ ] Inflight được hoàn thành trong giới hạn grace period hoặc được recovery/redelivery.
- [ ] Không ack nguồn trước khi trạng thái nghiệp vụ đạt điều kiện.
- [ ] Đã thử SIGTERM/kill trong HTTP call, SFTP transfer, DB transaction và broker delivery.
- [ ] Rolling deploy hai version có schema/message compatibility.
- [ ] Nhiều pod không cùng claim file/row trừ khi xử lý trùng đã được bảo vệ.
- [ ] Rollback có phương án bảo toàn offset, metadata, outbox và trạng thái tác động bên ngoài.

### 16.3. Sizing và backpressure

Định lượng arrival rate, processing throughput, latency p95/p99, max inflight, queue size, thread pool, connection pool và giới hạn đích. Ví dụ nếu upstream gửi 120 record/s còn downstream xử lý bền vững 80 record/s, backlog tăng khoảng 40 record/s khi tốc độ giữ nguyên; thêm thread nhưng không tăng DB/API capacity không giải quyết gốc vấn đề.

Cần lựa chọn **pause poller, bounded queue, broker backpressure, concurrency limit hoặc fail-fast** khi quá tải, theo ngữ nghĩa từng endpoint. Không để buffer in-memory tăng vô hạn tới OOM.

## 17. Observability: metric, log, tracing và alert

### 17.1. Logging có cấu trúc

| Trường | Mục đích |
|---|---|
| Business ID / eventId / idempotency key | Xác định record xuyên retry |
| correlationId / traceId | Nối ingress, handler và outbound |
| Adapter, channel, endpoint ID | Biết lỗi tại bước nào |
| Target endpoint / protocol | Biết dependency nào gặp vấn đề |
| Schema/mapping version | Giải thích parse/transform |
| Attempt, retry delay, error category | Phân loại lỗi và retry storm |
| Commit/ack/offset/checkpoint state | Điều tra cửa sổ mất/duplicate |
| Processing duration, payload size | Phát hiện bottleneck |
| Outcome: success/retry/quarantine/reject | Kết quả có thể đo được |

Không log raw Authorization, cookies, credential, private key hoặc payload chứa PII không cần thiết. Với file lớn, dùng file ID/checksum/metadata được phép thay vì toàn bộ nội dung.

### 17.2. Dashboard và cảnh báo

| Chỉ số | Tín hiệu cần cảnh báo |
|---|---|
| Ingress/egress rate | Giảm hoặc tăng bất thường |
| End-to-end processing latency | Vượt SLO p95/p99 |
| Handler/adapter error rate | Nhiều lỗi cùng loại hoặc lỗi security |
| Retry volume và attempts | Retry storm, partner bất ổn |
| DLQ/quarantine size và oldest age | Lỗi tồn lâu, chưa có xử lý |
| Kafka consumer lag / JMS-AMQP queue depth | Backlog không drain |
| Oldest SFTP/file pending age | File mắc kẹt hoặc partner ngừng gửi |
| JDBC PROCESSING lease age | Row bị claim nhưng chưa hoàn tất |
| Thread/queue depth, executor rejection | Channel bị nghẽn |
| Connection pool utilization, timeout | Hết connection hoặc dependency chậm |
| Duplicate detected rate | Producer retry nhiều, business key conflict |
| Business completion rate | Thành công kỹ thuật nhưng thất bại nghiệp vụ |

Spring Integration có khả năng quản lý/metrics/observation tùy phiên bản và cấu hình. Nếu dùng Micrometer, Spring Boot Actuator hoặc tracing stack, phải **xác minh metric/traces thực sự xuất hiện**, có nhãn và alert hợp lệ, không chỉ thêm dependency.

### 17.3. Correlation xuyên transport

HTTP thường có header tracing, còn file/SFTP/JDBC polling cần tạo hoặc trích xuất business ID theo hợp đồng. Khi chuyển qua Kafka/JMS/AMQP, mapping header phải được cấu hình và kiểm thử theo converter. Không giả định MessageHeaders của Spring Integration được truyền nguyên xi qua mọi giao thức.

### 17.4. Checklist vận hành số liệu

- [ ] Có SLO cụ thể về thời gian xử lý và mức mất/duplicate được chấp nhận.
- [ ] Alert có severity, owner/on-call và runbook URL.
- [ ] Đã test gửi alert khi DLQ, lag, timeout hoặc auth failure tăng.
- [ ] Dashboard phân biệt **không có dữ liệu mới** và **message bị kẹt trong luồng**.
- [ ] Có baseline theo giờ/ngày và cửa sổ vận hành, tránh threshold tùy tiện.
- [ ] Có correlation từ file/record nguồn tới side effect và target.

## 18. Ma trận kiểm thử bắt buộc trước go-live

**Không chỉ kiểm thử happy path.** Với hệ thống tích hợp, test quan trọng nhất thường là những thời điểm process chết **sau một side effect nhưng trước khi acknowledge hoặc ghi checkpoint**.

### 18.1. Các lớp kiểm thử

1. **Unit test:** contract, transform, router, validation, phân loại lỗi và idempotency rule.
2. **Integration test:** kết nối adapter với test broker/database/SFTP/HTTP stub có hành vi gần production.
3. **Contract test:** schema, message header, version compatibility và lỗi dữ liệu.
4. **Load/soak test:** throughput, concurrency, queue/buffer, connection pool, memory và backlog.
5. **Failure injection:** network reset, timeout, restart, rebalance, poison record, partial transfer.
6. **Security test:** credential hết hạn, TLS/host key sai, unauthorized API, oversized payload.
7. **Operations drill:** pause/resume, DLQ replay, failback, rotation secret, graceful shutdown.

### 18.2. Bộ kiểm thử có mã truy vết

| Mã | Tình huống | Điều kiện đạt |
|---|---|---|
| **T01** | Message hợp lệ đi từ inbound qua handler tới outbound | Đúng business output, correlation và audit |
| **T02** | Message sai schema version | Quarantine/reject đúng contract, không side effect |
| **T03** | Payload thiếu required field hoặc sai charset | Có lỗi rõ và không tạo dữ liệu lỗi |
| **T04** | Gửi cùng eventId hai lần | Không tạo side effect nghiệp vụ lặp |
| **T05** | App crash sau DB commit, trước ack | Redelivery an toàn, không insert trùng |
| **T06** | App crash sau outbound success nhưng trước lưu trạng thái | Idempotency/đối soát ngăn gửi tác động trùng |
| **T07** | File đang upload dở | Không được xử lý trước ready marker/rename |
| **T08** | File tải lại sau restart | Không mất và không tạo order trùng |
| **T09** | Hai replica poll cùng thư mục | Không double-process ngoài chính sách |
| **T10** | File cùng tên nhưng nội dung thay đổi | Xử lý theo version/hash/business key hợp đồng |
| **T11** | Local disk/inode đầy | Báo lỗi/alert, không đánh dấu DONE |
| **T12** | SFTP host key sai | Từ chối kết nối và alert, không bỏ xác minh |
| **T13** | SFTP mất mạng giữa download/upload | Retry/recovery đúng, không coi transfer thành công |
| **T14** | SFTP credential hết hạn | Không retry nóng vô hạn, có owner xử lý |
| **T15** | HTTP inbound duplicate POST | Idempotency key giữ một business effect |
| **T16** | HTTP inbound payload quá lớn | Từ chối an toàn, không tràn memory |
| **T17** | HTTP outbound trả 429/503 | Backoff phù hợp, giới hạn attempts |
| **T18** | HTTP POST thành công tại đối tác nhưng response timeout | Đối soát/idempotency tránh tạo trùng |
| **T19** | HTTP auth 401/403 | Alert/config action, không retry nóng |
| **T20** | JMS listener crash trước/sau commit/ack | Redelivery và idempotency đúng |
| **T21** | JMS poison message | Retry bounded, DLQ có replay |
| **T22** | JMS broker restart/failover | Consumer hồi phục và không làm sai state |
| **T23** | AMQP manual ack bị mất sau DB commit | Message giao lại nhưng side effect không lặp |
| **T24** | AMQP unroutable/routing sai | Detect theo publisher confirm/return policy |
| **T25** | AMQP requeue lặp poison message | DLX/DLQ hoặc cơ chế chặn storm |
| **T26** | AMQP prefetch quá cao so với downstream | Backpressure/queue metric phản ánh rủi ro |
| **T27** | Kafka record xử lý xong DB nhưng chưa commit offset | Redelivery idempotent |
| **T28** | Kafka consumer rebalance/scale | Không làm mất record; ordering đúng partition |
| **T29** | Kafka poison record chặn partition | DLT/quarantine theo chính sách ordering |
| **T30** | Kafka consumer lag tăng sau outage | Alert và kế hoạch drain backlog |
| **T31** | Kafka đổi group.id/offset reset | Replay có kiểm soát, tránh side effect lặp |
| **T32** | Hai JDBC poller claim cùng row | Chỉ một writer claim theo DB lock/lease thiết kế |
| **T33** | JDBC row PROCESSING bị crash | Lease hết hạn/recovery trả row về trạng thái xử lý được |
| **T34** | DB deadlock, timeout và pool exhaustion | Retry có giới hạn, metric/alert, không mất dữ liệu |
| **T35** | DB commit thành công, Kafka publish thất bại | Outbox ghi nghĩa vụ phát và publisher recover |
| **T36** | QueueChannel in-memory mất process | Hệ có durable boundary/recovery theo hợp đồng |
| **T37** | ExecutorChannel queue đầy | Backpressure/rejection rõ, không OOM |
| **T38** | Chuyển thread khi transaction đang mở | Không giả định transaction tự lan sang executor |
| **T39** | Retry cùng lúc HTTP client + advice + broker | Tổng số attempts không vượt ngân sách |
| **T40** | Error flow chỉ log rồi return | Kiểm thử phát hiện nguy cơ mất tác động/ack sai |
| **T41** | DLQ replay sau sửa lỗi | Không tạo tác động nghiệp vụ trùng |
| **T42** | TLS certificate hết hạn/hostname mismatch | Fail closed và alert đúng |
| **T43** | Secret được rotate khi app đang chạy | Kết nối hồi phục theo runbook |
| **T44** | Rolling deploy hai version | Message/schema tương thích, không double-claim |
| **T45** | Graceful shutdown còn inflight | Hoàn tất hoặc redelivery/recovery, không mất |
| **T46** | Network partition với remote dependency | Retry/backoff và capacity giới hạn |
| **T47** | Tăng tải vượt năng lực downstream | Backlog bị chặn/điều tiết, không vỡ tài nguyên |
| **T48** | Correlation đi qua SFTP → DB → Kafka | Có trace/log đối chiếu mà không lộ PII |
| **T49** | Replayed event đến sai thứ tự | Business version/order policy xử lý đúng |
| **T50** | Rollback sau một phần side effect | Đối soát/bù trừ, không phát trùng hoặc mất |
| **T51** | Source snapshot/batch rỗng bất thường | Không tự hiểu là lệnh xóa hàng loạt |
| **T52** | Xóa DLQ record không qua quyền vận hành | Bị chặn bởi ACL/audit và retention |
| **T53** | Listener chạy 24 giờ với intermittent errors | Không leak memory/thread/session/connection |
| **T54** | Startup khi broker/SFTP/DB tạm unavailable | Readiness và reconnect đúng chính sách |
| **T55** | Poison message đi cùng message hợp lệ | Không làm tắc vĩnh viễn cả hệ ngoài policy |

**Cách lưu bằng chứng:** mỗi test cần expected/actual result, môi trường, adapter/endpoint ID, cấu hình/version, message/business ID mô phỏng, timestamp, correlation ID, log/metric, người kiểm tra và issue liên quan. Đặc biệt các test T05, T18, T23, T27, T35 và T50 không thể thay bằng “đã thử một message thành công”.

## 19. Kế hoạch triển khai canary, vận hành và rollback

### 19.1. Trước ngày triển khai

- [ ] Chốt sơ đồ topology, endpoint owner, network path và access control.
- [ ] Config/secret production được xác minh bằng công cụ quản trị phù hợp.
- [ ] Schema/database migration tương thích với phiên bản app cũ khi rolling.
- [ ] Đã chạy contract, load, security và failure-window tests.
- [ ] Đã có dashboard/alert và on-call runbook hoạt động.
- [ ] Đã tập dượt stop/start endpoint, DLQ replay, restart và rollback.
- [ ] Có phương án xử lý backlog và giới hạn số message/file trong giai đoạn đầu.
- [ ] Có người phê duyệt go/no-go, mốc thời gian và kênh thông tin.

### 19.2. Triển khai canary

1. Triển khai một replica/canary với endpoint và credential theo kế hoạch.
2. Bật health/metrics/logging, kiểm tra các kết nối dựa trên quyền thật.
3. Chạy smoke test bằng dữ liệu giả nhưng đi qua đường sản xuất được kiểm soát.
4. Hạn chế tốc độ poller/concurrency để dễ quan sát.
5. Đo end-to-end business completion, duplicate rate, processing latency và backlog.
6. Khi đạt ngưỡng đã duyệt, tăng dần traffic/replica/batch.
7. Theo dõi trong cửa sổ ổn định và chỉ đóng change khi owner xác nhận.

**Không giả định canary chỉ nhận một phần traffic nếu consumer group, queue hoặc poller không có cơ chế phân tuyến.** Cần hiểu cách Kafka partition assignment, JMS/AMQP consumer competition và distributed claim của file/SFTP/JDBC thực sự hoạt động.

### 19.3. Khi nào phải HOLD hoặc rollback?

- Phát hiện mất message hoặc duplicate side effect không kiểm soát.
- App xử lý sai dữ liệu hoặc gửi dữ liệu nhạy cảm sai đích.
- DLQ/backlog tăng không thể drain trong SLO được duyệt.
- Lỗi TLS/auth, lộ credential hoặc bypass security validation.
- Nhiều replica cùng xử lý một item ngoài thiết kế.
- Consumer retry liên tục làm quá tải DB/API/broker.
- Không xác định được trạng thái đã commit/ack sau sự cố.
- Error flow nuốt message hoặc tạo kết quả success sai.

**Rollback application version không tự hoàn tác side effect ngoài process.** File đã ghi, message đã publish, DB đã commit, API đối tác đã thực thi và offset đã commit cần được đối soát riêng.

### 19.4. Runbook rollback

1. Pause các ingress/writer gây lỗi; chụp metric, log, offset, metadata và backlog.
2. Xác định những business effects đã commit, đã phát đi và chưa được xác nhận.
3. Kiểm tra tương thích schema/consumer group/checkpoint với phiên bản cũ.
4. Triển khai lại phiên bản đã kiểm chứng hoặc disable chức năng mới theo kế hoạch.
5. Replay có kiểm soát, sử dụng idempotency key và giữ ordering nghiệp vụ khi cần.
6. Đối soát hệ đích: DB, file, broker, API đối tác, tránh mất/trùng dữ liệu.
7. Chỉ resume ingress khi trạng thái nhất quán và owner phê duyệt.
8. Ghi postmortem, nguyên nhân, thay đổi test và chính sách phòng ngừa.

Không sử dụng “clear queue”, “xóa inbox”, “reset offset về earliest” hoặc “đổi filename rồi gửi lại hết” trước khi xác định side effect thực tế.

## 20. Runbook vận hành sau go-live

### 20.1. Không thấy dữ liệu mới

1. **Source có dữ liệu không?** File/SFTP xuất hiện file ready, broker có message, DB có row NEW, HTTP có request?
2. **Endpoint đang chạy không?** Poller/listener/gateway có disabled, paused, stopped hoặc lỗi startup?
3. **Channel bị nghẽn?** Executor queue depth, active threads, rejection, pool exhaustion.
4. **Dependency bị lỗi?** Credential, TLS, DNS, network, quota, response latency, broker/DB health.
5. **Message đi đâu?** Retry scheduler, error flow, DLQ, quarantine, outbox pending.
6. **Nghiệp vụ đã commit chưa?** Check DB/business records, ack/offset, file marker/metadata.
7. **Chọn hành động:** Retry, re-drive, sửa input, giảm tải, pause nguồn hay rollback.
8. **Ghi incident:** Owner, thời gian, phạm vi ảnh hưởng, business IDs và các điểm chưa rõ.

### 20.2. DLQ/quarantine replay

- Xác minh root cause đã được xử lý.
- Đọc bản ghi lỗi, xác định có side effect xảy ra một phần không.
- Phê duyệt replay với dữ liệu nhạy cảm hoặc nghiệp vụ có rủi ro.
- Chạy batch có giới hạn, theo dõi idempotency và ordering.
- Đối soát business result với nguồn/đích sau replay.
- Chỉ xóa/tái phân loại DLQ theo retention, quyền và audit.

### 20.3. Pause/resume endpoint

Runbook cần có **endpoint ID**, owner, cách tạm ngừng inbound poller/listener hoặc giảm outbound traffic, thời gian chờ inflight, điều kiện resume và đường kiểm tra backlog. Pause không nhất thiết hủy các HTTP call hoặc broker transaction đang chạy; hành vi từng loại endpoint phải được thử trước.

### 20.4. Credential rotation

1. Chuẩn bị secret/certificate/key mới theo quy trình bảo mật.
2. Xác minh cả hai đầu hỗ trợ giai đoạn chuyển đổi nếu cần.
3. Áp rotation trong phạm vi giới hạn, kiểm tra reconnect và readiness.
4. Theo dõi lỗi xác thực/TLS/host-key và traffic.
5. Thu hồi credential cũ sau khi đã kiểm chứng không còn dependency.
6. Ghi audit về owner, thời điểm, kết quả và phương án phục hồi.

## 21. Case study: SFTP → JDBC → Kafka

Một hệ thống nhận CSV đơn hàng từ đối tác qua SFTP. File được parse và validate; mỗi order được ghi DB và sinh sự kiện \`OrderAccepted\` cho Kafka. Dự án triển khai ba replica để tăng độ sẵn sàng.

### 21.1. Thiết kế ban đầu có lỗi

- Poller mỗi giây, không giới hạn batch.
- Hai pod cùng scan remote directory, chỉ dùng accept-once filter in-memory.
- Đối tác upload trực tiếp file \`.csv\` khi dữ liệu chưa hoàn tất.
- Không có business idempotency key; retry file có thể tạo order trùng.
- Handler commit DB rồi publish Kafka trực tiếp, không có outbox.
- \`errorChannel\` chỉ log exception, không có quarantine/replay.
- Không có metric file age hoặc Kafka publish failures.

Thiết kế này có thể chạy tốt khi local chỉ có một instance, nhưng chưa an toàn với production.

### 21.2. Thiết kế cải thiện

**Producer SFTP:** Upload tên tạm, chỉ rename thành đuôi ready hoặc tạo marker sau khi hoàn tất; cung cấp business key và checksum/manifest nếu hợp đồng yêu cầu.

**Ingress:** Xác minh SFTP host key, dùng secret store và timeout; phân vùng/claim nguồn khi nhiều replica; persistent metadata/filter phù hợp; poller có batch/concurrency giới hạn.

**Business contract:** Mỗi order có ID và revision ổn định, schema version, số dòng và giới hạn file. Validation chạy trước side effect; dữ liệu nhạy cảm không được đưa nguyên vào log.

**JDBC transaction:** Dùng unique business key và bảng processed events; ghi order cùng outbox event trong một transaction. Retry sau crash không tạo order mới.

**Kafka publisher:** Worker phát outbox với retry/backoff, ghi trạng thái từng lần gửi, theo dõi pending age và publish failures. Consumer phía đích vẫn idempotent do event có thể được gửi lại.

**Error handling:** File sai schema vào quarantine; lỗi hạ tầng retry có giới hạn; file nguồn không bị xóa sớm; có replay runbook và owner.

**Observability:** Truy vết từ remote file ID → order ID → DB transaction/outbox → Kafka event; dashboard có oldest pending file, duplicate no-op count và outbox lag.

### 21.3. Ba failure drills quyết định

**Drill A — DB commit xong, pod chết trước Kafka publish.** Outbox chứa sự kiện pending. Worker sau restart phát tiếp; không tạo duplicate order.

**Drill B — Hai replica cùng nhìn một file.** Distributed claim/filter làm giảm cạnh tranh; DB unique key bảo vệ tầng nghiệp vụ nếu input vẫn bị xử lý lại.

**Drill C — Đối tác bị rớt mạng khi upload.** File chưa ready không được parse; sau khi hoàn tất mới được xử lý. File lỗi phải có khả năng điều tra và re-drive.

### 21.4. Điều kiện chấp nhận

- Không mất order trong failure drills đã định nghĩa.
- Replay không tạo side effect trùng.
- Có khả năng truy vết và đối soát order từ SFTP tới Kafka.
- File lỗi không biến mất mà có quarantine/runbook.
- Backlog/latency đáp ứng SLO được duyệt.
- Mở rộng hoặc restart replica không gây duplicate ngoài hợp đồng.
- Có runbook pause/resume, credential rotation và rollback được thử.

**Bài học:** Không một inbound adapter, poller, Kafka producer hay transaction manager riêng lẻ nào có thể thay thế thiết kế toàn luồng.

## 22. Mẫu phiếu review có thể tái sử dụng

~~~yaml
flow: supplier-orders-sftp-to-kafka
owners:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations
ingress:
  type: sftp-inbound
  remoteReadyProtocol: temp-then-rename
  pollInterval: 5s
  maxBatch: 10
message:
  schemaVersion: "1.0"
  idempotencyKey: source-orderId-revision
  maxPayloadSize: REVIEWED_LIMIT
channels:
  processing: bounded-workers
  durableCheckpoint: database-inbox
delivery:
  expectedSemantics: at-least-once
  businessIdempotency: unique-constraint
  publishRecovery: transactional-outbox
failure:
  transient: bounded-backoff
  permanent: quarantine
  replayRunbook: documented-and-tested
security:
  sftpHostKeyVerification: required
  secretsManaged: true
observability:
  correlationId: required
  queueAndLagAlerts: tested
readiness:
  crashDrillsPassed: true
  gracefulShutdownTested: true
  rollbackTested: true
approval:
  businessOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

**Đây là phiếu review minh họa**, không phải YAML mà Spring Integration tự hiểu. Không đánh dấu GO khi phần approval còn PENDING hoặc bằng chứng kỹ thuật chưa có.

### 22.1. Mẫu quyết định

| Trạng thái | Điều kiện |
|---|---|
| **GO** | Tất cả cổng bắt buộc đạt, test và rollback có bằng chứng |
| **GO WITH EXCEPTION** | Ngoại lệ có owner/expiry, phạm vi và biện pháp giảm rủi ro được phê duyệt |
| **HOLD / RETEST** | Thiếu load/failure drill, source/contract chưa xác minh hoặc owner chưa chấp thuận |
| **NO-GO** | Mất/trùng side effect không kiểm soát, lỗi bảo mật, không biết ack/commit, không có đường recovery |

Không dùng ngoại lệ để hợp thức hóa việc bỏ qua xác thực TLS/host key, lưu secret công khai hoặc chấp nhận mất dữ liệu mà nghiệp vụ không cho phép.

## 23. Anti-pattern cần tránh

**“Bật retry là không mất message.”** Retry không giải quyết ack quá sớm, thiếu persistence hoặc side effect mơ hồ. Cần fail-window tests.

**“Kafka/JMS/AMQP đảm bảo exactly-once nên DB không cần idempotency.”** Semantics broker không tự bao trùm external DB/HTTP. Cần business key và transaction/reconciliation.

**“QueueChannel đồng nghĩa durable queue.”** Queue in-memory có thể mất sau restart; durability phụ thuộc MessageStore/broker.

**“Mọi exception tự đi qua errorChannel.”** Đường lỗi phụ thuộc endpoint đồng bộ/bất đồng bộ và error handler. Phải kiểm tra propagation/ack.

**“SFTP tải xong nghĩa là nghiệp vụ xử lý xong.”** Ingest/metadata filter, DB commit và archive là các trạng thái khác nhau.

**“HTTP timeout nghĩa là phía nhận chưa thực hiện.”** Request có thể đã thành công nhưng response bị mất. Cần idempotency key hoặc tra cứu trạng thái.

**“Kafka bảo toàn thứ tự cả topic.”** Chỉ có thứ tự trong partition; lựa chọn key/concurrency ảnh hưởng ordering.

**“Thêm pod chắc chắn tăng throughput.”** Có thể tăng cạnh tranh file/row, nghẽn remote API/DB và retry storm.

**“Commit DB và publish broker là một transaction.”** Cần hiểu ranh giới transaction, outbox hoặc thiết kế bù trừ.

**“Log toàn payload giúp debug nhanh nhất.”** Gây lộ PII/secret; nên dùng metadata và business correlation.

**“Rollback image là hoàn tác mọi thay đổi.”** External side effect, offset, file upload, API request và DB commit vẫn tồn tại.

**“Có Actuator là đã giám sát đủ.”** Cần metric và alert đúng luồng nghiệp vụ, correlation và thực nghiệm phát hiện lỗi.

## 24. Câu hỏi tự kiểm tra

1. Inbound adapter và inbound gateway khác nhau thế nào về request/reply?
2. Vì sao generated MessageHeaders.ID không nên tự động làm khóa idempotency nghiệp vụ?
3. DirectChannel chuyển sang ExecutorChannel ảnh hưởng transaction và ordering ra sao?
4. QueueChannel in-memory khác broker durable queue như thế nào?
5. Khi Kafka offset chưa commit nhưng DB đã commit, hành vi sau restart là gì?
6. Vì sao JMS/AMQP redelivery cần consumer idempotent?
7. Nếu HTTP POST timeout, tại sao không thể kết luận đối tác chưa xử lý?
8. Khi file SFTP đang upload dở, cần giao ước nào để consumer biết đã sẵn sàng?
9. Persistent accept-once filter có chứng minh business processing success không?
10. Nếu hai JDBC poller cùng SELECT row NEW, điều gì ngăn double claim?
11. Tại sao cần unique constraint thay vì chỉ SELECT xem key đã tồn tại?
12. Transactional outbox giải quyết failure window nào?
13. Retry ở ba tầng có nguy cơ gì, và ai nên sở hữu retry policy?
14. Thử nghiệm DLQ replay cần xác minh gì trước khi chạy lại?
15. Khi Kafka đưa poison record vào DLT, điều này có thể ảnh hưởng ordering ra sao?
16. Với AMQP, publisher confirm và consumer ack giải quyết hai phần việc gì?
17. Vì sao không nên giữ database transaction mở khi gọi API chậm?
18. Những metric nào phân biệt “nguồn không có message” với “message bị kẹt”?
19. Khi rolling deployment, phải thử những gì về schema, checkpoint và inflight?
20. Trong luồng SFTP → DB → Kafka, nếu DB commit nhưng Kafka publish thất bại, cần hồi phục thế nào?

**Gợi ý:** Tách các mốc *nhận → lưu bền vững → xử lý side effect → acknowledge/commit nguồn → xác minh đích*. Với mỗi mốc, hỏi “nếu process chết ngay sau bước này, cần retry ở đâu và sẽ có nguy cơ gì?”.

## 25. Thuật ngữ và tài liệu tham khảo

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Inbound/outbound adapter** | Endpoint nhận/gửi dữ liệu một chiều giữa luồng và hệ ngoài |
| **Inbound/outbound gateway** | Endpoint request/reply trong IntegrationFlow |
| **MessageChannel** | Kênh truyền message giữa các endpoint |
| **Poller** | Tác vụ đọc nguồn theo lịch |
| **At-least-once** | Message có thể được giao lại khi chưa được xác nhận |
| **Idempotency** | Lặp request mà không tạo tác động nghiệp vụ lặp ngoài dự kiến |
| **Ack/offset/checkpoint** | Xác nhận hoặc mốc đọc đã xử lý tại nguồn |
| **Transactional outbox** | Ghi nghĩa vụ phát message trong transaction DB nghiệp vụ |
| **DLQ/DLT/quarantine** | Nơi giữ message/record lỗi để điều tra và replay |
| **Retry/backoff** | Thử lại với giới hạn và khoảng chờ có kiểm soát |
| **Backpressure** | Giới hạn đầu vào theo năng lực xử lý |
| **Persistent metadata store** | Lưu trạng thái filter/checkpoint qua restart |
| **Consumer lag / backlog** | Lượng dữ liệu đang chờ hoặc độ trễ consumer |
| **Graceful shutdown** | Dừng nhận mới và xử lý inflight có kiểm soát |
| **Go/no-go** | Quyết định triển khai dựa trên bằng chứng và mức rủi ro |

Nguồn nên đối chiếu **theo phiên bản dự án**:

- **Spring Integration Reference Guide:** Message Channels, Polling Consumer, Endpoint Lifecycle, Error Handling và Message Store.
- **Spring Integration File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC adapters:** Java DSL, inbound/outbound/gateway, các giới hạn và cơ chế tùy adapter.
- **Spring Framework / Spring Boot Reference:** Transaction Management, TaskExecutor/TaskScheduler, configuration binding, Actuator và Micrometer.
- **Spring for Apache Kafka Reference:** Listener container, acknowledgement, retry, DLT, transaction và consumer groups.
- **Spring AMQP Reference và tài liệu RabbitMQ:** Ack, prefetch, publisher confirms/returns, dead lettering.
- **Jakarta Messaging (JMS) specification và broker vendor documentation:** Transactions, acknowledge, redelivery, durable subscription, DLQ.
- **Tài liệu chính thức của SFTP server, HTTP đối tác, JDBC driver và database:** Host-key, timeout, API idempotency, SQL locking, connection pool và failure recovery.

**Tiêu chí cuối cùng:** Một adapter đủ điều kiện production không chỉ **kết nối được hệ ngoài**. Nó phải có hợp đồng message rõ, ngữ nghĩa delivery và transaction/ack có thể giải thích, idempotency, error recovery, bảo mật, giới hạn tải, observability, runbook và bài test sự cố tương ứng. Chỉ khi **bằng chứng đạt yêu cầu và owner phê duyệt** mới nên chuyển luồng sang vận hành thật.



