# Trộn ghi thông thường với LWT và ảnh hưởng đến tính đúng trong Apache Cassandra

## 1. Vì sao đây là vấn đề về tính đúng, không chỉ là hiệu năng?

Trong Apache Cassandra — cơ sở dữ liệu phân tán theo mô hình **wide-column** — ứng dụng thường thiết kế bảng theo truy vấn, dùng **partition key** để định tuyến dữ liệu tới các replica và chọn **consistency level** cho việc đọc, ghi. Ở chương **LWT và đồng thời**, một rủi ro dễ bị bỏ qua là: **một số ứng dụng dùng lệnh có `IF` để bảo vệ trạng thái, trong khi những ứng dụng khác vẫn ghi trực tiếp lên chính dữ liệu đó**.

Hai kiểu thao tác có mục đích khác nhau:

- **Ghi thông thường (regular write):** `INSERT`, `UPDATE`, `DELETE` không chứa `IF`. Coordinator gửi mutation đến replica và chờ đủ xác nhận theo write consistency level; không bắt buộc phải thỏa một điều kiện trên giá trị hiện hành.
- **Ghi có điều kiện (lightweight transaction, LWT):** câu lệnh như `INSERT ... IF NOT EXISTS`, `UPDATE ... IF status = 'OPEN'`, `DELETE ... IF version = 3`. Giai đoạn **Paxos** tổ chức quyết định *compare-and-set* (CAS); client nhận `[applied] = true` hoặc `false`.

Khi mọi thao tác tranh chấp một bất biến đều đi qua LWT và được định tuyến, cấu hình đồng thuận đúng, Cassandra có thể sắp thứ tự các thao tác CAS liên quan. Nhưng **lệnh ghi thông thường không trở thành một phần của trật tự CAS chỉ vì cùng bảng, cùng khóa, cùng consistency level hoặc chạy cùng lúc**.

> Quy tắc thiết kế: muốn LWT thực thi một quy tắc nghiệp vụ, **mọi đường ghi có khả năng thay đổi dữ liệu mà quy tắc ấy phụ thuộc phải cùng tôn trọng quy tắc**. Chỉ thêm `IF` vào một nơi trong ứng dụng là chưa đủ.

## 2. Hiểu đúng sự khác nhau giữa hai đường ghi

Một mutation thông thường chỉ cần đủ replica xác nhận. Nếu hai client cập nhật cùng một cell, Cassandra hòa giải dữ liệu dựa trên timestamp mutation và các quy tắc tương ứng, chứ không bảo đảm *ai được ACK sau sẽ thắng*. Các cell có thể được hòa giải riêng: giá trị `status` có thể đến từ một mutation trong khi `version` đến từ mutation khác.

Với LWT, coordinator tham gia giao thức Paxos để xác định điều kiện `IF` có đúng hay không và để chấp nhận hoặc từ chối mutation có điều kiện. Phần **serial consistency** quyết định phạm vi đồng thuận; phần **regular write consistency** điều khiển xác nhận commit/ghi. LWT cung cấp tính chất *linearizable* cho chuỗi thao tác điều kiện phù hợp trên cùng phạm vi được bảo vệ, **không phải giao dịch ACID tùy ý trên nhiều partition**.

Điểm cần ghi nhớ: **Paxos không ngăn một client gửi mutation thông thường vào cùng row khi một LWT đang xử lý**. Mutation thường không bị bắt buộc kiểm tra `IF` hoặc tham gia quyết định Paxos. Vì vậy, không thể suy luận tính đúng của toàn bộ lịch sử ghi từ riêng kết quả của các LWT.

