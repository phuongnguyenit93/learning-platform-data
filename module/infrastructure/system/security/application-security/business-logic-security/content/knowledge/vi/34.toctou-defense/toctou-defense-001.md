# Check time definition — xác định thời điểm kiểm tra trong TOCTOU

Một bước kiểm tra trả về “được phép” chỉ chứng minh điều kiện đã đạt trên những dữ liệu mà bước đó sử dụng. Nó chưa chứng minh điều kiện còn đúng khi ứng dụng thay đổi dữ liệu hoặc tạo tác dụng bên ngoài. Muốn bảo vệ quy tắc nghiệp vụ trước TOCTOU, trước hết phải nói rõ: kiểm tra cái gì, dựa trên phiên bản nào, tại mốc nào và kết quả được dùng cho hành động nào.

Trong chương **TOCTOU Defense**, bài học này tập trung vào khái niệm **check time**, tức thời điểm kiểm tra. Mục tiêu không chỉ là gắn timestamp vào một lần gọi hàm, mà là xác định căn cứ và phạm vi hiệu lực của quyết định trước khi một hành động nghiệp vụ được thực hiện.

Sau bài học, bạn có thể:

- Phân biệt thời điểm đọc dữ liệu, đánh giá điều kiện, quyết định ghi, commit và tạo tác dụng.
- Nhận diện khi kết quả kiểm tra đã cũ dù request mới đến hoặc hàm kiểm tra vừa chạy xong.
- Viết hợp đồng thời điểm cho quyền theo đối tượng, trạng thái, thời hạn và phê duyệt nội dung.
- Xác định điều gì phải được bảo vệ giữa kiểm tra và sử dụng kết quả.
- Thiết kế kiểm thử điều khiển thứ tự để chứng minh hợp đồng đó được duy trì.

## 1. Từ một lần kiểm tra đúng đến một hành động sai

Giả sử Mai được phép phê duyệt đề nghị mua hàng của bộ phận A. Hệ thống yêu cầu quyền này phải còn hiệu lực khi đề nghị được chấp nhận phê duyệt.

```text
09:00  Mai mở đề nghị PR-101 và thấy nút Phê duyệt.
09:02  Quản trị viên thu hồi quyền phê duyệt của Mai.
09:03  Một job thực hiện phê duyệt bằng kết quả đã kiểm tra lúc 09:00.
```

Bước kiểm tra lúc 09:00 có thể hoàn toàn đúng. Sai lầm là dùng kết quả đó như quyền thực hiện lúc 09:03 mà không có hợp đồng bảo lưu hoặc cơ chế bảo vệ phù hợp.

Khoảng đua không cần dài đến vài phút:

```text
T1: Request A đọc quyền và kết luận Mai được phép.
T2: Request B thu hồi quyền, rồi commit.
T3: Request A ghi trạng thái APPROVED, rồi commit.
```

Nếu sản phẩm yêu cầu quyền hiện hành tại quyết định ghi, chỉ kiểm tra ở T1 rồi ghi không điều kiện ở T3 là thiếu bảo vệ. Khoảng cách chỉ vài mili giây vẫn có thể bị khai thác bằng request song song.

TOCTOU là viết tắt của **time of check to time of use**: khoảng cách giữa lúc kiểm tra một điều kiện và lúc sử dụng kết quả kiểm tra đó. Trong bảo mật logic nghiệp vụ, điều kiện có thể là quyền, trạng thái phê duyệt, giá, số dư hạn mức, quyền dùng chứng từ hoặc một mã chưa bị tiêu thụ.

## 2. Check time không đồng nghĩa với thời điểm request đến

Một request có nhiều mốc khác nhau. Việc gộp chúng thành một timestamp `requestTime` làm mất ý nghĩa bảo mật.

| Mốc | Câu hỏi nó trả lời |
|---|---|
| `t_received` | Hệ thống nhận request khi nào? |
| `t_read` | Đường xử lý đọc từng dữ liệu đầu vào khi nào? |
| `snapshot_revision` hoặc mốc dữ liệu | Dữ liệu đọc được đại diện cho trạng thái nào? |
| `t_evaluated` | Hàm kiểm tra tính kết quả khi nào? |
| `t_decision` | Hệ thống giành quyền thực hiện hoặc chấp nhận chuyển trạng thái tại điểm nào? |
| `t_commit` | Những thay đổi được commit khi nào? |
| `t_effect` | Tác dụng quan sát được, như cấp quyền lợi bên ngoài, xảy ra khi nào? |

