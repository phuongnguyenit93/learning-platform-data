# Credit expiration: Bảo vệ quy tắc hết hạn credit

## 1. Hết hạn credit là một quy tắc nghiệp vụ

Trong chương **Credit Rules**, credit expiration xác định thời điểm một khoản credit không còn được sử dụng. Credit trong bài là đơn vị nội bộ của sản phẩm, chẳng hạn điểm thưởng, lượt dùng API hoặc số dư khuyến mại. Những chính sách dưới đây là giả định thiết kế cho ví dụ; từng sản phẩm phải xác định chính sách của mình trước khi triển khai.

Bài thuộc phạm vi **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**: bảo vệ quy tắc nghiệp vụ khỏi việc bỏ qua bước xử lý, sửa dữ liệu, dùng sai quyền hoặc gửi yêu cầu trùng. Với credit expiration, lỗi bảo mật có thể xuất hiện dù request có JSON hợp lệ và người gọi đã đăng nhập.

Ví dụ: một ví còn 100 credit có hạn đến 10:00. Giao diện ẩn số dư lúc 10:00 nhưng API thanh toán vẫn chấp nhận vì tác vụ hết hạn chạy lúc 10:05. Người dùng gọi thẳng API trong khoảng này đã sử dụng được credit ngoài chính sách. Lỗi nằm ở quyết định nghiệp vụ trên máy chủ.

Sau bài này, bạn cần có khả năng:

- Viết bất biến về thời gian, số lượng và quyền sở hữu của credit.
- Mô hình hóa vòng đời credit và giữ chỗ bằng state machine.
- Đặt kiểm tra hết hạn cùng thay đổi số dư trong một transaction.
- Ngăn chi tiêu đồng thời, xử lý lặp và hoàn tiền làm sống lại credit.
- Thiết kế kiểm thử cho thời điểm biên, job trễ và các chuỗi thao tác có chủ đích.

## 2. Ví dụ xuyên suốt: một ví có nhiều lô credit

Một lần cấp credit tạo một **lô** riêng, gọi là credit lot. Không gộp các lô có hạn khác nhau thành một số dư duy nhất rồi làm mất nguồn gốc.

Ví `W1` của khách hàng `U1`, trong tenant `T1`, có:

| Lô | Credit chưa tiêu thụ | Bắt đầu có hiệu lực | Hết hạn |
| --- | ---: | --- | --- |
| A | 70 | 2026-11-01T00:00:00Z | 2026-11-22T10:00:00Z |
| B | 50 | 2026-11-01T00:00:00Z | 2026-12-01T00:00:00Z |

Tại `2026-11-22T09:00:00Z`, ví có thể dùng 120 credit nếu không có giữ chỗ. Nếu chi 80 theo quy tắc **FEFO — First Expiring, First Out**, hệ thống lấy 70 từ A và 10 từ B. B còn 40.

Nếu chưa có giao dịch nào, tại đúng `2026-11-22T10:00:00Z`, A không còn dùng được và số dư khả dụng chỉ còn 50. Kết quả phải đúng ngay cả khi chưa có job nào cập nhật trạng thái A.

FEFO là chính sách phân bổ được chọn trong ví dụ, không phải yêu cầu bắt buộc cho mọi sản phẩm. Nó giúp dùng lô sắp hết hạn trước và giữ được dấu vết lô nào tài trợ cho từng giao dịch.

## 3. Chốt hợp đồng thời gian trước khi viết code

### 3.1. Khoảng hiệu lực có điểm cuối loại trừ

Trong bài, mỗi lô có hai mốc bắt buộc:

~~~text
valid_from <= decision_at < expires_at
~~~

`decision_at` là thời điểm máy chủ ra quyết định nghiệp vụ theo quy trình transaction ở phần sau. Tại đúng `expires_at`, credit đã hết hạn.

| Thời điểm xét | Kết quả với lô hết hạn lúc 10:00:00Z |
| --- | --- |
| 09:59:59.999999Z | Có thể dùng nếu các điều kiện khác hợp lệ |
| 10:00:00.000000Z | Hết hạn |
| 10:00:00.000001Z | Hết hạn |

Thống nhất độ chính xác thời gian giữa DB, ứng dụng và kiểm thử. Nếu cột lưu đến microsecond, dùng các mốc biên biểu diễn được ở độ chính xác đó; không xây kỳ vọng trên phần nanosecond đã bị làm tròn khi ghi dữ liệu.

### 3.2. “Đến hết ngày” cần múi giờ nghiệp vụ

Nếu chính sách ghi “dùng đến hết ngày 22/11/2026 theo giờ Việt Nam”, có thể biểu diễn hạn là:

~~~text
2026-11-23T00:00:00+07:00
= 2026-11-22T17:00:00Z
~~~

