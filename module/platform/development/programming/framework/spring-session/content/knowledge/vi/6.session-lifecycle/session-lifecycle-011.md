# Thu dọn dữ liệu liên quan khi sự kiện đến muộn hoặc không được hỗ trợ

Spring Session quản lý vòng đời phiên HTTP và có thể phát các sự kiện như tạo, xóa hoặc hết hạn phiên. Ứng dụng thường cần làm thêm việc khi một phiên kết thúc: xóa dữ liệu tạm, giải phóng tài nguyên gắn với phiên, hủy đăng ký nhận thông báo hoặc thu hồi các liên kết phụ. Tuy nhiên, sự kiện vòng đời có thể đến trễ, bị bỏ lỡ hoặc không được repository hỗ trợ đầy đủ. Vì vậy, hệ thống cần một chiến lược thu dọn có thể chạy lặp lại, có thể phục hồi và không phụ thuộc hoàn toàn vào một sự kiện duy nhất.

Trong module Spring Session, phiên có thể được lưu trong Redis hoặc JDBC để nhiều instance cùng truy cập. Các tài nguyên liên quan cũng có thể nằm ở nhiều nơi: cache, bảng nghiệp vụ, kho file tạm, hàng đợi, WebSocket hoặc dịch vụ bên ngoài. Bài học này trình bày cách quản lý các tài nguyên đó khi sự kiện kết thúc phiên không đến đúng thời điểm hoặc không có sẵn.

## 1. Dữ liệu phiên và dữ liệu liên quan có vòng đời khác nhau

Bản ghi phiên là dữ liệu Spring Session quản lý trong repository. Dữ liệu liên quan là phần ứng dụng tạo ra để phục vụ một phiên hoặc một thiết bị cụ thể. Ví dụ:

- Cache tạm lưu kết quả tìm kiếm của phiên.
- Giỏ hàng ẩn danh hoặc trạng thái quy trình nhiều bước.
- File tải lên tạm thời trước khi người dùng xác nhận.
- Kết nối WebSocket, subscription hoặc đăng ký nhận thông báo.
- Khóa phân tán hoặc lease ngắn hạn mà ứng dụng gắn với một phiên.
- Bản ghi theo dõi thiết bị, lần đăng nhập hoặc tác vụ đang chạy.

Không phải mọi dữ liệu của người dùng đều nên bị xóa khi một phiên kết thúc. Hồ sơ, đơn hàng đã xác nhận, hóa đơn, lịch sử giao dịch và các dữ liệu nghiệp vụ lâu dài thường thuộc về tài khoản hoặc nghiệp vụ. Chúng không nên bị xóa chỉ vì một thiết bị đăng xuất hoặc một session hết hạn.

Hãy phân loại dữ liệu theo phạm vi sở hữu:

| Phạm vi | Ví dụ | Khi phiên kết thúc |
|---|---|---|
| Thuộc phiên | Cache tạm, trạng thái wizard, file nháp theo session ID | Có thể xóa hoặc để TTL tự thu dọn |
| Thuộc thiết bị | Token thiết bị, thông tin trình duyệt được người dùng cho phép lưu | Xử lý theo chính sách thiết bị, có thể tồn tại qua nhiều phiên |
| Thuộc tài khoản | Hồ sơ, đơn hàng, quyền, lịch sử nghiệp vụ | Giữ theo vòng đời nghiệp vụ; không xóa theo sự kiện của một phiên |
| Tài nguyên thuê có thời hạn | Lock, lease, subscription tạm | Gia hạn, giải phóng hoặc để lease hết hạn theo cơ chế an toàn |

Quy tắc thiết kế quan trọng là gắn tài nguyên tạm với định danh phiên cụ thể. Khi cần thu dọn, ứng dụng có thể xóa mọi tài nguyên thuộc session ID đó mà không ảnh hưởng phiên khác của cùng người dùng.

## 2. Các sự kiện vòng đời trong Spring Session

Spring Session có các sự kiện vòng đời thường gặp:

| Sự kiện | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| **SessionCreatedEvent** | Một phiên mới được tạo | Ghi nhận thời điểm tạo, tạo metadata hoặc kiểm toán |
| **SessionDeletedEvent** | Phiên bị xóa chủ động, ví dụ ứng dụng invalidate phiên | Thu dọn tài nguyên khi người dùng đăng xuất hoặc phiên bị thu hồi |
| **SessionExpiredEvent** | Phiên hết hạn theo thời gian không hoạt động | Thu dọn dữ liệu tạm sau khi phiên hết hạn |
| **SessionDestroyedEvent** | Lớp sự kiện chung cho các trường hợp phiên bị hủy | Lắng nghe chung cho cả xóa và hết hạn |

**SessionDeletedEvent** và **SessionExpiredEvent** là các loại sự kiện hủy phiên trong hệ sinh thái Spring Session; có thể lắng nghe lớp chung **SessionDestroyedEvent** nếu logic thu dọn giống nhau. Tên, dữ liệu đi kèm và cách phát sự kiện cần được kiểm tra theo phiên bản Spring Session và repository đang dùng.

Ví dụ một listener tối giản:

~~~java
@Component
public class SessionLifecycleListener {

    private final SessionCleanupQueue cleanupQueue;

    public SessionLifecycleListener(SessionCleanupQueue cleanupQueue) {
        this.cleanupQueue = cleanupQueue;
    }

    @EventListener
    public void onSessionDestroyed(SessionDestroyedEvent event) {
        cleanupQueue.enqueue(event.getSessionId());
    }
}
~~~

Listener chỉ gửi session ID vào hàng đợi thu dọn. Công việc xóa cache, file hoặc gọi dịch vụ khác được thực hiện ở worker riêng. Cách này giúp không kéo dài request logout hoặc xử lý event trong thread đang nhận thông báo.

Không nên mặc định mọi repository đều phát đủ các sự kiện giống nhau. Khả năng phát sự kiện phụ thuộc loại repository, cấu hình và phiên bản. Đặc biệt, sự kiện hết hạn có thể phụ thuộc cơ chế thông báo hết hạn của kho dữ liệu. Hãy xác nhận tính năng này trong tài liệu và kiểm thử của implementation thực tế.

## 3. Vì sao sự kiện có thể đến muộn?

Thời điểm một phiên hết hạn về mặt logic và thời điểm ứng dụng nhận được sự kiện không nhất thiết trùng nhau.

Với Redis, việc hết TTL không có nghĩa một callback được gửi chính xác vào đúng mili giây phiên hết hạn. Redis phát sự kiện expiration theo cơ chế keyspace notification; thời điểm phát phụ thuộc cách Redis phát hiện và xử lý khóa hết hạn. Spring Session Redis cần cấu hình thông báo phù hợp để nhận các sự kiện liên quan. Nếu máy chủ Redis không bật loại thông báo cần thiết hoặc cấu hình repository không sử dụng event support, ứng dụng có thể không nhận được sự kiện như mong đợi.

Ngoài ra, Redis Pub/Sub có tính chất truyền thông báo tức thời. Nếu ứng dụng đang mất kết nối hoặc listener không hoạt động khi thông báo được phát, thông báo có thể bị mất. Không nên xem thông báo Pub/Sub như một hàng đợi bền vững có thể phát lại.

Với JDBC, việc dọn các phiên hết hạn thường gắn với tác vụ dọn dữ liệu hoặc truy vấn xóa theo thời điểm hết hạn. Một bản ghi được phát hiện và xóa trong lần quét sau có thể được xử lý muộn hơn thời điểm hết hạn thực tế. Tùy repository và phiên bản, việc xóa dữ liệu có thể không phát cùng loại event mà ứng dụng mong đợi.

Một số tình huống khác cũng gây trễ:

- Listener chạy chậm hoặc hàng đợi xử lý đang bị nghẽn.
- Instance nhận sự kiện khởi động lại hoặc mất kết nối đến broker.
- Dịch vụ dọn tài nguyên bên ngoài tạm thời không sẵn sàng.
- Nhiều request đồng thời khiến phiên được gia hạn trong khi tác vụ thu dọn đang được lên lịch.
- Sự kiện đến sau khi người dùng đã đăng nhập lại bằng một phiên mới.

Vì thế, event là tín hiệu để bắt đầu thu dọn. Nó không phải bằng chứng tuyệt đối rằng mọi tài nguyên liên quan đã được xóa, cũng không phải cơ chế kiểm soát quyền truy cập.

## 4. Tách thời điểm hết hạn khỏi thời điểm thu dọn

