# Mẫu tạo định danh duy nhất trong phạm vi được bảo đảm

Trong Apache Cassandra, một giá trị **duy nhất** có thể mang hai nghĩa rất khác nhau: ứng dụng *tự sinh giá trị có xác suất trùng cực thấp* hoặc hệ thống *thật sự từ chối người thứ hai đăng ký cùng giá trị*. Bài này thuộc chương **LWT và đồng thời**, giải thích cách dùng **Lightweight Transaction (LWT)** với điều kiện **IF NOT EXISTS** để bảo đảm một định danh không bị hai yêu cầu đồng thời chiếm giữ, đồng thời xác định chính xác **phạm vi** mà sự bảo đảm đó có hiệu lực.

Đây là một mẫu thiết kế cụ thể trong mô-đun **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**: người học sử dụng khóa phân vùng và mô hình wide-column theo truy vấn, thực hành CQL/Java driver, cân nhắc replication và mức nhất quán, rồi xử lý retry, timeout và lỗi từng bước. LWT cung cấp phép **compare-and-set (CAS)** trên partition; nó không tự tạo ra một ràng buộc UNIQUE trên cột bất kỳ hoặc một giao dịch tổng quát giữa nhiều partition.

## 1. Kết quả mong đợi

Sau bài này, bạn có thể:

1. Xác định đúng phạm vi duy nhất: toàn hệ thống, theo tenant, theo ngày, theo namespace hoặc chỉ theo một khóa chính.
2. Phân biệt **UUID/timeuuid có xác suất trùng thấp** với **duy nhất được cưỡng chế bằng LWT**.
3. Thiết kế partition key để mọi yêu cầu tranh cùng một định danh đều đi qua **cùng một hàng/partition điều kiện**.
4. Dùng **INSERT ... IF NOT EXISTS** và đọc kết quả **[applied]** để phân xử cạnh tranh.
5. Hiểu ranh giới giữa **claim định danh** và **ghi hồ sơ nghiệp vụ** ở một partition khác.
6. Triển khai retry an toàn trong Java, kể cả khi yêu cầu LWT timeout và kết quả ghi chưa rõ.
7. Chọn consistency level, viết kịch bản kiểm thử cạnh tranh và theo dõi chi phí vận hành.

## 2. “Duy nhất” phải có một phạm vi rõ ràng

Tưởng tượng dịch vụ đăng ký có tenant A và tenant B. Hai người cùng muốn tên đăng nhập **an**.

| Quy tắc nghiệp vụ | Ví dụ khóa cần bảo vệ | Hai tenant cùng dùng “an”? |
| --- | --- | --- |
| Tên đăng nhập duy nhất **toàn hệ thống** | handle = an | Không |
| Tên đăng nhập duy nhất **trong từng tenant** | (tenant A, an), (tenant B, an) | Có |
| Mã vé duy nhất **trong từng sự kiện** | (event ID, ticket code) | Có thể trùng mã ở sự kiện khác |
| Mã đơn hàng duy nhất **mỗi ngày** | (ngày UTC, order code) | Có thể tái sử dụng ở ngày khác nếu quy định cho phép |
| Khóa bản ghi duy nhất | record_id | Chỉ bảo đảm không có hai hàng có cùng khóa chính, chưa bảo đảm các cột khác là duy nhất |

Định nghĩa bằng lời phải được ánh xạ thành **một khóa kiểm soát xác định**. Nếu chính sách là “duy nhất trong tenant”, khóa nên chứa **tenant_id và tên đã chuẩn hóa**. Khi hai client cùng đăng ký cùng một tên trong tenant A, chúng phải cùng đụng vào **một partition key**; nếu mỗi client tự tạo một UUID rồi ghi vào hai partition khác nhau, Cassandra không có gì để ngăn cả hai.

### Hai loại định danh thường gặp

**Định danh máy sinh**: UUID ngẫu nhiên (ví dụ UUID v4) rất phù hợp cho ID bản ghi phân tán khi chấp nhận rủi ro trùng cực nhỏ. TimeUUID thêm thành phần thời gian để phục vụ thứ tự và truy vấn theo thời gian, nhưng không phải cơ chế khóa duy nhất do DB cưỡng chế. Nếu yêu cầu “không bao giờ chấp nhận một khóa đã dùng”, dùng conditional insert trên **chính khóa ID**.

