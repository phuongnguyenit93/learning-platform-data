# Discount expiration: thực thi thời hạn ưu đãi nhất quán và chống lạm dụng

## 1. Hết hạn ưu đãi là điều kiện nghiệp vụ, không phải hiệu ứng giao diện

Một mã giảm giá hết hạn lúc 10:00. Giao diện ẩn mã đúng giờ, nhưng API xác nhận đơn chỉ kiểm tra cờ `active`. Tác vụ chuyển cờ chạy chậm hai phút, nên người dùng vẫn gọi API trực tiếp để nhận giảm giá sau hạn.

Một hệ thống khác kiểm tra mã lúc thêm vào giỏ nhưng không kiểm tra khi xác nhận. Kẻ tấn công giữ giỏ nhiều ngày hoặc gửi lại request cũ để tiếp tục dùng ưu đãi. Ngược lại, nếu đã cam kết giữ ưu đãi trong một khoảng thanh toán, việc tự xóa giảm giá ngay khi chiến dịch kết thúc có thể làm số tiền thu khác số người dùng đã chấp nhận.

*Discount expiration* là quy tắc xác định lúc nào một ưu đãi còn được cấp, giữ chỗ, áp dụng hoặc tiếp tục xử lý. Thiết kế an toàn phải chỉ rõ mốc thời gian, nguồn đồng hồ, điểm quyết định và trạng thái của quyền lợi.

Trong bảo mật logic nghiệp vụ, mục tiêu là ngăn dùng mã ngoài thời hạn, kéo dài quyền lợi bằng retry hoặc giữ chỗ, đồng thời giữ đúng cam kết đã được tạo hợp lệ. Quy tắc thời gian cần kết hợp với quyền theo đối tượng, transaction, idempotency, ngân sách và state machine của đơn.

## 2. Phân biệt các thời hạn liên quan

Một giao dịch có thể chịu nhiều đồng hồ nghiệp vụ:

| Thời hạn | Câu hỏi được trả lời |
|---|---|
| Thời gian chiến dịch | Khi nào được cấp hoặc bắt đầu sử dụng ưu đãi? |
| Thời hạn mã cá nhân | Người được cấp mã có thể sử dụng đến lúc nào? |
| Thời hạn báo giá | Kết quả giá đã tính có thể được chấp nhận đến lúc nào? |
| Thời hạn giữ chỗ ưu đãi | Quyền lợi và phần ngân sách đã giữ có được bảo đảm đến lúc nào? |
| Thời hạn thanh toán đơn | Đơn đã xác nhận được phép chờ thanh toán bao lâu? |
| Hiệu lực quyền truy cập | Actor hiện tại có được thao tác đơn hoặc tài khoản đó không? |

Không dùng một trường `expires_at` chung rồi để mỗi endpoint hiểu khác nhau. Mã còn hạn không chứng minh quote còn hạn; reservation còn hạn không cho người khác sử dụng nó; chiến dịch hết hạn không tự sửa giá của đơn đã được chốt.

Nếu mã cá nhân và chiến dịch đều giới hạn thời gian cấp mới, miền hợp lệ thường là giao của các khoảng tương ứng:

```text
effective_start = max(campaign_start, personal_code_start)
effective_end   = min(campaign_end, personal_code_end)
```

Đây là mô hình các điều kiện cùng phải thỏa. Nếu sản phẩm có quyền lợi độc lập được phép tồn tại lâu hơn chiến dịch gốc, cần mô hình hóa nó như một cam kết riêng, không tùy tiện đổi phép `min` thành `max`.

## 3. Định nghĩa khoảng thời gian không mơ hồ

### 3.1. Dùng khoảng đầu đóng, cuối mở

Một quy ước dễ kiểm chứng là:

```text
starts_at <= decision_time < ends_at
```

Ưu đãi hợp lệ đúng tại `starts_at`, nhưng không hợp lệ đúng tại `ends_at`. Khoảng này thường được viết là `[starts_at, ends_at)`.

Ví dụ chiến dịch mở từ 09:00 đến trước 10:00 theo giờ Việt Nam:

| Thời điểm quyết định | Được cấp mới? |
|---|---|
| 08:59:59.999 | Không, chưa bắt đầu |
| 09:00:00.000 | Có, nếu các điều kiện khác thỏa |
| 09:59:59.999 | Có, nếu các điều kiện khác thỏa |
| 10:00:00.000 | Không, đã hết hạn |

Không dùng “23:59:59” để biểu diễn cuối ngày nếu hệ thống còn độ chính xác mili giây hoặc cao hơn. Cách đó tạo khoảng bị bỏ sót và hành vi khác nhau giữa các thành phần.

