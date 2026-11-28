# Redis từ chối cấu hình keyspace, listener ngừng nhận và chỉ mục còn sót

Spring Session dùng Redis để lưu session có thể cần nhận biết các sự kiện như key bị xóa hoặc hết hạn. Với repository có hỗ trợ index và event, Redis keyspace notifications giúp Spring Session phát hiện thay đổi vòng đời session, phát các sự kiện như `SessionDeletedEvent` hoặc `SessionExpiredEvent`, cập nhật trạng thái liên quan và dọn các chỉ mục phụ.

Trong production, Redis có thể từ chối lệnh cấu hình `notify-keyspace-events` vì tài khoản ứng dụng không có quyền `CONFIG`, dịch vụ Redis managed khóa lệnh quản trị hoặc cấu hình được quản lý qua parameter group. Ứng dụng khi đó vẫn có thể đọc/ghi session, nhưng event listener không nhận đủ thông báo. Nếu listener mất kết nối hoặc bỏ lỡ Pub/Sub message, các index phụ có thể còn tham chiếu tới session đã hết hạn hoặc đã bị xóa.

Chẩn đoán cần tách ba lớp: Redis có phát event đúng không, ứng dụng có subscribe và nhận event không, và repository có xử lý event để cập nhật index không. Chỉ thấy session key đã hết hạn chưa đủ để kết luận toàn bộ vòng đời event và index cleanup đã hoàn tất.

## 1. Keyspace notifications là gì?

Redis keyspace notifications là cơ chế phát thông báo Pub/Sub khi một số thao tác hoặc sự kiện xảy ra trên key. Có hai kiểu channel:

- **Keyspace channel**: tên channel chứa tên key, dạng `__keyspace@<db>__:<key>`; message mô tả event.
- **Keyevent channel**: tên channel chứa loại event, dạng `__keyevent@<db>__:<event>`; message chứa tên key.

Spring Session Redis có thể dùng keyevent notifications để nhận biết thao tác xóa và expiration. Các event class Redis liên quan thường gồm:

| Redis event class | Ký hiệu cấu hình | Ví dụ |
|---|---|---|
| Generic commands | `g` | `DEL`, `EXPIRE`, `RENAME` và các thao tác generic liên quan |
| Expired events | `x` | Key bị Redis phát hiện hết TTL và expire |
| Evicted events | `e` | Key bị loại do `maxmemory-policy` |
| Keyevent channel | `E` | Phát thông báo trên channel `__keyevent@...__` |
| Keyspace channel | `K` | Phát thông báo trên channel `__keyspace@...__` |

Với cấu hình Spring Session Redis thường dùng, chuỗi `Egx` có nghĩa là bật keyevent channel (`E`), generic events (`g`) và expired events (`x`). Hãy xác nhận yêu cầu chính xác của phiên bản Spring Session và repository đang dùng; không bật toàn bộ notification class nếu chỉ cần một tập nhỏ.

Keyspace notifications thường bị tắt mặc định vì phát event có chi phí CPU và network. Đây là tính năng của Redis server, không phải chỉ một tùy chọn client. Tạo một `RedisMessageListenerContainer` trong ứng dụng không tự bật notifications ở Redis.

## 2. Spring Session dùng event để làm gì?

Với repository Redis có hỗ trợ index, event notifications giúp Spring Session phản ứng với session bị xóa hoặc hết hạn. Các chức năng liên quan có thể gồm:

- Phát `SessionDeletedEvent` khi session bị xóa chủ động và repository nhận được event tương ứng.
- Phát `SessionExpiredEvent` khi repository nhận được notification expiration.
- Phát event tổng quát `SessionDestroyedEvent` cho listener ứng dụng theo contract của Spring Session.
- Duy trì index dùng để tra cứu session theo principal name.
- Thực hiện cleanup các cấu trúc phụ liên quan tới session expiration và index.
- Hỗ trợ thành phần khác, ví dụ WebSocket registry, đóng kết nối gắn với session đã bị hủy.

Chi tiết event và index phụ thuộc repository implementation và phiên bản. `RedisIndexedSessionRepository` có các chức năng index/event khác với một repository Redis đơn giản chỉ lưu và tìm session theo ID. Nếu ứng dụng cần `findByIndexNameAndIndexValue`, sự kiện session hoặc cleanup index, hãy xác minh đang dùng implementation hỗ trợ các chức năng đó.

