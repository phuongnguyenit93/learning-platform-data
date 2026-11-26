# Deadlock khi cập nhật đồng thời trong Spring Batch

## Mục tiêu bài học

Khi một Spring Batch job chuyển từ một luồng sang multi-threaded step, parallel steps, local partitioning hoặc nhiều worker JVM, các giao dịch ghi database có thể chạy **đồng thời**. Một job xử lý tuần tự vốn hoạt động ổn định có thể bắt đầu báo lỗi deadlock, rollback chunk, retry liên tục hoặc mất SLA khi nhiều worker cùng cập nhật một nhóm bản ghi.

**Deadlock khi cập nhật đồng thời** là tình trạng các transaction giữ những khóa mà transaction khác đang cần và tạo thành một **vòng phụ thuộc chờ**, khiến không transaction nào trong vòng có thể tự tiến triển. Database thường phải phát hiện và hủy một transaction để phá vòng chờ. Đây không đơn thuần là “database chậm” và cũng không được khắc phục chắc chắn bằng cách tăng JDBC connection pool.

Bài thuộc chương **Database scaling**, module **SPRING_BATCH_SCALING_OPERATIONS**. Phạm vi module là mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; đồng thời học cách đo bottleneck, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc phù hợp tài nguyên thực tế.

Sau bài học, bạn có thể:

- Phân biệt **deadlock**, lock wait, lock timeout, serialization failure và optimistic locking conflict.
- Dùng wait-for graph để giải thích vì sao hai worker cùng UPDATE có thể khóa chéo.
- Hiểu cách row locks, index, foreign key, uniqueness và isolation level ảnh hưởng deadlock.
- Nhận diện rủi ro trong chunk transaction, partition overlap và hot-row contention.
- Thiết kế **thứ tự cập nhật nhất quán**, transaction ngắn và ranh giới dữ liệu rõ.
- Cấu hình retry/backoff tại **đúng transaction boundary** trong Spring Batch 5.x.
- Tránh nhầm retry với skip, restart và idempotency; bảo vệ side effect khi retry.
- Tạo kịch bản tái hiện deadlock với hai database sessions và integration test.
- Dùng log/metric/DB diagnostic để điều tra và giảm deadlock mà không đánh đổi tính đúng dữ liệu.

## 1. Deadlock là gì?

Giả sử một batch xử lý nghiệp vụ cần cập nhật cả hai bản ghi `account_id=10` và `account_id=20`:

~~~text
Transaction A:
  giữ khóa account 10
  chờ khóa account 20

Transaction B:
  giữ khóa account 20
  chờ khóa account 10
~~~

Không transaction nào có thể nhả khóa trước khi kết thúc, trong khi cả hai đang chờ nhau.

~~~mermaid
flowchart LR
    A["Tx A giữ row 10"] -->|"Đợi row 20"| B["Tx B giữ row 20"]
    B -->|"Đợi row 10"| A
~~~

Đây là **wait-for cycle**. Trong database có cơ chế phát hiện deadlock, hệ quản trị chọn một transaction làm **victim**, rollback transaction đó hoặc báo lỗi khiến ứng dụng phải rollback. Transaction còn lại có cơ hội tiếp tục.

### Phân biệt với lock wait thông thường

~~~text
Tx A giữ row 10, đang thực thi bình thường
Tx B đợi row 10
Tx A commit → Tx B có thể tiếp tục
~~~

Chờ khóa **không nhất thiết là deadlock** vì không có vòng phụ thuộc. Lock wait trở thành vấn đề khi độ trễ vượt budget hoặc có vòng chờ; hai trường hợp cần biện pháp khác nhau.

## 2. Điều kiện tạo deadlock và wait-for graph

Bốn điều kiện kinh điển thường được dùng để giải thích deadlock tài nguyên:

1. **Mutual exclusion:** tài nguyên/khóa có chế độ không cho những thao tác xung đột cùng sở hữu.
2. **Hold and wait:** transaction đang giữ một khóa trong khi chờ khóa khác.
3. **No preemption:** transaction khác không thể đơn giản lấy lại khóa đang được giữ; cần commit, rollback hoặc cơ chế của DB.
4. **Circular wait:** có chuỗi các transaction chờ nhau tạo thành vòng.

Với database, trọng tâm thực hành là **vòng chờ giữa các lock requests không tương thích**. Nó có thể dài hơn hai transaction.

~~~mermaid
flowchart LR
    T1["Tx 1"] -->|"đợi khóa của"| T2["Tx 2"]
    T2 -->|"đợi khóa của"| T3["Tx 3"]
    T3 -->|"đợi khóa của"| T1
~~~

**Chẩn đoán:** hai transaction đợi cùng một row chưa phải deadlock nếu transaction giữ row đó không đợi ai. Một deadlock cần nhìn **mối quan hệ chờ** chứ không chỉ số lượng sessions bị blocked.

Trong thực tế, DB có thể dùng lock mode khác nhau (row, table, index/key-range, advisory, metadata); không phải mọi chờ đều thể hiện bằng một khóa row duy nhất.

## 3. Tái hiện deadlock bằng hai PostgreSQL sessions

Tạo bảng trong một **database test riêng**:

~~~sql
CREATE TABLE account_balance (
    account_id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);

INSERT INTO account_balance (account_id, balance_cents)
VALUES (10, 100000), (20, 200000);
~~~

Mở **hai kết nối SQL độc lập** (Session A và Session B). Thực hiện xen kẽ các câu sau.

Session A:

~~~sql
BEGIN;

UPDATE account_balance
SET balance_cents = balance_cents - 100
WHERE account_id = 10;
-- Giữ khóa row account_id=10
~~~

Session B:

~~~sql
BEGIN;

UPDATE account_balance
SET balance_cents = balance_cents + 100
WHERE account_id = 20;
-- Giữ khóa row account_id=20
~~~

Tiếp theo, ở Session A:

~~~sql
UPDATE account_balance
SET balance_cents = balance_cents + 100
WHERE account_id = 20;
-- Bị chờ vì Session B đang giữ row 20
~~~

Trong lúc Session A đang chờ, chạy ở Session B:

~~~sql
UPDATE account_balance
SET balance_cents = balance_cents - 100
WHERE account_id = 10;
-- Tạo vòng chờ: A đợi B, B đợi A
~~~

PostgreSQL sẽ phát hiện vòng chờ và báo lỗi deadlock ở **một trong hai** transaction, thường với SQLSTATE `40P01`. Sau lỗi, transaction bị chọn làm victim phải rollback/được giải phóng theo cơ chế driver/transaction manager; transaction còn lại có thể tiếp tục.

### Những lưu ý khi thực hành

- Phải dùng **hai database sessions/transactions**; chạy tuần tự toàn bộ SQL trên một connection sẽ không tái hiện được tình huống.
- Không thực hiện trên production; có thể gây lock wait cho workload thật.
- Đừng kỳ vọng Session A luôn bị chọn làm victim. Database quyết định dựa trên trạng thái và thuật toán phát hiện.
- Nếu câu SQL bị timeout trước khi detector báo deadlock, có thể nhận lỗi timeout thay vì `40P01`.
- Sau khi một transaction nhận lỗi, cần xử lý rollback rồi mới thử lại toàn **đơn vị transaction** phù hợp.
- Hai lệnh UPDATE mang dữ liệu thật sẽ khiến chỉ transaction còn commit được có tác dụng; sau thử nghiệm cần reset fixture hoặc rollback đúng cách.

## 4. Deadlock khác những lỗi concurrency nào?

| Hiện tượng | Đặc điểm | Hướng xử lý |
| --- | --- | --- |
| **Deadlock** | Có vòng chờ khóa; DB chọn victim | Sửa lock order/transaction, retry toàn transaction theo policy |
| **Lock wait** | Đang chờ nhưng transaction giữ khóa có thể hoàn tất | Giảm lock duration, đo SQL và contention |
| **Lock timeout** | Chờ vượt hạn; chưa chắc có vòng chờ | Điều tra blocker, timeout/transaction sizing |
| **Serialization failure** | DB không thể bảo đảm tính serializable cho lịch thực thi | Retry transaction với dữ liệu/side effect an toàn |
| **Optimistic locking conflict** | Version đã đổi trước khi UPDATE | Xử lý tranh chấp phiên bản theo business policy |
| **Unique constraint violation** | Hai request tạo key giống nhau | Xử lý trùng khóa/idempotency; không retry mù |
| **Connection acquisition timeout** | Không mượn được connection từ pool | Pool/downstream capacity, không suy ra deadlock |
| **Application deadlock** | Java threads giữ mutex/monitor chờ nhau | Sửa lock trong JVM, DB detector không thấy |

**Lỗi có chữ “lock” không đồng nghĩa deadlock.** Nếu phân loại quá rộng rồi retry mọi SQL exception, hệ thống có thể tạo retry storm với lỗi dữ liệu cố định.

## 5. Row lock, index và foreign key có thể tạo vòng chờ

Ví dụ hai UPDATE trực tiếp vào hai row dễ hiểu, nhưng trong production deadlock có thể xuất hiện khi:

- Hai writer cập nhật nhiều row theo **thứ tự khác nhau**.
- Một UPDATE sửa khóa được index hoặc làm thay đổi nhiều index entries.
- Hai transaction đồng thời INSERT/UPSERT cùng business key.
- Foreign key check tạo khóa/điều kiện chờ trên bản ghi cha.
- Trigger thực hiện thêm UPDATE sang bảng khác mà application không thấy trong SQL chính.
- Cascade update/delete chạm các bản ghi liên quan.
- Transaction giữ advisory lock hoặc lock chế độ khác ngoài row lock.
- Một số DB/isolation dùng gap/key-range locks khi quét phạm vi.

**Chú ý theo hệ quản trị:** cơ chế lock của PostgreSQL và MySQL/InnoDB không giống nhau. PostgreSQL thường dùng row-level tuple locks và predicate locking cho các mức isolation phù hợp; InnoDB có record/gap/next-key locking theo access path và isolation. Không dùng một mô tả của PostgreSQL làm quy luật tuyệt đối cho MySQL hoặc SQL Server.

### Vì sao index quan trọng?

Câu UPDATE không có index phù hợp có thể scan nhiều row, tiêu tài nguyên lớn, kéo dài transaction, và ở một số DB/plan gây lock footprint hoặc phạm vi chờ khác dự kiến. Index giúp tìm đúng row nhanh hơn nhưng **không bảo đảm deadlock biến mất**, vì vấn đề cốt lõi vẫn là thứ tự/quan hệ khóa và transaction overlap.

## 6. Isolation level không phải “công tắc tắt deadlock”

Các isolation levels như READ COMMITTED, REPEATABLE READ và SERIALIZABLE điều khiển mức đảm bảo nhất quán và cách quản lý các xung đột.

- READ COMMITTED có thể giảm một số lock lifetime/contended reads tùy DB, nhưng UPDATE trên cùng row vẫn có thể deadlock.
- REPEATABLE READ có semantics khác giữa PostgreSQL và MySQL; không suy đồng nhất.
- SERIALIZABLE thường tăng ràng buộc đúng lịch thực thi, có thể tạo **serialization failures** cần retry.
- Một số cơ chế snapshot/MVCC cho phép đọc không block ghi, nhưng các UPDATE xung đột vẫn phải được phối hợp.

**Không nâng isolation lên SERIALIZABLE chỉ để sửa deadlock.** Isolation mạnh hơn có thể cần vì nghiệp vụ, nhưng cũng làm tăng số transaction abort và đòi retry toàn transaction.

Cần tách hai câu hỏi: **mức nhất quán nghiệp vụ nào bắt buộc?** và **làm sao giảm khả năng tạo vòng khóa?**

## 7. Spring Batch chunk transaction tác động thế nào?

Trong chunk-oriented processing, worker thường:

1. Reader đọc một nhóm item.
2. Processor chuẩn hóa/filter.
3. Writer ghi nhóm item.
4. Transaction manager commit chunk.
5. JobRepository lưu tiến độ/checkpoint theo contract của Step/ItemStream.

~~~mermaid
flowchart LR
    R["Read items"] --> P["Process"]
    P --> W["Write chunk"]
    W --> C{"Commit"}
    C -->|Thành công| CP["Checkpoint / tiến độ"]
    C -->|Deadlock victim| RB["Rollback"]
    RB --> RET["Retry / fail theo policy"]
~~~

Deadlock trong writer có thể khiến **toàn chunk transaction rollback**. Nếu retry được cấu hình, Spring Batch có thể chạy lại phần phù hợp theo fault-tolerant semantics; item/processor/writer invocation counts có thể khác với số business rows đã commit.

### Không hiểu sai thứ tự checkpoint

Tính atomic của metadata checkpoint và business write phụ thuộc transaction manager, DataSource và cấu hình repository/step. Nếu metadata và business DB nằm trên hai resource managers khác nhau, không được mặc định có distributed atomic commit.

Khi job restart, phải căn cứ **JobRepository/ExecutionContext cùng business DB state**, không lấy dòng log “read 500 items” làm checkpoint chắc chắn.

### Khi nào SQL deadlock ảnh hưởng read?

Reader dùng cursor, paging hoặc query khóa cũng có thể tham gia vào vòng chờ. Không nên mặc định deadlock chỉ xuất hiện ở writer: reader truy vấn `FOR UPDATE`, lookup update hoặc listener cũng có thể giữ/đòi khóa.

## 8. Các mô hình scaling dễ làm deadlock xuất hiện

| Mô hình | Đơn vị đồng thời | Rủi ro deadlock |
| --- | --- | --- |
| **Multi-threaded step** | Nhiều chunk threads trong một StepExecution | Writer/reader chia state, các chunk UPDATE trùng key hoặc đảo thứ tự |
| **Parallel steps** | StepExecutions chạy theo flow | Hai steps ghi bảng/bản ghi phụ thuộc theo thứ tự khác nhau |
| **Local partitioning** | Nhiều worker StepExecutions cùng JVM | Range overlap, hot key, bảng tổng hợp dùng chung |
| **Remote partitioning** | Nhiều worker StepExecutions trên các JVM | Không chia heap nhưng cùng tranh DB rows/index/locks |
| **Remote chunking** | Nhiều chunk requests xử lý qua broker | Chunk xử lý đảo thứ tự, duplicate request, writer tranh khóa |
| **Nhiều JobInstances** | Nhiều batch chạy cùng business date | Không phải một job đơn nhất nhưng vẫn ghi chung đích |

**Ranh giới thread/JVM không phải ranh giới dữ liệu.** Hai worker ở hai container khác nhau vẫn có thể cập nhật cùng row account, invoice summary hoặc partition metadata.

Một pipeline “partition không chồng lấn” vẫn có thể deadlock nếu từng partition cập nhật **bảng tổng hợp chung**, foreign key parent row hoặc cùng hot index key.

## 9. Nguyên nhân phổ biến nhất: thứ tự lấy khóa không nhất quán

Giả sử hai chunk chứa cùng hai account IDs nhưng thứ tự input khác nhau:

~~~text
Chunk A: [account 10, account 20]
Chunk B: [account 20, account 10]
~~~

Nếu writer cập nhật theo thứ tự danh sách, chúng có thể tạo vòng chờ. Giải pháp nền tảng là chọn **một thứ tự toàn cục** để xử lý các tài nguyên có thể khóa.

~~~text
Cùng quy ước:
  account_id tăng dần
  bảng cha trước bảng con
  trong cùng bảng, ID tăng dần
~~~

Với các transaction thực hiện cùng tập thao tác được sắp xếp nhất quán, nguy cơ tạo vòng chờ từ riêng các khóa ấy giảm mạnh.

### Thứ tự cần bao quát cả các bước gián tiếp

Chỉ sort item trong writer chưa đủ nếu:

- Trigger sau UPDATE lại ghi bảng khác theo thứ tự tùy ý.
- Foreign key/cascade tạo khóa bổ sung.
- Hai code paths lấy lock ở hai bảng theo thứ tự khác nhau.
- Query plan hoặc batch driver thực thi thứ tự hàng khác giả định.
- Một phần ứng dụng dùng SQL khác với writer batch.

**Lock ordering là nguyên tắc thiết kế xuyên các code paths**, không chỉ một `Collections.sort` cục bộ.

## 10. Ví dụ Java: writer cập nhật theo ID tăng dần

Ví dụ Spring Batch 5.x với `ItemWriter<InvoiceUpdate>` ghi vào PostgreSQL. Mục tiêu là **đặt thứ tự business keys trước khi phát SQL**, đồng thời vẫn dùng transaction do step quản lý.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

record InvoiceUpdate(long invoiceId, long amountCents) {}

public final class OrderedInvoiceWriter
        implements ItemWriter<InvoiceUpdate> {

    private final JdbcTemplate jdbc;

    public OrderedInvoiceWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends InvoiceUpdate> chunk) {
        List<InvoiceUpdate> updates =
                new ArrayList<>(chunk.getItems());

        updates.sort(
                Comparator.comparingLong(InvoiceUpdate::invoiceId));

        for (InvoiceUpdate row : updates) {
            jdbc.update(
                """
                UPDATE invoice_summary
                SET amount_cents = ?
                WHERE invoice_id = ?
                """,
                row.amountCents(),
                row.invoiceId());
        }
    }
}
~~~

### Vì sao dùng bản sao danh sách?

`Chunk.getItems()` không cần bị sửa tại chỗ để sắp xếp; tạo bản sao tránh thay đổi thứ tự chunk đầu vào nếu thành phần khác dựa vào nó. Writer không lưu `currentInvoice` hoặc `List` mutable trong singleton field.

### Giới hạn của ví dụ

- SQL UPDATE theo business key chỉ đúng nếu mỗi `InvoiceUpdate` là **snapshot giá trị cuối**; với delta cộng/trừ, phải thiết kế idempotency và thứ tự nghiệp vụ.
- Các UPDATE cùng key lặp trong một chunk cần quy tắc chọn version/giá trị trước khi chạy.
- Duyệt từng `jdbc.update` tạo nhiều round trips; production có thể dùng JDBC batch, staging table hoặc stored procedure **nhưng phải kiểm chứng thứ tự thực thi và locking**.
- Thứ tự từ application không bảo đảm trigger, foreign key và query plan sẽ lấy mọi khóa theo đúng thứ tự đó.
- Ví dụ không tự đăng ký Step, DataSource hoặc Job; cần cấu hình giao dịch thực.
- Nếu business record không tồn tại, `jdbc.update` trả số row bằng 0; ứng dụng phải quyết định update-missing là lỗi hay hành vi hợp lệ.

