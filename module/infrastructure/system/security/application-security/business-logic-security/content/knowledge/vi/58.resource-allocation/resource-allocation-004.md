# Allocation expiration: Hết hạn giữ tài nguyên an toàn

## 1. Vấn đề nghiệp vụ cần bảo vệ

**Allocation expiration** là cơ chế kết thúc quyền giữ hoặc sử dụng tài nguyên khi đến một thời điểm do hệ thống quy định. Trong bài này, allocation chủ yếu là **lượt giữ tài nguyên tạm thời**: giữ ghế, giữ hàng, giữ một suất tham gia hoặc giữ một phần quota trong lúc người dùng hoàn tất quy trình.

Ví dụ, một cửa hàng cho khách giữ hai sản phẩm trong năm phút để thanh toán. Khi hết năm phút, khách không còn quyền xác nhận lượt giữ đó; tài nguyên cần được thu hồi để người khác sử dụng. Nếu hệ thống chỉ ẩn nút thanh toán hoặc chờ một tác vụ định kỳ xóa bản ghi, khách vẫn có thể gọi API trực tiếp, gửi lại yêu cầu cũ hoặc lợi dụng thời gian giữa các lần quét.

Trong bảo mật logic nghiệp vụ, câu hỏi quan trọng là:

> Khi lượt giữ hết hạn, mọi thao tác nào phải mất hiệu lực, ai được phép thực hiện chúng, và bằng cách nào hệ thống thu hồi đúng một lần mà không cấp vượt tài nguyên?

Các nguyên tắc này cũng áp dụng cho lease của máy chạy tác vụ hoặc quyền truy cập có thời hạn. Tuy nhiên, việc chặn một tiến trình đang chạy ở hệ thống khác cần cơ chế bổ sung; đổi trạng thái trong cơ sở dữ liệu chưa tự động thu hồi được mọi tác động bên ngoài.

## 2. Tách ba khái niệm thời gian

Một thiết kế dễ kiểm chứng phải phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Hạn hiệu lực | Thời điểm lượt giữ không còn được phép xác nhận | `expires_at = 10:05:00Z` |
| Thời điểm quyết định | Thời gian máy chủ đọc để quyết định thao tác trong transaction | API lấy thời gian sau khi đã khóa dữ liệu cần thiết |
| Thời điểm thu hồi | Thời điểm transaction chuyển sang `EXPIRED` và trả tài nguyên vào pool | Worker thực hiện lúc `10:05:03Z` |

Quy ước của bài:

~~~text
Lượt giữ có hiệu lực để xác nhận khi:
state == HELD AND decision_at < expires_at

Đến đúng expires_at:
decision_at >= expires_at  =>  không được xác nhận
~~~

Khoảng hiệu lực có đầu cuối mở: đến đúng hạn là hết hiệu lực. Trạng thái `HELD` trong cơ sở dữ liệu không đủ để chứng minh lượt giữ còn hạn, bởi worker có thể chưa kịp thu hồi.

Trong mô hình minh họa, quyết định hợp lệ được đưa ra sau khi đã lấy đủ khóa và transaction giữ các khóa đó đến khi commit. Một xác nhận được quyết định trước hạn có thể commit sau hạn nếu transaction mất thêm thời gian. Đây là hợp đồng cần nêu rõ. Nếu nghiệp vụ yêu cầu hoàn tất trước hạn theo một mốc khác, phải thiết kế tiêu chí riêng; không thể mặc nhiên coi thời điểm nhận HTTP, thời điểm quyết định và thời điểm commit là một.

Không lấy thời gian từ trình duyệt hoặc trường `client_now` làm căn cứ. Thời gian phía khách chỉ phục vụ hiển thị và trải nghiệm.

## 3. Tình huống lạm dụng điển hình

### 3.1. Xác nhận trong khoảng trống trước lần quét tiếp theo

Lượt giữ hết hạn lúc 10:05:00, nhưng worker chỉ chạy lúc 10:05:30. Nếu API kiểm tra mỗi `state == HELD`, khách có thêm ba mươi giây ngoài chính sách.

Biện pháp: mọi đường xác nhận phải kiểm tra cả trạng thái và hạn bằng thời gian có thẩm quyền.

### 3.2. Gia hạn vô hạn để chiếm tài nguyên

Khách gọi `renew` liên tục, hoặc đổi tài khoản để tạo lượt giữ mới. Dù mỗi request hợp lệ về cú pháp, những người khác vẫn không thể mua hàng hoặc nhận quota.

Biện pháp: giới hạn tổng tuổi thọ lượt giữ, số lượt giữ, lượng tài nguyên và ngân sách gia hạn; đánh giá cả hành vi tạo lại sau khi hết hạn.

### 3.3. Hai worker cùng thu hồi

Hai worker cùng nhìn thấy một lượt giữ đã hết hạn. Cả hai cộng lại số lượng vào kho, làm số tài nguyên khả dụng lớn hơn thực tế.

