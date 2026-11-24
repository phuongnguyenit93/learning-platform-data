# Screen reader recovery flow

## 1. Mục tiêu của luồng khôi phục với trình đọc màn hình

Người dùng trình đọc màn hình cần biết mình đang ở bước nào, điều khiển nào đang được chọn, yêu cầu trước đó đã có kết quả chưa và cách tiếp tục khi mất phương thức xác thực. Những thông tin này phải xuất hiện qua cấu trúc trang, nhãn điều khiển, focus và thông báo trạng thái; chỉ đổi màu hoặc hiện một biểu tượng là chưa đủ.

Trong khôi phục tài khoản, một bước không thể tiếp cận có thể khiến người dùng tưởng mã sai, bấm gửi lại nhiều lần hoặc tìm đến kênh hỗ trợ không đáng tin cậy. Thiết kế cần đồng thời đạt hai mục tiêu:

- Người dùng tự thực hiện được các thao tác được phép bằng bàn phím và công nghệ hỗ trợ.
- Máy chủ vẫn xác minh bằng chứng, giới hạn thử, kiểm tra token và quyết định quyền khôi phục.

Trình đọc màn hình là cách tương tác với giao diện, không phải bằng chứng danh tính. Không được miễn MFA, bỏ xác minh hoặc cấp phiên đăng nhập chỉ vì người dùng chọn chế độ hỗ trợ.

Ví dụ xuyên suốt: Lan mất thiết bị chứa passkey, đang dùng trình đọc màn hình trên máy tính khác và còn một phương thức dự phòng đã đăng ký. Luồng phải giúp Lan tìm được phương thức đó, hoàn thành xác minh và hiểu điều gì xảy ra với phiên cùng thiết bị cũ.

## 2. Biểu diễn hành trình thành các bước rõ ràng

Mỗi trang hoặc màn hình cần một tiêu đề chính mô tả hành động hiện tại. Với luồng có nhiều nhánh, tránh công bố tổng số bước cố định khi hệ thống chưa biết có cần xác minh bổ sung hay không.

| Trạng thái | Nội dung người dùng cần nhận được | Hành động tiếp theo |
| --- | --- | --- |
| Bắt đầu | “Khôi phục tài khoản”, thông tin định danh cần nhập | Gửi yêu cầu |
| Chờ hướng dẫn | Phản hồi trung tính và cách kiểm tra kênh đã đăng ký | Mở hướng dẫn hoặc chọn trợ giúp |
| Chọn phương thức | Các lựa chọn hợp lệ tại giai đoạn hiện tại | Chọn một phương thức |
| Nhập bằng chứng | Nhãn mã, định dạng và điều kiện hiệu lực | Xác minh |
| Chưa thể xác minh | Lỗi có thể xử lý, trạng thái hết hạn hoặc giới hạn thử | Sửa mã, yêu cầu mã mới hoặc chuyển nhánh |
| Thiết lập lại | Thông tin chính xác về mật khẩu hay phương thức sắp thay | Xác nhận thay đổi |
| Hoàn tất | Thay đổi đã áp dụng và chính sách phiên thực tế | Đăng nhập lại hoặc tiếp tục theo chính sách |

Phản hồi trước xác minh có thể là: “Nếu thông tin phù hợp với tài khoản, hướng dẫn sẽ được gửi qua kênh đã đăng ký.” Không đọc ra tên chủ tài khoản, email đầy đủ hoặc danh sách thiết bị chưa được phép tiết lộ. Nội dung ẩn bằng CSS hay nhãn ARIA cũng phải tuân theo giới hạn tiết lộ tương tự phần nhìn thấy.

## 3. Cấu trúc biểu mẫu để người dùng tìm và hiểu được