**Định danh nghiệp vụ**: email, username, số hợp đồng, mã voucher… có thể trùng do người dùng cố ý chọn giống nhau. Ở đây chỉ sinh UUID cho account_id là **chưa đủ**. Cần bảo vệ giá trị nghiệp vụ bằng một **hàng claim (giữ chỗ)** có khóa chính là định danh được bảo vệ.

## 3. Cơ chế LWT bảo vệ cạnh tranh như thế nào?

Một INSERT CQL thông thường là thao tác kiểu *upsert*: nếu hàng đã có, ghi có thể cập nhật/ghi đè các cột theo quy tắc timestamp; không tự trả lỗi duplicate key như nhiều RDBMS.

~~~sql
-- Nếu record_id đã tồn tại, đây không phải kiểm tra trùng.
INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'new value');
~~~

Khi thêm **IF NOT EXISTS**, Cassandra thực hiện LWT dựa trên **Paxos**, để những đề nghị cạnh tranh đối với **cùng partition** được giải quyết theo thứ tự có thể quan sát như một phép CAS:

~~~sql
INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'new value')
IF NOT EXISTS;
~~~

Nếu thành công, kết quả CQL có **[applied] = true**. Nếu khóa đã được ghi, **[applied] = false**, và kết quả có thể bao gồm dữ liệu hiện tại của hàng để ứng dụng quyết định đó là xung đột hay retry của cùng yêu cầu.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant C as Cassandra / Paxos
    participant B as Client B
    A->>C: INSERT key=an IF NOT EXISTS
    B->>C: INSERT key=an IF NOT EXISTS
    C-->>A: applied=true (một người thắng)
    C-->>B: applied=false (đã có chủ)
    Note over A,B: Thứ tự A/B chỉ minh họa; ai thắng phụ thuộc thực thi
~~~

**Phạm vi bảo đảm** là điều kiện trên cùng khóa/partition mà những người tham gia đều sử dụng. Nó không có nghĩa “duy nhất tất cả giá trị của một cột trong mọi bảng”; Cassandra không hỗ trợ một UNIQUE constraint toàn cục tùy ý cho cột không phải khóa bằng việc thêm IF vào bảng có partition key khác.

### Hai mức nhất quán khi viết LWT

Một conditional statement có hai thuộc tính khác nhau:

- **Serial consistency** (**SERIAL** hoặc **LOCAL_SERIAL**): điều khiển giai đoạn Paxos xác nhận điều kiện và sắp thứ tự các CAS.
- **Regular consistency** (ví dụ **LOCAL_QUORUM**): áp dụng cho giai đoạn ghi/commit và ảnh hưởng tới việc các đọc thường có thể quan sát ghi vừa thành công như thế nào.

~~~sql
-- Lệnh dành cho cqlsh; không phải cú pháp CQL gửi từ Java driver.
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;
~~~

Với hệ thống nhiều DC và yêu cầu **duy nhất trên toàn bộ cụm**, cần thiết kế miền điều phối nhất quán: dùng SERIAL để phối hợp trên phạm vi phù hợp và kiểm chứng hành vi trong cấu hình đa DC. LOCAL_SERIAL chỉ thực hiện pha serial ở DC cục bộ, nên không được giả định mặc nhiên rằng hai vùng đều nhận claim cùng lúc mà vẫn có bảo đảm độc nhất **toàn cụm**. Một phương án đơn giản khác là định tuyến mọi thao tác claim của cùng namespace về một DC chủ quản và quy định rõ failover. Độ sẵn sàng của LWT giảm khi không đủ replica cho consensus hoặc commit: gặp lỗi timeout **không có nghĩa** điều kiện đã thất bại.

## 4. Mẫu 1 — ID cũng là khóa chính: chặn ghi đè ID

Khi chỉ cần ID duy nhất trong một bảng, đặt ID (và namespace nếu cần) vào partition key:

~~~sql
-- Ví dụ cần DC dc1 tồn tại với đủ replica; điều chỉnh RF theo cụm lab.
CREATE KEYSPACE IF NOT EXISTS app
WITH replication = {'class': 'NetworkTopologyStrategy', 'dc1': 3}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS app.records_by_id (
  record_id uuid PRIMARY KEY,
  description text
);

CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;

INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'created by request A')
IF NOT EXISTS;

-- Thử lại cùng ID với payload khác: dự kiến [applied] = false.
INSERT INTO app.records_by_id (record_id, description)
VALUES (11111111-1111-4111-8111-111111111111, 'created by request B')
IF NOT EXISTS;
~~~

