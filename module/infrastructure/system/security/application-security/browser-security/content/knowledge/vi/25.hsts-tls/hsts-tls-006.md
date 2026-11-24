# HSTS Preload List: bảo vệ HTTPS ngay từ lần truy cập đầu

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích HSTS preload list và phân biệt danh sách preload tĩnh với HSTS state mà browser học từ response.
2. Mô tả cách preload giảm khoảng trống bảo vệ ở lần truy cập đầu tiên.
3. Đối chiếu domain với các yêu cầu hiện hành của chương trình HSTS preload.
4. Kiểm kê domain gốc, mọi subdomain, redirect HTTP và TLS trước khi đăng ký.
5. Thực hiện quy trình chuẩn bị, gửi yêu cầu, theo dõi trạng thái và xác minh domain đã được preload.
6. Đánh giá lợi ích, chi phí vận hành và rủi ro dài hạn trước khi bật preload.
7. Lập kế hoạch gỡ domain khỏi preload list và hiểu vì sao rollback không diễn ra tức thì.

> **Bối cảnh:** Module Browser Security phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Bài học này tập trung vào HSTS preload list: danh sách hostname được tích hợp sẵn trong browser để browser biết phải dùng HTTPS ngay cả trước khi nhận response HSTS đầu tiên từ website.

## 1. Vì sao cần HSTS preload list?

HSTS thông thường hoạt động sau khi browser nhận header từ một response HTTPS hợp lệ:

```text
Lần truy cập đầu
Browser  ---------------- HTTP/HTTPS? ----------------> Website
                                  |
                                  v
                     Website trả HSTS qua HTTPS
                                  |
                                  v
                       Browser lưu HSTS state
                                  |
                                  v
Các lần sau: HTTP URL được browser tự nâng cấp thành HTTPS
```

Có một khoảng trống ở lần đầu: browser chưa biết hostname có HSTS policy. Nếu người dùng bắt đầu bằng HTTP, một attacker trên đường truyền có thể can thiệp trước khi browser nhận được header HSTS.

HSTS preload list giải quyết khoảng trống này bằng cách đưa hostname vào danh sách được browser phân phối sẵn:

```text
Browser khởi động với preload list đã tích hợp
                    |
                    v
Người dùng mở http://shop.example.com
                    |
                    v
Browser tra cứu hostname trong preload list
                    |
                    v
Hostname đã có HSTS từ trước
                    |
                    v
Browser nâng cấp URL thành HTTPS trước request mạng
```

Nhờ vậy, browser không cần đợi website gửi HSTS header ở lần truy cập đầu tiên.

### HSTS động và preload list khác nhau thế nào?

| Đặc điểm | HSTS động | HSTS preload |
| --- | --- | --- |
| Nguồn policy | Header Strict-Transport-Security từ website | Danh sách hostname được tích hợp trong browser |
| Thời điểm có hiệu lực | Sau khi browser nhận header qua HTTPS hợp lệ | Ngay từ khi browser có phiên bản chứa hostname |
| Phụ thuộc lần truy cập trước | Có, trừ khi đã có state | Không cần truy cập website trước |
| Cập nhật | Browser học lại header và max-age | Cần quy trình cập nhật danh sách và phát hành browser |
| Gỡ bỏ | Website có thể gửi max-age=0 qua HTTPS để xóa state động | Cần yêu cầu removal và chờ browser cập nhật danh sách |
| Phạm vi subdomain | Theo policy và includeSubDomains | Theo entry preload và yêu cầu includeSubDomains của chương trình |

Preload không phải một dịch vụ tra cứu online ở mỗi lần điều hướng. Danh sách được đóng gói vào browser hoặc được browser vendor phân phối theo quy trình cập nhật của họ.

### Browser nào sử dụng danh sách?

Chrome duy trì HSTS preload list. Một số browser lớn khác duy trì danh sách dựa trên danh sách Chrome hoặc tích hợp dữ liệu theo lịch phát hành riêng. Không giả định mọi browser có cùng phiên bản danh sách tại cùng thời điểm. Hãy kiểm tra browser matrix của sản phẩm nếu yêu cầu tương thích cụ thể.

