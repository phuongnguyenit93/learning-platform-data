# Ma trận khả năng: thời hạn, sự kiện, chỉ mục và chính sách lưu của từng repository

Spring Session cung cấp một API chung để ứng dụng Servlet làm việc với session, trong khi repository quyết định session được lưu ở đâu và những khả năng vận hành nào đi kèm. Hai ứng dụng cùng dùng `HttpSession` có thể có hành vi khác nhau về dọn session hết hạn, tra cứu phiên theo người dùng, phát sự kiện và ghi thay đổi xuống kho dữ liệu, tùy repository được cấu hình.

Bài này so sánh các repository thường gặp khi triển khai Spring Session với Redis, JDBC hoặc Map. Trọng tâm là bốn câu hỏi: session hết hạn được xử lý thế nào, repository có phát sự kiện vòng đời không, có thể tìm session theo chỉ mục nào và dữ liệu được ghi xuống kho theo chính sách nào.

## 1. API chung và khả năng riêng của repository

API nền tảng là `SessionRepository<S extends Session>`. Nó cung cấp các thao tác tạo, lưu, tìm và xóa session:

~~~java
S createSession();
void save(S session);
S findById(String id);
void deleteById(String id);
~~~

Đối tượng `Session` chứa ID, thời điểm tạo, thời điểm truy cập gần nhất, thời gian không hoạt động tối đa và các thuộc tính dạng key-value. Khi `findById` không tìm thấy session hoặc session đã hết hạn, repository trả về `null`.

Một số repository còn triển khai `FindByIndexNameSessionRepository`. Giao diện này bổ sung khả năng tìm session theo tên chỉ mục và giá trị chỉ mục; trường hợp phổ biến nhất là tìm các session thuộc một principal bằng `findByPrincipalName`. Không phải mọi `SessionRepository` đều có khả năng tra cứu này.

Trong ứng dụng Servlet, `SessionRepositoryFilter` kết nối repository với API `HttpSession`. Phần lớn controller và service nên tiếp tục dùng `HttpSession`; việc inject repository trực tiếp phù hợp hơn cho chức năng quản trị session, chẳng hạn xem các phiên đang hoạt động hoặc đăng xuất một phiên cụ thể.

Điểm cần nhớ là API chung không tự cung cấp TTL, chỉ mục hay sự kiện. Những khả năng đó phụ thuộc implementation và cấu hình của kho dữ liệu.

## 2. Ma trận khả năng của các repository

| Repository | Thời hạn và dọn dữ liệu | Sự kiện vòng đời | Chỉ mục và tra cứu | Chính sách lưu |
|---|---|---|---|---|
| `MapSessionRepository` | Session có `maxInactiveInterval`; Map được truyền vào phải tự chịu trách nhiệm dọn session hết hạn. Không có hạ tầng dọn dẹp được cấu hình tự động. | Không hỗ trợ `SessionDeletedEvent` hoặc `SessionExpiredEvent`. | Tra cứu theo session ID; implementation này chỉ triển khai `SessionRepository`. | Lưu vào Map khi gọi `save`. Không có cấu hình `FlushMode` hoặc `SaveMode` riêng. |
| `RedisSessionRepository` | Redis đặt TTL cho key session theo thời gian không hoạt động tối đa. Session hết hạn không được trả về khi tra cứu. | Không hỗ trợ phát session event. | Không tạo chỉ mục phụ; tra cứu chính theo session ID. | Hỗ trợ `FlushMode` và `SaveMode`; mặc định thường là `ON_SAVE` và `ON_SET_ATTRIBUTE`. |
| `RedisIndexedSessionRepository` | Dùng TTL cùng khóa đánh dấu hết hạn và lịch kiểm tra expiration. Hash session được giữ thêm khoảng 5 phút sau thời điểm hết hạn logic để xử lý sự kiện và dọn tài nguyên. | Hỗ trợ các sự kiện tạo, xóa và hết hạn session thông qua cơ chế message/keyspace notification của Redis. | Mặc định có chỉ mục principal name; có thể cấu hình `IndexResolver` để xây dựng chỉ mục khác. | Hỗ trợ `FlushMode` và `SaveMode`; mặc định thường là `ON_SAVE` và `ON_SET_ATTRIBUTE`. |
| `JdbcIndexedSessionRepository` | Lưu `MAX_INACTIVE_INTERVAL` và `EXPIRY_TIME` trong bảng session. Job dọn session hết hạn mặc định chạy mỗi phút. | Không hỗ trợ phát session event. | Có chỉ mục theo `SESSION_ID`, `EXPIRY_TIME` và `PRINCIPAL_NAME`; hỗ trợ tra cứu theo principal name. | Hỗ trợ `FlushMode` và `SaveMode`. Thao tác JDBC được thực hiện trong transaction; mặc định propagation là `REQUIRES_NEW`. |

