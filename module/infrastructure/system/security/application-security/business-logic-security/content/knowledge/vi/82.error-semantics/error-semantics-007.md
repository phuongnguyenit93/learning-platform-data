# Error disclosure boundary: ranh giới tiết lộ thông tin qua lỗi

## 1. Một lỗi cũng là dữ liệu trả về cho người gọi

Trong chương **Error Semantics**, *error disclosure boundary* là ranh giới xác định người gọi được biết điều gì khi một thao tác thất bại hoặc chưa xác định được kết quả. Ranh giới này bao gồm message, mã lỗi, HTTP status, header, thời gian phản hồi và mọi kênh trả kết quả liên quan.

Một API có thể chặn đúng việc hoàn tiền trái phép nhưng vẫn trả:

```json
{
  "code": "REFUND_LIMIT_EXCEEDED",
  "message": "Đơn hàng có thể hoàn thêm 850000 đồng",
  "ownerEmail": "owner@example.test",
  "approvalState": "APPROVED"
}
```

Nếu người gọi không được quyền biết đơn hàng đó, lỗi đã làm lộ sự tồn tại, chủ sở hữu, trạng thái phê duyệt và hạn mức. Việc không tạo khoản hoàn tiền chưa đủ để bảo vệ toàn bộ quy tắc nghiệp vụ.

Mục tiêu là cung cấp thông tin đủ để người có quyền xử lý tình huống của họ, đồng thời không biến API thành công cụ dò đối tượng, suy luận chính sách hoặc đọc dữ liệu vượt quyền.

Bất biến cần giữ:

> Mỗi chi tiết công khai trong phản hồi lỗi phải phù hợp với quyền biết thông tin của người nhận, không chỉ với quyền gọi endpoint.

Không phải mọi lỗi đều cần giống hệt nhau. Người dùng đang thao tác trên đơn của mình có thể cần biết đơn chưa được phê duyệt. Một người đang dò ID của tenant khác không được nhận cùng chi tiết đó. Thiết kế phải nêu rõ hai trường hợp, thay vì chọn giữa “lộ tất cả” và “mọi lỗi đều là lỗi chung”.

## 2. Phân biệt quyền thực hiện và quyền biết

### 2.1. Được gọi một hành động không đồng nghĩa được biết mọi dữ kiện

Một actor có thể được quyền đề nghị hoàn tiền nhưng không được xem công thức rủi ro, biên lợi nhuận hoặc hạn mức nội bộ của đối tác. Một nhân viên hỗ trợ có thể xem trạng thái xử lý nhưng không được xem thông tin tài khoản nhận tiền.

Cần xem xét ít nhất ba câu hỏi:

```text
mayDiscover(actor, object)
  Người gọi có được biết đối tượng này tồn tại không?

mayPerform(actor, action, object)
  Người gọi có được thực hiện hành động này không?

mayKnow(actor, detail, object, context)
  Người gọi có được biết chi tiết lỗi cụ thể này không?
```

Các quyết định này không tự thay thế nhau. Có consent cho một mục đích cũng không cấp quyền xem trạng thái consent của chủ thể khác. Biết một object ID hoặc idempotency key không chứng minh quyền đọc đối tượng hay kết quả cũ.

### 2.2. Phân loại thông tin có thể đi qua lỗi

| Loại thông tin | Ví dụ | Điều cần xác định |
|---|---|---|
| Cú pháp công khai | Trường bắt buộc bị thiếu, số tiền không đúng định dạng | Có thể giải thích mà không đọc trạng thái bí mật không? |
| Sự tồn tại | Order ID hợp lệ, tài khoản đã đăng ký | Người gọi có quyền khám phá đối tượng không? |
| Trạng thái nghiệp vụ | Đã phê duyệt, đã thanh toán, đã hoàn tiền | Có quyền đọc trạng thái đó trong ngữ cảnh hiện tại không? |
| Giá trị nghiệp vụ | Hạn mức còn lại, giá đối tác, số dư | Có cần và được phép trả con số cụ thể không? |
| Chính sách phòng vệ | Ngưỡng phát hiện lạm dụng, điểm rủi ro, quy tắc ngoại lệ | Chi tiết nào chỉ dành cho điều tra nội bộ? |
| Chi tiết hệ thống | SQL, stack trace, service nội bộ, connection string | Không đưa ra API công khai theo mặc định |
| Kết quả thực thi | Chưa thực hiện, đã commit, chưa rõ kết quả | Hệ thống có bằng chứng đủ để khẳng định không? |

Cùng một reason nội bộ có thể được ánh xạ thành nhiều cách diễn đạt công khai theo quyền người nhận. Ngược lại, nhiều reason nội bộ có thể cùng ánh xạ về một lỗi công khai khi việc phân biệt chúng làm lộ thông tin.

## 3. Các kênh tiết lộ vượt ngoài message

### 3.1. Mã lỗi và HTTP status

Hai message cùng là “Không thể thực hiện yêu cầu” nhưng status lần lượt 404 và 409 vẫn cho biết hai nhánh khác nhau. Mã `ORDER_EXISTS_BUT_NOT_YOURS` làm lộ sự tồn tại ngay cả khi message không chứa tên đơn hàng.

