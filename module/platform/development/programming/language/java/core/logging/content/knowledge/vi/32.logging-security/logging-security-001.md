# Threat model của logging trong Java

## 1. Threat model của logging là gì?

**Threat model** của logging là mô hình xác định **tài sản cần bảo vệ**, **dữ liệu và luồng đi của log**, **ranh giới tin cậy**, **đối thủ**, **kịch bản tấn công**, **kiểm soát phòng vệ** và **cách kiểm thử**. Logging vừa là công cụ phát hiện sự cố bảo mật, vừa là bề mặt tấn công: nó có thể làm lộ token, lưu thông tin sai, bị xóa/sửa để che dấu vết, hoặc trở thành nguyên nhân làm ứng dụng không sẵn sàng.

Hai câu hỏi phải được trả lời song song:

1. **Logging giúp phòng vệ thế nào?** Các sự kiện đăng nhập thất bại, vi phạm phân quyền, thay đổi quyền quản trị, truy cập dữ liệu nhạy cảm, bất thường và thay đổi cấu hình có được ghi đủ để điều tra không?
2. **Bản thân hệ thống log có thể bị tấn công ra sao?** Client có thể giả mạo dòng log qua đầu vào, appender có ghi bí mật, người xem có quyền quá rộng, collector có nhận diện sai nguồn, hay queue có thể bị làm nghẽn không?

Ví dụ: một API ghi thẳng header `User-Agent` do client điều khiển vào file text. Kẻ tấn công chèn ký tự xuống dòng rồi chuỗi giống như một bản ghi `ERROR`, khiến người điều tra hiểu sai timeline. Ở tình huống khác, log lỗi HTTP ghi nguyên `Authorization`, làm một token hợp lệ xuất hiện trong kho quan sát mà hàng chục người có quyền đọc.

**Đừng coi “có log” là “có bằng chứng đáng tin”.** Giá trị điều tra còn phụ thuộc nguồn dữ liệu, cách xác thực danh tính, thời gian, tính đầy đủ, toàn vẹn và quyền kiểm soát dữ liệu sau khi ghi.

## 2. Tài sản và mục tiêu an toàn

| Tài sản | Thuộc tính bảo vệ | Hậu quả khi bị xâm phạm |
| --- | --- | --- |
| Dữ liệu trong log | **Confidentiality** — bí mật | Lộ PII, token, mật khẩu, dữ liệu thanh toán, đường dẫn nội bộ |
| Từng sự kiện ghi log | **Integrity** — toàn vẹn | Dòng log giả, thay đổi outcome hoặc actor |
| Security/audit event | **Completeness / Accountability** | Thiếu sự kiện quan trọng, không xác định được hành động đã xảy ra |
| Dòng thời gian | Thời điểm và nguồn rõ ràng | Kết luận sai thứ tự và nguyên nhân của sự cố |
| Pipeline logging | **Availability** | Log bị drop; disk đầy; request bị block |
| Cấu hình logging | Chỉ người có quyền được sửa | Tắt log bảo mật hoặc chuyển dữ liệu sang đích trái phép |
| Log store và export | Phân quyền, retention | Đọc/tải hàng loạt dữ liệu, xóa lịch sử hoặc phát tán bản sao |

**Phân biệt ba loại nhật ký:**

- **Application/diagnostic log:** vận hành/debug, thường chấp nhận mức độ thiếu chi tiết nhất định khi quá tải theo chính sách.
- **Security event log:** ghi dấu hiệu xác thực, phân quyền, thao tác nhạy cảm, lỗi và hành vi đáng ngờ để giám sát.
- **Audit trail:** nếu phải làm bằng chứng hoặc đối soát, có thể yêu cầu lưu bền vững, tách quyền, tính toàn vẹn và thời gian lưu nghiêm ngặt hơn.

Đặt tên file `audit.log` **không** tự khiến file thành kho audit chống sửa đổi. Nếu yêu cầu có tính pháp lý/nghiệp vụ, cần thiết kế chính sách ghi và lưu riêng.

## 3. Tác nhân đe dọa và khả năng điều khiển

Trước khi đánh giá rủi ro, mô tả điều kẻ tấn công *thực sự có quyền làm*:

| Tác nhân | Có thể điều khiển | Không được mặc định tin |
| --- | --- | --- |
| Client chưa xác thực | URL/path, query, body, header, tốc độ gửi request | `X-User-ID`, `X-Forwarded-For`, `traceparent` do client khai |
| User đã đăng nhập có ác ý | Nội dung nghiệp vụ, thao tác lặp, một số tên/nhãn hiển thị | `toString()`, tên file, chuỗi lỗi được người dùng đưa vào |
| Dịch vụ phụ thuộc bị xâm nhập | Response/error message, metadata, event gửi về | Lỗi HTTP hay exception chứa chuỗi ngoài |
| Tài khoản dịch vụ bị lộ | Gửi dữ liệu bằng danh tính của dịch vụ theo phạm vi quyền | Tenant, index và source name nằm trong payload |
| Người vận hành có quyền quá rộng | Đổi level, sink, retention, export hoặc xóa log | Tính độc lập của audit trail nếu không tách quyền |
| Thành phần thu thập hoặc plugin lỗi | Parser, enrichment, vận chuyển, index và hiển thị | Dữ liệu sau khi rời process ứng dụng |

