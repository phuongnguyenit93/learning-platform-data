# Khóa khi cập nhật nút, quan hệ và thuộc tính

## 1. Tại sao cần khóa trong giao dịch Neo4j?

Trong Neo4j, mô hình **property graph** gồm **node (nút)**, **relationship (quan hệ)** và **property (thuộc tính)**. Một ứng dụng có thể đồng thời nhận nhiều yêu cầu đổi tên khách hàng, cập nhật trạng thái đơn hàng, ghi thêm quan hệ theo dõi hoặc tăng bộ đếm. Nếu hai giao dịch ghi lên cùng phần dữ liệu mà không có cơ chế điều phối, kết quả có thể sai hoặc không nhất quán.

**Khóa (lock)** là một trong những cơ chế Neo4j dùng để điều phối truy cập đồng thời. Khi giao dịch thay đổi node hoặc relationship, Neo4j tự động lấy các khóa cần thiết để ngăn những thao tác ghi xung đột diễn ra không an toàn. Khóa cũng ảnh hưởng đến thời gian chờ, độ trễ và nguy cơ deadlock.

Ví dụ hai giao dịch cùng tăng bộ đếm lượt xem:

- Ban đầu node bài viết có `views = 100`.
- Giao dịch T1 muốn cộng 1, T2 cũng muốn cộng 1.
- Kết quả nghiệp vụ mong muốn sau cả hai lần tăng thành công là **102**, không phải **101**.

Trong chương **Giao dịch** của module Neo4j, cần phân biệt rõ **khóa của thực thể**, **tính nguyên tử của giao dịch**, **mức cô lập**, và **cách viết Cypher**. Neo4j hỗ trợ khóa tự động, nhưng ứng dụng vẫn phải chọn mẫu truy vấn đúng để tránh đọc giá trị cũ rồi ghi đè kết quả của giao dịch khác.

### 1.1. Ba mục tiêu khác nhau

| Mục tiêu | Ý nghĩa | Cơ chế liên quan |
|---|---|---|
| Giao dịch nguyên tử | Các thao tác trong một giao dịch cùng commit hoặc rollback | Transaction |
| Điều phối cập nhật cùng thực thể | Hai thao tác ghi xung đột không đồng thời thay đổi cùng đối tượng một cách tùy tiện | Write lock |
| Bảo đảm quy tắc dữ liệu | Ví dụ một `User` không được có hai node cùng `userId` | Uniqueness constraint và kiểm tra nghiệp vụ |

Khóa không thay thế constraint. Ngược lại, constraint không giải quyết mọi bài toán như ghi đè thuộc tính, deadlock hoặc cập nhật dựa trên dữ liệu vừa đọc.

## 2. Neo4j khóa đối tượng nào?

Trong các thao tác cập nhật Cypher thông thường, Neo4j tự quản lý khóa. Có thể hình dung các nhóm thao tác:

| Thao tác | Đối tượng trực tiếp chịu tác động | Điều cần hiểu |
|---|---|---|
| `SET n.name = ...` | Node `n` | Ghi property của node cần đồng bộ các thao tác ghi liên quan |
| `SET n:Verified`, `REMOVE n:Verified` | Node `n` | Thay đổi nhãn cũng là cập nhật node |
| `SET r.since = ...` | Relationship `r` | Ghi property của relationship cần điều phối ghi lên relationship |
| `CREATE (a)-[:KNOWS]->(b)` | Cấu trúc relationship và các đầu mút liên quan | Neo4j có thể cần thêm khóa/đồng bộ dữ liệu kết nối ở node đầu mút |
| `DELETE r` | Relationship `r` | Thao tác xóa phải phối hợp với giao dịch đang sử dụng/ghi relationship |
| `DETACH DELETE n` | Node `n` và các relationship kề nó | Có thể ảnh hưởng nhiều thực thể và tăng phạm vi tranh chấp |

**Đơn vị khóa không đồng nghĩa với từng property riêng lẻ.** Nếu hai giao dịch cùng sửa `name` và `status` trên **cùng một node**, chúng vẫn có thể phải tranh chấp khóa ghi của node đó, mặc dù không sửa cùng tên property. Với relationship, thay đổi hai property khác nhau trên cùng relationship cũng có thể tranh chấp.

Neo4j có các loại khóa nội bộ và quy tắc tối ưu tùy phiên bản, loại thực thể, mật độ relationship và thao tác. Không nên suy ra rằng một câu Cypher chỉ lấy đúng một khóa từ tên biến được viết trong `SET`; việc tạo/xóa relationship còn cần cập nhật cấu trúc đồ thị.

### 2.1. Khóa ghi tồn tại trong phạm vi giao dịch

Một giao dịch có thể thực hiện nhiều câu Cypher trước khi commit:

~~~cypher
MATCH (u:User {userId: $userId})
SET u.status = 'ACTIVE';

