# Tạo, khôi phục và giải phóng savepoint bằng `TransactionStatus` trong Spring

## Mục tiêu

**Savepoint** là một mốc đánh dấu bên trong **giao dịch vật lý đang mở**. Khi một nhóm thao tác thất bại, có thể đưa trạng thái database quay về mốc đó thay vì rollback toàn bộ transaction. Spring Framework cung cấp ba API qua `TransactionStatus` (kế thừa `SavepointManager`):

- `Object createSavepoint()` — tạo mốc.
- `void rollbackToSavepoint(Object savepoint)` — hoàn tác phần công việc sau mốc.
- `void releaseSavepoint(Object savepoint)` — giải phóng mốc không còn cần dùng.

Bài học này tập trung vào **tự quản lý savepoint bằng `TransactionStatus`**, trong bối cảnh `NESTED và savepoint` của Spring transaction management. Bài sẽ dùng Java 17, Spring JDBC và database hỗ trợ JDBC savepoint. Sau khi học, bạn có thể hiểu chính xác ba lệnh, biết lúc nào cần gọi mỗi lệnh, phân biệt savepoint với commit/rollback toàn giao dịch và với `@Transactional(propagation = NESTED)`, xử lý lỗi an toàn và tự kiểm chứng kết quả trên database.

## 1. Savepoint giải quyết bài toán nào?

Giả sử một transaction nhập lô dữ liệu gồm ba phần:

1. Ghi thông tin lô (bắt buộc).
2. Nhập nhóm dữ liệu tùy chọn (có thể bỏ qua nếu vi phạm ràng buộc).
3. Ghi tổng kết lô (bắt buộc).

Nếu nhóm dữ liệu tùy chọn lỗi, bạn muốn **chỉ hoàn tác phần tùy chọn** rồi cho transaction tiếp tục. Đó là trường hợp phù hợp để đặt một savepoint trước phần tùy chọn.

```text
BEGIN TRANSACTION T
   |
   +-- INSERT "batch-start"          (giữ lại)
   |
   +-- SAVEPOINT S
   |      |
   |      +-- INSERT "optional-1"    (sẽ bị hoàn tác)
   |      +-- INSERT "optional-2"    (sẽ bị hoàn tác)
   |      +-- phát hiện lỗi
   |      |
   |      +-- ROLLBACK TO S
   |      +-- RELEASE S
   |
   +-- INSERT "batch-end"            (giữ lại)
   |
COMMIT TRANSACTION T
```

Sau commit, chỉ `batch-start` và `batch-end` tồn tại. Transaction T **vẫn là một giao dịch vật lý duy nhất**; savepoint không tạo connection mới, không tự commit các INSERT trước nó và không làm phần công việc giữ lại trở thành độc lập với transaction ngoài.

Trường hợp T cuối cùng rollback toàn bộ, ngay cả hai INSERT `batch-start` và `batch-end` cũng mất. Đây là khác biệt căn bản với `REQUIRES_NEW`: một physical transaction con độc lập có thể commit dù outer rollback, còn savepoint **không thể commit độc lập**.

## 2. `TransactionStatus` và hợp đồng `SavepointManager`

`org.springframework.transaction.TransactionStatus` biểu diễn trạng thái một transaction đang được quản lý. Nó kế thừa `SavepointManager`, nên có sẵn ba thao tác savepoint. Tuy nhiên, **việc có method trên interface không bảo đảm manager/driver hiện tại hỗ trợ savepoint**.

| API | Ý nghĩa | Điều không xảy ra |
|---|---|---|
| `Object sp = status.createSavepoint()` | Tạo savepoint mới trong transaction hiện hành; trả một handle để dùng về sau | **Không** mở physical transaction riêng; **không** commit |
| `status.rollbackToSavepoint(sp)` | Đưa database về trạng thái tại mốc `sp`, bỏ các thay đổi SQL phù hợp sau mốc | **Không** rollback toàn transaction; **không** tự release mốc |
| `status.releaseSavepoint(sp)` | Bỏ mốc không cần dùng để tài nguyên/database được giải phóng phù hợp | **Không** commit dữ liệu; **không** giữ lại dữ liệu bất chấp outer rollback |

**Kiểu dữ liệu `Object`:** `createSavepoint()` trả một handle trừu tượng (với JDBC thường liên quan `java.sql.Savepoint`). Hãy **truyền lại nguyên handle** vào `rollbackToSavepoint` / `releaseSavepoint`. Không tự chế handle, không ép kiểu hoặc lưu handle để dùng ở transaction/connection khác.

**Savepoint có vòng đời ngắn:** chỉ có hiệu lực bên trong transaction và resource nơi nó được tạo. Sau `releaseSavepoint(sp)`, không còn quyền rollback về mốc này. Sau transaction completion, không nên dùng lại bất kỳ handle nào.

### 2.1. `createSavepoint()`

```java
Object savepoint = status.createSavepoint();
```

