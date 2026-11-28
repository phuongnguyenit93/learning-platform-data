# Xóa thuộc tính và đồng bộ thay đổi xuống kho

Session thường chứa nhiều thuộc tính có vòng đời khác nhau: ngữ cảnh người dùng, lựa chọn giao diện, mã giỏ hàng hoặc dữ liệu tạm của một quy trình. Khi một thuộc tính không còn cần thiết, ứng dụng phải xóa nó khỏi session và bảo đảm thay đổi được ghi xuống repository. Nếu chỉ thay đổi một object trong bộ nhớ mà repository không nhận biết, dữ liệu cũ có thể xuất hiện lại ở request sau hoặc trên instance khác.

Spring Session cho phép ứng dụng Servlet tiếp tục thao tác qua `HttpSession`, trong khi dữ liệu được lưu trong kho chia sẻ như Redis hoặc JDBC. Việc xóa thuộc tính, theo dõi thay đổi và thời điểm flush được phối hợp bởi `SessionRepositoryFilter`, session implementation và repository. Nếu ứng dụng gọi trực tiếp `SessionRepository`, chính mã ứng dụng chịu trách nhiệm gọi `save` sau khi sửa session.

Chương này thuộc phần chính sách ghi của `SPRING_SESSION`: quản lý session ứng dụng Spring độc lập với một máy chủ bằng kho dữ liệu chia sẻ. Trọng tâm là xóa đúng một thuộc tính, hiểu cách Spring Session nhận biết thay đổi, phân biệt `SaveMode` với `FlushMode`, và xử lý các tình huống cập nhật đồng thời.

## 1. Xóa một thuộc tính khỏi HttpSession

Servlet API cung cấp `removeAttribute(name)` để xóa một thuộc tính khỏi session. Sau thao tác này, `getAttribute(name)` trả về `null` và tên thuộc tính không còn nằm trong danh sách thuộc tính của session.

```java
@PostMapping("/checkout/clear-draft")
public void clearCheckoutDraft(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        return;
    }

    session.removeAttribute("app.checkout.draft");
}
```

`getSession(false)` tránh tạo một session mới chỉ để xóa dữ liệu. Nếu không có session hiện tại, endpoint kết thúc mà không tạo cookie hoặc bản ghi session mới.

Theo hợp đồng Servlet, gọi `setAttribute(name, null)` cũng có tác dụng loại bỏ thuộc tính. Dù vậy, `removeAttribute` diễn đạt rõ ý định hơn và dễ đọc khi bảo trì:

```java
session.removeAttribute("app.ui.locale");

// Tương đương về hiệu quả với Servlet HttpSession:
session.setAttribute("app.ui.locale", null);
```

Xóa một thuộc tính khác với `session.invalidate()`. `removeAttribute` chỉ xóa dữ liệu được chỉ định; các thuộc tính khác và session ID vẫn tồn tại. `invalidate()` kết thúc toàn bộ session, làm mọi thuộc tính không còn khả dụng và yêu cầu người dùng tạo hoặc nhận một session mới ở request sau nếu cần.

| Thao tác | Phạm vi ảnh hưởng | Khi nên dùng |
|---|---|---|
| `removeAttribute(name)` | Một thuộc tính | Xóa bản nháp, lựa chọn giao diện hoặc dữ liệu tạm |
| `setAttribute(name, null)` | Một thuộc tính, tương đương xóa theo Servlet API | Có thể gặp trong code tổng quát; ưu tiên `removeAttribute` để rõ nghĩa |
| `invalidate()` | Toàn bộ session | Logout hoặc kết thúc phiên theo chính sách |

## 2. Xóa thuộc tính có được lưu xuống Redis/JDBC không?

Khi request đi qua `SessionRepositoryFilter`, `HttpSession` được cung cấp bởi wrapper của Spring Session. Các thao tác `setAttribute` và `removeAttribute` được ghi nhận trong trạng thái session mà repository quản lý. Ở thời điểm lưu, repository chuyển các thay đổi đó xuống kho dữ liệu.

