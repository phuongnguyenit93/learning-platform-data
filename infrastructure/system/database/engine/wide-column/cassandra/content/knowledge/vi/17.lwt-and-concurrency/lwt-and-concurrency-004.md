# Phân biệt đường ghi thông thường với đường ghi có điều kiện trong Apache Cassandra

## 1. Bài toán: hai thao tác ghi nhìn giống nhau nhưng có cam kết khác nhau

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình *wide-column*: dữ liệu được định tuyến theo **partition key** tới các replica, và ứng dụng thường thiết kế bảng dựa trên truy vấn cần phục vụ. Trong hệ thống có nhiều ứng dụng và nhiều node cùng ghi, câu hỏi quan trọng là: **lệnh ghi chỉ cần lưu giá trị mới, hay phải kiểm tra giá trị cũ trước khi ghi?**

- **Ghi thông thường (regular write)**: `INSERT`, `UPDATE` hoặc `DELETE` không có mệnh đề `IF`. Cassandra nhận mutation và phân phối tới các replica theo mức nhất quán ghi. Không có bước thống nhất toàn cụm rằng điều kiện nghiệp vụ đang đúng.
- **Ghi có điều kiện (conditional write / lightweight transaction, LWT)**: lệnh `INSERT ... IF NOT EXISTS`, `UPDATE ... IF ...`, `UPDATE ... IF EXISTS` hoặc `DELETE ... IF ...`. Cassandra dùng giao thức đồng thuận **Paxos** để kiểm tra điều kiện và quyết định có áp dụng mutation hay không.

Hai đường ghi có thể cùng cập nhật một bảng, nhưng khác nhau ở **độ trễ, thông lượng, cơ chế giải quyết xung đột và loại bất biến nghiệp vụ bảo vệ được**. Mục tiêu bài này là chọn đúng đường ghi, hiểu thứ tự xử lý và sử dụng đúng consistency level khi truy cập từ CQL hoặc ứng dụng Java.

### Một tình huống điển hình

Hai request đồng thời muốn đăng ký cùng tên người dùng `minh`:

1. Request A muốn gắn `minh` với tài khoản A.
2. Request B muốn gắn `minh` với tài khoản B.
3. Nếu cả hai chỉ chạy `INSERT` thông thường trên cùng primary key, cả hai có thể nhận phản hồi ghi thành công; giá trị cuối cùng chịu quy tắc hòa giải theo timestamp ở mức cell.
4. Nếu cả hai chạy `INSERT ... IF NOT EXISTS` đúng trên khóa `minh`, chỉ một request có thể giành quyền tạo bản ghi theo chuỗi LWT đã được đồng thuận; request còn lại nhận `[applied] = false`.

**Điểm mấu chốt:** consistency level ghi `QUORUM` giúp quy định số replica xác nhận, nhưng **không tự biến** một phép ghi thông thường thành phép *compare-and-set* (CAS).

## 2. Đường ghi thông thường đi qua những bước nào?

Ví dụ bảng tra cứu trạng thái đơn giản:

~~~cql
CREATE TABLE order_state_by_id (
    order_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);

UPDATE order_state_by_id
SET state = 'PROCESSING', updated_at = toTimestamp(now())
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

Một luồng điển hình:

1. **Client gửi mutation** tới một node làm **coordinator**.
2. Coordinator dùng **partition key** (ở đây là `order_id`) để xác định các replica chịu trách nhiệm.
3. Replica nhận mutation và thực hiện đường ghi lưu trữ, thường bao gồm **commit log** và **memtable**; SSTable được tạo về sau khi flush.
4. Coordinator phản hồi thành công khi đủ số xác nhận theo **write consistency level** của request, chẳng hạn `ONE` hoặc `LOCAL_QUORUM`.

Cassandra không cần đọc trạng thái hiện tại của dòng trước bước 3 để quyết định có được ghi hay không. Vì thế `UPDATE` có thể hoạt động như một phép **upsert**: dòng chưa tồn tại vẫn có thể được tạo.