### 3.2. Ngày hết hạn cần có múi giờ

Nếu cấu hình nói “dùng hết ngày 22/11/2026 theo giờ Việt Nam”, có thể biểu diễn mốc cuối độc quyền là:

```text
2026-11-23T00:00:00+07:00
            tương đương
2026-11-22T17:00:00Z
```

Backend nên lưu các mốc tuyệt đối có thể so sánh chính xác, thường bằng UTC, đồng thời giữ múi giờ nghiệp vụ hoặc thông tin cấu hình cần để giải thích lịch.

Không parse một ngày không có múi giờ theo timezone mặc định của từng máy. Hai server có timezone khác nhau có thể cấp ưu đãi ở hai thời điểm hết hạn khác nhau.

Với khu vực có thay đổi giờ mùa, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần. Luồng cấu hình cần giải quyết rõ tình huống đó, thay vì ngầm chọn một offset bất kỳ. Một khoảng “hai ngày theo lịch” cũng không nhất thiết bằng một số giờ cố định ở mọi múi giờ.

### 3.3. Kiểm tra cấu hình ngay khi tạo

Các điều kiện cơ bản gồm:

- Thời điểm bắt đầu phải trước thời điểm kết thúc.
- Múi giờ và cách diễn giải ngày phải được xác định.
- Độ chính xác timestamp giữa API, ứng dụng và database phải đủ và nhất quán.
- Thời hạn mã cá nhân không được vô tình mở rộng giới hạn của chiến dịch.
- Giá trị thiếu phải có ý nghĩa được cấu hình rõ; không tự xem chuỗi rỗng hoặc parse lỗi là vô thời hạn.

Quyền thay đổi lịch chiến dịch là quyền quản trị nghiệp vụ. Client mua hàng không được tự gửi thời điểm hết hạn mới.

## 4. Chọn điểm quyết định và nguồn thời gian

### 4.1. “Đã gửi trước giờ hết hạn” chưa phải bằng chứng đủ

Người dùng bấm lúc 09:59:59 nhưng request đến backend sau 10:00. Hệ thống phải định nghĩa ưu đãi dựa trên lúc bấm, lúc tiếp nhận hay lúc quyết định giữ chỗ hoặc xác nhận.

Một lựa chọn dễ kiểm soát là dùng thời điểm quyết định ở backend có thẩm quyền. Không dùng `client_time`, timestamp trong local storage hoặc header tùy ý để quyết định mã còn hạn.

Nếu sản phẩm chấp nhận thời điểm tiếp nhận ở một cổng vào đáng tin cậy, cần ghi nhận mốc đó bền vững, gắn với request đã xác minh và quy định độ trễ xử lý. Không biến bất kỳ timestamp do bên gọi khai báo thành bằng chứng đã đến trước hạn.

Thông điệp nằm trong queue trước khi hết hạn nhưng được xử lý sau hạn cũng cần chính sách tương tự. Retry không được tự mang theo một thời điểm cũ để được coi là yêu cầu mới hợp lệ mãi mãi.

### 4.2. Đồng hồ phải có thẩm quyền

Chọn một nguồn thời gian cho quyết định có hiệu lực, chẳng hạn đồng hồ database tại thao tác giữ chỗ. Các server có thể dùng đồng hồ cục bộ để hiển thị hoặc cảnh báo, nhưng không được tùy ý kéo dài quyền lợi khi khác kết quả từ nguồn có thẩm quyền.

Cần vận hành đồng bộ đồng hồ, quan sát độ lệch và xử lý lỗi nguồn thời gian theo thiết kế. Không tự cộng một khoảng dung sai bí mật ở từng service vì sợ lệch đồng hồ; nếu có khoảng ân hạn, nó là chính sách nghiệp vụ phải được định nghĩa và lưu được.

Đồng hồ đơn điệu hữu ích để đo khoảng chờ trong một tiến trình, nhưng không thay thế mốc UTC lưu bền vững cho một chiến dịch đi qua nhiều máy và nhiều lần khởi động.

### 4.3. Minh họa predicate trong Java

Hàm sau chỉ biểu diễn điều kiện khoảng thời gian. `decisionTime` phải đến từ nguồn tin cậy đã chọn, không từ payload người mua.

```java
import java.time.Instant;
import java.util.Objects;

public final class DiscountWindow {
    public static boolean allowsNewUse(
        Instant startsAt,
        Instant endsAt,
        Instant decisionTime
    ) {
        Objects.requireNonNull(startsAt);
        Objects.requireNonNull(endsAt);
        Objects.requireNonNull(decisionTime);

        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("Invalid discount window");
        }

        return !decisionTime.isBefore(startsAt)
            && decisionTime.isBefore(endsAt);
    }
}
```