Lệnh yêu cầu transaction manager tạo một mốc mới trên transaction hiện tại. JDBC driver thường thực hiện bằng `Connection.setSavepoint()`. Khi DB/driver/transaction manager không hỗ trợ, Spring có thể ném `NestedTransactionNotSupportedException` hoặc `TransactionException`.

Điều kiện quan trọng: phải có **transaction thực sự đang hoạt động** và cơ chế hỗ trợ savepoint. Không gọi trên transaction đã commit/rollback, hoặc dựa vào sự tồn tại của interface để kết luận có savepoint.

### 2.2. `rollbackToSavepoint(sp)`

```java
status.rollbackToSavepoint(savepoint);
```

Lệnh đưa trạng thái cơ sở dữ liệu quay lại **thời điểm tạo savepoint**, không quay về thời điểm bắt đầu transaction. Những thay đổi sau mốc bị hoàn tác; các thay đổi trước mốc tiếp tục thuộc transaction hiện hành và vẫn có thể bị rollback nếu toàn bộ transaction thất bại.

Theo hợp đồng `SavepointManager`, **rollback về savepoint không tự release savepoint**. Nếu database/driver hỗ trợ, bạn có thể tiếp tục thao tác sau rollback; những hiệu ứng ngoài DB (email, HTTP call, file, message đã gửi) không được rollback bởi JDBC savepoint.

Khi có nhiều savepoint, rollback về mốc trước có thể làm các mốc tạo sau mốc đó không còn hiệu lực tùy semantics của DB/driver. Tránh sử dụng một handle thuộc nhánh đã bị rollback.

### 2.3. `releaseSavepoint(sp)`

```java
status.releaseSavepoint(savepoint);
```

Release giải phóng **mốc**, không phải “commit một transaction con”. Mọi dữ liệu trước/sau mốc vẫn đang thuộc physical transaction chính và có thể bị rollback khi transaction đó kết thúc.

Tài liệu Spring nói đa số transaction manager tự giải phóng savepoint khi transaction hoàn tất. Dù vậy, khi **tự tạo savepoint để xử lý từng đoạn**, việc release sau khi không còn dùng là rõ ràng và giúp giảm tài nguyên. Một số DB/driver có giới hạn hoặc semantics đặc thù đối với release; khi release thất bại, Spring có thể ném `TransactionException`, dù hợp đồng khuyến khích implementation xử lý cleanup mềm dẻo nếu tài nguyên cuối cùng được dọn khi transaction hoàn tất.

### 2.4. Hai sự nhầm lẫn đặc biệt quan trọng

- `status.setRollbackOnly()` là yêu cầu **rollback transaction**, không tương đương `rollbackToSavepoint(sp)`. Nó có thể khiến toàn bộ transaction không thể commit. **Không gọi `setRollbackOnly()` khi mục tiêu chỉ là bỏ một nhóm thao tác tùy chọn**.
- `status.hasSavepoint()` chủ yếu cho biết **bản thân TransactionStatus có giữ savepoint do một nested transaction tạo ra hay không**. Nó **không phải** phép kiểm chung rằng bạn đã gọi `createSavepoint()` thủ công, và giá trị `false` không chứng minh manager không hỗ trợ savepoint. Để dùng API thủ công, hãy giữ handle được trả về và xử lý exception nếu create thất bại.

## 3. Lấy `TransactionStatus` ở đâu?

Có hai cách điển hình.

