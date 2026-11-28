# Khôi phục từ bản sao lưu và nguy cơ phục hồi cả phiên đã thu hồi

Khôi phục Redis hoặc database từ bản sao lưu có thể đưa dữ liệu session quay lại trạng thái của một thời điểm trong quá khứ. Điều này giúp phục hồi phiên bị mất do lỗi vận hành hoặc hỏng dữ liệu, nhưng cũng tạo ra một rủi ro bảo mật: những session đã logout, invalidate, bị thu hồi sau thời điểm backup có thể xuất hiện trở lại trong bản dữ liệu được phục hồi.

Spring Session lưu trạng thái phiên trong repository như Redis hoặc JDBC. Backup của repository chỉ phản ánh dữ liệu đã lưu tại thời điểm chụp. Nó không tự biết một người dùng đã đăng xuất sau đó, quản trị viên đã thu hồi một phiên bị lộ, hay hệ thống đã đổi session ID sau xác thực. Vì vậy, phục hồi session store phải đi cùng một nguồn ghi nhận việc thu hồi có độ bền và thời điểm mới hơn bản backup.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt backup dữ liệu session với nguồn sự thật về trạng thái thu hồi.
- Hiểu RPO, RTO và điểm nhất quán của bản sao lưu Redis/JDBC.
- Khôi phục vào môi trường cô lập và kiểm tra trước khi cutover.
- Nhận diện nguy cơ session logout/invalidate bị hồi sinh sau restore.
- Thiết kế revocation ledger hoặc authentication epoch độc lập với session backup.
- Xử lý TTL, index, schema, serializer và session event sau khôi phục.
- Xây dựng runbook, kiểm thử và tiêu chí rollback cho phục hồi an toàn.

## 1. Vì sao restore có thể làm sống lại session đã thu hồi?

Giả sử:

1. 09:00 người dùng đăng nhập, session ID là S1 và dữ liệu được lưu trong Redis/JDBC.
2. 09:10 hệ thống tạo backup.
3. 09:20 người dùng logout; ứng dụng invalidate S1 và xóa bản ghi.
4. 09:25 quản trị viên thu hồi một phiên khác do nghi ngờ credential bị lộ.
5. 10:00 đội vận hành restore session store từ backup lúc 09:10.

Bản backup chứa S1 vì tại 09:10 phiên vẫn còn hiệu lực. Khi restore, bản ghi S1 xuất hiện trở lại. Nếu server chỉ kiểm tra xem session ID có tồn tại trong repository hay không, cookie cũ có thể được chấp nhận lại.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Ứng dụng
    participant S as Session store
    participant B as Backup
    U->>A: Đăng nhập, tạo S1
    A->>S: Lưu S1
    S->>B: Snapshot lúc 09:10 có S1
    U->>A: Logout lúc 09:20
    A->>S: Invalidate và xóa S1
    Note over S: S1 không còn trong store hiện tại
    B->>S: Restore snapshot cũ lúc 10:00
    Note over S: S1 xuất hiện lại nếu không đối chiếu revocation
    U->>A: Replay cookie S1
    A->>S: Tìm session S1
    S-->>A: Có bản ghi cũ
~~~

Vấn đề không phải backup bị hỏng. Backup đã làm đúng nhiệm vụ khôi phục trạng thái tại thời điểm chụp. Vấn đề là trạng thái thu hồi phát sinh sau thời điểm đó chưa được áp dụng lại.

Logout, invalidate và session ID rotation thường được thực hiện bằng cách cập nhật hoặc xóa dữ liệu trong session repository. Khi phục hồi một snapshot cũ, các thao tác xóa hoặc đổi ID xảy ra sau snapshot có thể bị đảo ngược. Vì thế, session store không nên là nguồn duy nhất lưu dấu vết bảo mật về việc một session đã bị thu hồi.

## 2. Phân biệt backup, session store và nguồn thu hồi

Ba loại dữ liệu có mục đích khác nhau:

| Thành phần | Mục đích | Khi restore |
|---|---|---|
| Session store | Trạng thái phiên đang hoạt động: principal, thuộc tính, thời gian hết hạn | Có thể quay về snapshot cũ |
| Backup/session snapshot | Bản sao dữ liệu tại một thời điểm để phục hồi lỗi | Có thể chứa session đã logout sau thời điểm chụp |
| Revocation ledger hoặc authentication epoch | Ghi nhận session/user đã bị thu hồi hoặc phải xác thực lại | Phải giữ được các thay đổi mới hơn backup session |

Session repository trả lời câu hỏi “có dữ liệu phiên với ID này không?”. Nguồn thu hồi trả lời câu hỏi “dù dữ liệu có tồn tại, phiên này còn được phép dùng không?”. Hai câu hỏi phải được kiểm tra riêng.

Spring Session cung cấp cơ chế lưu trữ và vòng đời session, nhưng không tự cung cấp một revocation ledger độc lập cho mọi kiểu khôi phục backup. Ứng dụng cần thiết kế lớp xác minh quyền còn hiệu lực theo yêu cầu bảo mật.

## 3. Xác định RPO và RTO cho session

Trước khi chọn chiến lược backup, hãy xác định:

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất tính theo thời gian. Ví dụ RPO 5 phút nghĩa là mục tiêu phục hồi dữ liệu không cũ hơn khoảng 5 phút.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để dịch vụ hoạt động lại sau sự cố.
- **Session tolerance:** sản phẩm có chấp nhận người dùng đăng nhập lại sau phục hồi không?
- **Revocation guarantee:** logout, thu hồi do nghi ngờ bị lộ và khóa tài khoản phải có hiệu lực ngay cả khi session store được restore về quá khứ không?

Session thường là trạng thái tạm thời. Với nhiều ứng dụng, chấp nhận buộc người dùng đăng nhập lại an toàn hơn việc phục hồi mọi phiên cũ. Nếu trải nghiệm yêu cầu giữ session, phải có cơ chế loại bỏ những phiên đã bị thu hồi kể từ checkpoint backup.

Không đồng nhất RPO của session store với RPO của dữ liệu nghiệp vụ. Có thể chấp nhận mất vài phút trạng thái giỏ hàng tạm, nhưng không thể chấp nhận hồi sinh phiên của tài khoản đã bị khóa.

## 4. Sao lưu Redis chứa Spring Session

Spring Session Redis thường lưu session dưới dạng key/value hoặc cấu trúc Redis theo implementation và phiên bản. Redis có thể dùng:

- **RDB snapshot:** tạo snapshot dữ liệu tại một thời điểm. Snapshot có thể được sao chép ra nơi lưu trữ backup.
- **AOF (Append Only File):** ghi lại các thao tác ghi để tái dựng trạng thái. Chính sách fsync ảnh hưởng mức dữ liệu có thể mất khi sự cố.
- **Replication/managed backup:** dịch vụ Redis có thể cung cấp replica, snapshot hoặc point-in-time recovery với đặc tính riêng.

Replica không thay thế backup. Lỗi xóa nhầm, ghi đè hoặc hỏng logic có thể được replicate sang replica. Cần có bản sao lưu tách biệt, kiểm soát quyền truy cập và kiểm thử restore.

### 4.1. Backup cần nhất quán với cấu trúc session

Không chỉ quan tâm key session chính. Spring Session Redis có thể duy trì index, metadata, key phục vụ expiry và các cấu trúc liên quan, tùy repository. Nếu backup hoặc export chỉ lấy một phần namespace, sau restore có thể xuất hiện:

- Session record còn nhưng index theo principal thiếu.
- Index còn nhưng session record đã mất.
- Metadata hết hạn không đồng bộ.
- Key namespace của phiên bản mới và cũ trộn lẫn.

Ưu tiên cơ chế backup nhất quán ở cấp Redis deployment hoặc dịch vụ managed. Nếu phải export một phần keyspace, cần hiểu cấu trúc của đúng phiên bản và có bước reconcile bằng repository/API, không tự giả định một key là toàn bộ session.

