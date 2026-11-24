# Error announcement: thông báo lỗi dễ tiếp cận trong khôi phục tài khoản

Khi khôi phục tài khoản, một thông báo “Có lỗi xảy ra” thường chưa đủ để người dùng đi tiếp. Người dùng cần biết thao tác nào chưa hoàn tất, dữ liệu nào cần sửa và lựa chọn an toàn còn lại. Người dùng trình đọc màn hình còn cần được thông báo rằng giao diện vừa thay đổi, ngay cả khi focus vẫn nằm ở nút gửi.

Trong phạm vi SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, **error announcement** là cách đưa lỗi và thay đổi trạng thái đến người dùng qua văn bản, ngữ nghĩa HTML, công nghệ hỗ trợ và luồng focus. Nó liên quan đến yêu cầu đặt lại mật khẩu, xác nhận mã, sử dụng liên kết khôi phục, khôi phục MFA và lựa chọn phương thức thay thế khi mất passkey hoặc thiết bị.

Một thiết kế phù hợp cần đồng thời giữ được ba thuộc tính:

- Người dùng nhận biết và hiểu được vấn đề.
- Người dùng có hành động tiếp theo khả thi.
- Thông báo không tiết lộ thông tin tài khoản hoặc làm suy yếu điều kiện khôi phục.

## 1. Tách nội dung lỗi khỏi cách thông báo

Có hai quyết định khác nhau khi một yêu cầu thất bại.

**Nội dung được phép hiển thị** phụ thuộc vào trạng thái xác minh của luồng. Ví dụ, lỗi định dạng email có thể được diễn đạt cụ thể trước xác minh; thông tin tài khoản có bật MFA hay không thường không nên xuất hiện chỉ vì ai đó nhập một email.

**Cách thông báo nội dung đó** phụ thuộc vào ngữ cảnh tương tác. Một lỗi tại trường nhập cần liên kết với trường đó. Một phản hồi nền có thể cần live region. Một bước không thể tiếp tục có thể cần chuyển focus đến phần giải thích.

Không nên để frontend tự biến mọi mã lỗi nội bộ thành thông báo. Máy chủ cần xác định nhóm kết quả công khai; giao diện ánh xạ nhóm đó sang câu chữ, vị trí và hành động phù hợp.

Ví dụ, thông tin nội bộ “không tìm thấy tài khoản” không trở thành “Email này chưa đăng ký”, dù câu đó được trình bày bằng HTML dễ tiếp cận.

## 2. Viết thông báo có thể hành động

Một thông báo hữu ích thường trả lời được ba câu hỏi: chuyện gì vừa xảy ra, ảnh hưởng đến bước hiện tại ra sao, và người dùng có thể làm gì tiếp theo.

| Tình huống | Ví dụ thông báo | Hành động đi kèm |
| --- | --- | --- |
| Bỏ trống email | “Nhập địa chỉ email để tiếp tục.” | Liên kết hoặc focus về trường email |
| Email sai định dạng | “Nhập email theo dạng ten@vidu.com.” | Giữ dữ liệu đã nhập để sửa |
| Đã tiếp nhận yêu cầu khôi phục | “Nếu thông tin khớp với tài khoản đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.” | Hướng dẫn kiểm tra thư và lựa chọn thử lại theo chính sách |
| Mã không được chấp nhận | “Không thể xác nhận mã này. Kiểm tra mã vừa nhập hoặc yêu cầu mã mới.” | Trường nhập mã và nút yêu cầu mã mới |
| Liên kết không còn dùng được | “Không thể tiếp tục bằng liên kết này. Hãy bắt đầu một yêu cầu khôi phục mới.” | Liên kết bắt đầu lại |
| Yêu cầu bị giới hạn tần suất | “Bạn chưa thể thử lại lúc này. Hãy thử lại sau khoảng thời gian được hiển thị.” | Thời điểm hoặc khoảng chờ mà máy chủ cho phép công khai |
| Mất kết nối | “Chưa xác nhận được kết quả yêu cầu. Kiểm tra kết nối trước khi thử lại.” | Thử lại có kiểm soát |

Các câu trong bảng là ví dụ thiết kế, không phải một bộ thông báo bắt buộc cho mọi hệ thống. “Mã không được chấp nhận” có thể cần gộp nhiều nguyên nhân để tránh lộ trạng thái nội bộ.

Tránh các câu quy lỗi như “Bạn nhập sai liên tục” hoặc “Bạn đã làm mất thiết bị”. Người dùng có thể đang gặp hạn chế vận động, trí nhớ, thị lực hoặc đang chịu áp lực vì không truy cập được tài khoản.

