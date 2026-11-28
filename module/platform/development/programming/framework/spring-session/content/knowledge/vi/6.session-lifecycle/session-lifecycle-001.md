# Tạo phiên mới, sử dụng phiên hiện có và các điều kiện bắt đầu phiên

HTTP là giao thức không lưu trạng thái giữa các yêu cầu. Khi một ứng dụng Spring cần nhớ người dùng đã đăng nhập, giỏ hàng hoặc một quy trình đang thực hiện, ứng dụng có thể dùng HTTP session. Session cung cấp một vùng dữ liệu phía máy chủ được nhận diện bằng một session ID; trình duyệt gửi ID đó trong các yêu cầu tiếp theo để máy chủ tìm lại dữ liệu.

Spring Session thay thế cách servlet container tự giữ session trong bộ nhớ bằng một repository có thể lưu ở Redis hoặc JDBC. API Servlet mà ứng dụng sử dụng vẫn quen thuộc: HttpServletRequest.getSession(), HttpSession.getAttribute(), setAttribute() và invalidate(). Vì vậy, cần hiểu rõ thời điểm session được tạo, cách một yêu cầu tìm session đang tồn tại và điều gì xảy ra khi ID không còn hợp lệ.

## 1. Session bắt đầu khi nào?

Một session không nhất thiết được tạo ngay khi người dùng mở trang chủ. Session chỉ cần được tạo khi ứng dụng hoặc một thành phần trong chuỗi xử lý yêu cầu cần lưu trạng thái cho những yêu cầu sau. Ví dụ:

- Người dùng thêm sản phẩm vào giỏ hàng và ứng dụng cần giữ mã giỏ hàng.
- Người dùng đăng nhập và ứng dụng cần liên kết các yêu cầu tiếp theo với danh tính đã xác thực.
- Ứng dụng bắt đầu một quy trình nhiều bước, cần lưu dữ liệu tạm thời giữa các bước.
- Một tính năng bảo mật hoặc framework cần lưu thông tin trạng thái phía máy chủ.

Ngược lại, một yêu cầu đọc nội dung công khai, không cần trạng thái người dùng, có thể được xử lý mà không tạo session. Điều này giúp giảm số session phải lưu, giảm cookie không cần thiết và giảm tải cho Redis hoặc database.

Với Servlet API, lời gọi request.getSession() hoặc request.getSession(true) yêu cầu lấy session hiện tại; nếu chưa có session hợp lệ thì tạo session mới. Lời gọi request.getSession(false) chỉ tìm session hiện có và trả về null nếu không tìm thấy. Đây là khác biệt quan trọng nhất khi viết controller, filter hoặc interceptor.

| Lời gọi | Có tìm session hiện có? | Có tạo session mới nếu không có? |
| --- | --- | --- |
| request.getSession() | Có | Có |
| request.getSession(true) | Có | Có |
| request.getSession(false) | Có | Không |

Nếu chỉ muốn kiểm tra người dùng đã có session hay chưa, hãy dùng getSession(false). Dùng getSession() trong mọi yêu cầu chỉ để kiểm tra trạng thái có thể vô tình tạo một session cho cả người dùng chưa đăng nhập.

## 2. Spring Session tham gia vào vòng đời như thế nào?

Trong ứng dụng Servlet tích hợp Spring Session, SessionRepositoryFilter đặt một lớp bọc quanh request và response. Lớp lọc này cung cấp một HttpSession được quản lý bởi Spring Session. Khi ứng dụng yêu cầu session, filter làm việc với SessionRepository đã cấu hình để tìm hoặc tạo session.

Repository chịu trách nhiệm lưu trữ session. Với Redis, dữ liệu được lưu trong Redis; với JDBC, dữ liệu được lưu trong các bảng session của cơ sở dữ liệu. Các instance của ứng dụng có thể dùng cùng repository để truy cập cùng một session.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Trình duyệt gửi HTTP request"] --> B["Cookie mang session ID (nếu có)"]
    B --> C["SessionRepositoryFilter"]
    C --> D{"Repository tìm thấy session hợp lệ?"}
    D -->|Có| E["Dùng session hiện có"]
    D -->|Không| F{"Ứng dụng yêu cầu tạo session?"}
    F -->|Không| G["Tiếp tục request không có session"]
    F -->|Có| H["Tạo session mới"]
    E --> I["Controller / Service đọc hoặc cập nhật"]
    H --> I
    G --> J["Tạo response"]
    I --> J
    J --> K["Lưu thay đổi và gửi cookie khi cần"]
