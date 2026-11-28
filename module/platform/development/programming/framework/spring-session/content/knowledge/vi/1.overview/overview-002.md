# Phân biệt phiên, người dùng, trạng thái đăng nhập và kết nối mạng

Khi một ứng dụng web cần nhớ người đang thao tác, rất dễ gom nhiều khái niệm khác nhau vào một chữ “session”. Trong Spring Session, cần tách bạch **người dùng**, **phiên HTTP**, **trạng thái đăng nhập** và **kết nối mạng**. Bốn khái niệm có liên quan nhưng đại diện cho bốn loại thông tin khác nhau. Hiểu đúng chúng giúp thiết kế xác thực, lưu giỏ hàng, đăng xuất và triển khai ứng dụng trên nhiều instance mà không phụ thuộc nhầm vào một kết nối hay một máy chủ cụ thể.

## 1. Vì sao cần phân biệt?

HTTP được thiết kế theo mô hình không lưu trạng thái ở cấp giao thức: mỗi request có thể được xử lý độc lập. Một request đến máy chủ không tự mang theo toàn bộ lịch sử của các request trước đó. Nếu ứng dụng cần biết request hiện tại thuộc về ai, giỏ hàng đang có gì hoặc người đó đã đăng nhập chưa, ứng dụng phải có cách liên kết các request.

Một cách phổ biến là dùng cookie chứa **session ID**. Trình duyệt gửi cookie trong các request phù hợp; máy chủ dùng ID đó để tìm dữ liệu phiên đã lưu. Spring Session cung cấp cơ chế quản lý HttpSession và lưu phiên trong một kho dữ liệu, chẳng hạn Redis hoặc JDBC. Khi nhiều instance cùng dùng một kho phiên, request tiếp theo có thể được xử lý ở instance khác mà vẫn tìm được cùng phiên.

Cơ chế này không biến người dùng, phiên, đăng nhập và kết nối mạng thành một đối tượng duy nhất. Mỗi đối tượng vẫn có vòng đời và mục đích riêng.

## 2. Bốn khái niệm cốt lõi

| Khái niệm | Đại diện cho điều gì? | Ví dụ | Điều không nên suy ra |
|---|---|---|---|
| **Người dùng (user)** | Danh tính nghiệp vụ trong hệ thống | Tài khoản có userId = 42, email và hồ sơ | Một người dùng chỉ có một phiên |
| **Phiên (HTTP session)** | Một ngữ cảnh tương tác được máy chủ duy trì qua nhiều request, thường được nhận diện bằng session ID | Phiên chứa giỏ hàng, tùy chọn giao diện và dữ liệu xác thực | Phiên chính là người dùng hoặc là kết nối TCP |
| **Trạng thái đăng nhập (login/authentication state)** | Kết quả xác thực và danh tính đã được ứng dụng chấp nhận trong một ngữ cảnh | SecurityContext có Authentication đại diện cho người dùng đã xác thực | Có session ID nghĩa là đã đăng nhập |
| **Kết nối mạng (network connection)** | Kênh truyền dữ liệu giữa client và server ở tầng mạng/vận chuyển | Một kết nối TCP có TLS, hoặc một kết nối HTTP/2 | Kết nối còn mở thì phiên còn hợp lệ; đóng kết nối thì phiên bị xóa |

### 2.1. Người dùng là danh tính nghiệp vụ

Người dùng là đối tượng mà ứng dụng nhận diện: tài khoản khách hàng, nhân viên hoặc quản trị viên. Người dùng thường có một định danh ổn định như userId, cùng các thuộc tính nghiệp vụ và quyền được cấp.

Một người dùng có thể đăng nhập từ nhiều thiết bị hoặc trình duyệt cùng lúc. Ví dụ, cùng tài khoản có thể có một phiên trên laptop, một phiên trên điện thoại và một phiên trong cửa sổ trình duyệt riêng tư. Mỗi phiên có thể có session ID, thời điểm hoạt động và vòng đời riêng.

Ngược lại, một phiên có thể được tạo trước khi người dùng đăng nhập. Ví dụ, khách truy cập thêm sản phẩm vào giỏ hàng khi chưa có tài khoản. Khi đăng nhập, ứng dụng có thể liên kết hoặc chuyển dữ liệu giỏ hàng của phiên ẩn danh sang tài khoản theo chính sách nghiệp vụ.