Các mốc có thể rất gần nhau hoặc cách nhau nhiều giờ. Một bước xử lý hàng đợi thường có `t_received` rất sớm nhưng `t_evaluated` và `t_effect` rất muộn.

### Phân biệt thời điểm đánh giá và độ mới của dữ liệu

Giả sử lúc 09:03, hàm `canApprove()` chạy và đọc một cache quyền được tạo lúc 09:00. Timestamp đánh giá là 09:03, nhưng căn cứ quyền vẫn là bản dữ liệu cũ.

```text
Hàm vừa chạy xong không có nghĩa dữ liệu vừa có hiệu lực.
```

Tương tự, một transaction có thể đọc một snapshot nhất quán nhưng snapshot đó không chứa những thay đổi đã xảy ra ngoài phạm vi nhìn thấy của nó. Tính nhất quán của bản đọc và độ mới so với yêu cầu nghiệp vụ là hai tính chất cần xem xét riêng.

Vì vậy, mô tả check time hữu ích cần nói cả **thời điểm đánh giá** và **phiên bản căn cứ**. Chỉ ghi `checkedAt = now()` chưa đủ.

## 3. Mô hình hóa một quyết định kiểm tra

Có thể mô tả một điều kiện như sau:

```text
P(subject, action, object, context, business_time)
```

Trong đó:

- `subject`: danh tính đã xác thực, tenant và quan hệ ủy quyền liên quan.
- `action`: hành động cụ thể như sửa số tiền, phê duyệt hoặc dùng voucher.
- `object`: đối tượng và phiên bản nội dung mà hành động tác động tới.
- `context`: quyền, chính sách, trạng thái liên quan và các căn cứ nghiệp vụ khác.
- `business_time`: mốc dùng để áp dụng điều kiện thời gian, nếu hành động có thời hạn.

Một kết quả kiểm tra có thể biểu đạt:

```text
P(dữ liệu quan sát ở check) = true
```

Kết quả đó không tự suy ra:

```text
P(dữ liệu ở lúc use) = true
```

Muốn suy ra điều thứ hai, phải có căn cứ rằng các điều kiện quan trọng không thay đổi theo cách làm mất hiệu lực quyết định, hoặc hành động được quyền sử dụng một snapshot đã được chấp nhận theo hợp đồng rõ ràng.

### Bằng chứng kiểm tra nên gắn với cái gì?

Ví dụ Java sau chỉ minh họa dữ liệu mô tả quyết định, không phải một cơ chế đồng bộ hoàn chỉnh:

```java
record CheckEvidence(
    UUID subjectId,
    UUID tenantId,
    String action,
    UUID objectId,
    long objectVersion,
    String contentRevision,
    long authorizationRevision,
    long policyRevision,
    Instant evaluatedAt,
    boolean allowed
) {}
```

Trong hệ thống thực tế, bằng chứng có thể gắn thêm đối tượng liên quan, mục đích, khóa lệnh hoặc khoảng hiệu lực. Các giá trị phải xuất phát từ nguồn có thẩm quyền.

Ghi lại các revision không tự ngăn TOCTOU. Nếu không so sánh hoặc bảo vệ chúng ở điểm quyết định, một `CheckEvidence` vẫn chỉ là mô tả về quá khứ. Ký số bằng chứng có thể bảo vệ tính toàn vẹn, nhưng không tự chứng minh quyền chưa bị thu hồi hoặc đối tượng chưa thay đổi.

## 4. Một lần kiểm tra thường là một khoảng đọc nhiều căn cứ

Trong nghiệp vụ thực tế, `canApprove()` có thể lần lượt đọc:

1. Membership của người dùng trong tenant.
2. Phạm vi bộ phận được phê duyệt.
3. Số tiền và trạng thái của đề nghị.
4. Hạn mức theo cấp phê duyệt.
5. Revision của chứng từ được đính kèm.