Keyspace notifications không phải cơ chế lưu trữ session. Redis vẫn lưu session hash/key; notification chỉ báo cho subscriber biết một thay đổi đã xảy ra. Nếu notification bị mất, dữ liệu session và index có thể không còn đồng bộ.

## 3. Vì sao Redis từ chối cấu hình `notify-keyspace-events`?

Spring Session có thể dùng `ConfigureRedisAction` để yêu cầu Redis bật keyspace notifications khi khởi tạo. Trong một số cấu hình, action mặc định thực hiện lệnh cấu hình Redis. Lệnh có thể thất bại vì:

1. **ACL không cấp quyền quản trị:** user của ứng dụng được phép đọc/ghi key nhưng không có quyền chạy `CONFIG SET`.
2. **Managed Redis khóa lệnh CONFIG:** nhà cung cấp chỉ cho thay đổi tham số qua console, API quản trị hoặc parameter group.
3. **Tài khoản ứng dụng có quyền Pub/Sub nhưng không có quyền CONFIG:** listener có thể subscribe, nhưng ứng dụng không được phép bật server notification.
4. **Cấu hình sai endpoint hoặc DB index:** ứng dụng cấu hình một Redis node/database, còn key session thực tế nằm ở node hoặc database khác.
5. **Cấu hình bị ghi đè khi restart:** `CONFIG SET` có thể chỉ có hiệu lực runtime; cấu hình persistent/parameter group chưa được cập nhật.
6. **Topology cluster:** notification có thể được phát ở node sở hữu key; subscription và cấu hình phải phù hợp với cluster topology và khả năng của client/repository.

Log có thể cho thấy lỗi `NOPERM`, `ERR unknown command`, `CONFIG is disabled`, `Unsupported CONFIG` hoặc lỗi quản trị tương đương. Không được diễn giải lỗi này thành “Redis session repository không hoạt động”. Có thể thao tác đọc/ghi session vẫn thành công trong khi event-driven cleanup bị thiếu.

## 4. Bật cấu hình bằng quyền quản trị hoặc cấu hình dịch vụ

Nếu tự quản lý Redis và có quyền quản trị, có thể xem cấu hình hiện tại:

```text
CONFIG GET notify-keyspace-events
```

Để bật keyevent generic và expiration notifications theo yêu cầu thường gặp của Spring Session:

```text
CONFIG SET notify-keyspace-events Egx
```

`Egx` là ví dụ cấu hình tối thiểu thường dùng cho keyevent `del` và `expired`. Trước khi áp dụng, kiểm tra tài liệu của phiên bản Spring Session và các ứng dụng khác đang dùng Redis. Nếu Redis hiện có notification flags phục vụ chức năng khác, cần hợp nhất flags cần thiết thay vì ghi đè và vô tình tắt chúng.

Lệnh `CONFIG SET` có thể chỉ thay đổi cấu hình runtime và bị mất sau restart/failover. Hãy cập nhật cấu hình persistent tương ứng, ví dụ `redis.conf`, parameter group hoặc cấu hình của nhà cung cấp. Với dịch vụ managed, một thay đổi có thể cần apply parameter group hoặc chờ cửa sổ bảo trì; kiểm tra trạng thái áp dụng trên control plane.

Không cấp quyền `CONFIG` rộng cho tài khoản runtime chỉ để Spring Session tự cấu hình Redis nếu chính sách vận hành yêu cầu tách quyền. Tốt hơn là quản trị viên cấu hình server trước, còn ứng dụng dùng tài khoản có quyền tối thiểu để đọc/ghi key và subscribe các channel cần thiết.

## 5. Khi ứng dụng không được phép chạy CONFIG SET

Spring Session cung cấp `ConfigureRedisAction.NO_OP` để ứng dụng bỏ qua bước tự cấu hình Redis. Khi dùng cách này, quản trị viên chịu trách nhiệm bảo đảm Redis đã có notification flags phù hợp.

Ví dụ cấu hình Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.ConfigureRedisAction;

@Configuration
class RedisSessionOperationsConfiguration {

