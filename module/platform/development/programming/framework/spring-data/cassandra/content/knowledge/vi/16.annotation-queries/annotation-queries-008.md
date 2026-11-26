# IF EXISTS, IF NOT EXISTS và kết quả điều kiện trong Spring Data Cassandra

## 1. Vấn đề nghiệp vụ: đọc rồi ghi chưa đủ để tránh tranh chấp

Giả sử dịch vụ đặt hàng chạy nhiều instance Spring Boot. Hai request gần như đồng thời muốn **tạo cùng một đơn hàng**:

1. Request A hỏi: “Đơn hàng có ID này chưa?” và nhận câu trả lời “chưa”.
2. Request B cũng hỏi và nhận câu trả lời “chưa”.
3. A ghi đơn hàng; B cũng ghi, có thể thay thế những cột của hàng vừa được A tạo.

Đây là **race condition** của mẫu “kiểm tra tồn tại rồi ghi” (`check-then-act`). Dù ứng dụng dùng `CassandraRepository`, `CassandraTemplate` hoặc `CqlTemplate`, việc gọi `existsById(...)` trước `save(...)` **không biến hai thao tác thành nguyên tử**.

**Apache Cassandra** có những câu lệnh **ghi có điều kiện**:

- `INSERT ... IF NOT EXISTS`: chỉ tạo hàng nếu điều kiện hàng chưa tồn tại được thỏa.
- `UPDATE ... IF EXISTS`: chỉ cập nhật nếu hàng đang tồn tại.
- `DELETE ... IF EXISTS`: chỉ xóa nếu hàng đang tồn tại.
- `UPDATE ... IF version = ?` hoặc `IF state = ?`: chỉ thay đổi nếu giá trị đang lưu còn khớp giá trị kỳ vọng.

Các thao tác này sử dụng cơ chế **lightweight transactions (LWT)**, dựa trên đồng thuận Paxos trong phạm vi dữ liệu có điều kiện, chứ không phải một giao dịch SQL quan hệ tự do.

Trong chương **Truy vấn `@Query`** của module **SPRING_DATA_CASSANDRA**, bài học tập trung vào **ý nghĩa của điều kiện và cách đọc kết quả**: khi nào cập nhật thực sự được áp dụng, khi nào điều kiện thất bại, khi nào truy vấn gặp lỗi và cách truyền thông tin đó lên tầng service/API.

Sau bài này, người học cần:

1. Viết và giải thích `IF EXISTS`, `IF NOT EXISTS` cùng điều kiện so sánh giá trị trên một hàng.
2. Phân biệt **`[applied] = true`**, **`[applied] = false`**, kết quả đọc rỗng và **exception**.
3. Biết cách khai báo câu CQL có điều kiện bằng `@Query`/cơ chế modifying query, đồng thời hiểu vì sao một repository method trả `void` không đủ khi nghiệp vụ cần biết kết quả điều kiện.
4. Sử dụng `CqlSession` và `ResultSet.wasApplied()` của Java driver 4.x để lấy kết quả LWT rõ ràng.
5. Thiết kế xử lý cạnh tranh, consistency, retry, idempotency, hiệu năng và kiểm thử trên Cassandra thật.

## 2. Schema thử nghiệm và cách định danh hàng

Để giới hạn ví dụ vào **một hàng thuộc một partition**, ta sử dụng bảng đơn hàng:

~~~sql
-- Keyspace app_ks phải được tạo trước với replication phù hợp cluster.
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    version int,
    total_cents bigint,
    updated_at timestamp
);
~~~

| Cột | Vai trò | Ý nghĩa |
| --- | --- | --- |
| `order_id` | **Primary key và partition key** | Định danh hàng; đủ để tìm đúng một partition |
| `customer_id` | Cột thông thường | Người sở hữu đơn hàng |
| `state` | Cột thông thường | Ví dụ `CREATED`, `PAID`, `CANCELLED` |
| `version` | Cột thông thường | Số phiên bản phục vụ optimistic concurrency |
| `total_cents` | Cột thông thường | Tiền dạng đơn vị nhỏ, tránh dùng số dấu phẩy động cho tiền |
| `updated_at` | Cột thông thường | Thời điểm cập nhật nghiệp vụ |

Ví dụ dùng `order_id uuid` là **một partition key duy nhất** nên dễ hình dung kết quả CAS. Nếu schema có partition key tổng hợp và clustering columns, vẫn phải ràng buộc **đủ thành phần khóa chính cần thiết**, tuân thủ giới hạn conditional DML của phiên bản Cassandra; không tự coi `IF` là giấy phép cập nhật nhiều partition tùy ý.

**Cần nhớ:** `IF EXISTS` kiểm tra tình trạng tồn tại của **hàng tại khóa mục tiêu**. Nó không tìm kiếm hàng dựa trên một cột thông thường, cũng không kiểm tra “đơn hàng của cùng khách hàng đã tồn tại ở một bảng khác chưa”.

## 3. Ghi thông thường khác ghi có điều kiện thế nào?

Với CQL ghi không điều kiện:

~~~sql
INSERT INTO app_ks.orders_by_id
    (order_id, customer_id, state, version, total_cents)
VALUES (?, ?, ?, ?, ?);
~~~

Trong Cassandra, `INSERT` thường có ngữ nghĩa **upsert**: với khóa đã tồn tại, các cột được ghi có thể cập nhật giá trị của hàng hiện hữu theo cơ chế last-write-wins/timestamp. Không nên hiểu đây là `INSERT` kiểu RDBMS luôn phát lỗi duplicate primary key.

Câu tương ứng có điều kiện:

~~~sql
INSERT INTO app_ks.orders_by_id
    (order_id, customer_id, state, version, total_cents)
VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Điều kiện mới làm cho thao tác mang ý nghĩa **“chỉ tạo nếu chưa có hàng tại khóa đó”**. Cassandra trả về một **kết quả điều kiện** để client biết điều kiện có được thỏa hay không.

