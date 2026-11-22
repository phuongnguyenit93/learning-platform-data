# Lost update, write skew và bất biến giữa nhiều bản ghi trong Spring transaction management

## 1. Tại sao @Transactional chưa đủ bảo đảm đúng nghiệp vụ khi có concurrency?

**@Transactional** giúp Spring tạo ranh giới commit/rollback cho một nhóm thao tác trên tài nguyên được quản lý. Tuy nhiên, hai request có thể chạy **đúng transaction**, mỗi request đều commit thành công, nhưng kết quả **sai bất biến nghiệp vụ** do chúng cùng ra quyết định trên dữ liệu cũ.

Hai kiểu lỗi cần phân biệt:

- **Lost update (mất cập nhật):** hai transaction cùng đọc một giá trị, mỗi transaction tính giá trị mới dựa trên bản đã đọc; một lần ghi sau đó **ghi đè kết quả** của lần ghi kia. Ví dụ hai người cùng cộng 10 vào một số dư 100 nhưng giá trị cuối chỉ là 110, thay vì 120.
- **Write skew (lệch ghi):** hai transaction đọc **một điều kiện liên quan nhiều bản ghi**, rồi cập nhật **những bản ghi khác nhau**. Do không đụng cùng một row để gây xung đột ghi trực tiếp, cả hai có thể commit nhưng **làm sai bất biến chung**. Ví dụ trong ca trực phải luôn còn ít nhất một bác sĩ, nhưng hai bác sĩ cùng xin nghỉ khiến không còn ai trực.

Hai hiện tượng đều là **read–decide–write race**: kết quả quyết định được tạo từ một snapshot không còn phù hợp với toàn bộ lịch sử commit. Nhưng cách giải quyết khác nhau. Khóa hoặc version một row thường đủ chống lost update trên row đó; write skew còn cần bảo vệ **predicate/tập row/bất biến liên bản ghi**.

Bài này thuộc nhóm **Mức cô lập** của Spring Framework transaction management. Ta sẽ mô tả lịch thực thi theo thời gian, đối chiếu các mức isolation, viết ví dụ Java 17+ với Spring JDBC và PostgreSQL, rồi xây dựng chiến lược khóa, version, constraint và retry phù hợp. Không được chỉ nhìn sự hiện diện của @Transactional để kết luận toàn bộ nghiệp vụ đã nhất quán.

### Sau bài học, bạn cần làm được

1. Phân biệt dirty read, nonrepeatable read, phantom, lost update và write skew mà không đánh đồng các khái niệm.
2. Chỉ ra chính xác **transaction nào đọc gì, quyết định gì, ghi row nào và commit khi nào**.
3. Giải thích vì sao READ_COMMITTED cho phép lost update theo mô hình đọc–tính–ghi và vì sao PostgreSQL REPEATABLE_READ vẫn có thể cho phép write skew.
4. Hiểu bất biến liên nhiều bản ghi khác với CHECK constraint của từng row.
5. Chọn trong các cách: atomic UPDATE, optimistic locking, SELECT FOR UPDATE, shared guard row, SERIALIZABLE và retry toàn transaction.
6. Đặt isolation tại ranh giới Spring transaction phù hợp, lưu ý REQUIRED tham gia outer transaction.
7. Kiểm chứng kết quả bằng hai connection/transaction đồng thời, không bằng một unit test chạy tuần tự.

## 2. Ba khái niệm nền: atomicity, isolation và invariant

**Atomicity** là “hoặc tất cả thay đổi thuộc *một transaction* được commit, hoặc không thay đổi nào thuộc transaction đó được commit”. **Isolation** quy định các transaction đồng thời được quan sát và ảnh hưởng lẫn nhau như thế nào. **Business invariant** là điều kiện mà trạng thái database hợp lệ phải thỏa, kể cả sau khi hai người cùng hành động.

Ví dụ hệ thống tài khoản:

- Bất biến row: balance >= 0 cho từng tài khoản.
- Bất biến liên row: tổng một nhóm tài khoản sau chuyển tiền nội bộ không thay đổi.
- Bất biến liên bảng: mỗi booking được xác nhận phải có một reservation hợp lệ.
- Bất biến predicate: trong một đội phải có ít nhất một thành viên đang trực.

Hai transaction có thể **mỗi transaction đều atomic** nhưng vẫn phá vỡ invariant khi cùng đọc dữ liệu và ra quyết định mà isolation/locking không bảo vệ đủ. Vì vậy, câu “hai transaction đều được Spring commit” không đồng nghĩa “mọi invariant đều đúng”.

### Một lịch thực thi (interleaving) là gì?

Đặt tên hai transaction là **T1** và **T2**. Mỗi transaction chứa một chuỗi thao tác đọc và ghi. Khi chạy đồng thời, các thao tác có thể đan xen:

~~~text
T1: READ X -> tính toán -> WRITE X -> COMMIT
T2:     READ X -> tính toán -----> WRITE X -> COMMIT
~~~

Để phân tích anomaly, hãy viết **giá trị mà mỗi transaction thực sự nhìn thấy** thay vì chỉ ghi “T1 chạy trước T2”. Đối với một DBMS có MVCC, thời điểm lấy snapshot và thời điểm lấy write lock đều quan trọng.

**Serializable** có nghĩa kết quả của những transaction commit phải tương đương với **một thứ tự chạy tuần tự nào đó**, không nhất thiết các câu SQL trên server thực sự chạy lần lượt. PostgreSQL thực hiện Serializable Snapshot Isolation (SSI), có thể **hủy một transaction với serialization_failure** để ngăn lịch thực thi không thể tuần tự hóa. Ứng dụng cần biết retry.

## 3. Lost update: khi hai lần tăng chỉ còn một

### 3.1. Kịch bản đọc–tính–ghi

Giả sử counter.amount = 100. Hai request độc lập cùng muốn tăng 10:

~~~text
Thời điểm       T1                                  T2
-------------------------------------------------------------------
t1              SELECT amount -> 100
t2                                                  SELECT amount -> 100
t3              Tính newValue = 110
t4                                                  Tính newValue = 110
t5              UPDATE counter SET amount=110
t6              COMMIT
t7                                                  UPDATE counter SET amount=110
t8                                                  COMMIT

Giá trị cuối = 110 (sai); đúng ra cần 120.
~~~

Cả T1 và T2 có thể commit bình thường ở **PostgreSQL READ COMMITTED**. Ở t7, UPDATE của T2 có thể phải đợi lock của T1, nhưng **tham số 110 đã được ứng dụng tính từ lần đọc cũ**. Việc chờ lock không tự biến 110 thành 120.

Đây là kiểu lost update **do ứng dụng tự đưa giá trị mới tuyệt đối**:

~~~java
// Snippet minh họa; hai request có thể cùng đọc 100.
int balance = jdbc.queryForObject(
        "SELECT amount FROM counter WHERE id = 1", Integer.class);
int newValue = balance + 10;
jdbc.update("UPDATE counter SET amount = ? WHERE id = 1", newValue);
~~~

Nếu một request khác đã cập nhật trong khoảng giữa SELECT và UPDATE, câu UPDATE trên vẫn có thể ghi đè thay đổi đã commit mà code không biết.

