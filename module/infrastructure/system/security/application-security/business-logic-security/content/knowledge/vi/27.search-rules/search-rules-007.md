# Dấu vết kiểm toán tìm kiếm (Search audit trail)

Một lượt tìm kiếm có thể tiết lộ nhiều dữ liệu mà không sửa bất kỳ bản ghi nghiệp vụ nào. Người dùng có thể lần lượt thay bộ lọc, duyệt nhiều trang, xem dữ liệu đã lưu trữ hoặc dùng số đếm để dò thông tin. Nếu chỉ lưu access log, hệ thống khó biết truy vấn đã bị giới hạn theo quyền ra sao và phần kết quả nào thực sự được chuẩn bị trả.

Ngược lại, ghi nguyên query và mọi kết quả vào log có thể tạo một kho dữ liệu nhạy cảm mới. Audit tìm kiếm cần vừa giải thích được quyết định truy cập, vừa giữ đúng tenant, quyền đọc log và mục đích lưu dữ kiện.

Bài học thuộc chương **Search Rules** trong bảo mật logic nghiệp vụ. Trọng tâm là thiết kế dấu vết có cấu trúc cho toàn luồng tìm kiếm, phân biệt các mốc xử lý và bảo vệ chính thông tin kiểm toán.

Ví dụ xuyên suốt là tìm đề nghị mua hàng và lịch sử phê duyệt trong hệ thống nhiều tenant.

## 1. Audit tìm kiếm cần trả lời điều gì?

Một dấu vết có ích cần giúp xác định:

1. Ai thực sự gọi, có hoạt động thay ai không?
2. Tenant, dataset và action nào được xét?
3. Caller đã đề nghị truy vấn gì và máy chủ đã hiểu nó theo hợp đồng nào?
4. Scope, visibility và tập trường thực sự được áp dụng là gì?
5. Policy hoặc căn cứ nào cho phép hay chặn?
6. Kết quả được chuẩn bị ở mức nào và từ nguồn đọc nào?
7. Response đã tới mốc xử lý nào phía server?
8. Ai đã đọc hoặc xuất dữ kiện audit và bằng chứng liên quan?

Không nhất thiết mọi câu trả lời nằm trong một dòng. Các định danh và tham chiếu phải đủ nối những dữ kiện được bảo vệ lại với nhau.

### 1.1. Phân biệt các loại dấu vết

| Loại | Mục đích |
|---|---|
| Access log | Quan sát request, route và kết quả kỹ thuật ở một tầng |
| Log vận hành | Chẩn đoán lỗi, độ trễ hoặc nguồn phụ thuộc |
| Search audit | Giải thích chủ thể, scope, quyết định quyền và các mốc tìm kiếm |
| Search history của người dùng | Tính năng xem lại một số truy vấn theo quyền và chính sách riêng |
| Result evidence | Dữ kiện được giữ để kiểm chứng kết quả đã chuẩn bị hoặc công bố |

Một log route thành công chưa chứng minh query đã có tenant predicate đúng. Một dòng ghi số hit cũng chưa chứng minh caller nhận đủ từng bản ghi đó.

Search history hiển thị trên giao diện không tự là toàn bộ audit nghiệp vụ. Ngược lại, quyền dùng tính năng tìm kiếm không tự cho phép đọc mọi query hoặc result evidence trong kho audit.

### 1.2. Audit không thay thế kiểm soát tìm kiếm

Audit có thể giúp phát hiện một truy vấn sai scope, nhưng không hợp thức hóa việc trả dữ liệu ngoài quyền.

Máy chủ vẫn phải xác thực, phân quyền dataset, giới hạn tenant, kiểm tra filter, field, visibility và cursor. Không cho phép query rộng rồi coi việc đã ghi log là đủ bảo vệ.

## 2. Phân biệt các mốc từ request tới response

Một lượt có thể đi qua:

```text
nhận request
    → diễn giải input
    → xác định scope có thẩm quyền
    → chạy query
    → kiểm tra và chiếu kết quả được phép
    → chuẩn bị response
    → bắt đầu gửi
    → hoàn tất thao tác gửi theo khả năng quan sát của server
```

Mỗi mốc chứng minh một điều khác nhau.

| Mốc | Điều đã biết | Điều chưa được chứng minh |
|---|---|---|
| Request nhận được | Có một lần gọi | Input hợp lệ hoặc caller có quyền |
| Query được cho phép | Có quyết định cho một scope cụ thể | Engine đã chạy hoặc đã có hit |
| Engine trả candidate | Có dữ liệu ứng viên | Mọi candidate được phép công bố |
| Response được chuẩn bị | Có payload hoặc kế hoạch kết quả được chấp nhận | Client đã nhận hoặc đã xem |
| Server hoàn tất thao tác gửi | Tầng đó ghi nhận đã gửi xong theo contract | Con người đã đọc nội dung |
| Có request mở chi tiết | Có một hành động truy cập tiếp | Người dùng đã hiểu hoặc sử dụng thông tin |

### 2.1. Không gọi chuẩn bị kết quả là đã đọc dữ liệu

Một connection có thể đóng sau khi chuẩn bị response nhưng trước khi gửi. Luồng có thể gửi một phần rồi bị ngắt.

Audit cần giữ trạng thái quan sát thực tế. Không ghi DELIVERED chỉ vì hàm query trả về hoặc controller tạo DTO thành công.

Nếu có client acknowledgement, đó là tín hiệu riêng cần được đánh giá theo nguồn và giới hạn của nó. Không dùng tín hiệu tự khai làm bằng chứng thẩm quyền hay kết luận tuyệt đối rằng người dùng đã xem.

