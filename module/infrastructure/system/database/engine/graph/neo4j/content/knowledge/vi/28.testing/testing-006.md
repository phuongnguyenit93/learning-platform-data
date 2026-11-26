# Kiểm thử commit, rollback, xung đột ghi và retry trong Neo4j

## 1. Tại sao kiểm thử transaction không thể chỉ kiểm tra câu Cypher?

Trong **Neo4j property graph**, node và relationship được tạo, sửa hoặc xóa trong **transaction**. Một truy vấn Cypher có thể chạy đúng trên bộ dữ liệu nhỏ nhưng vẫn làm ứng dụng gặp lỗi khi hai request cùng ghi, một transaction bị rollback, kết nối mất ngay lúc commit, hoặc Java Driver tự chạy lại callback sau một lỗi tạm thời.

Bài này thuộc chương **Kiểm thử** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Mục tiêu là xây dựng những phép thử có thể lặp lại để xác nhận **kết quả dữ liệu sau commit và rollback**, phát hiện **lost update, xung đột uniqueness, deadlock**, đồng thời đánh giá **retry** của **Neo4j Java Driver** và các service dùng **Spring Data Neo4j**.

Sau khi học, bạn có thể:

1. Kiểm tra một transaction ghi được commit đầy đủ và được quan sát qua một Session khác.
2. Kiểm tra rollback chủ động và rollback khi callback/ứng dụng phát sinh exception.
3. Tạo lịch thực thi hai transaction đồng thời bằng barrier thay vì trông chờ `Thread.sleep()`.
4. Phân biệt lỗi **xung đột ghi**, **vi phạm constraint**, **deadlock** và **lỗi không rõ trạng thái commit**.
5. Kiểm tra phép tăng property trực tiếp tránh *lost update* và nhận diện cách đọc–tính–ghi không an toàn.
6. Thiết kế **retry hữu hạn, an toàn khi lặp lại**, không gây side effect bên ngoài transaction.
7. Tách unit test, repository integration test và concurrency/failure test cho ứng dụng Neo4j.

> **Phiên bản:** Các ví dụ Java dùng kiểu API `org.neo4j.driver` với `executeRead`/`executeWrite` trong Java Driver 5.x/6.x và JUnit 5. Ví dụ container chọn Neo4j **5.26** để cố định môi trường minh họa; khi triển khai cần ghép phiên bản DBMS, Driver, Testcontainers và Spring Data Neo4j theo dự án. Các mã lỗi và chi tiết khóa có thể thay đổi theo bản phát hành.

## 2. Hợp đồng transaction cần được kiểm chứng

Transaction có các tính chất **ACID**, nhưng bài kiểm thử phải diễn đạt đúng điều được hứa hẹn:

| Thuộc tính / hành vi | Phép thử thích hợp | Điều không được suy ra |
| --- | --- | --- |
| **Atomicity** | Một transaction ghi hai thứ rồi thất bại: không thứ nào được commit | Không có nghĩa từng câu query luôn không thể gặp lỗi |
| **Consistency** | Constraint và bất biến nghiệp vụ còn đúng sau commit | DB không tự hiểu mọi quy tắc đa-node của ứng dụng |
| **Isolation** | Hai Session độc lập chạy đồng thời, quan sát kết quả theo mức cô lập | Neo4j mặc định không phải serializable |
| **Durability** | Sau commit, Session khác đọc được kết quả; kiểm tra khôi phục nếu có yêu cầu vận hành | Một test đọc sau commit không chứng minh toàn bộ cơ chế phục hồi sau mất điện |
| **Idempotency** | Lặp yêu cầu với cùng khóa vẫn có một thực thể/cạnh | Retry một callback có side effect ngoài DB không tự an toàn |

Neo4j dùng **read committed** làm mức cô lập mặc định: không đọc được thay đổi **chưa commit** của transaction khác, nhưng các lần đọc trong một transaction **có thể thấy dữ liệu đã commit mới** của transaction khác. Do đó, test không nên mặc nhiên yêu cầu snapshot bất biến như một số cấu hình MVCC của hệ quản trị khác.

**Điều kiện quyết định của test transaction:** hãy đọc lại trạng thái bằng **một transaction/Session độc lập sau khi thao tác đang kiểm tra kết thúc**. Không lấy record được `RETURN` bên trong câu `SET` làm bằng chứng rằng commit đã thành công.

## 3. Ma trận kịch bản kiểm thử

| ID | Kịch bản | Kỳ vọng cần khẳng định |
| --- | --- | --- |
| C01 | `SET` rồi explicit `commit()` | Session mới thấy thay đổi |
| C02 | Tạo node và relationship trong cùng transaction rồi commit | Cả hai cùng tồn tại |
| R01 | `SET` rồi explicit `rollback()` | Dữ liệu sau rollback giữ giá trị cũ |
| R02 | Callback `executeWrite` ném exception sau khi đã chạy `SET` | Không có thay đổi nào của callback được commit |
| R03 | Ghi nhiều node rồi một bước vi phạm constraint | Toàn bộ transaction bị rollback nếu không commit được |
| I01 | Session A đọc, B ghi chưa commit, A đọc tiếp | A không được thấy dữ liệu chưa commit của B |
| I02 | B commit giữa hai lần A đọc | A có thể thấy hai giá trị khác nhau |
| W01 | Hai request đọc cùng giá trị cũ rồi ghi giá trị tính sẵn | Có thể xảy ra **lost update** |
| W02 | Hai request dùng `SET x.count = x.count + 1` | Hai lần tăng đều được bảo vệ khi cập nhật cùng property |
| U01 | Hai request tạo node với cùng unique business key | Không thể commit hai node trùng khóa nếu constraint đang hiệu lực |
| D01 | Hai transaction lấy khóa trên hai node theo thứ tự đối nghịch | Có thể có deadlock; giao dịch bị hủy không commit nửa vời |
| RT01 | Lỗi tạm thời trong managed transaction | Driver có thể chạy lại toàn bộ callback theo chính sách retry |
| RT02 | Client không biết commit đã xảy ra hay chưa | Lặp request có idempotency key không tạo bản ghi thứ hai |
| TO01 | Transaction vượt timeout có cấu hình | Báo lỗi/hủy phù hợp; tài nguyên được giải phóng |