### 4.2. Kiểm tra TTL sau restore

Redis lưu thời điểm hết hạn gắn với key. Snapshot RDB lưu thời gian hết hạn theo mốc thời gian tuyệt đối; key đã hết hạn tại thời điểm nạp thường không được khôi phục như một key còn sống. Tuy nhiên, cách backup/restore của dịch vụ managed, AOF, import tool và cấu trúc nhiều key có thể khác nhau.

Không chỉ dựa vào TTL của một key. Hãy kiểm tra:

- Session record có tồn tại không?
- TTL còn lại có phù hợp với inactivity timeout không?
- Các key metadata/index liên quan có TTL tương ứng không?
- Clock của máy chủ và môi trường restore có đồng bộ không?
- Cleanup/expiration job có chạy lại bình thường không?

Không tăng TTL để giữ lại mọi session sau restore. Điều đó có thể kéo dài hiệu lực của những phiên đáng lẽ đã hết hạn hoặc bị thu hồi.

## 5. Sao lưu Spring Session JDBC

Spring Session JDBC tiêu chuẩn lưu dữ liệu phiên trong bảng session và bảng thuộc tính session, thường là `SPRING_SESSION` và `SPRING_SESSION_ATTRIBUTES`. Tên bảng và schema có thể được tùy chỉnh.

Backup JDBC nên bảo đảm hai nhóm dữ liệu được chụp nhất quán. Nếu snapshot chỉ chứa bảng session nhưng thiếu bảng attributes, session có thể tồn tại mà không có dữ liệu cần thiết. Nếu attributes được phục hồi nhưng session row không còn, dữ liệu thuộc tính trở thành bản ghi mồ côi tùy schema và chính sách cleanup.

Các phương án phổ biến:

- Snapshot nhất quán của database volume/managed database.
- Backup logic với transaction snapshot phù hợp.
- Point-in-time recovery từ full backup và transaction log/WAL/binlog theo hệ quản trị.

Khi phục hồi, kiểm tra:

- Đúng database, catalog và schema.
- Cả bảng session và attributes.
- Index, constraint, sequence và quyền của application user.
- Cột expiry và các bản ghi đã quá hạn.
- Script schema/migration tương ứng phiên bản Spring Session.
- Các thay đổi schema trong thời gian giữa backup và sự cố.

Ví dụ truy vấn chỉ đọc để kiểm tra session:

~~~sql
SELECT PRIMARY_ID, SESSION_ID, CREATION_TIME, LAST_ACCESS_TIME,
       MAX_INACTIVE_INTERVAL, EXPIRY_TIME
FROM SPRING_SESSION
WHERE SESSION_ID = :sessionId;
~~~

Kiểm tra số lượng thuộc tính mà không đọc giá trị nhạy cảm:

~~~sql
SELECT SESSION_PRIMARY_ID, COUNT(*) AS ATTRIBUTE_COUNT
FROM SPRING_SESSION_ATTRIBUTES
GROUP BY SESSION_PRIMARY_ID;
~~~

Tên cột phải được xác minh theo schema đúng phiên bản và database. Dùng bind parameter cho ID test. Không xuất giá trị thuộc tính session vào báo cáo backup hoặc log.

## 6. Vì sao logout/invalidate không đủ để chống hồi sinh sau restore?

Trong hoạt động bình thường:

1. Ứng dụng nhận cookie session ID.
2. Spring Session tải session từ repository.
3. Logout gọi invalidate hoặc cơ chế xóa phiên.
4. Repository xóa hoặc đánh dấu phiên không còn hiệu lực.
5. Resolver phát cookie hết hạn để browser ngừng gửi ID.

Cookie hết hạn chỉ tác động tới browser tuân thủ response. Một client có thể giữ bản sao cookie cũ. Repository xóa session làm ID không còn tìm thấy trong trạng thái hiện tại, nhưng backup cũ có thể đưa record trở lại.