## 2. Preload thay đổi hành vi điều hướng như thế nào?

Giả sử domain shop.example.com đã có trong preload list:

1. Người dùng nhập http://shop.example.com/account.
2. Browser tra hostname trong preload list.
3. Browser nâng cấp scheme sang HTTPS trước khi gửi request HTTP.
4. TLS handshake được thực hiện với shop.example.com.
5. Nếu certificate hợp lệ, browser tiếp tục tải trang.
6. Nếu HTTPS không khả dụng hoặc certificate không hợp lệ, browser chặn kết nối theo chính sách HSTS; người dùng không có lựa chọn bỏ qua lỗi như với một website HTTP thông thường.

Preload vì vậy yêu cầu website duy trì HTTPS ổn định cho toàn bộ phạm vi hostname được bao phủ.

### Preload không phải redirect của server

Khi browser đã biết hostname từ preload list, request HTTP có thể được nâng cấp nội bộ trước khi server nhận request. Đây không phải HTTP 301/308 do server trả về.

Server vẫn nên cấu hình redirect HTTP sang HTTPS cho những client chưa có preload hoặc không áp dụng HSTS. Redirect và preload phục vụ hai mục đích bổ sung nhau:

- Redirect giúp client đang dùng HTTP tìm đến HTTPS.
- Preload giúp browser có chính sách HTTPS trước khi gửi request đầu tiên.

### Phạm vi subdomain

Preload theo yêu cầu của chương trình hiện hành bao phủ domain đã đăng ký cùng các subdomain và nested subdomain. Nếu domain cha được preload, các hostname như:

```text
example.com
www.example.com
api.example.com
admin.internal.example.com
legacy.example.com
```

đều thuộc phạm vi cần phục vụ HTTPS. Một subdomain không công khai trên Internet vẫn cần được kiểm kê; việc nó chỉ dùng nội bộ không làm nó tự nằm ngoài phạm vi policy.

## 3. Preload có luôn cần thiết không?

Không. HSTS preload bổ sung bảo vệ cho tình huống browser chưa có HSTS state và một attacker chủ động can thiệp lần truy cập đầu tiên. Tuy nhiên, preload cũng tạo cam kết vận hành dài hạn và khiến lỗi HTTPS ở bất kỳ subdomain nào trong phạm vi có thể làm dịch vụ không truy cập được.

Hướng dẫn chính thức tại hstspreload.org hiện khuyến nghị thận trọng và nêu rằng HSTS preload không được khuyến nghị như lựa chọn mặc định. Nhiều browser hiện đã tự nâng cấp một phần hoặc phần lớn điều hướng HTTP sang HTTPS; preload chủ yếu bổ sung giá trị khi có attacker chủ động khiến lần nâng cấp HTTPS thất bại. Lợi ích tăng thêm của preload vì vậy nhỏ hơn lợi ích của việc triển khai HSTS đúng cách.

Trước khi đăng ký, hãy trả lời:

- Domain có yêu cầu bảo vệ lần truy cập đầu trước attacker trên đường truyền không?
- Tất cả subdomain, kể cả subdomain nội bộ và do đối tác vận hành, có thể phục vụ HTTPS lâu dài không?
- Đội vận hành có kiểm soát certificate, DNS, redirect và hạ tầng của toàn bộ phạm vi không?
- Tổ chức có chấp nhận thời gian gỡ khỏi danh sách kéo dài qua nhiều đợt phát hành browser không?
- Có thể đạt mục tiêu bảo mật bằng HSTS động, HTTPS redirect và các biện pháp khác mà không cần preload không?

Nếu không có nhu cầu bảo vệ lần đầu đủ rõ ràng hoặc chưa kiểm soát được toàn bộ subdomain, hãy triển khai HSTS động và redirect trước. Không thêm token preload chỉ để làm theo một cấu hình mẫu.

## 4. Yêu cầu hiện hành để được đưa vào HSTS preload list