**Không gộp tất cả vào một test khổng lồ.** Mỗi test phải kiểm tra một hợp đồng rõ ràng, có setup và teardown xác định; các test đồng thời cần kiểm soát thời điểm để giảm hiện tượng lúc pass lúc fail (*flaky test*).

## 4. Môi trường thực hành: Neo4j thật trong Testcontainers

### 4.1. Vì sao mock Driver không đủ?

Mock có ích để unit test khi service gọi repository thế nào, nhưng không chứng minh được:

- Cypher đúng cú pháp và ánh xạ property đúng kiểu.
- Transaction thật commit/rollback như kỳ vọng.
- Unique constraint thực sự được áp dụng.
- Hai request ghi cùng node sẽ chờ khóa hoặc gặp lỗi ra sao.
- Deadlock, timeout, routing hay hành vi của driver khi giao tiếp Bolt.

Vì vậy, các test về giao dịch phải chạy trên **Neo4j thật**, lý tưởng là một container độc lập. Không chạy ví dụ dọn dữ liệu của bài trên database sản xuất.

### 4.2. Bộ dữ liệu thử

Sử dụng hai loại node nhỏ:

```text
(:TxAccount {id: 'A', balance: 100, version: 0})
(:TxAccount {id: 'B', balance: 200, version: 0})

(:TxRequest {requestId, amount, state})
```

- `TxAccount` phục vụ kiểm thử cập nhật cùng node, thứ tự khóa và rollback.
- `TxRequest` phục vụ uniqueness và idempotency.
- `id` và `requestId` là **business key**, không sử dụng internal node ID để xác minh.

Tạo constraint phù hợp:

```cypher
CREATE CONSTRAINT tx_account_id_unique IF NOT EXISTS
FOR (a:TxAccount)
REQUIRE a.id IS UNIQUE;

CREATE CONSTRAINT tx_request_id_unique IF NOT EXISTS
FOR (r:TxRequest)
REQUIRE r.requestId IS UNIQUE;
```

Constraint là phần bắt buộc của môi trường test; chỉ dựa vào `MERGE` rồi kỳ vọng hai writer đồng thời không thể tạo bản sao là không đủ để chứng minh ràng buộc dữ liệu.

### 4.3. Fixture JUnit 5 + Testcontainers

Đoạn dưới đây thể hiện một lớp kiểm thử tích hợp. Dự án cần các dependency test tương thích: **JUnit Jupiter**, `org.testcontainers:neo4j`, `org.testcontainers:junit-jupiter` và `org.neo4j.driver:neo4j-java-driver`. Hãy khóa version trong build hoặc BOM của dự án; không tự trộn phiên bản chỉ vì ví dụ dùng API gần giống.

```java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class Neo4jTransactionIT {

    @Container
    static final Neo4jContainer<?> NEO4J =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword("test-password");

    private static Driver driver;

    @BeforeAll
    static void initDriverAndSchema() {
        driver = GraphDatabase.driver(
            NEO4J.getBoltUrl(),
            AuthTokens.basic("neo4j", "test-password"));
        driver.verifyConnectivity();

        try (Session session = newSession()) {
            // Mỗi câu lệnh tạo constraint có transaction riêng.
            session.run("""
                CREATE CONSTRAINT tx_account_id_unique IF NOT EXISTS
                FOR (a:TxAccount) REQUIRE a.id IS UNIQUE
                """).consume();
            session.run("""
                CREATE CONSTRAINT tx_request_id_unique IF NOT EXISTS
                FOR (r:TxRequest) REQUIRE r.requestId IS UNIQUE
                """).consume();
        }
    }

    @BeforeEach
    void resetFixture() {
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                // Chỉ xóa nhãn chuyên biệt trên database test.
                tx.run("MATCH (a:TxAccount) DETACH DELETE a").consume();
                tx.run("MATCH (r:TxRequest) DETACH DELETE r").consume();
                tx.run("""
                    CREATE (:TxAccount {
                      id: 'A', balance: 100, version: 0
                    })
                    """).consume();
                tx.run("""
                    CREATE (:TxAccount {
                      id: 'B', balance: 200, version: 0
                    })
                    """).consume();
                return null;
            });
        }
    }

    private static Session newSession() {
        return driver.session(SessionConfig.forDatabase("neo4j"));
    }

    private long balance(String id) {
        try (Session session = newSession()) {
            return session.executeRead(tx ->
                tx.run("""
                    MATCH (a:TxAccount {id: $id})
                    RETURN a.balance AS balance
                    """, Map.of("id", id))
                .single()
                .get("balance").asLong());
        }
    }

    @AfterAll
    static void closeDriver() {
        if (driver != null) driver.close();
    }

    // Đặt các @Test trong các mục sau vào lớp này.
}
```

**Lưu ý về fixture:**

