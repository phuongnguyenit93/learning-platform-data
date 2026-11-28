# Quy trình phục hồi, tiêu chí xác nhận và trường hợp cần đăng nhập lại

Spring Session lưu trạng thái phiên ở một kho dùng chung như Redis hoặc JDBC để nhiều instance của ứng dụng có thể khôi phục cùng session. Khi kho dữ liệu gặp sự cố, việc khôi phục dịch vụ không chỉ là làm cho Redis/database hoạt động trở lại. Đội vận hành còn phải xác định dữ liệu session có nhất quán, đúng namespace, đọc được bởi phiên bản ứng dụng hiện tại và còn đáng tin cậy về mặt bảo mật hay không.

Session là trạng thái xác thực và tương tác có thời hạn. Nếu không thể chứng minh session được khôi phục an toàn, lựa chọn đúng thường là vô hiệu hóa các phiên bị ảnh hưởng và yêu cầu người dùng đăng nhập lại. Một lần đăng nhập mới tạo SecurityContext và session mới theo quy trình xác thực hiện tại. Điều này gây gián đoạn có kiểm soát nhưng tránh việc chấp nhận một session cũ, thiếu dữ liệu, bị phát lại hoặc được khôi phục từ snapshot không đáng tin.

Bài học này xây dựng quy trình phục hồi cho Spring Session với Redis/JDBC, các tiêu chí xác nhận trước khi mở lại traffic, cách đánh giá RTO/RPO, xử lý session sau restore, và quyết định khi nào phải đăng nhập lại. Trạng thái session không được xem là dữ liệu nghiệp vụ chuẩn: đơn hàng, thanh toán, số dư và tồn kho phải được phục hồi từ nguồn dữ liệu nghiệp vụ của chúng.

## 1. Phân biệt phục hồi dịch vụ và phục hồi session

Một backend có thể đã trả lời ping nhưng vẫn chưa sẵn sàng phục vụ Spring Session. Ví dụ:

- Redis đã khởi động nhưng ứng dụng đang kết nối nhầm database index, namespace hoặc replica.
- Database đã mở kết nối nhưng bảng session thiếu, schema migration chưa hoàn tất hoặc quyền DELETE/UPDATE chưa được khôi phục.
- Dữ liệu đã restore nhưng serializer của phiên bản ứng dụng mới không đọc được attributes cũ.
- Redis có key session nhưng các key/index phụ đã mất hoặc không nhất quán.
- JDBC có bản ghi session nhưng thiếu hàng attribute liên quan hoặc thời điểm hết hạn không phù hợp.
- Backend hoạt động nhưng một số application node vẫn giữ connection pool hoặc DNS/endpoint cũ.

Vì vậy, cần phân biệt các trạng thái:

| Trạng thái | Ý nghĩa | Hành động |
|---|---|---|
| Backend reachable | Có thể kết nối tới Redis/database | Chưa đủ điều kiện mở traffic |
| Repository operational | Có thể tạo, lưu, tìm và xóa session theo contract | Tiếp tục kiểm tra dữ liệu và bảo mật |
| Session data consistent | Session, attributes, index và expiry phù hợp | Có thể kiểm tra khả năng khôi phục người dùng |
| Authentication safe | Không chấp nhận session bị thu hồi, hết hạn hoặc không xác minh được | Có thể mở lại luồng xác thực theo chính sách |
| Service recovered | Health check, request thật và quan sát vận hành đạt tiêu chí | Mở traffic theo từng bước |

Không tuyên bố phục hồi hoàn tất chỉ vì health endpoint trả 200 hoặc vì connection pool đã tạo được kết nối.

## 2. Xác định phạm vi sự cố trước khi restore

Trước khi thao tác dữ liệu, xác định sự cố ảnh hưởng đến đâu:

- Một application instance mất kết nối nhưng Redis/JDBC vẫn khỏe.
- Một Redis primary hoặc database node gặp lỗi nhưng replica còn hoạt động.
- Toàn bộ session store mất khả năng truy cập.
- Dữ liệu bị xóa, hỏng hoặc restore từ backup.
- Secret, credential hoặc session ID có khả năng bị lộ.
- Một bản phát hành mới tạo session attributes không tương thích.
- Sai cấu hình namespace/schema khiến ứng dụng đọc nhầm kho.

Phạm vi quyết định chiến lược. Nếu chỉ một node bị lỗi kết nối và dữ liệu shared store vẫn nhất quán, có thể sửa kết nối rồi xác nhận node đó. Nếu toàn bộ session store bị mất hoặc không rõ tính toàn vẹn, cần chuẩn bị cho việc người dùng đăng nhập lại. Nếu có dấu hiệu lộ credential/session ID, phải xem đây là sự cố bảo mật và thu hồi các phiên có thể bị ảnh hưởng, không chỉ phục hồi availability.