~~~

Khi request kết thúc hoặc response được commit, Spring Session lưu thay đổi theo repository và chế độ flush đã cấu hình. Nếu session mới được tạo, trình duyệt cần nhận cookie chứa ID mới để nhận diện session trong các request sau. Cookie thường được gửi trong header Set-Cookie; tên cookie phụ thuộc cấu hình CookieSerializer và mặc định của Spring Session.

Việc dùng repository chung không làm cho session tự xuất hiện. Ứng dụng vẫn phải yêu cầu tạo session hoặc sử dụng một tính năng có nhu cầu tạo session. Repository chỉ cung cấp nơi lưu và truy xuất trạng thái đó.

## 3. Tạo session mới một cách có chủ đích

Ví dụ sau minh họa việc tạo session khi người dùng thực hiện hành động thêm sản phẩm vào giỏ hàng. Một yêu cầu đọc giỏ hàng chỉ kiểm tra session hiện có; yêu cầu ghi mới mới tạo session nếu chưa có.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CartController {

    @GetMapping("/cart")
    Map<String, Object> readCart(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            return Map.of("hasSession", false, "items", 0);
        }

        Integer items = (Integer) session.getAttribute("cartItems");
        return Map.of(
            "hasSession", true,
            "items", items == null ? 0 : items
        );
    }

    @PostMapping("/cart/items")
    Map<String, Integer> addItem(HttpServletRequest request) {
        HttpSession session = request.getSession();
        Integer items = (Integer) session.getAttribute("cartItems");
        int nextValue = (items == null ? 0 : items) + 1;
        session.setAttribute("cartItems", nextValue);
        return Map.of("items", nextValue);
    }
}
~~~

Khi người dùng gọi GET /cart lần đầu mà chưa có session, controller trả về giỏ hàng rỗng và không yêu cầu tạo session. Khi người dùng gọi POST /cart/items, getSession() tạo session nếu cần, sau đó thuộc tính cartItems được lưu. Trình duyệt nhận cookie trong response và gửi cookie đó trong request tiếp theo.

Đây là ví dụ đơn giản để minh họa vòng đời. Trong ứng dụng thật, số lượng sản phẩm, tồn kho và đơn hàng thường phải được lưu trong cơ sở dữ liệu nghiệp vụ. Session nên giữ mã tham chiếu hoặc trạng thái tạm thời nhỏ, không nên trở thành nơi lưu trữ duy nhất của dữ liệu giao dịch.

## 4. Sử dụng session hiện có

Ở một request tiếp theo, trình duyệt gửi cookie session ID. Spring Session dùng ID đó để tìm session trong repository. Nếu session còn tồn tại và chưa hết hạn, ứng dụng có thể đọc hoặc cập nhật thuộc tính:

~~~java
HttpSession session = request.getSession(false);

if (session != null) {
    Object userId = session.getAttribute("userId");
    Object cartId = session.getAttribute("cartId");
    // Sử dụng các giá trị hiện có theo nghiệp vụ.
}
~~~

Một session có thể chứa nhiều thuộc tính. Dùng tên thuộc tính ổn định và kiểu dữ liệu dễ tuần tự hóa. Không lưu đối tượng quá lớn hoặc đối tượng phụ thuộc vào trạng thái nội bộ của một instance, vì session có thể được đọc bởi instance khác hoặc bởi phiên bản ứng dụng khác trong quá trình rolling deployment.

Khi cập nhật thuộc tính, dùng setAttribute(). Khi không còn cần một thuộc tính, dùng removeAttribute(). Khi toàn bộ phiên không còn hợp lệ, dùng invalidate(). Không nên giữ nhiều bản sao dữ liệu nghiệp vụ trong session nếu chúng có thể bị thay đổi ở nơi khác và trở nên lỗi thời.

### Phân biệt session không tồn tại và session không hợp lệ

