# Phiên rất lớn, ghi thường xuyên và giới hạn tài nguyên

Spring Session giúp nhiều instance chia sẻ trạng thái phiên qua Redis, JDBC hoặc một repository khác. Khi session chứa quá nhiều dữ liệu hoặc bị cập nhật trong hầu hết request, chi phí không chỉ nằm ở một lần ghi. Ứng dụng phải đọc, deserialize, thay đổi, serialize và truyền dữ liệu qua mạng hoặc database; repository còn phải duy trì TTL, index và metadata. Khi số phiên tăng, các chi phí này cộng dồn thành áp lực lên bộ nhớ, CPU, connection pool, I/O và độ trễ request.

Thiết kế tốt bắt đầu bằng việc giữ session nhỏ và lưu đúng loại trạng thái ở đúng hệ thống. Session thường chỉ cần principal/security context, một vài lựa chọn giao diện và ID tham chiếu đến dữ liệu nghiệp vụ. Giỏ hàng lớn, nội dung biểu mẫu dài, danh sách kết quả, tệp tải lên, bộ đếm tần suất cao hoặc trạng thái workflow quan trọng nên được lưu trong kho phù hợp. Bài học này giải thích cách nhận diện write amplification, chọn chế độ lưu của Spring Session, đặt giới hạn kích thước và kiểm thử tải ở quy mô thực tế.

## 1. Vì sao session lớn làm hệ thống chậm?

Một session được truy cập trong nhiều request có thể tạo chi phí ở nhiều tầng:

1. Cookie hoặc header mang session ID đến ứng dụng.
2. Repository tìm bản ghi session trong Redis/JDBC.
3. Serializer chuyển dữ liệu lưu trữ thành object trong JVM.
4. Controller/filter đọc và thay đổi attributes.
5. Repository phát hiện thay đổi và serialize dữ liệu cần lưu.
6. Redis/JDBC nhận lệnh ghi, cập nhật thời hạn và index.
7. Response có thể phát cookie hoặc cập nhật metadata session.

Khi payload tăng, các bước deserialize/serialize và truyền dữ liệu tiêu tốn CPU, heap và băng thông. Với JDBC, các cột attributes có thể chứa payload nhị phân lớn, làm tăng I/O, dung lượng bảng, backup và thời gian transaction. Với Redis, mỗi session chiếm RAM cùng overhead của key, object, index và replication.

Một session 10 KB được ghi một lần mỗi phút có chi phí rất khác một session 500 KB được ghi ở mọi request. Cần đo cả kích thước payload lẫn tần suất ghi, không chỉ đếm số session.

## 2. Session không phải nơi lưu toàn bộ trạng thái ứng dụng

Session có vòng đời gắn với client và thường được tải trong nhiều request. Nó phù hợp với dữ liệu nhỏ cần để tiếp tục trải nghiệm người dùng:

- Principal hoặc thông tin xác thực mà Spring Security quản lý.
- Locale, theme hoặc tùy chọn giao diện nhỏ.
- ID của giỏ hàng, draft hoặc workflow.
- Một cờ luồng giao diện có thời hạn ngắn.
- Một vài giá trị điều hướng cần thiết giữa các request.

Không nên lưu toàn bộ:

- Entity graph Hibernate/JPA có quan hệ lazy, proxy hoặc vòng tham chiếu.
- Danh sách sản phẩm, kết quả tìm kiếm hoặc lịch sử giao dịch không giới hạn.
- Nội dung file, ảnh, byte array lớn hoặc dữ liệu upload.
- Request/response object, InputStream, connection hoặc object phụ thuộc tài nguyên đang mở.
- Cache ứng dụng, dữ liệu tham chiếu lớn hoặc bản sao của bảng nghiệp vụ.
- Bộ đếm có tần suất cập nhật cao cần độ chính xác đồng thời.

Thay vì lưu một Order đầy đủ, lưu orderId rồi tải trạng thái mới nhất từ service nghiệp vụ. Thay vì lưu toàn bộ Cart, lưu cartId và để CartService đọc/ghi các dòng trong database. Cách này tránh serialize một object lớn trong mỗi request và giữ nguồn dữ liệu có thẩm quyền ở một nơi.

## 3. Ước lượng ngân sách kích thước session

Đặt ngân sách payload theo ứng dụng và đo trên dữ liệu đã serialize. Kích thước object trong heap không bằng kích thước bytes lưu trữ: serializer có thể thêm metadata, tên class, cấu trúc map, encoding và overhead.

