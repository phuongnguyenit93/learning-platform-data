# Clock skew handling

## 1. Vì sao lệch đồng hồ ảnh hưởng tới recovery?

Một yêu cầu khôi phục tài khoản có thể đi qua nhiều thành phần: API nhận yêu cầu, dịch vụ xác minh, nơi phát token, worker gửi email và dịch vụ thực thi đổi mật khẩu hoặc MFA. Các thành phần đó không nhất thiết nhìn thấy cùng một thời điểm.

**Clock skew** là sự chênh lệch giữa các đồng hồ được so sánh. **Clock drift** là xu hướng sai lệch tích lũy theo thời gian khi đồng hồ chạy nhanh hoặc chậm hơn nguồn tham chiếu. Việc hiệu chỉnh đồng hồ còn có thể làm thời gian tường nhảy tới hoặc lùi lại.

Trong `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, lệch đồng hồ có thể khiến token bị coi là chưa có hiệu lực, hết hạn sớm hoặc còn dùng được lâu hơn dự kiến. Nó cũng ảnh hưởng thời hạn bằng chứng, approval request, grant dùng một lần, thời gian chờ và việc đối chiếu các sự kiện bảo mật.

Mục tiêu không phải làm mọi request luôn thành công bất chấp thời gian không đáng tin. Hệ thống cần định nghĩa thời hạn rõ ràng, kiểm soát sai số và có cách tạm dừng thao tác nhạy cảm khi không đủ căn cứ xác nhận quyền còn hợp lệ.

Ví dụ: node phát token chạy nhanh 40 giây, node kiểm tra chạy chậm 20 giây. Một token được cấp thời hạn 5 phút có thể được chấp nhận tới 6 phút thực tế, dù verifier không chủ động cộng thêm khoảng dung sai nào.

## 2. Ba loại thời gian có vai trò khác nhau

| Loại | Dùng cho | Không nên dùng cho |
|---|---|---|
| Thời gian tuyệt đối, như UTC instant | Thời điểm cấp, hết hạn và đối chiếu giữa hệ thống | Suy ra chắc chắn thứ tự nhân quả chỉ từ timestamp |
| Đồng hồ đơn điệu trong tiến trình | Đo khoảng chờ, timeout hoặc thời lượng cục bộ | Lưu deadline để node khác hoặc tiến trình sau restart đọc lại |
| Thứ tự logic, version hoặc sequence | Kiểm soát phiên bản, quan hệ sự kiện và xử lý đồng thời | Chứng minh một quyền đã hết hạn theo thời gian thực |

Trong Java, `Instant` phù hợp để biểu diễn một thời điểm tuyệt đối. Nó không tự làm đồng hồ máy chủ chính xác. `System.nanoTime()` phù hợp đo chênh lệch trong cùng JVM theo hợp đồng của nó, nhưng giá trị gốc không phải Unix timestamp và không thể đem so giữa hai node.

Ví dụ đo thời lượng cục bộ:

```java
long started = System.nanoTime();
// Thực hiện một bước xử lý có giới hạn.
long elapsedNanos = System.nanoTime() - started;
```

Không lưu `started` vào cơ sở dữ liệu để một worker khác tính thời gian hết hạn. Cũng cần hiểu cách nền tảng xử lý sleep, suspend và giới hạn khoảng đo; đồng hồ đơn điệu không thay thế mọi chính sách deadline phân tán.

Sequence và case version hữu ích khi giải thích phê duyệt nào có trước một lần cấp quyền. Chúng không trả lời được token có còn trong thời hạn UTC hay không.

## 3. Định nghĩa cửa sổ hiệu lực và biên thời gian

Một quyền recovery có thể chứa hoặc tham chiếu các thời điểm:

```text
issued_at: quyền được phát hành lúc nào.
not_before: thời điểm sớm nhất được phép sử dụng, nếu có.
expires_at: thời điểm quyền không còn được chấp nhận.
consumed_at: thời điểm quyền đã được tiêu thụ thành công, nếu có.
```

Một quy tắc biên rõ ràng là cửa sổ nửa mở:

```text
not_before <= thời điểm kiểm tra < expires_at
```

Đúng bằng `expires_at` là đã hết hạn. Cần áp dụng nhất quán ở API, dịch vụ thực thi và nguồn dữ liệu có thẩm quyền, tránh một nơi dùng `<` còn nơi khác dùng `<=`.

Các timestamp phải có đơn vị và encoding rõ. Seconds, milliseconds và nanoseconds không thể hoán đổi. Một số nguyên được hiểu sai đơn vị có thể làm token hết hạn ngay hoặc tồn tại lâu hơn rất nhiều.

Không dùng `LocalDateTime` thiếu ngữ cảnh múi giờ để so thời hạn giữa các vùng. Lưu thời điểm theo mô hình UTC thống nhất; chỉ chuyển sang múi giờ của người dùng để hiển thị. Thay đổi múi giờ hiển thị không được làm thay đổi hiệu lực token.

Thời hạn được xác lập khi cấp quyền hoặc theo nguồn chính sách có thẩm quyền. Retry xác minh không được đặt lại `expires_at = now + TTL`, vì mỗi lần thử sẽ kéo dài quyền.

## 4. Dung sai có thể kéo dài quyền truy cập

Giả sử verifier đọc thời gian là `T_v`, còn hệ thống cho dung sai `L`. Một cách kiểm tra thường gặp là:

```text
not_before <= T_v + L
T_v < expires_at + L
```

Hai phép nới trên có tác động khác nhau: cho phép sớm hơn ở đầu cửa sổ và muộn hơn ở cuối cửa sổ. Không nên gom chúng thành một cấu hình “tolerance” mà không hiểu hậu quả.

Nếu issuer cấp TTL là `D`, sai số đồng hồ issuer là `e_i`, sai số verifier là `e_v`, thời điểm hết hiệu lực được verifier chấp nhận trong một mô hình đơn giản có thể tới:

```text
thời điểm cấp thực tế + D + e_i - e_v + L
```

Nếu biết cả hai sai số có trị tuyệt đối không vượt `B`, phần kéo dài có thể tới `2B + L`. Đây là kết quả dựa trên giả định có giới hạn sai số, không phải bảo đảm rằng đồng hồ thực tế luôn nằm trong giới hạn đó.

Ví dụ minh họa:

| Sự kiện | Thời gian thực | Đồng hồ liên quan |
|---|---|---|
| Cấp token | 12:00:00 | Issuer đọc 12:00:40 |
| Ghi thời điểm hết hạn với TTL 5 phút | 12:00:00 | `expires_at = 12:05:40` |
| Verifier chậm 20 giây | 12:06:00 | Verifier mới đọc 12:05:40 |

Với phép kiểm tra nghiêm ngặt không cộng leeway, verifier có thể chấp nhận trước 12:06:00 thực tế. Nếu còn cộng 15 giây ở cuối, giới hạn trong ví dụ dịch thêm tới 12:06:15.

Do đó, một TTL ngắn không tự tạo ra cửa sổ thực tế ngắn nếu sai số không được quản lý. Không đặt dung sai rất lớn chỉ để làm biến mất lỗi “token hết hạn”. Cần xác định ngân sách sai số phù hợp với loại quyền và tính cả khoảng dung sai vào thời gian rủi ro được chấp nhận.

## 5. Chọn nguồn thời gian có thẩm quyền

Một thiết kế cần nói rõ thành phần nào quyết định thời hạn của quyền và thành phần nào quyết định quyền đã được sử dụng.

Các lựa chọn có thể gồm:

- Một dịch vụ cấp và kiểm tra grant có nguồn thời gian được quản lý.
- Thời gian của cơ sở dữ liệu dùng tại điểm kiểm tra trạng thái và tiêu thụ grant.
- Các node đã đồng bộ trong giới hạn được giám sát, với chính sách sai số rõ ràng.

Không lấy thời gian client, header `Date` hoặc timestamp do người yêu cầu gửi làm đồng hồ quyết định recovery. Đồng hồ trên thiết bị người dùng có thể sai hoặc bị điều khiển.

Nguồn thời gian của cơ sở dữ liệu giúp giảm chênh lệch giữa node ứng dụng ở một điểm quyết định, nhưng không tự giải quyết đồng hồ database chạy sai, failover sang node có thời gian khác hoặc phục hồi dữ liệu cũ.

Nguồn có thẩm quyền cũng không nhất thiết là một hàm luôn trả “bây giờ” theo nghĩa mong muốn. Chẳng hạn trong PostgreSQL, `CURRENT_TIMESTAMP` gắn với thời điểm bắt đầu transaction, không phải đồng hồ thay đổi qua từng lệnh trong transaction. Nếu giữ transaction lâu, kiểm tra hết hạn bằng thời điểm cũ có thể không phù hợp. Cần chọn hàm và vị trí kiểm tra theo hợp đồng thực tế.

Không gọi dịch vụ thời gian bên ngoài cho mọi request mà bỏ qua rủi ro độ trễ, mất kết nối và tính tin cậy. Kiến trúc cần một cách vận hành thời gian có giới hạn và có phản ứng khi vượt giới hạn.

## 6. Đồng bộ và theo dõi sức khỏe đồng hồ

Đồng bộ thời gian là trách nhiệm vận hành cần được thiết kế cùng ứng dụng. Nên có nguồn tham chiếu được quản lý, theo dõi offset, trạng thái đồng bộ và các sự kiện hiệu chỉnh bất thường.

Các tín hiệu có ích:

- Độ lệch ước tính so với nguồn tham chiếu của hệ thống.
- Độ bất định của ước lượng và thời gian từ lần đồng bộ hợp lệ gần nhất.
- Đồng hồ nhảy lùi, nhảy tới hoặc thay đổi nhanh bất thường.
- Node mới khởi động, resume hoặc được phục hồi từ snapshot.
- Thay đổi trạng thái time synchronization sau failover hoặc sự cố mạng.

“Đã bật đồng bộ thời gian” không có nghĩa sai số luôn bằng không. Ứng dụng cần biết khi nào không còn đủ điều kiện tin vào giới hạn sai số mà chính sách đang giả định.

Không nên tự sửa đồng hồ production một cách tùy tiện trong luồng recovery. Khi thời gian không đủ tin cậy, có thể ngừng phát grant mới, chuyển quyết định tới nguồn có thẩm quyền khác đã được thiết kế hoặc tạm dừng thao tác nhạy cảm.

Một node có thể vẫn phục vụ nội dung không nhạy cảm trong khi chưa đủ điều kiện cấp quyền recovery. Chính sách khả dụng nên phân biệt theo hành động, thay vì dùng một chế độ “bỏ mọi kiểm tra thời gian” cho cả hệ thống.

## 7. Kiểm tra bảo thủ bằng một khoảng thời gian có giới hạn

Thay vì giả sử đồng hồ hiện tại chính xác tuyệt đối, hệ thống có thể biểu diễn thời gian thực ước tính nằm trong một khoảng:

```text
earliest <= thời gian thực hiện tại <= latest
```

Khoảng này chỉ có giá trị khi cơ chế vận hành thực sự hỗ trợ giới hạn đó. Không tự gán sai số bằng 0 để làm thuật toán đơn giản.

Nếu muốn chỉ chấp nhận khi toàn bộ khoảng nằm trong cửa sổ hiệu lực, có thể yêu cầu:

```text
earliest >= not_before
latest < expires_at
```

Khi khoảng chồng lên biên hết hạn, hệ thống không chắc quyền còn hiệu lực. Một phản ứng bảo thủ là không thực thi và yêu cầu kiểm tra lại qua nguồn đủ tin cậy, thay vì cộng thêm leeway không giới hạn.

Ví dụ, token hết hạn lúc 12:05:00:

| Khoảng thời gian ước tính | Kết luận theo mô hình bảo thủ |
|---|---|
| 12:04:40 đến 12:04:50 | Có thể đạt điều kiện thời gian nếu đã qua `not_before` |
| 12:04:55 đến 12:05:05 | Chưa đủ chắc chắn, vì chồng lên biên hết hạn |
| 12:05:00 đến 12:05:10 | Đã hết hạn |

Thiết kế này đánh đổi một phần khả dụng gần biên để tránh chấp nhận muộn theo giới hạn đã biết. Không phải mọi sản phẩm đều dùng cùng chiến lược; điều cần thiết là mô tả được mức rủi ro thay vì vô tình mở rộng thời hạn.

## 8. Minh họa bộ kiểm tra thời gian bằng Java

Ví dụ dưới chỉ phân loại điều kiện thời gian. Đầu vào phải là các claim đã được xác thực hoặc bản ghi server có thẩm quyền, cùng khoảng thời gian lấy từ cơ chế được tin cậy.

```java
import java.time.Instant;
import java.util.Objects;

