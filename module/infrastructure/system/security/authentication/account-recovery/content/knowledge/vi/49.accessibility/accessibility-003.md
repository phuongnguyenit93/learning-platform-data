# Visible focus treatment trong luồng khôi phục tài khoản

## 1. Vì sao focus phải nhìn thấy được?

Khi một người dùng khôi phục tài khoản bằng bàn phím, họ cần biết chính xác thao tác tiếp theo sẽ tác động lên phần tử nào. Sau khi nhấn `Tab`, họ đang ở ô nhập email, nút gửi mã, liên kết đổi phương thức xác minh hay nút xác nhận mật khẩu mới? Nếu giao diện không hiển thị vị trí này, một trang vẫn có thể nhận phím nhưng người dùng không thể sử dụng một cách tự tin.

**Visible focus treatment** là cách giao diện thể hiện rõ phần tử đang nhận focus, thường bằng đường viền, vòng bao quanh hoặc một dấu hiệu hình học tương đương. Đây là trạng thái tương tác, không phải hiệu ứng trang trí.

Trong module khôi phục tài khoản, vấn đề đặc biệt quan trọng vì người dùng có thể đang mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Họ phải đọc hướng dẫn, chuyển giữa nhiều phương thức và nhập dữ liệu nhạy cảm trong lúc chịu áp lực. Một focus indicator rõ ràng giúp giảm thao tác nhầm, chẳng hạn gửi lại mã nhiều lần hoặc chọn nhầm phương thức xác minh.

Việc nhìn thấy focus hỗ trợ cả người dùng bàn phím, người dùng công cụ hỗ trợ có thao tác điều hướng tương ứng và người dùng thị lực kém. Nó không thay thế nhãn trường, thứ tự điều hướng hợp lý hay phản hồi lỗi bằng văn bản.

## 2. Phân biệt focus với các trạng thái khác

Focus là đích nhận tương tác bàn phím tại thời điểm hiện tại. Với các nút và liên kết thông thường, nhấn `Tab` để chuyển đến phần tử khác với việc kích hoạt phần tử bằng phím phù hợp.

| Trạng thái | Ý nghĩa | Ví dụ trong khôi phục tài khoản |
| --- | --- | --- |
| Focus | Phần tử đang nhận tương tác bàn phím | Nút “Gửi mã khôi phục” có vòng focus |
| Hover | Con trỏ đang nằm trên phần tử | Chuột đi qua liên kết “Thử cách khác” |
| Selected hoặc checked | Lựa chọn hiện tại của một thành phần | Radio “Dùng mã dự phòng” đã được chọn |
| Invalid | Dữ liệu nhập có lỗi cần xử lý | Ô mã khôi phục thiếu dữ liệu |
| Disabled | Phần tử hiện không cho phép thao tác | Nút gửi lại đang bị vô hiệu hóa theo trạng thái giao diện |

Một ô có thể đồng thời **invalid và focused**. Khi đó, người dùng phải nhận ra cả hai thông tin: ô nào đang nhận phím và vì sao dữ liệu chưa được chấp nhận. Không dùng cùng một thay đổi màu đơn lẻ để thể hiện cả lỗi lẫn focus.

Với nhóm radio, phím mũi tên có thể thay đổi lựa chọn theo hành vi của thành phần native. Vì vậy, “không tự gửi yêu cầu khi nhận focus” không có nghĩa là loại bỏ các tương tác bàn phím chuẩn của điều khiển.

## 3. Đặt focus indicator trên đúng phần tử

Các phần tử có thể nhận tương tác trong luồng khôi phục cần dấu hiệu focus dễ nhận biết:

- Ô nhập định danh tài khoản, mã xác minh, mã dự phòng và mật khẩu mới.
- Nút tiếp tục, gửi lại mã, xác nhận và quay lại.
- Liên kết trợ giúp hoặc đổi phương thức xác minh.
- Checkbox hiển thị mật khẩu và các lựa chọn phương thức khôi phục.
- Nút đóng hộp thoại, nút mở hướng dẫn và các điều khiển tùy chỉnh nếu thực sự cần dùng chúng.

