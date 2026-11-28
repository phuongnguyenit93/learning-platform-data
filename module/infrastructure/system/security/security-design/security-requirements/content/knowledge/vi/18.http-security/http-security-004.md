# HSTS

## 1. Chuyển hướng HTTPS chưa phải toàn bộ yêu cầu bảo mật

Một ứng dụng chỉ xử lý đăng nhập qua HTTPS vẫn có thể được người dùng mở bằng một liên kết HTTP cũ. Nếu trình duyệt phải gửi request HTTP rồi mới nhận chuyển hướng, đoạn trao đổi đầu tiên chưa được bảo vệ bởi TLS.

Trong thiết kế yêu cầu bảo mật, cần phân biệt hai mục tiêu:

- Máy chủ cung cấp và ưu tiên HTTPS.
- Client phù hợp không gửi HTTP tới một host đã được xác định phải dùng HTTPS.

HSTS, viết tắt của **HTTP Strict Transport Security**, phục vụ mục tiêu thứ hai bằng một chính sách mà user agent hỗ trợ có thể ghi nhớ và thực thi. Vì có trạng thái ở client, triển khai HSTS không chỉ là thêm một dòng header rồi kiểm tra trang chủ.

Bài học tập trung chuyển mục tiêu “duy trì kết nối HTTPS cho người dùng” thành phạm vi áp dụng, yêu cầu cấu hình, điều kiện vận hành và bằng chứng kiểm chứng. Ví dụ dùng các domain thuộc `example.test` để minh họa; chúng không đại diện một dịch vụ đã được cấu hình thực tế.

## 2. Cơ chế cốt lõi

