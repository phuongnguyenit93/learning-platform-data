# Retry tự động, tính lũy đẳng và tác dụng phụ ngoài cơ sở dữ liệu

## 1. Vì sao một transaction thành công vẫn có thể bị thực thi lại?

Neo4j Java Driver cho phép chạy truy vấn Cypher qua transaction được driver quản lý. Khi gặp những lỗi tạm thời như deadlock, kết nối gián đoạn hoặc thành viên cluster không còn sẵn sàng, driver có thể **thử thực hiện lại transaction** theo chính sách retry.

Điều này rất hữu ích cho tính sẵn sàng, nhưng kéo theo một yêu cầu thiết kế: **callback của managed transaction có thể chạy nhiều lần**. Những việc thực hiện bên trong callback cần được kiểm soát tương ứng.

Giả sử API nhận yêu cầu cộng 100 điểm cho khách hàng:

~~~text
API /rewards
    |
    +-- executeWrite(callback)
            |
            +-- Cypher tăng Account.points
            +-- gọi API gửi email "Bạn được cộng 100 điểm"
            +-- trả kết quả
~~~

Nếu Neo4j yêu cầu retry sau một lỗi tạm thời, callback có thể được gọi lần nữa. Lúc đó:

- Lệnh ghi trong giao dịch đã rollback trước đó có thể được thực hiện lại và commit một lần.
- **Email đã gửi ra ngoài không thể bị Neo4j rollback**; người dùng có thể nhận hai email.
- Nếu tình trạng commit trở nên **không rõ ràng** do mất xác nhận, một lần ghi đã commit vẫn có thể bị ứng dụng hoặc người gọi thử lại, khiến một phép cộng dồn không có định danh được áp dụng thêm lần nữa.

Đây là lý do phải phân biệt ba khái niệm:

1. **Retry:** cố chạy lại một transaction/thao tác khi có lỗi phù hợp.
2. **Idempotency (tính lũy đẳng):** cùng một yêu cầu logic được nhận lại không làm tăng thêm tác dụng nghiệp vụ.
3. **External side effect (tác dụng phụ ngoài cơ sở dữ liệu):** hành động như gửi email, gọi API thanh toán, publish message hoặc ghi file xảy ra ngoài phạm vi transaction Neo4j.

Bài học thuộc chương **Java Driver** của module Neo4j, tập trung vào thiết kế ứng dụng Java sử dụng Cypher và property graph một cách an toàn trước lỗi, ghi đồng thời và các hệ thống tích hợp.

## 2. Ba cách thực thi truy vấn trong Java Driver

Java Driver cung cấp nhiều cách dùng session và transaction. Khả năng retry khác nhau tùy cách chọn.

| Cách gọi | Mô hình | Retry tự động của driver |
|---|---|---|
| `session.executeRead(work)` | Managed transaction dành cho thao tác đọc | Có cơ chế retry cho lỗi phù hợp |
| `session.executeWrite(work)` | Managed transaction dành cho thao tác ghi | Có cơ chế retry cho lỗi phù hợp |
| `session.beginTransaction()` rồi `tx.commit()` | Explicit transaction do ứng dụng điều khiển | Không tự chạy lại toàn bộ callback như managed transaction; ứng dụng tự quyết định retry |
| `session.run(cypher, params)` | Auto-commit transaction | Không dùng cơ chế retry callback của managed transaction; xử lý lỗi và truy vấn lại phải theo hợp đồng API |

Ví dụ managed write transaction:

~~~java
try (Session session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {

    String accountId = "A-100";

    String updatedId = session.executeWrite(tx ->
        tx.run("""
            MATCH (a:Account {accountId: $accountId})
            SET a.lastTouchedAt = datetime()
            RETURN a.accountId AS accountId
            """, Values.parameters("accountId", accountId))
          .single()
          .get("accountId")
          .asString()
    );
}
~~~

Trong ví dụ này, **driver chịu trách nhiệm quản lý transaction và những lần thử lại được phép**. Java callback nhận biến `tx` đại diện cho giao dịch đang thực thi trong lần thử hiện tại.

**Không được xem** callback đó là một hàm chắc chắn chỉ được gọi một lần. Với truy vấn đọc, callback cũng có thể chạy lại, vì thế việc tích lũy biến đếm toàn cục, gửi thông báo hay ghi file trong `executeRead` cũng có thể tạo tác dụng phụ lặp.

### 2.1. Hướng dẫn import trong ví dụ Java

Các ví dụ ngắn dùng API của Neo4j Java Driver với các kiểu phổ biến:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;
~~~

Với ứng dụng thật, cần cấu hình `Driver`, URI, authentication, certificate và database cho môi trường đang chạy. **Driver** thường được tạo một lần và tái sử dụng theo vòng đời ứng dụng; **Session** nên có vòng đời ngắn, không chia sẻ bừa bãi giữa nhiều thread.

### 2.2. Lý do dùng executeWrite cho ghi dữ liệu

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (u:User {userId: $userId})
        SET u.active = true
        """, Values.parameters("userId", userId)).consume();

    return null;
});
~~~

`executeWrite` thể hiện ý định ghi và có thể hỗ trợ định tuyến tới máy chủ xử lý write phù hợp trong cluster. `executeRead` nên dành cho transaction chỉ đọc; không đưa lệnh `CREATE`, `MERGE`, `SET` hoặc `DELETE` vào callback đọc.

Đối với câu truy vấn chỉ cần chạy và không dùng dữ liệu trả về, `consume()` giúp xử lý hết kết quả bên trong transaction. Nếu cần DTO, nên đọc và ánh xạ `Record` trước khi callback kết thúc, thay vì trả đối tượng `Result` còn phụ thuộc vào transaction đã đóng.

## 3. Retry tự động hoạt động thế nào?

Mô hình đơn giản:

~~~text
executeWrite(callback)
    |
    v
Bắt đầu transaction, chạy callback
    |
    +-- Commit thành công --------------------> trả kết quả
    |
    +-- Lỗi tạm thời thuộc diện retry
             |
             +-- còn trong giới hạn retry? -- có --> chạy lại callback
             |
             +-- hết giới hạn hoặc không thể retry --> ném lỗi
    |
    +-- Lỗi không thuộc diện retry ----------> ném lỗi
~~~

Java Driver có cơ chế nhận diện và phân loại một số lỗi có thể retry; chính sách thực tế phụ thuộc phiên bản driver, loại lỗi, cấu hình và trạng thái cluster.

### 3.1. Các nhóm lỗi

| Tình huống | Hướng xử lý |
|---|---|
| Deadlock hoặc lỗi transaction tạm thời được driver nhận diện | Driver có thể retry managed transaction |
| Kết nối gián đoạn hoặc thay đổi máy chủ | Driver có thể thử lại tùy lỗi và khả năng xác định trạng thái |
| Lỗi cú pháp Cypher | Sửa mã; retry cùng câu lệnh không giải quyết |
| Tham số không hợp lệ | Kiểm tra input; không retry mù |
| Vi phạm uniqueness constraint | Xem có phải yêu cầu trùng hay xung đột dữ liệu; không giả định driver tự retry |
| Không có node khớp `MATCH` | Xử lý kết quả không tìm thấy theo nghiệp vụ |
| Lỗi API/email bên ngoài | Neo4j Driver không thể tự rollback tác dụng phụ đã xảy ra |
| Kết quả commit không rõ sau timeout/mất kết nối | Dùng khóa lũy đẳng và kiểm tra lại trạng thái đã ghi |

Không bắt mọi `Exception` rồi retry vô hạn. Điều đó chỉ tăng tải cho database, kéo dài lỗi và có thể gây tác dụng phụ lặp.

### 3.2. Giới hạn thời gian retry

Managed transaction không nên retry mãi. Driver có thiết lập thời lượng retry tối đa, ví dụ `maxTransactionRetryTime` trong cấu hình Driver; cú pháp cấu hình cụ thể phụ thuộc phiên bản API đang dùng.

Trong một số phiên bản Java Driver, cấu hình có dạng:

~~~java
Config config = Config.builder()
    .withMaxTransactionRetryTime(15, java.util.concurrent.TimeUnit.SECONDS)
    .build();
~~~

Đây là **giới hạn cho quá trình retry**, không phải lời hứa mọi thao tác sẽ hoàn thành trong chính xác 15 giây. Thời gian thực tế còn phụ thuộc timeout mạng, kết nối, transaction và các tham số vận hành khác. Đối chiếu tên API/cấu hình của phiên bản driver đang sử dụng.

**Đừng thêm một vòng retry tự viết bên ngoài `executeWrite`** nếu chưa xác định nó cần xử lý loại lỗi nào mà driver chưa xử lý. Hai tầng retry không kiểm soát có thể nhân số lần thực thi và che khuất vấn đề hệ thống.

## 4. Transaction được retry khác với “hành động chỉ xảy ra đúng một lần”

Một transaction Neo4j có tính **atomicity**: những thay đổi được commit thành một đơn vị, còn transaction thất bại trước commit thì không để lại một phần thay đổi được commit.

Tuy nhiên, có hai tình huống cần xét riêng:

**Tình huống A — lỗi trước commit được xác định:** lần thử đầu rollback; callback chạy lại; chỉ lần thử sau có thể commit. Tác dụng phụ ngoài Neo4j của lần thử đầu **không tự hoàn tác**.

**Tình huống B — không rõ commit đã xảy ra hay chưa:** Neo4j có thể đã commit nhưng xác nhận bị mất trên đường về client. Caller không được quyền kết luận “chắc chắn chưa ghi” chỉ vì chưa nhận phản hồi. Việc ứng dụng hoặc cơ chế retry phát lại cùng phép cộng có nguy cơ ghi lặp.

Vì vậy, không nên gọi một phép tăng bộ đếm là “an toàn” chỉ vì nó chạy trong `executeWrite`.

### 4.1. Phép gán tuyệt đối và phép cộng dồn khác nhau

~~~cypher
// Gán lại cùng giá trị, thường lũy đẳng theo giá trị đích.
MATCH (u:User {userId: $userId})
SET u.tier = 'GOLD';
~~~

~~~cypher
// Mỗi lần chạy thành công lại cộng thêm.
MATCH (u:User {userId: $userId})
SET u.rewardPoints = coalesce(u.rewardPoints, 0) + 100;
~~~

Với phép cộng, hai lần commit sẽ cho tổng cộng **200 điểm**. Với phép gán `tier`, cùng một câu chạy lại không cộng giá trị; nhưng nếu sự kiện cũ tới sau sự kiện mới, nó vẫn có thể **ghi lùi trạng thái**. Tính lũy đẳng của một phép gán **không thay thế kiểm soát thứ tự sự kiện hoặc version**.

### 4.2. MERGE chỉ xử lý định danh của mẫu được MERGE

~~~cypher
MERGE (u:User {userId: $userId})
SET u.rewardPoints = coalesce(u.rewardPoints, 0) + 100;
~~~

`MERGE` giúp tìm hoặc tạo node User theo khóa. Nó **không biết** 100 điểm này đến từ yêu cầu nào và đã được cộng trước đó hay chưa. Nếu cùng yêu cầu chạy lại, `SET` vẫn cộng thêm.

Để chặn node User trùng khi nhiều transaction tạo đồng thời, cần constraint phù hợp trên `User.userId`. Nhưng **constraint của User** cũng chưa bảo vệ được “mỗi lệnh cộng điểm chỉ có hiệu lực một lần”.

## 5. Chọn khóa lũy đẳng cho một thao tác nghiệp vụ

Một **idempotency key** nhận diện đúng **một lệnh logic** qua các lần retry. Ví dụ:

~~~json
{
  "commandId": "reward-api:cmd-20261125-0021",
  "accountId": "A-100",
  "operation": "CREDIT_POINTS",
  "delta": 100
}
~~~

Nếu HTTP client gửi lại cùng yêu cầu do timeout, `commandId` phải **giữ nguyên**. Nếu chương trình phát sinh UUID mới mỗi lần retry, mỗi lần có thể bị coi là một lệnh hợp lệ khác.

Có thể phân biệt các loại khóa:

| Khóa | Nhận diện | Phạm vi cần lưu ý |
|---|---|---|
| `accountId` | Node Account | Một tài khoản có nhiều lệnh cộng điểm |
| `commandId` | Một lệnh cộng điểm logic | Giữ nguyên khi HTTP/API retry |
| `eventId` | Một sự kiện trong broker/outbox | Giữ nguyên khi publish/redelivery |
| `requestId` | Một yêu cầu đầu vào ở API | Chỉ dùng làm khóa nghiệp vụ nếu hợp đồng bảo đảm tính ổn định |
| `aggregateVersion` | Thứ tự phiên bản của một aggregate | Không đồng nghĩa ID duy nhất của mọi thao tác |

Nếu ID chỉ duy nhất trong từng service, hãy chọn khóa có namespace, ví dụ `source + ":" + commandId`. Nếu hệ thống đa tenant, cần xác định có đưa `tenantId` vào định danh hay không.

### 5.1. Cùng khóa nhưng payload khác

Hai request cùng `commandId` nhưng một request cộng 100, request kia cộng 1000 không nên được coi là “bản tin gửi lại hợp lệ”. Cần so **accountId, operation, delta** hoặc một payload hash chuẩn hóa để phân biệt:

- **Cùng khóa, cùng nội dung:** lệnh đã được xử lý; trả kết quả đã lưu hoặc kiểm tra trạng thái.
- **Cùng khóa, khác nội dung:** xung đột khóa, từ chối hoặc điều tra.
- **Khóa chưa thấy:** có thể thử áp dụng lệnh mới.

Lưu ý payload hash phải được tính theo biểu diễn ổn định; thứ tự trường JSON, kiểu số và chuẩn hóa chuỗi có thể làm hash khác nhau nếu không có quy ước.

## 6. Phối hợp uniqueness constraint với sổ lệnh đã áp dụng

Trong Neo4j, có thể ghi nhận mỗi command bằng một node `AppliedCommand`, đồng thời thay đổi node `Account` trong **cùng transaction**.

Mô hình:

~~~text
(:AppliedCommand {
  commandId, accountId, delta, appliedAt, resultPoints
})
        |
    [:APPLIED_TO]
        |
        v
(:Account {accountId, rewardPoints})
~~~

Constraint:

~~~cypher
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account)
REQUIRE a.accountId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT applied_command_id_unique IF NOT EXISTS
FOR (c:AppliedCommand)
REQUIRE c.commandId IS UNIQUE;
~~~

Một constraint bảo vệ định danh **Account**; constraint còn lại bảo vệ **một lần áp dụng của mỗi commandId**. Các constraint phải được thiết lập trước khi xử lý ghi đồng thời. Nếu đã có dữ liệu trùng, câu tạo constraint có thể thất bại và cần dọn dữ liệu theo quy tắc nghiệp vụ.

### 6.1. Câu Cypher áp dụng lệnh mới đúng một lần

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
SET cmd.resultPoints = a.rewardPoints
CREATE (cmd)-[:APPLIED_TO]->(a)
RETURN cmd.commandId AS commandId,
       cmd.resultPoints AS resultPoints;
~~~

Điểm cần hiểu:

1. `MATCH` yêu cầu Account đã tồn tại. Nếu không có Account, câu lệnh trả **0 hàng**; ứng dụng phải xử lý “không tìm thấy”.
2. `CREATE AppliedCommand` tạo receipt cho một lệnh mới, với `commandId` được bảo vệ bằng uniqueness constraint.
3. `SET` cập nhật điểm tài khoản và ghi lại kết quả tại receipt.
4. `CREATE relationship` nối receipt tới Account để truy vết.
5. Receipt, thay đổi điểm và relationship đều được commit **nguyên tử** trong cùng Neo4j transaction.

Nếu hai worker đồng thời xử lý cùng `commandId`, **không thể commit hai node AppliedCommand trùng khóa** khi constraint còn hiệu lực. Một worker có thể hoàn thành, worker còn lại gặp tranh chấp hoặc lỗi uniqueness. Nếu một transaction thất bại, cập nhật điểm và receipt trong transaction đó cũng rollback.

**Điều kiện để đúng:** tất cả đường ghi có thể làm thay đổi `rewardPoints` theo command đều phải tuân theo cơ chế này; không được có worker khác cộng điểm trực tiếp rồi bỏ qua receipt. Constraint bảo vệ bất biến đã định nghĩa, không tự bảo vệ những luồng ghi không tuân thủ hợp đồng.

### 6.2. Không đặt phép cộng sau MERGE receipt một cách vô điều kiện

Ví dụ **sai**:

~~~cypher
MERGE (cmd:AppliedCommand {commandId: $commandId})
WITH cmd
MATCH (a:Account {accountId: $accountId})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta;
~~~

Dù `MERGE` khớp node AppliedCommand cũ, câu `SET` vẫn chạy. MERGE không tự tạo một nhánh “đã xử lý thì bỏ qua mọi câu tiếp theo”.

Dùng `CREATE` receipt có constraint như ví dụ 6.1 giúp biểu đạt rõ rằng **phải tạo được receipt mới** thì command mới được áp dụng. Nếu chọn MERGE, cần một cơ chế phân biệt chính xác receipt **vừa tạo trong lần transaction hiện tại** và chỉ cập nhật nghiệp vụ trong trường hợp đó; không dựa vào cảm giác “MERGE = lũy đẳng”.

### 6.3. Đọc lại receipt sau một lỗi không rõ kết quả

~~~cypher
MATCH (cmd:AppliedCommand {commandId: $commandId})
RETURN cmd.accountId AS accountId,
       cmd.delta AS delta,
       cmd.resultPoints AS resultPoints,
       cmd.appliedAt AS appliedAt;
~~~

Nếu receipt tồn tại và trường nghiệp vụ khớp command đang xử lý, ứng dụng có thể trả về **kết quả đã áp dụng** mà không tăng điểm lần nữa.

Nếu receipt tồn tại nhưng `accountId` hoặc `delta` khác, đó là **xung đột** chứ không phải duplicate an toàn. Nếu không có receipt, cần phân biệt transaction thực sự chưa commit với lỗi đọc/tính nhất quán của lần kiểm tra; không tự động phán đoán trong mọi trường hợp.

## 7. Java Driver: callback ghi chỉ làm việc với Neo4j

Ví dụ dưới đây minh họa nhánh **áp dụng command mới** bằng một managed transaction. Nó giả định các constraint ở mục 6 đã có sẵn, input hợp lệ và Account tồn tại.

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class RewardCommandWriter {
    public record AppliedReward(String commandId, long resultPoints) {}

    private final Driver driver;

    public RewardCommandWriter(Driver driver) {
        this.driver = driver;
    }

    public AppliedReward creditPoints(
            String commandId, String accountId, long delta) {
        if (commandId == null || commandId.isBlank()
                || accountId == null || accountId.isBlank()
                || delta <= 0) {
            throw new IllegalArgumentException("Invalid reward command");
        }

        String cypher = """
            MATCH (a:Account {accountId: $accountId})
            CREATE (cmd:AppliedCommand {
                commandId: $commandId,
                accountId: $accountId,
                delta: $delta,
                appliedAt: datetime()
            })
            SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
            SET cmd.resultPoints = a.rewardPoints
            CREATE (cmd)-[:APPLIED_TO]->(a)
            RETURN cmd.commandId AS commandId,
                   cmd.resultPoints AS resultPoints
            """;

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                Result result = tx.run(cypher, Map.of(
                    "commandId", commandId,
                    "accountId", accountId,
                    "delta", delta
                ));

                if (!result.hasNext()) {
                    throw new IllegalStateException(
                        "Account was not found: " + accountId
                    );
                }

                var row = result.single();
                return new AppliedReward(
                    row.get("commandId").asString(),
                    row.get("resultPoints").asLong()
                );
            });
        }
    }
}
~~~

**Lưu ý về ví dụ:**

- `commandId` được truyền **từ caller**, tạo một lần trước các lần retry; không phát sinh bên trong callback.
- Cypher dùng parameter, không ghép chuỗi dữ liệu từ request.
- Callback trả DTO giá trị thuần sau khi đã đọc kết quả, không đưa `Result` hoặc `TransactionContext` ra ngoài.
- Không gửi email, gọi REST, publish event hay ghi một hệ thống khác trong callback.
- Vi phạm constraint khi command đã được xử lý trước đó **chưa được xử lý thành kết quả duplicate trong đoạn code này**; application service phải có bước phục hồi theo mục 7.1.

### 7.1. Chiến lược phục hồi sau kết quả trùng hoặc không rõ commit

Thiết kế luồng gọi `creditPoints(...)`:

~~~text
Nhận (commandId, accountId, delta)
    |
    v
Thử creditPoints qua managed transaction
    |
    +-- Commit và trả AppliedReward --------> trả thành công
    |
    +-- Lỗi có thể do command đã áp dụng
    |       |
    |       +-- Đọc AppliedCommand theo commandId
    |               |
    |               +-- Có receipt, nội dung khớp --> trả kết quả đã lưu
    |               +-- Có receipt, nội dung khác --> lỗi xung đột
    |               +-- Không thấy receipt -------> phân loại lỗi ban đầu/retry
    |
    +-- Lỗi khác ---------------------------> xử lý theo loại lỗi
~~~

Không nên bắt **mọi exception** rồi tra receipt và tự coi thành công, vì một lỗi không liên quan như quyền truy cập, syntax, cấu hình cluster hoặc constraint khác cần được báo chính xác.

Với lỗi uniqueness, cần xác định **constraint nào** bị vi phạm. Với mất xác nhận commit, có thể cần đọc qua phiên mới với định tuyến và tính nhất quán phù hợp. Trong cluster, bookmark/session consistency và lựa chọn database có thể ảnh hưởng việc đọc ngay sau ghi; không coi truy vấn đọc tùy ý từ một replica trễ là bằng chứng chắc chắn receipt chưa tồn tại.

### 7.2. Vì sao không tạo UUID trong executeWrite?

Phản ví dụ:

~~~java
session.executeWrite(tx -> {
    String commandId = java.util.UUID.randomUUID().toString();
    tx.run("""
        CREATE (:AppliedCommand {commandId: $commandId})
        """, Map.of("commandId", commandId)).consume();
    return null;
});
~~~

Nếu callback chạy lại, UUID mới sẽ được tạo. Uniqueness constraint trên `commandId` không giúp nhận diện đây là **cùng một command logic**, vì lần retry dùng một khóa khác.

**Sửa:** tạo commandId ở ranh giới nhận yêu cầu và lưu/truyền nó ổn định qua retry:

~~~java
String commandId = request.commandId(); // do bên gọi cung cấp ổn định
session.executeWrite(tx -> {
    tx.run("""
        CREATE (:AppliedCommand {commandId: $commandId})
        """, Map.of("commandId", commandId)).consume();
    return null;
});
~~~

Đây là ví dụ đơn giản về vòng đời ID; đoạn CREATE rút gọn không thay thế mẫu receipt + cập nhật nghiệp vụ ở phần trước.

### 7.3. Chú ý mọi nguồn không xác định trong callback

Các biểu thức sau dễ tạo kết quả khác nhau giữa các lần thử:

- `UUID.randomUUID()` dùng làm định danh lệnh.
- Gọi API bên ngoài để lấy dữ liệu thay đổi liên tục.
- Đọc/ghi biến mutable được chia sẻ giữa thread.
- Tăng một bộ đếm ở RAM để thống kê “số lệnh đã xử lý”.
- Gọi `System.currentTimeMillis()` để quyết định logic duy nhất của command.
- Phát sự kiện sang broker hoặc gửi thông báo.

Nếu metadata thời gian cần lưu, xác định nó là **thời điểm xử lý từng lần thử** hay **thời điểm của command**. Ví dụ `datetime()` trong Cypher có thể phản ánh thời gian của lần thực thi thành công; còn thời điểm xảy ra thao tác có thể nên lấy từ payload ổn định do producer cung cấp.

Một callback có thể log debug nhiều lần mà không gây sai dữ liệu nghiệp vụ, nhưng khi dùng log/metric để tính “số command thành công”, cần đặt phép đo ở nơi phản ánh **commit hoặc receipt đã xác nhận**, tránh đếm nhầm những lần thử thất bại.

## 8. Tác dụng phụ ngoài cơ sở dữ liệu: vì sao callback nguy hiểm?

### 8.1. Gửi email bên trong transaction

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (a:Account {accountId: $accountId})
        SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
        """, parameters).consume();

    emailClient.sendRewardEmail(accountId, delta); // Tác dụng phụ ngoài Neo4j
    return null;
});
~~~