Giả sử một phiên có thời gian không hoạt động tối đa 30 phút. Khi hết thời hạn, repository xem phiên là hết hạn theo quy tắc của nó. Sự kiện có thể được phát sau đó, listener có thể xử lý tiếp sau một khoảng chờ, và dịch vụ lưu file có thể chỉ xóa file ở lần retry kế tiếp.

Do đó cần phân biệt ba mốc:

1. **Phiên hết hạn hoặc bị invalidate:** phiên không còn hợp lệ để ứng dụng tiếp tục sử dụng.
2. **Sự kiện được phát và tiếp nhận:** ứng dụng biết có một phiên cần được thu dọn.
3. **Thu dọn hoàn tất:** các tài nguyên liên quan đã được xóa hoặc chuyển sang trạng thái đã xử lý.

Không nên cho phép request truy cập chỉ vì tác vụ thu dọn chưa chạy. Xác thực và authorization phải kiểm tra trạng thái phiên hợp lệ theo cơ chế Spring Security/Spring Session. Thu dọn dữ liệu phụ có thể hoàn tất sau, nhưng quyền truy cập phiên phải bị thu hồi ngay theo luồng invalidate hoặc hết hạn mà repository hỗ trợ.

Ví dụ, người dùng đăng xuất. Ứng dụng vô hiệu hóa phiên hiện tại và xóa trạng thái xác thực. Nếu tác vụ xóa file nháp bị trễ vài phút, file đó không được phép trở thành dữ liệu có thể truy cập công khai. Endpoint tải file phải kiểm tra quyền sở hữu và trạng thái nghiệp vụ, hoặc file phải được lưu trong vùng riêng tư cho đến khi được xác nhận.

## 5. Thiết kế thu dọn theo session ID và có tính lặp lại

Một tác vụ thu dọn tốt phải có thể chạy nhiều lần mà kết quả cuối vẫn đúng. Đó là tính idempotent. Ví dụ, xóa cache theo session ID lần thứ hai không nên gây lỗi hoặc xóa dữ liệu của phiên khác.

Có thể thiết kế worker theo mô hình:

~~~java
@Component
public class SessionCleanupWorker {

    private final SessionResourceRepository resources;
    private final CleanupLedger ledger;

    public SessionCleanupWorker(
            SessionResourceRepository resources,
            CleanupLedger ledger) {
        this.resources = resources;
        this.ledger = ledger;
    }

    public void cleanup(String sessionId) {
        if (ledger.isCompleted(sessionId)) {
            return;
        }

        resources.deleteAllForSession(sessionId);
        ledger.markCompleted(sessionId);
    }
}
~~~

Đây là ví dụ khái niệm; trong hệ thống thật, việc đánh dấu và xóa cần xử lý lỗi và cạnh tranh giữa nhiều worker. Nếu worker bị dừng sau khi xóa tài nguyên nhưng trước khi đánh dấu hoàn tất, lần chạy tiếp theo sẽ xóa lại. Vì vậy, thao tác delete phải an toàn khi lặp lại.

Các nguyên tắc quan trọng:

- Dùng session ID làm khóa phạm vi thu dọn.
- Xóa theo điều kiện cụ thể, ví dụ **WHERE session_id = ?**, không xóa theo user ID nếu nghiệp vụ chỉ yêu cầu kết thúc một phiên.
- Không giả định tài nguyên chắc chắn còn tồn tại; delete không tìm thấy bản ghi vẫn có thể là thành công.
- Đánh dấu hoàn tất sau khi các thao tác bắt buộc đã thành công.
- Ghi lại lỗi và thử lại thay vì bỏ qua vĩnh viễn.
- Nếu nhiều worker có thể xử lý cùng event, dùng claim/lease hoặc cơ chế khóa để tránh công việc trùng lặp tốn kém.

Khi một người dùng có hai phiên trên laptop và điện thoại, sự kiện của phiên laptop chỉ nên thu dọn tài nguyên của phiên laptop. Nếu xóa cache theo user ID hoặc hủy mọi subscription của tài khoản, phiên điện thoại có thể bị ảnh hưởng ngoài ý muốn.

## 6. Đừng phụ thuộc vào thuộc tính của phiên sau khi phiên đã mất

