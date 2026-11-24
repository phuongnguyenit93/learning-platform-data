# Recovery progress indicator — Hiển thị tiến độ khôi phục tài khoản

## 1. Tiến độ phải giúp người dùng quyết định bước tiếp theo

Recovery progress indicator là thành phần cho biết người dùng đang ở đâu trong luồng khôi phục tài khoản, việc gì đã hoàn tất và điều gì cần xảy ra tiếp theo.

Người đang mất mật khẩu, MFA, passkey hoặc thiết bị xác thực thường không biết yêu cầu của mình đã được nhận chưa. Nếu chỉ thấy biểu tượng xoay, họ có thể gửi nhiều yêu cầu, dùng nhầm mã cũ, đóng trang khi còn cần thao tác hoặc tin rằng tài khoản đã an toàn quá sớm.

Một chỉ báo tiến độ hữu ích cần trả lời:

1. Yêu cầu đã được hệ thống tiếp nhận hay chưa?
2. Hệ thống đang xử lý hay đang chờ người dùng?
3. Bước nào đã hoàn tất trong phạm vi được phép công bố?
4. Người dùng cần làm gì và có thể rời trang hay không?
5. Nếu thời gian chờ kéo dài, họ có lựa chọn nào?

Giá trị của thành phần này nằm ở độ tin cậy của thông tin và khả năng hành động. Một thanh chạy mượt nhưng không phản ánh trạng thái thật có thể khiến người dùng đưa ra quyết định sai.

**Ví dụ:** Sau khi người dùng gửi mã recovery, máy chủ mới chỉ đưa yêu cầu vào hàng đợi. Giao diện nên hiển thị “Đã nhận thông tin, đang chờ xử lý” nếu đó là trạng thái thực tế. Nó chưa được đánh dấu “Xác minh thành công”.

## 2. Phân biệt tiến độ, thời gian và quyền truy cập

Ba khái niệm này có liên quan nhưng không thay thế nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tiến độ xử lý | Những phần công việc đã hoàn tất | Tài liệu đã được tiếp nhận, đang chờ xét duyệt |
| Thời gian | Mốc hoặc khoảng chờ của một bước | Có thể yêu cầu gửi lại sau thời điểm được chỉ định |
| Quyền truy cập | Những hành động người dùng được phép thực hiện | Được thiết lập mật khẩu mới nhưng chưa có session đăng nhập đầy đủ |

Đi đến bước cuối trên giao diện không cấp quyền thực hiện hành động cuối. Máy chủ vẫn phải xác minh điều kiện của từng yêu cầu.

Tương tự, một đồng hồ đếm ngược về không chỉ cho biết một mốc thời gian đã tới theo cách tính của giao diện. Nó không chứng minh xác minh đã hoàn tất hoặc yêu cầu recovery đã được chấp thuận.

Khi xác định nhãn “Hoàn tất”, cần nêu rõ đối tượng hoàn tất:

- Hoàn tất tải tài liệu.
- Hoàn tất xác minh một bằng chứng.
- Hoàn tất thay mật khẩu hoặc gắn phương thức xác thực mới.
- Hoàn tất toàn bộ luồng khôi phục theo điều kiện của dịch vụ.

Không dùng cùng một dấu tích xanh với cùng một câu “Thành công” cho tất cả các trường hợp trên.

## 3. Chọn hình thức theo loại công việc

Không phải bước nào cũng có thể biểu diễn bằng phần trăm.

| Hình thức | Phù hợp khi | Giới hạn cần giải thích |
| --- | --- | --- |
| Danh sách bước | Người dùng cần hiểu các giai đoạn chính | Số bước không cho biết thời lượng mỗi bước |
| Thanh tiến độ có giá trị | Có tổng công việc và lượng đã hoàn tất đo được | Cần nêu rõ thanh đang đo việc gì |
| Chỉ báo đang xử lý không có phần trăm | Công việc đang diễn ra nhưng chưa biết tổng hoặc thời lượng | Phải có mô tả trạng thái và hướng xử lý khi chờ lâu |
| Mốc thời gian hoặc đồng hồ chờ | Có một thời điểm thật do máy chủ xác định | Phải phân biệt hết hạn, được gửi lại và khoảng chờ bảo vệ |
| Dòng thời gian sự kiện | Recovery kéo dài hoặc có nhiều lần bổ sung | Chỉ công bố thông tin phù hợp với quyền xem của người nhận |