Vì vậy, không nên dùng session ID làm khóa người dùng, cũng không nên coi việc xóa một phiên là xóa tài khoản.

### 2.2. Phiên là ngữ cảnh được duy trì qua nhiều request

Một HTTP session là vùng trạng thái phía máy chủ gắn với một client context. Trong Servlet API, ứng dụng thường thao tác với phiên qua HttpSession:

    @GetMapping("/cart")
    public CartView getCart(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return CartView.empty();
        }

        Cart cart = (Cart) session.getAttribute("cart");
        return cart == null ? CartView.empty() : CartView.from(cart);
    }

getSession(false) chỉ lấy phiên hiện có và trả về null nếu request chưa gắn với phiên nào; nó không tự tạo phiên mới. Dùng cách này ở những endpoint chỉ cần kiểm tra phiên giúp tránh tạo session ngoài ý muốn. Nếu cần tạo phiên, ứng dụng có thể dùng request.getSession() hoặc cơ chế phù hợp với luồng nghiệp vụ.

Phiên thường được trình duyệt nhận diện qua một cookie chứa ID ngẫu nhiên, khó đoán. Cookie không nhất thiết chứa toàn bộ dữ liệu phiên. Trong mô hình Spring Session với Redis hoặc JDBC, dữ liệu được lưu ở kho phía máy chủ; cookie chủ yếu mang định danh để máy chủ tra cứu.

Session ID là thông tin nhạy cảm vì ai nắm được một ID phiên còn hiệu lực có thể có khả năng sử dụng phiên đó. Không đưa mật khẩu, thông tin cá nhân hoặc quyền hạn trực tiếp vào ID. Không tự tạo ID có thể đoán được.

### 2.3. Trạng thái đăng nhập là kết quả xác thực

Đăng nhập là quá trình xác minh thông tin xác thực, chẳng hạn mật khẩu, mã OTP hoặc một cơ chế SSO. Sau khi xác thực thành công, ứng dụng có một danh tính đã được xác thực cùng các thông tin liên quan như principal và authorities.

Trong ứng dụng Spring Security dùng xác thực dựa trên session, thông tin xác thực thường được biểu diễn qua Authentication trong SecurityContext. SecurityContext có thể được lưu và khôi phục giữa các request thông qua cơ chế lưu trữ context của Spring Security; ở cấu hình Servlet có trạng thái, HttpSession thường là nơi lưu trữ được sử dụng. Spring Session thay thế cách lưu HttpSession của container bằng repository của nó, nhờ vậy context có thể đi cùng phiên được chia sẻ giữa các instance.

Điều quan trọng là **có phiên không đồng nghĩa đã đăng nhập**. Một phiên có thể chỉ chứa giỏ hàng của khách vãng lai, hoặc tồn tại sau khi thông tin xác thực đã bị xóa. Tương tự, không nên tự kết luận người dùng đã đăng nhập chỉ vì trình duyệt gửi một cookie có tên session. Ứng dụng phải để cơ chế bảo mật xác minh phiên và trạng thái xác thực.

Cũng cần phân biệt trạng thái đăng nhập của một phiên với trạng thái tài khoản. Người dùng có thể đăng xuất khỏi điện thoại nhưng vẫn đăng nhập trên laptop. Nếu yêu cầu nghiệp vụ là khóa tài khoản hoặc thu hồi mọi phiên sau khi đổi mật khẩu, ứng dụng phải triển khai chính sách thu hồi phiên trên phạm vi tài khoản; chỉ vô hiệu hóa phiên hiện tại là chưa đủ.

Một số ứng dụng cấu hình Spring Security theo hướng stateless, chẳng hạn xác thực mỗi request bằng bearer token. Khi đó, Spring Security không cần dùng HTTP session để duy trì trạng thái đăng nhập. Ứng dụng vẫn có thể tạo HTTP session cho một mục đích khác, nhưng session đó không tự trở thành nơi lưu trạng thái xác thực.

### 2.4. Kết nối mạng là kênh vận chuyển

Kết nối TCP/TLS hoặc kết nối HTTP/2 giúp truyền request và response giữa client với server. Kết nối có thể được tái sử dụng cho nhiều request, hoặc bị đóng và thiết lập lại do timeout, chuyển mạng, proxy hay cân bằng tải.