Một cách ước lượng tải lưu trữ:

~~~text
Dung lượng dữ liệu session xấp xỉ
  = số session còn hiệu lực
    x kích thước trung bình đã serialize
    + overhead key/index/metadata
    + replication và dự phòng vận hành
~~~

Ví dụ minh họa: 200.000 session với payload trung bình 20 KB đã tương đương khoảng 4 GB dữ liệu payload trước khi tính overhead, index, fragmentation, replication và bản sao backup. Nếu payload tăng lên 200 KB, phần payload riêng đã thành khoảng 40 GB.

Đây chỉ là phép ước lượng ban đầu. Dung lượng thực tế phải đo trên Redis/JDBC cùng serializer và schema đang dùng. Cần theo dõi phân phối kích thước như p50, p95, p99 và giá trị lớn nhất; một số ít session cực lớn có thể gây vấn đề dù trung bình thấp.

### 3.1. Đặt ngưỡng ở tầng ứng dụng

Spring Session không thay thế chính sách kích thước của ứng dụng. Hãy xác định:

- Tổng payload session tối đa được phép.
- Kích thước tối đa cho từng loại attribute.
- Số phần tử tối đa trong collection.
- Độ dài tối đa của chuỗi do người dùng nhập.
- Số lần cập nhật session tối đa trong một luồng nghiệp vụ nếu cần.

Kiểm tra dữ liệu trước khi đặt vào session. Nếu vượt ngưỡng, lưu dữ liệu ở store nghiệp vụ và chỉ giữ ID tham chiếu. Không đợi tới lúc serializer hoặc database báo lỗi mới phát hiện session quá lớn.

Không ghi nội dung attribute hoặc session ID vào log khi báo lỗi vượt ngưỡng. Có thể log tên loại attribute đã chuẩn hóa, kích thước bytes, route và correlation ID.

## 4. Đo payload đã serialize

Kích thước cần quan tâm là dữ liệu mà repository thực sự lưu. Với Redis, có thể quan sát kích thước key/value bằng công cụ chẩn đoán phù hợp và giới hạn phạm vi đo. Với JDBC, đo kích thước payload attributes và thống kê dung lượng bảng/index từ database.

Không chạy truy vấn tải toàn bộ attributes trên production chỉ để đo kích thước. Dùng:

- Thống kê tổng hợp theo batch.
- Sampling có giới hạn.
- Database catalog hoặc thống kê dung lượng bảng.
- Redis MEMORY USAGE trên mẫu key được chọn an toàn, không quét mọi key theo request.
- Metric từ lớp serialization nếu ứng dụng có thể đo bytes trước khi ghi.

Nếu cần thêm instrumentation quanh serializer, tránh serialize object lần thứ hai chỉ để đo vì chính thao tác đo cũng tiêu tốn CPU và bộ nhớ. Có thể đếm bytes trong một wrapper serializer nếu cách đó tương thích với cấu hình và không làm thay đổi định dạng dữ liệu.

## 5. Write amplification khi request thường xuyên sửa session

Write amplification là lượng thao tác ghi phát sinh lớn hơn mức thay đổi nghiệp vụ thực tế. Một request có thể:

- Cập nhật last accessed time.
- Đặt lại một attribute dù giá trị không đổi.
- Serialize lại nhiều attribute không liên quan.
- Cập nhật expiration hoặc TTL.
- Cập nhật principal/expiration index.
- Ghi lại session nhiều lần trong cùng request tùy flush mode và integration.

Nếu một trang polling mỗi vài giây và mỗi lần lại đặt một attribute giống giá trị cũ, ứng dụng có thể tạo ra hàng nghìn lần ghi không mang thêm giá trị nghiệp vụ.

Các cách giảm ghi:

- Chỉ gọi setAttribute khi giá trị thực sự thay đổi.
- Không lưu dữ liệu có thể tính lại từ database hoặc cache.
- Gộp nhiều thay đổi trong một request.
- Không cập nhật session trong endpoint chỉ đọc nếu không cần.
- Chuyển bộ đếm và trạng thái thay đổi liên tục sang store chuyên dụng.
- Chọn save/flush mode theo semantics của repository và phiên bản.

Không giả định một request chỉ đọc hoàn toàn miễn phí. Repository có thể cập nhật last access time hoặc metadata hết hạn khi session được sử dụng. Hãy đo hành vi của repository thực tế.