Cũng cần threat model cho **lỗi vô ý**: cấu hình sai, clock drift, crash, network partition, queue đầy, hết disk, script dọn log sai hoặc vô tình export bản ghi nhạy cảm. Hậu quả về bí mật/toàn vẹn/khả dụng có thể giống một tấn công chủ động.

## 4. Sơ đồ luồng log và ranh giới tin cậy

```text
    [Internet / Client]           [Dependency / SDK]
         │  untrusted data               │
         ▼                               ▼
   [HTTP Server/Gateway] ──────► [Ứng dụng Java]
         │                              │
         │ access event                 │ application/security event
         │                              ▼
         │                      [Logger + MDC/trace]
         │                              │
         │                      [Filter + Encoder]
         │                              │
         └────────────┐                 ▼
                      └────────► [Async Queue/Appender]
                                            │
                                            ▼
                                     [stdout/File/Socket]
                                            │
                                            ▼
                                   [Collector / Agent]
                                            │
                                  TLS/Auth/Validation
                                            ▼
                                    [Central Log Store]
                                            │
                               ┌────────────┴────────────┐
                               ▼                         ▼
                         [Search/Dashboard]       [Export/Backup]
                               │                         │
                            Operators             Other systems
```

Xem kỹ các ranh giới:

1. **Internet → Server:** request ID, IP, URL, user-agent và header có thể không đáng tin; proxy đáng tin cũng phải được cấu hình rõ.
2. **Dữ liệu ứng dụng → Log event:** body, exception, MDC, object `toString()` và thông điệp từ dependency có thể chứa secret, PII hoặc chuỗi phá định dạng.
3. **Logger → Queue/Appender:** level/filter có thể làm mất event; hàng đợi ở RAM, backpressure, retry và shutdown ảnh hưởng bảo toàn dữ liệu.
4. **Process → Collector:** quyền đọc file/stdout, network transport, định danh nguồn gửi, chuyển giao và bộ đệm thuộc vùng tin cậy khác.
5. **Collector → Store:** parser, enrichment, relabel, multi-tenant routing và indexing có thể sửa, bỏ hoặc sao chép event.
6. **Store → Dashboard/Export:** search API, trình hiển thị, CSV, notebook và backup làm mở rộng bề mặt lộ lọt.
7. **Control plane → Logging config:** mọi quyền đổi level, filter, masking, destination và retention cũng là quyền thay đổi bằng chứng.

Với từng ranh giới ghi nhận: **ai kiểm soát dữ liệu**, giao thức và định dạng, cơ chế xác thực, nơi dữ liệu lưu tạm, quyền đọc/ghi và cách phát hiện lỗi.

## 5. STRIDE cho hệ thống logging

STRIDE là khung phân loại đe dọa; nó không phải danh sách cấu hình sẵn của Logback hay Log4j2.

| Nhóm | Kịch bản trong logging | Hậu quả | Biện pháp và kiểm chứng |
| --- | --- | --- | --- |
| **Spoofing** — giả mạo | Client đặt `X-User-ID: admin` hoặc giả IP rồi ứng dụng ghi thành actor đã xác thực | Quy kết sai hành động | Lấy actor từ security principal đã xác minh; chỉ tin proxy được cấu hình; thử header giả |
| **Tampering** — sửa đổi | CRLF tạo dòng giả, người vận hành sửa file, collector thay trường | Bằng chứng bị bóp méo | Structured encoding, sanitize, RBAC, append-only/tamper detection |
| **Repudiation** — chối bỏ | Thay đổi vai trò không được ghi hoặc audit bị xóa dễ dàng | Không thể đối soát hành động | Event schema, đối soát, tách quyền, retention và kho bền vững |
| **Information Disclosure** — lộ lọt | Log request header, JWT, PII, stack trace rồi export công khai | Chiếm quyền, vi phạm quyền riêng tư | Field allowlist, không log secret tại nguồn, mã hóa và quyền tối thiểu |
| **Denial of Service** — từ chối dịch vụ | Spam lỗi làm queue/disk đầy, format exception quá nặng | Request chậm, mất log, dịch vụ dừng | Bounded queue, rate/size limit, quota, metrics và chính sách overload |
| **Elevation of Privilege** — leo thang quyền | Viewer/parser có lỗ hổng, quyền quản trị logging quá rộng | Chiếm quyền hoặc vô hiệu hóa kiểm soát | Vá dependency, cô lập parser, phân tách quyền config/read/delete |

**Lưu ý:** một kịch bản có thể thuộc nhiều nhóm. Ví dụ log forging vừa làm sai tính toàn vẹn vừa hỗ trợ chối bỏ. Không gán mức nguy hiểm cao nhất cho tất cả tình huống; ưu tiên dựa trên phạm vi dữ liệu, quyền của attacker, khả năng khai thác và hậu quả thực tế.

## 6. Log injection và log forging (CWE-117)

### Kịch bản

Đoạn mã không an toàn trong ứng dụng có backend logging:

```java
// MINH HỌA KHÔNG AN TOÀN: không dùng kiểu này cho dữ liệu không tin cậy.
logger.warn("Login failed: user=" + username);
```