Những lần đọc này không nhất thiết đại diện cho cùng một trạng thái nhất quán. Đặt timestamp sau bước cuối không làm cho tất cả dữ liệu trước đó trở thành dữ liệu của cùng thời điểm.

Ví dụ:

```text
T1: Đọc số tiền đề nghị là 80 triệu.
T2: Một giao dịch khác đổi nội dung thành 150 triệu và tăng revision.
T3: Đọc chính sách cho phép Mai duyệt tối đa 100 triệu.
T4: Kết luận được phép dựa trên số tiền 80 triệu.
T5: Phê duyệt nội dung hiện tại trị giá 150 triệu.
```

Điều kiện đã được tính đúng trên số tiền 80 triệu, nhưng được dùng cho đối tượng khác về nội dung. Đây là lỗi gắn sai căn cứ giữa check và use.

### Liệt kê dependency của quyết định

Một bảng căn cứ giúp xác định cần bảo vệ gì:

| Căn cứ | Ai có thể làm thay đổi? | Điều gì làm kết quả cũ mất hiệu lực? |
|---|---|---|
| Quyền trên bộ phận | Quản trị viên hoặc luồng quản lý quyền | Thu hồi quyền hoặc thay phạm vi |
| Trạng thái đề nghị | Người dùng, approver khác, worker | Hủy, sửa, phê duyệt hoặc mở lại |
| Số tiền và dòng hàng | Luồng chỉnh sửa nội dung | Vượt hạn mức hoặc đổi nội dung được duyệt |
| Chính sách phê duyệt | Luồng cấu hình chính sách | Thay mức hoặc quy tắc áp dụng |
| Chứng từ | Luồng quản lý tệp và quan hệ | Đổi revision, bị chặn hoặc không còn được dùng |

Cách bảo vệ có thể khác nhau theo dependency: khóa, phiên bản, revision bất biến, snapshot đã được ràng buộc hoặc cơ chế điều phối khác. Không cần giữ khóa cho dữ liệu bất biến; cũng không thể bảo vệ quyền thay đổi độc lập chỉ bằng phiên bản của đề nghị.

## 5. Xác định mốc kiểm tra từ hợp đồng nghiệp vụ

Không có một câu trả lời duy nhất “luôn kiểm tra khi request đến” hoặc “luôn kiểm tra ở cuối”. Phải xác định điều gì cần đúng tại mốc nào.

| Điều kiện | Mốc hiệu lực thường cần xem xét | Chỉ kiểm tra sớm có thể bỏ sót |
|---|---|---|
| Quyền thao tác trên đối tượng | Điểm chấp nhận hành động theo hợp đồng thu hồi quyền | Quyền bị thu hồi khi request đang chờ |
| Nội dung người dùng đã xác nhận | Khi gắn quyết định vào đúng revision | Nội dung đổi sau khi mở màn hình |
| Trạng thái nguồn | Khi thực hiện chuyển trạng thái | Đối tượng đã được hủy hoặc xử lý bởi người khác |
| Lượng tồn kho hoặc hạn mức | Khi cấp phần tài nguyên cho lệnh | Tài nguyên bị giao dịch khác sử dụng |
| Thời hạn voucher | Mốc quyết định được policy định nghĩa | Voucher hết hạn trong hàng đợi hoặc khi chờ khóa |
| Quyền tải tệp | Khi cấp quyền tải hoặc tại từng lượt truy cập, tùy mô hình | URL đã cấp còn được dùng sau khi quyền đổi |

### Ba loại hợp đồng cần phân biệt

**Đánh giá trên trạng thái hiện hành tại quyết định.** Ví dụ, người dùng phải còn quyền phê duyệt khi thao tác được chấp nhận. Quyền đã đọc từ màn hình cũ không đủ.

**Sử dụng snapshot được ràng buộc có chủ ý.** Ví dụ, một báo giá có phiên bản và thời hạn riêng được hệ thống chấp nhận dùng trong khoảng hiệu lực. Giá danh mục mới không nhất thiết thay thế giá trong báo giá đã được cấp. Việc bảo lưu phải là chính sách rõ ràng, không phải hậu quả vô tình của cache.