Quy tắc đạt được: **không yêu cầu INSERT có IF NOT EXISTS nào được phép tạo lần thứ hai cùng record_id khi hàng đang tồn tại**. Tuy nhiên:

1. Nó không cấm một client khác dùng **UPDATE/INSERT thường** sửa hoặc ghi đè cùng hàng. Mọi writer phải tuân theo giao thức bảo vệ.
2. Nếu xóa bản ghi, bạn có thể cho phép **tái sử dụng ID**; điều này khác với “ID chưa từng được sử dụng trong lịch sử”.
3. Nó không bảo đảm description (hoặc email trong bảng khác) là duy nhất.

Với yêu cầu **ID không được tái sử dụng vĩnh viễn**, lưu một “sổ đã cấp” không hết hạn và không xóa, hoặc dùng một dịch vụ cấp ID có chính sách giữ lịch sử phù hợp. TTL trên sổ đã cấp sẽ làm mất bảo đảm “vĩnh viễn”.

## 5. Mẫu 2 — Claim định danh nghiệp vụ theo tenant

**Bài toán:** mỗi tenant có nhiều tài khoản; **handle** (tên hiển thị dùng để đăng nhập) phải duy nhất **bên trong tenant**, trong khi account_id là UUID do ứng dụng sinh và hồ sơ được truy vấn theo account_id.

Thiết kế hai bảng theo hai hướng truy vấn:

~~~sql
-- Một partition cho từng cặp (tenant_id, handle_key).
CREATE TABLE IF NOT EXISTS app.handle_claims (
  tenant_id text,
  handle_key text,
  account_id uuid,
  request_id uuid,
  PRIMARY KEY ((tenant_id, handle_key))
);

-- Một partition cho từng tài khoản, phục vụ truy vấn theo account_id.
CREATE TABLE IF NOT EXISTS app.accounts_by_id (
  tenant_id text,
  account_id uuid,
  handle_key text,
  display_name text,
  request_id uuid,
  PRIMARY KEY ((tenant_id, account_id))
);
~~~

Ở đây **tenant_id và handle_key cùng tạo khóa phân vùng của claim**. Mục đích là phân tán các handle qua token ring, tránh mô hình toàn bộ handle của một tenant nằm trong **một partition khổng lồ**. Không dùng PRIMARY KEY ((tenant_id), handle_key) chỉ để thuận tiện nếu tenant có số lượng đăng ký lớn: thiết kế đó gom toàn bộ handle theo một tenant vào một partition và dẫn đến giới hạn kích thước/hot partition.

### Bước 1 — Chuẩn hóa và cố định khóa cần giữ

Trước mọi truy vấn, ứng dụng phải xác định cùng một **hàm canonicalize** cho mọi caller: trim, quy định chữ hoa/chữ thường, Unicode, dấu, khoảng trắng, ký tự hợp lệ, và cách xử lý đổi tên. Ví dụ quy định handle chỉ chứa ký tự ASCII a-z, 0-9 và dấu gạch dưới, chuyển về chữ thường bằng Locale.ROOT:

~~~text
Input "  Alice_01  " -> handle_key = "alice_01"
Input "ALICE_01"     -> handle_key = "alice_01"
Scope: tenant_id = "shop-7"
Khóa claim: ("shop-7", "alice_01")
~~~

Đây là **quy tắc nghiệp vụ do ứng dụng quy định**; không được thay đổi ngầm sau khi dữ liệu đã tồn tại. Nếu nhiều service dùng chuẩn hóa khác nhau, chúng có thể tạo hai khóa khác nhau cho tên mà con người nghĩ là một.

### Bước 2 — Sinh ID yêu cầu ổn định

Ứng dụng tạo **account_id** một lần cho tài khoản dự định tạo và **request_id** (idempotency key) một lần cho thao tác đăng ký. Khi client timeout hoặc retry, **tái dùng đúng cả hai ID**, không sinh mới ở mỗi lần thử. Lưu request_id ổn định trong hệ thống điều phối/đầu vào request; header idempotency có thể do client gửi và server xác thực theo tenant.

### Bước 3 — Claim bằng một LWT

~~~sql
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY SERIAL;

INSERT INTO app.handle_claims
  (tenant_id, handle_key, account_id, request_id)
VALUES
  ('shop-7', 'alice_01',
   22222222-2222-4222-8222-222222222222,
   aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa)
IF NOT EXISTS;
~~~

Kết quả mong đợi với hai request cùng nhắm đến (shop-7, alice_01):