Biện pháp: chỉ transaction thực hiện thành công chuyển trạng thái `HELD -> EXPIRED` được giảm số tài nguyên đang giữ.

### 3.4. Xác nhận đua với thu hồi

Một request chuyển lượt giữ thành `CONFIRMED`, trong khi worker trả tài nguyên cho người khác. Nếu hai thao tác không có chung cơ chế tuần tự hóa, cùng một tài nguyên có thể được cam kết hai lần.

Biện pháp: khóa và cập nhật trạng thái, bộ đếm tài nguyên trong cùng một transaction.

### 3.5. Phát lại thông điệp hoặc callback muộn

Một thông điệp hết hạn cũ đến sau khi lượt giữ đã được gia hạn; hoặc webhook thanh toán đến sau khi tài nguyên được cấp cho khách khác.

Biện pháp: xử lý theo trạng thái và phiên bản hiện tại. Một sự kiện đến muộn không có quyền tự làm sống lại lượt giữ đã kết thúc.

## 4. Các bất biến nghiệp vụ

Với một pool có tổng dung lượng `capacity`, đặt:

- `held_units`: tổng số đơn vị còn được ghi nhận ở trạng thái `HELD`, bao gồm lượt đã qua hạn nhưng chưa được thu hồi.
- `committed_units`: tổng số đơn vị đã được cam kết bởi lượt `CONFIRMED`.
- `available_units = capacity - held_units - committed_units`.

Các bất biến cần giữ:

~~~text
capacity >= 0
held_units >= 0
committed_units >= 0
held_units + committed_units <= capacity

held_units = SUM(units của các allocation đang có state HELD)
committed_units = SUM(units của các allocation đang có state CONFIRMED)
~~~

Hai đẳng thức tổng giả định phạm vi dữ liệu minh họa chưa có giao hàng, hoàn trả hoặc kết thúc cam kết. Khi bổ sung các quy trình đó, phải mở rộng trạng thái và định nghĩa bộ đếm tương ứng.

Các bất biến về vòng đời:

1. Chỉ lượt `HELD` còn hạn mới được xác nhận hoặc gia hạn.
2. Lượt `EXPIRED` không được quay lại `HELD` hay `CONFIRMED`.
3. Mỗi lượt giữ chỉ giải phóng số lượng của nó một lần.
4. Gia hạn không làm tăng số lượng đang giữ; đổi số lượng là một thao tác có kiểm tra dung lượng riêng.
5. Mọi thay đổi ảnh hưởng tài nguyên đều phải tuân thủ cùng một quy tắc đồng thời.
6. Quyền xác nhận, hủy hoặc gia hạn phải được kiểm tra trên đúng đối tượng và tenant.
7. Retry không được tạo một lượt giữ mới hoặc làm thay đổi thời hạn ngoài ý định ban đầu.

**Hiệu lực và kế toán tài nguyên là hai việc khác nhau.** Lượt đã quá hạn phải bị từ chối xác nhận ngay, nhưng có thể còn chiếm `held_units` cho đến khi transaction thu hồi commit. Thiết kế này có thể tạm báo thiếu chỗ khi worker chậm, nhưng vẫn bảo toàn dung lượng.

Không vừa tính khả dụng bằng cách loại mọi bản ghi quá hạn, vừa tiếp tục dùng bộ đếm chứa các bản ghi đó trong những đường ghi khác. Hai cách tính không đồng nhất sẽ gây cấp vượt hoặc từ chối sai.

## 5. State machine cho một lượt giữ

~~~mermaid
stateDiagram-v2
    [*] --> HELD: Cấp giữ thành công
    HELD --> HELD: Gia hạn hợp lệ
    HELD --> CONFIRMED: Xác nhận trước hạn
    HELD --> CANCELLED: Hủy trước hạn
    HELD --> EXPIRED: Đến hạn và thu hồi
    CONFIRMED --> [*]
    CANCELLED --> [*]
    EXPIRED --> [*]
~~~

Trong bài này, nếu API hủy gặp lượt `HELD` đã quá hạn, hệ thống ghi nhận `EXPIRED` và trả tài nguyên theo cùng một hàm thu hồi. Nhờ đó, ý nghĩa trạng thái cuối không phụ thuộc người dùng bấm hủy trước hay sau khi worker chạy.

| Thao tác | Điều kiện | Kết quả |
| --- | --- | --- |
| Tạo lượt giữ | Đủ tài nguyên, đúng quyền và quota | Tăng `held_units`, tạo `HELD` |
| Xác nhận | `HELD`, còn hạn, đúng quyền | Giảm `held_units`, tăng `committed_units` |
| Gia hạn | `HELD`, còn hạn, chưa vượt chính sách | Cập nhật hạn và phiên bản |
| Hủy trước hạn | `HELD`, đúng quyền | Giảm `held_units`, chuyển `CANCELLED` |
| Thu hồi | `HELD`, đã đến hạn | Giảm `held_units`, chuyển `EXPIRED` |
| Retry trên trạng thái cuối | Cùng thao tác đã ghi nhận hoặc trạng thái đã kết thúc | Trả kết quả phù hợp, không đổi bộ đếm |