Giả sử client đưa giá trị `username` gồm:

```text
guest
ERROR user=admin event=login_success
```

Nếu ứng dụng ghi nguyên giá trị vào log văn bản theo từng dòng, một sự kiện thật có thể trông giống hai sự kiện. Dòng thứ hai do attacker đặt, không phải do ứng dụng xác nhận. Đây là ví dụ của **Improper Output Neutralization for Logs (CWE-117)**.

Các biến thể còn gồm dấu phân cách trong `key=value`, JSON tự ghép không escape, ký tự điều khiển terminal, Unicode line separators hoặc payload dài làm parser/collector quá tải.

### Phòng vệ theo thứ tự ưu tiên

1. **Định nghĩa schema cố định:** `event.name`, `actor.id`, `outcome`, `http.route` là trường có ý nghĩa; event name và route template do server quyết định.
2. **Validate kiểu/độ dài/giá trị:** request ID đúng format, action và reason thuộc tập mã hợp lệ; không dùng raw input làm tên logger, level, tên file hay index.
3. **Dùng structured logging** qua encoder đúng chuẩn: ví dụ JSON có escaping của từng giá trị, không tự ghép chuỗi JSON.
4. **Neutralize CR/LF và ký tự điều khiển** với log văn bản; xử lý thêm ký tự đặc biệt đúng định dạng đích và đặt event-size limit.
5. **Dùng message template tĩnh, parameterized logging**, chẳng hạn `logger.warn("Login failed for {}", safeUser)`. Nhưng **placeholder không tự chống CRLF** nếu layout vẫn in nguyên chuỗi.
6. **Bảo vệ pipeline sau đó:** parser, dashboard HTML, CSV export và query cũng phải escape theo ngữ cảnh của chúng.

Một JSON event hợp lệ không tự bảo đảm an toàn nếu dashboard đưa giá trị vào HTML không escape. Ngược lại, chỉ thay `\n` bằng chuỗi hai ký tự backslash-n không giải quyết bí mật, dấu phân cách hoặc dữ liệu vượt kích thước tối đa.

## 7. Tránh lộ token, PII và secret

**Nguồn rủi ro phổ biến:**

- `Authorization`, `Cookie`, `Set-Cookie`, session ID, access token, refresh token, API key.
- Query parameter chứa `code`, `token`, `password` hoặc định danh nhạy cảm.
- Request/response body cho login, thanh toán, y tế, hồ sơ cá nhân.
- `toString()` của DTO, record hoặc exception có trường bí mật.
- Database connection string, URL có credential, environment variables, nội dung secret manager.
- Stack trace và lỗi từ SDK/HTTP client chứa header, payload hoặc đường dẫn nội bộ.
- MDC, tracing baggage hoặc context được tự động đính vào mọi sự kiện.

Ví dụ không nên làm:

```java
// MINH HỌA KHÔNG AN TOÀN.
logger.error("Request headers={} body={}", requestHeaders, requestBody);
```

Nên phát một **security event theo allowlist** các trường cần cho điều tra, ví dụ:

```text
event=authentication_failed
route=/login
request_id=req_42
outcome=DENY
reason=BAD_CREDENTIALS
duration_ms=23
```

Không cần tên đầy đủ, password hay token để biết một yêu cầu đăng nhập đã thất bại. Nếu phải lưu actor ID hoặc IP, cần mục đích xử lý hợp lệ, kiểm soát quyền, retention và tránh suy diễn actor từ header client.

**Đặt phòng vệ sớm:** bỏ trường nhạy cảm trước khi tạo event tốt hơn sửa sau khi event đã đi qua stdout/file. Collector scrubber và masking ở dashboard chỉ là lớp bổ sung. Regex che token có thể bỏ sót format mới, nested JSON hoặc giá trị bị chia nhỏ. Hash ID không tự loại bỏ rủi ro nhận dạng lại, đặc biệt nếu tập giá trị nhỏ dễ dò ngược.

## 8. Ví dụ Java 17: log theo allowlist và neutralize xuống dòng

Ví dụ độc lập sau sử dụng **`java.util.logging` (JUL)** sẵn trong JDK. Mục tiêu là minh họa ba biện pháp:

- Event type, route và reason code có ý nghĩa do **ứng dụng** quyết định.
- Request ID chỉ được nhận nếu đúng allowlist định dạng.
- Một đầu vào không tin cậy phải được escape/giới hạn nếu thật sự cần hiển thị trong một dòng text.

**Đây là ví dụ giáo dục**, không phải một thư viện logging bảo mật production. Hàm escape chỉ xử lý ký tự điều khiển của **dòng text**; không thay thế JSON/CSV/HTML escaping, không phát hiện token/PII và không bảo đảm tính bền vững.

Lưu thành tệp **`LoggingThreatModelDemo.java`**:

```java
import java.util.Set;
import java.util.regex.Pattern;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LoggingThreatModelDemo {
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Set<String> REASONS =
            Set.of("BAD_CREDENTIALS", "ACCOUNT_LOCKED");
    private static final Logger LOG =
            Logger.getLogger("security.events");

    private static final class StdoutHandler extends Handler {
        StdoutHandler() {
            setLevel(Level.ALL);
        }

        @Override
        public void publish(LogRecord event) {
            if (isLoggable(event)) {
                System.out.println(event.getLevel().getName()
                        + " " + event.getMessage());
            }
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }

    private static String checkedId(String raw) {
        return raw != null && SAFE_ID.matcher(raw).matches()
                ? raw : "invalid";
    }

    private static String checkedReason(String raw) {
        return raw != null && REASONS.contains(raw)
                ? raw : "UNTRUSTED";
    }

    private static String escapeLine(String raw, int maxChars) {
        if (raw == null) {
            return "-";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < raw.length();) {
            int cp = raw.codePointAt(i);
            i += Character.charCount(cp);

            String safe;
            if (cp == '\r') {
                safe = "\\r";
            } else if (cp == '\n') {
                safe = "\\n";
            } else if (cp == '\t') {
                safe = "\\t";
            } else if (Character.isISOControl(cp)
                    || cp == 0x2028 || cp == 0x2029
                    || (cp >= 0xD800 && cp <= 0xDFFF)) {
                safe = "?";
            } else {
                safe = new String(Character.toChars(cp));
            }

            if (out.length() + safe.length() > maxChars) {
                break;
            }
            out.append(safe);
        }
        return out.toString();
    }

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        StdoutHandler handler = new StdoutHandler();
        LOG.addHandler(handler);

        try {
            String requestId = checkedId("req_42");
            String reason = checkedReason("BAD_CREDENTIALS");

            LOG.warning("event=authentication_failed"
                    + " route=/login"
                    + " request_id=" + requestId
                    + " reason=" + reason);

            LOG.info("event=http_response"
                    + " route=/login status=401"
                    + " request_id=" + requestId);

            String untrusted = "guest\nERROR event=login_success";
            System.out.println("escaped_input="
                    + escapeLine(untrusted, 80));
            System.out.println("invalid_request_id="
                    + checkedId("bad\nid"));
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }
    }
}
```

Biên dịch/chạy bằng JDK 17+:

```bash
javac --release 17 LoggingThreatModelDemo.java
java LoggingThreatModelDemo
```

**Stdout chính xác:**

```text
WARNING event=authentication_failed route=/login request_id=req_42 reason=BAD_CREDENTIALS
INFO event=http_response route=/login status=401 request_id=req_42
escaped_input=guest\nERROR event=login_success
invalid_request_id=invalid
```

Giải thích:

- Hai event thật được tạo bằng `LOG.warning` và `LOG.info`, với trường loại sự kiện, route và reason do ứng dụng kiểm soát.
- `checkedId` từ chối request ID chứa ký tự xuống dòng, tránh đưa trực tiếp chuỗi header chưa kiểm tra thành ID tương quan.
- `escapeLine` duyệt Unicode code point, thay CR/LF bằng chuỗi biểu diễn an toàn, xử lý ký tự điều khiển và áp giới hạn độ dài. Trong stdout, `\n` tại `escaped_input` là **hai ký tự literal** backslash và n, không phải dấu xuống dòng thực.
- Mẫu xử lý handler chạy tuần tự và tắt parent handlers, vì vậy không phát sinh dòng timestamp hoặc bản ghi trùng từ handler mặc định của JUL.
- `escapeLine` chỉ minh họa neutralization; với chuỗi `key=value` còn phải xét delimiter như dấu cách/`=` và encoding theo parser. Tốt nhất là dùng encoder JSON có cấu trúc thay vì tự dựng cả record bằng cách nối chuỗi.
- Khi input chứa bí mật hoặc PII thì **không log**, dù đã escape CR/LF. Dữ liệu được escape vẫn có thể là dữ liệu nhạy cảm.
- Không dùng chương trình này thay các framework production: nó không xử lý queue, file rotation, lưu bền vững, TLS, multi-tenant access control hay sự kiện audit có bảo đảm.

## 9. Tính toàn vẹn, provenance và audit trail

Tính toàn vẹn có các cấp độ khác nhau:

1. **Nội dung event đúng:** outcome đến từ logic đã kiểm chứng; actor đến từ security principal, không phải user ID trong request.
2. **Dòng log không bị giả ngay khi ghi:** schema, encoding và neutralization ngăn một đầu vào tạo dòng giả.
3. **Không bị sửa/xóa sau khi ghi:** quyền filesystem/index, phân tách quản trị, bản lưu append-only hoặc cơ chế phát hiện thay đổi.
4. **Không bị sửa khi truyền:** bảo vệ kênh và xác thực nguồn, đặc biệt collector multi-tenant.
5. **Phát hiện được sự kiện thiếu:** có event ID/sequence, ingestion metric, heartbeat và cơ chế đối soát.

Một số lựa chọn khi audit yêu cầu độ tin cậy cao:

- Lưu bản sao sang hệ thống **khác miền quyền** để một operator ứng dụng không thể sửa toàn bộ bằng chứng.
- Sử dụng **immutable/WORM retention** hoặc append-only storage khi phù hợp và thiết lập quyền quản trị riêng.
- Dùng hash chain/MAC/chữ ký trên event hoặc batch với canonical serialization và quản lý khóa độc lập. Một checksum đơn lẻ có thể được tính lại bởi người có quyền ghi nên không đủ chống giả mạo.
- Đánh số sự kiện theo nguồn/partition và kiểm tra gap, duplicate, clock drift. Multi-service không có thứ tự toàn cục chỉ bằng timestamp.
- Với sự kiện nghiệp vụ quan trọng, cân nhắc **transactional outbox/event store** để liên hệ dữ liệu giao dịch và dấu vết audit, thay vì tin queue logging in-memory.

