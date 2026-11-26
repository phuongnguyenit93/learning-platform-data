# Lựa chọn consistency và serial consistency cho LWT

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao **Lightweight Transaction (LWT)** của Apache Cassandra dùng cơ chế **Paxos/compare-and-set (CAS)**, khác với `INSERT`/`UPDATE` vô điều kiện.
- Phân biệt **regular consistency** (`ONE`, `LOCAL_ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL`...) với **serial consistency** (`SERIAL`, `LOCAL_SERIAL`) khi thực thi LWT.
- Biết regular CL quyết định mức xác nhận ở giai đoạn ghi/learn và khả năng quan sát của những phép đọc thường, còn serial CL xác định phạm vi phối hợp của **giai đoạn Paxos**.
- Lựa chọn cặp consistency trong keyspace **một data center (DC)** hoặc **nhiều DC**, không nhầm `LOCAL_SERIAL` với bảo đảm tuyến tính hóa trên toàn bộ các DC.
- Viết và kiểm tra `INSERT ... IF NOT EXISTS`, `UPDATE ... IF ...`, `DELETE ... IF ...`; đọc cột `[applied]` và xử lý xung đột nghiệp vụ.
- Cấu hình `setConsistencyLevel` và `setSerialConsistencyLevel` trên Java Driver 4.x `BoundStatement`, hoặc dùng cấu hình/execution profile ở đúng tầng.
- Hiểu cách `@Version` của Spring Data Cassandra thực hiện optimistic locking bằng LWT và cách kiểm soát options cho repository/`CassandraTemplate`.
- Xử lý timeout/`UnavailableException`/CAS contention, tránh retry mù khi kết quả chưa rõ, và phân biệt idempotency với tính đúng đắn end-to-end.
- Thiết kế test, metrics, runbook và tiêu chí chọn giữa LWT, bảng theo truy vấn, writer tuần tự hoặc cơ chế quản lý thứ tự khác.

Bài thuộc chương **LWT và khóa lạc quan** của **SPRING_DATA_CASSANDRA** — truy cập Apache Cassandra qua Spring Data Cassandra, repository, `CassandraTemplate` và truy vấn CQL. Dù đang nghiên cứu LWT, vẫn cần hiểu thiết kế bảng theo truy vấn, partition key, replication factor, consistency, paging và kiểm soát hiệu năng trong hệ phân tán: **LWT không biến Cassandra thành hệ quản trị giao dịch quan hệ cho mọi bảng và mọi thao tác**.

> **Quy tắc cốt lõi:** Đối với ghi điều kiện, **regular CL** và **serial CL** là **hai quyết định khác nhau**. Ví dụ `LOCAL_QUORUM + LOCAL_SERIAL` thường là một cặp dùng cho nghiệp vụ trong một DC, nhưng không phải công thức phù hợp khi cần bảo đảm một quy tắc duy nhất trên nhiều DC có writer đồng thời.

## 1. Vì sao cần LWT thay vì chỉ nâng consistency?

Một dịch vụ đăng ký muốn bảo đảm **mỗi email chỉ có một tài khoản**. Giả sử hai request đồng thời:

~~~text
Request A: tạo account với email alice@example.test, user_id = A
Request B: tạo account với email alice@example.test, user_id = B
~~~

Nếu hai request đều làm:

~~~text
SELECT ... WHERE email = 'alice@example.test'  -> không thấy row
INSERT ...                                       -> ghi row
~~~

thì giữa SELECT và INSERT có một **race condition**. Dù SELECT/INSERT được gửi ở `LOCAL_QUORUM`, hai request vẫn có thể cùng đọc trạng thái “chưa tồn tại”, sau đó ghi cạnh tranh. Tăng regular CL không biến **check-then-write** thành một thao tác atomic.

Giải pháp là **conditional mutation**:

~~~sql
CREATE TABLE accounts_by_email (
    email text PRIMARY KEY,
    user_id uuid,
    status text,
    version bigint
);

INSERT INTO accounts_by_email (email, user_id, status, version)
VALUES ('alice@example.test',
        11111111-1111-4111-8111-111111111111,
        'ACTIVE', 0)
IF NOT EXISTS;
~~~

Khi các writer cạnh tranh đúng phạm vi khóa, LWT cho phép phân xử điều kiện; phía client phải đọc kết quả `[applied]` để biết điều kiện có được áp dụng hay không.

### 1.1. Hai phép thử khác nhau

| Phép thử | Điều muốn bảo đảm | Cơ chế phù hợp |
| --- | --- | --- |
| “Có đủ replica phản hồi ghi chưa?” | Mức xác nhận dữ liệu trên replica | Regular consistency level |
| “Hai writer đồng thời có thể cùng thắng điều kiện không?” | Thứ tự/atomicity của thao tác điều kiện | Paxos/LWT với serial consistency |
| “Hai bảng account và profile có đồng bộ cùng giao dịch không?” | Bất biến nghiệp vụ qua nhiều bảng | Thiết kế workflow/outbox/reconciliation, không mặc định do LWT |
| “Đọc ở DC khác ngay sau ghi có thấy kết quả không?” | Phạm vi quan sát hậu commit/replication | Xem regular CL, topology, DC và read protocol |
| “Một request timeout có chắc chắn chưa áp dụng?” | Kết quả ghi không rõ | Idempotency key, CAS/state verification |

Nói ngắn gọn: **regular CL không thay thế CAS**, và **serial CL không thay thế các chính sách replication/read visibility**.

### 1.2. Mô hình luồng

~~~mermaid
flowchart TD
    A["Client: INSERT ... IF NOT EXISTS"] --> B["Coordinator Cassandra"]
    B --> C["Paxos/serial phase"]
    C --> D{"Điều kiện còn đúng?"}
    D -->|Không| E["[applied] = false / row hiện có"]
    D -->|Có| F["Commit/learn với regular CL"]
    F --> G["[applied] = true nếu hoàn tất"]
    G --> H["Đọc thường tùy read CL"]
    E --> I["Ứng dụng phân biệt conflict/retry"]
~~~

Sơ đồ mang tính khái niệm: các bước Paxos thực tế và cách triển khai giao thức có thể khác theo phiên bản Cassandra. Nó minh họa **hai nhóm mức consistency**, không đưa ra số round-trip cố định.

## 2. Phân biệt regular consistency và serial consistency

Cassandra cho phép ứng dụng chọn consistency trên từng request. Với LWT, có **hai trường cấu hình**:

| Thuộc tính | Nhóm giá trị | Áp dụng vào | Câu hỏi nó trả lời |
| --- | --- | --- | --- |
| **Regular consistency** | `ONE`, `LOCAL_ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL`... | Giai đoạn áp dụng/learn của conditional write; các phép đọc/ghi thường | Cần bao nhiêu replica phản hồi và ở đâu? |
| **Serial consistency** | **`SERIAL`** hoặc **`LOCAL_SERIAL`** | Giai đoạn Paxos của conditional mutation | Phạm vi phối hợp để bảo vệ điều kiện ghi là gì? |

Đối với các câu `INSERT`, `UPDATE`, `DELETE` có `IF`, driver hỗ trợ cả hai thuộc tính. Đối với lệnh thường không có điều kiện, **không** nên nghĩ rằng đặt serial consistency biến nó thành CAS; giai đoạn Paxos không tự xuất hiện từ một flag.

### 2.1. Regular CL theo replication factor

Giả sử keyspace chỉ có một DC, RF = 3 và đủ ba replica khỏe:

| Regular CL | Ngưỡng phản hồi điển hình | Nhận xét |
| --- | --- | --- |
| `ONE` | 1 replica | Thấp hơn về ngưỡng phản hồi |
| `LOCAL_ONE` | 1 replica trong DC cục bộ | Hợp workload cho phép đọc/ghi theo chính sách local |
| `QUORUM` | 2 trong tổng 3 replica | Quorum toàn replication trong ví dụ một DC |
| `LOCAL_QUORUM` | 2 replica trong DC cục bộ | Quorum tại local DC |
| `ALL` | Cả 3 replica | Nhạy với một replica không sẵn sàng |

Trong một DC với RF=3, `QUORUM` và `LOCAL_QUORUM` có thể cùng ngưỡng là hai replica. Trong nhiều DC, **phạm vi đếm** sẽ khác nhau; không suy từ tên gọi rằng chúng luôn tương đương.

### 2.2. Serial CL có hai lựa chọn chính

