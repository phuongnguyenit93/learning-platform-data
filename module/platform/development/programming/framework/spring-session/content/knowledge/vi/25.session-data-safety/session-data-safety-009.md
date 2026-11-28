# Tối thiểu hóa dữ liệu cá nhân và thời gian giữ lại

Spring Session giúp ứng dụng Servlet hoặc WebFlux lưu trạng thái phiên ở một kho dữ liệu dùng chung như Redis hoặc JDBC. Vì session có thể chứa thông tin xác thực, tùy chọn người dùng và trạng thái nghiệp vụ tạm thời, kho session cũng là nơi lưu dữ liệu cá nhân cần được quản lý vòng đời. Một session còn tồn tại sau khi người dùng đã rời ứng dụng, một attribute không còn cần thiết hoặc một bản backup cũ vẫn có thể làm tăng phạm vi dữ liệu bị lộ.

Nguyên tắc thiết kế là chỉ lưu thông tin thật sự cần cho các request tiếp theo, giữ trong thời gian ngắn nhất đáp ứng nghiệp vụ, và bảo đảm dữ liệu được xóa hoặc không còn được sử dụng sau khi hết hạn. Spring Session cung cấp cơ chế timeout và lưu/xóa phiên; ứng dụng vẫn phải quyết định dữ liệu nào được đưa vào session, khi nào xóa attribute, cách quản lý backup, log, remember-me và các bản sao dữ liệu khác.

## 1. Session không phải hồ sơ người dùng

Session là trạng thái tạm thời gắn với một lần sử dụng ứng dụng. Nó thường phục vụ các mục đích như:

- Giữ `SecurityContext` hoặc trạng thái xác thực cần thiết giữa các request.
- Giữ mã tham chiếu tới giỏ hàng, quy trình đang thực hiện hoặc bản nháp ngắn hạn.
- Giữ lựa chọn giao diện hoặc ngôn ngữ trong phạm vi phiên.
- Giữ một nonce hoặc dữ liệu chống CSRF theo cơ chế bảo mật của framework.
- Ghi nhận bước hiện tại của một quy trình nhiều request.

Session không nên trở thành bản sao đầy đủ của hồ sơ người dùng, cơ sở dữ liệu nghiệp vụ hoặc kho lưu trữ lâu dài. Nếu một request cần địa chỉ, số điện thoại hoặc thông tin hồ sơ, thường chỉ cần lưu `userId` trong session rồi tải dữ liệu cần thiết từ service có kiểm tra quyền.

Ví dụ, thay vì lưu toàn bộ đối tượng người dùng:

```java
// Tránh đưa toàn bộ hồ sơ cá nhân vào session
session.setAttribute("user", userEntity);

// Ưu tiên lưu một định danh tối thiểu khi cần tra cứu lại
session.setAttribute("userId", userId);
```

`userId` vẫn có thể là dữ liệu cá nhân nếu có thể liên kết với một cá nhân. Tuy nhiên, lưu một định danh nội bộ thường giảm lượng dữ liệu, tránh lưu bản sao các trường không cần thiết và giảm rủi ro serialization của entity lớn.

## 2. Lập danh mục session attributes trước khi lưu

Hãy liệt kê từng attribute và trả lời bốn câu hỏi: mục đích là gì, request nào cần nó, dữ liệu có nhạy cảm không, và khi nào có thể xóa?

