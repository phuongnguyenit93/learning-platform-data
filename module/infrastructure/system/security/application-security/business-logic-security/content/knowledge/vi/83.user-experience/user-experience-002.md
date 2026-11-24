# Clear rule explanation — Giải thích rõ quy tắc nghiệp vụ

## 1. Vì sao giải thích quy tắc là một phần của bảo mật?

Một hệ thống có thể kiểm tra quyền và trạng thái chính xác nhưng vẫn khiến người dùng liên tục thực hiện sai thao tác nếu giao diện chỉ báo “Không hợp lệ” hoặc “Có lỗi xảy ra”.

Người dùng không biết mình thiếu quyền, đang thao tác nhầm tenant, dùng dữ liệu cũ hay chỉ cần chờ một yêu cầu đang xử lý. Họ có thể bấm nhiều lần, gửi lại bằng một lệnh mới, nhờ người khác cho mượn tài khoản hoặc tìm một đường thao tác khác không đúng quy trình.

**Clear rule explanation** là việc giải thích quy tắc nghiệp vụ bằng ngôn ngữ phù hợp với người thực hiện, đúng với ngữ cảnh hiện tại và chỉ ra bước tiếp theo được phép.

Trong bảo mật logic nghiệp vụ, giải thích tốt giúp:

- Người dùng hiểu điều kiện trước khi đưa ra quyết định.
- Giảm lỗi vô ý khi sửa giá, phê duyệt hoặc gửi lệnh có tác động.
- Hướng người dùng đến luồng hợp lệ thay vì tìm cách vượt kiểm soát.
- Phân biệt từ chối nghiệp vụ với lỗi hệ thống và kết quả chưa xác định.
- Giữ nhất quán giữa điều giao diện nói và điều máy chủ thực thi.

Giải thích trên giao diện không thay thế business invariants, quyền theo đối tượng, transaction hoặc idempotency. Nút bị vô hiệu hóa và thông báo rõ ràng vẫn phải đi cùng việc máy chủ từ chối request không hợp lệ, kể cả request được gửi trực tiếp ngoài giao diện.

## 2. Tình huống xuyên suốt: giải thích quyền phê duyệt hoàn tiền

Giả sử ứng dụng có quy trình:

~~~text
Tạo yêu cầu hoàn tiền
    -> Chờ phê duyệt
    -> Đã phê duyệt
    -> Xử lý thanh toán
    -> Hoàn tất
~~~

Các quy tắc của ví dụ:

1. Chỉ hoàn tiền đang chờ phê duyệt mới được duyệt.
2. Người thực hiện phải có quyền trong đúng tenant và trên đúng đối tượng.
3. Người tạo không được tự phê duyệt yêu cầu của mình.
4. Số tiền phải nằm trong phạm vi thẩm quyền áp dụng.
5. Nếu dữ liệu ảnh hưởng quyết định đã thay đổi, người phê duyệt phải xem xét lại.
6. Gửi lại cùng một lệnh không được tạo thêm tác động ngoài quy định.

Người dùng u-17 tạo hoàn tiền R-420 rồi mở màn hình duyệt.

Thông báo quá ngắn:

~~~text
Bạn không thể thực hiện thao tác này.
~~~

Thông báo rõ hơn khi người đó có quyền xem quy tắc và yêu cầu:

~~~text
Bạn là người tạo yêu cầu này nên không thể tự phê duyệt.

Cần một người phê duyệt độc lập có thẩm quyền phù hợp.
Bạn có thể gửi yêu cầu phân công người phê duyệt.
~~~

Bước “gửi yêu cầu phân công” chỉ được hiển thị nếu hệ thống thật sự có luồng đó và người dùng được phép sử dụng.

Không hướng dẫn “đăng nhập bằng tài khoản khác” hoặc “nhờ người khác cho mượn quyền”. Quy tắc tách biệt nhiệm vụ liên quan đến người thao tác thực tế, không chỉ hai chuỗi user ID khác nhau.

## 3. Năm thành phần của một lời giải thích có ích

Một lời giải thích thường cần trả lời năm câu hỏi.

| Thành phần | Câu hỏi của người dùng | Ví dụ |
|---|---|---|
| Phạm vi | Quy tắc áp dụng cho thao tác và đối tượng nào? | Việc phê duyệt yêu cầu hoàn tiền đang mở |
| Điều kiện | Tôi cần đáp ứng điều gì? | Người phê duyệt phải khác người tạo và có thẩm quyền phù hợp |
| Kết quả hiện tại | Hệ thống đang cho phép, từ chối hay chưa xác định? | Chưa thể phê duyệt trong ngữ cảnh hiện tại |
| Lý do được phép công khai | Điều kiện nào chưa đáp ứng? | Bạn là người tạo yêu cầu |
| Bước tiếp theo | Tôi có thể làm gì đúng quy trình? | Gửi yêu cầu phân công người phê duyệt độc lập |