Các yêu cầu dưới đây được công bố trên trang submission chính thức của HSTS preload list. Chủ domain cần kiểm tra lại trang này trước khi gửi vì quy trình và tiêu chí có thể thay đổi.

### 1. Certificate hợp lệ

Domain phải phục vụ HTTPS với certificate hợp lệ:

- Certificate còn hạn.
- Subject Alternative Name bao phủ hostname.
- Chain được browser tin cậy.
- TLS endpoint hoạt động ổn định.
- Gia hạn certificate có thể duy trì lâu dài.

Một certificate hợp lệ cho domain gốc không tự chứng minh tất cả subdomain đều có certificate phù hợp.

### 2. HTTP phải redirect sang HTTPS trên cùng host nếu port 80 đang phục vụ

Nếu domain lắng nghe HTTP trên port 80, request HTTP phải được chuyển sang HTTPS trên cùng hostname.

Ví dụ:

```text
http://example.com/path
        |
        v
https://example.com/path
```

Không chuyển thẳng sang một hostname khác như https://www.example.com để thay cho yêu cầu redirect cùng host. Có thể thực hiện redirect bổ sung từ HTTPS apex sang một hostname canonical sau khi đã thiết lập kết nối HTTPS, nhưng response redirect HTTPS đó cũng phải mang HSTS header theo yêu cầu của chương trình.

### 3. Tất cả subdomain phải phục vụ HTTPS

Kiểm tra:

- Subdomain www nếu có bản ghi DNS.
- API và admin.
- Subdomain lồng nhiều tầng.
- Hostname dùng cho trang đăng nhập, thanh toán, hỗ trợ hoặc chiến dịch.
- Hostname nội bộ chỉ truy cập qua VPN/private network.
- Subdomain do nhà cung cấp bên thứ ba hoặc nền tảng SaaS quản lý.

Đừng chỉ kiểm tra các hostname có trong sitemap hoặc được liên kết từ trang chủ. Một host cũ, vanity URL hoặc hệ thống nội bộ vẫn có thể nằm trong phạm vi.

### 4. HSTS header trên HTTPS response của domain gốc

Response HTTPS của base domain phải gửi header có đủ ba thành phần:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

Yêu cầu chính:

| Thành phần | Yêu cầu |
| --- | --- |
| max-age | Ít nhất 31.536.000 giây, tương đương một năm |
| includeSubDomains | Bắt buộc |
| preload | Bắt buộc để yêu cầu được xem xét đưa vào danh sách |

Ví dụ trên dùng giá trị tối thiểu một năm. Trang chính thức cũng đưa ra ví dụ với max-age dài hơn. Không chọn giá trị dài hơn nếu tổ chức chưa sẵn sàng duy trì HTTPS cho toàn bộ phạm vi trong thời gian dài.

Nếu HTTPS apex trả redirect tới một trang khác, response redirect đó vẫn phải có HSTS header. Không chỉ đặt header ở trang đích cuối cùng.

### Tóm tắt checklist

| Điều kiện | Trạng thái |
| --- | --- |
| Certificate domain gốc hợp lệ | Cần xác minh |
| HTTP port 80 redirect sang HTTPS trên cùng host | Cần xác minh nếu port 80 hoạt động |
| Mọi subdomain và nested subdomain phục vụ HTTPS | Cần xác minh |
| www phục vụ HTTPS nếu có DNS record | Cần xác minh |
| Subdomain nội bộ và của bên thứ ba đã kiểm kê | Cần xác minh |
| HSTS header có trên HTTPS response của base domain | Cần xác minh |
| max-age ít nhất 31.536.000 giây | Cần xác minh |
| Có includeSubDomains | Cần xác minh |
| Có preload | Cần xác minh |
| HTTPS redirect response vẫn có HSTS header | Cần xác minh nếu có redirect HTTPS |

## 5. Kiểm kê toàn bộ domain trước khi đăng ký

Đây là bước quan trọng nhất. Preload một domain có thể buộc mọi subdomain và nested subdomain phải truy cập qua HTTPS. Nếu một hostname trong phạm vi không có TLS hợp lệ, người dùng có thể không truy cập được hostname đó trong browser có entry preload.

