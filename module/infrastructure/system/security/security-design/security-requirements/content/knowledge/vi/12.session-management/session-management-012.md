# Cookie SameSite

## 1. SameSite kiểm soát điều gì?

`SameSite` là thuộc tính cookie dùng để giới hạn việc trình duyệt đính kèm cookie theo ngữ cảnh site của request. Với cookie đại diện cho phiên đăng nhập, lựa chọn thuộc tính này ảnh hưởng trực tiếp đến những request nào có thể mang credential của người dùng.

Giả sử người học đang đăng nhập vào một nền tảng học tập rồi mở một website khác. Website đó có thể khiến trình duyệt tạo request đến nền tảng học tập. Yêu cầu bảo mật cần xác định request nào được phép mang cookie phiên và server phải kiểm tra gì trước khi thay đổi dữ liệu.

Đặc tả “cookie phải có SameSite” chưa nói rõ giá trị, mục đích hoặc các luồng sẽ bị ảnh hưởng. Một đặc tả hữu ích phải liên kết được cookie với chức năng nghiệp vụ, ranh giới tin cậy, luồng đăng nhập và tiêu chí chấp nhận trên trình duyệt được hỗ trợ.

Các ví dụ trong bài sử dụng các tên miền minh họa như `portal.learning.example`. Chúng mô tả một kiến trúc giả định, không phải cấu hình của hệ thống đang chạy.

## 2. Same-site khác same-origin