Không phải lúc nào cũng được công khai toàn bộ lý do nội bộ. Nhưng ngay cả thông báo giới hạn chi tiết cũng nên nói đúng trạng thái và chỉ ra cách xử lý hợp lệ.

### 3.1. Nói rõ điều kiện thay vì chỉ nêu khẩu hiệu

“Tuân thủ chính sách phê duyệt” khó giúp người dùng hành động. “Người tạo không được tự phê duyệt yêu cầu” mô tả được điều kiện cụ thể.

Nếu điều kiện có nhiều phần, có thể chia thành các mục ngắn:

~~~text
Để phê duyệt, cần:
- Yêu cầu còn ở trạng thái chờ phê duyệt.
- Bạn có quyền phê duyệt yêu cầu này.
- Bạn không phải người tạo yêu cầu.
- Số tiền nằm trong phạm vi thẩm quyền của bạn.
~~~

Danh sách này chỉ nên bao gồm các điều kiện phù hợp để công khai cho người xem. Nó không phải danh sách toàn bộ logic phát hiện gian lận bên trong hệ thống.

### 3.2. Phân biệt quy tắc với kết quả đánh giá

Quy tắc: “Người tạo không được tự phê duyệt”.

Kết quả đánh giá: “Bạn là người tạo yêu cầu này, vì vậy không thể phê duyệt”.

Thông báo chỉ chứa quy tắc chung có thể khiến người dùng không hiểu nó liên quan gì đến mình. Thông báo chỉ chứa kết quả mà không có điều kiện lại có thể trông tùy tiện.

Khi được phép, kết hợp cả hai với lượng thông tin vừa đủ.

### 3.3. Không đổ lỗi hoặc suy đoán ý định

Một yêu cầu sửa giá có thể bị từ chối vì dữ liệu cũ, không nhất thiết do cố tình gian lận. Không dùng thông điệp “Bạn đang cố sửa giá trái phép” nếu hệ thống chỉ biết giá client khác giá hiện tại.

Có thể nói:

~~~text
Giá hiện tại khác với giá bạn đã xem.
Hãy tải lại đơn hàng và kiểm tra giá trước khi tiếp tục.
~~~

Thông điệp mô tả dữ kiện và hướng xử lý, không kết luận về ý định của người dùng.

## 4. Giải thích ở đúng thời điểm trong hành trình

### 4.1. Trước khi nhập hoặc bắt đầu thao tác

Những điều kiện người dùng có thể chuẩn bị nên xuất hiện sớm:

- Ai có thể gửi hoặc phê duyệt.
- Trường dữ liệu nào bắt buộc.
- Giá trị nhập là số tiền, phần trăm hay số lượng.
- Khi nào cần người phê duyệt độc lập.
- Tác động nào sẽ xảy ra khi xác nhận.

Ví dụ, nếu yêu cầu thay đổi giá phải có lý do, hãy hiển thị điều đó cùng trường nhập. Không chờ đến cuối mới báo “thiếu lý do” sau khi người dùng đã hoàn thành toàn bộ quy trình.

### 4.2. Trong khi nhập

Giải thích nên gần dữ liệu liên quan và dựa trên quy tắc thật.

~~~text
Số tiền hoàn
Nhập bằng VND. Số tiền không được lớn hơn phần còn có thể hoàn của giao dịch.
~~~

Nếu được phép hiển thị giá trị còn có thể hoàn, có thể bổ sung số hiện tại. Tuy nhiên, giá trị này là một snapshot; máy chủ vẫn phải kiểm tra lại khi thực thi.

Không dùng một bản tính ở trình duyệt làm nguồn quyết định cuối cùng cho số tiền, chiết khấu hoặc quyền.

### 4.3. Trước khi xác nhận tác động

Tóm tắt những dữ kiện quyết định cần thiết:

~~~text
Phê duyệt hoàn tiền 750.000 VND cho yêu cầu R-420.

Hãy kiểm tra số tiền và thông tin người nhận trước khi xác nhận.
Sau khi phê duyệt, yêu cầu sẽ được chuyển sang bước xử lý thanh toán.
~~~

Chỉ dùng câu cuối nếu quy trình thực tế có bước chuyển đó. Không hứa “tiền sẽ về ngay” khi hệ thống chỉ ghi nhận một quyết định phê duyệt.

Nếu dữ liệu đã đổi từ lần xem trước, phải làm rõ sự thay đổi và yêu cầu xem xét lại theo mức độ nhạy cảm của hành động.

### 4.4. Khi bị từ chối

Thông báo cần phân biệt:

- Quy tắc nghiệp vụ chưa được đáp ứng.
- Người dùng không có quyền.
- Trạng thái hoặc dữ liệu đã thay đổi.
- Hệ thống chưa đánh giá được điều kiện.
- Lệnh trước đang xử lý hoặc chưa biết kết quả.