Một lỗi thiết kế phổ biến là đợi SessionDestroyedEvent rồi mới đọc thuộc tính phiên để tìm tên file, mã tác vụ hoặc tài nguyên cần xóa. Khi sự kiện đến muộn, phiên có thể đã bị xóa khỏi repository. Một số event có thể mang theo thông tin phiên hoặc thuộc tính phiên tùy loại và implementation, nhưng không nên giả định điều đó luôn đúng.

Nếu cần dữ liệu để thu dọn, hãy ghi metadata liên kết trước khi phiên kết thúc. Ví dụ:

- Lưu quan hệ session ID → danh sách file tạm trong bảng metadata riêng.
- Đặt namespace cache theo session ID.
- Lưu ID của subscription hoặc tác vụ trong một registry có thời hạn.
- Lưu thời điểm hết hạn dự kiến và trạng thái cleanup trong bản ghi riêng.

Khi event đến, listener chỉ cần session ID để tra registry. Nếu event không đến, tác vụ quét định kỳ vẫn có thể tìm metadata đã quá hạn và thu dọn. Metadata không nên chứa bí mật xác thực hoặc session cookie.

Nếu nghiệp vụ cần xóa một tài nguyên bên ngoài mà không thể suy ra từ session ID, hãy lưu khóa tham chiếu của tài nguyên trong registry ngay khi tạo nó. Đừng trông chờ có thể phục hồi toàn bộ thông tin từ phiên đã bị xóa.

## 7. Dùng TTL để thu dọn tự động

TTL là lớp bảo vệ hữu ích cho dữ liệu tạm. Nếu một cache key hoặc file tạm có thời hạn, hệ thống lưu trữ có thể tự loại bỏ nó khi hết hạn mà không cần listener phải chạy đúng thời điểm.

Ví dụ với Redis, có thể đặt TTL cho dữ liệu phụ:

~~~text
session-resource:<session-id>:draft -> TTL 30 phút
session-resource:<session-id>:cache -> TTL 30 phút
~~~

Đây chỉ là cách minh họa namespace; cần dùng session ID đã được bảo vệ và không đưa ID vào log. TTL của tài nguyên phụ phải phù hợp với vòng đời thực tế của phiên.

Có một điểm cần chú ý: session timeout thường là thời gian không hoạt động. Khi người dùng tiếp tục hoạt động, phiên có thể được gia hạn. Nếu TTL của dữ liệu phụ chỉ được đặt một lần khi tạo phiên, dữ liệu phụ có thể hết hạn trong khi phiên vẫn còn sống. Ngược lại, nếu dữ liệu phụ được gia hạn vô hạn, nó có thể tồn tại lâu hơn phiên. Hãy chọn chính sách rõ ràng:

- Nếu dữ liệu phụ không cần tồn tại suốt phiên, dùng TTL ngắn độc lập.
- Nếu cần sống cùng phiên, cập nhật thời hạn của dữ liệu phụ theo hoạt động hoặc dùng registry và cơ chế đối soát.
- Nếu dữ liệu có giá trị cao hoặc cần audit, dùng bản ghi bền vững với trạng thái và thời hạn riêng, không chỉ dựa vào TTL cache.

TTL giảm nhu cầu cleanup tức thời nhưng không thay thế việc kiểm soát quyền truy cập. Một file đã hết TTL vẫn phải được bảo vệ trong thời gian chờ hệ thống xóa thực tế.

## 8. Tác vụ đối soát định kỳ khi event không có hoặc bị mất

Khi repository không hỗ trợ event phù hợp hoặc hạ tầng thông báo không đáng tin cậy, cần có một đường thu dọn độc lập. Một scheduled job có thể tìm metadata tài nguyên đã hết hạn rồi xóa theo lô.

Ví dụ bảng registry:

~~~sql
CREATE TABLE SESSION_RESOURCE (
    RESOURCE_ID VARCHAR(100) PRIMARY KEY,
    SESSION_ID VARCHAR(200) NOT NULL,
    RESOURCE_TYPE VARCHAR(40) NOT NULL,
    EXPIRES_AT TIMESTAMP NOT NULL,
    CLEANUP_STATUS VARCHAR(20) NOT NULL
);

CREATE INDEX IDX_SESSION_RESOURCE_EXPIRY
    ON SESSION_RESOURCE (CLEANUP_STATUS, EXPIRES_AT);
~~~