**Origin** xét scheme, host và port. Với cách xét **schemeful same-site**, site dựa trên scheme và registrable domain; việc xác định registrable domain liên quan đến public suffix. Hai subdomain có thể cùng site nhưng khác origin. Scheme HTTP và HTTPS cũng tạo khác biệt khi xét site. Xem giải thích tại [web.dev: Schemeful Same-Site](https://web.dev/articles/schemeful-samesite).

Ví dụ lấy `https://portal.learning.example` làm điểm tham chiếu:

| Đích | Quan hệ origin | Quan hệ site trong ví dụ |
|---|---|---|
| `https://portal.learning.example` | Cùng origin | Cùng site |
| `https://api.learning.example` | Khác origin | Cùng site |
| `https://portal.learning.example:8443` | Khác origin | Cùng site |
| `http://portal.learning.example` | Khác origin | Khác site do scheme |
| `https://portal.training.example` | Khác origin | Khác site |

Hệ quả thiết kế là không dùng cụm “khác domain” một cách mơ hồ. Trong bản vẽ kiến trúc cần ghi đủ URL và xác định ranh giới tin cậy của từng host. Ví dụ, nếu một subdomain dành cho nội dung do người dùng cung cấp nằm cùng site với cổng quản trị, nhóm thiết kế phải xét rủi ro từ chính subdomain đó, thay vì chỉ xét website bên ngoài tổ chức.

## 3. Ba giá trị và ý nghĩa của việc khai báo tường minh

### 3.1. Strict

`SameSite=Strict` giới hạn cookie vào ngữ cảnh same-site. Một request điều hướng ban đầu từ site khác có thể không mang cookie này, dù người dùng trước đó đã đăng nhập. Điều đó cần được cân nhắc với liên kết từ email hoặc cổng bên ngoài. [web.dev: SameSite cookies explained](https://web.dev/articles/samesite-cookies-explained).

Ví dụ yêu cầu cho một cổng quản trị nội bộ có thể chọn `Strict`, đồng thời mô tả rõ màn hình tiếp nhận người dùng khi họ vào từ liên kết bên ngoài. Không nên coi trải nghiệm đó là lỗi ngẫu nhiên rồi mở rộng tất cả cookie mà không phân tích luồng.

### 3.2. Lax

`SameSite=Lax` cho phép cookie trong ngữ cảnh same-site và một số điều hướng cross-site ở cấp cao nhất sử dụng phương thức an toàn, điển hình là `GET`. Nó không đồng nghĩa “mọi GET đều mang cookie”: fetch và iframe là những ngữ cảnh khác với điều hướng cấp cao nhất. Các quy tắc này được mô tả trong [bản thảo IETF về HTTP cookies](https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-22.html#section-4.1.2.7), một tài liệu đặc tả đang được phát triển.

### 3.3. None

`SameSite=None` cho phép cookie tham gia ngữ cảnh cross-site và phải đi cùng `Secure`. Không khai báo thuộc tính khác với khai báo `None`: một số trình duyệt áp dụng mặc định kiểu Lax, có thể có ngoại lệ cho cookie mới tạo. Vì vậy, cần khai báo tường minh và không dựa vào khoảng nới lỏng mặc định. [MDN: Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#samesitesamesite-value).

Trong yêu cầu hệ thống, giá trị cần được chốt cho từng cookie. Không dùng việc một luồng đang thiếu cookie làm căn cứ tự động chuyển toàn bộ cookie phiên sang `None`.

## 4. Ma trận ngữ cảnh để phân tích luồng

Bảng dưới mô tả điều kiện SameSite trong các tình huống đơn giản. “Cho phép” không bảo đảm cookie thực sự được gửi: còn phải thỏa host, path, HTTPS, thời hạn, chế độ credentials và chính sách trình duyệt.

| Ngữ cảnh request đến host của cookie | Strict | Lax tường minh | None kèm Secure |
|---|---|---|---|
| Same-site, request hợp lệ theo các điều kiện khác | Cho phép | Cho phép | Cho phép |
| Cross-site, điều hướng cấp cao nhất bằng GET | Không cho phép | Cho phép | Cho phép |
| Cross-site, form POST ở cấp cao nhất | Không cho phép | Không cho phép | Cho phép |
| Cross-site, fetch GET | Không cho phép | Không cho phép | Cho phép |
| Cross-site, tải ảnh như tài nguyên con | Không cho phép | Không cho phép | Cho phép |
| Cross-site, điều hướng trong iframe | Không cho phép | Không cho phép | Cho phép |

Bảng là công cụ suy luận dựa trên các quy tắc tại [đặc tả cookie của IETF](https://www.ietf.org/archive/id/draft-ietf-httpbis-rfc6265bis-22.html#section-5.8.3). Với redirect nhiều bước, iframe lồng nhau hoặc thay đổi phương thức trong chuỗi điều hướng, phải mô tả đầy đủ ngữ cảnh và kiểm chứng luồng thực tế, không suy diễn từ một URL cuối cùng.

Một mẫu mô tả luồng nên có các trường: trang khởi tạo, URL đích, phương thức, loại điều hướng, cookie dự kiến và tác động nghiệp vụ. Thiếu một trong các thông tin đó có thể khiến hai nhóm hiểu khác nhau về việc cookie có xuất hiện hay không.

## 5. SameSite nằm trong một bộ thuộc tính cookie

Các thuộc tính cookie có chức năng khác nhau: `Secure` giới hạn truyền qua kết nối an toàn; `HttpOnly` hạn chế truy cập cookie từ JavaScript; `Domain` và `Path` xác định phạm vi gửi; `Max-Age` hoặc `Expires` quản lý thời hạn. Chúng không tự thay thế cho kiểm tra phiên ở server. [MDN: Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies).

Ví dụ header cho cookie phiên của host ứng dụng:

```http
Set-Cookie: __Host-session=opaque-session-reference; Path=/; Secure; HttpOnly; SameSite=Lax
```

Tiền tố `__Host-` yêu cầu `Secure`, `Path=/` và không có `Domain` trên trình duyệt hỗ trợ quy tắc tiền tố. Nó không tự chọn SameSite hay thay thế `HttpOnly`. [MDN: Cookie prefixes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#cookie_prefixes).

Header trên là ví dụ minh họa. Giá trị thực tế phải là credential được tạo và quản lý phù hợp; chuỗi `opaque-session-reference` không phải một giá trị phiên có thể dùng trong triển khai.

Một yêu cầu về phát hành cookie nên quy định tất cả nơi có thể phát hành lại nó: đăng nhập, xác thực lại, thay đổi quyền, gia hạn phiên và đường lỗi. Nếu chỉ endpoint đăng nhập có thuộc tính đúng nhưng endpoint gia hạn ghi đè bằng cấu hình khác, hành vi bảo mật vẫn không nhất quán.

Phạm vi host cần xuất phát từ nhu cầu. Ví dụ, nhóm thiết kế có thể yêu cầu cookie phiên của cổng quản trị chỉ thuộc host quản trị. Không mở rộng `Domain` sang mọi subdomain chỉ để giảm công cấu hình, đặc biệt khi các subdomain có chủ sở hữu hoặc mức tin cậy khác nhau.

## 6. SameSite và phòng chống CSRF

**CSRF** khai thác việc trình duyệt mang credential của người dùng vào một thao tác mà người dùng không có ý định thực hiện. SameSite giúp giảm một số đường tấn công nhưng thường cần kết hợp kiểm soát phía server, như cơ chế chống CSRF và kiểm tra nguồn request phù hợp. GET nghiệp vụ không nên được dùng để thực hiện thay đổi dữ liệu cần sự cho phép của người dùng. [OWASP: CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Xét hai tình huống của nền tảng giả định:

- Một website khác cố gửi form thay đổi địa chỉ liên hệ. Yêu cầu của hệ thống là từ chối thao tác khi không có bằng chứng chống CSRF hợp lệ, thay vì chỉ trông chờ credential có bị trình duyệt giữ lại hay không.
- Một trang nội dung không đáng tin trên host cùng site cố gọi chức năng quản trị. Mô hình đe dọa phải bao gồm nguồn này; nhãn same-site không thể được xem như quyền quản trị hoặc bằng chứng về ý định của người dùng.

Từ đó có thể viết yêu cầu riêng cho endpoint thay đổi dữ liệu, không phụ thuộc vào lựa chọn cookie của một luồng đăng nhập. Khi một ngoại lệ cross-site cần tồn tại, kiểm soát nghiệp vụ ở server vẫn phải duy trì.

`HttpOnly` cũng không phải bằng chứng rằng mọi request do script tạo ra đều vô hại. Mô hình đe dọa cần xem xét script chạy trong ứng dụng có thể kích hoạt những thao tác nào dưới quyền người dùng. Yêu cầu về phòng chống chèn script và yêu cầu về CSRF giải quyết các đường tấn công có giao nhau nhưng không đồng nhất.

## 7. Fetch, CORS và frontend tách khỏi API

Giả sử frontend ở `https://portal.learning.example`, API ở `https://api.learning.example`. Một lời gọi fetch có thể cần `credentials: 'include'` vì khác origin. Tuy nhiên, tùy chọn đó không vượt qua SameSite. CORS còn quyết định việc script được đọc phản hồi; với một số request đơn giản, request có thể đã được gửi trước khi phản hồi bị chặn. [MDN: Including credentials](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch#including_credentials).

Ví dụ lời gọi từ frontend:

```javascript
const response = await fetch('https://api.learning.example/profile', {
  method: 'GET',
  credentials: 'include'
});
```

Đây chỉ là ví dụ diễn đạt một luồng. Cookie phải thuộc phạm vi host API và đáp ứng các điều kiện khác; việc viết đoạn code trên không chứng minh phiên đã được cấu hình đúng.

Khi gặp lỗi, nên tách các câu hỏi trong yêu cầu và kiểm chứng:

1. Cookie có được trình duyệt chấp nhận khi nhận `Set-Cookie` không?
2. Cookie có thuộc phạm vi request đang xét không?
3. Ngữ cảnh SameSite có cho phép cookie tham gia không?
4. Fetch có sử dụng chế độ credentials phù hợp không?
5. CORS có cho phép frontend hợp lệ nhận phản hồi không?
6. Server có chấp nhận phiên và cho phép thao tác không?

Không thể kết luận “cần SameSite=None” chỉ từ thông báo lỗi CORS. Trong kiến trúc ví dụ, nhóm thiết kế phải chứng minh nhu cầu cross-site thực sự trước khi tạo ngoại lệ cookie. Các vấn đề về allowlist origin, host cookie hoặc chế độ fetch cần được giải quyết ở đúng lớp.

## 8. Đăng nhập liên kết và callback

Một luồng đăng nhập có thể đi từ ứng dụng sang nhà cung cấp identity ở site khác rồi quay về. Đặc tả cần ghi rõ callback dùng GET hay POST, là điều hướng cấp cao nhất hay nằm trong iframe và cookie nào cần có để kiểm tra giao dịch.

Ví dụ giả định:

```text
Ứng dụng học tập
    -> Khởi tạo giao dịch đăng nhập
    -> Nhà cung cấp identity ở site khác
    -> Callback về ứng dụng
    -> Kiểm tra ràng buộc giao dịch và kết quả theo giao thức
    -> Tạo phiên ứng dụng mới
```

Không coi việc thiếu cookie trên callback là lý do bỏ qua kiểm tra ràng buộc giao dịch. Cần xác định luồng thiếu cookie sẽ kết thúc an toàn hoặc hướng dẫn người dùng thực hiện lại như thế nào.

Giả sử một tích hợp của hệ thống bắt buộc nhận callback cross-site POST và cần cookie tương quan giao dịch. Nhóm thiết kế có thể đề xuất một cookie chuyên biệt thay vì mở rộng cookie phiên chính:

```http
Set-Cookie: __Host-login-flow=opaque-transaction-reference; Path=/; Max-Age=300; Secure; HttpOnly; SameSite=None
```

Trong thiết kế giả định này, cookie chỉ tham chiếu giao dịch đăng nhập, không tự cấp quyền đọc dữ liệu học viên hoặc quyền quản trị. Thời hạn 300 giây là lựa chọn minh họa, cần được chốt theo rủi ro và khả năng hoàn tất luồng.

Các yêu cầu kèm theo phải giới hạn mục đích, liên kết giao dịch với trình duyệt và kết quả mong đợi, ngăn sử dụng lại giao dịch đã hoàn tất và xử lý hết hạn. Tính an toàn của callback còn phụ thuộc vào giao thức đăng nhập; chỉ có cookie chuyên biệt chưa đủ chứng minh toàn bộ luồng an toàn.

Đây là một phương án để phân tích, không phải cấu hình bắt buộc cho mọi SSO. Nếu giao thức hoặc kiến trúc không cần cookie tương quan loại này, không tạo thêm cookie chỉ để làm giống ví dụ.

## 9. Iframe, third-party cookie và nhu cầu nhúng

Khai báo `SameSite=None; Secure` không bảo đảm trình duyệt cho phép cookie trong mọi bối cảnh bên thứ ba. Cài đặt riêng tư, hạn chế trình duyệt hoặc chính sách tổ chức có thể tiếp tục ảnh hưởng đến cookie. [web.dev: lưu ý về third-party cookie](https://web.dev/articles/samesite-cookies-explained).

Ví dụ, nền tảng học tập được nhúng trong cổng đối tác có thể cần một kiến trúc đăng nhập khác với khi người học mở ứng dụng trực tiếp. Yêu cầu không nên hứa “nhúng ở bất kỳ website nào cũng giữ phiên” nếu chưa xác định môi trường hỗ trợ và cơ chế tương thích.

Đối với một tính năng nhúng, cần chốt:

- Đối tác và bối cảnh nào được hỗ trợ.
- Người dùng được thông báo thế nào khi không có phiên trong iframe.
- Có đường chuyển sang cửa sổ cấp cao nhất để đăng nhập hoặc thực hiện tác vụ không.
- Cơ chế nào ngăn host đối tác không được phép nhận hoặc lạm dụng kết quả đăng nhập.
- Chức năng nào vẫn phải từ chối khi không xác định được chủ thể.

Không giải quyết tình huống cookie bị chặn bằng cách truyền credential phiên chính qua query string hoặc thông điệp không kiểm soát. Một phương án thay thế phải có mô hình tin cậy và yêu cầu bảo vệ riêng, không trở thành đường vòng bỏ qua quản lý phiên.

## 10. Từ mục tiêu đến yêu cầu bảo mật đo được

Giả sử hệ thống có cổng học tập, cổng quản trị riêng và một tích hợp đăng nhập liên kết. Các yêu cầu dưới đây là ví dụ đặc tả cho hệ thống giả định, không phải bằng chứng một triển khai hiện có đã đạt.

| ID | Yêu cầu | Bằng chứng chấp nhận dự kiến |
|---|---|---|
| SS-INV-01 | Mọi cookie có thể nhận diện phiên hoặc giao dịch xác thực phải có chủ sở hữu, mục đích, host, thời hạn và chính sách SameSite trong danh mục quản lý | Đối chiếu danh mục với các luồng phát hành cookie |
| SS-EXPLICIT-01 | Cookie thuộc danh mục xác thực phải khai báo SameSite tường minh trên mọi response phát hành hoặc thay thế | Thu các header ở đăng nhập, gia hạn, xác thực lại và đường lỗi |
| SS-PORTAL-01 | Cookie phiên cổng học tập của ví dụ sử dụng Lax, Secure, HttpOnly và phạm vi host được phê duyệt | Header thực tế phù hợp cấu hình, kiểm chứng luồng truy cập dự kiến |
| SS-ADMIN-01 | Cookie phiên cổng quản trị của ví dụ sử dụng Strict; hành vi vào cổng từ liên kết bên ngoài phải được mô tả và hỗ trợ | Luồng same-site hoạt động; luồng bên ngoài không bị xử lý thành lỗi không rõ nguyên nhân |
| SS-EXCEPTION-01 | Cookie None chỉ được sử dụng cho luồng có nhu cầu cross-site đã được phân tích, đi cùng Secure và có chủ sở hữu ngoại lệ | Danh sách ngoại lệ khớp cookie thực tế, có lý do và phạm vi |
| SS-FLOW-01 | Cookie tương quan callback POST trong ví dụ chỉ tham chiếu giao dịch đăng nhập và hết hiệu lực theo thời hạn 300 giây đã chọn | Không truy cập được dữ liệu nghiệp vụ bằng cookie đó; giao dịch quá hạn bị từ chối |
| SS-CSRF-01 | Endpoint thay đổi dữ liệu qua phiên trình duyệt phải thực thi cơ chế chống CSRF của ứng dụng trước khi tạo tác động | Request thiếu hoặc sai bằng chứng bị từ chối, dữ liệu không thay đổi |
| SS-GET-01 | Các endpoint GET nghiệp vụ không được xóa khóa học, cấp quyền hoặc thay đổi cấu hình theo tham số request | Gọi GET vào các đường dẫn liên quan không tạo tác động đó |
| SS-SUBDOMAIN-01 | Mô hình đe dọa và tiêu chí chấp nhận phải bao gồm nguồn không đáng tin nằm cùng site | Có tình huống kiểm chứng riêng cho subdomain được chỉ định |
| SS-CALLBACK-01 | Callback không có ràng buộc giao dịch hợp lệ không được tạo phiên ứng dụng hoặc bỏ qua kiểm tra giao thức | Giao dịch thiếu, sai, hết hạn hoặc dùng lại bị xử lý theo chính sách |
| SS-EDGE-01 | Proxy, gateway và ứng dụng không được ghi đè thuộc tính cookie ngoài chính sách đã chốt | Header quan sát tại biên công khai phù hợp với yêu cầu |
| SS-SUPPORT-01 | Chức năng nhúng phải có hành vi an toàn khi cookie không khả dụng, không tự chuyển dữ liệu bảo vệ sang chế độ công khai | Kịch bản không có cookie vẫn giữ đúng quyền truy cập |

Mục tiêu của bảng là biến các lựa chọn thành kết quả có thể quan sát. Yêu cầu về header và yêu cầu về hành vi đều cần thiết: một header đúng không chứng minh endpoint chống được thao tác ngoài ý định; một luồng chạy thành công cũng không chứng minh cookie có phạm vi tối thiểu.

## 11. Phân tích một thay đổi yêu cầu

Giả sử đội tích hợp báo rằng callback đăng nhập mới không có cookie mong đợi và đề nghị chuyển tất cả cookie sang `None`.

Trước khi quyết định, người viết yêu cầu cần thu đủ mô tả:

1. Cookie nào thiếu: cookie phiên chính hay cookie theo dõi giao dịch đăng nhập?
2. Callback thực sự có ngữ cảnh nào và đi qua những bước redirect nào?
3. Cookie đã được lưu hay bị từ chối ngay từ lúc phát hành?
4. Phạm vi host và path có khớp callback không?
5. Tác động nghiệp vụ nào cần cookie đó để hoàn tất an toàn?
6. Có thể giới hạn thay đổi vào đúng cookie và đúng luồng không?

Nếu chỉ một cookie tương quan giao dịch cần ngoại lệ, thay đổi cả cookie quản trị sẽ mở rộng bề mặt sử dụng credential mà không phục vụ nhu cầu đó. Một yêu cầu được sửa đúng phạm vi cần ghi rõ ngoại lệ, thời hạn, điều kiện thành công và hành vi khi không nhận được cookie.

Nhóm cũng phải xét trường hợp trình duyệt tiếp tục chặn cookie vì chính sách riêng tư. Nếu không có đường hoàn tất an toàn, kết quả đúng có thể là thông báo luồng chưa được hỗ trợ trong bối cảnh đó, thay vì bỏ kiểm tra xác thực để ép luồng chạy.

## 12. Ma trận tiêu chí chấp nhận

Kiểm chứng SameSite cần môi trường trình duyệt có các site và origin được kiểm soát. Các tình huống sau là mô tả kiểm chứng dự kiến, chưa phải kết quả chạy kiểm thử.

| Tình huống | Thao tác kiểm chứng | Kết quả cần quan sát |
|---|---|---|
| Phát hành lần đầu | Đăng nhập qua từng luồng thuộc phạm vi | Header và cookie được lưu đúng chính sách đã chốt |
| Phát hành lại | Gia hạn phiên, xác thực lại và xử lý nhánh lỗi | Không có response ghi đè bằng thuộc tính ngoài chính sách |
| Truy cập nội bộ | Điều hướng trong ứng dụng với phiên hợp lệ | Chức năng được phép hoạt động theo thiết kế |
| Liên kết từ site khác | Mở liên kết GET cấp cao nhất đến cổng học tập và cổng quản trị | Hành vi của từng loại cookie khớp yêu cầu tương ứng |
| Cross-site form POST | Gửi form từ site kiểm chứng bên ngoài | Không tạo tác động ngoài ý định, kể cả khi luồng ngoại lệ có cookie |
| Tài nguyên con | Tải endpoint bằng ảnh hoặc iframe cross-site | Không suy diễn thành điều hướng cấp cao nhất; không lộ dữ liệu ngoài chính sách |
| Frontend khác origin | Gọi API từ frontend được phép | Quyền đọc phản hồi và phiên đều đáp ứng cấu hình riêng của chúng |
| Subdomain không tin cậy | Khởi tạo thao tác từ host cùng site đã chỉ định trong mô hình đe dọa | Kiểm soát server vẫn ngăn hành động không hợp lệ |
| Callback hợp lệ | Hoàn tất giao dịch đăng nhập theo giao thức được chọn | Tạo đúng phiên cho giao dịch đã khởi tạo |
| Callback bất hợp lệ | Bỏ, sửa hoặc dùng lại dữ liệu ràng buộc giao dịch | Không tạo phiên bằng cách bỏ qua kiểm tra |
| Chặn cookie bên thứ ba | Chạy luồng nhúng với cài đặt hạn chế tương ứng | Chức năng bảo vệ không mở quyền; có hướng xử lý cho người dùng |
| Cookie mặc định | Kiểm tra danh mục cookie và mọi đường phát hành | Không phụ thuộc vào việc trình duyệt tự gán mặc định |
| Cookie hết hiệu lực | Dùng credential của phiên đã kết thúc | Server vẫn từ chối, độc lập với lựa chọn SameSite |
| Qua gateway | Quan sát response tại biên công khai | Không bị thay đổi hoặc mất thuộc tính so với chính sách |

Một công cụ HTTP có thể tự gửi header `Cookie` mà không áp dụng chính sách giống trình duyệt. Vì vậy, chỉ gửi request bằng công cụ đó chưa đủ chứng minh hành vi SameSite. Nó vẫn hữu ích để kiểm tra phản hồi server, nhưng tiêu chí về trình duyệt cần được kiểm chứng trong đúng môi trường thực thi.

Các tên miền kiểm chứng phải được bố trí để có cả trường hợp khác origin cùng site và trường hợp khác site. Chỉ đổi port hoặc đổi subdomain trong mọi phép thử có thể làm bỏ sót chính ranh giới đang muốn đánh giá.

## 13. Triển khai và quan sát vận hành

Khi thay đổi chính sách cookie, cần xác định cách xử lý cookie cũ đang tồn tại, đặc biệt khi có nhiều tên, host hoặc path. Một lần phát hành header mới không nên được coi là bằng chứng rằng mọi bản thể cũ đã biến mất khỏi trình duyệt của người dùng.

Kế hoạch chuyển đổi nên mô tả các luồng chịu ảnh hưởng, người sở hữu, dấu hiệu lỗi và tiêu chí hoàn tất. Nếu cần quay lại cấu hình trước, phải biết chính sách phiên nào vẫn được bảo đảm và tránh biến một ngoại lệ tạm thời thành cấu hình không có thời hạn.

Nhật ký có thể ghi loại lỗi callback, thiếu tương quan giao dịch hoặc thất bại kiểm tra CSRF bằng mã nguyên nhân. Không ghi giá trị cookie phiên, mã giao dịch có thể dùng như credential hoặc toàn bộ header chứa thông tin xác thực.

Quan sát ở server có giới hạn: không nhận được cookie chưa cho biết chắc trình duyệt đã chặn vì SameSite, phạm vi host, hết hạn hay chính sách riêng tư. Phân tích sự cố cần đối chiếu mô tả luồng và thông tin chẩn đoán phù hợp, không kết luận một nguyên nhân duy nhất từ tín hiệu thiếu cookie.

Phạm vi trình duyệt được hỗ trợ cần được quản lý như một phần của yêu cầu sản phẩm. Khi nền tảng hoặc chính sách trình duyệt thay đổi, nhóm phải đánh giá lại luồng phụ thuộc tương ứng. Không hứa khả năng tương thích vô thời hạn dựa trên một lần kiểm chứng.

## 14. Những cách viết yêu cầu dễ gây hiểu sai

| Cách viết chưa đủ | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “Bật SameSite cho an toàn” | Không chọn giá trị hoặc phạm vi | Nêu cookie, mục đích, giá trị và các luồng cần hỗ trợ |
| “Khác subdomain nên phải dùng None” | Chưa phân tích site và origin | Lập bảng URL, loại request và nhu cầu credential thực tế |
| “Cứ include credentials là có cookie” | Bỏ qua chính sách cookie và môi trường | Kiểm tra riêng từng điều kiện trên luồng được hỗ trợ |
| “CORS đã chặn nên không có CSRF” | Chưa chứng minh tác động nghiệp vụ đã bị ngăn | Kiểm tra quyết định server và trạng thái dữ liệu sau request |
| “Cookie này chỉ phục vụ SSO nên bỏ kiểm tra” | Ngoại lệ luồng bị hiểu thành ngoại lệ xác thực | Giới hạn cookie và giữ đầy đủ ràng buộc giao dịch |
| “Cookie có thể dùng ở mọi iframe” | Không xác định môi trường hỗ trợ | Nêu bối cảnh hỗ trợ và hành vi khi cookie không khả dụng |
| “Có header đúng là xong” | Chưa kiểm chứng hành vi và đường ghi đè | Quan sát header tại biên cùng kết quả nghiệp vụ của các luồng |

Một đặc tả Cookie SameSite tốt phải làm rõ credential nào được tham gia ngữ cảnh nào và vì sao. Các ngoại lệ cần gắn với một nhu cầu cụ thể; cơ chế kiểm tra phiên, chống CSRF và ràng buộc giao dịch vẫn phải có tiêu chí độc lập. Từ đó, lựa chọn thuộc tính cookie trở thành một yêu cầu có thể triển khai và kiểm chứng, thay vì một cờ cấu hình được bật theo thói quen.
