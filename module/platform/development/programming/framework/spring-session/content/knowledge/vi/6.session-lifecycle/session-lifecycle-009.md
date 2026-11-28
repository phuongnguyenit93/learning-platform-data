# Yêu cầu đang chạy khi phiên bị hết hạn hoặc bị thu hồi

Trong ứng dụng Spring Session, một phiên có thể hết hạn vì không hoạt động, bị người dùng đăng xuất, bị quản trị viên thu hồi hoặc bị hệ thống bảo mật vô hiệu hóa. Tình huống khó xử lý xuất hiện khi một request đã bắt đầu chạy nhưng phiên của nó bị hết hạn hoặc thu hồi trước khi request hoàn tất.

Điều cần hiểu đầu tiên là việc phiên bị xóa khỏi Redis, JDBC hoặc repository không tự động dừng thread đang xử lý request. Request đó có thể đã đọc session và xác thực người dùng trước khi phiên bị thu hồi. Vì vậy, ứng dụng cần phân biệt trạng thái của phiên trong kho lưu trữ với trạng thái xử lý đang diễn ra trong request, đồng thời quyết định những thao tác nghiệp vụ nào phải được kiểm tra lại quyền trước khi hoàn tất.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt hết hạn do inactivity với thu hồi chủ động.
- Giải thích request đang chạy có thể tiếp tục thế nào sau khi phiên bị xóa.
- Nhận diện race condition giữa request đang ghi phiên và thao tác logout/thu hồi.
- Thiết kế kiểm tra trạng thái phiên cho các thao tác nhạy cảm.
- Xử lý an toàn lỗi phiên đã invalidated và các request chạy lâu.
- Kiểm thử tình huống nhiều request và nhiều instance cùng truy cập một phiên.

## 1. Phân biệt hết hạn và thu hồi phiên

Hai nhóm sự kiện thường khiến một phiên không còn được chấp nhận:

| Trường hợp | Nguyên nhân | Ý nghĩa |
|---|---|---|
| Hết hạn do không hoạt động | Không có request truy cập phiên trong khoảng thời gian cấu hình | Repository hoặc Servlet container coi phiên đã quá thời gian inactivity |
| Thu hồi chủ động | Người dùng logout, quản trị viên kết thúc phiên, tài khoản bị khóa hoặc chính sách bảo mật yêu cầu thu hồi | Phiên bị vô hiệu hóa dù thời gian timeout chưa hết |

Với Servlet, `HttpSession.setMaxInactiveInterval(seconds)` đặt khoảng thời gian tối đa một phiên có thể không được truy cập trước khi hết hạn. Giá trị được tính bằng giây. Giá trị bằng không hoặc âm biểu thị phiên không hết hạn do inactivity theo hợp đồng Servlet; trong hệ thống thực tế, vẫn cần cân nhắc chính sách bảo mật và giới hạn lưu trữ.

Spring Session áp dụng timeout thông qua repository và cấu hình của ứng dụng. Khi dùng Redis, TTL của dữ liệu phiên được quản lý theo chính sách repository. Khi dùng JDBC, repository và cơ chế dọn dẹp xác định cách phát hiện và xóa phiên hết hạn. Chi tiết thời điểm xóa vật lý và phát sự kiện có thể khác nhau giữa các repository.

Thu hồi chủ động thường bắt đầu từ thao tác như:

- `HttpSession.invalidate()` trong ứng dụng Servlet.
- Logout của Spring Security.
- Xóa session ID thông qua `SessionRepository.deleteById(...)` hoặc API tương ứng của repository.
- Chính sách thu hồi tất cả phiên của một tài khoản khi đổi mật khẩu, khóa tài khoản hoặc phát hiện rủi ro.
- Kiểm soát số phiên đồng thời trong Spring Security.

Hết hạn và thu hồi đều làm cho các request sau không thể tiếp tục sử dụng phiên như trước. Tuy nhiên, chúng có thể có cách phát hiện, thời điểm dọn dữ liệu và sự kiện vòng đời khác nhau.

## 2. Điều gì xảy ra với request đã bắt đầu?

