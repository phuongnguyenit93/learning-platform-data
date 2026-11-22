# Transaction ID wraparound và tuổi giao dịch trong PostgreSQL

Một bảng PostgreSQL có thể chứa các hàng đã tồn tại nhiều năm, trong khi mỗi ngày hệ thống thực hiện hàng triệu transaction mới. **Làm thế nào PostgreSQL biết một phiên bản hàng rất cũ đã được commit từ lâu và phải luôn hiển thị cho transaction tương lai?** Câu hỏi này dẫn đến hai khái niệm nền tảng của MVCC: **Transaction ID (XID)** và **transaction ID wraparound**.

Trong PostgreSQL, các phiên bản hàng (*tuple versions*) mang thông tin transaction, và phần XID truyền thống dùng cho MVCC có kích thước **32 bit**. Bộ đếm 32 bit cuối cùng sẽ quay lại những giá trị cũ sau khoảng **4,29 tỷ** ID. Nếu cứ so sánh ID như số nguyên tăng mãi, một transaction đã commit trong quá khứ xa có thể bị nhầm là transaction **ở tương lai**, làm dữ liệu cũ không còn được nhìn thấy đúng.

Để tránh tai họa đó, PostgreSQL dùng **VACUUM**, đặc biệt là **freezing (đóng băng tuple)**, nhằm đánh dấu các phiên bản hàng đủ cũ là đã được xác nhận và luôn hiển thị cho các snapshot tương lai theo quy tắc MVCC. Hệ thống còn duy trì các mốc `relfrozenxid`, `datfrozenxid` và chạy **anti-wraparound autovacuum** trước khi mức tuổi trở nên nguy hiểm.

Bài học này đi sâu vào:

- XID 32 bit, `xid8` 64 bit, vòng quay và nguyên tắc “cũ/mới” theo modulo.
- `xmin`/`xmax` của tuple, XID được cấp khi nào và ý nghĩa của `age(xid)`.
- Freeze khác gì dọn dead tuple; vai trò của visibility map, `relfrozenxid` và `datfrozenxid`.
- Các ngưỡng `vacuum_freeze_min_age`, `vacuum_freeze_table_age`, `autovacuum_freeze_max_age` và `vacuum_failsafe_age`.
- Giám sát XID age ở cấp database, table, TOAST, transaction đang mở, replication slot và prepared transaction.
- Runbook khi xuất hiện cảnh báo wraparound hoặc hệ thống từ chối cấp XID mới.
- Phân biệt XID wraparound với **Multixact ID (MXID) wraparound**.
- Phòng ngừa và bài tập thực hành **không cố tạo wraparound thật**.

> **Phạm vi an toàn:** phần SQL đọc catalog/stats có thể phục vụ giám sát khi role có quyền thích hợp. Các lệnh `CREATE`, `UPDATE` và `VACUUM` minh họa phải thực hành trên database riêng hoặc môi trường được phép. Tuyệt đối không tạo hàng tỷ transaction để mô phỏng wraparound, không tự tắt autovacuum và không thử đưa production vào chế độ ngừng cấp XID.

## 1. Vì sao MVCC cần Transaction ID?

**MVCC (Multi-Version Concurrency Control)** cho phép nhiều transaction đọc và sửa dữ liệu đồng thời, trong đó một câu `UPDATE` thường tạo một phiên bản hàng mới thay vì ghi đè vật lý lên mọi thông tin của hàng cũ ngay lập tức.

Ví dụ bảng sản phẩm:

~~~text
Tuple version V1:
    sku = 'BOOK-01'
    price = 100
    xmin = XID 500
    xmax = XID 540  (bị thay thế khi transaction 540 cập nhật)

Tuple version V2:
    sku = 'BOOK-01'
    price = 120
    xmin = XID 540
    xmax = 0 hoặc chưa có transaction xóa/cập nhật phiên bản này
~~~

Một snapshot cũ có thể thấy V1 nhưng chưa thấy V2. Snapshot mới sau khi transaction 540 commit có thể thấy V2, trong khi V1 cuối cùng trở thành dead tuple và có thể được VACUUM thu gom khi không còn snapshot nào cần.

Trong mô hình đơn giản:

- **`xmin`:** XID của transaction tạo phiên bản tuple, thường do `INSERT` hoặc `UPDATE`.
- **`xmax`:** thông tin transaction liên quan đến việc xóa, thay thế hoặc khóa tuple. **Không được kết luận rằng mọi `xmax != 0` nghĩa là hàng đã bị xóa**: `xmax` có thể biểu diễn khóa hàng/Multixact và còn cần kiểm tra trạng thái transaction cùng các cờ nội bộ.
- **Snapshot:** xác định transaction nào đã commit và tuple version nào hiện có thể nhìn thấy.
- **`pg_xact`:** nơi PostgreSQL theo dõi trạng thái commit/abort của những transaction cần thiết; tên cũ thường thấy trong tài liệu lịch sử là CLOG.

~~~mermaid
flowchart LR
    A["INSERT phiên bản V1 (xmin=500)"] --> B["Transaction 540 UPDATE"]
    B --> C["V1 có xmax liên quan 540"]
    B --> D["V2 có xmin=540"]
    C --> E["Snapshot cũ có thể cần V1"]
    D --> F["Snapshot mới thấy V2 nếu 540 commit"]
    E --> G["VACUUM dọn V1 khi an toàn"]
    F --> H["V2 tồn tại lâu cần được freeze"]
~~~

Ví dụ minh họa XID 500/540 chỉ là số giả lập; chúng **không phải XID thực tế** mà PostgreSQL chắc chắn sẽ cấp trong bài lab.

### 1.1. Transaction ID không đồng nghĩa thời gian trên đồng hồ

XID được cấp theo một bộ đếm dùng chung trong **PostgreSQL cluster/instance**, chứ không phải:

- Số giây từ khi PostgreSQL khởi động;
- ID riêng cho mỗi database;
- Khóa chính của bảng;
- Mốc thời gian commit chính xác;
- Số tăng một ở mỗi câu `SELECT`.

Một transaction tồn tại 20 phút mà chỉ đọc dữ liệu có thể không cần XID thông thường. Trong khi đó, hàng triệu transaction ghi rất ngắn có thể đẩy bộ đếm XID đi rất nhanh.

### 1.2. XID được cấp lúc nào?

Trong PostgreSQL, mỗi transaction có **virtual transaction ID (vxid)** phục vụ quản lý hoạt động, nhưng không nhất thiết nhận ngay một **non-virtual XID** 32-bit. XID thông thường được cấp khi transaction lần đầu cần ghi/đánh dấu thay đổi trong database.

~~~text
Session A:
    BEGIN
    SELECT ...
    SELECT ...
    COMMIT

Có thể không cần cấp non-virtual XID cho transaction chỉ đọc.

Session B:
    BEGIN
    INSERT ...
       ↓
    nhận XID khi phát sinh ghi
    COMMIT
~~~

Vì vậy, thứ tự `BEGIN` không chắc trùng với **thứ tự cấp XID**. Hai transaction mở cùng lúc có thể lần lượt nhận XID theo thứ tự chúng bắt đầu ghi.

## 2. XID 32 bit và vấn đề quay vòng

Một số nguyên 32-bit có **2³² = 4.294.967.296** tổ hợp bit. PostgreSQL dành một vài giá trị đặc biệt (ví dụ `InvalidTransactionId=0`, `BootstrapTransactionId=1`, `FrozenTransactionId=2`), còn XID bình thường tiến qua không gian hữu hạn và cuối cùng quay vòng.

~~~text
... 4294967293, 4294967294, 4294967295
                           |
                           v
                quay lại vùng XID nhỏ
                sau các ID đặc biệt
~~~

**Đây là hành vi được thiết kế trước, không phải một lỗi phát sinh ngẫu nhiên.** PostgreSQL phải duy trì khả năng phân biệt transaction “quá khứ” và “tương lai” sau khi số XID thấp lặp lại.

### 2.1. Quy tắc cửa sổ khoảng 2³¹

Để so sánh thứ tự của XID 32-bit theo kiểu modulo, PostgreSQL dùng một cửa sổ có độ rộng khoảng **2³¹ = 2.147.483.648** transaction. Hãy hình dung các XID nằm trên **mặt đồng hồ**:

~~~text
Vòng tròn XID 32 bit (~4,29 tỷ vị trí)

                 XID tương lai
                      |
                      v
   ---- [vùng phía trước] ---- [CURRENT] ----
              ^                   |
              |                   v
         nửa vòng           nửa vòng quá khứ

Từ một điểm hiện tại, có thể xác định khoảng
~2,147 tỷ XID ở quá khứ và ~2,147 tỷ XID ở tương lai.
~~~

Nếu một tuple chưa freeze mang XID cũ đến mức nằm **quá xa phía sau**, phép so sánh vòng tròn có thể xem nó như **XID tương lai**. Khi đó tuple lẽ ra phải hiển thị có thể không còn được phân loại đúng.

**Không hiểu “sau đúng 4,29 tỷ transaction mới có nguy hiểm”.** Biên an toàn thực tế là khoảng **2,147 tỷ XID tuổi** tính từ XID chưa được freeze, chứ không phải đợi một vòng 32-bit hoàn chỉnh.

### 2.2. Ví dụ bằng mặt đồng hồ 12 giờ

Một phép ví von:

~~~text
Trên đồng hồ 12 giờ:
  Giờ hiện tại = 1
  Số 12 có thể được hiểu là 1 giờ trước
  hoặc 11 giờ sau.
~~~

Khi không gian số quay vòng, chỉ nhìn “12 nhỏ hơn 1” không đủ để quyết định số nào trước. Cần có **giới hạn khoảng cách thời gian/số bước**. PostgreSQL áp dụng nguyên tắc tương tự cho XID nhưng trên không gian 32 bit.

### 2.3. Wraparound không có nghĩa PostgreSQL bắt buộc mất dữ liệu

Một cluster PostgreSQL khỏe mạnh có thể hoạt động **qua nhiều lần quay vòng của XID 32 bit**. Cơ chế freeze làm cho các phiên bản hàng đủ cũ không còn phụ thuộc vào so sánh XID cũ trong vòng tròn.

Nguy hiểm xảy ra nếu **tuổi XID của dữ liệu chưa freeze vượt tầm an toàn** do VACUUM bị ngăn hoặc không hoàn tất. PostgreSQL có nhiều lớp phòng vệ, kể cả từ chối cấp XID mới khi nguy cơ đã quá gần.

## 3. xid, xid8 và epoch: vì sao có 64 bit vẫn cần freeze?

Tài liệu PostgreSQL hiện đại phân biệt:

| Khái niệm | Độ rộng / vai trò |
| --- | --- |
| `xid` | 32 bit, phục vụ các trường hệ thống/cơ chế MVCC truyền thống |
| `xid8` | 64 bit, gồm thông tin **epoch** và XID, hữu ích để quan sát/theo dõi định danh transaction qua vòng quay |
| **Epoch** | Phần tăng khi bộ đếm XID 32 bit quay vòng |
| **vxid** | Định danh transaction ảo trong backend, không giống XID toàn cluster |

~~~sql
SELECT
    pg_typeof(pg_current_xact_id_if_assigned())
        AS xid_function_type,
    pg_current_xact_id_if_assigned()
        AS my_xid_if_already_assigned;
~~~

`pg_current_xact_id_if_assigned()` trả `xid8` khi transaction hiện tại đã có XID, hoặc `NULL` nếu chưa. Nó không chủ động cấp XID mới chỉ để hiển thị.

Ngược lại:

~~~sql
SELECT pg_current_xact_id();
~~~

**có thể buộc cấp một XID mới** cho transaction chưa có XID. Khi viết dashboard giám sát, **không dùng hàm cấp XID trong vòng polling chỉ để “xem đồng hồ XID”**; ưu tiên hàm/metric không tạo XID mới khi phù hợp.

### 3.1. xid8 không thay cơ chế tuple freeze

`xid8` giúp ứng dụng/DBA biểu diễn ID mở rộng, tránh việc một chuỗi định danh 64 bit bị lặp do bộ đếm thấp quay vòng. Nhưng tuple header vẫn có những cấu trúc và quy tắc visibility dựa trên XID 32 bit. **Không thể kết luận PostgreSQL đã bỏ nguy cơ wraparound chỉ vì có hàm trả `xid8`.**

### 3.2. Hạn chế khi ép kiểu, so sánh và lưu XID

Không lấy giá trị `xmin::text` rồi so sánh hai chuỗi để xác định tuple nào “mới hơn” trong mọi thời điểm. Không chuyển XID thành `integer`, tính chênh lệch thông thường và kết luận đây là tuổi giao dịch. Hãy dùng hàm được thiết kế cho cơ chế modulo, tiêu biểu là **`age(xid)`**, và đối chiếu tài liệu đúng phiên bản.

