# Recovery email template

## 1. Mẫu email khôi phục cần giúp người dùng làm đúng việc

Email khôi phục tài khoản là một thông điệp bảo mật có thể mang liên kết hoặc mã chứng minh quyền tiếp cận một kênh đã đăng ký. Mẫu email phải giúp người nhận hiểu vì sao có thư, hành động nào đang được đề nghị, thời hạn sử dụng và cách xử lý nếu họ không khởi tạo yêu cầu.

Trong hệ thống hỗ trợ mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, cùng một câu “khôi phục tài khoản” có thể che giấu các mức quyền rất khác nhau. Một email xác minh địa chỉ chưa chứng minh đủ điều kiện để tắt MFA. Một thông báo tiếp nhận hồ sơ cũng chưa có nghĩa tài khoản đã được khôi phục. Nội dung mẫu phải phản ánh chính xác trạng thái và mục đích của quy trình.

Mẫu email còn là nơi dữ liệu từ dịch vụ khôi phục được chuyển sang tiêu đề thư, HTML, plain text và nhà cung cấp gửi. Nếu dùng dữ liệu sai nguồn hoặc escape sai ngữ cảnh, một mẫu có hình thức đẹp vẫn có thể đưa người dùng tới trang giả, làm lộ token hoặc gây hiểu nhầm về an toàn tài khoản.

Bài học tập trung vào thiết kế mẫu và hợp đồng dữ liệu của email khôi phục. Các ví dụ dùng domain `.test` và placeholder để minh họa; không chứa liên kết hoặc token thực tế.

### Mục tiêu học tập

- Xây nội dung email phù hợp với từng mục đích và trạng thái khôi phục.
- Tách dữ liệu đáng tin khỏi input mà người yêu cầu có thể kiểm soát.
- Tạo hai bản HTML và plain text nhất quán, đọc được và ít phụ thuộc tài nguyên ngoài.
- Bảo vệ bí mật khi render, gửi, retry và quan sát việc giao thư.
- Phân biệt gửi email, mở email, xác minh bằng chứng và hoàn tất khôi phục.

## 2. Hợp đồng nội dung của một email khôi phục

Người nhận cần trả lời được các câu hỏi sau mà không phải đoán:

| Câu hỏi | Nội dung cần có | Điều cần tránh |
| --- | --- | --- |
| Thư này liên quan dịch vụ nào? | Tên dịch vụ quen thuộc và danh tính người gửi ổn định. | Tên thương hiệu lấy từ request chưa kiểm tra. |
| Vì sao tôi nhận thư? | Mô tả ngắn mục đích, chẳng hạn yêu cầu đặt lại mật khẩu. | Khẳng định người nhận tự yêu cầu khi hệ thống chỉ biết có ai đó nhập identifier. |
| Tôi cần làm gì? | Một hành động chính với nhãn rõ nghĩa. | Nhiều nút cạnh tranh, quảng cáo hoặc yêu cầu trả lời kèm bí mật. |
| Hành động có giá trị đến khi nào? | Hạn dùng phản ánh đúng bản ghi token và múi giờ rõ ràng. | Tuyên bố thời gian không khớp token hoặc luôn tính lại từ lúc mở thư. |
| Nếu tôi không yêu cầu thì sao? | Hướng dẫn bỏ qua và đường hỗ trợ chính thức khi có dấu hiệu bất thường. | Đe dọa khóa tài khoản nếu không bấm hoặc khẳng định chắc chắn tài khoản an toàn. |
| Thư có thể chia sẻ không? | Nhắc không chia sẻ liên kết, mã và mật khẩu. | Đề nghị chuyển tiếp nguyên thư cho hỗ trợ. |

Một email khởi tạo không nên nói “Tài khoản đã được xác minh” hay “MFA đã được gỡ” nếu sự kiện nghiệp vụ mới chỉ là phát hành bằng chứng. Câu chữ không được đi trước quyền mà máy chủ thật sự cấp.

### 2.1. Tiêu đề và preheader

Tiêu đề nên ngắn, mô tả đúng mục đích và tránh dữ liệu nhạy cảm. Ví dụ:

```text
Hướng dẫn đặt lại mật khẩu Dịch vụ Mẫu
```

