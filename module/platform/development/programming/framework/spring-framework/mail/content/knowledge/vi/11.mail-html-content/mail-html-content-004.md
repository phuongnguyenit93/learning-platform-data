# CSS inline và giới hạn hỗ trợ của mail client

## 1. Vì sao HTML email không giống một trang web?

Trong **Spring Framework Mail**, ứng dụng có thể dùng `JavaMailSender` và `MimeMessageHelper` để gửi nội dung `text/html`. Về mặt cú pháp, HTML email vẫn có các thẻ quen thuộc như `<table>`, `<p>`, `<a>` và `<img>`. Tuy nhiên, **mail client không phải là một trình duyệt web đầy đủ**: mỗi ứng dụng đọc email có engine render, giới hạn bảo mật và cách xử lý CSS khác nhau.

Một email có thể đẹp ở Apple Mail nhưng bị lệch cột trong Outlook cổ điển trên Windows, mất một số định dạng ở Gmail hoặc đổi màu trong chế độ tối. Các hiện tượng thường gặp:

- Màu nền, font hoặc khoảng cách khác bản thiết kế.
- Bố cục viết bằng `display:flex` hay CSS Grid không như mong muốn.
- Nút kêu gọi hành động (CTA) mất nền hoặc khó bấm.
- Ảnh bị chặn tải, quá rộng hoặc không rõ trên dark mode.
- Nội dung đẹp trên desktop nhưng tràn màn hình mobile.
- Một phiên bản Outlook hiển thị khác với phiên bản Outlook khác.
- Thẻ HTML xuất hiện nguyên dạng vì phần MIME bị gán `text/plain` thay vì `text/html`.

SMTP vận chuyển thông điệp MIME, nhưng **không quyết định CSS được hiển thị thế nào**. Khả năng hỗ trợ HTML/CSS phụ thuộc client và bản email thực tế mà người nhận mở. Vì vậy, phải thiết kế theo nguyên tắc *tương thích rộng, có fallback và nâng cấp có điều kiện*.

> **Ý chính:** Đặt style thiết yếu trực tiếp trên phần tử HTML (CSS inline), dùng layout bảng cho những phần cần tương thích rộng, bảo đảm nội dung vẫn đọc được nếu CSS/ảnh bị hạn chế và kiểm tra trên các mail client mục tiêu.

## 2. CSS inline là gì?

**CSS inline** là cách viết quy tắc CSS trong thuộc tính `style` của chính phần tử:

~~~html
<p style="color:#1f2937; font-family:Arial,sans-serif;
          font-size:16px; line-height:24px;">
  Báo cáo của bạn đã sẵn sàng.
</p>
~~~

So sánh các cách khai báo:

| Kiểu CSS | Ví dụ | Đặc điểm trong email |
| --- | --- | --- |
| **Inline** | `<p style="color:#1f2937">...` | Quy tắc gắn trực tiếp với phần tử; phù hợp cho định dạng thiết yếu |
| **Internal stylesheet** | `<style>.notice { color:#1f2937; }</style>` | Có client hỗ trợ, nhưng có thể lọc, viết lại hoặc bỏ một số quy tắc |
| **External stylesheet** | `<link rel="stylesheet" href="...">` | Không đáng tin cậy; nhiều client không tải CSS bên ngoài |
| **HTML attribute cũ** | `<td align="center" bgcolor="#ffffff">` | Có thể làm fallback cho một số thuộc tính trong renderer cũ |

Ví dụ viết class trong stylesheet:

~~~html
<style>
  .notice {
    color: #1f2937;
    font-family: Arial, sans-serif;
    font-size: 16px;
    line-height: 24px;
  }
</style>
<p class="notice">Báo cáo đã sẵn sàng.</p>
~~~

Khi đưa style quan trọng trực tiếp vào phần tử:

~~~html
<p class="notice"
   style="color:#1f2937; font-family:Arial,sans-serif;
          font-size:16px; line-height:24px;">
  Báo cáo đã sẵn sàng.
</p>
~~~

Thư ít phụ thuộc hơn vào việc client có giữ lại stylesheet hoặc selector `.notice` hay không. **Nhưng inline CSS không bảo đảm mọi thuộc tính đều được hỗ trợ**: đặt `display:grid` vào `style=""` không làm một renderer vốn không hiểu CSS Grid bỗng hỗ trợ tính năng đó.

## 3. Giới hạn của môi trường email

### 3.1. Email HTML thường bị lọc vì bảo mật

Mail client có thể:

- Loại bỏ JavaScript, event handler như `onclick` và một số thẻ hoặc thuộc tính không an toàn.
- Lọc hoặc điều chỉnh CSS, URL, selector và các phần tử đặc biệt.
- Hiển thị nội dung trong vùng cô lập với giao diện ứng dụng.
- Chặn tải ảnh ngoài, hoặc dùng proxy/cache để lấy ảnh.
- Thay đổi màu nền/chữ khi dark mode hoặc cài đặt trợ năng hoạt động.

Vì vậy không xây dựng email dựa trên JavaScript, form tương tác phức tạp, CSS tải từ CDN hay giả định web font sẽ được tải. Giao diện nên chủ yếu mang nội dung và liên kết tới trang web an toàn.

### 3.2. Các nhóm mail client không render giống nhau

| Nhóm mail client | Điều cần đặc biệt chú ý |
| --- | --- |
| **Gmail** web/mobile | Hỗ trợ nhiều CSS, gồm một số stylesheet và media query trong các điều kiện nhất định, nhưng vẫn lọc/biến đổi HTML và có khác biệt theo môi trường |
| **Outlook cổ điển trên Windows** | Nhiều phiên bản sử dụng renderer dựa trên Microsoft Word; hạn chế mạnh với flex/grid và một số thuộc tính CSS web |
| **Outlook mới và Outlook trên web** | Cơ chế render dựa trên web khác Outlook cổ điển; không nên xem mọi sản phẩm mang tên Outlook là cùng một engine |
| **Apple Mail** macOS/iOS | Thường hỗ trợ CSS đa dạng, nhưng dark mode, việc tải nội dung từ xa và bảo vệ quyền riêng tư vẫn tác động |
| **Ứng dụng Android/mobile khác** | Phụ thuộc ứng dụng, hệ điều hành, phiên bản và chế độ xem; cần kiểm tra trên thiết bị đại diện |

Bảng này mô tả **rủi ro tương thích**, không phải danh sách bảo đảm hỗ trợ 100% một thuộc tính. Phiên bản mail client thay đổi theo thời gian; không nên lấy nhận định về một phiên bản cũ áp dụng cho mọi phiên bản mới.

### 3.3. Nội dung phải đọc được khi CSS hoặc ảnh biến mất

Nên bảo đảm:

- Thứ tự đọc của nội dung hợp lý ngay trong HTML source.
- Thông tin quan trọng hiện bằng text, không chỉ nằm trong ảnh.
- Liên kết và nút CTA có nhãn văn bản rõ nghĩa.
- Ảnh có `alt` thích hợp; hình trang trí có thể dùng `alt=""`.
- Text đủ tương phản với nền trong các tình huống màu bị ghi đè.
- Thư có bản `text/plain` dự phòng khi client không cho hiển thị HTML.

Đây là thiết kế chịu lỗi: **CSS là lớp trình bày, không nên là nơi duy nhất chứa thông tin nghiệp vụ**.

## 4. Những CSS nào đáng ưu tiên?

Không có bảng nào đúng tuyệt đối cho mọi mail client, nhưng nhóm kỹ thuật sau giúp xây dựng mức tương thích tốt hơn:

| Thuộc tính hoặc kỹ thuật | Cách sử dụng | Rủi ro |
| --- | --- | --- |
| `font-family` với font hệ thống | Inline trên text và cell chính | Luôn có fallback như `Arial, Helvetica, sans-serif` |
| `font-size`, `line-height`, `color` | Inline để giữ khả năng đọc | Client có thể áp dụng thiết lập trợ năng |
| `background-color` | Đặt trên container/cell; cân nhắc `bgcolor` | Có thể bị dark mode thay đổi |
| `padding` trên `td` | Khoảng cách nội dung cơ bản | Thường đáng tin cậy hơn phụ thuộc hoàn toàn vào margin |
| `border` và `border-collapse` | Viền cho table/cell | Cần xem kết quả trong Outlook mục tiêu |
| `width` và HTML `width` | Khung có kích thước và fallback | Tránh làm email tràn màn hình hẹp |
| `max-width` | Giới hạn bề ngang trong client hỗ trợ | Có renderer cũ cần giải pháp fallback |
| `display:block` cho `img` | Tránh khoảng trắng dưới ảnh trong nhiều layout | Ảnh vẫn có thể bị chặn tải |
| `border-radius`, `box-shadow` | Trang trí nút hoặc card | Có thể không được render; nội dung phải vẫn dùng được |
| `@media` query | Nâng cấp responsive khi được hỗ trợ | Bản mặc định vẫn phải dễ đọc |
| `display:flex`, CSS Grid | Tránh làm nền tảng layout tương thích rộng | Nhiều client/render engine không hỗ trợ đầy đủ |
| `position:fixed/absolute` | Không nên dựa vào để bố cục chính | Dễ chồng lấp hoặc bị bỏ qua |
| CSS variables, pseudo-selectors | Chỉ dùng cho enhancement | Có client không hỗ trợ/loại bỏ |
| Animation, transition, filter | Không dùng cho nội dung thiết yếu | Khả năng hỗ trợ phân mảnh |
| Web font qua `@font-face` | Trang trí có điều kiện | Phải cung cấp font hệ thống dự phòng |

### 4.1. Font, cỡ chữ và màu text

~~~html
<td style="font-family:Arial,Helvetica,sans-serif;
           font-size:16px; line-height:24px;
           font-weight:400; color:#1f2937;
           padding:16px 24px;">
  Tài khoản của bạn đã được xác minh.
</td>
~~~

Chuỗi font tạo fallback. Với nội dung tiếng Việt, font phải có glyph phù hợp; MIME `charset=UTF-8` giúp giải mã ký tự, **không chọn font và không sửa lỗi CSS**.

### 4.2. Khoảng cách trong table cell

~~~html
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td style="padding:24px 28px;">
      <p style="margin:0; font-size:16px; line-height:24px;">
        Nội dung thông báo.
      </p>
    </td>
  </tr>
</table>
~~~

Đặt khoảng cách khung trên `td` giúp tránh phụ thuộc hoàn toàn vào margin của `div`/`p` vốn có thể được render khác nhau. Không có nghĩa mọi kiểu margin đều bị cấm, nhưng phần cấu trúc nên dùng kỹ thuật ổn định hơn.

### 4.3. Màu nền và dark mode

~~~html
<td bgcolor="#ffffff"
    style="background-color:#ffffff; color:#1f2937;
           font-family:Arial,sans-serif;">
  Thông tin đơn hàng của bạn.
</td>
~~~

`bgcolor` là một fallback HTML truyền thống ở các client phù hợp; `background-color` giúp các client hỗ trợ CSS. Tuy nhiên dark mode có thể biến đổi màu, nên vẫn cần kiểm tra tương phản. Đừng đặt chữ trắng mà chỉ dựa vào ảnh nền màu tối: khi ảnh bị chặn, chữ có thể không đọc được.

## 5. Vì sao layout bảng vẫn phổ biến trong email?

Trên website, flexbox và CSS Grid thường là lựa chọn hiện đại. Trong email cần tương thích rộng, **table-based layout** vẫn hữu ích vì nhiều mail client, kể cả renderer cũ, xử lý cấu trúc bảng tương đối ổn định.

Một khung email cơ bản:

~~~html
<table role="presentation" width="100%" cellpadding="0"
       cellspacing="0" border="0"
       style="width:100%; border-collapse:collapse;">
  <tr>
    <td align="center" style="padding:24px 12px;">
      <table role="presentation" width="100%"
             cellpadding="0" cellspacing="0" border="0"
             style="width:100%; max-width:600px;
                    border-collapse:collapse;">
        <tr>
          <td style="padding:24px; font-family:Arial,sans-serif;
                     font-size:16px; line-height:24px;">
            Xin chào! Báo cáo tuần đã sẵn sàng.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
~~~

Đặc điểm:

1. Table bên ngoài rộng `100%` và có một cell căn giữa nội dung.
2. Table bên trong có `width:100%; max-width:600px` để tránh quá rộng trên nhiều client hỗ trợ.
3. `padding` trên `td` tạo khoảng cách bao quanh text.
4. Các HTML attributes `width` và `align` tạo fallback cho một số renderer.
5. `role="presentation"` thông báo đây là **bảng bố cục**, không phải bảng dữ liệu. Điều này giúp công cụ hỗ trợ tiếp cận tránh đọc các hàng/cột như dữ liệu nghiệp vụ.

Nếu email chứa **bảng dữ liệu thật** như các cột ngày, trạng thái và số tiền, hãy sử dụng markup có ngữ nghĩa bảng tương ứng như `<th>` và heading. Đừng đặt `role="presentation"` lên bảng dữ liệu chỉ vì muốn dễ style.

### 5.1. max-width và Outlook cổ điển

Một số renderer của Outlook cổ điển không xử lý `max-width` giống trình duyệt web. Khi cần giữ nội dung ở một chiều rộng cụ thể trên các phiên bản này, có thể áp dụng **hybrid layout** hoặc conditional markup dành cho Microsoft Office (MSO).

