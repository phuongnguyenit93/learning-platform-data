# Chỉ đọc phiên vẫn có thể cập nhật thời điểm truy cập hoặc phát sinh ghi

Một request có thể chỉ đọc dữ liệu nghiệp vụ nhưng vẫn làm thay đổi session. Khi ứng dụng lấy HttpSession, Spring Session có thể cập nhật lastAccessedTime để phản ánh hoạt động mới nhất của người dùng. Khi session được lưu ở cuối request, repository ghi metadata mới và làm mới thời hạn lưu trữ tương ứng. Vì vậy, một endpoint “chỉ xem” vẫn có thể tạo lệnh ghi Redis hoặc JDBC dù controller không gọi setAttribute.

Để hiểu hiện tượng này, cần tách ba loại thay đổi: metadata vòng đời của session, thuộc tính session và dữ liệu nghiệp vụ. FlushMode quyết định thời điểm thay đổi session được đẩy xuống repository; SaveMode quyết định thuộc tính nào được ghi. Hai chính sách này không có nghĩa là một request chỉ đọc sẽ tuyệt đối không phát sinh ghi.

Bài này tập trung vào cách session được truy cập trong request Servlet, vì sao thời điểm truy cập và TTL có thể thay đổi, cách chọn FlushMode/SaveMode, và cách kiểm tra lượng ghi thực tế khi ứng dụng chạy nhiều instance.

## 1. Ba loại dữ liệu cần phân biệt

Một session có thể chứa metadata do Spring Session quản lý và các thuộc tính do ứng dụng đặt vào.

| Loại dữ liệu | Ví dụ | Có thể đổi trong request chỉ đọc? |
|---|---|---|
| Metadata vòng đời | creationTime, lastAccessedTime, maxInactiveInterval | Có; việc sử dụng session có thể cập nhật lastAccessedTime |
| Thuộc tính session | SPRING_SECURITY_CONTEXT, app.locale, app.activeCartId | Thường không đổi nếu chỉ đọc; có thể được đánh dấu lưu tùy SaveMode |
| Dữ liệu nghiệp vụ | Hồ sơ, đơn hàng, giỏ hàng trong database | Không nhất thiết đổi nếu endpoint chỉ truy vấn |

Ví dụ, controller hiển thị trang hồ sơ có thể:

1. Đọc Authentication hoặc một thuộc tính từ session.
2. Gọi service tải hồ sơ bằng một truy vấn SELECT.
3. Trả HTML hoặc JSON mà không thay đổi hồ sơ.

Dữ liệu nghiệp vụ không bị cập nhật. Tuy nhiên, việc Spring Security hoặc controller truy cập session có thể cập nhật thời điểm hoạt động của session. Khi request hoàn tất, Spring Session lưu metadata mới theo chính sách repository.

Vì vậy, “read-only” cần được xác định rõ là:

- **Chỉ đọc nghiệp vụ:** không thay đổi đơn hàng, hồ sơ hoặc dữ liệu miền.
- **Không thay đổi thuộc tính session:** không gọi setAttribute/removeAttribute và không sửa object mutable được lưu trong session.
- **Không ghi bất kỳ dữ liệu session nào:** không thay đổi metadata, thuộc tính hoặc TTL ở repository.

Hai khái niệm đầu không đảm bảo khái niệm thứ ba.

## 2. Khi nào một request được xem là đã truy cập session?

Trong Servlet, ứng dụng làm việc với HttpSession thông qua HttpServletRequest. Một số thao tác thường gặp:

~~~java
HttpSession session = request.getSession();
~~~

~~~java
HttpSession session = request.getSession(false);
~~~

Lời gọi getSession() tạo session nếu request chưa có session hợp lệ. Lời gọi getSession(false) chỉ lấy session hiện có và trả null nếu không có; nó không tạo session mới.

Khi Spring Session bọc request, các thao tác truy cập session đi qua SessionRepositoryFilter và request wrapper. Khi session được lấy ra để phục vụ request, thời điểm lastAccessedTime có thể được cập nhật. Việc lưu metadata sau đó phụ thuộc repository và FlushMode.