## 6. FlushMode: ghi ngay hay ghi khi save?

Spring Session Redis cung cấp FlushMode để điều khiển thời điểm các thay đổi được đẩy xuống Redis:

| Chế độ | Hành vi | Đánh đổi |
|---|---|---|
| ON_SAVE | Gộp các thay đổi và flush khi repository save session | Giảm số lần round-trip trong request; dữ liệu thay đổi có thể chưa được ghi cho đến điểm save |
| IMMEDIATE | Đẩy thay đổi xuống store ngay khi thao tác session xảy ra | Thay đổi được gửi sớm hơn nhưng có thể tăng số lệnh, network round-trip và write load |

Với ứng dụng Servlet thông thường, ON_SAVE thường là lựa chọn phù hợp để gom các thay đổi trong request rồi lưu khi request hoàn tất. IMMEDIATE có thể cần trong một số luồng mà thay đổi phải được nhìn thấy trước khi request kết thúc, nhưng cần đánh giá số lần ghi và hành vi lỗi.

Ví dụ cấu hình Redis Servlet:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.FlushMode;
import org.springframework.session.SaveMode;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(
    maxInactiveIntervalInSeconds = 1800,
    flushMode = FlushMode.ON_SAVE,
    saveMode = SaveMode.ON_SET_ATTRIBUTE
)
public class SessionConfiguration {
}
~~~

Đây là ví dụ cho Spring Session Redis Servlet. Nếu dùng Spring Boot auto-configuration, cấu hình bằng các thuộc tính spring.session.redis tương ứng theo phiên bản Boot. Với WebFlux, dùng cấu hình reactive tương ứng. Không áp dụng cấu hình Servlet trực tiếp cho WebSession.

FlushMode không biến nhiều thao tác trên nhiều hệ thống thành một transaction phân tán. Nếu request ghi Redis rồi ghi database nghiệp vụ, ON_SAVE không đảm bảo hai store cùng commit hoặc rollback.

## 7. SaveMode: chọn attribute nào cần lưu?

SaveMode quyết định repository theo dõi hoặc persist attributes theo cách nào. Các chế độ thường gặp:

| Chế độ | Ý nghĩa | Khi cân nhắc |
|---|---|---|
| ON_SET_ATTRIBUTE | Lưu attribute được đặt hoặc xóa qua API session | Tốt khi ứng dụng thay thế attribute rõ ràng |
| ON_GET_ATTRIBUTE | Đánh dấu attribute được đọc là cần lưu | Có ích với object mutable bị thay đổi sau khi đọc, nhưng có thể tăng ghi |
| ALWAYS | Lưu mọi attribute khi save session | Dễ bảo đảm các thay đổi in-place được lưu, nhưng tăng serialization và write load |

ON_SET_ATTRIBUTE thường phù hợp khi ứng dụng tuân thủ mẫu thay thế attribute sau khi sửa. ALWAYS có thể làm payload lớn bị serialize lại ở mọi request. ON_GET_ATTRIBUTE chỉ nên bật sau khi hiểu chính xác cách code đọc và sửa attribute, vì mọi attribute được truy cập có thể bị đánh dấu cần persist.

Các chế độ và default có thể khác theo repository hoặc phiên bản Spring Session. Kiểm tra Javadoc và cấu hình của module đang dùng; không suy ra rằng mọi repository đều hỗ trợ mọi tổ hợp FlushMode/SaveMode giống Redis.

### 7.1. Cạm bẫy với object mutable

Giả sử session có một danh sách:

~~~java
List<String> recentItems =
    (List<String>) session.getAttribute("recentItems");

recentItems.add(itemId);
~~~

Nếu repository dùng ON_SET_ATTRIBUTE, thao tác add() thay đổi object trong memory nhưng không gọi session.setAttribute(). Repository có thể không nhận ra attribute đã thay đổi và không lưu danh sách mới.

Mẫu rõ ràng hơn:

~~~java
List<String> updated = new ArrayList<>(recentItems);
updated.add(itemId);
session.setAttribute("recentItems", updated);
~~~

Việc thay object giúp repository nhận biết attribute được đặt lại. Một lựa chọn khác là dùng object immutable và luôn tạo phiên bản mới khi cập nhật. Không nên chuyển sang ALWAYS chỉ để che một lỗi mutation nếu có thể sửa cách cập nhật dữ liệu.