Ví dụ một container với fallback cho Outlook dùng Word engine:

~~~html
<!--[if mso]>
<table role="presentation" width="600" cellpadding="0"
       cellspacing="0" border="0">
  <tr><td>
<![endif]-->

<table role="presentation" width="100%" cellpadding="0"
       cellspacing="0" border="0"
       style="width:100%; max-width:600px;">
  <tr>
    <td style="padding:24px;">Nội dung email</td>
  </tr>
</table>

<!--[if mso]>
  </td></tr>
</table>
<![endif]-->
~~~

Conditional comments `<!--[if mso]>...<![endif]-->` là một kỹ thuật dùng trong email để phục vụ một số Outlook cổ điển; các client khác thường coi chúng là comment. Cần kiểm tra phiên bản Outlook mục tiêu và bảo đảm cặp table/tr/td mở–đóng chính xác. **Không nên thêm các nhánh MSO khi chưa có nhu cầu tương thích thực tế**, vì chúng làm markup khó bảo trì.

### 5.2. Bố cục hai cột không đồng nghĩa responsive

~~~html
<table role="presentation" width="100%"
       cellpadding="0" cellspacing="0" border="0"
       style="width:100%; border-collapse:collapse;">
  <tr>
    <td width="50%" valign="top"
        style="width:50%; padding:12px;">
      <p style="margin:0; font-family:Arial,sans-serif;">
        Mã đơn hàng: A102
      </p>
    </td>
    <td width="50%" valign="top"
        style="width:50%; padding:12px;">
      <p style="margin:0; font-family:Arial,sans-serif;">
        Trạng thái: Đã xác nhận
      </p>
    </td>
  </tr>
</table>
~~~

Đây là hai cột tỷ lệ 50/50; **chưa tự chuyển thành một cột khi màn hình hẹp**. Nội dung có thể bị ép và xuống dòng nhiều. Để mobile dễ đọc, ưu tiên cấu trúc một cột làm mặc định, hoặc dùng hybrid/fluid layout kết hợp media queries đã được thử trên nhóm client mục tiêu. Không dựa hoàn toàn vào CSS Grid để xếp cột nếu cần tương thích Outlook cổ điển.

## 6. CSS inlining: chuyển CSS class thành style trên từng phần tử

Viết sẵn toàn bộ inline CSS trong template giúp tương thích nhưng tạo nhiều đoạn lặp. Một workflow phổ biến là **viết template dễ bảo trì trước, sau đó inline CSS trong bước xử lý**:

1. Tạo HTML template và định nghĩa các class trong CSS.
2. Render dữ liệu nghiệp vụ vào template bằng cơ chế escape phù hợp.
3. Dùng công cụ **CSS inliner** để đưa các khai báo thiết yếu vào `style` trên phần tử tương ứng.
4. Có thể giữ một số quy tắc `@media` trong `<style>` để làm responsive enhancement.
5. Gửi HTML đã xử lý thông qua Spring Mail.

~~~mermaid
flowchart LR
    A["HTML template + stylesheet"] --> B["Render dữ liệu an toàn"]
    B --> C["CSS inliner"]
    C --> D["HTML với style inline"]
    D --> E["MimeMessageHelper"]
    E --> F["JavaMailSender / SMTP"]
    F --> G["Mail clients"]
~~~

### 6.1. Ví dụ trước và sau khi inline

**Trước khi xử lý:**

~~~html
<style>
  .card-title {
    color: #172554;
    font-size: 24px;
    line-height: 30px;
    font-family: Arial, sans-serif;
  }
  .description {
    color: #334155;
    font-size: 16px;
    line-height: 24px;
  }
</style>

<h1 class="card-title">Báo cáo tuần</h1>
<p class="description">Báo cáo đã được tạo thành công.</p>
~~~

**Sau khi inline CSS:**

~~~html
<h1 class="card-title"
    style="color:#172554; font-size:24px; line-height:30px;
           font-family:Arial,sans-serif;">
  Báo cáo tuần
</h1>
<p class="description"
   style="color:#334155; font-size:16px; line-height:24px;">
  Báo cáo đã được tạo thành công.
</p>
~~~

Một CSS inliner phải cân nhắc **cascade**, specificity, inheritance, `!important`, thứ tự khai báo và các inline style có sẵn. Việc copy toàn bộ khai báo một cách mù quáng có thể làm sai độ ưu tiên CSS. Vì thế, chọn công cụ xử lý HTML email phù hợp và kiểm tra **đầu ra sau transform** là cần thiết.

### 6.2. Không phải rule nào cũng đưa vào style="" được

~~~css
@media screen and (max-width: 600px) {
  .content { padding: 16px !important; }
}

.button:hover {
  background-color: #1e40af;
}
~~~

`@media` phụ thuộc điều kiện viewport; `:hover` phụ thuộc trạng thái tương tác. Chúng **không tương đương một style tĩnh** ở mọi thời điểm. Tool inliner có thể giữ, bỏ hoặc xử lý riêng những quy tắc này tùy cấu hình. Với email, nên coi chúng là bổ sung, không phải điều kiện để nội dung chính đọc được.

### 6.3. JavaMailSender không tự inline CSS

~~~java
helper.setText(html, true);
mailSender.send(message);
~~~

`setText(..., true)` chỉ đánh dấu phần nội dung là **HTML**. `MimeMessageHelper` và `JavaMailSender` **không tự biến toàn bộ `<style>` hay stylesheet ngoài thành inline CSS**. Nếu cần inlining tự động, phải có bước xử lý trước lời gọi `setText` hoặc sử dụng sẵn template có style inline.

Tương tự, một template engine như Thymeleaf giúp render dữ liệu vào HTML; **render template và CSS inlining là hai bước có trách nhiệm khác nhau**, trừ khi chính pipeline của dự án chủ động tích hợp thêm inliner.

## 7. Responsive email khi media queries không ổn định

Với một trang web, responsive layout thường dựa vào CSS `@media`. Trong email, mức hỗ trợ media query thay đổi theo mail client. Vì thế một chiến lược thực tế là **mobile-friendly by default**, sau đó thêm media query như enhancement.

Ví dụ:

~~~html
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    @media screen and (max-width: 600px) {
      .mobile-padding {
        padding-left: 16px !important;
        padding-right: 16px !important;
      }
      .mobile-full {
        width: 100% !important;
        display: block !important;
      }
    }
  </style>
</head>
<body>
  <table role="presentation" width="100%"
         cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td class="mobile-padding"
          style="padding:24px; font-family:Arial,sans-serif;">
        Nội dung phải đọc được ngay cả khi media query bị bỏ.
      </td>
    </tr>
  </table>
