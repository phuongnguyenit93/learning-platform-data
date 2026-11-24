# Entitlement decision audit: lưu bằng chứng cho quyết định quyền sử dụng

## 1. Audit cần giải thích được quyết định, không chỉ ghi một dòng log

Trong chương **Entitlement Rules**, entitlement decision audit là việc lưu bằng chứng về cách hệ thống quyết định một chủ thể có được dùng một năng lực sản phẩm hay không. Bằng chứng phải giúp trả lời: **ai yêu cầu, trên đối tượng nào, dựa vào nguồn quyền và điều kiện nào, kết quả là gì, rồi hệ thống thực sự đã làm gì**.

Ví dụ, dòng log `premium check passed` không đủ để giải thích vì sao U17 được xuất báo cáo P1. Nó không cho biết tenant, phiên bản entitlement, phạm vi tài nguyên, thời hạn, quota hoặc việc file cuối cùng có được công bố hay không.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, tập trung bảo vệ quy tắc nghiệp vụ khỏi bỏ bước kiểm tra, thao tác sai quyền và gửi yêu cầu trùng. Audit hỗ trợ phát hiện, điều tra và kiểm chứng các cơ chế đó; bản thân audit không thay thế kiểm tra quyền hoặc transaction bảo vệ nghiệp vụ.

Sau bài học, bạn cần:

- Phân biệt quyết định cho phép với việc tiếp nhận lệnh và hiệu lực đã hoàn tất.
- Thiết kế bản ghi audit đủ để giải thích một quyết định entitlement.
- Giữ đúng bằng chứng khi có rollback, retry, cache cũ và tác vụ nền.
- Bảo vệ dữ liệu audit khỏi sửa, lộ thông tin hoặc bị dùng để vượt ranh giới tenant.
- Kiểm thử được tính đầy đủ và nhất quán của chuỗi quyết định đến hiệu lực.

## 2. Ba loại sự thật cần được tách biệt

Một entitlement có thể cho phép người dùng xuất báo cáo, nhưng một lần xuất cụ thể còn có thể bị chặn vì tài nguyên không thuộc phạm vi hoặc quota đã hết. Sau khi cho phép, worker vẫn có thể thất bại khi tạo file.

| Lớp thông tin | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Nguồn cấp quyền | Chủ thể được cấp những gì? | Grant G21 phiên bản 4 cho U17 xuất báo cáo trong P1 |
| Quyết định | Yêu cầu này có được phép ở thời điểm đánh giá không? | D301 cho phép xuất R8 vì grant phù hợp, chưa hết hạn và còn quota |
| Hiệu lực thực tế | Hệ thống đã tiếp nhận hoặc hoàn tất việc gì? | Operation O91 đã giữ quota; sau đó file F7 được công bố |

Thay đổi grant là một sự kiện quản trị quyền. Nó không thay thế bản ghi đánh giá từng yêu cầu. Ngược lại, một quyết định `ALLOW` cũng không chứng minh rằng file đã được tạo hoặc người dùng đã tải file.

Cần phân biệt audit nghiệp vụ với các loại dữ liệu gần nhau:

- Log ứng dụng hỗ trợ chẩn đoán lỗi, thường có mức chi tiết và thời gian lưu khác nhau.
- Trace mô tả đường đi qua các dịch vụ, nhưng không tự cung cấp đủ căn cứ cấp quyền.
- Metric cho biết tổng số cho phép, từ chối hoặc lỗi, nhưng không giải thích một trường hợp cụ thể.
- Bản ghi nguồn như grant, membership và seat mô tả trạng thái, có thể đã thay đổi sau quyết định.

Có thể liên kết các loại dữ liệu qua định danh phù hợp, nhưng không coi một trace ID hoặc một dòng log bất kỳ là bằng chứng đầy đủ về entitlement.

## 3. Tình huống xuyên suốt

Giả sử nền tảng phân tích dữ liệu có tình huống sau:

| Thành phần | Giá trị minh họa |
| --- | --- |
| Tenant | Tổ chức A |
| Người gọi | U17, đang là thành viên A |
| Hành động | `REPORT_EXPORT / EXPORT_CSV` |
| Tài nguyên | Báo cáo R8 thuộc dự án P1 |
| Nguồn quyền | Grant G21 phiên bản 4, cấp qua seat S5 |
| Thời hạn | Đang có hiệu lực tại lúc nhận lệnh |
| Quota | Cho giữ thêm tối đa 200 dòng trong cửa sổ Q12 |
| Operation | O91, đại diện cho một ý định xuất |

Chuỗi xử lý có thể diễn ra:

```text
T1: D301 cho phép tiếp nhận O91; giữ quota và lưu lệnh.
T2: Quản trị viên thu hồi grant G21, tạo phiên bản trạng thái mới.
T3: Worker đánh giá lại trước khi chạy O91, tạo D302.
T4: D302 từ chối vì quyền đã bị thu hồi; O91 không được công bố file.
```

Hai quyết định khác nhau không nhất thiết là mâu thuẫn. Chúng được đánh giá ở hai thời điểm với dữ liệu khác nhau. Audit cần chứng minh được sự khác biệt đó thay vì chỉ lưu trạng thái grant hiện tại rồi kết luận quyết định cũ sai.

Mô hình bài này yêu cầu quyền còn phù hợp khi nhận lệnh, trước thực thi và trước công bố hoặc truy cập kết quả theo từng điểm kiểm soát. Nếu một sản phẩm bảo lưu quyền cho lệnh đã được chấp nhận trước khi thu hồi, cần ghi rõ phiên bản chính sách và lý do ngoại lệ; không để hành vi đó xuất hiện chỉ vì worker bỏ kiểm tra.

