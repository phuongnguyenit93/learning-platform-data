# Dữ liệu nhạy cảm, thời gian giữ lại và trách nhiệm thu hồi

Spring Session giúp ứng dụng Servlet lưu phiên ở kho dữ liệu dùng chung như Redis hoặc JDBC. Trình duyệt giữ cookie chứa session ID; các thuộc tính phiên được lưu phía máy chủ và được khôi phục khi request mang cookie hợp lệ đến. Cách tổ chức này hỗ trợ nhiều instance cùng phục vụ một người dùng, nhưng không tự quyết định dữ liệu nào nên được lưu, giữ trong bao lâu hoặc ai phải thu hồi phiên.

Một phiên vẫn có thể chứa thông tin nhạy cảm dù dữ liệu không nằm trong cookie. Người có quyền đọc Redis, cơ sở dữ liệu, bản sao lưu hoặc heap dump có thể tiếp cận dữ liệu đó. Vì vậy, thiết kế session cần có chính sách dữ liệu, thời hạn rõ ràng và quy trình thu hồi khi người dùng đăng xuất, tài khoản bị khóa hoặc quyền truy cập thay đổi.

## 1. Xác định dữ liệu nào được phép nằm trong session

Session phù hợp để giữ một lượng nhỏ trạng thái tạm thời cần thiết cho các request liên tiếp, ví dụ mã giỏ hàng, lựa chọn giao diện, trạng thái quy trình nhiều bước hoặc thông tin xác thực mà framework quản lý. Trước khi thêm một thuộc tính, hãy trả lời ba câu hỏi:

1. Request tiếp theo có thực sự cần giá trị này không?
2. Có thể lưu một mã tham chiếu ngắn rồi đọc dữ liệu từ dịch vụ nghiệp vụ khi cần không?
3. Nếu session bị đọc trái phép, bị sao chép hoặc tồn tại lâu hơn dự kiến, hậu quả là gì?

Một cách phân loại thực tế:

| Loại dữ liệu | Ví dụ | Cách xử lý trong session |
|---|---|---|
| Trạng thái giao diện tạm thời | Ngôn ngữ, tab đang chọn, bộ lọc tìm kiếm | Có thể lưu nếu nhỏ và có thời hạn |
| Mã tham chiếu nghiệp vụ | `cartId`, `draftId`, `workflowId` | Thường phù hợp; kiểm tra quyền sở hữu ở mỗi lần sử dụng |
| Định danh người dùng | Principal name hoặc user ID | Chỉ lưu khi cần; tránh dùng nó thay cho bước xác thực và kiểm tra quyền |
| Dữ liệu cá nhân | Email, số điện thoại, địa chỉ | Hạn chế; ưu tiên tra cứu từ dịch vụ có kiểm soát quyền và audit |
| Bí mật xác thực | Mật khẩu, mã OTP, refresh token, API key | Không lưu trực tiếp trong session nếu không có thiết kế bảo mật chuyên biệt; tuyệt đối không lưu mật khẩu dạng rõ |
| Dữ liệu thanh toán nhạy cảm | Số thẻ đầy đủ, mã CVV, dữ liệu xác thực thanh toán | Không lưu trong session; dùng nhà cung cấp thanh toán và token tham chiếu theo yêu cầu của họ |
| Dữ liệu lớn hoặc object miền phức tạp | Toàn bộ giỏ hàng, entity ORM, kết quả truy vấn lớn | Tránh; lưu ở kho nghiệp vụ và giữ mã tham chiếu trong session |

Không nên xem Redis hoặc JDBC là vùng an toàn tuyệt đối. Session store vẫn có thể bị truy cập qua tài khoản vận hành, lỗi phân quyền, bản sao lưu, log chẩn đoán, công cụ giám sát hoặc sự cố máy chủ. Dữ liệu nhạy cảm lưu phía máy chủ vẫn cần giới hạn quyền đọc, mã hóa đường truyền, bảo vệ dữ liệu lưu trữ và thời gian giữ lại tối thiểu.

## 2. Áp dụng nguyên tắc tối thiểu hóa dữ liệu

