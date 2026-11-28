# Cảnh báo lỗi lưu phiên, công việc dọn dẹp tồn đọng và bất thường tạo phiên

Spring Session lưu trạng thái phiên trong Redis hoặc JDBC để nhiều instance có thể khôi phục cùng HttpSession. Vì session thường tham gia vào xác thực và trải nghiệm người dùng, lỗi lưu phiên, cleanup hết hạn bị chậm hoặc tốc độ tạo session tăng bất thường đều có thể ảnh hưởng đến độ ổn định và an toàn của hệ thống.

Ba nhóm tín hiệu cần theo dõi riêng:

- **Lỗi lưu phiên:** repository không ghi được thay đổi, timeout, lỗi kết nối, lỗi serialization hoặc hết tài nguyên.
- **Dọn dẹp tồn đọng:** session đã hết hạn nhưng dữ liệu hoặc công việc xử lý expiration chưa được dọn đúng nhịp.
- **Tạo phiên bất thường:** ứng dụng tạo quá nhiều session mới, thường do endpoint vô tình gọi getSession(), cookie không được gửi lại, bot traffic hoặc cấu hình sai sau triển khai.

Không nên gom tất cả thành một cảnh báo chung. Cần đo riêng số lần tạo, tải, lưu, xóa, hết hạn; thời gian xử lý; tỷ lệ lỗi; dung lượng store; và độ trễ cleanup. Khi các tín hiệu được phân tách, đội vận hành có thể xác định sự cố nằm ở request path, Redis/JDBC, cookie, cấu hình hay tác vụ nền.

## 1. Vòng đời session và các điểm có thể phát sinh lỗi

Trong ứng dụng Servlet, Spring Session thay thế việc lưu HttpSession cục bộ thông qua SessionRepositoryFilter. Filter tải session khi request cần, theo dõi thay đổi và lưu phiên theo lifecycle của request/response.

    Browser gửi cookie
           |
           v
    SessionRepositoryFilter
           |
           v
    findById(sessionId)
           |
           v
    Controller đọc / cập nhật thuộc tính
           |
           v
    Repository save(session)
           |
           v
    Redis hoặc JDBC

Lỗi có thể xảy ra ở nhiều điểm:

1. Client không gửi cookie hoặc gửi cookie sai.
2. Repository không tìm thấy session.
3. Store không kết nối được hoặc phản hồi quá chậm.
4. Session attribute không serialize/deserialize được.
5. Lệnh ghi bị từ chối do hết memory hoặc quota.
6. JDBC transaction bị timeout, deadlock hoặc thiếu quyền.
7. Request kết thúc nhưng save chưa hoàn tất.
8. Cleanup hoặc expiration xảy ra đồng thời với request đang dùng session.

Một HTTP response thành công không phải lúc nào cũng chứng minh dữ liệu session đã được ghi bền vững. Cần quan sát lỗi ở repository/filter boundary và kiểm thử bằng request tiếp theo tải lại session từ store.

## 2. Phân biệt lỗi request với lỗi lưu session

Không phải mọi HTTP 401, 403 hoặc 500 đều là lỗi save session.

| Triệu chứng | Có thể liên quan đến | Kiểm tra |
|---|---|---|
| 401 sau login | Cookie không được gửi, session không được tải, SecurityContext không còn | Cookie, repository lookup, security chain |
| 403 | CSRF hoặc authorization | Security logs, CSRF token, quyền principal |
| 500 ở cuối response | Save session hoặc lỗi xử lý response | Exception chain, repository latency |
| Login thành công nhưng request sau mất đăng nhập | Save lỗi, cookie không được phát, namespace sai | Set-Cookie, store, namespace |
| Request chậm khi có session | Redis/JDBC latency hoặc serialization | Repository timer, connection pool, payload |
| Session hết hạn sớm | Timeout, clock, last access hoặc cleanup | Expiry metadata, TTL, node clock |

Đặt metric và log ở nơi có thể phân biệt operation load, save, delete và event. Nếu chỉ theo dõi HTTP status, sẽ khó biết lỗi phát sinh ở controller hay khi Spring Session filter lưu phiên ở cuối request.

## 3. Những nguyên nhân thường gặp khiến save thất bại

**Redis:**

