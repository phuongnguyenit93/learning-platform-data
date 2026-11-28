# Quyền truy cập Redis, cơ sở dữ liệu và phạm vi tài khoản dịch vụ

## Mục tiêu bài học

Spring Session lưu trạng thái phiên ở một kho dữ liệu dùng chung như Redis hoặc JDBC. Kho dữ liệu này có thể chứa Session ID, thời hạn phiên, thuộc tính ứng dụng và cả thông tin xác thực được Spring Security lưu trong SecurityContext. Vì vậy, tài khoản kết nối của ứng dụng có quyền đọc hoặc sửa session cũng có thể tác động đến danh tính và quyền của người dùng đang đăng nhập.

Thiết kế quyền truy cập cần giới hạn chính xác tài nguyên, thao tác và môi trường mà mỗi tài khoản được phép sử dụng. Ứng dụng runtime cần quyền để đọc, tạo, cập nhật và xóa session theo hoạt động bình thường. Nó thường không cần quyền quản trị Redis, tạo schema, sửa bảng hoặc truy cập dữ liệu của ứng dụng khác. Tài khoản migration, quản trị và vận hành phải có phạm vi riêng.

Sau bài học, bạn có thể:

- Giải thích vì sao quyền đọc/ghi session có ảnh hưởng trực tiếp đến bảo mật xác thực.
- Thiết kế Redis ACL theo tài khoản ứng dụng, key namespace và channel cần thiết.
- Cấp quyền SQL tối thiểu cho các bảng Spring Session.
- Tách tài khoản runtime, migration, backup và break-glass.
- Phân biệt service account của ứng dụng với danh tính người dùng cuối.
- Giới hạn quyền theo môi trường, ứng dụng và tenant.
- Quản lý credential, TLS, rotation và audit.
- Kiểm thử cả thao tác được phép lẫn thao tác phải bị từ chối.
- Tránh dùng namespace hoặc logical database như ranh giới bảo mật duy nhất.

## 1. Vì sao kho session là tài nguyên nhạy cảm?

Một session có thể chứa nhiều loại dữ liệu:

- Định danh phiên do client gửi qua cookie hoặc header.
- Thời gian tạo, thời gian truy cập gần nhất và thời hạn hết hiệu lực.
- Thuộc tính ứng dụng như giỏ hàng, locale hoặc trạng thái quy trình.
- Thông tin principal hoặc SecurityContext do Spring Security lưu.
- Các thuộc tính tùy chỉnh mà ứng dụng đưa vào session.

Nếu một tài khoản trái phép đọc được dữ liệu session, họ có thể thu thập thông tin nhạy cảm hoặc Session ID còn hiệu lực. Nếu tài khoản đó sửa được session, họ có thể thay đổi thuộc tính, làm sai trạng thái xác thực hoặc gây lỗi cho người dùng. Nếu xóa session, họ có thể buộc người dùng đăng nhập lại hoặc làm gián đoạn dịch vụ.

Quyền truy cập kho session vì thế gần với quyền truy cập vào một phần trạng thái bảo mật của ứng dụng. Không nên coi Redis hoặc các bảng JDBC session là cache vô hại.

### Ba tác động chính của quyền quá rộng

| Quyền quá rộng | Tác động có thể xảy ra |
|---|---|
| Đọc mọi key hoặc mọi hàng session | Lộ Session ID, thuộc tính và dữ liệu xác thực |
| Ghi hoặc sửa session ngoài phạm vi | Giả mạo trạng thái, làm hỏng phiên hoặc ảnh hưởng người dùng khác |
| Xóa hàng loạt hoặc quản trị kho dữ liệu | Đăng xuất diện rộng, gián đoạn hoặc phá hủy dữ liệu |

Ứng dụng cần quyền đọc/ghi đủ để hoạt động, nhưng phạm vi quyền phải giới hạn theo đúng kho session mà ứng dụng sở hữu.

## 2. Phân biệt service account và tài khoản người dùng

Service account là danh tính kỹ thuật mà tiến trình ứng dụng dùng để kết nối đến Redis hoặc database. Nó đại diện cho workload Spring Session, không đại diện cho người dùng đang đăng nhập.

Ví dụ:

- **spring-session-prod-runtime**: tài khoản runtime của ứng dụng production.
- **spring-session-migration**: tài khoản dùng khi triển khai schema hoặc migration.
- **platform-backup**: tài khoản của hệ thống backup theo chính sách riêng.
- **operator-breakglass**: tài khoản khẩn cấp được cấp quyền có kiểm soát.

Người dùng cuối như Alice hoặc Bob được xác thực ở tầng Spring Security. Họ không cần và không nên nhận credential Redis hay database.

### Hai lớp kiểm soát khác nhau