MATCH (u:User {userId: $userId})
SET u.updatedAt = datetime();
~~~

Nếu hai câu trên nằm trong **cùng một transaction**, Neo4j giữ các khóa cần thiết trong quá trình thực hiện và giải phóng theo vòng đời giao dịch khi commit hoặc rollback. Vì vậy, giao dịch kéo dài trong lúc chờ HTTP/API bên ngoài có thể làm yêu cầu khác chờ khóa lâu hơn.

Một câu lệnh `MATCH ... RETURN ...` chỉ đọc không mặc nhiên trở thành thao tác "khóa độc quyền để sửa sau". Mức cô lập mặc định thường được mô tả là **read committed**: ứng dụng không đọc dữ liệu chưa commit của giao dịch khác, nhưng các lần đọc khác nhau có thể quan sát giá trị đã được giao dịch khác commit ở những thời điểm khác nhau.

## 3. Cập nhật thuộc tính node: tranh chấp ở cấp node

Giả sử hai request cập nhật cùng khách hàng:

~~~cypher
MATCH (u:User {userId: $userId})
SET u.displayName = $newName
RETURN u.userId AS userId, u.displayName AS displayName;
~~~

Đây là thao tác ghi lên **node `u`**. Nếu T1 và T2 cùng sửa node đó, mỗi giao dịch phải tuân theo cơ chế khóa ghi của Neo4j. Một giao dịch có thể chờ đến khi giao dịch khác hoàn tất.

Tuy nhiên, khóa chỉ giúp điều phối việc ghi; **không tự quyết định request nào phải thắng theo nghiệp vụ**. Nếu T1 ghi `"An"` còn T2 ghi `"An Nguyễn"`, giá trị cuối cùng phụ thuộc thứ tự thực thi/commit và logic cập nhật. Khi cần chỉ chấp nhận phiên bản mới nhất, ứng dụng nên thiết kế cơ chế version, điều kiện cập nhật hoặc xử lý xung đột rõ ràng.

### 3.1. Sửa hai property khác nhau trên cùng node

~~~cypher
// Giao dịch T1
MATCH (u:User {userId: 'u-1'})
SET u.displayName = 'An';
~~~

~~~cypher
// Giao dịch T2
MATCH (u:User {userId: 'u-1'})
SET u.lastSeenAt = datetime();
~~~

Cả hai câu đều ghi cùng node `User`. Tên property khác nhau không có nghĩa hai câu ghi hoàn toàn độc lập về khóa. Khi một node bị cập nhật thường xuyên, nó có thể trở thành **điểm nóng (hot node)**, đặc biệt nếu nhiều worker đều tăng các bộ đếm hoặc cập nhật timestamp trên node đó.

> **Quy ước ví dụ:** Các đoạn Cypher ghi riêng biệt trong bài thể hiện những câu lệnh chạy ở các giao dịch/phiên khác nhau khi ghi chú T1 hoặc T2; không ghép các đoạn ví dụ độc lập vào một file chạy một lần.

## 4. Cộng dồn giá trị đúng cách: tránh lost update

Một tình huống phổ biến là đọc property hiện tại rồi cộng thêm. Có hai cách viết với mức an toàn khác nhau.

### 4.1. Cập nhật dựa trên property ngay trong SET

~~~cypher
MATCH (p:Post {postId: $postId})
SET p.views = coalesce(p.views, 0) + 1
RETURN p.views AS views;
~~~

Với mẫu cập nhật trực tiếp thuộc tính của chính node, Cypher có thể xác định giá trị mới phụ thuộc giá trị cũ của thuộc tính đó và bảo vệ quá trình đọc–sửa–ghi bằng khóa thích hợp. Hai lần tăng đồng thời **đều thành công** phải bảo toàn được tổng số lần tăng.

Đây là mẫu cơ bản để thay đổi một bộ đếm. Tuy vậy, một node được cập nhật rất thường xuyên vẫn tạo tranh chấp khóa; đúng về dữ liệu chưa chắc tối ưu về thông lượng.

### 4.2. Phản ví dụ: tính trước giá trị rồi mới ghi

~~~cypher
MATCH (p:Post {postId: $postId})
WITH p, coalesce(p.views, 0) AS oldViews
SET p.views = oldViews + 1
RETURN p.views AS views;
~~~

Đoạn trên **có nguy cơ lost update** khi hai giao dịch đọc `oldViews` trước lúc lấy khóa ghi. Lịch xen kẽ có thể là:

| Thời điểm | T1 | T2 |
|---|---|---|
| 1 | Đọc `oldViews = 100` | |
| 2 | | Đọc `oldViews = 100` |
| 3 | Ghi `views = 101` và commit | |
| 4 | | Ghi giá trị đã tính trước `101` và commit |
| Kết quả | | **101 thay vì 102** |

