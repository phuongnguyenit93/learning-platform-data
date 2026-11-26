# Giao dịch ngầm định và giao dịch tường minh trong Neo4j

## 1. Giao dịch là gì và tại sao cần phân biệt hai cách thực thi?

Trong **Neo4j**, dữ liệu được lưu theo mô hình **property graph** gồm node, relationship, label và property. Khi ứng dụng dùng Cypher để tạo node, sửa thuộc tính hoặc nối các node bằng relationship, các thao tác đó diễn ra trong **transaction (giao dịch)**. Transaction quyết định một nhóm thao tác được **commit** để lưu kết quả hay **rollback** để hủy các thay đổi chưa commit.

Xét nghiệp vụ thêm thành viên vào nhóm dự án. Ứng dụng cần:

1. Tạo hoặc xác định node `(:AppUser {id: 'u-101'})`.
2. Tạo hoặc xác định node `(:Project {id: 'p-01'})`.
3. Tạo relationship `(user)-[:MEMBER_OF]->(project)`.

Nếu ba bước là một đơn vị nghiệp vụ, việc tạo được user nhưng không tạo được relationship có thể để lại trạng thái chưa hoàn chỉnh. Có thể giải quyết bằng **một câu Cypher** thực hiện đủ các bước hoặc bằng **một giao dịch tường minh** bao nhiều câu Cypher.

Neo4j hỗ trợ hai cách tổ chức thường gặp:

- **Giao dịch ngầm định** (*implicit / auto-commit transaction*): client gửi một câu Cypher; hệ thống tự quản lý transaction cho câu lệnh đó.
- **Giao dịch tường minh** (*explicit transaction*): ứng dụng/client chủ động xác định ranh giới của transaction và chạy một hoặc nhiều câu Cypher bên trong. Trong Java Driver, giao dịch tường minh có thể được quản lý tự động bằng callback (*managed transaction*) hoặc do lập trình viên trực tiếp gọi `commit()`/`rollback()` (*unmanaged transaction*).

**Điểm cốt lõi:** Một câu Cypher chạy bằng giao dịch ngầm định vẫn có tính nguyên tử. Khác biệt đáng chú ý là **ai quản lý ranh giới transaction** và **có thể gom nhiều câu Cypher vào cùng một lần commit hay không**.

## 2. Đặt transaction trong bối cảnh ACID

| Thuộc tính | Ý nghĩa khi thao tác trên graph Neo4j | Cần ghi nhớ |
| --- | --- | --- |
| **Atomicity** — nguyên tử | Mọi thay đổi trong cùng transaction được commit cùng nhau hoặc bị rollback | Hai câu lệnh chạy ở hai auto-commit transaction riêng **không** tạo thành một đơn vị nguyên tử |
| **Consistency** — nhất quán | Transaction phải tuân thủ các ràng buộc database; quy tắc nghiệp vụ cần được ứng dụng/truy vấn thể hiện | Unique constraint bảo vệ khóa; Neo4j không tự biết số thành viên tối đa của một dự án |
| **Isolation** — cô lập | Các giao dịch đang chạy có cơ chế cô lập và khóa để tránh đọc thay đổi chưa commit | Mặc định **read committed**; không mặc nhiên ngăn mọi non-repeatable read hoặc xung đột nghiệp vụ |
| **Durability** — bền vững | Giao dịch commit thành công được Neo4j lưu giữ theo cơ chế đảm bảo của hệ thống | Nhìn thấy dữ liệu **trong transaction chưa commit** không chứng minh dữ liệu đã bền vững |

Trong một transaction, truy vấn sau có thể đọc các thay đổi từ truy vấn trước của **chính transaction đó**. Giao dịch khác không được thấy thay đổi chưa commit. Khi transaction kết thúc bằng rollback, các cập nhật trong giao dịch đó không trở thành trạng thái đã commit.

Để giảm xung đột, giữ transaction đủ ngắn, hạn chế công việc ngoài database khi đang giữ transaction và sử dụng constraint/khóa nghiệp vụ phù hợp.

## 3. Giao dịch ngầm định (implicit / auto-commit)

### 3.1. Cơ chế

