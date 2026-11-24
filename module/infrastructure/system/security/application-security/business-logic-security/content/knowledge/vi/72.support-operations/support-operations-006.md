# Support override duration — Giới hạn thời gian hiệu lực của quyền ngoại lệ hỗ trợ

## Mục tiêu và phạm vi

Support override là quyền ngoại lệ được cấp cho nhân viên hỗ trợ để vượt qua **một quy tắc nghiệp vụ cụ thể**, trong phạm vi đã được phê duyệt. Thời hạn override xác định khoảng thời gian quyền đó được phép tham gia vào quyết định thực hiện một thao tác.

Trong module bảo mật logic nghiệp vụ, mục tiêu không dừng ở việc thêm cột `expires_at`. Hệ thống phải bảo đảm quyền ngoại lệ không tồn tại quá lâu, không bị gia hạn ngầm, không chuyển sang đối tượng khác và không được dùng lại qua retry hoặc tác vụ chạy nền sau thời điểm chính sách cho phép.

Sau bài học, bạn có thể:

- Phân biệt thời hạn yêu cầu phê duyệt, thời hạn kích hoạt và thời hạn sử dụng override.
- Diễn đạt business invariants về hiệu lực, gia hạn và thu hồi.
- Thiết kế state machine gắn quyền với nhân viên, tenant, đối tượng và hành động.
- Kiểm tra thời gian tại ranh giới quyết định nghiệp vụ, phối hợp với transaction và idempotency.
- Xử lý cache, token, hàng đợi và cạnh tranh giữa thao tác sử dụng với thao tác thu hồi.
- Kiểm thử các mốc biên thời gian và các cách lạm dụng để kéo dài quyền.

Các con số trong bài là **chính sách minh họa**, không phải mức thời gian an toàn áp dụng chung cho mọi hệ thống.

## 1. Một quyền tạm thời có thể trở thành quyền thường trực như thế nào?

Giả sử khách hàng hết thời hạn tự sửa địa chỉ giao hàng. Nhân viên hỗ trợ có thể xin ngoại lệ để sửa địa chỉ của đơn hàng `order-1042` thuộc `tenant-A`, miễn là đơn chưa được bàn giao cho đơn vị vận chuyển.

Chính sách minh họa:

| Thuộc tính | Giá trị |
| --- | --- |
| Nhân viên được sử dụng | Nhân viên được chỉ định trong yêu cầu |
| Đối tượng | Một đơn hàng cụ thể trong một tenant |
| Hành động | Sửa địa chỉ giao hàng |
| Quy tắc được phép vượt qua | Đã hết thời hạn tự sửa địa chỉ |
| Điều kiện vẫn bắt buộc | Đúng tenant, đúng quyền hỗ trợ, đơn chưa bàn giao, địa chỉ hợp lệ |
| Hiệu lực ban đầu | Tối đa 10 phút kể từ khi kích hoạt |
| Thời gian được chờ kích hoạt | Tối đa 5 phút kể từ phê duyệt |
| Gia hạn | Tối đa một lần, thêm không quá 5 phút, cần phê duyệt riêng |
| Hạn cuối của cả chuỗi | Không muộn hơn 15 phút từ lần kích hoạt đầu |
| Số lần thay đổi thành công | Tối đa một lần cho toàn bộ chuỗi override |

Những lỗi sau có thể làm chính sách mất tác dụng:

- Backend chỉ kiểm tra `overrideEnabled = true`.
- Giao diện hết đếm ngược nhưng API vẫn chấp nhận thao tác.
- Mỗi request đặt lại `expiresAt = now + 10 phút`.
- Chỉ cron job chuyển trạng thái sang hết hạn; cron chạy trễ thì quyền còn dùng được.
- Tạo ticket mới để lấy một chuỗi override khác cho cùng nhu cầu.
- Worker coi thời điểm enqueue là bằng chứng được phép thực hiện bất kỳ lúc nào.
- Hai request đồng thời cùng dùng một quyền chỉ được sử dụng một lần.

Thời gian sống ngắn không bù được phạm vi quá rộng. Override 30 giây cho mọi đơn hàng của mọi tenant vẫn có thể gây thiệt hại lớn.

## 2. Phân biệt các loại thời hạn

### 2.1. Không gộp mọi mốc thành một trường timeout

| Mốc hoặc khoảng thời gian | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `requestExpiresAt` | Hạn cuối được duyệt yêu cầu đang chờ | Yêu cầu quá cũ phải được lập lại |
| `activationDeadline` | Hạn cuối được kích hoạt bản đã duyệt | Sau phê duyệt 5 phút |
| `activatedAt` | Thời điểm bắt đầu hiệu lực thực tế | Lần kích hoạt hợp lệ đầu tiên |
| `expiresAt` | Hạn dùng của phiên bản override hiện tại | Kích hoạt cộng thời lượng đã duyệt |
| `hardExpiresAt` | Hạn cuối không được vượt của cả chuỗi | Lần kích hoạt đầu cộng 15 phút |
| `revokedAt` | Mốc thu hồi sớm | Trưởng nhóm hủy ngoại lệ |
| Idle timeout, nếu có | Hạn do không có hoạt động đủ điều kiện | Áp dụng riêng cho loại grant cho phép nhiều thao tác |

Yêu cầu đang chờ không có quyền thao tác. Bản đã được phê duyệt nhưng chưa kích hoạt cũng không tự có thời hạn vô hạn để dùng bất kỳ lúc nào.

Một phiên đăng nhập còn sống không chứng minh override còn hiệu lực. Thời hạn token, thời hạn phiên và thời hạn override là các điều kiện khác nhau; khi chính sách yêu cầu cả ba, thao tác phải thỏa cả ba.

### 2.2. Định nghĩa khoảng hiệu lực bằng điều kiện rõ ràng

Trong bài này, hiệu lực thời gian là khoảng nửa kín:

~~~text
activatedAt <= decisionTime < effectiveExpiresAt
~~~

Trong đó:

~~~text
effectiveExpiresAt = min(
    expiresAt,
    hardExpiresAt,
    các hạn chặn bổ sung mà chính sách yêu cầu
)
~~~

