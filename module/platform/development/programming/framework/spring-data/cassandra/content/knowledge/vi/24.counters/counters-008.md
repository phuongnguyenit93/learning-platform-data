# Xóa, tạo lại và vòng đời của dữ liệu counter

Trong **Apache Cassandra**, cột `counter` dùng để **tăng hoặc giảm** một số đếm phân tán mà không cần ứng dụng đọc tổng hiện tại rồi tự tính giá trị mới. Nó hữu ích cho lượt xem, số lần truy cập hay những thống kê có thể đối soát. Tuy nhiên, **counter không phải cột `bigint` thông thường**: không thể gán giá trị tuyệt đối, không áp dụng TTL, và **xóa một counter không đồng nghĩa với reset an toàn để sử dụng lại cùng khóa**.

Giả sử counter đã có giá trị 100. Ứng dụng gửi `DELETE`, sau đó gửi `UPDATE total = total + 1` lên cùng primary key và kỳ vọng giá trị luôn trở thành 1. Kỳ vọng đó bỏ qua **counter shards, replica chậm/offline, tombstone, các increment đang bay và retry**. Trong Cassandra, việc kết thúc vòng đời của một counter và bắt đầu một phép đếm mới nên được diễn đạt qua **khóa thế hệ (generation/epoch) khác nhau**, không chỉ qua một lệnh xóa.

Bài thuộc chương **Bộ đếm** của module **SPRING_DATA_CASSANDRA**. Ta sẽ học cấu trúc bảng counter, vòng đời create–increment–read–retire–delete, cách sử dụng **Spring Data Cassandra**, `CassandraTemplate`, repository/`@Query`, Java Driver, consistency level, và chiến lược đổi thế hệ để không trộn số đếm cũ với số đếm mới.

## 1. Counter phù hợp với mục tiêu nào?

| Nhu cầu | Counter có phù hợp? | Điều cần hiểu |
| --- | --- | --- |
| Lượt xem, lượt truy cập, thống kê có thể tái tính | Có thể | Increment thuận tiện nhưng timeout/retry có thể đếm đôi |
| Số đếm tạm thời theo kỳ/ngày/tháng | Có thể | Cần time bucket, lifecycle và thế hệ riêng |
| Số dư tài khoản hoặc tồn kho cần ràng buộc chính xác | **Không nên dùng đơn độc** | Không bảo đảm exactly-once hay compare-and-set tùy ý |
| Đặt số đếm thành một giá trị tuyệt đối | Không | Counter chỉ cập nhật bằng cộng/trừ |
| Giữ số đếm trong 30 ngày qua `USING TTL` | Không | Counter không hỗ trợ TTL |
| Xóa rồi mở lại cùng định danh an toàn tuyệt đối | Không | Cần cách ly khóa cũ khỏi khóa mới |

**Counter không phải một transaction ledger.** Nếu mỗi event nghiệp vụ bắt buộc được đếm chính xác một lần, cần một nguồn sự thật có định danh event riêng và quy trình dedup/reconciliation, thay vì chỉ dựa vào tổng hiện thời.

## 2. Schema: cột thường và cột counter không trộn lẫn

Thiết kế bảng counter theo truy vấn “đếm metric của một tenant trong một tháng và một thế hệ”:

~~~sql
CREATE KEYSPACE IF NOT EXISTS metrics_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS metrics_ks.metric_counters_by_month (
    tenant_id     uuid,
    month_bucket  date,
    generation_id uuid,
    metric_name   text,
    total         counter,
    PRIMARY KEY (
        (tenant_id, month_bucket, generation_id),
        metric_name
    )
);
~~~

- `(tenant_id, month_bucket, generation_id)` là **composite partition key**: chọn partition/replica.
- `metric_name` là **clustering column**: cho phép nhiều metric trong partition, miễn là số hàng/byte vẫn có giới hạn.
- `total counter` là cột counter: cập nhật bằng `+` hoặc `-`, không qua `INSERT`/`SET total = 0`.
- `generation_id` tách một đợt đo mới khỏi các giá trị đã hết vòng đời.

Quy tắc schema: trong bảng chứa counter, **những cột không thuộc primary key phải là counter**. Các trường metadata như `updated_at timestamp`, `status text` và `request_id uuid` phải nằm trong **bảng thường khác**.

Tên datacenter `dc1` và RF=3 chỉ là ví dụ; cấu hình phải phù hợp topology thực. Ở production, quản lý keyspace/schema bằng migration được duyệt, không để các instance tự tạo/sửa cấu trúc.

## 3. CQL: chỉ tăng hoặc giảm

Hai câu lệnh cơ bản:

~~~sql
-- Cộng một đơn vị.
UPDATE metrics_ks.metric_counters_by_month
SET total = total + 1
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?
  AND metric_name = ?;

-- Trừ một đơn vị.
UPDATE metrics_ks.metric_counters_by_month
SET total = total - 1
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?
  AND metric_name = ?;
~~~

Có thể bind delta:

~~~sql
UPDATE metrics_ks.metric_counters_by_month
SET total = total + ?
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?
  AND metric_name = ?;
~~~

Khi cần trừ, dùng câu lệnh có dấu `-` và bind trị tuyệt đối dương; validate dấu và khoảng delta ở service.

**Không làm những việc sau:**

~~~sql
-- SAI: không có thao tác gán một counter thành 0.
UPDATE metrics_ks.metric_counters_by_month
SET total = 0
WHERE tenant_id = ? AND month_bucket = ?
  AND generation_id = ? AND metric_name = ?;