**Giới hạn quan trọng:** TLS hay chữ ký trên event không thể chứng minh actor thật nếu ứng dụng đã lấy actor từ header giả. Chữ ký chỉ xác nhận bản dữ liệu đã được ký. Tính quy trách nhiệm cần chuỗi tin cậy: authentication, nghiệp vụ, nguồn log, vận chuyển, lưu và quyền xem/xóa.

## 10. Đảm bảo availability: logging không được trở thành đường DoS

Một attacker có thể gửi request dồn dập để kích hoạt log WARN/ERROR, stack trace dài hoặc event chứa payload lớn. Bản thân hệ thống log có thể làm dịch vụ mất khả dụng:

- **CPU** bận dựng message, serialize JSON, format exception.
- **Heap** chứa queue lớn, event và MDC snapshots; GC tăng.
- **Disk** đầy do file log và rotation không đủ giới hạn.
- **Request thread** chặn vì synchronous appender hoặc async queue đầy.
- **Collector/backend** quá tải, retry mãi hoặc bị tính chi phí ingest cao.
- **Dashboard** chậm do field cardinality quá lớn.

Mô hình đơn giản: `λ` là tốc độ tạo log events/giây và `μ` là tốc độ xử lý của consumer. Nếu `λ > μ` kéo dài, backlog tăng tới giới hạn. **Tăng queue size chỉ trì hoãn việc queue đầy; không làm sink xử lý nhanh hơn.**

| Biện pháp | Điều kiểm soát | Đánh đổi |
| --- | --- | --- |
| Bounded queue | Giới hạn dùng heap | Queue đầy phải block/drop/fallback theo chính sách |
| Giới hạn kích thước event | Tránh payload lớn | Có thể cắt dữ liệu; cần nhãn truncated |
| Rate limit hoặc tổng hợp | Giảm log lặp | Không được che sự kiện security quan trọng |
| Sampling có kiểm soát | Giảm lượng log vận hành | Không phù hợp nếu ngẫu nhiên loại audit event bắt buộc |
| Disk quota/volume riêng | Cô lập ứng dụng khỏi log disk full | Phải giám sát và định nghĩa hành vi khi đầy |
| Async appender | Giảm một phần I/O trên request | Không mặc định bảo toàn event khi crash |
| Collector buffering | Hấp thụ network hiccup | Buffer có hạn và có nguy cơ mất/trùng |

**Fail-open vs fail-closed:** nếu sink hỏng, logging thường không nên phá tính khả dụng của toàn hệ thống chỉ vì DEBUG mất. Nhưng với audit bắt buộc, tiếp tục một giao dịch mà không ghi được dấu vết có thể vi phạm yêu cầu. Đây là **quyết định chính sách theo nghiệp vụ**, cần cơ chế bền vững và đối soát; không đặt mặc định cho mọi loại log.

## 11. Pipeline transport, collector và storage cũng cần threat model

### Trên đường truyền

- Khi truyền qua mạng không tin cậy, sử dụng TLS, cân nhắc mTLS/service identity theo nhu cầu.
- Định danh service/tenant nguồn phải được ràng buộc với **danh tính xác thực của kênh**, không chỉ giá trị `service.name` trong payload.
- Collector cần validate schema, kích thước, số trường, timeout và mức quyền gửi vào index/tenant cụ thể.
- Theo dõi `retry`, `drop`, `ingest errors` và `lag`; HTTP 200 từ collector có thể chỉ là “đã chấp nhận”, không chắc dữ liệu đã tìm kiếm được.
- Không cho dữ liệu client quyết định URL sink, tên file hay đường dẫn lưu trên server.

### Ở kho và quyền xem

- Tách quyền **ingest**, **read/search**, **export**, **config** và **delete/retention**. Một tài khoản chỉ xem dashboard không nên đồng thời có quyền xóa index.
- Mã hóa at rest/in transit là cần thiết khi yêu cầu, nhưng **không thay thế IAM/RBAC**.
- Ghi nhận thao tác export/download và truy vấn nhạy cảm; có thể yêu cầu phê duyệt khi xuất lượng lớn.
- Kiểm tra bucket, index, snapshot, backup, file đính kèm và bản sao môi trường test, không chỉ kho production.
- Đảm bảo retention áp dụng cho những bản sao phù hợp và tuân thủ nghĩa vụ pháp lý, dữ liệu cá nhân.
- Không để thư mục log dưới web root công khai hoặc dùng signed link không giới hạn thời hạn.

### Bề mặt tấn công ở trình xem/export

Một event dạng JSON có thể an toàn lúc ghi nhưng nguy hiểm nếu dashboard render field bằng HTML không escape. CSV export có thể chứa chuỗi bắt đầu bằng `=`, `+`, `-` hoặc `@` và bị công cụ bảng tính diễn giải thành công thức nếu không được xử lý an toàn. Log content phải được coi là **dữ liệu không tin cậy** ở mọi lần hiển thị/biến đổi.