Hàm không kiểm tra quyền, ngân sách, trạng thái, giữ chỗ hay cạnh tranh dữ liệu. Kiểm tra Java trước transaction rồi ghi không điều kiện ở database vẫn có thể để request vượt qua mốc hết hạn hoặc làm vượt quota.

## 5. Hai chính sách hết hạn cần phân biệt

### 5.1. Chính sách chỉ chấp nhận trong cửa sổ chiến dịch

Theo chính sách này, bước xác nhận dùng ưu đãi phải xảy ra trước `campaign_end`. Việc thêm mã vào giỏ hoặc xem báo giá trước đó không tạo quyền dùng sau hạn.

Nếu có giữ chỗ ngắn để bảo vệ ngân sách, việc xác nhận vẫn phải thỏa cả thời hạn giữ chỗ lẫn cửa sổ chiến dịch. Có thể đặt thời hạn giữ chỗ không vượt quá mốc cuối chiến dịch.

Khi hết hạn trước lúc xác nhận, backend tính lại hoặc cung cấp báo giá mới theo luồng sản phẩm. Không tự tăng tiền thanh toán mà không xử lý việc người dùng chấp nhận nội dung mới theo chính sách.

### 5.2. Chính sách bảo đảm quyền lợi đã giữ chỗ

Theo chính sách này, một reservation hợp lệ được tạo trước hạn có thể được dùng để xác nhận đơn trong một khoảng ngắn sau khi chiến dịch kết thúc.

Ví dụ:

```text
Chiến dịch kết thúc:       10:00:00
Giữ chỗ được cấp lúc:      09:59:58
TTL giữ chỗ:               5 phút
Giới hạn ân hạn tuyệt đối:  campaign_end + 10 phút

reservation_end = min(09:59:58 + 5 phút, 10:00:00 + 10 phút)
                = 10:04:58
```

Một reservation như vậy có thể cho phép xác nhận lúc 10:02 theo chính sách, dù không được cấp reservation mới lúc đó. Đúng tại 10:04:58, reservation hết hiệu lực theo quy ước cuối mở.

Khoảng bảo đảm này phải được backend cấp, ràng buộc đúng đối tượng và giữ ngân sách tương ứng. Một dòng giảm giá trong giỏ không phải reservation.

### 5.3. Không trộn hai chính sách giữa các endpoint

Nếu endpoint tính giá dùng chính sách bảo đảm reservation nhưng endpoint xác nhận luôn yêu cầu chiến dịch còn trong cửa sổ, người dùng có thể bị mất cam kết vừa được cấp.

Ngược lại, nếu giao diện chỉ tính giá tham khảo nhưng backend coi mọi giỏ cũ là reservation được bảo đảm, kẻ tấn công có thể giữ giá giảm vô thời hạn.

Quote, reservation, xác nhận đơn và thông báo hiển thị phải dùng cùng chính sách và phiên bản. Không suy ra quyền dùng sau hạn chỉ từ chữ ký hợp lệ hoặc một `discount_amount` đã lưu ở client.

## 6. Mô hình trạng thái cho giữ chỗ và sử dụng

### 6.1. Tách trạng thái chiến dịch khỏi thời gian

Một chiến dịch có thể có trạng thái quản trị như `ENABLED`, `SUSPENDED` hoặc `CLOSED`. Điều kiện cấp mới thường kết hợp trạng thái cho phép với cửa sổ thời gian và các điều kiện khác.

Không để trạng thái `ENABLED` thay thế kiểm tra thời gian. Tác vụ nền chưa chạy không được mở rộng thời hạn. Tương tự, đã đến thời gian bắt đầu không có nghĩa chiến dịch bị tạm dừng trở thành được phép dùng.

### 6.2. Mô hình giữ chỗ trong bài

Ví dụ dùng quy trình:

```text
HELD -> REDEEMED
HELD -> RELEASED
HELD -> EXPIRED
```

Ý nghĩa:

- `HELD`: đã giữ lượt hoặc ngân sách, chưa xác nhận thành đơn.
- `REDEEMED`: đã xác nhận đơn với quyền lợi đó trong transaction; giá đơn đã được chốt.
- `RELEASED`: giữ chỗ được hủy có chủ đích trước xác nhận.
- `EXPIRED`: hết thời hạn mà chưa được xác nhận.

Trong mô hình này, tiêu thụ ưu đãi xảy ra khi xác nhận đơn, trước khi phát lệnh thanh toán ra ngoài. Sau đó trạng thái thanh toán thuộc vòng đời đơn, không còn là một reservation `HELD` chờ hết TTL.