Với Redis, thuộc tính session thường được biểu diễn trong dữ liệu hash của session; khi xóa thuộc tính, repository cần loại bỏ trường tương ứng hoặc ghi thay đổi xóa theo cách implementation quy định. Với JDBC, repository lưu thuộc tính theo schema của Spring Session và xử lý việc xóa bản ghi thuộc tính tương ứng. Ứng dụng không nên tự thao tác `HDEL` hay `DELETE` trực tiếp trên cấu trúc nội bộ vì có thể bỏ qua metadata, index và quy tắc tương thích của repository.

Đối với mã dùng `HttpSession`, không cần gọi `save()` thủ công sau mỗi `removeAttribute`. Spring Session filter quản lý việc commit session trong vòng đời request/response. Với mã dùng trực tiếp `SessionRepository`, ứng dụng phải gọi `save(session)` để ghi trạng thái đã thay đổi.

## 3. Phân biệt hai luồng sử dụng session

### 3.1. Qua HttpSession và SessionRepositoryFilter

Đây là cách thông dụng trong Spring MVC. Controller nhận `HttpServletRequest`, lấy `HttpSession`, rồi thêm hoặc xóa thuộc tính. Filter đã bọc request và response, do đó những thay đổi được ghi theo chính sách flush/save của session repository.

```java
@PostMapping("/profile/reset-preferences")
public void resetPreferences(HttpServletRequest request) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        return;
    }

    session.removeAttribute("app.profile.theme");
    session.removeAttribute("app.profile.time-zone");
}
```

Không giữ `HttpSession` trong field của singleton service để sử dụng ở request khác. Hãy lấy session từ request hiện tại; session là trạng thái dùng chung có thể được truy cập bởi nhiều request và nhiều instance.

### 3.2. Qua SessionRepository trực tiếp

Một số service hoặc tác vụ nền cần thao tác session theo ID mà không có `HttpServletRequest`. Khi đó có thể inject `SessionRepository<S>` và gọi API của repository. Với cách này, cần đọc session, thay đổi nó và gọi `save` tường minh.

```java
import org.springframework.session.MapSession;
import org.springframework.session.SessionRepository;
import org.springframework.stereotype.Service;

@Service
public class SessionMaintenanceService {

    private final SessionRepository<MapSession> repository;

    public SessionMaintenanceService(
            SessionRepository<MapSession> repository) {
        this.repository = repository;
    }

    public boolean removeDraft(String sessionId) {
        MapSession session = repository.findById(sessionId);
        if (session == null) {
            return false;
        }

        session.removeAttribute("app.checkout.draft");
        repository.save(session);
        return true;
    }
}
```

Ví dụ dùng `MapSession` để minh họa generic type; kiểu session thực tế phải khớp với repository mà ứng dụng cấu hình. `findById` của `SessionRepository` trả về `null` khi không tìm thấy session. Khi thao tác trực tiếp, nếu bỏ qua `repository.save(session)`, thay đổi trong object đang giữ không được bảo đảm ghi xuống kho.

Nếu chỉ muốn kết thúc toàn bộ session, dùng `repository.deleteById(sessionId)` thay vì xóa từng thuộc tính. Với session trong request hiện tại, `invalidate()` thường phù hợp hơn vì nó tham gia đúng vòng đời Servlet và logout.

## 4. SaveMode: chọn thuộc tính nào được ghi

`SaveMode` quyết định thuộc tính nào của session được đưa vào thao tác lưu. Nó giải quyết câu hỏi **“những thuộc tính nào cần được lưu?”** chứ không quyết định thời điểm ghi xuống Redis/JDBC.

Các chế độ thường gặp:

| SaveMode | Hành vi | Hệ quả |
|---|---|---|
| `ON_SET_ATTRIBUTE` | Lưu những thuộc tính được đặt hoặc xóa qua `Session.setAttribute` / `Session.removeAttribute` | Hiệu quả cho các thay đổi có thao tác set/remove rõ ràng |
| `ON_GET_ATTRIBUTE` | Lưu các thuộc tính đã được đọc hoặc ghi | Có thể phát hiện object được lấy ra rồi thay đổi trong request, nhưng cần hiểu chi phí lưu tăng thêm |
| `ALWAYS` | Lưu tất cả thuộc tính của session khi session được lưu | Dễ nắm bắt thay đổi object mutable, nhưng có thể ghi nhiều dữ liệu hơn cần thiết |

