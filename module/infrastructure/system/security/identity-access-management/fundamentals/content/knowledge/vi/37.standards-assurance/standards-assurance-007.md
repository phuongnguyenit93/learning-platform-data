# OWASP Session Management Cheat Sheet

## 1. Vì sao quản lý phiên là một phần của IAM?

Sau khi người dùng đăng nhập, ứng dụng thường không yêu cầu nhập lại mật khẩu ở mỗi request. Thay vào đó, ứng dụng duy trì **phiên đăng nhập** để liên kết các request tiếp theo với ngữ cảnh đã xác thực. Với phiên dùng bearer session ID, ai giữ giá trị đó có thể sử dụng phiên trong phạm vi hệ thống chấp nhận.

Ví dụ, Lan đăng nhập cổng quản trị, hoàn thành MFA rồi cấp role cho một nhân viên. Nếu kẻ khác lấy được session ID và sử dụng được nó, việc Lan đã dùng MFA trước đó không tự ngăn kẻ này tiếp tục thao tác qua phiên. Bảo vệ đăng nhập và bảo vệ trạng thái sau đăng nhập phải được thiết kế cùng nhau.

**OWASP Session Management Cheat Sheet** là hướng dẫn kỹ thuật về thuộc tính định danh phiên, cơ chế truyền và lưu giữ, vòng đời, hết hạn và theo dõi phiên. Khi sử dụng tài liệu trong chương Standards và assurance, mục tiêu là chuyển hướng dẫn thành quyết định triển khai có thể kiểm tra, không chỉ ghi “đã dùng session an toàn”. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Trong bài học, ví dụ chính là ứng dụng web có phiên lưu phía máy chủ và cookie mang một định danh không chứa dữ liệu nghiệp vụ. Khi kiến trúc có SSO hoặc token khác, cần xác định thêm trạng thái nào được quản lý ở từng thành phần.

## 2. Xác định rõ bí mật, trạng thái và quyền

Một mô hình minh họa:

```text
Trình duyệt: cookie chứa định danh phiên
                       |
                       v
Backend: tra cứu phiên và kiểm tra hiệu lực
                       |
                       v
Ngữ cảnh đã xác thực + chính sách truy cập hiện tại
                       |
                       v
Quyết định cho phép hoặc từ chối thao tác
```

Trong mô hình này, cookie không cần chứa tên, email, tenant hoặc role của Lan. Những giá trị nghiệp vụ thuộc trạng thái được quản lý tại backend. Việc nhận được một cookie đúng tên cũng chưa chứng minh phiên tồn tại hoặc còn hiệu lực.