Không gom các tình huống này vào “Thử lại sau”. Có tình huống retry không thay đổi gì; có tình huống retry bằng lệnh mới tạo rủi ro xử lý trùng.

### 4.5. Sau khi gửi

Cần tách “đã gửi”, “đang xử lý” và “đã hoàn tất”.

~~~text
Đã tiếp nhận yêu cầu phê duyệt.
Bạn có thể theo dõi trạng thái tại mục Yêu cầu của tôi.
~~~

Thông điệp này khác với:

~~~text
Yêu cầu đã được phê duyệt.
~~~

Mỗi câu phải có bằng chứng tương ứng từ hệ thống. Không suy ra thành công chỉ vì nút đã được bấm hoặc request đã rời trình duyệt.

## 5. Máy chủ là nguồn quyết định; giao diện là nơi giải thích

Một kiến trúc có thể tách thành:

~~~mermaid
flowchart TD
    A["Danh tính, tenant và đối tượng đã xác minh"] --> B["Policy và business invariants ở máy chủ"]
    B --> C["Kết quả đánh giá nội bộ"]
    C --> D["Ánh xạ mức chi tiết theo quyền người xem"]
    D --> E["Mã công khai, tham số an toàn, bước tiếp theo"]
    E --> F["Giao diện trình bày lời giải thích"]
    F --> G["Người dùng gửi lệnh"]
    G --> H["Máy chủ kiểm tra lại và thực thi nhất quán"]
    H --> I["Kết quả thực tế và hướng phục hồi"]
~~~

### 5.1. Tránh hai bộ quy tắc độc lập

Nếu frontend tự định nghĩa “người có role MANAGER luôn được duyệt”, trong khi backend còn kiểm tra tenant, hạn mức, đại diện và người tạo, thông báo của frontend sẽ sai trong nhiều trường hợp.

Có thể dùng cùng nguồn định nghĩa hoặc cùng cơ chế policy để phục vụ giải thích và thực thi. Một số validation đơn giản có thể xuất hiện ở cả client và server để hỗ trợ nhập liệu, nhưng máy chủ vẫn phải là nơi thực thi có thẩm quyền.

Không sao chép một phần policy thành nhiều chuỗi điều kiện rải rác rồi mặc định chúng luôn đồng bộ.

### 5.2. Kết quả xem trước không cấp quyền

API có thể trả allowedActions hoặc thông tin khả dụng để giúp giao diện. Dữ liệu đó không phải credential hay quyền có hiệu lực vĩnh viễn.

Giữa thời điểm xem trước và thực thi:

- Quyền có thể bị thu hồi.
- Đối tượng có thể đổi trạng thái.
- Số tiền có thể thay đổi.
- Tenant hoặc chế độ đại diện có thể đổi.
- Một lệnh khác có thể đã hoàn tất.

Vì vậy, nút đang hiển thị “có thể duyệt” không có nghĩa request cuối chắc chắn được chấp nhận. Cần diễn đạt khả dụng theo dữ liệu hiện tại và xử lý thay đổi một cách rõ ràng.

### 5.3. Kiểm tra khả dụng không được tạo tác động nghiệp vụ

Một endpoint xem trước không nên tiêu thụ hạn mức, phê duyệt hoặc gửi lệnh thanh toán chỉ để trả lời “có thể hay không”.

Nó cũng cần kiểm tra quyền theo đối tượng, giới hạn dữ liệu công khai và kiểm soát lượng truy vấn phù hợp. Nếu không, chức năng giải thích có thể trở thành công cụ dò sự tồn tại, quyền hoặc ngưỡng kiểm soát.

## 6. Hợp đồng dữ liệu để lời giải thích nhất quán

Một response minh họa sau khi máy chủ đã xác minh quyền xem yêu cầu:

~~~json
{
  "action": "refund.approve",
  "eligibility": "NOT_ALLOWED",
  "reasonCode": "SELF_APPROVAL_NOT_ALLOWED",
  "messageKey": "refund.approval.independent_reviewer_required",
  "messageParameters": {},
  "allowedNextActions": [
    "REQUEST_REVIEWER_ASSIGNMENT"
  ],
  "evaluatedAt": "2026-11-22T08:15:30Z",
  "resourceVersion": 8
}
~~~

Đây là hợp đồng ứng dụng tự định nghĩa. Các trường phục vụ những mục đích khác nhau:

| Trường | Vai trò |
|---|---|
| action | Hành động cụ thể đang được giải thích |
| eligibility | Trạng thái đánh giá, không phải kết quả commit |
| reasonCode | Mã công khai ổn định để client và hệ thống hỗ trợ hiểu tình huống |
| messageKey | Khóa chọn nội dung đã được biên soạn và bản địa hóa |
| messageParameters | Dữ liệu được phép dùng trong thông điệp |
| allowedNextActions | Những bước tiếp theo phù hợp được máy chủ xác định |
| evaluatedAt | Thời điểm đánh giá để theo dõi độ mới |
| resourceVersion | Liên kết với snapshot đối tượng đã đánh giá |

### 6.1. Phân biệt ba trạng thái đánh giá

Một mô hình có thể dùng:

~~~text
ALLOWED
NOT_ALLOWED
UNAVAILABLE
~~~

UNAVAILABLE biểu đạt rằng hệ thống chưa đánh giá được điều kiện. Không biến lỗi truy cập policy thành thông điệp “Bạn không đủ điều kiện” nếu chưa có quyết định như vậy.

Ngược lại, NOT_ALLOWED là kết quả từ chối đã được đánh giá. Client không nên trình bày nó như lỗi mạng rồi retry tự động.

Kết quả thực thi sau khi gửi lệnh cần mô hình riêng, vì ALLOWED không đồng nghĩa đã commit.

### 6.2. Mã công khai khác lý do nội bộ

Một reason nội bộ có thể chứa tên rule, dữ kiện nhạy cảm hoặc dấu hiệu phát hiện lạm dụng. Cần ánh xạ nó sang mã công khai theo quyền và mục đích sử dụng.

Không gửi toàn bộ decision object của policy engine ra trình duyệt rồi trông cậy frontend ẩn bớt. Dữ liệu đã gửi vẫn có thể bị đọc qua công cụ mạng.

Các thông tin kỹ thuật như resourceVersion phục vụ xử lý nhất quán, không cần hiện thành thông báo “Lỗi version 8”. Giao diện nên nói “Yêu cầu đã thay đổi” và hướng người dùng xem lại dữ liệu.

### 6.3. Bước tiếp theo cũng phải có quyền

allowedNextActions không nên chỉ là một danh sách gợi ý chung. Nếu người dùng không được phân công người duyệt, đừng hiển thị nút thực hiện thao tác đó như thể chắc chắn hợp lệ.

Khi bấm bước tiếp theo, máy chủ vẫn kiểm tra lại quyền và trạng thái. Metadata hướng dẫn không phải quyền thực thi.

Client nên ánh xạ action ID từ tập đã biết sang giao diện. Không thực thi một URL hoặc đoạn script tùy ý nằm trong thông điệp lỗi.

## 7. Ví dụ ánh xạ giải thích ở tầng Java

Mã dưới đây là minh họa cách phân loại nội dung công khai, không phải một thư viện hoặc triển khai hoàn chỉnh.

~~~java
enum Eligibility {
    ALLOWED,
    NOT_ALLOWED,
    UNAVAILABLE
}

enum NextAction {
    REQUEST_REVIEWER_ASSIGNMENT,
    REFRESH_AND_REVIEW,
    RETRY_ELIGIBILITY_CHECK,
    CONTACT_SUPPORT
}

record PublicRuleExplanation(
    Eligibility eligibility,
    String reasonCode,
    String messageKey,
    Set<NextAction> nextActions
) {}
~~~

Một hàm ánh xạ có thể được tổ chức như sau:

~~~java
PublicRuleExplanation explain(
        InternalDecision decision,
        VerifiedViewer viewer) {

    // Hợp đồng: đối tượng đã được kiểm tra quyền xem.
    // Không truyền decision chi tiết trái quyền vào hàm này.

    if (decision.evaluationUnavailable()) {
        return explanations.unavailable(
            "RULE_CHECK_UNAVAILABLE",
            "rules.check_unavailable",
            Set.of(NextAction.RETRY_ELIGIBILITY_CHECK));
    }

    if (decision.allowed()) {
        return explanations.allowed(
            "ACTION_CURRENTLY_AVAILABLE",
            "rules.action_available");
    }

    if (decision.reason() == InternalReason.SELF_APPROVAL) {
        Set<NextAction> actions = viewer.canRequestReviewerAssignment()
            ? Set.of(NextAction.REQUEST_REVIEWER_ASSIGNMENT)
            : Set.of();

        return explanations.denied(
            "SELF_APPROVAL_NOT_ALLOWED",
            "refund.approval.independent_reviewer_required",
            actions);
    }

    if (decision.reason() == InternalReason.RESOURCE_CHANGED) {
        return explanations.denied(
            "RESOURCE_REVIEW_REQUIRED",
            "refund.review_updated_information",
            Set.of(NextAction.REFRESH_AND_REVIEW));
    }

    return explanations.denied(
        "ACTION_NOT_AVAILABLE",
        "rules.action_not_available",
        viewer.canUseSupportFlow()
            ? Set.of(NextAction.CONTACT_SUPPORT)
            : Set.of());
}
~~~