| Serial CL | Phạm vi ý nghĩa | Khi cân nhắc |
| --- | --- | --- |
| `SERIAL` | Paxos/linearizability theo phạm vi replication toàn cụm được hỗ trợ | Có writer từ nhiều DC và cần cùng một bất biến toàn phạm vi |
| `LOCAL_SERIAL` | Paxos/linearizability trong DC cục bộ | Các conditional writers được giới hạn/điều phối trong một DC |

**Không có `SERIAL_ONE` hoặc `SERIAL_ALL`** như các lựa chọn serial CL phổ biến. `SERIAL` và `LOCAL_SERIAL` là những giá trị chuyên biệt; chúng không phải phiên bản “mạnh hơn một chút” của `ONE`/`LOCAL_ONE`.

### 2.3. Regular CL còn ảnh hưởng đến đọc sau LWT

Theo mô hình cơ bản của LWT, giai đoạn Paxos giúp các writer điều kiện có thứ tự, còn giai đoạn learn/commit theo regular CL quyết định mức áp dụng/khả năng quan sát ngay sau khi trả thành công.

Vì vậy:

- Một mutation điều kiện thành công ở regular `LOCAL_QUORUM` trong DC có RF=3 cho phép lập luận về các phép đọc quorum **cùng phạm vi** với những giả định nhất quán phù hợp.
- Một mutation thành công ở regular `LOCAL_ONE` không tự tạo giao nhau quorum với phép đọc `LOCAL_ONE` tiếp theo trên replica khác.
- `LOCAL_SERIAL` không đồng nghĩa “mọi client ở mọi DC đều nhìn thấy kết quả vừa ghi ngay lập tức”.
- Đọc với serial consistency được thực hiện theo semantics đặc biệt của serial read khi thực sự cần kiểm tra tiến trình LWT, khác với đọc thường ở `LOCAL_ONE`/`LOCAL_QUORUM`.

**Không tự đưa ra lời hứa “read-after-write toàn cầu” chỉ vì có chữ SERIAL** trong một lựa chọn. Cần định nghĩa phạm vi writer/readers, các DC, CL và consistency contract.

## 3. Paxos ở mức khái niệm: điều kiện trước, áp dụng sau

LWT thường được giải thích thông qua giao thức Paxos để nhiều coordinator/replica có thể thống nhất kết quả của thao tác điều kiện, kể cả khi hai request xảy ra đồng thời.

Một hình dung đơn giản:

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant C as Coordinator
    participant R as Paxos replicas

    A->>C: INSERT email=A IF NOT EXISTS
    B->>C: INSERT email=B IF NOT EXISTS
    C->>R: Serial/Paxos phase
    R-->>C: Quorum/ordering
    C->>R: Commit/learn (regular CL)
    C-->>A: [applied]=true hoặc conflict
    C-->>B: [applied]=false hoặc conflict
~~~

Đừng hiểu sơ đồ rằng chỉ có **một** coordinator hoặc mọi phiên bản Cassandra chạy đúng từng thông điệp theo thứ tự vẽ; đây là mô hình để nhận ra hai pha chính sách consistency.

### 3.1. LWT bảo vệ điều gì?

- Một điều kiện `IF NOT EXISTS` trên row của một primary key phù hợp.
- Một phép `UPDATE ... IF version = ?` hoặc `IF status = ?` trong phạm vi khóa mà CQL/LWT hỗ trợ.
- Một phép delete có điều kiện trong phạm vi CQL cho phép.
- Những writer cạnh tranh cùng giao thức/phạm vi được tuần tự hóa theo semantics LWT tương ứng.

LWT **không tự tạo**:

- Transaction nhiều bảng tùy ý như SQL `BEGIN ... COMMIT`.
- Unique constraint ở tất cả những cách biểu diễn cùng một email nếu ứng dụng không đặt email vào cùng khóa được kiểm soát.
- Distributed lock cho hệ thống ngoài Cassandra.
- Exactly-once giữa Cassandra, message broker và dịch vụ gửi email.
- Bảo đảm thứ tự cho các mutation **không dùng cùng quy tắc CAS**.

### 3.2. Tại sao LWT đắt hơn write thường?

Write thường theo Cassandra không cần các vòng phối hợp conditional/Paxos giống LWT. LWT phải kiểm tra điều kiện và đồng thuận thứ tự, nên thường:

- Có latency cao hơn và nhiều thông điệp giữa coordinator/replica.
- Nhạy với node chậm, mất mạng và bất ổn quorum.
- Tạo contention khi nhiều writer cùng cạnh tranh một partition/key.
- Có thể làm p99 xấu hơn rõ rệt khi hotspot.
- Đòi hỏi xử lý `[applied]=false` như một kết quả nghiệp vụ chứ không đơn giản là lỗi.

Đừng đưa toàn bộ thao tác ghi ở QPS cao qua LWT chỉ vì “an toàn hơn”; hãy xác định bất biến nào **thực sự cần CAS**.

## 4. Mẫu triển khai LWT: account theo email

### 4.1. Schema theo khóa duy nhất cần bảo vệ

~~~sql
CREATE KEYSPACE IF NOT EXISTS account_service
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS account_service.accounts_by_email (
    email text PRIMARY KEY,
    user_id uuid,
    status text,
    version bigint
);
~~~

`dc1` chỉ là tên minh họa; không dùng nguyên vào production nếu tên DC thực tế khác. Schema có partition key `email` để mọi request tạo tài khoản cùng email gặp **cùng phạm vi điều kiện**.

### 4.2. Câu lệnh create-only

~~~sql
INSERT INTO account_service.accounts_by_email (
    email, user_id, status, version
)
VALUES (?, ?, 'ACTIVE', 0)
IF NOT EXISTS;
~~~

Nếu không có `IF NOT EXISTS`, hai lần `INSERT` cùng email là upsert có thể ghi đè giá trị `user_id` theo write timestamp. Nếu có LWT, chỉ một điều kiện tạo row tương ứng được áp dụng khi các request cạnh tranh hợp lệ.

### 4.3. Đọc cột [applied]

Kết quả conditional CQL chứa cột `[applied]`. Ví dụ cqlsh:

~~~text
[applied]
-----------
 True

-- Hoặc khi row đã tồn tại:
[applied] | email | user_id | status | version
----------+-------+---------+--------+--------
 False     | ...   | ...     | ...    | ...
~~~

Hình dạng các cột bổ sung khi `[applied]=false` có thể khác theo lệnh/phiên bản. Không viết code phụ thuộc vào “luôn có đúng tất cả cột hiện tại” nếu chưa kiểm tra contract. Khi cần, đọc row riêng theo primary key để xác minh trạng thái.

### 4.4. Đưa requestId vào workflow

Một request đã thực sự tạo account nhưng response mất có thể bị retry, lần sau thấy `[applied]=false`. Nếu chỉ trả HTTP 409 mà không kiểm tra `user_id`/request ID, người dùng có thể tưởng đăng ký thất bại dù account đã được tạo.

Một API create-only nên định nghĩa:

- Cùng request ID và payload được gửi lại → nhận kết quả idempotent tương ứng nếu row đã được tạo bởi chính request.
- Cùng email nhưng khác user ID/payload → xung đột nghiệp vụ.
- Timeout không rõ kết quả → đọc lại theo email và so sánh request ID/payload đáng tin cậy, hoặc trả trạng thái đang xác minh.
- Không phát email chào mừng hai lần chỉ vì client retry.
- Kiểm tra email đã chuẩn hóa và quy tắc uniqueness (case folding, normalization) **trước** khi dùng làm partition key.

Việc chọn regular/serial CL đúng là điều kiện hạ tầng cần thiết, nhưng chưa đủ cho exactly-once ở API.

## 5. LWT cho optimistic locking bằng version

Giả sử row trạng thái đơn hàng:

~~~sql
CREATE TABLE account_service.orders_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    version bigint,
    updated_at timestamp
);
~~~

Trạng thái kỳ vọng:

~~~text
CREATED (version=1)
  |
  +-- PAID (version=2)
       |
       +-- SHIPPED (version=3)
~~~

Một CAS cập nhật version:

~~~sql
UPDATE account_service.orders_by_id
SET status = 'PAID',
    version = 2,
    updated_at = ?
WHERE order_id = ?
IF version = 1 AND status = 'CREATED';
~~~