## 12. Cấu hình logging cũng là đối tượng cần bảo vệ

Người có quyền thay logger/appender có thể:

- Giảm level hoặc tắt logger ghi security event.
- Bật DEBUG/TRACE để khiến log chứa thêm PII/secret.
- Chuyển appender sang file/socket hoặc endpoint do mình kiểm soát.
- Xóa/giảm retention và tắt collector/agent.
- Vô hiệu hóa masking, thay schema hoặc bộ lọc dẫn đến thất lạc chứng cứ.

Các kiểm soát nên có:

1. **Least privilege:** quyền đổi cấu hình tách khỏi đọc và xóa nếu mức độ rủi ro yêu cầu.
2. **Change management và audit:** ai đổi, thời điểm, trước/sau, mục đích; giám sát thay đổi bất thường.
3. **Không phụ thuộc hoàn toàn vào root logger level** cho những security event bắt buộc.
4. **Bật DEBUG có thời hạn**, giới hạn package và có cơ chế hoàn nguyên.
5. **Bảo vệ endpoint quản trị** như `/actuator/loggers` nếu ứng dụng có dùng; xác thực/phân quyền và không phơi ra Internet.
6. **Kiểm thử reload nhiều instance:** thay cấu hình trên một pod không mặc định áp dụng mọi pod; kiểm tra config version/effective level.

Cấu hình an toàn phải phân biệt “ghi ít đi để giảm overhead” với “làm mù hệ thống phát hiện sự cố”. Không bỏ log phân quyền hoặc thay đổi đặc quyền chỉ vì muốn giảm số dòng INFO.

## 13. Schema cho security event đáng tin hơn

Ví dụ một event JSON minh họa, tên trường do nhóm vận hành quy ước:

```json
{
  "timestamp": "2026-11-10T02:30:00.100Z",
  "service.name": "identity-api",
  "event.name": "authorization_denied",
  "event.id": "evt_501",
  "actor.id": "acct_17",
  "actor.authenticated": true,
  "action": "READ_PROFILE",
  "resource.type": "user_profile",
  "outcome": "DENY",
  "reason.code": "INSUFFICIENT_SCOPE",
  "http.route": "/profiles/{id}",
  "http.response.status_code": 403,
  "request_id": "req_42",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "schema.version": 1
}
```

Cần xác định quy tắc cho từng trường:

- `timestamp` là event time ở nguồn, có timezone UTC; có thể kèm ingestion time để nhận biết delay.
- `event.name` và `reason.code` thuộc allowlist, không được nhận nguyên từ request.
- `actor.id` lấy từ security context đã xác thực; nếu anonymous phải ghi rõ thay vì đoán từ header.
- `http.route` nên là route template do server biết, không phải raw URL có query/token.
- `request_id`, `trace_id` phải được validate và truyền đúng; **không phải bằng chứng actor đã được xác thực**.
- `outcome` phản ánh kết quả nghiệp vụ thật, không suy bằng cách nhìn có exception hay chỉ HTTP status.
- `event.id` giúp đối chiếu duplicate/gap, nhưng ID tự sinh không tự mang bảo đảm chống sửa/xóa.
- `schema.version` giúp biết collector đang parse đúng kiểu sự kiện.

Cần ghi rõ retention và ai được xem `actor.id`; đôi khi pseudonymized ID là đủ. Một event audit muốn quy kết trách nhiệm phải gắn với cơ chế xác thực và nơi lưu đáng tin, không chỉ có các trường JSON đẹp.

## 14. MDC, trace context và logging bất đồng bộ

### Context spoofing

Nếu request có `X-Request-ID: req_admin` và ứng dụng chép thẳng vào MDC, attacker có thể tạo ID trùng hoặc gây nhiễu điều tra. Nên xác định **nguồn canonical request ID**, validate độ dài/ký tự và chính sách khi header không hợp lệ. Với W3C trace context, phải dùng parser/instrumentation có kiểm tra và không tự tin mọi metadata từ client.

### Context leakage giữa các request

Thread pool của Java tái sử dụng thread. Nếu `MDC.put("tenant_id", ...)` không có scope cleanup, request sau có thể mang tenant ID của request trước. Điều này vừa làm sai bằng chứng, vừa có khả năng tiết lộ dữ liệu giữa tenant.

```java
// Trích đoạn minh họa với SLF4J MDC, không phải chương trình độc lập.
// Khi có context do tầng ngoài thiết lập, phải save/restore đúng scope.
org.slf4j.MDC.put("request_id", validatedRequestId);
try {
    processRequest();
} finally {
    org.slf4j.MDC.remove("request_id");
}
```

Trích đoạn trên cần dependency SLF4J, method `processRequest` và biến `validatedRequestId` của ứng dụng. Nó chỉ minh họa cleanup; nếu có giá trị MDC cũ từ scope cha, xóa thẳng có thể làm mất context hợp lệ, cần restore theo cơ chế tương ứng.

### Async queue và snapshot

Consumer chạy ở luồng khác producer. Event phải chụp thông tin cần thiết (trace ID, span ID, timestamp, actor context phù hợp) trước khi enqueue. Không để consumer đọc MDC hiện tại của chính thread worker rồi áp cho event cũ; có thể rỗng hoặc sai.

