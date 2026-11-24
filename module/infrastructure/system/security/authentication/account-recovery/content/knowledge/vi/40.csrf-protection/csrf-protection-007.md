# CSRF test coverage: Bao phủ kiểm thử CSRF trong luồng khôi phục tài khoản

Một ca kiểm thử gửi POST thiếu CSRF token và nhận 403 chưa đủ chứng minh luồng khôi phục đã được bảo vệ. Request có thể bị từ chối vì phiên không hợp lệ, token khôi phục đã hết hạn hoặc dữ liệu không đúng định dạng. Endpoint thay đổi MFA khác vẫn có thể bỏ sót kiểm tra.

Bao phủ CSRF cần chứng minh hai điều: yêu cầu hợp lệ từ hành trình được hỗ trợ vẫn thực hiện được; yêu cầu giả mạo không làm phát sinh thay đổi nhạy cảm. Việc đánh giá phải đi qua cả lớp xử lý máy chủ lẫn hành vi thật của trình duyệt.

Bài học này trình bày cách xây dựng phạm vi kiểm thử CSRF cho khôi phục mật khẩu, MFA, passkey và thiết bị xác thực. Các đường dẫn, tên fixture và dữ liệu dưới đây đều là ví dụ để diễn đạt thiết kế kiểm thử.

## 1. Xác định điều cần chứng minh trước khi viết test

CSRF tận dụng việc trình duyệt tự gửi thông tin xác thực, thường là cookie, trong một yêu cầu mà người dùng không chủ động cho phép theo ý nghĩa nghiệp vụ.

Trong luồng khôi phục, cookie liên quan có thể là phiên trước đăng nhập hoặc phiên khôi phục có quyền giới hạn. Không nên chỉ kiểm tra khi người dùng đã có phiên đăng nhập đầy đủ.

Một bộ kiểm thử cần thể hiện các thuộc tính sau:

| Thuộc tính | Điều kiện cần quan sát |
| --- | --- |
| Yêu cầu hợp lệ được chấp nhận | Có đủ bằng chứng khôi phục và CSRF hợp lệ thì thao tác đúng quyền thành công |
| Yêu cầu thiếu bảo vệ bị chặn | Khi các điều kiện khác đều hợp lệ, thiếu hoặc sai CSRF không gây thay đổi nhạy cảm |
| Token gắn đúng ngữ cảnh | Token của phiên hoặc giao dịch khác không được dùng ngoài ràng buộc đã thiết kế |
| Các đường vào cùng được bảo vệ | Endpoint cũ, form HTML, API và alias không tạo đường bỏ qua |
| Trạng thái tài khoản được giữ đúng | Request bị chặn không đổi mật khẩu, MFA, passkey hoặc quyền khôi phục |
| Cơ chế trình duyệt được đánh giá đúng | SameSite, CORS và Fetch Metadata được quan sát trong bối cảnh phù hợp |

CSRF token và token khôi phục có mục đích khác nhau. Có CSRF token hợp lệ không chứng minh người dùng có quyền khôi phục tài khoản. Ngược lại, không được mặc nhiên coi mọi credential khôi phục là biện pháp chống CSRF mà chưa phân tích cách credential được gửi.

OWASP mô tả các cơ chế như synchronizer token, signed double-submit cookie, kiểm tra nguồn và Fetch Metadata. Phạm vi kiểm thử phải bám vào cơ chế hệ thống thực sự triển khai. Xem [OWASP: CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).

## 2. Lập danh mục hành động nhạy cảm

Danh mục nên được xây dựng theo tác động nghiệp vụ, không chỉ theo màn hình đang hiển thị.