### 2.2. Các loại sự kiện minh họa

```text
SEARCH_ATTEMPT_RECORDED
SEARCH_AUTHORIZED
SEARCH_REJECTED
SEARCH_RESPONSE_PREPARED
SEARCH_SERVER_TRANSFER_COMPLETED
SEARCH_RESPONSE_ABORTED
SEARCH_FAILED
SEARCH_AUDIT_READ
SEARCH_AUDIT_EXPORTED
```

Không phải hệ thống nào cũng cần đúng danh sách này. Tên sự kiện phải khớp mốc thực sự biết được và tránh gộp mọi lỗi thành một lần bị từ chối quyền.

Một lỗi sau chuẩn bị khác lỗi cấu trúc đầu vào. Một sự cố nguồn audit khác việc query không có kết quả.

## 3. Ghi đúng query được đề nghị và scope thực tế

Có ít nhất ba biểu diễn:

| Biểu diễn | Ý nghĩa |
|---|---|
| Input người dùng | Văn bản, filter, sort, view hoặc các tham số được gửi |
| Query đã diễn giải | Cấu trúc chuẩn mà ứng dụng hiểu theo phiên bản hợp đồng |
| Read plan có thẩm quyền | Query kết hợp tenant, quyền, visibility và projection thật sự được áp dụng |

Không dùng nguyên input làm bằng chứng rằng engine đã chạy đúng plan.

Ví dụ:

```text
User filter:
    state = APPROVED

Effective plan:
    tenant = tenant-A
    AND (owner = U OR assignment_to_U_is_valid)
    AND deletedAt IS NULL
    AND state = APPROVED
```

Audit cần tham chiếu hoặc biểu diễn an toàn để giải thích plan có thẩm quyền đó. Không chỉ ghi một chuỗi state=APPROVED rồi bỏ thông tin scope.

### 3.1. Những nhóm trường có thể cần

```text
schemaVersion
eventId
searchSessionId
searchRequestId
correlationId
tenantId có thẩm quyền
actualActorId
effectiveSubjectId
delegationRef nếu có
dataset và action
queryContractVersion
normalizationVersion
queryFingerprint hoặc protectedQueryEvidenceRef
authorizationContextRef
policyVersion và scope context phù hợp
effectiveView
projectionRef
sortRef và pageSize
cursorFingerprint nếu cần
readModelRef hoặc snapshotRef nếu có
outcome và safeReasonCode
preparedResultCount nếu được phép giữ
resultEvidenceRef theo policy
occurredAt và recordedAt
```

Không phải mọi field bắt buộc trong mọi event. Schema nên yêu cầu những dữ kiện tối thiểu theo từng mốc và dataset.

### 3.2. Định danh không thay thế nhau

- EventId nhận diện một sự kiện để ghi và chuyển lại không nhân bản.
- SearchRequestId nhận diện một lần xử lý request hoặc trang theo contract.
- SearchSessionId có thể nhóm các trang thuộc một lượt tìm kiếm.
- CorrelationId hỗ trợ liên kết kỹ thuật, không tự là danh tính hoặc quyền.
- Query fingerprint nhận diện biểu diễn theo quy tắc đã chọn, không tự nhận diện người thực hiện.

Một lần retry trang có thể dùng cùng criteria nhưng dữ liệu hoặc quyền đã đổi. Không mặc định cùng fingerprint nghĩa là cùng tập kết quả.

### 3.3. Actor và tenant phải từ nguồn thật

Role, tenant hoặc userId trong filter có thể là đối tượng caller muốn tìm, không phải dữ kiện xác thực của caller.

Nếu query cố chọn tenant khác, audit nên phân biệt phạm vi đã xác minh với giá trị được đề nghị. Không ghi tenant tự khai như thể caller đã có quyền ở đó.

Nếu chưa xác định được một đối tượng hoặc tenant ngoài phạm vi, không truy vấn rộng để bổ sung thông tin nhạy cảm cho log từ chối.

## 4. Giữ giá trị điều tra mà không thu gom dữ liệu quá mức

Một query có thể chứa tên, mã giao dịch, địa chỉ, số tài khoản hoặc một bí mật người dùng vô tình dán vào.

Không nên mặc định ghi nguyên văn query ở mọi tầng hoặc đưa nó vào mọi event.

### 4.1. Chọn mức dữ kiện theo mục đích

| Mức | Dữ kiện | Giới hạn |
|---|---|---|
| Tóm tắt an toàn | Dataset, loại filter, kết quả quyền, số lượng phù hợp | Không tái dựng được đầy đủ query |
| Fingerprint có ngữ cảnh | Nhận diện theo quy tắc chuẩn hóa đã chọn | Không giải thích toàn bộ nội dung; vẫn có thể là dữ liệu nhạy cảm |
| Tham chiếu query được bảo vệ | Truy vấn được lưu riêng theo quyền, mục đích và vòng đời | Cần quản lý truy cập, lưu giữ và khả năng diễn giải |
| Bằng chứng kết quả | ID, revision, projection hoặc snapshot theo yêu cầu | Tăng lượng dữ liệu phải bảo vệ; không luôn cần |

Mức nào phù hợp phụ thuộc dataset và nhu cầu kiểm chứng. Không tự lưu tất cả rồi dự định giải quyết quyền đọc sau.

### 4.2. Hash không tự làm query vô danh

Query ngắn hoặc có ít khả năng có thể bị đoán bằng cách thử các giá trị rồi so hash. Hai hệ thống cũng có thể liên kết cùng một chuỗi nếu dùng cùng cách tính không có ngữ cảnh.