Ở chế độ auto-commit, mỗi lần gửi một statement Cypher qua API phù hợp, Neo4j tạo một transaction cho lần thực thi đó. Ví dụ, Java Driver sử dụng `session.run(...)` để thực thi trong **implicit transaction**.

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.run(
        "MERGE (u:AppUser {id: $id})",
        Map.of("id", "u-101")
    ).consume();
}
```

Ở đây:

- `session.run(...)` gửi một câu Cypher trong một giao dịch ngầm định.
- `consume()` tiêu thụ kết quả còn lại, giúp hoàn tất lần thực thi và lấy `ResultSummary` nếu cần.
- Khi transaction được hoàn tất và commit thành công, node tạo bởi câu lệnh (nếu chưa tồn tại) mới trở thành kết quả bền vững.

Java Driver trả về `Result` theo cơ chế stream/lazy. **Không nên xem thời điểm `session.run(...)` vừa trả về là bằng chứng commit đã hoàn tất.** Với implicit transaction, commit được bảo đảm khi result đã được tiêu thụ đầy đủ; nên sử dụng `consume()`, `list()` hoặc đọc đến cuối stream trước khi phụ thuộc vào kết quả ghi ở thao tác tiếp theo. Nếu có lỗi khi tiêu thụ result, ứng dụng phải xử lý lỗi đó.

Trong Neo4j Browser hoặc cypher-shell, mỗi câu Cypher thông thường cũng có thể được thực thi với transaction tự quản lý bởi client; cú pháp/chế độ thao tác giao dịch cụ thể tùy công cụ.

### 3.2. Mỗi lần auto-commit là một ranh giới riêng

Giả sử ứng dụng chạy lần lượt:

```cypher
MERGE (u:AppUser {id: 'u-101'});
```

```cypher
MERGE (p:Project {id: 'p-01'});
```

```cypher
MATCH (u:AppUser {id: 'u-101'})
MATCH (p:Project {id: 'p-01'})
MERGE (u)-[:MEMBER_OF]->(p);
```

Nếu client thực hiện **ba lệnh trên bằng ba implicit transaction**, lệnh 1 và 2 có thể đã commit trước khi lệnh 3 thất bại. Khi ấy node có thể tồn tại nhưng relationship chưa được tạo. Việc viết ba lệnh cạnh nhau trong tài liệu hoặc gửi từ cùng một session **không tự biến chúng thành một transaction**.

Ngược lại, có thể kết hợp thành **một câu Cypher duy nhất**:

```cypher
MERGE (u:AppUser {id: 'u-101'})
MERGE (p:Project {id: 'p-01'})
MERGE (u)-[:MEMBER_OF]->(p)
RETURN u.id AS userId, p.id AS projectId;
```

Khi thực thi bình thường trong một implicit transaction, cả ba thao tác thuộc **cùng một câu lệnh** và cùng một transaction: câu lệnh thất bại thì các thay đổi chưa commit của nó được rollback. Tuy vậy, ở nghiệp vụ phức tạp, việc tách thành nhiều câu lệnh rõ ràng trong giao dịch tường minh có thể dễ kiểm soát hơn.

### 3.3. Ưu điểm và hạn chế

| Ưu điểm | Hạn chế cần tính tới |
| --- | --- |
| API đơn giản, thích hợp với truy vấn đơn lẻ | Không dùng nhiều lần `session.run(...)` auto-commit để bảo đảm tất cả cùng commit |
| Ít mã quản lý commit/rollback | Cần tiêu thụ result để xác nhận truy vấn hoàn tất |
| Phù hợp với query đọc, ghi đơn bước hoặc lệnh quản trị riêng lẻ | Java Driver không tự retry implicit transaction như managed transaction |
| Là chế độ cần thiết cho một số thao tác chạy theo lô, ví dụ `CALL { ... } IN TRANSACTIONS` | Ghi theo lô có thể commit từng batch, không có tính nguyên tử toàn bộ |

## 4. Giao dịch tường minh (explicit transaction)

### 4.1. Cơ chế và vòng đời

Giao dịch tường minh có ranh giới rõ ràng:

```text
BEGIN transaction
    Query A: tạo hoặc tìm user
    Query B: tạo hoặc tìm project
    Query C: tạo relationship MEMBER_OF
    (có thể đọc lại kết quả trong transaction)
