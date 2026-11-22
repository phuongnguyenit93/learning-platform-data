# Phân biệt lưu trạng thái ở trình duyệt và ở máy chủ

Trong module **MODEL_VIEW_CONTROLLER**, trạng thái là thông tin giúp ứng dụng biết điều gì đang diễn ra và cần phản hồi như thế nào ở request tiếp theo. Một số trạng thái chỉ phục vụ giao diện, như tab đang mở hoặc nội dung bộ lọc chưa gửi. Một số khác có ý nghĩa nghiệp vụ, như giỏ hàng đã lưu, đơn hàng đang chờ thanh toán hoặc quyền truy cập của người dùng. Quyết định lưu trạng thái ở trình duyệt hay máy chủ ảnh hưởng đến bảo mật, tính nhất quán, khả năng mở rộng và trải nghiệm khi người dùng mở nhiều tab hoặc chuyển thiết bị.

Bài học thuộc chương **Trạng thái và vòng đời**. Trọng tâm là phân biệt trạng thái phía client và phía server, chọn nơi lưu theo vòng đời và mức độ tin cậy của dữ liệu, hiểu vai trò của cookie, session, local storage, database và cache, rồi tổ chức luồng MVC để đồng bộ trạng thái an toàn.

## 1. Trạng thái là gì trong ứng dụng web?

HTTP về cơ bản là giao thức không lưu trạng thái giữa các request: server không tự động nhớ request trước đó chỉ vì cùng một trình duyệt gửi request tiếp theo. Để xây dựng trải nghiệm liên tục, ứng dụng phải lưu thông tin cần thiết ở một nơi và xác định cách nhận diện nó khi có request mới.

Ví dụ, người dùng mở trang danh sách sách, chọn bộ lọc “Lập trình”, chuyển sang trang 2 rồi mở chi tiết một cuốn sách. Ứng dụng có thể cần giữ:

- Bộ lọc và trang hiện tại để người dùng quay lại danh sách.
- Tab đang mở trong trang chi tiết.
- Danh tính người dùng đã đăng nhập.
- Giỏ hàng hoặc lựa chọn đang chờ xác nhận.
- Trạng thái đơn hàng đã được lưu và cần hiển thị ở request tiếp theo.

Các thông tin này có vòng đời và mức độ tin cậy khác nhau. Tab đang mở thường chỉ là trạng thái giao diện tạm thời; danh tính đăng nhập cần được bảo vệ; đơn hàng là dữ liệu nghiệp vụ phải được lưu bền vững. Không nên chọn nơi lưu chỉ vì API lưu trữ nào dễ gọi nhất.

### 1.1. Hai vị trí lưu chính

**Client-side state** là trạng thái được lưu hoặc quản lý trong môi trường trình duyệt, ví dụ biến JavaScript, state của framework giao diện, URL, cookie, sessionStorage, localStorage hoặc IndexedDB.

**Server-side state** là trạng thái được lưu ở phía server, ví dụ HTTP session, database, distributed cache hoặc kho lưu trữ chuyên dụng. Trình duyệt thường giữ một mã định danh hoặc gửi dữ liệu cần thiết để server tìm đúng trạng thái.

| Tiêu chí | Client-side state | Server-side state |
|---|---|---|
| Nơi lưu | Trình duyệt hoặc thiết bị người dùng | Server, database, cache hoặc kho dùng chung |
| Quyền kiểm soát | Người dùng có thể xem, sửa hoặc xóa tùy cơ chế | Ứng dụng kiểm soát trực tiếp hơn |
| Khả năng chia sẻ giữa thiết bị | Thường không tự đồng bộ | Có thể truy cập từ nhiều thiết bị sau khi xác thực |
| Tải lên server | Có thể phải gửi lại trong request | Server đọc trạng thái từ kho lưu trữ |
| Vòng đời | Theo component, tab, origin hoặc thiết bị | Theo session, tài khoản, bản ghi hoặc chính sách lưu trữ |
| Rủi ro chính | XSS, giả mạo dữ liệu, lộ thông tin trên thiết bị | Truy cập trái phép, session hijacking, cấu hình lưu trữ và phân tán |
| Phù hợp | Trạng thái trình bày, lựa chọn tạm, dữ liệu offline có kiểm soát | Trạng thái nghiệp vụ, danh tính, quyền, tiến trình và dữ liệu dùng chung |

Hai nhóm không loại trừ nhau. Một ứng dụng MVC thường kết hợp cả hai: trình duyệt giữ trạng thái giao diện và một mã session; server giữ danh tính, giỏ hàng hoặc dữ liệu nghiệp vụ; database lưu trạng thái bền vững.

## 2. Chọn nơi lưu theo loại trạng thái

Trước khi chọn công nghệ, hãy trả lời các câu hỏi:

1. Trạng thái thuộc về ai: một component, một tab, một trình duyệt, một người dùng hay một nghiệp vụ?
2. Nó cần tồn tại bao lâu: đến khi component bị hủy, tab đóng, trình duyệt đóng, hết phiên, hay nhiều năm?
3. Có cần chia sẻ giữa tab, thiết bị hoặc người dùng không?
4. Người dùng có được phép sửa dữ liệu đó không?
5. Nếu dữ liệu bị mất hoặc bị sửa, hậu quả là gì?
6. Trạng thái có cần được khôi phục sau khi server restart hoặc người dùng đăng nhập lại không?
7. Dữ liệu có nhạy cảm hoặc cần audit không?

