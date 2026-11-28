# Bảo vệ bản sao lưu, kênh truyền và dữ liệu lưu trên thiết bị

Spring Session lưu trạng thái phiên ở một kho dùng chung như Redis hoặc JDBC để nhiều instance ứng dụng có thể đọc và cập nhật cùng session. Dữ liệu đó có thể chứa SecurityContext, principal, quyền truy cập, thông tin quy trình và các thuộc tính cá nhân. Vì vậy, bảo vệ session không chỉ là bật HttpOnly cho cookie: cần bảo vệ toàn bộ đường đi của dữ liệu từ trình duyệt đến load balancer, từ ứng dụng đến Redis/JDBC, trong bản sao lưu và trên thiết bị người dùng.

Một session ID hợp lệ thường hoạt động như bearer credential: bên nào sở hữu ID và gửi được nó đến ứng dụng có thể sử dụng phiên tương ứng. Bản sao lưu của kho session có thể chứa cả session ID lẫn dữ liệu xác thực phía server. Nếu bản backup bị lộ hoặc được khôi phục không đúng cách, kẻ tấn công có thể có cơ hội chiếm quyền phiên. Do đó, cần kết hợp mã hóa, phân quyền, giới hạn thời gian lưu, kiểm soát thiết bị và quy trình khôi phục an toàn.

## 1. Xác định dữ liệu nào cần được bảo vệ

Trong mô hình Spring Session thông thường, trình duyệt không nhận toàn bộ HttpSession. Client giữ định danh phiên, thường là cookie SESSION hoặc JSESSIONID; các thuộc tính session được lưu phía server trong Redis hoặc database.

Kho session có thể chứa:

- SecurityContext và thông tin Authentication.
- Principal name, vai trò hoặc thông tin phân quyền được ứng dụng lưu.
- Trạng thái giỏ hàng, wizard, quy trình đang thực hiện.
- Thông tin người dùng hoặc dữ liệu nghiệp vụ tạm thời.
- Thời điểm tạo, truy cập gần nhất và thời hạn session.
- Session ID và các chỉ mục phụ trợ do repository quản lý.

Không phải ứng dụng nào cũng lưu tất cả các loại dữ liệu trên. Hãy kiểm tra chính xác những thuộc tính mà ứng dụng đưa vào session và phân loại chúng theo độ nhạy cảm. Tránh lưu password, access token dài hạn, khóa bí mật, dữ liệu thanh toán đầy đủ hoặc dữ liệu cá nhân không cần thiết trong session.

Phân biệt các vị trí lưu trữ:

| Vị trí | Dữ liệu thường có | Rủi ro chính |
| --- | --- | --- |
| Browser cookie | Session ID | Bị đánh cắp hoặc gửi ngoài ý muốn |
| Browser/mobile storage | ID hoặc token do client tự lưu; có thể có cache ứng dụng | XSS, malware, backup thiết bị hoặc thiết bị bị mất |
| Redis | Session record, attributes, index và expiration metadata | Truy cập trái phép, dump/snapshot bị lộ |
| JDBC database | Session metadata và serialized attributes | Quyền DB quá rộng, backup hoặc export bị lộ |
| Backup/snapshot | Bản sao dữ liệu session tại một thời điểm | Dữ liệu tồn tại lâu hơn TTL, có thể khôi phục phiên cũ |
| Log/APM/trace | Có thể vô tình chứa cookie, header hoặc payload | Rò rỉ credential qua hệ thống quan sát |

## 2. Bảo vệ session ID ở phía client

Cookie chứa session ID là credential. Với ứng dụng Servlet dùng cookie resolver, nên cấu hình cookie bảo vệ phù hợp:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: SESSION
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Các property có thể thay đổi theo phiên bản Spring Boot. Xác nhận cấu hình thực tế của dự án và kiểm tra header Set-Cookie được trả về ở môi trường production.

- Secure yêu cầu browser chỉ gửi cookie qua HTTPS.
- HttpOnly ngăn JavaScript thông thường đọc cookie, giảm khả năng XSS lấy trực tiếp session ID.
- SameSite giúp kiểm soát khi cookie được gửi trong điều hướng hoặc request cross-site; chọn Lax, Strict hoặc None theo luồng đăng nhập và tích hợp thực tế.
- Path và Domain xác định phạm vi gửi cookie. Chỉ mở rộng phạm vi khi ứng dụng thực sự cần.