| Lớp | Câu hỏi cần trả lời | Cơ chế |
|---|---|---|
| Hạ tầng dữ liệu | Tiến trình nào được kết nối và thao tác trên key/table nào? | Redis ACL, SQL grants, network policy, TLS |
| Ứng dụng | Người dùng nào được xem hoặc thay đổi dữ liệu nghiệp vụ nào? | Authentication, authorization, tenant checks, service logic |

Redis ACL không thay thế authorization trong Spring Security. Ngược lại, việc Spring Security kiểm tra quyền người dùng cũng không làm cho tài khoản Redis được phép truy cập mọi key trở nên an toàn.

Nếu tất cả request của người dùng đều chạy qua một service account, database chỉ nhìn thấy tài khoản ứng dụng đó. Việc giới hạn dữ liệu theo user hoặc tenant vẫn phải được thực hiện ở tầng ứng dụng hoặc bằng thiết kế database riêng phù hợp.

## 3. Nguyên tắc least privilege

Least privilege nghĩa là mỗi danh tính chỉ có những quyền cần thiết để hoàn thành nhiệm vụ được giao, trong thời gian và phạm vi cần thiết.

Áp dụng cho Spring Session:

1. Một service account riêng cho mỗi ứng dụng hoặc workload cần ranh giới truy cập độc lập.
2. Tách tài khoản theo môi trường dev, test, staging và production.
3. Chỉ cho runtime truy cập key namespace hoặc schema của ứng dụng.
4. Chỉ cấp các lệnh Redis và quyền SQL thực sự cần.
5. Không cấp quyền quản trị server cho tiến trình web.
6. Dùng tài khoản riêng cho schema migration và backup.
7. Đặt thời hạn, rotation và quy trình thu hồi credential.
8. Ghi nhận và rà soát thay đổi quyền.
9. Kiểm thử rằng truy cập ngoài phạm vi bị từ chối.
10. Định kỳ loại bỏ quyền không còn được sử dụng.

Không cấp **ALL PRIVILEGES**, Redis **+@all** hoặc quyền owner database cho tài khoản runtime chỉ để tránh lỗi permission trong lúc triển khai.

### Ma trận danh tính và quyền

| Danh tính | Quyền phù hợp | Không nên cấp mặc định |
|---|---|---|
| Runtime Spring Session | Đọc/ghi/xóa session trong phạm vi ứng dụng | Redis CONFIG, FLUSHALL, ACL SETUSER, DROP DATABASE |
| Schema migration | Tạo/sửa schema và index trong cửa sổ triển khai | Dùng thường trực trong runtime |
| Backup | Đọc dữ liệu hoặc snapshot theo công cụ backup | Ghi session nghiệp vụ hoặc sửa schema |
| Monitoring | Đọc metric và health theo phạm vi | Đọc toàn bộ payload session |
| Break-glass operator | Quyền khẩn cấp có phê duyệt, thời hạn và audit | Credential dùng chung, không giới hạn thời gian |

Quyền chính xác phụ thuộc Redis version, Spring Session repository, driver, database và tính năng ứng dụng. Hãy đo và kiểm tra các thao tác thực tế trước khi chốt ACL/grants.

## 4. Tách môi trường và phạm vi ứng dụng

Không nên dùng cùng một credential cho dev, staging và production. Nếu credential của môi trường thử nghiệm bị lộ, nó không được phép mở đường vào kho session production.

Ví dụ cách phân chia:

~~~text
Redis production
  user: shop-session-prod
  keys: shop:prod:spring-session:*

Redis staging
  user: shop-session-staging
  keys: shop:staging:spring-session:*

Database production
  role: shop_session_runtime
  schema: shop_session

Database staging
  role: shop_session_staging
  schema: shop_session_staging
~~~

Tên chỉ là ví dụ. Mỗi môi trường cần credential, secret, endpoint và quyền độc lập.

Nếu nhiều ứng dụng cùng dùng một Redis cluster, hãy cấp ACL key pattern riêng cho từng ứng dụng. Nếu cần ranh giới mạnh hơn hoặc ứng dụng có mức độ nhạy cảm khác nhau, dùng Redis deployment hoặc database/schema tách biệt thay vì dựa hoàn toàn vào quy ước tên key.

### Namespace không tự tạo ranh giới bảo mật

Spring Session Redis có thể dùng namespace để thêm prefix vào key. Namespace giúp tránh va chạm key giữa các ứng dụng và môi trường. Nhưng namespace chỉ là quy ước đặt tên nếu ACL không giới hạn key tương ứng.

Nếu service account có quyền **~***, việc ứng dụng đặt namespace **shop:prod:spring-session** không ngăn credential đó đọc key của ứng dụng khác.

Cần kết hợp namespace với Redis ACL key pattern hoặc tách hạ tầng khi cần isolation mạnh hơn.

### Logical database của Redis không phải biên bảo mật

Redis logical database (ví dụ DB 0, DB 1) chủ yếu là cách phân vùng keyspace trong cùng server. Nó không thay thế ACL key pattern, user riêng hoặc instance riêng. Một client có quyền rộng vẫn có thể có khả năng chuyển database hoặc truy cập tài nguyên khác tùy cấu hình.

