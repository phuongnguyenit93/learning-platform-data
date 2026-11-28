# Phiên làm việc (session) là gì và vì sao HTTP cần cơ chế giữ trạng thái

## Mục tiêu bài học

Sau bài này, bạn có thể giải thích vì sao ứng dụng web cần liên kết nhiều HTTP request với cùng một ngữ cảnh; phân biệt HTTP, cookie, Session ID và dữ liệu session; mô tả vòng đời của session; hiểu vai trò của Spring Session khi triển khai nhiều instance; và nhận biết các vấn đề về timeout, đồng thời, bảo mật khi lưu trạng thái phiên.

## 1. Vấn đề: mỗi HTTP request được xử lý độc lập

HTTP hoạt động theo mô hình request/response. Trình duyệt gửi một request, máy chủ xử lý và trả về response. Request tiếp theo là một lần trao đổi mới. Theo thiết kế của HTTP, máy chủ không tự động ghi nhớ nội dung request trước để áp dụng cho request sau.

Hãy hình dung người dùng mở một cửa hàng trực tuyến:

1. Người dùng xem trang sản phẩm.
2. Người dùng thêm một sản phẩm vào giỏ hàng.
3. Người dùng mở trang thanh toán.
4. Người dùng đăng nhập.
5. Người dùng xác nhận đơn hàng.

Mỗi bước thường tạo ra một HTTP request riêng. Request xem giỏ hàng không tự nói rằng sản phẩm nào đã được thêm ở bước trước. Request thanh toán cũng không tự mang theo toàn bộ ngữ cảnh của quá trình mua hàng.

Một ứng dụng vẫn có thể hoạt động mà không giữ trạng thái giữa các request. Ví dụ, endpoint tra cứu tỷ giá có thể nhận đủ mã tiền tệ trong từng request và trả về kết quả ngay. Nhưng nhiều chức năng web cần nối các request thành một trải nghiệm liên tục: giỏ hàng, quy trình nhiều bước, lựa chọn ngôn ngữ, trạng thái đăng nhập hoặc một biểu mẫu đang điền dở.

Đây là lý do ứng dụng cần một cơ chế để liên kết các request với cùng một ngữ cảnh.

### HTTP không trạng thái có nghĩa gì?

“Không trạng thái” (stateless) ở đây có nghĩa là bản thân giao thức HTTP không quy định máy chủ phải lưu trạng thái ứng dụng của một client giữa các request. Điều đó không có nghĩa là:

- Máy chủ không được lưu dữ liệu.
- Trình duyệt không được gửi cookie.
- Mọi request bắt buộc phải đi qua cùng một kết nối TCP.
- Ứng dụng web không thể có đăng nhập hoặc giỏ hàng.

Ứng dụng có thể xây dựng cơ chế trạng thái ở tầng ứng dụng. Cookie, session, token và cơ sở dữ liệu là những cách phổ biến để thực hiện việc đó.

Kết nối TCP được giữ mở hoặc HTTP keep-alive cũng không thay thế session. Một người dùng có thể gửi nhiều request qua các kết nối khác nhau; proxy, trình duyệt hoặc bộ cân bằng tải có thể tạo và đóng kết nối theo cách riêng. Kết nối mạng không phải là danh tính ổn định của người dùng.

## 2. Session là gì?

Session (phiên làm việc) là một vùng ngữ cảnh có thời hạn mà ứng dụng dùng để liên kết nhiều request với cùng một lượt sử dụng ứng dụng.

Một session thường có ba thành phần:

| Thành phần | Vai trò |
|---|---|
| Session ID | Mã định danh ngẫu nhiên, khó đoán, dùng để tìm đúng phiên |
| Dữ liệu session | Các thuộc tính ứng dụng cần giữ giữa các request, chẳng hạn mã giỏ hàng hoặc trạng thái của một quy trình |
| Nơi lưu session | Thành phần lưu và truy xuất dữ liệu phiên, ví dụ bộ nhớ máy chủ, Redis hoặc cơ sở dữ liệu quan hệ |

Trong mô hình session phía máy chủ, trình duyệt thường chỉ giữ Session ID trong cookie. Dữ liệu nghiệp vụ của phiên được lưu ở phía máy chủ. Khi request tiếp theo đến, trình duyệt gửi lại cookie; ứng dụng dùng Session ID để tra cứu dữ liệu session tương ứng.