Các kiểu InternalDecision, VerifiedViewer và explanations là hợp đồng minh họa của ứng dụng.

Những điểm cần giữ:

- Viewer đến từ ngữ cảnh đã xác minh, không từ role do client tự gửi.
- Không cho client tự chọn reason để nhận một câu hướng dẫn có lợi.
- Nhánh chung không trả chi tiết nội bộ ngoài quyền.
- RETRY_ELIGIBILITY_CHECK là thử đánh giá lại điều kiện, không tự gửi lại lệnh có tác động.
- Quyết định cuối cùng vẫn được kiểm tra khi thực thi.
- Một thao tác chưa đánh giá được không bị mô tả sai thành vi phạm của người dùng.

Nếu người gọi không được xem đối tượng, xử lý theo hợp đồng tài nguyên và quyền trước khi dựng các giải thích chi tiết trong ví dụ. Không dùng thông điệp này để xác nhận đối tượng trái quyền có tồn tại.

## 8. Giải thích chính xác phạm vi, số tiền và thời gian

### 8.1. Quyền phụ thuộc ngữ cảnh

“Bạn có quyền phê duyệt” có thể bị hiểu là có quyền ở mọi tenant và mọi mức tiền.

Khi được phép công khai, có thể nói:

~~~text
Bạn có thể phê duyệt yêu cầu này trong đơn vị đang chọn,
nếu dữ liệu và trạng thái không thay đổi trước khi xác nhận.
~~~

Cần giúp người dùng nhận biết đơn vị hoặc tài khoản đang thao tác. Với chế độ đại diện, phải phân biệt người đang thao tác và chủ thể được đại diện, không khiến nhân viên tưởng mình đang dùng quyền trực tiếp của khách hàng cho mọi hành động.

Không hiển thị tên tenant hoặc thông tin khách hàng chỉ từ ID client cung cấp trước khi kiểm tra quyền.

### 8.2. Hạn mức phải nói rõ cách áp dụng

Một thông báo “Vượt hạn mức” có thể thiếu nhiều thông tin:

- Hạn mức cho mỗi giao dịch hay tổng trong một khoảng thời gian?
- Tính trên số tiền gốc, số tiền còn có thể hoàn hay tổng đã sử dụng?
- Đơn vị tiền tệ nào?
- Có bao gồm yêu cầu đang chờ không?
- Người dùng được phép biết giá trị cụ thể đến mức nào?

Nếu đây là hạn mức nghiệp vụ công khai cho người dùng đó, có thể giải thích đúng phạm vi. Nếu là ngưỡng phát hiện lạm dụng nhạy cảm, không công khai chi tiết giúp né kiểm soát.

Không gợi ý chia nhỏ giao dịch để lách hạn mức. Nếu quy trình có bước xin phê duyệt ở cấp phù hợp, hướng đến bước đó.

### 8.3. Hiển thị đơn vị và biên rõ ràng

“Số tiền tối đa 750.000 VND” cần nhất quán với việc có chấp nhận đúng 750.000 hay chỉ chấp nhận nhỏ hơn.

Quy tắc tính toán dùng đơn vị chuẩn ở máy chủ; giao diện định dạng theo ngôn ngữ người dùng. Với VND trong các ví dụ này, giá trị 750000 được hiển thị là 750.000 VND.

Không lấy chuỗi đã định dạng có dấu phân cách để làm nguồn tính toán nghiệp vụ. Khi hỗ trợ nhiều tiền tệ, cần giữ rõ currency và quy ước đơn vị.

### 8.4. Thời hạn cần tránh mơ hồ

Nếu yêu cầu phải xử lý trước một thời điểm, nên ghi ngày giờ và múi giờ phù hợp với người sử dụng.

“Còn 5 phút” có thể hỗ trợ trải nghiệm nhưng không thay thế thời điểm có thẩm quyền ở máy chủ. Đồng hồ trình duyệt sai không được kéo dài quyền hoặc làm lệnh hợp lệ sau hạn.

Không hứa thao tác sẽ được chấp nhận chỉ vì countdown trên màn hình chưa về 0. Khi thời gian hết hoặc dữ liệu đến trễ, cần giải thích đúng điều kiện hiện tại và bước tiếp theo.

## 9. Mức độ minh bạch phải đi cùng giới hạn tiết lộ

### 9.1. Có thể giải thích cụ thể khi đó là quy tắc người dùng cần biết

Ví dụ:

- Người tạo không tự phê duyệt.
- Lý do thay đổi giá là bắt buộc.
- Yêu cầu đã hủy không thể được duyệt.
- Dữ liệu đã thay đổi nên cần xem lại.

Những giải thích này giúp người dùng làm đúng quy trình.

### 9.2. Không công khai cơ chế kiểm soát nhạy cảm