### 3.1. Dùng `TransactionTemplate` — cách rõ ràng nhất cho savepoint thủ công

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.executeWithoutResult(status -> {
    // status là TransactionStatus của transaction do template quản lý.
    Object sp = status.createSavepoint();
    try {
        // Một nhóm thao tác database có thể rollback một phần.
        status.releaseSavepoint(sp);
    } catch (RuntimeException ex) {
        status.rollbackToSavepoint(sp);
        status.releaseSavepoint(sp);
        // Chỉ nuốt exception nếu đó là trường hợp nghiệp vụ cho phép.
    }
});
```

Đây là **mã mô tả mô hình**, chưa phải chương trình độc lập: cần `transactionManager`, datasource và SQL thật. `TransactionTemplate.executeWithoutResult` cung cấp `TransactionStatus` trực tiếp. Nếu transaction đã tồn tại theo propagation của template (mặc định `REQUIRED`), template có thể tham gia transaction đó; nếu chưa có, nó mở transaction mới.

Điểm mạnh: không cần phụ thuộc AOP proxy để *lấy* status. Tuy nhiên transaction manager và transaction resource vẫn phải cấu hình đúng; việc tạo savepoint chỉ được hỗ trợ khi underlying transaction/driver hỗ trợ.

### 3.2. Trong method được quản lý bằng `@Transactional`

```java
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public void importBatch() {
    TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();
    Object sp = status.createSavepoint();
    // SQL và rollbackToSavepoint()/releaseSavepoint() khi phù hợp.
}
```

Đây là **snippet thuộc class Spring service**, không phải file có thể biên dịch độc lập. `currentTransactionStatus()` yêu cầu lời gọi hiện tại đang do Spring Transaction AOP aspect/interceptor quản lý; nếu không có invocation context, nó ném `NoTransactionException`.

Đặc biệt, `this.importBatch()` từ một method khác trong cùng bean có thể **bỏ qua proxy**, khiến `@Transactional` không được kích hoạt. Việc một connection đã có actual transaction không đồng nghĩa `TransactionAspectSupport.currentTransactionStatus()` luôn sẵn ở mọi ngữ cảnh. Dùng bean Spring được gọi qua proxy hoặc chủ động dùng `TransactionTemplate`.

**Chú ý phạm vi status:** dùng đúng status của transaction mà bạn muốn tạo savepoint. Không lưu `TransactionStatus` vào field singleton, cache, thread khác hoặc truyền sang tác vụ async để dùng sau khi transaction hoàn tất.

## 4. Các điều kiện kỹ thuật cần đáp ứng

Với JDBC trong Spring Framework:

1. Dùng database và JDBC driver hỗ trợ savepoint, thường có thể kiểm tra qua `DatabaseMetaData.supportsSavepoints()`; kiểm tra này có giá trị tham khảo, vẫn cần thử với transaction thực.
2. Sử dụng transaction manager tương thích savepoint: `DataSourceTransactionManager` hoặc `JdbcTransactionManager` là lựa chọn chuẩn khi dùng một JDBC `DataSource`. Với các manager này, hỗ trợ `PROPAGATION_NESTED` mặc định được bật, **nhưng driver phải hỗ trợ JDBC savepoints**.
3. Dùng cùng `DataSource` cho `JdbcTemplate` và transaction manager. `JdbcTemplate` dùng `DataSourceUtils` để lấy connection đã gắn với transaction.
4. Có **physical transaction** đang mở, không phải code đang chạy ngoài transaction hoặc trên connection autocommit mà không có transaction manager phù hợp.
5. Chạy JDBC operations đồng bộ trong cùng transaction/thread; đừng chuyển một handle savepoint sang thread, connection hoặc transaction khác.
6. Với ORM/JPA, cache/persistence context có thể không được đưa về trạng thái cũ khi JDBC rollback về savepoint. Vì vậy không mặc định suy rộng ví dụ thuần JDBC sang JPA/Hibernate và các transaction manager JTA/reactive.

**Kiểu lỗi cần dự phòng:**

| Hoàn cảnh | Hậu quả |
|---|---|
| Database/driver không hỗ trợ savepoint | `NestedTransactionNotSupportedException` hoặc lỗi transaction phù hợp |
| Transaction không active/đã kết thúc | Tạo/rollback/release có thể thất bại vì trạng thái không hợp lệ |
| Dùng nhầm handle từ connection khác | SQLException/TransactionException hoặc undefined lifecycle theo driver |
| Release rồi mới rollback cùng mốc | Handle không còn hiệu lực |
| JDBC error làm transaction rơi vào trạng thái cần rollback | Cần rollback đến mốc hợp lệ trước khi tiếp tục; nếu rollback savepoint thất bại, nên kết thúc transaction bằng rollback toàn bộ |
| `setRollbackOnly()` đã được gọi | Không thể dùng release để “xóa” yêu cầu rollback toàn transaction |
| `@Transactional(REQUIRED)` của inner đánh dấu rollback-only | Catch ở outer không nhất thiết cho phép commit; có thể gặp `UnexpectedRollbackException` |

## 5. Chu trình đúng: tạo → thử thao tác → rollback hoặc release → hoàn tất transaction

Trường hợp thành công:

```text
BEGIN T
INSERT trước mốc
sp = createSavepoint()
INSERT phần tùy chọn
releaseSavepoint(sp)
INSERT sau mốc
COMMIT T
```

Trường hợp thất bại nhưng chấp nhận bỏ riêng phần tùy chọn:

```text
BEGIN T
INSERT trước mốc
sp = createSavepoint()
INSERT phần tùy chọn A
INSERT phần tùy chọn B -> lỗi được dự liệu
rollbackToSavepoint(sp)
releaseSavepoint(sp)        (nếu hỗ trợ; giải phóng mốc không còn cần)
INSERT sau mốc
COMMIT T
```

Trường hợp lỗi **không thể xử lý an toàn**:

```text
BEGIN T
sp = createSavepoint()
SQL -> lỗi nghiêm trọng / không rõ tình trạng connection
rollbackToSavepoint(sp) -> cũng thất bại
KHÔNG tiếp tục ghi như thể transaction sạch
NÉM LỖI RA NGOÀI transaction boundary
ROLLBACK T (nếu transaction manager còn thực hiện được)
```

Một mẫu quan trọng khi cần nuốt **chỉ lỗi đã dự liệu**:

```java
Object sp = status.createSavepoint();
try {
    importOptionalRecords();      // SQL trong cùng transaction
    status.releaseSavepoint(sp);   // Thành công: bỏ mốc
} catch (KnownRecoverableDatabaseException ex) {
    status.rollbackToSavepoint(sp);
    status.releaseSavepoint(sp);
    // Ghi nhận/báo cáo lỗi tùy chọn theo business policy.
}
```

Đây là **pseudocode Java trong một transaction**, vì `importOptionalRecords` và `KnownRecoverableDatabaseException` đại diện cho logic ứng dụng, chưa được khai báo. Trong production, chỉ catch đúng lỗi có thể phục hồi, không nuốt mọi `Exception`. Nếu tạo savepoint thành công nhưng lệnh bất kỳ ném exception không dự kiến, có thể để transaction manager rollback toàn transaction khi exception thoát ra; không buộc release trong mọi nhánh bởi lệnh release ở trạng thái connection lỗi có thể che mất nguyên nhân chính.

**Thứ tự phải được thiết kế cẩn thận:** nếu bạn gọi `releaseSavepoint(sp)` quá sớm, sau đó không thể rollback về mốc ấy. Nếu `rollbackToSavepoint(sp)` thành công, vẫn nên release mốc đã dùng xong theo khả năng của driver; hợp đồng Spring ghi rõ rollback **không** release tự động. Cũng không nên gọi `rollbackToSavepoint` hai lần trên cùng handle sau khi đã release.

## 6. Ví dụ Java 17 chạy được: kiểm chứng cả ba API trên H2

Để tránh nhầm lẫn với self-invocation của `@Transactional`, ví dụ dùng `TransactionTemplate`, nhận `TransactionStatus` trực tiếp và chạy trên H2 in-memory.

Các kịch bản:

1. Tạo savepoint, thêm một bản ghi tạm, **rollback về savepoint**, **release**, rồi ghi tiếp. Transaction vẫn commit các bản ghi trước/sau mốc.
2. Tạo savepoint, ghi dữ liệu hợp lệ, chỉ **release** mà không rollback; cuối transaction commit thì dữ liệu vẫn có.
3. Release savepoint rồi ném exception unchecked ra khỏi transaction callback: **cả transaction rollback**, chứng minh release không phải commit.
4. Tạo savepoint, thực hiện một INSERT hợp lệ rồi cố tình vi phạm primary key, bắt `DuplicateKeyException`, rollback về savepoint, release và tiếp tục với bản ghi khác.
5. Dùng **hai savepoint** để cho thấy rollback về mốc ngoài xóa các thay đổi kể từ mốc đó; không cố dùng lại mốc trong đã bị rollback/vô hiệu.

### 6.1. Cấu trúc dự án

```text
spring-savepoint-demo/
├── pom.xml
└── src/main/java/com/example/savepoint/Main.java
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-savepoint-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-jdbc` kéo theo Spring transaction infrastructure và hỗ trợ các helper JDBC; `h2` là database thử nghiệm. Ở đây không cần một Spring Boot application hoặc application context vì `TransactionTemplate` được cấu hình trực tiếp bằng transaction manager. Spring 6.2 cần Java 17+; phiên bản được cố định để dễ tái lập. Ứng dụng thật nên quản lý dependency và cập nhật security qua BOM/đợt phát hành được hỗ trợ.

### 6.3. `src/main/java/com/example/savepoint/Main.java`

```java
package com.example.savepoint;