- `@Container` khởi động Neo4j cho lớp test; cần Docker hoặc runtime container tương thích.
- Cố định image cho test để kết quả không thay đổi bất ngờ khi một tag `latest` di chuyển.
- Mỗi Session đều được đóng; `Driver` dùng chung cho cả lớp.
- `@BeforeEach` thay dữ liệu nền thành trạng thái xác định. **Không chạy các test dùng cùng fixture song song** nếu chúng có thể xóa/sửa dữ liệu của nhau; có thể dùng mỗi test một database/container hoặc tắt parallel execution của lớp.
- Lệnh `DETACH DELETE` chỉ áp dụng nhãn test trong **container dành riêng**. Tuyệt đối không biến fixture này thành script dọn dữ liệu production.

## 5. Test commit: nhìn trạng thái từ Session khác

### 5.1. Explicit transaction commit

Thêm method sau vào `Neo4jTransactionIT`:

```java
@Test
void commitMakesUpdateVisibleToAnotherSession() {
    try (Session writer = newSession()) {
        try (var tx = writer.beginTransaction()) {
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = 120
                """).consume();

            tx.commit();
        }
    }

    // balance() mở Session mới sau khi commit đã hoàn tất.
    assertEquals(120L, balance("A"));
}
```

**Vì sao `consume()` trước `commit()`?** Lệnh ghi phải được gửi/tiêu thụ đúng vòng đời. Kiểm tra `RETURN a.balance` từ chính transaction đang ghi chỉ chứng minh transaction đó thấy thay đổi của nó, **chưa chứng minh commit đã xảy ra**.

### 5.2. Tính nguyên tử trên nhiều thao tác

Một transfer mô phỏng phải sửa cả hai tài khoản trong **cùng transaction**:

```java
@Test
void transferCommitsBothChangesTogether() {
    try (Session session = newSession()) {
        session.executeWrite(tx -> {
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = a.balance - 30
                """).consume();
            tx.run("""
                MATCH (b:TxAccount {id: 'B'})
                SET b.balance = b.balance + 30
                """).consume();
            return null;
        });
    }

    assertAll(
        () -> assertEquals(70L, balance("A")),
        () -> assertEquals(230L, balance("B"))
    );
}
```

Đây là kiểm tra **hai cập nhật cùng commit**. Ví dụ chưa giải quyết bài toán nghiệp vụ tài chính hoàn chỉnh: ở hệ thống thật, cần kiểm tra đủ tiền, tránh *write skew*, tính toán số tiền đúng kiểu và xử lý retry/idempotency.

## 6. Test rollback: thay đổi không được tồn tại sau lỗi

### 6.1. Rollback chủ động

```java
@Test
void explicitRollbackRestoresOriginalValue() {
    try (Session session = newSession()) {
        try (var tx = session.beginTransaction()) {
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = 1
                """).consume();

            tx.rollback();
        }
    }

    assertEquals(100L, balance("A"));
}
```

Sau rollback, Session mới thấy giá trị cũ. Nếu chỉ đọc giá trị từ **chính transaction đang chạy trước rollback**, sẽ nhận kết quả sai về ý nghĩa kiểm thử.

### 6.2. Exception trong managed transaction

```java
@Test
void uncheckedExceptionRollsBackManagedTransaction() {
    assertThrows(IllegalStateException.class, () -> {
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (a:TxAccount {id: 'A'})
                    SET a.balance = 0
                    """).consume();
                throw new IllegalStateException("Reject this operation");
            });
        }
    });

    assertEquals(100L, balance("A"));
}
```

Vì callback không hoàn thành, managed transaction **không commit** thay đổi. Khi kiểm thử ứng dụng Spring, cần phân biệt thêm quy tắc rollback của `@Transactional`; xem mục 14.

### 6.3. Rollback phải bao phủ cả transaction, không chỉ câu cuối

Giả sử transaction đã ghi:

```cypher
MATCH (a:TxAccount {id: 'A'})
SET a.balance = 10;
```

Sau đó nó cố ghi một node `TxAccount` có `id = 'A'` khác, vi phạm unique constraint:

```cypher
CREATE (:TxAccount {id: 'A', balance: 999});
```

Khi transaction thất bại và bị rollback, **cập nhật balance = 10 ở câu trước không được commit**. Test cần mở Session khác và xác nhận `balance = 100`. Một lưu ý: lỗi constraint thuộc lớp **không nên retry mù**; nó thường là lỗi dữ liệu/logic cần xử lý, khác transient deadlock.

## 7. Read committed: đọc được gì giữa hai transaction?

Không phải mọi kiểm thử đồng thời đều kiểm thử *xung đột ghi*. Một bước cơ bản là phân biệt **chưa commit** và **đã commit**.

| Thời điểm | Transaction A | Transaction B |
| --- | --- | --- |
| T1 | Bắt đầu, đọc `balance = 100` | |
| T2 | | Bắt đầu, `SET balance = 80`, **chưa commit** |
| T3 | A đọc tiếp | B vẫn chưa commit |
| T4 | | B commit |
| T5 | A đọc tiếp | |

Ở T3, A **không được đọc giá trị 80 chưa commit** của B. Tùy tình huống khóa, truy vấn có thể phải đợi hoặc quan sát giá trị đã commit trước đó. Sau T4, A **có thể** đọc được `80` ở lần đọc mới — ví dụ của **non-repeatable read** theo read committed.

**Cách thiết kế test:** điều khiển thứ tự đọc/ghi bằng `CountDownLatch` hoặc cơ chế đồng bộ rõ ràng, luôn đặt timeout và đảm bảo mọi transaction được đóng trong `finally`/`try-with-resources`. Không kiểm tra kiểu «chạy 100 thread rồi đoán ai đi trước»; đó là bài thử tải, không phải test ngữ nghĩa xác định.

