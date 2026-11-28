# Phối hợp qua thao tác nguyên tử hoặc lưu trạng thái tại hệ thống phù hợp

Spring Session giúp nhiều instance dùng chung trạng thái phiên, nhưng việc đặt dữ liệu vào session không tự làm cho mọi thao tác đồng thời trở nên an toàn. Một trình duyệt có thể gửi nhiều request song song với cùng cookie; load balancer có thể chuyển chúng đến các node khác nhau. Nếu hai request cùng đọc một giá trị rồi cập nhật và lưu lại, lần ghi sau có thể ghi đè thay đổi của lần ghi trước.

Để giữ dữ liệu nhất quán, cần chọn đúng nơi lưu và đúng cơ chế phối hợp. Session phù hợp để giữ định danh người dùng, trạng thái giao diện nhỏ hoặc tham chiếu đến quy trình. Dữ liệu nghiệp vụ cần tính đúng đắn như số dư, tồn kho, lượt sử dụng, trạng thái đơn hàng hoặc quyền được tiêu thụ một lần nên được quản lý trong kho dữ liệu có primitive nguyên tử, transaction, constraint hoặc cơ chế versioning phù hợp.

Bài học này tập trung vào cách nhận diện race condition trong ứng dụng dùng Spring Session, sử dụng thao tác nguyên tử ở Redis/JDBC, thiết kế idempotency, khóa và version, cũng như cách kiểm thử khi nhiều request hoặc nhiều instance cùng thay đổi trạng thái.

## 1. Vì sao dùng chung session chưa đủ để bảo đảm nhất quán?

Spring Session đưa dữ liệu phiên ra khỏi bộ nhớ của một máy chủ. Nhờ đó, node A có thể ghi session và node B có thể đọc session đó. Kho dùng chung giải quyết khả năng truy cập dữ liệu giữa các node; nó không tự quyết định hai thao tác ghi cạnh tranh phải được hợp nhất như thế nào.

Giả sử session chứa số lượng sản phẩm đang chọn:

1. Request A đọc giá trị 2 từ session.
2. Request B gần như đồng thời cũng đọc giá trị 2.
3. A tăng lên 3 và lưu session.
4. B tăng lên 3 từ bản sao cũ và lưu sau A.
5. Kết quả cuối cùng là 3 thay vì 4.

Đây là lost update. Cả hai node đều đọc và ghi thành công, nhưng một cập nhật đã bị mất.

~~~mermaid
sequenceDiagram
    participant A as Request A / Node A
    participant S as Kho session dùng chung
    participant B as Request B / Node B
    A->>S: Đọc quantity = 2
    B->>S: Đọc quantity = 2
    A->>A: Tính 2 + 1 = 3
    B->>B: Tính 2 + 1 = 3
    A->>S: Ghi quantity = 3
    B->>S: Ghi quantity = 3
    Note over S: Kết quả 3; một lần tăng bị mất
~~~

Session repository có thể hỗ trợ đọc/ghi session trên nhiều node, nhưng không nên giả định một chuỗi read-modify-write trên object session là giao dịch nguyên tử. Hành vi lưu, flush, cập nhật thuộc tính và xử lý xung đột còn phụ thuộc repository và phiên bản. Nếu hai request cùng sửa một session, ứng dụng phải thiết kế chính sách nhất quán phù hợp.

## 2. Phân loại dữ liệu trước khi chọn cơ chế phối hợp

Không phải mọi dữ liệu đều cần cùng mức nhất quán. Hãy xác định nguồn dữ liệu có thẩm quyền và hậu quả nếu một cập nhật bị lặp, mất hoặc đến sai thứ tự.