Nếu hệ thống chọn chỉ tiêu thụ khi thanh toán thành công, cần state machine giữ chỗ và xử lý kết quả chưa biết khác. Không sao chép nguyên cơ chế thu hồi `HELD` của mô hình này vào một luồng đã gửi lệnh tiền nhưng chưa biết kết quả.

### 6.3. Dữ liệu cần giữ

| Thành phần | Dữ liệu trọng tâm |
|---|---|
| Chiến dịch/mã | Tenant, trạng thái, thời gian, phiên bản chính sách, quy tắc thu hồi |
| Reservation | ID, chiến dịch, người được hưởng, checkout attempt, trạng thái, thời điểm cấp và hết hạn |
| Ràng buộc giá | Snapshot hoặc fingerprint nội dung, số tiền và tiền tệ được giữ, điều kiện cần kiểm tra lại |
| Hạn mức | Lượt và ngân sách đã giữ, đã tiêu thụ theo phạm vi chiến dịch/người dùng |
| Redemption | Liên kết đơn và reservation, hiệu lực duy nhất, thời điểm quyết định |
| Audit | Cấp, xác nhận, từ chối, hết hạn, giải phóng và điều chỉnh quyền lợi |

Các ID phải liên kết đúng tenant và người được hưởng. Biết reservation ID không có nghĩa được dùng nó cho đơn khác hoặc tài khoản khác.

## 7. Cấp giữ chỗ trong transaction với thời gian có thẩm quyền

### 7.1. Kiểm tra rồi ghi sau là chưa đủ

Nếu backend kiểm tra mã lúc 09:59:59, chờ khóa hoặc xử lý lâu rồi ghi lúc 10:00:05, kết quả phụ thuộc điểm quyết định mà sản phẩm đã chọn. Không được tự khẳng định giao dịch hợp lệ đến lúc commit chỉ vì từng đọc thấy còn hạn.

Trong PostgreSQL, `CURRENT_TIMESTAMP` là thời điểm bắt đầu transaction; `statement_timestamp()` là thời điểm bắt đầu câu lệnh. Cả hai có thể nằm trước một khoảng chờ khóa dài.

Nếu muốn lấy thời gian thực sau khi đã lấy những khóa cần thiết, có thể đọc `clock_timestamp()` tại điểm đó và định nghĩa đó là thời điểm quyết định. Điều này không có nghĩa mọi chính sách đều bắt buộc dùng hàm ấy; điều cần thiết là ngữ nghĩa thời gian khớp yêu cầu.

### 7.2. Luồng SQL minh họa

Giả định mô hình có bảng `discount_campaigns` với số lượt và ngân sách, cùng bảng reservation. Các giá trị `verified_*` và `server_*` đã được backend xác minh. Named parameter được bind theo kiểu dữ liệu phù hợp, không nối chuỗi SQL từ request.

```sql
BEGIN;

SELECT id, starts_at, ends_at, policy_version, revocation_epoch
FROM discount_campaigns
WHERE tenant_id = :verified_tenant_id
  AND id = :verified_campaign_id
FOR UPDATE;

-- Nếu có quota theo người dùng hoặc mã cá nhân, lấy và khóa các dữ liệu
-- cần thiết theo cùng một thứ tự thống nhất trước khi quyết định.

SELECT clock_timestamp() AS decision_time;

-- :server_decision_time là kết quả đáng tin của bước trên.
-- Không lấy giá trị này từ timestamp do client gửi.

UPDATE discount_campaigns
SET reserved_uses = reserved_uses + 1,
    reserved_budget_minor = reserved_budget_minor + :server_discount_minor
WHERE tenant_id = :verified_tenant_id
  AND id = :verified_campaign_id
  AND status = 'ENABLED'
  AND starts_at <= :server_decision_time
  AND :server_decision_time < ends_at
  AND reserved_uses + redeemed_uses < max_uses
  AND :server_discount_minor
      <= budget_minor - reserved_budget_minor - redeemed_budget_minor
RETURNING policy_version, revocation_epoch;

-- Backend bắt buộc kiểm tra đúng một hàng, nếu không thì ROLLBACK và dừng.
-- Sau đó ghi reservation cùng deadline do server tính và dữ liệu ràng buộc.
-- Ghi idempotency, audit và outbox bắt buộc trong cùng cơ chế nhất quán.

COMMIT;
```

Đây là một phần của luồng, không phải schema và implementation đầy đủ. Cần kiểm tra mã cá nhân, quyền, mức tiền không âm, giới hạn số học, chống trùng và các quota khác. Chính sách dùng `NULL` để biểu diễn hạn mức không giới hạn cũng cần điều kiện riêng; ví dụ giả định các hạn mức đều có giá trị.