Ví dụ minh họa:

- Trình duyệt giữ cookie có giá trị `SESSION=abc...`.
- Kho session lưu bản ghi tương ứng với ID đó.
- Bản ghi có thể chứa `cartId`, `locale` hoặc thông tin phục vụ quy trình hiện tại.
- Khi request tiếp theo gửi cookie này, máy chủ tìm lại đúng bản ghi và tiếp tục xử lý.

Giá trị cookie ở ví dụ trên chỉ là chuỗi minh họa. Session ID thực tế phải được tạo bằng bộ sinh số ngẫu nhiên an toàn và đủ khó đoán.

### Session không đồng nghĩa với tài khoản đăng nhập

Session là ngữ cảnh của một lượt sử dụng ứng dụng. Người dùng có thể có session trước khi đăng nhập, chẳng hạn để lưu giỏ hàng tạm thời. Trạng thái xác thực lại cho biết người dùng đã được xác thực hay chưa và có danh tính nào.

Một ứng dụng có thể lưu thông tin xác thực trong session. Spring Security cũng có thể lưu `SecurityContext` qua session trong cấu hình web thông thường. Tuy vậy, session và xác thực là hai khái niệm khác nhau: session có thể tồn tại cho người dùng ẩn danh, còn ứng dụng cũng có thể được cấu hình để xác thực theo cơ chế không dùng HTTP session.

### Session ID là chìa khóa tra cứu, không phải dữ liệu nghiệp vụ

Session ID nên là một giá trị opaque: client chỉ gửi lại nó, không cần hiểu nội dung bên trong. Ứng dụng dùng ID để tra cứu session trong kho lưu trữ.

Không nên đưa tên, email, quyền truy cập hoặc dữ liệu nhạy cảm trực tiếp vào Session ID. Một ID đoán được hoặc bị đánh cắp có thể cho phép người khác sử dụng phiên của nạn nhân. Vì vậy, ID phải đủ ngẫu nhiên, được truyền qua HTTPS và được bảo vệ như một thông tin xác thực dạng bearer.

## 3. Cookie kết nối trình duyệt với session

Cookie là cơ chế HTTP cho phép máy chủ yêu cầu trình duyệt lưu một cặp tên/giá trị và gửi lại nó trong những request phù hợp.

Khi cần tạo session, máy chủ thường trả về header `Set-Cookie`. Trình duyệt lưu cookie rồi gửi header `Cookie` trong những request tiếp theo đến đúng phạm vi domain, path và điều kiện bảo mật.

Ví dụ rút gọn:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=opaque-session-id; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Request tiếp theo có thể chứa:

~~~http
GET /cart HTTP/1.1
Host: shop.example
Cookie: SESSION=opaque-session-id
~~~

Tên cookie phụ thuộc cấu hình. Servlet container truyền thống thường dùng tên `JSESSIONID`; Spring Session thường dùng cookie riêng và có thể cấu hình tên, thuộc tính cũng như cách phân giải ID.

Cookie không nhất thiết chứa dữ liệu session. Trong mô hình session phía máy chủ, cookie chủ yếu mang Session ID; dữ liệu được lưu ở repository phía máy chủ.

### Các thuộc tính cookie quan trọng

- `HttpOnly`: ngăn JavaScript phía trình duyệt đọc cookie qua API cookie thông thường. Thuộc tính này giảm một số nguy cơ đánh cắp cookie qua XSS, nhưng không loại bỏ lỗ hổng XSS.
- `Secure`: yêu cầu trình duyệt chỉ gửi cookie qua kết nối HTTPS. Môi trường production nên dùng HTTPS và bật thuộc tính này cho cookie session.
- `SameSite`: điều chỉnh việc gửi cookie trong ngữ cảnh điều hướng hoặc request cross-site. `Lax` thường là lựa chọn cân bằng cho nhiều ứng dụng web; `Strict` chặt hơn; `None` cho phép gửi trong ngữ cảnh cross-site và phải đi cùng `Secure` trên các trình duyệt hiện đại.
- `Path` và `Domain`: xác định phạm vi URL hoặc host mà trình duyệt gửi cookie.
- `Max-Age` hoặc `Expires`: xác định thời hạn lưu cookie ở trình duyệt.

