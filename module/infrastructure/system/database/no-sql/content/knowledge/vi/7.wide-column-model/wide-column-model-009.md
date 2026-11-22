# Cập nhật có điều kiện, bộ đếm và phạm vi nguyên tử theo từng hệ

Trong mô hình **cột rộng (wide-column)**, dữ liệu được tổ chức theo khóa hàng hoặc khóa phân vùng để hỗ trợ truy cập phân tán. Các hệ Apache Cassandra, Apache HBase và Google Cloud Bigtable đều có cách cập nhật dữ liệu cạnh tranh, nhưng **khả năng bảo đảm tính nguyên tử, cú pháp điều kiện và cơ chế đếm của chúng khác nhau**.

Giả sử chỉ còn một sản phẩm trong kho. Hai request đọc cùng giá trị `available = 1`, rồi cùng quyết định bán một sản phẩm và ghi `available = 0`. Dữ liệu cuối cùng có vẻ hợp lệ nhưng hệ thống đã xác nhận hai đơn hàng. Một lỗi khác xảy ra khi hai request cùng tăng số lượt xem từ 100 lên 101: nếu mỗi request tự đọc rồi ghi lại, một lượt tăng có thể bị mất.

Cập nhật có điều kiện (*conditional update*) và bộ đếm (*counter*) được sinh ra để giải quyết những kiểu cạnh tranh nhất định. Tuy nhiên, **increment nguyên tử không đồng nghĩa với đếm đúng một lần khi request được gửi lại**, và **transaction trên một hàng không đồng nghĩa với transaction giữa nhiều hàng**.

Bài học này sẽ đi từ cách hiểu chính xác tính nguyên tử đến các ví dụ Cassandra/CQL, HBase, Bigtable và quyết định thiết kế cho tồn kho, thống kê, đơn hàng, đặt chỗ và giao dịch liên hệ nhiều thực thể. Các ví dụ cần được áp dụng theo phiên bản hệ quản trị và driver thực tế; phần mã giả sẽ được ghi rõ để không nhầm với API chạy được.

## 1. Phân biệt nguyên tử, cô lập, nhất quán và chống lặp

Một thao tác được gọi là **nguyên tử (atomic)** khi nó được áp dụng trọn vẹn hoặc không được áp dụng theo phạm vi bảo đảm của hệ thống. Ví dụ, nếu thay đổi `status` và `version` trên **một hàng** là nguyên tử thì không nên quan sát hàng chỉ đổi status mà chưa đổi version trong những điều kiện quan sát được cam kết.

**Isolation** nói về cách các thao tác đồng thời tương tác. Cập nhật nguyên tử không tự bảo vệ cả chuỗi thao tác “đọc → kiểm tra → tính toán → ghi” được thực hiện bằng nhiều request riêng. Các request khác có thể chen vào giữa bước đọc và ghi.

**Consistency** có nhiều nghĩa: quy tắc nghiệp vụ như “không bán vượt tồn kho”; mức consistency khi đọc/ghi các replica; hoặc thuộc tính mạnh hơn như linearizability của một thao tác. Cần xác định đang nói nghĩa nào thay vì chỉ ghi “database strong consistency”.

**Idempotency** nghĩa là yêu cầu được thực hiện lại vẫn chỉ có hiệu ứng nghiệp vụ như một lần. Cập nhật giá trị cố định có thể idempotent về trạng thái cuối, còn `counter = counter + 1` thì không. Một increment được thực thi hai lần sẽ tăng hai lần, kể cả mỗi increment đều nguyên tử.

| Câu hỏi | Tính chất cần xem |
|---|---|
| Hai tiến trình cùng trừ một mặt hàng có bán vượt không? | Điều kiện ghi + isolation ở đối tượng cần bảo vệ |
| Các field `status` và `version` có đổi cùng nhau không? | Atomicity theo hàng/partition được hỗ trợ |
| Ghi thành công rồi mất phản hồi, retry có ghi lặp không? | Idempotency và khả năng xác minh outcome |
| Replica khác đã thấy giá trị mới chưa? | Read/write consistency, replication semantics |
| Cập nhật đơn hàng và tồn kho trên hai khóa có cùng commit không? | Transaction scope hoặc điều phối liên thực thể |
| Lượt xem tăng bao nhiêu khi có nhiều request đồng thời? | Atomic increment và chiến lược chống đếm lặp |

Một hệ wide-column không tự bảo đảm toàn bộ những tính chất này chỉ vì nó có API “update”.

## 2. Bẫy kinh điển: read-modify-write trong ứng dụng

Tồn kho ban đầu:

~~~text
item = SKU-01
available = 1
version = 7
~~~

Hai worker cùng thao tác:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as Database
    A->>DB: Đọc available=1
    B->>DB: Đọc available=1
    DB-->>A: 1
    DB-->>B: 1
    A->>DB: Ghi available=0
    B->>DB: Ghi available=0
    DB-->>A: Thành công
    DB-->>B: Thành công
~~~

Hàng cuối cùng còn `0` nhưng **hai đơn được xác nhận**. Đọc được dữ liệu đúng tại thời điểm T không có nghĩa dữ liệu vẫn đúng tại thời điểm ghi T+1.