| Loại dữ liệu | Ví dụ | Nơi lưu phù hợp |
|---|---|---|
| Trạng thái giao diện tạm thời | Tab đang mở, bộ lọc, locale | Session hoặc client |
| Tham chiếu quy trình | cartId, draftId, workflowId | Session giữ ID; trạng thái chính trong store nghiệp vụ |
| Dữ liệu nghiệp vụ có giá trị | Số dư, tồn kho, hạn mức, đơn hàng | Database nghiệp vụ có transaction/constraint |
| Bộ đếm hoặc tập hợp đơn giản | Số lượt, tập ID đã xử lý | Redis atomic operation hoặc database |
| Chống xử lý lặp | Idempotency key của yêu cầu thanh toán | Database có unique constraint hoặc store atomic |
| Trạng thái xác thực | SecurityContext, principal | Spring Security/Spring Session theo cấu hình |
| Quyền cần thu hồi tức thời | Phiên bị thu hồi, version bảo mật tài khoản | Store có cơ chế tra cứu và cập nhật nhất quán |

Một quy tắc hữu ích: session nên giữ dữ liệu nhỏ cần cho trải nghiệm request tiếp theo; nguồn dữ liệu có thẩm quyền của nghiệp vụ nên nằm trong hệ thống được thiết kế để bảo đảm invariant nghiệp vụ.

Ví dụ, thay vì giữ toàn bộ đối tượng Order trong session, chỉ lưu orderId. Khi người dùng xác nhận, service tải Order từ database, kiểm tra trạng thái hiện tại và thực hiện chuyển trạng thái trong transaction. Cách này tránh hai session hoặc hai node làm việc trên hai bản sao cũ của cùng một đơn hàng.

## 3. Xác định invariant và điểm nguyên tử

Trước khi chọn Redis, JDBC hay distributed lock, hãy viết ra điều kiện luôn phải đúng.

Ví dụ:

- Tồn kho không được âm.
- Một mã thanh toán chỉ được áp dụng một lần.
- Một đơn hàng chỉ chuyển từ PENDING sang CONFIRMED một lần.
- Một mã giảm giá có giới hạn tổng lượt sử dụng.
- Một session bị thu hồi không được dùng để thực hiện thao tác được bảo vệ.

Sau đó xác định thao tác nào phải xảy ra như một đơn vị không thể bị xen giữa. Điểm đó thường là một câu SQL có điều kiện, một lệnh Redis nguyên tử, một transaction hoặc một API duy nhất sở hữu trạng thái.

Không đặt invariant chỉ trong Java code kiểu:

~~~java
if (inventory.getAvailable() > 0) {
    inventory.setAvailable(inventory.getAvailable() - 1);
    repository.save(inventory);
}
~~~

Hai node có thể cùng đọc available bằng 1 và cùng đi qua điều kiện. Kiểm tra và cập nhật cần được thực hiện tại store bằng một thao tác có tính nguyên tử hoặc cơ chế khóa/version được kiểm soát.

## 4. Dùng câu lệnh SQL có điều kiện để cập nhật nguyên tử

Một cách đơn giản để trừ tồn kho là đưa điều kiện vào chính câu UPDATE:

~~~sql
UPDATE INVENTORY
SET AVAILABLE = AVAILABLE - 1,
    VERSION = VERSION + 1
WHERE PRODUCT_ID = ?
  AND AVAILABLE > 0;
~~~

Database thực hiện kiểm tra điều kiện và cập nhật trong cùng một statement. Hai request cùng tranh chấp sản phẩm cuối cùng không thể đều trừ thành công nếu database thực thi statement theo tính nhất quán của nó.

Ứng dụng kiểm tra số dòng bị ảnh hưởng:

- 1 dòng: thao tác giữ chỗ/trừ tồn kho thành công.
- 0 dòng: sản phẩm không tồn tại hoặc không còn đủ tồn kho; cần phân biệt bằng truy vấn/logic phù hợp nếu nghiệp vụ cần thông báo riêng.

Ví dụ với Spring JDBC:

~~~java
public boolean reserveOne(String productId) {
    int changed = jdbcTemplate.update("""
        UPDATE INVENTORY
        SET AVAILABLE = AVAILABLE - 1,
            VERSION = VERSION + 1
        WHERE PRODUCT_ID = ?
          AND AVAILABLE > 0
        """, productId);

    return changed == 1;
}
~~~

Đoạn mã minh họa thao tác nguyên tử ở database. Cần có primary key hoặc unique constraint trên PRODUCT_ID để mỗi sản phẩm chỉ khớp một dòng. Nếu thao tác còn phải tạo reservation/order, đặt các thay đổi liên quan trong cùng transaction JDBC khi chúng nằm trong cùng database.