Tại đúng `effectiveExpiresAt`, quyền đã hết hạn. Không dùng điều kiện `decisionTime <= expiresAt` nếu hợp đồng đã chọn mốc kết thúc loại trừ.

Ví dụ:

~~~text
Kích hoạt:       2026-11-22T03:00:00Z
Hết hạn:        2026-11-22T03:10:00Z

03:09:59Z       Có thể còn hợp lệ nếu thỏa các điều kiện khác
03:10:00Z       Hết hạn
03:10:01Z       Hết hạn
~~~

Mốc `03:00:00Z` có thể hiển thị thành 10:00 tại múi giờ UTC+7. Backend so sánh các thời điểm tuyệt đối, không so chuỗi giờ theo múi giờ trình duyệt.

Độ chính xác trong cơ sở dữ liệu, API và mã nguồn cần nhất quán. Nếu nơi lưu chỉ giữ đến giây, kiểm thử phải dùng chính độ chính xác đó, tránh hứa kiểm soát tới nano giây mà dữ liệu không lưu được.

### 2.3. Absolute timeout và idle timeout không thay thế nhau

Absolute timeout kết thúc quyền sau một hạn cố định. Idle timeout kết thúc quyền sau thời gian không có hoạt động hợp lệ.

Nếu có idle timeout:

~~~text
effectiveExpiresAt = min(
    expiresAt,
    hardExpiresAt,
    lastQualifyingUseAt + idleDuration
)
~~~

Polling, mở màn hình, nhận heartbeat hoặc request bị từ chối không nên làm mới thời gian hoạt động đủ điều kiện. Nếu mọi request đều kéo dài quyền, người dùng chỉ cần tạo lưu lượng đều đặn để duy trì ngoại lệ.

Trong ví dụ sửa địa chỉ chỉ được dùng một lần, một lần thay đổi thành công đã tiêu thụ quyền. Idle timeout không phải cơ chế chính; phần này hữu ích cho các loại override cho phép nhiều thao tác.

## 3. Business invariants cho thời hạn override

Một grant chỉ được sử dụng khi đồng thời thỏa các điều kiện:

~~~text
canUseOverride =
    actor vẫn có quyền hỗ trợ nền tảng cần thiết
    AND grant dành cho đúng actor
    AND actor, grant và đối tượng thuộc đúng tenant
    AND grant khớp loại đối tượng, objectId, action và quy tắc được vượt
    AND bản phê duyệt khớp phiên bản đang dùng
    AND trạng thái được phép sử dụng
    AND activatedAt <= decisionTime < effectiveExpiresAt
    AND chưa bị thu hồi
    AND chưa hết số lần sử dụng
    AND đối tượng vẫn thỏa các bất biến không được miễn trừ
~~~

Trong ví dụ, grant chỉ miễn kiểm tra “đã quá thời hạn khách hàng tự sửa”. Nó không miễn kiểm tra “đơn chưa bàn giao vận chuyển”, không cấp quyền hoàn tiền và không cho truy cập đơn hàng khác.

OWASP khuyến nghị kiểm tra quyền trên mỗi yêu cầu và từ chối mặc định. Với override, cần áp dụng điều đó cả trên đường thực thi thao tác có ngoại lệ; một lần kiểm tra lúc mở màn hình hỗ trợ không đủ. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#validate-the-permissions-on-every-request).

Những bất biến riêng về thời gian:

| Bất biến | Cách thực thi |
| --- | --- |
| Thời lượng phải hữu hạn và dương | Từ chối giá trị thiếu, bằng 0, âm hoặc vượt giới hạn |
| Client không tự cấp thời điểm bắt đầu | Backend tạo `activatedAt` khi kích hoạt hợp lệ |
| Không kích hoạt bản phê duyệt quá cũ | Kiểm tra `decisionTime < activationDeadline` |
| Không vượt hạn của chuỗi | Luôn có `expiresAt <= hardExpiresAt` |
| Không tự gia hạn khi dùng | API thao tác không được sửa `expiresAt` |
| Không phục hồi bản đã hết hạn | Bản hết hạn là trạng thái kết thúc của phiên bản đó |
| Gia hạn không tạo ngân sách sử dụng mới | Giữ nguyên root, hạn cứng và bộ đếm dùng chung |
| Thu hồi có ưu tiên chặn | Chưa đến hạn vẫn bị từ chối nếu đã thu hồi |
| Cleanup không quyết định quyền | Vẫn kiểm tra timestamp khi trạng thái lưu còn là `ACTIVE` |
| Retry không tạo quyền mới | Khóa idempotency không sinh lại thời hạn từ thời điểm retry |

Không dùng `null`, số cực lớn hoặc “hết hạn năm 9999” để biểu diễn ngoại lệ vận hành lâu dài. Nếu nghiệp vụ cần một vai trò thường trực, phải quản lý bằng mô hình quyền và quy trình đánh giá riêng.

## 4. Mô hình dữ liệu và state machine

### 4.1. Tách yêu cầu, phê duyệt và grant sử dụng

Có thể tổ chức ba loại dữ liệu:

| Loại dữ liệu | Nội dung chính |
| --- | --- |
| Override request | Người đề nghị, case, đối tượng, hành động, lý do, thời lượng mong muốn, hạn duyệt |
| Approval | Người duyệt, phạm vi và thời lượng đã duyệt, phiên bản yêu cầu, hạn kích hoạt, phiên bản chính sách |
| Override grant | Actor được dùng, scope, thời điểm kích hoạt, hạn hiện tại, hạn cứng, phiên bản, trạng thái |

Ngoài ra, một bản ghi gốc của chuỗi, gọi là `overrideRoot`, có thể giữ:

~~~text
rootId
tenantId + actorId + objectType + objectId + action + bypassRule
firstActivatedAt
hardExpiresAt
renewalCount
remainingUses
currentGrantVersion
businessEpisodeId
~~~

`businessEpisodeId` được backend xác định theo nhu cầu nghiệp vụ. Nó không phải một ticket ID tùy ý do client thay đổi để nhận ngân sách mới.