Nếu bắt buộc sửa object tại chỗ, kiểm thử với SaveMode đã cấu hình và xác nhận dữ liệu còn đúng sau request tiếp theo, node khác hoặc restart.

## 8. Gộp thay đổi và tránh ghi không cần thiết

Trong một request, gom các cập nhật session thành một nhóm:

~~~java
session.setAttribute("locale", locale);
session.setAttribute("cartId", cartId);
session.setAttribute("lastWorkflowId", workflowId);
~~~

Chỉ thực hiện set khi giá trị thay đổi:

~~~java
Object previous = session.getAttribute("locale");
if (!locale.equals(previous)) {
    session.setAttribute("locale", locale);
}
~~~

Không đặt lại toàn bộ attributes từ một object snapshot cũ sau mỗi request. Cách này có thể tạo nhiều ghi và ghi đè thay đổi của request đồng thời.

Nếu nhiều request cùng sửa session, giảm write amplification không đồng nghĩa giải quyết race condition. Dữ liệu cần nhất quán vẫn phải dùng version, atomic operation hoặc transaction ở store phù hợp. Không dùng session làm bộ đếm dùng chung khi nhiều request có thể cập nhật đồng thời.

## 9. Redis: RAM, TTL và chính sách eviction

Redis lưu session trong bộ nhớ, vì vậy dung lượng session tác động trực tiếp đến RAM. Tổng chi phí gồm payload, key, hash/list/set index, allocator overhead, replication buffer và các dữ liệu khác trong cùng instance.

Các nguyên tắc:

- Tách session store khỏi cache không quan trọng nếu chính sách eviction khác nhau.
- Dành đủ headroom cho tăng trưởng, replication, failover và memory fragmentation.
- Theo dõi used_memory, used_memory_rss, fragmentation ratio, key count và tốc độ tăng dữ liệu.
- Đặt cảnh báo trước khi chạm ngưỡng maxmemory.
- Xem xét chính sách eviction có thể xóa session còn hiệu lực như một sự cố đăng xuất hàng loạt.

Nếu session là trạng thái xác thực quan trọng, không nên dùng chính sách eviction tổng quát có thể âm thầm loại bỏ key session đang còn TTL. Một cấu hình noeviction tránh Redis tự chọn key để xóa, nhưng khi hết bộ nhớ lệnh ghi sẽ lỗi; ứng dụng phải có cảnh báo, dung lượng dự phòng và xử lý lỗi phù hợp. Chọn chính sách theo kiến trúc, không sao chép một giá trị maxmemory-policy mà không đánh giá.

TTL giúp Redis tự hết hạn dữ liệu session, nhưng không thay thế việc quản lý expiration index và cleanup của repository. Khi session được truy cập, repository có thể gia hạn expiration theo max inactive interval. Cần đo số lần cập nhật TTL và tránh lưu session không có timeout nếu nghiệp vụ không cần.

## 10. JDBC: payload, transaction và connection pool

Với JDBC, session metadata thường nằm trong SPRING_SESSION và attributes được lưu trong SPRING_SESSION_ATTRIBUTES. Attribute bytes lớn làm tăng:

- Kích thước row hoặc payload LOB/BLOB.
- I/O khi đọc và ghi.
- Thời gian serialize/deserialize.
- Thời gian transaction và khả năng giữ lock.
- Dung lượng index, backup và replication log.

Ghi thường xuyên có thể làm tăng số UPDATE, INSERT/DELETE attributes và cạnh tranh connection pool. Hãy theo dõi:

- Query latency p50/p95/p99 của repository.
- Connection pool active, idle, pending và timeout.
- Lock wait, deadlock và transaction duration.
- Số row session/attribute và tốc độ tăng trưởng.
- Cleanup job duration và số row đã xóa.

Đảm bảo index theo session ID, principal và expiration phù hợp schema/version. Không tự xóa bảng hoặc đổi index khi chưa kiểm tra query plan của repository. Với session lớn, tối ưu truy vấn không thể bù được việc serialize payload quá nhiều; giảm payload thường đem lại hiệu quả lớn hơn.

## 11. TTL và giới hạn thời gian sống

Spring Session thường dùng max inactive interval để xác định khoảng thời gian không hoạt động trước khi session hết hạn. Khi session được truy cập, last access time và expiration có thể được cập nhật tùy repository.

Chọn timeout theo rủi ro và trải nghiệm:

- Vùng quản trị hoặc dữ liệu nhạy cảm có thể cần idle timeout ngắn hơn.
- Workflow dài có thể cần lưu trạng thái nghiệp vụ ngoài session và cho phép khôi phục an toàn.
- Không dùng session không hết hạn chỉ để tránh người dùng phải đăng nhập lại.
- Nếu có absolute session lifetime, triển khai giới hạn tuyệt đối riêng; idle timeout đơn thuần có thể được gia hạn mỗi request.

Ví dụ cấu hình 30 phút trong annotation Redis ở trên. Với JDBC, dùng cấu hình EnableJdbcHttpSession và tham số maxInactiveIntervalInSeconds phù hợp. Với WebFlux, dùng EnableRedisWebSession hoặc cấu hình reactive repository tương ứng.

TTL cũng là một giới hạn tài nguyên: session không hoạt động lâu hơn cần thiết sẽ tiếp tục chiếm RAM/database và index. Nhưng timeout quá ngắn có thể làm người dùng mất công việc đang thực hiện. Đo hành vi thực tế và chọn timeout theo loại ứng dụng.

## 12. Giới hạn số session theo principal

Một tài khoản có thể tạo nhiều session từ nhiều thiết bị hoặc trình duyệt. Nếu không có chính sách, một tài khoản bị lộ có thể tạo ra số lượng session lớn và tiêu thụ tài nguyên.

Spring Security hỗ trợ giới hạn session đồng thời bằng maximumSessions và SessionRegistry. Khi dùng Spring Session trên nhiều node, sử dụng SpringSessionBackedSessionRegistry dựa trên repository có principal index để chia sẻ thông tin session giữa các node.

Ví dụ:

~~~java
http.sessionManagement(session -> session
    .maximumSessions(5)
    .sessionRegistry(sessionRegistry)
);
~~~

Giới hạn này kiểm soát số session theo principal; nó không giới hạn kích thước từng session hoặc số bytes attributes. Cần kết hợp quota kích thước ở tầng ứng dụng.

## 13. Không dùng session cho rate limit hoặc counter nóng

Một counter được tăng ở mỗi request là ví dụ không phù hợp để đặt trong session:

1. Hai request song song đọc cùng giá trị.
2. Cả hai cùng tăng và lưu.
3. Một cập nhật có thể ghi đè cập nhật còn lại.
4. Session lớn hoặc save thường xuyên làm tăng tải store.

Rate limit, số lượt tiêu thụ, quota và counter nên dùng Redis atomic commands, Lua script, database conditional update hoặc hệ thống chuyên dụng. Session có thể giữ tham chiếu đến bucket hoặc trạng thái giao diện, nhưng không phải nguồn có thẩm quyền của bộ đếm.

## 14. Serialization và cấu trúc object

Serialization là một phần quan trọng của chi phí session. Để giảm tải:

- Dùng DTO nhỏ, không lưu entity graph.
- Tránh object có vòng tham chiếu hoặc quan hệ lồng sâu.
- Không giữ proxy lazy của ORM trong session.
- Tránh class có nhiều trường không cần thiết.
- Giữ schema/version serialization tương thích giữa các node trong rolling deployment.
- Chỉ bật compression khi đo được lợi ích CPU/băng thông và kiểm thử độ trễ.

Compression có thể giảm bytes lưu trữ nhưng tiêu tốn CPU và không loại bỏ chi phí object graph lớn. Không nén một payload quá lớn rồi xem đó là giải pháp cho thiết kế session sai.

Khi thay đổi class hoặc serializer, kiểm thử session cũ được đọc bởi phiên bản mới và ngược lại trong giai đoạn rolling deployment. Nếu node cũ không deserialize được payload mới, người dùng có thể bị logout hoặc request lỗi.

## 15. Giới hạn tài nguyên theo nhiều lớp

Không có một ngưỡng duy nhất bảo vệ toàn hệ thống. Cần phối hợp:

| Tầng | Giới hạn hoặc kiểm soát | Mục tiêu |
|---|---|---|
| API/application | Kích thước input, số phần tử, payload session | Ngăn dữ liệu lớn đi vào session |
| Session policy | Idle timeout, absolute lifetime, số phiên/principal | Giảm số session và thời gian lưu |
| JVM | Heap, allocation rate, GC pause, thread pool | Tránh deserialize lớn làm cạn heap |
| Redis | maxmemory, headroom, key count, eviction policy | Bảo vệ RAM và session còn hiệu lực |
| JDBC | Pool size, query timeout, index, transaction | Giữ database ổn định |
| Network | Connection pool, bandwidth, timeout | Tránh serialize payload lớn làm nghẽn |
| Observability | Sampling, metric cardinality, log retention | Tránh công cụ giám sát tự tạo tải |