Trong ví dụ, hai writer cùng thấy version 1: chỉ một request có thể cập nhật theo điều kiện version/status trong phạm vi LWT tương ứng. Request thua cần đọc trạng thái mới và ra quyết định, không “cứ tăng version rồi ghi vô điều kiện”.

### 5.1. Vì sao version không có tác dụng nếu thiếu IF?

~~~sql
-- Không được xem như optimistic locking:
UPDATE account_service.orders_by_id
SET status = 'PAID', version = 2
WHERE order_id = ?;
~~~

CQL `UPDATE` thông thường là upsert. Nó không tự so sánh version đang tồn tại với version bạn viết; conflict resolution theo write timestamp của Cassandra, không theo số version lớn hơn.

### 5.2. Vì sao read-then-write ở LOCAL_QUORUM không đủ?

Hai request có thể đọc cùng version=1 ở regular `LOCAL_QUORUM`, rồi cùng ghi version=2. Quorum của phép đọc/ghi chỉ bảo đảm điều kiện phản hồi replica, không buộc mutation sau kiểm tra điều kiện cũ một cách atomic.

Chỉ khi phép ghi có điều kiện `IF version = 1` được Paxos phân xử theo serial CL đúng phạm vi mới có quy tắc CAS tương ứng.

### 5.3. Không tự cho version+1 là chính xác nếu event đảo thứ tự

Nếu event từ shipping chứa version 3 nhưng payment event cũ chứa version 2 đến sau, không dùng write timestamp hiện tại rồi mặc định payment có thể ghi vì request đến sau. Nếu nghiệp vụ có source-of-truth tạo sequence, cần xác minh version hợp lệ và điều kiện chuyển trạng thái. LWT có thể thực thi điều kiện, nhưng hệ thống vẫn phải định nghĩa **luật nghiệp vụ**.

## 6. Chọn cặp CL trong một data center

Giả định:

~~~text
Keyspace RF = 3 trong dc1
Driver local-datacenter = dc1
Writers và readers chính đều ở dc1
Bất biến: một email chỉ tạo một account
~~~

Một lựa chọn phổ biến để cân bằng giữa bảo đảm và độ sẵn sàng là:

~~~text
regular consistency = LOCAL_QUORUM
serial consistency  = LOCAL_SERIAL
~~~

### 6.1. Cặp LOCAL_QUORUM + LOCAL_SERIAL có ý nghĩa gì?

**LOCAL_SERIAL:** Các conditional writes dùng Paxos trong phạm vi local DC, bảo vệ điều kiện theo phạm vi được phối hợp.

**LOCAL_QUORUM:** Giai đoạn áp dụng/learn cần đủ replica trong local DC phản hồi. Với RF=3, quorum là hai replica theo điều kiện chuẩn.

Điều này phù hợp khi ứng dụng chọn **một DC có thẩm quyền cho các writer cạnh tranh**, hoặc phạm vi nghiệp vụ thực sự chỉ là DC cục bộ. Nếu có writer khác ở DC khác cùng ghi vào **cùng một khóa** mà yêu cầu unique toàn cầu, cần đánh giá lại: không thể chỉ nhìn thấy tên `LOCAL_SERIAL` rồi kết luận hai DC cùng tuyến tính hóa một luật toàn cục.

### 6.2. Điều kiện hạ tầng

- RF của keyspace phù hợp số node/rack có sẵn.
- Driver `local-datacenter` được đặt đúng.
- Writer không vô tình fail over sang DC khác với serial local khi cùng bất biến vẫn cần duy trì.
- Có ít nhất quorum replica còn khỏe trong DC phục vụ.
- Đọc sau ghi theo regular CL được chọn có giả định đúng về replica và không có writer ngoài phạm vi làm đổi state.
- Timeout và CAS contention được xử lý bằng logic nghiệp vụ, không retry vô hạn.

### 6.3. Không có cặp “mạnh nhất” cho mọi nhu cầu

| Cặp ví dụ | Có thể phù hợp | Rủi ro/cần xác minh |
| --- | --- | --- |
| `LOCAL_QUORUM + LOCAL_SERIAL` | Một DC có các writer chính; bảo đảm trong DC | Không suy là uniqueness toàn cầu khi multi-DC cùng ghi |
| `QUORUM + SERIAL` | Phối hợp across DC khi nghiệp vụ cần Paxos rộng | Latency/mạng/DC failures, cách regular quorum giao với reads |
| `LOCAL_QUORUM + SERIAL` | Paxos phạm vi rộng nhưng ghi thường/learn theo local DC | Remote DC visibility, SLA đọc nhiều vùng và failure mode |
| `LOCAL_ONE + LOCAL_SERIAL` | Chỉ trong tình huống có contract đọc/ghi chấp nhận weaker regular CL | Đọc thường ngay sau ghi có thể nhìn trạng thái cũ |
| `ALL + SERIAL` | Yêu cầu regular acknowledgement rất mạnh và capacity cho phép | Một replica chậm/down làm giảm availability, chi phí cao |

Bảng này là các **mẫu cân nhắc**, không phải công thức cấu hình production. Những cặp có thể hợp lệ về mặt API vẫn có thể **không đáp ứng** guarantee nghiệp vụ nếu topology, reader placement và writer routing không khớp.

## 7. SERIAL hay LOCAL_SERIAL khi có nhiều data center?

Giả sử keyspace dùng NetworkTopologyStrategy:

~~~sql
CREATE KEYSPACE IF NOT EXISTS global_accounts
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Hai ứng dụng có thể tạo cùng email:

~~~text
API A tại dc1: INSERT email=x IF NOT EXISTS
API B tại dc2: INSERT email=x IF NOT EXISTS
~~~

### 7.1. LOCAL_SERIAL: phạm vi local

`LOCAL_SERIAL` giới hạn pha serial/Paxos vào các replica của DC cục bộ. Nó thường giúp giảm phụ thuộc vào độ trễ WAN và giảm phạm vi cần sẵn sàng cho **bất biến cục bộ**.

Nhưng nếu writer từ dc1 và dc2 cùng tranh một khóa, **không dùng LOCAL_SERIAL ở cả hai nơi rồi hứa global uniqueness**. Hai vùng có thể xử lý điều kiện theo phạm vi local khác nhau, trong khi replication giữa DC có độ trễ. Hợp đồng không bảo đảm tuyến tính hóa toàn cụm cho tất cả request như `SERIAL`.

Có thể sử dụng LOCAL_SERIAL hợp lý nếu:

- Chỉ một DC nhận các conditional writers cho một tập khóa.
- Traffic được định tuyến tới DC home của tenant/key, có cơ chế tránh split-brain/failover trái phép.
- Các DC khác phục vụ bản sao read-only hoặc chấp nhận dữ liệu trễ.
- Việc failover thay đổi quyền viết được điều phối cẩn thận.

### 7.2. SERIAL: phạm vi rộng hơn

`SERIAL` hướng tới pha Paxos có phạm vi toàn replication, phù hợp hơn khi **các DC đều có thể nhận writer** và yêu cầu thống nhất một điều kiện trên toàn cục.

Đánh đổi:

- Quá trình phối hợp có thể liên quan các node cách xa nhau và WAN latency.
- Khi sự cố DC/network, availability/timeout thay đổi theo topology/quorum.
- P99 có thể xấu hơn nhiều so với local-only.
- Commit/learn theo regular CL vẫn cần được chọn để đạt hợp đồng quan sát của readers ở các vùng.

Không mặc định mọi kiến trúc multi-DC đều cần `SERIAL`: nếu đã định tuyến writer về một home DC, `LOCAL_SERIAL` có thể phù hợp, nhưng phải có **bảo đảm routing và failover** ở tầng kiến trúc.

### 7.3. Phân biệt phạm vi Paxos với read-after-write

Chọn `SERIAL` có thể cung cấp phạm vi phối hợp CAS lớn hơn. Tuy nhiên, nếu conditional write được learn theo regular `LOCAL_QUORUM` ở dc1, một phép đọc thường `LOCAL_ONE` tại dc2 ngay sau đó **không được hứa** thấy giá trị mới tức thì.

Khi cần read-after-write nhất quán qua nhiều vùng:

1. Định nghĩa rõ nơi client đọc sau khi ghi.
2. Đánh giá regular write CL và read CL có giao nhau phù hợp không.
3. Xem xét serial read khi thực sự cần semantics của Paxos state.
4. Đánh giá traffic đa vùng, độ trễ WAN và chế độ lỗi.
5. Đưa kết quả test failover/partition thực tế vào SLA thay vì dựa vào tên consistency.