| Trạng thái tại khóa | `INSERT` thông thường | `INSERT ... IF NOT EXISTS` |
| --- | --- | --- |
| Chưa có hàng | Ghi dữ liệu | Ghi dữ liệu; `[applied] = true` nếu thành công |
| Đã có hàng | Có thể upsert/thay giá trị cột được ghi | Không thay bằng giá trị mới; `[applied] = false` |
| Request timeout hoặc replica không đủ | Trạng thái ghi có thể chưa rõ | Trạng thái thao tác điều kiện có thể chưa rõ; **không suy thành false** |

**Không được đánh đồng** giá trị `false` của điều kiện với việc “Cassandra không thực thi được CQL”. `[applied] = false` là một **kết quả nghiệp vụ hợp lệ** của câu lệnh được thực hiện thành công ở mức giao thức.

## 4. INSERT ... IF NOT EXISTS: tạo duy nhất theo khóa

### 4.1. CQL và kết quả mong muốn

~~~sql
INSERT INTO app_ks.orders_by_id
    (order_id, customer_id, state, version, total_cents)
VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'CREATED',
    1,
    125000
)
IF NOT EXISTS;
~~~

Lần đầu, nếu chưa có hàng, Cassandra trả kết quả có cột điều kiện:

~~~text
 [applied]
-----------
 True
~~~

Khi gọi lại với cùng `order_id` và hàng đã tồn tại, kết quả thường có:

~~~text
 [applied] | ... các cột hiện hữu nếu server trả về ...
-----------+--------------------------------------------
 False     | ...
~~~

Đầu ra chỉ minh họa. **Danh sách các cột bổ sung khi điều kiện không được áp dụng tùy loại câu lệnh và phiên bản Cassandra/driver**; đừng viết code yêu cầu mọi cột phải có trong result. Kết luận ổn định là **cờ `[applied]`**.

Đặc biệt, nếu lần thử đầu đã được Cassandra ghi nhưng client mất response, một lần thử lại `IF NOT EXISTS` có thể trả **false**. Điều đó không chứng minh request đầu thất bại; cần đối chiếu **ID/định danh yêu cầu** hoặc giá trị hiện có để phân biệt “chính tôi đã tạo trước đó” với “một request khác đã tạo”.

### 4.2. Phạm vi “duy nhất”

`INSERT ... IF NOT EXISTS` bảo vệ **định danh hàng/partition tương ứng**. Với `orders_by_id`, nó giúp tránh hai writer cùng tạo **một order_id** khác nội dung.

Nó **không tự đảm bảo**:

- Mỗi khách hàng chỉ có một đơn hàng trên toàn cluster.
- Mỗi email chỉ xuất hiện một lần khi email không phải primary key của bảng đang ghi.
- Hai bảng khác nhau luôn được cập nhật đồng thời.
- Một điều kiện kiểm tra ở partition A đồng thời bảo vệ thay đổi ở partition B.

Muốn duy nhất theo một thuộc tính nghiệp vụ, trước tiên phải thiết kế **bảng tra cứu/giữ chỗ theo đúng khóa nghiệp vụ** và xử lý đồng bộ với những bảng khác theo quy trình có kiểm soát.

## 5. UPDATE ... IF EXISTS: không tạo hàng vô tình

Trong Cassandra, một câu `UPDATE` thông thường có thể tạo hàng tại khóa chưa tồn tại:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = 11111111-1111-4111-8111-111111111111;
~~~

Đối với API “chỉ cập nhật đơn hàng đã có”, hành vi upsert có thể gây sai nghiệp vụ. Ta thêm `IF EXISTS`:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, updated_at = ?
WHERE order_id = ?
IF EXISTS;
~~~

| Trạng thái | Kết quả điều kiện |
| --- | --- |
| Hàng đang tồn tại và mutation hoàn thành | `[applied] = true` |
| Hàng không tồn tại khi kiểm tra điều kiện | `[applied] = false` |
| Không liên lạc đủ replica, timeout, lỗi quyền/schema | **Exception hoặc trạng thái chưa rõ**, không phải `false` |

**Giới hạn quan trọng:** `IF EXISTS` chỉ kiểm tra **sự tồn tại**, không đảm bảo phép chuyển `CREATED → PAID` là hợp lệ. Nếu hàng đang là `CANCELLED` nhưng còn tồn tại, câu trên vẫn có thể cập nhật thành `PAID`.

Khi trạng thái hiện tại là điều kiện của nghiệp vụ, dùng **so sánh có điều kiện** như `IF state = 'CREATED'`, hoặc cơ chế version/compare-and-set ở phần 7.

## 6. DELETE ... IF EXISTS: kết quả xóa có điều kiện

Nếu nghiệp vụ muốn biết thao tác xóa có thật sự xóa được một hàng tồn tại hay không, dùng:

~~~sql
DELETE FROM app_ks.orders_by_id
WHERE order_id = ?
IF EXISTS;
~~~

Kết quả:

- `[applied] = true`: điều kiện tồn tại được thỏa và mutation có điều kiện được chấp nhận.
- `[applied] = false`: khi kiểm tra điều kiện, hàng tại khóa không tồn tại theo ngữ nghĩa thao tác.
- **Exception/timeout**: không thể kết luận đã xóa hay chưa từ một lỗi mạng đơn thuần.

Không phải mọi API xóa đều cần LWT. Với API `DELETE` có yêu cầu **idempotent** theo góc nhìn client (xóa hàng vắng mặt vẫn được xem là thành công), một `DELETE` thông thường có thể hợp lý và rẻ hơn. Hãy dùng `IF EXISTS` khi **kết quả “trước đó có tồn tại hay không” thực sự là một phần của hợp đồng nghiệp vụ**.

Lưu ý: Cassandra sử dụng **tombstone** cho các thao tác xóa. Việc thêm `IF EXISTS` không làm xóa miễn phí, không loại bỏ tombstone, và không thay thế chiến lược TTL/compaction hay thiết kế bảng theo truy vấn.