Với audit nghiệp vụ, `created_at`/`updated_at` và một business version rõ ràng thường phù hợp hơn việc dùng `xmin` làm timestamp hay phiên bản dài hạn công khai.

## 4. age(xid): đo **số giao dịch**, không đo thời gian

PostgreSQL có hàm:

~~~sql
age(xid)  -- trả integer
~~~

Hàm này cho biết khoảng cách tính theo **số Transaction ID** giữa XID đang xét và bộ đếm hiện tại, có xử lý ngữ nghĩa XID theo modulo.

~~~sql
SELECT
    age(datfrozenxid) AS oldest_unfrozen_xid_age
FROM pg_catalog.pg_database
WHERE datname = current_database();
~~~

Nếu kết quả là `80,000,000`, nghĩa là mốc XID đang được theo dõi cách hiện tại khoảng **80 triệu lần cấp XID**, **không có nghĩa database đã chạy 80 triệu giây**.

### 4.1. Cùng số ngày nhưng tuổi khác nhau

Giả sử:

| Cluster | Giao dịch ghi/ngày (xấp xỉ) | Sau 10 ngày có thể tăng XID |
| --- | ---: | ---: |
| A — lab nhỏ | 2.000 | 20.000 |
| B — ứng dụng trung bình | 500.000 | 5.000.000 |
| C — nền tảng lớn | 20.000.000 | 200.000.000 |

Cùng 10 ngày trôi qua nhưng mức tăng XID khác nhau **10.000 lần** giữa A và C trong ví dụ. Rủi ro wraparound phụ thuộc vào **số XID đã trôi qua kể từ mốc chưa freeze**, không chỉ thời gian uptime.

### 4.2. Công thức ước lượng thời gian còn lại

Chỉ để lập kế hoạch, nếu mức tăng XID trung bình là `r` XID/ngày:

\[
\text{Số ngày ước lượng} \approx
\frac{\text{Ngưỡng mục tiêu XID} - \text{XID age hiện tại}}
{\text{Số XID tăng mỗi ngày}}
\]

Ví dụ: ngưỡng bảo trì nội bộ là 200 triệu XID, tuổi hiện tại 160 triệu và workload dùng khoảng 10 triệu XID/ngày:

~~~text
(200.000.000 - 160.000.000) / 10.000.000
= 4 ngày (ước lượng)
~~~

**Đây không phải cam kết hệ thống chỉ còn đúng bốn ngày.** Tốc độ transaction có thể tăng theo giờ, một số bảng bị kẹt vacuum, và ngưỡng anti-wraparound là ngưỡng **bảo trì tự động**, **không phải điểm mất dữ liệu**. Cần giám sát liên tục, đánh giá nguyên nhân và lên kế hoạch sớm hơn.

### 4.3. Tại sao không so age với độ dài uptime?

Một hệ thống chạy một năm nhưng rất ít ghi có thể có XID age nhỏ; một hệ thống chạy vài tuần nhưng nhập hàng triệu thay đổi mỗi ngày có thể tiến nhanh tới ngưỡng vacuum. Do đó:

- `uptime` không thay `age(datfrozenxid)`.
- `pg_stat_database.xact_commit` là counter thống kê hữu ích nhưng không đồng nghĩa tuyệt đối với XID counter.
- Một câu SQL hoặc một transaction có thể dùng nhiều subtransaction; tốc độ cấp XID có thể khác số request.
- Không dùng số hàng thay đổi làm đơn vị đo trực tiếp cho XID age.

## 5. Freezing: bảo vệ phiên bản hàng rất cũ

Một phiên bản tuple đã được commit từ lâu, không còn cần trạng thái commit của XID tạo ra nó để xác định khả năng nhìn thấy trong snapshot tương lai, có thể được **frozen**.

Ý tưởng:

~~~text
Trước freezing:
    Tuple T có xmin = 500, phải xét XID/commit status.

Sau freezing:
    Tuple T mang trạng thái "frozen" trong metadata nội bộ.
    MVCC biết T đủ cũ và được coi như luôn hợp lệ
    cho các snapshot tương lai phù hợp.

XID counter tiếp tục tăng/quay vòng mà không làm
T bị nhầm thành "do transaction tương lai tạo ra".
~~~

### 5.1. Freezing không phải là DELETE

**VACUUM làm hai việc dễ bị nhầm:**

1. **Pruning/garbage collection:** dọn phiên bản hàng đã chết mà không snapshot nào còn cần, cho phép tái sử dụng không gian lưu trữ.
2. **Freezing:** làm cho các phiên bản hàng **vẫn sống nhưng đã rất cũ** được đánh dấu an toàn trước XID wraparound.

Một bảng **chỉ INSERT rồi không UPDATE/DELETE** có thể gần như không có dead tuples nhưng **vẫn cần freezing**. Đây là lý do “bảng tĩnh không có dead tuple” **không phải** lý do tắt autovacuum vĩnh viễn.

### 5.2. FrozenTransactionId và cờ frozen

Trong các phiên bản PostgreSQL rất cũ (trước 9.4), freezing thường được hiểu là thay `xmin` bằng `FrozenTransactionId=2`. PostgreSQL hiện đại chủ yếu dùng **cờ trạng thái trong tuple**, và có thể **giữ nguyên giá trị `xmin` được hiển thị**.

Do đó:

~~~sql
SELECT xmin, *
FROM some_table;
~~~

không phải cách đáng tin để kết luận một tuple đã freeze hay chưa chỉ vì `xmin` có hoặc không bằng 2. Dùng các mốc hệ thống và quan sát VACUUM thay vì suy đoán trực tiếp từ `xmin`.

### 5.3. Frozen không làm “tất cả tuple luôn hiển thị cho mọi snapshot lịch sử”

Phát biểu đúng là PostgreSQL chỉ freeze khi có thể bảo đảm an toàn theo các snapshot/tuổi transaction còn cần thiết. Không hiểu việc freeze như một thao tác làm dữ liệu từ một transaction tương lai bỗng hiện trong **snapshot cũ vẫn đang hoạt động**.

### 5.4. Freezing không thay đổi dữ liệu nghiệp vụ

Một lần `VACUUM` để freeze không làm `product.price` tăng, không viết thêm đơn hàng và không “commit hộ” transaction chưa hoàn tất. Freezing chủ yếu cập nhật metadata/lưu trữ vật lý để các phiên bản đã xác nhận được nhận diện an toàn lâu dài.

## 6. Visibility map: all-visible và all-frozen

PostgreSQL lưu **visibility map** để theo dõi trạng thái ở mức trang (*heap page*). Hai khái niệm quan trọng:

- **All-visible:** các tuple trên trang đủ điều kiện hiển thị với những transaction đang quan tâm, giúp một số tối ưu như index-only scan.
- **All-frozen:** các tuple trên trang đã có trạng thái freezing an toàn; những VACUUM aggressive về sau có thể **bỏ qua** trang đã all-frozen.

~~~text
Heap page P
    |
    +-- chưa all-visible: còn những điều kiện MVCC cần xét
    |
    +-- all-visible: nhìn thấy an toàn theo snapshot hiện hành
    |
    +-- all-frozen: phiên bản XID trên page đã đủ an toàn
                       trước wraparound, nhiều lần vacuum
                       tiếp theo có thể bỏ qua page
~~~

Không đánh đồng **all-visible = all-frozen**: một trang có thể nhìn thấy cho mọi transaction hiện tại nhưng vẫn chứa các XID chưa đủ tuổi freeze. Freeze là yêu cầu riêng để vượt qua thời gian rất dài.

### 6.1. Tác động lên VACUUM aggressive

Một lần VACUUM thường có thể bỏ qua nhiều trang dựa vào visibility map. Khi cần advance mốc XID lâu đời, **aggressive VACUUM** phải thăm mọi trang có thể còn tuple chưa freeze, nhưng vẫn có thể bỏ qua trang đã **all-frozen**.

Điều này lý giải vì sao hai bảng cùng kích thước có thể có chi phí anti-wraparound vacuum rất khác nhau: tỷ lệ trang all-frozen, mức thay đổi dữ liệu và tình trạng index/TOAST đều quan trọng.

### 6.2. Mở rộng pg_visibility chỉ là công cụ chuyên sâu

Extension `pg_visibility` có thể giúp quan sát visibility map trong môi trường DBA/lab, nếu extension đã được cài và role có quyền phù hợp. Không cần extension để hiểu bài hoặc giám sát định kỳ; **`pg_class`, `pg_database` và thống kê VACUUM** là điểm khởi đầu an toàn, ổn định hơn.

## 7. relfrozenxid: tuổi XID theo từng relation

Trong catalog `pg_class`, cột **`relfrozenxid`** đại diện cho mốc XID sớm nhất còn có thể tồn tại **chưa freeze** trong relation sau các lần VACUUM đủ điều kiện.

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
ORDER BY xid_age DESC
LIMIT 20;
~~~

Kết quả cho biết các bảng thường (`relkind='r'`) và materialized view (`relkind='m'`) có mốc XID tuổi cao nhất **trong database đang kết nối**.

**Lưu ý:** đây là **mốc an toàn/lower bound**, không phải phép quét xác định “tuple cụ thể già nhất trong mọi hàng”. `age(relfrozenxid)` có thể cao trong một bảng dù những hàng người dùng quan tâm đã được sửa gần đây.

### 7.1. Vì sao relfrozenxid có thể không thay đổi sau VACUUM thường?

Một VACUUM không nhất thiết quét mọi trang có thể có XID chưa freeze. Mốc `relfrozenxid` chỉ được đẩy tiến khi VACUUM thực hiện đủ việc cần để chứng minh không còn XID chưa freeze cũ hơn mốc mới.

~~~text
VACUUM thông thường:
    có thể dọn dead tuples và cập nhật visibility map
    nhưng chưa quét đủ trang để tăng relfrozenxid.

VACUUM aggressive / freeze phù hợp:
    quét những trang có thể còn XID chưa frozen
    và có thể đẩy relfrozenxid tiến đáng kể.
~~~

**Không kết luận VACUUM bị lỗi chỉ vì `age(relfrozenxid)` chưa giảm ngay sau một VACUUM thường.** Cần đọc log/VERBOSE, xét kiểu vacuum, các snapshot giữ chân horizon và tình trạng bảng.

### 7.2. TOAST là một relation riêng

Một bảng có cột lớn như `text`/`jsonb` có thể có **TOAST table** để lưu các giá trị ngoài dòng. TOAST mang `relfrozenxid` riêng và có thể là nguyên nhân giữ lại mốc cũ.

Mẫu theo dõi cả bảng và TOAST liên quan:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    age(c.relfrozenxid) AS heap_xid_age,
    t.oid::regclass AS toast_table,
    age(t.relfrozenxid) AS toast_xid_age,
    GREATEST(
        age(c.relfrozenxid),
        age(t.relfrozenxid)
    ) AS oldest_relevant_age
FROM pg_catalog.pg_class AS c
LEFT JOIN pg_catalog.pg_class AS t
    ON t.oid = c.reltoastrelid
WHERE c.relkind IN ('r', 'm')
ORDER BY oldest_relevant_age DESC
LIMIT 30;
~~~

Trong PostgreSQL, `GREATEST` bỏ qua đối số NULL khi còn đối số không NULL, nên bảng không có TOAST vẫn có `oldest_relevant_age` từ heap.

**Đừng quên các database và relation hệ thống**. Một bảng application trông khỏe không chứng minh cả cluster đã an toàn, nhất là khi database khác chưa được vacuum.

## 8. datfrozenxid: mốc rủi ro ở cấp database

`pg_database.datfrozenxid` đại diện cho mốc XID cũ nhất có thể còn chưa frozen trong database, xét từ các relation liên quan. Đây là metric rất quan trọng để giám sát nguy cơ wraparound **trên toàn cluster**.

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

Câu lệnh có thể chạy từ **một database** và liệt kê các database khác trong cluster, trong phạm vi quyền truy cập phù hợp.

### 8.1. Vì sao cần xem tất cả database?

XID được cấp từ bộ đếm **chung cho toàn cluster**. Một database `archive_db` không nhận request nào trong sáu tháng vẫn có thể thấy `age(datfrozenxid)` tăng mạnh khi **database khác** dùng nhiều XID.

~~~text
Cluster XID counter chung
       |
       +--- database app_prod (ghi 10 triệu XID/ngày)
       |
       +--- database reports (ít thay đổi)
       |
       +--- database archive (không có ghi)