Một phiên HTTP có thể tồn tại qua nhiều kết nối mạng. Ví dụ, người dùng đăng nhập trên điện thoại bằng Wi-Fi, tắt Wi-Fi rồi chuyển sang mạng di động. Kết nối cũ có thể mất, nhưng nếu trình duyệt vẫn gửi cookie session ID hợp lệ và phiên chưa hết hạn, request mới vẫn có thể khôi phục phiên.

Chiều ngược lại cũng đúng: một kết nối mạng còn mở không chứng minh người dùng đã đăng nhập. Một kết nối có thể truyền nhiều request với các cookie khác nhau, hoặc request không có cookie phiên. Vì vậy, không dùng trạng thái socket, địa chỉ IP hay việc kết nối còn sống để thay thế cơ chế quản lý phiên và xác thực.

## 3. Quan hệ giữa chúng trong một luồng request

Ví dụ, người dùng đã đăng nhập mở trang tài khoản. Trình duyệt gửi cookie phiên cùng request. Ứng dụng dùng session ID để tải phiên, khôi phục thông tin bảo mật, rồi kiểm tra quyền truy cập.

    Trình duyệt
       | GET /account + cookie session ID
       v
    Load balancer
       | Chuyển request đến instance A
       v
    Spring instance A
       | Tìm phiên theo session ID
       v
    Redis / JDBC
       | Trả dữ liệu phiên và SecurityContext
       v
    Spring instance A
       | Khôi phục Authentication, kiểm tra quyền
       v
    Trình duyệt nhận response

Các bước có ý nghĩa riêng:

1. **Trình duyệt gửi cookie:** cookie cho biết client đang trình ra session ID nào. Nó không tự chứng minh danh tính nếu máy chủ không xác minh phiên.
2. **Load balancer chọn instance:** request có thể đến instance A hoặc B. Việc chọn instance là quyết định định tuyến, không phải định danh phiên.
3. **Spring Session tìm phiên:** repository dùng ID để lấy dữ liệu phiên từ kho chia sẻ. Nếu phiên không tồn tại hoặc đã hết hạn, ứng dụng xử lý như không có phiên hợp lệ.
4. **Spring Security khôi phục xác thực:** trong cấu hình stateful phù hợp, context được đọc từ phiên để ứng dụng biết principal và quyền hiện tại.
5. **Ứng dụng xử lý nghiệp vụ:** kiểm tra quyền cho endpoint rồi tạo response. Kết nối mạng chỉ vận chuyển dữ liệu trong toàn bộ quá trình.

Khi request sau được chuyển đến instance B, B vẫn có thể tải cùng phiên nếu các instance được cấu hình dùng chung repository và cùng cách diễn giải dữ liệu phiên. Đây là lợi ích chính của Spring Session trong môi trường nhiều instance.

## 4. Vòng đời của phiên và trạng thái đăng nhập

Một luồng phổ biến có thể diễn ra như sau:

1. Người dùng truy cập trang công khai. Ứng dụng có thể chưa tạo phiên, hoặc tạo phiên ẩn danh để lưu giỏ hàng.
2. Người dùng gửi thông tin đăng nhập. Ứng dụng xác thực thông tin và xác định principal.
3. Sau khi xác thực thành công, ứng dụng liên kết trạng thái xác thực với phiên theo cấu hình bảo mật. Session ID cần được thay đổi hoặc xoay vòng sau xác thực để giảm nguy cơ session fixation; Spring Security có các chiến lược bảo vệ session fixation.
4. Các request tiếp theo gửi cookie phiên. Spring Session tải dữ liệu phiên, Spring Security khôi phục context, rồi ứng dụng kiểm tra quyền.
5. Khi người dùng đăng xuất, ứng dụng xóa trạng thái xác thực và vô hiệu hóa phiên theo cấu hình. Trình duyệt cũng cần xóa cookie phiên để ngừng gửi ID cũ.
6. Nếu không có hoạt động trong thời gian cấu hình, phiên hết hạn. Một request sau đó không được xem phiên cũ là phiên hợp lệ.