| Kết quả | Ý nghĩa | Xử lý |
| --- | --- | --- |
| **[applied] = true** | Request đã nhận quyền sở hữu claim. | Tiếp tục tạo hồ sơ accounts_by_id, ghi log để phục hồi. |
| **[applied] = false**, account_id + request_id đang lưu **giống của request này** | Một lần thử trước có thể đã claim; đây là retry cùng thao tác. | Tiếp tục/kiểm tra bước tạo hồ sơ. |
| **[applied] = false**, chủ hoặc request ID **khác** | Handle hiện được giữ bởi người khác. | Báo xung đột (ví dụ HTTP 409), không tạo hồ sơ dùng handle này. |
| **Timeout/Unavailable hoặc lỗi chưa rõ** | Không biết claim đã được ghi hay chưa. | Ghi nhận **UNKNOWN**, retry/reconcile bằng cùng ID; không lập tức cấp handle cho người khác. |

Một LWT thất bại vì điều kiện ([applied] = false) **khác** với một LWT bị timeout. Không chuyển hai trường hợp này thành cùng lỗi “handle đã tồn tại”.

### Bước 4 — Ghi hồ sơ theo ID

Chỉ sau khi claim đã được xác nhận cho đúng request, tạo hồ sơ:

~~~sql
INSERT INTO app.accounts_by_id
  (tenant_id, account_id, handle_key, display_name, request_id)
VALUES
  ('shop-7',
   22222222-2222-4222-8222-222222222222,
   'alice_01', 'Alice', aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa)
IF NOT EXISTS;
~~~

Chủ ý dùng thêm **IF NOT EXISTS** ở partition account_id để tránh một lần retry với payload sai ghi đè tài khoản hiện hữu. Nếu [applied] = false, đọc trạng thái đã tồn tại để xác minh **account_id/handle_key/request_id** khớp yêu cầu; không tự xem mọi lần từ chối đều là thành công.

**Điểm giới hạn quan trọng:** claim và accounts_by_id thuộc **hai partition khác nhau**. Hai LWT riêng biệt **không tạo một giao dịch nguyên tử/được cách ly xuyên partition**. Nếu ứng dụng chết sau claim mà trước khi ghi profile, handle vẫn được giữ nhưng có thể chưa thấy tài khoản. Một **LOGGED BATCH** cũng không biến cặp thao tác này thành một ràng buộc UNIQUE có điều kiện và cách ly đầy đủ như giao dịch SQL nhiều hàng. Vì thế, phần tiếp theo của mẫu bắt buộc là **recovery**.

~~~mermaid
flowchart TD
    req["Đăng ký tenant + handle"] --> canon["Chuẩn hóa handle và cố định request_id"]
    canon --> cas["INSERT claim IF NOT EXISTS"]
    cas -->|applied=true| profile["INSERT account IF NOT EXISTS"]
    cas -->|applied=false| check{"Chủ và request_id có trùng?"}
    check -->|Có| profile
    check -->|Không| conflict["409: handle đang được giữ"]
    cas -->|Kết quả không rõ| unknown["Retry cùng ID hoặc điều tra"]
    profile --> done["Xác minh profile rồi công bố thành công"]
    profile -->|Kết quả không rõ| retry["Retry/đối soát profile cùng ID"]
~~~

### Điều kiện để câu “duy nhất” là đúng

Với mẫu này, cam kết là: **tại một thời điểm, với mỗi cặp (tenant_id, canonical_handle) đang được claim hợp lệ, chỉ một account_id được claim nhận quyền sở hữu qua giao thức LWT**. Nó đòi hỏi đồng thời:

1. Tất cả đường ghi/đổi tên tài khoản đều phải claim cùng khóa canonical trước khi công bố handle.
2. Chỉ quản trị có quy trình rõ mới được sửa/xóa claim; không có writer thường ghi đè account_id của claim.
3. Không có TTL làm claim tự hết hạn ngoài chính sách tái sử dụng đã thiết kế.
4. Cấu hình replication, serial consistency, routing đa DC và quyền truy cập dữ liệu đáp ứng phạm vi đảm bảo cần thiết.
5. Không công bố tài khoản có handle đó trước khi workflow claim đã xác nhận quyền sở hữu.

Đây là **duy nhất theo namespace đang tồn tại trong bảng claim**, không tự động có nghĩa là lịch sử mọi lần cấp đều duy nhất, không có bản ghi hồ sơ tạm thiếu hoặc dữ liệu đã được kiểm tra ở mọi hệ thống khác.