Nếu transaction sau đó rollback, email vẫn có thể đã gửi. Nếu callback được retry, email có thể được gửi lần nữa. Neo4j không có cách tự động rollback một SMTP server đã nhận email.

### 8.2. Gửi email sau executeWrite có đủ chưa?

~~~java
AppliedReward result = rewardWriter.creditPoints(
    commandId, accountId, delta
);
emailClient.sendRewardEmail(accountId, delta);
~~~

Cách này **tốt hơn việc gửi trong callback** vì email chỉ được gọi sau khi phương thức xác nhận giao dịch thành công. Nhưng vẫn còn hai tình huống:

- **Crash sau DB commit, trước khi gửi email:** dữ liệu điểm đã cập nhật nhưng email chưa gửi.
- **Gửi email thành công, rồi mất phản hồi hoặc crash trước khi ghi “đã gửi”:** một lần retry có thể gửi email thứ hai.

Đây là vấn đề **dual write** giữa Neo4j và một hệ thống không cùng transaction. Việc chuyển lệnh gửi ra sau callback giảm nguy cơ lặp do retry nội bộ, nhưng chưa bảo đảm phát thông báo đúng một lần hay không bao giờ mất.

### 8.3. Các tác dụng phụ khác cần xem xét

| Hành động | Rủi ro khi callback chạy lại |
|---|---|
| Email/SMS | Thông báo trùng, người dùng hiểu nhầm |
| Gọi API thanh toán | Có nguy cơ thu phí/giao dịch lặp nếu API không hỗ trợ idempotency |
| Publish Kafka/RabbitMQ | Phát lại event dù Neo4j transaction rollback |
| Ghi file hoặc object storage | File đè nhau, sinh nhiều object, khó rollback |
| Ghi cache | Cache phản ánh trạng thái chưa commit hoặc quá cũ |
| Gọi service phân phối hàng | Tạo hai yêu cầu giao hàng |
| Ghi chỉ số business | Đếm số giao dịch thành công cao hơn thực tế |