    @Bean
    static ConfigureRedisAction configureRedisAction() {
        return ConfigureRedisAction.NO_OP;
    }
}
```

Tên package và cách cấu hình có thể thay đổi theo phiên bản Spring Session; hãy dùng API đúng với dependency đang chạy. Ý nghĩa của `NO_OP` là không yêu cầu ứng dụng thay đổi cấu hình server. Nó **không** bật notifications, không sửa ACL và không kiểm tra rằng Redis đã được cấu hình đúng.

Nếu dùng `NO_OP` trong khi Redis chưa bật notifications, ứng dụng có thể khởi động bình thường nhưng không nhận event expiration/delete. Đây là lỗi cấu hình có thể chỉ lộ ra khi session hết hạn, listener cần phát event hoặc index cần cleanup. Vì vậy cần có kiểm tra vận hành sau deploy.

## 6. Các quyền Redis cần phân biệt

Đừng gộp quyền cấu hình server với quyền sử dụng Pub/Sub. Một tài khoản có thể được cấp quyền subscribe nhưng vẫn không được phép thay đổi `notify-keyspace-events`.

| Hoạt động | Quyền/năng lực cần kiểm tra |
|---|---|
| Đọc/ghi session keys | Quyền command trên key pattern/namespace Spring Session |
| Subscribe keyevent channels | Quyền `SUBSCRIBE` hoặc `PSUBSCRIBE` phù hợp với cách listener đăng ký |
| Cấu hình notification flags | Quyền quản trị `CONFIG SET`, nếu ứng dụng tự cấu hình |
| Kiểm tra notification config | Quyền `CONFIG GET`, nếu môi trường cho phép |
| Dọn index/metadata | Quyền đọc, ghi, xóa trên các key phụ mà repository sử dụng |

Với Redis ACL, channel permissions cũng có thể giới hạn việc subscribe. Cần kiểm tra command permissions và channel patterns mà listener thực tế dùng. Không mở quyền `+@all` hoặc `allchannels` chỉ để khắc phục nhanh; hãy cấp đúng quyền tối thiểu dựa trên tài liệu repository và log Redis.

## 7. Listener ngừng nhận thông báo

Ngay cả khi Redis phát event đúng, ứng dụng vẫn có thể không nhận được nếu listener không hoạt động. Với Spring Session Redis, `RedisMessageListenerContainer` thường quản lý subscription và chuyển message tới listener của repository.

Nguyên nhân thường gặp:

- Listener container chưa khởi động hoặc bean không được tạo do cấu hình repository sai.
- Redis connection bị đóng, timeout hoặc TLS/authentication lỗi.
- ACL không cho subscribe channel hoặc pattern.
- Subscriber reconnect không thành công sau failover.
- Ứng dụng kết nối nhầm Redis endpoint/database.
- Network policy chặn luồng Pub/Sub trong khi lệnh command thông thường vẫn đi được.
- Redis Cluster/managed service có topology notification khác với cách subscription được cấu hình.
- Listener thread bị nghẽn hoặc exception trong callback làm chậm xử lý.

Redis Pub/Sub không phải durable queue. Nếu subscriber offline khi event được phát, Redis không giữ message để phát lại sau reconnect. Listener khởi động lại chỉ nhận các event tương lai; nó không tự biết những key đã hết hạn trong khoảng gián đoạn nếu repository không có cơ chế reconciliation riêng.

Do đó, listener health phải được theo dõi độc lập với health của thao tác GET/SET session. Một endpoint health chỉ kiểm tra `PING` hoặc đọc một session test không chứng minh Pub/Sub subscription đang nhận event.

## 8. Kiểm tra notification ở Redis

Trên Redis mà người vận hành có quyền quản trị, kiểm tra flags:

```text
CONFIG GET notify-keyspace-events
```

Nếu cần kiểm tra channel trong môi trường test, có thể subscribe bằng redis-cli:

```text
PSUBSCRIBE __keyevent@0__:expired __keyevent@0__:del
```

Sau đó, trong một terminal test khác, tạo key có TTL ngắn rồi chờ expire hoặc xóa key:

```text
SET spring-session-notification-test value EX 5
DEL spring-session-notification-test
```

Ví dụ dùng DB index `0`; thay index theo cấu hình thực tế. Lệnh subscribe minh họa cách quan sát keyevent channel; nếu listener Spring Session dùng pattern hoặc DB index khác, cần kiểm tra đúng channel tương ứng. Không dùng key session production làm test key và không publish/xóa session thật để thử.

Nếu `CONFIG GET` bị từ chối, đó không tự chứng minh notifications tắt. Dùng parameter group, cấu hình nhà cung cấp hoặc yêu cầu quản trị viên xác nhận flags. Nếu `PSUBSCRIBE` bị từ chối, kiểm tra ACL channel permissions và command permissions.

## 9. Kiểm tra listener trong ứng dụng

Các bước chẩn đoán ở phía Spring:

1. Xác nhận đúng Redis connection factory được repository và listener container dùng.
2. Xem startup logs để phát hiện lỗi cấu hình notifications hoặc đăng ký listener.
3. Xác nhận `RedisMessageListenerContainer` được khởi tạo và có connection/subscription đang hoạt động theo cách quan sát được của phiên bản.
4. Kiểm tra ACL user có thể subscribe các channel/pattern cần thiết.
5. Kiểm tra Redis endpoint, DB index, TLS, password/ACL và topology giống với session repository.
6. Trong môi trường test, tạo/xóa/expire một session giả và quan sát event listener nhận được.
7. Kiểm tra listener callback có exception, queue delay hoặc thread starvation không.

Không dựa vào việc application context đã khởi động thành công để kết luận listener đang nhận message. Một số cấu hình cho phép ứng dụng tiếp tục chạy dù notification feature không hoạt động; cần test event end-to-end.

## 10. Index còn sót là gì?

Repository có hỗ trợ index có thể duy trì cấu trúc phụ ngoài session record chính. Ví dụ, index principal name giúp tìm các session của một người dùng; expiration bucket hoặc metadata phụ giúp xử lý session hết hạn.

Index còn sót (stale index entry) xảy ra khi index vẫn chứa tham chiếu tới session ID đã không còn session hợp lệ. Một số nguyên nhân:

- Redis đã expire session key nhưng listener không nhận event.
- Listener offline hoặc mất Pub/Sub message trong thời gian reconnect.
- Redis không bật `expired`/`del` notifications cần thiết.
- Ứng dụng không có quyền subscribe channel.
- Session bị xóa thủ công bằng lệnh Redis hoặc công cụ quản trị bỏ qua logic repository.
- Một phiên bản repository cũ hoặc bug cleanup không xử lý hết cấu trúc phụ.
- Khôi phục backup đưa index và session data ở hai thời điểm không đồng nhất.
- Namespace hoặc DB index thay đổi giữa các node, khiến cleanup thao tác trên vùng dữ liệu khác.

Hệ quả phụ thuộc loại index và API sử dụng:

- Truy vấn theo principal có thể trả về ID không còn session, hoặc phải bỏ qua entry không tìm thấy.
- Số lượng index entry có thể tăng dù active session count không tăng.
- Cleanup/reconciliation có thể tốn thêm Redis commands và làm tăng latency.
- Các event session destroyed có thể không được phát tới listener ứng dụng, ví dụ thành phần quản lý WebSocket chưa đóng connection đúng lúc.

Không kết luận index hỏng chỉ vì số lượng index key khác số session key. Một session có thể xuất hiện trong nhiều cấu trúc index và expiration bucket theo thiết kế. Cần xác định semantics của repository và phiên bản trước khi đối chiếu số lượng.

## 11. Phân biệt session key, principal index và expiration metadata

Trong Redis indexed repository, dữ liệu session và các cấu trúc hỗ trợ tra cứu/expiration được lưu thành nhiều key hoặc collection. Prefix và cấu trúc nội bộ phụ thuộc `redisNamespace` và phiên bản Spring Session.

Vì vậy:

- Không hardcode key pattern nội bộ trong script cleanup nếu chưa xác nhận đúng version/schema.
- Không xóa một index key chỉ vì tên có vẻ cũ; key có thể chứa tham chiếu tới nhiều session còn hoạt động.
- Không dùng `KEYS *` trên Redis production để liệt kê session/index vì lệnh có thể chặn Redis khi keyspace lớn.
- Dùng `SCAN` theo namespace đã xác minh, với `COUNT` giới hạn, trong cửa sổ bảo trì hoặc công cụ giám sát có kiểm soát.
- Kiểm tra `TYPE`, `TTL`/`PTTL` và nội dung cấu trúc bằng dữ liệu test hoặc read-only khi có thể.
- Không ghi session ID, principal name hoặc attributes nhạy cảm ra terminal/log chia sẻ.

Index key có thể có TTL hoặc được dọn qua event, tùy cấu trúc. Không áp một TTL tùy ý cho mọi key phụ: một TTL quá ngắn có thể làm mất index của session còn sống; không TTL có thể để lại dữ liệu rác nếu listener không cleanup.

## 12. Ví dụ quy trình kiểm tra an toàn bằng redis-cli

Trước tiên xác nhận đúng endpoint, database index và namespace. Sau đó dùng một session giả trong môi trường test. Ví dụ các lệnh quan sát tổng quát:

```text
SCAN 0 MATCH spring:session:* COUNT 100
TYPE <test-key>
TTL <test-key>
PTTL <test-key>
```

Tên prefix `spring:session:*` chỉ là ví dụ; ứng dụng có thể đặt namespace khác. `SCAN` trả cursor nên phải tiếp tục cho tới cursor `0` nếu muốn duyệt hết, và kết quả có thể thay đổi trong khi keyspace đang được cập nhật.

Nếu cần xác minh index principal, tạo một session test với principal giả, dùng API repository được hỗ trợ để tra cứu và so sánh với key/index trong Redis. Không truy vấn principal thật hoặc dump toàn bộ index trong môi trường production nếu không có kiểm soát dữ liệu nhạy cảm.

Không chạy `DEL`/`UNLINK` trên key nội bộ production để thử nghiệm. Một thao tác xóa thủ công có thể bỏ qua event/cleanup logic, làm index không đồng bộ hơn hoặc phá hỏng session đang hoạt động.

## 13. Khôi phục cấu hình keyspace notifications

Một quy trình phục hồi an toàn:

1. Xác định Redis endpoint, topology, DB index và namespace mà ứng dụng thực sự dùng.
2. Thu thập lỗi startup/runtime: `CONFIG` bị từ chối, `NOPERM`, subscribe error, reconnect loop hoặc listener exception.
3. Xác nhận phiên bản Spring Session và repository implementation; xác định event classes cần thiết.
4. Làm việc với Redis administrator/managed service operator để bật keyevent flags phù hợp, thường cần `E`, `g` và `x` cho `del`/`expired`.
5. Nếu ứng dụng không được phép cấu hình server, khai báo `ConfigureRedisAction.NO_OP` và quản lý flags ngoài ứng dụng.
6. Xác nhận cấu hình đã được áp dụng bền vững sau restart/failover, không chỉ trong runtime hiện tại.
7. Kiểm tra ACL cho listener subscribe đúng channel/pattern và có quyền truy cập key cần thiết.
8. Khởi động lại hoặc buộc listener reconnect theo cách được hỗ trợ; xác nhận subscription hoạt động.
9. Tạo session giả, xóa chủ động và để một session khác hết TTL; xác nhận event tới ứng dụng.
10. Đo index entry trước/sau và xác nhận cleanup hoạt động trên dữ liệu test.

Không bật `CONFIG SET` bằng cách nâng quyền tài khoản ứng dụng lên admin nếu không cần. Tách quyền quản trị cấu hình Redis khỏi quyền runtime của ứng dụng sẽ dễ kiểm soát và audit hơn.

## 14. Listener đã phục hồi nhưng event cũ đã mất

Sau khi listener reconnect, nó chỉ nhận message mới. Các expiration/delete event đã phát trong khoảng subscriber offline có thể không được phát lại. Do đó, cần phân biệt:

- **Phục hồi subscription:** listener đã subscribe lại và nhận event mới.
- **Phục hồi dữ liệu:** index/metadata còn sót từ khoảng mất kết nối đã được đối soát và xử lý.

Hai việc này không đồng nghĩa. Nếu chỉ restart application và thấy log subscription thành công, index cũ vẫn có thể còn nguyên.

Reconciliation có thể được thực hiện bằng job có giới hạn:

1. Duyệt các index entry theo batch nhỏ, dùng API hoặc schema được hỗ trợ.
2. Với mỗi session ID, kiểm tra repository có còn session hợp lệ không.
3. Chỉ loại entry đã xác nhận stale và theo semantics repository; tránh thao tác trực tiếp nếu repository có API cleanup phù hợp.
4. Giới hạn tốc độ và concurrency để không làm quá tải Redis.
5. Ghi metric số entry kiểm tra, stale, xóa thành công và lỗi.
6. Chạy lại an toàn; xử lý phải idempotent.

Không tạo một job quét toàn bộ keyspace liên tục. Nếu repository không cung cấp API an toàn để sửa index, dùng quy trình được tài liệu hóa cho đúng phiên bản hoặc phối hợp nhà cung cấp/maintainer thay vì tự đoán cấu trúc nội bộ.

## 15. Vì sao không nên tự xóa index còn sót bằng tay?

Các key phụ có thể liên quan đến nhiều session, expiration bucket, principal index hoặc metadata nội bộ. Xóa nhầm có thể:

- Làm session còn hạn không thể tìm qua principal index.
- Làm session expiration event hoặc cleanup tiếp theo không còn tìm được metadata cần thiết.
- Xóa index của người dùng khác nếu key chứa tập session ID chung.
- Tạo khác biệt giữa node đang chạy hai phiên bản repository.
- Khiến số liệu vận hành sai, làm dashboard báo active sessions thấp hoặc cao không đúng.

Ưu tiên API repository và job reconciliation có kiểm tra session tồn tại. Nếu bắt buộc sửa dữ liệu trực tiếp, phải có backup, xác nhận schema đúng version, dry-run danh sách key, giới hạn batch, kế hoạch rollback và phê duyệt vận hành theo quy trình tổ chức.

## 16. Kiểm thử notifications và listener

Một integration test nên kiểm tra cả cấu hình Redis lẫn event end-to-end:

1. Khởi động Redis test instance với notification flags tương ứng.
2. Khởi động ứng dụng với repository indexed và listener container.
3. Tạo session có principal giả và xác nhận principal index tìm thấy session.
4. Xóa session qua repository; xác nhận listener nhận event delete/destroy theo contract.
5. Tạo session khác với idle timeout ngắn; chờ Redis expiration event và xác nhận `SessionExpiredEvent` nếu repository/version hỗ trợ.
6. Tắt hoặc ngắt subscriber trong lúc event được phát; xác nhận Pub/Sub không phát lại message sau reconnect.
7. Tạo stale index có kiểm soát trong test fixture hoặc mô phỏng missed event; chạy reconciliation và xác nhận entry được xử lý.
8. Khởi động Redis với ACL không cho `CONFIG SET`; xác nhận ứng dụng dùng `ConfigureRedisAction.NO_OP` và flags được provision bên ngoài.
9. Thử ACL không cho subscribe; xác nhận health/alert phát hiện listener không hoạt động.
10. Restart Redis hoặc failover; xác nhận listener reconnect và event mới tiếp tục được nhận.

Không dùng `Thread.sleep()` với một khoảng cố định rồi kết luận event chắc chắn tới. Dùng polling có timeout và assertion eventual để kiểm tra điều kiện. Redis expiration có thể trễ so với TTL logic vì cơ chế lazy/active expiration.

## 17. Giám sát vận hành

Theo dõi riêng repository operations, listener và index health.

| Chỉ số | Dấu hiệu cần chú ý |
|---|---|
| Redis notification flags/config drift | Flags không còn đúng sau restart hoặc failover |
| Listener connection/subscription state | Subscriber disconnected, reconnect loop hoặc không subscribe được |
| Event received theo loại | Expired/delete event giảm bất thường so với session churn |
| Event processing latency | Khoảng cách từ publish/receive tới xử lý cleanup tăng |
| Listener callback errors | Exception làm xử lý event thất bại |
| Principal index lookup miss/stale count | Index tham chiếu session không tồn tại hoặc query trả kết quả bất thường |
| Index size so với active sessions | Chênh lệch tăng kéo dài cần điều tra theo semantics repository |
| Redis memory/key count/TTL | Key phụ tăng bất thường hoặc thiếu TTL |
| Reconciliation count | Số entry stale được phát hiện và xử lý |

Không dùng session ID, username, principal name hoặc cookie làm metric label. Dùng label cardinality thấp như environment, instance, event type và repository name. Nếu cần correlation, dùng mã nội bộ ngắn hạn đã được bảo vệ trong log truy cập hạn chế.

Health check nên phân biệt:

- **Command health:** ứng dụng đọc/ghi được Redis.
- **Pub/Sub health:** listener đang subscribe và nhận được test event.
- **Index health:** thao tác tra cứu principal và cleanup hoạt động đúng trong test hoặc canary.

Một PING thành công chỉ chứng minh command path đang hoạt động; nó không chứng minh listener nhận event.

## 18. Xử lý theo tình huống

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Startup báo không được phép CONFIG | ACL hoặc managed Redis khóa CONFIG | Provision notification flags qua admin/parameter group; dùng `NO_OP` nếu ứng dụng không cấu hình server |
| Session đọc/ghi được nhưng không có expiration event | Thiếu `E`/`x`, sai DB index hoặc listener chưa subscribe | Kiểm tra flags, channel và event test |
| Delete event có nhưng expire event không có | Thiếu `x` hoặc Redis chưa thực hiện expiration vật lý | Kiểm tra notification flags và TTL/expiration timing |
| Redis có flags nhưng listener không nhận | ACL channel, network, container lỗi hoặc sai topology | Kiểm tra subscribe permissions, connection factory và reconnect logs |
| Listener reconnect nhưng index cũ còn | Pub/Sub không replay event đã bỏ lỡ | Chạy reconciliation có kiểm soát theo repository schema |
| Principal lookup trả ID không còn session | Stale index entry hoặc dữ liệu đang thay đổi đồng thời | Xác minh bằng repository lookup; xử lý stale entry theo API hỗ trợ |
| Index tăng mãi | Listener thiếu event, cleanup lỗi hoặc TTL/index policy sai | So sánh churn, event count, TTL và cleanup metrics |
| Sau Redis failover listener im lặng | Subscriber chưa kết nối lại tới topology mới | Kiểm tra RedisMessageListenerContainer, ACL và topology-aware connection |
| Sau restore có session đã logout xuất hiện lại | Backup phục hồi trạng thái cũ | Đánh giá invalidation epoch/reauthentication và không tin session cũ mặc định |

## 19. Quy trình runbook ngắn

Khi phát hiện Redis từ chối cấu hình keyspace hoặc index còn sót:

1. Xác định phạm vi: một node, toàn bộ app hay chỉ event/index feature.
2. Kiểm tra Redis command health, listener subscription health và repository lookup riêng.
3. Đọc lỗi `CONFIG`, ACL, subscribe, network và reconnect từ log đã che thông tin nhạy cảm.
4. Xác minh `notify-keyspace-events` qua cấu hình quản trị; bảo đảm có các flags cần thiết cho event mà repository sử dụng.
5. Kiểm tra `ConfigureRedisAction`: nếu dùng `NO_OP`, xác nhận cấu hình server được provision ngoài ứng dụng.
6. Test event delete và expiration bằng session/key giả trong môi trường phù hợp.
7. Khôi phục listener subscription và xác nhận event mới tới được ứng dụng.
8. Đánh giá stale index bằng API repository hoặc công cụ read-only đã xác minh schema.
9. Chạy reconciliation theo batch, idempotent và có giới hạn nếu cần.
10. Theo dõi event rate, listener errors, index size và session lookup sau khi phục hồi.

Không xóa namespace hoặc toàn bộ Redis keyspace để “làm sạch” index. Hành động đó có thể đăng xuất mọi người dùng và làm mất dữ liệu session hợp lệ mà không giải quyết được nguyên nhân listener.

## 20. Nguyên tắc cần nhớ

- Keyspace notifications là Pub/Sub events do Redis phát; chúng không phải session storage và không phải durable queue.
- `Egx` thường bật keyevent channel, generic delete events và expired events cần cho Spring Session Redis; xác minh theo đúng repository/version.
- Redis có thể từ chối `CONFIG SET` do ACL hoặc managed-service policy; provision flags qua quản trị và dùng `ConfigureRedisAction.NO_OP` khi phù hợp.
- `NO_OP` không bật notifications; ứng dụng chỉ bỏ qua thao tác tự cấu hình server.
- Phân biệt quyền `CONFIG`, quyền subscribe Pub/Sub và quyền đọc/ghi session/index keys.
- Command health không chứng minh Pub/Sub listener health; phải test event end-to-end.
- Pub/Sub message phát trong lúc listener offline có thể bị mất và không được replay sau reconnect.
- Stale index có thể còn sau missed event; xác minh session bằng repository trước khi kết luận entry stale.
- Không hardcode cấu trúc key nội bộ, không dùng `KEYS *` và không xóa index production bằng tay.
- Reconciliation phải theo batch, idempotent, có giới hạn và dựa trên schema/API đúng phiên bản.
- Theo dõi notification flags, listener subscription, event rate, callback errors, index size và cleanup metrics.
- Kiểm thử ACL restrictions, event expiration/delete, listener disconnect, failover và stale-index recovery bằng dữ liệu giả.
