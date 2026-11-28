# Thiết kế hành vi an toàn khi không thể đọc hoặc ghi trạng thái xác thực

Spring Session lưu trạng thái phiên ở một kho dữ liệu như Redis hoặc JDBC để nhiều instance ứng dụng có thể cùng khôi phục HttpSession và SecurityContext. Kho session vì vậy là một phần của đường xác thực. Khi Redis mất kết nối, database quá tải, timeout hoặc thao tác ghi bị lỗi, ứng dụng không thể mặc định rằng người dùng chưa đăng nhập hoặc thao tác xác thực đã được lưu.

Thiết kế an toàn cần phân biệt ba tình huống:

- **Session không tồn tại hoặc đã hết hạn:** repository hoạt động bình thường nhưng không tìm thấy session tương ứng. Đây thường là request anonymous hoặc cần xác thực lại.
- **Không thể đọc session:** repository không trả được kết quả vì lỗi hạ tầng. Trạng thái xác thực chưa biết; không được coi lỗi này là session không tồn tại.
- **Không thể ghi hoặc xóa session:** ứng dụng không xác nhận được trạng thái mới đã được lưu hoặc thu hồi. Không được báo đăng nhập, cập nhật quyền hay đăng xuất mọi thiết bị thành công khi thao tác bắt buộc chưa được xác nhận.

Bài học này tập trung vào cách fail-closed cho các thao tác cần trạng thái xác thực, cách xử lý lỗi đọc/ghi/xóa session, thiết kế timeout và retry, giới hạn tác động khi kho session gặp sự cố, cùng kiểm thử fault injection trong hệ thống nhiều instance.

## 1. Kho session nằm trên đường xác thực

Trong ứng dụng Servlet, Spring Security thường lưu SecurityContext trong HttpSession. Spring Session thay nơi lưu session mặc định của container bằng repository dùng chung. Một request đã có cookie session ID thường đi qua các bước:

1. SessionRepositoryFilter đọc session ID bằng HttpSessionIdResolver.
2. Filter yêu cầu repository tải session từ Redis/JDBC.
3. Spring Security khôi phục SecurityContext từ session.
4. Authorization kiểm tra Authentication và authorities.
5. Khi request thay đổi session, Spring Session lưu thay đổi theo flush/save mode.
6. Response được hoàn tất theo lifecycle của filter và session repository.

~~~mermaid
flowchart TD
    A[HTTP request + session cookie] --> B[SessionRepositoryFilter]
    B --> C{Đọc repository được?}
    C -->|Có| D{Session tồn tại và còn hạn?}
    C -->|Không: timeout/lỗi store| X[Không xác định được trạng thái xác thực]
    D -->|Không| G[Anonymous hoặc yêu cầu đăng nhập]
    D -->|Có| E[Khôi phục SecurityContext]
    E --> F[Spring Security authorization]
    F --> H[Controller / service]
    H --> I{Có thay đổi session?}
    I -->|Có| J[Lưu session]
    J --> K{Ghi được xác nhận?}
    K -->|Có| L[Hoàn tất response]
    K -->|Không| Y[Không xác nhận thao tác thành công]
    I -->|Không| L
    X --> Z[Fail closed cho route cần xác thực]
~~~

Nếu kho session không khả dụng, ứng dụng không thể biết cookie đang trỏ tới một session hợp lệ hay không. Việc tự coi lỗi kết nối là “không có session” có thể che giấu outage, làm mất thông tin xác thực và dẫn tới hành vi không nhất quán giữa các node.

## 2. Phân biệt session miss với repository failure

Đây là phân biệt quan trọng nhất khi thiết kế xử lý lỗi:

| Tình huống | Kết quả có ý nghĩa | Hành vi phù hợp |
| --- | --- | --- |
| Không có cookie session | Request không mang session ID | Tạo session mới khi cần; route bảo vệ yêu cầu đăng nhập |
| Cookie chứa ID không còn tồn tại | Repository đọc thành công nhưng không tìm thấy session | Coi là chưa xác thực; yêu cầu đăng nhập nếu route cần |
| Session hết hạn | Repository hoặc expiration logic xác định phiên không còn hiệu lực | Không khôi phục Authentication cũ |
| Redis/JDBC timeout khi đọc | Không biết session có tồn tại hay không | Báo trạng thái dịch vụ không khả dụng cho route phụ thuộc xác thực |
| Lỗi deserialize session | Không khôi phục được trạng thái đáng tin cậy | Fail closed, ghi nhận lỗi tương thích dữ liệu |
| Lỗi khi save session | Không xác nhận được trạng thái mới đã được lưu | Không báo thao tác cần lưu session thành công |
| Lỗi khi delete/invalidate | Không xác nhận được phiên đã bị thu hồi | Không tuyên bố logout/revoke đã hoàn tất |

findById trả về rỗng khi session không tồn tại khác với việc lời gọi repository kết thúc bằng exception. Tương tự, một session bị xóa do TTL không giống một lần đọc Redis bị timeout.

Không bắt mọi exception rồi chuyển thành Optional.empty(), Mono.empty() hoặc anonymous Authentication. Cách đó biến lỗi hạ tầng thành kết quả nghiệp vụ sai và làm cho monitoring không thể nhận biết outage.

## 3. Nguyên tắc fail-closed cho trạng thái xác thực

Fail-closed nghĩa là khi không thể xác minh trạng thái cần thiết, ứng dụng từ chối thao tác được bảo vệ. Với Spring Session, nếu không đọc được session store thì ứng dụng không thể chứng minh request hiện tại có Authentication hợp lệ.

Áp dụng nguyên tắc:

- Route cần đăng nhập không được cho phép tiếp tục chỉ vì session store lỗi.
- Route công khai có thể tiếp tục nếu thực sự không phụ thuộc session hoặc dữ liệu cá nhân hóa.
- Không thay repository dùng chung bằng một session local tạm thời.
- Không dùng Authentication cũ trong cache không có cơ chế kiểm tra hiệu lực nếu chính sách yêu cầu thu hồi ngay.
- Không trả thành công cho thao tác tạo session hoặc cập nhật trạng thái xác thực khi write chưa được xác nhận.
- Không tuyên bố logout/revoke hoàn tất khi delete chưa được xác nhận.

Fail-closed không có nghĩa mọi endpoint của ứng dụng đều phải dừng. Một trang trợ giúp công khai hoặc endpoint health không cần trạng thái đăng nhập có thể vẫn phục vụ. Nhưng endpoint xem hồ sơ, thực hiện thanh toán, quản trị hoặc lấy dữ liệu riêng tư phải từ chối nếu không thể xác minh Authentication.

### 3.1. Không biến lỗi store thành anonymous một cách âm thầm

Nếu cookie hợp lệ được gửi lên nhưng Redis không truy cập được, request không thể được phân loại là anonymous một cách đáng tin cậy. Trả trang đăng nhập như thể session hết hạn có thể gây nhầm lẫn cho người dùng và che giấu sự cố hạ tầng.

Nên phân biệt response:

- 401 Unauthorized: không có Authentication hợp lệ hoặc thông tin xác thực không hợp lệ trong điều kiện hệ thống hoạt động bình thường.
- 403 Forbidden: đã xác thực nhưng không có quyền cho thao tác.
- 503 Service Unavailable: không thể truy cập kho trạng thái xác thực cần thiết để quyết định request.

Ứng dụng có thể chọn trang lỗi hoặc response API khác theo giao diện, nhưng cần giữ khác biệt về ý nghĩa. Không trả thông tin chi tiết về hostname Redis, SQL, credential hoặc stack trace cho client.

## 4. Hành vi khi không thể đọc session

Lỗi đọc có thể xuất hiện ở nhiều giai đoạn:

- Lấy connection từ pool thất bại.
- DNS, network, TLS hoặc firewall làm kết nối tới Redis/database lỗi.
- Redis failover hoặc database failover đang diễn ra.
- Lệnh đọc timeout.
- Dữ liệu session không tương thích serializer.
- Database deadlock hoặc lỗi truy vấn.