Dữ liệu đọc trước khi khóa ghi có thể đã lỗi thời. Cần phân biệt kiểu truy vấn **SET một property dựa trên chính giá trị hiện tại của nó** với kiểu **tính trước bằng `WITH` rồi SET lại một giá trị đã cố định**. Nếu bài toán phức tạp hơn một biểu thức tự tăng đơn giản, hãy kiểm tra mô hình khóa/giao dịch và quy tắc nhất quán ở cấp ứng dụng.

### 4.3. Không nhầm nguyên tử với chống lost update

Hai transaction đều có thể **commit thành công và nguyên tử**, nhưng logic đọc–ghi ở mức nghiệp vụ vẫn gây lost update. Không có thao tác nào "nửa commit"; vấn đề nằm ở chỗ giao dịch sau **ghi một giá trị tính từ dữ liệu cũ**.

Nếu cần thao tác như:

- Trừ hàng tồn kho **chỉ khi còn đủ số lượng**;
- Chuyển điểm/tài sản giữa hai tài khoản;
- Đổi trạng thái **chỉ nếu trạng thái hiện tại vẫn là PENDING**;

thì cần bảo vệ toàn bộ điều kiện đọc và hành động ghi, không chỉ quan tâm việc câu `SET` có khóa ở thời điểm ghi. Đặc biệt, đánh giá `WHERE` trước khi thu được khóa có thể khiến điều kiện nghiệp vụ bị tính trên trạng thái không còn hiện hành. Trong các luồng quan trọng, phải thiết kế giao dịch có kiểm soát xung đột và kiểm thử cạnh tranh thực tế.

## 5. Khóa khi cập nhật relationship và thuộc tính relationship

Trong Neo4j, relationship cũng là thực thể có identity, type và property. Ví dụ một khách hàng là thành viên của tổ chức:

~~~cypher
MATCH (u:User {userId: $userId})-[m:MEMBER_OF]->(o:Organization {orgId: $orgId})
SET m.role = $newRole,
    m.updatedAt = datetime()
RETURN m.role AS role;
~~~

Ở đây `m` đại diện cho **relationship MEMBER_OF**. Câu `SET m.role` cập nhật **property trên relationship**, không phải property trên node User hoặc Organization.

Hai giao dịch cùng sửa role và joinedAt trên **cùng relationship `m`** có thể tranh chấp khóa ghi của relationship. Ngược lại, việc sửa một relationship khác không phải lúc nào cũng xung đột trực tiếp; kết quả còn phụ thuộc thao tác và các khóa liên quan khác.

### 5.1. Xóa relationship

~~~cypher
MATCH (u:User {userId: $userId})-[m:MEMBER_OF]->(o:Organization {orgId: $orgId})
DELETE m;
~~~

Lệnh xóa relationship nhưng giữ hai node đầu mút. Một transaction đồng thời sửa property của `m` có thể phải chờ khóa, hoặc gặp lỗi nếu giả định về dữ liệu bị thay đổi trong lúc chạy. Ứng dụng nên xử lý trường hợp relationship không còn tồn tại như một kết quả nghiệp vụ có thể xảy ra.

### 5.2. Tạo relationship cũng làm thay đổi cấu trúc graph

~~~cypher
MATCH (u:User {userId: $userId})
MATCH (o:Organization {orgId: $orgId})
MERGE (u)-[m:MEMBER_OF]->(o)
ON CREATE SET m.joinedAt = datetime()
RETURN m.joinedAt AS joinedAt;
~~~

Dù câu `MERGE` cuối cùng có thể chỉ tạo **một relationship**, thao tác liên quan đến đầu mút và danh sách kết nối của hai node. Neo4j dùng cơ chế đồng bộ thích hợp với việc tạo relationship; vì vậy tranh chấp có thể xảy ra tại các node có rất nhiều quan hệ hoặc khi nhiều giao dịch cùng tạo/xóa cạnh tới một đối tượng.

**MERGE không đồng nghĩa với ràng buộc duy nhất cho mọi quan hệ trong mọi lịch đồng thời.** Khi nghiệp vụ bắt buộc một membership duy nhất cho một cặp User–Organization, cần kiểm tra mô hình định danh, constraint phù hợp với phiên bản Neo4j và cách ứng dụng xử lý giao dịch đồng thời. Uniqueness constraint trên `User.userId` và `Organization.orgId` chỉ trực tiếp bảo vệ tính duy nhất của **node** theo hai khóa đó.

## 6. Xóa node và relationship: phạm vi khóa có thể rộng hơn

Với node còn relationship, `DELETE n` thông thường sẽ thất bại. Để xóa node và toàn bộ relationship nối trực tiếp đến nó, dùng `DETACH DELETE`:

~~~cypher
MATCH (u:User {userId: $userId})
DETACH DELETE u;
~~~

