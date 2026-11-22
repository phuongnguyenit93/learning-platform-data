# Kiểm thử cạnh tranh LWT và kết quả applied

> **Chương:** Kiểm thử tích hợp  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là cơ sở dữ liệu phân tán wide-column. Kiểm thử tích hợp Java phải hiểu partition key, thiết kế bảng theo truy vấn, replication, consistency level, CQL, compaction, repair và cách ứng dụng nhận/diễn giải lỗi.  
> **Trọng tâm:** Lightweight Transaction (LWT), thao tác có điều kiện, các client cạnh tranh và trường kết quả **[applied]**.

## 1. Tình huống mở đầu: hai yêu cầu cùng muốn giữ một khóa

Giả sử dịch vụ đặt hàng tạo một bản ghi **giữ chỗ đơn hàng** theo khóa nghiệp vụ. Hai request đến cùng lúc, có cùng **order_id** nhưng xuất phát từ hai worker khác nhau. Cả hai đều muốn trả về “đã tạo thành công”.

Cách viết dễ sai:

~~~text
Worker A: SELECT thấy chưa có order
Worker B: SELECT thấy chưa có order
Worker A: INSERT order
Worker B: INSERT order
Worker A: báo CREATED
Worker B: báo CREATED
~~~

Ngay cả khi hai SELECT và hai INSERT thường dùng **LOCAL_QUORUM**, chuỗi *đọc trước rồi ghi* vẫn không trở thành phép **compare-and-set atomic**. Với Cassandra, nếu nghiệp vụ cần điều kiện “chỉ tạo khi chưa tồn tại”, ta có thể sử dụng CQL:

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Cassandra thực hiện **LWT**, dựa trên cơ chế đồng thuận Paxos trong phạm vi dữ liệu liên quan. Các client cạnh tranh cho cùng một khóa sẽ nhận kết quả điều kiện khác nhau:

- **[applied] = true:** thao tác có điều kiện được áp dụng thành công theo phản hồi của server.
- **[applied] = false:** điều kiện không thỏa tại thời điểm xử lý; không phải exception hay dấu hiệu Cassandra “bị lỗi”.
- **Exception/timeout:** client **chưa có kết luận đáng tin cậy** rằng điều kiện được áp dụng hay không. Không được tự chuyển thành false.

Bài học sẽ xây dựng phép thử Java có **nhiều tác vụ cùng xuất phát ở một hàng rào (barrier)**, kiểm tra số client thắng, kiểm tra trạng thái cuối và mô phỏng kết quả không rõ.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Mô tả **IF NOT EXISTS**, **IF column = value**, regular CL và serial CL.
2. Thiết kế fixture **một khóa duy nhất cho mỗi lần chạy** để tránh nhiễu từ bài test khác.
3. Viết integration test **JUnit 5 + Java Driver 4.x** tạo nhiều client cạnh tranh.
4. Khẳng định đúng phạm vi: khi mọi kết quả đều xác định, **đúng một applied=true** cho một lần tạo khóa mới, các lần khác false.
5. Kiểm thử **conditional UPDATE** với trường **revision** và xác minh trạng thái cuối.
6. Phân biệt false, retry sau timeout, idempotency và cách đối soát dữ liệu.
7. Mở rộng kiểm thử từ node đơn sang cluster nhiều replica, multi-DC, sự cố và tải.
8. Ghi bằng chứng đủ để phát hiện regression, flakiness và lỗi nghiệp vụ trong CI/CD.

> **Giới hạn:** Ví dụ dùng API của **Apache Cassandra Java Driver 4.x** (namespace **com.datastax.oss.driver.api**) và JUnit 5. Cặp phiên bản Cassandra/driver/JDK, các exception và giới hạn LWT phải được xác minh với hệ thống đang dùng. Thực hiện phép thử cạnh tranh trên **cluster lab/staging cô lập**, không trên dữ liệu production.

## 2. Tại sao LWT cần kiểm thử cạnh tranh?

Một test tuần tự:

~~~text
INSERT IF NOT EXISTS → [applied]=true
INSERT IF NOT EXISTS → [applied]=false
~~~

chứng minh câu lệnh có điều kiện hoạt động trong tình huống **không có cạnh tranh**. Nó chưa chứng minh ứng dụng hoạt động đúng khi nhiều request khởi chạy cùng lúc. Các lỗi thực tế có thể nằm ở:

- API Java tạo **order_id mới cho mỗi lần retry**, dẫn tới nhiều bản ghi logic.
- Mỗi instance Spring Boot tự thực hiện **SELECT → INSERT** thay vì LWT.
- Một client đặt **LOCAL_SERIAL**, client khác có chính sách serial khác, nhưng invariant nghiệp vụ lại được giả định toàn cục.
- Sau **WriteTimeout/CAS timeout**, code đánh dấu thất bại và thử lại mà không đối soát.
- Repository/service gửi **email, tính tiền, publish event** ngay sau một future hoàn tất mà chưa kiểm tra **[applied]**.
- Test chỉ đếm kết quả true/false, bỏ qua exception hoặc không đối chiếu row cuối cùng.
- Tạo 100 task nhưng thread pool chỉ có 4 thread và các task không thật sự bắt đầu cạnh tranh.
- Chạy lại test với cùng khóa cũ khiến tất cả client nhận false, tạo false negative khó chẩn đoán.

**Integration test phải kiểm chứng cả ba lớp:** phản hồi của câu CQL, trạng thái dữ liệu cuối trong Cassandra và ý nghĩa nghiệp vụ khi các client thắng/thua.

## 3. Ngữ nghĩa [applied]: true, false và UNKNOWN

### 3.1. Bảng quyết định

| Kết quả Java quan sát | Có thể kết luận | Không được kết luận |
|---|---|---|
| CQL có điều kiện trả **[applied] = true** | Điều kiện thỏa và thao tác được xác nhận là áp dụng | Mọi bảng/partition khác cũng cập nhật atomic |
| CQL có điều kiện trả **[applied] = false** | Điều kiện không thỏa, thao tác có điều kiện **này** không áp dụng | Một request trước của cùng client chắc chắn chưa tạo dữ liệu |
| **Read/WriteTimeout**, CAS timeout hoặc lỗi mạng | Client thiếu kết quả cuối cùng cho lần thử đó | **[applied] = false**, hoặc “không có replica nào ghi” |
| **Overloaded/Unavailable** | Có vấn đề khả năng tiếp nhận/replica theo CL | Có thể retry vô hạn mà an toàn |
| **Driver request timeout/cancel** | Deadline phía client đã hết/luồng bị hủy | Coordinator chắc chắn ngừng hoặc rollback ghi |

Trong một thao tác INSERT IF NOT EXISTS, phản hồi false có thể mang thêm những giá trị hiện có của row, tùy cú pháp CQL/driver/server. Không nên viết test lệ thuộc vào **một định dạng chi tiết của các cột trả về khi false** mà chưa kiểm chứng version. Thông tin ổn định nhất để xác định **thao tác này có được áp dụng không** là trường **[applied]** của kết quả điều kiện.

### 3.2. Tình huống false sau retry

~~~mermaid
sequenceDiagram
    participant J as Java client A
    participant C as Cassandra
    J->>C: INSERT IF NOT EXISTS (claim=K, owner=A)
    C-->>C: Điều kiện true, dữ liệu được áp dụng
    C--xJ: Phản hồi bị mất / client timeout
    J->>C: Retry cùng claim=K
    C-->>J: [applied] = false (K đã tồn tại)
    J->>C: SELECT K để đối soát
    C-->>J: K có owner=A
~~~

Nếu client A thấy false trong lần thử sau, **nó không thể kết luận người khác đã thắng**. Lần đầu của chính A có thể đã thành công. Lớp nghiệp vụ cần **idempotency key**, owner/request fingerprint và quy tắc đối soát để trả về “đã thực hiện bởi request này” khi phù hợp.

Ngược lại, nếu row tồn tại với **owner=B** và fingerprint khác, có thể là một cạnh tranh/xung đột thật. Phải phân biệt hai tình huống bằng dữ liệu nghiệp vụ, không chỉ boolean.

### 3.3. LWT có phạm vi, không phải transaction đa bảng toàn cục

LWT giúp phối hợp **conditional mutation trong phạm vi partition** theo cơ chế Cassandra hỗ trợ. Nó **không** tạo một giao dịch ACID có rollback xuyên nhiều partition, nhiều bảng và dịch vụ bên ngoài.