import java.util.List;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {
    private static void add(JdbcTemplate jdbc, int id, String label) {
        jdbc.update(
            "INSERT INTO work_items(id, label) VALUES (?, ?)",
            id, label
        );
    }

    private static List<String> labels(JdbcTemplate jdbc) {
        return jdbc.queryForList(
            "SELECT label FROM work_items ORDER BY id",
            String.class
        );
    }

    private static void clear(JdbcTemplate jdbc) {
        jdbc.update("DELETE FROM work_items");
    }

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:savepoint_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
            "CREATE TABLE work_items (" +
            "id INT PRIMARY KEY, label VARCHAR(80) NOT NULL)"
        );

        var txManager = new JdbcTransactionManager(dataSource);
        var tx = new TransactionTemplate(txManager);

        // 1. Rollback một phần, sau đó release rồi vẫn ghi tiếp.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "before");
            Object sp = status.createSavepoint();
            add(jdbc, 2, "temporary");
            status.rollbackToSavepoint(sp);
            status.releaseSavepoint(sp);
            add(jdbc, 3, "after");
        });
        System.out.println("partial=" + labels(jdbc));
        clear(jdbc);

        // 2. Release không rollback, nên dữ liệu được giữ đến lúc commit.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "before");
            Object sp = status.createSavepoint();
            add(jdbc, 2, "kept");
            status.releaseSavepoint(sp);
            add(jdbc, 3, "after");
        });
        System.out.println("release=" + labels(jdbc));
        clear(jdbc);

        // 3. Dù đã release, outer ném exception thì mọi thay đổi rollback.
        try {
            tx.executeWithoutResult(status -> {
                add(jdbc, 1, "before");
                Object sp = status.createSavepoint();
                add(jdbc, 2, "not-committed");
                status.releaseSavepoint(sp);
                throw new IllegalStateException("rollback-all");
            });
        } catch (IllegalStateException ex) {
            System.out.println("full rollback=" + ex.getMessage());
        }
        System.out.println("after failure=" + labels(jdbc));
        clear(jdbc);

        // 4. SQL lỗi dự kiến: rollback về mốc rồi tiếp tục transaction.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "before");
            Object sp = status.createSavepoint();
            try {
                add(jdbc, 2, "discarded");
                add(jdbc, 1, "duplicate-key"); // id=1 đã tồn tại
            } catch (DuplicateKeyException ex) {
                status.rollbackToSavepoint(sp);
                System.out.println("constraint recovered=true");
            }
            status.releaseSavepoint(sp);
            add(jdbc, 3, "after");
        });
        System.out.println("constraint=" + labels(jdbc));
        clear(jdbc);

        // 5. Hai savepoint, rollback về mốc ngoài.
        tx.executeWithoutResult(status -> {
            add(jdbc, 1, "root");
            Object outerSp = status.createSavepoint();
            add(jdbc, 2, "first");
            Object innerSp = status.createSavepoint();
            add(jdbc, 3, "second");

            status.rollbackToSavepoint(innerSp);
            status.releaseSavepoint(innerSp);
            add(jdbc, 4, "third");

            status.rollbackToSavepoint(outerSp);
            status.releaseSavepoint(outerSp);
            add(jdbc, 5, "tail");
        });
        System.out.println("two savepoints=" + labels(jdbc));
    }
}
```

**Lưu ý cú pháp Java:**

- File tên `Main.java` nằm đúng package `com.example.savepoint`; lớp public tên `Main`.
- `TransactionTemplate.executeWithoutResult(status -> {...})` được hỗ trợ trong Spring 6.2; tham số callback là `TransactionStatus`.
- Các savepoint handle được giữ ở biến `Object` đúng với contract.
- Các lần `clear(jdbc)` thực hiện **sau khi** transaction của kịch bản trước hoàn tất, nhằm tách kết quả từng kịch bản.
- H2 với JDBC và `JdbcTransactionManager` hỗ trợ savepoint; `DriverManagerDataSource` chỉ thích hợp cho demo, không dùng thay connection pool trong production.

### 6.4. Lệnh chạy và kết quả

Trong thư mục `spring-savepoint-demo`, cài JDK 17+ và Maven rồi chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.savepoint.Main
```