| Attribute | Có thể cần lưu? | Cách giảm dữ liệu và thời gian giữ |
|---|---|---|
| `SecurityContext` | Có, nếu dùng session-based authentication | Chỉ lưu thông tin xác thực cần thiết; đặt timeout phù hợp và invalidate khi logout |
| `userId` | Có thể | Dùng ID nội bộ; tải hồ sơ từ nguồn chính khi cần |
| `cartId` | Thường phù hợp | Lưu mã tham chiếu; giỏ hàng và thời hạn của nó thuộc kho nghiệp vụ |
| `cart` chứa toàn bộ sản phẩm/giá | Thường không cần | Lưu `cartId`; đọc nội dung giỏ hàng từ service |
| `email`, số điện thoại, địa chỉ | Chỉ khi có nhu cầu rõ ràng | Tránh sao chép; nếu thật sự cần, xóa ngay khi bước nghiệp vụ kết thúc |
| Mật khẩu, OTP, access token bí mật | Không nên | Chỉ giữ trong luồng xác thực cần thiết; không lưu vào session lâu dài hoặc log |
| Dữ liệu thẻ thanh toán, CVV | Không | Dùng nhà cung cấp thanh toán và token tham chiếu phù hợp |
| Entity ORM và lazy collections | Tránh | Chuyển thành DTO nhỏ hoặc ID |
| Kết quả tra cứu lớn | Thường không | Cache riêng có TTL và giới hạn kích thước nếu thực sự cần |

Không phải mọi dữ liệu gắn với tài khoản đều cần có trong session. Đừng lưu một giá trị chỉ vì việc truy cập nó trong controller sẽ tiện hơn. Mỗi attribute làm tăng kích thước session, chi phí serialize/deserialize, dung lượng Redis/JDBC và phạm vi ảnh hưởng khi dữ liệu bị truy cập trái phép.

## 3. Không lưu bí mật hoặc dữ liệu nhạy cảm không cần thiết

Tránh lưu các dữ liệu sau trong session trừ khi có một yêu cầu kỹ thuật cụ thể, thời gian tồn tại ngắn và biện pháp bảo vệ đã được đánh giá:

- Mật khẩu dạng rõ, password hash hoặc câu trả lời bảo mật.
- OTP, mã khôi phục, mã xác minh một lần sau khi đã dùng.
- Access token/refresh token của hệ thống khác nếu không cần cho request kế tiếp.
- Số thẻ thanh toán đầy đủ, CVV hoặc dữ liệu xác thực thanh toán.
- Nội dung giấy tờ định danh, dữ liệu tài chính hoặc sức khỏe không cần cho luồng hiện tại.
- Toàn bộ hồ sơ người dùng hoặc bản sao dữ liệu từ hệ thống nguồn.

Nếu ứng dụng phải giữ credential để gọi một hệ thống khác, hãy dùng một kho bí mật hoặc token store có kiểm soát quyền, mã hóa và khả năng thu hồi. Session có thể chỉ giữ một handle hoặc ID tham chiếu. Không đưa bí mật vào cookie session ID; cookie nên chứa một định danh ngẫu nhiên khó đoán, còn trạng thái được lưu phía server.

`HttpOnly`, `Secure` và `SameSite` bảo vệ một số khía cạnh của cookie session ID. Chúng không mã hóa các attributes trong Redis/JDBC và không làm dữ liệu cá nhân trong session tự an toàn. Bảo vệ kho dữ liệu và giảm dữ liệu lưu vẫn là yêu cầu riêng.

## 4. Lưu DTO nhỏ và ổn định

Khi cần lưu trạng thái tạm thời, hãy tạo DTO chỉ chứa trường cần thiết:

```java
public record CheckoutSessionState(
        String checkoutId,
        String cartId,
        String currentStep,
        long createdAtEpochSecond) implements Serializable {
}
```

Ví dụ đặt attribute:

```java
session.setAttribute("checkoutState", new CheckoutSessionState(
        checkoutId,
        cartId,
        "ADDRESS",
        Instant.now().getEpochSecond()));
```

Không đưa tên, địa chỉ, email và toàn bộ nội dung đơn hàng vào DTO nếu bước hiện tại chỉ cần `checkoutId` và `currentStep`. Khi cần hiển thị thông tin, tải lại dữ liệu từ nguồn nghiệp vụ với kiểm tra chủ sở hữu và quyền truy cập.

DTO session nên có schema ổn định giữa các instance đang chạy. Nếu thay đổi class hoặc serializer, kiểm thử tương thích dữ liệu trong giai đoạn rolling deployment. Dữ liệu session cũ có thể tồn tại đến hết TTL, vì vậy không xóa class/field ngay khi phiên bản mới được triển khai nếu instance cũ hoặc session cũ còn cần đọc chúng.