### 4.1. Không tách kiểm tra và cập nhật thành hai request

Mẫu không an toàn:

1. SELECT AVAILABLE.
2. Java kiểm tra AVAILABLE lớn hơn 0.
3. UPDATE giảm AVAILABLE.

Giữa bước 1 và bước 3, request khác có thể thay đổi số lượng. Dùng UPDATE có điều kiện sẽ đưa kiểm tra và cập nhật về một statement. Nếu nghiệp vụ cần nhiều bước, dùng transaction và khóa/version thích hợp.

## 5. Transaction và khóa hàng trong JDBC

Khi nhiều bảng phải thay đổi cùng nhau, transaction giúp commit hoặc rollback nhóm thao tác trong một database.

Ví dụ: giữ tồn kho và tạo reservation phải cùng thành công hoặc cùng thất bại:

~~~java
@Service
public class ReservationService {

    private final JdbcTemplate jdbcTemplate;

    public ReservationService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void reserve(String productId, String reservationId) {
        int changed = jdbcTemplate.update("""
            UPDATE INVENTORY
            SET AVAILABLE = AVAILABLE - 1
            WHERE PRODUCT_ID = ?
              AND AVAILABLE > 0
            """, productId);

        if (changed != 1) {
            throw new IllegalStateException("Không còn tồn kho");
        }

        jdbcTemplate.update("""
            INSERT INTO RESERVATION (RESERVATION_ID, PRODUCT_ID, STATUS)
            VALUES (?, ?, 'PENDING')
            """, reservationId, productId);
    }
}
~~~

Nếu INSERT reservation thất bại, transaction có thể rollback cả UPDATE tồn kho. Cần để exception làm transaction rollback theo quy tắc Spring; nếu bắt exception rồi nuốt lỗi, transaction có thể commit thay đổi dở dang. Kiểm tra rollback rules nếu dùng checked exception hoặc tùy chỉnh transaction manager.

Một cách khác là đọc hàng bằng SELECT ... FOR UPDATE trong transaction, sau đó kiểm tra và cập nhật. Database khóa hàng được chọn cho đến khi transaction kết thúc. Cách này hữu ích khi cần đọc nhiều trường để ra quyết định, nhưng khóa lâu sẽ giảm throughput và có thể tạo deadlock nếu các transaction lấy khóa theo thứ tự khác nhau.

Chỉ dùng transaction manager cho resource mà nó quản lý. `@Transactional` với JDBC không tự làm cho một thao tác Redis trở thành một phần của cùng transaction. Nếu cùng một nghiệp vụ ghi JDBC và Redis, cần thiết kế nhất quán giữa hai hệ thống riêng.

## 6. Optimistic locking với version

Khi xung đột không thường xuyên, optimistic locking có thể giảm thời gian giữ khóa. Mỗi bản ghi có cột version. Khi cập nhật, ứng dụng chỉ ghi nếu version vẫn bằng giá trị đã đọc:

~~~sql
UPDATE ACCOUNT_STATE
SET STATUS = ?,
    VERSION = VERSION + 1
WHERE ACCOUNT_ID = ?
  AND VERSION = ?;
~~~

Nếu số dòng cập nhật bằng 0, dữ liệu đã bị một transaction khác thay đổi hoặc bản ghi không tồn tại. Ứng dụng phải tải lại và quyết định retry, trả lỗi xung đột hoặc yêu cầu người dùng làm mới.

Với JPA, có thể dùng `@Version`:

~~~java
@Entity
public class WorkflowState {

    @Id
    private String workflowId;

    @Version
    private long version;

    private String status;
}
~~~

Khi hai transaction cùng cập nhật một entity, provider dùng version để phát hiện cập nhật cạnh tranh và có thể ném OptimisticLockException. Cần xử lý lỗi ở tầng service và không tự retry vô hạn.