HttpOnly không ngăn XSS thực hiện request dưới danh nghĩa người dùng trong browser đã bị xâm nhập. Secure không bảo vệ cookie nếu TLS bị cấu hình sai hoặc cookie bị ghi vào log. SameSite không thay thế CSRF protection. Cần phối hợp CSP, encode output, dependency hygiene, CSRF token và kiểm soát origin.

Nếu frontend và backend ở các site khác nhau, cookie có thể cần SameSite=None và Secure, đồng thời cấu hình CORS credentials chính xác. Không dùng wildcard origin cùng credentials. Hãy xác định rõ origin được phép và giữ CSRF protection phù hợp.

## 3. Bảo vệ định danh khi dùng header resolver

Một số API hoặc ứng dụng mobile dùng HeaderHttpSessionIdResolver thay vì cookie. Client gửi session ID trong header, ví dụ x-auth-token. Header này cũng là bearer credential và phải được bảo vệ như cookie:

- Chỉ truyền qua HTTPS.
- Không ghi header vào access log, reverse proxy log, APM hoặc exception report.
- Không đưa ID vào URL, query string hoặc analytics event.
- Không chia sẻ credential giữa các ứng dụng không liên quan.
- Xóa ID khỏi client storage khi logout, hết hạn hoặc bị thu hồi.
- Giới hạn CORS origin và quyền truy cập API.

Ứng dụng mobile cần lưu credential trong vùng lưu trữ bảo mật của hệ điều hành, ví dụ Keychain trên nền tảng Apple hoặc Android Keystore-backed storage. Tránh lưu session ID trong file văn bản, shared preferences không mã hóa, clipboard hoặc backup thiết bị không được kiểm soát.

Header resolver không tự động bảo vệ khỏi XSS nếu ứng dụng browser lưu ID ở localStorage hoặc sessionStorage. JavaScript có thể đọc các vùng lưu trữ đó khi trang bị XSS. Với browser, cookie HttpOnly thường là lựa chọn phù hợp hơn nếu kiến trúc xác thực dùng session cookie.

## 4. Mã hóa toàn bộ kênh truyền

Session ID và session attributes cần được bảo vệ khi truyền qua mọi ranh giới mạng:

1. Browser đến load balancer/reverse proxy: HTTPS/TLS.
2. Load balancer đến instance Spring: TLS nếu hop này đi qua mạng hoặc vùng tin cậy riêng.
3. Instance Spring đến Redis: TLS và xác thực client.
4. Instance Spring đến JDBC database: TLS với xác minh chứng chỉ server.
5. Redis replication, cluster bus hoặc database replication: dùng cơ chế mã hóa được dịch vụ hỗ trợ.
6. Backup agent đến object storage hoặc hệ thống backup: TLS và xác thực riêng.

Chỉ bật HTTPS ở public endpoint chưa đủ nếu proxy gửi dữ liệu nhạy cảm qua mạng nội bộ không được bảo vệ. Đánh giá từng hop theo topology thật, bao gồm Kubernetes node network, subnet, service mesh và kết nối liên vùng.

### Browser và reverse proxy

Load balancer có thể kết thúc TLS rồi chuyển request đến ứng dụng qua HTTP nội bộ. Cách này chỉ phù hợp khi mạng nội bộ được kiểm soát và rủi ro đã được chấp nhận. Nếu các node nằm trên mạng dùng chung hoặc đi qua hạ tầng không tin cậy, hãy bật TLS giữa proxy và ứng dụng.

Ứng dụng phải tin forwarded headers chỉ từ proxy tin cậy. Không cho client bên ngoài tự đặt X-Forwarded-Proto hoặc X-Forwarded-Host để làm thay đổi cách ứng dụng phát cookie Secure, redirect hoặc URL. Cấu hình trusted proxy/forwarded header theo nền tảng triển khai.

### Redis TLS

