# CSRF protection

## 1. Request có danh tính hợp lệ chưa chứng minh ý định hợp lệ

Một người dùng đã đăng nhập có thể mở thêm một trang không đáng tin trong cùng trình duyệt. Trang đó tìm cách khiến trình duyệt gửi request tới ứng dụng mà người dùng đang có phiên. Nếu credential được trình duyệt tự đính kèm và server không kiểm tra đủ ngữ cảnh, request có thể được thực hiện dưới danh tính nạn nhân dù người đó không chủ định thực hiện thao tác.

**Cross-Site Request Forgery**, viết tắt là **CSRF**, khai thác sự khác biệt giữa hai điều:

- Request mang bằng chứng xác thực mà server chấp nhận.
- Request xuất phát từ một luồng tương tác được ứng dụng cho phép.

Bảo vệ CSRF giúp phân biệt hai điều này tại ranh giới request. Nó không thay thế xác thực, phân quyền hay kiểm tra nghiệp vụ.

Trong module yêu cầu bảo mật, mục tiêu cần được diễn đạt cụ thể:

> Những thao tác có thể được gọi bằng credential trình duyệt tự gửi phải có cơ chế kiểm tra chống giả mạo phù hợp. Request không đáp ứng chính sách phải bị từ chối trước khi tạo tác dụng nghiệp vụ.

Để nghiệm thu, cần biết endpoint nào thuộc phạm vi, cơ chế nào được chọn, client hợp lệ lấy và gửi bằng chứng ra sao, cùng hành vi khi bằng chứng thiếu hoặc không hợp lệ.

## 2. Tình huống minh họa

Giả sử `https://account.example.test` cho phép đổi email qua một form và dùng session cookie để xác thực. Trong điều kiện cookie và môi trường trình duyệt cho phép credential được gửi ở ngữ cảnh đang xét, một request bị gây ra từ nơi khác có thể có hình dạng:

```http
POST /api/profile/email HTTP/1.1
Host: account.example.test
Origin: https://untrusted.other.test
Cookie: __Host-session=<session-placeholder>
Content-Type: application/x-www-form-urlencoded

email=unwanted-recipient%40example.test
```

Tên miền, email và credential trong ví dụ đều là dữ liệu minh họa. Không được hiểu rằng cookie luôn được gửi trong mọi request cross-site; điều đó còn phụ thuộc chính sách cookie và trình duyệt.

Điểm cần phân tích là: nếu server chỉ kiểm tra session cookie rồi thay email, nó chưa có bằng chứng rằng thao tác đến từ luồng đổi email hợp lệ.

Trang gây ra request không nhất thiết phải đọc được response. Nếu email đã đổi, tác dụng mong muốn của bên giả mạo có thể đã xảy ra. Vì vậy, việc JavaScript ở trang khác không đọc được body không đủ chứng minh thao tác được bảo vệ.

Với thao tác nhạy cảm như đổi email, hệ thống còn có thể cần xác thực lại hoặc xác nhận qua một kênh riêng. Đó là yêu cầu bổ sung theo rủi ro, không phải lý do để bỏ kiểm soát CSRF của request.

## 3. Xác định phạm vi theo cách credential được gửi

Không nên quyết định bật hay tắt CSRF chỉ từ các nhãn “REST”, “JSON”, “JWT” hoặc “stateless”. Câu hỏi trực tiếp hơn là trình duyệt có thể tự mang quyền của người dùng vào request do một ngữ cảnh khác gây ra hay không.

[Tài liệu tổng quan CSRF của Spring Security](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html) giải thích rằng ứng dụng stateless dùng cookie xác thực vẫn có thể chịu CSRF; HTTP authentication do trình duyệt tự gửi cũng cần được xét. Tài liệu này còn lưu ý login CSRF: nạn nhân có thể bị đưa vào một phiên thuộc tài khoản khác, nên không chỉ các endpoint đã đăng nhập mới cần phân tích.

Một inventory cho dự án có thể như sau:

| Luồng hoặc endpoint | Cách mang bằng chứng | Câu hỏi cần trả lời |
| --- | --- | --- |
| Form web dùng session | Cookie theo chính sách trình duyệt | Kiểm tra CSRF của form nằm ở đâu? |
| API dùng JWT trong cookie | Cookie vẫn được tự gửi theo ngữ cảnh | Chính sách chống request giả mạo là gì? |
| API chỉ nhận bearer token do ứng dụng tự gắn vào header | Không dựa vào cookie tự gửi cho đường truy cập đó | Có cookie fallback hoặc đường xác thực khác không? |
| Endpoint refresh | Có thể dựa vào refresh cookie | Ai có thể gây request làm mới và response được công khai thế nào? |
| Đăng nhập và đăng xuất | Tạo, đổi hoặc hủy ngữ cảnh phiên | Làm sao tránh thao tác bị ép từ một nơi không được phép? |
| Webhook từ server đối tác | Chữ ký hoặc credential của tích hợp | Có cơ chế xác thực riêng, thay vì dùng phiên trình duyệt không? |
| Endpoint chỉ dành cho SDK | Credential theo hợp đồng SDK | Có thực sự tách khỏi các đường dùng cookie của trình duyệt không? |