Tách riêng trách nhiệm **ghi dữ liệu có giao dịch** và **phát tác dụng phụ ra thế giới bên ngoài**. Những hành động bất biến được đưa vào callback nên giới hạn ở các thay đổi Neo4j có cơ chế chống lặp phù hợp.

## 9. Transactional outbox: ghi ý định phát sự kiện cùng dữ liệu

**Transactional outbox** là cách xử lý phổ biến để tránh mất thông điệp giữa việc commit cơ sở dữ liệu và việc gửi ra broker.

Ý tưởng:

1. Trong **cùng transaction Neo4j**, cập nhật Account, tạo AppliedCommand và tạo một node **OutboxEvent** ghi ý định phát thông báo.
2. Commit toàn bộ.
3. Một **dispatcher riêng** tìm những OutboxEvent chưa gửi, gọi broker/email service, sau đó đánh dấu tiến độ.
4. Dispatcher có thể retry; hệ thống nhận thông điệp cần hỗ trợ idempotency.

Mô hình minh họa:

~~~text
(:AppliedCommand {commandId})
    |
    +--[:APPLIED_TO]-->(:Account {rewardPoints})
    |
    +--[:EMITTED]---->(:OutboxEvent {
                           eventKey, eventType, status,
                           accountId, delta, createdAt
                       })