Một số lựa chọn mạnh có thể đánh đổi availability; hệ thống phải chủ động chọn thay vì vừa đòi luôn sẵn sàng vừa đòi linearizable toàn cầu không điều kiện.

### 7.4. Ma trận quyết định

| Bất biến/traffic | Serial CL xem xét | Regular CL xem xét | Ghi chú |
| --- | --- | --- | --- |
| Writer chỉ ở dc1, người dùng đọc chủ yếu dc1 | `LOCAL_SERIAL` | `LOCAL_QUORUM` | Cần routing cố định và xử lý failover |
| Writer cạnh tranh ở dc1/dc2, uniqueness toàn cầu | `SERIAL` | Theo read-visibility contract | Đo WAN/failure, không dùng hai LOCAL_SERIAL độc lập |
| Dashboard có thể dữ liệu trễ | LWT cho mutation liên quan, hoặc không cần LWT | Đọc `LOCAL_ONE` có thể chấp nhận | Không dùng dashboard latency để quyết định CAS |
| Chuyển trạng thái đơn cần version ở home DC | `LOCAL_SERIAL` khi chỉ một DC authoritative | `LOCAL_QUORUM` | Xem xét writer coordination/split-brain |
| Ghi hầu hết bất biến quan trọng toàn cầu và không có home region | `SERIAL` hoặc kiến trúc coordinator khác | Cân đối read CL theo SLA | Phải benchmark và có chính sách outage |

## 8. cqlsh: cấu hình consistency đúng chỗ

Khi thử trên môi trường được phép, cqlsh hỗ trợ các lệnh **shell**, không phải CQL gửi qua prepared statement:

~~~text
CONSISTENCY LOCAL_QUORUM;
SERIAL CONSISTENCY LOCAL_SERIAL;
~~~

Sau đó thực thi:

~~~sql
INSERT INTO account_service.accounts_by_email (
    email, user_id, status, version
)
VALUES ('alice@example.test',
        11111111-1111-4111-8111-111111111111,
        'ACTIVE', 0)
IF NOT EXISTS;
~~~

Cú pháp và hiển thị của lệnh cqlsh cần đối chiếu version. Không nhầm:

- `CONSISTENCY LOCAL_QUORUM`: regular CL cho câu lệnh.
- `SERIAL CONSISTENCY LOCAL_SERIAL`: serial CL cho thao tác điều kiện.
- `IF NOT EXISTS`: thực sự **tạo conditional mutation**.
- `[applied]`: cho biết mutation theo điều kiện có thành công hay không.

Nếu chỉ thay `SERIAL CONSISTENCY` nhưng bỏ `IF NOT EXISTS`, câu INSERT trở thành write thường, không có CAS. Nếu chỉ thêm `IF` mà không xác định scope serial phù hợp, driver/server defaults có thể không đáp ứng topology/latency bạn mong muốn.

## 9. Java Driver 4.x: set hai mức trên BoundStatement

**Lưu ý về import:** Trong Java Driver 4.x, các giá trị sẵn có như `LOCAL_QUORUM`, `SERIAL` nằm trong **`DefaultConsistencyLevel`**. Interface `ConsistencyLevel` là kiểu nhận tham số; không dùng nhầm cú pháp `ConsistencyLevel.LOCAL_QUORUM` như một enum nếu dependency của bạn dùng Driver 4.x hiện hành.

### 9.1. Prepare một lần, bind mỗi request

~~~java
import java.time.Duration;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class AccountRegistrationDao {

    private final CqlSession session;
    private final PreparedStatement createByEmail;

    public AccountRegistrationDao(CqlSession session) {
        this.session = session;
        this.createByEmail = session.prepare(
            "INSERT INTO account_service.accounts_by_email " +
            "(email, user_id, status, version) " +
            "VALUES (?, ?, 'ACTIVE', 0) IF NOT EXISTS"
        );
    }

    public boolean register(String email, UUID userId) {
        BoundStatement statement = createByEmail.bind(email, userId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setSerialConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_SERIAL)
            .setTimeout(Duration.ofSeconds(5))
            .setIdempotent(false);

        ResultSet result = session.execute(statement);
        return result.wasApplied();
    }
}
~~~

Ở đây:

1. `PreparedStatement` được khởi tạo và dùng lại.
2. `bind` tạo `BoundStatement` riêng cho từng request.
3. Regular CL đặt `LOCAL_QUORUM`.
4. Serial CL đặt `LOCAL_SERIAL`.
5. Timeout minh họa 5 giây; phải đo p99 và chọn theo SLA thật.
6. `setIdempotent(false)` chọn bảo thủ vì timeout có thể dẫn tới trạng thái nghiệp vụ không rõ; ứng dụng quyết định retry theo request ID.
7. `ResultSet.wasApplied()` đọc kết quả conditional statement.

Không coi `false` là “không có tài khoản” — đó là **điều kiện không được áp dụng**. Muốn biết row hiện tại thuộc cùng request hay một người khác, cần đọc lại và đối chiếu theo contract.

### 9.2. BoundStatement immutable

Driver 4.x dùng API statement theo hướng immutable: các phương thức `setXxx` trả về **statement mới**. Đừng bỏ giá trị trả về:

~~~java
BoundStatement original = createByEmail.bind(email, userId);

// Không nên: gọi setter rồi bỏ kết quả.
original.setSerialConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_SERIAL);

// Đúng: dùng giá trị trả về.
BoundStatement configured = original
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL);
~~~

Không chia sẻ một `BoundStatementBuilder` có thể thay đổi giữa các thread. Một prepared query có thể được dùng lại cho nhiều statement với options khác nhau.

### 9.3. UPDATE có điều kiện và đọc kết quả

~~~java
PreparedStatement payIfCreated = session.prepare(
    "UPDATE account_service.orders_by_id " +
    "SET status = 'PAID', version = 2, updated_at = ? " +
    "WHERE order_id = ? " +
    "IF version = 1 AND status = 'CREATED'"
);

BoundStatement bound = payIfCreated.bind(updatedAt, orderId)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL)
    .setTimeout(Duration.ofSeconds(5))
    .setIdempotent(false);

boolean applied = session.execute(bound).wasApplied();

if (!applied) {
    // Xem row hiện tại; phân biệt cạnh tranh hợp lệ,
    // request đã xử lý hoặc trạng thái không cho phép.
}
~~~

Giá trị `updatedAt` trong ví dụ phải là `Instant`/type codec phù hợp CQL `timestamp`. Không nhầm field `updated_at` với timestamp nội bộ dùng LWW. Conditional mutation và write timestamp do client tự cung cấp có những hạn chế riêng; không cố “ép thắng” bằng `USING TIMESTAMP` khi dùng LWT.

### 9.4. Vì sao không làm hai lần đọc thường rồi dùng so sánh client-side?

~~~java
// Sai khi có nhiều writer:
Order current = readById(orderId);
if ("CREATED".equals(current.status())) {
    unconditionalUpdate(orderId, "PAID");
}
~~~

Ngay cả khi cả hai request chạy ở `LOCAL_QUORUM`, vẫn có khoảng thời gian để writer khác thay đổi state. Conditional CQL đưa việc kiểm tra và áp dụng **vào cùng giao thức LWT**.

## 10. Execution profile và cấu hình mặc định của Java Driver

Khi `BoundStatement` không đặt trực tiếp consistency, serial consistency hoặc timeout, Java Driver lấy giá trị từ execution profile. Có thể đặt chính sách khác nhau cho LWT ở DC cục bộ và LWT có phạm vi toàn cụm thay vì sao chép options ở nhiều adapter.

### 10.1. Ví dụ HOCON

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    serial-consistency = LOCAL_SERIAL
    timeout = 5 seconds
    default-idempotence = false
  }

  profiles {
    global-cas {
      basic.request.consistency = QUORUM
      basic.request.serial-consistency = SERIAL
      basic.request.timeout = 8 seconds
    }
  }
}
~~~

Các giá trị trên **chỉ minh họa**, không phải khuyến nghị SLA cố định. `default-idempotence=false` là chính sách bảo thủ: không cho driver mặc định coi mọi mutation là an toàn khi có thêm retry/speculative attempts.

~~~java
BoundStatement statement = createByEmail.bind(email, userId)
    .setExecutionProfileName("global-cas")
    .setIdempotent(false);

ResultSet result = session.execute(statement);
~~~