Trong Redis Cluster, logical database khác 0 không được hỗ trợ như standalone. Vì vậy, không thiết kế isolation production chỉ dựa vào số database.

## 5. Giới hạn quyền Redis bằng ACL

Redis ACL cho phép tạo user với trạng thái bật/tắt, mật khẩu, key pattern, channel pattern và tập lệnh được phép.

Một ứng dụng Spring Session nên dùng user riêng thay vì dùng user **default** chung cho mọi workload. User runtime chỉ được truy cập key prefix mà ứng dụng sở hữu.

Ví dụ ý tưởng:

~~~text
ACL SETUSER shop-session-prod reset on >LONG_RANDOM_SECRET ~shop:prod:spring-session:*
~~~

Lệnh trên minh họa việc bật user, đặt mật khẩu và giới hạn key pattern. Nó chưa cấp command permissions, vì vậy chưa đủ để ứng dụng hoạt động. Cần bổ sung đúng lệnh mà repository và các tính năng đang bật sử dụng.

Redis ACL hỗ trợ pattern key. Với Redis version hỗ trợ read/write key pattern riêng, có thể phân biệt quyền đọc và ghi bằng cú pháp ACL tương ứng. Hãy kiểm tra tài liệu của đúng Redis version trước khi áp dụng.

### Vì sao không nên cấp +@all?

**+@all** cho phép toàn bộ command mà Redis nhận diện cho user đó. Với tài khoản runtime, điều này có thể mở rộng quyền đến các thao tác quản trị, xóa dữ liệu hoặc thay đổi cấu hình không cần thiết.

Tương tự, cấp **~*** cho phép truy cập key ngoài namespace của ứng dụng.

Một tài khoản session runtime không nên có quyền:

- Thay đổi ACL user khác.
- Thay đổi cấu hình server.
- Dừng hoặc khởi động server.
- Xóa toàn bộ keyspace hoặc database.
- Truy cập key của ứng dụng khác.
- Chạy command nguy hiểm không cần cho session repository.

### Command permissions phải dựa trên repository thật

Spring Session Redis có thể thao tác với hash, string, sorted set, set, expiration và pub/sub tùy repository, phiên bản và tính năng được bật. Các lệnh có thể gồm nhóm như GET, SET, DEL, EXISTS, EXPIRE/PEXPIRE, PTTL, HGETALL, HSET, HDEL, SADD, SREM, ZADD, ZREM, ZRANGE hoặc PUBLISH/SUBSCRIBE.

Danh sách này chỉ minh họa các nhóm thao tác thường gặp; không phải ACL hoàn chỉnh để sao chép cho mọi phiên bản. Implementation có thể dùng thêm lệnh khác hoặc thay đổi cách lưu.

Quy trình đúng:

1. Chọn chính xác Spring Session và Spring Data Redis version.
2. Dùng repository, save/flush mode và expiration settings giống production.
3. Chạy integration test với Redis ACL user giới hạn.
4. Ghi nhận command bị từ chối và key pattern tương ứng trong môi trường test.
5. Bổ sung từng command/key/channel cần thiết.
6. Lặp lại toàn bộ luồng tạo, đọc, cập nhật, expire và xóa session.
7. Xác nhận các command quản trị và key ngoài namespace vẫn bị từ chối.

Không cấp rộng toàn bộ command categories chỉ để làm cho test pass.

## 6. Key namespace và Redis ACL pattern

Spring Session Redis có thể tạo nhiều key cho một session: dữ liệu session, thông tin expiration, index theo principal hoặc metadata phục vụ cleanup. Tên và cấu trúc key phụ thuộc repository, namespace và phiên bản.

Nếu namespace là **shop:prod:spring-session**, ACL key pattern có thể bắt đầu từ:

~~~text
~shop:prod:spring-session:*
~~~

Nhưng trước khi chốt pattern, hãy kiểm tra mọi key mà repository thực sự tạo. Một số cấu trúc phụ trợ có thể dùng prefix hoặc pattern khác theo cấu hình.

### Tránh pattern quá rộng

Ví dụ sau không có giới hạn hữu ích:

~~~text
~*
~~~

Nó cho phép user truy cập toàn bộ key phù hợp với pattern. Nếu Redis dùng chung nhiều ứng dụng, rủi ro ảnh hưởng chéo tăng đáng kể.

Nên dùng prefix riêng theo:

- Tên ứng dụng.
- Môi trường.
- Loại dữ liệu.
- Tenant hoặc vùng dữ liệu nếu kiến trúc yêu cầu.

Ví dụ:

~~~text
shop:prod:spring-session:...
billing:prod:spring-session:...
shop:staging:spring-session:...
~~~

Key prefix giúp phân chia phạm vi, nhưng vẫn phải kết hợp ACL để server thực thi giới hạn.

### Key pattern không thay authorization người dùng