Ví dụ cấu hình Spring Boot cho kết nối Redis có TLS:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      ssl:
        enabled: true
~~~

Property cụ thể tùy phiên bản Spring Boot và Redis client. Trong production, xác minh chứng chỉ server, hostname, trust store và chính sách certificate rotation. Không hạ xuống kết nối plaintext chỉ để né lỗi chứng chỉ.

### JDBC TLS

Với PostgreSQL, JDBC URL có thể yêu cầu xác minh chứng chỉ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.internal:5432/app?sslmode=verify-full
    username: session_runtime
    password: <secret-from-secret-manager>
~~~

sslmode=verify-full yêu cầu TLS và xác minh danh tính server theo hostname/chứng chỉ. Cách cấu hình trust material phụ thuộc driver và môi trường. Không dùng sslmode=disable trong production; cũng không xem mã hóa TLS là thay thế cho authentication và quyền DB tối thiểu.

## 5. Mã hóa dữ liệu khi lưu trữ

Mã hóa at rest bảo vệ dữ liệu khi ổ đĩa, volume, snapshot hoặc thiết bị lưu trữ bị truy cập trái phép. Nên bật mã hóa ở các lớp được nền tảng hỗ trợ:

- Redis managed service hoặc volume lưu persistence file.
- Database storage, tablespace hoặc volume.
- Snapshot và backup database.
- Redis RDB/AOF hoặc bản export.
- Object storage chứa backup.
- Volume và file tạm được dùng khi restore.

Mã hóa ổ đĩa không bảo vệ dữ liệu khỏi một ứng dụng đã được cấp quyền đọc hợp lệ. Nếu attacker chiếm được credential của application runtime, họ có thể đọc session qua Redis/JDBC dù storage đã mã hóa at rest. Vì vậy cần kết hợp ACL, network isolation, authentication, audit và phân quyền.

### Mã hóa ở tầng ứng dụng

Nếu threat model yêu cầu bảo vệ một số thuộc tính ngay cả khi kho dữ liệu bị đọc trái phép, có thể mã hóa các trường nhạy cảm trước khi lưu session. Cách này đòi hỏi serializer hoặc lớp mã hóa riêng và quản lý khóa cẩn thận.

Không tự viết thuật toán mã hóa. Dùng thư viện mật mã được duy trì, chế độ authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305 theo tiêu chuẩn của nền tảng, nonce/IV duy nhất và xác thực tính toàn vẹn. Không tái sử dụng nonce trong cùng một khóa.

Mã hóa toàn bộ serialized session có thể làm khó tra cứu theo principal, phân tích dữ liệu và tương thích rolling deployment. Chỉ mã hóa trường cần thiết nếu repository cần index metadata để phục vụ chức năng. Không mã hóa session ID theo cách làm hỏng cơ chế lookup của Spring Session.

Nếu dùng application-level encryption:

- Lưu key identifier cùng ciphertext để biết khóa nào dùng khi giải mã.
- Giữ khóa trong KMS/HSM hoặc secret manager, không lưu cùng backup dữ liệu.
- Hỗ trợ giai đoạn đọc khóa cũ và ghi khóa mới khi rotation.
- Có kế hoạch giải mã/migrate dữ liệu trước khi xóa khóa cũ.
- Kiểm thử khôi phục backup bằng bộ khóa phù hợp.

## 6. Bảo vệ Redis và database khỏi truy cập trái phép

Mọi instance Spring có quyền truy cập session store đều có thể đọc hoặc sửa trạng thái phiên. Tài khoản runtime cần quyền tối thiểu:

- Redis ACL chỉ cho phép ứng dụng truy cập key namespace cần thiết và các command repository cần dùng.
- Không dùng tài khoản Redis mặc định có quyền quản trị toàn bộ server.
- Database runtime chỉ có quyền SELECT/INSERT/UPDATE/DELETE trên các bảng session cần thiết.
- Tài khoản migration/schema admin tách biệt với tài khoản chạy ứng dụng.
- Giới hạn nguồn mạng có thể kết nối đến Redis/database.
- Bật authentication và TLS.
- Bảo vệ credential bằng secret manager và rotation định kỳ.
- Ghi audit truy cập quản trị, nhưng không ghi dữ liệu session hoặc credential.