Khi lỗi xảy ra trước khi controller được gọi, ứng dụng cần có xử lý ở đúng tầng filter/servlet container. ControllerAdvice chỉ xử lý các exception đi qua Spring MVC dispatcher; nó không bảo đảm bắt được exception phát sinh trước controller trong SessionRepositoryFilter hoặc Spring Security filter chain.

Một cách triển khai là có error handling ở tầng servlet filter/container bao quanh filter xử lý session và security, hoặc cấu hình error dispatch phù hợp. Filter xử lý lỗi cần kiểm tra response chưa commit trước khi đặt status/body. Nếu response đã commit, không thể thay status; chỉ có thể kết thúc xử lý và ghi nhận lỗi nội bộ.

Không viết một catch Exception rộng rồi trả 401. Chỉ nhận diện các lỗi repository/data access đã được phân loại là lỗi hạ tầng; lỗi lập trình hoặc lỗi không xác định cần đi theo cơ chế xử lý lỗi chung và được quan sát riêng.

Ví dụ response body khi lỗi kho session:

~~~json
{
  "type": "about:blank",
  "title": "Session service unavailable",
  "status": 503,
  "detail": "Trạng thái xác thực tạm thời không khả dụng. Vui lòng thử lại sau."
}
~~~

Response không chứa session ID, cookie, SQL statement, Redis endpoint, credential hoặc exception message nội bộ. Có thể gửi Retry-After nếu hệ thống có ước lượng thời gian phục hồi phù hợp.

## 5. Hành vi khi không thể tạo hoặc ghi session

Đăng nhập thành công về mặt kiểm tra mật khẩu chưa đồng nghĩa người dùng đã có một session có thể dùng ở request tiếp theo. Sau xác thực, Spring Security và Spring Session phải lưu SecurityContext/session và gửi cookie tương ứng.

Nếu save thất bại:

- Không trả response như thể login hoàn tất bình thường.
- Không gửi cookie chứa session ID mà server chưa xác nhận có thể khôi phục.
- Không lưu Authentication vào local memory để “cứu” request tiếp theo.
- Trả lỗi dịch vụ tạm thời, thường là 503, và ghi nhận nguyên nhân nội bộ.
- Nếu write timeout không rõ kết quả, xem trạng thái là không xác định; session có thể đã được ghi ở server nhưng acknowledgement bị mất.

Một write timeout là trường hợp đặc biệt: client không nhận được xác nhận không có nghĩa Redis chắc chắn chưa ghi. Session có thể đã được lưu nhưng response/cookie chưa đến browser. Nếu repository dùng session ID ngẫu nhiên và TTL hữu hạn, entry mồ côi có thể tự hết hạn; không phát lại session ID cho client nếu ứng dụng không thể xác nhận trạng thái.

Với cập nhật thuộc tính session trong một request, response chỉ nên báo thành công sau khi lifecycle lưu session đã hoàn tất theo contract của repository và cấu hình flush mode. Spring Session có thể lưu ở thời điểm cuối request hoặc theo chế độ ghi ngay; hiểu rõ cấu hình đang dùng. Không gọi subscribe rời hoặc trả response trước một thao tác save mà nghiệp vụ phụ thuộc.

## 6. Hành vi khi không thể xóa hoặc invalidate session

Logout và revoke session cũng là thao tác ghi/xóa vào kho session. Nếu repository không thể xóa:

- Không tuyên bố session đã bị thu hồi.
- Không cho rằng xóa cookie ở browser đủ để thu hồi server-side session.
- Không fallback sang xóa một bản session local trong khi Redis/JDBC vẫn giữ phiên.
- Ghi nhận revoke chưa hoàn tất và thực hiện retry/đối soát theo chính sách.
- Với tài khoản bị khóa hoặc có rủi ro, dùng trạng thái tài khoản/security version độc lập để từ chối request nhạy cảm trong thời gian session chưa xóa được.

Xóa cookie ở client có thể giảm việc browser tiếp tục gửi cookie, nhưng cookie đã bị sao chép vẫn có thể được dùng nếu session còn trong repository. Vì vậy, cookie clearing không thay thế server-side invalidation.