Không nên xem `HttpOnly`, `Secure` hay `SameSite` là phương án thay thế cho mọi biện pháp bảo mật khác. Ví dụ, cookie session vẫn cần được bảo vệ khỏi CSRF bằng cấu hình phù hợp, token CSRF hoặc cơ chế phòng vệ tương ứng với kiến trúc ứng dụng.

### Cookie phiên và thời hạn session phía máy chủ là hai việc khác nhau

Cookie không có `Expires` hoặc `Max-Age` thường được gọi là session cookie: trình duyệt quản lý nó theo vòng đời phiên trình duyệt. Tuy nhiên, điều đó không bảo đảm dữ liệu session trên máy chủ còn tồn tại đến lúc trình duyệt đóng.

Máy chủ có thể hết hạn session sau 30 phút không hoạt động dù cookie vẫn còn trong trình duyệt. Ngược lại, trình duyệt có thể khôi phục session cookie sau khi khởi động lại tùy theo hành vi khôi phục phiên của trình duyệt.

Vì vậy, cần phân biệt:

- **Thời hạn cookie**: trình duyệt giữ và gửi cookie trong bao lâu.
- **Thời hạn session**: kho lưu trữ giữ dữ liệu phiên trong bao lâu.
- **Thời gian không hoạt động tối đa**: khoảng thời gian một phiên có thể không được truy cập trước khi hết hạn, tùy cách repository triển khai.

## 4. Vòng đời của một session

Một vòng đời điển hình gồm các bước sau.

### Bước 1: request đầu tiên chưa có Session ID

Trình duyệt gửi request mà không có cookie session. Máy chủ có thể trả lời mà không tạo session nếu endpoint không cần trạng thái. Session thường chỉ được tạo khi ứng dụng hoặc framework yêu cầu.

Với Servlet API:

- `request.getSession()` trả về session hiện tại hoặc tạo session mới nếu chưa có.
- `request.getSession(false)` trả về session hiện tại nếu có, hoặc `null` nếu chưa có; lời gọi này không tạo session mới.

Sự khác nhau này hữu ích cho các endpoint chỉ muốn kiểm tra phiên hiện có mà không vô tình tạo phiên mới.

### Bước 2: máy chủ tạo session

Khi ứng dụng cần lưu trạng thái, nó tạo session. Repository cấp hoặc ghi nhận Session ID, lưu các thuộc tính và thiết lập thời hạn theo cấu hình.

Response thường gửi Session ID về trình duyệt qua `Set-Cookie`.

### Bước 3: request tiếp theo gửi lại cookie

Trình duyệt tự động gửi cookie phù hợp. Thành phần quản lý session đọc Session ID, tìm bản ghi tương ứng trong repository và gắn session vào ngữ cảnh xử lý request.

Ứng dụng có thể đọc hoặc cập nhật thuộc tính session như khi làm việc với `HttpSession`.

### Bước 4: session được cập nhật và gia hạn

Khi ứng dụng thay đổi thuộc tính, repository cần lưu thay đổi theo cơ chế của nó. Một lần truy cập có thể làm mới thời điểm hết hạn hoặc TTL, tùy chính sách của kho session và cấu hình.

Không nên giả định mọi thay đổi được ghi xuống kho lưu trữ ngay tại đúng dòng lệnh gọi `setAttribute`. Một số chế độ có thể gom thay đổi và ghi khi request kết thúc.

### Bước 5: session hết hạn hoặc bị hủy

Session có thể kết thúc vì:

- Quá thời gian không hoạt động.
- Người dùng đăng xuất và ứng dụng chủ động hủy session.
- Quản trị viên hoặc quy trình vận hành xóa session.
- Repository bị cấu hình xóa dữ liệu theo chính sách riêng.

Khi session đã hết hạn hoặc bị hủy, Session ID cũ không còn tra cứu được thành một phiên hợp lệ. Request sau đó có thể tạo session mới nếu ứng dụng yêu cầu.

Sơ đồ khái quát:

~~~mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant A as Ứng dụng Spring
    participant R as Session Repository

    B->>A: GET /cart (chưa có cookie session)
    A->>R: Tạo session khi ứng dụng yêu cầu
    R-->>A: Session ID và dữ liệu phiên
    A-->>B: Response + Set-Cookie
    B->>A: GET /cart (gửi Cookie)
    A->>R: Tìm session theo Session ID
    R-->>A: Dữ liệu session
    A->>A: Xử lý request với HttpSession
    A->>R: Lưu thay đổi và cập nhật thời hạn
    A-->>B: Response