## 4. Các bất biến cần bảo vệ trong audit

Những bất biến dưới đây giúp biến audit thành bằng chứng có thể đối chiếu:

1. Mọi hiệu lực được bảo vệ phải liên kết được với quyết định cho phép phù hợp tại điểm thực thi mà chính sách yêu cầu.
2. Quyết định gắn với đúng tenant, actor, chủ thể hưởng quyền, hành động, tài nguyên và nội dung lệnh; không được dùng lại cho yêu cầu khác.
3. Bản ghi phân biệt rõ dữ kiện đã xác minh, dữ liệu do client khai và dữ liệu chưa xác định.
4. Audit không tuyên bố nghiệp vụ đã commit nếu transaction tương ứng rollback.
5. Retry cùng một lần truyền audit không tạo thêm một quyết định nghiệp vụ giả.
6. Một lần đánh giá lại thực sự tạo quyết định mới, có liên kết đến cùng operation và quyết định trước khi cần.
7. Bản ghi đã chốt không bị sửa để che lỗi; bổ sung hoặc đính chính bằng sự kiện có quan hệ rõ ràng.
8. Người đọc audit không được vượt quyền xem dữ liệu của tenant hoặc chủ thể khác.

Bất biến thứ nhất phải có ranh giới cụ thể. Trong một cơ sở dữ liệu, có thể ràng buộc việc tiếp nhận lệnh và audit trong cùng transaction. Với nhiều dịch vụ hoặc tác động bên ngoài, cần chuỗi liên kết bền vững và đối soát; một lệnh ghi log qua mạng không tự tạo nguyên tử với hiệu lực ở dịch vụ khác.

Không cần giả vờ mọi phép tính tạm thời trong một transaction đều là quyết định đã có hiệu lực. Có thể tách **đánh giá tạm thời**, **quyết định được dùng để xử lý** và **kết quả thực thi**. Nếu sản phẩm yêu cầu lưu cả đánh giá bị hủy do rollback, phải thiết kế đường ghi riêng và đánh dấu đúng là chưa được áp dụng.

## 5. Mô hình bản ghi quyết định

Một bản ghi có thể gồm các nhóm thông tin sau:

| Nhóm | Trường minh họa | Mục đích |
| --- | --- | --- |
| Định danh | `event_id`, `decision_id`, `operation_id`, `request_id` | Phân biệt lần truyền, lần đánh giá và ý định nghiệp vụ |
| Ngữ cảnh tin cậy | Tenant đã xác minh, actor, loại xác thực, chủ thể đại diện | Giải thích ai thực sự gọi và thay mặt ai |
| Mục tiêu | Tính năng, hành động, loại và ID tài nguyên, dự án thực tế | Ràng buộc quyết định với đúng đối tượng |
| Căn cứ | Grant, nguồn cấp, seat, nhóm, phiên bản và policy | Giải thích quyền đến từ đâu |
| Dữ kiện | Trạng thái, thời hạn, quota, quan hệ đối tượng và phiên bản | Giải thích các điều kiện đã được kiểm tra |
| Kết quả | `ALLOW`, `DENY`, `INDETERMINATE`, mã lý do | Phân biệt được cho phép, bị chặn và thiếu căn cứ kết luận |
| Thực thi | Điểm kiểm soát, kết quả tiếp nhận, commit, rollback hoặc hiệu lực liên quan | Tránh đồng nhất cho phép với hoàn tất |
| Độ mới | Thời điểm đánh giá, phiên bản nguồn, cache age hoặc snapshot reference | Đánh giá nguy cơ dùng dữ liệu cũ |
| Lược đồ | `schema_version`, phiên bản bộ đánh giá | Giải mã và đối chiếu về sau |

### 5.1. Phân biệt actor và beneficiary

Actor là người hoặc tiến trình thực hiện yêu cầu. Beneficiary là chủ thể hưởng entitlement. Chúng có thể khác nhau khi một service account chạy tác vụ cho người dùng hoặc một người có ủy nhiệm thao tác thay tổ chức.

Bản ghi cần giữ được cả hai và căn cứ đại diện. Nếu chỉ lưu `userId`, sẽ khó biết worker đang dùng quyền riêng hay thực thi một lệnh của người khác.

Tenant trong bản ghi có thẩm quyền phải đến từ ngữ cảnh đã xác minh. Nếu client cố gửi ID tenant B trong lúc chỉ có quyền ở A, ghi nhận đó là giá trị mục tiêu được yêu cầu hoặc dữ liệu chưa tin cậy, không tự ghi sự kiện dưới tenant B như thể người gọi đã có quyền ở đó.

Đối với yêu cầu chưa xác thực hoặc không xác định được tenant, dùng luồng sự kiện ingress hoặc an ninh phù hợp. Không gán tùy tiện một tenant hợp lệ chỉ để điền đủ trường.

### 5.2. Mã lý do phải diễn tả được nguyên nhân

Một tập mã lý do có thể gồm:

```text
MATCHING_GRANT
NO_MATCHING_ENTITLEMENT
RESOURCE_OUT_OF_SCOPE
MEMBERSHIP_INACTIVE
SEAT_UNASSIGNED
GRANT_EXPIRED
GRANT_REVOKED
QUOTA_EXCEEDED
POLICY_SOURCE_UNAVAILABLE
STALE_EVIDENCE
IDEMPOTENCY_CONFLICT
```

Mã máy đọc được giúp thống kê và kiểm thử; phần giải thích có cấu trúc giúp điều tra. Không chỉ lưu một chuỗi tự do dài như `not allowed` hoặc `premium false`.