## 5. Đặt thời hạn session theo mục đích

Spring Session quản lý thời gian không hoạt động tối đa của phiên thông qua `maxInactiveInterval`. Với Servlet API, ứng dụng có thể đặt timeout theo giây:

```java
HttpSession session = request.getSession();
session.setMaxInactiveInterval(20 * 60); // 20 phút không hoạt động
```

Khi dùng Spring Session, giá trị này được repository sử dụng để xác định thời điểm hết hạn. Với cấu hình Spring Boot, có thể đặt timeout mặc định cho session theo property của phiên bản đang dùng, thường là `spring.session.timeout` hoặc cấu hình tương ứng do starter cung cấp. Hãy kiểm tra configuration metadata của đúng dòng Boot/Spring Session.

Không chọn một timeout quá dài chỉ để tránh người dùng phải đăng nhập lại. Hãy cân nhắc:

- Độ nhạy cảm của dữ liệu và quyền trong session.
- Mức độ rủi ro nếu thiết bị bị mất hoặc cookie bị đánh cắp.
- Thời gian trung bình người dùng cần để hoàn tất quy trình.
- Có remember-me hoặc cơ chế xác thực lại hay không.
- Có yêu cầu timeout riêng cho tài khoản quản trị hoặc thao tác nhạy cảm hay không.

Một ứng dụng có thể dùng timeout mặc định 20 phút cho session thông thường, timeout ngắn hơn cho luồng quản trị và yêu cầu xác thực lại trước khi đổi mật khẩu hoặc xác nhận thanh toán. Con số cụ thể cần dựa trên threat model và yêu cầu sản phẩm, không có một giá trị đúng cho mọi ứng dụng.

## 6. Session timeout khác cookie Max-Age

Thời hạn server-side và thời hạn cookie trình duyệt là hai cơ chế riêng:

| Cơ chế | Nơi áp dụng | Ý nghĩa |
|---|---|---|
| `maxInactiveInterval` | Spring Session/repository | Phiên không còn hợp lệ sau thời gian không hoạt động |
| Cookie `Max-Age`/`Expires` | Trình duyệt | Thời gian trình duyệt giữ và gửi session ID |
| Remember-me validity | Spring Security | Thời hạn credential dài hạn có thể xác thực lại người dùng |
| TTL của attribute riêng | Logic ứng dụng | Thời gian một attribute cụ thể được phép sử dụng |

Session cookie không có `Max-Age` thường là cookie theo phiên trình duyệt, nhưng điều đó không làm session server-side tự hết hạn khi trình duyệt đóng. Session có thể còn trong Redis/JDBC cho tới khi timeout hoặc bị invalidate. Ngược lại, cookie có thể còn trong browser sau khi session đã hết hạn; server vẫn phải từ chối ID cũ.

Không đặt cookie Max-Age bằng nhiều ngày rồi cho rằng session có thời hạn tương ứng. Cũng không coi remember-me cookie là session cookie. Remember-me có thể tạo một session mới sau khi session cũ hết hạn và cần chính sách riêng về thời hạn, thu hồi và bảo vệ.

## 7. TTL và cleanup trong Redis

Với Redis repository, Spring Session lưu dữ liệu session dưới dạng các key/hash theo namespace và áp dụng TTL để quản lý vòng đời. Khi session được truy cập, last-access time và thời hạn có thể được cập nhật theo repository. Với một số triển khai indexed, repository giữ thêm expiration marker và sorted set để hỗ trợ xử lý sự kiện hết hạn.

Các điểm cần hiểu:

- Session hết hạn logic khi vượt `maxInactiveInterval`.
- TTL của key Redis là cơ chế giúp Redis dọn dữ liệu vật lý.
- Một số key phụ trợ có thể có thời gian tồn tại hoặc cleanup riêng để hỗ trợ event.
- Expiration notification có thể đến trễ; không dùng thời điểm xóa vật lý làm căn cứ duy nhất cho authorization.
- Namespace giúp tách session giữa ứng dụng/môi trường, nhưng không thay thế ACL và phân quyền Redis.