XID mới trong app_prod vẫn làm tuổi của mốc
datfrozenxid ở reports và archive tăng lên.
~~~

Đây là lý do **database ít sử dụng vẫn cần autovacuum anti-wraparound** và không thể bị bỏ quên trong runbook.

### 8.2. Tỷ lệ tương đối tới biên 2³¹

Có thể tạo một chỉ số giám sát tham khảo:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    ROUND(
        100.0 * age(datfrozenxid)
        / 2147483648.0,
        2
    ) AS pct_of_half_range,
    2147483648::bigint
        - age(datfrozenxid)::bigint
        AS approximate_xids_to_half_range
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

Ở đây `2³¹` là **mốc tham chiếu toán học**. Không coi kết quả là đồng hồ đếm ngược chính xác tới một ngày sự cố; PostgreSQL có nhiều ngưỡng bảo vệ và còn phụ thuộc trạng thái vacuum. Khi metric đã tiến xa đến vùng đỏ, cần xử lý như sự cố vận hành trước khi chạm giới hạn.

### 8.3. datfrozenxid không phải timestamp của lần vacuum gần nhất

`datfrozenxid` là **XID horizon**, không phải thời gian. Muốn biết thời điểm vacuum trên từng bảng, xem `pg_stat_all_tables.last_vacuum`, `last_autovacuum`; nhưng **thời gian vacuum gần đây không tự chứng minh freeze horizon đã tiến**.

### 8.4. So sánh hai cấp

| Thuộc tính | `relfrozenxid` | `datfrozenxid` |
| --- | --- | --- |
| Nơi lưu | `pg_class` | `pg_database` |
| Phạm vi | Relation trong database hiện tại | Database |
| Dùng để | Tìm bảng/TOAST có XID tuổi cao | Giám sát nguy cơ trên các database |
| Đơn vị qua `age` | Số XID | Số XID |
| Cách tiến lên | VACUUM đủ điều kiện trên relation | Khi mốc của các relation liên quan cùng tiến |
| Có phải giờ/phút? | Không | Không |

**Không thể sửa `datfrozenxid` đúng cách bằng một `UPDATE pg_database SET ...` tự chế.** Đây là metadata do PostgreSQL duy trì. Phải giải quyết các bảng/transaction/slot thực sự đang ngăn VACUUM hoàn tất.

## 9. VACUUM thường, aggressive VACUUM và VACUUM FREEZE

### 9.1. VACUUM thường

~~~sql
VACUUM some_table;
~~~

VACUUM thường có thể:

- Thu hồi không gian từ dead tuple để tái sử dụng;
- Làm sạch các dead index tuples;
- Cập nhật visibility map và thống kê maintenance;
- Freeze những tuple phù hợp ở các trang đã xử lý;
- Có thể, nhưng **không phải lúc nào**, tăng `relfrozenxid`.

VACUUM thường có thể chạy đồng thời với hoạt động đọc/ghi trên bảng với những giới hạn khóa phù hợp. Nó khác `VACUUM FULL`, vốn viết lại relation và thường yêu cầu khóa mạnh.

### 9.2. Aggressive VACUUM

Khi `relfrozenxid` quá cũ so với cấu hình ngưỡng, PostgreSQL cần kiểm tra toàn bộ các trang **có khả năng còn XID chưa freeze** (bỏ qua trang all-frozen). Đây là ý nghĩa của **aggressive vacuum**, một chiến lược quét sâu hơn nhằm advance XID horizon.

### 9.3. VACUUM (FREEZE)

~~~sql
-- Chỉ chạy trên bảng của database lab được cấp quyền.
VACUUM (FREEZE, VERBOSE) demo_table;
~~~

Tùy chọn `FREEZE` khiến VACUUM thực hiện freezing rất tích cực, tương đương việc dùng các ngưỡng freeze ở mức 0 trong phạm vi hành vi tương ứng. Nó có thể có ích trong quy trình chuẩn bị dữ liệu tĩnh hoặc demo, nhưng **không phải nút “chữa mọi vấn đề MVCC”**.

**Lưu ý khẩn cấp:** nếu cluster đã quá gần điểm **từ chối cấp XID**, tài liệu PostgreSQL hiện đại khuyến nghị ưu tiên **VACUUM thường** sau khi gỡ blocker, không dùng `VACUUM FULL` hay tự động chọn `VACUUM FREEZE` làm bước cứu đầu tiên. `FREEZE` có thể làm thêm việc không cần thiết so với mục tiêu khôi phục khả năng cấp XID càng nhanh càng tốt.

### 9.4. VACUUM FULL khác mục tiêu và rủi ro

`VACUUM FULL`:

- Viết lại toàn bộ bảng để thu gọn file vật lý;
- Có thể cần không gian trống bổ sung và khóa `ACCESS EXCLUSIVE`;
- Có hành vi cấp XID/chi phí riêng khi rewrite;
- **Không phải phương pháp mặc định để phòng chống/cứu wraparound**.

Nói ngắn gọn: **rủi ro wraparound cần xử lý freeze horizon bằng VACUUM phù hợp**, không phải “chạy FULL để dữ liệu sạch hơn”.

## 10. Các tham số quản lý tuổi XID

Các tham số tiêu biểu của PostgreSQL hiện đại:

| Tham số | Giá trị mặc định thường gặp ở PostgreSQL 18 | Vai trò |
| --- | ---: | --- |
| `vacuum_freeze_min_age` | 50.000.000 | Tuổi tham khảo để cân nhắc freeze những XID gặp khi vacuum |
| `vacuum_freeze_table_age` | 150.000.000 | Tuổi khiến một VACUUM dùng chiến lược aggressive trên relation |
| `autovacuum_freeze_max_age` | 200.000.000 | Tuổi `relfrozenxid` khiến anti-wraparound vacuum được ép chạy |
| `vacuum_failsafe_age` | 1.600.000.000 | Mức nguy cấp để VACUUM ưu tiên chống wraparound |

**Đây là giá trị mặc định tham khảo, không phải cấu hình chắc chắn của server bạn.** Chúng có thể khác theo phiên bản hoặc administrator. Kiểm tra thực tế:

~~~sql
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
SHOW vacuum_failsafe_age;
~~~

### 10.1. vacuum_freeze_min_age

Nếu freeze tuple ngay khi còn rất mới, một lần `UPDATE` sau đó sẽ tạo tuple version mới và nhiều công sức freeze trước đó trở nên ít có lợi. `vacuum_freeze_min_age` giúp cân bằng việc **không freeze quá sớm** với việc phải bảo vệ tuple trước khi XID cũ.

Giảm giá trị này quá thấp trên mọi bảng không đương nhiên tăng hiệu suất. PostgreSQL có giới hạn hiệu dụng của tham số so với `autovacuum_freeze_max_age` để đảm bảo khoảng an toàn.

### 10.2. vacuum_freeze_table_age

Đây là ngưỡng để **VACUUM sử dụng chiến lược aggressive**, không phải ngưỡng PostgreSQL ngừng ghi. Nếu ứng dụng chạy nhiều transaction trong khi bảng chưa được quét đủ sâu, `relfrozenxid` có thể tiếp tục già đi.

Giá trị hiệu dụng được giới hạn tương đối với `autovacuum_freeze_max_age`, thường không quá khoảng **95%** ngưỡng autovacuum freeze max age. Nhờ vậy còn khoảng thời gian cho bảo trì trước khi hệ thống phải ép anti-wraparound vacuum.

### 10.3. autovacuum_freeze_max_age

Khi tuổi `relfrozenxid` chạm ngưỡng, PostgreSQL sẽ tổ chức **anti-wraparound autovacuum**, kể cả khi bảng không có nhiều dead tuples. Ngưỡng mặc định **200 triệu XID** nằm xa giới hạn khoảng 2,147 tỷ để tạo biên an toàn và tránh giữ lịch sử commit trong `pg_xact` quá lâu.

Điểm đặc biệt quan trọng:

> Cơ chế anti-wraparound vẫn được khởi động trong những trường hợp cần thiết **kể cả khi autovacuum thông thường bị tắt**.

Điều này **không phải** lý do để cấu hình `autovacuum=off`. Tắt bảo trì thường làm dead tuples, index bloat và freeze work tích lũy; đến khi anti-wraparound bị buộc chạy, chi phí I/O và thời gian có thể tăng mạnh.

### 10.4. vacuum_failsafe_age

Đây là lớp phòng vệ rất muộn. Khi nguy cơ đã cao, VACUUM có thể:

- Bỏ qua delay giới hạn chi phí thông thường;
- Bỏ qua một số bước bảo trì không thiết yếu như index vacuuming;
- Ưu tiên làm tiến mốc XID/MXID để tránh hệ thống dừng cấp ID.

**Failsafe không phải vùng vận hành bình thường.** Nếu thấy relation tới gần `vacuum_failsafe_age`, phải coi là tình trạng nghiêm trọng cần DBA xử lý, thay vì tiếp tục chờ failsafe cứu hộ.

### 10.5. Không chỉnh ngưỡng như cách chữa sự cố

Tăng `autovacuum_freeze_max_age` có thể trì hoãn anti-wraparound nhưng kéo dài thời gian giữ lịch sử trong `pg_xact`/`pg_commit_ts`, tăng khoảng cách đến công việc freeze và giảm dư địa vận hành nếu có blocker. Nó không giải quyết một prepared transaction bị bỏ quên hay một replication slot giữ snapshot cũ.

Thay đổi tham số cần hiểu workload, dung lượng lưu trữ, phiên bản server, cơ chế restart/reload, per-table storage parameters và quy trình kiểm chứng. **Không thay cấu hình production chỉ để làm cảnh báo “đẹp đi”.**

## 11. Normal autovacuum và anti-wraparound autovacuum

Autovacuum phục vụ cả **dọn dead tuples**, **ANALYZE**, **freezing** và **phòng chống wraparound**.

### 11.1. Hai loại kích hoạt cần phân biệt

**Kích hoạt do số tuple thay đổi:**

~~~text
Số hàng dead / số lần INSERT đạt ngưỡng
        |
        v
Autovacuum xử lý bảng để thu hồi chỗ và thống kê
~~~

**Kích hoạt do tuổi XID/MXID:**

~~~text
age(relfrozenxid) tiến đến autovacuum_freeze_max_age
        |
        v
Anti-wraparound autovacuum được ép chạy
        |
        v
Aggressive scan + freezing để đưa horizon tiến lên
~~~

Một bảng rất ít UPDATE/DELETE có thể không kích hoạt vacuum theo dead tuple, nhưng vẫn **phải** được freeze theo chu kỳ XID.

### 11.2. Ngưỡng dead tuples không phải ngưỡng XID

Những tham số như `autovacuum_vacuum_threshold`, `autovacuum_vacuum_scale_factor` giúp quyết định khi nào vacuum vì lượng thay đổi dữ liệu. Chúng **khác** với `autovacuum_freeze_max_age`.

Ví dụ bảng có 100 triệu hàng không đổi trong một năm nhưng cluster khác trong cùng instance tạo hàng tỷ XID. Bảng tĩnh vẫn cần aggressive vacuum để tránh tuple cũ bị nhầm là “tương lai”, dù hầu như không có dead tuples để dọn.

### 11.3. Anti-wraparound autovacuum không dễ bị hủy tùy tiện

Autovacuum thông thường có thể bị ngắt trong một số tình huống khi có yêu cầu lấy khóa xung đột. Nhưng anti-wraparound autovacuum có tính bảo vệ hệ thống cao hơn và **không tự nhường/hủy chỉ vì yêu cầu khóa thông thường** theo cách của nhiều autovacuum khác.

Trong `pg_stat_activity.query`, quá trình có thể xuất hiện nhãn như:

~~~text
autovacuum: VACUUM ... (to prevent wraparound)
~~~

**Đừng tự `pg_cancel_backend` hay `pg_terminate_backend` worker anti-wraparound** để “giải tỏa khóa” khi chưa có kế hoạch DBA. Việc lặp lại hành động này có thể đẩy cluster gần hơn tới điểm từ chối cấp XID.

### 11.4. Vì sao anti-wraparound vacuum có thể tốn nhiều I/O?

Nó cần bảo đảm không còn XID quá cũ trong các trang chưa all-frozen. Bảng lớn ít được vacuum có thể phải quét rất nhiều trang; khi tới failsafe, PostgreSQL còn ưu tiên an toàn hơn cost delay thông thường. Vì thế phòng ngừa sớm giúp tránh maintenance burst ở những thời điểm xấu.

## 12. Khoảng an toàn, cảnh báo và cơ chế từ chối cấp XID

Các ngưỡng thuộc **nhiều lớp khác nhau**:

~~~text
XID age tăng dần →

    < 200 triệu               ~1,6 tỷ              ~2,147 tỷ
        |                        |                       |
        v                        v                       v
  anti-wraparound         vacuum failsafe        biên 2^31
  autovacuum thường       nguy cấp                wraparound
  được ép chạy
                         [cảnh báo cực cao và vùng
                          từ chối cấp XID mới gần cuối]
~~~

Đường thời gian chỉ mang tính minh họa: mặc định cụ thể có thể thay đổi, và việc PostgreSQL bắt đầu cảnh báo hay ngăn cấp XID còn phụ thuộc phiên bản.

### 12.1. Cảnh báo ở gần biên wraparound

Theo tài liệu PostgreSQL 18, khi database còn khoảng **40 triệu transaction** trước điểm wraparound nguy hiểm, hệ thống có thể cảnh báo dạng:

~~~text
WARNING: database "exampledb" must be vacuumed within
         ... transactions
HINT: To avoid XID assignment failures, execute a
      database-wide VACUUM in that database.
~~~

Đây là **cảnh báo vận hành rất nghiêm trọng**, không phải mức giới hạn bình thường của autovacuum.

### 12.2. Nếu vẫn không xử lý

Gần hơn nữa, khi chỉ còn khoảng **3 triệu transaction** tới biên bảo vệ theo tài liệu PostgreSQL 18, server có thể từ chối những thao tác **cần cấp XID mới**:

~~~text
ERROR: database is not accepting commands that assign
       new transaction IDs to avoid wraparound data loss
       in database "exampledb"
HINT: Execute a database-wide VACUUM in that database.
~~~

Việc PostgreSQL từ chối cấp XID nhằm **tránh nguy cơ mất khả năng nhìn thấy dữ liệu**, không phải vì “hết dung lượng đĩa” hay “khóa chính integer đã đầy”.

Các transaction đã hoạt động có thể tiếp tục trong phạm vi cho phép; những thao tác bắt đầu mới chỉ đọc và các lệnh VACUUM phù hợp vẫn có thể thực hiện. **Không kết luận máy chủ hoàn toàn không thể cứu chỉ vì ghi đang bị từ chối.**

### 12.3. Ngưỡng cảnh báo phụ thuộc major version

Con số **40 triệu** và **3 triệu** được trình bày theo tài liệu PostgreSQL hiện đại đang tham chiếu. Khi vận hành cluster phiên bản cụ thể, đối chiếu tài liệu của **đúng major version** và log thực tế; không tạo runbook chỉ dựa vào một con số hard-code của phiên bản khác.

### 12.4. XID age vượt 200 triệu không có nghĩa dữ liệu đã hỏng

`autovacuum_freeze_max_age=200000000` là **ngưỡng yêu cầu bảo trì**. Nếu một bảng có age hơi vượt ngưỡng, có thể đang có anti-wraparound vacuum chạy hoặc đang chờ tài nguyên. Cần điều tra, nhưng **không diễn giải đó là wraparound đã xảy ra**.

Ngược lại, chờ đến gần 2 tỷ rồi mới hành động là quá trễ trong nhiều hệ thống. Cần thiết lập cảnh báo từ sớm, dựa trên **mức tăng XID**, cấu hình và thời gian vacuum có thể kéo dài.

## 13. Bộ truy vấn giám sát an toàn: bắt đầu từ database

Phần này là **runbook truy vấn chỉ đọc**, dành cho người có quyền giám sát PostgreSQL. Không có lệnh nào tự sửa thông tin `pg_database` hoặc `pg_class`. Một số kết quả hiển thị hạn chế nếu role không được phép xem chi tiết session khác.

### 13.1. Xếp hạng XID age của tất cả database

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    ROUND(
        age(datfrozenxid)::numeric
        / 2147483648::numeric * 100,
        2
    ) AS pct_of_half_range
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
~~~

**Cách diễn giải:**

- Hàng đầu có `xid_age` lớn nhất là database cần ưu tiên xem xét.
- `pct_of_half_range` chỉ là phép tham chiếu tiến gần 2³¹, **không phải phần trăm dung lượng đĩa**.
- Các database tĩnh/ít truy cập vẫn có thể nằm đầu danh sách vì dùng bộ đếm XID chung.
- Một lần đọc không đủ để biết xu hướng; nên thu thập mẫu theo thời gian.

### 13.2. So với ngưỡng autovacuum hiện tại

~~~sql
SELECT
    d.datname,
    age(d.datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS configured_autovacuum_freeze_max_age,
    ROUND(
        100.0 * age(d.datfrozenxid)
        / NULLIF(
            current_setting('autovacuum_freeze_max_age')::numeric,
            0
        ),
        1
    ) AS pct_of_configured_age
FROM pg_catalog.pg_database AS d
ORDER BY xid_age DESC;
~~~

Nếu `pct_of_configured_age` vượt 100%, **đừng coi như 100% khả năng mất dữ liệu**. Nó chỉ nói tuổi database cao hơn giá trị tham số ngưỡng anti-wraparound mặc định/đang cấu hình ở server. Cần xem bảng cụ thể, mốc cấu hình theo bảng, VACUUM đang chạy và blocker.

### 13.3. Ước lượng mức tiêu thụ XID

Muốn ước lượng tốc độ tăng XID, nên **ghi snapshot của chỉ số từ hệ thống giám sát** theo thời gian, ví dụ:

~~~text
2026-11-14 09:00:00   xid_age=120,000,000
2026-11-15 09:00:00   xid_age=128,000,000

Tăng khoảng 8 triệu XID trong 24 giờ.
~~~

**Cẩn thận:** `age(datfrozenxid)` có thể **giảm mạnh khi vacuum đẩy datfrozenxid tiến**; vì vậy hiệu giữa hai điểm đo không luôn bằng tốc độ cấp XID. Muốn đo tốc độ bộ đếm toàn cluster, dùng nguồn metric XID thích hợp do hệ giám sát cung cấp và hiểu sự khác biệt giữa `xid` 32 bit với `xid8`.

Ví dụ trên chỉ là một khoảng có giả định **datfrozenxid chưa đổi**, không phải công thức phổ quát suy ra TPS.

## 14. Truy vấn bảng có XID age lớn nhất trong database hiện tại

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.oid::regclass AS relation_oid,
    age(c.relfrozenxid) AS xid_age,
    c.reltuples::bigint AS estimated_rows,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_total_relation_size(c.oid)
    ) AS total_relation_size
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Ở đây:

- `relkind='r'`: bảng thường.
- `relkind='m'`: materialized view.
- `relkind='t'`: TOAST table.
- `reltuples`: **ước lượng** số hàng, không phải `COUNT(*)` chính xác.
- `pg_total_relation_size`: giúp nhìn chi phí maintenance có thể lớn trên bảng/toast có kích thước cao.

Kết quả chỉ bao gồm **database đang kết nối**. `pg_class` không được dùng như một bảng catalog chứa `relfrozenxid` của mọi database trong cluster.

### 14.1. Chỉ xem bảng ứng dụng, bỏ catalog hệ thống

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname NOT IN (
      'pg_catalog',
      'information_schema',
      'pg_toast'
  )
ORDER BY xid_age DESC
LIMIT 20;
~~~

Đây chỉ là truy vấn **điều tra ứng dụng**, không phải bức tranh rủi ro hoàn chỉnh. **System catalogs và TOAST cũng cần freeze**; loại chúng khỏi báo cáo cuối cùng có thể che mất relation đang giữ XID cũ.

### 14.2. Báo cáo kết hợp bảng thường và TOAST

~~~sql
SELECT
    c.oid::regclass AS table_name,
    age(c.relfrozenxid) AS table_xid_age,
    t.oid::regclass AS toast_name,
    age(t.relfrozenxid) AS toast_xid_age,
    GREATEST(
        age(c.relfrozenxid),
        age(t.relfrozenxid)
    ) AS max_table_or_toast_age
FROM pg_catalog.pg_class AS c
LEFT JOIN pg_catalog.pg_class AS t
    ON t.oid = c.reltoastrelid
WHERE c.relkind IN ('r', 'm')
ORDER BY max_table_or_toast_age DESC
LIMIT 30;
~~~

Đây là cách thực tế để không bỏ qua TOAST trong phân tích tuổi.

### 14.3. Partitioned table: đừng chỉ xem bảng cha

Bảng partitioned parent (`relkind='p'`) thường không chứa trực tiếp các tuple dữ liệu như một heap table thông thường. Mỗi partition là một relation riêng và có thể có `relfrozenxid` riêng.

~~~sql
SELECT
    inhparent::regclass AS parent_table,
    inhrelid::regclass AS partition_table
FROM pg_catalog.pg_inherits
ORDER BY inhparent::regclass::text,
         inhrelid::regclass::text;
~~~

Nếu một bảng logic có 365 partition theo ngày, không đánh giá rủi ro chỉ từ tên bảng cha. Cần liệt kê **các partition vật lý**, đặc biệt những partition lịch sử ít được cập nhật và dễ bị bỏ quên trong quy trình bảo trì.

### 14.4. Bảng temporary và khác biệt autovacuum

**Autovacuum không thể truy cập bảng tạm của session khác.** Vì vậy các bảng temporary cần được xử lý thống kê/vacuum từ chính session khi phù hợp. Tuy nhiên, điều này không có nghĩa mọi bảng tạm giữ mốc XID nguy hiểm sau khi session đóng; lifecycle và yêu cầu vacuum của chúng khác bảng thường.

## 15. Giám sát lần VACUUM gần nhất và số tuple chết

View `pg_stat_all_tables` cung cấp số liệu bảo trì theo relation:

~~~sql
SELECT
    relid::regclass AS table_name,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_all_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

### 15.1. Không chỉ nhìn last_autovacuum

`last_autovacuum IS NOT NULL` chứng minh có autovacuum được ghi nhận, nhưng chưa chứng minh `relfrozenxid` đã đủ tiến tới mức an toàn. Nó có thể là VACUUM thường chưa cần aggressive scan. Ngược lại, một bảng có `last_autovacuum` cũ nhưng `relfrozenxid` rất mới có thể chưa cần freeze thêm.

**Dùng kết hợp:** tuổi XID + mốc VACUUM + tiến độ VACUUM + các blocker.

### 15.2. n_dead_tup không bằng XID age

`n_dead_tup` là ước lượng dead tuple. XID age đo **tuổi mốc unfrozen**, hoàn toàn khác. Bảng có `n_dead_tup=0` vẫn có thể cần anti-wraparound vacuum.

### 15.3. VACUUM thường không trả ngay dung lượng về filesystem

VACUUM thường chủ yếu làm không gian trong bảng **tái sử dụng được**. Nếu file bảng không nhỏ đi sau VACUUM, đó không phải bằng chứng freeze thất bại. `VACUUM FULL` có mục đích thu gọn file khác và có chi phí/khóa mạnh hơn.

## 16. Theo dõi VACUUM đang chạy

Trong khi hệ thống xử lý bảng lớn, `pg_stat_progress_vacuum` giúp trả lời:

> “VACUUM có đang chạy không, chạy bảng nào, đang ở pha nào, đã xử lý bao nhiêu heap block?”

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    CASE
        WHEN heap_blks_total > 0
        THEN ROUND(
            100.0 * heap_blks_scanned
            / heap_blks_total,
            1
        )
        ELSE NULL
    END AS pct_heap_scanned,
    index_vacuum_count
FROM pg_catalog.pg_stat_progress_vacuum
ORDER BY datname, table_name;
~~~

Các cột hiển thị và giai đoạn VACUUM có thể thay đổi giữa major versions; truy vấn dùng những cột thường có ở nhiều bản PostgreSQL đang được hỗ trợ.

### 16.1. Percent heap scanned không phải tiến độ tổng tuyệt đối

`heap_blks_scanned/heap_blks_total` đo **tiến độ quét heap**; VACUUM còn xử lý index, heap vacuuming, cleanup và cập nhật thống kê. Vì vậy 100% heap scanned **không đồng nghĩa toàn bộ VACUUM đã hoàn tất**.

### 16.2. Xem phiên làm việc của VACUUM

~~~sql
SELECT
    pid,
    datname,
    backend_type,
    state,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'autovacuum worker'
   OR query ILIKE '%VACUUM%'
ORDER BY query_start;
~~~

Đừng đánh giá một worker “bị treo” chỉ vì nó đã chạy lâu; nó có thể đang quét bảng lớn hoặc chờ tài nguyên. Cần đối chiếu tiến độ, I/O, lock wait và tốc độ XID tăng.

### 16.3. Lưu ý query text và quyền xem