Khi một request đi qua Spring Session, `SessionRepositoryFilter` bọc request và response. Trong quá trình xử lý, ứng dụng hoặc Spring Security có thể đã lấy `HttpSession`, đọc thuộc tính và tạo `SecurityContext` cho request hiện tại.

Nếu một request khác hoặc một tác vụ nền xóa phiên trong lúc request đầu tiên vẫn chạy, không có cơ chế chung tự động gửi tín hiệu hủy tới thread đang chạy. Thread đó thường tiếp tục thực thi với dữ liệu đã đọc vào bộ nhớ của request. Những lần truy cập tiếp theo vào đối tượng session có thể gặp hành vi khác nhau tùy phiên bản, repository, thời điểm invalidation và cách session được lưu.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Instance A
    participant R as Repository dùng chung
    participant B as Instance B hoặc Logout
    C->>A: Request 1 mang session ID
    A->>R: Tìm session
    R-->>A: Trả session đang hoạt động
    A->>A: Xác thực và bắt đầu xử lý nghiệp vụ
    C->>B: Request 2: logout hoặc thu hồi
    B->>R: Xóa hoặc đánh dấu session bị thu hồi
    R-->>B: Hoàn tất thao tác repository
    Note over A: Request 1 vẫn đang chạy
    A->>A: Tiếp tục xử lý với trạng thái đã đọc
    A->>R: Có thể phát sinh thao tác lưu cuối request
    A-->>C: Response của request 1
    C->>A: Request tiếp theo với session ID cũ
    A->>R: Tìm session
    R-->>A: Không tìm thấy hoặc đã hết hạn
    A-->>C: Yêu cầu xác thực lại
~~~

Sơ đồ mô tả tình huống tổng quát. Việc request A có ghi lại dữ liệu cũ sau khi B thu hồi hay không phụ thuộc repository, chế độ flush/save, cách cập nhật session và thời điểm hai thao tác cạnh tranh. Không nên giả định mọi repository đều xử lý race condition giống nhau.

Có ba điều quan trọng:

1. **Request đang chạy không tự động bị dừng.** Việc xóa session trong repository không tương đương với hủy request HTTP, ngắt thread hoặc rollback giao dịch nghiệp vụ.
2. **Dữ liệu request có thể đã được đọc trước khi thu hồi.** `Authentication`, `SecurityContext` và các thuộc tính đã copy vào biến cục bộ có thể vẫn tồn tại trong bộ nhớ request.
3. **Thao tác lưu cuối request có thể cạnh tranh với thao tác xóa.** Một request cũ có thể cố lưu session sau khi một request khác đã thu hồi; kết quả chính xác phụ thuộc repository và cấu hình.

Do đó, logout thành công thường bảo đảm các request tiếp theo không thể dùng phiên cũ sau khi repository đã xử lý việc thu hồi. Nó không phải cam kết rằng mọi request đã được xác thực trước thời điểm logout sẽ bị dừng ngay lập tức.

## 3. Hết hạn trong khi request đang chạy

Timeout của session thường biểu thị thời gian không hoạt động, không phải giới hạn tuyệt đối cho thời gian thực thi của một request. Tuy nhiên, request dài vẫn có thể gặp vấn đề nếu thời gian xử lý vượt quá timeout hoặc nếu repository không gia hạn TTL như ứng dụng kỳ vọng.

Thời điểm cập nhật `lastAccessedTime`, gia hạn TTL và ghi session phụ thuộc cách Spring Session cùng repository xử lý request. Một request có thể cập nhật thời gian truy cập khi bắt đầu, trong lúc lưu hoặc theo chính sách flush. Vì vậy:

- Không suy ra rằng một request còn chạy thì session chắc chắn không thể hết hạn.
- Không giả định request dài tự động gia hạn TTL liên tục.
- Không dùng `maxInactiveInterval` như timeout cho tác vụ nghiệp vụ hoặc giới hạn thời gian chạy của HTTP request.
- Cần kiểm tra hành vi thực tế với repository, `FlushMode`, `SaveMode` và cấu hình timeout của ứng dụng.