Khi nhiều mutation xung đột trên cùng một cell, Cassandra hòa giải bằng metadata ghi, trong đó **timestamp của mutation** có vai trò quyết định theo cơ chế *last-write-wins*; không được suy luận rằng request được gửi sau hoặc được xác nhận sau sẽ luôn là giá trị cuối cùng. Các cột độc lập cũng có thể được hòa giải riêng, nên không nên hình dung toàn bộ dòng lúc nào cũng có một người thắng duy nhất.

**Điểm mạnh:** ít vòng trao đổi thông điệp hơn LWT, phù hợp lượng ghi lớn, dữ liệu sự kiện, cập nhật trạng thái không đòi hỏi điều kiện trên giá trị trước đó.

**Giới hạn:** một request nhận `LOCAL_QUORUM` thành công không chứng minh rằng trước lúc cập nhật chưa có request khác sở hữu cùng tên người dùng, hoặc version vẫn bằng giá trị client từng đọc.

## 3. Đường ghi có điều kiện đi qua những bước nào?

Ví dụ:

~~~cql
CREATE TABLE username_owner (
    username text PRIMARY KEY,
    user_id uuid,
    claimed_at timestamp
);

INSERT INTO username_owner (username, user_id, claimed_at)
VALUES (
    'minh',
    aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,
    toTimestamp(now())
)
IF NOT EXISTS;
~~~

Mệnh đề `IF NOT EXISTS` thay đổi bản chất thao tác: chỉ chấp nhận mutation khi khóa chính `username = 'minh'` chưa có bản ghi theo trạng thái được Paxos thống nhất. Kết quả CQL có cột đặc biệt `[applied]`:

~~~text
[applied]
-----------
True
~~~

Nếu một request cạnh tranh đã tạo khóa đó trước, thao tác trả `[applied] = false`; tùy câu lệnh và phiên bản Cassandra, kết quả thất bại có thể kèm các cột giá trị hiện có để client xử lý.

### Paxos: tách việc đồng thuận với việc lưu mutation

LWT sử dụng Paxos để sắp thứ tự các thao tác có điều kiện trên cùng phạm vi dữ liệu cần bảo vệ. Có thể hình dung quy trình logic như sau:

1. **Prepare / promise:** coordinator bắt đầu một đề xuất Paxos; replica tham gia hứa không chấp nhận đề xuất cũ hơn.
2. **Xác định trạng thái cần kiểm tra:** coordinator thu thập thông tin Paxos và giá trị hiện hành, đồng thời xử lý đề xuất đang dở nếu cần.
3. **Kiểm tra điều kiện:** nếu `IF` sai thì không áp dụng mutation có điều kiện; nếu đúng, tiếp tục đề xuất giá trị mới.
4. **Propose / accept:** các replica Paxos bỏ phiếu chấp nhận đề xuất.
5. **Commit / apply:** giá trị đã được chọn được đưa vào đường ghi, rồi coordinator trả kết quả tương ứng.

Đây là mô hình khái niệm để học; cách tối ưu vòng trao đổi có thể khác theo phiên bản và trường hợp thực tế. Không nên dùng một con số cố định về số lượt mạng để dự đoán mọi LWT.

~~~mermaid
flowchart TD
    A["Client gửi mutation"] --> B{"Câu lệnh có IF?"}
    B -->|Không| C["Coordinator chuyển mutation tới replica"]
    C --> D["Replica ghi commit log / memtable"]
    D --> E["Đủ ACK theo write CL → thành công"]
    B -->|Có| F["Paxos prepare / promise"]
    F --> G["Đồng thuận trạng thái cần kiểm tra"]
    G --> H{"Điều kiện IF đúng?"}
    H -->|Không| I["Trả [applied] = false"]
    H -->|Có| J["Paxos propose / accept"]
    J --> K["Commit mutation theo write CL"]
    K --> L["Trả [applied] = true"]
~~~

LWT cung cấp phép **compare-and-set có tính tuyến tính (*linearizable*) cho các thao tác điều kiện cùng khóa/phân vùng được phối hợp qua Paxos**. Nó không cung cấp một giao dịch ACID tùy ý qua nhiều partition, nhiều bảng hay cả hệ thống. Cũng không được giả định rằng ghi thông thường lên cùng dữ liệu sẽ tự tham gia trình tự Paxos: một đường ghi không có `IF` có thể phá vỡ bất biến mà ứng dụng tưởng đang bảo vệ bằng LWT.