## 8. Lost update: hai request đọc cũ, ghi đè kết quả của nhau

### 8.1. Cập nhật từ giá trị đã đọc trước

Giả sử hai transaction cùng muốn tăng `A.balance` từ 100 lên 101. Mỗi transaction đọc `100`, tự tính `old + 1` trong Java, rồi ghi giá trị đã tính:

```cypher
MATCH (a:TxAccount {id: $id})
RETURN a.balance AS oldValue;
```

Sau đó:

```cypher
MATCH (a:TxAccount {id: $id})
SET a.balance = $computedNewValue;
```

Nếu cả hai đã đọc `100` rồi cùng gửi `computedNewValue = 101`, kết quả cuối cùng là **101**, dù hai request cùng yêu cầu tăng. Khóa tại lúc ghi chỉ khiến hai phép ghi diễn ra lần lượt; nó **không thể tự sửa** giá trị `101` đã được ứng dụng tính từ dữ liệu cũ.

### 8.2. Test tạo đúng lịch «cả hai đã đọc trước khi viết»

```java
@Test
void staleClientSideComputationCanLoseAnUpdate()
        throws Exception {
    CountDownLatch bothRead = new CountDownLatch(2);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    Callable<Long> update = () -> {
        try (Session session = newSession();
             var tx = session.beginTransaction()) {
            long old = tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                RETURN a.balance AS balance
                """).single().get("balance").asLong();

            bothRead.countDown();
            if (!bothRead.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Both readers did not reach the barrier");
            }

            // Truyền kết quả tính bên ngoài, không phụ thuộc trực tiếp
            // vào property ở vế phải của SET.
            tx.run("""
                MATCH (a:TxAccount {id: 'A'})
                SET a.balance = $newValue
                """, Map.of("newValue", old + 1))
                .consume();
            tx.commit();
            return old;
        }
    };

    try {
        Future<Long> first = pool.submit(update);
        Future<Long> second = pool.submit(update);
        assertEquals(100L, first.get(15, TimeUnit.SECONDS).longValue());
        assertEquals(100L, second.get(15, TimeUnit.SECONDS).longValue());
    } finally {
        pool.shutdownNow();
    }

    // Cả hai cùng tính 100+1: một lần tăng đã bị mất.
    assertEquals(101L, balance("A"));
}
```

Barrier bảo đảm **cả hai giao dịch đã đọc** giá trị cũ trước khi một giao dịch bắt đầu phần ghi. Với môi trường có lock contention bất thường hoặc timeout, test vẫn có thể thất bại vì điều kiện hạ tầng; cần xem log trước khi kết luận thay đổi hành vi cách ly. Không dùng testcase này làm thuật toán tăng counter trong production.

## 9. Phép tăng phụ thuộc trực tiếp vào property

Neo4j tài liệu hóa việc Cypher có thể tự lấy **khóa ghi trước khi đọc** khi cập nhật property có **phụ thuộc trực tiếp**:

```cypher
MATCH (a:TxAccount {id: 'A'})
SET a.balance = a.balance + 1;
```

Nhờ quan hệ phụ thuộc đó, hai thao tác tăng cùng node được đồng bộ phù hợp để không đánh mất một lần tăng theo kiểu vừa mô tả.

### Test hai Session cùng tăng

```java
@Test
void directPropertyIncrementPreservesBothUpdates()
        throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CountDownLatch start = new CountDownLatch(1);

    Callable<Void> increment = () -> {
        if (!start.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Start was not released");
        }
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (a:TxAccount {id: 'A'})
                    SET a.balance = a.balance + 1
                    """).consume();
                return null;
            });
        }
        return null;
    };

    try {
        Future<Void> first = pool.submit(increment);
        Future<Void> second = pool.submit(increment);
        start.countDown();
        first.get(15, TimeUnit.SECONDS);
        second.get(15, TimeUnit.SECONDS);
    } finally {
        pool.shutdownNow();
    }

    assertEquals(102L, balance("A"));
}
```

Kết quả `102` xác nhận **hai yêu cầu tăng một property** đều được phản ánh trong trường hợp thử. Nó **không chứng minh** mọi bất biến trải qua nhiều node có tính serializable. Nếu cập nhật phụ thuộc vào số liệu đọc trước, hoặc trên nhiều node không khóa cùng tài nguyên, phải thiết kế đồng bộ riêng.

### 9.1. Thận trọng với `WITH`

Truy vấn sau tách việc đọc khỏi phép cập nhật:

```cypher
MATCH (a:TxAccount {id: 'A'})
WITH a, a.balance AS oldBalance
SET a.balance = oldBalance + 1;
```

Không nên mặc định câu trên có cùng bảo đảm tránh lost update như `SET a.balance = a.balance + 1`. Khi có thao tác đọc–tính toán phức tạp, cần nghiên cứu cơ chế khóa chủ động theo phiên bản, hoặc dùng optimistic locking/version check và kiểm thử đồng thời.

## 10. Unique constraint: hai transaction tranh cùng business key

### 10.1. Lịch cạnh tranh

Hai client đồng thời cố tạo:

```cypher
CREATE (:TxRequest {requestId: 'req-01', amount: 50});
```

Nếu `TxRequest.requestId` có unique constraint đang hoạt động, **không thể cùng commit thành công hai node có cùng khóa**. Thường một transaction thành công và transaction còn lại nhận lỗi constraint (hoặc chờ/nhận lỗi phù hợp với lịch thực thi).

Đừng khẳng định trước «thread 1 luôn thắng»; lịch chạy do hệ điều hành, driver, lock và DBMS quyết định.

