# request.getSession(), getSession(false) và thời điểm tạo phiên

Trong ứng dụng Servlet, `HttpServletRequest.getSession()` là cách phổ biến để lấy phiên làm việc của request hiện tại. Tuy nhiên, phương thức này có thể tạo một phiên mới nếu request chưa gắn với phiên hợp lệ. Nếu một endpoint chỉ cần đọc trạng thái tùy chọn, việc vô tình tạo phiên có thể làm tăng số phiên trong Redis hoặc JDBC, tạo cookie không cần thiết và khiến ứng dụng khó kiểm soát vòng đời phiên.

Spring Session thay thế cơ chế lưu trữ phiên cục bộ của Servlet container bằng một repository dùng chung như Redis hoặc JDBC. Ứng dụng vẫn có thể dùng API `HttpSession` quen thuộc, nhưng cần hiểu rõ lúc nào request tìm phiên hiện có, lúc nào tạo phiên mới và khi nào phiên được lưu vào repository.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt `getSession()`, `getSession(true)` và `getSession(false)`.
- Chọn cách truy cập phù hợp khi đọc hoặc ghi trạng thái phiên.
- Giải thích thời điểm một phiên được tạo, lưu vào repository và gửi session ID về trình duyệt.
- Nhận biết các thành phần có thể tạo phiên gián tiếp.
- Tránh tạo phiên ngoài ý muốn và kiểm thử hành vi này trong ứng dụng dùng Spring Session.

## 1. Ba cách gọi và ý nghĩa

Servlet API cung cấp hai dạng phương thức:

~~~java
HttpSession getSession();
HttpSession getSession(boolean create);
~~~

`getSession()` tương đương `getSession(true)`. Tham số `create` quyết định có tạo phiên mới nếu request chưa có phiên hợp lệ hay không.

| Cách gọi | Khi request đã có phiên hợp lệ | Khi request chưa có phiên hợp lệ |
|---|---|---|
| `request.getSession()` | Trả về phiên hiện tại | Tạo và trả về phiên mới |
| `request.getSession(true)` | Trả về phiên hiện tại | Tạo và trả về phiên mới |
| `request.getSession(false)` | Trả về phiên hiện tại | Trả về `null`, không tạo phiên |

Ví dụ:

~~~java
HttpSession session = request.getSession();       // Có thể tạo phiên
HttpSession same = request.getSession(true);      // Có thể tạo phiên
HttpSession existing = request.getSession(false); // Không tạo phiên
~~~

Trong code ứng dụng, hãy xem `getSession()` là một thao tác có khả năng ghi trạng thái. Dù đoạn code chỉ định đọc một thuộc tính, nó vẫn có thể tạo phiên nếu chưa có phiên hiện tại. `getSession(false)` phù hợp khi phiên là tùy chọn và code chỉ muốn đọc nếu phiên đã tồn tại.

`getSession(false)` có thể trả về một phiên đã được request wrapper tìm thấy từ repository. Nó không có nghĩa là “không truy cập kho dữ liệu”; nếu request mang session ID hợp lệ, Spring Session có thể phải tìm phiên tương ứng. Điều được bảo đảm là lời gọi này không yêu cầu tạo phiên mới khi không tìm thấy phiên.

## 2. Một request tìm và tạo phiên như thế nào?

Ở mức khái niệm, luồng xử lý trong ứng dụng Servlet dùng Spring Session diễn ra như sau:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant F as SessionRepositoryFilter
    participant A as Controller hoặc Filter
    participant R as Redis hoặc JDBC
    B->>F: HTTP request, có thể kèm session ID
    F->>F: Bọc request/response
    F->>A: Chuyển request đã được bọc
    A->>F: getSession(false) hoặc getSession()
    alt Có session ID hợp lệ
        F->>R: Tìm phiên theo ID khi cần
        R-->>F: Phiên hiện có
        F-->>A: Trả về HttpSession
    else Không có phiên và create=false
        F-->>A: Trả về null
    else Không có phiên và create=true
        F->>F: Tạo session mới trong request
        F-->>A: Trả về HttpSession mới
    end
    A->>F: Ghi thuộc tính hoặc tiếp tục xử lý
    F->>R: Lưu session trước khi response được commit
    F-->>B: Response, có thể kèm session ID cookie
~~~

