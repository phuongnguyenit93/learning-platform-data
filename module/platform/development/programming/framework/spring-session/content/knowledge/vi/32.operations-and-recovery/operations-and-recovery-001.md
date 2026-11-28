# Chẩn đoán mất phiên: cookie, định danh, filter, namespace hay dữ liệu kho

Khi người dùng đăng nhập thành công nhưng request tiếp theo lại bị xem như chưa đăng nhập, nguyên nhân thường nằm ở một mắt xích trong đường đi của session: trình duyệt không gửi cookie, server không phân giải đúng session ID, filter Spring Session không chạy, ứng dụng đọc nhầm namespace hoặc bản ghi trong kho đã hết hạn/bị xóa. Chẩn đoán hiệu quả cần lần theo cùng một request từ trình duyệt qua reverse proxy và filter tới repository, sau đó xác minh dữ liệu trong Redis hoặc JDBC.

Spring Session tách session khỏi bộ nhớ của một instance. Với ứng dụng Servlet, `SessionRepositoryFilter` bọc request/response và kết nối `HttpSession` với repository. Với WebFlux, `WebSessionManager` cùng `WebSessionIdResolver` phân giải phiên theo luồng reactive. Redis/JDBC là nơi lưu trạng thái theo cấu hình; chỉ việc bật một dependency hoặc thấy cookie trong browser chưa chứng minh cả chuỗi đang hoạt động.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân loại triệu chứng mất phiên theo cookie, session ID, filter, namespace và dữ liệu store.
- Lần theo một session qua request tạo phiên và request kế tiếp.
- Kiểm tra thuộc tính cookie, domain/path, HTTPS, SameSite và reverse proxy.
- Xác minh filter hoặc WebFlux session manager thực sự được đăng ký.
- Đối chiếu namespace Redis, bảng JDBC, session ID và TTL.
- Phân biệt session không tồn tại với session tồn tại nhưng thiếu thuộc tính.
- Thu thập log/metric hữu ích mà không làm lộ session ID hoặc credential.
- Xây dựng quy trình chẩn đoán có thể lặp lại giữa các instance.

## 1. Hiểu đúng triệu chứng “mất session”

Trước khi thay đổi cấu hình, cần xác định chính xác điều gì đã mất. Các triệu chứng khác nhau thường chỉ tới những lớp khác nhau:

| Triệu chứng quan sát được | Khả năng cần kiểm tra đầu tiên |
|---|---|
| Response đăng nhập không có session cookie | Handler không tạo session, resolver/serializer không phát cookie, response bị ghi đè |
| Browser có cookie nhưng request tiếp theo không gửi | Domain, Path, Secure, SameSite, scheme, browser policy hoặc cookie bị xóa |
| Request gửi cookie nhưng server tạo session mới | Sai tên cookie, resolver không đọc cookie, filter không chạy hoặc repository không tìm thấy ID |
| Session ID được resolve nhưng repository không tìm thấy bản ghi | Namespace/prefix, backend, TTL, ID đã rotate/invalidate hoặc dữ liệu bị xóa |
| Bản ghi có tồn tại nhưng ứng dụng không đọc thuộc tính | Serialization, tên thuộc tính, session object mới, sai ứng dụng/schema hoặc thuộc tính chưa được flush |
| Chỉ một instance mất phiên | Cấu hình node không đồng nhất, khác namespace/secret/serializer, store endpoint hoặc clock |
| Mất phiên sau deploy/restart | Dùng repository cục bộ, schema/namespace thay đổi, TTL, migration hoặc rolling version không tương thích |
| Mất phiên sau login hoặc nâng quyền | Session ID rotation, cookie response không được client cập nhật, security context không được lưu |
| Mất phiên sau logout | Có thể là hành vi đúng do invalidate; kiểm tra xem client còn gửi cookie cũ hay không |

Không nên bắt đầu bằng cách tăng TTL hoặc xóa toàn bộ Redis keys. Những thao tác đó có thể che mất nguyên nhân và làm ảnh hưởng phiên của người dùng khác.