## 4. So sánh trực diện hai đường ghi

| Khía cạnh | Ghi thông thường | Ghi có điều kiện (LWT) |
|---|---|---|
| Cú pháp thường gặp | `INSERT`, `UPDATE`, `DELETE` | `INSERT ... IF NOT EXISTS`, `UPDATE ... IF version = ?`, `DELETE ... IF ...` |
| Điều kiện dựa trên giá trị trước đó | Không kiểm tra | Kiểm tra qua Paxos trước khi quyết định |
| Đồng thuận | Không dùng Paxos cho mutation này | Dùng Paxos |
| Phản hồi thành công | Đủ ACK theo write CL | Điều kiện được áp dụng (`[applied] = true`) và đường ghi hoàn tất theo cấu hình |
| Khi cạnh tranh cùng khóa | Các lần ghi có thể đều thành công; dữ liệu hòa giải theo quy tắc Cassandra | Những thao tác CAS cạnh tranh được sắp thứ tự; một điều kiện có thể thất bại |
| Chi phí mạng | Thường thấp hơn | Nhiều trao đổi hơn; tăng độ trễ và mức tranh chấp |
| Dùng cho | Ghi log, trạng thái không yêu cầu CAS, cập nhật chấp nhận ghi đè | Giành quyền sở hữu khóa, kiểm tra phiên bản, chuyển trạng thái có điều kiện |
| Phạm vi bảo vệ | Không có predicate nghiệp vụ | Predicate trên dữ liệu được mô hình hóa trong phạm vi partition/khóa phù hợp |

**Không nhầm lẫn:** tăng mức write CL từ `ONE` lên `QUORUM` hoặc `ALL` không thêm mệnh đề `IF`. Hai khái niệm trả lời hai câu hỏi khác nhau: *bao nhiêu replica xác nhận?* và *mutation có được phép xảy ra khi điều kiện còn đúng không?*

## 5. Ví dụ 1: giữ duy nhất tên người dùng bằng `IF NOT EXISTS`

Giả sử bảng được thiết kế sao cho tên cần bảo vệ chính là partition key:

~~~cql
CREATE TABLE username_owner (
    username text PRIMARY KEY,
    user_id uuid,
    claimed_at timestamp
);
~~~

Hai client cùng gửi:

~~~cql
-- Client A
INSERT INTO username_owner (username, user_id, claimed_at)
VALUES ('minh', aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, toTimestamp(now()))
IF NOT EXISTS;

-- Client B
INSERT INTO username_owner (username, user_id, claimed_at)
VALUES ('minh', bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb, toTimestamp(now()))
IF NOT EXISTS;
~~~

Nếu cả hai đều được xử lý như các LWT trên cùng khóa và không có tác nhân ghi thường chen vào, chỉ một yêu cầu tạo tên thành công; yêu cầu còn lại thấy điều kiện không còn đúng. Ứng dụng phải đọc **`[applied]`**, thay vì chỉ dựa vào việc lệnh CQL không ném exception.

Đối chiếu với:

~~~cql
INSERT INTO username_owner (username, user_id)
VALUES ('minh', aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa);

INSERT INTO username_owner (username, user_id)
VALUES ('minh', bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb);
~~~

Hai lệnh thường không hề kiểm tra quyền sở hữu tên. Việc dữ liệu cuối cùng chỉ chứa một giá trị `user_id` **không** có nghĩa một trong hai người dùng đã nhận được lỗi “trùng tên”.

### Chọn khóa đúng mới bảo vệ được điều cần bảo vệ

Nếu bảng được tạo theo `PRIMARY KEY (user_id)` và `username` chỉ là cột thường, `IF NOT EXISTS` trên mỗi `user_id` **không chặn** hai user khác nhau chọn cùng username. Muốn bảo vệ uniqueness của username, cần có điểm tranh chấp chung — chẳng hạn bảng `username_owner` khóa theo `username` như trên.