Điểm chấp nhận thời gian của ví dụ là lúc lấy `server_decision_time` sau các khóa cần thiết. Không hứa rằng quyền lợi còn được cấp mới đến lúc commit. Nếu sản phẩm chọn điểm khác, phải điều chỉnh giao thức cho khớp thay vì chỉ đổi tên trường thời gian.

### 7.3. Các đường ghi phải cùng giữ invariant

API trực tiếp, app di động, webhook, import và job nền không được dùng các điều kiện thời gian khác nhau. Một hàm dùng UTC chính xác trong controller không bảo vệ đường ghi bỏ qua controller.

Tài nguyên quota chưa có hàng cũng cần xử lý tạo hàng có chống trùng và khóa phù hợp. Không thể khóa một hàng không tồn tại rồi mặc định hai request không thể cùng tạo hạn mức riêng.

Giữ transaction ngắn, không gọi dịch vụ thanh toán chậm khi đang giữ khóa ngân sách. Lệnh ra ngoài cần được phối hợp sau khi trạng thái nội bộ đã được ghi bền vững theo thiết kế.

## 8. Xác nhận reservation và thu hồi hết hạn không được cùng thắng

### 8.1. Xác nhận đơn

Luồng xác nhận cần kiểm tra lại:

- Actor còn quyền với người mua, giỏ và reservation.
- Reservation đúng tenant, checkout attempt và nội dung giá được phép.
- Trạng thái vẫn là `HELD` và chưa hết `reservation_end` tại điểm quyết định.
- Chính sách thời hạn được thỏa: còn trong chiến dịch hoặc được phép dùng reservation đã bảo đảm sau hạn.
- Không có thu hồi bắt buộc hoặc điều kiện khác làm mất quyền lợi.
- Đơn được tạo từ đúng snapshot và việc chuyển hạn mức sang đã tiêu thụ được ghi nhất quán.

Trong cùng transaction, chuyển `HELD -> REDEEMED`, tạo redemption duy nhất, chốt đơn và cập nhật các counter liên quan. Nếu tạo đơn thất bại, rollback không được để reservation bị tiêu thụ dở.

### 8.2. Tác vụ thu hồi hết hạn

Job chỉ giải phóng một reservation còn `HELD` và đã hết hạn theo nguồn thời gian có thẩm quyền. Chuyển trạng thái và hoàn lại phần giữ ngân sách phải thuộc cùng transaction hoặc cơ chế nhất quán tương đương.

Hai worker cùng tìm thấy một reservation hết hạn không được cùng trừ counter. Chỉ worker thực sự chuyển được trạng thái mới được giải phóng phần giữ tương ứng; cần khóa, cập nhật có điều kiện hoặc khóa hiệu lực phù hợp.

Luồng xác nhận và luồng thu hồi phải phối hợp trên cùng dữ liệu và cùng thứ tự khóa. Kết quả không được chứa cả một đơn đã hưởng ưu đãi lẫn ngân sách đã được trả lại như thể ưu đãi chưa được dùng.

### 8.3. Trạng thái hết hạn không phụ thuộc job chạy đúng giờ

Nếu reservation đã qua deadline nhưng job chưa đổi `HELD` thành `EXPIRED`, endpoint xác nhận vẫn phải từ chối bằng điều kiện thời gian.

Job chậm có thể khiến ngân sách tạm bị giữ lâu hơn cần thiết, làm giảm khả năng cấp mới. Đó là vấn đề thu hồi và khả năng phục vụ; không nên sửa bằng cách cho xác nhận reservation quá hạn hoặc bỏ qua counter.

Có thể thu hồi theo yêu cầu khi cấp mới nếu thiết kế an toàn, nhưng vẫn cần xử lý trạng thái và counter đúng một lần.

### 8.4. Minh họa cuộc đua

```text
Reservation R hết hạn lúc 10:04:58.

Luồng A: muốn xác nhận R.
Luồng B: muốn thu hồi R vì hết hạn.

Cả hai phải theo giao thức khóa và thời điểm quyết định đã định.

Nếu A xác nhận hợp lệ và commit trước:
  R = REDEEMED; B không giải phóng như một reservation HELD.

Nếu B chuyển EXPIRED hợp lệ và commit trước:
  A không xác nhận R; không tạo đơn dựa trên quyền lợi đã thu hồi.
```

Không chỉ kiểm tra số tiền cuối. Cần đối chiếu cả trạng thái reservation, redemption, đơn và ngân sách sau commit.

## 9. Ngăn kéo dài ưu đãi bằng retry và giữ chỗ

### 9.1. Retry không được tạo deadline mới