### Lập danh sách hostname

Kết hợp nhiều nguồn thông tin:

- DNS zone và danh sách record đang hoạt động.
- Certificate inventory và Certificate Transparency logs.
- Cấu hình CDN, load balancer, reverse proxy và ingress.
- Danh mục ứng dụng/cloud account.
- Danh sách host do nhóm IT, security và platform quản lý.
- Tài liệu tích hợp của các nhà cung cấp bên thứ ba.
- Subdomain staging, preview, test và hệ thống nội bộ.

DNS enumeration công khai không thể bảo đảm tìm ra mọi hostname nội bộ. Cần đối chiếu với chủ sở hữu domain, đội hạ tầng và đội ứng dụng.

### Phân loại trạng thái HTTPS

| Nhóm hostname | Câu hỏi cần xác minh | Hành động |
| --- | --- | --- |
| Production | Certificate và redirect đã ổn định chưa? | Kiểm tra liên tục và theo dõi expiry |
| Internal/VPN | Browser có thể truy cập bằng HTTPS không? | Cấp certificate phù hợp và kiểm thử từ mạng nội bộ |
| Third-party/SaaS | Nhà cung cấp có hỗ trợ HTTPS trên vanity hostname không? | Xác nhận hỗ trợ, DNS và TLS |
| Staging/preview | Có hostname nào được tạo tự động không? | Kiểm soát vòng đời và cấp TLS |
| Legacy | Có host chỉ hỗ trợ HTTP không? | Di chuyển, đổi domain hoặc retire trước preload |
| Unused | Có thể còn DNS record hoặc client cũ không? | Xác minh owner rồi retire an toàn |

### Ví dụ tình huống không nên preload

Giả sử example.com có:

```text
www.example.com       HTTPS
api.example.com       HTTPS
admin.example.com     HTTPS
campaign.example.com  HTTP do nhà cung cấp marketing quản lý
printer.example.com   HTTP trong mạng nội bộ
```

Chỉ cần campaign.example.com hoặc printer.example.com còn được sử dụng, domain cha chưa sẵn sàng cho preload theo yêu cầu includeSubDomains. Việc chúng không xuất hiện trong luồng người dùng công khai không loại bỏ rủi ro.

## 6. Rollout HSTS trước khi preload

Trang HSTS preload chính thức khuyến nghị triển khai HSTS theo từng giai đoạn và chờ đủ thời gian max-age của từng giai đoạn trước khi tăng tiếp. Ví dụ các mốc:

| Giai đoạn | Header mẫu | Thời gian theo dõi |
| --- | --- | --- |
| Thử nghiệm ban đầu | max-age=300; includeSubDomains | Ít nhất 5 phút |
| Mở rộng | max-age=604800; includeSubDomains | Ít nhất 1 tuần |
| Ổn định | max-age=2592000; includeSubDomains | Ít nhất 1 tháng |
| Sẵn sàng đăng ký | max-age=31536000; includeSubDomains; preload | Duy trì lâu dài |

Đây là lộ trình tham khảo; chỉ bắt đầu includeSubDomains sau khi đã xác minh mọi subdomain có thể hỗ trợ HTTPS. Nếu phát hiện lỗi trong một giai đoạn, sửa lỗi và đánh giá lại trước khi tăng max-age.

Trong mỗi giai đoạn:

1. Theo dõi tỷ lệ lỗi TLS, redirect và page load.
2. Kiểm tra các hostname có lưu lượng thấp.
3. Theo dõi phản ánh từ nhân viên và người dùng beta.
4. Kiểm tra doanh thu, chuyển đổi và các luồng nghiệp vụ phụ thuộc subdomain.
5. Chờ hết toàn bộ thời hạn max-age của giai đoạn trước khi chuyển sang giai đoạn kế tiếp.

Không sử dụng max-age một năm ngay từ ngày đầu trên domain chưa được kiểm kê.

## 7. Quy trình gửi domain lên HSTS preload list

Khi domain đáp ứng yêu cầu và tổ chức đã chấp nhận rủi ro dài hạn, quy trình thường gồm:

### Bước 1 — Chuẩn bị base domain

Xác định domain gốc/registrable domain cần đăng ký theo form chính thức. Không tự chọn một subdomain riêng nếu mục tiêu là áp dụng policy cho toàn bộ domain và subdomain.

### Bước 2 — Phát HSTS header đáp ứng yêu cầu

Ví dụ:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

Header phải xuất hiện trên HTTPS response của base domain. Nếu HTTPS apex redirect sang canonical host, redirect response cũng cần header.

### Bước 3 — Kiểm tra HTTP redirect và mọi subdomain

Kiểm tra http://example.com chuyển sang https://example.com trên cùng host nếu port 80 đang hoạt động. Kiểm tra HTTPS certificate và response của www, API, admin, internal và các host đã kiểm kê.

### Bước 4 — Đọc lại yêu cầu chính thức

Truy cập trang submission của HSTS preload list, đọc cảnh báo và xác nhận phạm vi ảnh hưởng tới mọi subdomain/nested subdomain.

### Bước 5 — Gửi form

Nhập domain vào form và gửi yêu cầu. Header có token preload chỉ thể hiện ý định xin đưa domain vào danh sách; **chỉ thêm token này không tự động đưa domain vào preload list**.

### Bước 6 — Theo dõi trạng thái

Trang submission có thể hiển thị trạng thái pending inclusion. Quay lại kiểm tra domain trong các tuần tiếp theo và theo dõi thay đổi trong danh sách.

### Bước 7 — Chờ browser cập nhật

Các entry mới được đưa vào source/list của browser rồi phân phối qua các phiên bản phát hành. Theo tài liệu chính thức, có thể mất vài tháng trước khi entry xuất hiện trong bản Chrome stable mà người dùng đang chạy. Các browser khác có lịch tích hợp riêng.

Vì vậy, phân biệt ba mốc:

1. Form đã nhận yêu cầu.
2. Domain đã được đưa vào nguồn dữ liệu/list của browser vendor.
3. Người dùng đã cập nhật browser lên phiên bản chứa entry.

Ba mốc này không xảy ra đồng thời.

## 8. Kiểm tra domain và trạng thái preload

### Kiểm tra response header HTTPS

Dùng curl để kiểm tra server có trả header:

```bash
curl -sS -D - -o /dev/null https://example.com/
```

