# Phiên hết hạn, phiên bị xóa và phiên không còn tồn tại

Trong ứng dụng Servlet, cookie phiên chỉ mang mã định danh để máy chủ tra cứu dữ liệu `HttpSession`. Cookie vẫn có thể được trình duyệt gửi lên sau khi dữ liệu phiên ở máy chủ đã hết hạn hoặc bị xóa. Vì vậy, cần phân biệt ba trạng thái: phiên còn hiệu lực, phiên đã bị kết thúc và mã phiên được gửi lên nhưng không còn bản ghi tương ứng.

Spring Session quản lý vòng đời phiên thông qua một repository như Redis hoặc JDBC. Khi nhiều instance cùng dùng repository đó, mọi instance có thể kiểm tra cùng một trạng thái phiên. Tuy nhiên, hết hạn, xóa và không tìm thấy phiên là các tình huống khác nhau; cách xử lý đúng giúp ứng dụng đăng xuất an toàn, tránh tạo phiên ngoài ý muốn và phản hồi phù hợp khi kho dữ liệu gặp sự cố.

## 1. Phân biệt ba trạng thái

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| Phiên còn hiệu lực | Repository vẫn trả về phiên và phiên chưa vượt quá thời hạn | Người dùng vừa đăng nhập và tiếp tục thao tác |
| Phiên hết hạn | Thời hạn không hoạt động hoặc chính sách hết hạn đã kết thúc phiên | Người dùng không gửi request trong thời gian timeout |
| Phiên bị xóa | Ứng dụng hoặc thao tác quản trị chủ động kết thúc phiên | Người dùng đăng xuất hoặc quản trị viên thu hồi phiên |
| Phiên không tồn tại | Không có dữ liệu phiên ứng với mã nhận được | Cookie cũ, mã không hợp lệ hoặc phiên đã bị dọn khỏi kho |

"Không tồn tại" mô tả kết quả tra cứu tại thời điểm hiện tại. Nó không cho biết nguyên nhân chắc chắn. Phiên có thể chưa từng được tạo, đã hết hạn, đã bị xóa, hoặc mã trong cookie không trỏ đến phiên nào trong repository hiện tại.

## 2. Phiên hết hạn do không hoạt động

### 2.1. Thời gian không hoạt động của HttpSession

Servlet API cung cấp `HttpSession.setMaxInactiveInterval(int seconds)` để đặt khoảng thời gian tối đa một phiên được phép không có hoạt động truy cập. Container hoặc lớp quản lý session dùng thời điểm truy cập gần nhất và khoảng thời gian này để xác định phiên đã hết hạn hay chưa. Giá trị mặc định thường được đặt ở cấu hình ứng dụng hoặc container; không nên dựa vào một giá trị mặc định nếu yêu cầu bảo mật cần timeout cụ thể.

Ví dụ, nếu thời gian không hoạt động tối đa là 30 phút:

1. Người dùng gửi request lúc 09:00 và phiên được truy cập.
2. Người dùng tiếp tục gửi request lúc 09:20; hoạt động này làm mới mốc không hoạt động.
3. Nếu không có hoạt động tiếp theo, phiên có thể hết hạn sau khoảng 30 phút tính từ lần truy cập gần nhất, tức khoảng 09:50.

Đây là timeout theo trạng thái không hoạt động, không phải thời gian sống tuyệt đối kể từ lúc đăng nhập. Một người dùng vẫn hoạt động có thể giữ phiên lâu hơn 30 phút. Nếu yêu cầu có giới hạn đăng nhập tối đa, chẳng hạn bắt buộc đăng nhập lại sau 8 giờ dù vẫn có hoạt động, ứng dụng cần bổ sung chính sách tuổi đời tuyệt đối hoặc cơ chế xác thực tương ứng.

Có thể đặt timeout cho một phiên bằng Servlet API:

```java
@PostMapping("/session/timeout")
public ResponseEntity<Void> updateTimeout(HttpSession session) {
    // 30 phút không hoạt động
    session.setMaxInactiveInterval(30 * 60);
    return ResponseEntity.noContent().build();
}
```

