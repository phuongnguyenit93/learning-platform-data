# Right to left recovery layout: bố cục khôi phục tài khoản từ phải sang trái

Một luồng khôi phục tài khoản có thể được sử dụng bằng tiếng Ả Rập, tiếng Hebrew hoặc ngôn ngữ khác có hướng viết chủ đạo từ phải sang trái. Trong cùng một màn hình, người dùng vẫn có thể gặp địa chỉ email, mã xác minh, số điện thoại hoặc tên thiết bị viết từ trái sang phải.

**Right to left recovery layout** là cách tổ chức giao diện khôi phục theo hướng đọc phù hợp, đồng thời xử lý chính xác các đoạn văn bản có hướng khác nhau. Đây không phải thao tác lật toàn bộ màn hình như một bức ảnh.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, bố cục phải giúp người dùng chọn đúng phương thức, đọc đúng hướng dẫn và nhập đúng bằng chứng khi mất mật khẩu, MFA, passkey hoặc thiết bị. Thay đổi cách trình bày không được thay đổi quyền của token, thời hạn khôi phục hoặc điều kiện xác minh.

## 1. Phân biệt hướng viết, căn lề và thứ tự dữ liệu

Ba khái niệm thường bị trộn lẫn:

| Khái niệm | Ví dụ | Điều nó quyết định |
| --- | --- | --- |
| Hướng cơ sở | `dir="rtl"` | Cách trình duyệt xử lý hướng của nội dung trong phạm vi đó |
| Căn lề | `text-align: start` | Nội dung được căn về đầu dòng theo ngữ cảnh |
| Thứ tự logic | Chuỗi mã `012345` và thứ tự phần tử DOM | Giá trị dữ liệu, trình tự đọc và thao tác |

Căn phải một biểu mẫu tiếng Ả Rập chưa đủ để thiết lập hướng viết. Ngược lại, đặt `dir="rtl"` không có nghĩa phải đảo giá trị mã thành `543210`.

Chuỗi trong bộ nhớ và thứ tự hiển thị là hai việc khác nhau. Trình duyệt xử lý văn bản hai chiều dựa trên hướng cơ sở và đặc tính của ký tự. Ứng dụng không nên tự gọi hàm đảo chuỗi để “hỗ trợ RTL”.

Một giao diện khôi phục đúng cần giữ nguyên:

- Giá trị kỹ thuật của mã, token và định danh giao dịch.
- Thứ tự các bước xác minh mà máy chủ yêu cầu.
- Ý nghĩa của hành động tiếp tục, quay lại và dùng phương thức khác.
- Trình tự truy cập bằng bàn phím và công nghệ hỗ trợ.

## 2. Thiết lập hướng ở đúng phạm vi

### 2.1. Khai báo ngôn ngữ và hướng riêng biệt

Ví dụ một trang tiếng Ả Rập:

```html
<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>استعادة الحساب</title>
</head>
<body>
  <main>
    <h1>استعادة الحساب</h1>
  </main>
</body>
</html>
```

Tiêu đề trong ví dụ có nghĩa là “Khôi phục tài khoản”. `lang="ar"` mô tả ngôn ngữ; `dir="rtl"` thiết lập hướng cơ sở. Một thuộc tính không thay thế thuộc tính còn lại.