Câu này có thể ảnh hưởng **nhiều relationship**, bao gồm cả quan hệ đi vào và đi ra. Với node có rất nhiều kết nối, số thực thể bị sửa và thời gian giữ khóa có thể đáng kể.

Nếu chỉ cần bỏ quan hệ thành viên:

~~~cypher
MATCH (:User {userId: $userId})-[m:MEMBER_OF]->(:Organization {orgId: $orgId})
DELETE m;
~~~

Chọn đúng **đối tượng cần xóa** giúp giảm phạm vi tác động và phù hợp nghiệp vụ hơn. Không dùng `DETACH DELETE u` để thay thế cho việc hủy một relationship đơn lẻ.

## 7. Khi hai giao dịch cần khóa nhiều đối tượng

Giao dịch thường phải cập nhật nhiều node hoặc relationship. Ví dụ dịch chuyển một số điểm giữa hai ví:

~~~cypher
MATCH (src:Wallet {walletId: $sourceId})
MATCH (dst:Wallet {walletId: $targetId})
SET src.points = src.points - $amount,
    dst.points = dst.points + $amount
RETURN src.points AS sourcePoints, dst.points AS targetPoints;
~~~

Các phép ghi này được thực hiện trong cùng câu Cypher và cùng giao dịch. Nếu giao dịch commit, các cập nhật thuộc về cùng một đơn vị nguyên tử; nếu rollback, không có trạng thái commit "chỉ trừ mà không cộng".

**Đây chỉ là ví dụ về tính nguyên tử và phạm vi khóa, chưa phải thuật toán chuyển điểm hoàn chỉnh.** Hệ thống thật cần kiểm tra `sourceId != targetId`, số dư đủ, giá trị `amount` hợp lệ và bảo vệ điều kiện đó trước các yêu cầu chuyển đồng thời. Cách `MATCH ... WHERE src.points >= $amount ... SET ...` viết đơn giản có thể chưa đủ nếu việc kiểm tra điều kiện bị tách khỏi thời điểm khóa phù hợp.

### 7.1. Deadlock: hai giao dịch chờ nhau

Hình dung T1 lấy được khóa ghi của ví A rồi muốn sửa ví B; T2 lấy được khóa ghi của ví B rồi muốn sửa ví A:

~~~text
T1: giữ khóa A  ---> chờ khóa B
T2: giữ khóa B  ---> chờ khóa A
                    ^ vòng chờ ^
~~~

Hai transaction tạo thành **vòng chờ**. Đây là deadlock. Neo4j có cơ chế phát hiện deadlock và có thể hủy/rollback một giao dịch để giao dịch còn lại tiếp tục. Ứng dụng nhận lỗi giao dịch tạm thời trong tình huống này, thay vì cứ chờ mãi.

Khóa không có nghĩa deadlock sẽ không xảy ra. Deadlock thường liên quan tới **thứ tự lấy nhiều khóa khác nhau** dưới tải đồng thời.

### 7.2. Giảm deadlock bằng thứ tự cập nhật nhất quán

Nếu nhiều service đều cần ghi một tập ví, nên sắp xếp **ID ví** trước rồi cập nhật tuần tự theo cùng thứ tự trong một transaction:

~~~java
List<String> orderedWalletIds = walletIds.stream()
    .distinct()
    .sorted()
    .toList();

session.executeWrite(tx -> {
    for (String walletId : orderedWalletIds) {
        tx.run("""
            MATCH (w:Wallet {walletId: $walletId})
            SET w.updatedAt = datetime()
            """, Values.parameters("walletId", walletId)).consume();
    }
    return null;
});
~~~

Đây là **minh họa chiến lược thứ tự khóa ở cấp ứng dụng**: nhiều workflow sử dụng cùng quy tắc sắp xếp giúp giảm các vòng chờ đối nghịch do chúng tự tạo ra. Nó **không bảo đảm loại bỏ mọi deadlock**, bởi một truy vấn có thể khóa thêm tài nguyên nội bộ, một service khác có thể ghi không theo cùng thứ tự hoặc query plan xử lý khác với giả định.

Ví dụ Java giả định đã có biến `session`, `walletIds` và import các kiểu tương ứng. Đây không phải một hàm chuyển tiền hoàn chỉnh.

## 8. Khóa, isolation và constraint: ranh giới trách nhiệm

Một transaction Neo4j có tính nguyên tử, nhưng mức cô lập mặc định **read committed** không hứa rằng tất cả dữ liệu đọc ở đầu và cuối giao dịch đều là một snapshot bất biến. Trong một luồng đọc rồi mới quyết định ghi, giao dịch khác có thể commit xen vào.