Nếu hợp đồng che sự tồn tại của đối tượng ngoài phạm vi, các trường hợp “không tồn tại” và “không được khám phá” cần có cùng dạng lỗi công khai, chẳng hạn `RESOURCE_UNAVAILABLE` với HTTP 404. Đây là một lựa chọn hợp đồng cho ranh giới đó, không có nghĩa mọi lỗi phân quyền trong hệ thống đều phải là 404.

Với đối tượng người gọi đã được phép biết, có thể trả lỗi từ chối hành động hoặc xung đột trạng thái cụ thể nếu nội dung đó cũng được phép biết. HTTP status không thay thế mã nghiệp vụ ổn định; mã nghiệp vụ cũng không được dùng để lách chính sách che thông tin.

### 3.2. Header và cấu trúc phản hồi

Các vị trí cần kiểm tra gồm:

- Header `Location` trỏ tới một thao tác hoặc đối tượng người gọi chưa được xem.
- ETag, phiên bản đối tượng hoặc timestamp cập nhật chỉ xuất hiện khi đối tượng tồn tại.
- `Retry-After` hoặc thông tin cooldown quá chi tiết về một chủ thể khác.
- Mảng `errors`, `details`, `extensions` hoặc nested `cause` chứa dữ liệu đã bỏ khỏi message chính.
- Độ dài, số trường và cách phân trang khác nhau giữa đối tượng bí mật và đối tượng không tồn tại.
- Mẫu lỗi khác nhau giữa JSON, HTML, endpoint phiên bản cũ và phương thức khác của cùng tài nguyên.

Nếu phản hồi phụ thuộc danh tính hoặc có dữ liệu riêng tư, phải thiết kế chính sách cache phù hợp. Một cache công khai chỉ khóa theo URL có thể phát lại lỗi chứa chi tiết của người có quyền cho người khác.

### 3.3. Thời gian và hành vi phụ

Một nhánh dừng ngay khi ID không tồn tại và một nhánh truy vấn nhiều lần khi đối tượng tồn tại có thể tạo tín hiệu thời gian. Lỗi đồng nhất về JSON không tự loại bỏ điều này.

Cần giảm khác biệt do thiết kế luồng: tra cứu trong phạm vi được phép, không đọc dữ liệu nhạy cảm chỉ để xây lỗi, không gọi dependency tùy theo trạng thái bí mật rồi trả cùng một câu chung. Với luồng nhạy cảm như khôi phục tài khoản, có thể dùng bước tiếp nhận bất đồng bộ và phản hồi chung theo hợp đồng.

Không coi thêm delay ngẫu nhiên là bằng chứng đã khắc phục rò rỉ. Nhiễu có thể bị giảm bằng nhiều quan sát, đồng thời tạo chi phí vận hành. Đánh giá thời gian cần dựa vào đường thực thi, số lượng mẫu và threat model; không hứa mọi thao tác nghiệp vụ có thời gian hằng tuyệt đối.

## 4. Chính sách tiết lộ theo ngữ cảnh

Một ma trận quyết định giúp tránh việc từng exception tự chọn thông điệp:

| Ngữ cảnh đã xác minh | Kết quả nội bộ | Phản hồi công khai có thể dùng |
|---|---|---|
| Chưa xác thực trong endpoint yêu cầu đăng nhập | Thiếu danh tính hợp lệ | Lỗi xác thực theo hợp đồng, không tra chi tiết đối tượng để giải thích |
| Actor không được khám phá đối tượng | Không tồn tại hoặc ngoài phạm vi | Cùng lỗi `RESOURCE_UNAVAILABLE` |
| Actor biết đối tượng nhưng không có quyền hành động | Không được phép thực hiện | Lỗi quyền hành động nếu không làm lộ trạng thái khác |
| Actor có quyền và được đọc trạng thái phê duyệt | Thiếu phê duyệt | `APPROVAL_REQUIRED`, có hướng dẫn hợp lệ tiếp theo |
| Actor được yêu cầu thao tác nhưng không được xem chi tiết rủi ro | Rule rủi ro từ chối | Lỗi điều kiện chung, không trả điểm và ngưỡng |
| Không đọc được trạng thái có thẩm quyền | Dependency lỗi | Lỗi tạm thời; không giả vờ đã xác định đối tượng không tồn tại |
| Mất phản hồi sau khi tác động có thể đã xảy ra | Chưa rõ kết quả | Lỗi hoặc trạng thái chưa xác định, kèm cách kiểm tra hợp lệ |

Những status hoặc tên mã trong bài là ví dụ hợp đồng API. Hệ thống cần chọn cách nhất quán và kiểm thử chúng, không suy luận rằng mọi `deny` phải thành cùng một status hoặc mọi exception đều là lỗi của người dùng.

Ba lớp thông tin nên được tách:

```text
Public error:
  Mã ổn định, message an toàn, hướng dẫn phù hợp, correlation reference.

Diagnostic event:
  Reason nội bộ, rule, giai đoạn, thông tin kỹ thuật đã giảm dữ liệu.

Audit/business record:
  Quyết định và tác động cần lưu bền vững, với quyền đọc chuyên biệt.
```

Chi tiết được giữ nội bộ vẫn cần bảo vệ dữ liệu nhạy cảm. Không chuyển nguyên stack trace chứa token vào log rồi coi việc giấu nó khỏi API là đã hoàn tất ranh giới bảo vệ.