| Hành động | Ví dụ đường vào | Trạng thái cần quan tâm |
| --- | --- | --- |
| Bắt đầu yêu cầu khôi phục | POST /recovery/requests | Tạo giao dịch, gửi thông báo và kiểm soát lạm dụng |
| Đổi bằng chứng lấy phiên khôi phục | POST /recovery/exchange | Tài khoản được gắn vào phiên và phạm vi quyền |
| Đặt mật khẩu mới | POST /recovery/password | Mật khẩu, token dùng một lần, giao dịch và phiên liên quan |
| Thay hoặc xóa MFA | POST /recovery/mfa/replace | Danh sách yếu tố và quyền được cấp |
| Bắt đầu đăng ký passkey | POST /recovery/passkeys/options | Challenge và giao dịch được ràng buộc |
| Hoàn tất đăng ký passkey | POST /recovery/passkeys/finish | Credential mới gắn đúng tài khoản |
| Thay kênh khôi phục | POST /recovery/contacts | Địa chỉ hoặc số điện thoại được xác minh |
| Hủy quá trình khôi phục | POST /recovery/cancel | Quyền khôi phục bị chấm dứt đúng phạm vi |

Không phải tất cả endpoint đều có cùng yêu cầu cookie hoặc cùng biện pháp CSRF. Với bước công khai như bắt đầu gửi email khôi phục, cần xác định tác động của yêu cầu bị ép gửi và thiết kế bảo vệ phù hợp; CSRF token cũng không thay thế chống spam hoặc chống dò tài khoản.

GET, HEAD và OPTIONS cần được bao phủ để bảo đảm không thực hiện thay đổi tài khoản hoặc cấp quyền nhạy cảm ngoài thiết kế. Việc mở link email không được tự thay mật khẩu, xóa MFA hoặc hoàn tất đăng ký passkey.

Endpoint có bearer token chỉ được client chủ động đặt trong Authorization có mô hình khác với cookie tự gửi. Cần xác nhận endpoint không âm thầm nhận thêm cookie như một đường xác thực thay thế, làm thay đổi giả định về CSRF.

## 3. Chuẩn bị fixture để thất bại có ý nghĩa

Một fixture tốt tạo ra trạng thái ban đầu đã biết:

- Tài khoản A và B độc lập, với dữ liệu minh họa.
- Phiên khôi phục A đã đủ điều kiện cho một hành động cụ thể.
- Phiên khôi phục B có cookie và CSRF token riêng.
- Credential khôi phục đang còn hiệu lực và chưa sử dụng.
- Payload đáp ứng chính sách nghiệp vụ, chẳng hạn mật khẩu mới hợp lệ.
- Origin và các header khác phù hợp với ca đang xét.

Sau đó, thay đổi đúng yếu tố cần kiểm tra. Nếu muốn chứng minh thiếu CSRF bị chặn, không đồng thời gửi credential khôi phục sai, mật khẩu không hợp lệ và Origin không được phép.

### Tạo dữ liệu mới cho từng ca

Hành động khôi phục thường dùng quyền một lần. Nếu một ca thành công đã tiêu thụ credential, dùng lại nó trong ca thiếu CSRF có thể chỉ chứng minh credential đã bị tiêu thụ.

Mỗi ca cần fixture mới hoặc cơ chế khôi phục trạng thái được thiết kế riêng cho môi trường kiểm thử. Không dùng chung một giao dịch theo thứ tự chạy và không phụ thuộc vào ca trước để chuẩn bị dữ liệu.

### Chụp trạng thái nhạy cảm trước request

Tùy hành động, dữ liệu so sánh có thể gồm:

~~~text
passwordVersion
authenticatorIds
recoveryContactIds
recoveryTransactionState
recoveryCredentialConsumedAt
activeSessionVersions
pendingAuthenticatorBinding
~~~

Đây là các tên thuộc tính minh họa. Không cần đưa mật khẩu, token hoặc mã dự phòng vào báo cáo để so sánh trạng thái.

Request bị chặn có thể vẫn làm tăng bộ đếm lạm dụng hoặc tạo audit event. Vì vậy, “không có thay đổi nhạy cảm” không có nghĩa mọi bản ghi vận hành phải bất biến. Bộ assertion cần phân biệt thay đổi được phép với thay đổi quyền hoặc bí mật tài khoản.

## 4. Ma trận kiểm thử ở phía máy chủ

Ma trận dưới minh họa một endpoint dùng phiên khôi phục bằng cookie và cơ chế CSRF token gắn với phiên. Chính sách Origin và Fetch Metadata được xét thêm ở phần sau.