Với Spring Session, thời gian không hoạt động được lưu cùng dữ liệu phiên và được repository sử dụng để quản lý thời hạn. Có thể cấu hình giá trị mặc định khi bật repository Redis:

```java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 30 * 60)
public class SessionConfiguration {
}
```

Tên annotation và cấu hình cụ thể cần phù hợp với phiên bản Spring Session đang dùng. Nếu ứng dụng cấu hình timeout bằng Spring Boot properties hoặc cơ chế auto-configuration, hãy chọn một nguồn cấu hình thống nhất và kiểm tra giá trị thực tế mà repository nhận được.

### 2.2. Timeout không đồng nghĩa cookie tự hết hạn

Thời hạn ở máy chủ và thời hạn cookie là hai cơ chế riêng:

- Timeout session quyết định repository còn chấp nhận dữ liệu phiên hay không.
- `Max-Age` hoặc `Expires` của cookie quyết định trình duyệt giữ và gửi cookie trong bao lâu.

Một cookie dạng session cookie có thể vẫn được gửi trong khi trình duyệt còn mở, dù dữ liệu phiên ở Redis hoặc JDBC đã hết hạn. Ngược lại, cookie có thể hết hạn ở trình duyệt trong khi bản ghi phiên vẫn còn ở máy chủ cho đến khi TTL hoặc tác vụ dọn dẹp xử lý.

Do đó, xóa cookie không thay thế việc xóa phiên phía máy chủ. Tương tự, đặt TTL phía máy chủ không đảm bảo trình duyệt lập tức xóa cookie khi người dùng không gửi request.

### 2.3. Timeout không hoạt động và timeout tuyệt đối

Ứng dụng cần xác định rõ loại giới hạn đang áp dụng:

| Chính sách | Điều kiện kết thúc | Mục đích |
|---|---|---|
| Không hoạt động (idle timeout) | Không có request truy cập phiên trong một khoảng thời gian | Giảm thời gian tồn tại của phiên bị bỏ quên |
| Tuổi đời tuyệt đối (absolute lifetime) | Đã qua một khoảng thời gian kể từ khi đăng nhập hoặc tạo phiên | Giới hạn thời gian sử dụng liên tục của thông tin xác thực |
| Thu hồi chủ động | Người dùng đăng xuất, đổi mật khẩu hoặc quản trị viên thu hồi | Kết thúc phiên theo một sự kiện nghiệp vụ hoặc bảo mật |

Chỉ cấu hình `maxInactiveInterval` không tự tạo ra giới hạn tuổi đời tuyệt đối. Nếu cần giới hạn đó, ứng dụng có thể lưu thời điểm xác thực ban đầu trong một thuộc tính phiên hoặc trong kho xác thực, rồi kiểm tra ở mỗi request được bảo vệ. Không nên cập nhật lại thời điểm ban đầu mỗi khi request chạy, vì như vậy chính sách tuyệt đối sẽ biến thành timeout trượt.

## 3. Phiên bị xóa hoặc vô hiệu hóa chủ động

### 3.1. Gọi invalidate khi đăng xuất

`HttpSession.invalidate()` kết thúc phiên hiện tại. Sau khi phiên bị vô hiệu hóa, ứng dụng không được tiếp tục dùng đối tượng phiên như một phiên hợp lệ. Các thao tác truy cập trạng thái của phiên đã invalid có thể phát sinh `IllegalStateException`.

Ví dụ với Servlet:

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

`getSession(false)` rất quan trọng trong luồng đăng xuất: nó chỉ lấy phiên hiện có và không tạo phiên mới. Nếu dùng `getSession()` sau khi người dùng đã đăng xuất, ứng dụng có thể tạo một phiên mới chỉ để thực hiện thao tác kết thúc phiên.