**Thử nghiệm với DB thật** vẫn cần thiết. Mục tiêu của lock ordering là giảm khả năng deadlock, không tuyên bố không bao giờ xảy ra deadlock.

## 11. Partition range không chồng lấn nhưng vẫn có hot key

Giả sử Partitioner chia `invoice_id` thành:

~~~text
p0: [1, 500001)
p1: [500001, 1000001)
p2: [1000001, 1500001)
p3: [1500001, 2000001)
~~~

Dùng cận `[fromInclusive, toExclusive)` giúp mỗi invoice thuộc đúng một partition. Nhưng mọi writer còn làm:

~~~sql
UPDATE daily_summary
SET total_cents = total_cents + :delta
WHERE business_date = :businessDate;
~~~

Khi đó bốn partition dù khác ID vẫn tranh **cùng một row daily_summary**. Nếu writer còn khóa các invoice rows rồi mới update summary, các transaction khác khóa summary trước rồi lại update invoice, vòng chờ có thể xuất hiện.

### Những cách tổ chức lại

- Ghi dữ liệu chi tiết theo invoice ID độc lập.
- Tính tổng riêng theo partition hoặc shard, rồi tổng hợp ở **step cuối**.
- Nếu cần atomic increment trên summary, giữ transaction ngắn và thống nhất thứ tự khóa.
- Đảm bảo uniqueness/idempotency khi chunk có thể retry.
- Kiểm tra database partitioning/aggregation có thực sự giải quyết hot row không; không chỉ đổi số partition.

**Không chia cùng một business key qua nhiều partition** nếu nghiệp vụ đòi các thao tác theo thứ tự và không có cơ chế sequence/merge phù hợp.

## 12. Mất dữ liệu do sai cận range khác deadlock

Hai partition sai ranh giới:

~~~text
p0: id BETWEEN 1 AND 500000       -- inclusive
p1: id BETWEEN 500000 AND 1000000 -- inclusive, trùng id 500000
~~~

Chúng có thể cùng cập nhật `invoice_id=500000`, tăng tranh chấp và tạo duplicate. Nhưng **chỉ overlap thôi không đủ chứng minh deadlock**; phải có thêm vòng chờ khóa.

Phân chia rõ theo cận:

~~~sql
SELECT invoice_id, amount_cents
FROM invoice_source
WHERE invoice_id >= :fromInclusive
  AND invoice_id <  :toExclusive
ORDER BY invoice_id;
~~~

Test Partitioner phải xác minh union ranges phủ đúng input, không gap/overlap, tên partition ổn định khi restart.

**Đừng dùng tổng readCount để xác nhận duy nhất.** Hai partition có thể vừa đọc trùng mười bản ghi vừa bỏ sót mười bản ghi, khiến tổng count vẫn bằng kỳ vọng.

## 13. UPDATE/UPSERT trên cùng key không tự an toàn với retry

Trong remote chunking hoặc remote partitioning, cùng business event có thể xuất hiện hai lần sau timeout hoặc broker redelivery. Deadlock retry cũng làm processor/writer được gọi lại.

Có hai loại side effect khác nhau:

**Đặt trạng thái (snapshot):**

~~~sql
INSERT INTO invoice_projection
    (invoice_id, source_version, normalized_amount_cents)
