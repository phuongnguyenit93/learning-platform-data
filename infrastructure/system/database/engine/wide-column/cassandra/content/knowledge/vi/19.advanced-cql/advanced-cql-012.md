# Đối chiếu CQL feature với server, native protocol và driver trong Apache Cassandra

## 1. Vấn đề: cùng một câu CQL, vì sao môi trường này chạy còn môi trường khác lỗi?

Apache Cassandra là cơ sở dữ liệu phân tán dạng **wide-column**, tổ chức dữ liệu theo **partition key**, nhân bản trên nhiều node và thường thiết kế bảng theo truy vấn. Trong chương **CQL nâng cao**, khi đưa một tính năng vào ứng dụng Java, không đủ để hỏi “CQL có cú pháp này không?”. Cần trả lời ba câu hỏi riêng:

1. **Server Cassandra** đang chạy có nhận biết cú pháp, kiểu dữ liệu và ngữ nghĩa của tính năng đó không?
2. **Native protocol** mà client và server đang sử dụng có truyền được loại request, metadata, giá trị tham số và kết quả mà tính năng cần không?
3. **Driver Java** có tương thích với phiên bản server/protocol, biết mã hóa và giải mã kiểu dữ liệu, và cung cấp API phù hợp không?

Ví dụ một ứng dụng truy vấn dữ liệu thông thường bằng `SELECT` chạy tốt, nhưng khi bổ sung một kiểu dữ liệu mới hoặc thử tìm kiếm vector thì lỗi. Nguyên nhân có thể nằm ở **server chưa hỗ trợ feature**, **cluster đang nâng cấp chưa đồng nhất**, **protocol đã thương lượng không diễn tả được kiểu mới**, hoặc **driver/codec chưa hiểu kiểu đó**. Những trường hợp này cần cách khắc phục khác nhau.

**Nguyên tắc:** khả năng sử dụng một feature là **giao nhau của server, protocol, driver và cấu hình triển khai**; nâng cấp riêng một lớp không bảo đảm toàn bộ tính năng sẵn sàng.

## 2. Bốn khái niệm dễ bị trộn lẫn

| Thành phần | Nó làm gì? | Không làm gì? |
|---|---|---|
| **CQL (Cassandra Query Language)** | Ngôn ngữ mô tả schema và truy vấn: `CREATE TABLE`, `SELECT`, `INSERT`, `UPDATE ... IF`, `USING TTL`... | Không định nghĩa cách frame TCP được mã hóa |
| **Cassandra server** | Parse và validate CQL, thực thi truy vấn, phân phối đọc/ghi đến replica, áp dụng tính năng của bản server và cấu hình | Không tự cập nhật thư viện client đã triển khai |
| **Native protocol** | Giao thức client–server cho handshake, `QUERY`, `PREPARE`, `EXECUTE`, kiểu giá trị, metadata, paging và lỗi | Không quyết định rằng một cú pháp CQL mới được server cho phép |
| **Java driver** | Quản lý kết nối, discovery, prepared statements, binding, codec, retries, paging, consistency và map kết quả vào Java | Không bổ sung feature chưa được server thực thi |

**Đặc biệt:** **“CQL 3.x” và “native protocol v3/v4/v5” là hai hệ thống phiên bản khác nhau**. Native protocol v4 không có nghĩa “CQL phiên bản 4”; chọn protocol cao hơn cũng không biến một server cũ thành server hỗ trợ cú pháp mới.

Một luồng thực thi điển hình:

~~~mermaid
flowchart LR
    A["Ứng dụng Java"] --> B["Java driver\nAPI + codec"]
    B --> C["Native protocol\nQUERY / EXECUTE"]
    C --> D["Coordinator Cassandra\nparse + validate CQL"]
    D --> E["Replica\nđọc / ghi"]
    E --> D
    D --> C
    C --> B
    B --> A
~~~