~~~

Tạo constraint cho outbox:

~~~cypher
CREATE CONSTRAINT outbox_event_key_unique IF NOT EXISTS
FOR (e:OutboxEvent)
REQUIRE e.eventKey IS UNIQUE;
~~~

Chọn eventKey ổn định từ commandId, ví dụ `eventKey = commandId + ":reward-applied"`. Chuỗi này được xây **trước transaction**, để retry cùng command không sinh event mới.

### 9.1. Tạo outbox trong cùng transaction cập nhật

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + $delta
SET cmd.resultPoints = a.rewardPoints
CREATE (cmd)-[:APPLIED_TO]->(a)
CREATE (outbox:OutboxEvent {
    eventKey: $eventKey,
    eventType: 'RewardPointsCredited',
    status: 'PENDING',
    accountId: $accountId,
    delta: $delta,
    createdAt: datetime()
})
CREATE (cmd)-[:EMITTED]->(outbox)
RETURN cmd.resultPoints AS resultPoints,
       outbox.eventKey AS eventKey;
~~~

Đoạn này là **một transaction trong Neo4j**. Nếu transaction rollback, không có update điểm, receipt hoặc outbox nào commit. Nếu commit, có cả dữ liệu nghiệp vụ và ý định gửi.

**Giới hạn:** transaction Neo4j chỉ bảo đảm các thay đổi **bên trong Neo4j**. Nó không làm broker hoặc email service tham gia vào cùng transaction.

### 9.2. Dispatcher có thể gửi trùng

Giả sử:

~~~text
Dispatcher đọc OutboxEvent PENDING
    |
    +-- publish tới broker thành công
    |
    X crash trước khi đánh dấu SENT
    |
Dispatcher khởi động lại, thấy vẫn PENDING
    |
    +-- publish lại cùng eventKey
~~~

Đây là lý do outbox thường cung cấp **ít nhất một lần giao**, không tự bảo đảm người nhận thấy chính xác một lần. Consumer nên dùng `eventKey` để chống áp dụng trùng. Với email/SMS, có thể cần idempotency key được nhà cung cấp hỗ trợ hoặc một hệ thống dispatch/receipt riêng.

Trong môi trường nhiều dispatcher, phải thiết kế **claim/lease/lock** và quy tắc cập nhật trạng thái để hai worker không đồng thời lấy cùng một outbox. Chỉ dùng:

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e LIMIT 10;
~~~

không thể xem là đã “claim độc quyền” các event. Truy vấn đọc không tự khóa chúng cho một dispatcher duy nhất. Việc claim, timeout, giải phóng lease và xử lý worker crash cần được thiết kế thành một quy trình riêng.

### 9.3. Outbox nên chứa gì?

Một bản ghi outbox thường cần:

- `eventKey` ổn định và duy nhất.
- `eventType` và phiên bản schema.
- Khóa aggregate, ví dụ `accountId`.
- Payload cần gửi hoặc thông tin đủ để tái dựng payload một cách ổn định.
- `createdAt`, trạng thái/tiến độ phát, số lần thử.
- Metadata hỗ trợ tracing và chẩn đoán lỗi.

Không nên chỉ ghi `status = 'PENDING'` rồi để dispatcher đọc lại **trạng thái Account hiện tại** và giả định đó là trạng thái đúng vào lúc phát sinh event. Account có thể đã được cập nhật thêm giữa thời điểm commit và dispatch. Nếu event mô tả một thay đổi cụ thể, payload cần giữ **snapshot của thay đổi đó** hoặc version tương ứng.

## 10. Khi nào cần idempotency ở phía dịch vụ bên ngoài?