Ví dụ:

1. INSERT IF NOT EXISTS trên bảng **claim_by_key** trả true.
2. App ghi một row vào **events_by_tenant_day**.
3. App gửi thông báo qua message broker.

Nếu bước 2 hoặc 3 lỗi, bước 1 không tự bị rollback. Kiểm thử cạnh tranh phải tách **bất biến của một khóa** với **hợp đồng end-to-end**, và nếu cần thì dùng outbox, projection idempotent hay reconciliation.

## 4. Regular consistency và serial consistency trong LWT

LWT có hai loại mức nhất quán cần phân biệt:

| Thuộc tính | Mục đích | Giá trị minh họa |
|---|---|---|
| **Regular consistency level** | Mức xác nhận/commit của thao tác theo quy tắc request | **LOCAL_QUORUM** |
| **Serial consistency level** | Phạm vi phối hợp điều kiện/Paxos cho thao tác có **IF** | **LOCAL_SERIAL** hoặc **SERIAL** |

Trên Java Driver 4.x:

~~~java
BoundStatement statement = prepared.bind(
        tenantId, claimId, "client-A", "CLAIMED", 0)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL);
~~~

**Không nhầm** LOCAL_QUORUM là serial consistency. Một regular CL cao **không làm một SELECT rồi INSERT thành CAS**.

### 4.1. RF = 3 tại một datacenter

Với keyspace có **RF = 3** ở **dc1**, LOCAL_QUORUM thông thường cần phản hồi **hai trong ba replica local**. LOCAL_SERIAL điều phối pha serial trong local DC theo chính sách LWT của Cassandra.

Điều kiện kiểm thử phải ghi rõ **RF, số node sống, snitch/topology/DC và CL của từng statement**. Một test chỉ có một node và RF = 1 có thể xác minh API/điều kiện đơn giản, nhưng **không chứng minh hành vi khi replica lỗi, quorum hoặc multi-DC**.

### 4.2. SERIAL và LOCAL_SERIAL trên nhiều DC

- **SERIAL** liên quan pha serial consensus ở phạm vi rộng hơn trong cấu hình nhiều DC.
- **LOCAL_SERIAL** giới hạn pha serial theo local DC, nhằm giảm phụ thuộc liên DC nhưng thay đổi phạm vi phối hợp.
- Nếu **invariant yêu cầu duy nhất trên toàn bộ các datacenter**, không tự cho rằng LOCAL_SERIAL từ hai DC khác nhau bảo đảm cùng một thứ tự điều kiện toàn cục.
- Không trộn chính sách SERIAL và LOCAL_SERIAL cho những writers cùng duy trì một invariant khi chưa có phân tích/kiểm thử đúng version.
- Trong bài test một DC, việc dùng LOCAL_SERIAL phải được ghi rõ; bài test multi-DC phải có kịch bản cạnh tranh từ **cả hai DC**, không chỉ một Java client ở dc1.

**LWT không miễn phí:** Paxos có thêm lượt trao đổi và cạnh tranh trên cùng partition có thể làm tăng latency, CAS contention, timeout và tài nguyên. Không áp dụng LWT cho mọi event độc lập chỉ để “thật chắc chắn”.

## 5. Thiết kế CQL fixture: một khóa, một tranh chấp

### 5.1. Keyspace và replication

Trên **cluster lab ba node thuộc dc1**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lwt_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

Đây là **cấu hình thử nghiệm giả định**. Trên Cassandra test một node, phải dùng RF và CL hợp lệ cho lab, đồng thời ghi nhận giới hạn kiểm chứng. Không sửa replication production chỉ để làm bài test.

### 5.2. Bảng claim có partition một bản ghi

~~~sql
CREATE TABLE IF NOT EXISTS lwt_lab.claim_by_key (
    tenant_id uuid,
    claim_id uuid,
    owner_token text,
    state text,
    revision int,
    PRIMARY KEY ((tenant_id, claim_id))
);
~~~

**Giải thích:**

- **(tenant_id, claim_id)** là **composite partition key**. Mỗi claim logic được đặt vào một partition riêng theo khóa kết hợp.
- **owner_token** phân biệt client/request nắm claim; **state** là trạng thái; **revision** dùng cho CAS update.
- Bảng có một row cho mỗi partition. Điều này làm phạm vi LWT của từng claim rõ ràng và tránh tất cả đơn của một tenant tranh chấp trên cùng partition tenant.
- Hai INSERT có cùng partition key nhưng khác **owner_token** sẽ tranh cùng một điều kiện **IF NOT EXISTS**.
- Các claim khác nhau có partition khác nhau, cho phép kiểm thử mức cạnh tranh khác nhau và phân phối token; không tự động gom tất cả vào một batch LWT.

**Cassandra không thay PRIMARY KEY bằng ALTER TABLE theo cách ứng dụng quan hệ hay làm**. Nếu muốn đổi khóa từ (tenant_id, claim_id) sang (tenant_id) thì cần bảng mới, backfill và đổi truy vấn, không phải đổi annotation Java rồi giữ nguyên dữ liệu.

### 5.3. Conditional INSERT

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'client-A',
    'CLAIMED',
    0
) IF NOT EXISTS;
~~~

Thực hiện lại **cùng key** (hoặc thử với **owner_token = 'client-B'**):

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'client-B',
    'CLAIMED',
    0
) IF NOT EXISTS;
~~~

Nếu thao tác đầu trả true và không có xóa/biến đổi xen giữa, thao tác kế tiếp nhận false vì claim đã tồn tại. **Bài test cạnh tranh** sẽ điều khiển nhiều client phát cùng lúc, không chỉ thực hiện tuần tự như cqlsh.

### 5.4. Conditional UPDATE theo revision

Giả sử claim đang có **revision = 0**:

~~~sql
UPDATE lwt_lab.claim_by_key
SET state = 'COMMITTED',
    revision = 1,
    owner_token = 'worker-A'
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND claim_id = 22222222-2222-4222-8222-222222222222
IF revision = 0;
~~~

Khi nhiều client cùng gửi câu **IF revision = 0** với owner_token khác nhau, chỉ một lần thay đổi điều kiện từ revision 0 sang 1 có thể trả **applied=true** khi tất cả lần thử hoàn tất xác định và không có writer khác đảo revision. Những lần còn lại false.

**Đừng nhầm revision với MVCC đầy đủ:** đây là một trường do ứng dụng duy trì. Một writer khác bỏ qua điều kiện, hoặc update dựa trên timestamp/cấu hình khác, có thể phá quy tắc. Mọi writer quản lý revision phải tuân thủ cùng hợp đồng.

## 6. Ma trận bất biến cần kiểm chứng

| Test | Tiền điều kiện | Các hành động | Điều phải đúng khi mọi kết quả xác định |
|---|---|---|---|
| **T1 — create race** | Key chưa tồn tại | N client cùng **INSERT IF NOT EXISTS** | **Đúng 1 true**, N − 1 false; row cuối thuộc winner |
| **T2 — duplicate request** | Key chưa tồn tại | Gửi lần đầu rồi gửi lại cùng owner/fingerprint | Lần đầu true; lần sau false nhưng cùng dữ liệu nghiệp vụ |
| **T3 — update race** | revision = 0 | N client cùng **UPDATE ... IF revision = 0** | **Đúng 1 true**, revision cuối = 1 và owner của winner |
| **T4 — sequential CAS** | revision = 0 | CAS 0→1 rồi CAS 1→2 | Cả hai true khi đúng thứ tự, revision cuối = 2 |
| **T5 — stale expected revision** | revision = 2 | UPDATE IF revision = 1 | False; row không bị thay bởi thao tác đó |
| **T6 — different keys** | N key mới | Mỗi client claim một key khác nhau | Mỗi key độc lập có thể true; không đếm một winner cho tất cả key |
| **T7 — timeout/unknown** | Không biết trạng thái sau attempt | Timeout giữa quá trình | Test báo **UNKNOWN/ERROR**, không tính là false |
| **T8 — multi-DC** | Có ít nhất hai DC, RF/serial policy phù hợp | Writers từ cả hai DC cạnh tranh cùng key | Invariant được kiểm tra theo chính sách được hỗ trợ, không suy từ lab một DC |

**Bất biến “đúng một true” có giả định**: ban đầu row không tồn tại, không có client khác đang thay đổi/xóa row, mọi attempt trả phản hồi cuối cùng bình thường, tất cả cùng dùng cơ chế LWT và phạm vi serial CL đúng, test không tự retry làm xuất hiện các thao tác không đếm được.

