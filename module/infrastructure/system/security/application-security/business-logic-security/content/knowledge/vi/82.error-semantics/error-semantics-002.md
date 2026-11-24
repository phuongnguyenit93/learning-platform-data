# Phản hồi khi kiểm tra quyền thất bại (Authorization failure response)

## 1. Phản hồi lỗi quyền là một phần của kiểm soát nghiệp vụ

Trong chương **Error Semantics**, phản hồi khi kiểm tra quyền thất bại cần diễn đạt đúng điều đã xảy ra: hệ thống từ chối chủ thể thực hiện hành động trên một đối tượng trong ngữ cảnh cụ thể. Nó phải giúp client xử lý hợp lý, hạn chế lộ thông tin và giữ được dấu vết điều tra.

Một thông báo “Không có quyền” không tự chứng minh hệ thống an toàn. Nếu server đã đổi giá hoặc gửi hoàn tiền rồi mới trả lỗi, kiểm soát đã thất bại. Ngược lại, phản hồi quá chi tiết có thể giúp người gọi dò ra đơn hàng của tenant khác, danh tính người duyệt hoặc trạng thái nhạy cảm của đối tượng.

Trong mô-đun bảo mật logic nghiệp vụ, thiết kế này liên quan trực tiếp đến việc ngăn:

- Thao tác đúng loại nhưng sai đối tượng, như hoàn tiền cho đơn của khách hàng khác.
- Gọi trực tiếp bước phê duyệt mà tài khoản không được phép thực hiện.
- Tự phê duyệt, vượt phạm vi hạn mức hoặc dùng quyền của người khác.
- Khai thác thông điệp lỗi để dò tài nguyên và tìm đường bỏ qua quy trình.
- Gửi lại yêu cầu sau lỗi rồi tạo thay đổi trùng hoặc đọc được kết quả của người khác.

Mục tiêu là giữ nhất quán bốn thành phần: **quyết định quyền, kết quả nghiệp vụ thật, phản hồi công khai và bản ghi nội bộ**.

## 2. Phân biệt xác thực, phân quyền và quy tắc nghiệp vụ

### 2.1. Ba câu hỏi khác nhau

| Lớp kiểm tra | Câu hỏi | Ví dụ thất bại |
| --- | --- | --- |
| Xác thực — authentication | Ai đang gọi, và danh tính đó có được xác nhận không? | Thiếu thông tin xác thực hoặc phiên không còn hợp lệ |
| Phân quyền — authorization | Chủ thể này được thực hiện hành động này trên đối tượng này không? | Nhân viên không được duyệt; đơn không thuộc phạm vi được giao |
| Quy tắc và trạng thái nghiệp vụ | Với chủ thể có quyền, thao tác có hợp lệ tại thời điểm này không? | Yêu cầu đã hủy, phiên bản đã đổi hoặc không còn số dư để hoàn |

Một tài khoản đã đăng nhập không mặc nhiên có quyền trên mọi đối tượng. Một tài khoản có vai trò `REFUND_AGENT` cũng không mặc nhiên được hoàn tiền cho mọi tenant hay được tự phê duyệt yêu cầu của mình.

Cần xác định ranh giới theo hợp đồng sản phẩm. Ví dụ, “không thuộc nhóm người được duyệt” là lỗi quyền; “yêu cầu đã được duyệt trước đó” có thể là xung đột trạng thái. Chính sách dựa trên thuộc tính có thể sử dụng cả trạng thái đối tượng; điều quan trọng là phân loại nhất quán và không tiết lộ trạng thái cho người không có quyền biết.

### 2.2. Ý nghĩa HTTP nền tảng

| Status | Ý nghĩa liên quan tới bài này |
| --- | --- |
| `401 Unauthorized` | Thiếu thông tin xác thực hợp lệ cho tài nguyên; phản hồi phải có `WWW-Authenticate` với challenge phù hợp |
| `403 Forbidden` | Server hiểu yêu cầu nhưng từ chối thực hiện; không chỉ giới hạn ở vấn đề thông tin xác thực |
| `404 Not Found` | Không tìm thấy biểu diễn hiện tại hoặc không muốn tiết lộ nó tồn tại; có thể dùng để che tài nguyên bị cấm |

Các ý nghĩa trên theo [RFC 9110, mục 15.5.2–15.5.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2). Tên “Unauthorized” của 401 dễ gây nhầm; không vì thấy chữ đó mà dùng 401 cho mọi lỗi thiếu quyền.

Ví dụ API dùng Bearer authentication có thể gửi challenge như sau khi cần xác thực:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="business-api"
Content-Type: application/json
Cache-Control: no-store