**Cấp quyền hoặc reservation có phạm vi và thời hạn.** Ví dụ, một phần tài nguyên được giữ riêng cho lệnh trước khi xử lý tiếp. Phải có danh tính reservation, điều kiện sử dụng, kết thúc và giải phóng. Một cờ `checked=true` không tạo ra reservation.

Những hợp đồng này có thể kết hợp. Một lệnh có thể dùng giá từ báo giá bất biến, nhưng vẫn phải kiểm tra quyền hiện hành và tồn kho hiện hành tại điểm cấp tài nguyên.

## 6. Điểm quyết định cần có thứ tự với thay đổi cạnh tranh

“Kiểm tra ngay trước khi ghi” vẫn còn một khoảng đua nếu một giao dịch khác có thể thay đổi căn cứ sau kiểm tra mà trước khi ghi.

```text
A: đọc quyền hiện hành, thấy được phép
B: thu hồi quyền và commit
A: UPDATE đề nghị bằng ID, không có bảo vệ liên quan
```

Việc hai câu lệnh của A nằm sát nhau không chứng minh B không thể chen vào. Cần xác định **điểm quyết định** mà các thao tác tranh chấp được đặt theo một thứ tự rõ ràng.

### Ví dụ hợp đồng thu hồi quyền

Giả sử giao dịch phê duyệt và giao dịch thu hồi quyền cùng tham gia một giao thức khóa bảo vệ căn cứ quyền. Hai lịch hợp lệ có thể là:

```text
Lịch 1:
  Thu hồi quyền giành khóa, cập nhật và commit trước.
  Phê duyệt đọc quyền sau đó, thấy quyền không còn và bị từ chối.

Lịch 2:
  Phê duyệt giành khóa bảo vệ quyền trước và giữ đến commit.
  Thu hồi quyền phải chờ; sau phê duyệt mới cập nhật và commit.
  Những lệnh phê duyệt sau đó bị từ chối.
```

Theo hợp đồng này, việc một yêu cầu thu hồi đã được gửi lên không đồng nghĩa mọi giao dịch đang thực hiện phải bị hủy ngay. Điều bảo đảm là thứ tự hiệu lực giữa những giao dịch cùng tham gia giao thức.

Nếu sản phẩm yêu cầu hủy hoặc chặn cả các công việc đã chấp nhận nhưng chưa tạo tác dụng, cần cơ chế bổ sung ở giai đoạn đó. Không tuyên bố bảo đảm này chỉ từ khóa dùng ở bước cập nhật ban đầu.

### Những cơ chế có thể tạo căn cứ

- **Conditional update:** gắn phiên bản và trạng thái được kiểm tra vào cùng câu ghi.
- **Khóa trong transaction:** giữ những dữ liệu có thể thay đổi theo giao thức đến khi hoàn tất quyết định.
- **Revision bất biến:** gắn quyết định với đúng nội dung không bị ghi đè bên dưới.
- **Điểm điều phối aggregate:** bảo vệ điều kiện liên quan nhiều hàng, như hạn mức chung.
- **Reservation hoặc capability:** cấp một quyền có phạm vi rõ ràng, thay cho việc giả định kết quả kiểm tra sống vô hạn.

Mỗi cơ chế chỉ bảo vệ phần nó thực sự bao phủ. `object.version` không phát hiện thay đổi ACL ở bảng khác. Khóa một membership không bảo vệ một role dùng chung có thể đổi độc lập. Chỉ lưu `policyRevision` không làm cho policy đó được bảo lưu.

## 7. Điều kiện thời gian: chọn đồng hồ và điểm lấy thời gian

Một check time có thể cần một giá trị thời gian vật lý để áp dụng điều kiện như:

```text
valid_from <= decision_time < expires_at
```

Đó là điều kiện nghiệp vụ, khác với việc chỉ ghi timestamp phục vụ log.

### Không lấy thời gian do khách khai báo làm căn cứ cấp quyền

`submittedAt` từ trình duyệt có thể hữu ích để hiển thị hoặc đối chiếu, nhưng không đủ chứng minh một voucher đã được chấp nhận trước hạn. Máy chủ cần nguồn thời gian có thẩm quyền và mốc chấp nhận rõ ràng.