VALUES (:id, :version, :amount)
ON CONFLICT (invoice_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    normalized_amount_cents =
        EXCLUDED.normalized_amount_cents
WHERE invoice_projection.source_version
      < EXCLUDED.source_version;
~~~

Với PostgreSQL, mẫu này phù hợp khi event chứa **snapshot đầy đủ**, phiên bản tăng đơn điệu và không cần áp dụng mọi delta trung gian. Cùng version nhưng payload khác cần **conflict detection**, không âm thầm bỏ qua.

**Thao tác cộng dồn (delta):**

~~~sql
UPDATE account_balance
SET balance_cents = balance_cents + :delta
WHERE account_id = :accountId;
~~~

Lệnh này **không idempotent** nếu sự kiện được áp dụng hai lần. Có thể dùng event ledger có unique constraint để xác lập event đã xử lý trong **cùng transaction DB** với balance update, và phát hiện payload conflict.

Deadlock retry chỉ an toàn khi transaction thật sự rollback hoàn toàn trước thử lại. Broker redelivery/restart có thể xảy ra **sau commit** của lần trước; đó là rủi ro khác, cần business idempotency độc lập.

## 14. Đừng giữ khóa DB trong lúc chờ network

Anti-pattern:

~~~text
BEGIN transaction
  SELECT/UPDATE account 10 (giữ lock)
  gọi HTTP API chờ 15 giây
  UPDATE account 20
COMMIT
~~~

Trong 15 giây chờ API, các worker khác có thể bị khóa. Nếu một worker khác giữ row 20 và chờ row 10, deadlock càng dễ xảy ra.

Một hướng cải tiến có thể gồm:

- Thực hiện lookup HTTP **trước** transaction ghi khi nghiệp vụ cho phép.
- Giữ transaction DB ngắn, chỉ làm các thao tác atomic cần thiết.
- Tách external side effect bằng outbox/inbox hoặc workflow có idempotency/reconciliation.
- Dùng timeout và backpressure cho HTTP client; không giữ JDBC connection chờ permit vô hạn.
- Giảm số resource bị giữ đồng thời.

**Không đơn giản đẩy HTTP call ra ngoài transaction rồi tuyên bố exactly-once.** Nếu API có side effect, cần xử lý trường hợp API đã thực hiện nhưng DB chưa ghi nhận hoặc ngược lại.

## 15. Chunk size ảnh hưởng lock lifetime và retry cost

Giả sử chunk size là `N`. Một chunk lớn có thể giảm số transaction và tăng JDBC batching, nhưng cũng có thể:

- Giữ nhiều row locks cùng lúc.
- Kéo dài thời gian từ lock đầu tiên tới commit.
- Tăng xác suất hai transactions overlap.
- Tăng chi phí rollback/retry khi deadlock.
- Tăng payload/buffer/heap.
- Làm stale worker khó xác định tiến độ nếu chunk quá dài.

Chunk nhỏ hơn giúp nhả lock thường xuyên hơn nhưng cũng tăng commit overhead, metadata writes và có thể giảm throughput.

| Cấu hình | Tác động thường thấy | Rủi ro |
| --- | --- | --- |
| Chunk 50 | Giao dịch ngắn, ít row locks | Nhiều commits |
| Chunk 500 | Cân bằng latency/transaction overhead | Cần benchmark |
| Chunk 5.000 | Ít commits, JDBC batching có thể tốt | Lock duration, rollback cost lớn |
| Chunk 50.000 | Transaction rất lớn | WAL/undo/lock/resource pressure |

Bảng minh họa xu hướng, **không phải ngưỡng khuyến nghị chung**. Với một UPDATE chỉ giữ khóa 1 ms và có index, chunk 5.000 có thể tốt; với DB hot row hoặc API callback trong transaction, chunk 50 vẫn có thể chậm.

**Phương pháp:** cố định dataset, đo deadlocks/1.000 commits, throughput hữu ích, p95 chunk duration, lock wait, rollback và DB resource trước/sau mỗi thay đổi.

## 16. Resource pool lớn không giải quyết vòng chờ

Một worker JVM có 8 handler threads nhưng HikariCP tối đa 4 connections; vài handler phải đợi connection. Nếu tăng pool lên 16:

- Có thể giảm JDBC acquire wait.
- Nhưng cũng có thể tăng số SQL transactions đồng thời giữ khóa.
- Khi DB đang bị hot-row contention, số deadlock và lock wait có thể tăng.
- Connection count toàn cluster tăng khi autoscale JVM.

Công thức trần cấu hình:

\[
C_{\mathrm{worker,total}}=P\times C_{\mathrm{pool,max}}
\]

Với 12 worker JVM và pool max 12:

\[
12\times12=144\text{ connections tiềm năng}
\]

Còn phải tính manager, JobRepository và các ứng dụng khác. Trần connection thấp hơn DB max không chứng minh DB I/O/lock chịu được tải.

### Cách chọn pool/concurrency

1. Xác định DB còn capacity hay đã bão hòa.
2. Đo Hikari active/idle/pending và acquire latency.
3. Đo DB lock wait/deadlock/transaction duration.
4. Tăng worker/concurrency theo từng nấc.
5. Nếu throughput hữu ích không tăng mà lock wait tăng, giảm concurrency hoặc sửa SQL/hot keys.
6. Đừng thay pool, chunk size, index và worker count cùng lúc rồi quy nguyên nhân tùy tiện.

## 17. SELECT FOR UPDATE, lock ordering và SKIP LOCKED

Đôi khi application muốn khóa trước các row theo một thứ tự xác định:

~~~sql
BEGIN;

SELECT account_id
FROM account_balance
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;

-- Sau khi giữ được khóa theo chính sách và query plan
-- thực hiện UPDATE các bản ghi đã xác định

COMMIT;
~~~

Tuy nhiên câu SQL chỉ là một **phương án cần kiểm chứng với DB/plan thực tế**: planner/locking semantics, trigger, FK và những câu SQL khác trong transaction vẫn có thể làm thứ tự khóa thực tế khác mong muốn. Không xem `ORDER BY ... FOR UPDATE` là bằng chứng toán học loại trừ mọi deadlock.

### SKIP LOCKED dùng để làm gì?

Ở một số DB, `FOR UPDATE SKIP LOCKED` cho phép chọn **những row hiện không bị khóa** để các worker giống queue consumers tránh chờ nhau:

~~~sql
SELECT task_id
FROM work_queue
WHERE state = 'PENDING'
ORDER BY task_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

Các giới hạn:

- Cần chạy trong transaction/claim protocol đúng để không hai worker cùng nhận một task sau khi transaction nhả lock.
- `SKIP LOCKED` trả về **tập dữ liệu không nhất quán theo ảnh chụp toàn cục**; phù hợp hơn cho queue claim, không phù hợp tùy tiện cho batch cần đọc **mọi** invoice trong một snapshot.
- Task bị khóa có thể bị bỏ qua trong lượt hiện tại, cần cơ chế revisit/lease/recovery.
- Không đảm bảo fairness hay thứ tự business khi các worker xử lý đảo thứ tự.
- Không tự sửa deadlock do writer khóa nhiều bảng khác.

**Không áp `SKIP LOCKED` lên một reader partitioning rồi coi work bị skip là đã hoàn thành.** Phải có proof về coverage, checkpoint và restart.

## 18. SQLSTATE và exception classification

Tùy hệ quản trị và driver, cùng một vấn đề có thể được biểu diễn khác nhau:

| Hệ quản trị | Dấu hiệu thường gặp | Phải phân biệt |
| --- | --- | --- |
| PostgreSQL | SQLSTATE `40P01` = deadlock detected | `40001` = serialization failure; `55P03` = lock not available; `57014` có thể là query cancelled/statement timeout |
| MySQL/InnoDB | Error code `1213` thường deadlock, SQLSTATE thường `40001` | Error `1205` thường lock wait timeout; mã phụ thuộc driver/phiên bản |
| SQL Server | Error number `1205` = deadlock victim | Khác lỗi lock timeout hay client-side timeout |
| Oracle | ORA-00060 = deadlock detected | Khác ORA-00054 resource busy theo NOWAIT |

Các mã trên là ví dụ thường gặp; **không viết logic chung dựa vào một số 1205** vì với SQL Server đó là deadlock, còn MySQL/InnoDB 1205 thường là lock wait timeout.

Spring JDBC có cơ chế exception translation theo JDBC driver và DB vendor. Các kiểu exception có thể gặp gồm `DeadlockLoserDataAccessException`, `CannotAcquireLockException` và các lớp thuộc họ `PessimisticLockingFailureException`. Loại thực tế phải kiểm tra trên DB/driver/Spring Framework version đang dùng.

### Cách phân loại an toàn

- Log SQLSTATE/vendor code, tên exception và transaction phase.
- Phân loại lỗi retryable theo *policy*, không catch rồi retry tất cả SQLException.
- Khi Spring đã translate exception, test xem throwable nào thực sự tới fault-tolerant step.
- Tránh retry lỗi unique constraint hoặc data validation vô hạn.
- Khi không xác định commit outcome, dùng trạng thái **UNKNOWN** thay vì nói rollback chắc chắn.

## 19. Deadlock victim phải rollback trước khi thử lại

Sau khi database báo deadlock, transaction liên quan thường không thể tiếp tục dùng như chưa có gì xảy ra. Với PostgreSQL, sau một statement error trong transaction, transaction vào trạng thái aborted và cần rollback trước khi thực hiện thao tác tiếp.

~~~mermaid
flowchart TD
    W["Writer UPDATE"] --> R{"SQL result"}
    R -->|Commit OK| C["Chunk COMMITTED"]
    R -->|Deadlock| RB["Rollback transaction"]
    RB --> F{"Retryable + còn budget?"}
    F -->|Có| B["Backoff + transaction mới"]
    B --> W
    F -->|Không| FAIL["Step FAILED / policy khác"]
~~~

### Vì sao retry statement riêng có thể sai?

Giả sử writer đã ghi row A, rồi UPDATE row B gây deadlock. Nếu chỉ retry UPDATE row B trên transaction đã lỗi mà không rollback/replay toàn **đơn vị atomic**, ứng dụng có thể mất nhất quán giữa A và B.

Spring Batch có chunk transaction và fault-tolerant retry support, nhưng phải cấu hình đúng **transaction manager**, writer và exception classification. Không dùng một vòng `while(retry)` trong writer để giữ lại transaction aborted.

### Lưu ý với processor có side effect

Nếu processor gửi email hoặc gọi API ngoài DB transaction rồi writer bị deadlock, khi chunk retry có thể gửi lại email/API call. Cần dời side effect về giai đoạn có outbox/idempotency và kiểm tra re-execution semantics. Một processor được gọi lại không đồng nghĩa business transaction đã commit hai lần; cần nhìn từng resource.

## 20. Cấu hình retry deadlock trong Spring Batch 5.x

Spring Batch hỗ trợ fault-tolerant chunk steps. Với lỗi deadlock đã được phân loại là **tạm thời và rollback-safe**, có thể bật retry hữu hạn trên các exception types đã xác minh từ Spring JDBC.

Ví dụ Java 17, Spring Batch 5.x, Spring Framework 6.x:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.DeadlockLoserDataAccessException;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step updateInvoiceStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InvoiceUpdate> reader,
        ItemWriter<InvoiceUpdate> writer) {

    ExponentialBackOffPolicy backoff =
            new ExponentialBackOffPolicy();

    backoff.setInitialInterval(200L); // ms
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(3000L);    // ms

    return new StepBuilder("updateInvoiceStep", jobRepository)
            .<InvoiceUpdate, InvoiceUpdate>chunk(
                    200, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retry(CannotAcquireLockException.class)
            .retryLimit(3)
            .backOffPolicy(backoff)
            .build();
}
~~~

### Giải thích và giới hạn

- `chunk(200, transactionManager)` xác định transaction boundary của chunk.
- `faultTolerant()` bật các chính sách retry/skip của builder.
- `retry(...)` là allow-list cho nhóm lỗi được thử lại; **phải quan sát loại exception thực tế** trong môi trường DB/driver của bạn.
- `retryLimit(3)` là giới hạn attempts theo Spring Retry/Spring Batch semantics. Hãy kiểm thử chính xác số lần callback được gọi theo phiên bản và kiểu retry; không giả định một SQL statement sẽ được chạy đúng ba lần trong mọi tình huống.
- Backoff giới hạn nhịp retry; các giá trị chỉ minh họa, không phải cấu hình production chuẩn.
- **Không cấu hình skip deadlock như cách thường xuyên để “hoàn thành job”.** Skip có thể làm thiếu bản ghi cần ghi.
- Ví dụ chưa định nghĩa bean reader/writer/Job, chưa có datasource/schema/transaction cho dự án hoàn chỉnh.
- Thử lại đúng transaction semantics phụ thuộc writer, reader state, metadata và Step configuration; cần integration test với DB thật.

### Vì sao tránh retry thủ công trong writer?

Không nên bắt exception deadlock, rồi retry `jdbc.update` ngay bên trong cùng transaction đã bị PostgreSQL đánh dấu aborted. Hãy để Spring Batch/transaction manager kết thúc rollback và thử lại theo **đơn vị công việc có contract rõ**.

Nếu writer dùng nested transactions hoặc external service không rollback theo DB, phải kiểm tra từng ranh giới thay vì mặc định mọi side effect được rollback.

## 21. Backoff, jitter và giới hạn retry toàn hệ thống

Nếu 20 worker cùng gặp deadlock và retry ngay không delay, chúng có thể đụng nhau lần nữa. Exponential backoff giảm nhịp đồng bộ.

Một dãy delay minh họa:

~~~text
Lần thử 1: ngay
Lần thử 2: chờ khoảng 200 ms
Lần thử 3: chờ khoảng 400 ms
Các lần tiếp theo (nếu policy cho phép): tăng đến trần
~~~

**Jitter** bổ sung biến thiên ngẫu nhiên có giới hạn giúp các worker không cùng thức dậy đúng một thời điểm. Một `ExponentialBackOffPolicy` cơ bản không tự có jitter chỉ vì đặt multiplier; nếu cần jitter, chọn implementation/policy phù hợp và test các giới hạn.

### Retry budget nhiều tầng

| Tầng | Vì sao có thể retry? | Cần làm gì? |
| --- | --- | --- |
| Spring Batch chunk | Deadlock trong transaction | Retry hữu hạn sau rollback |
| Spring Integration handler | Lỗi xử lý request | Không lồng vô hạn với chunk retry |
| Broker | Worker chết trước ACK | Redelivery có thể là request hoàn chỉnh |
| Manager | Reply timeout | Không suy ra business transaction chưa commit |
| Job restart | StepExecution FAILED | Giữ input/checkpoint, idempotency |
| JDBC client/driver | Có thể có retry nội bộ tùy cấu hình | Biết rõ driver/SDK đang làm gì |

Ví dụ hai tầng, mỗi tầng cho ba attempts, có thể tạo tới nhiều lần gọi writer hơn người vận hành nghĩ. **Số lượng attempts phải được xác định theo đúng cấu hình thực tế**; không mặc định phép nhân áp dụng cho mọi luồng retry vì callbacks/commit policies khác nhau.

### Timeout hợp lý

Backoff phải nằm trong deadline chung của chunk/job và broker delivery. Nếu manager request timeout 5 giây trong khi worker có thể chờ retry 30 giây, manager có thể đánh dấu timeout trước khi worker hoàn tất.

Cần chỉnh `retry budget`, transaction timeout, message visibility/ACK handling, request-reply timeout và worker shutdown grace thành một chính sách nhất quán.

## 22. Skip vs retry vs restart: ba ý nghĩa khác nhau

**Retry** là thử lại phần việc có khả năng thành công khi điều kiện tạm thời thay đổi. **Skip** là bỏ qua item lỗi theo chính sách dữ liệu. **Restart** là tiếp tục một JobInstance sau lần thực thi thất bại với metadata/checkpoint phù hợp.

| Tình huống | Chính sách điển hình | Lý do |
| --- | --- | --- |
| Deadlock transient trong writer | Retry transaction/chunk bounded | Dữ liệu vẫn hợp lệ, chỉ bị tranh lock |
| DB connection outage dài | Retry ngắn, sau đó fail/restart có kiểm soát | Không chặn worker vô hạn |
| Input sai định dạng cho phép bỏ | Skip có audit/quarantine | Không sửa bằng retry |
| Vi phạm ràng buộc business cố định | Fail hoặc quarantine theo nghiệp vụ | Retry không làm dữ liệu hợp lệ |
| Worker chết sau commit trước ACK | Idempotency + reconciliation/recovery | Không chắc work chưa được áp dụng |
| Deadlock attempts exhausted | Step FAIL, alert, restart khi phù hợp | Không tự coi item đã xử lý |

### Cẩn trọng với counters

- `retryCount` do listener đo có thể khác số rollback transaction.
- `writeCount` không nhất thiết bằng số lời gọi writer; chỉ số gắn với execution semantics của Step.
- `readCount` và `writeCount` có thể khác vì filter/skip.
- `JobExecution COMPLETED` không thay business reconciliation.

**Không dùng skipPolicy cho mọi `DeadlockLoserDataAccessException` để ép job hoàn thành.** Nó có thể bỏ qua những giao dịch cần xuất hiện ở đích.

## 23. Thiết kế writer tránh side effect trùng sau retry

Một writer an toàn phải cân nhắc ít nhất hai cơ chế retry:

**Cơ chế A — Deadlock rollback:** DB transaction chứa các UPDATE chưa commit sẽ bị rollback, sau đó chunk có thể được chạy lại.

**Cơ chế B — Redelivery/restart sau commit:** DB đã commit nhưng manager/broker chưa biết kết quả; cùng business event có thể đến lần nữa.

Cơ chế B không được xử lý chỉ bằng việc “deadlock sẽ rollback”. Cần **idempotency bền vững**.

Ví dụ ledger:

~~~sql
CREATE TABLE applied_event (
    event_id UUID PRIMARY KEY,
    payload_hash CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE account_balance (
    account_id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL
);
~~~

Bên trong một transaction DB, quy trình logic:

1. Xác lập event ID mới với unique constraint/atomic insert.
2. Nếu ID đã tồn tại, xác minh hash tương ứng; duplicate hợp lệ thì không cộng delta lại.
3. Nếu ID mới, áp dụng `balance = balance + delta` đúng một lần.
4. Commit ledger và balance update **cùng transaction**.
5. Nếu deadlock, rollback cả hai rồi cho framework retry transaction phù hợp.

Không dùng `SELECT event_id` trước rồi `INSERT` sau **mà không có unique constraint**: hai worker có thể cùng nhìn chưa tồn tại và cộng hai lần.

### Ordering trong ledger

Nếu event chứa các delta theo một account với sequence, idempotency từng event chưa bảo đảm **đúng thứ tự**. Cần sequence guard, per-key serialization hoặc phép gộp có tính giao hoán được chứng minh, tùy nghiệp vụ.

### HTTP side effect

Nếu writer đồng thời gọi API thanh toán, transaction của PostgreSQL không tự rollback API. Dùng API idempotency key, outbox/inbox hoặc reconciliation; không gửi lại một lệnh thanh toán tùy tiện chỉ vì SQL deadlock ở bước sau.

## 24. Optimistic locking và isolation theo business version

Một cách giảm thời gian giữ row locks cho một số workload là dùng **optimistic concurrency control**, khi nghiệp vụ cho phép detect/retry conflict.

Ví dụ cập nhật projection theo version:

~~~sql
UPDATE invoice_projection
SET normalized_amount_cents = :amount,
    source_version = :nextVersion
WHERE invoice_id = :invoiceId
  AND source_version = :expectedVersion;
~~~

Nếu affected rows = 0:

- Có thể phiên bản đã thay đổi.
- Có thể row không tồn tại.
- Có thể event trùng hoặc đã lỗi thời.

Ứng dụng phải phân loại ba trường hợp, không auto retry với version cũ vô hạn.

### Optimistic locking có loại trừ deadlock không?

**Không.** UPDATE vẫn phải lấy khóa khi ghi. Optimistic concurrency giúp ứng dụng phát hiện stale writes và có thể tránh một số giao dịch giữ khóa lâu, nhưng các writer đồng thời, index/FK/trigger vẫn có thể tạo deadlock.

### Khi nào dùng?

- Projection theo snapshot/version.
- Work có conflict rate thấp.
- Business có thể lấy phiên bản mới và tính lại kết quả một cách an toàn.
- Có cách xử lý version conflict rõ và không làm mất delta events.

Với cùng hot account liên tục thay đổi, optimistic retry có thể biến thành **optimistic retry storm**. Khi đó cần sharding theo key, per-key ordering, queue partition hoặc cập nhật atomic đúng thiết kế.

## 25. Giảm contention từ kiến trúc dữ liệu

Các biện pháp ở mức kiến trúc thường hiệu quả hơn tăng pool:

| Biện pháp | Khi hữu ích | Điều cần kiểm tra |
| --- | --- | --- |
| **Partition theo business key** | Các key độc lập | Không có cross-partition update ngầm |
| **Range/ID partition** | Dataset có ranh giới ổn định | Cận không chồng lấn, hot row bên ngoài range |
| **Staging table rồi merge** | Ghi nhiều kết quả tổng hợp | Trình tự merge, uniqueness, transaction length |
| **Aggregate theo shard rồi finalize** | Nhiều worker tranh một row tổng | Finalizer chính xác, checkpoint và retry |
| **Consistent lock order** | Transaction ghi nhiều row/bảng | Mọi code path, trigger/FK |
| **Thao tác DB ngắn** | Transaction đang giữ lock quá lâu | External API, batch sizes, commit overhead |
| **Serial hóa theo key** | Một hot key bắt buộc đúng thứ tự | Worker throughput, queue lag, fairness |
| **Idempotent upsert** | Duplicate/restart là khả năng bình thường | Version conflict, payload hash |
| **Giảm worker concurrency** | DB bị saturation | SLA, resource budget, số partition chờ |

### Data skew làm một partition giữ tài nguyên lâu

Nếu một partition có 10 triệu item còn các partition khác chỉ 100 nghìn, job có thể bị kéo dài bởi **straggler**. Tăng thêm worker JVM không giúp nếu chỉ còn một partition lớn không chia được. Cần đo row count/elapsed theo partition và thiết kế lại phạm vi, nhưng giữ identity ổn định để restart.

### Tránh một bảng summary nóng

Thay vì mỗi worker tăng cùng một row tổng theo ngày, có thể ghi summary theo partition/shard rồi một step cuối gộp. Tuy nhiên kết quả tổng cuối phải idempotent: nếu finalizer retry sau commit, không cộng tổng lần thứ hai.

## 26. Lock timeout và transaction timeout: chọn ngưỡng theo mục đích

Deadlock detection, lock timeout, statement timeout, Spring transaction timeout và message request timeout là **những đồng hồ khác nhau**.

| Timeout | Phạm vi | Không nên hiểu nhầm |
| --- | --- | --- |
| DB deadlock detector | Phát hiện vòng chờ | Không phải deadline của cả job |
| DB lock timeout | Đợi lock vượt ngưỡng | Không chứng minh có deadlock |
| Statement timeout | Một SQL statement quá lâu | Có thể do scan, I/O hoặc lock |
| Spring transaction timeout | Transaction theo manager/policy | Không mặc nhiên bao phủ API ngoài DB |
| JDBC pool connection timeout | Chờ lấy connection từ pool | Không phải SQL deadlock |
| Broker request/reply timeout | Chờ phản hồi | Không chứng minh worker đã dừng |
| Worker shutdown grace | Thời gian drain process | Không bảo đảm mọi chunk commit |

### PostgreSQL ví dụ trong một transaction thử nghiệm

~~~sql
BEGIN;

SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '10s';

UPDATE invoice_summary
SET amount_cents = amount_cents + 1
WHERE invoice_id = 42;

COMMIT;
~~~

`SET LOCAL` áp dụng trong phạm vi transaction PostgreSQL ở ví dụ. Chọn lock timeout ngắn quá có thể tạo timeout trước khi deadlock detector có đủ thời gian phát hiện; chọn dài quá có thể giữ worker/chunk bị kẹt. Cần thử với data distribution, p95 SQL latency và SLA.

**Không giảm timeout để che deadlock mà không sửa nguyên nhân.** Timeout khiến giao dịch lỗi sớm hơn, không tự loại bỏ vòng lock order sai.

## 27. Diagnostic PostgreSQL: ai chờ ai?

Khi có lock contention trên PostgreSQL, có thể quan sát sessions và blockers bằng các view/hàm hệ thống.

Ví dụ query chẩn đoán:

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY transaction_age DESC NULLS LAST;
~~~

Câu query giúp thấy **sessions đang bị block tại thời điểm quan sát** và các PID blockers tương ứng. Nó không trực tiếp dựng lại toàn bộ deadlock đã bị DB phá trước đó; cần DB logs và deadlock reports để xem vòng chờ của sự cố trong quá khứ.

### Đếm deadlocks theo database

~~~sql
SELECT datname, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

`pg_stat_database.deadlocks` là **counter tích lũy**; cần theo dõi delta theo thời gian và reset stats, không coi số tuyệt đối là số lỗi của riêng một job.

### Một số dữ liệu nên ghi từ ứng dụng

- `jobExecutionId`, `stepExecutionId`, partition name.
- `workerInstance` và tên transaction phase.
- SQLSTATE `40P01` và exception type.
- Chunk size, number of rows touched, elapsed time.
- Retry attempt, rollback outcome, backoff.
- DB pool acquire latency và lock wait.
- Business key theo dạng được phép log hoặc hashed/normalized ID.

**Quyền truy cập:** các hệ thống DB có chính sách hạn chế xem query text/sessions khác. Tránh thu raw SQL có tham số nhạy cảm nếu không được phép. Không tự kill backend DB trong production chỉ từ PID mà chưa có runbook phê duyệt.

## 28. Diagnostic MySQL/InnoDB và SQL Server

Trong MySQL/InnoDB, có thể tham khảo:

- `SHOW ENGINE INNODB STATUS` để xem thông tin deadlock gần đây và các trạng thái engine.
- `performance_schema.data_locks` và `performance_schema.data_lock_waits` ở phiên bản hỗ trợ.
- Logs về deadlock, transaction duration, InnoDB row lock wait.
- Error code `1213` cho deadlock và `1205` thường cho lock wait timeout.

Trong SQL Server, có thể dùng:

- Deadlock graph từ Extended Events/system_health và các công cụ được DBA cấu hình.
- Error `1205` cho deadlock victim.
- Dynamic management views để xem blocked sessions/wait stats theo quyền.

**Không có một cú pháp SQL chẩn đoán chung cho mọi DB.** Trước khi thiết kế alert, xác định dialect, driver version và semantics retry/rollback thực tế.

### Vì sao cần deadlock graph của DB?

Một error log chỉ ghi “deadlock detected” không cho biết hai bảng/statement nào tạo vòng. Deadlock graph thường giúp thấy **processes, resources, lock modes và statements** liên quan, từ đó sửa thứ tự khóa và access path thay vì chỉ tăng retryLimit.

## 29. Metrics: giảm deadlock mà vẫn giữ throughput hữu ích

Các metrics nên nhìn cùng nhau:

| Metric | Ý nghĩa |
| --- | --- |
| Deadlock victims/s hoặc /1.000 commits | Tần suất vòng khóa bị phá |
| Lock wait p95/p99 | Mức tranh khóa kể cả khi chưa deadlock |
| DB transaction duration | Khóa bị giữ lâu hay không |
| Chunk p95/p99 latency | Hậu quả lên tiến độ worker |
| Retry attempts/chunk | Mức khuếch đại tải |
| Rollback count | Transaction không hoàn tất |
| JDBC pool pending/acquire latency | Có chờ resource không |
| DB CPU/IOPS/WAL/locks | DB còn capacity hay đã bão hòa |
| Broker queue age/unacked/lag | Backlog do worker chậm |
| JobExecution elapsed | Có đáp ứng SLA không |
| Unique business keys committed | Throughput **hữu ích**, không đếm duplicate |
| Reconciliation mismatch | Sai dữ liệu/side effect |

Một cấu hình có 0 deadlocks nhưng chỉ xử lý 10% SLA **không phải giải pháp scaling thành công**. Ngược lại, một số deadlock hiếm được retry an toàn có thể chấp nhận nếu throughput, latency và correctness đạt mục tiêu.

### Công thức throughput hữu ích

\[
R_{\mathrm{useful}}=
\frac{N_{\mathrm{unique\ valid\ business\ items\ committed}}}
{T_{\mathrm{end-to-end}}}
\]

Không dùng `handlerInvocationsTotal` hoặc `messagesProcessedTotal` làm tử số nếu chúng bao gồm retries, redeliveries và rollback.

## 30. Thiết kế integration test deadlock với PostgreSQL thật

Unit test giả lập exception chỉ chứng minh retry policy. Để chứng minh deadlock thật, cần **hai database transactions thực** với SQL và khóa đảo thứ tự.

Có thể dùng Testcontainers PostgreSQL hoặc DB integration-test cô lập. Một test deterministic hơn test stress thuần ngẫu nhiên cần:

1. Hai JDBC connections độc lập.
2. Mỗi transaction lấy khóa row khác nhau trước.
3. Đồng bộ bằng `CountDownLatch` để **cả hai đã giữ khóa đầu tiên**.
4. Mỗi transaction yêu cầu khóa thứ hai theo thứ tự ngược.
5. Assert có deadlock victim (`40P01` trong PostgreSQL).
6. Rollback victim; transaction kia có thể tiếp tục.
7. Test retry bằng **transaction mới**, không dùng transaction đã aborted.

Ví dụ JUnit 5 + Testcontainers, chỉ để tái hiện vòng khóa DB (không chạy Spring Batch job):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class ActualPostgresDeadlockTest {

    @Container
    static final PostgreSQLContainer<?> pg =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void twoTransactionsOppositeOrderCauseDeadlock()
            throws Exception {

        try (Connection setup = open();
             Statement statement = setup.createStatement()) {

            statement.execute(
                """
                CREATE TABLE account_balance (
                    account_id BIGINT PRIMARY KEY,
                    balance_cents BIGINT NOT NULL
                )
                """);
            statement.execute(
                """
                INSERT INTO account_balance VALUES
                (10, 100000), (20, 200000)
                """);
        }

        CountDownLatch firstLocksTaken = new CountDownLatch(2);
        var executor = Executors.newFixedThreadPool(2);

        try {
            Callable<String> a =
                    () -> attempt(10, 20, firstLocksTaken);
            Callable<String> b =
                    () -> attempt(20, 10, firstLocksTaken);

            var futureA = executor.submit(a);
            var futureB = executor.submit(b);

            String resultA =
                    futureA.get(20, TimeUnit.SECONDS);
            String resultB =
                    futureB.get(20, TimeUnit.SECONDS);

            long victims = java.util.stream.Stream
                    .of(resultA, resultB)
                    .filter("DEADLOCK"::equals)
                    .count();

            assertEquals(1L, victims);
        } finally {
            executor.shutdownNow();
        }
    }

    private static Connection open() throws SQLException {
        return DriverManager.getConnection(
                pg.getJdbcUrl(),
                pg.getUsername(),
                pg.getPassword());
    }

    private static String attempt(
            long firstId,
            long secondId,
            CountDownLatch firstLocksTaken) throws Exception {

        try (Connection connection = open()) {
            connection.setAutoCommit(false);

            try {
                updateRow(connection, firstId);
                firstLocksTaken.countDown();

                if (!firstLocksTaken.await(
                        5, TimeUnit.SECONDS)) {
                    throw new AssertionError(
                            "Both sessions did not reach first lock");
                }

                updateRow(connection, secondId);
                connection.commit();
                return "COMMITTED";

            } catch (SQLException ex) {
                connection.rollback();

                if ("40P01".equals(ex.getSQLState())) {
                    return "DEADLOCK";
                }
                throw ex;

            } catch (Exception ex) {
                connection.rollback();
                throw ex;
            }
        }
    }

    private static void updateRow(
            Connection c, long accountId) throws SQLException {

        try (PreparedStatement ps = c.prepareStatement(
                """
                UPDATE account_balance
                SET balance_cents = balance_cents
                WHERE account_id = ?
                """)) {

            ps.setLong(1, accountId);
            ps.executeUpdate();
        }
    }
}
~~~

### Điều test này chứng minh

Hai sessions lấy khóa đầu tiên trên hai row riêng, rồi cùng yêu cầu khóa thứ hai, hình thành vòng chờ. PostgreSQL thường chọn một victim với SQLSTATE `40P01`, transaction còn lại commit.

### Giới hạn quan trọng

- Cần Docker/Testcontainers/JUnit/JDBC driver đúng version; không chạy được trên CI không có container runtime.
- Test tạo bảng cố định: phải dùng database container riêng cho mỗi test hoặc cleanup/namespace riêng; không chạy song song nhiều test sử dụng cùng bảng trong một DB.
- Tùy thời điểm scheduling/DB timeouts, failure có thể khác expected; latch và deadline giảm tính ngẫu nhiên chứ không biến mọi môi trường thành hoàn toàn deterministic.
- Test chỉ kiểm chứng **deadlock ở tầng DB**, chưa kiểm chứng `StepExecution`, chunk rollback, reader checkpoint hay business idempotency.
- Khi có lỗi ngoài SQL hoặc test timeout, test phải fail và báo thông tin; không được “PASS” chỉ vì một future throw exception.
- `balance_cents = balance_cents` vẫn là UPDATE có thể lấy row lock trong PostgreSQL ở ví dụ này; production không nên ghi no-op updates để giữ khóa.

## 31. Test Spring Batch retry và checkpoint đúng

Sau khi có test DB deadlock, tạo một lớp integration test chạy **job/step thật** qua Spring Batch:

1. Seed dataset có business key xác định và output mong đợi.
2. Chạy worker StepExecutions đồng thời bằng local/remote partitioning.
3. Dùng test hook/transaction barriers để tạo deadlock tại ranh giới writer có kiểm soát.
4. Ghi nhận exception được Spring translate tới fault-tolerant step.
5. Assert transaction victim rollback, retry theo budget và một execution cuối thành công hoặc thất bại đúng policy.
6. Assert JobRepository status, `rollbackCount`, `commitCount`, restart state.
7. Đối chiếu **tập business keys/values** ở đích, không chỉ tổng rows.
8. Nếu fail sau retry exhaustion, giữ nguyên identifying JobParameters để kiểm thử restart của **cùng JobInstance**.
9. Nếu có message broker, thử mất ACK/reply sau commit để xác minh idempotency với redelivery.

### Kiểm thử “double-counting”

Với một event có delta +100 và business ID `E-42`, cố gửi hai lần trong hai worker. Kết quả đúng là business state chỉ tăng +100 **một lần** nếu contract là exactly-once business effect qua idempotency.

Kết quả tăng +200 là lỗi ngay cả khi JobExecution `COMPLETED` hoặc retry handler báo success.

### Đừng dùng retry fake rồi kết luận đã hết deadlock

Một test mock writer ném `DeadlockLoserDataAccessException` rồi thành công lần hai chứng minh **retry policy invocation**, không chứng minh lock ordering, DB SQLSTATE, rollback và transaction isolation đúng. Cần cả test thật từ phần 30.

## 32. Diễn giải lỗi khi chạy multi-threaded step

Trong multi-threaded step, nhiều chunk threads có thể xử lý cùng `StepExecution`. Rủi ro không chỉ là DB locking:

- Reader cursor có thể không thread-safe.
- `@StepScope` tạo target theo **StepExecution**, không theo chunk thread.
- Processor/writer singleton có state mutable có thể race.
- Chunk commit/retry order có thể khác input order.
- Database lock acquisition order thay đổi do scheduler.
- Các callback/ItemStream update có thể có giả định sai về concurrency.

**Deadlock DB và race trong JVM là hai lỗi độc lập.** Tăng JDBC pool không sửa reader state bị chia sẻ. Nếu có stateful reader, partitioning theo StepExecution độc lập thường giúp làm rõ ownership hơn multi-threaded chunks, nhưng vẫn phải kiểm tra singleton dependencies và DB locks.

### Một phương án đơn giản hơn

Nếu mục tiêu throughput đạt bằng **4 partition threads**, không nhất thiết bật thêm `taskExecutor` 8 chunk threads trong mỗi worker step. Hai tầng concurrency có thể khiến DB nhận rất nhiều transaction đồng thời khó dự đoán, làm deadlock tăng mà throughput không tăng tương ứng.

## 33. Chiến lược xử lý một sự cố deadlock trên production

Một runbook ngắn, tuần tự:

**Bước 1 — Xác nhận loại lỗi.** Thu SQLSTATE, vendor code, exception type. Phân biệt deadlock, lock timeout, serialization failure và pool acquire timeout.

**Bước 2 — Xác định phạm vi.** JobName, JobExecutionId, StepExecutionId, partition, worker instance, input snapshot/cutoff và phase READ/PROCESS/WRITE/COMMIT.

**Bước 3 — Giữ bằng chứng database.** Deadlock graph/log, blocking sessions, SQL statements, lock modes, transaction duration. Không kill database backend tùy tiện.

**Bước 4 — Đo tác động.** Rate deadlock, retry attempts, rollback, DB lock wait, p95 chunk latency, backlog và JobExecution elapsed.

**Bước 5 — Ưu tiên phục hồi an toàn.** Nếu deadlock transient, retry bounded với rollback; nếu quá tải, giảm concurrency/stop phát việc. Không skip silently.

**Bước 6 — Sửa nguyên nhân.** Kiểm tra thứ tự UPDATE, trigger/FK, hot keys, missing index, chunk size và thời gian giữ transaction.

**Bước 7 — Test trước khi tăng tải.** Reproduce với hai sessions/partitions, test restart và redelivery. Chỉ tăng worker khi dữ liệu đúng và DB còn capacity.

**Bước 8 — Đối soát.** Business keys/values, JobRepository, DLQ/quarantine, duplicate prevention; đóng incident khi outcome được chứng minh.

### Khi nào cần dừng job?

Nếu deadlock retry liên tục làm DB quá tải hoặc dữ liệu không thể xác minh, dừng/giảm điều phối có kiểm soát có thể tốt hơn “retry cho tới khi hoàn thành”. Việc cancel phải tuân Spring Batch stop/restart protocol và bảo toàn chunk đang active; không gọi mọi transaction là rollback nếu process chết trước reply.

## 34. Case study: 18 triệu thanh toán trong 30 phút

Một hệ thống cần chuẩn hóa và ghi **18.000.000 bản ghi thanh toán** trong **30 phút**. Manager chia theo `payment_id`; tám worker JVM nhận partition qua broker và ghi vào PostgreSQL.

Thông lượng tối thiểu lý tưởng:

\[
R_{\mathrm{required}}=
\frac{18.000.000}{30\times60}
=10.000\ \mathrm{items/s}
\]

Cần thêm headroom cho startup, retry, checkpoint, tail partition và final aggregation.

### Thiết kế ban đầu

- Partition ranges không chồng lấn theo payment ID.
- Mỗi worker ghi `payment_projection` riêng theo payment ID.
- Nhưng trong cùng transaction, worker cập nhật `merchant_daily_total` theo `merchant_id`.
- Chunk nào có nhiều merchant IDs thì UPDATE theo thứ tự input không nhất quán.
- Với tám JVM, các chunk từ nhiều partition cùng đụng merchant hot keys.
- Deadlock victims và rollback tăng mạnh, DB lock wait cao.

**Bài học:** dữ liệu chi tiết không chồng lấn **không** có nghĩa bảng tổng hợp cũng không chồng lấn.

### Bước 1 — Đo hiện trạng

Giả định dashboard:

~~~text
workerJvms=8
concurrentWriters=32
chunkSize=1000
jdbcPoolMaxPerJVM=12
deadlockVictimsPerMinute=140
chunkRollbackRatio=9%
dbLockWaitP95Ms=950
usefulThroughputItemsPerSecond=7200
~~~

Số liệu minh họa; không phải đặc tính mặc định Spring Batch/PostgreSQL.

### Bước 2 — Tìm vòng khóa

Deadlock reports cho thấy:

~~~text
Tx A: merchant 17 → merchant 42
Tx B: merchant 42 → merchant 17
~~~

Hai chunk cập nhật merchant IDs theo thứ tự khác nhau. Tăng retry từ 3 lên 20 attempts có thể che triệu chứng nhưng tăng DB load.

### Bước 3 — Sửa thiết kế

1. Sort merchant IDs để nhất quán order trước khi UPDATE.
2. Loại bỏ side effect HTTP khỏi transaction ghi.
3. Cân nhắc ghi partial aggregates theo partition, rồi finalizer tổng hợp an toàn.
4. Giảm số concurrent writers nếu DB đã lock-bound.
5. Retry deadlock hữu hạn và backoff/jitter.
6. Với duplicate message, dùng business event ledger/unique constraint.
7. Không đổi input partition mapping khi restart cùng JobInstance.

### Benchmark giả định

| Phương án | Deadlocks/phút | Throughput hữu ích | Thời gian N/R | Đối soát |
| --- | ---: | ---: | ---: | --- |
| 8 JVM, UPDATE theo input order | 140 | 7.200 item/s | 41,7 phút | PASS sau nhiều retry |
| 8 JVM, tăng retryLimit nhưng chưa sửa order | 130 | 7.400 item/s | 40,5 phút | PASS, DB load lớn |
| 8 JVM, consistent lock order | 12 | 10.500 item/s | 28,6 phút | PASS |
| 8 JVM, partial aggregate + finalizer | 4 | 12.800 item/s | 23,4 phút | PASS |
| 12 JVM, chưa sửa hot keys | 230 | 6.800 item/s | 44,1 phút | PASS nhưng chậm |
| 8 JVM, retry gây duplicate side effects | 15 | 13.000 reported attempts/s | Không đáng tin | **FAIL** |

Các số đều **giả định**. Thời gian `N/R` chỉ là ước lượng lý tưởng; phải đo thời gian JobExecution end-to-end để xác minh SLA.

### Bước 4 — Kiểm thử sự cố

- Kill worker giữa chunk trước commit → rollback/restart không mất việc.
- Kill worker sau commit trước ACK/reply → không tăng merchant total hai lần.
- Cùng payment ID đến hai worker → ledger/upsert ngăn trùng.
- Một partition thất bại quá retry budget → job/step status phản ánh đúng, không skip silent.
- Restart cùng input snapshot → không đổi partition scope, đủ 18 triệu business keys hợp lệ.
- Thử tăng pool/concurrency sau khi sửa lock order → không vượt DB resource budget.

**Kết luận tình huống:** giảm deadlock bằng thứ tự khóa/kiến trúc dữ liệu có thể đem lại throughput lớn hơn so với chỉ tăng worker hoặc retry.

## 35. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Hai UPDATE chậm chắc chắn là deadlock.” | Có thể chỉ lock wait/I/O; deadlock cần vòng chờ. |
| “Connection pool quá nhỏ gây mọi deadlock.” | Pool wait khác DB lock cycle; pool lớn có thể tăng contention. |
| “Chia partition không chồng lấn là đủ.” | Các partition vẫn có thể cập nhật hot summary/FK rows. |
| “@StepScope làm mọi writer thread-safe.” | Scope theo StepExecution, không phải per chunk thread. |
| “Bật SERIALIZABLE sẽ hết deadlock.” | Có thể tạo serialization failure và retry nhiều hơn. |
| “ORDER BY luôn loại trừ deadlock.” | Trigger/FK/SQL plan và đường code khác vẫn khóa chéo. |
| “SKIP LOCKED luôn tốt cho mọi batch.” | Có thể bỏ qua locked rows, cần claim/revisit/coverage. |
| “Retry cùng JDBC transaction đã lỗi là được.” | PostgreSQL transaction aborted cần rollback trước retry. |
| “Tăng retryLimit đến 100 là xử lý root cause.” | Chỉ che lỗi, tạo retry amplification. |
| “Deadlock thì skip item để job COMPLETED.” | Có thể làm thiếu business data. |
| “WriteCount bằng số lần writer gọi.” | Framework counters và retry attempts khác nhau. |
| “DB commit trước reply đồng nghĩa manager biết đã xong.” | Reply mất có thể gây redelivery. |
| “UPsert nào cũng idempotent.” | Delta update, version conflict vẫn có thể ghi sai. |
| “Optimistic locking không lấy DB locks.” | UPDATE vẫn cần khóa ghi. |
| “Đếm số message processed là throughput.” | Retry/duplicate làm số attempts cao hơn useful work. |
| “Deadlock report của PostgreSQL giống MySQL.” | SQLSTATE/locking/dialect khác nhau. |
| “Thêm JVM luôn cải thiện scaling.” | DB là tài nguyên chung, lock contention có thể tăng. |

## 36. Checklist thiết kế và kiểm thử

- [ ] Phân biệt deadlock, lock timeout, serialization và optimistic conflicts.
- [ ] Có wait-for graph/DB log chứng minh vòng khóa thật.
- [ ] Cùng business operation cập nhật nhiều row/bảng theo thứ tự nhất quán.
- [ ] Kiểm tra trigger, foreign key, index, cascade và side effects gián tiếp.
- [ ] Partitioner tạo ranges không overlap, tên và ExecutionContext ổn định.
- [ ] Không nhầm partitioning logic với cô lập tất cả hot keys.
- [ ] Writer không giữ mutable shared state sai thread safety.
- [ ] Không giữ DB transaction khi chờ network lâu nếu có thể tách an toàn.
- [ ] Có unique constraint/idempotent writer cho duplicate/restart.
- [ ] Delta events được ledger hoặc cơ chế tương đương chống lặp.
- [ ] Không dùng correlation/message ID thay business event ID tùy tiện.
- [ ] Chunk size được benchmark theo lock time/rollback/commit overhead.
- [ ] Có resource budget JDBC pool/concurrency toàn cluster.
- [ ] Retry đúng exception sau rollback với budget/backoff/jitter.
- [ ] Không skip deadlock âm thầm để ép COMPLETED.
- [ ] SQLSTATE/vendor errors được log và phân loại theo DB driver.
- [ ] Timeout DB/transaction/broker/job được phối hợp.
- [ ] Có test hai DB sessions tái hiện deadlock.
- [ ] Có Spring Batch integration test cho chunk rollback/retry/restart.
- [ ] Có test fault injection worker chết sau commit trước reply/ACK.
- [ ] Có test data reconciliation theo business keys, không chỉ row count.
- [ ] Deadlock/lock wait/retry/rollback metrics được theo dõi.
- [ ] Có runbook phân tích deadlock graph và giảm contention.
- [ ] Benchmark theo useful throughput và JobExecution elapsed.
- [ ] Chỉ tăng worker khi correctness và SLA đều PASS.

## 37. Câu hỏi tự kiểm tra

**1. Hai transactions cùng chờ khóa row 10 có chắc deadlock không?**

Không. Nếu chúng chờ một transaction khác có thể commit bình thường, đó là lock wait. Deadlock cần vòng chờ các tài nguyên không tương thích.

**2. Vì sao hai worker update row 10 và 20 theo thứ tự ngược nhau dễ deadlock?**

Vì A giữ row 10 chờ row 20, còn B giữ row 20 chờ row 10. Cả hai tạo wait-for cycle.

**3. PostgreSQL thường báo SQLSTATE nào cho deadlock?**

`40P01`. Đừng nhầm với `40001` thường là serialization failure hoặc `55P03` là lock not available.

**4. Vì sao MySQL error 1205 và SQL Server error 1205 không nên dùng chung classifier?**

Vì MySQL/InnoDB error 1205 thường là lock wait timeout, còn SQL Server error 1205 là deadlock victim. Cần xét dialect/driver.

**5. Một StepExecution FAILED vì deadlock, có nên skip toàn bộ chunk?**

Không mặc định. Deadlock là lỗi concurrency tạm thời: nên rollback/retry hữu hạn theo policy, hoặc fail để restart an toàn khi exhausted. Skip không đúng có thể làm mất dữ liệu.

**6. Tại sao tăng JDBC pool có thể làm deadlock tăng?**

Nhiều transaction chạy đồng thời hơn có thể giữ/đòi khóa trên cùng hot rows nhiều hơn, dù connection acquire wait giảm.

**7. @StepScope có bảo vệ một stateful reader khi multi-threaded chunk chạy cùng StepExecution không?**

Không tự động. Scoped target theo StepExecution có thể được nhiều chunk threads dùng chung. Cần kiểm tra thread safety và checkpoint.

**8. Chia mỗi invoice vào một partition duy nhất rồi còn cập nhật daily summary chung, có thể deadlock không?**

Có. Các transaction có thể tranh cùng summary row hoặc các lock phụ dù invoice IDs không overlap.

**9. Tại sao ORDER BY trong một query không đủ để tuyên bố không bao giờ deadlock?**

Vì trigger, FK, nhiều SQL statements, query planner và code paths khác có thể tạo lock order bổ sung/khác nhau.

**10. Khi PostgreSQL transaction bị deadlock victim, có thể retry một UPDATE trên chính transaction cũ không?**

Không. Transaction cần rollback rồi thử lại trong transaction mới theo unit-of-work policy phù hợp.

**11. SKIP LOCKED có thể dùng để chia mọi bảng dữ liệu lớn không?**

Không. Nó có thể bỏ qua row đang khóa, phù hợp với claim work queue có cơ chế revisit; không tự bảo đảm quét đầy đủ một snapshot dữ liệu cần xử lý.

**12. Optimistic locking có loại bỏ mọi deadlock không?**

Không. UPDATE vẫn lấy khóa và các thao tác index/FK có thể gây deadlock. Optimistic conflict cần business policy.

**13. Vì sao retry sau DB commit trước reply khác retry deadlock?**

Deadlock thường rollback transaction; commit-before-reply nghĩa side effect đã xảy ra mà manager chưa biết, dễ nhân đôi nếu request được xử lý lại.

**14. Một job xử lý 1 triệu messages/s nhưng chỉ ghi đúng 700 nghìn business records/s, throughput nào dùng đánh giá SLA?**

Throughput hữu ích đã commit hợp lệ, không tính retries/duplicates như việc mới.

**15. Khi nào một cấu hình có ít deadlock nhưng vẫn không được chấp nhận?**

Khi throughput thấp hơn SLA, có missing/duplicate business keys, restart không an toàn hoặc làm DB resource quá tải. Không tối ưu số deadlock tách khỏi correctness và hiệu năng.

**16. Làm sao chứng minh deadlock thật trong test?**

Dùng hai DB transactions độc lập, mỗi bên khóa một row, đồng bộ barrier rồi yêu cầu khóa bên kia; kiểm tra error SQLSTATE, rollback, retry và business state.

---

**Ghi nhớ:** **Deadlock là vòng chờ khóa giữa các transactions**, không phải mọi hiện tượng query chậm hoặc connection timeout. Trong Spring Batch, tăng concurrency/partitioning/worker JVM chỉ tăng năng lực khi database còn đủ capacity và writer có **thứ tự cập nhật nhất quán, transaction ngắn, khóa nghiệp vụ rõ và xử lý duplicate an toàn**. Hãy đọc deadlock graph, phân loại lỗi đúng dialect, rollback trước retry với backoff/budget, kiểm thử hai DB sessions cùng JobRepository/restart và đo **throughput hữu ích cộng tính đúng dữ liệu**. Một hệ thống scaling tốt không phải hệ thống **không bao giờ có deadlock**, mà là hệ thống **giảm nguyên nhân gốc, phục hồi an toàn và đáp ứng SLA khi xảy ra tranh chấp thực tế**.