Các hàng không phải kết luận miễn trừ tự động. Chúng là đầu vào để xác định threat model và chính sách cho từng đường gọi.

### Trường hợp API chỉ dùng Authorization header

Nếu một endpoint thực sự chỉ chấp nhận access token mà client hợp lệ chủ động gắn vào Authorization header, không có credential tự gửi thay thế, mô hình CSRF truyền thống khác với một endpoint nhận session cookie.

Tuy nhiên, quyết định giới hạn phạm vi bảo vệ phải được chứng minh bằng những đường xác thực thực tế. Không được tắt toàn bộ bảo vệ cho ứng dụng chỉ vì một nhóm endpoint có tính chất này, trong khi login, refresh hoặc API khác vẫn dựa vào cookie.

## 4. Origin và site là hai ranh giới khác nhau

Origin phân biệt scheme, host và port. Site dùng trong chính sách cookie là một ranh giới khác, có xét scheme và domain đăng ký được theo quy tắc trình duyệt.

Ví dụ thiết kế:

| Hai địa chỉ | Quan hệ cần lưu ý |
| --- | --- |
| `https://account.example.test` và chính địa chỉ đó | Cùng origin |
| `https://account.example.test` và `https://files.example.test` | Khác origin nhưng có thể cùng site |
| `https://account.example.test` và `https://account.example.test:8443` | Port khác tạo origin khác |
| `https://account.example.test` và `https://untrusted.other.test` | Khác site trong ví dụ |

Nếu một subdomain chứa nội dung người dùng hoặc do bên thứ ba quản lý, không nên tự coi mọi nguồn cùng site là đáng tin tương đương ứng dụng tài khoản.

Trong ma trận yêu cầu, cần có một hàng dành cho **nguồn khác origin nhưng cùng site**. Nếu chỉ thử với một domain hoàn toàn khác, đội có thể bỏ sót rủi ro từ một nhánh domain mà SameSite không phân biệt theo cách mong muốn.

## 5. HTTP method phải phản ánh đúng tác dụng

Trước khi chọn token hoặc header, cần loại bỏ những đường thay đổi trạng thái được ngụy trang thành truy cập đọc.

Ví dụ thiết kế không phù hợp:

```text
GET /api/profile/delete?confirm=true
GET /api/session/logout
GET /api/preferences/enable-sharing
```

Một mục tiêu của dự án nên là: GET, HEAD và OPTIONS không thực hiện các thay đổi nghiệp vụ nhạy cảm như xóa tài khoản, đổi email hoặc thay quyền. Các tác dụng kỹ thuật phục vụ vận hành cần được phân biệt với thao tác nghiệp vụ mà người dùng phải chủ định thực hiện.

Không dùng tên endpoint hoặc việc có một tham số `confirm=true` làm bằng chứng ý định. Một trang khác có thể tạo URL chứa chính tham số đó.

Nếu framework hỗ trợ method override, alias hoặc route cũ, chính sách phải xét method và thao tác hiệu lực. Không để một request được kiểm tra như thao tác đọc nhưng sau đó lại được chuyển thành thao tác ghi.

Đăng xuất cũng nên được mô hình hóa như một thay đổi phiên có chủ đích, với phương thức và kiểm soát phù hợp, thay vì một liên kết GET được dùng như ngoại lệ vĩnh viễn.

## 6. Các cơ chế token và thuộc tính cần bảo vệ

Hai pattern thường gặp là synchronizer token và signed double-submit cookie. Pattern đầu kiểm tra giá trị gắn với ngữ cảnh phiên ở server; pattern sau cần ràng buộc có kiểm chứng với phiên, không chỉ so sánh hai chuỗi tùy ý. [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) ưu tiên cơ chế framework đã có, cảnh báo cookie injection với double-submit đơn giản và yêu cầu không dùng cookie tự gửi làm bằng chứng duy nhất.

Trong một thiết kế dùng token, hợp đồng của dự án cần chỉ rõ:

- Token được tạo bằng cơ chế ngẫu nhiên hoặc mật mã phù hợp của thành phần được chọn.
- Token được ràng buộc với ngữ cảnh nào và được server kiểm tra bằng cách nào.
- Client nhận token từ đâu, sau điều kiện truy cập nào.
- Client trình token ở header hay trường form nào.
- Token cũ được xử lý ra sao khi phiên thay đổi.
- Có giới hạn kích thước, định dạng và hành vi lỗi thế nào.