Không đặt token, OTP, email đầy đủ, số điện thoại, mã session hoặc chi tiết thiết bị nhạy cảm trong subject. Subject và đoạn xem trước có thể xuất hiện trên màn hình khóa, hộp thư chia sẻ hoặc hệ thống lưu trữ thông báo.

Preheader là phần văn bản xem trước mà nhiều email client hiển thị cạnh tiêu đề. Có thể dùng:

```text
Xác minh quyền truy cập email để tiếp tục yêu cầu đặt lại mật khẩu.
```

Không để phần xem trước vô tình lấy ngay URL chứa token ở đầu body. Tuy nhiên, preheader ẩn không bảo đảm mọi email client sẽ hiển thị cùng một đoạn. Toàn bộ email vẫn cần hạn chế dữ liệu cá nhân không cần thiết.

### 2.2. Chọn từ theo mức độ chắc chắn

Có thể viết “Chúng tôi nhận được một yêu cầu đặt lại mật khẩu”. Không nên mặc định viết “Bạn vừa yêu cầu” vì người khởi tạo có thể là người khác.

Cũng không viết “Bấm link để đăng nhập ngay” nếu link chỉ mở quy trình xác minh. Nhãn “Tiếp tục đặt lại mật khẩu” cho biết đích đến phù hợp hơn. Đối với mất MFA hoặc passkey, nhãn có thể là “Tiếp tục xác minh khôi phục”.

## 3. Chọn mẫu theo mục đích và trạng thái phía máy chủ

Không dùng một mẫu duy nhất rồi chèn một chuỗi mục đích tùy ý do client gửi. Máy chủ nên ánh xạ một tập giá trị nghiệp vụ hợp lệ sang các mẫu đã được duyệt:

| Sự kiện hoặc mục đích | Thông điệp chính | Hành động phù hợp |
| --- | --- | --- |
| Yêu cầu đặt lại mật khẩu | Có yêu cầu và cần xác minh để tiếp tục. | Mở quy trình đặt lại mật khẩu. |
| Bắt đầu khôi phục khi mất MFA | Cần thực hiện các bước xác minh theo chính sách. | Tiếp tục quy trình, chưa hứa gỡ MFA. |
| Khôi phục khi mất passkey hoặc thiết bị | Có yêu cầu khôi phục phương thức truy cập. | Xác minh và thực hiện bước được cho phép, chưa tự đăng ký yếu tố mới. |
| Hồ sơ đang chờ đánh giá | Hồ sơ đã được tiếp nhận hoặc đang chờ. | Xem hướng dẫn công khai hoặc trạng thái có kiểm soát quyền. |
| Hoàn tất thay đổi thông tin xác thực | Một thay đổi cụ thể đã hoàn tất. | Hướng dẫn kiểm tra an ninh nếu không nhận ra hoạt động. |

Email mang bằng chứng khôi phục và email thông báo sau thay đổi có thể dùng cùng hệ thống gửi, nhưng cần mẫu riêng. Thông báo hoàn tất thường không cần chứa token khôi phục mới.

Ngôn ngữ email không quyết định mức bảo đảm danh tính. Dù mẫu ghi đúng mục đích, endpoint nhận token vẫn phải kiểm tra tài khoản, tenant, purpose, hạn dùng và trạng thái. Không dựa vào tên mẫu hoặc một field trong URL để thay thế các kiểm tra đó.

## 4. Hợp đồng dữ liệu cho bộ render

Một model minh họa có thể được tổ chức như sau:

```text
RecoveryEmailModel
  templateId
  templateVersion
  locale
  serviceName
  purpose
  recipientAddress
  actionUrl
  expiresAt
  expiresAtText
  officialRecoveryUrl
  supportUrl
  correlationId
```

Mỗi trường phải có nguồn và quy tắc sử dụng rõ ràng:

| Trường | Nguồn phù hợp | Ràng buộc |
| --- | --- | --- |
| `templateId`, `templateVersion` | Ánh xạ nghiệp vụ do máy chủ kiểm soát. | Không dùng đường dẫn template do người yêu cầu cung cấp. |
| `locale` | Sở thích đã lưu hoặc lựa chọn thuộc danh sách hỗ trợ. | Không ghép trực tiếp locale vào đường dẫn file tùy ý. |
| `serviceName` | Cấu hình thương hiệu hoặc tenant đã xác minh. | Giới hạn độ dài, ký tự điều khiển và escape khi render. |
| `purpose` | Quy trình khôi phục đã tạo. | Chỉ dùng giá trị hợp lệ; không chèn mô tả tự do thành nội dung bảo mật. |
| `recipientAddress` | Kênh khôi phục hợp lệ gắn với tài khoản. | Không dùng một `sendTo` tùy ý để chuyển bằng chứng sang địa chỉ khác. |
| `actionUrl` | Bộ phát hành link với origin và route tin cậy. | HTTPS, đích được phép, đúng token và đúng quy trình. |
| `expiresAt` | Hạn dùng của token trong bản ghi phía máy chủ. | Không tính lại từ thời điểm render hoặc mở thư. |
| `expiresAtText` | Định dạng từ `expiresAt` với locale và múi giờ xác định. | Nêu rõ múi giờ; không lấy nguyên chuỗi từ request. |
| `officialRecoveryUrl`, `supportUrl` | Cấu hình URL công khai đã kiểm tra. | Không chứa token và không có chuyển hướng tùy ý. |
| `correlationId` | Mã vận hành không có quyền khôi phục. | Không dùng thay token; tránh đưa chi tiết nội bộ không cần thiết vào email. |

Việc dữ liệu nằm trong cơ sở dữ liệu không tự làm nó đáng tin ở mọi ngữ cảnh. Tên tenant hoặc tên hiển thị có thể do một quản trị viên nhập. Chúng vẫn cần được giới hạn và escape khi dùng trong nội dung hoặc header.

### 4.1. Dữ liệu tối thiểu thường tốt hơn cá nhân hóa quá mức

Mẫu có thể bắt đầu bằng “Xin chào,” thay vì tên tài khoản. Điều này giảm phụ thuộc vào dữ liệu hồ sơ và giảm khả năng chèn nội dung ngoài ý muốn.

Nếu sản phẩm cần hiển thị thời điểm yêu cầu, địa điểm gần đúng hoặc thiết bị, chỉ dùng tín hiệu đã xử lý và có giá trị hỗ trợ quyết định. Không xem User-Agent hay định vị IP là bằng chứng danh tính. Không đưa chuỗi User-Agent thô, vị trí quá chi tiết hoặc identifier không cần thiết vào thư.

Địa chỉ gửi tới, danh sách CC/BCC và địa chỉ Reply-To phải được xây bằng API thư có cấu trúc. Đừng ghép chuỗi header với input chưa kiểm tra; đặc biệt từ chối ký tự CR/LF trong các trường mà hợp đồng không cho phép xuống dòng.

## 5. Mẫu plain text tiếng Việt

Ví dụ sau dành cho yêu cầu đặt lại mật khẩu. Các placeholder là ký hiệu minh họa cho bộ template, không phải cú pháp bắt buộc của một thư viện cụ thể.

```text
Tiêu đề: Hướng dẫn đặt lại mật khẩu {{serviceName}}

Xin chào,

Chúng tôi nhận được một yêu cầu đặt lại mật khẩu cho tài khoản tại
{{serviceName}}.

Dùng liên kết dưới đây để xác minh quyền truy cập email và tiếp tục
các bước đặt lại mật khẩu:

{{actionUrl}}

Liên kết chỉ được sử dụng một lần và hết hạn lúc {{expiresAtText}}.
Nếu liên kết đã hết hạn, hãy tự mở trang khôi phục chính thức để bắt đầu
một yêu cầu mới:
{{officialRecoveryUrl}}

Nếu bạn không yêu cầu đặt lại mật khẩu, bạn có thể bỏ qua email này.
Nếu nhận nhiều yêu cầu bất thường, hãy tự truy cập dịch vụ để kiểm tra
an ninh tài khoản hoặc xem hướng dẫn tại:
{{supportUrl}}

Không chia sẻ liên kết này. Nhân viên hỗ trợ không yêu cầu bạn gửi
mật khẩu, mã xác thực hoặc toàn bộ liên kết khôi phục qua email.

Đội ngũ {{serviceName}}
```