{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Cần xác thực để tiếp tục.",
  "request_id": "req-a81f"
}
```

Challenge phải phù hợp cơ chế xác thực thật của API. Ví dụ không yêu cầu mọi hệ thống dùng Bearer hoặc dùng cùng một realm.

## 3. Quyết định khi nào trả 403 và khi nào che bằng 404

### 3.1. Quyền biết đối tượng và quyền thao tác không giống nhau

Giả sử một hệ thống có ba chủ thể:

- Khách hàng An được xem đơn của mình nhưng không được thực hiện thao tác hoàn tiền nội bộ.
- Nhân viên Bình được xử lý các đơn trong phạm vi được giao, nhưng không có quyền duyệt hoàn tiền.
- Người dùng Chi thuộc một tenant khác, không được biết đơn đang xét tồn tại.

Với An hoặc Bình, một phản hồi 403 chung cho hành động bị cấm có thể phù hợp nếu việc xác nhận đối tượng tồn tại không làm lộ thêm thông tin ngoài quyền xem của họ. Với Chi, sản phẩm có thể chọn cùng phản hồi 404 như khi ID không tồn tại.

Đây là lựa chọn chính sách công khai thông tin, không phải quy tắc “mọi lỗi quyền luôn là 404” hoặc “đã đăng nhập thì luôn là 403”. Quyết định phải do server đưa ra từ ngữ cảnh đáng tin cậy, không từ tham số `show_details=true` do client gửi.

### 3.2. Hai phản hồi công khai minh họa

Đối tượng được phép biết, nhưng hành động không được phép:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{
  "code": "ACTION_NOT_ALLOWED",
  "message": "Bạn không được phép thực hiện thao tác này.",
  "request_id": "req-b72e"
}
```

Không muốn tiết lộ đối tượng tồn tại:

```http
HTTP/1.1 404 Not Found
Content-Type: application/json
Cache-Control: no-store

{
  "code": "RESOURCE_NOT_FOUND",
  "message": "Không tìm thấy tài nguyên.",
  "request_id": "req-c63d"
}
```

Trong chính sách che giấu này, nhánh “ID không tồn tại” và nhánh “ID tồn tại nhưng không được phép biết” cần có hình dạng phản hồi công khai tương đương. Nếu status cùng là 404 nhưng body nhánh thứ hai có `TENANT_MISMATCH`, mục tiêu che giấu đã bị phá vỡ.

Không trả tên chủ sở hữu, tenant đúng, trạng thái phê duyệt hoặc danh sách vai trò còn thiếu chỉ để giải thích kỹ hơn cho một chủ thể không được biết dữ liệu ấy.

### 3.3. Không chỉ body mới có thể làm lộ thông tin

Cần xem cả:

- Header như `ETag`, `Last-Modified`, `Location` hoặc metadata của đối tượng.
- Link tải tệp, trang trạng thái job và API tìm kiếm có cùng dữ liệu.
- Kết quả danh sách, số lượng bản ghi, thông báo trong batch và đường xuất báo cáo.
- Sự khác nhau quá rõ về đường xử lý và thời gian phản hồi giữa ID có thật và ID không có thật.

Không thể hứa mọi request mạng sẽ mất đúng cùng thời gian. Mục tiêu là loại bỏ các khác biệt có hệ thống không cần thiết và kiểm thử khả năng dò qua nhiều lần gọi. Thêm một lệnh sleep tùy ý không sửa được việc body hoặc header đã tiết lộ dữ liệu.

Bản thân mã lỗi công khai cũng là một kênh thông tin. Có thể cần nhiều mã nội bộ nhưng chỉ một mã công khai cho các nhánh phải được che giấu.

## 4. Tách nguyên nhân nội bộ khỏi hợp đồng lỗi công khai

Một hệ thống có thể cần biết chính xác lý do từ chối để điều tra, trong khi client chỉ nên nhận thông báo an toàn.

| Nguyên nhân nội bộ minh họa | Phản hồi công khai có thể dùng | Ghi chú |
| --- | --- | --- |
| `OBJECT_OUTSIDE_VISIBLE_SCOPE` | 404, `RESOURCE_NOT_FOUND` | Không khẳng định tenant hoặc chủ sở hữu thật |
| `ACTION_PERMISSION_MISSING` | 403, `ACTION_NOT_ALLOWED` | Chỉ khi được phép xác nhận ngữ cảnh đối tượng |
| `SEPARATION_OF_DUTIES_VIOLATION` | 403, thông điệp được sản phẩm cho phép | Có thể giải thích không được tự duyệt nếu thông tin đó được phép công khai |
| `DELEGATION_NOT_VALID` | 403 hoặc phản hồi che giấu theo ngữ cảnh | Không coi một header tự khai là ủy quyền hợp lệ |
| `AUTHORIZATION_EVALUATION_UNAVAILABLE` | Lỗi dịch vụ chung theo hợp đồng | Đây là chưa đánh giá được, không phải quyết định chắc chắn rằng người gọi thiếu quyền |
| `VISIBLE_RESOURCE_STATE_CONFLICT` | Lỗi xung đột nghiệp vụ theo hợp đồng | Chỉ mô tả trạng thái khi chủ thể được phép biết |

Ví dụ bản ghi nội bộ cho một lần từ chối:

```json
{
  "event_type": "AUTHORIZATION_DENIED",
  "request_id": "req-b72e",
  "actor_id": "user-17",
  "tenant_id": "tenant-08",
  "action": "REFUND_APPROVE",
  "target_ref": "RFD-42",
  "internal_reason": "SEPARATION_OF_DUTIES_VIOLATION",
  "policy_version": "refund-approval-v4",
  "decision": "DENY",
  "public_status": 403,
  "public_code": "ACTION_NOT_ALLOWED",
  "business_effect": "NOT_APPLIED"
}
```