Nếu policy bảo lưu cho request đã được tiếp nhận trước hạn, thao tác tiếp nhận đó phải thực sự tạo một ràng buộc có thẩm quyền, như một reservation hoặc bản ghi chấp nhận được kiểm soát. Không chỉ đóng dấu thời gian khi request vừa chạm gateway rồi cho phép xử lý mọi điều kiện nghiệp vụ về sau.

### Chờ khóa có thể làm timestamp trước đó không còn phù hợp

```text
10:00:00  Request lấy timestamp và bắt đầu chờ khóa.
10:00:05  Voucher hết hạn.
10:00:10  Request lấy được khóa và tiếp tục dùng timestamp 10:00:00.
```

Nếu policy yêu cầu còn hạn tại điểm quyết định sau chờ, timestamp cũ không đáp ứng hợp đồng. Lấy hoặc đánh giá thời gian tại mốc thích hợp, đồng thời hiểu ngữ nghĩa thời gian của cơ sở dữ liệu hoặc dịch vụ thời gian đang dùng. Không mặc định một hàm mang tên `now` luôn phản ánh thời điểm mới nhất của từng câu lệnh.

### Phân biệt hiệu lực lúc quyết định và lúc commit

Một policy có thể cho phép chấp nhận voucher khi quyết định hợp lệ được thực hiện, rồi transaction commit sau hạn một khoảng ngắn. Policy khác có thể yêu cầu một tác dụng phải hoàn tất trước hạn.

Hai yêu cầu không tương đương. Bài kiểm tra thời hạn trước một UPDATE không chứng minh một dịch vụ bên ngoài sẽ thực thi trước hạn. Nếu nghiệp vụ yêu cầu bảo đảm ở tác dụng cuối, phải thiết kế ràng buộc hoặc kiểm tra tại nơi tạo tác dụng phù hợp.

Đồng bộ đồng hồ giúp kiểm soát sai lệch thời gian, nhưng không ngăn được giao dịch khác chen vào. Timestamp trùng nhau giữa hai log cũng không chứng minh hai hành động đồng thời hoặc theo thứ tự nào. Dùng phiên bản, giao thức khóa và quan hệ thứ tự khi cần chứng minh điều phối dữ liệu.

## 8. Ví dụ Java: đặt tên rõ thời điểm và căn cứ của phê duyệt

Đoạn sau là mã minh họa kiến trúc. Các abstraction thuộc ứng dụng; không mô tả API của framework cụ thể và không phải chương trình độc lập.

Mô hình ví dụ yêu cầu người duyệt còn quyền theo giao thức hiệu lực hiện hành, đề nghị đang `SUBMITTED` và nội dung đúng revision người duyệt đã xem.

```java
ApprovalResult approve(AuthenticatedContext requestContext,
                       ApproveCommand command) {
    return tx.required(() -> {
        AuthContext auth = authority.lockAndLoadCurrent(requestContext);
        PurchaseRequest request = requests.lockInTenant(
            auth.tenantId(), command.requestId())
            .orElseThrow(ResourceUnavailableException::new);

        PolicySnapshot rules = policies.loadUnderDecisionProtocol(auth, request);
        Instant evaluatedAt = decisionClock.nowAfterRequiredWaits();

        policy.requireApprovalPermission(auth, request, rules, evaluatedAt);
        workflow.requireState(request, SUBMITTED);
        revisions.requireReviewedContent(
            request.contentRevision(), command.reviewedContentRevision());
        invariants.requireApprovalRules(auth, request, rules);

        int changed = requests.markApprovedIfUnchanged(
            auth.tenantId(), request.id(), request.metadataVersion(),
            request.contentRevision(), SUBMITTED);
        if (changed != 1) {
            throw new ApprovalConflictException();
        }

        ApprovalRecord record = approvals.insert(
            auth.actorId(), auth.tenantId(), request.id(),
            request.contentRevision(), rules.revision(), evaluatedAt);
        audit.recordApproval(record);
        outbox.appendApprovalCommitted(record.id());
        return ApprovalResult.accepted(record.id());
    });
}
```

### Cần đọc đúng ý nghĩa của đoạn mã