## 2. Đường đi của session cần kiểm tra

Đối với ứng dụng Servlet, luồng khái quát là:

~~~mermaid
flowchart TD
    A[Browser lưu session cookie] --> B[Browser gửi request]
    B --> C[Reverse proxy / load balancer]
    C --> D[Servlet filter chain]
    D --> E[SessionRepositoryFilter]
    E --> F[CookieSerializer đọc session ID]
    F --> G[SessionRepository tìm session]
    G --> H{Có bản ghi hợp lệ?}
    H -->|Có| I[Khôi phục HttpSession và attributes]
    H -->|Không| J[Tạo session mới khi ứng dụng yêu cầu]
    I --> K[Controller / Spring Security]
    J --> K
    K --> L[Filter lưu thay đổi cuối request]
    L --> M[Redis hoặc JDBC]
    L --> N[Response và Set-Cookie nếu cần]
~~~

Đối với WebFlux, không có Servlet filter chain như trên. WebFlux dùng `WebSessionManager`, `WebSessionIdResolver`, `WebSessionStore` và repository reactive. Vì vậy, khi ứng dụng dùng WebFlux, không chẩn đoán bằng cách tìm `SessionRepositoryFilter`; hãy xác minh bean manager, resolver và store reactive.

Trong cả hai mô hình, cookie thường chỉ mang session ID. Dữ liệu thuộc tính nằm phía server. Cookie hợp lệ nhưng bản ghi không còn tồn tại vẫn dẫn tới một session mới hoặc trạng thái rỗng.

## 3. Thu thập bằng chứng theo một request cụ thể

Chọn một luồng tái hiện đơn giản:

1. Mở một cửa sổ trình duyệt mới hoặc profile test sạch.
2. Gọi endpoint tạo session hoặc đăng nhập bằng tài khoản test.
3. Ghi lại thời điểm, host, scheme, path và response status.
4. Kiểm tra response có header `Set-Cookie` không; chỉ ghi tên cookie và các thuộc tính, không chép giá trị ID vào ticket/log.
5. Gửi request tiếp theo tới cùng ứng dụng và xác nhận cookie có nằm trong request header.
6. Ghi nhận instance xử lý request nếu có nhiều node.
7. Tìm log cùng correlation/request ID ở filter, repository và backend.
8. Kiểm tra session record bằng công cụ quản trị phù hợp, không thay đổi hoặc xóa dữ liệu.

Tốt nhất dùng một tài khoản test và một session mới. Không lấy cookie phiên của người dùng thật để chia sẻ trong chat, log hoặc ảnh chụp màn hình.

Một bảng ghi nhận ngắn giúp so sánh:

| Mốc | Cần ghi nhận |
|---|---|
| Sau login | Có Set-Cookie? Tên cookie, Domain, Path, Secure, HttpOnly, SameSite |
| Request tiếp theo | Cookie có được gửi? Host/scheme/path có khớp? |
| Ở ứng dụng | Node nào nhận request? Filter/manager có chạy? |
| Ở resolver | Có ID sau khi parse? Không ghi giá trị ID thô |
| Ở repository | Backend/namespace nào được truy cập? Tìm thấy session không? |
| Ở store | Key/row có tồn tại? TTL/expiry còn hiệu lực? |
| Sau xử lý | Thuộc tính có được tải và response có thay đổi cookie không? |

## 4. Nhánh 1: cookie không được phát trong response

Nếu login hoặc endpoint tạo session trả về response mà không có session cookie, hãy kiểm tra:

- Handler có thực sự gọi thao tác tạo/lấy session không? Trong Servlet, `request.getSession()` tạo phiên khi chưa có; `getSession(false)` thì không. Trong WebFlux, `exchange.getSession()` trả publisher và phải được nối vào reactive chain.
- Response có bị redirect, commit sớm hoặc ghi đè header bởi filter/proxy không?
- Có cấu hình cookie resolver/serializer tùy chỉnh không?
- Ứng dụng có dùng cơ chế stateless, bearer token hoặc session policy không tạo session không?
- Session có được tạo rồi invalidate ngay trong cùng request không?