## 5. Thứ tự kiểm tra quyết định ranh giới lỗi

### 5.1. Đừng đánh giá bí mật trước khi xác định quyền

Một thứ tự nguy hiểm:

```text
Đọc đơn theo orderId bất kỳ
→ kiểm tra trạng thái thanh toán
→ kiểm tra hạn mức còn lại
→ nếu mọi thứ đúng mới kiểm tra người gọi có quyền
```

Người ngoài phạm vi có thể lần lượt quan sát `NOT_PAID`, `LIMIT_EXCEEDED` hoặc `FORBIDDEN` để suy ra dữ kiện. Việc đổi toàn bộ message về câu chung ở cuối không đủ nếu status, reason hoặc thời gian vẫn khác.

Một thứ tự có kiểm soát hơn:

```text
Xác thực danh tính
→ kiểm tra cú pháp công khai không phụ thuộc trạng thái bí mật
→ xác định đối tượng trong phạm vi được phép khám phá
→ xác minh quyền hành động hiện tại
→ xác định các chi tiết được phép công khai
→ đánh giá bất biến và thực hiện transaction
→ ánh xạ lỗi theo chính sách tiết lộ
```

Kiểm tra cú pháp công khai có thể diễn ra sớm: thiếu field, sai định dạng hoặc số tiền không dương nếu đây là quy tắc đầu vào công khai. Kiểm tra phụ thuộc dữ liệu như hạn mức còn lại hoặc trạng thái phê duyệt cần đúng ngữ cảnh quyền trước khi công khai kết quả.

Query theo tenant là cần thiết trong nhiều mô hình nhưng chưa luôn đủ: hai người trong cùng tenant vẫn có thể có phạm vi đối tượng khác nhau. Nếu query không biểu diễn được toàn bộ chính sách, cần bước authorize thích hợp trước khi đọc thêm chi tiết hoặc tạo lỗi đặc thù đối tượng.

### 5.2. Luồng Java minh họa

Mã giả dưới đây diễn đạt thứ tự và trách nhiệm, không phải một triển khai hoàn tiền có thể chép vào chạy ngay:

```java
@Transactional
public RefundReceipt requestRefund(
        VerifiedActor actor,
        RefundCommand command) {

    publicInput.validateSyntax(command);

    // Scope bắt nguồn từ danh tính đã xác minh, không từ tenantId của client.
    RefundTarget target = orders.findDiscoverableRefundTargetForUpdate(
        actor.scope(), command.orderId());

    if (target == null) {
        throw failures.resourceUnavailable();
    }

    if (!permissions.mayRequestRefundNow(actor, target)) {
        // Chỉ dùng lỗi quyền hành động ở đây vì quyền khám phá đã được giữ.
        throw failures.actionForbidden();
    }

    DisclosureGrant disclosure = disclosurePolicy.forRefund(actor, target);
    RuleOutcome outcome = refundRules.evaluate(target, command);

    if (outcome.isError()) {
        throw failures.evaluationUnavailable(outcome.internalReason());
    }

    if (outcome.isDenied()) {
        throw failures.ruleDenied(
            outcome.internalReason(),
            disclosure,
            EffectStatus.NOT_APPLIED);
    }

    return refundWriter.applyWithCommitGuards(target, command);
}
```

Các hợp đồng cần đi kèm:

- `VerifiedActor` không được tạo bằng cách sao chép role, tenant hoặc user ID do client tự khai báo.
- Repository chỉ trả đối tượng có thể khám phá theo chính sách; query không đọc được do lỗi hạ tầng phải phát lỗi hạ tầng, không trả `null` để giả thành không tồn tại.
- Quyền hành động và trạng thái dùng để ghi phải có cơ chế nhất quán nếu có thể thay đổi đồng thời. Một lần kiểm tra trước transaction không tự bảo vệ mọi bất biến.
- `DisclosureGrant` do máy chủ tạo cho đúng actor, đối tượng và hành động. Nó không phải field cho client gửi lên để bật lỗi chi tiết.
- `NOT_APPLIED` chỉ đúng ở nhánh đã chứng minh chưa có tác động. Không tái dùng khẳng định đó cho timeout sau một lời gọi ra ngoài.
- Handler chỉ tạo DTO lỗi công khai sau khi xác định kết quả transaction phù hợp; không serialize toàn bộ exception hoặc `DisclosureGrant` ra response.

Mapper không nên tự truy vấn lại đối tượng chỉ để “làm đẹp” thông báo. Việc đó có thể tạo cuộc đua mới, đọc vượt phạm vi hoặc phát sinh thêm tín hiệu thời gian. Nên mang theo ngữ cảnh tiết lộ tối thiểu đã được xác lập ở ranh giới nghiệp vụ, với mặc định hạn chế khi ngữ cảnh không đủ.

## 6. Thiết kế DTO lỗi và ánh xạ có kiểm soát

### 6.1. DTO công khai có schema riêng

Ví dụ lỗi dành cho người có quyền đọc trạng thái phê duyệt:

```json
{
  "code": "APPROVAL_REQUIRED",
  "message": "Yêu cầu cần được phê duyệt trước khi tiếp tục.",
  "correlationRef": "corr-generated-by-server",
  "nextAction": "REVIEW_APPROVAL"
}
```

Ví dụ cho đối tượng không được khám phá:

```json
{
  "code": "RESOURCE_UNAVAILABLE",
  "message": "Không tìm thấy tài nguyên có thể truy cập.",
  "correlationRef": "corr-generated-by-server"
}
```

Correlation reference do máy chủ kiểm soát giúp hỗ trợ tìm sự kiện nội bộ. Nó không phải bằng chứng cấp quyền xem log hoặc trạng thái thao tác. Không trả một liên kết dashboard nội bộ hoặc token tra cứu đặc quyền như phần thưởng kèm lỗi.

Nếu thêm `nextAction`, chỉ dẫn phải phù hợp với quyền người nhận. Không hướng người ngoài phạm vi tới `/approvals/{secretApprovalId}` hoặc cung cấp tên người phê duyệt của một hồ sơ bí mật.

### 6.2. Ánh xạ theo tập cho phép

Một bảng ánh xạ cho rule hoàn tiền có thể là:

| Reason nội bộ | Điều kiện tiết lộ | Mã công khai |
|---|---|---|
| `object_missing` | Mọi trường hợp ở ranh giới che sự tồn tại | `RESOURCE_UNAVAILABLE` |
| `object_outside_discovery_scope` | Cùng ranh giới ở trên | `RESOURCE_UNAVAILABLE` |
| `approval_missing` | Được biết đối tượng và trạng thái phê duyệt | `APPROVAL_REQUIRED` |
| `approval_missing` | Biết đối tượng nhưng không được xem chi tiết trạng thái | `ACTION_NOT_AVAILABLE` |
| `risk_rule_rejected` | Không có quyền biết chi tiết chính sách | `ACTION_NOT_AVAILABLE` |
| `remaining_exceeded` | Được biết điều kiện hoàn tiền | `REFUND_AMOUNT_NOT_ALLOWED`, không mặc nhiên trả hạn mức chính xác |
| `dependency_unavailable` | Không thể đánh giá đáng tin cậy | `TEMPORARILY_UNAVAILABLE` |
| Lỗi không phân loại được | Không đủ ngữ cảnh an toàn | `INTERNAL_ERROR`, không lộ message gốc |

Các dòng `ACTION_NOT_AVAILABLE` chỉ áp dụng sau khi quyền khám phá và ngữ cảnh hành động đã được xác lập; không dùng chúng thay cho lỗi che sự tồn tại ở một nhánh khác rồi vô tình tạo dấu phân biệt.

Một mã lỗi cụ thể không bắt buộc chứa mọi dữ kiện tạo ra quyết định. Ví dụ người dùng có thể biết số tiền đề nghị không hợp lệ nhưng không cần biết công thức ngưỡng rủi ro hoặc ngoại lệ của đối tác.

### 6.3. Những shortcut dễ phá ranh giới

```java
// Không dùng thông điệp exception làm hợp đồng công khai.
return error(exception.getMessage());

// Không serialize nguyên đối tượng lỗi có cause, stack hoặc context nội bộ.
return json(exception);
```

Cũng cần kiểm soát lỗi validation của framework: nhiều bộ xử lý mặc định kèm `rejectedValue`, tên class hoặc thông báo chứa giá trị gốc. Chỉ trả đường dẫn field được phép và lời nhắc cố định; không echo token, số tài khoản hoặc nội dung nhạy cảm để nói chúng không hợp lệ.

Message có thể được bản địa hóa, nhưng code và chính sách tiết lộ phải ổn định. Bản dịch không được vô tình thêm thông tin mà phiên bản ngôn ngữ khác đã giấu. Không để query `debug=true`, header tùy ý hoặc role chưa kiểm chứng bật stack trace công khai.

## 7. Transaction và cuộc đua làm giới hạn điều có thể khẳng định

### 7.1. Một cập nhật thất bại không tự cho biết nguyên nhân duy nhất

Giả sử một cập nhật hoàn tiền dùng điều kiện tổng hợp:

```sql
UPDATE refund_budget
SET refunded_amount = refunded_amount + :amount,
    revision = revision + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND revision = :expected_revision
  AND refund_approved = TRUE
  AND refunded_amount + :amount <= refundable_amount;
```

Khi số hàng cập nhật bằng 0, có thể revision đã đổi, phê duyệt đã bị thu hồi, hạn mức không còn đủ hoặc không có đối tượng trong phạm vi query. Không tự suy luận “hạn mức còn lại là X” hoặc “đơn không tồn tại” từ kết quả đó.

Với người được phép biết đối tượng, có thể trả một xung đột an toàn và yêu cầu đọc lại trạng thái nếu hợp đồng cho phép. Muốn trả reason cụ thể phải có dữ kiện có thẩm quyền và giữ đúng ranh giới tiết lộ. Đọc lại ngoài transaction có thể thấy trạng thái mới khác nguyên nhân thất bại ban đầu; không trình bày nó như bằng chứng chắc chắn về quá khứ.

Nếu một lỗi ràng buộc cơ sở dữ liệu chứa tên constraint, giá trị khóa trùng hoặc dữ liệu hàng, chỉ chuyển nó thành mã công khai đã chọn. Không trả nguyên SQL exception để người gọi biết vì sao transaction rollback.

### 7.2. Lỗi trước commit, sau commit và chưa rõ kết quả