Do đó, sau restore cần một kiểm tra thu hồi độc lập. Nếu ứng dụng chỉ xác thực bằng sự tồn tại của session record, bản ghi cũ được phục hồi có thể trở thành credential hợp lệ một lần nữa.

Đặc biệt chú ý:

- Logout từng thiết bị.
- Logout tất cả thiết bị.
- Thu hồi session do phát hiện credential bị lộ.
- Khóa hoặc vô hiệu hóa tài khoản.
- Đổi mật khẩu hoặc thay đổi yếu tố xác thực.
- Session ID rotation sau login hoặc nâng quyền.

Những sự kiện này phải tiếp tục có hiệu lực sau khi session store quay về snapshot cũ.

## 7. Thiết kế revocation ledger độc lập

Revocation ledger là nguồn dữ liệu bền vững ghi nhận phiên hoặc người dùng đã bị thu hồi. Nó phải tồn tại độc lập với bản backup session store đang được phục hồi, hoặc phải có log/audit có thể replay để tái áp dụng mọi lần thu hồi sau checkpoint.

Một bản ghi thu hồi session có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| Session fingerprint | Hash/HMAC của session ID, không lưu session ID dạng rõ |
| Revoked at | Thời điểm thu hồi |
| Reason | Logout, suspected compromise, admin revoke hoặc rotation |
| Actor/source | Người dùng, quản trị viên hay quy trình bảo mật |
| Correlation ID | Dấu vết request/audit liên quan |
| Expire after | Thời điểm có thể dọn tombstone an toàn |

Không lưu raw session ID trong audit log. Nếu dùng HMAC, khóa HMAC phải được bảo vệ riêng và không nằm trong cùng bản backup session store.

### 7.1. Ledger phải sống lâu hơn cửa sổ phục hồi

Nếu backup có thể được restore từ bất kỳ thời điểm nào trong 30 ngày, tombstone thu hồi cần được giữ đủ lâu để ngăn session cũ trong mọi backup còn được phép phục hồi. Một quy tắc thực tế là retention của revocation record phải bao phủ:

`max session lifetime + maximum backup restore horizon + operational safety margin`

Thời gian chính xác phụ thuộc chính sách backup, session timeout và khả năng replay. Không xóa tombstone ngay khi session đã hết TTL ở store hiện tại nếu vẫn còn backup cũ có thể được restore.

### 7.2. Ledger không được rollback cùng backup

Đây là điều kiện cốt lõi. Nếu revocation ledger nằm trong cùng database snapshot và được phục hồi về cùng thời điểm cũ, ledger cũng mất các lần thu hồi sau backup.

Các lựa chọn:

- Lưu ledger ở database hoặc dịch vụ khác có backup/replication độc lập.
- Ghi sự kiện thu hồi vào audit log bất biến và replay các sự kiện sau checkpoint.
- Dùng hệ thống quản lý danh tính có version/epoch hiện hành được bảo vệ khỏi rollback cùng session store.

Không coi một bảng revocation trong cùng database snapshot là độc lập nếu cả session data và bảng đó đều được restore về cùng một thời điểm.

## 8. Authentication epoch để thu hồi theo người dùng

Với logout-all, khóa tài khoản, đổi mật khẩu hoặc sự cố bảo mật diện rộng, có thể dùng một số phiên bản xác thực (authentication epoch/version) lưu trong nguồn dữ liệu có thẩm quyền độc lập.

Ví dụ:

- Bản ghi người dùng lưu `authEpoch = 12`.
- Khi tạo session, ứng dụng ghi `authEpoch = 12` vào session.
- Khi cần thu hồi mọi phiên của người dùng, tăng epoch hiện hành lên 13.
- Mỗi request xác thực session so sánh epoch trong session với epoch hiện hành.
- Nếu khác nhau, ứng dụng từ chối session và invalidate nó.

Sau khi restore session store cũ, session mang epoch 12 vẫn không hợp lệ vì nguồn xác thực hiện hành giữ 13.