Không tự đặt TTL cho key session bằng lệnh Redis riêng nếu không hiểu cấu trúc repository. Thao tác thủ công có thể làm hash, expiration marker, index và event không còn nhất quán. Hãy dùng API Spring Session hoặc cơ chế cleanup được hỗ trợ.

Với Redis managed hoặc cluster, xác minh persistence, replication, keyspace notifications và chính sách eviction. Nếu Redis bị cấu hình eviction theo memory pressure, session có thể biến mất sớm hơn timeout dự kiến. Đó là hành vi khác với retention policy có chủ đích và cần được theo dõi.

## 8. Cleanup trong JDBC và thời điểm xóa vật lý

Với JDBC repository, session metadata thường nằm trong bảng `SPRING_SESSION`, attributes nằm trong `SPRING_SESSION_ATTRIBUTES`. `EXPIRY_TIME` biểu diễn thời điểm hết hạn logic. Một cleanup task định kỳ xóa các hàng đã hết hạn; thời điểm cleanup chạy phụ thuộc lịch, tải database và cấu hình repository.

Điều đó có nghĩa:

- Một session có thể đã hết hạn logic nhưng hàng vật lý vẫn tồn tại tạm thời.
- Truy vấn `findById` phải không khôi phục phiên đã hết hạn chỉ vì hàng chưa bị cleanup.
- Bảng attributes cần được xóa cùng session theo khóa ngoại/cascade hoặc logic repository.
- Cleanup quá thưa làm tăng dung lượng lưu trữ và thời gian giữ dữ liệu vật lý.
- Cleanup quá thường xuyên có thể tăng tải, lock và I/O trên database.

Trong production, dùng migration để quản lý schema/index và theo dõi số hàng hết hạn, thời gian cleanup và dung lượng bảng. Không chạy `DELETE` tùy tiện trên bảng session khi ứng dụng đang hoạt động; xóa ngoài repository có thể bỏ qua event hoặc quan hệ phụ trợ cần thiết.

## 9. Xóa attribute ngay khi không còn cần

Không phải mọi dữ liệu đều cần giữ tới khi cả session hết hạn. Khi người dùng hoàn tất một bước, dữ liệu tạm thời có thể được xóa ngay:

```java
HttpSession session = request.getSession(false);
if (session != null) {
    session.removeAttribute("checkoutState");
    session.removeAttribute("temporaryVerificationCode");
}
```

`getSession(false)` tránh tạo một session mới chỉ để xóa attribute. Với WebFlux, dùng `WebSession.getAttributes().remove(...)` và để WebSession lifecycle lưu thay đổi theo reactive chain; nếu cần xác nhận lưu xong trước bước tiếp theo, compose `session.save()` vào publisher.

Các thời điểm nên xóa dữ liệu tạm:

- Sau khi OTP đã được xác minh hoặc hết hiệu lực.
- Sau khi quy trình checkout hoàn tất hoặc bị hủy.
- Sau khi người dùng đổi tài khoản hoặc tenant.
- Sau khi quyền truy cập tạm thời được cấp và sử dụng xong.
- Sau khi một bản nháp được chuyển sang nguồn lưu trữ nghiệp vụ chính.
- Khi logout hoặc session bị thu hồi.

Khi xóa một attribute, cần xác nhận repository thực sự ghi thao tác remove. Với `SaveMode.ON_SET_ATTRIBUTE`, thay đổi qua API session được theo dõi; nếu attribute là object mutable, thay đổi nội dung object mà không gọi lại `setAttribute` có thể không được nhận diện là thay đổi. Đối với dữ liệu nhạy cảm, hãy dùng `removeAttribute` và kiểm thử đọc lại từ repository.

## 10. TTL riêng cho từng attribute

Spring Session thường áp dụng timeout cho toàn bộ session, không cung cấp một TTL độc lập tự động cho mọi attribute. Nếu một attribute chỉ có hiệu lực trong vài phút nhưng session sống lâu hơn, ứng dụng cần quản lý thời hạn riêng.