### 3.2. Không phải mọi UPDATE đồng thời đều lost update

Thay bằng một SQL **atomic read–modify–write ở database**:

~~~sql
UPDATE counter
SET amount = amount + 10
WHERE id = 1;
~~~

Ở PostgreSQL READ COMMITTED, hai UPDATE cùng row sẽ được DBMS phối hợp qua row locking và áp dụng phép cộng lên phiên bản row phù hợp. Nếu cả hai thành công và commit, 100 -> 110 -> 120. Điều này khác với việc truyền một hằng số newValue=110 đã tính sẵn trong Java.

**Giới hạn:** câu UPDATE atomic giải quyết phép cộng một row, nhưng **không tự giải quyết bất biến đòi hỏi đọc nhiều row rồi cập nhật hai row khác nhau**. Không được suy luận rằng chuyển mọi UPDATE sang phép cộng là đã loại được write skew.

### 3.3. Các cách khác để bảo vệ một row

- **Pessimistic row lock:** đọc bằng SELECT ... FOR UPDATE **bên trong cùng transaction**, rồi tính và ghi; các writer cạnh tranh cùng row sẽ tuần tự theo lock.
- **Optimistic locking/version:** đọc cùng version; khi ghi dùng WHERE version = giá trị đã đọc; nếu updateCount = 0 thì có conflict, không được lặng lẽ coi như commit.
- **Isolation mạnh hơn:** trên PostgreSQL, REPEATABLE READ/Serializable có thể từ chối một transaction khi phát hiện concurrent update của cùng row; **phải retry** nếu muốn request hoàn tất.
- **Conditional UPDATE:** với số dư không được âm, một statement có thể gộp điều kiện và cập nhật: UPDATE ... SET balance=balance-? WHERE id=? AND balance>=?, rồi kiểm tra số row bị ảnh hưởng.

Ví dụ optimistic version:

~~~java
// Snippet: trước đó đã đọc amount, version từ một row.
int updated = jdbc.update(
        "UPDATE counter SET amount = ?, version = version + 1 " +
        "WHERE id = ? AND version = ?",
        proposedAmount, counterId, oldVersion);
if (updated != 1) {
    throw new org.springframework.dao.OptimisticLockingFailureException(
            "Counter has changed; retry the whole operation");
}
~~~

Đây là snippet, không phải Java file độc lập; biến proposedAmount, counterId, oldVersion phải tồn tại. Trong JPA, @Version giúp tạo cơ chế optimistic version tương tự cho entity đã được quản lý. **Version trên từng entity không tự ngăn write skew trên nhiều entity**: hai request có thể cập nhật hai row khác nhau, không có version conflict trực tiếp.

## 4. Write skew: invariant đúng ở mỗi snapshot nhưng sai sau cả hai commit

### 4.1. Ví dụ hai bác sĩ trực

Bảng doctors:

| id | name | on_call |
| --- | --- | --- |
| 1 | An | true |
| 2 | Bình | true |

**Bất biến kinh doanh:** tại mọi trạng thái đã commit, phải còn **ít nhất một bác sĩ on_call = true**.

Yêu cầu của từng bác sĩ: “Tôi có thể rời ca nếu hiện còn ít nhất hai người trực”. Hai request đồng thời:

~~~text
Thời điểm      T1 (bác sĩ An)                  T2 (bác sĩ Bình)
--------------------------------------------------------------------
t1             SELECT COUNT(on_call) -> 2
t2                                             SELECT COUNT(on_call) -> 2
t3             Nếu >= 2, cho An nghỉ
t4                                             Nếu >= 2, cho Bình nghỉ
t5             UPDATE doctors SET false
               WHERE id=1
t6                                             UPDATE doctors SET false
                                               WHERE id=2
t7             COMMIT
t8                                             COMMIT

Trạng thái cuối: An=false, Bình=false -> COUNT(on_call)=0.
Bất biến >= 1 đã bị phá vỡ.
~~~

**Điểm đặc trưng:** T1 ghi **row 1**, T2 ghi **row 2**; hai write sets không đụng cùng row. Khi mỗi transaction kiểm tra COUNT, nó đọc một snapshot mà cả hai vẫn đang trực. Bởi vậy, optimistic version riêng của row 1 và row 2 cũng có thể **đều cập nhật thành công**, không báo xung đột.

### 4.2. Vì sao REPEATABLE READ chưa chắc ngăn được?

Ở **PostgreSQL**, REPEATABLE READ dùng **transaction-level snapshot isolation**. Nó tránh nonrepeatable read theo snapshot, đồng thời phát hiện một số concurrent update trên cùng row. Nhưng write skew **có thể xảy ra** vì hai transaction cùng đọc một predicate và ghi những row khác nhau; không có xung đột ghi cùng row bắt buộc một bên thất bại.

~~~text
Snapshot của T1: [An=true, Bình=true] -> COUNT=2
Snapshot của T2: [An=true, Bình=true] -> COUNT=2

T1 chỉ ghi An=false.
T2 chỉ ghi Bình=false.

Mỗi transaction tự nhìn kết quả hợp lệ dựa trên snapshot của nó.
Trạng thái tổng hợp sau hai commit: không ai trực.
~~~

**Serializable** trên PostgreSQL nhận diện dependency/cycle làm lịch thực thi không thể tương đương với một thứ tự tuần tự hợp lệ. Thông thường **một transaction bị rollback với SQLSTATE 40001**, transaction còn lại commit; nếu retry toàn bộ giao dịch thua cuộc, lần đọc mới thấy chỉ còn một người trực và không cho bác sĩ cuối cùng nghỉ.

Không được khẳng định mọi DBMS triển khai REPEATABLE READ như PostgreSQL. MySQL/InnoDB, Oracle, SQL Server và các database khác có khác biệt MVCC, locking, snapshot và mức tên tương ứng. Khi viết phần mềm cần tính đúng đắn, phải kiểm chứng theo **engine/version/isolation thực tế**.

### 4.3. Write skew khác mất cập nhật và khác phantom

| Hiện tượng | Tâm điểm | Ví dụ |
| --- | --- | --- |
| **Lost update** | Hai thao tác ghi ảnh hưởng cùng giá trị nhưng một thay đổi bị ghi đè | Hai người đọc 100 rồi cùng UPDATE amount=110 |
| **Write skew** | Hai transaction đọc điều kiện chung rồi ghi các row khác nhau, phá invariant | Hai bác sĩ đồng thời tự tắt on_call |
| **Nonrepeatable read** | Cùng transaction đọc lại *cùng row* và thấy giá trị mới đã commit | T1 SELECT balance=100 rồi SELECT lại thấy 90 |
| **Phantom read** | Cùng transaction chạy lại predicate query và thấy tập row thay đổi | T1 COUNT bookings rồi T1 COUNT lại thấy row mới từ T2 |
| **Dirty read** | Đọc dữ liệu chưa commit của transaction khác | T1 thấy giá trị T2 chưa commit, rồi T2 rollback |