Không dùng màu đỏ, biểu tượng hoặc âm thanh làm dấu hiệu duy nhất. Cần có văn bản mô tả lỗi. Một biểu tượng trang trí có thể được ẩn với công nghệ hỗ trợ bằng `aria-hidden="true"` khi văn bản bên cạnh đã truyền đạt đầy đủ ý nghĩa.

## 3. Chọn cơ chế thông báo theo tình huống

### 3.1. Lỗi gắn với trường nhập

Với lỗi tại một trường:

1. Giữ nhãn trường rõ ràng.
2. Đặt thông báo gần trường.
3. Gắn thông báo với trường bằng `aria-describedby`.
4. Đặt `aria-invalid="true"` khi đã xác định dữ liệu không hợp lệ.
5. Khi lỗi được xử lý, xóa trạng thái không hợp lệ và cập nhật liên kết mô tả.

`aria-describedby` giúp người dùng nhận được mô tả khi truy cập trường; nó không phải cơ chế bảo đảm mọi thay đổi bất đồng bộ đều được đọc ngay. `aria-invalid` cũng không tự cung cấp câu hướng dẫn sửa lỗi.

Ví dụ:

```html
<label for="recovery-email">Địa chỉ email</label>
<p id="recovery-email-help">
  Nhập địa chỉ email bạn dùng cho tài khoản.
</p>
<input
  id="recovery-email"
  name="email"
  type="email"
  autocomplete="email"
  required
  aria-invalid="true"
  aria-describedby="recovery-email-help recovery-email-error"
>
<p id="recovery-email-error">
  Nhập email theo dạng ten@vidu.com.
</p>
```

