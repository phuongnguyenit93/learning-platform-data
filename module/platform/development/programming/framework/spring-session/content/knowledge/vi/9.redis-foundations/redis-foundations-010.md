# Quan sát dữ liệu bằng công cụ Redis mà không làm lộ định danh, thuộc tính

Spring Session lưu session ở Redis để nhiều instance của ứng dụng có thể dùng chung trạng thái. Khi vận hành, đội ngũ cần quan sát số lượng session, TTL, mức sử dụng bộ nhớ, tỷ lệ hết hạn và tình trạng kết nối. Tuy nhiên, key Redis của session có thể chứa hoặc suy ra session ID; giá trị lưu trong session có thể chứa thông tin đăng nhập, principal, quyền truy cập hoặc dữ liệu cá nhân. Một lệnh kiểm tra tưởng như vô hại cũng có thể làm lộ credential nếu in key hoặc value ra terminal, log, ảnh chụp màn hình hay ticket hỗ trợ.

Mục tiêu của quan sát an toàn là lấy đủ dữ liệu để chẩn đoán hệ thống ở mức tổng hợp và metadata tối thiểu, đồng thời giữ nguyên tính bí mật của session ID và session attributes. Bài học này trình bày cách chọn lệnh Redis, cách xử lý kết quả, cách giới hạn quyền truy cập và cách thiết kế công cụ nội bộ phục vụ vận hành Spring Session.

## 1. Hiểu dữ liệu nào cần được bảo vệ

Một session Spring Session thường có nhiều thành phần lưu trữ: định danh phiên, metadata vòng đời, các thuộc tính do ứng dụng lưu, thông tin xác thực của Spring Security và cấu trúc phụ phục vụ TTL, chỉ mục hoặc sự kiện. Tên key và cách tổ chức cụ thể phụ thuộc repository implementation, cấu hình và phiên bản Spring Session.

| Dữ liệu | Ví dụ | Cách xử lý khi quan sát |
|---|---|---|
| Session ID | Chuỗi định danh trong cookie hoặc key | Xem như credential; không in, chia sẻ hoặc ghi log thô |
| Principal/user identifier | Username, email, user ID | Dữ liệu nhạy cảm; chỉ dùng khi có mục đích và quyền rõ ràng |
| Session attributes | SecurityContext, cart, tenant, workflow state | Không đọc hàng loạt; có thể chứa bí mật hoặc dữ liệu cá nhân |
| Key Redis của session | Key có namespace và phần định danh | Có thể làm lộ session ID; không xuất danh sách raw keys |
| TTL/expiration metadata | Số giây còn lại hoặc mốc hết hạn | Có thể quan sát ở dạng số tổng hợp hoặc cho một mẫu được kiểm soát |
| Metrics Redis | Memory, expired keys, evictions, hits/misses | Ưu tiên số liệu tổng hợp không gắn với cá nhân |

Session ID là bearer credential: người có ID hợp lệ có thể được hệ thống nhận diện là chủ phiên. Vì vậy, không coi nó là một mã kỹ thuật vô hại. Ngay cả khi key không chứa ID theo dạng rõ ràng, không nên giả định key hoặc value nội bộ không thể tiết lộ thông tin nhạy cảm.

## 2. Nguyên tắc quan sát an toàn

Trước khi chạy lệnh, xác định câu hỏi vận hành cần trả lời. Nếu câu hỏi là “Redis còn hoạt động không?”, không cần đọc key. Nếu câu hỏi là “namespace session có tăng bất thường không?”, số lượng key và metrics tổng hợp có thể đủ. Nếu cần điều tra một session cụ thể, hãy dùng API nội bộ có xác thực và chỉ trả về metadata đã lọc.

Áp dụng các nguyên tắc sau:

1. **Ưu tiên dữ liệu tổng hợp:** số key, memory, expired keys, evictions, latency và tỷ lệ hit/miss thường đủ cho kiểm tra sức khỏe.
2. **Chỉ đọc metadata cần thiết:** nếu cần TTL, chỉ lấy con số TTL; không đọc value hoặc attributes.
3. **Không xuất định danh thô:** tránh in key chứa session ID, cookie, principal name hoặc nội dung session.
4. **Giới hạn phạm vi:** chỉ kiểm tra đúng Redis deployment, database và namespace của ứng dụng cần chẩn đoán.
5. **Giảm quyền:** dùng Redis ACL account chỉ có các command cần thiết; tách tài khoản quan sát khỏi tài khoản ghi dữ liệu của ứng dụng.
6. **Kiểm soát đầu ra:** terminal, shell history, CI logs, screenshots, clipboard và ticket đều có thể trở thành nơi lưu dữ liệu nhạy cảm.
7. **Ghi nhận mục đích:** lưu lại người thực hiện, thời điểm, môi trường, câu hỏi vận hành và kết quả tổng hợp; không lưu raw session ID hoặc attributes.

## 3. Bắt đầu bằng các lệnh Redis không đọc session value

Các lệnh sau cung cấp thông tin sức khỏe ở mức server hoặc database. Chúng thường phù hợp để bắt đầu điều tra vì không cần lấy session attributes.

```text
PING
INFO server
INFO memory
INFO stats
INFO keyspace
```

| Lệnh | Thông tin chính | Lưu ý |
|---|---|---|
| `PING` | Redis có phản hồi hay không | Không cung cấp thông tin session |
| `INFO server` | Phiên bản, uptime và thông tin server | Không chia sẻ toàn bộ output nếu có thông tin hạ tầng cần giới hạn |
| `INFO memory` | Bộ nhớ đang dùng, peak memory, cấu hình maxmemory | Dùng để theo dõi áp lực bộ nhớ |
| `INFO stats` | Tổng số request, expired keys, evicted keys, keyspace hits/misses và các bộ đếm khác | Dùng để xem xu hướng; nên so sánh theo thời gian |
| `INFO keyspace` | Số key và số key có expiration theo từng database | Là số liệu tổng hợp, không liệt kê tên key |

`INFO keyspace` có thể trả về dòng dạng:

```text
db0:keys=12000,expires=11800,avg_ttl=1740000
```

Đây là ví dụ minh họa. `keys` là số key trong database, `expires` là số key có expiration và `avg_ttl` là TTL trung bình theo milliseconds đối với key có expiry theo cách Redis báo cáo. Các con số này bao gồm workload khác nếu database được dùng chung; không mặc định chúng chỉ đại diện cho Spring Session. Nếu cần số liệu riêng theo namespace, cần phương pháp đếm có lọc và giới hạn đầu ra như phần tiếp theo.

`INFO` là snapshot tại thời điểm gọi, không phải báo cáo lịch sử. Để phát hiện xu hướng, thu thập metrics theo chu kỳ qua hệ thống monitoring và so sánh các khoảng thời gian tương đương.

## 4. Đếm key theo namespace mà không hiển thị tên key

`SCAN` duyệt key theo từng đợt và có thể lọc theo pattern. Lệnh này an toàn hơn `KEYS` đối với Redis đang phục vụ traffic vì không cố quét toàn bộ key trong một lệnh chặn dài. Tuy nhiên, `SCAN` vẫn trả về tên key cho client. Nếu key Spring Session chứa session ID, việc hiển thị kết quả có thể làm lộ định danh.

Trong PowerShell, có thể chuyển thẳng kết quả scan vào bộ đếm dòng để terminal chỉ hiển thị số lượng:

```powershell
redis-cli --scan --pattern 'storefront:sessions:*' | Measure-Object -Line
```

Trong shell kiểu Unix:

```bash
redis-cli --scan --pattern 'storefront:sessions:*' | wc -l
```

Hai ví dụ giả định namespace đã được cấu hình là `storefront:sessions`. Hãy thay pattern bằng namespace thực tế của ứng dụng. Đầu ra của bộ đếm chỉ là số dòng, nhưng tên key vẫn đi qua pipeline trong tiến trình cục bộ. Không bật chế độ trace ghi lại pipeline, không redirect raw output sang file chia sẻ và không chụp màn hình tiến trình trung gian.

Lưu ý khi đếm:

- `SCAN` là phép duyệt có thể trả kết quả trùng lặp trong một số tình huống khi key thay đổi trong lúc quét; bộ đếm là số liệu quan sát, không phải snapshot giao dịch chính xác.
- Tham số `COUNT` là gợi ý số phần tử mỗi lần quét, không phải giới hạn tổng số key.
- Pattern phải đủ hẹp để tránh quét các ứng dụng hoặc workload không liên quan.
- Nếu Redis database chứa nhiều loại key, kết quả đếm namespace không đồng nghĩa số session hợp lệ. Repository có thể dùng key phụ cho expiration hoặc index.
- Với Redis Cluster, cần dùng công cụ hiểu cluster và bảo đảm việc quét bao phủ các primary node. Không kết luận tổng số key toàn cluster từ một node đơn lẻ.

Không dùng lệnh sau trong production để liệt kê key:

```text
KEYS *
```

`KEYS` có thể làm Redis bị chặn khi keyspace lớn và sẽ in tên key ra output. Tránh cả việc copy danh sách key từ Redis Insight hoặc công cụ GUI sang ticket.

## 5. Quan sát TTL mà không đọc attributes

TTL là metadata hữu ích để hiểu expiration. Redis cung cấp `TTL` cho đơn vị giây và `PTTL` cho milliseconds. Khi dùng chúng, chỉ lấy số TTL cho một key đã được xác định trong quy trình điều tra được phê duyệt; không in key hoặc value trong báo cáo.

```text
TTL <key-da-duoc-chon-trong-phien-lam-viec-bao-mat>
PTTL <key-da-duoc-chon-trong-phien-lam-viec-bao-mat>
```

Các giá trị thường gặp:

| Kết quả | Ý nghĩa |
|---|---|
| Số dương | Số giây còn lại trước khi key hết hạn |
| `-1` | Key tồn tại nhưng không có expiration |
| `-2` | Key không tồn tại tại thời điểm kiểm tra |

Không suy ra session còn hợp lệ chỉ từ TTL của một key phụ. Redis repository có thể duy trì nhiều key với vai trò khác nhau; expiration và cleanup của Spring Session có thể không làm mọi key biến mất cùng lúc. Hãy kiểm tra session qua API Spring Session khi cần xác định tính hợp lệ của một session.

Nếu key có chứa session ID, ngay cả việc đặt key vào command line cũng có thể lưu nó trong shell history, process list hoặc audit log. Dùng công cụ nội bộ có cơ chế nhận input bảo mật và chỉ trả TTL, hoặc chạy thao tác trong phiên quản trị được kiểm soát. Không đưa key thật vào tài liệu, chat, ảnh chụp hay báo cáo sự cố.

## 6. Những lệnh cần tránh khi kiểm tra session production

Một số lệnh hữu ích trong phát triển nhưng có thể làm lộ session data hoặc gây ảnh hưởng hiệu năng khi chạy trên production.

| Lệnh/cách làm | Rủi ro | Cách thay thế |
|---|---|---|
| `GET`, `HGETALL`, `LRANGE`, `SMEMBERS` trên key session | Đọc trực tiếp value hoặc attributes có thể chứa thông tin nhạy cảm | Dùng API Spring Session chỉ trả metadata cần thiết |
| `DUMP` | Xuất toàn bộ nội dung serialized của key | Dùng metadata tổng hợp hoặc kiểm thử trong môi trường cô lập |
| `MONITOR` | Hiển thị command và arguments đang chạy; có thể chứa key, ID hoặc value | Dùng metrics, tracing đã lọc hoặc log ứng dụng đã redaction |
| `KEYS *` | Quét keyspace theo cách có thể chặn Redis và làm lộ key names | Dùng `SCAN` với pattern hẹp và đếm output mà không hiển thị |
| Redis Insight/GUI xem raw values | Dễ lộ key, attributes hoặc dữ liệu xác thực trên màn hình và clipboard | Dùng dashboard tổng hợp hoặc view metadata đã lọc |
| Export toàn bộ key/value | Tạo bản sao dữ liệu session ngoài repository | Không export production session; dùng dữ liệu giả trong môi trường test |

`SLOWLOG GET` cũng cần thận trọng: slow log có thể giữ tên command và arguments của lệnh chậm. Nếu arguments chứa key session hoặc dữ liệu nhạy cảm, việc xem raw slow log sẽ làm lộ chúng. Chỉ dùng trong quy trình được kiểm soát, giới hạn quyền và lọc/redact trước khi chia sẻ. Không bật `MONITOR` như công cụ chẩn đoán mặc định.