~~~

## 5. Ứng dụng cần giữ những loại trạng thái nào?

Session phù hợp với dữ liệu nhỏ, có phạm vi theo một lượt sử dụng và cần được truy cập ở nhiều request.

Một số trường hợp phổ biến:

| Trường hợp | Dữ liệu có thể lưu trong session |
|---|---|
| Giỏ hàng ẩn danh | Mã giỏ hàng hoặc mã định danh các mục tạm thời |
| Quy trình nhiều bước | ID quy trình, bước hiện tại, dữ liệu tạm đã được xác thực |
| Giao diện | Ngôn ngữ hoặc lựa chọn hiển thị của phiên hiện tại |
| Xác thực web | Ngữ cảnh bảo mật hoặc thông tin tham chiếu đến trạng thái đăng nhập |
| Thông báo một lần | Thông báo cần hiển thị sau khi chuyển hướng |

Session không phải nơi lưu trữ lâu dài cho mọi dữ liệu của người dùng. Đơn hàng đã tạo, hồ sơ khách hàng, quyền sở hữu tài nguyên và dữ liệu tài chính nên nằm trong kho dữ liệu nghiệp vụ có vòng đời và quy tắc nhất quán riêng. Session có thể giữ ID tham chiếu đến các bản ghi đó.

Một quy tắc thực tế là chỉ lưu trong session lượng dữ liệu cần thiết để tiếp tục request tiếp theo. Tránh lưu file lớn, ảnh, toàn bộ entity graph của ORM hoặc bản sao dữ liệu nghiệp vụ có thể thay đổi thường xuyên. Dữ liệu session lớn làm tăng chi phí đọc, ghi, truyền qua mạng và serialize.

## 6. Spring Session giải quyết phần nào?

Servlet API đã định nghĩa `HttpSession`, cho phép ứng dụng tạo, đọc, cập nhật và hủy session. Với cấu hình servlet mặc định, session thường do servlet container quản lý. Nếu ứng dụng chạy trên một máy chủ, dữ liệu session có thể nằm trong bộ nhớ của tiến trình đó.

Cách lưu cục bộ có giới hạn khi triển khai nhiều instance. Giả sử hệ thống có hai instance:

- Request đầu tiên được cân bằng tải đến instance A. A tạo session trong bộ nhớ của A.
- Request tiếp theo được chuyển đến instance B.
- B không có bản ghi session của A nên không thể khôi phục trạng thái.

Có thể cấu hình sticky session để bộ cân bằng tải cố gắng đưa cùng người dùng về cùng instance. Cách này giảm tình huống request đổi máy chủ, nhưng vẫn khiến phiên phụ thuộc vào instance đó; khi instance lỗi hoặc cần phân phối lại tải, trải nghiệm có thể bị gián đoạn.

Spring Session cung cấp một lớp quản lý session có thể thay thế cách lưu cục bộ của container bằng một repository dùng chung. Các ứng dụng tiếp tục làm việc qua API `HttpSession`, trong khi Spring Session quản lý việc phân giải Session ID và lưu/đọc dữ liệu phiên từ kho được cấu hình.

Hai lựa chọn thường gặp:

- **Redis**: lưu session trong kho key-value dùng chung. Redis hỗ trợ TTL, phù hợp với dữ liệu phiên có thời hạn và nhiều instance cần truy cập.
- **JDBC**: lưu session trong cơ sở dữ liệu quan hệ. Cách này hữu ích khi hạ tầng đã có cơ sở dữ liệu quan hệ và muốn quản lý session qua bảng dữ liệu.

Khi mọi instance dùng cùng một repository, request có thể đến instance A hoặc B mà vẫn tra cứu được session chung, miễn là các instance dùng cấu hình tương thích và repository đang hoạt động.

### Luồng xử lý với Spring Session

Trong ứng dụng Servlet, Spring Session tích hợp ở tầng filter. Filter bọc request/response để lời gọi `HttpSession` của ứng dụng được chuyển đến repository Spring Session. Nhờ đó, controller vẫn sử dụng API Servlet quen thuộc mà không cần tự viết mã Redis hoặc SQL ở từng endpoint.