~~~mermaid
sequenceDiagram
    participant R as Request
    participant S as Spring Session
    participant I as Identity store
    R->>S: Load session và authEpoch
    S-->>R: principal, authEpoch=12
    R->>I: Đọc authEpoch hiện tại
    I-->>R: authEpoch=13
    R->>R: So sánh 12 != 13
    R-->>R: Từ chối và invalidate session
~~~

Spring Session không tự thêm cơ chế epoch này. Ứng dụng cần tích hợp kiểm tra ở authentication/session validation layer sao cho được thực hiện trước khi request được coi là đã xác thực. Không chỉ kiểm tra epoch tại login; nếu chỉ kiểm tra một lần, session cũ có thể tiếp tục hợp lệ trong suốt thời gian tồn tại.

Epoch theo người dùng thu hồi được toàn bộ session cũ của user. Nó không thay thế ledger theo session nếu cần thu hồi riêng một thiết bị mà vẫn giữ các thiết bị khác.

## 9. Thu hồi một session cụ thể

Để logout một thiết bị hoặc thu hồi một session bị lộ, lưu fingerprint của session ID trong revocation ledger độc lập. Khi request tới:

1. Resolver đọc session ID.
2. Ứng dụng tính fingerprint bằng HMAC hoặc hash phù hợp.
3. Kiểm tra fingerprint có nằm trong ledger không.
4. Nếu đã thu hồi, từ chối xác thực, invalidate record nếu có và yêu cầu đăng nhập lại.
5. Nếu chưa thu hồi, tiếp tục kiểm tra session và quyền.

Việc kiểm tra cần được đặt ở lớp bảo mật trước khi ứng dụng tin cậy principal trong session. Với Servlet, có thể tích hợp qua Spring Security filter/provider hoặc một thành phần xác thực phù hợp với session context. Với WebFlux, dùng reactive security chain và không block khi truy vấn ledger reactive.

Độ trễ cache của revocation ledger phải được cân nhắc. Cache stale có thể cho phép session đã thu hồi tiếp tục hoạt động. Với thao tác thu hồi khẩn cấp, cần chiến lược invalidate cache hoặc kiểm tra nguồn có thẩm quyền theo yêu cầu bảo mật.

## 10. Session ID rotation và backup cũ

Khi session ID được đổi sau login hoặc nâng quyền, session ID cũ phải mất hiệu lực. Nhưng backup trước thời điểm rotation có thể chứa bản ghi cũ.

Các cách giảm rủi ro:

- Ghi nhận rotation như một sự kiện thu hồi ID cũ trong ledger độc lập.
- Tăng authentication epoch khi có sự kiện cần vô hiệu hóa các phiên trước đó.
- Sau restore, buộc re-authentication cho các phiên nằm trước mốc tin cậy.
- Kiểm tra ID cũ không truy cập được ngay cả khi record cũ xuất hiện trong môi trường restore.

Không dựa vào việc browser đã nhận cookie ID mới. Client độc hại có thể replay ID cũ nếu server chấp nhận lại nó sau restore.

## 11. Restore có kiểm soát: quy trình tổng thể

Không restore trực tiếp lên session store production đang phục vụ request. Quy trình an toàn nên chia thành các giai đoạn:

1. **Contain:** xác định phạm vi sự cố, dừng thay đổi dữ liệu liên quan và điều phối traffic/maintenance mode phù hợp.
2. **Chọn checkpoint:** xác định backup, thời điểm chụp, RPO và dữ liệu có thể mất.
3. **Restore cô lập:** khôi phục Redis/JDBC vào môi trường riêng, chưa cho application production đọc.
4. **Kiểm tra toàn vẹn:** schema, keyspace, record count, index, TTL, serializer và lỗi deserialize.
5. **Reconcile revocation:** lấy ledger/audit mới nhất, áp dụng mọi thu hồi sau checkpoint.
6. **Áp dụng epoch/policy:** tăng epoch hoặc buộc đăng nhập lại nếu không thể chứng minh trạng thái thu hồi đầy đủ.
7. **Lọc session hết hạn:** kiểm tra expiry theo thời gian hiện tại, không chỉ thời điểm backup.
8. **Kiểm thử:** session hợp lệ được khôi phục theo policy; session đã logout/thu hồi không thể dùng.
9. **Cutover:** chuyển traffic sang store đã kiểm tra và theo dõi metric.
10. **Giữ bằng chứng:** lưu checkpoint, log restore, số record bị loại và người phê duyệt.