| Ca | Điều kiện khác | Kỳ vọng |
| --- | --- | --- |
| Có CSRF hợp lệ của đúng phiên | Quyền khôi phục và payload hợp lệ | Thao tác thành công đúng một lần |
| Không gửi CSRF token | Các điều kiện còn lại hợp lệ | Bị chặn, không thay đổi nhạy cảm |
| Token rỗng hoặc chỉ có khoảng trắng | Các điều kiện còn lại hợp lệ | Không được xem là token hợp lệ |
| Token có giá trị ngẫu nhiên sai | Các điều kiện còn lại hợp lệ | Bị chặn |
| Token của phiên B đi cùng phiên A | Hai fixture độc lập | Bị chặn theo ràng buộc phiên |
| Token cũ sau khi bị xoay hoặc thu hồi | Việc xoay đã xảy ra theo chính sách | Không được tiếp tục dùng ngoài chính sách |
| CSRF hợp lệ nhưng quyền khôi phục sai | Payload hợp lệ | Bị từ chối bởi kiểm soát quyền |
| CSRF hợp lệ nhưng giao dịch đã hoàn tất | Có fixture trạng thái hoàn tất | Không thay đổi tài khoản lần hai |
| Header và field form cùng xuất hiện, giá trị mâu thuẫn | Hợp đồng có thể nhận cả hai dạng | Hành vi rõ ràng, không tạo bypass do cách chọn giá trị |
| Nhiều giá trị token trong cùng tham số hoặc header | Request phù hợp với khả năng phân tích của hạ tầng | Từ chối hoặc xử lý theo quy tắc nhất quán đã công bố |
| Đổi content type hoặc HTTP method | Cùng ý định thay đổi tài khoản | Không đi vào đường xử lý thiếu bảo vệ |
| Gọi endpoint cũ hoặc alias | Cùng quyền và payload nghiệp vụ | Không có đường vào bỏ sót CSRF |

Không mặc định CSRF token phải dùng một lần. Một synchronizer token có thể được dùng cho nhiều request trong cùng phiên theo thiết kế. Phải kiểm tra đúng quy tắc vòng đời đang áp dụng, thay vì yêu cầu xoay token sau mọi POST.

Nếu dùng signed double-submit cookie, cần thêm các ca sửa chữ ký, ghép token với phiên khác và thao túng cookie theo mô hình đe dọa. Chỉ chứng minh cookie và field có cùng chuỗi là chưa đủ chứng minh ràng buộc an toàn.

### Không chỉ quan sát mã 403

Khi endpoint trả 403, cần xác định request đã đi qua chuỗi xử lý cần kiểm tra và bị chặn bởi lớp phù hợp. Có thể dùng mã lỗi nội bộ không nhạy cảm, sự kiện bảo mật hoặc bằng chứng rằng service thay đổi tài khoản chưa được gọi.

Đồng thời đọc lại trạng thái nghiệp vụ. Một lỗi nghiêm trọng là hệ thống đã ghi mật khẩu hoặc tiêu thụ token trước khi trả lỗi CSRF.

Ngược lại, một ca thành công phải quan sát thay đổi đúng phạm vi. Chỉ nhận 200 nhưng không kiểm tra việc đặt mật khẩu thực sự diễn ra có thể che giấu một đường xử lý không hoạt động.

## 5. Ví dụ MockMvc cho ứng dụng dùng Spring Security

Spring Security cung cấp bộ hỗ trợ để đưa CSRF token hợp lệ hoặc không hợp lệ vào request MockMvc. Các dạng thường dùng là csrf(), csrf().asHeader() và csrf().useInvalidToken(). Xem [Spring Security: Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html).

Ví dụ dưới giả định MockMvc đã gắn chuỗi filter bảo mật thật của ứng dụng. RecoveryFixture, fixtures.authorizedRecovery(), snapshot() và assertNoSensitiveChanges() là helper của bộ kiểm thử minh họa, không phải API có sẵn của Spring.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@Test
void rejectsMissingCsrfWithoutChangingRecoveryState() throws Exception {
    RecoveryFixture fixture = fixtures.authorizedRecovery();
    var before = fixtures.snapshot(fixture);

    mockMvc.perform(post("/recovery/password")
            .session(fixture.session())
            .header("Origin", "https://accounts.example.test")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("newPassword", fixture.validNewPassword()))
        .andExpect(status().isForbidden());

    fixtures.assertNoSensitiveChanges(before);
}