Với Servlet, kiểm tra bean `CookieSerializer` nếu ứng dụng tự cấu hình Spring Session. Với WebFlux, kiểm tra `WebSessionIdResolver` và cách response cookie được ghi. Không cấu hình đồng thời nhiều resolver/serializer không tương thích.

Nếu endpoint chỉ đọc dữ liệu và không cần session, không có cookie mới có thể là hành vi đúng. Hãy xác định endpoint nào được kỳ vọng tạo session trước khi coi thiếu cookie là lỗi.

## 5. Nhánh 2: cookie có trong browser nhưng không được gửi

Mở DevTools của trình duyệt, chọn request tiếp theo và xem phần Request Headers/Cookies. Kiểm tra lý do browser loại cookie nếu DevTools cung cấp cảnh báo.

### 5.1. Domain và host

Cookie host-only chỉ được gửi tới host đã phát cookie. Nếu server phát cookie từ `app.example.com` nhưng request sau đi tới `api.example.com`, cookie host-only không được gửi sang host khác.

Thuộc tính `Domain` có thể mở rộng phạm vi tới subdomain, nhưng mở rộng không cần thiết làm tăng bề mặt tấn công. Chọn domain hẹp nhất đáp ứng kiến trúc.

### 5.2. Path

Cookie có `Path=/portal` chỉ được gửi tới path phù hợp bên dưới `/portal`. Nếu reverse proxy đổi context path hoặc ứng dụng được truy cập ở path khác, cookie có thể không được gửi.

Kiểm tra URL công khai mà browser gọi, không chỉ context path nội bộ mà ứng dụng nhìn thấy.

### 5.3. Secure và HTTPS termination

Cookie `Secure` chỉ được browser gửi qua HTTPS. Nếu người dùng truy cập HTTPS ở ngoài nhưng reverse proxy chuyển tiếp HTTP tới ứng dụng, ứng dụng có thể nhận diện sai scheme nếu forwarded headers không được xử lý đúng. Điều này có thể làm response phát cookie thiếu hoặc sai thuộc tính.

Kiểm tra:

- Browser dùng HTTPS và URL chuẩn hóa có đúng không.
- Proxy có chuyển tiếp scheme gốc bằng header được tin cậy không.
- Spring Boot có cấu hình forwarded headers phù hợp với proxy không.
- Cookie serializer có cấu hình `Secure` đúng theo môi trường public không.

Không tắt `Secure` trong production để né lỗi proxy. Sửa nhận diện scheme và cấu hình TLS termination.

### 5.4. SameSite

`SameSite=Strict` có thể khiến cookie không được gửi khi người dùng đi từ một site khác tới ứng dụng. `Lax` cho phép một số điều hướng top-level an toàn nhưng thường chặn cross-site POST và nhiều request nền. `None` cho phép cross-site cookie trong trình duyệt hỗ trợ, đồng thời yêu cầu `Secure`.

Nếu lỗi chỉ xảy ra trong iframe, SSO, redirect từ nhà cung cấp hoặc frontend khác site, kiểm tra SameSite và chính sách third-party cookie của browser. Đừng mặc định mọi trình duyệt đều cho phép cookie bên thứ ba.

### 5.5. Cookie trùng tên

Browser có thể lưu nhiều cookie cùng tên nhưng khác Domain hoặc Path. Server có thể nhận nhiều giá trị hoặc một giá trị không như mong đợi. Kiểm tra toàn bộ cookie có cùng tên và dọn cookie cũ trong profile test sau khi ghi nhận bằng chứng.

Không khuyên người dùng xóa mọi cookie như bước đầu tiên. Trước hết hãy xác định cookie nào được phát, phạm vi của nó và request nào không gửi cookie.

## 6. Nhánh 3: cookie được gửi nhưng session ID không được resolve

Nếu request có cookie, kiểm tra tên cookie mà server mong đợi:

- Spring Session Servlet thường dùng cookie tên `SESSION` theo cấu hình mặc định, nhưng có thể được đổi bằng `DefaultCookieSerializer`.
- WebFlux thường dùng cookie resolver mặc định nhưng cũng có thể đổi tên qua `CookieWebSessionIdResolver`.
- Một ứng dụng có thể dùng header hoặc resolver tùy chỉnh thay vì cookie.

Tên cookie phân biệt chữ hoa/chữ thường trong thực tế header/cookie. Cookie `JSESSIONID` của Servlet container không tự động là session ID của Spring Session. Nếu ứng dụng chuyển từ container session sang Spring Session, cần xác minh resolver và cookie name đang hoạt động.

Kiểm tra định dạng ID và resolver:

- Có khoảng trắng, dấu phân tách hoặc encoding sai do proxy/gateway?
- Có nhiều cookie cùng tên?
- Resolver có đang đọc đúng cookie/header không?
- Cookie ID có bị rotate sau login hoặc nâng quyền không?
- Client có tiếp tục gửi ID cũ sau khi server đã phát ID mới?

Không ghi ID đầy đủ vào log. Có thể dùng fingerprint một chiều hoặc hash rút gọn chỉ trong môi trường kiểm soát để đối chiếu request, nhưng phải bảo đảm không thể dùng fingerprint đó làm credential.

## 7. Nhánh 4: filter hoặc WebFlux integration không chạy

### 7.1. Ứng dụng Servlet

Với Servlet, kiểm tra:

- Dependency Spring Session phù hợp với backend đã có trong runtime.
- Auto-configuration hoặc cấu hình enable repository đã được nạp.
- Bean filter `springSessionRepositoryFilter` tồn tại và được đăng ký vào Servlet container.
- Filter chạy cho URL cần session, không bị bỏ qua bởi filter registration mapping.
- `SessionRepositoryFilter` đứng trước các filter cần sử dụng `HttpSession`, đặc biệt là Spring Security.
- Không có filter đăng ký thủ công trùng với filter auto-configured.

Spring Boot thường tự đăng ký filter khi Spring Session được cấu hình đúng. Nếu tự đăng ký bằng Servlet initializer hoặc cấu hình container, cần xác minh mapping và thứ tự. Filter có bean trong application context nhưng không được container gọi vẫn khiến session hoạt động như session cục bộ hoặc không hoạt động như mong đợi.

Nếu một endpoint dùng session container trong khi endpoint khác dùng Spring Session, kiểm tra thứ tự filter và có nhiều cơ chế session cùng tồn tại không.

### 7.2. WebFlux

WebFlux không dùng Servlet filter. Kiểm tra:

- `WebSessionManager` được cấu hình đúng.
- `WebSessionIdResolver` đọc đúng cookie/header.
- `WebSessionStore` được kết nối với repository Spring Session reactive.
- Handler trả publisher và nối các thao tác session vào reactive chain.
- Không gọi `subscribe()` tách rời rồi trả response trước khi lưu xong.
- Không dùng JDBC blocking repository như thể nó là reactive repository.

Với WebFlux, repository reactive Redis là lựa chọn phổ biến. Spring Session JDBC tiêu chuẩn hướng tới Servlet và JDBC blocking; không mặc định nó tương thích trực tiếp với WebFlux. Nếu cần database quan hệ trong WebFlux, cần giải pháp reactive như R2DBC hoặc adapter được thiết kế riêng.

## 8. Nhánh 5: namespace hoặc backend không khớp

Một session có thể được lưu thành công nhưng request tiếp theo tìm ở namespace khác. Điều này thường xuất hiện khi các node có cấu hình không đồng nhất hoặc một phiên bản triển khai đổi prefix/schema.

### 8.1. Redis namespace

Spring Session Redis dùng namespace để nhóm key của session. Namespace mặc định thường là `spring:session`, nhưng ứng dụng có thể thay đổi. Property hoặc cách cấu hình cụ thể phụ thuộc phiên bản Spring Boot/Spring Session.

Kiểm tra:

- Tất cả node có cùng Redis host/cluster, database index và namespace không?
- Một node có dùng môi trường dev/test hoặc database index khác không?
- Có cấu hình namespace riêng trong annotation/configuration không?
- Redis key của session có còn tồn tại và TTL có lớn hơn 0 không?
- Có eviction policy, cleanup job hoặc thao tác xóa key ngoài dự kiến không?

Lệnh kiểm tra chỉ đọc trong Redis CLI có thể dùng để tìm key theo prefix đã biết:

~~~text
SCAN 0 MATCH spring:session:* COUNT 100
TTL spring:session:sessions:<session-id>
~~~

Đây là ví dụ minh họa. Không dùng `KEYS *` trên Redis production lớn vì có thể chặn server. Không chạy lệnh `DEL`, `FLUSHDB` hoặc sửa hash nội bộ để “thử”. Thay `<session-id>` bằng ID test chỉ trong phiên terminal an toàn; không đưa ID người dùng thật vào log hoặc ticket.

Redis có thể lưu session record và các index/metadata liên quan. Đừng giả định một key đơn lẻ phản ánh toàn bộ trạng thái; cấu trúc phụ thuộc implementation và phiên bản. Dùng Spring Session repository/API hoặc quan sát có kiểm soát để xác nhận.

### 8.2. JDBC schema và bảng

Spring Session JDBC tiêu chuẩn dùng các bảng session và session attributes, thường có tên `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`. Tên bảng có thể được tùy chỉnh.

Kiểm tra:

- Schema Spring Session đã được tạo trong database mà ứng dụng thực sự kết nối chưa?
- Các node có cùng datasource, schema, catalog và table name không?
- User database có quyền SELECT/INSERT/UPDATE/DELETE cần thiết không?
- Có migration hoặc cleanup job xóa session ngoài ý muốn không?
- Session row còn hiệu lực theo cột expiry không?
- Bảng attributes có dữ liệu tương ứng với session row không?

Truy vấn chỉ đọc có thể bắt đầu bằng:

~~~sql
SELECT PRIMARY_ID, SESSION_ID, CREATION_TIME, LAST_ACCESS_TIME,
       MAX_INACTIVE_INTERVAL, EXPIRY_TIME
FROM SPRING_SESSION
WHERE SESSION_ID = :sessionId;
~~~

Và kiểm tra thuộc tính:

~~~sql
SELECT SESSION_PRIMARY_ID, ATTRIBUTE_NAME
FROM SPRING_SESSION_ATTRIBUTES
WHERE SESSION_PRIMARY_ID = :primaryId;
~~~

Tên cột và schema cần đối chiếu với script schema của đúng phiên bản và database. Truy vấn chỉ đọc; không chọn hoặc in giá trị attribute nhạy cảm. Dùng session ID test và bind parameter, không nối chuỗi trực tiếp.

## 9. Nhánh 6: dữ liệu không tồn tại, hết TTL hoặc đã bị invalidate

Nếu filter/resolver chạy đúng nhưng repository trả về không có session, xác minh:

1. Session đã từng được lưu chưa? Có request tạo session thành công không?
2. Request tạo session có kết thúc bình thường để repository flush không?
3. Session ID có bị đổi sau login hoặc nâng quyền không?
4. Có thao tác logout/invalidate hoặc session destruction event không?
5. TTL hoặc inactivity timeout đã hết chưa?
6. Redis eviction, cleanup job, database purge hoặc operator có xóa dữ liệu không?

Phân biệt timeout cookie và timeout session:

- Cookie `Max-Age`/`Expires` điều khiển thời gian browser giữ cookie.
- Session inactivity timeout điều khiển thời gian server/repository coi phiên là hết hạn.
- TTL ở Redis hoặc expiry record trong JDBC phản ánh chính sách lưu trữ thực tế, có thể được làm tròn hoặc dọn bất đồng bộ tùy implementation.

Cookie còn tồn tại không có nghĩa session phía server còn tồn tại. Ngược lại, session record có thể còn một thời gian trong store nhưng cookie đã bị browser xóa; server không thể liên kết request với session nếu client không gửi ID.