| Thuộc tính | LWT trên dữ liệu được bảo vệ | Ghi thông thường trên cùng dữ liệu |
|---|---|---|
| Có kiểm tra predicate hiện hành trước khi chấp nhận? | Có, qua `IF` và Paxos | Không |
| Có phản hồi `[applied]`? | Có | Không |
| Có tham gia thứ tự các lần CAS cùng khóa? | Có, khi cấu hình/phạm vi phù hợp | Không |
| Có thể được ACK dù vi phạm quy tắc của LWT khác? | Điều kiện sai thì `[applied] = false` | Có |
| Nâng write CL lên `QUORUM` có thêm CAS? | Không cần vì đã có `IF` | Không |
| Giá trị cùng cell được lưu/hòa giải ở replica? | Vẫn thuộc cơ chế lưu trữ Cassandra | Vẫn thuộc cơ chế lưu trữ Cassandra |

## 3. Phản ví dụ: một LWT đúng vẫn dẫn đến trạng thái sai

Giả sử dịch vụ đặt chỗ cần duy trì bất biến:

**Khi `status = 'HELD'` và `version = 1`, phải có chủ sở hữu; một lệnh hủy chỉ được thực hiện theo chính sách có kiểm tra trạng thái/phiên bản.**

Bảng được thiết kế theo truy vấn tra cứu đặt chỗ bằng `reservation_id`:

~~~cql
CREATE TABLE reservation_by_id (
    reservation_id uuid PRIMARY KEY,
    status text,
    version int,
    holder_id uuid,
    updated_at timestamp
);
~~~

Dữ liệu ban đầu được khởi tạo **trước khi có yêu cầu cạnh tranh**:

~~~cql
INSERT INTO reservation_by_id
    (reservation_id, status, version)
VALUES
    (11111111-1111-1111-1111-111111111111, 'OPEN', 0);
~~~

### 3.1. Dịch vụ mới dùng LWT

Một người dùng cố gắng giữ chỗ:

~~~cql
UPDATE reservation_by_id
SET status = 'HELD',
    version = 1,
    holder_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
WHERE reservation_id = 11111111-1111-1111-1111-111111111111
IF status = 'OPEN' AND version = 0;
~~~

Nếu nhận `[applied] = true`, LWT đã chấp nhận chuyển trạng thái vì điều kiện đúng tại điểm đồng thuận của nó.

### 3.2. Dịch vụ cũ vẫn ghi thông thường

Một job cũ hoặc API hủy chỗ vẫn gọi:

~~~cql
UPDATE reservation_by_id
SET status = 'CANCELLED'
WHERE reservation_id = 11111111-1111-1111-1111-111111111111;
~~~

Không có `IF`, nên lệnh này không kiểm tra `status` hoặc `version`; một write CL cao không thêm điều kiện bị thiếu.

### 3.3. Điều gì có thể xảy ra?

Giả sử LWT giữ chỗ thành công và mutation hủy có timestamp thắng ở **cell `status`**. Kết quả lưu cuối cùng có thể là:

| Cột | Giá trị |
|---|---|
| `status` | `CANCELLED` |
| `version` | `1` |
| `holder_id` | `aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` |

Client giữ chỗ đã nhận `[applied] = true`; dịch vụ hủy cũng đã nhận ACK ghi thành công. Nhưng kết hợp giá trị cuối cùng có thể vi phạm quy tắc quy trình đặt chỗ mà nhóm phát triển tưởng `IF` bảo vệ.

Nếu một dịch vụ cũ còn ghi trực tiếp cả `version = 0`, một timestamp thắng có thể đưa version lùi về 0, khiến bước CAS sau đó đánh giá trên trạng thái không phản ánh tiến trình nghiệp vụ. Không thể lấy thứ tự request đến coordinator hoặc thứ tự ACK làm cách chứng minh an toàn vì Cassandra hòa giải mutation theo quy tắc riêng.

~~~mermaid
sequenceDiagram
    participant A as Dịch vụ mới
    participant C as Cassandra
    participant B as Dịch vụ cũ
    Note over A,B: Ban đầu: OPEN, version=0
    A->>C: UPDATE ... IF status='OPEN' AND version=0
    C-->>A: [applied] = true
    B->>C: UPDATE status='CANCELLED' (không IF)
    C-->>B: ACK theo write CL
    Note over A,B: Có thể còn CANCELLED, version=1, holder=A