Ưu tiên HTML có sẵn như `button`, `a`, `input`, `select` và `textarea`. Các phần tử này cung cấp nền tảng hành vi bàn phím và ngữ nghĩa tốt hơn một `div` có sự kiện click. Thêm một vòng focus cho `div` không tự biến nó thành nút hoàn chỉnh.

Không thêm `tabindex="0"` cho mọi tiêu đề, đoạn giải thích hoặc biểu tượng. Điều đó làm đường đi của phím `Tab` dài và khó dự đoán. Tiêu đề của bước mới có thể dùng `tabindex="-1"` để nhận focus bằng chương trình mà không trở thành một điểm dừng thường xuyên trong thứ tự Tab.

## 4. Một mẫu CSS đơn giản và có thể dự đoán

Có thể bắt đầu bằng cách giữ focus visible cho mọi tương tác trong vùng khôi phục, kể cả khi người dùng nhấp chuột. Đây là một lựa chọn giao diện hợp lệ và dễ duy trì.

```css
.recovery {
  --recovery-surface: #ffffff;
  --recovery-text: #172554;
  --recovery-focus: #1745b8;

  color: var(--recovery-text);
  background: var(--recovery-surface);
}

.recovery :where(
  a[href], button, input, select, textarea, [tabindex]
):focus {
  outline: 3px solid var(--recovery-focus);
  outline-offset: 3px;
}

/* Nhấn mạnh thêm khi trình duyệt xác định cần focus visible. */
.recovery :where(
  a[href], button, input, select, textarea, [tabindex]
):focus-visible {
  outline-width: 4px;
}

.recovery :where(input, select, textarea, button, a[href], [tabindex]) {
  scroll-margin-block: 7rem;
}

.recovery[data-theme="dark"] {
  --recovery-surface: #0f172a;
  --recovery-text: #f8fafc;
  --recovery-focus: #facc15;
}

@media (forced-colors: active) {
  .recovery :where(
    a[href], button, input, select, textarea, [tabindex]
  ):focus {
    outline: 3px solid Highlight;
    outline-offset: 3px;
  }
}
```

Trong ví dụ này, `:focus` là nền tảng. `:focus-visible` chỉ tăng độ nhấn mạnh; giao diện vẫn có đường viền focus khi quy tắc này không được áp dụng. Các kích thước và màu trên là giá trị minh họa, cần phù hợp với nền, thành phần và bố cục thực tế.

`outline` thuận tiện vì không chiếm chỗ trong luồng bố cục như việc thêm một border mới. Nếu dùng border cho focus, cần dành sẵn độ dày tương ứng để nút hoặc ô nhập không dịch chuyển khi người dùng nhấn `Tab`.

`outline-offset` tạo khoảng cách giữa indicator và viền điều khiển. Khoảng cách này giúp vòng focus không hòa vào border thông thường. Tuy nhiên, nó cũng làm vòng focus nằm xa phần tử hơn; vùng chứa phải có đủ chỗ để đường viền không bị cắt.

`scroll-margin-block` tạo khoảng đệm khi phần tử được cuộn vào vùng nhìn thấy trong các trường hợp trình duyệt hỗ trợ. Giá trị `7rem` không tự bảo đảm tránh mọi header cố định; chiều cao header, vùng cuộn và kích thước màn hình vẫn quyết định kết quả.

## 5. Dùng `:focus-visible` với hiểu biết về hành vi trình duyệt

`:focus` khớp khi phần tử có focus. `:focus-visible` còn phụ thuộc vào cách trình duyệt xác định thời điểm nên thể hiện dấu hiệu focus. Đây không phải một cờ chính xác mang nghĩa “người dùng vừa nhấn Tab”. Chẳng hạn, trường nhập văn bản có thể cần indicator khi được nhấp chuột vì người dùng sắp nhập bằng bàn phím.