Sơ đồ thể hiện luồng tổng quát. Chi tiết tải phiên, lưu phiên và phát session ID phụ thuộc repository, cấu hình và `HttpSessionIdResolver`.

Với Spring Session, `SessionRepositoryFilter` bọc request và response để ánh xạ API Servlet sang repository. Filter này cung cấp đối tượng `HttpSession` được Spring Session quản lý. Khi ứng dụng gọi `getSession(false)` hoặc `getSession()`, request wrapper kiểm tra phiên đã gắn với request và có thể tìm phiên theo ID mà resolver nhận được.

Nếu không tìm thấy phiên:

- Với `getSession(false)`, kết quả là `null`.
- Với `getSession()` hoặc `getSession(true)`, request wrapper tạo một phiên mới trong ngữ cảnh request.

Phiên mới có thể tồn tại trong bộ nhớ của request wrapper trước khi được ghi vào Redis hoặc JDBC. Spring Session thường lưu thay đổi khi response được commit; response wrapper có thể thực hiện thao tác lưu trước khi response thực sự được gửi. Vì vậy, thời điểm gọi `getSession()` và thời điểm dữ liệu phiên được ghi bền vững vào repository là hai mốc khác nhau.

## 3. Thời điểm tạo phiên khác thời điểm lưu phiên

Có ba mốc nên phân biệt:

1. **Tạo đối tượng phiên:** xảy ra khi ứng dụng hoặc framework yêu cầu tạo phiên, thường qua `getSession()` hoặc `getSession(true)` khi chưa có phiên hợp lệ.
2. **Lưu phiên vào repository:** Spring Session lưu phiên theo cơ chế commit của request/response và chính sách lưu của repository. Việc lưu có thể được thực hiện trước khi response được commit.
3. **Trình duyệt nhận session ID:** resolver ghi session ID vào response, thường dưới dạng cookie. Trình duyệt chỉ có thể gửi lại ID nếu response thực sự tới được client và cookie được chấp nhận.

Vì vậy, gọi `getSession()` không đồng nghĩa ngay tại dòng lệnh đó đã có một bản ghi bền vững trong Redis hoặc JDBC, và cũng không bảo đảm trình duyệt đã nhận cookie. Nếu request thất bại trước khi response hoàn tất, hoặc response đã commit trước khi ứng dụng tạo phiên, việc lưu và gửi cookie có thể không diễn ra như dự kiến.

Không nên tạo phiên muộn sau khi đã ghi response body hoặc commit response. Hãy xác định nhu cầu phiên trước khi response được flush hoặc commit. Với Spring Session, response wrapper phối hợp lưu phiên trước khi response được commit trong luồng thông thường, nhưng ứng dụng vẫn cần tránh những luồng xử lý tùy chỉnh tạo phiên sau thời điểm response không còn có thể thay đổi header.

### 3.1. Thời điểm tạo phiên và creationTime

Sau khi phiên được tạo, có thể đọc thời điểm tạo qua `session.getCreationTime()`. Giá trị trả về là thời gian Unix epoch tính bằng mili giây. Đây là thời điểm tạo phiên, không phải thời điểm phiên được lưu lần đầu vào kho dữ liệu hay thời điểm cookie đến trình duyệt.

~~~java
HttpSession session = request.getSession();
long createdAtMillis = session.getCreationTime();
Instant createdAt = Instant.ofEpochMilli(createdAtMillis);
~~~

Chỉ gọi đoạn code trên khi nghiệp vụ thực sự cần phiên. Nếu chỉ muốn hiển thị trang công khai và không cần trạng thái phiên, không nên tạo phiên chỉ để ghi nhận thời gian truy cập.

## 4. Dùng getSession(false) khi chỉ đọc phiên tùy chọn

Giả sử trang sản phẩm hiển thị số lượng mặt hàng trong giỏ nếu người dùng đã có giỏ hàng. Người truy cập mới vẫn có thể xem trang mà không cần tạo phiên.

~~~java
@GetMapping("/products/{id}")
public String product(
        @PathVariable long id,
        HttpServletRequest request,
        Model model) {

    Product product = productService.findById(id);
    model.addAttribute("product", product);

    HttpSession session = request.getSession(false);
    if (session != null) {
        Object cart = session.getAttribute("cart");
        model.addAttribute("cart", cart);
    }

    return "products/detail";
}
~~~