Một ma trận quyết định ban đầu:

| Loại trạng thái | Nơi lưu thường phù hợp | Lý do |
|---|---|---|
| Tab đang mở, modal đang hiện | Bộ nhớ UI phía client | Tạm thời, chỉ phục vụ trình bày |
| Bộ lọc có thể chia sẻ bằng liên kết | URL query string | Bookmark và gửi link được |
| Bản nháp form nhỏ, không nhạy cảm | Client memory hoặc sessionStorage | Khôi phục trong một tab hoặc phiên tab |
| Giỏ hàng đã đăng nhập | Server-side store hoặc database | Cần tồn tại qua nhiều request/thiết bị |
| Danh tính đăng nhập | Server session hoặc token theo thiết kế bảo mật | Cần xác minh ở server |
| Đơn hàng và thanh toán | Database | Dữ liệu nghiệp vụ bền vững và cần audit |
| Cache kết quả truy vấn | Cache phía server hoặc client có kiểm soát | Dữ liệu dẫn xuất, có thể tái tạo |
| Tiến độ tác vụ nền | Job store phía server | Worker và nhiều client cùng cần trạng thái chuẩn |

Không nên lưu dữ liệu nghiệp vụ có giá trị lâu dài chỉ trong localStorage. Người dùng có thể xóa dữ liệu trình duyệt, đổi thiết bị hoặc chỉnh sửa nội dung; server không thể xem đó là bản ghi có thẩm quyền.

## 3. Các phạm vi và vòng đời trạng thái phía trình duyệt

Trạng thái phía client có nhiều phạm vi. Chọn sai phạm vi thường gây lỗi như dữ liệu biến mất khi reload, bị chia sẻ ngoài ý muốn giữa tab hoặc còn tồn tại lâu hơn mong đợi.

### 3.1. Bộ nhớ của ứng dụng giao diện

State trong component hoặc biến JavaScript tồn tại trong vòng đời của trang đang chạy. Khi component unmount hoặc trang reload, trạng thái thường mất trừ khi framework hoặc ứng dụng chủ động lưu lại.

Phù hợp với:

- Modal đang mở.
- Tab đang được chọn.
- Trạng thái loading của một nút.
- Dữ liệu form chưa gửi trong phiên làm việc hiện tại.
- Kết quả tạm thời vừa nhận từ API.

Ưu điểm là truy cập nhanh và không cần serialization. Hạn chế là dữ liệu không tự tồn tại qua reload, điều hướng toàn trang hoặc đóng tab.

### 3.2. URL path và query string

URL có thể lưu trạng thái cần chia sẻ hoặc bookmark, chẳng hạn bộ lọc, trang hiện tại, sắp xếp và tab nội dung công khai:

~~~text
/books?category=programming&page=2&sort=title
~~~

URL giúp nút Back/Forward của trình duyệt hoạt động tự nhiên và cho phép người dùng gửi liên kết cho người khác. Server cũng có thể đọc query string khi render trang hoặc xử lý API.

Không đưa mật khẩu, token, thông tin cá nhân nhạy cảm hoặc dữ liệu bí mật vào URL. URL có thể xuất hiện trong lịch sử trình duyệt, log server, analytics, referrer hoặc ảnh chụp màn hình.

### 3.3. sessionStorage

**sessionStorage** lưu dữ liệu theo origin và phạm vi tab. Dữ liệu thường tồn tại khi reload trang trong cùng tab và bị xóa khi tab hoặc cửa sổ tương ứng đóng. Một tab mới thường có sessionStorage riêng; hành vi tab được mở từ tab khác có thể khởi đầu bằng bản sao trạng thái, nhưng sau đó hai tab có vùng lưu riêng.

Phù hợp với:

- Bản nháp form tạm trong một tab.
- Bước hiện tại của một wizard.
- Bộ lọc chưa cần chia sẻ giữa tab.
- Dữ liệu giao diện cần tồn tại qua reload nhưng không cần giữ lâu.

Không dùng sessionStorage làm nơi có thẩm quyền cho đơn hàng, quyền truy cập hoặc dữ liệu nghiệp vụ. Client có thể sửa dữ liệu và server phải xác thực lại mọi giá trị có ảnh hưởng đến nghiệp vụ.

### 3.4. localStorage

**localStorage** lưu dữ liệu theo origin và thường tồn tại qua reload, đóng/mở trình duyệt cho đến khi bị xóa hoặc bị trình duyệt dọn theo chính sách. Các tab cùng origin có thể truy cập cùng vùng lưu; sự kiện storage có thể thông báo thay đổi giữa các tab.

Phù hợp với:

- Tùy chọn giao diện như theme hoặc ngôn ngữ.
- Một số thiết lập cá nhân không nhạy cảm.
- Trạng thái UI có thể khôi phục khi quay lại ứng dụng.
- Cache nhỏ có thể tái tạo và có version/schema rõ ràng.