Có thể cần một cơ chế fingerprint có khóa và ngữ cảnh theo thiết kế đã được chấp nhận, chẳng hạn dựa trên MAC, cùng quản lý khóa phù hợp. Không tự nối chuỗi tùy ý hoặc xem fingerprint như một credential.

Dù được bảo vệ tốt hơn, fingerprint vẫn có thể phục vụ liên kết hành vi. Quyền đọc và chính sách lưu giữ vẫn cần thiết.

### 4.3. Chuẩn hóa phải giữ ý nghĩa

Fingerprint nên dựa trên query được diễn giải theo một normalizationVersion, cùng những thành phần ngữ cảnh cần thiết.

Không bỏ tenant, dataset, view hoặc filter có ảnh hưởng rồi gộp các truy vấn khác nghĩa. Cũng không tự đổi null thành vắng mặt hoặc bỏ thứ tự khi thứ tự có ý nghĩa.

Nếu lưu cả input fingerprint và effective-plan fingerprint, cần đặt tên và mục đích rõ. Hai giá trị không trả lời cùng một câu hỏi.

### 4.4. Kiểm soát các nguồn log khác

Query có thể xuất hiện ở gateway, URL log, trace, exception, log query chậm, analytics hoặc bản xuất.

Bảo vệ một bảng search audit không xóa dữ liệu đã bị ghi rộng ở nguồn khác. Chuyển tham số từ một vị trí request sang vị trí khác cũng không tự bảo vệ mọi tầng.

Cần hiểu luồng dữ liệu và chỉ giữ các giá trị theo mục đích, phạm vi cùng cơ chế truy cập đã xác định.

## 5. Đặt audit trong pipeline tìm kiếm

Một pipeline cần giữ cùng actor, target, scope và kết quả qua các bước:

```text
input theo giới hạn
    → query hợp lệ
    → read plan có quyền
    → candidate từ nguồn
    → page được kiểm tra và chiếu field
    → quyết định công bố theo policy
    → audit phù hợp với page đã chuẩn bị
    → adapter gửi response
```

Không dùng một event ghi đầu vào làm bằng chứng rằng mọi bước sau đã áp dụng đúng.

### 5.1. Ví dụ Java

Đây là mã giả theo cú pháp Java, dùng các cổng trừu tượng. Adapter đã áp dụng giới hạn đọc input; các lỗi parse trước khi vào hàm cần đường ghi nhận an toàn riêng nếu chính sách yêu cầu.

```java
PreparedSearchResponse searchPurchaseRequests(
        SearchInput input,
        VerifiedRequest verifiedRequest) {

    ActorContext actor =
            actorContexts.fromVerifiedRequest(verifiedRequest);

    SearchAuditPlan auditPlan = auditPolicy.forAction(
            actor, Action.SEARCH_PURCHASE_REQUESTS);

    SearchAttempt attempt = searchAudit.openAttempt(
            auditPlan, actor, safeDescriptors.from(input));

    ValidatedSearchQuery query =
            searchInputs.validateAndNormalize(input);

    SearchReadPlan readPlan = searchAuthorization.requirePlan(
            actor, Action.SEARCH_PURCHASE_REQUESTS, query);

    searchAudit.recordAuthorized(
            auditPlan, attempt, readPlan.auditContext());

    CandidatePage candidates = searchSource.execute(readPlan);

    AuthorizedPage page = resultPolicy.materialize(
            actor, readPlan, candidates);

    ReleaseDecision release = responsePolicy.requireMayRelease(
            actor, readPlan, page);

    PreparedSearchEvidence evidence = evidenceFactory.capture(
            auditPlan, attempt, readPlan, release, page);

    searchAudit.recordPreparedBeforeRelease(
            auditPlan, evidence);

    return PreparedSearchResponse.of(
            page, attempt.publicCorrelationId());
}
```

Hợp đồng cần có:

- VerifiedRequest được tạo từ xác thực có thẩm quyền, không deserialize từ body.
- AuditPolicy do server chọn theo action, dataset và chính sách. Caller không tự tắt bằng skipAudit.
- SafeDescriptors không chép nguyên query, credential hoặc payload lạ vào event đầu.
- ReadPlan giữ tenant, scope, filter, view, projection và nguồn đọc thực sự được phép.
- CandidatePage không được trả thẳng cho caller hoặc đưa nguyên vào log khi có lỗi.
- ResultPolicy xác nhận hàng, snippet, metadata và field phù hợp trước khi tạo page được phép.
- ReleaseDecision gắn với page và ngữ cảnh đang xét; nó không phải một grant chung cho trang hoặc request khác.
- EvidenceFactory ghi đúng căn cứ và mức bằng chứng được policy cho phép, không mặc định lưu tất cả dữ liệu.
- RecordPreparedBeforeRelease phải bảo đảm mức ghi theo AuditPlan. Nếu audit bắt buộc không ghi được, không đi tiếp tới trả kết quả.
- Hàm trả đối tượng đã chuẩn bị, chưa chứng minh tầng mạng đã gửi xong. Các event truyền response do adapter ghi theo khả năng quan sát thực tế.

Nếu scope hoặc quyền có thể đổi giữa các bước, cần quy định mốc quyết định và cơ chế nhất quán. Một lần gọi requireMayRelease không tự tạo bảo đảm thu hồi tức thì ở mọi nguồn và mọi byte tương lai.

Nếu read plan ban đầu và quyết định công bố dùng các context khác nhau theo policy, audit cần giữ hoặc tham chiếu đúng sự khác biệt. Không ghi context cũ như thể đó là scope cuối đã áp dụng.