Dùng đầu ngày kế tiếp làm cận loại trừ giúp tránh tự ghép chuỗi `23:59:59.999`. Khi cấp lô, chuyển quy tắc ngày và múi giờ thành một instant cụ thể, đồng thời lưu phiên bản chính sách để giải thích cách tính.

“30 ngày” cũng cần được phân biệt: thời lượng cố định hay số ngày lịch trong một múi giờ xác định. Không lấy múi giờ trình duyệt, cấu hình mặc định của từng máy hoặc việc đổi múi giờ hồ sơ để tính lại hạn của lô đã cấp.

### 3.3. Chính sách được dùng trong bài

| Câu hỏi | Quyết định |
| --- | --- |
| Nguồn thời gian có thẩm quyền? | DB chính; lấy sau khi đã có các khóa nghiệp vụ cần thiết |
| Request đến trước hạn nhưng chờ khóa qua hạn? | Xét theo thời điểm sau khi có khóa |
| Transaction được chấp nhận trước hạn nhưng commit sau hạn? | Chấp nhận nếu transaction commit; điểm xét là `decision_at` |
| Giữ chỗ có kéo dài hạn lô không? | Không; deadline không vượt hạn của bất kỳ lô nguồn nào |
| Hoàn tiền có tạo thời hạn mới không? | Không; giữ nguồn gốc và hạn ban đầu |
| Job hết hạn trễ? | Quyết định chi tiêu vẫn kiểm tra thời gian tại máy chủ |
| Người dùng được gửi `expires_at` để sửa lô? | Không; hạn do chính sách máy chủ xác định |
| Lô không hết hạn? | Ngoài mô hình ví dụ; nếu có phải biểu diễn bằng chính sách riêng |

Sản phẩm có thể chọn giữ chỗ trước hạn và cho phép thanh toán sau hạn. Khi đó, đây là một quyền nghiệp vụ riêng: cần giới hạn thời gian giữ, mục đích sử dụng và điều kiện capture. Không để hành vi đó hình thành ngẫu nhiên từ việc thiếu kiểm tra.

## 4. Các business invariant cần bảo vệ

### 4.1. Thời gian và quyền theo đối tượng

Một khoản credit chỉ được đưa vào phân bổ mới khi đồng thời thỏa mãn:

1. Lô thuộc đúng ví, tenant và chủ thể được phép sử dụng.
2. Lô đã có hiệu lực và chưa hết hạn tại `decision_at`.
3. Lô chưa bị thu hồi hoặc bị khóa theo chính sách.
4. Phần được chọn chưa bị tiêu thụ hoặc giữ cho giao dịch khác.
5. Loại credit phù hợp với sản phẩm, đơn hàng và mục đích sử dụng.

Đăng nhập thành công không chứng minh người gọi có quyền dùng `wallet_id`, `lot_id`, `reservation_id` hoặc `order_id` do họ gửi. Mỗi đối tượng phải được kiểm tra trong ngữ cảnh quyền của thao tác hiện tại.

### 4.2. Số lượng

Với mỗi lô:

~~~text
0 <= held_amount <= remaining_amount
~~~

Trong đó:

- `remaining_amount` là lượng chưa bị tiêu thụ hoặc ghi giảm vì hết hạn; nó bao gồm phần đang giữ chỗ.
- `held_amount` là tổng phân bổ của các reservation còn được lưu ở trạng thái `HELD`.
- Giữ chỗ tăng `held_amount`, không trừ `remaining_amount`.
- Capture giảm cả hai lượng bằng phần giữ chỗ được tiêu thụ.
- Release chỉ giảm phần giữ chỗ; không cộng thêm `remaining_amount`.

Dùng đơn vị nguyên nhỏ nhất phù hợp với sản phẩm. Nếu cho phép phần lẻ, dùng biểu diễn thập phân cố định và quy tắc làm tròn rõ ràng. Kiểm tra số dương và tràn số; không để số âm biến một thao tác chi thành thao tác cộng credit.

### 4.3. Số dư khả dụng có thời điểm

Có thể định nghĩa:

~~~text
eligible(lot, t) =
    lot.valid_from <= t
    AND t < lot.expires_at
    AND lot được phép sử dụng theo chính sách

live_held(lot, t) =
    tổng phân bổ trên lot của reservation lưu là HELD
    và t < reservation.deadline

available(wallet, t) =
    SUM(remaining_amount(lot) - live_held(lot, t))
    trên các lot eligible tại t
~~~

Reservation trong ví dụ có `deadline` không vượt hạn của các lô nguồn. Một reservation có thể vẫn được lưu là `HELD` sau deadline nếu chưa được dọn; khi đó nó không còn hiệu lực nghiệp vụ.