Tìm:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
```

Nếu domain có HTTPS redirect:

```bash
curl -sS -D - -o /dev/null -L https://example.com/
```

Kiểm tra từng response trong redirect chain, đặc biệt response redirect HTTPS đầu tiên. Không chỉ nhìn header ở response cuối.

### Kiểm tra HTTP redirect

```bash
curl -sS -D - -o /dev/null http://example.com/
```

Nếu port 80 hoạt động, kiểm tra status và Location có giữ nguyên hostname khi chuyển sang HTTPS. Ví dụ:

```http
HTTP/1.1 301 Moved Permanently
Location: https://example.com/
```

curl giúp kiểm tra server response và redirect; curl mặc định không phải browser HSTS preload client. Không dùng kết quả curl để kết luận browser đã có entry preload.

### Kiểm tra browser

Trong Chrome, có thể dùng trang nội bộ HSTS state:

```text
chrome://net-internals/#hsts
```

Tùy phiên bản browser, giao diện công cụ nội bộ có thể thay đổi hoặc không còn khả dụng. Nếu công cụ không có, dùng profile sạch, Network panel và kiểm tra hành vi điều hướng HTTP/HTTPS trong browser version mục tiêu.

### Kiểm tra từ profile mới

Để kiểm tra lợi ích lần đầu:

1. Dùng browser profile thử nghiệm mới.
2. Xác nhận browser version đã chứa entry preload cần kiểm tra.
3. Nhập URL HTTP của hostname.
4. Quan sát browser nâng cấp sang HTTPS trước khi gửi request HTTP.
5. Kiểm tra certificate và response HTTPS.

Nếu chỉ kiểm tra trên profile đã từng truy cập domain, browser có thể đang dùng HSTS state động đã lưu từ trước. Điều đó không chứng minh domain có trong preload list.

## 9. Gỡ domain khỏi HSTS preload list

Gỡ preload khó hơn nhiều so với xóa HSTS state động. Khi domain đã được tích hợp trong browser, website không thể xóa entry tĩnh chỉ bằng cách thay header.

### Gỡ token preload không đồng nghĩa đã được gỡ

Bỏ token preload khỏi header có thể làm domain đủ điều kiện gửi yêu cầu removal, nhưng không tự động xóa entry khỏi browser.

Quy trình tổng quát:

1. Đảm bảo website vẫn phục vụ HTTPS trong thời gian chờ.
2. Cập nhật header theo hướng dẫn removal hiện hành; trang chính thức cho biết bỏ token preload làm domain đủ điều kiện dùng removal form.
3. Gửi yêu cầu removal trên trang chính thức.
4. Theo dõi trạng thái và phản hồi.
5. Chờ danh sách được cập nhật trong source của browser.
6. Chờ các phiên bản browser mới mang thay đổi tới người dùng.
7. Kiểm tra các browser khác vì không có bảo đảm mọi vendor cập nhật cùng thời điểm.

### max-age=0 có xóa preload không?

Không. Header:

```http
Strict-Transport-Security: max-age=0
```

được gửi qua HTTPS có thể xóa HSTS state động mà browser đã học từ website. Nó không xóa entry tĩnh đã được đóng gói trong preload list của browser.

### Vì sao removal có thể mất nhiều tháng?

Danh sách preload được đưa vào source và phát hành cùng browser. Sau khi source được cập nhật, người dùng vẫn cần cài phiên bản browser có thay đổi. Trang chính thức cảnh báo quá trình này có thể mất vài tháng và không thể bảo đảm cho tất cả browser.

Trong thời gian đó, domain và các subdomain vẫn cần phục vụ HTTPS hợp lệ để người dùng không bị khóa truy cập.

## 10. Rủi ro vận hành khi preload

| Rủi ro | Hậu quả | Cách giảm thiểu |
| --- | --- | --- |
| Bỏ sót subdomain nội bộ | Người dùng VPN không truy cập được host HTTP | Kiểm kê DNS, ứng dụng nội bộ và owner trước khi đăng ký |
| Vanity hostname do SaaS quản lý | Nhà cung cấp không hỗ trợ TLS theo yêu cầu | Xác nhận hỗ trợ HTTPS và kiểm thử thực tế |
| Certificate hết hạn | Browser chặn hostname thuộc preload | Tự động gia hạn, giám sát expiry và cảnh báo |
| Redirect sai host | Không đáp ứng yêu cầu redirect hoặc tạo luồng khó debug | HTTP redirect sang HTTPS cùng host trước |
| Header thiếu trên HTTPS redirect | Có thể không đạt tiêu chí submission | Gắn HSTS lên response redirect HTTPS |
| Bật preload nhầm domain cha | Tất cả nested subdomain bị ảnh hưởng | Kiểm tra phạm vi domain và xác nhận owner |
| Cần rollback gấp | Entry tĩnh vẫn tồn tại trên browser cũ | Duy trì HTTPS và có kế hoạch removal dài hạn |
| Browser list không đồng bộ | Hành vi khác nhau giữa browser/version | Kiểm thử browser matrix và theo dõi release |

### Ví dụ sự cố

Một công ty preload example.com vì website chính đã chạy HTTPS. Sau đó nhân viên phát hiện:

- vpn.example.com chỉ chạy HTTP trong mạng nội bộ.
- campaign.example.com do nền tảng marketing quản lý và không cấp certificate phù hợp.
- legacy.example.com là ứng dụng cũ không có đội vận hành.

Các hostname này có thể không truy cập được trên browser đã preload. Việc gửi max-age=0 hoặc bỏ includeSubDomains không thể lập tức gỡ entry tĩnh khỏi browser. Công ty phải tiếp tục phục vụ HTTPS hoặc hoàn tất removal và chờ browser cập nhật.

## 11. Ví dụ cấu hình server

### Nginx: domain gốc

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate     /etc/ssl/certs/example.com.pem;
    ssl_certificate_key /etc/ssl/private/example.com.key;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

    location / {
        proxy_pass http://application;
    }
}
```