public final class RecoveryTimeGate {
    public enum Result {
        ELIGIBLE_BY_TIME,
        NOT_YET_VALID,
        EXPIRED,
        TIME_UNCERTAIN,
        INVALID_WINDOW
    }

    public record TimeWindow(Instant earliest, Instant latest) {
        public TimeWindow {
            Objects.requireNonNull(earliest);
            Objects.requireNonNull(latest);
            if (latest.isBefore(earliest)) {
                throw new IllegalArgumentException("Invalid time estimate");
            }
        }
    }

    public Result check(Instant notBefore, Instant expiresAt, TimeWindow now) {
        Objects.requireNonNull(notBefore);
        Objects.requireNonNull(expiresAt);
        Objects.requireNonNull(now);

        if (!expiresAt.isAfter(notBefore)) {
            return Result.INVALID_WINDOW;
        }
        if (now.latest().isBefore(notBefore)) {
            return Result.NOT_YET_VALID;
        }
        if (now.earliest().isBefore(notBefore)) {
            return Result.TIME_UNCERTAIN;
        }
        if (!now.earliest().isBefore(expiresAt)) {
            return Result.EXPIRED;
        }
        if (!now.latest().isBefore(expiresAt)) {
            return Result.TIME_UNCERTAIN;
        }
        return Result.ELIGIBLE_BY_TIME;
    }
}
```

`ELIGIBLE_BY_TIME` không có nghĩa recovery được phép hoàn tất. Backend còn phải kiểm tra token đúng mục đích, chủ thể, tenant, case, trạng thái thu hồi và điều kiện dùng một lần.

Đoạn mã không tự tính độ bất định, không kiểm tra chữ ký và không đo sức khỏe đồng hồ. Đó là các trách nhiệm bên ngoài; một `TimeWindow` do client gửi không được dùng như nguồn thời gian tin cậy.

Cũng cần kiểm tra các ràng buộc khi cấp quyền: cửa sổ hợp lệ, TTL không vượt giới hạn chính sách và các thời điểm có quan hệ đúng. Việc verifier thấy `expires_at` ở tương lai không chứng minh issuer đã cấp đúng thời hạn cho loại quyền đó.

Nếu kiểm tra một claim `issued_at` nằm quá xa trong tương lai, dùng giới hạn sai số đã định và kết quả đã được xác thực. Đừng coi timestamp tùy ý trong một token chưa xác thực là bằng chứng đồng hồ của hệ thống đang sai.

## 9. Kiểm tra thời gian và dùng một lần phải nhất quán

Hai node có thể cùng thấy token còn hạn. Chúng vẫn không được dùng token hai lần. Clock skew handling không thay thế kiểm soát đồng thời và trạng thái tiêu thụ.

Một cách thiết kế là giữ grant tại nguồn dữ liệu có thẩm quyền, khóa bản ghi trước khi quyết định và kiểm tra thời gian trong vùng xử lý nhất quán. Ví dụ khái niệm với PostgreSQL:

```sql
BEGIN;