Servlet API cung cấp một số thông tin để kiểm tra yêu cầu có mang session ID hay không và ID đó có còn hợp lệ hay không:

~~~java
String requestedId = request.getRequestedSessionId();
boolean suppliedId = requestedId != null;
boolean fromCookie = request.isRequestedSessionIdFromCookie();
boolean validId = request.isRequestedSessionIdValid();
HttpSession session = request.getSession(false);
~~~

- getRequestedSessionId() trả về ID mà client gửi trong request, nếu có.
- isRequestedSessionIdFromCookie() cho biết ID được lấy từ cookie.
- isRequestedSessionIdValid() cho biết ID được gửi lên có được container hoặc lớp quản lý session chấp nhận là hợp lệ hay không.
- getSession(false) trả về session hiện có nếu tìm được; nếu không, trả về null.

Không dùng riêng việc cookie tồn tại để kết luận người dùng đang có session hợp lệ. Cookie có thể chứa ID cũ, ID đã bị xóa, ID đã hết hạn hoặc ID không còn được repository nhận diện.

## 5. Điều gì xảy ra khi session ID không tìm thấy?

Có cookie không đồng nghĩa với việc dữ liệu session vẫn còn trên máy chủ. Repository có thể không tìm thấy ID vì:

- Session đã hết hạn do vượt quá thời gian không hoạt động.
- Người dùng đã đăng xuất và session bị vô hiệu hóa.
- Session bị xóa bởi tác vụ quản trị hoặc chính sách dọn dữ liệu.
- Kho Redis hoặc database đã mất dữ liệu do sự cố hoặc thao tác vận hành.
- Trình duyệt gửi cookie cũ sau khi session ID đã được thay đổi.
- Cookie thuộc môi trường, domain hoặc ứng dụng khác.

Nếu ứng dụng gọi getSession(false), kết quả là null khi không có session hiện hành. Ứng dụng có thể yêu cầu đăng nhập lại, hiển thị trạng thái chưa có giỏ hàng hoặc khởi tạo một luồng nghiệp vụ mới. Nếu ứng dụng gọi getSession(), Servlet API có thể tạo session mới và cấp ID mới.

Không nên tự động tạo session mới cho mọi request mang ID không hợp lệ mà không cân nhắc nghiệp vụ. Ví dụ endpoint yêu cầu người dùng đã đăng nhập cần trả về kết quả chưa xác thực hoặc để Spring Security xử lý, thay vì tạo một session rỗng rồi coi như người dùng đã có trạng thái hợp lệ.

## 6. Cookie và việc nhận diện session

Session ID thường được truyền bằng cookie. Khi tạo session, Spring Session có thể gửi cookie trong response. Trình duyệt lưu cookie và tự gửi lại trong những request phù hợp với domain, path, thời hạn và chính sách SameSite.

Cookie chỉ mang mã nhận diện, không nên chứa toàn bộ dữ liệu người dùng hoặc dữ liệu nghiệp vụ của session. Repository giữ dữ liệu thực tế ở phía máy chủ. Một số cấu hình quan trọng:

- HttpOnly: ngăn JavaScript thông thường đọc cookie.
- Secure: chỉ gửi cookie qua HTTPS.
- SameSite: kiểm soát cookie trong các request cross-site; chọn Lax, Strict hoặc None theo luồng điều hướng và xác thực.
- Path và Domain: xác định phạm vi cookie được gửi.

Ví dụ cấu hình CookieSerializer:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        return serializer;
    }
}
~~~

Chỉ bật Secure khi ứng dụng được truy cập qua HTTPS. Nếu chạy local qua HTTP, cần cấu hình riêng cho môi trường phát triển. Trong production, nên dùng HTTPS và không đưa session ID vào URL. URL rewriting có thể làm ID xuất hiện trong lịch sử trình duyệt, access log, referrer hoặc liên kết được chia sẻ.

## 7. Thời hạn của session và hoạt động truy cập

Session thường có thời hạn không hoạt động (idle timeout). Khi hết khoảng thời gian này mà không có hoạt động làm mới theo chính sách repository, session hết hạn và không còn được xem là session hợp lệ. Spring Boot có thể cấu hình timeout chung:

~~~yaml
spring:
  session:
    timeout: 30m
~~~