Write skew không đòi hỏi query được chạy hai lần; mỗi transaction **chỉ cần đọc một lần** rồi ghi trên snapshot cũ. Vì vậy việc một test chỉ xác minh “tôi đọc lại trong cùng transaction không thay đổi” không đủ bảo vệ invariant liên nhiều row.

## 5. Isolation levels: phải hiểu theo DBMS cụ thể

Bốn tên chuẩn JDBC/Spring:

- READ_UNCOMMITTED
- READ_COMMITTED
- REPEATABLE_READ
- SERIALIZABLE

Ngoài ra, Spring có Isolation.DEFAULT, để dùng mức mặc định của datasource/database. Bảng dưới nói về **PostgreSQL hiện đại** (không nên thay thành quy tắc chung cho mọi engine):

| Isolation | Snapshot/đặc tính PostgreSQL | Lost update kiểu application read-then-set | Write skew hai bác sĩ |
| --- | --- | --- | --- |
| READ UNCOMMITTED | PostgreSQL xử lý như READ COMMITTED | Có thể xảy ra | Có thể xảy ra |
| READ COMMITTED | Snapshot theo mỗi statement; không đọc uncommitted | Có thể xảy ra khi ghi giá trị cũ tính ở Java | Có thể xảy ra |
| REPEATABLE READ | Snapshot nhất quán theo transaction; phát hiện concurrent update trên cùng row | Lịch concurrent same-row update thường bị từ chối bằng serialization failure thay vì mất cập nhật | **Vẫn có thể xảy ra** khi update hai row khác nhau |
| SERIALIZABLE | SSI ngăn lịch commit không tương đương chạy tuần tự | Không để lịch commit sai tính serializable; có thể rollback/retry | Một transaction thường bị hủy khi phát hiện write skew, phải retry |

**Không xem “SERIALIZABLE” là “khóa toàn bộ database”.** PostgreSQL dùng SSI dựa trên snapshot và phát hiện dependency, có thể trả lỗi serialization_failure để yêu cầu ứng dụng thử lại. Phương án này bảo vệ serializability nếu các transaction liên quan được thiết kế và chạy ở mức phù hợp, nhưng đổi lại có rollback/retry và chi phí quan sát.

**Lưu ý ngôn ngữ:** SQL standard ban đầu thường mô tả các cấp bằng dirty/nonrepeatable/phantom. “Write skew” là một anomaly cụ thể dưới snapshot isolation; tên REPEATABLE_READ tự nó **không** xác nhận rằng mọi invariant đọc nhiều row đều an toàn.

### Không gộp propagation với isolation

~~~java
// Snippet trong service, cần Spring bean/proxy và đúng manager.
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE)
public void decideDuty() {
    // read invariant, then update rows ...
}
~~~

Nếu method tham gia **outer REQUIRED transaction đã tồn tại** ở READ_COMMITTED, isolation đặt ở inner **thường không đổi** physical transaction của outer. Spring mặc định có thể im lặng bỏ qua isolation của scope tham gia; để phát hiện mismatch, xét validateExistingTransaction=true trên AbstractPlatformTransactionManager.

Vì vậy, hãy đặt mức isolation ở **ranh giới tạo physical transaction** đúng với use case, không chỉ ở một DAO method con. Cần biết transaction manager nào điều phối JDBC/JPA resource thật, và một method @Transactional phải được gọi qua Spring proxy trong proxy mode.

## 6. Hai bất biến điển hình: cùng một row và nhiều row

### Bất biến A — không âm trên một tài khoản

Một row accounts(id,balance) và điều kiện balance>=0:

~~~sql
UPDATE accounts
SET balance = balance - 30
WHERE id = 1 AND balance >= 30;
~~~

Kiểm tra **updateCount==1** để biết debit có thành công. Câu SQL vừa kiểm tra điều kiện vừa ghi dưới DB row locking, tránh kịch bản hai request cùng đọc balance rồi cùng tự viết giá trị mới mà không phối hợp.

Kết hợp với **CHECK(balance >= 0)** để có lớp bảo vệ ở database cho từng row. Constraint giúp bắt lỗi nếu một đường code khác ghi số âm.

### Bất biến B — ít nhất một bác sĩ trực trong cả đội

Điều kiện:
 
~~~sql
SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
~~~

Đây là một **predicate trên nhiều row**. Một **CHECK(on_call ...)** trên từng row không thể tự chứng minh còn ai khác on_call=true. CHECK constraint kiểu per-row thông thường không thể chứa logic COUNT(*) trên cả bảng trong PostgreSQL. Vì vậy cần một chiến lược đồng bộ ở cấp rộng hơn, chẳng hạn:

- **SERIALIZABLE** và retry toàn bộ transaction khi lỗi 40001.
- **Pessimistic locking:** khóa trước toàn bộ các row/guard resource liên quan, sau đó **đọc lại điều kiện và cập nhật trong cùng transaction**.
- **Shared guard row:** mọi hành động thay đổi tư cách trực khóa/cập nhật một row đại diện của đội; mọi writer phải tuân thủ protocol đó.
- **Thiết kế lại dữ liệu/invariant:** một bản ghi “current on-call doctor” với unique/foreign-key/constraint phù hợp khi nghiệp vụ cho phép, hoặc counter/aggregate có cập nhật atomic kèm CHECK.
- **Database logic có kiểm soát** như constraint trigger kết hợp locking/serializable nếu cần chặn tất cả đường ghi, không chỉ Java service.

Chỉ thêm **@Version** vào entity bác sĩ đang sửa không ngăn hai bác sĩ khác nhau cùng nghỉ. Version hữu ích nếu mọi giao dịch đồng thời cập nhật **cùng một guard row/version** hoặc một cơ chế kiểm tra cấp invariant tương đương.

## 7. Demo Java 17+ với Spring JDBC và PostgreSQL

Ví dụ này cố ý dùng **PostgreSQL 16** để minh họa chính xác đặc tính MVCC, REPEATABLE READ và SSI SERIALIZABLE. H2 rất hữu ích để học CRUD, nhưng isolation/locking behavior có thể khác PostgreSQL; dùng H2 rồi khẳng định write skew/SSI của PostgreSQL là một sai lầm.

Bốn thí nghiệm chạy hai transaction đồng thời, đồng bộ bằng **CyclicBarrier** để buộc cả hai worker hoàn tất bước đọc **trước khi bất kỳ worker nào ghi**:

1. **Lost update:** READ_COMMITTED, cả hai đọc amount=100 rồi UPDATE hằng số 110, kết quả sai = 110.
2. **Atomic SQL increment:** READ_COMMITTED, cả hai thực thi UPDATE amount=amount+10, kết quả đúng = 120.
3. **Write skew:** REPEATABLE_READ, cả hai đọc count=2 rồi tắt trạng thái on_call của hai row riêng, cả hai commit, count cuối = 0.
4. **Serializable protection:** SERIALIZABLE, lịch tương tự, một transaction được commit, một bị serialization_failure 40001, count cuối = 1.