Không nên lưu session ID, refresh token hoặc dữ liệu xác thực nhạy cảm trong localStorage nếu không có thiết kế bảo mật chuyên biệt. JavaScript cùng origin có thể đọc dữ liệu này; nếu xảy ra XSS, script độc hại có thể lấy cắp chúng. Không lưu dữ liệu mà người dùng không được phép tự sửa như giá, role hoặc quyền.

### 3.5. IndexedDB

IndexedDB là kho dữ liệu bất đồng bộ phía trình duyệt, phù hợp với lượng dữ liệu có cấu trúc lớn hơn localStorage, chẳng hạn bản ghi offline, hàng đợi thao tác chờ đồng bộ hoặc dữ liệu cache có chỉ mục.

Phù hợp với ứng dụng offline-first hoặc dữ liệu cần truy vấn tại client. Tuy nhiên, dữ liệu vẫn nằm trên thiết bị người dùng: có thể bị xóa, thay đổi, không đồng bộ giữa thiết bị và cần cơ chế đồng bộ/conflict resolution. Server vẫn là nguồn có thẩm quyền cho dữ liệu nghiệp vụ cần bảo vệ.

### 3.6. Cookie

Cookie là dữ liệu nhỏ mà trình duyệt tự động gửi đến server theo domain, path, thời hạn và các thuộc tính phù hợp. Cookie thường được dùng để mang session identifier hoặc một số tùy chọn nhỏ.

Các thuộc tính quan trọng:

- **HttpOnly:** JavaScript phía trang không đọc trực tiếp được cookie.
- **Secure:** chỉ gửi cookie qua kết nối HTTPS.
- **SameSite:** kiểm soát một phần việc cookie được gửi trong ngữ cảnh cross-site.
- **Path** và **Domain:** giới hạn phạm vi gửi cookie.
- **Max-Age** hoặc **Expires:** quy định thời hạn cookie.

Cookie không phải kho dữ liệu lớn. Giới hạn kích thước và số lượng cookie phụ thuộc trình duyệt; thông thường mỗi cookie chỉ chứa vài kilobyte. Dữ liệu cookie cũng được gửi kèm request phù hợp, làm tăng kích thước request.

HttpOnly giúp giảm nguy cơ script đọc cookie, nhưng không ngăn XSS thực hiện hành động thay người dùng trong phiên hiện tại. SameSite hỗ trợ giảm CSRF nhưng cần được cấu hình cùng cơ chế CSRF phù hợp với ứng dụng.

## 4. Session phía server và vai trò của cookie

Một mô hình phổ biến là server giữ trạng thái session, còn trình duyệt chỉ giữ một session identifier trong cookie.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Server as MVC Server
    participant Session as Session Store

    User->>Browser: Đăng nhập
    Browser->>Server: POST /login
    Server->>Server: Xác thực thông tin
    Server->>Session: Tạo session và lưu userId
    Session-->>Server: sessionId
    Server-->>Browser: Set-Cookie: SESSION=sessionId
    User->>Browser: Mở trang tiếp theo
    Browser->>Server: GET /account + Cookie
    Server->>Session: Tìm sessionId
    Session-->>Server: userId và session state
    Server->>Server: Kiểm tra quyền và xử lý request
    Server-->>Browser: HTML / JSON
~~~

Cookie trong ví dụ chỉ mang mã định danh. Server dùng mã đó để tìm session và xác định người dùng. Nếu người dùng sửa một giá trị UI trong localStorage, điều đó không thay đổi userId có thẩm quyền trong session.

### 4.1. Server-side session lưu gì?

Session thường lưu thông tin nhỏ, gắn với phiên làm việc:

- ID người dùng đã xác thực.
- Thời điểm đăng nhập hoặc thông tin cần cho timeout.
- CSRF token hoặc dữ liệu bảo vệ phiên theo framework.
- Một số lựa chọn tạm thời gắn với phiên, nếu cần.
- Tham chiếu đến trạng thái workflow ngắn hạn.

Không nên biến session thành database thứ hai. Tránh lưu toàn bộ entity, danh sách lớn, dữ liệu báo cáo hoặc bản sao trạng thái nghiệp vụ lâu dài. Những dữ liệu đó khó đồng bộ, dễ lỗi thời và có thể làm session lớn.

### 4.2. Session timeout và logout

Session cần chính sách hết hạn:

- **Idle timeout:** hết hạn sau một khoảng không có hoạt động.
- **Absolute timeout:** hết hạn sau tổng thời gian tối đa, kể cả khi vẫn có request.
- **Logout:** hủy session phía server và xóa/expire cookie phía trình duyệt.
- **Thu hồi quyền:** nếu tài khoản bị khóa hoặc quyền bị thu hồi, server cần phản ánh thay đổi ở request tiếp theo theo chính sách.

Chỉ xóa cookie ở trình duyệt mà không vô hiệu hóa session phía server có thể để session cũ còn hiệu lực nếu mã định danh bị lộ. Logout nên gọi cơ chế invalidate session ở server.

### 4.3. Session fixation và đổi session ID

Sau khi đăng nhập hoặc nâng quyền, nên thay session ID theo cơ chế framework để giảm nguy cơ session fixation. Nếu kẻ tấn công biết hoặc kiểm soát được session ID trước đăng nhập, việc tiếp tục dùng cùng ID có thể làm phiên mới bị chiếm dụng.