Một luồng có thể kết hợp các hình thức: danh sách bước cho toàn hành trình, thanh phần trăm cho việc tải tệp và thông báo chờ cho bước xử lý thủ công.

Nếu phần trăm tải tệp đạt 100%, nhãn nên nói “Đã gửi xong dữ liệu tải lên; đang chờ máy chủ xác nhận” khi máy chủ chưa xác nhận tiếp nhận. Sau đó mới có thể chuyển sang “Tài liệu đã được tiếp nhận”.

Không biến số bước hoàn tất thành “mức độ tài khoản đã an toàn”. Bước thứ ba trong bốn bước không đồng nghĩa tài khoản đã an toàn 75%.

## 4. Lấy trạng thái nghiệp vụ từ máy chủ

Giao diện không nên tự suy tiến độ từ số lần nhấp nút, số màn hình đã đi qua hoặc thời gian đã trôi.

Một mô hình trạng thái minh họa:

| Trạng thái nội bộ | Ý nghĩa | Nội dung có thể trình bày trong ngữ cảnh được cấp quyền |
| --- | --- | --- |
| ACCEPTED | Yêu cầu đã được tiếp nhận | “Đã nhận yêu cầu.” |
| AWAITING_USER | Cần người dùng cung cấp bước tiếp theo | “Nhập mã để tiếp tục.” |
| VERIFYING | Đang xử lý bằng chứng đã gửi | “Đang kiểm tra thông tin bạn đã gửi.” |
| WAITING_REVIEW | Đang chờ xử lý thủ công | “Yêu cầu đang chờ được xem xét.” |
| WAITING_PERIOD | Đang trong khoảng chờ theo chính sách | “Bạn có thể tiếp tục từ thời điểm được hiển thị.” |
| READY_FOR_CHANGE | Đã đáp ứng điều kiện để thực hiện thay đổi cụ thể | “Bạn có thể thiết lập phương thức mới.” |
| APPLYING_CHANGE | Đang áp dụng thay đổi | “Đang lưu thay đổi bảo mật.” |
| COMPLETED | Đạt điều kiện hoàn tất đã định nghĩa | “Đã khôi phục phương thức truy cập. Hãy đăng nhập lại.” |
| EXPIRED | Giao dịch hoặc quyền tiếp tục đã hết hạn | “Yêu cầu này đã hết hạn.” |
| CANCELLED | Máy chủ xác nhận yêu cầu bị hủy | “Yêu cầu đã được hủy.” |
| UNABLE_TO_COMPLETE | Luồng này không thể tiếp tục theo kết quả xử lý | “Chưa thể hoàn tất bằng phương thức này.” |

Đây là schema minh họa, không phải tập trạng thái bắt buộc cho mọi dịch vụ. Một màn hình chưa xác thực có thể chỉ được thấy trạng thái công khai tổng quát, thay vì toàn bộ những trạng thái trong bảng.

Luồng có thể có nhánh và vòng bổ sung:

~~~mermaid
flowchart TD
    A[Đã tiếp nhận] --> B[Cần người dùng thao tác]
    B --> C[Đang xác minh]
    C --> D[Chờ xem xét hoặc khoảng chờ]
    C --> E[Được phép thực hiện thay đổi]
    D --> B
    D --> E
    E --> F[Đang áp dụng thay đổi]
    F --> G[Hoàn tất trong phạm vi đã định nghĩa]
    B --> H[Hết hạn hoặc hủy]
    D --> H
~~~

Việc quay lại bước bổ sung không nhất thiết là mất toàn bộ tiến độ. Nội dung có thể nói “Cần thêm thông tin để tiếp tục xác minh”, đồng thời giữ phần đã hoàn tất nếu máy chủ vẫn công nhận phần đó.

Không công bố các trạng thái nội bộ nhạy cảm như điểm rủi ro, điều kiện phát hiện gian lận hay chi tiết kiểm tra mà người dùng không cần biết để hành động.