Ghi lại thời điểm bắt đầu, thời điểm phát hiện, backend/namespace/schema bị ảnh hưởng, các phiên bản ứng dụng đang chạy và thao tác vận hành đã thực hiện. Không đưa session ID, cookie, access token hoặc dữ liệu session thô vào incident log.

## 3. Quy trình phục hồi tổng quát

Một quy trình an toàn có thể chia thành các giai đoạn:

1. **Contain:** hạn chế hoặc dừng traffic tới các node không thể xác thực session an toàn; giữ lại log và bằng chứng cần thiết.
2. **Diagnose:** xác định backend, phạm vi dữ liệu, loại lỗi và thời điểm dữ liệu cuối cùng đáng tin cậy.
3. **Recover backend:** khôi phục Redis/JDBC, network, credential, schema, replication hoặc backup theo runbook của backend.
4. **Validate repository:** kiểm tra create, save, find, delete, timeout và serialization bằng dữ liệu thử nghiệm.
5. **Decide session policy:** giữ session cũ, thu hồi một nhóm hay vô hiệu hóa toàn bộ session thuộc phạm vi ảnh hưởng.
6. **Validate application:** kiểm tra mọi instance dùng đúng endpoint, namespace, schema và serializer.
7. **Canary:** mở một phần traffic, quan sát lỗi session, login, logout và latency.
8. **Restore traffic:** tăng traffic theo từng bước sau khi tiêu chí xác nhận đạt.
9. **Communicate:** thông báo người dùng cần đăng nhập lại nếu session bị thu hồi.
10. **Review:** đối chiếu metric, ghi nhận RTO/RPO thực tế và cập nhật runbook.

~~~mermaid
flowchart TD
    A[Phát hiện session store failure] --> B[Giới hạn traffic và xác định phạm vi]
    B --> C[Khôi phục Redis hoặc JDBC]
    C --> D{Repository create/find/save/delete đạt?}
    D -->|Không| E[Giữ traffic hạn chế và tiếp tục xử lý]
    E --> C
    D -->|Có| F[Kiểm tra expiry, serialization, namespace và index]
    F --> G{Session cũ còn đáng tin?}
    G -->|Không hoặc chưa rõ| H[Thu hồi session bị ảnh hưởng]
    G -->|Có| I[Giữ session theo chính sách]
    H --> J[Kiểm tra đăng nhập mới và replay ID cũ]
    I --> K[Canary traffic]
    J --> K
    K --> L{Metric và kiểm tra đạt?}
    L -->|Không| E
    L -->|Có| M[Mở traffic và theo dõi]
~~~

Không chạy restore backup lên backend production khi chưa xác định rõ target, timestamp và phạm vi ghi đè. Backup cũ có thể làm mất session mới, khôi phục phiên đã logout hoặc đưa lại session đã bị thu hồi.

## 4. Tiêu chí RTO và RPO cho session

RTO (Recovery Time Objective) là thời gian mục tiêu để khôi phục dịch vụ. RPO (Recovery Point Objective) là mức mất dữ liệu tối đa được chấp nhận, tính theo thời điểm dữ liệu có thể phục hồi.

Với session, RPO có ý nghĩa khác dữ liệu nghiệp vụ:

- Mất session thường khiến người dùng phải đăng nhập lại hoặc dựng lại ngữ cảnh.
- Mất đơn hàng/thanh toán không thể xử lý như mất session; chúng cần backup, transaction log và quy trình phục hồi riêng.
- Restore snapshot session cũ có thể làm sống lại phiên đã logout hoặc bị thu hồi sau thời điểm backup.
- RPO gần bằng 0 cho session không phải lúc nào cũng đáng chi phí; availability và khả năng xác thực an toàn có thể quan trọng hơn việc giữ mọi phiên.

Ví dụ mục tiêu cần được tổ chức phê duyệt:

| Thành phần | RTO/RPO cần xác định | Câu hỏi vận hành |
|---|---|---|
| Redis session store | Thời gian failover/restore và lượng session có thể mất | Có thể yêu cầu login lại khi mất dữ liệu không? |
| JDBC session tables | Thời gian restore database và transaction log | Có cần point-in-time recovery hay chỉ cần tạo lại session rỗng? |
| Application nodes | Thời gian rollout/restart và readiness | Tất cả node có cùng config/secret không? |
| Authentication provider | Thời gian sẵn sàng xác thực lại | Người dùng có thể đăng nhập khi session store vừa phục hồi không? |
| Business database | RTO/RPO nghiệp vụ riêng | Có thể đối chiếu order/payment sau sự cố không? |

Đừng đặt RPO session bằng RPO database nghiệp vụ chỉ vì chúng cùng chạy trên một database server. Session có thể được tái tạo qua login; dữ liệu nghiệp vụ thường không thể tái tạo như vậy.

## 5. Quyết định giữ hay thu hồi session cũ

Không phải mọi sự cố đều bắt buộc logout tất cả người dùng. Quyết định phải dựa trên bằng chứng:

| Tình huống | Khuyến nghị |
|---|---|
| Một node mất kết nối ngắn, shared store không bị gián đoạn và không có dữ liệu stale | Có thể giữ session; xác nhận node đọc được cùng repository |
| Redis failover có thể làm mất một số ghi gần nhất nhưng dữ liệu còn lại hợp lệ | Đánh giá phạm vi mất; session thiếu có thể yêu cầu login lại |
| JDBC restore từ backup cũ hơn thời điểm logout/revoke | Thu hồi session thuộc phạm vi restore; không để phiên cũ sống lại |
| Session attributes không tương thích với phiên bản ứng dụng | Invalidate các session không deserialize được hoặc chuyển đổi theo migration đã kiểm thử |
| Namespace/schema bị thay đổi nhầm | Khôi phục đúng mapping; xác định có đọc nhầm dữ liệu của ứng dụng khác không |
| Có khả năng session ID bị lộ | Thu hồi session bị ảnh hưởng hoặc toàn bộ phạm vi có nguy cơ |
| Không xác định được tính toàn vẹn hoặc thời điểm backup | Fail closed và yêu cầu đăng nhập lại |
| Chỉ cleanup job bị lỗi nhưng repository vẫn kiểm tra expiry đúng | Có thể giữ session còn hiệu lực, xử lý backlog riêng |

Nguyên tắc: chỉ giữ session cũ khi có thể chứng minh dữ liệu còn đúng, còn hạn, thuộc đúng ứng dụng/principal và không bị thu hồi. Nếu không thể chứng minh, đăng nhập lại là biện pháp phục hồi rõ ràng hơn.

## 6. Phục hồi Redis session store

Với Spring Session Redis, quy trình phụ thuộc topology và chính sách persistence của Redis:

- Redis Sentinel hoặc Cluster có thể tự failover theo cấu hình; ứng dụng phải dùng endpoint/connection factory hỗ trợ topology đó.
- RDB snapshot và AOF có đặc tính durability khác nhau; xác định thời điểm dữ liệu cuối cùng có thể khôi phục.
- Replica có thể lag so với primary; không coi replica đã bắt kịp chỉ vì trạng thái node là healthy.
- Key TTL có thể tiếp tục giảm trong khi backend ngừng phục vụ hoặc sau restore, tùy cách dữ liệu và thời gian được khôi phục.
- Key session, expiration metadata và principal index phải được xem xét cùng nhau.

Trình tự tham khảo:

1. Xác định primary/replica, trạng thái replication, persistence và thời điểm backup.
2. Khôi phục/failover theo runbook Redis của môi trường.
3. Xác minh ứng dụng kết nối đúng endpoint, database index, TLS/ACL và namespace.
4. Tạo session thử nghiệm, lưu attribute, đọc lại từ một kết nối khác và xóa.
5. Kiểm tra TTL của key thử nghiệm và chính sách expiration event/index.
6. Xác định liệu restore có thể làm sống lại key đã logout/revoke sau thời điểm backup hay không.
7. Nếu không thể loại trừ replay session cũ, chuyển sang chính sách thu hồi session và login lại.

Không dùng FLUSHALL/FLUSHDB như bước phục hồi mặc định. Các lệnh này có thể xóa dữ liệu của ứng dụng khác hoặc toàn bộ key trong Redis database dùng chung. Nếu cần loại bỏ session, dùng namespace/database dành riêng và một thao tác có phạm vi được xác nhận.

## 7. Phục hồi Spring Session JDBC

Với JDBC, session được lưu trong các bảng Spring Session, thường gồm SPRING_SESSION và SPRING_SESSION_ATTRIBUTES. Bảng session chứa ID, thời điểm tạo/truy cập, thời điểm hết hạn và các metadata khác; bảng attributes chứa payload của session.

Trình tự tham khảo:

1. Khôi phục database theo runbook của DBMS, gồm backup và transaction log nếu cần.
2. Xác minh database/schema/table đúng với cấu hình Spring Session.
3. Kiểm tra schema version, index, foreign key và quyền SELECT/INSERT/UPDATE/DELETE.
4. Xác nhận cleanup job và query expiration hoạt động.
5. Tạo session thử nghiệm, lưu nhiều loại attribute được hỗ trợ, đọc lại và invalidate.
6. Kiểm tra session hết hạn không được trả về ngay cả khi hàng vật lý chưa được cleanup.
7. Xác định thời điểm backup so với logout, revoke và đổi mật khẩu; cân nhắc thu hồi các session cũ.

Nếu restore database từ thời điểm trước đó, các session bị logout sau thời điểm backup có thể xuất hiện trở lại. Đây là rủi ro bảo mật quan trọng. Cần có cơ chế credential/session version, revocation marker hoặc chính sách invalidate toàn bộ session trong phạm vi restore để ngăn ID cũ được sử dụng lại.