Luồng khái quát:

1. Trình duyệt gửi cookie chứa Session ID.
2. Filter của Spring Session phân giải ID.
3. Repository đọc session từ Redis hoặc JDBC.
4. Request được chuyển vào controller với `HttpSession` tương ứng.
5. Khi request kết thúc, thay đổi được lưu theo chế độ flush của repository.
6. Kho lưu trữ áp dụng TTL hoặc chính sách hết hạn.

Spring Session không tự biến toàn bộ ứng dụng thành stateless. Ứng dụng vẫn dựa vào trạng thái phiên; điểm khác biệt là trạng thái có thể được lưu ở nơi nhiều instance cùng truy cập.

## 7. Ví dụ sử dụng HttpSession trong ứng dụng Spring

Controller sau minh họa cách lưu một giá trị nhỏ qua nhiều request. Mục đích là làm rõ API session; một giỏ hàng thực tế nên được quản lý bằng mô hình nghiệp vụ và kho dữ liệu phù hợp.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CartSessionController {

    @PostMapping("/cart/items")
    public String addItem(HttpServletRequest request) {
        // Tạo session nếu request hiện tại chưa có session.
        HttpSession session = request.getSession();

        Integer count = (Integer) session.getAttribute("cartCount");
        int nextCount = (count == null) ? 1 : count + 1;

        session.setAttribute("cartCount", nextCount);
        return "Số mục trong phiên: " + nextCount;
    }

    @GetMapping("/cart/count")
    public int getCount(HttpServletRequest request) {
        // Không tạo session mới chỉ để đọc.
        HttpSession session = request.getSession(false);

        if (session == null) {
            return 0;
        }

        Integer count = (Integer) session.getAttribute("cartCount");
        return (count == null) ? 0 : count;
    }
}
~~~

Sau request `POST /cart/items` đầu tiên, ứng dụng tạo session và trả cookie session. Khi trình duyệt gọi `GET /cart/count`, cookie được gửi lại, session được tìm thấy và giá trị `cartCount` được đọc.

Nếu trình duyệt không gửi cookie, hoặc session đã hết hạn, endpoint đọc trả về `0`. Điều này không có nghĩa dữ liệu giỏ hàng đã bị xóa khỏi hệ thống nghiệp vụ; ví dụ này chỉ lưu một bộ đếm minh họa trong session.

### Cấu hình lưu trữ tập trung

Với Spring Boot, có thể bổ sung module Spring Session phù hợp và cấu hình kết nối đến Redis hoặc JDBC. Ví dụ các dependency thường dùng cho Redis trong dự án Gradle được quản lý phiên bản bởi Spring Boot:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.session:spring-session-data-redis")
}
~~~

Ví dụ cấu hình kết nối và thời hạn session:

~~~properties
spring.data.redis.host=localhost
spring.data.redis.port=6379
spring.session.timeout=30m
~~~

Cách kích hoạt repository cụ thể phụ thuộc phiên bản Spring Boot và cấu hình ứng dụng. Với cấu hình auto-configuration phù hợp, Spring Boot có thể đăng ký Spring Session Redis khi module cần thiết có mặt. Một số cấu hình Servlet chủ động dùng `@EnableRedisHttpSession`. Cần chọn một cách cấu hình tương thích với phiên bản đang dùng và tránh đăng ký hai cấu hình session chồng lấn.

Nếu chọn JDBC, ứng dụng dùng module Spring Session JDBC và cấu hình `DataSource` phù hợp. Cần tạo schema Spring Session theo hướng dẫn của phiên bản đang sử dụng; không nên tự giả định tên cột hoặc cấu trúc bảng giữa các phiên bản.

Khi dùng kho lưu trữ ngoài, cần kiểm tra cách serialize thuộc tính session. Nếu lưu object Java tùy chỉnh, kiểu dữ liệu và serializer phải tương thích giữa các instance. Thay đổi cấu trúc class trong lúc triển khai rolling update có thể khiến instance cũ không đọc được dữ liệu do instance mới ghi. Lưu các giá trị đơn giản hoặc DTO ổn định giúp giảm rủi ro.

## 8. Session trong hệ thống nhiều instance