Không nhận `state`, `owner_id`, `tenant_id`, giá trị quota hoặc `expires_at` tùy ý từ request rồi ghi thẳng vào entity. Client gửi ý định; server quyết định chuyển trạng thái và hạn.

## 6. Mô hình dữ liệu tối thiểu

~~~text
resource_pool
  id
  tenant_id
  capacity
  held_units
  committed_units

allocation
  id
  tenant_id
  pool_id
  owner_id
  units
  state
  created_at
  expires_at
  max_hold_until
  generation
  version
~~~

Ý nghĩa một số trường:

- `expires_at`: hạn hiện tại do server tính.
- `max_hold_until`: trần thời gian tuyệt đối, ví dụ thời điểm tạo cộng mười lăm phút.
- `generation`: thế hệ lịch hết hạn; tăng khi gia hạn thành công để nhận diện thông điệp lịch cũ.
- `version`: phiên bản phục vụ cập nhật có điều kiện hoặc phát hiện ghi đè. Có trường version không tự làm thao tác an toàn; câu lệnh ghi phải sử dụng nó khi chọn cơ chế kiểm soát đồng thời bằng phiên bản.
- `owner_id`, `tenant_id`: ranh giới quyền theo đối tượng. Giá trị đối chiếu phải xuất phát từ danh tính đã xác thực.

Có thể thêm bảng idempotency và outbox theo nhu cầu. Khóa idempotency nên có phạm vi xác định, chẳng hạn `(tenant, actor, operation, key)`, kèm dấu vân tay các tham số và tham chiếu kết quả.

Ở mức cơ sở dữ liệu, nên có ràng buộc `units > 0`, bộ đếm không âm và `held_units + committed_units <= capacity`. Ràng buộc trên một hàng pool hỗ trợ chặn lỗi, nhưng chưa thay thế việc giữ đồng nhất tổng các allocation và bộ đếm trong transaction.

Dùng kiểu dữ liệu lưu một thời điểm tuyệt đối và chuẩn hóa trao đổi thời gian, thường là UTC. Chuỗi ngày giờ không kèm múi giờ dễ gây sai lệch giữa các thành phần.

## 7. Transaction và thứ tự khóa

### 7.1. Một cách triển khai dễ phân tích

Với một cơ sở dữ liệu quan hệ làm nguồn dữ liệu có thẩm quyền, có thể tuần tự hóa mọi thao tác trên một pool bằng khóa hàng:

1. Bắt đầu transaction.
2. Khóa hàng pool.
3. Khóa lượt giữ cần xử lý và kiểm tra lại quan hệ của nó với pool.
4. Kiểm tra tenant, chủ sở hữu và quyền thao tác.
5. Đọc thời gian có thẩm quyền sau khi lấy đủ khóa.
6. Kiểm tra trạng thái, hạn và chính sách.
7. Ghi trạng thái, bộ đếm và bản ghi outbox nếu cần.
8. Commit rồi trả kết quả hoặc phát tác động bên ngoài thông qua outbox.

Tất cả đường ghi phải dùng cùng thứ tự: cấp mới, xác nhận, gia hạn, hủy, thu hồi và thao tác quản trị. Với nhiều pool, khóa theo một thứ tự ổn định, chẳng hạn tăng dần theo ID, trước khi khóa allocation.

Khóa pool trước giúp thiết kế minh họa dễ chứng minh, nhưng cũng giới hạn mức đồng thời trên pool nóng. Có thể chọn cập nhật có điều kiện hoặc thiết kế phân mảnh khác khi cần; vẫn phải chứng minh lại các bất biến.

Đọc `pool_id` để định tuyến trước transaction chỉ có giá trị tham khảo. Trong transaction phải kiểm tra lại allocation thuộc đúng pool và tenant; không tin `pool_id` hoặc `owner_id` do client khai báo.

### 7.2. Không đọc thời gian quá sớm

Giả sử request lấy thời gian lúc 10:04:59 rồi chờ khóa năm giây. Nếu sau khi lấy được khóa nó vẫn dùng thời gian cũ, một lượt hết hạn lúc 10:05:00 có thể bị xác nhận sai.

Hãy lấy thời gian sau khi lấy đủ khóa, rồi dùng cùng giá trị cho quyết định đó. Trong PostgreSQL, `CURRENT_TIMESTAMP` phản ánh thời điểm bắt đầu transaction; `clock_timestamp()` phản ánh thời gian thực tại lúc gọi. Vì vậy, ví dụ bên dưới lấy một giá trị `clock_timestamp()` sau các khóa.