### Synchronizer token trong thiết kế phiên

Một thiết kế minh họa có thể lưu giá trị kiểm chứng ở phiên server và đưa giá trị dành cho client vào trang hoặc response bootstrap. Client gửi lại qua một vị trí được công bố khi thực hiện thao tác ghi.

Điều cần nghiệm thu không chỉ là hai giá trị giống nhau. Hệ thống phải xác định đúng phiên cần kiểm tra, không nhận token của một phiên khác và không để giá trị do bên gọi tự chọn trở thành giá trị được kỳ vọng.

Quy tắc nhiều tab, nút Back và request đồng thời cần được định nghĩa. Nếu dự án chọn token dùng một lần, nó phải thiết kế hành vi khi nhiều thao tác hợp lệ tranh chấp token. Không nên thêm cơ chế dùng một lần chỉ vì cho rằng mọi token CSRF đều phải là token chống phát lại cho từng nghiệp vụ.

### Signed double-submit trong thiết kế không lưu token phiên riêng

Nếu chọn pattern có chữ ký, dự án cần dùng implementation được kiểm chứng thay vì tự ghép một hàm băm từ email hoặc user ID. Hợp đồng phải giải thích dữ liệu nào làm ràng buộc phiên, cách quản lý khóa và cách xác minh giá trị được trình trong request.

Không đưa session ID bí mật dạng rõ vào token công khai. Thông tin cần thiết để client gửi request không nên mở thêm một đường làm lộ bằng chứng xác thực.

Tên “double-submit” không đủ để kết luận an toàn. Bằng chứng kiểm chứng phải bao gồm trường hợp cookie không đúng nguồn, token của phiên khác và dữ liệu bị thay đổi.

### Token không phải credential xác thực người dùng

Một request có token CSRF hợp lệ vẫn cần xác thực, phân quyền và kiểm tra dữ liệu. Token không cấp quyền xem tài nguyên, không xác nhận số tiền hoặc địa chỉ nhận là đúng và không chặn người dùng tự động hóa các thao tác mà họ vốn được phép gọi.

## 7. Phân phối và bảo vệ token

Giả sử dự án chọn endpoint bootstrap cùng origin:

```http
GET /api/csrf HTTP/1.1
Host: account.example.test
Accept: application/json
```