Một repository dùng chung cho phép nhiều instance cùng đọc và ghi session. Điều này giúp ứng dụng mở rộng ngang mà không buộc người dùng phải quay lại cùng một máy chủ.

Ví dụ:

~~~text
                    +------------------+
Trình duyệt --------> Load Balancer
  Cookie: SESSION   +--------+---------+
                             |
                  +----------+----------+
                  |                     |
             +----v----+           +----v----+
             | App A   |           | App B   |
             +----+----+           +----+----+
                  |                     |
                  +----------+----------+
                             |
                    +--------v---------+
                    | Redis / JDBC     |
                    | Shared Session   |
                    +------------------+
~~~

Cả App A và App B đều tra cứu Session ID trong cùng repository. Request đầu tiên có thể đến A, request sau có thể đến B mà vẫn tiếp tục được phiên.

Tuy nhiên, repository dùng chung không giải quyết mọi vấn đề phân tán:

- Redis hoặc cơ sở dữ liệu trở thành một phụ thuộc vận hành quan trọng. Nếu kho lưu trữ không khả dụng, ứng dụng có thể không đọc hoặc ghi được session.
- Độ trễ mạng và thao tác serialize/deserialize ảnh hưởng thời gian xử lý request.
- Nhiều request đồng thời có thể đọc cùng một trạng thái cũ rồi ghi đè thay đổi của nhau.
- Các instance cần thống nhất cấu hình cookie, namespace, serializer và chính sách timeout.
- Khi triển khai phiên bản mới, cần tính đến khả năng đọc dữ liệu session được ghi bởi phiên bản cũ.

Session repository nên được giám sát như một thành phần hạ tầng: theo dõi độ trễ, tỷ lệ lỗi, dung lượng, số lượng session, TTL và tình trạng kết nối.

## 9. Request đồng thời và cập nhật session

Một người dùng có thể mở nhiều tab hoặc gửi nhiều request gần như cùng lúc. Ví dụ hai request cùng đọc `cartCount = 2`, mỗi request tăng lên `3`, rồi cả hai cùng ghi. Kết quả cuối có thể vẫn là `3` thay vì `4`. Đây là vấn đề lost update.

Việc lưu session ở Redis hay JDBC không tự động biến chuỗi thao tác đọc-sửa-ghi của ứng dụng thành một giao dịch nguyên tử. Cách xử lý phụ thuộc vào yêu cầu nghiệp vụ:

- Nếu giá trị có thể tính lại, chấp nhận được khi sai lệch nhỏ hoặc không cần chính xác tuyệt đối, hãy xác định rõ mức nhất quán mong muốn.
- Nếu dữ liệu cần cập nhật chính xác, hãy lưu dữ liệu nghiệp vụ trong kho dữ liệu hỗ trợ transaction hoặc thao tác nguyên tử phù hợp.
- Hạn chế dùng một thuộc tính session như bộ đếm có tính cạnh tranh cao.
- Tránh để nhiều request ghi đè một object lớn trong session khi chúng chỉ cập nhật các phần khác nhau.

Session phù hợp để giữ ngữ cảnh điều hướng hoặc tham chiếu đến dữ liệu. Các thao tác cần bảo đảm tính đúng đắn của nghiệp vụ nên có cơ chế đồng bộ và transaction riêng.

## 10. Hết hạn, đăng xuất và quản lý vòng đời

Một session cần có thời hạn để dữ liệu cũ không tồn tại vô hạn. Thời hạn không hoạt động thường được gọi là session timeout hoặc max inactive interval. Khi không có hoạt động trong khoảng thời gian được cấu hình, session hết hạn và repository có thể xóa dữ liệu tương ứng.

Đăng xuất thường cần hủy session hiện tại. Với Servlet API:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
~~~

Sau khi invalidate, ứng dụng không nên tiếp tục sử dụng object session cũ. Với Spring Security, nên sử dụng luồng logout được framework cung cấp hoặc cấu hình đúng để dọn dẹp `SecurityContext`, session và cookie liên quan.

Khi người dùng đăng nhập, ứng dụng cần phòng chống session fixation. Kẻ tấn công có thể tìm cách khiến nạn nhân sử dụng một Session ID mà kẻ tấn công đã biết trước. Sau khi xác thực thành công, ID phiên nên được thay mới hoặc session được tạo lại theo cơ chế bảo vệ của framework. Spring Security có các chiến lược bảo vệ session fixation; cần giữ cấu hình phù hợp thay vì tự xử lý bằng mã tùy tiện.