Khi dùng Spring Security, cấu hình logout mặc định thường vô hiệu hóa HTTP session. Nếu tùy chỉnh logout handler, cần kiểm tra rõ thao tác invalidation và xóa cookie phiên có còn được thực hiện hay không. Không nên chỉ xóa cookie ở trình duyệt mà để dữ liệu phiên đã xác thực tồn tại trong repository.

### 3.2. Thu hồi phiên từ một nơi khác

Ứng dụng có thể cần kết thúc phiên ngoài request đăng xuất hiện tại, ví dụ:

- Người dùng đổi mật khẩu và tổ chức yêu cầu thu hồi các phiên cũ.
- Quản trị viên khóa tài khoản hoặc buộc người dùng đăng nhập lại.
- Hệ thống phát hiện hoạt động đáng ngờ và cần vô hiệu hóa một phiên.
- Người dùng chọn đăng xuất khỏi tất cả thiết bị.

Với Spring Session, dữ liệu phiên nằm trong repository dùng chung nên một thao tác xóa phiên có thể được các instance khác quan sát. Ở tầng repository, thao tác xóa thường được biểu diễn bằng `deleteById(sessionId)`; trong mã Servlet, nên ưu tiên API `HttpSession.invalidate()` cho phiên của request hiện tại. Khi cần quản trị phiên khác, dùng API quản lý phiên phù hợp với repository và phiên bản Spring Session đang triển khai.

Để đăng xuất tất cả thiết bị, ứng dụng cần biết những session ID nào thuộc về tài khoản. Có thể duy trì chỉ mục liên kết tài khoản với các phiên, hoặc dùng cơ chế quản lý phiên của Spring Security nếu phù hợp. Không thể suy ra mọi session ID của một người dùng chỉ từ một cookie phiên đơn lẻ.

### 3.3. Xóa dữ liệu phiên và xóa cookie

Hai thao tác cần được xem là hai phần của cùng một luồng:

1. Vô hiệu hóa hoặc xóa dữ liệu phiên phía máy chủ.
2. Gửi response yêu cầu trình duyệt xóa cookie chứa mã phiên.

Spring Session tích hợp với cơ chế phân giải session ID trong cookie. Khi ứng dụng vô hiệu hóa phiên qua filter và repository, resolver có thể gửi cookie hết hạn về trình duyệt. Nếu ứng dụng tự quản lý cookie hoặc dùng tên cookie tùy chỉnh, cần bảo đảm response xóa đúng tên, đường dẫn (`Path`) và domain đã dùng khi tạo cookie. Cookie chỉ bị xóa nếu các thuộc tính định danh phù hợp với cookie ban đầu.

Xóa cookie không thu hồi một bản sao mã phiên mà kẻ khác đã lấy được. Vì vậy, bước xóa dữ liệu ở repository là phần quyết định để mã phiên cũ không còn truy cập được.

## 4. Khi mã phiên được gửi lên nhưng repository không tìm thấy

### 4.1. Những nguyên nhân thường gặp

Một request có thể mang cookie `SESSION=abc123`, nhưng repository không còn phiên có ID `abc123`. Các nguyên nhân gồm:

- Phiên đã vượt quá thời gian không hoạt động và bị repository xem là hết hạn.
- Người dùng đã đăng xuất và phiên bị xóa.
- Quản trị viên hoặc một luồng bảo mật đã thu hồi phiên.
- Trình duyệt gửi cookie cũ sau khi dữ liệu phiên đã hết hạn hoặc bị dọn dẹp.
- Client gửi một ID ngẫu nhiên, bị cắt, sai định dạng hoặc không thuộc ứng dụng hiện tại.
- Request đi tới môi trường, namespace hoặc kho dữ liệu khác với nơi phiên được tạo.

Với request chứa ID không còn hợp lệ, ứng dụng không được xem cookie là bằng chứng rằng người dùng đã đăng nhập. Trạng thái xác thực phải được xác định từ dữ liệu phiên còn hiệu lực và các thông tin xác thực hợp lệ khác.

### 4.2. getSession(false) và getSession()

Servlet API có hai cách lấy session với hành vi khác nhau:

```java
HttpSession existing = request.getSession(false);
if (existing == null) {
    // Không có phiên hợp lệ gắn với request này.
    return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
}

HttpSession session = request.getSession();
// Nếu chưa có phiên hợp lệ, lời gọi này có thể tạo một phiên mới.
```

`getSession(false)` trả về `null` nếu request không có phiên hợp lệ. Đây thường là lựa chọn phù hợp khi kiểm tra trạng thái đăng nhập hoặc xử lý endpoint chỉ dành cho người đã xác thực.

`getSession()` tương đương yêu cầu lấy hoặc tạo phiên. Nếu request mang cookie cũ nhưng repository không tìm thấy dữ liệu, lớp quản lý session có thể tạo một phiên mới. Phiên mới đó không khôi phục trạng thái đăng nhập cũ; nó chỉ là một phiên mới, chưa được xác thực cho đến khi ứng dụng thực hiện quy trình đăng nhập.

Tránh gọi `getSession()` một cách vô thức trong filter, interceptor hoặc endpoint kiểm tra xác thực. Việc đó có thể tạo session cho request ẩn danh, làm tăng số lượng phiên và gây khó khăn khi phân biệt người dùng chưa đăng nhập với người dùng có phiên đã bị thu hồi.

### 4.3. Mã phiên không hợp lệ và phiên không hợp lệ về xác thực

Một session có thể vẫn tồn tại nhưng thông tin xác thực trong đó đã không còn được chấp nhận. Ví dụ, phiên còn trong repository nhưng tài khoản đã bị khóa hoặc quyền truy cập đã thay đổi. Đây là tình huống khác với việc không tìm thấy session.

Ứng dụng nên kiểm tra cả hai lớp:

1. Session ID có ánh xạ đến một phiên còn hiệu lực hay không?
2. Người dùng và quyền được lưu hoặc tham chiếu trong phiên còn được phép truy cập hay không?

Khi cần thu hồi nhanh, ứng dụng có thể xóa phiên hoặc kiểm tra một phiên bản bảo mật (security version) của tài khoản. Nếu chỉ lưu vai trò trong session trong thời gian dài mà không có cơ chế cập nhật hoặc thu hồi, quyền cũ có thể tiếp tục được dùng cho đến khi phiên hết hạn.

## 5. Vòng đời phiên trong Spring Session

### 5.1. Vai trò của SessionRepositoryFilter

Trong ứng dụng Servlet, `SessionRepositoryFilter` bọc request và response để ánh xạ API `HttpSession` sang một session do Spring Session quản lý. Khi request đến, filter đọc mã phiên qua `HttpSessionIdResolver`, tra cứu repository và cung cấp phiên tương ứng cho mã ứng dụng. Khi request hoàn tất, các thay đổi được lưu theo cơ chế của repository.

Luồng tổng quát:

```mermaid
flowchart TD
    A[Request mang cookie session ID] --> B[SessionRepositoryFilter]
    B --> C{Repository tìm thấy phiên còn hiệu lực?}
    C -- Có --> D[Khôi phục HttpSession]
    C -- Không --> E[getSession(false) trả null]
    D --> F[Ứng dụng xử lý request]
    E --> F
    F --> G{Ứng dụng yêu cầu tạo phiên?}
    G -- Có --> H[Tạo phiên mới và lưu repository]
    G -- Không --> I[Không tạo phiên]
    H --> J[Commit response và cập nhật cookie khi cần]
    I --> K[Response]
    J --> K
```

Sơ đồ mô tả luồng khái niệm. Việc ghi dữ liệu, đặt TTL và cập nhật cookie phụ thuộc repository, resolver và thời điểm response được commit.

### 5.2. Redis: TTL và sự kiện hết hạn

Với repository Redis, Spring Session lưu dữ liệu phiên trong Redis và thiết lập thời hạn tương ứng. Redis có thể tự hết hạn key khi TTL kết thúc. Thời điểm Redis thực hiện xóa vật lý và thời điểm ứng dụng quan sát được sự kiện hết hạn không nhất thiết trùng chính xác với giây timeout đã cấu hình.