Không tự tạo session ID bằng số tuần tự, timestamp hoặc giá trị đoán được. Dùng cơ chế session an toàn của framework và cấu hình cookie phù hợp.

## 5. Trạng thái phía server: session, database và cache

Server-side state không phải một loại duy nhất. Mỗi kho có mục đích và vòng đời riêng.

| Kho lưu trữ | Vòng đời và tính chất | Dữ liệu phù hợp |
|---|---|---|
| HTTP session | Theo phiên đăng nhập, có timeout | userId, trạng thái phiên nhỏ |
| Database | Bền vững, có transaction và ràng buộc | Tài khoản, đơn hàng, giỏ hàng đã lưu, nghiệp vụ |
| Distributed cache | Nhanh, có TTL, có thể mất hoặc bị eviction | Cache truy vấn, session phân tán, dữ liệu tạm có thể tái tạo |
| Job store | Theo vòng đời công việc, có trạng thái và tiến độ | Tác vụ nền, retry, kết quả |
| File/object storage | Theo vòng đời tệp, thường lưu nội dung lớn | Tệp xuất, ảnh, tài liệu đính kèm |

### 5.1. Database là nguồn dữ liệu nghiệp vụ có thẩm quyền

Các thay đổi như tạo đơn hàng, thanh toán, cập nhật hồ sơ hoặc cấp quyền cần được lưu ở server và thường ở database. Database có thể áp dụng transaction, unique constraint, foreign key và cơ chế khóa để bảo vệ tính toàn vẹn.

Không gửi giá trị từ browser rồi tin nó là sự thật. Ví dụ, client có thể gửi totalPrice là 1 dù tổng giá đúng là 1.000.000. Server cần tính hoặc xác minh giá dựa trên sản phẩm, chính sách và dữ liệu có thẩm quyền.

### 5.2. Cache không thay thế nguồn dữ liệu chuẩn

Cache lưu bản sao hoặc kết quả dẫn xuất để tăng tốc. Cache có thể hết hạn, bị eviction hoặc không đồng bộ với database. Vì vậy, phải biết dữ liệu nào là nguồn chuẩn và chiến lược cập nhật cache là gì.

Một số chiến lược:

- **Cache-aside:** ứng dụng đọc cache; nếu thiếu thì đọc database rồi đưa vào cache.
- **Write-through:** cập nhật cache đồng thời với ghi dữ liệu theo cơ chế được chọn.
- **TTL:** dữ liệu cache hết hạn sau một khoảng thời gian.
- **Invalidation:** xóa hoặc làm mới cache khi dữ liệu nguồn thay đổi.

Không dùng cache làm nơi duy nhất lưu dữ liệu không thể mất nếu công nghệ cache không bảo đảm độ bền tương ứng.

### 5.3. Session phân tán khi chạy nhiều server

Nếu ứng dụng chạy nhiều instance, request tiếp theo có thể đến một server khác. Nếu session chỉ nằm trong bộ nhớ của một instance, server khác có thể không tìm thấy session.

Có các lựa chọn:

- Dùng shared session store như Redis hoặc database.
- Dùng session replication do nền tảng hỗ trợ.
- Dùng sticky session ở load balancer trong một số hệ thống, nhưng cần hiểu giới hạn khi instance chết hoặc scale.
- Thiết kế API stateless với token phù hợp nếu bài toán và mô hình bảo mật cho phép.

Shared store thường giúp các instance nhìn thấy cùng trạng thái session. Tuy nhiên, vẫn cần timeout, serialization, bảo mật, xử lý lỗi store và kiểm soát cạnh tranh.

## 6. Token và trạng thái đăng nhập

Một số hệ thống dùng access token thay cho session server-side truyền thống. Với token tự chứa như JWT, server có thể xác minh chữ ký và các claim mà không cần tra session cho mọi request. Tuy nhiên, điều đó không có nghĩa ứng dụng không còn trạng thái.

Token có thời hạn; refresh token, thu hồi, đăng xuất, quyền thay đổi và phiên đăng nhập trên nhiều thiết bị vẫn cần chính sách quản lý. Một JWT đã phát hành có thể còn hợp lệ đến khi hết hạn nếu hệ thống không có cơ chế thu hồi hoặc kiểm tra trạng thái bổ sung.

Cần phân biệt:

- **Authentication credential:** bằng chứng để xác thực request.
- **Authorization data:** quyền và phạm vi được phép.
- **UI state:** trạng thái giao diện.
- **Business state:** trạng thái nghiệp vụ được lưu có thẩm quyền.

Không coi một giá trị isAdmin do client gửi là bằng chứng quyền. Với JWT, chữ ký giúp phát hiện token bị sửa nhưng payload thường không được mã hóa; không đặt bí mật vào claim. Chỉ đưa claim cần thiết, có thời hạn và audience/issuer phù hợp.

## 7. Đồng bộ trạng thái giữa trình duyệt và máy chủ

Client và server có thể giữ những bản sao khác nhau của cùng một thông tin. Điều đó tạo ra câu hỏi: bản nào có thẩm quyền và khi nào cần đồng bộ?

