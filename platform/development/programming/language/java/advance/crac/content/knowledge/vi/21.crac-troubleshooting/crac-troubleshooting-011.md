# Thu thập bằng chứng lỗi mà không làm lộ dữ liệu trong checkpoint

Khi một ứng dụng Java dùng CRaC gặp lỗi checkpoint hoặc restore, nhóm vận hành cần thu thập đủ bằng chứng để xác định lỗi đến từ JVM, CRIU, kernel, container runtime, tài nguyên ứng dụng hay dependency bên ngoài. Tuy nhiên, ảnh checkpoint là trạng thái bộ nhớ của tiến trình. Nó có thể chứa password, token, private key, session cookie, dữ liệu cá nhân, request body, cache và thông tin nghiệp vụ đang được xử lý.

Vì vậy, **không coi checkpoint image, heap dump hoặc core dump là log chẩn đoán thông thường**. Một gói bằng chứng ban đầu nên ưu tiên log đã được kiểm soát, timeline callback, phiên bản runtime, trạng thái tài nguyên, mã lỗi, metric và checksum. Chỉ truy cập nội dung bộ nhớ khi có lý do điều tra cụ thể, người phê duyệt phù hợp và một quy trình lưu trữ riêng có kiểm soát.

Mục tiêu là giữ được khả năng tái dựng sự cố mà không sao chép dữ liệu nhạy cảm sang ticket, chat, email hoặc hệ thống log có phạm vi truy cập rộng.

## 1. Vì sao checkpoint cần được xem là dữ liệu nhạy cảm?

Checkpoint có thể lưu trạng thái heap và các thành phần tiến trình khác theo khả năng của JDK/CRaC và nền tảng. Nếu ứng dụng đang giữ dữ liệu nhạy cảm trong memory tại thời điểm checkpoint, dữ liệu đó có thể xuất hiện trong ảnh.

Ví dụ nội dung có thể nằm trong memory:

- Password database, access token, refresh token và API key.
- Private key, TLS material hoặc credential object đã được giải mã.
- Session cookie, authorization header và thông tin nhận dạng người dùng.
- Request/response body, dữ liệu thanh toán hoặc thông tin nghiệp vụ.
- Cache chứa dữ liệu cá nhân, hồ sơ khách hàng hoặc quyền truy cập.
- Query parameter, SQL bind value và message payload.
- Đối tượng chứa URL nội bộ, hostname, IP, đường dẫn file hoặc cấu hình hạ tầng.

Ngay cả khi ứng dụng đã đóng connection pool trước checkpoint, password hoặc token có thể vẫn còn trong object cấu hình, chuỗi immutable, cache hoặc bản sao do thư viện tạo ra. Việc gọi `Arrays.fill()` trên một `char[]` cũng không chứng minh mọi bản sao secret đã biến mất khỏi heap.

Các loại artifact chẩn đoán khác cũng có thể chứa dữ liệu nhạy cảm:

| Artifact | Nội dung có thể chứa | Mức thận trọng |
| --- | --- | --- |
| CRaC checkpoint image | Trạng thái tiến trình, heap, thread, native/process state và dữ liệu ứng dụng | Rất cao; xử lý như dữ liệu nhạy cảm của ứng dụng. |
| JVM heap dump | Object graph, chuỗi, byte array, credential và payload | Rất cao; có thể tiết lộ dữ liệu trực tiếp. |
| Core dump | Memory của process, register, stack và vùng native | Rất cao; có thể chứa secret và payload. |
| JFR recording | Event runtime, class/method, exception, thread, socket hoặc custom event tùy cấu hình | Cao; phải kiểm tra event và nội dung trước khi chia sẻ. |
| Thread dump | Stack trace, thread name, lock/monitor và đôi khi thông tin nằm trong exception hoặc tên tác vụ | Trung bình đến cao; rà soát trước khi gửi ra ngoài. |
| JVM/CRIU log | PID, path, mount, command, namespace, lỗi hệ thống và có thể có thông tin cấu hình | Trung bình đến cao; lọc và giới hạn truy cập. |
| Metrics/health output | Tên dependency, endpoint, label, lỗi và trạng thái hoạt động | Phụ thuộc label và cách instrumentation; tránh đưa identifier/secret vào label. |
| Manifest/checksum | Build, version, artifact id, đường dẫn hoặc hash | Thường ít nhạy cảm hơn nhưng vẫn có thể tiết lộ topology và quan hệ artifact. |

Không có artifact nào tự động an toàn chỉ vì nó không phải checkpoint image. Phải xem nội dung thực tế, mục đích thu thập và phạm vi người nhận.

## 2. Phân loại bằng chứng trước khi thu thập

Hãy chia bằng chứng thành ba nhóm để quyết định cách xử lý:

**Nhóm A — Metadata và trạng thái ít nhạy cảm:** phiên bản JDK/CRaC/CRIU, kernel, architecture, thời điểm, duration, exit code, loại exception, số lượng retry, trạng thái readiness, dung lượng filesystem và checksum. Đây thường là lựa chọn đầu tiên.

**Nhóm B — Log và diagnostic output cần rà soát:** log JVM/CRIU, thread dump, JFR, command line, system properties, process tree, mount table, DNS result và endpoint. Chúng có thể chứa path, hostname, username, token hoặc payload nên cần lọc trước khi chia sẻ.

**Nhóm C — Nội dung bộ nhớ và artifact gốc:** checkpoint image, heap dump, core dump, raw packet capture và file chứa secret. Chỉ thu thập khi cần thiết, lưu riêng, mã hóa và giới hạn người được phép truy cập.

| Nhóm | Ví dụ | Cách dùng thông thường |
| --- | --- | --- |
| A | Runtime version, callback duration, error code, readiness transition | Có thể đưa vào evidence package sau khi kiểm tra metadata. |
| B | JVM/CRIU logs, thread dump, JFR, `/proc` output | Lưu bản gốc trong vùng hạn chế; tạo bản đã redaction để chia sẻ. |
| C | Checkpoint, heap/core dump, packet capture có payload | Không đính kèm ticket/chat; chỉ truy cập qua quy trình incident đặc biệt. |

Nếu chưa biết một file có chứa secret hay không, hãy phân loại nó ở mức nhạy cảm cao cho đến khi kiểm tra xong.

## 3. Bắt đầu bằng timeline và correlation ID

Một timeline chính xác thường hữu ích hơn việc thu thập thật nhiều file. Ghi lại các mốc thời gian theo UTC và gắn với một `checkpointAttemptId`/`restoreAttemptId` ổn định.

Các mốc nên có:

1. Ứng dụng bắt đầu chạy và hoàn tất warm-up.
2. Readiness chuyển sang từ chối traffic.
3. Resource bắt đầu `beforeCheckpoint`.
4. Từng Resource bắt đầu/kết thúc drain, flush, đóng socket hoặc pool.
5. Lệnh checkpoint được gửi và kết thúc.
6. JVM/CRIU báo thành công hoặc lỗi; process gốc thay đổi trạng thái.
7. Dependency thay đổi trạng thái trong khoảng checkpoint nếu có.
8. Lệnh restore bắt đầu.
9. JVM bắt đầu/hoàn tất `afterRestore`.
10. Từng Resource reconnect, validate và báo kết quả.
11. Readiness chuyển sang chấp nhận traffic hoặc tiếp tục `NOT_READY`.
12. Request/message đầu tiên sau restore thành công hoặc thất bại.

Ví dụ log có cấu trúc:

```text
timestamp=2026-11-13T09:00:00.120Z attempt=cp-7f2a event=readiness state=REFUSING_TRAFFIC
timestamp=2026-11-13T09:00:00.145Z attempt=cp-7f2a resource=db-pool event=beforeCheckpoint-start
timestamp=2026-11-13T09:00:00.390Z attempt=cp-7f2a resource=db-pool event=beforeCheckpoint-complete duration_ms=245
timestamp=2026-11-13T09:00:00.410Z attempt=cp-7f2a event=checkpoint-requested
timestamp=2026-11-13T09:00:01.900Z attempt=cp-7f2a event=checkpoint-failed error_type=DumpError
```

Ví dụ chỉ chứa định danh đã được làm giả và metadata. Không ghi password, token, SQL bind value, payload, Authorization header hoặc nội dung secret vào log callback.

Đồng hồ host/container có thể lệch. Ghi rõ timezone, nguồn thời gian và độ lệch ước tính nếu biết. Khi ghép log từ JVM, CRIU, database và orchestration, dùng cả timestamp lẫn attempt id để tránh suy luận sai thứ tự do clock skew.

## 4. Thu thập metadata runtime trước khi đọc memory

Các thông tin sau thường giúp thu hẹp phạm vi sự cố mà không cần dump heap:

- Application build/version và Git commit.
- JDK vendor, version, build và JVM flags liên quan đã được lọc.
- CRaC library/runtime version.
- CRIU version và capability/runtime mode nếu sử dụng CRIU.
- OS distribution, kernel version và CPU architecture.
- Container runtime, container image digest và Kubernetes/node version nếu áp dụng.
- Cgroup limits, memory pressure, OOM event và filesystem capacity.
- Checkpoint path dưới dạng identifier đã sanitize; không để lộ path chứa username hoặc tenant nhạy cảm.
- Loại filesystem/mount và quyền truy cập cần thiết.
- Dependency version/endpoint identity ở mức đã được phép công bố.

Ví dụ lệnh lấy thông tin cơ bản trên Linux:

```bash
java -version
uname -srmo
criu --version
df -h /var/lib/myapp
```