Ứng dụng có thể đi qua driver Java, `cqlsh` hoặc một client khác. Dù cùng dùng native protocol, **khả năng biểu diễn kiểu dữ liệu và API của từng client không nhất thiết giống nhau**.

## 3. Cách kiểm tra phiên bản từ đúng góc nhìn

### 3.1. Kiểm tra node server đang trả lời

Trong `cqlsh`, có thể truy vấn thông tin node local của kết nối:

~~~cql
SELECT release_version, cql_version, native_protocol_version
FROM system.local;
~~~

Diễn giải:

- `release_version`: phiên bản bản phát hành Cassandra của **node đang được truy vấn**.
- `cql_version`: phiên bản CQL mà node công bố.
- `native_protocol_version`: phiên bản native protocol được node công bố, **không nhất thiết là protocol phiên hiện tại của mọi driver**.

Cần phân biệt **thông tin một node** với **thông tin toàn cluster**. Trong quá trình rolling upgrade, các node có thể chưa cùng phiên bản. Kiểm tra thêm metadata/health các node bằng công cụ vận hành phù hợp và thử tính năng trên các coordinator mà ứng dụng thực tế có thể kết nối.

**Không suy ra** rằng thấy một node báo phiên bản mới thì toàn bộ cluster đã đủ điều kiện dùng feature mới. Một tính năng có thể cần schema tương thích, index được tạo/xây dựng đầy đủ, cấu hình bật và tất cả node tham gia truy vấn đáp ứng yêu cầu.

### 3.2. Kiểm tra phiên native protocol thực sự được thương lượng

Tại thời điểm thiết lập kết nối, client và server trao đổi thông tin giao thức. Tùy client, luồng có thể bao gồm `OPTIONS / SUPPORTED`, `STARTUP`, `READY` hoặc bước xác thực. Driver chọn phiên bản **hai bên cùng hỗ trợ** và quản lý các kết nối tới host.

Cần kiểm tra log cấu hình/khởi tạo của driver và thông tin protocol đã thương lượng trong phiên chạy thực tế. Đừng chỉ đọc version được ghi trong tài liệu của thư viện: **maximum supported** của driver có thể khác **actual negotiated** khi kết nối một server cũ.

### 3.3. Kiểm tra phiên bản driver và các codec phụ thuộc

Ở ứng dụng Java, xác nhận rõ:

- Phiên bản thư viện Cassandra Java driver thực tế được đóng gói trong ứng dụng.
- Major API đang dùng: ví dụ namespace `com.datastax.oss.driver.api` của driver 4.x, khác namespace driver 3.x.
- Codec tương ứng với các kiểu dữ liệu CQL cần đọc/ghi: `uuid`, `timestamp`, collections, UDT, tuple hoặc kiểu mới.
- Thư viện có hỗ trợ đúng native protocol và topology Cassandra đang triển khai không.

Một dự án có thể build thành công với driver mới nhưng deployment vẫn mang thư viện cũ; vì thế cần kiểm tra **dependency thực tế khi chạy**, không chỉ phiên bản mong muốn trong file cấu hình build.

## 4. Ma trận tính năng: mỗi lớp phải đáp ứng điều gì?

Bảng sau là **phương pháp đối chiếu**, không phải lời hứa rằng tất cả phiên bản Cassandra đều có cùng feature. Phải đối chiếu tài liệu của đúng **bản server, bản phân phối và driver** đang triển khai.