Nếu sản phẩm chọn chỉ hiển thị vòng focus trong một số tình huống qua `:focus-visible`, hãy thiết kế cả hành vi dự phòng và trường hợp focus được đặt bằng chương trình. Không xóa outline toàn cục rồi giả định rằng mọi đường đi đều đã có một indicator thay thế.

Đặc biệt tránh quy tắc sau nếu chưa có cơ chế thay thế đầy đủ:

```css
/* Ví dụ cần tránh: làm mất indicator mặc định trên mọi phần tử. */
*:focus {
  outline: none;
}
```

Một hiệu ứng hover đẹp không bù được việc mất focus indicator. Tương tự, chỉ đổi màu chữ của nút thường không đủ rõ để người dùng nhận ra vị trí đang điều hướng, nhất là khi nhiều nút có màu giống nhau.

## 6. Giữ focus nhìn thấy trong bố cục thực tế

Một vòng focus có màu rõ vẫn có thể biến mất vì bố cục:

| Tình huống | Điều xảy ra | Hướng xử lý |
| --- | --- | --- |
| Card dùng `overflow: hidden` | Outline ngoài nút bị cắt | Chừa khoảng đệm hoặc điều chỉnh vùng clipping phù hợp |
| Header hoặc thanh hành động cố định | Điều khiển có focus bị che | Chừa khoảng cuộn và bố trí vùng nội dung tránh lớp che |
| Nhóm nút đặt sát nhau | Không rõ vòng focus bao quanh nút nào | Tăng khoảng cách và giữ indicator bám sát phần tử |
| Nền sáng, tối hoặc nền đổi theo trạng thái | Một màu indicator bị hòa vào nền | Dùng màu focus theo theme hoặc thiết kế nhiều lớp có độ phân biệt rõ |
| Chỉ dùng `box-shadow` | Dấu hiệu có thể không còn rõ trong chế độ màu cưỡng bức | Giữ một outline hữu hình dùng được với màu hệ thống |
| Focus chỉ xuất hiện qua animation | Người dùng phải chờ mới tìm thấy đích | Hiển thị indicator ngay; animation chỉ là phần bổ sung |

Không dựa riêng vào màu để phân biệt trạng thái. Hình dạng vòng bao, độ dày, khoảng cách và vị trí ổn định đều giúp người dùng tìm được focus. Với liên kết nằm trong đoạn văn, indicator phải giúp nhận biết liên kết đang nhận phím mà không che nội dung lân cận.

Khi phóng to giao diện, các nút có thể xuống dòng và hộp thoại có thể trở thành vùng cuộn. Focus phải còn nhận biết được trong bố cục đó. Không cố định chiều cao một khối lỗi rồi để nội dung và indicator bị che bên ngoài.

## 7. Ví dụ: bước nhập mã khôi phục

Ví dụ dưới đây minh họa cấu trúc trường nhập và vùng tóm tắt lỗi. Mã trong ô là dữ liệu người dùng nhập; việc xác minh, giới hạn thử và quyết định cho phép khôi phục thuộc phía máy chủ.

```html
<section class="recovery" aria-labelledby="recovery-title">
  <h1 id="recovery-title" tabindex="-1">Nhập mã khôi phục</h1>

  <p id="recovery-instruction">
    Nhập mã từ phương thức khôi phục bạn đã chọn.
  </p>

  <section
    id="recovery-errors"
    tabindex="-1"
    aria-labelledby="recovery-errors-title"
    hidden
  >
    <h2 id="recovery-errors-title">Chưa thể tiếp tục</h2>
    <ul>
      <li>
        <a href="#recovery-code" id="recovery-code-error-link">
          <span id="recovery-error-summary-text"></span>
        </a>
      </li>
    </ul>
  </section>

  <form method="post" action="/account-recovery/verify-code">
    <!-- Cơ chế bảo vệ yêu cầu và ràng buộc giao dịch do server cung cấp. -->
    <label for="recovery-code">Mã khôi phục</label>
    <p id="recovery-code-hint">
      Bạn có thể dán toàn bộ mã vào ô này.
    </p>
    <input
      id="recovery-code"
      name="recoveryCode"
      type="text"
      aria-describedby="recovery-code-hint"
      required
    >
    <p id="recovery-code-error" hidden></p>

    <button type="submit">Xác minh mã</button>
    <a href="/account-recovery/methods">Thử phương thức khác</a>
  </form>

  <p id="recovery-status" role="status"></p>
</section>
```

