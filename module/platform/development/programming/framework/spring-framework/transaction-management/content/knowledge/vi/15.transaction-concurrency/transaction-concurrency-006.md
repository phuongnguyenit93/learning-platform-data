# Deadlock và thứ tự truy cập tài nguyên nhất quán trong Spring transaction management

## 1. Bài toán: vì sao hai transaction đều hợp lệ mà vẫn chờ nhau mãi?

Trong ứng dụng Spring, mỗi lời gọi **@Transactional** có thể được cấu hình đúng, từng câu SQL cũng hợp lệ, nhưng hai transaction chạy đồng thời lại **giữ những lock mà transaction kia đang cần**. Nếu các phụ thuộc chờ nhau tạo thành **một vòng khép kín**, đó là **deadlock**.

Ví dụ hai yêu cầu cùng cập nhật hai tài khoản A và B:

- T1 khóa A, rồi muốn khóa B.
- T2 khóa B, rồi muốn khóa A.
- T1 chờ T2 nhả B; T2 chờ T1 nhả A.
- Không transaction nào có thể tự tiến lên để nhả lock.

Một DBMS như PostgreSQL có deadlock detector. Nó sẽ chọn một transaction làm **victim**, hủy transaction đó và trả lỗi. Transaction còn lại có thể tiếp tục, nhưng nghiệp vụ của victim **không tự động được làm lại**. Ứng dụng phải quyết định có retry không và nếu retry thì phải tạo transaction mới.

**Phòng ngừa quan trọng nhất:** khi nhiều transaction cần truy cập cùng một nhóm tài nguyên, hãy yêu cầu **mọi đường thực thi cùng lấy lock theo một thứ tự tổng quát nhất quán**. Chẳng hạn luôn xử lý tài khoản có id nhỏ trước, id lớn sau, không phụ thuộc chiều chuyển tiền.

Bài này nằm trong nhóm **Khóa và đồng thời** của Spring Framework transaction management. Trọng tâm là cách nhận diện deadlock, thiết kế lock ordering thực tế, làm việc với Spring TransactionManager, đọc lỗi PostgreSQL, retry an toàn và kiểm chứng bằng hai transaction đồng thời.

### Mục tiêu

Sau bài, bạn có thể:

1. Dựng **wait-for graph** và phân biệt deadlock với lock wait/timeout thông thường.
2. Giải thích deadlock do row locks, table locks, lock upgrades, SQL/foreign keys/ORM flush.
3. Thiết kế một **canonical lock order** theo entity type, database key và lock mode.
4. Áp dụng **SELECT ... FOR UPDATE** và UPDATE theo thứ tự ổn định trong một @Transactional service.
5. Đọc đúng PostgreSQL **SQLSTATE 40P01** và phân biệt 40001, 55P03, 57014.
6. Retry **toàn bộ transaction** bên ngoài transaction boundary với giới hạn/backoff, không nhân đôi side effects.
7. Chạy ví dụ Java 17+ Spring JDBC với PostgreSQL: một lịch thực thi tạo deadlock và một lịch thực thi cùng thứ tự tránh vòng chờ.
8. Kiểm thử và giám sát deadlock mà không phải dựa vào Thread.sleep() hoặc chỉ xem log ứng dụng.

## 2. Deadlock là gì? Phân biệt với chờ khóa thông thường

Trong relational database, UPDATE hoặc SELECT ... FOR UPDATE thường lấy lock theo chế độ tương ứng để bảo vệ các row khỏi những thay đổi mâu thuẫn. Lock là cần thiết để giữ tính đúng đắn khi đồng thời; vấn đề không phải “có lock” mà là **cách nhiều transaction lấy và chờ lock**.

Một tình huống **chờ hợp lệ**:

~~~text
T1: lock A ----------- UPDATE A -------- COMMIT (nhả lock A)
T2:       xin lock A ---- WAIT ---------- có lock A --- COMMIT

T2 chờ T1, nhưng T1 không chờ T2 -> không có deadlock.
~~~

Một tình huống **deadlock**:

~~~text
T1: lock A ------------------- xin lock B -- WAIT(T2)
T2:      lock B -------------- xin lock A -- WAIT(T1)

T1 giữ A và chờ B; T2 giữ B và chờ A.
T1 chỉ tiến khi T2 kết thúc; T2 chỉ tiến khi T1 kết thúc.
=> Vòng chờ không có đường thoát nếu không can thiệp.
~~~

**Wait-for graph (đồ thị chờ):**

~~~mermaid
flowchart LR
    T1["Transaction T1: giữ A, cần B"]
    T2["Transaction T2: giữ B, cần A"]
    T1 -->|"chờ lock B do T2 giữ"| T2
    T2 -->|"chờ lock A do T1 giữ"| T1
~~~

Đây là một **chu trình**. Nếu có ba transaction, deadlock có thể là T1 chờ T2, T2 chờ T3, T3 chờ T1; không cần chỉ có hai bên. Trong hệ thống có lock modes và queue phức tạp, wait-for graph có thể chứa nhiều cạnh hơn một vòng đơn giản.

### Deadlock, lock contention, timeout và starvation

| Hiện tượng | Bản chất | Hướng giải quyết |
| --- | --- | --- |
| **Lock contention** | Nhiều transaction cần cùng tài nguyên; một bên chờ bên giữ lock | Tối ưu transaction duration, index, batch, lock mode và concurrency |
| **Deadlock** | Có chu trình chờ; không ai tự tiến lên được | Consistent lock ordering; DB abort victim; retry toàn transaction khi phù hợp |
| **Lock timeout** | Một yêu cầu chờ lock quá giới hạn; có thể không có chu trình | Xác định blocker, giảm lock duration, chọn timeout và retry policy phù hợp |
| **Statement timeout** | SQL chạy lâu hơn giới hạn; có thể do lock hoặc do query chậm | Phân tích plan/lock/IO; không mặc định đó là deadlock |
| **Starvation** | Một request luôn bị trì hoãn hoặc bị chọn bất lợi nhiều lần | Fairness, backoff, giới hạn tải, queue và retry metrics |
| **Optimistic conflict** | Version check/update count cho biết dữ liệu đã đổi | Retry logic với dữ liệu mới hoặc báo conflict cho người dùng |

**Quan trọng:** chờ lock lâu **không đủ** kết luận deadlock. Bằng chứng mạnh là database trả lỗi deadlock cụ thể, hoặc wait graph có chu trình. Nếu không có vòng chờ, transaction giữ lock có thể tiến lên và cuối cùng giải phóng cho waiter.

## 3. Vì sao Spring @Transactional không tự loại bỏ deadlock?

Spring quản lý **transaction boundary**, không phải người lập lịch mọi lock ở DBMS. Với imperative JDBC/JPA:

~~~text
Caller
  |
  v
Spring AOP proxy / TransactionInterceptor
  |
  +-- PlatformTransactionManager mở hoặc tham gia transaction
  |
  +-- Service/repository gọi SQL
  |       |
  |       +-- PostgreSQL cấp lock hoặc buộc chờ
  |       +-- PostgreSQL phát hiện deadlock và abort victim
  |
  +-- exception thoát ra -> rollback theo policy
  +-- transaction cleanup, release Connection
~~~

Giả sử hai service methods đều có:

~~~java
// Snippet: method phải được gọi qua Spring-managed proxy.
@Transactional
public void transfer(long fromId, long toId, long amount) {
    debit(fromId, amount);
    credit(toId, amount);
}
~~~

Nếu request **A -> B** gọi debit(A) rồi credit(B), còn request **B -> A** gọi debit(B) rồi credit(A), thứ tự **lấy lock thực tế** có thể đảo ngược. Một outer @Transactional đúng chỉ giữ mỗi transaction atomic; nó **không ép hai transactions cùng chọn A trước B**.

Transaction manager JDBC giúp rollback khi SQLException thích hợp thoát qua interceptor (Spring DataAccessException là RuntimeException), nhưng nó không thể “cam kết không deadlock”. **Một transaction bị PostgreSQL abort vì deadlock phải được kết thúc và làm lại trong transaction mới** nếu nghiệp vụ cho phép.