| Nhóm feature | Điều kiện phía server | Điều kiện phía native protocol | Điều kiện phía driver |
|---|---|---|---|
| `SELECT` theo partition key, `INSERT`, `UPDATE` | Grammar, schema, cách định tuyến partition và quy tắc truy vấn | Mang CQL text, tham số và kết quả | Gửi statement, bind khóa đúng kiểu, đọc row |
| `USING TTL`, `USING TIMESTAMP` | Parser và ngữ nghĩa TTL/timestamp của server | Truyền câu CQL và các giá trị bind | Bind kiểu số và hiểu tác dụng ghi |
| `IF NOT EXISTS`, `UPDATE ... IF` (LWT) | Server hỗ trợ conditional update và Paxos | Mang request/result, trả row `[applied]` | Đọc `[applied]` và thiết lập regular/serial consistency |
| Collections/UDT/tuple | Server hỗ trợ kiểu và schema tương ứng | Biểu diễn metadata type và giá trị | Codec chuyển CQL ↔ Java |
| `SELECT JSON` / `INSERT ... JSON` | Server hỗ trợ cú pháp và xử lý JSON CQL | Mang query/result như dữ liệu | Có thể gửi raw CQL, đọc chuỗi JSON/kết quả |
| Prepared statements | Server `PREPARE`, lưu metadata và thực thi `EXECUTE` | Thông điệp prepare/execute, ID, bound values, lỗi `UNPREPARED` | Prepare/cache/reprepare, bind kiểu đúng |
| Paging | Server tạo trang và paging state | Mang cờ và paging state giữa request/response | API phân trang, quản lý fetch tiếp theo |
| Giá trị **UNSET** trong binding | Server hiểu semantics “không cập nhật tham số này” | Cần encoding UNSET được phiên protocol hỗ trợ (v4 trở lên) | API bind/unset và xử lý đúng NULL khác UNSET |
| Index nâng cao/SAI, vector/ANN | Phụ thuộc phiên bản/bản phân phối, cấu hình index và loại truy vấn được hỗ trợ | Có thể cần diễn tả type/metadata mà protocol hỗ trợ | Query API, codec kiểu mới và chiến lược decode |

**Lưu ý:** một số feature chỉ phụ thuộc chủ yếu vào **CQL trên server** (ví dụ viết truy vấn `USING TTL`); một số feature liên quan rõ tới **wire format và codec** (ví dụ truyền giá trị typed mới); một số vừa cần **bản server**, vừa cần **index/cấu hình** (ví dụ tìm kiếm vector). Không nên lập bảng “câu lệnh này cần protocol vN” nếu chưa kiểm tra tài liệu cho đúng phiên bản.

## 5. Những phép thử thực tế theo từng lớp

### 5.1. Tính năng server hiểu cú pháp: TTL và conditional write

Tạo bảng minh họa đúng cách định tuyến bằng partition key:

~~~cql
CREATE TABLE event_by_account (
    account_id uuid,
    event_id uuid,
    state text,
    tags set<text>,
    PRIMARY KEY ((account_id), event_id)
);
~~~

Ghi sự kiện có thời hạn sống 10 phút:

~~~cql
INSERT INTO event_by_account
    (account_id, event_id, state, tags)
VALUES
    (aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
     11111111-1111-1111-1111-111111111111,
     'NEW',
     {'mobile', 'created'})
USING TTL 600;
~~~

TTL được **server thực thi và lưu cùng mutation**; native protocol mang câu query và giá trị. Nếu driver không có phương thức dựng TTL chuyên dụng, ứng dụng vẫn có thể gửi **CQL thuần** qua driver nếu server hiểu cú pháp.

Thử LWT trên đúng khóa chính:

~~~cql
UPDATE event_by_account
SET state = 'PROCESSING'
WHERE account_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
  AND event_id = 11111111-1111-1111-1111-111111111111
IF state = 'NEW';
~~~

Kết quả có cột `[applied]`. Driver cần **đọc cột đó** và phân biệt `true` với `false`; việc lệnh chạy không có exception **chưa có nghĩa** điều kiện đã được áp dụng.

Hai ví dụ này minh họa rằng **cú pháp và semantics nằm ở server**. Protocol/driver cần chuyển request và kết quả chính xác, nhưng chúng không quyết định predicate CQL.

### 5.2. Tính năng gắn với encoding: NULL và UNSET

Với prepared statements, hãy phân biệt:

- **Bind một giá trị**: cập nhật hoặc cung cấp giá trị đó.
- **Bind NULL**: thường biểu diễn giá trị null trong mutation CQL; với cột bình thường, việc ghi null tạo ý nghĩa xóa/tombstone.
- **Bind UNSET**: yêu cầu server **bỏ qua phần cập nhật tương ứng**, không coi đó là ghi NULL.

