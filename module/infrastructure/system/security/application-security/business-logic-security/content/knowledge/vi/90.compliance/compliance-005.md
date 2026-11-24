# Nghĩa vụ lưu giữ dữ liệu nghiệp vụ (Retention obligation)

Một người dùng đóng tài khoản không có nghĩa mọi bằng chứng phê duyệt, khoản thu và hoàn tiền được phép biến mất ngay. Ngược lại, giữ toàn bộ request, thông tin cá nhân và bản sao vô thời hạn cũng không phải cách mặc định để đáp ứng tuân thủ. Hệ thống phải xác định dữ liệu nào cần giữ, giữ vì lý do gì, từ mốc nào, trong phạm vi nào và khi nào được xử lý kết thúc vòng đời.

Trong chương **Compliance** của module Business Logic Security, retention obligation là nghĩa vụ lưu giữ một loại hồ sơ trong điều kiện đã xác định, bao gồm khả năng bảo vệ, truy xuất và giải thích hồ sơ trong suốt thời gian cần thiết. Với ứng dụng nghiệp vụ, đây là quy tắc có thể bị lạm dụng: xóa chứng cứ sau khi sửa giá, rút ngắn hạn lưu để che thao tác vượt quyền hoặc giữ dữ liệu quá mức bằng cách tạo hold không hợp lệ.

## 1. Hiểu đúng nghĩa vụ lưu giữ

### 1.1. Lưu giữ là một phần của vòng đời nghiệp vụ

Một hồ sơ có thể cần tồn tại để chứng minh:

- Nội dung nào được người có thẩm quyền phê duyệt và thuộc phiên bản nào.
- Quyền trên đối tượng được đánh giá thế nào tại thời điểm hành động.
- Giá, currency và điều kiện server đã chấp nhận khi tạo nghĩa vụ.
- Request nào là retry, request nào bị từ chối vì xung đột và operation nào đã có hiệu lực.
- Một khoản thu hoặc refund có liên kết với nghĩa vụ nào.
- Ai đã thay đổi retention policy, đặt hold, gỡ hold hoặc yêu cầu xóa hồ sơ.

Không nhất thiết phải giữ toàn bộ payload để trả lời các câu hỏi này. Cần thiết kế hồ sơ tối thiểu nhưng đủ ngữ cảnh, đồng thời bảo vệ phần thông tin nhạy cảm thực sự phải lưu.

### 1.2. Các nguồn yêu cầu không tự đồng nhất

| Nguồn yêu cầu | Ví dụ ý nghĩa | Việc hệ thống cần biểu diễn |
|---|---|---|
| Quy định áp dụng | Loại hồ sơ phải lưu trong phạm vi tổ chức, ngành hoặc khu vực cụ thể | Tham chiếu căn cứ, phạm vi áp dụng, thời hạn và phiên bản đã được xác nhận |
| Hợp đồng | Nghĩa vụ giữ hồ sơ, cung cấp chứng từ hoặc xử lý dữ liệu khi chấm dứt dịch vụ | Bên chịu trách nhiệm, loại dữ liệu, trigger và cách bàn giao/xóa |
| Chính sách tổ chức | Lịch lưu audit, hồ sơ xử lý sự cố, dữ liệu vận hành | Chủ sở hữu, phê duyệt, lịch rà soát, quy tắc thay đổi |
| Hold theo quyết định có thẩm quyền | Tạm ngăn xử lý hủy hồ sơ liên quan một vụ việc | Hold ID, căn cứ, scope, thời điểm hiệu lực, người đặt/gỡ và lịch rà soát |
| Yêu cầu an toàn nghiệp vụ | Cần dữ liệu để chống thu trùng hoặc đối soát operation unknown | Thời gian an toàn của giao thức, trạng thái nghĩa vụ và dữ liệu tối thiểu cần thiết |

Một yêu cầu nội bộ hoặc tham số kỹ thuật không tự trở thành nghĩa vụ pháp lý. Nhóm phụ trách xác định căn cứ và phạm vi; phần mềm thực thi chính sách đã được xác nhận, ghi phiên bản và phát hiện trường hợp chưa thể quyết định.