Không chạy `FLUSHDB`, `FLUSHALL`, `DEL` hàng loạt hoặc script tự viết để xóa key session trong lúc “kiểm tra”. Đây là thao tác thay đổi dữ liệu, có thể đăng xuất diện rộng hoặc phá hỏng cấu trúc index/expiration. Dùng API quản lý phiên và quy trình vận hành có kiểm soát nếu thực sự cần thu hồi session.

## 7. Dùng Redis ACL và tài khoản quan sát có quyền tối thiểu

Redis ACL cho phép giới hạn user theo command, key pattern và channel. Tài khoản quan sát nên tách khỏi tài khoản mà ứng dụng dùng để ghi session. Cấu hình cụ thể phụ thuộc phiên bản Redis và cách repository hoạt động; không sao chép một ACL mẫu vào production mà chưa kiểm tra các command thực sự cần thiết.

Một quy trình phù hợp gồm:

1. Tạo user riêng cho hoạt động monitoring/diagnostics.
2. Chỉ cấp quyền kết nối và các lệnh đọc metadata cần thiết như `PING`, `INFO`, `SCAN` hoặc lệnh metrics phù hợp.
3. Giới hạn key pattern vào namespace ứng dụng nếu cần truy cập key cụ thể; nhớ rằng quyền đọc key vẫn có thể tiết lộ định danh.
4. Không cấp `FLUSHDB`, `FLUSHALL`, `CONFIG`, `EVAL`, `DEL`, `SET` hoặc quyền quản trị không cần thiết cho tài khoản quan sát.
5. Bảo vệ thông tin xác thực ACL, dùng TLS khi phù hợp và luân chuyển credential theo quy trình của tổ chức.
6. Kiểm tra ACL trong staging với repository thực tế để bảo đảm tài khoản ứng dụng vẫn có đủ quyền vận hành.

Ví dụ minh họa tạo user chỉ có quyền một số lệnh đọc tổng hợp (cú pháp và command category cần xác nhận theo phiên bản Redis):

```text
ACL SETUSER session-observer on >REPLACE_WITH_SECRET \
  +ping +info +scan
```

Không đưa secret thật vào shell history hoặc tài liệu. Trong môi trường quản lý ACL nghiêm ngặt, cấu hình user qua secret manager hoặc công cụ quản trị có audit. Lệnh mẫu trên không phải một policy hoàn chỉnh cho mọi Redis version hoặc mọi dashboard.

## 8. Tạo endpoint chẩn đoán chỉ trả metadata đã lọc

Đội vận hành thường cần biết session có tồn tại hay không, được tạo khi nào, lần truy cập cuối và timeout bao nhiêu. Có thể xây endpoint nội bộ sử dụng `SessionRepository` để đọc session, nhưng chỉ trả những trường được cho phép. Không trả session ID thô hoặc toàn bộ attributes.

Ví dụ service trả metadata tối thiểu:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import org.springframework.stereotype.Service;

@Service
class SessionDiagnosticsService {

    private final SessionRepository<? extends Session> repository;