Các lệnh trên chỉ là ví dụ; lệnh `criu` chỉ có nếu CRIU được cài trên host và có trong PATH. Đường dẫn filesystem có thể tiết lộ cấu trúc hạ tầng, nên thay bằng mount label hoặc đường dẫn đã sanitize trong bản gửi ra ngoài. Không chạy lệnh in toàn bộ environment hoặc system properties chỉ để lấy metadata.

Nếu cần JVM diagnostic summary, ưu tiên các lệnh chỉ trả version, uptime hoặc memory summary đã được phê duyệt. Ví dụ `jcmd <pid> VM.version` và `jcmd <pid> VM.uptime` thường ít rủi ro hơn việc xuất toàn bộ command line hoặc system properties. Vẫn phải rà soát output trước khi đính kèm.

## 5. Chọn log JVM và CRIU phù hợp

Log JVM và CRIU thường là bằng chứng quan trọng để xác định lỗi ở bước chuẩn bị, dump, restore hoặc resource callback.

Nên thu thập:

- Log ứng dụng bao quanh checkpoint/restore attempt.
- Log JVM có thông báo callback CRaC, exception type và kết quả thao tác.
- Log CRIU hoặc container runtime tương ứng với đúng attempt.
- Kernel/system log nếu có lỗi syscall, permission, cgroup hoặc OOM.
- Orchestrator event liên quan đến container restart, node pressure, mount hoặc network.

Khi đọc log, tập trung vào:

- Thời điểm lỗi đầu tiên, không chỉ dòng cuối cùng.
- PID và namespace context của process liên quan.
- Loại operation đang thực hiện: prepare, dump, restore hay reconnect.
- Error code/errno, exception class và component phát sinh.
- Resource callback cuối cùng hoàn tất.
- Thay đổi trạng thái process hoặc container quanh thời điểm lỗi.

CRIU log có thể chứa đường dẫn filesystem, PID, namespace, mount, socket endpoint và thông tin cấu hình. Một số log hoặc wrapper có thể in command/argument; rà soát trước khi gửi ra ngoài. Không giả định log hệ thống là đã được redaction.

Giữ bản gốc trong vùng lưu trữ incident hạn chế. Tạo một bản sao làm việc để redaction, giữ lại bản gốc không sửa đổi cho mục đích audit và so sánh.

## 6. Những lệnh chẩn đoán có nguy cơ làm lộ secret

Một số lệnh rất hữu ích khi điều tra nhưng có thể xuất dữ liệu nhạy cảm. Không đưa output thô của chúng vào ticket hoặc chat.

| Lệnh/nguồn | Nguy cơ |
| --- | --- |
| `jcmd <pid> GC.heap_dump ...` | Heap dump có thể chứa password, token, payload và object nhạy cảm. |
| Core dump từ kernel hoặc debugger | Có thể chứa toàn bộ vùng memory của process. |
| `jcmd <pid> VM.system_properties` | System property có thể chứa credential, URL có token hoặc cấu hình nội bộ. |
| `jcmd <pid> VM.command_line` / JVM flags | Argument có thể chứa secret truyền trực tiếp trên command line hoặc path nhạy cảm. |
| `cat /proc/<pid>/environ` hoặc `ps eww` | Có thể in environment variable, bao gồm secret. |
| Thread dump/JFR | Có thể chứa class, thread name, exception, endpoint, custom event hoặc dữ liệu do ứng dụng đưa vào. |
| Packet capture đầy đủ payload | Có thể chứa token, cookie, request/response body hoặc dữ liệu cá nhân. |
| `strings` trên checkpoint/core/heap dump | Có thể trích xuất chuỗi secret từ binary memory artifact. |

Không chạy các lệnh này theo thói quen trong môi trường production. Nếu cần, phải có mục đích điều tra cụ thể, phê duyệt, vị trí lưu an toàn và người chịu trách nhiệm xử lý output. Không paste output trực tiếp vào kênh hỗ trợ chung.

## 7. Khi nào cần thread dump, JFR, heap dump hoặc core dump?

Chọn artifact theo câu hỏi cần trả lời:

| Câu hỏi điều tra | Bằng chứng ưu tiên | Lưu ý bảo mật |
| --- | --- | --- |
| Callback nào bị treo? | Callback timeline, thread dump đã rà soát, log timeout | Thread name/stack có thể tiết lộ tên tác vụ, path hoặc endpoint. |
| Thread đang chờ lock nào? | Thread dump có lock information, log lock wait | Chỉ chia sẻ phần thread liên quan và redaction thông tin không cần thiết. |
| JVM/GC có áp lực memory không? | GC log, memory summary, container memory metric | Tránh heap dump nếu metric/GC log đủ trả lời. |
| Sự kiện runtime nào xảy ra trước restore? | JFR recording với event set tối thiểu | JFR có thể chứa event nhạy cảm tùy cấu hình và custom event. |
| Object nào giữ reference hoặc secret? | Heap dump trong môi trường phân tích hạn chế | Đây là dữ liệu cực nhạy cảm; không đưa vào evidence package thông thường. |
| Native crash ở đâu? | Core dump và native stack | Core dump có thể chứa toàn bộ memory; quyền truy cập rất hạn chế. |
| Lỗi syscall/namespace nào xảy ra? | CRIU log, kernel log, runtime event | Rà soát PID, path, mount và endpoint. |