Chỉ gán `NOT_APPLIED` khi đã có căn cứ về ranh giới xử lý. Nếu không biết commit đã xảy ra chưa, phải ghi kết quả chưa xác định thay vì suy từ HTTP status.

Danh tính và tenant trong bản ghi đến từ ngữ cảnh xác thực đã được kiểm chứng. Không chép nguyên `actor_id` trong body vào như danh tính thật. Nếu cần lưu ID do người gọi thử truy cập, hãy phân biệt rõ nó là đầu vào được yêu cầu, không nhất thiết là đối tượng đã tồn tại và được phân giải thành công.

`request_id` dùng nối phản hồi với dấu vết nội bộ, không phải mật khẩu để mở log hoặc quyền truy cập đối tượng. Trường này nên được tạo hoặc kiểm soát ở ranh giới hệ thống để không chứa dữ liệu do người gọi tùy ý chèn.

Không gửi stack trace, câu SQL, đường dẫn máy chủ, biểu thức chính sách, token hoặc nội dung hồ sơ nhạy cảm trong phản hồi. Dữ liệu nội bộ cũng cần tối thiểu hóa, giới hạn kích thước và phân quyền đọc.

## 5. Từ chối phải xảy ra trước tác dụng phụ

### 5.1. Thứ tự xử lý có chủ đích

Một trình tự phù hợp cho lệnh thay đổi nghiệp vụ là:

1. Kiểm tra an toàn giao thức, kích thước và cấu trúc tối thiểu để tiếp nhận request.
2. Xác thực danh tính và xác lập ngữ cảnh tenant/ủy quyền từ nguồn đáng tin cậy.
3. Tìm đối tượng trong phạm vi được phép nhìn thấy hoặc áp dụng chính sách che giấu.
4. Kiểm tra quyền thực hiện hành động, quan hệ với đối tượng và các điều kiện phân quyền liên quan.
5. Kiểm tra trạng thái, phiên bản, phê duyệt và business invariant theo hợp đồng hành động.
6. Chỉ khi các điều kiện cần thiết đều đạt, ghi thay đổi, audit bắt buộc, outbox và kết quả idempotency theo ranh giới transaction đã thiết kế.
7. Trả phản hồi phản ánh đúng kết quả đã biết.

Đây là thứ tự trách nhiệm, không buộc mọi kiểm tra phải nằm trong một hàm. Kiểm tra một phần ở gateway không thay thế kiểm tra đối tượng trong dịch vụ nghiệp vụ. Việc ẩn nút trên giao diện cũng không bảo vệ API khỏi lời gọi trực tiếp.

Có thể cần parse hoặc chặn input không an toàn trước xác thực; không nên hiểu “xác thực trước” thành yêu cầu tải toàn bộ một body không giới hạn. Tuy nhiên, không thực hiện kiểm tra nghiệp vụ chi tiết làm lộ trạng thái đối tượng cho người chưa được phép biết.

### 5.2. Không kiểm tra quyền trên bản chụp đã lỗi thời rồi dùng dữ liệu khác

Giả sử nhân viên có quyền trên một yêu cầu khi nó còn thuộc nhóm mình. Giữa lúc kiểm tra và lúc cập nhật, yêu cầu được chuyển cho nhóm khác. Nếu thao tác vẫn dùng kết quả kiểm tra cũ mà chính sách yêu cầu đánh giá tại thời điểm thực thi, có thể xảy ra lỗi kiểm tra và sử dụng ở hai thời điểm khác nhau.

Với thuộc tính ảnh hưởng quyết định, cần bảo vệ mối liên hệ giữa dữ liệu đã đánh giá và dữ liệu được thay đổi bằng khóa, phiên bản hoặc một cơ chế tương đương. Các luồng chuyển quyền sở hữu, thay đổi phê duyệt và thu hồi quyền phải tuân thủ quy ước nhất quán.

Trong hệ thống phân tán, việc thu hồi quyền và thời điểm hiệu lực phải có hợp đồng rõ ràng. Không khẳng định quyền luôn được cập nhật tức thì ở mọi node nếu thực tế dùng cache có thời hạn. Cache quyết định cho phép cần được thiết kế cùng yêu cầu về thu hồi và độ trễ phân phối chính sách.

### 5.3. Một phản hồi 403 không đảo ngược giao dịch đã gửi

Đoạn mã giả sau là một lỗi thiết kế:

```java
refundGateway.sendRefund(command);  // Tác dụng phụ đã xảy ra bên ngoài.
authorization.requireCanRefund(principal, order);
return acceptedReceipt();
```

Nếu kiểm tra quyền thất bại, trả 403 không thu hồi được lệnh hoàn tiền đã gửi. Đặt lời gọi bên ngoài trong một transaction cơ sở dữ liệu cũng không khiến rollback cơ sở dữ liệu đảo ngược cổng thanh toán.

Lệnh bị chặn ở ranh giới phân quyền phải dừng trước tác dụng phụ cần quyền đó. Với luồng bất đồng bộ, không được tạo một outbox có thể thực thi lệnh bị cấm rồi coi việc trả lỗi là đủ. Nếu có tác vụ bù cho tác dụng phụ đã phát sinh, đó là một quy trình nghiệp vụ riêng có quyền, trạng thái và audit riêng.