Một service account có thể được phép đọc toàn bộ session của ứng dụng shop trong namespace production. Điều đó không có nghĩa user Alice được phép xem session của Bob.

Ứng dụng phải giữ Session ID trong cookie/header, không cung cấp API tùy tiện cho người dùng nhập Session ID khác. Endpoint quản trị session cần kiểm tra role, tenant, mục đích và audit.

Nếu yêu cầu isolation theo tenant rất chặt, cân nhắc store/schema riêng hoặc một thiết kế dữ liệu cho phép thực thi tenant boundary ở tầng lưu trữ. Không giả định prefix theo tenant là đủ nếu tài khoản runtime có quyền trên tất cả prefix.

## 7. Redis Pub/Sub và keyspace notification

Spring Session Redis có thể sử dụng keyspace notifications để nhận biết session hết hạn và phát sự kiện vòng đời. Việc này phụ thuộc repository, cấu hình và tính năng đang dùng.

Redis cần được cấu hình để phát các event phù hợp. Trong một số triển khai, server setting **notify-keyspace-events** phải bật nhóm event expiration. Đây là cấu hình server, không nên giao quyền **CONFIG SET** cho tài khoản runtime của ứng dụng.

### Tách quyền quản trị và quyền subscribe

- Redis administrator cấu hình keyspace notification theo chính sách hạ tầng.
- Runtime session user chỉ được subscribe đúng channel cần thiết nếu ứng dụng bật listener.
- Runtime không cần quyền thay đổi cấu hình Redis.
- ACL channel pattern cần giới hạn đúng channel cần thiết theo cấu hình Redis thực tế.

Redis ACL có thể giới hạn channel bằng channel pattern. Cú pháp và yêu cầu quyền pub/sub phụ thuộc Redis version. Kiểm thử listener thực tế để xác nhận chỉ channel cần thiết được phép.

Không cấp quyền subscribe toàn bộ channel nếu chỉ cần event expiration. Channel có thể chứa thông tin hoạt động của ứng dụng khác.

### Sự kiện không thay thế kiểm tra trạng thái

Keyspace notification là tín hiệu bất đồng bộ. Event có thể đến trễ hoặc bị mất trong một số tình huống vận hành. Không dùng một event duy nhất làm bằng chứng tuyệt đối rằng session chắc chắn còn hiệu lực hoặc đã bị hủy.

Khi xử lý request, repository vẫn phải kiểm tra trạng thái session trong kho dữ liệu theo semantics của nó. Sự kiện chủ yếu hỗ trợ cleanup, listener và thông báo vòng đời.

## 8. Cấu hình tài khoản SQL riêng cho Spring Session JDBC

Với Spring Session JDBC, dữ liệu session thường được lưu trong các bảng như **SPRING_SESSION** và **SPRING_SESSION_ATTRIBUTES** theo schema do phiên bản Spring Session cung cấp.

Ứng dụng runtime cần các quyền thao tác dữ liệu phù hợp:

- SELECT để đọc session.
- INSERT để tạo session và thuộc tính.
- UPDATE để cập nhật truy cập, expiration hoặc thuộc tính.
- DELETE để invalidate và cleanup session hết hạn.

Các quyền chính xác cần kiểm tra với schema script và SQL mà repository phát ra trong phiên bản đang dùng.

### Tách tài khoản runtime và migration

Tài khoản runtime thường không cần:

- CREATE TABLE.
- ALTER TABLE.
- DROP TABLE.
- CREATE SCHEMA.
- DROP SCHEMA.
- Quyền owner database.
- Quyền cấp quyền cho user khác.

Migration user cần quyền DDL trong cửa sổ triển khai có kiểm soát. Sau migration, runtime tiếp tục dùng credential DML tối thiểu.

Ví dụ PostgreSQL minh họa:

~~~sql
CREATE ROLE shop_session_runtime
    LOGIN
    PASSWORD 'INJECT_FROM_SECRET_MANAGER';

GRANT CONNECT ON DATABASE shopdb TO shop_session_runtime;
GRANT USAGE ON SCHEMA shop_session TO shop_session_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE shop_session.spring_session
TO shop_session_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE shop_session.spring_session_attributes
TO shop_session_runtime;
~~~

Tên bảng, schema và chữ hoa/thường phải khớp chính xác với migration của dự án. PostgreSQL phân biệt tên identifier được quote và không quote; hãy kiểm tra tên thực tế trước khi dùng.

Đoạn SQL là ví dụ nguyên tắc, không phải script dùng nguyên trạng cho mọi database. Cần xem thêm quyền sequence nếu schema hoặc custom SQL sử dụng sequence. Các bảng session mặc định thường dùng ID do ứng dụng tạo, nhưng không giả định điều này cho mọi schema tùy chỉnh.

Không dùng role owner hoặc superuser cho datasource runtime.

### Cleanup và quyền DELETE