Một response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{"token":"<csrf-token-placeholder>"}
```

Đây là một hợp đồng giả định cho ví dụ, không phải endpoint mặc định bắt buộc của mọi framework.

Yêu cầu liên quan cần bao gồm:

1. Giá trị trả về thuộc đúng ngữ cảnh client đang sử dụng.
2. Response không bị cache dùng chung và phát lại sai người.
3. Không cho origin không tin cậy đọc token bằng một cấu hình chia sẻ response quá rộng.
4. Không đặt token trong query string, đường dẫn hoặc link có thể đi vào lịch sử và log ngoài dự kiến.
5. Không ghi nguyên token hoặc session cookie vào log để chẩn đoán.
6. Nếu nhúng token vào HTML, sử dụng cơ chế mã hóa đầu ra đúng ngữ cảnh.

Trong một mô hình cookie-to-header, cookie chứa giá trị mà JavaScript cần đọc có thể có chính sách khác cookie xác thực. Không được vì nhu cầu đọc token mà bỏ HttpOnly của session cookie.

Cũng không nên cài token như header mặc định cho mọi request mạng của trang. Chỉ gắn nó vào các URL và thao tác thuộc phạm vi tin cậy đã định. Một thư viện dùng chung gửi token cho dịch vụ bên ngoài có thể làm mất ranh giới bảo vệ mà thiết kế ban đầu giả định.

## 8. SameSite là một lớp chính sách cookie

Theo [MDN về Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie), SameSite điều khiển việc gửi cookie theo ngữ cảnh site: Strict chặt hơn, Lax có trường hợp điều hướng cấp cao với method an toàn, còn None cần Secure. Chính sách Lax được áp dụng mặc định ở một số trình duyệt có thể khác trường hợp khai báo tường minh. `HttpOnly` hạn chế JavaScript đọc cookie, không phải bằng chứng request có ý định hợp lệ; tiền tố `__Host-` có ràng buộc riêng về Secure, Path và Domain.

Ví dụ cookie phiên của một thiết kế giả định:

```http
Set-Cookie: __Host-session=<session-placeholder>; Secure; HttpOnly; Path=/; SameSite=Lax
```

Việc chọn Lax trong ví dụ phải được đánh giá cùng luồng đăng nhập, điều hướng và tích hợp thực tế. Không sao chép một giá trị mà chưa biết ứng dụng có nhúng cross-site hoặc luồng liên kết tài khoản hay không.

Đối với hệ thống minh họa, một yêu cầu bổ sung là không dùng SameSite làm lý do bỏ qua request từ subdomain khác mà tổ chức chưa xác nhận tin cậy. Same-site không có nghĩa mọi ứng dụng ở các origin liên quan đều có cùng mức bảo vệ.

Một cookie chỉ được gửi tới host đích cũng không chứng minh trang khởi phát request thuộc host đó. Phạm vi nơi nhận cookie và nguồn gây ra request là hai câu hỏi khác nhau.

Nếu ứng dụng cần credential trong một luồng cross-site hợp lệ, phải thiết kế đầy đủ kiểm soát request, chia sẻ response và khả năng tương thích client. Không nên giải quyết bằng một ngoại lệ rộng cho mọi origin hoặc mọi request thiếu token.

## 9. Kiểm tra Origin và tín hiệu nguồn request

Header Origin mang thông tin scheme, hostname và port của nguồn gây request; nó có thể vắng mặt hoặc có giá trị `null` trong những hoàn cảnh được mô tả tại [MDN về Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin). Vì vậy, chính sách phải định nghĩa cả các trường hợp này, thay vì mặc định chúng luôn đáng tin hoặc luôn tương đương cùng origin.

Một chính sách của dự án có thể dùng allowlist origin chính xác cho những endpoint thay đổi trạng thái dành cho trình duyệt. Việc so sánh phải dựa trên thành phần URL đã được phân tích và chuẩn hóa theo implementation phù hợp, không dùng phép tìm chuỗi như “có chứa example.test”.

Ví dụ các nguồn cần được phân biệt:

```text
https://account.example.test
https://account.example.test:8443
https://account.example.test.untrusted.other.test
https://files.example.test
null
```

Không nguồn nào trong danh sách tự được cho phép chỉ vì có một phần tên giống nguồn tin cậy.

Nếu dùng Referer làm fallback, chỉ lấy phần origin phù hợp cho quyết định và xét khả năng header bị lược bỏ theo chính sách riêng tư. Không ghi URL Referer đầy đủ một cách mặc định nếu nó có thể chứa dữ liệu nhạy cảm.

### Xác định origin đích sau proxy

Một backend phía sau reverse proxy cần biết origin công khai nào là đích hợp lệ. Danh sách này nên đến từ cấu hình được kiểm soát hoặc cơ chế proxy tin cậy, không từ header mà client Internet có thể tự đặt.

Hệ thống nhiều tenant có thể cần nhiều origin hợp lệ. Quy tắc ánh xạ phải gắn với tenant và chức năng, không biến thành việc chấp nhận mọi subdomain chỉ vì cùng hậu tố.

### Origin không phải chứng chỉ danh tính cho mọi client

Việc trình duyệt hạn chế JavaScript tự đặt một header không làm header đó thành credential cho client máy chủ. Một chương trình HTTP ngoài trình duyệt có thể tạo request riêng. Xác thực và phân quyền vẫn cần hoạt động độc lập.

## 10. Fetch Metadata và chính sách tương thích

[MDN về Sec-Fetch-Site](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site) mô tả các giá trị `same-origin`, `same-site`, `cross-site` và `none`. Header cho server biết quan hệ giữa nguồn khởi phát và tài nguyên đích; nó không phải một danh tính người dùng. `none` có thể gắn với thao tác do người dùng khởi phát như nhập URL, không có nghĩa là một origin được cấp quyền.

Trong một thiết kế có sử dụng Fetch Metadata, cần chốt:

- Endpoint và method nào áp dụng chính sách.
- Hành vi với nguồn cross-site, cùng site nhưng không tin cậy và các điều hướng hợp lệ.
- Tín hiệu bổ sung nào cần để phân biệt loại request.
- Cách xử lý client không có header hoặc giá trị không được hiểu.
- Cách đo tương thích trước khi bật chế độ chặn.

Không miễn mọi request thiếu Fetch Metadata chỉ để hỗ trợ một SDK. Nếu SDK có cơ chế xác thực khác, hãy định nghĩa đường gọi và chính sách riêng. Một sự vắng mặt trong request không tự chứng minh request đến từ SDK đó.

Cũng không nên cho phép toàn bộ `same-site` nếu cây subdomain có nội dung người dùng, môi trường preview hoặc ứng dụng do bên ngoài quản lý. Quyết định tin cậy phải phản ánh kiến trúc thật.

## 11. CORS, Content-Type và custom header

[MDN về CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) phân biệt request cần preflight với những request có thể được gửi mà không có bước đó, chẳng hạn một số form submission. CORS còn kiểm soát khả năng script đọc response. Vì thế, một lỗi CORS ở client không tự chứng minh server chưa xử lý thao tác.

Trong một profile API giả định, dự án có thể yêu cầu:

```text
POST /api/profile/email
  Cookie xác thực hợp lệ
  Content-Type: application/json
  X-CSRF-TOKEN: giá trị hợp lệ theo chính sách phiên
  Nguồn request đáp ứng chính sách origin