Nếu request cấp reservation đã commit nhưng phản hồi bị mất, retry đúng idempotency key phải trả cùng reservation và cùng deadline. Không tính lại `expires_at = now + TTL` ở mỗi lần đọc hoặc retry.

Thời điểm cấp ban đầu cần được giữ ổn định. Nếu có gia hạn hợp lệ, đó là hành động riêng có điều kiện, giới hạn và audit; không phải tác dụng phụ của việc mở lại giỏ.

Cùng key nhưng khác giỏ, người mua hoặc nội dung nghiệp vụ phải bị xử lý theo hợp đồng xung đột. Idempotency key không thay thế quyền đọc kết quả hoặc quyền sử dụng mã.

### 9.2. Đổi key không mở thêm quyền lợi

Kẻ tấn công có thể đổi key liên tục để tạo nhiều reservation, chiếm hết ngân sách trước khi chiến dịch đóng hoặc giữ một mã dùng một lần trong nhiều checkout song song.

Cần các giới hạn nghiệp vụ đúng phạm vi, chẳng hạn số giữ chỗ đang hoạt động theo người mua, chiến dịch và checkout attempt do server quản lý. Khóa duy nhất và quota phải phản ánh phạm vi đó; một key tùy ý của client không phải danh tính kinh tế mới.

Với dữ liệu nhiều phiên bản giỏ, quy trình thay reservation cần giải phóng hoặc chuyển quyền lợi có kiểm soát. Không cho mỗi lần tăng version giỏ tạo thêm một hạn mức độc lập ngoài ý định sản phẩm.

### 9.3. Không tái sử dụng token cũ

Token có chữ ký có thể chứng minh nội dung do hệ thống cấp, nhưng vẫn cần kiểm tra người dùng, mục đích, thời hạn và trạng thái đã dùng hoặc thu hồi.

Không chấp nhận token sau hạn chỉ vì chữ ký đúng. Không cho timestamp cũ bên trong token biến thành quyền tạo reservation mới sau khi cửa sổ cấp mới kết thúc.

Nếu token đại diện một reservation được bảo đảm, phải liên kết được với trạng thái quyền lợi và giới hạn tương ứng. Token không tự giữ ngân sách hay ngăn hai request đồng thời dùng cùng quyền lợi.

## 10. Phân biệt hết hạn tự nhiên, tạm dừng và thu hồi

### 10.1. Hết hạn tự nhiên

Hết hạn tự nhiên thường chặn việc cấp mới. Có tiếp tục chấp nhận reservation đã cấp hay không phụ thuộc chính sách đã chọn.

Không sửa snapshot và số tiền của đơn đã được xác nhận chỉ vì thời gian chiến dịch trôi qua. Điều kiện cấp quyền lợi và vòng đời của một giao dịch đã chốt là hai vấn đề khác nhau.

### 10.2. Tạm dừng cấp mới

Tạm dừng có thể chỉ ngăn cấp reservation mới, còn các cam kết đã cấp vẫn được giữ. Nếu sản phẩm muốn chặn cả xác nhận đang chờ, phải ghi rõ phạm vi tác động.

Tiếp tục chiến dịch không tự kéo dài `ends_at` hoặc deadline reservation. Gia hạn lịch cần một thay đổi được phép, có phiên bản và audit.

### 10.3. Thu hồi bắt buộc

Khi phát hiện cấu hình giá sai hoặc lạm dụng, sản phẩm có thể có cơ chế thu hồi các reservation chưa xác nhận. Một cách triển khai là lưu thế hệ thu hồi, như `revocation_epoch`, trên chiến dịch và trên reservation lúc cấp.

Tại bước xác nhận, so khớp thế hệ theo chính sách. Khi thu hồi, tăng thế hệ hoặc tạo trạng thái vô hiệu hóa tương ứng và đồng bộ với luồng xác nhận. Đây chỉ là một cơ chế version; nó không tự sửa hoặc hoàn tiền cho đơn đã tạo.

Không dùng việc “thay phiên bản” một cách tùy tiện: cập nhật mô tả hiển thị có thể không cần hủy giữ chỗ, còn thu hồi bảo mật thì cần. Phải phân biệt thay đổi thông thường và thay đổi làm mất quyền lợi.

### 10.4. Nội dung giá thay đổi

Nếu người dùng đổi sản phẩm, số lượng hoặc bối cảnh ảnh hưởng giá, reservation cũ chỉ được dùng nếu chính sách cho phép và nội dung còn nằm trong phạm vi cam kết. Nếu không, cần tính lại và cấp quyền lợi phù hợp khi còn điều kiện.

Không để việc giữ chỗ trước hạn trở thành quyền áp cùng mức giảm cho một giỏ khác sau hạn. Fingerprint hoặc phiên bản phải được xác minh từ dữ liệu backend, không chỉ từ hash client khai báo.