Nguyên tắc là dùng bằng chứng ít nhạy cảm nhất đủ trả lời câu hỏi. Nếu thread dump và log callback đã chỉ ra `beforeCheckpoint` chờ `Future.get()` vô hạn, thường chưa cần tạo heap dump. Nếu chỉ cần biết memory pressure, GC log và cgroup metric có thể đủ.

### Thread dump

Thread dump hữu ích để tìm deadlock, thread bị block hoặc worker không drain. Tuy nhiên, stack trace và thread name có thể tiết lộ class nội bộ, tenant, URL hoặc tên job. Rà soát nội dung trước khi chia sẻ và chỉ giữ thread liên quan nếu có thể.

### JFR

JFR có thể giúp phân tích CPU, allocation, lock contention, GC và socket event. Chọn event set cần thiết, giới hạn thời gian recording và kiểm tra custom event. Không giả định JFR luôn chỉ chứa metadata vô hại.

### Heap dump và core dump

Chỉ tạo khi câu hỏi điều tra không thể trả lời bằng bằng chứng ít nhạy cảm hơn. Lưu vào vùng forensic riêng, mã hóa, hạn chế quyền, ghi audit access và không đính kèm vào ticket/chat. Nếu có thể, thực hiện phân tích trong môi trường cô lập, không sao chép raw dump sang máy cá nhân.

## 8. Không đưa checkpoint image vào evidence package thông thường

Một evidence package dùng cho ticket hoặc báo cáo vận hành thường chỉ cần:

- Timeline và correlation IDs.
- JVM/CRIU/runtime log đã rà soát.
- Version/build/platform metadata.
- Callback result và exception type.
- Readiness, dependency health và resource metrics.
- Exit status/error code.
- Checksum của checkpoint artifact, nếu cần xác định đúng artifact.
- Manifest mô tả nội dung gói và mức redaction.

Không đưa toàn bộ thư mục checkpoint vào archive log, không đính kèm heap/core dump và không gửi ảnh qua email/chat. Nếu chuyên gia cần kiểm tra image, cung cấp artifact id hoặc đường dẫn trong kho lưu trữ hạn chế và cấp quyền truy cập theo quy trình riêng. Người nhận cần biết đây là dữ liệu memory nhạy cảm, mục đích truy cập, thời hạn và cách xóa bản sao.

Checksum của checkpoint có thể giúp xác định artifact mà không đọc nội dung. Tuy nhiên, hash vẫn là metadata liên kết artifact; tránh công bố nếu nó có thể tiết lộ việc hai môi trường đang dùng cùng một ảnh hoặc giúp đối chiếu dữ liệu nhạy cảm. Chỉ đưa vào package khi cần truy vết.

## 9. Redaction và giảm thiểu dữ liệu

Redaction cần thực hiện trên bản sao, giữ nguyên bản gốc trong vùng hạn chế. Đừng chỉnh sửa log gốc tại chỗ vì có thể phá vỡ chain of custody.

Những trường thường cần loại bỏ hoặc thay thế:

- `Authorization`, `Cookie`, `Set-Cookie`, API key và bearer token.
- Password, secret, private key và connection string có credential.
- Query parameter chứa token hoặc PII.
- Request/response body và SQL bind value.
- Email, số điện thoại, user id hoặc tenant id nếu không cần cho chẩn đoán.
- Hostname, IP, mount path và username hệ thống nếu thuộc thông tin hạ tầng hạn chế.
- PID/namespace id nếu báo cáo ra ngoài không cần định danh chính xác.

Ví dụ redaction:

```text
Trước:
database_url=jdbc:postgresql://db-prod-17.internal:5432/orders
username=service_orders
password=SuperSecretValue
request_user=customer-918273

Sau:
database_endpoint=<DB_ENDPOINT_REDACTED>
username=<SERVICE_ID_REDACTED>
password=<REDACTED>
request_user=<SUBJECT_ID_REDACTED>
```

Nếu cần giữ khả năng liên kết cùng một user/endpoint giữa nhiều log, dùng pseudonym nhất quán có kiểm soát, ví dụ `subject-<HMAC-prefix>`, với key HMAC được bảo vệ riêng. Không dùng hash không khóa cho dữ liệu có không gian giá trị nhỏ như email hoặc user id nếu có thể dò ngược bằng dictionary.

Không redaction theo kiểu thay mọi chuỗi trông giống token một cách mù quáng rồi làm mất error code hoặc cấu trúc cần chẩn đoán. Hãy xác định schema log, danh sách field nhạy cảm và kiểm tra mẫu sau khi redaction. Nếu không chắc, giữ dữ liệu trong vùng hạn chế và chỉ chia sẻ bản tóm tắt.