Không chạy DDL tùy tiện để “sửa nhanh” schema session trong lúc restore. So sánh schema với migration được quản lý và kiểm tra trên bản sao trước khi áp dụng. Nếu bảng attributes hoặc foreign key không nhất quán, dừng mở traffic cho đến khi repository round-trip và delete semantics đạt.

## 8. Kiểm tra namespace, schema và cấu hình mọi instance

Sau restore hoặc failover, các node phải dùng cùng cấu hình:

- Redis host/cluster, database index, namespace và serializer;
- JDBC URL, schema, table name, transaction manager và migration version;
- session timeout và chính sách cookie;
- application version và compatibility của session attributes;
- encryption key hoặc key version nếu session payload được mã hóa;
- principal index và event configuration nếu ứng dụng phụ thuộc.

Một node dùng namespace khác có thể tạo session mới trong khi node khác khôi phục session cũ. Điều này tạo lỗi đăng nhập ngẫu nhiên theo load balancer. Một node dùng serializer cũ có thể đọc session trong khi node mới không đọc được.

Tạo một kiểm tra cấu hình khi startup/readiness để xác nhận backend và schema cần thiết. Không đưa secret hoặc session ID vào health response. Có thể hiển thị trạng thái dependency, schema version và repository type ở mức an toàn.

## 9. Tiêu chí xác nhận repository đã phục hồi

Trước khi mở traffic, xác nhận các thao tác sau với backend thật:

| Kiểm tra | Cách xác minh | Điều kiện đạt |
|---|---|---|
| Connectivity | Kết nối từ mọi application node | Không có lỗi DNS, TLS, ACL, pool hoặc timeout |
| Create | Tạo session thử nghiệm | Có ID hợp lệ và không trùng |
| Save | Ghi metadata và attributes | Ghi hoàn tất theo contract |
| Find | Đọc lại session từ request/kết nối khác | Khôi phục đúng ID, timestamps, timeout và attributes |
| Expiration | Dùng timeout test ngắn hoặc fixture hết hạn | Session hết hạn không được trả như phiên hợp lệ |
| Delete | Invalidate/delete session thử nghiệm | ID không còn khôi phục được |
| Serialization | Đọc dữ liệu do phiên bản ứng dụng hiện tại ghi | Không có lỗi format/class |
| Multi-instance | Ghi ở node A, đọc ở node B | Cùng trạng thái session |
| Revocation | Thử ID đã logout/thu hồi | ID cũ không được xác thực |
| Monitoring | Quan sát metric/log | Error rate và latency nằm trong ngưỡng |

Một lệnh ping hoặc câu SELECT 1 chỉ xác nhận kết nối cơ bản. Nó không chứng minh repository có thể serialize, lưu, khôi phục, hết hạn và xóa session đúng.

## 10. Canary và mở traffic theo từng bước

Sau khi backend đạt kiểm tra cơ bản:

1. Khởi động một application node với đúng config/secret.
2. Chạy synthetic login/session round-trip bằng tài khoản kiểm thử.
3. Xác nhận request kế tiếp có thể đi tới node khác và khôi phục cùng session.
4. Thử logout và replay ID cũ.
5. Theo dõi repository latency, error rate, login failure, session creation và expiration.
6. Mở một phần traffic, sau đó tăng dần theo tiêu chí đã định.
7. Giữ khả năng rollback nếu lỗi tăng hoặc dữ liệu session có dấu hiệu không nhất quán.

Không dùng tài khoản người dùng thật hoặc session cookie thật trong synthetic test. Tài khoản test phải có quyền tối thiểu và dữ liệu có thể xóa sau kiểm tra.

## 11. Khi nào phải yêu cầu người dùng đăng nhập lại?

Đăng nhập lại là lựa chọn phù hợp trong các trường hợp:

- session store bị mất dữ liệu và không thể khôi phục session cũ;
- restore từ backup có thể làm sống lại session đã logout hoặc revoke;
- session attributes không tương thích với phiên bản ứng dụng;
- không thể xác định session còn thuộc đúng principal hoặc còn hạn;
- encryption/signing key đã thay đổi hoặc có khả năng bị lộ;
- session ID hoặc cookie có nguy cơ bị đánh cắp;
- namespace/index bị hỏng và không thể xác minh mapping;
- chính sách bảo mật yêu cầu thu hồi tất cả phiên sau incident.

Không bắt người dùng đăng nhập lại chỉ vì một node tạm thời mất kết nối nếu shared store vẫn nhất quán và session có thể được xác minh sau khi node phục hồi. Tránh tạo logout diện rộng không cần thiết vì nó làm tăng login burst, tải identity provider và áp lực lên session store vừa phục hồi.

Khi cần đăng nhập lại, thông báo rõ rằng phiên đã hết hiệu lực và người dùng cần xác thực lại. Không yêu cầu người dùng gửi cookie cũ, session ID hoặc mật khẩu qua kênh hỗ trợ.

## 12. Thu hồi session cũ một cách có kiểm soát