Ví dụ, một request tạo báo cáo mất 20 phút trong khi timeout phiên là 15 phút. Nếu phiên hết hạn trong thời gian đó, phần code đã chạy có thể tiếp tục, nhưng các request mới dùng session ID cũ có thể không tìm thấy phiên. Nếu request báo cáo cần ghi kết quả nhạy cảm hoặc thay đổi dữ liệu quan trọng, phải xác định lại quyền tại ranh giới nghiệp vụ thay vì dựa duy nhất vào trạng thái đã xác thực lúc request bắt đầu.

Đối với tác vụ dài, hãy cân nhắc chuyển công việc sang hàng đợi hoặc job worker. Request HTTP tạo job và nhận mã theo dõi; worker kiểm tra quyền, trạng thái tài khoản và chính sách truy cập theo thiết kế của job. Không giữ `HttpSession` hoặc đối tượng request trong một tác vụ nền để sử dụng sau khi request kết thúc.

## 4. Khi session bị invalidate trong cùng request

Nếu chính request hiện tại gọi `session.invalidate()`, phiên bị vô hiệu hóa theo hợp đồng Servlet. Sau thao tác này, không tiếp tục dùng session như một đối tượng còn hiệu lực. Những thao tác truy cập trạng thái phiên đã invalidated, chẳng hạn đọc hoặc ghi thuộc tính, có thể ném `IllegalStateException`.

Ví dụ không an toàn:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();

    // Không dùng session sau khi invalidate.
    Object cart = session.getAttribute("cart");
}
~~~

Hãy đọc dữ liệu cần thiết trước khi invalidate, hoặc kết thúc xử lý phiên ngay sau thao tác thu hồi:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}

// Không truy cập lại đối tượng session đã bị vô hiệu hóa.
return "redirect:/login";
~~~

Trong ứng dụng có Spring Security, nên dùng logout flow đã cấu hình thay vì tự gọi `invalidate()` rời rạc ở một controller. Logout handler có thể xóa SecurityContext, xóa cookie hoặc header session ID, cập nhật session registry và thực hiện các thao tác liên quan khác.

## 5. Thu hồi từ request khác hoặc instance khác

Trong môi trường nhiều instance, request A có thể đang xử lý tại instance A trong khi request B thực hiện logout tại instance B. Cả hai cùng dùng Redis hoặc JDBC làm repository. Repository dùng chung giúp các instance nhìn thấy cùng trạng thái lưu trữ, nhưng không tạo ra một khóa tự động bao quanh toàn bộ thời gian xử lý request.

Ví dụ:

- Request A tải session và bắt đầu xử lý thanh toán.
- Request B logout và xóa session.
- Request A tiếp tục xử lý với `Authentication` đã được tạo trước đó.
- Request A ghi kết quả nghiệp vụ hoặc lưu thuộc tính session vào cuối request.

Nếu nghiệp vụ chỉ là xem dữ liệu công khai, việc request A hoàn tất có thể không gây hậu quả đáng kể. Nếu nghiệp vụ là chuyển tiền, đổi email, cấp quyền hoặc thay đổi thông tin bảo mật, việc chỉ kiểm tra session ở đầu request có thể không đáp ứng yêu cầu thu hồi tức thời.

Để xử lý đúng, hãy xác định mức bảo đảm cần thiết:

| Yêu cầu | Cách tiếp cận |
|---|---|
| Request đã bắt đầu được phép hoàn tất | Chấp nhận ngữ nghĩa request đã xác thực tại thời điểm bắt đầu; tài liệu hóa chính sách |
| Request mới phải từ chối ngay sau logout | Xóa session khỏi repository và xác minh request kế tiếp không còn tải được phiên |
| Thao tác nhạy cảm phải kiểm tra lại quyền | Kiểm tra trạng thái tài khoản/phiên tại ranh giới nghiệp vụ trước khi ghi dữ liệu |
| Thu hồi phải thắng mọi ghi đồng thời | Dùng cơ chế đồng bộ hoặc fencing token/phiên bản trạng thái trong kho dùng chung, phối hợp với giao dịch nghiệp vụ |

