# Confirmation for risky action: Xác nhận trước hành động có rủi ro

## 1. Mục tiêu và phạm vi

**Confirmation for risky action** là bước giúp người dùng xem lại một hành động quan trọng, hiểu đối tượng và hậu quả của nó, rồi chủ động quyết định có tiếp tục hay không. Ví dụ gồm phê duyệt hoàn tiền, thay đổi giá ngoại lệ, thu hồi quyền quản trị hoặc xóa một tập dữ liệu lớn.

Trong chương **User Experience** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, bước xác nhận phải gắn với business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Một hộp thoại đẹp hoặc một trường `confirmed=true` không ngăn được caller gọi thẳng API, thay payload hoặc gửi yêu cầu trùng.

Mục tiêu là kết hợp trải nghiệm rõ ràng với quyết định backend đúng: người dùng xem đúng điều sắp làm; hệ thống chỉ thực hiện điều được phép và còn hợp lệ; kết quả chưa rõ không dẫn đến một lần thực hiện thay thế thiếu căn cứ.

Sau bài học, bạn cần có khả năng:

- Chọn mức xác nhận tương xứng với hậu quả của hành động.
- Phân biệt xác nhận ý định, xác thực, kiểm tra quyền và phê duyệt.
- Ràng buộc nội dung đã xem với đối tượng, actor, phiên bản và phạm vi thao tác.
- Thiết kế luồng chống thay nội dung sau khi xem, bỏ qua bước và thực hiện trùng.
- Hiển thị đúng trạng thái đã ghi nhận, đang xử lý và chưa rõ kết quả.
- Kiểm thử cả giao diện lẫn invariant tại backend.

## 2. Xác nhận giải quyết vấn đề nào?

### 2.1. Giảm sai sót trước một quyết định có hậu quả

Người dùng có thể chọn nhầm đơn hàng, đang ở nhầm tổ chức, đọc sai số tiền hoặc bấm một nút do thói quen. Một bước xem lại có ích khi nó làm rõ những dữ kiện mà người dùng có khả năng kiểm tra trước khi thực hiện.

Ngược lại, hộp thoại “Bạn có chắc không?” xuất hiện ở mọi thao tác có thể khiến người dùng bấm tiếp theo phản xạ. Thêm số lần bấm không tự làm tăng chất lượng quyết định.

Bước xác nhận nên trả lời những câu hỏi cụ thể:

```text
Tôi đang làm hành động gì?
Cho đối tượng nào, trong tổ chức hoặc phạm vi nào?
Giá trị và người nhận/phạm vi tác động là gì?
Điều gì sẽ xảy ra sau khi tôi gửi?
Tôi có thể dừng hoặc sửa ở bước nào?
```

### 2.2. Các kiểm soát có vai trò khác nhau

| Kiểm soát | Câu hỏi chính | Không tự thay thế được |
| --- | --- | --- |
| Xác thực | Caller được ràng buộc với danh tính nào? | Quyền đối với một đối tượng cụ thể |
| Quyền theo đối tượng | Actor có được làm hành động này trên đối tượng này không? | Tính hợp lệ của trạng thái hoặc số tiền |
| Xác nhận ý định | Người dùng được yêu cầu xem lại và gửi lựa chọn nào? | Phân quyền, invariant hoặc phê duyệt của người khác |
| Xác thực bổ sung | Có đáp ứng mức xác thực/freshness theo chính sách không? | Quyết định nghiệp vụ đúng hoặc ý nghĩa của nội dung |
| Phê duyệt | Quyết định có thỏa chính sách người duyệt, nội dung và trình tự không? | Tính toàn vẹn của bước thực thi và chống trùng |
| Transaction và idempotency | Quyết định có được ghi nhất quán, không áp dụng lại ngoài hợp đồng không? | Việc người dùng nhìn thấy nội dung rõ ràng |

Một người đăng nhập hợp lệ và bấm xác nhận vẫn có thể không được tự phê duyệt yêu cầu do mình tạo. Một người có quyền cũng không được duyệt yêu cầu đã hủy hoặc vượt hạn mức nghiệp vụ.

### 2.3. Không nâng dấu vết kỹ thuật thành bằng chứng tuyệt đối

Backend có thể ghi nhận rằng một request hợp lệ đã tham chiếu đúng ngữ cảnh xác nhận. Điều đó không tự chứng minh người dùng đã đọc mọi dòng, hiểu mọi hậu quả hoặc thiết bị không bị chiếm quyền.

Nhập lại tên đối tượng, đánh dấu checkbox hoặc xác thực bổ sung có thể hỗ trợ một mục tiêu cụ thể. Chúng không phải cơ chế chống tự động hóa tuyệt đối, cũng không biến mọi thao tác thành một quyết định không thể tranh chấp.

## 3. Chọn mức xác nhận theo rủi ro

### 3.1. Đánh giá hậu quả và khả năng phục hồi

Các yếu tố có thể ảnh hưởng thiết kế gồm:

- Mức ảnh hưởng tới tiền, quyền truy cập, dữ liệu hoặc hoạt động của người khác.
- Phạm vi một đối tượng hay hàng loạt đối tượng.
- Khả năng hoàn tác thực tế và thời điểm không còn có thể dừng.
- Khả năng người dùng chọn nhầm hoặc khó phân biệt các đối tượng.
- Mức nhạy cảm của ngữ cảnh và chính sách xác thực/phê duyệt áp dụng.

Đây là tiêu chí thiết kế, không phải một thang điểm bắt buộc chung cho mọi sản phẩm. Quy tắc quyết định mức kiểm soát cần do hệ thống thực thi, không để caller tự gửi `risk=low` để bỏ bước.