## 7. So sánh điều kiện: IF state = ? và IF version = ?

### 7.1. Chặn chuyển trạng thái không hợp lệ

Giả sử đơn hàng chỉ được thanh toán nếu còn ở trạng thái `CREATED`:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID', updated_at = ?
WHERE order_id = ?
IF state = 'CREATED';
~~~

Hai writer cùng thử:

~~~mermaid
sequenceDiagram
    participant A as Writer A
    participant C as Cassandra / LWT
    participant B as Writer B
    A->>C: IF state = CREATED, SET state = PAID
    B->>C: IF state = CREATED, SET state = CANCELLED
    C-->>A: Một thao tác có thể [applied] = true
    C-->>B: Thao tác còn lại có thể [applied] = false
~~~

Nếu các thao tác cạnh tranh trên **cùng hàng/partition** và hệ thống hoàn tất xử lý nhất quán, chỉ một writer có thể thành công với trạng thái ban đầu `CREATED` trong cuộc đua này; writer thua phải xử lý **conflict**. Không được suy rằng writer thua gặp lỗi mạng, hoặc tự ý cập nhật không điều kiện để “thử lại cho được”.

### 7.2. Optimistic concurrency bằng version

Nếu một đơn hàng chứa nhiều trường có thể thay đổi, thêm cột `version` là một cách mô tả trạng thái đã đọc. Writer chỉ được cập nhật nếu phiên bản hiện tại còn đúng.

Giả sử hàng đang có `version = 7`. Service đã đọc version 7 và muốn đặt `state = 'PAID'`:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, version = ?, updated_at = ?
WHERE order_id = ?
IF version = ?;
~~~

Bind values minh họa:

~~~text
state       = "PAID"
newVersion  = 8
updatedAt   = 2026-11-25T09:00:00Z
orderId     = UUID(...)
oldVersion  = 7
~~~

Với hai writer cùng đọc version 7, một writer có thể cập nhật thành version 8. Writer còn lại nhận `[applied] = false`, phải **đọc lại và quyết định** có thực hiện lại ý định nghiệp vụ theo version mới hay trả conflict.

**Version là dữ liệu nghiệp vụ của ứng dụng**, không phải counter mà Cassandra tự tăng cho mỗi dòng. Chương trình phải thiết kế cách tăng version, loại bỏ các đường ghi không điều kiện có thể phá quy tắc và kiểm thử các tình huống:

- Bản ghi chưa có `version` hoặc giá trị `null` do dữ liệu cũ.
- Hai writer cùng sửa cùng một field.
- Writer retry sau timeout nhưng có thể lần trước đã áp dụng.
- Những code path sử dụng `save(...)` không điều kiện, khiến version guard bị bỏ qua.

Nếu cần chuyển trạng thái có quy tắc phức tạp, kiểm tra **cả state và version** khi ngữ nghĩa nghiệp vụ yêu cầu, và bảo đảm điều kiện được Cassandra hỗ trợ trong đúng schema/phiên bản.

## 8. Kết quả LWT: [applied] khác dữ liệu trả về

Cassandra trả một **result set cho câu lệnh có điều kiện**. Cột cốt lõi là `[applied]`:

| `[applied]` | Ý nghĩa | Service nên làm gì? |
| --- | --- | --- |
| `true` | Điều kiện được chấp nhận; mutation có điều kiện được áp dụng | Trả kết quả thành công theo hợp đồng |
| `false` | Điều kiện không thỏa; mutation không được áp dụng | Chuyển thành already-exists, not-found hoặc conflict **tùy câu lệnh** |
| Không có kết quả hợp lệ vì timeout/lỗi | Không biết chắc điều kiện/mutation đã diễn ra thế nào | Báo lỗi kỹ thuật/trạng thái chưa xác định và dùng quy trình đối soát phù hợp |

**Không dùng một phép ánh xạ duy nhất** `false → 404 Not Found`:

- `INSERT IF NOT EXISTS` trả false có thể là **409 Conflict / đã tồn tại**.
- `UPDATE IF EXISTS` trả false có thể là **404 / chưa tồn tại**.
- `UPDATE ... IF version = ?` trả false có thể là **409 Conflict / trạng thái cũ** hoặc cần đọc lại để xác định bản ghi có còn tồn tại hay không.
- `DELETE IF EXISTS` trả false có thể là **404**, hoặc có thể là một phản hồi xóa thành công mang tính idempotent theo hợp đồng API.

**Kết quả `[applied] = false` có thể bao gồm giá trị hiện tại** của một số cột liên quan. Đây là dữ liệu bổ trợ để hiểu tranh chấp, **không phải một entity Java đã được mapping đầy đủ**. Hãy kiểm tra metadata/kết quả thực tế theo phiên bản, và không phụ thuộc vào giả định rằng mọi cột luôn xuất hiện.

## 9. Đọc kết quả qua Java driver 4.x: ResultSet.wasApplied()

Khi cần biết điều kiện có được áp dụng hay không, đường rõ ràng là dùng Java driver:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.util.UUID;

public final class OrderConditionalWriter {
    private final CqlSession session;
    private final PreparedStatement createIfAbsent;

    public OrderConditionalWriter(CqlSession session) {
        this.session = session;
        this.createIfAbsent = session.prepare(
            "INSERT INTO app_ks.orders_by_id " +
            "(order_id, customer_id, state, version, total_cents) " +
            "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS"
        );
    }

    public boolean create(
            UUID orderId, UUID customerId, long totalCents) {
        BoundStatement bound = createIfAbsent.bind(
            orderId, customerId, "CREATED", 1, totalCents
        );
        ResultSet result = session.execute(bound);
        return result.wasApplied();
    }
}
~~~

Trong ví dụ, `wasApplied()` trả kết quả boolean của conditional statement:

- `true`: tạo hàng được chấp nhận.
- `false`: hàng đã tồn tại nên thao tác create-if-absent không được áp dụng.
- Nếu `execute(...)` ném exception, **không có boolean hợp lệ để kết luận điều kiện thất bại**.

Ví dụ dùng **`CqlSession` được quản lý và tái sử dụng**, không đóng session trong từng request. `PreparedStatement` được chuẩn bị một lần khi writer được tạo, còn `BoundStatement` được tạo mới cho mỗi thao tác. Cấu hình contact points, local datacenter, authentication và keyspace phải phù hợp với cluster. Cú pháp Java driver ở đây dựa trên dòng **4.x**; cần đối chiếu phiên bản dự án.

### 9.1. Không lấy Row như một SELECT thông thường

Với kết quả conditional write, API ưu tiên dùng `wasApplied()`, không cố giả định:

~~~java
// KHÔNG KHUYẾN NGHỊ làm cách duy nhất để biết CAS đã thành công:
Row row = result.one();
boolean applied = row.getBoolean("[applied]");
~~~

Tùy trình điều khiển kết quả, metadata và phương thức mapping, cột đặc biệt `[applied]` có thể cần xử lý khác với một cột CQL bình thường. `ResultSet.wasApplied()` thể hiện rõ dụng ý và ít phụ thuộc hơn vào cách biểu diễn các cột. Chỉ đọc thêm `Row` nếu nghiệp vụ thực sự cần dữ liệu hiện tại được trả khi điều kiện thất bại **và đã kiểm tra chúng có tồn tại**.

### 9.2. Dùng @Query cho câu SELECT, driver cho kết quả CAS

Hai chức năng có thể cùng tồn tại trong một service:

~~~text
OrderRepository.findById(orderId)  -> đọc entity qua Spring Data
OrderConditionalWriter.create(...) -> CqlSession.execute(...) và wasApplied()
~~~

Không có mâu thuẫn: repository thuận tiện cho thao tác thông thường; driver thuận tiện khi cần **kiểm soát chính xác kết quả LWT**, consistency, serial consistency và lỗi. Điều quan trọng là **cả hai cùng dùng đúng schema/keyspace**.

## 10. @Query và @Modifying: khai báo DML có điều kiện cần chú ý gì?

Spring Data Cassandra hỗ trợ khai báo truy vấn CQL bằng annotation `@Query`. Với **CQL làm thay đổi dữ liệu**, nhiều dòng Spring Data Cassandra còn dùng `@Modifying` để thể hiện đây không phải truy vấn trả entity thông thường.

Ví dụ minh họa cách **khai báo câu CQL có điều kiện** trong repository:

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Modifying;
import org.springframework.data.cassandra.repository.Query;

public interface OrderRepository
        extends CassandraRepository<OrderRow, UUID> {

    @Modifying
    @Query("UPDATE app_ks.orders_by_id " +
           "SET state = ?0 WHERE order_id = ?1 IF EXISTS")
    void updateStateIfExists(String nextState, UUID orderId);
}
~~~

Đoạn ví dụ dùng **`void` một cách có chủ ý để không giả định mapping của `[applied]`**. Những vấn đề cần kiểm tra ở **đúng phiên bản Spring Data Cassandra** đang sử dụng:

1. Annotation `@Modifying`, package import, cú pháp bind parameter và kiểu trả về được hỗ trợ cho modifying query.
2. Framework **có trả về cờ CAS hay không** khi method khai báo một kiểu khác `void`; không tự suy luận rằng kiểu `boolean` của repository luôn là `[applied]`.
3. Một số kiểu kết quả modifying có thể mang ý nghĩa khác (số hàng, success/acknowledgement) theo công nghệ/phiên bản; không dùng chúng làm CAS result nếu chưa chứng minh.
4. Nếu ứng dụng **cần phân biệt hàng có tồn tại**, **đã cập nhật hay chưa**, hoặc cần các cột hiện có khi CAS thất bại, nên ưu tiên một đường đọc `ResultSet.wasApplied()` tường minh, có test tích hợp.

**Đừng coi việc method `void` không ném exception là bằng chứng điều kiện đã thỏa.** Một câu LWT có thể hoàn tất thành công nhưng trả `[applied] = false`. Nếu nghiệp vụ cần báo conflict cho client, method `void` là **không đủ thông tin**.

### 10.1. Khi nào @Query vẫn rất hữu ích?

Ví dụ repository đọc:

~~~java
@Query("SELECT order_id, customer_id, state, version, total_cents, updated_at " +
       "FROM app_ks.orders_by_id WHERE order_id = ?0")
Optional<OrderRow> findOrder(UUID orderId);
~~~

`@Query` giúp kiểm soát projection và câu CQL khi derived method không phù hợp. Với mutation có điều kiện, nó mô tả **điều kiện tại server**; **kết quả điều kiện** vẫn cần được xử lý rõ ở tầng truy cập dữ liệu thay vì chỉ nhìn tên method.

## 11. Một service trả kết quả nghiệp vụ thay vì boolean mơ hồ

Boolean `true/false` có thể đủ ở tầng driver, nhưng API thực tế cần phân biệt kết quả khác nhau. Ví dụ khi tạo đơn hàng:

~~~java
public enum CreateOrderOutcome {
    CREATED,
    ALREADY_EXISTS
}
~~~

Service:

~~~java
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderCreationService {
    private final OrderConditionalWriter writer;

    public OrderCreationService(OrderConditionalWriter writer) {
        this.writer = writer;
    }

    public CreateOrderOutcome create(
            UUID orderId, UUID customerId, long totalCents) {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        if (totalCents < 0) {
            throw new IllegalArgumentException("Negative total");
        }

        return writer.create(orderId, customerId, totalCents)
            ? CreateOrderOutcome.CREATED
            : CreateOrderOutcome.ALREADY_EXISTS;
    }
}
~~~