Chỉ lưu thuộc tính thực sự cần để xử lý request tiếp theo. Nếu một trang cần hiển thị tên và ảnh đại diện, có thể giữ user ID trong ngữ cảnh xác thực rồi lấy thông tin hiển thị từ dịch vụ hồ sơ. Tránh sao chép toàn bộ hồ sơ cá nhân vào session vì dữ liệu có thể cũ và tạo thêm nơi cần xóa khi người dùng cập nhật hoặc yêu cầu xóa thông tin.

Ví dụ dưới đây lưu mã tham chiếu giỏ hàng và dùng dịch vụ nghiệp vụ để tải dữ liệu. Dịch vụ vẫn phải xác minh giỏ hàng thuộc về người dùng hiện tại:

```java
@PostMapping("/cart/select")
public String selectCart(HttpServletRequest request,
                         @RequestParam String cartId) {
    HttpSession session = request.getSession(true);
    session.setAttribute("cartId", cartId);
    return "redirect:/cart";
}

@GetMapping("/cart")
public CartView viewCart(HttpServletRequest request,
                         Authentication authentication) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    String cartId = (String) session.getAttribute("cartId");
    if (cartId == null) {
        throw new ResponseStatusException(HttpStatus.NOT_FOUND);
    }

    return cartService.loadForUser(cartId, authentication.getName());
}
```

Ví dụ chỉ minh họa cách lưu mã tham chiếu. Trong ứng dụng thực tế, nên kiểm tra kiểu dữ liệu, xử lý session hết hạn và trả mã trạng thái phù hợp. Không được tin `cartId` chỉ vì nó nằm trong session: dữ liệu session là trạng thái do ứng dụng quản lý, còn quyền truy cập tài nguyên phải được xác minh ở tầng nghiệp vụ.

Không lưu mật khẩu, OTP, câu trả lời khôi phục tài khoản, khóa riêng, API key hoặc dữ liệu thẻ thanh toán vào session. Với access token hoặc refresh token, cần cân nhắc cơ chế lưu trữ và thu hồi dành riêng cho token, thời hạn ngắn, phạm vi quyền tối thiểu và cách bảo vệ khóa. Việc đặt một bí mật vào Redis không làm nó tự động an toàn.

## 3. Bảo vệ kho phiên và đường đi của dữ liệu

Do session chứa trạng thái có thể đại diện cho người dùng đã đăng nhập, session store phải được coi là một thành phần bảo mật quan trọng.

**Với Redis:**

- Chỉ cho phép ứng dụng và thành phần vận hành được ủy quyền kết nối; đặt Redis trong mạng riêng, không phơi cổng trực tiếp ra Internet.
- Bật xác thực và ACL theo nguyên tắc quyền tối thiểu; tách quyền đọc/ghi và môi trường khi hạ tầng hỗ trợ.
- Dùng TLS cho kết nối qua mạng không đáng tin cậy và cấu hình chứng thư đúng cách.
- Đặt chính sách mã hóa dữ liệu lưu trữ và bản sao lưu theo tiêu chuẩn của môi trường.
- Theo dõi dung lượng, eviction, lỗi kết nối, độ trễ và số lượng phiên. Chính sách eviction không được vô tình làm mất dữ liệu phiên đang hoạt động trên diện rộng.
- Dùng namespace phù hợp để tách ứng dụng hoặc môi trường; không xem namespace là biện pháp phân quyền thay cho ACL.

**Với JDBC:**

- Dùng tài khoản database riêng cho ứng dụng, chỉ cấp quyền cần thiết trên các bảng Spring Session.
- Bảo vệ kết nối database bằng TLS khi phù hợp; bảo vệ thông tin đăng nhập trong secret manager hoặc cơ chế quản lý bí mật của nền tảng.
- Áp dụng schema và migration có kiểm soát; giới hạn quyền truy cập trực tiếp của người dùng vận hành.
- Đưa bảng phiên và bản sao lưu vào chính sách backup, retention, phục hồi và xóa dữ liệu của tổ chức.
- Theo dõi dung lượng bảng, index, truy vấn chậm và công việc dọn phiên hết hạn.

Ở cả hai loại kho, không ghi session ID hoặc toàn bộ session attribute vào log. Nếu cần chẩn đoán, ghi mã tương quan request, tên instance, thời điểm, tên cookie và trạng thái có/không có phiên. Nếu cần đối chiếu session ID, dùng giá trị đã che hoặc mã băm có kiểm soát; không sao chép cookie thật vào ticket, chat hoặc hệ thống analytics.