Vì vậy, cột tổng hợp `held_amount` có thể tạm chứa giữ chỗ đã quá hạn. Trước khi dùng cột này để cấp phát hoặc capture, transaction phải giải phóng giữ chỗ quá hạn trong ví. API chỉ đọc có thể tính `live_held` trực tiếp. Hai cách phải cho cùng kết quả tại cùng thời điểm và cùng trạng thái dữ liệu.

Số dư cache giúp hiển thị nhanh nhưng không phải bằng chứng đủ điều kiện thanh toán.

### 4.4. Ghi nhận và xử lý lặp

- Một command thành công chỉ tạo một hiệu ứng nghiệp vụ.
- Cùng một phần credit không được vừa chi tiêu vừa ghi giảm hết hạn.
- Một reservation chỉ được đi đến một kết quả cuối cùng.
- Tổng hoàn cho từng phân bổ không vượt phần đã chi trừ các lần hoàn trước.
- Mỗi bút toán truy được về ví, lô, thao tác và chính sách liên quan.
- Thay đổi số dư, ledger, trạng thái command và ý định phát sự kiện được commit hoặc rollback cùng nhau.

## 5. Mô hình dữ liệu và state machine

### 5.1. Các đối tượng tối thiểu

| Đối tượng | Trường hoặc quan hệ đáng chú ý | Vai trò |
| --- | --- | --- |
| `wallet` | `id`, `tenant_id`, `owner_id`, trạng thái | Ranh giới quyền và điểm khóa chung |
| `credit_lot` | Ví, lượng cấp, lượng còn lại, lượng giữ, `valid_from`, `expires_at`, `policy_version` | Giữ nguồn gốc và hạn từng lô |
| `credit_reservation` | Ví, đơn hàng, trạng thái, `deadline` | Giữ credit cho một mục đích |
| `credit_allocation` | Reservation hoặc spend, lô nguồn, lượng phân bổ, phần đã hoàn | Gắn giao dịch với các lô |
| `credit_ledger` | Loại nghiệp vụ, lượng, lô, command, thời điểm xét | Giải thích thay đổi số dư |
| `credit_command` | Ví, loại thao tác, idempotency key, hash nội dung, kết quả | Nhận diện retry |
| `outbox_event` | Mã sự kiện, command, payload | Ghi ý định phát sự kiện cùng transaction |

Khóa ngoại và ràng buộc tenant/ví phải ngăn liên kết chéo, chẳng hạn reservation của ví A tham chiếu lô của ví B. Ràng buộc số học và unique key ở DB bổ sung cho kiểm tra tại tầng dịch vụ.

Không gắn `HELD` làm trạng thái duy nhất của cả lô: một lô có thể vừa có 20 credit giữ chỗ vừa có 50 credit khả dụng. Trạng thái reservation và lượng giữ chỗ mô tả phần này chính xác hơn.

### 5.2. Trạng thái suy ra khác trạng thái lưu sẵn

~~~mermaid
stateDiagram-v2
    [*] --> Scheduled
    Scheduled --> Active: Đến valid_from
    Active --> Depleted: Phần còn lại bằng 0
    Active --> Expired: Đến expires_at
    Scheduled --> Revoked: Thu hồi hợp lệ
    Active --> Revoked: Thu hồi hợp lệ
~~~

Sơ đồ thể hiện trạng thái nghiệp vụ suy ra. Không bắt buộc job cập nhật cột `status` đúng ngay từng thời điểm. Nếu cột vẫn ghi `ACTIVE` nhưng `decision_at >= expires_at`, lô vẫn hết hạn.

`Depleted` nghĩa là không còn lượng để sử dụng ở thời điểm xét. Nếu cho phép hoàn tiền trước hạn, một bút toán hoàn hợp lệ có thể làm lô có lượng trở lại. Việc đó phải qua luồng hoàn tiền, không phải sửa trực tiếp trạng thái.

### 5.3. Vòng đời giữ chỗ

~~~mermaid
stateDiagram-v2
    [*] --> Held
    Held --> Captured: Xác nhận khi còn hiệu lực
    Held --> Released: Hủy giữ chỗ hợp lệ
    Held --> TimedOut: Đạt deadline
    Captured --> [*]
    Released --> [*]
    TimedOut --> [*]
~~~

Máy chủ tính:

~~~text
deadline = min(
    decision_at + thời_gian_giữ_tối_đa,
    expires_at của tất cả lô đã phân bổ
)
~~~

Nếu dùng nhiều lô, ví dụ chọn một deadline chung theo lô hết hạn sớm nhất. Mô hình cho phép từng phần có deadline riêng cần thêm quy tắc capture một phần và tính lại lượng còn thiếu.

Tại deadline, reservation không còn được capture, dù bản ghi chưa được job đổi sang `TIMED_OUT`. Chuyển trạng thái cuối cùng phải kiểm tra điều kiện trong transaction.

## 6. Những chuỗi lạm dụng cần nhận diện