Hủy session ở máy chủ và xóa cookie ở trình duyệt là hai thao tác khác nhau. Xóa cookie giúp trình duyệt ngừng gửi ID cũ; invalidate làm cho session ID đó không còn trỏ đến phiên hợp lệ ở máy chủ. Luồng đăng xuất nên xử lý cả hai khía cạnh theo cấu hình ứng dụng.

## 11. Các nguyên tắc bảo mật khi dùng session

Session ID có thể cho phép người nắm giữ nó tiếp tục sử dụng phiên. Vì vậy, cần bảo vệ ID và dữ liệu session trong toàn bộ vòng đời.

1. **Dùng HTTPS** cho toàn bộ luồng có cookie session và bật `Secure` trong môi trường production.
2. **Bật `HttpOnly`** cho cookie session để JavaScript không đọc được cookie qua API thông thường.
3. **Chọn `SameSite` phù hợp** và triển khai bảo vệ CSRF cho các thao tác làm thay đổi dữ liệu.
4. **Dùng Session ID đủ ngẫu nhiên, khó đoán**; không tự tạo ID bằng timestamp, số tăng dần hoặc thông tin người dùng.
5. **Thay ID sau khi xác thực hoặc thay đổi mức đặc quyền** theo cơ chế bảo vệ session fixation.
6. **Hủy session khi đăng xuất** và áp dụng timeout phù hợp với mức nhạy cảm của ứng dụng.
7. **Không ghi Session ID vào log công khai**, URL, thông báo lỗi hoặc dữ liệu phân tích mà nhiều người có thể truy cập.
8. **Giảm dữ liệu nhạy cảm lưu trong session**; chỉ lưu thông tin cần thiết và có chính sách bảo vệ kho lưu trữ.
9. **Kiểm tra quyền ở phía máy chủ trên từng request**. Việc có một session hợp lệ không đồng nghĩa người dùng được phép truy cập mọi tài nguyên.
10. **Giám sát truy cập bất thường** như cùng một session xuất hiện từ nhiều vị trí hoặc thiết bị không phù hợp với mô hình sử dụng.

Session ID trong URL đặc biệt dễ bị lộ qua lịch sử trình duyệt, log máy chủ, ảnh chụp màn hình và header referrer. Với ứng dụng web hiện đại, cookie thường là lựa chọn phù hợp hơn.

## 12. Khi nào dùng session, khi nào không?

Session không phải lựa chọn bắt buộc cho mọi API.

| Nhu cầu | Hướng tiếp cận thường phù hợp |
|---|---|
| Web app cần giỏ hàng ẩn danh, wizard hoặc trạng thái giao diện | Session phía máy chủ |
| Nhiều instance cần dùng chung trạng thái phiên | Spring Session với Redis hoặc JDBC |
| API stateless, mỗi request mang thông tin xác thực độc lập | Token hoặc cơ chế xác thực stateless phù hợp |
| Dữ liệu nghiệp vụ cần tồn tại lâu dài và có transaction | Cơ sở dữ liệu nghiệp vụ |
| Dữ liệu có thể tính lại, không gắn với một phiên người dùng | Cache hoặc cơ chế tính toán phù hợp |

Token như JWT có thể chứa claim để máy chủ xác minh mà không cần tra cứu session ở mỗi request. Tuy nhiên, token tự chứa thường khó thu hồi ngay trước khi hết hạn nếu không có thêm cơ chế kiểm tra hoặc danh sách thu hồi. Token cũng cần được bảo vệ khi lưu và truyền.

Dùng cookie session vẫn có thể phù hợp cho web app truyền thống, kể cả khi frontend và backend tách riêng. Điều cần quan tâm là cookie được gửi tự động nên phải xử lý CSRF, CORS và chính sách SameSite đúng với mô hình triển khai.

Quyết định nên dựa trên yêu cầu: cần thu hồi phiên nhanh đến đâu, có cần lưu trạng thái phía máy chủ không, số lượng instance, loại client, cách xác thực và khả năng vận hành kho lưu trữ.

## 13. Những nhầm lẫn thường gặp