Giới hạn phải có phản hồi rõ ràng. Nếu payload vượt ngưỡng, từ chối hoặc chuyển sang lưu trữ ngoài session; không cắt bytes tùy tiện vì có thể làm hỏng serialization.

## 16. Giám sát hiệu năng session

Các metric hữu ích:

- Số session hiện có và tốc độ tạo/xóa.
- Kích thước payload session p50/p95/p99 và max.
- Số lần save/flush mỗi request.
- Tỷ lệ request có thay đổi session.
- Thời gian serialize/deserialize.
- Redis command latency, memory, key count và error rate.
- JDBC query latency, pool saturation, lock wait và deadlock.
- Expiration backlog và cleanup duration.
- Số lỗi serialization/deserialization.

Không dùng session ID, username, email hoặc principal làm metric label. Các giá trị này tạo cardinality cao và có thể tiết lộ thông tin. Dùng nhãn ít biến thiên như repository type, operation, environment, application version và error class.

Dashboard nên phân biệt:

- Session count: số lượng phiên.
- Payload size: kích thước dữ liệu phiên.
- Write rate: số lần ghi.
- Active request: số request đang xử lý.
- Store pressure: RAM, connection pool và I/O.

Một số lượng session ổn định vẫn có thể gây tải cao nếu mỗi request serialize và ghi payload lớn. Ngược lại, nhiều session nhỏ, ít thay đổi có thể vận hành tốt hơn.

## 17. Kiểm thử tải và kiểm thử giới hạn

Test hiệu năng nên dùng dữ liệu có phân phối gần production:

| Kịch bản | Cần đo | Mục tiêu |
|---|---|---|
| Session nhỏ, ít thay đổi | Request latency, read/write rate | Baseline |
| Session lớn p95 | Serialize time, heap, bandwidth | Tìm ngưỡng payload |
| Session cực lớn | Error rate, GC, timeout | Xác minh giới hạn và phản hồi |
| Mỗi request sửa attribute | Writes/request, store latency | Đo write amplification |
| ON_SAVE so với IMMEDIATE | Command count và p95 latency | Chọn flush mode |
| ON_SET_ATTRIBUTE so với ALWAYS | Bytes ghi và độ đúng dữ liệu | Chọn save mode |
| Nhiều session đồng thời | Redis RAM hoặc JDBC pool | Kiểm tra capacity |
| Expiration burst | Cleanup time và database/Redis load | Kiểm tra dọn dữ liệu |
| Redis/JDBC gần ngưỡng | Lỗi ghi, timeout và recovery | Kiểm tra graceful failure |
| Rolling deployment | Serialization compatibility | Đảm bảo node đọc được session cũ/mới |

Chạy test qua nhiều node nếu production có nhiều instance. Không chỉ benchmark serializer trong unit test rồi suy ra hiệu năng hệ thống; cần đo toàn bộ request path và repository.

### 17.1. Kiểm thử save mode với mutable object

Tạo session có attribute là collection, đọc và sửa collection tại chỗ, rồi gửi request tiếp theo để kiểm tra giá trị đã lưu. Chạy cùng test với ON_SET_ATTRIBUTE, ON_GET_ATTRIBUTE và ALWAYS nếu repository hỗ trợ.

Test cũng nên có trường hợp thay object bằng collection mới qua setAttribute. So sánh dữ liệu đúng và số bytes ghi. Kết quả giúp chọn chế độ lưu dựa trên hành vi code thật, không dựa trên giả định.

## 18. Xử lý khi store chạm giới hạn hoặc không khả dụng

Khi Redis hết memory với noeviction, lệnh ghi có thể lỗi. Khi JDBC pool cạn, request có thể chờ hoặc timeout. Ứng dụng cần:

- Đặt timeout cho thao tác store.
- Giới hạn số request đồng thời có thể tạo session mới.
- Trả lỗi phù hợp, không giả vờ session đã được lưu thành công.
- Không cấp quyền mặc định khi không đọc được session xác thực.
- Phát cảnh báo sớm theo ngưỡng RAM/pool/latency.
- Có kế hoạch tăng capacity hoặc giảm payload.
- Không retry vô hạn khiến store càng quá tải.