Chương trình dùng **TransactionTemplate** thay cho @Transactional để tạo ranh giới transaction **rõ ràng trong từng worker thread** và đặt isolation trực tiếp; nó vẫn dùng **Spring PlatformTransactionManager và JdbcTransactionManager**, không phải tự commit qua JDBC. Sau demo ta sẽ ánh xạ lại về @Transactional ở tầng service.

### 7.1. Chạy PostgreSQL phục vụ bài học

Máy cần **JDK 17+**, Maven và Docker. Tạo PostgreSQL local để thử nghiệm, không dùng lệnh này làm cấu hình production:

~~~bash
docker run -d --rm --name spring-iso-pg \
  -e POSTGRES_USER=demo \
  -e POSTGRES_PASSWORD=demo \
  -e POSTGRES_DB=demo \
  -p 127.0.0.1:55432:5432 \
  postgres:16
~~~

Chạy:

~~~bash
docker exec spring-iso-pg pg_isready -U demo -d demo
~~~

Chỉ chạy chương trình khi server báo **accepting connections**. Nếu port 55432 đã được chiếm, chọn port local khác rồi đổi JDBC URL trong code. Không dùng credential ví dụ cho hệ thống thật.

### 7.2. Cấu trúc project và Maven

~~~text
isolation-anomalies/
├── pom.xml
└── src/main/java/demo/IsolationAnomalies.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>isolation-anomalies</artifactId>
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
                    <mainClass>demo.IsolationAnomalies</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Version ở đây dùng để tái lập môi trường demo, không phải khẳng định mới nhất. Trong ứng dụng Spring Boot, dùng dependency management/BOM phù hợp với phiên bản Boot đang triển khai.

### 7.3. Java file đầy đủ

**src/main/java/demo/IsolationAnomalies.java**:

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

public final class IsolationAnomalies {
    private IsolationAnomalies() {}