Ví dụ, người dùng mở form chỉnh sửa hồ sơ. Trình duyệt giữ bản nháp trong state của component; server giữ hồ sơ hiện tại trong database. Khi người dùng gửi form, server kiểm tra quyền và validation rồi lưu thay đổi. Nếu một thiết bị khác đã cập nhật hồ sơ, request cũ có thể ghi đè dữ liệu mới nếu không có cơ chế phát hiện xung đột.

### 7.1. Server là nguồn có thẩm quyền cho nghiệp vụ

Các dữ liệu sau thường phải được xác minh ở server:

- Giá, số dư, số lượng tồn kho.
- Quyền và vai trò.
- Trạng thái đơn hàng, thanh toán hoặc khoản vay.
- Chủ sở hữu của tài nguyên.
- Điều kiện nghiệp vụ phụ thuộc database.
- Tiến độ và kết quả của tác vụ nền.

Client có thể hiển thị bản sao để phản hồi nhanh, nhưng server quyết định thay đổi có hợp lệ và được chấp nhận hay không.

### 7.2. Optimistic UI và rollback

Optimistic UI cập nhật giao diện ngay khi người dùng thực hiện thao tác, trước khi server phản hồi. Cách này tạo cảm giác nhanh, nhưng cần giữ thông tin đủ để hoàn tác nếu server từ chối.

Ví dụ, người dùng đánh dấu một sách là yêu thích. UI có thể đổi biểu tượng ngay; nếu API trả lỗi, UI khôi phục trạng thái cũ và hiển thị thông báo. Với thanh toán hoặc xóa dữ liệu quan trọng, nên thận trọng hơn vì cập nhật lạc quan có thể khiến người dùng hiểu nhầm một hành động đã thành công.

### 7.3. Version và optimistic locking

Server có thể trả version hoặc ETag cho tài nguyên. Client gửi lại version khi cập nhật. Nếu tài nguyên đã thay đổi, server từ chối ghi đè và trả xung đột.

Ví dụ dùng ETag:

~~~http
GET /api/books/42
ETag: "v7"
~~~

~~~http
PUT /api/books/42
If-Match: "v7"
Content-Type: application/json

{
  "title": "Clean Code, 2nd Edition"
}
~~~

Nếu phiên bản hiện tại không còn là v7, server có thể trả 412 Precondition Failed. Client cần tải lại dữ liệu và cho người dùng xử lý xung đột thay vì tự động ghi đè.

### 7.4. Đồng bộ nhiều tab

Các tab cùng origin có thể có state giao diện khác nhau nhưng chia sẻ localStorage và cookie. Nếu một tab logout, tab khác cần phản ánh trạng thái đăng nhập đã thay đổi. Có thể dùng sự kiện storage, BroadcastChannel hoặc cơ chế cập nhật từ server để thông báo giữa các tab.

Không dựa hoàn toàn vào sự kiện client để bảo vệ session. Khi request đến server, server vẫn phải kiểm tra session/token hiện tại. Sự kiện giữa tab chỉ giúp giao diện cập nhật kịp thời.

## 8. Luồng MVC với trạng thái ở hai phía

Xét form cập nhật thông tin thành viên. View giữ nội dung đang nhập ở phía client; server lưu hồ sơ có thẩm quyền.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant View as Browser View
    participant C as MVC Controller
    participant App as Application Service
    participant DB as Database

    User->>View: Mở trang hồ sơ
    View->>C: GET /profile
    C->>App: getProfile(currentUser)
    App->>DB: Đọc hồ sơ
    DB-->>App: Profile
    App-->>C: ProfileViewModel
    C-->>View: HTML / JSON
    User->>View: Sửa tên hiển thị
    Note over View: Bản nháp nằm trong UI state
    View->>C: PUT /profile + form data + version
    C->>C: Binding và validation
    C->>App: updateProfile(command, version)
    App->>DB: Kiểm tra version và lưu
    DB-->>App: Thành công hoặc conflict
    App-->>C: Kết quả use case
    C-->>View: Response
    View->>View: Cập nhật hoặc giữ bản nháp khi lỗi
~~~

Luồng này có hai loại trạng thái:

- Bản nháp form nằm ở trình duyệt và có thể mất khi tab đóng nếu không được lưu tạm.
- Hồ sơ đã được chấp nhận nằm ở database và có thể được đọc từ nhiều thiết bị.

Nếu người dùng rời trang, ứng dụng có thể hỏi có muốn bỏ bản nháp hoặc lưu nháp vào server. Hai lựa chọn có vòng đời và quyền riêng tư khác nhau.

### 8.1. Ví dụ Controller với HttpSession

Trong Spring MVC, Controller có thể dùng HttpSession cho một số trạng thái phiên nhỏ:

~~~java
@Controller
@RequestMapping("/catalog")
public class CatalogController {
    @GetMapping
    public String showCatalog(
        @RequestParam(required = false) String category,
        HttpSession session,
        Model model
    ) {
        if (category != null && !category.isBlank()) {
            session.setAttribute("lastCategory", category);
        }

        var lastCategory = (String) session.getAttribute("lastCategory");
        model.addAttribute("selectedCategory", lastCategory);
        return "catalog/index";
    }
}
~~~