Optimistic locking bảo vệ bản ghi trong database; nó không tự bảo vệ một object được deserialize từ HttpSession. Nếu session giữ bản sao WorkflowState cũ, vẫn phải tải state có thẩm quyền từ database hoặc kiểm tra version trước khi ghi.

## 7. Dùng Redis atomic operations

Redis cung cấp nhiều lệnh nguyên tử hữu ích cho bộ đếm, tập hợp và khóa ngắn hạn. Ví dụ:

- `INCR`/`DECR`: tăng hoặc giảm số nguyên.
- `INCRBY`: tăng theo bước.
- `HINCRBY`: tăng trường số trong hash.
- `SADD`: thêm phần tử vào set; trả kết quả cho biết phần tử đã mới hay đã tồn tại.
- `SET key value NX PX ttl`: chỉ tạo key nếu chưa tồn tại và đặt thời hạn.

Nếu nghiệp vụ là tăng bộ đếm, không nên đọc giá trị rồi ghi giá trị mới từ Java. Dùng một lệnh atomic:

~~~java
Mono<Long> increment = redisTemplate.opsForValue()
    .increment("rate:account:42");
~~~

Với ReactiveRedisTemplate, publisher phải được compose và subscribe bởi runtime reactive. Với RedisTemplate blocking, chỉ gọi ở luồng phù hợp; không đưa blocking call vào event loop WebFlux.

### 7.1. Giới hạn của một lệnh atomic

Một lệnh Redis nguyên tử chỉ bảo vệ thao tác mà lệnh đó thực hiện. Nó không tự bảo đảm nhiều lệnh rời rạc hoặc cả quy trình liên quan đến database đều là một transaction nguyên tử.

Ví dụ:

1. INCR bộ đếm Redis thành công.
2. Ghi order vào database thất bại.
3. Bộ đếm đã tăng dù order không được tạo.

Nếu hai bước thuộc một invariant nghiệp vụ, cần xác định nguồn dữ liệu có thẩm quyền và thiết kế phục hồi, transaction/outbox hoặc workflow bù trừ. Không giả định transaction JDBC và Redis command tự commit/rollback cùng nhau.

## 8. Lua script cho thao tác nhiều bước trong Redis

Khi cần kiểm tra và cập nhật nhiều key Redis như một đơn vị, Lua script chạy nguyên tử trên Redis trong thời gian script thực thi. Ví dụ giới hạn một bộ đếm không vượt ngưỡng:

~~~lua
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])

if current >= limit then
    return 0
end

redis.call('INCR', KEYS[1])
return 1
~~~

Ứng dụng truyền key bộ đếm trong KEYS[1], ngưỡng trong ARGV[1]. Giá trị trả về 1 nghĩa là đã nhận một slot; 0 nghĩa là đã đạt giới hạn. Toàn bộ check-and-increment không bị một lệnh Redis khác xen vào giữa script.

Script trên là ví dụ tối giản. Production cần xác định TTL, cách reset theo cửa sổ thời gian, key namespace, kiểu dữ liệu, giới hạn script và cách hoàn tác khi bước nghiệp vụ sau đó thất bại. Nếu bộ đếm đại diện cho một nguồn dữ liệu có thẩm quyền khác, Redis script một mình chưa đủ để bảo đảm toàn bộ quy trình.

Không viết script đọc/ghi key nội bộ của Spring Session để thay thế repository. Dùng atomic primitive cho dữ liệu nghiệp vụ được thiết kế riêng; để Spring Session quản lý schema session của nó.

## 9. Idempotency để chống request lặp

Atomic update ngăn một số race condition, nhưng client hoặc proxy vẫn có thể gửi lại cùng yêu cầu khi timeout. Ví dụ server đã tạo đơn hàng nhưng response bị mất; client retry có thể tạo đơn hàng thứ hai.

Idempotency key là mã duy nhất do client hoặc server cấp cho một thao tác nghiệp vụ. Server lưu kết quả đã xử lý cùng key và từ chối hoặc trả lại kết quả cũ khi nhận lại key đó.

Một bảng đơn giản:

~~~sql
CREATE TABLE IDEMPOTENCY_RECORD (
    IDEMPOTENCY_KEY VARCHAR(100) PRIMARY KEY,
    REQUEST_HASH VARCHAR(128) NOT NULL,
    RESULT_ID VARCHAR(100),
    STATUS VARCHAR(20) NOT NULL,
    CREATED_AT TIMESTAMP NOT NULL
);
~~~

Unique constraint trên IDEMPOTENCY_KEY là điểm bảo vệ cuối cùng khi hai request cùng đến. Trong transaction, ứng dụng thử tạo record; nếu key đã tồn tại, đọc trạng thái/kết quả trước đó và kiểm tra request hash có giống nhau không.

Không chỉ lưu idempotency key trong HttpSession. Hai request có thể chạy trên hai node và cùng đọc session cũ. Key cần được ghi vào store dùng chung có uniqueness/atomicity để deduplicate trên toàn cụm.

### 9.1. Phân biệt retry và yêu cầu mới

Idempotency key phải đại diện cho một thao tác logic. Nếu người dùng chủ động tạo một đơn hàng mới, phải dùng key mới. Nếu client retry vì không biết kết quả lần trước, phải gửi lại cùng key.

Lưu request hash để ngăn cùng key bị tái sử dụng với payload khác. Không trả kết quả của một yêu cầu trước cho một payload mới chỉ vì key bị trùng.

## 10. Distributed lock: khi nào cần và cần thận trọng gì?

Distributed lock có thể tuần tự hóa một đoạn công việc theo resource, ví dụ chỉ cho một worker xử lý workflow ID tại một thời điểm. Tuy nhiên, lock là cơ chế phối hợp có lease và failure mode, không phải bảo đảm tuyệt đối.

Với Redis, một mẫu cơ bản là tạo lock key bằng:

~~~text
SET lock:workflow:W-100 token-unique NX PX 10000
~~~

- NX chỉ tạo key nếu key chưa tồn tại.
- PX 10000 đặt lease 10 giây.
- token-unique là giá trị ngẫu nhiên duy nhất của chủ lock.

Chỉ chủ lock mới được giải phóng lock. Không dùng lệnh DEL vô điều kiện vì lease cũ có thể hết hạn, một worker mới đã lấy lock, rồi worker cũ xóa nhầm lock của worker mới. Việc giải phóng phải so sánh token và xóa trong cùng một thao tác atomic, thường bằng Lua script.

Lock còn có vấn đề worker bị pause lâu hơn lease. Lease hết hạn, worker khác lấy lock và bắt đầu xử lý; worker cũ tỉnh lại và vẫn tiếp tục ghi. Để chống stale worker, hệ thống cần fencing token tăng đơn điệu hoặc version ở resource đích. Resource đích từ chối lệnh mang fencing token cũ.

Vì vậy:

- Đặt lease dựa trên thời gian xử lý dự kiến và có chiến lược gia hạn an toàn nếu cần.
- Dùng token duy nhất để release đúng lock.
- Thiết kế timeout và retry có giới hạn.
- Dùng fencing/version tại nơi ghi dữ liệu để ngăn worker cũ ghi sau worker mới.
- Không giữ lock trong khi chờ người dùng hoặc gọi dịch vụ bên ngoài lâu không kiểm soát.
- Không xem lock là thay thế transaction, unique constraint hoặc kiểm tra invariant tại database.

Nếu database có thể thực hiện invariant bằng UPDATE có điều kiện hoặc khóa hàng, đó thường là điểm bảo vệ trực tiếp và đơn giản hơn một distributed lock riêng.

## 11. Không dùng session làm khóa phân tán

Session ID không phải lock token và session attributes không phải cơ chế đồng bộ. Hai request cùng một session có thể chạy song song, kể cả khi sticky session gửi chúng đến cùng một node.

Các cách không an toàn:

- Đọc cờ busy trong session, rồi đặt busy=true bằng hai thao tác riêng.
- Giữ một biến Java static để ngăn hai node cùng xử lý.
- Dựa vào synchronized trên bean singleton để bảo vệ dữ liệu dùng chung giữa nhiều instance.
- Giữ lock bằng session attribute mà không có TTL, token và cơ chế phục hồi.