Nếu thao tác logout hiện tại không thể invalidate session do store outage, không thể khẳng định request sau sẽ bị từ chối trên mọi node. Có thể trả lỗi dịch vụ không khả dụng và giải thích rằng thao tác đăng xuất chưa được xác nhận. Với chính sách bảo mật cao, cần có cơ chế account-level revocation hoặc security epoch được kiểm tra bởi mọi node và không phụ thuộc vào cùng session store đang lỗi.

## 7. Không fallback sang session local

Một anti-pattern là khi Redis lỗi, mỗi instance tự tạo session local để người dùng vẫn tiếp tục làm việc. Điều này phá vỡ giả định session dùng chung:

1. Người dùng gửi request đầu tới A; A tạo session local.
2. Request tiếp theo đến B; B không có session của A và tạo session khác.
3. Logout ở A không xóa được session local của B.
4. Khi Redis phục hồi, local session không tự hợp nhất với dữ liệu dùng chung.
5. Quyền và trạng thái xác thực có thể khác nhau giữa các node.

Fallback local làm tăng nguy cơ session fixation, stale authorization và không thể thu hồi tập trung. Nó cũng khiến hành vi ứng dụng phụ thuộc node mà load balancer chọn.

Nếu cần một chế độ degraded operation, hãy thiết kế rõ route nào có thể hoạt động mà không cần session. Ví dụ, trang thông tin công khai hoặc tác vụ đọc dữ liệu công khai có thể tiếp tục. Các route cần xác thực phải từ chối khi không thể xác minh session.

## 8. Retry, timeout, circuit breaker và bulkhead

Khi session store chậm hoặc mất kết nối, retry vô hạn có thể làm tình hình tệ hơn. Mỗi request giữ thread, connection hoặc tài nguyên chờ đợi; nhiều node retry đồng thời có thể tạo retry storm.

Thiết kế nên có:

- **Timeout ngắn và có giới hạn:** giới hạn thời gian chờ lệnh Redis/JDBC và connection acquisition.
- **Retry có chọn lọc:** chỉ retry lỗi tạm thời và thao tác có thể retry an toàn.
- **Backoff và jitter:** tránh tất cả instance retry cùng thời điểm.
- **Circuit breaker:** khi lỗi vượt ngưỡng, ngừng gửi request dồn dập tới store và trả lỗi nhanh.
- **Bulkhead/connection pool limit:** ngăn session store chiếm hết tài nguyên xử lý request.
- **Giới hạn hàng đợi:** tránh tích tụ request chờ vô hạn.

Không retry lỗi serialization, cấu hình sai, schema không tương thích hoặc authentication failure như thể chúng là lỗi mạng tạm thời.

Với thao tác save cùng session ID, retry có thể an toàn hơn thao tác có side effect ngoài session, nhưng vẫn cần hiểu timeout ambiguity và semantics của repository. Không retry một thao tác tạo session mới nếu mỗi lần retry sinh ID khác mà không có cơ chế dọn entry trước đó.

Ví dụ cấu hình timeout cần được đặt theo client và pool đang dùng:

~~~yaml
spring:
  data:
    redis:
      timeout: 2s
      connect-timeout: 1s
~~~

Đây chỉ là ví dụ tên property theo một số dòng Spring Boot; kiểm tra đúng phiên bản và Redis client. JDBC cần cấu hình connection pool, query timeout và transaction timeout riêng.

## 9. Circuit breaker không được mở cửa cho route bảo vệ

Circuit breaker có thể chuyển sang open state khi store lỗi liên tục. Khi đó, thao tác đọc session sẽ bị từ chối nhanh thay vì chờ timeout cho từng request.

Đối với route yêu cầu Authentication, circuit breaker open phải dẫn tới trạng thái không thể xác minh xác thực và route cần bị từ chối. Không cấu hình fallback trả true, tạo principal mặc định hoặc dùng session cache cũ vô thời hạn.

Fallback hợp lệ có thể là:

- Response 503 với thông báo chung.
- Trang bảo trì công khai.
- Endpoint health/readiness báo ứng dụng không sẵn sàng nhận traffic xác thực.
- Chỉ tiếp tục các route đã được thiết kế rõ ràng là public và không dùng trạng thái session.