Các phiên native protocol **v4 trở lên** có encoding cho UNSET trong bound values; driver phải cung cấp cách thiết lập và không tự đổi UNSET thành NULL. Đây là ví dụ dễ thấy khi một feature liên quan **cả hành vi server lẫn wire protocol**.

Tình huống: ứng dụng xử lý PATCH, trường `display_name` không có trong request JSON thì nên **giữ nguyên cột**, còn người dùng chủ động xóa tên thì có thể cần một mutation rõ ràng. Nếu driver nhầm “không gửi giá trị” thành “bind null”, dữ liệu có thể bị xóa ngoài ý muốn.

**Không dùng UNSET để né thiết kế query:** Cassandra vẫn yêu cầu đầy đủ các thành phần khóa chính trong những statement cần chúng; UNSET không biến một prepared statement thành cơ chế cập nhật tùy ý mọi khóa.

### 5.3. Tính năng gắn với kiểu dữ liệu: collections, UDT và vector

Một cột `set<text>` trong bảng `event_by_account` yêu cầu driver có codec chuyển từ một tập hợp Java sang encoding CQL và ngược lại. Các kiểu `map`, `list`, `tuple` và **user-defined type (UDT)** có yêu cầu codec/metadata tương ứng.

Các phiên Cassandra mới, chẳng hạn dòng **5.x**, có thêm nhóm tính năng như **kiểu vector và truy vấn tìm kiếm gần đúng (ANN)**. Trước khi dùng, hãy kiểm tra:

1. Server của **mọi node liên quan** có hỗ trợ kiểu CQL và truy vấn dự định không?
2. Cú pháp tạo index, index phù hợp và trạng thái xây dựng index đã đáp ứng chưa?
3. Protocol đã thương lượng có mang được **metadata và giá trị** tương ứng không?
4. Driver hiện tại có codec đọc/ghi kiểu mới, hay cần cập nhật phiên bản/custom codec?

Một driver có thể **gửi DDL bằng raw CQL** dù chưa có API Java dành riêng cho feature. Nhưng nếu tiếp theo nó không **decode được giá trị trả về**, ứng dụng vẫn chưa thực sự hỗ trợ feature đó đầu-cuối.

### 5.4. Tính năng do protocol hỗ trợ: prepared và paging

Quy trình prepared statement nhìn tổng quát:

~~~mermaid
sequenceDiagram
    participant J as Java application
    participant D as Java driver
    participant S as Cassandra coordinator
    J->>D: prepare(CQL có dấu ?)
    D->>S: PREPARE
    S-->>D: Prepared ID + parameter metadata
    J->>D: bind(giá trị)
    D->>S: EXECUTE + ID + encoded values
    S-->>D: RESULT hoặc ERROR
    D-->>J: Row / exception
~~~

Driver thường quản lý việc cache/preparation trên nhiều node. Nếu server không còn biết prepared ID, nó có thể trả lỗi `UNPREPARED`; driver phù hợp có thể chuẩn bị lại tùy luồng xử lý. **Đừng tự xem một lỗi prepare là bằng chứng CQL feature chưa được server hỗ trợ.**

Với paging, server trả một **paging state** để yêu cầu tiếp tục truy vấn. Driver có thể tự lấy trang tiếp theo khi ứng dụng duyệt kết quả, nhưng **page size không đồng nghĩa giới hạn tổng số dòng**. Paging state phải được dùng đúng ngữ cảnh query, bind values, cấu hình và phiên protocol; không sửa thủ công hay chia sẻ token vô điều kiện cho một truy vấn khác.

## 6. Phân tích lỗi để tìm đúng lớp gây ra

Không nên xử lý mọi lỗi “unsupported” bằng cách tăng protocol version. Hãy xác định **lệnh đi được tới tầng nào**.