Một cách là lưu envelope chứa dữ liệu và thời điểm hết hạn:

```java
public record ExpiringValue<T>(T value, Instant expiresAt)
        implements Serializable {
}
```

Khi lưu:

```java
session.setAttribute("verificationState",
        new ExpiringValue<>(verificationState,
                Instant.now().plus(Duration.ofMinutes(5))));
```

Khi đọc:

```java
@SuppressWarnings("unchecked")
ExpiringValue<VerificationState> stored =
        (ExpiringValue<VerificationState>) session.getAttribute("verificationState");

if (stored == null || !stored.expiresAt().isAfter(Instant.now())) {
    session.removeAttribute("verificationState");
    throw new IllegalStateException("Trạng thái xác minh đã hết hạn");
}

VerificationState value = stored.value();
```

Đây là mẫu minh họa. Trong ứng dụng thật, nên validate kiểu và schema thay vì cast không kiểm soát, dùng clock có thể thay thế trong test và xử lý đồng thời khi nhiều request cùng đọc/xóa. Việc xóa lười khi đọc chỉ diễn ra nếu attribute được truy cập; nếu cần xóa vật lý đúng hạn ngay cả khi không có request, cần một cleanup job hoặc lưu loại dữ liệu đó trong kho có TTL riêng.

Không dùng TTL riêng để thay thế session timeout. Session có thể hết hạn trước attribute TTL; khi đó toàn bộ session không còn hợp lệ. Ngược lại, attribute hết hạn trước session phải bị từ chối ngay cả khi session còn tồn tại.

## 11. Logout và thu hồi dữ liệu session

Đăng xuất cần vô hiệu hóa phiên phía server và xóa cookie phía client. Với Servlet:

```java
@PostMapping("/logout")
public ResponseEntity<Void> logout(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session != null) {
        session.invalidate();
    }
    return ResponseEntity.noContent().build();
}
```

Trong ứng dụng Spring Security, ưu tiên logout filter/handler được cấu hình để clear SecurityContext, invalidate session và xóa cookie theo đúng tên/path/domain. Nếu có remember-me, phải xóa hoặc thu hồi credential remember-me theo cơ chế của Spring Security; invalidate session đơn lẻ không thu hồi token dài hạn.

Với “logout mọi thiết bị”, tìm các session theo principal index nếu repository hỗ trợ, thu hồi từng session và xử lý các remember-me token tương ứng. Cookie trên thiết bị khác không thể bị xóa trực tiếp nếu thiết bị không nhận response, nhưng server phải từ chối session/token cũ theo chính sách.

Không tuyên bố logout hoàn tất nếu thao tác thu hồi ở repository thất bại. Thiết kế retry idempotent và ghi nhận lỗi bằng correlation ID đã che; không ghi session ID hoặc token nguyên vẹn vào log.

## 12. Session retention không phải retention của mọi bản sao

Xóa session khỏi Redis/JDBC không có nghĩa mọi bản sao dữ liệu biến mất ngay lập tức. Cần lập danh mục các nơi dữ liệu session có thể xuất hiện:

- Redis replication, persistence file, snapshot hoặc backup.
- Backup database, transaction log, replica và bản sao phục hồi.
- Log ứng dụng, trace, error report hoặc dump khi vô tình ghi attribute.
- Cache trung gian, message hoặc event payload do ứng dụng tự phát.
- Dữ liệu trong bộ nhớ của request đang chạy.
- Export/debug dump do nhân viên vận hành tạo.

Đặt chính sách retention riêng cho backup và snapshot, giới hạn quyền truy cập, mã hóa khi lưu và có quy trình xóa/hết hạn theo lịch. Nếu cần phục hồi backup, đánh giá nguy cơ đưa session đã bị thu hồi trở lại hệ thống. Với kho session, có thể dùng namespace/version hoặc chiến lược vô hiệu hóa session sau restore để tránh tái kích hoạt credential cũ.