```

Khi đã chọn profile này, server phải thực thi nó. Không chấp nhận âm thầm `text/plain` hoặc form body như một lối tương thích rồi bỏ qua những điều kiện đã công bố.

Một kiến trúc cũng có thể chọn cơ chế custom header và origin policy phù hợp thay cho token ở một số đường API, nhưng đó phải là một thiết kế đầy đủ, có kiểm tra CORS và mọi nguồn được phép. Việc chỉ thêm một header vào client mà server không yêu cầu nó không tạo ra kiểm soát.

Nếu một origin không tin cậy được cho phép gửi request có credential và header nhạy cảm hoặc đọc response cấp token, những giả định của cơ chế bảo vệ có thể bị phá vỡ. Không giải quyết lỗi tích hợp bằng cách phản chiếu tùy ý Origin vào cấu hình cho phép.

OPTIONS phục vụ preflight không được thực hiện thao tác nghiệp vụ. Việc một preflight được chấp nhận không thay cho xác thực, kiểm tra CSRF và phân quyền ở request thực sự.

## 12. Ví dụ client cùng origin theo hợp đồng đã chọn

Ví dụ sau minh họa một client nhận token từ endpoint bootstrap giả định rồi đổi email. Nó không phải implementation mặc định của một framework và không thay các kiểm tra phía server.

```javascript
async function requestEmailChange(newEmail) {
  const bootstrap = await fetch("/api/csrf", {
    method: "GET",
    credentials: "same-origin",
    redirect: "error",
    cache: "no-store",
    headers: { Accept: "application/json" }
  });

  if (!bootstrap.ok) {
    throw new Error("Không thể chuẩn bị yêu cầu an toàn.");
  }

  const csrf = await bootstrap.json();
  if (typeof csrf.token !== "string" || csrf.token.length === 0) {
    throw new Error("Phản hồi chuẩn bị không đúng hợp đồng.");
  }

  const response = await fetch("/api/profile/email", {
    method: "POST",
    credentials: "same-origin",
    redirect: "error",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRF-TOKEN": csrf.token
    },
    body: JSON.stringify({ email: newEmail })
  });

  if (!response.ok) {
    throw new Error("Yêu cầu đổi email chưa được xác nhận thành công.");
  }

  return response;
}
```

Những quyết định cần nhận ra trong ví dụ:

- URL là đường dẫn cùng origin được lập trình xác định, không lấy địa chỉ đích tùy ý từ query string.
- Token chỉ được gắn vào request thuộc chức năng đã chọn.
- Client không tự tạo token rồi coi đó là bằng chứng hợp lệ.
- Không có cơ chế tự lặp vô hạn khi server từ chối.
- Lỗi hoặc mất response không được dùng làm bằng chứng chắc chắn rằng thao tác chưa xảy ra.

Trong ứng dụng thực, giao diện còn cần xử lý lỗi theo mã công khai, trạng thái phiên và luồng xác nhận đổi email. Kiểm tra định dạng email và quyết định có được đổi hay không vẫn thuộc server.

## 13. Pipeline phía server phải chặn trước tác dụng

Mã giả thể hiện yêu cầu xử lý:

```text
handleStateChangingBrowserRequest(request):
    enforceRequestLimitsAndSupportedRepresentation(request)
    establishAuthenticationContextAccordingToPolicy(request)

    if request requires csrf protection:
        verifySourceContextAccordingToEndpointPolicy(request)
        verifyCsrfEvidenceAccordingToSelectedMechanism(request)

    authorizeActionOnTargetResource(request)
    validateBusinessInput(request)
    executeBusinessOperation(request)