### 3.2. Một số cách xác nhận và giới hạn

| Cách thực hiện | Khi có thể hữu ích | Giới hạn cần hiểu |
| --- | --- | --- |
| Xem lại và nút có tên hành động cụ thể | Một quyết định có nội dung rõ, cần giảm bấm nhầm | Không tự kiểm tra quyền hay dữ liệu hiện tại |
| Màn hình xem lại riêng | Cần đọc nhiều dữ kiện, đối chiếu trước/sau hoặc phạm vi lớn | Không được dùng điều hướng như bằng chứng đã xác nhận |
| Nhập lại tên đối tượng | Xóa hoặc thay đổi có hậu quả lớn, cần chú ý đúng mục tiêu | Có thể được tự động điền; không phải bí mật hay quyền |
| Xác thực bổ sung | Chính sách yêu cầu mức xác thực mới hơn hoặc mạnh hơn | Không thay phê duyệt, invariant hoặc việc ràng buộc nội dung |
| Phê duyệt độc lập | Chính sách yêu cầu người khác hoặc nhiều cấp duyệt | Vẫn phải gắn quyết định với nội dung và revision |
| Hoàn tác có bảo đảm phù hợp | Thao tác thật sự có cửa sổ phục hồi an toàn | Không được hứa hoàn tác nếu tác động ngoài đã không thể thu hồi |

Không bắt người dùng nhập một từ chung như “ĐỒNG Ý” cho mọi hành động rồi coi đó là bảo vệ chính. Nếu cần nhập tên, làm rõ mục tiêu của bước đó và hỗ trợ cách tương tác phù hợp; tránh biến lỗi gõ hoặc khả năng vận động thành rào cản không cần thiết.

### 3.3. Giữ quyền quyết định rõ ràng

Nút chính phải nêu hành động, không dùng một nhãn mơ hồ như “OK” khi người dùng đang phê duyệt một số tiền cụ thể. Nút quay lại phải cho phép kiểm tra mà chưa gây tác động.

Tránh lời cảnh báo cường điệu hoặc gây áp lực để buộc bấm tiếp. Nêu hậu quả thực tế, điều kiện dừng và bước tiếp theo. Không hứa “có thể hoàn tác bất cứ lúc nào” nếu hợp đồng của sản phẩm không có bảo đảm đó.

## 4. Ví dụ: phê duyệt một yêu cầu hoàn tiền

### 4.1. Bối cảnh nghiệp vụ

Giả sử một sản phẩm có các quy tắc minh họa:

- Nhân viên lập yêu cầu không được tự duyệt yêu cầu đó.
- Actor duyệt phải có quyền đối với đúng yêu cầu, đơn hàng và tenant.
- Yêu cầu chỉ được duyệt từ trạng thái chờ duyệt phù hợp.
- Số tiền phải dương, đúng tiền tệ và không vượt phần có thể hoàn theo các cam kết liên quan.
- Việc duyệt được ghi nhận trước; gửi yêu cầu hoàn tiền ra ngoài là bước tiếp theo.
- Mỗi yêu cầu chỉ có chuyển đổi duyệt hợp lệ theo state machine; retry không tạo thêm tác động.

Đây là chính sách của ví dụ, không phải kết luận rằng mọi sản phẩm phải có cùng quy trình. Bước xác nhận cần trình bày nội dung mà chính sách thực tế yêu cầu người duyệt xem xét.

### 4.2. Nội dung người dùng cần thấy

Một vùng xem lại có thể thể hiện:

```text
Phê duyệt hoàn tiền

Đơn vị: Cửa hàng A
Đơn hàng: DH-731
Yêu cầu hoàn: HT-318
Số tiền: 1.500.000 VND
Nơi hoàn: Phương thức thanh toán gốc của đơn, kết thúc bằng 4821

Sau khi được phê duyệt, yêu cầu sẽ được chuyển sang bước thực hiện hoàn tiền.
Đóng màn hình sau khi gửi không hủy yêu cầu đã được ghi nhận.

[Quay lại]   [Phê duyệt hoàn 1.500.000 VND]
```

Tên đối tượng, phạm vi tổ chức, số tiền và nơi hoàn đều giúp giảm nhầm lẫn. Không chỉ hiển thị ID nội bộ khó đọc hoặc một câu cảnh báo chung.

Dữ liệu che phải vẫn đủ phân biệt trong ngữ cảnh được phép. Hai phương thức có cùng vài ký tự cuối không tự là cùng một người nhận; hệ thống cần reference chính xác ở backend và cách hiển thị phù hợp để người dùng không bị đánh lừa.

### 4.3. Giá trị hiển thị phải cùng nghĩa với giá trị thực thi

Trong ví dụ, giao diện hiển thị `1.500.000 VND`, còn dữ liệu chuẩn có thể là chuỗi thập phân `1500000` cùng mã `VND`. Cần thống nhất đơn vị, độ chính xác và cách định dạng.

Không làm tròn một giá trị quan trọng tới mức người dùng xác nhận một con số có vẻ khác với số được thực thi. Không bỏ mã tiền tệ hoặc để dấu phân cách khiến người dùng hiểu nhầm quy mô.

Nếu màn hình cho phép sửa số tiền hay nơi nhận, việc sửa phải dẫn tới kiểm tra và ngữ cảnh xác nhận mới theo hợp đồng. Không giữ một tóm tắt cũ trong khi payload gửi đi đã thay đổi.

## 5. Ràng buộc xác nhận với một ý định xác định

### 5.1. Ngữ cảnh xác nhận do máy chủ tạo

Máy chủ có thể phát hành một ngữ cảnh xác nhận gồm:

- Tenant, actor hoặc quan hệ đại diện được phép.
- Loại hành động và đối tượng đích.
- Revision/generation của đối tượng và các phụ thuộc quan trọng.
- Số tiền, tiền tệ, người nhận hoặc phạm vi tác động được chuẩn hóa.
- Phiên bản chính sách/nội dung ảnh hưởng tới quyết định.
- Deadline và trạng thái sử dụng của ngữ cảnh xác nhận.

Dữ liệu này được lưu hoặc được ràng buộc theo mô hình tin cậy được thiết kế. Client không tự khai toàn bộ nội dung rồi chỉ thêm `confirmed=true` để yêu cầu máy chủ tin rằng đã có một bước xem lại hợp lệ.

### 5.2. Ví dụ phản hồi chuẩn bị

```json
{
  "confirmation_ref": "confirmation-904",
  "action": "APPROVE_REFUND",
  "expires_at": "2026-10-05T09:10:00Z",
  "summary": {
    "organization_display": "Cửa hàng A",
    "refund_ref": "refund-318",
    "refund_display": "HT-318",
    "order_display": "DH-731",
    "refund_revision": 12,
    "refund_state": "PENDING_REVIEW",
    "amount": {
      "value": "1500000",
      "currency": "VND"
    },
    "recipient_display": "Phương thức thanh toán gốc của đơn, kết thúc bằng 4821",
    "effect": "APPROVAL_THEN_REFUND_PROCESSING"
  }
}
```

Đây là dữ liệu minh họa cho client đã được phép xem. Máy chủ giữ reference người nhận thực sự và các điều kiện cần kiểm chứng; chuỗi đã che không được dùng làm khóa thực thi.

`confirmation_ref` chỉ là reference trong giao thức. Biết reference không tự tạo quyền phê duyệt hoặc đọc thông tin. Thiết kế dùng token/chữ ký cũng phải xác định rõ ràng buộc, thời hạn và cách chống sử dụng lại; chữ ký không thay kiểm tra state hiện tại.

Thông tin kỹ thuật như nonce, digest hoặc chi tiết xác thực không cần trở thành nội dung chính trên màn hình người dùng. Chỉ đưa ra những gì giúp họ quyết định và tra cứu phù hợp.

### 5.3. Request xác nhận chỉ chọn ngữ cảnh đã được kiểm chứng

Một request có thể gửi:

```json
{
  "command_ref": "command-772",
  "confirmation_ref": "confirmation-904"
}
```

Máy chủ giải quyết ý định từ ngữ cảnh đã ràng buộc và dữ liệu có thẩm quyền, không nhận một số tiền mới để âm thầm thay số đã xem. Nếu API cần nhận thêm trường, phải đối chiếu chúng với ngữ cảnh và hợp đồng thay đổi, không cho chúng mở rộng phạm vi.

Command/reference idempotency phải có phạm vi và fingerprint phù hợp. Reference do client biết hoặc chọn không có nghĩa client có quyền điều khiển kết quả đã lưu của người khác.

### 5.4. Nội dung hoặc điều kiện quan trọng đổi thì phải xem lại

Nếu số tiền đổi từ 1.500.000 thành 15.000.000, không được dùng xác nhận cũ để duyệt số mới. Nếu actor mất quyền, đối tượng đã hủy hoặc chính sách áp dụng thay đổi, backend phải đánh giá lại theo quy tắc hiện tại.

Revision là một cách phát hiện dữ liệu đã thay đổi, nhưng cần hiểu nó bao phủ những gì. Nếu người nhận nằm ở một đối tượng khác mà revision của yêu cầu không đổi, chỉ kiểm tra revision yêu cầu có thể chưa đủ.

Có thể ràng buộc thêm phiên bản phụ thuộc hoặc nội dung chuẩn quan trọng theo thiết kế. Không tự tái tạo tóm tắt mới nhất rồi áp dụng khi người dùng vẫn đang xác nhận tóm tắt cũ.

## 6. Quy trình chuẩn bị và thực thi tại backend

### 6.1. Bước chuẩn bị không thực hiện thay hành động

Endpoint chuẩn bị kiểm tra caller, quyền theo đối tượng và điều kiện để trình bày lựa chọn. Nó lấy dữ liệu từ nguồn đáng tin cậy rồi phát hành ngữ cảnh xác nhận.

Trong ví dụ, chuẩn bị không phê duyệt và không gửi hoàn tiền. Việc mở hộp thoại hoặc tải một trang không được coi là xác nhận. Nếu sản phẩm có cơ chế giữ tài nguyên tạm trong bước chuẩn bị, đó là hành vi riêng cần phạm vi, thời hạn và dọn tài nguyên rõ ràng.

Các kiểm tra ở bước chuẩn bị giúp trải nghiệm đúng, nhưng không giữ quyền hoặc trạng thái đứng yên tới lúc thực thi. Bước thực thi vẫn phải kiểm tra lại.

### 6.2. Giả mã cho bước xác nhận

```text
Xác thực caller và xác định tenant từ ngữ cảnh đáng tin cậy
Kiểm tra cấu trúc command và confirmation reference

BEGIN TRANSACTION
    Phối hợp trên confirmation, yêu cầu hoàn và dữ liệu ngân sách liên quan
    Đọc đối tượng trong đúng phạm vi và quan hệ do máy chủ xác định
    Kiểm tra quyền hiện tại của actor theo đối tượng

    Tra command idempotency và đối chiếu fingerprint
    Nếu đã có kết quả hợp lệ:
        trả lại quyết định đã lưu, không thực hiện lần nữa

    Kiểm tra confirmation thuộc đúng actor/phạm vi/hành động
    Kiểm tra trạng thái sử dụng, deadline và generation
    Kiểm tra revision và các phụ thuộc của nội dung đã xem
    Kiểm tra xác thực bổ sung nếu chính sách yêu cầu
    Kiểm tra actor không vi phạm quy tắc người lập/người duyệt
    Kiểm tra state machine và các invariant số tiền/ngân sách

    Ghi nhận phần ngân sách/cam kết cần bảo vệ theo chính sách
    Chuyển yêu cầu sang trạng thái duyệt được chấp nhận
    Đánh dấu confirmation đã dùng, gắn với command
    Ghi kết quả command, audit và outbox công việc
COMMIT

Trả kết quả chấp nhận đã lưu và hướng tra trạng thái
```