COMMIT  -> lưu cùng lúc toàn bộ thay đổi thành công
    hoặc
ROLLBACK -> hủy các thay đổi chưa commit của A, B, C
```

Nếu câu lệnh thứ ba ném exception và transaction bị rollback, các thay đổi chưa commit của câu 1 và 2 cũng bị hủy. Một transaction có thể chứa nhiều câu Cypher, kể cả lệnh đọc để kiểm tra điều kiện và lệnh ghi.

Điểm cần phân biệt:

- **Managed transaction:** ứng dụng truyền callback cho Driver qua `session.executeRead(...)` hoặc `session.executeWrite(...)`; Driver quản lý commit/rollback và có thể retry khi gặp lỗi tạm thời.
- **Unmanaged transaction:** ứng dụng gọi `session.beginTransaction()`, rồi `tx.commit()` hoặc `tx.rollback()`. Ứng dụng tự kiểm soát vòng đời và tự thiết kế retry nếu cần.

Cả hai đều cho phép nhiều câu Cypher dùng chung một transaction, khác với nhiều implicit transaction tách rời.

### 4.2. Ví dụ managed transaction bằng Java Driver

Ví dụ sau dùng Driver API đồng bộ của Neo4j Java Driver hiện hành:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public class ManagedTransactionExample {
    public static void main(String[] args) {
        try (
            Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me")
            );
            Session session = driver.session(
                SessionConfig.forDatabase("neo4j")
            )
        ) {
            Map<String, Object> params = Map.of(
                "userId", "u-101",
                "projectId", "p-01"
            );

            session.executeWrite(tx -> {
                tx.run("""
                    MERGE (u:AppUser {id: $userId})
                    """, params).consume();

                tx.run("""
                    MERGE (p:Project {id: $projectId})
                    """, params).consume();

                tx.run("""
                    MATCH (u:AppUser {id: $userId})
                    MATCH (p:Project {id: $projectId})
                    MERGE (u)-[:MEMBER_OF]->(p)
                    """, params).consume();

                return null;
            });

            // Tới đây, executeWrite đã trả về sau khi commit thành công.
            long membershipCount = session.executeRead(tx ->
                tx.run("""
                    MATCH (u:AppUser {id: $userId})
                          -[r:MEMBER_OF]->
                          (p:Project {id: $projectId})
                    RETURN count(r) AS total
                    """, params)
                  .single()
                  .get("total")
                  .asLong()
            );

            if (membershipCount != 1L) {
                throw new IllegalStateException(
                    "Quan hệ MEMBER_OF chưa đúng kỳ vọng"
                );
            }
            System.out.println("Đã commit và xác minh MEMBER_OF");
        }
    }
}
```

Trong ví dụ:

1. Ba lần `tx.run(...)` cùng nằm trong **một managed write transaction**.
2. Nếu một lệnh thất bại hoặc callback ném exception, transaction đang thực thi không được commit và sẽ rollback.
3. Sau khi `executeWrite(...)` hoàn tất thành công, ví dụ dùng một **transaction đọc mới** qua `executeRead(...)` để xác minh relationship đã commit.
4. `MERGE` giúp lệnh tạo node/relationship có thể chạy lại mà không sinh bản sao nếu mô hình và dữ liệu khóa định danh được quản lý đúng.

Trong hệ thống thực, nên có uniqueness constraint cho `AppUser.id` và `Project.id`, chẳng hạn:

```cypher
CREATE CONSTRAINT app_user_id_unique IF NOT EXISTS
FOR (u:AppUser)
REQUIRE u.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project)
REQUIRE p.id IS UNIQUE;
```

Hai lệnh tạo constraint là bước quản lý schema độc lập, nên thực hiện trước luồng nghiệp vụ. Tránh chạy migration schema lẫn với callback ghi dữ liệu thường xuyên.

**Quan trọng với retry:** Driver có thể chạy lại toàn bộ callback của `executeWrite` khi gặp lỗi tạm thời (transient error). Vì vậy callback cần an toàn khi thực thi lại. Không nên gửi email, gọi API thanh toán bên ngoài, tăng biến chia sẻ hoặc thực hiện side effect không thể rollback bên trong callback. Với thao tác tạo bản ghi, dùng khóa nghiệp vụ và thiết kế idempotent.