`ON_SET_ATTRIBUTE` là lựa chọn phù hợp khi ứng dụng thay thế giá trị thuộc tính bằng `setAttribute` và xóa bằng `removeAttribute`. Đây cũng là chế độ thường được chọn mặc định trong các cấu hình Spring Session hiện đại, nhưng hãy kiểm tra phiên bản và cấu hình thực tế của dự án.

Ví dụ bật rõ ràng chế độ lưu theo thao tác set/remove:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.SaveMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(saveMode = SaveMode.ON_SET_ATTRIBUTE)
public class SessionWriteConfiguration {
}
```

Khi dùng `ON_SET_ATTRIBUTE`, hãy gọi `setAttribute` sau khi tạo giá trị mới và gọi `removeAttribute` khi muốn xóa. Đừng giả định repository sẽ tự phát hiện mọi thay đổi bên trong object Java mà ứng dụng đang giữ tham chiếu.

## 5. Thay đổi object mutable bên trong thuộc tính

Một lỗi thường gặp là lưu collection vào session, lấy collection ra rồi sửa trực tiếp:

```java
@SuppressWarnings("unchecked")
List<String> recentItems =
        (List<String>) session.getAttribute("app.recent-items");

if (recentItems != null) {
    recentItems.add("item-42");
}
```

Với `SaveMode.ON_SET_ATTRIBUTE`, thao tác `add` không gọi `setAttribute` hoặc `removeAttribute`. Spring Session có thể không đánh dấu thuộc tính này là đã thay đổi, vì vậy cập nhật có thể không được ghi xuống kho.

Cách rõ ràng hơn là tạo giá trị mới rồi đặt lại thuộc tính:

```java
@SuppressWarnings("unchecked")
List<String> current =
        (List<String>) session.getAttribute("app.recent-items");

List<String> updated = current == null
        ? new ArrayList<>()
        : new ArrayList<>(current);
updated.add("item-42");

session.setAttribute("app.recent-items", updated);
```

Thay thế giá trị giúp Spring Session nhận biết thay đổi theo `ON_SET_ATTRIBUTE`. Có thể dùng DTO bất biến hoặc tạo bản sao collection để tránh việc nhiều request cùng sửa một object mutable.

`ON_GET_ATTRIBUTE` có thể hữu ích với mô hình mà ứng dụng đọc rồi sửa object mutable, vì thuộc tính đã đọc được đưa vào tập cần lưu. Tuy nhiên, nó làm tăng lượng thuộc tính được ghi và không giải quyết xung đột khi nhiều request cùng sửa một giá trị. `ALWAYS` ghi mọi thuộc tính ở mỗi lần lưu session, nhưng cũng làm tăng serialization và I/O. Hãy chọn mode dựa trên cách code thay đổi dữ liệu, kích thước session và kết quả đo đạc.

## 6. FlushMode: thời điểm thay đổi được ghi xuống kho

`FlushMode` trả lời câu hỏi **“khi nào thay đổi session được ghi?”**. Nó độc lập với `SaveMode`: một cấu hình chọn tập thuộc tính cần lưu, cấu hình còn lại chọn thời điểm flush.

| FlushMode | Hành vi | Khi cân nhắc |
|---|---|---|
| `ON_SAVE` | Ghi session khi `SessionRepository.save(session)` được gọi | Phù hợp với mô hình request, gom các thay đổi rồi lưu ở ranh giới commit |
| `IMMEDIATE` | Ghi thay đổi xuống repository sớm nhất có thể khi chúng xảy ra | Cân nhắc khi cần thay đổi được nhìn thấy sớm hơn, chấp nhận nhiều thao tác I/O hơn |

Với `SessionRepositoryFilter`, Spring Session quản lý thời điểm gọi save/commit trong vòng đời request. `ON_SAVE` thường giúp gom thay đổi của một request vào thao tác lưu cuối request hoặc lúc response được commit theo tích hợp. `IMMEDIATE` có thể ghi các delta sớm hơn, nhưng không biến nhiều thao tác thuộc tính thành một transaction nghiệp vụ nguyên tử.

Ví dụ cấu hình cả hai chính sách:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(
        flushMode = FlushMode.ON_SAVE,
        saveMode = SaveMode.ON_SET_ATTRIBUTE
)
public class SessionWriteConfiguration {
}
```