~~~

Sơ đồ là **một lịch thực thi có thể xảy ra**, không phải cam kết rằng kết quả ấy luôn xuất hiện. Việc lệnh nào thắng ở từng cell phụ thuộc vào mutation, timestamp và các điều kiện phân tán cụ thể.

## 4. Những hiểu nhầm dẫn tới lỗi đồng thời

### Hiểu nhầm 1: “LWT khóa row, nên ghi thường sẽ phải chờ”

LWT không cung cấp một khóa ứng dụng mà mọi client ghi Cassandra bắt buộc tuân thủ. Nó tổ chức đồng thuận Paxos giữa các replica cho thao tác có điều kiện. Ghi thường không tự xếp hàng đợi cho tới khi LWT hoàn tất.

**Hệ quả:** có thể nhận `[applied] = true` mà một mutation thường vẫn làm thay đổi dữ liệu được bảo vệ ngay sau đó, hoặc cạnh tranh trong lúc LWT đang xử lý.

### Hiểu nhầm 2: “Hai lệnh đều dùng `QUORUM` thì không thể xung đột”

`QUORUM` (hoặc `LOCAL_QUORUM` trong topology phù hợp) trả lời câu hỏi **cần bao nhiêu replica xác nhận**. Nó không trả lời câu hỏi **có được phép đổi trạng thái khi trạng thái cũ là gì**. Hai request đều có thể đạt quorum, nhưng không hề kiểm tra cùng predicate.

**Hệ quả:** tăng consistency level có thể giúp một số thuộc tính quan sát/hội tụ của dữ liệu, nhưng không thay cho CAS.

### Hiểu nhầm 3: “`SERIAL` hoặc `LOCAL_SERIAL` tự bảo vệ mọi truy cập đến partition”

Serial consistency được sử dụng cho **giai đoạn Paxos** của LWT và cho một số serial read. Một mutation không có `IF` không trở thành conditional mutation chỉ vì ứng dụng đang sử dụng LWT ở nơi khác.

**Hệ quả:** một hệ thống dùng đúng `SERIAL` cho thao tác giành quyền nhưng vẫn cho phép API quản trị cập nhật trực tiếp cùng field thì bất biến có thể bị phá vỡ.

### Hiểu nhầm 4: “Nếu cuối cùng replica đồng bộ thì dữ liệu sẽ hợp lệ”

Repair, read repair (tùy phiên bản và cấu hình), hinted handoff, compaction và cơ chế chống entropy có mục đích liên quan đến **nhất quán bản sao và lưu trữ**. Chúng không tự biết rằng `status='CANCELLED'` đi với `holder_id` hiện tại là không hợp lệ theo nghiệp vụ.

**Hệ quả:** hệ thống có thể hội tụ về **một trạng thái giống nhau nhưng sai về mặt nghiệp vụ**.

### Hiểu nhầm 5: “CQL `BATCH` sẽ giải quyết mọi race”

Một batch không tự biến toàn bộ những writer khác trên cùng partition thành thao tác tham gia Paxos. Batching cũng không tạo một giao dịch với tính cách ly và điều kiện tùy ý xuyên nhiều partition. Khi cần bảo vệ bất biến, phải xác định phạm vi một partition, câu lệnh điều kiện hợp lệ và **tất cả tác nhân ghi liên quan**.

## 5. Khi nào trộn hai đường ghi thực sự nguy hiểm?

Không phải mọi mutation thường và LWT cùng **bảng** đều là lỗi. Cần xác định liệu chúng có cùng tác động lên **bất biến** hay không.