Tương tự, một LWT trên một bảng không tự thực hiện atomically mọi thay đổi liên quan ở các bảng khác. Nếu luồng đăng ký còn ghi bảng `user_by_id`, ứng dụng cần thiết kế trình tự, retry và cơ chế bù/đối soát khi bước sau lỗi.

## 6. Ví dụ 2: cập nhật trạng thái theo phiên bản (optimistic concurrency)

Bài toán: hai worker cùng đọc hóa đơn ở `version = 7`, sau đó đều muốn cập nhật nó. Ghi thông thường theo kiểu “đọc trước, ghi sau” có thể khiến một worker ghi đè kết quả của worker kia.

~~~cql
CREATE TABLE invoice_state_by_id (
    invoice_id uuid PRIMARY KEY,
    state text,
    version int,
    updated_at timestamp
);

INSERT INTO invoice_state_by_id (invoice_id, state, version)
VALUES (22222222-2222-2222-2222-222222222222, 'PENDING', 7)
IF NOT EXISTS;
~~~

Khi client đã đọc được `version = 7`, nó tự tính phiên bản mới và đưa cả kỳ vọng vào điều kiện:

~~~cql
UPDATE invoice_state_by_id
SET state = 'PAID',
    version = 8,
    updated_at = toTimestamp(now())
WHERE invoice_id = 22222222-2222-2222-2222-222222222222
IF version = 7;
~~~

- Client A nhận `[applied] = true`: dữ liệu phù hợp điều kiện tại thời điểm LWT thắng, mutation được chấp nhận.
- Client B cũng bắt đầu từ `version = 7` và nhận `[applied] = false` sau khi A cập nhật: B phải đọc lại, tính toán lại và quyết định có thử lại hay trả xung đột lên tầng nghiệp vụ.

Đừng viết logic “SELECT version rồi UPDATE không `IF`” và kỳ vọng mức `QUORUM` giải quyết tranh chấp. Cũng đừng dùng cú pháp `version = version + 1` theo cách tăng bộ đếm SQL thông thường: với cột `int` ở đây, **client tính trước version mới rồi kiểm tra version cũ bằng CAS**.

Với các điều kiện tồn tại thuần túy, Cassandra còn có dạng `UPDATE ... IF EXISTS` và `DELETE ... IF EXISTS`. Chọn `IF version = ?` khi trạng thái/phiên bản hiện tại mới là bất biến cần bảo vệ.

## 7. Hai nhóm consistency level trong LWT

Cassandra có hai cấu hình liên quan nhưng phục vụ các giai đoạn khác nhau:

| Cấu hình | Ý nghĩa | Ví dụ |
|---|---|---|
| **Regular / write consistency** | Số replica cần xác nhận ở giai đoạn ghi/commit mutation | `ONE`, `LOCAL_QUORUM`, `QUORUM` |
| **Serial consistency** | Phạm vi replica tham gia đồng thuận Paxos của LWT | `SERIAL`, `LOCAL_SERIAL` |

Với replication factor là 3 replica trong một datacenter, `LOCAL_QUORUM` thường yêu cầu 2 replica ở datacenter đó để xác nhận. Nhưng các xác nhận này **không thay thế bước Paxos**.

- **`SERIAL`**: phối hợp giai đoạn serial/Paxos trên phạm vi các datacenter cần tham gia; phù hợp khi cần đồng thuận điều kiện ở phạm vi toàn cụm theo topology đang dùng.
- **`LOCAL_SERIAL`**: chỉ phối hợp serial/Paxos trong datacenter địa phương; thường giúp giảm trao đổi xuyên datacenter. Nếu các datacenter có thể đồng thời giành cùng khóa, không được mặc định `LOCAL_SERIAL` bảo đảm một người thắng duy nhất ở phạm vi toàn bộ cluster.

Vì thế cần chọn cặp consistency theo topology và yêu cầu. Với một datacenter có RF=3, cặp thường gặp trong Java là **regular = `LOCAL_QUORUM`**, **serial = `LOCAL_SERIAL`**. Với triển khai đa datacenter đòi hỏi một điều kiện chung toàn cụm, cần đánh giá `SERIAL` và chiến lược replication/commit tương ứng; không sao chép máy móc cấu hình một datacenter.