Không thể đạt tính nguyên tử chỉ bằng cách gọi `getSession(false)` lần thứ hai. Request wrapper có thể đang giữ đối tượng session đã tải trước đó. Nếu cần trạng thái thu hồi mới nhất, việc kiểm tra phải đọc từ nguồn trạng thái dùng chung có thẩm quyền, không dựa trên một bản sao cũ trong request.

## 6. Kiểm tra lại quyền trước thao tác nhạy cảm

Với thao tác có hậu quả lớn, nên đặt một bước kiểm tra trạng thái ngay trước khi thực hiện thay đổi nghiệp vụ. Một cách triển khai là duy trì trạng thái thu hồi tập trung theo session ID hoặc theo tài khoản. Mỗi instance đều truy vấn cùng nguồn dữ liệu.

Ví dụ dưới đây dùng một interface minh họa để tách chính sách kiểm tra khỏi controller:

~~~java
public interface SessionLiveness {
    boolean isActive(String sessionId);
}
~~~

Service kiểm tra phiên hiện có và trạng thái thu hồi:

~~~java
public class ActiveSessionGuard {
    private final SessionLiveness sessionLiveness;

    public ActiveSessionGuard(SessionLiveness sessionLiveness) {
        this.sessionLiveness = sessionLiveness;
    }

    public String requireActiveSession(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new SessionNoLongerActiveException();
        }

        String sessionId;
        try {
            sessionId = session.getId();
        } catch (IllegalStateException ex) {
            throw new SessionNoLongerActiveException();
        }

        if (!sessionLiveness.isActive(sessionId)) {
            throw new SessionNoLongerActiveException();
        }

        return sessionId;
    }
}
~~~

`SessionLiveness` không phải API có sẵn của Spring Session; đây là abstraction của ứng dụng. Phần triển khai cần đọc một nguồn trạng thái dùng chung có thẩm quyền, chẳng hạn bảng trạng thái phiên hoặc kho revocation riêng. Không triển khai nó bằng một map trong bộ nhớ của từng instance vì các instance sẽ có kết quả khác nhau.

Ví dụ sử dụng ở service nghiệp vụ:

~~~java
public Receipt confirmTransfer(
        HttpServletRequest request, TransferCommand command) {

    String sessionId = activeSessionGuard.requireActiveSession(request);
    return transferService.confirm(command, sessionId);
}
~~~

Đây là một bước kiểm tra bổ sung, không tự tạo ra bảo đảm nguyên tử. Phiên vẫn có thể bị thu hồi ngay sau khi `isActive` trả về `true` và trước khi giao dịch hoàn tất. Nếu yêu cầu bảo mật bắt buộc thao tác thu hồi phải thắng mọi cập nhật đang chạy, việc kiểm tra và cập nhật nghiệp vụ phải được phối hợp bằng transaction, khóa phân tán hoặc fencing token trên cùng nguồn trạng thái có thể đồng bộ.

Một thiết kế mạnh hơn có thể gắn `sessionVersion` hoặc `revocationVersion` vào thông tin xác thực và so sánh với phiên bản hiện tại của tài khoản trong kho dữ liệu. Khi logout toàn bộ phiên hoặc khóa tài khoản, tăng phiên bản thu hồi. Các thao tác nhạy cảm kiểm tra phiên bản trong cùng transaction với cập nhật nghiệp vụ. Cách này giúp phát hiện request mang thông tin xác thực cũ, kể cả khi request vẫn giữ `SecurityContext` trong bộ nhớ.

## 7. Xử lý request khi phiên không còn hoạt động

Khi ứng dụng phát hiện phiên đã hết hạn hoặc bị thu hồi, hãy kết thúc request theo ngữ nghĩa của endpoint:

- API yêu cầu đăng nhập: trả về `401 Unauthorized` hoặc lỗi xác thực tương ứng theo hợp đồng API.
- Endpoint giao diện web: chuyển hướng người dùng tới trang đăng nhập, có thể kèm thông báo phiên đã hết hạn.
- Thao tác nhạy cảm chưa thực hiện: dừng trước khi ghi dữ liệu và yêu cầu xác thực lại.
- Thao tác đã hoàn tất trong transaction: trả về kết quả giao dịch đã commit; không giả vờ rollback nếu dữ liệu đã được ghi.
- Request chạy nền: kiểm tra lại quyền theo danh tính và chính sách job, không phụ thuộc session HTTP đã kết thúc.

Không nên bắt `IllegalStateException` rồi tiếp tục nghiệp vụ như thể phiên vẫn hợp lệ. Nếu session đã bị invalidated, hãy kết thúc luồng xử lý hoặc chuyển sang một nhánh không cần phiên đã được thiết kế rõ ràng.

Ví dụ xử lý lỗi trong controller advice:

~~~java
@RestControllerAdvice
public class SessionExceptionHandler {

    @ExceptionHandler(SessionNoLongerActiveException.class)
    public ResponseEntity<Map<String, String>> handleExpiredSession() {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of(
                        "code", "SESSION_EXPIRED",
                        "message", "Phiên làm việc không còn hiệu lực"));
    }
}
~~~

Với ứng dụng MVC trả về view, có thể dùng exception handler tương ứng để redirect. Không đưa session ID, token hoặc chi tiết repository vào nội dung lỗi gửi cho client.

## 8. Sự kiện hết hạn và thu hồi không phải tín hiệu hủy request

Spring Session có các sự kiện vòng đời như `SessionDeletedEvent` và `SessionExpiredEvent` khi repository và cấu hình hỗ trợ phát các sự kiện tương ứng. Ứng dụng có thể lắng nghe để:

- Ghi nhận metric số phiên hết hạn hoặc bị xóa.
- Dọn dữ liệu phụ trợ liên quan đến phiên.
- Cập nhật dashboard hoặc audit log.
- Gửi tín hiệu cho thành phần khác biết một phiên đã bị thu hồi.

Ví dụ listener:

~~~java
@Component
public class SessionLifecycleListener {

    @EventListener
    public void onSessionDeleted(SessionDeletedEvent event) {
        // Ghi metric hoặc dọn dữ liệu phụ trợ theo chính sách ứng dụng.
    }

    @EventListener
    public void onSessionExpired(SessionExpiredEvent event) {
        // Ghi nhận phiên hết hạn.
    }
}
~~~

Tên sự kiện và package import cần khớp với phiên bản Spring Session đang sử dụng. Khả năng phát sự kiện phụ thuộc repository. Chẳng hạn, Redis cần cấu hình keyspace notifications phù hợp để nhận biết sự kiện hết hạn; các repository khác có thể phát hiện hoặc dọn phiên theo cơ chế riêng.

Sự kiện thường được xử lý bất đồng bộ hoặc tại thời điểm repository phát hiện thay đổi. Không dùng listener làm cơ chế duy nhất để chặn một request đang chạy. Listener không thể bảo đảm đã chạy trước khi request khác ghi dữ liệu nghiệp vụ. Với kiểm soát truy cập, hãy dùng một nguồn trạng thái thu hồi có thể kiểm tra đồng bộ tại điểm cần bảo vệ.

## 9. Request dài, async processing và job nền

Servlet hỗ trợ xử lý bất đồng bộ thông qua `AsyncContext`, `Callable`, `DeferredResult` hoặc các cơ chế tương tự của framework. Khi request chuyển sang xử lý async, công việc có thể tiếp tục sau khi thread ban đầu nhường lại container. Thời gian xử lý có thể dài hơn thời gian sống của session.

Một số nguyên tắc:

1. Chỉ đọc các thuộc tính cần thiết từ session khi request còn hợp lệ.
2. Truyền dữ liệu tối thiểu như principal ID, tenant ID và mã job vào job context.
3. Không giữ `HttpServletRequest`, `HttpSession` hoặc mutable session attribute trong worker thread.
4. Kiểm tra lại trạng thái tài khoản, quyền và phiên bản thu hồi trước thao tác nhạy cảm.
5. Xác định chính sách nếu người dùng logout trong lúc job chạy: tiếp tục, hủy job hay yêu cầu xác nhận lại.