Giả mã là mô tả trách nhiệm. Cơ chế khóa/version và ràng buộc dữ liệu phải thực sự phối hợp các cập nhật cạnh tranh. Đọc phần có thể hoàn ngoài transaction rồi tin nó không đổi có thể làm hai yêu cầu cùng chiếm một ngân sách.

### 6.3. Mọi đường gọi đều phải giữ invariant

Giao diện web, ứng dụng di động, tác vụ nền, API nội bộ và công cụ quản trị không được có một đường gọi bỏ qua kiểm tra cùng loại hành động. Việc nút chỉ xuất hiện cho một số vai trò không bảo vệ endpoint khỏi caller trực tiếp.

Với ví dụ hoàn tiền, cần xét các cam kết đã được chấp nhận chứ không chỉ các khoản đã hoàn xong, nếu đó là cơ sở giới hạn của sản phẩm. Không để khoảng chờ thực thi trở thành cửa sổ cho nhiều phê duyệt vượt tổng cho phép.

Bước xác nhận không cho phép vượt hạn mức, tự duyệt hoặc bỏ qua phê duyệt cấp khác. Nếu nội dung cần duyệt lại, phải đưa về quy trình phù hợp thay vì biến nút xác nhận thành quyền đặc biệt.

### 6.4. Chỉ công bố kết quả sau ranh giới lưu phù hợp

Nếu transaction rollback, không trả thông báo phê duyệt đã được ghi nhận và không phát công việc như đã commit. Nếu commit thành công nhưng response mất, backend phải có cách tra lại command để tránh thực hiện thay thế.

Outbox có thể giữ ý định thực thi cùng transaction nguồn, nhưng bước hoàn tiền bên ngoài vẫn cần idempotency và đối soát riêng. “Phê duyệt đã được ghi nhận” không đồng nghĩa nhà cung cấp đã hoàn tiền xong.

## 7. Phiên bản, thời hạn và sử dụng một lần

### 7.1. Ngữ cảnh xác nhận có vòng đời riêng

Một confirmation có thể có các trạng thái như `ISSUED`, `CONSUMED`, `EXPIRED`, `CANCELLED` hoặc `INVALIDATED`. Vòng đời này khác với vòng đời yêu cầu hoàn tiền.

`CONSUMED` cần liên kết được với command đã dùng nó. Caller retry đúng command có thể được trả kết quả đã lưu, không phải được phép dùng confirmation cho một lần phê duyệt mới.

Không coi “token kiểm tra chữ ký được” là đủ. Backend còn phải biết ngữ cảnh có còn được dùng, thuộc đúng actor, hành động và đối tượng hay không.

### 7.2. Hết hạn không phủ nhận một quyết định đã được ghi nhận

Deadline xác nhận được xét bằng thời gian máy chủ tại điểm quyết định đã định nghĩa, dưới cơ chế phối hợp phù hợp. Countdown hoặc timestamp caller gửi không có quyền giữ ngữ cảnh còn hiệu lực.

Nếu command đã được chấp nhận nhưng response mất, retry sau deadline vẫn cần tra kết quả cũ trước khi kết luận về lần gọi mới. Không trả một thông báo khiến người dùng tin rằng chắc chắn chưa có gì xảy ra chỉ vì confirmation nay đã quá hạn.

Nếu ngữ cảnh thật sự hết hạn và command chưa được chấp nhận, yêu cầu chuẩn bị lại theo chính sách. Việc chuẩn bị lại không tự phê duyệt và không tự giữ nguyên nội dung cũ nếu dữ liệu có thẩm quyền đã thay đổi.

### 7.3. Hai tab và hai confirmation không được cùng vượt invariant

Hai tab có thể mở hai confirmation cho cùng yêu cầu ở revision 12. Vô hiệu hóa nút ở tab thứ nhất không khóa tab thứ hai hoặc một caller khác.

State machine và cơ chế version/khóa phải đảm bảo chỉ những chuyển đổi hợp lệ được chấp nhận. Nếu yêu cầu đã được duyệt bởi command A, command B không được tạo thêm một lần thực hiện chỉ vì dùng key hoặc confirmation khác.

Phạm vi ngân sách cũng có thể rộng hơn một yêu cầu. Hai yêu cầu hoàn tiền khác nhau của cùng đơn cần được phối hợp ở dữ liệu bảo vệ phần có thể hoàn, không chỉ khóa riêng từng confirmation.

### 7.4. Thay đổi nào cần xác nhận lại?

Định nghĩa rõ các thay đổi ảnh hưởng ý nghĩa hoặc điều kiện quyết định. Ví dụ số tiền, nơi nhận, tập đối tượng, quyền đại diện hoặc cấp phê duyệt có thể quan trọng; một thay đổi kỹ thuật không liên quan có thể được xử lý khác nếu hợp đồng cho phép.

Không mặc định mọi revision khác đều có thể tự bỏ qua, và không tự cho rằng mọi revision đổi đều là bằng chứng ý định đã khác. Mô hình version và chính sách phải giúp backend đánh giá đúng, đồng thời giữ nội dung người dùng đã xác nhận.