| Tình huống | Việc khóa tự động hỗ trợ | Điều ứng dụng vẫn phải làm |
|---|---|---|
| T1 và T2 cùng `SET u.name` | Điều phối hai thao tác ghi cùng node | Chọn quy tắc cập nhật phiên bản mới nhất |
| Hai lần tăng `counter` trực tiếp trong `SET` | Bảo vệ phép đọc–sửa–ghi khi Cypher nhận biết phụ thuộc | Tránh tính trước giá trị có thể cũ |
| Cùng tạo `User` theo `userId` | Điều phối thao tác ghi và các khóa liên quan | Định nghĩa uniqueness constraint, dùng MERGE theo khóa |
| Hai giao dịch sửa hai node theo thứ tự ngược nhau | Quản lý khóa, phát hiện vòng chờ | Retry khi phù hợp và thống nhất thứ tự ghi |
| Một worker xóa relationship, worker khác sửa nó | Đồng bộ thay đổi thực thể | Xử lý kết quả không còn dữ liệu hoặc lỗi cạnh tranh |
| Cập nhật số dư có điều kiện | Khóa khi thực hiện ghi | Bảo vệ điều kiện kiểm tra và quy tắc không âm theo thiết kế nhất quán |

### 8.1. MERGE và uniqueness constraint

Khi nhiều request cùng cố tạo node theo một khóa, `MERGE` tiện cho tìm hoặc tạo:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = $displayName
RETURN u.userId AS userId;
~~~

Nhưng để **cấm trùng khóa ở cấp database**, cần constraint tương ứng:

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

Constraint phải được triển khai trước khi cho phép ghi đồng thời quy mô lớn. Nếu đã có node trùng, lệnh tạo constraint có thể thất bại. Constraint không thay thế việc phân loại lỗi transient hay kiểm soát transaction.

### 8.2. Optimistic concurrency: chỉ cập nhật nếu phiên bản khớp

Khi nhiều người cùng sửa cùng một bản ghi nhưng không muốn âm thầm ghi đè, có thể dùng một property version để biểu diễn yêu cầu nghiệp vụ:

~~~cypher
MATCH (d:Document {documentId: $documentId})
WHERE d.version = $expectedVersion
SET d.title = $newTitle,
    d.version = d.version + 1
RETURN d.documentId AS documentId,
       d.version AS version;
~~~

Nếu truy vấn trả về **0 hàng**, có thể bản ghi không tồn tại hoặc version không khớp. Tuy nhiên, mẫu kiểm tra version ở `WHERE` và ghi trong `SET` cần **được kiểm chứng dưới concurrency**: đọc điều kiện trước khi thu được khóa và sự tái đánh giá điều kiện phụ thuộc semantics thực thi. Không được tự suy luận đây là một compare-and-swap nguyên tử có bảo đảm trên mọi phiên bản/kế hoạch truy vấn.

Đối với quy tắc **bắt buộc chỉ một request thành công khi cùng version**, hãy sử dụng mẫu transaction/lock có bảo đảm được kiểm chứng cho phiên bản Neo4j đang dùng, hoặc cơ chế concurrency phù hợp ở tầng ứng dụng. Kết hợp kiểm tra số hàng trả về với xử lý retry/xung đột; tránh giả định có một câu lệnh Cypher là tự động đạt serializable isolation.

## 9. Lựa chọn transaction trong Java Driver

Neo4j Java Driver hỗ trợ transaction được quản lý bằng `Session.executeWrite(...)`. Đây là nơi phù hợp để gom các câu ghi cần nguyên tử:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class UserService {
    private final Driver driver;

    public UserService(Driver driver) {
        this.driver = driver;
    }

    public String changeDisplayName(String userId, String newName) {
        if (userId == null || userId.isBlank()) {
            throw new IllegalArgumentException("userId is required");
        }

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx ->
                tx.run("""
                    MATCH (u:User {userId: $userId})
                    SET u.displayName = $newName,
                        u.updatedAt = datetime()
                    RETURN u.userId AS userId
                    """, Map.of("userId", userId, "newName", newName))
                  .single()
                  .get("userId")
                  .asString()
            );
        }
    }
}
~~~

Một vài lưu ý triển khai:

- **Driver** thường được tái sử dụng ở cấp ứng dụng; **Session** có vòng đời ngắn và không nên chia sẻ tùy tiện giữa các thread.
- Callback trong `executeWrite` có thể được driver thực thi lại khi gặp lỗi transient thuộc diện retry. Hành động trong callback nên **an toàn khi chạy lại**.
- Không gọi email, thanh toán hoặc API bên ngoài bên trong callback có thể retry nếu những thao tác đó không có cơ chế idempotency phù hợp.
- `single()` giả định đúng một node được tìm thấy. Nếu không có node hoặc nhiều hàng không hợp lệ, phương thức sẽ ném lỗi; ứng dụng cần xác định cách trả về “không tìm thấy”.
- Tên database, thời gian retry và driver version phải được cấu hình theo hệ thống thực tế.

Với **Spring Data Neo4j**, một service dùng transaction phù hợp vẫn dựa trên cơ chế khóa của Neo4j và lựa chọn truy vấn. Annotation quản lý transaction không tự biến mọi logic đọc–kiểm tra–ghi thành thao tác miễn nhiễm lost update hoặc deadlock.