Một statement có thể ghi đè profile bằng `setSerialConsistencyLevel`, `setConsistencyLevel`, `setTimeout`. Khi review, phải kiểm tra **giá trị có hiệu lực**, không chỉ tên profile. Đặc biệt, nếu profile tên `global-cas` nhưng một đoạn code sau đó đặt `LOCAL_SERIAL`, tính chất toàn cục không còn như thiết kế.

### 10.2. Spring Boot và driver configuration

Spring Boot có các property Cassandra thông thường:

~~~yaml
spring:
  cassandra:
    keyspace-name: account_service
    local-datacenter: dc1
    request:
      consistency: LOCAL_QUORUM
      timeout: 5s
~~~

Những property này không tự đặt serial CL theo cách mọi phiên bản Boot đều công bố. Khi cần serial CL cụ thể, cấu hình trực tiếp bằng driver HOCON, execution profile, hoặc options mà Spring Data Cassandra phiên bản ứng dụng hỗ trợ.

Không tạo session thứ hai chỉ để đổi serial CL: nên dùng `CqlSession` do Spring quản lý, tránh thêm connection pool/metadata footprint và khó kiểm soát vòng đời.

### 10.3. Kiểm tra default có hiệu lực

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverConfig;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

DriverConfig cfg = session.getContext().getConfig();
DriverExecutionProfile defaults = cfg.getDefaultProfile();

String regular = defaults.getString(
    DefaultDriverOption.REQUEST_CONSISTENCY);
String serial = defaults.getString(
    DefaultDriverOption.REQUEST_SERIAL_CONSISTENCY);
~~~

Đây là cách đọc **default profile**, không phải những tùy chọn tường minh của một request đang chạy. Nếu dùng named profile, xem giá trị profile đó riêng; nếu statement override, giá trị statement ưu tiên hơn. Không log secret/certificates khi ghi nhận cấu hình runtime.

## 11. Spring Data Cassandra: @Version và optimistic locking

Spring Data Cassandra hỗ trợ `@Version` để đảm bảo optimistic locking bằng **LWT**. Khác với JPA, đây không phải transaction được quản lý qua persistence context và row lock; framework tạo conditional CQL phù hợp với mapping/version.

### 11.1. Entity ví dụ

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("status")
    private String status;

    @Column("updated_at")
    private Instant updatedAt;

    @Version
    @Column("version")
    private Long version;

    public OrderById() {
    }

    // Constructor, getters, setters...
}
~~~

CQL:

~~~sql
CREATE TABLE account_service.orders_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    updated_at timestamp,
    version bigint
);
~~~

Với `@Version` được cấu hình đúng theo API:

- Insert entity mới dùng cơ chế kiểm tra tồn tại, thông thường là `INSERT ... IF NOT EXISTS`.
- Update có điều kiện so sánh version cũ với version trên row; version được tăng theo quy tắc framework.
- Delete có thể dùng version trong điều kiện theo hợp đồng method/version.
- Khi điều kiện không thỏa, Spring Data phát tín hiệu optimistic locking conflict (thường qua `OptimisticLockingFailureException` hoặc kiểu tương ứng).
- Version ban đầu và cách xác định entity mới nên kiểm tra theo phiên bản dependency đang dùng.

### 11.2. Vì sao repository.save có thể xung đột?

~~~java
OrderById order = repository.findById(orderId).orElseThrow();
order.setStatus("PAID");
order.setUpdatedAt(Instant.now());

repository.save(order);
~~~

Nếu entity có `@Version`, đường save có thể dùng LWT để ngăn hai update dựa cùng một version cũ đều thành công. Nếu entity không có `@Version` và operation không có điều kiện, chỉ việc gọi `findById` trước `save` **không tạo** CAS.

Một tình huống tranh chấp:

~~~text
A đọc version=4 -> muốn PAID.
B đọc version=4 -> muốn CANCELLED.

A CAS IF version=4 -> thắng, lưu version mới.
B CAS IF version=4 -> thua; phải đọc lại và quyết định.
~~~

Service phải phân biệt conflict hợp lệ với lỗi mạng. Không phát email, ghi charge hay cập nhật bên ngoài như thể request B đã thắng.

### 11.3. QueryOptions regular/serial CL

Spring Data Cassandra có `QueryOptions` và các builders hỗ trợ options theo request (khả dụng theo version):

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.cql.QueryOptions;

QueryOptions opts = QueryOptions.builder()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .serialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .timeout(Duration.ofSeconds(5))
    .build();
~~~

`QueryOptions` **không tự tạo `IF`**. Chúng chỉ áp dụng cho API có nhận options. Khi dùng entity insert/update, có thêm các options như `InsertOptions`/`UpdateOptions` và các chế độ conditional phù hợp. Ví dụ `withIfExists()` chỉ kiểm tra **row tồn tại**, không thay điều kiện version nếu nghiệp vụ cần CAS theo revision.

Khi dùng `@Version`, hãy đảm bảo options và defaults của Spring Data không bị đường viết CQL trực tiếp khác bypass. Nếu cần lựa chọn serial CL theo từng mutation và đọc `[applied]`, adapter Java Driver trực tiếp thường rõ ràng hơn; nhưng vẫn dùng cùng `CqlSession` của Spring.

### 11.4. Tách mapping và business logic

Một số thao tác cần condition cụ thể `IF version = ? AND status = 'CREATED'`, khác với optimistic lock thuần bằng version. `@Version` là công cụ tốt cho CAS theo phiên bản, còn **luật chuyển trạng thái** phải được thiết kế riêng. Không mặc định version đúng đồng nghĩa mọi transition hợp lệ.

## 12. Serial read và regular read

Một truy vấn đọc thông thường có regular CL như `LOCAL_ONE` hoặc `LOCAL_QUORUM`. Cassandra cũng hỗ trợ serial read theo semantics của Paxos khi cần xem trạng thái liên quan LWT đang tiến hành.

Khác biệt cần nhớ:

- **Conditional write:** `setSerialConsistencyLevel(DefaultConsistencyLevel.SERIAL)` kiểm soát Paxos; `setConsistencyLevel(LOCAL_QUORUM)` kiểm soát regular phase.
- **Serial read:** consistency của chính lệnh SELECT là `SERIAL` hoặc `LOCAL_SERIAL`, không phải chỉ gắn serial option lên một SELECT thường.
- Serial read có thể phải xử lý trạng thái chưa được learn/commit của một LWT; có overhead và giới hạn phạm vi, không sử dụng cho mọi trang thống kê.

Ví dụ:

~~~java
PreparedStatement read = session.prepare(
    "SELECT status, version FROM account_service.orders_by_id " +
    "WHERE order_id = ?"
);

BoundStatement serialRead = read.bind(orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.SERIAL)
    .setTimeout(Duration.ofSeconds(5));

Row row = session.execute(serialRead).one();
~~~

Đây là truy vấn theo **đầy đủ partition key**. Không dùng serial read để “hợp thức hóa” truy vấn cần quét toàn cluster. Nếu không có yêu cầu trạng thái Paxos nhất quán, regular read theo partition key vẫn phù hợp hơn về chi phí.

## 13. Timeout LWT: applied chưa chắc là true hay false

Một LWT cần điều phối các replica. Nếu coordinator/driver timeout sau một phần giao thức, client có thể **không biết chắc kết quả cuối cùng**.

~~~mermaid
sequenceDiagram
    participant API
    participant D as Driver
    participant C as Coordinator
    participant R as Replicas
    API->>D: INSERT IF NOT EXISTS
    D->>C: Conditional mutation
    C->>R: Paxos/learn
    R-->>C: Có replica đã tham gia
    C--xD: Phản hồi mất hoặc trễ
    D-->>API: Timeout
    Note over API,R: Không kết luận được applied
~~~

| Đầu ra | Ý nghĩa | Ứng dụng nên làm |
| --- | --- | --- |
| `[applied]=true` | Điều kiện thành công trong request được trả kết quả | Tiến hành workflow thành công |
| `[applied]=false` | Điều kiện không thỏa | Phân biệt conflict và retry cùng tác vụ |
| Timeout/network failure | Kết quả không rõ | Đối chiếu row, request ID, revision; retry có kiểm soát |

Lỗi kết nối không tự mang nghĩa “row chưa được tạo”. Không viết workflow POST tạo account kiểu “timeout thì tạo user ID khác và gửi lại” vì có thể sinh side effect lặp.