HTTP listener redirect cùng host:

```nginx
server {
    listen 80;
    server_name example.com;

    return 301 https://example.com$request_uri;
}
```

Nếu HTTPS apex chuyển hướng sang canonical hostname, response redirect đó cũng cần HSTS header. Kiểm tra cấu hình add_header và kế thừa ở các location; không chỉ xác minh trang cuối.

### Node.js / Express với Helmet

```js
import express from "express";
import helmet from "helmet";

const app = express();

app.use(
  helmet.hsts({
    maxAge: 31536000,
    includeSubDomains: true,
    preload: true
  })
);
```

Đây là ví dụ header khi domain đã qua kiểm kê và sẵn sàng đáp ứng preload requirements. Không bật các option này mặc định cho mọi ứng dụng hoặc mọi domain.

### Kiểm tra header ở nhiều hostname

```bash
for host in example.com www.example.com api.example.com admin.example.com; do
  echo "=== $host ==="
  curl -sS -D - -o /dev/null "https://$host/"
done
```

Danh sách trên chỉ là ví dụ. Hãy thay bằng inventory thật, gồm cả subdomain nội bộ và subdomain do nhà cung cấp quản lý. Một vòng lặp curl không thay thế xác nhận owner và kiểm thử luồng ứng dụng.

## 12. Ma trận kiểm thử trước và sau submission

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Certificate domain gốc | Kiểm tra TLS chain và hostname | Certificate hợp lệ |
| HTTP apex | Gửi request tới port 80 | Redirect sang HTTPS trên cùng host nếu port 80 hoạt động |
| HTTPS apex header | Đọc response header | Có max-age >= 31536000, includeSubDomains và preload |
| HTTPS redirect | Theo dõi từng response trong chain | Redirect response HTTPS vẫn có HSTS |
| www | Kiểm tra DNS và HTTPS | Nếu có DNS record, hostname phục vụ HTTPS |
| Subdomain nội bộ | Kiểm tra từ mạng nội bộ/VPN | HTTPS hợp lệ |
| Subdomain bên thứ ba | Kiểm tra certificate và redirect | Nhà cung cấp hỗ trợ HTTPS ổn định |
| Browser profile sạch | Mở HTTP trong browser đã có preload entry | Browser nâng cấp sang HTTPS trước request |
| Browser chưa có entry | Dùng version/profile phù hợp | Không kết luận preload chỉ từ HSTS state động |
| Removal | Kiểm tra status và version browser | Chỉ coi là gỡ khi browser đã nhận danh sách mới |

## 13. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ thêm token preload là đã được preload | Domain chưa có trong browser list | Gửi form và theo dõi trạng thái |
| Chỉ kiểm tra domain gốc | Subdomain nội bộ hoặc SaaS bị bỏ sót | Kiểm kê mọi nested subdomain |
| Bỏ qua www vì không có link tới www | Nếu DNS record tồn tại, www vẫn thuộc yêu cầu | Kiểm tra DNS và phục vụ HTTPS |
| Chỉ redirect HTTP sang hostname www | Không đáp ứng yêu cầu redirect cùng host | Redirect HTTP sang HTTPS cùng hostname |
| Chỉ đặt HSTS ở trang HTTPS cuối | HTTPS redirect response thiếu header | Kiểm tra và thêm header vào redirect response |
| Nghĩ preload có hiệu lực ngay sau submit | Browser stable có thể chưa có entry | Theo dõi pending, source update và browser release |
| Nghĩ max-age=0 gỡ preload | Entry tĩnh vẫn tồn tại | Dùng removal form và chờ browser update |
| Cho rằng mọi browser đồng bộ tức thì | Người dùng có hành vi khác nhau theo browser/version | Duy trì HTTPS và kiểm thử browser matrix |
| Bật preload mặc định trong template | Chủ domain có thể không hiểu phạm vi | Preload phải là opt-in có xác nhận rõ |
| Chỉ dùng curl để chứng minh browser preload | curl không đại diện HSTS state của browser | Kiểm tra trong browser profile và version mục tiêu |