| Chuỗi thao tác | Mục đích lạm dụng | Điểm bảo vệ |
| --- | --- | --- |
| Gửi `expires_at` xa hơn, `status=ACTIVE` hoặc thời gian máy khách | Tự gia hạn | DTO cho phép rõ từng trường; máy chủ tự xác định hạn |
| Mở trang trước hạn, gọi API sau hạn | Dùng kết quả kiểm tra cũ | Kiểm tra lại trong transaction ghi |
| Gửi hai request chi tiêu song song | Tiêu cùng credit hai lần | Khóa ví và cập nhật có điều kiện |
| Giữ chỗ sát hạn, capture sau hạn | Kéo dài quyền sử dụng | Deadline bị chặn bởi hạn lô; kiểm tra khi capture |
| Hủy giữ chỗ sau hạn | Cộng lại credit hết hạn | Release không tạo lô mới hoặc tăng lượng khả dụng |
| Mua trước hạn rồi hoàn sau hạn | Đổi credit sắp hết hạn thành credit mới | Truy nguồn phân bổ và giữ hạn ban đầu |
| Retry spend hoặc callback nhiều lần | Nhân hiệu ứng | Idempotency và unique theo nghiệp vụ gốc |
| Chạy lại job hết hạn | Ghi giảm hai lần | Cập nhật lượng và ledger nguyên tử |
| Đổi ví hoặc reservation trong request | Dùng credit của người khác | Kiểm tra quyền theo đối tượng và tenant |
| Gọi gia hạn trực tiếp hoặc tự phê duyệt | Bỏ qua kiểm soát quản trị | Quyền riêng, phê duyệt, kiểm tra phiên bản |
| Gửi `occurred_at` cũ trong callback | Giả giao dịch trước hạn | Không dùng timestamp bên gọi tự khai làm thời gian xét |

Tái hiện những tình huống này trong môi trường kiểm thử do nhóm phát triển kiểm soát, bằng tài khoản và dữ liệu thử nghiệm.

## 7. Transaction để chi tiêu an toàn

### 7.1. Một giao thức khóa nhất quán

Ví dụ dùng một DB chính và khóa hàng `wallet` để tuần tự hóa các thay đổi credit của cùng ví. Cấp credit, spend, reserve, capture, release, refund, expire và extend đều phải đi qua cùng giao thức.

Trong PostgreSQL, `SELECT ... FOR UPDATE` khóa các hàng được chọn, khiến thao tác ghi hoặc khóa xung đột phải chờ. Trong luồng thông thường, khóa được giữ tới khi transaction kết thúc. Xem [tài liệu khóa hàng PostgreSQL 18](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).

Khóa ví có tác dụng vì mọi writer cùng tuân thủ giao thức; khóa hàng cha không tự động khóa toàn bộ lô con. Một job bỏ qua khóa ví có thể phá vỡ thiết kế.

Quy định thứ tự khóa: ví trước, reservation/command theo thứ tự thống nhất, rồi lô theo ID ổn định. Nếu một nghiệp vụ thật sự cần nhiều ví, khóa các ví theo ID ổn định trước khi khóa đối tượng con. Không giữ khóa DB khi chờ dịch vụ mạng.

### 7.2. Lấy thời gian sau khi đã chờ khóa