| Tình huống | Điều hệ thống có thể biết | Cách diễn đạt cần tránh |
|---|---|---|
| Bị chặn trước tác động, không có bước ngoài transaction | Chưa thực hiện thao tác được bảo vệ | Không cần bịa thêm nguyên nhân chi tiết không có quyền biết |
| Transaction cục bộ rollback đã được xác nhận | Thay đổi trong transaction không có hiệu lực | Không suy rộng rằng mọi lời gọi ngoài hệ thống cũng đã hoàn tác |
| Commit thành công nhưng serialize response lỗi | Tác động đã xảy ra | “Thao tác thất bại, hãy tạo yêu cầu mới” |
| Timeout sau khi gửi yêu cầu cho đối tác | Có thể đã được tiếp nhận hoặc thực hiện | “Chắc chắn chưa có khoản hoàn tiền nào” |
| Không nhận được xác nhận commit | Chưa đủ bằng chứng về trạng thái cuối | Trả một kết luận chắc chắn chỉ vì client thấy lỗi |

Phản hồi lỗi phải vừa bảo vệ thông tin, vừa trung thực về kết quả. Một câu chung “Không thể hoàn tất phản hồi” có thể phù hợp hơn lời khẳng định “Đã hủy thao tác” khi hệ thống chưa xác định được tác động.

Nếu hợp đồng hỗ trợ trạng thái chưa xác định, có thể dùng mã như `OPERATION_STATUS_UNKNOWN` và hướng dẫn kiểm tra một thao tác mà người gọi có quyền xem. Không dùng một correlation reference chẩn đoán như mã cấp quyền truy vấn thao tác.

### 7.3. Chỉ dẫn retry cũng nằm trong ranh giới lỗi

Thông báo “hãy thử lại” có thể dẫn đến tác động lặp nếu thao tác không được bảo vệ. Với yêu cầu có thể đã tạo hiệu lực, nên dùng lại cơ chế idempotency của cùng thao tác theo hợp đồng hoặc kiểm tra trạng thái trước, thay vì tự động tạo key mới.

Việc dùng lại key cũng không tự cấp quyền hoặc bảo đảm hệ thống bên ngoài không xử lý trùng. Hướng dẫn cần gắn với cơ chế đã triển khai và trạng thái có thể xác minh. Không trả `retryable=true` chỉ dựa vào việc status là 500 hoặc 503.

Đường kiểm tra trạng thái phải xác thực actor, phạm vi tenant, quyền trên thao tác và mức chi tiết được xem. Biết mã thao tác hoặc receipt không tự được quyền đọc số tiền, người nhận hoặc kết quả của người khác.

## 8. Idempotency có thể lưu lại lỗi vượt quyền

### 8.1. Cache phản hồi là một kho dữ liệu cần phân quyền

Một triển khai idempotency có thể lưu cả status và body rồi trả nguyên trạng khi key trùng. Nếu body chứa hạn mức, trạng thái phê duyệt hoặc dữ kiện đối tượng, cache đã trở thành một đường đọc khác của dữ liệu đó.

Cần giữ các điều kiện:

- Key được phân phạm vi theo tenant, actor hoặc principal và thao tác theo hợp đồng; không dùng một namespace chung cho mọi người.
- Request cùng key nhưng khác nội dung nghiệp vụ phải bị xử lý xung đột, không được diễn giải lại thành thao tác khác.
- Quyền đọc kết quả và mức tiết lộ cần được kiểm tra theo trạng thái hiện tại khi phục vụ dữ liệu lưu trước đó, nhất là khi vai trò, chủ sở hữu hoặc consent đã đổi.
- Receipt tối thiểu và dữ liệu chi tiết có thể cần chính sách đọc khác nhau.
- Lỗi hoặc kết quả cũ không được phát sang actor khác chỉ vì họ biết key.

Trả lỗi `IDEMPOTENCY_CONFLICT` không cần kèm payload trước đó, hash của dữ liệu nhạy cảm, người tạo thao tác hay số tiền cũ. Phân biệt key không tồn tại với key thuộc người khác cũng có thể làm lộ sự tồn tại nếu endpoint cho phép dò namespace chung.

### 8.2. Không đóng băng quyền cũ trong một response

Giả sử một nhân viên từng được đọc hồ sơ và nhận lỗi kèm tên người phê duyệt. Sau đó nhân viên mất quyền. Gửi lại key không được trở thành cách đọc lại tên người phê duyệt từ response cache.

Có thể lưu kết quả nghiệp vụ chuẩn hóa và dựng lại phần hiển thị theo quyền hiện tại, hoặc kiểm tra quyền trước khi trả response đã lưu. Dù chọn cách nào, cần giữ nghĩa idempotency của tác động mà không coi nội dung cache là giấy phép tiết lộ vĩnh viễn.

Nếu cùng thao tác đã commit nhưng actor hiện không còn quyền xem chi tiết, phản hồi cần bảo vệ dữ liệu và không nói sai rằng thao tác chưa từng tồn tại hay đã rollback. Một lỗi quyền đọc phù hợp với ranh giới công khai có thể đi cùng đường hỗ trợ có kiểm soát, thay vì lộ kết quả cũ.

## 9. Các tình huống nghiệp vụ thường gặp

### 9.1. Dò đối tượng bằng thay đổi ID