Có nhiều cách thực hiện tùy repository và phạm vi:

### Thu hồi theo principal

Nếu repository hỗ trợ tìm session theo principal, có thể liệt kê và invalidate các phiên của một người dùng hoặc nhóm người dùng. Cần bảo đảm principal index được populate và không bị hỏng sau restore.

### Thu hồi theo namespace

Nếu toàn bộ session thuộc một ứng dụng/namespace bị ảnh hưởng, có thể xóa dữ liệu trong phạm vi đó theo công cụ được phê duyệt. Xác minh key pattern/schema trước khi chạy; không xóa toàn bộ Redis database dùng chung.

### Credential/session version

Ứng dụng có thể lưu một version xác thực hoặc session generation trong kho dữ liệu có thẩm quyền. Session chứa version tại thời điểm đăng nhập; mỗi request bảo vệ so sánh với version hiện tại. Tăng version có thể vô hiệu hóa các session cũ mà không cần tìm và xóa từng session ngay lập tức.

Ví dụ ý tưởng:

~~~java
boolean isCurrentSession(long sessionVersion,
                         long accountSessionVersion) {
    return sessionVersion == accountSessionVersion;
}
~~~

Đây chỉ là phép kiểm tra minh họa. Giá trị hiện tại phải đến từ nguồn tin cậy, có consistency phù hợp và được kiểm tra ở service/filter boundary theo chính sách. Không lưu version hiện hành chỉ trong session; như vậy restore session cũ vẫn có thể mang version cũ và tự xác nhận sai.

### Revocation marker

Một marker cho biết session ID hoặc generation đã bị thu hồi có thể giúp ngăn replay khi backend session được restore. Marker phải được lưu ở nơi không bị rollback cùng snapshot session hoặc được cập nhật sau restore. Bảo đảm TTL của marker dài hơn thời gian mà session cũ có thể bị phát lại.

Không thiết kế marker dựa trên session ID trong log hoặc metric; ID phải được xử lý như credential. Nếu marker store cũng không đáng tin cậy, chọn invalidate toàn bộ session và xác thực lại.

## 13. Tái xác thực và tạo session mới

Khi người dùng đăng nhập lại:

1. Browser gửi request tới endpoint login bằng HTTPS.
2. Spring Security xác thực credential/MFA theo chính sách hiện tại.
3. Session fixation protection đổi session ID ở ranh giới xác thực.
4. SecurityContext mới được lưu vào session mới theo repository.
5. Response phát cookie session mới với Secure, HttpOnly và SameSite phù hợp.
6. Request tiếp theo khôi phục session mới từ Redis/JDBC.

Không tái sử dụng cookie/session ID cũ chỉ vì browser vẫn giữ cookie đó. Sau khi thu hồi, server phải từ chối ID cũ. Việc xóa cookie ở client giúp tránh gửi lại ID cũ nhưng không thay thế việc invalidate phía server.

Nếu hệ thống dùng MFA hoặc step-up authentication, có thể yêu cầu xác thực bổ sung sau sự cố tùy mức độ rủi ro. Không nên tự động hạ cấp phương thức xác thực chỉ để giảm gián đoạn.

## 14. Khác biệt giữa khôi phục session và khôi phục dữ liệu nghiệp vụ

Session có thể tái tạo sau login; dữ liệu nghiệp vụ cần quy trình khôi phục riêng:

| Dữ liệu | Nguồn khôi phục | Có thể yêu cầu login lại thay cho restore không? |
|---|---|---|
| Session ID và attributes | Redis/JDBC session repository | Có thể invalidate và tạo session mới |
| SecurityContext | Session mới sau xác thực | Có thể xác thực lại |
| Giỏ hàng | Database/cache nghiệp vụ tùy thiết kế | Không được giả định mất session đồng nghĩa mất giỏ |
| Đơn hàng | Order database | Không; phải khôi phục dữ liệu nghiệp vụ |
| Thanh toán | Payment ledger/provider reconciliation | Không; cần đối soát giao dịch |
| Số dư/tồn kho | Database/ledger/inventory service | Không; cần transaction và đối soát |
| Workflow đang dở | Workflow store hoặc database | Khôi phục theo trạng thái nghiệp vụ |

Không dùng snapshot session để phục hồi order, balance hoặc inventory. Không kết luận một giao dịch thất bại chỉ vì browser mất session; truy vấn trạng thái giao dịch theo idempotency key hoặc mã tham chiếu nghiệp vụ.

## 15. Session attributes không tương thích sau deployment

Rolling deployment có thể làm các node chạy hai phiên bản ứng dụng cùng lúc. Session được ghi bởi phiên bản mới có thể chứa attribute mà phiên bản cũ không deserialize được. Khi restore sau incident, vấn đề này càng dễ xuất hiện nếu backup được tạo từ phiên bản trước.

Chiến lược:

- ưu tiên lưu kiểu dữ liệu ổn định hoặc ID tham chiếu thay vì object graph lớn;
- version hóa payload nếu ứng dụng tự quản lý serialization;
- hỗ trợ đọc định dạng cũ trong giai đoạn chuyển đổi nếu cần;
- triển khai theo thứ tự tương thích đọc/ghi;
- kiểm thử session fixture từ phiên bản trước;
- nếu không thể chuyển đổi an toàn, invalidate các session không tương thích và yêu cầu login lại.

Không bắt lỗi deserialize rồi tiếp tục dùng một phần SecurityContext. Nếu payload xác thực bị lỗi hoặc không đầy đủ, phải fail closed.

## 16. Bảo mật khi restore từ backup

Backup có thể chứa bearer session state và dữ liệu cá nhân. Quy trình restore cần:

- xác minh nguồn backup và quyền truy cập;
- ghi nhận timestamp, checksum hoặc metadata integrity theo nền tảng;
- chỉ restore vào đúng cluster/database/namespace;
- kiểm soát người phê duyệt và người thực hiện;
- không sao chép backup session sang môi trường ít bảo vệ hơn;
- bảo vệ encryption keys và secrets độc lập với backup;
- đánh giá session đã bị logout/revoke sau thời điểm backup;
- invalidate session nếu không thể bảo đảm trạng thái thu hồi;
- xóa bản sao tạm sau khi hoàn tất theo chính sách retention.

Nếu secret hoặc key mã hóa session bị lộ, chỉ restore dữ liệu không đủ. Cần rotate secret theo kế hoạch tương thích, vô hiệu hóa phiên có thể bị giải mã/giả mạo và kiểm tra các credential liên quan.

## 17. Health check và readiness sau phục hồi

Health check nên phân biệt:

- **Liveness:** tiến trình ứng dụng còn sống và có thể tiếp tục chạy.
- **Readiness:** node có thể phục vụ traffic theo yêu cầu chức năng, bao gồm dependency bắt buộc cho session.
- **Dependency health:** Redis/JDBC có thể kết nối và thực hiện thao tác cần thiết.

Không nhất thiết restart ứng dụng chỉ vì session store tạm thời lỗi. Liveness có thể vẫn healthy trong khi readiness chuyển sang refusing traffic nếu request bảo vệ không thể hoạt động an toàn.

Readiness probe nên nhẹ và có timeout. Một thao tác create/save/find/delete probe có thể tạo tải hoặc dữ liệu rác nếu chạy quá thường xuyên; nếu cần synthetic repository check, chạy theo chu kỳ riêng và dọn dữ liệu thử nghiệm.

Sau khi backend phục hồi, không bật readiness chỉ dựa trên một lần ping. Xác minh repository round-trip, schema/namespace và chính sách session cũ trước.

## 18. Runbook mẫu khi Redis session store mất dữ liệu

1. Tạm dừng hoặc giới hạn traffic tới các node không thể khôi phục session an toàn.
2. Xác định Redis topology, primary/replica, persistence và thời điểm dữ liệu cuối cùng đáng tin.
3. Khôi phục/failover theo runbook Redis; xác minh endpoint, TLS, ACL, database index và namespace.
4. Kiểm tra keyspace/replication/memory và trạng thái notification nếu ứng dụng phụ thuộc.
5. Dùng một session thử nghiệm để create, save, find, expire và delete.
6. Đánh giá khả năng restore làm sống lại session đã logout/revoke hoặc session ID bị lộ.
7. Nếu không chứng minh được an toàn, thu hồi namespace session bị ảnh hưởng hoặc tăng credential/session generation.
8. Khởi động một application node, xác minh login mới và replay ID cũ bị từ chối.
9. Canary traffic, theo dõi repository errors, login rate, session creation rate và latency.
10. Mở traffic theo từng bước và thông báo người dùng đăng nhập lại nếu cần.

Không chạy FLUSHALL hoặc FLUSHDB nếu Redis còn chứa dữ liệu khác. Phạm vi xóa phải được xác nhận bằng namespace/database và backup phù hợp.

## 19. Runbook mẫu khi JDBC session tables bị hỏng

1. Xác định database/schema và thời điểm backup/transaction log.
2. Khôi phục database theo quy trình DBA; không sửa trực tiếp bảng production khi chưa có bản sao kiểm thử.
3. Kiểm tra SPRING_SESSION, SPRING_SESSION_ATTRIBUTES, index, foreign key và quyền.
4. Xác minh migration/schema version tương thích với ứng dụng.
5. Chạy repository round-trip: create, save, find, update và delete.
6. Kiểm tra EXPIRY_TIME; session hết hạn không được khôi phục dù hàng chưa cleanup.
7. So sánh timestamp backup với logout/revoke và đổi mật khẩu.
8. Nếu restore có thể làm sống lại session cũ, invalidate phạm vi bị ảnh hưởng hoặc áp dụng version/revocation marker.
9. Canary một node, thử login mới và request qua node thứ hai.
10. Mở traffic, theo dõi query latency, pool, cleanup backlog và lỗi serialization.