### 5.2. Đường lỗi phải giữ đúng giai đoạn

Middleware hoặc coordinator có thể ghi stage cùng loại lỗi an toàn:

```text
PARSE
VALIDATION
AUTHORIZATION
SOURCE_QUERY
RESULT_FILTERING
AUDIT_PREPARATION
RESPONSE_TRANSFER
```

Không bắt mọi exception rồi gắn nhãn SEARCH_REJECTED. Lỗi engine hoặc lỗi gửi response không đồng nghĩa caller thiếu quyền.

Lỗi ghi event thứ cấp cũng không được làm code trả raw candidate như phương án dự phòng. Giữ nguyên nguyên nhân phù hợp để client và vận hành biết đây là một kết quả không được công bố hoặc chưa rõ.

### 5.3. Kết quả rỗng là một kết quả có ngữ nghĩa

Một search hợp lệ có thể không có item được phép khớp. Điều đó khác nguồn lỗi, query bị chặn hoặc chưa xác minh được visibility.

Audit cần phân biệt các tình huống này mà không trả số candidate ngoài scope cho client.

Một event nói query được thực hiện thành công với 0 kết quả không nên được dùng khi thực tế engine timeout hoặc policy source không sẵn sàng.

## 6. Bằng chứng nào đủ để tái dựng kết quả?

### 6.1. Query và count không đủ chứng minh từng bản ghi

Cùng query chạy lại hôm sau có thể cho kết quả khác vì:

- Dữ liệu được sửa, xóa hoặc khôi phục.
- Owner, membership hoặc chia sẻ thay đổi.
- Policy, mapping hoặc cách chuẩn hóa thay đổi.
- Nguồn tìm kiếm cập nhật chậm hoặc đã có dữ liệu mới.
- Thứ tự, ranking hoặc snapshot khác.
- Các trang được đọc ở những mốc khác nhau.

Vì vậy, việc chạy lại chỉ là một phép kiểm tra theo dữ liệu hiện tại, không tự là bằng chứng response quá khứ.

### 6.2. Các mức result evidence

| Mức | Có thể giúp xác định | Không tự chứng minh |
|---|---|---|
| Count cùng context | Quy mô page được chuẩn bị và phạm vi quyết định | Những ID hoặc giá trị cụ thể đã có |
| RecordRef, revision và projectionRef | Những đối tượng, phiên bản và trường dự kiến trả | Payload đầy đủ nếu nguồn phiên bản đã mất |
| Snapshot kết quả được bảo vệ | Nội dung theo định dạng và phạm vi đã ghi | Người dùng thật sự đã nhìn hoặc hiểu nội dung |
| Dấu digest hoặc kiểm chứng | So sánh với dữ liệu tương ứng khi còn có nó và nguồn tin cậy | Khôi phục payload đã mất hoặc tự chứng minh quyền nghiệp vụ |

Chỉ giữ mức cần thiết theo mục đích. Result evidence có thể chứa nhiều dữ liệu hơn bản ghi audit thông thường và cần quyền riêng.

### 6.3. Bằng chứng phải khớp payload nào?

Nếu tính digest, cần xác định nó bao phủ biểu diễn nào: tập dữ kiện logic, response đã serialize hay một dạng chuẩn đã định nghĩa.

Không ghi digest của candidate rồi gọi đó là bằng chứng của page đã lọc và che field. Cũng không dùng một biểu diễn khác mà không giữ cách diễn giải cần thiết.

Nếu dùng snapshot, cần ràng buộc với searchRequestId, tenant, actor context, projection và mốc quyết định. Một snapshot không có căn cứ truy cập có thể chỉ lưu lại dữ liệu đã bị trả sai.

### 6.4. Tham chiếu có ích khi nguồn còn đủ diễn giải

Giữ policyVersion nhưng xóa mọi khả năng hiểu policy đó có thể làm điều tra thiếu căn cứ. Tương tự, record revision không hữu ích nếu không còn dữ kiện cần thiết theo nhu cầu đã chọn.

Cần phối hợp vòng đời audit, query evidence, result evidence và các nguồn được tham chiếu. Nếu có phần không còn giữ, công cụ phải phản ánh giới hạn thay vì tự suy ra response đầy đủ.

Không kéo dài lưu dữ liệu vô hạn chỉ để một báo cáo có vẻ tái dựng được mọi thứ.

## 7. Độ bền audit và giới hạn nguyên tử

Search engine, kho audit và đường gửi response thường không nằm trong cùng một transaction.

Cần nói rõ bảo đảm nào có thể thực hiện:

```text
Có dấu vết bền vững về page đã chuẩn bị trước khi cho phép trả

khác với

Có một transaction nguyên tử chứng minh client đã nhận và đọc page
```

Bảo đảm thứ nhất có thể được thiết kế bằng cổng audit trước công bố. Nó không tự tạo bảo đảm thứ hai.

### 7.1. Tách audit bắt buộc với telemetry bổ sung

Một dataset có thể yêu cầu ghi dấu vết bền vững trước khi cấp kết quả. Khi đó lỗi đường ghi bắt buộc phải ngăn bước công bố theo contract.

Telemetry chẩn đoán có thể có policy khác. Nếu cho phép mất một phần, cần công bố và quan sát đúng mức bao phủ, không mô tả nó như audit đầy đủ.

Không để một tham số debug, một cache hit hoặc một adapter cũ tự bỏ cổng audit bắt buộc.

### 7.2. Ghi local rồi chuyển tới kho tập trung