## 5. Danh sách bước nên phản ánh hành trình có nhánh

Một danh sách bước minh họa cho recovery sau khi mất MFA:

1. Chọn phương thức khôi phục.
2. Xác minh quyền sở hữu.
3. Thiết lập phương thức xác thực mới.
4. Hoàn tất và đăng nhập lại.

Trong giai đoạn hai, có thể phát sinh nhập mã, chờ duyệt hoặc bổ sung thông tin. Không cần biến mỗi công việc nội bộ thành một bước mới trên đầu trang.

Nếu số bước chưa cố định, câu “Đang xác minh quyền sở hữu” có thể phù hợp hơn “Bước 2/3”. Nếu tổng số bước thay đổi, phải giải thích lý do theo nhu cầu của người dùng, không làm thanh tiến độ nhảy lùi một cách khó hiểu.

Một bước được đánh dấu hoàn tất khi máy chủ xác nhận điều kiện hoàn tất của bước đó. Chẳng hạn:

- Gửi yêu cầu kiểm tra mã chưa phải là mã đã hợp lệ.
- Nhận quyền đặt mật khẩu chưa phải là mật khẩu đã được lưu.
- Tạo công việc thu hồi session chưa phải là mọi session đã bị thu hồi.
- Gửi email thành công tới nhà cung cấp chưa chứng minh chủ tài khoản đã đọc.

Các bước tương lai nên có nhãn rõ nhưng không tạo cảm giác có thể bỏ qua. Nếu cho phép quay lại, máy chủ cần quyết định dữ liệu đã xác minh còn hiệu lực hay phải xác minh lại.

Nút “Quay lại” cũng cần phân biệt với “Hủy yêu cầu”. Quay về màn hình trước không tự đảo ngược một thay đổi bảo mật đã có hiệu lực.

## 6. Thời gian chờ cần có ý nghĩa cụ thể

Một màn hình recovery có thể chứa nhiều loại thời gian:

| Loại thời gian | Mục đích | Khi tới mốc |
| --- | --- | --- |
| Hạn dùng mã hoặc liên kết | Giới hạn quyền sử dụng một bằng chứng | Cần phản hồi theo kết quả kiểm tra của máy chủ |
| Thời điểm được gửi lại | Hạn chế lạm dụng thao tác gửi mã | Máy chủ quyết định có cho gửi lại hay không |
| Khoảng chờ bảo vệ | Trì hoãn một thay đổi nhạy cảm theo chính sách | Còn phải kiểm tra các điều kiện tiếp tục |
| Ước lượng xử lý | Giúp người dùng chuẩn bị kỳ vọng | Không tự chuyển yêu cầu sang thành công |
| Thời điểm cập nhật gần nhất | Cho biết độ mới của thông tin hiển thị | Không chứng minh nhân viên đang trực tiếp xem hồ sơ |

Mốc tính thời gian nên do máy chủ cung cấp. Giao diện có thể dùng serverTime và một đồng hồ đơn điệu để hiển thị khoảng chờ trong phiên, rồi đồng bộ lại khi tải lại hoặc kết nối trở lại. Thay đồng hồ hệ điều hành hay mở lại trang không được kéo dài thời hạn thật.

Một câu có ích khi chờ xử lý thủ công:

> Yêu cầu đang chờ được xem xét. Bạn chưa cần gửi thêm thông tin. Có thể đóng trang và kiểm tra lại bằng cách đã được hướng dẫn.

Chỉ sử dụng câu này nếu người dùng thực sự có cách quay lại và việc đóng trang không làm mất phương thức tiếp tục duy nhất.

Nếu có ước lượng đáng tin, hãy ghi “Thời gian xử lý dự kiến…” và trình bày cách xử lý khi vượt khoảng dự kiến. Nếu không có cơ sở, không tự tạo số phút hoặc vị trí hàng đợi.

Không để bộ đếm liên tục trở về cùng một con số sau mỗi lần refresh. Người dùng cần thấy cùng một mốc thời gian của cùng một giao dịch.

## 7. Tách tình trạng kết nối khỏi tình trạng recovery

Lỗi mạng không tự chứng minh yêu cầu recovery thất bại. Một thao tác có thể đã được máy chủ thực hiện dù trình duyệt không nhận được phản hồi.