Nếu có nhiều nguyên nhân, quy định cách chọn lý do chính và cách lưu các điều kiện liên quan. Một bộ đánh giá dừng ở lỗi đầu tiên không được tuyên bố rằng những điều kiện chưa chạy đều đã đạt.

Thông tin chi tiết nội bộ không nhất thiết được trả cho người gọi. Một thông báo từ chối bên ngoài có thể hạn chế chi tiết để tránh tiết lộ tài nguyên khác tenant, trong khi audit dành cho người có quyền điều tra lưu được bằng chứng cần thiết.

## 6. Lưu bằng chứng nào để giải thích được quyết định cũ?

### 6.1. Chỉ lưu ID đến dữ liệu có thể sửa là chưa đủ

Nếu bản ghi chỉ chứa `grant_id = G21`, nhưng G21 đã bị thay đổi ba lần sau đó, việc mở G21 hiện tại không chứng minh dữ liệu tại T1. Cần lưu phiên bản bất biến hoặc một ảnh chụp tối thiểu của các dữ kiện đã dùng.

Ví dụ tập bằng chứng cho D301:

```text
grant G21 version 4: ACTIVE, EXPORT_CSV, PROJECT P1
seat S5 version 2: assigned to U17
membership M8 version 7: ACTIVE in tenant A
resource R8 version 11: belongs to project P1
policy entitlement-export version 6
evaluated_at: thời điểm máy chủ đã dùng để kiểm tra thời hạn
quota window Q12: reservation 200 accepted
```

Có thể lưu các nội dung trong kho bằng chứng riêng rồi tham chiếu bằng ID và digest. Digest giúp kiểm tra nội dung có thay đổi hay không khi vẫn còn nội dung để đối chiếu; digest không tự khôi phục một snapshot đã mất.

Lưu một tham chiếu bất biến cũng chỉ có ích nếu tham chiếu còn truy xuất được trong khoảng thời gian cần điều tra. Thời gian lưu policy, snapshot và các khóa hoặc cơ chế xác minh liên quan phải tương thích với vòng đời bằng chứng.

### 6.2. Ghi đúng phép kết hợp quyền

Nếu có nhiều grant, bằng chứng cần cho biết grant nào thực sự tạo ra quyết định và quy tắc kết hợp nào được dùng. Không lưu riêng `feature=true` và `resource=true` rồi làm mất quan hệ giữa chúng.

Ví dụ, G1 cho xuất ở P1 và G2 chỉ cho xem ở P2 không tạo ra quyền xuất ở P2. Audit tốt cần đủ dữ kiện để phát hiện lỗi ghép hai mảnh quyền này, thay vì chỉ ghi rằng đã tìm thấy hai điều kiện đúng ở đâu đó.

Không nhất thiết lưu toàn bộ mọi grant trong hệ thống cho một request. Có thể lưu tập được chọn, các điều kiện bắt buộc và bằng chứng giới hạn của tìm kiếm, tùy khả năng tái hiện cần thiết. Nếu không lưu đủ để chứng minh đã xét toàn bộ tập ứng viên, không tuyên bố có thể tái dựng chính xác mọi lý do của kết quả `NO_MATCHING_ENTITLEMENT`.

### 6.3. Tái hiện quá khứ khác với đánh giá hiện tại

Có hai câu hỏi điều tra khác nhau:

1. Với policy và dữ kiện tại T1, kết quả D301 có đúng không?
2. Với policy và dữ kiện hiện tại, cùng ý định đó còn được phép không?

Câu hỏi thứ nhất dùng bộ đánh giá, thời điểm và bằng chứng lịch sử phù hợp. Câu hỏi thứ hai tạo một đánh giá mới. Không chạy policy mới lên dữ liệu mới rồi kết luận đó là bằng chứng về quyết định cũ.

Nếu một điều kiện phụ thuộc vào nguồn ngoài nhưng không có snapshot hoặc câu trả lời có thể kiểm chứng, audit chỉ nên nêu giới hạn bằng chứng. Không mô tả việc tái hiện là hoàn toàn xác định khi còn thiếu đầu vào.

## 7. Ví dụ sự kiện có cấu trúc

Dưới đây là một sự kiện minh họa tại điểm tiếp nhận lệnh. Các ID và giá trị đều là dữ liệu giả định:

```json
{
  "schema_version": 1,
  "event_id": "evt_601",
  "event_type": "ENTITLEMENT_DECISION_RECORDED",
  "decision_id": "dec_301",
  "operation_id": "op_91",
  "request_id": "req_77",
  "checkpoint": "COMMAND_ACCEPTANCE",
  "evaluated_at": "2026-12-10T03:00:00Z",
  "tenant_id": "tenant_A",
  "actor": {
    "type": "USER",
    "id": "user_17"
  },
  "beneficiary": {
    "type": "USER",
    "id": "user_17"
  },
  "action": "EXPORT_CSV",
  "feature": "REPORT_EXPORT",
  "resource": {
    "type": "REPORT",
    "id": "report_8",
    "project_id": "project_1",
    "version": 11
  },
  "policy": {
    "id": "entitlement-export",
    "version": 6
  },
  "evidence_refs": [
    { "type": "GRANT", "id": "grant_21", "version": 4 },
    { "type": "SEAT", "id": "seat_5", "version": 2 },
    { "type": "MEMBERSHIP", "id": "membership_8", "version": 7 }
  ],
  "decision": "ALLOW",
  "reason_codes": ["MATCHING_GRANT"],
  "command_fingerprint": "example-digest",
  "quota": {
    "window_id": "quota_12",
    "reservation_id": "reservation_44",
    "reserved_units": 200,
    "unit": "ROW"
  },
  "enforcement": {
    "outcome": "COMMAND_ACCEPTED",
    "execution_completed": false
  },
  "evidence_freshness": {
    "mode": "TRANSACTIONAL_SOURCE",
    "authorization_epoch": 42
  }
}
```