### Lock có thể được lấy ngầm

Không cần SQL LOCK TABLE mới có deadlock. Các thao tác sau có thể lấy lock:

- UPDATE/DELETE trực tiếp trên row.
- SELECT ... FOR UPDATE / FOR NO KEY UPDATE / FOR SHARE theo mode.
- INSERT/UPDATE có unique constraint hoặc foreign key.
- Trigger, cascade delete/update, kiểm tra referential integrity.
- DDL cần table-level locks; batch maintenance hoặc migration.
- JPA/Hibernate flush, JDBC batch và thay đổi index.

Vì vậy, kế hoạch lock order phải nhìn vào **tài nguyên database mà câu SQL thật sự đụng tới**, không chỉ vị trí các lệnh Java trong source code.

## 4. Deadlock hai tài khoản: thứ tự không nhất quán

Giả sử bảng account có hai row id=1, id=2, mỗi row amount=0. Hai requests muốn cập nhật cả hai row. Nếu mỗi transaction lấy lock theo thứ tự khác nhau:

~~~text
Thời điểm     T1 (id 1 rồi id 2)                T2 (id 2 rồi id 1)
-----------------------------------------------------------------------
t1            BEGIN
t2                                               BEGIN
t3            UPDATE account WHERE id=1          (T1 khóa row 1)
t4                                               UPDATE account WHERE id=2
                                                 (T2 khóa row 2)
t5            UPDATE account WHERE id=2          (T1 chờ row 2)
t6                                               UPDATE account WHERE id=1
                                                 (T2 chờ row 1)
t7            PostgreSQL phát hiện chu trình
t8            Một transaction bị abort với 40P01
t9            Transaction còn lại có thể chạy xong và COMMIT
~~~

Kết quả sau lỗi phụ thuộc vào transaction nào bị chọn làm victim và business operation của từng bên. Không được thiết kế dựa trên giả định **“T2 luôn là victim vì đến sau”**; PostgreSQL có quyền chọn bên nào để phá chu trình.

### Ví dụ SQL minh họa với hai phiên psql

**Session 1:**

~~~sql
BEGIN;
UPDATE account SET amount = amount + 1 WHERE id = 1;
-- Dừng tại đây để session 2 khóa id=2.
UPDATE account SET amount = amount + 1 WHERE id = 2;
COMMIT;
~~~

**Session 2:**

~~~sql
BEGIN;
UPDATE account SET amount = amount + 1 WHERE id = 2;
-- Dừng tại đây để session 1 khóa id=1.
UPDATE account SET amount = amount + 1 WHERE id = 1;
COMMIT;
~~~

Các câu “dừng tại đây” là hướng dẫn thao tác thủ công, không phải lệnh SQL. Nếu chạy hai script tuần tự từ đầu đến cuối thì thường **không có deadlock**. Phải interleave ở đúng vị trí sau hai UPDATE đầu. Với PostgreSQL, khi một transaction nhận lỗi 40P01, transaction đó đã ở trạng thái aborted; không tiếp tục COMMIT như thể mọi thứ thành công.

## 5. Thứ tự truy cập nhất quán phá vòng chờ như thế nào?

Chọn một **thứ tự toàn phần** (total order) cho các tài nguyên mà transaction phải khóa. Với hai tài khoản:

~~~text
Quy tắc: luôn lấy lock tài khoản có ID nhỏ trước, ID lớn sau.

T1 muốn xử lý A=1 và B=2:
  lock row 1 -> lock row 2 -> thay đổi -> commit

T2 muốn xử lý B=2 và A=1:
  lock row 1 -> lock row 2 -> thay đổi -> commit

Nếu T1 đang giữ row 1, T2 chờ row 1.
T1 không cần xin một lock do T2 đã giữ trước đó.
=> Không tạo vòng chờ giữa hai row theo protocol này.
~~~

Quan trọng: **thứ tự khóa không phụ thuộc vai trò nghiệp vụ** như “source account”, “destination account”, “debit” hay “credit”. Nó phụ thuộc một khóa ổn định như **account_id**. Sau khi có đủ lock, code mới áp dụng chuyển tiền theo chiều nghiệp vụ đúng.

Nếu mọi transaction chỉ lấy lock theo thứ tự tăng dần của cùng một khóa tổng quát, vòng chờ do chính tập lock đó thường bị loại trừ: giả sử có vòng chờ thì mỗi transaction phải chờ một lock lớn hơn lock đã giữ, còn vòng khép kín lại yêu cầu đi về lock nhỏ hơn, mâu thuẫn với thứ tự. Đây là lý do chọn một **thứ tự chung cho tất cả đường ghi** rất hiệu quả.

### Canonical order áp dụng cho nhiều loại tài nguyên

Khi code truy cập nhiều bảng/entity, một quy ước có thể là:

1. Chọn thứ tự lớp tài nguyên: ví dụ tenant_guard trước account, account trước ledger_entry.
2. Trong cùng loại, chọn khóa định danh ổn định: tenantId, accountId, orderId...
3. Sắp xếp trước khi lấy lock; dùng cùng comparator ở mọi service/worker.
4. Khi cần lock mode mạnh hơn về sau, cân nhắc lấy **mode cần thiết từ đầu** để tránh conversion/upgrade deadlocks.
5. Duy trì cùng thứ tự trong bulk operations, background jobs, scheduler, admin tools và migration.
6. Kiểm tra khóa gián tiếp do index, foreign key, triggers, cascades hoặc ORM flush.

**Không đồng nghĩa** chỉ cần sort một list trong Java là tuyệt đối không deadlock. SQL optimizer có thể thay đổi thứ tự truy cập thực tế trong bulk SQL, ORM có thể flush theo thứ tự khác, triggers/foreign keys có thể phát sinh locks ngoài list. Quy ước phải dựa trên **thứ tự lock thực tế**, được kiểm chứng bằng integration tests và SQL/DB logs.

### Lock nhiều row bằng cách có thể kiểm soát

Trong PostgreSQL, nếu có chính xác hai id cần khóa, cách rõ ràng cho bài học là **hai câu SELECT FOR UPDATE tuần tự**, theo id đã sort:

~~~sql
BEGIN;

SELECT id FROM account WHERE id = 1 FOR UPDATE;
SELECT id FROM account WHERE id = 2 FOR UPDATE;

-- Cả hai row đã bị khóa theo thứ tự ổn định.
-- Áp dụng debit/credit trong cùng transaction.

COMMIT;
~~~

Đối với hai request xử lý (2,1), vẫn chạy SELECT id=1 trước id=2. Dòng SELECT FOR UPDATE giữ row lock đến khi transaction kết thúc (trừ trường hợp cụ thể của savepoint rollback). Nếu một id không tồn tại, SELECT không trả row để khóa; code phải xử lý **missing resource** chứ không tự xem như đã có guard lock.

Một câu **SELECT ... WHERE id IN (...) ORDER BY id FOR UPDATE** đôi khi được dùng để khóa tập row. Với các quy trình đòi thứ tự tuyệt đối, đừng suy đoán mọi plan/batching/ORM đều cấp khóa đúng theo thứ tự của list; kiểm tra DBMS và SQL plan. Khóa tuần tự từng row theo khóa canonical là cách dễ kiểm chứng trong ví dụ ít row.

## 6. Phân biệt lock order với thứ tự cập nhật nghiệp vụ

Giả sử chuyển tiền từ account 20 sang account 10:

- **Lock order:** 10 trước, 20 sau.
- **Business logic:** trừ tiền từ 20, cộng tiền vào 10.
- **Physical row writes:** có thể thực thi sau khi đã lấy đủ locks.

Không được dùng “id nhỏ luôn debit” — đó là **sai nghiệp vụ**. Sort chỉ để **đồng bộ tài nguyên**, còn debit/credit dựa vào fromId/toId. Ví dụ Spring JDBC:

~~~java
// Snippet trong service @Transactional đã đi qua Spring proxy.
long first = Math.min(fromId, toId);
long second = Math.max(fromId, toId);

jdbc.queryForObject(
        "SELECT id FROM account WHERE id = ? FOR UPDATE",
        Long.class, first);
jdbc.queryForObject(
        "SELECT id FROM account WHERE id = ? FOR UPDATE",
        Long.class, second);

// Sau khi giữ đủ lock, thao tác theo hướng chuyển tiền thật.
int debited = jdbc.update(
        "UPDATE account SET balance = balance - ? " +
        "WHERE id = ? AND balance >= ?",
        amount, fromId, amount);
int credited = jdbc.update(
        "UPDATE account SET balance = balance + ? WHERE id = ?",
        amount, toId);
if (debited != 1 || credited != 1) {
    throw new IllegalStateException("Invalid transfer");
}
~~~

Đoạn trên **chưa phải một file Java độc lập**, cần imports, JdbcTemplate, fromId/toId/amount và transaction configuration. Trong ứng dụng thật phải xử lý fromId==toId, số tiền không hợp lệ, row không tồn tại, overflow, constraints và idempotency request.

Với Spring JDBC, JdbcTemplate sẽ sử dụng transaction-bound Connection nếu cùng DataSource và TransactionManager; **đừng mở connection riêng** trong repository để thực thi UPDATE sau khi service đã khóa row. Nếu SQL đi qua kết nối khác, hai câu SELECT FOR UPDATE không còn bảo vệ được thao tác đó như mong muốn.

## 7. Demo Java 17+ với Spring JDBC/PostgreSQL: tự tạo deadlock rồi tránh nó

Ví dụ dùng **PostgreSQL 16**, **Spring Framework 6.2.12** và **PostgreSQL JDBC driver 42.7.4**. Chúng ta tạo **hai physical transactions chạy đồng thời** bằng Spring **TransactionTemplate** (PlatformTransactionManager), đồng bộ bằng **CyclicBarrier**. Bài học không dùng Thread.sleep() để hy vọng race tự xuất hiện.

Hai vòng thử:

- **Vòng 1 — opposite order:** T1 UPDATE id=1 rồi id=2; T2 UPDATE id=2 rồi id=1. Barrier bảo đảm hai worker đã khóa row đầu tiên trước khi tranh row thứ hai → tạo vòng chờ. PostgreSQL hủy một transaction bằng 40P01; transaction còn lại commit cả hai UPDATE.
- **Vòng 2 — consistent order:** cả hai worker UPDATE id=1 rồi id=2; barrier nằm **trước khi lấy lock đầu**, không chặn giữa hai lần lock. Một worker có thể chờ row 1 của worker kia, nhưng không có vòng chờ do hai row này. Cả hai transaction hoàn tất lần lượt.

Mỗi lần UPDATE tăng amount lên 1. Bắt đầu row1=row2=0; kết quả dự kiến ở vòng 1 là 1/1 do chỉ một transaction commit, ở vòng 2 là 2/2 do cả hai commit.

### 7.1. Dựng PostgreSQL local cho thí nghiệm

Máy cần Java 17+, Maven và Docker. Lệnh sau dùng dữ liệu/credential **chỉ dành cho bài học local**:

~~~bash
docker run -d --rm --name spring-deadlock-pg \
  -e POSTGRES_USER=demo \
  -e POSTGRES_PASSWORD=demo \
  -e POSTGRES_DB=demo \
  -p 127.0.0.1:55432:5432 \
  postgres:16
~~~

Kiểm tra readiness:

~~~bash
docker exec spring-deadlock-pg pg_isready -U demo -d demo
~~~

Tiếp tục khi PostgreSQL báo **accepting connections**. Không dùng mật khẩu ví dụ cho database thật; nếu port đã bận, đổi cả cổng Docker và JDBC URL ở phần sau. Trên PowerShell Windows, dùng một lệnh docker run trên một dòng hoặc cú pháp nối dòng riêng của PowerShell thay vì dấu gạch chéo ngược Bash.

### 7.2. Cấu trúc project

~~~text
spring-deadlock-demo/
├── pom.xml
└── src/main/java/demo/SpringDeadlockDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-deadlock-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.4</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.SpringDeadlockDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Các version được cố định để demo có môi trường rõ ràng, không có nghĩa là bản mới nhất. Trong ứng dụng Spring Boot, để Spring Boot BOM quản lý các dependency tương thích với version Boot hiện hành.

### 7.3. Java main đầy đủ

**src/main/java/demo/SpringDeadlockDemo.java**:

~~~java
package demo;

import java.sql.SQLException;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringDeadlockDemo {
    private SpringDeadlockDemo() {}

    private static TransactionTemplate transaction(
            PlatformTransactionManager manager) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(20);
        return template;
    }

    private static void awaitBoth(CyclicBarrier barrier) {
        try {
            barrier.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        } catch (BrokenBarrierException | TimeoutException ex) {
            throw new IllegalStateException("Barrier timed out", ex);
        }
    }

    private static boolean hasSqlState(Throwable error, String expected) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql &&
                    expected.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    private static void increment(JdbcTemplate jdbc, int id) {
        int updated = jdbc.update(
                "UPDATE demo_account SET amount = amount + 1 WHERE id = ?",
                id);
        if (updated != 1) {
            throw new IllegalStateException("Account row missing: " + id);
        }
    }

    // Hai worker sẽ khóa hai row trái thứ tự rồi đòi row còn lại.
    private static String oppositeOrder(
            PlatformTransactionManager manager, JdbcTemplate jdbc,
            CyclicBarrier barrier, int firstId, int secondId) {
        TransactionTemplate tx = transaction(manager);
        try {
            tx.executeWithoutResult(status -> {
                increment(jdbc, firstId);
                // Cả hai đã giữ row đầu trước khi đòi row thứ hai.
                awaitBoth(barrier);
                increment(jdbc, secondId);
            });
            return "COMMIT";
        } catch (RuntimeException ex) {
            if (hasSqlState(ex, "40P01")) {
                return "40P01";
            }
            throw ex;
        }
    }

    // Hai worker luôn khóa theo thứ tự row 1 -> row 2.
    private static String consistentOrder(
            PlatformTransactionManager manager, JdbcTemplate jdbc,
            CyclicBarrier startBarrier) {
        TransactionTemplate tx = transaction(manager);
        try {
            tx.executeWithoutResult(status -> {
                // Đồng bộ trước khi lấy lock, KHÔNG giữ nhau ở giữa.
                awaitBoth(startBarrier);
                increment(jdbc, 1);
                increment(jdbc, 2);
            });
            return "COMMIT";
        } catch (RuntimeException ex) {
            if (hasSqlState(ex, "40P01")) {
                return "40P01";
            }
            throw ex;
        }
    }

    private static List<String> runBoth(
            Callable<String> left, Callable<String> right)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(left);
            Future<String> second = pool.submit(right);
            return List.of(
                    first.get(30, TimeUnit.SECONDS),
                    second.get(30, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
        }
    }

    private static long count(List<String> results, String value) {
        return results.stream().filter(value::equals).count();
    }

    private static int amount(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
                "SELECT amount FROM demo_account WHERE id = ?",
                Integer.class, id);
        if (value == null) {
            throw new IllegalStateException("Row missing: " + id);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("DROP TABLE IF EXISTS demo_account");
            jdbc.execute("CREATE TABLE demo_account (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update("INSERT INTO demo_account(id, amount) VALUES (1, 0)");
            jdbc.update("INSERT INTO demo_account(id, amount) VALUES (2, 0)");

            CyclicBarrier oppositeBarrier = new CyclicBarrier(2);
            List<String> opposite = runBoth(
                    () -> oppositeOrder(
                            manager, jdbc, oppositeBarrier, 1, 2),
                    () -> oppositeOrder(
                            manager, jdbc, oppositeBarrier, 2, 1));
            System.out.printf(
                    "opposite order: commits=%d, deadlocks=%d, " +
                    "row1=%d, row2=%d%n",
                    count(opposite, "COMMIT"), count(opposite, "40P01"),
                    amount(jdbc, 1), amount(jdbc, 2));

            // Reset được thực hiện sau khi cả hai transactions đã kết thúc.
            jdbc.update("UPDATE demo_account SET amount = 0");

            CyclicBarrier orderedStart = new CyclicBarrier(2);
            List<String> ordered = runBoth(
                    () -> consistentOrder(manager, jdbc, orderedStart),
                    () -> consistentOrder(manager, jdbc, orderedStart));
            System.out.printf(
                    "consistent order: commits=%d, deadlocks=%d, " +
                    "row1=%d, row2=%d%n",
                    count(ordered, "COMMIT"), count(ordered, "40P01"),
                    amount(jdbc, 1), amount(jdbc, 2));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.postgresql.Driver");
            ds.setUrl("jdbc:postgresql://127.0.0.1:55432/demo");
            ds.setUsername("demo");
            ds.setPassword("demo");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }
    }
}
~~~