## 11. Thanh toán, hủy và hoàn tiền sau khi chiến dịch kết thúc

### 11.1. Đơn đã xác nhận giữ nội dung tài chính của nó

Trong mô hình của bài, reservation trở thành `REDEEMED` khi xác nhận đơn. Lệnh thanh toán sau đó lấy số tiền và tiền tệ đã chốt của đơn, không tính lại ưu đãi theo thời gian chiến dịch hiện tại.

Đơn vẫn có deadline thanh toán riêng. Nếu thanh toán đến muộn sau khi đơn bị hủy, cần state machine xử lý kết quả ngoài thời hạn, thay vì khôi phục mã hoặc sửa tổng đơn tùy ý.

### 11.2. Timeout không chứng minh chưa dùng ưu đãi

Một API thanh toán timeout có thể đã tạo giao dịch thành công bên ngoài. Không giải phóng lượt hoặc ngân sách chỉ vì HTTP lỗi nếu đơn và hiệu lực tiền chưa được xác minh.

Trong mô hình này, job hết hạn reservation không được đụng vào `REDEEMED`. Nếu cần trả lại quyền lợi khi đơn hủy, đó là nghiệp vụ đảo hoặc điều chỉnh riêng, có điều kiện và hiệu lực duy nhất.

Nếu hệ thống vẫn giữ trạng thái `HELD` trong lúc gửi tiền ra ngoài, cần thêm mô hình bảo vệ cho kết quả chưa biết trước khi thu hồi. Không chỉ dựa vào TTL để trả ngân sách trong khi giao dịch vẫn có thể thành công.

### 11.3. Có khôi phục mã sau hủy hay không là chính sách riêng

Hủy đơn không nhất thiết khôi phục mọi loại lượt dùng. Có sản phẩm trả lại ngân sách nhưng không cho dùng lại mã cá nhân, hoặc chỉ cho dùng lại khi chiến dịch còn mở.

Nếu hoàn lại quyền lợi sau khi chiến dịch hết hạn, phải quyết định đó là khôi phục trong cửa sổ cũ hay phát một quyền lợi mới có thời hạn mới. Không đổi `ends_at` của mã gốc cho mọi người để xử lý một trường hợp cá nhân.

Ghi điều chỉnh có liên kết tới đơn và redemption gốc; chống lặp khi nhận nhiều sự kiện hủy hoặc hoàn.

### 11.4. Hoàn tiền dựa trên giao dịch gốc

Chiến dịch hết hạn không làm mất nghĩa vụ tính hoàn theo khoản thực thu và chính sách hoàn. Không lấy giá không giảm hiện tại để hoàn nhiều hơn số được phép, cũng không từ chối mọi khoản hoàn chỉ vì mã đã hết hạn.

Nếu hoàn một phần làm thay đổi điều kiện ưu đãi, áp dụng quy tắc điều chỉnh đã xác định và giữ lịch sử, phân bổ gốc. Không lặng lẽ chạy lại chính sách khuyến mãi hiện tại lên đơn cũ.

## 12. Audit, lỗi và kiểm thử tình huống tấn công logic

### 12.1. Bằng chứng thời gian cần lưu

Để giải thích một quyết định ở sát biên thời gian, nên lưu hoặc tham chiếu được:

- Chiến dịch, mã cá nhân, người hưởng, tenant và phạm vi nghiệp vụ.
- Các mốc bắt đầu, kết thúc có hiệu lực và phiên bản chính sách.
- Thời điểm quyết định cùng nguồn có thẩm quyền đã chọn.
- Thời điểm cấp, hết hạn reservation và quy tắc ân hạn nếu có.
- Snapshot, checkout attempt, đơn, redemption và idempotency liên quan.
- Lý do từ chối, giải phóng hoặc thu hồi và các version cần thiết.

Không chỉ ghi “coupon expired” mà thiếu mốc so sánh. Cũng không lưu token xác thực hoặc toàn bộ thông tin thanh toán chỉ để có log đầy đủ.

Phản hồi cho người dùng có thể yêu cầu xác nhận báo giá mới hoặc thử mã khác. Không tiết lộ mã cá nhân hoặc reservation của người khác khi họ chỉ biết một ID.