Một role bình thường có thể không được xem chi tiết query hoặc thông tin phiên khác. Hệ thống giám sát nên dùng role có quyền **đọc thống kê tối thiểu cần thiết** (ví dụ `pg_monitor` khi chính sách cho phép), không cấp superuser cho dashboard chỉ để chạy các câu SELECT.

## 17. Long-running transaction: vì sao VACUUM bị giữ chân?

Một transaction giữ snapshot lâu có thể buộc PostgreSQL giữ lại các phiên bản hàng cũ mà snapshot đó vẫn có thể nhìn thấy. Điều này làm tăng **vacuum cleanup horizon** và gây dead tuple/bloat; một số trường hợp cũng cản tiến trình bảo trì freeze horizon.

Ví dụ:

~~~text
Session A:
    BEGIN REPEATABLE READ;
    SELECT ...;  -- tạo snapshot
    ... idle 4 giờ ...

Session B/C/D:
    UPDATE / DELETE rất nhiều hàng;
    COMMIT;

Autovacuum:
    không thể dọn những phiên bản hàng mà
    snapshot cũ của A vẫn có thể cần.
~~~

### 17.1. Xem các session có transaction mở lâu

~~~sql
SELECT
    pid,
    usename,
    application_name,
    datname,
    state,
    xact_start,
    now() - xact_start AS transaction_duration,
    backend_xid,
    age(backend_xid) AS backend_xid_age,
    backend_xmin,
    age(backend_xmin) AS backend_xmin_age,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

**Hai cột rất quan trọng:**

- `backend_xid`: XID top-level mà backend được cấp, nếu có.
- `backend_xmin`: horizon XID liên quan snapshot/tuổi mà backend đang giữ, nếu có.

Không phải mọi session có `backend_xid`. Một transaction chỉ đọc có thể giữ snapshot và `backend_xmin` mà không được cấp XID ghi.

### 17.2. Xem những horizon XID tuổi lớn nhất

~~~sql
SELECT
    pid,
    datname,
    usename,
    state,
    xact_start,
    age(backend_xid) AS xid_age,
    age(backend_xmin) AS xmin_age
FROM pg_catalog.pg_stat_activity
WHERE backend_xid IS NOT NULL
   OR backend_xmin IS NOT NULL
ORDER BY GREATEST(
    age(backend_xid),
    age(backend_xmin)
) DESC NULLS LAST;
~~~

`age(NULL::xid)` trả NULL. Ở PostgreSQL, `GREATEST` bỏ qua đối số NULL khi có giá trị khác NULL, nên có thể sắp theo horizon lớn hơn trong hai cột.

### 17.3. idle in transaction nguy hiểm theo cách nào?

~~~sql
SELECT
    pid,
    application_name,
    state,
    now() - xact_start AS transaction_duration,
    age(backend_xmin) AS xmin_age
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
~~~

Session **`idle in transaction`** đã mở transaction nhưng không thực hiện câu lệnh ngay lúc quan sát. Nó có thể:

- Giữ snapshot cũ;
- Giữ lock hàng/bảng;
- Làm VACUUM không thể dọn đủ dead tuples;
- Tăng thời gian giữ XID horizon;
- Gây bloat và tăng chi phí vận hành.

**Không có nghĩa mọi session idle in transaction đều ngay lập tức gây wraparound.** Cần xem `backend_xmin`, thời gian, workload và loại transaction.

### 17.4. Hướng xử lý

Trong ứng dụng:

- Transaction cần ngắn và luôn `COMMIT`/`ROLLBACK` đúng chỗ.
- Không mở transaction rồi chờ người dùng click, gọi API chậm hoặc làm tác vụ ngoài database kéo dài.
- Xử lý connection pool trả kết nối còn transaction mở.
- Cân nhắc `idle_in_transaction_session_timeout` sau khi đánh giá luồng nghiệp vụ.

Trong vận hành:

- Xác định PID/ứng dụng/owner của transaction dài;
- Liên hệ owner để commit/rollback an toàn;
- Chỉ cân nhắc `pg_cancel_backend`/`pg_terminate_backend` theo runbook có quyền và hiểu tác động;
- Đừng tự ý terminate một transaction đang thực hiện thanh toán hoặc migration quan trọng.

## 18. Prepared transaction / Two-phase commit có thể giữ XID cũ

PostgreSQL hỗ trợ two-phase commit với:

~~~sql
PREPARE TRANSACTION 'some-gid';
COMMIT PREPARED 'some-gid';
ROLLBACK PREPARED 'some-gid';
~~~

Đây là cú pháp minh họa, **không chạy như một bài demo tùy tiện**. Khi một transaction đã được **PREPARE** nhưng chưa COMMIT/ROLLBACK PREPARED, nó có thể giữ transaction ID và những tài nguyên liên quan lâu dài, kể cả khi client ban đầu đã ngắt kết nối.

### 18.1. Xem prepared transactions

~~~sql
SELECT
    gid,
    "transaction" AS xid,
    age("transaction") AS xid_age,
    prepared,
    now() - prepared AS prepared_duration,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY xid_age DESC;
~~~

`pg_prepared_xacts` có cột tên `transaction`, được đặt trong dấu ngoặc kép để tránh nhầm với từ khóa SQL. Cột `prepared` là thời điểm transaction được đưa vào trạng thái prepared.

### 18.2. Không tự COMMIT PREPARED hoặc ROLLBACK PREPARED bừa bãi

Một prepared transaction thường thuộc một giao thức điều phối nhiều hệ thống. Tự rollback để giải phóng XID mà không biết coordinator đã quyết định commit hay chưa có thể tạo **bất nhất dữ liệu giữa các thành phần**.

Khi `age("transaction")` rất lớn:

1. Xác nhận GID, owner, database và hệ thống điều phối.
2. Kiểm tra trạng thái giao dịch phân tán thực tế.
3. Thực hiện `COMMIT PREPARED`/`ROLLBACK PREPARED` theo quyết định nhất quán của coordinator.
4. Đo lại XID horizon và quan sát VACUUM.

**Prepared transactions là một trong các nguồn blocker phải kiểm tra trước khi xử lý cảnh báo wraparound nghiêm trọng.**

## 19. Replication slots và horizon bị giữ lại

Replication slot giúp PostgreSQL quản lý các trạng thái cần giữ cho một consumer/replica. Một slot không còn được tiêu thụ có thể giữ lại tài nguyên:

- **`restart_lsn`:** liên quan việc giữ WAL cho replication; ảnh hưởng disk/WAL.
- **`xmin`:** horizon XID cần giữ cho dữ liệu hàng trong những tình huống liên quan.
- **`catalog_xmin`:** horizon bảo vệ catalog tuples, thường quan trọng với logical decoding.

**WAL retention** và **XID vacuum horizon** có liên hệ nhưng **không phải cùng một metric**.

### 19.1. Kiểm tra slot không hoạt động và XID age

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    xmin,
    age(xmin) AS xmin_age,
    catalog_xmin,
    age(catalog_xmin) AS catalog_xmin_age
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    age(xmin),
    age(catalog_xmin)
) DESC NULLS LAST;
~~~

Một slot không có `xmin`/`catalog_xmin` không nên bị coi là blocker XID chỉ vì `restart_lsn` cũ; nó có thể gây **rủi ro giữ WAL** riêng. Cần phân tích các cột theo ý nghĩa đúng.

### 19.2. Vì sao slot cũ nguy hiểm?

Khi slot giữ một `xmin` hoặc `catalog_xmin` quá cũ, PostgreSQL có thể phải bảo tồn những phiên bản dữ liệu/catalog để consumer còn đọc được. Điều này có thể ngăn VACUUM dọn dẹp và tiến đủ nhanh với một số horizon.

Ví dụ:

~~~text
Logical replication consumer đã dừng
          |
          v
Slot không tiến xmin/catalog_xmin
          |
          v
VACUUM bị hạn chế xóa tuple cũ
          |
          v
Tăng bloat, có thể làm khó tiến freeze horizon
~~~

### 19.3. Không tự drop replication slot

~~~sql
-- Chỉ là cú pháp tham khảo, KHÔNG tự chạy trong production:
-- SELECT pg_drop_replication_slot('slot_name');
~~~

Xóa slot có thể làm replica/consumer **không thể tiếp tục từ WAL cần thiết**, phải rebuild/resync hoặc mất vị trí đồng bộ. DBA phải xác định slot có còn được dùng, tác động tới subscriber/replica và kế hoạch khôi phục trước khi can thiệp.

### 19.4. hot_standby_feedback

Trong replication vật lý, cơ chế `hot_standby_feedback` có thể gửi thông tin snapshot cần giữ từ standby về primary, làm primary giữ lại phiên bản hàng lâu hơn để tránh query trên standby bị hủy do vacuum. Đây có thể là một nguồn làm **vacuum cleanup horizon** cũ đi, cần cân bằng giữa độ trễ truy vấn standby và bloat ở primary.

**Không bật/tắt hot_standby_feedback chỉ để giải quyết một cảnh báo** mà không hiểu replication topology, streaming lag và tác động tới VACUUM.

## 20. Multixact ID wraparound: một vấn đề liên quan nhưng khác XID

PostgreSQL còn có **Multixact ID (MXID)**, dùng khi nhiều transaction cùng khóa một tuple; thông tin đa chủ thể khóa có thể được biểu diễn qua một Multixact ID và nội dung thành viên lưu ngoài tuple header.

Giống XID, Multixact ID cũng có **bộ đếm 32 bit** và cần cơ chế aging/freezing riêng.

| XID wraparound | MXID wraparound |
| --- | --- |
| Liên quan định danh transaction tạo/xóa tuple và MVCC visibility | Liên quan định danh nhóm transaction cùng khóa tuple |
| `pg_class.relfrozenxid` | `pg_class.relminmxid` |
| `pg_database.datfrozenxid` | `pg_database.datminmxid` |
| `age(xid)` | `mxid_age(mxid)` |
| `autovacuum_freeze_max_age` | `autovacuum_multixact_freeze_max_age` |
| `vacuum_failsafe_age` | `vacuum_multixact_failsafe_age` |

### 20.1. Giám sát Multixact age ở database

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY mxid_age DESC;
~~~

### 20.2. Giám sát Multixact age ở relation

~~~sql
SELECT
    c.oid::regclass AS table_name,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY mxid_age DESC
LIMIT 20;
~~~

### 20.3. Cấu hình tham khảo

~~~sql
SHOW autovacuum_multixact_freeze_max_age;
SHOW vacuum_multixact_freeze_min_age;
SHOW vacuum_multixact_freeze_table_age;
SHOW vacuum_multixact_failsafe_age;
~~~

Ở PostgreSQL 18, `autovacuum_multixact_freeze_max_age` thường mặc định **400 triệu MXID**, nhưng cần xem cấu hình server thực tế.

### 20.4. MXID exhaustion khác phạm vi lỗi XID

Nếu nguy cơ MXID wraparound quá cao, PostgreSQL có thể từ chối **những thao tác cần cấp Multixact ID mới**. Điều này khác với XID exhaustion làm các thao tác cần XID mới bị chặn rộng hơn.

**Không gộp hai alert vào một chỉ số “transaction age” duy nhất.** Nên giám sát cả `age(datfrozenxid)` và `mxid_age(datminmxid)` vì một trong hai có thể tới ngưỡng trước.

## 21. Bài lab an toàn: quan sát xmin, xmax và VACUUM

**Mục tiêu:** quan sát tuple version có `xmin`/`xmax` và VACUUM trên một bảng nhỏ; không giả lập vòng quay XID thật. Lab dùng một schema riêng `xid_lab_233`; nếu schema đã tồn tại, đổi tên thay vì xóa dữ liệu.

### 21.1. Tạo bảng

~~~sql
CREATE SCHEMA xid_lab_233;

CREATE TABLE xid_lab_233.inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL
        CHECK (quantity >= 0),
    note TEXT NOT NULL DEFAULT ''
);

INSERT INTO xid_lab_233.inventory
    (sku, quantity, note)
VALUES
    ('LAB-01', 10, 'Phiên bản ban đầu'),
    ('LAB-02', 20, 'Không thay đổi');
~~~

### 21.2. Xem cột hệ thống

~~~sql
SELECT
    sku,
    quantity,
    xmin::text AS inserting_xid,
    xmax::text AS xmax_raw
FROM xid_lab_233.inventory
ORDER BY sku;
~~~

`xmin`/`xmax` là **system columns**. Số cụ thể phụ thuộc server và lịch sử transaction của lab; **không sao chép kết quả XID từ máy khác rồi kỳ vọng giống nhau**.

### 21.3. Tạo tuple version mới bằng UPDATE