`COMMAND_ACCEPTED` chỉ đúng khi sự kiện và việc tiếp nhận lệnh đã được commit theo thiết kế. Không phát nội dung đó ra ngoài trước commit rồi để transaction rollback sau đó.

`command_fingerprint` phải được tính trên nội dung nghiệp vụ đã chuẩn hóa ở máy chủ, chẳng hạn tenant, chủ thể, hành động, tài nguyên, bộ lọc và giới hạn dòng. Không dùng một digest do client tự gửi làm bằng chứng nội dung đã được ràng buộc.

Nếu sau đó worker bị chặn do thu hồi quyền, tạo D302 ở checkpoint tương ứng và liên kết O91. Không sửa D301 từ `ALLOW` thành `DENY` để làm lịch sử trông nhất quán với trạng thái hiện tại.

## 8. Ranh giới transaction: không ghi sai về commit và rollback

### 8.1. Cho phép và tiếp nhận lệnh trong cùng cơ sở dữ liệu

Với một thao tác được bảo vệ, transaction có thể cùng lưu:

```text
quyết định cuối cùng tại checkpoint
+ operation hoặc thay đổi nghiệp vụ
+ reservation quota nếu có
+ audit event cục bộ
+ outbox để chuyển audit và lệnh xử lý sang hệ thống khác
```

Nếu một bước bắt buộc thất bại, toàn bộ transaction rollback. Nhờ vậy, không có operation đã commit nhưng thiếu bằng chứng tiếp nhận bắt buộc, và không có sự kiện đã chốt nói rằng operation được tiếp nhận trong khi nó chưa tồn tại.

Điều này yêu cầu mọi đường tạo hiệu lực đều đi qua cơ chế tương ứng. Một endpoint quản trị hoặc công cụ sửa dữ liệu đi vòng transaction sẽ làm mất bảo đảm; cần kiểm soát các đường đó bằng quyền, quy trình và đối soát thích hợp.

### 8.2. Từ chối không được vô tình rollback luôn audit

Một lỗi phổ biến là:

```java
@Transactional
public void exportReport(...) {
    audit.insertDenied(...);
    throw new AccessDeniedException("DENIED");
}
```

Nếu ngoại lệ làm transaction rollback, bản ghi từ chối cũng mất. API có thể trả lỗi đúng nhưng audit không còn bằng chứng.

Một cách xử lý là trả một kết quả miền như `DeniedResult`, commit transaction chỉ chứa bằng chứng từ chối, rồi để tầng HTTP chuyển kết quả thành response sau khi transaction hoàn tất. Không phát sinh thay đổi nghiệp vụ trong nhánh này.

Một cách khác là đường ghi bền vững độc lập cho sự kiện từ chối, nhưng phải hiểu ranh giới commit và tránh giữ khóa nghiệp vụ không cần thiết khi chờ ghi. Không chỉ thêm một annotation transaction mới rồi giả định mọi rủi ro kết nối, khóa và lỗi ghi đã được giải quyết.

### 8.3. Lỗi hạ tầng khác với từ chối do policy

Nếu nguồn entitlement không truy cập được, hệ thống không biết chắc người dùng thiếu quyền. Có thể ghi:

```text
policy_decision = INDETERMINATE
reason = POLICY_SOURCE_UNAVAILABLE
enforcement_outcome = REQUEST_BLOCKED
```

Trong mô hình xuất dữ liệu nhạy cảm của bài, không có bằng chứng đủ mới thì không tạo hiệu lực được bảo vệ. Nhưng audit vẫn phải phân biệt lỗi thiếu dữ kiện với kết quả `DENY` đã xác định. Nếu gộp chúng, một sự cố hạ tầng dễ bị hiểu nhầm là hành vi lạm dụng hoặc cấu hình quyền sai.

Nếu cả nơi lưu audit bắt buộc cũng không ghi được, không thể vừa cho phép hiệu lực vừa tuyên bố có bằng chứng đầy đủ. Với checkpoint yêu cầu audit nguyên tử, transaction phải không commit hiệu lực; dùng kênh giám sát sự cố phù hợp và không báo rằng audit đã lưu thành công khi chưa có xác nhận.

### 8.4. Đánh giá cho phép nhưng transaction bị hủy

Một phép đánh giá có thể trả `ALLOW` trong bộ nhớ, sau đó ghi quota hoặc operation thất bại. Khi đó chưa có một quyết định tiếp nhận đã commit.

Nếu cần ghi lại diễn biến này, tầng điều phối sau khi transaction đã rollback có thể lưu sự kiện `EVALUATION_ABORTED` hoặc `ENFORCEMENT_FAILED`, gắn với request hoặc operation dự kiến. Sự kiện phải nói rõ không có hiệu lực nghiệp vụ được xác nhận, thay vì ghi `COMMAND_ACCEPTED`.

Không giữ một bản ghi cho phép trước transaction nghiệp vụ rồi coi đó là chứng cứ nghiệp vụ đã hoàn tất. Hai commit độc lập có thể nằm ở hai phía của một sự cố process.

## 9. Mã giả Java cho quyết định và audit cục bộ

Ví dụ sau nhận một lệnh xuất, đánh giá quyền và lưu kết quả trong cùng cơ sở dữ liệu. Tenant và actor đã được xác thực trước khi vào hàm. Mô hình dùng khóa điều phối quyền theo tenant; các đường sửa dữ liệu ảnh hưởng đến quyết định phải tuân thủ cùng giao thức hoặc một cơ chế phiên bản tương đương.