Nếu lưu session thất bại, request tiếp theo có thể không khôi phục được thay đổi vừa thực hiện. Đối với thao tác nghiệp vụ quan trọng, commit dữ liệu nghiệp vụ ở store có thẩm quyền và không phụ thuộc vào việc một attribute session được lưu thành công.

## 19. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Redis tăng RAM nhanh | Session payload lớn, TTL dài hoặc nhiều index | Giảm payload, đặt timeout, theo dõi overhead |
| JDBC chậm khi tải tăng | Ghi attributes thường xuyên, transaction dài, pool cạn | Giảm write rate, tối ưu index/query và pool |
| Attribute mutable không được lưu | SaveMode chỉ nhận diện set/remove, code chỉ sửa object tại chỗ | Đặt lại attribute hoặc chọn mode phù hợp |
| Nhiều lệnh Redis trong một request | FlushMode.IMMEDIATE hoặc nhiều mutation | Gom thay đổi và đánh giá ON_SAVE |
| Payload ghi lại dù không đổi | Gọi setAttribute không cần thiết hoặc SaveMode.ALWAYS | Chỉ set khi giá trị thay đổi |
| GC pause tăng | Deserialize object graph lớn, allocation nhiều | Giảm kích thước và độ sâu object |
| Session bị mất ngẫu nhiên | Redis eviction xóa key còn hạn hoặc cleanup sai | Đánh giá eviction policy và repository cleanup |
| Cookie hợp lệ nhưng request lỗi | Serialization incompatibility giữa node | Đồng bộ serializer và rolling compatibility |
| Request polling tạo tải store | Mỗi request cập nhật session/last access | Tách endpoint chỉ đọc và giảm mutation không cần |
| Session hết hạn quá sớm | Idle timeout không phù hợp | Điều chỉnh timeout theo nghiệp vụ và kiểm thử |

## 20. Quy trình tối ưu

1. Đo kích thước payload đã serialize và tần suất ghi theo route.
2. Xác định attribute lớn, mutable hoặc được đặt lại không cần thiết.
3. Chuyển dữ liệu nghiệp vụ lớn sang database/object store; giữ ID trong session.
4. Đặt ngân sách kích thước và timeout session.
5. Chọn SaveMode để theo dõi đúng thay đổi mà không ghi mọi attribute vô ích.
6. Chọn FlushMode theo nhu cầu hiển thị thay đổi và chi phí round-trip.
7. Kiểm tra Redis memory/eviction hoặc JDBC pool/query/lock.
8. Giới hạn số session theo principal nếu phù hợp.
9. Chạy load test với payload và concurrency gần production.
10. Theo dõi latency, write amplification, payload distribution và store pressure sau triển khai.

## 21. Nguyên tắc triển khai

- Giữ session nhỏ; lưu ID tham chiếu thay cho object nghiệp vụ lớn.
- Đo bytes đã serialize, không chỉ kích thước object trong heap.
- Đặt giới hạn tổng payload, từng attribute và collection ở tầng ứng dụng.
- Chỉ cập nhật attribute khi giá trị thay đổi.
- Với Redis, hiểu rõ ON_SAVE và IMMEDIATE trước khi chọn FlushMode.
- Chọn SaveMode phù hợp; kiểm tra mutable object khi dùng ON_SET_ATTRIBUTE.
- Không dùng ALWAYS như cách che mọi lỗi dirty tracking mà chưa đo write cost.
- Dùng store nghiệp vụ hoặc atomic primitive cho counter, quota và dữ liệu thay đổi thường xuyên.
- Đặt idle timeout và absolute lifetime theo chính sách.
- Theo dõi RAM/eviction Redis hoặc connection pool/query latency JDBC.
- Không ghi session ID hoặc payload nhạy cảm vào metric/log.
- Kiểm thử payload lớn, nhiều session, request song song, expiration và store failure.

Session rất lớn và ghi thường xuyên làm tăng chi phí serialization, mạng, bộ nhớ và I/O ở mọi node. Giữ dữ liệu session nhỏ, chọn SaveMode/FlushMode theo hành vi thực tế, đặt quota và chuyển trạng thái nghiệp vụ sang store phù hợp giúp Spring Session hoạt động ổn định khi số lượng phiên và lưu lượng tăng. Hiệu năng cần được xác minh bằng payload, concurrency và backend gần production, không chỉ bằng một test request đơn lẻ.