Circuit breaker không phải nơi quyết định quyền. Authorization vẫn phải fail-closed khi dữ liệu xác thực không thể đọc.

## 10. Cache Authentication và nguy cơ stale state

Một số ứng dụng cache user details, authorities hoặc security version để giảm truy vấn. Cache có thể giúp ứng dụng tiếp tục xử lý một số dữ liệu khi database chậm, nhưng không được dùng như bản thay thế vô thời hạn cho session repository.

Các rủi ro:

- Cache giữ role cũ sau khi quản trị viên thu hồi quyền.
- Cache giữ account enabled sau khi tài khoản bị khóa.
- Node A đã nhận invalidation nhưng node B chưa nhận.
- TTL cache dài hơn thời gian mà chính sách cho phép quyền cũ tồn tại.
- Khi store outage, fallback đọc cache không phân biệt dữ liệu còn hiệu lực hay đã stale.

Nếu nghiệp vụ cho phép stale read trong một khoảng thời gian xác định, phải đặt giới hạn TTL, cơ chế invalidation và xác định route nào được phép dùng dữ liệu cache. Với thanh toán, quản trị, dữ liệu nhạy cảm hoặc thao tác không thể đảo ngược, kiểm tra trạng thái hiện tại từ nguồn đáng tin cậy hoặc từ security version có consistency phù hợp.

Không cache toàn bộ SecurityContext ở local memory để tiếp tục cho phép request đã xác thực khi session store không khả dụng, trừ khi có một kiến trúc xác thực khác được thiết kế và đánh giá riêng.

## 11. Security version để hỗ trợ thu hồi độc lập

Khi cần chặn session cũ ngay cả lúc session repository lỗi, có thể lưu một securityVersion hoặc credentialVersion trong bản ghi tài khoản ở nguồn dữ liệu độc lập:

~~~text
Account:
  principal = alice
  enabled = true
  securityVersion = 42

Session:
  principal = alice
  securityVersion = 42
~~~

Khi khóa tài khoản, đổi mật khẩu hoặc thu hồi quyền quan trọng, tăng version trong nguồn dữ liệu chính. Mỗi request nhạy cảm so sánh version trong session với version hiện tại:

~~~java
if (!account.isEnabled()
        || sessionSecurityVersion != account.getSecurityVersion()) {
    throw new ReauthenticationRequiredException();
}
~~~

Đoạn code chỉ minh họa quy tắc; cần xử lý kiểu dữ liệu, null, cache, transaction và cách lấy session version theo mô hình thực tế.

Nếu nguồn version cũng không truy cập được, không thể xác nhận phiên còn hợp lệ; route nhạy cảm vẫn phải fail-closed. Nếu cache version được dùng, TTL và invalidation phải phù hợp với mục tiêu thu hồi. Security version giúp tách một phần kiểm soát thu hồi khỏi session store, nhưng không tự giải quyết mọi outage.

## 12. Phân biệt lỗi xác thực và lỗi hạ tầng

Không dùng cùng một response cho tất cả tình huống:

| Tình huống | HTTP semantics thường phù hợp | Ghi nhận nội bộ |
| --- | --- | --- |
| Sai mật khẩu | 401 hoặc luồng login failure | Authentication failure |
| Không có session trên route bảo vệ | 401 hoặc redirect login | Anonymous request |
| Đã xác thực nhưng thiếu quyền | 403 | Authorization denied |
| Session repository timeout | 503 | Store unavailable/timeout |
| Lỗi deserialize session | 503 hoặc lỗi dịch vụ được phân loại | Serialization incompatibility |
| Save session thất bại khi login | 503 | Session persistence failure |
| Delete session thất bại khi logout-all | 503 hoặc trạng thái pending có tracking | Revocation incomplete |

Response bên ngoài nên ngắn gọn và không tiết lộ hạ tầng. Log nội bộ nên có correlation ID, node ID, thao tác read/write/delete, loại lỗi và thời gian. Không log session ID, cookie, token, password hoặc nội dung SecurityContext.

## 13. Xử lý lỗi ở filter chain