Có thể đặt thời hạn cho một session cụ thể bằng Servlet API:

~~~java
HttpSession session = request.getSession();
session.setMaxInactiveInterval(30 * 60);
~~~

setMaxInactiveInterval() nhận số giây. Giá trị âm có ý nghĩa session không hết hạn theo timeout không hoạt động; không nên sử dụng tùy tiện vì có thể giữ dữ liệu phiên vô thời hạn. TTL của repository cần được cấu hình nhất quán với chính sách thời hạn của ứng dụng.

Idle timeout khác với absolute lifetime. Một session có thể tiếp tục tồn tại nếu thường xuyên được sử dụng, dù đã được tạo từ lâu. Nếu nghiệp vụ yêu cầu đăng nhập lại sau một khoảng thời gian tuyệt đối, ứng dụng cần lưu thời điểm xác thực hoặc thời điểm tạo phù hợp và kiểm tra riêng; không nên nhầm idle timeout với giới hạn tuổi tối đa của phiên.

Không phải mọi request đều nhất thiết phải tạo session. Một request có thể chỉ đọc tài nguyên công khai và không truy cập HttpSession. Khi cần biết session đã có mà không tạo mới, dùng getSession(false). Khi cần tạo session, gọi getSession() tại điểm nghiệp vụ cần lưu trạng thái. Việc truy cập session và lưu thuộc tính phải được cân nhắc vì có thể làm mới thời hạn không hoạt động hoặc tạo thao tác đọc/ghi tới repository.

## 8. Session trong luồng đăng nhập và đăng xuất

Đăng nhập thường là một thời điểm quan trọng trong vòng đời session. Sau khi xác thực thành công, ứng dụng hoặc Spring Security liên kết danh tính người dùng với session. Để chống session fixation, ID session cần được thay đổi hoặc session cũ được di chuyển theo chiến lược bảo mật của framework. Không nên tự viết quy trình xác thực rồi giữ nguyên session ID cũ mà không hiểu chính sách session fixation đang áp dụng.

Khi dùng Spring Security, cấu hình quản lý session và bảo vệ session fixation tại security filter chain. Chiến lược mặc định có thể khác theo phiên bản Servlet/Spring Security và cấu hình ứng dụng; hãy kiểm tra hành vi của phiên bản đang dùng. Các request đăng nhập, đăng xuất và yêu cầu xác thực cần được kiểm thử cùng cookie thực tế.

Khi đăng xuất, session phải được vô hiệu hóa ở phía máy chủ. Có thể gọi session.invalidate() trong ứng dụng Servlet hoặc để Spring Security xử lý qua logout flow đã cấu hình. Sau khi vô hiệu hóa, cookie cũ có thể vẫn còn trong trình duyệt cho đến khi được xóa hoặc thay thế, nhưng ID đó không còn đại diện cho session hợp lệ. Xóa cookie ở response giúp trình duyệt ngừng gửi lại ID cũ; tên, path và domain khi xóa phải khớp với cookie đã tạo.

## 9. Những lỗi thường gặp khi tạo và dùng session

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Mỗi request đều có session ID mới | Mã ứng dụng tạo session nhưng cookie không được lưu hoặc gửi lại | Kiểm tra Set-Cookie, domain, path, Secure, SameSite và proxy HTTPS |
| Session được tạo trên trang công khai | Một filter/controller gọi getSession() chỉ để kiểm tra | Dùng getSession(false) khi chỉ đọc hoặc kiểm tra |
| Có cookie nhưng ứng dụng coi như chưa đăng nhập | ID đã hết hạn, bị invalidate hoặc không tìm thấy trong repository | Kiểm tra TTL, kho session, namespace và luồng đăng xuất |
| Một instance thấy session, instance khác không thấy | Các instance không dùng cùng repository hoặc cấu hình không đồng nhất | Kiểm tra endpoint, namespace, database/schema và credential |
| Session mất sau khi đăng nhập | Cấu hình cookie, session fixation hoặc proxy làm thay đổi cookie | Kiểm tra ID trước/sau đăng nhập và chính sách cookie |
| Số lượng session tăng bất thường | Session được tạo trong các request không cần trạng thái | Tìm các lời gọi getSession() trong filter, interceptor và controller |