Nếu cần xem lại, trả kết quả rõ ràng và phát hành ngữ cảnh mới. Không sửa nội dung của confirmation cũ để làm như người dùng đã xem phiên bản mới.

## 8. Xác thực bổ sung và bảo vệ luồng tương tác

### 8.1. Xác thực bổ sung không phải quyền phê duyệt

Chính sách có thể yêu cầu xác thực mới hơn hoặc mạnh hơn trước một hành động rủi ro. Backend cần kiểm tra danh tính, thời điểm, mục đích và phạm vi của bằng chứng xác thực theo mô hình tin cậy được chọn.

Một lần xác thực bổ sung thành công không cho phép actor tự duyệt nếu quy tắc cấm, không mở rộng tenant và không thay thế việc đối chiếu số tiền hay trạng thái.

Nếu cần ràng buộc bằng chứng xác thực với một giao dịch hoặc ngữ cảnh cụ thể, phải thiết kế và kiểm chứng ràng buộc đó. Không suy từ một dấu “đã xác thực gần đây” rằng mọi nội dung trên mọi tab đều đã được xác nhận.

### 8.2. Quay lại sau đăng nhập không tự thực thi

Khi phiên đăng nhập hết hạn giữa luồng, việc đăng nhập lại phải giữ được phạm vi dữ liệu và danh tính hiện tại. Nếu người dùng đăng nhập bằng tài khoản khác, confirmation của tài khoản trước không tự chuyển chủ.

Sau khi khôi phục truy cập, kiểm tra trạng thái command đã gửi nếu có, rồi đưa người dùng về bước xem lại cần thiết. Không tự gửi một payload cũ ngay sau redirect đăng nhập chỉ vì trước đó nút từng được bấm.

Việc gia hạn đăng nhập không gia hạn confirmation nghiệp vụ. Thời hạn và generation của mỗi kiểm soát cần được đánh giá riêng.

### 8.3. Bảo vệ request và nội dung được hiển thị

Luồng web cần biện pháp phù hợp chống gửi yêu cầu giả qua phiên người dùng và nhúng giao diện theo cách gây nhầm lẫn. Cơ chế cụ thể phải phù hợp với cách quản lý phiên và kiến trúc của ứng dụng.

Tên đối tượng, ghi chú và dữ liệu nhập phải được hiển thị như dữ liệu, không thực thi như nội dung tùy ý. Một chuỗi có thể giả nhãn hoặc che thông tin nếu giao diện render không an toàn.

Summary do máy chủ tạo giúp giữ tính nhất quán của giao thức, nhưng không tự bảo đảm một client bị sửa đã hiển thị trung thực. Cần giữ các lớp bảo vệ ứng dụng và phiên tương ứng; confirmation không giải quyết thay mọi rủi ro trên thiết bị hoặc trình duyệt.

### 8.4. Không làm lộ bí mật để thuận tiện điều hướng

Không đưa session token, bằng chứng xác thực bổ sung hoặc token xác nhận bí mật vào URL, analytics hay thông báo lỗi. Reference dùng tra cứu vẫn cần kiểm tra quyền tại mỗi endpoint.

Dữ liệu giữ để phục hồi màn hình cần có phạm vi, thời hạn và cơ chế bảo vệ phù hợp. Không lưu toàn bộ payload nhạy cảm chỉ để người dùng có thể mở lại một hộp thoại.

## 9. Thiết kế trạng thái giao diện đúng với kết quả

### 9.1. Một mô hình giao diện minh họa

| Trạng thái giao diện | Nội dung và hành động phù hợp |
| --- | --- |
| Đang chuẩn bị | Cho biết đang lấy dữ liệu; chưa cho xác nhận khi chưa có nội dung hợp lệ |
| Đang xem lại | Hiển thị đối tượng, phạm vi, giá trị và hậu quả; có đường quay lại rõ |
| Đang gửi | Phản hồi ngay rằng request đã được gửi; hạn chế bấm lặp ở giao diện |
| Đã ghi nhận, đang thực hiện | Hiển thị quyết định đã lưu và cách theo dõi; không gọi là hoàn tất tác động ngoài |
| Hoàn tất đã xác minh | Hiển thị kết quả đúng phạm vi đã được nguồn xác nhận |
| Cần xem lại | Giải thích dữ liệu/điều kiện đã đổi ở mức được phép và lấy nội dung mới |
| Hết hạn chưa được chấp nhận | Kết thúc ngữ cảnh cũ; cho phép chuẩn bị lại theo hợp đồng |
| Chưa rõ kết quả | Giữ reference, tra trạng thái; không khuyến khích thực hiện một command thay thế |
| Bị từ chối | Nêu cách xử lý phù hợp với quyền và loại điều kiện không đạt |

Mô hình giao diện không phải nguồn sự thật về trạng thái backend. Reload, mở tab khác hoặc quay lại lịch sử không được tạo một kết quả nghiệp vụ mới.

### 9.2. Phản hồi thành công cần nêu đúng tầng

Trong ví dụ, sau commit có thể hiển thị:

```text
Đã ghi nhận phê duyệt yêu cầu HT-318.
Yêu cầu hoàn tiền đang chờ thực hiện.
Bạn có thể xem trạng thái tại hồ sơ yêu cầu.
```

Không hiển thị “Đã hoàn tiền thành công” nếu chỉ mới tạo outbox hoặc nhận được quyết định phê duyệt nội bộ. Khi nhà cung cấp xác nhận kết quả cuối, giao diện có thể cập nhật theo bằng chứng tương ứng.