## 4. Phân biệt thời hạn không hoạt động và thời hạn tuyệt đối

Spring Session cung cấp thời gian không hoạt động tối đa của phiên thông qua `maxInactiveInterval`. Khi phiên không được sử dụng trong khoảng thời gian cấu hình, repository xem phiên là hết hạn. Đây thường là chính sách **sliding expiration**: hoạt động hợp lệ có thể làm mới thời điểm truy cập và thời hạn còn lại.

Ví dụ cấu hình Servlet:

```java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1200)
public class SessionConfiguration {
}
```

Trong ví dụ này, thời gian không hoạt động tối đa là 1.200 giây, tức 20 phút. Cấu hình tương tự có thể dùng với JDBC repository bằng annotation tương ứng. Giá trị cụ thể cần dựa trên mức độ nhạy cảm, thời gian người dùng thường thao tác và yêu cầu xác thực lại của ứng dụng.

Thời hạn không hoạt động không đồng nghĩa với **thời hạn tuyệt đối**. Nếu người dùng liên tục gửi request, một phiên có sliding expiration có thể tồn tại lâu hơn nhiều so với 20 phút. Với khu vực nhạy cảm như quản trị, thay đổi thông tin bảo mật hoặc xác nhận giao dịch, có thể cần giới hạn tuổi tối đa kể từ lúc đăng nhập, kể cả khi phiên vẫn hoạt động. Chính sách tuyệt đối cần được thực thi bằng logic ứng dụng hoặc Spring Security phù hợp, chẳng hạn lưu thời điểm xác thực gần nhất và yêu cầu xác thực lại khi vượt ngưỡng.

Ví dụ minh họa kiểm tra thời điểm xác thực:

```java
private static final String AUTHENTICATED_AT = "authenticatedAt";
private static final long MAX_AUTH_AGE_SECONDS = 8 * 60 * 60;

public boolean authenticationTooOld(HttpSession session) {
    Object value = session.getAttribute(AUTHENTICATED_AT);
    if (!(value instanceof Instant authenticatedAt)) {
        return true;
    }

    return Duration.between(authenticatedAt, Instant.now()).getSeconds()
            > MAX_AUTH_AGE_SECONDS;
}
```

Đây là đoạn minh họa cho chính sách tuổi xác thực; mã production cần xử lý múi giờ/đồng hồ, cập nhật timestamp tại đúng thời điểm xác thực, kiểm soát đồng thời và chuyển người dùng qua luồng xác thực lại an toàn. Với Spring Security, ưu tiên tích hợp quy tắc này vào cơ chế xác thực và authorization hiện có thay vì tự tạo một cơ chế đăng nhập riêng trong controller.

Cookie ở trình duyệt có thời hạn riêng. Cookie session có thể là cookie phiên của trình duyệt hoặc có `Max-Age`/`Expires`; thuộc tính này không quyết định TTL của bản ghi trong Redis/JDBC. Nếu cookie còn tồn tại sau khi phiên phía máy chủ hết hạn, session ID đó không khôi phục được dữ liệu cũ. Nếu trình duyệt xóa cookie, bản ghi phía máy chủ cũng không nhất thiết bị xóa ngay. Do đó, cần thiết kế cả hai phía nhưng luôn dựa vào thời hạn và trạng thái phiên phía máy chủ để quyết định quyền truy cập.

## 5. Xây dựng chính sách retention cho session

Retention là thời gian dữ liệu được phép tồn tại và cách dữ liệu được xóa khi không còn mục đích sử dụng. Một chính sách thực tế nên trả lời:

- Loại session nào được tạo và phục vụ mục đích gì?
- Thời gian không hoạt động tối đa là bao lâu?
- Có cần giới hạn tuổi tuyệt đối hoặc yêu cầu xác thực lại không?
- Khi nào phiên bị thu hồi ngay lập tức?
- Repository xóa dữ liệu hết hạn bằng TTL, tác vụ cleanup hay cơ chế nào?
- Bản sao lưu, bản xuất dữ liệu, log và môi trường khôi phục giữ dữ liệu trong bao lâu?
- Ai chịu trách nhiệm theo dõi và xác nhận chính sách đang có hiệu lực?