~~~mermaid
flowchart TD
    A[Chọn backup và checkpoint] --> B[Restore vào môi trường cô lập]
    B --> C[Kiểm tra schema, key, TTL, serialization]
    C --> D[Đối chiếu revocation ledger mới nhất]
    D --> E[Loại session bị thu hồi hoặc hết hạn]
    E --> F{Có chứng minh được revocation đầy đủ?}
    F -->|Không| G[Tăng epoch hoặc buộc đăng nhập lại]
    F -->|Có| H[Chạy kiểm thử chấp nhận]
    G --> H
    H --> I{Kiểm thử đạt?}
    I -->|Không| J[Giữ maintenance, điều tra/rollback]
    I -->|Có| K[Cutover và giám sát]
~~~

## 12. Reconcile dữ liệu sau restore

Reconciliation là bước đối chiếu dữ liệu đã phục hồi với các sự kiện có thẩm quyền xảy ra sau checkpoint.

Các quy tắc tối thiểu:

- Xóa hoặc từ chối mọi session fingerprint có revocation record.
- Từ chối session có auth epoch thấp hơn epoch hiện hành.
- Từ chối session có thời điểm hết hạn đã qua theo đồng hồ hiện tại.
- Kiểm tra tài khoản bị khóa, xóa hoặc đổi trạng thái sau backup.
- Kiểm tra session thuộc principal không còn tồn tại hoặc không còn được phép đăng nhập.
- Xác minh index/metadata có nhất quán với session record.

Không chỉ xóa row/key khỏi backup rồi cho rằng đã an toàn. Một số repository có index hoặc metadata phụ; dùng API/repository phù hợp hoặc quy trình cleanup được kiểm thử để tránh để lại index sai.

Nếu không thể xác định đầy đủ các lần thu hồi kể từ backup, phương án an toàn là vô hiệu hóa các session cũ trong phạm vi bị ảnh hưởng và yêu cầu người dùng xác thực lại. Không đoán rằng “chắc chỉ có vài logout”.

## 13. Session event và audit sau restore

Session event như created, expired hoặc deleted có thể được phát trong quá trình ứng dụng hoạt động. Tuy nhiên, việc restore dữ liệu từ snapshot không đồng nghĩa framework phát lại đầy đủ mọi event đã xảy ra trong khoảng thời gian snapshot.

Vì vậy:

- Không dùng event listener như audit log duy nhất.
- Không giả định restore một Redis key sẽ phát lại session destroy event.
- Không giả định các subscriber Redis Pub/Sub hoặc keyspace notification nhận được event đã xảy ra khi subscriber offline.
- Duy trì audit/revocation log bền vững riêng cho login, logout, admin revoke, rotation và account disable.
- Sau restore, chạy reconciliation chủ động thay vì chờ event tự xuất hiện.

Nếu hệ thống có consumer cập nhật index, thống kê active sessions hoặc thông báo bảo mật, cần có quy trình rebuild/reconcile các dữ liệu dẫn xuất từ nguồn bền vững.

## 14. Tương thích phiên bản và serialization

Backup có thể được tạo bởi phiên bản ứng dụng cũ rồi restore vào phiên bản mới. Session attributes có thể chứa object Java hoặc payload phụ thuộc serializer.

Rủi ro:

- Class đã đổi package hoặc tên.
- Field đã đổi kiểu hoặc ý nghĩa.
- Serializer/ObjectMapper đã đổi cấu hình.
- Version mới không đọc được payload cũ.
- Phiên cũ có SecurityContext hoặc principal representation không còn tương thích.
- Redis namespace hoặc JDBC schema đã thay đổi giữa các release.

Biện pháp:

- Ưu tiên lưu kiểu dữ liệu đơn giản, versioned và ổn định trong session.
- Dùng DTO có version hoặc dữ liệu tham chiếu thay vì lưu entity lớn.
- Kiểm thử restore backup cũ bằng đúng binary dự kiến cutover.
- Có migration/compatibility plan cho schema và serialization.
- Nếu không thể đọc an toàn, invalidate các session bị ảnh hưởng và yêu cầu login lại.

Không deserialize dữ liệu session từ backup không tin cậy trong một môi trường đặc quyền cao. Backup session chứa dữ liệu do ứng dụng ghi, có thể bao gồm dữ liệu đầu vào người dùng hoặc object serialized.

## 15. Bảo vệ bản backup và môi trường restore

Session backup có thể chứa principal, vai trò, thông tin workflow, CSRF-related state hoặc dữ liệu cá nhân. Cần áp dụng:

- Mã hóa backup khi truyền và khi lưu.
- Phân quyền đọc/restore theo nguyên tắc tối thiểu.
- Audit mọi lần truy cập và restore.
- Tách môi trường restore khỏi production cho tới khi hoàn tất kiểm tra.
- Không đưa session ID, cookie hoặc thuộc tính nhạy cảm vào log restore.
- Hủy bản restore tạm theo quy trình sau khi hoàn tất.
- Bảo vệ khóa mã hóa, HMAC và secret độc lập với backup session store.

Không cấp quyền ghi production cho người chỉ cần kiểm tra backup. Một bản backup cũ có thể chứa credential session còn hiệu lực nếu bị phục hồi nguyên trạng.

## 16. Kiểm thử chiến lược backup/restore

Kiểm thử định kỳ cần mô phỏng cả dữ liệu hợp lệ và đã thu hồi:

1. Tạo session S1 và lưu một thuộc tính test.
2. Tạo backup checkpoint C1 khi S1 còn hiệu lực.
3. Logout/invalidate S1 sau checkpoint.
4. Ghi revocation record vào ledger độc lập.
5. Restore C1 vào môi trường cô lập.
6. Thực hiện reconciliation.
7. Gửi lại cookie S1 và xác minh ứng dụng từ chối.
8. Tạo session S2 hợp lệ theo quy trình sau restore và xác minh hoạt động.
9. Kiểm tra TTL, expiry, index và event consumer.
10. Lặp lại với user-wide epoch, tài khoản bị khóa và session ID rotation.

Ma trận kết quả:

| Trường hợp | Kết quả mong đợi sau restore |
|---|---|
| Session hợp lệ tại checkpoint, chưa bị thu hồi | Được phục hồi nếu policy cho phép và chưa hết hạn |
| Session logout sau checkpoint | Bị từ chối dù record xuất hiện trong snapshot |
| Session bị admin revoke sau checkpoint | Bị từ chối theo ledger |
| User bị khóa sau checkpoint | Session không được xác thực |
| Session ID cũ trước rotation | Bị từ chối hoặc buộc xác thực lại |
| Session hết hạn theo thời gian hiện tại | Không được khôi phục như phiên còn hiệu lực |
| Revocation ledger không truy cập được | Fail closed theo policy; không âm thầm chấp nhận session cũ |
| Không thể xác minh lịch sử thu hồi | Invalidate phạm vi session liên quan hoặc buộc re-authentication |

Test cần gửi cookie cũ trực tiếp tới ứng dụng đã restore. Chỉ kiểm tra record đã xóa trong database hoặc cookie đã expire ở browser là chưa đủ.

## 17. Runbook vận hành

Một runbook phục hồi nên ghi rõ:

**Trước sự cố**

- Tần suất backup, retention, mã hóa và nơi lưu.
- RPO/RTO đã được chủ dịch vụ chấp thuận.
- Nguồn revocation ledger và cách replay.
- Authentication epoch hiện hành được lưu ở đâu.
- Người có quyền phê duyệt restore và cutover.
- Kịch bản kiểm thử restore gần nhất.

**Trong sự cố**