Nếu có kết quả một phần hoặc bước bù, cần thể hiện đúng phạm vi. Một thông báo chung không được làm mất thông tin đối tượng nào đã thay đổi và đối tượng nào chưa thay đổi.

### 9.3. Timeout cần một đường tra cứu

Client timeout hoặc người dùng đóng tab không chứng minh request đã rollback. Khi chưa biết kết quả, hiển thị thông điệp như “Chưa xác định được kết quả. Đang kiểm tra trạng thái” cùng hành động tra cứu phù hợp.

Dùng reference của command để nhận lại kết quả theo quyền. Nếu hợp đồng cho phép gửi lại cùng command và cùng key để lấy kết quả, giữ quan hệ đó; không tự tạo key mới ở mỗi lỗi mạng.

Lỗi truy cập khi tra cứu cũng không tự chứng minh command chưa xảy ra. Không cho giao diện biến mọi lỗi thành lời mời “thực hiện lại” mà thiếu kiểm tra kết quả cũ.

### 9.4. Đóng hộp thoại và hủy nghiệp vụ khác nhau

Trước khi gửi, quay lại có thể đơn giản là không thực hiện hành động. Sau khi gửi, đóng hộp thoại chỉ thay đổi giao diện, trừ khi có một command hủy riêng được backend chấp nhận.

Nếu sản phẩm hỗ trợ hủy, phải giải thích khi nào có thể hủy và kết quả hủy đã được ghi nhận hay mới đang chờ. Không hứa dừng được một tác động mà hệ thống ngoài đã nhận và không còn cho thu hồi.

Không giữ người dùng mắc kẹt trong modal chỉ vì request đang chạy. Có thể cho rời màn hình đồng thời giữ cách theo dõi command đang xử lý trong phạm vi được phép.

### 9.5. Hỗ trợ bàn phím, trình đọc màn hình và thao tác chạm

Nội dung quan trọng phải có nhãn và văn bản rõ ràng, không chỉ dựa vào màu đỏ hoặc biểu tượng. Nêu tên hành động, số tiền và đối tượng theo cách có thể đọc bằng công cụ hỗ trợ.

Quản lý focus phù hợp khi mở và đóng modal; giữ thứ tự điều hướng dễ hiểu và cho phép quay lại. Tránh cách đặt focus hoặc xử lý phím khiến một lần Enter ngoài dự định lập tức kích hoạt hành động nguy hiểm.

Thông báo trạng thái gửi, cần xem lại hoặc chưa rõ kết quả cần có cách nhận biết ngoài thay đổi hình ảnh. Không phát thông báo lặp liên tục gây khó theo dõi. Kích thước và vị trí nút nên giảm bấm nhầm, đặc biệt trên màn hình chạm.

Nếu yêu cầu nhập tên đối tượng, hỗ trợ phương thức nhập phù hợp và giải thích rõ giá trị cần nhập. Đây là bước tăng chú ý, không phải bí mật để xác thực người dùng.

## 10. Xác nhận cho hành động hàng loạt

### 10.1. Con số hiển thị phải gắn với tập mục tiêu thực sự

Một hộp thoại ghi “Xóa 128 tài liệu” không được dẫn tới việc backend áp dụng cho mọi tài liệu khớp bộ lọc sau đó, khi tập đó đã tăng thành 250.

Có thể dùng selection reference gắn với một tập mục tiêu hoặc một ngữ nghĩa lựa chọn có phiên bản được máy chủ quản lý. Nếu hợp đồng dùng một tập động, phải trình bày đúng điều đó và kiểm tra các điều kiện thay đổi, không giả định một con số preview là lời hứa về tập cuối.

Client tự gửi `count=128` không chứng minh tập thực thi có 128 phần tử. Backend phải xác định mục tiêu và quyền trên phạm vi cần thiết theo chính sách.

### 10.2. Nêu rõ nguyên tử hay từng phần

Nếu batch cho phép thành công từng phần, phải cho người dùng biết và cung cấp kết quả phù hợp sau thực thi. Không dùng một thông báo “đã xóa” cho toàn tập khi thực tế chỉ một phần được chấp nhận.

Nếu sản phẩm yêu cầu tất cả hoặc không phần tử nào, triển khai phải có bảo đảm tương ứng. Hộp thoại xác nhận không tự tạo transaction xuyên nhiều hệ thống.

Với công việc chạy nền, “đã nhận tác vụ” và “mọi phần tử đã hoàn tất” là hai trạng thái khác nhau. Hủy tác vụ cũng phải theo khả năng thực tế, không chỉ dừng thanh tiến trình.

### 10.3. Không tiết lộ dữ liệu ngoài quyền trong bản xem lại

Preview, số lượng và ví dụ đối tượng có thể làm lộ thông tin nếu bộ lọc đi qua nhiều tenant hoặc phạm vi không được phép. Kiểm tra quyền áp dụng cả ở bước xem lại, không chỉ ở bước thực thi.

Các ID mục tiêu và revision cần lưu ở nơi phù hợp để đối chiếu. Không đưa cả tập dữ liệu nhạy cảm vào log hoặc URL của màn hình xác nhận.

## 11. Ca minh họa: nội dung đổi giữa xem lại và xác nhận

### 11.1. Dòng thời gian

Giả sử yêu cầu `refund-318` ở revision 12, số tiền 1.500.000 VND, được tạo bởi một actor khác người đang duyệt. Phần ngân sách liên quan vẫn phải được kiểm tra tại bước thực thi.