Đoạn code không tạo phiên chỉ vì khách truy cập trang chi tiết sản phẩm. Nếu request đã mang một session ID hợp lệ, code có thể đọc thuộc tính của phiên đó. Nếu không có phiên, giao diện vẫn hiển thị phần sản phẩm và bỏ qua phần thông tin giỏ hàng.

Đối với logic dùng chung, có thể tách thao tác đọc tùy chọn:

~~~java
public Optional<Object> findSessionAttribute(
        HttpServletRequest request, String attributeName) {
    HttpSession session = request.getSession(false);
    if (session == null) {
        return Optional.empty();
    }
    return Optional.ofNullable(session.getAttribute(attributeName));
}
~~~

Không dùng `getSession()` trong helper chỉ để đọc thuộc tính. Nếu helper được gọi từ nhiều endpoint, một lời gọi tạo phiên ẩn có thể làm tăng số phiên mà không ai nhận ra ở nơi gọi.

## 5. Dùng getSession() khi nghiệp vụ cần bắt đầu trạng thái phiên

Khi người dùng thực hiện hành động cần lưu trạng thái, chẳng hạn thêm sản phẩm vào giỏ hàng, ứng dụng có thể chủ động tạo phiên:

~~~java
@PostMapping("/cart/items")
public String addToCart(
        @RequestParam long productId,
        HttpServletRequest request) {

    HttpSession session = request.getSession(true);
    Cart cart = (Cart) session.getAttribute("cart");
    if (cart == null) {
        cart = new Cart();
    }

    cart.add(productId);
    session.setAttribute("cart", cart);
    return "redirect:/cart";
}
~~~

Trong ví dụ, việc tạo phiên gắn với một hành động nghiệp vụ rõ ràng. Nếu session đã tồn tại, code lấy lại phiên đó; nếu chưa có, Spring Session tạo phiên mới và thuộc tính giỏ hàng được ghi vào phiên.

Một điểm quan trọng là không nên tạo phiên chỉ để lưu một dữ liệu có thể xử lý trong request hiện tại. Ví dụ, dữ liệu tìm kiếm chỉ dùng để trả về kết quả trong cùng request thường nên nằm trong biến cục bộ hoặc model của request, không cần đưa vào HttpSession.

## 6. Kiểm tra phiên và session ID mà không tạo phiên mới

Servlet API có các phương thức hỗ trợ kiểm tra session ID của request:

~~~java
String requestedId = request.getRequestedSessionId();
boolean fromCookie = request.isRequestedSessionIdFromCookie();
boolean valid = request.isRequestedSessionIdValid();

HttpSession session = request.getSession(false);
boolean hasSession = session != null;
~~~

Các phương thức này trả lời những câu hỏi khác nhau:

| Phương thức | Ý nghĩa |
|---|---|
| `getRequestedSessionId()` | Lấy ID phiên mà request mang theo theo cơ chế nhận diện phiên đang cấu hình; có thể là `null` |
| `isRequestedSessionIdFromCookie()` | Cho biết ID được request gửi qua cookie theo Servlet API |
| `isRequestedSessionIdValid()` | Cho biết ID phiên được request gửi lên có hợp lệ theo container/repository tại thời điểm kiểm tra |
| `getSession(false)` | Lấy phiên hiện có gắn với request; trả về `null` nếu không có, không tạo phiên mới |

`requestedId != null` không chứng minh phiên còn tồn tại. Cookie có thể chứa ID đã hết hạn, đã logout hoặc không còn trong repository. Trong trường hợp đó, `getSession(false)` có thể trả về `null` và `isRequestedSessionIdValid()` trả về `false`.

Ứng dụng có thể dùng thông tin này để hỗ trợ chẩn đoán, nhưng không nên ghi toàn bộ session ID vào log. Nếu cần tương quan log, dùng một mã đã được băm hoặc xử lý an toàn, đồng thời tránh log token hay cookie nhạy cảm.

Không dùng việc có phiên làm bằng chứng người dùng đã đăng nhập. Một phiên có thể được tạo bởi giỏ hàng ẩn danh, CSRF token, flash attribute hoặc một tính năng khác. Trạng thái xác thực cần được kiểm tra qua Spring Security hoặc cơ chế xác thực mà ứng dụng sử dụng.