- Redis không sẵn sàng, failover hoặc network chập chờn.
- Connection pool cạn hoặc command timeout.
- Redis từ chối ghi do maxmemory và policy noeviction.
- ACL không cho phép command hoặc key pattern cần thiết.
- Serialization lỗi vì thuộc tính session không tương thích.
- Redis latency tăng do workload khác hoặc hot key.
- Namespace hoặc cấu hình endpoint khác nhau giữa các node.

**JDBC:**

- Database không kết nối được hoặc pool hết connection.
- Transaction timeout, lock wait hoặc deadlock.
- Bảng session/attributes thiếu, sai schema hoặc sai kiểu cột.
- Runtime user thiếu quyền INSERT/UPDATE/DELETE.
- Index hoặc query plan không phù hợp khi bảng lớn.
- Serialization lỗi trước khi ghi attributes.
- Cleanup job cạnh tranh với request đang cập nhật.

**Ứng dụng:**

- Lưu object không serializable với serializer đang dùng.
- Thay đổi class session attribute không tương thích giữa các phiên bản.
- Session payload quá lớn.
- Nhiều request đồng thời ghi snapshot cũ.
- Request bị ngắt khi store đang ghi.
- Code bỏ qua exception hoặc phát response thành công trước khi thao tác lưu hoàn tất trong workflow tự quản lý.

## 4. Instrument repository operation

Đối với thao tác SessionRepository được gọi trực tiếp trong service, có thể đo thời gian và lỗi ngay tại service boundary:

~~~java
public void saveWorkflowSession(Session session) {
    Timer.Sample sample = Timer.start(meterRegistry);

    try {
        sessionRepository.save(session);
        meterRegistry.counter(
                "app.session.repository.operations",
                "operation", "save",
                "result", "success"
        ).increment();
    } catch (RuntimeException ex) {
        meterRegistry.counter(
                "app.session.repository.operations",
                "operation", "save",
                "result", "failure"
        ).increment();
        throw ex;
    } finally {
        sample.stop(Timer.builder("app.session.repository.duration")
                .tag("operation", "save")
                .register(meterRegistry));
    }
}
~~~

Đây là ví dụ cho code gọi repository trực tiếp. Với HttpSession thông thường, thao tác save có thể diễn ra bên trong SessionRepositoryFilter sau khi controller đã trả về. Khi đó, đo ở service không bao phủ toàn bộ đường ghi. Hãy instrument repository implementation/decorator hoặc filter boundary theo cách tương thích với cấu hình Spring Session của ứng dụng.

Không nuốt exception rồi trả thành công. Nếu repository không lưu được SecurityContext hoặc trạng thái bắt buộc, request cần đi theo chính sách lỗi đã định. Nếu session chỉ chứa dữ liệu phụ có thể tái tạo, ứng dụng có thể chọn fallback có chủ đích, nhưng phải phân biệt rõ với phiên xác thực.

## 5. Bộ metric tối thiểu

Nên có một bộ metric nhất quán giữa Redis và JDBC:

| Metric | Loại | Ý nghĩa |
|---|---|---|
| app.session.repository.operations | Counter | Số operation theo operation/result |
| app.session.repository.duration | Timer | Độ trễ load/save/delete |
| app.session.repository.errors | Counter | Lỗi theo store và nhóm nguyên nhân |
| app.session.created | Counter | Tốc độ tạo session |
| app.session.expired | Counter | Số event expiration quan sát được |
| app.session.deleted | Counter | Số session bị xóa |
| app.session.active.estimated | Gauge | Ước lượng session còn hiệu lực |
| app.session.cleanup.duration | Timer | Thời gian cleanup |
| app.session.cleanup.deleted | Counter | Số bản ghi/key được cleanup |
| app.session.cleanup.failures | Counter | Số lần cleanup thất bại |
| app.session.payload.bytes | Distribution summary | Kích thước payload nếu đo được |

Tên metric là quy ước ứng dụng, không khẳng định mọi metric này có sẵn tự động từ Spring Session. Cần tự instrument hoặc tích hợp exporter phù hợp.

Không dùng session ID, username, email, IP đầy đủ hoặc tenant ID tùy ý làm tag metric. Các tag có cardinality lớn sẽ làm hệ thống metrics tăng nhanh và có thể lộ dữ liệu. Dùng tag hữu hạn như store=redis/jdbc, operation=save, result=success/failure, error_class=timeout/serialization/connection.

## 6. Đo tỷ lệ lỗi và độ trễ, không chỉ đếm lỗi