Có thể ghi event local cùng outbox trong một transaction phù hợp, rồi relay chuyển tới kho tập trung.

Khi relay retry, eventId phải ổn định để bên nhận không đếm một event thành nhiều lượt search.

Nếu kho tập trung chưa có event, có thể do độ trễ chuyển. Cần đối soát với nguồn local thay vì kết luận ngay rằng search không có dấu vết.

Nếu chính sách yêu cầu xác nhận từ chính kho tập trung trước công bố, đó là một hợp đồng mạnh hơn cần cơ chế và khả năng vận hành tương ứng.

### 7.3. Ghi prepared thành công nhưng gửi response thất bại

Tình huống:

```text
ghi SEARCH_RESPONSE_PREPARED bền vững
    → connection đóng trước khi gửi xong
```

Audit vẫn đúng rằng page đã được chuẩn bị. Không được nâng event đó thành bằng chứng client nhận đủ.

Adapter có thể ghi aborted, completed-at-server hoặc unknown theo điều thực sự biết. Mất event cuối không tự chứng minh không có byte nào được gửi.

Nếu lỗi ghi nhận phát sinh sau khi dữ liệu đã ra ngoài, không thể làm như dữ liệu chưa từng được cấp chỉ bằng cách rollback một bảng audit.

### 7.4. Streaming cần mức bằng chứng phù hợp

Với page có giới hạn, có thể chuẩn bị trước rồi qua cổng audit. Với luồng lớn, cần định nghĩa audit của toàn intent, từng chunk hoặc mức quan sát được chọn.

Nếu yêu cầu bằng chứng trước từng chunk, đường gửi phải thực thi đúng cổng đó. Nếu chỉ ghi phạm vi query trước luồng, không được tuyên bố đã giữ danh sách chính xác mọi dòng đã gửi.

Một luồng ngắt giữa chừng cần kết quả một phần hoặc chưa rõ phù hợp, không ghi toàn bộ manifest như đã được người dùng nhận hết.

## 8. Phân quyền đọc audit và bằng chứng

Kho audit có thể chứa những dữ kiện mà kết quả tìm kiếm thông thường đã che: query nhạy cảm, danh tính người tìm, scope nội bộ hoặc tham chiếu kết quả.

Cần phân quyền như một dataset riêng, theo tenant, chủ thể, mục đích và mức dữ kiện.

| Khả năng minh họa | Phạm vi cần xác định |
|---|---|
| READ_OWN_SEARCH_HISTORY | Những dữ kiện lịch sử cá nhân được phép hiển thị |
| READ_TENANT_SEARCH_AUDIT | Event trong tenant và nhóm trường được cấp |
| READ_QUERY_EVIDENCE | Nội dung query được bảo vệ |
| READ_RESULT_EVIDENCE | RecordRef, revision hoặc snapshot kết quả |
| EXPORT_SEARCH_AUDIT | Phạm vi được xuất cùng người nhận hoặc kênh phân phối |
| MANAGE_AUDIT_STORAGE | Thao tác vận hành theo chính sách riêng |

Không suy từ tên role quản trị rằng mọi quyền này tự được gộp.

### 8.1. Quyền tìm kiếm và quyền kiểm toán khác nhau

Một người có thể tìm dữ liệu nghiệp vụ nhưng không được xem query của đồng nghiệp. Một người kiểm tra event có thể chỉ được xem metadata đã che, không có quyền mở snapshot kết quả.

Tương tự, đọc một event cũ không tự cấp quyền đọc các record hiện tại được tham chiếu trong event đó.

Nếu cần quyền lịch sử hoặc quyền điều tra riêng, hãy mô hình hóa rõ, giữ scope và audit hành động tương ứng.

### 8.2. Tenant của event phải giữ ở mọi đường đọc

Các truy vấn danh sách audit, count, filter, tải bằng chứng và export đều cần cùng ranh giới phù hợp.

Không lọc tenant ở event chính rồi lấy queryEvidenceRef bằng một API toàn cục không kiểm tra quan hệ. Đối tượng bằng chứng thật được mở phải khớp event cùng scope được cấp.

Một luồng điều tra xuyên tenant có thể tồn tại, nhưng phải có thẩm quyền riêng. Một tham số includeAllTenants không tự tạo quyền đó.

### 8.3. Lịch sử cá nhân cũng cần vòng đời rõ

Một người rời tenant hoặc mất quyền có thể còn thấy phần lịch sử nào phụ thuộc policy. Không mặc định quyền tìm trước đây kéo dài mãi.

Nếu cho xem một biên nhận hoặc metadata hạn chế, không dùng nó làm đường tải payload hoặc kết quả đầy đủ ngoài quyền.

Các query do chính người dùng nhập cũng có thể chứa dữ liệu nhạy cảm vô tình. Tính năng “lịch sử của tôi” không làm mất yêu cầu bảo vệ khi lưu, hiển thị hoặc xuất.

## 9. Audit cho phân trang, metadata, cache và index

### 9.1. Mỗi trang cần context thực tế

SearchSessionId có thể nhóm các trang, nhưng không phải một grant cho toàn bộ các request về sau.

Nếu quyền, ownership hoặc visibility đổi giữa các trang, trang sau phải tuân thủ contract hiện tại hoặc mô hình snapshot được cấp rõ. Audit cần thể hiện context đã dùng cho từng page.

Cursor là dữ liệu điều hướng có ràng buộc, không là bằng chứng caller được xem mọi item từng khớp. Nếu cursor bị sửa hoặc không khớp dataset, ghi lý do an toàn thay vì lấy dữ liệu rộng để giải thích.

