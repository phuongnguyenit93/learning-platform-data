# Entitlement cache freshness: Bảo đảm dữ liệu quyền lợi đủ mới

## 1. Vì sao độ mới của cache là vấn đề bảo mật nghiệp vụ?

Trong chương **Entitlement Rules**, entitlement là quyền lợi sản phẩm mà một chủ thể được hưởng: dùng tính năng xuất báo cáo, truy cập nội dung trả phí, có thêm seat hoặc sử dụng một loại tài nguyên. Quyền lợi có thể đến từ gói thuê bao, hợp đồng, khoản mua thêm hoặc quyết định cấp quyền có thời hạn.

Cache giúp giảm độ trễ và tải đọc. Tuy nhiên, một bản cache hợp lệ về định dạng vẫn có thể không còn đúng về nghiệp vụ: gói đã bị hủy, tính năng đã bị thu hồi, thành viên đã rời tenant hoặc thời hạn quyền lợi đã kết thúc.

Bài thuộc phạm vi **SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY**: bảo vệ business invariant, state machine, quyền theo đối tượng, transaction và idempotency trước các chuỗi thao tác lạm dụng. Với cache entitlement, câu hỏi bảo mật là:

> Tại thời điểm thực hiện thao tác này, hệ thống có bằng chứng nào cho phép dùng bản quyền lợi đang giữ?

Ví dụ, người dùng làm nóng cache quyền xuất dữ liệu, sau đó bị thu hồi quyền nhưng tiếp tục gọi API qua các máy chủ còn bản cũ. Nếu API cho phép mọi cache hit mà không xét độ mới, cơ chế thu hồi trên DB không còn đủ để bảo vệ hành vi thực tế.

