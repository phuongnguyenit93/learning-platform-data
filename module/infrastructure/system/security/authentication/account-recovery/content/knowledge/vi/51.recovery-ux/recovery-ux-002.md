# Progressive disclosure trong trải nghiệm khôi phục tài khoản

## 1. Progressive disclosure giải quyết vấn đề gì?

Người dùng đang mất quyền truy cập tài khoản thường không biết ngay mình cần thực hiện quy trình nào. Họ có thể quên mật khẩu, mất thiết bị MFA, không còn passkey dùng được hoặc không truy cập được kênh nhận mã. Nếu màn hình đầu tiên trình bày mọi phương thức, mọi tình huống lỗi và toàn bộ chính sách an toàn, người dùng phải tự đọc rồi phân loại một lượng thông tin lớn trước khi bắt đầu.

**Progressive disclosure** là cách trình bày thông tin và hành động theo từng lớp: hiển thị những gì cần để quyết định ở thời điểm hiện tại, rồi mở thêm chi tiết khi người dùng cần hoặc khi ngữ cảnh đã thay đổi.

Trong khôi phục tài khoản, nguyên tắc này giúp trả lời tuần tự ba câu hỏi:

- Tôi đang ở bước nào và cần làm gì ngay bây giờ?
- Nếu không thể thực hiện cách này, tôi đi tiếp bằng đường nào?
- Hành động sắp xác nhận sẽ thay đổi điều gì đối với tài khoản?

Ví dụ, ở bước nhập định danh, người dùng cần biết thông tin phải nhập và cách tiếp tục. Họ chưa cần đọc toàn bộ hướng dẫn thay MFA, thu hồi session hay đăng ký passkey mới. Những nội dung đó trở nên cần thiết ở các nhánh và thời điểm tương ứng.

Mục tiêu không phải làm mọi màn hình ngắn nhất có thể. Mục tiêu là giảm việc đọc và lựa chọn không cần thiết mà vẫn giúp người dùng nhìn thấy thông tin ảnh hưởng đến quyết định của mình.

## 2. Hai cách áp dụng và một ranh giới quan trọng

Có hai cách thường gặp:

| Cách áp dụng | Cách hoạt động | Ví dụ trong khôi phục |
| --- | --- | --- |
| Mở thêm thông tin trên cùng màn hình | Người dùng chủ động mở phần giải thích tùy nhu cầu | “Vì sao tôi cần bước xác minh này?” |
| Tiết lộ theo tiến trình | Màn hình tiếp theo xuất hiện sau một thao tác hoặc kết quả được xác nhận | Hiển thị tác vụ khôi phục được phép sau khi server đánh giá bằng chứng |

Hai cách có thể cùng tồn tại. Một bước nhập mã vẫn có phần trợ giúp mở rộng, còn bước đặt mật khẩu mới chỉ xuất hiện khi giao dịch được phép thực hiện tác vụ đó.

Tuy nhiên, **thu gọn nội dung và giới hạn quyền truy cập là hai cơ chế khác nhau**. Một phần bị ẩn bằng CSS, thuộc tính `hidden` hoặc trạng thái component vẫn có thể nằm trong HTML, dữ liệu mạng hoặc bộ nhớ phía client.

Vì vậy, không gửi số điện thoại đầy đủ, danh sách yếu tố xác thực hay tác vụ chưa được phép rồi trông chờ giao diện giấu chúng. Server chỉ trả dữ liệu phù hợp với quyền xem của ngữ cảnh hiện tại và kiểm tra lại quyền khi nhận hành động tiếp theo.

## 3. Phân biệt thông tin thiết yếu và thông tin bổ sung

Trước khi đưa nội dung vào vùng thu gọn, cần xác định người dùng có phải đọc nó để hoàn thành bước một cách có hiểu biết hay không.