Đây là mã giả mô tả ranh giới nghiệp vụ, không phải lớp Java hoàn chỉnh:

```java
@Transactional
public ExportStartResult decideAndAccept(
        VerifiedContext ctx, ExportCommand command) {

    authorizationGuard.lockTenant(ctx.tenantId());

    var facts = evidence.captureWithinTenant(ctx, command);
    // Có phiên bản grant, membership, seat, tài nguyên và policy.
    // Không tìm thấy hoặc không đủ dữ kiện cũng là đầu vào có cấu trúc.
    var candidate = policy.evaluate(
        facts, command.action(), clock.instant()
    );
    var fingerprint = fingerprints.forCanonicalCommand(ctx, command);
    var decisionId = ids.newDecisionId();

    if (!candidate.isAllow()) {
        var result = ExportStartResult.blocked(candidate.outcome());
        decisionAudit.append(
            decisionId, ctx, command, facts, candidate,
            "REQUEST_BLOCKED", null
        );
        auditOutbox.appendDecisionRecorded(decisionId);
        return result; // Không ném lỗi làm mất audit từ chối.
    }

    var existing = operations.findByKeyForUpdate(
        ctx.tenantId(), ctx.actorId(), command.idempotencyKey()
    );

    if (existing.isPresent()) {
        if (!existing.get().matches(fingerprint)) {
            decisionAudit.appendConflict(
                decisionId, ctx, command, facts, existing.get().id()
            );
            auditOutbox.appendDecisionRecorded(decisionId);
            return ExportStartResult.conflict();
        }

        access.requireCanReadOperation(ctx, existing.get());
        decisionAudit.append(
            decisionId, ctx, command, facts, candidate,
            "EXISTING_OPERATION_RETURNED", existing.get().id()
        );
        auditOutbox.appendDecisionRecorded(decisionId);
        return ExportStartResult.existing(existing.get());
    }

    var operationId = ids.newOperationId();
    var reservation = quotas.tryReserveForUpdate(
        candidate.budgetId(), candidate.quotaWindow(),
        operationId, command.validatedRowLimit()
    );

    if (reservation.isEmpty()) {
        decisionAudit.appendQuotaDenied(
            decisionId, ctx, command, facts, candidate
        );
        auditOutbox.appendDecisionRecorded(decisionId);
        return ExportStartResult.denied("QUOTA_EXCEEDED");
    }

    var operation = operations.createPending(
        operationId, ctx, command, fingerprint,
        candidate.scopeBinding(), decisionId, reservation.get()
    );

    decisionAudit.appendAccepted(
        decisionId, ctx, command, facts, candidate, operation
    );
    auditOutbox.appendDecisionRecorded(decisionId);
    executionOutbox.appendExportRequested(operation.id());

    return ExportStartResult.accepted(operation);
}
```

Những giả định cần thực hiện trong hệ thống thật:

- Kết quả trả về chỉ được chuyển thành response sau khi transaction commit thành công.
- `candidate` chưa phải quyết định tiếp nhận đã chốt. Các hàm ghi audit lưu kết quả cuối ở checkpoint; nhánh hết quota phải thể hiện việc entitlement phù hợp nhưng điều kiện ngân sách đã chặn lệnh.
- `facts` giữ được phiên bản và dữ kiện đã dùng. Nó không chỉ là các ID trỏ đến hàng có thể sửa tùy ý.
- Các thao tác có điều kiện và unique constraint bảo vệ idempotency, reservation và liên kết operation. Việc `find` trước khi `create` không tự chống được tranh chấp.
- Quyền xem operation cũ vẫn được kiểm tra. Nếu nhánh này từ chối, triển khai cần đưa kết quả về cùng cơ chế audit có cấu trúc, thay vì để một ngoại lệ chưa được xử lý làm mất bằng chứng.
- Không ghi raw token, toàn bộ dữ liệu báo cáo hoặc request body không kiểm soát vào `decisionAudit`.
- Outbox chỉ được phát sau commit. Consumer nhận lại cùng event không tạo một decision mới.
- Mã ví dụ chỉ xử lý checkpoint tiếp nhận. Worker phải tạo quyết định của checkpoint riêng theo chính sách.

Nếu dùng ngoại lệ cho lỗi nội bộ làm rollback, tầng ngoài có thể ghi sự kiện xử lý bị hủy qua đường riêng. Nó không được sửa một sự kiện đã commit để giả định đã rollback, hoặc ngược lại.

## 10. Retry, idempotency và chuỗi quyết định trong tác vụ nền

### 10.1. Mỗi định danh có một nhiệm vụ

| Định danh | Ý nghĩa | Điều không nên làm |
| --- | --- | --- |
| `request_id` | Một lần vào hệ thống | Dùng nó làm định danh duy nhất của ý định qua mọi retry |
| `operation_id` | Ý định nghiệp vụ bền vững | Tạo mới chỉ vì worker nhận lại thông điệp |
| `decision_id` | Một lần đánh giá có nội dung xác định | Dùng lại ID khi đã đánh giá bằng dữ kiện mới |
| `event_id` | Một sự kiện audit đã được hình thành | Đổi ID mỗi lần phát lại cùng sự kiện |
| `delivery_attempt_id` | Một lần vận chuyển sự kiện nếu cần theo dõi | Coi mỗi lần vận chuyển là một quyết định mới |

Cùng một operation có thể có nhiều decision hợp lệ: khi nhận lệnh, trước chạy, trước công bố và khi tải. Cùng một decision có thể được vận chuyển nhiều lần đến kho audit, nhưng đó vẫn là một sự kiện nguồn.