Spring Session JDBC có thể xóa session hết hạn theo cơ chế cleanup. Nếu runtime hoặc scheduler của ứng dụng thực hiện cleanup, tài khoản cần quyền DELETE trên bảng liên quan.

Nếu muốn tách cleanup thành job vận hành riêng, có thể dùng danh tính job riêng với quyền giới hạn. Tuy nhiên, cần bảo đảm session hết hạn được xử lý đúng và không cấp quyền rộng hơn cho ứng dụng web.

## 9. Schema riêng, bảng riêng và quyền theo tenant

Một database có thể chứa dữ liệu của nhiều ứng dụng. Dùng schema riêng giúp giới hạn grants theo đối tượng:

~~~text
shopdb
  schema shop_session
    SPRING_SESSION
    SPRING_SESSION_ATTRIBUTES

  schema billing_session
    SPRING_SESSION
    SPRING_SESSION_ATTRIBUTES
~~~

Tài khoản shop runtime chỉ có USAGE trên schema shop_session và DML trên các bảng session của shop. Tài khoản billing runtime có phạm vi tương tự trong schema riêng.

Đối với tenant, có một số cách:

- Tách database hoặc schema theo tenant khi yêu cầu isolation mạnh và số tenant phù hợp.
- Dùng cấu trúc bảng có tenant key và database row-level security nếu repository/schema hỗ trợ thiết kế đó.
- Giữ tenant context và authorization ở tầng ứng dụng khi dùng một repository chung.
- Dùng namespace riêng để phân biệt key Redis, kết hợp ACL nếu muốn giới hạn service account theo prefix.

Spring Session JDBC schema mặc định không tự cung cấp tenant isolation hoàn chỉnh chỉ bằng cách thêm một cột tùy ý. Nếu thay đổi schema/repository để có tenant key, cần đảm bảo mọi truy vấn load, save, cleanup và index đều áp dụng tenant constraint. Không chỉ thêm cột tenant rồi vẫn truy vấn bằng Session ID toàn cục.

### Một service account không phải một tài khoản cho mỗi user

Thông thường ứng dụng dùng một service account runtime để thao tác session cho nhiều người dùng. Database không tự biết mỗi request thuộc Alice hay Bob trừ khi ứng dụng truyền thông tin đó qua một cơ chế được thiết kế rõ ràng.

Không đưa database credential vào browser hoặc tạo một database user cho từng người dùng cuối chỉ để giới hạn session. Hãy dùng Spring Security authorization và tenant-aware service logic; chỉ dùng database row-level security nếu context được truyền an toàn và transaction luôn thiết lập đúng context.

## 10. Tài khoản migration và quyền DDL

Spring Session JDBC cần bảng và index tương thích với version đang dùng. Việc tạo hoặc cập nhật schema nên nằm trong quy trình migration như Flyway hoặc Liquibase.

Một quy trình tách quyền:

1. Migration job lấy credential DDL từ secret store.
2. Job chạy migration đã review và có version.
3. Migration xác nhận schema/index tương thích.
4. Runtime deployment dùng credential DML riêng.
5. Credential migration không được mount vào container web.
6. Audit ghi nhận migration identity, thời điểm và version đã áp dụng.

Không để ứng dụng runtime tự động khởi tạo hoặc thay đổi schema production nếu không có yêu cầu vận hành rõ ràng. Quyền DDL thường có tác động lớn hơn nhiều so với thao tác session thông thường.

Nếu dùng schema initialization của Spring Session trong môi trường dev/test, có thể dùng credential riêng có quyền phù hợp. Production nên có chính sách rõ ràng về ai quản lý schema và khi nào migration được chạy.

## 11. Tách quyền backup, restore và monitoring

Backup cần đọc dữ liệu session theo cách phù hợp với công cụ Redis/database, nhưng không nhất thiết dùng chung credential runtime.

Tài khoản backup có thể cần quyền snapshot, replication hoặc đọc backup artifact tùy nền tảng. Hạn chế khả năng ghi session đang chạy và không cấp quyền truy cập không cần thiết vào ứng dụng.

Restore thường nguy hiểm hơn backup vì có thể ghi đè dữ liệu hiện hành. Hãy yêu cầu phê duyệt, kiểm tra môi trường đích, kiểm tra thời điểm snapshot và có kế hoạch rollback.

Monitoring chỉ cần các số liệu như:

- Kết nối thành công/thất bại.
- Số session hoặc kích thước kho dữ liệu theo metric tổng hợp.
- Độ trễ lệnh Redis/JDBC.
- Connection pool usage.
- Lỗi timeout và permission denied.
- Tỷ lệ cleanup hoặc session expiration.

Không cấp quyền đọc payload session cho hệ thống monitoring nếu chỉ cần metric tổng hợp. Không log Session ID, SecurityContext, cookie hoặc thuộc tính session nhạy cảm.

## 12. Quản lý credential và rotation

Credential Redis và database là bí mật vận hành. Không commit vào Git, file cấu hình công khai, Docker image hoặc log.