| Nội dung | Cách trình bày phù hợp |
| --- | --- |
| Tiêu đề bước và yêu cầu nhập hiện tại | Hiển thị trực tiếp |
| Lỗi đang ngăn tiếp tục | Hiển thị trực tiếp, gắn với trường hoặc bước liên quan |
| Hệ quả của thao tác thay yếu tố xác thực | Hiển thị trước khi xác nhận tác vụ đó |
| Thông tin về thời gian chờ đang chặn gửi lại | Hiển thị tại hành động gửi lại |
| Đường đi khi mất quyền truy cập phương thức hiện tại | Có dấu hiệu hoặc hành động rõ ràng trên màn hình |
| Giải thích thuật ngữ hoặc ví dụ phụ | Có thể cho mở thêm |
| Hướng dẫn xử lý sự cố chỉ một số người gặp | Có thể cho mở thêm nếu không che đường thoát chính |
| Chi tiết triển khai kỹ thuật của hệ thống | Không đưa vào luồng người dùng nếu không giúp họ quyết định |

Không giấu thông báo “Thay MFA sẽ làm phương thức cũ không còn dùng được” dưới một liên kết mơ hồ nếu đó là hệ quả thực tế của thao tác sắp xác nhận. Cũng không để người không còn điện thoại phải mở nhiều lớp trợ giúp mới tìm được phương án khác.