Phạm vi chính xác cần được chọn theo rủi ro. Ví dụ, giới hạn theo actor mà không giới hạn theo đối tượng có thể bị lách bằng việc chia sẻ nhiều tài khoản hỗ trợ; giới hạn chỉ theo ticket có thể bị lách bằng nhiều ticket.

### 4.2. State machine đề xuất

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: Đủ quyền và đúng phiên bản
    REQUESTED --> REJECTED: Từ chối
    REQUESTED --> CANCELLED: Hủy yêu cầu
    REQUESTED --> EXPIRED: Quá hạn duyệt
    APPROVED --> ACTIVE: Kích hoạt trước hạn
    APPROVED --> EXPIRED: Quá hạn kích hoạt
    APPROVED --> REVOKED: Thu hồi trước khi dùng
    ACTIVE --> CONSUMED: Dùng hết số lần cho phép
    ACTIVE --> EXPIRED: Đến hạn hiệu lực
    ACTIVE --> REVOKED: Thu hồi
    ACTIVE --> SUPERSEDED: Phiên bản gia hạn mới có hiệu lực
    SUPERSEDED --> [*]
    CONSUMED --> [*]
    EXPIRED --> [*]
    REVOKED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
~~~

Gia hạn là một yêu cầu và quyết định phê duyệt riêng. Nếu được duyệt, hệ thống tạo phiên bản mới của cùng chuỗi rồi chuyển phiên bản cũ sang `SUPERSEDED` trong cùng transaction. Không có endpoint tổng quát “đặt trạng thái về ACTIVE”.

Trạng thái `EXPIRED` có thể được materialize bởi job nền để phục vụ tra cứu. Quyền thực tế hết ngay khi điều kiện thời gian không còn đúng, kể cả job chưa chạy.

### 4.3. Chính sách kích hoạt và gia hạn của ví dụ

Khi kích hoạt lần đầu:

~~~text
firstActivatedAt = thời gian tin cậy tại quyết định kích hoạt
hardExpiresAt    = firstActivatedAt + 15 phút
expiresAt       = min(
    firstActivatedAt + approvedDuration,
    hardExpiresAt,
    hạn của quyền cha nếu có ràng buộc quyền cha
)

0 < approvedDuration <= 10 phút
~~~

Khi gia hạn:

~~~text
newExpiresAt = min(
    oldExpiresAt + approvedExtension,
    hardExpiresAt,
    hạn của quyền cha nếu có
)

0 < approvedExtension <= 5 phút
renewalCount trước gia hạn = 0
decisionTime < oldExpiresAt
newExpiresAt > oldExpiresAt
~~~

Quy tắc ví dụ cho phép gia hạn một lần khi bản hiện tại vẫn còn hiệu lực. `firstActivatedAt`, `hardExpiresAt` và số lượt sử dụng còn lại không được đặt lại.

Nếu phiên bản đã hết hạn, một phê duyệt gia hạn đến muộn không làm sống lại nó. Nhu cầu còn tồn tại phải đi qua yêu cầu mới và vẫn bị kiểm tra các giới hạn dùng chung cho cùng đợt xử lý nghiệp vụ.

Việc rút ngắn chính sách, khóa actor hoặc đóng case cũng có thể làm quyền ngừng dùng sớm. Ngược lại, nới chính sách hệ thống không tự kéo dài các grant đã cấp; thời hạn đã duyệt vẫn ràng buộc chúng.

## 5. API theo ý định nghiệp vụ và phê duyệt có giới hạn

### 5.1. Client đề nghị thời lượng, backend quyết định hiệu lực

Một request có thể như sau:

~~~http
POST /api/support/cases/case-204/override-requests
Idempotency-Key: request-address-change-204

{
  "objectType": "ORDER",
  "objectId": "order-1042",
  "action": "CHANGE_DELIVERY_ADDRESS",
  "requestedDurationSeconds": 600,
  "reasonCode": "CUSTOMER_CONFIRMED_CORRECTION"
}
~~~

Backend kiểm tra case, đối tượng, quan hệ với tenant, quyền đề nghị và mục đích hợp lệ. Tenant và danh tính người đề nghị lấy từ ngữ cảnh đã xác thực.

Không nhận các trường sau như nguồn thẩm quyền:

~~~json
{
  "approved": true,
  "activatedAt": "2026-11-22T03:00:00Z",
  "expiresAt": "2099-01-01T00:00:00Z",
  "renewalCount": 0,
  "bypassAllChecks": true
}
~~~

Schema ghi dữ liệu cần tránh mass assignment. Với trường thời lượng, phải kiểm tra kiểu, đơn vị, khoảng giá trị và tràn số trước khi cộng vào thời điểm. Không để số quá lớn biến thành hạn âm hoặc nhánh “không hết hạn”.

Nếu thời lượng đề nghị vượt giới hạn, API nên báo lỗi rõ ràng theo hợp đồng. Nếu sản phẩm chọn rút ngắn tự động, người đề nghị và người duyệt phải thấy chính thời lượng hiệu lực đã được rút ngắn.

### 5.2. Người duyệt phải duyệt cả phạm vi và thời hạn

Màn hình duyệt cần nêu:

- Ai được sử dụng quyền và cho đối tượng nào.
- Quy tắc nào được miễn, quy tắc nào vẫn bắt buộc.
- Thời lượng, hạn kích hoạt và hạn cuối của cả chuỗi.
- Số lần sử dụng, lịch sử gia hạn và lý do nghiệp vụ.
- Các điều kiện xác thực bổ sung nếu chính sách yêu cầu.

Người có quyền duyệt 10 phút không đương nhiên có quyền cấp 24 giờ. Tách quyền duyệt, kích hoạt, sử dụng, gia hạn và thu hồi khi nghiệp vụ cần phân tách trách nhiệm. Trong ví dụ, người đề nghị không được tự duyệt yêu cầu của mình.

Khi actor, đối tượng, action, quy tắc được miễn hoặc thời lượng thay đổi, cần xác định đó có còn là nội dung đã duyệt không. Không duyệt một request rồi cho phép sửa các trường này trước khi kích hoạt.