Đây là cấu hình minh họa cho Spring Session Redis Servlet. Tên thuộc tính annotation và package cần khớp với phiên bản dependency của dự án. Trong Spring Boot, có thể cấu hình các giá trị tương ứng bằng properties nếu phiên bản Boot hỗ trợ, ví dụ `spring.session.redis.flush-mode` và `spring.session.redis.save-mode`.

## 7. Kết hợp SaveMode và FlushMode

Hai chính sách phối hợp với nhau. Ví dụ:

| SaveMode | FlushMode | Ý nghĩa |
|---|---|---|
| `ON_SET_ATTRIBUTE` | `ON_SAVE` | Chỉ lưu thuộc tính được set/remove, tại thời điểm repository được yêu cầu save |
| `ON_SET_ATTRIBUTE` | `IMMEDIATE` | Chỉ lưu delta set/remove, nhưng ghi sớm khi thay đổi phát sinh |
| `ON_GET_ATTRIBUTE` | `ON_SAVE` | Lưu thuộc tính đã đọc/ghi khi request commit session |
| `ALWAYS` | `ON_SAVE` | Ghi toàn bộ thuộc tính tại thời điểm save |
| `ALWAYS` | `IMMEDIATE` | Ghi sớm theo chính sách flush và bao gồm toàn bộ thuộc tính theo SaveMode; có thể tạo nhiều I/O hơn đáng kể |

Không nên chọn `ALWAYS` và `IMMEDIATE` chỉ để “chắc chắn dữ liệu được lưu”. Hai mode này có thể làm tăng số lần serialization và ghi Redis, nhất là khi session có nhiều thuộc tính hoặc request cập nhật nhiều lần. Đo latency, số lệnh Redis và kích thước payload trước khi thay đổi cấu hình.

## 8. Xóa thuộc tính và dữ liệu đã được đọc

Khi dùng `ON_SET_ATTRIBUTE`, thao tác xóa phải được biểu diễn bằng `removeAttribute` hoặc `setAttribute(name, null)` để session implementation ghi nhận delta xóa. Không sửa trực tiếp cấu trúc dữ liệu nội bộ hoặc chỉ xóa một giá trị trong collection rồi mong repository hiểu đó là xóa cả session attribute.

Ví dụ xóa một thuộc tính và giữ các thuộc tính khác:

```java
session.removeAttribute("app.checkout.draft");
session.setAttribute("app.ui.locale", "vi-VN");
```

Sau khi request được commit, repository lưu việc xóa `app.checkout.draft` và cập nhật `app.ui.locale`. Session ID vẫn có thể giữ nguyên; cookie không nhất thiết bị xóa vì session vẫn còn.

Nếu xóa thuộc tính principal hoặc `SecurityContext`, cần hiểu tác động tới xác thực. Xóa một thuộc tính tùy chỉnh không tự động đăng xuất Spring Security nếu `SecurityContext` vẫn còn. Ngược lại, xóa `SPRING_SECURITY_CONTEXT` trực tiếp không thay thế toàn bộ logout flow. Dùng logout handler của Spring Security để xóa context, invalidate session và xóa cookie theo chính sách.

## 9. Thay đổi trong session không phải transaction nghiệp vụ

Việc Spring Session lưu một hoặc nhiều thuộc tính không bảo đảm toàn bộ thao tác nghiệp vụ có tính nguyên tử. Ví dụ, request có thể xóa `checkoutDraft` sau khi tạo đơn hàng. Nếu lưu đơn hàng thành công nhưng Redis save thất bại, hoặc ngược lại, trạng thái đơn hàng và session có thể không đồng bộ.