PostgreSQL phân biệt `CURRENT_TIMESTAMP`/`now()` theo thời điểm bắt đầu transaction và `clock_timestamp()` theo thời gian thực tại lúc gọi. Transaction chờ lâu có thể nhận một mốc cũ nếu dùng `now()` để xét hạn. Xem [tài liệu thời gian PostgreSQL 18](https://www.postgresql.org/docs/18/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

Ví dụ chọn lấy một `clock_timestamp()` sau khi có các khóa cần thiết, rồi dùng cùng giá trị `decision_at` cho toàn bộ quyết định. Không gọi đồng hồ riêng cho từng lô trong cùng phép phân bổ.

Việc chọn mốc đó làm điểm phân xử là chính sách ứng dụng. Nó không bảo đảm thời gian vật lý lúc commit hoặc lúc giao hàng còn trước hạn. Cần giới hạn thời gian transaction và tránh công việc chậm trong khoảng giữ khóa.

### 7.3. Luồng chi tiêu trực tiếp

Đây là giả mã điều phối, không phải một hàm có thể sao chép và chạy ngay:

~~~text
BEGIN transaction trên DB chính

1. Khóa wallet theo (tenant_id, wallet_id).
   Kiểm tra quyền dùng ví và quan hệ với đơn hàng.
   Không để kết quả làm lộ ví thuộc người khác.

2. Tìm credit_command theo (tenant_id, wallet_id, operation, idempotency_key).
   Nếu đã có:
       khác hash nội dung -> từ chối xung đột;
       cùng nội dung -> trả kết quả đã lưu, không chi tiêu lần nữa.

3. Khóa đối tượng liên quan theo thứ tự quy định.
   Đọc decision_at từ DB sau khi đã có khóa.
   Giải phóng reservation đã quá deadline.
   Vật chất hóa phần hết hạn cần thiết trong ví.

4. Xác định amount từ dữ liệu đơn hàng đáng tin cậy.
   Kiểm tra amount > 0, loại credit và mục đích sử dụng.
   Chọn lô hợp lệ tại decision_at theo FEFO.
   Không đủ -> lưu kết quả từ chối theo hợp đồng command.

5. Phân bổ amount vào các lô.
   Giảm remaining_amount từng lô bằng cập nhật có điều kiện.
   Sai số hàng cập nhật mong đợi -> rollback toàn bộ.
   Không để lại phân bổ hoặc ghi giảm một phần.

6. Ghi allocation, ledger, kết quả command và outbox_event.
   Unique theo đơn hàng/loại thanh toán ngăn chi trùng
   ngay cả khi bên gọi đổi idempotency key.

COMMIT
Chỉ trả thành công sau khi commit thành công.
~~~

Ví dụ coi kết quả từ chối được lưu là kết quả cuối của command đó. Nếu số dư thay đổi và người dùng muốn thử lại như thao tác mới, cần command mới theo hợp đồng API. Lỗi hạ tầng làm rollback không được biến thành kết quả nghiệp vụ đã hoàn tất.

### 7.4. SQL minh họa bước giảm một lô

Placeholder có tên dưới đây cần được bind theo driver. Đây chỉ là phần giữa transaction, sau khóa, kiểm tra quyền, cleanup và phân bổ:

~~~sql
UPDATE credit_lot
SET remaining_amount = remaining_amount - :take
WHERE tenant_id = :tenant_id
  AND wallet_id = :wallet_id
  AND id = :lot_id
  AND valid_from <= :decision_at
  AND expires_at > :decision_at
  AND revoked_at IS NULL
  AND :take > 0
  AND remaining_amount - held_amount >= :take
RETURNING id, remaining_amount;
~~~

Mỗi lần cập nhật phải trả đúng một hàng. Nếu phân bổ trải qua nhiều lô và một lô không cập nhật được, rollback toàn bộ giao dịch.

SQL giả định có cột `revoked_at` và đã xử lý reservation quá hạn tại `decision_at`, nên `held_amount` phản ánh giữ chỗ có hiệu lực ở thời điểm đó. Nó không thay thế kiểm tra quyền hoặc toàn bộ transaction.

Có thể dùng optimistic locking với cột phiên bản thay giao thức trên. Khi xung đột phải đọc lại, lấy thời điểm mới và tính lại phân bổ; không lặp một quyết định được tính trước khi credit hết hạn.

## 8. Job hết hạn: trễ, chạy trùng và chạy đồng thời

Job hết hạn phục vụ ghi nhận và vận hành: tạo ledger, cập nhật lượng còn lại, phát sự kiện và hỗ trợ báo cáo. Quyền chi tiêu đã bị chặn bằng điều kiện thời gian, nên job trễ không tạo thêm thời gian sử dụng.

Quy trình cho một ví:

1. Tìm ứng viên bằng truy vấn có chỉ mục; danh sách ứng viên chỉ là gợi ý.
2. Mở transaction, khóa ví và đối tượng con theo giao thức.
3. Lấy `decision_at`, kiểm tra lại dữ liệu hiện tại.
4. Chuyển giữ chỗ quá hạn từ `HELD` sang `TIMED_OUT`, giảm `held_amount` trên các lô liên quan.
5. Với lô hết hạn, lấy `remaining_amount` hiện tại làm lượng hết hạn, ghi ledger và đưa phần còn lại về 0.
6. Ghi outbox rồi commit.

Deadline reservation không vượt hạn lô nguồn, nên tại lúc vật chất hóa một lô hết hạn, giữ chỗ trên lô đó đều đã đến hạn theo mô hình ví dụ. Xử lý chúng trước để tránh `held_amount > remaining_amount`.

A còn 70 credit, trong đó giữ chỗ 20. Khi A hết hạn, lượng hết hạn là **70**, không phải 90. Phần giữ chỗ nằm bên trong phần còn lại; nó không phải số dư riêng để trừ thêm.

Nếu spend và job chạy đồng thời:

- Bên có khóa trước hoàn tất trên trạng thái hiện tại theo mốc xét của mình.
- Bên có khóa sau đọc lại lượng đã commit và lấy thời điểm mới.
- Spend được xét sau hạn không dùng được lô, kể cả job chưa chạy.
- Job chạy lại khi phần còn lại đã bằng 0 không tạo bút toán ghi giảm dương lần nữa.

Unique key như `EXPIRE:{lot_id}` phù hợp khi mỗi lô chỉ có một lần ghi nhận hết hạn. Nếu cho phép nhiều chu kỳ gia hạn, khóa sự kiện cần định danh chu kỳ/phiên bản; không dùng một khóa làm lần hết hạn hợp lệ sau này bị bỏ qua.

Consumer của sự kiện hoặc thông báo có thể nhận bản phát lại, nên phải nhận diện `event_id` đã xử lý. Dấu “đã gửi thông báo” không quyết định credit đã hết hạn hay chưa.

## 9. Giữ chỗ, capture và hủy

A có 70 credit, hết hạn lúc 10:00. Người dùng giữ chỗ 20 lúc 09:58; thời gian giữ tối đa là 15 phút.

~~~text
deadline = min(09:58 + 15 phút, 10:00) = 10:00
~~~

| Thao tác | Thời điểm xét | Kết quả |
| --- | --- | --- |
| Capture 20 | 09:59 | Có thể thành công; giảm remaining và held cùng 20 |
| Capture 20 | 10:00 | Từ chối theo deadline |
| Hủy giữ chỗ | 09:59 | Bỏ giữ 20; lượng đó khả dụng nếu lô vẫn đủ điều kiện |
| Hủy hoặc timeout | 10:01 | Bỏ giữ; không tạo 20 credit mới còn hiệu lực |
| Capture lần hai sau lần đầu thành công | Bất kỳ | Không tiêu thụ thêm; trả lịch sử hoặc trạng thái đã kết thúc theo API |
| Hủy sau capture | Bất kỳ | Không xử lý như release; nếu hợp lệ phải đi qua hoàn tiền |

Capture kiểm tra quyền trên reservation, quan hệ với ví/đơn hàng, trạng thái, deadline và lô nguồn trong cùng transaction. Client không được đổi mục đích reservation sang đơn hàng khác.

Nếu reservation quá hạn nhưng vẫn lưu `HELD`, chuỗi trạng thái đó không đủ cho capture. Điều kiện `decision_at < deadline` vẫn bắt buộc.

## 10. Hoàn tiền và gia hạn

### 10.1. Hoàn tiền phải truy nguồn

Giao dịch chi 80 đã dùng 70 từ A và 10 từ B. Nếu hoàn sau khi A hết hạn nhưng B chưa hết hạn:

- Phần 70 từ A được ghi nhận đã hoàn theo nguồn gốc nhưng không thành credit khả dụng.
- Phần 10 từ B có thể dùng lại tới hạn ban đầu của B.
- Không tạo một lô 80 credit có hạn mới chỉ vì hoàn tiền hôm nay.

Với hoàn một phần, cần chính sách phân bổ xác định được, ví dụ thứ tự đảo của phân bổ chi hoặc theo dòng hàng. Không cho bên gọi tự chọn lô còn hạn nhằm tối đa hóa lượng được khôi phục.

Nếu ledger hoàn lượng vào lô đã hết hạn, phải ghi phần hoàn và phần hết hạn tương ứng trong cùng transaction, tránh cửa sổ có thể chi tiêu. Có thể dùng kết quả `REFUND_EXPIRED` riêng; yêu cầu là đối soát được việc đã hoàn và không tăng lượng khả dụng.

Tổng phần hoàn không vượt phần đã chi phải được kiểm tra dưới khóa hoặc cập nhật nguyên tử. Idempotency riêng cho mỗi request không ngăn hai request khác key hoàn vượt cùng giao dịch gốc.

### 10.2. Gia hạn là command quản trị có quyền riêng

API cập nhật hồ sơ thông thường không nhận `expires_at`, `policy_version` hoặc `remaining_amount` để thay đổi credit.

Luồng gia hạn có thể yêu cầu:

- Quyền theo tenant và chương trình credit.
- Lý do, phiếu yêu cầu và phạm vi lô.
- Phê duyệt độc lập nếu chính sách yêu cầu; người tạo không tự bỏ qua bước này.
- Kiểm tra phiên bản lô khi thực thi, tránh áp dụng phê duyệt cũ lên dữ liệu đã đổi.
- Audit hạn cũ, hạn mới, người yêu cầu, người phê duyệt và command.
- Idempotency để retry không gia hạn thêm lần nữa.

Trong chính sách ví dụ, chỉ gia hạn lô chưa hết hạn. Nếu muốn bù credit đã hết hạn, dùng nghiệp vụ cấp bù được phê duyệt, có liên kết lô nguồn và lý do. Chỉ sửa hạn sau khi job đã đưa lượng còn lại về 0 không xác định rõ lượng cần khôi phục.

Không xóa hoặc sửa ledger cũ để lịch sử trông như chưa từng hết hạn.

## 11. Idempotency và thứ tự kiểm tra

Một phạm vi idempotency có thể là:

~~~text
(tenant_id, wallet_id, operation_type, idempotency_key)
~~~

Command lưu hash các trường nghiệp vụ đã chuẩn hóa: đơn hàng, lượng, loại credit và reservation. Cùng key nhưng đổi payload phải báo xung đột, không thực hiện nội dung mới.

Ví dụ:

1. Spend thành công lúc 09:59:59 nhưng response bị mất.
2. Client retry cùng command lúc 10:00:02, sau hạn lô nguồn.
3. Sau khi kiểm tra danh tính và quyền xem đối tượng, máy chủ trả kết quả thành công đã lưu.
4. Không chạy lại spend và không từ chối lịch sử thành công chỉ vì credit hiện đã hết hạn.

Đây là trả kết quả thao tác cũ. Command mới được xét sau hạn vẫn không có quyền dùng lô hết hạn.

Unique idempotency key ngăn lặp cùng command. Unique theo nghiệp vụ gốc, chẳng hạn một lần capture cho reservation hoặc một khoản chi credit của đơn hàng, ngăn hiệu ứng trùng khi người gọi đổi key.

Nếu lịch sử command bị xóa theo thời hạn lưu trữ, cần bảo đảm ràng buộc nghiệp vụ còn đủ chặn retry cũ tạo hiệu ứng mới. Không hứa “đúng một lần” chỉ bằng cache key tồn tại vài phút.

## 12. Minh họa kiểm tra thời gian bằng Java

`Instant` biểu diễn một điểm trên trục thời gian. `Clock` cho phép truyền nguồn thời gian và thay bằng đồng hồ cố định khi kiểm thử. Xem [Java Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) và [Java Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html).

Mã sau chỉ minh họa predicate thời gian; không xử lý transaction, quyền hoặc số dư:

~~~java
import java.time.Instant;
import java.util.Objects;

public final class CreditWindow {
    private final Instant validFrom;
    private final Instant expiresAt;

    public CreditWindow(Instant validFrom, Instant expiresAt) {
        this.validFrom = Objects.requireNonNull(validFrom);
        this.expiresAt = Objects.requireNonNull(expiresAt);
        if (!validFrom.isBefore(expiresAt)) {
            throw new IllegalArgumentException("Invalid credit window");
        }
    }

    public boolean isUsableAt(Instant decisionAt) {
        Objects.requireNonNull(decisionAt);
        return !decisionAt.isBefore(validFrom)
                && decisionAt.isBefore(expiresAt);
    }
}
~~~

Trong unit test, truyền thời điểm cố định để kiểm tra biên:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Instant from = Instant.parse("2026-11-01T00:00:00Z");
Instant end = Instant.parse("2026-11-22T10:00:00Z");
CreditWindow window = new CreditWindow(from, end);

Clock atEnd = Clock.fixed(end, ZoneOffset.UTC);
boolean usable = window.isUsableAt(atEnd.instant());
// Mong đợi: false.
~~~

Luồng transaction dùng DB làm nguồn thời gian có thẩm quyền phải truyền `decision_at` từ DB vào predicate. Không lấy thêm `Instant.now()` trên máy ứng dụng để tạo một thời điểm cạnh tranh khác.

Đồng hồ có thể lệch hoặc bị điều chỉnh. Theo dõi đồng bộ thời gian của DB và máy chủ; quy tắc timestamp phụ thuộc nguồn thời gian. Một lần đồng hồ lùi không được tự khôi phục lượng đã ghi giảm hết hạn.

## 13. Kiểm thử tình huống tấn công logic

Không chỉ kiểm tra mã HTTP. Mỗi tình huống cần kiểm tra lượng từng lô, giữ chỗ, ledger, command và sự kiện sau commit hoặc rollback.

### 13.1. Ma trận theo quy tắc

| Nhóm | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| Thời điểm biên | Trước, đúng và sau `expires_at` | Chỉ trước hạn mới có thể dùng |
| Chưa hiệu lực | Spend trước `valid_from` | Không phân bổ từ lô |
| Độ chính xác | Lưu rồi đọc mốc có phần lẻ | So sánh theo độ chính xác DB |
| Múi giờ | Cùng instant với offset khác | Kết quả không đổi |
| Job trễ | Chặn job, spend sau hạn | Không dùng lô hết hạn |
| Chờ khóa | Đến trước hạn, có khóa sau hạn | Dùng mốc sau chờ |
| Phân bổ | Nhiều lô, một lô hết hạn | FEFO chỉ chọn lô đủ điều kiện |
| Số lượng | Amount 0, âm, rất lớn | Từ chối; không cộng credit hoặc tràn số |
| Capture | Tạo hold trước hạn, capture đúng deadline | Từ chối |
| Release | Hủy hold sau hạn lô | Không tăng lượng khả dụng |
| Refund | Hoàn trước/sau hạn từng lô nguồn | Giữ hạn, không hoàn vượt |
| Phát lại | Lặp spend, callback, expire event | Không có hiệu ứng trùng |
| Đổi key | Cùng đơn hàng, nhiều key | Ràng buộc nghiệp vụ ngăn chi trùng |
| Xung đột key | Cùng key, đổi amount/order | Báo xung đột, giữ kết quả cũ |
| Sai quyền | Đổi tenant, ví, lô, reservation | Không đọc hoặc sửa ngoài quyền |
| Mass assignment | Chèn `expires_at` vào request thường | Không đổi hạn |
| Gia hạn | Tự phê duyệt hoặc dùng phê duyệt cũ | Không vượt quy trình/phiên bản |
| Rollback | Lỗi sau khi giảm lô đầu | Không có chi tiêu một phần |
| Retry sau hạn | Thành công trước hạn, retry sau hạn | Trả lịch sử, không ghi giảm mới |
| Hạ tầng | Mất response sau commit | Retry xác định kết quả từ command |

### 13.2. Kiểm thử đồng thời có điểm đồng bộ

Dùng hai kết nối DB thật và cơ chế phối hợp trong bộ kiểm thử, không trông chờ hai luồng ngẫu nhiên chạy đúng lúc:

1. Transaction A giữ khóa ví trước khi hết hạn.
2. B bắt đầu spend khi còn trước hạn, bị chặn tại khóa ví.
3. Điều phối dữ liệu/mốc thử để B nhận khóa khi đã qua hạn.
4. Xác nhận B không phân bổ lô hết hạn và `decision_at` phản ánh thời điểm sau khi nhận khóa.

Với DB thật làm nguồn thời gian, `Clock.fixed` ở unit test không điều khiển `clock_timestamp()`. Integration test cần cách dựng dữ liệu/mốc thời gian và quan sát khóa phù hợp môi trường thử nghiệm. Không mở tham số thời gian tùy ý cho API production chỉ để kiểm thử.

Kiểm tra thêm các cặp spend/spend, spend/expire, capture/timeout, capture/release và refund/refund. Chỉ các kết quả được state machine cho phép được tồn tại; không có số dư âm, phân bổ trùng hoặc hoàn vượt mức.

### 13.3. Kiểm thử chuỗi thao tác và đối soát

Sinh chuỗi `grant → reserve → capture/release → refund → expire` với nhiều thời điểm và request lặp. Sau mỗi bước, kiểm tra các invariant đã nêu.

Trong kịch bản không có hoàn tiền, thu hồi hoặc điều chỉnh, dùng phương trình đơn giản:

~~~text
tổng đã cấp
= tổng đã tiêu thụ + tổng đã hết hạn + tổng remaining_amount
~~~

`held_amount` nằm trong `remaining_amount` nên không cộng thêm vào vế phải. Khi thêm refund, thu hồi hoặc cấp bù, mở rộng phương trình theo các loại bút toán; không áp nguyên phương trình đơn giản cho toàn hệ thống.

## 14. Vận hành và giải thích quyết định

Log nghiệp vụ cần đủ để trả lời “vì sao request được chấp nhận hoặc từ chối?”:

- `command_id`, `correlation_id`, tenant, ví và đối tượng nghiệp vụ liên quan.
- `decision_at`, hạn lô, deadline reservation và phiên bản chính sách.
- Kết quả như `INSUFFICIENT_ELIGIBLE_CREDIT`, `RESERVATION_TIMED_OUT`, `IDEMPOTENCY_CONFLICT`.
- Lô được phân bổ, lượng thay đổi và tham chiếu ledger.
- Với gia hạn/cấp bù: người yêu cầu, người phê duyệt và căn cứ.

Không ghi token truy cập hoặc toàn bộ dữ liệu nhạy cảm vào log. Lỗi trả về không làm lộ chi tiết ví ngoài quyền của người gọi.

Chỉ số hữu ích gồm độ trễ job hết hạn, reservation quá hạn chưa dọn, lỗi đối soát ledger, xung đột idempotency, thời gian chờ khóa và capture bị từ chối do deadline. Job trễ có thể không ảnh hưởng quyền chi tiêu khi kiểm tra thời gian vẫn đúng, nhưng vẫn cần theo dõi để hiển thị và báo cáo không chậm quá cam kết.

Cache số dư nên kèm `calculated_at` và `next_change_at` nếu xác định được. Cache có thể sai chỉ vì thời gian trôi qua dù không phát sinh sự kiện ghi. API chi tiêu phải quyết định lại trên nguồn dữ liệu có thẩm quyền.

Credit expiration được bảo vệ khi thời gian, trạng thái, quyền sở hữu và lượng credit cùng tham gia vào một quyết định nguyên tử; retry, job trễ và chuỗi hoàn/hủy không tạo quyền sử dụng mới ngoài chính sách.