OWASP mô tả việc giới hạn thời gian cho ủy quyền giao dịch, kiểm soát trình tự trạng thái và có cổng kiểm tra gắn với thực thi. Bài này áp dụng các nguyên tắc đó để thiết kế quyền ngoại lệ hỗ trợ; các mức 5, 10 và 15 phút là lựa chọn minh họa của nghiệp vụ. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html#29-authorization-credentials-should-only-be-valid-during-a-limited-time-period).

## 6. Kiểm tra tại ranh giới quyết định nghiệp vụ

### 6.1. Chọn rõ lúc nào một thao tác được coi là đã được cấp quyền

Một request đến máy chủ trước hạn không đương nhiên được phép thực hiện sau khi chờ khóa hoặc nằm trong hàng đợi.

Trong ví dụ đồng bộ này, ranh giới quyết định là bước kiểm tra và chấp nhận thay đổi trong transaction, sau khi đã khóa các bản ghi cần thiết. Lấy `decisionTime` sát bước kiểm tra đó. Quyết định chỉ trở thành một thao tác thành công nếu transaction commit.

Hợp đồng này cho phép một thao tác đã được chấp nhận hợp lệ hoàn tất commit sau mốc hết hạn. Nó không cho phép các thao tác mới dùng lại grant sau mốc đó.

Nếu nghiệp vụ yêu cầu một ranh giới chặt hơn, chẳng hạn chấp nhận lệnh ngay trước dispatch ra hệ thống ngoài, phải đặt kiểm tra tại ranh giới đó và thiết kế việc phối hợp tương ứng. Không hứa “mọi tác động đều dừng đúng hạn” khi các tác động đã được gửi ra ngoài không thể thu hồi.

### 6.2. Transaction phối hợp quyền, số lượt và thay đổi nghiệp vụ

Luồng minh họa:

1. Xác thực actor và kiểm tra quyền tiếp cận case, đối tượng, thao tác.
2. Bắt đầu transaction và xử lý bản ghi idempotency bằng khóa duy nhất.
3. Khóa root của chuỗi, grant hiện hành và đơn hàng theo thứ tự thống nhất.
4. Lấy thời gian tin cậy sau khi đã chờ các khóa cần thiết.
5. Kiểm tra scope, phiên bản, hạn dùng, thu hồi, số lượt và trạng thái đơn.
6. Tiêu thụ một lượt từ root và cập nhật địa chỉ trong cùng transaction.
7. Lưu sự kiện kiểm toán, kết quả idempotency và outbox nếu cần.
8. Commit.

Nếu cập nhật địa chỉ thất bại và transaction rollback, việc tiêu thụ lượt cũng rollback. Nếu hai request cùng cạnh tranh lượt cuối, chỉ một request được chấp nhận thay đổi.

Khóa bản ghi grant không tự bảo vệ mọi bất biến. Điều kiện “đơn chưa bàn giao” cũng phải được phối hợp với luồng bàn giao. Quy trình bàn giao, thu hồi, gia hạn và dùng override cần dùng thứ tự khóa hoặc điều kiện phiên bản tương thích.

Không giữ transaction mở xuyên suốt lời gọi dịch vụ vận chuyển để giả lập tính nguyên tử. Hệ thống ngoài có thể đã nhận lệnh dù transaction trong ứng dụng sau đó thất bại.

### 6.3. Hết hạn, thu hồi và sử dụng đồng thời

Cần quy định thứ tự có ý nghĩa:

- Thu hồi được ghi nhận trước ranh giới chấp nhận thao tác: thao tác phải bị chặn.
- Thao tác đã được chấp nhận và commit theo thứ tự trước thu hồi: thu hồi không đảo ngược kết quả đã tạo.
- Hai thao tác cùng muốn dùng lượt cuối: tranh chấp phải được giải quyết nguyên tử.
- Gia hạn và sử dụng cùng lúc: không được có hai phiên bản hiện hành hoặc khôi phục số lượt đã dùng.

Có thể dùng khóa bản ghi, compare-and-set theo version hoặc cơ chế tuần tự hóa phù hợp. Điều quan trọng là tất cả đường ghi liên quan cùng tuân thủ một mô hình, không chỉ riêng endpoint hỗ trợ.

Nếu quyền nền tảng của actor có thể bị thu hồi ở một hệ thống khác, cần định nghĩa thêm cách đồng bộ và độ trễ chấp nhận. Khóa grant trong cơ sở dữ liệu không tự làm dữ liệu phân quyền ở mọi dịch vụ trở nên tức thời.

### 6.4. Idempotency không gia hạn quyền

Phân biệt hai tình huống sau thời điểm hết hạn:

| Tình huống | Cách xử lý |
| --- | --- |
| Một thao tác mới hoặc lần thử trước chưa tạo hiệu ứng nghiệp vụ | Phải kiểm tra grant tại ranh giới hiện tại; hết hạn thì từ chối |
| Retry đúng một thao tác đã commit thành công | Có thể trả lại kết quả đã lưu nếu actor hiện vẫn được phép xem kết quả; không chạy lại thay đổi |

Khóa idempotency cần được giới hạn theo tenant, actor và loại hành động. Lưu fingerprint của yêu cầu, bao gồm đối tượng, nội dung thay đổi và định danh override thích hợp. Cùng khóa nhưng payload khác phải được xử lý như xung đột.

Bản ghi idempotency cần có cơ chế claim và ràng buộc duy nhất để hai request không cùng xử lý lần đầu. Không chỉ thực hiện một phép đọc “chưa thấy khóa” rồi cho cả hai tiếp tục.

Đối với yêu cầu tạo grant, retry trả lại chính grant và các timestamp đã cấp trước đó. Không tạo một grant mới với `activatedAt = thời điểm retry`.

## 7. Ví dụ Java và điều kiện cập nhật nguyên tử

Các đoạn dưới là mã minh họa logic, không phải ứng dụng hoàn chỉnh. Repository, cơ chế transaction, tra cứu chính sách và nguồn thời gian phải được hiện thực phù hợp với hệ thống.

### 7.1. Một hàm kiểm tra thời gian có biên rõ ràng

~~~java
enum OverrideState {
    ACTIVE, EXPIRED, REVOKED, CONSUMED, SUPERSEDED
}