Không dùng session làm nguồn dữ liệu chính cho giao dịch. Hãy lưu đơn hàng trong cơ sở dữ liệu nghiệp vụ bằng transaction; session chỉ giữ mã tham chiếu hoặc trạng thái giao diện tạm. Khi hoàn tất giao dịch, thiết kế thứ tự và khả năng retry rõ ràng:

1. Xác thực request và kiểm tra bản nháp.
2. Tạo đơn hàng bằng transaction ở kho nghiệp vụ, có idempotency key nếu request có thể retry.
3. Khi đã có kết quả bền vững, xóa thuộc tính bản nháp khỏi session.
4. Nếu thao tác lưu session lỗi, request tiếp theo cần kiểm tra trạng thái đơn hàng trong kho chính và không tạo đơn hàng trùng.

Với thao tác nhạy cảm, không suy luận thành công chỉ vì thuộc tính session đã bị xóa. Session là trạng thái phụ trợ; trạng thái nghiệp vụ phải được quyết định từ kho dữ liệu chính.

## 10. Nhiều request cùng sửa hoặc xóa thuộc tính

Người dùng có thể mở nhiều tab hoặc gửi request song song. Hai request có thể cùng tải một phiên bản session, sau đó một request xóa thuộc tính trong khi request còn lại cập nhật nó. Kết quả cuối phụ thuộc thứ tự ghi và semantics repository.

Ví dụ:

1. Request A đọc `app.checkout.draft`.
2. Request B đọc cùng thuộc tính.
3. A gọi `removeAttribute` rồi lưu session.
4. B sửa bản nháp cũ và gọi `setAttribute` sau đó.
5. Giá trị B ghi có thể xuất hiện trở lại nếu lần lưu của B đến sau.

Đây là race condition; `FlushMode.IMMEDIATE` không tự giải quyết nó. Việc ghi sớm hơn không đồng nghĩa với khóa độc quyền hay compare-and-set trên toàn bộ thao tác đọc–sửa–ghi.

Với dữ liệu không quan trọng, có thể chấp nhận chính sách cập nhật cuối cùng thắng nếu đã được xác định rõ. Với giỏ hàng, hạn mức, quyền hoặc trạng thái thanh toán, hãy dùng kho nghiệp vụ có transaction, optimistic locking/version column hoặc lệnh nguyên tử. Nếu cần khóa phân tán theo session, phải thiết kế lease/timeout và xử lý trường hợp client chết; không tự giữ lock vô thời hạn.

## 11. Kiểm thử việc xóa và đồng bộ session

Kiểm thử cần xác minh không chỉ response của endpoint mà cả trạng thái sau khi đọc lại qua repository hoặc instance khác.

| Trường hợp | Cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| Xóa một thuộc tính qua HttpSession | Tạo session, gọi `removeAttribute`, gửi request tiếp theo | Thuộc tính không còn; các thuộc tính khác vẫn tồn tại |
| `setAttribute(name, null)` | Gán null rồi đọc lại | Thuộc tính bị loại bỏ theo Servlet API |
| Invalidate session | Gọi `invalidate()` rồi gửi lại cookie cũ | Session không còn hợp lệ |
| Direct repository | `findById`, remove attribute, `save`, rồi tìm lại | Thay đổi đã được ghi xuống repository |
| Bỏ qua save trực tiếp | Sửa session object nhưng không gọi `save` | Không giả định thay đổi được lưu |
| `ON_SET_ATTRIBUTE` | Sửa collection tại chỗ mà không gọi set/remove | Xác nhận thay đổi có thể không được lưu; sau đó kiểm thử set lại giá trị |
| `ON_GET_ATTRIBUTE` | Đọc thuộc tính rồi sửa object mutable | Xác minh thuộc tính được lưu theo mode và repository thực tế |
| `ALWAYS` | Sửa thuộc tính và commit session | Tất cả thuộc tính được lưu theo chính sách |
| `ON_SAVE` và `IMMEDIATE` | Theo dõi thời điểm repository nhận thao tác save | Xác minh thời điểm ghi đúng cấu hình |
| Hai request đồng thời | Một request xóa, request khác cập nhật cùng thuộc tính | Hành vi xung đột được xác định và kiểm soát ở tầng phù hợp |
| Nhiều instance | Xóa thuộc tính qua A rồi đọc session qua B | B nhìn thấy trạng thái đã commit |