    private static TransactionTemplate template(
            PlatformTransactionManager manager, int isolationLevel) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
        tx.setIsolationLevel(isolationLevel);
        tx.setTimeout(20);
        return tx;
    }

    private static void synchronize(CyclicBarrier barrier) {
        try {
            barrier.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Worker interrupted", ex);
        } catch (BrokenBarrierException | TimeoutException ex) {
            throw new IllegalStateException("Concurrency barrier failed", ex);
        }
    }

    private static List<String> simultaneously(
            Callable<String> first, Callable<String> second)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = pool.submit(first);
            Future<String> b = pool.submit(second);
            return List.of(
                    a.get(30, TimeUnit.SECONDS),
                    b.get(30, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
        }
    }

    private static long committed(List<String> result) {
        return result.stream().filter("COMMIT"::equals).count();
    }

    private static long serializationFailures(List<String> result) {
        return result.stream().filter("40001"::equals).count();
    }

    private static boolean containsSqlState(Throwable throwable, String state) {
        for (Throwable cause = throwable; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql
                    && state.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    private static int counter(JdbcTemplate jdbc) {
        Integer number = jdbc.queryForObject(
                "SELECT amount FROM counter WHERE id = 1", Integer.class);
        return number.intValue();
    }

    private static int onCall(JdbcTemplate jdbc) {
        Integer number = jdbc.queryForObject(
                "SELECT COUNT(*) FROM doctors WHERE on_call = TRUE",
                Integer.class);
        return number.intValue();
    }

    private static String lostUpdate(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc, CyclicBarrier barrier) {
        TransactionTemplate tx = template(
                manager, TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.executeWithoutResult(status -> {
            int oldValue = counter(jdbc);
            synchronize(barrier); // Cả hai worker cùng đọc oldValue=100.
            jdbc.update("UPDATE counter SET amount = ? WHERE id = 1",
                    oldValue + 10);
        });
        return "COMMIT";
    }

    private static String atomicIncrement(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc, CyclicBarrier barrier) {
        TransactionTemplate tx = template(
                manager, TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.executeWithoutResult(status -> {
            synchronize(barrier);
            jdbc.update("UPDATE counter " +
                    "SET amount = amount + 10 WHERE id = 1");
        });
        return "COMMIT";
    }

    private static String doctorLeaves(
            PlatformTransactionManager manager, JdbcTemplate jdbc,
            CyclicBarrier barrier, int doctorId, int isolationLevel) {
        TransactionTemplate tx = template(manager, isolationLevel);
        try {
            tx.executeWithoutResult(status -> {
                int currentlyOnCall = onCall(jdbc);
                synchronize(barrier); // Cả hai SELECT hoàn tất trước UPDATE.
                if (currentlyOnCall >= 2) {
                    jdbc.update(
                            "UPDATE doctors SET on_call = FALSE WHERE id = ?",
                            doctorId);
                }
            });
            return "COMMIT";
        } catch (RuntimeException ex) {
            if (containsSqlState(ex, "40001")) {
                return "40001";  // PostgreSQL serialization_failure
            }
            throw ex; // Không nuốt lỗi khác.
        }
    }

    private static void resetCounter(JdbcTemplate jdbc) {
        jdbc.update("UPDATE counter SET amount = 100 WHERE id = 1");
    }

    private static void resetDoctors(JdbcTemplate jdbc) {
        jdbc.update("UPDATE doctors SET on_call = TRUE");
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            // Các phép chuẩn bị hoàn tất trước khi chạy hai worker.
            jdbc.execute("DROP TABLE IF EXISTS doctors");
            jdbc.execute("DROP TABLE IF EXISTS counter");
            jdbc.execute("CREATE TABLE counter (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.execute("CREATE TABLE doctors (" +
                    "id INT PRIMARY KEY, on_call BOOLEAN NOT NULL)");
            jdbc.update(
                    "INSERT INTO counter(id, amount) VALUES (1, 100)");
            jdbc.update(
                    "INSERT INTO doctors(id, on_call) VALUES (1, TRUE)");
            jdbc.update(
                    "INSERT INTO doctors(id, on_call) VALUES (2, TRUE)");

            CyclicBarrier b1 = new CyclicBarrier(2);
            List<String> lost = simultaneously(
                    () -> lostUpdate(manager, jdbc, b1),
                    () -> lostUpdate(manager, jdbc, b1));
            System.out.printf(
                    "lost update READ_COMMITTED: committed=%d, amount=%d%n",
                    committed(lost), counter(jdbc));

            resetCounter(jdbc);
            CyclicBarrier b2 = new CyclicBarrier(2);
            List<String> atomic = simultaneously(
                    () -> atomicIncrement(manager, jdbc, b2),
                    () -> atomicIncrement(manager, jdbc, b2));
            System.out.printf(
                    "atomic SQL READ_COMMITTED: committed=%d, amount=%d%n",
                    committed(atomic), counter(jdbc));

            resetDoctors(jdbc);
            CyclicBarrier b3 = new CyclicBarrier(2);
            List<String> repeatable = simultaneously(
                    () -> doctorLeaves(manager, jdbc, b3, 1,
                            TransactionDefinition.ISOLATION_REPEATABLE_READ),
                    () -> doctorLeaves(manager, jdbc, b3, 2,
                            TransactionDefinition.ISOLATION_REPEATABLE_READ));
            System.out.printf(
                    "write skew REPEATABLE_READ: committed=%d, " +
                    "serializationFailures=%d, onCall=%d%n",
                    committed(repeatable),
                    serializationFailures(repeatable), onCall(jdbc));

            resetDoctors(jdbc);
            CyclicBarrier b4 = new CyclicBarrier(2);
            List<String> serializable = simultaneously(
                    () -> doctorLeaves(manager, jdbc, b4, 1,
                            TransactionDefinition.ISOLATION_SERIALIZABLE),
                    () -> doctorLeaves(manager, jdbc, b4, 2,
                            TransactionDefinition.ISOLATION_SERIALIZABLE));
            System.out.printf(
                    "write skew SERIALIZABLE: committed=%d, " +
                    "serializationFailures=%d, onCall=%d%n",
                    committed(serializable),
                    serializationFailures(serializable), onCall(jdbc));
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
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }
    }
}
~~~

### 7.4. Lệnh chạy và stdout dự kiến

Từ thư mục **isolation-anomalies**:

~~~bash
mvn -q compile exec:java
~~~

Khi database đã sẵn sàng và không có traffic ngoài demo, **stdout kết quả** của bốn thử nghiệm theo PostgreSQL 16 có dạng:

~~~text
lost update READ_COMMITTED: committed=2, amount=110
atomic SQL READ_COMMITTED: committed=2, amount=120
write skew REPEATABLE_READ: committed=2, serializationFailures=0, onCall=0
write skew SERIALIZABLE: committed=1, serializationFailures=1, onCall=1
~~~

Chương trình không in tên worker nào thắng vì lịch chạy song song không quyết định T1 hay T2 sẽ commit trong ca SERIALIZABLE. Giá trị **committed=1** và **serializationFailures=1** là điều cần quan sát, không phải danh tính bác sĩ nào còn trực. Với môi trường có tùy chỉnh database hoặc sự cố kết nối, chương trình có thể dừng với lỗi thay vì in kết quả trên; đó là lỗi cần phân tích, không nên diễn giải như một kết quả thành công.

Dừng container khi xong:

~~~bash
docker stop spring-iso-pg
~~~

Nếu đang ở Windows PowerShell, lệnh docker run có dấu gạch chéo nối dòng kiểu Bash không được PowerShell hiểu giống nhau; hãy đặt lệnh docker run trên một dòng hoặc dùng cú pháp xuống dòng của PowerShell. Đây là lệnh ví dụ Bash, không phải yêu cầu người học dùng shell cụ thể.

### 7.5. Vì sao ví dụ có khả năng tái lập?

- **Hai physical transactions** nằm trên hai worker threads, mỗi transaction được TransactionTemplate mở tại thread của nó.
- **DriverManagerDataSource** mở connection khi được hỏi; vì hai transactions tồn tại đồng thời, chúng không sử dụng một JDBC Connection chung. Ứng dụng production nên dùng pool được cấu hình đúng.
- **CyclicBarrier** sau SELECT buộc cả hai request nhìn thấy trạng thái ban đầu trước khi bất kỳ UPDATE nào xảy ra. Không dựa vào Thread.sleep() hoặc may rủi scheduler.
- **READ_COMMITTED + UPDATE amount=?** giữ nguyên hằng số đã tính từ snapshot cũ; hai commits dẫn đến lost update.
- **READ_COMMITTED + UPDATE amount=amount+10** để DBMS áp dụng phép cộng atomic; row lock bảo vệ khỏi ghi đè hằng số cũ.
- **REPEATABLE_READ** tạo snapshot transaction cho cả hai doctors; do hai writes khác row, write skew vẫn có thể commit.
- **SERIALIZABLE** nhận diện nguy cơ không thể tuần tự hóa. Một transaction có thể báo SQLSTATE **40001**, bị rollback; transaction còn lại commit.
- **Query sau run** được thực hiện ngoài transaction của hai worker, nên thấy trạng thái đã commit mà không đọc snapshot cũ của một worker.

**Lưu ý về timeout:** CyclicBarrier đặt chờ tối đa 15 giây, transaction timeout 20 giây, Future.get tối đa 30 giây. Các mốc này là **giới hạn an toàn cho demo**, không phải bảo đảm thời gian chạy dưới tải mọi máy. Nếu máy rất chậm, timeout là tín hiệu cần xem môi trường thay vì tự thay đổi logic isolation. Không đưa barrier chờ nhau vào code production khi đang giữ DB transaction.

## 8. Dùng @Transactional thay cho TransactionTemplate trong ứng dụng thật

Ví dụ chương trình trên dùng TransactionTemplate để rõ hai thread và cấu hình isolation; trong ứng dụng thông thường, policy được đặt ở application service:

~~~java
// Snippet: cần @Service, imports, Spring AOP transaction infrastructure.
@Service
public class DutyService {
    private final JdbcTemplate jdbc;

    public DutyService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
            transactionManager = "transactionManager",
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE)
    public void leaveDuty(int doctorId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM doctors WHERE on_call = TRUE",
                Integer.class);
        if (count == null || count < 2) {
            throw new IllegalStateException(
                    "Must keep at least one doctor on call");
        }
        jdbc.update(
                "UPDATE doctors SET on_call = FALSE WHERE id = ?",
                doctorId);
    }
}
~~~

**Không phải chương trình độc lập**: cần Java class file, imports, các bean và bảng doctors. Nhưng nó diễn đạt đúng ranh giới: **đọc invariant + ra quyết định + cập nhật** nằm trong cùng service transaction với mức isolation phù hợp.

Trong Spring proxy mode, method phải được gọi từ ngoài **qua Spring-managed proxy**. Gọi this.leaveDuty(...) trong cùng object hoặc khởi tạo DutyService bằng new có thể bỏ qua TransactionInterceptor; mức isolation sẽ không được áp dụng như mong muốn.

### 8.1. Vì sao đặt isolation ở service, không chỉ DAO?

Một transaction với Propagation.REQUIRED có thể chứa nhiều DAO methods. Nếu outer service đã mở READ_COMMITTED, một DAO con ghi:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void updateDoctor(...) {
    // ...
}
~~~

thường **không nâng cấp** transaction ngoài đang chạy. Với REQUIRED, inner scope tham gia physical transaction cũ và Spring mặc định có thể bỏ qua isolation inner khi tham gia. Đặt **SERIALIZABLE ở outer boundary tạo transaction mới**, hoặc dùng TransactionTemplate tại nơi mở transaction. Có thể bật validateExistingTransaction để phát hiện mismatch khi phù hợp.

### 8.2. Khi dùng Spring Data JPA

Một service @Transactional(isolation=Isolation.SERIALIZABLE) sử dụng đúng JpaTransactionManager và datasource/provider tương ứng vẫn có thể bảo vệ invariant nếu DBMS áp dụng đúng isolation và các thao tác được thực hiện trong một transaction. Nhưng:

- EntityManager persistence context có cache trạng thái entity; đọc trong cùng context không thay thế đọc commit độc lập.
- **save()/flush() không đồng nghĩa COMMIT**; lỗi serialization có thể phát sinh ở statement hoặc thời điểm commit.
- @Version trên **từng bác sĩ** không tự ngăn write skew khi mỗi transaction cập nhật bác sĩ khác nhau.
- Với bulk SQL/JPQL, optimistic version có thể yêu cầu cấu hình và xử lý riêng; không suy diễn mọi update đều increment version.
- Cần test behavior trên **database production** (không chỉ H2 in-memory).

## 9. Khắc phục write skew không chỉ có SERIALIZABLE

### 9.1. Pessimistic locking các row liên quan

Một chiến lược ở READ_COMMITTED là trước khi COUNT và UPDATE, **khóa toàn bộ các row có thể cùng tham gia invariant** trong thứ tự thống nhất.

~~~sql
BEGIN;
SELECT id, on_call
FROM doctors
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- Nếu count >= 2, mới UPDATE bản ghi của người đang xin nghỉ.
UPDATE doctors SET on_call = FALSE WHERE id = 1;

COMMIT;
~~~

Khi mọi transaction cạnh tranh **đều** tuân thủ protocol khóa hai row trước khi kiểm tra, một transaction phải chờ transaction kia; transaction đến sau thấy dữ liệu đã commit mới ở READ_COMMITTED rồi **kiểm tra lại** invariant. Lưu ý một SELECT ... FOR UPDATE khác trong PostgreSQL không thể ghép trực tiếp vào SELECT COUNT(*) aggregate theo cách dùng FOR UPDATE cho chính aggregate; cần khóa row trước, rồi mới COUNT ở statement riêng.

**Điều kiện quan trọng:**

- Không đọc COUNT rồi mới lấy lock và dùng quyết định cũ; phải **đọc lại predicate sau khi khóa**.
- Với tập bác sĩ động, một truy vấn khóa “những row đang tồn tại” không nhất thiết chặn **phantom insert/delete** hoặc mọi đường ghi làm thay đổi tập. Có thể cần khóa **một row đội/ca đại diện (guard row)** mà mọi request phải cùng khóa, hoặc dùng SERIALIZABLE.
- Thứ tự khóa nhất quán giúp giảm deadlock nhưng không loại hết rủi ro. Có thể cần retry khi deadlock 40P01.

### 9.2. Shared guard row cho bất biến liên bản ghi

Ví dụ bổ sung bảng duty_team(team_id, active_count, version). Mọi yêu cầu một bác sĩ rời ca trong cùng đội đều phải:

1. Mở transaction.
2. Lock row duty_team tương ứng hoặc cập nhật **active_count** có điều kiện.
3. Chỉ khi vẫn active_count >= 2, cập nhật cả duty_team và doctors trong **cùng transaction**.
4. Commit cả hai cùng lúc; nếu có lỗi thì rollback cả hai.

Cách làm này buộc các giao dịch gây xung đột trên **cùng một guard row**, để database có điểm phối hợp rõ ràng. Có thể đặt CHECK(active_count >= 1) nếu counter được duy trì chính xác bởi mọi đường ghi/trigger. Nhưng nếu một writer bỏ qua protocol, counter có thể lệch với bảng doctors; cần quản lý mọi lối ghi ở application/DB và integration test.

Ví dụ SQL có điều kiện:

~~~sql
UPDATE duty_team
SET active_count = active_count - 1
WHERE team_id = 7
  AND active_count >= 2;
~~~

Nếu updateCount=1, transaction mới được phép cập nhật doctor tương ứng; nếu 0, từ chối rời ca. Hai UPDATE cùng transaction; rollback cùng nhau khi lỗi. Với mỗi team, các writer tranh chấp guard row thay vì chỉ những row doctor khác nhau.

### 9.3. Dùng unique/exclusion constraint khi invariant cho phép

Một bất biến như “một slot không được có hai booking ACTIVE trùng nhau” có thể được biểu diễn bằng UNIQUE index hoặc EXCLUDE constraint. Constraint cấp DB thường mạnh hơn việc SELECT kiểm tra tồn tại rồi INSERT với READ_COMMITTED. Tuy nhiên:

- UNIQUE có thể ngăn **quá một** bản ghi thỏa điều kiện, không tự diễn đạt **ít nhất một** bác sĩ trực.
- CHECK thông thường trên row không thể tự đảm bảo COUNT(*) >= 1 xuyên cả bảng.
- Constraint trigger có thể cần lock/serializable để không tự bị race giữa hai transaction.
- Phải xử lý database constraint violations như một outcome hợp lệ của concurrency, không âm thầm bắt lỗi rồi return success.

### 9.4. SERIALIZABLE + retry toàn transaction

PostgreSQL khuyến nghị ứng dụng retry **toàn bộ transaction** khi SQLSTATE **40001** (serialization_failure). Điều này bao gồm đọc trạng thái, quyết định nghiệp vụ, chọn SQL và thao tác ghi. Không chỉ retry câu UPDATE đã thất bại bằng dữ liệu cũ.

~~~text
ĐÚNG:
  attempt 1:
    BEGIN SERIALIZABLE
    SELECT COUNT(on_call) -> 2
    UPDATE doctor 1 -> serialization failure
    ROLLBACK

  attempt 2:
    BEGIN SERIALIZABLE mới
    SELECT COUNT(on_call) -> 1
    Từ chối rời ca (không UPDATE)
    transaction kết thúc theo policy

SAI:
  sau 40001 chỉ chạy lại UPDATE doctor 1
  mà không đọc lại COUNT/on_call.
~~~

Sau khi transaction đã bị PostgreSQL abort, không tiếp tục các SQL trong cùng transaction bị lỗi. Phải thoát boundary, để Spring rollback/cleanup, rồi bắt đầu một **transaction mới**. Khi dùng @Transactional, bố trí retry ở **caller bên ngoài proxy transaction** hoặc dùng một cơ chế retry bảo đảm mỗi attempt mở transaction mới; chú ý thứ tự AOP advisor nếu kết hợp @Retryable và @Transactional.

### 9.5. Retry bounded, idempotency và side effects

Một ứng dụng production nên:

- Giới hạn số lần retry; dùng backoff/jitter hợp lý dưới contention.
- Retry SQLSTATE 40001 ở phạm vi toàn use case; có thể cân nhắc 40P01 deadlock theo policy. Không retry vô điều kiện mọi 23505 unique violation vì có lỗi dữ liệu cố hữu.
- Không gửi email, HTTP request hoặc message bên trong transaction có thể retry nếu side effect không idempotent; mỗi retry có thể **gửi nhiều lần**.
- Với publish event, cân nhắc **transactional outbox** trong cùng DB rồi worker gửi sau commit.
- Dùng idempotency key ở ranh giới request nếu client cũng có thể retry.
- Ghi metric số serialization failures, deadlocks, số lần retry và thời gian transaction để phát hiện contention/chi phí.

Một skeleton ngoài transaction:

~~~java
// Snippet: caller KHÔNG nằm trong transaction đang mở.
// dutyService là Spring bean/proxy có @Transactional(SERIALIZABLE).
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        dutyService.leaveDuty(doctorId);
        break;
    } catch (org.springframework.dao.ConcurrencyFailureException ex) {
        if (attempt == 3) {
            throw ex;
        }
        // Trong production: chỉ retry những lỗi được phân loại là transient,
        // đặc biệt SQLSTATE 40001, và backoff có giới hạn.
    }
}
~~~