### 5.4. Khi thành phần đánh giá quyền bị lỗi

Không đánh giá được quyền và đã đánh giá là không có quyền là hai kết quả khác nhau:

```text
ALLOW         -> chỉ tiếp tục khi các điều kiện nghiệp vụ khác cũng đạt
DENY          -> dừng hành động và ánh xạ phản hồi theo chính sách công khai
INDETERMINATE -> không cấp quyền mặc định; xử lý lỗi đánh giá theo hợp đồng
```

Ví dụ, dịch vụ chính sách mất kết nối không phải bằng chứng người dùng thiếu vai trò. Hệ thống có thể trả lỗi dịch vụ chung như 503 với thông điệp không lộ dữ liệu, đồng thời không thực hiện hành động khi chưa có quyết định cho phép hợp lệ. Đây là lựa chọn hợp đồng của ứng dụng, không phải yêu cầu rằng mọi lỗi nội bộ đều ánh xạ sang cùng một status.

Không bắt exception rồi chuyển sang một tài khoản mặc định có quyền rộng hơn. Không bỏ qua bước kiểm tra chỉ vì môi trường đang có sự cố. Nếu có cơ chế dùng quyết định được cache hoặc quyền khẩn cấp, nó phải là chính sách được thiết kế và kiểm soát rõ, không phải nhánh `catch` ngẫu nhiên.

## 6. Tập trung ánh xạ lỗi nhưng giữ quyết định quyền ở đúng chỗ

### 6.1. Handler phản hồi không tự quyết định quyền thay dịch vụ