Những dòng **do chương trình in ra**, không gồm thông báo tùy môi trường của Maven/SLF4J:

```text
partial=[before, after]
release=[before, kept, after]
full rollback=rollback-all
after failure=[]
constraint recovered=true
constraint=[before, after]
two savepoints=[root, tail]
```

**Phân tích theo trạng thái database:**

- `partial=[before, after]`: `temporary` được tạo sau savepoint rồi rollback; hai bản ghi còn lại nằm trong transaction chính và được commit.
- `release=[before, kept, after]`: khi không rollback, release chỉ bỏ mốc; ba INSERT đều được transaction chính commit.
- `after failure=[]`: release savepoint không giúp hai INSERT tránh rollback khi callback ném unchecked exception ra khỏi `TransactionTemplate`.
- `constraint=[before, after]`: INSERT `discarded` sau savepoint cũng bị rollback cùng với xử lý lỗi duplicate key; sau đó transaction tiếp tục ghi `after`. Với database như PostgreSQL, rollback về mốc hợp lệ còn đặc biệt hữu ích khi một câu SQL lỗi làm transaction cần trở lại trạng thái có thể tiếp tục.
- `two savepoints=[root, tail]`: rollback về `innerSp` loại `second`; sau đó rollback về `outerSp` loại cả `first` và `third`. `root` nằm trước hai mốc, `tail` được tạo sau rollback cuối nên còn.

**Giới hạn tái lập:** ví dụ kiểm chứng bằng hành vi chuẩn của Spring JDBC và H2; các API savepoint, việc release và cách xử lý lỗi SQL có thể khác ở DB khác. Hãy chạy integration test trên driver/database thật trước khi thiết kế hành vi phục hồi lỗi.

## 7. Cách quản lý lỗi và release an toàn

### 7.1. Không nuốt lỗi không biết chắc có thể phục hồi

Một lỗi duplicate key khi import *dữ liệu tùy chọn* có thể được xử lý bằng rollback về savepoint. Nhưng lỗi mất kết nối, transaction manager bị hỏng, lỗi schema migration hoặc lỗi do resource ngoài DB có thể khiến transaction không an toàn để tiếp tục. Trường hợp đó nên cho exception thoát khỏi callback để transaction manager rollback toàn bộ và thông báo lỗi đúng bản chất.

Không nên dùng `catch (Exception ignored)` quanh mọi SQL rồi cố commit. Một transaction còn `isActualTransactionActive() == true` không đồng nghĩa kết quả commit vẫn an toàn.

### 7.2. Không release trước khi quyết định rollback

Sai thứ tự:

```java
Object sp = status.createSavepoint();
doSomething();
status.releaseSavepoint(sp);
// Quá muộn: không thể rollback về handle đã release.
status.rollbackToSavepoint(sp);
```