### 10.2. `MERGE` + constraint cho idempotency

```cypher
MERGE (r:TxRequest {requestId: $requestId})
ON CREATE SET
    r.amount = $amount,
    r.state = 'NEW'
RETURN r.requestId AS requestId,
       r.amount AS storedAmount;
```

Cùng `requestId` lặp lại sẽ tìm lại bản ghi đã tồn tại, thay vì luôn tạo mới. Tuy nhiên, nếu một request dùng cùng ID nhưng `amount` khác, câu trên giữ giá trị cũ; **ứng dụng phải kiểm tra trùng ID khác payload** và trả conflict, không coi đó là thành công nghiệp vụ.

### 10.3. Test idempotency dễ lặp

```java
@Test
void repeatedRequestIdDoesNotCreateDuplicateNode() {
    for (int i = 0; i < 2; i++) {
        try (Session session = newSession()) {
            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (r:TxRequest {requestId: $requestId})
                    ON CREATE SET r.amount = $amount, r.state = 'NEW'
                    """, Map.of(
                        "requestId", "req-01",
                        "amount", 50
                    )).consume();
                return null;
            });
        }
    }

    try (Session session = newSession()) {
        long count = session.executeRead(tx ->
            tx.run("""
                MATCH (r:TxRequest {requestId: 'req-01'})
                RETURN count(r) AS count
                """).single().get("count").asLong());
        assertEquals(1L, count);
    }
}
```

Test này kiểm tra **lặp tuần tự**. Để kiểm thử concurrent insert, mở hai Session và phát cùng khóa sau một barrier, sau đó khẳng định **không có hai node được commit**; xử lý tình huống một request thất bại do constraint, chứ không nhất thiết đòi cả hai callback thành công.

## 11. Deadlock: thử nghiệm xung đột thứ tự khóa

Deadlock xảy ra khi các transaction tạo thành vòng chờ:

```text
Transaction A                         Transaction B
SET account A (giữ khóa A)           SET account B (giữ khóa B)
          |                                     |
          +---- chờ khóa B        chờ khóa A ----+
```

Một lịch tạo deadlock trong môi trường test:

1. Transaction A bắt đầu và cập nhật node `A`, đảm bảo kết quả query đã được tiêu thụ.
2. Transaction B bắt đầu và cập nhật node `B`.
3. Dùng barrier xác nhận **mỗi bên đang giữ khóa ghi riêng**.
4. Cho A tiếp tục cập nhật `B` và B tiếp tục cập nhật `A`.
5. Neo4j có thể phát hiện vòng chờ và hủy một giao dịch để giải quyết deadlock.

Trong Java Driver hiện đại, có thể gặp lỗi có mã `Neo.TransientError.Transaction.DeadlockDetected`; các thế hệ Neo4j mới còn cung cấp **GQLSTATUS** và thông tin chẩn đoán tương ứng. **Không assert nguyên văn một message lỗi** vì nó có thể khác giữa phiên bản.

Các điều cần assert:

- Không có thay đổi **chưa commit** của transaction bị hủy còn lại trong database.
- Transaction có thể được retry an toàn theo chính sách được phép.
- Không có thread treo vô hạn; mọi `Future.get`/barrier có timeout.
- Kết quả cuối không vi phạm invariant/constraint, bất kể giao dịch nào thắng.

**Chú ý:** Deadlock test thường nhạy với thời gian, runtime và cơ chế khóa. Nên cô lập nó trong nhóm integration/failure tests, cố định phiên bản, ghi log chẩn đoán và không dùng `sleep(100)` để «chắc chắn» một thread tới trước. Nếu dùng managed transaction, driver có thể retry và che mất lỗi deadlock ban đầu; để đo chính xác lỗi, hãy dùng **explicit transaction** hoặc logging số lần callback được chạy.

## 12. Retry: chính xác cần kiểm tra những gì?

### 12.1. Managed và explicit transaction khác nhau

| Hình thức | Java Driver API phổ biến | Quy tắc thử lại |
| --- | --- | --- |
| Managed read | `session.executeRead(callback)` | Driver có thể tự retry callback khi lỗi đủ điều kiện |
| Managed write | `session.executeWrite(callback)` | Driver có thể tự retry toàn bộ callback |
| Explicit | `session.beginTransaction()`, `commit()`/`rollback()` | Ứng dụng tự xử lý retry nếu cần |
| Auto-commit query | `session.run(...)` | Không giả định có chính sách retry như managed transaction |

Driver chỉ retry **các lỗi được phân loại đủ điều kiện**, trong phạm vi cấu hình `maxTransactionRetryTime` và hành vi API thực tế. Vi phạm unique constraint, lỗi cú pháp Cypher, sai input hoặc không có quyền **không nên** được xem là transient chỉ để thử lại nhiều lần.

### 12.2. Callback có thể chạy nhiều lần

```java
try (Session session = newSession()) {
    session.executeWrite(tx -> {
        tx.run("""
            MATCH (a:TxAccount {id: 'A'})
            SET a.balance = a.balance + 1
            """).consume();
        return null;
    });
}
```

Với lỗi phù hợp, driver có thể bỏ một lần chạy transaction và thực thi lại callback trong một transaction mới. **Các thay đổi của lần chạy bị rollback không được tích lũy vào kết quả commit**, nhưng side effect **nằm ngoài Neo4j** không được driver rollback:

```java
// Không an toàn:
session.executeWrite(tx -> {
    // paymentGateway.charge(...); // có thể bị gọi nhiều lần!
    tx.run("CREATE (:TxEvent {kind: 'CHARGED'})").consume();
    return null;
});
```