Các endpoint nên dùng cùng hợp đồng phản hồi và cùng cơ chế ánh xạ lỗi. OWASP khuyến nghị tập trung xử lý thất bại kiểm soát truy cập, thoát an toàn và tránh đưa thông tin nhạy cảm vào thông báo lỗi. Xem [OWASP Authorization Cheat Sheet — Exit Safely when Authorization Checks Fail](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html#exit-safely-when-authorization-checks-fail).

Tập trung handler không có nghĩa chỉ kiểm tra quyền tại controller. Quy tắc phải được thực thi ở lớp mà các đường vào liên quan đều phải đi qua, bao gồm API, job, công cụ quản trị và các lời gọi nội bộ cần cùng bảo đảm.

Một mô hình mã giả Java cho phần ánh xạ:

```java
ApiResponse mapAccessFailure(AccessFailure failure, SafeRequestContext context) {
    // Kind và disclosure là dữ liệu phía server, không lấy từ request body.
    if (failure.kind() == FailureKind.AUTHENTICATION_REQUIRED) {
        return errors.authenticationRequired(
            context.requestId(), authenticationChallenge.forThisApi()
        );
    }

    if (failure.kind() == FailureKind.EVALUATION_UNAVAILABLE) {
        return errors.serviceUnavailable(
            "SECURITY_CHECK_UNAVAILABLE",
            "Chưa thể xử lý yêu cầu lúc này.",
            context.requestId()
        );
    }

    if (failure.disclosure() == Disclosure.HIDE_EXISTENCE) {
        return errors.notFound(
            "RESOURCE_NOT_FOUND",
            "Không tìm thấy tài nguyên.",
            context.requestId()
        );
    }

    return errors.forbidden(
        "ACTION_NOT_ALLOWED",
        "Bạn không được phép thực hiện thao tác này.",
        context.requestId()
    );
}
```

Đoạn mã minh họa trách nhiệm, không phải ví dụ chạy độc lập. Các helper thiết lập status và header phù hợp, dùng schema công khai cố định, không tự serialize toàn bộ exception. `AccessFailure` chỉ đại diện các lỗi truy cập đã phân loại; handler không được coi mọi lỗi lập trình là lỗi quyền.

Quyết định `HIDE_EXISTENCE` phải được tạo theo chính sách đáng tin cậy. Không suy quyền công khai chỉ từ việc repository đã tìm thấy row, vì row có thật không đồng nghĩa người gọi được biết nó.

Nếu repository cố ý tìm trong phạm vi nhìn thấy và không có kết quả, hệ thống có thể chỉ biết `NOT_FOUND_OR_NOT_VISIBLE`. Không cần mở thêm một truy vấn đặc quyền để phân biệt hai trường hợp chỉ nhằm tạo thông báo lỗi chi tiết hơn.

### 6.2. Những cách xử lý exception nguy hiểm

```java
try {
    authorization.requireCanApprove(principal, refund);
} catch (AccessDenied denied) {
    logger.warn("Approval denied");
}

// Sai: luồng vẫn tiếp tục sau khi đã bị từ chối.
refund.approve(principal.subjectId());
```

Ghi log không chấm dứt thực thi. Luồng cần trả về hoặc ném lỗi để kết thúc hành động; nếu đã có thay đổi trong transaction thì phải rollback theo bảo đảm của framework hoặc hạ tầng đang sử dụng.

Cũng không nên bắt mọi `Exception` rồi trả 403. Một lỗi kết nối cơ sở dữ liệu, lỗi serialize hay lỗi lập trình cần được ghi nhận và xử lý theo nhóm phù hợp, thay vì che thành “người dùng không có quyền”. Sự nhầm lẫn đó làm client xử lý sai và che giấu sự cố thật.

Phải kiểm tra cả đường do middleware xác thực, filter, interceptor và dịch vụ nghiệp vụ tạo lỗi. Nếu mỗi đường phát một kiểu HTML/JSON khác nhau, API có thể vừa khó sử dụng vừa tạo tín hiệu dò thông tin không chủ đích.

## 7. Không dùng lỗi quyền thay cho mọi lỗi nghiệp vụ

Ví dụ hợp đồng cho một API hoàn tiền có thể là:

| Tình huống | Nhóm lỗi của ứng dụng | Phản hồi minh họa |
| --- | --- | --- |
| Chưa có danh tính hợp lệ | Xác thực | 401, mã yêu cầu xác thực |
| Được xem yêu cầu nhưng không được duyệt | Phân quyền hành động | 403, `ACTION_NOT_ALLOWED` |
| Không được biết yêu cầu tồn tại | Không công khai đối tượng | 404, giống nhánh không tìm thấy |
| Có quyền gửi nhưng yêu cầu chưa được phê duyệt | Điều kiện trạng thái chưa đáp ứng | 409, `REFUND_NOT_READY`, chỉ khi được phép biết trạng thái |
| Có quyền nhưng phiên bản lệnh đã cũ | Xung đột phiên bản theo hợp đồng lệnh | 409, mã xung đột của ứng dụng |
| Số tiền âm hoặc định dạng không hợp lệ | Kiểm tra đầu vào | Nhóm lỗi đầu vào do API quy định |
| Không đánh giá được quyền | Sự cố đánh giá | Lỗi dịch vụ chung, không tự thực hiện lệnh |

Những dòng về lỗi trạng thái và đầu vào là lựa chọn minh họa của hợp đồng ứng dụng. Không cần ép mọi vi phạm business invariant vào 403 chỉ vì nó liên quan bảo mật. Điều quan trọng là không cung cấp thông tin trạng thái trước khi đã xác định người gọi được phép biết.

Ví dụ, thông báo “Yêu cầu đang chờ quản lý Nguyễn Văn B duyệt khoản 450.000 VND” có thể phù hợp ở một màn hình nội bộ có đủ quyền, nhưng không phù hợp cho người ngoài đang thử ID. Cùng một căn cứ nội bộ có thể cần mức chi tiết khác nhau theo quyền công khai.

Không trả `200 OK` kèm `success=false` cho nhánh từ chối của REST API trong hợp đồng minh họa này. Client, proxy và công cụ quan sát cần hiểu được đó là một lần bị chặn. Với giao thức có cấu trúc lỗi khác, như kết quả từng trường hoặc từng phần tử batch, phải định nghĩa và kiểm thử rõ lớp lỗi ứng dụng thay vì suy toàn bộ kết quả chỉ từ status HTTP.

## 8. Retry, idempotency và thay đổi quyền

### 8.1. Client không nên lặp mù quáng một yêu cầu bị từ chối

Trong hợp đồng ứng dụng, client cần có hành vi phục hồi theo nhóm lỗi:

- Khi cần xác thực, đi qua luồng xác thực phù hợp với cơ chế của API; giới hạn số vòng thử và không gửi lại vô hạn.
- Khi hành động bị cấm, dừng thao tác tự động và hiển thị hướng dẫn được phép công khai, thay vì liên tục refresh token rồi gọi lại.
- Khi tài nguyên không được tìm thấy theo chính sách công khai, không dò các endpoint phụ để cố lấy thông tin còn lại.
- Khi có xung đột trạng thái trên đối tượng được phép xem, đọc lại trạng thái hoặc làm mới thao tác theo quy trình hợp lệ.
- Khi lỗi tạm thời hoặc kết quả chưa rõ, tuân thủ hợp đồng retry, idempotency và tra cứu trạng thái; không tự tạo lệnh mới với khóa mới để “thử cho chắc”.

Một số sản phẩm có bước xác thực tăng cường cho hành động nhạy cảm. Cơ chế challenge và phản hồi phải tuân theo giao thức được chọn. Hoàn thành xác thực tăng cường không tự cấp một quyền nghiệp vụ còn thiếu, như quyền tự duyệt hoặc quyền trên đơn thuộc tenant khác.

### 8.2. Khóa idempotency không phải giấy phép truy cập

Giả sử một nhân viên đã gửi lệnh hợp lệ, kết quả đã commit và được lưu theo khóa idempotency. Sau đó quyền của nhân viên bị thu hồi; họ gửi lại cùng khóa.

Hệ thống không được chỉ tìm thấy khóa rồi trả toàn bộ kết quả nhạy cảm. Cần kiểm tra danh tính, phạm vi của bản ghi idempotency và quyền hiện tại đối với việc đọc lại kết quả theo hợp đồng sản phẩm. Một người khác biết khóa cũng không mặc nhiên có quyền đọc receipt.

Ngược lại, việc lần đọc lại bị từ chối không làm giao dịch trước đó bị rollback. Client và audit phải phân biệt: “không được phép nhận kết quả trong lần gọi này” với “lệnh trước chưa từng được thực hiện”. Không khuyến khích người dùng đổi khóa để thử lại một tác dụng phụ có thể đã xảy ra.

Không lưu một phản hồi lỗi quyền trong cache toàn cục chỉ theo URL hoặc khóa do client gửi. Phạm vi danh tính, tenant, hành động, nội dung lệnh và chính sách đọc lại cần được xem xét. Nếu có lưu kết quả từ chối theo idempotency, phải quy định rõ nó còn hiệu lực thế nào khi quyền thay đổi; không vô tình chặn vĩnh viễn một thao tác sau khi người dùng được cấp quyền hợp lệ.

### 8.3. Khi không biết giao dịch đã commit chưa

Nếu mất kết nối sau khi gửi lệnh, một lỗi mạng hoặc lỗi chung không đủ chứng minh thao tác chưa xảy ra. Cần tra cứu theo định danh lệnh trong phạm vi quyền cho phép, đối chiếu trạng thái và xử lý retry cùng ý định theo hợp đồng.

Không tự đổi một tình huống commit chưa xác định thành `AUTHORIZATION_DENIED` chỉ vì bước đọc kết quả sau đó gặp lỗi quyền. Hai sự kiện có thể cần được ghi nhận riêng với tương quan chung.

## 9. Cache, header và giao diện phải giữ cùng ngữ nghĩa

### 9.1. Không để cache làm lẫn quyền của các chủ thể

404 có thể được cache theo suy luận nếu không có chỉ dẫn phù hợp; xem [RFC 9110, mục 15.5.5](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.5). Vì vậy, không coi việc chọn 404 là đủ để bảo vệ phản hồi phụ thuộc danh tính.

Với API nghiệp vụ nhạy cảm trong các ví dụ, `Cache-Control: no-store` là lựa chọn để ngăn lưu phản hồi theo chính sách cache đã chỉ dẫn. Đồng thời phải cấu hình gateway, CDN và client phù hợp; một header không sửa được một tầng trung gian bị cấu hình bỏ qua nó.

Nếu sản phẩm chủ động cache dữ liệu hoặc quyết định quyền, cần thiết kế cache key, phạm vi chủ thể/tenant, thời gian sống và vô hiệu hóa khi thay đổi quyền. Không cache theo mỗi đường dẫn `/refunds/RFD-42` rồi dùng chung cho mọi người. Cũng không cho một phản hồi 404 của người không có quyền làm người có quyền nhận cùng kết quả từ cache dùng chung.

Các phản hồi thành công cũng phải được kiểm soát cache. Chỉ bảo vệ nhánh lỗi trong khi nội dung thành công bị chia sẻ sai vẫn làm lộ tài nguyên.

### 9.2. Header phải nhất quán với quyết định công khai

Khi che tài nguyên, không gắn header mô tả phiên bản, chủ sở hữu hay URL tải kết quả chỉ có ở nhánh đối tượng tồn tại. Mã request và các header vận hành không nên vô tình chứa ID nhạy cảm.

Nếu API gửi liên kết cho hành động tiếp theo, link đó không phải quyền mới và endpoint đích vẫn phải kiểm tra quyền. Không trả link “yêu cầu quản lý X phê duyệt” cho người không được biết quản lý hoặc tài nguyên tương ứng.

### 9.3. Giao diện phản ánh đúng cách phục hồi

Một giao diện có thể hiển thị “Bạn không được phép thực hiện thao tác này” cùng một hướng dẫn đã được sản phẩm cho phép, như liên hệ bộ phận hỗ trợ. Hướng dẫn không cần liệt kê toàn bộ vai trò, điều kiện chính sách và dữ liệu của chủ thể khác.

Không tự đăng xuất mọi người dùng khi gặp 403. Lỗi một hành động bị cấm không nhất thiết có nghĩa phiên xác thực đã hết hiệu lực. Ngược lại, không tiếp tục hiển thị kết quả cũ như thể thao tác mới đã thành công sau khi server từ chối.

Giao diện có thể ẩn hoặc vô hiệu hóa nút để giảm thao tác sai, nhưng server vẫn kiểm tra mỗi lời gọi cần bảo vệ. Client cũng không được suy rằng một object ID đoán được hoặc một nút từng hiển thị trước đó là bằng chứng có quyền hiện tại.

## 10. Batch, tác vụ nền và các đường vào khác

### 10.1. Batch phải định nghĩa tính toàn bộ hay từng phần

Với lệnh duyệt nhiều yêu cầu, sản phẩm có thể chọn:

- **Toàn bộ hoặc không có gì:** kiểm tra quyền và điều kiện của toàn bộ tập trong phạm vi nhất quán, chỉ commit khi mọi phần cần thiết đạt; khi bị chặn thì không có một phần đã âm thầm được duyệt.
- **Kết quả từng phần:** mỗi phần tử có kết quả rõ ràng theo hợp đồng; phần tử bị cấm không được thực hiện, các phần được chấp nhận có dấu vết và kết quả riêng.

Không xử lý ba phần tử rồi gặp phần tử thứ tư thiếu quyền, trả một lỗi chung khiến client hiểu toàn bộ đã rollback trong khi ba phần đầu vẫn tồn tại. Nếu có kết quả từng phần, không để thông báo một phần tử làm lộ việc đối tượng của tenant khác có thật. Chính sách 404 cho đối tượng không được phép biết cần áp dụng tương đương ở đây.

HTTP status của một envelope batch không tự diễn đạt kết quả mọi phần tử. Schema, ngữ nghĩa retry và định danh từng ý định cần đủ rõ để client không gửi lại phần đã thành công như một lệnh mới.

### 10.2. Job bất đồng bộ không được mất ngữ cảnh quyền

Khi nhận lệnh, server kiểm tra quyền tiếp nhận. Nếu chính sách còn yêu cầu quyền tại thời điểm thực thi, worker phải đánh giá tại mốc đó theo ngữ cảnh được lưu an toàn. Không thay người khởi tạo bằng tài khoản dịch vụ có toàn quyền rồi bỏ qua mọi hạn chế của hành động được ủy thác.

Cần phân biệt người khởi tạo, dịch vụ thực thi và căn cứ ủy quyền. Không lưu hoặc truyền token tùy tiện vào payload job chỉ để tái sử dụng về sau. Mô hình ủy quyền phải có phạm vi, thời hạn và cách kiểm tra phù hợp với sản phẩm.

Phản hồi “đã tiếp nhận job” không hứa công việc chắc chắn hoàn tất. Nếu job dừng vì không còn đủ quyền theo chính sách, trạng thái phải phản ánh điều đó và không được có tác dụng phụ trái quyền. Endpoint đọc trạng thái job cũng cần quyền theo đối tượng; biết `job_id` không cấp quyền đọc lý do lỗi hoặc dữ liệu kết quả.

### 10.3. Cùng một bảo đảm trên mọi đường thực thi

Cần kiểm tra các đường có thể thay đổi cùng dữ liệu: API chính, API quản trị, thao tác hàng loạt, import, job và công cụ hỗ trợ. Một đường khác không được bỏ qua quyền chỉ vì nó là “nội bộ”.

Một lỗi phổ biến là API chính trả 403 đúng, còn một endpoint đổi trạng thái hoặc một action được gọi bằng HTTP method khác vẫn thực hiện cùng thay đổi. Kiểm thử cần theo hành động nghiệp vụ và đối tượng, không chỉ theo một URL duy nhất.

## 11. Audit và quan sát lỗi quyền

Một bản ghi nội bộ hữu ích thường có chủ thể đã xác thực, hành động, phạm vi đối tượng hoặc tham chiếu được yêu cầu, quyết định, mã nguyên nhân, phiên bản chính sách, thời gian và request ID. Cần ghi đúng điều hệ thống thực sự biết.

Nếu một truy vấn giới hạn phạm vi không thấy đối tượng, có thể dùng lý do nội bộ `NOT_FOUND_OR_NOT_VISIBLE`; không tự khẳng định `TENANT_MISMATCH` khi chưa phân giải đối tượng. Với lỗi đánh giá, dùng trạng thái chưa xác định hoặc lỗi hạ tầng phù hợp thay vì tăng số quyết định `DENY` như thể đã kiểm tra xong.

Không ghi mật khẩu, token, cookie phiên hoặc toàn bộ request vào log lỗi quyền. Đầu vào như ID và lý do cần được giới hạn, mã hóa đúng định dạng log để không chèn dòng giả hoặc phá giao diện xem log. Kho log và trang điều tra cũng cần phân quyền theo mức nhạy cảm.

Nếu bản ghi từ chối nằm trong transaction rồi transaction rollback, bản ghi đó có thể bị rollback theo. Có thể cần đường ghi sự kiện an ninh riêng sau khi xác định kết quả, cùng cơ chế xử lý lỗi và giám sát. Không giả định một lời gọi `logger` bảo đảm lưu bền vững trong mọi tình huống tiến trình chết. Mức bảo đảm phải tương ứng nhu cầu của hệ thống.

Các số đo có thể phân loại lần từ chối theo action và mã nguyên nhân hữu hạn. Không đưa từng `user_id`, `refund_id` hoặc nội dung exception vào nhãn metric. Tỷ lệ từ chối tăng có thể do thử tấn công, tích hợp sai, thay đổi quyền hoặc lỗi phát hành; đó là tín hiệu điều tra, không tự chứng minh gian lận.

Phản hồi 404 để che tài nguyên không buộc mất mọi khả năng quan sát nội bộ. Tuy nhiên, người đọc dashboard hoặc log không mặc nhiên được biết tất cả tài nguyên mà người gọi bên ngoài không được biết. Phân quyền nguồn quan sát là một phần của thiết kế.

## 12. Kiểm thử cả phản hồi và điều không được xảy ra

Chỉ assert HTTP status là chưa đủ. Cần kiểm tra trạng thái cơ sở dữ liệu, outbox, lời gọi hệ thống bên ngoài, cache và dữ liệu công khai của phản hồi.

| Tình huống | Phản hồi mong muốn theo hợp đồng ví dụ | Bằng chứng cần kiểm tra thêm |
| --- | --- | --- |
| Thiếu hoặc không có thông tin xác thực hợp lệ | 401 với challenge phù hợp | Không chạm dữ liệu hoặc thực hiện hành động cần quyền |
| Có quyền xem nhưng thiếu quyền hành động | 403 với schema chung | Không đổi trạng thái, giá, số tiền hoặc người duyệt |
| ID có thật nhưng ngoài phạm vi được biết | 404 giống nhánh không tìm thấy | Body và header không lộ tenant, chủ sở hữu hay trạng thái |
| ID hoàn toàn không tồn tại | 404 theo cùng chính sách | Không có mã lỗi công khai phân biệt với nhánh phải che giấu |
| Body tự khai `actor_id`, tenant hoặc vai trò khác | Không dùng các trường đó làm danh tính/đặc quyền | Audit dùng principal đã xác thực; không có thay đổi vượt quyền |
| Người tạo cố tự phê duyệt | Từ chối theo quy tắc tách biệt trách nhiệm | Không có quyết định phê duyệt hợp lệ hoặc outbox thực thi được tạo |
| Có quyền nhưng trạng thái nghiệp vụ không cho phép | Lỗi nghiệp vụ đã quy định, không gán nhầm mọi trường hợp là lỗi quyền | Chỉ công khai trạng thái trong phạm vi được phép xem |
| Thành phần đánh giá quyền không sẵn sàng | Lỗi dịch vụ chung, không mặc định cho phép | Không có tác dụng phụ; dấu vết phân biệt chưa đánh giá được với đã từ chối |
| Exception bị bắt ở một lớp trung gian | Luồng vẫn phải dừng an toàn | Không tiếp tục thực thi sau nhánh log/catch |
| Quyền hoặc thuộc tính sở hữu thay đổi đồng thời | Kết quả theo mốc hiệu lực và cơ chế nhất quán đã thiết kế | Không dùng dữ liệu kiểm tra cũ trái hợp đồng tại lúc cập nhật |
| Quyền bị thu hồi trước lần replay | Không trả receipt nhạy cảm nếu không còn quyền đọc lại | Giao dịch cũ không bị thực hiện thêm; lịch sử commit không bị mô tả lại thành chưa xảy ra |
| Người khác biết cùng khóa idempotency | Không đọc được kết quả ngoài phạm vi | Khóa không hoạt động như quyền truy cập hoặc khóa cache dùng chung |
| Hai người dùng đi qua cache tới cùng URL | Mỗi người nhận kết quả theo ngữ cảnh của mình | Không chia sẻ nhầm phản hồi thành công hoặc phủ định |
| Batch có một phần tử thiếu quyền | Tính toàn bộ/từng phần đúng hợp đồng | Không có thay đổi âm thầm rồi trả lỗi như thể mọi phần đã rollback |
| Job đã nhận nhưng không đủ quyền tại mốc thực thi bắt buộc | Trạng thái job phản ánh việc dừng | Không gọi đối tác; đọc job vẫn kiểm tra quyền |
| Gọi đường quản trị, import hoặc method khác | Cùng bảo đảm quyền nghiệp vụ | Không có đường thay thế để bỏ qua bước bị chặn ở API chính |
| Đầu vào chứa xuống dòng hoặc nội dung HTML | Không chèn nội dung không tin cậy vào phản hồi/log một cách nguy hiểm | Không có log giả, script thực thi hoặc lỗi hiển thị làm lộ dữ liệu |

Với kiểm thử che giấu, cần so sánh nhóm ID có thật nhưng không được biết với nhóm ID không tồn tại. Chuẩn hóa các trường vô hại biến đổi như request ID trước khi so schema và nội dung; không chỉ kiểm tra hai status bằng nhau. Có thể đo nhiều lần để tìm khác biệt thời gian có hệ thống, đồng thời xét nhiễu mạng thay vì kết luận từ một lần đo.

Với kiểm thử tác dụng phụ, cần quan sát cả cổng gọi bên ngoài hoặc stub của nó. Một row không đổi chưa chứng minh không có email, lệnh thanh toán hoặc job đã được gửi. Với kiểm thử đồng thời, phải tạo tranh chấp ở mốc kiểm tra/cập nhật và xác nhận bảo đảm thực tế, không chỉ gọi tuần tự.

Các dữ liệu kiểm thử nên giả lập chủ thể, tenant, đối tượng và token; không dùng bí mật thật chỉ để chứng minh phản hồi không làm lộ chúng.

## 13. Các nguyên tắc cần giữ

Phản hồi lỗi quyền tốt phải khớp với hành vi thật và mức thông tin người gọi được phép biết. Việc lựa chọn status chỉ là một phần của hợp đồng đó.

1. Phân biệt thiếu xác thực, bị từ chối quyền, xung đột nghiệp vụ và lỗi đánh giá chính sách.
2. Chọn 403 hay phản hồi che giấu theo quyền biết đối tượng; giữ nhất quán body, mã lỗi, header và các endpoint liên quan.
3. Kiểm tra quyền trước tác dụng phụ, bảo vệ dữ liệu làm căn cứ và dừng luồng khi bị từ chối.
4. Dùng thông báo công khai tối thiểu nhưng giữ nguyên nhân nội bộ đủ chính xác để điều tra trong phạm vi được phân quyền.
5. Retry, cache, batch và job phải giữ cùng bảo đảm quyền; một khóa idempotency hoặc một ID đoán được không cấp quyền truy cập.
6. Kiểm thử cả điều client nhìn thấy lẫn điều không được xảy ra: không thay đổi trái quyền, không tạo lệnh thực thi và không làm lộ dữ liệu đối tượng.