| Hiện tượng | Lớp đáng kiểm tra trước | Hướng xác minh |
|---|---|---|
| CQL trả lỗi cú pháp ngay cả trong `cqlsh` | Server/CQL grammar | `release_version`, cú pháp của đúng bản server, câu CQL tối giản |
| DDL chỉ lỗi khi kết nối một số node | Cluster chưa đồng nhất, feature gate, coordinator | Phiên bản/tình trạng từng node, rolling upgrade và schema agreement |
| Không kết nối được, lỗi protocol version/handshake | Native protocol, TLS/auth, driver compatibility | Version đã thương lượng, cấu hình endpoint, logs kết nối |
| CQL chạy trong `cqlsh` nhưng Java không bind/đọc được cột mới | Driver codec/metadata hoặc protocol capability | Kiểu CQL thực, codec/type mapping, driver dependency |
| Prepared statement báo `UNPREPARED` | Prepare/cache/host/schema lifecycle | Reprepare, thay đổi schema, pool/host được chọn |
| Dùng LWT mà Java luôn hiểu là thành công | Ứng dụng xử lý result | Đọc cột `[applied]` và xử lý `false` |
| Paging lặp/bỏ dữ liệu khi tự truyền state | API phân trang/truy vấn và dữ liệu thay đổi | Giữ nguyên query/bind values, kiểm tra cách truyền paging state |
| Query chạy nhưng quá chậm hoặc báo `ALLOW FILTERING` | Thiết kế bảng/index và ràng buộc CQL | Kiểm tra partition key, clustering order, index, điều kiện truy vấn |

Một lỗi hiển thị ở driver **chưa chắc** có nguyên nhân từ driver. Driver có thể chỉ chuyển tiếp phản hồi `ERROR` từ server, chẳng hạn cú pháp sai, schema không hợp lệ, không đủ replica cho consistency hoặc timeout. Cần ghi nhận **loại lỗi, thông điệp, statement, host và phiên bản liên quan** trước khi kết luận.

### Ba tình huống phải phân biệt

**Tình huống A — server thiếu feature:** Java driver gửi một câu CQL mới; coordinator parse và trả lỗi syntax/invalid. Đổi driver mà không nâng server/cấu hình sẽ không giải quyết được.

**Tình huống B — driver thiếu codec:** server chấp nhận schema và thậm chí một client khác đọc được dữ liệu, nhưng driver Java không biết giải mã kiểu mới. Khi đó cần codec/driver tương thích; sửa câu CQL có thể không đủ.

**Tình huống C — protocol không tương thích:** client không hoàn tất handshake hoặc phiên đang dùng không thể biểu diễn thông tin/giá trị cần thiết. Cần xác minh phiên protocol **hai đầu cùng hỗ trợ**, rồi quyết định phiên driver/server phù hợp; ép protocol mới khi server không hỗ trợ có thể khiến kết nối thất bại.

## 7. Ví dụ Java Driver 4.x: kiểm tra từ kết nối tới kết quả

Ví dụ sau sử dụng **DataStax Java Driver 4.x** (namespace `com.datastax.oss.driver.api`). Giả sử `CqlSession session` đã được khởi tạo bằng contact points/local datacenter phù hợp, xác thực và keyspace đúng; bảng `event_by_account` đã tạo.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.Set;
import java.util.UUID;

// Ví dụ nằm trong một method có tham số CqlSession session.
// Chuẩn bị một lần, tái sử dụng trong service cho các lời gọi khác.
PreparedStatement insert = session.prepare(
    "INSERT INTO event_by_account " +
    "(account_id, event_id, state, tags) " +
    "VALUES (?, ?, ?, ?) USING TTL ?"
);

UUID accountId = UUID.fromString(
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
);
UUID eventId = UUID.fromString(
    "11111111-1111-1111-1111-111111111111"
);

BoundStatement mutation = insert.bind(
        accountId, eventId, "NEW", Set.of("mobile", "created"), 600)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(mutation);