Nếu session đã invalidate, gửi lại cookie cũ phải không khôi phục được phiên. Đó là hành vi bảo mật đúng, không phải lỗi lưu trữ.

## 10. Session tồn tại nhưng thuộc tính bị mất

Khi repository tìm thấy session nhưng controller không đọc được thuộc tính mong đợi, hãy kiểm tra:

- Request có đang dùng đúng session ID không?
- Code có đang ghi thuộc tính vào một session mới do vô tình gọi `getSession()` không?
- Có gọi `invalidate()` hoặc đổi ID trong luồng trước không?
- Thuộc tính có được ghi trước khi response commit/flush không?
- Có exception khiến request kết thúc trước khi lưu?
- Các node có cùng serializer và class version cho object được lưu không?
- Attribute name có thay đổi về chữ hoa/thường hoặc namespace nghiệp vụ không?
- Một request đồng thời có ghi đè/xóa thuộc tính không?

Ưu tiên lưu kiểu dữ liệu đơn giản, ổn định và có thể serialize. Nếu lưu object Java, thay đổi class, package hoặc serialVersionUID có thể khiến phiên cũ không deserialize được sau deploy. Cần có chiến lược tương thích dữ liệu hoặc để session cũ hết hạn trước khi loại bỏ class cũ.

Đừng dùng session để lưu object lớn hoặc toàn bộ entity persistence. Lưu ID tham chiếu và tải dữ liệu nghiệp vụ từ nguồn có thẩm quyền khi cần.

## 11. Chẩn đoán khi chỉ một node bị lỗi

Nếu cùng một cookie lúc hoạt động, lúc mất phiên tùy request được gửi tới node nào, nghi ngờ cấu hình node không đồng nhất.

So sánh an toàn giữa các instance:

| Hạng mục | Cần đồng nhất hoặc tương thích |
|---|---|
| Session cookie | Name, Domain, Path, SameSite, Secure và resolver |
| Backend | Redis cluster/database hoặc datasource/schema |
| Namespace | Prefix Redis hoặc bảng/schema JDBC |
| Serialization | Serializer, class version và cấu hình object mapper |
| Session policy | Timeout, flush mode, save mode và security configuration |
| Filter/integration | Filter registration/order hoặc WebFlux manager/store |
| Proxy | Forwarded headers, public host, scheme và path |
| Phiên bản | Spring Boot/Spring Session và cấu trúc dữ liệu tương thích trong rolling deploy |

Sticky session có thể làm triệu chứng biến mất tạm thời vì request quay về node cũ, nhưng không sửa lỗi shared store hoặc cấu hình node. Với kiến trúc session dùng chung, mọi node cần có khả năng đọc cùng phiên.

## 12. Cây quyết định chẩn đoán nhanh

~~~mermaid
flowchart TD
    A[Người dùng báo mất phiên] --> B{Response tạo session có Set-Cookie?}
    B -->|Không| C[Kiểm tra handler, session policy, resolver và response]
    B -->|Có| D{Request kế tiếp gửi cookie?}
    D -->|Không| E[Kiểm tra Domain, Path, Secure, SameSite, HTTPS]
    D -->|Có| F{Filter hoặc WebFlux manager chạy?}
    F -->|Không| G[Kiểm tra registration, mapping, order và context]
    F -->|Có| H{Repository tìm thấy session?}
    H -->|Không| I[Kiểm tra ID, namespace, backend, TTL, invalidate]
    H -->|Có| J{Thuộc tính cần có hiện diện?}
    J -->|Không| K[Kiểm tra flush, serialization, attribute name, ghi đè]
    J -->|Có| L[Kiểm tra authorization, security context và logic ứng dụng]
    I --> M[So sánh cấu hình giữa các node]
    K --> M
~~~

Cây này giúp chọn lớp kiểm tra tiếp theo. Nó không thay thế việc thu thập request/response và log ở từng lớp; một triệu chứng có thể có nhiều nguyên nhân cùng lúc.