Một cookie SESSION xuất hiện trong request không tự chứng minh controller đã sửa session. Cần phân biệt:

- Request không truy cập HttpSession: ứng dụng có thể không cần tải hoặc lưu session, tùy filter và cơ chế lazy lookup.
- Request gọi getSession(false) và tìm thấy session: session đã được truy cập; metadata hoạt động có thể thay đổi.
- Request gọi getSession() khi chưa có session: ứng dụng tạo session mới, thường phát sinh ghi khi session được lưu.
- Filter bảo mật truy cập session trước controller: dù controller không gọi HttpSession, session vẫn có thể được tải và cập nhật.

Spring Security có thể truy cập session để đọc hoặc lưu SecurityContext, request cache, CSRF state hoặc dữ liệu bảo mật khác tùy cấu hình. Do đó, cần kiểm tra toàn bộ filter chain khi điều tra một request tưởng như chỉ đọc.

### Ví dụ endpoint chỉ đọc session

~~~java
@GetMapping("/account/summary")
public AccountSummary summary(
        HttpServletRequest request,
        @AuthenticationPrincipal AppPrincipal principal) {

    HttpSession session = request.getSession(false);

    // Không tạo session mới nếu request không có session.
    // Nếu session tồn tại, việc lấy session vẫn có thể cập nhật lastAccessedTime.

    return accountService.loadSummary(principal.userId());
}
~~~

Endpoint này không đặt hoặc xóa thuộc tính session. Tuy nhiên, khi session hiện hữu được lấy ra, Spring Session có thể ghi metadata hoạt động và làm mới thời hạn idle timeout.

Nếu endpoint không cần session, hãy tránh gọi getSession() chỉ để kiểm tra hoặc ghi log. Dùng principal đã được Spring Security cung cấp nếu đủ cho nghiệp vụ, và kiểm tra cấu hình filter để biết liệu session có bị truy cập trước controller hay không.

## 3. lastAccessedTime và idle timeout

Spring Session theo dõi thời điểm session được truy cập gần nhất. Về khái niệm, thời điểm hết hạn không hoạt động được tính như sau:

~~~text
expirationTime = lastAccessedTime + maxInactiveInterval
~~~

Ví dụ:

| Thời điểm | Sự kiện |
|---|---|
| 09:00 | Người dùng đăng nhập |
| 09:10 | Truy cập trang hồ sơ |
| 09:10 | lastAccessedTime được cập nhật |
| 09:40 | Thời điểm hết hạn dự kiến nếu timeout là 30 phút |
| 09:35 | Người dùng xem trang đơn hàng |
| 09:35 | lastAccessedTime được cập nhật |
| 10:05 | Thời điểm hết hạn dự kiến mới |

Một thao tác chỉ đọc vẫn có thể kéo dài idle timeout. Đây là hành vi hợp lý nếu chính sách định nghĩa rằng bất kỳ hoạt động được xác thực nào cũng giữ phiên đăng nhập. Nếu hệ thống muốn chỉ một số hành động mới làm mới idle timeout, cần thiết kế chính sách truy cập riêng; không thể dựa vào SaveMode để tạo ra quy tắc đó.

### Idle timeout khác absolute timeout

Idle timeout hết hạn khi người dùng không hoạt động trong khoảng maxInactiveInterval. Absolute timeout giới hạn tổng tuổi của session kể từ lúc tạo hoặc đăng nhập, kể cả khi người dùng liên tục hoạt động.

Ví dụ:

- Idle timeout: 30 phút không hoạt động.
- Absolute timeout: 8 giờ kể từ lúc đăng nhập.

Một request chỉ đọc có thể làm mới idle timeout, nhưng không nên tự động kéo dài absolute timeout nếu chính sách yêu cầu giới hạn tuổi phiên. Ứng dụng cần lưu thời điểm xác thực hoặc thời điểm tạo phiên và kiểm tra riêng khi xử lý request.

## 4. Vì sao request chỉ đọc vẫn có thể ghi Redis/JDBC?

Khi session được truy cập, Spring Session có thể cập nhật lastAccessedTime. Repository cần lưu thay đổi metadata đó để các instance khác thấy thời điểm hoạt động mới và để TTL được điều chỉnh theo idle timeout.