Đoạn trên là **minh họa cấu trúc retry**, không phải Java file độc lập. ConcurrencyFailureException có thể bao nhiều lỗi hơn 40001, nên production phải phân loại cause/SQLSTATE trước khi retry. Với một tác vụ bắt buộc, không return success khi đã hết attempts.

## 10. Tại sao write skew khó bắt bằng unit test thông thường?

Một unit test gọi service tuần tự:

~~~text
Gọi bác sĩ An nghỉ:
  COUNT=2, UPDATE An=false, COMMIT

Gọi bác sĩ Bình nghỉ:
  COUNT=1, từ chối, không UPDATE

=> invariant đúng.
~~~

Cách test này chỉ chứng minh **lịch tuần tự** đúng. Write skew chỉ xuất hiện khi hai request **cùng thấy count=2 trước khi ghi**. Vì thế cần test tạo **concurrent transactions thật**, dùng barrier/latch để ép interleaving, rồi đọc trạng thái sau commit.

Một integration test tốt cần có:

1. Khởi tạo database bằng transaction đã hoàn tất.
2. Tạo **hai connection/transactions độc lập**, không đặt cả hai worker trong cùng transaction test.
3. Cấu hình đúng isolation trên transaction mới và verify database thực tế.
4. Dùng barrier ở điểm sau READ/trước WRITE để mô phỏng race.
5. Kiểm tra số transaction commit, số serialization failures, và **trạng thái cuối**.
6. Thử với READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE theo DBMS đang dùng.
7. Kiểm tra trường hợp retry đầy đủ và việc business validation từ chối thao tác đã không còn hợp lệ.
8. Kiểm tra side effects ngoài DB không bị gửi trùng khi có retry.