| Bước | Sự kiện | Kết quả đúng |
| --- | --- | --- |
| 1 | Người duyệt mở xem lại | Tạo confirmation A gắn revision 12 và số tiền 1.500.000 VND |
| 2 | Một thay đổi hợp lệ tăng số tiền thành 1.800.000 VND, revision 13 | Nội dung của A không tự đổi theo |
| 3 | Người duyệt gửi xác nhận A | Từ chối dùng ngữ cảnh cũ; không duyệt số mới bằng xác nhận số cũ |
| 4 | Giao diện lấy lại dữ liệu | Hiển thị thay đổi, tạo confirmation B và yêu cầu xem lại |
| 5 | Người duyệt chủ động xác nhận B bằng command C | Backend kiểm tra quyền, quy tắc người duyệt, state và ngân sách hiện tại |
| 6 | Command C commit quyết định ở revision 14 | Consume B, ghi kết quả C và outbox theo cùng hợp đồng transaction |
| 7 | Response mất, client retry C | Trả quyết định đã lưu, không tạo lần duyệt hay tác động thứ hai |
| 8 | Worker thực hiện hoàn tiền | Dùng cơ chế chống trùng/đối soát riêng; giao diện theo dõi kết quả thực tế |

Nếu backend tự đọc số tiền mới nhất ở bước 3 rồi duyệt, nó có thể giữ đúng một số kiểm tra dữ liệu nhưng làm sai ý nghĩa của bước xác nhận. Người dùng chưa xem quyết định 1.800.000 VND tại ngữ cảnh đó.

### 11.2. Các nhánh khác cần giữ đúng

Nếu quyền người duyệt bị thu hồi sau bước xem lại, backend phải từ chối theo quyền hiện tại. Confirmation A hoặc B không giữ quyền sống mãi.

Nếu một tab khác đã duyệt trước, tab còn lại phải nhận kết quả/xung đột phù hợp. Không tạo lại tác động bằng cách đổi key hoặc làm ngơ state mới.

Nếu ngân sách có thể hoàn đã bị một yêu cầu khác chiếm trước, confirmation còn hạn vẫn không cho phép vượt tổng. Bước xem lại không đóng băng các invariant trừ khi có cơ chế giữ tài nguyên được thiết kế rõ.

### 11.3. Giới hạn cần truyền đạt cho người dùng

Thông báo cần xem lại có thể nêu “Nội dung yêu cầu đã thay đổi. Hãy kiểm tra số tiền trước khi phê duyệt”, trong phạm vi caller còn được phép xem.

Không dùng một hộp thoại mới với số tiền đổi rất nhỏ ở vị trí khó nhận ra rồi tự gửi lại. Mục tiêu là tạo cơ hội quyết định trên nội dung mới, không chỉ tạo thêm một token hợp lệ cho backend.

## 12. Kiểm thử tình huống lạm dụng và lỗi trải nghiệm

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Gọi thẳng API không qua màn hình | Endpoint rủi ro vẫn thực thi hợp đồng confirmation và mọi invariant |
| Tự gửi `confirmed=true` hoặc reference không hợp lệ | Không được coi như bằng chứng xác nhận hợp lệ |
| Đổi amount, recipient hoặc đối tượng sau bước xem lại | Không thực thi nội dung khác bằng confirmation cũ |
| Dùng confirmation của tenant/actor khác | Từ chối, không lộ summary hoặc receipt ngoài quyền |
| Caller có vai trò nhưng không có quyền trên đối tượng | Bị chặn ở prepare và execute theo chính sách |
| Người tạo tự duyệt dù đã xác thực bổ sung | Quy tắc người lập/người duyệt vẫn được giữ |
| Mất quyền sau prepare | Không phê duyệt bằng quyền đã cũ |
| Đối tượng hoặc phụ thuộc đổi version | Đánh giá đúng nội dung và yêu cầu xem lại khi cần |
| Confirmation hết hạn hoặc đã invalidated | Không tự gia hạn hoặc dùng lại bằng key mới |
| Hai tab dùng hai confirmation cho cùng yêu cầu | State machine và version ngăn các lần duyệt không hợp lệ |
| Hai yêu cầu cùng chiếm ngân sách hoàn của một đơn | Tổng cam kết không vượt invariant theo chính sách |
| Double click, nhấn Enter lặp hoặc retry mạng | Không tạo tác động nghiệp vụ trùng |
| Cùng command nhưng đổi payload quan trọng | Xung đột idempotency được xử lý, không áp dụng ý định mới |
| Transaction rollback sau bước consume | Không có một phần trạng thái bị công bố như đã commit |
| Commit thành công nhưng response mất | Tra lại command; giao diện không kết luận chắc chắn chưa thực hiện |
| Đóng tab hoặc hủy request ở client | Không bị hiểu nhầm là đã hủy backend |
| Provider chậm hoặc timeout | Không hiển thị hoàn tiền xong, không tự gửi tác động thay thế |
| Xác thực lại bằng tài khoản khác | Không tiếp tục confirmation của actor trước |
| Session bị lợi dụng gửi request giả hoặc nhúng giao diện | Các lớp bảo vệ phiên/request và giao diện được thực thi phù hợp |
| Tên đối tượng chứa nội dung giống nút hoặc HTML | Được hiển thị như dữ liệu, không giả luồng xác nhận |
| Định dạng tiền tệ và ngôn ngữ khác nhau | Người dùng thấy đúng giá trị, đơn vị và hậu quả được thực thi |
| Dùng bàn phím, trình đọc màn hình hoặc màn hình chạm | Đọc được nội dung, điều hướng và trạng thái; tránh kích hoạt ngoài ý muốn |
| Tập batch thay đổi sau preview | Không âm thầm mở rộng mục tiêu đã xem lại |
| Batch thành công một phần | Kết quả và khả năng phục hồi được hiển thị đúng phạm vi |
| Telemetry hoặc serializer gặp lỗi | Không lộ bí mật, không làm command bị thực hiện lại |