record OverrideGrant(
        UUID tenantId,
        UUID actorId,
        UUID orderId,
        String action,
        String bypassRule,
        OverrideState state,
        Instant activatedAt,
        Instant expiresAt,
        Instant hardExpiresAt,
        Instant revokedAt,
        long version) {}

void requireTimeValid(OverrideGrant grant, Instant decisionTime) {
    if (grant.state() != OverrideState.ACTIVE
            || grant.revokedAt() != null) {
        throw new OverrideDenied("OVERRIDE_NOT_ACTIVE");
    }

    if (grant.activatedAt() == null
            || grant.expiresAt() == null
            || grant.hardExpiresAt() == null
            || !grant.activatedAt().isBefore(grant.expiresAt())
            || grant.expiresAt().isAfter(grant.hardExpiresAt())) {
        throw new OverrideDenied("OVERRIDE_TIME_DATA_INVALID");
    }

    if (decisionTime.isBefore(grant.activatedAt())
            || !decisionTime.isBefore(grant.expiresAt())
            || !decisionTime.isBefore(grant.hardExpiresAt())) {
        throw new OverrideDenied("OVERRIDE_OUTSIDE_VALID_WINDOW");
    }
}
~~~

Hàm này không dựa riêng vào trạng thái `ACTIVE`. Một bản ghi có trạng thái chưa được cleanup vẫn bị chặn khi timestamp đã quá hạn.

Thời gian truyền vào phải đến từ nguồn được backend tin cậy. Không truyền `clientNow`, thời gian trong request hoặc timestamp lúc mở màn hình.

Không dùng Java `assert` cho kiểm soát bắt buộc, vì assertion có thể bị tắt. Vi phạm phải đi qua nhánh từ chối rõ ràng.

### 7.2. Kiểm tra thời gian chỉ là một phần của quyền

~~~java
void requireScope(
        Actor actor,
        Order order,
        OverrideGrant grant) {

    boolean sameTenant =
            actor.tenantId().equals(grant.tenantId())
            && order.tenantId().equals(grant.tenantId());

    boolean exactScope =
            actor.id().equals(grant.actorId())
            && order.id().equals(grant.orderId())
            && "CHANGE_DELIVERY_ADDRESS".equals(grant.action())
            && "SELF_SERVICE_ADDRESS_WINDOW".equals(grant.bypassRule());

    if (!sameTenant || !exactScope) {
        throw new OverrideDenied("OVERRIDE_SCOPE_MISMATCH");
    }

    supportPolicy.requireCurrentSupportPermission(actor, order);

    // Bất biến này không được miễn trừ bằng override.
    if (order.isHandedToCarrier()) {
        throw new OverrideDenied("ORDER_ALREADY_HANDED_TO_CARRIER");
    }
}
~~~

Đừng viết `if (grantValid) skipAllValidation()`. Cấu trúc nghiệp vụ cần chỉ ra đúng kiểm tra được thay thế:

~~~java
validateAddress(newAddress);
requireTenantAndObjectPermission(actor, order);
requireNotHandedToCarrier(order);

if (order.isSelfServiceAddressWindowClosed()) {
    requireValidAddressWindowOverride(actor, order, grant, decisionTime);
}

applyAddressChange(order, newAddress);
~~~

Nếu không cần dùng ngoại lệ vì thao tác đã được cho phép bằng luồng bình thường, xử lý theo chính sách bình thường; không tiêu thụ grant một cách vô nghĩa. Phải ghi nhận rõ kết quả được thực hiện theo quyền nào để kiểm toán.

### 7.3. Tiêu thụ lượt trong cùng transaction

Ví dụ SQL rút gọn cho root có tối đa một lượt dùng chung:

~~~sql
UPDATE support_override_root
SET remaining_uses = remaining_uses - 1,
    version = version + 1
WHERE id = :root_id
  AND tenant_id = :tenant_id
  AND actor_id = :actor_id
  AND current_grant_version = :grant_version
  AND revoked_at IS NULL
  AND hard_expires_at > :decision_time
  AND remaining_uses > 0
  AND version = :expected_root_version;
~~~

Chỉ chấp nhận nếu đúng một hàng được cập nhật. Cập nhật đơn hàng, lưu kết quả idempotency và sự kiện kiểm toán trong cùng transaction với phép trừ lượt này.

SQL trên **không phải toàn bộ kiểm tra cấp quyền**. Nó giả định grant hiện hành đã được đọc và khóa hoặc bảo vệ bằng điều kiện phiên bản, thời gian hiệu lực đã được kiểm tra, scope đã được đối chiếu và mọi luồng gia hạn/thu hồi cùng phối hợp với root. Nếu giả định đó không đúng, một phép UPDATE riêng lẻ không đủ bảo vệ.

Với optimistic concurrency, xung đột phải dẫn đến đọc lại và đánh giá lại bằng thời gian mới. Không tiếp tục dùng `decisionTime` cũ sau một chuỗi chờ và retry kéo dài.

## 8. Nguồn thời gian, cache và token

### 8.1. Nguồn thời gian là một phần của ranh giới tin cậy

Lưu thời điểm tuyệt đối, thường biểu diễn bằng UTC, và sử dụng nguồn thời gian thống nhất cho các quyết định liên quan.

Trong ứng dụng đơn giản, có thể inject `Clock` để lấy `Instant` và kiểm thử. Trong hệ thống nhiều node, cần quyết định một nguồn có thẩm quyền, ví dụ thời gian của thành phần thực hiện chuyển trạng thái nguyên tử, thay vì mặc định đồng hồ của mọi node hoàn toàn trùng nhau.

Những điểm cần xử lý:

- Đồng bộ đồng hồ và theo dõi độ lệch.
- Lấy mẫu thời gian sau thời gian chờ khóa, không tái sử dụng mẫu từ đầu request.
- Chuẩn hóa độ chính xác khi lưu và so sánh.
- Phát hiện các bước nhảy thời gian bất thường.
- Với thao tác nhạy cảm, từ chối khi không thể xác định thời gian trong giới hạn tin cậy đã đặt ra.