Câu “chỉ được sử dụng một lần” chỉ phù hợp khi máy chủ thật sự thực hiện tiêu thụ bằng chứng nguyên tử. Nếu thiết kế đổi link thành một grant khôi phục có thời hạn, việc sử dụng một lần ở đây là đổi token thành grant; các bước tiếp theo có thể cần nhiều request trong phạm vi grant đó.

Không dùng câu “Bỏ qua email sẽ hủy mọi phiên khôi phục” trừ khi hệ thống có cơ chế tương ứng. Không hành động không đồng nghĩa với việc đã ghi nhận từ chối, thu hồi token hoặc kiểm tra an ninh.

Hạn dùng nên có dạng rõ ràng, chẳng hạn `14:30 ngày 23/11/2026 (UTC+07:00)` trong dữ liệu minh họa. Một chuỗi như “sau 15 phút” dễ trở nên sai khi email bị xếp hàng hoặc giao chậm. Nếu dùng thời lượng tương đối, cần nói rõ tính từ thời điểm phát hành và vẫn bảo đảm nhất quán với hạn dùng thực tế.

## 6. Mẫu HTML tương ứng

HTML nên có ít thành phần, chữ đọc được, một hành động chính và một đường hỗ trợ công khai. Không cần JavaScript, form, ảnh ngoài, font ngoài hay nội dung quảng cáo trong email khôi phục.

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hướng dẫn đặt lại mật khẩu</title>
</head>
<body style="margin:0; padding:0; background:#f3f4f6; color:#111827;">
  <div aria-hidden="true"
       style="display:none; max-height:0; overflow:hidden;">
    Xác minh quyền truy cập email để tiếp tục yêu cầu đặt lại mật khẩu.
  </div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:24px 16px;">
        <table role="presentation" cellpadding="0" cellspacing="0"
               style="width:100%; max-width:600px; background:#ffffff;">
          <tr>
            <td style="padding:28px; font-family:Arial,sans-serif;
                       font-size:16px; line-height:1.6;">
              <p style="margin:0 0 16px; font-weight:bold;">
                {{serviceName}}
              </p>
              <h1 style="margin:0 0 20px; font-size:24px; line-height:1.3;">
                Tiếp tục đặt lại mật khẩu
              </h1>
              <p>Xin chào,</p>
              <p>
                Chúng tôi nhận được một yêu cầu đặt lại mật khẩu
                cho tài khoản tại {{serviceName}}.
              </p>
              <p>
                Dùng liên kết dưới đây để xác minh quyền truy cập email
                và tiếp tục các bước đặt lại mật khẩu.
              </p>
              <p style="margin:24px 0;">
                <a href="{{actionUrl}}"
                   style="display:inline-block; padding:12px 20px;
                          background:#1e40af; color:#ffffff;
                          text-decoration:none; border-radius:6px;">
                  Tiếp tục đặt lại mật khẩu
                </a>
              </p>
              <p>
                Liên kết chỉ được sử dụng một lần và hết hạn lúc
                <strong>{{expiresAtText}}</strong>.
              </p>
              <p>Nếu nút không hoạt động, sao chép toàn bộ liên kết sau:</p>
              <p style="word-break:break-all;">
                <a href="{{actionUrl}}" style="color:#1e40af;">
                  {{actionUrl}}
                </a>
              </p>
              <p>
                Nếu liên kết đã hết hạn, hãy tự mở
                <a href="{{officialRecoveryUrl}}" style="color:#1e40af;">
                  trang khôi phục chính thức
                </a>
                để bắt đầu một yêu cầu mới.
              </p>
              <p>
                Nếu bạn không yêu cầu đặt lại mật khẩu, bạn có thể bỏ qua
                email này. Nếu nhận nhiều yêu cầu bất thường, hãy tự truy cập
                dịch vụ để kiểm tra an ninh tài khoản hoặc xem
                <a href="{{supportUrl}}" style="color:#1e40af;">
                  hướng dẫn hỗ trợ an ninh
                </a>.
              </p>
              <p>
                Không chia sẻ liên kết này. Nhân viên hỗ trợ không yêu cầu
                bạn gửi mật khẩu, mã xác thực hoặc toàn bộ liên kết
                khôi phục qua email.
              </p>
              <p style="margin:24px 0 0;">Đội ngũ {{serviceName}}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