Spring Session Redis có thể sử dụng Redis keyspace notifications để nhận biết key hết hạn và phát sự kiện phiên. Tính năng này phụ thuộc cấu hình thông báo keyspace và cách Redis được triển khai. Nếu thông báo bị tắt, bị giới hạn hoặc không được chuyển tiếp trong môi trường cluster, ứng dụng không nên giả định mọi sự kiện hết hạn đều được giao đúng một lần.

Một số cơ chế lưu trữ giữ metadata hoặc key phụ trợ trong một khoảng thời gian sau khi session hết hạn để hỗ trợ xử lý sự kiện. Vì vậy, việc một key còn nhìn thấy trong công cụ quản trị Redis không nhất thiết có nghĩa session vẫn được coi là hợp lệ. Hãy dùng API repository và kiểm tra thời hạn thay vì suy luận chỉ từ sự tồn tại của một key nội bộ.

### 5.3. JDBC: thời điểm hết hạn và dọn dẹp bản ghi

Với repository JDBC, dữ liệu phiên thường được lưu trong các bảng Spring Session cùng thời điểm hết hạn. Khi truy vấn, repository có thể xem phiên đã hết hạn là không còn hợp lệ ngay cả khi bản ghi chưa được xóa vật lý khỏi bảng.

Tác vụ dọn dẹp định kỳ xóa các bản ghi hết hạn để tránh bảng tăng trưởng không kiểm soát. Khoảng thời gian chạy tác vụ dọn dẹp ảnh hưởng đến thời điểm bản ghi biến mất khỏi cơ sở dữ liệu, nhưng không nên làm thay đổi quy tắc rằng phiên hết hạn không được tiếp tục dùng để xác thực. Tên bảng, schema và lịch cleanup cần theo đúng phiên bản Spring Session và cấu hình triển khai.

| Khía cạnh | Redis | JDBC |
|---|---|---|
| Thời hạn | TTL trên dữ liệu lưu trữ và logic của repository | Thời điểm hết hạn được lưu cùng bản ghi |
| Dọn dẹp | Redis tự xử lý TTL; repository có thể dùng key phụ trợ cho sự kiện | Tác vụ cleanup loại bỏ bản ghi hết hạn |
| Sự kiện | Việc nhận sự kiện hết hạn phụ thuộc keyspace notifications và cấu hình Redis | Khả năng và thời điểm phát sự kiện phụ thuộc implementation và đường cleanup |
| Kiểm tra hợp lệ | Dùng repository, không chỉ kiểm tra key còn hiện diện | Dùng repository, không chỉ kiểm tra hàng còn trong bảng |

## 6. Sự kiện vòng đời phiên

Spring Session cung cấp các sự kiện vòng đời như `SessionCreatedEvent`, `SessionDeletedEvent` và `SessionExpiredEvent`. Chúng giúp ứng dụng quan sát phiên được tạo, bị xóa chủ động hoặc hết hạn. Việc sự kiện nào được phát và thời điểm phát phụ thuộc repository cụ thể cùng cấu hình cần thiết cho repository đó.

Ví dụ lắng nghe sự kiện:

```java
@Component
public class SessionLifecycleListener {

    @EventListener
    public void onSessionExpired(SessionExpiredEvent event) {
        String sessionId = event.getSessionId();
        // Ghi nhận số liệu hoặc log sự kiện hết hạn.
    }

    @EventListener
    public void onSessionDeleted(SessionDeletedEvent event) {
        String sessionId = event.getSessionId();
        // Ghi nhận thao tác xóa phiên.
    }
}
```

Các import sự kiện thuộc package `org.springframework.session.events`. Hãy kiểm tra API của phiên bản Spring Session đang sử dụng nếu cần truy cập thêm thông tin trong đối tượng sự kiện.

### 6.1. Dùng sự kiện cho việc gì?

Sự kiện phù hợp cho các tác vụ quan sát và đồng bộ phụ trợ, chẳng hạn:

- Ghi log thời điểm phiên hết hạn hoặc bị thu hồi.
- Cập nhật số liệu về số phiên hoạt động.
- Gửi thông báo bảo mật theo chính sách của ứng dụng.
- Dọn dữ liệu phụ trợ có thể tái tạo và gắn với session ID.
- Phát tín hiệu để các thành phần khác cập nhật trạng thái hiển thị.

Không nên đặt một nghiệp vụ không thể mất vào một listener sự kiện hết hạn. Thông báo có thể đến trễ, bị mất khi hạ tầng gặp sự cố hoặc được phát lại tùy cơ chế triển khai. Nếu phải thực hiện một hành động quan trọng như thu hồi quyền, đóng giao dịch hoặc ghi nhận kiểm toán bắt buộc, hãy bảo đảm hành động đó có cơ chế bền vững, idempotent và có thể retry độc lập với sự kiện session.

### 6.2. Phân biệt xóa và hết hạn trong xử lý sự kiện

`SessionDeletedEvent` thể hiện phiên bị xóa, thường do thao tác chủ động. `SessionExpiredEvent` thể hiện phiên hết hạn theo thời hạn. Hai sự kiện có thể dẫn đến cùng hành động phụ trợ, nhưng ý nghĩa vận hành khác nhau. Ví dụ, số liệu đăng xuất chủ động nên phân biệt với số liệu timeout để đội sản phẩm hiểu hành vi người dùng.

Không suy luận rằng mọi session biến mất đều tạo ra một sự kiện mà mọi instance đều nhận được. Nếu cần một thống kê chính xác, hãy thiết kế nguồn dữ liệu kiểm toán riêng và xác định rõ mức bảo đảm giao nhận sự kiện của repository.

## 7. Xử lý khi repository không truy cập được

Không tìm thấy phiên và không thể truy cập repository là hai tình huống hoàn toàn khác nhau:

- Repository trả lời thành công nhưng không có session ID: phiên không tồn tại hoặc không còn hợp lệ.
- Kết nối Redis/JDBC timeout, bị từ chối hoặc lỗi: ứng dụng chưa xác định được trạng thái phiên.

Không được diễn giải lỗi kết nối thành "người dùng chưa đăng nhập" rồi âm thầm tạo phiên ẩn danh nếu request đang cần xác thực. Với endpoint được bảo vệ, nên xử lý theo hướng fail closed: không cấp quyền khi không thể xác minh session. Có thể trả lỗi dịch vụ tạm thời phù hợp, ghi log có mã tương quan và phát cảnh báo vận hành.

Các điểm cần cấu hình và giám sát:

- Timeout kết nối và timeout truy vấn để request không chờ vô hạn.
- Connection pool đủ dùng nhưng không vượt quá khả năng của Redis hoặc cơ sở dữ liệu.
- Số lỗi đọc/ghi session, độ trễ, số kết nối đang dùng và tình trạng repository.
- Chính sách retry có giới hạn; tránh retry dồn dập làm kho dữ liệu quá tải.
- Cách phản hồi riêng cho request công khai và request yêu cầu xác thực.

Không nên tự động xóa cookie khi chỉ gặp lỗi mạng. Một lỗi tạm thời không chứng minh phiên đã hết hạn; xóa cookie có thể khiến người dùng mất phiên dù dữ liệu vẫn còn trong repository. Chỉ thực hiện luồng xóa cookie khi ứng dụng đã xác định phiên không còn hợp lệ hoặc đang chủ động đăng xuất.

## 8. Cạnh tranh giữa request và thay đổi vòng đời phiên

Một trình duyệt có thể gửi nhiều request đồng thời. Ví dụ, request A đang tải dữ liệu tài khoản trong khi request B gửi logout. Cả hai có thể bắt đầu khi phiên còn hiệu lực. Nếu B xóa phiên trước khi A hoàn tất, kết quả cuối cùng phụ thuộc thời điểm đọc/ghi và cách repository xử lý các thao tác đó.