Một bộ kiểm soát có thể xét mẫu hành vi, quan hệ giữa tài khoản hoặc nhiều tín hiệu nội bộ. Giải thích đầy đủ từng ngưỡng có thể trở thành hướng dẫn né phát hiện.

Trong trường hợp cần giới hạn, có thể dùng thông điệp trung thực:

~~~text
Hiện chưa thể thực hiện thao tác này.
Bạn có thể liên hệ bộ phận hỗ trợ qua luồng được cung cấp để kiểm tra.
~~~

Chỉ nói “Yêu cầu đang được kiểm tra bổ sung” nếu hệ thống thật sự đã tiếp nhận và đưa yêu cầu vào quy trình đó. Không dùng một câu nghe dễ chịu nhưng mô tả sai trạng thái.

Không gắn nhãn người dùng là gian lận từ một tín hiệu chưa được xác minh.

### 9.3. Không tiết lộ sự tồn tại ngoài quyền

Người gọi không có quyền xem một hoàn tiền không nên nhận:

~~~text
Yêu cầu này đã được quản lý của tenant khác phê duyệt.
~~~

Cần dùng phản hồi theo hợp đồng che giấu hoặc giới hạn tài nguyên của hệ thống. Sự rõ ràng ở đây là giúp người dùng hiểu phạm vi truy cập và kênh hỗ trợ phù hợp, không phải cung cấp mọi dữ kiện của đối tượng.

### 9.4. Giải thích mở rộng theo quyền

Có thể có nhiều mức nội dung:

- Người dùng cuối thấy điều kiện và bước tiếp theo cần thiết.
- Người phê duyệt được phép thấy dữ kiện quyết định phù hợp.
- Nhân viên hỗ trợ có quyền thấy mã tra cứu và lịch sử giới hạn.
- Nhóm điều tra có thẩm quyền xem bằng chứng chi tiết hơn.

Không lấy màn hình của nhóm điều tra làm mẫu thông báo cho mọi người. Đồng thời, việc người hỗ trợ biết mã tra cứu không tự cấp quyền xem mọi hồ sơ.

## 10. Thiết kế giao diện để lời giải thích được tìm thấy

### 10.1. Không chỉ vô hiệu hóa nút

Một nút mờ không cho biết nguyên nhân. Người dùng có thể nghĩ ứng dụng bị lỗi hoặc chưa tải xong.

Nên có lời giải thích nhìn thấy được gần thao tác hoặc trong phần tóm tắt điều kiện. Không đặt thông tin duy nhất trong tooltip chỉ xuất hiện khi hover; người dùng bàn phím hoặc thiết bị chạm có thể không truy cập được theo cách đó.

Ví dụ:

~~~text
[Phê duyệt] — hiện không khả dụng

Bạn là người tạo yêu cầu nên cần người phê duyệt độc lập.
[Gửi yêu cầu phân công]
~~~

Việc hiển thị hoặc vô hiệu hóa nút là hỗ trợ trải nghiệm. Máy chủ vẫn kiểm tra quyền nếu có request gửi trực tiếp.

### 10.2. Không chỉ dùng màu hoặc biểu tượng

Màu đỏ hoặc biểu tượng khóa không đủ để diễn đạt một quy tắc. Cần văn bản nêu ý nghĩa.

Khi nội dung thay đổi sau một hành động, giao diện nên giúp người dùng nhận ra thông báo và liên hệ nó với trường hoặc thao tác liên quan. Với biểu mẫu dài, có thể có tóm tắt lỗi và liên kết tới vị trí cần xem.

Không làm mất dữ liệu nhập hợp lệ chỉ vì một điều kiện khác bị từ chối. Nhưng cũng không giữ lại nội dung nhạy cảm ngoài nhu cầu hoặc tự gửi lại dữ liệu cũ sau khi ngữ cảnh đổi.

### 10.3. Bản địa hóa giữ nguyên ý nghĩa

Code nghiệp vụ nên ổn định; thông điệp được biên soạn cho ngôn ngữ người dùng. Không yêu cầu client phân tích câu tiếng Việt để quyết định retry hay đổi bước.

Cần chú ý:

- Đơn vị tiền tệ và cách viết số.
- Ngày giờ và múi giờ.
- Các từ “đã”, “đang”, “chưa” phản ánh trạng thái khác nhau.
- Thuật ngữ thống nhất như “người tạo”, “người phê duyệt”, “yêu cầu”.
- Văn phong rõ ràng, tránh tên bảng, exception hoặc nội dung kỹ thuật không cần thiết.

### 10.4. Dữ liệu động cần được trình bày an toàn

Tên người nhận, ghi chú hoặc tên đơn vị có thể chứa dữ liệu từ người dùng. Khi đưa vào thông điệp, phải xử lý hiển thị theo ngữ cảnh, không chèn như HTML tin cậy.