**Nếu test class có @Transactional**, Spring TestContext có thể mở transaction cho test rồi rollback cuối test; đọc dữ liệu từ cùng transaction không chứng minh các worker đã commit. Tách transaction boundary và query bằng connection độc lập. Testcontainers hoặc một PostgreSQL container riêng thường cho kết quả gần production hơn H2.

## 11. Phân tích trực tiếp theo Spring configuration

### 11.1. @Transactional không tự kiểm tra invariant

Annotation chỉ giao nhiệm vụ mở/kết thúc transaction và cấu hình isolation cho manager. Nó không tự biết rằng “phải còn một bác sĩ trực”. Code SQL/business logic phải **thực sự đọc và bảo vệ invariant** dưới isolation/locking phù hợp.

Một method @Transactional với READ_COMMITTED và hai câu SELECT/UPDATE vẫn có thể write skew. Ngược lại, một statement SQL atomic có thể giải quyết counter lost update hiệu quả mà không cần nâng toàn application lên Serializable.

### 11.2. Isolation trong Spring là yêu cầu tới database

Khi JDBC transaction mới bắt đầu, Spring transaction manager cố gắng cấu hình Connection isolation tương ứng với TransactionDefinition. DB driver/DBMS quyết định behavior cụ thể. Nếu database không hỗ trợ isolation được yêu cầu, có thể báo lỗi hoặc áp dụng policy riêng; đừng coi enum Java là bằng chứng tuyệt đối.

**ISOLATION_DEFAULT** dùng default của datasource/database. Ở PostgreSQL, mặc định thường READ COMMITTED. Hãy kiểm tra session/database configuration, ví dụ:

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
~~~

Phải chạy trong session/transaction phù hợp để đọc giá trị thực tế. Với pool, cấu hình Connection isolation riêng có thể khác database default.

### 11.3. Propagation.REQUIRES_NEW không thay SERIALIZABLE

REQUIRES_NEW giúp inner có physical transaction độc lập và commit riêng. Nó **không tự đảm bảo** rằng hai REQUIRES_NEW transactions đồng thời cùng kiểm tra một predicate sẽ bảo vệ invariant. Hai giao dịch độc lập ở READ_COMMITTED hoặc REPEATABLE_READ vẫn có thể write skew. Propagation trả lời câu hỏi “transaction nào?”, isolation/locking trả lời “chạy đồng thời thế nào?”.

### 11.4. READ_ONLY không ngăn concurrency anomaly

@Transactional(readOnly=true) là thông tin/hint cho resource manager và ORM/driver; không thể dùng nó như quyền truy cập DB hay bảo vệ invariant. Nếu một method chỉ đọc count với readOnly=true rồi một method khác ghi ở transaction riêng, khoảng cách giữa hai transaction càng khiến quyết định dễ cũ. Đặt **READ và WRITE phụ thuộc cùng một quyết định** vào cùng boundary.

### 11.5. Multiple DataSources

Nếu quyết định invariant đọc từ DB A nhưng update DB B, một local JdbcTransactionManager của A không tự điều phối B. Các màn hình cache/read replicas còn có thể đọc dữ liệu trễ hơn primary. Với invariant cần ACID, kiểm tra **nguồn đọc nào**, **nguồn ghi nào**, **manager nào**, và liệu tất cả nằm trong một transaction thực sự hay cần thiết kế consistency khác.

## 12. Những lỗi tư duy phổ biến

| Ngộ nhận | Tại sao sai | Cách sửa |
| --- | --- | --- |
| Có @Transactional là không thể mất cập nhật | Transaction commit được nhưng quyết định dựa trên oldValue | Atomic SQL, version check, khóa hoặc SERIALIZABLE phù hợp |
| REPEATABLE_READ luôn bảo vệ mọi invariant | PostgreSQL snapshot isolation vẫn cho phép write skew | SERIALIZABLE/lock shared guard, test trên DBMS |
| Hai UPDATE khác row nên không có vấn đề concurrency | Cả hai có thể đọc cùng predicate và phá invariant | Bảo vệ tập row/predicate, không chỉ row ghi |
| @Version trên từng row ngăn mọi write skew | Hai transaction sửa hai row khác nhau nên version không conflict | Shared guard row/version hoặc SERIALIZABLE |
| SELECT FOR UPDATE sau COUNT là đủ | Quyết định đã dựa vào count cũ; có thể vẫn sai | Khóa trước và kiểm tra lại trong transaction |
| SERIALIZABLE nghĩa là không bao giờ lỗi | PostgreSQL có thể trả 40001 để ngăn kết quả không tuần tự hóa | Retry toàn transaction với giới hạn |
| Retry lại UPDATE bằng cùng tham số cũ là đúng | Không tái đánh giá invariant đã thay đổi | Retry read–decide–write toàn bộ |
| CHECK trên doctor row đảm bảo còn một người trực | Bất biến liên nhiều row không phải CHECK row đơn giản | Shared guard/constraint phù hợp/serializable |
| Isolation đặt ở DAO con luôn có hiệu lực | REQUIRED inner có thể tham gia outer với isolation khác | Đặt isolation tại outer boundary tạo physical transaction |
| H2 unit test pass là PostgreSQL production an toàn | MVCC/locking/SSI giữa engines khác nhau | Integration test với DBMS thực tế |
| Đọc lại từ EntityManager cũ cho biết commit cuối | Persistence context có thể cache state | Đọc từ transaction/context độc lập sau commit |