Một lỗi đơn lẻ có thể là nhiễu tạm thời. Một tỷ lệ lỗi tăng liên tục hoặc p99 tăng cao thường quan trọng hơn tổng số lỗi.

Các phép đo nên có:

- Tỷ lệ save lỗi trên tổng số save.
- Tỷ lệ load miss so với tổng request cần session.
- p50/p95/p99 latency cho load, save và delete.
- Số timeout theo store.
- Số request login thất bại có liên quan repository.
- Thời gian từ khi session được tạo đến khi được tải lại thành công.
- Tỷ lệ retry và số lần retry trung bình.

Ví dụ công thức:

    save_error_ratio =
        save_failure_count / max(save_attempt_count, 1)

    save_p99 =
        percentile_99(save_duration)

Cảnh báo nên dựa trên cửa sổ thời gian và baseline của hệ thống. Không đặt ngưỡng tuyệt đối tùy tiện cho mọi môi trường; lưu lượng, số node, Redis topology và database capacity khác nhau.

## 7. Phân loại exception để cảnh báo có ích

Không nên chỉ đếm mọi RuntimeException như nhau. Phân nhóm nguyên nhân giúp runbook đưa ra hành động đúng:

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Connection | Redis/database unavailable | Kiểm tra network, endpoint, failover |
| Timeout | Command/query timeout | Kiểm tra latency, pool, tải |
| Capacity | Redis OOM, connection limit | Kiểm tra memory, quota, pool |
| Authorization | Redis ACL, database permission | Kiểm tra secret và quyền |
| Serialization | Invalid class/type, serializer mismatch | Kiểm tra session attributes và rollout |
| Schema | Missing table/column, SQL mismatch | Kiểm tra migration |
| Concurrency | Deadlock, stale update | Kiểm tra lock và request song song |
| Configuration | Namespace, table, cookie mismatch | So sánh cấu hình node |

Giữ exception cause trong log nội bộ với quyền truy cập phù hợp. Không ghi session object hoặc cookie vào stack trace bổ sung. Một số exception message có thể chứa key hoặc thông tin nhạy cảm; cần lọc trước khi đưa vào log tập trung.

## 8. Cảnh báo save failure theo mức độ

Có thể chia mức độ:

- **Warning:** lỗi lẻ tẻ dưới ngưỡng, retry hoặc request tiếp theo thành công.
- **Critical:** tỷ lệ save lỗi vượt ngưỡng trong nhiều cửa sổ liên tiếp.
- **Urgent:** login/session xác thực không thể persist, Redis/database unavailable hoặc pool cạn trên toàn cụm.

Một rule cần xét cả tỷ lệ và lưu lượng tối thiểu. Nếu chỉ có một request và một lỗi, tỷ lệ là 100% nhưng không nhất thiết cần page on-call. Nếu có hàng nghìn request và 2% save lỗi trong 10 phút, đó có thể là sự cố đáng báo động.

Cũng nên cảnh báo theo node. Nếu chỉ một node lỗi, khả năng cao là cấu hình lệch, network path hoặc pool cục bộ. Nếu mọi node lỗi cùng lúc, kiểm tra store dùng chung trước.

## 9. Log và trace không làm lộ session credential

Khi điều tra, cần liên kết log của request với repository operation. Có thể dùng:

- Trace ID hoặc correlation ID.
- Node ID và build version.
- Operation: load/save/delete.
- Store type: Redis/JDBC.
- Duration và result.
- Exception class đã phân loại.
- Session ID đã hash bằng cơ chế an toàn nếu thực sự cần đối chiếu.

Không ghi raw session ID, cookie header, SecurityContext, access token hoặc toàn bộ session attributes. Session ID là bearer credential; ai có nó có thể chiếm phiên nếu các biện pháp bảo vệ khác không ngăn được.

Tránh log payload để debug serialization trong production. Nếu phải tái hiện, dùng dữ liệu test đã làm sạch và môi trường riêng.

## 10. Cleanup: dữ liệu hết hạn và event expiration khác nhau

Cần phân biệt hai việc:

1. **Dữ liệu hết hạn được loại bỏ khỏi store:** Redis áp dụng TTL; JDBC cần cơ chế cleanup xóa các hàng đã hết hạn.
2. **Ứng dụng nhận được event expiration/deletion:** listener có thể cần sự kiện để thu hồi tài nguyên phụ hoặc cập nhật thống kê.