Không tự cộng “grace period” vào hạn override để che độ lệch đồng hồ. Nếu cần dung sai, nó phải là một phần được công bố của chính sách; dung sai chấp nhận sau hạn chính là một phần thời gian quyền còn có thể được dùng.

Đồng hồ đơn điệu có ích cho đo khoảng thời gian trong một tiến trình, nhưng không thay thế timestamp dùng chung giữa node và qua các lần khởi động lại. Nếu đồng hồ quay lùi, một grant có trạng thái `ACTIVE` cũ có thể trông như còn hạn; cần kết hợp nguồn thời gian tin cậy, xử lý bất thường và trạng thái kết thúc được bảo vệ khỏi phục hồi.

### 8.2. Cache không được làm quyền sống lâu hơn

Một cache chứa kết quả `canOverride = true` trong 30 phút có thể vô hiệu hóa một grant chỉ sống 10 phút.

Nếu dùng cache, nên giữ cả định danh, version, trạng thái và timestamp cần thiết, đồng thời kiểm tra hạn tại mỗi lần dùng. Hạn cache dương không nên muộn hơn hạn hiệu lực của grant. Tuy nhiên, điều này chỉ giải quyết hết hạn theo thời gian, chưa giải quyết thu hồi sớm.

Muốn cam kết thu hồi tức thời tại ranh giới chấp nhận, cần kiểm tra trạng thái có thẩm quyền hoặc có cơ chế phối hợp tương đương. Sự kiện invalidation đến muộn không tạo được cam kết đó. Nếu chấp nhận độ trễ thu hồi, phải định nghĩa và đo được giới hạn của nó.

Không fallback sang “cho phép” khi cache hoặc dịch vụ phân quyền lỗi. Một hệ thống hỗ trợ bị gián đoạn cần quy trình dự phòng có kiểm soát, không phải quyền ngoại lệ tự động vô hạn.

### 8.3. Token ký số vẫn có thể mang quyền đã lỗi thời

Một token chứa:

~~~json
{
  "overrideId": "override-81",
  "grantVersion": 2,
  "objectId": "order-1042",
  "action": "CHANGE_DELIVERY_ADDRESS",
  "exp": 1795317000
}
~~~

Chữ ký giúp phát hiện sửa payload khi được xác minh đúng, nhưng không tự cho biết grant đã bị thu hồi, dùng hết lượt hay thay phiên bản chưa.

Nếu token chỉ là tham chiếu, dịch vụ cần đối chiếu trạng thái hiện hành. Nếu thiết kế capability tự chứa để dùng offline, phải chấp nhận và giới hạn khả năng không thu hồi ngay; mô hình đó cần quyết định rủi ro riêng.

Token dài hạn của phiên không được mang một claim `supportOverride = true` rồi bỏ qua bản ghi grant. Khi tạo quyền con hoặc token ủy quyền cho worker, phạm vi và thời hạn không được rộng hơn quyền cha theo hợp đồng đã chọn.

## 9. Tác vụ chạy nền: quyền còn hạn lúc enqueue có đủ không?

### 9.1. Chọn một hợp đồng rõ ràng

Có hai mô hình khác nhau:

| Mô hình | Điều kiện thời gian | Hệ quả |
| --- | --- | --- |
| Worker cần dùng override khi thực thi | Worker kiểm tra lại quyền tại ranh giới thực thi đã chọn | Enqueue trước hạn nhưng chạy sau hạn vẫn có thể bị từ chối |
| Thao tác nghiệp vụ đã được chấp nhận hợp lệ, worker chỉ giao hiệu ứng đã commit | Quyền được kiểm tra khi chấp nhận lệnh nghiệp vụ; worker chỉ giao đúng lệnh đó | Hết hạn không nhất thiết hủy hiệu ứng đã được chấp nhận trước đó |

Ví dụ, nếu “đổi địa chỉ” chưa được chấp nhận vào miền nghiệp vụ và job chỉ chứa ý định gọi API đổi địa chỉ sau này, worker không được coi một lần kiểm tra tại enqueue là quyền vô hạn.

Nếu địa chỉ mới đã được chấp nhận và lưu hợp lệ trong transaction trước hạn, outbox có thể chỉ làm nhiệm vụ đồng bộ chính thay đổi đó đến hệ thống khác. Việc giao outbox sau hạn không tự động là một lần dùng override mới.

Mô hình thứ hai không được dùng làm cách lách: tạo một lệnh tổng quát “được sửa mọi thứ trong tương lai” ngay trước hạn. Lệnh được chấp nhận phải đóng băng đúng actor, tenant, đối tượng, hành động, dữ liệu và định danh thao tác.

### 9.2. Không làm mới thời hạn trong queue hoặc retry

Payload tham chiếu có thể gồm:

~~~text
operationId
tenantId
actorId
objectId
action
overrideRootId
grantVersion
operationPayloadHash
authorizationDecisionId
~~~

Queue không tự là nguồn thẩm quyền cho các trường này. Worker phải truy xuất hoặc xác minh bản ghi đã được backend bảo vệ, kiểm tra đúng hợp đồng và không cho publisher tùy ý tự dựng bằng chứng cấp quyền.

Các lỗi cần tránh:

- Dequeue rồi tính lại `expiresAt = now + originalDuration`.
- Retry bằng một override ID mới mà không có phê duyệt.
- Thay payload nhưng giữ quyết định cấp quyền cũ.
- Gộp các công việc của nhiều đối tượng dưới một grant đơn lẻ.
- Gia hạn token worker lâu hơn quyền cha trong mô hình cần quyền cha khi thực thi.
- Coi lỗi timeout là bằng chứng hệ thống ngoài chắc chắn chưa làm gì.

Với lời gọi ra hệ thống ngoài, cần idempotency hoặc đối soát theo `operationId` và khả năng của hệ thống đích. Transaction và outbox không tự bảo đảm hiệu ứng bên ngoài xảy ra đúng một lần.

### 9.3. Thu hồi không đồng nghĩa hoàn tác

Sau khi thu hồi, hệ thống phải ngăn những quyết định mới thuộc phạm vi bị thu hồi theo ranh giới đã cam kết.