Điều kiện cần cho retry an toàn:

- Callback không tạo side effect ngoài DB, hoặc mọi side effect đã có cơ chế **idempotency** riêng.
- Giao dịch kiểm tra/increment/ghi theo khóa nghiệp vụ được thiết kế an toàn dưới concurrent writes.
- Không tái sử dụng `Session` hoặc `Transaction` giữa các thread.
- Không retry vô hạn khi lỗi có tính xác định (syntax/constraint/data validation).
- Có timeout/budget cho cả request, transaction và retry; theo dõi tỉ lệ retry.

### 12.3. Kiểm thử retry theo hai lớp

**Unit test** của retry policy do ứng dụng sở hữu có thể dùng fake port phát lỗi tạm thời theo một kịch bản xác định rồi thành công; assert số lần gọi, backoff, dừng đúng ngân sách. Unit test không chứng minh Java Driver thực sự retry một lỗi Bolt cụ thể.

**Integration test** dùng Neo4j thật và lỗi transient có kiểm soát (ví dụ deadlock có barrier, hoặc cơ chế fault injection có sẵn trong hạ tầng thử nghiệm). Assert:

1. Không còn thay đổi của lần chạy bị rollback.
2. Kết quả cuối sau retry đúng số liệu nghiệp vụ.
3. Callback có thể chạy lại nên không tạo side effect ngoài DB nhiều lần.
4. Khi quá ngân sách retry, lỗi được truyền lên và tài nguyên đóng đúng cách.

**Không giả lập transient bằng cách tự ném bất kỳ `RuntimeException` nào** rồi kỳ vọng Driver sẽ retry: không phải mọi exception đều được xem là retryable. Nếu muốn kiểm tra quyết định retry của driver, cần đọc hợp đồng exception của đúng phiên bản.

### 12.4. Lỗi ở thời điểm commit có thể gây không chắc chắn

Nếu client mất kết nối **ngay quanh lúc commit**, client có thể không biết server đã commit hay chưa. Chỉ vì callback báo lỗi không đủ để kết luận dữ liệu chưa tồn tại.

Đây là lý do phải dùng **idempotency key** cho các lệnh tạo thực thể/cạnh quan trọng. Ví dụ hệ thống tạo đơn với `requestId` ổn định:

```cypher
MERGE (r:TxRequest {requestId: $requestId})
ON CREATE SET r.amount = $amount, r.state = 'NEW'
RETURN r.requestId, r.amount, r.state;
```

Khi retry cùng business request, đọc lại bằng `requestId`, xác nhận payload cũ có khớp không rồi mới trả thành công. Không dùng một `CREATE` mới với ID ngẫu nhiên ở mỗi lần retry.

## 13. Optimistic locking, version và bất biến nhiều node

### 13.1. So sánh version để phát hiện stale write

Một chiến lược là đọc `balance` cùng `version`, tính toán nghiệp vụ, rồi cập nhật chỉ khi version vẫn bằng giá trị đã đọc:

```cypher
MATCH (a:TxAccount {id: $id})
WHERE a.version = $expectedVersion
SET a.balance = $newBalance,
    a.version = a.version + 1
RETURN a.id AS id, a.version AS version;
```

Ứng dụng kiểm tra **số dòng trả về**:

- Một dòng: thao tác đã khớp version và được thực hiện trong transaction.
- Không có dòng: node không tồn tại **hoặc** version không khớp; cần phân biệt nếu nghiệp vụ yêu cầu.

**Cảnh báo về concurrency:** Việc có `WHERE a.version = ...` không tự biến mọi mô hình đọc–ghi thành thao tác *compare-and-swap* an toàn dưới mọi lịch thực thi. Cần chứng minh cơ chế khóa/tranh chấp của câu query trên **bản Neo4j đang dùng**, hoặc lấy khóa ghi thích hợp **trước khi đọc/kiểm tra version**, và chạy test đồng thời để xác nhận chỉ một writer với cùng version được nhận. Không coi ví dụ này là bằng chứng tự động của serializable isolation.

### 13.2. Invariant đa-node

Ví dụ nghiệp vụ: «một nhóm trực phải luôn có ít nhất một người đang trực». Hai transaction cùng đọc danh sách hai nhân viên, rồi mỗi bên cập nhật **một node khác nhau** thành nghỉ. Mỗi transaction có thể thấy điều kiện đúng tại lúc kiểm tra nhưng kết quả chung lại không có ai trực. Đây là dạng **write skew**.

Thử nghiệm cần:

1. Chuẩn bị đúng hai node `onDuty = true`.
2. Cho A và B cùng đọc trạng thái trước khi ai ghi.
3. Để mỗi bên ghi một node khác nhau.
4. Kiểm tra kết quả cuối có vi phạm bất biến không.
5. Thêm giao thức khóa node bảo vệ chung trong cả hai luồng ghi; chạy lại để chứng minh invariant được giữ.

Unique constraint trên một khóa đơn không thay thế khóa/giao thức quản lý điều kiện liên quan **nhiều node**.

## 14. Spring Data Neo4j: kiểm thử ranh giới `@Transactional`

Trong ứng dụng Spring, `@Transactional` thường quản lý transaction khi method được gọi thông qua **Spring proxy** và hệ thống có transaction manager thích hợp. Cần kiểm tra một use case thực tế, thay vì suy từ annotation:

```java
@Service
public class AccountService {
    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeThenReject(String id) {
        repository.setBalance(id, 1L);
        throw new IllegalStateException("Business rejection");
    }
}
```

Test integration nên gọi **bean `AccountService` lấy từ Spring container**, bắt exception rồi đọc lại bằng **một transaction mới**:

```java
assertThrows(IllegalStateException.class,
    () -> accountService.changeThenReject("A"));

assertEquals(100L, accountQueryRepository.getBalance("A"));
```

Các interface `AccountRepository`/`AccountQueryRepository` là thành phần ứng dụng phải định nghĩa. Ví dụ cho thấy ý nghĩa của test, không phải một dự án Spring đã ghép đủ bean.

Những bẫy quan trọng:

- **Self-invocation**: gọi method `@Transactional` của chính object qua `this.method()` có thể bỏ qua proxy.
- **Lỗi checked exception**: cấu hình rollback mặc định của Spring thường khác với unchecked exception; cần `rollbackFor` hoặc chính sách phù hợp.
- **Method test mang `@Transactional`**: nhiều framework test tự rollback transaction test khi kết thúc, có thể che lỗi commit của code production. Muốn **test commit thật**, để test tự điều khiển boundary rồi đọc lại từ Session/transaction khác.
- **Kết hợp Java Driver và SDN**: mở transaction Driver độc lập bên trong service đang được Spring quản lý không đảm bảo cùng transaction nếu không có cấu hình tích hợp phù hợp.
- **Mapping relationship**: test nên dùng Cypher/constraint thật để xác minh cạnh đã được ghi hoặc rollback, không chỉ so sánh object trong persistence context.

## 15. Cách viết test đồng thời ít flaky

### 15.1. Dùng barrier thay vì chờ thời gian ước đoán

| Cách tạo lịch | Độ tin cậy | Ghi chú |
| --- | --- | --- |
| `Thread.sleep(200)` rồi hy vọng thread kia đã ghi | Thấp | Phụ thuộc máy CI, scheduler và độ trễ DB |
| `CountDownLatch` xác nhận mỗi thread đã qua một bước | Tốt hơn | Có timeout và đường cleanup khi một thread lỗi |
| `CyclicBarrier` đồng bộ nhiều điểm trong lịch | Tốt nếu thiết kế kỹ | Tránh barrier bị kẹt khi một thread lỗi |
| Fault injection có kiểm soát (network/DB) | Phù hợp failure testing | Cần hạ tầng riêng và test isolation |
| Chạy nhiều lượt stress | Phát hiện lỗi xác suất | Không thay thế test có expected state rõ |

Không chỉ kiểm tra «không exception»; luôn xác minh **số node, số cạnh, property và invariant** sau khi mọi transaction đã kết thúc.

### 15.2. Timeout và cleanup

Các concurrency test nên có:

- `Future.get(timeout, TimeUnit.SECONDS)` thay vì chờ vô hạn.
- `CountDownLatch.await(timeout, unit)`.
- `try-with-resources` cho mỗi Session/Transaction.
- `ExecutorService.shutdownNow()` trong `finally` khi test lỗi.
- Neo4j test instance tách biệt để test khác không vô tình sửa node đang tranh chấp.
- Log mã lỗi và nguyên nhân, nhưng không log mật khẩu hoặc dữ liệu nhạy cảm.

Các test có thể **bất định về thứ tự thread thắng**. Assert «một request thành công và invariant vẫn đúng», thay vì assert tên thread chiến thắng, trừ khi bài toán kiểm thử chủ đích tạo thứ tự xác định.

## 16. Checklist quan sát và điều tra lỗi

Khi một test commit/rollback/retry thất bại, hãy kiểm tra theo thứ tự:

1. **Đúng database chưa?** Test có đang sử dụng `neo4j` hay database khác, chạy vào container đúng URI không?
2. **Constraint có tồn tại và ONLINE chưa?** Lệnh `CREATE CONSTRAINT` đã hoàn thành trước khi chạy race test chưa?
3. **Đúng transaction boundary chưa?** Có vô tình gọi `session.run()` auto-commit thay vì dùng transaction chung không?
4. **Sau commit mới assert chưa?** Query đọc từ Session khác sau khi writer kết thúc, không từ result trước commit?
5. **Có exception bị nuốt không?** Trong managed callback, exception có bị code bắt rồi vẫn trả thành công không?
6. **Có nhiều Session/thread riêng không?** Một Session chia sẻ giữa thread làm test không đại diện cho hai giao dịch độc lập.
7. **Lịch đồng thời có thật không?** Barrier có xác nhận hai transaction đều đọc trước bước ghi không?
8. **Lỗi thuộc nhóm nào?** Deadlock/transient, constraint violation, connect timeout, transaction timeout hay Java callback error?
9. **Retry có che lỗi không?** `executeWrite` có tự thử lại, khiến test chỉ thấy thành công cuối?
10. **Kết quả trả về có bị đếm nhầm?** `count(*)` sau `OPTIONAL MATCH` có thể khác `count(node)`; hãy đối chiếu với dữ liệu thực.
11. **Version server và driver có khớp giả định test không?** Cơ chế khóa, mã lỗi, syntax và default có thể thay đổi.
12. **Test có cô lập dữ liệu không?** Có test khác cùng reset fixture hoặc cleanup trong lúc concurrency test chạy không?

Trong môi trường phát triển, có thể dùng `SHOW TRANSACTIONS` nếu tài khoản đủ quyền để quan sát transaction đang chạy/chờ. Với truy vấn chậm, `EXPLAIN`/`PROFILE` giúp xác định cardinality, truy cập index và chi phí mở rộng relationship, nhưng kế hoạch tốt không thay thế test đồng thời.

## 17. Bài tập có lời giải gợi ý

### Bài 1 — Commit hay chỉ nhìn thấy thay đổi trong transaction?