Ngay cả khi Neo4j đã có AppliedCommand và OutboxEvent, downstream còn có thể bị gọi lặp.

### 10.1. API thanh toán

Một nhà cung cấp thanh toán có hỗ trợ idempotency key có thể cho phép ứng dụng gửi lại **cùng một payment operation** mà không tạo hai giao dịch thanh toán. Khi đó, key truyền cho bên ngoài phải là khóa ổn định của **một lần thu phí logic**, không phải UUID mới ở mỗi lần retry.

Cần đọc hợp đồng nhà cung cấp: phạm vi key, thời gian lưu, hành vi khi payload khác nhưng key trùng và tình trạng kết quả không xác định. Không mặc định mọi API thanh toán đều có cơ chế tương tự.

### 10.2. Email và thông báo

Một số dịch vụ email không cung cấp chống trùng tuyệt đối ở cấp yêu cầu. Có thể dùng sổ dispatch trong hệ thống của mình và idempotency/correlation key để hạn chế gửi trùng, nhưng sự cố giữa “dịch vụ đã chấp nhận gửi” và “đã lưu kết quả” vẫn là ranh giới cần được nhận thức.

Yêu cầu sản phẩm cần phân biệt:

- **Ít nhất một thông báo cuối cùng được gửi** (chấp nhận khả năng trùng).
- **Tránh gửi trùng tối đa** (có thể chấp nhận một số tình huống chưa gửi khi không xác định).
- **Chính xác một tác dụng nghiệp vụ** (thường cần hợp đồng/idempotency từ hệ thống đích).

Không hứa “exactly once email” chỉ vì dùng transaction Neo4j.

## 11. Retry, uniqueness và concurrency khi hai request cùng commandId

Hãy xét hai thread Java đồng thời nhận cùng commandId `cmd-77`.

~~~text
Thread A                    Neo4j                  Thread B
    |                          |                        |
    |-- CREATE AppliedCommand ->|<- CREATE AppliedCommand|
    |                          |                        |
    |            constraint: commandId duy nhất         |
    |                          |                        |
    |     tối đa một transaction có receipt commit      |
    |     transaction còn lại xử lý conflict/error      |
~~~

Uniqueness constraint cho `AppliedCommand.commandId` bảo đảm **không có hai receipt cùng khóa được commit**. Vì cập nhật điểm nằm trong transaction tạo receipt, các transaction xử lý cùng khóa không thể cùng commit thay đổi điểm theo mẫu đã thiết kế.

Trong thực tế, thread thua có thể chờ hoặc nhận lỗi khác nhau tùy kế hoạch và lịch thực thi. Ứng dụng phải phân loại kết quả rồi **đọc receipt ở phiên/giao dịch mới** để xác nhận lệnh đã được xử lý trước đó.

Không khẳng định rằng mọi request cạnh tranh đều **thành công lần đầu**. Điều bất biến được bảo vệ là **không áp dụng trùng theo khóa đã định nghĩa**.

### 11.1. Với những thay đổi nhiều node

Một command chuyển 50 điểm từ A sang B cần cập nhật hai node và lưu receipt trong **cùng transaction**, đồng thời kiểm tra số dư và xử lý cạnh tranh cập nhật. Receipt chống **cùng command bị áp dụng hai lần**; nó không tự giải quyết mọi điều kiện như **không cho số dư âm**, **khóa nhiều tài khoản** hoặc **deadlock**.

Khi hai transaction chạm các Account theo thứ tự khác nhau, có thể xảy ra deadlock. Driver có thể retry lỗi transient phù hợp; thiết kế transaction cần ngắn gọn và tránh tác dụng phụ bên ngoài callback.

## 12. Sự kiện gửi lại và thứ tự cập nhật không phải một vấn đề

Giả sử hai event cho cùng Account:

~~~text
E-41: status = ACTIVE,  version = 41
E-42: status = SUSPENDED, version = 42
~~~

Nếu E-42 đã commit rồi E-41 mới được gửi lại, chỉ kiểm tra eventId/receipt chưa chắc ngăn được cập nhật ngược nếu E-41 chưa từng được xử lý. Cần xét `version`.

- **Snapshot đầy đủ:** có thể bỏ qua event version thấp hơn phiên bản đã áp dụng, theo hợp đồng nguồn.
- **Delta phụ thuộc lịch sử:** có thể phải xử lý đủ các version theo thứ tự; không được bỏ qua một delta chưa áp dụng chỉ vì gặp version mới hơn.

Đừng biến `occurredAt` thành quy tắc thứ tự duy nhất khi nguồn có nhiều máy chủ, clock lệch hoặc replay. Nếu nghiệp vụ yêu cầu thứ tự, chọn sequence/version của **cùng aggregate** hoặc cơ chế điều phối phù hợp.

Idempotency key trả lời **“đã xử lý chính thao tác này chưa?”**; version trả lời **“thao tác này đang ở đâu trong tiến trình trạng thái?”**. Hai thứ phối hợp chứ không thay thế nhau.

## 13. Spring Data Neo4j và phạm vi của @Transactional

Với Spring Data Neo4j, service có thể dùng annotation `@Transactional` để gom các thao tác repository/`Neo4jClient` trong transaction do Spring quản lý.

Tuy nhiên:

- `@Transactional` **không tự bảo đảm callback được chạy lại như `Session.executeWrite`**. Nếu cần retry, phải hiểu cấu hình Spring transaction manager, cơ chế retry bên ngoài (nếu có) và nhóm lỗi retry.
- Retry của Spring hoặc tầng HTTP có thể gọi lại **toàn bộ phương thức service**, nên idempotency key và outbox vẫn cần thiết.
- `repository.save(entity)` không tự sinh ra receipt chống trùng command.
- Một Spring transaction quản lý Neo4j **không mặc nhiên commit nguyên tử** với SQL database, broker, email hoặc API thanh toán.
- Đừng gọi trực tiếp Java Driver managed transaction lồng tùy tiện trong một transaction Spring đang hoạt động nếu chưa hiểu cách chia sẻ session và phạm vi giao dịch.

Khi ứng dụng dùng nhiều data store, hãy mô tả rõ **transaction manager** của từng hệ thống, ranh giới commit và đường phát event. Đây là phần thiết kế tích hợp, không thể giải quyết bằng một annotation duy nhất.

## 14. Theo dõi và phân tích các lần retry