Cần phân biệt **thời hạn cookie** với **thời hạn phiên ở máy chủ**. Cookie có thể được cấu hình sống đến khi đóng trình duyệt hoặc có Max-Age/Expires; trong khi phiên phía máy chủ có thời gian không hoạt động tối đa (inactivity timeout) và TTL tương ứng trong repository. Hai thời hạn này có liên quan nhưng không nhất thiết bằng nhau. Xóa cookie ở trình duyệt làm client mất ID, nhưng không nhất thiết xóa ngay bản ghi phiên ở Redis hoặc JDBC. Vô hiệu hóa phiên phía máy chủ mới là bước quan trọng để thu hồi một phiên đã biết.

Spring Session quản lý vòng đời HttpSession thông qua repository. Tùy loại repository và cấu hình, dữ liệu phiên có thể được lưu trong Redis hoặc cơ sở dữ liệu quan hệ. Khi vận hành nhiều instance, các instance cần dùng chung kho phiên, namespace và cấu hình tương thích. Nếu mỗi instance dùng một kho độc lập, request chuyển sang instance khác có thể không tìm thấy phiên mà client đang trình ra.

## 5. Ví dụ: một người dùng, nhiều phiên và nhiều kết nối

Giả sử tài khoản userId = 42 đăng nhập trên hai thiết bị:

| Ngữ cảnh | Người dùng | Session ID | Trạng thái đăng nhập | Kết nối mạng |
|---|---|---|---|---|
| Laptop | 42 | S-A | Đã đăng nhập | Có thể thay đổi qua nhiều kết nối |
| Điện thoại | 42 | S-B | Đã đăng nhập | Có thể thay đổi qua nhiều kết nối |

Hai phiên cùng thuộc một người dùng nhưng có ID và vòng đời riêng. Nếu người dùng đăng xuất trên laptop, ứng dụng thường vô hiệu hóa S-A; S-B vẫn có thể hoạt động. Nếu chính sách yêu cầu đăng xuất mọi thiết bị, ứng dụng cần theo dõi các phiên theo principal và thu hồi tất cả phiên liên quan.

Một ví dụ khác: người dùng đang mở trang tài khoản thì mạng bị ngắt. Khi kết nối lại, trình duyệt gửi lại cookie S-A. Nếu phiên vẫn còn hiệu lực và chưa bị thu hồi, máy chủ có thể khôi phục phiên. Điều này cho thấy phiên không phụ thuộc vào việc giữ nguyên một kết nối TCP.

## 6. Các nhầm lẫn thường gặp và hệ quả

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
|---|---|---|
| Dùng userId làm session ID | Nhiều phiên của cùng người dùng bị nhập làm một; ID dễ lộ thông tin và khó bảo vệ | Session ID là định danh ngẫu nhiên, riêng cho từng phiên |
| Coi mọi session đều đã đăng nhập | Khách vãng lai có thể truy cập nhầm chức năng yêu cầu xác thực | Kiểm tra trạng thái xác thực bằng Spring Security và áp dụng authorization |
| Coi một user chỉ có một session | Đăng nhập thiết bị mới có thể vô tình ghi đè hoặc làm mất phiên thiết bị cũ | Thiết kế quan hệ một user đến nhiều session nếu nghiệp vụ cho phép |
| Coi session gắn với TCP connection | Mất mạng hoặc reconnect làm người dùng bị đăng xuất sai | Phiên được nhận diện bằng session ID và được lưu độc lập với kết nối |
| Chỉ xóa cookie khi logout | Bản ghi phiên phía máy chủ có thể vẫn còn hiệu lực nếu ID bị lộ ở nơi khác | Vô hiệu hóa phiên phía máy chủ và xóa cookie ở client |
| Nghĩ dùng Redis tự động làm mọi thứ an toàn | Phiên vẫn có thể bị đánh cắp, cấu hình sai hoặc truy cập trái phép | Bảo vệ cookie, ID phiên, kho dữ liệu và quyền truy cập repository |

## 7. Hệ quả khi thiết kế với Spring Session

Khi thiết kế một ứng dụng Spring Session, hãy quyết định rõ dữ liệu nào thuộc về tài khoản và dữ liệu nào chỉ thuộc về phiên. Hồ sơ, vai trò và trạng thái khóa tài khoản thường thuộc về miền người dùng. Giỏ hàng tạm thời, bước đang thực hiện trong quy trình nhiều bước hoặc lựa chọn giao diện có thể thuộc về phiên, tùy yêu cầu nghiệp vụ. Không lưu một dữ liệu dài hạn vào session chỉ vì thao tác đọc ghi thuận tiện.