Ưu tiên phần tử HTML có ngữ nghĩa: heading cho tiêu đề, `main` cho nội dung chính, `form` cho biểu mẫu, `label` cho trường nhập và `button` cho hành động. Liên kết nhãn bằng `for` và `id`; placeholder chỉ là gợi ý phụ. Đây là nền tảng mà [W3C WAI hướng dẫn về nhãn điều khiển](https://www.w3.org/WAI/tutorials/forms/labels/) mô tả.

Đối với lựa chọn phương thức, dùng nhóm radio có `fieldset` và `legend`, chẳng hạn “Chọn cách xác minh”. Nhãn mỗi lựa chọn nói rõ ý nghĩa: “Dùng mã dự phòng đã lưu” dễ hiểu hơn “Cách 2”. Chỉ hiển thị lựa chọn được chính sách cho phép ở thời điểm đó.

Ví dụ sau minh họa phần nhập một mã gồm sáu chữ số. Đường dẫn và giá trị CSRF là hợp đồng giả định; máy chủ phải cung cấp giá trị thật và xử lý bảo mật tương ứng.

```html
<main lang="vi">
  <h1 id="step-title" tabindex="-1">Nhập mã khôi phục</h1>
  <p>Mã gồm 6 chữ số. Bạn có thể dán toàn bộ mã vào một ô.</p>

  <section id="error-summary" hidden
           aria-labelledby="error-title" tabindex="-1">
    <h2 id="error-title">Chưa thể xác minh mã</h2>
    <p><a href="#recovery-code">Kiểm tra mã khôi phục.</a></p>
  </section>

  <form id="recovery-form" method="post"
        action="/recovery/verify-code">
    <input type="hidden" name="csrfToken"
           value="{{ serverRenderedCsrfToken }}">

    <label for="recovery-code">Mã khôi phục</label>
    <p id="code-help">Nhập đủ 6 chữ số, bao gồm số 0 ở đầu nếu có.</p>
    <input id="recovery-code" name="code" type="text"
           inputmode="numeric" autocomplete="one-time-code"
           pattern="[0-9]{6}" maxlength="6" required
           aria-describedby="code-help code-error">
    <p id="code-error" hidden></p>

    <button type="submit">Xác minh mã</button>
    <button type="button" id="resend">Yêu cầu mã mới</button>
  </form>

  <p id="recovery-status" role="status" aria-atomic="true"></p>
  <a href="/recovery/other-method">Tôi không dùng được phương thức này</a>
</main>
```

Dùng `type="text"` để giữ nguyên số 0 ở đầu; `inputmode` chỉ gợi ý bàn phím, không thay kiểm tra dữ liệu phía máy chủ. Một ô nhập giúp thao tác dán dễ hơn so với việc buộc di chuyển qua sáu ô riêng. Không tự gửi ngay khi đủ ký tự; nút “Xác minh mã” cho người dùng quyền quyết định thời điểm gửi.

## 4. Quản lý focus khi chuyển bước và khi có lỗi

Focus là vị trí tương tác bằng bàn phím. Vị trí đọc của trình đọc màn hình có thể khác focus; vì vậy gọi `focus()` liên tục không bảo đảm người dùng hiểu giao diện.

Áp dụng một quy tắc nhất quán cho từng loại thay đổi:

- Khi SPA thay toàn bộ bước sau hành động của người dùng, cập nhật tiêu đề trang rồi chuyển focus đến heading của bước mới sau khi heading đã có trong DOM.
- Khi gửi biểu mẫu có lỗi, đưa focus đến phần tổng hợp lỗi hoặc trường lỗi theo thiết kế đã chọn. Thông báo phải chỉ ra cách sửa và liên kết đến trường liên quan.
- Khi có thay đổi nền như gửi lại mã thành công, giữ focus tại điều khiển hiện tại và dùng vùng trạng thái để thông báo.
- Khi mở hộp thoại, đặt focus trong hộp thoại; khi đóng, trả về điều khiển mở nếu nó vẫn tồn tại.
- Khi người dùng quay lại một bước, giữ thông tin không nhạy cảm phù hợp để họ không phải nhập lại toàn bộ.

Không dùng `tabindex` dương để ép thứ tự điều hướng. `tabindex="-1"` trên heading hoặc phần tổng hợp lỗi phục vụ focus theo chương trình mà không thêm một điểm dừng Tab thường trực.

[Hướng dẫn W3C WAI về phản hồi biểu mẫu](https://www.w3.org/WAI/tutorials/forms/notifications/) giải thích việc thông báo kết quả, liên kết lỗi với điều khiển và cung cấp cách sửa. Trong luồng này, cần chọn chiến lược thông báo phù hợp để tránh cùng một lỗi vừa bị đọc bởi vùng cảnh báo vừa bị đọc lại do focus chuyển ngay lập tức.

## 5. Thông báo trạng thái mà không làm gián đoạn thao tác

Đặt sẵn vùng `role="status"` trong trang rồi cập nhật nội dung khi có kết quả. Thông báo nên ngắn và mô tả sự kiện: “Đã xử lý yêu cầu gửi mã mới. Hãy kiểm tra kênh nhận mã.” Ở giai đoạn cần chống dò tài khoản, giữ câu chữ trung tính theo hợp đồng phản hồi của máy chủ.

Ví dụ xử lý lỗi định dạng và thông báo nền:

```javascript
const form = document.getElementById("recovery-form");
const code = document.getElementById("recovery-code");
const error = document.getElementById("code-error");
const summary = document.getElementById("error-summary");
const status = document.getElementById("recovery-status");

function showCodeFormatError() {
  status.textContent = "";
  error.textContent = "Nhập đủ 6 chữ số của mã khôi phục.";
  error.hidden = false;
  code.setAttribute("aria-invalid", "true");
  summary.hidden = false;
  summary.focus();
}

function clearCodeError() {
  code.removeAttribute("aria-invalid");
  error.textContent = "";
  error.hidden = true;
  summary.hidden = true;
}

function announceRequestProcessed() {
  status.textContent =
    "Đã xử lý yêu cầu gửi mã mới. Hãy kiểm tra kênh nhận mã.";
}

form.addEventListener("input", () => clearCodeError());
```

Các hàm trên chỉ minh họa cập nhật giao diện; chúng không gọi API, xác minh mã hay thay đổi quyền khôi phục. Khi tích hợp, chỉ gọi thông báo kết quả sau khi nhận phản hồi tương ứng. Lỗi mạng phải có câu riêng, chẳng hạn “Chưa nhận được kết quả. Hãy thử lại”; không biến lỗi mạng thành thông báo đã gửi mã.

Không đọc toàn bộ mã, mật khẩu mới hoặc token qua live region. Không đặt `aria-live` lên toàn trang. Nếu có đồng hồ đếm ngược, tránh thông báo mỗi giây; thông báo ở các thời điểm có ý nghĩa như khi được phép gửi lại hoặc khi mã hết hạn.

Trong khi gửi, cho biết “Đang xác minh” và chặn yêu cầu trùng. Nếu dùng `aria-disabled` để giữ focus trên nút, mã xử lý vẫn phải chặn kích hoạt vì thuộc tính này không tự vô hiệu hóa hành vi. Máy chủ phải tự kiểm soát yêu cầu trùng và giới hạn thử, kể cả khi JavaScript không hoạt động.

## 6. Hết hạn, gửi lại mã và chuyển sang phương thức khác

Đọc nội dung và di chuyển bằng công nghệ hỗ trợ có thể mất thời gian. Giao diện cần giải thích thời hạn bằng văn bản dễ tìm và cung cấp lối thoát khi người dùng không kịp hoàn thành.

Khi mã hết hạn, thông báo “Mã không còn hiệu lực. Bạn có thể yêu cầu mã mới.” Giữ đường đến phương thức khác và trợ giúp; không chỉ khóa biểu mẫu rồi để người dùng tự đoán. Trường hợp bị giới hạn thử cần phân biệt với lỗi định dạng, đồng thời không công bố thông tin tài khoản chưa được phép.

Thời hạn và hiệu lực do máy chủ quyết định. Đồng hồ phía trình duyệt chỉ hỗ trợ hiển thị. Nếu chính sách quy định mã mới làm mã cũ mất hiệu lực, phải giải thích điều đó sau phản hồi gửi lại. Không tự gia hạn token hoặc bỏ giới hạn thử dựa trên việc phát hiện trình đọc màn hình.

Nút phương thức khác cần xuất hiện trước khi người dùng bị mắc kẹt. Với Lan đã mất passkey, yêu cầu xác nhận bằng chính passkey đó tạo vòng lặp không thể hoàn thành. Nhánh thay thế phải dùng bằng chứng được chính sách cho phép; hỗ trợ thủ công cũng cần quy trình xác minh và kiểm soát lạm dụng riêng.

[Giải thích WCAG 2.2 về xác thực có thể tiếp cận](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html) đề cập cơ chế hỗ trợ nhập như sao chép, dán và việc khôi phục tài khoản trong quá trình xác thực. Đừng cấm dán mã hay chặn trình quản lý mật khẩu. Chỉ thay CAPTCHA hình ảnh bằng một đoạn âm thanh vẫn có thể để lại rào cản ghi nhớ và chép lại thông tin.

## 7. Khôi phục thành công và kiểm soát session

Thông báo hoàn tất phải xuất phát từ kết quả đã xác nhận của máy chủ. Phân biệt “đã xác minh phương thức dự phòng” với “đã thay mật khẩu” và “đã hoàn tất khôi phục”; ba sự kiện có thể nằm ở các bước khác nhau.

Màn hình cuối cần cho biết cụ thể:

- Mật khẩu, passkey hoặc phương thức MFA nào đã được thay đổi.
- Phiên hiện tại có được tiếp tục sử dụng hay phải đăng nhập lại.
- Các phiên và thiết bị cũ đã bị thu hồi theo chính sách nào.
- Người dùng có cần đăng ký phương thức dự phòng mới hay không.

Nếu thu hồi phiên đang được xử lý, đừng thông báo “mọi thiết bị đã đăng xuất”. Nếu thay mật khẩu không làm mất hiệu lực passkey cũ trong thiết kế hiện tại, đừng mô tả như đã loại bỏ mọi cách truy cập cũ.

Token khôi phục dùng một lần phải được kiểm tra và tiêu thụ ở máy chủ theo thao tác nguyên tử thích hợp. Sau khi hoàn tất, quay lại bằng nút Back không được tạo cơ hội sử dụng lại token. Về giao diện, trang cũ cần hướng đến kết quả hiện tại hoặc lối khởi động lại phù hợp.

## 8. Tình huống minh họa

Lan mở “Khôi phục tài khoản”. Tiêu đề trang giúp cô nhận biết đúng nơi, trường định danh có nhãn rõ ràng và nút gửi có tên mô tả hành động.

Sau yêu cầu ban đầu, hệ thống trả thông báo trung tính. Ở giai đoạn được phép chọn phương thức, Lan chọn “Dùng mã dự phòng đã lưu”. Bước mới có heading được focus, hướng dẫn ngay trước trường nhập và một ô cho phép dán toàn bộ mã.

Nếu mã có định dạng sai, phần tổng hợp lỗi được focus và liên kết đưa Lan về đúng trường. Nếu máy chủ báo mã không còn hiệu lực, hệ thống giải thích cách tiếp tục mà không đọc lại mã. Thông báo gửi lại xuất hiện qua vùng trạng thái và không kéo focus khỏi nơi Lan đang thao tác.

Sau khi bằng chứng được chấp nhận, Lan thực hiện thay đổi được phép. Máy chủ xác nhận hoàn tất, xử lý token và session theo chính sách; màn hình cuối mô tả đúng kết quả cùng đường đăng nhập tiếp theo.

Điểm quyết định là hành trình có thể hoàn thành mà người dùng luôn hiểu trạng thái hiện tại. Ngữ nghĩa HTML, focus và thông báo hỗ trợ việc tương tác; bằng chứng, token và kiểm soát session quyết định quyền truy cập.