Một retry HTTP có thể cần kiểm tra quyền hiện tại trước khi trả operation cũ. Nếu thực sự đánh giá lại, ghi decision mới với outcome `EXISTING_OPERATION_RETURNED` hoặc kết quả bị chặn tương ứng; không ghi rằng operation vừa được tạo lần nữa.

### 10.2. Ràng buộc quyết định với ý định và checkpoint

Không cho worker nhận một `decision_id` có kết quả `ALLOW` rồi dùng cho mọi việc. Cần kiểm tra nó liên quan đến đúng operation, tài nguyên, chủ thể, hành động và checkpoint.

Một quyết định cho phép tiếp nhận không tự là quyết định cho phép công bố file sau ba giờ. Một quyết định cho export giới hạn 200 dòng cũng không cho phép worker đổi bộ lọc để xuất toàn bộ tenant.

Thông điệp hàng đợi nên tham chiếu operation bền vững. Worker đọc binding từ nguồn máy chủ, tạo đánh giá mới nếu chính sách yêu cầu và liên kết quyết định trước bằng các trường quan hệ thích hợp.

### 10.3. Không dùng thời điểm nhận sự kiện làm toàn bộ thứ tự nghiệp vụ

Trong hệ thống phân tán, sự kiện có thể đến kho audit sai thứ tự. Có thể nhận sự kiện hoàn tất trước sự kiện tiếp nhận do độ trễ vận chuyển.

Cần phân biệt `evaluated_at`, `recorded_at`, thời điểm hiệu lực và `ingested_at`. Sử dụng phiên bản nguồn, trình tự theo operation hoặc quan hệ nhân quả để ghép chuỗi. Đồng hồ của hai dịch vụ không tạo một thứ tự tổng tuyệt đối chỉ vì cùng lưu timestamp UTC.

Một trường sequence chỉ có ý nghĩa khi biết phạm vi và cơ chế cấp nó. Sequence theo từng operation không chứng minh thứ tự toàn hệ thống; sequence trong kho nhận chỉ cho biết thứ tự nhận.

### 10.4. Liên kết với hiệu lực bên ngoài

Nếu worker tạo file trong kho đối tượng hoặc một dịch vụ khác cấp quyền sử dụng, transaction cục bộ không bao trùm các hệ thống đó. Audit cần liên kết lệnh đã commit, định danh thực thi bên ngoài, kết quả đã xác minh và quyết định tại điểm công bố.

Timeout nghĩa là chưa biết kết quả trong nhiều tình huống. Ghi `OUTCOME_UNKNOWN` hoặc trạng thái tương đương khi phù hợp, tiếp tục đối soát theo cùng định danh và không tự biến thành “không có hiệu lực” để tạo thao tác mới.

Đối với file, nội dung trung gian cần được giữ riêng tư cho đến khi có quyết định công bố hợp lệ. Audit nói “không công bố” sẽ không có giá trị bảo vệ nếu một URL công khai đã được phát trước đó.

## 11. Bảo vệ tính toàn vẹn và quyền truy cập audit

### 11.1. Append-only cần được bảo đảm bằng nhiều lớp

Thiết kế ứng dụng có thể chỉ cho thêm sự kiện, không cho sửa hoặc xóa qua API thông thường. Tài khoản ghi của ứng dụng nên được giới hạn phù hợp và tách khỏi quyền quản trị dữ liệu audit.

Tuy nhiên, gọi một bảng là append-only không tự ngăn quản trị viên cơ sở dữ liệu sửa dữ liệu. Mức bảo đảm cao hơn có thể cần kho lưu trữ có cơ chế bảo vệ bất biến, tách miền quản trị, bản sao độc lập và khả năng phát hiện thay đổi.

Digest, chuỗi liên kết hoặc chữ ký có thể hỗ trợ phát hiện sửa nội dung nếu cơ chế tạo, khóa và điểm kiểm chứng được bảo vệ. Chúng không tự chứng minh dữ liệu đầu vào là thật, không ngăn một dịch vụ có quyền ký ghi bằng chứng giả và không tự phát hiện mọi sự kiện bị bỏ sót.

Muốn phát hiện xóa đuôi một chuỗi sự kiện, cần điểm kiểm chứng hoặc bản sao nằm ngoài phạm vi mà bên có thể sửa chuỗi kiểm soát. Không chỉ lưu cả chuỗi và mọi bằng chứng kiểm chứng trong cùng một nơi có thể bị sửa tùy ý rồi tuyên bố chống sửa tuyệt đối.

### 11.2. Nguồn gửi phải được xác minh

Kho audit không nên tin `actor_id`, `tenant_id` hoặc `decision = ALLOW` chỉ vì chúng có đúng định dạng JSON. Cần xác thực dịch vụ gửi, giới hạn loại sự kiện nó được phát và giữ được provenance của sự kiện.

Những dữ kiện đến từ request như lý do tự khai hoặc target ID cần có giới hạn độ dài và xử lý an toàn. Dùng trường dữ liệu có cấu trúc, không nối chuỗi thiếu kiểm soát thành dòng log để tránh giả mạo hình thức sự kiện hoặc chèn thêm dòng.

### 11.3. Đọc audit cũng cần quyền theo đối tượng

Audit thường chứa định danh người dùng, tài nguyên, quan hệ nhóm và thông tin sử dụng. Người hỗ trợ một tenant không tự có quyền tìm kiếm mọi tenant hoặc mọi lịch sử thanh toán và giấy phép.

Các chức năng tìm kiếm, xuất audit, xem snapshot và theo liên kết event cần kiểm tra phạm vi nhất quán. Không chỉ lọc danh sách chính rồi cho mở `event_id` bất kỳ bằng một endpoint khác.