## 6. Mã Java: kiểm tra [applied], không biến timeout thành xung đột

Ví dụ dùng **Java Driver 4.x** (package com.datastax.oss.driver.api). CqlSession đã được tạo với contact points, local datacenter, credentials và chính sách kết nối phù hợp. Phần dưới chỉ minh họa **đăng ký claim**:

~~~java
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.UUID;

enum ClaimResult { ACQUIRED, OWNED_BY_SAME_REQUEST, CONFLICT }

static ClaimResult claimHandle(
    CqlSession session,
    PreparedStatement stmt,
    String tenantId,
    String canonicalHandle,
    UUID accountId,
    UUID requestId
) {
    BoundStatement bound = stmt
        .bind(tenantId, canonicalHandle, accountId, requestId)
        .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(ConsistencyLevel.SERIAL);

    ResultSet result = session.execute(bound);
    if (result.wasApplied()) {
        return ClaimResult.ACQUIRED;
    }

    Row existing = result.one();
    if (existing != null
        && accountId.equals(existing.getUuid("account_id"))
        && requestId.equals(existing.getUuid("request_id"))) {
        return ClaimResult.OWNED_BY_SAME_REQUEST;
    }
    return ClaimResult.CONFLICT;
}

// Khởi tạo một lần lúc service bắt đầu:
PreparedStatement claimStmt = session.prepare(
    "INSERT INTO app.handle_claims " +
    "(tenant_id, handle_key, account_id, request_id) " +
    "VALUES (?, ?, ?, ?) IF NOT EXISTS");
~~~

Ở đoạn mã trên:

- **ACQUIRED**: ghi claim thành công; bước kế tiếp là tạo hồ sơ, không đồng nghĩa workflow hai bảng đã hoàn tất.
- **OWNED_BY_SAME_REQUEST**: chỉ xác nhận claim thuộc cùng account/request; vẫn phải **kiểm tra hoặc hoàn tất** bước ghi hồ sơ.
- **CONFLICT**: claim đang do request khác sở hữu; trả trạng thái nghiệp vụ phù hợp.
- **Exception/timeout khi execute**: hàm không tự trả CONFLICT, vì có thể LWT đã commit trước khi client mất phản hồi. Tầng orchestration phải giữ cùng request_id/account_id và thực hiện retry có kiểm soát hoặc đối soát. Không áp dụng retry mù, vô hạn hoặc sinh request_id mới.

Tùy phiên bản driver, cấu hình profile, timeout và exception cụ thể sẽ khác; mã chỉ minh họa một thao tác, không phải ứng dụng chạy độc lập. Tất cả biến đầu vào được bind vào prepared statement để giữ định dạng dữ liệu và tránh nối chuỗi CQL từ input người dùng.

## 7. Retry, orphan claim và thu hồi định danh

### Hai “nửa” của một workflow nhiều partition

| Thời điểm hỏng | Trạng thái có thể còn lại | Cách giải quyết |
| --- | --- | --- |
| Trước khi claim thành công | Không có claim, hoặc trạng thái chưa rõ do timeout | Retry cùng ID; dùng kết quả CAS/đọc kiểm tra để phân biệt |
| Claim thành công, chưa ghi profile | **Orphan claim**: tên đang bị giữ nhưng không có hồ sơ | Worker phục hồi hoàn tất profile hoặc chuyển sang quy trình giải phóng có kiểm soát |
| Profile đã được ghi, phản hồi bị mất | Cả hai bảng có thể đúng nhưng client không biết | Retry cùng ID; xác minh claim và profile trùng request_id trước khi báo thành công |
| Profile có nhưng claim không thuộc chủ đúng | Bất biến nghiệp vụ bị vi phạm bởi thao tác ngoài giao thức | Cô lập, cảnh báo, điều tra; không âm thầm trả thành công |
| Người dùng muốn đổi handle | Cần claim tên mới và giải phóng tên cũ | Dùng workflow đổi tên nhiều bước, có điểm công bố và cơ chế phục hồi |

Một chiến lược phục hồi thực tế:

1. Lưu **request_id, account_id, tenant_id, handle_key** vào hệ thống xử lý yêu cầu bền vững (ví dụ một bảng trạng thái tra cứu theo request ID và/hoặc hàng đợi có thể chạy lại). Ghi trạng thái ở nhiều partition vẫn có cửa sổ lỗi, nên quy trình phải idempotent.
2. Khi timeout, **không** tự giả định ghi chưa diễn ra. Thử lại claim bằng đúng thông tin; nếu claim thuộc cùng ID, tiếp tục kiểm tra accounts_by_id.
3. Nếu thiếu profile, tạo lại bằng IF NOT EXISTS; nếu profile đã tồn tại và khớp request, xem bước ghi profile hoàn tất.
4. Chỉ trả kết quả “đăng ký thành công” sau khi đã xác minh trạng thái nghiệp vụ cần thiết.
5. Có job đối soát các request treo dựa trên **journal/queue tra cứu được bằng khóa**, thay vì quét toàn bộ bảng claim bằng ALLOW FILTERING.

**Không xóa claim ngay khi ghi profile gặp timeout.** Ghi profile có thể đã thành công; xóa claim lúc đó có thể cho người khác chiếm cùng tên trong khi tài khoản cũ vẫn sử dụng tên đó.

### Nếu nghiệp vụ cho phép giải phóng handle

Để chỉ chủ sở hữu dự kiến được xóa, dùng **conditional delete** theo account_id và request_id:

~~~sql
DELETE FROM app.handle_claims
WHERE tenant_id = 'shop-7' AND handle_key = 'alice_01'
IF account_id = 22222222-2222-4222-8222-222222222222
   AND request_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;
~~~

Tuy nhiên, điều kiện trên **chỉ bảo vệ quyền xóa claim**. Nó không đồng thời vô hiệu hóa phiên đăng nhập hoặc xóa/cập nhật hồ sơ trong partition khác. Quy trình đổi tên/hủy tài khoản phải bảo đảm điểm công bố và khôi phục được. Nếu client cũ có thể retry sau khi tên được giải phóng và người khác claim, nên dùng mô hình **generation/fencing token** hoặc ghi lại lịch sử request đã kết thúc để ngăn thao tác cũ hoạt động lại. Nếu tên **không bao giờ được tái sử dụng**, đơn giản hơn là **không xóa claim** và giữ sổ cấp phát.

TTL chỉ phù hợp với **lease có chính sách hết hạn rõ ràng**. Khi một hàng claim tự hết hạn, quyền sở hữu có thể trở thành khả dụng trong lúc hệ thống khác vẫn tin rằng tài khoản cũ còn hiệu lực. Không gắn TTL tùy tiện vào claim dùng để bảo đảm duy nhất lâu dài.

## 8. Những kiểu thiết kế không thực hiện được bảo đảm mong muốn

| Cách làm | Vì sao chưa đủ | Thay bằng |
| --- | --- | --- |
| SELECT xem tên đã có chưa, sau đó INSERT thường | Hai client cùng đọc “chưa có” rồi cùng tạo tài khoản | Claim với INSERT ... IF NOT EXISTS |
| Chỉ đặt UUID cho account_id | Tránh trùng ID theo xác suất nhưng không ngăn hai account có cùng username | Bảng claim khóa theo (scope, canonical username) |
| Đánh secondary index lên username | Index hỗ trợ tìm dữ liệu, không tự tạo UNIQUE constraint | Bảo vệ khóa nghiệp vụ bằng LWT |
| IF NOT EXISTS trên bảng account có partition key account_id | Điều kiện chỉ bảo vệ ID của tài khoản; mỗi yêu cầu có ID khác nhau | Claim theo khóa username được tranh chấp |
| Gom mọi handle của tenant trong một partition | Dễ quá kích thước partition và tạo điểm nóng trên tenant đông | Khóa phân vùng ghép (tenant_id, handle_key) |
| Dùng counter tăng số để cấp ID global gapless | Counter không tạo bộ cấp số có CAS và cam kết thứ tự/không hổng cho nhiều writer | Dịch vụ sequence chuyên dụng nếu cần strict/gapless |
| Dùng LOGGED BATCH để “giao dịch” claim và profile | BATCH không cung cấp cách ly/giao dịch điều kiện tổng quát giữa partition | Workflow idempotent và đối soát |
| Khi LWT timeout, trả “tên đã được dùng” | Timeout không cho biết lệnh được áp dụng hay chưa | Retry/reconcile bằng cùng request ID |
| Ghi claim bằng LWT, nhưng có job khác upsert thường | Job có thể ghi đè chủ sở hữu mà không tuân theo CAS | Siết quyền ghi và buộc mọi writer theo cùng giao thức |
| Dùng LOCAL_SERIAL từ hai DC mà tuyên bố uniqueness toàn hệ thống | Phạm vi Paxos cục bộ chưa chứng minh tính duy nhất toàn cụm | Chọn SERIAL hoặc một miền điều phối chung và kiểm thử đa DC |