Nếu có **timeout** hoặc exception, test không nên chấp nhận mơ hồ là “0 winner”. Khi đó phải báo rõ **inconclusive** và đối soát row cùng log/metrics.
## 7. Kiểm thử JUnit 5: N client cùng INSERT IF NOT EXISTS

### 7.1. Điều kiện chạy

Trước phép thử:

1. Tạo **keyspace và bảng** ở mục 5 trên cluster thử nghiệm.
2. Bảo đảm tên **local datacenter** của driver đúng với cluster, ví dụ **dc1**.
3. Nếu dùng RF = 3 và LOCAL_QUORUM, phải có đủ replica khỏe trong dc1.
4. Cấu hình **TLS/auth** của môi trường nếu bắt buộc; mã ví dụ lược bỏ để tập trung vào LWT.
5. Chạy bằng **JUnit Jupiter (JUnit 5)** và **Java Driver 4.x**; không cần Spring Boot để hiểu bản chất phép thử.
6. Mỗi test dùng **UUID mới** cho tenant/claim, không phụ thuộc trạng thái của lần chạy trước.

Điều tối quan trọng: tạo **N worker threads** và dùng **CountDownLatch** làm điểm bắt đầu đồng thời. Nếu chỉ gọi INSERT trong một vòng for tuần tự, không có thử nghiệm cạnh tranh đúng nghĩa.

### 7.2. Code hoàn chỉnh cho một integration test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.InetSocketAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import org.junit.jupiter.api.Test;

public class ClaimContentionIT {
    private static final int CONTENDERS = 8;

    private static final class Attempt {
        final String actor;
        final boolean applied;

        Attempt(String actor, boolean applied) {
            this.actor = actor;
            this.applied = applied;
        }
    }

    @Test
    void exactlyOneAppliedWhenClaimingNewKey()
            throws Exception {

        UUID tenantId = UUID.randomUUID();
        UUID claimId = UUID.randomUUID();

        // Test lab: thay contact point/DC và bảo mật nếu cần.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement claim = session.prepare(
                "INSERT INTO lwt_lab.claim_by_key " +
                "(tenant_id, claim_id, owner_token, " +
                "state, revision) VALUES (?, ?, ?, ?, ?) " +
                "IF NOT EXISTS");

            PreparedStatement verify = session.prepare(
                "SELECT owner_token, state, revision " +
                "FROM lwt_lab.claim_by_key " +
                "WHERE tenant_id = ? AND claim_id = ?");

            ExecutorService workers =
                Executors.newFixedThreadPool(CONTENDERS);
            CountDownLatch ready =
                new CountDownLatch(CONTENDERS);
            CountDownLatch start =
                new CountDownLatch(1);
            List<Future<Attempt>> futures =
                new ArrayList<>();

            try {
                for (int i = 0; i < CONTENDERS; i++) {
                    final String actor = "client-" + i;

                    futures.add(workers.submit(() -> {
                        ready.countDown();

                        // Cùng đợi một tín hiệu để bắt đầu.
                        if (!start.await(
                                10, TimeUnit.SECONDS)) {
                            throw new TimeoutException(
                                "start barrier timed out");
                        }

                        BoundStatement statement = claim.bind(
                                tenantId, claimId,
                                actor, "CLAIMED", 0)
                            .setConsistencyLevel(
                                DefaultConsistencyLevel
                                    .LOCAL_QUORUM)
                            .setSerialConsistencyLevel(
                                DefaultConsistencyLevel
                                    .LOCAL_SERIAL);

                        Row outcome =
                            session.execute(statement).one();

                        if (outcome == null) {
                            throw new IllegalStateException(
                                "LWT did not return a row");
                        }

                        return new Attempt(
                            actor,
                            outcome.getBoolean("[applied]"));
                    }));
                }

                assertTrue(
                    ready.await(10, TimeUnit.SECONDS),
                    "Not all contenders reached barrier");

                start.countDown();

                int winners = 0;
                String winningActor = null;

                for (Future<Attempt> future : futures) {
                    // Timeout/exception => test FAIL,
                    // tuyệt đối không đổi thành applied=false.
                    Attempt attempt =
                        future.get(30, TimeUnit.SECONDS);
                    if (attempt.applied) {
                        winners++;
                        winningActor = attempt.actor;
                    }
                }

                assertEquals(
                    1, winners,
                    "Exactly one conditional insert should win");

                Row stored = session.execute(
                    verify.bind(tenantId, claimId)
                        .setConsistencyLevel(
                            DefaultConsistencyLevel
                                .LOCAL_QUORUM))
                    .one();

                assertNotNull(stored);
                assertEquals(
                    winningActor,
                    stored.getString("owner_token"));
                assertEquals(
                    "CLAIMED",
                    stored.getString("state"));
                assertEquals(
                    0,
                    stored.getInt("revision"));
            } finally {
                // Giải phóng worker dù assertion/attempt lỗi.
                start.countDown();
                workers.shutdownNow();
            }
        }
    }
}
~~~

### 7.3. Giải thích vì sao harness có giá trị

- **N = 8** worker đều đợi ở latch **start**; các tác vụ được “mở cổng” cùng thời điểm logic, tạo cơ hội tranh chấp thực sự.
- **CqlSession** có thể dùng chung cho các request từ nhiều thread; không tạo một session mới cho từng contender.
- **PreparedStatement** dùng chung, mỗi worker tạo **BoundStatement riêng** với owner_token của mình. Không dùng chung statement mutable để gán giá trị.
- Mỗi request dùng **cùng tenantId + claimId**, nhưng **owner_token khác nhau** để nhận biết winner. Nếu mỗi worker sinh claimId riêng, đó không phải race trên cùng khóa.
- **getBoolean("[applied]")** chỉ đọc trên result trả về thành công. Nếu server/driver throw exception, Future hoàn thành lỗi và **future.get** làm test fail, chứ không biến nó thành false.
- Đếm **exactly one** áp dụng trên kết quả xác định, sau đó đọc lại bằng **LOCAL_QUORUM** và xác minh **owner_token, state, revision**.
- **shutdownNow()** trong finally dừng thêm việc phía Java, nhưng không hứa hủy một mutation đã gửi tới Cassandra. Test sử dụng ID cô lập nên outcome lỡ đến muộn không ghi đè dữ liệu production.
- Timeout **10/30 giây** chỉ là ngưỡng của bài test minh họa; có thể điều chỉnh theo môi trường CI, nhưng không xem ngưỡng lớn hơn là cách chữa CAS contention hoặc cluster quá tải.

### 7.4. Vì sao không khẳng định “bắt đầu đúng cùng một nanosecond”?

**CountDownLatch** giúp N task cùng nhận tín hiệu nhưng thread scheduler, driver, network và coordinator vẫn có độ lệch. Điều ta kiểm tra là **nhiều thao tác có thể giao nhau về thời gian** và vẫn thỏa invariant LWT, không phải chứng minh tất cả packet đến server cùng một nanosecond.

Muốn chứng minh cuộc cạnh tranh thực sự diễn ra, có thể bổ sung **start timestamp**, **end timestamp**, thời gian mỗi attempt và CAS contention metrics trên cluster. Nếu test chạy quá nhanh theo trình tự, tăng số contenders hoặc giới hạn phân phối nhưng **không cố thêm sleep tùy tiện để ép một thứ tự chiến thắng**.

## 8. Test thứ hai: nhiều client cùng CAS revision 0 → 1

Phép thử tạo claim ở trạng thái **revision = 0**, rồi N workers cùng cố thay đổi sang revision = 1 nhưng mỗi worker có **owner_token khác nhau**.

### 8.1. Setup state rõ ràng

Dùng CQL có điều kiện để tạo dữ liệu đầu:

~~~sql
INSERT INTO lwt_lab.claim_by_key (
    tenant_id, claim_id, owner_token, state, revision
) VALUES (?, ?, 'seed', 'CLAIMED', 0)
IF NOT EXISTS;
~~~

Khi chạy test qua driver, phải **kiểm tra applied=true** cho setup. Nếu false, key có thể đã tồn tại và test không còn tiền điều kiện hợp lệ. Tốt nhất dùng UUID mới cho mỗi test.

### 8.2. Conditional UPDATE

~~~sql
UPDATE lwt_lab.claim_by_key
SET state = ?,
    revision = ?,
    owner_token = ?