Cần đọc giá trị thời gian bằng một câu lệnh thực sự chạy sau các câu lệnh khóa, tránh tưởng rằng mọi biểu thức thời gian trong một câu SQL phức tạp đều được đánh giá sau khi chờ khóa.

Quy tắc này giảm lỗi do chờ khóa, nhưng không loại bỏ rủi ro đồng hồ hệ thống bị chỉnh sai. Hệ thống cần nguồn thời gian nhất quán, giám sát độ lệch và chính sách vận hành khi đồng hồ bất thường.

## 8. Luồng xác nhận có kiểm tra hết hạn

Đoạn dưới là giả mã Java để thể hiện ranh giới transaction; các hàm kho dữ liệu và kiểu kết quả cần được hiện thực trong ứng dụng.

~~~java
ConfirmResult result = transaction.execute(() -> {
    Pool pool = poolRepository.lockForUpdate(tenantId, poolId);
    Allocation hold = allocationRepository.lockForUpdate(
        tenantId, poolId, allocationId
    );

    authorization.requireConfirm(principal, hold);

    // Chạy truy vấn thời gian sau khi đã lấy đủ khóa.
    Instant decisionAt = databaseClock.readNow();

    if (hold.isConfirmed()) {
        return confirmationRepository.previousResultForSameIntent(
            hold, requestFingerprint
        );
    }

    if (!hold.isHeld()) {
        return ConfirmResult.closed(hold.state());
    }

    if (!decisionAt.isBefore(hold.expiresAt())) {
        hold.expire(decisionAt);
        pool.releaseHeld(hold.units());

        allocationRepository.save(hold);
        poolRepository.save(pool);
        outboxRepository.addExpired(hold);

        // Trả kết quả để transaction commit phần thu hồi.
        return ConfirmResult.expired();
    }

    hold.confirm(decisionAt);
    pool.moveHeldToCommitted(hold.units());

    allocationRepository.save(hold);
    poolRepository.save(pool);
    confirmationRepository.saveResult(hold, requestFingerprint);
    outboxRepository.addConfirmed(hold);

    return ConfirmResult.confirmed(hold.id());
});

// Chuyển kết quả nghiệp vụ thành HTTP sau khi transaction đã kết thúc.
return responseMapper.toHttp(result);
~~~

Những điểm cần giữ khi hiện thực:

- Kiểm tra quyền trước khi trả kết quả cũ hoặc thay đổi dữ liệu. Biết ID allocation không đồng nghĩa có quyền.
- Nếu cần trả kết quả idempotent cho một xác nhận trước đó, phải kiểm tra cùng ý định: allocation, số lượng, tài liệu chấp thuận hoặc thông tin đơn hàng liên quan.
- Một lượt `CONFIRMED` từ trước không bị hủy chỉ vì hạn giữ ban đầu đã qua. Hạn giữ chỉ điều khiển chuyển đổi từ `HELD`.
- Việc ghi kết quả xác nhận và dữ liệu idempotency phải nguyên tử với chuyển trạng thái.
- Lỗi cơ sở dữ liệu phải làm transaction rollback; không trả thành công khi ghi thất bại.

**Bẫy rollback:** nếu nhánh hết hạn vừa ghi thu hồi vừa ném exception khiến transaction rollback, tài nguyên không được thu hồi như dự định. Có thể chọn chỉ từ chối và để worker thu hồi sau; nếu chọn thu hồi ngay trong API, phải commit kết quả đó trước khi ánh xạ thành phản hồi lỗi nghiệp vụ.

Không gọi dịch vụ thanh toán hoặc gửi email khi đang giữ khóa pool. Ghi outbox trong transaction, xử lý tác động bên ngoài sau commit và bảo đảm consumer chịu được thông điệp trùng.

## 9. Worker thu hồi và xử lý lặp an toàn

Worker thường tìm ứng viên bằng điều kiện:

~~~sql
SELECT id, pool_id, tenant_id
FROM allocation
WHERE state = 'HELD'
  AND expires_at <= :scan_time
ORDER BY expires_at, id
LIMIT :batch_size;
~~~

Danh sách này là gợi ý công việc. Sau lần đọc, một allocation có thể đã được gia hạn, hủy hoặc xác nhận.

Với mỗi ứng viên, xử lý trong transaction theo cùng thứ tự khóa của API:

~~~text
BEGIN

  lock pool
  lock allocation
  kiểm tra lại tenant và pool
  decision_at = đọc thời gian sau khóa

  nếu state != HELD:
      COMMIT, không thu hồi

  nếu decision_at < expires_at hiện tại:
      COMMIT, chưa đến hạn

  chuyển HELD -> EXPIRED
  giảm pool.held_units đúng bằng allocation.units
  ghi sự kiện AllocationExpired vào outbox

COMMIT
~~~