Nếu nghiệp vụ yêu cầu logout phải hủy cả job đang chạy, cần có cơ chế cancellation riêng. Ví dụ, lưu job ID theo tài khoản và phát tín hiệu hủy tới worker. Việc xóa session trong Redis hoặc JDBC không tự động hủy một tác vụ đã được đưa vào executor hoặc message queue.

## 10. Kiểm thử race condition giữa request và thu hồi

Unit test cho một controller đơn lẻ không đủ để xác minh hành vi khi hai request chạy đồng thời trên hai instance. Hãy kiểm thử với repository thật hoặc môi trường tích hợp tương đương production.

Các kịch bản quan trọng:

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Request A bắt đầu, request B logout | Request B thu hồi phiên; request mới sau đó không dùng được session ID cũ |
| Request A đọc session, request B xóa session, A tiếp tục ghi | Xác định repository có thể ghi lại dữ liệu cũ hay không và chính sách ứng dụng xử lý ra sao |
| Phiên hết hạn trong request dài | Request đang chạy hoàn tất hoặc bị chặn theo chính sách; request mới không được dùng phiên hết hạn |
| Hai request đồng thời cập nhật cùng thuộc tính | Xác định hành vi lost update và cách đồng bộ |
| Quản trị viên thu hồi phiên từ instance khác | Tất cả instance nhận biết trạng thái thu hồi theo thời gian và mức nhất quán đã thiết kế |
| Tài khoản bị khóa khi request nhạy cảm đang chạy | Thao tác nghiệp vụ kiểm tra lại trạng thái tài khoản trước khi commit |
| Job nền tiếp tục sau logout | Job tuân theo chính sách tiếp tục/hủy và không dùng session object đã kết thúc |

Có thể dùng latch hoặc barrier trong integration test để tạo đúng thứ tự:

1. Request A tải session và tạm dừng ngay trước thao tác ghi.
2. Test gửi request B thực hiện logout hoặc gọi API thu hồi.
3. Xác nhận repository không còn phiên hoạt động.
4. Cho request A tiếp tục ghi.
5. Kiểm tra trạng thái repository, kết quả nghiệp vụ và request kế tiếp.

Đừng chỉ kiểm tra response của request B. Cần kiểm tra cả repository sau khi request A hoàn tất để phát hiện trường hợp ghi cũ làm xuất hiện lại trạng thái phiên.

## 11. Giảm rủi ro trong môi trường nhiều instance

Khi triển khai nhiều instance Spring Session, cần thống nhất chính sách và cơ chế đồng bộ:

- Mọi instance dùng cùng repository, namespace, serializer và cấu hình timeout.
- Logout hoặc thu hồi phải cập nhật nguồn trạng thái dùng chung.
- Không dựa vào cache cục bộ để quyết định phiên còn hiệu lực nếu cache có thể giữ trạng thái cũ.
- Với thao tác quan trọng, kiểm tra trạng thái thu hồi tại ranh giới nghiệp vụ.
- Nếu cần tính nguyên tử, dùng transaction hoặc cơ chế khóa/fencing có phạm vi toàn cụm.
- Theo dõi độ trễ replication, consistency và lỗi kết nối của Redis/database.

Nếu Redis được triển khai theo mô hình replication hoặc cluster, hãy hiểu chính sách consistency và failover của hạ tầng. Một lần xóa được xác nhận ở primary không nhất thiết đồng nghĩa mọi replica hoặc cache phụ đã quan sát thay đổi tại cùng một thời điểm. Tương tự, transaction JDBC chỉ bảo vệ các thao tác nằm trong transaction và cùng nguồn dữ liệu; nó không tự khóa mọi request đang chạy ở instance khác.

Không nên dùng `synchronized` trên controller hoặc service singleton để bảo vệ phiên trong hệ thống nhiều instance. Khóa đó chỉ có tác dụng trong một JVM. Nếu cần khóa phân tán, phải có thời hạn, cơ chế gia hạn phù hợp, xử lý chủ sở hữu khóa bị chết và fencing để tránh chủ khóa cũ tiếp tục ghi sau khi khóa đã hết hạn.