</body>
~~~

`<meta name="viewport">` giúp nhiều client di động xử lý chiều rộng, nhưng không phải mọi email client đều giữ/tuân theo nó. `@media` có thể thay padding khi màn hình hẹp, song **base style** vẫn phải dễ đọc. Không đặt kích thước chữ quá nhỏ rồi trông chờ media query luôn tăng cỡ chữ.

### 7.1. Những nguyên tắc responsive có fallback

- Đặt container có chiều rộng tối đa hợp lý và cho phép co giãn trên màn hình hẹp khi renderer hỗ trợ.
- Ưu tiên một cột cho nội dung chính; hạn chế nhiều cột có text dài.
- Dùng font khoảng 16px cho body như một điểm khởi đầu dễ đọc, rồi điều chỉnh theo thiết kế và thử nghiệm.
- Tạo CTA với khoảng đệm đủ lớn để bấm trên màn hình cảm ứng.
- Dùng ảnh có `width` phù hợp và `style="max-width:100%; height:auto;"` khi client hỗ trợ; có fallback theo kích thước thiết kế.
- Tránh chuỗi không ngắt quá dài như URL thô trong vùng hẹp; đặt link sau một nhãn văn bản thay vì in toàn URL.
- Đảm bảo email vẫn hợp lý khi media queries bị loại bỏ.

### 7.2. Kỹ thuật hybrid/fluid

**Hybrid email** kết hợp layout co giãn, các giới hạn kích thước và (khi cần) fallback dành cho renderer cũ để một email không phụ thuộc hoàn toàn vào media query. Ví dụ, có thể dùng table bên ngoài rộng 100%, container bên trong có `max-width`, rồi cân nhắc conditional table cho Outlook cổ điển.

Đây là một chiến lược bố cục chứ không phải một CSS property đơn lẻ. Sự tương thích tốt phụ thuộc **toàn bộ markup, thứ tự cell, fallback và các client mục tiêu**; không thể chỉ thêm `max-width` và khẳng định email sẽ responsive trên mọi ứng dụng.

## 8. Dark mode: màu inline vẫn có thể bị thay đổi

Nhiều mail client hỗ trợ dark mode và có thể:

1. Giữ nguyên màu inline.
2. Đổi một phần màu nền/text.
3. Đảo hoặc biến đổi màu theo thuật toán của client.
4. Chỉ áp dụng một số thay đổi trên phần header/body nhất định.

Do đó, `style="background-color:#ffffff; color:#111827;"` **không bảo đảm** nền luôn trắng và chữ luôn tối.

Các điểm cần làm:

- Tạo màu có tương phản tốt trong cả bối cảnh sáng và tối.
- Nếu logo có nền trong suốt, kiểm tra nó có còn rõ trên nền tối không; đôi khi cần biến thể logo hoặc viền sáng/tối phù hợp.
- Tránh chữ nằm trong ảnh khi có thể, để text vẫn đọc được khi ảnh bị chặn.
- Không đặt nền ảnh là nguồn duy nhất tạo tương phản cho chữ.
- Kiểm tra CTA và link ở chế độ sáng/tối trên các client đại diện.
- Có thể thêm các gợi ý hỗ trợ như `color-scheme`, `supported-color-schemes` hoặc `@media (prefers-color-scheme: dark)` khi client hỗ trợ, nhưng coi chúng là enhancement và thử nghiệm trên từng nhóm client.

Ví dụ một quy tắc bổ sung:

~~~css
@media (prefers-color-scheme: dark) {
  .surface {
    background-color: #111827 !important;
    color: #f9fafb !important;
  }
}
~~~

Quy tắc này không thay thế inline CSS và không phải mọi client đều giữ hoặc tuân theo `prefers-color-scheme`. Một số client tự chỉnh màu độc lập với media query; thiết kế vẫn phải chấp nhận các cách render khác nhau.

## 9. Mẫu HTML email có CSS inline cho thông báo nghiệp vụ

Một ví dụ tự chứa sau sử dụng table layout, inline styles, font dự phòng và một nút liên kết có văn bản. Những yếu tố này được chọn để giảm phụ thuộc vào JavaScript, ảnh ngoài hoặc CSS selector phức tạp.

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Báo cáo tuần đã sẵn sàng</title>
</head>
<body style="margin:0; padding:0; background-color:#f1f5f9;">
  <table role="presentation" width="100%" cellpadding="0"
         cellspacing="0" border="0"
         style="width:100%; border-collapse:collapse;
                background-color:#f1f5f9;">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellpadding="0"
               cellspacing="0" border="0"
               style="width:100%; max-width:600px;
                      border-collapse:collapse;
                      background-color:#ffffff;">
          <tr>
            <td bgcolor="#ffffff"
                style="padding:32px 28px; background-color:#ffffff;">
              <h1 style="margin:0 0 16px; color:#0f172a;
                         font-family:Arial,Helvetica,sans-serif;
                         font-size:24px; line-height:30px;
                         font-weight:700;">
                Báo cáo tuần đã sẵn sàng
              </h1>
              <p style="margin:0 0 18px; color:#334155;
                        font-family:Arial,Helvetica,sans-serif;
                        font-size:16px; line-height:24px;">
                Bạn có thể mở báo cáo mới nhất từ liên kết bên dưới.
              </p>
              <table role="presentation" cellpadding="0"
                     cellspacing="0" border="0">
                <tr>
                  <td bgcolor="#1d4ed8" align="center"
                      style="background-color:#1d4ed8;
                             padding:14px 22px;">
                    <a href="https://example.com/reports"
                       style="color:#ffffff; text-decoration:none;
                              font-family:Arial,Helvetica,sans-serif;
                              font-size:16px; line-height:20px;
                              font-weight:700; display:inline-block;">
                      Xem báo cáo
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:20px 0 0; color:#475569;
                        font-family:Arial,Helvetica,sans-serif;
                        font-size:14px; line-height:21px;">
                Nếu nút không hoạt động, hãy mở trang báo cáo
                từ ứng dụng của bạn.
              </p>
            </td>
          </tr>
          <tr>
            <td bgcolor="#e2e8f0"
                style="padding:16px 28px; background-color:#e2e8f0;
                       color:#334155; font-family:Arial,sans-serif;
                       font-size:12px; line-height:18px;">
              Đây là thông báo tự động của hệ thống.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
~~~

**Các quyết định thiết kế ở ví dụ:**