Ví dụ giả định `OrderConditionalWriter` đã được đăng ký làm bean (ví dụ bằng `@Bean` hoặc `@Component`), hạ tầng session được Spring quản lý và bảng đã tồn tại. Kết quả `ALREADY_EXISTS` chỉ có nghĩa conditional insert **không được áp dụng** vì điều kiện tại hàng đã không thỏa; nếu cần kiểm tra hàng đó thuộc request tương ứng, phải bổ sung thông tin/idempotency key và quy trình đối chiếu.

Không nên viết:

~~~java
try {
    return writer.create(orderId, customerId, totalCents);
} catch (Exception ex) {
    return false; // SAI: biến mọi lỗi mạng/schema/thời gian chờ thành conflict.
}
~~~

Đường lỗi kỹ thuật phải được phân loại riêng. Đặc biệt sau timeout, mutation **có thể đã xảy ra**; cần trạng thái chưa xác định hoặc quy trình kiểm tra lại thích hợp, không trả chắc chắn “chưa tạo”.

## 12. Serial consistency và regular consistency trong LWT

LWT dùng **quy trình đồng thuận Paxos**, vì vậy cần phân biệt hai nhóm consistency:

| Khía cạnh | Vai trò |
| --- | --- |
| **Regular consistency level** | Mức phản hồi/nhất quán của thao tác đọc/ghi thông thường ở pha phù hợp |
| **Serial consistency level** | Phạm vi yêu cầu nhất quán cho pha đồng thuận LWT; thường có lựa chọn `SERIAL` hoặc `LOCAL_SERIAL` tùy cluster/phiên bản |

Ví dụ Java driver 4.x với một `BoundStatement` có điều kiện:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

BoundStatement statement = createIfAbsent
    .bind(orderId, customerId, "CREATED", 1, totalCents)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

ResultSet result = session.execute(statement);
boolean applied = result.wasApplied();
~~~

Đây là **minh họa cú pháp**, không phải cấu hình mặc định nên áp dụng cho mọi triển khai. Chọn `LOCAL_SERIAL` hay `SERIAL` phụ thuộc topology, các datacenter và yêu cầu nhất quán; đặc biệt trong multi-DC, không được giả định phạm vi local tương đương phạm vi đồng thuận toàn cluster. Hãy sử dụng tài liệu và quy tắc vận hành của **phiên bản Cassandra/driver thực tế** để chọn kết hợp consistency phù hợp.

**LWT không miễn phí**: so với write không điều kiện, nó cần thêm phối hợp giữa replica, làm tăng round-trip, độ trễ và khả năng cạnh tranh trên partition nóng. Không nên đưa mọi thao tác cập nhật thành LWT chỉ vì có `IF` trong CQL.

### 12.1. Tại sao không dùng LWT để thay mọi transaction?

LWT hữu ích khi nghiệp vụ cần một **quyết định có điều kiện trên hàng/partition được xác định**. Nó không tự biến Cassandra thành hệ RDBMS:

- Không có `JOIN` hoặc transaction ACID tùy ý qua nhiều bảng/partition.
- Không tự đồng bộ các bảng denormalized khác nhau khi một hàng được ghi có điều kiện.
- Không thay thế cơ chế workflow/saga/đối soát cho các thao tác xuyên partition.
- Không loại bỏ việc xử lý timeout, idempotency và khả năng kết quả chưa xác định.

Với dữ liệu phân tán, hãy dùng LWT **có chọn lọc** cho những bất biến nghiệp vụ thực sự phải bảo vệ bằng compare-and-set.

## 13. Chống race condition và tính idempotent khi retry

### 13.1. Ba kết quả khác nhau của một request

Giả sử client gửi lệnh `INSERT ... IF NOT EXISTS`:

~~~mermaid
flowchart TD
    A[Execute conditional INSERT] --> B{Nhận kết quả hợp lệ?}
    B -->|Có| C{wasApplied?}
    C -->|true| D[CREATED]
    C -->|false| E[ALREADY_EXISTS hoặc cần đối soát]
    B -->|Không: timeout/Unavailable| F[UNKNOWN / technical error]
    F --> G[Đọc/đối soát và retry theo chính sách]
~~~

Lựa chọn **UNKNOWN** là thực tế cần lưu ý: khi client không nhận được phản hồi, có thể thao tác chưa diễn ra, đang diễn ra hoặc đã diễn ra trên một số replica. Không nên cam kết trạng thái chỉ dựa vào exception class mà chưa xem ngữ nghĩa thao tác và khả năng đối soát.

### 13.2. Idempotency key và cùng một request được gửi lại

Giả sử gateway retry request tạo đơn hàng sau timeout. Lần đầu đã tạo thành công nhưng response mất; lần thứ hai nhận `[applied] = false`. Nếu API trả 409 ngay, client có thể hiểu nhầm là một request khác đã tranh chấp.

Một thiết kế có thể lưu thêm **`request_id`** hoặc khóa idempotency do client cấp cùng hàng:

~~~sql
-- Ví dụ schema mở rộng cho bài toán idempotency:
-- orders_by_id có thêm cột request_id uuid.
INSERT INTO app_ks.orders_by_id
    (order_id, request_id, customer_id, state, version, total_cents)
VALUES (?, ?, ?, 'CREATED', 1, ?)
IF NOT EXISTS;
~~~

Khi nhận `false`, service có thể đọc hàng hiện tại và kiểm tra `request_id`:

- Trùng request ID và payload khớp: có thể trả một phản hồi **idempotent replay** theo hợp đồng.
- Khác request ID hoặc payload mâu thuẫn: xử lý conflict.
- Đọc lại gặp lỗi hoặc trạng thái không rõ: không tự khẳng định đã an toàn.

**Quan trọng:** bước đối chiếu phụ thuộc consistency, có thể có cạnh tranh/xóa/TTL và cần giữ thông tin idempotency đủ lâu. Đây là **quy trình nghiệp vụ** bổ sung, không phải tính năng tự động của `IF NOT EXISTS`.