## 7. Những thành phần có thể tạo phiên gián tiếp

Một ứng dụng có thể tạo phiên dù controller không gọi trực tiếp `getSession()`. Một số thành phần thường gặp:

| Thành phần | Vì sao có thể tạo hoặc dùng phiên |
|---|---|
| Spring Security | Một số cấu hình lưu SecurityContext, lưu request cần tiếp tục sau đăng nhập hoặc lưu CSRF token trong HttpSession |
| Spring MVC `@SessionAttributes` | Chuyển các thuộc tính model được chỉ định sang phiên để dùng qua nhiều request |
| Flash attributes | Cơ chế lưu dữ liệu tạm giữa redirect và request kế tiếp thường dùng session-backed FlashMap |
| JSP | JSP mặc định có thể tham chiếu session thông qua implicit object; trang không cần session có thể cấu hình `session="false"` |
| Thư viện hoặc filter tùy chỉnh | Có thể gọi `request.getSession()` trong quá trình xử lý |

Hành vi thực tế phụ thuộc phiên bản và cấu hình. Ví dụ, Spring Security có thể trì hoãn việc tạo session cho tới khi một tính năng cần lưu trạng thái được sử dụng. Một trang công khai vẫn có thể tạo phiên nếu filter, template hoặc thư viện truy cập session trong lúc render.

Khi thấy cookie session xuất hiện trên endpoint vốn không cần phiên, hãy kiểm tra toàn bộ chuỗi filter, interceptor, controller, view và thư viện được gọi. Tìm các điểm gọi `getSession()`, `getSession(true)`, `setAttribute` hoặc các tính năng lưu trạng thái gián tiếp.

### 7.1. Kiểm tra JSP không cần session

Nếu một JSP chỉ render nội dung công khai và không sử dụng session implicit object, có thể tắt session cho trang:

~~~jsp
<%@ page session="false" %>
~~~

Điều này giúp tránh việc JSP yêu cầu session chỉ vì cơ chế mặc định của trang. Chỉ đặt `session="false"` khi trang thực sự không cần dùng session; nếu code JSP hoặc tag library phụ thuộc vào session, cần điều chỉnh chúng trước.

## 8. Tác động đến Spring Session và repository dùng chung

Với Spring Session, số phiên được tạo có ảnh hưởng trực tiếp đến Redis hoặc JDBC. Một request công khai vô tình gọi `getSession()` có thể tạo phiên mới và khiến repository phải lưu dữ liệu, phát session ID, theo dõi TTL và dọn phiên hết hạn.

Ví dụ, nếu trang chủ được tải bởi 100.000 khách truy cập không đăng nhập và mỗi lần render đều tạo một phiên, hệ thống có thể phát sinh lượng phiên lớn dù phần lớn người dùng không sử dụng chức năng cần trạng thái. Tác động gồm:

- Tăng số key hoặc bản ghi phiên trong Redis/JDBC.
- Tăng số lần ghi, cập nhật và dọn dữ liệu.
- Tăng lưu lượng cookie trong request và response.
- Làm metric số phiên hoạt động không còn phản ánh gần đúng số người dùng thực sự cần trạng thái.
- Tăng chi phí lưu trữ và làm khó điều tra session bất thường.

Nếu dùng Redis, mỗi phiên có thể tạo một nhóm key/field và metadata theo cấu trúc repository. Nếu dùng JDBC, phiên và thuộc tính có thể tạo các hàng tương ứng trong bảng Spring Session. Chi tiết phụ thuộc repository và cấu hình, nhưng nguyên tắc chung là giảm tạo phiên không cần thiết sẽ giảm công việc lưu trữ.

Spring Session hỗ trợ nhiều instance chia sẻ repository, nhưng không có nghĩa mọi request đều cần một phiên. Hãy chỉ tạo phiên ở những luồng nghiệp vụ cần trạng thái qua nhiều request.

## 9. Filter order và thời điểm truy cập HttpSession

`SessionRepositoryFilter` phải chạy trước các filter khác có nhu cầu sử dụng `HttpSession`. Khi filter này bọc request/response, những lời gọi session ở các filter phía sau mới được chuyển tới Spring Session repository.