Ma trận cho thấy ba lựa chọn chính có đặc điểm khác nhau:

- Chọn `RedisSessionRepository` khi ứng dụng chỉ cần lưu và lấy session theo ID, đồng thời muốn dùng TTL của Redis.
- Chọn `RedisIndexedSessionRepository` khi cần tra cứu session theo principal hoặc cần nhận sự kiện vòng đời để quản lý tài nguyên gắn với session.
- Chọn `JdbcIndexedSessionRepository` khi muốn lưu session trong cơ sở dữ liệu quan hệ, dùng chỉ mục principal có sẵn và tận dụng transaction cùng công cụ vận hành cơ sở dữ liệu. Cần thiết kế riêng nếu nghiệp vụ yêu cầu sự kiện vòng đời.

`MapSessionRepository` hữu ích cho kiểm thử hoặc ứng dụng đơn giản. Có thể truyền vào một Map phân tán, nhưng khả năng chia sẻ, xóa hết hạn và phát sự kiện khi đó phụ thuộc Map và phần tích hợp bên ngoài; bản thân repository không bổ sung các khả năng này.

## 3. Thời hạn session và thời điểm dọn dữ liệu

### Thời hạn không hoạt động

`maxInactiveInterval` là khoảng thời gian session có thể không được truy cập trước khi hết hạn. Giá trị mặc định thường là 30 phút. Đây là thời hạn không hoạt động, không phải thời gian sống tuyệt đối kể từ lúc đăng nhập. Request tiếp tục sử dụng session sẽ cập nhật thời điểm truy cập gần nhất và kéo dài thời điểm hết hạn theo chính sách của repository.

Có thể đặt thời hạn mặc định ở cấu hình Spring Session hoặc cấu hình Spring Boot tương ứng. Với cấu hình annotation cho Servlet, ví dụ:

~~~java
@Configuration
@EnableJdbcHttpSession(maxInactiveIntervalInSeconds = 1800)
class SessionConfiguration {
}
~~~

Nếu cần thay đổi thời hạn cho một session cụ thể, API `Session` có thao tác đặt `maxInactiveInterval`. Hãy chọn thời hạn theo rủi ro và trải nghiệm người dùng; session đăng nhập quản trị thường cần chính sách khác session lưu lựa chọn giao diện.

### Hết hạn logic và dọn dữ liệu vật lý

Hai thời điểm này không nhất thiết trùng nhau. Khi hết hạn logic, repository phải xem session là không còn hợp lệ và không trả về nó. Việc xóa bản ghi hoặc key khỏi kho dữ liệu có thể diễn ra sau đó theo cơ chế cleanup.

**RedisSessionRepository** dựa vào TTL của key session. Khi TTL kết thúc, Redis loại bỏ key. Repository không phát sự kiện vòng đời cho ứng dụng.