Không xóa mọi hàng session chỉ để làm cho ứng dụng khởi động nếu chưa thông báo và xác định tác động. Nếu quyết định buộc mọi người đăng nhập lại, ghi rõ phạm vi, lý do và thời điểm thực hiện.

## 20. Tiêu chí xác nhận phục hồi hoàn tất

Chỉ đóng incident khi các điều kiện liên quan đều đạt:

- Redis/JDBC primary/cluster/database hoạt động và topology đúng.
- Mọi application node dùng cùng endpoint, namespace/schema, serializer và timeout.
- Repository create/save/find/delete hoạt động qua đường tích hợp thật.
- Session hết hạn không được khôi phục.
- Session đã logout/revoke không được replay.
- Session attributes được đọc bởi phiên bản ứng dụng hiện tại.
- Login mới tạo session ID mới và request tiếp theo khôi phục được.
- Các node chia sẻ session đúng theo thiết kế.
- Health/readiness phản ánh đúng khả năng phục vụ.
- Error rate, latency, connection pool và cleanup backlog nằm trong ngưỡng.
- Người dùng bị ảnh hưởng đã nhận thông báo đăng nhập lại nếu chính sách yêu cầu.
- Dữ liệu nghiệp vụ đã được đối soát độc lập nếu sự cố có ảnh hưởng đến business database.

Ghi lại số liệu trước/sau, thời gian phục hồi, lượng session bị thu hồi, tỷ lệ login lại và lỗi phát sinh trong canary. Không dùng “dashboard xanh” làm tiêu chí duy nhất.

## 21. Kiểm thử diễn tập phục hồi

Phục hồi phải được diễn tập định kỳ trong môi trường staging hoặc môi trường cô lập:

| Kịch bản | Thực hiện | Kết quả cần chứng minh |
|---|---|---|
| Redis failover | Dừng primary hoặc chuyển endpoint theo kịch bản | App kết nối lại, session được xác minh |
| Redis restore cũ | Restore snapshot trước một số logout | Session đã revoke không sống lại |
| JDBC restore | Khôi phục backup vào database test | Schema và repository hoạt động |
| Schema mismatch | Dùng migration version không phù hợp | Readiness không mở traffic sai |
| Serialization mismatch | Tạo session fixture từ app version cũ | Migration hoặc login lại theo chính sách |
| Secret rotation | Thay encryption/connection secret | Node dùng key/secret đúng và session cũ được xử lý |
| Partial node failure | Một node không kết nối được store | Load balancer/readiness loại node theo chính sách |
| Session replay | Gửi cookie cũ sau revoke | Server từ chối ID cũ |
| Login burst | Nhiều người dùng xác thực lại | Identity provider và session store chịu tải |
| Recovery rollback | Canary thất bại | Có thể quay lại cấu hình/backend ổn định mà không làm hỏng dữ liệu |

Đo RTO từ thời điểm phát hiện đến khi traffic an toàn được phục vụ; đo RPO từ thời điểm dữ liệu cuối cùng đáng tin cậy. Ghi lại các bước thủ công gây chậm và tự động hóa khi phù hợp.

## 22. Chuẩn bị cho lượng đăng nhập lại tăng đột biến

Nếu phải invalidate nhiều session, login traffic có thể tăng mạnh trong thời gian ngắn. Chuẩn bị:

- capacity của identity provider, MFA provider và database người dùng;
- rate limit hợp lý để tránh brute force nhưng không khóa nhầm toàn bộ người dùng;
- connection pool và write throughput của Redis/JDBC;
- autoscaling cho application nodes;
- cơ chế backoff cho client và thông báo retry;
- hỗ trợ người dùng không thể truy cập email/MFA;
- dashboard theo dõi login success/failure, session create rate và repository latency.

Không tự động tạo session anonymous thay cho login để giảm tải. Không hạ yêu cầu MFA hoặc bỏ kiểm tra credential trong sự cố. Nếu cần mở traffic theo nhóm, ưu tiên canary hoặc cohort có kiểm soát.

## 23. Truyền thông với người dùng và bộ phận hỗ trợ

Thông báo nên nêu:

- người dùng có thể cần đăng nhập lại;
- dữ liệu nghiệp vụ như đơn hàng đã xác nhận vẫn được truy cập qua tài khoản sau đăng nhập nếu hệ thống nghiệp vụ không bị ảnh hưởng;
- không yêu cầu gửi session cookie, session ID, mật khẩu hoặc mã MFA cho nhân viên hỗ trợ;
- nếu thao tác trước sự cố không rõ kết quả, người dùng nên tra cứu trạng thái theo mã giao dịch thay vì gửi lại thao tác tạo giao dịch mới;
- kênh hỗ trợ chính thức và cách khôi phục MFA nếu cần.