Không nên áp dụng `SERIAL` hay `LOCAL_SERIAL` như các mức write CL thay thế `QUORUM`: chúng dùng cho **giai đoạn serial** của LWT. Đọc với serial consistency cũng có thể tham gia hoàn tất một Paxos chưa xong, nhưng không làm cho mọi mutation thông thường trở thành CAS.

## 8. Gọi LWT từ Java và xử lý phản hồi

Ví dụ sử dụng **DataStax Java Driver 4.x**. Giả sử `CqlSession session` đã kết nối tới keyspace phù hợp và bảng `username_owner` đã tồn tại:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.util.UUID;

// Trong hàm đăng ký tên; session được quản lý bởi vòng đời ứng dụng.
String username = "minh";
UUID userId = UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");

SimpleStatement claim = SimpleStatement.builder(
        "INSERT INTO username_owner (username, user_id, claimed_at) " +
        "VALUES (?, ?, toTimestamp(now())) IF NOT EXISTS")
    .addPositionalValues(username, userId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .build();

Row outcome = session.execute(claim).one();
if (outcome == null) {
    throw new IllegalStateException("Không nhận được kết quả CAS");
}

if (outcome.getBoolean("[applied]")) {
    // Tên đã được giành thành công bởi yêu cầu này.
} else {
    // Tên đã tồn tại: báo xung đột hoặc xác minh retry của cùng userId.
}
~~~

Đoạn này minh họa cặp consistency cho một datacenter. Khi triển khai đa datacenter, ứng dụng phải lựa chọn serial consistency theo yêu cầu bảo vệ khóa trên toàn bộ topology.

### Ba kiểu kết quả cần phân biệt

1. **`[applied] = true`**: phép so sánh điều kiện thành công và ghi được áp dụng theo giao thức của yêu cầu.
2. **`[applied] = false`**: điều kiện không đúng; đây là **kết quả nghiệp vụ hợp lệ**, không tự động là lỗi hệ thống. Có thể kiểm tra ai đang sở hữu khóa.
3. **Timeout, mất kết nối hoặc exception không rõ kết quả**: trạng thái thao tác có thể **chưa xác định đối với client**. Request có thể đã được chấp nhận ở server dù phản hồi thất lạc. Không được suy ra `applied = false` từ timeout.

Với lệnh giành username, retry bằng **cùng `userId`** và kiểm tra giá trị thực tế khi retry trả `false`: nếu owner bằng chính `userId` của yêu cầu trước, ứng dụng có thể xem đó là thao tác đã thành công trước đó theo quy tắc idempotency của nghiệp vụ; nếu là user khác thì trả xung đột. Không đổi user ID ngẫu nhiên ở mỗi lần thử, và không tạo side effect ngoài Cassandra hai lần chỉ vì client chưa nhận phản hồi.

Với cập nhật dựa trên version, một lần retry sau timeout cần đọc/đối soát trạng thái và version trước khi quyết định tiếp tục. Khi điều kiện `IF version = 7` không còn đúng, thao tác có thể đã thành công trước đó hoặc một thao tác khác đã thay đổi dữ liệu; hãy dùng request ID hay dấu hiệu nghiệp vụ đủ rõ để phân biệt khi cần.

## 9. Khi nào nên dùng đường nào?

**Ưu tiên ghi thông thường** nếu bản chất nghiệp vụ cho phép upsert, giá trị mới thay thế giá trị cũ, hoặc chấp nhận chiến lược hòa giải của Cassandra. Ví dụ: ghi log theo khóa duy nhất, lưu sự kiện append-only (khóa được tạo không trùng), cập nhật telemetry và trạng thái cache có thể tính lại.

**Dùng LWT** nếu yêu cầu phụ thuộc vào **trạng thái hiện hành** và nhiều client có thể cạnh tranh: chỉ cho một người giành tên duy nhất, đổi trạng thái `PENDING → PAID` khi còn `PENDING`, hoặc ghi bản cập nhật nếu version chưa đổi. Luôn xác định **điểm tranh chấp nằm ở partition key nào**, vì đó là cơ sở để condition kiểm tra đúng bất biến.

Các lỗi thiết kế thường gặp:

- **Lạm dụng LWT cho mọi ghi:** Paxos tăng số vòng trao đổi và chi phí vận hành; một partition nóng bị cạnh tranh có thể giảm thông lượng và tăng latency rõ rệt.
- **Tưởng `QUORUM` thay thế `IF`:** quorum xác nhận replica, không kiểm tra điều kiện nghiệp vụ.
- **Dùng `IF NOT EXISTS` trên khóa sai:** hai giá trị business cần unique nhưng nằm ở hai partition khác nhau vẫn có thể cùng thành công.
- **Trộn mutation không điều kiện với mutation LWT lên dữ liệu được bảo vệ:** mutation thường không tuân theo trình tự CAS; cần quy ước mọi đường ghi cùng bất biến đều dùng đúng giao thức.
- **Hiểu `LOCAL_SERIAL` như bảo vệ toàn cluster đa datacenter:** cần quyết định rõ phạm vi cạnh tranh của yêu cầu.
- **Gộp nhiều partition thành một “transaction” tưởng tượng:** LWT không phải giải pháp giao dịch ACID đa partition tùy ý; phải chọn mô hình dữ liệu hoặc giao thức phối hợp nghiệp vụ khác.
- **Coi timeout là thất bại chắc chắn:** cần retry có kiểm soát và đối soát để tránh tạo tác dụng phụ trùng lặp.

### Checklist trước khi chọn LWT

1. Bất biến nào cần giữ: *chưa tồn tại*, *đang ở trạng thái X* hay *version đúng bằng N*?
2. Bất biến đó được biểu diễn tại **một khóa/phân vùng thống nhất** chưa?
3. Tất cả đường cập nhật dữ liệu liên quan có tuân thủ quy tắc điều kiện không?
4. Topology có nhiều datacenter không, và có tranh chấp xuyên datacenter không?
5. Ứng dụng đã xử lý `[applied] = false`, timeout không rõ kết quả và retry idempotent chưa?
6. Tải ghi và mức tranh chấp có chấp nhận latency/throughput của Paxos không?

## 10. Bài tập tự kiểm tra

**Tình huống A.** Hai producer cùng `UPDATE sensor_state SET value = ...` lên một partition với `LOCAL_QUORUM`. Có thể cả hai nhận ACK thành công không? **Có.** Không có CAS; giá trị cell cuối cùng được hòa giải bằng timestamp và các quy tắc Cassandra tương ứng.

**Tình huống B.** Hai người cùng giành `username = 'minh'`, bảng có `PRIMARY KEY (username)`, cả hai dùng `INSERT ... IF NOT EXISTS` với serial consistency thích hợp. Có thể cả hai được `[applied] = true` cho cùng khóa trong cùng trình tự Paxos hợp lệ không? **Không.** Sau khi một yêu cầu tạo khóa, điều kiện của yêu cầu kia không còn đúng.

**Tình huống C.** Ứng dụng dùng `IF version = 7` nhưng một dịch vụ cũ vẫn `UPDATE` không có `IF` lên cùng row. Bất biến phiên bản có chắc còn được bảo vệ không? **Không.** Dịch vụ cũ bỏ qua đường điều kiện.

**Tình huống D.** Java driver ném timeout khi gọi `IF NOT EXISTS`. Có nên gửi ngay thông báo “đăng ký thất bại” và tạo UUID mới để retry không? **Không.** Trạng thái chưa chắc chắn; cần retry cùng danh tính và đối soát owner/version.

## 11. Ghi nhớ

Đường ghi thông thường tối ưu cho việc **phân phối và lưu mutation** theo write consistency level; nó không biết điều kiện nghiệp vụ cần giữ. Đường ghi có `IF` sử dụng **Paxos** để quyết định *có được thực hiện mutation khi trạng thái hiện tại thỏa điều kiện hay không*, đổi lại là latency và chi phí phối hợp cao hơn. Thiết kế bảng theo khóa tranh chấp, phân biệt **write CL** với **serial CL**, và xử lý đúng kết quả `[applied]` cùng timeout là ba điều kiện để dùng LWT an toàn trong ứng dụng Cassandra/Java.