| Tình huống | Đánh giá |
|---|---|
| LWT kiểm tra `version` và thay `status`; dịch vụ cũ cập nhật `status` không `IF` | Nguy hiểm: bỏ qua quy tắc chuyển trạng thái |
| LWT giành `username`; job import ghi `username_owner` trực tiếp | Nguy hiểm: có thể cướp quyền sở hữu hoặc ghi đè |
| LWT cập nhật `status` và `version`; job thay `version` trực tiếp | Nguy hiểm: vô hiệu hóa kiểm tra phiên bản |
| LWT bảo vệ `status`; một lệnh chỉ ghi dữ liệu độc lập, không liên quan tới điều kiện và bất biến | Có thể chấp nhận, nhưng phải chứng minh thực sự độc lập |
| Ghi thường vào các partition khác, không chia sẻ ràng buộc nghiệp vụ | Thường không xung đột trực tiếp với CAS trên partition đang xét |
| Đưa một trường cần unique ở hai partition và chạy LWT riêng trên mỗi partition | Không đủ để bảo đảm unique toàn cục |

**Nguyên tắc rà soát:** hỏi *“Một mutation thường có thể thay đổi bất kỳ field nào khiến điều kiện `IF`, hành động sau CAS, hoặc quy tắc chuyển trạng thái trở nên sai không?”* Nếu có, hai đường ghi không thể được coi là an toàn khi chạy cạnh tranh.

### Tình huống uniqueness: `IF NOT EXISTS` vẫn bị phá

Bảng:

~~~cql
CREATE TABLE username_owner (
    username text PRIMARY KEY,
    user_id uuid
);
~~~

API đăng ký mới dùng:

~~~cql
INSERT INTO username_owner (username, user_id)
VALUES ('minh', aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa)
IF NOT EXISTS;
~~~

Nhưng một tác vụ import dùng:

~~~cql
INSERT INTO username_owner (username, user_id)
VALUES ('minh', bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb);
~~~

Tác vụ import không kiểm tra `IF NOT EXISTS`. Nếu mutation của nó thắng ở cell `user_id`, owner cuối cùng có thể không còn là user vừa được API báo đăng ký thành công. Bất biến *“một khi tên được cấp thì không bị người khác cướp bằng cùng API quy định”* đã thất bại vì một đường ghi bỏ qua giao thức.

Không nên dùng `IF NOT EXISTS` trên khóa `user_id` để kỳ vọng uniqueness của `username`: hai user khác nhau sẽ khóa vào hai partition khác nhau. **Partition key phải biểu diễn đúng đối tượng tranh chấp.**

## 6. Bảo vệ bất biến theo một giao thức ghi nhất quán

### 6.1. Đặt quy tắc chuyển trạng thái ở điểm ghi

Khi giữ chỗ, sử dụng một điều kiện phản ánh cả status và version:

~~~cql
UPDATE reservation_by_id
SET status = 'HELD',
    version = 1,
    holder_id = aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
WHERE reservation_id = 11111111-1111-1111-1111-111111111111
IF status = 'OPEN' AND version = 0;
~~~

Khi hủy, dịch vụ mới cũng phải áp dụng quy tắc đã thống nhất, ví dụ **chỉ hủy chỗ chưa ai giữ**:

~~~cql
UPDATE reservation_by_id
SET status = 'CANCELLED',
    version = 1
WHERE reservation_id = 11111111-1111-1111-1111-111111111111
IF status = 'OPEN' AND version = 0;
~~~

Khi hai lời gọi trên cùng bắt đầu từ `OPEN, version=0` và cùng tham gia Paxos với phạm vi phù hợp, **chỉ một phép chuyển trạng thái có thể áp dụng thành công**; phép kia nhận `[applied] = false` và phải xử lý xung đột.

Không cần luôn kiểm tra cả status lẫn version: predicate nào là đủ còn phụ thuộc trạng thái nghiệp vụ. Nhưng một số đường ghi có `IF` và số khác có thể cập nhật field được bảo vệ mà không `IF` thì không tạo được cam kết như trên.