Đối với lệnh đã được chấp nhận trước đó, cần có chính sách riêng: tiếp tục giao, hủy trước dispatch hoặc đưa vào xử lý thủ công. Nếu cần hủy, worker và thao tác hủy phải phối hợp để xác định thứ tự trước khi lệnh ra ngoài.

Nếu hệ thống vận chuyển đã nhận thay đổi, việc đặt grant thành `REVOKED` không tự đảo ngược địa chỉ. Hoàn tác, nếu được nghiệp vụ cho phép, là thao tác mới cần quyền và kiểm tra trạng thái hiện tại.

## 10. Những cách kéo dài hoặc tái sử dụng quyền cần kiểm thử

### 10.1. Ma trận tình huống lạm dụng

| Tình huống | Kết quả cần có |
| --- | --- |
| Sửa `requestedDurationSeconds` thành số âm, 0, thiếu, sai kiểu hoặc rất lớn | Từ chối rõ ràng, không tạo quyền không hết hạn hoặc bị tràn số |
| Gửi thêm `expiresAt`, `approved` hoặc `bypassAllChecks` | Không làm thay đổi thẩm quyền theo dữ liệu client |
| Kích hoạt tại đúng `activationDeadline` | Từ chối theo khoảng thời gian đã định nghĩa |
| Dùng grant trước `activatedAt` | Từ chối |
| Dùng tại đúng `expiresAt` | Từ chối |
| Job cleanup chưa chạy, trạng thái vẫn `ACTIVE` nhưng đã quá hạn | Vẫn từ chối |
| Duy trì polling hoặc request bị từ chối | Không gia hạn `expiresAt`; không làm mới idle timeout trái chính sách |
| Đổi object ID hoặc action trong request sử dụng | Bị chặn vì sai scope |
| Nhân viên khác hoặc tenant khác dùng lại grant ID | Bị chặn dù grant còn hạn |
| Đơn đã bàn giao nhưng grant vẫn còn 8 phút | Bị chặn vì bất biến không được miễn trừ |
| Duyệt 10 phút rồi sửa request thành 60 phút trước kích hoạt | Bản duyệt không còn khớp hoặc sửa đổi bị từ chối |
| Gia hạn hai request đồng thời | Không vượt số lần gia hạn hoặc tạo hai phiên bản hiện hành |
| Gia hạn được duyệt nhưng tới lúc áp dụng grant đã hết hạn | Không phục hồi grant cũ |
| Tạo ticket mới cho cùng đợt xử lý | Giới hạn dùng chung không bị đặt lại |
| Gia hạn sau khi đã dùng hết lượt | Không khôi phục quyền sử dụng |
| Request đến trước hạn nhưng chờ khóa qua hạn | Đánh giá bằng thời gian tại ranh giới quyết định mới |
| Thu hồi commit trước ranh giới chấp nhận thao tác | Thao tác bị chặn |
| Hai request khác nhau cùng dùng lượt cuối | Tối đa một thay đổi thành công |
| Retry đúng thao tác đã thành công sau khi grant hết hạn | Không chạy lại thay đổi; chỉ trả kết quả nếu còn quyền xem |
| Cùng idempotency key nhưng đổi địa chỉ đích | Lỗi xung đột, không tạo thay đổi mới |
| Token chưa hết hạn nhưng grant đã thu hồi hoặc thay version | Bị chặn trong mô hình kiểm tra trạng thái hiện hành |
| Node có cache cũ hoặc đồng hồ lệch | Không vượt bảo đảm thời hạn và thu hồi đã công bố |
| Job chạy sau hạn | Hành vi đúng mô hình thực thi hoặc giao lệnh đã chọn |
| Timeout sau khi hệ thống ngoài đã nhận lệnh | Đối soát hoặc retry có kiểm soát; không tạo ý định mới |

Khi kiểm thử hành vi từ chối, không chỉ kiểm tra HTTP status. Cần xác nhận không đổi dữ liệu nghiệp vụ, không tiêu thụ sai lượt, không tạo outbox thực thi và không làm mới thời hạn.

### 10.2. Kiểm thử thời gian không cần chờ thật

Tách nguồn thời gian khỏi logic giúp kiểm thử xác định. Với hàm nhận trực tiếp `Instant`, có thể dùng ba mốc quanh hạn:

~~~java
Instant start = Instant.parse("2026-11-22T03:00:00Z");
Instant end = start.plusSeconds(600);

// Trước hạn: hợp lệ về thời gian.
requireTimeValid(grant, end.minusSeconds(1));

// Đúng hạn: phải bị từ chối.
expectDenied(() -> requireTimeValid(grant, end));

// Sau hạn: phải bị từ chối.
expectDenied(() -> requireTimeValid(grant, end.plusSeconds(1)));
~~~

Ví dụ giả định `grant` đang ACTIVE, bắt đầu tại `start`, có `expiresAt = end` và `hardExpiresAt >= end`; `expectDenied` là helper minh họa. Những điều kiện khác như scope, thu hồi và lượt dùng cần có kiểm thử riêng.

Có thể inject `Clock` cố định hoặc clock có thể điều khiển cho service. Không dùng `sleep(600000)` để kiểm thử quyền 10 phút.

Kiểm thử biên thêm cho thời điểm kích hoạt, hạn cứng của chuỗi và độ chính xác thực tế của cơ sở dữ liệu. Với thời điểm bằng nhau, kỳ vọng phải nhất quán trên mọi đường API.

### 10.3. Kiểm thử cạnh tranh phải kiểm tra kết quả nghiệp vụ

Dùng các điểm đồng bộ trong kiểm thử để chủ động tạo thứ tự:

1. Request sử dụng đã đọc thông tin nhưng chưa vượt ranh giới quyết định.
2. Request thu hồi hoặc gia hạn được phép chạy tới bước ghi cần kiểm tra.
3. Cho request sử dụng tiếp tục.
4. Xác nhận kết quả theo thứ tự được hợp đồng cho phép.

Các thuộc tính hữu ích:

~~~text
successfulUses(root) <= approvedMaxUses(root)

expiresAt(version) <= hardExpiresAt(root)