Có thể dùng cập nhật có điều kiện như một lớp bảo vệ bổ sung:

~~~sql
UPDATE allocation
SET state = 'EXPIRED',
    version = version + 1
WHERE id = :allocation_id
  AND tenant_id = :tenant_id
  AND pool_id = :pool_id
  AND state = 'HELD'
  AND expires_at <= :decision_at
RETURNING units;
~~~

Chỉ khi trả về đúng một hàng mới giảm `held_units` và ghi sự kiện, tất cả trong cùng transaction. Nếu không có hàng nào, không hoàn tài nguyên.

Một số chi tiết vận hành ảnh hưởng trực tiếp đến tính đúng:

- Worker chạy với quyền hệ thống được giới hạn; không biến endpoint thu hồi thành API cho người dùng sửa allocation của người khác.
- Chỉ mục phục vụ điều kiện trạng thái và hạn giúp quét theo lô. Chọn kích thước lô để tránh transaction giữ khóa quá lâu.
- Nếu dùng cách khóa hàng trong lúc quét như `SKIP LOCKED`, phải thiết kế lại để giữ thứ tự khóa nhất quán. Không khóa allocation trước rồi khóa pool, trong khi API làm ngược lại.
- Worker có thể chạy nhiều bản sao; tính đúng đến từ kiểm tra trong transaction, không đến từ giả định chỉ có một worker.
- Retry sau deadlock hoặc lỗi tạm thời phải chạy lại toàn bộ transaction với trạng thái và thời gian mới.

Khi xác nhận thắng tranh chấp, worker thấy `CONFIRMED` và không trả tài nguyên. Khi thu hồi thắng, xác nhận thấy `EXPIRED` và bị từ chối. Không có kết quả hợp lệ nào vừa cam kết vừa hoàn lại cùng lượng tài nguyên.

## 10. Gia hạn và giới hạn chiếm giữ

Một chính sách mẫu:

~~~text
initial_hold = 5 phút
max_total_lifetime = 15 phút tính từ created_at
max_renewals = 2
renewal_window = 60 giây cuối trước expires_at
~~~

Các giá trị này chỉ minh họa; lựa chọn thực tế phải dựa vào quy trình thanh toán, độ khan hiếm tài nguyên và rủi ro lạm dụng.

Để gia hạn, server cần kiểm tra trong transaction:

1. Người gọi có quyền trên allocation.
2. Allocation vẫn là `HELD`.
3. `decision_at < expires_at`; lượt đã hết hạn không được cứu bằng `renew`.
4. Đang ở cửa sổ được gia hạn và chưa vượt ngân sách.
5. Hạn mới không vượt `max_hold_until` hoặc giới hạn của tài nguyên.
6. Hạn mới thực sự lớn hơn hạn hiện tại; nếu không, trả kết quả không thay đổi và không tính thành một lần gia hạn mới.

Ví dụ công thức theo chính sách kéo dài tính từ thời điểm quyết định:

~~~text
new_expires_at = min(
    decision_at + renewal_duration,
    max_hold_until,
    resource_booking_deadline
)
~~~

Một nghiệp vụ khác có thể cộng thời lượng vào hạn hiện tại. Phải chọn rõ một chính sách, bởi hai cách sẽ cho kết quả khác nhau khi client gọi sớm hoặc retry.

Gia hạn thành công cập nhật `expires_at`, tăng `generation`, tăng `version` và ghi lịch/sự kiện cần thiết trong cùng transaction.

Ngoài giới hạn trên từng allocation, cần giới hạn số lượng giữ đồng thời và hành vi tạo lại. Nếu khách cứ hủy rồi tạo mới, trần mười lăm phút trên mỗi lượt không ngăn được chiếm giữ liên tục. Có thể áp dụng quota theo tài khoản và tổ chức, giới hạn tốc độ, ngân sách giữ theo thời gian hoặc yêu cầu điều kiện bổ sung cho tài nguyên khan hiếm.

Không dùng riêng địa chỉ IP để xác định quyền sở hữu hoặc quota duy nhất; nhiều người có thể dùng chung mạng, còn người lạm dụng có thể đổi IP.

## 11. Thông điệp hết hạn cũ và thế hệ lịch

Giả sử lượt giữ có `generation = 3`, hạn 10:05. Sau khi gia hạn, nó có `generation = 4`, hạn 10:10. Thông điệp được tạo từ lịch cũ vẫn có thể đến lúc 10:05.

Thông điệp nên mang thông tin như:

~~~json
{
  "allocationId": "hold-842",
  "expectedGeneration": 3,
  "expectedExpiresAt": "2026-11-22T10:05:00Z"
}
~~~

Consumer không được xem nội dung này là lệnh thu hồi vô điều kiện. Nó phải khóa và đọc trạng thái hiện tại:

- Nếu generation khác, thông điệp lịch cũ không được làm hết hạn lịch mới.
- Nếu chưa đến hạn hiện tại, không thu hồi; vẫn phải bảo đảm lịch mới hoặc bộ quét sẽ xử lý về sau.
- Nếu lượt đã kết thúc, xử lý như no-op.
- Nếu generation khớp và đã đến hạn, thực hiện chuyển trạng thái đúng một lần.

Một lựa chọn khác là xem mọi thông điệp chỉ như tín hiệu đánh thức, sau đó quyết định hoàn toàn bằng trạng thái và hạn hiện tại. Cả hai cách đều cần bộ quét đối soát để phục hồi khi thông điệp bị mất hoặc hệ thống ngừng hoạt động.

`generation` giúp nhận diện lịch cũ của một allocation. Nó không thay thế kiểm tra thời gian, khóa transaction hay token chống tác vụ cũ trên tài nguyên bên ngoài.

## 12. Idempotency cho tạo, gia hạn và xác nhận

Retry là điều bình thường khi mất phản hồi mạng. Mỗi thao tác cần ngăn retry biến thành thay đổi nghiệp vụ mới.

| Thao tác | Hành vi khi retry cùng key và tham số | Rủi ro nếu làm sai |
| --- | --- | --- |
| Tạo lượt giữ | Trả lại allocation đã tạo | Mỗi retry giữ thêm một phần tài nguyên |
| Gia hạn | Trả lại kết quả lần gia hạn đó | Mỗi retry kéo dài hạn hoặc tiêu hao thêm ngân sách |
| Xác nhận | Trả lại kết quả xác nhận đã commit | Tạo nhiều đơn hoặc cam kết nhiều lần |
| Thu hồi | Không đổi bộ đếm sau lần chuyển trạng thái đầu | Hoàn tài nguyên nhiều lần |

Nếu cùng key nhưng tham số khác, phải từ chối theo hợp đồng API. Không cho phép một key cũ được dùng để đổi allocation, số lượng hoặc ý định xác nhận.

Khóa duy nhất cho idempotency phải được bảo vệ ở nơi lưu trữ có thẩm quyền. Trong request tạo mới, việc ghi key, tạo allocation và tăng bộ đếm phải cùng transaction. Nếu đụng khóa duy nhất khi xử lý đồng thời, rollback toàn bộ phần cấp mới trước khi đọc và trả kết quả đã tồn tại.

Idempotency không làm thời gian ngừng trôi. Retry tạo lượt giữ trả lại ID cũ và hạn cũ; muốn biết còn hiệu lực cần đọc trạng thái hiện tại. Nó không tự tạo thêm một lượt mới sau khi lượt cũ hết hạn.

Tương tự, retry xác nhận đã thành công có thể trả biên nhận cũ dù hạn giữ ban đầu đã qua. Nếu lần xác nhận chưa từng commit và lượt hiện đã hết hạn, retry phải bị từ chối.

Thời gian lưu bản ghi idempotency phải bao phủ khoảng retry mà hệ thống hỗ trợ. Nếu xóa key quá sớm, một request cũ có thể bị hiểu thành yêu cầu mới.

## 13. Thanh toán muộn và tài nguyên đã được cấp lại

Một tình huống thường gặp:

1. Khách A giữ ghế đến 10:05.
2. Tại 10:05, lượt giữ của A hết hiệu lực.
3. Worker thu hồi; khách B giữ hoặc xác nhận ghế.
4. Tại 10:06, webhook báo thanh toán của A thành công.

Webhook được xác thực chỉ chứng minh sự kiện thanh toán theo hợp đồng tích hợp; nó không chứng minh ghế vẫn thuộc A.

Cách xử lý phải được chọn trước:

- Thử cấp lại bằng một thao tác mới có kiểm tra dung lượng và transaction đầy đủ.
- Nếu không thể cấp lại, chuyển sang quy trình hoàn tiền, tín dụng hoặc xử lý ngoại lệ theo chính sách.
- Lưu riêng kết quả thanh toán và kết quả cấp tài nguyên để đối soát.

Không chuyển trực tiếp `EXPIRED -> CONFIRMED` vì callback mang trạng thái thành công. Không hủy quyền của B để che lỗi của quy trình A.

Nếu nghiệp vụ cho phép một khoảng chờ thanh toán, phải mô hình hóa rõ khoảng chờ đó và tiếp tục tính tài nguyên trong dung lượng bị giữ. Có thể dùng một trạng thái riêng với hạn và bất biến riêng. Không thêm một khoảng ân hạn bí mật chỉ ở webhook.

Nếu quyết định dựa vào thời điểm sự kiện từ nhà cung cấp thay vì thời điểm nhận callback, cần xác định nguồn sự kiện được tin cậy, cách chống phát lại và chính sách giữ tài nguyên trong lúc chờ. Một timestamp cũ không tự tạo lại tài nguyên đã cấp cho người khác.

## 14. TTL, cache và giới hạn của lease