Đây là **snippet sai chủ đích**, không dùng trong chương trình thật. Sau release, handle không còn mốc hợp lệ để rollback.

Đúng hơn:

```java
Object sp = status.createSavepoint();
try {
    doOptionalWork();
    status.releaseSavepoint(sp);
} catch (ExpectedRecoverableException ex) {
    status.rollbackToSavepoint(sp);
    status.releaseSavepoint(sp);
}
```

Snippet thứ hai cũng chỉ là minh họa với các method/type tượng trưng; production cần xử lý rõ nếu rollback hoặc release **tự nó ném lỗi**. Nếu rollback thất bại, đừng cố tiếp tục nghiệp vụ; thường nên ném lỗi ra ngoài để transaction manager xử lý rollback toàn bộ. Nếu release gặp lỗi do driver, cần tuân theo hợp đồng API và thực tế resource manager; không tự động bỏ qua mọi exception.

### 7.3. Không dùng `setRollbackOnly()` để rollback từng phần

```java
Object sp = status.createSavepoint();
performOptionalInserts();
status.setRollbackOnly(); // Đánh dấu CẢ transaction để rollback.
status.releaseSavepoint(sp);
```

Đây là **ví dụ sai về ý định**, không phải khuyến nghị. `setRollbackOnly()` không thay thế `rollbackToSavepoint(sp)`; release không xóa rollback-only. Hãy chọn rõ **partial rollback** hay **full rollback**.

### 7.4. Savepoint không làm những tác dụng phụ ngoài DB trở nên atomic

Ví dụ gửi email hoặc gọi REST API giữa `createSavepoint()` và `rollbackToSavepoint()`. Những hành động đó không được database rollback. Nếu cần gửi event chỉ khi transaction commit thành công, cân nhắc transactional outbox hoặc cơ chế after-commit thích hợp và hiểu giới hạn của chúng. Savepoint chỉ tác động đến những thao tác được resource/database hỗ trợ.

### 7.5. Khi `@Transactional` lồng nhau dễ tạo rollback-only ngoài ý muốn

Một service inner có `@Transactional(propagation = REQUIRED)` tham gia physical transaction ngoài và ném unchecked exception **qua transaction interceptor**. Interceptor inner có thể đánh dấu toàn transaction rollback-only trước khi outer bắt exception. Khi đó, việc outer có một savepoint riêng không tự động “xóa” rollback-only do interceptor đã đặt; cuối cùng có thể nhận `UnexpectedRollbackException`.

Muốn tự dùng `TransactionStatus.createSavepoint()` để bỏ phần tùy chọn, hãy thiết kế một transaction boundary rõ ràng và catch lỗi **trong phạm vi được quản lý trước khi nó thoát qua một interceptor REQUIRED khác**. Hoặc dùng `@Transactional(propagation = NESTED)` ở bean riêng, nếu JDBC transaction manager/driver hỗ trợ.

## 8. So sánh savepoint thủ công với `@Transactional(propagation = NESTED)`

| Tiêu chí | `TransactionStatus.createSavepoint()` thủ công | `Propagation.NESTED` qua proxy |
|---|---|---|
| Ai tạo mốc? | Business code chủ động gọi | Transaction manager khi bắt đầu logical nested scope có outer transaction |
| Ai rollback về mốc? | Business code gọi `rollbackToSavepoint` | Transaction manager khi nested scope quyết định rollback |
| Ai giải phóng mốc? | Business code gọi `releaseSavepoint` (hoặc cuối transaction dọn) | Infrastructure quản lý mốc của nested scope |
| Phạm vi | Tùy bạn đặt mốc trong một method/callback | Gắn với method boundary được intercept |
| Yêu cầu proxy | Không bắt buộc nếu dùng `TransactionTemplate` | Có trong Spring AOP proxy mode |
| Physical transaction | Vẫn là một transaction đang chạy | Vẫn một physical transaction khi NESTED tham gia outer |
| Cách rollback theo lỗi | Tự catch/rollback, tùy chính sách | Theo rollback rules của method và transaction manager |
| Hỗ trợ | Cần resource/manager hỗ trợ savepoint | Cần resource/manager hỗ trợ nested transaction/savepoint |
| Phù hợp | Một method có nhiều điểm quyết định rollback nhỏ | Nghiệp vụ inner độc lập về xử lý lỗi nhưng không commit vật lý riêng |

Ví dụ ngắn về cách declarative:

```java
@Service
class OptionalPartService {
    @Transactional(propagation = Propagation.NESTED)
    public void insertOptional() {
        // Truy cập JDBC qua JdbcTemplate trên cùng datasource.
        // Lỗi unchecked thoát khỏi method sẽ khiến Spring rollback
        // về savepoint do manager tạo cho logical nested scope.
    }
}

@Service
class BatchService {
    private final OptionalPartService optional;

    BatchService(OptionalPartService optional) {
        this.optional = optional;
    }

    @Transactional
    public void importBatch() {
        // Phần bắt buộc trong transaction ngoài.
        try {
            optional.insertOptional(); // Gọi QUA PROXY của bean khác.
        } catch (RuntimeException ex) {
            // Chỉ tiếp tục nếu loại lỗi này được phép bỏ qua.
        }
        // Phần bắt buộc khác trong cùng physical transaction.
    }
}
```