Với quyền điều tra đặc biệt, xác định phạm vi, mục đích, thời hạn và dấu vết sử dụng thích hợp. Đặc quyền đọc audit không tự cho phép sửa grant hoặc ghi đè kết quả nghiệp vụ.

## 12. Giữ bằng chứng hữu ích mà không thu thập quá mức

Không cần lưu nội dung báo cáo, toàn bộ hồ sơ cá nhân hay bí mật xác thực để chứng minh một quyết định entitlement. Ưu tiên định danh ổn định, các thuộc tính thật sự tham gia quyết định và snapshot tối thiểu phù hợp.

Không ghi vào audit:

```text
access token hoặc refresh token nguyên vẹn
mật khẩu và khóa bí mật
toàn bộ nội dung file chỉ để chứng minh quyền xuất
dữ liệu phương tiện thanh toán không cần cho quyết định
request body không giới hạn do client tự cung cấp
```

Nếu dùng mã hóa định danh hoặc mã giả danh, cơ chế đối chiếu phải được kiểm soát để người có thẩm quyền vẫn điều tra được. Một hash đơn giản của dữ liệu dễ đoán không tự biến dữ liệu thành vô danh.

Thời gian lưu cần được xác định theo mục đích điều tra và yêu cầu thực tế của hệ thống. Policy, snapshot, mapping định danh và sự kiện cần có vòng đời tương thích; giữ event mười năm nhưng xóa bằng chứng sau một ngày sẽ làm giảm khả năng giải thích.

Không sửa sự kiện cũ để thêm một cách hiểu mới mà không để lại dấu vết. Có thể thêm sự kiện đính chính hoặc bổ sung, tham chiếu sự kiện gốc và nêu rõ ai thực hiện, vì sao và nội dung nào được làm rõ.

## 13. Chống mất sự kiện và đối soát tính đầy đủ

### 13.1. Outbox giúp bền vững, không tự tạo xử lý đúng một lần

Trong mô hình cục bộ, outbox commit cùng audit event và operation. Một tiến trình chuyển tiếp có thể gửi nhiều lần; kho nhận cần chống trùng bằng định danh sự kiện nguồn trong phạm vi nguồn phù hợp.

Nếu consumer đã ghi sự kiện rồi bị ngắt trước khi xác nhận, lần nhận lại phải tìm về sự kiện đó. Không tạo event mới chỉ để tránh lỗi unique, vì như vậy số liệu quyết định sẽ bị phóng đại.

Cần theo dõi trạng thái chưa chuyển, số lần thử, độ trễ và sự kiện không xử lý được. Một hàng outbox tồn tại chưa có nghĩa đội điều tra đã thấy nó ở kho tập trung.

### 13.2. Đối soát hai chiều

Có thể kiểm tra các quan hệ sau:

```text
Operation đã tiếp nhận
  → có decision chấp nhận tương ứng đã commit
  → có scope binding và quota reservation phù hợp nếu cần

Hiệu lực đã công bố
  → có decision hợp lệ ở checkpoint công bố
  → liên kết đúng operation và dữ liệu thực thi

Decision có outcome COMMAND_ACCEPTED
  → tìm được operation tương ứng

Audit event cục bộ
  → được chuyển đến kho nhận hoặc có trạng thái chờ, lỗi rõ ràng
```

Một sự kiện thiếu ở kho tập trung có thể là chậm vận chuyển, không phải chưa được tạo. Ngược lại, có outbox nhưng dữ liệu nguồn sai vẫn không phải audit đúng. Đối soát phải phân biệt các lớp này.

Không chỉ đối soát các sự kiện `ALLOW`. Việc mất nhiều sự kiện từ chối có thể che quá trình dò ID, thử phạm vi hoặc tấn công quota. Vì không có một operation thành công để đối chiếu, cần cơ chế theo dõi đường ghi từ chối và các tín hiệu tiếp nhận độc lập phù hợp.

### 13.3. Không để audit bị quá tải bởi đầu vào tùy ý

Kẻ lạm dụng có thể gửi nhiều yêu cầu sai để làm đầy kho audit hoặc gây tranh chấp tài nguyên. Cần giới hạn kích thước sự kiện, kiểm soát tốc độ ở điểm phù hợp, phân bổ tài nguyên và theo dõi độ trễ.

Không âm thầm lấy mẫu những sự kiện quyết định bắt buộc rồi vẫn tuyên bố đã lưu đầy đủ. Có thể lấy mẫu log chẩn đoán hoặc gộp tín hiệu lưu lượng theo một chính sách riêng, nhưng phải phân biệt với bằng chứng nghiệp vụ cần giữ cho từng quyết định.

Metric không nên dùng các giá trị tùy ý như toàn bộ `resource_id` do client gửi làm nhãn không giới hạn. Giữ thông tin chi tiết trong sự kiện có kiểm soát và dùng các chiều tổng hợp phù hợp để phát hiện xu hướng.

## 14. Kiểm thử audit bằng tình huống tấn công và lỗi

Kiểm thử cần kiểm tra cả bản ghi nguồn, vận chuyển và liên kết đến hiệu lực, thay vì chỉ tìm xem có một dòng log xuất hiện hay không.