### 4.3. Ví dụ unmanaged transaction và rollback chủ động

Khi cần điều khiển trực tiếp thời điểm commit hoặc có trường hợp nghiệp vụ muốn rollback, dùng `beginTransaction()`:

```java
import java.util.Map;
import org.neo4j.driver.Session;
import org.neo4j.driver.Transaction;

try (Session session = driver.session()) {
    try (Transaction tx = session.beginTransaction()) {
        tx.run("""
            MERGE (u:AppUser {id: $id})
            ON CREATE SET u.name = $name
            """, Map.of("id", "u-102", "name", "Bình")
        ).consume();

        long matching = tx.run("""
            MATCH (u:AppUser {id: $id})
            RETURN count(u) AS total
            """, Map.of("id", "u-102")
        ).single().get("total").asLong();

        if (matching != 1L) {
            tx.rollback();
            throw new IllegalStateException(
                "Không xác định được duy nhất AppUser"
            );
        }

        tx.commit();
    }
}
```

Trong ví dụ trên, `tx.commit()` là điểm xác nhận kết quả. Nếu luồng thực thi rời khỏi khối `try` mà chưa commit hoặc rollback, việc đóng transaction sẽ rollback những thay đổi chưa commit. Không được coi một truy vấn `tx.run(...)` trả về bình thường là transaction đã commit. Khác managed transaction, `beginTransaction()` **không tự retry toàn bộ công việc** khi gặp lỗi tạm thời.

Một số hệ thống dùng transaction tường minh ngay trong công cụ dòng lệnh. Ví dụ, trong **cypher-shell tương tác**, có các lệnh của client:

```text
:begin
MERGE (u:AppUser {id: 'u-103'});
MERGE (p:Project {id: 'p-02'});
:commit
```

Để hủy thay đổi chưa commit, dùng `:rollback` thay `:commit`. Các lệnh có tiền tố dấu hai chấm ở trên là **lệnh của công cụ client**, không phải cú pháp Cypher để nhét trực tiếp vào `session.run(":begin")`. Khả năng và cách điều khiển transaction trong Neo4j Browser, cypher-shell hoặc công cụ quản trị có thể khác nhau; nên kiểm tra hướng dẫn của đúng client/phiên bản đang dùng.

## 5. So sánh trực tiếp

| Tiêu chí | Giao dịch ngầm định | Giao dịch tường minh |
| --- | --- | --- |
| Ranh giới | Thường là một statement gửi qua client/API | Do client/ứng dụng xác định, bao được nhiều statement |
| Commit | Tự động sau khi thực thi/tiêu thụ result hoàn tất | Managed: Driver tự commit khi callback thành công; unmanaged: gọi `commit()` |
| Rollback | Một statement lỗi thì transaction của statement đó bị hủy | Lỗi/rollback có thể hủy tất cả bước chưa commit trong cùng transaction |
| Java Driver | `session.run(cypher)` | `session.executeWrite/read(...)` hoặc `session.beginTransaction()` |
| Retry | Không có cơ chế tự retry tương đương managed transaction | Managed transaction có thể retry lỗi tạm thời; unmanaged cần tự thiết kế |
| Kịch bản phù hợp | Query độc lập, ghi đơn bước, một số thao tác nhập theo lô | Nhiều lệnh phải cùng thành công; điều kiện cập nhật/phối hợp nhiều node, relationship |
| Rủi ro phổ biến | Tưởng nhiều `session.run` là một transaction; quên consume result | Quên commit, giữ transaction lâu, side effect trong callback được retry |

### Một câu Cypher nhiều `CREATE` có phải là transaction tường minh?

**Không nhất thiết.** Nếu câu Cypher đó chạy bằng `session.run(...)`, nó là một **implicit transaction** nhưng chứa nhiều thao tác graph. Phân biệt theo **cách client mở/quản lý transaction**, không phân loại bằng số lượng node hay relationship bị sửa trong một câu lệnh.

### Một transaction chỉ có một câu Cypher có phải là ngầm định?

**Không nhất thiết.** Nếu ứng dụng gọi `beginTransaction()` rồi chạy một câu Cypher và `commit()`, đó vẫn là **explicit transaction**.