**Tại sao không dùng @Transactional ngay trong main?** Main tự tạo hai Callable và chạy chúng trên **hai worker threads**. TransactionTemplate giúp mở một Spring-managed transaction đúng ngay trong từng worker. Trong ứng dụng thường dùng @Transactional trên **public service methods được gọi qua Spring proxy**; semantics của JdbcTransactionManager và database vẫn là cơ sở chung.

**Tại sao dùng DriverManagerDataSource?** Đây là DataSource đơn giản phù hợp demo, không có connection pool; mỗi transaction của hai worker nhận connection độc lập. Ứng dụng production nên dùng pool như HikariCP với giới hạn phù hợp và quan sát active/idle/pending connections. Không dùng DriverManagerDataSource cho hệ thống tải cao.

**Tại sao có barrier trong transaction?** Chỉ để mô phỏng deadlock có tính xác định. Ở vòng opposite order, mỗi worker đã UPDATE row khác nhau và giữ lock, rồi hai worker đồng loạt yêu cầu row còn lại. Đừng làm theo bằng cách dùng CyclicBarrier hoặc Thread.sleep bên trong production transaction: giữ DB locks chờ synchronization như vậy có thể làm nghẽn cả hệ thống.

### 7.4. Chạy và đọc output

Từ thư mục **spring-deadlock-demo**:

~~~bash
mvn -q compile exec:java
~~~

Khi PostgreSQL local sẵn sàng, không có traffic ngoài demo và deadlock detector hoạt động bình thường, **stdout dự kiến từ Java main**:

~~~text
opposite order: commits=1, deadlocks=1, row1=1, row2=1
consistent order: commits=2, deadlocks=0, row1=2, row2=2
~~~

Đọc kết quả:

- Ở **opposite order**, cả hai transaction đã cập nhật row đầu tiên nhưng chỉ **một transaction commit được cả hai UPDATE**. Transaction bị 40P01 đã rollback, nên row1=row2=1. Không quan trọng worker nào thắng.
- Ở **consistent order**, hai worker chờ nhau tại row1 theo cách bình thường, sau đó lần lượt cập nhật row2 và commit. Mỗi row được tăng hai lần nên row1=row2=2.
- Thử nghiệm không chạy retry tự động: nó cố tình để bạn thấy victim được DB abort rồi cần caller ra quyết định làm gì. Phần sau sẽ bàn chính sách retry.
- Nếu phát sinh lỗi khác như database chưa sẵn sàng, barrier timeout, pool/connection issue hoặc môi trường cấu hình timeout quá thấp, chương trình sẽ ném exception thay vì in đủ hai dòng; cần điều tra nguyên nhân thay vì xem đó là “deadlock test thành công”.

Tắt container demo:

~~~bash
docker stop spring-deadlock-pg
~~~

### 7.5. Những giới hạn của demo

Demo dùng **READ_COMMITTED** của PostgreSQL và hai row đơn giản; nó không thử mọi hình thức deadlock trong sản phẩm thực. Một schema có foreign key, trigger, index, partition hoặc JPA batching có thể có các khóa khác mà protocol “row1 trước row2” chưa bao trùm.

Một test đúng đắn cần kiểm chứng cả **giá trị DB sau kết thúc** và **lỗi có SQLSTATE 40P01**, không chỉ đếm exception bất kỳ. Dữ liệu được đọc sau khi hai Future hoàn tất, bên ngoài transaction của hai workers, nên phản ánh trạng thái đã được commit.

## 8. Cách viết @Transactional service theo thứ tự khóa chuẩn

Trong ứng dụng thật, một **application service** nên sở hữu toàn bộ business operation. Ví dụ Spring JDBC sau chuyển tiền từ fromId sang toId, khóa hai account theo ID tăng dần **bất kể chiều chuyển**:

~~~java
// Trích đoạn đầy đủ về method, nhưng cần đặt trong Spring-managed class
// có field JdbcTemplate jdbc và import các annotation.
@Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 10)
public void transfer(long fromId, long toId, long amount) {
    if (fromId == toId || fromId <= 0 || toId <= 0 || amount <= 0) {
        throw new IllegalArgumentException("Invalid transfer input");
    }

    long first = Math.min(fromId, toId);
    long second = Math.max(fromId, toId);

    // Khóa tuần tự, cùng canonical order cho mọi chuyển tiền.
    Long actual1 = jdbc.queryForObject(
            "SELECT id FROM account WHERE id = ? FOR UPDATE",
            Long.class, first);
    Long actual2 = jdbc.queryForObject(
            "SELECT id FROM account WHERE id = ? FOR UPDATE",
            Long.class, second);
    if (actual1 == null || actual2 == null) {
        throw new IllegalStateException("Account missing");
    }

    int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount);
    int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId);

    if (debited != 1 || credited != 1) {
        throw new IllegalStateException("Transfer rejected");
    }
}
~~~

**Lưu ý về JDBC queryForObject:** với mỗi SELECT FOR UPDATE theo primary key, queryForObject sẽ ném EmptyResultDataAccessException nếu không tìm thấy row (không chỉ trả null). Trong ứng dụng thật cần xử lý ngoại lệ đó theo error policy; đoạn if null là kiểm tra phòng thủ, không thay thế trường hợp missing row. Đây là **snippet**, không phải Java file độc lập hoặc câu lệnh có thể copy vào dự án khi chưa có bean/config.

Thứ tự lock **không nhất thiết giống thứ tự UPDATE nghiệp vụ**; vì row đã bị khóa theo thứ tự tăng dần, service có thể debit fromId rồi credit toId. Đừng vô tình chuyển tiền sai hướng chỉ để theo thứ tự id.

**Bảo vệ số dư** còn cần CHECK(balance>=0), idempotency key, điều kiện balance>=amount và xử lý số row ảnh hưởng. Consistent order chủ yếu giải quyết một nhóm deadlock; nó **không thay thế** isolation, constraints hoặc logic nghiệp vụ đúng.

### Cách tốt hơn cho batch nhiều tài khoản

Nếu cần khóa danh sách accountIds, chuẩn hóa rồi sort theo stable numeric ID:

~~~java
// Snippet trong transaction; accountIds là Collection<Long>.
List<Long> orderedIds = accountIds.stream()
        .distinct()
        .sorted()
        .toList();

for (Long id : orderedIds) {
    jdbc.queryForObject(
            "SELECT id FROM account WHERE id = ? FOR UPDATE",
            Long.class, id);
}

// Sau khi khóa đủ, kiểm tra dữ liệu và áp dụng business changes.
~~~

Với lượng row rất lớn, nhiều SELECT round trips gây overhead; có thể tối ưu bằng câu SQL/batch phù hợp và **kiểm chứng lock acquisition order thực tế** trên DBMS. Một câu UPDATE ... WHERE id IN (...) không tự có guarantee thứ tự khóa theo thứ tự list của Java. Không nên dựa vào iteration order của HashMap hoặc HashSet.

## 9. Vì sao chỉ “sort ID” chưa phải toàn bộ giải pháp?

### 9.1. Cùng canonical order ở mọi code path