Đây là **hai class minh họa**, chưa là chương trình độc lập: cần imports, component scanning, cấu hình transaction manager và SQL thật. `Propagation.NESTED` phụ thuộc khả năng savepoint của transaction manager và database, và **không tạo transaction B độc lập**. `@Transactional(REQUIRES_NEW)` thì mở transaction vật lý riêng và có thể commit bất chấp outer rollback.

Khi dùng `NESTED` trên một call không có outer transaction, transaction manager thường tạo physical transaction mới như `REQUIRED`; không tự có savepoint con chỉ vì tên propagation. Nếu muốn bảo đảm có outer transaction, hãy kiểm tra kiến trúc lời gọi và chính sách truy cập.

## 9. Các sắc thái nâng cao cần biết

### 9.1. Hai savepoint có thứ tự và phạm vi hiệu lực

Một transaction có thể có nhiều savepoint:

```text
BEGIN
INSERT A
SP1 = createSavepoint()
INSERT B
SP2 = createSavepoint()
INSERT C
rollbackToSavepoint(SP2)     -- C mất
releaseSavepoint(SP2)
INSERT D
rollbackToSavepoint(SP1)     -- B và D mất
releaseSavepoint(SP1)
INSERT E
COMMIT                       -- A và E còn
```

Không nên tùy tiện rollback mốc cũ và sau đó dùng handle của một mốc tạo sau mốc cũ, vì database có thể đã vô hiệu hóa các mốc sau đó. Mỗi savepoint nên có nhánh sở hữu rõ ràng; cấu trúc quản lý theo LIFO giúp giảm lỗi, nhưng vẫn phải hiểu semantics DB.

### 9.2. `status.hasSavepoint()` không đo số savepoint thủ công

`hasSavepoint()` phản ánh **savepoint do chính transaction status giữ trong nested scope**, không cung cấp danh sách các handle bạn đã tạo bằng `createSavepoint()`. Nếu muốn biết savepoint thủ công có tồn tại, ứng dụng phải quản lý handle và vòng đời của nó. Không dùng `hasSavepoint() == false` để quyết định tự động tạo một savepoint nếu bạn có thể đã tạo trước đó.

### 9.3. Synchronization callbacks cho savepoint từ Spring 6.2

Trong Spring Framework 6.2+, `TransactionSynchronization` có thêm hai callback:

- `savepoint(Object savepoint)`: được gọi **ngay sau khi** resource savepoint tạo xong.
- `savepointRollback(Object savepoint)`: được gọi **ngay trước khi** rollback về savepoint.

Chúng có thể dùng trong hạ tầng cần điều phối state nội bộ với savepoint, nhưng không thay thế ba method trên `TransactionStatus`. Đừng nhầm `savepointRollback()` với `afterCompletion(STATUS_ROLLED_BACK)`: rollback về savepoint không phải hoàn tất physical transaction. Callback không tự hoàn tác các side effect ngoài DB nếu bạn chưa viết logic xử lý tương ứng.

### 9.4. JPA persistence context không nhất thiết quay về trạng thái cũ

Khi JDBC rollback về savepoint, các đối tượng entity đã thay đổi trong `EntityManager`/Hibernate session có thể vẫn mang state được thay đổi sau savepoint. Một số SQL có thể bị trì hoãn đến khi flush. Vì vậy **không áp dụng máy móc** ví dụ JDBC thuần với `JdbcTransactionManager` cho `JpaTransactionManager` và code JPA mà không kiểm thử thêm flushing, persistence context, savepoint support.

### 9.5. Phạm vi transaction của savepoint không tự truyền sang thread/reactive pipeline

Mô hình JDBC imperative của Spring dùng resource ràng buộc theo thread. Mở `@Async` hoặc thread mới trong đoạn giữa create/rollback có thể khiến SQL của thread mới nằm ngoài transaction hiện tại, và rollback về savepoint ở thread cũ không đảo ngược các side effect đó. Với R2DBC/reactive, transaction dùng Reactor context và manager riêng; ví dụ `TransactionStatus`/`JdbcTemplate` ở đây **không** phải cách triển khai reactive transaction.