```

Thứ tự filter thực tế có thể khác giữa các framework. Thuộc tính bắt buộc cần giữ là không tạo tác dụng nghiệp vụ được bảo vệ trước khi các điều kiện an toàn liên quan đã được đáp ứng.

Một request thiếu token không được đổi email rồi mới trả 403. Tương tự, nó không được tạo job, gửi thông báo hoặc phát sự kiện nghiệp vụ trước khi bị từ chối.

### Upload và multipart

Một endpoint upload có thể cần đọc metadata hoặc xử lý luồng request. Thiết kế cần xác định nơi kiểm tra token, giới hạn tài nguyên và thời điểm một file trở thành tài nguyên nghiệp vụ được chấp nhận.

Không coi việc request cuối cùng trả lỗi là đủ nếu nội dung đã được công khai trong object storage hoặc một job xử lý đã chạy. Đối với multipart, cách trình token và thứ tự xử lý phải phù hợp với cơ chế framework đã chọn.

### Phương thức, route và filter chain

Kiểm kê phải bao gồm route cũ, alias, method override và nhiều security filter chain nếu ứng dụng có sử dụng. Chính sách đúng ở một controller không chứng minh mọi đường tới cùng thao tác đều được bảo vệ.

## 14. Tích hợp framework thay vì bỏ kiểm soát vì lỗi 403

Với ứng dụng Servlet dùng Spring Security, tài liệu chính thức mô tả cơ chế bảo vệ cho unsafe methods, các thành phần lưu/đọc token và tích hợp SPA. Một điểm khai báo minh họa là:

```java
http.csrf(Customizer.withDefaults());
```

Đây là một dòng trong cấu hình bảo mật, không phải cấu hình ứng dụng hoàn chỉnh. Chi tiết token repository, request handler và việc lấy token mới sau đăng nhập/đăng xuất phải theo phiên bản cùng kiểu client thực tế. Xem [Spring Security: CSRF cho Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

Khi một request hợp lệ nhận 403, quy trình chẩn đoán nên kiểm tra:

1. Client có nhận token cho đúng ngữ cảnh phiên hay không.
2. Tên header hoặc trường form có khớp cấu hình không.
3. Cookie phiên có được gửi theo chính sách và origin đang dùng không.
4. Token có bị cũ sau một thay đổi phiên không.
5. Proxy có loại bỏ header hoặc làm sai origin công khai không.
6. Có một filter chain hoặc route khác đang được áp dụng không.

Không dùng việc vô hiệu hóa toàn cục CSRF làm bước sửa lỗi đầu tiên cho một endpoint cookie-based. Nếu một đường gọi cần ngoại lệ, quyết định phải dựa vào threat model và có phạm vi cụ thể cùng cơ chế bảo vệ thay thế phù hợp.

## 15. Vòng đời phiên và các endpoint dễ bị bỏ sót

### Đăng nhập

Một request đăng nhập thay đổi danh tính đang gắn với trình duyệt. Cần xác định cách bảo vệ luồng trước khi có phiên người dùng chính thức, cùng cách tạo ngữ cảnh xác thực mới mà không giữ một định danh phiên do bên khác định đoạt.

Nếu chọn cơ chế phiên trước đăng nhập, hợp đồng phải mô tả việc tạo, kết thúc hoặc thay thế ngữ cảnh đó khi đăng nhập thành công. Không nhầm việc có token trước đăng nhập với việc đã xác thực người dùng.

### Đăng xuất và làm mới credential

Đăng xuất có thể hủy phiên, còn refresh có thể cấp credential mới. Cả hai cần được xét theo cơ chế request thực sự, không chỉ theo việc chúng nằm ngoài phần nghiệp vụ chính.

Không nhận refresh cookie tự gửi rồi mặc định request được chủ thể mong muốn. Cũng không gửi token mới ra ngoài qua một cấu hình CORS quá rộng.

### Phiên thay đổi, nhiều tab và timeout

Thiết kế cần có hành vi rõ khi client đang giữ token cũ, người dùng đăng nhập lại hoặc một tab khác đã đăng xuất. Client có thể cần nhận token mới hoặc quay về luồng đăng nhập theo hợp đồng.

Không tự động bỏ kiểm tra vì token hết hiệu lực. Không tự retry một thao tác nhạy cảm sau khi đổi danh tính mà chưa xác định ý định và trạng thái nghiệp vụ tương ứng.

Tùy cơ chế đã chọn, thời hạn và quy tắc invalidation có thể gắn với phiên thay vì một bộ đếm độc lập cho mỗi request. Điều cần nghiệm thu là hành vi thực sự của chính sách, không phải một giả định chung rằng mọi token đều có cùng vòng đời.

## 16. Hành vi từ chối và quan sát an toàn

Một response công khai cho kiểm tra CSRF thất bại có thể là:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{
  "code": "CSRF_CHECK_FAILED",
  "message": "Không thể xác nhận tính hợp lệ của yêu cầu.",
  "requestId": "req-demo-csrf-01"
}
```

Đây là một profile lỗi minh họa của dự án. Nó không khẳng định mọi framework mặc định có cùng body hoặc mã máy.

Yêu cầu xử lý lỗi cần bảo đảm:

- Không echo token đã nhận, token kỳ vọng, session ID hoặc body nhạy cảm.
- Không thực hiện nghiệp vụ rồi mới báo lỗi.
- Phân biệt lỗi phiên, lỗi nguồn request và lỗi cấu hình trong kênh chẩn đoán được phép.
- Dùng reason code hữu hạn và định danh đối chiếu phù hợp.
- Giới hạn độ dài header, token và dữ liệu được ghi nhận.
- Có hướng dẫn client phục hồi mà không mở một đường bỏ qua kiểm tra.