Với Spring Boot auto-configuration, thứ tự đăng ký filter thường được thiết lập tự động. Nếu tự đăng ký filter hoặc tự cấu hình Spring Session, hãy xác minh thứ tự thực tế. Một filter chạy trước `SessionRepositoryFilter` có thể truy cập session cục bộ của Servlet container, trong khi controller phía sau lại truy cập session do Spring Session quản lý. Điều này gây ra trạng thái không nhất quán hoặc session ID không như mong đợi.

Trong một chain thông thường:

1. Request đi vào Servlet container.
2. `SessionRepositoryFilter` bọc request và response.
3. Các filter bảo mật, filter ứng dụng và DispatcherServlet xử lý request đã được bọc.
4. Controller hoặc framework truy cập `HttpSession`.
5. Response được commit; Spring Session hoàn tất việc lưu phiên và xử lý session ID theo resolver.

Nếu một filter cần kiểm tra phiên hiện có mà không tạo mới, hãy dùng `request.getSession(false)`. Nếu filter cần tạo phiên cho một lý do cụ thể, hãy ghi rõ lý do đó trong thiết kế và kiểm thử hành vi trên tất cả instance.

## 10. Kết hợp với đăng nhập, logout và session fixation

Không dùng `getSession()` để quyết định người dùng đã đăng nhập. Việc có session chỉ chứng minh request có một phiên làm việc. Một phiên có thể được tạo trước khi đăng nhập hoặc dùng cho khách ẩn danh.

Trong ứng dụng Spring Security, nên dùng `SecurityContextHolder`, `Authentication` hoặc cơ chế authorization được cấu hình để xác định danh tính và quyền truy cập. Spring Security có thể lưu SecurityContext vào session tùy chính sách lưu trữ. Khi đăng nhập thành công, chiến lược session fixation protection có thể đổi session ID hoặc chuyển session; đây là một phần của luồng bảo mật và không nên tự thay thế bằng thao tác tạo phiên tùy tiện.

Khi logout, Spring Security thường xóa SecurityContext và vô hiệu hóa phiên theo cấu hình logout. Nếu code cần truy cập phiên trước khi logout, dùng `getSession(false)` để tránh tạo phiên mới chỉ để xóa nó:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
~~~

Trong ứng dụng đã tích hợp Spring Security, ưu tiên cấu hình logout của Spring Security để các handler, repository và cơ chế dọn trạng thái liên quan được gọi đúng thứ tự. Đoạn code trên chỉ minh họa cho Servlet app tự quản lý logout đơn giản.

## 11. Kiểm thử thời điểm tạo phiên

Nên có kiểm thử chứng minh endpoint công khai không tạo phiên, còn endpoint nghiệp vụ tạo phiên đúng lúc.

### 11.1. Unit test với MockHttpServletRequest

Mock Servlet request có thể kiểm tra ngữ nghĩa API:

~~~java
@Test
void getSessionFalseDoesNotCreateSession() {
    MockHttpServletRequest request = new MockHttpServletRequest();

    assertNull(request.getSession(false));
    assertNull(request.getSession(false));
}

@Test
void getSessionCreatesSessionWhenMissing() {
    MockHttpServletRequest request = new MockHttpServletRequest();

    HttpSession session = request.getSession();

    assertNotNull(session);
    assertSame(session, request.getSession(false));
    assertSame(session, request.getSession(true));
}
~~~

Unit test này xác nhận hành vi của mock request. Nó không chứng minh phiên đã được lưu vào Redis/JDBC hoặc cookie đã được gửi qua HTTP.

### 11.2. Integration test với Spring Session

Để xác minh repository, hãy chạy ứng dụng với đúng cấu hình Spring Session và kho thử nghiệm:

1. Gửi request tới endpoint công khai chưa có cookie; xác nhận response không tạo session cookie nếu endpoint và toàn bộ filter/view không cần phiên.
2. Gửi request tới endpoint chỉ gọi `getSession(false)`; xác nhận kết quả không có phiên và repository không có session mới.
3. Gửi request tới endpoint tạo phiên và ghi thuộc tính; xác nhận response phát session ID theo resolver đang dùng.
4. Gửi request tiếp theo kèm session ID; xác nhận endpoint đọc được thuộc tính đã lưu.
5. Gửi request với ID không hợp lệ hoặc phiên đã hết TTL; xác nhận ứng dụng xử lý như trường hợp chưa có phiên.
6. Thử qua hai instance cùng dùng Redis/JDBC để xác nhận phiên mới có thể được đọc ở instance còn lại.