## 9. Chi phí, replication và tính sẵn sàng

LWT cần nhiều bước trao đổi giữa các replica hơn ghi thường; độ trễ và khả năng chịu sự cố phụ thuộc phiên bản Cassandra, Paxos implementation, topology và consistency. Vì vậy không nên thêm IF NOT EXISTS lên mọi INSERT nếu chỉ cần UUID có xác suất trùng thấp.

Một số nguyên tắc vận hành:

1. **Replication**: dùng NetworkTopologyStrategy để bố trí replica theo DC/rack; một namespace có yêu cầu toàn cục phải được thiết kế với topology đủ khả năng phối hợp LWT.
2. **Serial consistency và regular consistency**: cấu hình riêng biệt và ghi nhận trên log/trace. Khi không đủ replica phục vụ consensus, **không được tự hạ consistency** để vượt qua bảo đảm đã cam kết.
3. **Tranh chấp (contention)**: hàng claim của một tên phổ biến có thể nhận rất nhiều đề nghị; theo dõi latency LWT, timeouts, retries và tỷ lệ [applied] = false.
4. **Đọc/ghi dữ liệu phụ**: profile theo account_id là mô hình thiết kế bảng theo truy vấn. Eventual consistency, compaction và repair vẫn áp dụng khi dữ liệu được sao chép; LWT không miễn yêu cầu bảo trì/repair hoặc xử lý sự cố.
5. **Khôi phục**: một yêu cầu điều kiện có thể từ chối/timeout khi một số replica hỏng; đây là đánh đổi để không cấp phát hai chủ sở hữu một tên khi hệ thống không thể xác minh trạng thái.

### Không biến ID thành bộ đếm toàn cục

Ví dụ yêu cầu “mọi đơn hàng trên toàn hệ thống phải nhận số nguyên liên tục, tăng đúng một, không có khoảng trống” **khác hẳn** với yêu cầu “mỗi ID không trùng”. Một partition duy nhất để tăng số bằng LWT sẽ là điểm tranh chấp/giới hạn thông lượng, và việc client mất phản hồi gây khó khăn cho bảo đảm không có khoảng trống. Với nhu cầu thứ tự toàn cục/gapless, hãy chọn kiến trúc cấp sequence chuyên dụng, thương lượng lại yêu cầu gapless, hoặc cấp dải số theo vùng nếu nghiệp vụ cho phép; **không** hứa rằng UUID/timeuuid, counter Cassandra hoặc LWT đơn lẻ giải quyết toàn bộ.

## 10. Kiểm thử thực tế: hai client cạnh tranh một handle

Thử nghiệm trong **lab**, có ít nhất số nút đáp ứng RF/consistency đã cấu hình. Không thử bằng cách sửa trực tiếp dữ liệu production. Tất cả request phải sử dụng **cùng cách chuẩn hóa**, namespace và cấu hình serial consistency.

### Tập ca thử

| Ca | Yêu cầu song song | Kỳ vọng có thể kiểm chứng |
| --- | --- | --- |
| T1 — Cùng handle, cùng tenant | Client A và B dùng account_id/request_id **khác nhau** cho (shop-7, alice_01) | Chỉ **một claim** được [applied] = true; bên còn lại false hoặc phải retry sau lỗi chưa rõ; cuối cùng chỉ một chủ hợp lệ |
| T2 — Cùng handle, khác tenant | A đăng ký (shop-7, alice_01), B đăng ký (shop-8, alice_01) | Cả hai có thể thành công, vì phạm vi là tenant |
| T3 — Khác kiểu chữ | A gửi “Alice_01”, B gửi “ALICE_01” | Sau chuẩn hóa phải tranh **cùng khóa**; không có hai chủ hợp lệ |
| T4 — Retry sau timeout | Request A timeout rồi gửi lại đúng account_id/request_id | Không tạo chủ thứ hai; xác minh claim thuộc A và hoàn tất profile |
| T5 — Crash sau claim | A claim thành công, tiến trình chết trước khi ghi accounts_by_id | Claim giữ tên; worker đối soát tái tạo hồ sơ hoặc thực hiện hủy có điều kiện |
| T6 — Hai DC | Hai request cạnh tranh từ các DC khác nhau | Không có hai chủ thắng nếu mô hình bảo đảm toàn cụm được cấu hình đúng; quan sát timeout và hành vi failover |
| T7 — Ghi ngoài giao thức | Job dùng upsert thường trên cùng claim | Đánh dấu đây là **vi phạm quy trình**, không coi kết quả là bảo đảm của LWT |