Các cơ chế này chỉ có phạm vi local hoặc không nguyên tử. Nếu cần điều phối, dùng store/primitive có semantics rõ ràng và kiểm tra điều kiện tại resource có thẩm quyền.

## 12. Đặt trạng thái ở hệ thống phù hợp

Session không nên trở thành database nghiệp vụ thứ hai. Một thiết kế thường gặp:

~~~text
Browser
  |
  | Cookie session ID
  v
Spring Session
  |-- principal / SecurityContext
  |-- cartId / workflowId
  |-- locale / UI preferences
  |
  v
Application service
  |
  +--> Business database
  |      order, inventory, balance, version, idempotency
  |
  +--> Redis atomic data
         rate limit, counters, short-lived coordination
~~~

Ví dụ:

- Session giữ cartId; bảng CART và CART_ITEM giữ giỏ hàng có thẩm quyền.
- Session giữ workflowId; bảng WORKFLOW_STATE giữ trạng thái và version.
- Session giữ user identity; bảng account giữ trạng thái khóa/thu hồi tài khoản.
- Redis giữ rate-limit counter; database nghiệp vụ vẫn quyết định giao dịch cuối cùng.

Nếu người dùng mở nhiều tab hoặc nhiều thiết bị, mỗi request vẫn tải trạng thái mới nhất từ service nghiệp vụ. Điều này giảm phụ thuộc vào snapshot cũ nằm trong session.

## 13. Kết hợp JDBC transaction và Redis: tránh giả định giao dịch phân tán

Một phương thức có @Transactional và gọi RedisTemplate không tự động tạo transaction nguyên tử giữa JDBC và Redis. Transaction manager JDBC quản lý connection database; Redis connection là resource khác.

Ví dụ không an toàn:

1. Tăng Redis counter.
2. Insert database record.
3. Database insert thất bại.
4. Redis counter vẫn tăng.

Các lựa chọn thiết kế:

- Để database là nguồn có thẩm quyền và cập nhật counter trong cùng transaction nếu counter thuộc cùng database.
- Dùng transactional outbox: ghi business state và event vào cùng database transaction; worker phát event để cập nhật Redis sau commit.
- Dùng saga/compensation khi quy trình nhiều hệ thống cần bước bù trừ có kiểm soát.
- Chấp nhận eventual consistency nếu nghiệp vụ cho phép và có reconciliation.

Outbox giúp không mất event giữa commit database và gửi message, nhưng consumer vẫn cần idempotent vì event có thể được giao nhiều lần. Không giả định outbox khiến hai store cùng thay đổi tại đúng một thời điểm.

## 14. Xử lý lỗi, retry và thứ tự thao tác

Khi thao tác atomic hoặc transaction thất bại, ứng dụng cần phân biệt:

- **Conflict có thể thử lại:** version không khớp; tải lại dữ liệu và quyết định retry.
- **Điều kiện nghiệp vụ không đạt:** hết tồn kho hoặc vượt hạn mức; không retry vô hạn.
- **Timeout không rõ kết quả:** client không biết server đã commit hay chưa; dùng idempotency key để tra kết quả.
- **Store tạm thời không khả dụng:** áp dụng retry có backoff, giới hạn số lần và circuit breaker nếu phù hợp.
- **Lỗi serialization/session:** không biến lỗi khôi phục session thành mặc định cấp quyền hoặc trạng thái nghiệp vụ.

Retry chỉ an toàn khi thao tác idempotent hoặc có cơ chế deduplication. Không retry mù một lệnh trừ tiền, tạo order hoặc gửi thông báo mà không có khóa idempotency.

Khi nhiều resource được khóa, thống nhất thứ tự lấy khóa để giảm deadlock. Giữ transaction ngắn; không gọi API mạng chậm trong khi đang khóa hàng database nếu có thể tách thành workflow.

## 15. Đồng thời trong cùng session và giữa các session

Có hai loại cạnh tranh cần kiểm tra:

1. **Cùng session:** hai tab hoặc request song song cùng gửi một cookie session ID và sửa các attribute khác nhau hoặc cùng một attribute.
2. **Cùng principal, nhiều session:** người dùng đăng nhập trên nhiều trình duyệt/thiết bị, mỗi session có snapshot riêng nhưng cùng thay đổi một tài nguyên nghiệp vụ.

Loại thứ hai không thể được giải quyết bằng cách khóa một session ID. Cả hai session phải đi qua cùng service/database có thẩm quyền và cùng invariant.

Ví dụ, hai session cùng đặt hàng sản phẩm cuối cùng. Database phải bảo đảm chỉ một reservation thành công. Việc session A và session B khác nhau không làm giảm nhu cầu atomic update.

Đối với thuộc tính session không quan trọng, có thể chấp nhận last-write-wins nếu nghiệp vụ cho phép. Với dữ liệu quan trọng, không dựa vào thứ tự ghi session để hợp nhất.

## 16. Bảo vệ trạng thái xác thực và thu hồi quyền

SecurityContext có thể được lưu trong session, nhưng quyền người dùng có thể thay đổi trong database sau khi session được tạo. Nếu ứng dụng chỉ tin snapshot Authentication cho đến khi session hết hạn, thay đổi quyền hoặc khóa tài khoản có thể không được phản ánh ngay.

Tùy yêu cầu, có thể:

- Dùng session expiration ngắn hơn cho vùng nhạy cảm.
- Kiểm tra trạng thái tài khoản hoặc security version từ store có thẩm quyền tại các thao tác quan trọng.
- Khi thu hồi quyền, tìm và invalidate các session của principal qua repository/index hỗ trợ.
- Dùng event để thông báo node và cache liên quan, nhưng vẫn kiểm tra nguồn có thẩm quyền khi cần bảo đảm tức thời.

Không lưu một cờ revoked trong session rồi kỳ vọng mọi node tự nhận được thay đổi. Một session khác hoặc bản sao đã được tải trước đó có thể vẫn giữ giá trị cũ. Cơ chế thu hồi phải được thiết kế trên store dùng chung và đường xác thực.

## 17. Kiểm thử tính nguyên tử và nhất quán

Unit test một request đơn lẻ không phát hiện đầy đủ race condition. Cần tạo tranh chấp có kiểm soát bằng nhiều thread, nhiều request và nhiều instance.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Hai request cùng trừ tồn kho cuối | Gửi song song tới service/database | Chỉ một request thành công |
| Hai cập nhật cùng version | Cùng đọc version rồi ghi | Một cập nhật thành công, cập nhật còn lại nhận conflict |
| Retry cùng idempotency key | Gửi lại request nhiều lần | Chỉ một thao tác nghiệp vụ được ghi nhận |
| Cùng key, payload khác | Tái sử dụng key với request hash khác | Từ chối, không trả kết quả sai |
| Hai node cùng thao tác Redis | Gọi atomic primitive từ hai instance | Kết quả thỏa invariant |
| Lock hết lease | Tạm dừng worker lâu hơn lease | Fencing/version ngăn worker cũ ghi đè |
| JDBC commit, Redis lỗi | Mô phỏng lỗi sau commit | Outbox/reconciliation đưa hệ thống về trạng thái mong đợi |
| Cùng session, hai tab | Hai request cập nhật attribute song song | Hành vi đúng theo chính sách được chọn |
| Hai session cùng principal | Hai client cùng cập nhật tài nguyên | Invariant nghiệp vụ vẫn được bảo vệ |
| Node restart giữa xử lý | Dừng node sau một bước | Retry không tạo tác dụng phụ trùng |

### 17.1. Kiểm thử bằng store thật

Với Redis, dùng Redis instance/container để kiểm tra semantics của lệnh, Lua script, TTL, failover và serialization. Với JDBC, dùng cùng loại database với production để xác minh isolation level, row lock, unique constraint và deadlock behavior.

Mock repository hữu ích cho unit test nhưng không chứng minh tính nguyên tử của Redis hoặc database. Các test concurrency cần có barrier/latch để nhiều request cùng bắt đầu, đồng thời kiểm tra invariant cuối cùng thay vì chỉ kiểm tra HTTP status.