Một nguyên nhân khó phát hiện là filter hoặc interceptor tạo session trước khi controller chạy. Khi điều tra, hãy kiểm tra toàn bộ chuỗi Servlet filter, cấu hình Spring Security và các tính năng lưu trạng thái. Thứ tự filter cũng quan trọng: SessionRepositoryFilter phải chạy trước thành phần cần dùng HttpSession, để thành phần đó nhận được session do Spring Session quản lý.

## 10. Kiểm thử việc tạo và sử dụng session

Kiểm thử tốt cần phân biệt ba tình huống: request chưa có cookie, request có cookie của session hợp lệ và request có cookie cũ hoặc không hợp lệ.

Ví dụ dùng curl để kiểm tra luồng:

~~~bash
# Request đầu tiên đọc giỏ hàng không tạo session nếu controller dùng getSession(false).
curl -i http://localhost:8080/cart

# Thêm sản phẩm: ứng dụng tạo session và response có thể chứa Set-Cookie.
curl -i -c session.cookie -b session.cookie -X POST http://localhost:8080/cart/items

# Đọc lại với cùng cookie jar để sử dụng session vừa tạo.
curl -i -b session.cookie http://localhost:8080/cart

# Gửi request mà không có cookie để kiểm tra trạng thái client mới.
curl -i http://localhost:8080/cart
~~~

Cookie jar giúp giữ cookie giữa các request. Khi đọc kết quả, kiểm tra header Set-Cookie ở response tạo session và header Cookie ở request kế tiếp. Không chia sẻ file cookie jar vì nó chứa session ID có thể dùng để truy cập phiên.

Nên có kiểm thử tích hợp cho các trường hợp:

1. Request không có cookie và chỉ đọc dữ liệu công khai không tạo session.
2. Request thực hiện hành động cần trạng thái tạo session và trả cookie.
3. Request kế tiếp dùng cookie hợp lệ đọc được thuộc tính đã lưu.
4. Request dùng ID hết hạn hoặc đã invalidate được xử lý như một session không hợp lệ.
5. Đăng xuất vô hiệu hóa session; cookie cũ không thể tiếp tục truy cập dữ liệu đã bảo vệ.
6. Hai instance cùng repository có thể đọc session do instance còn lại tạo.
7. Session hết hạn theo timeout đã cấu hình.

Trong kiểm thử tự động, dùng cookie jar hoặc MockHttpSession tùy loại kiểm thử. MockHttpSession hữu ích cho kiểm thử controller đơn vị, nhưng không chứng minh Redis/JDBC hoặc cookie thật hoạt động giữa nhiều instance. Muốn kiểm chứng Spring Session, cần kiểm thử tích hợp với repository thực hoặc container test phù hợp.

## 11. Nguyên tắc thiết kế

- Chỉ tạo session khi nghiệp vụ cần giữ trạng thái qua nhiều request.
- Dùng getSession(false) để kiểm tra hoặc đọc session tùy chọn mà không tạo mới.
- Tạo session tại điểm bắt đầu của một luồng nghiệp vụ cần lưu trạng thái.
- Chỉ lưu dữ liệu nhỏ, cần thiết và có thể tuần tự hóa ổn định.
- Cấu hình cookie bảo mật và dùng HTTPS trong production.
- Đặt idle timeout phù hợp; nếu cần absolute lifetime, triển khai chính sách riêng.
- Để Spring Security quản lý session trong luồng xác thực và session fixation khi ứng dụng dùng Spring Security.
- Vô hiệu hóa session khi đăng xuất hoặc khi nghiệp vụ yêu cầu kết thúc phiên.
- Kiểm thử cả session mới, session hiện có, session hết hạn và session được chia sẻ giữa các instance.

Tạo session là một quyết định của luồng xử lý, không phải hệ quả bắt buộc của mọi HTTP request. Khi ứng dụng phân biệt rõ việc kiểm tra session hiện có với yêu cầu tạo session mới, vòng đời phiên trở nên dễ dự đoán hơn. Spring Session đảm nhiệm việc ánh xạ ID đến repository và chia sẻ dữ liệu giữa các instance, còn ứng dụng quyết định khi nào cần bắt đầu, sử dụng và kết thúc trạng thái người dùng.