OWASP nêu mức entropy tối thiểu 64 bit cho session ID; nếu tự tạo định danh, hướng dẫn sử dụng CSPRNG với kích thước ít nhất 128 bit. Hướng dẫn cũng ưu tiên cơ chế phiên sẵn có của nền tảng, định danh không mang ý nghĩa và tránh truyền session ID trong URL. Độ dài chuỗi không đồng nghĩa với độ khó dự đoán. [OWASP — Session ID Properties](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#session-id-properties).

Ví dụ, chuỗi rất dài được ghép từ tên tài khoản, thời gian và số tăng dần có thể vẫn dễ đoán. Trong triển khai thực tế, hãy dùng cơ chế sinh phiên được framework hỗ trợ và kiểm tra cấu hình của nó; không thay bằng thuật toán tự ghép chuỗi.

Backend cũng phải phân biệt **xác thực phiên** với **cấp quyền**. Phiên còn hoạt động của Lan không có nghĩa Lan được cấp role trên mọi tenant. Mỗi thao tác vẫn cần đánh giá quyền và phạm vi tài nguyên tương ứng.

## 3. Cookie: mỗi thuộc tính giải quyết một việc

Ví dụ header cho một ứng dụng phục vụ hoàn toàn qua HTTPS:

```http
Set-Cookie: __Host-id=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

`<opaque-session-id>` là ký hiệu thay thế cho giá trị do hệ thống tạo, không phải giá trị dùng thật.

| Thuộc tính | Tác dụng chính |
| --- | --- |
| `Secure` | Giới hạn gửi cookie qua kết nối an toàn. |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua API như `document.cookie`. |
| `SameSite` | Điều khiển việc gửi cookie trong ngữ cảnh cross-site. |
| Không đặt `Domain` | Giữ cookie ở phạm vi host đặt nó. |
| Tiền tố `__Host-` | Trình duyệt hỗ trợ yêu cầu `Secure`, `Path=/` và không có `Domain`. |

`SameSite=None` cần `Secure`. Việc chọn `Strict`, `Lax` hay `None` phải phù hợp luồng thực tế, đặc biệt các bước chuyển hướng hoặc POST từ bên cung cấp SSO. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

Đối với ví dụ trên, không thêm `Domain=example.com` chỉ để “đồng bộ cấu hình”: điều đó mâu thuẫn yêu cầu tiền tố đã chọn. Nếu nhiều ứng dụng cần SSO, hãy thiết kế luồng federation thay vì mặc định chia sẻ cùng một cookie đăng nhập cho mọi subdomain.

`Path` xác định phạm vi gửi cookie, không phải ranh giới bảo mật giữa các ứng dụng. Khi xóa cookie, tên, domain và path cần khớp cookie đã tạo. [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html).

Trong môi trường có reverse proxy, kiểm tra header cuối cùng trình duyệt nhận được. Cấu hình đúng ở một tầng không đảm bảo tầng khác không sửa hoặc tạo thêm cookie cùng tên ở path khác.

## 4. Session fixation: không tiếp tục dùng định danh trước đăng nhập

**Session fixation** xảy ra khi kẻ tấn công khiến nạn nhân sử dụng một định danh mà kẻ tấn công đã biết, rồi ứng dụng tiếp tục dùng định danh đó sau đăng nhập. Spring Security mô tả tấn công này và cung cấp các chiến lược chống fixation, trong đó có sử dụng `HttpServletRequest.changeSessionId()`. [Spring Security — Session Fixation Protection](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html#understanding-session-fixation-attack-protection).

Tình huống minh họa:

1. Kẻ tấn công biết định danh phiên ẩn danh `S0`.
2. Lan bị dẫn vào luồng sử dụng `S0`.
3. Lan đăng nhập thành công.
4. Ứng dụng vẫn chấp nhận `S0` như phiên đã xác thực.
5. Kẻ tấn công gửi `S0` để thao tác dưới tài khoản Lan.

Kết quả cần chứng minh trong kiểm thử là `S0` không còn dùng được để truy cập với quyền sau đăng nhập, còn trình duyệt hợp lệ nhận và sử dụng định danh thích hợp. Chỉ quan sát có thêm một cookie mới chưa đủ nếu backend vẫn nhận cookie cũ.

Với Jakarta Servlet, API sau đổi định danh của phiên hiện tại; nó không tự thực hiện xác thực người dùng. `getSession(true)` có thể tạo phiên và cũng không chứng minh người gọi đã đăng nhập. [Jakarta Servlet — HttpServletRequest](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html).

```java
// Chỉ minh họa thao tác với một phiên đã tồn tại.
// Việc xác thực và lưu security context do cơ chế xác thực đảm nhiệm.
HttpSession session = request.getSession(false);
if (session != null) {
    request.changeSessionId();
}
```

Nếu đang dùng Spring Security, cần tích hợp theo cơ chế của framework thay vì chèn đoạn này vào mọi request. Đổi ID liên tục không giải quyết việc thiếu kiểm tra quyền và có thể gây lỗi khi nhiều request chạy đồng thời.

Tương tự, sau step-up hoặc chuyển sang ngữ cảnh đặc quyền, hãy xác định rõ phiên nào được nâng quyền, định danh cũ còn được nhận ở đâu và các thuộc tính nào được giữ lại. Đổi ID và xác thực lại là hai thao tác khác nhau.

## 5. Timeout phải là quyết định của máy chủ

Một giao diện hiển thị bộ đếm hết phiên giúp người dùng biết khi nào cần đăng nhập lại. Nó không thể là nơi quyết định phiên có còn hợp lệ hay không: người gọi có thể bỏ qua giao diện và gửi request trực tiếp.

NIST phân biệt giới hạn tổng thời gian và giới hạn không hoạt động, đồng thời yêu cầu giới hạn phiên được thực thi dù người gọi vẫn chứng minh được quyền giữ session secret. [NIST — Session Management](https://pages.nist.gov/800-63-4/sp800-63b/session/).

Trong thiết kế ứng dụng, cần phân biệt:

| Cơ chế | Câu hỏi |
| --- | --- |
| Idle timeout | Phiên đã không hoạt động đủ lâu để bị kết thúc chưa? |
| Absolute timeout | Phiên đã đạt tuổi tối đa dù vẫn có request chưa? |
| Đổi định danh định kỳ | Có cần thay giá trị mang phiên trong lúc phiên vẫn hoạt động không? |
| Độ mới xác thực | Lần xác thực có đủ gần để thực hiện thao tác nhạy cảm không? |

Ví dụ giả định một ứng dụng đặt idle timeout 15 phút và absolute timeout 8 giờ. Đây là giá trị phục vụ bài học, không phải cấu hình OWASP bắt buộc cho mọi hệ thống.

- Lan đăng nhập lúc 08:00 và liên tục thao tác: hạn tuyệt đối vẫn là 16:00.
- Lan thao tác lần cuối lúc 09:00: phiên phải bị từ chối khi đạt giới hạn không hoạt động theo chính sách.
- Backend đổi session ID lúc 10:00: thao tác đổi ID không tự tạo một lần xác thực mới hoặc kéo dài phiên thêm 8 giờ.

Nếu ứng dụng có polling, tải nền hoặc nhiều tab, phải định nghĩa request nào cập nhật thời điểm hoạt động. Một request nền lặp lại có thể làm phiên trông như luôn được sử dụng. Không lấy mốc thời gian do trình duyệt tự khai làm nguồn quyết định duy nhất.

## 6. API Servlet: idle timeout và invalidate không thay thế nhau

`HttpSession.setMaxInactiveInterval()` nhận khoảng không hoạt động tính bằng **giây**. Giá trị không dương mang nghĩa không timeout theo cơ chế này. `invalidate()` vô hiệu hóa phiên và bỏ các đối tượng gắn với nó. [Jakarta Servlet — HttpSession](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html).

```java
HttpSession session = request.getSession(false);
if (session != null) {
    // 15 phút chỉ là giá trị minh họa cho idle timeout.
    session.setMaxInactiveInterval(15 * 60);
}
```

Đoạn này không cấu hình absolute timeout. Nếu ứng dụng cần hạn tuyệt đối tính từ lần xác thực, phải duy trì và kiểm tra mốc đó qua cơ chế phù hợp. Không mặc định thời điểm tạo `HttpSession` chính là thời điểm đăng nhập vì phiên có thể đã được tạo từ lúc người dùng còn ẩn danh.

Trong luồng logout tối giản, phần làm việc với phiên có thể là:

```java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
```

Đây là minh họa API, không phải toàn bộ logout handler. Cơ chế bảo mật còn cần xử lý security context, cookie và những loại trạng thái khác mà ứng dụng sử dụng. Tránh gọi `getSession(true)` chỉ để logout vì nó có thể tạo một phiên mới không cần thiết.

## 7. Logout: kiểm tra bằng việc dùng lại bằng chứng cũ

Giả sử ứng dụng chỉ xóa cookie trên trình duyệt của Lan nhưng bản ghi phiên vẫn được backend chấp nhận. Một bản sao cookie đã bị lấy trước đó vẫn có thể hoạt động. Ngược lại, vô hiệu hóa phiên ở backend nhưng để cookie cũ lại có thể gây vòng lặp hoặc trạng thái giao diện khó hiểu.

Với cookie minh họa ở phần trước, response xóa cookie có thể là:

```http
Set-Cookie: __Host-id=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
```

Luồng của ứng dụng nên có kết quả rõ ràng: phiên cũ không còn được dùng để truy cập tài nguyên được bảo vệ; trình duyệt được hướng dẫn bỏ cookie tương ứng; giao diện chuyển về trạng thái phù hợp.

Trong hệ thống nhiều backend instance, hãy thử dùng lại cookie qua instance khác sau logout. Nếu instance A đã vô hiệu hóa phiên nhưng instance B vẫn nhận từ cache riêng, việc logout mới có tác dụng ở một phần hệ thống. Nhóm triển khai cần định nghĩa và kiểm tra cơ chế lan truyền thu hồi.

Với request đã bắt đầu trước khi logout, phải xác định ranh giới hiệu lực. Không hứa rằng một thao tác đã commit sẽ tự bị hủy chỉ vì người dùng logout sau đó. Các thao tác đặc quyền có thể cần kiểm tra trạng thái và quyền ở thời điểm phù hợp trước khi thay đổi dữ liệu.

## 8. Cookie an toàn vẫn cần chống CSRF và XSS

`HttpOnly` hạn chế đọc cookie qua JavaScript nhưng không ngăn mã chạy trong trang gửi request bằng phiên của người dùng. Khi xét XSS, hãy kiểm tra cả khả năng thực hiện hành động dưới tài khoản nạn nhân, không chỉ việc đọc giá trị cookie.

Với CSRF, trình duyệt có thể tự gắn cookie vào request. OWASP khuyến nghị tận dụng bảo vệ CSRF của framework, sử dụng cơ chế token phù hợp và xem `SameSite` như một lớp bảo vệ bổ sung trong phần lớn triển khai. Thao tác thay đổi trạng thái không nên được đặt sau `GET`. Same-site cũng không đồng nghĩa same-origin. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

Ví dụ, API cấp role của cổng quản trị cần kiểm tra quyền của Lan và yêu cầu chống CSRF phù hợp. Một request thiếu bằng chứng CSRF không nên được chấp nhận chỉ vì cookie phiên vẫn hợp lệ.

Đối với callback SSO, cần kiểm tra đúng cơ chế bảo vệ của giao thức và cách liên kết callback với yêu cầu đăng nhập ban đầu. Đừng giải quyết lỗi callback bằng cách tắt toàn bộ bảo vệ cho mọi endpoint. Tương tự, đừng chuyển session ID sang query parameter chỉ để né giới hạn gửi cookie.

Các biện pháp có mục đích khác nhau: bảo vệ mã phía trình duyệt, chống request giả mạo, kiểm tra phiên và kiểm tra quyền. Một biện pháp không tự thay thế tất cả những phần còn lại.

## 9. Cache, trình duyệt và dữ liệu đã hiển thị

Một trang nhạy cảm có thể sử dụng:

```http
Cache-Control: no-store
```

Theo RFC 9111, `no-store` yêu cầu cache không lưu request/response liên quan; `no-cache` có nghĩa khác, cho phép lưu nhưng cần xác minh lại trước khi dùng theo điều kiện quy định. Header cache không phải cơ chế thu hồi dữ liệu đã đến người dùng. [RFC 9111 — Response Cache-Control Directives](https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2).

Ví dụ, sau logout, Lan bấm nút Back và nhìn thấy một phần giao diện cũ. Cần phân biệt việc trình duyệt hiển thị lại dữ liệu đã có với việc backend vẫn cho phép lấy dữ liệu mới hoặc thực hiện hành động. Cả trải nghiệm dữ liệu còn hiển thị lẫn hiệu lực truy cập đều cần được kiểm tra, nhưng chúng là hai kết quả khác nhau.

Nếu ứng dụng sử dụng service worker hoặc cache do JavaScript tự quản lý, hãy mô tả cách chúng xử lý dữ liệu của người đã logout. Chỉ kiểm tra header HTTP của backend có thể chưa đủ để hiểu toàn bộ vòng đời dữ liệu trên máy khách.

Không coi việc đóng tab là bằng chứng logout. Trong thiết kế sản phẩm, chỉ thông báo “đã kết thúc phiên” khi các thao tác phía máy chủ theo chính sách đã thực hiện, thay vì suy từ sự kiện giao diện không còn xuất hiện.

## 10. SSO có nhiều phiên và nhiều ranh giới logout

Trong ví dụ có SSO, cần tách phiên tại ứng dụng của Lan và phiên tại nhà cung cấp danh tính. OIDC RP-Initiated Logout mô tả cách RP yêu cầu OP đăng xuất người dùng thông qua logout endpoint, thường được công bố bằng `end_session_endpoint`. [OpenID Connect — RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html).

Một yêu cầu sản phẩm như “đăng xuất” cần được diễn đạt cụ thể hơn:

| Phạm vi mong muốn | Điều phải xác định trong thiết kế |
| --- | --- |
| Ứng dụng hiện tại | Phiên nào ở RP bị kết thúc? |
| Các thiết bị của cùng tài khoản | Làm sao tìm và thu hồi các phiên liên quan? |
| Nhà cung cấp danh tính | Có thực hiện luồng logout của OP không? |
| Các ứng dụng khác đã SSO | Cơ chế nào thông báo và xử lý tại các RP khác? |

Nếu chỉ logout ở cổng quản trị nhưng phiên IdP vẫn còn, một lần chuyển hướng đăng nhập mới có thể nhanh chóng đưa Lan trở lại. Điều đó không tự chứng minh phiên cũ của cổng quản trị chưa bị thu hồi. Kiểm thử phải ghi rõ đang xác minh phiên cũ bị từ chối hay đang xác minh không thể tạo phiên mới qua SSO.

Nếu kiến trúc còn access token hoặc refresh token, hãy xác định chúng có thuộc phạm vi logout này hay không và cơ chế xử lý tương ứng. Không suy rằng xóa một cookie có thể trực tiếp làm mất hiệu lực mọi loại credential ở mọi dịch vụ.

## 11. Theo dõi phiên mà không phát tán bí mật

OWASP Logging Cheat Sheet phân biệt dữ liệu cần ghi phục vụ điều tra với dữ liệu cần loại trừ; session ID, access token và mật khẩu không nên xuất hiện nguyên dạng trong log. Khi cần liên kết sự kiện phiên, dùng cách nhận diện phù hợp thay cho giá trị có thể được dùng để truy cập. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

Một sự kiện minh họa do ứng dụng định nghĩa:

```json
{
  "event": "session_revoked",
  "subject_id": "user-42",
  "session_audit_ref": "audit-ref-7c2",
  "reason": "user_logout",
  "result": "success"
}
```

`session_audit_ref` trong ví dụ là mã liên kết riêng, không được endpoint xác thực chấp nhận như session ID. Cách sinh, lưu và giữ mã này là một quyết định triển khai; bản ghi mẫu không mô tả một schema OWASP bắt buộc.

Kiểm tra cả log ứng dụng, proxy, APM và báo cáo lỗi. Dù developer không gọi `log.info(sessionId)`, bộ ghi request tự động vẫn có thể thu thập toàn bộ header `Cookie`. Tương tự, dump session store hoặc công cụ hỗ trợ vận hành có thể trở thành nơi làm lộ thông tin nếu quyền truy cập và nội dung thu thập không được kiểm soát.

## 12. Chuyển hướng dẫn thành bằng chứng kiểm tra

Bộ kiểm tra sau áp dụng cho tình huống cổng quản trị trong bài. Mỗi phép thử cần thực hiện trong môi trường được phép và gắn với chính sách thực tế của ứng dụng.

| Tình huống | Bằng chứng mong đợi |
| --- | --- |
| Đăng nhập từ phiên ẩn danh | ID trước đăng nhập không dùng được với quyền sau đăng nhập. |
| Cấu hình cookie | Response cuối cùng tới trình duyệt có đúng thuộc tính và phạm vi. |
| Gửi ID không được hệ thống cấp | Không tự tạo một phiên đã xác thực từ giá trị người gọi chọn. |
| Gửi ID qua URL hoặc kênh không hỗ trợ | Không dùng kênh đó để truy cập như phiên hợp lệ. |
| Vượt idle timeout | Backend từ chối dù trình duyệt vẫn gửi cookie cũ. |
| Request đều đặn đến hạn tuyệt đối | Hoạt động không kéo dài phiên vượt chính sách. |
| Đổi ID khi nhiều tab đang hoạt động | Không giữ đường truy cập ngoài ý muốn bằng ID cũ. |
| Logout rồi dùng lại cookie trên node khác | Phiên bị thu hồi theo cam kết của hệ thống. |
| Thu hồi role trong khi phiên còn sống | Thao tác liên quan không tiếp tục dựa vào quyền cũ ngoài chính sách. |
| Gọi API thay đổi dữ liệu thiếu bảo vệ CSRF | Request bị xử lý theo chính sách chống giả mạo. |
| Backend không truy cập được session store | Không chuyển lỗi thành một phiên đã xác thực mặc định. |
| Đăng nhập lại qua SSO sau local logout | Phân biệt phiên cũ với phiên mới vừa được tạo. |

Khi lưu bằng chứng, ghi điều kiện ban đầu, thao tác, trạng thái backend cần quan sát và kết quả. Ví dụ “nút Logout chuyển về trang login” là bằng chứng giao diện; “cookie cũ bị từ chối trên mọi node trong phạm vi cam kết” mới trực tiếp kiểm tra việc thu hồi phiên.

Một cách áp dụng Cheat Sheet hiệu quả là gắn từng quyết định vào vòng đời của ứng dụng: tạo phiên cho ai, chấp nhận ID bằng kênh nào, thay đổi ngữ cảnh ra sao, kết thúc khi nào và chứng minh điều đó bằng phép thử nào. Khi quyền truy cập, MFA, SSO hoặc hạ tầng thay đổi, các ranh giới này cũng cần được xem xét lại.