Nên phân biệt hai lớp:

- **Trạng thái nghiệp vụ gần nhất:** điều máy chủ đã xác nhận về giao dịch.
- **Trạng thái quan sát:** giao diện hiện có lấy được bản cập nhật mới hay không.

Ví dụ:

> Lần cập nhật gần nhất: đang xác minh. Hiện chưa kết nối được để lấy trạng thái mới. Chúng tôi chưa xác định được kết quả tiếp theo.

Câu này chính xác hơn “Khôi phục thất bại, hãy gửi lại” khi chỉ có một lỗi timeout.

Với polling hoặc luồng cập nhật sự kiện, cần xác định:

- Tần suất cập nhật phù hợp với trạng thái và thời gian chờ dự kiến.
- Backoff và giới hạn khi kết nối lỗi hoặc bị giới hạn tốc độ.
- Cách lấy snapshot mới khi mở lại trang.
- Cách dừng quan sát khi giao dịch kết thúc hoặc quyền xem hết hạn.
- Cách phân biệt giao dịch cũ và một lần recovery mới.

Đọc trạng thái phải là thao tác quan sát. Nó không được tiêu thụ mã dùng một lần, tự gửi lại OTP, gia hạn giao dịch hoặc tự hoàn tất một thay đổi.

Khi tab ẩn hoặc thiết bị mất mạng, số lần polling có thể giảm. Việc này không làm tiến trình trên máy chủ bị “tạm dừng” trừ khi nghiệp vụ thật sự định nghĩa như vậy.

## 8. Đồng bộ khi phản hồi đến chậm hoặc có nhiều tab

Hai phản hồi có thể đến theo thứ tự khác với thứ tự máy chủ tạo ra chúng. Nếu giao diện áp dụng mọi phản hồi ngay khi nhận được, người dùng có thể thấy “Hoàn tất” rồi quay về “Đang xử lý”.

Một snapshot hiển thị có thể mang mã phiên bản tăng theo từng giao dịch:

~~~json
{
  "viewVersion": 15,
  "displayStage": "WAITING_REVIEW",
  "messageKey": "recovery.review.waiting",
  "statusAsOf": "2026-11-23T09:00:00Z",
  "serverTime": "2026-11-23T09:00:02Z",
  "nextPollAfterSeconds": 30,
  "estimatedCompletionAt": null,
  "canLeavePage": true,
  "allowedActions": ["VIEW_HELP"]
}
~~~

Các tên trường và giá trị chỉ minh họa hợp đồng dữ liệu, không phải cấu hình đang được ghi vào module.

Giao diện cần liên kết phản hồi với đúng giao dịch đang hiển thị và bỏ qua phiên bản cũ hơn của giao dịch đó. Không so sánh phiên bản của hai lần recovery khác nhau như thể chúng thuộc cùng một chuỗi.

Một trường hợp xử lý:

1. Tab A nhận snapshot phiên bản 15 và hiển thị đang chờ duyệt.
2. Tab B thực hiện bước bổ sung, máy chủ chuyển sang phiên bản 16.
3. Tab A lấy trạng thái mới và cập nhật sang phiên bản 16.
4. Một phản hồi phiên bản 15 đến muộn không được ghi đè phiên bản 16.

Việc ngăn nút bấm lặp trên trình duyệt giúp giảm nhầm lẫn nhưng không đủ để ngăn thực hiện nghiệp vụ hai lần. Các thao tác thay đổi vẫn cần cơ chế chống lặp phù hợp và kiểm tra trạng thái ở máy chủ.

allowedActions giúp giao diện biết lựa chọn nào nên được trình bày. Sửa mảng này trên trình duyệt không tạo thêm quyền; máy chủ phải tự kiểm tra khi nhận từng hành động.

canLeavePage cũng là một cam kết về trải nghiệm. Chỉ trả về true khi có cơ chế tiếp tục thật sự phù hợp với giao dịch. Không dùng giá trị này nếu rời trang làm mất một bí mật mà hệ thống không thể cấp lại an toàn.

## 9. Công bố tiến độ mà không làm lộ tài khoản