### 14.1. TTL không thay thế kiểm tra nghiệp vụ

TTL của cache hoặc cơ chế tự xóa bản ghi có thể hỗ trợ dọn dữ liệu, nhưng không nên là điều kiện duy nhất cho phép xác nhận.

Các lỗi thường thấy:

- Cache vẫn trả trạng thái `HELD` dù hạn đã qua.
- Cache mất key khiến server tưởng tài nguyên đã rảnh trong khi allocation vẫn được cam kết ở cơ sở dữ liệu.
- Bản ghi allocation bị xóa trước khi hoàn bộ đếm hoặc ghi sự kiện thu hồi.
- Các thành phần áp dụng độ chính xác thời gian hoặc quy tắc làm tròn khác nhau.

Đường ghi cần kiểm tra trạng thái và hạn ở nguồn dữ liệu có thẩm quyền. Nếu đọc cache để hiển thị, phản hồi nên mang `server_time` và `expires_at` để client dựng đồng hồ đếm ngược; giá trị này vẫn không thay thế kiểm tra tại API.

Giữ bản ghi trạng thái cuối đủ lâu cho audit, idempotency và đối soát. Dọn lịch sử là chính sách lưu trữ riêng, thực hiện sau khi hoàn tất nghĩa vụ nghiệp vụ liên quan.

### 14.2. Hết hạn không tự chặn tiến trình cũ

Với tài nguyên là worker hoặc thiết bị, một tiến trình giữ lease có thể mất mạng, bị tạm dừng rồi tiếp tục chạy sau hạn. Server đã cấp lease mới nhưng tiến trình cũ vẫn cố ghi kết quả.

Khi đó cần thêm **fencing token**: số thứ tự tăng đơn điệu cho mỗi lần cấp quyền trên cùng tài nguyên. Hệ thống nhận lệnh ghi phải kiểm tra token một cách nguyên tử và từ chối token cũ theo giao thức đã thiết kế.

Token phải được cấp và kiểm chứng trong phạm vi tài nguyên chung. Một biến `generation` tăng riêng trong từng allocation không đủ để so sánh hai chủ sở hữu khác nhau.

Nếu hệ thống đích không kiểm tra token hoặc không hỗ trợ cơ chế thu hồi tương đương, chỉ hết hạn lease trong cơ sở dữ liệu chưa thể bảo đảm tiến trình cũ ngừng tác động.

Với nhiều vùng hoặc nhiều cơ sở dữ liệu, cũng không thể giả định khóa hàng ở một nơi sẽ bảo vệ mọi nơi. Phải xác định nơi có quyền quyết định cấp phát hoặc cơ chế phối hợp bảo toàn bất biến.

## 15. Kiểm thử tình huống tấn công logic

Nên dùng đồng hồ có thể điều khiển ở kiểm thử đơn vị và cơ chế đồng bộ có chủ đích ở kiểm thử transaction. Tránh dựa chủ yếu vào `sleep`, vì kết quả dễ phụ thuộc tốc độ máy chạy.

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Xác nhận ngay trước hạn | Thành công nếu mọi điều kiện khác đúng |
| Xác nhận đúng tại hạn | Bị từ chối; không tăng `committed_units` |
| Xác nhận sau hạn nhưng worker chưa chạy | Vẫn bị từ chối |
| Request bắt đầu trước hạn nhưng lấy khóa sau hạn | Quyết định theo thời gian sau khóa, không dùng thời gian cũ |
| Hai worker thu hồi cùng allocation | Chỉ giảm `held_units` một lần |
| Xác nhận và thu hồi đồng thời | Chỉ một chuyển trạng thái cuối thắng |
| Gia hạn và thu hồi đồng thời | Tuân thủ thứ tự khóa và hạn hiện tại |
| Thông điệp generation cũ đến sau gia hạn | Không kết thúc lượt giữ còn hạn |
| Gia hạn tại đúng hạn hoặc sau hạn | Bị từ chối, không hồi sinh allocation |
| Retry gia hạn sau khi mất phản hồi | Không gia hạn thêm lần nữa |
| Tạo trùng key đồng thời | Chỉ một allocation và một lần tăng bộ đếm |
| Cùng key, đổi allocation hoặc số lượng | Bị từ chối |
| Đổi `owner_id`, `tenant_id` hoặc ID trong request | Không vượt quyền theo đối tượng |
| Sửa giờ máy khách hoặc gửi `expires_at` tùy ý | Không thay đổi quyết định của server |
| Callback thanh toán đến sau khi cấp lại | Không xác nhận chồng tài nguyên |
| Transaction lỗi sau cập nhật trạng thái | Bộ đếm và trạng thái cùng rollback |
| Worker dừng rồi chạy lại | Xử lý lại an toàn, dần thu hồi hết lượt quá hạn |
| Hủy rồi tạo mới liên tục | Chính sách quota và ngân sách giữ được thực thi |