Một người gọi lần lượt thử nhiều order ID. Nếu đơn không tồn tại trả 404, đơn của người khác trả 403 kèm `APPROVED`, còn đơn đã hoàn tiền trả 409, họ có thể phân loại đơn mà không được quyền đọc.

Giải pháp là xác lập ranh giới khám phá trước, trả cùng dạng lỗi cho “không có đối tượng có thể truy cập” ở phạm vi đó, và không đọc trạng thái bí mật để tạo lời giải thích cho người ngoài phạm vi. Rate limit và phát hiện hành vi dò giúp giảm lạm dụng nhưng không sửa việc phản hồi vốn đã tiết lộ.

### 9.2. Suy luận trạng thái phê duyệt

Endpoint `approve` hoặc `execute` có thể làm lộ người phê duyệt, số bước còn lại hoặc lý do bị treo. Người được gửi đề nghị không mặc nhiên được biết quy tắc duyệt nội bộ.

Có thể trả “Yêu cầu chưa đáp ứng điều kiện thực hiện” cho nhóm người chỉ được biết kết quả khả dụng, trong khi người có quyền xem quy trình nhận `APPROVAL_REQUIRED` với hướng dẫn phù hợp. Không trả đường dẫn tới một hồ sơ phê duyệt mà người nhận không được mở.

### 9.3. Sửa giá và dò ngưỡng chấp nhận

Nếu lỗi trả cả giá nhập, giá tối thiểu bí mật, chiết khấu tối đa và công thức điều chỉnh, người gọi có thể dùng nhiều lần thử để học điều kiện nội bộ.

Máy chủ vẫn cần tự xác định giá hợp lệ và bảo vệ transaction. Phản hồi chỉ nên trả báo giá hoặc điều kiện mà actor có quyền xem, ví dụ yêu cầu làm mới quote của chính phiên giao dịch. Không nhầm “giấu ngưỡng” với việc không cần kiểm tra giá; bảo vệ thực sự vẫn nằm ở quy tắc được thực thi phía máy chủ.

Một `quoteId` cũng cần gắn với đúng actor, phạm vi và nội dung theo thiết kế. Lỗi quote không được tiết lộ báo giá của người khác hoặc cho phép dùng quote cũ để vượt điều kiện mới.

### 9.4. Khôi phục tài khoản và xác nhận thông tin liên hệ

Một luồng có thể trả cùng thông báo tiếp nhận cho địa chỉ tồn tại và không tồn tại, chẳng hạn “Nếu thông tin phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký”. Không nói chắc chắn “đã gửi” nếu chỉ mới tiếp nhận hoặc không có tài khoản tương ứng.

Cần xem cả status, header, thời gian, quota và lỗi của nhà cung cấp gửi. Phản hồi bất đồng bộ chỉ giảm một phần khác biệt; không tự loại bỏ mọi kênh suy luận. Bằng chứng xác thực, mã xác nhận và link khôi phục không được xuất hiện trong lỗi.

Sự cố hạ tầng không nên bị che thành một kết luận sai về tài khoản. Chính sách tiếp nhận, hàng đợi và tình huống không thể phục vụ cần được thống nhất mà không dùng trạng thái tồn tại tài khoản làm tín hiệu công khai ngoài ý muốn.

### 9.5. Batch, GraphQL, websocket và tác vụ nền

Ranh giới không kết thúc ở REST controller. Mảng kết quả batch, trường lỗi từng phần, message websocket, email trạng thái và webhook đều có thể chứa cùng chi tiết nhạy cảm.

Trong batch, không trả reason phân biệt “không tồn tại” và “tồn tại nhưng không phải của bạn” cho các ID ngoài phạm vi. Số lượng phân theo hai loại đó cũng có thể tiết lộ, dù không trả từng bản ghi. Chỉ trả tổng hoặc phân loại theo mức người nhận được phép biết.

Một job được tạo khi actor có quyền nhưng hoàn tất sau khi quyền thay đổi không tự được gửi chi tiết cũ ra kênh thông báo. Kiểm tra quyền và chính sách tiết lộ ở thời điểm cung cấp kết quả theo yêu cầu của hệ thống; không chỉ ở lúc enqueue.

## 10. Giữ chẩn đoán nội bộ mà không làm rò ra kênh khác

### 10.1. Lưu reason nội bộ riêng với public code

Một sự kiện chẩn đoán đã giảm dữ liệu có thể ghi:

```json
{
  "event": "business_operation_rejected",
  "operation": "refund",
  "rule": "refund_approval_required",
  "internalReason": "approval_missing",
  "publicCode": "ACTION_NOT_AVAILABLE",
  "disclosureClass": "object_visible_details_restricted",
  "effectStatus": "not_applied",
  "correlationRef": "corr-generated-by-server"
}
```

Sự khác nhau giữa `internalReason` và `publicCode` là có chủ đích. Nội bộ cần phân biệt điều kiện nghiệp vụ với dependency lỗi; bên ngoài chỉ được biết phần hợp đồng cho phép. Không gộp mọi lỗi nội bộ vào một reason duy nhất để che thông tin rồi làm mất khả năng vận hành.

Các trường này thuộc tập đã định nghĩa, không nhận nguyên message hoặc giá trị request. Nếu cần tham chiếu đối tượng để điều tra, dùng hình thức, nơi lưu và quyền đọc phù hợp; không đặt email, object ID hoặc correlation reference vào nhãn metric.