Một pipeline có thể cho kết quả cuối cùng đúng mà vẫn bị contention hoặc retry quá nhiều, làm tăng độ trễ.

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Số command đầu vào theo commandId phân biệt | Tải nghiệp vụ thực |
| Số lần callback/transaction attempt | Cho biết mức retry và tranh chấp |
| Số receipt tạo mới | Số command thực sự áp dụng |
| Số duplicate xác nhận | Tỷ lệ gửi lại hoặc retry ở tầng gọi |
| Số conflict cùng key khác payload | Lỗi hợp đồng idempotency |
| Số transient error/deadlock/timeout | Áp lực giao dịch và kết nối |
| Outbox pending lâu nhất | Ý định phát chưa được hoàn tất |
| Số lần publish so với eventKey phân biệt | Tỷ lệ phát lại từ dispatcher |
| Độ trễ từ commit đến dispatch | Chất lượng xử lý eventual delivery |
| Số lần downstream nhận duplicate | Kiểm tra cơ chế lũy đẳng đầu cuối |

Không tính metric “số lệnh thành công” chỉ bằng số lần gọi callback: một callback có thể chạy lại dù cùng commandId. Để đối soát, hãy dựa vào receipt và commit được xác nhận.

### 14.1. Truy vấn kiểm tra receipt

~~~cypher
MATCH (cmd:AppliedCommand {commandId: $commandId})
RETURN cmd.accountId AS accountId,
       cmd.delta AS delta,
       cmd.resultPoints AS resultPoints,
       cmd.appliedAt AS appliedAt;
~~~

~~~cypher
MATCH (cmd:AppliedCommand)
WITH cmd.commandId AS commandId, count(cmd) AS occurrences
WHERE occurrences > 1
RETURN commandId, occurrences
LIMIT 20;
~~~

Với uniqueness constraint hoạt động đúng và giá trị commandId được cung cấp, không thể có hai node AppliedCommand đã commit cùng khóa. Nếu thấy trường hợp bất thường, cần kiểm tra lại database/schema/nhãn/property hoặc quy trình tạo dữ liệu.

### 14.2. Kiểm tra outbox pending

~~~cypher
MATCH (e:OutboxEvent {status: 'PENDING'})
RETURN e.eventKey AS eventKey,
       e.eventType AS eventType,
       e.createdAt AS createdAt
ORDER BY createdAt ASC
LIMIT 50;
~~~

Đây là truy vấn **quan sát**. Nó chưa claim event cho một worker và không giải quyết đồng thời giữa nhiều dispatcher.

## 15. Kiểm thử các tình huống lỗi có chủ đích

Nên thử trong **database riêng** với constraint như môi trường thật. Chọn một Account có `rewardPoints = 0` và một command cộng 100 điểm.

| Kịch bản | Cách mô phỏng | Kết quả kỳ vọng |
|---|---|---|
| Command mới | Gửi `cmd-1` một lần | Có 1 receipt, cộng 100 |
| HTTP retry cùng command | Gửi lại `cmd-1` | Không cộng lần thứ hai; phát hiện duplicate |
| Hai thread cùng command | Chạy song song `cmd-2` | Tối đa một cập nhật commit theo key |
| Key trùng, delta khác | Gửi `cmd-1` với delta 900 | Xung đột, không cộng thêm |
| Lỗi transient trước commit | Ép rollback một lần thử | Callback có thể chạy lại; không email trùng |
| Commit thành công, mất phản hồi | Mô phỏng mất kết nối sau commit | Đọc receipt xác định kết quả, không cộng lại |
| Crash sau commit, trước publish | Outbox còn PENDING | Dispatcher tiếp tục gửi được |
| Crash sau publish, trước SENT | Dispatcher gửi lại | Consumer/downstream phải xử lý duplicate |
| Account không tồn tại | Dùng khóa sai | Không tạo receipt giả; trả lỗi |
| Hai command khác nhau | `cmd-3` và `cmd-4` | Mỗi command được áp dụng một lần |
| Receipt hết hạn nhưng request cũ quay lại | Replay sau retention | Không được áp dụng nhầm nếu nghiệp vụ yêu cầu exactly-once effect |

### 15.1. Kiểm tra giá trị, không chỉ kiểm tra response

Sau hai lần gửi cùng commandId, đối chiếu:

~~~cypher
MATCH (a:Account {accountId: $accountId})
OPTIONAL MATCH (cmd:AppliedCommand {commandId: $commandId})
RETURN a.rewardPoints AS points,
       count(cmd) AS receipts;
~~~

Nếu dữ liệu thử ban đầu là 0, command hợp lệ cộng 100 và không có cập nhật khác, kết quả mong muốn là **points = 100**, **receipts = 1**.

**Chú ý:** Query trên chỉ kiểm tra sự hiện diện receipt cùng key, không chứng minh receipt thuộc đúng Account nếu không so `cmd.accountId` hoặc relationship `APPLIED_TO`. Khi xác minh nghiệp vụ, phải kiểm tra cả khóa đối tượng, payload và thay đổi thực tế.

### 15.2. Kiểm tra callback chạy nhiều lần

Dùng test double/điều kiện thử để gây một lỗi retry phù hợp trước commit, rồi đo:

- Số lần callback được gọi.
- Số receipt cuối cùng tồn tại.
- Giá trị điểm cuối cùng.
- Số lần gọi email hoặc publish message từ luồng chuẩn.

Kết quả đúng là **không có external side effect trong callback**; dispatcher riêng có thể phát lại nhưng nhận diện bằng eventKey. Không dùng một test chỉ chạy tuần tự để kết luận mô hình an toàn khi có nhiều worker.

## 16. Các ngộ nhận thường gặp

**“executeWrite chạy callback đúng một lần.”** Sai. Callback của managed transaction có thể bị gọi lại khi driver retry lỗi phù hợp.

**“Transaction rollback cũng hoàn tác email hoặc thanh toán.”** Sai. Neo4j chỉ rollback các thay đổi thuộc phạm vi transaction của chính nó.

**“Có MERGE node thì cộng điểm lặp không nguy hiểm.”** Sai. MERGE không nhận biết lệnh cộng 100 đã được thực hiện hay chưa.

**“UUID được tạo trong callback là idempotency key tốt.”** Không. Retry tạo UUID mới khiến các lần thử không cùng định danh nghiệp vụ.

**“Mọi lỗi uniqueness đều là duplicate an toàn.”** Sai. Có thể vi phạm constraint khác hoặc cùng khóa mang payload mâu thuẫn.