| Tình huống | Cách tạo tình huống | Bằng chứng cần có |
| --- | --- | --- |
| Cho phép bình thường | U17 xuất R8 trong phạm vi G21 | Đúng tenant, actor, grant version, policy, operation và quota |
| Vượt phạm vi | Đổi R8 sang báo cáo P2 | `DENY` có căn cứ phù hợp; không tạo hiệu lực hoặc lộ tài nguyên ngoài quyền |
| Giả tenant | Gửi tenant B khi chỉ có quyền ở A | Không ghi tenant B như ngữ cảnh đã được xác minh |
| Giả dữ liệu quyền | Gửi `isPremium=true` hoặc grant version tự khai | Dữ kiện được quyết định từ nguồn máy chủ; đầu vào tự khai không trở thành chứng cứ tin cậy |
| Thu hồi sau tiếp nhận | D301 cho phép rồi G21 bị thu hồi trước worker | D302 mới, liên kết cùng operation và nêu dữ kiện thay đổi |
| Nguồn policy lỗi | Làm nguồn entitlement không truy cập được | Phân biệt `INDETERMINATE` với thiếu entitlement đã được xác định |
| Audit ghi lỗi | Gây lỗi ghi audit trong transaction tiếp nhận | Không commit hiệu lực yêu cầu audit bắt buộc; không báo ghi thành công |
| Từ chối có rollback | Chạy nhánh bị chặn của service | Sự kiện từ chối vẫn tồn tại theo thiết kế, không mất do ngoại lệ |
| Lỗi sau đánh giá allow | Gây lỗi trước commit operation | Không có sự kiện đã chốt tuyên bố tiếp nhận thành công |
| Gửi lại HTTP | Cùng key và nội dung sau timeout | Cùng operation; audit nói đúng là trả kết quả cũ hoặc đánh giá lại |
| Đổi nội dung giữ key | Đổi report hoặc giới hạn dòng | Có kết quả xung đột, không dùng decision cũ cho ý định mới |
| Outbox phát lại | Gửi cùng event nhiều lần | Một event nguồn trong kho nhận, không tăng số decision giả |
| Đánh giá lại thật | Dùng policy hoặc facts mới cho cùng operation | Decision ID mới, có phiên bản và quan hệ rõ ràng |
| Sự kiện sai thứ tự | Chuyển hoàn tất trước tiếp nhận | Ghép được theo quan hệ, không kết luận chỉ từ thứ tự nhận |
| Rò rỉ dữ liệu audit | Người tenant A mở event của B | Bị chặn ở cả API danh sách, chi tiết, snapshot và xuất |
| Sửa bằng chứng | Thay snapshot hoặc sự kiện trong môi trường thử | Cơ chế kiểm chứng phát hiện trong phạm vi bảo đảm đã thiết kế |
| Log injection | Gửi trường lý do có xuống dòng và nội dung giống event | Dữ liệu được giới hạn và biểu diễn có cấu trúc, không tạo sự kiện giả |
| Đọc sau khi đổi grant | Sửa G21 rồi điều tra D301 | Vẫn truy xuất được phiên bản hoặc snapshot tại lúc quyết định |
| Bằng chứng hết hạn | Mô phỏng snapshot đã bị xóa | Công cụ nêu giới hạn, không tuyên bố tái hiện đầy đủ |

### 14.1. Kiểm thử đồng thời và điểm commit

Với thao tác thu hồi cạnh tranh nhận lệnh, dùng các transaction độc lập và điểm đồng bộ. Kiểm tra cả hai thứ tự:

- Thu hồi commit trước: quyết định tiếp nhận phải dùng phiên bản phù hợp và không cho phép dựa trên nguồn cũ ngoài chính sách độ mới.
- Tiếp nhận commit trước: audit giữ đúng phiên bản đã cho phép; checkpoint sau đánh giá theo trạng thái mới nếu chính sách yêu cầu.

Đồng thời kiểm tra rằng operation, audit cục bộ, reservation và outbox cùng xuất hiện hoặc cùng không tồn tại sau commit hoặc rollback. Một test chỉ xác nhận code đã gọi `audit.append()` không chứng minh được tính bền vững này.

### 14.2. Kiểm thử phục hồi

Ngắt process ở các vị trí: sau commit nhưng trước phát outbox, sau consumer ghi nhưng trước xác nhận, và sau hiệu lực bên ngoài nhưng trước ghi nhận kết quả. Sau khi khôi phục, cần giữ được cùng định danh, không nhân bản quyết định và biểu diễn đúng phần kết quả chưa xác định.

Có thể chạy các truy vấn đối soát để phát hiện operation không có decision, decision chấp nhận không có operation hoặc hiệu lực không có checkpoint phù hợp. Các kiểm tra này bổ sung cho test từng endpoint và phát hiện được đường xử lý bỏ quên audit.

## 15. Tự đánh giá thiết kế

1. Một bản ghi `ALLOW` đang nói được phép, đã tiếp nhận hay đã hoàn tất, và các nghĩa đó có bị trộn không?
2. Có thể xác định đúng actor, beneficiary, tenant, hành động và tài nguyên mà không tin dữ liệu tự khai không?
3. Có thể tìm lại policy và dữ kiện ở đúng phiên bản đã dùng, hay chỉ còn trạng thái hiện tại?
4. Nhánh từ chối có làm rollback luôn bằng chứng không?
5. Nếu audit bắt buộc không ghi được, hệ thống có còn tạo hiệu lực được bảo vệ không?
6. Khi retry, ID nào giữ nguyên cho sự kiện cũ và ID nào đổi cho lần đánh giá mới?
7. Có chuỗi kiểm chứng từ operation đến decision, hiệu lực và kết quả đối soát không?
8. Người đọc audit có bị giới hạn tenant, dữ liệu và mục đích truy cập phù hợp không?

Entitlement decision audit có giá trị khi giữ được căn cứ của từng quyết định và liên kết nó với hiệu lực đã xảy ra. Một thiết kế đáng tin cậy cần bằng chứng có phiên bản, ngữ nghĩa kết quả rõ ràng, ranh giới commit đúng và cơ chế phục hồi không làm mất hoặc nhân bản lịch sử.