Với ứng dụng chạy nhiều instance, Spring Session cho phép các instance cùng truy cập phiên qua repository dùng chung. Redis thường phù hợp khi cần truy cập nhanh và TTL; JDBC có thể phù hợp khi muốn lưu trong hệ quản trị cơ sở dữ liệu quan hệ hiện có. Lựa chọn nào cũng cần xem xét độ sẵn sàng, sao lưu, quyền truy cập, serialization, dung lượng và hành vi khi kho dữ liệu gặp sự cố.

Cookie phiên cần được bảo vệ bằng HTTPS và các thuộc tính phù hợp. Thông thường cần cân nhắc Secure để chỉ gửi qua HTTPS, HttpOnly để JavaScript phía trình duyệt không đọc được cookie, và SameSite để kiểm soát việc gửi cookie trong ngữ cảnh cross-site. Cấu hình cụ thể phụ thuộc vào kiến trúc đăng nhập, domain và luồng điều hướng. Sau khi xác thực thành công, cần đổi session ID để giảm rủi ro session fixation. Không ghi session ID vào log ứng dụng hoặc đưa nó vào URL.

Cũng cần xác định rõ phạm vi đăng xuất. Đăng xuất phiên hiện tại, đăng xuất mọi phiên của một tài khoản, khóa tài khoản và thu hồi token là các yêu cầu khác nhau. Nếu hệ thống cần giới hạn số phiên đồng thời hoặc cho phép người dùng xem và kết thúc phiên trên thiết bị khác, cần bổ sung cơ chế theo dõi phiên theo principal và xử lý đồng thời cẩn thận.

## 8. Cách kiểm tra mô hình trong thực tế

Có thể kiểm tra các phân biệt trên bằng những tình huống nhỏ:

- Gửi hai request liên tiếp với cùng cookie: nếu phiên còn hiệu lực, ứng dụng đọc được cùng dữ liệu phiên.
- Gửi request không có cookie: ứng dụng không được suy ra người dùng đã đăng nhập chỉ từ kết nối mạng.
- Tạo phiên ẩn danh có giỏ hàng: xác nhận phiên tồn tại mà chưa có trạng thái xác thực.
- Đăng nhập rồi kiểm tra session ID: xác nhận chiến lược bảo vệ session fixation được áp dụng.
- Dùng cùng cookie lần lượt gọi qua hai instance: xác nhận repository chia sẻ cho phép cả hai instance khôi phục cùng phiên.
- Đăng xuất rồi gửi lại cookie cũ: máy chủ phải từ chối phiên đã bị vô hiệu hóa.
- Đăng nhập cùng tài khoản trên hai trình duyệt: xác nhận hai phiên độc lập và kiểm tra đúng chính sách đăng xuất.
- Ngắt rồi khôi phục kết nối mạng trong khi phiên chưa hết hạn: xác nhận phiên không phụ thuộc vào kết nối TCP ban đầu.
- Chờ quá inactivity timeout rồi gửi lại cookie: xác nhận phiên hết hạn không còn được chấp nhận.

Các tình huống này giúp phân biệt lỗi ở cookie, repository, xác thực và kết nối. Khi một request thất bại, cần xác định nó không tìm thấy phiên, phiên đã hết hạn, xác thực không còn hợp lệ, thiếu quyền hay đơn giản là kết nối đến máy chủ bị lỗi. Mỗi nguyên nhân cần cách xử lý và quan sát riêng.

## Kết luận

Người dùng là danh tính nghiệp vụ; phiên là ngữ cảnh trạng thái được duy trì qua nhiều request; trạng thái đăng nhập là kết quả xác thực gắn với ngữ cảnh hoặc được xác minh theo từng request; kết nối mạng chỉ là kênh vận chuyển. Spring Session quản lý phiên Servlet và cho phép lưu phiên trong kho dùng chung như Redis hoặc JDBC, nhờ đó nhiều instance có thể xử lý các request thuộc cùng một phiên. Khi thiết kế, hãy giữ rõ ranh giới giữa bốn khái niệm này để xử lý đúng việc đăng nhập, hết hạn, đăng xuất, nhiều thiết bị và triển khai phân tán.