## 10. Log callback CRaC an toàn ngay từ thiết kế

Logging có cấu trúc giúp giảm nhu cầu trích xuất raw memory. Mỗi Resource nên log event và metadata, không log nội dung resource.

Ví dụ:

```java
logger.info(
    "crac_resource_before_checkpoint_complete resource={} durationMs={} status={}",
    "database-pool",
    durationMillis,
    "SUCCESS");
```

Tránh:

```java
logger.info("Database configuration: {}", databaseConfiguration);
logger.info("Request payload before checkpoint: {}", requestBody);
logger.info("Credential used by pool: {}", password);
```

Các trường hữu ích cho log callback:

- Attempt id và resource id ổn định nhưng không chứa dữ liệu người dùng.
- Event name, phase và kết quả.
- Duration và timeout budget.
- Số request/transaction/worker còn hoạt động.
- Exception class và error code đã phân loại.
- Dependency category và trạng thái health, không phải secret/payload.
- Readiness transition.

Nếu exception message có thể chứa URL, SQL, username hoặc payload, chỉ log exception class và error code trong log chia sẻ. Bản đầy đủ có thể lưu riêng với quyền hạn chế nếu thực sự cần.

## 11. Thu thập process và namespace metadata có chọn lọc

PID và namespace giúp liên kết log JVM với CRIU/runtime, nhưng chúng là định danh tạm thời. Một PID có thể được tái sử dụng; cùng process có thể có PID khác nhau ở host và container namespace.

Có thể cần thu thập:

- PID trong container và host PID nếu runtime cung cấp.
- `NSpid`, `PPid` và PID namespace mapping.
- Container ID, Pod UID hoặc workload identity.
- Namespace inode và cgroup path ở mức cần thiết.
- Process start time và executable identity.

Không lưu PID đơn lẻ làm identity bền vững xuyên qua restore. Khi chia sẻ log ra ngoài, có thể thay PID bằng nhãn `java-process-A` nếu số thật không cần thiết. Giữ bản mapping đầy đủ trong incident store có kiểm soát để đội vận hành nội bộ vẫn truy vết được.

Tránh thu thập toàn bộ `/proc/<pid>/environ` hoặc command line nếu chúng có thể chứa secret. Nếu cần biết một flag có được bật hay không, trích xuất đúng tên flag và bỏ giá trị nhạy cảm thay vì gửi toàn bộ command line.

## 12. Thu thập dependency evidence mà không lộ payload

Khi dependency lỗi, thường chỉ cần metadata của request/kết nối:

- Dependency logical name hoặc pseudonym.
- Host/port đã redaction nếu cần.
- Connect/read/query timeout cấu hình.
- Thời gian bắt đầu/kết thúc và duration.
- HTTP status, SQLState, broker error code hoặc exception class.
- Retry count, backoff và circuit breaker state.
- Connection pool active/idle/pending và số connection bị loại bỏ.
- DNS lookup result ở mức đã được phép công bố.
- TLS handshake outcome và certificate expiry metadata, không phải private key.
- Readiness/health result.

Không cần log raw SQL bind parameter, HTTP body, broker payload hoặc secret để chứng minh dependency timeout. Với request cần tương quan, dùng correlation id ngẫu nhiên hoặc HMAC pseudonym thay vì user identifier thật.

## 13. Checksum, manifest và chain of custody

Khi cần giữ checkpoint image hoặc dump để forensic analysis, phải xác định chính xác artifact nào đã được thu thập và có bị thay đổi hay không.

Một manifest có thể ghi:

| Trường | Mục đích |
| --- | --- |
| Incident id | Liên kết với hồ sơ sự cố. |
| Artifact id | Định danh artifact trong kho lưu trữ hạn chế. |
| Source workload identity | Xác định service/container mà không cần công bố secret. |
| Capture timestamp (UTC) | Thời điểm tạo bản sao bằng chứng. |
| Original artifact timestamp | Thời điểm checkpoint hoặc dump được tạo. |
| SHA-256 | Kiểm tra tính toàn vẹn của bản thu thập. |
| Collector identity | Service/nhân sự được phép thu thập. |
| Storage location/class | Vị trí lưu và mức phân loại dữ liệu. |
| Encryption key id | Tham chiếu key mã hóa, không chứa key. |
| Access/audit reference | Nơi ghi nhận lần đọc/copy/restore. |
| Redaction status | Bản gốc hay bản đã redaction; công cụ/policy áp dụng. |
| Retention/deletion date | Thời điểm xem xét xóa. |

Ví dụ tạo checksum cho một archive đã được đóng gói:

```bash
sha256sum checkpoint-evidence.tar > checkpoint-evidence.tar.sha256
sha256sum --check checkpoint-evidence.tar.sha256
```