### 13.1. Thiết kế idempotency key

Một API có thể nhận:

~~~text
POST /accounts
Idempotency-Key: signup-request-123
Payload: email=alice@example.test, userId=A
~~~

Khi timeout và client gửi lại:

1. Nếu đã xử lý cùng request ID + payload → trả lại kết quả hợp đồng.
2. Nếu row hiện tại thuộc user/request khác → báo conflict.
3. Nếu trạng thái chưa rõ → đối soát/đọc lại theo primary key, không phát side effect.
4. Không gửi email/charge/event hai lần chỉ vì có một retry.

`INSERT IF NOT EXISTS` ngăn tạo trùng theo điều kiện row, nhưng không tự đảm bảo “exactly-once” qua database, message broker, email và các bảng read model.

### 13.2. Retry theo loại lỗi

- `[applied]=false` thường là xung đột hợp lệ, không phải lỗi hạ tầng cần retry ngay.
- Timeout phải phân loại: driver deadline, server/Paxos timeout, replica unavailable hay mạng.
- Nếu request còn hợp lệ, retry **hữu hạn** có exponential backoff + jitter.
- Có tổng deadline ở API/job.
- Kiểm soát speculative execution, không đánh dấu mọi CAS là idempotent để driver tự phát nhiều attempts.
- Ghi log request ID và outcome theo chính sách bảo mật; không log payload/PII dư thừa.

## 14. Contention, hot key và chi phí LWT

Một khóa bị nhiều writer tranh chấp là trường hợp đặc biệt tốn kém:

~~~text
100 requests đọc version=1
    -> nhiều request CAS cùng version=1
    -> phần lớn thua
    -> đọc lại version mới
    -> retry và tăng contention
~~~

LWT không làm một hot partition scale tuyến tính. Khi `CAS applied=false` liên tục tăng, cần xác định có vấn đề business concurrency hay chỉ retries gây tải.

### 14.1. Những chỉ số nên đo

| Nhóm | Metrics |
| --- | --- |
| API | p50/p95/p99 latency, timeout, error budget |
| LWT | Applied true/false, conditional conflicts, CAS timeout |
| Driver | Retry, speculative attempts, in-flight, request failures |
| Cluster | CPU, I/O, GC/heap, compaction, read/write latency |
| Topology | Replica health, RF, local DC, WAN latency |
| Data | Hot key QPS, partition size, tombstone, write amplification |

Benchmark một request `IF NOT EXISTS` không đủ. Phải kiểm thử **cùng một khóa** với nhiều writer, đồng thời đo traffic thông thường để chắc rằng LWT không làm toàn hệ thống chậm đi.

### 14.2. Giảm contention bằng thiết kế

Nếu nghiệp vụ cho phép, có thể:

- Định tuyến các cập nhật của cùng aggregate ID qua một writer/queue có partitioning.
- Giới hạn số CAS đồng thời trên cùng key.
- Trả conflict và yêu cầu người dùng tải lại thay vì retry mù.
- Dùng idempotency key để tránh hai request logic giống nhau tranh chấp không cần thiết.
- Giảm phạm vi row/field mà nhiều người cùng cập nhật.
- Tách read model cho danh sách/analytics khỏi write path có điều kiện.

Đừng thay `SERIAL` bằng `LOCAL_SERIAL` chỉ để hạ latency nếu nghiệp vụ vẫn cần global uniqueness đa vùng.

## 15. Không trộn writer có CAS với writer không điều kiện

Nếu một đường thực hiện:

~~~sql
UPDATE account_service.orders_by_id
SET status = 'PAID', version = 2
WHERE order_id = ?
IF status = 'CREATED' AND version = 1;
~~~

nhưng đường khác ghi:

~~~sql
UPDATE account_service.orders_by_id
SET status = 'CANCELLED', version = 99
WHERE order_id = ?;
~~~

thì writer thứ hai không tham gia điều kiện CAS. Việc một trong các writer dùng `SERIAL` **không tự buộc** writer khác tuân thủ cùng business invariant.

Cần kiểm soát:

1. Owner ghi mỗi field/table và quyền của từng adapter.
2. Mọi đường ghi cạnh tranh đều dùng condition/protocol tương thích.
3. Backfill, migration và replay có quy trình riêng.
4. Ghi theo version không nhầm với write timestamp của Cassandra.
5. Khi có read model khác bảng, projector/outbox/reconciliation có trách nhiệm riêng.

### 15.1. LWT không phải giao dịch ACID đa bảng

~~~text
accounts_by_email -> uniqueness key
accounts_by_id    -> profile chính
events_by_account -> audit/read model
~~~

Một CAS trên `accounts_by_email` không tự đảm bảo ghi profile, xuất event hoặc gửi email như một transaction đa hệ thống. Cassandra logged batch và LWT có hợp đồng khác nhau; không suy rằng logged batch tạo serializable transaction giữa mọi bảng.

## 16. Lựa chọn LWT so với phương án khác

| Bài toán | LWT phù hợp? | Ghi chú |
| --- | --- | --- |
| Unique email trên cùng primary key | Có | `IF NOT EXISTS` và request ID |
| Transition trạng thái theo version | Có | `UPDATE ... IF version = ?` |
| Feed sản phẩm theo thời gian | Thường không | Bảng theo partition/clustering, cursor |
| Đếm lượt xem tăng liên tục | Không mặc định | Counter/event aggregation + dedup |
| Mỗi đơn có audit event mới | Có thể không cần LWT | Event ID ổn định, partition/bucket phù hợp |
| Giao dịch Cassandra + email | Một LWT không đủ | Outbox/workflow/idempotency |
| Global unique ở nhiều DC | Có thể cần `SERIAL` hoặc home DC | Benchmark WAN/failover |
| Một ví điện tử bị ghi nghìn lần/giây | Có thể cần invariant nhưng hot | Writer sequencing, contention test |

Một thiết kế đáng tin cậy bắt đầu bằng **bất biến cần bảo vệ và phạm vi primary key**, rồi mới chọn serial/regular CL và chiến lược vận hành.

## 17. Case study: đăng ký tài khoản từ hai khu vực

Một sản phẩm có API tại `dc1` và `dc2`. Hai API đều có thể nhận cùng email gần như đồng thời. Yêu cầu:

- Email được gắn với tối đa một account hợp lệ.
- Retry không tạo hai user ID hoặc phát email onboarding hai lần.
- Dashboard có thể trễ nhưng **nguồn uniqueness** phải đúng.
- Có giới hạn latency p99 và hành vi xác định khi một DC/network bị lỗi.
- Hệ thống có thể quan sát CAS conflicts và biết khi nào cần can thiệp vận hành.

### 17.1. Ba lựa chọn kiến trúc

**Lựa chọn A — Home DC cho mọi conditional writer:** Định tuyến tất cả request ghi cùng bất biến về DC có thẩm quyền. Cặp `LOCAL_SERIAL + LOCAL_QUORUM` có thể phù hợp khi chỉ DC đó có quyền quyết định. Đổi lại, phải kiểm soát routing và failover để tránh hai DC cùng thành writer authoritative.

**Lựa chọn B — Writer ở nhiều DC, dùng serial toàn phạm vi:** Dùng `SERIAL` khi cần phối hợp Paxos theo phạm vi toàn replication, kết hợp regular CL/read strategy đã được kiểm chứng. Cách này có thể tăng WAN latency và gặp giới hạn availability khi network/DC lỗi.

**Lựa chọn C — Tầng điều phối nghiệp vụ:** Một service/queue tạo hoặc cấp ownership cho email trước khi ghi read models Cassandra. Có thể giúp xử lý retry/event/outbox rõ hơn trong một số kiến trúc, nhưng thêm thành phần cần vận hành và khôi phục khi lỗi.

Không có phương án thắng trong mọi trường hợp. Quyết định cần dựa trên **bất biến**, topology thật, chi phí WAN, khả năng phục hồi và SLA.

### 17.2. Bảng so sánh sau khi load test