### 6.2. Quy ước mọi writer chạm bất biến

Liệt kê tất cả tác nhân có thể sửa các cột bảo vệ: API công khai, job định kỳ, backfill, import/export, script vận hành, consumer message, dịch vụ cũ và công cụ quản trị. Sau đó:

1. **Xác định bất biến rõ bằng văn bản:** ví dụ một chỗ chỉ có một holder và chỉ chuyển `OPEN → HELD` hoặc `OPEN → CANCELLED`.
2. **Xác định điểm đồng thuận duy nhất:** dùng một partition theo `reservation_id`, hoặc bảng theo khóa business cần unique như `username`.
3. **Đưa tất cả mutation tác động đến bất biến qua CQL có `IF` thích hợp:** kể cả tác vụ bảo trì hoặc cổng quản trị.
4. **Cấm đường ghi tắt bằng quy ước và kiểm soát kiến trúc:** dùng một DAO/service ghi dùng chung, hạn chế quyền ghi của các job không cần, rà soát những câu CQL làm thay đổi field quan trọng.
5. **Xử lý xung đột đúng nghĩa:** `[applied] = false` là kết quả một điều kiện không thỏa, không phải lỗi replica; đọc/đối chiếu dữ liệu và trả về lỗi nghiệp vụ hoặc tính lại thao tác.
6. **Giám sát quá trình chuyển đổi:** phát hiện mutation không có `IF` chạm field được bảo vệ, soát log ứng dụng và đối chiếu các trạng thái không hợp lệ.

Đối với field **hoàn toàn độc lập** với predicate và bất biến, ghi thường có thể là lựa chọn hợp lý để tránh chi phí Paxos; điều kiện tiên quyết là tính độc lập được chứng minh, thay vì chỉ vì field nằm khác cột.

### 6.3. Không giả định deployment từng phần lập tức an toàn

Một cuộc chuyển đổi từ regular writes sang LWT cần xem xét giai đoạn hai phiên bản ứng dụng chạy song song:

~~~text
Trước chuyển đổi:       A ghi thường, B ghi thường
Triển khai từng phần:   A dùng LWT, B vẫn ghi thường  <-- cửa sổ nguy hiểm
Sau chuyển đổi:         A dùng LWT, B dùng LWT
~~~

Trong cửa sổ giữa, hệ thống vẫn có thể vi phạm bất biến. Một cách chuyển đổi có kiểm soát là đưa mọi writer qua một cổng cập nhật chung hoặc tạm ngừng những luồng ghi ảnh hưởng tới bất biến, kết thúc request đang xử lý, đối soát dữ liệu hiện hữu, rồi cho phép traffic trở lại theo giao thức mới. Thứ tự cụ thể tùy kiến trúc và yêu cầu sẵn sàng của hệ thống.

**Dữ liệu đã sai trước khi chuyển đổi không tự sửa lại chỉ vì các request mới đã dùng LWT.** Cần rà soát và giải quyết chủ sở hữu trùng, trạng thái không hợp lệ và phiên bản bị lệch.

## 7. Ứng dụng Java: đưa điều kiện vào đúng câu lệnh ghi

Ví dụ dùng **DataStax Java Driver 4.x**, với `CqlSession session` đã kết nối tới keyspace, bảng `reservation_by_id` đã được tạo. Toàn bộ service cập nhật status nên dùng một API yêu cầu `expectedVersion` và `expectedStatus`; không cho caller tự thực hiện `UPDATE ... SET status = ? WHERE ...` khi thao tác đó có ảnh hưởng tới bất biến.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

// Chuẩn bị một lần và tái sử dụng PreparedStatement trong service.
PreparedStatement hold = session.prepare(
    "UPDATE reservation_by_id " +
    "SET status = ?, version = ?, holder_id = ? " +
    "WHERE reservation_id = ? " +
    "IF status = ? AND version = ?"
);