Nguồn cấp credential nên là:

- Secret manager của nền tảng.
- Kubernetes Secret có mã hóa và RBAC phù hợp.
- Vault hoặc dịch vụ quản lý bí mật tương đương.
- Environment injection được bảo vệ theo hạ tầng.

Không viết password trực tiếp trong application.properties được commit.

### Rotation không làm gián đoạn session

Một quy trình rotation cần tính đến connection pool và kết nối đang mở:

1. Tạo credential mới với cùng phạm vi quyền tối thiểu.
2. Cho phép credential cũ và mới cùng tồn tại trong khoảng chuyển tiếp.
3. Cập nhật secret của workload.
4. Khởi tạo lại hoặc refresh connection theo cơ chế được hỗ trợ.
5. Xác minh mọi instance kết nối bằng credential mới.
6. Thu hồi credential cũ.
7. Kiểm tra metric authentication failure và session read/write.

Không xóa user cũ trước khi mọi instance đã chuyển, trừ khi có tình huống khẩn cấp cần thu hồi ngay. Nếu ứng dụng có nhiều replica, rotation cần được thực hiện có thứ tự và có khả năng rollback.

### Mật khẩu mạnh và ACL user

Dùng secret ngẫu nhiên đủ mạnh, không dùng chung giữa môi trường. Nếu Redis hỗ trợ ACL user/password, không dựa vào user mặc định dùng chung cho mọi ứng dụng.

Database role nên dùng credential riêng. Hạn chế quyền tạo user/role và thay đổi grants ở runtime.

## 13. TLS và giới hạn mạng

ACL xác định client được phép làm gì sau khi kết nối. Network policy xác định client nào có thể tiếp cận endpoint. TLS bảo vệ dữ liệu trên đường truyền và xác thực server theo cấu hình.

Cần kết hợp:

- Redis/database chỉ mở trong private network.
- Firewall/security group chỉ cho workload cần thiết kết nối.
- TLS bật khi kết nối qua mạng có nguy cơ bị nghe lén.
- Client xác minh certificate của server.
- Không tắt hostname verification để xử lý lỗi certificate.
- Không expose Redis port hoặc database port ra Internet.
- Giới hạn egress của container nếu nền tảng hỗ trợ.

TLS không thay ACL. ACL không thay network isolation. Cần nhiều lớp kiểm soát vì credential có thể bị lộ hoặc một workload có thể bị xâm nhập.

## 14. Quyền truy cập khi chạy nhiều instance

Trong deployment nhiều nút, mỗi instance thường dùng cùng một loại service account runtime nhưng mỗi kết nối vẫn được xác thực độc lập với Redis/database.

Các instance cần:

- Cùng endpoint và môi trường.
- Cùng namespace hoặc schema.
- Credential có quyền tương đương.
- Cùng serializer và repository tương thích.
- Quyền đọc/ghi session cần thiết.
- Không có quyền quản trị không cần thiết.

Nếu A dùng credential có quyền đầy đủ còn B dùng credential giới hạn, lỗi có thể chỉ xuất hiện khi load balancer chuyển request sang B. Vì vậy, phải kiểm tra cấu hình quyền trên mọi replica và mọi profile.

### Tách identity theo workload

Nếu một ứng dụng có nhiều workload, ví dụ web runtime, cleanup scheduler và migration job, cân nhắc tài khoản riêng:

- Web runtime: thao tác session thông thường.
- Cleanup job: xóa session hết hạn nếu được tách riêng.
- Migration job: DDL/schema changes.
- Backup job: quyền snapshot/backup.

Không tạo quá nhiều tài khoản nếu không có ranh giới nhiệm vụ thực tế; mục tiêu là giảm blast radius và làm quyền dễ audit.

## 15. Kiểm thử quyền Redis

Không chỉ kiểm tra user có thể kết nối. Cần xác minh thao tác đúng được cho phép và thao tác ngoài phạm vi bị từ chối.

Một bộ test:

1. Kết nối bằng user runtime.
2. Tạo session qua ứng dụng Spring Session.
3. Đọc session bằng request tiếp theo.
4. Cập nhật thuộc tính và xác minh lưu thành công.
5. Logout và xác minh session được xóa/invalidate.
6. Thử truy cập key ngoài namespace và xác minh bị từ chối.
7. Thử command quản trị như CONFIG hoặc ACL SETUSER và xác minh bị từ chối.
8. Nếu có listener expiration, xác minh chỉ channel cần thiết được subscribe.
9. Xác minh ứng dụng vẫn hoạt động khi ACL được bật thật.

Ví dụ kiểm tra một key ngoài phạm vi bằng redis-cli hoặc test client có kiểm soát:

~~~text
GET billing:prod:spring-session:sample
~~~

User của shop không nên đọc được key của billing. Test phải xác minh kết quả permission denied theo policy Redis.