HSTS được khai báo bằng response header `Strict-Transport-Security` qua kết nối HTTPS hợp lệ. Với host đã biết chính sách, user agent phù hợp đổi URL HTTP sang HTTPS trước khi tải và không cho bỏ qua lỗi thiết lập kết nối bảo mật. `max-age` tính bằng giây; `includeSubDomains` mở rộng phạm vi xuống các domain con. HSTS áp dụng theo host, không theo từng đường dẫn. Header trên HTTP thường không thiết lập chính sách; thẻ HTML meta cũng không thay được header này. Đây là cơ chế được mô tả trong [RFC 6797](https://www.rfc-editor.org/rfc/rfc6797).

Ví dụ một response HTTPS:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Strict-Transport-Security: max-age=31536000
```

Giá trị `31536000` tương ứng 365 ngày. Nó là một lựa chọn thời hạn trong ví dụ, không phải giá trị bắt buộc cho mọi lần triển khai HSTS.

Từ cơ chế này, một yêu cầu của dự án có thể là:

> Các host thuộc danh mục HTTPS-only phải phát chính sách HSTS đã được phê duyệt tại điểm phục vụ HTTPS cho client. Phạm vi, thời hạn, lớp sở hữu và điều kiện phục hồi phải được xác định cho từng host hoặc nhóm host.

Yêu cầu này vẫn cần được làm rõ bằng những phần tiếp theo; chỉ nêu “bật HSTS” chưa đủ để nghiệm thu.

## 3. Đe dọa mà thiết kế cần xử lý

HSTS hỗ trợ giảm rủi ro từ truy cập HTTP không chủ ý và hành vi bỏ qua cảnh báo chứng thư, nhưng không thay các kiểm soát ứng dụng. Phần mô hình đe dọa của [OWASP HSTS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html) phân biệt những tình huống này.

Trong một hệ thống giả định có trang đăng nhập, API và trang hỗ trợ, nhóm có thể lập bảng phân tích riêng:

| Tình huống trong hệ thống | Rủi ro cần đánh giá | Quyết định thiết kế cần có |
| --- | --- | --- |
| Người dùng mở bookmark HTTP | Có một đường truy cập không dùng TLS trước khi tới ứng dụng | Chính sách client, liên kết chuẩn và hành vi HTTP của server |
| Một email cũ chứa URL HTTP | Người dùng tiếp tục đi vào đường cũ dù ứng dụng đã đổi cấu hình | Kiểm kê nguồn phát liên kết và kế hoạch tương thích |
| Trang lỗi có cấu hình header khác | Người dùng chỉ nhận chính sách khi vào một số đường thành công | Phạm vi response và lớp phát header |
| Chứng thư hết hạn | Người dùng không thể kết nối theo chính sách bảo mật | Theo dõi chứng thư và quy trình phục hồi HTTPS |
| Subdomain do đối tác quản lý | Thay đổi ở domain cha tác động dịch vụ ngoài đội triển khai | Kiểm kê ownership, khả năng TLS và nghĩa vụ vận hành |
| Client là SDK tự viết | Không có cơ sở cho rằng client thực thi HSTS | Hợp đồng HTTPS và xác minh chứng thư của SDK |

Bảng này là phân tích áp dụng cho tình huống minh họa, không phải danh sách mọi đe dọa mà HSTS giải quyết. Khi đánh giá hệ thống thực, cần xác định đường truyền và loại client cụ thể.

## 4. Khai báo chính sách phải là một quyết định có chủ sở hữu

Một bản đặc tả nên tách những giá trị cấu hình khỏi mục tiêu bảo mật. Ví dụ:

```yaml
host: app.example.test
purpose: browser-facing application
httpsOnly: true
hsts:
  maxAgeSeconds: 86400
  includeSubDomains: false
  preload: false
owner: web-platform-team
```

Đây là ví dụ biểu diễn yêu cầu, không phải schema của một sản phẩm hay file cần được tạo trong dự án. Các giá trị chỉ minh họa một giai đoạn đã có giới hạn.

Những nội dung cần được quyết định gồm:

1. Host nào nằm trong phạm vi và ai có quyền thay chính sách.
2. Client nào phải được hỗ trợ và cách xác nhận khả năng thực thi.
3. Thời hạn hiện tại, thời hạn mục tiêu và điều kiện tăng thời hạn.
4. Có mở rộng xuống subdomain hay không, dựa trên danh mục nào.
5. Tầng nào chịu trách nhiệm phát một giá trị nhất quán cho client.
6. Các chỉ tiêu vận hành cần đạt trước khi thay đổi phạm vi.
7. Cách phục hồi khi chứng thư hoặc định tuyến HTTPS gặp lỗi.

Không dùng một giá trị mặc định của framework làm quyết định thay cho các mục này. Hai dịch vụ dùng cùng template vẫn có thể có cây domain và cam kết vận hành rất khác nhau.

### Phân biệt thời hạn chính sách với lịch thay chứng thư

Trong đặc tả vận hành, nên có hai dòng thời gian riêng: thời hạn mà client ghi nhớ chính sách và vòng đời chứng thư của host. Không coi việc chứng thư sắp hết hạn là một cách làm chính sách bảo mật tự mất hiệu lực.

Đội sở hữu cần xác định khả năng gia hạn, thay chứng thư và xử lý sự cố cho toàn bộ khoảng thời gian mà chính sách được dự kiến duy trì. Một cấu hình dài hạn nhưng không có owner chứng thư là một khoảng trống của yêu cầu khả dụng.

## 5. Phạm vi host và subdomain

Giả sử tổ chức có cấu trúc:

```text
example.test
├── app.example.test
│   └── preview.app.example.test
├── api.example.test
└── legacy.example.test
```

Một chính sách ở `app.example.test` không đồng nghĩa mọi nhánh dưới `example.test` đã được quản lý bởi chính sách ấy. `includeSubDomains` mở rộng xuống cây con của host phát hành, không lên domain cha hoặc sang một nhánh ngang hàng. Phạm vi này thuộc mô hình domain của [RFC 6797, mục 8.2](https://www.rfc-editor.org/rfc/rfc6797#section-8.2).

Đối với hệ thống giả định, bảng kiểm kê có thể như sau:

| Host | Chủ sở hữu | Chức năng | Điều kiện cần xác nhận trước khi đổi phạm vi |
| --- | --- | --- | --- |
| `example.test` | Đội nền tảng | Trang điều hướng | Khả năng duy trì HTTPS và các nhánh bị ảnh hưởng |
| `app.example.test` | Đội web | Ứng dụng người dùng | Luồng đăng nhập, callback và tài nguyên liên quan |
| `preview.app.example.test` | Đội phát triển | Môi trường xem trước | Quy trình cấp chứng thư, xóa môi trường và ownership |
| `api.example.test` | Đội API | API và tích hợp | Client trình duyệt, SDK và các endpoint thực tế |
| `legacy.example.test` | Đội dịch vụ cũ | Chức năng đang chuyển đổi | Khả năng TLS, phụ thuộc và phương án chuyển đổi |

Danh mục không nên chỉ lấy từ những trang mà đội hiện tại nhớ. Có thể cần kết hợp quản lý DNS, hạ tầng, danh mục ứng dụng, hợp đồng đối tác và thông tin môi trường nội bộ theo quyền truy cập của tổ chức.

### Domain do bên thứ ba phục vụ

Một tên miền do tổ chức quản lý có thể trỏ tới hạ tầng của nhà cung cấp. Yêu cầu cần xác định nhà cung cấp có duy trì HTTPS cho tên đó, hỗ trợ đổi chứng thư và có cam kết khôi phục phù hợp hay không.

Việc một CNAME tồn tại không tự trả lời các câu hỏi vận hành. Đối với môi trường ngắn hạn hoặc dịch vụ sắp ngừng, cần làm rõ ai chịu trách nhiệm trong suốt vòng đời tên miền và chính sách đã phát.

### Không thiết kế ngoại lệ theo URL path

Không nên mô tả một host “chỉ bật HSTS cho `/login` nhưng giữ HTTP cho `/legacy`” như hai vùng độc lập. Nếu có nhu cầu tương thích khác nhau, nhóm phải xem lại cấu trúc host và mục tiêu HTTPS; cấu hình theo route không thay đổi bản chất phạm vi host.

## 6. Trạng thái ở trình duyệt và ý nghĩa của việc thay đổi header

Theo [MDN về Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security), mỗi lần nhận chính sách hợp lệ sẽ cập nhật hạn theo `max-age`. Bỏ header không xóa chính sách đã lưu. `max-age=0` chỉ có tác dụng khi client nhận qua HTTPS và không xóa các bản ghi HSTS độc lập của subdomain. HSTS dựa vào domain, không phải IP literal; khi nâng URL, port 80 chuyển thành 443, còn port được ghi rõ khác 80 giữ nguyên.

Những chi tiết này dẫn tới một yêu cầu quản lý thay đổi quan trọng: kiểm tra cấu hình server hiện tại và kiểm tra trạng thái của client là hai công việc khác nhau.

Ví dụ đội triển khai rút thời hạn từ một năm xuống một giờ. Không nên ghi nhận rằng mọi client đã có thời hạn mới ngay tại thời điểm deploy. Cần phân biệt client đã nhận cấu hình mới với client chưa quay lại dịch vụ.

Một kế hoạch nghiệm thu nên có các nhóm trạng thái:

| Nhóm client kiểm thử | Mục đích |
| --- | --- |
| Chưa có trạng thái HSTS của host trong điều kiện thử | Quan sát hành vi ban đầu theo môi trường đã mô tả |
| Đã học chính sách đang triển khai | Quan sát việc thực thi chính sách dự kiến |
| Đã học chính sách cũ | Đánh giá tương thích và phạm vi phục hồi khi thay đổi |
| Đã học chính sách ở domain cha hoặc subdomain | Kiểm tra các trạng thái liên quan theo mô hình domain |
| Có chính sách được cài sẵn theo danh sách của trình duyệt | Phân biệt với trạng thái chỉ học từ response |

Đây là thiết kế tập kiểm chứng cho dự án. Việc mở một cửa sổ riêng tư không nên được dùng làm định nghĩa duy nhất cho “client sạch”; cần xác định hồ sơ trình duyệt, chính sách quản trị và cơ chế nâng cấp HTTPS đang tham gia.

## 7. Lần truy cập đầu và quyết định preload

HSTS học từ response không tự bảo đảm client đã biết chính sách trước lần kết nối đầu. Preload là một cơ chế phân phối danh sách host cho trình duyệt, không phải kết quả tự động của việc thêm chữ `preload` vào header. Tại thời điểm đối chiếu 27/11/2026, trang chương trình nhấn mạnh lợi ích của HSTS nhưng không khuyến nghị preload như lựa chọn mặc định; việc gỡ khỏi danh sách có độ trễ. Nếu cân nhắc tham gia, phải đối chiếu điều kiện hiện hành và tác động dài hạn tại [HSTS Preload](https://hstspreload.org/).

Ví dụ cú pháp có thể xuất hiện trong một cấu hình được quyết định riêng:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

Không sao chép ví dụ này vào một cấu hình dùng chung chỉ để một công cụ chấm điểm hiện đủ chỉ thị. Tổ chức cần xác định lợi ích cần đạt, phạm vi domain và khả năng duy trì cam kết trước khi chọn cơ chế phân phối chính sách đó.

Trong yêu cầu của dự án, nên tách riêng:

- Gate triển khai HSTS động cho host mục tiêu.
- Gate mở rộng phạm vi domain.
- Quyết định có tham gia một danh sách preload hay không.

Ba quyết định có thể có điều kiện hoàn thành khác nhau. Không dùng một cờ cấu hình để thay cho bằng chứng rằng một trình duyệt cụ thể đã có chính sách trong danh sách được phân phối tới nó.

Các trình duyệt có thể có cơ chế ưu tiên hoặc tự nâng HTTPS khác. Khi kiểm chứng mục tiêu bảo vệ, cần ghi nhận cơ chế thực sự tác động đến kết quả, thay vì suy luận mọi lần nâng HTTPS đều do HSTS của ứng dụng.

## 8. HSTS không thay thế các ranh giới bảo mật khác

Trong thiết kế hệ thống, cần gắn HSTS vào mục tiêu cụ thể để tránh kết luận quá mức từ một header đúng.

| Kiểm soát | Trách nhiệm riêng trong thiết kế |
| --- | --- |
| Cấu hình TLS và chứng thư | Đảm bảo kết nối HTTPS thực sự được xác minh và bảo vệ phù hợp |
| Cookie Secure | Quy định cách cookie được gửi theo ngữ cảnh truyền tải |
| HttpOnly và SameSite | Giải quyết các khía cạnh truy cập cookie và request trong trình duyệt |
| Xác thực và phân quyền | Xác định ai gọi và được phép làm gì |
| CSP và xử lý nội dung | Kiểm soát những rủi ro liên quan nội dung được tải hoặc thực thi |
| Quản lý URL và liên kết | Tránh tiếp tục phát hành những đường dẫn không phù hợp chính sách |
| Bảo vệ edge–backend | Giữ yêu cầu bảo mật cho các chặng phía sau điểm kết thúc TLS |

Ví dụ, một API trả HSTS nhưng cho phép xem đơn hàng của người khác vẫn có lỗi phân quyền. Một ứng dụng có XSS không thể lấy header HSTS làm bằng chứng rằng dữ liệu trong trình duyệt đã an toàn.

Không suy từ việc tên host được bảo vệ sang việc toàn bộ tên miền, mọi client hoặc mọi chặng mạng đều đã được bảo vệ tương đương. Mỗi kết luận cần có phạm vi và bằng chứng riêng.

## 9. Chọn nơi phát header trong kiến trúc nhiều tầng

Một luồng thực tế có thể là:

```text
Trình duyệt
    → CDN hoặc dịch vụ biên
    → load balancer / reverse proxy
    → ứng dụng
```

Ứng dụng có thể tạo header nhưng tầng ngoài ghi đè hoặc loại bỏ. Ngược lại, dịch vụ biên có thể tự tạo response lỗi mà ứng dụng không được xử lý.

Yêu cầu cần chỉ rõ **ai sở hữu giá trị cuối cùng mà client nhìn thấy**. Không đủ để mỗi đội đều khai báo rằng họ đã thêm header ở phần của mình.

Một mô hình ownership của dự án có thể là:

| Thành phần | Trách nhiệm được giao |
| --- | --- |
| Đội nền tảng | Quản lý giá trị chính sách đã phê duyệt và cấu hình phân phối |
| Đội ứng dụng | Kiểm kê host, route và luồng nghiệp vụ cần tương thích |
| Đội chứng thư/TLS | Theo dõi gia hạn, trust chain và khả năng khôi phục |
| Đội vận hành biên | Giữ header nhất quán ở response do biên tạo ra |
| Đội kiểm thử | Thu bằng chứng từ đường gọi cuối cùng và trạng thái client được định nghĩa |

Nếu client được kết nối qua HTTPS nhưng backend nhận HTTP sau proxy, cần dựa trên mô hình proxy tin cậy khi quyết định chính sách tại tầng ứng dụng. Không mặc định tin một header tự khai từ Internet để xác định trạng thái kết nối ban đầu.

HSTS dành cho tương tác của client với host không phải bằng chứng rằng chặng nội bộ đã dùng TLS. Nếu chặng nội bộ cần mã hóa hoặc xác thực dịch vụ, đặc tả riêng phải mô tả điều đó.

## 10. Ví dụ cấu hình và những điều không thể suy ra từ nó

Với Nginx, một dòng cấu hình minh họa trong ngữ cảnh phục vụ HTTPS là:

```nginx
add_header Strict-Transport-Security "max-age=300" always;
```

Theo [tài liệu ngx_http_headers_module](https://nginx.org/en/docs/http/ngx_http_headers_module.html), `always` làm việc thêm header không bị giới hạn bởi nhóm status mặc định của directive. Việc kế thừa `add_header` giữa các mức cấu hình cũng cần được xét theo phiên bản và cấu hình đang dùng.

Đây không phải một cấu hình TLS hoàn chỉnh. Nó chưa mô tả chứng thư, virtual host, CDN, các nhánh location hoặc giá trị mục tiêu của hệ thống.

Những điều phải kiểm tra thêm trong triển khai giả định:

1. Dòng cấu hình có thực sự áp dụng cho host client truy cập không.
2. Một location riêng có làm đầu ra khác với dự kiến không.
3. Proxy khác có thêm một giá trị mâu thuẫn không.
4. Response cache hoặc trang lỗi ở tầng biên có cùng chính sách không.
5. Route chuyển hướng HTTPS sang host khác có phát chính sách cho đúng host của response không.

Một giá trị hiệu lực nhất quán nên là tiêu chí đầu ra của dự án. Không dựa vào giả định mọi client xử lý các header trùng hoặc giá trị ghép mâu thuẫn giống nhau.

### Không dùng nội dung request để tạo phạm vi tùy ý

Chính sách nên lấy từ cấu hình có kiểm soát của host. Không để query parameter hoặc một header do client tự gửi quyết định `max-age` hay việc mở rộng domain trong response bình thường.

Nếu có cơ chế canary theo một nhóm client được quản lý, thiết kế phải giải thích cách phân phối, cách đo lường và giới hạn của phép thử. Nó không nên trở thành một đường mà bên gọi tùy ý làm giảm chính sách cho người dùng khác qua cache.

## 11. Kế hoạch triển khai theo gate

Một kế hoạch triển khai minh họa có thể chia thành các gate sau. Đây là phương án phân rã công việc của dự án, không phải một lịch bắt buộc của giao thức.

### Gate A — Đủ điều kiện HTTPS

- Mỗi host mục tiêu có chủ sở hữu và đường phục vụ HTTPS xác định.
- Chứng thư phù hợp với hostname và tập client cần hỗ trợ.
- Những luồng quan trọng đã được kiểm tra qua HTTPS.
- Có khả năng giám sát và xử lý sự cố gia hạn.
- Có danh mục dependency về domain, callback và dịch vụ bên ngoài.

### Gate B — Phát chính sách ban đầu

- Xác định giá trị thời hạn ngắn phù hợp cho giai đoạn đánh giá.
- Xác định phạm vi response cần có header và cách lấy bằng chứng.
- Theo dõi lỗi kết nối, tỷ lệ đăng nhập và các chỉ số nghiệp vụ liên quan.
- Không mở rộng subdomain ngoài phạm vi đã kiểm kê.

### Gate C — Tăng thời hạn hoặc phạm vi

- Có dữ liệu vận hành đủ đại diện cho các host và luồng trong phạm vi.
- Đã đánh giá client giữ chính sách cũ và client nhận chính sách mới.
- Các owner xác nhận có thể duy trì HTTPS cho phạm vi mục tiêu.
- Kế hoạch phục hồi đã được diễn tập trong môi trường phù hợp.

### Gate D — Duy trì và quản lý thay đổi

- Host mới phải được đánh giá trước khi đưa vào cây domain liên quan.
- Thay đổi CDN, proxy hoặc cấu hình error page có kiểm tra hồi quy.
- Gia hạn chứng thư và bàn giao ownership có người chịu trách nhiệm.
- Việc ngừng một dịch vụ xét cả tên miền và trạng thái chính sách còn ở client.

Ví dụ một giai đoạn dùng `max-age=300` chỉ cho thấy đội đang chọn thời hạn năm phút. Nó không tự chứng minh đã đủ an toàn để chuyển sang thời hạn dài. Tiêu chí tăng phải dựa trên bằng chứng đã định, không chỉ vì header tồn tại trong một lần gọi.

## 12. Phục hồi phải ưu tiên khôi phục HTTPS đúng

Hãy xét một sự cố: ứng dụng vẫn chạy nhưng một nhóm client không thiết lập được TLS sau khi đổi chứng thư. Một kế hoạch “tạm phục vụ HTTP để người dùng vào lại” không phải phương án phục hồi phù hợp cho mục tiêu HTTPS-only.

Trong thiết kế vận hành, nên mô tả các lựa chọn trong phạm vi đã chuẩn bị:

- Khôi phục chứng thư hoặc trust chain đúng cho hostname.
- Khôi phục cấu hình TLS hoặc route ở điểm phục vụ client.
- Chuyển lưu lượng tới hạ tầng dự phòng vẫn đáp ứng cùng danh tính HTTPS.
- Đối chiếu những thay đổi chính sách đã phát và nhóm client bị ảnh hưởng.
- Thực hiện quy trình thay đổi chính sách nếu có cơ sở và kênh cập nhật hợp lệ.

Đừng đồng nhất thao tác rollback một deployment server với việc mọi trạng thái ở client đã quay về trước deployment. Hai việc cần bằng chứng riêng.

### Ghi rõ giới hạn của kế hoạch thay đổi chính sách

Một runbook nên xác định host nào phát chính sách, những trạng thái domain liên quan và client nào có thể nhận cập nhật. Nếu hệ thống còn dùng cơ chế phân phối danh sách cài sẵn, cần có nhánh xử lý tương ứng với quy trình bên ngoài đó.

Không ghi cam kết “tắt HSTS trong vài phút cho mọi người dùng” nếu tổ chức không kiểm soát được cách từng client nhận và thực thi thay đổi. Mục tiêu phục hồi khả dụng nên tập trung vào khả năng cung cấp HTTPS đúng trên hạ tầng đã chuẩn bị.

## 13. Chuyển thành yêu cầu có thể nghiệm thu

Ví dụ bảng yêu cầu cho một hệ thống có các host trình duyệt truy cập:

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| HSTS-01 | Mỗi host HTTPS-only trong phạm vi có policy và owner xác định | Danh mục host, giá trị thời hạn, phạm vi domain và lớp cấu hình khớp nhau |
| HSTS-02 | Client nhận chính sách dự kiến qua đường HTTPS thực tế | Response thu ở điểm client đi qua CDN/proxy có giá trị hiệu lực đúng |
| HSTS-03 | Không chỉ dựa vào response trang chủ hoặc nhánh 200 | Các nhóm route và status đã chọn trong ma trận đều được kiểm tra |
| HSTS-04 | Việc mở rộng xuống subdomain dựa trên inventory và khả năng vận hành đã xác nhận | Có danh mục nhánh, owner, TLS và các dịch vụ bên thứ ba liên quan |
| HSTS-05 | Không dùng path như một ranh giới ngoại lệ HSTS trong cùng host | Đặc tả và kết quả kiểm chứng phản ánh phạm vi host |
| HSTS-06 | Tăng thời hạn hoặc thay phạm vi phải đáp ứng gate đã định | Báo cáo đo lường và kế hoạch xử lý trạng thái client cũ/mới |
| HSTS-07 | Phục hồi sự cố giữ mục tiêu HTTPS đúng thay vì phụ thuộc HTTP fallback | Diễn tập lỗi chứng thư/route và xác nhận đường phục hồi đã chuẩn bị |
| HSTS-08 | Trình duyệt kiểm thử có trạng thái và cơ chế nâng HTTPS được ghi nhận | Bằng chứng phân biệt client chưa học, đã học và có danh sách cài sẵn |
| HSTS-09 | SDK và client khác có hợp đồng bảo vệ truyền tải riêng | Kiểm tra URL HTTPS và xác minh chứng thư theo cấu hình client của dự án |
| HSTS-10 | Thay đổi edge, cache và error handling không làm sai chính sách cuối cùng | Kiểm tra hồi quy theo các điểm tạo response |
| HSTS-11 | Quản lý chứng thư bao phủ các host chịu tác động | Có owner, cảnh báo, lịch gia hạn và phương án khôi phục phù hợp |
| HSTS-12 | Quyết định preload, nếu có, được quản lý tách biệt với bật HSTS động | Hồ sơ phạm vi, điều kiện và bằng chứng trạng thái phân phối tương ứng |

Các yêu cầu này là đề xuất áp dụng từ mục tiêu và kiến trúc minh họa. Dự án cần chốt tập host, tập client, giá trị mục tiêu và bằng chứng trước khi coi chúng là tiêu chí chính thức.

## 14. Thiết kế bằng chứng kiểm chứng

Hai loại bằng chứng bổ sung cho nhau:

1. **Bằng chứng đầu ra server:** client thực sự nhận header nào qua đường triển khai cần đánh giá.
2. **Bằng chứng thực thi client:** một user agent hỗ trợ hành xử ra sao với trạng thái chính sách đã xác định.

Ví dụ lệnh quan sát header trên Windows:

```powershell
curl.exe --head https://app.example.test/login
```

Đây chỉ là ví dụ thao tác kiểm tra ở môi trường có domain và chứng thư hợp lệ. Lệnh HEAD không thay cho toàn bộ kiểm tra GET, POST, error handling hoặc hành vi trình duyệt. Việc một công cụ in được header cũng không chứng minh nó đang ghi nhớ và thực thi HSTS.

Không bỏ xác minh TLS trong một phép thử rồi lấy kết quả đó làm bằng chứng rằng đường HTTPS đáp ứng yêu cầu chứng thư của người dùng.

### Ma trận response của dự án

| Đường phản hồi | Điều cần quan sát |
| --- | --- |
| Trang chính và trang đăng nhập qua HTTPS | Header cuối cùng và giá trị policy dự kiến |
| Route API hoặc tài nguyên tĩnh trong phạm vi | Không có cấu hình riêng làm sai đầu ra đã cam kết |
| Redirect được phục vụ qua HTTPS | Đúng host, đúng policy và không chỉ phụ thuộc trang đích |
| 401, 403, 404 của ứng dụng | Error handler giữ yêu cầu header của dự án |
| Lỗi do gateway hoặc dịch vụ biên tạo | Chính sách thực tế không lệch khỏi profile đã định |
| Response từ cache | Không phát cấu hình cũ ngoài kế hoạch thay đổi |
| Host khác hoặc nhánh domain khác | Đúng inventory và phạm vi chính sách của chính host đó |

Không nhất thiết mọi dự án có cùng tập status hoặc tầng hạ tầng. Ma trận phải dựa vào những đường có thể tạo response trong hệ thống đang xét.

## 15. Kịch bản chấp nhận minh họa

### 15.1. Client đã học chính sách truy cập URL HTTP

```text
Given:
  Trình duyệt hỗ trợ HSTS đã nhận policy hợp lệ cho app.example.test.
  Policy chưa hết hiệu lực trong điều kiện thử.
  Môi trường ghi nhận được hoạt động mạng cần quan sát.

When:
  Người dùng mở một URL HTTP thuộc host này.

Then:
  Client áp dụng hành vi nâng HTTPS theo chính sách.
  Bằng chứng phân biệt thao tác nâng ở client với redirect do server gửi.
  Luồng nghiệp vụ tiếp tục qua HTTPS hợp lệ.
```

### 15.2. Cấu hình của trang lỗi

```text
Given:
  Dự án yêu cầu policy xuất hiện trên các response HTTPS trong ma trận.
  Một route tạo 404 ở ứng dụng và một tình huống tạo lỗi tại edge.

When:
  Kiểm tra các response qua đường triển khai dành cho client.

Then:
  Giá trị policy phù hợp với profile của từng điểm tạo response.
  Không kết luận từ cấu hình trang chủ thay cho các đường này.
```

### 15.3. Mở rộng phạm vi xuống cây subdomain

```text
Given:
  Có đề xuất mở rộng policy của một host xuống subdomain.
  Inventory ghi nhận một môi trường preview và một dịch vụ đối tác.

When:
  Đánh giá gate thay đổi phạm vi.

Then:
  Cả hai dịch vụ đều có owner và bằng chứng đáp ứng yêu cầu HTTPS.
  Không bỏ sót dịch vụ chỉ vì nó không có trang công khai dễ nhìn thấy.
  Nếu chưa đủ bằng chứng, phạm vi triển khai chưa được coi là đạt gate.
```

### 15.4. Thay chứng thư gặp sự cố

```text
Given:
  Môi trường thử có client đã học chính sách.
  Có phương án phục hồi HTTPS đã được chuẩn bị.

When:
  Mô phỏng một thay đổi chứng thư hoặc định tuyến làm kết nối không hợp lệ.

Then:
  Runbook khôi phục đường HTTPS đúng trong phạm vi đã thiết kế.
  Không dựa vào việc người dùng bỏ qua cảnh báo hoặc chuyển sang HTTP.
  Báo cáo ghi rõ trạng thái client và nhóm bị ảnh hưởng.
```

### 15.5. Rollback cấu hình server

```text
Given:
  Một nhóm client đã nhận policy dài hơn cấu hình mới.
  Đội triển khai thực hiện rollback server.

When:
  Đánh giá kết quả phục hồi.

Then:
  Không xem việc file cấu hình quay lại giá trị cũ là bằng chứng mọi client đã cập nhật.
  Có kiểm tra riêng với các nhóm trạng thái đã xác định.
  HTTPS tiếp tục đáp ứng yêu cầu trong khoảng tương thích còn lại.
```

## 16. Những kết luận dễ sai

### “Có redirect nên đã đạt mục tiêu HSTS”

Redirect và chính sách phía client giải quyết các phần khác nhau của đường đi. Báo cáo cần chỉ rõ cái nào được kiểm tra và trạng thái nào có hiệu lực, thay vì dùng một response 301 làm bằng chứng cho mọi thuộc tính bảo mật.

### “Chỉ cần bật ở trang đăng nhập”

Một trang có thể là nơi phát header, nhưng không tạo ranh giới policy theo path. Thiết kế cần xét toàn host và những luồng tiếp cận host đó.

### “Thêm includeSubDomains luôn là thay đổi nhỏ”

Phạm vi tên miền có thể thuộc nhiều đội và nhà cung cấp. Việc thay một chỉ thị có thể tạo một cam kết vận hành rộng hơn nhiều so với ứng dụng đang sửa.

### “Xóa header là mọi client hết chính sách”

Trạng thái ở client không đồng nhất với cấu hình hiện tại của server. Quản lý thay đổi cần có mô hình trạng thái và giới hạn phục hồi thực tế.

### “Thêm preload là đã xuất hiện trong mọi trình duyệt”

Cấu hình và trạng thái phân phối danh sách là hai loại bằng chứng khác nhau. Không đánh dấu hoàn tất một quyết định dài hạn chỉ từ một lần đọc header.

### “Ứng dụng Java hoặc SDK chắc chắn tuân theo HSTS”

Không nên suy từ khả năng trình duyệt sang mọi HTTP client. Mỗi client quan trọng cần có yêu cầu URL HTTPS, xác minh chứng thư và cấu hình cụ thể phù hợp với thư viện đang dùng.

## 17. Duy trì yêu cầu trong vòng đời hệ thống

HSTS cần được xem là cam kết theo host và theo thời gian. Một lần nghiệm thu chỉ có ý nghĩa với danh mục host, cấu hình, client và trạng thái đã quan sát tại thời điểm đó.

Khi thêm subdomain, đổi nhà cung cấp, thay CDN hoặc chuyển một dịch vụ sang hạ tầng khác, nhóm cần xem lại quan hệ với chính sách đã phát. Khi gia hạn chứng thư hoặc bàn giao quyền sở hữu, trách nhiệm duy trì HTTPS phải đi cùng dịch vụ thay vì bị bỏ lại trong một template cũ.

Thiết kế đáp ứng mục tiêu khi chính sách được phát đúng phạm vi, client mục tiêu được kiểm chứng trong các trạng thái liên quan và vận hành có khả năng duy trì HTTPS hợp lệ. Một header đúng là một phần của bằng chứng; danh mục domain, trách nhiệm vận hành và kế hoạch phục hồi làm cho yêu cầu ấy có thể duy trì lâu dài.