@Test
void rejectsInvalidCsrfWithoutChangingRecoveryState() throws Exception {
    RecoveryFixture fixture = fixtures.authorizedRecovery();
    var before = fixtures.snapshot(fixture);

    mockMvc.perform(post("/recovery/password")
            .session(fixture.session())
            .header("Origin", "https://accounts.example.test")
            .with(csrf().useInvalidToken())
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("newPassword", fixture.validNewPassword()))
        .andExpect(status().isForbidden());

    fixtures.assertNoSensitiveChanges(before);
}

@Test
void acceptsValidCsrfAndCompletesOnlyTheAuthorizedAction() throws Exception {
    RecoveryFixture fixture = fixtures.authorizedRecovery();

    mockMvc.perform(post("/recovery/password")
            .session(fixture.session())
            .header("Origin", "https://accounts.example.test")
            .with(csrf())
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("newPassword", fixture.validNewPassword()))
        .andExpect(status().isNoContent());

    fixtures.assertPasswordRecoveryCompletedExactlyOnce(fixture);
}
~~~

Mã 204 ở ca thành công là lựa chọn của endpoint minh họa; ứng dụng thực tế có thể dùng mã khác theo hợp đồng. Nếu có lớp Fetch Metadata yêu cầu header bổ sung, fixture cần cung cấp chúng theo đúng tình huống.

Điểm cần giữ trong các ví dụ:

- Không tắt filter bảo mật để làm cho request vào được controller.
- Không biến fixture khôi phục thành phiên đăng nhập toàn quyền nếu luồng thật chỉ có phiên giới hạn.
- Mỗi phương thức tạo một fixture mới.
- Cả ca âm tính lẫn ca dương tính đều dùng payload nghiệp vụ hợp lệ.
- Assertion kiểm tra tác động tài khoản, không chỉ HTTP status.

Helper csrf() thuận tiện để kiểm tra tích hợp filter, nhưng không chứng minh trang thật phát token đúng hoặc JavaScript thật gửi token đúng. Nó cũng không tự chứng minh token A bị ràng buộc với phiên A.

Để kiểm tra việc ràng buộc, cần lấy token do hệ thống thật phát hành cho hai phiên, giữ đúng cookie hoặc session tương ứng, rồi chủ động hoán đổi. Khi ứng dụng có token repository hoặc request handler tùy chỉnh, cần có ca đi qua chính đường phát hành và kiểm tra đó.

## 6. Kiểm tra Origin và Fetch Metadata theo chính sách

Nguồn request cần được xét theo scheme, host và port. Không kiểm tra bằng cách tìm một chuỗi con giống tên miền tin cậy.

Ví dụ ứng dụng chạy ở:

~~~text
https://accounts.example.test
~~~

Các bối cảnh cần phân biệt:

| Nguồn gửi | Quan hệ với ứng dụng | Điều cần chứng minh |
| --- | --- | --- |
| https://accounts.example.test | Same-origin | Hành trình hợp lệ hoạt động khi đủ các điều kiện |
| https://untrusted.example.test | Same-site nhưng khác origin | Subdomain không tin cậy không được mặc nhiên có quyền |
| https://accounts.example.test:8443 | Cùng site nhưng khác port và origin | Bộ kiểm tra origin không bỏ sót port |
| https://attacker.other.test | Cross-site | Yêu cầu thay đổi trạng thái bị xử lý theo chính sách chống giả mạo |
| Origin: null | Nguồn opaque hoặc bối cảnh đặc biệt | Không tự coi chuỗi null là nguồn tin cậy |
| Không có Origin | Thiếu tín hiệu | Áp dụng fallback đã được thiết kế, không tự bỏ toàn bộ kiểm tra |

Đây là các hostname dành cho môi trường kiểm thử được cấu hình riêng; chúng không chỉ tới một dịch vụ khôi phục thật.