Nút bấm là một thẻ liên kết thông thường để vẫn hoạt động khi email client không hỗ trợ một số CSS. Văn bản của nút nói rõ hành động; người dùng không cần phân biệt chỉ bằng màu sắc. Các bảng có `role="presentation"` phục vụ bố cục, không diễn đạt dữ liệu dạng bảng cho công cụ hỗ trợ.

Không cần logo tải từ server ngoài để biết phải làm gì. Nếu dùng logo, nội dung và nút vẫn phải đọc được khi ảnh bị chặn; ảnh có mô tả thay thế phù hợp và không được dùng làm pixel theo dõi.

Bản HTML và plain text phải dùng cùng token, cùng mục đích, cùng thời hạn và cùng đích hỗ trợ. Đây là hai biểu diễn của một email, không phải hai yêu cầu khôi phục riêng.

## 7. Escape dữ liệu và kiểm tra URL trước khi render

### 7.1. Escape không thay thế xác minh ý nghĩa

`actionUrl` phải được tạo từ origin và route tin cậy. Sau khi kiểm tra ý nghĩa và cấu trúc URL, bộ render còn phải escape khi đặt vào thuộc tính HTML.

Nếu chỉ HTML-escape một URL `javascript:...` hoặc một link tới domain không được phép, thuộc tính có thể đúng cú pháp nhưng vẫn không an toàn. Ngược lại, URL đúng đích vẫn có thể phá cấu trúc HTML nếu dữ liệu được chèn sai ngữ cảnh.

| Ngữ cảnh | Xử lý cần có |
| --- | --- |
| Giá trị query của link | Encode theo thành phần URI khi phát hành link. |
| Thuộc tính `href` | URL đã được kiểm tra, sau đó escape thuộc tính HTML. |
| Văn bản HTML | Escape HTML cho dữ liệu động. |
| Body plain text | Không dùng entity HTML; kiểm soát ký tự điều khiển và bố cục. |
| Subject, From, Reply-To | Dùng API MIME/header, kiểm tra dữ liệu và không cho chèn CR/LF. |

Trong HTML, dấu phân cách query `&` được biểu diễn thành `&amp;` khi nằm trong mã thuộc tính. Trong plain text, URL vẫn dùng `&`. Không dùng lại chuỗi đã escape HTML làm URL gốc hoặc body plain text.

Không bật tính năng render HTML thô cho tên người dùng, tên tenant hoặc thông điệp do người gửi nhập. Mẫu email bảo mật không nên nhận một field `customHtml` không có kiểm soát. Bản dịch cũng cần qua quy trình kiểm soát nội dung, đặc biệt các vị trí có link và markup.

### 7.2. Model thiếu dữ liệu phải dừng trước khi gửi

Nếu thiếu token, URL không đúng đích, purpose không khớp mẫu hoặc hạn dùng không hợp lệ, không gửi một email “gần đúng”. Dừng công việc gửi và ghi lỗi vận hành đã che dữ liệu nhạy cảm.

Một nút có `href=""`, placeholder chưa thay hoặc link về trang chủ có thể làm người dùng thử lại liên tục, tạo thêm tải và tăng nguy cơ họ tin một email giả xuất hiện sau đó.

Không đưa toàn bộ model vào thông báo lỗi. Nhiều cơ chế log tự động của đối tượng dữ liệu có thể in cả `actionUrl` và `recipientAddress`. Chỉ ghi tên trường lỗi, mã template, phiên bản và mã tương quan không có quyền khôi phục.

## 8. Ngôn ngữ, thời gian và khả năng tiếp cận

### 8.1. Chọn locale có kiểm soát

Locale có thể đến từ tùy chọn tài khoản hoặc một lựa chọn hợp lệ trong yêu cầu, tùy chính sách. Không cho locale quyết định origin, tenant hay mục đích khôi phục. Nếu không có bản dịch phù hợp, dùng bản dự phòng đã được duyệt cho cùng mục đích.