Log không nên chứa toàn bộ session attributes, cookie, Authorization header, OTP, email hoặc token. Nếu cần điều tra, chỉ ghi loại sự kiện, tên attribute không nhạy cảm, kết quả xử lý, timestamp và định danh đã che.

## 13. Bảo vệ kho session và dữ liệu trên đường truyền

Tối thiểu hóa dữ liệu giảm tác động khi bị lộ; các biện pháp bảo vệ kho dữ liệu giảm khả năng truy cập trái phép:

- Dùng TLS cho kết nối ứng dụng tới Redis/database khi đi qua mạng không hoàn toàn tin cậy.
- Dùng ACL hoặc database account riêng cho service; cấp quyền tối thiểu trên key pattern/schema cần thiết.
- Không công khai Redis port ra Internet hoặc mạng người dùng.
- Quản lý credential bằng secret manager và xoay vòng định kỳ.
- Mã hóa disk/backup và kiểm soát quyền đọc snapshot.
- Tách môi trường dev, staging và production; tránh dùng chung namespace hoặc credential.
- Giới hạn quyền truy cập công cụ debug và dashboard có thể xem session content.
- Theo dõi truy cập bất thường, export hàng loạt và thay đổi cấu hình TTL/cleanup.

Mã hóa cookie không phải mã hóa session data. `Secure` bảo vệ cookie trên kênh HTTPS; `HttpOnly` hạn chế truy cập từ JavaScript; còn dữ liệu trong Redis/JDBC cần TLS, encryption at rest và quyền truy cập kho riêng.

## 14. Dữ liệu cá nhân trong principal và SecurityContext

Session-based authentication thường lưu `SecurityContext`, có thể tham chiếu tới `Authentication`, principal và authorities. Nếu principal là một `UserDetails` lớn chứa email, số điện thoại, địa chỉ và nhiều thuộc tính khác, toàn bộ dữ liệu đó có thể bị serialize vào session.

Hãy thiết kế principal/session representation gọn:

- Giữ subject/user ID ổn định và authorities cần thiết cho authorization.
- Tránh nhúng toàn bộ hồ sơ người dùng vào principal.
- Không lưu password thô hoặc credential không cần thiết sau xác thực.
- Khi thông tin quyền thay đổi, cân nhắc cách cập nhật/revoke SecurityContext đang tồn tại.
- Đảm bảo principal có thể serialize/deserialize giữa các instance và phiên bản.

Không tự giảm SecurityContext xuống một chuỗi username nếu ứng dụng cần authorities và các chi tiết xác thực khác. Mục tiêu là lưu đúng dữ liệu bảo mật cần thiết, không làm mất semantics của Spring Security.

## 15. Cookie session ID và phạm vi dữ liệu

Cookie session thường chỉ mang session ID ngẫu nhiên, không chứa trực tiếp attributes. Đây là một lợi thế của mô hình server-side session: dữ liệu cá nhân ở kho server thay vì nằm trong cookie client. Tuy nhiên, session ID là bearer credential; ai có ID còn hiệu lực có thể thử sử dụng phiên.

Cấu hình cookie nên xem xét:

```java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
```

Đặt `Secure` khi chạy HTTPS, `HttpOnly` để JavaScript không đọc trực tiếp cookie và `SameSite` theo luồng cross-site/SSO của ứng dụng. Các thuộc tính cookie không thay thế CSRF protection. Giới hạn domain/path để cookie không được gửi rộng hơn cần thiết. Nếu TLS kết thúc ở proxy, cấu hình forwarded headers đáng tin cậy để ứng dụng nhận diện đúng scheme.

## 16. Theo dõi retention mà không thu thập thêm dữ liệu cá nhân

Observability cần đo được vòng đời session mà không lưu nội dung session. Các metric hữu ích:

- Số session đang hoạt động theo application/namespace.
- Số session được tạo, invalidate và hết hạn trong một khoảng thời gian.
- Phân bố tuổi session và thời gian không hoạt động.
- Số attributes và kích thước session trung bình/p95/p99 nếu đo được an toàn.
- Số lỗi serialize/deserialize và lỗi repository.
- Số hàng JDBC hết hạn đang chờ cleanup hoặc backlog expiration trong Redis.
- Số lần logout thất bại và số kết nối dài hạn chưa được đóng sau revoke.