UUID reservationId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");
UUID userId =
    UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
int expectedVersion = 0;

BoundStatement statement = hold.bind(
        "HELD", expectedVersion + 1, userId,
        reservationId, "OPEN", expectedVersion)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

Row result = session.execute(statement).one();
if (result == null) {
    throw new IllegalStateException("Không có phản hồi CAS");
}

if (result.getBoolean("[applied]")) {
    // Thành công: thao tác giữ chỗ được chấp nhận.
} else {
    // Xung đột: đọc trạng thái mới và xử lý theo quy tắc nghiệp vụ.
}
~~~

Đây là cấu hình minh họa cho **một datacenter có replication phù hợp**, thường với RF=3. `LOCAL_QUORUM` là write consistency; `LOCAL_SERIAL` là serial consistency cho Paxos. Với nhiều datacenter cùng có thể tranh chấp khóa, phải thiết kế phạm vi serial consistency (cân nhắc `SERIAL`) và chiến lược replication theo yêu cầu của hệ thống. **Cấu hình consistency hợp lý không cứu được một writer vẫn bỏ `IF`.**

Đừng tạo một bản sao API “nhanh hơn” dùng lệnh thường để đổi `status` khi gặp tải cao. Nếu latency LWT thành nút thắt, cần xem lại mức tranh chấp, cách phân vùng và yêu cầu nghiệp vụ, thay vì âm thầm bỏ kiểm tra.

### 7.1. Ba kết quả ứng dụng phải phân biệt

| Phản hồi từ Cassandra | Ý nghĩa đối với client | Cách xử lý |
|---|---|---|
| `[applied] = true` | Condition được chấp nhận, mutation LWT hoàn tất theo giao thức request | Xử lý thành công nghiệp vụ |
| `[applied] = false` | Condition đã không thỏa | Đọc/đối chiếu trạng thái, trả conflict hoặc tính lại thao tác |
| Timeout / lỗi kết nối | Không chắc kết quả đã được áp dụng hay chưa | Đối soát, retry có kiểm soát và giữ danh tính request |

Một timeout không đồng nghĩa điều kiện đã thất bại. Nếu gửi lại thao tác sau timeout, cần phân biệt **lần thử lại của cùng một nghiệp vụ** với một lệnh cập nhật khác. Ví dụ có thể lưu `operation_id` hoặc quy ước chuyển trạng thái đủ để nhận biết thao tác trước đã thành công; không được phát sinh thêm thanh toán, phát notification hoặc tạo sự kiện lặp chỉ vì chưa nhận ACK.

### 7.2. Quy trình đọc rồi ghi không có `IF` vẫn có race

Đoạn pseudocode sau **không** thay CAS:

~~~java
// KHÔNG an toàn khi có nhiều writer:
Row current = session.execute(readState).one();
if ("OPEN".equals(current.getString("status"))) {
    session.execute(
        SimpleStatement.newInstance(
            "UPDATE reservation_by_id SET status = 'HELD' " +
            "WHERE reservation_id = ?", reservationId));
}
~~~

Một writer khác có thể sửa row **sau SELECT nhưng trước UPDATE**. Ngay cả khi SELECT và UPDATE đều dùng `QUORUM`, không có điều kiện nguyên tử buộc giá trị lúc ghi vẫn là `OPEN`. Thay bằng một câu `UPDATE ... IF status = 'OPEN'` (và version nếu cần).

## 8. Ảnh hưởng của mô hình dữ liệu và thao tác đa bảng

Trong Cassandra, cùng một đối tượng nghiệp vụ thường được phi chuẩn hóa thành nhiều bảng theo truy vấn. Ví dụ, dịch vụ đăng ký có thể lưu:

- `username_owner` theo khóa `username` để giành duy nhất tên.
- `user_by_id` theo khóa `user_id` để tra cứu hồ sơ.