Không fallback từ email mất MFA sang một mẫu “đăng nhập bằng link” chỉ vì mẫu đó có sẵn. Một bản dịch thiếu phải được xử lý như vấn đề nội dung hoặc cấu hình, không làm thay đổi ý nghĩa bảo mật.

Tên hành động, hạn dùng và hướng dẫn khi không yêu cầu cần nhất quán giữa các ngôn ngữ. Tránh dịch bằng cách nối nhiều mảnh câu nếu điều đó làm nhầm chủ thể hoặc thời điểm hết hạn.

### 8.2. Hạn dùng phải dựa trên cùng một thời điểm

Lưu thời điểm chuẩn trong dữ liệu nghiệp vụ, rồi định dạng thành chuỗi hiển thị với múi giờ rõ ràng. Không dựa vào múi giờ mặc định của một worker vì các worker có thể chạy ở vùng khác nhau.

Nếu email nằm trong hàng đợi lâu đến mức token đã hết hạn, worker không tự gia hạn token hoặc sửa dòng thời gian để email trông còn mới. Nó cần áp dụng chính sách bỏ qua, hủy hoặc yêu cầu phát hành lại bằng chứng theo một thao tác được kiểm soát.

Một email gửi thành công ở phút cuối vẫn có thể đến sau hạn. Hướng dẫn bắt đầu yêu cầu mới qua trang chính thức giúp người dùng xử lý tình huống đó mà không gửi token cho hỗ trợ.

### 8.3. Thiết kế khi HTML hoặc CSS bị hạn chế

Email cần đọc được trên màn hình nhỏ, khi ảnh bị chặn và khi một phần CSS không được áp dụng. Dùng văn bản thật, kích thước chữ hợp lý và liên kết có nhãn mô tả. Bản plain text là đường tiếp cận bổ sung, không phải một dòng “hãy mở bản HTML”.

Dark mode, cách email client đổi màu và cơ chế bảo vệ link có thể làm nội dung hiển thị khác nhau. Cần kiểm chứng trên các client mà sản phẩm hỗ trợ trước khi phát hành; một đoạn HTML có cú pháp đúng chưa bảo đảm giao diện nhất quán ở mọi nơi.

## 9. Gửi thư và vận hành không được làm đổi ý nghĩa của mẫu

### 9.1. Một thông điệp, hai biểu diễn MIME

Email có thể dùng cấu trúc:

```text
multipart/alternative
  text/plain; charset=UTF-8
  text/html; charset=UTF-8
```

Dùng thư viện gửi email để xử lý MIME, mã hóa Unicode, địa chỉ và header. Không tự ghép dữ liệu thô thành toàn bộ thư bằng phép nối chuỗi.

Danh tính From nên ổn định, đến từ domain do dịch vụ kiểm soát. Reply-To cần phản ánh đúng cách hỗ trợ vận hành; không dùng địa chỉ do người khởi tạo nhập. Có thể nêu rõ hộp thư không nhận phản hồi nếu đúng thực tế và cung cấp kênh hỗ trợ chính thức.

Các cơ chế xác thực domain gửi như SPF, DKIM và DMARC góp phần chống giả mạo và hỗ trợ giao thư theo cấu hình của hệ thống email. Chúng không chứng minh người nhận đã yêu cầu khôi phục, cũng không sửa được một `actionUrl` bị ghép sai domain trong mẫu.

### 9.2. Không đo mức thành công bằng việc mở email

Pixel mở thư và hệ thống click tracking có thể làm lộ thêm dữ liệu hoặc đưa token qua bên trung gian. Nên tránh chúng trong email chứa bằng chứng khôi phục, đồng thời kiểm tra cả cấu hình mặc định của nhà cung cấp.

Các trạng thái cần tách biệt:

| Tín hiệu | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| Nhà cung cấp chấp nhận gửi | Công việc đã được nhà cung cấp tiếp nhận. | Email đã vào hộp thư hoặc người dùng đã đọc. |
| Có sự kiện giao thư | Có tín hiệu giao theo ngữ nghĩa của nhà cung cấp. | Người nhận đã xác minh danh tính. |
| Có GET vào link | Một tác nhân đã mở URL. | Chủ tài khoản bấm; trình quét cũng có thể mở. |
| Token được đổi thành grant hợp lệ | Bằng chứng được hệ thống chấp nhận theo chính sách của bước đó. | Mọi bước khôi phục đã hoàn tất. |
| Chuyển trạng thái khôi phục hoàn tất | Các điều kiện nghiệp vụ cuối đã được đáp ứng. | Mọi session cũ đã bị thu hồi nếu chưa thực hiện chính sách session. |

