# Dữ liệu phiên, dữ liệu theo dõi hết hạn và các khóa phụ trợ

Spring Session có thể lưu session trong Redis để nhiều instance ứng dụng cùng đọc và cập nhật. Một session không chỉ là một key chứa thuộc tính. Đặc biệt với RedisIndexedSessionRepository, Spring Session còn duy trì các key phụ để theo dõi thời điểm hết hạn, phát sự kiện vòng đời và tra cứu session theo principal.

Hiểu cấu trúc dữ liệu này giúp phân biệt thời điểm session hết hạn về mặt logic với thời điểm Redis xóa key vật lý. Điều đó cũng giúp chẩn đoán các trường hợp session đã hết hạn nhưng hash vẫn còn, index chưa được dọn, hoặc sự kiện hết hạn không được phát như mong đợi.

Bài này tập trung vào ba nhóm dữ liệu: hash lưu nội dung session, các key theo dõi expiration và các cấu trúc phụ trợ như index principal. Các tên key minh họa dựa trên namespace mặc định phổ biến của Spring Session; tên và chi tiết nội bộ có thể thay đổi theo repository, phiên bản và cấu hình. Ứng dụng nên thao tác qua API Spring Session thay vì phụ thuộc trực tiếp vào cấu trúc key nội bộ.

## 1. Một session có thể tương ứng với nhiều key Redis

Ở mức ứng dụng, lập trình viên làm việc với HttpSession: tạo session, đọc thuộc tính, cập nhật dữ liệu hoặc invalidate session. Ở tầng Redis, repository chuyển trạng thái đó thành các key và cấu trúc dữ liệu phù hợp.

Với RedisIndexedSessionRepository, một session có thể liên quan tới:

| Nhóm dữ liệu | Key minh họa | Vai trò |
|---|---|---|
| Hash session | spring:session:sessions:<session-id> | Lưu thời điểm tạo, lần truy cập gần nhất, timeout và các thuộc tính session |
| Key đánh dấu hết hạn | spring:session:sessions:expires:<session-id> | Có TTL tương ứng thời điểm session hết hạn logic, dùng để kích hoạt xử lý expiration |
| Set theo phút hết hạn | spring:session:expirations:<minute-bucket> | Gom các key expiration theo khoảng thời gian để tác vụ nền truy cập và hỗ trợ phát notification |
| Index principal | spring:session:index:... | Ánh xạ principal name hoặc giá trị index khác tới session ID |
| Kênh sự kiện | spring:session:channel:... | Truyền thông báo vòng đời giữa các instance đang lắng nghe |

Tên chính xác của từng key và nội dung bên trong là chi tiết triển khai của repository. Chẳng hạn, tên index có thể chứa tên chỉ mục và giá trị principal; cấu trúc kênh phụ thuộc sự kiện được phát. Không nên tự xây dựng logic ứng dụng dựa trên việc phân tích chuỗi key.

Điểm quan trọng là hash session và key theo dõi expiration có vòng đời khác nhau. Session có thể đã hết hạn logic trong khi hash vẫn còn tồn tại thêm một khoảng thời gian để Spring Session hoàn tất xử lý sự kiện và dọn các cấu trúc phụ trợ.

## 2. Hash session lưu dữ liệu gì?

Hash là nơi lưu trạng thái session. Với namespace mặc định, key thường có dạng:

~~~text
spring:session:sessions:<session-id>
~~~

Các trường nội bộ thường bao gồm:

| Trường | Ý nghĩa |
|---|---|
| creationTime | Thời điểm session được tạo |
| lastAccessedTime | Thời điểm session được truy cập gần nhất |
| maxInactiveInterval | Khoảng thời gian không hoạt động tối đa |
| sessionAttr:<name> | Giá trị của từng thuộc tính session |

Ví dụ, một session có thể chứa:

~~~text
creationTime = 2026-11-26T08:00:00Z
lastAccessedTime = 2026-11-26T08:12:00Z
maxInactiveInterval = 1800 seconds
sessionAttr:SPRING_SECURITY_CONTEXT = ...
sessionAttr:app.activeCartId = ...
~~~