Khi kiểm tra cookie, đừng chỉ nhìn header `Set-Cookie` của một response. Cần theo dõi cả cookie jar của client và request kế tiếp để xác nhận client thực sự gửi lại session ID. Nếu ứng dụng dùng header resolver hoặc resolver tùy chỉnh, hãy kiểm tra đúng cơ chế thay vì giả định cookie.

### 11.3. Theo dõi trong môi trường phát triển

Trong môi trường test hoặc staging, có thể thêm log tạm thời để ghi nhận:

- Endpoint nào gọi tạo phiên.
- Có session hiện tại trước khi xử lý hay không.
- Session ID có được resolver nhận diện hay không, nhưng tránh ghi giá trị ID thô.
- Response có phát session cookie hoặc session header hay không.
- Repository ghi phiên mới ở thời điểm nào.

Không để log chi tiết session hoạt động lâu dài trong production nếu không cần thiết. Không ghi nội dung thuộc tính, token, thông tin xác thực hoặc cookie nguyên vẹn.

## 12. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Trang công khai luôn phát session cookie | Controller, JSP, filter hoặc framework gọi tạo phiên | Tìm điểm truy cập session gián tiếp; đổi sang `getSession(false)` nếu chỉ đọc tùy chọn |
| Repository có nhiều phiên dù ít người đăng nhập | Session được tạo bởi request ẩn danh, CSRF, flash attribute hoặc request cache | Xác định tính năng cần session; chỉ tạo phiên ở luồng cần trạng thái |
| `getSession(false)` trả về `null` dù trình duyệt gửi cookie | Session ID hết hạn, đã logout, sai namespace hoặc repository không tìm thấy phiên | Kiểm tra resolver, TTL, repository và cookie; xử lý như phiên không còn tồn tại |
| Phiên được tạo nhưng request tiếp theo không dùng lại được | Response không gửi được session ID, cookie bị chặn hoặc cấu hình resolver khác nhau giữa các instance | Kiểm tra `Set-Cookie`, domain/path/SameSite/Secure và resolver ở mọi instance |
| Một filter thấy session khác với controller | Filter chạy trước SessionRepositoryFilter hoặc có cấu hình session cục bộ song song | Sửa thứ tự filter và xác minh chỉ một cơ chế quản lý phiên đang được dùng |
| Logout xong request tiếp theo lại có phiên mới | Một filter hoặc framework tạo session mới sau khi phiên cũ bị invalidate | Kiểm tra thứ tự logout và các thành phần truy cập session phía sau |

## 13. Checklist khi dùng getSession trong code

- [ ] Dùng `getSession(false)` khi phiên là tùy chọn và chỉ cần đọc trạng thái hiện có.
- [ ] Chỉ dùng `getSession()` hoặc `getSession(true)` khi nghiệp vụ thật sự cần tạo trạng thái phiên.
- [ ] Không dùng sự tồn tại của session để kết luận người dùng đã đăng nhập.
- [ ] Kiểm tra các filter, interceptor, JSP, flash attributes và framework có thể tạo session gián tiếp.
- [ ] Đảm bảo `SessionRepositoryFilter` chạy trước các filter cần `HttpSession`.
- [ ] Hiểu rằng tạo đối tượng session, lưu repository và gửi session ID là các thời điểm khác nhau.
- [ ] Không tạo phiên sau khi response đã commit.
- [ ] Kiểm thử request không có cookie, cookie hợp lệ, cookie hết hạn và request qua nhiều instance.
- [ ] Không ghi session ID hoặc dữ liệu nhạy cảm vào log.

Trong ứng dụng Spring Session, lựa chọn giữa `getSession()` và `getSession(false)` quyết định request có được phép tạo trạng thái mới hay không. Dùng `getSession(false)` cho thao tác đọc tùy chọn, tạo phiên có chủ đích ở luồng nghiệp vụ cần lưu trạng thái và kiểm thử cả thời điểm lưu repository lẫn thời điểm gửi session ID sẽ giúp kiểm soát số phiên, cookie và hành vi của ứng dụng khi chạy nhiều instance.