Namespace Redis giúp tách key theo ứng dụng nhưng không phải ranh giới bảo mật nếu ACL vẫn cho phép mọi client đọc toàn bộ key. Tương tự, prefix hoặc tên bảng JDBC không thay thế quyền database.

## 7. Bản sao lưu session chứa những gì?

Backup của Redis hoặc JDBC có thể chứa dữ liệu tương đương kho session tại thời điểm sao lưu. Tùy repository và cấu hình, dữ liệu có thể bao gồm:

- Session ID và metadata.
- Serialized session attributes.
- SecurityContext hoặc thông tin principal.
- Index principal và index phụ trợ.
- Expiration metadata hoặc bản ghi có thời hạn.
- Dữ liệu tạm thời mà ứng dụng lưu trong session.

Không giả định session data vô hại chỉ vì nó có TTL. Backup có thể tồn tại lâu hơn TTL của session gốc. Một bản snapshot được tạo hôm nay có thể chứa session đã hết hạn hoặc đã bị thu hồi sau thời điểm snapshot; nếu backup giữ nhiều tuần, dữ liệu nhạy cảm có thể tồn tại tương ứng trong kho backup.

Hãy phân loại backup session là dữ liệu nhạy cảm. Áp dụng mã hóa, kiểm soát quyền đọc, retention, audit và quy trình hủy tương tự dữ liệu xác thực.

## 8. Bảo vệ backup và snapshot

Quy trình backup an toàn cần bảo vệ cả dữ liệu, metadata và khóa:

1. Mã hóa backup trước khi ghi vào object storage hoặc kho backup, hoặc dùng encryption được nền tảng cung cấp với KMS.
2. Giới hạn quyền tạo, đọc, tải xuống và xóa backup theo vai trò.
3. Tách tài khoản backup khỏi tài khoản runtime của ứng dụng.
4. Bật versioning/immutability khi cần chống sửa hoặc xóa trái phép.
5. Dùng TLS khi truyền backup đến kho lưu trữ.
6. Ghi audit ai đã tạo, tải, khôi phục hoặc xóa backup.
7. Đặt retention phù hợp với mục tiêu khôi phục và yêu cầu dữ liệu cá nhân.
8. Hủy backup hết hạn theo chính sách, kể cả bản sao ở vùng dự phòng.
9. Không đưa backup production vào laptop hoặc môi trường development không được bảo vệ.
10. Kiểm thử khôi phục trong môi trường cô lập bằng dữ liệu và khóa được quản lý.

Nếu dùng Redis, hiểu rõ backup RDB, AOF và snapshot của dịch vụ managed. Nếu dùng JDBC, phối hợp full backup, incremental backup và log/WAL theo quy trình database. Không tự copy file dữ liệu đang ghi mà bỏ qua hướng dẫn consistency của backend.

## 9. Rủi ro khôi phục backup cũ: phiên đã thu hồi có thể sống lại

Đây là rủi ro quan trọng khi backup chứa session. Giả sử lúc 10:00 tạo snapshot khi session S còn hợp lệ. Lúc 10:15 người dùng logout và session S bị xóa khỏi Redis. Lúc 11:00 hệ thống khôi phục snapshot 10:00. Dữ liệu session S có thể xuất hiện trở lại, mặc dù người dùng đã logout trước sự cố.

Khôi phục dữ liệu cũ có thể làm sống lại:

- Session đã logout.
- Session bị quản trị viên thu hồi sau thời điểm backup.
- Session của tài khoản đã bị khóa hoặc đổi mật khẩu.
- SecurityContext chứa quyền cũ.
- Session có principal hoặc trạng thái nghiệp vụ không còn hợp lệ.

Vì vậy, khôi phục session store không chỉ là khôi phục dữ liệu. Cần có quy trình bảo đảm credential cũ không được chấp nhận sau restore nếu không thể chứng minh snapshot có trạng thái thu hồi mới nhất.

Các biện pháp:

- Sau restore, chuyển ứng dụng sang namespace session mới hoặc xóa toàn bộ session đã phục hồi trước khi mở traffic.
- Yêu cầu người dùng xác thực lại nếu tính toàn vẹn của trạng thái thu hồi không được bảo đảm.
- Dùng authentication version/session generation ở cấp tài khoản và kiểm tra phiên bản đó trong request.
- Giữ danh sách thu hồi hoặc audit state bên ngoài session store để đối chiếu sau restore.
- Không khôi phục backup cũ trực tiếp vào production đang nhận traffic mà chưa đánh giá session nào có thể được hồi sinh.

Việc đổi namespace làm ứng dụng không còn tra cứu session cũ theo namespace mới, nhưng cần phối hợp cấu hình tất cả instance và kế hoạch chuyển đổi. Nếu xóa session đã restore, xác nhận đã xóa cả index/key phụ trợ theo API hoặc quy trình được hỗ trợ của repository.

## 10. Retention của backup và session TTL là hai chính sách khác nhau

TTL trong Redis hoặc expiration trong JDBC quyết định thời gian session được xem là hợp lệ ở kho đang hoạt động. Retention của backup quyết định bản sao dữ liệu được giữ bao lâu. Xóa session khỏi Redis không tự xóa nó khỏi snapshot đã tạo trước đó.

Ví dụ:

| Chính sách | Ý nghĩa |
| --- | --- |
| Session idle timeout 30 phút | Session không hoạt động quá 30 phút sẽ hết hạn theo repository |
| Redis snapshot hằng ngày | Snapshot có thể chứa session còn tồn tại tại thời điểm snapshot |
| Backup retention 30 ngày | Dữ liệu session có thể còn trong backup tới 30 ngày |
| Backup immutable 7 ngày | Backup không thể bị sửa/xóa trong thời hạn đó theo chính sách kho |

Đặt retention dựa trên RPO/RTO, yêu cầu kiểm toán và chính sách dữ liệu cá nhân. Không giữ backup session vô thời hạn nếu không có nhu cầu rõ ràng. Nếu quy định yêu cầu xóa dữ liệu cá nhân, xác định cách xử lý cả bản sao lưu, bản sao vùng dự phòng và quy trình hết hạn.

## 11. Bảo vệ dữ liệu session trên thiết bị

Với Spring Session, dữ liệu session đầy đủ thường nằm ở server. Trên thiết bị, thành phần quan trọng nhất là session ID và dữ liệu mà frontend tự lưu hoặc cache.

Browser:

- Ưu tiên cookie HttpOnly để JavaScript không đọc trực tiếp session ID.
- Không sao chép session ID vào localStorage, sessionStorage, IndexedDB hoặc service worker cache.
- Không đưa session ID vào URL, fragment, query string hoặc analytics.
- Không cache response chứa thông tin cá nhân hoặc dữ liệu xác thực trong service worker nếu không có chính sách cache rõ.
- Dùng Cache-Control phù hợp, thường là no-store cho response nhạy cảm.
- Xóa dữ liệu hiển thị/cached state khi logout và khi session hết hạn.

Ứng dụng mobile hoặc desktop:

- Dùng secure storage được hệ điều hành bảo vệ cho credential nếu kiến trúc cần lưu token.
- Không lưu session ID trong file log, database local không mã hóa hoặc clipboard.
- Hạn chế thời gian credential được giữ và xóa khi logout.
- Bảo vệ backup thiết bị và khóa màn hình theo chính sách nền tảng.
- Không đồng bộ credential lên cloud backup cá nhân nếu không có yêu cầu và kiểm soát.

Nếu ứng dụng cần lưu bản nháp hoặc dữ liệu offline, lưu dữ liệu nghiệp vụ tối thiểu và mã hóa khi phù hợp. Không biến local cache thành bản sao lâu dài của SecurityContext hoặc session attributes.

## 12. Log, tracing và công cụ quan sát

Session ID thường xuất hiện trong cookie request, Set-Cookie response hoặc header tùy chỉnh. Các thành phần hạ tầng có thể ghi chúng vào log nếu cấu hình mặc định không lọc:

- Reverse proxy access log.
- API gateway log.
- Application request logging.
- APM agent và distributed tracing.
- Error tracker, crash report và support bundle.
- HTTP client debug log.