Không cần ghi nguyên cursor nếu nó có dữ kiện nhạy cảm. Một tham chiếu hoặc fingerprint phù hợp có thể đủ cho mục đích đã xác định.

### 9.2. Candidate count khác số kết quả được phép chuẩn bị

Một nguồn có thể trả candidate rồi ứng dụng lọc tiếp theo quyền. Count trước lọc không phải count mà caller được phép biết.

Nếu cần quan sát số candidate bị loại để điều tra lỗi scope, dữ kiện đó phải có quyền truy cập và mục đích riêng. Không tự đưa vào audit mà mọi quản trị tenant có thể xem.

Facets, suggestions, autocomplete, snippet và truy vấn chỉ lấy count cũng là các đường có thể tiết lộ dữ liệu. Audit policy cần bao phủ những action liên quan theo nhu cầu, không chỉ endpoint trả danh sách chính.

Không biến event audit thành một cách trả tổng số dữ liệu riêng tư mà search response đã cố che.

### 9.3. Cache hit vẫn là một lần có thể công bố dữ liệu

Nếu chỉ audit khi engine chạy, các response từ cache có thể mất dấu vết truy cập.

Cổng kiểm tra quyền và audit bắt buộc phải áp dụng cho đường cache theo contract. Event cần chỉ ra nguồn kết quả thực sự khi điều đó ảnh hưởng khả năng giải thích.

Cache cũ không được dùng để vượt chính sách thu hồi, soft delete hoặc scope hiện tại. Ghi audit về việc trả dữ liệu sai không sửa được lỗi truy cập.

Nếu snapshot hoặc read model có độ trễ, ghi tham chiếu đúng giúp điều tra; nó không tự hợp thức hóa việc trả dữ liệu ngoài quyền.

### 9.4. Chạy lại từ lịch sử là request mới

Một nút “chạy lại query” cần diễn giải hợp đồng, xác thực và phân quyền theo mô hình hiện tại.

Có thể liên kết với searchRequestId trước để giải thích nguồn thao tác. Không dùng quyết định ALLOW cũ như một quyền vô thời hạn.

Nếu cú pháp hoặc query contract cũ không còn được hiểu đầy đủ, cần chuyển đổi có chủ đích hoặc từ chối phù hợp. Không bỏ filter không biết rồi chạy một query rộng hơn.

### 9.5. Bằng chứng sai lệch scope cần được bảo vệ

Nếu phát hiện candidate sai tenant hoặc ngoài scope, có thể ghi một sự kiện bảo mật với tham chiếu an toàn để điều tra.

Không trả raw row đó trong lỗi, cũng không sao chép nó vào một log tenant thông thường như thể đó là dữ liệu caller được phép đọc.

Đường xử lý kết quả không được có fallback trả candidate vì bước kiểm tra hoặc mapper thất bại.

## 10. Phát hiện lạm dụng mà không suy luận quá mức

Các tín hiệu có thể cần xem xét:

- Nhiều lần đổi tenant selector hoặc cố dùng view ngoài quyền.
- Thay dần ID, tên hoặc bộ lọc nhạy cảm để dò dữ liệu.
- Liên tục yêu cầu scope rộng, nhiều field hoặc nhiều trang.
- Tìm count của những tập rất hẹp để kiểm tra sự tồn tại.
- Thử cursor khác scope hoặc dùng lại sau thu hồi.
- Tải hoặc xuất nhiều query evidence và result evidence.
- Nhiều lần lỗi cấu trúc quanh các trường quyền hoặc filter bị bảo vệ.

Một tín hiệu không tự chứng minh cố ý lạm dụng. Người điều tra, công việc theo đợt, lỗi client và retry kỹ thuật có thể tạo hình thái tương tự.

### 10.1. Đếm đúng đơn vị

```text
một intent tìm kiếm trên giao diện
    có thể tạo nhiều request trang

một request
    có thể tạo nhiều event theo giai đoạn

một event
    có thể được relay nhiều lần
```

Không đếm mọi event thành một lượt tìm kiếm mới.

Nhưng cũng không khử mọi request có cùng queryFingerprint thành một event duy nhất. Hai request khác thời điểm có thể là hai lần truy cập thật với quyền và kết quả khác nhau.

Dedupe việc chuyển event nên dựa trên eventId ổn định. Phân tích lượt search, page, retry và intent cần định nghĩa riêng.

### 10.2. Alert cần căn cứ và phạm vi

Có thể dùng query shape, tần suất, scope bị từ chối và chuỗi hành động theo policy. Ngưỡng cần phù hợp lưu lượng hợp lệ và dataset.

Không cần đưa toàn bộ query hoặc payload kết quả vào mọi cảnh báo. Người nhận cảnh báo cũng cần quyền xem mức dữ kiện đó.

Audit là bằng chứng hỗ trợ kiểm tra. Không tự biến một nhãn role do caller gửi hoặc một query có từ nhạy cảm thành căn cứ cấp quyền hay kết luận chắc chắn.

### 10.3. Không sampling rồi gọi là bao phủ đầy đủ

Telemetry hiệu năng có thể có sampling theo thiết kế. Audit bắt buộc cho một loại truy cập cần mức bao phủ mà policy yêu cầu.

Nếu hệ thống gộp các lượt gõ tìm kiếm hoặc giảm dữ kiện để bảo vệ riêng tư và tài nguyên, phải giữ đúng mục đích cùng giới hạn đã chọn. Không mô tả một bản tóm tắt như danh sách chính xác mọi query và kết quả.