- `evaluatedAt` mô tả mốc đánh giá sau những lần chờ được yêu cầu. Nó không tự là thời điểm commit hoặc thời điểm bên ngoài nhận thông báo.
- `lockAndLoadCurrent` phải có giao thức thật với những luồng thay đổi quyền. Nếu quyền còn đến từ nguồn thay đổi độc lập, abstraction phải giải quyết nguồn đó hoặc giới hạn bảo đảm được tuyên bố.
- `loadUnderDecisionProtocol` không chỉ tải một policy bất kỳ từ cache. Policy cần được bảo vệ hoặc bảo lưu đúng hợp đồng để không bị dùng sai giữa kiểm tra và ghi.
- `lockInTenant` đọc đúng tenant từ nguồn có thẩm quyền. Những thay đổi nội dung liên quan phải cùng tăng revision hoặc tham gia giao thức bảo vệ aggregate.
- `reviewedContentRevision` đến từ nội dung mà người dùng đã được phép xem và xác nhận. Máy chủ không tự thay nó bằng revision mới để làm lệnh thành công.
- `markApprovedIfUnchanged` kiểm tra tenant, đối tượng, phiên bản, revision và trạng thái nguồn trong câu ghi. Số hàng khác 1 không được coi là thành công.
- Trạng thái đề nghị, approval record, audit thành công và outbox nằm trong cùng transaction; nếu rollback, không có phê duyệt được chấp nhận.
- Những đường ghi khác phải dùng giao thức tương thích. Đặt tên hàm có chữ `lock`, `current` hoặc `protocol` không tạo ra bảo đảm nếu phần triển khai bỏ qua căn cứ liên quan.

Trong mô hình này, điểm ghi là một chuyển tiếp được bảo vệ trong transaction cuối cùng commit. Bước đánh giá là căn cứ của chuyển tiếp đó. Nếu transaction rollback, không có quyết định phê duyệt thành công chỉ vì hàm kiểm tra từng trả về true.

Endpoint hoàn chỉnh còn cần xử lý yêu cầu lặp theo ngữ nghĩa nghiệp vụ. Trả lại kết quả của một phê duyệt đã commit là việc đọc kết quả cũ, không phải một lần phê duyệt mới; đường đọc đó vẫn cần quyền xem hiện hành.

## 9. Khi nào cần kiểm tra lại ở một giai đoạn mới?

Không cần lặp cùng một kiểm tra ở mọi dòng mã. Cần đánh giá lại khi đi qua một ranh giới làm thay đổi căn cứ, ý nghĩa quyền hoặc phạm vi bảo đảm.

### Từ màn hình sang lệnh ghi

Hiện nút Phê duyệt giúp trải nghiệm người dùng, nhưng không phải quyết định cuối. Lệnh ghi phải kiểm tra danh tính, đối tượng, revision và trạng thái theo hợp đồng của nó.

### Từ tiếp nhận request sang worker

Job có thể chạy sau khi người dùng mất quyền, đối tượng bị hủy hoặc policy đổi. Worker phải dùng actor và tenant đã được máy chủ ràng buộc, rồi đánh giá điều kiện cần hiện hành tại giai đoạn thực thi. Quyền của tài khoản dịch vụ không tự thay thế quyền nghiệp vụ của người yêu cầu.

Nếu job chủ ý dùng snapshot chính sách đã được chấp nhận, hãy lưu đúng snapshot và quy tắc hiệu lực. Không mặc định mọi dữ liệu lúc enqueue đều được bảo lưu.

### Từ commit DB sang tác dụng bên ngoài

Outbox bảo vệ việc ghi nhận ý định phát công việc cùng transaction. Nó không bảo đảm quyền, thời hạn hoặc trạng thái bên ngoài còn phù hợp khi công việc được nhận.

Phải xác định tác dụng đó là thực hiện một quyết định đã được chấp nhận và được bảo lưu, hay là một hành động mới cần đánh giá lại. Nếu có khả năng hủy trong khoảng chờ, phải phối hợp thứ tự giữa lệnh hủy và nơi thực hiện, thay vì chỉ kiểm tra một cờ rồi gửi lệnh không thể thu hồi.

### Từ cấp URL sang sử dụng URL