## 6. Ngoại lệ đáng nhớ: `CALL { ... } IN TRANSACTIONS`

Khi nhập dữ liệu lớn, có thể cần chia việc ghi thành nhiều lô để tránh một transaction quá lớn:

```cypher
UNWIND range(1, 1000) AS userNumber
CALL {
    WITH userNumber
    MERGE (:SampleUser {id: userNumber})
} IN TRANSACTIONS OF 100 ROWS;
```

Ở đây, Cypher tạo nhiều batch và mỗi batch được thực thi/commit trong transaction riêng theo cơ chế của mệnh đề `IN TRANSACTIONS`. Ví dụ cố ý dùng ít dữ liệu; trên hệ thống thực cần chọn batch size theo tải, ràng buộc và nhu cầu phục hồi.

**Hai điểm khác hẳn một transaction thông thường:**

1. Mệnh đề `CALL { ... } IN TRANSACTIONS` cần được thực thi bằng **implicit transaction** ở phía client; không đặt nguyên câu lệnh này bên trong `executeWrite(...)` hoặc `beginTransaction()`. Đây là trường hợp cần áp dụng đúng loại transaction cho chức năng Cypher.
2. Nếu batch sau lỗi, **những batch đã commit trước đó có thể vẫn tồn tại**. Không thể giả định toàn bộ 1.000 dòng sẽ rollback cùng nhau. Vì vậy thiết kế nhập liệu theo lô nên idempotent, có khóa định danh/constraint, điểm kiểm tra và khả năng chạy lại an toàn.

Ví dụ Java Driver để thực thi câu lệnh theo lô ở implicit transaction:

```java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    session.run("""
        UNWIND range(1, 1000) AS userNumber
        CALL {
            WITH userNumber
            MERGE (:SampleUser {id: userNumber})
        } IN TRANSACTIONS OF 100 ROWS
        """).consume();
}
```

Lưu ý cú pháp import/subquery có thay đổi theo các phiên bản Cypher; mẫu `CALL { WITH userNumber ... }` phổ biến trong Neo4j 5, còn các bản mới có thêm cú pháp biến phạm vi `CALL (userNumber) { ... }`. Đối chiếu phiên bản server nếu ứng dụng cần hỗ trợ nhiều đời Neo4j.

## 7. Tích hợp Spring Data Neo4j