Khi có khoảng trống do sự cố, cần nhận diện và xử lý theo khả năng thực tế, không tự tạo lại các event “thành công” từ suy đoán.

## 11. Bảo vệ vòng đời và tính toàn vẹn của audit

### 11.1. Lưu nối tiếp và sửa sai có dấu vết

Các event đã dùng để giải thích hành động không nên bị cập nhật tùy ý qua endpoint nghiệp vụ.

Nếu cần sửa phân loại hoặc bổ sung kết quả, có thể ghi event liên kết với bản trước theo mô hình. Một projection trạng thái mới nhất có thể được cập nhật, nhưng cần phân biệt với nguồn lịch sử.

Quyền ghi thêm không mặc nhiên là quyền xóa hoặc sửa mọi event. Các thao tác vận hành, phục hồi và thay đổi cấu hình liên quan cần thẩm quyền cùng dấu vết phù hợp.

Một bảng không có nút sửa vẫn có thể bị thay bằng quyền hạ tầng. Cần bảo đảm thực tế tương ứng mô hình đe dọa, không chỉ đặt tên append-only.

### 11.2. Lưu giữ theo mục đích và khả năng diễn giải

Audit event, query evidence, result evidence và dữ kiện policy có thể có vòng đời khác nhau. Cần phối hợp để biết dữ kiện nào còn đủ tái dựng và dữ kiện nào đã hết hiệu lực lưu giữ.

Nếu xóa hoặc che một phần theo policy, công cụ đọc lịch sử cần thể hiện đúng giới hạn. Không lấy giá trị hiện tại để giả làm giá trị quá khứ đã mất.

Tính năng xóa search history trên giao diện và xử lý dữ kiện audit cần hợp đồng rõ. Không hứa xóa mọi bản sao nếu hệ thống vẫn giữ chúng; cũng không dùng nhãn audit để tự suy ra cần giữ vô hạn.

### 11.3. Thời gian và thứ tự

OccurredAt và recordedAt có thể khác nếu relay chậm hoặc ghi nhận qua nhiều tầng.

Cần các định danh, stage và thứ tự theo request đủ để hiểu quan hệ. Không chỉ so timestamp rồi kết luận một page đã được gửi trước khi được cho phép nếu các đồng hồ hoặc nguồn mốc không tương đương.

Thời gian client cung cấp có thể là tín hiệu bổ sung theo contract, không tự là mốc thẩm quyền của sự kiện server.

### 11.4. Giới hạn để audit không thành đường tiêu tốn tài nguyên

Cần giới hạn kích thước query, số lỗi, metadata, bằng chứng và số event theo contract.

Một payload sai không được làm log tăng không kiểm soát hoặc ghi hàng loạt giá trị bí mật. Quota và cơ chế bảo vệ cần dựa trên ngữ cảnh đã xác minh khi phù hợp, không theo tenant tự khai.

Khi đường audit bắt buộc thiếu dung lượng hoặc không ghi được, cách xử lý phải giữ đúng policy công bố dữ liệu. Không âm thầm bỏ audit rồi vẫn ghi nhãn bao phủ đầy đủ.

Audit việc đọc audit cũng cần thiết kế tránh vòng gọi đệ quy không kiểm soát. Tách các đường ghi và đọc cùng trách nhiệm rõ ràng, thay vì mỗi thao tác tự kích hoạt vô hạn một thao tác tương tự.

## 12. Kiểm thử search audit theo mốc và quyền

### 12.1. Ma trận tình huống

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Search hợp lệ trong tenant A | Actor, tenant, read plan và projection phản ánh nguồn thật |
| Caller tự khai tenant hoặc role khác | Audit không ghi lời khai thành thẩm quyền thực tế |
| Query bị chặn trước nguồn dữ liệu | Không có response prepared hoặc hit ngoài quyền |
| Query có dữ liệu nhạy cảm rồi sai cấu trúc | Lỗi và safe descriptor không lặp nguyên payload |
| Query hợp lệ không có kết quả | Phân biệt được với denied, timeout và nguồn lỗi |
| Engine trả candidate ngoài scope | Không công bố hoặc lưu chúng vào bằng chứng tenant thông thường |
| Field nhạy cảm bị che trong response | Evidence không mặc định giữ bản raw như thể đó là payload đã trả |
| Cache hit | Giữ kiểm tra quyền và audit bắt buộc tương ứng |
| Quyền đổi giữa các trang | Event trang sau dùng context thực tế, không kế thừa một grant vô hạn |
| Cursor sai scope | Từ chối an toàn, không tra cứu rộng để bổ sung dữ kiện log |
| Audit bắt buộc không ghi được | Không công bố kết quả theo contract |
| Telemetry tùy chọn mất một phần | Không mô tả như audit đầy đủ đã ghi |
| Prepared xong nhưng connection đóng | Không tự ghi rằng client đã nhận đủ |
| Stream ngắt giữa chừng | Không gọi toàn bộ tập dự kiến là đã truyền hoàn tất |
| Relay giao lại event | Dedupe eventId, không nhân số lượt search |
| Request mới có cùng queryFingerprint | Không xóa dấu vết truy cập thật bằng dedup sai cấp |
| Chạy lại query sau khi dữ liệu đổi | Không dùng kết quả mới làm bằng chứng response cũ |
| Có quyền search nhưng không có quyền xem audit | Không mở query hoặc bằng chứng của người khác |
| Có quyền xem event nhưng không có quyền đọc result evidence | Tham chiếu không trở thành đường tải ngoài quyền |
| Xuất audit | Giữ scope, field và kênh phân phối được phép |
| Query xuất hiện ở gateway hoặc trace | Cơ chế bảo vệ bao phủ đúng nguồn ghi liên quan |
| Client tự báo đã đọc | Được phân loại theo nguồn, không tự thành bằng chứng quyền hoặc nhận đủ dữ liệu |