`effectStatus` phải dựa vào dữ kiện thực thi. Nó không được tự động là `not_applied` cho mọi exception. Trường hợp chưa biết phải có trạng thái tương ứng thay vì một giá trị làm dashboard trông chắc chắn hơn thực tế.

### 10.2. Kênh hỗ trợ cũng có ranh giới

Một nhân viên hỗ trợ biết correlation reference không tự được đọc toàn bộ dữ liệu của vụ việc. Công cụ tra cứu cần xác thực người vận hành, giới hạn phạm vi và ghi nhận truy cập thích hợp.

Không dán lỗi nội bộ chứa token, query hoặc dữ liệu thanh toán vào ticket để bù cho message công khai ngắn. Nếu phải chuyển giao điều tra, dùng tham chiếu và dữ kiện đã lọc qua kênh có quyền phù hợp.

Đường thông báo lỗi của proxy, servlet container hoặc handler cuối cùng cũng cần cùng chính sách. Một mapper an toàn ở controller không giúp ích khi exception ngoài controller được trang lỗi mặc định render stack trace và biến môi trường.

## 11. Quản lý hợp đồng lỗi khi hệ thống thay đổi

### 11.1. Mặc định hạn chế cho lỗi mới

Khi thêm một domain exception mới, không mặc định message của nó là nội dung công khai. Cần xác định:

1. Nó phát sinh ở giai đoạn nào và dữ kiện nào đã được xác minh?
2. Nó có tiết lộ sự tồn tại, trạng thái hoặc giá trị của đối tượng không?
3. Nhóm người nhận nào được biết từng chi tiết?
4. Tác động đã bị ngăn, đã commit hay chưa rõ kết quả?
5. Mã công khai, status và hướng dẫn tiếp theo là gì?
6. Reason nội bộ và dữ liệu audit cần giữ là gì?

Mapper nên dùng tập ánh xạ được quản lý và fallback an toàn cho trường hợp không biết. Không suy đoán chính sách bằng cách tìm từ `permission`, `amount` hoặc `approval` trong exception message.

### 11.2. Những thay đổi cần được xem cùng nhau

Thay message nhưng giữ code chi tiết cũ không khép được ranh giới. Đổi 403 thành 404 nhưng vẫn trả ETag thật cũng chưa đủ. Khi sửa chính sách, cần xem đồng thời body, status, header, cache, format và các đường đọc lại kết quả.

Một client có thể dựa vào code để quyết định retry hoặc mở bước phê duyệt. Vì vậy, đổi code hoặc gộp reason cần quản lý như thay đổi hợp đồng. Đừng sửa rò rỉ bằng cách làm client tạo lại yêu cầu có khả năng tác động lặp.

Chính sách chi tiết hơn chỉ nên bật theo quyền và ngữ cảnh đã kiểm chứng. Môi trường production không được nhận cấu hình debug từ request. Với công cụ quản trị thực sự cần nhiều thông tin, có thể có endpoint hoặc kênh riêng cùng quyền đọc chuyên biệt, thay vì bật một cờ để mọi người nhận raw exception.

### 11.3. Khi phát hiện lỗi đang tiết lộ dữ liệu

Có thể xử lý theo trình tự:

- Xác định chính xác trường hoặc tín hiệu đang vượt quyền, không chỉ câu message.
- Sửa thứ tự kiểm tra hoặc phép ánh xạ tại ranh giới thích hợp; loại bỏ default serializer nguy hiểm.
- Xem lại các response cache và kết quả idempotency có thể giữ body cũ.
- Kiểm tra các kênh tương đương như batch, phiên bản API cũ, websocket và thông báo nền.
- Nếu bí mật truy cập đã bị trả ra, đánh giá việc vô hiệu hóa hoặc thay mới; chỉ ngừng trả lỗi cũ không làm bí mật đã sao chép mất hiệu lực.
- Bổ sung ca kiểm thử cho tín hiệu bị lộ và giữ khả năng chẩn đoán bằng kênh nội bộ đã bảo vệ.

Không cần đưa dữ liệu bị lộ thật vào mã kiểm thử hoặc tài liệu tái hiện. Dùng dữ liệu tổng hợp có thể nhận diện và tham chiếu sự kiện theo quyền điều tra.

## 12. Kiểm thử ranh giới tiết lộ và hành vi nghiệp vụ

### 12.1. So sánh các trường hợp không được phép phân biệt

Với ranh giới che sự tồn tại, tạo ít nhất hai đối tượng thử nghiệm:

```text
A: ID chắc chắn không tồn tại.
B: ID tồn tại nhưng nằm ngoài phạm vi khám phá của actor.
```

Gửi cùng loại yêu cầu và so sánh status, code, field, header, định dạng và đường cache. Nếu có correlation reference hoặc timestamp thay đổi hợp lệ, so sánh ý nghĩa sau khi chuẩn hóa các trường động, không yêu cầu toàn bộ byte response luôn giống nhau.

Thực hiện thêm biến thể payload sai cú pháp, payload đúng nhưng sai trạng thái và phương thức/định dạng được hỗ trợ. Một ranh giới chỉ đúng cho payload “đẹp” vẫn có thể bị phá bởi thứ tự validation ở nhánh lỗi khác.