- Dùng `table` có `role="presentation"` để bố cục. Không dùng CSS Grid/Flexbox.
- Các màu, font, padding và line-height thiết yếu nằm trong `style` trực tiếp.
- `bgcolor` trên một số `td` đóng vai trò fallback bên cạnh `background-color`.
- Nút CTA là một liên kết `<a>` thật, có text rõ nghĩa.
- Không phụ thuộc vào ảnh để truyền đạt “Báo cáo đã sẵn sàng”.
- Đặt `width:100%; max-width:600px` cho khung nội dung, có thể cần fallback riêng cho Outlook cổ điển.
- Link là một URL mẫu. Trong ứng dụng thật, phải lấy URL từ cấu hình hoặc nghiệp vụ tin cậy và chỉ dùng domain được phép.

**Giới hạn của mẫu:** Đây là điểm xuất phát cho một email có thể đọc tốt, không phải lời bảo đảm pixel-perfect trên mọi client. Một số Outlook cũ có thể xử lý độ rộng, nút và margin khác; dark mode có thể thay màu; các phiên bản ứng dụng di động có thể reflow nội dung. Nếu CTA cần khả năng hiển thị đặc biệt trên Outlook cổ điển, có thể cân nhắc phương án nút có VML fallback, nhưng giải pháp đó cần thiết kế và kiểm tra riêng cho tập client thực tế.

### 9.1. Tại sao không đặt toàn bộ CTA trong một ảnh?

Nếu CTA chỉ là một ảnh có chữ “Xem báo cáo”, khi ảnh không được tải, người dùng có thể mất hoàn toàn hành động chính. Một `<a>` chứa văn bản có nghĩa vẫn có thể bấm khi style bị hạn chế. Nếu ảnh chỉ nhằm trang trí, nên giữ hành động và nội dung quan trọng ở dạng HTML text.

### 9.2. Cần cân nhắc chiều rộng của ảnh

Nếu email thêm logo:

~~~html
<img src="https://static.example.com/mail/logo.png"
     width="160" height="48"
     alt="Logo dịch vụ"
     style="display:block; width:160px; max-width:100%;
            height:auto; border:0;">
~~~

Lý do khai báo `width` và `height` là để cung cấp kích thước dự kiến, hạn chế layout nhảy trong những client phù hợp. `style="max-width:100%; height:auto;"` giúp ảnh không vượt khung ở client hỗ trợ. Nhưng nhiều client **chặn tải ảnh từ xa**; dùng `alt` không thể thay thế tất cả nội dung ảnh. URL `https://static.example.com/...` chỉ là địa chỉ ví dụ, không phải tài nguyên cần truy cập để bài học hoạt động.

## 10. Tạo và gửi HTML có CSS inline bằng Spring Framework Mail

Spring Mail **không render CSS và không kiểm tra client có hỗ trợ một thuộc tính nào hay không**. Nó nhận chuỗi HTML đã chuẩn bị, đặt đúng MIME content type và gửi qua transport.

### 10.1. Ví dụ service gửi HTML và plain text

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportEmailService {

    private final JavaMailSender mailSender;

    public ReportEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReportNotice(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("reports@example.com");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tuần đã sẵn sàng");

        String plainText = "Báo cáo tuần đã sẵn sàng. "
                + "Mở https://example.com/reports để xem.";

        String html = """
                <!doctype html>
                <html lang="vi">
                <body style="margin:0; padding:0;">
                  <table role="presentation" width="100%"
                         cellpadding="0" cellspacing="0" border="0">
                    <tr>
                      <td style="padding:24px; font-family:Arial,sans-serif;
                                 color:#1f2937; font-size:16px;
                                 line-height:24px;">
                        <h1 style="font-size:24px; line-height:30px;
                                   margin:0 0 16px;">
                          Báo cáo tuần đã sẵn sàng
                        </h1>
                        <p style="margin:0 0 20px;">
                          Bạn có thể xem báo cáo mới nhất.
                        </p>
                        <a href="https://example.com/reports"
                           style="color:#ffffff; background-color:#1d4ed8;
                                  padding:12px 20px; text-decoration:none;">
                          Xem báo cáo
                        </a>
                      </td>
                    </tr>
                  </table>
                </body>
                </html>
                """;

        // Hai phiên bản nội dung: text/plain và text/html.
        helper.setText(plainText, html);

        mailSender.send(message);
    }
}
~~~

Ví dụ sử dụng Java text blocks (Java 15 trở lên; Spring Framework 6 yêu cầu Java 17). Đây là mã minh họa tạo nội dung **tĩnh và tin cậy**; trong hệ thống thật, đường dẫn, địa chỉ gửi và nội dung cần lấy từ cấu hình/nghiệp vụ đã được kiểm soát.

Các điểm cần hiểu:

1. `mailSender.createMimeMessage()` tạo thông điệp MIME, **chưa gửi**.
2. `new MimeMessageHelper(message, true, "UTF-8")` bật khả năng multipart và chọn UTF-8.
3. `helper.setText(plainText, html)` tạo **hai phiên bản thay thế của cùng nội dung**, giúp client có thể dùng `text/plain` khi không hiển thị HTML.
4. Trong `html`, style hiển thị quan trọng đã được đặt inline.
5. `mailSender.send(message)` thực hiện gửi qua Jakarta Mail/SMTP với cấu hình của hệ thống.

Nếu chỉ gửi một body HTML, helper cũng hỗ trợ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Thông báo");
helper.setText("<p style=\"color:#1f2937;\">Xin chào!</p>", true);
mailSender.send(message);
~~~

Ở `setText(html, true)`, tham số `true` chỉ định **body HTML**. Nó không tự thêm bản plain text. Còn `true` trong constructor `MimeMessageHelper(message, true, "UTF-8")` lại là **cờ bật multipart**. Hai vị trí `true` có ý nghĩa khác nhau.

### 10.2. CSS nên được inline ở bước nào?

Một pipeline gửi email có template có thể tổ chức:

~~~text
Nghiệp vụ xác định người nhận / nội dung
             |
             v
Template engine render dữ liệu đã escape an toàn
             |
             v
CSS inliner chuyển quy tắc thiết yếu thành style=""
             |
             v
Tạo bản text/plain tương đương
             |
             v
MimeMessageHelper.setText(plainText, htmlWithInlineCss)
             |
             v
JavaMailSender.send(message)
~~~

Đặt inlining **trước khi gọi `setText`** giúp rõ ràng rằng JavaMailSender nhận **HTML đã xử lý**. Tool inliner không nên tự ý chạy trên nội dung người dùng chưa được kiểm soát; bước render/escape cần thực hiện theo hợp đồng dữ liệu của template.

Nếu template được build trước thành tài nguyên HTML đã inline CSS, runtime cũng có thể chỉ đọc template đó và render biến động phù hợp. Chọn cách nào tùy hệ thống cần cập nhật template qua deploy hay qua kho dữ liệu, nhưng phải giữ nhất quán thứ tự **render → inline → MIME → send** hoặc một thứ tự tương đương đã được thiết kế rõ ràng.