### 12.2. Chèn lỗi ở ranh giới quan trọng

Nên thử:

1. Attempt đã được ghi nhưng validation hoặc authorization thất bại.
2. Quyền đã được chấp nhận nhưng engine lỗi.
3. Page đã được tạo trong bộ nhớ nhưng journal bắt buộc chưa ghi được.
4. Ghi prepared thành công nhưng truyền response không hoàn tất.
5. Server đã ghi nhận gửi xong nhưng event cuối không chuyển được tới kho tập trung.
6. Kho tập trung đã nhận event, relay mất acknowledgement rồi gửi lại.
7. Query evidence hoặc snapshot được tham chiếu đã hết vòng đời.
8. Dữ kiện quyền thay đổi giữa read plan và mốc công bố theo contract.

Kiểm tra cả dữ liệu đã được phép ra ngoài, event nguồn, bản sao và trạng thái chưa rõ. Không chỉ assert có một dòng log chứa từ search.

Nếu chưa xác nhận một thao tác ghi bắt buộc đã bền vững, không tự coi nó thành công để trả dữ liệu. Đối soát hoặc dừng theo contract.

Ngược lại, sau khi dữ liệu đã được cấp, lỗi audit ở bước cuối không làm các byte đó tự biến mất. Dấu vết cần phản ánh giới hạn biết được.

### 12.3. Kiểm tra query và kết quả bằng fixture phân biệt tenant

Tạo dữ liệu tổng hợp riêng cho A và B, có dấu hiệu khác nhau trong field được phép và field bị che.

Thực hiện search với các scope khác nhau, rồi kiểm tra:

```text
response không có dữ liệu ngoài quyền
event ghi tenant và actor đúng
plan reference chỉ đúng scope đã áp dụng
count có ngữ nghĩa rõ, không lấy tổng ngoài quyền
query evidence theo đúng mức bảo vệ
result evidence khớp page đã chuẩn bị, không phải raw candidate
người đọc audit không mở được bằng chứng ngoài scope
lỗi và log không chứa dấu hiệu nhạy cảm của tenant khác
```

Dùng fixture tổng hợp, không cần bí mật thật để kiểm tra chống ghi log.

### 12.4. Kiểm thử khả năng giải thích lịch sử

Cho một query trả kết quả ở thời điểm đầu, sau đó thay owner, xóa item hoặc đổi policy rồi chạy lại.

Công cụ lịch sử phải phân biệt event cũ với request mới. Nếu chỉ lưu query và count, nó không được hiển thị như chắc chắn biết mọi giá trị response trước đó.

Nếu có record revision hoặc snapshot, kiểm tra nguồn đó còn tồn tại và người mở có quyền tương ứng. Nếu thiếu, hiển thị giới hạn dữ kiện.

Một history view không được dùng quyền search quá khứ để cấp quyền đọc hiện tại hoặc chạy lại query rộng hơn.

### 12.5. Kiểm tra chất lượng dữ kiện audit

Các bất biến có thể gồm:

- EventId ổn định khi relay cùng sự kiện.
- SearchRequestId và stage không bị nhầm với một intent người dùng.
- Query fingerprint không làm mất những khác biệt ngữ nghĩa cần thiết.
- Evidence tham chiếu đúng payload và projection được chuẩn bị.
- Không có event khẳng định một mốc mà source chưa quan sát.
- Actor thực không bị ghi đè bằng input.
- Lỗi hoặc sampling không được che thành bao phủ đầy đủ.
- Thao tác đọc audit không tạo vòng ghi vô hạn.
- Luồng search không sửa state nghiệp vụ để vượt qua lỗi query hoặc audit.

Các kiểm thử cần đi qua adapter và đường ghi thực tế khi bảo đảm phụ thuộc chúng. Mock một logger nhận message chưa chứng minh độ bền, quyền đọc hay tính đúng của mốc truyền response.

## 13. Bài tập áp dụng

Thiết kế audit cho search đề nghị mua hàng có phân trang, cache và một nguồn tìm kiếm cập nhật bất đồng bộ.

1. Xác định câu hỏi điều tra cần trả lời và mức dữ kiện tối thiểu.
2. Tách input query, query đã diễn giải và effective read plan.
3. Thiết kế event cho attempt, authorization, prepared response và mốc truyền biết được.
4. Chọn cách giữ query nhạy cảm, fingerprint và normalizationVersion.
5. Xác định khi nào cần record reference, revision hoặc snapshot kết quả.
6. Vẽ cổng audit bắt buộc trước công bố và cách xử lý lỗi tại từng giai đoạn.
7. Phân quyền riêng cho search history, event, query evidence, result evidence và export.
8. Mô tả pagination, cache hit, quyền đổi và replay từ lịch sử.
9. Viết ca kiểm thử response bị ngắt, relay trùng và query chứa dữ liệu nhạy cảm.
10. Chỉ ra những điều audit không thể chứng minh khi không có bằng chứng tương ứng.

Một search audit trail đáng tin cần diễn giải đúng phạm vi đã được cho phép, dữ kiện đã chuẩn bị và mốc xử lý thực sự quan sát được. Bằng chứng phải đủ cho mục đích kiểm tra nhưng vẫn được phân quyền, bảo vệ và giữ theo vòng đời phù hợp, để việc ghi nhận truy cập không trở thành một đường rò rỉ dữ liệu mới.