Khi có nhiều lỗi, phần tổng hợp ở đầu biểu mẫu giúp người dùng hiểu phạm vi vấn đề và quay về từng trường. Với biểu mẫu chỉ có một trường lỗi sau khi gửi, đưa focus về trường đó cũng có thể là lựa chọn hợp lý. Hướng dẫn biểu mẫu của [W3C WAI](https://www.w3.org/WAI/tutorials/forms/notifications/) trình bày cách kết hợp mô tả lỗi và focus với trường nhập.

### 3.2. Trạng thái không cần ngắt tương tác

Dùng `role="status"` cho thông tin như đang xử lý hoặc kết quả tiếp nhận yêu cầu. Vai trò này có ngữ nghĩa live region ở mức `polite`: công nghệ hỗ trợ có thể đọc cập nhật ở thời điểm phù hợp, thay vì yêu cầu ngắt ngay nội dung đang đọc. Theo [WAI-ARIA 1.2, vai trò status](https://www.w3.org/TR/wai-aria-1.2/#status), việc cập nhật trạng thái không nên tự chuyển focus vào vùng này.

```html
<p id="recovery-status" role="status" aria-atomic="true"></p>
```

Tạo vùng trạng thái rỗng từ khi dựng giao diện rồi cập nhật nội dung giúp có một điểm thông báo ổn định. Tránh tạo rồi hủy liên tục các vùng live trong mỗi lần render.

Văn bản cần tồn tại đủ lâu để người dùng đọc lại. Một toast biến mất sau vài giây không nên là nơi duy nhất chứa lỗi hoặc bước xử lý tiếp theo.

### 3.3. Thông báo cần chú ý ngay

`role="alert"` dành cho thông tin quan trọng cần được chú ý ngay, chẳng hạn bước khôi phục đang mở vừa bị vô hiệu hóa và người dùng phải dừng thao tác hiện tại. Vai trò này có mức thông báo `assertive`; nó không tự quản lý focus. Xem [WAI-ARIA 1.2, vai trò alert](https://www.w3.org/TR/wai-aria-1.2/#alert).

Không dùng alert cho từng ký tự nhập, mọi lần kiểm tra định dạng hoặc từng giây đếm ngược. Các thông báo dồn dập có thể làm người dùng không nghe hết thông tin đang cần.

Nếu có hộp thoại buộc người dùng lựa chọn, đó là một thiết kế tương tác riêng với tên truy cập, focus ban đầu và điều hướng bàn phím. Gắn `role="alert"` lên một khối chứa nút không tự tạo ra hành vi hộp thoại đúng.

### 3.4. Focus và live region cần phối hợp

Có thể chọn một trong hai cách cho một lần cập nhật chính:

- **Giữ focus, thông báo bằng live region:** phù hợp khi người dùng có thể tiếp tục ở vị trí hiện tại.
- **Chuyển focus có chủ đích:** phù hợp sau khi gửi biểu mẫu có lỗi hoặc khi bước hiện tại không còn khả dụng.

Nếu đã đưa focus đến tiêu đề phần tổng hợp lỗi, không đồng thời phát lại nguyên phần đó qua một vùng alert. Việc đọc lặp có thể khiến người dùng tưởng có nhiều lỗi hoặc bỏ lỡ hành động cần làm.

Không chuyển focus khi người dùng chỉ đang gõ hoặc khi một phản hồi nền đến muộn. Chuyển focus cần gắn với hành động và trạng thái mà người dùng đang thực sự tương tác.

## 4. Giữ ranh giới bảo mật trong mọi kênh thông báo

Trước khi xác minh quyền kiểm soát tài khoản, thông báo có thể trở thành công cụ dò tìm tài khoản nếu nó khác nhau theo sự tồn tại, trạng thái khóa, phương thức MFA hoặc thiết bị đã đăng ký.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại, đồng thời tránh chênh lệch thời gian phản hồi có thể dùng để dò tài khoản.

Áp dụng nguyên tắc này cho cả văn bản nhìn thấy và nội dung công nghệ hỗ trợ nhận được. Hai màn hình giống nhau về hình thức vẫn có thể rò rỉ nếu một màn hình có `aria-label="Không tìm thấy tài khoản"` hoặc thêm một mục gợi ý phương thức MFA riêng.

Trong một thiết kế khôi phục an toàn:

- Không đưa email, số điện thoại đầy đủ, mã khôi phục, token hoặc URL chứa token vào vùng thông báo.
- Không hiển thị stack trace, tên nhà cung cấp hay mã lỗi nội bộ có thể phân biệt trạng thái tài khoản.
- Không khẳng định “Đã gửi email” nếu giao diện chỉ biết yêu cầu đã được tiếp nhận.
- Chỉ đưa ra lựa chọn phương thức thay thế đã được chính sách của bước hiện tại cho phép.
- Không coi việc người dùng bấm “Tôi không thể đọc mã” là bằng chứng đủ để bỏ qua xác minh.

Khả năng tiếp cận thay đổi cách người dùng nhận hướng dẫn và thực hiện thao tác. Điều kiện chứng minh quyền kiểm soát tài khoản vẫn do cơ chế khôi phục quyết định.

Một câu thông báo trung tính cũng chưa đủ để chống dò tài khoản. Trạng thái HTTP, cấu trúc phản hồi và hành vi phía máy chủ cần được thiết kế cùng chính sách; frontend không thể tự sửa một API đang công khai nguyên nhân nhạy cảm.

## 5. Mẫu triển khai thông báo trên giao diện

Ví dụ dưới đây minh họa riêng cách trình bày và thông báo lỗi cho trường email. Mã không gửi yêu cầu mạng và không thực hiện xác minh danh tính. Lớp gọi API của ứng dụng có thể dùng các hàm trình bày sau khi nhận được kết quả công khai đã được máy chủ xác định.

```html
<form id="recovery-form" novalidate>
  <section id="error-summary" hidden>
    <h2 id="error-heading" tabindex="-1">Cần kiểm tra địa chỉ email</h2>
    <p><a id="email-error-link" href="#recovery-email"></a></p>
  </section>

  <label for="recovery-email">Địa chỉ email</label>
  <p id="email-help">Nhập email bạn dùng cho tài khoản.</p>
  <input
    id="recovery-email"
    name="email"
    type="email"
    autocomplete="email"
    required
    aria-describedby="email-help"
  >
  <p id="email-error" hidden></p>

  <button type="submit">Tiếp tục khôi phục</button>
</form>

<p id="recovery-status" role="status" aria-atomic="true"></p>

<section id="recovery-problem" hidden>
  <h2 id="recovery-problem-heading" tabindex="-1"></h2>
  <p id="recovery-problem-detail"></p>
</section>
```

```javascript
const form = document.querySelector("#recovery-form");
const email = document.querySelector("#recovery-email");
const inlineError = document.querySelector("#email-error");
const summary = document.querySelector("#error-summary");
const errorHeading = document.querySelector("#error-heading");
const errorLink = document.querySelector("#email-error-link");
const statusRegion = document.querySelector("#recovery-status");
const problem = document.querySelector("#recovery-problem");
const problemHeading = document.querySelector("#recovery-problem-heading");
const problemDetail = document.querySelector("#recovery-problem-detail");

function clearEmailError() {
  email.removeAttribute("aria-invalid");
  email.setAttribute("aria-describedby", "email-help");
  inlineError.hidden = true;
  inlineError.textContent = "";
  summary.hidden = true;
}

function showEmailError(message) {
  statusRegion.textContent = "";
  inlineError.textContent = message;
  inlineError.hidden = false;
  email.setAttribute("aria-invalid", "true");
  email.setAttribute("aria-describedby", "email-help email-error");

  errorLink.textContent = message;
  summary.hidden = false;
  errorHeading.focus();
}

function showAcceptedRequest() {
  problem.hidden = true;
  statusRegion.textContent =
    "Nếu thông tin khớp với tài khoản đủ điều kiện, " +
    "hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.";
}

function showBlockingProblem(title, detail, moveFocus) {
  statusRegion.textContent = "";
  problemHeading.textContent = title;
  problemDetail.textContent = detail;
  problem.hidden = false;

  if (moveFocus) {
    problemHeading.focus();
  } else {
    statusRegion.textContent = title + ". " + detail;
  }
}

errorLink.addEventListener("click", (event) => {
  event.preventDefault();
  email.focus();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  clearEmailError();

  if (email.validity.valueMissing) {
    showEmailError("Nhập địa chỉ email để tiếp tục.");
    return;
  }

  if (email.validity.typeMismatch) {
    showEmailError("Nhập email theo dạng ten@vidu.com.");
    return;
  }

  // Điểm tích hợp với lớp gọi API của ứng dụng.
  // Chỉ dùng showAcceptedRequest khi máy chủ xác nhận tiếp nhận.
  // showBlockingProblem nhận câu chữ công khai đã được lựa chọn.
});
```

Phần tổng hợp lỗi không có `role="alert"` vì ví dụ chủ động chuyển focus đến tiêu đề. Người dùng có thể đọc thông báo và dùng liên kết để trở về trường. Lỗi chi tiết vẫn được mô tả khi trường nhận focus.

`textContent` đưa câu chữ vào DOM dưới dạng văn bản. Không chèn trực tiếp thông báo từ máy chủ bằng `innerHTML`. Việc tránh chèn HTML không thay thế cho chính sách chọn nội dung được phép công khai.

Tham số `moveFocus` là quyết định của lớp điều phối tương tác. Nó chỉ nên đúng khi kết quả còn thuộc thao tác hiện tại và việc đưa người dùng đến phần lỗi là phù hợp. Ví dụ này không cung cấp cơ chế xác định điều đó cho một ứng dụng có nhiều yêu cầu đồng thời.

## 6. Xử lý các trạng thái bất đồng bộ

### Phản hồi đến muộn

Giả sử người dùng gửi email A, sau đó sửa thành email B và gửi lại. Kết quả của A đến sau kết quả của B. Nếu giao diện phát thông báo của A hoặc chuyển focus theo A, người dùng có thể làm theo hướng dẫn sai ngữ cảnh.

Lớp điều phối nên gắn mỗi yêu cầu với định danh của lần thao tác và bước khôi phục. Trước khi cập nhật giao diện, đối chiếu kết quả với lần thao tác còn hiệu lực. Một phản hồi cũ không được thay nội dung của bước mới.

Hủy chờ ở trình duyệt không chứng minh thao tác máy chủ đã bị hủy. Với timeout, thông báo nên nói chưa xác nhận được kết quả, đồng thời áp dụng chính sách thử lại của hệ thống để tránh phát sinh nhiều yêu cầu ngoài ý muốn.

### Nhiều lần gửi cùng một lỗi

Nếu cùng một câu lỗi được gán lại vào live region, không nên mặc định mọi tổ hợp trình duyệt và trình đọc màn hình đều sẽ đọc lại. Với lỗi sau thao tác gửi, một phần tổng hợp có thể nhận focus là cách tạo điểm quay lại rõ ràng.

Đồng thời, không thêm dấu chấm ngẫu nhiên hoặc chuỗi vô nghĩa chỉ để ép trình đọc màn hình phát âm. Đầu ra cần giữ nguyên ý nghĩa và có thể đọc lại bằng cách điều hướng thông thường.

### Trạng thái đang xử lý

Có thể hiển thị “Đang xử lý yêu cầu” và chặn gửi trùng ở lớp xử lý thao tác. Tránh thay toàn bộ biểu mẫu bằng spinner khiến vị trí focus biến mất. Khi nút bị vô hiệu hóa, thiết kế cần giữ thứ tự điều hướng hợp lý và cung cấp phản hồi kết thúc rõ ràng.

Dữ liệu cần sửa không nên bị xóa khi có lỗi mạng. Riêng mã bí mật, token hoặc dữ liệu nhạy cảm cần tuân theo chính sách giữ dữ liệu của bước hiện tại, không lưu chúng vào log hoặc lịch sử thông báo.

## 7. Đếm ngược, hết hạn và phương thức thay thế

Thời gian chờ gửi lại và thời hạn sử dụng mã là hai khái niệm khác nhau. Thông báo cần chỉ rõ đang nói về việc nào, tránh câu “Hết thời gian” không có ngữ cảnh.

Không đặt đồng hồ thay đổi mỗi giây trong một live region. Có thể hiển thị đồng hồ bằng văn bản thông thường, rồi thông báo một lần ở mốc có ý nghĩa như “Bạn có thể yêu cầu mã mới”. Khi mã không còn được chấp nhận, giải thích cách lấy mã mới; máy chủ vẫn là nơi quyết định thời hạn và hiệu lực.

Nếu người dùng mất thiết bị hoặc không thể sử dụng một phương thức:

- Giải thích rõ liên kết “Dùng phương thức khác” sẽ đưa họ đến lựa chọn nào.
- Giữ tên nút và hướng dẫn đủ cụ thể để phân biệt “Nhập mã dự phòng” với “Yêu cầu mã mới”.
- Cung cấp lựa chọn khôi phục đã được thiết kế để sử dụng bằng bàn phím và công nghệ hỗ trợ.
- Nếu chuyển sang hỗ trợ con người, nêu cách bắt đầu và thông tin được phép cung cấp; không yêu cầu gửi mật khẩu hoặc mã xác thực cho nhân viên.

Không tự gia hạn token hoặc giảm yêu cầu xác minh chỉ vì người dùng cần thêm thời gian đọc thông báo. Nếu hệ thống hỗ trợ bắt đầu lại, giao diện cần giúp người dùng thực hiện lựa chọn đó rõ ràng.

## 8. Diễn tiến của một tình huống thực tế

Một người dùng trình đọc màn hình đang khôi phục tài khoản sau khi mất điện thoại:

1. Người dùng gửi biểu mẫu có email sai định dạng. Focus chuyển đến tiêu đề tổng hợp, sau đó liên kết đưa họ về trường có mô tả lỗi.
2. Sau khi sửa email và gửi, vùng status thông báo kết quả tiếp nhận bằng câu trung tính. Focus không bị kéo khỏi thao tác đang thực hiện.
3. Ở bước nhập mã được phép truy cập, mã không được chấp nhận. Giao diện giữ thông báo cạnh trường, hướng dẫn kiểm tra mã hoặc yêu cầu mã mới theo chính sách.
4. Khi chọn phương thức thay thế, giao diện trình bày lựa chọn đã được hệ thống cho phép. Nó không tiết lộ thêm thiết bị hay số điện thoại chỉ từ email đã nhập.
5. Nếu người dùng chuyển bước trước khi phản hồi cũ đến, phản hồi đó không ghi đè nội dung hoặc tạo thông báo lỗi ngoài ngữ cảnh.

Trong diễn tiến này, khả năng tiếp cận nằm ở việc người dùng luôn biết đang ở đâu và có thể làm gì tiếp theo. Bảo mật nằm ở việc mỗi thông báo và lựa chọn đều gắn với đúng mức xác minh của luồng.

## 9. Các quyết định cần giữ nhất quán

| Quyết định | Cách áp dụng |
| --- | --- |
| Lỗi thuộc trường hay toàn bước | Gắn lỗi trường với input; giải thích lỗi toàn bước ở vùng riêng |
| Giữ focus hay chuyển focus | Chọn theo hành động hiện tại; tránh đọc lặp cùng nội dung |
| Thông báo thường hay khẩn cấp | Dùng status cho cập nhật thông thường; dành alert cho trường hợp cần chú ý ngay |
| Nội dung nào được công khai | Theo trạng thái xác minh và chính sách máy chủ |
| Người dùng xử lý tiếp bằng cách nào | Giữ nút, liên kết và hướng dẫn cụ thể trong nội dung có thể đọc lại |
| Kết quả nào còn hiệu lực | Đối chiếu yêu cầu và bước hiện tại trước khi cập nhật giao diện |

Error announcement cần được thiết kế như một phần của giao thức tương tác khôi phục tài khoản: nội dung được phép công khai, vị trí lỗi, cơ chế đọc và hành động tiếp theo phải khớp với nhau ở mỗi bước.