Với Redis, thao tác có thể bao gồm cập nhật hash session, TTL của key session và các key theo dõi expiration tùy repository. Với RedisIndexedSessionRepository, còn có các cấu trúc expiration/index liên quan. Với JDBC, repository có thể cập nhật các cột thời gian truy cập và hết hạn trong bảng session.

Một request chỉ đọc có thể tạo ra các thao tác như:

| Tình huống | Dữ liệu có thể được ghi |
|---|---|
| Đọc session hiện có | lastAccessedTime và thời hạn tương ứng |
| Đọc thuộc tính session với SaveMode.ON_GET_ATTRIBUTE | Thuộc tính đã đọc có thể được đưa vào tập thuộc tính cần lưu |
| Đặt thuộc tính mới | Thuộc tính mới và metadata liên quan |
| Gọi getSession() khi chưa có session | Bản ghi session mới và cookie ID |
| Chỉ truy vấn database nghiệp vụ, không truy cập session | Có thể không phát sinh ghi session từ request đó |

Không nên kết luận rằng mỗi request có cookie luôn tạo một lần ghi. Hành vi thực tế phụ thuộc request có truy cập session không, filter chain có dùng session không, repository nào được cấu hình và chính sách lưu/flush.

### Tác động khi tải lớn

Giả sử có 10.000 request đọc mỗi phút và phần lớn request truy cập session. Dù không cập nhật thuộc tính nào, metadata truy cập vẫn có thể được làm mới. Điều này có thể tạo tải ghi đáng kể lên Redis hoặc database session.

Các tác động có thể gồm:

- Tăng lệnh ghi và băng thông giữa ứng dụng với Redis/JDBC.
- Tăng tải transaction, connection pool và log ghi của database.
- Tăng độ trễ cuối request nếu session phải flush trước khi response hoàn tất.
- Tăng replication traffic và chi phí persistence của Redis.
- Tăng khả năng hai request đồng thời ghi metadata session.
- Tạo nhiều hoạt động cleanup/expiration hơn khi session có TTL ngắn và số lượng lớn.

Hãy đo bằng metric repository, Redis command statistics, database monitoring và tracing đã che thông tin nhạy cảm. Không giả định controller không gọi setAttribute thì hệ thống không ghi.

## 5. FlushMode: thời điểm ghi session

FlushMode quyết định khi nào thay đổi session được ghi xuống kho dữ liệu. Hai chế độ phổ biến:

| Chế độ | Hành vi | Tác động |
|---|---|---|
| ON_SAVE | Repository lưu khi SessionRepository.save được gọi; trong Servlet flow thường gần cuối request | Gom các thay đổi trong request và giảm số lần ghi trung gian |
| IMMEDIATE | Thay đổi được ghi xuống repository sớm nhất có thể sau thao tác thay đổi | Thay đổi xuất hiện sớm hơn nhưng có thể tăng số lần I/O |

Ví dụ cấu hình Redis:

~~~java
@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
public class SessionConfiguration {
}
~~~

Với ON_SAVE, một request có thể truy cập session, cập nhật lastAccessedTime và chỉ lưu khi request kết thúc. Điều đó không có nghĩa là metadata sẽ không được lưu; nó chỉ quyết định thời điểm flush.

Với IMMEDIATE, các thay đổi có thể được gửi xuống kho sớm hơn. Nếu một request đặt nhiều thuộc tính liên tiếp, có thể phát sinh nhiều thao tác lưu riêng hoặc nhiều lần cập nhật repository, tùy implementation. Không chọn IMMEDIATE chỉ vì muốn “session mới nhất”; cần cân nhắc tải I/O và yêu cầu nhất quán.

FlushMode không phải chế độ read-only. Nó không vô hiệu hóa việc lưu metadata hoặc thuộc tính session.

## 6. SaveMode: thuộc tính nào được ghi?

SaveMode quyết định tập thuộc tính session nào được đưa vào thao tác lưu. Các chế độ phổ biến:

| Chế độ | Thuộc tính được lưu | Trường hợp phù hợp |
|---|---|---|
| ON_SET_ATTRIBUTE | Thuộc tính được đặt hoặc thay đổi bằng setAttribute | Mặc định hợp lý khi ứng dụng thay đổi thuộc tính theo cách rõ ràng |
| ON_GET_ATTRIBUTE | Thuộc tính được đặt hoặc đã được đọc trong request | Khi ứng dụng sửa object mutable tại chỗ sau khi lấy từ session |
| ALWAYS | Tất cả thuộc tính session được lưu mỗi lần save | Khi cần lưu toàn bộ trạng thái và chấp nhận lượng ghi lớn hơn |

Ví dụ, nếu session chứa một danh sách:

~~~java
@SuppressWarnings("unchecked")
List<String> recentItems =
        (List<String>) session.getAttribute("app.recentItems");

recentItems.add(itemId);
~~~

Đoạn code sửa object mutable tại chỗ nhưng không gọi setAttribute lại. Với ON_SET_ATTRIBUTE, repository có thể không đánh dấu thuộc tính đó là đã thay đổi. Với ON_GET_ATTRIBUTE, thuộc tính được đọc có thể được đưa vào tập cần lưu, nên thay đổi bên trong object có cơ hội được ghi.

Cách rõ ràng hơn là tạo collection mới và đặt lại thuộc tính:

~~~java
List<String> updated = new ArrayList<>(recentItems);
updated.add(itemId);
session.setAttribute("app.recentItems", updated);
~~~

### SaveMode không quyết định metadata

Đây là điểm quan trọng khi phân tích request chỉ đọc:

- ON_SET_ATTRIBUTE giới hạn thuộc tính được ghi, nhưng không đảm bảo metadata session không đổi.
- ON_GET_ATTRIBUTE có thể khiến các thuộc tính chỉ đọc cũng được đưa vào tập lưu.
- ALWAYS có thể ghi lại toàn bộ thuộc tính mỗi lần lưu, kể cả khi request chỉ đọc.
- lastAccessedTime và expiration metadata thuộc vòng đời session, không phải thuộc tính nghiệp vụ do controller đặt.

Vì vậy, chuyển từ ALWAYS sang ON_SET_ATTRIBUTE có thể giảm lượng dữ liệu thuộc tính phải serialize và ghi, nhưng không nhất thiết loại bỏ thao tác cập nhật metadata hoặc TTL.

## 7. Chọn FlushMode và SaveMode cùng nhau

Hai chính sách trả lời hai câu hỏi khác nhau. Có thể phối hợp như sau:

| FlushMode | SaveMode | Ý nghĩa |
|---|---|---|
| ON_SAVE | ON_SET_ATTRIBUTE | Ghi khi request lưu; chỉ lưu thuộc tính được đặt/thay đổi rõ ràng |
| ON_SAVE | ON_GET_ATTRIBUTE | Ghi gần cuối request; lưu cả thuộc tính đã đọc để hỗ trợ sửa object tại chỗ |
| ON_SAVE | ALWAYS | Ghi gần cuối request; serialize/lưu toàn bộ thuộc tính |
| IMMEDIATE | ON_SET_ATTRIBUTE | Ghi thay đổi thuộc tính sớm; chỉ các thuộc tính được đặt/thay đổi |
| IMMEDIATE | ON_GET_ATTRIBUTE | Ghi sớm; các thuộc tính đã đọc cũng có thể được lưu |
| IMMEDIATE | ALWAYS | Chính sách có thể tạo nhiều I/O và payload lớn nhất |

Đối với ứng dụng web thông thường, ON_SAVE + ON_SET_ATTRIBUTE thường là điểm khởi đầu hợp lý. Cặp này gom thao tác lưu ở cuối request và tránh serialize toàn bộ thuộc tính khi không cần. Tuy nhiên, vẫn cần đo xem metadata truy cập và TTL có tạo tải ghi đáng kể hay không.

Nếu code hiện tại sửa object mutable trong session mà không gọi setAttribute, hãy sửa cách cập nhật hoặc cân nhắc ON_GET_ATTRIBUTE sau khi đo tác động. Không chuyển sang ALWAYS như giải pháp mặc định cho mọi lỗi mất cập nhật.