| Tình huống | Kỳ vọng |
| --- | --- |
| Hai writer cùng email trong một DC | Conditional create chỉ có một request thắng |
| Hai writer cùng email từ hai DC | Nếu cần global uniqueness, policy phải phối hợp đủ phạm vi |
| Retry cùng request ID | Trả lại kết quả theo hợp đồng, không sinh side effect mới |
| Retry cùng email nhưng khác user ID | Phân biệt business conflict, không xem là cùng yêu cầu |
| Một replica down, RF3 và local quorum | Hai replica khỏe có thể đáp ứng nếu mạng/role cho phép |
| Paxos quorum không đạt | Lỗi/timeout có kiểm soát, không tuyên bố chắc applied=false |
| Failover home writer tới DC khác | Không cho split-brain cùng khóa nếu dùng LOCAL_SERIAL |
| Read tại remote DC ngay sau local commit | Có thể trễ; phải tuân read visibility contract |
| Read model được projector cập nhật chậm | Không ảnh hưởng nguồn uniqueness, nhưng UI cần biết độ trễ |
| Rất nhiều request cùng một email | Theo dõi CAS conflicts/hot-key latency, hạn chế retry |

### 17.3. Kiểm soát timeout và hậu xử lý

API tạo account nên trả phản hồi theo ba nhóm:

- **Created**: `[applied]=true`, workflow xác nhận thành công.
- **Already exists/conflict**: `[applied]=false`, sau khi đối chiếu identity/request ID.
- **Unknown/pending verification**: timeout hoặc mạng khiến outcome chưa rõ.

Không phát sự kiện “AccountCreated” chỉ vì đã gửi một request CQL; hãy phát khi đã có bằng chứng mutation thành công và dùng outbox/deduplication để tránh side effects lặp.

## 18. Thực hành: test cạnh tranh và lỗi đa vùng

### 18.1. Test hai writer cùng khóa

Với JUnit 5 và một cluster **test** khỏe, phát nhiều request đăng ký cùng email nhưng user ID khác nhau. Khi không có timeout, đúng một conditional mutation được áp dụng.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.Test;

class AccountLwtIntegrationTest {

    private AccountRegistrationDao dao;