Ví dụ ma trận chính sách tham khảo:

| Tình huống | Chính sách tham khảo | Lý do |
|---|---|---|
| Phiên duyệt nội dung thông thường | TTL không hoạt động ngắn, phù hợp chu kỳ sử dụng | Giảm thời gian session ID còn hiệu lực |
| Khu vực có dữ liệu cá nhân hoặc thao tác nhạy cảm | TTL ngắn hơn và có thể yêu cầu xác thực lại theo tuổi xác thực | Hạn chế tác động nếu thiết bị bị bỏ quên |
| Phiên quản trị | TTL ngắn, tuổi xác thực tuyệt đối, MFA hoặc xác thực tăng cường cho thao tác quan trọng | Quyền cao làm tăng hậu quả của phiên bị chiếm đoạt |
| Quy trình nhiều bước | Giữ trạng thái tạm thời trong khoảng thời gian công việc cần thiết; xóa khi hoàn tất hoặc hủy | Tránh giữ dữ liệu nháp quá lâu |
| Phiên bị đăng xuất hoặc thu hồi | Vô hiệu hóa ngay ở repository và xóa cookie tương ứng | Ngăn session ID cũ tiếp tục được sử dụng |

Các khoảng thời gian trong ma trận phải được tổ chức chọn theo rủi ro và yêu cầu nghiệp vụ; đây không phải giá trị mặc định bắt buộc cho mọi ứng dụng. Không dùng session để lưu trữ hồ sơ, đơn hàng hoặc dữ liệu nghiệp vụ cần tồn tại lâu dài. Những dữ liệu đó phải ở kho nghiệp vụ có chính sách retention riêng.

TTL là cơ chế hết hạn ở repository, không phải lời đảm bảo rằng mọi byte lập tức biến mất khỏi mọi bản sao. Redis có thể hết hạn khóa theo cơ chế của Redis; JDBC có thể cần tác vụ cleanup để xóa hàng hết hạn. Thời điểm cleanup thực tế phụ thuộc repository, cấu hình và tải hệ thống. Bản sao lưu, snapshot, log hoặc bản xuất có vòng đời riêng và cần được quản lý tương ứng.

## 6. Thu hồi phiên trong các tình huống nghiệp vụ

Thu hồi là làm cho một session ID không còn được chấp nhận để truy cập phiên. Những sự kiện thường cần thu hồi gồm:

- Người dùng chủ động đăng xuất.
- Tài khoản bị khóa, vô hiệu hóa hoặc xóa.
- Mật khẩu được đổi hoặc có dấu hiệu tài khoản bị chiếm đoạt.
- Quyền hoặc vai trò thay đổi làm phiên hiện tại không còn phù hợp.
- Quản trị viên kết thúc phiên đáng ngờ.
- Phát hiện session ID bị lộ hoặc thiết bị bị mất.
- Phiên đạt tuổi tuyệt đối hoặc vi phạm chính sách bảo mật.

Với Servlet API, `HttpSession.invalidate()` vô hiệu hóa phiên hiện tại:

```java
@PostMapping("/logout")
public String logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session != null) {
        session.invalidate();
    }
    return "redirect:/login?logout";
}
```

Nếu ứng dụng dùng Spring Security, nên sử dụng logout flow của Spring Security để xóa `SecurityContext`, gọi các `LogoutHandler` đã cấu hình và xử lý session/cookie nhất quán. Không nên chỉ xóa cookie ở trình duyệt: bản sao cookie cũ vẫn có thể dùng được nếu phiên phía máy chủ chưa bị vô hiệu hóa.

Sau khi đổi mật khẩu, khóa tài khoản hoặc thu hồi quyền, chỉ kết thúc phiên hiện tại có thể chưa đủ vì người dùng có thể đăng nhập trên nhiều thiết bị. Ứng dụng cần có chính sách kết thúc tất cả phiên liên quan đến principal. Spring Session cung cấp `FindByIndexNameSessionRepository` cho repository có hỗ trợ tra cứu phiên theo tên principal. Ví dụ sau minh họa việc xóa các phiên đã được index cho một người dùng:

```java
@Service
public class UserSessionRevocationService {

    private final FindByIndexNameSessionRepository<? extends Session> repository;

    public UserSessionRevocationService(
            FindByIndexNameSessionRepository<? extends Session> repository) {
        this.repository = repository;
    }

    public void revokeAllSessions(String principalName) {
        repository.findByPrincipalName(principalName)
                .values()
                .forEach(session -> repository.deleteById(session.getId()));
    }
}
```

Khả năng tra cứu theo principal phụ thuộc repository và cách tích hợp để principal được index. Cần xác minh repository đang dùng hỗ trợ tính năng này, cấu hình index đúng và kiểm thử trên kho dữ liệu thật. Nếu không có index principal, phải xây dựng cơ chế quản lý phiên phù hợp; không thể giả định chỉ biết user ID là tự tìm được mọi session ID.

Khi gọi `revokeAllSessions`, nên thực hiện sau khi xác minh danh tính và quyền của người yêu cầu. Đối với tài khoản bị xâm phạm, có thể cần thu hồi token hoặc thông tin xác thực khác bên ngoài Spring Session, vì xóa session không tự thu hồi access token độc lập, API key hay cookie của một hệ thống khác.

## 7. Xử lý phiên đang được sử dụng đồng thời

Trong môi trường nhiều instance, hai request có thể cùng sử dụng một session. Ví dụ, request A đang xử lý cập nhật hồ sơ trong khi request B đăng xuất hoặc quản trị viên thu hồi phiên. Việc xóa bản ghi trong repository không tự dừng đoạn mã đã chạy trong request A. Nếu request A tiếp tục ghi phiên sau khi bị thu hồi, kết quả phụ thuộc repository, flush mode và thứ tự thao tác.

Vì vậy, với thao tác nhạy cảm cần kiểm tra trạng thái xác thực và quyền gần thời điểm thực hiện nghiệp vụ. Không dựa vào một lần kiểm tra session ở đầu request cho một tác vụ kéo dài. Có thể cần kiểm tra trạng thái tài khoản hoặc phiên thu hồi tại tầng dịch vụ ngay trước khi ghi dữ liệu quan trọng. Với yêu cầu thu hồi nghiêm ngặt, thiết kế cơ chế version/revocation marker hoặc xác thực lại tập trung, sau đó kiểm thử các tình huống request đang chạy và request mới đến.

Ví dụ một tình huống cần kiểm thử:

1. Instance A nhận request cập nhật thông tin nhạy cảm với session ID hợp lệ.
2. Instance B xử lý yêu cầu đổi mật khẩu và xóa mọi phiên của người dùng.
3. Request cũ ở A tiếp tục đến bước ghi dữ liệu.
4. Request mới mang cookie cũ đến B.

Kết quả mong muốn cần được định nghĩa theo mức rủi ro: request mới phải bị từ chối sau khi phiên bị thu hồi; request cũ phải kiểm tra lại trạng thái trước thao tác nhạy cảm hoặc bị hủy theo chính sách. Bài test cần dùng repository dùng chung và nhiều instance/context để bộc lộ race condition; kiểm thử chỉ bằng một `MockHttpSession` trong bộ nhớ không đủ.

## 8. Sự kiện phiên và trách nhiệm xử lý

Spring Session có các sự kiện vòng đời như `SessionCreatedEvent`, `SessionDeletedEvent` và `SessionExpiredEvent`. Ứng dụng có thể lắng nghe để cập nhật số liệu, dọn tài nguyên phụ trợ hoặc ghi nhận hoạt động bảo mật:

```java
@Component
public class SessionEventsListener {

    @EventListener
    public void onCreated(SessionCreatedEvent event) {
        // Tăng metric phiên được tạo; không ghi session ID hoặc thuộc tính nhạy cảm.
    }

    @EventListener
    public void onDeleted(SessionDeletedEvent event) {
        // Dọn dữ liệu phụ trợ liên quan nếu nghiệp vụ yêu cầu.
    }

    @EventListener
    public void onExpired(SessionExpiredEvent event) {
        // Ghi nhận phiên hết hạn và xử lý tài nguyên phụ trợ.
    }
}
```