Đây là mô tả khái niệm; giá trị thực được tuần tự hóa theo cấu hình repository. Một số thuộc tính có thể là byte array thay vì chuỗi dễ đọc. Không giả định rằng có thể đọc toàn bộ hash bằng mắt hoặc sửa trực tiếp một trường bằng redis-cli.

Hash có thể chứa SecurityContext, dữ liệu người dùng và trạng thái ứng dụng. Vì vậy, không đưa kết quả HGETALL hoặc nội dung thuộc tính session vào log công khai. Khi kiểm tra production, ưu tiên quan sát metadata, TTL và số lượng key; chỉ đọc giá trị chi tiết trong môi trường kiểm thử được kiểm soát.

## 3. Thời điểm hết hạn logic được tính thế nào?

Spring Session sử dụng thời gian không hoạt động tối đa, thường gọi là maxInactiveInterval. Về khái niệm, thời điểm hết hạn được xác định từ lần truy cập gần nhất cộng với khoảng không hoạt động tối đa:

~~~text
expirationTime = lastAccessedTime + maxInactiveInterval
~~~

Ví dụ:

| Giá trị | Thời điểm |
|---|---|
| lastAccessedTime | 10:00:00 |
| maxInactiveInterval | 30 phút |
| expirationTime | 10:30:00 |

Nếu người dùng tiếp tục gửi request có session hợp lệ lúc 10:20, thời điểm truy cập được cập nhật và expirationTime được tính lại. Khi đó, session có thể tiếp tục hợp lệ đến 10:50.

Đây là idle timeout, không phải absolute lifetime. Nếu nghiệp vụ yêu cầu session phải hết hạn sau một khoảng cố định kể từ khi đăng nhập, kể cả khi người dùng vẫn hoạt động, ứng dụng cần bổ sung chính sách absolute timeout riêng. Chỉ đặt maxInactiveInterval không tạo ra giới hạn tuổi tuyệt đối của session.

### TTL được làm mới khi nào?

Trong ứng dụng Servlet, Spring Session filter tải session và cập nhật thời điểm truy cập theo vòng đời request. Khi thay đổi session được lưu xuống repository, repository cập nhật dữ liệu và thời hạn key tương ứng. Chi tiết thời điểm ghi còn chịu ảnh hưởng của FlushMode và SaveMode.

Với cấu hình lưu theo ON_SAVE, thay đổi thường được ghi khi session được lưu ở cuối request. Với IMMEDIATE, repository ghi thay đổi sớm hơn. Dù dùng chế độ nào, ứng dụng không nên suy luận rằng mọi request HTTP đều làm mới mọi session: request có thể không mang session ID, không truy cập session hoặc không được filter xử lý như một request sử dụng session.

Nếu session không còn tồn tại hoặc đã hết hạn, việc gửi lại cookie cũ không khôi phục session. Ứng dụng phải xử lý request như không có session hợp lệ và áp dụng quy trình xác thực phù hợp.

## 4. Vì sao cần key đánh dấu hết hạn riêng?

Redis hỗ trợ TTL trên key, nhưng thời điểm một key hết hạn và thời điểm Redis thực sự xóa key không nhất thiết trùng nhau.

Redis sử dụng cả hai cơ chế:

- **Passive expiration:** khi một client truy cập key đã quá hạn, Redis phát hiện và loại bỏ key.
- **Active expiration:** Redis chạy các chu kỳ nền để kiểm tra một phần key có TTL và loại bỏ các key đã hết hạn.

Vì vậy, key hết TTL có thể vẫn tồn tại vật lý trong một khoảng thời gian trước khi Redis phát hiện và xóa nó. Nếu Spring Session chỉ dựa vào việc hash session biến mất đúng một thời điểm, việc phát sự kiện hết hạn và dọn index sẽ khó kiểm soát.

RedisIndexedSessionRepository sử dụng key expiration riêng cho mỗi session. Key thường có dạng:

~~~text
spring:session:sessions:expires:<session-id>
~~~