Ví dụ chỉ minh họa cách đọc/ghi một lựa chọn nhỏ trong session. Trong ứng dụng thật, cần xác định có nên lưu bộ lọc trong URL thay vì session để hỗ trợ bookmark và nhiều tab độc lập. Không lưu đối tượng nghiệp vụ lớn hoặc dữ liệu nhạy cảm không cần thiết vào session.

### 8.2. Ví dụ cookie tùy chọn giao diện

Một tùy chọn không nhạy cảm như theme có thể được lưu ở client hoặc cookie. Nếu server cần đọc nó để render HTML, cookie có thể là một lựa chọn:

~~~java
@GetMapping("/preferences")
public String preferences(
    @CookieValue(name = "theme", defaultValue = "light") String theme,
    Model model
) {
    var safeTheme = Set.of("light", "dark").contains(theme) ? theme : "light";
    model.addAttribute("theme", safeTheme);
    return "preferences/index";
}
~~~

Giá trị cookie vẫn do client gửi và có thể bị sửa. Server cần giới hạn nó vào danh sách hợp lệ và không dùng nó làm căn cứ phân quyền hoặc quyết định nghiệp vụ.

## 9. Chọn giữa cookie, sessionStorage, localStorage và server session

Các công nghệ có tên gần nhau nhưng vai trò khác nhau:

| Cơ chế | Ai đọc/ghi? | Gửi tự động trong HTTP? | Phạm vi và vòng đời | Lưu dữ liệu nhạy cảm? |
|---|---|---|---|---|
| Cookie | Trình duyệt; server gửi Set-Cookie | Có, theo domain/path/samesite | Theo thời hạn cookie | Chỉ khi thiết kế bảo mật phù hợp; session cookie thường HttpOnly, Secure |
| sessionStorage | JavaScript cùng origin | Không | Theo tab/session tab | Không nên lưu credential hoặc bí mật |
| localStorage | JavaScript cùng origin | Không | Theo origin, tồn tại đến khi xóa | Không nên lưu credential hoặc bí mật |
| IndexedDB | JavaScript cùng origin | Không | Theo origin, lưu dữ liệu có cấu trúc | Không coi là kho an toàn trước XSS hoặc người dùng thiết bị |
| Server HTTP session | Ứng dụng server | Không tự gửi; browser thường gửi cookie session ID | Theo timeout và chính sách server | Có thể lưu thông tin phiên tối thiểu ở server |
| Database | Ứng dụng server | Không | Bền vững theo chính sách dữ liệu | Có thể lưu dữ liệu nghiệp vụ với kiểm soát truy cập và mã hóa phù hợp |

Cookie và server session thường đi cùng nhau nhưng không phải một thứ. Cookie mang session ID; server session store giữ trạng thái tương ứng. localStorage và sessionStorage không tự gửi dữ liệu lên server; client phải chủ động đưa dữ liệu vào request.

## 10. Bảo mật khi lưu trạng thái

Nơi lưu trạng thái ảnh hưởng bề mặt tấn công. Cần đánh giá cả dữ liệu ở client, dữ liệu trên server và cách chúng được gửi qua mạng.

### 10.1. XSS và dữ liệu trong Web Storage

JavaScript cùng origin có thể đọc localStorage, sessionStorage và IndexedDB. Nếu ứng dụng có XSS, script độc hại có thể đọc hoặc sửa dữ liệu đó. Vì vậy:

- Không lưu access token hoặc refresh token dài hạn trong Web Storage nếu không có đánh giá bảo mật và thiết kế phù hợp.
- Escape output theo ngữ cảnh và tránh chèn HTML không tin cậy.
- Dùng Content Security Policy phù hợp để giảm rủi ro script trái phép.
- Không xem dữ liệu đọc từ Web Storage là đáng tin cậy.
- Kiểm tra dữ liệu trước khi dùng để dựng giao diện hoặc gửi lệnh nghiệp vụ.

### 10.2. CSRF và cookie

Cookie được gửi tự động trong các request phù hợp. Nếu ứng dụng dùng cookie session, một trang bên ngoài có thể cố khiến trình duyệt gửi request dưới danh nghĩa người dùng. Cần CSRF token hoặc cơ chế bảo vệ tương đương; cấu hình SameSite là một lớp hỗ trợ chứ không nên được xem là giải pháp duy nhất trong mọi kiến trúc.

### 10.3. Session hijacking

Session ID là thông tin nhạy cảm. Dùng HTTPS, cookie Secure và HttpOnly, session ID khó đoán, timeout phù hợp và đổi ID sau đăng nhập/nâng quyền. Tránh ghi session ID vào log, URL hoặc analytics.

### 10.4. Dữ liệu nhạy cảm và quyền riêng tư

Không lưu thông tin cá nhân, dữ liệu tài chính hoặc bí mật trong client storage chỉ vì thuận tiện. Nếu cần lưu bản nháp ở client, cân nhắc mã hóa không giải quyết được mọi rủi ro: khóa giải mã có thể cũng nằm ở client và dữ liệu vẫn có thể bị script cùng origin đọc khi ứng dụng đang chạy.

Ở server, giới hạn quyền đọc theo user/tenant, áp dụng retention, mã hóa khi phù hợp và chỉ lưu dữ liệu cần thiết.

### 10.5. Không tin hidden field hoặc client role