**Spring Data Neo4j (SDN)** thường được dùng trong ứng dụng Spring Boot có repository, entity và quan hệ object. Với nhiều thao tác graph cần cùng thành công, đặt ranh giới transaction ở **service layer**:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {
    private final AppUserRepository userRepository;
    private final ProjectRepository projectRepository;

    public RegistrationService(
            AppUserRepository userRepository,
            ProjectRepository projectRepository) {
        this.userRepository = userRepository;
        this.projectRepository = projectRepository;
    }

    @Transactional
    public void register(AppUser user, Project project) {
        userRepository.save(user);
        projectRepository.save(project);
        // Nếu có thay đổi relationship giữa các entity,
        // thực hiện trong cùng transaction này.
    }
}
```

Mã minh họa giả định ứng dụng đã định nghĩa `AppUser`, `Project` và các repository tương ứng. Cách gắn và persist relationship còn phụ thuộc mapping entity của dự án. Ý chính là hai lệnh `save` cùng tham gia transaction do Spring quản lý nếu method được gọi thông qua Spring proxy và cấu hình transaction đúng.

Một số lưu ý quan trọng:

- `@Transactional` mặc định rollback đối với unchecked exception (`RuntimeException`/`Error`); với checked exception có thể cần cấu hình `rollbackFor` theo chính sách ứng dụng.
- Nếu method `@Transactional` **tự gọi** một method khác cũng có annotation trong cùng instance, proxy Spring thông thường không áp dụng ranh giới transaction mới cho lời gọi nội bộ đó.
- Tránh trộn transaction do Spring quản lý với `session.run(...)` ở một Driver/session độc lập nếu muốn bảo đảm các lệnh thuộc **cùng** một giao dịch.
- Nếu nghiệp vụ cần xác minh dữ liệu **sau commit**, tổ chức bước đọc ở transaction tiếp theo hoặc dùng cơ chế after-commit phù hợp. Đọc trong cùng `@Transactional` chỉ xác minh trạng thái thấy được ở transaction hiện tại.
- Với xử lý nhiều luồng, không chia sẻ `Session` hoặc `Transaction` mutable của Java Driver giữa các thread; mỗi đơn vị công việc tự có session/transaction thích hợp.

## 8. Điều gì xảy ra khi có lỗi, timeout hoặc xung đột đồng thời?

| Tình huống | Kết quả cần hiểu | Cách xử lý |
| --- | --- | --- |
| Lệnh implicit đầu đã commit; lệnh implicit sau lỗi | Lệnh trước **không** rollback theo lệnh sau | Gom vào một explicit transaction khi cần all-or-nothing |
| Statement trong explicit transaction thất bại | Transaction có thể phải rollback; các thay đổi chưa commit không nên giữ lại | Xử lý exception, rollback/để managed transaction rollback |
| Callback `executeWrite` bị retry | Toàn bộ logic trong callback có thể chạy lại | Dùng logic idempotent, tránh side effect ngoài DB |
| `beginTransaction` mà quên `commit()` | Transaction bị rollback khi đóng mà chưa commit | Commit rõ ràng chỉ sau khi các kiểm tra cần thiết đạt |
| Transaction giữ lâu/khóa tranh chấp | Tăng chờ lock, deadlock, timeout hoặc ảnh hưởng throughput | Rút ngắn transaction, cập nhật theo thứ tự nhất quán, retry lỗi tạm thời |
| Nhiều writer cùng sửa cùng property | Có thể có xung đột dữ liệu hoặc lost update nếu thiết kế đọc-rồi-ghi không đúng | Dùng khóa, điều kiện phiên bản và cơ chế cập nhật phù hợp |
| Kết nối mất khi commit | Client có thể không biết chắc commit đã tới server chưa | Kiểm tra dữ liệu theo khóa nghiệp vụ/idempotency key trước khi thử lại |
| Đọc ở session khác trong cluster | Nếu không mang bookmark, lần đọc có thể chưa bảo đảm quan hệ nhân quả với lần ghi | Dùng bookmark/bookmark manager khi chuyển giữa các session |
| `CALL { ... } IN TRANSACTIONS` thất bại giữa chừng | Những batch đã commit có thể tồn tại | Kiểm tra tiến độ và chạy lại an toàn bằng khóa duy nhất |

### Isolation không thay thế kiểm soát đồng thời

Theo mức cô lập read committed mặc định, một transaction không đọc dữ liệu chưa commit của transaction khác. Tuy nhiên, khi transaction đọc giá trị ở một thời điểm rồi ghi dựa trên giá trị đó, ứng dụng vẫn cần chú ý **race condition**, thao tác khóa và phiên bản dữ liệu.

Ví dụ cập nhật có điều kiện theo phiên bản:

```cypher
MATCH (p:Project {
  id: $projectId,
  version: $expectedVersion
})
SET p.status = $newStatus,
    p.version = p.version + 1
RETURN count(p) AS updatedProjects;
```

Nếu `updatedProjects = 0`, có thể project không tồn tại **hoặc** phiên bản đã thay đổi. Không nên xem mọi kết quả 0 là lỗi mạng hoặc tự retry vô hạn. Để tránh các race condition phức tạp, cần kiểm tra cơ chế locking/optimistic locking của stack đang dùng, đặc biệt trong các nghiệp vụ có bất biến tài chính hoặc tài nguyên cạnh tranh.

## 9. Xác minh một giao dịch thực sự đã được lưu

Với nghiệp vụ cập nhật graph, nên thực hiện ba lớp kiểm tra:

1. **Truy vấn hoàn tất:** API tiêu thụ đầy đủ result; exception và lỗi transaction được xử lý. Với explicit transaction, đợi `commit()` hoặc managed transaction trả về thành công.
2. **Cập nhật hợp lý:** sử dụng `ResultSummary.counters()` nếu cần đếm node/relationship tạo, xóa, property được gán. Cần nhớ counters mô tả hoạt động của câu truy vấn, **không tự chứng minh transaction ngoài đã commit**.
3. **Trạng thái sau commit đúng:** chạy một transaction đọc mới, truy vấn đúng khóa node và quan hệ mong đợi; kiểm tra cả giá trị property và số bản ghi.

Ví dụ truy vấn xác minh sau khi tạo membership:

```cypher
OPTIONAL MATCH (u:AppUser {id: 'u-101'})
OPTIONAL MATCH (p:Project {id: 'p-01'})
OPTIONAL MATCH (u)-[m:MEMBER_OF]->(p)
RETURN count(DISTINCT u) AS users,
       count(DISTINCT p) AS projects,
       count(m) AS memberships;