Ưu tiên metric tổng hợp, không gắn nhãn bằng email, username, session ID hoặc token. Cardinality cao và dữ liệu nhận dạng trong metric có thể biến hệ thống monitoring thành một kho dữ liệu cá nhân khác.

Đặt ngưỡng cảnh báo cho session size bất thường, session lifetime vượt chính sách, cleanup chậm, tăng số session đột biến và lỗi thu hồi. Khi điều tra, dùng correlation ID ngắn hạn và định danh đã che.

## 17. Kiểm thử thời gian giữ lại và xóa dữ liệu

Một bộ kiểm thử nên xác nhận dữ liệu thực sự không còn được sử dụng sau khi hết hạn hoặc bị xóa:

1. Tạo session và chỉ lưu các attributes được phép.
2. Kiểm tra không có password, OTP đã dùng, token thô hoặc dữ liệu hồ sơ dư thừa trong attributes.
3. Đặt timeout ngắn và xác nhận session hết hạn logic; request dùng ID cũ không khôi phục được phiên.
4. Với Redis, kiểm tra TTL/key cleanup trong môi trường test và lưu ý grace-period/index keys của repository.
5. Với JDBC, xác nhận `findById` không trả session hết hạn và cleanup xóa metadata/attributes theo lịch.
6. Gọi `removeAttribute` sau khi quy trình hoàn tất; đọc lại session để xác nhận attribute không còn.
7. Kiểm thử TTL riêng của attribute: giá trị hết hạn phải bị từ chối dù session còn hoạt động.
8. Logout và xác nhận session ID cũ không còn hợp lệ.
9. Nếu dùng remember-me, kiểm tra token có chính sách retention/revocation riêng.
10. Kiểm tra response xóa cookie đúng name/domain/path và không log cookie.
11. Kiểm tra backup/restore hoặc quy trình phục hồi không vô tình kích hoạt session đã bị thu hồi.
12. Kiểm tra log, trace và metric không chứa nội dung attributes hoặc định danh nhạy cảm.

Không dùng `Thread.sleep(timeout)` làm bằng chứng duy nhất rằng Redis TTL hoặc JDBC cleanup đã chạy. Dùng polling có timeout để chờ trạng thái quan sát được, test clock nếu implementation cho phép, và kiểm tra cả tính hợp lệ logic lẫn việc xóa vật lý.

## 18. Ma trận retention mẫu

Mỗi loại dữ liệu cần có mục đích, nơi lưu, thời hạn và hành động khi hết hạn:

| Loại dữ liệu | Nơi lưu phù hợp | Retention gợi ý theo mục đích | Hành động hết hạn |
|---|---|---|---|
| SecurityContext trong session | Spring Session store | Theo session inactivity timeout | Invalidate/expire session |
| Checkout step | Session hoặc workflow store | Chỉ trong thời gian hoàn tất quy trình | Xóa attribute hoặc workflow record |
| OTP state | Kho xác minh có TTL ngắn | Vài phút hoặc theo chính sách xác minh | Từ chối và xóa |
| Cart ID | Session | Theo thời gian người dùng tiếp tục phiên | Xóa attribute; giỏ hàng có TTL riêng |
| Hồ sơ người dùng | Database nghiệp vụ | Theo chính sách dữ liệu tài khoản | Quản lý ở nguồn chính, không nhân bản trong session |
| Remember-me token | Persistent token store | Theo chính sách đăng nhập dài hạn | Thu hồi token/series |
| Log vận hành | Hệ thống log | Theo nhu cầu vận hành và chính sách tổ chức | Xóa/ẩn danh theo lịch |
| Backup Redis/JDBC | Kho backup | Theo lịch backup/khôi phục đã phê duyệt | Hết hạn hoặc xóa bản sao an toàn |