Có thể dùng ACL dry-run hoặc lệnh kiểm tra ACL phù hợp Redis version để đánh giá một command có được phép hay không. Tuy nhiên, test tích hợp qua ứng dụng mới chứng minh được toàn bộ tập lệnh repository thực sự cần.

Không bật Redis MONITOR công khai hoặc ghi toàn bộ lệnh có thể chứa dữ liệu nhạy cảm trong production chỉ để tìm command. Dùng môi trường test, instrumentation được bảo vệ hoặc log quyền bị từ chối đã được lọc.

## 16. Kiểm thử quyền JDBC

Với database, chạy integration test bằng đúng runtime role, không dùng tài khoản owner mà test thường dùng.

Kiểm tra:

- Runtime role kết nối được database.
- Có thể SELECT session.
- Có thể INSERT session mới.
- Có thể UPDATE session và attributes.
- Có thể DELETE session khi logout/cleanup.
- Không thể CREATE, ALTER hoặc DROP bảng.
- Không thể đọc schema/bảng của ứng dụng khác.
- Không thể cấp quyền cho role khác.
- Migration job dùng credential riêng và chạy được DDL cần thiết.

Một test quan trọng là chạy Spring Session repository bằng runtime role từ đầu đến cuối. Nếu test chỉ kiểm tra SELECT 1, nó chưa chứng minh quyền cần thiết cho session lifecycle.

### Kiểm tra quyền theo môi trường

Chạy cùng test suite với:

- Redis/JDBC local test.
- Staging credential.
- Production-equivalent ACL/grants trong môi trường kiểm thử được bảo vệ.

Không dùng production credential trong unit test hoặc ghi credential vào CI output. CI nên lấy secret từ secret store và che output.

## 17. Kiểm soát truy cập quản trị session

Một số hệ thống có chức năng quản trị để xem session đang hoạt động, thu hồi session hoặc đăng xuất người dùng từ xa. Đây là API nhạy cảm.

Cần bảo vệ bằng:

- Role quản trị riêng.
- Authorization theo tenant hoặc phạm vi người dùng.
- Audit actor, mục đích và thời điểm.
- CSRF protection nếu thao tác qua cookie/browser.
- Rate limit và xác nhận bổ sung với thao tác diện rộng.
- Không trả Session ID hoặc payload nhạy cảm ra UI/log.
- Chỉ hiển thị dữ liệu tối thiểu cần cho support.

Không cho nhân viên support dùng tài khoản Redis trực tiếp để tìm và sửa key session. Hãy cung cấp công cụ quản trị ở tầng ứng dụng có authorization, audit và quy trình thu hồi.

Nếu cần thao tác trực tiếp kho dữ liệu trong sự cố, dùng break-glass account có phê duyệt, thời hạn, logging và phạm vi được giới hạn.

## 18. Xử lý permission denied trong vận hành

Khi ứng dụng báo lỗi quyền Redis hoặc JDBC, không giải quyết bằng cách cấp **+@all**, **~*** hoặc database owner ngay lập tức.

Quy trình điều tra:

1. Xác định workload và service account đang kết nối.
2. Xác định thao tác bị từ chối và resource key/table/channel.
3. Kiểm tra ứng dụng có đang dùng đúng môi trường/endpoint không.
4. Đối chiếu thao tác với repository version và feature đang bật.
5. Xác định quyền tối thiểu cần bổ sung.
6. Thay đổi ACL/grant qua quy trình review.
7. Chạy integration test bằng đúng account.
8. Theo dõi permission denied sau rollout.

Một lỗi có thể xuất phát từ việc ứng dụng dùng nhầm credential staging trong production, namespace thay đổi hoặc một tính năng expiration listener cần channel permission mới. Không mặc định rằng cần quyền quản trị rộng hơn.

### Phân biệt lỗi kết nối và lỗi quyền

| Triệu chứng | Hướng kiểm tra |
|---|---|
| Connection refused | Network, port, service endpoint |
| TLS handshake failure | Certificate, truststore, hostname |
| Authentication failed | Username/password, secret rotation |
| Permission denied | ACL command/key/channel hoặc SQL grants |
| Table not found | Migration/schema/search path |
| Serialization error | Serializer, class version, dữ liệu cũ |
| Timeout | Latency, connection pool, backend load |

Không ghi password, full connection URI chứa secret hoặc Session ID trong log khi điều tra.

## 19. Checklist triển khai production

Trước khi phát hành Spring Session Redis/JDBC, xác nhận:

- Mỗi ứng dụng và môi trường có service account riêng.
- Runtime credential không có quyền admin hoặc DDL không cần thiết.
- Redis ACL giới hạn key pattern theo namespace.
- Redis channel permission chỉ cấp nếu listener thực sự cần.
- Command permissions được xác minh với version repository thực tế.
- Không dùng **+@all**, **~*** hoặc **FLUSHALL** cho runtime.
- JDBC runtime role chỉ có DML trên bảng session cần thiết.
- Migration credential được tách khỏi web workload.
- Backup và monitoring dùng identity riêng theo nhiệm vụ.
- Database/Redis endpoint nằm trong private network.
- TLS và certificate validation được bật theo yêu cầu hạ tầng.
- Secret được lấy từ secret manager và có rotation plan.
- Các replica dùng cùng cấu hình quyền và endpoint.
- Test được cả thao tác hợp lệ và thao tác ngoài phạm vi.
- Quyền quản trị session được kiểm soát và audit.
- Không log Session ID, cookie, SecurityContext hoặc credential.