// Kiểm tra typed result; driver phải giải mã uuid, text và set<text>.
PreparedStatement select = session.prepare(
    "SELECT event_id, state, tags FROM event_by_account " +
    "WHERE account_id = ?"
);

BoundStatement query = select.bind(accountId)
    .setPageSize(100)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

ResultSet rows = session.execute(query);
for (Row row : rows) {
    UUID returnedId = row.getUuid("event_id");
    String state = row.getString("state");
    Set<String> tags = row.getSet("tags", String.class);
    // Sử dụng các giá trị theo nghiệp vụ; tránh log dữ liệu nhạy cảm.
}
~~~

Ví dụ này chứng minh **mối liên hệ**, không phải một ma trận tương thích cho mọi cụm Cassandra:

- **Server:** hỗ trợ bảng, TTL, `set<text>`, prepared query, phân vùng và mức nhất quán được yêu cầu.
- **Protocol:** mang `PREPARE`, `EXECUTE`, bound values, metadata/result và paging.
- **Driver:** bind `UUID`, `String`, `Set<String>`, `int`; decode kiểu trả về; đặt consistency/paging và quản lý kết nối.

`LOCAL_QUORUM` chỉ có ý nghĩa nếu replication và topology đáp ứng được số replica xác nhận. Nếu không, lỗi khả dụng/consistency có thể xuất hiện dù **feature CQL, protocol và codec đều được hỗ trợ**.

### LWT và hai consistency level trong Java

Khi thử feature LWT, đừng chỉ thấy câu CQL chạy là đủ:

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement cas = SimpleStatement.builder(
        "UPDATE event_by_account SET state = ? " +
        "WHERE account_id = ? AND event_id = ? IF state = ?")
    .addPositionalValues("PROCESSING", accountId, eventId, "NEW")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

Row outcome = session.execute(cas).one();
if (outcome == null) {
    throw new IllegalStateException("Không nhận được kết quả LWT");
}
boolean applied = outcome.getBoolean("[applied]");
if (!applied) {
    // Xung đột: điều kiện không đúng; đọc lại trạng thái nếu cần.
}
~~~

- `LOCAL_QUORUM` là **regular/write consistency level**.
- `LOCAL_SERIAL` là **serial consistency level** dùng cho Paxos của LWT.
- Với nhiều datacenter cạnh tranh cùng khóa, phải lựa chọn serial consistency dựa trên yêu cầu đồng thuận, không tự suy rằng `LOCAL_SERIAL` bảo vệ toàn cluster.
- `[applied] = false` là kết quả điều kiện không thỏa; **timeout** lại là trạng thái kết quả có thể chưa rõ và phải được xử lý riêng.

Một driver có hỗ trợ API `setSerialConsistencyLevel` không chứng minh rằng mọi phiên bản server đều hỗ trợ mọi câu CQL có `IF` hoặc mọi kiểu dữ liệu mới.

## 8. Vì sao `cqlsh` chạy được nhưng ứng dụng Java thất bại?

Đây là phép so sánh hữu ích, nhưng phải thực hiện trong **cùng điều kiện**.

Kiểm tra theo trình tự:

1. **Cùng cluster và coordinator phù hợp chưa?** `cqlsh` có thể kết nối thẳng node mới, trong khi driver dùng load balancing và gửi query tới node cũ.
2. **Cùng keyspace, schema và tài khoản chưa?** Khác role, search path/keyspace, quyền hoặc schema đã đồng bộ có thể gây kết quả khác.
3. **Cùng query text và bound values chưa?** `cqlsh` dùng literal; Java prepared statement dùng encoded binding, có thể sai type hoặc thiếu codec.
4. **Cùng protocol capability chưa?** Hai client có thể thương lượng phiên protocol khác nhau; tính năng UNSET/type mới có thể bị ảnh hưởng.
5. **Cùng consistency, retry policy và paging chưa?** Hành vi timeout, số replica, kích thước trang và độ trễ có thể khác.
6. **Đã chờ index/schema thực sự sẵn sàng chưa?** Một lệnh `CREATE INDEX` thành công không tự chứng minh mọi node đã xây dựng index đầy đủ và mọi query đã nhanh.