Giả sử TransferService luôn khóa account 1 rồi 2, nhưng một batch reconciliation job lại khóa 2 rồi 1. Vẫn có thể deadlock:

~~~text
HTTP request:     lock 1 -> muốn lock 2
Nightly job:      lock 2 -> muốn lock 1
                  => vòng chờ
~~~

Một convention trong chỉ một service **không đủ**. Cần thống nhất ở tất cả paths cùng chạm vào tài nguyên: HTTP, scheduler, Kafka consumer, batch job, admin command, migration và trigger/DB procedure. Khi thay schema, cập nhật lock ordering contract và regression tests.

### 9.2. Lock mode upgrade

Hai transaction có thể cùng lấy share lock trên một tài nguyên, sau đó **cùng yêu cầu nâng lên lock mạnh hơn** để ghi. Nếu mỗi transaction chặn yêu cầu upgrade của bên kia, có thể hình thành deadlock dù danh sách row giống nhau.

Nguyên tắc: nếu đã biết cần ghi, cân nhắc **lấy lock mode phù hợp ngay từ đầu**, chẳng hạn PostgreSQL SELECT FOR UPDATE thay vì SELECT FOR SHARE rồi chuyển sang UPDATE. Việc chọn mode mạnh hơn phải cân bằng throughput và requirements; không khóa mọi bảng một cách quá rộng chỉ vì sợ deadlock.

### 9.3. Foreign keys, indexes, constraints và triggers

Một INSERT vào child table có foreign key có thể cần kiểm tra/khóa row parent; một update unique key có thể chờ transaction khác; trigger có thể UPDATE thêm bảng. Vì vậy một service đọc code theo thứ tự Account -> Ledger nhưng DB còn ngầm đụng Inventory -> Customer thì thứ tự logic chưa mô tả hết locks.

Khi deadlock vẫn xuất hiện dù code “đã sort”, điều tra:
- SQL statements thật sự được gửi và bind parameters.
- Foreign keys và các cascades.
- Trigger và stored procedures.
- Unique/exclusion constraints và index maintenance.
- ORM flush order, JDBC batching.
- DDL/maintenance operations và lock modes.
- Transactions dài có nâng cấp mode hoặc giữ nhiều row.

### 9.4. JPA/Hibernate flush order

Trong JPA, gọi entityManager.persist/update entity theo thứ tự Java không bảo đảm SQL INSERT/UPDATE thực thi ngay theo thứ tự đó. Persistence context có thể đợi flush; Hibernate có thể batch/reorder SQL theo chính sách. Với case cần thứ tự khóa chắc chắn, dùng explicit pessimistic lock trên entities theo ID đã sort hoặc một giao thức khóa tài nguyên chung trước khi thay đổi state, rồi kiểm tra generated SQL.

~~~java
// Snippet: chạy trong Spring/JPA transaction, IDs đã được sort.
Account first = entityManager.find(
        Account.class, firstId, LockModeType.PESSIMISTIC_WRITE);
Account second = entityManager.find(
        Account.class, secondId, LockModeType.PESSIMISTIC_WRITE);
if (first == null || second == null) {
    throw new IllegalStateException("Missing account");
}
~~~

Đoạn trên cần Jakarta Persistence imports, entity Account, fields và context, không phải chương trình Java độc lập. Lock mode và lock behavior phụ thuộc provider/DBMS; không dùng một JPA test H2 để khẳng định mọi PostgreSQL/MySQL production path đều không deadlock.

### 9.5. Không có row để khóa

Một truy vấn SELECT ... FOR UPDATE theo primary key không trả row thì **không đặt row lock lên một bản ghi chưa tồn tại**. Với invariant “không được có hai đơn đang tạo cùng mã”, chỉ lock row nếu có sẵn không đủ; hai transactions cùng thấy “chưa tồn tại”. Hãy dùng unique constraint, upsert/insert guarded, advisory lock hoặc shared parent/guard row tùy thiết kế. Deadlock và uniqueness race có thể cùng xuất hiện nhưng là hai vấn đề khác nhau.

## 10. Khi database phát hiện deadlock: PostgreSQL 40P01

PostgreSQL trả **SQLSTATE 40P01 (deadlock_detected)**. Server sẽ phá chu trình bằng cách abort một transaction; bên còn lại có thể được cấp lock rồi tiến tiếp. SQLSTATE ổn định hơn việc parse chuỗi message vì message có thể được dịch hoặc thêm PID/transaction ID.

Bảng phân biệt:

| SQLSTATE | Điều kiện PostgreSQL | Ý nghĩa | Hướng ứng dụng |
| --- | --- | --- | --- |
| **40P01** | deadlock_detected | Một transaction bị abort vì vòng chờ | Rollback hoàn tất, retry toàn use case nếu được phép, sửa lock order |
| **40001** | serialization_failure | Transaction không thể commit an toàn dưới isolation tương ứng | Retry toàn transaction sau khi phân loại và theo policy |
| **55P03** | lock_not_available | Có thể từ NOWAIT hoặc lock_timeout | Không mặc định là deadlock; có thể backoff, báo bận hoặc retry |
| **57014** | query_canceled | Ví dụ statement_timeout hoặc hủy query | Phân tích query/timeout/cancellation, không coi là deadlock |
| **23505** | unique_violation | Vi phạm uniqueness constraint | Có thể là trùng nghiệp vụ; không tự retry vô điều kiện |
| **25P02** | in_failed_sql_transaction | Transaction đã lỗi trước đó và các câu lệnh mới bị từ chối | Kết thúc/rollback transaction bị lỗi trước khi làm việc tiếp |

Spring JDBC có exception translation qua DataAccessException. Tùy driver, translator và version, deadlock có thể xuất hiện dưới dạng subclass như CannotAcquireLockException hoặc exception liên quan pessimistic locking; **đừng ràng buộc mọi luồng xử lý vào đúng một tên exception class** mà chưa kiểm chứng runtime. Trong ví dụ, ta tìm SQLException trong cause chain và kiểm tra SQLSTATE 40P01 để phân loại.

**Khi SQL lỗi khiến PostgreSQL transaction bị abort, không tiếp tục chạy SQL nghiệp vụ trong transaction đó**. Spring TransactionTemplate hoặc @Transactional cần rollback/cleanup; retry phải bắt đầu một transaction mới.

### Cảnh báo về savepoint

PostgreSQL có thể cho phép khôi phục một số lỗi qua ROLLBACK TO SAVEPOINT khi transaction và thiết kế hỗ trợ; nhưng việc dựa vào savepoint để “nuốt lỗi deadlock rồi tiếp tục như chưa có gì” là rủi ro và không thay thế retry toàn business transaction. Khi mục tiêu là hoàn tất một use case sau 40P01, chiến lược rõ ràng là để transaction bị hủy kết thúc, rồi chạy lại toàn bộ read–decide–write trong boundary mới.

### Deadlock victim không đồng nghĩa lỗi dữ liệu

Database abort victim vì liveness/concurrency, không nhất thiết do dữ liệu business sai. Một retry có thể thành công khi transaction còn lại đã commit và nhả lock. Nhưng nếu yêu cầu nghiệp vụ **không idempotent** hoặc side effects đã gửi ra ngoài, retry không thể thực hiện mù quáng. Phần tiếp theo giải thích cách tổ chức.

## 11. Retry đúng vị trí trong Spring: một attempt = một transaction mới

Đặt một vòng retry **ở bên ngoài** service method transactional. Mỗi attempt phải:

1. Mở transaction mới.
2. Đọc lại dữ liệu cần thiết.
3. Kiểm tra business preconditions/invariants.
4. Lấy lock theo canonical order.
5. Ghi thay đổi và commit.
6. Nếu 40P01/40001 được phân loại là retryable, để Spring rollback/cleanup xong rồi thử lại từ bước 1.

**Không chỉ retry câu UPDATE cuối cùng với tham số đọc cũ.** Sau khi transaction khác đã commit, số dư, tồn kho, version hoặc trạng thái đơn hàng có thể khác; quyết định nghiệp vụ phải được tính lại.