Redact các header Cookie, Set-Cookie và header session tùy chỉnh trước khi ghi log. Không ghi toàn bộ HttpSession attributes hoặc SecurityContext. Nếu cần correlation, tạo một request ID không có khả năng dùng để xác thực và không suy ra session ID.

Kiểm tra cả log của hệ thống backup, job restore và công cụ quản trị. Một lệnh dump Redis hoặc export database có thể vô tình được ghi vào terminal history hoặc artifact CI.

## 13. Quản lý khóa và rotation

Khóa dùng để mã hóa backup, storage hoặc thuộc tính session phải được quản lý tách khỏi dữ liệu:

- Lưu khóa trong KMS/HSM hoặc secret manager.
- Tách quyền dùng khóa với quyền đọc backup.
- Dùng key identifier để biết bản backup được mã hóa bằng khóa nào.
- Rotation có giai đoạn tương thích: ứng dụng có thể đọc dữ liệu cũ trong khi ghi dữ liệu mới bằng khóa mới.
- Giữ khóa cũ trong khoảng thời gian cần thiết để restore backup còn retention.
- Hủy khóa cũ chỉ sau khi backup và ciphertext phụ thuộc vào nó hết hạn hoặc đã được re-encrypt.
- Audit mọi thao tác decrypt, export và key administration.

Nếu khóa mã hóa backup bị mất, dữ liệu có thể không khôi phục được. Nếu khóa bị lộ, kẻ tấn công có thể giải mã backup đã lấy được. Hãy kiểm thử khôi phục với quy trình key access thực tế, không chỉ kiểm tra rằng snapshot đã được tạo.

## 14. Quy trình backup và restore an toàn

Một quy trình có thể triển khai:

1. Xác định RPO/RTO và dữ liệu session có cần được phục hồi hay không.
2. Dùng cơ chế snapshot/backup được Redis hoặc database hỗ trợ để bảo đảm consistency.
3. Mã hóa backup và truyền qua TLS đến kho riêng.
4. Áp dụng ACL, immutable retention và audit.
5. Thực hiện restore trong môi trường cô lập trước khi production.
6. Kiểm tra schema, serializer, phiên bản ứng dụng và khả năng đọc dữ liệu.
7. Đối chiếu trạng thái thu hồi session, khóa tài khoản và authentication version.
8. Nếu không thể bảo đảm session cũ vẫn hợp lệ, xóa/đổi namespace session và yêu cầu đăng nhập lại.
9. Mở traffic sau khi xác minh mọi instance dùng cùng repository và cấu hình.
10. Ghi nhận thời điểm, snapshot, key ID, người thực hiện và kết quả kiểm thử.

Không chạy restore thử trên kho session production đang được nhiều instance sử dụng. Restore có thể ghi đè session mới, làm mất logout gần đây hoặc khôi phục credential đã bị thu hồi.

## 15. Kiểm thử bảo vệ dữ liệu và backup

Kiểm thử cần chứng minh cả dữ liệu đang hoạt động lẫn bản sao lưu được bảo vệ:

| Kịch bản | Cách kiểm thử | Kết quả cần xác nhận |
| --- | --- | --- |
| HTTP transport | Gửi request qua HTTPS | Cookie Secure được phát và không gửi qua HTTP |
| Proxy-to-app | Kiểm tra hop nội bộ | TLS hoặc ranh giới mạng được bảo vệ theo thiết kế |
| Redis TLS | Kết nối bằng chứng chỉ hợp lệ và thử chứng chỉ sai | Kết nối mã hóa; certificate validation hoạt động |
| JDBC TLS | Kết nối database với verify-full | Đúng hostname/chứng chỉ; kết nối không hạ xuống plaintext |
| Cookie flags | Kiểm tra Set-Cookie | HttpOnly, Secure, SameSite, Path và Domain đúng |
| Header resolver | Kiểm tra request/response header | ID không xuất hiện trong log; client xóa ID khi logout |
| Backup encryption | Kiểm tra artifact backup và quyền đọc | Backup được mã hóa và chỉ vai trò cho phép truy cập |
| Restore | Khôi phục snapshot trong môi trường cô lập | Session và serializer được đọc đúng; quy trình thu hồi được áp dụng |
| Session revoked before snapshot restore | Tạo snapshot, logout, rồi restore snapshot | Phiên đã thu hồi không được chấp nhận sau restore theo chính sách |
| Retention | Chạy lifecycle hết hạn backup | Bản backup quá hạn bị xóa theo chính sách |
| Log redaction | Tạo request có cookie/header session | Log, trace và error report không chứa credential |
| Device storage | Kiểm tra browser/mobile client | Không lưu ID trong vùng lưu trữ không an toàn |