### Hướng dẫn thực hiện

1. Tạo schema bằng CQL; xác nhận RF, DC, các nút sẵn sàng và cqlsh dùng CONSISTENCY/ SERIAL CONSISTENCY phù hợp.
2. Đồng bộ thời điểm bắt đầu của hai client (ví dụ barrier trong chương trình Java) để làm tăng khả năng va chạm; không cần giả lập độ chính xác mili-giây của đồng hồ.
3. Mỗi client gửi **một** conditional insert với cùng tenant/handle nhưng request_id/account_id khác nhau. Ghi nhận [applied], thời điểm, latency, exception và request ID.
4. Truy vấn claim tại khóa (shop-7, alice_01) bằng mức nhất quán thích hợp và đối chiếu owner ID. Trường hợp một client timeout, retry/reconcile trước khi kết luận số chủ.
5. Lặp lại đủ số lần để quan sát tranh chấp; thử thêm T2–T5. Đối với T6, cần có lab đa DC và một thiết kế định tuyến/serial nhất quán rõ ràng.
6. Khôi phục dữ liệu test có kiểm soát; dùng khóa tên khác cho vòng thử tiếp theo hoặc xóa thử bằng conditional delete **chỉ trong lab**.

**Tiêu chí đạt:** ở từng cặp **(scope, canonical ID)**, mọi kết quả thành công sau đối soát đều quy về **tối đa một chủ sở hữu tại một thời điểm**; kết quả UNKNOWN được xử lý thành một trạng thái biết được mà không cấp nhầm; không công bố hồ sơ trái với claim.

## 11. Câu hỏi tự kiểm tra

1. Hai account_id UUID khác nhau có thể cùng đăng ký username “alice” nếu bảng account chỉ dùng IF NOT EXISTS trên account_id không? Vì sao?
2. Tại sao PRIMARY KEY ((tenant_id, handle_key)) diễn đạt phạm vi duy nhất **theo tenant**, còn PRIMARY KEY (handle_key) diễn đạt phạm vi rộng hơn?
3. Nếu [applied] = false nhưng request_id trùng lần gửi trước, quy trình phải làm gì trước khi trả thành công?
4. Vì sao mất phản hồi LWT không đủ kết luận claim chưa được ghi?
5. Tại sao không được giải phóng claim ngay khi ghi accounts_by_id bị timeout?
6. Khi nào có thể dùng UUID v4 thông thường và khi nào cần LWT để bảo vệ ID?
7. Vì sao một LOGGED BATCH hoặc secondary index không tự tạo ràng buộc duy nhất cho hai partition độc lập?

## 12. Tài liệu tham khảo

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): INSERT/UPDATE/DELETE có điều kiện, IF NOT EXISTS và ngữ nghĩa BATCH.
- [Apache Cassandra — Architecture Overview](https://cassandra.apache.org/doc/latest/cassandra/architecture/overview.html): compare-and-set trong phạm vi một partition và giới hạn giao dịch giữa các partition.
- [Apache Cassandra — Guarantees](https://cassandra.apache.org/doc/latest/cassandra/architecture/guarantees.html): mô hình LWT với Paxos và nhất quán tuyến tính.
- [Apache Cassandra — cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): CONSISTENCY và SERIAL CONSISTENCY.
- [Java Driver 4.x — Statement API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html): setConsistencyLevel và setSerialConsistencyLevel.
- [Java Driver 4.x — ResultSet API](https://docs.datastax.com/en/drivers/java/4.10/com/datastax/oss/driver/api/core/cql/ResultSet.html): wasApplied khi xử lý conditional statement.

**Ghi nhớ:** muốn bảo đảm định danh duy nhất bằng Cassandra, hãy quyết định **phạm vi duy nhất trước**, mã hóa phạm vi thành **một khóa claim mà mọi writer đều tranh chấp**, áp dụng **LWT IF NOT EXISTS**, đọc đúng **[applied]**, và giữ nguyên request ID khi retry. Với nhiều partition và ứng dụng Java, cần thêm một workflow phục hồi rõ ràng: LWT giải quyết **ai được quyền sở hữu tên**, còn ứng dụng chịu trách nhiệm hoàn tất và đối soát các bản ghi phát sinh từ quyền sở hữu ấy.