Tránh đưa secret/PII vào tracing baggage rồi tự động xuất hiện trong mọi log. Đừng dùng `trace_id` hoặc `request_id` làm nhãn metric cardinality thấp; giá trị quá đa dạng có thể làm hệ thống quan sát quá tải.

## 15. Dependency, formatter và dynamic processing

Logging framework và plugin là phần mềm phải được cập nhật như các dependency khác:

- Kiểm kê runtime logging backend thực tế (Logback, Log4j2, JUL bridge) và các transitive dependencies.
- Kiểm tra advisory/vulnerability theo đúng phiên bản triển khai; không khẳng định chỉ cần dùng SLF4J là tránh được lỗ hổng ở backend.
- Tránh tính năng lookup/evaluation không cần thiết trên chuỗi untrusted và cấu hình appender động dựa vào input.
- Hạn chế custom formatter/parser nhận event không giới hạn hoặc tự giải mã nhiều lần.
- Xác minh đường I/O của appender không thể bị điều khiển thành endpoint hoặc file path do client chọn.
- Kiểm tra log viewer/search/export đối với injection và permission boundary.

**Log4Shell (CVE-2021-44228)** là ví dụ lịch sử về hậu quả khi xử lý dữ liệu không tin cậy trong thành phần logging với phiên bản/cấu hình dễ bị khai thác. Điều này **không** có nghĩa mọi phiên bản Log4j2 hay mọi lời gọi placeholder đều có lỗ hổng đó. Phải dựa vào phiên bản và bản vá thực tế.

## 16. Xếp hạng rủi ro và kế hoạch giảm thiểu

Với mỗi threat, ghi dạng **nguồn → attack path → trust boundary → hậu quả → kiểm soát → kiểm thử → residual risk**. Ví dụ:

| Mã | Tình huống | Kiểm soát chính | Bằng chứng mong muốn |
| --- | --- | --- | --- |
| T1 | Header CRLF tạo thêm dòng giả | Schema JSON + neutralize + max length | Một request chỉ tạo event hợp lệ, không có dòng giả |
| T2 | JWT bị ghi khi SDK ném exception | Field allowlist + canary scan | Token giả không xuất hiện ở file, index, export |
| T3 | Admin xóa audit | Tách quyền và immutable copy | Quyền xóa bị từ chối hoặc thay đổi bị phát hiện |
| T4 | Brute force lấp disk log | Quota, bounded queue, rate bound | Burst test không làm cạn disk ứng dụng |
| T5 | MDC tenant A rò sang request B | Cleanup/restore và snapshot | Chạy đồng thời không lẫn actor/tenant |
| T6 | Collector mất kết nối | Delivery lag/drop metric, alert, buffer có hạn | Tự phát cảnh báo và thực thi policy đã chọn |
| T7 | Runtime logger bị tắt | Admin RBAC, cấu hình được audit | 401/403 với người không có quyền; thay đổi hợp lệ có trail |
| T8 | CSV export kích hoạt công thức | Safe export theo ngữ cảnh | Chuỗi do client tạo không trở thành formula |

T2 có thể rất nghiêm trọng nếu token vẫn dùng được và log được nhiều người xem; T4 nghiêm trọng nếu file log và cơ sở dữ liệu dùng chung disk. Hãy xếp hạng theo **khả năng khai thác × mức ảnh hưởng**, không mặc định tất cả là critical.

## 17. Kiểm thử bảo mật logging

### Nội dung và injection

1. Gửi CR/LF, tab, control characters, Unicode separators, text chứa dấu `=`, dấu nháy và input dài vào field nhận dữ liệu bên ngoài.
2. Xác minh parser nhận **đúng một event có cấu trúc**, không nhận event giả, không làm hỏng các event sau.
3. Kiểm thử HTML dashboard, CSV export và query interface với cùng payload đã được làm vô hại.
4. Đảm bảo event sai format được báo lỗi hoặc sanitized có kiểm soát, không gán nhầm actor/event type.

### Bí mật, quyền và dữ liệu

1. Dùng **secret giả/canary**, không dùng token thật trong thử nghiệm; tìm canary qua stdout/file/collector/index/dashboard/export.
2. Thử khi exception ở HTTP client, JDBC, SDK hoặc authentication provider; không lộ raw request body/headers.
3. Dùng role chỉ xem, role export, role admin và role audit để xác minh RBAC tách biệt.
4. Kiểm tra retention, snapshot, backup, file staging và khả năng truy cập ngoài ý muốn.
5. Bật DEBUG trong môi trường test rồi xác nhận không có secret vô tình xuất hiện.

### Tính toàn vẹn và xác thực nguồn

1. Giả mạo `X-User-ID`, `X-Forwarded-For`, `X-Request-ID`; actor/địa chỉ nguồn phải tuân theo mô hình trust đã định.
2. Ghi thử authorization denial, role change, privileged action; kiểm tra event, outcome và context đến từ logic thật.
3. Dùng tài khoản thử sửa/xóa audit data và xác nhận bị chặn/phát hiện theo policy.
4. Kiểm tra gap/duplicate, event time/ingestion time và clock drift.
5. Gửi dữ liệu từ service A nhưng khai `service.name=B`; collector không được nâng tin cậy của payload thành danh tính nguồn.