Lệnh chỉ kiểm tra tính toàn vẹn của file archive; nó không chứng minh checkpoint hợp lệ, an toàn hoặc tương thích. Không đưa private key hoặc credential mã hóa vào cùng manifest.

Chain of custody cần ghi ai/automation nào đã tạo, sao chép, giải mã, phân tích hoặc xóa artifact, thời điểm, lý do và nơi lưu. Khi có nhiều bản sao, mỗi bản phải có checksum và quan hệ nguồn gốc rõ ràng.

## 14. Lưu trữ bằng chứng an toàn

Evidence store cần có mức bảo vệ tương xứng với dữ liệu có thể nằm trong artifact:

- Encryption at rest và encryption in transit.
- Quyền truy cập theo least privilege và service identity riêng.
- MFA/approval cho thao tác tải raw checkpoint hoặc dump nếu hệ thống hỗ trợ.
- Audit log cho đọc, copy, download, decrypt và delete.
- Network boundary riêng; không public bucket hoặc shared folder rộng.
- Retention ngắn nhất đáp ứng incident investigation và legal requirements.
- Backup/replication của evidence store theo policy đã được phê duyệt.
- Quản lý encryption key tách khỏi nơi lưu artifact.
- Không cho phép tự động index raw checkpoint/heap dump vào hệ thống tìm kiếm hoặc AI ingestion không được phê duyệt.

Không dùng cùng một quyền truy cập cho log thường và raw memory artifact. Nhân sự cần xem timeline không nhất thiết cần quyền đọc heap dump hoặc checkpoint image.

## 15. Chia sẻ bằng chứng trong ticket, chat và với vendor

Trước khi gửi file ra khỏi incident store, xác định rõ người nhận cần biết điều gì.

Một ticket kỹ thuật thông thường có thể nhận:

- Tóm tắt lỗi và timeline đã redaction.
- JVM/CRIU log đã lọc.
- JDK/CRaC/CRIU/kernel/runtime version.
- Error code, exception class và callback/resource cuối cùng.
- Metrics, readiness state và checksum nếu cần.
- Các bước tái hiện không chứa dữ liệu thật.

Không gửi:

- Toàn bộ checkpoint directory.
- Heap dump/core dump thô.
- Environment dump, system properties hoặc command line chưa rà soát.
- Secret, token, private key, session cookie.
- Request/message/database payload thật nếu không cần thiết.

Nếu vendor cần raw artifact, dùng kênh upload bảo mật đã được tổ chức phê duyệt, thỏa thuận phạm vi sử dụng và retention, giới hạn người được truy cập và ghi nhận artifact id. Không chuyển file qua email cá nhân hoặc chat thông thường.

## 16. Quy trình thu thập bằng chứng theo từng bước

Một quy trình có thể áp dụng cho sự cố checkpoint/restore:

### Bước 1: Ghi nhận incident và bảo toàn trạng thái

- Tạo incident id và checkpoint/restore attempt id.
- Ghi thời điểm UTC, workload identity, build và môi trường.
- Ghi nhận process/container state trước khi restart hoặc cleanup.
- Tránh xóa checkpoint, log hoặc staging directory trước khi biết chúng có liên quan tới sự cố không.

### Bước 2: Thu thập bằng chứng nhóm A

- Version JDK/CRaC/CRIU/kernel/container runtime.
- Exit code, error code và exception class.
- Callback timeline, duration, timeout budget và readiness transitions.
- Memory/cgroup/disk metrics và dependency health.
- Artifact id và checksum nếu cần.

### Bước 3: Thu thập log nhóm B

- Copy JVM, CRIU, runtime và application log vào incident store.
- Giữ bản gốc read-only.
- Tạo working copy và chạy redaction.
- Kiểm tra output bằng mắt hoặc công cụ DLP trước khi chia sẻ.

### Bước 4: Xác định câu hỏi còn thiếu

Ví dụ: callback nào bị treo, thread nào giữ lock, native crash ở đâu, hay object nào còn giữ credential cũ? Chọn artifact tiếp theo theo câu hỏi đó, không dump toàn bộ memory ngay từ đầu.

### Bước 5: Nếu cần raw memory artifact

- Ghi rõ lý do và người phê duyệt.
- Tạo artifact trong storage forensic riêng.
- Mã hóa ngay khi thu thập hoặc trước khi rời host.
- Hash và ghi manifest/chain of custody.
- Hạn chế người phân tích và thời hạn truy cập.
- Không sao chép sang ticket/chat; chia sẻ artifact id hoặc kênh chuyên dụng.

### Bước 6: Tạo evidence package đã redaction

Chỉ đưa các file cần thiết, manifest, checksum và mô tả mức redaction. Kiểm tra không có file tạm, secret hoặc raw dump lọt vào archive.

### Bước 7: Kết thúc và cleanup