LWT ở `username_owner` chỉ bảo vệ điều kiện trên điểm tranh chấp được thiết kế. Nó không biến ghi tiếp theo tới `user_by_id` thành một transaction toàn cục. Nếu ghi hồ sơ sau khi giành tên bị lỗi, cần retry, quy trình hoàn tất lại hoặc cơ chế đối soát/bù phù hợp.

Lỗi nguy hiểm trong trường hợp trộn đường ghi là một job sửa `username_owner` bằng regular update chỉ vì nó “đồng bộ” từ `user_by_id`. Job đó có thể ghi đè kết quả CAS của API đăng ký. Phải xác định **bảng/partition nào là nguồn quyết định quyền sở hữu** và ai được phép thay đổi nó.

Cần phân biệt hai tầng tính đúng:

1. **Tính đúng đồng thời tại điểm quyết định:** mọi thay đổi ảnh hưởng đến predicate cùng tôn trọng CAS.
2. **Tính đúng xuyên bảng và xuyên bước nghiệp vụ:** retry/idempotency và đối soát đảm bảo các bảng được cập nhật theo tiến trình hợp lệ.

LWT giúp giải quyết tầng thứ nhất khi được dùng nhất quán; tầng thứ hai vẫn cần thiết kế ứng dụng.

## 9. Quan sát, kiểm thử và khắc phục hệ thống đã trộn write path

### Dấu hiệu cần điều tra

- Hai request cùng nhận “giành quyền thành công”, hoặc một request thành công nhưng sau đó owner đổi bất ngờ.
- `status` và `version` không tương ứng với cùng một bước chuyển trạng thái.
- Tỷ lệ `[applied] = false` tăng bất thường, nhất là sau khi thêm worker/batch job.
- Tình trạng xuất hiện sau deploy từng phần, chạy backfill hoặc kích hoạt một job cũ.
- Thao tác sửa dữ liệu thủ công làm một request LWT hợp lệ ngay trước đó bị mất hiệu lực.

Không được dựa duy nhất vào các tín hiệu này để kết luận nguyên nhân: chúng cũng có thể xuất phát từ lỗi model dữ liệu, phiên bản ứng dụng, timestamp, retry hoặc thao tác khác. Cần đối chiếu **câu CQL thực tế** và mọi producer viết cùng khóa.

### Kiểm thử cạnh tranh có chủ đích

Tạo một test tích hợp trên môi trường Cassandra phù hợp, sử dụng cùng `reservation_id`:

1. Khởi tạo trạng thái `OPEN, version=0`.
2. Cho N client cùng gửi hai câu CAS trái nhau (`HELD` và `CANCELLED`) với cùng điều kiện.
3. Xác nhận trong các lần thử có điều kiện cạnh tranh đúng trên cùng trạng thái ban đầu, **tối đa một** mutation từ `OPEN, version=0` được `[applied] = true`.
4. Thử thay một client bằng câu `UPDATE ... SET status = ...` không `IF`; quan sát rằng câu ghi này không có `[applied]` và có thể tạo trạng thái nằm ngoài quy tắc ứng dụng.
5. Chạy lại với timeout/network failure được mô phỏng; kiểm tra ứng dụng không tuyên bố sai “thất bại chắc chắn” và không lặp tác dụng phụ.

Test không chứng minh hết mọi interleaving trong production, nhưng giúp phát hiện sớm việc một đường ghi bỏ qua condition. Một hướng bảo vệ quan trọng khác là tìm trong codebase mọi câu `INSERT`/`UPDATE`/`DELETE` nhắm tới bảng chứa trạng thái quan trọng và đưa chúng qua review thiết kế.

### Khi đã có dữ liệu không hợp lệ