[Hướng dẫn cấu trúc RTL của W3C](https://www.w3.org/International/questions/qa-html-dir.en) trình bày cách đặt `dir` ở cấp tài liệu và ghi đè ở phạm vi cần thiết. Ưu tiên thể hiện hướng bằng HTML để ngữ nghĩa không chỉ phụ thuộc vào CSS.

Với ứng dụng chọn locale từ một catalog được kiểm soát, có thể lưu thông tin ngôn ngữ và hướng cùng cấu hình hiển thị:

```json
{
  "vi": { "language": "vi", "direction": "ltr" },
  "en": { "language": "en", "direction": "ltr" },
  "ar": { "language": "ar", "direction": "rtl" },
  "he": { "language": "he", "direction": "rtl" }
}
```

Đây là bảng minh họa cho một tập ngôn ngữ cụ thể. Với sản phẩm có nhiều hệ chữ hoặc biến thể, hướng cần đi theo cấu hình locale và script thực sự được hỗ trợ, thay vì suy đoán từ ký tự đầu của tên locale.

Không lấy một giá trị `direction` tùy ý từ request rồi ghép thành CSS hoặc thuộc tính không kiểm tra.

### 2.2. Không dùng hướng tự động cho toàn bộ luồng

`dir="auto"` hữu ích cho một vùng văn bản chưa biết trước hướng, chẳng hạn tên thiết bị do người dùng đặt. Nó không phải lựa chọn thay thế cho hướng đã biết của cả màn hình.

Nếu hướng trang thay đổi chỉ vì tên người dùng bắt đầu bằng chữ Latin, bố cục có thể trở nên thiếu nhất quán. Đặt hướng trang theo ngôn ngữ giao diện; xử lý dữ liệu động trong vùng riêng.

## 3. Cô lập văn bản có hướng khác nhau

### 3.1. Địa chỉ, tên thiết bị và dấu câu

Trong một câu RTL, dấu ngoặc, dấu hai chấm hoặc phần số nằm cạnh nội dung LTR có thể xuất hiện ở vị trí khó hiểu nếu các vùng không được phân định.

Với dữ liệu có hướng chưa biết, dùng `bdi` hoặc vùng bao phù hợp:

```html
<p lang="ar" dir="rtl">
  الجهاز:
  <bdi id="device-name" dir="auto"></bdi>
</p>
```

Phần nhãn có nghĩa là “Thiết bị”. Ứng dụng có thể điền tên thiết bị dưới dạng văn bản:

```javascript
const deviceNameNode = document.querySelector("#device-name");
deviceNameNode.textContent = displayDeviceName;
```

`displayDeviceName` là dữ liệu đã được phép hiển thị ở bước hiện tại. Dùng `textContent` tránh diễn giải tên như HTML; dùng `bdi` xử lý sự tương tác về hướng với phần câu bên ngoài. Hai cơ chế giải quyết hai vấn đề khác nhau.

[Hướng dẫn inline bidi của W3C](https://www.w3.org/International/articles/inline-bidi-markup/index.en) giải thích việc bao sát đoạn nội dung khác hướng và dùng `bdi` hoặc `dir="auto"` khi chưa biết hướng của dữ liệu.

Với một địa chỉ Latin trong ví dụ minh họa, có thể khai báo LTR rõ ràng:

```html
<p lang="ar" dir="rtl">
  البريد الإلكتروني:
  <bdi dir="ltr">m***@example.com</bdi>
</p>
```

Không mặc định mọi địa chỉ email quốc tế đều chỉ có chữ Latin. Cách nhận, xác minh và trình bày địa chỉ cần thống nhất với phạm vi địa chỉ mà sản phẩm hỗ trợ.

Việc che địa chỉ cũng là quyết định bảo mật riêng. Không công khai địa chỉ đã che hoặc tên thiết bị chỉ vì giao diện RTL cần một ví dụ. Chỉ hiển thị thông tin tài khoản khi bước hiện tại được phép tiết lộ thông tin đó.

### 3.2. Không dùng bidi override để sửa bố cục thông thường

Không áp dụng `unicode-bidi: bidi-override` hoặc `bdo` cho toàn bộ biểu mẫu để ép thứ tự ký tự. Cách đó có thể làm mã và thông tin kỹ thuật được trình bày khác với cách người dùng cần đọc.

Trong HTML, ưu tiên markup cho phạm vi hướng. [W3C phân biệt markup và ký tự điều khiển bidi](https://www.w3.org/International/questions/qa-bidi-controls.en), trong đó khuyến nghị markup cho những trường hợp có thể biểu diễn bằng markup.

Không chèn ký tự điều khiển vô hình vào giá trị token chỉ để đạt hiệu ứng hiển thị. Nếu một định dạng văn bản thuần cần thông tin hướng, phần trình bày đó phải được tách khỏi giá trị bí mật dùng để so khớp.

## 4. Dùng CSS theo trục logic

CSS theo tọa độ vật lý thường dẫn đến nhiều bản sửa riêng cho RTL:

```css
/* Phụ thuộc vào một phía vật lý của màn hình. */
.field-message {
  margin-left: 0.75rem;
  border-left: 0.25rem solid #9f1239;
}
```

Có thể diễn đạt theo đầu và cuối của luồng:

```css
.field-message {
  margin-inline-start: 0.75rem;
  border-inline-start: 0.25rem solid #9f1239;
  padding-inline-start: 0.75rem;
  text-align: start;
}
```

Trong chế độ viết ngang thông thường, đầu inline nằm bên trái với LTR và bên phải với RTL. [CSS Logical Properties and Values của W3C](https://www.w3.org/TR/css-logical-1/) định nghĩa các giá trị và thuộc tính dựa trên luồng thay cho việc luôn gắn với trái hoặc phải.

Các thuộc tính hữu ích cho biểu mẫu khôi phục gồm:

| Nhu cầu | Thuộc tính theo luồng |
| --- | --- |
| Khoảng cách đầu hoặc cuối dòng | `margin-inline-start`, `margin-inline-end` |
| Khoảng đệm hai phía dòng | `padding-inline` |
| Viền nhấn ở đầu vùng | `border-inline-start` |
| Căn chữ theo hướng đọc | `text-align: start` |
| Kích thước theo trục dòng | `inline-size`, `max-inline-size` |
| Đặt phần tử ở cuối vùng | `inset-inline-end` |

Không cần thay mọi từ “left” hoặc “right” một cách máy móc. Có thành phần mang ý nghĩa vật lý riêng. Điều cần xác định là vị trí đang biểu đạt “đầu/cuối theo hướng đọc” hay thực sự là “trái/phải của một đối tượng”.

Tránh `transform: scaleX(-1)` trên cả trang. Phép biến đổi đó có thể lật cả chữ, mã QR, hình thương hiệu và các dấu hiệu cần nhận dạng chính xác.

## 5. Biểu mẫu nhập mã trong giao diện RTL

Ví dụ sau minh họa một bước đã được phép nhập mã xác minh. Giao diện dùng tiếng Ả Rập, còn trường mã sáu chữ số ASCII được trình bày LTR.

```html
<main lang="ar" dir="rtl" class="recovery-card">
  <h1>استعادة الحساب</h1>

  <p id="step-description">
    أدخل رمز التحقق للمتابعة.
  </p>

  <form method="post" action="/recovery/verify">
    <input
      type="hidden"
      name="csrf"
      value="{{ csrfToken }}"
    >

    <div class="field">
      <label for="recovery-code">رمز التحقق</label>
      <p id="code-help">
        أدخل الرمز المكوّن من ستة أرقام.
      </p>

      <input
        id="recovery-code"
        name="code"
        type="text"
        dir="ltr"
        inputmode="numeric"
        autocomplete="one-time-code"
        pattern="[0-9]{6}"
        maxlength="6"
        required
        aria-describedby="code-help code-error"
      >

      <p id="code-error" class="field-message" hidden></p>
    </div>

    <div class="actions">
      <button type="submit">تحقق من الرمز</button>
      <a href="/recovery/methods">استخدام طريقة أخرى</a>
    </div>
  </form>

  <p id="recovery-status" role="status" aria-atomic="true"></p>
</main>
```

Các nhãn lần lượt diễn đạt: khôi phục tài khoản, nhập mã để tiếp tục, mã xác minh, hướng dẫn nhập sáu chữ số, kiểm tra mã và dùng phương thức khác.

Đoạn HTML là khung minh họa. `{{ csrfToken }}` cần được hệ thống thực tế thay bằng giá trị và escape đúng ngữ cảnh; ví dụ không triển khai CSRF, cấp mã, giới hạn thử hoặc xác minh phía máy chủ.

```css
.recovery-card {
  box-sizing: border-box;
  inline-size: 100%;
  max-inline-size: 34rem;
  margin-inline: auto;
  padding: 1.5rem;
  text-align: start;
}

.field {
  display: grid;
  gap: 0.5rem;
  margin-block: 1.25rem;
}

.field input {
  box-sizing: border-box;
  min-inline-size: 0;
  inline-size: 100%;
  padding-block: 0.75rem;
  padding-inline: 1rem;
  font: inherit;
}

.field input[dir="ltr"] {
  text-align: start;
}

.field-message {
  margin: 0;
  border-inline-start: 0.25rem solid #9f1239;
  padding-inline-start: 0.75rem;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
}

.actions button,
.actions a {
  min-block-size: 2.75rem;
  display: inline-flex;
  align-items: center;
  padding-block: 0.5rem;
  padding-inline: 0.875rem;
}

:focus-visible {
  outline: 0.2rem solid #1d4ed8;
  outline-offset: 0.2rem;
}
```

Thứ tự DOM vẫn là trường mã, nút xác minh và liên kết phương thức khác. Không dùng `row-reverse` hoặc thuộc tính `order` chỉ để đảo lại những phần tử mà hướng của container đã sắp xếp phù hợp.

Dùng một trường mã cũng tránh việc phải điều phối sáu ô riêng theo hai hướng đọc. Nếu sản phẩm chọn nhiều ô, cần giải quyết việc dán toàn bộ mã, tự điền, thứ tự focus và vị trí con trỏ như một thành phần tương tác riêng.

### Mã số không phải một số để tính toán

`type="text"` giữ được số 0 ở đầu. `inputmode="numeric"` chỉ gợi ý bàn phím; nó không chứng minh dữ liệu hợp lệ và không buộc mọi thiết bị gửi đúng tập ký tự.

Ví dụ dùng `[0-9]{6}` nên chỉ chấp nhận sáu chữ số ASCII ở phía giao diện. Nếu sản phẩm hỗ trợ chữ số Ả Rập hoặc Ba Tư, cần một chính sách chuyển đổi được mô tả rõ và nhất quán với máy chủ. Không tự áp dụng quy tắc đó cho mã dự phòng chứa chữ hoặc token ngẫu nhiên.

Các thuộc tính giao diện không thay thế kiểm tra mục đích mã, thời hạn, số lần thử hoặc trạng thái dùng một lần.

## 6. Thứ tự thao tác, điều hướng và biểu tượng

### 6.1. Giữ trình tự có ý nghĩa

Luồng có thể gồm “Xác định tài khoản → Xác minh → Khôi phục quyền truy cập”. Khi hiển thị RTL, vị trí trực quan của tiến trình có thể đi từ phải sang trái, nhưng thứ tự bước trong dữ liệu vẫn giữ nguyên.

Có thể dùng danh sách có thứ tự và đánh dấu bước hiện tại bằng `aria-current="step"`. Không đảo mảng các bước rồi đồng thời để container RTL đảo cách bố trí lần nữa.

[W3C WAI về Meaningful Sequence](https://www.w3.org/WAI/WCAG22/Understanding/meaningful-sequence) giải thích yêu cầu duy trì trình tự có thể xác định bằng chương trình khi thứ tự ảnh hưởng đến ý nghĩa. Với biểu mẫu khôi phục, điều này giúp phần hướng dẫn, trường nhập và hành động được hiểu nhất quán.

Tránh `tabindex` dương để vá thứ tự focus khác với bố cục. Sắp xếp DOM theo trình tự thao tác có nghĩa, rồi dùng bố cục phù hợp với hướng đọc.

### 6.2. Chỉ đổi hướng biểu tượng có ý nghĩa định hướng

Một mũi tên thể hiện “quay lại” có thể cần hướng khác khi giao diện chuyển RTL. Cần chọn theo quy ước điều hướng của sản phẩm và đặt tên hành động rõ ràng.

Không tự lật:

- Biểu tượng khóa, khiên hoặc dấu xác nhận.
- Logo, ảnh đại diện và hình thiết bị.
- Mã QR dùng để thiết lập hoặc xác thực.
- Hình chứa văn bản hoặc thông tin nhận dạng.
- Ký hiệu chỉ một đối tượng vật lý có hướng riêng.

Không để mũi tên là cách duy nhất giải thích hành động. Nút cần có tên như “Quay lại đăng nhập” hoặc “Dùng phương thức khác” trong ngôn ngữ giao diện.

Nếu icon chỉ trang trí, có thể đặt `aria-hidden="true"` và giữ văn bản nút là nguồn tên truy cập. Tên truy cập không nên ghi “mũi tên trái” khi ý nghĩa thực tế là quay về bước trước.

### 6.3. Màn hình hẹp và bàn phím ảo

Câu dịch có thể dài hơn bản gốc. Hàng nút cần cho phép xuống dòng; vùng nhập không nên bị ép nhỏ chỉ vì còn một liên kết dài bên cạnh.

Khi bàn phím ảo mở, người dùng vẫn cần đọc được thông báo lỗi và tìm thấy nút tiếp tục. Tránh cố định một thanh hành động che trường mã hoặc hướng dẫn cần thiết.

Nếu cửa sổ xác thực passkey hoặc ứng dụng xác thực được mở từ luồng, không giả định giao diện hệ điều hành sẽ dùng cùng ngôn ngữ hay cùng hướng với trang. Hướng dẫn trên trang nên nói rõ hành động cần làm và lựa chọn khi không có thiết bị, thay vì dựa hoàn toàn vào vị trí một nút trong cửa sổ bên ngoài.

## 7. Thông báo lỗi và đổi ngôn ngữ giữa luồng

Thông báo lỗi thuộc trường mã nên giữ ngôn ngữ RTL của giao diện, trong khi giá trị mã vẫn có hướng riêng.

Khi mã không được chấp nhận:

1. Hiển thị thông báo bằng văn bản gần trường.
2. Liên kết thông báo với trường qua mô tả truy cập.
3. Đặt trạng thái không hợp lệ sau khi đã xác định lỗi.
4. Giữ thứ tự ký tự người dùng đã nhập theo chính sách dữ liệu.
5. Cung cấp lựa chọn thử lại hoặc lấy mã mới theo chính sách máy chủ.

Không dùng CSS căn phải để biến một lỗi tiếng Anh chưa dịch thành trải nghiệm RTL hoàn chỉnh. Hướng viết và nội dung ngôn ngữ cần được xử lý cùng nhau.

Với cập nhật không cần chuyển focus, có thể dùng vùng trạng thái. Nếu chủ động đưa focus đến phần tổng hợp lỗi, tránh đồng thời phát lại toàn bộ nội dung đó qua nhiều live region.

Khi người dùng đổi ngôn ngữ trong lúc khôi phục, ứng dụng nên giữ định danh giao dịch hiện tại và cập nhật hướng, nhãn, hướng dẫn cùng nhau. Không tự:

- Phát hành token mới chỉ vì đổi hướng hiển thị.
- Khởi động lại thời hạn hoặc số lần thử.
- Đánh dấu một bước đã được xác minh.
- Chuyển địa chỉ nhận mã sang dữ liệu khác.
- Hạ yêu cầu MFA hoặc lựa chọn bằng chứng.

Nếu giao diện phải dựng lại, cần có chính sách giữ hoặc đặt lại focus ở vị trí hợp lý. Không đưa giá trị mã hay token vào URL đổi ngôn ngữ chỉ để khôi phục trạng thái hiển thị.

## 8. Ranh giới bảo mật của dữ liệu hai chiều

### 8.1. Cô lập hướng không xác minh danh tính

Một tên thiết bị hiển thị gọn nhờ `bdi` vẫn có thể là tên do người khác đặt. Một chuỗi trông giống email quen thuộc không tự trở thành bằng chứng rằng địa chỉ đó thuộc người dùng.

Cần phân biệt:

| Lớp xử lý | Trách nhiệm |
| --- | --- |
| Bố cục và bidi | Giữ nội dung đọc được trong ngữ cảnh hai chiều |
| Escape đầu ra | Tránh diễn giải dữ liệu thành markup ngoài ý muốn |
| Kiểm tra dữ liệu | Áp dụng quy tắc hợp lệ của từng loại trường |
| Chính sách khôi phục | Quyết định bằng chứng, quyền và mức thông tin được công khai |

Không dựa vào hình thức hiển thị để quyết định hai token bằng nhau. Không dùng tên hiển thị của phương thức để xác định phương thức; cần định danh kỹ thuật do máy chủ kiểm soát.

### 8.2. Ký tự điều khiển và dữ liệu bí mật

Ký tự điều khiển hướng có thể không nhìn thấy như chữ thông thường. Với trường mã có bảng chữ cái xác định, máy chủ cần kiểm tra theo bảng chữ cái đó. Một ký tự không thuộc định dạng không nên được chấp nhận chỉ vì giao diện không hiển thị nó.

Không áp dụng quy tắc “xóa mọi ký tự Unicode đặc biệt” cho tất cả dữ liệu. Tên người dùng, tên thiết bị và văn bản tự nhiên có nhu cầu khác với token. Chính sách cần theo từng trường và tránh biến hai định danh khác nhau thành một giá trị mà không có chủ đích.

Nếu hướng dẫn lỗi cần nói về một ký tự không hợp lệ, không lặp lại toàn bộ mã bí mật vào thông báo. Cũng không ghi mã thô hoặc URL chứa token vào log để chẩn đoán lỗi RTL.

### 8.3. Đích điều hướng do máy chủ kiểm soát

Các đường dẫn “Tiếp tục”, “Quay lại” và “Dùng phương thức khác” cần được xác định theo trạng thái giao dịch và cấu hình tin cậy. Không để một chuỗi bản dịch hoặc tên phương thức chứa đích tùy ý.

Việc đổi bố cục không thay đổi origin được phép, quyền của session khôi phục hoặc trạng thái dùng một lần. Một phản hồi từ bước cũ đến muộn cũng không được kéo người dùng về màn hình đã hết hiệu lực chỉ vì hệ thống vừa đổi ngôn ngữ.

## 9. Một diễn tiến cụ thể

Một người dùng chọn giao diện tiếng Ả Rập để khôi phục tài khoản sau khi mất điện thoại:

1. Trang thiết lập `lang="ar"` và `dir="rtl"`; nhãn và hướng dẫn bắt đầu từ phía phù hợp với hướng đọc.
2. Sau khi hệ thống cho phép một phương thức khôi phục, màn hình hiển thị bước nhập mã. Mã có định dạng số ASCII nên trường nhập dùng hướng LTR, giữ được số 0 ở đầu.
3. Tên thiết bị hoặc thông tin liên hệ được phép hiển thị được đặt trong vùng cô lập hướng. Chúng không làm thay đổi hướng cả dòng hay cả trang.
4. Mã không được chấp nhận. Người dùng nhận thông báo bằng ngôn ngữ giao diện, truy cập lại trường và tiếp tục theo số lần thử mà máy chủ cho phép.
5. Người dùng chọn phương thức khác. Giao diện dùng thứ tự và nhãn rõ ràng; máy chủ vẫn quyết định phương thức nào đủ điều kiện.
6. Nếu chuyển sang tiếng Việt, bố cục đổi về LTR nhưng giao dịch, thời hạn và mức xác minh không thay đổi.

Trong diễn tiến này, RTL làm thay đổi cách trình bày và cách người dùng định hướng trên màn hình. Giá trị bí mật và quy tắc khôi phục vẫn có một ý nghĩa thống nhất ở mọi ngôn ngữ.