~~~sql
UPDATE xid_lab_233.inventory
SET
    quantity = 12,
    note = 'Đã cập nhật'
WHERE sku = 'LAB-01'
RETURNING
    sku,
    quantity,
    xmin::text AS inserting_xid,
    xmax::text AS xmax_raw;
~~~

Khi `UPDATE` tạo tuple version mới, `xmin` của phiên bản mới phản ánh transaction đã tạo ra nó. Phiên bản cũ có thể tiếp tục tồn tại vật lý cho đến khi VACUUM có thể dọn an toàn.

### 21.4. Theo dõi tuổi mốc bảng

~~~sql
SELECT
    c.oid::regclass AS table_name,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'xid_lab_233.inventory'::regclass;
~~~

**Đừng kỳ vọng `age(relfrozenxid)` bằng `age(xmin)` của hàng LAB-01.** Mốc ở cấp bảng liên quan toàn bộ relation và quá trình vacuum, không đại diện một tuple được chọn.

### 21.5. Quan sát VACUUM (VERBOSE)

Chạy câu sau **ngoài transaction `BEGIN`**, vì PostgreSQL không cho `VACUUM` bên trong transaction block thông thường:

~~~sql
VACUUM (VERBOSE, ANALYZE) xid_lab_233.inventory;
~~~

Xem thông điệp về số trang, số tuple và XID horizon theo phiên bản server. Trên bảng lab chỉ vài hàng và XID còn rất mới, giá trị `relfrozenxid` có thể không giảm tuổi đáng kể.

### 21.6. Thử FREEZE trong lab riêng

~~~sql
VACUUM (FREEZE, VERBOSE) xid_lab_233.inventory;
~~~

Đây là ví dụ **trên bảng lab**, nơi chi phí nhỏ và mục tiêu giáo dục. `FREEZE` đặt chiến lược freeze tích cực; PostgreSQL chỉ có thể freeze những phiên bản **đủ an toàn** theo các quy tắc visibility.

Sau đó đọc:

~~~sql
SELECT
    age(c.relfrozenxid) AS xid_age_after
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'xid_lab_233.inventory'::regclass;
~~~

Không mặc định `xmin=2` sau freeze trong PostgreSQL mới. Thay đổi `relfrozenxid` và log VACUUM là dữ liệu quan sát phù hợp hơn.

### 21.7. VACUUM không cần và không nên đặt trong BEGIN để ROLLBACK

Lệnh:

~~~sql
BEGIN;
VACUUM xid_lab_233.inventory;
-- Lỗi: VACUUM cannot run inside a transaction block
ROLLBACK;
~~~

được viết để giải thích lỗi cú pháp/vận hành, **không phải trình tự nên thử trong production**. Hãy thực hành `VACUUM` ở chế độ autocommit của SQL client.

### 21.8. Kết luận của lab

Lab chứng minh:

- Tuple có cột hệ thống liên quan transaction.
- `UPDATE` tạo tuple version mới theo MVCC.
- VACUUM là thao tác bảo trì độc lập.
- Freezing liên quan an toàn XID lâu dài, không phải thay đổi giá trị nghiệp vụ.
- Không cần hàng tỷ transaction hoặc các lệnh nguy hiểm để học cơ chế này.

**Nó không mô phỏng điều kiện wraparound thật**. Những cảnh báo chống wraparound sẽ chỉ được thảo luận bằng tình huống giả định và SQL giám sát.

## 22. Chẩn đoán khi tuổi XID tăng nhưng VACUUM không đẩy mốc tiến

Đặt tình huống:

~~~text
Database prod:
    age(datfrozenxid) tăng liên tục.
    Một relation có age(relfrozenxid) cao.
    Autovacuum được cấu hình bật.
    Nhiều lần VACUUM vẫn không giảm được tuổi mốc.
~~~

Đừng ngay lập tức chỉnh `autovacuum_freeze_max_age` cao hơn. Xử lý theo từng nhóm bằng chứng.

### 22.1. Có table hoặc TOAST nào giữ mốc cũ?

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY xid_age DESC
LIMIT 30;
~~~

Nếu relation đứng đầu không nằm trong database hiện tại mà ở database khác, **phải kết nối vào database đó** để xem chi tiết `pg_class`.

### 22.2. VACUUM có đang chạy và tiến tới đâu?

~~~sql
SELECT
    pid,
    datname,
    relid::regclass,
    phase,
    heap_blks_total,
    heap_blks_scanned
FROM pg_catalog.pg_stat_progress_vacuum;
~~~

Nếu có worker chạy rất lâu, xem log, I/O, wait event và kích thước bảng. VACUUM có thể chưa hoàn tất aggressive scan nên chưa cập nhật horizon cuối cùng.

### 22.3. Có snapshot/XID cũ đang bị giữ?

~~~sql
SELECT
    pid,
    datname,
    application_name,
    state,
    age(backend_xid) AS xid_age,
    age(backend_xmin) AS xmin_age,
    now() - xact_start AS transaction_age
FROM pg_catalog.pg_stat_activity
WHERE backend_xid IS NOT NULL
   OR backend_xmin IS NOT NULL
ORDER BY GREATEST(
    age(backend_xid),
    age(backend_xmin)
) DESC NULLS LAST;
~~~

### 22.4. Có prepared transaction bỏ quên?

~~~sql
SELECT
    gid,
    database,
    age("transaction") AS xid_age,
    prepared
FROM pg_catalog.pg_prepared_xacts
ORDER BY xid_age DESC;
~~~

### 22.5. Replication slot có giữ xmin/catalog_xmin?

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    age(xmin) AS xmin_age,
    age(catalog_xmin) AS catalog_xmin_age
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    age(xmin),
    age(catalog_xmin)
) DESC NULLS LAST;
~~~

### 22.6. Có vấn đề lock, cấu hình hoặc tài nguyên?

Các khả năng cần xem:

- Autovacuum bị tắt hoặc bị hạn chế worker/cost quá mạnh.
- Những job DDL hoặc lock xung đột liên tục làm vacuum bị ngắt/chậm.
- Disk gần đầy, I/O quá thấp, filesystem lỗi.
- Transaction/replication slot/prepared transaction giữ horizon cũ.
- Bảng rất lớn ít có trang all-frozen.
- Các partition cũ/TOAST/materialized view không được bảo trì đầy đủ.
- Một database tĩnh không được ứng dụng chạm tới nhưng XID vẫn già đi do database khác.

**Tách rõ nguyên nhân:** một transaction dài có thể ngăn dọn dead tuples; một bảng ít được aggressive vacuum có thể giữ `relfrozenxid` cũ dù không có transaction dài. Không dùng một giả thuyết duy nhất để giải thích mọi cảnh báo.

## 23. Runbook khi xuất hiện cảnh báo chống wraparound

Đây là khung xử lý **dành cho DBA có quyền và hiểu topology**, không phải hướng dẫn người mới tự vận hành trên production. Ưu tiên giảm nguy cơ không cấp được XID và giữ dữ liệu nguyên vẹn.

### Giai đoạn A — Xác nhận mức độ nghiêm trọng

1. Ghi nhận phiên bản PostgreSQL, database được cảnh báo và nội dung log.
2. Chạy `SELECT datname, age(datfrozenxid) ... FROM pg_database`.
3. Xem tốc độ tăng XID và thời gian đến các ngưỡng theo cấu hình.
4. Xác định bảng/TOAST nào có `relfrozenxid` già nhất trong database liên quan.
5. Kiểm tra VACUUM đã đang chạy chưa, có phải anti-wraparound không.

Nếu thấy thông báo:

~~~text
database ... must be vacuumed within ... transactions
~~~

thì đây là **cảnh báo sự cố** cần được xử lý ngay theo runbook, không đợi lượt bảo trì định kỳ.

### Giai đoạn B — Gỡ blocker hợp lệ

Tài liệu PostgreSQL khuyến nghị xem xét:

- Prepared transactions cũ trong `pg_prepared_xacts`;
- Transaction mở lâu có `backend_xid`/`backend_xmin` cũ;
- Replication slots không còn được dùng nhưng giữ `xmin`/`catalog_xmin`;
- Khóa/tài nguyên đang ngăn VACUUM tiến hành.

**Không tự ý:**

- Kết thúc một transaction nghiệp vụ quan trọng mà không biết kết quả.
- Rollback prepared transaction đang chờ quyết định coordinator.
- Drop slot phục vụ replica/consumer còn hoạt động.
- Hủy anti-wraparound worker chỉ vì nó đang sử dụng I/O.

### Giai đoạn C — VACUUM để tiến freeze horizon

Trên database được xác định, lệnh tham khảo:

~~~sql
-- Chạy ngoài explicit transaction block;
-- cần quyền xử lý đủ các bảng, kể cả system catalogs.
VACUUM;
~~~

Trong tình huống khẩn cấp, **quyền của role thực thi rất quan trọng**. Tài liệu PostgreSQL lưu ý nếu không có quyền vacuum system catalogs/những relation liên quan, `datfrozenxid` có thể không thể tiến đủ. Một DBA có quyền thích hợp phải thực hiện theo runbook.

Lệnh `VACUUM` không có table list chỉ tác động **database hiện tại** (đối với những bảng mà role có quyền), **không tự vacuum mọi database của cluster**. Nếu nhiều database cùng nguy hiểm, cần chạy từng database hoặc dùng công cụ `vacuumdb` được cấu hình đúng.

### Giai đoạn D — Nếu database đã từ chối cấp XID

Theo tài liệu PostgreSQL hiện đại, **vẫn có thể chạy VACUUM thường** trong tình trạng từ chối cấp XID mới. Hướng khuyến nghị:

1. Xử lý những prepared transactions cũ được phép xử lý;
2. Kết thúc những transaction/snapshot đang giữ horizon quá cũ theo quyết định an toàn;
3. Dọn những replication slot **thật sự bỏ quên** sau khi đánh giá tác động;
4. Thực hiện **`VACUUM` thông thường** ở database bị ảnh hưởng;
5. Đo lại `age(datfrozenxid)`/`relfrozenxid` và xác nhận thao tác ghi phục hồi;
6. Khôi phục/cải thiện cấu hình autovacuum, monitoring và quy trình vận hành.

**Không dùng `VACUUM FULL` trong tình huống khẩn cấp**: nó cần XID/khóa mạnh và có thể không chạy được hoặc làm rủi ro tệ hơn. Cũng **không mặc định dùng `VACUUM FREEZE` để “cứu nhanh”**: theo tài liệu hiện đại, nó có thể thực hiện nhiều việc hơn mức tối thiểu cần để khôi phục an toàn.

**Không chuyển sang single-user mode theo các bài hướng dẫn cũ nếu chưa có lý do cụ thể.** PostgreSQL hiện đại có các cơ chế bảo vệ trong chế độ bình thường; tắt chúng có thể tăng rủi ro.

### Giai đoạn E — Xác minh hậu sự cố và phòng tái diễn

- Xác nhận tuổi `datfrozenxid` đã giảm hoặc ngừng tăng bất thường.
- Xem các bảng/TOAST lâu đời nhất còn lại.
- Kiểm tra `pg_stat_progress_vacuum` và log.
- Xác minh workload ghi bình thường, latency/lock wait trong giới hạn.
- Xử lý nguyên nhân gốc: prepared xact, slot, transaction dài, autovacuum tuning, thiếu tài nguyên.
- Thiết lập alert sớm theo XID/MXID age và tốc độ tiêu thụ.
- Ghi lại timeline, quyết định can thiệp, tác động và runbook cải tiến.

### 23.1. Không ghi trực tiếp vào catalog để “reset age”

**Cấm coi câu sau là giải pháp:**

~~~sql
-- TUYỆT ĐỐI KHÔNG CHẠY:
-- UPDATE pg_catalog.pg_database
-- SET datfrozenxid = ...;
~~~

Các mốc trong catalog phản ánh bất biến vật lý của tuple và khả năng nhìn thấy. Sửa chúng thủ công có thể làm metadata không còn phù hợp dữ liệu thực và gây rủi ro mất dữ liệu/không nhất quán.

### 23.2. Backup không thay VACUUM chống wraparound

Backup/PITR là thành phần bảo vệ dữ liệu quan trọng, nhưng **không làm XID chưa frozen trong cluster đang chạy tự trở nên an toàn**. Có backup không cho phép bỏ qua anti-wraparound maintenance.

## 24. Thiết kế cảnh báo XID/MXID age

Một hệ thống monitoring nên lưu dữ liệu dạng chuỗi thời gian:

~~~text
postgres_database_xid_age{database="orders"} = ...
postgres_database_mxid_age{database="orders"} = ...
postgres_relation_xid_age{database="orders",relation="..."} = ...
postgres_autovacuum_running{database="orders"} = ...
postgres_oldest_backend_xmin_age{database="orders"} = ...
postgres_replication_slot_catalog_xmin_age{slot="..."} = ...
~~~

Đây là **tên metric minh họa**, không cam kết exporter cụ thể cung cấp cùng tên. Tùy Prometheus exporter, công cụ cloud hoặc script nội bộ mà bạn phải ánh xạ sang metric thực tế.

### 24.1. Các lớp cảnh báo mẫu

| Mức xử lý minh họa | Điều kiện quan sát | Hành động |
| --- | --- | --- |
| Thông tin | XID age tăng đều, vacuum khỏe | Tiếp tục theo dõi |
| Sớm | Một database/table tiến gần ngưỡng maintenance nội bộ | Kiểm tra autovacuum, trend, tăng dung lượng bảo trì nếu cần |
| Cao | Tuổi vượt ngưỡng anti-wraparound cấu hình, vacuum không hoàn tất | Điều tra blocker, worker, progress, cấp quyền/DBA |
| Rất cao | Tiến gần vùng failsafe hoặc log cảnh báo wraparound | Kích hoạt ứng phó sự cố, ưu tiên bảo vệ XID |
| Khẩn cấp | Từ chối cấp XID mới | Runbook phục hồi có kiểm soát, VACUUM sau khi giải quyết blocker |

**Không copy các mức tỷ lệ phần trăm cứng cho mọi cluster.** Nên đặt ngưỡng theo phiên bản, cấu hình, tốc độ tiêu thụ XID, số lượng bảng/database và thời gian cần cho VACUUM aggressive hoàn tất.

### 24.2. Alert nên bao gồm điều gì?

Một thông báo hữu ích có thể ghi:

~~~text
Cluster: cluster-a
Database: reporting
XID age: 165,000,000
autovacuum_freeze_max_age: 200,000,000
Oldest table: archive.events_2022
Last autovacuum: 10 days ago
Oldest backend_xmin age: 8,000,000
Oldest slot catalog_xmin age: 140,000,000
Observed XID consumption: ~12,000,000/day
Runbook: PostgreSQL XID wraparound response
~~~

Số liệu là **giả định** để minh họa bố cục, không phải tình trạng hệ thống thực tế. Khi có dữ liệu thật, cần tránh ghi thông tin nhạy cảm trong kênh công khai.

### 24.3. Dự báo bằng tốc độ phải tính cả thời gian sửa

Nếu còn 4 ngày tới ngưỡng bảo trì nhưng VACUUM một bảng lớn mất 10 giờ, một cuộc điều tra replication slot mất 1 ngày và chỉ có nhân sự DBA trong giờ làm việc, thì cảnh báo tại “còn 4 ngày” có thể **đã rất muộn**. Alert nên phát đủ sớm để kiểm tra nguyên nhân trước khi cần dừng workload ghi.

### 24.4. Sử dụng age theo transaction thay vì thời gian tuyệt đối

Mức XID age lớn nhất có thể tăng mạnh trong flash sale, import batch, migration hoặc workload tăng đột biến. Nếu chỉ gửi email “sau mỗi 30 ngày chạy VACUUM” mà không theo dõi XID, hệ thống có thể vượt ngưỡng trước lịch.

## 25. Tại sao transaction dài, bloat và wraparound thường xuất hiện cùng nhau?

Cả ba liên quan tới **khả năng loại bỏ/đóng băng thông tin MVCC** nhưng không phải một vấn đề duy nhất.

### 25.1. Bloat

Một transaction dài giữ snapshot cũ khiến VACUUM chưa thể xóa các tuple versions mà snapshot đó vẫn có thể cần. Khi nhiều UPDATE/DELETE tiếp tục, bảng/index có thể phình to.

### 25.2. XID age

Trong cùng lúc, global XID counter vẫn tiến lên khi các worker khác ghi. `age(datfrozenxid)`/`age(relfrozenxid)` tăng nếu các mốc không được đẩy tiến.

### 25.3. Freeze horizon

Việc advance `relfrozenxid` cần một lần VACUUM phù hợp và điều kiện an toàn. Nếu snapshot giữ chân quá cũ, một số tuple chưa đủ điều kiện freeze/cleanup, hoặc VACUUM không thể hoàn tất đúng thời điểm, mốc XID có thể còn già.

### 25.4. Kết luận chẩn đoán

~~~text
Transaction dài / slot cũ
        |
        +-- có thể giữ dead tuples
        |      |
        |      +-- bloat
        |
        +-- có thể giữ snapshot/XID horizon
               |
               +-- hạn chế cleanup/freeze tiến trình
                      |
                      +-- XID age tăng theo workload
~~~

Nhưng một database cũng có thể có XID age tăng chỉ vì **bảng tĩnh rất lớn chưa được aggressive vacuum**, dù không có transaction dài. Vì vậy phải xem cả **nguyên nhân về horizon** lẫn **lịch bảo trì/độ lớn quan hệ**.

## 26. Những ngộ nhận phổ biến

| Ngộ nhận | Giải thích đúng |
| --- | --- |
| “XID là 64-bit rồi nên không còn wraparound.” | `xid8` mở rộng định danh; tuple/MVCC vẫn cần quản lý XID 32-bit |
| “Phải đợi 4,29 tỷ transaction mới có sự cố.” | Cửa sổ so sánh an toàn khoảng **2³¹** từ XID chưa frozen |
| “PostgreSQL mỗi 24 giờ tự reset XID.” | XID tăng theo cấp phát transaction, không theo đồng hồ |
| “Transaction mở là đã có XID.” | Có virtual XID; non-virtual XID thường cấp khi cần ghi |
| “Mỗi database có bộ đếm XID riêng.” | Các database trong cùng cluster dùng bộ đếm XID chung |
| “Bảng không UPDATE thì không cần VACUUM.” | Tuple cũ trong bảng tĩnh vẫn cần freeze |
| “VACUUM chỉ để thu nhỏ file.” | VACUUM còn thu gom dead tuples, visibility map, freeze và phòng wraparound |
| “VACUUM thường luôn đẩy relfrozenxid.” | Chỉ khi VACUUM đã quét đủ các trang cần thiết |
| “VACUUM FREEZE luôn là lựa chọn tốt nhất.” | Nó có thể tốn công và không phù hợp xử lý khẩn cấp |
| “VACUUM FULL cứu wraparound.” | FULL đòi tài nguyên/khóa, có thể cần XID, không phải runbook cứu |
| “xmin bằng 2 mới là frozen.” | PostgreSQL hiện đại thường dùng cờ frozen, có thể giữ nguyên xmin |
| “xmax != 0 nghĩa là hàng bị xóa.” | xmax còn có thể liên quan khóa/Multixact và trạng thái chưa commit |
| “age(xid)=giây từ khi commit.” | Nó đo số XID đã trôi qua |
| “datfrozenxid là lúc vacuum gần nhất.” | Nó là XID horizon, không phải timestamp |
| “Đã vacuum một bảng application thì cluster an toàn.” | Còn TOAST, catalogs, relation khác, database khác |
| “Autovacuum off nghĩa là không có anti-wraparound vacuum.” | PostgreSQL vẫn ép anti-wraparound trong tình huống cần |
| “Không có dead tuples thì không có XID risk.” | Freezing của live tuples vẫn cần |
| “Chỉ cần chỉnh ngưỡng lên cao để hết cảnh báo.” | Không sửa blocker/horizon và có thể giảm biên an toàn |
| “Cứ terminate mọi PID có age lớn.” | Có thể phá transaction nghiệp vụ; phải xác định owner/tác động |
| “Replication slot chỉ giữ WAL.” | Một số slot còn giữ `xmin`/`catalog_xmin` |
| “Có backup thì wraparound không nguy hiểm.” | Backup không thay bảo trì MVCC của cluster đang chạy |
| “Đang cảnh báo wraparound phải stop server.” | PostgreSQL hiện đại có runbook VACUUM trong chế độ hoạt động |
| “XID và MXID là một.” | Hai không gian ID khác nhau với mốc và ngưỡng riêng |
| “pct_of_half_range=100% mới cần chú ý.” | Alert phải đặt sớm từ ngưỡng maintenance và trend |
| “VACUUM đầy đủ là chạy trong BEGIN rồi rollback.” | `VACUUM` không chạy trong transaction block thông thường |

## 27. Bài tập thực hành

Các bài tập không yêu cầu tăng XID tới mức nguy hiểm. Chỉ dùng truy vấn đọc, bảng lab `xid_lab_233` hoặc mô phỏng bằng số.

### Bài 1 — Phân biệt XID với thời gian

Giải thích vì sao một database hoạt động một năm với 10.000 transaction ghi/ngày có thể có XID age thấp hơn một database khác hoạt động 10 ngày với 10 triệu transaction ghi/ngày.

**Gợi ý:** age được đo bằng số lần cấp XID đã trôi qua, không phải uptime.

### Bài 2 — XID quay vòng

Tính:

~~~text
2^32 = ?
2^31 = ?
~~~

**Đáp án:** `4.294.967.296` và `2.147.483.648`. Vì sao giới hạn cần chú ý là khoảng **nửa không gian** XID chứ không phải đợi trọn một vòng?

### Bài 3 — Xem XID hiện tại có cần cấp thêm không

So sánh ý nghĩa:

~~~sql
SELECT pg_current_xact_id_if_assigned();
SELECT pg_current_xact_id();
~~~

**Câu hỏi:** hàm nào có thể cấp XID nếu transaction chưa có? Vì sao một dashboard read-only không nên gọi liên tục hàm có tác dụng cấp mới?

### Bài 4 — Đọc xmin và xmax

Trên `xid_lab_233.inventory`, quan sát `xmin`, `xmax` trước/sau `UPDATE`.

**Câu hỏi:** `xmin` mới cho biết gì? Tại sao `xmax` không nên được diễn giải duy nhất là “đã xóa”?

### Bài 5 — Frozen flag

Sau `VACUUM (FREEZE)` trên bảng lab, `xmin` có bắt buộc đổi thành 2 không?

**Đáp án:** không trong PostgreSQL hiện đại; freezing chủ yếu dùng metadata/cờ, không đảm bảo `xmin=2`.

### Bài 6 — Bảng tĩnh vẫn cần freeze

Một bảng chỉ insert từ năm trước, có 100 triệu hàng và gần như không có dead tuples. Trong cùng cluster, ứng dụng khác ghi liên tục.

**Câu hỏi:** bảng tĩnh có cần VACUUM chống wraparound không? Vì sao?

### Bài 7 — Xem database nào rủi ro nhất

Viết truy vấn `SELECT datname, age(datfrozenxid) ... FROM pg_database ORDER BY ... DESC`.

**Câu hỏi:** vì sao database ít traffic vẫn có XID age tăng?

### Bài 8 — Xem bảng già nhất

Trong database lab, tìm 10 relation có `age(relfrozenxid)` lớn nhất. Bỏ qua giả định “mới VACUUM hôm qua là đủ”; kết hợp `relfrozenxid` với log VACUUM để đánh giá.

### Bài 9 — TOAST

Viết truy vấn join `pg_class` của heap với `pg_class` của TOAST qua `reltoastrelid` và so sánh tuổi hai relation.

**Câu hỏi:** nếu heap age nhỏ nhưng TOAST age lớn, chỉ VACUUM phần heap trong mô hình phù hợp có đủ giải thích tuổi database không?

### Bài 10 — Tính phần trăm nửa vòng

Giả sử `age(datfrozenxid)=1.000.000.000`. Tính:

\[
\frac{1.000.000.000}{2.147.483.648}\times100\%
\]

Kết quả xấp xỉ **46,6%**. Vì sao con số này **không** cho phép chờ đến 99% mới chạy bảo trì?

### Bài 11 — Ngưỡng cấu hình

Chạy:

~~~sql
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
SHOW vacuum_failsafe_age;
~~~

**Câu hỏi:** trong các tham số này, tham số nào làm anti-wraparound VACUUM được ép chạy? Tham số nào là lớp bảo vệ rất muộn?

### Bài 12 — VACUUM thường so với FULL

Phân biệt `VACUUM`, `VACUUM (FREEZE)` và `VACUUM FULL` về phạm vi quét, khóa và mục đích.

**Đáp án định hướng:** `FULL` dùng rewrite/thu gọn file và khóa mạnh; không phải lựa chọn cứu wraparound.

### Bài 13 — Theo dõi autovacuum tiến độ

Chạy truy vấn `pg_stat_progress_vacuum` ở mục 16.