**RedisIndexedSessionRepository** cần giữ dữ liệu session đủ lâu để xử lý việc xóa chỉ mục và phát sự kiện. Repository tạo khóa expiration riêng với thời hạn logic; hash session có thể được giữ thêm khoảng 5 phút. `findById` vẫn không trả về session đã hết hạn logic, dù hash có thể còn tồn tại trong khoảng thời gian phục vụ cleanup. Repository cũng theo dõi các thời điểm hết hạn theo từng khoảng phút và có tác vụ nền truy cập các khóa expiration để Redis phát thông báo trong trường hợp key đã hết hạn nhưng chưa được Redis chủ động quét.

**JdbcIndexedSessionRepository** ghi thời điểm hết hạn vào cột `EXPIRY_TIME`. Tác vụ cleanup mặc định chạy mỗi phút để xóa các session hết hạn cùng các thuộc tính liên quan. Có thể đổi lịch bằng thuộc tính `cleanupCron` của `@EnableJdbcHttpSession` hoặc cấu hình Spring Boot tương ứng. Ví dụ, biểu thức sau chạy vào đầu mỗi phút:

~~~java
@Configuration
@EnableJdbcHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    cleanupCron = "0 * * * * *"
)
class SessionConfiguration {
}
~~~

Tác vụ cleanup chủ yếu quản lý dữ liệu tồn dư trong bảng. Không nên dùng thời điểm job chạy để quyết định quyền truy cập: ứng dụng phải coi session hết hạn là không hợp lệ ngay cả khi dòng dữ liệu chưa được dọn vật lý.

**MapSessionRepository** không cung cấp job cleanup. Tài liệu API yêu cầu Map được truyền vào chịu trách nhiệm purge session hết hạn. Nếu dùng `ConcurrentHashMap` thông thường, cần tự xây dựng cơ chế dọn dữ liệu hoặc chỉ dùng trong kiểm thử ngắn hạn.

### Cookie không phải TTL của repository

Cookie session quyết định trình duyệt giữ và gửi session ID trong bao lâu. TTL repository quyết định máy chủ còn chấp nhận session đó hay không. Hai cấu hình liên quan nhưng độc lập:

- Cookie còn hạn nhưng session trong Redis/JDBC đã hết hạn: máy chủ không tìm thấy session hợp lệ và luồng xác thực phải xử lý lại.
- Trình duyệt xóa cookie trước khi session hết hạn: dữ liệu session phía máy chủ có thể còn tồn tại cho đến khi TTL hoặc cleanup loại bỏ.
- Đặt cookie sống lâu hơn không làm session phía máy chủ sống lâu hơn.

Khi thiết kế đăng nhập, cần phối hợp thời hạn cookie, timeout của Servlet/Spring Session và chính sách xác thực lại.

## 4. Sự kiện vòng đời: repository nào có thể phát?

Các sự kiện thường cần quan tâm gồm:

- `SessionCreatedEvent`: session được tạo.
- `SessionDeletedEvent`: session bị xóa chủ động.
- `SessionExpiredEvent`: session hết hạn.
- `SessionDestroyedEvent`: lớp sự kiện tổng quát cho các tình huống session bị hủy; hai sự kiện xóa và hết hạn là các dạng cụ thể.

Trong nhóm repository của bài này, `RedisIndexedSessionRepository` là lựa chọn hỗ trợ các sự kiện vòng đời. `RedisSessionRepository` và `JdbcIndexedSessionRepository` không hỗ trợ phát session event theo implementation hiện hành. `MapSessionRepository` cũng không phát `SessionDeletedEvent` hoặc `SessionExpiredEvent`.

Có thể lắng nghe sự kiện trong Spring bằng `@EventListener`:

~~~java
@Component
public class SessionLifecycleListener {

    @EventListener
    public void onCreated(SessionCreatedEvent event) {
        // Ghi nhận session mới hoặc cập nhật số liệu vận hành.
    }

    @EventListener
    public void onDeleted(SessionDeletedEvent event) {
        // Dọn tài nguyên phụ gắn với session bị xóa.
    }

    @EventListener
    public void onExpired(SessionExpiredEvent event) {
        // Dọn tài nguyên phụ gắn với session hết hạn.
    }
}
~~~

### Điều kiện để nhận sự kiện từ Redis