[GOV.UK Design System về thành phần Details](https://design-system.service.gov.uk/components/details/) khuyến nghị dùng phần mở rộng cho thông tin chỉ một số người cần, đồng thời giữ thông tin đa số người dùng cần ở trạng thái dễ thấy.

## 4. Xây dựng luồng theo trạng thái người dùng cần hiểu

Một luồng minh họa có thể tổ chức như sau. Phương thức và bằng chứng cụ thể phải theo chính sách khôi phục của sản phẩm; bảng không mặc định rằng mọi hệ thống đều hỗ trợ mọi lựa chọn.

| Trạng thái | Nội dung chính | Nội dung có thể mở thêm | Điều chưa được phép suy ra |
| --- | --- | --- | --- |
| Bắt đầu | Nhập thông tin định danh và gửi yêu cầu | Giải thích thông tin được chấp nhận | Tài khoản chắc chắn tồn tại |
| Yêu cầu đã được tiếp nhận | Hướng dẫn kiểm tra kênh khôi phục theo phản hồi công khai | Cách tìm thư hoặc khắc phục chưa nhận được thông báo | Người yêu cầu đã kiểm soát tài khoản |
| Có ngữ cảnh xác minh phù hợp | Hiển thị hành động hoặc phương thức server cho phép | Giải thích từng phương thức | Mọi yếu tố xác thực đều có thể bị thay |
| Đang thực hiện thử thách | Nhập mã hoặc cung cấp bằng chứng cần thiết | Giải thích định dạng, trợ giúp theo phương thức | Qua một bước là đã đủ mọi điều kiện |
| Được phép khôi phục một tác vụ | Thực hiện đúng tác vụ được cấp, kèm hệ quả liên quan | Hướng dẫn phụ khi cần | Quyền khôi phục tương đương session đầy đủ |
| Hoàn tất | Kết quả thực tế và hành động tiếp theo | Hướng dẫn xem lại an toàn tài khoản | Mọi sự cố bảo mật đã được giải quyết |

Ở mỗi màn hình, có thể áp dụng một cấu trúc nhất quán:

1. Tiêu đề mô tả việc cần làm.
2. Một đoạn hướng dẫn ngắn, gắn với trạng thái hiện tại.
3. Trường nhập hoặc lựa chọn cần thiết.
4. Hành động chính và đường đi thay thế dễ nhận biết.
5. Phần giải thích bổ sung nếu có nhu cầu thực sự.

Nếu các nhánh có độ dài khác nhau, không nhất thiết ghi “Bước 2/3”. Một tổng số bước không đúng sau khi người dùng đổi phương thức dễ tạo cảm giác bị kéo dài quy trình. Có thể dùng nhãn giai đoạn như “Xác minh” và “Khôi phục” cùng mô tả tiến độ trung thực.

## 5. Tiết lộ đúng lúc cũng phải đúng quyền xem

Ở bước công khai, một thông báo như sau có thể phù hợp:

> Nếu thông tin khớp với một tài khoản đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.

Thông điệp này không nên đi kèm một trường dữ liệu cho biết `accountExists`, một danh sách MFA đã đăng ký hoặc địa chỉ đã che chỉ xuất hiện khi tài khoản tồn tại. Khác biệt ở lớp dữ liệu vẫn có thể làm lộ điều mà câu chữ đang cố giữ kín.

Đối với yêu cầu đặt lại mật khẩu, [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại, đồng thời tránh khác biệt thời gian giúp dò tài khoản. Câu chữ chung chỉ là một phần của hành vi đó.

Sau khi có bằng chứng phù hợp, server có thể cho phép một ngữ cảnh hạn chế xem thêm thông tin. Mức được tiết lộ phụ thuộc bằng chứng và mục đích; không mặc định rằng một định danh đã nhập hoặc một lần mở trang đủ để xem danh sách liên hệ.

Ví dụ hợp đồng phản hồi công khai dưới đây chỉ minh họa cấu trúc trình bày:

```json
{
  "view": "CHECK_RECOVERY_CHANNEL",
  "messageKey": "recovery.request.received",
  "actions": [
    "OPEN_DELIVERY_HELP",
    "EDIT_IDENTIFIER",
    "OPEN_RECOVERY_OPTIONS"
  ]
}
```

Các hành động này biểu thị điều giao diện có thể đề nghị. Chúng không phải bằng chứng cấp quyền và không thay thế việc server kiểm tra ngữ cảnh khi người dùng kích hoạt. “Mở các lựa chọn khôi phục” ở bước công khai có thể dẫn đến hướng dẫn chung, không nhất thiết trả về cấu hình riêng của tài khoản.

## 6. Ví dụ: trợ giúp có thể mở thêm nhưng đường thoát luôn rõ

Giả sử người dùng đang ở màn hình kiểm tra kênh khôi phục. Hướng dẫn xử lý thư chưa đến là thông tin bổ sung; đường sửa định danh và đường không còn truy cập được kênh hiện tại cần dễ thấy.

```html
<main aria-labelledby="recovery-title">
  <h1 id="recovery-title">Kiểm tra kênh khôi phục</h1>

  <p>
    Nếu thông tin khớp với một tài khoản đủ điều kiện,
    hướng dẫn sẽ được gửi qua kênh đã đăng ký.
  </p>

  <p>
    Làm theo hướng dẫn của dịch vụ và không chia sẻ mã khôi phục
    với người khác.
  </p>

  <p>
    <a href="/account-recovery/start">Sửa thông tin đã nhập</a>
  </p>
  <p>
    <a href="/account-recovery/options">
      Tôi không còn truy cập được kênh khôi phục
    </a>
  </p>

  <details>
    <summary>Tôi chưa nhận được hướng dẫn</summary>
    <p>
      Nếu bạn đang kiểm tra email, hãy xem cả thư mục thư rác
      và kiểm tra lại thông tin đã nhập.
    </p>
    <p>
      Nếu dịch vụ đang yêu cầu chờ trước khi gửi lại,
      hãy làm theo thời gian được hiển thị tại hành động gửi lại.
    </p>
  </details>
</main>
```

Các đường dẫn trên minh họa vai trò điều hướng. Việc sửa định danh hoặc đổi phương thức trong một ứng dụng thực tế cần xử lý trạng thái giao dịch tương ứng ở server.

`details` và `summary` cung cấp một cấu trúc HTML có sẵn để mở, đóng phần nội dung bổ sung. Không cần thêm một `button` khác bên trong `summary` chỉ để thực hiện cùng thao tác.

Phần mở rộng không được chứa lỗi bắt buộc phải sửa nhưng lại đóng kín sau khi gửi biểu mẫu thất bại. Khi một nội dung trở thành thiết yếu ở trạng thái mới, cần đưa nó vào nơi dễ thấy hoặc mở vùng chứa phù hợp rồi dẫn người dùng đến vấn đề.

## 7. Khi dùng disclosure tùy chỉnh

Nếu hệ thống thiết kế cần một disclosure tùy chỉnh, điều khiển phải có ngữ nghĩa và trạng thái rõ ràng. Với một nút HTML, có thể biểu thị trạng thái qua `aria-expanded` và liên kết tới vùng được điều khiển bằng `aria-controls`.

```html
<button
  type="button"
  id="recovery-help-toggle"
  aria-expanded="false"
  aria-controls="recovery-help-panel"
>
  Vì sao cần thêm bước xác minh?
</button>

<div id="recovery-help-panel" hidden>
  <p>
    Dịch vụ cần thêm bằng chứng trước khi cho phép thay đổi
    phương thức truy cập tài khoản.
  </p>
</div>
```

```javascript
const helpToggle = document.getElementById('recovery-help-toggle');
const helpPanel = document.getElementById('recovery-help-panel');

function setRecoveryHelpExpanded(expanded) {
  if (!expanded && helpPanel.contains(document.activeElement)) {
    helpToggle.focus();
  }

  helpPanel.hidden = !expanded;
  helpToggle.setAttribute('aria-expanded', String(expanded));
}

helpToggle.addEventListener('click', () => {
  const isExpanded = helpToggle.getAttribute('aria-expanded') === 'true';
  setRecoveryHelpExpanded(!isExpanded);
});
```

Theo [WAI-ARIA APG — Disclosure Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), điều khiển mở/đóng có vai trò button, hỗ trợ kích hoạt bằng `Enter` và `Space`, đồng thời phản ánh trạng thái qua `aria-expanded`. Dùng `button` native giúp có sẵn hành vi bàn phím cơ bản đó.

Khi chỉ mở phần giải thích, thường có thể giữ focus trên nút để người dùng tự tiếp tục đọc hoặc nhấn `Tab`. Nếu chuyển hẳn sang bước mới, cần xử lý focus theo ngữ cảnh điều hướng. Không tự kéo focus khỏi ô nhập chỉ vì một phần trợ giúp vừa được cập nhật.

Nếu một vùng sắp đóng đang chứa phần tử có focus, cần đưa focus về vị trí phù hợp trước khi ẩn nó. Không chỉ thay biểu tượng mũi tên mà quên đồng bộ trạng thái hiển thị và trạng thái truy cập.

## 8. Điều phối nhánh mà không tạo đường bỏ qua xác minh

Một hành động như “Thử cách khác” rất quan trọng với người mất thiết bị. Tuy nhiên, hành động này chỉ mở một nhánh được chính sách cho phép; nó không tự giảm yêu cầu chứng minh quyền khôi phục.

Ví dụ, một người không còn dùng được passkey có thể được hướng dẫn thử một thiết bị đã đăng ký khác hoặc một phương án khôi phục được hỗ trợ. Không nên khẳng định rằng mất một thiết bị luôn đồng nghĩa mất mọi passkey, cũng không tự coi một phương án thay thế là đủ cho mọi tài khoản.

Ở phía server, có thể hình dung việc mở lớp thông tin tiếp theo như sau:

```text
Nhận hành động của người dùng
    ↓
Tải ngữ cảnh khôi phục và trạng thái hiện tại
    ↓
Kiểm tra hành động có hợp lệ tại trạng thái này không
    ↓
Đánh giá bằng chứng và điều kiện chính sách
    ↓
Thực hiện chuyển trạng thái nếu được phép
    ↓
Trả đúng dữ liệu và hành động người dùng được xem tiếp
```

Không dùng một cờ client như `showResetForm=true` hoặc `currentStep=4` để cho phép đổi mật khẩu. Người yêu cầu có thể thay cờ, gọi trực tiếp endpoint hoặc gửi lại yêu cầu cũ.

Khi chuyển phương thức, phải quyết định rõ thử thách trước còn hiệu lực hay bị thay thế, hạn mức được tính thế nào và bằng chứng nào được giữ lại. Đây là quyết định trạng thái của server; đóng một panel không tự hủy token, còn mở panel khác không tự tạo bằng chứng mới.

Quyền đặt lại mật khẩu, thay MFA, thu hồi session và thêm passkey cũng cần phạm vi rõ ràng. Giao diện không nên đưa tất cả tác vụ vào một nhóm mang tên “Khôi phục hoàn tất” nếu giao dịch chỉ được phép thực hiện một tác vụ.

## 9. Lỗi, chờ xử lý và hết hạn cũng cần được tiết lộ đúng lúc

Progressive disclosure hữu ích nhất khi nội dung mở thêm phù hợp với vấn đề đang xảy ra, thay vì đưa mọi lỗi dự đoán được lên màn hình từ đầu.

| Tình huống | Cần hiển thị ngay | Chi tiết có thể mở thêm |
| --- | --- | --- |
| Thiếu dữ liệu bắt buộc | Trường cần sửa và cách sửa ngắn gọn | Ví dụ định dạng nếu cần |
| Chưa nhận được thông báo | Hành động chính và trạng thái chờ phù hợp | Hướng dẫn tìm thư hoặc kiểm tra thiết bị |
| Yêu cầu đang được xử lý | Xác nhận hệ thống đang xử lý, tránh gửi lặp | Giải thích thêm nếu có độ trễ đáng kể |
| Mã không dùng được | Thông báo an toàn và đường thử lại hoặc bắt đầu lại | Giải thích cách dùng đúng loại mã |
| Giao dịch hết hạn | Nêu rõ không thể tiếp tục bằng giao dịch cũ | Cách bắt đầu một giao dịch mới |
| Cần xem xét thêm | Trạng thái tiếp nhận và hành động người dùng còn có thể làm | Giải thích quy trình ở mức phù hợp |

Không hứa “sắp xong” nếu nhánh hỗ trợ còn cần xem xét thủ công và chưa có thời gian xác định. Nếu có khoảng chờ do chính sách an toàn, cần giải thích hành động tiếp theo mà người dùng có thể thực hiện; không trình bày khoảng chờ như một sự cố kỹ thuật nếu đó không phải sự thật.

Thông tin thời gian hết hạn và thời gian được gửi lại phải dựa trên trạng thái server. Mở lại trang hoặc đóng rồi mở trợ giúp không được làm mới thời hạn thực của thử thách.

Khi lỗi liên quan đến bí mật hoặc trạng thái tài khoản, nội dung chi tiết vẫn phải tuân thủ quyền tiết lộ. Không để phần “Xem chi tiết lỗi” làm lộ tài khoản có tồn tại, yếu tố nào đang được đăng ký hoặc cơ chế đánh giá rủi ro nội bộ.

## 10. Quay lại, tải lại và tiếp tục trên thiết bị khác

Người dùng khôi phục thường phải chuyển từ trình duyệt sang ứng dụng email hoặc sang thiết bị khác. Trải nghiệm cần phân biệt trạng thái trình bày với trạng thái giao dịch:

- Việc một phần trợ giúp đang mở hay đóng là trạng thái trình bày.
- Việc thử thách đã được xác minh, đã hết hạn hoặc đã dùng là trạng thái nghiệp vụ.
- Việc có được phép đặt lại mật khẩu hay thay MFA là quyết định cấp quyền trong giao dịch.

Khi tải lại, server phải xác định lại màn hình phù hợp từ trạng thái thực. Không phục hồi quyền chỉ bằng bước cuối cùng được lưu trong `localStorage`. Nếu có lưu sở thích trình bày, tránh lưu token, mã dự phòng hoặc bằng chứng nhạy cảm cùng với chúng.

Khi nhấn quay lại, người dùng có thể sửa thông tin hoặc đổi phương thức, nhưng hành động đó không tự đảo ngược một token đã dùng hoặc khôi phục lại quyền đã hết hạn. Nếu thay đổi định danh làm ngữ cảnh cũ không còn phù hợp, giao diện cần giải thích bước phải làm lại.

Với giao dịch hoàn tất trên tab khác, tab hiện tại cần xử lý phản hồi mới từ server và dẫn tới trạng thái đúng. Không để một biểu mẫu cũ tiếp tục khẳng định người dùng còn được phép sử dụng thử thách đó.

Một luồng tốt cũng không buộc người dùng đọc lại mọi hướng dẫn đã hiểu chỉ vì họ mở phần trợ giúp. Giữ việc khám phá thông tin bổ sung độc lập với việc bắt đầu lại giao dịch, trừ khi chính người dùng chọn hành động làm thay đổi giao dịch.

## 11. Những cách áp dụng phản tác dụng

| Thiết kế | Vì sao gây khó khăn | Hướng thay đổi |
| --- | --- | --- |
| Hiển thị tất cả phương thức và chính sách trên trang đầu | Người dùng phải tự phân loại quá nhiều thông tin | Tổ chức theo quyết định và trạng thái hiện tại |
| Mọi đoạn văn đều nằm trong accordion | Người dùng phải mở nhiều nơi để hiểu bước cơ bản | Giữ nội dung thiết yếu ở ngoài vùng thu gọn |
| Liên kết chỉ ghi “Xem thêm” | Khó biết nội dung có giải quyết vấn đề của mình không | Dùng nhãn mô tả như “Tôi chưa nhận được mã” |
| Giấu đường mất thiết bị trong nhiều lớp trợ giúp | Người dùng bị mắc kẹt ở phương thức không thể dùng | Hiển thị đường thay thế dễ tìm |
| Tự gửi OTP khi mở phương thức | Hành động tìm hiểu tạo tác dụng ngoài mong đợi | Tách mở thông tin và xác nhận gửi |
| Chỉ ẩn biểu mẫu chưa được phép bằng CSS | Giao diện bị dùng như cơ chế cấp quyền | Kiểm tra dữ liệu và hành động ở server |
| Luôn đưa focus về đầu trang khi mở trợ giúp | Người dùng mất vị trí đang đọc hoặc nhập | Xử lý focus theo loại thay đổi |
| Giấu hệ quả thay MFA trong phần chú thích | Người dùng không hiểu tác động trước khi xác nhận | Hiển thị hệ quả tại điểm quyết định |

Một số lựa chọn có thể cần nhiều lời giải thích hơn, nhất là khi liên quan đến thiết bị bị mất hoặc nghi ngờ tài khoản bị chiếm đoạt. Không áp dụng quy tắc cứng như “mỗi màn hình chỉ được có một câu” nếu điều đó làm thiếu thông tin quyết định.

## 12. Tình huống vận dụng

Một người dùng quên mật khẩu và không còn điện thoại chứa ứng dụng MFA. Họ vẫn truy cập được một kênh liên hệ đã đăng ký và có mã dự phòng được lưu từ trước. Dịch vụ phải quyết định tổ hợp bằng chứng nào đáp ứng chính sách; giao diện chỉ trình bày các nhánh được phép.

Một cách tổ chức phù hợp là:

1. Màn hình đầu yêu cầu thông tin định danh cần thiết, có đường trợ giúp rõ ràng.
2. Phản hồi công khai hướng dẫn bước tiếp theo mà không xác nhận cấu hình tài khoản.
3. Sau khi có ngữ cảnh xác minh phù hợp, giao diện hiển thị những tác vụ và phương thức được server cho phép.
4. Khi người dùng cho biết mất điện thoại, nhánh tiếp theo giải thích bằng chứng thay thế cần cung cấp theo chính sách.
5. Phần giải thích dài về mã dự phòng có thể mở thêm; yêu cầu nhập mã và lỗi cần sửa vẫn luôn dễ thấy.
6. Trước một thay đổi như thay MFA, hệ quả thực tế được hiển thị trực tiếp để người dùng xác nhận có hiểu biết.
7. Kết quả cuối nói rõ tác vụ nào đã hoàn thành và hành động tiếp theo, như đăng nhập lại hoặc xem lại thiết bị theo chính sách.

Thiết kế progressive disclosure cho khôi phục tài khoản cần thống nhất ba điều: **thông tin người dùng cần ngay lúc này, thông tin ngữ cảnh hiện tại được phép xem và hành động server thực sự cho phép thực hiện**. Khi ba điều đó khớp nhau, giao diện có thể dễ hiểu hơn mà vẫn bảo toàn các ranh giới xác minh và quyền khôi phục.