SELECT id, state, not_before, expires_at
FROM recovery_grant
WHERE tenant_id = :tenant_id
  AND id = :grant_id
FOR UPDATE;

WITH check_time AS MATERIALIZED (
    SELECT clock_timestamp() AS checked_at
)
UPDATE recovery_grant AS g
SET state = 'CONSUMED',
    consumed_at = check_time.checked_at
FROM check_time
WHERE g.tenant_id = :tenant_id
  AND g.id = :grant_id
  AND g.state = 'ACTIVE'
  AND g.not_before <= check_time.checked_at
  AND check_time.checked_at < g.expires_at
RETURNING g.id;

-- Chỉ tiếp tục khi đúng một grant được tiêu thụ.
-- Ghi thay đổi xác thực và audit liên quan trong cùng transaction phù hợp.
-- Có lỗi ở bước bắt buộc thì ROLLBACK, không báo đã hoàn tất.

COMMIT;
```

SQL chỉ minh họa thời gian và trạng thái. Luồng thật còn phải kiểm tra quyền, giá trị kiểm chứng token, scope, trạng thái case và chính sách. Không chạy cập nhật chỉ dựa trên grantId do người gọi gửi.

Việc lấy thời gian sau khi đã khóa giúp tránh dùng một thời điểm quá cũ trong khi chờ tranh chấp khóa. Transaction cần ngắn, không chờ email hoặc gọi dịch vụ bên ngoài trong lúc giữ khóa.

Phải định nghĩa **điểm quyết định hiệu lực**: ví dụ, thời điểm kiểm tra và tiêu thụ grant trong transaction. Commit có thể xảy ra sau điểm đó; không được mô tả hệ thống là bảo đảm mọi hiệu ứng bên ngoài hoàn tất trước `expires_at` nếu thiết kế không cung cấp bảo đảm đó.

Nếu thao tác được thực thi ở dịch vụ khác, không tiêu thụ token rồi chuyển một lệnh không có thời hạn qua hàng đợi vô hạn. Cần command hoặc capability có phạm vi, idempotency, điều kiện thực thi và kiểm tra cuối tại nơi có thẩm quyền.

## 10. Hàng đợi, cache và tác vụ hết hạn

Worker gửi email có thể nhận việc chậm hơn thời điểm tạo token. Thời hạn token không được bắt đầu lại từ lúc worker gửi hoặc từ lúc người dùng mở email, trừ khi đó là một quy trình cấp quyền mới được thiết kế rõ ràng.

Nếu token đã hết hạn trước khi gửi, không phát nội dung như thể token còn dùng được. Có thể bỏ gửi, ghi trạng thái phù hợp hoặc thực hiện quy trình cấp lại được phép. Retry không tự tạo token mới ở mỗi lần thử.

Job đánh dấu case hết hạn hoặc TTL của cache giúp dọn dữ liệu, nhưng không phải cổng bảo mật cuối. Scheduler có thể chạy muộn và cache có thể chưa hết hạn do đồng hồ hoặc cơ chế lưu trữ khác nhau. Nơi dùng quyền phải kiểm tra điều kiện hiện hành.

Ngược lại, một mục biến mất khỏi cache không nhất thiết chứng minh quyền đã được thu hồi trong mọi nơi. Trạng thái thu hồi và tiêu thụ cần có nguồn có thẩm quyền, không chỉ dựa vào sự tồn tại của một cache entry.

Không tính lại tuổi quyền bằng thời điểm nhận sự kiện nếu sự kiện đã đến trễ. Giữ thời điểm cấp gốc và ngữ nghĩa deadline; thời điểm chuyển giao chỉ là metadata vận hành.

## 11. TOTP và đồng hồ thiết bị người dùng

Một số luồng recovery dùng mã theo thời gian từ thiết bị đã đăng ký. Khi đó cần phân biệt lệch đồng hồ thiết bị với lệch đồng hồ giữa các server.

Cửa sổ chấp nhận mã phải do chính sách của phương thức xác thực quy định. Cho phép thêm nhiều bước thời gian có thể tăng số mã có thể được chấp nhận và mở rộng cơ hội thử; không mở vô hạn chỉ vì người dùng báo mã sai.

Việc xử lý cần kết hợp giới hạn thử, chống dùng lại khi thiết kế yêu cầu và kiểm tra thiết bị hoặc secret đang được đăng ký hợp lệ. Không tự đồng bộ một sai số rất lớn chỉ từ vài mã do người chưa được xác minh gửi.

Timestamp trên thiết bị không trở thành thời gian có thẩm quyền của backend. Có thể hướng dẫn người dùng kiểm tra cài đặt giờ tự động, nhưng không yêu cầu gửi secret MFA, OTP cho nhân viên hay backup code qua cuộc trò chuyện để “sửa đồng hồ”.

Dung sai TOTP và dung sai token recovery có ngữ nghĩa khác nhau. Không sao chép một cấu hình leeway chung sang mọi cơ chế xác thực.

## 12. Đồng hồ nhảy, restart, failover và restore

Nếu đồng hồ nhảy lùi, phép tính `now - issued_at` có thể âm. Không tự kẹp về 0 rồi cấp thêm nguyên TTL, vì điều đó có thể kéo dài quyền. Cần nhận diện trạng thái thời gian không đáng tin và áp dụng chính sách đã định.

Nếu đồng hồ nhảy tới, nhiều quyền có thể bị coi là hết hạn sớm. Khi đồng hồ được sửa lại, không tự khôi phục mọi quyền đã bị kết thúc như thể chưa từng có quyết định. Trạng thái nghiệp vụ và thời gian cần được đối chiếu, không chỉ kiểm tra lại một timestamp.

Sau restart, không dùng deadline từ đồng hồ đơn điệu của tiến trình cũ. Sau failover, cần xác nhận node mới đáp ứng các điều kiện thời gian trước khi cấp hoặc tiêu thụ quyền nhạy cảm.

Restore còn có rủi ro khác: trạng thái đã dùng hoặc thu hồi có thể bị lùi theo snapshot. Ngay cả khi giờ hiện tại đúng, token chưa hết hạn trong snapshot có thể đã được dùng ở trạng thái mới hơn. Cần đối chiếu mốc bảo mật và lịch sử có thẩm quyền; chỉ kiểm tra `expires_at` là chưa đủ.

Một mốc thời gian lớn nhất từng thấy có thể hỗ trợ phát hiện rollback trong một thiết kế cụ thể, nhưng không tự chứng minh thời gian thực. Mốc phải có nguồn tin cậy, được bảo vệ và không dễ bị timestamp giả làm nhảy tới tương lai.

## 13. Phản ứng khi không thể tin thời gian

Không nên biến sự cố đồng hồ thành kết luận rằng người dùng gian lận hoặc bằng chứng danh tính sai.

| Tình huống | Phản ứng phù hợp có thể dùng |
|---|---|
| Node lệch vượt giới hạn | Ngừng xử lý thao tác recovery nhạy cảm trên node đó |
| Khoảng thời gian chồng biên expiry | Kiểm tra lại qua nguồn đủ tin cậy hoặc không thực thi |
| Không đọc được nguồn trạng thái dùng một lần | Chờ hoặc từ chối thao tác có kiểm soát, không dùng cache cũ để cấp quyền |
| Token hết hạn rõ ràng | Hướng dẫn tuyến cấp lại được cho phép |
| Lỗi cấu hình đơn vị hoặc policy | Chặn cấp quyền mới và sửa cấu hình theo quy trình vận hành |

Nếu cần chuyển vùng hoặc chuyển node, chỉ chuyển tới nơi vẫn bảo đảm cùng trạng thái bảo mật và điều kiện thời gian. Không chọn một node “dễ chấp nhận hơn” bằng cách thử lần lượt tới khi có kết quả thành công.

Phản hồi người dùng nên phân biệt lỗi tạm thời với yêu cầu không còn hiệu lực trong mức thông tin được phép. Nội bộ có thể ghi lý do `TIME_SOURCE_UNHEALTHY` hoặc `TIME_BOUNDARY_UNCERTAIN`; bên ngoài không cần tiết lộ cấu hình thời gian chi tiết.

Khi tuyến recovery bị tạm dừng vì thời gian, các lựa chọn hỗ trợ tiếp theo vẫn phải giữ tiêu chuẩn xác minh. Nhân viên không được dùng sự cố này làm lý do bỏ qua MFA hoặc cấp grant thủ công không có hạn dùng.

## 14. Audit và quan sát hệ thống

Các trường có ích cho một quyết định thời gian có thể gồm:

```text
operation_reference / grant_reference
issuer_reference / verifier_reference
policy_version / time_policy_version
issued_at / not_before / expires_at
checked_at hoặc time_window_reference
estimated_uncertainty
time_source_health_reference
outcome / controlled_reason_code
case_version / consumption_reference
```

Không ghi token bản rõ hoặc OTP vào log để tiện so thời điểm. Grant reference và dữ liệu quyết định tối thiểu thường đủ để truy vết.

Các chỉ số đáng theo dõi gồm số request bị chặn vì thời gian không chắc chắn, tỷ lệ token có thời điểm cấp bất thường sau khi đã xác thực, offset theo node, độ trễ hàng đợi và số lần cấp lại do chậm gửi.

Một đợt tăng token hết hạn có thể do hàng đợi email chậm, không phải clock skew. Cần đối chiếu nhiều nguồn trước khi thay dung sai. Không tăng leeway chỉ để kéo một biểu đồ lỗi xuống.

Khi dựng timeline, lưu thời điểm xảy ra và thời điểm ghi nhận, đồng thời dùng quan hệ operation, revision và trạng thái. Không sắp timestamp rồi khẳng định chắc chắn một hành động đã được phê duyệt chỉ vì giờ hiển thị nhỏ hơn.

## 15. Tình huống xuyên suốt

Một token thay MFA được phát tại vùng A và sử dụng tại vùng B. Hệ thống dùng grant server-side, có thời hạn cố định và trạng thái tiêu thụ chung.

1. Issuer kiểm tra sức khỏe thời gian trước khi cấp, ghi `issued_at`, `expires_at`, case và scope vào nguồn có thẩm quyền.
2. Worker gửi thông báo trễ. Nó không kéo dài grant theo thời điểm gửi; nếu grant không còn đủ điều kiện gửi, xử lý theo policy cấp lại.
3. Vùng B xác thực request và token, rồi kiểm tra ngữ cảnh grant thay vì tin đồng hồ client.
4. Một node B có độ bất định vượt giới hạn nên không thực thi thay MFA. Request chỉ được xử lý qua tuyến khác nếu tuyến đó giữ đủ trạng thái và bảo đảm cần thiết.
5. Tại điểm tiêu thụ có thẩm quyền, hệ thống kiểm tra thời hạn cùng trạng thái dùng một lần trong ranh giới nhất quán.
6. Hai request cùng token không thể cùng thành công; request sau thấy quyền đã tiêu thụ, dù theo đồng hồ của nó token vẫn còn hạn.
7. Quyết định và thao tác hoàn tất được audit bằng tham chiếu, không log token.
8. Nếu sau đó restore một snapshot cũ, hệ thống không làm sống lại grant chỉ vì snapshot ghi trạng thái chưa dùng.

Khi người dùng gặp lỗi vì node không đủ tin cậy về thời gian, hướng dẫn tiếp tục qua kênh chính thức. Không yêu cầu họ đổi đồng hồ theo một giá trị bất kỳ hoặc gửi mã bí mật cho hỗ trợ.

## 16. Những lỗi thiết kế thường gặp

- **Tin thời gian client:** người gọi điều khiển điều kiện hiệu lực.
- **Cộng dung sai lớn ở mọi nơi:** vô tình kéo dài quyền recovery ngoài ngân sách rủi ro.
- **Đặt lại TTL khi retry hoặc gửi email:** mỗi lần xử lý làm quyền sống lâu hơn.
- **Dùng đồng hồ đơn điệu giữa các node:** so sánh các giá trị không có cùng gốc.
- **Dùng timestamp làm thứ tự quyết định duy nhất:** hiểu sai quan hệ giữa phê duyệt và thực thi.
- **Tin scheduler là cổng hết hạn:** job chạy muộn khiến quyền cũ vẫn được dùng.
- **Kiểm tra expiry trước khi chờ khóa lâu:** thao tác dựa trên thời điểm đã cũ.
- **Chỉ kiểm tra thời gian, bỏ trạng thái tiêu thụ:** hai node cùng dùng được một token.
- **Restore trạng thái cũ mà không đối chiếu thu hồi:** làm sống lại quyền đã dùng hoặc bị hủy.
- **Đổ lỗi cho người dùng khi nguồn giờ lỗi:** xử lý sai nguyên nhân và có thể dẫn tới bỏ kiểm soát thủ công.

Clock skew handling an toàn kết hợp nguồn thời gian có thẩm quyền, giới hạn sai số được giám sát, ngữ nghĩa thời hạn rõ và trạng thái recovery nhất quán. Điều kiện thời gian chỉ là một phần của quyền truy cập; nó phải được kiểm tra cùng scope, quyết định, thu hồi và dùng một lần tại nơi thực sự thực thi thay đổi bảo mật.