    SessionDiagnosticsService(SessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    Optional<SessionMetadata> inspect(String sessionId) {
        Session session = repository.findById(sessionId);
        if (session == null) {
            return Optional.empty();
        }

        return Optional.of(new SessionMetadata(
                session.getCreationTime(),
                session.getLastAccessedTime(),
                session.getMaxInactiveInterval()));
    }

    record SessionMetadata(
            Instant createdAt,
            Instant lastAccessedAt,
            Duration maxInactiveInterval) {
    }
}
```

Đây chỉ là service minh họa; endpoint gọi service cần xác thực mạnh, phân quyền riêng cho đội vận hành, giới hạn tốc độ, audit truy cập và kiểm soát cách nhận session ID. Nếu cần hiển thị kết quả cho người hỗ trợ, hãy chỉ trả `found`, tuổi session, idle duration và timeout; không trả ID hoặc attributes. Một API nhận session ID vẫn cần coi ID đầu vào là bí mật và tránh ghi nó vào access log.

Nếu chỉ cần thống kê, nên dùng metrics tổng hợp thay vì tra cứu từng session. Nếu cần tìm các phiên theo principal, dùng indexed repository và một quy trình quản trị được phân quyền; không để client tùy ý truy vấn principal khác.

## 9. Ẩn danh định danh khi cần liên kết log

Đôi khi cần biết hai log có thuộc cùng một session hay không mà không tiết lộ session ID. Có thể tạo fingerprint bằng HMAC với secret riêng của môi trường. HMAC an toàn hơn hash không khóa đối với định danh có thể đoán được, vì người xem log không thể dễ dàng thử danh sách ID phổ biến nếu không có secret.

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class SessionFingerprint {

    static String of(String sessionId, byte[] hmacSecret) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacSecret, "HmacSHA256"));
            byte[] digest = mac.doFinal(
                    sessionId.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(digest);
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot create session fingerprint", ex);
        }
    }
}
```

Secret HMAC phải được lấy từ secret manager, không hardcode trong source code hoặc ghi vào log. Dùng secret khác nhau giữa production, staging và development để fingerprint không liên kết chéo môi trường. Nếu không cần đối chiếu lâu dài, có thể dùng fingerprint luân phiên theo ngày hoặc theo incident để giảm khả năng liên kết hành vi qua thời gian.

Fingerprint vẫn là dữ liệu có thể liên kết các hoạt động của cùng một session, nên không nên đưa nó vào metric label có cardinality cao hoặc chia sẻ rộng rãi. Chỉ lưu trong log hạn chế quyền và theo thời hạn retention phù hợp.

## 10. Dashboard và metrics phù hợp cho Spring Session

Dashboard vận hành nên tập trung vào trạng thái hệ thống, không hiển thị danh sách người dùng hoặc session ID.

| Nhóm | Metrics nên hiển thị | Tránh hiển thị |
|---|---|---|
| Redis health | Availability, ping latency, reconnects, command errors | Credentials, client command arguments |
| Memory | Used memory, peak memory, maxmemory headroom, fragmentation | Raw key/value samples |
| Keyspace | Tổng key, key có expiration, xu hướng số key theo namespace | Danh sách key có session ID |
| Expiration | `expired_keys`, TTL distribution dạng histogram nếu đo được an toàn | ID của session vừa hết hạn |
| Eviction | `evicted_keys`, eviction rate | Nội dung key bị eviction |
| Application | Session lookup success/miss, create/delete/expire counts, repository latency | Session ID hoặc principal làm label |
| Serialization | Lỗi serialize/deserialize theo loại exception | Payload lỗi đầy đủ nếu chứa dữ liệu session |

Các metrics nên có label giới hạn như `service`, `environment`, `instance` hoặc `operation`. Tránh label theo session ID, username, email, tenant tùy ý hoặc key Redis vì cardinality sẽ tăng rất nhanh và có thể làm lộ dữ liệu. Với log lỗi serialization, chỉ ghi tên class hoặc loại lỗi cần thiết; không dump object/payload.

## 11. Quy trình điều tra một sự cố session

Khi người dùng báo bị đăng xuất hoặc session không được chia sẻ giữa các instance, hãy đi từ dữ liệu tổng hợp đến metadata tối thiểu:

1. Kiểm tra Redis `PING`, availability, latency và connection errors.
2. Xem `INFO memory`, `INFO stats`, `INFO keyspace` để phát hiện memory pressure, eviction, expiration tăng bất thường hoặc key count thay đổi.
3. So sánh cấu hình Redis endpoint, database, namespace, cookie name và serializer giữa các instance.
4. Kiểm tra request/response cookie trong môi trường bảo mật; che giá trị cookie trước khi lưu ảnh hoặc gửi báo cáo.
5. Dùng API chẩn đoán được phân quyền để kiểm tra trạng thái session mà không trả attributes.
6. Nếu cần đối chiếu log, dùng fingerprint HMAC thay session ID thô.
7. Nếu nghi ngờ serializer, kiểm tra loại exception và class liên quan trong môi trường giới hạn; không in payload.
8. Nếu cần thu hồi session, dùng API Spring Session hoặc công cụ quản trị được kiểm soát, không xóa key bằng thao tác quét hàng loạt.

Mỗi bước chỉ nên mở rộng mức chi tiết khi bằng chứng hiện tại chưa trả lời được câu hỏi. Không bắt đầu bằng việc dump toàn bộ Redis keyspace hoặc session data.

## 12. Kiểm thử công cụ quan sát

Trước khi dùng dashboard hoặc script trong production, hãy thử với dữ liệu giả ở staging và xác nhận đầu ra không chứa session ID, principal hoặc attributes.

Các kiểm tra nên có:

- Tạo session test với attribute giả, sau đó xác nhận dashboard chỉ hiển thị count/TTL/metadata cho phép.
- Chạy lệnh scan qua pipeline đếm và xác nhận terminal chỉ hiển thị số lượng, không hiển thị raw keys.
- Kiểm tra log shell, CI và audit không lưu command arguments chứa key hoặc session ID.
- Xác nhận Redis observer ACL không có quyền ghi hoặc xóa dữ liệu ngoài nhu cầu.
- Kiểm tra endpoint diagnostics từ user không có quyền phải bị từ chối và truy cập hợp lệ được audit.
- Xác nhận HMAC fingerprint không thể được tạo nếu thiếu secret và secret không xuất hiện trong log.
- Thử với Redis Cluster nếu production dùng cluster; xác nhận công cụ quét và metrics bao phủ các primary node.
- Kiểm tra dashboard không có label theo session ID, username hoặc key Redis.

Không dùng session thật của người dùng để kiểm thử chức năng xem raw data. Hãy tạo dữ liệu giả, với ID và attributes không mang thông tin cá nhân.

## 13. Bảng lệnh tham khảo

| Nhu cầu | Lệnh/cách làm | Đầu ra an toàn cần giữ |
|---|---|---|
| Kiểm tra Redis sống | `PING` | `PONG` hoặc lỗi kết nối |
| Xem bộ nhớ | `INFO memory` | Các số liệu memory tổng hợp |
| Xem key count tổng thể | `INFO keyspace` | Số key, số key có expiry, TTL trung bình |
| Xem thống kê expiration/eviction | `INFO stats` | Bộ đếm tổng hợp |
| Đếm key namespace | `SCAN`/`--scan` qua pipeline đếm | Số lượng; không lưu raw key list |
| Kiểm tra TTL một key đã được phê duyệt | `TTL` hoặc `PTTL` qua công cụ bảo mật | Chỉ số TTL, không ghi key |
| Kiểm tra session hợp lệ | API `SessionRepository` được phân quyền | Found/not found và metadata đã lọc |
| Liên kết log cùng phiên | HMAC fingerprint | Fingerprint hạn chế quyền, không phải session ID |

Tránh `KEYS *`, `MONITOR`, `GET`/`HGETALL`/`DUMP` trên session production và mọi thao tác xóa hàng loạt chỉ nhằm phục vụ quan sát.

## 14. Nguyên tắc cần nhớ

- Key Redis và session ID phải được xem là dữ liệu nhạy cảm; session attributes có thể chứa credential hoặc thông tin cá nhân.
- Bắt đầu bằng `PING`, `INFO memory`, `INFO stats` và `INFO keyspace` để lấy số liệu tổng hợp.
- Dùng `SCAN` với namespace hẹp; chuyển kết quả thẳng vào bộ đếm để không in raw key names.
- Dùng `TTL`/`PTTL` chỉ cho key được chọn qua quy trình bảo mật; chỉ giữ kết quả số và không đưa key thật vào history/log.
- Không dùng `KEYS *`, `MONITOR` hoặc lệnh đọc value để kiểm tra session production theo thói quen.
- Tách Redis observer account, áp dụng ACL và quyền tối thiểu; không cấp quyền ghi/xóa cho công cụ chỉ quan sát.
- Endpoint diagnostics phải xác thực, phân quyền, audit và chỉ trả metadata được phép.
- Dùng HMAC fingerprint nếu cần liên kết log; bảo vệ secret và giới hạn retention.
- Dashboard dùng metrics tổng hợp, không dùng session ID hoặc principal làm label.
- Khi cần kiểm tra tính hợp lệ của phiên, dùng API Spring Session; không suy luận chỉ từ sự tồn tại của key Redis.