OWASP khuyến nghị mặc định từ chối và kiểm tra quyền trên mọi request. Kiểm tra qua cache vẫn phải đáp ứng chính sách quyền và độ mới, không chỉ chứng minh một lần rằng người dùng từng có quyền. Xem [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## 2. Xác định chính xác thứ gì đang được cache

Không phải dữ liệu nào có chữ “quyền” cũng có cùng phạm vi:

| Dữ liệu | Ví dụ | Điều cache đó chưa chứng minh |
| --- | --- | --- |
| Entitlement snapshot | Tenant có tính năng export, giới hạn 20 seat | Người dùng được xuất đối tượng cụ thể |
| Membership/role | Người dùng là quản trị tenant A | Gói A còn quyền lợi trả phí |
| Quyền theo đối tượng | Người dùng được xem báo cáo R | Quyền dùng tính năng export vẫn còn |
| Quyết định cuối cùng | Cho phép U export R trong ngữ cảnh C | Các điều kiện sẽ còn đúng ở request sau |
| Quota còn lại | Còn 3 lượt export | Hai request song song đều có thể tiêu cùng lượt |
| Token đã ký | Có claim `export=true` | Claim chưa bị lỗi thời hoặc thu hồi |

Bài dùng cache **snapshot entitlement theo tenant, chủ thể và ứng dụng nhận quyền**. Quyền theo đối tượng, điều kiện phiên và lượng quota động vẫn được kiểm tra ở lớp phù hợp.

Nếu cache quyết định cuối cùng, key và thông tin phiên bản phải bao phủ mọi đầu vào quyết định: subject, tenant, action, resource, policy và các thuộc tính ngữ cảnh có ảnh hưởng. Bỏ một đầu vào có thể khiến kết quả của người này hoặc tài nguyên này được dùng cho đối tượng khác.

Ngay cả entitlement mới nhất cũng không cho phép vượt business invariant. Có tính năng mời thành viên không đồng nghĩa có thể tạo seat thứ 21 khi hợp đồng chỉ mua 20 seat. Cạnh tranh quota phải được kiểm soát nguyên tử tại điểm ghi.

## 3. Một sự cố thu hồi quyền điển hình

Giả sử tenant `T1` có người dùng `U1` và quyền xuất dữ liệu:

| Mốc | Sự kiện |
| --- | --- |
| 10:00:00 | Node A cache snapshot revision 42, có quyền export |
| 10:00:02 | Quản trị thu hồi quyền; DB commit revision 43 |
| 10:00:03 | Event invalidation chưa đến node A |
| 10:00:04 | U1 gọi export qua A, cache revision 42 vẫn tồn tại |
| 10:00:05 | Invalidation mới đến A |

Nếu export là thao tác yêu cầu quyền hiện hành tại điểm chấp nhận công việc, request lúc 10:00:04 không được chỉ dựa vào revision 42.

Giảm TTL giúp giới hạn một phần thời gian sai lệch nhưng không tự tạo bảo đảm thu hồi tức thời. Một TTL một giây vẫn để lại cửa sổ một giây nếu không có cơ chế kiểm tra tại nguồn. Ngược lại, một event đến rất nhanh trong đa số lần không chứng minh giới hạn tối đa khi mạng lỗi.

Cần tách ba khái niệm:

- **TTL lưu trữ:** cache giữ entry bao lâu trước khi loại bỏ.
- **Giới hạn độ cũ được chấp nhận:** quyết định được dùng dữ liệu cũ tối đa bao lâu.
- **Độ trễ thu hồi thực tế:** từ lúc thay đổi có hiệu lực đến lúc đường thực thi ngừng dùng quyền cũ.

TTL của một lớp cache chỉ là một thành phần của hai đại lượng còn lại.

## 4. Hợp đồng về độ mới

### 4.1. Chọn yêu cầu theo thao tác

Các con số dưới đây là giả định thiết kế để minh họa, không phải chuẩn áp dụng cho mọi sản phẩm:

| Loại thao tác | Hợp đồng mẫu | Đường xử lý |
| --- | --- | --- |
| Hiển thị nhãn gói/tính năng trên giao diện | Có thể chậm tối đa 30 giây | Cache có tuổi nguồn bị giới hạn |
| Đọc một tính năng ít nhạy cảm đã được sản phẩm chấp thuận | Có thể dùng snapshot cũ tối đa 5 giây | Kiểm tra deadline và phạm vi mỗi lần dùng |
| Xuất dữ liệu nhạy cảm, thay đổi quyền, chấp nhận lệnh có chi phí | Quyền phải đúng tại điểm phân xử nghiệp vụ | Kiểm tra nguồn có thẩm quyền cùng transaction hoặc giao thức tương đương |
| Kết quả không có quyền | Có thể cache ngắn, ví dụ 2 giây | Không để negative cache chặn quyền mới quá cam kết |

Cache cho giao diện không phải bằng chứng cấp quyền cho API. Một request gửi được từ nút còn hiện trên giao diện vẫn phải qua kiểm tra phía máy chủ.

Với thao tác dùng dữ liệu cũ có giới hạn, sản phẩm phải chấp nhận rõ khoảng trễ sau thu hồi. Không đặt tên “real-time” cho một thiết kế chỉ dựa trên event và TTL.

### 4.2. Tuổi dữ liệu tính từ nguồn

Một entry nên lưu:

~~~text
tenant_id, subject_id, audience
revision, schema_version, policy_model_version
source_verified_at
fresh_until
next_transition_at
entitlements
~~~

`source_verified_at` là mốc snapshot được xác minh trên nguồn có thẩm quyền theo giao thức đã chọn. Nó không phải thời điểm copy dữ liệu từ Redis sang RAM.

Ví dụ B là độ cũ tối đa và ε là biên dự phòng cho sai lệch thời gian đã được kiểm soát:

~~~text
fresh_until = min(
    source_verified_at + B - ε,
    next_transition_at
)
~~~

Điều kiện sử dụng là `decision_at < fresh_until`; tại đúng deadline phải xác minh lại. Cần `B > ε` và quy tắc đồng bộ thời gian phù hợp. Nếu không chứng minh được biên sai lệch, không thể tuyên bố một giới hạn thời gian cứng chỉ bằng so sánh đồng hồ.

Một primary read cũng cần hợp đồng snapshot: timestamp xác minh phải ứng với dữ liệu nhất quán đã đọc. Không lấy dữ liệu từ transaction snapshot cũ rồi gắn nhãn “vừa xác minh” bằng thời gian hiện tại.

Đọc từ replica bị trễ và đặt `source_verified_at = now` có thể che tuổi thật của dữ liệu. Replica chỉ được dùng cho cam kết độ mới khi có bằng chứng nó đã bắt kịp mốc/revision cần thiết; số đo lag trung bình không chứng minh điều đó.

### 4.3. Không làm mới tuổi dữ liệu khi copy giữa các lớp

Giả sử L2 có entry đã được xác minh cách đây 25 giây, hợp đồng cho phép 30 giây. Khi L1 lấy entry đó, L1 chỉ còn tối đa 5 giây, trừ biên dự phòng; không được cấp lại 30 giây.

Những thao tác sau không được kéo dài thời hạn cấp quyền:

- Cache hit.
- Copy L2 sang L1.
- Refresh token dựa nguyên claim cũ.
- Retry request.
- Ghi lại một snapshot cũ vào key mới.
- Phát lại event cũ hoặc phục hồi cache từ backup.

Có thể giữ entry quá `fresh_until` để hỗ trợ quan sát hoặc phối hợp refresh, nhưng entry đó không còn đủ điều kiện cấp quyền theo hợp đồng cũ.

### 4.4. Thời gian tự làm thay đổi quyền dù revision không đổi

Một grant có hiệu lực từ 12:00 hoặc hết hạn lúc 18:00 có thể thay đổi quyết định mà không có một lần ghi DB mới tại mốc đó.

`next_transition_at` phải xét mốc nghiệp vụ gần nhất có thể thay đổi kết quả: bắt đầu/kết thúc grant, kết thúc trial, pause/resume đã lên lịch hoặc hạn hợp đồng. Nếu mốc đã tới, tính lại; không chỉ đẩy deadline về tương lai.

Không kéo TTL qua hạn grant. Không chờ một job phát event “đã hết hạn” mới dừng cấp quyền.

## 5. Phạm vi cache và version

### 5.1. Key phải tách đúng chủ thể

Một key snapshot có thể có dạng:

~~~text
entitlement:{tenant_id}:{subject_id}:{audience}:{schema_version}:{policy_model_version}
~~~

Các thành phần cần biểu diễn chuẩn hóa, tránh va chạm do ghép chuỗi tùy tiện. Tenant và subject được xác định từ phiên/ngữ cảnh đã được xác thực, không lấy một header tùy ý rồi coi là có quyền.

Nếu snapshot thực sự chỉ theo tài khoản chung và không phụ thuộc người dùng, có thể tách dữ liệu quyền lợi tài khoản khỏi dữ liệu membership. Khi đó mọi request vẫn phải kiểm tra người dùng hiện tại thuộc tài khoản ấy.

Không lưu `allow=true` vào key chỉ có `user_id` nếu kết quả còn phụ thuộc tenant, ứng dụng, resource hoặc action.

### 5.2. Một revision chỉ có ý nghĩa khi bao phủ đủ đầu vào

Ví dụ đơn giản dùng `entitlement_revision` tăng đơn điệu theo aggregate `(tenant, subject, audience)`. Mọi thay đổi có thể ảnh hưởng snapshot phải đồng thời cập nhật revision trong cùng transaction tại nguồn.

Nếu quyền còn phụ thuộc chính sách chung của tenant, membership hoặc catalog plan mà không cùng aggregate, cần phiên bản phụ thuộc tương ứng, chẳng hạn:

~~~text
subject_entitlement_revision
tenant_policy_revision
membership_revision
policy_model_version
~~~

Không cộng các revision thành một con số rồi so lớn/nhỏ. So sánh từng chiều theo giao thức đã định. Một event về grant không chứng minh membership còn hiện hành.

Trong phần ví dụ transaction ở bài, giả định nguồn đã gom đầy đủ đầu vào entitlement vào aggregate có revision chung. Quyền đối tượng và những điều kiện khác vẫn được kiểm tra riêng dưới phạm vi đồng bộ cần thiết.

### 5.3. Revision mới nhất đã biết chưa chắc là mới nhất tại nguồn

Giả sử node biết revision tối thiểu là 42 và entry cũng là 42. Điều đó không chứng minh DB chưa có 43; event 43 có thể chưa đến.

Một watermark local chỉ giúp bác bỏ revision cũ hơn điều node đã biết. Để có quyền hiện hành cho thao tác nghiêm ngặt, phải kiểm tra revision trên nguồn có thẩm quyền hoặc có một cơ chế đồng bộ với bảo đảm tương đương.

Khi phục hồi dữ liệu, không reset revision rồi tái sử dụng các key cũ. Có thể dùng thêm epoch triển khai/khôi phục để phân biệt các thế hệ dữ liệu và vô hiệu hóa snapshot từ thế hệ trước.

## 6. State machine cho vòng đời entry

~~~mermaid
stateDiagram-v2
    [*] --> Missing
    Missing --> Loading: Đọc nguồn
    Loading --> Usable: Đủ phạm vi, thời hạn và version
    Loading --> Missing: Nạp lỗi hoặc generation đổi
    Usable --> Stale: Chạm fresh_until hoặc mốc nghiệp vụ
    Usable --> Invalidated: Biết revision mới hơn
    Usable --> Unknown: Mất bằng chứng độ mới
    Stale --> Loading: Xác minh lại
    Invalidated --> Loading: Nạp revision phù hợp
    Unknown --> Loading: Phục hồi nguồn tin cậy
~~~

`Usable` chỉ nghĩa là entry đủ điều kiện tái sử dụng cho hợp đồng đã chọn. Nó không tự khẳng định mọi action được phép.

`Unknown` khác `DENY`: hệ thống chưa biết quyền hiện tại, chẳng hạn DB không đọc được. Với thao tác cần quyền nghiêm ngặt, trạng thái chưa biết không được trở thành allow. API có thể trả lỗi tạm thời phù hợp thay vì khẳng định người dùng chắc chắn không có quyền.

Trước mỗi lần dùng, kiểm tra lại scope, thời hạn, mốc nghiệp vụ và watermark. Không chỉ gắn cờ `usable=true` lúc nạp rồi tin cờ đó mãi.

## 7. Cập nhật nguồn và phát invalidation

### 7.1. Thay đổi quyền và revision phải nguyên tử

Một command thu hồi quyền có thể đi theo trình tự:

~~~text
BEGIN trên DB chính
  Khóa aggregate entitlement liên quan.
  Kiểm tra tenant, quyền quản trị, trạng thái và phê duyệt nếu cần.
  Kiểm tra command idempotency để không áp dụng lại thao tác.
  Cập nhật grant hoặc trạng thái quyền lợi.
  Tăng entitlement_revision.
  Ghi audit và outbox event mang revision mới.
COMMIT

Worker đọc outbox đã commit và phát invalidation.
~~~

Nếu sửa grant nhưng không tăng revision, entry cũ có thể trông hoàn toàn hợp lệ theo version. Nếu tăng revision nhưng event bị mất vì tiến trình crash sau commit, TTL và đường kiểm tra nguồn vẫn phải bảo vệ theo hợp đồng; outbox giúp sự kiện còn cơ hội được gửi lại.

Không phát invalidation như thể thay đổi đã hoàn tất trước khi transaction commit. Consumer có thể đọc trạng thái cũ hoặc nhận một revision không bao giờ tồn tại nếu transaction rollback.

### 7.2. Event nên mang căn cứ để loại snapshot cũ

Ví dụ payload nội bộ:

~~~json
{
  "eventId": "evt-739",
  "tenantId": "T1",
  "subjectId": "U1",
  "audience": "reporting-api",
  "revision": 43,
  "changeType": "ENTITLEMENT_CHANGED"
}
~~~

Payload là ví dụ, không phải một định dạng nhà cung cấp. Event ID dùng nhận diện bản phát lại; revision dùng kiểm tra tiến triển của aggregate. Hai trường không thay thế nhau.

Với event chỉ báo invalidation, consumer có thể:

~~~text
known_revision_floor = max(known_revision_floor, event.revision)
loại entry có revision < known_revision_floor
~~~

Cập nhật watermark và loại entry phải được phối hợp nguyên tử trong phạm vi cache liên quan. Event 42 đến sau event 43 không được đưa watermark trở về 42.

Nếu event mang delta để dựng lại trạng thái, phép lấy max không đủ. Bỏ qua một delta có thể làm snapshot thiếu dữ liệu; cần kiểm tra sequence liên tục hoặc tải lại snapshot đầy đủ từ nguồn.

### 7.3. Các lớp cache đều cần hợp đồng riêng

Một hệ thống có thể có:

~~~text
DB quyền lợi
  → snapshot trong Redis
  → cache RAM từng node
  → quyết định trong worker/gateway
  → giao diện hoặc token của khách hàng
~~~

Xóa Redis không tự xóa RAM của mọi node. Redis tracking chỉ theo dõi những thay đổi Redis được cấu hình theo dõi; nó không tự biết DB nghiệp vụ vừa sửa grant nếu ứng dụng không cập nhật hoặc invalidation đường Redis.

Tài liệu Redis mô tả cả invalidation cho client-side cache và nguy cơ stale khi mất kết nối nhận thông báo. Không coi một subscription invalidation còn được khai báo là bằng chứng rằng thông báo vẫn đến được. Xem [Redis client-side caching reference](https://redis.io/docs/latest/develop/reference/client-side-caching/).

Mỗi lớp cần giữ nguyên nguồn gốc thời gian/version và phản ứng phù hợp khi không còn nhận invalidation. Một lớp âm thầm gia hạn TTL có thể phá giới hạn của toàn hệ thống.

## 8. Race condition: snapshot cũ quay lại sau khi đã xóa

### 8.1. Chỉ DEL key chưa đủ

Xét hai tiến trình:

| Bước | Reader A | Writer/consumer B |
| --- | --- | --- |
| 1 | Đọc snapshot revision 42 từ nguồn | |
| 2 | Bị chậm trước khi ghi cache | Thu hồi quyền, commit revision 43 |
| 3 | | Nhận event 43 và xóa cache |
| 4 | Ghi snapshot 42 trở lại cache | |
| 5 | Request sau đọc thấy allow cũ | |

Đây là stale fill: bản cũ được công bố sau invalidation. Cache miss sau khi xóa không bảo đảm lần nạp tiếp theo sử dụng dữ liệu mới.

Redis cũng mô tả race giữa response đọc và thông báo invalidation trên các kết nối khác nhau. Điểm cần rút ra cho ứng dụng là phải quản lý cả lần nạp đang chạy, không chỉ entry đã tồn tại. Xem [phần tránh race condition trong tài liệu Redis](https://redis.io/docs/latest/develop/reference/client-side-caching/#avoiding-race-conditions).

### 8.2. Phối hợp generation và revision floor

Một cơ chế trong từng miền cache có thể như sau:

~~~text
Bắt đầu nạp:
  giữ load_generation hiện tại của key

Nhận invalidation revision r:
  tăng generation
  nâng revision_floor lên max(revision_floor, r)
  loại entry cũ

Công bố kết quả nạp:
  trong cùng thao tác nguyên tử:
    generation phải bằng generation lúc bắt đầu nạp
    snapshot.revision phải >= revision_floor
    scope/schema phải khớp
    snapshot chưa qua hạn sử dụng
  nếu không đủ -> bỏ kết quả, xác minh lại theo hợp đồng
~~~

Generation ngăn response của một lần nạp đã bị vô hiệu hóa ghi lại dữ liệu. Revision floor ngăn snapshot thấp hơn revision đã biết được chấp nhận ngay cả khi nó đến từ replica hoặc một tầng cache khác.

Thao tác “đọc floor rồi SET ở lệnh sau” vẫn có race. Cần CAS, mutex thích hợp hoặc thao tác server-side nguyên tử. Nếu dùng nhiều key trong Redis Cluster, còn phải thiết kế vị trí key tương thích với giới hạn nguyên tử của cơ chế được chọn.

Tài liệu Redis về một kỹ thuật placeholder không tự tạo transaction xuyên DB và Redis. Giao thức của ứng dụng vẫn phải bao phủ writer, nguồn đọc và tất cả các lớp cache.

### 8.3. Tombstone không được biến mất quá sớm

Sau khi xóa entry, giữ lại revision floor/generation như một dấu chống phục hồi bản cũ. Nếu xóa cả dấu đó trong khi request nạp cũ còn có thể quay về, snapshot cũ lại có thể được công bố.

Thời gian giữ dấu phải có căn cứ từ giới hạn vòng đời của công việc đang chạy và giao thức khôi phục. Nếu không giới hạn được độ trễ, không dùng một TTL tùy chọn rồi cho rằng đã chứng minh an toàn. Có thể cần lưu floor bền vững hoặc xác minh nguồn trước khi công bố lại.

Khi node/cache khởi động lại mà mất watermark, trạng thái ban đầu là chưa biết. Không đặt floor bằng 0 rồi tiếp nhận bất kỳ snapshot nào từ một replica hoặc backup chưa xác minh.

### 8.4. Điều cơ chế này chưa bảo đảm

Generation/floor chặn dữ liệu thấp hơn điều cache đã biết. Nó không phát hiện revision 43 khi event 43 chưa đến.

Vì vậy:

- Với quyền được phép cũ có giới hạn, deadline tuổi nguồn vẫn cần được kiểm tra.
- Với quyền phải hiện hành, vẫn cần đường kiểm tra nguồn tại điểm phân xử.
- Việc nạp được snapshot mới không tự kiểm tra quyền theo đối tượng hay chống tiêu quota trùng.

## 9. Quyền phải hiện hành tại thời điểm ghi nghiệp vụ

### 9.1. Dùng cache làm dữ liệu ứng viên

Với thao tác quan trọng, có thể dùng snapshot cache để tránh tính lại toàn bộ quyền, nhưng phải đối chiếu căn cứ hiện hành trong transaction.

Ví dụ đơn giản có bảng guard theo aggregate:

~~~sql
SELECT revision, administratively_blocked
FROM entitlement_guard
WHERE tenant_id = :tenant_id
  AND subject_id = :subject_id
  AND audience = :audience
FOR UPDATE;
~~~

Các placeholder cần bind theo driver. Giả định mọi writer thay đổi quyền lợi đều khóa/cập nhật cùng guard, và guard bao phủ đầy đủ đầu vào entitlement của ví dụ.

Trong PostgreSQL, khóa hàng này buộc các writer/locker xung đột chờ tới khi transaction hiện tại kết thúc. Xem [tài liệu khóa hàng PostgreSQL 18](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).

Nếu còn chính sách tenant, membership hoặc quyền đối tượng ở aggregate khác, phải kiểm tra và đồng bộ các phụ thuộc đó bằng giao thức tương ứng. Một guard của entitlement không tự khóa toàn bộ hệ thống phân quyền.

### 9.2. Điểm phân xử phải nằm cùng hiệu ứng nghiệp vụ

Giả mã:

~~~text
BEGIN trên nguồn có thẩm quyền
  Xác thực ngữ cảnh tenant/subject.
  Khóa các guard và đối tượng theo thứ tự thống nhất.
  Lấy decision_at sau khi đã có khóa cần thiết.

  Đọc revision/trạng thái hiện tại.
  Nếu candidate cache đúng scope, đúng revision và còn hợp lệ về thời gian:
      tái sử dụng snapshot
  Ngược lại:
      đọc và tính quyền từ dữ liệu nguồn nhất quán

  Kiểm tra entitlement, membership, quyền đối tượng và trạng thái nghiệp vụ.
  Kiểm tra/tiêu quota nguyên tử nếu thao tác cần.
  Ghi hiệu ứng nghiệp vụ, command idempotency và outbox.
COMMIT
~~~

Không đọc revision hiện tại, đóng transaction, rồi vài giây sau ghi nghiệp vụ mà không kiểm tra lại. Thu hồi có thể xảy ra trong khoảng đó.

PostgreSQL `CURRENT_TIMESTAMP`/`now()` lấy mốc bắt đầu transaction, còn `clock_timestamp()` lấy thời gian lúc gọi. Nếu đã chờ khóa qua hạn grant, cần chính sách lấy thời điểm sau chờ thay vì xét theo mốc cũ. Xem [tài liệu thời gian PostgreSQL 18](https://www.postgresql.org/docs/18/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

Cần chốt thứ tự nghiệp vụ: thao tác đã được chấp nhận dưới khóa trước thu hồi có thể được coi là hợp lệ; thao tác được phân xử sau khi thu hồi commit phải thấy căn cứ mới. “Thu hồi tức thời” không tự có nghĩa là hủy hồi tố mọi công việc đã được chấp nhận trước đó.

Không giữ khóa DB khi chờ HTTP hoặc xử lý một báo cáo dài. Với công việc bất đồng bộ, transaction có thể chỉ chấp nhận một job. Chính sách phải nói job giữ quyền tại thời điểm chấp nhận hay phải xác minh lại khi thực thi/giao dữ liệu. Nếu yêu cầu thu hồi ảnh hưởng cả job đang chạy, cần kiểm tra bổ sung hoặc fencing ở worker.

### 9.3. Idempotency không phải giấy phép dùng quyền cũ

Một command đã hoàn tất có thể được retry sau thu hồi. Sau khi kiểm tra quyền xem kết quả, hệ thống có thể trả lịch sử được phép trả, nhưng không tạo lại hiệu ứng hay cấp quyền mới từ snapshot cũ.

Một command chưa từng được chấp nhận phải được xét theo quyền tại thời điểm hiện hành. Không cho client gửi một “authorization decision ID” cũ rồi biến nó thành quyền thực thi vô hạn.

Đồng thời, cache không giải quyết chi tiêu trùng. Dù entitlement còn hợp lệ, request cùng hoặc khác key vẫn cần ràng buộc nghiệp vụ, idempotency và transaction phù hợp với hiệu ứng đang ghi.

## 10. Sự cố, nhiều vùng và token

### 10.1. Phân biệt mất cache và mất nguồn quyền

| Tình huống | Cách xử lý theo hợp đồng |
| --- | --- |
| Cache không truy cập được, DB quyền còn hoạt động | Đọc nguồn, có kiểm soát tải |
| Entry quá hạn, nguồn không đọc được | Không cấp quyền mới cho thao tác yêu cầu xác minh |
| Mất invalidation nhưng nguồn còn đọc được | Xác minh lại hoặc chuyển đường nghiêm ngặt; không gia hạn tuổi cũ |
| Watermark mất sau restart | Đánh dấu chưa biết, bootstrap từ nguồn tin cậy |
| Consumer lag lớn | Theo dõi và áp dụng ngưỡng chuyển chế độ đã định |
| Chỉ UI cần hiển thị tham khảo | Có thể hiển thị dữ liệu cũ kèm trạng thái phù hợp, API vẫn tự kiểm tra |

Đối với hợp đồng cho phép dữ liệu cũ trong B giây, việc mất event không cho phép dùng quá B. Hệ thống có thể chọn ngừng dùng cache sớm hơn khi mất bằng chứng. Không kéo dài deadline mỗi lần fallback vì “nguồn đang lỗi”.

`stale-while-revalidate` hữu ích cho một số nội dung hiển thị. Nó chỉ dùng được cho cấp quyền khi chính sách thật sự chấp nhận cửa sổ đó và còn kiểm soát deadline; không tự động áp dụng cho xuất dữ liệu hoặc thay đổi quyền.

### 10.2. Refresh và cache stampede

Single-flight, khóa nạp ngắn hoặc giới hạn số refresh giúp giảm tải. Chúng không chứng minh snapshot đủ mới. Response nạp về vẫn phải qua generation, revision và deadline.

Refresh sớm có thể dùng jitter để tránh nhiều key cùng hết hạn. Jitter không được kéo `fresh_until` vượt cam kết; có thể rút ngắn thời điểm refresh hoặc đổi lịch nền bên trong giới hạn.

Khi cache trống hàng loạt, giới hạn tải đọc nguồn và trả lỗi kiểm soát được nếu cần. Không chuyển sang `allow=true` mặc định để giảm tải.

### 10.3. Nhiều vùng và thu hồi khẩn cấp

Một vùng vừa mất kết nối có thể vẫn phục vụ snapshot cũ. Cam kết thu hồi phải bao phủ toàn bộ vùng đang phục vụ, không chỉ vùng ghi DB.

Với thao tác nghiêm ngặt, định tuyến tới nguồn có thẩm quyền hoặc ngừng cấp quyền khi không xác minh được. Một denylist đồng bộ bất đồng bộ ở các vùng cũng có cùng bài toán độ trễ; đặt tên “emergency revoke” không làm nó có tính nguyên tử.

Nếu chấp nhận một cửa sổ sau thu hồi, đo và ghi rõ giới hạn cùng giả định về đồng hồ, nguồn đọc và thời gian xử lý. Không lấy độ trễ trung bình thay cho giới hạn tối đa.

### 10.4. Token có claim entitlement vẫn có thể cũ

Chữ ký token chứng minh payload không bị sửa theo khóa tin cậy; nó không chứng minh entitlement chưa thay đổi từ lúc token được cấp.

Token ngắn hạn có thể giới hạn một phần cửa sổ cũ. Muốn đối chiếu revision/session hiện hành vẫn cần nguồn kiểm tra hoặc giao thức thu hồi tương ứng.

Không phát token mới bằng cách sao chép claim cũ rồi đặt thời điểm cấp mới mà không xác minh. Cách đó có thể giữ quyền đã thu hồi qua nhiều vòng refresh.

## 11. Minh họa Java: kiểm tra điều kiện tái sử dụng snapshot

Hàm dưới đây chỉ phục vụ **đường đọc được phép dùng dữ liệu cũ có giới hạn**. Nó không cấp quyền action, không bảo đảm revision hiện hành ở DB và không thay thế giao thức phối hợp invalidation.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class EntitlementCachePolicy {
    public record Scope(
            String tenantId,
            String subjectId,
            String audience,
            int schemaVersion,
            int policyModelVersion) {
        public Scope {
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(audience);
        }
    }

    public record Entry(
            Scope scope,
            long revision,
            Instant sourceVerifiedAt,
            Instant freshUntil,
            Instant nextTransitionAt) {
        public Entry {
            Objects.requireNonNull(scope);
            Objects.requireNonNull(sourceVerifiedAt);
            Objects.requireNonNull(freshUntil);
            Objects.requireNonNull(nextTransitionAt);
            if (revision < 1) {
                throw new IllegalArgumentException("Invalid revision");
            }
        }
    }

    public static boolean mayReuseForBoundedRead(
            Entry entry,
            Scope expectedScope,
            long knownRevisionFloor,
            boolean cacheGenerationTrusted,
            Instant decisionAt,
            Duration maximumSourceAge) {
        Objects.requireNonNull(expectedScope);
        Objects.requireNonNull(decisionAt);
        Objects.requireNonNull(maximumSourceAge);

        if (maximumSourceAge.isNegative() || maximumSourceAge.isZero()) {
            throw new IllegalArgumentException("Invalid freshness budget");
        }

        if (entry == null || !cacheGenerationTrusted) {
            return false;
        }
        if (!entry.scope().equals(expectedScope)
                || entry.revision() < knownRevisionFloor) {
            return false;
        }
        if (decisionAt.isBefore(entry.sourceVerifiedAt())
                || !decisionAt.isBefore(entry.freshUntil())
                || !decisionAt.isBefore(entry.nextTransitionAt())) {
            return false;
        }

        Duration sourceAge =
                Duration.between(entry.sourceVerifiedAt(), decisionAt);
        return sourceAge.compareTo(maximumSourceAge) < 0;
    }
}
~~~

Các giá trị scope, generation và revision floor lấy từ hệ thống tin cậy, không phải tham số để client tự chứng nhận. `maximumSourceAge` là ngân sách cấu hình theo endpoint sau khi đã tính biên dự phòng cần thiết.

Nếu không có mốc nghiệp vụ tương lai, ví dụ có thể dùng một sentinel như `Instant.MAX` cho `nextTransitionAt`, miễn phần lưu trữ/serialization hỗ trợ biểu diễn đó. Không mặc nhiên ghi giá trị này vào kiểu timestamp DB có miền giá trị khác.

Ví dụ với entry được xác minh lúc `10:00:00Z`:

- `fresh_until = 10:00:05Z`: xét đúng 10:00:05 phải nạp lại.
- Copy entry từ L2 sang L1 lúc 10:00:04 không đổi `source_verified_at`.
- Nếu biết floor đã là 43 và entry là 42, phải bỏ entry dù chưa tới deadline.
- Nếu entry là 43 và floor là 43, hàm vẫn không chứng minh DB chưa có 44.
- Nếu đồng hồ đọc quay lùi về trước thời điểm xác minh, hàm không cho dùng entry.

Kết quả `true` chỉ cho phép dùng snapshot làm đầu vào ở đường bounded read. Sau đó vẫn phải xét quyền lợi cụ thể, quyền theo đối tượng và những điều kiện nghiệp vụ còn lại.

Với code bất đồng bộ, không kiểm tra entry trước khi xếp hàng rồi dùng kết quả boolean đó vô hạn. Cần kiểm tra lại ở ranh giới mà chính sách chọn, hoặc ghi một quyết định đã được chấp nhận có phạm vi và vòng đời rõ ràng.

## 12. Các chuỗi lạm dụng cache entitlement

| Chuỗi thao tác | Mục đích | Bất biến cần bảo vệ |
| --- | --- | --- |
| Làm nóng cache rồi bị thu hồi, tiếp tục gọi qua nhiều node | Tận dụng node còn allow cũ | Độ mới và đường nguồn theo endpoint |
| Đổi tenant nhưng giữ user/token cũ | Dùng snapshot của tenant khác | Scope cache và membership hiện tại |
| Gọi action khác với cùng cache decision | Mở rộng phạm vi quyết định | Key/đầu vào đầy đủ hoặc snapshot có kiểm tra action riêng |
| Tạo tải để refresh chậm qua invalidation | Ghi bản cũ trở lại | Generation, revision floor và công bố nguyên tử |
| Chờ event đảo thứ tự | Khôi phục quyền bằng event cũ | Revision không lùi |
| Lặp refresh token trước khi hết hạn | Kéo dài claim đã bị thu hồi | Không làm mới tuổi quyền từ payload cũ |
| Dùng tính năng sát hạn grant | Vượt thời gian đã mua | Deadline không vượt mốc nghiệp vụ |
| Tạo nhiều request tiêu quota đồng thời | Vượt hạn mức dù quyền đúng | Cập nhật lượng nguyên tử |
| Cố ý kích hoạt nhánh timeout/fallback | Biến lỗi nguồn thành allow | Unknown không cấp quyền ngoài hợp đồng |
| Gọi lại command cũ sau thu hồi | Tạo hiệu ứng mới bằng căn cứ lịch sử | Idempotency và kiểm tra cho command mới |
| Dùng negative cache cũ sau khi nâng cấp | Khiến quyền mới chưa dùng được | Cam kết độ trễ cấp quyền, invalidation và TTL deny |
| Tận dụng cache key khác schema hoặc model | Đọc kết quả tính bằng quy tắc cũ | Version mô hình và kiểm tra tương thích |

HMAC hoặc chữ ký cho envelope cache có thể phát hiện sửa payload trong một số mô hình đe dọa. Chúng không làm revision cũ trở thành hiện hành. Quyền ghi cache cũng phải giới hạn cho các thành phần được phép; API tự phục vụ không được nhận một snapshot allow do client gửi để đưa vào cache chung.

Chỉ làm bài thử trên tài khoản, dữ liệu và môi trường do nhóm kiểm soát. Mục tiêu là chứng minh invariant trước các cách phối hợp request, không chỉ kiểm tra cơ chế cache có hoạt động.

## 13. Kiểm thử độ mới và race condition

### 13.1. Ma trận kiểm thử

| Nhóm | Tình huống | Kết quả cần chứng minh |
| --- | --- | --- |
| Scope | Cùng user, khác tenant/audience | Không dùng chung snapshot sai phạm vi |
| Thời hạn | Trước, đúng, sau `fresh_until` | Chỉ trước hạn mới có thể tái sử dụng |
| Mốc nghiệp vụ | Grant hết hạn trước TTL | Không cấp quyền sau hạn grant |
| Bắt đầu grant | Negative cache đi qua `valid_from` | Xác minh lại đúng mốc |
| Nhiều lớp | L2 đã cũ 25 giây, L1 cấp TTL mới | Tuổi nguồn không được đặt lại |
| Revision | Entry 42, floor 43 | Không tái sử dụng |
| Event chưa đến | DB 43, node chỉ biết 42 | Đường nghiêm ngặt vẫn chặn quyền đã thu hồi |
| Event đảo thứ tự | Nhận 43 rồi 42 | Không hạ watermark |
| Event delta thiếu | Mất một phần chuỗi cập nhật | Phát hiện thiếu hoặc nạp snapshot đầy đủ |
| Stale fill | Invalidation đến trước response load cũ | Kết quả nạp cũ không được công bố |
| Restart | Mất watermark, còn snapshot từ backup | Bootstrap/xác minh, không mặc định tin snapshot |
| Replica lag | Trả revision thấp nhưng đọc vừa xong | Không gắn nhãn mới nếu chưa đủ bằng chứng |
| Mất invalidation | Kết nối ngắt, local còn allow | Không dùng quá hợp đồng; chuyển chế độ phù hợp |
| Nguồn lỗi | Entry quá hạn và DB không đọc được | Không fallback allow cho thao tác nghiêm ngặt |
| Negative cache | Vừa mua thêm tính năng | Không từ chối quá cam kết cấp quyền |
| Token | Refresh claim cũ sau thu hồi | Không gia hạn quyền chỉ từ token cũ |
| Quota | Hai request cùng thấy còn một lượt | Không ghi được hai lần tiêu |
| Command | Retry sau commit và sau thu hồi | Không tạo hiệu ứng mới từ quyết định cũ |
| Đồng hồ | Lệch giờ hoặc lùi trước mốc xác minh | Không kéo dài quyền ngoài cam kết |
| Triển khai | Schema/model hoặc epoch đã đổi | Không phục vụ snapshot không tương thích |

Không chỉ assert cache hit/miss hoặc HTTP status. Kiểm tra revision được dùng, nguồn quyết định, scope, deadline, số hiệu ứng nghiệp vụ và audit sau commit/rollback.

### 13.2. Kiểm thử stale fill bằng điểm đồng bộ

Dùng cơ chế điều phối trong test thay vì chờ race ngẫu nhiên:

1. Reader đọc snapshot 42 và dừng ngay trước bước công bố cache.
2. Writer thu hồi quyền, commit 43 và phát event.
3. Consumer nâng floor/generation, loại snapshot cũ.
4. Cho reader tiếp tục.
5. Xác nhận thao tác công bố 42 bị từ chối.
6. Request tiếp theo phải đi theo đường nạp lại hoặc kiểm tra nguồn, không nhận allow từ 42.

Lặp lại với L1/L2, response đọc chậm, consumer retry và dấu floor bị eviction. Nếu xóa floor làm test thất bại, hệ thống cần quy tắc giữ/khôi phục dấu đúng với vòng đời công việc.

### 13.3. Kiểm thử điểm phân xử với thu hồi

Dùng hai kết nối DB trên cùng guard:

- Một trường hợp request nghiệp vụ giữ khóa trước: ghi nhận kết quả theo quyền tại điểm chấp nhận trước thu hồi.
- Một trường hợp thu hồi commit trước: request nghiệp vụ phải thấy revision mới và không thực hiện action đã bị cấm.
- Một trường hợp request chờ qua hạn grant: lấy thời điểm sau chờ và không dùng thời điểm transaction bắt đầu để vượt hạn.

Không chỉ test hàm boolean Java; test này cần đường ghi thật và giao thức khóa thật của ứng dụng. Nếu hiệu ứng là job, kiểm tra thêm quyền ở thời điểm thực thi theo chính sách đã chọn.

### 13.4. Kiểm thử chuỗi thao tác và sự cố

Một chuỗi mẫu:

~~~text
cấp quyền
→ nạp cache trên hai node
→ thu hồi
→ làm mất event ở một node
→ copy L2 sang L1
→ retry command
→ refresh token
→ khởi động lại một node
→ request quyền nhạy cảm
~~~

Sau mỗi bước, xác nhận:

- Không dùng entry ngoài scope hoặc quá deadline.
- Tuổi nguồn không giảm chỉ vì copy/refresh.
- Revision đã biết không lùi.
- Snapshot bị invalidation không tự sống lại do load cũ.
- Thao tác nghiêm ngặt không dựa hoàn toàn vào bản cache có thể cũ.
- Sự cố không làm phát sinh hiệu ứng trùng hoặc vượt quota.

Các giả mã và code trong bài là minh họa thiết kế; chưa cấu thành một bộ tích hợp hoàn chỉnh cho một framework hay hệ thống production cụ thể.

## 14. Quan sát, audit và triển khai

### 14.1. Ghi căn cứ của quyết định

Log/audit nên lưu được:

- Tenant, subject, audience, action và định danh đối tượng phù hợp.
- Request/command ID và nguồn quyết định: cache L1, L2 hay DB.
- Revision entry, revision floor và revision nguồn nếu đã kiểm tra.
- `source_verified_at`, `decision_at`, `fresh_until` và mốc nghiệp vụ liên quan.
- Chế độ endpoint: bounded read hay kiểm tra nguồn nghiêm ngặt.
- Lý do như `CACHE_EXPIRED`, `REVISION_TOO_OLD`, `SCOPE_MISMATCH` hoặc `AUTHORITY_UNAVAILABLE`.
- Căn cứ chấp nhận công việc và version chuyển cho worker nếu có.

Không ghi access token hoặc toàn bộ danh sách dữ liệu nhạy cảm vào log. Client cũng không được tự chọn mức freshness thấp hơn để bỏ qua kiểm tra của endpoint.

### 14.2. Đo hiệu quả cùng với độ an toàn

Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Cache hit rate và thời gian đọc nguồn | Hiệu quả tối ưu |
| Tuổi nguồn tại lúc ra quyết định | Dữ liệu thực sự cũ bao nhiêu |
| Độ trễ từ commit đến invalidation trên từng vùng | Chất lượng truyền thay đổi |
| Số load bị chặn vì generation/revision | Race được phát hiện |
| Số lần source fallback và từ chối do không xác minh được | Hành vi khi sự cố |
| Chênh lệch khi đối chiếu cache với nguồn | Phát hiện bản sai hoặc thiếu dependency |
| Số quyết định vượt freshness budget | Vi phạm hợp đồng cần xử lý |

Đối chiếu lấy mẫu hữu ích để phát hiện lỗi nhưng không thay thế kiểm tra bắt buộc cho từng request quan trọng. Một tỷ lệ sai thấp vẫn có thể tập trung ở những quyền nhạy cảm.

### 14.3. Thay đổi chính sách và xử lý khẩn cấp

Khi giảm freshness budget, các entry cũ phải chịu giới hạn mới tại lúc dùng; không chờ chúng hết TTL cũ. Đổi schema/model cần phiên bản key hoặc kiểm tra envelope tương thích.

Quy trình thu hồi khẩn cấp cần chỉ rõ đường nào vẫn xác minh được khi event bus/cache lỗi, vùng nào đang phục vụ và khi nào phải ngừng chấp nhận thao tác. Người vận hành phải có cách nhận biết trạng thái chưa xác minh, thay vì coi cache hit là hệ thống khỏe.

Sửa dữ liệu bằng command có audit và cập nhật revision/outbox đúng giao thức. Sửa trực tiếp grant hoặc xóa key thủ công có thể bỏ sót cache khác, mất dấu chống stale fill hoặc để snapshot cũ quay lại.

Freshness trở thành một phần của quy tắc nghiệp vụ khi mỗi đường thực thi biết rõ mình được chấp nhận dữ liệu cũ đến đâu, kiểm tra bằng căn cứ nào và phản ứng thế nào khi căn cứ đó không còn đủ.