### Thử nghiệm tối thiểu có kiểm soát

Để phân biệt lỗi cú pháp server với lỗi driver:

1. Chọn **một câu CQL nhỏ nhất** tái hiện vấn đề, hạn chế dữ liệu ghi mới.
2. Gửi trong `cqlsh` tới đúng host/cluster cần thử.
3. Gửi **cùng câu CQL dạng raw SimpleStatement** từ Java, nếu an toàn và phù hợp.
4. Nếu raw CQL chạy nhưng prepared/binding lỗi, kiểm tra type metadata, codec và bound values.
5. Nếu cả hai cùng bị server từ chối, xác minh phiên bản server, cấu hình và syntax trước khi nâng driver.
6. Lặp lại với những coordinator có phiên bản khác nhau trong giai đoạn rolling upgrade.

Không đưa kết luận từ **một lần thử trên một node** thành cam kết cho toàn bộ cụm.

## 9. Phát hành một feature CQL mới an toàn

Ví dụ đội phát triển muốn thêm một kiểu dữ liệu hoặc truy vấn được cung cấp ở Cassandra bản mới, sau đó gọi qua Java.

~~~mermaid
flowchart TD
    A["Xác định feature / kiểu dữ liệu cụ thể"] --> B{"Server tất cả node cần thiết đã hỗ trợ?"}
    B -->|Chưa| C["Nâng cấp/chuẩn hóa server và hoàn thành rolling upgrade"]
    B -->|Có| D{"Schema, index và config sẵn sàng?"}
    C --> D
    D -->|Chưa| E["Triển khai schema, xây dựng index, xác minh"]
    D -->|Có| F{"Protocol tương thích?"}
    E --> F
    F -->|Chưa| G["Chọn phiên bản protocol/driver được hỗ trợ"]
    F -->|Có| H{"Driver codec/API và test tích hợp đạt?"}
    G --> H
    H -->|Chưa| I["Cập nhật driver/codec hoặc điều chỉnh cách bind"]
    H -->|Có| J["Bật feature có kiểm soát + theo dõi"]
    I --> H
~~~

**Các bước đề xuất:**

1. **Lập bảng phiên bản chính xác:** Cassandra trên từng datacenter/node, kiểu deployment (Apache Cassandra hay bản phân phối khác), native protocol đã thương lượng, driver Java và các codec.
2. **Đọc yêu cầu của feature cụ thể:** server version tối thiểu, syntax, type, index hoặc cấu hình. Không suy luận từ tên “CQL nâng cao”.
3. **Giữ tương thích khi rolling upgrade:** trong giai đoạn chưa đồng nhất, tạm tránh câu lệnh/kiểu dữ liệu chỉ có node mới hiểu cho tới khi toàn bộ các node cần thiết đã sẵn sàng.
4. **Thử với cluster đại diện:** dữ liệu thực tế, partition key, replication, consistency, read/write patterns; kiểm tra cả success lẫn lỗi.
5. **Triển khai driver/codec phù hợp:** kiểm tra negotiated protocol, prepared statements, decoding, paging và retry trong ứng dụng thật.
6. **Bật feature theo từng nhóm traffic:** quan sát syntax/invalid errors, lỗi codec/protocol, timeout, latency, p95/p99, load lên coordinator/replica và tác động index.
7. **Lên phương án quay lui:** thay đổi CQL/schema/index có thể khó rollback hơn thay code; xác định khả năng đọc dữ liệu mới bằng driver/server cũ trước khi bật ghi rộng rãi.

**Không coi `ALLOW FILTERING` hoặc tạo index là “sửa compatibility”.** Chúng liên quan đến thiết kế và thực thi truy vấn; một tính năng được hỗ trợ về cú pháp vẫn có thể không đáp ứng được yêu cầu tải. Cassandra thường hiệu quả nhất khi thiết kế bảng theo truy vấn và giữ các phép đọc đúng partition/clustering/index phù hợp.