Một test chạy `SET a.balance = 200 RETURN a.balance`, nhận `200` rồi kết luận transaction đã commit. Kết luận đó đúng không?

**Đáp án:** Không. Transaction luôn nhìn thấy thay đổi do chính nó thực hiện. Phải chờ `commit()` thành công rồi đọc lại bằng Session/transaction khác để kiểm chứng.

### Bài 2 — Giao dịch có hai thay đổi rồi thất bại

A và B lần lượt có `balance = 100` và `200`. Một transaction sửa A thành `70` và B thành `230` rồi ném exception trước commit. Giá trị nào phải được quan sát sau rollback?

**Đáp án:** A vẫn `100`, B vẫn `200`. Test cần assert **cả hai** giá trị, không chỉ một bên.

### Bài 3 — Hai callback tăng balance

Hai transaction cùng đọc `100` rồi `SET a.balance = $value` với `value = 101`. Vì sao kết quả có thể vẫn là `101`? Hãy viết lại câu Cypher phù hợp cho phép tăng trực tiếp.

**Đáp án:**

```cypher
MATCH (a:TxAccount {id: 'A'})
SET a.balance = a.balance + 1;
```

Giá trị đọc sẵn và tính bên ngoài không còn liên kết trực tiếp với property tại thời điểm ghi. Phép tăng trực tiếp cho phép Neo4j bảo vệ cập nhật theo cơ chế khóa được tài liệu hóa.

### Bài 4 — Hai request cùng ID

Hai request cùng `requestId = 'req-01'` nhưng số tiền lần lượt là `50` và `80`. Unique constraint và `MERGE` đã đủ để coi cả hai là hợp lệ chưa?

**Đáp án:** Chưa. Chúng ngăn tạo hai node có cùng ID, nhưng request thứ hai cần được xem là **xung đột payload**, không tự ghi đè hoặc bỏ qua sự khác biệt.

### Bài 5 — Kiểm thử deadlock

Vì sao test với hai thread cập nhật A/B ngược thứ tự và `Thread.sleep(100)` có thể lúc pass lúc fail?

**Đáp án:** Thời gian thread, network và Neo4j không được đảm bảo bằng một khoảng ngủ cố định. Cần barrier để biết mỗi transaction đã lấy khóa đầu tiên trước khi cùng cố lấy khóa thứ hai; đặt timeout và cleanup rõ ràng.

### Bài 6 — Retry callback có gửi email

`executeWrite` tạo node thành công, gọi API gửi email, rồi server/driver báo lỗi tạm thời. Driver retry callback. Có nguy cơ gì?

**Đáp án:** Email có thể bị gửi nhiều lần dù lần transaction lỗi được rollback. Cần chuyển side effect ra ngoài callback, hoặc dùng outbox/idempotency có ràng buộc nghiệp vụ.

### Bài 7 — Spring test tự rollback

Một `@SpringBootTest` có `@Transactional` trên method test. Test gọi service tạo node, query thấy node, rồi test framework rollback toàn bộ. Test đã chứng minh use case commit thật chưa?

**Đáp án:** Chưa. Test chỉ chứng minh trong transaction test có thấy node. Cần một integration test chủ động commit rồi đọc từ transaction mới, hoặc tổ chức test transaction theo công cụ kiểm thử Spring phù hợp.

### Bài 8 — Thiết kế test matrix cho relationship

Ứng dụng có `(:User)-[:MEMBER_OF]->(:Team)`. Hãy thiết kế ba test cho thao tác thêm thành viên có tính idempotent và atomic.

**Gợi ý:** (1) Commit tạo đúng một relationship và đọc lại từ Session khác; (2) ném exception sau khi tạo relationship khiến nó bị rollback; (3) hai writer cùng khóa nghiệp vụ không thể commit hai relationship tương đương khi có constraint/chiến lược chống trùng thích hợp. Cần kiểm tra cả **node đầu mút**, hướng cạnh và property khóa quan hệ.

## 18. Tổng kết

Kiểm thử giao dịch Neo4j không dừng ở việc query trả đúng record. **Commit** phải được xác nhận từ một transaction khác; **rollback** phải làm biến mất **mọi thay đổi chưa commit của transaction thất bại**; **concurrent writes** phải được kiểm tra bằng lịch thực thi có điều khiển và constraint thực tế.

Đặc biệt, **read committed không đồng nghĩa serializable**. Phép tính từ giá trị đã đọc có thể gây *lost update*, trong khi `SET n.value = n.value + 1` có cơ chế khóa đặc thù. **Managed transaction** của Java Driver có thể retry callback, nên logic ghi cần an toàn khi thực thi lại; idempotency key cần thiết khi trạng thái commit trở nên không chắc chắn. Với Spring Data Neo4j, phải kiểm chứng transaction boundary, proxy và rollback thật bằng integration test, không chỉ bằng annotation.

Một bộ kiểm thử đáng tin cậy kết hợp **JUnit + Neo4j Testcontainers**, dữ liệu fixture tách biệt, barrier có timeout, đọc lại sau commit/rollback, kiểm tra invariant và theo dõi lỗi theo phiên bản. Đây là nền tảng để ứng dụng Java sử dụng Neo4j an toàn trước tải đồng thời và các sự cố thực tế.

### Tài liệu tham khảo

- [Neo4j Java Driver Manual – Transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Query advanced topics](https://neo4j.com/docs/java-manual/current/query-advanced/)
- [Neo4j Operations Manual – Concurrent data access](https://neo4j.com/docs/operations-manual/current/database-internals/concurrent-data-access/)
- [Neo4j Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)
- [Testcontainers – Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