Các thời hạn trong bảng chỉ là ví dụ phân loại; tổ chức cần đặt giá trị thực dựa trên yêu cầu nghiệp vụ, threat model và nghĩa vụ bảo vệ dữ liệu áp dụng. Không dùng một TTL duy nhất cho mọi loại dữ liệu.

## 19. Lỗi thiết kế thường gặp

| Vấn đề | Hậu quả | Cách cải thiện |
|---|---|---|
| Lưu toàn bộ User/ORM entity | Session lớn, chứa nhiều dữ liệu cá nhân và dễ lỗi serialization | Dùng ID hoặc DTO nhỏ |
| Lưu OTP sau khi đã xác minh | Mã đã dùng vẫn tồn tại trong kho session | `removeAttribute` ngay sau khi dùng và kiểm thử |
| Session timeout quá dài | Credential bị đánh cắp có cửa sổ sử dụng lớn | Đặt timeout theo mức nhạy cảm và yêu cầu xác thực lại |
| Chỉ xóa cookie khi logout | Session phía server vẫn còn | Invalidate qua repository và xóa cookie |
| Chỉ xóa session nhưng quên remember-me | Token dài hạn có thể đăng nhập lại | Thu hồi remember-me riêng |
| Dùng cookie Max-Age thay server TTL | Cookie tồn tại lâu nhưng session có thể hết hạn, hoặc ngược lại | Quản lý hai thời hạn độc lập |
| Chờ Redis/JDBC xóa vật lý mới từ chối request | Có thể chấp nhận session đã hết hạn | Dựa vào semantics hết hạn logic của repository |
| Log toàn bộ session khi lỗi | Tạo thêm bản sao dữ liệu cá nhân/bí mật | Log metadata đã che, không log payload |
| Không tính backup và replica | Dữ liệu còn tồn tại ngoài kho chính | Đặt retention và quyền truy cập cho mọi bản sao |
| Dùng session làm kho nghiệp vụ lâu dài | Dữ liệu khó quản lý, khó đối soát và có thể mất khi hết hạn | Lưu nghiệp vụ ở database/service phù hợp |

## 20. Quy trình áp dụng trong dự án

1. Liệt kê tất cả attributes đang được đưa vào `HttpSession`/`WebSession`.
2. Xác định mục đích, mức nhạy cảm, consumer và thời điểm xóa của từng attribute.
3. Loại bỏ dữ liệu không cần; thay entity lớn bằng ID hoặc DTO tối thiểu.
4. Không lưu password, OTP đã dùng, dữ liệu thanh toán hoặc credential thô.
5. Chọn session inactivity timeout theo rủi ro và thời gian nghiệp vụ.
6. Đặt TTL riêng cho attribute cần hết hạn sớm hơn session.
7. Cấu hình Redis TTL hoặc JDBC cleanup và theo dõi hoạt động thực tế.
8. Xóa attribute ngay sau khi hoàn tất bước nghiệp vụ; invalidate session khi logout.
9. Quản lý remember-me, access token, cookie và backup theo retention riêng.
10. Bảo vệ Redis/JDBC, backup, log và monitoring bằng quyền tối thiểu và che dữ liệu.
11. Kiểm thử hết hạn logic, cleanup vật lý, logout, multi-instance và khôi phục backup.
12. Định kỳ rà soát danh mục dữ liệu để loại bỏ attributes không còn được sử dụng.

Tối thiểu hóa dữ liệu và giới hạn thời gian giữ lại là hai lớp kiểm soát bổ sung cho Spring Session. Lưu ít dữ liệu hơn làm giảm tác động khi kho session bị truy cập; timeout, TTL, `removeAttribute`, invalidate và cleanup giới hạn khoảng thời gian dữ liệu còn được sử dụng. Để chính sách có hiệu lực, cần kiểm tra cả session store, cookie, remember-me, request đang chạy, log, replica và backup. Hãy xem session là trạng thái tạm thời có chủ đích, không phải nơi lưu hồ sơ cá nhân hoặc dữ liệu nghiệp vụ lâu dài.