## 8. Cấu hình trong Spring Boot và ứng dụng Java

Với ứng dụng dùng annotation, có thể đặt FlushMode và SaveMode trên cấu hình repository phù hợp. Ví dụ Redis:

~~~java
@Configuration
@EnableRedisHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
class SessionConfiguration {
}
~~~

JDBC cũng có cấu hình session tương ứng hỗ trợ các chính sách lưu:

~~~java
@Configuration
@EnableJdbcHttpSession(
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
class JdbcSessionConfiguration {
}
~~~

Trong Spring Boot, các property và khả năng cấu hình phụ thuộc phiên bản Spring Boot/Spring Session. Hãy kiểm tra metadata cấu hình của dependency đang dùng, tránh đồng thời bật auto-configuration và khai báo annotation tạo thêm repository/filter thứ hai.

Dù dùng Redis hay JDBC, ý nghĩa của hai chính sách vẫn cần được hiểu riêng: FlushMode điều khiển thời điểm ghi; SaveMode điều khiển thuộc tính được lưu. Cả hai không thay đổi quy tắc xác thực hoặc quyền truy cập.

## 9. getSession(false) có tránh được ghi không?

getSession(false) tránh tạo một session mới nếu request không có session hiện tại. Điều này hữu ích cho endpoint công khai, nơi ứng dụng chỉ muốn kiểm tra xem session có tồn tại hay không.

~~~java
HttpSession session = request.getSession(false);

if (session == null) {
    return ResponseEntity.ok("anonymous");
}

return ResponseEntity.ok("session-present");
~~~

Tuy nhiên, nếu session tồn tại và được trả về, việc truy cập session vẫn có thể cập nhật lastAccessedTime. Do đó, getSession(false) tránh ghi do tạo session mới nhưng không đảm bảo không có ghi metadata.

Đừng gọi getSession() trong mọi request chỉ để lấy ID hoặc ghi log. Nếu không có session, lời gọi đó có thể tạo session mới không cần thiết, làm phát cookie và lưu dữ liệu vào repository.

Nếu endpoint không cần session, tốt nhất không truy cập HttpSession. Tuy nhiên, Spring Security hoặc filter khác vẫn có thể dùng session trước controller. Hãy kiểm tra SecurityContextRepository, request cache, CSRF và các filter tùy chỉnh. Cấu hình stateless cho một nhóm API có thể giảm việc dùng session nếu kiến trúc xác thực cho phép, nhưng không nên thay đổi chỉ để giảm I/O mà bỏ qua yêu cầu bảo mật.

## 10. Transaction read-only của nghiệp vụ không ngăn ghi session

Một service có thể dùng:

~~~java
@Transactional(readOnly = true)
public AccountSummary loadSummary(UUID userId) {
    return accountRepository.loadSummary(userId);
}
~~~

readOnly=true là gợi ý/chính sách cho transaction nghiệp vụ theo transaction manager và database đang dùng. Nó không tự động biến Spring Session thành read-only.

Nếu session được quản lý bởi Redis, thao tác lưu session diễn ra qua RedisConnectionFactory và không thuộc transaction đọc của database nghiệp vụ. Nếu session được quản lý bằng JDBC, repository session có thể dùng transaction manager và propagation riêng theo cấu hình của nó. Vì vậy, không được giả định transaction đọc của service sẽ chặn hoặc rollback việc lưu metadata session.

Nếu yêu cầu của endpoint là không ghi database nghiệp vụ, hãy xác minh query và transaction nghiệp vụ. Nếu yêu cầu là không phát sinh ghi ở kho session, cần kiểm tra riêng việc truy cập HttpSession, filter chain và repository.

## 11. Request đồng thời và cập nhật metadata

Một người dùng có thể mở nhiều tab hoặc gửi request song song. Hai request có thể cùng tải session ở thời điểm gần nhau, sau đó cập nhật lastAccessedTime hoặc thuộc tính theo các nhịp khác nhau.

Ví dụ:

1. Request A tải session với lastAccessedTime là 10:00:00.
2. Request B tải cùng session sau đó và có thời gian mới hơn.
3. Request B lưu session.
4. Request A hoàn tất muộn hơn và lưu snapshot cũ hơn.

Tùy repository, flush/save mode và cách thay đổi session, việc lưu sau có thể ghi đè một phần dữ liệu mới hơn nếu cùng một thuộc tính bị cập nhật. Không coi session repository là cơ chế transaction nguyên tử cho mọi thuộc tính.

Các nguyên tắc:

- Tránh lưu object nghiệp vụ lớn hoặc collection mutable vào session.
- Dùng ON_SET_ATTRIBUTE và đặt lại thuộc tính sau khi tạo giá trị mới.
- Đặt dữ liệu cần nhất quán vào database nghiệp vụ và dùng optimistic locking/transaction.
- Không dùng session làm bộ đếm giao dịch hoặc nguồn sự thật cho số dư, tồn kho và trạng thái thanh toán.
- Kiểm thử hai request đồng thời khi cả hai cùng đọc và ghi session.

lastAccessedTime là metadata hoạt động; nó không nên được dùng để xác định thứ tự giao dịch nghiệp vụ hoặc thay thế audit timestamp.

## 12. Đo và chẩn đoán lượng ghi do request chỉ đọc

Khi nghi ngờ endpoint chỉ đọc đang tạo quá nhiều thao tác Redis/JDBC, hãy quan sát cả tầng web và tầng repository.

Các chỉ số nên theo dõi:

- Số request có truy cập HttpSession theo endpoint.
- Số lần tạo session mới ngoài dự kiến.
- Số lần save session và thời gian save.
- Số lệnh Redis liên quan tới session, độ trễ và lượng dữ liệu ghi.
- Số câu UPDATE/INSERT trong bảng Spring Session JDBC.
- Tỷ lệ request đọc nghiệp vụ nhưng vẫn có ghi session.
- Số lần cập nhật lastAccessedTime và refresh TTL nếu có thể đo qua instrumentation.
- Lỗi connection pool, transaction, serialization và timeout.

Không ghi session ID, cookie hoặc SecurityContext vào log. Metric label nên dùng route template, repository type, environment và outcome; tránh dùng principal hoặc session ID làm label có cardinality cao.

### Quy trình kiểm tra

1. Chọn endpoint được cho là chỉ đọc.
2. Xác nhận controller/service không gọi setAttribute, removeAttribute hoặc sửa object mutable trong session.
3. Kiểm tra filter chain xem Spring Security hoặc filter tùy chỉnh có truy cập session không.
4. Gửi request có và không có cookie để so sánh.
5. So sánh request không truy cập session với request gọi getSession(false).
6. Quan sát lệnh Redis hoặc câu SQL của repository session.
7. Thử ON_SAVE + ON_SET_ATTRIBUTE, sau đó so sánh với cấu hình hiện tại.
8. Xác nhận TTL vẫn đáp ứng idle timeout và hành vi xác thực không thay đổi.
9. Kiểm tra tải đồng thời và độ trễ cuối request.

Không dựa vào một lần chạy đơn lẻ. Hãy thử với số lượng request đủ lớn và cùng điều kiện để tránh kết luận sai do cache, connection pool hoặc tác vụ nền.

## 13. Ma trận kiểm thử chính sách ghi

| Ca kiểm thử | Thao tác | Điều cần xác nhận |
|---|---|---|
| Request không có session | Gọi endpoint công khai không truy cập HttpSession | Không tạo session ngoài ý muốn |
| getSession(false), không có session | Request không gửi cookie | Trả null và không tạo session mới |
| getSession(false), có session | Gửi cookie hợp lệ | Session được đọc; kiểm tra metadata và TTL có được cập nhật |
| Chỉ đọc thuộc tính | Gọi getAttribute | SaveMode có hành vi như cấu hình |
| Đặt thuộc tính | Gọi setAttribute | Thuộc tính được lưu theo SaveMode |
| Sửa object tại chỗ | Đọc collection rồi sửa mà không set lại | Xác nhận ON_SET_ATTRIBUTE và ON_GET_ATTRIBUTE khác nhau |
| ON_SAVE | Thay đổi session trong request | Ghi được thực hiện khi repository save |
| IMMEDIATE | Thay đổi session | Ghi xảy ra sớm hơn; đo số thao tác I/O |
| ALWAYS | Request chỉ đọc session | Kiểm tra toàn bộ thuộc tính có bị ghi lại |
| Transaction nghiệp vụ read-only | Truy vấn service có @Transactional(readOnly=true) | Phân biệt ghi nghiệp vụ và ghi repository session |
| Hai request song song | Cùng truy cập/cập nhật một session | Kiểm tra cập nhật bị ghi đè hoặc mất dữ liệu |
| Nhiều instance | Request tiếp theo được định tuyến sang node khác | Node khác nhìn thấy metadata/session theo repository |

Integration test nên chạy với Redis hoặc JDBC repository tương ứng. MockHttpSession có thể kiểm thử controller nhưng không chứng minh TTL, lệnh ghi, transaction hoặc FlushMode/SaveMode của repository thật.

## 14. Chọn chính sách theo mục tiêu

| Mục tiêu | Hướng xử lý |
|---|---|
| Giảm số lần ghi trung gian trong một request | Ưu tiên đánh giá FlushMode.ON_SAVE |
| Tránh serialize mọi thuộc tính session | Đánh giá SaveMode.ON_SET_ATTRIBUTE |
| Ứng dụng sửa object mutable trong session mà không set lại | Sửa code để set lại; hoặc cân nhắc ON_GET_ATTRIBUTE với đo đạc |
| Giữ idle timeout chính xác theo hoạt động | Cho phép cập nhật lastAccessedTime theo chính sách truy cập session |
| Endpoint công khai không cần session | Tránh truy cập HttpSession và tránh tạo session mới |
| API stateless | Cấu hình bảo mật stateless phù hợp với kiến trúc, xác minh filter không dùng session |
| Không muốn request đọc kéo dài phiên đăng nhập | Thiết kế chính sách idle/absolute timeout riêng, không kỳ vọng SaveMode giải quyết |
| Dữ liệu nghiệp vụ cần tính nguyên tử | Lưu trong database nghiệp vụ với transaction/locking phù hợp |

Đừng hy sinh ý nghĩa của idle timeout chỉ để giảm vài thao tác ghi. Nếu mọi hoạt động được xác thực phải giữ phiên đăng nhập, cập nhật lastAccessedTime là hành vi cần thiết. Nếu chỉ một nhóm hoạt động được phép kéo dài phiên, hãy định nghĩa rõ nhóm hoạt động đó và thực hiện kiểm tra timeout riêng.

## 15. Checklist trước khi tối ưu write policy

Trước khi thay đổi chính sách ghi session, hãy xác nhận:

- Đã phân biệt metadata session, thuộc tính session và dữ liệu nghiệp vụ.
- Đã xác định request/filter nào thực sự truy cập HttpSession.
- Đã biết getSession(false) tránh tạo session mới nhưng không nhất thiết tránh cập nhật lastAccessedTime.
- FlushMode được chọn theo thời điểm cần ghi và ngân sách I/O.
- SaveMode phù hợp với cách ứng dụng cập nhật thuộc tính.
- Không sửa object mutable trong session mà không hiểu cơ chế dirty tracking.
- Transaction read-only của nghiệp vụ không bị nhầm là read-only của repository session.
- Đã đo Redis/JDBC write load trước và sau thay đổi.
- Đã kiểm thử idle timeout, absolute timeout và logout.
- Đã kiểm thử nhiều request đồng thời và nhiều instance.
- Không ghi session ID hoặc dữ liệu xác thực vào log/metric.

Một request chỉ đọc vẫn có thể là một hoạt động session. Khi request truy cập HttpSession, Spring Session có thể cập nhật lastAccessedTime và làm mới TTL để phản ánh idle timeout. SaveMode giúp kiểm soát thuộc tính được lưu, FlushMode giúp kiểm soát thời điểm flush; cả hai cần được lựa chọn cùng với cách filter chain sử dụng session và yêu cầu bảo mật của ứng dụng.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session — JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [FlushMode Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FlushMode.html)
- [SaveMode Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SaveMode.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Jakarta Servlet — HttpSession](https://jakarta.ee/specifications/servlet/)