Ứng dụng có thể kiểm tra quyền khi cấp một URL tải tệp. Lượt tải sau đó có thể dùng quyền đã phát hành mà không đi qua ứng dụng nữa. Khi đó check time nằm ở lúc cấp URL, còn use time nằm ở lúc tải.

Nếu sản phẩm cần quyền hiện hành ở từng lượt truy cập, phải dùng một đường kiểm soát hoặc cơ chế thu hồi thực sự hỗ trợ yêu cầu đó. Thời hạn URL ngắn chỉ thu hẹp cửa sổ, không tự tạo thu hồi tức thì.

## 10. Những cách mô tả check time dễ gây hiểu nhầm

| Mô tả hoặc cách làm | Điều còn thiếu |
|---|---|
| “Đã kiểm tra ở controller” | Quyền và trạng thái có còn phù hợp khi service ghi không? |
| “Kiểm tra ngay trước save” | Giao dịch khác có thể thay căn cứ giữa hai bước không? |
| “Hàm vừa chạy nên dữ liệu là mới” | Hàm đọc cache, replica hay snapshot nào? |
| “Có transaction nên không có TOCTOU” | Isolation và giao thức có bảo vệ đúng những dependency cần thiết không? |
| “Có version trên đối tượng” | Quyền, policy và các hàng liên quan có cùng được bao phủ không? |
| “Bằng chứng có chữ ký và chưa hết hạn” | Chữ ký chứng minh tính toàn vẹn; quyền có bị thu hồi hoặc nội dung có đổi không? |
| “Request đã đến trước hạn” | Điểm tiếp nhận có thực sự giữ quyền lợi hoặc chấp nhận nghiệp vụ không? |
| “Kiểm tra lại khi retry” | Có đọc và tính lại đầy đủ, hay chỉ thay version để ghi payload cũ? |

### Recheck không có bảo vệ vẫn có thể bị đua

Hai lần đọc liên tiếp chỉ tạo hai lần quan sát. Nếu điều kiện vẫn có thể đổi sau lần thứ hai, lỗ hổng vẫn tồn tại. Recheck cần đi cùng một điểm quyết định có điều kiện hoặc cơ chế giữ hiệu lực phù hợp.

### Cache TTL không phải khoảng hiệu lực quyền

TTL là chính sách làm mới dữ liệu. Một quyền có thể bị thu hồi ngay sau khi cache được tạo. Nếu nghiệp vụ chấp nhận độ trễ thu hồi, đó phải là hợp đồng rõ ràng; nếu không, TTL ngắn vẫn không đáp ứng yêu cầu.

### Nhiều phiên bản đúng riêng lẻ chưa chắc đủ

Kiểm tra version của từng hàng không tự bảo vệ invariant tổng hợp giữa các hàng. Hai giao dịch sửa hai hàng khác nhau có thể không xung đột phiên bản nhưng cùng vượt hạn mức. Khi định nghĩa check time cho điều kiện tổng hợp, cần xác định cả tập dữ liệu và điểm điều phối chung.

## 11. Kiểm thử bằng thứ tự hiệu lực thay vì chỉ timestamp

Một kiểm thử TOCTOU có ý nghĩa phải tạo được thay đổi giữa kiểm tra và sử dụng. Dùng transaction hoặc kết nối độc lập và điểm đồng bộ có điều khiển; không chỉ gửi nhiều request rồi hy vọng gặp khoảng đua.

### Kịch bản thu hồi thắng trước

```text
1. Cho giao dịch B thu hồi quyền và commit theo đúng giao thức.
2. Bắt đầu điểm quyết định phê duyệt của A.
3. Xác nhận A đọc căn cứ mới và bị từ chối.
4. Xác nhận không có trạng thái APPROVED, approval record hoặc tác dụng mới.
```

### Kịch bản phê duyệt giành bảo vệ trước

```text
1. A lấy khóa bảo vệ quyền và căn cứ cần thiết.
2. B bắt đầu thu hồi theo cùng giao thức và phải chờ ở điểm xung đột.
3. A hoàn tất kiểm tra và commit phê duyệt.
4. B tiếp tục thu hồi và commit.
5. Lệnh phê duyệt mới sau đó bị từ chối.
```