## 10. Xử lý lỗi tranh chấp, timeout và retry

Các giao dịch cạnh tranh có thể gặp một số nhóm kết quả:

| Loại kết quả | Ví dụ | Phản ứng phù hợp |
|---|---|---|
| Commit thành công | Hai lần tăng counter đều hoàn thành | Trả kết quả; kiểm tra giá trị nghiệp vụ |
| Chờ khóa | T1 đang sửa node mà T2 cũng cần | Giữ giao dịch ngắn; quan sát latency và tải |
| Deadlock/transient failure | Hai transaction chờ nhau theo vòng | Retry **toàn bộ transaction** khi lỗi được phân loại có thể retry |
| Constraint violation | Hai yêu cầu tạo trùng khóa unique; hoặc dữ liệu xung đột | Đọc lại theo khóa, phân biệt ghi cạnh tranh với lỗi nghiệp vụ |
| Input không hợp lệ | Khóa null, số tiền âm, thiếu định danh | Từ chối request; không retry |
| Transaction timeout | Câu ghi/khóa chờ quá lâu so với giới hạn | Xác định nút nóng, truy vấn chậm và thời gian giữ khóa trước khi điều chỉnh |

Không nên **retry vô hạn**. Retry nên có giới hạn về số lần/thời gian, backoff hợp lý và chỉ áp dụng cho loại lỗi thực sự có khả năng thành công ở lần sau. Java Driver managed transaction có thể tự retry một số lỗi transient; đừng thêm vòng retry bên ngoài một cách tùy tiện để vô tình nhân số lần thực thi.

### 10.1. Retry phải bao gồm toàn bộ đơn vị công việc

Nếu T1 đã lấy khóa của A và cần B nhưng deadlock làm transaction rollback, lần thử lại phải làm lại **toàn bộ phần việc thuộc transaction**, bao gồm bước đọc cần thiết và các câu ghi liên quan.

Không tiếp tục từ giữa quy trình như thể những phần trước đã commit. Trạng thái dữ liệu có thể thay đổi trong khoảng thời gian từ lỗi đến lần retry.

### 10.2. Bảo vệ thao tác có tác dụng phụ

Giả sử transaction cộng điểm và sau đó gửi thông báo. Nếu gửi thông báo bên trong callback trước khi commit, callback có thể chạy nhiều lần khi retry, dẫn tới thông báo trùng. Với tác vụ quan trọng, dùng cơ chế như **outbox** hoặc idempotency key, để việc công bố sự kiện sau commit được kiểm soát.

## 11. Giảm tranh chấp khóa từ thiết kế truy vấn

### 11.1. Bắt đầu từ node cần cập nhật, tránh mở rộng đồ thị không cần thiết

Nếu chỉ đổi trạng thái đơn hàng, truy vấn ngắn gọn:

~~~cypher
MATCH (o:Order {orderId: $orderId})
SET o.status = $status,
    o.updatedAt = datetime()
RETURN o.orderId AS orderId;
~~~

Không cần duyệt tất cả customer, sản phẩm hay relationship trước khi đến node Order nếu `orderId` đã nhận diện chính xác đơn hàng.

Tạo uniqueness constraint/index phù hợp cho `Order.orderId` giúp tìm điểm bắt đầu hiệu quả. Index **không làm khóa ghi biến mất**, nhưng có thể giảm thời gian tìm node và lượng công việc trước/sau khi lấy khóa.

### 11.2. Tránh transaction quá dài

Một transaction dài có thể:

- Giữ khóa lâu, làm nhiều request khác chờ.
- Tăng nguy cơ đụng độ với các workflow đang cập nhật cùng thực thể.
- Tiêu thụ thêm bộ nhớ và tài nguyên xử lý.
- Khi bị rollback, phải làm lại một lượng công việc lớn.

Ưu tiên hoàn tất tính toán không phụ thuộc dữ liệu đang thay đổi trước khi mở transaction, truyền tham số cần thiết, ghi đủ ngắn và commit. Nhưng **không** chuyển phép đọc dữ liệu cần nhất quán ra khỏi transaction chỉ để giảm thời gian khóa; cần cân bằng giữa correctness và hiệu năng.

### 11.3. Giảm “hot node”

Nếu một node `Post` nhận hàng nghìn lần tăng `views` mỗi giây, tất cả các thao tác ghi trực tiếp cùng node có thể phải chờ nhau. Có thể cân nhắc:

- Gom nhiều sự kiện lượt xem thành cập nhật theo lô, với cơ chế xử lý trùng.
- Dùng bộ đếm phân mảnh hoặc bảng tổng hợp riêng nếu nghiệp vụ chấp nhận đồng bộ trễ.
- Tách hoạt động ghi thường xuyên khỏi các cập nhật không liên quan, khi mô hình cho phép.

