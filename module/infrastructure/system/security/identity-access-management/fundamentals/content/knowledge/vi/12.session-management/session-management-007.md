# Idle timeout — Giới hạn thời gian không hoạt động của phiên

## 1. Idle timeout bảo vệ điều gì?

Idle timeout, hay inactivity timeout, là giới hạn thời gian một phiên được tiếp tục sử dụng khi không có hoạt động được chính sách chấp nhận. Khi khoảng thời gian đó hết, backend không cho phép phiên tiếp tục truy cập tài nguyên bảo vệ nếu chưa đáp ứng quy trình xác thực lại phù hợp.

Ví dụ, một nhân viên mở hồ sơ nhân sự rồi rời máy mà không đăng xuất. Nếu phiên không có giới hạn không hoạt động, người đến sau có thể tiếp tục sử dụng danh tính và quyền của nhân viên đó. Idle timeout giảm khoảng thời gian phiên bị bỏ quên còn có thể dùng được.

OWASP mô tả idle timeout theo khoảng không hoạt động kể từ request của phiên, đồng thời yêu cầu thực thi hết hạn tại server. Bộ đếm ở trình duyệt không thể là nơi quyết định duy nhất vì client có thể bị sửa hoặc bỏ qua. [Nguồn: OWASP Session Management Cheat Sheet, Idle Timeout](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html#idle-timeout).

Trong hệ thống IAM, idle timeout là một phần quản lý vòng đời phiên. Nó không thay thế MFA, phân quyền RBAC/ABAC hoặc khóa màn hình của thiết bị. Một phiên chưa hết hạn cũng không tự chứng minh người đang cầm máy là người đã xác thực ban đầu.

## 2. Phân biệt các giới hạn thường bị gọi chung là timeout

| Giới hạn | Mốc dùng để tính | Điều kiện làm mới |
| --- | --- | --- |
| Idle timeout | Hoạt động hợp lệ gần nhất của phiên | Hoạt động được chính sách chấp nhận, trước khi hết hạn |
| Giới hạn tổng thể của phiên hoặc chu kỳ xác thực | Lần tạo phiên hoặc xác thực lại được chấp nhận | Theo chính sách xác thực lại; không chỉ do có request |
| Thời gian sống cookie | Thời điểm hoặc thời lượng lưu cookie ở client | Khi server phát lại cookie theo cấu hình |
| Hạn `exp` của token | Giá trị đã được phát hành trong token | Cấp token mới theo quy trình riêng |
| Timeout kết nối HTTP, proxy hoặc TCP | Hoạt động của kết nối mạng | Lưu lượng ở tầng kết nối |
| Độ mới của bằng chứng cho thao tác nhạy cảm | Lần xác thực đáp ứng yêu cầu của thao tác | Xác thực lại hoặc step-up thích hợp |

NIST phân biệt inactivity timeout và overall timeout: hoạt động phiên làm mới giới hạn không hoạt động, còn xác thực lại thành công có thể làm mới cả hai theo chính sách. Các mức assurance có yêu cầu khác nhau, nên không có một con số duy nhất phù hợp cho mọi dịch vụ. [Nguồn: NIST SP 800-63B-4, Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b.html#reauthentication).

Một request tải hồ sơ có thể làm mới idle timeout nhưng không tự biến bằng chứng MFA đã cũ thành bằng chứng vừa được thực hiện. Tương tự, cookie còn nằm trong trình duyệt không có nghĩa là bản ghi phiên ở server vẫn hợp lệ.

Trong phần còn lại, cổng nhân sự giả định áp dụng idle timeout 15 phút và một mốc hết hạn tổng thể 8 giờ cho chu kỳ đang xét. Đây là giá trị minh họa do nhóm thiết kế lựa chọn, không phải cấu hình bắt buộc hoặc tuyên bố đáp ứng một chuẩn cụ thể.

## 3. Mô hình thời gian và quy tắc tại ranh giới

Giả sử backend lưu:

```text
last_eligible_activity_at
idle_window
idle_expires_at
overall_expires_at
status
```

Quy tắc của ví dụ:

```text
idle_expires_at = min(
    last_eligible_activity_at + idle_window,
    overall_expires_at
)

Request chỉ được tiếp tục nếu:
    status == ACTIVE
    now < idle_expires_at
    now < overall_expires_at
```

`now` đến từ nguồn thời gian được server tin cậy. Client không được gửi `lastActivity=now` rồi yêu cầu backend tin đó là mốc gia hạn.

Ví dụ không có hoạt động hợp lệ mới sau 09:08:

| Thời điểm | Sự kiện | Deadline idle tại server |
| --- | --- | --- |
| 09:00 | Hoàn tất xác thực, tạo phiên | 09:15 |
| 09:08 | Người dùng gửi request nghiệp vụ được chấp nhận | 09:23 |
| 09:14 | Request nền không được tính là hoạt động theo chính sách | Vẫn 09:23 |
| 09:23 | Chạm deadline | Phiên không còn được chấp nhận cho truy cập bảo vệ |
| 09:24 | Client gửi request mới với cookie cũ | Bị từ chối; không tự gia hạn |

Trong mô hình này, tại đúng deadline sử dụng điều kiện `now >= deadline` để hết hạn. Phải định nghĩa ranh giới nhất quán giữa các thành phần; không để một node dùng `>` còn node khác dùng `>=`.

Nếu có hoạt động hợp lệ lúc 09:22, deadline có thể chuyển đến 09:37 nhưng vẫn không được vượt mốc tổng thể đã đặt. Sau khi hết hạn, request mới phải đi vào xử lý hết phiên hoặc xác thực lại, không được cập nhật thời gian trước rồi coi phiên như chưa từng hết hạn.

## 4. “Hoạt động” là một quyết định chính sách

Backend quan sát được request, thông điệp và các bằng chứng mà client trình. Nó không trực tiếp nhìn thấy người dùng còn ngồi trước màn hình. Vì vậy, phải làm rõ loại sự kiện nào được dùng để duy trì phiên.

Đối với cổng nhân sự của bài, nhóm thiết kế chọn:

| Sự kiện | Có gia hạn idle của phiên xác thực trong ví dụ? | Lý do |
| --- | --- | --- |
| Request nghiệp vụ do người dùng chủ động thực hiện và được chấp nhận | Có | Thể hiện hoạt động của luồng sử dụng ứng dụng |
| Tải thông báo tự động theo chu kỳ | Không | Có thể tiếp tục khi không có người dùng |
| Heartbeat kỹ thuật | Không | Chứng minh kết nối hoặc tiến trình còn chạy, không chứng minh người dùng hiện diện |
| Tự refresh access token | Không mặc nhiên | Cấp lại token và hoạt động của người dùng là hai sự kiện khác nhau |
| Di chuột trong trang | Không tự quyết định tại server | Tín hiệu client có thể bị tạo giả |
| Tab đang hiển thị nhưng không gửi tương tác | Không có bằng chứng mới tại server | Tình trạng tab không phải sự kiện xác thực |
| Xác thực lại thành công | Xử lý theo chính sách reauthentication | Có bằng chứng mới để thiết lập lại giới hạn thích hợp |

Bảng này là chính sách minh họa về hoạt động đủ điều kiện, không phải hành vi mặc định của mọi framework. Nhiều container tính tất cả request liên quan đến session là truy cập phiên. Muốn loại polling hoặc heartbeat khỏi giới hạn an ninh cần thiết kế và thực thi riêng, không chỉ ghi chú ở frontend.

Một endpoint “giữ phiên” cũng cần được đánh giá theo mô hình đe dọa. Nếu chỉ cần có bearer cookie là có thể gọi liên tục, kẻ lấy được cookie cũng có thể giữ phiên hoạt động. Idle timeout không bảo đảm ngắt được một đối thủ đang chủ động phát request.

Không coi việc nhận chuỗi `userIsActive=true` là xác thực lại. Tín hiệu tương tác có thể hỗ trợ trải nghiệm, nhưng không thay mật khẩu, MFA hoặc phương thức xác thực mà chính sách yêu cầu.

## 5. Kiểm tra trước, cập nhật sau, không hồi sinh phiên hết hạn

Một lỗi nguy hiểm là gán `last_activity=now` ngay khi nhận request rồi mới kiểm tra timeout. Cách đó làm mọi request, kể cả request đến sau deadline, tự kéo dài phiên trước khi quyết định hết hạn được thực hiện.

Mã giả cho session store có thể tổ chức như sau:

```text
evaluateSession(presentedSessionCredential, activityClassification):
    thực hiện nguyên tử tại nơi giữ trạng thái chuẩn:
        now = trustedServerTime()
        session = loadAndVerifyCurrentCredential(presentedSessionCredential)

        if session không tồn tại hoặc không ACTIVE:
            return SESSION_NOT_VALID

        if now >= session.idleExpiresAt
           or now >= session.overallExpiresAt:
            markExpiredWithoutRevival(session)
            return SESSION_EXPIRED

        if activityClassification được server chấp nhận:
            session.lastEligibleActivityAt = now
            session.idleExpiresAt = min(
                now + session.idleWindow,
                session.overallExpiresAt
            )
            saveWithVersionCheck(session)

        return VALID_SESSION_CONTEXT
```

Đây là mô hình điều phối, không phải một bộ xác thực hoàn chỉnh. Credential phải được xác minh với bản ghi hiện tại trước khi gia hạn; biết một mã tham chiếu phiên không đủ để cập nhật hoạt động. Trước khi dùng context để xử lý tài nguyên, vẫn cần kiểm tra trạng thái tài khoản, tenant và quyền truy cập tương ứng. Việc phân loại hoạt động phải do server quyết định theo hợp đồng đã thiết kế.

Tính nguyên tử có thể được thực hiện bằng transaction, khóa phù hợp hoặc thao tác cập nhật có điều kiện của session repository. Không dùng một snapshot đã cũ rồi ghi lại toàn bộ bản ghi, vì request khác có thể vừa thu hồi hoặc làm phiên hết hạn.

Đường ghi nhận hết hạn cũng phải giữ được trạng thái cần thiết. Nếu cập nhật `EXPIRED` rồi ném exception khiến transaction rollback, không được dựa vào bản ghi `EXPIRED` chưa lưu để quyết định các request sau. Dù cleanup chưa chạy, điều kiện deadline vẫn phải làm request bị từ chối.

## 6. Server timeout, TTL và cleanup có vai trò khác nhau

Trong một kho phiên có TTL, dữ liệu có thể bị xóa tự động khi đến hạn. Trong một kho khác, job cleanup có thể chạy theo chu kỳ để loại bản ghi cũ. Cả hai cách đều hữu ích cho quản lý tài nguyên, nhưng phải biết điều gì thực sự bảo đảm quyết định truy cập.

Nếu bản ghi vẫn tồn tại đến lần cleanup tiếp theo, backend vẫn phải từ chối nó khi deadline đã qua. Ngược lại, mất bản ghi phiên không cho phép tự tạo lại một phiên xác thực chỉ vì cookie cũ vẫn còn ở client.

Một TTL được refresh ở mỗi lần ghi bất kỳ có thể bị job nền giữ sống. Vì vậy, TTL của dữ liệu và idle deadline của phiên xác thực cần có quan hệ được định nghĩa rõ. Khi một repository đã cung cấp cơ chế hết hạn bảo đảm yêu cầu, cần dùng đúng cơ chế đó thay vì thêm các lớp TTL mâu thuẫn.

Trong hệ thống nhiều node, mọi node cần cùng áp dụng chính sách và trạng thái phiên. Cache cục bộ không được tự gia hạn dựa trên thông tin đã lỗi thời. Nếu không truy cập được dữ liệu cần để quyết định, phải xử lý lỗi theo chính sách đã xác định, thay vì mặc định cho phép vô hạn.

Thời gian cũng là dữ liệu an ninh. Cần kiểm soát lệch đồng hồ giữa node và nơi lưu phiên, dùng nguồn thời gian nhất quán trong cập nhật cạnh tranh và tránh để một request ghi mốc cũ đè mốc mới. Với deadline lưu bền vững, không so giá trị đồng hồ đơn điệu của hai tiến trình khác nhau như thể chúng có cùng gốc thời gian.

Nếu tối ưu bằng cách gom cập nhật `last activity`, phải đánh giá sai số. Ghi chậm có thể làm người dùng bị hết hạn sớm, trong khi một TTL được nới quá mức lại có thể làm phiên sống lâu hơn giới hạn dự kiến.

## 7. Ví dụ trong Java Servlet và Spring Boot

Trong Jakarta Servlet, `HttpSession.setMaxInactiveInterval(...)` nhận số giây tối đa giữa các request trước khi container vô hiệu hóa session. Giá trị bằng hoặc nhỏ hơn 0 có nghĩa là không timeout theo cơ chế này. [Nguồn: Jakarta Servlet 6.1, HttpSession](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html#setMaxInactiveInterval(int)).

Ví dụ cấu hình tại thời điểm đã có session hợp lệ:

```java
import jakarta.servlet.http.HttpSession;

public final class SessionIdlePolicy {
    private static final int IDLE_TIMEOUT_SECONDS = 15 * 60;

    private SessionIdlePolicy() {
    }

    public static void configure(HttpSession session) {
        session.setMaxInactiveInterval(IDLE_TIMEOUT_SECONDS);
    }
}
```

Đoạn mã chỉ đặt khoảng không hoạt động cho container. Nó không thêm absolute timeout, không phân biệt polling với tương tác chủ động và không triển khai xác thực hoặc phân quyền.

`getLastAccessedTime()` phản ánh thời điểm container nhận request gắn với session; đọc hoặc ghi session attribute từ mã ứng dụng không tự thay đổi thời gian truy cập đó. Không suy ra rằng một biến `lastMouseMove` trong attribute đã thay đổi thì container đã có chính sách idle theo tương tác người dùng. [Nguồn: Jakarta Servlet, getLastAccessedTime](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html#getLastAccessedTime()).

Với ứng dụng Spring Boot dùng Servlet, một cấu hình minh họa là:

```yaml
server:
  servlet:
    session:
      timeout: 15m
```

Spring Boot có thuộc tính `server.servlet.session.timeout`; khi dùng Spring Session còn có `spring.session.timeout`. Phải kiểm tra thành phần nào thực sự quản lý session trong ứng dụng và cấu hình repository tương ứng. [Nguồn: Spring Boot, Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html).

Không nhầm timeout session với `server.servlet.session.cookie.max-age`, timeout kết nối của container hoặc timeout của load balancer. Nếu ứng dụng dùng WebFlux hoặc một cơ chế token riêng, cấu hình Servlet trên không tự áp dụng cho cơ chế đó.

Nếu yêu cầu nghiệp vụ chỉ tính hoạt động có ý nghĩa của người dùng, có thể cần thêm lớp deadline an ninh hoặc một session repository phù hợp. Chỉ bỏ lời gọi `setAttribute()` ở endpoint polling không bảo đảm request đó ngừng được container tính là truy cập phiên.

## 8. Giao diện cảnh báo phải tuân theo quyết định của server

Đếm ngược ở frontend giúp người dùng hiểu phiên sắp kết thúc và tránh mất công việc. Nó không thay thế kiểm tra backend.

Server có thể cung cấp metadata được phép, chẳng hạn deadline idle hiện tại, mốc tổng thể và thời gian server. Client dùng chúng để hiển thị cảnh báo, rồi cập nhật theo response mới khi cần. Không cần gửi session secret hoặc bản ghi credential trong response này.

Trong cổng nhân sự, nút “Tiếp tục làm việc” chỉ có thể gia hạn nếu server xác nhận phiên còn hợp lệ và thao tác đáp ứng chính sách. Nếu phiên đã hết hạn, nút phải đưa người dùng vào luồng xác thực lại phù hợp, không chỉ đóng hộp cảnh báo hoặc đặt lại bộ đếm cục bộ.

Nếu có endpoint kiểm tra trạng thái phiên, phải bảo đảm chính request kiểm tra không vô tình giữ phiên an ninh sống mãi. Điều này cần được thực thi tại lớp thật sự quản lý idle, đặc biệt khi container mặc định tính request là hoạt động.

Trình duyệt có thể làm chậm timer ở tab nền, thiết bị có thể sleep và người dùng có thể sửa giờ hệ thống. Khi tab hoạt động trở lại, cần xác nhận trạng thái với server, thay vì tin rằng bộ đếm JavaScript đã chạy chính xác suốt thời gian đó.

Với biểu mẫu dài, có thể cảnh báo và hỗ trợ lưu nháp theo chính sách dữ liệu. Không tự chuyển hồ sơ nhạy cảm vào `localStorage` để tránh mất dữ liệu sau timeout; nơi lưu nháp, quyền đọc và thời hạn của bản nháp cũng cần được thiết kế.

## 9. Nhiều tab, WebSocket và request chạy dài

Các tab dùng chung cookie thường dùng chung phiên. Một request hợp lệ ở tab A có thể làm mới deadline của phiên mà tab B đang sử dụng. Đóng tab B không tự thu hồi phiên dùng ở tab A.

Nếu mỗi tab tự đếm ngược độc lập, giao diện có thể báo hết hạn không nhất quán. Các tab có thể trao đổi metadata trạng thái để đồng bộ trải nghiệm, nhưng chỉ backend quyết định phiên được tiếp tục hay không.

WebSocket ping/pong hoặc SSE giữ kết nối không mặc nhiên chứng minh người dùng hoạt động. Kết nối được mở khi phiên còn hợp lệ cũng không có nghĩa nó được quyền hoạt động mãi sau khi phiên hết hạn hoặc tài khoản bị vô hiệu hóa. Cần chính sách cho kiểm tra lại, xử lý thông điệp và đóng kênh khi trạng thái không còn phù hợp.

Đối với request chạy dài, phải chọn rõ thời điểm ghi nhận hoạt động và thời điểm cần kiểm tra lại trước tác động nhạy cảm. Một lần bắt đầu tải file, xuất báo cáo hoặc gửi job không tự chứng minh người dùng liên tục hiện diện trong toàn bộ thời gian thực thi.

Job nền đã được cấp quyền chạy theo mô hình riêng cũng không nên gọi endpoint giữ phiên thay người dùng. Cần phân biệt quyền của một tác vụ đã được chấp nhận với quyền tiếp tục dùng phiên tương tác.

## 10. MFA, refresh token và SSO sau khi idle hết hạn

Khi idle timeout xảy ra, tài nguyên bảo vệ không được tiếp tục chấp nhận phiên theo trạng thái cũ. Sản phẩm có thể thiết kế luồng xác thực lại hoặc cơ chế khôi phục phiên theo yêu cầu assurance, nhưng phải thu thập đúng bằng chứng cần thiết.

Không bắt buộc mọi hệ thống luôn yêu cầu lại tất cả factor trong mọi trường hợp. Chẳng hạn, NIST có điều kiện riêng cho reauthentication ở AAL2 khi chỉ inactivity timeout đã xảy ra còn overall timeout chưa hết. Việc lựa chọn phải theo mức bảo vệ và chính sách cụ thể, không phải theo cờ “đã bật MFA” của tài khoản. [Nguồn: NIST SP 800-63B-4, AAL2 Reauthentication](https://pages.nist.gov/800-63-4/sp800-63b.html#aal2).

Một refresh token còn hiệu lực có thể tiếp tục xin access token trong phạm vi được cấp. Nếu ứng dụng chỉ kiểm tra chữ ký và `exp` của access token, việc session giao diện hết idle chưa chắc đã ngăn các API tiếp tục hoạt động. Cần xác định quan hệ giữa phiên tương tác, token và quyền truy cập thực tế.

Trong SSO, IdP và ứng dụng có thể có phiên và deadline riêng. Khi ứng dụng yêu cầu reauthentication, IdP có thể vẫn có phiên cũ và phát assertion mới mà người dùng chưa thực hiện bằng chứng mới. Ứng dụng phải kiểm tra mức xác thực và độ mới cần thiết, không coi mọi lần redirect thành công là người dùng vừa xác thực lại. [Nguồn: NIST, Reauthentication trong federation](https://pages.nist.gov/800-63-4/sp800-63b.html#reauthentication).

Idle timeout cũng không tự cập nhật quyền. Nếu người dùng bị gỡ vai trò trong RBAC hoặc thuộc tính ABAC thay đổi, quyền mới cần được thực thi theo cơ chế cập nhật của hệ thống, kể cả khi phiên vẫn còn hoạt động.

## 11. Lựa chọn ngưỡng và theo dõi tác động

Ngưỡng phù hợp phụ thuộc tài nguyên, môi trường và cách người dùng làm việc. Máy dùng chung ở quầy tiếp nhận, cổng quản trị đặc quyền và ứng dụng đọc nội dung công khai có mức rủi ro khác nhau.

Cần cân nhắc dữ liệu đang mở trên màn hình, quyền có thể thực hiện, khả năng khóa thiết bị, thời gian hoàn thành công việc và quy trình xác thực lại. Các yêu cầu chuẩn hoặc chính sách tổ chức áp dụng cho hệ thống cũng phải được xác định trước khi chọn giá trị.

Nếu chức năng quản trị có ngưỡng chặt hơn, backend phải thực thi ngưỡng đó trên các API tương ứng. Không chỉ đặt timer ngắn ở màn hình quản trị trong khi cùng phiên vẫn gọi được endpoint đặc quyền từ nơi khác.

Các chỉ số hữu ích gồm số phiên hết idle, tỷ lệ xác thực lại thất bại, request bị từ chối sau deadline, mức sử dụng polling, độ lệch deadline giữa node và các trường hợp người dùng mất công việc. Dữ liệu quan sát không được chứa cookie hoặc token phiên thô.

Nếu thay đổi chính sách khi phiên đang hoạt động, phải quyết định cách áp dụng cho phiên cũ: hiệu lực ngay, sau xác thực lại hoặc theo lộ trình được kiểm soát. Lưu phiên bản chính sách và xác minh nơi thực thi giúp tránh mỗi node áp dụng một ngưỡng khác nhau.

## 12. Tình huống kiểm chứng thiết kế

| Tình huống | Kết quả mong đợi với chính sách của bài |
| --- | --- |
| Không có hoạt động hợp lệ đến đúng deadline | Request bảo vệ bị từ chối |
| Hoạt động hợp lệ trước deadline | Idle được gia hạn nhưng không vượt mốc tổng thể |
| Request đến sau deadline | Không làm mới rồi hồi sinh phiên |
| Polling chạy liên tục trong lúc người dùng rời máy | Không kéo dài deadline an ninh nếu chính sách loại polling |
| Chỉ sửa thời gian hoặc tắt JavaScript ở client | Không vượt được quyết định hết hạn của backend |
| Hai request cập nhật cạnh tranh | Không ghi mốc cũ đè mốc mới hoặc phục hồi trạng thái đã thu hồi |
| Job cleanup chưa xóa bản ghi | Phiên hết hạn vẫn bị từ chối |
| Client có token còn `exp` nhưng phiên tương tác đã hết idle | Áp dụng đúng chính sách truy cập đã thiết kế, không chỉ tin timer giao diện |
| Chuyển tab hoặc thiết bị sleep rồi mở lại | Giao diện đồng bộ lại với server |
| IdP phát kết quả mới từ phiên cũ | Không tự coi đó là bằng chứng xác thực vừa diễn ra |
| Thay ngưỡng khi phiên đã tồn tại | Các node áp dụng cùng quy tắc chuyển đổi |

Khi kiểm tra logic thời gian, nên dùng nguồn thời gian có thể điều khiển trong môi trường thử nghiệm để kiểm tra ngay trước, đúng và sau deadline. Chỉ chờ thực tế vài phút rồi thấy trình duyệt chuyển trang sẽ bỏ sót nhiều lỗi ở backend và ranh giới thời gian.

## 13. Bài tập vận dụng

Một cổng quản trị đặt idle timeout 15 phút. Giao diện kiểm tra thông báo mỗi 30 giây và container coi mỗi request là một lần truy cập session. JavaScript hiển thị cảnh báo hết hạn sau 15 phút không di chuột, nhưng API vẫn chấp nhận cookie. Ngoài ra, một job cleanup chạy mỗi 10 phút và các node có cache phiên riêng.

Hãy đề xuất thiết kế thay thế và trả lời:

1. Hệ thống hiện đang đo sự không hoạt động của người dùng hay sự không hoạt động của request?
2. Lớp nào phải kiểm tra deadline để request bị từ chối dù JavaScript không chạy và cleanup chưa tới lượt?
3. Cần xử lý polling, endpoint kiểm tra trạng thái và nút “Tiếp tục làm việc” như thế nào?
4. Phải cập nhật deadline ra sao để request cạnh tranh không hồi sinh phiên hết hạn hoặc đã bị thu hồi?
5. Khi chuyển qua IdP để xác thực lại, cần bằng chứng gì để biết yêu cầu của ứng dụng đã được đáp ứng?

Phương án cần nêu rõ hoạt động được chấp nhận, nguồn thời gian, quy tắc ranh giới và nơi thực thi. Idle timeout trở thành một kiểm soát của nền tảng IAM khi backend thực sự ngừng chấp nhận phiên theo chính sách, còn giao diện giúp người dùng hiểu và tiếp tục công việc bằng quy trình phù hợp.