### 13.3. Retry UPDATE IF version

Khi CAS version thất bại, thường **không** retry nguyên request với `expectedVersion` cũ mãi mãi. Cần:

1. Đọc lại phiên bản và dữ liệu hiện tại nếu nghiệp vụ yêu cầu.
2. Kiểm tra lệnh người dùng còn hợp lệ không.
3. Tạo mutation mới với expected version đúng, hoặc trả conflict để người dùng quyết định.
4. Giới hạn số lần retry và quan sát mức tranh chấp.

Không tự động “cố ghi thành công” bằng câu `UPDATE` không điều kiện, vì điều đó phá mục đích CAS.

## 14. Ràng buộc theo partition key và các bảng denormalized

Trong Cassandra, dữ liệu thường được **nhân bản logic theo nhiều bảng phục vụ truy vấn**. Ví dụ có thể có:

~~~text
orders_by_id
orders_by_customer_day
order_state_by_customer
~~~

Một `INSERT IF NOT EXISTS` trên `orders_by_id` chỉ bảo vệ điều kiện ở **hàng thuộc bảng đó**. Nó không tự đảm bảo hai bảng còn lại được cập nhật cùng lúc và không có trạng thái tạm thời lệch nhau.

Nếu cần:

- Ghi hàng chính bằng conditional insert.
- Chỉ khi **`[applied] = true`**, tiếp tục ghi bảng phục vụ truy vấn khác.
- Nếu bước ghi thứ hai thất bại, ghi nhận trạng thái cần retry/đối soát.
- Nếu thao tác đầu timeout, đối soát trước khi tái chạy cả workflow.

Đây là kiểu **workflow nhiều bước**, không phải giao dịch nhiều bảng được bảo đảm bởi một `@Query`. Cần làm rõ bất biến nào bảo vệ ở Cassandra bằng LWT, bất biến nào xử lý bằng idempotency/saga và độ trễ đồng bộ chấp nhận được.

### 14.1. Ví dụ giữ chỗ tên đăng nhập theo tenant

Nếu cần tên đăng nhập duy nhất **trong một tenant**, có thể định danh bảng theo cặp tenant/username:

~~~sql
CREATE TABLE app_ks.username_reservations (
    tenant_id uuid,
    username text,
    owner_id uuid,
    request_id uuid,
    PRIMARY KEY ((tenant_id, username))
);
~~~

~~~sql
INSERT INTO app_ks.username_reservations
    (tenant_id, username, owner_id, request_id)
VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Mỗi tổ hợp `(tenant_id, username)` là một partition key, nên LWT bảo vệ quyết định giữ chỗ **đúng cặp khóa đó**. Phải chuẩn hóa `username` **trước khi làm partition key** (ví dụ quy tắc chữ hoa/thường, Unicode, khoảng trắng), không để các instance dùng hai quy tắc khác nhau.

Nhưng thao tác giữ chỗ và thao tác tạo profile ở bảng khác **vẫn là hai bước**; hệ thống cần xử lý trường hợp reservation thành công còn tạo profile thất bại, cơ chế giải phóng giữ chỗ và đối soát.

## 15. Hiệu năng và cách dùng LWT có chủ đích

### 15.1. LWT nên dùng khi nào?

| Nhu cầu | LWT có hợp lý? | Lý do |
| --- | --- | --- |
| Tạo đúng một hàng theo khóa, không được ghi đè | **Có thể nên dùng `IF NOT EXISTS`** | Chặn hai writer cùng tạo khác nội dung |
| Chuyển trạng thái chỉ khi ở trạng thái cho phép | **Có thể dùng `IF state = ?`** | Bảo vệ state transition |
| Optimistic concurrency khi nhiều writer cập nhật một hàng | **Có thể dùng `IF version = ?`** | Phát hiện stale update |
| Ghi telemetry độc lập với khóa duy nhất, chấp nhận upsert | **Không nhất thiết** | Ghi thông thường có thể đơn giản và rẻ hơn |
| Đọc một trang lịch sử sự kiện | **Không** | Đây là vấn đề SELECT/paging, không phải conditional write |
| Bảo đảm cập nhật nguyên tử xuyên nhiều partition/bảng | **Không đủ** | Cần thiết kế workflow hoặc công nghệ khác |

### 15.2. Hot partition và contention

Nếu nhiều request LWT tranh chấp **cùng một partition**, độ trễ có thể tăng và tần suất `[applied] = false` lớn. Không nên mặc định thêm nhiều retry với backoff thấp vì có thể làm tắc nghẽn nặng hơn.

Đo các chỉ số như:

- Tỷ lệ điều kiện được áp dụng so với thất bại.
- Latency phân vị của LWT, timeout và lỗi không đủ replica.
- Tần suất retry, số request cùng tranh chấp một khóa.
- Trạng thái node/topology, replication và serial consistency được cấu hình.
- Kích thước partition, tombstone, workload ghi/đọc khác trên cùng dữ liệu.

Việc dùng prepared statement cho một câu LWT giúp tránh chuẩn bị query liên tục, nhưng **không loại bỏ chi phí Paxos**. Cần thiết kế truy vấn theo partition key và đo trước khi đưa LWT vào đường ghi có lưu lượng rất lớn.

## 16. Kiểm thử kết quả điều kiện và cạnh tranh

### 16.1. Một bài test tích hợp INSERT IF NOT EXISTS

Giả sử test có `CqlSession session` đã kết nối đến keyspace phù hợp và bảng `orders_by_id` đã tạo. Ví dụ:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