Key này được đặt TTL tương ứng với thời điểm session hết hạn logic. Khi key expiration hết hạn, Redis có thể phát keyspace notification để Spring Session xử lý sự kiện hết hạn.

Trong khi đó, hash session chính có thể được giữ lâu hơn thời điểm hết hạn logic, thường thêm khoảng 5 phút trong cơ chế Redis indexed. Khoảng lưu thêm này cho listener cơ hội tải thông tin session cần thiết khi xử lý expiration event và dọn index. Do đó:

- Hash còn tồn tại không chứng minh session vẫn hợp lệ.
- TTL của hash có thể dài hơn TTL logic của session.
- API repository mới là nơi ứng dụng nên dùng để kiểm tra session còn hợp lệ hay không.

Khoảng giữ thêm là chi tiết triển khai, không phải cam kết để ứng dụng lưu thêm dữ liệu hoặc tiếp tục cho phép người dùng sử dụng session.

## 5. Set theo phút hỗ trợ theo dõi expiration

Redis có thể trì hoãn việc phát expiration notification cho tới khi key được truy cập hoặc được chu kỳ active expiration xử lý. Để hỗ trợ việc phát hiện expiration đúng hơn, RedisIndexedSessionRepository còn dùng các set gom key expiration theo khoảng thời gian.

Key set có dạng minh họa:

~~~text
spring:session:expirations:<minute-bucket>
~~~

Set chứa tham chiếu tới những key expiration dự kiến hết hạn trong khoảng phút tương ứng. Tác vụ nền chạy định kỳ có thể đọc set của khoảng thời gian cần xử lý và truy cập các key expiration đó. Nếu key đã quá hạn nhưng chưa được Redis chủ động xử lý, thao tác truy cập có thể khiến Redis nhận ra key hết hạn và phát notification.

Luồng khái niệm:

~~~mermaid
flowchart TD
    A[Session được lưu] --> B[Ghi hash session]
    B --> C[Tạo key expiration với TTL]
    C --> D[Thêm key expiration vào set theo phút]
    D --> E[Đến khoảng thời gian cleanup]
    E --> F[Tác vụ nền truy cập các key expiration]
    F --> G{Key đã hết hạn?}
    G -->|Có| H[Redis phát expiration notification]
    G -->|Chưa| I[Tiếp tục theo dõi]
    H --> J[Spring Session xử lý expiration]
    J --> K[Dọn index và phát sự kiện phù hợp]
~~~

Set theo phút là cấu trúc theo dõi phụ trợ. Nó không phải danh sách session còn hoạt động và cũng không thay thế TTL của key expiration. Không dùng set này để hiển thị danh sách người dùng đang đăng nhập.

Tác vụ nền và notification có thể chạy trễ so với thời điểm hết hạn dự kiến. Vì vậy, ứng dụng phải kiểm tra hiệu lực session thông qua repository ở mỗi request; không dựa vào thời điểm event để cấp quyền.

## 6. Các index và kênh sự kiện liên quan

Ngoài dữ liệu expiration, RedisIndexedSessionRepository có thể duy trì index principal. Ví dụ, một principal có nhiều session:

~~~text
principal: linh.nguyen
  -> session-A
  -> session-B
  -> session-C
~~~

Index cho phép gọi findByPrincipalName để tìm các session của người dùng. Khi session bị xóa hoặc hết hạn, repository cần cập nhật index để không giữ liên kết cũ mãi mãi.

Các kênh Redis Pub/Sub hỗ trợ truyền sự kiện vòng đời giữa các instance. Ứng dụng có thể lắng nghe SessionCreatedEvent, SessionDeletedEvent hoặc SessionExpiredEvent để thực hiện tác vụ phụ như cập nhật số liệu hoặc dọn tài nguyên gắn với phiên.

Cần phân biệt:

- Hash session chứa dữ liệu của phiên.
- Key expiration và set theo phút hỗ trợ nhận biết thời điểm hết hạn.
- Principal index hỗ trợ tra cứu theo danh tính.
- Pub/Sub channel truyền thông báo vòng đời.