### 12.2. Ma trận thời gian và quyền

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Trước bắt đầu, đúng bắt đầu, ngay trước kết thúc, đúng kết thúc | Đúng quy ước `[start, end)` |
| Cấu hình theo ngày địa phương | Đổi đúng mốc cuối ngày sang thời điểm tuyệt đối |
| Client chỉnh đồng hồ hoặc gửi timestamp cũ | Không kéo dài hiệu lực |
| Server có timezone hiển thị khác | Không thay thời điểm cấp mới có thẩm quyền |
| Transaction mở trước hạn nhưng chờ khóa qua hạn | Quyết định đúng theo nguồn và điểm thời gian đã chọn |
| Job đóng chiến dịch chạy chậm | API vẫn chặn cấp mới ngoài hạn |
| Job thu hồi reservation chưa chạy | Không xác nhận reservation đã quá deadline |
| Mã cá nhân hết hạn sớm hơn chiến dịch | Áp dụng đúng giao các điều kiện thời gian |
| Reservation của người khác hoặc tenant khác | Bị kiểm tra quyền và phạm vi |
| Token đúng chữ ký nhưng hết hạn hoặc đã dùng | Không tạo quyền lợi mới |

### 12.3. Ma trận giữ chỗ và trạng thái

| Tình huống | Kết quả cần chứng minh |
|---|---|
| Cấp giữ chỗ trước hạn, xác nhận sau hạn | Đúng chính sách đã chọn, không tùy endpoint |
| Retry hoặc mở lại giỏ nhiều lần | Không tự dời deadline |
| Đổi key liên tục để giữ nhiều quyền lợi | Không vượt quota và giới hạn đang hoạt động |
| Đổi nội dung giỏ sau hạn | Không dùng reservation cho nội dung ngoài cam kết |
| Tạm dừng hoặc thu hồi chiến dịch | Tác động đúng phạm vi và version đã định |
| Hai worker cùng thu hồi một reservation | Giải phóng ngân sách tối đa một lần |
| Xác nhận cạnh tranh với thu hồi | Không vừa dùng ưu đãi vừa trả lại ngân sách |
| Lỗi tạo đơn sau khi chuyển reservation | Rollback không để hiệu lực dở |
| Hủy hoặc hoàn đến lặp | Không khôi phục lượt/ngân sách nhiều lần |
| Thanh toán chưa rõ kết quả | Không giải phóng quyền lợi đã tiêu thụ một cách mù quáng |

### 12.4. Kiểm thử có đồng hồ điều khiển và lịch cạnh tranh

Ở tầng hàm thời gian, dùng thời điểm hoặc `Clock` có thể điều khiển để kiểm tra sát biên. Không phụ thuộc thời gian thực rồi chờ đến đúng giờ chiến dịch mới chạy test.

Ở tầng transaction, dùng hai kết nối và điểm đồng bộ để tái hiện chờ khóa, xác nhận, thu hồi và retry. Chỉ đổi đồng hồ ứng dụng không kiểm tra được một quyết định do database làm nguồn thời gian.

Sau mỗi ca, kiểm tra reservation, redemption, đơn, counter ngân sách/lượt, audit và thông điệp liên quan. Mã HTTP đúng chưa chứng minh dữ liệu cuối đúng.

Các thuộc tính quan trọng:

```text
Cấp mới thành công -> thỏa cửa sổ và điều kiện tại điểm quyết định.

Xác nhận thành công -> có quyền lợi hợp lệ theo chính sách đã cấp.

Một reservation -> không vừa REDEEMED vừa được giải phóng như HELD.

Retry cùng hành động -> cùng hiệu lực, không thêm thời hạn.

Ngân sách và lượt -> không vượt giới hạn do các request đồng thời.

Chiến dịch hết hạn -> không tự sửa nội dung đơn đã chốt.
```

## 13. Những quyết định cần chốt khi triển khai

- Mốc đầu/cuối và múi giờ nghiệp vụ được diễn giải thế nào?
- Thời điểm quyết định là tiếp nhận, giữ chỗ, xác nhận đơn hay thanh toán?
- Nguồn đồng hồ nào có thẩm quyền, kể cả khi transaction chờ khóa?
- Có cam kết bảo đảm reservation sau hạn hay chỉ cho xác nhận trong cửa sổ chiến dịch?
- Deadline được cấp một lần hay có luồng gia hạn riêng, với giới hạn nào?
- Hết hạn, tạm dừng, thu hồi và thay đổi nội dung tác động khác nhau ra sao?
- Xác nhận, thu hồi, hủy và retry có cập nhật quyền lợi đúng một lần không?
- Khi tiền chưa rõ kết quả, quyền lợi được giữ và xác minh theo state machine nào?

Một chính sách hết hạn an toàn cần chặn đúng lúc, giữ đúng cam kết và giải phóng đúng quyền lợi. Khi thời gian, quyền, trạng thái và hiệu lực tài chính cùng được kiểm chứng, người dùng không thể kéo dài ưu đãi bằng cách giữ giỏ cũ, chỉnh timestamp hoặc phát lại yêu cầu.