Hướng xử lý là cập nhật có điều kiện, chẳng hạn:

~~~text
IF version == 7
THEN SET available = 0, version = 8
ELSE return CONFLICT
~~~

Nếu thao tác kiểm tra và ghi được hệ DB thực hiện nguyên tử trong một phạm vi phù hợp, một worker thắng. Worker còn lại thấy điều kiện không còn đúng; nó phải đọc lại hoặc từ chối, không tiếp tục ghi đè dựa trên dữ liệu cũ.

Điểm quan trọng: **điều kiện phải phản ánh bất biến cần bảo vệ**. Nếu mọi writer cập nhật `available` đều tăng `version`, điều kiện theo version sẽ phát hiện cạnh tranh. Nếu có writer ghi `available` mà không tăng version, toàn bộ hợp đồng phiên bản bị phá vỡ.

## 3. Ba họ cơ chế trong wide-column

| Hệ | Đơn vị dữ liệu thường thao tác | Cập nhật có điều kiện | Bộ đếm/tăng | Ranh giới cần nhớ |
|---|---|---|---|---|
| **Apache Cassandra** | Hàng CQL thuộc partition được xác định bởi partition key | `INSERT ... IF NOT EXISTS`, `UPDATE ... IF ...` qua lightweight transaction (LWT) | Cột kiểu `counter`, phép cộng/trừ | LWT có chi phí đồng thuận; không suy ra transaction tổng quát nhiều partition |
| **Apache HBase** | Hàng theo row key, cell trong column family | `CheckAndMutate` và các row mutation phù hợp | `Increment`, `incrementColumnValue` | Bảo đảm nguyên tử chính ở phạm vi **một hàng** |
| **Google Cloud Bigtable** | Hàng theo row key, family, qualifier và timestamp | `CheckAndMutateRow` | `ReadModifyWriteRow` với increment | Thao tác một hàng nguyên tử theo API; không tự có transaction nhiều hàng |

Cassandra có mô hình CQL và partition; HBase/Bigtable có cấu trúc row key và cell có phiên bản. Vì vậy, “wide-column” mô tả một họ giải pháp lưu trữ, **không phải một chuẩn chung về transaction**.

## 4. Cassandra: tạo bản ghi có điều kiện bằng LWT

Dùng một bảng tồn kho minh họa:

~~~sql
CREATE TABLE inventory_by_item (
    tenant_id text,
    item_id text,
    available int,
    version bigint,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, item_id))
);
~~~

Trong bảng này, `(tenant_id, item_id)` là partition key tổng hợp. Một cặp xác định đúng hàng cần cập nhật. Đây là mô hình học tập, không mặc nhiên là cách phân vùng tốt nhất cho mọi nhu cầu tìm kiếm.

Để chỉ tạo hàng mới khi chưa tồn tại:

~~~sql
INSERT INTO inventory_by_item (
    tenant_id, item_id, available, version, updated_at
)
VALUES (
    'shop-17', 'SKU-01', 12, 0, toTimestamp(now())
)
IF NOT EXISTS;
~~~

Cassandra dùng **lightweight transaction (LWT)** cho lệnh conditional insert/update. Kết quả thường có trường `[applied]`: nếu `true`, điều kiện được áp dụng; nếu `false`, điều kiện không thỏa. Đây là kết quả cạnh tranh hợp lệ, không nhất thiết là lỗi database.

Nếu dùng insert thông thường trên khóa đã có, cần hiểu semantics ghi đè của Cassandra; đừng dựa vào nó để chặn tạo thực thể trùng.

## 5. Cassandra: cập nhật theo phiên bản với `IF`

Giả sử đọc được:

~~~text
tenant_id = shop-17
item_id = SKU-01
available = 12
version = 7
~~~

Ứng dụng muốn trừ một sản phẩm, tính ra `available = 11` và `version = 8`:

~~~sql
UPDATE inventory_by_item
SET available = 11,
    version = 8,
    updated_at = toTimestamp(now())
WHERE tenant_id = 'shop-17'
  AND item_id = 'SKU-01'
IF version = 7;
~~~

Có hai kết quả nghiệp vụ:

- **`[applied] = true`:** hàng còn version 7 và cập nhật được áp dụng.
- **`[applied] = false`:** trạng thái kỳ vọng không còn đúng; request phải đọc lại dữ liệu hoặc trả lỗi xung đột.

Luồng xử lý:

1. Đọc `available` và `version`.
2. Nếu số lượng cần mua lớn hơn `available`, từ chối.
3. Tính giá trị mới và version kế tiếp.
4. Gửi một conditional update, không tách kiểm tra version và ghi thành hai thao tác.
5. Nếu thành công, hoàn tất bước xử lý tồn kho.
6. Nếu điều kiện không thỏa, đọc lại rồi thử có giới hạn hoặc trả conflict.

~~~text
function reserve(itemId, quantity):
    repeat up to MAX_ATTEMPTS:
        row = read(itemId)
        if row.available < quantity:
            return OUT_OF_STOCK

        applied = compareAndSet(
            itemId = itemId,
            expectedVersion = row.version,
            nextAvailable = row.available - quantity,
            nextVersion = row.version + 1
        )

        if applied:
            return RESERVED

    return RETRYABLE_CONFLICT