**“HTTP stateless nên ứng dụng không thể nhớ người dùng.”**  
HTTP không tự lưu trạng thái ứng dụng giữa request, nhưng ứng dụng có thể liên kết request bằng cookie, session, token hoặc dữ liệu khác.

**“Session chính là cookie.”**  
Cookie là phương tiện trình duyệt lưu và gửi thông tin. Trong mô hình server-side session, cookie thường chỉ chứa Session ID; dữ liệu session nằm ở máy chủ hoặc repository.

**“Session chỉ dành cho người đã đăng nhập.”**  
Session có thể được tạo trước đăng nhập để giữ giỏ hàng, lựa chọn giao diện hoặc quy trình tạm thời.

**“Đóng trình duyệt là session trên máy chủ bị xóa ngay.”**  
Không nhất thiết. Session phía máy chủ thường được dọn theo timeout hoặc chính sách repository. Cookie phía trình duyệt và dữ liệu session có vòng đời riêng.

**“Dùng Redis là mọi cập nhật session đều an toàn khi chạy đồng thời.”**  
Redis giúp chia sẻ trạng thái, nhưng không tự làm cho chuỗi đọc-sửa-ghi của ứng dụng trở thành thao tác nguyên tử.

**“Dùng Spring Session là ứng dụng đã stateless.”**  
Ứng dụng vẫn giữ trạng thái phiên. Spring Session thay đổi cách quản lý và lưu trữ session để nhiều instance có thể dùng chung.

## 14. Tự kiểm tra

1. Vì sao hai request HTTP liên tiếp không tự động chia sẻ dữ liệu ứng dụng?
2. Session ID có vai trò gì? Vì sao không nên nhúng thông tin cá nhân vào ID?
3. Cookie session hết hạn khi đóng trình duyệt có đồng nghĩa dữ liệu session trên Redis bị xóa ngay không?
4. `getSession()` khác `getSession(false)` ở điểm nào?
5. Vì sao session trong bộ nhớ của một instance có thể gây mất trạng thái khi request được chuyển sang instance khác?
6. Spring Session giúp giải quyết vấn đề nào khi dùng Redis hoặc JDBC?
7. Vì sao một session hợp lệ vẫn không đủ để kết luận người dùng được phép truy cập một tài nguyên?
8. Hai request đồng thời cùng cập nhật một thuộc tính session có thể gây ra lỗi gì?

### Gợi ý trả lời

1. HTTP xử lý từng request/response và không quy định máy chủ tự lưu ngữ cảnh ứng dụng giữa các request.
2. Session ID giúp tìm đúng bản ghi session. ID phải khó đoán và không tiết lộ dữ liệu nghiệp vụ hoặc thông tin cá nhân.
3. Không. Cookie phía trình duyệt và TTL của session phía máy chủ được quản lý riêng.
4. `getSession()` tạo session nếu chưa có; `getSession(false)` chỉ trả về session hiện tại hoặc `null`.
5. Instance khác không có bản session nằm trong bộ nhớ cục bộ của instance đầu tiên.
6. Spring Session cung cấp cơ chế lưu và truy xuất `HttpSession` qua repository dùng chung.
7. Xác thực phiên và phân quyền tài nguyên là hai bước khác nhau; ứng dụng vẫn phải kiểm tra quyền ở phía máy chủ.
8. Có thể xảy ra lost update khi cả hai request đọc cùng giá trị cũ rồi ghi đè kết quả của nhau.

## Kết luận

HTTP cung cấp cách trao đổi request/response nhưng không tự duy trì trạng thái ứng dụng giữa các request. Session bổ sung một ngữ cảnh có thời hạn để ứng dụng nối nhiều request thành một lượt sử dụng liên tục. Trình duyệt thường gửi Session ID qua cookie, còn dữ liệu phiên được lưu ở phía máy chủ.

Trong ứng dụng Spring, `HttpSession` cung cấp API quen thuộc để làm việc với phiên. Spring Session cho phép chuyển việc lưu trữ sang repository như Redis hoặc JDBC, nhờ đó nhiều instance có thể truy cập cùng trạng thái phiên. Để cơ chế này hoạt động an toàn và ổn định, cần quản lý timeout, đăng xuất, cookie, bảo mật Session ID, dữ liệu được lưu và cập nhật đồng thời.