Với repository indexed, Spring Session đăng ký listener nhận message từ Redis. Để nhận sự kiện xóa và hết hạn, Redis cần bật keyspace notification cho lệnh tổng quát và sự kiện hết hạn. Cấu hình thường dùng là:

~~~text
CONFIG SET notify-keyspace-events Egx
~~~

Khi dùng annotation cấu hình indexed, Spring Session có thể tự cấu hình các keyspace notification cần thiết nếu Redis cho phép lệnh cấu hình. Với Redis được quản lý hoặc môi trường bảo mật không cho phép lệnh `CONFIG`, ứng dụng có thể cung cấp `ConfigureRedisAction.NO_OP` và nhờ quản trị viên cấu hình notification trên Redis.

Không nên coi event hết hạn của Redis là đồng hồ chính xác đến từng giây. Redis không cam kết phát sự kiện ngay đúng thời điểm TTL kết thúc nếu key chưa được truy cập; cơ chế expiration store và tác vụ nền của Spring Session giúp thời điểm phát sự kiện có tính xác định cao hơn. Trong Redis Cluster, cần kiểm tra giới hạn subscription theo node của phiên bản đang dùng, vì sự kiện từ node khác có thể không được listener nhận và chỉ mục liên quan có thể chưa được dọn.

Sự kiện qua Redis Pub/Sub phục vụ xử lý vòng đời, không phải hàng đợi nghiệp vụ bền vững. Listener có thể bị gián đoạn khi ứng dụng mất kết nối. Vì vậy:

- Listener nên idempotent: nhận cùng sự kiện nhiều lần không gây sai lệch.
- Giữ listener ngắn và tránh chạy công việc dài ngay trên luồng nhận message.
- Không dùng sự kiện session làm bằng chứng duy nhất cho giao dịch, kiểm toán hoặc nghĩa vụ nghiệp vụ.
- Nếu cần xử lý chắc chắn, hãy ghi trạng thái vào cơ sở dữ liệu hoặc phát sự kiện nghiệp vụ qua outbox/hàng đợi bền vững.

## 5. Chỉ mục và tra cứu session

### Chỉ mục principal name

Một yêu cầu quản trị thường gặp là xem người dùng đang đăng nhập trên bao nhiêu trình duyệt hoặc thiết bị, rồi cho phép đăng xuất một phiên cụ thể. Đây là lý do cần `FindByIndexNameSessionRepository`.

Ví dụ:

~~~java
@Service
public class SessionAdministration {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public SessionAdministration(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    public void logoutSession(String principalName, String sessionId) {
        Map<String, ? extends Session> userSessions =
                sessions.findByPrincipalName(principalName);

        if (userSessions.containsKey(sessionId)) {
            sessions.deleteById(sessionId);
        }
    }
}
~~~

Ví dụ này kiểm tra session ID có thuộc principal trước khi xóa. Trong ứng dụng thực tế, quyền gọi chức năng quản trị và cách xác định principal phải được bảo vệ ở tầng service/controller; không cho phép người dùng gửi một session ID bất kỳ rồi xóa mà không kiểm tra quyền.

`RedisIndexedSessionRepository` và `JdbcIndexedSessionRepository` triển khai `FindByIndexNameSessionRepository`. `RedisSessionRepository` và `MapSessionRepository` không cung cấp tra cứu theo principal qua API này.

### Redis: chỉ mục có thể tùy chỉnh

`RedisIndexedSessionRepository` mặc định sử dụng `PrincipalNameIndexResolver` để xây dựng chỉ mục principal name. Repository lưu các tập hợp ID session theo giá trị chỉ mục để có thể tra cứu mà không phải quét toàn bộ session.

Có thể cấu hình `IndexResolver` riêng khi ứng dụng cần chỉ mục khác, ví dụ mã tenant hoặc một thuộc tính định danh đã được chuẩn hóa. Chỉ mục bổ sung làm tăng số cấu trúc Redis cần cập nhật và dọn dẹp. Chỉ nên tạo chỉ mục cho truy vấn vận hành thực sự cần, không biến mọi thuộc tính session thành một chỉ mục.

### JDBC: chỉ mục từ schema quan hệ

Schema mặc định của Spring Session JDBC tách dữ liệu session và thuộc tính thành hai bảng:

- `SPRING_SESSION` lưu ID nội bộ, session ID, thời điểm tạo, lần truy cập gần nhất, thời hạn không hoạt động, thời điểm hết hạn và principal name.
- `SPRING_SESSION_ATTRIBUTES` lưu từng thuộc tính theo session, thường dưới dạng mảng byte đã tuần tự hóa.

Với PostgreSQL, các chỉ mục mặc định quan trọng có dạng:

~~~sql
CREATE UNIQUE INDEX SPRING_SESSION_IX1 ON SPRING_SESSION (SESSION_ID);
CREATE INDEX SPRING_SESSION_IX2 ON SPRING_SESSION (EXPIRY_TIME);
CREATE INDEX SPRING_SESSION_IX3 ON SPRING_SESSION (PRINCIPAL_NAME);
~~~

Chỉ mục `SESSION_ID` giúp tìm một session cụ thể; `EXPIRY_TIME` hỗ trợ cleanup; `PRINCIPAL_NAME` hỗ trợ truy vấn các phiên của người dùng. Bảng thuộc tính có khóa chính kết hợp session nội bộ và tên thuộc tính, nhờ đó mỗi thuộc tính có thể được lưu/cập nhật riêng.

`JdbcIndexedSessionRepository` không tự tạo chỉ mục cho mọi thuộc tính trong `SPRING_SESSION_ATTRIBUTES`. Nếu cần truy vấn theo tenant hoặc thuộc tính tùy chỉnh, phải thiết kế schema và câu SQL tương ứng, hoặc duy trì bảng tra cứu riêng. Không nên giả định rằng việc thêm thuộc tính vào `HttpSession` sẽ tự làm thuộc tính đó có thể truy vấn hiệu quả trong SQL.

## 6. Chính sách lưu: FlushMode và SaveMode

Hai khái niệm này giải quyết hai câu hỏi khác nhau:

- `FlushMode` quyết định **khi nào** thay đổi được ghi xuống kho.
- `SaveMode` quyết định **những thuộc tính nào** được xem là cần ghi.

Các repository Redis và JDBC hỗ trợ cả hai chế độ này. Giá trị mặc định thường là `FlushMode.ON_SAVE` và `SaveMode.ON_SET_ATTRIBUTE`.

### FlushMode

| Chế độ | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `ON_SAVE` | Ghi khi `SessionRepository.save(session)` được gọi; trong web request thường là gần thời điểm response được commit. | Lựa chọn mặc định phù hợp với phần lớn request Servlet, giảm số lần ghi. |
| `IMMEDIATE` | Ghi xuống kho sớm nhất có thể sau thao tác thay đổi session. | Khi cần thay đổi được nhìn thấy sớm hơn giữa các request, chấp nhận thêm thao tác I/O. |

`IMMEDIATE` không tự tạo giao dịch nghiệp vụ nguyên tử. Nó chỉ thay đổi thời điểm ghi session xuống repository. Nếu cần đồng bộ một cập nhật session với thay đổi đơn hàng hoặc thanh toán, phải thiết kế transaction và tính nhất quán ở tầng nghiệp vụ.

### SaveMode

| Chế độ | Thuộc tính được ghi | Tác động |
|---|---|---|
| `ON_SET_ATTRIBUTE` | Thuộc tính được đặt hoặc thay đổi qua thao tác session. | Ghi ít dữ liệu hơn; giảm nguy cơ request song song ghi đè thuộc tính không liên quan. |
| `ON_GET_ATTRIBUTE` | Như `ON_SET_ATTRIBUTE`, cộng thêm thuộc tính đã được đọc. | Hữu ích nếu code đọc một object rồi sửa object tại chỗ mà không gọi lại `setAttribute`. |
| `ALWAYS` | Ghi tất cả thuộc tính mỗi lần lưu. | Đơn giản nhưng tăng lượng ghi và tăng nguy cơ ghi đè thay đổi từ request song song. |

Ví dụ: controller lấy một danh sách từ session rồi thêm phần tử vào chính object đó. Với chính sách chỉ theo dõi thao tác set, repository có thể không biết thuộc tính đã thay đổi nếu code không gọi `setAttribute` lại. Cách rõ ràng hơn là tạo giá trị mới hoặc đặt lại thuộc tính sau khi sửa:

~~~java
@SuppressWarnings("unchecked")
List<String> recentItems =
        (List<String>) session.getAttribute("app.recentItems");

List<String> updated = new ArrayList<>(
        recentItems == null ? List.of() : recentItems);
updated.add(itemId);

session.setAttribute("app.recentItems", updated);
~~~

Trong môi trường nhiều request đồng thời, `ON_SET_ATTRIBUTE` thường là điểm bắt đầu tốt. `ON_GET_ATTRIBUTE` và đặc biệt `ALWAYS` có thể làm tăng khả năng một request ghi lại snapshot cũ lên thay đổi mới hơn. Không chế độ lưu nào thay thế khóa, optimistic locking hoặc transaction cho dữ liệu nghiệp vụ cần tính nguyên tử.

### Cấu hình minh họa

Redis indexed:

~~~java
@Configuration
@EnableRedisIndexedHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    redisNamespace = "shop:session",
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
class RedisSessionConfiguration {
}
~~~

JDBC:

~~~java
@Configuration
@EnableJdbcHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    cleanupCron = "0 * * * * *",
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
class JdbcSessionConfiguration {
}
~~~

Trong một ứng dụng Servlet, hãy chọn một repository làm nguồn session chính. Không bật đồng thời hai cấu hình để cùng quản lý một `HttpSession`. Nếu dùng Spring Boot, tên property và cách auto-configure có thể thay đổi theo phiên bản; cần đối chiếu với phiên bản Spring Boot/Spring Session được quản lý trong dependency BOM của dự án.

## 7. Chính sách tuần tự hóa và độ bền của dữ liệu

Chính sách lưu thay đổi không đồng nghĩa với định dạng dữ liệu và độ bền sau sự cố.

### Redis

Redis repository lưu mỗi session dưới dạng cấu trúc Redis, thường là hash. Thuộc tính Java cần được tuần tự hóa. Cấu hình mặc định của Spring Session Redis dùng Java serialization; có thể thay bằng `RedisSerializer` riêng thông qua bean có tên `springSessionDefaultRedisSerializer`.

Nếu nhiều instance hoặc nhiều ứng dụng cùng đọc session, chúng phải tương thích về serializer, tên lớp và cấu trúc thuộc tính. Đổi class hoặc kiểu dữ liệu khi session cũ vẫn còn có thể làm deserialize thất bại. Namespace riêng giúp tách key giữa các ứng dụng cùng Redis instance.

Việc Redis giữ dữ liệu qua restart phụ thuộc cấu hình persistence, replication và chính sách vận hành của Redis như RDB/AOF. Spring Session không tự quyết định các chính sách này.

### JDBC

Mặc định, JDBC repository chuyển thuộc tính thành byte array, thường bằng Java serialization, rồi lưu trong bảng thuộc tính. Có thể tùy biến `ConversionService` để dùng định dạng khác như JSON; nếu dùng kiểu JSON riêng của cơ sở dữ liệu, cần điều chỉnh kiểu cột và câu SQL insert/update tương ứng.

Các thao tác JDBC của Spring Session được thực hiện trong transaction. Mặc định transaction propagation là `REQUIRES_NEW`, nhằm tránh bị ảnh hưởng ngoài ý muốn bởi transaction hiện tại, chẳng hạn một transaction chỉ đọc. Điều đó cũng có nghĩa là thay đổi session có thể commit độc lập với transaction nghiệp vụ bao quanh request. Không giả định rằng rollback của giao dịch đơn hàng sẽ tự động rollback mọi thay đổi session.

Độ bền cuối cùng phụ thuộc transaction log, replication, backup và chính sách khôi phục của cơ sở dữ liệu.

### Map

Map chỉ giữ dữ liệu theo khả năng của Map được truyền vào. Với `ConcurrentHashMap` trong bộ nhớ, dữ liệu mất khi tiến trình dừng. Một Map phân tán có thể bổ sung khả năng chia sẻ và lưu trữ, nhưng các đặc tính đó thuộc implementation của Map, không phải cam kết chung của `MapSessionRepository`.

## 8. Chọn repository theo yêu cầu vận hành

| Yêu cầu | Lựa chọn phù hợp để đánh giá | Lý do |
|---|---|---|
| Chỉ cần session chia sẻ giữa nhiều instance và tìm theo session ID | `RedisSessionRepository` | TTL của Redis, cấu trúc đơn giản, không phát sinh chỉ mục phụ. |
| Cần xem hoặc xóa tất cả session theo người dùng | `RedisIndexedSessionRepository` hoặc `JdbcIndexedSessionRepository` | Cả hai hỗ trợ tra cứu principal name; chọn theo kho dữ liệu và yêu cầu vận hành. |
| Cần nhận sự kiện tạo, xóa hoặc hết hạn session | `RedisIndexedSessionRepository` | Có cơ chế sự kiện Redis; cần cấu hình notification và chấp nhận đặc tính giao nhận của Pub/Sub. |
| Muốn session nằm trong cơ sở dữ liệu quan hệ, có thể truy vấn principal và cleanup bằng SQL | `JdbcIndexedSessionRepository` | Có schema, chỉ mục session/principal/expiry và transaction JDBC. |
| Cần kiểm thử nhanh hoặc chạy một tiến trình đơn giản | `MapSessionRepository` | Ít hạ tầng; phải tự quản lý cleanup nếu cần và không có session events tích hợp. |
| Cần audit hoặc xử lý nghiệp vụ chắc chắn khi session hết hạn | Thiết kế thêm kho sự kiện bền vững | Không repository nào trong ma trận nên được xem là event log nghiệp vụ bền vững. |

Không nên chọn repository chỉ dựa trên tốc độ đọc/ghi. Hãy cân nhắc cả khả năng khôi phục, cách quản trị đăng xuất nhiều thiết bị, chi phí cleanup, khả năng tìm session và những hành động cần thực hiện khi session bị hủy.

## 9. Kiểm thử và giám sát theo từng khả năng

Một bộ kiểm thử tích hợp nên kiểm tra các hành vi thực tế của repository, không chỉ kiểm thử controller với `MockHttpSession`.

**Kiểm tra thời hạn**

- Tạo session với timeout ngắn, chờ quá thời hạn và xác nhận `findById` không còn trả session hợp lệ.
- Với JDBC, xác nhận cleanup xóa cả dòng session và các thuộc tính liên quan sau khi job chạy.
- Với Redis indexed, phân biệt thời điểm hết hạn logic với thời điểm hash vật lý được dọn.
- Với Map, xác nhận cơ chế purge do ứng dụng hoặc Map cung cấp thực sự hoạt động.

**Kiểm tra sự kiện**

- Chỉ kỳ vọng các event tích hợp khi dùng repository hỗ trợ event.
- Với Redis indexed, xác nhận keyspace notification, listener và cấu hình quyền Redis hoạt động trong môi trường triển khai.
- Mô phỏng listener mất kết nối; bảo đảm nghiệp vụ không phụ thuộc duy nhất vào một event có thể bị bỏ lỡ.
- Kiểm tra listener xử lý lặp lại an toàn.

**Kiểm tra chỉ mục**

- Đăng nhập một principal trên nhiều client và xác nhận truy vấn trả đúng các session.
- Xóa một session và xác nhận truy vấn principal không còn trả ID đó.
- Thử session không có principal name để xác nhận hành vi phù hợp.
- Với chỉ mục tùy chỉnh của Redis, kiểm tra cả cập nhật chỉ mục khi thuộc tính đổi và cleanup khi session bị xóa/hết hạn.

**Kiểm tra chính sách lưu và đồng thời**

- Kiểm tra thuộc tính được thay đổi bằng `setAttribute` được lưu theo `SaveMode` đã chọn.
- Nếu code sửa object tại chỗ, xác nhận cách lưu phù hợp hoặc chuyển sang đặt lại thuộc tính.
- Gửi hai request đồng thời cùng sửa session để quan sát nguy cơ ghi đè.
- Với JDBC, xác nhận transaction và `FlushMode` theo cấu hình.
- Với Redis, xác nhận serializer đọc được dữ liệu do instance khác ghi.

Nên theo dõi thời gian đọc/ghi repository, lỗi kết nối Redis/JDBC, lỗi serialize/deserialize, số session hết hạn nhưng chưa cleanup, số lượng session theo principal khi có chỉ mục, lỗi subscription Redis và kích thước dữ liệu session. Không ghi cookie hoặc session ID nguyên vẹn vào log; sử dụng mã tương quan đã được kiểm soát.

## 10. Những điểm cần xác nhận trước khi đưa vào production

Trước khi triển khai, hãy trả lời các câu hỏi sau:

1. Repository đang chạy là loại nào? Kiểm tra bean hoặc cấu hình auto-configuration thực tế, không suy đoán chỉ từ dependency.
2. Timeout nào đang có hiệu lực? Kiểm tra cấu hình session, thời hạn theo từng session và cookie của trình duyệt.
3. Dữ liệu hết hạn được dọn bởi TTL, job định kỳ hay Map bên ngoài? Ai chịu trách nhiệm nếu job ngừng chạy?
4. Có cần tra cứu session theo principal hoặc tiêu chí khác không? Chỉ mục nào đã được tạo và được dọn như thế nào?
5. Có cần sự kiện vòng đời không? Repository có phát sự kiện không, Redis notification đã bật chưa, và listener có xử lý lặp lại an toàn không?
6. `FlushMode` và `SaveMode` có phù hợp với kiểu cập nhật thuộc tính và mức đồng thời của ứng dụng không?
7. Serializer và schema có tương thích giữa các instance trong giai đoạn rolling deployment không?
8. Redis hoặc cơ sở dữ liệu đã có chính sách persistence, backup, replication và khôi phục phù hợp chưa?

Một luồng quản lý session theo principal có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Request quản trị session] --> B[FindByIndexNameSessionRepository]
    B --> C[Tra cứu theo principal name]
    C --> D{Repository có hỗ trợ chỉ mục?}
    D -->|Không| E[Không thể dùng API tra cứu principal]
    D -->|Có| F[Nhận danh sách session ID]
    F --> G[Kiểm tra quyền và chọn session]
    G --> H[deleteById]
    H --> I{Repository hỗ trợ event?}
    I -->|Có: Redis indexed| J[Phát sự kiện xóa]
    I -->|Không: JDBC indexed| K[Session được xóa qua repository]
~~~

Ma trận khả năng giúp chọn đúng repository và xác định phần vận hành phải cấu hình thêm. Với Spring Session, TTL, sự kiện, chỉ mục và chính sách ghi là các đặc tính liên quan nhưng độc lập; cần kiểm tra từng đặc tính theo implementation đang chạy thay vì suy ra từ tên API chung.

## Tài liệu tham khảo

- [Spring Session API](https://docs.spring.io/spring-session/reference/api.html)
- [Spring Session Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Session JDBC Configuration](https://docs.spring.io/spring-session/reference/configuration/jdbc.html)
- [RedisIndexedSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/data/redis/RedisIndexedSessionRepository.html)
- [JdbcIndexedSessionRepository Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/jdbc/JdbcIndexedSessionRepository.html)
- [FlushMode Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FlushMode.html)
- [SaveMode Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/SaveMode.html)