WHERE tenant_id = ?
  AND claim_id = ?
IF revision = ?;
~~~

Mỗi contender bind **state = COMMITTED**, **revision mới = 1**, **owner_token riêng**, cùng khóa và **expected revision = 0**.

**Bất biến kỳ vọng:** khi mọi attempt trả kết quả cuối bình thường, đúng một true, các attempt sau nhận false; row cuối **revision = 1** và **owner_token** thuộc winner.

### 8.3. Đoạn test mở rộng

Đây là method JUnit đặt trong lớp test có imports/lifecycle tương đương mục 7:

~~~java
@Test
void exactlyOneCasUpdateWins() throws Exception {
    UUID tenantId = UUID.randomUUID();
    UUID claimId = UUID.randomUUID();
    int contenders = 8;

    try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build()) {

        PreparedStatement seed = session.prepare(
            "INSERT INTO lwt_lab.claim_by_key " +
            "(tenant_id, claim_id, owner_token, state, revision) " +
            "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS");

        Row seeded = session.execute(seed
            .bind(tenantId, claimId, "seed", "CLAIMED", 0)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_SERIAL))
            .one();

        assertNotNull(seeded);
        assertTrue(seeded.getBoolean("[applied]"));

        PreparedStatement cas = session.prepare(
            "UPDATE lwt_lab.claim_by_key " +
            "SET state = ?, revision = ?, owner_token = ? " +
            "WHERE tenant_id = ? AND claim_id = ? " +
            "IF revision = ?");

        PreparedStatement verify = session.prepare(
            "SELECT owner_token, state, revision " +
            "FROM lwt_lab.claim_by_key " +
            "WHERE tenant_id = ? AND claim_id = ?");

        ExecutorService pool =
            Executors.newFixedThreadPool(contenders);
        CountDownLatch ready =
            new CountDownLatch(contenders);
        CountDownLatch start =
            new CountDownLatch(1);
        List<Future<Attempt>> results =
            new ArrayList<>();

        try {
            for (int i = 0; i < contenders; i++) {
                final String owner = "updater-" + i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new TimeoutException("barrier timeout");
                    }

                    BoundStatement update = cas.bind(
                            "COMMITTED", 1, owner,
                            tenantId, claimId, 0)
                        .setConsistencyLevel(
                            DefaultConsistencyLevel.LOCAL_QUORUM)
                        .setSerialConsistencyLevel(
                            DefaultConsistencyLevel.LOCAL_SERIAL);

                    Row result = session.execute(update).one();
                    if (result == null) {
                        throw new IllegalStateException(
                            "Missing CAS outcome");
                    }
                    return new Attempt(
                        owner, result.getBoolean("[applied]"));
                }));
            }

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            int winnerCount = 0;
            String winner = null;
            for (Future<Attempt> future : results) {
                Attempt outcome =
                    future.get(30, TimeUnit.SECONDS);
                if (outcome.applied) {
                    winnerCount++;
                    winner = outcome.actor;
                }
            }
            assertEquals(1, winnerCount);

            Row stored = session.execute(
                verify.bind(tenantId, claimId)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            assertNotNull(stored);
            assertEquals(1, stored.getInt("revision"));
            assertEquals("COMMITTED", stored.getString("state"));
            assertEquals(winner, stored.getString("owner_token"));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

**Điều kiện để ghép code:** class phải chứa **Attempt** như mục 7 và các imports **JUnit, java.util.concurrent, CqlSession** tương ứng. Mã ở mục 7 và 8 là **hai test method độc lập**. Khi triển khai thực tế, nên factor phần barrier/race runner thành helper chung để tránh copy/paste; giữ test chính dễ đọc.

### 8.4. Khi nào vẫn có “hai true” hợp lệ?

Nếu bài test **không dùng cùng khóa**, nếu có một thao tác khác **reset revision về 0** giữa các attempts, hoặc nếu các câu lệnh điều kiện được đặt trên **những partitions khác nhau**, thì có thể thấy nhiều true mà không vi phạm chính sách LWT của một partition. Test cần kiểm soát:

- Partition key và clustering key (nếu có) giống nhau.
- Không có writer khác reset/xóa row.
- Seed state chính xác và được quan sát bằng CL phù hợp.
- Mọi actor dùng câu điều kiện/serial policy tương đương.
- Thời gian và outcome của từng attempt được ghi rõ.

Đó là lý do không nên chỉ assert số true mà không xác minh **tiền điều kiện + dữ liệu cuối**.

## 9. Đoạn Java async: kết hợp kết quả [applied] qua CompletionStage

Một số ứng dụng Spring WebFlux hoặc Java service không muốn block worker thread cho I/O Cassandra. Có thể thực thi LWT bằng **executeAsync** và chuyển mỗi kết quả về một outcome chứa boolean.

~~~java
import java.util.Iterator;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class AsyncClaimClient {
    private final CqlSession session;
    private final PreparedStatement insert;

    public AsyncClaimClient(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO lwt_lab.claim_by_key " +
            "(tenant_id, claim_id, owner_token, state, revision) " +
            "VALUES (?, ?, ?, ?, ?) IF NOT EXISTS");
    }

    public CompletionStage<Boolean> claim(
            UUID tenantId, UUID claimId, String owner) {
        BoundStatement statement = insert
            .bind(tenantId, claimId, owner, "CLAIMED", 0)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_SERIAL);

        return session.executeAsync(statement).thenApply(page -> {
            Iterator<Row> iterator =
                page.currentPage().iterator();
            if (!iterator.hasNext()) {
                throw new IllegalStateException(
                    "LWT result is missing [applied]");
            }
            return iterator.next().getBoolean("[applied]");
        });
    }
}
~~~

**Giải thích:**

- Stage thành công chỉ chứa **true hoặc false** khi driver/server đã trả một kết quả LWT bình thường.
- Stage thất bại **exceptionally** nếu timeout/lỗi, không bị chuyển thành false.
- Không gọi **join/get** trong driver callback hoặc reactive event loop.
- **AsyncResultSet.currentPage** phù hợp vì kết quả conditional DML thông thường chỉ cần hàng chứa **[applied]**; không biến thao tác này thành luồng phân trang dữ liệu hàng nghìn row.
- Sử dụng session/prepared statement dùng chung, tránh tạo session cho mỗi HTTP request.

### 9.1. Nhiều async calls không đồng nghĩa barrier

Một đoạn như:

~~~java
for (int i = 0; i < 8; i++) {
    stages.add(client.claim(
        tenantId, claimId, "client-" + i));
}
~~~

khởi tạo nhiều request nhanh, nhưng không bảo đảm mọi call đã sẵn sàng cùng lúc. Test **CountDownLatch** ở mục 7 là minh họa tốt để kiểm soát thời điểm phát hành logic. Trong môi trường reactive, có thể tạo **completion gate** dùng chung hoặc barrier qua các workers rồi phát hành các lời gọi async, nhưng vẫn phải chấp nhận sai lệch scheduling/network.

### 9.2. Không che lỗi bằng exceptionally(false)

Anti-pattern:

~~~java
return client.claim(tenantId, claimId, owner)
    .exceptionally(error -> false);  // SAI ngữ nghĩa!
~~~

Dòng trên biến **timeout/Overloaded/network failure** thành **[applied]=false**, khiến API báo “không thắng” hoặc “đã tồn tại” dù mutation có thể đã được áp dụng.

Một cách rõ hơn là mô hình kết quả có **ba trạng thái** ở service:

~~~text
APPLIED_TRUE  : server trả [applied] = true
APPLIED_FALSE : server trả [applied] = false
UNKNOWN       : timeout/transport/error; cần kiểm tra trạng thái
~~~

Đây là **model ứng dụng**, không phải enum của Cassandra. UNKNOWN cần mang nguyên nhân, số attempt, khóa nghiệp vụ và chính sách đối soát, tránh log raw payload/secret.

## 10. Đánh dấu idempotent và retry: test phải quan sát cả attempt

Một lỗi phổ biến là giả định “có IF NOT EXISTS nên retry vô hạn sẽ an toàn”. Có hai tầng idempotency:

1. **Trạng thái dữ liệu:** cùng primary key và cùng nội dung, sau nhiều lần thử thường chỉ có một row logic.
2. **Kết quả nghiệp vụ/side effect:** lần đầu có thể trả true, lần sau false; nếu ứng dụng chỉ gửi message ở nhánh true, bị mất phản hồi có thể khiến workflow không được hoàn thành theo kỳ vọng. Nếu gửi message trước khi biết kết quả, có thể gửi trùng.