Trang theo dõi recovery có thể trở thành công cụ dò tài khoản nếu nó trả thông tin chi tiết chỉ dựa trên email hoặc một mã hồ sơ dễ đoán.

Cần tách hai mức quan sát:

| Ngữ cảnh | Thông tin có thể cung cấp theo thiết kế |
| --- | --- |
| Người dùng mới gửi định danh trên trang công khai | Phản hồi tổng quát không xác nhận tài khoản tồn tại |
| Người có quyền theo dõi giao dịch recovery cụ thể | Trạng thái của giao dịch trong phạm vi quyền được cấp |
| Người đã xác minh đủ điều kiện cho bước nhạy cảm | Hướng dẫn và hành động tiếp theo tương ứng với quyền đó |

Phản hồi công khai có thể là:

> Nếu thông tin phù hợp với tài khoản có thể khôi phục, chúng tôi sẽ gửi hướng dẫn qua kênh đã đăng ký.

Không chuyển sang “Đang xác minh MFA của tài khoản này” chỉ vì vài giây đã trôi qua. Thông tin về cách xác thực cũng có thể làm lộ rằng tài khoản tồn tại.

OWASP khuyến nghị phản hồi nhất quán cho yêu cầu quên mật khẩu và tránh khác biệt thời gian làm lộ sự tồn tại của tài khoản. Nguyên tắc đó cần được xem xét cho cả các phản hồi tiến độ công khai, không chỉ nút gửi yêu cầu đầu tiên. Xem [Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

Quyền theo dõi nên được ràng buộc với một giao dịch và có giới hạn thích hợp. Nó không mặc nhiên cho phép đặt mật khẩu, gỡ MFA hoặc tạo session đầy đủ. Mã tham chiếu dùng khi liên hệ hỗ trợ cũng không nên tự mang quyền xem thông tin nhạy cảm.

Không đưa bí mật theo dõi, OTP hoặc token recovery vào log, hệ thống phân tích hay URL chuyển tới bên thứ ba. Nếu cơ chế tiếp tục dùng liên kết mang quyền, cần kiểm soát rò rỉ và thời hạn của chính liên kết đó; không coi việc có một URL là đủ an toàn.

Nội dung tiến độ chỉ nên nêu chi tiết giúp người dùng hành động. Câu “Cần thêm một bước xác minh” thường phù hợp hơn việc công khai ngưỡng điểm gian lận hoặc quy tắc thiết bị đang được áp dụng.

## 10. Hỗ trợ người dùng trình đọc màn hình

Thông tin tiến độ cần được nhận biết bằng văn bản và ngữ nghĩa giao diện, thay vì chỉ bằng màu hoặc chuyển động.

Theo giải thích của W3C về WCAG 2.2 SC 4.1.3, các thông báo trạng thái thuộc phạm vi tiêu chí cần có cách xác định bằng chương trình để công nghệ hỗ trợ có thể trình bày mà không phải chuyển focus tới chúng. Xem [Understanding Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

Một ví dụ danh sách bước:

~~~html
<section aria-labelledby="recovery-heading">
  <h2 id="recovery-heading">Tiến độ khôi phục tài khoản</h2>

  <ol aria-label="Các giai đoạn khôi phục">
    <li>Chọn phương thức — đã hoàn tất</li>
    <li aria-current="step">Xác minh quyền sở hữu — đang xử lý</li>
    <li>Thiết lập phương thức mới — chưa bắt đầu</li>
    <li>Hoàn tất và đăng nhập lại — chưa bắt đầu</li>
  </ol>

  <p id="recovery-status" role="status" aria-atomic="true">
    Đang kiểm tra thông tin bạn đã gửi. Bạn chưa cần nhập thêm.
  </p>
</section>
~~~

Vùng thông báo nên được tạo trước khi có thay đổi cần công bố. Khi trạng thái chuyển từ chờ sang cần nhập mã, cập nhật thông điệp có nghĩa thay vì chỉ thay một con số.

Không thông báo lại cùng một câu ở mỗi lần polling. Một bộ đếm cập nhật từng giây cũng không nên làm trình đọc màn hình liên tục đọc lại. Có thể công bố những thay đổi quan trọng như được phép gửi lại hoặc mã đã hết hạn, trong khi vẫn giữ thời gian trực quan cho người cần xem.

Với thanh tiến độ đo được, một ví dụ riêng cho tải tệp:

~~~html
<p id="upload-label">Tiến độ tải tài liệu lên</p>

<div role="progressbar"
     aria-labelledby="upload-label"
     aria-valuemin="0"
     aria-valuemax="100"
     aria-valuenow="42">
  42%
</div>

<p>Đây là tiến độ gửi tệp, chưa phải kết quả xác minh.</p>
~~~

WAI-ARIA định nghĩa progressbar và các thuộc tính giá trị liên quan. Khi tiến độ không xác định, không đặt aria-valuenow thành một phần trăm giả. Thanh tiến độ cần tên truy cập và thông tin phù hợp với việc nó đang đo. Xem [WAI-ARIA: progressbar](https://www.w3.org/TR/wai-aria-1.2/#progressbar).

Các thành phần chỉ báo tiến độ không tự tạo thành một vùng thông báo liên tục. Khi cần thông báo thay đổi, sử dụng cơ chế phù hợp và tránh đọc quá nhiều thông tin lặp lại.

Nếu một bước mới tạo ra biểu mẫu, cần quản lý tiêu đề và focus để người dùng tìm được việc tiếp theo. Không tự chuyển focus về chỉ báo mỗi khi máy chủ trả snapshot mới.

Ngoài ra, cần có nhãn trạng thái bằng chữ, thứ tự đọc hợp lý, độ tương phản phù hợp và phương án giảm chuyển động. Một biểu tượng xanh hoặc hiệu ứng thanh chạy không đủ để mô tả thành công, lỗi hay chờ xử lý.

## 11. Viết thông điệp đi cùng hành động cụ thể

Mỗi trạng thái nên đi cùng một lời giải thích và lựa chọn phù hợp. Chỉ đưa ra thao tác mà dịch vụ thật sự hỗ trợ.

| Trạng thái | Thông điệp minh họa | Hành động phù hợp |
| --- | --- | --- |
| Đang chờ người dùng nhập mã | “Nhập mã để tiếp tục xác minh.” | Nhập mã; xem cách dùng phương thức khác nếu được phép |
| Máy chủ đang xử lý | “Đang kiểm tra thông tin bạn đã gửi.” | Chờ; xem trợ giúp |
| Đang chờ xét duyệt | “Yêu cầu đang chờ được xem xét. Bạn chưa cần gửi thêm.” | Xem hướng dẫn quay lại nếu có |
| Mất kết nối cập nhật | “Chưa lấy được trạng thái mới. Kết quả trước đó vẫn được hiển thị bên dưới.” | Thử kết nối lại |
| Giao dịch hết hạn | “Yêu cầu này đã hết hạn. Hãy bắt đầu lại để nhận hướng dẫn mới.” | Bắt đầu giao dịch mới theo chính sách |
| Thay đổi đang được lưu | “Đang lưu thay đổi bảo mật. Chưa xác nhận hoàn tất.” | Chờ kết quả hoặc tra cứu lại cùng giao dịch |
| Hoàn tất phạm vi recovery | “Đã hoàn tất khôi phục. Hãy đăng nhập lại bằng phương thức vừa thiết lập.” | Đi tới luồng đăng nhập thông thường |

Nếu người dùng nhấn “Hủy”, giao diện có thể tạm hiển thị “Đang yêu cầu hủy”. Chỉ chuyển sang “Đã hủy” khi máy chủ xác nhận. Nếu thay đổi đã hoàn tất trước yêu cầu hủy, cần hiển thị kết quả thực tế và hướng dẫn phù hợp, thay vì giả vờ đã đảo ngược.

Tránh để nút “Thử lại” có nghĩa không rõ. “Tải lại trạng thái” khác với “Gửi lại mã” và “Bắt đầu yêu cầu mới”. Mỗi hành động có thể có tác động, giới hạn và yêu cầu xác minh khác nhau.

## 12. Ví dụ xuyên suốt: mất điện thoại chứa MFA

Minh còn nhớ mật khẩu nhưng không thể sử dụng điện thoại có ứng dụng xác thực. Dịch vụ cho phép một quy trình recovery theo điều kiện đã xác định.

**Chọn phương thức:** Minh thấy các giai đoạn chính và lựa chọn được phép. Chọn một phương thức chỉ chuyển giao diện tới bước tương ứng; chưa được đánh dấu xác minh thành công.

**Gửi bằng chứng:** Minh gửi thông tin cần thiết. Khi máy chủ xác nhận tiếp nhận, màn hình chuyển sang “Đang kiểm tra thông tin”. Nếu có tải tài liệu, thanh tải 100% được tách khỏi giai đoạn xác minh.

**Chờ xử lý:** Yêu cầu cần xét duyệt. Màn hình hiển thị điều đã được xác nhận, thời điểm cập nhật và cách quay lại. Nếu không có ước lượng đáng tin, không xuất hiện một thanh 90% đứng yên.

**Mất mạng:** Minh thấy thông báo chưa lấy được trạng thái mới. Ứng dụng không tự gửi lại bằng chứng và không tạo yêu cầu recovery thứ hai chỉ vì polling lỗi.

**Được phép thay đổi:** Máy chủ xác nhận Minh có thể thiết lập MFA mới. Giao diện chuyển sang giai đoạn tương ứng. Quyền đó có phạm vi và thời hạn riêng; không tự biến thành quyền truy cập mọi chức năng của tài khoản.

**Áp dụng thay đổi:** Minh hoàn tất thiết lập. Máy chủ xác nhận phương thức mới đã được gắn. Nếu còn công việc bảo vệ bắt buộc chưa xong, màn hình mô tả trạng thái còn lại và giới hạn truy cập thực tế.

**Kết thúc:** Khi điều kiện hoàn tất của luồng đã đạt, giao diện hướng dẫn đăng nhập lại. Những tuyên bố như đã thu hồi mọi session chỉ xuất hiện khi cơ chế của dịch vụ thực sự xác nhận điều đó.

Nếu lúc này một tab cũ nhận phản hồi “Đang chờ duyệt” đến muộn, phiên bản trạng thái ngăn nó ghi đè kết quả mới. Khi quyền theo dõi hết hạn, tab cũ dừng cập nhật và hướng dẫn tiếp tục bằng cách phù hợp.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách thiết kế phù hợp hơn |
| --- | --- | --- |
| Tăng phần trăm theo đồng hồ dù không có dữ liệu | Người dùng tin vào tiến độ giả | Dùng trạng thái có ý nghĩa hoặc phần trăm đo được |
| Đồng nhất timeout với recovery thất bại | Người dùng tạo yêu cầu lặp hoặc bỏ qua kết quả đã có | Tra cứu lại giao dịch và nêu giới hạn thông tin hiện tại |
| Hiển thị “đang xử lý” khi chờ người dùng | Người dùng chờ vô ích | Nêu rõ cần nhập mã hay thực hiện bước nào |
| Tải lại trang là mất toàn bộ tiến độ | Gây thao tác lặp và nhầm mã | Khôi phục snapshot theo quyền tiếp tục hợp lệ |
| Đếm ngược về không là cho phép bỏ bước | Giao diện trở thành đường vượt kiểm soát | Máy chủ quyết định điều kiện của từng hành động |
| Mọi lần polling đều công bố lại qua trình đọc màn hình | Gây gián đoạn liên tục | Chỉ công bố thay đổi có ý nghĩa |
| Tiến độ công khai làm lộ MFA hoặc tài khoản tồn tại | Tăng khả năng dò thông tin | Tách phản hồi công khai và trạng thái có kiểm soát truy cập |
| Một dấu tích xanh đại diện cho cả recovery và toàn bộ bảo vệ tài khoản | Tạo cảm giác an toàn quá sớm | Nêu rõ phạm vi công việc đã hoàn tất |

Chỉ báo tiến độ đáng tin cần nối được trạng thái thật, thông điệp dễ hiểu và hành động tiếp theo. Trong khôi phục tài khoản, sự rõ ràng đó giúp người dùng tiếp tục đúng cách mà vẫn giữ nguyên các điều kiện xác minh và kiểm soát truy cập.