## 13. Log và metric để chẩn đoán mà không lộ session

Log hữu ích nên mô tả trạng thái xử lý, không ghi credential:

- Correlation ID/request ID.
- Instance ID, deployment version và route.
- Session repository type và namespace đã cấu hình (không gồm secret).
- Có cookie session hay không.
- Cookie name và resolver type.
- Session lookup result: found, missing, expired hoặc error.
- Thời gian đọc/ghi repository và lỗi backend.
- Có rotate/invalidate hay không.
- Response status và việc phát/xóa cookie.

Không ghi:

- Session ID đầy đủ.
- Giá trị cookie hoặc header Authorization.
- CSRF token, access token, refresh token.
- Nội dung attribute có thông tin cá nhân hoặc bí mật.
- Connection string chứa password.

Nếu cần tương quan một session qua nhiều log, dùng fingerprint một chiều được tạo bằng secret log riêng và rotate theo chính sách. Không dùng session ID rút gọn dễ đoán hoặc một giá trị có thể tái sử dụng như credential.

Metric có thể theo dõi:

| Metric | Điều có thể phát hiện |
|---|---|
| Session create/save/find/delete count | Tăng đột biến session mới hoặc mất session |
| Repository lookup miss rate | ID không tìm thấy hoặc namespace/backend sai |
| Redis/JDBC operation latency | Store chậm làm request timeout |
| Repository error count | Kết nối, serialization hoặc schema lỗi |
| Session expiry/cleanup count | TTL hoặc cleanup thay đổi bất thường |
| Cookie missing/invalid count | Client không gửi cookie hoặc resolver không parse được |
| Per-instance comparison | Một node có hành vi khác phần còn lại |

Đặt dashboard theo instance và phiên bản để nhận ra lỗi chỉ xảy ra sau một rollout hoặc trên một nhóm node.

## 14. Các lỗi thường gặp và cách khắc phục

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có `Set-Cookie` sau login | Session không được tạo, ứng dụng stateless hoặc resolver không phát cookie | Kiểm tra session policy và endpoint có thực sự tạo session |
| Cookie có nhưng không gửi lại | Domain/path/scheme/SameSite không khớp | Kiểm tra DevTools và public URL sau proxy |
| Cookie gửi nhưng server tạo session mới | Cookie name sai, filter không chạy hoặc repository miss | Xác minh resolver, filter order và lookup |
| Redis có key nhưng ứng dụng không tìm thấy | Namespace, database index hoặc cluster endpoint khác | So sánh cấu hình các node và prefix |
| JDBC có row nhưng session không được tải | Datasource/schema/table không giống hoặc row hết hạn | Xác minh kết nối và expiry theo schema đúng phiên bản |
| Session tồn tại nhưng attribute thiếu | Flush chưa hoàn tất, serialization lỗi hoặc code ghi nhầm session | Kiểm tra exception, serializer và thời điểm response commit |
| Chỉ node mới mất session cũ | Thay đổi namespace, serializer hoặc phiên bản không tương thích | Triển khai rolling-compatible migration |
| Mất phiên sau một khoảng thời gian cố định | Inactivity timeout hoặc store TTL | So sánh cookie lifetime, session timeout và expiry store |
| Mất phiên sau logout | Session đã bị invalidate đúng cách | Kiểm tra contract logout và client nhận cookie hết hạn |
| Mất phiên không ổn định giữa các node | Config drift hoặc backend khác nhau | So sánh fingerprint cấu hình và truy cập store từ từng node |

## 15. Quy trình xử lý sự cố theo thứ tự

Khi nhận báo cáo mất phiên, thực hiện theo thứ tự sau:

1. **Xác nhận phạm vi:** một người dùng, một browser, một endpoint, một node hay toàn cụm.
2. **Tái hiện an toàn:** dùng tài khoản test và session mới; ghi thời gian và correlation ID.
3. **Kiểm tra response:** xác nhận session cookie có được phát và thuộc tính đúng.
4. **Kiểm tra request kế tiếp:** xác nhận browser gửi đúng cookie tới đúng host/path/scheme.
5. **Kiểm tra integration:** xác nhận Servlet filter hoặc WebFlux manager/resolver chạy.
6. **Kiểm tra repository:** xác nhận lookup có đi tới đúng backend và namespace.
7. **Kiểm tra store:** xác minh key/row, TTL/expiry và attribute metadata bằng thao tác chỉ đọc.
8. **So sánh node:** kiểm tra config, version, serializer, schema và proxy headers.
9. **Kiểm tra vòng đời:** tìm rotate, invalidate, logout, timeout và cleanup event.
10. **Khắc phục có kiểm soát:** thay một yếu tố, tái hiện lại, xác minh request tiếp theo và theo dõi metric.

Không xóa Redis namespace, truncate bảng, tăng TTL toàn cục hoặc restart toàn bộ cụm trước khi biết dữ liệu nằm ở đâu và nguyên nhân là gì. Nếu cần thao tác phá hủy hoặc migration dữ liệu, phải có kế hoạch vận hành riêng và phê duyệt phù hợp.

## 16. Kiểm thử hồi quy sau khi sửa

Sau khi khắc phục, cần chứng minh toàn bộ chuỗi hoạt động:

- Tạo session mới và nhận cookie đúng thuộc tính.
- Gửi request tiếp theo với cookie và khôi phục thuộc tính.
- Gửi request tới instance khác và đọc cùng session từ shared store.
- Thay đổi thuộc tính, hoàn tất response và đọc lại ở request kế tiếp.
- Rotate ID nếu luồng xác thực yêu cầu; cookie mới phải được sử dụng.
- Invalidate/logout; ID cũ không khôi phục session.
- Đợi qua một khoảng thời gian kiểm soát để xác minh timeout theo cấu hình.
- Restart một application node và xác minh session đã lưu vẫn dùng được ở node còn lại.
- Chạy browser test cho SameSite, Secure, Domain và Path nếu thay đổi cookie policy.

Test nên kiểm tra cả trường hợp hợp lệ và lỗi: cookie thiếu, ID không tồn tại, repository timeout, store unavailable, session expired và serializer không tương thích. Không coi một lần login thành công là đủ để xác nhận lỗi đã được sửa.

## 17. Checklist vận hành

- [ ] Có thể truy vết một request từ browser tới instance và repository bằng correlation ID.
- [ ] Cookie name, Domain, Path, Secure, HttpOnly và SameSite được cấu hình tường minh.
- [ ] Reverse proxy chuyển tiếp scheme/host/path đúng và ứng dụng chỉ tin proxy đã cấu hình.
- [ ] Servlet filter hoặc WebFlux manager/store được đăng ký đúng.
- [ ] Mọi node dùng cùng backend, namespace/schema và cấu hình tương thích.
- [ ] Redis namespace hoặc JDBC schema được kiểm tra theo đúng phiên bản.
- [ ] TTL, inactivity timeout và cleanup policy được hiểu rõ.
- [ ] Serialization tương thích trong rolling deployment.
- [ ] Log không chứa session ID, cookie, token hoặc thuộc tính nhạy cảm.
- [ ] Có metric cho create, lookup miss, save, delete, expiry và store errors.
- [ ] Có test round-trip qua request tiếp theo và qua node khác.
- [ ] Có quy trình chỉ đọc để kiểm tra store trước khi thực hiện thao tác sửa dữ liệu.

Khi mất phiên, hãy lần theo chuỗi cookie → session ID → filter/resolver → repository → namespace/backend → bản ghi và TTL. Cookie không được gửi, filter không chạy, namespace không khớp và dữ liệu đã hết hạn là các lỗi khác nhau, cần bằng chứng ở đúng lớp. Chỉ sau khi xác định được mắt xích hỏng mới thay đổi cấu hình hoặc dữ liệu. Với Spring Session chạy nhiều instance, kiểm chứng cuối cùng là request tiếp theo, kể cả khi được định tuyến tới node khác, có thể khôi phục đúng phiên đã lưu.