Không phải mã khôi phục nào cũng chỉ gồm chữ số. Một ô `type="text"` không tự làm mất số 0 đầu và có thể chứa mã dự phòng có chữ hoặc dấu phân cách theo định dạng hệ thống. Nếu bước cụ thể chỉ nhận OTP dạng số, có thể cân nhắc `inputmode="numeric"` và `autocomplete="one-time-code"` theo đúng loại mã và nền tảng; không gán cùng một cấu hình cho mọi bí mật khôi phục.

Một ô nhập chung cũng giúp người dùng dán nguyên mã. Nếu chia mã thành nhiều ô, sản phẩm phải xử lý thêm thứ tự focus, phím xóa, thao tác dán và cách đọc tên từng ô. Không tự chuyển focus sang nút xác nhận rồi tự kích hoạt chỉ vì số ký tự đã đủ.

Các ID trong ví dụ là định danh giao diện cố định. Không đưa giá trị token, mã dự phòng hoặc định danh tài khoản nhạy cảm vào ID, tên truy cập của nút hay thông báo focus.

## 8. Focus và thông báo lỗi cần phối hợp

Sau một lần gửi biểu mẫu thất bại, chỉ tô đỏ trường không đủ. Người dùng cần một thông báo lỗi rõ ràng và một vị trí bắt đầu để hiểu vấn đề.

Có hai cách thường dùng: đưa focus đến trường lỗi đầu tiên, hoặc đưa đến vùng tóm tắt lỗi có liên kết tới trường. Lựa chọn nên nhất quán với cấu trúc và số lượng lỗi của bước. Với vùng tóm tắt, `tabindex="-1"` cho phép đặt focus bằng chương trình mà không thêm một điểm dừng Tab thường trực.

Ví dụ hàm hiển thị lỗi cho cấu trúc HTML phía trên:

```javascript
function showRecoveryCodeError(message) {
  const input = document.getElementById('recovery-code');
  const error = document.getElementById('recovery-code-error');
  const summary = document.getElementById('recovery-errors');
  const summaryText = document.getElementById(
    'recovery-error-summary-text'
  );

  error.textContent = message;
  error.hidden = false;
  summaryText.textContent = message;

  input.setAttribute('aria-invalid', 'true');
  input.setAttribute(
    'aria-describedby',
    'recovery-code-hint recovery-code-error'
  );

  summary.hidden = false;
  summary.focus();
}

document.getElementById('recovery-code-error-link')
  .addEventListener('click', (event) => {
    event.preventDefault();
    document.getElementById('recovery-code').focus();
  });
```

Hàm này được gọi sau khi ứng dụng đã nhận và xử lý kết quả kiểm tra phù hợp; nó không thực hiện xác minh mã. Dùng `textContent` để hiển thị văn bản, tránh đưa thông điệp vào `innerHTML` một cách tùy tiện.

Khi lỗi được xử lý, ứng dụng cần cập nhật lại `aria-invalid`, liên kết mô tả và các vùng lỗi tương ứng. Không để thông báo cũ tiếp tục mô tả một trường đã được chấp nhận ở bước khác.