`MockHttpSession` hữu ích cho unit test controller nhưng không kiểm chứng Redis/JDBC persistence. Dùng integration test với repository thật hoặc Testcontainers để kiểm tra read-after-write, serialization, TTL và khả năng đọc từ instance khác. Với test concurrency, tạo hai request độc lập cùng dùng một session ID và xác minh chính sách xung đột.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
|---|---|---|
| Thuộc tính đã xóa xuất hiện lại | Xóa object trong bộ nhớ nhưng không gọi `removeAttribute`, hoặc một request khác ghi giá trị cũ | Dùng API session và kiểm tra race condition |
| Thay đổi collection không được lưu | `ON_SET_ATTRIBUTE` không nhận biết mutation tại chỗ | Tạo bản sao và gọi `setAttribute` lại |
| Direct repository sửa nhưng Redis không đổi | Quên gọi `repository.save(session)` | Gọi save và xử lý publisher/kết quả nếu repository reactive |
| Session bị xóa toàn bộ khi chỉ muốn xóa một giá trị | Dùng `invalidate()` thay cho `removeAttribute` | Chọn đúng phạm vi thao tác |
| Ghi Redis tăng đột biến | Chọn `ALWAYS` hoặc `IMMEDIATE` không cần thiết | Đo tải và chọn SaveMode/FlushMode phù hợp |
| Thuộc tính principal không còn index đúng | Xóa hoặc thay đổi principal attribute mà không đồng bộ quy tắc index | Dùng resolver nhất quán và kiểm thử index update/delete |
| Logout nhưng context còn hiệu lực | Chỉ xóa một thuộc tính tùy chỉnh hoặc cookie phía client | Dùng logout flow và invalidate session server-side |
| Hai request ghi đè nhau | Không có kiểm soát concurrency ở session attribute | Dùng versioning/transaction ở kho nghiệp vụ |
| Request báo thành công dù save thất bại | Lỗi repository bị nuốt hoặc thao tác save không được nối vào luồng xử lý | Truyền lỗi và trả phản hồi phù hợp; không fire-and-forget |

## 13. Quy trình chọn chính sách ghi

Khi thiết kế thao tác xóa/cập nhật session, hãy thực hiện theo thứ tự:

1. Xác định dữ liệu nào chỉ là trạng thái tạm và dữ liệu nào thuộc kho nghiệp vụ chính.
2. Dùng `removeAttribute` để xóa một thuộc tính, `invalidate` để kết thúc toàn bộ session.
3. Nếu dùng `HttpSession`, để `SessionRepositoryFilter` quản lý việc commit; nếu gọi repository trực tiếp, gọi `save` sau khi sửa.
4. Chọn `SaveMode.ON_SET_ATTRIBUTE` nếu code dùng set/remove tường minh; cân nhắc `ON_GET_ATTRIBUTE` hoặc `ALWAYS` khi mô hình object mutable yêu cầu và đã đánh giá chi phí.
5. Chọn `FlushMode.ON_SAVE` để gom thay đổi theo ranh giới save thông thường; chỉ dùng `IMMEDIATE` khi cần ghi sớm và đã đo tác động I/O.
6. Thay thế object mutable và gọi `setAttribute` để thay đổi được nhận biết rõ ràng.
7. Xác định cách xử lý hai request đồng thời sửa cùng thuộc tính; dùng transaction/versioning cho dữ liệu nghiệp vụ quan trọng.
8. Kiểm thử read-after-write, xóa thuộc tính, invalidate, lỗi repository và chia sẻ giữa nhiều instance.

Xóa thuộc tính chỉ thực sự hoàn tất khi thay đổi được ghi theo đúng chính sách repository. `SaveMode` quyết định thuộc tính nào được lưu; `FlushMode` quyết định thời điểm ghi; `SessionRepositoryFilter` quản lý commit cho luồng `HttpSession`, còn mã dùng repository trực tiếp phải gọi `save`. Kết hợp đúng ba phần này giúp tránh dữ liệu cũ xuất hiện lại và giữ trạng thái session nhất quán giữa các instance Spring.