## 10. Lỗi phổ biến và phương án xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `createSavepoint()` ném `NestedTransactionNotSupportedException` | Driver/transaction manager hoặc resource hiện tại không hỗ trợ savepoint | Kiểm tra DB driver, transaction manager và active transaction; fallback an toàn |
| Rollback về savepoint nhưng dữ liệu vẫn còn | SQL không dùng cùng physical transaction/connection; code ngoài DB; mốc tạo sai thời điểm | Dùng `JdbcTemplate` cùng datasource/manager; test trạng thái DB sau commit |
| `releaseSavepoint()` rồi rollback báo lỗi | Handle đã được release hoặc invalidated | Không sử dụng lại; quản lý vòng đời handle |
| Sau rollback một phần, outer vẫn rollback | Code gọi `setRollbackOnly()`; lỗi đã thoát qua interceptor REQUIRED; lỗi khác chưa xử lý | Xác định transaction boundary và chính sách rollback |
| Sau JDBC error không thể tiếp tục SQL | Database yêu cầu phục hồi về savepoint/transaction trạng thái lỗi | Tạo savepoint **trước** thao tác có thể lỗi; rollback về nó hoặc rollback toàn transaction |
| `hasSavepoint()` là false dù code từng gọi create | API chỉ báo savepoint nội bộ do nested status nắm giữ | Quản lý handle của savepoint thủ công |
| Rollback về mốc ngoài rồi dùng lại mốc trong | Mốc sau có thể bị vô hiệu | Không giữ/dùng handle thuộc nhánh đã bị rollback |
| Chạy ổn H2 nhưng lỗi trên database thực | Khác nhau về DDL transaction, isolation, driver và release semantics | Test tích hợp trên DB thực, kiểm tra `supportsSavepoints()` |
| Rollback không hoàn tác gửi email/HTTP | Savepoint chỉ thuộc resource có hỗ trợ transaction | Dùng outbox/after-commit/compensation cho side effect |
| Dùng savepoint khi không có actual transaction | Chạy ngoài transaction hoặc sai context | Dùng `TransactionTemplate`/AOP boundary phù hợp và cùng manager |
| Business code giữ handle quá lâu | Transaction đã hoàn tất hoặc đổi thread/connection | Giữ handle trong local scope của transaction, không cache |
| `NESTED` không chạy qua proxy | Self-invocation hoặc không bật transaction advice | Gọi bean riêng qua proxy hoặc dùng template rõ ràng |

## 11. Tóm tắt và câu hỏi tự kiểm tra

**Quy tắc ghi nhớ:**

1. `createSavepoint()` là tạo **mốc bên trong physical transaction**.
2. `rollbackToSavepoint(sp)` là hoàn tác **phần sau mốc**, không rollback cả transaction và **không release tự động**.
3. `releaseSavepoint(sp)` là dọn mốc, **không commit** hay giữ phần đã release trước outer rollback.
4. `status.setRollbackOnly()` là quyết định rollback **toàn transaction**, không phải partial rollback.
5. `TransactionTemplate` cung cấp `TransactionStatus` trực tiếp; `TransactionAspectSupport.currentTransactionStatus()` cần invocation của Spring transaction interceptor.
6. Spring JDBC savepoint phù hợp khi transaction manager, driver và database hỗ trợ; phải kiểm thử SQL failure/cleanup và khả năng commit tiếp.
7. `Propagation.NESTED` dùng cùng physical transaction/savepoint, trong khi `REQUIRES_NEW` dùng transaction vật lý độc lập.

**Tự kiểm tra:**

- **Q1.** Sau `rollbackToSavepoint(sp)`, mốc có được tự release không? — **Không**, có thể gọi `releaseSavepoint(sp)` khi không còn dùng.
- **Q2.** Release một savepoint có khiến các INSERT trước đó chắc chắn tồn tại dù transaction ngoài rollback không? — **Không**, release không commit.
- **Q3.** `status.hasSavepoint() == false` có nghĩa không thể gọi `createSavepoint()`? — **Không**, API này chủ yếu phản ánh savepoint mà nested status đang giữ.
- **Q4.** Nếu đã `setRollbackOnly()`, release một savepoint có cứu được transaction để commit không? — **Không**.
- **Q5.** Hai savepoint SP1 rồi SP2, rollback về SP1 có thể sử dụng lại SP2 không? — **Không nên**; SP2 có thể đã vô hiệu.
- **Q6.** Lý do cần savepoint trước một INSERT có thể lỗi trên PostgreSQL? — **Để có mốc hợp lệ rollback phần lỗi, khôi phục trạng thái transaction và tiếp tục các SQL sau đó nếu lỗi thực sự có thể phục hồi**.
- **Q7.** Khi cần một transaction commit riêng ngay cả nếu outer rollback, chọn savepoint hay `REQUIRES_NEW`? — **`REQUIRES_NEW`**, đồng thời cân nhắc kết nối, khóa và nhất quán nghiệp vụ.

## Tài liệu chính thức

- Spring Framework — `TransactionStatus` API và `hasSavepoint()`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `SavepointManager`: `createSavepoint`, `rollbackToSavepoint`, `releaseSavepoint`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/SavepointManager.html
- Spring Framework — `AbstractTransactionStatus`: phân biệt custom savepoint và nested held savepoint: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractTransactionStatus.html
- Spring Framework — `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework — `TransactionSynchronization` callbacks từ Spring 6.2: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — Transaction Propagation, `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — `DataSourceTransactionManager` và JDBC savepoint support: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — Controlling Database Connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