~~~

Đây là **mã giả thuật toán**, không phải một driver API đầy đủ. Dùng `MAX_ATTEMPTS` và backoff thích hợp để tránh nhiều worker cùng retry liên tục trên hàng nóng.

### 5.1. Máy trạng thái cũng cần CAS

Ví dụ đơn hàng chỉ được chuyển từ `PENDING` sang `PAID`:

~~~sql
CREATE TABLE order_status_by_id (
    tenant_id text,
    order_id text,
    status text,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

UPDATE order_status_by_id
SET status = 'PAID',
    version = 2
WHERE tenant_id = 'shop-17'
  AND order_id = 'ORD-7008'
IF status = 'PENDING'
   AND version = 1;
~~~

Hai request thanh toán và hủy đơn cùng xuất phát từ `PENDING` không nên cùng được ghi là hoàn tất. Điều kiện trạng thái và version giúp biến chuyển trạng thái thành một thao tác được bảo vệ.

Nhưng một cập nhật thành công trên hàng đơn hàng **không tự chứng minh** cổng thanh toán ngoài hệ đã xử lý tiền đúng một lần. Bài toán liên dịch vụ cần idempotency, trạng thái nghiệp vụ và đối soát.

## 6. Chi phí và giới hạn của LWT

LWT sử dụng cơ chế đồng thuận khi cập nhật có điều kiện. Vì vậy:

- LWT thường có **nhiều lượt trao đổi** và độ trễ cao hơn ghi CQL thông thường.
- Nhiều request tranh chấp cùng khóa có thể làm tăng retry và latency.
- Driver/cụm cần sử dụng đúng **consistency level** và **serial consistency** cho trường hợp sử dụng.
- Timeout không chứng minh thao tác đã không áp dụng; client có thể mất phản hồi sau khi trạng thái đã đổi.
- Những writer khác cập nhật cùng hàng phải tuân thủ giao thức version/điều kiện; ghi thông thường xen vào có thể phá bất biến mà chương trình kỳ vọng.

### 6.1. LWT không phải transaction xuyên mọi partition

LWT giúp xử lý cập nhật có điều kiện trong phạm vi mà Cassandra hỗ trợ. Nó không tự gộp những hành động sau thành một ACID transaction tổng quát:

~~~text
Trừ tồn kho SKU-01       -> partition mặt hàng
Tạo đơn ORD-7008         -> partition đơn hàng
Ghi giao dịch thanh toán -> dịch vụ khác
Phát event               -> broker
~~~

Nếu một phần thành công rồi phần khác lỗi, cần workflow có trạng thái trung gian, retry có kiểm soát hoặc bù trừ. Nếu yêu cầu transaction đa thực thể chặt chẽ là cốt lõi, có thể cần chọn hệ lưu trữ khác cho phần nghiệp vụ đó.

### 6.2. `BATCH` của Cassandra không tương đương transaction SQL

Cassandra hỗ trợ `BEGIN BATCH ... APPLY BATCH`, nhưng không nên hiểu rằng một batch nhiều partition có **isolation và rollback tổng quát như transaction quan hệ**.

- Logged batch có những bảo đảm thực thi cuối cùng và phục hồi riêng; không đồng nghĩa mọi reader quan sát toàn bộ partition đổi đồng thời.
- Batch qua nhiều partition có thể tăng áp lực coordinator; nó không phải công cụ tăng tốc bulk load mặc định.
- Conditional batch có những ràng buộc về câu lệnh và phạm vi partition; phải xác minh theo phiên bản Cassandra thực tế.
- Không dùng batch như cách thay thế việc thiết kế nghiệp vụ khi một thay đổi liên quan nhiều hàng.

Với một bất biến quan trọng, cần hỏi chính xác **mỗi thao tác bảo vệ hàng hoặc partition nào**, thay vì chỉ xem tên “batch”.

## 7. Cassandra counter: cú pháp và giới hạn

Cassandra có kiểu `counter` cho các số liệu cộng/trừ:

~~~sql
CREATE TABLE article_views (
    article_id text PRIMARY KEY,
    views counter
);
~~~

Tăng một lượt xem:

~~~sql
UPDATE article_views
SET views = views + 1
WHERE article_id = 'article-101';
~~~

Giảm một đơn vị:

~~~sql
UPDATE article_views
SET views = views - 1
WHERE article_id = 'article-101';
~~~

Đây là thao tác counter chuyên dụng, không phải kiểu cột `int` có thể đọc và ghi tùy ý.

| Đặc điểm | Hệ quả thiết kế |
|---|---|
| `counter` dùng phép cộng/trừ | Không tùy ý `SET views = 100` như giá trị thông thường |
| Bảng counter phải tuân thủ quy tắc schema đặc biệt | Không trộn cột counter và cột dữ liệu thông thường không thuộc khóa trong cùng bảng |
| Counter không hỗ trợ LWT `IF` như cột thông thường | Không dùng counter để CAS trạng thái có điều kiện phức tạp |
| Counter không hỗ trợ TTL như cột thông thường | Cần cơ chế retention/tái tổng hợp riêng |
| Counter update không idempotent | Retry có thể làm tăng/giảm nhiều lần |
| Một khóa counter rất nóng có chi phí riêng | Phải đo throughput, partition skew và retry |

### 7.1. Vì sao retry làm tăng trùng?

~~~text
T0 Client gửi: views = views + 1
T1 Database áp dụng tăng
T2 Response bị mất trên mạng
T3 Client thấy timeout
T4 Client retry: views = views + 1
T5 Counter có thể tăng thêm một lần
~~~

Mỗi phép increment có thể thực hiện theo cơ chế counter của database, nhưng **một logical event đã gửi hai thao tác**. Nguyên tử không giải quyết bài toán dedup.

Ba câu hỏi cần tách biệt:

- Có mất cập nhật khi nhiều phép cộng đến đồng thời không?
- Có đếm lặp khi cùng event được gửi lại không?
- Khi hệ thống bị lỗi, có thể tái dựng tổng từ nguồn dữ liệu nào?

Nếu phải chứng minh số đếm chính xác theo từng event, cần ID sự kiện và thiết kế xử lý lặp hoặc lưu event nguồn để đối soát, không chỉ có một cột counter.

### 7.2. Một bảng nguồn sự kiện để tái tính

Ví dụ lưu click theo ngày:

~~~sql
CREATE TABLE clicks_by_day (
    day date,
    event_id uuid,
    article_id text,
    occurred_at timestamp,
    PRIMARY KEY ((day), event_id)
);
~~~

Một event có định danh riêng giúp hệ thống phát hiện việc tiếp nhận lại cùng sự kiện theo chính sách khóa đã xác định. Nếu cần chặn tạo trùng, có thể dùng conditional insert phù hợp.

Tuy nhiên, ghi event và tăng counter ở **hai bảng/partition khác nhau** vẫn có thể bị gián đoạn ở giữa. Không thể chỉ thêm bảng dedup rồi tuyên bố đảm bảo exactly-once end-to-end. Cần chiến lược checkpoint, tổng hợp, đối soát và xử lý replay có chủ đích.

### 7.3. Khi nào nên dùng counter?

| Dữ liệu | Counter có phù hợp? | Điều kiện cần làm rõ |
|---|---|---|
| Lượt xem trang | Thường có thể | Có chấp nhận điều chỉnh/đối soát khi retry? |
| Thống kê truy cập theo giờ | Có thể | Cửa sổ thời gian, TTL hoặc cơ chế giữ dữ liệu |
| Số lượt click theo chiến dịch | Có thể | Nguồn event và quy tắc chống đếm lặp |
| Số lượng hàng khả dụng | Không nên chỉ dùng counter không điều kiện | Có ngăn âm và oversell được không? |
| Số dư tài khoản | Không nên dùng counter đơn lẻ | Cần sổ cái, idempotency và transaction phù hợp |
| Trạng thái ghế còn trống | Counter tổng không đủ | Phải bảo vệ từng ghế khỏi đặt trùng |

**Cộng/trừ nguyên tử không đồng nghĩa “chỉ trừ nếu còn đủ”**. Hai phép trừ trên số tồn 1 vẫn có thể dẫn tới -1. Với tồn kho phải xét CAS hoặc cơ chế đặt chỗ.

## 8. HBase: nguyên tử ở phạm vi một hàng

HBase tổ chức dữ liệu theo **row key**, column family và qualifier. Hàng ví dụ:

~~~text
rowKey = inventory#shop-17#SKU-01

state:available = 12
state:version   = 7
state:status    = ACTIVE

meta:updatedBy  = inventory-service
~~~

Tên family/qualifier và cách mã hóa giá trị chỉ là ví dụ. HBase lưu giá trị dạng byte nên ứng dụng cần thống nhất encoding cho số nguyên, chuỗi và timestamp.

### 8.1. CheckAndMutate bảo vệ điều kiện

Ý định nghiệp vụ:

~~~text
CheckAndMutate on row "inventory#shop-17#SKU-01":
    CHECK state:version == encodeLong(7)
    THEN atomically:
        PUT state:available = encodeLong(11)
        PUT state:version   = encodeLong(8)
    ELSE:
        return condition_not_met
~~~

Đây là **mã giả**. Java client HBase có API `CheckAndMutate` với các biến thể theo phiên bản; không nên chép mã giả trên thành một lệnh HBase Shell.

Điểm mấu chốt: điều kiện và các mutation được phép xảy ra **trên cùng hàng**. Nếu một bước cần cập nhật hàng `inventory#SKU-01` và hàng `orders#ORD-7008`, tính nguyên tử của thao tác một hàng không bao trùm cả hai.

### 8.2. RowMutations

HBase có cơ chế gom các mutation tương thích của **cùng row key** vào một thao tác nguyên tử. Ví dụ, khi đổi `status`, `version` và metadata cập nhật, ứng dụng có thể bảo vệ sự nhất quán giữa các qualifier của một hàng.

Nhưng không được từ đó suy ra nhiều hàng khác nhau có transaction ACID tổng quát. Một workflow nhiều hàng cần xác định trạng thái dở dang và phục hồi.

### 8.3. Increment

HBase có các API như `Increment` và `incrementColumnValue` để tăng một cell số theo encoding phù hợp.

~~~text
INCREMENT:
    rowKey = article#101
    family = metrics
    qualifier = views
    delta = +1
~~~

Ưu điểm: client không phải đọc giá trị cũ rồi ghi `value + 1` bằng hai request. Nhược điểm:

- Increment không biết hai request có cùng `eventId` hay không.
- Retry sau timeout có thể cộng lặp.
- Giá trị cell phải có kiểu mã hóa số phù hợp.
- Một row key cực nóng có thể là nút thắt dù bảng chứa rất nhiều hàng.
- Increment không tự thi hành điều kiện như “chỉ tăng khi user đã được xác minh”.

## 9. Google Cloud Bigtable: CheckAndMutateRow và ReadModifyWriteRow

Bigtable lưu các cell thuộc hàng theo row key và family/qualifier; các cell có phiên bản timestamp. Nó cung cấp các thao tác nguyên tử ở **phạm vi một hàng**.

### 9.1. Conditional row mutation

Một hàng đơn hàng:

~~~text
rowKey = order#ORD-7008
state:status = PENDING
state:version = 1
~~~

Ý định cập nhật:

~~~text
CheckAndMutateRow(
    rowKey = "order#ORD-7008",
    predicate = [state:status matches "PENDING"],
    trueMutations = [
        set state:status = "PAID",
        set state:version = encodeInt64(2)
    ],
    falseMutations = []
)
~~~

Đây là **mã giả biểu đạt hành vi**. Bigtable API dùng **row filter** để xác định predicate, cùng các mutation tương ứng khi điều kiện khớp hoặc không. Cần cấu hình predicate đúng family, qualifier, giá trị và phạm vi phiên bản cell; không được coi bản phác thảo trên là chữ ký client API.

Một thao tác hàng thành công không tự cập nhật nguyên tử hàng tồn kho khác hoặc hàng giao dịch của đối tác.

### 9.2. Atomic increment bằng read-modify-write

~~~text
ReadModifyWriteRow(
    rowKey = "article#101",
    rule = increment("metrics:views", +1)
)
~~~

Cơ chế `ReadModifyWriteRow` hỗ trợ cập nhật số đếm ở phạm vi hàng. Cần dùng đúng encoding số nguyên mà Bigtable API yêu cầu (ví dụ biểu diễn 64-bit theo quy ước API), thay vì lưu số thập phân dạng text rồi mong phép cộng đọc hiểu tự động.

**Read-modify-write nguyên tử không idempotent**: nếu thao tác đã áp dụng nhưng response bị mất, gửi lại sẽ có thể tăng lần hai.

### 9.3. Bulk mutation không tự thành transaction nhiều hàng

Nhiều API hỗ trợ gửi nhiều mutation để tăng hiệu quả truyền và xử lý, nhưng việc gộp chúng trong một call không tự tạo một transaction ACID giữa nhiều row key. Để bảo vệ một invariant liên quan nhiều hàng hoặc hệ bên ngoài, vẫn cần thiết kế quy trình tương ứng.

## 10. Đọc bảng khả năng theo nhu cầu

| Nhu cầu | Cassandra | HBase | Bigtable |
|---|---|---|---|
| Chỉ tạo nếu chưa tồn tại | `INSERT ... IF NOT EXISTS` | Conditional mutation đối với hàng chưa có | `CheckAndMutateRow` với predicate phù hợp |
| Chỉ đổi `PENDING → PAID` | `UPDATE ... IF status='PENDING'` | `CheckAndMutate` trên trạng thái hàng | `CheckAndMutateRow` trên predicate của hàng |
| CAS theo version | `UPDATE ... IF version = old` | Kiểm tra qualifier version rồi mutate hàng | Predicate version rồi mutate hàng |
| Increment số đếm | `counter` | `Increment` | `ReadModifyWriteRow` |
| Chống retry tăng lặp chỉ nhờ increment | **Không** | **Không** | **Không** |
| Nguyên tử trên nhiều hàng/partition mặc định như SQL | **Không suy ra** | **Không suy ra** | **Không suy ra** |
| Điểm nóng cần theo dõi | LWT contention tại key/partition | Hot row và region | Hot row và phân bố row key |

Các cơ chế trên bảo đảm trong **phạm vi và điều kiện sử dụng riêng**. Cần xem tài liệu engine/version trước khi sử dụng tính năng như một phần hợp đồng nghiệp vụ quan trọng.

## 11. Phạm vi nguyên tử và hệ quả đối với mô hình dữ liệu

Sơ đồ nghiệp vụ tạo đơn:

~~~text
Đơn ORD-7008
  ├── Hàng tồn kho SKU-01
  ├── Hàng trạng thái đơn ORD-7008
  ├── Hàng reservation RES-989
  └── Thanh toán ở nhà cung cấp ngoài hệ thống
~~~

Nếu mỗi bước là cập nhật nguyên tử **trên hàng riêng**, cả quy trình vẫn có thể dừng ở giữa.

Một số hướng thiết kế:

1. **Gom bất biến vào một đơn vị phù hợp:** nếu nghiệp vụ cho phép và không tạo hot row hoặc hàng quá lớn.
2. **Reservation/hold:** ghi quyền giữ tài nguyên có ID ổn định, trạng thái và hạn hiệu lực; hoàn tất hoặc giải phóng sau.
3. **Saga:** chia công việc thành các bước có trạng thái rõ và hành động bù trừ.
4. **Event và reconciliation:** lưu sự kiện có ID, xử lý idempotent và sửa trạng thái dở dang bằng nguồn sự thật.
5. **Chọn công nghệ khác cho phần cần transaction mạnh:** có thể lưu tài chính ở sổ cái/giao dịch phù hợp và wide-column cho truy vấn/historical projection.

Cần phân biệt **nguyên tử về dữ liệu** và **hoàn tất của toàn bộ quy trình nghiệp vụ**. Một API trả `202 Accepted` vì đã tiếp nhận yêu cầu bền vững không nên được diễn giải như đã hoàn thành thanh toán hoặc cấp chỗ ngồi.

## 12. Ví dụ ghế ngồi: điều kiện, hạn giữ và lỗi ABA

Trạng thái ghế trước khi đặt:

~~~text
showtimeId = ST-01
seatId = A12
status = AVAILABLE
reservationId = null
generation = 7
~~~

Một request muốn giữ ghế cho `R1`:

~~~text
IF status == AVAILABLE AND generation == 7
THEN SET
    status = HELD
    reservationId = R1
    generation = 8
ELSE CONFLICT
~~~

Trong Cassandra, logic CAS có thể được hiện thực bằng LWT trên hàng. Trong HBase hoặc Bigtable, dùng conditional row mutation tương ứng. Cần bảo đảm trạng thái và generation được thay đổi trong một phạm vi nguyên tử đúng yêu cầu.

### Vấn đề ABA

Giả sử trạng thái đã đi qua:

~~~text
AVAILABLE, generation=7
    -> HELD by R1, generation=8
    -> AVAILABLE, generation=9
~~~

Một request cũ đọc `AVAILABLE` ở thế hệ 7 nhưng bị trễ, rồi tiếp tục khi ghế lại có trạng thái `AVAILABLE` ở thế hệ 9. Nếu chỉ kiểm tra chuỗi status, request không nhận ra ghế đã trải qua một vòng đời giữ chỗ khác.

**Generation/version** giúp phân biệt hai trạng thái có cùng giá trị tên nhưng khác lịch sử. Điều này quan trọng với tài nguyên có thể được giải phóng rồi cấp lại.

Hạn giữ còn làm phát sinh các quy tắc: ai được giải phóng, thanh toán đến sát hạn được xử lý thế nào, yêu cầu cũ có thể retry hay không, và trạng thái `HELD → SOLD` phải kiểm tra đúng `reservationId` nào.

## 13. Version không tự giải quyết nếu có đường ghi bỏ qua nó

Giả sử hàng có:

~~~text
status = PENDING
amount = 500000
version = 7
~~~

Client A kiểm tra `version = 7` và chuẩn bị thanh toán 500.000. Trong lúc đó, client B đổi `amount` thành 600.000 nhưng **không tăng version**. Khi A CAS theo version 7, nó có thể áp dụng quyết định trên số tiền cũ.

Vì vậy, hợp đồng version cần bao gồm:

- Mọi thao tác làm thay đổi field thuộc invariant đều phải tăng version.
- Version và dữ liệu được bảo vệ phải cập nhật nguyên tử cùng nhau.
- Không có writer nào dùng “ghi thẳng” để bypass kiểm tra ở những nơi cần CAS.
- Initial version phải được đặt thống nhất khi tạo hàng.
- Xóa rồi tạo lại cùng key phải có quy tắc generation đủ để nhận biết thực thể mới.
- Nếu một quyết định phụ thuộc nhiều field, version phải đại diện cho tất cả field liên quan.

CAS theo version chỉ hiệu quả bằng **mức độ mọi writer tuân thủ quy trình**.

## 14. Timeout không phải điều kiện không thỏa

Khi gửi conditional update, client có thể nhận ba loại kết quả:

| Kết quả | Điều có thể kết luận | Cách xử lý |
|---|---|---|
| Điều kiện được áp dụng | Thao tác thành công theo hợp đồng DB | Tiếp tục bước nghiệp vụ |
| Điều kiện sai, phản hồi xác định | Có cạnh tranh ghi hoặc trạng thái không phù hợp | Đọc lại, xử lý conflict hoặc thử có giới hạn |
| Timeout, mất kết nối, không nhận phản hồi | **Không chắc thao tác đã áp dụng hay chưa** | Tra trạng thái, operation ID hoặc ledger; tránh retry mù |

Nếu sau timeout client gửi lại cùng CAS theo version cũ và nhận `false`, điều đó không tự chứng minh thao tác trước của **chính client** đã thành công. Một writer khác có thể đã thay đổi version.

Để phân biệt, có thể lưu **operationId** cùng trạng thái và có cơ chế kiểm tra kết quả. Tuy nhiên, chỉ giữ `lastOperationId` có thể không đủ để nhận một request rất cũ được gửi lại sau nhiều thao tác khác; cần định nghĩa retention hoặc ledger idempotency.

### Retry phù hợp với từng loại thao tác

- Đọc dữ liệu: thường có thể retry với timeout/backoff và consistency phù hợp.
- CAS: retry có giới hạn sau khi đọc trạng thái mới và xác định nghiệp vụ còn hợp lệ.
- Increment: không retry vô điều kiện nếu yêu cầu đếm chính xác theo event.
- Gửi thanh toán: dùng idempotency key và tra cứu kết quả theo hợp đồng bên ngoài.
- Ghi event có ID: cần bảo đảm nhận diện cùng sự kiện để không xử lý lặp ngoài ý muốn.

**Exponential backoff và jitter** giúp giảm bão retry khi cluster bận, nhưng không tự làm một thao tác không idempotent trở nên idempotent.

## 15. Counter nóng và giới hạn mở rộng

Một hệ wide-column có thể lưu hàng tỷ hàng nhưng vẫn có một điểm nghẽn nếu phần lớn thao tác đổ vào một row/partition. Ví dụ:

~~~text
50.000 lượt xem/phút
       |
       v
INCREMENT article#popular:views
       |
       v
Một row / partition nhận rất nhiều thao tác
~~~

Một cách phân tán bộ đếm thống kê là chia thành bucket:

~~~text
article#popular#bucket-00
article#popular#bucket-01
...
article#popular#bucket-31
~~~

Một event chọn bucket theo chính sách, cập nhật vào đó; khi đọc tổng, ứng dụng cộng kết quả các bucket.

| Lợi ích | Đánh đổi |
|---|---|
| Giảm tập trung vào một khóa | Đọc nhiều bucket để lấy tổng |
| Có thể phân tán tải nếu hệ thống đặt key hợp lý | Tăng số key/index/công việc quản lý |
| Hữu ích cho thống kê có thể tổng hợp | Tổng có thể trễ hoặc cần materialized view |
| Cho phép mở rộng số bucket | Retry/dedup của từng event vẫn phải giải quyết |

Cần nhớ row key HBase và Bigtable có thứ tự sắp xếp; key tạo tuần tự hoặc cùng prefix có thể gây hotspot tại một số region/tablet. Với Cassandra, các partition key khác nhau có thể được phân bố qua token space, nhưng **một partition cực nóng** vẫn là vấn đề. Không nên suy rằng “thêm máy” tự phân chia một hàng duy nhất.

Không tùy tiện bucket tồn kho hoặc số dư cần invariant mạnh: nếu các bucket có thể trừ độc lập, hệ thống phải chứng minh rằng tổng nguồn lực không bị cấp vượt.

## 16. Vì sao bộ đếm không thích hợp làm sổ cái tiền?

Giả sử chuyển 100.000 đồng từ tài khoản A sang B:

~~~text
INCREMENT A.balance BY -100000
INCREMENT B.balance BY +100000
~~~

Ngay cả khi mỗi increment nguyên tử tại hàng tương ứng, lỗi có thể xảy ra **giữa hai bước**. Retry không có cơ chế chống lặp có thể trừ A hai lần hoặc cộng B hai lần.

Một nghiệp vụ tài chính thường cần:

- **Ledger/giao dịch có ID riêng** để truy vết và đối soát.
- Kiểm tra không chi vượt số dư và quyền thực hiện.
- Ghi nợ/ghi có theo mô hình transaction hoặc quy trình đủ mạnh.
- Retry và idempotency ở toàn bộ ranh giới.
- Trạng thái `PENDING / POSTED / FAILED` và chính sách đảo giao dịch.
- Cơ chế phục hồi và chứng minh số dư từ nguồn dữ liệu gốc.

Wide-column có thể phục vụ rất tốt lịch sử giao dịch hay báo cáo theo tài khoản, nhưng không nên biến một counter thuần thành cơ chế bảo toàn tiền nếu chưa thiết kế đầy đủ nghiệp vụ và bảo đảm lưu trữ.

## 17. Gợi ý quan sát hệ thống khi triển khai

| Chỉ số | Vì sao cần |
|---|---|
| Tỷ lệ conditional update `applied` | Xác định số thao tác thành công |
| Tỷ lệ condition failed | Phản ánh cạnh tranh hoặc trạng thái không còn phù hợp |
| P95/P99 latency LWT/CheckAndMutate | Theo dõi chi phí điều kiện và hot row |
| Timeout, retry, retry limit exceeded | Biết nguy cơ kết quả không rõ và bão retry |
| Counter updates/s theo key/partition | Nhận diện số đếm nóng |
| Event trùng và tỷ lệ dedup | Phân biệt một logical event với nhiều lần giao |
| Backlog/tuổi event | Biết xử lý tổng hợp có đang chậm |
| Số nghiệp vụ chờ đối soát | Theo dõi lỗi giữa các bước khác hàng/hệ |
| Mức tải node/partition/region | Phát hiện lệch dù trung bình cluster còn dư |

Không gộp mọi **condition failed** thành lỗi hạ tầng. Việc điều kiện không còn đúng có thể là một kết quả nghiệp vụ hợp lệ. Ngược lại, timeout là trạng thái chưa chắc chắn, cần xử lý khác với conflict.

## 18. Bài tập ứng dụng

### Bài tập A — Hai worker đổi trạng thái

Đơn `ORD-1` có `status=PENDING, version=3`. Worker A muốn `PAID`, worker B muốn `CANCELLED`.

**Câu hỏi:** Cần bảo vệ gì?

**Hướng suy luận:** một cập nhật có điều kiện phải kiểm tra trạng thái/version cũ và tăng version trong cùng thao tác; chỉ một chuyển trạng thái hợp lệ được áp dụng. Worker còn lại xử lý conflict thay vì ghi đè.

### Bài tập B — Tăng view hai lần sau timeout

Client gọi increment, response mất nhưng DB đã cộng. Client retry; counter tăng hai lần.

**Câu hỏi:** Có phải database mất atomicity?

**Hướng suy luận:** không. Hai phép increment riêng đều có thể nguyên tử. Vấn đề là **idempotency của một event logic** qua retry.

### Bài tập C — Bán khi tồn kho còn 1

Hai request cùng trừ 1 trên counter. Kết quả có thể thành `-1`.

**Câu hỏi:** Tại sao “increment nguyên tử” chưa đủ?

**Hướng suy luận:** thao tác không mang điều kiện “còn hàng”. Phải kiểm tra và ghi trong phạm vi có điều kiện/transaction phù hợp.

### Bài tập D — HBase hai hàng

Ghi `orders#O1` thành công, ghi `inventory#SKU1` thất bại.

**Câu hỏi:** Nguyên tử theo hàng có ngăn được trạng thái dở dang không?

**Hướng suy luận:** không. Cần workflow trạng thái, bù trừ hoặc reconciliation, hoặc thay mô hình sao cho bất biến được đặt đúng phạm vi.

### Bài tập E — Bigtable hai nguồn gửi trùng event

Hai consumer xử lý cùng `eventId` và đều gọi `ReadModifyWriteRow increment +1`.

**Câu hỏi:** Giá trị đếm có phản ánh số event duy nhất?

**Hướng suy luận:** chưa chắc. Cần dedup nguồn, event ledger hoặc cơ chế tổng hợp có khả năng tái dựng.

### Bài tập F — Hàng cập nhật quá nóng

Flash sale có 10.000 request/giây cùng CAS trên một mặt hàng. Nhiều request bị conflict và retry.

**Câu hỏi:** Thêm 10 node có chắc giúp không?

**Hướng suy luận:** không. Một key/partition vẫn có thể là nút thắt. Cần đo contention và cân nhắc điều phối theo khóa hoặc reservation, đồng thời giữ invariant không oversell.

## 19. Khung ra quyết định khi chọn kiểu cập nhật

Với một yêu cầu nghiệp vụ, có thể đi lần lượt:

1. **Định nghĩa invariant:** điều gì tuyệt đối không được sai? Hay đây chỉ là thống kê có thể điều chỉnh?
2. **Xác định nguồn sự thật:** hàng trạng thái, event log hay một ledger?
3. **Xác định phạm vi:** một cell, một hàng, một partition, nhiều hàng hay dịch vụ ngoài?
4. **Chọn cơ chế đúng engine:** Cassandra LWT/counter; HBase CheckAndMutate/Increment; Bigtable CheckAndMutateRow/ReadModifyWriteRow.
5. **Kiểm tra concurrent writers:** mọi đường ghi có dùng cùng điều kiện/version không?
6. **Thiết kế retry và timeout:** làm sao biết request đã áp dụng mà response bị mất?
7. **Tách atomicity và idempotency:** có cần một eventId hoặc operationId không?
8. **Đánh giá tải nóng:** CAS/row contention, bucket, giới hạn retry và backpressure.
9. **Thiết kế workflow nhiều hàng:** bước nào xác nhận, bù trừ và đối soát?
10. **Diễn tập lỗi:** hai writer đồng thời, mất response, retry, lỗi giữa hai hàng và phục hồi sau khởi động lại.

Một hợp đồng thiết kế minh họa:

~~~yaml
entity: InventoryItem
businessInvariant: "available >= 0"
storageScope: "one item row or partition"
writeStrategy: "conditional update with expected version"
onConditionFailed: "re-read or return conflict"
onTimeout: "resolve outcome before repeating effects"
counterUse: "analytics only; not enforceable available stock"
idempotency: "operation ID retained for the business retry window"
crossEntityFlow: "reservation state and reconciliation"
hotKeyPolicy: "bounded retry, contention metrics, backpressure"
~~~

Đoạn YAML chỉ là **mẫu ghi quyết định**, không phải cấu hình tự được Cassandra, HBase hay Bigtable thực thi.

Một cập nhật có điều kiện chỉ bảo vệ dữ liệu trong **phạm vi điều kiện và mutation được hệ quản trị cam kết thực thi nguyên tử**. Một phép increment giúp cộng số trong cạnh tranh nhưng không tự phát hiện request lặp. Cassandra, HBase và Bigtable đều cung cấp những công cụ hữu ích; thiết kế NoSQL có trách nhiệm là chọn công cụ phù hợp với bất biến, hiểu rõ ranh giới của nó và xây dựng quy trình phục hồi cho phần công việc nằm ngoài ranh giới ấy.