Một số lỗi xảy ra trước khi controller chạy, do đó ControllerAdvice không phải cơ chế duy nhất. Cần hiểu thứ tự filter:

- SessionRepositoryFilter phải bọc request để Spring Security làm việc với session do Spring Session quản lý.
- Bộ xử lý lỗi cần nằm ở vị trí có thể quan sát exception từ session filter và security filter.
- Nếu exception xảy ra sau khi response commit, không thể thay response thành 503.
- Nếu lỗi được ném trong async dispatch, cần xử lý đúng async lifecycle.

Có thể dùng servlet error mapping hoặc filter chuyên biệt được đặt đúng thứ tự để chuyển lỗi session-store đã phân loại thành response 503. Cấu hình order phải được kiểm tra với filter registration thực tế của Spring Boot/Spring Session; không sao chép một số Order cố định mà không xác minh.

Ví dụ pseudocode cho lớp xử lý lỗi ngoài filter chain:

~~~java
try {
    filterChain.doFilter(request, response);
}
catch (SessionStoreUnavailableException ex) {
    if (!response.isCommitted()) {
        response.resetBuffer();
        response.setStatus(HttpServletResponse.SC_SERVICE_UNAVAILABLE);
        response.setContentType("application/problem+json");
        response.getWriter().write(
            "{\"title\":\"Session service unavailable\",\"status\":503}");
    }
    else {
        throw ex;
    }
}
~~~

SessionStoreUnavailableException là exception do ứng dụng định nghĩa sau khi phân loại lỗi repository; không phải class mặc định của Spring Session. Pseudocode cần được đặt trong filter wrapper có thứ tự phù hợp và bổ sung logging/async handling trong implementation thực tế.

## 14. Hành vi cho từng nghiệp vụ quan trọng

### 14.1. Login

- Nếu credential sai trong khi identity store hoạt động: trả lỗi xác thực thông thường.
- Nếu credential hợp lệ nhưng không lưu được session: không tạo trạng thái đăng nhập cục bộ; trả lỗi dịch vụ tạm thời.
- Chỉ phát cookie session sau khi session được lưu theo contract của repository.
- Với write timeout không rõ kết quả, không gửi cookie và để entry không được sử dụng hết hạn theo TTL hoặc cleanup.

### 14.2. Request đã đăng nhập

- Nếu session đọc thành công: tiếp tục authentication/authorization bình thường.
- Nếu session không tồn tại hoặc hết hạn: xử lý như anonymous.
- Nếu store không thể đọc: từ chối route cần xác thực với lỗi dịch vụ; không biến thành anonymous âm thầm.

### 14.3. Thay đổi quyền hoặc thuộc tính xác thực

- Ghi thay đổi vào nguồn dữ liệu chính.
- Lưu security version hoặc session state theo chính sách.
- Chỉ trả thành công khi các ghi bắt buộc đã được xác nhận.
- Nếu một phần commit thành công còn phần khác thất bại, ghi nhận trạng thái chưa hoàn tất và có quy trình đối soát.

### 14.4. Logout và revoke-all

- Invalidate/delete session ở repository dùng chung.
- Xóa cookie phía client theo resolver nhưng không coi đây là bằng chứng server-side delete đã thành công.
- Nếu delete thất bại, không báo revoke hoàn tất.
- Với account compromise, khóa account hoặc tăng security version qua nguồn độc lập để chặn request mới trong khi retry revoke.

### 14.5. Public route và health check

- Public route không phụ thuộc session có thể tiếp tục phục vụ.
- Route cá nhân hóa không được âm thầm trả dữ liệu của anonymous user nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.
- Liveness có thể vẫn pass nếu process còn sống.
- Readiness nên báo không sẵn sàng cho traffic cần session khi store bắt buộc không khả dụng, theo cách tích hợp health indicator của ứng dụng.

## 15. Health check và readiness

Không nên chỉ kiểm tra process còn chạy để kết luận ứng dụng sẵn sàng phục vụ authentication. Với session store là dependency bắt buộc, readiness cần phản ánh khả năng truy cập dependency theo chính sách.

Phân biệt:

- **Liveness:** JVM/process còn hoạt động và không cần restart.
- **Readiness:** instance có thể nhận loại traffic được phân công.
- **Dependency health:** Redis/JDBC có thể thực hiện thao tác cần thiết hay không.

Nếu Redis tạm thời lỗi, liveness có thể vẫn healthy để tránh orchestrator restart liên tục. Readiness có thể chuyển trạng thái không sẵn sàng để load balancer ngừng gửi request cần session. Nếu ứng dụng có route public độc lập, có thể cần health/routing policy chi tiết hơn thay vì đưa toàn bộ process ra khỏi traffic.

Health check không nên tạo session thật hoặc ghi dữ liệu xác thực của người dùng. Dùng health indicator hoặc thao tác nhẹ, timeout ngắn và không gây tải lớn lên store.

## 16. Quan sát lỗi session store

Nên theo dõi tối thiểu:

| Chỉ số | Điều cần phát hiện |
| --- | --- |
| Session read latency | Redis/JDBC chậm trước khi request bị timeout |
| Session read errors | Không thể khôi phục Authentication |
| Session save errors | Login hoặc thay đổi session không được lưu |
| Session delete errors | Logout/revoke chưa hoàn tất |
| Connection pool exhaustion | Không lấy được connection dù store có thể còn sống |
| Circuit breaker state | Store bị cô lập sau lỗi liên tiếp |
| Retry count | Phát hiện retry storm hoặc dependency chập chờn |
| 503 do session store | Ảnh hưởng thực tế tới route cần xác thực |
| Serialization failures | Node không tương thích dữ liệu session |
| Revoke backlog | Các lệnh thu hồi còn chờ xử lý |

Gắn metric với operation và node, không gắn với session ID hoặc username. Log dùng correlation ID để nối request và lỗi store. Cảnh báo nên phân biệt read failure, write failure, delete failure và circuit open vì tác động nghiệp vụ khác nhau.

## 17. Kiểm thử fault injection

Unit test mock repository có thể xác minh code xử lý exception, nhưng không chứng minh timeout, connection pool hoặc failover thực tế. Nên có integration test với Redis/JDBC test instance và fault injection.

Các kịch bản:

1. **Read timeout:** đăng nhập trước, sau đó làm Redis/JDBC không truy cập được; request với cookie cũ phải không vào controller bảo vệ và không bị coi là session miss bình thường.
2. **Session miss bình thường:** xóa một session khi store vẫn hoạt động; request phải được coi là anonymous, khác response/metric với outage.
3. **Login save failure:** credential hợp lệ nhưng repository write lỗi; response không báo login thành công và không phát cookie có thể dùng.
4. **Write timeout không rõ kết quả:** mô phỏng client timeout sau khi server có thể đã nhận lệnh; xác nhận ứng dụng không gửi cookie hoặc báo thành công giả.
5. **Logout delete failure:** repository không xóa được; API không tuyên bố logout-all đã hoàn tất và ghi nhận revoke pending/failure.
6. **Recovery:** khôi phục store; request mới có thể đọc session đã được lưu hợp lệ, còn các revoke pending được xử lý theo chính sách.
7. **Circuit breaker open:** route bảo vệ trả lỗi nhanh, không dùng Authentication cache cũ; route public độc lập vẫn hoạt động nếu thiết kế cho phép.
8. **Nhiều instance:** node A và B cùng dùng repository; outage/recovery được quan sát nhất quán và không có fallback local.
9. **Serializer mismatch:** node không đọc được session do phiên bản khác; lỗi được phân loại, không chuyển thành anonymous âm thầm.
10. **Readiness:** dependency session store lỗi làm readiness phản ánh đúng khả năng phục vụ authentication, trong khi liveness không gây restart loop.
11. **Security version:** session version cũ bị từ chối khi account version đổi; nếu version store cũng lỗi thì route nhạy cảm vẫn fail-closed.
12. **Không rò rỉ dữ liệu:** response/log không chứa cookie, session ID, token, credential hoặc stack trace.

Dùng test container, network fault proxy hoặc cơ chế dừng/khởi động service test để tạo lỗi có kiểm soát. Dùng timeout có giới hạn, latch hoặc polling; tránh Thread.sleep dài và test phụ thuộc vào timing ngẫu nhiên.