## 12. Quan sát và chẩn đoán

Nên theo dõi các chỉ số:

- Số phiên tạo mới, hết hạn, logout và thu hồi.
- Số request bị từ chối vì session không còn hiệu lực.
- Số lần truy cập session gặp `IllegalStateException`.
- Số lần ghi session thất bại hoặc phát hiện xung đột cập nhật.
- Thời gian request và số request còn chạy khi session hết hạn.
- Độ trễ đọc, ghi và xóa session tại Redis/JDBC.

Khi điều tra, ghi correlation ID của request, instance xử lý, loại sự kiện và một định danh session đã được băm. Tránh ghi session ID nguyên vẹn, cookie, access token hoặc dữ liệu thuộc tính. Cần phân biệt rõ sự kiện `expired`, `deleted`, `logout` và `request rejected` để tránh hiểu nhầm rằng mọi session bị xóa đều do timeout.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Logout trả thành công nhưng một request đang chạy vẫn cập nhật dữ liệu | Request đã xác thực trước khi phiên bị thu hồi | Kiểm tra lại quyền ở ranh giới nghiệp vụ; dùng transaction/fencing nếu cần bảo đảm mạnh |
| Session xuất hiện lại sau khi logout | Request cũ ghi snapshot session sau thao tác xóa | Kiểm thử race với repository thực tế; ngăn stale write hoặc dùng trạng thái thu hồi độc lập |
| Request dài báo lỗi khi truy cập session | Phiên bị invalidated hoặc dữ liệu session không còn hợp lệ | Không tiếp tục dùng session; kết thúc request hoặc xử lý nhánh yêu cầu xác thực lại |
| Listener hết hạn chạy nhưng request vẫn hoàn tất | Sự kiện vòng đời không phải cơ chế hủy request | Dùng kiểm tra đồng bộ tại điểm bảo vệ và cancellation riêng nếu cần |
| Instance A nhận logout chậm hơn instance B | Cache, replication hoặc nguồn trạng thái chưa nhất quán | Xác định mức consistency, giảm cache stale và kiểm tra nguồn revocation dùng chung |
| Job nền lỗi sau khi request kết thúc | Job giữ tham chiếu đến request/session hoặc giả định session còn sống | Truyền job context tối thiểu và kiểm tra quyền theo chính sách job |

## 14. Checklist thiết kế

- [ ] Đã xác định request đang chạy có được phép hoàn tất sau logout hay không.
- [ ] Đã phân biệt timeout do inactivity và thu hồi chủ động.
- [ ] Không giả định xóa session tự động dừng request hoặc job đang chạy.
- [ ] Không truy cập đối tượng `HttpSession` sau khi gọi `invalidate()`.
- [ ] Các thao tác nhạy cảm kiểm tra lại trạng thái tài khoản/quyền ở ranh giới nghiệp vụ.
- [ ] Nếu yêu cầu thu hồi thắng mọi cập nhật, có transaction, khóa hoặc fencing phù hợp.
- [ ] Không dùng listener bất đồng bộ làm cơ chế bảo vệ duy nhất.
- [ ] Request async/job nền không giữ `HttpSession` hoặc request object.
- [ ] Integration test bao gồm race giữa đọc, ghi, logout và hết hạn.
- [ ] Metric và log phân biệt được expired, deleted, logout và request bị từ chối.

Trong Spring Session, hết hạn hoặc thu hồi phiên ngăn các request sau sử dụng phiên cũ sau khi repository đã xử lý thay đổi. Request đã bắt đầu có thể vẫn tiếp tục với trạng thái đã đọc, và thao tác lưu cuối request có thể cạnh tranh với việc xóa phiên. Hãy xác định rõ chính sách cho request đang chạy, kiểm tra lại quyền trước thao tác nhạy cảm và kiểm thử race condition trên repository dùng chung để bảo vệ dữ liệu khi ứng dụng vận hành nhiều instance.