    @Test
    void oneWinnerForSameEmail() {
        String email = "race-" + UUID.randomUUID()
            + "@example.test";

        ExecutorService pool = Executors.newFixedThreadPool(8);

        try {
            List<CompletableFuture<Boolean>> tasks =
                java.util.stream.IntStream.range(0, 8)
                    .mapToObj(i -> CompletableFuture.supplyAsync(
                        () -> dao.register(email, UUID.randomUUID()),
                        pool
                    ))
                    .toList();

            long appliedCount = tasks.stream()
                .map(CompletableFuture::join)
                .filter(Boolean::booleanValue)
                .count();

            assertEquals(1L, appliedCount);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

**Đây là skeleton integration test.** Trước khi chạy, cần tạo/inject `dao` và kết nối Cassandra test, dùng schema phù hợp, đảm bảo test fixture không có email đó. Nếu có timeout, không suy rằng request đã thất bại từ exception để khẳng định đúng một winner; phải đối chiếu kết quả thực tế và trạng thái không rõ.

### 18.2. Test theo từng cặp CL

Thử ở môi trường được phép:

~~~text
Case A: regular=LOCAL_QUORUM, serial=LOCAL_SERIAL
Case B: regular=QUORUM,       serial=SERIAL
Case C: regular=LOCAL_ONE,    serial=LOCAL_SERIAL
~~~

So sánh:

1. Tỷ lệ `[applied]=true` và `false` khi contention cao.
2. p50/p95/p99 và timeout sau khi một replica bị chậm/down.
3. Regular read `LOCAL_ONE` vs `LOCAL_QUORUM` ngay sau CAS.
4. Ảnh hưởng retry/bounded backoff tới request rate.
5. Resource usage trên replicas và coordinator.
6. Trạng thái version khi concurrent update vào cùng row.
7. Độ ổn định của response contract khi lỗi mạng.

Không benchmark bằng cách tạo một key mới cho mỗi request rồi tuyên bố LWT “không có contention”: đó là workload khác.

### 18.3. Kiểm thử multi-DC

Một test thực sự có hai DC cần bao gồm:

- Writer A tại dc1 và writer B tại dc2, cùng email.
- LOCAL_SERIAL ở hai nơi để hiểu **giới hạn** phạm vi, không dùng làm bằng chứng uniqueness toàn cụm.
- SERIAL khi invariant yêu cầu global conditional ordering.
- Network latency và partition giữa DC, coordinator/node failure.
- Regular learn phase nhận timeout sau khi một phần Paxos đã tiến hành.
- Serial/regular reads từ hai DC sau ghi thành công.
- Thay đổi quyền writer khi failover, kiểm tra tránh split-brain.
- Retry cùng request ID khi kết quả ghi không rõ.
- Số CAS conflicts và tail latency ở các tình huống nói trên.
- Một đường ghi vô điều kiện thử nghiệm để chứng minh vì sao cần chặn writer bypass.

Test một node đơn lẻ **không chứng minh** semantics SERIAL/LOCAL_SERIAL ở topology nhiều DC.

## 19. Runbook vận hành khi LWT có vấn đề

### 19.1. Khi [applied]=false tăng đột biến

1. Xem có client retry cùng request ID hay user thực sự tranh cùng khóa.
2. Xác minh code có normalize email / định danh primary key nhất quán.
3. Với version CAS, xem các writer có đọc version cũ kéo dài hay không.
4. Tìm hot keys và phân bố request theo partition.
5. Phân biệt conflict nghiệp vụ đúng (HTTP 409) với bug luồng trạng thái.
6. Giới hạn retry; không tự mở thêm concurrency khi contention cao.
7. Ghi nhận metrics và business impact, tránh log PII quá mức.

### 19.2. Khi LWT timeout/unavailable

- Đọc regular CL và serial CL **thực tế** trên statement/profile.
- Kiểm tra RF của keyspace, driver local DC và node/rack availability.
- Kiểm tra WAN latency nếu `SERIAL` phối hợp giữa nhiều DC.
- Phân loại driver request timeout, server/Paxos timeout, unavailable và lỗi mạng.
- Kiểm tra request đã áp dụng chưa bằng row/version/request ID theo workflow.
- Kiểm tra driver retries/speculative attempts và mức in-flight.
- Không âm thầm đổi `SERIAL` thành `LOCAL_SERIAL` khi cần invariant toàn cục.
- Không tăng timeout mù để che hot key hoặc quorum không đạt.

### 19.3. Khi regular read thấy dữ liệu cũ

Kiểm tra:

1. Read CL và write/learn CL có khớp hợp đồng không.
2. Các request đọc/ghi đang ở cùng DC hay khác DC.
3. LWT đã trả `[applied]=true` hay vẫn có unknown outcome.
4. Có writer không CAS hoặc custom timestamp bất thường không.
5. Đây có thật sự là **cùng bảng** hay một bảng read model cập nhật qua projector.
6. Có cần serial read cho điểm kiểm tra nghiệp vụ đó không.
7. Replication/projection lag có vượt giới hạn được chấp nhận không.

Không tăng serial CL của writer rồi tự cho rằng mọi dashboard trên mọi DC đã có snapshot toàn cục.

### 19.4. Khi p99 tăng mạnh

~~~text
1. Xem p99 HTTP và số request cùng key.
2. Xem applied=false, CAS timeouts và retries.
3. Kiểm tra health/RF của replica và local DC.
4. Nếu SERIAL multi-DC: xem WAN latency và mạng chập chờn.
5. Kiểm tra driver pool, in-flight và speculative attempts.
6. Kiểm tra CPU/GC/disk I/O/compaction trên Cassandra.
7. Giảm request không thiết yếu, hạn chế contention.
8. Chỉ thay chính sách CL khi hiểu ảnh hưởng tới correctness.
~~~

## 20. Các ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “LOCAL_QUORUM tự biến read-then-write thành CAS.” | Chỉ conditional mutation qua LWT mới bảo vệ điều kiện atomic. |
| “SERIAL và QUORUM là cùng một thuộc tính.” | Một cái là serial/Paxos CL; cái kia regular CL. |
| “LOCAL_SERIAL đảm bảo unique toàn thế giới.” | Nó là phạm vi local; multi-DC writers cần lựa chọn rộng hơn hoặc home routing. |
| “Chỉ set serial CL là đủ, không cần IF.” | Không có `IF` thì không có conditional mutation. |
| “LWT thành công nghĩa là mọi DC đã nhìn thấy.” | Read visibility phụ thuộc regular CL, placement và replication. |
| “LOCAL_ONE sau CAS sẽ luôn đọc thấy version mới.” | Đọc từ replica chưa cập nhật có thể thấy giá trị cũ. |
| “applied=false luôn là lỗi hạ tầng.” | Điều kiện sai là outcome bình thường trong cạnh tranh. |
| “Timeout nghĩa là CAS chắc chắn không thành công.” | Kết quả có thể đã được áp dụng. |
| “Spring Data @Version chỉ tăng long.” | Optimistic locking dùng LWT/conditional CQL. |
| “Mọi repository.save đều có CAS.” | Cần `@Version`/API điều kiện và mapping đúng. |
| “Version cao hơn tự thắng trong UPDATE thường.” | Cassandra dùng conflict resolution theo write timestamps, không tự so version. |
| “LWT tương đương transaction giữa mọi bảng.” | Bất biến nhiều bảng/hệ thống cần workflow riêng. |
| “SERIAL cho tất cả SELECT vừa nhanh vừa an toàn.” | Serial reads có overhead, chỉ dùng khi cần. |
| “Ghi ở consistency mạnh sẽ loại mọi CAS conflict.” | Conflict nghiệp vụ vẫn tồn tại và phải xử lý. |
| “Không cần test network partition.” | SERIAL/LOCAL_SERIAL phụ thuộc topology và phạm vi coordination. |
| “Tăng timeout sẽ chữa hot key.” | Cần điều phối writer và giảm contention. |
| “LWT có nghĩa exactly-once qua email/broker.” | Cần idempotency và outbox/reconciliation. |
| “Có thể trộn CAS với upsert vô điều kiện tùy ý.” | Writer bypass condition có thể phá invariant. |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `SELECT` ở `LOCAL_QUORUM` rồi `INSERT` thường vẫn có race?

*Gợi ý:* Hai request có thể cùng đọc trạng thái chưa tồn tại trước khi ghi.

**Câu 2.** Regular CL và serial CL áp dụng vào hai pha nào của LWT?

*Đáp án:* Regular cho apply/learn và visibility; serial cho Paxos/conditional ordering.

**Câu 3.** Với RF=3 trong một DC, `LOCAL_QUORUM` cần mấy replica?

*Đáp án:* Hai replica theo giả định topology khỏe.

**Câu 4.** Khi nào `LOCAL_SERIAL` có thể đủ?

*Gợi ý:* Các writer của cùng một invariant được giới hạn ở một DC authoritative và failover được kiểm soát.

**Câu 5.** Vì sao hai `LOCAL_SERIAL` tại dc1/dc2 không tạo bảo đảm tuyến tính hóa toàn cụm?

*Gợi ý:* Các pha Paxos local không phối hợp trên phạm vi toàn replication.

**Câu 6.** `[applied]=false` có đồng nghĩa timeout?

*Đáp án:* Không, đó là kết quả điều kiện không thỏa.

**Câu 7.** Timeout sau `INSERT IF NOT EXISTS` có chắc row chưa được tạo không?

*Đáp án:* Không; cần xác minh theo primary key/request ID.

**Câu 8.** `setSerialConsistencyLevel` trên INSERT không có `IF` có tạo CAS không?

*Đáp án:* Không.

**Câu 9.** Spring Data `@Version` dùng cơ chế nào?

*Đáp án:* Optimistic locking qua LWT/conditional statements.

**Câu 10.** Sau conditional write ở dc1 với regular `LOCAL_QUORUM`, đọc `LOCAL_ONE` tại dc2 có chắc đọc được ngay không?

*Đáp án:* Không.

**Câu 11.** Vì sao writer UPDATE thường có thể phá version invariant?

*Gợi ý:* Nó không tham gia điều kiện CAS.

**Câu 12.** Phải benchmark trường hợp nào để hiểu CAS contention?

*Gợi ý:* Nhiều request đồng thời cùng primary key, không chỉ key khác nhau.

**Câu 13.** Trong Java Driver 4.x, tên hằng enum là gì?

*Đáp án:* `DefaultConsistencyLevel.LOCAL_SERIAL` và `DefaultConsistencyLevel.LOCAL_QUORUM`.

**Câu 14.** Vì sao `SERIAL` có thể làm latency tăng trong multi-DC?

*Gợi ý:* Phải phối hợp quorum/replicas trong phạm vi rộng hơn, có thể liên quan WAN.

## 22. Checklist triển khai production

- **Bất biến:** Xác định luật uniqueness/transition và phạm vi khóa phải bảo vệ.
- **Schema:** Primary key đúng để các writer cạnh tranh gặp cùng partition/row.
- **Conditional CQL:** Có `IF NOT EXISTS` hoặc `IF version/status = ...`; không dựa vào read-then-write.
- **Regular CL:** Chọn theo RF, topology và read-after-write contract.
- **Serial CL:** `LOCAL_SERIAL` cho scope local có thẩm quyền; `SERIAL` cho conditional coordination toàn replication khi cần.
- **Multi-DC:** Có chiến lược routing/failover, không để split-brain writer nếu chỉ bảo vệ local.
- **Driver:** Dùng `DefaultConsistencyLevel`, phân biệt hai setter và kiểm tra profile overrides.
- **Spring Data:** `@Version` mapping đúng, truyền QueryOptions nếu API hỗ trợ.
- **Response:** Diễn giải `[applied]=true/false` và timeout khác nhau.
- **Retry:** Idempotency key, bounded backoff, không lặp side effects.
- **Read semantics:** Regular reads không tự là serial reads; kiểm tra DC/CL.
- **Contention:** Đo hot-key QPS, CAS conflicts và p95/p99.
- **Quorum failures:** Test node down, network partition, WAN latency và failover.
- **Writer safety:** Không để upsert không điều kiện bypass LWT trên fields cần invariant.
- **Read models:** Đồng bộ denormalized tables, event broker và email qua workflow rõ ràng.
- **Observability:** Tỷ lệ CAS applied, timeouts, retries, pool, replicas, RF/DC và logs tối thiểu.
- **CQL correctness:** Không nhầm write timestamp với business version hoặc LWT.
- **Rollback:** Có feature flag, giảm traffic/cạnh tranh, không hạ consistency mù.
- **Không chạy STEP_6 ở bước này:** Chuyên sâu QA nội dung sẽ được thực hiện theo giai đoạn sau của quy trình.

## Tài liệu tham khảo

- [Apache Cassandra — Lightweight Transactions/Guarantees](https://cassandra.apache.org/doc/latest/cassandra/architecture/guarantees.html): Paxos, linearizability và giới hạn của LWT.
- [Apache Cassandra — cqlsh Consistency](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): `CONSISTENCY` và `SERIAL CONSISTENCY`.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): conditional INSERT/UPDATE/DELETE.
- [Java Driver 4.x — Statement API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/Statement.html): set regular/serial consistency và statement immutable.
- [Java Driver 4.x — Reference Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/reference/): `basic.request.consistency` / `serial-consistency`.
- [Spring Data Cassandra — Optimistic Locking](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `@Version` và LWT.
- [Spring Data Cassandra — QueryOptions Builder](https://docs.spring.io/spring-data/cassandra/reference/api/java/org/springframework/data/cassandra/core/cql/QueryOptions.QueryOptionsBuilder.html): regular CL và serial CL qua Spring Data.

## Kết luận

**LWT dùng hai mức consistency với hai nhiệm vụ khác nhau.** **Serial consistency** (`SERIAL` / `LOCAL_SERIAL`) quyết định phạm vi Paxos để xử lý điều kiện; **regular consistency** (`LOCAL_QUORUM`, `QUORUM`, `LOCAL_ONE`...) quyết định mức xác nhận ở giai đoạn ghi/learn và khả năng quan sát của những phép đọc thường. Đặt serial CL không tự tạo CAS nếu CQL thiếu `IF`, và tăng regular CL không loại bỏ race của read-then-write.

Trong **SPRING_DATA_CASSANDRA**, hãy chọn cặp CL từ **bất biến nghiệp vụ, replication factor và vị trí writers/readers**. Với một home DC có thể cân nhắc `LOCAL_SERIAL + LOCAL_QUORUM`; với nhiều DC cùng viết vào cùng khóa và cần global linearizability phải xem xét `SERIAL` cùng read strategy/failover phù hợp. `@Version` của Spring Data, `BoundStatement` của Java Driver và các conditional CQL là công cụ triển khai, nhưng không tự tạo transaction đa bảng hay exactly-once. Kiểm thử contention, timeouts, network partition, idempotency và quan sát hiệu năng mới giúp lựa chọn consistency trở nên đáng tin cậy trong Cassandra phân tán.