Một số tình huống cần chú ý:

1. **Request đọc bắt đầu trước khi hết hạn:** request có thể đã khôi phục phiên trước thời điểm timeout, trong khi một request khác đến sau đó không còn tìm thấy phiên.
2. **Logout chạy đồng thời với cập nhật:** request cập nhật có thể đã đọc dữ liệu trước khi logout xóa phiên. Không giả định cập nhật đang chạy sẽ tự động bị hủy.
3. **Request tạo phiên mới sau khi phiên cũ mất:** nếu code gọi `getSession()` khi tra cứu không thành công, một phiên mới có thể được tạo. Nó không được kế thừa trạng thái xác thực của phiên cũ.
4. **Nhiều instance cùng cập nhật:** các request trên những instance khác nhau có thể ghi dữ liệu theo thứ tự khác nhau. Không dùng session làm nơi chứa trạng thái nghiệp vụ cần giao dịch phức tạp.

Để giảm rủi ro, hãy dùng `getSession(false)` trong các bước chỉ kiểm tra phiên, thực hiện kiểm tra quyền ở gần thời điểm thao tác nhạy cảm, giữ session nhỏ và đưa dữ liệu nghiệp vụ cần nhất quán vào kho dữ liệu nghiệp vụ. Nếu ứng dụng cần đảm bảo logout có hiệu lực ngay cả với request đang chạy, cần thiết kế thêm cơ chế kiểm tra trạng thái thu hồi hoặc phiên bản xác thực tại thời điểm xử lý thao tác quan trọng.

## 9. Kiểm thử hết hạn, xóa và session không tồn tại

Kiểm thử nên dùng repository thật hoặc môi trường tích hợp tương đương khi cần xác minh TTL, cleanup và sự kiện. Mock `HttpSession` đơn lẻ không thể chứng minh Redis/JDBC đã lưu và hết hạn dữ liệu đúng cách.

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Session hợp lệ | Đăng nhập, gửi request tiếp theo với cookie nhận được | Request truy cập được thông tin phiên |
| Idle timeout | Đặt timeout ngắn, chờ quá thời hạn rồi gửi request | Phiên cũ không còn được xác thực |
| Chủ động logout | Đăng nhập rồi gọi endpoint logout | Repository không còn chấp nhận phiên cũ; response xóa cookie theo cấu hình |
| Cookie cũ | Giữ cookie sau timeout hoặc logout rồi gửi lại | Request được xem là không có phiên hợp lệ |
| Không tự tạo phiên | Gửi cookie không tồn tại đến endpoint dùng `getSession(false)` | Không có session mới được tạo chỉ vì kiểm tra |
| Tạo phiên mới có chủ đích | Gửi request đến luồng cho phép tạo session | Session mới có ID mới và chưa được xác thực |
| Thu hồi từ instance khác | Tạo phiên qua A, xóa qua B, gửi cookie cũ đến A | A cũng không chấp nhận phiên đã xóa |
| Repository tạm lỗi | Ngắt kết nối hoặc làm timeout Redis/JDBC trong môi trường test | Request được xử lý theo chính sách lỗi dịch vụ, không cấp quyền sai |
| Sự kiện vòng đời | Theo dõi event khi tạo, xóa và hết hạn | Sự kiện phù hợp được phát theo khả năng repository và cấu hình |

Ví dụ kiểm thử đơn giản cho hành vi không tạo phiên khi không có phiên hiện hữu:

```java
@Test
void shouldNotCreateSessionWhenLookupUsesFalse() {
    MockHttpServletRequest request = new MockHttpServletRequest();

    HttpSession session = request.getSession(false);

    assertNull(session);
}
```

Đây chỉ là kiểm thử hành vi Servlet cơ bản. Kiểm thử tích hợp Spring Session cần gửi request qua filter chain và repository thực, sau đó xác minh cùng cookie ở instance hoặc application context khác.

### 9.1. Kiểm thử trên nhiều instance

Một kịch bản tích hợp hữu ích:

1. Khởi động hai instance A và B dùng chung Redis hoặc JDBC repository.
2. Đăng nhập qua A và lưu cookie session.
3. Gửi request qua B để xác nhận phiên được khôi phục.
4. Đăng xuất qua B.
5. Gửi lại cookie cũ qua A; A phải xem phiên là không còn hiệu lực.
6. Tạo phiên mới, để timeout xảy ra và gửi cookie cũ qua instance còn lại.
7. Tắt repository tạm thời và xác nhận request được bảo vệ không được cấp quyền khi trạng thái phiên chưa thể xác minh.

Kịch bản này phát hiện lỗi thường bị bỏ qua khi chỉ kiểm thử một instance: cấu hình namespace khác nhau, cookie resolver không đồng nhất, repository không dùng chung, hoặc một instance vẫn giữ dữ liệu phiên cục bộ ngoài ý muốn.

## 10. Các lỗi triển khai thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Người dùng bị đăng xuất sớm | Idle timeout quá ngắn, TTL không đồng nhất hoặc request không cập nhật phiên như dự kiến | Kiểm tra timeout hiệu lực, thời điểm truy cập và cấu hình giữa các instance |
| Đăng xuất xong vẫn truy cập được | Chỉ xóa cookie, chưa xóa session ở repository; hoặc endpoint không thực hiện invalidation | Kiểm tra repository và logout handler |
| Trình duyệt gửi cookie cũ liên tục | Cookie chưa được xóa hoặc response xóa sai Path/Domain | Kiểm tra header `Set-Cookie`, tên cookie, Path và Domain |
| Bản ghi còn trong JDBC sau timeout | Cleanup chạy định kỳ; bản ghi đã hết hạn về mặt logic nhưng chưa bị xóa vật lý | Kiểm tra expiration time và lịch cleanup, không chỉ đếm hàng trong bảng |
| Không nhận được event hết hạn từ Redis | Keyspace notifications hoặc cấu hình triển khai không phù hợp | Kiểm tra cấu hình Redis, quyền và đường truyền event |
| Lỗi repository bị coi là đăng xuất | Ứng dụng gộp lỗi kết nối với kết quả không tìm thấy session | Phân biệt exception hạ tầng với kết quả lookup rỗng |
| Request ẩn danh tạo quá nhiều session | Filter hoặc interceptor gọi `getSession()` khi chỉ cần kiểm tra | Chuyển sang `getSession(false)` tại đường kiểm tra |

## 11. Nguyên tắc áp dụng

- Đặt idle timeout phù hợp với độ nhạy của ứng dụng và bổ sung absolute lifetime nếu chính sách yêu cầu.
- Phân biệt hết hạn, xóa chủ động, không tìm thấy session và lỗi repository.
- Dùng `getSession(false)` khi chỉ kiểm tra phiên; chỉ tạo phiên mới ở luồng thực sự cần nó.
- Khi đăng xuất, vô hiệu hóa dữ liệu phiên phía máy chủ và xóa cookie phiên ở response.
- Dùng sự kiện vòng đời cho quan sát và công việc phụ trợ có thể retry; không đặt nghiệp vụ quan trọng duy nhất trong event listener.
- Kiểm tra khả năng phát sự kiện, TTL và cleanup theo repository cụ thể.
- Kiểm thử timeout, logout, cookie cũ, thu hồi liên instance, request đồng thời và lỗi kho lưu trữ.
- Khi không thể xác minh session do repository lỗi, không cấp quyền dựa trên trạng thái chưa được xác minh.

Một cookie chỉ cho biết client đang gửi một mã phiên. Trạng thái đăng nhập thực tế phụ thuộc vào việc Spring Session có khôi phục được phiên còn hiệu lực từ repository và ứng dụng có chấp nhận thông tin xác thực trong phiên đó hay không. Hiểu rõ ranh giới giữa hết hạn, xóa và không tồn tại giúp xử lý đúng cả luồng Servlet thông thường lẫn hệ thống Spring Session chạy trên nhiều instance.