@Test
void insertIfNotExistsReportsAppliedFlag() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    PreparedStatement insert = session.prepare(
        "INSERT INTO app_ks.orders_by_id " +
        "(order_id, customer_id, state, version, total_cents) " +
        "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS"
    );

    ResultSet first = session.execute(insert.bind(
        orderId, customerId, "CREATED", 1, 1000L
    ));
    assertTrue(first.wasApplied());

    ResultSet second = session.execute(insert.bind(
        orderId, customerId, "CREATED", 1, 9999L
    ));
    assertFalse(second.wasApplied());

    // Xác nhận lần gọi thứ hai không ghi đè tổng tiền đã tạo.
    PreparedStatement select = session.prepare(
        "SELECT total_cents FROM app_ks.orders_by_id " +
        "WHERE order_id = ?"
    );
    long stored = session.execute(select.bind(orderId))
        .one().getLong("total_cents");
    assertEquals(1000L, stored);
}
~~~

Đoạn test sử dụng bind parameter cho cả câu `INSERT` lẫn `SELECT`, không nối giá trị đầu vào vào CQL. Test cần có fixture, cấu hình session và cleanup dữ liệu test rõ ràng.

### 16.2. Ma trận kiểm thử nên có

| Tình huống | Lệnh | Kỳ vọng |
| --- | --- | --- |
| ID chưa tồn tại | `INSERT IF NOT EXISTS` | `wasApplied() == true` |
| ID đã tồn tại | `INSERT IF NOT EXISTS` | `false`, dữ liệu cũ không bị ghi đè |
| Hàng đã tồn tại | `UPDATE ... IF EXISTS` | `true` |
| Hàng chưa tồn tại | `UPDATE ... IF EXISTS` | `false`, không tạo hàng mới |
| Hàng đã tồn tại | `DELETE ... IF EXISTS` | `true` |
| Hàng chưa tồn tại | `DELETE ... IF EXISTS` | `false` |
| Version hiện tại khớp | `UPDATE ... IF version = ?` | `true`, version tăng theo quy tắc ứng dụng |
| Version cũ | `UPDATE ... IF version = ?` | `false`, không ghi đè dữ liệu mới |
| Hai writer cùng expected version | Hai LWT cạnh tranh trên một hàng | Chỉ writer đáp ứng điều kiện tại thời điểm quyết định mới được áp dụng |
| Timeout/Unavailable | Bất kỳ LWT nào | Exception, **không** chuyển thành `[applied] = false` |
| Dữ liệu cũ thiếu version | `UPDATE ... IF version = ?` | Xử lý theo migration/khởi tạo version đã xác định |
| Tranh chấp nhiều | Gửi nhiều request vào cùng key | Đo latency và tỷ lệ false, không retry vô hạn |

### 16.3. Test nhiều writer

Một test cạnh tranh có thể dùng hai thread/service instance, cùng đọc `version = 1` rồi **đồng bộ thời điểm bắt đầu** cho cả hai mutation:

~~~text
T0: Order có version = 1, state = CREATED
T1: Writer A và B đều chuẩn bị IF version = 1
T2: A muốn version = 2, state = PAID
T3: B muốn version = 2, state = CANCELLED
T4: Cả hai cùng thực thi
Kỳ vọng: một thao tác được áp dụng;
         thao tác còn lại không được áp dụng nếu điều kiện đã đổi.
Kiểm tra: state/version cuối cùng khớp writer thắng.
~~~

Test cần chạy trên **Cassandra thật** với cùng partition và không có tác động ngoài test làm thay đổi hàng. Mock repository không thể kiểm tra Paxos/định tuyến của cluster; nó chỉ kiểm tra cách service xử lý `true/false`.

### 16.4. Test tầng API

| Thao tác nghiệp vụ | Kết quả LWT | Phản hồi API gợi ý |
| --- | --- | --- |
| Tạo đơn | `true` | `201 Created` |
| Tạo đơn | `false` do ID đã được sử dụng | `409 Conflict` hoặc replay idempotent nếu khớp request |
| Cập nhật phải có sẵn | `false` do hàng không tồn tại | `404 Not Found` |
| Cập nhật theo version | `false` do stale version | `409 Conflict` / yêu cầu tải lại |
| Xóa idempotent | `false` do hàng vắng mặt | Có thể `204 No Content` tùy hợp đồng |
| Cassandra timeout hoặc unavailable | Không có cờ `[applied]` hợp lệ | Lỗi kỹ thuật/không chắc trạng thái, thường thuộc nhóm 5xx hoặc chính sách API phù hợp |

Đây là **quy ước API gợi ý**, không phải HTTP status do Cassandra tự quyết định. Không log toàn bộ request chứa dữ liệu nhạy cảm khi truy vết LWT; ưu tiên correlation ID và metadata cần thiết.

## 17. Những lỗi thường gặp

| Hiểu nhầm / cách làm sai | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “`INSERT` thường bị lỗi nếu khóa đã có.” | Dễ ghi đè do upsert | Dùng `IF NOT EXISTS` khi thật sự cần create-only |
| “`existsById` rồi `save` là nguyên tử.” | Hai request có thể vượt qua kiểm tra cùng lúc | Dùng LWT nếu bất biến cần CAS |
| “`UPDATE IF EXISTS` bảo đảm chuyển trạng thái hợp lệ.” | Có thể sửa hàng ở trạng thái không được phép | Dùng `IF state = ?` hoặc version guard |
| “`[applied] = false` nghĩa là query lỗi.” | Biến conflict thành lỗi hạ tầng | Đó là **kết quả điều kiện**, không phải exception |
| “Mọi `false` đều là 404.” | Tạo sai hợp đồng API | Diễn giải theo loại câu CQL |
| “`void` method không ném lỗi nghĩa là điều kiện thành công.” | Che mất CAS không áp dụng | Đọc kết quả điều kiện rõ ràng nếu cần |
| “Trả `boolean` từ `@Modifying` chắc chắn là `[applied]`.” | Có thể hiểu sai contract theo framework | Xác minh phiên bản, hoặc dùng `ResultSet.wasApplied()` |
| “Timeout thì chắc chắn mutation chưa xảy ra.” | Retry sai, tạo kết quả khó đối soát | Xử lý trạng thái chưa rõ và idempotency |
| “LWT bảo vệ mọi bảng/partition trong workflow.” | Dữ liệu denormalized có thể lệch tạm thời | Thiết kế saga/đối soát |
| “`LOCAL_SERIAL` và `SERIAL` luôn tương đương.” | Đánh giá sai độ nhất quán ở multi-DC | Chọn theo topology và yêu cầu |
| “LWT làm mọi write nhanh hơn.” | Tăng Paxos round-trip và contention | Dùng chọn lọc, đo hiệu năng |
| “Ghi version ở một code path là đủ.” | Write không điều kiện khác phá cơ chế kiểm soát | Bảo vệ mọi đường cập nhật liên quan |