Hidden input, cookie tùy chỉnh, localStorage và dữ liệu trong URL đều có thể bị sửa. Không dùng chúng làm nguồn xác định giá, ownerId, role, số dư hoặc trạng thái được phép. Server cần lấy danh tính từ cơ chế xác thực tin cậy và kiểm tra quyền trên tài nguyên cụ thể.

## 11. Hiệu năng và khả năng mở rộng

Lưu trạng thái ở client có thể giảm số lần đọc server, nhưng làm tăng kích thước dữ liệu phía trình duyệt và yêu cầu đồng bộ. Lưu ở server giúp kiểm soát và chia sẻ tốt hơn, nhưng cần hạ tầng lưu trữ và có thể tạo tải.

Một số cân nhắc:

- Không gửi lại toàn bộ client state trong mọi request nếu chỉ cần một phần.
- Cookie được gửi tự động nên giữ nhỏ.
- Web Storage là đồng bộ đối với localStorage/sessionStorage; không dùng cho thao tác lớn gây chặn main thread.
- IndexedDB phù hợp dữ liệu client lớn hơn nhưng API bất đồng bộ và cần quản lý schema.
- Server session cần serialization và shared store nếu chạy nhiều instance.
- Database cần index, transaction và chính sách retention.
- Cache cần TTL/invalidation và xử lý cache miss.
- Trạng thái tạm cần được dọn dẹp để tránh tích lũy vô hạn.

Không tối ưu bằng cách chuyển mọi trạng thái sang client hoặc server. Hãy đo tải thực tế và chọn nơi lưu dựa trên tính chất dữ liệu.

## 12. Xử lý dữ liệu lỗi thời và xung đột

Dữ liệu trong trình duyệt có thể cũ hơn dữ liệu server. Ví dụ, người dùng mở một form lúc 9 giờ, để đó đến 11 giờ rồi gửi; trong lúc đó người khác đã cập nhật bản ghi.

Các cách xử lý:

- **Reload/refresh:** tải lại dữ liệu mới nhất trước khi chỉnh sửa hoặc khi phát hiện xung đột.
- **Optimistic locking:** gửi version hoặc ETag để server phát hiện dữ liệu cũ.
- **Field-level merge:** nếu các bên sửa các trường khác nhau, có thể hợp nhất theo chính sách.
- **Conflict UI:** cho người dùng xem bản hiện tại và bản đang chỉnh sửa rồi quyết định.
- **Last-write-wins:** chỉ dùng khi nghiệp vụ chấp nhận ghi đè theo thời điểm; không áp dụng mặc định cho dữ liệu quan trọng.

Với dữ liệu offline, cần thêm hàng đợi thao tác, idempotency key và quy tắc giải quyết xung đột khi kết nối lại. Một bản ghi lưu ở IndexedDB chưa đồng nghĩa server đã chấp nhận nó.

## 13. Xóa, hết hạn và khôi phục trạng thái

Mỗi loại trạng thái cần chính sách kết thúc:

| Trạng thái | Khi nào xóa/hết hạn? | Cách khôi phục |
|---|---|---|
| Component state | Khi component unmount hoặc trang reload | Khởi tạo lại hoặc tải từ nguồn khác |
| sessionStorage | Khi tab/session tab đóng hoặc bị xóa | Thường không khôi phục sau khi kết thúc tab |
| localStorage | Khi người dùng xóa hoặc ứng dụng chủ động xóa | Có thể khôi phục từ server nếu đã đồng bộ |
| Cookie session | Khi logout, hết hạn hoặc bị server thu hồi | Đăng nhập lại |
| Server session | Khi timeout, logout hoặc chính sách thu hồi | Tạo session mới |
| Database record | Theo vòng đời nghiệp vụ và retention | Quy trình restore/backup hoặc trạng thái archived |
| Cache entry | TTL, invalidation hoặc eviction | Tái tạo từ nguồn chuẩn |

Không dùng một thời hạn duy nhất cho mọi dữ liệu. Bản nháp form, session đăng nhập và hồ sơ nghiệp vụ có yêu cầu lưu trữ khác nhau. Chính sách retention cần phù hợp với nghiệp vụ và quyền riêng tư.

## 14. Kiểm thử trạng thái ở hai phía

Kiểm thử cần xác nhận trạng thái nằm đúng nơi, tồn tại đúng thời gian và không vượt ranh giới quyền.

### 14.1. Kiểm thử phía trình duyệt

- Component state thay đổi đúng khi người dùng tương tác.
- Reload trang có hoặc không khôi phục dữ liệu theo thiết kế.
- sessionStorage được cô lập theo tab như mong đợi.
- localStorage chia sẻ giữa tab và sự kiện cập nhật được xử lý.
- URL giữ bộ lọc khi reload và Back/Forward.
- Dữ liệu bị sửa trong Web Storage không thể thay đổi quyền hoặc dữ liệu nghiệp vụ.
- Khi storage bị chặn hoặc quota đầy, giao diện có phương án dự phòng.

### 14.2. Kiểm thử session và cookie

- Đăng nhập tạo session mới và cookie có thuộc tính phù hợp.
- Request tiếp theo nhận đúng session.
- Logout vô hiệu hóa session phía server.
- Session hết hạn được xử lý đúng.
- Session ID được đổi sau đăng nhập hoặc nâng quyền theo cấu hình.
- CSRF protection từ chối request thay đổi dữ liệu thiếu token khi cần.
- Cookie không bị gửi ngoài domain/path hoặc điều kiện SameSite dự kiến.