## 14. Câu hỏi củng cố

**Câu 1.** HSTS động khác preload list ở điểm nào?

**Giải đáp:** HSTS động được browser học từ response HTTPS của website. Preload list được tích hợp sẵn trong browser nên có hiệu lực trước lần truy cập đầu.

**Câu 2.** Chỉ thêm preload vào Strict-Transport-Security có đủ để domain xuất hiện trong Chrome preload list không?

**Giải đáp:** Không. Header thể hiện yêu cầu; chủ domain còn phải đáp ứng tiêu chí và gửi submission qua form chính thức. Sau đó cần chờ danh sách được phát hành trong browser.

**Câu 3.** Vì sao phải kiểm tra cả subdomain nội bộ?

**Giải đáp:** Preload với includeSubDomains bao phủ subdomain và nested subdomain trong phạm vi, kể cả hostname không công khai. Một host HTTP nội bộ có thể bị browser buộc dùng HTTPS và không truy cập được.

**Câu 4.** max-age tối thiểu theo yêu cầu hiện hành là bao nhiêu?

**Giải đáp:** Ít nhất 31.536.000 giây, tương đương một năm; đồng thời cần includeSubDomains và preload.

**Câu 5.** Nếu HTTPS apex redirect sang www, chỉ trang www có HSTS header đã đủ chưa?

**Giải đáp:** Chưa. Response redirect HTTPS của apex cũng phải có HSTS header theo yêu cầu submission.

**Câu 6.** Gửi max-age=0 có xóa domain khỏi preload list không?

**Giải đáp:** Không. Nó xóa HSTS state động; entry preload cần removal request và thời gian cập nhật browser.

**Câu 7.** Vì sao preload không nên bật mặc định?

**Giải đáp:** Preload mở rộng chính sách HTTPS tới mọi subdomain, khó rollback và có thể làm hỏng hostname chưa sẵn sàng. Chỉ đăng ký sau khi kiểm kê và đánh giá rõ lợi ích tăng thêm.

## 15. Tổng kết

**HSTS preload list** giúp browser biết một hostname phải dùng HTTPS ngay từ trước lần truy cập đầu tiên. Để được xem xét đưa vào danh sách, domain cần certificate hợp lệ, redirect HTTP sang HTTPS cùng host nếu port 80 hoạt động, HTTPS cho mọi subdomain và HSTS header trên HTTPS response của base domain với max-age ít nhất một năm, includeSubDomains và preload.

Token preload không tự đăng ký domain. Chủ sở hữu phải gửi form, theo dõi trạng thái và chờ browser phát hành phiên bản có entry. Việc gỡ cũng chậm: max-age=0 chỉ xóa HSTS state động, còn entry preload cần removal process và thời gian cập nhật browser.

Preload không phải lựa chọn mặc định. Hãy triển khai HSTS và HTTPS redirect trước, kiểm kê toàn bộ domain/subdomain, đánh giá lợi ích bảo vệ lần đầu so với chi phí vận hành, rồi mới quyết định đăng ký. Nếu đã preload, duy trì HTTPS cho toàn bộ phạm vi trong dài hạn và chuẩn bị kế hoạch xử lý certificate, subdomain và removal.

## Tài liệu tham khảo

1. [HSTS Preload — Submission Requirements](https://hstspreload.org/): tiêu chí hiện hành, form submission, theo dõi trạng thái và removal.
2. [RFC 6797 — HTTP Strict Transport Security (HSTS)](https://www.rfc-editor.org/rfc/rfc6797): cơ chế HSTS, policy động và hành vi browser.
3. [Chromium — HTTP Strict Transport Security](https://www.chromium.org/hsts/): cách Chromium quản lý HSTS và preload list.
4. [MDN — Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security): cú pháp header và triển khai HSTS.
5. [OWASP — HTTP Strict Transport Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Strict_Transport_Security_Cheat_Sheet.html): rollout, preload và rủi ro vận hành.