~~~text
Attempt 1:
  BEGIN T1
  READ + lock + UPDATE
  deadlock 40P01
  ROLLBACK T1
  Spring release Connection

Backoff

Attempt 2:
  BEGIN T2 mới
  READ lại + kiểm tra lại + lock cùng thứ tự
  UPDATE nếu nghiệp vụ còn hợp lệ
  COMMIT T2
~~~

### Ví dụ skeleton retry ngoài @Transactional

~~~java
// Snippet: this caller KHÔNG nằm trong transaction đang mở.
// transferService là một Spring bean/proxy khác với @Transactional.
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        transferService.transfer(fromId, toId, amount);
        return;
    } catch (org.springframework.dao.DataAccessException ex) {
        boolean retryable = hasSqlState(ex, "40P01")
                || hasSqlState(ex, "40001");
        if (!retryable || attempt == 3) {
            throw ex;
        }
        // Production: backoff tăng dần, jitter và xử lý interruption.
    }
}
~~~

Đây **không phải code độc lập**: cần hàm hasSqlState, biến đầu vào, class/caller và cấu hình transaction. Chỉ nên retry khi business operation được thiết kế an toàn để thử lại. Nếu @Transactional bao **cả vòng for**, các attempts có thể cùng một transaction đã abort — không đúng. Với Spring Retry/@Retryable, chú ý **thứ tự AOP aspects**: retry advice phải được bố trí để mỗi lần gọi đi vào một transactional invocation **mới**.

### Bounded backoff và idempotency

Retry không thể vô hạn. Nên có:

- Số lần thử tối đa và exponential backoff có **jitter**.
- Phân loại SQLSTATE rõ; không retry tất cả DataAccessException.
- Timeout/budget của request, không giữ thread hoặc connection vô hạn.
- Correlation/request ID để tìm tất cả attempts liên quan.
- Idempotency key nếu client hoặc message consumer có thể gửi lại cùng yêu cầu.
- Transactional outbox hoặc after-commit event để tránh gửi email/message nhiều lần khi DB rollback rồi retry.
- Tách remote API calls khỏi transaction khi có thể; remote payment đã thực hiện không tự rollback theo JDBC.

Ví dụ “ghi DB, gửi email, rồi deadlock” rất nguy hiểm: DB có thể rollback nhưng email đã gửi. Retry gửi lại email tạo duplicate. Một thiết kế tốt là ghi cả business change và **outbox event** trong cùng database transaction; worker gửi email/message sau commit với retry/idempotency riêng.

### Chỉ retry một victim, không replay cả hai như cùng thất bại

Trong ví dụ demo, một transaction đã commit, một bị 40P01. Nếu caller retry victim mà cả hai operations **thực sự là hai sự kiện nghiệp vụ độc lập**, có thể hợp lệ cả hai sau cùng đều commit. Nhưng nếu chúng là cùng một request bị gửi trùng, cần idempotency key để không xử lý hai lần. Không suy diễn “deadlock retry được” thành “chạy lại mọi request an toàn”.

## 12. Giữ transaction ngắn để giảm deadlock và lock wait

Consistent order là biện pháp mạnh cho cùng một tập khóa, nhưng transaction kéo dài vẫn tăng thời gian giữ lock và tạo nhiều cơ hội tương tác phức tạp.

**Không nên giữ transaction mở qua:**

- HTTP call tới gateway khác.
- Người dùng chờ xác nhận.
- Gửi email hoặc upload file lớn.
- Tính toán CPU dài không cần đọc/ghi dữ liệu trong transaction.
- Sleep/retry delay hoặc chờ Future đang chạy ở thread khác.
- Batch hàng nghìn row nếu nghiệp vụ có thể chia thành chunks độc lập.

Thay vào đó, chuẩn bị dữ liệu có thể chuẩn bị trước, mở transaction **gần các read–decide–write cần atomic**, lấy lock theo thứ tự chung, kiểm tra lại điều kiện có thể thay đổi, commit sớm và xử lý side effects sau commit.

**Không được đưa bước kiểm tra bất biến quan trọng ra ngoài transaction rồi tin dữ liệu không đổi.** Ví dụ số dư/tồn kho đọc trước lock có thể đã khác khi transaction bắt đầu. Cần kiểm tra lại dưới lock, dùng conditional UPDATE, optimistic version hoặc isolation phù hợp.

### Tránh lock mode rộng hơn yêu cầu

SELECT FOR UPDATE và LOCK TABLE mạnh có thể gây giảm throughput nếu lạm dụng. Khi bài toán chỉ là tăng một counter, một atomic SQL:

~~~sql
UPDATE counter SET value = value + 1 WHERE id = 10;
~~~

có thể vừa đơn giản vừa an toàn hơn cặp SELECT ... FOR UPDATE rồi UPDATE. Tuy nhiên khi phải cập nhật **nhiều row theo một invariant**, cần lựa chọn protocol rộng hơn. Chọn đúng mức lock thay vì “khóa toàn bộ bảng cho chắc”.

## 13. NOWAIT, SKIP LOCKED và timeouts: công cụ khác mục đích

### NOWAIT

~~~sql
SELECT id FROM account WHERE id = 1 FOR UPDATE NOWAIT;
~~~

Nếu không lấy được lock ngay, PostgreSQL báo lỗi thay vì chờ dài. Nó hữu ích cho API cần phản hồi “đang bận”, nhưng không thay thế business correctness hoặc mọi cách tránh deadlock. Lỗi NOWAIT thường thuộc nhóm **lock_not_available** (55P03), không phải bằng chứng deadlock.

### SKIP LOCKED

~~~sql
SELECT id
FROM job_queue
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 10;
~~~

Hữu ích cho **work queue**: worker có thể bỏ qua job đang bị worker khác khóa. Nhưng kết quả không phản ánh một snapshot hoàn chỉnh của toàn bảng; **không nên dùng SKIP LOCKED tùy tiện** cho bài toán chuyển tiền hoặc kiểm tra invariant cần thấy đủ row. Đổi nội dung đọc bằng cách bỏ qua row bị khóa có thể phá logic nghiệp vụ.

### PostgreSQL timeout settings

| Cấu hình | Ý nghĩa |
| --- | --- |
| **deadlock_timeout** | Sau khoảng chờ này PostgreSQL cân nhắc chạy deadlock detector; không phải “tự abort mọi lock wait chậm” |
| **lock_timeout** | Giới hạn chờ lấy lock; vượt mức có thể hủy statement với lỗi lock_not_available |
| **statement_timeout** | Giới hạn thời gian xử lý statement; có thể timeout dù không chờ lock |
| **idle_in_transaction_session_timeout** | Giới hạn session giữ transaction mở nhưng idle; giúp giảm lock giữ vô thời hạn |
| **@Transactional(timeout=...)** | Metadata timeout của Spring transaction, enforcement tùy manager/driver/operation; không đồng nhất với mọi PostgreSQL server setting |

Nếu lock_timeout quá ngắn so với deadlock_timeout, request có thể báo lock timeout **trước khi PostgreSQL deadlock detector nhận diện vòng chờ**; việc không nhìn thấy 40P01 lúc đó không chứng minh ứng dụng không còn vòng chờ. Với bài demo, không đặt lock_timeout quá ngắn, và dùng deadlock detector cấu hình bình thường.

Không chỉnh global deadlock_timeout hoặc statement_timeout trên production chỉ để minh họa. Các tham số này phải được DBA/operations đánh giá theo workload, quyền và môi trường. Timeout là **cơ chế giới hạn thiệt hại/độ trễ**, không thay thế lock ordering.

## 14. Quan sát deadlock trong PostgreSQL

### 14.1. Đọc log lỗi

PostgreSQL thường cung cấp thông điệp **deadlock detected**, SQLSTATE 40P01 và thông tin bổ sung về các process/locks/statements liên quan. Log server có thể ghi một wait graph. **PID, transaction ID và nạn nhân cụ thể thay đổi theo lần chạy**; không nên hardcode các giá trị này trong test.