Tăng số lần lỗi có thể đến từ tấn công hoặc từ một rollout làm client gửi sai token. Quan sát cần hỗ trợ phân tích cả hai mà không biến log thành kho lưu credential.

Các chỉ số như tỷ lệ từ chối theo route template, phiên bản client và lý do có kiểm soát có thể hữu ích. Không đưa nguyên token, URL có dữ liệu nhạy cảm hoặc định danh không giới hạn vào nhãn metric.

## 17. Mẫu yêu cầu bảo mật có thể nghiệm thu

| ID | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| CSRF-01 | Có danh mục endpoint thay đổi trạng thái và cách mỗi endpoint nhận credential | Đối chiếu route, method, login, logout, refresh, upload và đường cũ |
| CSRF-02 | Mỗi endpoint trong phạm vi có cơ chế chống giả mạo được chọn và thực thi ở server | Request thiếu hoặc không đáp ứng bằng chứng bị từ chối trước tác dụng |
| CSRF-03 | Token trong profile được ràng buộc với đúng ngữ cảnh và không thể do client tùy ý định đoạt | Kiểm tra token phiên khác, token bị thay đổi và giá trị tự chọn |
| CSRF-04 | Phân phối token không lộ qua URL, log, cache dùng chung hoặc origin không tin cậy | Kiểm tra bootstrap, template, response cache và cấu hình chia sẻ dữ liệu |
| CSRF-05 | Các method đọc không thực hiện thao tác nghiệp vụ nhạy cảm | Gọi GET, HEAD, OPTIONS và kiểm tra tác dụng tại hệ thống liên quan |
| CSRF-06 | Origin và thông tin proxy được xử lý theo danh mục nguồn tin cậy | Kiểm tra nguồn gần giống, port khác, null, thiếu header và giả header chuyển tiếp |
| CSRF-07 | SameSite được khai báo và đánh giá cùng mô hình subdomain, không thay thế ngầm các điều kiện khác | Thử luồng cùng origin, cùng site khác origin và cross-site theo tập client hỗ trợ |
| CSRF-08 | Content-Type, custom header và CORS giữ đúng giả định của profile API | Thử form, text/plain, JSON, preflight và nguồn không được phép |
| CSRF-09 | Thay đổi phiên có hành vi token và phục hồi client được công bố | Kiểm tra đăng nhập lại, đăng xuất, timeout và nhiều tab |
| CSRF-10 | Mọi đường tới cùng thao tác chịu chính sách tương ứng | Kiểm tra alias, route cũ, method override và nhiều filter chain |
| CSRF-11 | Lỗi kiểm tra không lộ credential và có khả năng chẩn đoán được kiểm soát | Đối chiếu response, log và reason code bằng dữ liệu kiểm thử |
| CSRF-12 | Ngoại lệ có phạm vi cụ thể và không tạo cookie fallback không được bảo vệ | Kiểm tra trực tiếp từng cơ chế xác thực được chấp nhận của endpoint ngoại lệ |

Các yêu cầu là ví dụ cho một hệ thống web/API. Dự án phải điền cơ chế, tập client và endpoint cụ thể trước khi dùng làm tiêu chí nghiệm thu chính thức.

## 18. Kịch bản chấp nhận minh họa

### 18.1. Request hợp lệ từ luồng ứng dụng

```text
Given:
  Người dùng có ngữ cảnh phiên hợp lệ.
  Client nhận token đúng cơ chế của endpoint.
  Người dùng được phép thực hiện hành động với tài nguyên đích.

When:
  Client gửi request theo method, media type, nguồn và vị trí token đã công bố.

Then:
  Kiểm tra CSRF chấp nhận bằng chứng tương ứng.
  Request tiếp tục qua các kiểm tra quyền và nghiệp vụ còn lại.
  Token không thay thế quyết định phân quyền.
```

### 18.2. Request từ nơi không tin cậy mang cookie nhưng thiếu bằng chứng

```text
Given:
  Môi trường thử có thể tạo request từ một nguồn không tin cậy.
  Trong điều kiện đang thử, cookie xác thực được trình duyệt gửi theo chính sách.

When:
  Request thay đổi trạng thái không đáp ứng cơ chế chống giả mạo của endpoint.

Then:
  Server từ chối trước khi ghi dữ liệu, phát sự kiện hoặc tạo job.
  Không chỉ dựa vào việc trang khởi phát không đọc được response.
  Response và log không chứa credential hoặc token kỳ vọng.
```

### 18.3. Token của phiên khác