Hai việc này không đồng nghĩa. Một session có thể hết hạn logic nhưng event listener chưa xử lý; ngược lại, event có thể bị bỏ lỡ trong một khoảng thời gian do cấu hình notification hoặc consumer lỗi.

Không dùng số event nhận được làm nguồn duy nhất để kết luận số session hết hạn. Hãy có reconciliation định kỳ với store và metric cleanup.

## 11. Redis TTL và expiration

Spring Session Redis lưu session với expiration theo repository implementation. Redis có cơ chế hết hạn key dựa trên TTL, kết hợp kiểm tra chủ động và khi truy cập. Thời điểm key bị loại bỏ vật lý có thể không trùng chính xác với giây hết hạn.

Theo dõi các chỉ số Redis:

- used_memory và used_memory_rss.
- expired_keys.
- evicted_keys.
- keyspace_hits/keyspace_misses nếu phù hợp.
- Command latency và rejected writes.
- Connection count và replication lag.
- Số key trong namespace session nếu có thể lấy an toàn.

expired_keys là số key hết hạn trong Redis, không nhất thiết bằng số session hết hạn: một session có thể dùng nhiều key/metadata. Không diễn giải trực tiếp thành số người dùng đã logout.

Tránh quét toàn bộ keyspace liên tục để đếm session. Với cụm lớn, SCAN vẫn tạo tải và kết quả là ảnh chụp không nguyên tử. Dùng metric store, index được hỗ trợ hoặc công cụ kiểm tra giới hạn trong cửa sổ vận hành.

## 12. Redis keyspace notifications và session events

Spring Session Redis có thể phát session lifecycle event dựa trên Redis keyspace notifications. Để nhận expiration event, Redis cần bật loại notification phù hợp. Trên managed Redis, ứng dụng có thể không có quyền CONFIG; cấu hình notification cần được provision bởi người quản trị hoặc hạ tầng.

Khi dùng Spring Session Redis, kiểm tra:

- Keyspace notifications được bật theo yêu cầu phiên bản.
- Redis ACL cho phép các lệnh/subscription cần thiết.
- Listener container kết nối đúng Redis và namespace.
- Executor xử lý event có đủ thread.
- Listener không block lâu.
- Lỗi listener được ghi nhận và có cơ chế retry/reconciliation.

Redis expiration event không phải hàng đợi bền vững bảo đảm exactly-once. Event có thể đến trễ hoặc không được xử lý khi listener bị ngắt. Nếu nghiệp vụ cần bảo đảm thu hồi một tài nguyên phụ, hãy thiết kế idempotent handler và tác vụ đối soát định kỳ.

## 13. Theo dõi event listener và backlog

Nếu listener nhận session expiration/deletion để dọn dữ liệu phụ, cần đo:

- Số event nhận theo loại.
- Số event xử lý thành công/thất bại.
- Thời gian từ event nhận đến hoàn tất.
- Queue depth hoặc executor active/pending.
- Số lần retry.
- Số event bị bỏ qua do session/resource đã không còn.
- Tuổi của event lâu nhất đang chờ.

Handler nên nhanh và idempotent. Nếu cần gọi dịch vụ ngoài hoặc chạy tác vụ lâu, hãy ghi nhận công việc vào hàng đợi bền vững phù hợp thay vì giữ thread listener. Không dùng listener để thực hiện công việc có thể mất khi process restart mà không có cơ chế phục hồi.

SessionDeletedEvent và SessionExpiredEvent có thể được phát tùy repository và cấu hình. Không giả định mọi implementation phát event giống hệt nhau hoặc phát đúng một lần. Kiểm tra contract và thử nghiệm với store thực tế.

## 14. Cleanup JDBC và hàng hết hạn tồn đọng

Spring Session JDBC lưu metadata session trong bảng session và thuộc tính trong bảng attributes. Session hết hạn có thể vẫn còn hàng trong database cho đến khi cleanup task xóa chúng.

Các dấu hiệu backlog:

- Số hàng có expiry time đã qua tăng liên tục.
- Cleanup task chạy lâu hơn chu kỳ dự kiến.
- Số hàng xóa mỗi lần giảm bất thường trong khi hàng hết hạn tăng.
- Query cleanup bị lock hoặc timeout.
- Bảng/index tăng nhanh hơn dự kiến.
- Connection pool có nhiều request cleanup chờ.