Sự kiện và thời điểm nhận phụ thuộc repository. Chẳng hạn, phát hiện khóa Redis hết hạn liên quan đến cơ chế keyspace notifications; việc xóa bản ghi JDBC hết hạn liên quan đến cơ chế cleanup. Không nên coi event listener là cơ chế duy nhất bảo đảm thu hồi hoặc là sổ kiểm toán đầy đủ. Event có thể đến trễ, không có sẵn trong mọi tình huống hoặc được xử lý lại tùy cơ chế vận hành. Handler nên idempotent, có metric lỗi và không làm request chính chờ tác vụ phụ không cần thiết.

Quyết định thu hồi cần diễn ra ở luồng nghiệp vụ rõ ràng, ví dụ logout handler, quy trình khóa tài khoản hoặc dịch vụ quản lý phiên. Event listener hữu ích để đồng bộ công việc phụ sau đó, nhưng không thay thế lệnh xóa phiên tại repository.

## 9. Dọn dữ liệu hết hạn và quản lý bản sao

Hết hạn về mặt logic và xóa vật lý có thể xảy ra ở thời điểm khác nhau. Một repository có thể từ chối khôi phục phiên đã hết hạn trước khi bản ghi được dọn khỏi bảng hoặc bộ nhớ. Vì vậy, cần phân biệt:

- **Hết hiệu lực:** session ID không còn được chấp nhận để khôi phục phiên.
- **Dọn khỏi repository:** bản ghi và thuộc tính được xóa khỏi Redis hoặc bảng JDBC.
- **Xóa khỏi bản sao:** dữ liệu trong backup, snapshot, bản xuất, log và môi trường khôi phục hết thời hạn lưu theo chính sách tương ứng.

Với Redis, kiểm tra TTL của khóa phiên, chính sách persistence/backup, quyền truy cập và cách cấu hình thông báo hết hạn nếu ứng dụng dựa vào sự kiện. Với JDBC, kiểm tra cơ chế cleanup, lịch chạy, index, số hàng hết hạn còn tồn và quyền xóa của tài khoản ứng dụng. Tránh chạy lệnh xóa thủ công trên kho production nếu chưa xác định chính xác namespace, schema và điều kiện lọc.

Nếu tổ chức cần xóa dữ liệu theo yêu cầu người dùng hoặc quy định nội bộ, cần xác định dữ liệu nào thực sự nằm trong session, dữ liệu nào được sao chép sang hệ thống khác và lịch backup nào còn giữ bản cũ. Session thường là dữ liệu tạm thời; hồ sơ và giao dịch nghiệp vụ phải được xử lý theo quy trình retention riêng. Không cam kết rằng xóa một session đồng nghĩa xóa toàn bộ dữ liệu liên quan của người dùng trên mọi hệ thống.

## 10. Kiểm thử chính sách retention và thu hồi

Nên có kiểm thử ở cả tầng ứng dụng và tầng tích hợp repository:

| Kiểm thử | Cách thực hiện | Kết quả cần xác nhận |
|---|---|---|
| TTL không hoạt động | Tạo session, không gửi request trong khoảng vượt TTL | Session cũ không được khôi phục |
| Sliding expiration | Tạo session, gửi request hợp lệ trước khi TTL hết | Thời hạn không hoạt động được cập nhật theo cấu hình repository |
| Tuổi tuyệt đối | Gửi request liên tục nhưng vượt tuổi xác thực tối đa | Người dùng phải xác thực lại theo chính sách |
| Logout | Đăng xuất rồi gửi lại cookie cũ | Phiên cũ không còn được khôi phục |
| Thu hồi mọi phiên | Đăng nhập cùng tài khoản ở hai client, sau đó thu hồi principal | Cả hai session ID đều không còn truy cập được |
| Khóa tài khoản/đổi mật khẩu | Thực hiện thay đổi trạng thái tài khoản và thử request từ phiên cũ | Request bị từ chối theo chính sách |
| Request đồng thời | Một request đang chạy khi request khác thu hồi session | Hành vi được kiểm soát, không cho phép thao tác nhạy cảm trái chính sách |
| Dọn dữ liệu | Chờ cleanup hoặc chạy quy trình cleanup trong môi trường test | Bản ghi hết hạn được dọn theo cơ chế đã cấu hình |
| Chuyển instance | Tạo session ở A, đọc ở B, thu hồi ở A rồi thử lại ở B | Trạng thái chia sẻ và thu hồi nhất quán |