Không phải repository Redis nào cũng có đầy đủ index và event. RedisSessionRepository đơn giản tập trung vào lưu và tìm session theo ID; RedisIndexedSessionRepository cung cấp khả năng index principal và cơ chế sự kiện liên quan. Hãy xác nhận implementation đang dùng trước khi dựa vào các key phụ này.

## 7. Cấu hình Redis keyspace notification

Để Spring Session nhận expiration event từ Redis, Redis cần bật keyspace notification phù hợp. Cấu hình thường dùng cho RedisIndexedSessionRepository là:

~~~text
CONFIG SET notify-keyspace-events Egx
~~~

Trong chuỗi cấu hình:

- E bật keyevent notification.
- g bật các sự kiện generic cần thiết.
- x bật sự kiện expired.

Nếu Redis được quản lý hoặc ứng dụng không có quyền chạy CONFIG, quản trị viên có thể cấu hình notification ở phía Redis. Khi ứng dụng không được phép tự cấu hình Redis, có thể khai báo ConfigureRedisAction.NO_OP theo hướng dẫn Spring Session để bỏ qua thao tác CONFIG lúc khởi động. NO_OP không bật notification; Redis vẫn phải được quản trị viên cấu hình đúng.

Không nên thay đổi notify-keyspace-events trên Redis production mà chưa kiểm tra tác động tới các ứng dụng khác. Đây là cấu hình cấp Redis server, có thể ảnh hưởng các subscriber khác. Hãy xác nhận cấu hình thực tế và các quyền ACL liên quan trước khi triển khai.

### Sự kiện không phải hàng đợi bền vững

Redis keyspace notification và Pub/Sub có thể mất thông báo khi listener mất kết nối hoặc ứng dụng đang dừng. Không dùng SessionExpiredEvent làm bằng chứng duy nhất để thực hiện giao dịch nghiệp vụ quan trọng, ghi nhận kiểm toán bắt buộc hoặc thu hồi quyền trên một hệ thống khác.

Listener nên ngắn, idempotent và có thể xử lý lặp lại. Nếu nghiệp vụ yêu cầu xử lý chắc chắn, hãy ghi sự kiện vào cơ chế bền vững riêng như transactional outbox hoặc hàng đợi có lưu trữ.

## 8. Trình tự lưu, truy cập và hết hạn session

Có thể mô tả vòng đời một session trong Redis indexed theo các bước:

1. Request đầu tiên yêu cầu tạo session.
2. Spring Session tạo session object và repository lưu hash session.
3. Repository tạo key expiration có TTL theo maxInactiveInterval.
4. Repository đưa key expiration vào set của minute bucket tương ứng.
5. Nếu session có principal, repository duy trì index principal.
6. Request tiếp theo tải session, cập nhật lastAccessedTime và tính lại thời điểm hết hạn.
7. Khi lưu session, repository cập nhật hash, TTL và dữ liệu theo dõi expiration.
8. Khi session hết hạn, key expiration có thể phát notification.
9. Listener xử lý expiration, phát event phù hợp và dọn liên kết index.
10. Hash session chính được Redis dọn sau thời hạn lưu thêm.

Đây là mô hình khái niệm. Thứ tự lệnh Redis, transaction/pipeline và thời điểm lưu chính xác phụ thuộc phiên bản repository. Ứng dụng không nên dựa vào thứ tự thao tác nội bộ để xây dựng logic nghiệp vụ.

## 9. Quan sát TTL và key trong Redis

Có thể dùng redis-cli để quan sát metadata trong môi trường kiểm thử hoặc khi vận hành có kiểm soát.

Liệt kê key theo namespace bằng SCAN:

~~~bash
redis-cli --scan --pattern 'spring:session:sessions:*'
~~~

Tìm key expiration:

~~~bash
redis-cli --scan --pattern 'spring:session:sessions:expires:*'
~~~

Kiểm tra TTL của một key đã biết:

~~~bash
redis-cli PTTL 'spring:session:sessions:expires:<session-id>'
~~~

PTTL trả thời gian còn lại tính bằng millisecond. Các kết quả đặc biệt thường gặp:

| Kết quả | Ý nghĩa |
|---|---|
| Số dương | Số millisecond còn lại trước khi key hết hạn |
| -1 | Key tồn tại nhưng không có expiration |
| -2 | Key không tồn tại |

Đừng so sánh TTL của hash session với TTL key expiration rồi kết luận repository sai. Hash có thể được giữ thêm để phục vụ xử lý expiration; marker mới thể hiện thời điểm hết hạn logic gần nhất trong cơ chế indexed.

Tránh chạy KEYS trên keyspace production lớn. KEYS có thể chặn Redis trong lúc quét. SCAN phù hợp hơn cho thao tác quan sát từng phần, nhưng vẫn cần giới hạn tần suất và xử lý cursor đúng cách.

Không dùng HGETALL để in toàn bộ hash session production. Hash có thể chứa SecurityContext hoặc thông tin cá nhân. Nếu cần kiểm tra, hãy dùng môi trường thử nghiệm với dữ liệu giả hoặc chỉ quan sát TYPE, TTL và số lượng key.

## 10. Chẩn đoán các tình huống expiration

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Session không còn được dùng nhưng hash vẫn tồn tại | Hash được giữ thêm sau thời điểm hết hạn logic | Kiểm tra key expiration và gọi findById qua repository |
| Session hết hạn nhưng event không đến | Keyspace notification chưa bật, listener mất kết nối hoặc event bị bỏ lỡ | Kiểm tra notify-keyspace-events, subscription và log listener |
| Principal index còn ID cũ | Cleanup chưa hoàn tất hoặc notification bị mất | Kiểm tra session bằng repository; xác minh cấu hình notification và index |
| Session hết hạn sớm | TTL bị refresh sai, request không đi qua cùng repository hoặc Redis eviction | So sánh lastAccessedTime, maxInactiveInterval và eviction metrics |
| Một instance thấy session, instance khác không thấy | Namespace, Redis endpoint hoặc serializer khác nhau | So sánh cấu hình runtime giữa các node |
| Key phụ tăng bất thường | Cleanup không hoạt động, session tạo quá nhiều hoặc TTL chưa được áp dụng | Theo dõi số lượng key theo prefix và kiểm tra tác vụ nền |
| Event đến trễ | Redis expiration không đảm bảo đúng thời điểm từng millisecond | Kiểm tra TTL, notification và lịch cleanup; không dựa event để cấp quyền |

Khi điều tra, cần xác định repository có thực sự trả session hợp lệ hay không. Nếu findById trả null, request phải được xem như không có session hợp lệ, kể cả khi hash vật lý vẫn còn trong Redis. Nếu Redis timeout hoặc lỗi kết nối, đó là lỗi hạ tầng chứ không phải session hết hạn.

## 11. Kiểm thử dữ liệu phiên và key expiration

Một bộ integration test nên xác nhận cả session logic lẫn cấu trúc expiration.

| Ca kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| Tạo session | Lưu session qua repository | Hash session được tạo |
| Đặt timeout ngắn | Cấu hình maxInactiveInterval ngắn trong test | Repository coi session hết hạn sau khoảng không hoạt động |
| Làm mới session | Truy cập session trước khi hết hạn | lastAccessedTime và thời điểm hết hạn được cập nhật |
| Không hoạt động | Không gửi request quá timeout | findById không trả session hợp lệ |
| Kiểm tra key expiration | Quan sát marker trong Redis test | Marker có TTL phù hợp với expiration logic |
| Kiểm tra hash giữ thêm | So sánh TTL hash với marker | Hash có thể tồn tại lâu hơn thời điểm hết hạn logic |
| Principal index | Tạo session có principal | findByPrincipalName trả đúng session |
| Xóa chủ động | Gọi deleteById | Session bị xóa và index được cập nhật |
| Expiration event | Bật keyspace notification và lắng nghe event | Listener nhận sự kiện hết hạn theo cơ chế repository |
| Redis mất kết nối | Ngắt kết nối trong test tích hợp | Lỗi hạ tầng được nhận diện riêng |

Ví dụ kiểm thử API repository:

~~~java
Session session = repository.createSession();
session.setMaxInactiveInterval(Duration.ofSeconds(2));
repository.save(session);

String id = session.getId();

assertThat(repository.findById(id)).isNotNull();

// Chờ hết hạn bằng polling có giới hạn trong integration test.
await().atMost(Duration.ofSeconds(5))
       .untilAsserted(() ->
           assertThat(repository.findById(id)).isNull()
       );
~~~

Ví dụ này cần một repository và Redis test environment đã cấu hình. Không dùng sleep cố định dài trong unit test; polling với timeout giúp test ổn định hơn. Tùy API và phiên bản, kiểu generic của Session có thể khác, nhưng nguyên tắc là kiểm tra hiệu lực qua repository chứ không chỉ nhìn key có còn trong Redis hay không.

Để kiểm tra event, đăng ký listener test nhận SessionExpiredEvent, bật notification trong Redis test container và chờ event với thời hạn hữu hạn. Không dùng một event listener mock làm bằng chứng rằng Redis production đã bật notification đúng.

## 12. Những điều không nên làm với key nội bộ

Các key session và expiration là cấu trúc do repository quản lý. Tránh:

- Tự tạo key có tiền tố spring:session rồi mong Spring Session coi đó là session hợp lệ.
- Xóa key expiration hoặc set theo phút để ép event xảy ra.
- Sửa TTL trực tiếp trên hash session mà không cập nhật marker và index liên quan.
- Xóa index principal trực tiếp bằng SREM hoặc DEL khi chưa hiểu toàn bộ vòng đời.
- Dùng KEYS * để quét production.
- Dùng FLUSHDB hoặc FLUSHALL để dọn session của một ứng dụng.
- Dựa vào sự kiện Pub/Sub để bảo đảm một hành động nghiệp vụ được thực hiện đúng một lần.
- Dựa vào hash còn tồn tại để cho phép request tiếp tục dùng session.

Nếu cần thu hồi một session, dùng SessionRepository.deleteById hoặc cơ chế logout phù hợp. Nếu cần thu hồi theo principal, dùng FindByIndexNameSessionRepository khi repository hỗ trợ. API giúp repository cập nhật các key và index liên quan theo logic nội bộ.

## 13. Checklist vận hành expiration

Trước khi triển khai Spring Session Redis lên production, hãy xác nhận:

- Namespace được đặt riêng cho ứng dụng và môi trường; mọi instance cùng ứng dụng dùng một namespace.
- maxInactiveInterval phù hợp với chính sách đăng nhập.
- Cookie timeout và server-side timeout được thiết kế riêng nhưng nhất quán.
- Hiểu hash session và key expiration có vòng đời khác nhau.
- Redis keyspace notification được bật nếu repository indexed cần event expiration.
- Tác vụ nền và listener có thể kết nối tới Redis, và log lỗi được theo dõi.
- ACL cho phép key pattern, command và Pub/Sub channel cần thiết.
- Không phụ thuộc event expiration cho giao dịch nghiệp vụ bền vững.
- Có metric về số session, lookup miss, key phụ, TTL, Redis memory và lỗi listener.
- Integration test xác nhận session hết hạn logic, index được dọn và event hoạt động trên topology tương tự production.

Khi đọc dữ liệu Redis, hãy nhớ ba lớp: hash session chứa trạng thái, expiration marker và bucket theo phút giúp theo dõi thời điểm hết hạn, còn index và channel hỗ trợ tra cứu cùng thông báo vòng đời. Redis có thể giữ một số key vật lý thêm sau khi session hết hạn logic; điều đó là một phần của cơ chế xử lý expiration. Ứng dụng cần dựa vào repository để xác định session hợp lệ, đồng thời vận hành notification và cleanup đúng cách để các cấu trúc phụ trợ không bị tồn đọng.

## Tài liệu tham khảo

- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [RedisIndexedSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [Spring Session — Session Events](https://docs.spring.io/spring-session/reference/api.html)
- [Redis — EXPIRE command](https://redis.io/docs/latest/commands/expire/)
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis — PTTL command](https://redis.io/docs/latest/commands/pttl/)