không có quyết định mới hợp lệ nếu decisionTime >= effectiveExpiresAt

retry không thay đổi firstActivatedAt hoặc hardExpiresAt

các version cùng root không tạo thêm ngân sách sử dụng
~~~

Ở mô hình nhiều node, chạy các request qua nhiều instance để tránh vô tình chỉ kiểm thử một khóa trong bộ nhớ. Một khóa `synchronized` trong một JVM không bảo vệ được các node khác.

Property-based testing có thể sinh các chuỗi yêu cầu, duyệt, kích hoạt, gia hạn, thu hồi và retry. Cần kiểm tra bất biến trên mọi bước, thay vì chỉ kiểm tra một đường đi thuận lợi.

## 11. Kiểm toán và vận hành vòng đời

### 11.1. Ghi lại quyết định, không chỉ trạng thái cuối

Một audit event có thể bao gồm:

~~~text
eventId, operationId, occurredAt, decisionTime
tenantId, actorId, approverId
caseId, businessEpisodeId, rootId, grantId, grantVersion
objectType, objectId, action, bypassRule
approvedDuration, activatedAt, previousExpiresAt, newExpiresAt
hardExpiresAt, renewalCount, policyVersion
decision, reasonCode
~~~

Phân biệt thời điểm sự kiện được ghi hoặc thu thập với thời điểm quyết định cấp quyền. Điều này giúp điều tra một thao tác được chấp nhận sát hạn nhưng sự kiện tới hệ thống log muộn.

Không ghi token truy cập, bí mật xác thực hoặc địa chỉ đầy đủ nếu không cần cho mục đích kiểm toán. Quyền xem audit cũng phải được giới hạn theo vai trò và tenant thích hợp.

Lưu dấu vết trước và sau khi gia hạn, người phê duyệt, căn cứ thay đổi và phiên bản chính sách. Nếu chỉ lưu `expiresAt` mới nhất, rất khó nhận ra chuỗi gia hạn liên tiếp.

Sự kiện kiểm toán cần được lưu bền cùng quyết định nghiệp vụ hoặc có cơ chế giao đáng tin cậy. Một lệnh ghi log ra mạng bị mất không nên làm biến mất lịch sử cấp và dùng quyền nhạy cảm.

### 11.2. Theo dõi hành vi kéo dài quyền

Những tín hiệu đáng quan sát:

- Tỷ lệ yêu cầu gia hạn và số lần chạm hạn cứng.
- Nhiều case cho cùng actor, đối tượng, hành động trong một đợt xử lý.
- Nỗ lực sử dụng sau hạn hoặc sau thu hồi.
- Tranh chấp version, lượt dùng hoặc idempotency.
- Job bị chặn vì hết hạn khi chờ hàng đợi.
- Độ trễ invalidation và độ lệch đồng hồ.
- Grant có timestamp bất thường, thiếu hạn hoặc vượt giới hạn chính sách.

Không coi mọi bản ghi `ACTIVE` quá hạn là một lần sử dụng trái phép: có thể chỉ là cleanup chậm. Cần phân biệt dữ liệu trạng thái chưa cập nhật với một quyết định thực thi đã sai.

Ngược lại, một dashboard hiển thị “đã hết hạn” không chứng minh đường API thật sự chặn. Có thể dùng kiểm tra vận hành trong môi trường kiểm soát để xác minh hành vi tại ranh giới cấp quyền.

### 11.3. Break-glass vẫn cần thời hạn

Trong tình huống khẩn cấp, quy trình có thể khác quy trình hỗ trợ thường ngày, nhưng phải xác định rõ:

- Ai được kích hoạt và bằng phương thức xác thực nào.
- Phạm vi khẩn cấp và thời lượng tối đa.
- Giới hạn bất biến vẫn không được vượt.
- Người nhận cảnh báo và người kiểm tra lại sau sự kiện.
- Cách thu hồi hoặc hết hạn mà không phụ thuộc việc người dùng nhớ tắt.

Không biến cờ `emergency = true` thành nhánh bỏ qua mọi kiểm tra thời gian. Nếu cơ chế cấp quyền chính bị lỗi, phương án dự phòng cũng cần dữ liệu thẩm quyền và cách thực thi có thể kiểm chứng.

### 11.4. Khi phát hiện quyền tồn tại quá lâu

Ưu tiên ngăn các quyết định sử dụng mới: thu hồi các root liên quan, chặn gia hạn hoặc tạm vô hiệu hóa đúng loại override theo khả năng vận hành.

Sau đó xác định các grant, thời hạn đã cấp, version, quyết định sử dụng, actor và đối tượng bị ảnh hưởng. Với lệnh đang chờ hoặc đã gửi ra ngoài, xử lý theo hợp đồng tác vụ nền và khả năng hủy thực tế.

Không xóa dấu vết hoặc giả định đổi timestamp sẽ đảo ngược các thay đổi đã thành công. Nếu cần khắc phục dữ liệu, thực hiện bằng quy trình nghiệp vụ riêng với quyền và kiểm toán phù hợp.

## 12. Những quyết định cần chốt trước khi triển khai

Một thiết kế có thể kiểm chứng phải trả lời được:

1. Override miễn đúng quy tắc nào, trên đối tượng và hành động nào?
2. Ai được đề nghị, duyệt, kích hoạt, dùng, gia hạn và thu hồi?
3. Thời hạn bắt đầu từ lúc nào, kết thúc tại biên nào và lấy thời gian từ đâu?
4. Gia hạn bị giới hạn theo từng grant, cả chuỗi và cùng đợt xử lý như thế nào?
5. Ranh giới chấp nhận thao tác nằm ở đâu khi có khóa, queue và dịch vụ ngoài?
6. Thu hồi, retry và nhiều request đồng thời phối hợp bằng trạng thái nào?
7. Những bằng chứng nào xác nhận quyền đã hết hiệu lực trên đường thực thi thật?

Thời hạn override là một điều kiện cấp quyền phải được backend thực thi xuyên suốt vòng đời nghiệp vụ. Bộ đếm trên giao diện, TTL của cache hay job cleanup chỉ hỗ trợ vận hành; chúng không tự thay thế quyết định đó.