Kỳ vọng này phù hợp hợp đồng ở phần trước. Nếu sản phẩm chọn một hợp đồng thu hồi khác, kiểm thử phải biểu đạt đúng hợp đồng đó, thay vì mặc định mọi yêu cầu thu hồi đều hủy giao dịch đã bắt đầu.

### Ma trận tình huống cần kiểm tra

| Thay đổi hoặc ranh giới | Bằng chứng cần xác nhận |
|---|---|
| Quyền bị thu hồi sau khi mở màn hình | Nút cũ không cấp quyền cho lệnh mới |
| Nội dung đổi sau khi người dùng xem | Không phê duyệt revision mới bằng quyết định của revision cũ |
| Status đổi sau lần đọc đầu | Conditional transition hoặc khóa ngăn dùng trạng thái cũ |
| Cache quyền vẫn còn dữ liệu cũ | Đường quyết định đáp ứng hợp đồng độ mới đã chọn |
| Policy đổi trong khi request xử lý | Dùng đúng policy được bảo vệ hoặc bảo lưu, không trộn căn cứ |
| Thời hạn qua đi khi request chờ khóa | Không dùng timestamp trước chờ nếu policy yêu cầu thời điểm sau chờ |
| Job chạy muộn so với lúc enqueue | Đánh giá đúng điều kiện hiện hành hoặc snapshot đã được chấp nhận |
| Transaction kiểm tra đạt nhưng rollback | Không có quyết định nghiệp vụ hoặc tác dụng thành công tương ứng |
| Outbox được xử lý sau lệnh hủy | Kết quả tuân theo hợp đồng thứ tự với nơi tạo tác dụng |
| URL đã cấp được dùng sau thay đổi quyền | Hành vi đúng với bảo đảm thu hồi thực tế, không chỉ trạng thái DB |
| Retry sau xung đột | Không thay ngầm revision đã xem hoặc bỏ điều kiện để ghi được |

Trong kiểm thử thời hạn, dùng nguồn thời gian có thể điều khiển trong môi trường kiểm thử để đặt các mốc chính xác. Không cần chờ nhiều phút thật và cũng không dùng `sleep` ngẫu nhiên làm bằng chứng thứ tự.

Audit nên ghi subject, tenant, action, object, các revision liên quan, kết quả, evaluatedAt và định danh transaction hoặc lệnh phù hợp. Nếu chưa commit thì không gắn timestamp đánh giá với nhãn “đã thực hiện”. Log hỗ trợ giải thích quyết định; nó không thay thế cơ chế giữ quyết định hợp lệ.

## 12. Checklist định nghĩa check time

Với mỗi lệnh nhạy cảm, hãy hoàn thành các câu sau:

- Tôi đang kiểm tra predicate nào cho subject, action và object nào?
- Mỗi căn cứ được đọc từ đâu, thuộc revision nào và có nhất quán với các căn cứ khác không?
- Kết quả cần đúng lúc tiếp nhận, lúc quyết định ghi, lúc commit hay lúc tạo tác dụng bên ngoài?
- Đối tượng phải là nội dung người dùng đã xem hay trạng thái mới nhất mà lệnh cho phép đánh giá lại?
- Những thay đổi nào có thể làm kết quả kiểm tra mất hiệu lực?
- Cơ chế nào ngăn, phát hiện hoặc điều phối các thay đổi đó đến điểm sử dụng?
- Nếu dùng snapshot hoặc quyền có thời hạn, phạm vi bảo lưu và điều kiện thu hồi là gì?
- Thời gian nghiệp vụ lấy từ nguồn nào, trước hay sau các lần chờ có ý nghĩa?
- Retry, worker và sự kiện đến muộn có còn nằm trong cùng phạm vi hiệu lực không?
- Có kiểm thử chứng minh cả thứ tự cạnh tranh thắng trước và thắng sau không?

Check time được định nghĩa tốt phải nối được lần đánh giá với đúng căn cứ và đúng hành động được chấp nhận. Khi mối nối đó rõ ràng, ứng dụng mới có cơ sở chọn khóa, phiên bản, transaction hoặc reservation để bảo vệ quy tắc nghiệp vụ trong khoảng giữa kiểm tra và sử dụng.