### Khả dụng và lỗi pipeline

1. Phát log burst từ request lỗi để quan sát queue depth, CPU, GC, disk và p99 latency.
2. Làm sink chậm hoặc mất mạng; đếm attempted/enqueued/written/dropped events và kiểm tra cảnh báo.
3. Giả lập disk full, appender permission denied và collector timeout, xác minh policy fail-open/fail-closed được phê duyệt.
4. Kill process khi queue còn backlog để kiểm tra rủi ro mất event; khác với shutdown bình thường có drain.
5. Kiểm tra đa tenant và nhiều pod, tránh log/trace của tenant này bị đọc bởi tenant khác.

**Tiêu chí PASS phải cụ thể:** có ID cho sự kiện thử, expected field/value, phạm vi nguồn đã kiểm tra, quyền truy cập, số event mất và bằng chứng báo động. Chỉ thấy một dòng WARN trên console không đủ chứng minh pipeline an toàn.

## 18. Quan sát pipeline và xử lý sự cố

Các chỉ số sau là **gợi ý instrumentation**, không phải tên metric có sẵn của mọi framework:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `logging_events_attempted` | Volume bất thường, brute force |
| `logging_events_dropped` | Mất event do queue/collector/policy |
| `logging_queue_depth` | Nghẽn hoặc consumer chậm |
| `event_to_ingest_lag` | Trễ dữ liệu được tra cứu |
| `collector_ingest_errors` | Parser, TLS, auth hoặc network lỗi |
| `audit_sequence_gaps` | Dấu hiệu thiếu/thay đổi record nếu có sequence đáng tin |
| `log_config_changes` | Ai đổi level/filter/sink/retention |
| `log_export_bytes` | Export dữ liệu lớn bất thường |
| `tamper_detection_alerts` | Dấu hiệu sửa/xóa hoặc integrity check hỏng |
| `secret_scan_hits` | Dữ liệu nhạy cảm có thể lọt vào log |

Khi phát hiện **token đã lộ trong log**:

1. Dừng phát sinh token ở nguồn (chỉnh schema/encoder/cách log) và bảo vệ access.
2. Thu hồi/rotate secret theo mức độ ảnh hưởng; việc xóa một dòng log không làm token không còn hợp lệ.
3. Xác định đường lan truyền: file, stdout, collector, index, dashboard, export và backup.
4. Kiểm tra ai đã xem/tải dữ liệu, thông báo/ứng cứu theo chính sách tổ chức.
5. Xử lý bản đã lưu theo yêu cầu retention/pháp lý và bổ sung regression test để tránh tái diễn.

Khi **nghi log bị sửa/xóa**, không ghi đè bằng chứng hiện tại. Bảo toàn bản sao có quyền kiểm soát độc lập, đối chiếu với transaction store và log từ gateway/collector, rồi phân tích quyền cấu hình/xóa đã bị sử dụng.

## 19. Checklist threat modeling trong design review

- [ ] Đã vẽ luồng client → Java logger → appender/queue → collector → store → viewer/export.
- [ ] Đã xác định asset, threat actor, khả năng điều khiển và trust boundary.
- [ ] Đã phân loại application, access, security và audit events; không đánh đồng retention.
- [ ] Đã xác định identity nào đến từ security principal và metadata nào chỉ là client-provided.
- [ ] Đã có field allowlist và không ghi raw credential, body/header nhạy cảm mặc định.
- [ ] Đã kiểm thử log injection/forging và output encoding theo text/JSON/HTML/CSV.
- [ ] Đã giới hạn event size, queue và disk; biết chính sách khi sink hỏng.
- [ ] Đã có RBAC cho ingest/read/export/config/delete và phân quyền giữa tenant.
- [ ] Đã bảo vệ đường truyền và provenance của nguồn gửi log.
- [ ] Đã kiểm tra log context không rò giữa thread/request/tenant.
- [ ] Đã xác định nếu audit cần storage bền vững, tamper evidence và đối soát nghiệp vụ.
- [ ] Đã có giám sát dropped events, lag, collector errors và thay đổi cấu hình.
- [ ] Đã kiểm thử secret canary, header giả, parser, dashboard và export.
- [ ] Đã phân công người phản ứng khi log ngừng, bị sửa hoặc lộ dữ liệu.
- [ ] Các residual risks và người chấp nhận rủi ro được ghi lại.

**Ghi nhớ:** một threat model logging đầy đủ bảo vệ **bí mật dữ liệu**, **tính chính xác và toàn vẹn của dấu vết**, cùng **khả năng vận hành của dịch vụ và pipeline**. Log chỉ giúp bảo mật khi sự kiện được tạo từ nguồn đáng tin, không làm lộ thông tin cần bảo vệ, có thể phát hiện mất/sửa và được truy cập đúng người, đúng lúc.

### Tài liệu đối chiếu

- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [MITRE CWE-117 — Improper Output Neutralization for Logs](https://cwe.mitre.org/data/definitions/117.html)
- [OWASP — Log Injection](https://owasp.org/www-community/attacks/Log_Injection)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [Java 17 API — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html)
