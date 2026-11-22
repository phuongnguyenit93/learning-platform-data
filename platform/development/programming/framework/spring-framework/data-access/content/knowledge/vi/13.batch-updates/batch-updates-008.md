# Batch không tự tạo tính nguyên tử nếu thiếu giao dịch phù hợp

Trong Spring Framework Data Access, `batch` là kỹ thuật gom nhiều thao tác SQL để giảm chi phí gửi lệnh và xử lý. **Batch không đồng nghĩa với một giao dịch (transaction).** Khi một thao tác giữa chừng thất bại, các thao tác đã chạy trước đó có được giữ lại hay bị hủy cùng nhau phụ thuộc vào **ranh giới giao dịch, cơ chế commit/rollback và khả năng giao dịch của database**.

Sau bài này, bạn có thể giải thích sự khác nhau giữa batch và atomicity, nhận diện rủi ro cập nhật dở dang, đặt ranh giới giao dịch đúng khi dùng `JdbcTemplate.batchUpdate(...)`, và kiểm chứng rollback bằng một tình huống gây lỗi có chủ đích.

## 1. Phân biệt batch, transaction và atomicity

| Khái niệm | Vai trò | Điều không được suy diễn |
| --- | --- | --- |
| JDBC batch | Gom nhiều lần thực thi của cùng `PreparedStatement` hoặc nhóm lệnh để giảm round trip; `JdbcTemplate.batchUpdate` hỗ trợ cơ chế này. | Gom lệnh **không tự tạo** một transaction bao quanh tất cả lệnh. |
| Transaction | Một đơn vị công việc được quản lý qua `BEGIN`/bắt đầu giao dịch, `COMMIT` hoặc `ROLLBACK`. | Chỉ những thao tác thực sự tham gia **cùng transaction** mới được xử lý chung tại ranh giới đó. |
| Atomicity | Với thao tác được DB bảo đảm ở mức giao dịch: hoặc toàn bộ thay đổi trong transaction được commit, hoặc toàn bộ bị rollback. | Atomicity không tự mở rộng sang kết nối khác, tài nguyên ngoài DB hoặc giao dịch đã commit. |
| Isolation | Quy định cách các giao dịch đồng thời quan sát và ảnh hưởng lẫn nhau. | Isolation không thay thế atomicity và không tự sửa lỗi thiếu transaction. |

Một lời gọi API không phải lúc nào cũng tương đương một lệnh SQL duy nhất. Ví dụ, `batchUpdate` chứa 500 lần `INSERT` có thể được driver gửi theo nhiều cách, chia thành các nhóm nhỏ, hoặc thực thi tuần tự nếu driver không hỗ trợ batching. Không nên lấy tên hàm hay số lần gọi API làm bằng chứng tất cả thay đổi sẽ cùng thành công hoặc cùng thất bại.

### `autoCommit` là mắt xích quan trọng

Với JDBC `Connection` thông thường, `autoCommit=true` là mặc định ban đầu. Khi không có transaction do Spring quản lý và kết nối hoạt động ở chế độ tự commit, một câu lệnh thành công có thể được commit trước khi một câu lệnh khác trong batch thất bại. Cách driver/database xử lý phần còn lại sau lỗi có thể khác nhau; **đừng giả định batch sẽ dừng đúng ở phần tử lỗi hay hoàn tác các phần tử trước**.

Khi `autoCommit=false`, các thao tác trên **cùng kết nối** có thể nằm trong cùng transaction. Tuy nhiên, chỉ tắt auto-commit vẫn chưa đủ: chương trình phải `commit()` khi toàn bộ đơn vị công việc hợp lệ, và `rollback()` khi có lỗi. Trong Spring, transaction manager thực hiện việc điều phối này nếu cấu hình và phạm vi gọi đúng.

## 2. Tình huống: hai hàng đã ghi, hàng thứ ba lỗi

Giả sử bảng bắt đầu trống:

~~~sql
CREATE TABLE batch_item (
    id BIGINT PRIMARY KEY,
    name VARCHAR(80) NOT NULL
);
~~~

Ứng dụng muốn thêm lần lượt ba phần tử:

~~~text
(1, 'One')  -> hợp lệ
(2, 'Two')  -> hợp lệ
(1, 'Dup')  -> lỗi trùng PRIMARY KEY
~~~

Diễn biến có thể quan sát với cơ sở dữ liệu hỗ trợ tình huống này, chẳng hạn H2 trong ví dụ chạy ở phần 3:

| Điểm kiểm tra | Không có transaction bao cả batch, auto-commit bật | Toàn batch trong một transaction, lỗi dẫn đến rollback |
| --- | --- | --- |
| Ghi `id=1` lần đầu | Thành công và có thể đã commit | Thành công tạm thời, chưa commit |
| Ghi `id=2` | Thành công và có thể đã commit | Thành công tạm thời, chưa commit |
| Ghi `id=1` lần hai | Lỗi khóa chính | Lỗi khóa chính |
| Trạng thái sau khi xử lý lỗi | Hai dòng đầu **có thể** còn trong DB | Không còn dòng nào của transaction đó nếu rollback hoàn tất |
| Tính nguyên tử của *cả nhóm* | Không được bảo đảm | Được bảo đảm trong phạm vi transaction và tài nguyên DB phù hợp |

Điểm quyết định là **lệnh `ROLLBACK` chỉ đảo được thay đổi chưa commit của đúng transaction**. Nó không thể `quay ngược` những lần commit đã hoàn tất ở các transaction khác. Đừng dựa vào suy đoán “batch là một lần gọi phương thức” để bảo vệ các nghiệp vụ như ghi số dư, tạo đơn hàng kèm chi tiết, hoặc nhập dữ liệu phải nhất quán theo nhóm.

## 3. Ví dụ Java 17 chạy được: cùng một batch, hai kết quả

Ví dụ dùng Spring JDBC, `TransactionTemplate` và H2 in-memory để tránh phụ thuộc vào ứng dụng Spring Boot. Chương trình chủ ý gây lỗi khóa chính hai lần: lần đầu **không tạo transaction bao quanh**, lần sau **bao toàn bộ batch trong một transaction**. Nó bắt exception ở **bên ngoài** transaction để có thể đếm số hàng còn lại.

Tạo cấu trúc tệp:

~~~text
batch-atomicity-demo/
├── pom.xml
└── src/main/java/example/BatchAtomicityDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>batch-atomicity-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
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
            <version>2.4.240</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.4</version>
                <configuration>
                    <mainClass>example.BatchAtomicityDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/example/BatchAtomicityDemo.java`:

~~~java
package example;

import java.util.List;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class BatchAtomicityDemo {

    record Item(long id, String name) {}

    public static void main(String[] args) {
        JdbcDataSource dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:batch_atomicity;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE batch_item (
                    id BIGINT PRIMARY KEY,
                    name VARCHAR(80) NOT NULL
                )
                """);

        List<Item> rows = List.of(
                new Item(1, "One"),
                new Item(2, "Two"),
                new Item(1, "Dup")
        );

        // Thử 1: Không có transaction bao trùm toàn bộ batch.
        try {
            insertBatch(jdbc, rows);
        } catch (DataAccessException expected) {
            System.out.println("No tx: batch failed");
        }
        System.out.println("No tx: rows=" + countRows(jdbc));

        // Xóa dữ liệu thử 1 để hai trường hợp có cùng trạng thái ban đầu.
        jdbc.update("DELETE FROM batch_item");

        // Thử 2: Cùng thao tác, nhưng transaction manager quản lý kết nối,
        // rollback khi DataAccessException thoát khỏi callback.
        TransactionTemplate tx = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource)
        );
        try {
            tx.executeWithoutResult(status -> insertBatch(jdbc, rows));
        } catch (DataAccessException expected) {
            System.out.println("With tx: batch failed");
        }
        System.out.println("With tx: rows=" + countRows(jdbc));
    }

    static void insertBatch(JdbcTemplate jdbc, List<Item> rows) {
        jdbc.batchUpdate(
                "INSERT INTO batch_item(id, name) VALUES (?, ?)",
                rows,
                3,
                (ps, item) -> {
                    ps.setLong(1, item.id());
                    ps.setString(2, item.name());
                }
        );
    }

    static int countRows(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM batch_item", Integer.class
        );
    }
}
~~~

Trong thư mục gốc, cần JDK 17+ và Maven đã cài:

~~~bash
mvn -q compile exec:java
~~~

Kết quả in bởi chương trình với H2 và các phiên bản phụ thuộc ở trên:

~~~text
No tx: batch failed
No tx: rows=2
With tx: batch failed
With tx: rows=0
~~~

**Giải thích kết quả:** Ở lượt đầu, H2 chấp nhận hai `INSERT` đầu trước khi phát hiện trùng khóa; khi không có transaction bao trùm, hai dòng đã được commit. Ở lượt sau, `TransactionTemplate` bắt đầu transaction, `JdbcTemplate` dùng kết nối gắn với transaction đó, exception thoát khỏi callback khiến manager rollback cả hai `INSERT` đã chạy; kết quả còn 0 dòng. Lệnh `DELETE` giữa hai lượt chỉ đặt lại dữ liệu thử nghiệm và **không phải** một phần của transaction thử 2.

Đây là ví dụ xác nhận **khả năng cập nhật dở dang**, không phải lời hứa mọi driver hoặc database đều giữ đúng 2 dòng sau một batch lỗi khi auto-commit bật. Các hệ quản trị có quy tắc xử lý batch và statement khác nhau; kết quả phải kiểm tra trên DB/driver thực tế. Trong ứng dụng sản xuất, không nuốt `DataAccessException` nếu nghiệp vụ cần rollback; phần `catch` ở đây đặt ngoài lời gọi transaction chỉ để báo kết quả thử nghiệm.

## 4. Áp dụng trong ứng dụng Spring: đặt transaction ở tầng service

Với ứng dụng Spring JDBC, `JdbcTemplate.batchUpdate(...)` **không tự thêm transaction**. Ranh giới nên bao trọn *đơn vị nghiệp vụ* ở tầng service: một lời gọi có thể chứa một batch, nhiều batch, hoặc nhiều lệnh cập nhật liên quan. Ví dụ sau là **đoạn mã đặt trong ứng dụng Spring đã cấu hình JDBC**, không phải chương trình độc lập thứ hai.

~~~java
package example;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchItemService {
    private final JdbcTemplate jdbc;

    public BatchItemService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void saveAll(List<Item> items) {
        jdbc.batchUpdate(
                "INSERT INTO batch_item(id, name) VALUES (?, ?)",
                items,
                100,
                (ps, item) -> {
                    ps.setLong(1, item.id());
                    ps.setString(2, item.name());
                }
        );
        // Nếu còn thao tác DB bắt buộc cùng thành công, đặt tại đây
        // để chúng tham gia cùng transaction.
    }

    public record Item(long id, String name) {}
}
~~~

Để `@Transactional` có tác dụng thực, cần thỏa các điều kiện:

1. `BatchItemService` là bean do Spring quản lý và phương thức được gọi **qua Spring proxy từ bên ngoài bean**. Lời gọi nội bộ `this.saveAll(...)` trong cùng đối tượng không được proxy chặn theo cơ chế mặc định.
2. Cấu hình đã kích hoạt transaction management và có `PlatformTransactionManager` phù hợp. Với JDBC trên một `DataSource`, dùng `JdbcTransactionManager` hoặc `DataSourceTransactionManager` phù hợp; khi tự cấu hình Spring thuần có thể khai báo `@EnableTransactionManagement`.
3. `JdbcTemplate` và transaction manager cùng tham chiếu **một `DataSource` cần được quản lý**; các lệnh dùng kết nối lấy theo cơ chế Spring để tham gia transaction hiện tại. Tự lấy `DriverManager.getConnection(...)` bên trong có thể tạo kết nối ngoài transaction.
4. Lỗi phải kích hoạt rollback. `DataAccessException` của Spring là unchecked nên mặc định rollback khi thoát khỏi phương thức được proxy quản lý. Mặc định `@Transactional` không rollback với checked exception nếu không cấu hình quy tắc khác.
5. Database/tables thực sự hỗ trợ transaction cho loại thao tác đã chạy; không đặt kỳ vọng rollback lên lệnh có implicit commit hoặc tài nguyên ngoài ranh giới DB.

Trong Spring Boot đã bật JDBC auto-configuration, thường có sẵn transaction manager thích hợp; hãy kiểm tra bean thực tế thay vì khai báo thêm manager tùy tiện. Với cấu hình Spring thuần, có thể cấu hình minh họa như sau (dùng khi chưa có manager tương đương):

~~~java
@Configuration
@EnableTransactionManagement
public class JdbcTxConfig {
    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
~~~

Đoạn cấu hình cần các import tương ứng từ `org.springframework.context.annotation`, `org.springframework.transaction`, `org.springframework.jdbc.datasource` và `javax.sql`; nó được dùng trong context Spring có bean `DataSource`. Đặt `@Transactional` lên một method nhưng gọi qua `new BatchItemService(...)` hoặc gọi nội bộ qua `this` sẽ không nhận được cơ chế proxy mong đợi.

### Một transaction cho nhiều chunk

Giả sử nhập 10.000 bản ghi theo chunk 100. `batchSize=100` chỉ nói Spring chia công việc JDBC thành các batch nhỏ; **nó không tự giới hạn hay mở rộng phạm vi transaction**. Nếu cả 10.000 bản ghi phải cùng thành công, đặt vòng lặp hoặc lời gọi `batchUpdate` bên trong **cùng một** phương thức `@Transactional` (và bảo đảm transaction manager/connection nhất quán). Nếu mỗi chunk gọi qua một transaction riêng và commit xong, lỗi chunk sau không hoàn tác chunk trước.

Ngược lại, một transaction quá dài giữ lock, log và tài nguyên lâu hơn. Phạm vi giao dịch cần phản ánh yêu cầu nhất quán thực sự: có nghiệp vụ chấp nhận từng chunk thành công riêng và có cơ chế retry/idempotency; nghiệp vụ khác bắt buộc một lần commit chung. Không đánh đổi tính đúng đắn bằng cách âm thầm chuyển từ transaction toàn nhóm sang commit từng chunk.

## 5. Vì sao `@Transactional` vẫn có thể không bảo vệ được batch?

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Dữ liệu đã lưu một phần sau khi có lỗi | Không có transaction hoạt động, hoặc ngoại lệ bị bắt và bỏ qua trước khi rời method giao dịch | Xác nhận transaction active; cho exception phù hợp lan ra khỏi method, hoặc đánh dấu `rollbackOnly` khi cần xử lý lỗi bên trong |
| Có annotation nhưng không rollback | Tự gọi method trong cùng class, tạo object bằng `new`, hoặc cấu hình transaction chưa kích hoạt | Gọi service qua bean Spring được proxy quản lý, kiểm tra bean transaction manager và proxy |
| Một số câu lệnh vẫn commit | Dùng connection/`DataSource` khác; propagation `REQUIRES_NEW` có thể đã commit transaction con; một bước chạy ngoài transaction | Theo dõi từng kết nối và transaction boundary, kiểm tra `propagation` |
| Checked exception xảy ra nhưng dữ liệu vẫn commit | Rollback mặc định theo quy tắc unchecked; method trả về bình thường hoặc checked exception không thuộc rollback rule | Dùng `@Transactional(rollbackFor = Exception.class)` nếu nghiệp vụ yêu cầu, hoặc ném exception phù hợp |
| Rollback không đảo hết tác động | DDL có implicit commit, bảng/engine không transactional, gửi email/HTTP/Kafka hoặc ghi file bên ngoài transaction DB | Tách thao tác ngoài DB; dùng transactional outbox, saga hoặc cơ chế bù trừ phù hợp khi cần |
| Lỗi xuất hiện sau lúc trả về từ method | Gọi async, transaction đã kết thúc, công việc chuyển thread và mất context thread-bound | Đặt transaction tại đơn vị xử lý thực, xác định rõ thread và thời điểm commit |

**Hai trường hợp dễ bị bỏ sót:**

- Bắt lỗi bên trong method rồi chỉ log: `catch (DataAccessException ex) { log.warn(...); }` có thể khiến transaction kết thúc bằng commit vì không còn exception thoát ra, trừ khi tài nguyên/manager đã đánh dấu rollback-only. Nếu muốn toàn bộ thất bại, ném lại exception hoặc đánh dấu rollback-only có chủ đích.
- `@Transactional(propagation = REQUIRES_NEW)` bắt đầu một transaction độc lập. Những thay đổi của transaction đó có thể commit trước; một transaction ngoài rollback sau đó không tự đảo được commit độc lập này.

## 6. Đọc kết quả batch và exception cho đúng

`JdbcTemplate.batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` trả `int[][]`: mỗi mảng con là kết quả các lệnh trong một chunk. Các cách gọi `batchUpdate` khác có thể trả `int[]`. Giá trị số hàng bị ảnh hưởng đến từ JDBC driver; `Statement.SUCCESS_NO_INFO` (giá trị `-2`) nghĩa là driver báo thành công nhưng không biết chính xác số dòng; `Statement.EXECUTE_FAILED` (giá trị `-3`) biểu thị lệnh thất bại trong những trường hợp driver tiếp tục báo trạng thái từng phần tử.

Với JDBC thuần, `BatchUpdateException.getUpdateCounts()` có thể cho biết tiến độ thực thi đến thời điểm lỗi, nhưng **không phải bằng chứng đã commit, cũng không phải dấu hiệu mọi dòng sẽ còn lại sau rollback**. Spring có thể dịch `SQLException` thành `DataAccessException`; hãy kiểm tra ngoại lệ gốc khi chẩn đoán, đồng thời dùng truy vấn trạng thái DB sau khi transaction kết thúc để xác nhận tác động thật.

Một số điểm cần quan sát khi debug:

- Transaction có đang active tại điểm gọi batch không? Có thể dùng `TransactionSynchronizationManager.isActualTransactionActive()` để hỗ trợ log trong môi trường Spring.
- SQL nào gây lỗi: unique/check/foreign key, constraint `NOT NULL`, hoặc lỗi kết nối?
- Các câu lệnh thực tế có dùng cùng connection đã được transaction manager bind không?
- Sau exception và khi method giao dịch đã thoát, dữ liệu còn lại là bao nhiêu? Đọc từ một transaction/kết nối mới nếu cần xác nhận trạng thái **đã commit**.
- Nếu driver hỗ trợ nhiều chiến lược batching/rewrite, kiểm tra hành vi trên đúng DB, phiên bản driver và các cấu hình production.

## 7. Kiểm thử tính nguyên tử theo hành vi, không theo annotation

Một kiểm thử có giá trị phải chủ động gây lỗi ở phần tử đến sau và xác nhận trạng thái DB **sau khi method giao dịch kết thúc**:

1. Tạo bảng có constraint rõ ràng và khởi tạo dữ liệu xác định; dùng danh sách chứa hai hàng hợp lệ và một hàng trùng khóa.
2. Gọi method service `@Transactional` từ bean khác hoặc từ test qua bean Spring, để lời gọi thực sự đi qua proxy.
3. Xác nhận có `DataAccessException` hoặc exception nghiệp vụ đã cấu hình rollback; không chỉ kiểm tra mảng số lượng cập nhật.
4. Truy vấn lại và khẳng định **không có hàng nào của nhóm vừa thử được commit**. Nếu nhóm chứa nhiều bảng, kiểm tra tất cả bảng liên quan.
5. Có thể chạy đối chứng một lời gọi không có transaction trong môi trường test riêng để thấy trạng thái cập nhật dở dang; đừng coi số hàng còn lại là hằng số áp dụng mọi DB.

Lưu ý: test tự mang `@Transactional` đôi khi rollback sau mỗi test, che khuất việc service thực sự có transaction hay không. Khi kiểm thử ranh giới commit của service, tổ chức test để kiểm tra trạng thái từ bên ngoài transaction của test, hoặc tắt transaction cấp test và chủ động dọn dữ liệu.

## 8. Quy tắc thực hành và những giới hạn cần nhớ

- **Batch tối ưu cách gửi lệnh; transaction quyết định nhóm thay đổi được commit hay rollback cùng nhau.** Đó là hai trục độc lập.
- Đặt transaction quanh đơn vị nghiệp vụ nhỏ nhất cần cùng thành công; quản lý connection/DataSource thống nhất và chọn transaction manager đúng loại tài nguyên.
- Để lỗi thất bại lan qua ranh giới transaction với rollback rule phù hợp. Không vô tình nuốt lỗi hoặc tạo một transaction độc lập ở giữa luồng.
- Kiểm tra đặc tính transactional của bảng/engine và các câu lệnh DDL; một số DB có implicit commit. Transaction của một DB không tự quản lý dịch vụ mạng, file, message broker hay nhiều DB.
- Với batch lớn, cân bằng kích thước chunk, thời gian giữ lock, tài nguyên, retry và idempotency. Nếu phải commit theo chunk, hãy công khai semantics “một phần thành công” và thiết kế phục hồi.
- Dùng phép thử lỗi có chủ đích và truy vấn sau transaction để chứng minh tính nguyên tử; annotation, `updateCounts` và log “batch complete” chỉ là tín hiệu phụ trợ.

**Tự kiểm tra:** Nếu 100 bản ghi được xử lý qua `JdbcTemplate.batchUpdate` với `batchSize=20`, bản ghi thứ 73 vi phạm khóa chính, điều gì xảy ra với 72 bản ghi trước? **Không thể kết luận chỉ từ `batchSize`.** Cần biết cả 100 bản ghi có nằm trong một transaction phù hợp không, exception có kích hoạt rollback không, driver/DB và các bước ngoài transaction có hành xử như thế nào. Nếu một transaction bao toàn bộ và rollback thành công, không bản ghi nào của nhóm được commit; nếu đã commit từng chunk hoặc từng lệnh, có thể còn dữ liệu một phần.

### Tài liệu tham khảo

- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/advanced.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