Mẫu email không nên có link GET thực hiện thay đổi thông tin xác thực ngay khi mở. Một trang tiếp nhận có thể yêu cầu bước xác nhận chủ động và bảo vệ request thay đổi trạng thái; nội dung nút cần mô tả đúng trải nghiệm đó.

### 9.3. Retry và phiên bản mẫu

Một lệnh gửi có thể gắn với `eventId`, `templateId`, `templateVersion`, locale, recipient đã xác định và bằng chứng đã phát hành. Retry cùng sự kiện giữ nguyên token và ý nghĩa; không tự sinh một bằng chứng mới mỗi lần render lại.

Để tránh một retry dùng nội dung mới không tương thích, có thể ghim phiên bản mẫu cho sự kiện hoặc lưu bản render đã mã hóa với quyền truy cập và thời gian lưu phù hợp. Cả hai cách cần cân bằng việc tái lập nội dung với rủi ro lưu bản sao token.

Gửi một lần trong nghiệp vụ không bảo đảm nhà cung cấp chỉ giao một email khi có timeout giữa hai hệ thống. Dedupe theo event ID và khả năng của nhà cung cấp cần được thiết kế riêng. Template không giải quyết được khoảng trống này, nhưng phải tránh hứa rằng người dùng sẽ chỉ nhận đúng một thư trong mọi tình huống.

Nếu có bounce hoặc địa chỉ bị suppression, không tự chuyển thư chứa token sang một địa chỉ mới do người yêu cầu cung cấp. Thay đổi kênh khôi phục là một quyết định an ninh cần quy trình xác minh riêng.

## 10. Các lỗi nội dung làm tăng rủi ro

| Lỗi trong mẫu hoặc bộ render | Hệ quả | Cách xử lý phù hợp |
| --- | --- | --- |
| Dùng subject “Tài khoản sắp bị xóa, bấm ngay” cho yêu cầu khôi phục thông thường | Tạo áp lực và huấn luyện người dùng làm theo email đe dọa. | Tiêu đề đúng sự kiện và hướng dẫn bình tĩnh, cụ thể. |
| Đặt token hoặc mã xác thực trong preheader | Lộ bí mật qua phần xem trước và thông báo. | Chỉ mô tả mục đích trong phần xem trước. |
| Nhãn nút hiển thị domain chính thức nhưng href tới đích khác | Người dùng khó nhận biết đường đi thật. | Dùng URL từ cấu hình tin cậy và kiểm tra bản render. |
| Đề nghị gửi mật khẩu hoặc chuyển tiếp nguyên thư cho hỗ trợ | Biến hỗ trợ thành nơi tập trung bí mật. | Hướng dẫn hỗ trợ qua mã tương quan không có quyền khôi phục. |
| Dùng tên hoặc mô tả do người yêu cầu nhập làm HTML thô | Có thể chèn link hoặc nội dung giả vào email. | Giới hạn dữ liệu và escape theo ngữ cảnh. |
| Ghi “MFA đã bị gỡ” khi mới bắt đầu xét duyệt | Gây hiểu nhầm trạng thái và quyền tài khoản. | Chọn mẫu dựa trên chuyển trạng thái đã được ghi nhận. |
| Tạo hạn dùng mới khi retry gửi | Nội dung và token không còn nhất quán. | Định dạng lại từ đúng `expiresAt` đã lưu. |
| Bật click tracking trên link chứa token | Bí mật đi qua dịch vụ theo dõi và log của họ. | Tắt theo dõi cho thư bảo mật và kiểm tra luồng gửi thực tế. |
| Ghi toàn bộ model khi render lỗi | Lộ link và recipient trong log vận hành. | Chỉ ghi dữ liệu chẩn đoán đã giới hạn và che bí mật. |