Kiểm thử backend cần kiểm tra dữ liệu cuối, revision, command result, trạng thái confirmation và audit/outbox liên quan. Với bước ngoài hệ thống, kiểm tra số tác động thực tế ở môi trường giả lập thích hợp.

Kiểm thử giao diện cần quan sát người dùng có phân biệt được đối tượng, giá trị, bước quay lại và kết quả chưa rõ hay không. Chỉ xác nhận modal đã xuất hiện hoặc nút đã bị disable không đủ để chứng minh luồng an toàn.

Với cạnh tranh, dùng điểm đồng bộ để tạo thứ tự prepare, thay đổi dữ liệu và commit cần kiểm chứng. Với timeout, kiểm tra riêng lỗi trước commit, sau commit và sau khi đã gửi ra ngoài; chúng không có cùng cách phục hồi.

## 13. Audit và observability của bước xác nhận

### 13.1. Ghi đúng điều hệ thống quan sát được

Có thể cần các dấu vết riêng cho:

- Ngữ cảnh xem lại được phát hành, cùng phiên bản nội dung và phạm vi.
- Attempt xác nhận, actor và kết quả kiểm chứng theo chính sách.
- Quyết định đã commit, command, revision và confirmation được consume.
- Công việc thực thi ngoài và kết quả đối soát liên quan.

Không ghi “người dùng đã đọc và hiểu” chỉ vì summary được tải. Không lấy analytics phía client làm bằng chứng duy nhất rằng quyết định đã được chấp nhận.

Nếu cần lưu snapshot nội dung quyết định, chọn dữ liệu đủ giải thích và có chính sách quyền/lưu giữ rõ ràng. Không lưu session secret, mã xác thực bổ sung hoặc token xác nhận nguyên giá trị trong audit chung.

### 13.2. Đo ma sát và lỗi mà không giảm kiểm soát

Có thể theo dõi số attempt theo operation/result/reason hữu hạn, tỷ lệ ngữ cảnh hết hạn, cần xem lại và kết quả chưa rõ. Các reference chi tiết để điều tra nằm trong nguồn được phân quyền, không phải labels có số giá trị không giới hạn.

Nhiều người quay lại có thể cho thấy nội dung khó hiểu, hoặc bước xem lại đang giúp phát hiện sai sót. Nhiều lỗi stale có thể do giao diện chậm, thay đổi cạnh tranh hoặc hành vi cố dùng ngữ cảnh cũ. Cần kiểm chứng nguyên nhân, không tự coi mọi tín hiệu là tấn công hoặc ma sát thừa.

Không giảm lỗi bằng cách bỏ kiểm tra revision, cho tự duyệt hoặc đổi timeout thành thành công. Kết quả vận hành chỉ tốt lên khi trải nghiệm rõ hơn và invariant vẫn được giữ.

### 13.3. Lỗi telemetry không làm thay đổi kết quả

Không thực thi lại command chỉ vì gửi metric/log vận hành thất bại. Nếu một loại audit là điều kiện bền vững bắt buộc, giữ nó theo hợp đồng transaction riêng, không nhập nhằng với analytics hoặc counter best effort.

Khả năng hỗ trợ sau sự cố nên dựa trên reference và kết quả nguồn có thẩm quyền. Không yêu cầu người dùng gửi ảnh token hoặc toàn bộ dữ liệu nhạy cảm để chứng minh họ đã bấm nút.

## 14. Câu hỏi tự kiểm tra

**Một checkbox xác nhận có đủ để bảo vệ API rủi ro không?**

Không. Backend vẫn phải kiểm tra quyền, trạng thái, nội dung, thời hạn, invariant và hợp đồng sử dụng confirmation. Caller có thể bỏ qua giao diện.

**Xác thực bổ sung có cho phép người lập tự phê duyệt không?**

Không nếu chính sách cấm tự duyệt. Xác thực và phê duyệt có vai trò khác nhau.

**Vì sao phải gắn số tiền và người nhận với ngữ cảnh xác nhận?**

Để một lựa chọn trên nội dung đã xem không bị dùng cho nội dung khác. Backend phải đối chiếu cả đối tượng và các phụ thuộc ảnh hưởng ý nghĩa quyết định.

**Vô hiệu hóa nút có ngăn được mọi yêu cầu trùng không?**

Không. Nhiều tab, caller trực tiếp và retry mạng vẫn có thể gửi thêm request. State machine, transaction và idempotency mới giữ được invariant tại nguồn.

**Timeout sau khi bấm xác nhận có nghĩa thao tác thất bại không?**

Không. Có thể command đã commit. Cần tra lại theo reference và hợp đồng, không tự tạo một lần thực hiện thay thế.

**Đóng modal sau khi gửi có hủy backend không?**

Không mặc định. Hủy nghiệp vụ cần command và điều kiện riêng; việc đóng giao diện không hoàn tác một quyết định đã lưu.

**Confirmation hết hạn sau khi command đã commit thì retry phải làm gì?**

Tra và trả kết quả command cũ theo quyền, thay vì phủ nhận lịch sử hoặc thực hiện lại. Deadline không xóa quyết định đã được chấp nhận.

**Khi nào bước xác nhận có giá trị đối với bảo mật logic nghiệp vụ?**

Khi người dùng có cơ hội xem đúng đối tượng, giá trị và hậu quả; backend chỉ thực hiện nội dung được ràng buộc còn hợp lệ; và mọi kết quả, retry hoặc phục hồi đều giữ đúng quyền, phê duyệt và invariant.