-- SAI: INSERT counter không phải cách tạo số đếm.
INSERT INTO metrics_ks.metric_counters_by_month (
    tenant_id, month_bucket, generation_id, metric_name, total
) VALUES (?, ?, ?, ?, 0);

-- SAI: counter update không hỗ trợ TTL.
UPDATE metrics_ks.metric_counters_by_month
USING TTL 3600
SET total = total + 1
WHERE tenant_id = ? AND month_bucket = ?
  AND generation_id = ? AND metric_name = ?;
~~~

Tương tự, **`USING TIMESTAMP` không được dùng cho counter update** như với cột scalar thông thường. Counter được quản lý bằng cơ chế trạng thái phân tán riêng; không có thao tác gán write timestamp tùy ý kiểu scalar.

## 4. Đọc counter và phân biệt “không có hàng” với số 0

Truy vấn một metric:

~~~sql
SELECT total
FROM metrics_ks.metric_counters_by_month
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?
  AND metric_name = ?;
~~~

Đọc một nhóm nhỏ metric cùng partition:

~~~sql
SELECT metric_name, total
FROM metrics_ks.metric_counters_by_month
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?;
~~~

Ở một generation mới có thể **chưa từng có increment**, vì thế query có thể không trả hàng. API có thể quy ước “không có counter row” được hiển thị **0** cho người dùng; đó là quyết định của **miền nghiệp vụ**, không phải bằng chứng đã ghi `total = 0`.

Khi chạy trong cluster phân tán, giá trị quan sát còn phụ thuộc replication, consistency level, đồng bộ replica và các increment/decrement đang thực thi.

## 5. DELETE counter không phải SET counter = 0

Các thao tác xóa **hàng hoặc partition** có điều kiện khóa hợp lệ:

~~~sql
-- Xóa một hàng counter xác định bằng đầy đủ khóa.
DELETE FROM metrics_ks.metric_counters_by_month
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?
  AND metric_name = ?;

-- Xóa cả partition của một thế hệ trong tháng.
DELETE FROM metrics_ks.metric_counters_by_month
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?;
~~~

Các ví dụ cố ý xóa **row/partition**, không minh họa cú pháp xóa riêng một counter column. Giới hạn thao tác xóa counter theo phạm vi cụ thể cần được đối chiếu với Cassandra version.

Xóa tạo thông tin về trạng thái bị xóa trong hệ thống phân tán; **dữ liệu vật lý không biến mất ngay**. Replica đã offline có thể còn dữ liệu cũ, và writer trước khi xóa có thể còn request đang thực thi. Việc **tiếp tục tăng đúng khóa cũ ngay sau DELETE** không có ngữ nghĩa giống tạo một counter chưa từng được sử dụng.

**Nguyên tắc vòng đời:** sau khi một counter được đánh dấu **retired**, hãy coi khóa của nó là lịch sử, **không tái sử dụng để bắt đầu phép đếm mới**.

## 6. Tình huống xóa và tạo lại gây rủi ro

Giả sử counter `K=(tenant A, tháng 11, G1, page_view)` có giá trị 100:

~~~text
T0: Các replica đang giữ trạng thái counter K.
T1: Một replica chậm/offline hoặc chưa nhận mutation mới.
T2: Ứng dụng DELETE K rồi cho rằng số đếm đã reset.
T3: Một writer cũ gửi UPDATE K SET total = total + 1.
T4: Replica cũ trở lại và dữ liệu xóa/counter được hòa giải.

Không được mặc định rằng SELECT K sẽ luôn cho 1.
~~~

Cassandra quản lý trạng thái counter dưới dạng các **counter shards** và metadata phù hợp với thuật toán/phiên bản. Xóa không phải thao tác nguyên tử “đặt 0 rồi khóa mọi increment trước đó”. Replica chậm, repair và những lệnh retry có thể khiến vòng đời khó dự đoán.

**Không giải quyết bằng cách ngủ vài giây rồi tăng lại cùng khóa.** Cần một thế hệ mới, chính sách dành cho writer cũ và quy trình đối soát nếu số đếm quan trọng.

## 7. Reset bằng cách trừ giá trị đọc được cũng có race

Một cách tiếp cận sai:

~~~text
T0: SELECT total -> 100.
T1: Writer khác gửi UPDATE total = total + 10.
T2: Reset job gửi UPDATE total = total - 100.
T3: Counter có thể là 10, không phải 0.
~~~

Nếu T2 bị timeout rồi reset job retry `-100`, tổng có thể bị trừ thêm lần nữa. Trừ là **thêm một delta**, không phải compare-and-set. Không có phép đọc-trừ nguyên tử chống writer đồng thời.

Muốn “từ thời điểm reset R trở đi đếm từ đầu”, **đổi thế hệ** là cách biểu đạt đúng hơn việc cố ép một counter thành 0.

## 8. Generation/epoch: tạo số đếm mới bằng khóa mới

Ta đặt định danh generation vào partition key. Khi mở kỳ mới, metadata trỏ sang một UUID khác:

~~~text
Tenant A, tháng 11/2026
    Generation G1 -> tổng cũ (có thể đang chờ dọn)

Reset ở thời điểm R:
    Metadata active_generation = G2
    Generation G2 -> chưa có row, API hiển thị 0
    Increment mới -> chỉ nhắm G2

G1 không được tái sử dụng cho một lần reset khác.
~~~

Lợi ích:

- **Counter shards của G1 không thể hòa vào hàng G2**, vì primary key khác nhau.
- Reader chọn G2 để trả **số hiện tại**, trong khi G1 được giữ cho đối soát nếu cần.
- Retention job có thể dọn G1 sau khi hoàn tất quy trình cutover/drain.
- Việc reset có một **dấu mốc phiên bản** để truy vết.

Điểm đánh đổi: ứng dụng phải duy trì **metadata active generation**, xử lý writer đến muộn và điều phối hai lần ghi nếu nghiệp vụ yêu cầu độ chính xác cao.

## 9. Metadata active generation ở bảng thường

Không đặt `active_generation` dạng UUID thường trong cùng bảng counter. Thay bằng bảng **không-counter**:

~~~sql
CREATE TABLE IF NOT EXISTS metrics_ks.active_counter_generations (
    tenant_id          uuid,
    month_bucket       date,
    active_generation  uuid,
    changed_at         timestamp,
    PRIMARY KEY ((tenant_id, month_bucket))
);
~~~

Khởi tạo thế hệ cho một tháng/tenant:

~~~sql
INSERT INTO metrics_ks.active_counter_generations (
    tenant_id, month_bucket, active_generation, changed_at
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Vì bảng này là bảng thường, có thể dùng **lightweight transaction (LWT)** với `IF NOT EXISTS`. Cần kiểm tra kết quả `[applied]`:

- Nếu `applied=true`, generation đã được khởi tạo theo request này.
- Nếu `applied=false`, một writer khác có thể đã tạo metadata. Đọc lại `active_generation` và dùng generation hiện hành.
- Nếu client timeout, kết quả có thể chưa chắc chắn; không suy ra lần insert trước chưa xảy ra.

Không dùng `INSERT IF NOT EXISTS` để khởi tạo **giá trị counter**: counter không có cú pháp gán số tuyệt đối.

Đọc metadata:

~~~sql
SELECT active_generation
FROM metrics_ks.active_counter_generations
WHERE tenant_id = ?
  AND month_bucket = ?;
~~~

## 10. Chuyển generation bằng conditional update

Tạo UUID G2 mới và chỉ chuyển metadata khi G1 vẫn là thế hệ hiện tại:

~~~sql
UPDATE metrics_ks.active_counter_generations
SET active_generation = ?, changed_at = ?
WHERE tenant_id = ?
  AND month_bucket = ?
IF active_generation = ?;
~~~

Điều kiện ở cuối bind với **G1 dự kiến**. LWT giúp các reset job cạnh tranh không tự ghi đè metadata một cách mù quáng.

**Nhưng LWT metadata không khóa counter update** ở bảng khác:

~~~text
Writer A đọc active_generation = G1.
Reset job chuyển metadata từ G1 sang G2.
Writer A gửi increment vào counter G1.
Reader mới chỉ đọc G2.
~~~

Writer A vẫn có thể ghi vào **G1** vì counter update không thuộc cùng conditional transaction. Đổi generation giúp **cách ly tổng mới**, không tự đảm bảo mọi event đã được tính vào đúng một thế hệ.

### Giao thức cutover có kiểm soát

1. Xác định mốc reset và thông báo đóng nhận các lệnh thuộc thế hệ G1.
2. Dừng/giảm writer hoặc đặt trạng thái chuyển tiếp trong hệ thống điều phối.
3. Chờ request đang bay được xử lý hoặc ghi nhận để replay/đối soát.
4. Dùng LWT chuyển metadata active từ G1 sang G2.
5. Cho phép writer mới dùng G2; xử lý event cũ theo policy, không tự chuyển nó sang G2 tùy tiện.
6. Sau khi đối soát và hết retention, mới dọn G1.

Nếu nghiệp vụ yêu cầu **không mất một event nào quanh mốc reset**, cần event log/ledger hoặc giao thức fencing thực sự. Chỉ kiểm tra generation trước mỗi update vẫn có race giữa kiểm tra và ghi.

## 11. Fencing token và writer đã cầm generation cũ

Một command nên có định danh ổn định:

~~~json
{
  "requestId": "9c53e4bc-9cbe-4f34-8a2e-ff1e64d117ae",
  "tenantId": "550e8400-e29b-41d4-a716-446655440000",
  "month": "2026-11-01",
  "generation": "68f81234-8a2e-4f34-8a2e-ff1e64d117ae",
  "metricName": "page_view",
  "delta": 1
}
~~~

Generation trong command làm rõ **lệnh này thuộc thế hệ nào**; sau cutover, service có thể từ chối/quarantine các command còn nhắm G1. Nhưng cần hiểu:

- Cassandra **không tự so metadata active_generation** khi nhận một counter UPDATE.
- Nếu writer kiểm tra metadata G1 rồi G2 được kích hoạt ngay sau đó, writer vẫn có thể cập nhật G1.
- Cần phối hợp queue, writer leases, drain hoặc một sự kiện có ID để đối soát.
- Một service bị restart có thể dùng cache active_generation cũ; cache phải có chính sách làm mới/invalidate.

**Không quảng bá “LWT metadata + UPDATE counter = một giao dịch nguyên tử”.** Đây là hai thao tác riêng với failure window.

## 12. Java Driver 4.x: cộng, trừ, đọc counter

Giả sử Spring Boot quản lý một bean `CqlSession`. DAO sau chuẩn bị mẫu CQL một lần:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class CounterDao {
    private final CqlSession session;
    private final PreparedStatement plus;
    private final PreparedStatement minus;
    private final PreparedStatement select;

    public CounterDao(CqlSession session) {
        this.session = session;
        this.plus = session.prepare("""
            UPDATE metrics_ks.metric_counters_by_month
            SET total = total + ?
            WHERE tenant_id = ? AND month_bucket = ?
              AND generation_id = ? AND metric_name = ?
            """);
        this.minus = session.prepare("""
            UPDATE metrics_ks.metric_counters_by_month
            SET total = total - ?
            WHERE tenant_id = ? AND month_bucket = ?
              AND generation_id = ? AND metric_name = ?
            """);
        this.select = session.prepare("""
            SELECT total FROM metrics_ks.metric_counters_by_month
            WHERE tenant_id = ? AND month_bucket = ?
              AND generation_id = ? AND metric_name = ?
            """);
    }

    public void add(UUID tenant, LocalDate month, UUID generation,
                    String metric, long delta) {
        if (delta <= 0) throw new IllegalArgumentException("delta");
        BoundStatement statement = plus.bind(
            delta, tenant, month, generation, metric
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotent(false);
        session.execute(statement);
    }

    public void subtract(UUID tenant, LocalDate month, UUID generation,
                         String metric, long delta) {
        if (delta <= 0) throw new IllegalArgumentException("delta");
        BoundStatement statement = minus.bind(
            delta, tenant, month, generation, metric
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotent(false);
        session.execute(statement);
    }

    public long readOrZero(UUID tenant, LocalDate month,
                           UUID generation, String metric) {
        ResultSet result = session.execute(
            select.bind(tenant, month, generation, metric)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        );
        Row row = result.one();
        return row == null || row.isNull("total")
            ? 0L : row.getLong("total");
    }
}
~~~

Giải thích:

- `PreparedStatement` tái sử dụng mẫu CQL; mỗi request tạo `BoundStatement` riêng.
- `setIdempotent(false)` đúng cho increment/decrement: một delta bị thực thi hai lần **không còn cùng kết quả**.
- `LOCAL_QUORUM` chỉ là CL minh họa cho RF cục bộ phù hợp; không biến increment thành exactly-once.
- `readOrZero` trả 0 cho trường hợp chưa có hàng **theo policy ứng dụng**, không tạo một counter có giá trị 0 trong database.
- Code chưa bao gồm xác thực tenant, kiểm soát tên metric, generation metadata, deadline/retry và đối soát: phải bổ sung tại service.

## 13. Spring Data Cassandra: dùng @Query để cập nhật delta

Spring Data Cassandra hỗ trợ viết câu CQL tường minh trong repository. Với **counter update**, cần chắc chắn rằng câu lệnh sinh ra có dạng `SET total = total + ?` hoặc `SET total = total - ?`, **không phải gán giá trị tuyệt đối**.

~~~java
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Modifying;
import org.springframework.data.cassandra.repository.Query;

public interface MetricCounterRepository
        extends CassandraRepository<MetricCounterRow, MetricCounterKey> {

    @Modifying
    @Query("""
        UPDATE metric_counters_by_month
        SET total = total + ?0
        WHERE tenant_id = ?1 AND month_bucket = ?2
          AND generation_id = ?3 AND metric_name = ?4
        """)
    void increment(long delta, UUID tenantId,
                   LocalDate month, UUID generation,
                   String metricName);

    @Modifying
    @Query("""
        UPDATE metric_counters_by_month
        SET total = total - ?0
        WHERE tenant_id = ?1 AND month_bucket = ?2
          AND generation_id = ?3 AND metric_name = ?4
        """)
    void decrement(long delta, UUID tenantId,
                   LocalDate month, UUID generation,
                   String metricName);
}
~~~

Ví dụ dùng Java text block (Java 15+) và giả định keyspace mặc định là `metrics_ks`. Các API/overload của Spring Data Cassandra phải được kiểm chứng theo version, đặc biệt là annotation `@Modifying` và cách bind.

Trách nhiệm service khi gọi method:

1. Validate `delta > 0` và giới hạn kích thước delta để tránh overflow/giá trị vô lý.
2. Đọc/xác định **generation đúng** rồi gắn vào command.
3. Không áp dụng retry mù quáng; kết quả timeout là **chưa biết**, không phải chắc chắn chưa tăng.
4. Không gọi repository như một bộ đếm có transaction isolation hay exactly-once.
5. Ghi nhật ký/metrics bằng request ID thích hợp, nhưng tránh log dữ liệu nhạy cảm.

## 14. Entity mapping và vì sao save() không phải reset

Một entity để đọc/mapping có thể được khai báo:

~~~java
@PrimaryKeyClass
public class MetricCounterKey implements Serializable {
    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "month_bucket", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate monthBucket;

    @PrimaryKeyColumn(name = "generation_id", ordinal = 2,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID generationId;

    @PrimaryKeyColumn(name = "metric_name", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED)
    private String metricName;

    // Constructor/getters/setters/equals/hashCode.
}

@Table("metric_counters_by_month")
public class MetricCounterRow {
    @PrimaryKey
    private MetricCounterKey key;

    @Column("total")
    private Long total;

    // Constructor/getters/setters.
}
~~~

Ví dụ trên lược bỏ import `Serializable`, `UUID`, `LocalDate`, các annotation mapping và boilerplate; hai public class phải đặt ở các file Java phù hợp. `@PrimaryKeyClass` cần metadata và equality nhất quán với schema.

**Không dùng `repository.save(counterEntity)` hoặc `CassandraTemplate.insert(counterEntity)` để “tạo counter bằng 0”**. Các thao tác mapped entity thông thường có thể sinh `INSERT` hoặc một phép gán scalar, không phải cú pháp counter update hợp lệ.

`CassandraTemplate` rất hữu ích cho entity mapping và các truy vấn Cassandra thông thường, nhưng **không làm thay đổi luật CQL của counter**. Với các delta, dùng `@Query`/`@Modifying`, `CqlTemplate` với CQL rõ ràng hoặc trực tiếp `CqlSession`/prepared statement.

### Quy tắc đi qua template

| Việc cần làm | Cách tiếp cận |
| --- | --- |
| Đọc entity `MetricCounterRow` | Repository/template mapping nếu version hỗ trợ |
| Tăng counter +5 | CQL `UPDATE total = total + 5` qua repository annotation/driver |
| Giảm counter -2 | CQL `UPDATE total = total - 2` qua repository annotation/driver |
| Chuyển active generation | LWT ở **bảng metadata không-counter** |
| Reset counter về 0 | **Đổi generation**; không `save(entity)` với total=0 |
| Dọn dữ liệu cũ | Row/partition DELETE theo retention, không tái sử dụng key |

## 15. Counter không hỗ trợ TTL, TIMESTAMP và LWT như scalar

Các giới hạn cần ghi nhớ:

| Tính năng | Counter |
| --- | --- |
| `UPDATE total = total + delta` | Có |
| `UPDATE total = total - delta` | Có |
| `SET total = 0` | Không |
| `INSERT` trực tiếp có giá trị counter | Không |
| `USING TTL` cho counter update | Không |
| `USING TIMESTAMP` cho counter update | Không |
| Bảng có `default_time_to_live > 0` để hết hạn counter | Không phù hợp/không hỗ trợ |
| Thêm cột thường cạnh counter ngoài primary key | Không |
| Dùng counter như điều kiện `IF total = ...` trong LWT | Không |
| Index lên cột counter như scalar thường | Không |
| Row/partition DELETE hợp lệ | Có, nhưng không phải reset để tái dùng khóa |

Đừng sử dụng `TTL(total)` hay `WRITETIME(total)` theo suy luận từ cột scalar để xây chính sách retention. Counter có cơ chế lưu và cập nhật khác; không có thời hạn sống theo cell qua `USING TTL`.

**Hệ quả thiết kế:** một counter được giữ bao lâu do **khóa bucket, reader policy và retention job** quyết định, không được tự động hết hạn sau số giây như event row có TTL.

## 16. Retention theo bucket: thay TTL bằng vòng đời rõ ràng

Ví dụ chỉ cần thống kê 12 tháng gần nhất:

~~~text
Writer -> xác định month_bucket từ event time/ingest time
       -> lấy active_generation của tenant/tháng
       -> gửi delta tới counter cùng khóa thế hệ

Reader -> giới hạn khoảng 12 tháng, không quét toàn bộ bảng
       -> lấy active_generation của từng tháng
       -> SELECT counter theo các partition tương ứng

Retention job -> đóng kỳ cũ
              -> drain/reconcile request đang bay
              -> archive tổng/ledger nếu cần
              -> DELETE các partition generation đã retired
              -> theo dõi tombstone, repair, compaction
~~~

**Time bucket không tự xóa dữ liệu.** Nó giúp định tuyến và giới hạn phạm vi đọc, còn job retention xác định thời điểm xóa.

Trước khi xóa:

- Đã định nghĩa “12 tháng” theo **UTC hay timezone nghiệp vụ**, cùng quy tắc ở writer/reader.
- Không còn writer hoặc queue consumer hợp lệ gửi delta cho kỳ/generation chuẩn bị xóa.
- Có bản tổng hợp hoặc nguồn dữ liệu đủ để rebuild nếu cần kiểm toán.
- Đã kiểm tra ảnh hưởng của DELETE tới tombstone, replica health và compaction.
- Snapshot, backup, export và mục tiêu tuân thủ dữ liệu có vòng đời riêng.

Nếu yêu cầu “giữ counter 7 ngày rồi tự hết hạn” là bất biến, cân nhắc **bảng dữ liệu thường có TTL và aggregation** thay vì ép counter làm điều nó không hỗ trợ.

## 17. Tombstone, gc_grace_seconds và repair sau khi xóa

`DELETE` đánh dấu dữ liệu không còn sống; Cassandra cần giữ thông tin xóa đủ lâu để replica từng offline không đưa trạng thái cũ trở lại. Việc loại bỏ thông tin xóa liên quan đến `gc_grace_seconds`, compaction, repair và topology.

~~~text
Replica A, B: đã nhận DELETE counter của generation G1.
Replica C: offline, còn trạng thái G1 cũ.

Nếu tombstone bị dọn quá sớm và replica C trở lại
với bản dữ liệu chưa nhận xóa, có nguy cơ trạng thái
đã xóa xuất hiện trở lại khi dữ liệu được hòa giải.
~~~

Với counter, những **counter shards** và các delta không idempotent khiến việc tái sử dụng khóa cũ càng khó dự đoán. Không lấy một lần SELECT rỗng ngay sau DELETE làm bằng chứng dữ liệu đã được xóa ở **mọi replica và mọi bản lưu**.

**Không tự đặt `gc_grace_seconds = 0` để xóa nhanh.** Cần xem phiên bản Cassandra, chiến lược repair/anti-entropy, thời gian replica offline, replication và quy trình vận hành trước khi thay đổi. Backup/snapshot có thể còn dữ liệu vật lý sau khi dữ liệu sống không còn được API trả về.

### Giới hạn thao tác dọn

Một job xóa hàng triệu counter cũ với tốc độ cao có thể tạo áp lực tombstone, I/O và compaction. Hãy:

1. Chọn partition/generation đã hết hạn dựa trên metadata.
2. Giới hạn số partition xóa mỗi vòng và concurrency.
3. Dừng hoặc giảm tốc khi p95/p99 và pending compaction tăng.
4. Theo dõi repair/replica state và khả năng phục hồi.
5. Không tái sử dụng `generation_id` của dữ liệu đã xóa.

## 18. Retry: +1 không idempotent

Một tình huống timeout:

~~~text
T0: Tổng quan sát được = 10.
T1: Client gửi UPDATE total = total + 1.
T2: Một số replica áp dụng delta; response bị mất.
T3: Client timeout và retry +1.
T4: Tổng có thể trở thành 12 thay vì 11.
~~~

**Cùng lệnh CQL, cùng primary key, cùng delta** vẫn không làm phép cộng trở thành idempotent: thực hiện hai lần cho hiệu ứng khác thực hiện một lần.

Trong Java Driver, đặt:

~~~java
BoundStatement update = preparedCounterUpdate.bind(
    1L, tenantId, month, generationId, metricName
).setIdempotent(false);

session.execute(update);
~~~

Cờ `setIdempotent(false)` cho driver thông tin để quyết định một số hành vi retry/speculative execution. **Nó không chặn các tầng khác tự retry**: HTTP client, gateway, Spring service hay queue consumer vẫn có thể gửi lại mutation.

Khi counter update timeout, **đọc lại tổng không đủ để nhận diện delta nào đã áp dụng**, vì nhiều writer có thể đồng thời cập nhật tổng. Nếu phép đếm phải chính xác, cần event log/dedup/reconciliation.

## 19. Vì sao bảng dedup riêng không tự đạt exactly-once?

Một thiết kế tưởng như hoàn hảo:

~~~text
1. INSERT request_id vào bảng ledger IF NOT EXISTS.
2. Nếu applied=true thì UPDATE counter total = total + 1.
~~~

Nhưng hai bảng không có giao dịch ACID chung:

- Bước 1 thành công, process crash **trước bước 2**: ledger đã ghi request nhưng counter chưa tăng.
- Bước 2 thành công, process crash trước khi ghi kết quả hoàn tất: hệ thống không biết counter đã tăng hay chưa.
- Retry có thể bị dedup chặn hoặc lặp delta tùy state machine, làm thiếu/thừa số đếm.

**LWT của bảng ledger không tự bao bọc một counter mutation ở bảng khác.**

Nếu yêu cầu số đếm chính xác:

1. Ghi **event có ID duy nhất** làm nguồn sự thật.
2. Xây pipeline tổng hợp idempotent từ event log/ledger có checkpoint.
3. Coi counter là **materialized metric** có thể được đối soát, sửa hoặc rebuild.
4. Có state machine cho event đã nhận, đang tổng hợp, đã hoàn tất, cần xử lý lại.

Đối với tiền, hạn mức cứng hoặc dữ liệu pháp lý cần tính đúng tuyệt đối, không chỉ dùng Cassandra counter.

## 20. COUNTER BATCH không tạo ra reset hay exactly-once

Cassandra có cú pháp batch riêng cho counter:

~~~sql
BEGIN COUNTER BATCH
    UPDATE metrics_ks.metric_counters_by_month
    SET total = total + 1
    WHERE tenant_id = ? AND month_bucket = ?
      AND generation_id = ? AND metric_name = ?;

    UPDATE metrics_ks.metric_counters_by_month
    SET total = total + 2
    WHERE tenant_id = ? AND month_bucket = ?
      AND generation_id = ? AND metric_name = ?;
APPLY BATCH;
~~~

Không trộn counter mutation và mutation scalar thường vào một batch. Counter batch **không biến increment thành idempotent**, cũng không cung cấp phép reset về 0.

Java Driver 4.x:

~~~java
BatchStatement batch =
    BatchStatement.builder(DefaultBatchType.COUNTER)
        .addStatement(firstCounterUpdate)
        .addStatement(secondCounterUpdate)
        .setIdempotent(false)
        .build();

session.execute(batch);
~~~

Đoạn mã giả định `firstCounterUpdate`/`secondCounterUpdate` là bound statements của các **counter UPDATE** hợp lệ; cần import `BatchStatement`/`DefaultBatchType` và giới hạn số thao tác. Không dùng counter batch lớn chỉ để tăng bulk throughput hoặc giả định có isolation đa partition như SQL transaction.

## 21. Consistency level không sửa lỗi ngữ nghĩa counter

Với RF=3 trong một DC, `LOCAL_QUORUM` cần đa số replica cục bộ phản hồi cho request tương ứng. Nhưng:

- `LOCAL_QUORUM` không ngăn increment bị gửi **hai lần**.
- `ALL` không tạo được thao tác `SET total = 0`.
- CL cao hơn không chặn writer cũ nhắm generation G1 sau khi đã chuyển active sang G2.
- Thành công theo CL không có nghĩa tất cả backup/snapshot hoặc replica xa đã ở cùng trạng thái.
- Một giá trị tổng quan sát được không chỉ ra ID của từng event đã được đếm.

Chọn CL theo yêu cầu độ trễ và tính sẵn sàng, nhưng cần **generation protocol, idempotency/reconciliation và dữ liệu theo partition** riêng.

### Counter rất nóng và sharding

Một metric có hàng chục nghìn update/giây có thể tạo hot partition và contention. Nếu benchmark cho thấy nút thắt, có thể chia thành nhiều **shards**:

~~~sql
CREATE TABLE metrics_ks.sharded_metric_counters (
    tenant_id     uuid,
    month_bucket  date,
    generation_id uuid,
    metric_name   text,
    shard_id      int,
    total         counter,
    PRIMARY KEY (
        (tenant_id, month_bucket, generation_id, metric_name, shard_id)
    )
);
~~~

Một event được phân phối vào một shard bằng quy tắc ổn định. Reader phải tính:

~~~text
logicalTotal = total(shard0) + total(shard1) + ... + total(shardN)
~~~

Đọc nhiều shard có thêm fan-out và chi phí merge; phải xử lý shard chưa có hàng, áp dụng cùng generation và giới hạn số shard. **Sharding phân phối tải, không giải quyết retry double count**. Khi reset, đổi generation **cho toàn bộ tập shard**, không trừ từng shard về 0.

## 22. Quy trình vận hành generation cũ

Một vòng đời dễ kiểm tra:

~~~text
ACTIVE (G1)
  |
  v
QUIESCING (đóng/dừng writer cũ)
  |
  v
CUTOVER (metadata G1 -> G2)
  |
  v
DRAINED (xử lý command đang bay của G1)
  |
  v
ARCHIVED (lưu summary/ledger nếu cần)
  |
  v
RETIRED (không còn phục vụ API hiện tại)
  |
  v
DELETED (xóa G1 theo retention)
  |
  v
COMPACTED (thu hồi vật lý khi điều kiện an toàn)
~~~

Đây là **state machine của service/vận hành**, không phải những trạng thái Cassandra tự sinh. Nếu muốn lưu trạng thái `QUIESCING`, `DRAINED`, `ARCHIVED` thì dùng **bảng metadata thường**, không thêm cột scalar vào bảng counter.

Giữa cutover và dọn, có thể giữ G1 ở chế độ **đọc phục vụ đối soát**, nhưng phải rõ reader nào được phép đọc nó. Không cho API “current counter” vô tình cộng G1 với G2 nếu ý nghĩa reset là **bắt đầu lại từ 0**.

## 23. Khi nào nên chọn thiết kế không-counter?

| Nhu cầu | Hướng thay thế |
| --- | --- |
| Chỉ số có thể sai lệch nhỏ và tái tính | Counter + generation + đối soát |
| Đếm event duy nhất chính xác | Event table có event ID ổn định; tổng hợp có dedup |
| Cần dữ liệu tự hết hạn bằng TTL | Bảng thường lưu events/tổng hợp, TTL theo policy |
| Cần `SET count = 100` | Cột `bigint` thường với concurrency control thích hợp |
| Cần CAS “chỉ tăng nếu tổng dưới 100” | Bảng thường với LWT/thiết kế hạn mức phù hợp |
| Cần reset nguyên tử tại một thời điểm chính xác | Giao thức generation/fencing hoặc ledger có thứ tự |
| Cần throughput cực cao trên một metric | Cân nhắc shard/stream aggregation và chi phí read |

Tên dữ liệu là “count” **không đủ để quyết định dùng kiểu `counter`**. Hãy xác định yêu cầu *chính xác, tuần tự, retention, khả năng tái tính và mức chịu lỗi* trước.

## 24. Kiểm thử vòng đời và tình huống lỗi

Chạy trên cluster test có Cassandra/driver tương thích. Không chủ động làm down node production để thử tombstone.

| Trường hợp | Cách thử | Kỳ vọng |
| --- | --- | --- |
| Generation mới | Tạo metadata G1, SELECT trước lần increment | Có thể chưa có row; API hiển thị 0 theo policy |
| Increment và decrement | Gửi +3 rồi -1 | Tổng logic phản ánh delta khi không có race |
| Retry +1 | Gửi cùng increment hai lần | Tổng tăng hai lần, không idempotent |
| CQL không hợp lệ | `SET total=0`, `INSERT`, `USING TTL` | Cassandra từ chối thao tác không hỗ trợ |
| Delete cũ | Ghi G1, chuyển active G2, xóa G1 | Reader hiện tại chỉ dùng G2 |
| Writer giữ G1 | Cutover khi có request đang bay | Không trộn G1 vào G2; có chính sách late event |
| Reset đồng thời | Hai tác vụ cùng `IF active_generation=G1` | Chỉ một kết quả cutover được áp dụng |
| Timeout | Mất phản hồi sau UPDATE +1 | Không coi timeout là chưa ghi; có đối soát |
| Replica offline | Thử delete/repair trên môi trường test | Quan sát tombstone và chính sách đồng bộ |
| Sharded counter | Ghi nhiều shard, đọc tổng | Chỉ cộng shard thuộc đúng generation |

Truy vấn kiểm tra:

~~~sql
SELECT metric_name, total
FROM metrics_ks.metric_counters_by_month
WHERE tenant_id = ?
  AND month_bucket = ?
  AND generation_id = ?;
~~~

Theo dõi **counter update latency p95/p99, timeout/unavailable, retry rate, số command lệch generation, số reset conflicts, partition size, repair health, tombstone và compaction**. Không log payload nhạy cảm hay toàn bộ ID khách hàng trong production nếu không cần.

## 25. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `SET total=0` để reset | CQL counter không chấp nhận gán scalar | Dùng generation mới |
| DELETE rồi +1 trên cùng key | Replica cũ/writer cũ làm vòng đời không an toàn | Không tái sử dụng key retired |
| Đọc rồi trừ số vừa đọc | Race và retry phép trừ | Không dùng read-modify-write để reset |
| Dùng TTL/TIMESTAMP như cột thường | Counter không hỗ trợ | Bucket, retention job và metadata |
| `repository.save(entity)` để tạo counter | Có thể sinh INSERT/set absolute không hợp lệ | `@Query`/driver UPDATE delta |
| Bật retry +1 khắp nơi | Double count khi response mất | Giới hạn retry, đối soát, idempotent=false |
| Tin LWT metadata khóa mọi counter update | Cross-table không atomic | Drain/fencing/ledger |
| Cắt generation G1 rồi đọc cộng G1+G2 | Sai ý nghĩa reset | Reader chỉ lấy generation hiện hành |
| Hạ `gc_grace_seconds` tùy tiện | Nguy cơ phục hồi dữ liệu đã xóa | Repair/compaction policy phù hợp |
| Dùng counter cho số dư thanh toán | Không bảo đảm exactly-once | Ledger/transaction phù hợp |
| Shard rồi tưởng retry an toàn | Delta vẫn không idempotent | Sharding chỉ giải quyết contention |

## 26. Checklist trước production

- [ ] Chọn counter vì nhu cầu **tăng/giảm** và chấp nhận được những giới hạn chính xác.
- [ ] Bảng counter chỉ chứa primary-key columns và counter columns.
- [ ] Không dùng INSERT, SET absolute, TTL hoặc USING TIMESTAMP với counter.
- [ ] Dùng `UPDATE total=total +/- delta` có bind parameters và validation.
- [ ] Có `generation_id`/epoch nếu cần reset hoặc tạo lại counter.
- [ ] Metadata active generation ở bảng thường; LWT nếu reset cạnh tranh.
- [ ] Hiểu rằng LWT metadata **không atomic** với counter update.
- [ ] Có quy trình quiesce/drain và xử lý in-flight command lúc cutover.
- [ ] Không sử dụng lại key đã DELETE/retired.
- [ ] Có retention/archive/repair/snapshot policy cho dữ liệu cũ.
- [ ] Driver và các tầng HTTP/queue/service thống nhất retry semantics.
- [ ] Không coi một lần đọc tổng là bằng chứng mỗi event được tính đúng một lần.
- [ ] Có ledger/reconciliation khi số liệu phải chính xác.
- [ ] Đã đo contention, throughput, độ trễ, sharding và chi phí đọc.
- [ ] Đã kiểm thử timeout, reset đồng thời và replica lag trên cluster test.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `UPDATE ... SET total = 0` không dùng được để reset counter?

**Đáp án:** Counter chỉ hỗ trợ cộng/trừ, không gán giá trị tuyệt đối như `bigint` thông thường.

**Câu 2.** DELETE counter rồi dùng ngay lại cùng primary key có tương đương tạo counter mới?

**Đáp án:** Không. Replica, counter shards, tombstone và writer cũ có thể ảnh hưởng; nên dùng **generation mới với khóa mới**.

**Câu 3.** Tại sao trừ bằng tổng đã đọc không phải reset nguyên tử?

**Đáp án:** Có race giữa đọc và ghi; retry phép trừ cũng có thể trừ lặp.

**Câu 4.** Làm sao tạo số đếm mới có giá trị hiển thị ban đầu bằng 0?

**Đáp án:** Đổi `generation_id`, chưa cần tạo row counter; API quy ước không có hàng nghĩa là tổng hiển thị bằng 0.

**Câu 5.** `IF active_generation=G1` có khóa counter update trên G1 không?

**Đáp án:** Không. Nó chỉ điều kiện hóa mutation trên bảng metadata; counter update là thao tác riêng.

**Câu 6.** Vì sao retry +1 sau timeout có thể đếm đôi?

**Đáp án:** Lần đầu có thể đã được áp dụng nhưng phản hồi bị mất. Cộng lần thứ hai làm số đếm tăng thêm.

**Câu 7.** Có thể dùng `USING TTL 2592000` cho counter để tự hết hạn 30 ngày?

**Đáp án:** Không. Cần time bucket, metadata/retention job hoặc một mô hình bảng thường có TTL.

**Câu 8.** Cờ `setIdempotent(false)` có bảo đảm HTTP client không gửi lại command không?

**Đáp án:** Không. Cờ này cung cấp thông tin cho driver; các tầng ứng dụng và queue vẫn có thể retry.

**Câu 9.** Sharded counters có giải quyết được exactly-once không?

**Đáp án:** Không. Shard phân phối tải; mỗi delta vẫn không idempotent, cần ledger/reconciliation.

**Câu 10.** Vì sao phải quan tâm repair và `gc_grace_seconds` khi DELETE thế hệ cũ?

**Đáp án:** Replica offline có thể giữ dữ liệu cũ; dọn tombstone quá sớm có rủi ro dữ liệu đã xóa xuất hiện lại.

---

**Ghi nhớ:** Cassandra `counter` là **phép cộng/trừ phân tán**, không phải scalar có thể `INSERT`, `SET 0` hoặc `TTL` tùy ý. **DELETE không phải reset an toàn để tái sử dụng cùng khóa**. Khi cần bắt đầu chu kỳ đếm mới, hãy tạo **generation/epoch mới trong partition key**, cập nhật metadata active có kiểm soát, phối hợp writer cũ và chỉ dọn thế hệ đã retired sau khi đối soát. Với Spring Data Cassandra, dùng `@Query` hoặc Java Driver cho `UPDATE total = total +/- delta`, không retry counter một cách mù quáng và không dùng counter làm nguồn sự thật duy nhất cho nghiệp vụ đòi **exactly-once**.