Không dùng raw exception message làm nội dung giao diện. Ngoài nguy cơ lộ nội bộ, nó thường khó hiểu và không có bước tiếp theo hữu ích.

## 11. Hướng dẫn phục hồi mà không bỏ qua quy tắc

### 11.1. Dữ liệu thay đổi

Thông điệp nên cho biết cần xem lại:

~~~text
Thông tin yêu cầu đã thay đổi kể từ lần bạn mở màn hình.
Hãy tải lại và kiểm tra số tiền, người nhận trước khi xác nhận lại.
~~~

Client không tự lấy version mới rồi duyệt trong nền. Việc người dùng đã đồng ý với dữ liệu cũ không mặc nhiên áp dụng cho dữ liệu mới.

### 11.2. Lệnh đang xử lý

Nếu đã có command được tiếp nhận bền vững:

~~~text
Yêu cầu này đang được xử lý.
Hãy theo dõi kết quả tại đây thay vì tạo yêu cầu mới.
~~~

Có thể cung cấp đường theo dõi trong phạm vi quyền. Không tạo key mới chỉ để vượt tình trạng đang xử lý.

### 11.3. Chưa xác định kết quả

Sau timeout, hệ thống có thể chưa biết tác động cuối cùng:

~~~text
Chưa xác định được kết quả của lần gửi vừa rồi.
Hãy kiểm tra trạng thái yêu cầu trước khi thực hiện lại.
~~~

Không nói “Gửi thất bại, bấm lại” nếu chưa biết lệnh đã tạo tác động hay chưa. Idempotency và đường tra cứu phải hỗ trợ lời hướng dẫn này.

### 11.4. Thiếu thẩm quyền

Nếu có luồng hợp lệ:

~~~text
Yêu cầu này cần người phê duyệt có thẩm quyền phù hợp.
Bạn có thể gửi yêu cầu phân công theo quy trình.
~~~

Không hướng dẫn đổi vai trò, mượn tài khoản hoặc chia nhỏ số tiền. Một bước tiếp theo rõ ràng phải giữ nguyên mục đích của invariant.

### 11.5. Hệ thống chưa kiểm tra được quy tắc

Nếu đánh giá khả dụng bị lỗi trước khi có lệnh:

~~~text
Hiện chưa kiểm tra được điều kiện phê duyệt.
Bạn có thể thử kiểm tra lại sau.
~~~

Đừng đổ lỗi cho người dùng hoặc khẳng định họ không đủ điều kiện. Cần tách hành động kiểm tra lại khỏi việc gửi một lệnh có tác động.

## 12. So sánh cách viết thông điệp

| Cách viết thiếu rõ ràng | Cách viết phù hợp hơn khi dữ kiện và quyền cho phép |
|---|---|
| Không hợp lệ | Bạn là người tạo yêu cầu nên không thể tự phê duyệt |
| Forbidden | Tài khoản hiện tại không được thực hiện thao tác này trong phạm vi đang chọn |
| Vượt hạn mức | Số tiền vượt phạm vi phê duyệt của bạn; cần người có thẩm quyền phù hợp |
| Có lỗi, thử lại | Thông tin đã thay đổi; hãy tải lại và xem xét trước khi gửi lệnh mới |
| Thành công | Đã tiếp nhận yêu cầu; quá trình xử lý chưa hoàn tất |
| Gửi thất bại | Chưa xác định kết quả; hãy kiểm tra trạng thái trước khi thực hiện lại |
| Bạn đang sửa giá trái phép | Giá hiện tại khác với giá đã xem; hãy tải lại và kiểm tra |
| Đổi tài khoản để duyệt | Cần người phê duyệt độc lập thực hiện theo quy trình |
| Liên hệ admin | Liên hệ qua luồng hỗ trợ được cung cấp và sử dụng mã tra cứu nếu có |

Cột bên phải không phải mẫu để áp dụng máy móc. “Đã tiếp nhận” chỉ đúng khi đã tiếp nhận; “thông tin đã thay đổi” chỉ đúng khi đã xác định điều đó. Lời giải thích phải bắt đầu từ kết quả thật, không chọn một câu dễ nghe rồi gán cho mọi lỗi.

## 13. Kiểm thử tính đúng và mức dễ hiểu

Các tình huống dưới đây dùng để thiết kế kiểm thử cho một triển khai thực tế; mã minh họa trong bài chưa phải triển khai đã được chạy.