Sec-Fetch-Site mô tả quan hệ same-origin, same-site, cross-site hoặc none. Header này là tín hiệu ngữ cảnh, không phải bằng chứng khôi phục. Xem [MDN: Sec-Fetch-Site](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site).

Nếu chính sách yêu cầu từ chối cross-site trên endpoint nhạy cảm, cần ca có CSRF hợp lệ nhưng nguồn bị từ chối để chứng minh quy tắc này thực sự có tác dụng. Nếu cho phép một frontend khác origin, cần có ca riêng cho origin được cho phép và ca cho origin gần giống nhưng không nằm trong danh sách.

Với trường hợp thiếu Fetch Metadata, ghi rõ cơ chế dự phòng: chẳng hạn CSRF token và xác minh nguồn theo khả năng hỗ trợ, hoặc từ chối trên endpoint đặc biệt nhạy cảm. Không xem việc thiếu header là dấu hiệu request an toàn.

Một HTTP test client có thể tự đặt header mà JavaScript trong trình duyệt không được tự do đặt. Vì vậy, test header phía máy chủ đánh giá nhánh quyết định của server; nó không thay thế việc quan sát header mà trình duyệt thực sự sinh.

## 7. Cần có kiểm thử bằng trình duyệt thật

MockMvc không mô phỏng đầy đủ quy tắc cookie, điều hướng, CORS và Fetch Metadata của trình duyệt.

Một bộ tình huống trình duyệt có thể gồm:

1. Mở hành trình khôi phục hợp lệ trên origin của ứng dụng.
2. Xác nhận cookie và trạng thái khôi phục đã hình thành đúng thiết kế.
3. Mở trang mô phỏng nguồn không tin cậy trong cùng browser context của người dùng.
4. Gửi form hoặc yêu cầu theo tình huống cần đánh giá.
5. Quan sát request thật, phản hồi máy chủ và trạng thái tài khoản sau request.
6. Lặp lại bằng fixture mới cho các nguồn và kiểu gửi khác nhau.

Hai người dùng A và B cần browser context độc lập để tránh vô tình dùng chung cookie. Riêng trang mô phỏng nguồn giả mạo phải được mở trong context đang giữ phiên của người dùng cần đánh giá; nếu dùng một context hoàn toàn trống, kết quả có thể chỉ chứng minh không có phiên.

### Form cross-site không cần đọc response

Một trang từ origin không tin cậy có thể chứa form minh họa:

~~~html
<form action="https://accounts.example.test/recovery/password" method="post">
  <input type="hidden" name="newPassword" value="GiaTriMinhHoaChoKiemThu">
  <button type="submit">Gửi tình huống kiểm thử</button>
</form>
~~~

Đây là dữ liệu cho môi trường kiểm thử riêng. Form không có CSRF token hợp lệ; kỳ vọng là không có thay đổi nhạy cảm.

Nếu trình duyệt không gửi cookie do SameSite, tình huống đó chứng minh một lớp bảo vệ trình duyệt có tác dụng trong bối cảnh đã chọn. Nó chưa chứng minh server từ chối CSRF khi một request khác vẫn mang được cookie.

Vì thế cần thêm ca same-site từ subdomain không tin cậy và ca máy chủ độc lập để đánh giá lớp kiểm tra token. Không nới chính sách cookie của sản phẩm chỉ để ép một tình huống chạy rồi coi đó là bằng chứng cho cấu hình đang triển khai.

### CORS chặn đọc không đồng nghĩa thao tác bị chặn

Một số request có thể được gửi mà trang gọi không được đọc response. Do đó, lỗi CORS trong console không đủ để kết luận tài khoản không thay đổi. Cần xem request tới server và trạng thái nghiệp vụ.

Với JSON hoặc custom header, trình duyệt có thể gửi preflight. Cần bao phủ cả đường bị chặn tại preflight và đường request thực sự tới ứng dụng. Xem [MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).

### SameSite cần được quan sát đúng

Kiểm tra thuộc tính cookie được phát thật và các bối cảnh cần hỗ trợ. Không suy luận rằng mọi POST cross-site đều không mang cookie.