## 20. Tự kiểm tra

1. Vì sao quyền đọc Redis session có thể ảnh hưởng đến bảo mật đăng nhập?
2. Service account khác tài khoản người dùng cuối như thế nào?
3. Least privilege có nghĩa gì với Spring Session runtime?
4. Vì sao namespace Redis không tự tạo ranh giới bảo mật?
5. Redis logical database có thay thế ACL key pattern không?
6. Vì sao không nên cấp **+@all** cho runtime?
7. Command permissions cần được xác định dựa trên điều gì?
8. Vì sao runtime JDBC user thường không cần CREATE/ALTER/DROP?
9. Tại sao cần tách migration user và runtime user?
10. Keyspace notification có thể cần những quyền gì và ai nên cấu hình server setting?
11. Vì sao service account chung không tự cung cấp tenant isolation?
12. Credential rotation cần tính đến điều gì khi có nhiều replica?
13. Làm sao chứng minh ACL chỉ cho phép truy cập namespace của ứng dụng?
14. Làm sao chứng minh JDBC role không có quyền DDL?
15. Vì sao monitoring không nên đọc payload session?
16. Khi gặp permission denied, tại sao không nên cấp quyền rộng ngay?

### Gợi ý trả lời

1. Session có thể chứa Session ID và SecurityContext; đọc hoặc sửa chúng có thể làm lộ hoặc tác động trạng thái xác thực.
2. Service account đại diện tiến trình ứng dụng kết nối kho dữ liệu; user cuối được xác thực và phân quyền trong ứng dụng.
3. Chỉ cấp quyền cần để tạo, đọc, cập nhật, xóa session trong namespace hoặc bảng của workload.
4. Namespace chỉ là prefix; nếu ACL cho phép mọi key thì user vẫn truy cập dữ liệu ngoài prefix.
5. Không. Logical DB không phải ranh giới bảo mật đủ mạnh; cần ACL key patterns hoặc hạ tầng riêng.
6. Vì runtime có thể thực hiện lệnh quản trị hoặc phá hủy dữ liệu không cần cho session.
7. Repository implementation, version, save/flush mode, expiration/listener feature và command thực tế trong integration test.
8. Runtime chỉ thao tác dữ liệu; DDL có blast radius lớn và thuộc trách nhiệm migration.
9. Để ứng dụng web không thể tự sửa hoặc phá schema khi bị xâm nhập.
10. Có thể cần subscribe đúng keyevent expiration channel; administrator cấu hình notification, runtime chỉ subscribe channel cần thiết.
11. Database thấy một service account dùng chung; tenant authorization phải được thực thi ở ứng dụng hoặc bằng schema/RLS được thiết kế đúng.
12. Tạo credential mới, chuyển mọi replica, xác minh kết nối mới rồi mới thu hồi credential cũ.
13. Test đọc/ghi key trong namespace được phép và xác minh key ngoài namespace bị từ chối.
14. Dùng đúng runtime role để thử DML thành công và CREATE/ALTER/DROP bị từ chối.
15. Metric tổng hợp thường đủ; payload có thể chứa PII, Session ID và SecurityContext.
16. Vì lỗi có thể do sai endpoint, secret, channel hoặc migration; cần xác định thao tác cụ thể rồi cấp đúng quyền tối thiểu.

## Kết luận

Kho Redis hoặc JDBC của Spring Session chứa trạng thái phiên có thể ảnh hưởng trực tiếp đến xác thực và quyền truy cập. Service account runtime vì vậy cần được giới hạn theo ứng dụng, môi trường, key namespace hoặc schema và tập thao tác thực sự cần. Redis ACL phải giới hạn key, command và channel; JDBC grants phải giới hạn bảng và quyền DML. Namespace và logical database hỗ trợ tổ chức dữ liệu nhưng không thay thế cơ chế authorization ở kho dữ liệu.

Tách runtime, migration, backup, monitoring và break-glass identities để giảm blast radius. Quản lý credential bằng secret manager, bật TLS và network isolation, audit thay đổi quyền, kiểm thử cả thao tác được phép lẫn bị từ chối. Đặc biệt, không cấp quyền quản trị hoặc DDL cho tiến trình web chỉ để khắc phục nhanh lỗi permission. Một cấu hình an toàn phải chứng minh rằng ứng dụng vẫn thực hiện đầy đủ session lifecycle trong phạm vi của mình và không thể truy cập tài nguyên ngoài phạm vi đó.