Kiểm tra thời gian bằng nhiều quan sát trong môi trường có kiểm soát và xem đường query/dependency. Một ca test đơn lẻ không chứng minh không có kênh thời gian; số liệu cũng không thay thế việc hiểu vì sao hai nhánh xử lý khác nhau.

### 12.2. Ma trận ca kiểm thử

| Tình huống | Điều cần xác minh |
|---|---|
| Chưa xác thực gọi endpoint được bảo vệ | Không đọc hoặc tiết lộ trạng thái đối tượng để giải thích lỗi |
| ID không tồn tại và ID ngoài phạm vi | Cùng hợp đồng công khai tại ranh giới che sự tồn tại |
| Hai người cùng tenant nhưng khác quyền đối tượng | Không coi tenant đúng là đã đủ quyền đọc chi tiết |
| Actor biết đối tượng nhưng không được làm hành động | Lỗi phản ánh quyền hành động mà không lộ trạng thái khác |
| Chủ thể có quyền đọc phê duyệt | Có hướng dẫn đủ dùng, không chứa dữ liệu nội bộ không cần thiết |
| Actor không được biết chi tiết rủi ro | Không có điểm, ngưỡng, rule expression hoặc ngoại lệ bí mật |
| Validation thất bại với token hoặc số tài khoản trong input | Không có `rejectedValue`, echo input hoặc nested cause làm lộ giá trị |
| Dependency kiểm tra lỗi | Nội bộ phân loại được error; không trả một kết luận sai rằng đối tượng không tồn tại |
| Cập nhật có điều kiện ảnh hưởng 0 hàng | Không đoán một nguyên nhân cụ thể chưa được chứng minh |
| Transaction rollback đã biết | Không ghi hoặc trả thành công; giới hạn khẳng định đúng với phạm vi transaction |
| Commit thành công nhưng response lỗi | Không hướng client tạo yêu cầu mới như thể chắc chắn chưa có tác động |
| Timeout ở dịch vụ ngoài | Có ngữ nghĩa chưa rõ kết quả và đường kiểm tra/retry phù hợp |
| Replay sau khi actor mất quyền | Không phát lại dữ liệu đặc quyền từ body idempotency cũ |
| Cùng idempotency key nhưng khác payload | Không trả payload, người tạo hoặc dữ kiện của thao tác trước |
| Client gửi `debug=true` hoặc role giả | Không bật chi tiết và không đổi chính sách tiết lộ |
| Batch gồm ID ngoài phạm vi và ID không tồn tại | Không lộ qua lỗi từng phần hoặc số lượng phân biệt hai nhóm |
| Request qua proxy hoặc handler ngoài controller | Không có trang lỗi mặc định, stack trace hoặc header nội bộ |
| Đổi ngôn ngữ hoặc format response | Vẫn cùng chính sách tiết lộ, không chỉ cùng message ở một ngôn ngữ |
| Cache nhận response của actor có quyền | Không phục vụ body đó cho actor khác qua cùng URL |

Mỗi ca lỗi cần kiểm tra cả tác động thực tế. Một response an toàn nhưng thao tác trái phép vẫn commit không phải thiết kế đạt yêu cầu. Ngược lại, transaction được bảo vệ nhưng response lộ dữ liệu cũng không đạt ranh giới đã định nghĩa.

### 12.3. Bảo toàn giá trị sử dụng cho người có quyền

Cần có ca dương tính cho chủ thể hợp lệ: họ vẫn biết nên bổ sung field nào, làm mới phiên bản nào hoặc mở quy trình phê duyệt nào mà họ được phép dùng. Nếu mọi lỗi đều thành `INTERNAL_ERROR`, hệ thống có thể che dữ liệu nhưng làm người dùng và client xử lý sai, tăng retry và tăng tải hỗ trợ.

Mục tiêu kiểm thử là chi tiết đúng người, đúng ngữ cảnh và đúng mức chắc chắn về tác động. Không phải tối đa hóa số trường bị xóa mà bỏ qua ngữ nghĩa nghiệp vụ.

## 13. Tự đối chiếu thiết kế

1. Ai được biết đối tượng tồn tại, ai được thực hiện hành động và ai được biết reason chi tiết?
2. Mọi lỗi phụ thuộc dữ liệu bí mật có được kiểm tra sau ranh giới quyền phù hợp không?
3. Status, code, header, body, cache và thời gian có vô tình phân biệt điều phải được che không?
4. Có raw exception, `rejectedValue`, SQL hoặc dữ liệu request nào lọt qua serializer mặc định không?
5. Phản hồi có đang khẳng định chưa có tác động khi thực tế chỉ là chưa nhận được xác nhận không?
6. Hướng dẫn retry có giữ nghĩa idempotency và quyền đọc kết quả hiện tại không?
7. Batch, thông báo nền và API phiên bản cũ có cùng chính sách với đường chính không?
8. Nội bộ còn đủ reason và bằng chứng điều tra mà không làm log trở thành kênh lộ dữ liệu mới không?

Ranh giới tiết lộ lỗi được giữ khi mỗi phản hồi chỉ chứa những khẳng định mà hệ thống có thể chứng minh và người nhận được phép biết. Việc đó cần đi cùng quyền theo đối tượng, thứ tự kiểm tra, transaction và idempotency, thay vì chỉ thay đổi câu chữ cuối cùng trước khi trả response.