Tác vụ định kỳ chọn các bản ghi chưa hoàn tất có EXPIRES_AT nhỏ hơn thời điểm hiện tại, claim một nhóm bản ghi, xóa tài nguyên liên quan rồi đánh dấu hoàn tất. Cần giới hạn kích thước batch để tránh tạo tải đột biến. Với nhiều instance cùng chạy job, dùng khóa phân tán, FOR UPDATE SKIP LOCKED nếu cơ sở dữ liệu hỗ trợ, hoặc cơ chế claim có lease để tránh nhiều instance cùng xử lý một nhóm.

Không nhất thiết phải truy vấn toàn bộ session repository để tìm mọi phiên hết hạn. Có thể quản lý thời hạn của tài nguyên phụ trong registry riêng. Nếu cần xác minh phiên còn tồn tại, hãy dùng API phù hợp của repository và cân nhắc chi phí đọc; tránh quét toàn bộ kho phiên theo mỗi chu kỳ.

Một chiến lược thực tế thường kết hợp:
1. Event listener để bắt đầu thu dọn sớm khi nhận được thông báo.
2. TTL để tự xóa dữ liệu tạm có thể hết hạn độc lập.
3. Scheduled reconciliation để xử lý event bị mất, listener lỗi hoặc dữ liệu tồn đọng.
4. Retry queue để xử lý các dịch vụ bên ngoài đang tạm thời không sẵn sàng.

## 9. Hàng đợi bền vững, retry và xử lý trùng lặp

Nếu thu dọn chỉ gồm xóa một cache key, listener đồng bộ đơn giản có thể đủ. Nếu cần xóa file từ object storage, thu hồi subscription ở dịch vụ khác hoặc giải phóng tài nguyên quan trọng, không nên thực hiện toàn bộ công việc trong listener của event.

Một listener có thể ghi yêu cầu thu dọn vào hàng đợi bền vững hoặc bảng outbox. Worker độc lập đọc công việc, xử lý rồi đánh dấu trạng thái. Khi thao tác thất bại tạm thời, worker thử lại với backoff và giới hạn số lần thử. Khi vượt ngưỡng, công việc được chuyển sang dead-letter queue hoặc trạng thái cần can thiệp.

Luồng khái quát:

    SessionDeletedEvent / SessionExpiredEvent
                    |
                    v
             Event listener
                    |
                    v
          Ghi cleanup request bền vững
                    |
                    v
              Cleanup worker
                    |
             +------+------+
             |             |
           Thành công     Lỗi tạm thời
             |             |
             v             v
         Đánh dấu       Retry có backoff
         hoàn tất           |
                             v
                       Dead-letter / cảnh báo

Spring application event trong một process không tự động là hàng đợi bền vững. Nếu ứng dụng dừng sau khi nhận event nhưng trước khi hoàn tất cleanup, công việc có thể bị mất. Outbox hoặc broker bền vững giúp lưu yêu cầu để worker tiếp tục sau khi khởi động lại.

Mỗi yêu cầu cleanup nên có khóa idempotency, chẳng hạn session ID kết hợp loại tài nguyên hoặc mã tác vụ. Nếu một event được gửi hai lần, worker nhận diện yêu cầu đã hoàn tất và bỏ qua phần việc đã xong. Không đánh dấu hoàn tất trước khi tài nguyên bắt buộc được thu dọn.

## 10. Sự kiện đến muộn sau khi người dùng đăng nhập lại

Một tình huống dễ gây lỗi là người dùng đăng xuất trên thiết bị A rồi đăng nhập lại hoặc tiếp tục dùng thiết bị B. Sự kiện hủy phiên A có thể được xử lý sau khi phiên B đã hoạt động. Nếu listener xóa dữ liệu theo user ID, nó có thể vô tình xóa trạng thái của phiên mới.

Hãy giữ ranh giới:

- Sự kiện hủy một session ID chỉ thu dọn tài nguyên gắn với session ID đó.
- Nếu cần thu hồi toàn bộ phiên của tài khoản, đây là một thao tác nghiệp vụ riêng, phải xác định danh sách phiên cần thu hồi và thực hiện theo chính sách.
- Nếu tài nguyên dùng chung giữa nhiều phiên, chỉ xóa khi không còn phiên hoặc chủ thể nào cần dùng nó.
- Nếu ID có thể được thay mới sau đăng nhập để bảo vệ session fixation, cập nhật liên kết tài nguyên theo chính sách chuyển phiên rõ ràng.