## 18. Bài thực hành tổng hợp

**Tình huống:** một API tạo đơn hàng phải ngăn ghi đè khi hai request cùng dùng `order_id`. API chuyển trạng thái từ `CREATED` sang `PAID` phải từ chối nếu đơn đã bị hủy hoặc bị writer khác cập nhật.

Các bước:

1. Tạo bảng thử nghiệm `app_ks.orders_by_id` với `order_id`, `state`, `version` và các cột minh họa.
2. Viết ba câu CQL: `INSERT ... IF NOT EXISTS`, `UPDATE ... IF EXISTS` và `UPDATE ... IF version = ?`.
3. Thực thi trực tiếp qua `cqlsh` để quan sát `[applied]` khi hàng vắng mặt và khi đã tồn tại.
4. Tạo lớp `OrderConditionalWriter` sử dụng một `CqlSession` và `PreparedStatement`, bind tham số mỗi lần, trả `wasApplied()`.
5. Viết repository `@Query` đọc hàng theo ID; nếu thử `@Modifying` cho conditional update, xác minh kiểu trả về và **không tự xem `void` là thành công của điều kiện**.
6. Trả kết quả nghiệp vụ `CREATED`/`ALREADY_EXISTS` hoặc `UPDATED`/`CONFLICT` ở tầng service.
7. Gửi hai lệnh tạo cùng `order_id` với dữ liệu khác nhau; xác minh chỉ một bản ghi được tạo.
8. Đọc `version = 1`, cho hai writer cạnh tranh cùng expected version; xác minh không có lost update âm thầm.
9. Thử một hàng không tồn tại với `UPDATE IF EXISTS`; kiểm tra `false` và không có hàng “ma” mới được tạo.
10. Mô phỏng timeout/lỗi kết nối ở tầng service để bảo đảm exception **không bị biến thành CAS false**; mô tả cách đối soát sau trạng thái chưa rõ.
11. Đo chi phí truy vấn conditional so với write thông thường trong môi trường thử nghiệm, không gây tải quá mức hoặc thử fault injection trên production.
12. Nếu có bảng denormalized, thiết kế các bước retry/idempotency/đối soát khi bước thứ hai thất bại.

**Tiêu chí đạt:** người học phân biệt được **điều kiện được áp dụng**, **điều kiện không thỏa** và **không có phản hồi hợp lệ do lỗi**; dùng LWT đúng phạm vi hàng/partition, có chính sách concurrency và retry phù hợp với ứng dụng phân tán.

## 19. Câu hỏi tự kiểm tra

1. Vì sao `existsById` rồi `save` không bảo vệ được hai request tạo cùng hàng?
2. `INSERT ... IF NOT EXISTS` khác `INSERT` thông thường ở điểm nào?
3. `UPDATE ... IF EXISTS` có thể chặn trường hợp tạo hàng ngoài ý muốn như thế nào?
4. Vì sao `UPDATE ... IF EXISTS` chưa đủ để bảo vệ chuyển trạng thái `CREATED → PAID`?
5. Khi `[applied] = false` đối với `INSERT IF NOT EXISTS`, nên hiểu ra sao?
6. Khi `[applied] = false` đối với `UPDATE IF version = ?`, có chắc hàng đã bị xóa không?
7. Vì sao `ResultSet.wasApplied()` phù hợp hơn việc chỉ dựa vào một repository method `void`?
8. Annotation `@Query` diễn đạt CQL; khi thực hiện DML có điều kiện, cần kiểm tra thêm điều gì về `@Modifying` và kiểu trả về?
9. Vì sao timeout sau `IF NOT EXISTS` không chứng minh insert chưa xảy ra?
10. Khi retry cùng một request tạo đơn, tại sao cần request ID hoặc cách đối chiếu payload?
11. Version guard bảo vệ được vấn đề gì và những code path ghi không điều kiện có thể phá nó thế nào?
12. `SERIAL` và `LOCAL_SERIAL` đóng vai trò gì trong LWT? Khác gì regular consistency?
13. Vì sao LWT có thể làm tăng độ trễ khi nhiều writer tranh chấp cùng partition?
14. LWT trên bảng `orders_by_id` có tự cập nhật nguyên tử bảng `orders_by_customer_day` không?
15. Khi cần tên đăng nhập duy nhất theo tenant, vì sao nên định danh bảng giữ chỗ bằng `(tenant_id, username)`?
16. Các test nào cần dùng Cassandra thật thay vì chỉ mock repository?

**Ghi nhớ:** `IF NOT EXISTS`, `IF EXISTS` và `IF cột = giá_trị` giúp Cassandra quyết định có thực hiện mutation hay không theo cơ chế **lightweight transaction**. **`[applied] = true` là được áp dụng; `false` là điều kiện không thỏa; timeout/exception là trạng thái khác, có thể chưa biết thao tác đã xảy ra hay chưa.** Với Spring Data Cassandra, dùng `@Query` để biểu đạt CQL rõ ràng, nhưng **phải kiểm tra contract của modifying method**; khi cần kết quả CAS chính xác, `CqlSession` và `ResultSet.wasApplied()` là đường tường minh. LWT bảo vệ những bất biến cụ thể trên khóa phù hợp, không thay thế thiết kế bảng theo truy vấn, partition key, consistency, paging hay quy trình nghiệp vụ phân tán.
