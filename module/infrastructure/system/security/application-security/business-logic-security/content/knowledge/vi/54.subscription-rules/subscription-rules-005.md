# Pause and resume policy: Bảo vệ quy tắc tạm dừng và tiếp tục thuê bao

## 1. Pause/resume là thay đổi quyền lợi, không chỉ đổi trạng thái

Trong chương **Subscription Rules**, pause là tạm dừng theo một chính sách đã xác định; resume là tiếp tục từ phần quyền lợi còn lại. Nếu chỉ đổi `status = PAUSED` rồi đổi lại `ACTIVE`, hệ thống có thể vô tình cấp thêm thời gian, xóa nợ, làm mới hạn mức hoặc khôi phục một hợp đồng đã hủy.

Bài thuộc phạm vi **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**: bảo vệ quy tắc nghiệp vụ trước việc bỏ qua bước, sửa tham số, thao tác sai quyền và gửi yêu cầu trùng. Các trọng tâm là business invariant, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử chuỗi thao tác.

Cần phân biệt những hành vi dễ bị gọi chung là “pause”:

| Hành vi | Quyền sử dụng dịch vụ | Thời gian quyền lợi | Thu tiền/hóa đơn |
| --- | --- | --- | --- |
| Chỉ tạm ngừng thu tiền | Có thể vẫn mở | Có thể vẫn trôi | Theo chính sách thanh toán |
| Đóng băng gói trả trước | Đóng trong thời gian pause | Bảo toàn phần còn lại | Không tự sinh một khoản mua mới |
| Tạm khóa do nợ hoặc rủi ro | Đóng theo điều kiện quản trị | Theo hợp đồng | Nghĩa vụ cũ có thể vẫn tồn tại |
| Hủy thuê bao | Theo thời điểm hủy có hiệu lực | Kết thúc theo chính sách hủy | Xử lý riêng các nghĩa vụ còn lại |