**setIdempotent(true)** chỉ cung cấp thông tin cho retry/speculative execution policy của driver; nó không bảo đảm toàn quy trình exactly-once. Với test cạnh tranh, mặc định nên **kiểm soát driver/app retry** để biết có bao nhiêu physical attempts, tránh ẩn tình huống kết quả không rõ.

### 10.1. Một bảng quyết định cho retry

| Hành động | Timeout trước khi client biết kết quả | Có thể tự retry không? |
|---|---|---|
| SELECT theo partition key | Thường không có mutation | Có thể retry giới hạn nếu còn deadline và tải cho phép |
| INSERT cùng khóa và cùng giá trị cố định | Row có thể đã được áp dụng | Chỉ retry theo idempotency contract, rồi đối soát |
| INSERT IF NOT EXISTS | Có thể đã true nhưng phản hồi mất | Không coi false sau retry là thất bại lần đầu; so owner/request fingerprint |
| UPDATE IF revision = 0 | Có thể đã đổi revision thành 1 | Đọc revision/owner trước khi quyết định tiếp |
| Counter increment | Có thể đã cộng | **Không retry mù** |
| Ghi Cassandra rồi gửi email | Side effect có thể xảy ra một phần | Cần outbox/deduplication/saga phù hợp |

Khi test giả lập timeout, hãy thu cả:

- Request identity và idempotency key.
- Thời gian gửi, deadline, số attempt ở driver/app/gateway.
- Kết quả true/false hoặc exception mỗi lần.
- Row cuối cùng theo khóa với CL thích hợp.
- Side effect ở sink (nếu tích hợp).
- Trạng thái **UNKNOWN** khi chưa đủ bằng chứng.

### 10.2. Retry không được thay đổi serial CL ngầm

Nếu một đường writer dùng **SERIAL** nhằm bảo vệ invariant rộng nhiều DC, một fallback tự chuyển sang **LOCAL_SERIAL** hoặc regular CL thấp hơn chỉ vì timeout có thể vi phạm thiết kế. Hãy có **execution profile** riêng cho LWT, kiểm tra hiệu lực và chỉ thay đổi theo quyết định có chủ đích.

### 10.3. Không coi applied=false là exception

**[applied]=false** là một **kết quả điều kiện hợp lệ**. Trong metrics, nên tách:

- **applied_true**: thao tác thành công theo điều kiện.
- **applied_false**: cạnh tranh/xung đột hoặc duplicate business request.
- **request_error**: timeout, unavailable, overloaded, network, protocol.
- **unknown_outcome**: chưa thể khẳng định đã thay đổi dữ liệu hay chưa.

Tỷ lệ false tăng có thể là dấu hiệu **contention**, khóa nghiệp vụ bị dùng trùng hoặc retry của cùng request — không nên tự gộp vào “database error rate”.

## 11. Chạy thử trên node đơn khác cluster nhiều replica

**Một Cassandra container** giúp kiểm thử API CQL, schema, mapping và logic ứng dụng, nhưng không mô phỏng đầy đủ điều kiện phân tán.

| Môi trường | Kiểm chứng được | Chưa thể suy ra |
|---|---|---|
| **Một node, RF = 1** | INSERT IF NOT EXISTS, [applied], serial syntax cơ bản, Java mapping | Quorum RF3, network partitions, CAS với replica hỏng, multi-DC |
| **Ba node trong một DC, RF = 3** | LOCAL_QUORUM, LOCAL_SERIAL, replica lỡ nhịp, contention trong DC | Invariant liên DC, cross-region latency |
| **Nhiều DC đại diện** | Writers ở từng DC, SERIAL/LOCAL_SERIAL policy, phân vùng mạng có kiểm soát | Mọi tình huống của production nếu hardware/load khác |
| **Production** | Quan sát SLO/error thật ở workload thật | Không phải môi trường để cố tình gây lỗi/đụng dữ liệu người dùng |

Trong CI nhanh, có thể dùng **Testcontainers** để khởi tạo một Cassandra node ngắn hạn (với module và image pin version đã được phê duyệt). Trên node đó cần schema **RF = 1** phù hợp, và ghi rõ rằng phép test chỉ xác nhận **ngữ nghĩa cơ bản**. Để xác thực quorum hoặc mất replica, dùng **môi trường nhiều node** trong pipeline chuyên biệt.

**Không hard-code đường import/container API Testcontainers** nếu version chưa xác minh. Testcontainers Cassandra module và API có thể khác theo phiên bản; hãy chọn dependency phù hợp BOM/build hệ Java hiện tại, xác minh tài liệu của bản đã khóa và test thành công trong CI. Không cần giả lập production nhiều DC bằng một container rồi kết luận về global consistency.

## 12. Tính độc lập và khả năng lặp lại của test

Một integration test cạnh tranh dễ trở thành flaky nếu không kiểm soát môi trường:

1. **Mỗi test sinh tenantId/claimId mới**. Không tái dùng UUID cố định qua nhiều lần chạy CI.
2. **Không chạy hai suite dùng cùng keyspace/fixture** nếu test có thao tác xóa/truncate toàn bảng.
3. Schema nên được tạo qua **test setup/migration riêng**, không để mọi JUnit method hoặc mọi Spring context cùng gửi DDL.
4. Đợi schema agreement trước khi prepare statement.
5. Kiểm tra cluster health và đủ replica trước khi khởi động contention.
6. Không giả định thứ tự winner: **client-0 không nhất thiết thắng**. Chỉ assert đúng một winner và row cuối thuộc winner.
7. Đừng dùng **Thread.sleep** để suy thứ tự cuộc đua; dùng barrier và các assertion dựa trên invariant.
8. Ghi rõ timeout CI và giới hạn contention phù hợp năng lực cluster test.
9. Thu error/timeout/metrics riêng, không biến exception thành applied=false.
10. Sau test, dọn dữ liệu **chỉ trong keyspace lab** theo ownership, tránh tạo tombstone/truncate đồng thời ảnh hưởng test khác.

Với test dữ liệu lớn, dùng cluster test tạm có lifecycle rõ. **DELETE/TRUNCATE** cũng có chi phí và tính chất phân tán, không phải cleanup miễn phí.
## 13. Spring Boot/Spring Data: dùng test profile và schema được quản lý riêng

Với ứng dụng Spring Boot và Spring Data Cassandra, bài test thường muốn chạy qua **service/repository thực** thay vì tạo CqlSession từ đầu trong mỗi method. Cần phân biệt ba lớp:

1. **CqlSession/Java driver:** gửi CQL có điều kiện, nhận **[applied]** và các lỗi server.
2. **Service Spring:** chọn serial/regular CL, giữ idempotency key, ánh xạ false/unknown thành kết quả nghiệp vụ.
3. **HTTP/controller:** trả 201/200/409/503 hoặc kết quả thích hợp theo contract, không lộ dữ liệu nhạy cảm.

### 13.1. Context test không tự tạo schema

Một cách mô tả integration test:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "spring.cassandra.schema-action=none"
})
public class LwtSpringIntegrationIT {
    @Autowired
    private CqlSession session;

    @Test
    void serviceUsesRealCassandraSession() {
        // Chuẩn bị test fixture có khóa mới.
        // Gọi service thật để thực hiện IF NOT EXISTS.
        // Assert applied true/false + trạng thái lưu cuối.
        // Không chạy CREATE/DROP trong mỗi lần startup context.
    }
}
~~~

**Giới hạn của snippet:** Đây là skeleton, chưa phải phép thử hoàn chỉnh; method minh họa nơi gọi service và assertion. Cấu hình **spring.cassandra.schema-action** là tên thuộc tính cho hướng Spring Boot 3.x; Boot 2.x và phiên bản Spring Data khác có thể dùng namespace khác. Đối chiếu version, không dùng property vô hiệu mà tưởng framework đã tắt DDL.

Nên tạo schema lab bằng migration/test setup trước khi khởi tạo context hoặc trước khi chạy suite. Không để các **ApplicationRunner/@PostConstruct** tạo và drop bảng trên mỗi Spring Boot instance.

### 13.2. Vì sao cần test qua service ngoài test CQL trực tiếp?

Một phép CQL test thuần xác minh ngữ nghĩa LWT của cluster. Nhưng service có thể sai dù server trả đúng:

- Bắt exception rồi trả **boolean false**, làm mất trạng thái UNKNOWN.
- Phát **event “created”** trước khi kiểm tra [applied].
- Sau timeout, sinh **order_id mới** rồi retry; cùng yêu cầu tạo hai row khác partition.
- Dùng một execution profile cho SELECT, profile khác cho IF NOT EXISTS, serial CL thực sự không khớp thiết kế.
- Có nhiều service instance dùng **khác local DC** nhưng business contract giả định global uniqueness.
- Trộn **@Transactional** hoặc repository API của hệ quan hệ rồi suy rằng Cassandra có transaction xuyên nhiều row/bảng.

Do đó nên có **hai tầng integration tests**: test LWT CQL trực tiếp để xác minh database behavior và test endpoint/service để xác minh **mapping outcome + idempotency + side effects**.

### 13.3. Mẫu response nghiệp vụ rõ nghĩa

Giả sử tạo claim cho một request ID:

| Trạng thái service | Ngữ nghĩa | Hành động tầng API |
|---|---|---|
| **CREATED** | LWT true và row có fingerprint phù hợp | Trả trạng thái tạo mới |
| **ALREADY_OWNED_BY_SAME_REQUEST** | LWT false, đọc/đối soát row trùng idempotency key | Trả thành công idempotent theo contract |
| **CONFLICT** | LWT false, row thuộc request khác | Trả conflict nghiệp vụ |
| **UNKNOWN_RECONCILIATION_REQUIRED** | Timeout/transport hoặc dữ liệu chưa thể xác minh | Trả lỗi có thể theo dõi; không báo false/created |
| **UNAVAILABLE/OVERLOADED** | Cluster không đủ năng lực phục vụ | Bounded retry/backoff/shed load, không retry vô hạn |

HTTP status cụ thể (201, 200, 409, 503...) phụ thuộc API, nhưng **không nên dùng cùng một phản hồi “failed”** cho trường hợp điều kiện sai và outcome không xác định.

## 14. Kiểm thử concurrency ở nhiều mức tải

Một bài test với 8 contenders có ích, nhưng không đủ đánh giá contention ở workload cao.

### 14.1. Ma trận mức tranh chấp

| Kịch bản | Số khóa | Concurrent clients | Điều quan sát |
|---|---:|---:|---|
| **Hot key** | 1 | 2 / 8 / 32 | Đúng một winner khi tất cả kết quả xác định; CAS latency/false |
| **Independent keys** | 100 | 100 | Các keys độc lập có thể đều true; đo throughput |
| **Same tenant, multiple claims** | 100 | 100 | Partition key gồm claim_id nên không phải mọi request tranh cùng partition |
| **Mixed reads and CAS** | 1 | N readers + N writers | Quan sát dữ liệu/CL và điều kiện update |
| **Mixed DC writers** | 1 | Writers từ dc1 và dc2 | Kiểm thử SERIAL/LOCAL_SERIAL đúng phạm vi |
| **Injected failure** | 1 | N | Phân loại true/false/error/unknown và đối soát |
| **Backfill/compaction load** | nhiều | N | CAS latency, timeout và ảnh hưởng tới API |

Số **32/100** chỉ là ví dụ. Test lớn phải được **giới hạn concurrency, rate và tổng thời gian** để không gây quá tải ngoài ý muốn cho cluster thử nghiệm.

### 14.2. Race theo một khóa và test throughput là hai phép đo khác nhau

Nếu 1.000 clients cùng claim một khóa, serialization/contended Paxos có thể gây độ trễ cao. Điều này không đại diện cho throughput của 1.000 claims độc lập trên nhiều token ranges. Hãy tách:

- **Safety/correctness test:** bất biến một winner trong cùng partition.
- **Performance under contention:** latency/p99, failure rate và CAS contention.
- **Distributed throughput test:** nhiều partition keys, phân bố tenant/order ID thực tế.
- **Availability test:** mất replica/DC hoặc network partition.

Không lấy latency của hot key để đại diện cho mọi query, và không đánh giá correctness chỉ bằng throughput.

## 15. Kiểm thử khi timeout, replica lỗi và network gián đoạn

Phần quan trọng nhất của integration testing phân tán là **không ép mọi outcome thành boolean**.

### 15.1. Ba trạng thái phải được giữ riêng

~~~mermaid
flowchart TD
    A["Thực thi LWT"] --> B{"Nhận response hoàn chỉnh?"}
    B -->|Có| C{"[applied]?"}
    C -->|true| T["APPLIED_TRUE"]
    C -->|false| F["APPLIED_FALSE"]
    B -->|Không/exception| U["UNKNOWN hoặc ERROR có phân loại"]
    U --> R["Đối soát row theo khóa + request fingerprint"]
    R --> D{"Có đủ bằng chứng kết luận?"}
    D -->|Có| E["Báo outcome theo hợp đồng nghiệp vụ"]
    D -->|Không| I["INCONCLUSIVE; điều tra / retry có kiểm soát"]
~~~

Với request bị timeout:

1. Lưu **tenant_id + claim_id + owner/request fingerprint** đã gửi.
2. Không tự đổi claim_id ở retry.
3. Phân loại **server timeout**, **driver-side deadline**, **Overloaded**, **Unavailable**, **connection error**.
4. Đọc lại row theo partition key với CL được thiết kế.
5. So owner/fingerprint/version với request ban đầu.
6. Nếu đọc không đủ tin cậy hoặc mất replica, giữ trạng thái **UNKNOWN**, không tuyên bố thành công/thất bại.
7. Nếu nghiệp vụ cho phép thử lại, dùng **retry budget** và chính sách serial/regular CL không bị hạ ngầm.

**Không có test giả lập timeout đơn giản nào chứng minh mọi timeout đều xảy ra sau khi commit.** Cần quan sát timeline và dữ liệu thực để biết kết quả từng lần.

### 15.2. Kịch bản lỗi có kiểm soát

| Fault trong lab | Điều kiểm tra | Tránh giả định |
|---|---|---|
| Tăng độ trễ network tới một replica | Có đáp ứng CL/serial consensus và deadline không? | Một replica UP là luôn khỏe |
| Ngắt một replica của RF3 | Quorum/serial phase theo policy còn khả dụng không? | Tất cả requests vẫn phải success |
| Hủy response phía client | Đối soát nếu server có thể đã áp dụng | Timeout = false |
| Tạm ngắt liên DC | Invariant của SERIAL/LOCAL_SERIAL ở multi-DC | Một local test chứng minh global uniqueness |
| Disk/GC stress có giới hạn | CAS latency/timeout/Overloaded | Retry vô hạn làm tăng reliability |
| Retry trùng cùng request ID | False sau retry có được hiểu là same-request success không? | False = một client khác thắng |
| Client crash trước khi ghi outcome | Job có checkpoint/reconciliation không? | Không ghi log = không có mutation |

Chỉ dùng **fault injection/network shaping** trên cluster thử nghiệm được phê duyệt. Không cố tắt replica, phá disk hoặc cắt mạng production để học LWT.

### 15.3. Đặt tiêu chí pass/fail hợp lý khi có fault

Với **fault-free contention**, có thể assert **exactly one applied=true** và row cuối thuộc winner.

Với **fault-injection**, test cần tách hai nhóm:

- **Safety:** không quan sát được hai applied=true **không hợp lệ** cho cùng phiên bản trạng thái trong cùng phạm vi LWT, không có dữ liệu trái invariant.
- **Liveness/availability:** có bao nhiêu request hoàn tất, timeout/unavailable, latency và khả năng phục hồi khi fault kết thúc.

Khi một số attempt timeout, số **applied=true quan sát được** có thể là **0** dù row đã được tạo. Test phải báo **inconclusive/unknown outcome**, đọc và phân tích evidence, không đưa ra khẳng định sai rằng Cassandra “chưa ghi”.

## 16. Quan sát kết quả trong Java, Cassandra và CI

### 16.1. Kết quả kiểm thử có cấu trúc

Ví dụ một báo cáo chạy:

~~~yaml
suite: "lwt_contention_integration"
run_id: "ci-example-2026-11-21-01"
environment: "staging-lab"
cassandra_version: "<exact-version>"
java_driver_version: "<exact-version>"
jdk_version: "<exact-version>"
topology:
  datacenter: "dc1"
  nodes: 3
  replication_factor: 3
cql:
  table: "lwt_lab.claim_by_key"
  statement_shape: "INSERT ... IF NOT EXISTS"
  regular_consistency: "LOCAL_QUORUM"
  serial_consistency: "LOCAL_SERIAL"