Khi ứng dụng xuất hiện 40P01, nên log có chọn lọc:

- Correlation ID và operation name.
- SQLSTATE và exception class (không chỉ message).
- Transaction attempt number, thời lượng.
- Tên transaction/resource nếu có.
- Database connection/backend PID khi công cụ cho phép và phù hợp.
- Mẫu SQL hoặc fingerprint đã loại dữ liệu nhạy cảm.

Đừng in nguyên payment credentials, token hoặc PII trong SQL params để debug lock.

### 14.2. pg_stat_activity và pg_blocking_pids

Trong PostgreSQL, nếu có quyền phù hợp, một truy vấn giám sát blocker:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    LEFT(query, 120) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY pid;
~~~

Cột **wait_event_type='Lock'** cho biết backend có thể đang chờ lock. **pg_blocking_pids(pid)** cho danh sách blocker theo quan sát hiện tại. Quan hệ có thể thay đổi nhanh; database deadlock detector và log lỗi vẫn là nguồn bằng chứng đáng tin khi đã phát hiện deadlock.

Với môi trường có nhiều tenant, hạn chế quyền xem SQL của session khác và không ghi query sample chứa thông tin nhạy cảm vào log ứng dụng.

### 14.3. pg_locks và số liệu tích lũy

~~~sql
SELECT pid, locktype, mode, granted, relation::regclass AS relation_name,
       transactionid
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

Một số row-level conflicts có thể biểu lộ qua các lock vào transaction ID hoặc cơ chế khác; không thể chỉ nhìn một row pg_locks rồi suy ra toàn bộ wait chain. Kết hợp pg_blocking_pids, pg_stat_activity, log server và SQL execution path.

Số deadlocks tích lũy của database:

~~~sql
SELECT datname, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

Đây là **counter cộng dồn** trong cửa sổ thống kê DBMS, không phải số deadlock của riêng một request. Muốn đo rate, lấy delta theo thời gian; so với traffic và concurrency. Metric tăng nên dẫn tới điều tra những đường lock order khác nhau và transaction duration.

### 14.4. Đừng đợi production mới kiểm thử

Một kế hoạch observability tốt bao gồm dashboard:

- Deadlocks per minute hoặc deadlocks / thousand transactions.
- Lock wait time và blocked sessions.
- Transaction duration (P95/P99).
- Connection pool active, idle, pending và timeout.
- Số retries/attempts, số lần thành công sau retry, số lần exhausted.
- SQL fingerprint thường xuất hiện trong deadlock report.

Các chỉ số chỉ giúp tìm điểm nóng; **để sửa dứt điểm cần tìm vòng chờ cụ thể và thống nhất thứ tự lock giữa các code paths**.

## 15. Lỗi phổ biến trong Spring/JPA khi xử lý deadlock

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gắn @Transactional rồi cho rằng sẽ không deadlock | DB vẫn có hai transactions chờ vòng | Thiết kế lock order và xử lý 40P01 |
| Mọi chiều chuyển tiền đều khóa fromId trước | A->B và B->A khóa đảo ngược | Sort account IDs rồi khóa ID nhỏ trước |
| Repository A sort, background worker B không sort | Vẫn có vòng giữa các paths | Chuẩn hóa protocol xuyên toàn hệ thống |
| HashSet/HashMap iteration quyết định lock order | Order không ổn định/không phải contract | Comparator ổn định, sort trước khi lấy lock |
| Dựa vào thứ tự method gọi trong JPA | Flush/SQL có thể diễn ra sau hoặc reorder | Lock explicit theo canonical order, xem SQL thật |
| Dùng @Transactional trên this.inner() rồi mong advice chạy | Self-invocation bỏ qua proxy mode | Gọi qua Spring-managed bean/proxy phù hợp |
| Catch DataAccessException bên trong @Transactional và tiếp tục SQL | PostgreSQL transaction đã abort, dễ nhận 25P02 | Cho exception thoát và rollback, retry ngoài |
| Retry trong một outer transaction đã mở | Attempt sau vẫn dùng transaction lỗi hoặc rollback-only | Mỗi attempt một transaction mới |
| Retry chỉ statement cuối sau lỗi | Điều kiện tiền đề đã cũ | Chạy lại toàn bộ read–decide–write |
| Retry vô hạn, không có jitter | Retry storm, tăng contention | Giới hạn attempt, backoff/jitter, metric |
| Gửi email trước commit rồi retry | Email/message có thể bị gửi trùng | Outbox/after-commit/idempotency |
| Thấy lock wait rồi gọi đó là deadlock | Chẩn đoán sai | Kiểm tra SQLSTATE 40P01 hoặc wait cycle |
| Đặt lock_timeout cực ngắn để “chữa deadlock” | Che giấu deadlock bằng timeout, request thất bại sớm | Sửa lock order, giữ transaction ngắn; timeout chỉ là phụ trợ |
| SELECT FOR UPDATE một row không tồn tại | Không có row nào được khóa | Unique/guard/advisory lock hoặc thiết kế constraint |
| Dùng SKIP LOCKED cho nghiệp vụ phải đọc đầy đủ | Bỏ qua row, sai kết quả | Chỉ dùng khi queue semantics cho phép |
| Chia thao tác thành REQUIRES_NEW tùy tiện | Các commits độc lập, pool có thể cạn và outer còn giữ lock | Chọn propagation theo business atomicity và resource costs |

### Spring AOP và propagation liên quan thế nào?

Một @Transactional service method chỉ thực sự điều khiển transaction khi lời gọi đi qua Spring proxy (trong proxy mode). **Self-invocation** hoặc object tạo bằng new có thể làm boundary không tồn tại. Nếu outer REQUIRED đã mở, inner REQUIRED tham gia transaction đó; nếu inner REQUIRES_NEW, Spring suspend outer và mở transaction khác, thường cần thêm connection. REQUIRES_NEW **không phải thuốc chống deadlock**: transaction inner vẫn có thể tranh chấp lock với outer hoặc các transactions khác, thậm chí còn làm phức tạp graph vì outer giữ resource khi đang suspend.

Nếu có nhiều transaction managers/DataSources, cần xác định manager thật đang điều khiển SQL. Một transaction manager local của DB A không thể điều khiển mọi lock/commit của DB B. Với distributed resources phải đánh giá kiến trúc consistency và công nghệ tương ứng.

## 16. Quy trình điều tra deadlock thực tế

Khi nhận cảnh báo deadlock:

1. **Xác nhận lỗi:** nhận SQLSTATE 40P01 (PostgreSQL) từ cause/log. Tách riêng 40001, 55P03, 57014.
2. **Xác định các participants:** correlation IDs, backend PIDs, SQL fingerprint và các bảng/row/lock modes từ log.
3. **Dựng wait-for graph:** T1 giữ gì, chờ gì; T2 giữ gì, chờ gì; vòng nào tạo deadlock.
4. **Đọc toàn bộ transaction code paths:** service, repository, scheduler, ORM flush, trigger, FK, background jobs.
5. **Xác định canonical lock order:** resource type và primary key; viết thành contract có thể review.
6. **Cân nhắc lock modes:** lấy lock đủ mạnh từ đầu nếu cần, tránh upgrade deadlock.
7. **Giảm lock duration:** bỏ remote calls/sleeps khỏi transaction, tối ưu query/index, phân nhỏ batch theo business atomicity.
8. **Đặt retry an toàn:** tại outer caller; mỗi attempt mở transaction mới; giới hạn/backoff, phân loại lỗi.
9. **Thử bằng hai transactions đồng thời:** interleaving trước/sau thay đổi, đọc dữ liệu sau commit.
10. **Theo dõi sau rollout:** deadlock count, lock waits, pool saturation, retry success và request latency.