Không chỉ kiểm tra file backup có tồn tại. Thử restore, giải mã, đọc session, xác minh phiên bị thu hồi và xác nhận quyền truy cập backup mới chứng minh quy trình có thể vận hành an toàn.

## 16. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Session ID xuất hiện trong log | Proxy hoặc application logger ghi Cookie/header | Redact trước khi ghi và rà soát log retention |
| Backup chứa dữ liệu đọc được | Snapshot không được mã hóa hoặc quyền truy cập quá rộng | Bật encryption, ACL, audit và retention |
| Redis TLS không kết nối | Certificate, hostname hoặc trust store sai | Kiểm tra chain và hostname; không tắt xác minh |
| Browser vẫn gửi cookie qua HTTP | Cookie thiếu Secure hoặc proxy/forwarded scheme sai | Bật HTTPS và kiểm tra cấu hình cookie/proxy |
| Logout xong session sống lại sau restore | Backup được tạo trước thời điểm thu hồi | Đổi namespace, purge session hoặc dùng auth generation |
| Mobile app vẫn dùng ID cũ | Client không xóa secure storage khi logout/401 | Cập nhật logout và credential-expiry handling |
| Backup quá hạn vẫn còn | Retention không áp dụng cho bản sao phụ hoặc immutable copy | Kiểm tra toàn bộ lifecycle và replication |
| Không giải mã được backup | Khóa KMS cũ đã bị hủy hoặc quyền decrypt thiếu | Giữ khóa theo retention và thử restore định kỳ |
| Session attributes lộ trong APM | Agent thu thập payload/header không được lọc | Cấu hình redaction và giới hạn capture |

## 17. Checklist triển khai

- [ ] Lập danh sách thuộc tính session và phân loại dữ liệu nhạy cảm.
- [ ] Không lưu password, secret hoặc token dài hạn trong session nếu không cần.
- [ ] Bật HTTPS và cookie Secure, HttpOnly, SameSite phù hợp.
- [ ] Nếu dùng header resolver, bảo vệ header và client secure storage.
- [ ] Mã hóa các hop từ proxy đến app, app đến Redis/JDBC và backup transport theo trust boundary.
- [ ] Bật encryption at rest cho Redis/database, snapshot và object storage.
- [ ] Dùng ACL Redis/database tối thiểu và tách tài khoản runtime khỏi backup/admin.
- [ ] Redact Cookie, Set-Cookie và session header trong log/APM/trace.
- [ ] Quản lý khóa qua KMS/HSM/secret manager và có kế hoạch rotation.
- [ ] Đặt backup retention phù hợp; hiểu backup có thể giữ session lâu hơn TTL.
- [ ] Có quy trình restore ngăn session đã logout hoặc thu hồi bị hồi sinh.
- [ ] Kiểm thử TLS, cookie flags, backup decrypt/restore, retention và log redaction.

Spring Session giúp chia sẻ session giữa các instance nhưng cũng khiến kho session và bản sao lưu trở thành dữ liệu bảo mật quan trọng. Hãy bảo vệ session ID ở client, mã hóa từng kênh truyền và dữ liệu lưu trữ, giới hạn quyền truy cập Redis/JDBC, kiểm soát backup và khóa, đồng thời xử lý đặc biệt trường hợp restore có thể hồi sinh session đã bị thu hồi. Một quy trình an toàn cần kiểm chứng từ browser đến repository và cả vòng đời backup, không chỉ dựa vào một cờ HTTPS hoặc một thiết lập mã hóa ổ đĩa.