**Câu hỏi:** nếu `heap_blks_scanned = heap_blks_total`, có chắc VACUUM đã hoàn tất toàn bộ pha index/cleanup không?

### Bài 14 — Tìm transaction dài

Dùng `pg_stat_activity` xem `xact_start`, `backend_xid`, `backend_xmin` và `age(...)`.

**Câu hỏi:** transaction read-only có thể giữ snapshot mà `backend_xid IS NULL` không? Vì sao phải quan sát cả `backend_xmin`?

### Bài 15 — Prepared transaction bị bỏ quên

Một prepared transaction có `age("transaction")` gần 600 triệu.

**Câu hỏi:** có nên lập tức `ROLLBACK PREPARED`? Ai phải xác nhận quyết định và tại sao?

### Bài 16 — Replication slot

Giả sử một logical slot `active=FALSE`, `catalog_xmin_age=700 triệu` và `restart_lsn` rất cũ.

**Câu hỏi:** những rủi ro nào độc lập? Vì sao không thể chỉ drop slot mà không xem subscriber/recovery?

### Bài 17 — VACUUM trong transaction

Thử `BEGIN; VACUUM xid_lab_233.inventory;` trên lab rồi rollback.

**Kỳ vọng:** lỗi vì VACUUM không được chạy trong transaction block thông thường. Sau đó chạy VACUUM riêng ở chế độ autocommit.

### Bài 18 — Kiểm tra xu hướng

Giả sử mốc `datfrozenxid` không thay đổi, XID age tăng từ 100 triệu lên 115 triệu trong 3 ngày.

**Câu hỏi:** tốc độ xấp xỉ bao nhiêu XID/ngày? Nếu chỉ xét tốc độ này, còn bao lâu tới ngưỡng 200 triệu?

**Đáp án:** ~5 triệu/ngày và ~17 ngày. Đây chỉ là phép tính tình huống, không phải dự báo đáng tin cho production khi tốc độ/ VACUUM thay đổi.

### Bài 19 — Khi age giảm sau VACUUM

Hệ giám sát ghi `age(datfrozenxid)` từ 190 triệu xuống 30 triệu sau aggressive vacuum.

**Câu hỏi:** có phải cluster tự “hoàn tác 160 triệu transaction” không?

**Đáp án:** không; freeze horizon `datfrozenxid` tiến lên, nên **khoảng cách tới bộ đếm hiện tại giảm**.

### Bài 20 — Cảnh báo cao nhưng autovacuum đang chạy

Một database có `xid_age=240 triệu`, `autovacuum_freeze_max_age=200 triệu`, và `pg_stat_progress_vacuum` cho thấy aggressive VACUUM đang quét bảng lớn.

**Câu hỏi:** đã có wraparound failure chưa? Cần quan sát gì tiếp theo? Có nên hủy VACUUM để giải tỏa I/O không?

### Bài 21 — Tình huống khẩn cấp

Server xuất hiện log:

~~~text
ERROR: database is not accepting commands that assign
new transaction IDs to avoid wraparound data loss
~~~

**Bài tập:** liệt kê thứ tự kiểm tra prepared transactions, backend horizons, replication slots, VACUUM thường và xác minh sau sửa. Vì sao không dùng `VACUUM FULL`?

### Bài 22 — XID khác MXID

Viết query hiển thị `age(datfrozenxid)` và `mxid_age(datminmxid)` cho mọi database.

**Câu hỏi:** nếu XID age bình thường nhưng MXID age tiến gần ngưỡng, có được xem là an toàn không?

### Bài 23 — Tính toán thời gian cần bảo trì

Một bảng lịch sử 2 TB chưa freeze, tốc độ quét VACUUM trong workload hiện tại chỉ 80 MB/s. Hãy ước lượng thời gian **chỉ để đọc 2 TB** theo đơn vị byte nhất quán, rồi giải thích vì sao tổng thời gian VACUUM thực tế có thể lớn hơn hoặc nhỏ hơn ước lượng quét toàn bộ file (all-frozen pages, I/O cạnh tranh, index, buffer, parallelism).

**Mục tiêu:** không chỉ đặt cảnh báo theo số XID, mà còn theo khả năng **hoàn thành maintenance kịp thời**.

### Bài 24 — Đọc trạng thái autovacuum bị tắt

Một server có `autovacuum=off` và ít bảng bị UPDATE.

**Câu hỏi:** liệu PostgreSQL có thể ép anti-wraparound VACUUM không? Vì sao vẫn không khuyến nghị tắt autovacuum?

### Bài 25 — Code review dashboard

Một developer lập dashboard bằng:

~~~sql
SELECT pg_current_xact_id();
~~~

và gọi mỗi giây trên từng kết nối chỉ đọc.

**Câu hỏi:** hàm này có thể tạo tác dụng phụ gì? Đề xuất cách giám sát ít tác động hơn, có phân biệt XID 32-bit với xid8.

### Bài 26 — Nguyên nhân trực tiếp hay hệ quả

Một hệ thống có:

~~~text
age(datfrozenxid) cao
n_dead_tup cao
last_autovacuum cũ
replication slot catalog_xmin cũ
backend_xmin cũ
~~~

**Bài tập:** giải thích mỗi dấu hiệu chứng minh điều gì, điều gì chưa chứng minh được, và thứ tự điều tra phù hợp. Phân biệt **dấu hiệu**, **blocker** và **nguyên nhân gốc**.

### Bài 27 — Viết runbook ngắn cho nhóm vận hành

Từ các mục 13–24, viết một runbook một trang:

1. Điều kiện kích hoạt;
2. SQL đọc database age;
3. SQL tìm relation/TOAST;
4. SQL xem VACUUM progress;
5. SQL tìm backend/slot/prepared transaction cũ;
6. Ai có quyền quyết định xử lý blocker;
7. Khi nào chạy VACUUM thường;
8. Cách xác minh và rollback/khôi phục nghiệp vụ.

**Quan trọng:** không đưa lệnh terminate session/drop slot tự động vào runbook nếu chưa có bước kiểm soát quyền và tác động.

## 28. Checklist vận hành phòng ngừa wraparound

1. **Giám sát `age(datfrozenxid)` cho mọi database**, không chỉ database ứng dụng chính.
2. **Giám sát `mxid_age(datminmxid)`** để không bỏ sót Multixact exhaustion.
3. Theo dõi các bảng/TOAST/partition có `relfrozenxid`/`relminmxid` già nhất.
4. Quan sát `pg_stat_progress_vacuum`, `pg_stat_all_tables` và log autovacuum.
5. Có alert sớm theo **cấu hình server thực tế**, tốc độ XID và thời gian cần VACUUM hoàn thành.
6. Không tắt autovacuum hoặc kéo ngưỡng quá cao chỉ để tránh I/O.
7. Giữ transaction ngắn; giảm `idle in transaction`.
8. Rà soát prepared transactions theo hai-phase commit coordinator.
9. Quản lý replication slots có owner/retention/resync plan, không để slot bị bỏ quên vô thời hạn.
10. Kiểm tra hot standby feedback và ảnh hưởng giữ cleanup horizon.
11. Đảm bảo system catalogs, bảng tĩnh, partition lịch sử, materialized view và TOAST cũng được bảo trì.
12. Chọn quyền/role DBA cho công việc VACUUM cần bao phủ system catalogs.
13. Đảm bảo đủ disk, I/O, worker, maintenance window và quan sát cạnh tranh với DDL/lock.
14. Không dùng `VACUUM FULL` như biện pháp cứu XID exhaustion.
15. Không sửa trực tiếp `relfrozenxid`/`datfrozenxid`.
16. Không tạo hàng tỷ transaction hoặc tắt bảo vệ để “test” sự cố.
17. Có runbook cho trường hợp gần failsafe và trường hợp server từ chối cấp XID.
18. Sau mỗi sự cố, ghi nhận nguyên nhân, biện pháp phòng tái diễn, metrics và kiểm thử alert.

## 29. Tài liệu PostgreSQL chính thức

Nên đọc tài liệu của **đúng major version server**; các liên kết sau tới tài liệu hiện hành hoặc trang chức năng tương ứng:

- [Transactions and Identifiers](https://www.postgresql.org/docs/current/transaction-id.html): XID 32 bit, `xid8`, epoch và thời điểm cấp XID.
- [Routine Vacuuming — Preventing Transaction ID Wraparound Failures](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-WRAPAROUND): lý do freezing, vòng quay XID, `relfrozenxid`/`datfrozenxid`, ngưỡng bảo vệ và runbook phục hồi.
- [Routine Vacuuming — Multixacts and Wraparound](https://www.postgresql.org/docs/current/routine-vacuuming.html#VACUUM-FOR-MULTIXACT-WRAPAROUND): Multixact ID, `relminmxid` và `datminmxid`.
- [Server Configuration — Vacuuming](https://www.postgresql.org/docs/current/runtime-config-vacuum.html): `autovacuum_freeze_max_age`, `vacuum_freeze_min_age`, `vacuum_failsafe_age` và các tham số liên quan.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): tùy chọn `FREEZE`, `FULL`, `VERBOSE`, giới hạn thực thi và xử lý relation.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-info.html): `age(xid)`, `mxid_age`, `pg_current_xact_id` và `pg_current_xact_id_if_assigned`.
- [Progress Reporting — VACUUM](https://www.postgresql.org/docs/current/progress-reporting.html): `pg_stat_progress_vacuum`, các pha VACUUM.
- [Statistics Collector / pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `backend_xid`, `backend_xmin`, trạng thái transaction và các view thống kê.
- [pg_prepared_xacts](https://www.postgresql.org/docs/current/view-pg-prepared-xacts.html): các transaction đang chờ hoàn tất two-phase commit.
- [pg_replication_slots](https://www.postgresql.org/docs/current/view-pg-replication-slots.html): replication slot, `xmin`, `catalog_xmin`, `restart_lsn`.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html): cách snapshot/tuple versions hoạt động.

Đặc biệt, các ngưỡng cảnh báo muộn và cột thống kê có thể được thay đổi giữa các phiên bản. Không sử dụng một lệnh hoặc con số được sao chép từ một phiên bản khác mà bỏ qua tài liệu và log của cluster đang vận hành.

## 30. Tổng kết

**Transaction ID wraparound** bắt nguồn từ việc PostgreSQL lưu phần XID truyền thống cho MVCC trong không gian **32 bit hữu hạn**. Bộ đếm XID dùng chung giữa các database sẽ quay vòng sau khoảng **4,29 tỷ** ID, và cơ chế so sánh theo modulo chỉ có thể phân loại an toàn thứ tự transaction trong cửa sổ khoảng **2,147 tỷ**. Nếu một phiên bản hàng chưa freeze trở nên quá cũ, nó có nguy cơ bị nhầm thành do một transaction “ở tương lai” tạo ra.

**VACUUM freezing** là cơ chế phòng vệ cốt lõi: các phiên bản hàng đủ cũ được đánh dấu an toàn để không còn phụ thuộc vào so sánh XID vòng tròn. `pg_class.relfrozenxid` theo dõi mốc của từng relation; `pg_database.datfrozenxid` theo dõi mốc của từng database; `age(xid)` đo khoảng cách bằng **số transaction ID**, **không phải giây hoặc ngày**. Vì XID counter là tài nguyên chung toàn cluster, ngay cả database tĩnh cũng phải được bảo trì.

PostgreSQL hỗ trợ nhiều lớp tự bảo vệ: **normal/aggressive VACUUM, anti-wraparound autovacuum** ở ngưỡng khoảng **200 triệu XID mặc định**, và **failsafe** khi tuổi trở nên quá cao. Nhưng hệ thống vẫn cần DBA theo dõi **tuổi XID/MXID, TOAST/partition, VACUUM progress, transaction mở lâu, prepared transactions và replication slots**; những nguồn giữ snapshot cũ hoặc hạn chế bảo trì có thể khiến hệ thống tiến tới cảnh báo nặng và cuối cùng **từ chối cấp XID mới để tránh mất dữ liệu**.

**Nguyên tắc vận hành quan trọng nhất:** đừng chờ wraparound xảy ra mới xử lý. Giám sát theo XID age và tốc độ cấp XID, giữ autovacuum hoạt động, không lạm dụng transaction dài, quản lý slot/prepared transaction, và ưu tiên **VACUUM đúng cách sau khi loại bỏ blocker**. Không sửa catalog thủ công, không dùng `VACUUM FULL` để chữa wraparound và không tự tạo tình huống nguy hiểm trong môi trường có dữ liệu quan trọng. Phòng ngừa từ sớm giúp PostgreSQL duy trì MVCC an toàn ngay cả khi hệ thống đã trải qua nhiều vòng quay Transaction ID.