Ví dụ, người dùng có một giỏ hàng gắn với tài khoản và hai session đang hoạt động. Đăng xuất một phiên không nên xóa giỏ hàng tài khoản. Nếu giỏ hàng là giỏ ẩn danh gắn riêng với session ID, chỉ dữ liệu của session đó được xử lý; việc hợp nhất vào tài khoản khi đăng nhập phải do logic nghiệp vụ đảm nhiệm.

Không dùng event cleanup làm cơ chế thu hồi quyền. Khi phiên cũ đã invalidate, request dùng cookie cũ phải bị từ chối theo trạng thái repository và cơ chế bảo mật, bất kể worker đã xóa file tạm hay chưa.

## 11. Khi repository không phát sự kiện: các phương án thay thế

Nếu implementation hoặc cấu hình không phát event hết hạn, có thể chọn một hoặc nhiều cách sau:

| Phương án | Khi phù hợp | Điểm cần lưu ý |
|---|---|---|
| TTL tại kho tài nguyên | Cache, dữ liệu tạm, file có thể hết hạn độc lập | TTL phải được đồng bộ với chính sách gia hạn phiên nếu cần |
| Cleanup khi logout | Người dùng chủ động đăng xuất | Không xử lý được trình duyệt đóng đột ngột hoặc phiên hết hạn tự nhiên |
| Cleanup lười khi truy cập | Dữ liệu có thể kiểm tra và xóa khi người dùng quay lại | Cần có một job đối soát để xử lý người dùng không quay lại |
| Scheduled reconciliation | Có metadata về tài nguyên và hạn dùng | Cần batch, claim và theo dõi retry |
| Database cascade hoặc job SQL | Tài nguyên phụ nằm trong cùng cơ sở dữ liệu | Chỉ dùng cascade khi quan hệ sở hữu và chính sách xóa thật sự phù hợp |
| Broker/outbox bền vững | Cleanup cần gọi nhiều dịch vụ hoặc không được mất yêu cầu | Cần idempotency, retry và dead-letter |

Không phải phương án nào cũng thay thế hoàn toàn event. Ví dụ, TTL rất tốt cho cache nhưng không thể tự gọi API để hủy subscription ở dịch vụ bên ngoài. Một job đối soát có thể phát hiện bản ghi hết hạn rồi tạo cleanup request cho dịch vụ đó.

Với Redis keyspace notifications, hãy xác nhận máy chủ cho phép các loại notification mà Spring Session cần. Một số môi trường quản trị Redis hạn chế CONFIG hoặc đặt notification ở chế độ tắt. Cấu hình tự động của Spring Session có thể có tùy chọn yêu cầu Boot cấu hình notification, bỏ qua cấu hình hoặc để quản trị viên tự thiết lập; tên và giá trị thuộc tính phụ thuộc phiên bản. Không giả định việc thêm module Redis là đủ để event expiration luôn xuất hiện.

## 12. An toàn khi xóa dữ liệu và xử lý lỗi

Cleanup thường chạy sau khi request ban đầu đã kết thúc, vì vậy worker phải tự xác minh phạm vi tài nguyên được phép xóa. Không nhận session ID tùy ý từ API công khai rồi xóa dữ liệu chỉ dựa trên giá trị đó.

Một số nguyên tắc an toàn:

- Chỉ listener nội bộ hoặc luồng quản trị tin cậy mới được tạo cleanup request.
- Xác minh session ID thuộc namespace và module của ứng dụng.
- Không ghi cookie hoặc session ID đầy đủ vào log; dùng mã tham chiếu đã băm hoặc rút gọn nếu cần đối chiếu.
- Giới hạn quyền của worker đối với Redis, database và object storage.
- Tránh xóa theo prefix quá rộng; giới hạn chính xác theo session ID và loại tài nguyên.
- Ghi audit về yêu cầu cleanup, trạng thái, số lần thử và kết quả.
- Nếu dữ liệu có yêu cầu lưu giữ pháp lý hoặc kiểm toán, dùng chính sách retention riêng thay vì xóa theo vòng đời phiên.

Nếu repository không sẵn sàng, request logout vẫn cần xử lý theo chính sách bảo mật. Tùy kiến trúc, việc invalidate có thể thất bại nếu không ghi/xóa được session store; ứng dụng phải có cách báo lỗi và ngăn xác nhận logout thành công sai sự thật. Khi cần thu hồi khẩn cấp, có thể bổ sung denylist hoặc trạng thái thu hồi bền vững theo tài khoản/session, nhưng cơ chế đó phải được kiểm tra trong mọi đường xác thực.