Đối với schema mặc định, bảng thường có tên SPRING_SESSION và cột EXPIRY_TIME; tên bảng/cột có thể khác nếu ứng dụng tùy biến. Có thể dùng truy vấn chỉ đọc để ước lượng hàng hết hạn, điều chỉnh cú pháp theo database:

~~~sql
SELECT COUNT(*)
FROM SPRING_SESSION
WHERE EXPIRY_TIME < CURRENT_TIMESTAMP;
~~~

Đây là truy vấn minh họa. Kiểm tra kiểu dữ liệu timestamp, timezone và tên bảng thực tế trước khi dùng. Truy vấn count trên bảng lớn cũng có thể tốn tài nguyên; chạy theo lịch phù hợp, dùng index và không đưa nó vào mọi request.

## 15. Lịch cleanup và năng lực database

Spring Session JDBC có cơ chế cleanup session hết hạn; cách cấu hình lịch và tên property phụ thuộc phiên bản Spring Session/Spring Boot. Nếu ứng dụng tự quản lý cleanup, tránh vô tình chạy đồng thời nhiều scheduler trên tất cả instance mà không có điều phối.

Khi cleanup backlog tăng:

1. Xác nhận cleanup task thực sự được kích hoạt.
2. Kiểm tra exception, cron/schedule và lần chạy thành công gần nhất.
3. Kiểm tra query plan và index expiry.
4. Đo lock wait, deadlock, transaction duration và pool usage.
5. Kiểm tra lượng session mới tạo có tăng đột biến không.
6. Điều chỉnh batch size hoặc lịch chạy sau khi đo tải.
7. Tránh xóa hàng đang còn hiệu lực.
8. Kiểm tra quan hệ giữa bảng session và attributes để dữ liệu phụ được dọn đúng.
9. Chạy reconciliation sau khi khôi phục.
10. Ghi lại số hàng xóa và thời gian xử lý.

Không tăng tần suất cleanup một cách mù quáng. Job chạy quá dày có thể tranh chấp với request save và làm database chậm hơn. Nếu custom cleanup chạy trên nhiều node, dùng scheduler singleton/lock hoặc cơ chế phân công để tránh nhiều node cùng quét và xóa một tập dữ liệu.

## 16. Đo backlog cleanup

Một dashboard cleanup nên hiển thị:

| Chỉ số | Ý nghĩa |
|---|---|
| expired_rows_estimate | Ước lượng hàng đã hết hạn nhưng còn tồn tại |
| cleanup_last_success_timestamp | Lần cleanup thành công gần nhất |
| cleanup_duration | Thời gian mỗi lần chạy |
| cleanup_rows_deleted | Số hàng bị xóa mỗi lần |
| cleanup_failures | Số lần cleanup lỗi |
| oldest_expired_age | Tuổi của hàng hết hạn cũ nhất |
| cleanup_pool_wait | Thời gian chờ connection |
| cleanup_lock_wait | Thời gian chờ lock |

Không phải tất cả metric đều có sẵn; cần instrument job và query phù hợp. Với Redis, dùng TTL và expired/evicted metrics, đồng thời theo dõi event listener backlog riêng. Không cố quy đổi số key Redis thành số session nếu không biết cấu trúc key của phiên bản đang chạy.

## 17. Bất thường tạo session: cần đo creation rate

Tăng số session active có thể do nhiều người dùng mới, nhưng cũng có thể do mỗi request vô tình tạo session. Theo dõi:

- SessionCreatedEvent rate.
- Tỷ lệ session mới trên request.
- Session creation theo endpoint.
- Session anonymous so với session đã xác thực.
- Session được tạo nhưng không có request tiếp theo.
- Số session mới trên mỗi principal/device nếu có model tương ứng.
- Tỷ lệ session bị tạo rồi xóa trong thời gian ngắn.
- Cookie được phát và cookie quay lại ở request kế tiếp.

SessionCreatedEvent có thể hữu ích để đếm creation, nhưng event delivery phụ thuộc repository. Kết hợp với application instrumentation và store metrics; không coi event count là nguồn duy nhất.

## 18. Nguyên nhân phổ biến của session creation tăng bất thường

**Code tạo session vô tình:**

- Gọi request.getSession() ở filter/interceptor cho mọi request.
- Health check hoặc static resource tạo session.
- API vốn stateless nhưng code gọi getSession().
- Template/view hoặc CSRF flow tạo session khi render.
- Một service tạo session trước khi biết request có cần hay không.

**Cookie không được gửi lại:**