Đổi mô hình có chi phí: phải quyết định cách tính tổng, độ trễ dữ liệu và xử lý sự kiện lặp. Chỉ tối ưu sau khi đo được contention và mục tiêu thông lượng.

### 11.4. Ghi theo lô với mức song song có kiểm soát

Khi nhập dữ liệu, giao dịch cực lớn có thể giữ nhiều khóa lâu; giao dịch quá nhỏ có thể gây overhead. Tìm kích thước lô hợp lý theo dữ liệu, mật độ relationship và contention.

Nhiều worker cùng nhập các bản ghi có chung khóa nghiệp vụ cần phối hợp constraint, MERGE và retry. Chia lô **không** tự loại bỏ xung đột giữa các worker.

## 12. Quan sát giao dịch và kiểm chứng

### 12.1. Xem các transaction đang chạy

Trong môi trường và quyền hạn cho phép, có thể quan sát trạng thái giao dịch:

~~~cypher
SHOW TRANSACTIONS;
~~~

Các cột và khả năng thấy transaction của người dùng khác phụ thuộc Neo4j version, edition và quyền quản trị. Hãy tìm giao dịch chạy lâu, câu lệnh đang thực thi và trạng thái chờ nếu phiên bản/công cụ quan sát cung cấp thông tin đó.

### 12.2. EXPLAIN và PROFILE phục vụ mục đích khác nhau

~~~cypher
EXPLAIN
MATCH (u:User {userId: $userId})
SET u.status = 'ACTIVE'
RETURN u.userId;
~~~

`EXPLAIN` phân tích kế hoạch **mà không thực thi thao tác ghi**, hữu ích để xem điểm bắt đầu và cách truy vấn tìm node. `PROFILE` **thực thi** câu lệnh, vì vậy không dùng PROFILE với truy vấn ghi trên dữ liệu production chỉ để “xem thử”.

Kế hoạch truy vấn không tự cung cấp bảo đảm rằng không có contention hoặc deadlock. Để đánh giá khóa, cần xem thêm latency, lỗi transient, timeout, mức độ song song và các chỉ số phù hợp từ Neo4j/ứng dụng.

### 12.3. Kịch bản thử đồng thời tối thiểu

Trong database thử nghiệm riêng, tạo node có khóa duy nhất và bộ đếm ban đầu:

~~~cypher
CREATE CONSTRAINT lock_lab_counter_id IF NOT EXISTS
FOR (n:LockLabCounter)
REQUIRE n.counterId IS UNIQUE;
~~~

~~~cypher
MERGE (n:LockLabCounter {counterId: 'demo'})
SET n.value = 0;
~~~

Từ **hai hoặc nhiều session**, cho mỗi session thực thi nhiều lần câu sau với transaction riêng:

~~~cypher
MATCH (n:LockLabCounter {counterId: 'demo'})
SET n.value = n.value + 1
RETURN n.value AS value;
~~~

Đọc lại:

~~~cypher
MATCH (n:LockLabCounter {counterId: 'demo'})
RETURN n.value AS actual;
~~~

Nếu có `W` worker, mỗi worker hoàn thành `K` transaction tăng một lần, giá trị mong muốn là **W × K**, với điều kiện tất cả transaction đều thành công và không có tiến trình khác sửa `value`. Ghi riêng số lỗi, số lần retry và độ trễ; kết quả đúng nhưng retry liên tục vẫn cho thấy vấn đề contention.

Lặp lại trong **môi trường thử nghiệm** với mẫu tính trước giá trị qua `WITH` để nhận diện nguy cơ lost update. Sự xuất hiện của lỗi có thể phụ thuộc cách hai session xen kẽ; không thấy lỗi trong một lần thử không phải bằng chứng an toàn cho mọi lịch thực thi.

Dọn dữ liệu ví dụ sau khi hoàn tất trên database thử nghiệm:

~~~cypher
MATCH (n:LockLabCounter {counterId: 'demo'})
DETACH DELETE n;
~~~

## 13. Các ngộ nhận thường gặp

**“Neo4j khóa mỗi property độc lập.”** Không nên hiểu như vậy. Cập nhật property của cùng một node có thể tranh chấp khóa ở cấp node, kể cả tên property khác nhau.

**“Có khóa thì không bao giờ lost update.”** Không đúng. Nếu ứng dụng tính giá trị từ dữ liệu đã đọc trước thời điểm ghi, nó có thể ghi đè kết quả của giao dịch khác bằng giá trị cũ.

**“Một transaction đảm bảo mọi phép đọc và ghi đều serializable.”** Không đúng với giả định cô lập mặc định. Cần kiểm tra cách đọc, thời điểm khóa và bảo vệ điều kiện nghiệp vụ.