**Ví dụ một root cause:** transfer() và nightly-reconcile() cập nhật cùng hai tài khoản; transfer dùng from->to, reconcile dùng sorted ID. Chỉ cần một chiều chuyển tiền ngược là xuất hiện vòng. Sửa bằng cách cả hai dùng sorted ID trước khi cập nhật. Nếu nguyên nhân đến từ trigger/unique constraint khác, phải cập nhật thứ tự tài nguyên ở tầng đó chứ không chỉ thay một method Java.

## 17. Kiểm thử concurrency trong Spring

Một unit test tuần tự sẽ không phát hiện deadlock nếu không có interleaving:

~~~text
T1: lock A, lock B, commit
T2: lock B, lock A, commit
=> Không có thời điểm hai transaction giữ lock chéo nhau.
~~~

Muốn kiểm thử, cần:

1. **Hai connection/physical transactions độc lập** đồng thời.
2. Một barrier/latch đặt tại đúng vị trí giữa hai lần lấy lock **chỉ trong test**.
3. Assertions cho kết quả gồm **commits**, **deadlock errors**, **dữ liệu sau kết thúc**.
4. Dùng DBMS gần production; H2 có thể có semantics và error codes khác PostgreSQL.
5. Không chạy cả hai workers trong **cùng @Transactional test context** rồi nghĩ đó là hai transaction độc lập.
6. Kiểm thử protocol mới với nhiều permutations (A->B, B->A, batch trùng ID, nhiều hơn hai row).
7. Chạy với cùng schema constraints, indexes, triggers/ORM flush như production.
8. Thử retry của victim sau rollback trong transaction mới, kiểm tra idempotency/constraints.
9. Kiểm thử cả failure modes: lock timeout, serialization failure, deadlock, network interruption, commit failure.

Trong Spring TestContext, nếu test method có @Transactional, framework có thể rollback cuối test và không đại diện cho commit thật. Cần đọc dữ liệu bằng transaction/connection độc lập sau khi worker hoàn tất. Demo Java ở phần 7 dùng TransactionTemplate trong từng worker để tránh nhầm transaction context bị chia sẻ qua thread.

### Ví dụ checklist assertions

| Test | Hành vi chờ đợi |
| --- | --- |
| Opposite order + barrier sau lock đầu | PostgreSQL phát hiện 40P01; một transaction rollback, một commit |
| Same order + barrier trước lock đầu | Hai transaction lần lượt commit, không có vòng do hai row |
| Same order + nhiều request | Không có deadlock từ chính tập row/lock order đã chuẩn hóa |
| Inner REQUIRES_NEW gặp outer locks | Không giả định an toàn; kiểm tra lock wait/pool timeout |
| Retry victim sau 40P01 | Mở transaction mới và đọc lại state; business result vẫn hợp lệ |
| Retry gửi message/event | Không tạo side effect trùng nếu request/idempotency/outbox bảo vệ |
| ORM flush/trigger/foreign key | Không phát sinh lock order trái convention từ tầng gián tiếp |

## 18. Câu hỏi tự kiểm tra

**1. Vì sao T1 giữ A chờ B và T2 giữ B chờ A là deadlock, còn T2 chỉ chờ T1 giữ A thì không?**  
Vì deadlock cần **chu trình chờ**. Trường hợp thứ hai T1 không bị chặn bởi T2 nên vẫn có thể commit và nhả A cho T2.

**2. PostgreSQL tự động phát hiện deadlock có nghĩa ứng dụng không phải làm gì?**  
Không. PostgreSQL chỉ phá vòng bằng abort một transaction. Ứng dụng phải xử lý lỗi, rollback/cleanup và retry toàn nghiệp vụ nếu an toàn; phòng ngừa bằng lock order vẫn quan trọng.

**3. Tại sao chuyển tiền A->B và B->A không nên khóa fromId trước?**  
Vì hai request có thể khóa thứ tự ngược nhau. Hãy khóa account IDs theo một canonical order, sau đó debit/credit theo chiều nghiệp vụ.

**4. Một câu UPDATE theo row ID có tạo lock dù không dùng SELECT FOR UPDATE không?**  
Có. UPDATE thường lấy lock phục vụ ghi nên deadlock row-level có thể xảy ra mà không có explicit SELECT FOR UPDATE.

**5. Vì sao sort một HashSet bằng stream().sorted() có ích?**  
Nó tạo thứ tự ổn định để các transaction lấy row locks theo cùng một quy tắc; cần áp dụng ở mọi paths và xác minh DB SQL thực tế.

**6. Tại sao 40P01 khác 55P03?**  
40P01 là deadlock_detected — vòng chờ được database phát hiện. 55P03 là lock_not_available — ví dụ do NOWAIT/lock_timeout, không chứng minh có vòng chờ.

**7. Vì sao retry phải ở ngoài @Transactional boundary?**  
Vì PostgreSQL transaction đã bị lỗi/abort, phải kết thúc và mở transaction mới. Retry trong cùng transaction lỗi không khôi phục trạng thái để làm lại use case.

**8. Nếu ORM gọi persist(A) rồi persist(B), có chắc DB lấy lock theo thứ tự đó?**  
Không. ORM có thể defer và reorder SQL khi flush/batch. Phải quan sát SQL thực tế hoặc explicit lock theo canonical order.

**9. Dùng @Transactional(timeout=10) có tránh hết deadlock không?**  
Không. Timeout giới hạn thời gian theo mức hỗ trợ; nó không loại bỏ vòng chờ và có thể báo lỗi timeout trước deadlock detector.

**10. Một request đã gửi email rồi transaction bị deadlock và rollback. Nếu retry có gì nguy hiểm?**  
Email đã gửi không rollback cùng DB, retry có thể gửi trùng. Cần outbox, after-commit workflow và idempotency.

**11. Có nên dùng SKIP LOCKED để giải quyết lock wait trong chuyển tiền?**  
Không tùy tiện. Bỏ qua row đang khóa làm mất dữ liệu cần kiểm tra và có thể phá logic; SKIP LOCKED hợp với job queue, không phải bất kỳ invariant liên nhiều row.

**12. Có thể loại 100% mọi deadlock bằng việc sort hai account IDs không?**  
Không. Nó loại vòng do hai account row nếu mọi transaction tuân thủ, nhưng còn locks khác qua FK, unique, triggers, ORM flush, DDL và nhiều resource types.

## 19. Kết luận và nguyên tắc áp dụng

- **Deadlock = chu trình transaction chờ lock của nhau**, không đồng nghĩa mọi lock wait chậm.
- **Spring @Transactional cung cấp atomic boundary, không tự quyết định thứ tự locks** ở DBMS.
- **Canonical lock order** cần thống nhất cho mọi code paths: resource type, stable ID, lock mode; ưu tiên lấy mode cần thiết từ đầu.
- Với chuyển tiền hai chiều, **khóa id nhỏ rồi id lớn** trước, sau đó debit/credit đúng chiều nghiệp vụ.
- PostgreSQL phá deadlock bằng **SQLSTATE 40P01**, abort một victim; transaction còn lại có thể tiếp tục.
- **Retry toàn transaction**, với fresh reads, bounded attempts/backoff, phân loại lỗi và idempotency; không tiếp tục trên transaction đã abort.
- Giữ transaction ngắn, không dùng remote calls/sleep trong critical section.
- Kiểm chứng bằng **concurrent integration test trên DBMS thật**, kết hợp log lỗi, pg_stat_activity, pg_blocking_pids, pool metrics và dữ liệu sau commit.
- **Không suy diễn không deadlock tuyệt đối** từ một quy tắc sort, bởi locks còn có thể phát sinh gián tiếp từ index, trigger, FK, ORM và DDL.

## Tài liệu tham khảo

- [PostgreSQL — Explicit Locking, mục Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — Error Codes: 40P01, 40001, 55P03, 57014](https://www.postgresql.org/docs/current/errcodes-appendix.html)
- [PostgreSQL — Lock Management, deadlock_timeout](https://www.postgresql.org/docs/current/runtime-config-locks.html)
- [PostgreSQL — Client Connection Defaults, lock_timeout / statement_timeout](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [PostgreSQL — Monitoring Statistics, pg_stat_activity và pg_locks](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Serialization Failure Handling](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