Không nên thêm link “Không phải tôi” có khả năng khóa tài khoản hoặc hủy mọi phiên chỉ bằng GET. Nếu sản phẩm cần cơ chế báo cáo hoặc từ chối, hành động đó cần thiết kế quyền, xác nhận và tác động riêng; một nút trong template không đủ để làm quyết định đó an toàn.

## 11. Tình huống minh họa xuyên suốt

Giả sử người dùng mất mật khẩu gửi yêu cầu lúc 14:00. Máy chủ tạo token hết hạn lúc 14:15, ghi sự kiện gửi và chọn mẫu `recovery.password.start` phiên bản đã duyệt.

1. Bộ render nhận recipient từ kênh khôi phục của tài khoản, không từ một trường `sendTo` của request.
2. `actionUrl` được tạo từ recovery origin đã cấu hình; hai bản email cùng dùng URL đó.
3. `expiresAtText` hiển thị đúng thời điểm 14:15 với múi giờ đã chọn, không phải 15 phút sau lúc worker chạy.
4. Mẫu mô tả yêu cầu đặt lại mật khẩu và việc xác minh email; nó không tuyên bố mật khẩu đã đổi.
5. Worker gửi lúc 14:02, nhà cung cấp quét GET link trước người dùng; việc quét không được làm token bị tiêu thụ.
6. Người dùng mở thư lúc 14:05 và thực hiện các bước xác nhận theo chính sách; máy chủ quyết định quyền dựa trên token và quy trình.
7. Sau khi đổi mật khẩu thành công, hệ thống có thể gửi một thông báo hoàn tất riêng và thực hiện chính sách session. Không dùng lại email khởi tạo như bằng chứng rằng các bước đó đã xảy ra.

Nếu worker chỉ bắt đầu lúc 14:20, mẫu không được sửa thành “hết hạn lúc 14:35”. Hệ thống xử lý bằng chứng hết hạn theo chính sách vận hành; việc render không có quyền gia hạn.

Nếu người nhận không khởi tạo yêu cầu, hướng dẫn bỏ qua không làm hệ thống tự coi họ đã xác nhận từ chối. Token sẽ hết hạn hoặc bị thu hồi theo cơ chế thật sự được thiết kế, và các yêu cầu bất thường vẫn cần kiểm soát chống lạm dụng ở phía máy chủ.

## 12. Các điều cần kiểm chứng trước khi phát hành mẫu

Những tình huống sau giúp đánh giá mẫu trong hệ thống thực thi:

- Render mọi purpose và locale được hỗ trợ; đối chiếu subject, nhãn nút, trạng thái và hạn dùng ở cả HTML lẫn plain text.
- Thử tên thương hiệu chứa ký tự HTML, chuỗi dài và ký tự điều khiển; bảo đảm chúng không tạo markup hoặc header ngoài ý muốn.
- Thử URL sai scheme, sai domain, thiếu token và placeholder chưa thay; công việc gửi phải bị chặn trước khi gọi nhà cung cấp.
- Thử thời điểm gần hết hạn, hàng đợi chậm và retry; thông điệp không tự cấp lại hoặc gia hạn bằng chứng.
- Mở thư khi ảnh bị chặn, trên màn hình nhỏ, với trình đọc màn hình và các client được sản phẩm hỗ trợ.
- Kiểm tra bản thư sau khi nhà cung cấp xử lý để phát hiện tracking, URL rewriting hoặc footer tự chèn làm thay đổi luồng bí mật.
- Tìm token giả được dùng cho kiểm chứng trong log, APM, sự kiện phân tích và bản chẩn đoán; không dùng token thật của người dùng cho việc này.
- Mô phỏng GET của trình quét và xác nhận rằng email không dẫn tới thao tác nhạy cảm chỉ bằng một lượt mở link.
- Đối chiếu sự kiện hoàn tất khôi phục với việc gửi thông báo và xử lý session; không dùng trạng thái gửi thư làm bằng chứng hoàn tất.

Các mục trên là yêu cầu kiểm chứng khi triển khai, không phải kết quả thử nghiệm đã được thực hiện cho một hệ thống cụ thể. Một recovery email template tốt giữ đúng ý nghĩa của quy trình, hướng dẫn người dùng rõ ràng và mang ít dữ liệu nhạy cảm nhất cần thiết để thực hiện bước khôi phục được phép.