- Cookie Domain hoặc Path sai.
- Secure cookie được phát nhưng request kế tiếp dùng HTTP.
- SameSite không phù hợp với redirect/cross-site flow.
- Reverse proxy không chuyển forwarded headers đúng.
- Cookie name thay đổi giữa node.
- Browser chặn hoặc xóa cookie.
- Response song song ghi đè cookie mới bằng cookie cũ.

**Traffic bất thường:**

- Bot/crawler gửi request tạo session.
- Credential stuffing hoặc scan endpoint.
- Retry loop từ frontend hoặc client.
- Load test vượt thiết kế.
- Client không giữ cookie jar.

**Triển khai/configuration:**

- Namespace đổi khiến session cũ không được tìm thấy.
- Node dùng store hoặc database khác.
- Session cookie serializer khác nhau.
- Lỗi serialization làm session không khôi phục được, code tạo session mới.
- Rolling deployment trộn các phiên bản không tương thích.

## 19. Hạn chế tạo session không cần thiết

Nếu chỉ cần kiểm tra session hiện có, dùng getSession(false):

~~~java
@GetMapping("/account/status")
public ResponseEntity<String> status(HttpServletRequest request) {
    HttpSession session = request.getSession(false);

    if (session == null) {
        return ResponseEntity.status(401).body("No session");
    }

    return ResponseEntity.ok("Session exists");
}
~~~

getSession() không tham số tạo session mới nếu chưa có. Dùng nó trong filter chạy trên mọi request có thể tạo session cho cả health check, static asset và bot traffic.

Các biện pháp:

- Dùng getSession(false) khi chỉ đọc session hiện tại.
- Chỉ tạo session ở luồng thực sự cần state.
- Để health check và static resource stateless.
- Cấu hình Spring Security SessionCreationPolicy theo loại API.
- Rate-limit endpoint có thể tạo anonymous session.
- Tránh tạo session trước khi xác thực nếu không cần.
- Kiểm tra view, CSRF và OAuth/OIDC flow có yêu cầu session hay không.
- Đo creation rate theo endpoint và trạng thái authentication.

SessionCreationPolicy.STATELESS ảnh hưởng cách Spring Security dùng HttpSession cho SecurityContext; nó không cấm mọi code ứng dụng tự gọi request.getSession(). Cần rà cả filter, interceptor, controller và thư viện tích hợp.

## 20. Phân biệt tạo mới, đổi ID và đăng nhập

Không nên gộp session creation với session ID rotation. Sau xác thực, Spring Security có thể đổi ID để chống session fixation. Đây là lifecycle event khác với việc tạo một phiên hoàn toàn mới.

Khi xây dashboard, phân biệt:

- Session created.
- Session ID changed/rotated.
- Session authenticated.
- Session deleted.
- Session expired.
- Login success/failure.

Nếu chỉ đếm Set-Cookie hoặc số lần đổi ID, có thể báo động sai về session creation. Ngược lại, nếu không đếm rotation, có thể bỏ sót hoạt động xác thực bất thường.

Tùy repository và integration, event cụ thể có thể khác nhau. Kiểm tra các event class và cách phát event của phiên bản đang dùng trước khi dựa vào chúng.

## 21. Event listener cho lifecycle

Spring Session có các event như SessionCreatedEvent, SessionDeletedEvent và SessionExpiredEvent. Ứng dụng có thể lắng nghe để cập nhật metric hoặc dọn tài nguyên phụ:

~~~java
@Component
public class SessionLifecycleMetrics {

    private final MeterRegistry registry;

    public SessionLifecycleMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    @EventListener
    public void onCreated(SessionCreatedEvent event) {
        registry.counter(
                "app.session.lifecycle",
                "event", "created"
        ).increment();
    }

    @EventListener
    public void onDeleted(SessionDeletedEvent event) {
        registry.counter(
                "app.session.lifecycle",
                "event", "deleted"
        ).increment();
    }

    @EventListener
    public void onExpired(SessionExpiredEvent event) {
        registry.counter(
                "app.session.lifecycle",
                "event", "expired"
        ).increment();
    }
}
~~~

Đây là ví dụ minh họa; xác minh package và event support của phiên bản Spring Session cùng repository đang dùng. Với Redis, expiration event phụ thuộc keyspace notifications và listener configuration. Với repository khác, khả năng phát event có thể khác.