MDN lưu ý một số trình duyệt có cách áp dụng Lax mặc định dễ dãi hơn đối với cookie mới được đặt, bao gồm một khoảng thời gian ngắn cho POST. Điều này khác với việc chủ động cấu hình SameSite=Lax. Xem [MDN: Set-Cookie và SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#samesitesamesite-value).

Không cần dựa vào một hành vi mặc định thay đổi theo trình duyệt để bảo vệ thao tác nhạy cảm. Bộ kiểm thử nên ghi lại browser và cấu hình thực sự đã đánh giá.

## 8. Bao phủ toàn hành trình và vòng đời phiên

Chỉ kiểm tra endpoint đặt mật khẩu là chưa đủ. Một yêu cầu giả mạo ở bước trước có thể làm phiên gắn với giao dịch khác hoặc chuẩn bị một thay đổi yếu tố không đúng ý người dùng.

Các tình huống cần đưa vào phạm vi:

| Tình huống | Kỳ vọng nghiệp vụ |
| --- | --- |
| Trình duyệt chưa đăng nhập nhưng có pre-session | Cơ chế bảo vệ trước đăng nhập vẫn có hiệu lực |
| Đổi bằng chứng sang phiên khôi phục | Không bị ép gắn vào giao dịch ngoài ý định |
| Có phiên đăng nhập A nhưng khôi phục B | Không âm thầm chọn nhầm tài khoản đích |
| Hai tab giữ token ở các thời điểm khác nhau | Hành vi theo chính sách vòng đời, không tự bỏ CSRF để chữa lỗi |
| Hủy hoặc hết hạn phiên khôi phục | Token CSRF còn lại không tạo lại quyền đã mất |
| Quay lại trang bằng Back sau khi hoàn tất | Gửi lại form không thay đổi tài khoản lần hai |
| Đăng ký passkey thay thế | Cả bước lấy challenge và hoàn tất đều theo đúng quyền và ngữ cảnh |
| Chuyển sang phương án khôi phục khác | Không có endpoint dự phòng bỏ qua bảo vệ |
| Dùng endpoint hoặc schema cũ | Các ràng buộc bảo mật vẫn được áp dụng |

Cần phân biệt lỗi CSRF với chống phát lại. CSRF token hợp lệ có thể vẫn bị từ chối vì quyền khôi phục đã dùng; đó là một kiểm soát khác. Bộ kiểm thử nên có bằng chứng riêng cho mỗi thuộc tính.

Đồng thời, CSRF không thay thế kiểm soát XSS. Nếu mã độc đã chạy trong cùng origin, nó có thể tương tác với trang và token theo những cách ngoài giả định của một cuộc tấn công từ origin khác.

## 9. Đọc coverage bằng kịch bản, không chỉ bằng phần trăm dòng mã

Một báo cáo có nhiều dòng code được chạy vẫn có thể bỏ sót toàn bộ endpoint thay MFA hoặc chưa từng gửi một request có cookie từ subdomain không tin cậy.

Cách tổng hợp hữu ích là ánh xạ:

~~~text
hành động nghiệp vụ
    -> đường vào và phương thức
    -> loại phiên hoặc credential
    -> cơ chế CSRF đang áp dụng
    -> tình huống hợp lệ và giả mạo
    -> trạng thái tài khoản cần quan sát
~~~

Mỗi kết quả nên có fixture, điều kiện request, kỳ vọng, phản hồi thực tế và so sánh trạng thái sau cùng. Thông tin nhạy cảm cần được che hoặc loại khỏi dữ liệu báo cáo.

Các dấu hiệu coverage còn thiếu gồm: mọi test đều dùng csrf() hợp lệ; mọi ca âm tính đều thiếu cả quyền khôi phục; toàn bộ kiểm thử chỉ chạy trong một origin; không có ca thành công; hoặc chỉ xem console trình duyệt mà không đọc lại trạng thái tài khoản.

Bao phủ CSRF có ý nghĩa khi nó chỉ ra đường hợp lệ vẫn hoạt động và mọi đường thay đổi tài khoản đã được xét trong các bối cảnh giả mạo liên quan. Kết luận phải gắn với cơ chế, hành trình và môi trường đã quan sát, thay vì coi một mã 403 hay một con số coverage là bảo đảm cho toàn hệ thống.