Không tuyên bố dữ liệu nghiệp vụ an toàn nếu chưa đối soát. Session store và business database có thể bị ảnh hưởng bởi các sự cố khác nhau.

## 24. Lỗi thường gặp trong phục hồi

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Mở traffic sau khi Redis ping thành công | Repository hoặc namespace vẫn sai | Chạy round-trip session qua ứng dụng |
| Restore backup session cũ mà không đánh giá logout | Session đã thu hồi có thể sống lại | So sánh thời điểm backup và revoke; invalidate nếu không chắc |
| Dùng FLUSHALL trên Redis dùng chung | Xóa dữ liệu ứng dụng khác | Xác định namespace/database và phạm vi thao tác |
| Chỉ kiểm tra JDBC SELECT 1 | Schema/permission/serialization có thể vẫn lỗi | Test create/save/find/delete thật |
| Giữ session có serialization failure | Có thể dùng SecurityContext không đầy đủ | Fail closed và yêu cầu login lại |
| Coi session mất là order mất | Xử lý nghiệp vụ sai hoặc tạo giao dịch trùng | Tra cứu order/payment từ nguồn chuẩn |
| Chỉ xóa cookie phía client | ID cũ vẫn có thể được replay | Invalidate server-side hoặc dùng revocation/version |
| Mở mọi node cùng lúc | Lỗi cấu hình lặp trên toàn cụm | Canary và kiểm tra node-by-node |
| Không chuẩn bị login burst | Identity provider hoặc store quá tải | Capacity plan, backoff và autoscaling |
| Không diễn tập restore | RTO thực tế vượt mục tiêu | Recovery drill và runbook được kiểm chứng |

## 25. Checklist phục hồi

- [ ] Phạm vi sự cố và thời điểm dữ liệu cuối cùng đáng tin cậy đã được xác định.
- [ ] Đã phân biệt session store với business data store.
- [ ] Redis/JDBC được phục hồi theo runbook của backend.
- [ ] Endpoint, credential, TLS, namespace/schema và migration được xác minh.
- [ ] Mọi node dùng cùng cấu hình và serializer tương thích.
- [ ] Repository create/save/find/delete đã được kiểm thử.
- [ ] Expiration logic và cleanup được xác minh riêng.
- [ ] Đã đánh giá khả năng restore làm sống lại session đã logout/revoke.
- [ ] Session ID cũ bị từ chối sau revoke/rotation.
- [ ] Đã quyết định rõ giữ session, thu hồi theo principal/namespace hay invalidate toàn bộ.
- [ ] Login mới và session mới hoạt động qua nhiều instance.
- [ ] Readiness, metric, log và alert đạt tiêu chí.
- [ ] Có kế hoạch xử lý login burst nếu yêu cầu đăng nhập lại diện rộng.
- [ ] Người dùng và support team nhận thông tin phù hợp.
- [ ] RTO/RPO thực tế, dữ liệu mất và hành động tiếp theo được ghi nhận.

## 26. Nguyên tắc kết luận

- Backend reachable chưa đồng nghĩa session repository đã phục hồi.
- Xác nhận create, save, find, delete, expiration, serialization và multi-instance trước khi mở traffic.
- Phân biệt dữ liệu session còn hiệu lực với bản ghi vật lý còn tồn tại.
- Đánh giá backup timestamp so với logout, revoke và thay đổi credential.
- Không restore session cũ một cách mù quáng; có thể làm sống lại định danh đã thu hồi.
- Khi không thể chứng minh tính toàn vẹn, fail closed và yêu cầu đăng nhập lại.
- Xóa cookie ở browser không thay thế thu hồi session phía server.
- Session có thể được tái tạo sau login; order, payment, balance và inventory phải được khôi phục từ nguồn nghiệp vụ.
- Mở traffic bằng canary, theo dõi metric và có rollback plan.
- Diễn tập RTO/RPO và login burst trước khi sự cố thật xảy ra.

Quy trình phục hồi Spring Session kết thúc khi ứng dụng có thể xác thực an toàn, repository hoạt động nhất quán trên mọi node và các session cũ đã được xử lý theo chính sách rõ ràng. Nếu dữ liệu phiên không còn đáng tin, yêu cầu người dùng đăng nhập lại là một kết quả phục hồi hợp lệ. Điều cần bảo đảm là session mới được tạo từ quy trình xác thực hiện tại, ID cũ không thể được phát lại và dữ liệu nghiệp vụ được đối soát từ kho dữ liệu sở hữu nó.

## Tài liệu tham khảo

- Spring Session – HttpSession integration: https://docs.spring.io/spring-session/reference/http-session.html
- Spring Session – Redis configuration: https://docs.spring.io/spring-session/reference/configuration/redis.html
- Spring Session – JDBC configuration: https://docs.spring.io/spring-session/reference/configuration/jdbc.html
- Spring Security – Session management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Redis – Persistence: https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
- PostgreSQL – Backup and restore: https://www.postgresql.org/docs/current/backup.html