Listener chỉ nên tăng metric hoặc phát tín hiệu nhẹ. Không log session ID thô. Nếu cần dọn dữ liệu ngoài hệ thống, dùng handler idempotent và lưu công việc bền vững nếu không thể chấp nhận mất event.

## 22. Cảnh báo bất thường tạo session

Một số rule có thể áp dụng:

- Creation rate tăng nhiều lần so với baseline trong 5-10 phút.
- Session created/request ratio tăng mạnh ở endpoint không cần state.
- Anonymous session tăng nhưng login success không tăng.
- Session create rồi expire/delete rất nhanh tăng bất thường.
- Cookie return ratio giảm: cookie được phát nhưng không quay lại ở request sau.
- Session active estimate tăng nhanh hơn traffic và số người dùng.
- Một node tạo session nhiều hơn đáng kể các node khác.
- Namespace hoặc cookie configuration thay đổi đúng thời điểm spike bắt đầu.

Cảnh báo phải gắn với nguyên nhân có thể điều tra. Ví dụ creation spike trên /health gợi ý health check tạo session; spike trên endpoint login có thể liên quan bot hoặc flow xác thực. Không tự động chặn toàn bộ người dùng chỉ vì creation rate cao.

## 23. Runbook khi save session lỗi

Khi cảnh báo save failure:

1. Xác định phạm vi: một node, một AZ hay toàn bộ cụm.
2. Xem tỷ lệ lỗi, latency p95/p99 và thời điểm bắt đầu.
3. Phân loại exception: connection, timeout, capacity, ACL, serialization, schema hay deadlock.
4. Kiểm tra Redis health/memory/eviction hoặc JDBC pool/locks/schema.
5. So sánh cấu hình namespace, endpoint và secret giữa các node.
6. Kiểm tra thay đổi deployment gần nhất và session attribute class.
7. Xác minh login/session persistence bằng test account và cookie jar riêng.
8. Khôi phục store/pool hoặc rollback cấu hình nếu cần.
9. Không xóa toàn bộ session để che lỗi save.
10. Sau khi phục hồi, kiểm tra request mới tải lại session và theo dõi tỷ lệ lỗi trở về baseline.

Nếu lỗi chỉ xảy ra trên một node, đưa node đó ra khỏi traffic theo quy trình vận hành và so sánh cấu hình. Nếu mọi node cùng lỗi, ưu tiên kiểm tra dependency dùng chung.

## 24. Runbook khi cleanup tồn đọng

Khi backlog cleanup tăng:

1. Kiểm tra lần cleanup thành công gần nhất.
2. Xác định backlog thuộc JDBC expired rows hay Redis event/listener processing.
3. Kiểm tra job có đang chạy trùng trên nhiều node không.
4. Xem query duration, lock wait, pool saturation và số hàng xóa.
5. Kiểm tra index expiry và query plan.
6. Với Redis, kiểm tra TTL, expired_keys, notifications và listener health.
7. Điều chỉnh batch/interval sau khi đánh giá tải.
8. Không xóa hàng hoặc key chưa hết hạn.
9. Chạy reconciliation và đo backlog giảm.
10. Lưu lại nguyên nhân, thay đổi và thời điểm phục hồi.

Không chạy FLUSHDB/FLUSHALL để xử lý backlog session. Lệnh đó có thể xóa cả session hợp lệ và dữ liệu của workload khác dùng chung Redis.

## 25. Runbook khi creation rate bất thường

Khi số session mới tăng đột biến:

1. Xem creation rate theo node và endpoint.
2. Tách anonymous với authenticated session.
3. Kiểm tra cookie được phát và có quay lại request sau không.
4. Rà các filter/interceptor gọi getSession().
5. Kiểm tra health check, static resource, CSRF và OAuth flow.
6. Kiểm tra bot traffic, retry loop và rate-limit logs.
7. So sánh cookie name/domain/path/Secure/SameSite giữa node.
8. So sánh Redis namespace hoặc JDBC datasource/schema.
9. Kiểm tra deployment/serializer change gần thời điểm spike.
10. Giảm nguồn tạo session không cần thiết và xác nhận rate trở về baseline.

Nếu cookie không quay lại, mỗi request có thể tạo một session mới. Điều này làm store tăng nhanh và có thể tạo vòng lặp người dùng liên tục bị xem là chưa đăng nhập.

## 26. Kiểm thử cảnh báo và phục hồi

Nên có integration/operational test cho từng nhóm:

**Save failure**