Vùng tóm tắt trên không đồng thời dùng `role="alert"`: đặt focus và phát thông báo khẩn cùng lúc có thể tạo trải nghiệm đọc lặp. Thông báo bất đồng bộ không cần chuyển vị trí, như “Đã xử lý yêu cầu gửi lại mã”, có thể đi vào vùng `role="status"` mà không giành focus từ ô đang nhập.

## 9. Quản lý focus khi chuyển bước

Trong giao diện nhiều bước hoặc ứng dụng thay nội dung tại chỗ, phần tử đang có focus có thể bị gỡ khỏi DOM. Nếu không xác định đích tiếp theo, vị trí tương tác của người dùng trở nên khó hiểu dù CSS indicator vẫn đúng.

| Sự kiện | Đích hoặc hành vi focus hợp lý |
| --- | --- |
| Chuyển thành công sang bước chọn phương thức | Tiêu đề của bước mới sau khi nội dung sẵn sàng |
| Gửi biểu mẫu có lỗi | Tóm tắt lỗi hoặc trường lỗi đầu tiên theo thiết kế nhất quán |
| Gửi lại mã nhưng vẫn ở cùng bước | Giữ vị trí thao tác; cập nhật thông báo trạng thái |
| Token hết hạn và cần bắt đầu lại | Tiêu đề hoặc thông báo giải thích trạng thái mới, kèm hành động rõ ràng |
| Mở hộp thoại hướng dẫn | Đích có ý nghĩa trong hộp thoại theo hành vi của hộp thoại |
| Đóng hộp thoại | Trả focus về phần tử mở hộp thoại nếu nó còn dùng được |
| Hoàn thành khôi phục | Tiêu đề xác nhận và hướng dẫn hành động tiếp theo |

Đối với ứng dụng thay nội dung tại chỗ, có thể dùng một hàm nhỏ sau khi bước đích đã được render và hiển thị:

```javascript
function focusRecoveryStepTitle(titleId) {
  const title = document.getElementById(titleId);
  if (!title) return;

  // Tiêu đề được render với tabindex="-1" và có style :focus.
  title.focus();
}
```

Đích phải đang hiển thị và không nằm trong vùng bị vô hiệu hóa tương tác. Trong framework, gọi ở thời điểm cập nhật DOM đã hoàn tất theo vòng đời của framework; không dựa vào một khoảng `setTimeout` tùy ý để đoán lúc render xong.

Không chạy lại thao tác focus tiêu đề sau mỗi lần người dùng gõ hoặc sau mỗi lần component render. Điều đó kéo họ ra khỏi trường đang nhập. Việc chuyển focus phải gắn với một thay đổi có ý nghĩa, chẳng hạn điều hướng sang bước mới.

`tabindex="-1"` chỉ giải quyết khả năng nhận focus bằng chương trình. Nó không tự tạo ngữ nghĩa hộp thoại, cơ chế giữ focus trong modal hay khôi phục focus khi đóng modal; các hành vi đó cần được thiết kế đầy đủ nếu có hộp thoại.

## 10. Thứ tự focus, thời gian chờ và thao tác gửi lại

Thứ tự Tab nên đi theo cấu trúc DOM và cách đọc nội dung: định danh hoặc mã, hành động chính, rồi hành động phụ trong ngữ cảnh phù hợp. Tránh `tabindex` số dương để vá một bố cục đặt phần tử sai thứ tự, vì các thay đổi sau này rất dễ làm đường đi bàn phím bất nhất.

Trong bước có thời gian chờ gửi lại mã, không chuyển focus mỗi giây theo bộ đếm. Cũng không phát toàn bộ thời gian còn lại vào live region từng giây. Người dùng cần đọc và nhập mã mà không bị giao diện liên tục ngắt lời.

Nếu nút bị thay thế, bị ẩn hoặc bị vô hiệu hóa trong lúc đang có focus, phải xác định trạng thái và đích tiếp theo một cách chủ động. Không dựa vào việc trình duyệt có thể tự giữ hoặc tự chuyển focus theo một hành vi giống nhau trên mọi tổ hợp thiết bị.

