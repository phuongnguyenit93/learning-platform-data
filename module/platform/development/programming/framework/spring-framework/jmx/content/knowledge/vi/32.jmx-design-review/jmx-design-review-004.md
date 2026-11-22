# Đánh giá attribute, operation và notification theo tác động trong Spring JMX

## 1. Bối cảnh

Spring Framework JMX cho phép công bố trạng thái và khả năng quản trị của một Spring bean thành MBean thông qua các annotation như \`@ManagedResource\`, \`@ManagedAttribute\`, \`@ManagedOperation\` và \`@ManagedNotification\`. Tuy nhiên, một management API chỉ được xem là tốt khi **những gì nó phơi bày đem lại lợi ích vận hành tương xứng với rủi ro**.

Ba thành phần có vai trò và mức độ tác động khác nhau:

- **Attribute:** cho phép đọc một giá trị trạng thái, và trong trường hợp writable còn cho phép thay đổi giá trị.
- **Operation:** cho phép gọi một hành động quản trị có thể làm thay đổi trạng thái hoặc phát sinh công việc.
- **Notification:** phát tín hiệu về biến cố hoặc thay đổi trạng thái cho những listener đang đăng ký.

Bài học này đưa ra một phương pháp đánh giá theo tác động để quyết định nên expose gì, cần bảo vệ thế nào và kiểm thử điều gì trước khi đưa management interface lên production.

### Kết quả mong đợi

Sau bài này, bạn có thể:

1. Phân biệt tác động của read-only attribute, writable attribute, operation và notification.
2. Đánh giá lợi ích vận hành, phạm vi ảnh hưởng, rủi ro bảo mật và chi phí thực thi.
3. Lập bảng inventory và risk matrix cho một MBean thực tế.
4. Chọn những thành phần nên giữ, thay đổi, loại bỏ hoặc chuyển sang API quản trị khác.
5. Thiết kế validation, authorization, idempotency, audit và giới hạn thực thi phù hợp.
6. Kiểm tra metadata mà JMX client thực sự thấy qua \`MBeanInfo\`.
7. Phân tích remote JMX, Spring AOP proxies và transaction boundaries khi chúng ảnh hưởng hành vi.
8. Kiểm thử các tình huống lỗi, tải cao, thao tác trùng và mất notification.

## 2. Đánh giá theo câu hỏi vận hành

Không bắt đầu bằng câu hỏi “Lớp này có những public methods nào?”. Nên bắt đầu bằng:

- Operator đang cần biết hoặc làm gì?
- Không có thông tin/hành động này thì sự cố nào khó xử lý?
- Ai là người có thẩm quyền sử dụng nó?
- Tần suất sử dụng và độ khẩn cấp là bao nhiêu?
- Có một nguồn telemetry hoặc runbook khác an toàn hơn không?
- Nếu dữ liệu sai, bị đọc quá thường xuyên hoặc hành động bị gọi nhầm thì điều gì xảy ra?
- Nếu kết nối từ xa đứt giữa chừng, có thể phục hồi kết quả không?

Ví dụ cho một worker xử lý thanh toán:

| Câu hỏi | Giao diện có thể dùng | Cần đánh giá |
|---|---|---|
| Worker còn tiến triển? | \`LastSuccessAt\`, \`ProcessedTotal\` | Độ mới và semantics |
| Có backlog không? | \`PendingCount\` | Chi phí đọc và nguồn dữ liệu |
| Lỗi tăng nhanh? | \`FailedTotal\` + metrics rate | Counter reset và sampling |
| Có thể tạm ngừng nhận việc? | \`pauseIntake()\` | Ảnh hưởng tới SLA và recovery |
| Có thể chạy lại công việc? | \`retryJob(id)\` | Idempotency và authorization |
| Cần biết chuyển trạng thái thất bại? | Notification \`worker.failed\` | Lọc nhiễu, loss/reconnect |
| Có cần xem token kết nối? | Không expose | Rủi ro tiết lộ bí mật |

Điểm cốt lõi: **Khả năng quan sát không đồng nghĩa với quyền thay đổi trạng thái**. Ngay cả read-only attribute cũng có thể có tác động nếu gọi tốn tài nguyên hoặc tiết lộ dữ liệu nhạy cảm.

## 3. Một ma trận đánh giá đơn giản

Có thể đánh giá từng mục theo những tiêu chí sau:

| Tiêu chí | Câu hỏi | Mức độ cần chú ý |
|---|---|---|
| Operational value | Có giúp chẩn đoán hoặc xử lý sự cố? | Cao khi trực tiếp phục vụ quyết định |
| Sensitivity | Có lộ bí mật, PII, topology, dữ liệu nội bộ? | Rủi ro bảo mật |
| Side effect | Có thay đổi trạng thái, tạo job, xóa dữ liệu? | Rủi ro tính đúng |
| Cost | Một lần gọi có tốn CPU, I/O, lock hoặc network? | Rủi ro hiệu năng |
| Concurrency | Có an toàn khi nhiều caller gọi đồng thời? | Rủi ro race |
| Reliability | Remote call timeout có kết quả không xác định? | Rủi ro retry |
| Availability | Có thể block thread pool hoặc làm service chậm? | Rủi ro vận hành |
| Compatibility | Client có phụ thuộc tên, kiểu, semantics? | Rủi ro thay đổi API |
| Auditability | Có cần lưu ai đã làm gì, khi nào? | Kiểm soát |
| Discoverability | Operator có hiểu names/units/description? | Khả năng sử dụng |

Không nhất thiết biến tất cả thành một “điểm” duy nhất. Một attribute chứa password cần bị loại dù giá trị vận hành cao; một operation xóa dữ liệu cần quyền và workflow mạnh, không thể được chấp thuận chỉ nhờ tổng điểm.

## 4. Phân loại mức tác động

Một mô hình định tính để review:

**Mức A — Quan sát nhẹ:** Đọc một snapshot hoặc counter nhỏ, ít overhead, không chứa thông tin nhạy cảm.

**Mức B — Quan sát có chi phí hoặc nhạy cảm:** Đọc dữ liệu tổng hợp lớn, stack/thread details, cấu hình nội bộ hoặc gọi I/O.

**Mức C — Thay đổi trạng thái có kiểm soát:** Setter đổi một giới hạn có validation, operation pause/resume có thể phục hồi.

**Mức D — Thao tác ảnh hưởng lớn:** Reset dữ liệu, restart thành phần, xóa cache toàn hệ thống, làm thay đổi dòng công việc đang chạy.

**Mức E — Hành động nghiệp vụ không phù hợp JMX thông thường:** Thanh toán, hoàn tiền, xóa hồ sơ hoặc tác vụ đòi hỏi audit/approval và giao nhận giao dịch chặt.

Phân loại này là công cụ thảo luận, không phải chuẩn JMX chính thức. Mức độ thực tế phụ thuộc bối cảnh: \`clearCache()\` có thể nhẹ ở local nhưng làm tăng tải nghiêm trọng trong production.

## 5. Attribute read-only: đọc không phải luôn vô hại

Ví dụ đơn giản:

\`\`\`java
@ManagedAttribute(description = "Current pending job count")
public int getPendingCount() {
    return pendingCount.get();
}
\`\`\`

Đây thường là loại management surface có rủi ro thấp nếu:
- Counter được duy trì chính xác.
- Getter không chặn worker threads.
- Giá trị đọc nhanh.
- Không lộ dữ liệu nhạy cảm.
- Đơn vị và thời điểm lấy mẫu rõ.

Ngược lại:

\`\`\`java
@ManagedAttribute(description = "All active customer records")
public List<Customer> getCustomers() {
    return repository.findAll();
}
\`\`\`

có nhiều vấn đề:
- Trả dữ liệu khách hàng có thể vi phạm bảo mật.
- Query toàn bộ database rất nặng khi JMX client poll thường xuyên.
- Danh sách lớn có thể làm chậm serialization hoặc connector.
- Object graph có thể không tương thích remote JMX.
- Tên/kiểu Java nội bộ trở thành phụ thuộc cho external clients.

Giải pháp tốt hơn là expose những aggregate cần thiết, ví dụ \`ActiveCustomerCount\`, hoặc dùng một API quản trị được bảo vệ riêng khi thật sự cần dữ liệu chi tiết.

## 6. Phân tích chi phí của một managed getter

Một monitoring collector có thể đọc mỗi attribute mỗi 10 giây trên hàng trăm JVMs. Nếu mỗi getter query database 500 ms, tổng tải có thể đáng kể.

Nên phân loại nguồn dữ liệu:
- **In-memory counter:** thường chi phí nhỏ.
- **Cached snapshot:** chi phí thấp, có độ trễ cập nhật.
- **Database aggregation:** có chi phí I/O, cần index/query plan.
- **External API:** có latency, timeout và failure modes.
- **Full thread dump/heap dump:** chi phí lớn, không thích hợp polling liên tục.

Với attribute tốn kém, cân nhắc:
1. Chuyển sang snapshot được cập nhật định kỳ.
2. Công bố \`SnapshotTimestamp\` hoặc \`SnapshotAgeSeconds\`.
3. Giới hạn tần suất thực thi.
4. Nếu cần thao tác chẩn đoán có chủ đích, dùng operation riêng thay vì getter.
5. Đo latency trong test bằng workload đại diện.

Một read-only getter mà khóa toàn bộ processing pipeline trong 2 giây có thể có tác động lớn dù không sửa state.

## 7. Tính nhất quán và độ mới của attributes

JMX client có thể đọc \`PendingCount\`, \`ActiveCount\` và \`ProcessedTotal\` ở những thời điểm khác nhau. Không mặc định chúng là một snapshot transactionally consistent.

Nếu cần dữ liệu nhất quán:
- Duy trì một immutable snapshot.
- Trả dữ liệu có \`version\` hoặc \`capturedAt\`.
- Sử dụng OpenTypes/MXBean representation khi cần cấu trúc.
- Nói rõ freshness và accuracy trong description.

Một attribute \`LastSuccessAt\` có thể rỗng khi chưa có lần thành công; mô tả phải phân biệt “chưa từng chạy” với “nguồn dữ liệu không sẵn sàng”.

Không sử dụng giá trị sentinel như \`0\` mà không tài liệu hóa. Chẳng hạn \`LastSuccessEpochMs=0\` có thể bị hiểu nhầm là Unix epoch thay vì chưa có dữ liệu.

## 8. Writable attribute: điều kiện chấp nhận

Ví dụ:

\`\`\`java
private volatile int maxConcurrentJobs = 8;

@ManagedAttribute(description = "Maximum concurrent jobs")
public int getMaxConcurrentJobs() {
    return maxConcurrentJobs;
}

@ManagedAttribute(description = "Maximum concurrent jobs")
public void setMaxConcurrentJobs(int value) {
    if (value < 1 || value > 64) {
        throw new IllegalArgumentException("Allowed range: 1..64");
    }
    maxConcurrentJobs = value;
}
\`\`\`

Writable property cần được xem như **configuration mutation API**. Review phải trả lời:
- Giá trị mới có hiệu lực ngay hay sau restart?
- Có làm gián đoạn tác vụ đang chạy?
- Có phụ thuộc capacity của resource khác?
- Nhiều callers cùng set thì kết quả nào thắng?
- Thay đổi có được lưu bền không?
- Có rollback được không?
- Ai được phép set?
- Có audit log không?
- Có thể bị tool tự động ghi nhầm do mapping cũ không?

Với thay đổi phức tạp, một operation tên rõ như \`requestConcurrencyChange(int)\` có thể truyền đạt preconditions tốt hơn writable attribute. Nhưng operation cũng không tự bổ sung authentication, validation hoặc transaction.

## 9. Operation: rõ tác động và khôi phục

\`@ManagedOperation\` tạo một khả năng được gọi qua JMX. Nó có thể nhẹ như \`resetStatistics()\` hoặc nguy hiểm như \`deletePendingJobs()\`.

Ví dụ operation quản trị có scope rõ:

\`\`\`java
@ManagedOperation(description = "Pause acceptance of new jobs")
public void pauseIntake() {
    workerControl.pauseIntake();
}
\`\`\`

Thiết kế cần làm rõ:
- Pause chỉ dừng nhận việc mới hay dừng cả job đang chạy?
- Thời gian để pause có hiệu lực?
- Gọi pause nhiều lần có an toàn không?
- Nếu JVM restart, trạng thái pause có được khôi phục?
- Caller có thể xác minh kết quả bằng attribute nào?
- Nếu operation thất bại giữa chừng, hệ thống ở trạng thái gì?

### So sánh một số operations

| Operation | Rủi ro chính | Kiểm soát đề xuất |
|---|---|---|
| \`resetStatistics()\` | Mất continuity của counters | Audit; reset scope rõ |
| \`pauseIntake()\` | Giảm throughput | Authorization; state verification |
| \`resumeIntake()\` | Tăng tải bất ngờ | Preconditions; rate limiting |
| \`clearCache()\` | Cache stampede | Concurrency guard; capacity checks |
| \`reloadConfiguration()\` | Runtime config không nhất quán | Validation; rollback |
| \`triggerJob()\` | Duplicate execution | Idempotency key; job status |
| \`terminateWorker()\` | Mất availability | Strong authorization/approval |
| \`deleteAllRecords()\` | Mất dữ liệu | Thường không nên expose qua JMX |

## 10. Các thao tác dài và bất đồng bộ

Một operation JMX đồng bộ chạy nhiều phút có thể gây:
- Timeout ở remote client.
- Tài nguyên connector bị chiếm lâu.
- Kết quả không xác định khi disconnect.
- Retry dẫn đến tạo công việc trùng.
- Tăng tải khi nhiều operators cùng gọi.

Thay vì:

\`\`\`java
@ManagedOperation
public void rebuildIndex() {
    indexService.rebuildEverything();
}
\`\`\`

có thể thiết kế:

\`\`\`java
@ManagedOperation(description = "Submit index rebuild and return job ID")
public String requestIndexRebuild() {
    return indexService.submitRebuild();
}

@ManagedAttribute(description = "Current rebuild state")
public String getRebuildState() {
    return indexService.currentState().name();
}
\`\`\`

Cần quản lý job identity, concurrency và idempotency; việc chỉ trả job ID không tự tạo hệ thống job bền vững.

## 11. Remote invoke timeout và idempotency

Giả sử client gọi \`clearCache()\` qua JMX remote, server thực thi thành công nhưng response không tới client vì mất mạng.

Từ phía client:
\`\`\`text
invoke(clearCache) -> timeout
\`\`\`

Timeout **không chứng minh** operation chưa chạy. Retry ngay có thể gây hai lần xóa cache hoặc hai tác vụ rebuild.

Review operation cần xác định:
- Có idempotent không?
- Có \`requestId\` không?
- Có endpoint để tra cứu trạng thái không?
- Có thể kiểm tra trạng thái trước khi retry không?
- Nếu thực thi hai lần thì hậu quả gì?

Ví dụ \`pauseIntake()\` thường có thể thiết kế idempotent. Một operation như \`chargeCustomer()\` không phù hợp để expose qua JMX vì yêu cầu exactly-once business effect, audit và quyền phức tạp.

## 12. Authorization và nguyên tắc đặc quyền tối thiểu

Công bố một operation không tự bảo vệ nó. Nếu JMX remote connector cho phép caller thực thi, operation có thể bị gọi.

Một thiết kế tốt:
- Read-only monitoring identity.
- Administrative identity riêng với quyền chặt hơn.
- Network segmentation.
- Authentication và authorization của connector.
- TLS hoặc bảo vệ kênh phù hợp.
- Server-side validation và audit.
- Không đưa secrets vào attributes hoặc exception messages.

\`@ManagedOperation(description = "Admin only")\` chỉ là description. Nó không thực thi quyền.

Ngay cả local JMX cũng cần được đánh giá theo quyền của process/user có thể attach và quản trị JVM.

## 13. Notification: giá trị và giới hạn

JMX notification thích hợp để báo:
- Worker chuyển sang FAILED.
- Cấu hình reload thành công hoặc thất bại.
- Hệ thống đạt một trạng thái quan trọng.
- Job quản trị bắt đầu/kết thúc.
- Một resource bị degraded.

Ví dụ metadata:

\`\`\`java
@ManagedNotification(
    name = "com.example.jobs.worker.failed",
    notificationTypes = {"com.example.jobs.worker.failed"},
    description = "Worker entered failed state"
)
\`\`\`

Annotation mô tả loại notification, nhưng để phát cần một broadcaster hoặc \`NotificationPublisher\` thực sự gửi \`Notification\`.

### Tác động của notification không chỉ là phát sự kiện

Một notification được gửi quá thường xuyên có thể:
- Gây tải serialization/remote connector.
- Làm tràn bộ nhớ ở listener hoặc queue bên ngoài nếu không có backpressure.
- Tạo cảnh báo trùng hoặc alert storm.
- Gây mất sự chú ý đối với sự kiện nghiêm trọng.
- Làm lộ payload hoặc runtime state.

Đặc biệt, thông báo cho từng request/job ở hệ thống throughput lớn có thể không phù hợp; metrics và sampled logs thường tốt hơn.

## 14. Notification không phải durable message broker

JMX không mặc định cung cấp event storage, durable replay, offsets hay exactly-once processing. Một listener có thể:
- Chưa đăng ký khi notification được gửi.
- Mất kết nối.
- Được đăng ký hai lần.
- Restart.
- Lỗi khi xử lý payload.
- Nhận nhiều sự kiện cùng logical cause.

Nếu cần lịch sử không mất một sự kiện, phải có nguồn dữ liệu bền vững khác như outbox/event store/broker. JMX notification có thể đóng vai trò báo hiệu để client đọc lại snapshot.

Một cách dùng thích hợp:

\`\`\`text
worker.changed notification
          |
          v
Client reads WorkerState attribute
          |
          v
Updates monitoring dashboard
\`\`\`

Khi reconnect, client đọc lại \`WorkerState\` dù không nhận đủ notifications trong thời gian offline.

## 15. Notification payload và bảo mật

Dữ liệu trong \`Notification.userData\` có thể xuất hiện ở client qua JMX connector. Cần cân nhắc:
- Không có password/token.
- Không chứa PII nếu không cần thiết.
- Có giới hạn kích thước.
- Client có hiểu kiểu dữ liệu không?
- Remote serialization có khả thi không?
- Có thể dùng \`String\`, scalar hoặc OpenType thay cho DTO nội bộ không?
- Có event ID/correlation ID ổn định không?

Ví dụ payload đơn giản:
\`\`\`java
notification.setUserData("job-123");
\`\`\`

Nếu dùng Java object tùy ý, client từ JVM khác có thể thiếu class để deserialize hoặc bị các serialization filters chặn. Không coi một test local thành công là bảo đảm remote interoperability.

## 16. Kết hợp attribute, operation và notification

Một thiết kế thường hữu ích:

\`\`\`text
Managed resource: JobWorker
  |
  +-- Attributes
  |      PendingCount (read-only)
  |      WorkerState (read-only)
  |      LastSuccessTime (read-only)
  |
  +-- Operations
  |      pauseIntake()
  |      resumeIntake()
  |
  +-- Notifications
         worker.paused
         worker.resumed
         worker.failed
\`\`\`

Ba phần bổ sung cho nhau:
- Attribute cho phép đọc trạng thái hiện tại.
- Operation tạo hành động.
- Notification báo chuyển trạng thái.

Đừng chỉ dựa vào notification để xác nhận operation hoàn tất. Sau khi gọi pause, đọc \`WorkerState\` hoặc một status attribute để kiểm tra. Với thao tác bất đồng bộ, cần job ID/status và xử lý timeout.

## 17. Ví dụ Spring management facade

Nên tách management interface khỏi business service lớn:

\`\`\`java
package com.example.operations;

import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.jobs:type=Worker,name=Import",
    description = "Import worker management"
)
public class ImportWorkerManagement {

    private final ImportWorkerService service;

    public ImportWorkerManagement(ImportWorkerService service) {
        this.service = service;
    }

    @ManagedAttribute(description = "Pending jobs at read time")
    public int getPendingCount() {
        return service.pendingCount();
    }

    @ManagedAttribute(description = "Current worker state")
    public String getWorkerState() {
        return service.state().name();
    }

    @ManagedOperation(description = "Pause acceptance of new jobs")
    public void pauseIntake() {
        service.pauseIntake();
    }

    @ManagedOperation(description = "Resume acceptance of new jobs")
    public void resumeIntake() {
        service.resumeIntake();
    }
}
\`\`\`

\`ImportWorkerService\` là dependency nghiệp vụ được giả định trong ví dụ. Các operations phải có validation và authorization theo môi trường. Facade không tự thực thi quyền nhưng giúp quản lý bề mặt JMX rõ ràng hơn.

## 18. Ma trận đánh giá cho facade

| Mục | Loại | Lợi ích | Tác động | Quyết định |
|---|---|---|---|---|
| \`PendingCount\` | Read-only attribute | Chẩn đoán backlog | Polling cost nếu query nặng | Expose qua snapshot |
| \`WorkerState\` | Read-only attribute | Biết tình trạng | Thấp nếu enum nhỏ | Expose |
| \`LastFailureMessage\` | Read-only attribute | Chẩn đoán | Có thể lộ nội dung | Sanitize/giới hạn |
| \`setMaxConcurrentJobs\` | Writable attribute | Runtime tuning | Thay đổi capacity | Validate, audit, phân quyền |
| \`pauseIntake()\` | Operation | Bảo trì | Giảm throughput | Allowlist admin |
| \`clearAllJobs()\` | Operation | Hiếm cần | Mất dữ liệu | Không expose |
| \`worker.failed\` | Notification | Báo lỗi tức thì | Noise, mất/retry | Expose có filter |
| \`job.completed\` mỗi request | Notification | Chi tiết quá mức | Lượng lớn | Dùng metrics/event log |

Đây là ví dụ; yêu cầu thật phụ thuộc SLO, data classification và quyền thực tế.

## 19. Đánh giá khả năng thay đổi API

ObjectName, tên attributes và operations được xem là hợp đồng của monitoring clients.

Thay đổi:
\`\`\`text
com.example.jobs:type=Worker,name=Import
\`\`\`
thành:
\`\`\`text
com.example.import:type=Worker,name=Primary
\`\`\`
có thể làm script cũ gặp \`InstanceNotFoundException\`.

Tương tự:
- Đổi \`PendingCount\` thành \`QueueLength\` phá truy vấn cũ.
- Đổi type \`long\` sang object phức tạp có thể làm client parse sai.
- Xóa operation cũ có thể ảnh hưởng runbooks.
- Đổi notification type cần cập nhật listener filters.

Khi review API, đánh giá dependency của external tools; không coi refactor JMX names là thay đổi nội bộ vô hại.

## 20. Spring AOP và đường gọi thực tế

Một bean vừa có \`@ManagedResource\` vừa có \`@Transactional\` có thể được Spring bọc trong JDK/CGLIB proxy. Khi review operation:
- Metadata có được phát hiện trên target class không?
- Operation có khả dụng qua proxy interface không?
- JMX invocation có đi qua Spring proxy để transaction interceptor có hiệu lực không?
- Có self-invocation làm \`@Transactional\` bị bypass không?
- Bean nào thực sự được exporter đăng ký?

Một management facade gọi transactional service được inject thường tạo ranh giới rõ hơn so với expose thẳng service có nhiều advice. Nhưng phải kiểm chứng bằng integration test; không mặc định mọi proxy configuration đều giống nhau.

## 21. Cách kiểm tra MBeanInfo thực tế

Ví dụ:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server =
    ManagementFactory.getPlatformMBeanServer();

ObjectName name = new ObjectName(
    "com.example.jobs:type=Worker,name=Import"
);

if (!server.isRegistered(name)) {
    throw new IllegalStateException("MBean not registered");
}

var info = server.getMBeanInfo(name);

for (var attr : info.getAttributes()) {
    System.out.printf(
        "%s %s read=%s write=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (var op : info.getOperations()) {
    System.out.println("Operation: " + op.getName());
}

for (var notification : info.getNotifications()) {
    System.out.println("Notification: " + notification.getName());
}
\`\`\`

Trong hệ thống dùng custom MBeanServer, phải lấy đúng server mà Spring exporter sử dụng. MBeanInfo cho thấy interface công bố trên runtime; annotation trong source không đủ chứng minh mọi thứ đã được export đúng.

## 22. Kiểm thử từng nhóm tác động

### 22.1. Attribute test

- MBean có đăng ký không?
- Attribute có đúng tên/kiểu/description không?
- Có vô tình writable không?
- Getter có side effect không?
- Đọc lặp lại có gây tải bất thường không?
- Khi dữ liệu chưa có/không khả dụng, kết quả có rõ nghĩa không?
- Có lộ dữ liệu nhạy cảm không?

### 22.2. Operation test

- Operation có đúng chữ ký không?
- Inputs có được validate không?
- User trái quyền có bị chặn không?
- Có kiểm soát gọi đồng thời không?
- Gọi lặp có an toàn không?
- Nếu fail giữa chừng, state có khôi phục được không?
- Nếu client timeout, có status để đối chiếu không?
- Có audit cho hành động quan trọng không?

### 22.3. Notification test

- Type và payload đúng không?
- Có phát đúng khi event xảy ra không?
- Filter chỉ nhận loại cần thiết không?
- Listener lifecycle và cleanup đúng không?
- Có duplicate callback không?
- Có mất state khi reconnect không?
- Tốc độ phát có gây overload không?
- Payload có thể deserialize từ remote client không?

### 22.4. Security test

- Connector remote được bảo vệ?
- Quyền read khác quyền invoke/write?
- Secrets có bị expose qua attribute, userData hoặc exception không?
- Local/remote callers có đúng phạm vi quyền?

## 23. Kiểm thử chi phí và tải

Một giả định cần tránh: “JMX ít dùng nên operation tốn bao nhiêu cũng được”.

Collectors có thể poll mỗi vài giây trên nhiều services. Một getter query database có thể tạo thêm tải đáng kể. Một diagnostic operation đồng bộ dài có thể làm nghẽn thread connector hoặc tạo contention.

Nên kiểm thử:
- Latency p95/p99 của getter khi có tải.
- Memory allocations khi serialize dữ liệu.
- Ảnh hưởng đến business throughput.
- Lock contention.
- Khi 10 hoặc 100 clients cùng gọi.
- Khi connector network chậm.
- Cleanup khi client disconnect.

Nếu monitoring làm service chậm, thiết kế đó cần chỉnh: cache/snapshot, hạn chế payload, rate-limit hoặc chuyển sang công cụ chẩn đoán on-demand.

## 24. Tài liệu và ownership

Mỗi MBean nên có:
- Owner/team.
- ObjectName convention.
- Danh sách attributes với units, freshness và reset semantics.
- Operations với input, side effects, preconditions, result và recovery.
- Notifications với types, payload schema và delivery limitations.
- Access policy.
- Runbook.
- Compatibility/deprecation policy.

Một description ngắn trong \`@ManagedAttribute\` hữu ích nhưng không thay thế tài liệu cho operation có tác động lớn.

## 25. Khi nào không nên dùng JMX?

Một số tình huống nên ưu tiên công cụ khác:
- Workflow nghiệp vụ cần authentication/approval, audit và idempotent requests: administrative REST/gRPC API được bảo vệ.
- Metrics lịch sử và alerting: Micrometer/Prometheus hoặc observability stack tương đương.
- Distributed tracing: tracing infrastructure.
- Event không được mất: durable broker/event store.
- Bulk data export: batch/report API.
- Configuration có versioning và approvals: configuration management system.

JMX vẫn thích hợp cho trạng thái JVM-local, diagnostic attributes và các thao tác quản trị quy mô nhỏ. Việc chọn công cụ dựa trên mức tác động giúp tránh dùng JMX như một backdoor để bỏ qua các quy trình nghiệp vụ.

## 26. Checklist review thực hành

Trước khi approve một management surface, trả lời:

1. Thành phần này phục vụ câu hỏi vận hành nào?
2. Có cần phơi bày qua JMX không?
3. Đây là read-only, writable, operation hay notification?
4. Có dữ liệu nhạy cảm không?
5. Có side effect hoặc rủi ro tính đúng không?
6. Có thể bị gọi thường xuyên không?
7. Chi phí latency, CPU, memory và I/O là bao nhiêu?
8. Có gọi đồng thời và retry không?
9. Khi remote disconnect, caller xác định kết quả bằng gì?
10. Có đủ validation và authorization không?
11. Có audit và runbook không?
12. Tên/kiểu/semantics có ổn định không?
13. Đã kiểm tra MBeanInfo thực tế chưa?
14. Đã test failure, overload và restart/reconnect chưa?
15. Có phương án ít rủi ro hơn không?

Review không nhất thiết có câu trả lời “có” cho mọi câu. Quan trọng là mọi tác động đáng kể được nhận diện và xử lý có chủ đích.

## 27. Bài tập thực hành

### Bài A — Inventory management surface

Cho một service có 12 public methods, hãy xác định:
- Ba attributes read-only hữu ích.
- Một writable attribute có thể chấp nhận được.
- Hai operations thật sự cần.
- Một notification đáng phát.
- Những methods nên giữ nội bộ.

Giải thích dựa trên lợi ích và rủi ro, không dựa trên sở thích code style.

### Bài B — Review attribute tốn kém

1. Tạo getter đọc tất cả database records.
2. Đo latency khi poll nhiều lần.
3. Chuyển sang snapshot counter.
4. Thêm timestamp/freshness.
5. Đề xuất điều kiện để collector không poll quá thường xuyên.

### Bài C — Operation có tác động

1. Tạo \`pauseIntake()\` và \`resumeIntake()\`.
2. Định nghĩa trạng thái hợp lệ và idempotency.
3. Viết validation.
4. Kiểm thử gọi lặp và đồng thời.
5. Tạo audit record trong môi trường test.

### Bài D — Remote timeout

1. Giả lập operation tạo job.
2. Làm client mất response sau khi server nhận request.
3. Kiểm tra nguy cơ retry tạo job mới.
4. Thêm request ID hoặc status lookup.
5. Xác minh duplicate request không nhân đôi side effect.

### Bài E — Notification

1. Tạo \`worker.failed\` notification.
2. Đăng ký listener với filter.
3. Kiểm tra type/payload/sequence.
4. Thử disconnect/reconnect.
5. Đọc lại WorkerState snapshot.
6. Giải thích vì sao notification không thay durable event history.

### Bài F — Security

1. Tạo secret giả trong cấu hình.
2. Kiểm tra tất cả attributes không lộ secret.
3. Dùng user read-only và admin trong connector test.
4. Xác minh read được phép nhưng invoke bị chặn với identity thiếu quyền.
5. Kiểm tra audit khi admin thực hiện operation.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** Read-only attribute có luôn an toàn không?  
**Trả lời:** Không. Nó có thể lộ dữ liệu nhạy cảm hoặc tạo tải lớn.

**Câu 2.** Writable attribute khác read-only ở điểm nào quan trọng nhất?  
**Trả lời:** Nó có thể thay đổi runtime state, cần validation, authorization và consistency.

**Câu 3.** Khi nào operation nên trả job ID thay vì chạy đồng bộ?  
**Trả lời:** Khi tác vụ dài, có nguy cơ timeout, cần theo dõi trạng thái và retry có kiểm soát.

**Câu 4.** JMX notification có bảo đảm replay đầy đủ sau reconnect?  
**Trả lời:** Không mặc định, cần snapshot hoặc durable event store nếu không được mất event.

**Câu 5.** \`@ManagedOperation\` có tự cấp quyền admin?  
**Trả lời:** Không. Authentication/authorization phải được cấu hình riêng.

**Câu 6.** Vì sao cần xem \`MBeanInfo\`?  
**Trả lời:** Để kiểm tra interface thực tế được expose, kể cả writable flags và operation signatures.

**Câu 7.** Một operation bị timeout có chắc chưa thực thi?  
**Trả lời:** Không. Cần idempotency/status để xử lý kết quả không rõ.

**Câu 8.** Vì sao facade quản trị hữu ích?  
**Trả lời:** Nó giữ bề mặt JMX nhỏ, có ownership và tách khỏi business implementation details.

**Câu 9.** Notification phát quá thường xuyên có tác động gì?  
**Trả lời:** Có thể gây overload, alert storm và tăng chi phí serialization.

**Câu 10.** Khi nào nên chọn API khác JMX?  
**Trả lời:** Khi workflow cần security, audit, reliability hoặc scale vượt khả năng phù hợp của JMX.

## 29. Ghi nhớ

- Attribute, operation và notification có mức tác động khác nhau, cần review riêng.
- Lợi ích vận hành phải tương xứng với security, cost và side-effect risk.
- Read-only không tự an toàn; writable và invoke cần kiểm soát mạnh hơn.
- Tránh getter nặng hoặc trả object graph không kiểm soát.
- Operations cần validation, idempotency, concurrency, audit và recovery semantics.
- Remote timeout không chứng minh operation chưa chạy.
- Notifications không có durable replay mặc định; dùng snapshot/resync và event store khi cần.
- Tách management facade khỏi service nghiệp vụ khi giúp giảm bề mặt quản trị.
- Kiểm tra \`MBeanInfo\` trên MBeanServer thực tế để xác minh exposed interface.
- Thay đổi names/types là thay đổi management API contract.
- JMX hữu ích cho JVM-local state, nhưng không thay mọi hệ thống observability và workflow quản trị.
- Review management API theo tác động chứ không theo số lượng annotations hoặc methods.

### Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework Reference — Exporting MBeans: https://docs.spring.io/spring-framework/reference/integration/jmx/exporting.html
- Spring Framework Reference — Notifications: https://docs.spring.io/spring-framework/reference/integration/jmx/notifications.html
- Spring Framework Javadoc — \`ManagedAttribute\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedAttribute.html
- Spring Framework Javadoc — \`ManagedOperation\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Spring Framework Javadoc — \`ManagedNotification\`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedNotification.html
- Java SE 21 API — \`MBeanInfo\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanInfo.html
- Java SE 21 API — \`MBeanServer\`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