```text
Given:
  Có hai phiên kiểm thử A và B.
  Endpoint dùng profile token ràng buộc phiên.

When:
  Request mang credential của A nhưng trình token thuộc B.

Then:
  Bằng chứng không được chấp nhận cho A.
  Không thực hiện thao tác được bảo vệ.
  Hành vi không phụ thuộc việc token có định dạng trông hợp lệ hay không.
```

### 18.4. Origin cùng site nhưng ngoài phạm vi tin cậy

```text
Given:
  files.example.test chứa nội dung không tin cậy.
  account.example.test chỉ nhận thao tác tài khoản theo chính sách nguồn đã định.

When:
  Request khởi phát từ files.example.test tới thao tác được bảo vệ.

Then:
  Không tự cho phép chỉ vì quan hệ same-site.
  Quyết định dựa trên toàn bộ cơ chế và chính sách của endpoint.
```

### 18.5. Client cũ sau thay đổi phiên

```text
Given:
  Client đang giữ token từ ngữ cảnh cũ.
  Phiên đã thay đổi theo một sự kiện được chính sách quy định.

When:
  Client gửi thao tác với bằng chứng không còn được chấp nhận.

Then:
  Server từ chối theo hợp đồng.
  Client đi vào luồng phục hồi được công bố.
  Không có fallback tự bỏ kiểm tra hoặc lặp thao tác nhạy cảm vô hạn.
```

## 19. Ma trận kiểm chứng cần chuẩn bị

| Nhóm tình huống | Điều cần quan sát |
| --- | --- |
| Token hợp lệ, thiếu, rỗng, sai định dạng, bị sửa | Quyết định server và tác dụng thực tế |
| Token của phiên khác hoặc ngữ cảnh cũ | Ràng buộc phiên và chính sách invalidation |
| Same-origin, same-site khác origin, cross-site | Ranh giới tin cậy không bị giản lược sai |
| Origin thiếu, null hoặc gần giống allowlist | Hành vi fallback có kiểm soát |
| Fetch Metadata có, thiếu hoặc không phù hợp | Chính sách tương thích đúng tập client |
| Form, multipart, text/plain, JSON | Không mở một lối biểu diễn bỏ qua điều kiện |
| POST, PUT, PATCH, DELETE và method override | Toàn bộ thao tác hiệu lực thuộc phạm vi |
| GET, HEAD, OPTIONS | Không có tác dụng nghiệp vụ nhạy cảm |
| Login, logout, refresh và nhiều tab | Vòng đời token/phiên và phục hồi hợp lệ |
| CORS từ nguồn không được phép | Phân biệt gửi request, preflight và đọc response |
| Cache token hoặc thư viện gắn header toàn cục | Không phát token sai người hoặc sai đích |
| Upload và thao tác tạo job | Không có tài nguyên hoặc công việc được chấp nhận trước kiểm tra |
| Route cũ, alias và nhiều filter chain | Không còn đường thay thế với chính sách yếu hơn |

Bằng chứng nên kết hợp HTTP thực tế với trạng thái dữ liệu, hàng đợi hoặc dịch vụ phụ liên quan. Một status 403 trên màn hình chưa đủ nếu một tác dụng đã diễn ra trước đó.

Phép thử bằng HTTP client có thể kiểm tra logic server, nhưng không tự chứng minh hành vi gửi cookie, Origin, preflight hoặc SameSite của trình duyệt. Cần có môi trường trình duyệt và ngữ cảnh nguồn được xác định cho các thuộc tính ấy.

## 20. Ranh giới của kết luận bảo mật

Bảo vệ CSRF không chứng minh ứng dụng đã chống XSS. Mã chạy được trong origin tin cậy có thể sử dụng các khả năng mà origin đó được cấp; vì vậy, bảo vệ nội dung và tránh đưa dữ liệu không tin cậy thành mã thực thi vẫn là yêu cầu riêng.

Tương tự, một trang hợp lệ không nên lấy URL hoặc method tùy ý từ dữ liệu bên ngoài rồi tự gắn token để thực hiện request. Thiết kế client cần giới hạn những đích và thao tác mà nó có thể thực hiện, thay vì biến nó thành một công cụ chuyển tiếp request có quyền.

Token CSRF cũng không phải biện pháp chống mọi replay nghiệp vụ, bot hoặc lạm dụng tài khoản đã bị chiếm quyền. Những mục tiêu đó cần cơ chế về giao dịch, giới hạn lưu lượng, xác thực và phát hiện lạm dụng tương ứng.

Thiết kế đạt mục tiêu khi các đường nhận credential tự gửi được nhận diện đầy đủ, request phải đáp ứng bằng chứng theo chính sách server và thất bại xảy ra trước tác dụng được bảo vệ. Các giả định về cookie, origin, CORS, phiên và client phải được kiểm chứng cùng nhau, thay vì được suy ra từ một tên công nghệ hoặc một thông báo lỗi của trình duyệt.