Ví dụ kiểm thử logout ở mức HTTP có thể lấy cookie từ response tạo phiên, gửi request logout, rồi gửi lại cookie cũ. Test phải xác nhận endpoint được bảo vệ và session repository thực sự được dùng; chỉ kiểm tra response xóa cookie chưa chứng minh bản ghi phía máy chủ đã bị thu hồi.

Với TTL, tránh dùng `Thread.sleep` dài và giả định thời điểm cleanup chính xác đến mili giây. Dùng TTL ngắn trong profile test, chờ theo điều kiện có giới hạn hoặc đồng hồ giả nếu thành phần cho phép. Integration test nên dùng Redis/database test riêng, namespace riêng và dọn dữ liệu sau test.

## 11. Phân định trách nhiệm vận hành

Chính sách session chỉ hiệu quả khi có người chịu trách nhiệm duy trì:

- **Nhóm phát triển ứng dụng** xác định thuộc tính nào được lưu, loại dữ liệu nhạy cảm bị cấm, TTL, tuổi xác thực, logout flow và các tình huống cần thu hồi.
- **Nhóm nền tảng/vận hành** bảo vệ Redis hoặc database, cấu hình mạng, ACL, TLS, backup, cleanup, giám sát dung lượng và cảnh báo lỗi.
- **Nhóm bảo mật và quản trị dữ liệu** xác định phân loại dữ liệu, thời hạn lưu, yêu cầu audit, xử lý sự cố và quy trình yêu cầu xóa theo chính sách tổ chức.
- **Nhóm hỗ trợ vận hành** chỉ truy cập dữ liệu phiên khi được ủy quyền, theo quy trình có ghi nhận; không yêu cầu người dùng gửi cookie hoặc session ID qua kênh hỗ trợ.

Trong production, cần có dashboard hoặc cảnh báo cho số phiên đang hoạt động, tốc độ tạo/hết hạn, lỗi đọc/ghi repository, tỷ lệ thu hồi thất bại, độ trễ Redis/JDBC và số bản ghi hết hạn còn tồn. Metric nên tổng hợp, không gắn dữ liệu cá nhân hoặc session ID vào label vì có thể làm lộ thông tin và tạo cardinality rất lớn.

## 12. Checklist trước khi đưa vào production

- [ ] Mỗi session attribute có mục đích cụ thể và được tối thiểu hóa.
- [ ] Không lưu mật khẩu, OTP, API key, khóa riêng hoặc dữ liệu thanh toán nhạy cảm trong session.
- [ ] Mã tham chiếu được kiểm tra quyền sở hữu ở tầng nghiệp vụ.
- [ ] Redis/JDBC được bảo vệ bằng phân quyền tối thiểu, mạng phù hợp và TLS khi cần.
- [ ] Cookie session ID có cấu hình `HttpOnly`, `Secure`, `SameSite` phù hợp; ứng dụng dùng HTTPS.
- [ ] Có TTL không hoạt động và đánh giá nhu cầu tuổi phiên tuyệt đối.
- [ ] Logout vô hiệu hóa phiên phía máy chủ và xóa cookie đúng thuộc tính.
- [ ] Có quy trình thu hồi mọi phiên khi khóa tài khoản, đổi mật khẩu hoặc có sự cố.
- [ ] Đã kiểm thử nhiều instance, request đồng thời, TTL, logout và cleanup.
- [ ] Log, metric, backup và bản xuất không làm lộ session ID hoặc giữ dữ liệu ngoài chính sách.
- [ ] Có chủ sở hữu cho chính sách retention, cleanup và xử lý sự cố.

Spring Session cung cấp cơ chế lưu trữ và khôi phục phiên dùng chung. Trách nhiệm bảo vệ dữ liệu vẫn thuộc về thiết kế ứng dụng và quy trình vận hành: chỉ lưu trạng thái cần thiết, giới hạn thời gian hiệu lực, thu hồi phiên ở phía máy chủ khi có sự kiện bảo mật và kiểm soát cả bản sao của dữ liệu. Một chính sách rõ ràng giúp session phục vụ đúng mục đích tạm thời mà không trở thành nơi lưu trữ lâu dài ngoài kiểm soát.