### 14.3. Kiểm thử database và cache

- Dữ liệu nghiệp vụ tồn tại sau khi server restart.
- Transaction rollback khi thao tác thất bại.
- Cache invalidation không làm hiển thị dữ liệu cũ quá chính sách.
- Nhiều server instance đọc được trạng thái session dùng chung.
- Request đồng thời phát hiện version conflict.
- Dữ liệu thuộc tenant khác không thể được đọc qua ID đoán được.

### 14.4. Kiểm thử tích hợp MVC

- Controller nhận session hiện tại và gọi đúng ca sử dụng.
- ViewModel được dựng từ dữ liệu server có thẩm quyền.
- Dữ liệu client gửi lên được binding và validation trước khi dùng.
- Không bind trực tiếp role, ownerId hoặc trạng thái nội bộ từ client.
- Reload, mở nhiều tab và đăng nhập trên thiết bị khác cho kết quả phù hợp với chính sách vòng đời.

## 15. Những lỗi thiết kế thường gặp

| Dấu hiệu | Hệ quả | Cách cải thiện |
|---|---|---|
| Lưu giá hoặc role trong localStorage rồi tin giá trị đó | Client có thể sửa dữ liệu và vượt quy tắc | Server tính và xác minh từ nguồn có thẩm quyền |
| Dùng localStorage cho trạng thái chỉ cần trong một tab | Dữ liệu rò giữa tab và còn lâu hơn cần thiết | Dùng component state hoặc sessionStorage |
| Lưu toàn bộ entity trong HttpSession | Session lớn, lỗi thời và khó phân tán | Lưu định danh hoặc trạng thái nhỏ; đọc dữ liệu từ database |
| Lưu session chỉ trong memory một instance | Request đến instance khác mất phiên | Shared session store hoặc thiết kế stateless phù hợp |
| Dùng cookie để lưu dữ liệu lớn | Request phình to và vượt giới hạn trình duyệt | Chỉ lưu ID hoặc tùy chọn nhỏ |
| Đưa token bí mật vào URL | Token có thể lộ qua history, log hoặc referrer | Dùng cơ chế credential phù hợp, không đặt bí mật trong URL |
| Logout chỉ xóa cookie ở client | Session phía server có thể vẫn còn hiệu lực | Invalidate session ở server và expire cookie |
| Dùng cache làm nguồn dữ liệu duy nhất | Eviction có thể làm mất trạng thái | Lưu dữ liệu cần bền vững ở database/kho phù hợp |
| Không có version khi cập nhật từ nhiều tab | Request cũ ghi đè thay đổi mới | Optimistic locking hoặc xử lý conflict |
| Dùng hidden field để xác định owner hoặc quyền | Client có thể sửa giá trị | Lấy danh tính từ session/token và kiểm tra server-side |
| Không đặt retention cho session hoặc bản nháp | Dữ liệu cũ tích lũy hoặc lộ lâu hơn cần thiết | TTL, cleanup và chính sách xóa rõ ràng |

## 16. Checklist chọn nơi lưu trạng thái

- [ ] Xác định chủ sở hữu và phạm vi của trạng thái: component, tab, browser, user hay nghiệp vụ.
- [ ] Xác định vòng đời: tạm thời, qua reload, qua session hay bền vững.
- [ ] Dữ liệu có thể bị người dùng sửa không và hậu quả nếu bị sửa là gì?
- [ ] Trạng thái có cần chia sẻ giữa tab, thiết bị hoặc server instance không?
- [ ] URL chỉ chứa thông tin không nhạy cảm và có thể chia sẻ an toàn.
- [ ] Cookie nhỏ, có Secure/HttpOnly/SameSite và thời hạn phù hợp.
- [ ] Web Storage không chứa credential hoặc dữ liệu có thẩm quyền.
- [ ] Server session chỉ giữ dữ liệu phiên nhỏ, có timeout và logout/invalidation.
- [ ] Database giữ dữ liệu nghiệp vụ cần bền vững; cache chỉ giữ dữ liệu có thể tái tạo.
- [ ] Client state được đồng bộ với server qua hợp đồng rõ và có xử lý dữ liệu cũ.
- [ ] Có kiểm soát XSS, CSRF, session fixation, quyền truy cập và tenant isolation.
- [ ] Có kiểm thử reload, nhiều tab, logout, hết hạn, xung đột và server restart.

Phân biệt trạng thái ở trình duyệt và ở máy chủ bắt đầu từ việc hiểu ai sở hữu dữ liệu, dữ liệu cần sống bao lâu và ai có quyền thay đổi nó. Trình duyệt phù hợp với trạng thái trình bày và lựa chọn tạm; server là nơi có thẩm quyền cho danh tính, quyền và nghiệp vụ; database giữ dữ liệu cần bền vững, còn cache hỗ trợ hiệu năng. Khi các ranh giới này rõ ràng, MVC có thể duy trì trải nghiệm liên tục mà vẫn bảo vệ được tính đúng đắn và an toàn của ứng dụng.
