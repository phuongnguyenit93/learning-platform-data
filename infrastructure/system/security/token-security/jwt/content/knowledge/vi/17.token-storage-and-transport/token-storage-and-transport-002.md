# Vì sao không đặt JWT vào URL, query string hoặc địa chỉ chia sẻ?

## 1. Vấn đề cốt lõi: URL thường bị lưu và sao chép rộng hơn ta nghĩ

JSON Web Token (JWT) là định dạng biểu diễn claims. Trong nhiều hệ thống, JWT được dùng như **bearer access token**: bất kỳ ai nắm giữ token đều có thể sử dụng nó trong phạm vi token được cấp, cho đến khi token hết hạn hoặc bị cơ chế khác từ chối.

Nếu một bearer JWT được đặt trong URL, ví dụ query string:

```text
https://api.example.com/orders?access_token=eyJhbGciOi...
```

thì token trở thành một phần của địa chỉ có thể xuất hiện trong lịch sử trình duyệt, log máy chủ, proxy, CDN, công cụ phân tích, hệ thống giám sát, ảnh chụp màn hình, email, tin nhắn và các bản sao khác của URL.

Đây là rủi ro lớn vì URL thường được dùng như dữ liệu định tuyến và dữ liệu chẩn đoán. Nhiều thành phần ghi lại URL đầy đủ mà không nhận biết một query parameter đang chứa credential. Khi token bị lộ, người có được nó có thể gửi lại request để truy cập tài nguyên nếu các điều kiện xác minh khác vẫn đạt.