Ví dụ ở một nhà cung cấp, Stripe phân biệt pause payment collection với pause subscription: chế độ `pause_collection` giữ nguyên trạng thái thuê bao và hóa đơn vẫn có thể được tạo. Không ánh xạ nó trực tiếp thành “đóng băng quyền sử dụng” của ứng dụng. Xem [tài liệu Stripe về pause payment collection](https://docs.stripe.com/billing/subscriptions/pause-payment).

Bài dùng một **gói trả trước do hệ thống nội bộ quản lý thời gian quyền lợi**. Tích hợp thu tiền bên ngoài được phân tích riêng; công thức của ví dụ không mặc nhiên tương đương cách tính của mọi nhà cung cấp.

## 2. Viết chính sách rõ ràng trước khi xây API

### 2.1. Chính sách mẫu

Các con số sau là giả định phục vụ thiết kế, không phải chuẩn chung của ngành:

| Câu hỏi | Chính sách trong ví dụ |
| --- | --- |
| Gói nào được pause? | Gói trả trước đang `ACTIVE`, còn thời gian đã trả, không nợ và không bị khóa quản trị |
| Thời điểm pause? | Ngay tại thời điểm máy chủ chấp nhận trong transaction |
| Quyền dịch vụ khi pause? | Không nhận thao tác sử dụng có trả phí mới |
| Thời gian gói khi pause? | Đóng băng phần thời lượng chưa dùng |
| Số đợt pause? | Tối đa 2 đợt trong một năm chính sách của hợp đồng |
| Mỗi đợt tối đa? | 14 ngày, tính theo thời lượng cố định |
| Tổng thời gian pause? | Tối đa 21 ngày trong cùng năm chính sách |
| Khoảng cách giữa các đợt? | Ít nhất 24 giờ từ lần resume gần nhất |
| Đến deadline? | Tự resume tại deadline; không chờ job mới phát sinh hiệu lực |
| Có làm mới quota sử dụng? | Không; pause/resume không tạo kỳ quyền lợi mới |
| Nợ, khóa rủi ro và hủy? | Không bị xóa bởi resume |
| Trial hoặc khuyến mại đặc biệt? | Không hỗ trợ trong ví dụ, trừ khi có chính sách riêng |
| Có hủy đã lên lịch? | Không nhận pause mới khi đang có lịch hủy |

“Năm chính sách” có một định danh và mốc bắt đầu/kết thúc ổn định theo hợp đồng. Nó không được tính lại chỉ vì đổi plan, gia hạn ngày hết quyền lợi hoặc gọi resume.

Một đợt đi qua ranh giới năm được gắn với bucket đã chọn khi bắt đầu. Phần ngân sách đã dành cho nó vẫn nằm ở bucket đó đến khi quyết toán; qua năm mới không mở thêm đợt pause chồng lấn.

### 2.2. Dữ liệu người dùng được đề nghị và dữ liệu máy chủ quyết định

Client có thể đề nghị độ dài pause và gửi lý do. Máy chủ quyết định:

- Tenant và chủ thể có quyền trên thuê bao.
- Phiên bản chính sách, số lượt còn lại và ngân sách còn lại.
- `pause_started_at`, `pause_deadline` và phần thời gian đóng băng.
- Trạng thái thanh toán, trạng thái quản trị và quyền dịch vụ thực tế.
- Hạn quyền lợi sau resume.

Không nhận trực tiếp `remaining_seconds`, `new_paid_until`, `pause_count`, `payment_status` hoặc `approved=true` từ API tự phục vụ.

Nếu độ dài đề nghị vượt giới hạn, ví dụ chọn từ chối rõ ràng. Một sản phẩm có thể chọn rút ngắn tự động, nhưng phải trả lại deadline thật để người dùng biết điều đã được chấp nhận.

## 3. Bảo toàn thời gian còn lại

### 3.1. Công thức cho một đợt pause

Gọi:

- `E`: hạn quyền lợi đang có trước pause.
- `P`: thời điểm pause có hiệu lực.
- `D`: deadline tự resume.
- `T`: thời điểm máy chủ xét yêu cầu resume hoặc xử lý chuyển trạng thái đến hạn.
- `R`: thời lượng đã trả còn lại được đóng băng.

Điều kiện nhận pause:

~~~text
P < E
P < D
R = E - P
~~~

Khoảng pause có dạng `[P, effective_resume_at)`. Điểm cuối không thuộc khoảng pause:

~~~text
effective_resume_at = min(T, D)
new_paid_until = effective_resume_at + R
actual_paused_duration = effective_resume_at - P
~~~

Công thức chỉ áp dụng cho **đợt pause đang mở**, với `T >= P`. Nó không phải phép tính được lặp trên mỗi request resume.

### 3.2. Ví dụ cụ thể

Gói có hạn `2026-11-30T00:00:00Z`. Pause bắt đầu lúc `2026-11-20T00:00:00Z`, nên còn 10 ngày đã trả. Deadline pause là `2026-12-04T00:00:00Z`, tương ứng 14 ngày.

| Tình huống | Thời điểm resume có hiệu lực | Hạn quyền lợi sau resume |
| --- | --- | --- |
| Resume sớm ngày 25/11 | 2026-11-25T00:00:00Z | 2026-12-05T00:00:00Z |
| Tự resume đúng deadline | 2026-12-04T00:00:00Z | 2026-12-14T00:00:00Z |
| Job chỉ chạy ngày 06/12 | Vẫn là 2026-12-04T00:00:00Z | Vẫn là 2026-12-14T00:00:00Z |

Nếu job chạy trễ ngày 06/12 rồi lấy `now + 10 ngày`, hệ thống đã cấp thêm 2 ngày ngoài chính sách. Thời điểm xử lý và thời điểm có hiệu lực phải được lưu riêng.

Nếu không có job nào chạy, đường kiểm tra quyền truy cập vẫn phải tính hoặc vật chất hóa chuyển trạng thái đến hạn trước khi quyết định. Request ngày 15/12 trong nhánh tự resume phải thấy gói đã hết quyền lợi, không được cấp lại 10 ngày.

### 3.3. Tránh nhầm hạn cũ với hợp đồng đã hết hiệu lực

Khi đang pause hợp lệ, `E` là snapshot phục vụ tính `R`; nó không còn là điều kiện độc lập để kết luận gói đã hết thời gian. Trong ví dụ, resume ngày 02/12 vẫn có thể hợp lệ dù hạn cũ là 30/11.

Điều đó khác với `CANCELED` hoặc `EXPIRED` đã có hiệu lực. Các trạng thái kết thúc không được resume.

Nếu hợp đồng có một mốc kết thúc tuyệt đối `contract_end_at`, mốc đó là ràng buộc riêng, không tự dịch theo pause. Sản phẩm phải quy định cách xử lý thời lượng còn dư tại mốc này. Không mặc nhiên áp dụng mô hình đóng băng vô điều kiện cho hợp đồng có hạn cứng.

### 3.4. Thời gian có thẩm quyền và độ chính xác

Dùng timestamp chuẩn hóa và nguồn thời gian của máy chủ. Thống nhất độ chính xác giữa DB, ứng dụng và kiểm thử; không để làm tròn từng lần pause/resume tạo thêm thời gian.

Ví dụ dùng một ngày bằng 86.400 giây. Nếu chính sách là ngày lịch, phải xác định múi giờ và quy tắc riêng, không thay thế âm thầm bằng thời lượng cố định.

## 4. Business invariant

### 4.1. Quyền và vòng đời

1. Chỉ người có quyền quản lý thuê bao trong đúng tenant mới được pause/resume.
2. Tại một thời điểm, một thuê bao có tối đa một đợt pause đang mở.
3. Chỉ trạng thái nguồn cho phép mới được chuyển trạng thái.
4. Resume không xóa nợ, khóa rủi ro, lịch hủy hoặc quyết định thu hồi quyền.
5. Thuê bao đã hủy/hết hiệu lực không được sống lại nhờ command hoặc webhook cũ.
6. Đóng băng thời gian không đồng nghĩa với cấp thêm tính năng, seat hay quota.

### 4.2. Bảo toàn quyền lợi

Trong mô hình không có mua thêm, hoàn tiền hoặc điều chỉnh:

~~~text
tổng thời lượng đã trả
= thời lượng đã tiêu hao khi gói hoạt động
+ thời lượng đã trả còn lại
~~~

Thời gian pause không làm giảm phần còn lại, nhưng cũng không tạo thêm một phần thưởng mới. Tổng thời gian lịch mà khách hàng giữ hợp đồng có thể tăng; tổng thời lượng sử dụng đã trả không tự tăng.

Một lần resume đóng đợt pause đúng một lần và áp dụng `R` đúng một lần. Không vừa dời hạn quyền lợi vừa cấp credit bù cho cùng khoảng thời gian nếu chính sách chỉ hứa một lợi ích.

### 4.3. Ngân sách pause

Tại bucket của một năm chính sách:

~~~text
0 <= settled_paused_duration
0 <= reserved_paused_duration

settled_paused_duration + reserved_paused_duration <= 21 ngày
successful_pause_count <= 2
~~~

Khi mở đợt pause có độ dài tối đa đã chấp nhận `D - P`:

- Tăng số đợt thành công một lần.
- Dành trước toàn bộ `D - P` vào ngân sách reserved.
- Không mở đợt nếu không đủ ngân sách.

Khi resume:

- Bỏ reservation ngân sách của đợt.
- Cộng thời lượng pause thực tế vào settled.
- Trả lại phần ngân sách thời gian chưa dùng.
- Không trả lại số lượt đã sử dụng, kể cả resume rất sớm.

Cách dành trước ngân sách ngăn hệ thống hứa nhiều thời gian pause hơn giới hạn rồi mới phát hiện lúc quyết toán.

### 4.4. Tính nguyên tử

Đổi trạng thái thuê bao, mở/đóng pause episode, cập nhật ngân sách, ghi command, audit và outbox phải cùng commit hoặc rollback.

Unique key chống retry cần đi cùng invariant nghiệp vụ. Hai request khác idempotency key vẫn không được tạo hai pause episode hoặc áp dụng cùng một lần resume hai lần.

## 5. State machine và quyền dịch vụ

### 5.1. Vòng đời tối giản của ví dụ

~~~mermaid
stateDiagram-v2
    [*] --> Active
    Active --> Paused: Pause hợp lệ
    Paused --> Active: Resume sớm hoặc đến deadline
    Active --> Expired: Hết thời lượng quyền lợi
    Active --> Canceled: Hủy có hiệu lực
    Paused --> Canceled: Hủy có hiệu lực
    Canceled --> [*]
    Expired --> [*]
~~~

Đây là trạng thái nghiệp vụ nội bộ, không phải bảng ánh xạ nguyên trạng của một nhà cung cấp thanh toán.

Khi vật chất hóa chuyển trạng thái trễ, có thể cần thực hiện liên tiếp `PAUSED → ACTIVE → EXPIRED` trong cùng transaction, với các mốc có hiệu lực đúng lịch. Không buộc hệ thống mở quyền dịch vụ giữa hai bước.

| Trạng thái hiện tại | Pause mới | Resume mới | Quyền dịch vụ |
| --- | --- | --- | --- |
| `ACTIVE` còn quyền lợi | Có điều kiện | Không có episode để áp dụng | Theo thời gian, thanh toán và khóa quản trị |
| `PAUSED` chưa đến deadline | Không | Có điều kiện | Đóng đối với thao tác trả phí mới |
| `PAUSED` đã đến deadline | Reconcile trước | Reconcile trước | Xét theo trạng thái sau reconcile |
| `CANCELED` | Không | Không | Theo chính sách hủy đã có hiệu lực |
| `EXPIRED` | Không | Không | Không có quyền từ gói này |

### 5.2. Không dùng một cột trạng thái cho mọi quyết định

Trạng thái dịch vụ, điều kiện thanh toán và khóa quản trị là những trục khác nhau:

~~~text
can_use_paid_feature =
    effective_service_state == ACTIVE
    AND decision_at < effective_paid_until
    AND payment_eligibility == GOOD
    AND administrative_block == false
    AND đối tượng/tính năng nằm trong phạm vi được cấp
~~~

Resume không tự đặt `payment_eligibility = GOOD` và không xóa `administrative_block`. Trạng thái “active” cũng không đủ để mở mọi tính năng ngoài plan hiện tại.

Khi gọi lại một command cũ đã thành công, kết quả trả về là lịch sử thao tác. Nó không phải giấy phép truy cập hiện tại; không cấp token mới chỉ vì response lịch sử ghi “resume thành công”.

### 5.3. Request và công việc đang chạy tại thời điểm pause

Cần xác định ranh giới nghiệp vụ. Ví dụ chọn cho phép công việc đã được chấp nhận nguyên tử trước pause hoàn tất, nhưng không chấp nhận công việc trả phí mới sau pause.

Nếu yêu cầu là dừng cả công việc đang chạy, cần cancellation/fencing tại worker và quy tắc quyết toán phần đã sử dụng. Chỉ xóa nút trên giao diện không dừng được tác vụ nền, phiên đang mở hoặc request đã được xếp hàng.

## 6. Mô hình dữ liệu và các ràng buộc

| Đối tượng | Dữ liệu chính | Điều cần bảo vệ |
| --- | --- | --- |
| `subscription` | Tenant, chủ thể, trạng thái, `paid_until`, version, plan, bucket chính sách | Quyền theo đối tượng và trạng thái hiện hành |
| `pause_episode` | Thuê bao, `started_at`, `deadline`, thời lượng đóng băng, hạn cũ, policy snapshot, trạng thái | Nguồn gốc phần thời gian và chỉ đóng một lần |
| `pause_budget` | Năm chính sách, số lượt, settled, reserved | Không vượt giới hạn |
| `subscription_command` | Loại thao tác, key, hash payload, episode, kết quả | Idempotency |
| `entitlement_history` | Thay đổi quyền lợi, version, thời điểm có hiệu lực | Giải thích việc dời hạn |
| `outbox_event` | Event ID, subscription version, nội dung thay đổi | Phát sự kiện sau commit và chống ghi đè cũ |

Một episode lưu ít nhất hai thời điểm kết thúc nếu đã đóng:

- `effective_resumed_at`: thời điểm có hiệu lực theo chính sách.
- `processed_at`: thời điểm hệ thống thực sự xử lý.

Policy snapshot giữ các điều kiện đã chấp nhận cho đợt pause. Việc sửa cấu hình giới hạn tuần sau không được khiến episode cũ tự có deadline mới. Thay đổi hồi tố, nếu cần, phải là command quản trị được audit.

Ví dụ ràng buộc PostgreSQL cho mô hình một episode mở:

~~~sql
CREATE UNIQUE INDEX uq_one_open_pause_per_subscription
ON pause_episode (tenant_id, subscription_id)
WHERE status = 'OPEN';
~~~

Khóa ngoại hoặc ràng buộc liên kết phải bảo đảm episode, budget và subscription thuộc cùng tenant/hợp đồng. Thêm kiểm tra `deadline > started_at`, thời lượng đóng băng dương, ngân sách không âm và version cập nhật đúng.

Đổi plan hoặc gia hạn ngày quyền lợi không tạo lại bucket ngân sách. Nếu hạn mức là theo tài khoản thay vì từng hợp đồng, ranh giới khóa và unique phải bao phủ toàn tài khoản để hai thuê bao không cùng tiêu một ngân sách.

## 7. Quy trình transaction cho pause và resume

### 7.1. Khóa và thời điểm phân xử

Ví dụ dùng khóa hàng subscription và bucket liên quan trong DB chính. Mọi writer, gồm API, job, thanh toán, hủy và thao tác quản trị, phải theo cùng thứ tự khóa. Với mô hình một hợp đồng, có thể khóa subscription trước rồi các bucket theo ID ổn định.

PostgreSQL `SELECT ... FOR UPDATE` ngăn writer hoặc locker xung đột thay đổi hàng được khóa trước khi transaction hoàn tất. Xem [tài liệu khóa hàng PostgreSQL 18](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).

Khóa subscription không tự động khóa mọi hàng con; sự an toàn phụ thuộc giao thức writer và ràng buộc DB. Nếu một quy trình dùng bucket chung cho nhiều thuê bao, thiết kế lại thứ tự khóa thống nhất ở phạm vi chủ thể chung, không thêm các khóa tùy tiện theo từng endpoint.

Lấy một `decision_at` từ DB sau khi đã có khóa cần thiết. PostgreSQL `now()`/`CURRENT_TIMESTAMP` dùng thời điểm bắt đầu transaction; `clock_timestamp()` phản ánh lúc gọi. Transaction chờ khóa qua hạn không nên tiếp tục quyết định bằng mốc thời gian cũ. Xem [tài liệu thời gian PostgreSQL 18](https://www.postgresql.org/docs/18/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

Cùng một quyết định dùng cùng mốc thời gian. Nếu transaction rollback rồi retry, đọc lại trạng thái và thời điểm mới.

### 7.2. Command pause

Giả mã sau mô tả điều phối nghiệp vụ:

~~~text
BEGIN
  Khóa subscription và các đối tượng liên quan theo giao thức.
  Kiểm tra tenant, quyền quản lý và quan hệ hợp đồng.

  Tìm command theo key:
    cùng payload -> trả lại kết quả lịch sử, không áp dụng lại;
    khác payload -> báo xung đột.

  Lấy decision_at.
  Reconcile các chuyển trạng thái đã đến hạn.
  Kiểm tra ACTIVE, còn thời lượng, không nợ/khóa/lịch hủy.
  Kiểm tra cooldown, số lượt và ngân sách.

  Tính R từ dữ liệu máy chủ.
  Tính deadline từ độ dài hợp lệ đã chấp nhận.
  Dành trước ngân sách và tăng số lượt.
  Tạo episode OPEN với policy snapshot.
  Đổi subscription sang PAUSED, tăng version.
  Ghi command, entitlement history, audit và outbox.
COMMIT
Chỉ trả thành công khi commit đã thành công.
~~~

Một unique idempotency key không thay thế kiểm tra trạng thái. Hai command pause khác key đến đồng thời vẫn chỉ được có một episode mở.

### 7.3. Command resume

~~~text
BEGIN
  Khóa subscription, episode và bucket theo giao thức.
  Kiểm tra tenant và quyền quản lý.
  Kiểm tra command cũ và hash payload trước khi thực thi lại.

  Lấy decision_at.
  Reconcile chuyển trạng thái đến hạn, gồm hủy và auto-resume.
  Nếu episode đã đóng -> không áp dụng R lần nữa.
  Nếu subscription đã kết thúc -> từ chối command resume mới.

  Với episode OPEN còn hợp lệ:
    effective_resume_at = min(decision_at, deadline)
    new_paid_until = effective_resume_at + frozen_remaining
    quyết toán reserved/settled một lần
    đóng episode
    đặt ACTIVE, lưu paid_until và last_resumed_at, tăng version

  Ghi command, history, audit và outbox.
COMMIT
~~~

Nếu auto-resume đã được reconcile trong bước đầu, resume mới có thể trả “đã hoạt động” theo hợp đồng API, nhưng không cộng thêm thời gian. Không tạo một episode giả để hợp thức hóa request.

Ví dụ cập nhật có điều kiện cho bước đóng episode:

~~~sql
UPDATE pause_episode
SET status = 'CLOSED',
    effective_resumed_at = :effective_resume_at,
    processed_at = :decision_at,
    closed_by_command_id = :command_id
WHERE tenant_id = :tenant_id
  AND subscription_id = :subscription_id
  AND id = :episode_id
  AND status = 'OPEN'
RETURNING id;
~~~

Phải cập nhật đúng một hàng khi đang thực thi lần đóng mới. Nếu không đúng kỳ vọng, rollback và đọc lại; không tiếp tục dời hạn. Các thay đổi subscription/budget/history vẫn nằm trong cùng transaction. Placeholder cần bind theo driver, không nối chuỗi từ request.

## 8. Race condition, hủy và các thay đổi liên quan

### 8.1. Hai pause cùng lúc

Nếu hai request cùng đọc “còn một lượt” trước khi ghi, cả hai có thể vượt giới hạn hoặc tạo hai snapshot thời gian. Khóa, cập nhật ngân sách nguyên tử và unique episode mở phải cùng bảo vệ đường ghi.

Không chỉ kiểm tra `count < limit` ngoài transaction. Đổi idempotency key không phải quyền mở đợt pause thứ hai.

### 8.2. Resume thủ công và job tự resume

Hai bên cùng nhắm một episode. Bên thắng đóng episode và áp dụng quyền lợi một lần; bên còn lại đọc trạng thái đã đóng rồi kết thúc không tạo thêm hiệu ứng.

Job trễ dùng deadline làm thời điểm có hiệu lực. Tại đúng deadline, đường kiểm tra quyền phải reconcile trước: không được cho pause kéo dài chỉ vì trạng thái lưu sẵn chưa đổi.

Job phải mang `episode_id` và version hoặc định danh chuyển trạng thái tương ứng. Một job của đợt cũ không được resume đợt pause mới xuất hiện sau đó.

### 8.3. Resume và hủy

Hủy có hiệu lực là sự kiện kết thúc. Sau khi nó đã commit, mọi resume mới hoặc callback cũ đều phải thấy trạng thái kết thúc và không mở lại gói.

Nếu resume thắng khóa trước, gói có thể hoạt động trong khoảng hợp lệ trước thời điểm hủy. Khi hủy có hiệu lực, quyền vẫn kết thúc. Đây là hai quyết định có thứ tự, không phải lý do để bỏ kiểm tra ở bên đến sau.

Khi hủy trong lúc pause, phải đóng episode và quyết toán ngân sách tới thời điểm phù hợp, không để một episode `OPEN` chờ job tương lai. Không áp dụng phần thời gian đóng băng thành quyền sử dụng mới sau hủy. Hoàn tiền, nếu có, là nghiệp vụ riêng.

Khi nhiều mốc đã quá hạn, reconcile theo thứ tự có hiệu lực. Nếu hủy và auto-resume trùng mốc, chính sách ví dụ ưu tiên hủy. Nếu deadline trước thời điểm hủy, có thể ghi lại auto-resume rồi hủy theo thứ tự, nhưng kết quả quyền hiện tại vẫn đóng. Không chọn trạng thái bằng thứ tự webhook đến.

### 8.4. Thay đổi plan, mua thêm và hóa đơn đã có

Ví dụ không cho sửa trực tiếp quyền lợi đang đóng băng bằng một API cập nhật plan thông thường. Nếu sản phẩm cho đổi plan hoặc mua thêm khi pause, cần một command riêng có quy tắc:

- Phần thời gian mới được cộng vào đâu và theo mức giá nào.
- Tính năng nào có hiệu lực khi đang pause.
- Episode và policy snapshot nào được giữ nguyên.
- Có cần phê duyệt hoặc báo giá lại không.
- Cách đối soát để không vừa giữ nguyên phần đã trả vừa nhận hoàn tiền cho chính phần đó.

Không dùng pause để xóa khoản nợ hoặc hóa đơn đã phát sinh. Không reset bộ đếm usage đã tiêu chỉ vì mở lại dịch vụ; `benefit_period_id` phải được giữ hoặc chuyển theo chính sách thật, không theo thao tác resume.

Nếu pause/resume làm dời ngày quyền lợi, quy tắc ngày gia hạn tiếp theo cần được đồng bộ rõ ràng. `paid_until` nội bộ và billing cycle anchor của nhà cung cấp không mặc nhiên là cùng một đại lượng.

## 9. Các chuỗi lạm dụng cần kiểm thử

| Chuỗi thao tác | Mục đích | Điều kiện phải ngăn |
| --- | --- | --- |
| Pause/resume liên tục vài giây | Tích lũy thời gian từ làm tròn | Tính thời lượng nhất quán, cooldown và số lượt |
| Resume nhiều lần với nhiều key | Cộng phần đóng băng nhiều lần | Episode chỉ đóng một lần |
| Đổi plan rồi pause tiếp | Reset số lượt hoặc ngân sách | Bucket chính sách không phụ thuộc thao tác đổi plan |
| Pause sát giờ gia hạn | Nhận cả quyền lợi mới lẫn phần bù cũ | Quy tắc thứ tự và đối soát quyền lợi |
| Đợi job auto-resume chạy trễ | Kéo dài pause ngoài hạn | Dùng deadline, reconcile ở đường truy cập |
| Dùng token cũ sau pause | Tiếp tục dùng khi thời gian không trôi | Kiểm tra quyền máy chủ tại ranh giới chấp nhận công việc |
| Đổi `subscription_id` hoặc tenant | Quản lý gói của người khác | Kiểm tra quyền theo đối tượng |
| Gửi `new_paid_until` hoặc `pause_count=0` | Tự kéo dài gói/reset giới hạn | DTO và tính toán phía máy chủ |
| Resume gói đang nợ | Xóa khóa thanh toán | Payment eligibility độc lập |
| Phát lại webhook resume sau hủy | Khôi phục gói đã kết thúc | Kiểm tra command/episode/version và trạng thái hiện tại |
| Tạo pause ở hai thuê bao dùng chung ngân sách | Chi vượt hạn mức theo tài khoản | Khóa/ràng buộc ở đúng chủ thể ngân sách |
| Tạo yêu cầu quản trị rồi tự phê duyệt | Vượt giới hạn pause | Quyền phê duyệt và kiểm tra trạng thái yêu cầu |
| Hủy sau khi nhận bù thời gian rồi xin hoàn toàn bộ | Nhận hai lợi ích cho cùng phần đã trả | Ledger quyền lợi và hoàn tiền có liên kết |

Giới hạn tần suất có thể giảm tải nhưng không thay thế invariant. Hai request hợp lệ về tần suất vẫn có thể khai thác race condition nếu đường ghi không nguyên tử.

Với giao diện dùng cookie phiên, cần bảo vệ yêu cầu thay đổi trạng thái khỏi CSRF theo cơ chế xác thực của ứng dụng. Pause/resume nên là command có phương thức thay đổi dữ liệu; đường GET xem thuê bao không được gây chuyển trạng thái theo ý người gọi. Reconcile nội bộ khi đọc là xử lý mốc đã được chính sách chấp nhận từ trước, không phải nhận một command pause mới qua URL.

## 10. Đồng bộ với nhà cung cấp thanh toán

### 10.1. Transaction DB không bao phủ HTTP bên ngoài

Trong mô hình trả trước nội bộ, resume không mua thêm quyền lợi nên có thể hoàn tất bằng transaction local. Khi tích hợp một nhà cung cấp, DB và lời gọi HTTP không có chung tính nguyên tử chỉ nhờ annotation transaction.

Ví dụ lỗi:

1. Nhà cung cấp đã resume và có thể tạo hóa đơn.
2. Kết nối timeout trước khi ứng dụng nhận response.
3. Ứng dụng gọi lại như một thao tác mới.
4. Hệ thống tạo hiệu ứng ngoài ý muốn hoặc hiểu sai điều kiện mở quyền.

Cần phân biệt `desired_state`, trạng thái đồng bộ và trạng thái hiệu lực thực tế. Có thể có `PAUSE_PENDING`, `RESUME_PENDING` hoặc operation riêng với `PENDING/SUCCEEDED/FAILED/UNKNOWN`; không mở quyền chỉ vì đã gửi HTTP thành công.

### 10.2. Luồng điều phối bằng outbox

Một thiết kế có thể dùng các bước:

1. Transaction local kiểm tra quyền/chính sách, tạo command và outbox.
2. Worker nhận operation, gọi nhà cung cấp bằng idempotency key ổn định.
3. Nếu response mơ hồ, tra cứu/reconcile theo operation, không coi timeout là chắc chắn thất bại.
4. Khi có bằng chứng kết quả, transaction local kiểm tra lại episode, version và trạng thái kết thúc rồi cập nhật.
5. Ghi audit và phát sự kiện quyền lợi với version mới.

Không giữ khóa DB trong suốt lời gọi mạng. Worker cần cơ chế claim và xử lý retry để hai worker không chủ động phát các operation trái chiều cùng lúc.

Một bài toán bắt buộc phải chốt thêm là **thời điểm quyền dịch vụ đổi trong giai đoạn pending**. Ví dụ:

- Nếu đã đóng truy cập khi pause pending nhưng billing chưa dừng, phải có chính sách bù hoặc xử lý thất bại.
- Nếu resume cần thanh toán mà invoice chưa đạt điều kiện, không cấp quyền đã trả từ một response chấp nhận yêu cầu.
- Nếu nhà cung cấp chưa hỗ trợ đóng băng đúng như công thức nội bộ, cần đổi mô hình hoặc thực hiện điều chỉnh có đối soát.

Không tự giả định khả năng bù hoàn hảo. Operation lỗi không được xóa khỏi DB rồi để nhân viên hoặc job không còn biết trạng thái nào cần xử lý.

### 10.3. Webhook trùng và đến sai thứ tự

Stripe ghi rõ webhook có thể trùng và không bảo đảm thứ tự nhận sự kiện. Vì vậy không dùng “sự kiện đến sau cùng” làm quy tắc thắng cho trạng thái thuê bao. Xem [hướng dẫn webhook Stripe](https://docs.stripe.com/webhooks).

Handler cần:

- Xác thực chữ ký theo dữ liệu gốc và cơ chế của nhà cung cấp.
- Kiểm tra môi trường, tài khoản nhà cung cấp và ánh xạ tenant.
- Lưu định danh sự kiện để nhận diện phát lại.
- Liên kết sự kiện với operation/thuê bao thật, không tin `tenant_id` do payload tùy ý gán.
- Reconcile trạng thái hiện hành khi không có version/sequence được nhà cung cấp cam kết.
- Áp dụng cập nhật dưới cùng giao thức khóa và kiểm tra trạng thái kết thúc.

Đọc lại provider cũng không cho phép ghi đè mù quáng dữ liệu mới hơn ở local. Phải kiểm tra version/operation sau khi nhận response, và xử lý các thay đổi phát sinh trong lúc HTTP đang chạy.

Lưu receipt sự kiện bền vững và công việc cần làm trước khi báo đã nhận. Nếu chỉ đánh dấu “đã xử lý” rồi crash trước khi cập nhật nghiệp vụ, retry sau đó có thể bị bỏ qua vĩnh viễn.

## 11. Idempotency, quyền và phê duyệt

### 11.1. Phạm vi command

Ví dụ khóa:

~~~text
(tenant_id, subscription_id, operation_type, idempotency_key)
~~~

Hash payload cần bao gồm các trường ảnh hưởng nghiệp vụ: episode, độ dài đề nghị và phiên bản kỳ vọng nếu API sử dụng nó. Cùng key khác nội dung phải báo xung đột.

Trình tự quan trọng:

1. Xác thực và kiểm tra quyền xem/quản lý đối tượng theo hợp đồng API.
2. Tìm command cũ và so payload.
3. Nếu đã hoàn tất, trả kết quả cũ; không chạy lại phép tính.
4. Với command mới, kiểm tra trạng thái/chính sách hiện tại rồi thực thi.

Một request pause đã thành công có thể được retry sau khi gói lại active. Retry đó vẫn thuộc episode cũ, không được tạo pause mới. Một request resume cũ sau hủy chỉ trả lịch sử được phép xem, không mở quyền.

### 11.2. Ngoại lệ quản trị phải có chủ thể và phạm vi

Một số sản phẩm cho bộ phận hỗ trợ vượt giới hạn pause. Luồng đó cần command riêng, không phải một tham số `force=true` mà khách hàng cũng có thể gửi.

Nếu yêu cầu phê duyệt, lưu người yêu cầu, người phê duyệt, lý do, hạn mức được phép và version của thuê bao. Khi thực thi, kiểm tra quyền và version còn phù hợp. Không để yêu cầu đã được duyệt cho plan cũ áp dụng vô hạn lên plan mới.

Audit ngoại lệ phải chỉ ra ngân sách tăng theo căn cứ nào. Không đặt lại số đếm cũ về 0 để che việc vượt giới hạn.

## 12. Minh họa Java: tính kết quả, không tự cấp quyền

`Duration` biểu diễn thời lượng theo giây và nanosecond; ngày trong phép tính Duration là thời lượng 24 giờ. Nó phù hợp với giả định thời lượng cố định của ví dụ. Xem [Java Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html).

Mã sau là hàm tính thuần cho một episode đang mở. Tầng dịch vụ phải xác thực, kiểm tra trạng thái và áp dụng kết quả đúng một lần trong transaction:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class PauseMath {
    public record PauseSnapshot(
            Instant startedAt,
            Instant deadline,
            Instant previousPaidUntil,
            Duration frozenRemaining) {

        public PauseSnapshot {
            Objects.requireNonNull(startedAt);
            Objects.requireNonNull(deadline);
            Objects.requireNonNull(previousPaidUntil);
            Objects.requireNonNull(frozenRemaining);

            if (!startedAt.isBefore(deadline)
                    || !startedAt.isBefore(previousPaidUntil)
                    || !frozenRemaining.equals(
                            Duration.between(startedAt, previousPaidUntil))) {
                throw new IllegalArgumentException("Invalid pause snapshot");
            }
        }
    }

    public record ResumePlan(
            Instant effectiveAt,
            Instant newPaidUntil,
            Duration actualPaused) {}

    public static ResumePlan calculate(
            PauseSnapshot pause, Instant decisionAt) {
        Objects.requireNonNull(pause);
        Objects.requireNonNull(decisionAt);

        if (decisionAt.isBefore(pause.startedAt())) {
            throw new IllegalArgumentException("Decision precedes pause");
        }

        Instant effectiveAt = decisionAt.isBefore(pause.deadline())
                ? decisionAt
                : pause.deadline();

        return new ResumePlan(
                effectiveAt,
                effectiveAt.plus(pause.frozenRemaining()),
                Duration.between(pause.startedAt(), effectiveAt));
    }
}
~~~

Ví dụ dựng snapshot:

~~~java
Instant start = Instant.parse("2026-11-20T00:00:00Z");
Instant oldEnd = Instant.parse("2026-11-30T00:00:00Z");
Instant deadline = Instant.parse("2026-12-04T00:00:00Z");

PauseMath.PauseSnapshot pause = new PauseMath.PauseSnapshot(
        start, deadline, oldEnd, Duration.between(start, oldEnd));

PauseMath.ResumePlan late = PauseMath.calculate(
        pause, Instant.parse("2026-12-06T00:00:00Z"));

// effectiveAt  = 2026-12-04T00:00:00Z
// newPaidUntil = 2026-12-14T00:00:00Z
// actualPaused = 14 ngày
~~~

Không gọi `calculate` trên dữ liệu từ request rồi cập nhật thẳng DB. Snapshot phải được đọc từ nguồn có thẩm quyền; trạng thái episode và version hiện tại quyết định kết quả có còn được áp dụng không.

Lưu thời lượng theo độ chính xác đã thống nhất. Không chuyển qua `toDays()` rồi cộng ngày cho mỗi lần resume nếu phần lẻ phải được bảo toàn. Kiểm tra giới hạn timestamp/thời lượng ở đầu vào chính sách và dữ liệu lưu trữ; lỗi tính toán không được khiến transaction ghi trạng thái một phần.

## 13. Kiểm thử quy tắc và tình huống tấn công

### 13.1. Ma trận kiểm thử

| Nhóm | Kịch bản | Kết quả cần chứng minh |
| --- | --- | --- |
| Điều kiện pause | Active, còn thời lượng, đủ ngân sách | Tạo đúng một episode và reservation ngân sách |
| Thời điểm biên | Pause ngay trước/đúng hạn quyền lợi | Chỉ trước hạn mới có thể được chấp nhận |
| Thời gian máy khách | Gửi timestamp quá khứ hoặc hạn mới | Không thay thời điểm máy chủ/quyền lợi |
| Resume sớm | Còn 10 ngày, pause 5 ngày | Sau resume vẫn còn đúng 10 ngày |
| Auto-resume | Xét đúng deadline | Dùng deadline làm thời điểm hiệu lực |
| Job trễ | Worker chạy sau deadline 2 ngày | Không cấp thêm 2 ngày |
| Job rất trễ | Xử lý sau hạn quyền lợi đã dịch | Kết quả hiện tại là hết quyền lợi |
| Giới hạn | Lượt thứ ba hoặc vượt tổng 21 ngày | Từ chối, không thay trạng thái/ngân sách |
| Cooldown | Pause lại trước 24 giờ từ resume | Từ chối command mới |
| Ranh giới năm | Episode đi qua năm chính sách | Quyết toán bucket gốc, không mở episode chồng |
| Usage quota | Dùng một phần quota rồi pause/resume | Không làm mới phần đã dùng |
| Sai quyền | Đổi tenant/subscription/episode | Không đọc hoặc sửa ngoài quyền |
| Mass assignment | Gửi status, remaining, approved | Không vượt chính sách |
| Nợ/khóa | Resume gói bị khóa thanh toán/rủi ro | Không mở quyền trái điều kiện |
| Hủy | Resume mới hoặc webhook cũ sau hủy | Không khôi phục gói |
| Retry cùng key | Mất response sau commit | Trả lịch sử, không đếm lượt/cộng hạn lần nữa |
| Key xung đột | Cùng key khác độ dài pause | Báo xung đột |
| Key khác | Hai resume cùng episode | Chỉ một lần áp dụng thời lượng |
| Rollback | Lỗi sau khi cập nhật ngân sách | Trạng thái, episode, budget đều rollback |
| Provider timeout | Không rõ external operation thành công | Reconcile, không phát thao tác mới mù quáng |
| Webhook | Trùng, đảo thứ tự, sai tài khoản | Không ghi đè trạng thái/quyền mới hơn |

Các ví dụ kiểm thử là đặc tả mong đợi; mã minh họa và giả mã trong bài chưa phải một bộ tích hợp chạy được.

### 13.2. Kiểm thử đồng thời có điều phối

Dùng hai kết nối DB và điểm đồng bộ rõ ràng để tạo các cuộc đua:

- Hai pause cùng tranh lượt cuối.
- Hai resume khác key cùng một episode.
- Resume thủ công và job auto-resume.
- Resume và hủy.
- Pause và nhận quyền lợi từ thanh toán.
- Thao tác trả phí và pause.

Xác nhận kết quả trên DB sau commit: số episode mở, số lần đóng, ngân sách reserved/settled, version, hạn quyền lợi, command và outbox. Không chỉ kiểm tra một response `200` và một response lỗi.

Để thử request chờ khóa qua hạn, giữ khóa ở kết nối A, cho B bắt đầu khi còn hợp lệ, rồi chỉ cho B nhận khóa khi đã qua mốc. B phải dùng thời gian sau khi nhận khóa. Unit test với đồng hồ giả trong Java không điều khiển được thời gian DB thật; integration test cần phương án dữ liệu và đồng bộ phù hợp.

### 13.3. Kiểm thử theo chuỗi thao tác

Sinh chuỗi như:

~~~text
mua gói
→ dùng một phần thời gian/quota
→ pause
→ retry pause
→ resume
→ retry resume bằng key khác
→ pause lần nữa
→ hủy
→ nhận webhook resume cũ
~~~

Sau mỗi bước, kiểm tra:

- Không quá một episode mở.
- Tổng ngân sách đã dùng và dành trước không vượt giới hạn.
- Không reset usage hoặc năm chính sách ngoài quy tắc.
- Phần thời gian còn lại không tăng do lặp command hay làm tròn.
- Trạng thái kết thúc không bị command cũ đảo ngược.
- Mọi thay đổi quyền lợi truy được về một căn cứ hợp lệ.

Trong mô hình chỉ có freeze/resume, kết quả cuối phải bảo toàn tổng thời lượng đã trả. Nếu thêm mua mới, hoàn tiền hoặc cấp bù, mở rộng đối soát bằng các bút toán tương ứng; không gộp chúng vào một phép dời hạn không có nguồn gốc.

## 14. Vận hành và giải thích quyết định

Audit cần đủ thông tin để trả lời ai đã đổi quyền lợi, đổi theo quy tắc nào và vì sao:

- Tenant, subscription, episode, command và correlation ID.
- Chủ thể gọi, quyền hoặc phê duyệt được sử dụng.
- Trạng thái/version trước và sau.
- `decision_at`, thời điểm có hiệu lực và thời điểm xử lý.
- Hạn cũ, phần đóng băng, deadline và hạn mới.
- Policy snapshot, bucket, ngân sách đã dành và đã quyết toán.
- External operation/event ID nếu có tích hợp nhà cung cấp.

Không ghi token, thông tin thẻ hoặc toàn bộ payload nhạy cảm vào log. Lỗi trả về cho khách hàng cần đủ hiểu điều kiện từ chối, nhưng không lộ thuê bao thuộc người khác.

Theo dõi episode quá deadline chưa reconcile, operation pending quá lâu, độ trễ outbox, bất nhất provider/local, xung đột version, lỗi ngân sách và số lần truy cập bị chặn sau pause.

Token hoặc cache được cấp trước pause có thể còn ghi quyền cũ. Đường chấp nhận thao tác trả phí phải có cách quan sát trạng thái có thẩm quyền hoặc generation quyền lợi hiện hành. Chỉ phát sự kiện xóa cache nhưng không kiểm soát độ trễ không bảo đảm đóng quyền ngay. Nếu sản phẩm chấp nhận một cửa sổ trễ, phải đưa nó thành cam kết rõ ràng của chính sách.

Sự kiện quyền lợi nên có version tăng đơn điệu theo thuê bao. Consumer bỏ qua version cũ để một sự kiện resume đến trễ không mở lại quyền sau một sự kiện pause hoặc hủy mới hơn. Dùng thời gian đến hoặc timestamp tự khai làm tiêu chí thay thế có thể đảo ngược trạng thái.

Reconciliation định kỳ tìm các trạng thái không khớp giữa episode, ngân sách, quyền lợi và nhà cung cấp. Công cụ sửa chữa nên thực thi command có audit và idempotency, thay vì sửa thẳng `paid_until` hoặc xóa episode để “làm sạch” dữ liệu.