**“Khóa ghi là lock do mình phải khai báo thủ công trong mọi câu Cypher.”** Không. Neo4j tự lấy khóa cần thiết cho thao tác ghi. Tuy vậy, các workflow đọc–kiểm tra–ghi phức tạp có thể đòi hỏi thiết kế đồng bộ bổ sung.

**“Tạo constraint UNIQUE cũng giải quyết deadlock.”** Không. Constraint bảo vệ tính duy nhất của dữ liệu theo khóa; deadlock phát sinh khi các transaction tranh chấp nhiều tài nguyên theo thứ tự khác nhau.

**“Deadlock nghĩa là database bị hỏng.”** Không. Đó là điều kiện cạnh tranh có thể phát sinh trong hệ thống nhiều giao dịch. Neo4j có thể phát hiện và rollback một giao dịch; ứng dụng cần xử lý lỗi transient.

**“Chuyển hết sang một câu Cypher là hết tranh chấp.”** Không. Một câu Cypher vẫn có thể cập nhật nhiều node/relationship, giữ khóa và xảy ra xung đột với transaction khác.

**“PROFILE chỉ hiển thị kế hoạch.”** Không. PROFILE thực thi truy vấn; hãy dùng EXPLAIN nếu chỉ muốn xem kế hoạch của câu lệnh ghi.

## 14. Bài tập tự kiểm tra

### Bài tập 1 — Hai trường trên cùng một node

T1 chạy `SET u.name = 'Bình'`, còn T2 chạy `SET u.status = 'ACTIVE'` trên cùng node `u`. Vì thay đổi hai trường khác nhau, có thể khẳng định không tranh chấp khóa không?

**Gợi ý:** Không. Các thao tác ghi trên cùng node vẫn có thể cần cùng khóa ghi của node.

### Bài tập 2 — Bộ đếm bị thiếu một lần tăng

Hai worker đọc cùng giá trị `oldCount = 7` vào biến Java, sau đó mỗi worker chạy `SET p.count = $oldCount + 1`. Cả hai request thành công, giá trị cuối là 8. Vì sao?

**Gợi ý:** Hai request cùng gửi giá trị tính từ trạng thái cũ, nên một lần tăng bị ghi đè. Chuyển phép cộng vào `SET p.count = p.count + 1` thay vì truyền kết quả tính trước có thể tránh kiểu lost update này.

### Bài tập 3 — Cập nhật membership

Ứng dụng cần đổi `role` trên quan hệ MEMBER_OF giữa User và Organization. Có nên `SET u.role` hay `SET m.role`?

**Gợi ý:** Nếu role thuộc về **mối quan hệ thành viên**, cập nhật `m.role` trên relationship. Xác định chính xác đối tượng được ghi giúp mô hình hóa đúng và hiểu phạm vi tranh chấp.

### Bài tập 4 — Deadlock hai ví

T1 cập nhật ví A rồi B; T2 cập nhật B rồi A. Hai giao dịch đều đang giữ một khóa và chờ khóa còn lại. Điều gì cần diễn ra?

**Gợi ý:** Cơ chế phát hiện deadlock có thể khiến một transaction bị rollback. Ứng dụng retry toàn bộ đơn vị công việc khi lỗi được phân loại có thể retry; thống nhất thứ tự cập nhật giúp giảm nguy cơ.

### Bài tập 5 — Transaction có gọi HTTP

Một callback `executeWrite` cập nhật đơn hàng, rồi trực tiếp gọi API gửi SMS. Vì sao không nên làm vậy?

**Gợi ý:** Callback có thể chạy lại khi transaction gặp lỗi transient. Nếu SMS đã gửi nhưng transaction rollback/retry, thông báo có thể bị gửi nhiều lần. Cần cơ chế phát sự kiện sau commit hoặc idempotency phù hợp.

## 15. Ghi nhớ

Trong Neo4j, **ghi property lên node** và **ghi property lên relationship** được điều phối bằng cơ chế khóa giao dịch; **tạo và xóa relationship** còn tác động tới cấu trúc kết nối của graph. Hai thao tác cùng sửa một thực thể có thể phải chờ nhau, còn một transaction cập nhật nhiều thực thể có thể gặp **deadlock**. Neo4j quản lý khóa tự động và bảo đảm atomicity, nhưng người viết Cypher vẫn phải tránh **đọc giá trị cũ rồi ghi đè**, xác định đúng điều kiện nghiệp vụ và xử lý retry hợp lý.

Để vận hành ổn định, hãy **ghi ngắn gọn theo khóa định danh rõ ràng**, cập nhật trực tiếp các property cần đổi, thống nhất thứ tự thao tác khi xử lý nhiều thực thể, theo dõi hot node và thử concurrency với dữ liệu thực tế. Kết hợp điều đó với **constraint**, **Java Driver managed transaction** và cơ chế quan sát giúp ứng dụng graph vừa đúng dữ liệu vừa chịu tải tốt.