**“Gửi email ngay sau commit là chính xác một lần.”** Chưa đủ. Crash trước/sau gửi có thể làm mất hoặc gửi trùng; cần outbox và cơ chế chống lặp của bên nhận theo yêu cầu.

**“Outbox làm broker chỉ nhận một event duy nhất.”** Không. Dispatcher có thể publish lại sau crash. Outbox bảo đảm ý định phát không mất cùng transaction; consumer vẫn cần lũy đẳng.

**“Không trả success nghĩa là database chắc chắn chưa commit.”** Sai. Lỗi kết nối có thể làm mất xác nhận trong khi commit đã diễn ra.

**“Có receipt thì không cần version.”** Không. Receipt chống cùng command lặp; version bảo vệ quy tắc thứ tự cập nhật.

**“@Transactional của Spring thay thế tất cả những cơ chế trên.”** Không. Một annotation không tự giao dịch xuyên Neo4j, broker, email, SQL và HTTP service.

**“Retry mọi exception vô hạn sẽ tăng độ tin cậy.”** Không. Lỗi dữ liệu bền vững không biến mất nhờ retry; quá nhiều retry gây tải và làm chậm xử lý.

## 17. Bài tập vận dụng

### Bài 1. Email trong callback

Đoạn code:

~~~java
session.executeWrite(tx -> {
    tx.run("""
        MATCH (a:Account {accountId: $accountId})
        SET a.active = true
        """, parameters).consume();
    mailer.send("Đã cập nhật"); 
    return null;
});
~~~

**Câu hỏi:** Vì sao có thể gửi nhiều email dù transaction cuối cùng chỉ commit một lần?

**Đáp án:** Callback được chạy lại khi có lỗi retry phù hợp, trong khi email là tác dụng phụ ngoài Neo4j, không rollback được. Chuyển ý định gửi vào outbox cùng transaction và để dispatcher gửi sau commit.

### Bài 2. Tạo UUID sai chỗ

Một worker phát sinh `UUID.randomUUID()` bên trong callback rồi dùng ID đó cho AppliedCommand.

**Câu hỏi:** Vì sao uniqueness constraint không tự chống cùng lệnh chạy lại?

**Đáp án:** Mỗi lần retry có UUID mới; constraint không nhìn thấy hai lần là cùng khóa. Command ID phải ổn định trước lần thử đầu tiên.

### Bài 3. MERGE Account nhưng cộng hai lần

Ứng dụng nhận `commandId = C5` hai lần. Mỗi lần chạy:

~~~cypher
MERGE (a:Account {accountId: 'A100'})
SET a.rewardPoints = coalesce(a.rewardPoints, 0) + 100;
~~~

**Câu hỏi:** Account có thể tăng tổng cộng bao nhiêu?

**Đáp án:** Có thể tăng 200 nếu cả hai lần commit. MERGE Account không ghi nhớ C5 đã được áp dụng. Cần receipt/constraint theo commandId và ghi receipt cùng cập nhật điểm trong một transaction.

### Bài 4. Outbox và crash

Dispatcher publish event thành công, sau đó crash trước khi đánh dấu SENT.

**Câu hỏi:** Lần chạy sau có thể publish lại không, và cần làm gì?

**Đáp án:** Có. Giữ eventKey ổn định, consumer/downstream chống xử lý lặp hoặc gọi dịch vụ đích có idempotency. Dispatcher cũng cần cơ chế claim/lease nếu có nhiều worker.

### Bài 5. Mất xác nhận commit

Caller gặp timeout nhưng database có thể đã commit `cmd-77`.

**Câu hỏi:** Có nên tạo commandId mới để chạy lại cho chắc?

**Đáp án:** Không. Phải kiểm tra receipt theo commandId cũ và payload, rồi xác định trạng thái áp dụng trước khi quyết định retry. CommandId mới biến một thao tác thành hai thao tác khác nhau.

### Bài 6. Sự kiện cũ đến muộn

Event version 12 có status PAID đến sau event version 13 có status SHIPPED.

**Câu hỏi:** Nếu hai event có eventId khác nhau, receipt đã đủ tránh ghi lùi không?

**Đáp án:** Chưa. Cần kiểm soát version/thứ tự theo hợp đồng nguồn; idempotency chỉ xử lý sự kiện logic đã áp dụng trước đó.

### Bài 7. Nên dùng executeRead hay executeWrite?

Bạn cần tìm 20 đơn gần nhất của một khách hàng mà không sửa dữ liệu.

**Câu hỏi:** Nên dùng API nào và callback có thể chạy lại không?

**Đáp án:** Dùng `executeRead` với Cypher đọc. Callback đọc vẫn có thể được retry; tránh tác dụng phụ ngoài DB trong callback.

### Bài 8. Hai command hợp lệ khác nhau

`cmd-11` và `cmd-12` cùng cộng 100 điểm cho một tài khoản.

**Câu hỏi:** Có nên coi chúng là duplicate chỉ vì cùng accountId và delta?

**Đáp án:** Không nếu chúng là hai lệnh nghiệp vụ độc lập. Idempotency key phân biệt từng command; nếu cả hai hợp lệ và commit, tổng cộng 200 là đúng. Không dùng payload giống nhau làm bằng chứng duy nhất rằng đó là một lệnh.

## 18. Ghi nhớ

Trong Neo4j Java Driver, **`executeRead` và `executeWrite` có thể tự retry managed transaction**, nên callback phải được thiết kế như một đơn vị có thể **thực thi lại**. Transaction chỉ kiểm soát dữ liệu trong Neo4j; email, thanh toán, publish message hoặc file bên ngoài không được rollback cùng nó.

Đối với thao tác **cộng dồn hoặc tạo hiệu ứng chỉ một lần**, dùng **commandId/eventId ổn định**, uniqueness constraint và receipt được ghi **nguyên tử cùng cập nhật nghiệp vụ**. Khi gặp lỗi hoặc mất xác nhận commit, **tra receipt và so payload** trước khi retry, tránh tự tạo ID mới. Nếu cần phát sự kiện ra hệ thống khác, cân nhắc **transactional outbox**, dispatcher và idempotency ở phía nhận. Kết hợp phân loại lỗi, retry có giới hạn, kiểm soát thứ tự và kiểm thử concurrency giúp Java Driver hoạt động đúng khi hệ thống gặp sự cố thực tế.