`aria-disabled="true"` chỉ mô tả trạng thái; nó không tự ngăn click, bàn phím hay yêu cầu mạng. Ngược lại, việc nút bị disabled trên giao diện cũng không thay thế giới hạn gửi lại và giới hạn thử mã phía máy chủ.

Nếu hệ thống dùng CAPTCHA hoặc một bước xác minh bổ sung, dấu hiệu focus và đường đi bàn phím phải tiếp tục có ý nghĩa ở cả bước đó. Không đánh đổi khả năng truy cập bằng cách bỏ yêu cầu xác minh; cần có phương án tương tác phù hợp với chính sách khôi phục đã định.

## 11. Ranh giới giữa khả năng truy cập và an toàn khôi phục

Focus treatment giúp người dùng thao tác đúng. Quyền đổi mật khẩu, thay MFA, thu hồi session hoặc ràng buộc passkey mới vẫn phải dựa trên quyết định xác minh và trạng thái giao dịch phía máy chủ.

Trong thiết kế luồng khôi phục cần giữ các ranh giới sau:

- **Nhận focus không kích hoạt yêu cầu.** Đi đến nút “Gửi mã” không được tự gửi mã hoặc thay đổi trạng thái tài khoản.
- **Thông báo giao diện không tiết lộ bí mật.** Không đưa mã xác minh, token hoặc mã dự phòng vào live region để mô tả trường đang nhận focus.
- **Phản hồi công khai phải phù hợp chính sách chống dò tài khoản.** Cách đặt focus và thông điệp ở bước gửi yêu cầu không nên vô tình tạo hai luồng dễ phân biệt cho tài khoản tồn tại và không tồn tại.
- **Trợ giúp không mở đường bỏ qua xác minh.** Liên kết “Tôi mất thiết bị” đưa tới phương án khôi phục được thiết kế, không biến trạng thái focus thành bằng chứng danh tính.
- **Hoàn tất giao diện không đồng nghĩa đã có session đầy đủ.** Chỉ hiển thị bước và hành động phù hợp với kết quả khôi phục thực tế, bao gồm hướng dẫn đăng nhập lại nếu chính sách yêu cầu.

Một thay đổi nhỏ về focus có thể tạo khác biệt lớn về trải nghiệm, nhưng không được thay đổi ý nghĩa của token dùng một lần, số lần thử hoặc điều kiện cấp quyền.

## 12. Tình huống vận dụng

Giả sử người dùng đã mất điện thoại chứa ứng dụng MFA và chọn dùng mã dự phòng. Họ mở trang khôi phục, dùng `Tab` đến ô mã, dán mã rồi kích hoạt “Xác minh mã”.

Một thiết kế có focus treatment rõ ràng sẽ có các đặc điểm sau:

1. Khi ô mã nhận focus, vòng bao hiện ngay và không bị card cắt mất.
2. Khi chuyển đến nút xác minh, vòng bao theo đúng nút; trường mã vẫn giữ trạng thái lỗi riêng nếu có.
3. Nếu mã không thể sử dụng, vùng tóm tắt lỗi nhận focus với thông điệp an toàn và liên kết quay về trường.
4. Nếu người dùng chọn gửi lại hoặc đổi phương thức, hành động chỉ xảy ra khi họ kích hoạt điều khiển.
5. Khi chuyển sang bước đặt mật khẩu mới, tiêu đề bước mới nhận focus sau khi nội dung đã sẵn sàng.
6. Trong theme tối hoặc chế độ màu cưỡng bức, indicator vẫn có hình dạng dễ nhận biết.

Khi thiết kế một bước khôi phục mới, hãy xác định đồng thời **phần tử nào nhận focus, dấu hiệu nào cho biết vị trí đó và sự kiện nào cho phép chuyển focus**. Ba quyết định này cần thống nhất với cấu trúc HTML, phản hồi lỗi và trạng thái khôi phục thực tế.