```

Trên database thử nghiệm với uniqueness constraint và không có dữ liệu trùng, trạng thái mong đợi là `users = 1`, `projects = 1`, `memberships = 1`. Nếu đọc được dữ liệu ngay trong một transaction **chưa commit**, kết quả này chưa chứng minh thay đổi đã lưu lâu dài.

Khi xác minh từ session/instance khác trên Neo4j cluster, cần chú ý **causal consistency** bằng bookmark được truyền đúng, hoặc các phương thức đọc sau ghi được Driver quản lý trong cùng session.

## 10. Thực hành: chọn loại transaction theo yêu cầu

Trên database thử nghiệm, thực hiện các tình huống sau và ghi lại điểm bắt đầu/kết thúc mỗi transaction:

1. **Một lệnh độc lập:** dùng implicit transaction để `MERGE` một `AppUser`; bảo đảm tiêu thụ result và đọc lại node sau đó.
2. **Ba lệnh auto-commit:** lần lượt tạo user, tạo project và tạo membership bằng ba câu riêng. Giả lập câu thứ ba không chạy hoặc lỗi; kiểm tra node tạo từ những câu trước còn tồn tại không.
3. **Một managed transaction:** chuyển cả ba câu vào callback `executeWrite`; cố tình ném exception trước khi callback thành công, rồi đọc lại để xác minh những thay đổi mới trong transaction đã rollback. Sau đó chạy trường hợp thành công và kiểm tra membership.
4. **Một unmanaged transaction:** mở `beginTransaction()`, cập nhật một node rồi gọi `rollback()`; xác minh giá trị không bị thay đổi. Lặp lại với `commit()`.
5. **Ghi theo lô:** chạy `CALL { ... } IN TRANSACTIONS` trong implicit transaction; giải thích vì sao không đặt nó vào `executeWrite(...)` và tại sao batch đã commit vẫn có thể tồn tại khi batch sau lỗi.
6. **Spring Data Neo4j:** xác định ranh giới `@Transactional` trong một service, nêu điều kiện rollback và cách đặt kiểm tra sau commit.

Tự trả lời ba câu hỏi:

- Tại sao ba lần `session.run(...)` liên tiếp không bảo đảm cùng rollback?
- Khi nào chọn `executeWrite(...)`, khi nào chọn `beginTransaction()`, và vì sao callback của managed transaction phải an toàn khi retry?
- Vì sao kết quả `MATCH ... RETURN` trong cùng transaction không thay thế xác minh sau `commit`?

**Tiêu chí hoàn thành:** phân biệt được implicit và explicit transaction dựa trên ranh giới thực thi; chọn API đúng để tạo một nhóm cập nhật nguyên tử; biết khi nào commit/rollback xảy ra; hiểu ngoại lệ import theo lô, retry và cách xác minh dữ liệu sau commit.

## Tài liệu tham khảo chính thức

- [Neo4j Java Driver Manual — Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/): implicit, managed và unmanaged transaction; commit, rollback và retry.
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/): thực thi truy vấn, lựa chọn API và tiêu thụ kết quả.
- [Neo4j Cypher Manual — Transactions](https://neo4j.com/docs/cypher-manual/current/transactions/): ranh giới transaction, tính nguyên tử và xử lý transaction trong Cypher.
- [Neo4j Cypher Manual — CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/): chạy lệnh theo nhiều batch transaction.
- [Neo4j Java Driver Manual — Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/): đảm bảo thứ tự nhìn thấy cập nhật giữa các session trong cluster.
- [Spring Data Neo4j Reference — Transactions](https://docs.spring.io/spring-data/neo4j/reference/transactions.html): quản lý transaction khi dùng Spring Data Neo4j.