### 10.3. Inline CSS và MIME charset là hai vấn đề khác nhau

Một phần email có thể mang:

~~~text
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

`charset=UTF-8` mô tả cách giải mã ký tự; `Content-Transfer-Encoding` mô tả cách biểu diễn bytes khi vận chuyển. CSS inline là nội dung bên trong HTML:

~~~html
<p style="font-size:16px; color:#1f2937;">Xin chào!</p>
~~~

Nếu chữ tiếng Việt bị lỗi ký tự, cần kiểm tra charset, transfer encoding và dữ liệu đầu vào. Nếu chữ đúng nhưng layout lệch, kiểm tra CSS, HTML và mail client. Đổi encoding của `MimeMessageHelper` sẽ **không** khiến Outlook hỗ trợ CSS Grid.

## 11. Ảnh inline CID, ảnh ngoài và CSS

Trong email HTML, có hai nhóm ảnh thường gặp:

**Ảnh được tải từ URL:**

~~~html
<img src="https://static.example.com/mail/banner.png"
     width="560" alt="Thông tin báo cáo"
     style="display:block; width:100%; max-width:560px;
            height:auto; border:0;">
~~~

Ảnh loại này có thể bị mail client chặn tải hoặc truy cập qua proxy. Đó không hẳn là lỗi HTML hay CSS.

**Ảnh đính kèm inline và tham chiếu bằng Content-ID:**

~~~html
<img src="cid:report-logo"
     width="160" alt="Logo báo cáo"
     style="display:block; width:160px; max-width:100%;
            height:auto; border:0;">
~~~

Với Spring Mail, có thể tạo phần image MIME có ID tương ứng:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Thông báo có logo");

String html = "<p style=\"font-family:Arial,sans-serif;\">"
        + "Báo cáo đã sẵn sàng.</p>"
        + "<img src=\"cid:report-logo\" alt=\"Logo báo cáo\""
        + " width=\"160\" style=\"display:block;width:160px;\">";

// Đặt HTML trước khi thêm inline resource.
helper.setText("Báo cáo đã sẵn sàng.", html);
helper.addInline("report-logo", logoResource, "image/png");

mailSender.send(message);
~~~

Đoạn code giả định có một `logoResource` kiểu `org.springframework.core.io.Resource` chứa ảnh PNG hợp lệ, có thể đọc được. `cid:report-logo` trong HTML phải tương ứng `Content-ID: <report-logo>` ở part ảnh MIME; `MimeMessageHelper.addInline(...)` giúp tạo mối liên hệ đó.

**Giới hạn:** ảnh CID có thể được các mail client hiển thị khác nhau, thậm chí bị liệt kê như attachment trong một số hoàn cảnh. CSS inline không tự sửa được việc ID không khớp, nội dung MIME lỗi hoặc chính sách chặn ảnh. Khi chẩn đoán, cần xem `multipart/related`, `Content-ID` và bản email thực nhận.

## 12. Những khác biệt cần quan tâm theo mail client

### 12.1. Gmail: có CSS nhưng vẫn có bước lọc HTML

Gmail có thể hiển thị CSS inline và hỗ trợ các quy tắc CSS trong `<style>` trong nhiều tình huống. Tuy nhiên Gmail cũng có thể xử lý lại HTML, loại bỏ thuộc tính không được phép, và áp dụng quy tắc riêng cho một số loại nội dung.

Vì thế:

- Đừng phụ thuộc vào việc Gmail tải `<link rel="stylesheet">` từ Internet.
- Đừng đặt style thiết yếu chỉ trong selector phức tạp hoặc các rule nằm bên ngoài message.
- Hãy kiểm tra nội dung **trong hộp thư Gmail thực nhận**, không chỉ preview trên trình duyệt.
- Cân nhắc kích thước HTML email. Gmail có thể cắt bớt nội dung hiển thị đối với email HTML lớn; điều này còn ảnh hưởng những style/element nằm gần cuối thông điệp.
- Không cho rằng khả năng render của Gmail web và mọi ứng dụng Gmail di động là giống hệt.

Một nội dung bị cắt hoặc stylesheet bị biến đổi có thể khiến thiết kế khác xa preview dù SMTP đã chấp nhận message.

### 12.2. Outlook cổ điển: cần phân biệt engine Word

Đối với nhiều phiên bản Outlook cổ điển trên Windows:

- Cấu trúc bảng và kích thước tường minh thường đáng tin cậy hơn CSS flex/grid.
- Các thuộc tính margin, padding hoặc nền có thể được xử lý khác với trình duyệt.
- `border-radius` và background image có thể thiếu hỗ trợ hoặc cần fallback.
- Nút CTA có thể không có hình dáng đúng nếu chỉ dựa vào CSS của thẻ `<a>`.
- Conditional MSO markup hoặc VML có thể được dùng trong những mẫu đòi hỏi giao diện riêng cho Outlook, nhưng làm tăng chi phí bảo trì.

Chú ý rằng **Outlook mới và Outlook trên web không nhất thiết dùng cùng renderer Word**. Khi phát hiện lỗi, phải xác định **tên phiên bản và nền tảng** chứ không chỉ ghi chung “lỗi Outlook”.

### 12.3. Apple Mail: hỗ trợ CSS tốt hơn không có nghĩa giống browser

Apple Mail thường hiển thị CSS hiện đại tốt hơn nhiều client khác, nhưng:

- Dark mode có thể làm màu sắc thay đổi.
- Mail Privacy Protection hoặc chính sách tải nội dung từ xa ảnh hưởng cách ảnh được tải và việc đo lường.
- Web font, media query hoặc hiệu ứng CSS không nên là điều kiện duy nhất để hiểu thông điệp.
- Kết quả ở Apple Mail không chứng minh HTML tương thích với Outlook cổ điển.

### 12.4. Mobile mail clients: một email phải chịu nhiều vùng hiển thị

Người dùng có thể mở email trong app, webview, split view hoặc cửa sổ kích thước hẹp. Ngay cả khi desktop đẹp, các thành phần có `width="600"` cố định, URL không ngắt được hoặc ảnh quá lớn có thể tràn màn hình. Thiết kế mobile-friendly cần được xem từ **khả năng đọc nội dung** trước rồi mới tới việc sắp xếp đồ họa.

## 13. Phân biệt lỗi CSS, MIME và lỗi tải tài nguyên

Không phải email nào hiển thị sai cũng do CSS. Khi chẩn đoán nên phân biệt:

| Triệu chứng | Vị trí cần xem | Hướng xử lý |
| --- | --- | --- |
| Người nhận thấy `<p>Xin chào</p>` nguyên văn | `Content-Type` của body MIME | Dùng `setText(html, true)` hoặc `setText(plain, html)` phù hợp |
| Chữ “Đã gửi” bị thành ký tự rác | `charset`/transfer encoding và dữ liệu nguồn | Kiểm tra UTF-8, MIME part và việc mã hóa trùng |
| HTML có nội dung nhưng mất cỡ chữ/màu | Style inline, `<style>` và cách client lọc CSS | Inline những khai báo thiết yếu |
| Hai cột xếp chồng hoặc lệch trong Outlook | CSS flex/grid, table structure | Dùng table/hybrid fallback phù hợp |
| Logo không hiển thị | URL ảnh bị chặn hoặc `cid:` không khớp `Content-ID` | Phân biệt remote image và MIME inline image |
| Nút CTA mất màu nhưng link còn | CSS background/border trên `<a>`/`td` | Dùng cell nền làm fallback, kiểm tra Outlook |
| Màu bị đảo trong dark mode | Color transformation của mail client | Kiểm tra tương phản, logo và fallback |
| Font khác mockup | Font không có, web font không tải | Sử dụng font hệ thống dự phòng |
| HTML bị cắt cuối | Kích thước nội dung hoặc cơ chế hiển thị của client | Giảm markup thừa, inline có kiểm soát |
| Email có HTML nhưng chỉ hiển thị text | `multipart/alternative`, thứ tự part hoặc cài đặt client | Kiểm tra MIME tree và khả năng hiển thị HTML |
| Email “gửi thất bại” | SMTP AUTH/TLS/recipient/data | Phân tích exception và phản hồi SMTP, không chỉ sửa CSS |

### 13.1. Cách thu thập bằng chứng

Nếu người nhận báo email hiển thị lỗi:

1. Ghi lại mail client, nền tảng, phiên bản, dark mode và thiết bị bị ảnh hưởng.
2. Lấy bản **Show original / View source / Download original (.eml)** của email thực nhận nếu được phép.
3. Xác định `Content-Type`, phần `text/html`, `text/plain` và quan hệ multipart.
4. Đọc HTML part sau khi giải mã transfer encoding, kiểm tra style thực có nằm trong thuộc tính `style` không.
5. Kiểm tra style bị loại do client hay không, và so sánh với HTML trước khi gửi.
6. Xem có ảnh ngoài bị chặn hoặc part CID bị lỗi không.
7. Nếu MIME/HTML đúng nhưng chỉ một client sai, tập trung vào renderer của client đó.

Một bản screenshot chỉ cho biết *triệu chứng*. Bản `.eml` và các MIME headers cho biết **nội dung thực** được nhận; kết hợp hai loại dữ liệu giúp phân biệt lỗi ở bước tạo template, inlining, MIME và ứng dụng hiển thị.

### 13.2. Kiểm tra message Spring đã tạo trước khi gửi

Khi cần quan sát MIME trong môi trường thử nghiệm, `MimeMessage` có thể được serialize:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("reports@example.com");
helper.setTo("test@example.net");
helper.setSubject("Bản xem thử");
helper.setText("Bản text.", "<p style=\"color:#1f2937;\">Bản HTML.</p>");

message.saveChanges();
try (java.io.OutputStream output = java.nio.file.Files.newOutputStream(
        java.nio.file.Path.of("preview.eml"))) {
    message.writeTo(output);
}
~~~

Đoạn mã giả định được đặt trong method có xử lý/khai báo `MessagingException` và `IOException`. Nó chỉ tạo tệp `preview.eml`, **không gửi email** vì chưa gọi `mailSender.send(message)`. Hãy dùng dữ liệu giả, lưu vào nơi được cấp quyền và không để lộ nội dung thư chứa thông tin nhạy cảm.

## 14. Bảo mật khi dựng HTML email và CSS inline

HTML email là dữ liệu được gửi tới phần mềm của người nhận, vì vậy cần phân biệt hai vấn đề:

**Bảo vệ phía người nhận:** client thường lọc các yếu tố nguy hiểm, nhưng ứng dụng không được phụ thuộc vào bộ lọc đó để xử lý dữ liệu đầu vào không đáng tin cậy. Không cố chèn JavaScript, event handler hoặc hình thức nhúng tương tác đòi hỏi quyền không phù hợp.

**Bảo vệ hệ thống gửi:** nếu nội dung email chứa tên người dùng, mã sản phẩm, đường dẫn hoặc thông báo động, phải escape giá trị theo **ngữ cảnh** HTML text hoặc HTML attribute. Không nối thẳng dữ liệu chưa kiểm soát vào cấu trúc HTML/CSS.

Ví dụ không an toàn:

~~~java
String html = "<p>Xin chào " + userDisplayName + "</p>";
~~~

Nếu `userDisplayName` chứa dấu `<`, `>`, dấu nháy hoặc một đoạn HTML, nội dung có thể bị diễn giải như markup. Nên dùng template engine có cơ chế escape mặc định cho text, hoặc hàm escape HTML đáng tin cậy trước khi chèn dữ liệu vào ngữ cảnh thích hợp. Việc escape text khác với kiểm soát an toàn của **URL** hoặc giá trị **CSS**.

Các nguyên tắc cần thiết:

- Chỉ xây dựng link tới domain/đường dẫn được ứng dụng cho phép; không tạo `href` từ URL tùy ý do người dùng chưa được tin cậy cung cấp.
- Không nhúng access token dài hạn hoặc dữ liệu bí mật trực tiếp vào URL email.
- Không dùng CSS như cách che giấu nội dung quan trọng hoặc đánh lừa người nhận.
- Không cho người dùng tùy ý cung cấp HTML/CSS nguyên vẹn nếu nghiệp vụ không cần. Nếu có, cần hệ thống làm sạch nội dung theo whitelist được duy trì phù hợp.
- Không coi một công cụ **CSS inliner** là công cụ **HTML sanitizer**. Inlining và kiểm tra an toàn nội dung là hai bước khác nhau.
- Với ảnh/tệp đính kèm, kiểm soát nguồn dữ liệu, loại file và kích thước trước khi gửi.

## 15. Quy trình kiểm thử giao diện HTML email

Vì không thể suy ra hỗ trợ của mọi client từ một trình duyệt duy nhất, việc kiểm thử cần bao phủ **tập khách hàng thực** của hệ thống. Có thể tổ chức thành các mức:

### Mức 1 — Xem trước template trong môi trường phát triển

- Render template với dữ liệu mẫu: tiếng Việt, chuỗi dài, số tiền, danh sách nhiều phần tử và trường rỗng.
- Kiểm tra nội dung cơ bản, thứ tự đọc và liên kết.
- Kiểm tra HTML sau bước CSS inlining, không chỉ template nguồn.