**Nguyên tắc:** Không truyền bearer JWT trong URL, query string, path hoặc địa chỉ chia sẻ. Với OAuth 2.0 access token, [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700#section-4.3.2) yêu cầu client không truyền access token trong URI query parameter theo cách mô tả ở RFC 6750. [RFC 6750](https://www.rfc-editor.org/rfc/rfc6750#section-2.3) cũng khuyến nghị không dùng cách này vì nguy cơ URL chứa token bị ghi log rất cao.

## 2. Vì sao bearer JWT trong URL nguy hiểm?

### Người nắm giữ token có thể sử dụng token

Với bearer token, quyền sử dụng gắn với việc nắm giữ token. Nếu token bị sao chép từ URL, kẻ tấn công có thể gửi token đến resource server như client hợp lệ, miễn là token còn được chấp nhận và không có ràng buộc sender-constrained ngăn việc sử dụng đó.

Ví dụ:

1. Người dùng mở một URL chứa JWT để tải báo cáo.
2. URL được lưu trong browser history hoặc access log.
3. Người khác có quyền đọc log, lịch sử đồng bộ hoặc bản sao của URL.
4. Người đó gửi lại token đến API trước khi token hết hạn.
5. API có thể chấp nhận request nếu chữ ký, issuer, audience, thời hạn và quyền đều hợp lệ.

Kẻ tấn công không cần biết mật khẩu hoặc tạo chữ ký JWT mới. Họ chỉ cần lấy được bearer token còn sử dụng được.

### JWT tự chứa không tự thu hồi ngay khi bị lộ

Một JWT có chữ ký hợp lệ thường có thể được xác minh độc lập mà không cần hỏi issuer ở mỗi request. Điều này giúp giảm phụ thuộc trạng thái, nhưng cũng có nghĩa token bị lộ có thể tiếp tục sử dụng đến `exp`, trừ khi hệ thống có denylist, introspection, phiên bản credential, sender constraint hoặc cơ chế thu hồi khác.

Thời hạn ngắn, audience restriction và scope hẹp giúp giảm tác động, nhưng không làm URL trở thành nơi truyền token an toàn.

## 3. URL có thể làm lộ token ở những đâu?

Một URL có thể đi qua nhiều thành phần trước, trong và sau khi request được xử lý. Những nơi thường gặp gồm:

| Nơi lưu hoặc xử lý | Cách token có thể xuất hiện |
| --- | --- |
| Browser history | Trình duyệt lưu địa chỉ đã truy cập; người có quyền dùng thiết bị hoặc dữ liệu đồng bộ có thể xem lại |
| Address bar, bookmarks và autocomplete | URL có thể được lưu, gợi ý hoặc sao chép lại |
| Browser sync | Lịch sử hoặc bookmark có thể đồng bộ sang thiết bị khác theo cài đặt tài khoản |
| Web server access log | Log thường ghi request target gồm path và query string |
| Reverse proxy, load balancer và API gateway | Có thể ghi URL đầy đủ để chẩn đoán hoặc thống kê request |
| CDN, WAF và cache trung gian | Có thể lưu hoặc ghi lại URL như cache key, request metadata hoặc security event |
| Application log và exception report | Ứng dụng có thể ghi URL khi xảy ra lỗi hoặc khi trace request |
| Analytics, telemetry và session replay | Công cụ có thể thu thập page URL, navigation hoặc dữ liệu request |
| HTTP `Referer` | URL nguồn có thể được gửi trong header khi trình duyệt tải tài nguyên hoặc điều hướng, tùy Referrer Policy và ngữ cảnh |
| Link preview, crawler và email scanner | Hệ thống tự động có thể mở URL để tạo preview, kiểm tra an toàn hoặc quét nội dung |
| Email, chat, ticket và tài liệu | URL được chia sẻ có thể bị chuyển tiếp, lưu trữ hoặc hiển thị cho người không dự kiến |
| Screenshot, screen recording và clipboard | Token có thể bị ghi lại cùng địa chỉ trên màn hình hoặc nội dung sao chép |

Không phải mọi nền tảng đều lưu mọi URL theo cùng cách. Rủi ro đến từ việc URL có nhiều điểm xuất hiện và nhiều hệ thống ghi nhận nó theo mặc định, trong khi token là dữ liệu nhạy cảm.

### Log có thể lộ token dù ứng dụng không cố ý ghi token

Ví dụ log access:

```text
GET /orders?access_token=eyJhbGciOi... HTTP/1.1
200 OK
```

Một người vận hành có quyền đọc log có thể nhìn thấy token. Log cũng có thể được chuyển đến hệ thống tập trung, nhà cung cấp giám sát, kho lưu trữ dài hạn hoặc bản sao phục vụ điều tra.

Ngay cả khi ứng dụng không ghi query string, proxy hoặc CDN phía trước vẫn có thể ghi request target. Vì vậy, không thể dựa vào một cấu hình logging ở riêng ứng dụng để giải quyết vấn đề.

## 4. Query string, path và fragment đều không phải nơi lưu bearer token

URL có các thành phần khác nhau. Chúng có hành vi truyền tải khác nhau, nhưng không thành phần nào nên được dùng để giấu bearer token.

| Vị trí | Ví dụ | Điều cần hiểu |
| --- | --- | --- |
| Query string | `/resource?access_token=...` | Được gửi trong request target và thường xuất hiện trong access log, proxy log, browser history |
| Path segment | `/resource/token/...` | Được gửi đến server như một phần path; thường được ghi log và có thể xuất hiện trong URL/referrer |
| Fragment | `/callback#access_token=...` | Không được gửi trong HTTP request thông thường, nhưng vẫn có thể xuất hiện trong browser history, clipboard và mã phía client; JavaScript trên trang có thể đọc fragment |

### Query string

Query string là vị trí dễ bị lạm dụng nhất vì có vẻ thuận tiện để truyền tham số. Tuy nhiên, URL đầy đủ thường được ghi lại trong access log và các hệ thống trung gian. Tham số token cũng có thể bị sao chép khi người dùng copy link hoặc chia sẻ địa chỉ.

### Path segment

Đưa JWT vào path không khắc phục được vấn đề. Path vẫn là một phần của request target và có thể được ghi trong access log, proxy log, analytics hoặc referrer theo chính sách tương ứng.

Ví dụ không an toàn:

```text
https://api.example.com/download/eyJhbGciOi...
```

Không nên cho rằng path ít nhạy cảm hơn query string. Cả hai đều là thành phần URL có thể bị ghi nhận và chia sẻ.

### Fragment

Fragment bắt đầu bằng ký tự `#`. Trình duyệt thông thường không gửi fragment trong HTTP request đến server, nhưng fragment vẫn tồn tại ở phía client:

- Có thể xuất hiện trong browser history.
- Có thể được đọc bởi JavaScript trên trang.
- Có thể bị lộ qua extension, công cụ debug, screenshot, clipboard hoặc dữ liệu đồng bộ.
- Có thể bị xử lý sai khi trang chuyển fragment vào query string, log hoặc request khác.

OAuth 2.0 trước đây từng có implicit flow trả access token trong fragment. [RFC 9700, mục 4.3.2](https://www.rfc-editor.org/rfc/rfc9700#section-4.3.2) ghi nhận URL chứa fragment access token cũng có thể xuất hiện trong browser history và khuyến nghị các biện pháp thay thế. Không nên dùng fragment như một cách “an toàn hơn” để đặt bearer JWT vào URL.

## 5. HTTPS không loại bỏ nguy cơ rò rỉ URL

HTTPS bảo vệ dữ liệu trên đường truyền giữa các điểm kết thúc TLS. Nó không ngăn các thành phần ở hai đầu hoặc các hệ thống trung gian được ủy quyền ghi lại URL.

Ví dụ, khi trình duyệt gửi request qua HTTPS:

```text
Browser -- TLS --> CDN -- TLS --> API Gateway -- TLS --> Application
```

CDN, API gateway và ứng dụng có thể giải mã request tại điểm kết thúc TLS để xử lý. Nếu một thành phần ghi full URL vào log, query/path chứa token vẫn bị lộ trong hệ thống đó.

HTTPS không tự ngăn:

- Browser history lưu URL.
- Người dùng copy URL rồi gửi qua email/chat.
- Proxy hoặc gateway ghi URL sau khi kết thúc TLS.
- Analytics hoặc error reporting thu thập URL.
- Trang hiện tại gửi URL nguồn qua `Referer` trong các trường hợp chính sách cho phép.
- Malware, extension hoặc người có quyền truy cập thiết bị đọc địa chỉ.

Do đó, HTTPS là điều kiện cần để bảo vệ truyền tải, nhưng không biến URL thành kho chứa credential an toàn.

## 6. Rủi ro từ HTTP `Referer` và tài nguyên bên thứ ba

Khi trình duyệt tải một tài nguyên hoặc điều hướng từ trang này sang trang khác, nó có thể gửi header `Referer` cho biết URL nguồn. Nội dung được gửi phụ thuộc vào `Referrer-Policy`, loại request và quan hệ cùng nguồn/khác nguồn.

Ví dụ trang có URL:

```text
https://app.example.com/report?access_token=eyJhbGciOi...
```

Trang tải một hình ảnh hoặc script từ dịch vụ bên ngoài. Nếu chính sách referrer cho phép gửi đầy đủ URL trong ngữ cảnh đó, URL chứa token có thể được chuyển đến bên cung cấp tài nguyên.

Các trình duyệt hiện đại có chính sách mặc định hạn chế một phần thông tin referrer khi điều hướng cross-origin, nhưng không nên dựa vào mặc định này để bảo vệ token trong URL. Cấu hình có thể thay đổi, same-origin request có thể mang nhiều thông tin hơn và URL vẫn còn trong browser history, log hoặc hệ thống khác.

### Giảm rủi ro referrer

Nếu một trang xử lý dữ liệu nhạy cảm:

- Có thể đặt `Referrer-Policy: no-referrer` để không gửi URL nguồn trong header `Referer`.
- Tránh tải script, ảnh, pixel, font hoặc nội dung bên thứ ba không cần thiết trên trang xử lý credential.
- Không coi Referrer Policy là biện pháp thay thế việc không đặt token trong URL.
- Tránh chuyển URL chứa credential qua redirect hoặc mở liên kết ngoài trước khi loại bỏ dữ liệu nhạy cảm.

Referrer Policy chỉ kiểm soát một kênh rò rỉ. Nó không xóa URL khỏi lịch sử trình duyệt, access log, clipboard hoặc các hệ thống đã thu thập URL.

## 7. Link preview, crawler và email scanner có thể sử dụng URL trước người dùng

Nhiều hệ thống tự động mở URL khi người dùng gửi hoặc nhận một liên kết:

- Ứng dụng chat tạo ảnh preview.
- Email gateway quét URL để phát hiện phishing hoặc malware.
- Công cụ bảo mật kiểm tra đích liên kết.
- Crawler hoặc bot truy cập trang để thu thập metadata.
- Browser prefetch/prerender có thể truy cập trước khi người dùng tương tác, tùy cấu hình.

Nếu URL chứa token có hiệu lực, hệ thống tự động có thể vô tình làm lộ token trong log hoặc gửi token đến dịch vụ preview. Nếu token là one-time-use, scanner còn có thể tiêu thụ token trước người dùng thật.

Đây là lý do đặc biệt quan trọng đối với các link đăng nhập, link đặt lại mật khẩu hoặc link xác nhận thao tác. Một URL bí mật không nhất thiết chỉ được mở bởi người nhận mà bạn dự kiến.

## 8. Vì sao địa chỉ chia sẻ làm tăng phạm vi rủi ro?

URL chứa JWT có thể trở thành một credential có thể chuyển giao. Khi người dùng copy địa chỉ, họ có thể vô tình cấp quyền truy cập cho mọi người nhận URL.

Ví dụ:

```text
https://app.example.com/share/report?token=eyJhbGciOi...
```

Địa chỉ này có thể được:

- Gửi vào nhóm chat thay vì gửi riêng.
- Chuyển tiếp trong email hoặc ticket hỗ trợ.
- Lưu vào bookmark hoặc tài liệu cộng tác.
- Đưa vào lịch sử đồng bộ của trình duyệt.
- Chụp lại trong screenshot hoặc video hướng dẫn.
- Gửi tới hệ thống preview của nền tảng chia sẻ.

Nếu token là bearer credential, người nhận URL có thể sử dụng token trong phạm vi quyền của nó. Đổi tên query parameter từ `token` sang một tên khó đoán không thay đổi rủi ro này.

**Một URL không phải cơ chế phân quyền.** Việc người dùng biết địa chỉ không chứng minh họ là người được cấp quyền, trừ khi hệ thống chủ ý thiết kế một capability link và kiểm soát chặt vòng đời của nó.

## 9. Cách truyền JWT phù hợp hơn

### Ưu tiên HTTP Authorization header

Với bearer access token, cách truyền tiêu chuẩn thường dùng là HTTP `Authorization` header:

```http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
```

Header không tự động an toàn nếu hệ thống ghi toàn bộ request headers. Cần cấu hình redaction cho `Authorization`, không đưa bearer token vào log, trace, analytics hoặc error report. Kết hợp HTTPS và xác minh token theo issuer, audience, thời hạn, loại token và quyền.

[RFC 6750, mục 2.1](https://www.rfc-editor.org/rfc/rfc6750#section-2.1) mô tả phương thức Authorization header và đây là phương thức nên ưu tiên khi có thể.

### Cookie bảo mật cho phiên trình duyệt

Trong ứng dụng web, một lựa chọn là dùng cookie phiên được cấu hình phù hợp thay vì để JavaScript tự gắn bearer token vào URL. Các thuộc tính thường cần cân nhắc:

- `Secure`: chỉ gửi cookie qua HTTPS.
- `HttpOnly`: JavaScript phía trang không đọc trực tiếp được cookie.
- `SameSite`: hạn chế một số request cross-site mang cookie tự động.
- `Path` và `Domain`: giới hạn phạm vi cookie cần thiết.
- Thời hạn cookie và cơ chế hết hạn/thu hồi phiên.

Cookie được trình duyệt tự động gửi theo request nên cần đánh giá **CSRF (Cross-Site Request Forgery)**. Có thể cần CSRF token, kiểm tra `Origin`/`Referer`, SameSite phù hợp và các biện pháp bảo vệ bổ sung theo kiến trúc.

`HttpOnly` giảm khả năng đọc cookie bằng JavaScript nhưng không ngăn mọi kiểu tấn công XSS thực hiện hành động thay mặt người dùng trong phiên đang mở. Cookie cũng không loại bỏ nhu cầu quản lý phiên và thu hồi.

### Request body chỉ là lựa chọn hạn chế trong trường hợp đặc biệt

Một số giao thức cho phép gửi access token trong request body theo điều kiện cụ thể. RFC 6750 mô tả phương thức form-encoded body ở mục 2.2 và giới hạn việc sử dụng; đây không phải lý do để tùy ý đặt token trong body của mọi request.

Nếu buộc phải dùng body theo một giao thức đã định nghĩa:

- Chỉ dùng HTTP method có ngữ nghĩa request body phù hợp; không dùng GET.
- Dùng đúng content type và quy tắc giao thức.
- Không ghi body chứa token vào application log, proxy log hoặc telemetry.
- Vẫn dùng HTTPS và xác minh token đầy đủ.

Đối với tích hợp API thông thường, Authorization header vẫn là lựa chọn ưu tiên.

## 10. Redirect OAuth: dùng authorization code thay vì đưa access token vào URL

Một số luồng OAuth cần trình duyệt chuyển hướng qua authorization server rồi quay lại ứng dụng. Redirect URI có thể mang một authorization code, nhưng code này khác access token:

- Authorization code là credential tạm thời, thời hạn ngắn và chỉ dùng một lần.
- Client đổi code tại token endpoint qua back-channel để nhận access token.
- Code cần được ràng buộc với client và redirect URI; public client nên dùng PKCE theo profile OAuth áp dụng.
- Client phải xác minh `state` để liên kết callback với yêu cầu đã khởi tạo và chống CSRF; áp dụng thêm biện pháp nhận diện authorization server/redirect URI theo profile để chống mix-up, đồng thời dùng `nonce` khi OpenID Connect yêu cầu.

Ví dụ callback có code:

```text
https://client.example.com/callback?code=SplxlOBeZQQYbYS6WxSbIA&state=af0ifjsldkj
```

Authorization code trong URL vẫn là dữ liệu nhạy cảm và có thể xuất hiện trong browser history hoặc log. Cần giữ code ngắn hạn, single-use, bảo vệ bằng PKCE, tránh tài nguyên bên thứ ba trên callback page, hạn chế referrer và xử lý URL callback an toàn. Khi phù hợp, có thể sử dụng response mode `form_post` để tránh đưa response parameters vào URL.

Không nhầm cơ chế này với việc đặt **access token hoặc JWT bearer token** vào query string. [RFC 9700, mục 4.3](https://www.rfc-editor.org/rfc/rfc9700#section-4.3) phân tích rủi ro authorization code và access token trong browser history; mục 4.3.2 yêu cầu client không truyền access token trong URI query parameter.

## 11. Trường hợp link-based token không thể tránh hoàn toàn

Một số nghiệp vụ có chủ đích dùng link gửi qua email hoặc tin nhắn, ví dụ xác nhận email, đặt lại mật khẩu hoặc chia sẻ tài liệu. Đây là một mô hình capability link: người có URL có thể thực hiện một hành động nhất định.

Nếu nghiệp vụ thực sự cần link như vậy, không nên tái sử dụng access token JWT dài hạn. Có thể thiết kế một mã ngẫu nhiên, phạm vi hẹp, một lần dùng và thời hạn ngắn, với các kiểm soát:

1. Mã chỉ cho phép đúng một hành động và đúng một tài nguyên.
2. Mã có entropy đủ lớn, được sinh bằng bộ sinh số ngẫu nhiên mật mã.
3. Server lưu trạng thái mã (hoặc hash của mã) để có thể thu hồi và đánh dấu đã sử dụng.
4. Mã hết hạn nhanh và chỉ được tiêu thụ một lần theo thao tác nguyên tử.
5. Link chỉ dùng HTTPS và host được cấu hình cố định; không tạo redirect tùy ý từ query parameter.
6. Trang landing tránh tải tài nguyên bên thứ ba, đặt `Referrer-Policy: no-referrer` và hạn chế logging.
7. Sau khi xác thực mã, đổi sang phiên hoặc credential phù hợp qua request tiếp theo và loại mã khỏi thanh địa chỉ bằng điều hướng sạch.
8. Chống link scanner tiêu thụ mã ngoài ý muốn; ví dụ hiển thị bước xác nhận rõ ràng và chỉ thực hiện hành động thay đổi trạng thái sau thao tác người dùng bằng POST.
9. Giới hạn số lần thử và ghi nhận sự kiện sử dụng bất thường.

Mã trong link vẫn có thể bị lộ; các kiểm soát này giới hạn hậu quả và thời gian sử dụng. Đây là thiết kế riêng cho capability link, không phải lý do để dùng access token JWT như một URL chia sẻ.

## 12. Các biện pháp bổ sung nếu URL nhạy cảm đã xuất hiện

Không đặt token trong URL là biện pháp chính. Các biện pháp dưới đây giúp giảm rủi ro trong trường hợp hệ thống có callback hoặc link nhạy cảm hợp lệ:

- **Referrer Policy:** dùng `no-referrer` trên trang xử lý credential khi phù hợp.
- **Cache-Control:** đặt `no-store` cho response nhạy cảm để ngăn cache lưu response theo chính sách HTTP; lưu ý nó không xóa browser history hoặc access log.
- **Không tải bên thứ ba:** tránh analytics, tracking pixel, script hoặc ảnh không cần thiết.
- **Redact logs:** loại bỏ query parameter nhạy cảm và che header Authorization trước khi log hoặc gửi telemetry.
- **Redirect sạch:** sau khi xử lý callback, điều hướng sang URL không chứa code/token; không giữ query nhạy cảm trong địa chỉ hiển thị lâu hơn cần thiết.
- **Hạn chế quyền đọc log:** giới hạn người và hệ thống được truy cập log có thể chứa URL nhạy cảm.
- **Retention:** đặt thời hạn lưu log hợp lý và quy trình xóa/ẩn dữ liệu theo chính sách.

`Cache-Control: no-store` là một biện pháp hạn chế cache, không phải biện pháp bảo vệ toàn diện. RFC 6750 có khuyến nghị cache directive khi buộc phải dùng query token, nhưng RFC 9700 hiện yêu cầu client không truyền access token theo cách đó. Không dùng `no-store` để hợp thức hóa việc đặt bearer token trong URL.

## 13. Nếu JWT đã bị lộ trong URL thì cần làm gì?

Hãy xử lý URL chứa bearer token như một credential có khả năng đã bị lộ. Không chỉ xóa URL khỏi thanh địa chỉ rồi xem sự cố đã kết thúc.

Quy trình ứng phó tham khảo:

1. **Ngăn sử dụng tiếp:** thu hồi token cụ thể bằng denylist/introspection hoặc cơ chế thu hồi phù hợp; nếu không thể thu hồi token tự chứa ngay lập tức, giảm thời hạn chấp nhận theo chính sách và xử lý phiên liên quan.
2. **Xử lý credential liên quan:** nếu refresh token, session cookie hoặc credential khác cũng có thể bị lộ, thu hồi/rotate chúng theo quy trình.
3. **Xác định phạm vi:** kiểm tra URL đã xuất hiện trong browser history, email/chat, proxy/CDN, access log, analytics, error tracker và hệ thống hỗ trợ nào.
4. **Giảm truy cập:** hạn chế quyền đọc log và kho dữ liệu chứa URL; redaction hoặc xóa bản sao theo quy trình lưu trữ và điều tra.
5. **Kiểm tra sử dụng bất thường:** tìm request dùng token từ nguồn, thiết bị, địa chỉ mạng hoặc thời điểm không mong đợi.
6. **Khắc phục luồng:** chuyển token sang Authorization header hoặc cơ chế cookie/session phù hợp; loại credential khỏi URL và các log/telemetry.
7. **Đánh giá lại:** kiểm thử để xác nhận URL không còn chứa token và các hệ thống ghi log đã che dữ liệu nhạy cảm.

Không thể bảo đảm xóa hết mọi bản sao URL đã được gửi hoặc đồng bộ. Vì vậy, thu hồi credential và điều tra nơi token đã xuất hiện là các bước quan trọng.

## 14. Ví dụ so sánh cách truyền

| Cách truyền | Đánh giá | Lý do |
| --- | --- | --- |
| `Authorization: Bearer <JWT>` qua HTTPS | Ưu tiên | Không đặt credential trong URL; cần redaction header ở log |
| Cookie phiên `Secure; HttpOnly; SameSite=...` | Có thể phù hợp với ứng dụng trình duyệt | Không lộ trong URL; cần CSRF protection và quản lý phiên |
| JWT trong query string | Không dùng cho bearer access token | URL dễ xuất hiện trong history, log, referrer và bản sao chia sẻ |
| JWT trong path | Không dùng | Path cũng nằm trong request target và thường được ghi nhận |
| JWT trong fragment | Không dùng | Có thể nằm trong browser history và được JavaScript đọc; không phải nơi lưu bí mật |
| JWT trong body theo giao thức cho phép | Ngoại lệ có giới hạn | Cần method/content type đúng và kiểm soát logging; Authorization header vẫn ưu tiên |
| Authorization code ngắn hạn trong OAuth redirect | Luồng giao thức được định nghĩa, nhưng vẫn cần bảo vệ | Code single-use, client/redirect-bound và nên dùng PKCE cho public clients |
| Mã capability một lần trong link nghiệp vụ | Chỉ khi nghiệp vụ cần link | Phải có scope hẹp, entropy cao, TTL ngắn, single-use và trạng thái server-side |

## 15. Checklist thiết kế và kiểm thử

### Checklist thiết kế

- [ ] Không đặt bearer JWT/access token trong query string.
- [ ] Không đặt token trong path segment hoặc fragment.
- [ ] Không tạo link chia sẻ chứa access token hoặc JWT phiên dài hạn.
- [ ] Ưu tiên `Authorization: Bearer` qua HTTPS và redaction header trong log.
- [ ] Nếu dùng cookie, cấu hình `Secure`, `HttpOnly`, `SameSite` và CSRF protection phù hợp.
- [ ] Nếu dùng OAuth redirect, dùng authorization code flow và PKCE theo profile; không đưa access token vào URI.
- [ ] Kiểm soát `Referrer-Policy`, `Cache-Control`, third-party resources và redirect callback.
- [ ] Redact URL query/path nhạy cảm khỏi proxy, CDN, application log và telemetry.
- [ ] Nếu bắt buộc dùng capability link, dùng mã riêng, single-use, TTL ngắn, scope hẹp và trạng thái server-side.
- [ ] Có quy trình thu hồi và xử lý khi URL chứa credential bị lộ.

### Kịch bản kiểm thử

| Trường hợp | Kỳ vọng | Mục tiêu |
| --- | --- | --- |
| Request mang JWT trong Authorization header | Xác minh theo chính sách và không ghi token vào log | Phương thức truyền ưu tiên |
| Request có `access_token` trong query string | Bị từ chối theo chính sách API | Ngăn URI bearer token |
| JWT xuất hiện trong path | Bị từ chối hoặc route không hỗ trợ kiểu truyền này | Không chuyển token sang path |
| JWT xuất hiện trong fragment | Ứng dụng không dùng fragment làm credential transport | Không dựa vào client-side URL secret |
| Log ở CDN/proxy/API gateway | Không chứa token hoặc đã redact theo quy tắc | Kiểm tra mọi tầng logging |
| Analytics/error reporting | Không thu thập URL chứa credential | Kiểm tra telemetry |
| Trang callback tải tài nguyên bên thứ ba | Không gửi URL nhạy cảm qua Referer; tốt nhất không tải tài nguyên không cần thiết | Referrer leakage |
| URL được gửi vào chat/email có preview | Không chứa access token; link capability có kiểm soát scanner | Link preview/scanner |
| URL có bearer token bị sao chép sang thiết bị khác | Coi token có khả năng bị lộ; thu hồi hoặc ràng buộc lại credential và kiểm tra việc sử dụng | Bearer credential exposure |
| OAuth callback nhận authorization code | Code ngắn hạn, single-use, PKCE/state được xác minh và code được xử lý an toàn | Redirect flow |
| Capability link được mở hai lần đồng thời | Chỉ một lần tiêu thụ thành công | Atomic single-use |
| Response chứa nội dung nhạy cảm | Cache policy phù hợp; không coi no-store là biện pháp duy nhất | Cache behavior |
| Token bị lộ đã được thu hồi | Request tiếp theo bị từ chối ở mọi verifier cần áp dụng thu hồi | Incident response |

## 16. Nguyên tắc cần ghi nhớ

1. Bearer JWT là credential: ai nắm giữ token có thể sử dụng token trong phạm vi được cấp.
2. URL thường xuất hiện trong browser history, access log, proxy/CDN, telemetry, referrer và các bản sao được chia sẻ.
3. HTTPS bảo vệ đường truyền nhưng không ngăn endpoint hoặc hệ thống trung gian ghi lại URL.
4. Query string, path và fragment có cách truyền khác nhau nhưng đều không phải nơi lưu bearer token.
5. Với OAuth access token, RFC 9700 yêu cầu không truyền token trong URI query parameter; RFC 6750 đã cảnh báo nguy cơ log URL.
6. Ưu tiên Authorization header qua HTTPS; nếu dùng cookie cần cấu hình an toàn và bảo vệ CSRF.
7. Authorization code trong redirect khác access token nhưng vẫn nhạy cảm; cần single-use, thời hạn ngắn, ràng buộc client và PKCE theo profile.
8. Capability link là ngoại lệ nghiệp vụ cần thiết kế riêng bằng mã một lần, scope hẹp, TTL ngắn và trạng thái server-side.
9. Referrer Policy, Cache-Control và log redaction chỉ giảm một số kênh rò rỉ; không làm URL chứa token trở nên an toàn.
10. Nếu URL chứa JWT đã bị lộ, hãy thu hồi credential, kiểm tra phạm vi rò rỉ và khắc phục mọi tầng logging/telemetry.

### Tài liệu chuẩn tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage, mục 2.1–2.3 và 5](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer token qua header/body, rủi ro URI query parameter và khuyến nghị không đặt token trong page URL.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security, mục 4.3.1–4.3.2](https://www.rfc-editor.org/rfc/rfc9700#section-4.3): credential leakage qua browser history và yêu cầu không truyền access token trong URI query parameter.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code grant, redirect URI và token endpoint.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636): ràng buộc authorization code với client bằng code verifier/challenge.
- [W3C Referrer Policy](https://www.w3.org/TR/referrer-policy/): kiểm soát thông tin gửi trong HTTP `Referer`.
- [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url): các vị trí URL có thể làm lộ dữ liệu nhạy cảm.

**Kết luận:** Không đặt bearer JWT trong URL vì địa chỉ có thể bị lưu, ghi log, chuyển tiếp và mở bởi nhiều thành phần ngoài dự kiến. Hãy truyền token qua Authorization header hoặc cơ chế phiên phù hợp; với redirect OAuth, dùng authorization code được bảo vệ theo giao thức; với link nghiệp vụ bắt buộc, dùng capability code riêng có thời hạn ngắn và chỉ dùng một lần.