Để kiểm thử cuộc đua, dùng hai kết nối/transaction thực:

~~~text
T1 khóa pool và allocation
T2 bắt đầu thao tác cạnh tranh, chờ khóa

T1 lấy decision_at, ghi kết quả và commit
T2 lấy được khóa, đọc lại dữ liệu và thời gian rồi quyết định

Kiểm tra trạng thái cuối, bộ đếm, biên nhận và outbox
Lặp lại kịch bản với thứ tự T1/T2 đảo ngược
~~~

Ví dụ pool có một đơn vị, kết quả cuối chỉ có thể phù hợp với một trong hai nhánh:

~~~text
Xác nhận thắng:
  allocation.state = CONFIRMED
  held_units = 0
  committed_units = 1
  available_units = 0

Thu hồi thắng, chưa có cấp mới:
  allocation.state = EXPIRED
  held_units = 0
  committed_units = 0
  available_units = 1
~~~

Không chỉ kiểm tra mã HTTP. Một API trả lỗi đúng vẫn có thể đã tăng bộ đếm sai, phát sự kiện trùng hoặc tạo tác động bên ngoài trước rollback.

Với thử nghiệm ngẫu nhiên nhiều thao tác tạo, gia hạn, hủy, xác nhận và thu hồi, hãy kiểm tra lại các bất biến sau mỗi chuỗi đã commit. Đây là cách phát hiện lỗi mà các ví dụ đơn lẻ dễ bỏ sót.

## 16. Quan sát và phục hồi

Các tín hiệu hữu ích:

- Số lượt `HELD` đã quá hạn nhưng chưa thu hồi.
- Độ trễ thu hồi: `expired_transition_at - expires_at`, theo phân vị và theo pool.
- Số request xác nhận/gia hạn bị từ chối vì hết hạn.
- Tỷ lệ thông điệp cũ hoặc thu hồi lặp trở thành no-op.
- Số lần chờ khóa, deadlock và retry transaction.
- Mức chiếm tài nguyên theo tài khoản, tổ chức và chuỗi tạo lại.
- Sai lệch giữa bộ đếm pool và tổng allocation.

Độ trễ worker tăng là sự cố về khả dụng tài nguyên; nó không được biến thành thời gian hiệu lực bổ sung cho khách.

Audit nên ghi ID allocation, chủ thể, thao tác, trạng thái trước/sau, hạn hiện tại, thời điểm quyết định, generation và mã tương quan. Hạn chế dữ liệu nhạy cảm trong log.

Đối soát phải đọc ảnh chụp dữ liệu nhất quán hoặc phối hợp khóa; nếu đọc pool và allocation tại hai thời điểm khác nhau, hoạt động đồng thời có thể tạo cảnh báo sai. Khi phát hiện sai lệch, sửa chữa bằng quy trình có kiểm soát, tránh cộng hoặc trừ bù trực tiếp trong lúc các transaction vẫn đang thay đổi cùng dữ liệu.

Nếu worker bị dừng, khởi động lại bằng quét các lượt quá hạn. Nếu outbox tồn đọng, tiếp tục phát lại với consumer idempotent. Hệ thống cần khả năng phục hồi từ dữ liệu đã commit, không phụ thuộc một timer còn sống trong bộ nhớ ứng dụng.

## 17. Các câu hỏi cần trả lời trước khi triển khai

1. Hạn điều khiển quyền giữ, quyền xác nhận hay cả quyền sử dụng sau xác nhận?
2. Đến đúng hạn có bị từ chối không, và thời điểm quyết định được lấy ở đâu?
3. Những API, worker, callback và thao tác quản trị nào có thể đổi trạng thái?
4. Tất cả đường ghi có chung quy tắc khóa hoặc cập nhật có điều kiện không?
5. Bộ đếm có bao gồm lượt quá hạn chưa được thu hồi không?
6. Ai được gia hạn, được gia hạn bao nhiêu lần và tổng thời gian tối đa là bao lâu?
7. Retry hoặc thông điệp trùng có thể tạo thêm tài nguyên hay kéo dài hạn không?
8. Khi thanh toán thành công muộn, hệ thống cấp lại hoặc bù trừ theo chính sách nào?
9. Nếu tác vụ cũ vẫn chạy sau khi hết lease, hệ thống đích có chặn được quyền cũ không?
10. Bằng chứng nào cho thấy trạng thái, bộ đếm và tác động bên ngoài vẫn đúng sau lỗi?

Một cơ chế hết hạn an toàn kết hợp kiểm tra thời gian tại điểm quyết định, state machine không hồi sinh, quyền theo đối tượng, transaction bảo toàn tài nguyên và xử lý lặp có kiểm soát. Worker thu hồi giúp đưa tài nguyên trở lại sử dụng; quyền xác nhận đúng hạn phải được bảo vệ ngay tại mỗi thao tác nghiệp vụ.