| Tình huống | Điều cần xác minh |
|---|---|
| Người tạo mở màn hình duyệt | Lý do độc lập được giải thích đúng, máy chủ vẫn chặn request trực tiếp |
| Người ngoài tenant đổi ID | Không lộ sự tồn tại, trạng thái hoặc lý do chi tiết của đối tượng |
| Quyền bị thu hồi sau khi xem trước | Giao diện xử lý từ chối cuối cùng, không tin allowedActions cũ |
| Số tiền thay đổi trước xác nhận | Yêu cầu xem lại dữ liệu mới, không tự nâng version rồi duyệt |
| Không truy cập được policy | Hiển thị chưa đánh giá được, không kết luận người dùng sai quy tắc |
| Lệnh đã tiếp nhận nhưng còn chạy | Không trình bày là hoàn tất hoặc khuyến khích tạo lệnh mới |
| Response mất sau commit | Hướng tra cứu và replay đúng lệnh, không tạo tác động thứ hai |
| Cùng lệnh được gửi nhiều lần | Thông điệp không làm người dùng tưởng có nhiều lần phê duyệt |
| Người đang thao tác qua đại diện | Hiển thị đúng ngữ cảnh, không đánh đồng quyền đại diện với mọi quyền |
| Tên người nhận chứa nội dung đặc biệt | Nội dung động được hiển thị an toàn, không thành mã thực thi |
| Người dùng chỉ dùng bàn phím hoặc thiết bị chạm | Tìm được lý do, không phụ thuộc duy nhất vào hover |
| Giao diện thay đổi trạng thái động | Thông báo mới được nhận biết và liên hệ đúng thao tác |
| Ngôn ngữ hoặc múi giờ thay đổi | Số tiền, thời hạn và ý nghĩa trạng thái vẫn nhất quán |
| Không có quyền phân công hoặc hỗ trợ | Không hiển thị bước tiếp theo mà người dùng không thể dùng |
| Lý do nội bộ chứa tín hiệu nhạy cảm | Chỉ trả mã và mức giải thích công khai phù hợp |
| Client sửa reasonCode hoặc allowedActions | Không thay đổi quyết định thực thi ở máy chủ |

Ngoài kiểm thử chức năng, có thể kiểm tra khả năng hiểu bằng những câu hỏi cụ thể:

- Người dùng có nói lại được vì sao thao tác chưa thể thực hiện không?
- Họ có biết bước tiếp theo hợp lệ là gì không?
- Họ có phân biệt yêu cầu đã tiếp nhận với đã hoàn tất không?
- Họ có hiểu cần xem lại dữ liệu trước khi xác nhận lại không?

Không chỉ hỏi “Thông báo có dễ hiểu không?”. Quan sát lựa chọn tiếp theo sẽ cho thấy thông điệp có thực sự dẫn đến hành vi đúng hay không.

### 13.1. Đo hiệu quả mà không nới lỏng kiểm soát

Có thể theo dõi số lần lặp lại cùng lỗi, số yêu cầu hỗ trợ về một quy tắc hoặc mức hoàn thành bước hợp lệ sau thông báo.

Các chỉ số này cần có bối cảnh. Tỷ lệ từ chối giảm có thể do giải thích tốt hơn, nhưng cũng có thể do kiểm soát bị lỗi hoặc người dùng bỏ cuộc. Không tối ưu trải nghiệm bằng cách âm thầm bỏ invariant.

Metric nên dùng mã lý do và action có tập giá trị giới hạn. Không đưa user ID, request ID hoặc toàn bộ thông điệp có dữ liệu động vào nhãn metric.

## 14. Checklist thiết kế lời giải thích quy tắc

Trước khi đưa lời giải thích vào luồng sửa giá, phê duyệt, chuyển tiền hoặc thay đổi quyền, hãy xác định:

1. Quy tắc nào đang áp dụng và người dùng có cần biết trước khi thao tác không?
2. Kết quả là được phép, bị từ chối hay chưa đánh giá được?
3. Thông điệp có nói đúng hành động, đối tượng, số tiền và ngữ cảnh hiện tại không?
4. Mức chi tiết có phù hợp quyền xem và không tiết lộ cơ chế kiểm soát nhạy cảm không?
5. Bước tiếp theo có thật, có quyền thực hiện và giữ nguyên mục đích của quy tắc không?
6. Giải thích xem trước có được tách khỏi quyết định thực thi cuối cùng không?
7. Các thay đổi về version, quyền, tenant và đại diện có được xử lý rõ ràng không?
8. Người dùng có tìm được lý do mà không phụ thuộc duy nhất vào màu, biểu tượng hoặc tooltip không?
9. Nội dung động, bản địa hóa và cách viết trạng thái có an toàn, nhất quán không?
10. Kiểm thử có đối chiếu thông điệp với kết quả nghiệp vụ và hành vi phục hồi thực tế không?

Giải thích rõ quy tắc giúp người dùng đưa ra quyết định đúng và đi theo quy trình hợp lệ. Giá trị đó chỉ được giữ khi lời hướng dẫn phản ánh đúng policy, quyền theo đối tượng, state machine và kết quả thực tế mà máy chủ xác nhận.