## 10. Bài tập chẩn đoán

### Bài 1 — CQL và protocol có cùng phiên bản không?

Node công bố `cql_version = 3.x`, driver kết nối bằng native protocol v4. Đây có phải xung đột phiên bản?

**Gợi ý trả lời:** Không. CQL version và native protocol version là hai trục độc lập. Cần kiểm tra sự tương thích cụ thể của server và driver, không so số phiên bản bằng nhau.

### Bài 2 — Server hỗ trợ, driver cũ đọc kiểu mới bị lỗi

`cqlsh` tạo bảng và chạy truy vấn kiểu mới được, nhưng Java client không decode được cột.

**Gợi ý trả lời:** Kiểm tra **codec/type metadata**, thư viện driver thực chạy và native protocol đã thương lượng. Việc server nhận CQL chỉ chứng minh server phía đó hỗ trợ; chưa chứng minh mọi client biết giải mã kết quả.

### Bài 3 — LWT không báo exception nhưng người dùng vẫn không cập nhật được

Ứng dụng chạy `UPDATE ... IF state = 'NEW'` và báo thành công vì không có lỗi từ `execute()`.

**Gợi ý trả lời:** Phải đọc `[applied]` từ row kết quả. `false` là một CAS conflict hợp lệ, không phải exception giao thức.

### Bài 4 — Bật feature giữa rolling upgrade

Một node đã nâng cấp xử lý CQL mới tốt; node chưa nâng cấp lại trả syntax error.

**Gợi ý trả lời:** Feature rollout chưa an toàn. Trước tiên hoàn tất nâng cấp các node cần thiết và kiểm tra schema/index/driver, sau đó mới bật ứng dụng dùng syntax mới rộng rãi.

### Bài 5 — Một PATCH làm mất dữ liệu

Client Java không nhận `display_name` từ request nên bind `null` vào prepared `UPDATE`. Giá trị trong Cassandra bị xóa.

**Gợi ý trả lời:** Phân biệt **field không được cung cấp** với **field được yêu cầu xóa**. Khi dùng prepared statement và phiên protocol hỗ trợ, UNSET có thể giữ nguyên cột; NULL có semantics khác. Kiểm tra driver binding để tránh nhầm lẫn.

## 11. Checklist trước khi đưa CQL feature vào production

- [ ] Biết chính xác **feature/CQL syntax/type** sẽ dùng và yêu cầu bản server cụ thể.
- [ ] Kiểm tra phiên bản, bản phân phối và tình trạng nâng cấp của **tất cả node cần thiết**.
- [ ] Kiểm tra native protocol **được thương lượng thực tế**, không dựa vào tên thư viện.
- [ ] Driver Java tương thích protocol, có **codec** cho các kiểu dữ liệu và API binding phù hợp.
- [ ] Câu CQL đã được thử bằng literal và prepared/bound values, với đúng keyspace/role/host.
- [ ] Nếu có LWT, code kiểm tra `[applied]` và phân biệt conflict với timeout.
- [ ] Nếu có paging, test khi nhiều trang và không giả định page size là total limit.
- [ ] Nếu có index/tìm kiếm nâng cao, schema, index và kế hoạch tải đã được kiểm chứng.
- [ ] Có theo dõi lỗi theo **server, protocol, driver, query** và có kế hoạch quay lui.

**Kết luận:** **Server quyết định CQL feature có tồn tại và được thực thi hay không; native protocol quyết định nội dung request/result có thể truyền qua wire như thế nào; driver quyết định ứng dụng Java có thể bind, giải mã, kết nối và sử dụng tính năng đó đúng cách hay không.** Chỉ khi ba lớp tương thích với **topology, replication, cấu hình và thiết kế truy vấn thực tế**, một feature CQL mới mới sẵn sàng cho production.