Trước tiên xác định và dừng/điều chỉnh **writer đang bỏ qua quy tắc**. Sau đó lập quy trình sửa dữ liệu dựa trên nguồn sự thật nghiệp vụ: đối soát owner, trạng thái, version, operation ID và các bước liên quan. Nếu sửa bằng regular update trực tiếp trên field được bảo vệ trong khi traffic LWT vẫn chạy, chính quy trình sửa có thể tái tạo lỗi. Hãy áp dụng quy trình điều phối cho dữ liệu nóng hoặc đóng băng các mutation liên quan trong giai đoạn sửa.

Repair và compaction phục vụ lưu trữ/đồng bộ replica; chúng **không thay** bước sửa logic nghiệp vụ.

## 10. Bài tập tình huống

**Bài 1.** Hệ thống có bảng khóa `username`. API mới gọi `INSERT ... IF NOT EXISTS`, nhưng script import ghi `INSERT` thường lên cùng username. Có thể cam kết uniqueness/ownership ổn định không?

**Đáp án:** Không. Script import không tuân theo CAS nên có thể ghi đè `user_id`; mọi đường thay chủ sở hữu phải phối hợp theo cùng chính sách.

**Bài 2.** Dịch vụ A dùng `UPDATE ... IF version = 4`, dịch vụ B dùng `UPDATE` thường nhưng cả hai đều chọn `QUORUM`. Thêm `QUORUM` vào cả hai có giải quyết race không?

**Đáp án:** Không. Quorum chỉ xác định điều kiện ACK, không tạo compare-and-set cho lệnh B.

**Bài 3.** Job analytics viết riêng một cột `last_seen_at` không tham gia predicate, không ảnh hưởng bất biến và không được service sử dụng để quyết định chuyển trạng thái. Có bắt buộc mọi cập nhật `last_seen_at` dùng LWT không?

**Đáp án:** Không nhất thiết. Có thể dùng ghi thường nếu chứng minh cột này thực sự độc lập với quy tắc được bảo vệ và không bị những yêu cầu khác hiểu nhầm là một phần của snapshot trạng thái nguyên tử.

**Bài 4.** Sau khi tất cả service đã chuyển sang LWT, một số row vẫn có `version=0` dù `status='HELD'`. LWT ở thời điểm hiện tại có tự sửa mọi row cũ không?

**Đáp án:** Không. Cần xác định nguồn lỗi lịch sử và đối soát dữ liệu; CAS mới không tự chữa một trạng thái cũ không hợp lệ.

## 11. Tổng kết quy tắc vận hành

- **Bảo vệ đúng bất biến:** dùng `IF` trên điểm tranh chấp được biểu diễn bằng khóa/phân vùng thích hợp.
- **Bảo vệ mọi lối vào:** mọi producer có thể sửa field thuộc bất biến phải tuân theo cùng giao thức; không trộn regular write vào các lối ghi cạnh tranh ấy.
- **Không nhầm consistency với điều kiện:** `ONE`, `LOCAL_QUORUM`, `QUORUM` quyết định ACK; `SERIAL`, `LOCAL_SERIAL` phục vụ giai đoạn Paxos, không tự ép regular write tuân theo CAS.
- **Xử lý xung đột và timeout:** `[applied] = false` là điều kiện không thỏa; timeout có thể để lại kết quả chưa rõ, cần retry/đối soát có kiểm soát.
- **Khép kín toàn bộ luồng:** nếu dữ liệu được phi chuẩn hóa qua nhiều bảng hoặc nhiều hệ thống, thêm chiến lược idempotency, bù và đối soát.

**Kết luận:** LWT không phải một lớp khóa chung bao quanh toàn bộ bảng Cassandra. Cam kết điều kiện chỉ có ý nghĩa khi các đường ghi có thể phá vỡ cùng bất biến được thiết kế cùng nhau. Một writer còn dùng mutation thông thường lên dữ liệu được bảo vệ có thể khiến **cả LWT lẫn lệnh thường đều báo thành công mà hệ thống vẫn đi tới trạng thái sai**.