## 18. Những lỗi thiết kế thường gặp

- **Chuyển mọi lỗi repository thành session rỗng:** biến outage thành anonymous và che giấu lỗi xác thực.
- **Fail-open cho route bảo vệ:** request tiếp tục khi không thể xác minh Authentication.
- **Fallback sang session local:** tạo trạng thái khác nhau giữa các instance và phá vỡ revoke tập trung.
- **Trả login thành công trước khi save:** browser nhận cookie nhưng node khác không thể khôi phục session.
- **Báo logout thành công khi delete lỗi:** session cũ vẫn có thể còn dùng được.
- **Chỉ xóa cookie phía browser:** cookie bị sao chép vẫn có thể truy cập session server-side.
- **Retry vô hạn:** làm cạn connection/thread và khuếch đại outage.
- **Dùng cache cũ vô thời hạn:** quyền đã thu hồi vẫn được chấp nhận.
- **Chỉ dùng ControllerAdvice:** bỏ sót lỗi phát sinh trước Spring MVC controller.
- **Readiness chỉ kiểm tra JVM:** load balancer tiếp tục gửi traffic xác thực tới node không đọc được session.
- **Ghi session ID vào log để debug:** tạo thêm bề mặt rò rỉ credential.

## 19. Checklist triển khai

Trước khi phát hành, xác nhận:

- [ ] Phân biệt rõ session không tồn tại với lỗi đọc repository.
- [ ] Route cần Authentication fail-closed khi không thể đọc session.
- [ ] Public route chỉ tiếp tục nếu không phụ thuộc trạng thái session.
- [ ] Login không báo thành công hoặc phát cookie nếu session save chưa được xác nhận.
- [ ] Logout/revoke không báo hoàn tất khi delete chưa được xác nhận.
- [ ] Không có fallback sang local session khi shared store lỗi.
- [ ] Timeout, retry, backoff, circuit breaker và bulkhead có giới hạn.
- [ ] Cache Authentication/security version có TTL và invalidation phù hợp.
- [ ] Lỗi phát sinh trong filter chain có error handling đúng tầng.
- [ ] Response 503 không tiết lộ chi tiết Redis/JDBC hoặc credential.
- [ ] Readiness phản ánh khả năng truy cập session store; liveness tránh restart loop.
- [ ] Có metric riêng cho read, save, delete, retry và revoke backlog.
- [ ] Đã kiểm thử fault injection trên nhiều instance.
- [ ] Không log session ID, cookie, token hoặc SecurityContext.

## 20. Tự kiểm tra kiến thức

Bạn đã nắm được bài học nếu có thể trả lời:

- Vì sao repository trả về không có session khác với repository timeout?
- Vì sao không được chuyển exception đọc Redis thành anonymous session?
- Fail-closed ảnh hưởng thế nào đến route cần xác thực và route công khai?
- Vì sao login chỉ thành công sau khi session state được lưu theo contract?
- Vì sao xóa cookie không chứng minh server-side session đã bị thu hồi?
- Vì sao fallback local phá vỡ session sharing và logout trên nhiều node?
- Retry và circuit breaker cần giới hạn như thế nào để tránh retry storm?
- Khi nào cache Authentication có thể tạo stale authorization?
- Vì sao ControllerAdvice có thể không bắt lỗi từ SessionRepositoryFilter?
- Cần kiểm thử gì để chứng minh ứng dụng xử lý an toàn khi read, write hoặc delete session thất bại?

Khi không thể đọc hoặc ghi trạng thái xác thực, ứng dụng phải coi trạng thái đó là chưa xác minh và từ chối các thao tác được bảo vệ. Hãy phân biệt session miss với repository outage, chỉ xác nhận login/logout sau khi các thao tác lưu/xóa bắt buộc hoàn tất, và dùng timeout, retry có giới hạn, circuit breaker cùng readiness để khoanh vùng sự cố. Với hệ thống nhiều instance, không tạo session local thay thế và không dựa vào Authentication cache cũ để mở quyền khi shared store không khả dụng.