test:
  contenders: 8
  partition_keys: 1
  fresh_fixture: true
outcomes:
  applied_true: 1
  applied_false: 7
  exceptions: 0
  unknown_outcomes: 0
verification:
  expected_winners: 1
  final_row_matches_winner: true
  status: "PASS"
evidence:
  ci_job: "<run-link>"
  test_logs: "<trace-id-location>"
  server_metrics: "<dashboard-or-snapshot>"
~~~

Đây là **format báo cáo minh họa**, không phải file cấu hình Cassandra hay output mặc định của driver. Trong CI thật, phải ghi cả **thời gian bắt đầu/kết thúc, query shape, bytes/latency, lỗi theo loại** và **phạm vi đã thử**. Không ghi raw tenant IDs, session tokens, payload hoặc thông tin cá nhân vào log.

### 16.2. Metrics quan trọng

| Tầng | Metric/thông tin | Vì sao cần |
|---|---|---|
| **Java test harness** | N contenders, barrier readiness, result true/false/error, duration | Kiểm chứng race thực sự và không nuốt lỗi |
| **Driver** | Retry count, coordinator, request timeout, local DC, CL/profile | Biết policy thực thi của client |
| **Cassandra LWT** | CAS latency, contention, timeout/failure theo phiên bản | Quan sát chi phí Paxos và áp lực hot key |
| **Cassandra cluster** | Replica UP/DOWN, RF/DC, read/write latency, unavailable | Đủ điều kiện trả kết quả theo CL? |
| **JVM/Storage** | GC pause, heap/native RSS, disk I/O/free, compaction backlog | Phân biệt lỗi do hạ tầng/tải nền |
| **Business service** | CREATED/CONFLICT/SAME_REQUEST/UNKNOWN, duplicated side effects | Test có bảo vệ invariant end-to-end không? |

Tên metric LWT cụ thể (CAS contention, read/write latency...) tùy Cassandra version và exporter/JMX mapping. Không giả định một tên Prometheus metric luôn tồn tại.

### 16.3. Kiểm tra cluster bằng công cụ chỉ đọc

~~~bash
# Health và DC/rack/token.
nodetool status

# Thông tin node và một số trạng thái vận hành.
nodetool info

# Pending/dropped messages và thread pools.
nodetool tpstats

# Công việc nền tiêu tốn I/O.
nodetool compactionstats

# Thống kê table/partition.
nodetool tablestats lwt_lab.claim_by_key
~~~

Đọc thêm server logs ở coordinator và replica, disk latency, GC và network. Một node **UP/NORMAL** vẫn có thể bị quá tải; compaction/repair có thể làm tail latency của LWT tăng.

**Không chạy repair theo phản xạ khi có applied=false.** False là kết quả điều kiện; repair là tác vụ đồng bộ replica theo cơ chế Cassandra, không “làm cho điều kiện thành true” và không biết bất biến nghiệp vụ của ứng dụng.

## 17. Sự khác nhau giữa test safety và test đúng luồng nghiệp vụ

Một test “đúng một winner” là điều kiện cần nhưng có thể chưa đủ.

Ví dụ API tạo đơn hàng:

~~~text
1. Claim orderId bằng LWT IF NOT EXISTS.
2. Ghi order detail vào bảng theo truy vấn.
3. Publish OrderCreated event.
4. Trả HTTP 201.
~~~

Giả sử bước 1 trả true, bước 2 thành công, bước 3 lỗi. LWT đã bảo vệ **uniqueness của claim**, nhưng sự kiện vẫn thiếu. Nếu request retry, bước 1 trả false. Nếu code coi false là conflict và ngừng, sự kiện có thể không bao giờ được phát.

Giải pháp kiểm thử cần xét:

- **Idempotency key** và fingerprint cho một request nghiệp vụ.
- Trạng thái tiến triển của workflow, ví dụ CLAIMED → STORED → PUBLISHED.
- Outbox/CDC hoặc durable event log nếu cần độ tin cậy thông điệp.
- Reconciliation/job tiếp tục từ trạng thái trung gian.
- Hợp đồng trả kết quả khi request trùng của **chính client**.
- Xử lý timeout không đồng nghĩa rollback bước 1.

**Không coi LWT là transaction đa hệ thống.** Một bài test concurrency cấp Cassandra nên được bổ sung bằng integration test cấp service/endpoint nếu sản phẩm có side effects bên ngoài.

## 18. Phát hiện và xử lý test flaky

Một test CAS đôi khi pass, đôi khi lỗi vì môi trường quá tải hoặc timing của barrier. Không nên sửa bằng cách **thêm Thread.sleep** vô hạn hay bỏ assertion.

### 18.1. Những nguồn flakiness

| Dấu hiệu | Nguyên nhân khả dĩ | Cách điều tra |
|---|---|---|
| 0 true, N false ngay lần đầu | Fixture không mới hoặc bị test khác chiếm | Log run ID, khóa fixture đã hash, chuẩn bị key mới |
| Future timeout | Cluster chậm, contention cao, timeout CI quá chặt | Xem CAS latency, disk/GC, retry/CL |
| Một số workers chưa đến barrier | Thread pool nhỏ hơn contenders, scheduler/CI quá tải | Pool size bằng N, ready latch có timeout rõ |
| Hai true trên các tests khác nhau | Các test dùng **khóa khác nhau** hoặc revision reset | So partition key, seed và writer khác |
| Schema unknown table | Migration/test setup chưa xong, schema chưa agreement | Tách lifecycle schema và job test |
| Applied=true nhưng row verify sai | Concurrent writer khác hoặc read policy/fixture sai | Cô lập test, kiểm tra CL, timestamp, data model |
| Applied=false sau retry | Lần trước có thể đã áp dụng | Đối soát owner/fingerprint, phân loại duplicate |
| Test pass một node, fail multi-DC | Khác RF/serial policy, network và thời gian | Ma trận topologies, kiểm chứng SERIAL/LOCAL_SERIAL |

### 18.2. Cách xử lý an toàn

1. Giữ **test inputs và run ID** để tái hiện có kiểm soát; không log thông tin nhạy cảm.
2. Phân loại **assertion failure, infrastructure failure, unknown outcome** riêng.
3. Thu **stack trace root cause**, không nuốt exception ở CompletableFuture/Future.
4. Phân tích các phiên bản driver/server và effective retry policy.
5. Kiểm tra schema agreement, cluster health và resource baseline.
6. Chạy lại trên test cluster cô lập sau khi xử lý nguyên nhân, không chỉ tăng timeout.
7. Nếu một fault test bất định, định nghĩa **bất biến safety** và điều kiện inconclusive rõ ràng thay vì đặt kỳ vọng liveness không thực tế.
8. Không đổi một bài kiểm thử lỗi nghiêm trọng thành “ignored” để pipeline xanh mà không có ticket/owner và kế hoạch khắc phục.

## 19. Bài tập tình huống và đáp án gợi ý

### Bài 1 — SELECT rồi INSERT có đủ mạnh không?

Hai client đọc cùng claim bằng LOCAL_QUORUM, cả hai thấy chưa có row, sau đó INSERT thông thường.

**Câu hỏi:** Có bảo đảm chỉ một client báo created không?

**Đáp án:** Không. LOCAL_QUORUM của hai request riêng không tạo atomic compare-and-set. Cần IF NOT EXISTS hoặc cơ chế uniqueness/idempotency phù hợp, và phải kiểm thử cạnh tranh.

### Bài 2 — Đếm applied khi N = 10

Một key hoàn toàn mới có 10 clients cùng INSERT IF NOT EXISTS, không có timeout hay writer bên ngoài. Kết quả gồm 1 true, 9 false.

**Câu hỏi:** Test đã đủ chưa?

**Đáp án:** Chưa hoàn toàn. Cần xác minh **row cuối có owner của winner**, giá trị state/revision đúng, cùng partition key và policy serial CL. Đồng thời ghi lại CL, RF/DC và timing.

### Bài 3 — Test nhận 0 true và một timeout

Với 8 workers, có 7 kết quả false và 1 timeout; SELECT cuối cho thấy claim đã tồn tại.

**Câu hỏi:** Có thể báo Cassandra vi phạm vì không có winner không?

**Đáp án:** Không. Worker timeout có thể đã áp dụng claim. Test phải đánh dấu **UNKNOWN/INCONCLUSIVE** và đối soát owner/fingerprint; không tính timeout thành false.