- Redis unavailable hoặc timeout.
- Redis noeviction khi gần hết memory trong môi trường test.
- JDBC pool exhausted.
- SQL lock timeout/deadlock.
- Serialization failure.
- Xác nhận metric, log và alert được phát.
- Xác nhận lỗi không bị nuốt và request phản ánh đúng trạng thái.

**Cleanup backlog**

- Tạo session đã hết hạn trong môi trường test.
- Tạm dừng cleanup hoặc listener.
- Quan sát backlog tăng.
- Khôi phục job/listener.
- Xác nhận cleanup tiếp tục và không xóa session còn hiệu lực.
- Kiểm tra xử lý lặp không gây lỗi.

**Abnormal creation**

- Gửi request không cookie đến endpoint có gọi getSession().
- So sánh endpoint dùng getSession(false).
- Gửi nhiều request health check và xác nhận không tạo session.
- Mô phỏng cookie domain/path sai.
- Kiểm tra alert creation rate và endpoint attribution.

Không dùng production session hoặc credential thật trong test lỗi. Thực hiện chaos/failure injection ở môi trường cô lập và có giới hạn tác động.

## 27. Dashboard vận hành đề xuất

Một dashboard có thể chia thành bốn hàng:

| Khu vực | Biểu đồ/chỉ số |
|---|---|
| Save/load health | Operation rate, error ratio, p95/p99 latency, timeout |
| Lifecycle | Created, ID changed, authenticated, deleted, expired |
| Cleanup | Last success, duration, expired row estimate, listener queue/lag |
| Capacity | Redis memory/eviction, JDBC pool/table size, payload size, active session estimate |

Bộ lọc nên giới hạn ở environment, application, node, store type và operation. Không thêm session ID làm filter. Đặt annotation trên dashboard cho deploy, config change, Redis failover, database maintenance và cleanup schedule change.

## 28. Checklist trước khi đưa cảnh báo vào production

- [ ] Có metric riêng cho load, save, delete và lifecycle event.
- [ ] Có tỷ lệ lỗi và p95/p99 latency cho repository.
- [ ] Exception được phân loại mà không log session credential.
- [ ] Alert có cửa sổ thời gian, baseline và minimum traffic.
- [ ] Có phân biệt lỗi một node với lỗi store toàn cụm.
- [ ] Có giám sát Redis memory, eviction, TTL và connection.
- [ ] Có giám sát JDBC pool, lock, query latency và expired rows.
- [ ] Có metric lần cleanup thành công gần nhất và backlog ước lượng.
- [ ] Event listener có giám sát queue, lỗi và thời gian xử lý.
- [ ] Không coi Redis expiration event là nguồn exactly-once.
- [ ] Có creation rate theo endpoint và anonymous/authenticated.
- [ ] Health check và endpoint stateless không tạo session ngoài ý muốn.
- [ ] Cookie return ratio được theo dõi khi có spike.
- [ ] Có runbook save failure, cleanup backlog và creation spike.
- [ ] Có test failure injection trong môi trường riêng.
- [ ] Không dùng FLUSHDB/FLUSHALL như biện pháp cleanup.
- [ ] Không log raw session ID, cookie hoặc session attributes.

## Kết luận

Vận hành Spring Session cần quan sát riêng lỗi save, cleanup tồn đọng và tốc độ tạo session. Đo operation rate, error ratio, latency và phân loại exception để phát hiện Redis/JDBC connection, capacity, serialization hoặc schema failure. Với cleanup, phân biệt TTL vật lý, expired JDBC rows và event listener backlog; theo dõi lần chạy thành công, thời gian, số lượng xóa và reconciliation. Với session creation, đo theo endpoint, node và trạng thái authentication; kiểm tra getSession(), cookie return, bot traffic và thay đổi cấu hình. Event lifecycle hữu ích cho metrics và xử lý phụ nhưng không nên được xem là nguồn exactly-once. Một dashboard cùng runbook và bài test failure injection sẽ giúp phát hiện sớm sự cố mà không xóa nhầm các phiên còn hiệu lực.

## Tài liệu tham khảo

- Spring Session Reference: https://docs.spring.io/spring-session/reference/
- Spring Session Redis Configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session JDBC Configuration: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Session API and Events: https://docs.spring.io/spring-session/reference/api.html
- Spring Boot Actuator Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Micrometer Documentation: https://docs.micrometer.io/micrometer/reference/
- Redis Keyspace Notifications: https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/