Ví dụ, AU-11 trong [NIST SP 800-53, bản Revision 5.1](https://csrc.nist.gov/CSRC/media/Projects/risk-management/800-53%20Downloads/800-53r5/SP_800-53_v5_1-derived-OSCAL.pdf) dùng thời gian lưu audit do tổ chức xác định phù hợp chính sách, nhằm hỗ trợ điều tra và đáp ứng yêu cầu liên quan. Không thể đọc control này rồi tự suy ra một con số chung cho mọi hệ thống.

### 1.3. Có cả giới hạn giữ và điều kiện xóa

Retention không chỉ là “không xóa trước ngày X”. Cần xét mục đích, mức dữ liệu cần thiết, quyền sử dụng và các nghĩa vụ kết thúc lưu giữ.

Khi GDPR thuộc phạm vi áp dụng, Điều 5(1)(e) nêu nguyên tắc giới hạn lưu dữ liệu nhận diện cá nhân theo nhu cầu mục đích; Điều 17(3)(b), (e) quy định ngoại lệ liên quan nghĩa vụ pháp lý và yêu cầu pháp lý trong phạm vi điều kiện của điều luật. Đây là ví dụ cho việc không áp dụng máy móc “xóa ngay” hay “giữ mãi”. Xem [văn bản GDPR trên EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/).

Bài học không ấn định số năm theo luật cho một tổ chức cụ thể. Các khoảng thời gian trong ví dụ dưới đây là **fixture giả định để kiểm thử**, không phải thời hạn tuân thủ được đề xuất.

## 2. Phân biệt những khái niệm dễ bị trộn

| Khái niệm | Nó bảo đảm hoặc thực hiện điều gì? | Không được suy ra |
|---|---|---|
| Retention period | Khoảng thời gian hồ sơ phải được giữ theo rule | Mọi bản sao tự có cùng cấu hình hoặc tự xóa khi hết hạn |
| Immutability/WORM | Hạn chế sửa/xóa byte hoặc phiên bản được bảo vệ | Dữ liệu đầy đủ, đúng nghiệp vụ hoặc được phân loại đúng |
| Archive | Chuyển sang cách lưu/truy xuất khác | Đã xóa dữ liệu hoặc hết nghĩa vụ giữ |
| Backup | Hỗ trợ phục hồi từ một mốc | Tự là kho chứng cứ có thể truy xuất theo hồ sơ |
| Legal/preservation hold | Ngăn disposition trong phạm vi và thời gian hiệu lực đã xác định | Cho phép dùng dữ liệu cho mọi mục đích hoặc áp dụng vô hạn cho mọi tenant |
| Soft delete | Ẩn hoặc đánh dấu xóa trong luồng ứng dụng | Đã purge bản gốc, version cũ, index, export và backup |
| Anonymization | Làm dữ liệu không còn có thể nhận diện theo tiêu chí phù hợp | Xóa field tên hoặc hash email đã đủ để đạt điều đó |
| Disposition | Quyết định xử lý kết thúc vòng đời: xóa, chuyển giao hoặc lưu trữ theo chính sách | Một batch `DELETE` là toàn bộ quy trình |

Giữ được file nhưng làm mất schema, khóa giải mã hoặc liên kết tới approval có thể khiến hồ sơ không còn sử dụng được. Nghĩa vụ lưu giữ cần đi cùng khả năng đọc và diễn giải đúng trong phạm vi yêu cầu.

## 3. Mô hình xuyên suốt: hồ sơ xác nhận đơn

Giả sử đơn ORD-742 thuộc tenant T1, được duyệt ở version 7 với tổng tiền 195.000 VND. Một confirmation tạo operation OP-63, reservation, outbox PaymentRequested và ánh xạ idempotency. Provider có thể đã thu tiền trong khi kết quả cục bộ còn unknown.

Trong fixture, tổ chức đã phê duyệt các rule giả định:

| Nhóm dữ liệu | Rule giả định | Mục đích trong fixture |
|---|---|---|
| Hồ sơ quyết định và hiệu lực nghiệp vụ | Giữ tối thiểu 90 ngày từ event BUSINESS_CASE_FINALIZED hợp lệ | Giải thích approval, quyền, số tiền và hiệu lực đã đối soát |
| Log chẩn đoán chi tiết | Đánh giá xóa sau 30 ngày từ lúc phát sinh nếu không có lý do giữ riêng | Hạn chế dữ liệu vận hành dư thừa |
| Cache response idempotency | TTL 24 giờ theo hợp đồng API giả định | Tăng tốc replay; dữ liệu chống trùng durable nằm ở lớp khác |
| Artifact thuộc case đang hold | Ngăn disposition tới khi hold được gỡ hợp lệ | Giữ chứng cứ đúng scope của case |

“Đánh giá xóa” nghĩa là kiểm tra tất cả điều kiện, không phải cứ tới ngày là xóa. Một bản ghi log đã được chọn làm artifact thuộc case có thể chịu rule khác với log chẩn đoán thông thường; việc chuyển loại phải có căn cứ và dấu vết.

### 3.1. Các invariant cần bảo vệ

```text
R1: Không hủy hồ sơ khi còn một nghĩa vụ giữ hợp lệ hoặc hold có hiệu lực.
R2: Không dùng retention/hold ngoài thẩm quyền để kéo dài lưu dữ liệu.
R3: Hồ sơ được giữ phải truy xuất và giải thích được trong phạm vi yêu cầu.
R4: Xóa cache hoặc hết TTL không cho phép thực hiện lại nghĩa vụ đã có hiệu lực.
R5: Quyết định disposition phải gắn đúng tenant, record class, version và policy.
R6: Không báo hoàn tất xóa khi target còn pending, unknown hoặc chưa xác minh.
R7: Bản phục hồi không được tự tái đưa dữ liệu đã xử lý xóa vào luồng sử dụng.
```

Các invariant này là mô hình kỹ thuật của bài. Chính sách thực tế cần định nghĩa record class, căn cứ, phạm vi và các điều kiện tương ứng trước khi triển khai.

### 3.2. Không chốt trigger chỉ vì HTTP thành công

Trong fixture, BUSINESS_CASE_FINALIZED chỉ được phát khi operation đã được đối soát và các nghĩa vụ thuộc case đã đạt điều kiện kết thúc đã công bố. HTTP 202, payment timeout hoặc thời điểm tài khoản bị đóng không tự làm case kết thúc.

Nếu khoản thu còn unknown hoặc refund còn pending, hệ thống phải biết đó là nghĩa vụ chưa được giải quyết. Không để một job “đóng đơn cũ” tự khởi động đồng hồ lưu giữ từ ngày tạo đơn rồi xóa bằng chứng cần cho phục hồi.

## 4. Xây dựng retention schedule có thể thực thi

### 4.1. Một rule cần nhiều hơn một số ngày

Retention schedule nên mô tả ít nhất:

- **Record class và trường dữ liệu:** hồ sơ nào là bản cần giữ, dữ liệu nào chỉ là bản sao/working copy.
- **Phạm vi áp dụng:** tenant, tổ chức, khu vực, loại nghiệp vụ, contract hoặc case tương ứng.
- **Căn cứ và chủ sở hữu:** reference đã được xác nhận, người chịu trách nhiệm, người phê duyệt.
- **Trigger:** sự kiện nào bắt đầu tính hạn, nguồn nào được tin cậy và cách xử lý thiếu/cải chính sự kiện.
- **Cách tính thời gian:** ngày lịch hay khoảng thời gian, timezone, ngày cuối kỳ, quy tắc biên.
- **Điều kiện giữ/xóa:** hạn tối thiểu, hạn/mốc rà soát kết thúc, hold, workflow chưa giải quyết và disposition action.
- **Nơi có bản sao:** database, object version, index, warehouse, backup, export và processor/provider liên quan.
- **Khả năng truy xuất:** schema, khóa giải mã, tài liệu diễn giải và thời gian cung cấp hồ sơ theo hợp đồng.
- **Phiên bản và hiệu lực:** thời điểm áp dụng, quy tắc cho dữ liệu cũ, kế hoạch migration và kiểm thử.

Nếu chưa xác định được rule, cần một trạng thái ngoại lệ có owner và deadline rà soát. Không tự điền TTL mặc định ngắn nhất hoặc giữ vô hạn không ai chịu trách nhiệm.

### 4.2. Nhiều nghĩa vụ trên một hồ sơ

Với một tập yêu cầu giữ tối thiểu đã xác nhận **cùng áp dụng** cho hồ sơ, thời điểm sớm nhất có thể xét hủy không thể sớm hơn mốc muộn nhất của các yêu cầu đó:

```text
earliest_disposition_at = max(retain_until của các nghĩa vụ giữ tối thiểu hợp lệ)
```

Công thức không tự giải quyết giới hạn xử lý dữ liệu, quyền xóa, phạm vi field khác nhau hoặc xung đột căn cứ. Không được lấy `max` của mọi policy trong toàn công ty rồi áp cho toàn bộ dữ liệu cá nhân.

Nếu hai yêu cầu không thể đồng thời đáp ứng, ghi conflict, scope và quyết định cần thiết để người có thẩm quyền xử lý. Có thể cần tách hồ sơ tối thiểu được giữ với dữ liệu phục vụ mục đích đã hết, thay vì giữ nguyên mọi cột chỉ vì cùng một hàng database.

### 4.3. Không lấy dữ liệu do client kiểm soát làm căn cứ tuổi hồ sơ

Các trường như `clientTimestamp`, `requestedFinalizedAt`, tên folder hoặc `lastModified` của bản export không tự chứng minh trigger nghiệp vụ. Timestamp từ client có thể bị sửa để làm hồ sơ trông quá hạn hoặc liên tục “mới”.

Server phải xác định event hợp lệ, version, actor và mốc thời gian theo hợp đồng. Giữ event gốc cùng lịch sử cải chính, không sửa âm thầm trigger để đạt kết quả xóa mong muốn.

## 5. Tính thời gian đúng và không để retry làm đổi tuổi hồ sơ

### 5.1. Trigger thuộc nghiệp vụ, không thuộc mọi lần ghi

Nếu rule là 90 ngày từ BUSINESS_CASE_FINALIZED, một lần đọc, retry request, di chuyển storage hoặc backfill index không được tự đặt lại đồng hồ. Ngược lại, nếu chính sách quy định một sự kiện mở lại nghĩa vụ làm thay đổi lịch, cần biểu diễn sự kiện đó rõ ràng.

Lưu ít nhất trigger event ID, event time, ngày được hệ thống tiếp nhận và rule version đã dùng. Với event đến muộn hoặc bị sửa, việc tính lại cần có decision record và lý do; không thay bằng `updatedAt + duration`.

### 5.2. Ngày lịch khác thời lượng cố định

“Một năm”, “365 ngày”, “cuối năm tài chính cộng N năm” và “N ngày kể từ hoàn tất” có thể cho kết quả khác nhau. Cần định nghĩa timezone của mốc nghiệp vụ, năm nhuận, giờ chuyển mùa nếu có và tính bao hàm của ngày kết thúc.

Ở tầng thực thi, có thể chuẩn hóa thành một instant UTC đã tính theo quy tắc lịch tương ứng. Không dùng timezone của máy chạy batch để ngầm quyết định hạn của mọi tenant.

### 5.3. Thiếu trigger và đồng hồ không đáng tin

Thiếu event hoặc metadata không có nghĩa là đã hết hạn. Đưa hồ sơ vào hàng đợi exception, giới hạn thao tác hủy và xử lý trong thời hạn vận hành đã xác định. Cơ chế này cần cảnh báo để tránh biến mọi lỗi metadata thành lưu vô hạn.

Job dùng thời gian do hệ thống kiểm soát, với clock có thể tiêm trong test. Sai lệch đồng hồ lớn, snapshot policy cũ hoặc control service không truy cập được là lý do ngừng quyết định hủy trong phạm vi không xác minh được, đồng thời ghi backlog và owner xử lý.

## 6. Hold có phạm vi, thẩm quyền và vòng đời riêng

### 6.1. Một cờ boolean không đủ cho mọi trường hợp

Một record có thể thuộc nhiều hold. Gỡ HOLD-A không gỡ HOLD-B, và gỡ hold không xóa yêu cầu giữ tối thiểu còn hiệu lực.

Mỗi hold nên có ID, case/reference, căn cứ đã xác nhận, người đặt, scope selector/version, thời điểm yêu cầu, trạng thái áp dụng, owner rà soát và lịch sử gỡ. Scope phải gắn đúng tenant/đối tượng; có thể cần bao gồm cả record phát sinh sau thời điểm đặt hold nếu chúng thuộc vụ việc.

```text
Hold lifecycle minh họa:
    REQUESTED -> APPLYING -> EFFECTIVE -> RELEASE_REQUESTED -> RELEASED

Ngoại lệ:
    APPLYING có thể phát hiện target thiếu hoặc không bảo vệ được;
    phải ghi lỗi/coverage, không tự báo EFFECTIVE đầy đủ.
```

Thời điểm gỡ và lý do cần được ghi, nhưng `review_due_at` không phải thời điểm tự gỡ hold. Quá hạn rà soát phải tạo escalations theo chính sách, không tự làm mất bảo vệ.

### 6.2. Kiểm soát cuộc đua giữa hold và purge

Nếu purge đọc “không có hold” rồi vài giây sau xóa, trong khi hold đã được chấp nhận có hiệu lực ở giữa, hệ thống vi phạm R1. Chỉ kiểm tra hold ở lúc lập danh sách candidate không đủ.

Thiết kế cần một ranh giới điều phối được chứng minh cho hold và disposition theo record/scope. Ví dụ, coordinator và cơ chế storage protection cùng kiểm soát quyền thực hiện irreversible delete; worker không được dùng plan/token cũ sau khi hold hoặc policy generation đã đổi.

Với nhiều storage không hỗ trợ transaction chung, phải mô tả rõ thời điểm hold được coi là hiệu lực, cách chặn purge trong giai đoạn áp dụng, cách xử lý attempt đang chạy và cách xác minh coverage. Một lần đọc DB ngay trước cuộc gọi xóa mạng vẫn có cửa sổ race nếu không có cơ chế phối hợp tiếp theo.

Nếu xóa đã trở thành không thể đảo ngược trước ranh giới tiếp nhận hold, phải ghi target đã mất và báo ngoại lệ. Không thể cam kết khôi phục chứng cứ chỉ bằng cách đặt lại trạng thái database.

### 6.3. Hold không phải quyền đọc mọi dữ liệu

Người có quyền đề nghị giữ chứng cứ chưa chắc được xem payload nhạy cảm, sửa policy hay gỡ hold. Tách quyền theo chức năng và đối tượng; kiểm tra scope cả ở API, job quản trị và công cụ bulk.

Với thao tác rủi ro cao, áp dụng quy trình phê duyệt theo chính sách, kiểm tra version và audit người đề nghị/người duyệt. Đường break-glass nếu có cũng cần scope, lý do và record riêng; không mặc định quản trị viên tenant có quyền rút ngắn nghĩa vụ của mọi hồ sơ.

### 6.4. Ví dụ giới hạn của khóa ở tầng storage

Theo [tài liệu Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html), retention và legal hold áp dụng cho object version; hold độc lập với retention period. Gỡ hold không làm mất period còn hiệu lực, và hết period không gỡ hold. Đây là ví dụ semantics của một sản phẩm, không phải định nghĩa chung cho mọi cơ chế hold của ứng dụng.

Vì vậy cần ánh xạ hold nghiệp vụ tới đúng object version và kiểm tra kết quả áp dụng. Tên object, trạng thái mới nhất hoặc một cờ trong bảng order không đủ chứng minh mọi bản sao liên quan đã được bảo vệ.

## 7. Mô hình hóa quyết định retention trong ứng dụng

### 7.1. Dữ liệu điều khiển tách khỏi payload được giữ

Payload chứa chứng từ nghiệp vụ; dữ liệu điều khiển mô tả rule, trigger, hold và trạng thái disposition. Dữ liệu điều khiển cũng cần được bảo vệ khỏi sửa trái quyền, và có vòng đời lưu giữ riêng thay vì mặc định tồn tại mãi.

Ví dụ JSON là **record giả của fixture**, không phải cấu hình pháp lý hoặc schema bắt buộc:

```json
{
  "fixture_only": true,
  "tenant_id": "T1",
  "record_id": "REC-742",
  "record_class": "order_decision_and_effect_proof",
  "business_reference": {
    "order_id": "ORD-742",
    "operation_id": "OP-63"
  },
  "policy_refs": ["PROOF-90D@3"],
  "trigger": {
    "event_id": "FINAL-31",
    "type": "BUSINESS_CASE_FINALIZED",
    "event_time": "2026-11-23T00:00:00Z",
    "verified": true
  },
  "time_rule": {
    "kind": "ELAPSED_DAYS",
    "days": 90,
    "boundary": "eligible_at_or_after"
  },
  "minimum_retain_until": "2027-02-21T00:00:00Z",
  "active_hold_ids": ["HOLD-A"],
  "retention_revision": 12,
  "business_resolution": "FINALIZED",
  "disposition_state": "BLOCKED_BY_HOLD",
  "copy_inventory_ref": "INVENTORY-742@5",
  "last_decision_ref": "RETDEC-83"
}
```

`minimum_retain_until` là mốc tối thiểu đã tính cho rule của fixture, không phải giấy phép xóa tự động. Nếu có obligation khác, hold, yêu cầu xử lý dữ liệu hoặc conflict, quyết định phải xét thêm những điều đó.

### 7.2. Hàm đánh giá chỉ tạo quyết định, chưa được xóa

Mã dưới là **mã giả Java**, không phải chương trình chạy độc lập. Nó minh họa các guard của một planner sau khi policy đã được phân giải; giao thức thực hiện disposition ở mục 8 là phần riêng.

```java
Decision evaluate(Record r, Context ctx, Instant now) {
    if (!ctx.canEvaluate(r.tenantId(), r.recordClass())) {
        return Decision.deny("OUT_OF_SCOPE");
    }
    if (!ctx.controlStateIsCurrentAndReliable()) {
        return Decision.review("CONTROL_STATE_UNVERIFIED");
    }
    if (r.hasUnresolvedPolicyConflict()) {
        return Decision.review("POLICY_CONFLICT");
    }
    if (r.hasActiveOrApplyingHold()) {
        return Decision.keep("HOLD_BLOCKS_DISPOSITION");
    }
    if (!r.hasVerifiedTrigger()) {
        return Decision.review("MISSING_OR_UNVERIFIED_TRIGGER");
    }
    if (!r.businessObligationsAreResolved()) {
        return Decision.keep("BUSINESS_OBLIGATION_UNRESOLVED");
    }
    if (now.isBefore(r.minimumRetainUntil())) {
        return Decision.keep("MINIMUM_RETENTION_NOT_REACHED");
    }
    if (!ctx.hasApprovedDispositionFor(r)) {
        return Decision.review("DISPOSITION_NOT_RESOLVED");
    }
    return Decision.eligibleForCoordinatedDisposition(
        r.recordId(), r.retentionRevision(), ctx.policyGeneration()
    );
}
```

Một kết quả eligible chỉ là candidate có điều kiện. Không dùng nó như quyền hủy vô thời hạn hoặc bỏ qua kiểm tra quyền thực thi, generation và hold tại ranh giới phối hợp.

Các nhánh review phải có owner, lý do và hạn xử lý. Nếu dữ liệu đã quá hạn xử lý theo chính sách, cảnh báo và đưa ra quyết định có thẩm quyền; không giữ backlog im lặng chỉ vì hàm chưa trả eligible.

## 8. Disposition là workflow có trạng thái và bằng chứng

### 8.1. Từ candidate tới kế hoạch đúng scope

Một workflow minh họa:

```text
RETAINED / HELD / NEEDS_REVIEW
    -> ELIGIBLE_CANDIDATE
    -> PLAN_VALIDATED
    -> DISPOSITION_IN_PROGRESS
    -> VERIFIED_COMPLETE

Các nhánh khác:
    BLOCKED, PARTIAL, EFFECT_UNKNOWN, FAILED_REVIEW_REQUIRED
```

Plan cần gắn tenant, record/version, policy generation, retention revision, inventory version, action và target cụ thể. Các target có thể cần hành động khác nhau: xóa một bản export, giữ hồ sơ tối thiểu trong kho archive hoặc xóa field không còn mục đích lưu.

Không lấy một filter rộng như “tenant đã đóng hơn 90 ngày” để thay mọi kiểm tra theo record class. Các record chưa final, đang hold hoặc thuộc nghĩa vụ khác phải được xử lý đúng điều kiện riêng.

### 8.2. Ranh giới phối hợp phải bao cả quyền thay đổi quyết định

Trước khi thực hiện, hệ thống cần chứng minh plan còn hợp lệ và chưa bị hold/policy mới vô hiệu hóa. Cơ chế claim/lease giúp phân công worker, nhưng lease đơn lẻ không giải quyết cuộc đua với hold hoặc xóa ở storage ngoài.

Các khả năng thiết kế tùy hệ thống gồm coordinator có fencing/generation, hàng đợi điều phối theo record, storage retention/hold và ranh giới cho phép hành động không đảo ngược. Phải kiểm thử việc một hold được tiếp nhận trong khi attempt đang chạy; không tuyên bố atomicity xuyên DB và object storage nếu chúng không cùng giao thức đó.

Nếu hold chỉ có thể trở thành EFFECTIVE sau khi attempt đang chạy được giải quyết, hợp đồng trạng thái phải nói rõ; trong lúc APPLYING phải chặn những attempt mới trong scope. Nếu cần bảo đảm từ thời điểm nhận yêu cầu hold, thiết kế intake và delete gate phải thực thi được ranh giới sớm hơn ấy.

### 8.3. Mỗi target có outcome riêng

Lưu job/attempt ID, target identity/version, action, thời điểm, response và kết quả xác minh. Dùng định danh ổn định để retry đúng target; tránh xóa theo object key tái sử dụng rồi tác động nhầm phiên bản mới.

| Outcome của target | Ý nghĩa | Bước tiếp theo |
|---|---|---|
| VERIFIED_REMOVED | Đã xác minh target được xử lý theo action trong phạm vi hỗ trợ | Ghi bằng chứng và tổng hợp trạng thái plan |
| RETAINED_BY_POLICY_OR_HOLD | Chưa được phép hủy | Giữ lý do, rà soát khi điều kiện thay đổi |
| REQUEST_ACCEPTED | Storage/provider nhận yêu cầu bất đồng bộ | Theo dõi kết quả cuối; chưa coi là hoàn tất |
| EFFECT_UNKNOWN | Mất phản hồi hoặc chưa đủ khả năng quan sát | Tra cứu/reconcile theo giao thức, không tự báo thành công |
| FAILED | Thao tác bị lỗi đã xác định | Retry hoặc can thiệp theo policy với plan còn hợp lệ |
| NOT_FOUND_WITH_CONTEXT | Target không có trong phép đọc với scope cụ thể | Đánh giá quyền đọc, version, inventory và giới hạn trước khi kết luận |

Một response “not found” với quyền đọc thiếu hoặc do delete marker không chứng minh mọi version đã bị hủy. Xóa thành công trong database không chứng minh warehouse, index và bản export đã xử lý.

### 8.4. Không có rollback chung cho việc xóa nhiều bản sao

Nếu database đã xóa nhưng object storage lỗi, trạng thái phải là PARTIAL hoặc tương đương, với đường phục hồi và mục tiêu còn lại rõ ràng. Không đặt toàn plan thành COMPLETE chỉ vì bước đầu không còn lỗi.

Retry cần đánh giá lại điều kiện và phối hợp theo giao thức, đồng thời giữ định danh các bước đã thực hiện. Nếu hold đến sau một bước hủy không đảo ngược, ghi đúng phần còn tồn tại, phần đã mất và thời điểm tương ứng. Không giả lập “rollback thành công” bằng cách phục hồi một hàng metadata trong khi payload đã không còn.

### 8.5. Bằng chứng hoàn tất có phạm vi

Một report hoàn tất nên nêu rõ inventory và các target đã xác minh, các loại bản sao xử lý bằng lịch riêng, ngoại lệ và phương pháp xác minh. Không dùng nhãn “đã xóa toàn bộ” nếu chỉ kiểm tra được một nhóm store.

Giữ decision/execution receipt tối thiểu để chứng minh ai cho phép, rule nào được áp dụng và các target nào đã xử lý. Receipt cũng có thể chứa dữ liệu liên kết tới cá nhân; cần policy riêng, không ghi nguyên payload đã có quyết định xóa chỉ để tạo bằng chứng xóa.

## 9. Retention không được phá transaction, idempotency và state machine

### 9.1. TTL của cache không phải vòng đời nghĩa vụ

Trong fixture, cache response idempotency hết sau 24 giờ nhưng hồ sơ nghiệp vụ giữ lâu hơn. Sau cache miss, API phải tra trạng thái durable và hợp đồng hiệu lực của request; không được coi “không tìm thấy key trong cache” là một ý định hoàn toàn mới.

Các lớp cần phân biệt:

- Cache dùng để trả response nhanh.
- Ánh xạ key/fingerprint dùng để nhận diện replay trong cửa sổ đã công bố.
- State machine và ràng buộc theo đơn/nghĩa vụ ngăn thực hiện lại hiệu lực.
- Ledger operation/payment dùng để đối soát và chứng minh kết quả.

Không mặc định giữ mọi request body lâu bằng hồ sơ kế toán hay chứng cứ quyết định. Có thể lưu fingerprint và dữ liệu tối thiểu cần thiết, nhưng phải đủ để kiểm tra xung đột và có vòng đời phù hợp.

### 9.2. Chưa rõ kết quả thì không purge dấu vết phục hồi

Provider đã thu tiền nhưng worker chưa ghi kết quả là trạng thái có thể xảy ra. Nếu cleanup xóa operation, external key hoặc outbox/inbox cần thiết lúc này, retry có thể thu trùng hoặc không còn cách đối soát.

Đường retention phải xét nghĩa vụ chưa giải quyết, không chỉ ngày tạo. Nếu phát hiện policy lưu quá ngắn so với cửa sổ callback/recovery cần thiết, đó là conflict cần sửa ở thiết kế và chính sách, không phải lý do để worker tự giữ mọi dữ liệu vô hạn.

External key cũng có cửa sổ bảo đảm riêng của provider. Giữ key trong database lâu hơn không tự kéo dài bảo đảm chống trùng bên ngoài; khi kết quả vẫn unknown ngoài cửa sổ đó, cần đối soát hoặc can thiệp theo giao thức.

### 9.3. Kết thúc vòng đời mà không cho tạo lại đối tượng cũ

Khi được phép purge hồ sơ chi tiết, cần xác định API xử lý request cũ thế nào. ID không nên được tái sử dụng để một retry tác động vào đối tượng mới; đối tượng hết vòng đời không được âm thầm tạo lại chỉ vì lookup trả thiếu dữ liệu.

Tombstone hoặc bản ghi kết quả tối thiểu có thể hỗ trợ chống tái thực hiện, nhưng cũng là dữ liệu cần scope, thời hạn và căn cứ. Phải định nghĩa toàn bộ safety horizon và hành vi từ chối request quá hạn; “tombstone giữ mãi” không thay cho thiết kế vòng đời.

## 10. Bản sao, archive, backup và dữ liệu phục hồi

### 10.1. Inventory phải theo luồng dữ liệu

Hồ sơ có thể tồn tại ở nhiều nơi:

```text
OLTP + lịch sử phiên bản
    -> audit/outbox/inbox
    -> object archive + các object version
    -> search index/cache
    -> warehouse/lake/CDC stream
    -> export báo cáo + working copy
    -> backup/snapshot/replica
    -> processor hoặc provider nhận dữ liệu
```

Không phải mọi nơi giữ cùng tập field hoặc cùng rule. Inventory cần mô tả lineage, bản authoritative, cách liên kết và đường thực thi nghĩa vụ ở từng nơi. Không sao chép toàn bộ PII sang archive “cho đủ hồ sơ” nếu chỉ cần một tập trường hẹp hơn.

Với provider/processor ngoài, ghi trách nhiệm và khả năng thực tế theo thỏa thuận áp dụng. Yêu cầu xóa đã gửi chưa đồng nghĩa đã hoàn tất; theo dõi acknowledgment, trạng thái cuối và phần dữ liệu mà bên đó giữ theo nghĩa vụ riêng đã được xác định.

### 10.2. Archive phải còn đọc được

Kiểm thử khả năng lấy lại đúng hồ sơ theo tenant/order/operation, đọc đúng schema, giải thích policy/approval version và xác minh integrity khi cần. Thời gian truy xuất phải phù hợp yêu cầu đã xác nhận, không chỉ phù hợp giá lưu trữ.

Mất khóa giải mã, mapping hoặc tài liệu đơn vị tiền có thể làm hồ sơ không sử dụng được dù byte vẫn còn. Khi xoay khóa hoặc thay định dạng, bảo đảm dữ liệu cần giữ tiếp tục truy xuất được và lịch sử chuyển đổi có thể kiểm tra.

Việc hủy khóa để làm dữ liệu không đọc được cần được đánh giá theo scope khóa, bản sao khóa, bản plaintext và tiêu chí xử lý dữ liệu được chấp nhận. Không gọi một thao tác key deletion là “đã xóa đúng nghĩa vụ” khi hồ sơ cần giữ vẫn dùng khóa đó hoặc bản sao vẫn đọc được.

### 10.3. Backup không phải ngoại lệ mặc định

Không giả định mọi backup được miễn yêu cầu xử lý dữ liệu, cũng không mặc định có thể xóa chọn lọc một record trong mọi bản backup. Thiết kế phải xác định retention backup, phạm vi truy cập, cách phục hồi và xử lý xung đột với nghĩa vụ áp dụng.

Một đường restore an toàn có thể yêu cầu:

1. Khôi phục vào môi trường cách ly, chưa cấp traffic hoặc export thông thường.
2. Đối chiếu với quyết định retention/hold/disposition mới nhất từ nguồn kiểm soát không bị quay lùi theo backup.
3. Áp dụng lại việc hạn chế sử dụng và các quyết định xóa tương ứng theo thiết kế.
4. Kiểm tra downstream/index/cache không phát tán lại dữ liệu đã xử lý.
5. Ghi kết quả trước khi cho môi trường phục hồi hoạt động.

Delete/hold ledger phục vụ bước này phải có khả năng tồn tại và được xác thực đủ lâu cho cửa sổ restore đã thiết kế, đồng thời có policy riêng. Nếu phục hồi ledger cũ cùng backup rồi tin nó là trạng thái mới nhất, dữ liệu đã xóa có thể xuất hiện trở lại.

### 10.4. Khóa lưu trữ không tự làm disposition

Trong [S3 Object Lock considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html), AWS lưu ý delete marker không xóa underlying version và lifecycle không xóa được version còn được bảo vệ. Do đó cần kiểm tra version và semantics của thao tác, thay vì suy ra purge từ việc object không xuất hiện trong phép đọc thông thường.

Hết hạn bảo vệ chỉ có nghĩa một rào cản đã hết; còn cần điều kiện policy, hold, quyền và workflow disposition. Ngược lại, cấu hình retention storage quá dài có thể cản việc xử lý dữ liệu sau này, nên phải đánh giá schedule và khả năng thay đổi trước khi bật chế độ không thể rút ngắn.

## 11. Thay đổi policy và các hành vi lạm dụng cần chặn

### 11.1. Policy là dữ liệu quản trị có phiên bản

Thay từ 90 ngày sang khoảng thời gian khác trong fixture cần ghi căn cứ, người phê duyệt, effective date, cohort chịu tác động và cách xử lý dữ liệu đã tồn tại. Không mặc định policy mới tự áp hồi tố hoặc chỉ áp cho record mới.

Chạy dry-run để biết số record trở thành candidate, record bị kéo dài, hold/obligation bị xung đột và giới hạn của storage. Dry-run không cấp quyền xóa; trước thực thi phải đánh giá plan theo policy/generation hiện hành.

Nếu cần rút ngắn, không tự suy ra hồ sơ cũ đều được phép hủy. Nếu cần kéo dài, không thể khôi phục hồ sơ đã bị hủy hợp lệ chỉ bằng migration metadata. Báo khoảng trống và kiểm tra căn cứ giữ bổ sung, thay vì ghi một `retainUntil` trong tương lai rồi tuyên bố mọi dữ liệu đã đủ coverage.

### 11.2. Các đường tấn công nghiệp vụ

| Hành vi | Invariant có nguy cơ | Kiểm soát và assertion cần có |
|---|---|---|
| Client sửa finalizedAt để làm hồ sơ quá hạn | R1, R5 | Trigger phải đến từ event hợp lệ; không nhận tuổi hồ sơ tùy ý từ request |
| Đổi tenant/record ID khi gọi purge hoặc hold | R1, R2, R5 | Authorization theo đối tượng và scope ở cả API lẫn worker |
| Gửi gỡ hold nhiều lần hoặc gỡ một hold trong tập nhiều hold | R1 | Idempotency theo hold operation; hold khác và retention period vẫn còn |
| Tạo hold giả để giữ dữ liệu người khác vô hạn | R2 | Thẩm quyền, căn cứ, scope và owner rà soát; không coi hold là cờ client được đặt |
| Sửa record class sang loại có TTL ngắn | R1, R5 | Phân loại có nguồn, version và audit; kiểm soát reclassification |
| Đóng tài khoản rồi retry thanh toán sau khi cache bị xóa | R4 | Nghĩa vụ durable và state machine vẫn ngăn thu lại |
| Xóa audit trước khi sửa giá hoặc tự phê duyệt | R1, R3 | Tách quyền, bảo vệ hồ sơ và ghi audit quản trị độc lập phù hợp |
| Dùng plan đã được duyệt trước khi có hold | R1 | Chặn plan/generation cũ theo giao thức phối hợp |
| Đặt COMPLETE sau khi chỉ database xóa xong | R6 | Tổng hợp target outcomes và bằng chứng đúng phạm vi |
| Restore backup để lấy lại dữ liệu đã xóa | R7 | Restore gate, control ledger mới nhất và kiểm tra trước khi cấp sử dụng |

## 12. Kiểm thử nghĩa vụ lưu giữ và bằng chứng vận hành

### 12.1. Ma trận kiểm thử tối thiểu

Các case dùng dữ liệu giả và clock có thể điều khiển. Không chạy thao tác hủy trên hồ sơ thật chỉ để kiểm tra rule của bài.

| Case | Thiết lập/hành động | Kỳ vọng |
|---|---|---|
| Trước biên retention | Đánh giá ngay trước minimum_retain_until | Không eligible |
| Đúng biên đã định nghĩa | Đánh giá đúng instant với rule eligible_at_or_after | Chỉ thành candidate nếu mọi điều kiện khác đạt |
| Thiếu trigger | Record cũ nhưng không có event final hợp lệ | NEEDS_REVIEW, không lấy createdAt thay thế |
| Retry/migrate archive | Gửi retry hoặc chuyển storage sau final | Trigger gốc và tuổi hồ sơ không bị đổi tùy tiện |
| Operation unknown | Case rất cũ, provider chưa xác định kết quả | Không purge dữ liệu cần đối soát; có owner/deadline exception |
| Hai hold | Gỡ HOLD-A khi HOLD-B còn hiệu lực | Vẫn bị chặn disposition |
| Hold đang áp dụng | Chưa bảo vệ đủ target | Chặn attempt mới trong scope; không báo coverage hoàn chỉnh |
| Hold cạnh tranh purge | Điều phối hold và worker ở sát ranh giới irreversible delete | Kết quả tuân thủ hợp đồng thứ tự; không để worker cũ vượt hold đã hiệu lực |
| Plan cũ | Đổi policy generation hoặc retention revision | Plan cũ không được thực thi như còn hợp lệ |
| Sai tenant/sai quyền | Caller và bulk job tác động record ngoài scope | Bị từ chối, không đổi payload/hold/retention |
| Xóa từng phần | Một target xóa xong, target khác timeout | PARTIAL/EFFECT_UNKNOWN; không VERIFIED_COMPLETE |
| Worker crash rồi retry | Dừng sau một bước xử lý target | Tiếp tục đúng target/version, không tác động đối tượng mới |
| Cache key hết hạn | Retry đơn đã thanh toán sau TTL response cache | Không tạo nghĩa vụ thu tiền mới |
| Restore backup cũ | Phục hồi bản trước quyết định xóa hoặc hold | Áp trạng thái mới nhất trước khi cho sử dụng lại |
| Lệch clock/quy tắc lịch | Kiểm tra năm nhuận, timezone, biên ngày và clock bất thường | Kết quả đúng rule; ngừng hủy nếu không xác minh được điều kiện |
| Archive không đọc được | Làm thiếu schema hoặc khóa trong fixture | Phát hiện vi phạm khả năng truy xuất; không báo chỉ tiêu retention đã đạt |
| Conflict giữ/xóa | Hai yêu cầu áp dụng chưa được phân giải | Ghi conflict và scope; không tự lấy TTL nhỏ nhất hoặc `max` cho mọi field |

### 12.2. Kịch bản: hold đến sau khi plan đã lập

```text
Given:
    record đủ tuổi theo fixture, không còn nghĩa vụ pending
    worker đã lập plan với retentionRevision=12
    chưa qua ranh giới irreversible delete

When:
    hold hợp lệ được tiếp nhận qua cơ chế điều phối
    hệ thống chặn các attempt mới theo hợp đồng đã xác định
    worker cũ cố thực hiện plan revision 12

Then:
    plan cũ không được vượt delete gate
    payload/versions cần bảo vệ còn tồn tại
    hold có coverage rõ ràng trước khi được báo hiệu lực đầy đủ
    audit thể hiện thứ tự, generation và lý do bị chặn
```

Test phải chứng minh gate/protection thật, không chỉ gọi hàm planner lần hai. Thêm lịch chạy ngược lại, trong đó bước xóa đã không thể đảo ngược trước khi hold có thể tiếp nhận; kết quả phải ghi giới hạn/mất dữ liệu tương ứng theo hợp đồng, không tạo báo cáo hold thành công giả.

### 12.3. Kịch bản: primary đã xóa nhưng bản backup còn tồn tại

```text
Given:
    disposition theo policy đã xử lý dữ liệu active trong inventory
    backup có lịch lưu và cơ chế hạn chế sử dụng đã được xác nhận
    control ledger mới nhất ghi quyết định cần áp lại khi restore

When:
    phục hồi một backup trước quyết định đó trong môi trường cách ly

Then:
    không cấp traffic chỉ vì database restore thành công
    đối chiếu ledger hiện hành và áp lại disposition/hold phù hợp
    xác minh index/export/downstream trước khi mở lại sử dụng
    report phân biệt active deletion với vòng đời backup
```

Fixture này kiểm tra kỹ thuật restore gate, không tự xác nhận một cách xử lý backup cụ thể đã đáp ứng mọi yêu cầu pháp lý.

### 12.4. Bằng chứng và chỉ số cần theo dõi

Decision/execution record nên liên kết tenant/record class, policy/rule version, trigger event, hold revision, plan/job/attempt và target version. Giữ reason code, outcome, verification method và người/service thực hiện; tránh sao chép payload nhạy cảm vào log quản trị.

Các chỉ số có ích gồm:

- Record thiếu trigger, không phân loại được hoặc có policy conflict.
- Hold đang APPLYING quá lâu, coverage thiếu và hold quá hạn rà soát.
- Candidate/quyết định xóa bị tồn đọng quá deadline theo chính sách.
- Attempt bị chặn do stale plan, sai quyền hoặc storage retention.
- Target PARTIAL/EFFECT_UNKNOWN và thời gian đối soát.
- Tỷ lệ truy xuất archive thành công, thời gian lấy hồ sơ và lỗi giải mã/schema.
- Kết quả diễn tập restore có áp lại control ledger mới nhất.

Số lượng byte được giữ hoặc xóa không tự chứng minh tuân thủ. Cần đối chiếu với đúng obligation, scope, timeline và mức dữ liệu thực tế được bảo vệ/xử lý.

## 13. Bài tập áp dụng

1. Với một luồng đơn hàng có approval, payment và refund, phân loại hồ sơ cần giữ, log chẩn đoán, cache và bản sao; nêu dữ liệu tối thiểu để chứng minh từng quyết định.
2. Viết một retention rule giả định với trigger, cách tính lịch, phạm vi, quyền thay đổi, hold và disposition. Chỉ ra trường nào có thể bị client sửa nếu thiết kế sai.
3. Cho hai obligation giữ tối thiểu cùng áp dụng nhưng có một yêu cầu kết thúc xử lý dữ liệu chưa được phân giải. Giải thích vì sao lấy `max(retainUntil)` chưa đủ để ra lệnh purge hoặc giữ nguyên mọi field.
4. Mô tả lịch chạy của một hold cạnh tranh purge ở hai thứ tự khác nhau; nêu điểm nào được coi là hiệu lực và điểm nào không còn đảo ngược.
5. Cho cache idempotency hết TTL và provider trả callback muộn. Chứng minh hệ thống vẫn nhận diện nghĩa vụ cũ, không thu lại và không xóa mất đường đối soát.
6. Thiết kế kiểm thử restore backup chứa hồ sơ đã được disposition. Nêu nguồn control state mới nhất, bước chặn cấp sử dụng và bằng chứng xác minh.

Một lời giải đạt yêu cầu phải chỉ ra **giữ cái gì, vì căn cứ nào, tới điều kiện nào, ai có quyền thay đổi, bản sao nằm đâu và bằng chứng nào cho thấy workflow đã thực thi đúng phạm vi**.