Khi incident kết thúc, rà soát retention, thu hồi quyền tạm thời, xóa working copy và artifact không còn cần thiết theo policy. Ghi audit event và xác nhận các bản sao staging đã được xử lý.

## 17. Cấu trúc evidence package tối thiểu

Một gói bằng chứng dùng cho điều tra thông thường có thể tổ chức như sau:

```text
incident-<id>/
├── README.txt                 # Tóm tắt sự cố và mức redaction
├── manifest.json              # Artifact id, timestamp, version, checksum
├── timeline.csv               # UTC time, attempt id, event, result, duration
├── runtime-versions.txt       # JDK, CRaC, CRIU, kernel, container runtime
├── application-redacted.log   # Bản log đã rà soát
├── jvm-redacted.log           # JVM log đã rà soát
├── criu-redacted.log          # CRIU/runtime log đã rà soát
├── dependency-health.csv      # Status, latency, error class, retry count
├── resource-lifecycle.csv     # beforeCheckpoint/afterRestore outcomes
└── checksums.txt              # Checksum của các file trong package
```

Không có thư mục `checkpoint/`, `heapdump/` hoặc `core/` trong gói thông thường. Nếu raw artifact được thu thập, nó nằm ở kho forensic riêng và manifest chỉ tham chiếu artifact id, checksum cùng quyền truy cập.

Ví dụ `timeline.csv`:

```csv
timestamp_utc,attempt_id,event,resource,result,duration_ms
2026-11-13T09:00:00.120Z,cp-7f2a,readiness,application,REFUSING_TRAFFIC,
2026-11-13T09:00:00.145Z,cp-7f2a,beforeCheckpoint,db-pool,STARTED,
2026-11-13T09:00:00.390Z,cp-7f2a,beforeCheckpoint,db-pool,SUCCESS,245
2026-11-13T09:00:01.900Z,cp-7f2a,checkpoint,process,FAILED,
```

Các định danh và timestamp trong ví dụ là dữ liệu giả. Không đưa customer id, token hoặc endpoint thật vào CSV nếu không cần.

## 18. Xử lý tình huống cần heap dump hoặc core dump

Có những lỗi chỉ có thể xác định bằng phân tích object graph hoặc native memory. Khi đó:

1. Xác định rõ câu hỏi forensic, ví dụ object nào giữ secret, native allocation nào gây crash hoặc thread state nào không thể quan sát từ log.
2. Đánh giá khả năng lấy bằng chứng ít nhạy cảm hơn trước.
3. Chọn đúng process và đúng thời điểm; ghi nhận tác động của việc tạo dump lên latency, disk và process.
4. Đảm bảo dung lượng storage đủ và quyền truy cập hạn chế.
5. Tạo dump theo quy trình của JDK/debugger/platform đang dùng.
6. Mã hóa và hash artifact; ghi collector, timestamp, process identity và tool version.
7. Phân tích trong môi trường cô lập; không mở dump bằng tool hoặc dịch vụ tự động upload dữ liệu ra ngoài.
8. Chỉ trích xuất các object/stack/field cần thiết, redaction trước khi đưa kết quả vào báo cáo.
9. Xóa working copy và artifact tạm theo retention policy.

Heap dump hoặc core dump có thể rất lớn và gây pause, I/O pressure hoặc ảnh hưởng process. Đừng tạo dump đồng loạt trên tất cả instance chỉ vì một instance gặp lỗi. Chọn một instance đại diện hoặc môi trường tái hiện nếu có thể.

## 19. Không làm thay đổi bằng chứng trong lúc điều tra

Các thao tác cleanup hoặc restart có thể phá hủy bằng chứng cần thiết:

- Xóa thư mục checkpoint dở dang trước khi lưu log.
- Restart container làm mất `/proc` state, PID mapping và transient runtime log.
- Rotate log trước khi copy file liên quan.
- Chạy cleanup tự động xóa staging artifact trong lúc điều tra.
- Mở/giải nén checkpoint trên host không tương thích rồi ghi đè hoặc thay đổi nội dung.
- Redact trực tiếp file gốc và mất khả năng so sánh.

Khi cần giữ hiện trạng, hãy snapshot/copy theo cách được nền tảng hỗ trợ, lưu bản gốc read-only và thực hiện phân tích trên bản sao. Không giữ một process lỗi ở trạng thái nguy hiểm chỉ để bảo toàn bằng chứng; ưu tiên an toàn và tính liên tục dịch vụ theo incident procedure, đồng thời ghi lại thao tác đã thực hiện.

## 20. Retention và xóa an toàn

Raw checkpoint, heap dump và core dump không nên được giữ vô thời hạn. Chúng có thể tiếp tục chứa secret ngay cả sau khi credential đã rotation.

Retention policy nên xác định:

- Loại artifact và mức phân loại.
- Incident/owner chịu trách nhiệm.
- Mục đích và thời hạn điều tra.
- Người được phép đọc hoặc decrypt.
- Legal hold hoặc yêu cầu bảo toàn nếu có.
- Ngày xem xét và ngày xóa.
- Cách xác nhận xóa bản sao, archive, staging và replica.

Xóa object trong object storage có versioning có thể chỉ tạo delete marker; snapshot hoặc replica cũng có thể giữ bản sao. Nếu yêu cầu xóa an toàn, sử dụng cơ chế do storage cung cấp như version deletion, crypto-erasure hoặc key revocation theo policy, và ghi nhận phạm vi thực tế. Không tuyên bố dữ liệu đã biến mất vật lý nếu hệ thống lưu trữ không cung cấp bảo đảm đó.

## 21. Các lỗi thường gặp khi thu thập bằng chứng

| Sai sót | Rủi ro | Cách làm phù hợp |
| --- | --- | --- |
| Đính kèm checkpoint vào ticket | Lộ token, password, session và dữ liệu heap | Chỉ gửi artifact id/checksum; raw image ở forensic store hạn chế. |
| Gửi heap dump qua chat | Người nhận và hệ thống lưu trữ có thể không được phép truy cập dữ liệu | Dùng quy trình forensic và kênh truyền được phê duyệt. |
| In toàn bộ environment/system properties | Secret có thể nằm trong biến hoặc property | Thu thập allowlist field; không dump toàn bộ. |
| Chỉ giữ log đã redaction, bỏ bản gốc | Mất khả năng audit và kiểm tra redaction | Giữ original read-only trong restricted store. |
| Redact trực tiếp file gốc | Phá hủy chain of custody | Redact trên working copy. |
| Chỉ thu thập dòng log cuối cùng | Bỏ lỡ lỗi đầu tiên và chuỗi callback | Thu thập timeline quanh toàn bộ attempt. |
| Dựa vào PID đơn lẻ | Nhầm process do namespace hoặc PID reuse | Kết hợp container identity, namespace và process start time. |
| Hash nhưng không ghi nguồn gốc | Không biết checksum thuộc artifact/attempt nào | Gắn hash với manifest, timestamp và artifact id. |
| Dùng log message chứa exception đầy đủ không lọc | Message có thể chứa URL, SQL hoặc payload | Ghi exception class/error code; lưu detail riêng nếu cần. |
| Giữ raw dump vô thời hạn | Secret vẫn tồn tại sau khi incident kết thúc | Retention, access review và deletion procedure. |

## 22. Checklist trước khi chia sẻ evidence package

- [ ] Mỗi file có mục đích điều tra cụ thể.
- [ ] Có incident id, checkpoint/restore attempt id và timestamp UTC.
- [ ] Đã thu thập version/build/platform metadata cần thiết.
- [ ] Đã có timeline callback và dependency state.
- [ ] JVM/CRIU/runtime log đã được rà soát.
- [ ] Không có password, token, private key, cookie hoặc connection string chứa secret.
- [ ] Không có request/response body, SQL bind value hoặc broker payload không cần thiết.
- [ ] Không có raw checkpoint, heap dump hoặc core dump trong package thông thường.
- [ ] Thread dump/JFR/packet capture đã được phân loại và redaction nếu dùng.
- [ ] PID, path, hostname, IP và tenant identifier đã được xử lý theo policy.
- [ ] Bản gốc được giữ read-only trong restricted store.
- [ ] Bản chia sẻ được tạo từ working copy và có ghi nhận redaction.
- [ ] Checksum/manifest liên kết đúng artifact và attempt.
- [ ] Archive evidence được mã hóa và chỉ người nhận cần thiết có quyền.
- [ ] Retention/deletion date và owner đã được ghi nhận.
- [ ] Đã kiểm tra archive để bảo đảm không có file tạm hoặc dump ngoài ý muốn.

## 23. Kết luận

Checkpoint CRaC có thể chứa dữ liệu nhạy cảm trong memory; heap dump và core dump cũng có mức rủi ro tương tự. Điều tra sự cố nên bắt đầu bằng timeline, callback log, runtime version, error code, dependency health, metric và checksum. Những bằng chứng này thường đủ để xác định lỗi thuộc bước prepare, dump, restore hay reconnect mà không phải trích xuất nội dung bộ nhớ.

Chỉ thu thập raw checkpoint hoặc memory dump khi có câu hỏi forensic cụ thể và quy trình được phê duyệt. Giữ bản gốc read-only trong kho hạn chế, tạo bản chia sẻ đã redaction, mã hóa dữ liệu, ghi checksum/manifest và chain of custody, rồi áp dụng retention/xóa theo policy. Không đưa checkpoint, heap dump, core dump, environment dump hoặc system properties thô vào ticket/chat thông thường. Cách thu thập theo allowlist và tối thiểu hóa dữ liệu giúp nhóm kỹ thuật có đủ bằng chứng mà không làm lộ secret hoặc dữ liệu người dùng.