- Xác định backup checkpoint và khoảng thời gian mất dữ liệu.
- Giữ nguyên audit/revocation source mới nhất.
- Restore session store vào môi trường cô lập.
- Không cho request production dùng dữ liệu trước khi reconciliation xong.
- Nếu ledger hoặc epoch không đáng tin cậy, áp dụng forced re-authentication cho phạm vi bị ảnh hưởng.

**Sau restore**

- Kiểm tra session hợp lệ, session đã revoke và session hết hạn.
- Kiểm tra login/logout, ID rotation và user lock.
- Theo dõi tỷ lệ session lookup miss, login mới, lỗi serialization và repository latency.
- Ghi nhận số session bị loại, số user phải đăng nhập lại và thời điểm cutover.
- Giữ lại audit evidence theo chính sách lưu trữ.

## 18. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Restore Redis snapshot thẳng vào production | Session đã logout có thể xuất hiện lại | Restore cô lập, reconcile revocation trước cutover |
| Revocation ledger nằm cùng snapshot | Ledger cũng rollback, mất các lần revoke mới | Lưu độc lập hoặc replay từ audit log bền vững |
| Chỉ dựa vào cookie đã expire | Client có thể replay cookie cũ | Kiểm tra revocation phía server |
| Chỉ dựa vào TTL của Redis | Một số metadata/index hoặc expiry policy có thể không đồng bộ | Kiểm tra repository-level semantics và thời điểm hết hạn |
| Restore riêng bảng session | Thiếu attributes hoặc dữ liệu không nhất quán | Restore snapshot database nhất quán gồm cả schema và bảng liên quan |
| Tin session destroy event sẽ tự phát lại | Event lịch sử có thể không được replay | Reconcile từ audit/revocation ledger |
| Dùng backup cũ với serializer mới mà không thử | Session lỗi deserialize hoặc sai principal | Test tương thích, migration hoặc invalidate |
| Không có revocation source độc lập | Không biết session nào đã bị thu hồi sau backup | Buộc re-authentication nếu không chứng minh được trạng thái |
| Chỉ kiểm tra record trong store | Không chứng minh server từ chối cookie cũ | Thực hiện replay test qua ứng dụng sau restore |

## 19. Checklist trước khi cutover

- [ ] Xác định checkpoint backup, RPO và RTO.
- [ ] Restore vào môi trường cô lập trước khi mở traffic.
- [ ] Xác minh Redis namespace hoặc JDBC schema/bảng đầy đủ.
- [ ] Kiểm tra TTL, expiry và cleanup theo thời gian hiện tại.
- [ ] Kiểm tra index, metadata và serialization tương thích.
- [ ] Có revocation ledger/audit source mới hơn checkpoint.
- [ ] Ledger không bị rollback cùng session backup.
- [ ] Áp dụng logout, admin revoke, account lock và session rotation sau checkpoint.
- [ ] So sánh authentication epoch hiện hành với epoch trong session.
- [ ] Nếu không thể xác minh revocation, buộc đăng nhập lại trong phạm vi bị ảnh hưởng.
- [ ] Replay cookie của session đã thu hồi và xác minh server từ chối.
- [ ] Xác minh session hợp lệ được phục hồi theo policy.
- [ ] Kiểm tra event consumer, index và dashboard sau restore.
- [ ] Có phê duyệt cutover, rollback plan và audit record.

Backup giúp phục hồi dữ liệu session tại một thời điểm, nhưng không phải lịch sử đầy đủ về quyền sử dụng session ở hiện tại. Restore snapshot cũ có thể đưa lại bản ghi đã bị logout hoặc thu hồi sau checkpoint. Hãy giữ revocation ledger hoặc authentication epoch trong nguồn dữ liệu độc lập, phục hồi vào môi trường cô lập, reconcile các thay đổi mới hơn backup và thử replay cookie cũ trước khi cutover. Nếu không thể chứng minh mọi lần thu hồi đã được áp dụng, buộc xác thực lại an toàn hơn việc chấp nhận session cũ.