## 18. Theo dõi xung đột và thao tác phối hợp

Các metric vận hành có ích:

- Số optimistic-lock conflict và retry.
- Số lần unique constraint từ chối duplicate.
- Tỷ lệ idempotency replay.
- Thời gian giữ row lock và số deadlock.
- Số lần acquire lock thất bại, lock timeout và lease renewal thất bại.
- Số lỗi Redis script/command và độ trễ.
- Số request có kết quả không xác định do timeout.
- Số event outbox chờ xử lý và tuổi event cũ nhất.

Không dùng session ID hoặc principal nhạy cảm làm metric label. Dùng operation name, loại store, error class và phiên bản ứng dụng; liên kết trace bằng correlation ID đã được làm sạch.

Khi có xung đột tăng đột biến, kiểm tra xem có phải một tài nguyên nóng bị nhiều request tranh chấp, transaction quá dài, retry storm hoặc node bị pause. Tăng retry không giới hạn thường làm hệ thống quá tải hơn.

## 19. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Bộ đếm trong session bị mất cập nhật | Read-modify-write cạnh tranh | Dùng atomic operation hoặc lưu counter ở store chuyên dụng |
| Tồn kho âm hoặc bán vượt số lượng | Kiểm tra và cập nhật tách rời | UPDATE có điều kiện, constraint và transaction |
| Hai đơn hàng được tạo khi client retry | Thiếu idempotency key/unique constraint | Deduplicate ở store dùng chung |
| Node A và B có trạng thái khác nhau | Dựa vào snapshot session hoặc local memory | Tải state có thẩm quyền từ store chung |
| Lock hết hạn nhưng worker cũ vẫn ghi | Không có fencing token/version | Kiểm tra fencing/version tại resource đích |
| Redis và JDBC lệch trạng thái | Nghĩ @Transactional quản lý cả hai resource | Outbox, saga hoặc reconciliation |
| Retry tạo tác dụng phụ nhiều lần | Thao tác không idempotent | Thiết kế key dedup và xử lý kết quả cũ |
| Logout không thu hồi quyền ở node khác | Chỉ xóa trạng thái local hoặc session khác còn tồn tại | Invalidate qua repository chung và kiểm tra quyền theo nguồn có thẩm quyền |
| Test đơn node pass nhưng production lỗi | Không kiểm tra request song song và nhiều instance | Integration test concurrency với store thật |

## 20. Quy trình chọn cơ chế phối hợp

Khi thiết kế một chức năng có trạng thái dùng chung:

1. Viết invariant nghiệp vụ và xác định hậu quả của lost update hoặc xử lý lặp.
2. Chọn nguồn dữ liệu có thẩm quyền; chỉ giữ ID/tham chiếu nhỏ trong session.
3. Nếu một statement đủ, dùng atomic SQL hoặc Redis command.
4. Nếu nhiều bảng cùng thay đổi trong một database, dùng transaction và constraint/row lock phù hợp.
5. Nếu xung đột ít, cân nhắc optimistic locking bằng version.
6. Nếu cần deduplicate request, dùng idempotency key được bảo vệ bằng unique constraint hoặc thao tác atomic.
7. Chỉ dùng distributed lock khi primitive tại resource đích không đủ; bổ sung lease, token và fencing.
8. Nếu nhiều store tham gia, thiết kế outbox, saga hoặc eventual consistency có reconciliation.
9. Kiểm thử request đồng thời, nhiều node, retry và node failure.
10. Theo dõi conflict, retry, lock và độ trễ để điều chỉnh thiết kế.

Spring Session là lớp quản lý phiên dùng chung, không phải cơ chế transaction cho mọi dữ liệu mà ứng dụng đặt trong session. Khi trạng thái nghiệp vụ được lưu ở database hoặc Redis phù hợp và được cập nhật qua thao tác nguyên tử, constraint, version hoặc idempotency, nhiều request và nhiều instance có thể phối hợp mà không làm mất cập nhật hay tạo tác dụng phụ lặp. Chọn đúng điểm có thẩm quyền và kiểm tra invariant tại chính store đó là nền tảng của tính nhất quán.