## 13. Bộ câu hỏi áp dụng và đáp án

**1. Vì sao hai transaction READ_COMMITTED mỗi cái tăng 10 mà amount cuối chỉ là 110?**  
Vì code đọc 100 rồi tính giá trị tuyệt đối 110 trên hai request, cuối cùng cả hai UPDATE giá trị 110. Thao tác nào đến sau không cộng thêm chênh lệch mà ghi đè giá trị đã commit.

**2. Thay UPDATE amount=? bằng UPDATE amount=amount+10 có ích gì?**  
Database thực hiện phép cộng dựa trên row version được bảo vệ bởi write locking; hai increment cùng row ở PostgreSQL READ_COMMITTED có thể tạo giá trị 120. Nhưng đây không phải thuốc chữa invariant liên nhiều row.

**3. Write skew có nhất thiết cập nhật cùng row không?**  
Không. Điểm thường gặp chính là hai transaction **cập nhật các row khác nhau** sau khi đọc một predicate chung.

**4. Vì sao PostgreSQL REPEATABLE_READ có thể cho cả hai bác sĩ nghỉ?**  
Cả hai transaction đọc snapshot có hai bác sĩ trực, rồi mỗi transaction ghi một row khác nhau. Snapshot isolation không nhất thiết phát hiện cycle predicate dependency này.

**5. Ở PostgreSQL SERIALIZABLE có chuyện gì khi cả hai cùng xin nghỉ?**  
Để đảm bảo kết quả tương đương chạy tuần tự, PostgreSQL SSI có thể hủy một transaction bằng 40001; transaction còn lại commit. Khi retry, request bị hủy đọc count mới và phải tuân theo business rule.

**6. Có thể chỉ retry câu UPDATE sau lỗi 40001 không?**  
Không. Phải mở transaction mới và lặp lại cả bước đọc/ra quyết định/ghi vì dữ liệu đầu vào cho quyết định đã thay đổi.

**7. @Version trên entity An và Bình có tự ngăn write skew không?**  
Không nếu mỗi transaction chỉ cập nhật một entity khác nhau. Hai optimistic version checks có thể cùng đúng; phải có điểm phối hợp chung hoặc SERIALIZABLE.

**8. Một DAO có @Transactional(isolation=SERIALIZABLE) nhưng outer service đã ở READ_COMMITTED REQUIRED. DAO có nâng isolation không?**  
Không nên kỳ vọng. Inner REQUIRED thường dùng physical transaction ngoài; chọn isolation ở service boundary hoặc validate mismatch.

**9. Khi dùng SELECT FOR UPDATE cho nhóm bác sĩ, đọc COUNT trước hay sau khi khóa?**  
Sau khi khóa các row liên quan trong cùng transaction, để quyết định dựa trên trạng thái không bị thay đổi đồng thời bởi writer tuân thủ cùng locking protocol.

**10. Nếu bác sĩ mới có thể được INSERT/DELETE tùy ý, khóa các row hiện có đã giải quyết mọi phantom chưa?**  
Không mặc nhiên. Tập row có thể thay đổi; cần shared guard, khóa phù hợp với mọi lối ghi, hoặc SERIALIZABLE và retry.

**11. Transaction commit thành công có khẳng định invariant luôn đúng không?**  
Không. Isolation không đủ hoặc code không bảo vệ invariant có thể để lại lịch concurrent sai dù cả hai transactions atomic và commit.

**12. Khi nào nên chọn READ_COMMITTED + atomic SQL thay vì SERIALIZABLE?**  
Khi bài toán là một phép cập nhật row đơn giản được diễn đạt atomic ở DB và không có predicate liên row phức tạp, lựa chọn này có thể giảm xung đột/retry. Nhưng cần test chính business invariant thực tế.

## 14. Checklist production cho bất biến liên nhiều bản ghi

- [ ] Viết invariant bằng câu rõ nghĩa: ví dụ “mỗi ca có >=1 bác sĩ trực”.
- [ ] Liệt kê **mọi đường ghi** có thể thay đổi tập row liên quan, kể cả batch, admin SQL và worker.
- [ ] Phân biệt update một row và quyết định dựa trên **COUNT/EXISTS/SUM/JOIN** nhiều row.
- [ ] Kiểm tra isolation thật của transaction mới, không suy đoán từ annotation inner.
- [ ] Chọn một protocol có thể chứng minh: atomic SQL, lock chung, SERIALIZABLE hoặc schema constraint.
- [ ] Đảm bảo giao dịch bao cả **read–decide–write**, hạn chế remote call trong transaction.
- [ ] Bắt và phân loại SQLSTATE 40001; retry **toàn transaction** với giới hạn/backoff.
- [ ] Bảo vệ side effects ngoài DB khỏi việc lặp khi retry.
- [ ] Kiểm thử bằng **hai giao dịch đồng thời**, không chỉ unit test tuần tự.
- [ ] Kiểm thử trên **DBMS production** ở cùng engine/version/driver/isolation khi yêu cầu quan trọng.
- [ ] Quan sát metric concurrency conflicts, serialization failures, deadlocks, wait time, retry count.
- [ ] Kiểm tra kết quả invariant bằng query sau khi transactions đã kết thúc.

## 15. Tóm tắt

- **Lost update** thường bắt nguồn từ read–calculate–write trên cùng giá trị mà không kiểm soát concurrent update. Atomic SQL, optimistic version, row lock hoặc isolation mạnh có thể giải quyết tùy hoàn cảnh.
- **Write skew** xảy ra khi các transactions đọc một điều kiện **liên nhiều row** rồi ghi các row khác nhau. Bảo vệ row riêng lẻ chưa đủ; invariant chung cần shared lock/guard/constraint hay SERIALIZABLE.
- Trong **PostgreSQL**, REPEATABLE_READ là snapshot isolation và vẫn có thể write skew; SERIALIZABLE dùng SSI để ngăn lịch commit không tuần tự hóa bằng cách rollback một transaction với **40001**.
- **@Transactional** chỉ khai báo ranh giới và isolation; nó không tự hiểu business invariant. Đặt mức isolation ở **owner transaction boundary**, đảm bảo Spring proxy/manager/resource đúng.
- **Retry phải chạy lại nguyên transaction** và mọi quyết định; không dùng tham số cũ, không lặp side effects thiếu idempotency.
- **Chứng minh bằng concurrent integration test và trạng thái DB sau commit** thay vì dựa vào cảm giác “có transaction nên an toàn”.

## Tài liệu tham khảo

- [PostgreSQL — Transaction Isolation, MVCC và Serializable](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — Serialization Failure Handling (SQLSTATE 40001)](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html)
- [PostgreSQL — Data Consistency Checks at the Application Level](https://www.postgresql.org/docs/current/applevel-consistency.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — SELECT và FOR UPDATE](https://www.postgresql.org/docs/current/sql-select.html)
- [PostgreSQL — SET TRANSACTION và isolation levels](https://www.postgresql.org/docs/current/sql-set-transaction.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Transaction Propagation / REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