### Bài 4 — Retry thay đổi order ID

Client thử tạo order với orderId A, timeout, rồi sinh orderId B để retry.

**Câu hỏi:** LWT có ngăn hai order logic không?

**Đáp án:** Không. A và B thuộc hai partition keys khác nhau; hai lần có thể cùng áp dụng. Phải giữ orderId/idempotency key ổn định cho một request nghiệp vụ.

### Bài 5 — CAS revision

Row đang revision 3. Hai workers cùng UPDATE SET revision=4 IF revision=3, đều nhắm cùng partition.

**Câu hỏi:** Nếu mọi phản hồi hoàn chỉnh, kỳ vọng số true là bao nhiêu và phải kiểm tra gì?

**Đáp án:** Một true, một false nếu không có writer reset revision và cùng phạm vi LWT. Kiểm tra revision cuối = 4 và owner/state của winner.

### Bài 6 — Test không thật sự cạnh tranh

Một test tạo N = 20 tasks nhưng executor có 2 threads, mỗi task chờ đến khi tất cả 20 tasks báo ready.

**Câu hỏi:** Điều gì xảy ra?

**Đáp án:** Các task còn lại không được chạy để đếm ngược latch; test có thể deadlock/timeout. Dùng pool đủ threads cho barrier hoặc thiết kế barrier không chặn các worker chưa được schedule.

### Bài 7 — Single-node Testcontainers

Team chạy LWT trên một container Cassandra RF = 1, tất cả test true/false đều đạt. Họ kết luận hệ thống đảm bảo quorum RF = 3 và multi-DC.

**Câu hỏi:** Kết luận có hợp lý?

**Đáp án:** Không. Single-node test xác minh cú pháp/logic cơ bản; cần multi-node RF3 và kịch bản writers từ nhiều DC để kiểm chứng consistency/availability đúng topology.

### Bài 8 — LOCAL_SERIAL và hai DC

Hai service ở dc1/dc2 đồng thời claim cùng key, đều chọn LOCAL_SERIAL vì độ trễ thấp; nghiệp vụ yêu cầu uniqueness toàn hệ thống.

**Câu hỏi:** Có thể coi test chỉ tại dc1 là bằng chứng đủ?

**Đáp án:** Không. Phải đánh giá phạm vi consensus, phiên bản Cassandra, RF mỗi DC, serial policy của mọi writer và thực hiện test cross-DC; cân nhắc SERIAL cho invariant toàn cục theo tài liệu hỗ trợ.

### Bài 9 — Applied=false có phải lỗi cần retry?

Một request mới nhận [applied]=false vì đã có row do worker khác tạo.

**Câu hỏi:** Có nên retry liên tục tới khi true?

**Đáp án:** Không. False là kết quả điều kiện hợp lệ. Service nên trả conflict hoặc xử lý duplicate theo owner/fingerprint, không gây thêm CAS contention.

### Bài 10 — LWT true nhưng email bị lỗi

Client claim order thành công rồi gửi email thất bại. Retry toàn endpoint, LWT trả false.

**Câu hỏi:** Làm thế nào không bỏ sót email hoặc gửi trùng?

**Đáp án:** Theo dõi trạng thái workflow, outbox/event ID ổn định, sink idempotent và reconciliation. LWT chỉ bảo vệ claim, không transactionally commit email.

### Bài 11 — Khi test overload

Một test tăng lên 5.000 contenders trên cùng partition; xuất hiện Overloaded, WriteTimeout và p99 rất cao.

**Câu hỏi:** Có nên hạ LOCAL_QUORUM xuống ONE và tăng retries để “làm xanh test”?

**Đáp án:** Không. Đó là thay đổi hợp đồng consistency và có thể khuếch đại tải. Giảm concurrency, tách correctness test với load test, xem CAS contention/disk/GC và giới hạn test environment.

### Bài 12 — Bảng dữ liệu mới cho truy vấn khác

Ứng dụng cần query claim theo **owner_token** nhưng bảng chỉ có partition key **(tenant_id, claim_id)**.

**Câu hỏi:** Có thể thêm filter owner_token rồi yêu cầu LOCAL_QUORUM để truy vấn nhanh không?

**Đáp án:** CL không thay đổi access pattern. Cần thiết kế bảng/query mới theo owner với partition key thích hợp hoặc index được đánh giá theo phiên bản. Nếu duy trì hai bảng, cần idempotent projections và reconciliation; LWT ở bảng claim không tạo transaction liên bảng.

## 20. Checklist CI/CD cho kiểm thử LWT cạnh tranh

- [ ] Schema CQL/replication được tạo bằng setup/migration cô lập, chờ schema agreement trước khi test.
- [ ] Mỗi test dùng **tenantId + claimId mới**, không va chạm với suite khác.
- [ ] Mọi contenders dùng **cùng partition key** và cùng điều kiện để tạo race.
- [ ] Dùng **CountDownLatch/barrier** hoặc cơ chế đồng thời rõ, không chỉ một vòng gọi tuần tự.
- [ ] Đếm và lưu **applied_true**, **applied_false**, **errors**, **unknown** riêng.
- [ ] Không biến timeout/exception thành applied=false.
- [ ] Chỉ assert exactly-one true khi **mọi outcome xác định**, key mới và không có writer khác.
- [ ] Xác minh **row cuối** có owner/state/revision của winner bằng CL phù hợp.
- [ ] Kiểm thử thêm **UPDATE IF revision = ...** và stale expected revision.
- [ ] Kiểm tra trùng request của chính client sau timeout và idempotency key/fingerprint.
- [ ] Java service không phát side effect trước khi kiểm tra [applied] và không đồng nhất false với unknown.
- [ ] Regular CL/serial CL được đặt tường minh và phù hợp RF/DC.
- [ ] Không trộn SERIAL/LOCAL_SERIAL giữa writers khi chưa có chiến lược đồng thuận tương thích.
- [ ] Testcontainers một node chỉ dùng cho test cơ bản; multi-node/multi-DC có suite riêng.
- [ ] Không tạo/đóng CqlSession theo mỗi worker; dùng session thread-safe và prepared statements.
- [ ] Executor/futures có timeout và finally dọn resource, không để test treo vô hạn.
- [ ] Có retry budget, backoff/jitter khi fault injection; không tạo retry storm.
- [ ] Có test replica/network faults trên staging, không phá production.
- [ ] Theo dõi CAS contention, p95/p99, errors, RF/DC, disk/GC, compaction/repair khi thử tải.
- [ ] Không dùng repair như cách “sửa” applied=false hay hoàn tác ghi sai.
- [ ] Không log raw payload, credential, idempotency secret hoặc dữ liệu người dùng.
- [ ] Kết quả CI ghi rõ phiên bản Cassandra/driver/JDK, topology, CL, số contenders, durations và evidence.
- [ ] Phân biệt **correctness PASS**, **infrastructure error** và **INCONCLUSIVE** khi thiếu outcome.

## 21. Tổng kết

**Lightweight Transaction** giải quyết điều kiện **IF NOT EXISTS** hoặc **IF column = value** trong phạm vi Cassandra hỗ trợ, còn trường **[applied]** cho biết **lần thao tác có điều kiện nhận được phản hồi đó** có được áp dụng hay không. Khi nhiều client cạnh tranh cùng một khóa mới và mọi phản hồi xác định, test nên quan sát **đúng một true** và **trạng thái cuối thuộc winner**. Với CAS revision, chỉ một request đổi một phiên bản trạng thái cho cùng partition trong điều kiện thí nghiệm được kiểm soát.

**Timeout/exception không phải applied=false.** Lần đầu có thể đã thành công rồi mất phản hồi; retry có thể trả false vì chính request đã tạo row. Vì vậy test phải giữ **idempotency key**, đối soát row và phân biệt **APPLIED_TRUE / APPLIED_FALSE / UNKNOWN**.

Một bài test LWT đáng tin cậy kết hợp **barrier cạnh tranh, fixture cô lập, CQL/Java Driver integration, regular/serial consistency đúng RF/DC, xác minh dữ liệu cuối, test lỗi phân tán và observability**. Với Apache Cassandra, vẫn phải chú ý partition key, bảng thiết kế theo truy vấn, compaction/repair và khả năng phục vụ replica; tính đúng đắn của một LWT **không tự bảo đảm transaction đa bảng, exactly-once cho email/broker hay tính sẵn sàng dưới mọi sự cố**.