Preview trên Chrome/Firefox chỉ có giá trị ở giai đoạn này; nó **không thay thế** thử nghiệm mail client.

### Mức 2 — Gửi qua SMTP sink hoặc hộp thư kiểm thử

- Dùng SMTP sink cô lập như Mailpit/MailHog trong local để xem bản email được tạo.
- Kiểm tra phần MIME `text/plain` và `text/html`, encoding UTF-8 và tài nguyên inline.
- Mở bản raw `.eml` để xác nhận CSS thiết yếu đã được inline.
- Không dùng địa chỉ khách hàng thật cho các lần kiểm thử nội dung.

### Mức 3 — Kiểm tra trên các client mục tiêu

Ví dụ ma trận thử nghiệm:

| Nền tảng | Những điều cần xem |
| --- | --- |
| Gmail trên web | Style inline, khoảng cách, link, ảnh ngoài, clipping |
| Gmail trên di động | Chiều rộng, font, khả năng bấm CTA, ảnh |
| Outlook cổ điển Windows | Table widths, cell padding, nút, ảnh, fallback MSO |
| Outlook mới/web | Layout so với Outlook cổ điển, dark mode và ảnh |
| Apple Mail macOS/iOS | Responsive, font, dark mode, hình ảnh |
| Client khác có tỷ lệ người dùng cao | Những chức năng cụ thể mà nhóm khách hàng cần |

Không nhất thiết hỗ trợ mọi client trên thị trường. Hãy xác định nhóm cần ưu tiên, định nghĩa những sai khác giao diện chấp nhận được và bảo đảm chức năng quan trọng (nội dung, link, tài liệu) hoạt động.

### Mức 4 — Kiểm tra trường hợp suy giảm

Hãy thử:

- Tắt tải ảnh ngoài.
- Dùng dark mode.
- Tăng kích thước chữ theo thiết lập trợ năng.
- Mở thư trên màn hình hẹp.
- Xem bản plain text.
- Thử email có tiêu đề/text dài và nội dung động có dấu tiếng Việt.
- Xem thư được forward, vì hệ thống chuyển tiếp có thể thay đổi HTML/MIME.

**Mục tiêu không phải pixel-perfect:** quan trọng hơn là email luôn đọc được, CTA rõ ràng, các con số và liên kết không bị mất hoặc hiểu nhầm.

## 16. Các câu hỏi thường gặp

**“CSS inline có được mọi mail client hỗ trợ không?”**  
Inline CSS thường là một trong những phương án tương thích nhất cho style quan trọng, nhưng khả năng hỗ trợ **từng CSS property** vẫn khác nhau. Không có bảo đảm rằng flex/grid/animation sẽ chạy chỉ vì đã inline.

**“Gmail có hỗ trợ thẻ style không?”**  
Gmail hỗ trợ nhiều kiểu CSS và có thể xử lý `<style>` trong các điều kiện nhất định; không nên khẳng định Gmail luôn xóa mọi stylesheet. Với định dạng thiết yếu, inline CSS vẫn là phương án đáng cân nhắc vì email còn được mở ở những client khác.

**“Có nên dùng Bootstrap trong email?”**  
Không nên phụ thuộc vào stylesheet Bootstrap từ CDN hoặc các component CSS/JavaScript của website. Có thể học ý tưởng spacing và màu sắc, nhưng email cần một HTML layout và CSS được thiết kế/inline riêng với fallback phù hợp.

**“Vì sao HTML đẹp trong trình duyệt nhưng hỏng ở Outlook?”**  
Outlook cổ điển có thể dùng renderer Microsoft Word thay vì engine trình duyệt hiện đại. Các kỹ thuật như flex/grid hoặc margin có thể không được hỗ trợ như mong đợi. Cần chọn bố cục bảng, fallback và kiểm tra đúng phiên bản.

**“Dùng Spring MimeMessageHelper có tự khắc phục lỗi CSS không?”**  
Không. Helper tạo MIME message và đánh dấu body `text/html`, không tự biến CSS web thành CSS tương thích tất cả mail client.

**“Nếu ảnh không xuất hiện thì có phải CSS inline sai?”**  
Chưa chắc. Có thể là client chặn ảnh ngoài, URL hết hạn, sai `cid:`/`Content-ID`, MIME image part lỗi hoặc dark mode làm ảnh khó nhìn. Cần xác định loại ảnh và kiểm tra bản email thực.

**“Có cần dùng @media cho email responsive?”**  
Có thể, nhưng không nên phụ thuộc hoàn toàn vào nó. Dùng base layout đủ tốt cho mobile và để media query cải thiện khi được hỗ trợ.

**“Sử dụng CSS inline có giúp email không vào Spam?”**  
Không có quan hệ bảo đảm như vậy. Việc phân loại spam phụ thuộc nhiều yếu tố khác như xác thực miền gửi, uy tín gửi, nội dung, danh sách nhận và chính sách provider. CSS inline chủ yếu phục vụ khả năng **hiển thị**.

**“Thư plain text có CSS được không?”**  
Không. `text/plain` là văn bản thuần; CSS chỉ có ý nghĩa khi mail client render phần HTML. Với `multipart/alternative`, client có thể chọn bản plain hoặc HTML theo khả năng/cài đặt.

## 17. Ghi nhớ khi làm HTML email trong Spring Framework Mail

Một pipeline đáng tin cậy nên tách rõ trách nhiệm:

~~~text
Business data
   |
   v
Template render (escape dữ liệu)
   |
   v
HTML + CSS thiết kế cho email
   |
   v
CSS inlining cho style thiết yếu
   |
   v
Plain-text alternative + HTML MIME part (UTF-8)
   |
   v
MimeMessageHelper / JavaMailSender
   |
   v
SMTP transport -> Mail client render
~~~

Ở tầng **template**, hãy dùng inline style có fallback, cấu trúc bảng khi cần tương thích rộng và bảo đảm nội dung vẫn rõ khi CSS/ảnh bị hạn chế. Ở tầng **Spring Mail**, dùng `MimeMessageHelper.setText(plain, html)` để tạo hai phiên bản nội dung, đặt charset thích hợp và không nhầm bước gửi MIME với bước xử lý CSS. Ở tầng **kiểm tra hiển thị**, quan sát bản email thực trên các client quan trọng, nhất là Outlook cổ điển, Gmail, mobile và dark mode.

Kết luận: **CSS inline là kỹ thuật cốt lõi để tăng độ tin cậy của giao diện HTML email, không phải một công tắc tương thích tuyệt đối**. Thành công đến từ việc kết hợp markup có cấu trúc, CSS đơn giản, fallback hợp lý, nội dung truy cập được và thử nghiệm trên đúng các mail client mà ứng dụng cần phục vụ.