## 13. Kiểm thử sự kiện trễ, bị mất và lặp lại

Một bài kiểm thử chỉ xác nhận listener được gọi một lần là chưa đủ. Hãy kiểm thử các tình huống thực tế:

1. Phát SessionDeletedEvent cho một session và xác nhận tài nguyên của đúng session được xóa.
2. Phát SessionExpiredEvent trễ sau thời điểm hết hạn và xác nhận cleanup vẫn thành công.
3. Phát cùng event hai lần và xác nhận thao tác idempotent.
4. Giả lập worker lỗi sau khi xóa một phần tài nguyên, chạy lại và xác nhận có thể hoàn tất.
5. Tắt listener hoặc ngắt kết nối nhận event, sau đó chạy scheduled reconciliation và xác nhận tài nguyên tồn đọng được thu dọn.
6. Tạo hai session cho cùng một user, phát event cho session thứ nhất và xác nhận session thứ hai vẫn còn tài nguyên.
7. Tạo metadata thiếu hoặc tài nguyên đã bị xóa trước đó và xác nhận worker xử lý an toàn.
8. Giả lập Redis không phát keyspace expiration event hoặc JDBC chỉ dọn theo batch để xác nhận đường fallback hoạt động.
9. Kiểm tra rằng request dùng session đã invalidate bị từ chối ngay cả khi cleanup tài nguyên phụ còn đang chờ.
10. Kiểm tra retry, backoff, dead-letter và cảnh báo khi dịch vụ ngoài không sẵn sàng lâu dài.

Đối với Redis, nên có kiểm thử tích hợp với cấu hình notification tương tự môi trường triển khai. Với JDBC, kiểm thử truy vấn cleanup, chỉ mục theo expiry và xử lý nhiều worker chạy song song. Các bài kiểm thử này giúp phát hiện giả định sai về thời điểm event hoặc khả năng phát event của repository.

## 14. Quan sát và vận hành cleanup

Thu dọn dữ liệu là một luồng nền nên cần metric và log có cấu trúc. Những số liệu hữu ích gồm:

- Số event tạo, xóa và hết hạn được nhận theo loại.
- Độ trễ từ thời điểm hết hạn dự kiến đến khi cleanup hoàn tất.
- Số yêu cầu đang chờ, đang chạy, retry và dead-letter.
- Số tài nguyên đã xóa và số tài nguyên không còn tồn tại.
- Số lỗi theo dịch vụ đích, loại tài nguyên và nguyên nhân.
- Tuổi của bản ghi cleanup cũ nhất chưa hoàn tất.

Không ghi session ID thô vào log. Dùng một mã tương quan đã băm hoặc một cleanup request ID để nối các bước. Cảnh báo khi backlog tăng liên tục, thời gian cleanup vượt SLA hoặc số lượng tài nguyên hết hạn tồn đọng tăng bất thường.

Có thể đặt ngưỡng vận hành, ví dụ cảnh báo khi bản ghi cleanup cũ nhất tồn tại quá lâu hoặc số lần retry vượt giới hạn. Ngưỡng cụ thể phụ thuộc khối lượng, mức độ quan trọng của tài nguyên và khả năng của kho lưu trữ.

## Kết luận

Sự kiện vòng đời của Spring Session giúp ứng dụng bắt đầu thu dọn tài nguyên khi phiên bị xóa hoặc hết hạn, nhưng thời điểm và khả năng phát sự kiện phụ thuộc repository, cấu hình và hạ tầng. Redis expiration notification có thể đến trễ hoặc bị mất khi listener không kết nối; JDBC có thể phát hiện phiên hết hạn qua tác vụ dọn dữ liệu theo chu kỳ. Vì vậy, hãy gắn tài nguyên phụ với session ID, lưu metadata cần thiết trước khi phiên biến mất, thiết kế cleanup idempotent, dùng TTL cho dữ liệu tạm và có scheduled reconciliation hoặc hàng đợi bền vững làm đường phục hồi. Giữ quyền truy cập phụ thuộc trạng thái phiên hợp lệ, còn cleanup dữ liệu phụ có thể hoàn tất theo cơ chế eventual consistency an toàn.
