# Freeze, tuổi transaction ID và chống wraparound trong PostgreSQL

## 1. Vì sao PostgreSQL phải freeze transaction ID?

PostgreSQL dùng transaction ID (XID) để xác định transaction nào tạo, cập nhật hoặc xóa một tuple và transaction đó đã commit hay chưa. XID thông thường có độ rộng 32-bit, nên không gian số hữu hạn. Sau khi dùng hết không gian, bộ đếm sẽ quay vòng và dùng lại các giá trị cũ.

Nếu một tuple vẫn giữ XID rất cũ trong khi bộ đếm đã quay vòng, PostgreSQL có thể nhầm transaction cũ với transaction mới có cùng số XID. Điều này có thể làm sai kết quả kiểm tra visibility. Vì vậy PostgreSQL phải đánh dấu các XIDs cũ là đã hoàn tất từ lâu trước khi chúng trở nên mơ hồ.

**Freezing** là quá trình đánh dấu transaction metadata cũ trong tuple là frozen. Sau khi freeze, PostgreSQL không còn cần tra cứu trạng thái transaction thông thường của XID cũ để xác định tuple đó luôn visible theo quy tắc xmin.

VACUUM vì vậy có hai nhiệm vụ quan trọng:

- Dọn các tuple versions không còn cần thiết, cập nhật visibility map và hỗ trợ tái sử dụng không gian.
- Freeze XIDs/MultiXacts đủ cũ để bảo vệ database khỏi wraparound.

Một bảng ít UPDATE/DELETE vẫn cần VACUUM để freeze. Số dead tuples thấp không chứng minh tuổi XID an toàn.

```text
XID 32-bit tăng dần
       |
       v
Tuple lưu transaction metadata
       |
       v
VACUUM kiểm tra XID/MultiXact cũ
       |
       +---- Chưa đủ tuổi / snapshot còn cần
       |          |
       |          v
       |      Chưa thể freeze
       |
       +---- Đã đủ tuổi và an toàn
                  |
                  v
          Freeze tuple metadata
                  |
                  v
       relfrozenxid / relminmxid tiến lên
                  |
                  v
        Giữ khoảng an toàn trước wraparound

Nếu VACUUM không theo kịp:
anti-wraparound autovacuum -> cảnh báo -> từ chối transaction mới
```

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao XID 32-bit có thể wraparound và tại sao cần freezing.
2. Phân biệt transaction ID thông thường, special XIDs và FrozenTransactionId.
3. Hiểu vai trò của tuple xmin, xmax, MultiXactId và MVCC visibility.
4. Giải thích tuple freezing và vì sao không phải tuple nào cũng freeze được ngay.
5. Đọc pg_class.relfrozenxid, pg_database.datfrozenxid và tuổi XID.
6. Phân biệt tuổi XID với số lượng dead tuples.
7. Hiểu vacuum_freeze_min_age, vacuum_freeze_table_age và autovacuum_freeze_max_age.
8. Hiểu aggressive vacuum và visibility map.
9. Phân biệt VACUUM thường, VACUUM FREEZE và VACUUM FULL.
10. Hiểu anti-wraparound autovacuum và failsafe vacuum.
11. Theo dõi MultiXact wraparound bằng relminmxid và datminmxid.
12. Phát hiện long-running transactions, prepared transactions và replication slots giữ vacuum horizon.
13. Theo dõi autovacuum qua pg_stat_progress_vacuum và pg_stat_activity.
14. Xử lý cảnh báo wraparound mà không tùy tiện xóa dữ liệu hoặc reset counter.
15. Thiết kế lịch vận hành VACUUM và capacity monitoring phù hợp.
16. Kiểm thử freezing trong database lab và xác minh tuổi XID thay đổi.
17. Phân biệt anti-wraparound protection với cleanup/bloat maintenance thông thường.

## 3. XID 32-bit và giới hạn so sánh

### 3.1. XID không phải số thứ tự vô hạn

XID thông thường có không gian 32-bit:

```text
2^32 = 4,294,967,296
```

Một số giá trị được dành riêng cho mục đích nội bộ; transaction IDs bình thường bắt đầu ở vùng XID thông thường. Sau khi bộ đếm dùng hết không gian, nó quay vòng.

Không thể so sánh XID như số nguyên tăng mãi bằng phép so sánh số học thông thường. PostgreSQL sử dụng phép so sánh có nhận biết wraparound và giới hạn một cửa sổ an toàn.

### 3.2. Nửa không gian XID là ranh giới quan trọng

Một XID cũ và một XID mới có thể trở nên mơ hồ nếu khoảng cách giữa chúng vượt quá nửa không gian 32-bit:

```text
2^31 = 2,147,483,648
```

PostgreSQL phải bảo đảm các XIDs còn được tuple tham chiếu không vượt qua vùng mơ hồ này. Freeze loại bỏ sự phụ thuộc vào trạng thái transaction của các XIDs cũ.

### 3.3. Special transaction IDs

Một số XID đặc biệt thường được nhắc tới:

| Tên | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| InvalidTransactionId | 0 | Không phải XID bình thường hợp lệ |
| BootstrapTransactionId | 1 | Transaction bootstrap ban đầu |
| FrozenTransactionId | 2 | Đại diện tuple đã được freeze |
| FirstNormalTransactionId | 3 | Bắt đầu vùng XID thông thường |

Đây là chi tiết nội bộ PostgreSQL. Ứng dụng không nên tự gán hoặc chỉnh sửa tuple system columns.

### 3.4. XID được cấp theo nhu cầu

Không phải mọi câu SELECT đều cần cấp XID thông thường. Transaction thường nhận XID khi thực hiện thao tác cần transaction identity, chẳng hạn ghi dữ liệu. Vì vậy tốc độ tăng XID không luôn bằng số SQL statements hoặc số HTTP requests.

Một transaction read-only có thể giữ snapshot lâu mà không tự tiêu thụ XID mới, nhưng snapshot của nó vẫn có thể giữ lại các XIDs cũ và cản trở VACUUM.

### 3.5. Quan sát XID hiện tại cẩn thận

Một số hàm lấy XID hiện tại có thể cấp XID nếu transaction chưa được cấp. Khi viết monitoring, ưu tiên hàm không cấp XID nếu chỉ cần xem transaction đã có ID hay chưa. Tránh tạo thêm transaction IDs không cần thiết trong công việc giám sát.

## 4. Tuple visibility: xmin, xmax và freezing

Mỗi tuple heap có transaction metadata. Hai system columns quan trọng là:

- `xmin`: XID của transaction tạo tuple version.
- `xmax`: XID hoặc MultiXactId liên quan tới transaction xóa/cập nhật tuple, hoặc row locking tùy trạng thái tuple.

Ví dụ:

```sql
SELECT
    event_id,
    xmin,
    xmax,
    ctid
FROM vacuum_lab.events
LIMIT 20;
```

`xmin` và `xmax` ở đây là system columns của tuple. Không dùng chúng làm khóa nghiệp vụ hoặc sửa trực tiếp.

### 4.1. Một UPDATE thường tạo tuple version mới

PostgreSQL dùng MVCC. Khi UPDATE, hệ thống thường tạo tuple version mới và đánh dấu version cũ đã bị thay thế theo transaction metadata. Snapshot khác nhau có thể nhìn thấy các versions khác nhau.

VACUUM phải xác định khi nào tuple cũ không còn cần thiết cho snapshot hợp lệ nào nữa; sau đó nó có thể prune/reclaim tuple và freeze metadata cần thiết của tuple còn sống.

### 4.2. Freeze xử lý transaction identity cũ

Một tuple được tạo bởi transaction đã commit từ lâu có thể được đánh dấu Frozen. Khi đó PostgreSQL không cần tra cứu trạng thái commit cũ để xác định tuple đó luôn visible theo xmin.

Điều này không có nghĩa tuple không bao giờ bị UPDATE/DELETE nữa. Tuple mới vẫn có XID riêng khi được thay đổi.

### 4.3. Freeze không làm tuple bất tử

Tuple frozen vẫn có thể được UPDATE hoặc DELETE sau này. Freeze chỉ thay đổi cách PostgreSQL diễn giải transaction metadata cũ; nó không khóa dữ liệu hoặc cấm sửa row.

### 4.4. Không phải mọi XID đều có thể freeze ngay

Tuple được tạo bởi transaction còn đang chạy hoặc nằm trong vùng mà snapshot cũ có thể cần phân biệt thì không thể được đánh dấu frozen một cách an toàn. VACUUM phải tôn trọng global visibility horizon.

### 4.5. Freezing khác xóa dead tuple

- **Pruning/removal:** loại bỏ tuple versions không còn cần thiết.
- **Freezing:** đánh dấu XID cũ của tuple còn tồn tại để không bị nhầm sau wraparound.

Một VACUUM có thể freeze live tuples mà không xóa chúng. Ngược lại, tuple dead có thể được loại bỏ khi an toàn mà không cần giữ lại như frozen tuple.

## 5. MultiXact ID và wraparound thứ hai

PostgreSQL còn có MultiXact IDs (MXID). Chúng được sử dụng khi nhiều transactions cùng giữ row locks trên một tuple. Trong một số trường hợp, xmax của tuple đại diện MultiXact thay vì một XID đơn.

MultiXact ID cũng có giới hạn và cần được freeze/retire. Vì thế, giám sát XID thôi chưa đủ.

### 5.1. MultiXact gồm nhiều thành viên

Một MultiXact đại diện tập transaction members và lock modes. Nó giúp PostgreSQL quản lý nhiều row lockers đồng thời.

### 5.2. Metadata theo dõi MultiXact

| Catalog field | Ý nghĩa |
| --- | --- |
| pg_class.relminmxid | MXID cũ nhất relation còn có thể cần |
| pg_database.datminmxid | MXID cũ nhất được theo dõi ở cấp database |

Dùng hàm `mxid_age()` để xem tuổi MultiXact theo cách nhận biết wraparound.

### 5.3. Vì sao bảng nhiều row locks cần chú ý?

Một workload có nhiều concurrent transactions chạy `SELECT ... FOR UPDATE` hoặc các row-locking operations có thể tạo MultiXacts. Dù XID age còn thấp, MXID age vẫn có thể tăng đáng kể.

### 5.4. Freeze XID và freeze MultiXact là hai trục

Một bảng có thể an toàn về XID nhưng đang tiến gần ngưỡng MultiXact, hoặc ngược lại. Theo dõi cả `relfrozenxid`/`datfrozenxid` lẫn `relminmxid`/`datminmxid`.

## 6. relfrozenxid và datfrozenxid

PostgreSQL lưu các mốc freezing trong catalog.

### 6.1. relfrozenxid

`pg_class.relfrozenxid` là mốc XID cho relation. Nó đại diện XID cũ nhất mà relation vẫn có thể cần xử lý theo visibility/freeze rules. Khi VACUUM hoàn tất đủ công việc an toàn, mốc này có thể tiến lên.

### 6.2. datfrozenxid

`pg_database.datfrozenxid` là mốc cấp database, được xác định từ các relations cần theo dõi trong database. Một relation cũ có thể giữ mốc database lại dù các bảng khác đã được vacuum gần đây.

### 6.3. Age thay vì so sánh XID thô

Dùng:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_catalog.pg_database
ORDER BY age(datfrozenxid) DESC;
```

`age(xid)` trả số transaction IDs đã đi qua kể từ mốc XID theo semantics wraparound-aware. Đây là cách phù hợp hơn để quan sát tuổi.

### 6.4. Không so XID bằng MAX/MIN số học tùy tiện

Do XID quay vòng, `MAX(relfrozenxid)` hoặc so sánh integer casts không cho biết relation nào cũ nhất theo nghĩa transaction age. Dùng `age()`.

### 6.5. Database age và table age trả lời câu hỏi khác nhau

- `age(datfrozenxid)`: database đã tiến gần ngưỡng nào.
- `age(relfrozenxid)`: relation cụ thể đang giữ XID age bao nhiêu.

Database-level age giúp alert tổng quan; relation-level age tìm bảng, catalog hoặc TOAST đang giữ mốc cũ.

## 7. Lab: tạo một bảng có thể theo dõi

Các ví dụ thực hành dùng schema riêng. Không chạy thử thao tác freeze hoặc tạo tải XID trên production.

### 7.1. Tạo schema và dữ liệu

```sql
CREATE SCHEMA IF NOT EXISTS vacuum_lab;

CREATE TABLE vacuum_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO vacuum_lab.events (tenant_id, payload)
SELECT
    (g % 10)::integer,
    'event-' || g
FROM generate_series(1, 10000) AS g;

ANALYZE vacuum_lab.events;
```

### 7.2. Xem tuple metadata

```sql
SELECT
    event_id,
    xmin,
    xmax,
    ctid
FROM vacuum_lab.events
ORDER BY event_id
LIMIT 10;
```

Bạn có thể thấy nhiều rows có cùng xmin nếu chúng được tạo trong cùng transaction.

### 7.3. Xem relfrozenxid của bảng

```sql
SELECT
    c.oid::regclass AS relation,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'vacuum_lab.events'::regclass;
```

Tuổi trong lab có thể còn rất thấp vì bảng vừa được tạo.

### 7.4. Tạo dead tuples để hiểu VACUUM thường

```sql
UPDATE vacuum_lab.events
SET payload = payload || '-updated'
WHERE event_id <= 1000;

DELETE FROM vacuum_lab.events
WHERE event_id BETWEEN 9001 AND 9500;

SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'vacuum_lab';
```

Statistics là ước lượng và có thể cập nhật trễ. Dead tuple counts không phải XID age.

### 7.5. Chạy VACUUM FREEZE trên bảng lab

```sql
VACUUM (FREEZE, VERBOSE) vacuum_lab.events;
```

Sau đó đọc lại:

```sql
SELECT
    c.oid::regclass AS relation,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'vacuum_lab.events'::regclass;
```

Với bảng nhỏ và không có horizon blocker, VACUUM FREEZE có thể tiến mốc freezing gần XID hiện hành. Kết quả chính xác tùy transactions đang hoạt động và điều kiện visibility.

### 7.6. VACUUM không chạy trong transaction block

Không đặt `VACUUM` trong `BEGIN ... COMMIT` thông thường. Chạy như statement độc lập từ psql/JDBC connection phù hợp. Nếu công cụ migration tự bọc mọi lệnh trong transaction, cần cấu hình task riêng.

## 8. Các ngưỡng freezing quan trọng

PostgreSQL có nhiều settings. Chúng không có cùng mục đích.

| Setting | Vai trò |
| --- | --- |
| vacuum_freeze_min_age | Tuổi tối thiểu của XID trước khi VACUUM cân nhắc freeze |
| vacuum_freeze_table_age | Tuổi relation khiến VACUUM thực hiện aggressive scan |
| autovacuum_freeze_max_age | Tuổi relation khiến anti-wraparound autovacuum được yêu cầu |
| vacuum_failsafe_age | Ngưỡng failsafe cho XID wraparound |
| vacuum_multixact_freeze_min_age | Ngưỡng tuổi MultiXact để freeze |
| vacuum_multixact_freeze_table_age | Ngưỡng aggressive scan theo MXID |
| autovacuum_multixact_freeze_max_age | Ngưỡng anti-wraparound theo MultiXact |
| vacuum_multixact_failsafe_age | Ngưỡng failsafe theo MultiXact |

Giá trị mặc định phụ thuộc phiên bản PostgreSQL và có thể bị override bởi cấu hình. Hãy đọc settings trên server đang vận hành thay vì ghi nhớ một con số như thể nó bất biến.

### 8.1. vacuum_freeze_min_age

XID có tuổi vượt ngưỡng này có thể được freeze trong một VACUUM thông thường nếu việc freeze an toàn. Mặc định phổ biến là 50 triệu XIDs.

Đặt quá thấp có thể làm freezing xảy ra sớm và tăng công việc ghi tuple metadata. Đặt quá cao làm các tuples giữ XID lâu hơn và dồn thêm công việc cho các lần VACUUM sau.

### 8.2. vacuum_freeze_table_age

Khi tuổi `relfrozenxid` của bảng vượt ngưỡng này, VACUUM có thể thực hiện aggressive scan để tìm các tuples cần freeze trên relation, không chỉ dựa vào các pages đã được đánh dấu all-visible.

Mặc định phổ biến là 150 triệu XIDs.

### 8.3. autovacuum_freeze_max_age

Khi relation tiến tới ngưỡng này, PostgreSQL yêu cầu một anti-wraparound vacuum. Mặc định phổ biến là 200 triệu XIDs.

Đây là ngưỡng bảo vệ quan trọng, không phải mục tiêu để vận hành bảng thường xuyên ở sát ngưỡng.

### 8.4. Các ngưỡng có quan hệ

Với cấu hình mặc định phổ biến:

```text
vacuum_freeze_min_age       ~  50 million
vacuum_freeze_table_age     ~ 150 million
autovacuum_freeze_max_age   ~ 200 million
                                  |
                                  v
                        2^31 = 2.147 billion
                        vùng nguy hiểm wraparound
```

Các con số trên chỉ để hình dung thứ tự. Một hệ thống có thể đặt values khác; hãy kiểm tra `SHOW` và `pg_settings`.

### 8.5. Tại sao không đặt autovacuum_freeze_max_age thật lớn?

Tăng ngưỡng có thể trì hoãn anti-wraparound vacuum, khiến các XID cũ tồn tại lâu hơn và tăng dung lượng transaction status data cần giữ. Nó giảm tần suất công việc ngắn hạn nhưng làm giảm safety margin và có thể biến một vấn đề vận hành thành sự cố nghiêm trọng.

### 8.6. Không chỉ nhìn một setting

`vacuum_freeze_min_age` ảnh hưởng tuple freeze trong một vacuum; `vacuum_freeze_table_age` ảnh hưởng aggressive scan; `autovacuum_freeze_max_age` quyết định khi cần vacuum khẩn hơn. Điều chỉnh một setting không thay thế các setting còn lại.

## 9. Aggressive vacuum và visibility map

Visibility map (VM) lưu thông tin theo page về khả năng tất cả tuples trên page đã visible với mọi transactions hiện hành, và liệu page đã all-frozen hay chưa.

### 9.1. All-visible

Một page all-visible có thể cho phép VACUUM bỏ qua một số công việc visibility thông thường và hỗ trợ index-only scans. All-visible không tự có nghĩa tất cả XIDs đã được freeze.

### 9.2. All-frozen

Một page all-frozen đã được freeze đủ để không cần kiểm tra lại XIDs cũ trong các lần VACUUM thông thường cho mục đích wraparound. Đây là trạng thái mạnh hơn all-visible.

### 9.3. Aggressive vacuum

Khi cần tiến `relfrozenxid`, VACUUM phải kiểm tra mọi page có thể còn XIDs chưa freeze, kể cả page có all-visible bit nhưng chưa all-frozen. Nó vẫn có thể tận dụng all-frozen map để bỏ qua pages đã an toàn.

### 9.4. Vì sao aggressive scan tốn I/O?

Một bảng rất lớn có thể cần đọc nhiều pages để xác định không còn XIDs quá cũ. Nếu storage chậm, buffer cache nhỏ hoặc workload đồng thời cao, vacuum có thể mất thời gian đáng kể.

### 9.5. Page bị pin hoặc lock

Một số page/tuple không thể được xử lý ngay vì hoạt động đồng thời, buffer pin hoặc lock conditions. VACUUM có thể phải bỏ qua và quay lại sau; tiến trình cần được quan sát qua logs/progress.

## 10. VACUUM thường, VACUUM FREEZE và VACUUM FULL

| Lệnh | Mục tiêu | Tác động |
| --- | --- | --- |
| VACUUM table_name | Dọn dead tuples, cập nhật visibility, freeze theo ngưỡng | Thường cho phép concurrent reads/writes |
| VACUUM (FREEZE) table_name | Yêu cầu freezing mạnh hơn | Aggressive freeze; vẫn là VACUUM thường |
| VACUUM FULL table_name | Rewrite table để thu hồi disk space | Cần lock mạnh, có thể chặn truy cập |
| ANALYZE table_name | Cập nhật planner statistics | Không thay freezing |

### 10.1. FREEZE không phải FULL

`VACUUM (FREEZE)` không đồng nghĩa rewrite toàn bảng như `VACUUM FULL`. Không dùng FULL chỉ vì thấy cảnh báo XID age cao; FULL có thể gây lock và I/O nặng mà không phải giải pháp thích hợp cho wraparound.

### 10.2. VACUUM thường cũng có thể freeze

Không cần thêm FREEZE cho mọi lệnh VACUUM. VACUUM thường vẫn freeze các XIDs đủ cũ theo freeze settings. FREEZE hữu ích khi chủ động muốn freeze sớm hơn, ví dụ trong maintenance hoặc chuẩn bị dữ liệu lab.

### 10.3. VACUUM FULL rewrite relation

Rewrite tạo file relation mới và cần lock mạnh, thường là ACCESS EXCLUSIVE. Nó có thể kéo dài thời gian lock và cần nhiều không gian tạm. Phải lập kế hoạch riêng, không chạy như phản ứng tự động với warning wraparound.

### 10.4. VACUUM cần quyền phù hợp

Thông thường owner relation hoặc role có đặc quyền thích hợp mới thực hiện được. Anti-wraparound autovacuum chạy bằng cơ chế hệ thống riêng. Không cấp superuser cho ứng dụng chỉ để gọi VACUUM.

## 11. Anti-wraparound autovacuum

Autovacuum bình thường có thể được kích hoạt bởi dead tuples hoặc inserts. Anti-wraparound vacuum được yêu cầu dựa trên tuổi XID/MultiXact để bảo vệ database, kể cả khi bảng không có nhiều dead tuples.

### 11.1. Autovacuum không chỉ là tối ưu hiệu năng

Nó là một cơ chế bảo vệ tính đúng đắn của dữ liệu. Tắt autovacuum để giảm I/O mà không có kế hoạch vacuum thay thế có thể dẫn đến database ngừng nhận transactions.

### 11.2. Anti-wraparound có thể chạy dù autovacuum bị tắt

PostgreSQL vẫn khởi chạy các worker cần thiết để ngăn transaction ID wraparound ngay cả khi cấu hình autovacuum thông thường bị disable. Tuy nhiên, việc disable autovacuum vẫn rất nguy hiểm vì các công việc cleanup/analyze thông thường bị ảnh hưởng.

### 11.3. Worker có thể ưu tiên freeze hơn cleanup

Khi tuổi tiến gần ngưỡng nguy hiểm, hệ thống ưu tiên tiến mốc freeze. Failsafe có thể giảm cost delay và bỏ qua một số index cleanup để đẩy nhanh công việc bảo vệ wraparound.

### 11.4. Cảnh báo trong log

Khi một database tiến gần giới hạn, log có thể cảnh báo database cần được vacuum trong một số lượng transactions còn lại. Đây là tín hiệu vận hành khẩn cấp, không phải warning có thể bỏ qua đến maintenance window kế tiếp.

### 11.5. Khi chạm vùng nguy hiểm

PostgreSQL có cơ chế ngăn cấp phát XID mới để tránh wraparound làm hỏng visibility. Hệ thống có thể từ chối commands cần transaction ID hoặc không nhận transactions mới theo trạng thái bảo vệ. Không đợi đến lúc này mới lập kế hoạch xử lý.

## 12. Failsafe vacuum

Một vacuum có thể bị trì hoãn bởi cost-based delay để giảm ảnh hưởng workload. Khi tuổi XID/MultiXact đạt ngưỡng failsafe, PostgreSQL có thể chuyển sang chế độ ưu tiên chống wraparound.

### 12.1. vacuum_failsafe_age

Setting này xác định ngưỡng tuổi XID để VACUUM kích hoạt failsafe behavior. Giá trị mặc định và khả năng cấu hình phụ thuộc phiên bản; hãy kiểm tra server thực tế.

### 12.2. Failsafe thay đổi ưu tiên

Failsafe có thể tắt cost-based vacuum delay và bỏ qua index cleanup để ưu tiên hoàn thành freezing. Điều này giúp tránh wraparound nhưng có thể tăng I/O/CPU và để lại một số cleanup work cần xử lý sau.

### 12.3. Không nên dựa vào failsafe như lịch bảo trì

Failsafe là lớp bảo vệ cuối khi vacuum đã bị chậm so với nhu cầu. Mục tiêu vận hành là phát hiện age sớm và để autovacuum hoàn thành trước khi failsafe cần can thiệp.

### 12.4. MultiXact có failsafe riêng

Theo dõi `vacuum_multixact_failsafe_age` cùng các ngưỡng freeze MultiXact. Không chỉ kiểm tra XID.

## 13. Những thứ giữ vacuum horizon lại

VACUUM không thể freeze hoặc remove tuple nếu một snapshot cũ vẫn có thể cần phân biệt transaction state của tuple. Một số nguồn giữ horizon lâu:

- Transaction mở lâu, kể cả transaction read-only.
- Session `idle in transaction`.
- Prepared transactions chưa `COMMIT PREPARED` hoặc `ROLLBACK PREPARED`.
- Replication slots giữ `xmin` hoặc `catalog_xmin`.
- Standby feedback (`hot_standby_feedback`) giữ xmin trên primary.
- Snapshot được export và còn transaction sở hữu snapshot.
- Một số logical decoding/replication workflows.

### 13.1. Long-running transaction

Một transaction bắt đầu từ lâu có thể giữ `backend_xmin` cũ. Dù không chạy query liên tục, snapshot cũ vẫn có thể ngăn VACUUM tiến horizon.

### 13.2. Idle in transaction

Một session đã BEGIN, chạy query rồi ngồi chờ application có thể giữ transaction và locks. Đây là nguyên nhân thường gặp khiến vacuum không thể dọn hoặc freeze như mong muốn.

### 13.3. Prepared transactions

Prepared transaction giữ locks và transaction state sau giai đoạn `PREPARE TRANSACTION`. Nếu coordinator không hoàn tất two-phase commit, chúng có thể giữ horizon lâu.

### 13.4. Replication slots

Replication slot có thể giữ lại WAL và/hoặc xmin/catalog_xmin để consumer tiếp tục decode đúng. Slot bị bỏ quên có thể giữ dữ liệu cũ và làm tăng disk usage hoặc cản trở vacuum.

### 13.5. Hot standby feedback

Standby có thể gửi xmin về primary để tránh conflict với queries trên replica. Điều đó giúp replica nhưng có thể giữ vacuum horizon ở primary. Cần cân bằng replica query stability và primary bloat/freeze progress.

### 13.6. Không xóa slot tùy tiện

Xóa replication slot có thể làm subscriber/replica không thể tiếp tục từ vị trí cũ và cần rebuild/resync. Trước khi drop, xác minh consumer, retention, restart LSN và quy trình khôi phục.

## 14. Monitoring database XID age

Bắt đầu từ database:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    current_setting('autovacuum_freeze_max_age')::bigint
        AS autovacuum_freeze_max_age,
    round(
        100.0 * age(datfrozenxid)::numeric
        / NULLIF(
            current_setting('autovacuum_freeze_max_age')::numeric,
            0
        ),
        1
    ) AS pct_of_freeze_max
FROM pg_catalog.pg_database
ORDER BY age(datfrozenxid) DESC;
```

### 14.1. Diễn giải phần trăm

`pct_of_freeze_max` giúp dashboard nhìn xu hướng. Nó không phải xác suất wraparound hoặc SLA. Nếu vượt 100%, cần hiểu autovacuum đã được kích hoạt nhưng chưa chắc đã hoàn tất; phải điều tra ngay.

### 14.2. Theo dõi MXID age ở cấp database

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY GREATEST(
    age(datfrozenxid),
    mxid_age(datminmxid)
) DESC;
```

Hai age có thể có tốc độ tăng và ngưỡng cấu hình khác nhau. Dashboard nên có series riêng thay vì gộp thành một số duy nhất.

### 14.3. Xem settings đang có hiệu lực

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name IN (
    'autovacuum',
    'autovacuum_freeze_max_age',
    'vacuum_freeze_min_age',
    'vacuum_freeze_table_age',
    'vacuum_failsafe_age',
    'autovacuum_multixact_freeze_max_age',
    'vacuum_multixact_freeze_min_age',
    'vacuum_multixact_freeze_table_age',
    'vacuum_multixact_failsafe_age',
    'autovacuum_max_workers',
    'autovacuum_naptime',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit'
)
ORDER BY name;
```

Nếu một setting không tồn tại trên phiên bản PostgreSQL hiện tại, filter name IN (...) chỉ đơn giản không trả row cho setting đó.

## 15. Tìm relation đang giữ XID age cao

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
    c.reloptions
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
  AND c.relfrozenxid <> '0'::xid
ORDER BY age(c.relfrozenxid) DESC
LIMIT 50;
```

### 15.1. Bao gồm TOAST tables

TOAST relation cũng có tuple metadata và có thể liên quan đến vacuum/freeze. `relkind = 't'` giúp phát hiện những relations này.

### 15.2. Partitioned parent

Partitioned table parent thường không có heap storage như ordinary table. Cần xem từng partition thực sự chứa tuples; đừng chỉ kiểm tra parent và kết luận toàn partition tree an toàn.

### 15.3. System catalogs

System catalogs cũng phải được vacuum/freeze. Không loại chúng khỏi điều tra chỉ vì chúng nằm trong pg_catalog; catalog age có thể quan trọng trong sự cố.

### 15.4. Database age bị giữ bởi một relation

Một relation có tuổi rất cao có thể giữ `datfrozenxid` của database lại. Query top relations giúp tìm nơi cần điều tra, nhưng phải xét cả vacuum horizon và relation type.

## 16. Tìm transactions giữ horizon

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 16.1. Tập trung vào transaction lâu nhất

Kiểm tra owner, application, trạng thái, query và lý do transaction chưa kết thúc. Không terminate chỉ vì age cao; một transaction có thể là migration hoặc maintenance hợp lệ cần được xử lý theo runbook.

### 16.2. Read-only transaction vẫn quan trọng

Một transaction không UPDATE/DELETE vẫn có thể giữ snapshot cũ và cản vacuum. Đừng chỉ tìm các sessions có câu lệnh ghi.

### 16.3. Idle in transaction

```sql
SELECT
    pid,
    usename,
    application_name,
    clock_timestamp() - xact_start AS xact_age,
    state_change,
    clock_timestamp() - state_change AS idle_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state = 'idle in transaction'
ORDER BY xact_start;
```

`state_change` cho biết thời điểm backend chuyển sang state hiện tại. Transaction age và idle age là hai số khác nhau.

### 16.4. Prepared transactions

```sql
SELECT
    transaction,
    gid,
    prepared,
    clock_timestamp() - prepared AS prepared_age,
    owner,
    database,
    age(transaction) AS xid_age
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

Chỉ resolve prepared transaction sau khi xác minh với transaction coordinator và business owner. `COMMIT PREPARED` hoặc `ROLLBACK PREPARED` là quyết định nghiệp vụ/transaction, không phải thao tác dọn dẹp tùy tiện.

## 17. Kiểm tra replication slots và standby feedback

### 17.1. Replication slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL
        THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Một slot không nhất thiết giữ cả hai mốc. Kiểm tra loại slot, consumer và state.

### 17.2. Standby feedback

```sql
SHOW hot_standby_feedback;

SELECT
    application_name,
    state,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS backend_xmin_age,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

Nếu replica giữ snapshot cũ, feedback có thể truyền xmin về primary. Theo dõi cả query lâu trên replica và vacuum progress trên primary.

### 17.3. Slot inactive lâu ngày

Slot inactive không nhất thiết vô dụng. Có thể là logical subscriber tạm dừng, backup workflow hoặc replica đang offline. Xác định owner và recovery plan trước khi drop.

### 17.4. WAL retention khác XID horizon

`restart_lsn` giữ WAL để logical decoding/replication tiếp tục. `xmin`/`catalog_xmin` có thể giữ tuple/catalog visibility horizon. Hai loại retention liên quan nhưng không đồng nhất.

## 18. Theo dõi VACUUM đang chạy

```sql
SELECT
    p.pid,
    a.datname,
    a.application_name,
    n.nspname,
    c.relname,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    round(
        100.0 * p.heap_blks_scanned
        / NULLIF(p.heap_blks_total, 0),
        1
    ) AS scanned_pct,
    a.wait_event_type,
    a.wait_event,
    clock_timestamp() - a.query_start AS runtime
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
LEFT JOIN pg_catalog.pg_class AS c
  ON c.oid = p.relid
LEFT JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
ORDER BY a.query_start;
```

### 18.1. Phase

Progress view cung cấp các phase như scanning heap, vacuuming indexes và cleaning up indexes. Tên/chi tiết phase phụ thuộc phiên bản PostgreSQL.

### 18.2. Scanned percent không phải percent freeze hoàn thành

Một vacuum có thể scan nhiều pages nhưng vẫn bị horizon blockers hoặc pages cần retry. Dùng age trước/sau, logs và kết quả VACUUM để đánh giá tiến triển.

### 18.3. Autovacuum worker

Có thể lọc `pg_stat_activity` theo `backend_type` hoặc application/query tương ứng để nhận diện autovacuum worker. Cần kiểm tra cột có sẵn theo phiên bản.

### 18.4. VACUUM statistics

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_user_tables
ORDER BY last_autovacuum NULLS FIRST;
```

Đây là statistics cho hoạt động vacuum/dead tuples; không thay thế `age(relfrozenxid)`.

## 19. Autovacuum cleanup threshold và freeze threshold

Một nhầm lẫn phổ biến là nghĩ autovacuum chỉ chạy khi dead tuple count vượt ngưỡng.

### 19.1. Dead tuple trigger

Autovacuum vacuum thông thường có thể được kích hoạt theo công thức gần dạng:

```text
threshold =
    autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * reltuples
```

Đây là cơ chế cleanup dựa trên số dead tuples ước lượng.

### 19.2. Freeze trigger

Anti-wraparound vacuum được kích hoạt theo tuổi `relfrozenxid` hoặc MultiXact age. Một bảng append-only ít UPDATE/DELETE vẫn có thể cần vacuum freeze.

### 19.3. Bảng insert-only

Bảng chỉ INSERT có thể ít dead tuples nhưng XID age của các tuples cũ vẫn tăng. Freeze không được bỏ qua chỉ vì bảng ít UPDATE/DELETE.

### 19.4. Autovacuum per-table settings

Có thể điều chỉnh các reloptions như scale factor/threshold, nhưng không được vô tình đặt cấu hình khiến relation không thể được vacuum đúng hạn. Luôn xem `reloptions` và cấu hình hiệu lực trước khi kết luận.

## 20. Vì sao autovacuum không theo kịp?

Các nguyên nhân phổ biến:

- `autovacuum_max_workers` quá thấp so với số bảng/throughput.
- Vacuum cost delay/limit khiến tiến độ quá chậm.
- I/O bị giới hạn hoặc storage latency cao.
- Một bảng rất lớn cần aggressive scan.
- Long-running transactions giữ old xmin.
- Replication slot hoặc standby feedback giữ horizon.
- Prepared transactions chưa được resolve.
- Autovacuum bị tắt hoặc reloptions không hợp lý.
- Worker liên tục bị cancel bởi maintenance/deploy.
- Database có nhiều relations nhỏ hoặc catalogs lớn.
- Table churn/transaction rate vượt capacity vacuum.

### 20.1. Không chỉ tăng worker count

Thêm workers có thể tăng I/O/CPU contention. Cần xem vacuum throughput, database workload và storage headroom.

### 20.2. Tăng cost limit có thể hữu ích

`autovacuum_vacuum_cost_limit` và `autovacuum_vacuum_cost_delay` điều khiển tốc độ vacuum thông thường theo cost model. Điều chỉnh cần theo tải và quan sát; không phải một con số cố định cho mọi cluster.

### 20.3. Anti-wraparound cần được ưu tiên

Nếu age tiến gần ngưỡng, có thể cần dành capacity cho vacuum, giảm write traffic hoặc tạm dừng workload không thiết yếu để worker hoàn tất.

### 20.4. Đừng cancel autovacuum chỉ vì thấy I/O tăng

Nếu worker là anti-wraparound vacuum, cancel nó có thể làm tình hình nguy hiểm hơn. Xác định relation, age và lý do trước khi can thiệp.

## 21. Thực hành VACUUM FREEZE và xác minh kết quả

### 21.1. Chạy riêng lệnh VACUUM

```sql
VACUUM (FREEZE, VERBOSE) vacuum_lab.events;
```

Lệnh này cần chạy ngoài explicit transaction block.

### 21.2. So sánh tuổi trước và sau

```sql
SELECT
    c.oid::regclass AS relation,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age,
    c.relminmxid,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'vacuum_lab.events'::regclass;
```

Đọc log verbose để biết vacuum scan/freeze đã làm gì. Với bảng nhỏ, tuổi có thể rất thấp; điều đó không chứng minh hệ thống production không có vấn đề.

### 21.3. Freeze không nhất thiết làm age bằng 0

Mốc mới phải tôn trọng các transaction/snapshot đang tồn tại và phạm vi relation. Nếu một transaction cũ giữ horizon, VACUUM có thể không tiến mốc như mong đợi.

### 21.4. Xem visibility map

Nếu extension `pg_visibility` có sẵn và được cài, các hàm của nó có thể hỗ trợ kiểm tra page visibility/all-frozen. Đây là công cụ bổ trợ; không cần cài extension trên production chỉ để chạy một query monitoring đơn giản.

### 21.5. Không tự chỉnh system catalogs

Không UPDATE trực tiếp `pg_class.relfrozenxid`, `pg_database.datfrozenxid`, tuple `xmin` hoặc transaction status files. Các giá trị này phải được quản lý bởi PostgreSQL VACUUM/transaction machinery.

## 22. Quy trình xử lý cảnh báo wraparound

Khi log báo database cần vacuum trong số transactions còn lại, coi đây là sự cố có mức ưu tiên cao.

### Bước 1. Đánh giá age toàn cluster

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY age(datfrozenxid) DESC;
```

Xác định database nào có age cao nhất và có xu hướng tăng nhanh.

### Bước 2. Tìm relations già nhất trong database đó

Chạy query `pg_class` theo `age(relfrozenxid)` và `mxid_age(relminmxid)`. Kiểm tra cả user tables, TOAST và system catalogs.

### Bước 3. Tìm horizon blockers

Kiểm tra:

- `pg_stat_activity` và transaction age.
- `idle in transaction`.
- `pg_prepared_xacts`.
- `pg_replication_slots`.
- `pg_stat_replication.backend_xmin`.
- Snapshot/exported snapshot workflows.
- Logs của autovacuum và replication.

### Bước 4. Cho vacuum cơ hội hoàn tất

Xác minh autovacuum được bật, workers hoạt động, disk/WAL/storage còn đủ, và không có job khác liên tục cancel workers.

### Bước 5. Giảm blocker có kiểm soát

Yêu cầu application kết thúc transaction cũ. Resolve prepared transaction qua coordinator. Xử lý slot/replica theo recovery plan. Chỉ terminate backend sau khi xác minh owner, PID và business impact.

### Bước 6. Chạy VACUUM thủ công nếu cần

Trong database bị ảnh hưởng, với quyền phù hợp và capacity đã được đánh giá:

```sql
VACUUM (FREEZE, VERBOSE) vacuum_lab.events;
```

Đây chỉ là ví dụ với bảng lab. Trong production phải vacuum đúng relations đang giữ age, theo kế hoạch có thể bao gồm cả catalogs và TOAST. `VACUUM` không thể chạy trong transaction block.

Với nhiều database, công cụ `vacuumdb` có thể chạy trên nhiều databases:

```bash
vacuumdb --all --freeze --jobs=2 --verbose
```

Số jobs chỉ là ví dụ. Chọn concurrency theo I/O/CPU và workload; không chạy hàng chục workers vô điều kiện.

### Bước 7. Theo dõi age tiến lên

Chạy lại age queries và progress view. Xác minh `datfrozenxid`/`relfrozenxid` thực sự tiến lên và cảnh báo giảm. Không chỉ kiểm tra lệnh VACUUM đã trả exit code 0.

### Bước 8. Khôi phục workload dần dần

Khi safety margin đã phục hồi, đưa write traffic trở lại theo capacity, tiếp tục theo dõi age, autovacuum duration và replication lag.

### Bước 9. Tìm nguyên nhân gốc

Điều chỉnh transaction lifetime, slot retention, autovacuum capacity, per-table settings, alert thresholds và runbook. Không chỉ xử lý một bảng rồi bỏ qua nguyên nhân khiến vacuum bị chặn.

## 23. Khi database đã vào vùng từ chối transaction

PostgreSQL có cơ chế ngăn cấp phát XID mới khi sắp chạm vùng nguy hiểm. Khi database từ chối commands để tránh wraparound, việc vận hành bình thường có thể không còn thực hiện được.

### 23.1. Không reset XID counter

Không dùng các thủ thuật chỉnh pg_control, sửa catalog hoặc thay transaction ID bằng tay. Những thao tác đó có thể làm hỏng visibility và khiến dữ liệu không thể tin cậy.

### 23.2. Dùng maintenance procedure theo major version

Nếu database không còn nhận transactions cần thiết để vacuum, DBA có thể phải dùng quy trình recovery chuyên biệt, chẳng hạn single-user mode trong điều kiện phù hợp. Cú pháp và các bước phải theo tài liệu của đúng major version, có bản backup/snapshot và người có kinh nghiệm PostgreSQL.

### 23.3. Không xóa dữ liệu để giảm tuổi

DELETE rows không giải quyết vấn đề nếu XIDs cũ chưa được freeze; DELETE còn tạo thêm transaction metadata và dead tuples. VACUUM freeze mới là cơ chế xử lý XID horizon.

### 23.4. Không drop database/table cũ một cách mù quáng

Drop một relation có thể loại bỏ một XID horizon blocker nếu đúng object, nhưng có thể phá dữ liệu và không giải quyết các blockers khác. Chỉ làm sau khi xác định ownership, backup và dependency.

### 23.5. Sau recovery

Xác minh database age, relation age, autovacuum status, logs và khả năng tạo transaction mới. Chạy kiểm tra integrity theo runbook trước khi coi hệ thống hoạt động bình thường.

## 24. Bảng có tuổi cao nhưng ít dead tuples

Đây là trường hợp dễ bị hiểu nhầm.

### 24.1. Append-only table

Một bảng log chỉ INSERT có thể có gần như không có dead tuples. Nhưng những rows cũ vẫn giữ xmin từ nhiều tháng trước. Chúng cần được freeze để XID counter có thể tiếp tục quay vòng an toàn.

### 24.2. VACUUM FREEZE không chỉ dành cho bảng UPDATE nhiều

Chính bảng ít thay đổi có thể cần freeze định kỳ. Không dùng `n_dead_tup = 0` làm lý do bỏ qua freeze.

### 24.3. Partitioned tables

Nếu partition theo ngày/tháng, partitions cũ có thể ít write và dễ freeze. Tuy nhiên, parent partitioned table không đại diện cho mọi heap partition. Theo dõi từng partition và TOAST relation.

### 24.4. Read-only archival tables

Bảng archive có thể được vacuum freeze trước khi chuyển sang read-only storage/workload. Việc freeze giúp giảm phụ thuộc vào trạng thái XID cũ, nhưng cần retention và restore plan riêng.

## 25. Freeze và transaction age trong môi trường replication

### 25.1. Physical replication

Primary và standby cần nhất quán về WAL/transaction history. Vacuum cleanup có thể gây conflict với queries trên standby. Hot standby feedback có thể giữ xmin ở primary và làm chậm cleanup/freezing.

### 25.2. Logical replication

Logical decoding cần giữ thông tin catalog và tuple theo slot horizon. Slot inactive lâu có thể giữ `catalog_xmin`/`xmin`, khiến primary không thể reclaim dữ liệu cũ.

### 25.3. Replica lag

Replica lag không đồng nghĩa trực tiếp XID age cao. Nhưng lag và slots có thể kéo dài retention, làm tăng disk usage hoặc giữ vacuum horizon. Theo dõi cả replication progress lẫn age.

### 25.4. Slot không active nhưng còn tồn tại

Một logical slot có thể giữ catalog xmin dù subscriber đã ngừng. Xác minh subscriber và khả năng resync trước khi drop.

### 25.5. Logical slot failover

Các phiên bản PostgreSQL mới có thêm tính năng liên quan failover logical slots; chi tiết phụ thuộc major version. Không áp dụng lệnh quản lý slot theo một ví dụ chung mà chưa xác minh version/config.

## 26. Multixact monitoring và vận hành

### 26.1. Database-level MXID age

```sql
SELECT
    datname,
    mxid_age(datminmxid) AS mxid_age
FROM pg_catalog.pg_database
ORDER BY mxid_age(datminmxid) DESC;
```

### 26.2. Relation-level MXID age

```sql
SELECT
    n.nspname,
    c.relname,
    mxid_age(c.relminmxid) AS mxid_age,
    age(c.relfrozenxid) AS xid_age
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY mxid_age(c.relminmxid) DESC
LIMIT 50;
```

### 26.3. Vì sao MXID có ngưỡng khác XID?

MultiXacts được tạo theo các tình huống row locking và có lifecycle/retention riêng. `autovacuum_multixact_freeze_max_age` thường có default khác `autovacuum_freeze_max_age`; không copy threshold XID sang MXID.

### 26.4. Workload row locking

Nếu workload có nhiều transactions cùng lock một row hoặc lock nhiều rows đồng thời, xem xét transaction duration, lock modes và contention. Giảm thời gian giữ locks có thể giảm áp lực MultiXact.

## 27. Điều chỉnh autovacuum capacity

Khi vacuum không theo kịp, cần đo và điều chỉnh nhiều yếu tố.

### 27.1. autovacuum_max_workers

Giới hạn số autovacuum workers có thể chạy đồng thời. Tăng workers có thể cải thiện throughput nếu CPU/I/O còn headroom; quá nhiều workers gây contention.

### 27.2. autovacuum_naptime

Khoảng thời gian launcher kiểm tra databases. Giá trị nhỏ có thể phát hiện công việc sớm hơn nhưng tăng scheduling activity.

### 27.3. Cost-based delay và limit

```sql
SHOW autovacuum_vacuum_cost_delay;
SHOW autovacuum_vacuum_cost_limit;
SHOW vacuum_cost_delay;
SHOW vacuum_cost_limit;
```

Các setting này ảnh hưởng tốc độ vacuum thông thường. Failsafe có thể bỏ qua một số throttling để ưu tiên wraparound protection.

### 27.4. autovacuum_work_mem

Giới hạn memory cho vacuum worker theo cấu hình liên quan. Index cleanup có thể cần memory; quá thấp có thể tăng số vòng xử lý index. Điều chỉnh phải theo workload và memory budget.

### 27.5. Table reloptions

Có thể có per-table settings cho autovacuum threshold/scale factors và freeze parameters. Xem:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.reloptions IS NOT NULL
ORDER BY c.oid::regclass::text;
```

Không sao chép một cấu hình table-specific lên mọi bảng mà không xét kích thước, tốc độ ghi và SLA.

### 27.6. Tăng autovacuum_freeze_max_age không phải giải pháp capacity

Nếu workers không theo kịp, tăng ngưỡng chỉ trì hoãn thời điểm cần xử lý và có thể tăng storage/risks. Trước tiên xử lý blockers và throughput.

## 28. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| VACUUM chỉ xóa dead rows | VACUUM còn freeze XIDs và tiến horizon |
| Bảng không UPDATE thì không cần VACUUM | Append-only rows vẫn cần freeze |
| n_dead_tup thấp nghĩa XID age thấp | Hai chỉ số khác nhau |
| XID là số 64-bit tăng vô hạn | Tuple XIDs thông thường là 32-bit |
| Có thể so XID bằng MAX | Dùng age() vì wraparound-aware semantics |
| Frozen tuple không thể UPDATE | Tuple vẫn có thể có version mới |
| FREEZE giống VACUUM FULL | FREEZE không đồng nghĩa rewrite/ACCESS EXCLUSIVE |
| Autovacuum chỉ chạy khi nhiều dead tuples | Anti-wraparound dựa trên XID/MXID age |
| Tắt autovacuum là tắt mọi anti-wraparound worker | PostgreSQL vẫn có bảo vệ anti-wraparound cần thiết |
| VACUUM FREEZE luôn làm age bằng 0 | Horizon blockers có thể ngăn tiến mốc |
| Database age cho biết chính xác bảng nào chậm | Cần relation-level age query |
| Chỉ cần xem XID age | MultiXact age cũng cần giám sát |
| Idle transaction không ảnh hưởng vacuum | Snapshot cũ có thể giữ horizon |
| Read-only transaction không quan trọng | Nó vẫn có thể giữ snapshot |
| Drop replication slot luôn an toàn | Có thể làm subscriber/replica cần resync |
| Tăng freeze_max_age là hết warning | Chỉ trì hoãn, giảm safety margin |
| VACUUM FULL là cách chữa wraparound | Không; regular VACUUM FREEZE là cơ chế phù hợp |
| DELETE hết dữ liệu cũ sẽ giải quyết | DELETE không thay freezing |
| Progress 100% nghĩa age chắc đã tiến | Phải kiểm tra mốc sau vacuum |
| Một database vacuum xong là cả cluster an toàn | Mỗi database có datfrozenxid riêng |
| Partition parent là đủ để theo dõi | Phải xem heap partitions và TOAST |
| Failsafe là kế hoạch vận hành bình thường | Failsafe là safety mechanism cuối |
| Một transaction mở lâu chỉ ảnh hưởng row lock | Nó còn giữ visibility horizon |
| WAL slot retention và xmin retention giống nhau | restart_lsn khác xmin/catalog_xmin |
| Số worker càng nhiều càng tốt | I/O/CPU contention có thể tăng |
| VACUUM có thể chạy trong BEGIN | VACUUM không chạy trong transaction block thông thường |
| Tự sửa relfrozenxid sẽ nhanh hơn | Có thể phá database; chỉ VACUUM machinery được quản lý mốc |
| XID counter reset là cách xử lý | Tuyệt đối không reset thủ công |

## 29. Bài tập thực hành có đáp án

Các bài tập sử dụng PostgreSQL lab và catalog views. Chạy lệnh VACUUM độc lập, không đặt trong transaction block.

### Bài 1. Vì sao cần freezing?

**Đáp án:** XID 32-bit sẽ wraparound; freeze đánh dấu tuple cũ để PostgreSQL không cần diễn giải XID cũ như transaction mới sau khi counter quay vòng.

### Bài 2. XID thông thường có độ rộng bao nhiêu?

**Đáp án:** 32-bit.

### Bài 3. Nửa không gian XID là bao nhiêu?

**Đáp án:** `2^31`, tức 2,147,483,648; đây là giới hạn an toàn quan trọng cho so sánh XID.

### Bài 4. FrozenTransactionId có giá trị đặc biệt nào?

**Đáp án:** XID 2.

### Bài 5. xmin của tuple biểu diễn gì?

**Đáp án:** Transaction ID tạo tuple version đó.

### Bài 6. xmax luôn là transaction xóa row?

**Đáp án:** không. Nó có thể liên quan delete/update hoặc row-lock metadata, gồm MultiXact trong các trường hợp phù hợp.

### Bài 7. Freeze có làm row bất biến?

**Đáp án:** không. Tuple vẫn có thể được UPDATE/DELETE; freezing chỉ thay đổi cách diễn giải transaction metadata cũ.

### Bài 8. XID age xem bằng hàm nào?

```sql
SELECT age(datfrozenxid)
FROM pg_catalog.pg_database
WHERE datname = current_database();
```

**Đáp án:** `age(xid)`.

### Bài 9. Vì sao không dùng MAX(relfrozenxid)?

**Đáp án:** XID quay vòng nên so sánh số học thông thường không thể xác định tuổi đúng.

### Bài 10. relfrozenxid nằm ở catalog nào?

**Đáp án:** `pg_class`.

### Bài 11. datfrozenxid nằm ở đâu?

**Đáp án:** `pg_database`.

### Bài 12. relminmxid theo dõi gì?

**Đáp án:** MultiXact ID cũ nhất relation còn có thể cần.

### Bài 13. datminmxid theo dõi gì?

**Đáp án:** MultiXact ID cũ nhất ở cấp database.

### Bài 14. Hàm đo MXID age?

**Đáp án:** `mxid_age()`.

### Bài 15. Vì sao XID age thấp nhưng vẫn cần xem MXID age?

**Đáp án:** MultiXacts có counter và freeze lifecycle riêng, có thể tiến nhanh theo row-lock workload.

### Bài 16. vacuum_freeze_min_age có vai trò gì?

**Đáp án:** ngưỡng tuổi để VACUUM cân nhắc freeze tuples.

### Bài 17. vacuum_freeze_table_age có vai trò gì?

**Đáp án:** ngưỡng kích hoạt aggressive scan relation để tiến freeze horizon.

### Bài 18. autovacuum_freeze_max_age có vai trò gì?

**Đáp án:** tuổi relation khiến anti-wraparound autovacuum được yêu cầu.

### Bài 19. Giá trị mặc định phổ biến của autovacuum_freeze_max_age?

**Đáp án:** khoảng 200 triệu XIDs, nhưng phải kiểm tra cấu hình và phiên bản thực tế.

### Bài 20. Có nên tăng freeze_max_age khi vacuum chậm?

**Đáp án:** không xem đó là cách chữa mặc định; nó trì hoãn vacuum và làm giảm safety margin, đồng thời tăng transaction status retention.

### Bài 21. Append-only table có cần freeze?

**Đáp án:** có. Tuples cũ vẫn giữ XIDs cũ dù không có dead tuples.

### Bài 22. n_dead_tup = 0 chứng minh bảng đã freeze chưa?

**Đáp án:** không. Đây là ước lượng dead tuples, không phải XID age/freeze status.

### Bài 23. All-visible và all-frozen khác nhau?

**Đáp án:** all-frozen là trạng thái mạnh hơn; all-visible không tự chứng minh mọi XID đã freeze.

### Bài 24. Aggressive vacuum làm gì?

**Đáp án:** scan các pages có thể còn XIDs chưa freeze để tiến relfrozenxid, kể cả pages chỉ all-visible nhưng chưa all-frozen.

### Bài 25. VACUUM (FREEZE) có tương đương VACUUM FULL?

**Đáp án:** không. FREEZE yêu cầu freezing mạnh hơn; FULL rewrite table và cần lock mạnh.

### Bài 26. VACUUM có chạy trong explicit transaction block không?

**Đáp án:** không, chạy VACUUM như statement độc lập.

### Bài 27. VACUUM thường có freeze tuple không?

**Đáp án:** có, theo freeze age settings và điều kiện visibility.

### Bài 28. Anti-wraparound vacuum có phụ thuộc dead tuple count?

**Đáp án:** không. Nó dựa trên transaction/MultiXact age.

### Bài 29. PostgreSQL có khởi chạy anti-wraparound worker khi autovacuum setting bị disable không?

**Đáp án:** PostgreSQL vẫn có cơ chế khởi chạy vacuum cần thiết để ngăn wraparound; tắt autovacuum thông thường vẫn rất nguy hiểm.

### Bài 30. Failsafe vacuum nhằm mục đích gì?

**Đáp án:** ưu tiên hoàn tất freezing khi age đã rất cao, có thể giảm throttling và bỏ qua index cleanup.

### Bài 31. Một long-running read-only transaction có thể cản VACUUM không?

**Đáp án:** có. Snapshot cũ có thể giữ vacuum horizon dù transaction không ghi dữ liệu.

### Bài 32. idle in transaction nguy hiểm vì sao?

**Đáp án:** giữ transaction/snapshot/locks trong khi application không làm việc hữu ích, cản cleanup/freezing.

### Bài 33. Prepared transaction có thể giữ horizon không?

**Đáp án:** có. Nó giữ transaction state/locks cho đến khi được commit hoặc rollback prepared.

### Bài 34. Replication slot có field nào liên quan XID horizon?

**Đáp án:** `xmin` và `catalog_xmin`; `restart_lsn` là WAL retention marker khác.

### Bài 35. hot_standby_feedback có thể ảnh hưởng primary thế nào?

**Đáp án:** standby gửi xmin về primary, có thể giữ vacuum horizon và làm chậm cleanup/freezing.

### Bài 36. Query tìm database age cao nhất?

```sql
SELECT datname, age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

**Đáp án:** sắp xếp theo `age(datfrozenxid)` giảm dần.

### Bài 37. Query tìm relation age cao nhất dùng catalog nào?

**Đáp án:** `pg_class` join `pg_namespace`, sắp xếp `age(relfrozenxid)`.

### Bài 38. Vì sao phải xem TOAST relations?

**Đáp án:** TOAST là relation lưu tuple data phụ và cũng có XID/MultiXact metadata cần được vacuum/freeze.

### Bài 39. Partition parent có đủ đại diện cho partition tree?

**Đáp án:** không. Cần xem từng heap partition và TOAST relation có storage.

### Bài 40. pg_stat_progress_vacuum giúp gì?

**Đáp án:** theo dõi PID, relation, phase và tiến độ heap/index của vacuum đang chạy.

### Bài 41. n_dead_tup và age(relfrozenxid) khác nhau?

**Đáp án:** một bên ước lượng dead tuples; bên kia đo tuổi XID freeze horizon.

### Bài 42. Vì sao không cancel anti-wraparound vacuum vì I/O tăng?

**Đáp án:** có thể làm age tiếp tục tiến gần vùng nguy hiểm; cần xác minh worker và capacity trước khi can thiệp.

### Bài 43. Có thể sửa trực tiếp pg_class.relfrozenxid không?

**Đáp án:** không. Chỉ PostgreSQL VACUUM/transaction machinery được quản lý các mốc này.

### Bài 44. DELETE hết rows cũ có thay freezing không?

**Đáp án:** không. DELETE tạo transaction metadata và dead tuples; cần VACUUM freeze đúng cách.

### Bài 45. Nếu một batch import tạo XID age nhanh, nên xem gì?

**Đáp án:** write throughput, transaction rate, autovacuum progress, long snapshots, replication slots và freeze thresholds.

### Bài 46. Vì sao một relation lớn cần aggressive scan có thể mất lâu?

**Đáp án:** VACUUM phải đọc nhiều heap pages để xác định/freeze các tuples còn giữ XID cũ.

### Bài 47. vacuumdb --all --freeze có thể giúp gì?

**Đáp án:** yêu cầu freeze vacuum trên nhiều databases; cần chọn concurrency hợp lý và xác minh từng database sau chạy.

### Bài 48. Vì sao không drop slot inactive ngay?

**Đáp án:** slot có thể thuộc subscriber/replica cần resync; xác minh owner, retention và recovery plan trước.

### Bài 49. Khi age cao, nên kiểm tra những blockers nào trước?

**Đáp án:** long transactions, idle-in-transaction, prepared xacts, replication slots và standby feedback.

### Bài 50. Khi database từ chối transactions vì wraparound, có nên reset counter thủ công?

**Đáp án:** tuyệt đối không. Dùng recovery procedure theo đúng PostgreSQL major version và DBA chuyên môn.

### Bài 51. VACUUM FREEZE có bảo đảm age bằng 0 không?

**Đáp án:** không. Transaction horizons và các điều kiện visibility có thể giữ mốc lại.

### Bài 52. Vì sao autovacuum_max_workers quá thấp có thể gây vấn đề?

**Đáp án:** nhiều relations cần vacuum cạnh tranh worker slots, làm anti-wraparound work không theo kịp.

### Bài 53. Tăng workers luôn tốt?

**Đáp án:** không. Cần I/O/CPU capacity; quá nhiều workers có thể gây contention.

### Bài 54. Failsafe có thay thế monitoring không?

**Đáp án:** không. Failsafe là lớp bảo vệ cuối; monitoring phải phát hiện age tăng từ sớm.

### Bài 55. Một database đã vacuum xong có nghĩa mọi database trong cluster an toàn?

**Đáp án:** không. Mỗi database có datfrozenxid/datminmxid riêng; cần giám sát tất cả.

### Bài 56. MultiXact thường phát sinh trong workload nào?

**Đáp án:** nhiều transactions cùng giữ row locks, ví dụ các câu lệnh SELECT FOR UPDATE/SHARE và concurrent locking.

### Bài 57. VACUUM FULL có thể gây vấn đề gì khi dùng để chữa wraparound?

**Đáp án:** rewrite nặng và ACCESS EXCLUSIVE lock; không phải cách xử lý freeze horizon phù hợp.

### Bài 58. Cần theo dõi metric nào trong alert?

**Đáp án:** database XID age, MXID age, phần trăm ngưỡng freeze, oldest relation age, vacuum progress, blockers, slot xmin/catalog_xmin và thời gian autovacuum.

### Bài 59. Sau khi vacuum thủ công, kiểm tra gì?

**Đáp án:** age database/relation có tiến lên, worker/log hoàn tất, blockers đã hết và warning không còn tăng.

### Bài 60. Lập checklist xử lý anti-wraparound warning

**Đáp án gợi ý:**

1. Xếp hạng tất cả databases theo `age(datfrozenxid)` và `mxid_age(datminmxid)`.
2. Tìm relations/TOAST/catalogs có age cao nhất.
3. Kiểm tra autovacuum workers và `pg_stat_progress_vacuum`.
4. Tìm long transactions, idle-in-transaction và prepared transactions.
5. Kiểm tra `pg_replication_slots.xmin/catalog_xmin` và standby feedback.
6. Bảo đảm storage/I/O/capacity đủ cho aggressive vacuum.
7. Không cancel anti-wraparound workers nếu chưa hiểu hậu quả.
8. Chạy VACUUM FREEZE có kế hoạch trên relations/database cần thiết.
9. Xác minh age đã giảm và mọi databases đều trong safety margin.
10. Xử lý root cause, alert và runbook để ngăn tái diễn.

## 30. Checklist vận hành production

| Kiểm tra | Điều cần bảo đảm |
| --- | --- |
| XID age mọi database? | Có dashboard/alert |
| MXID age mọi database? | Có dashboard/alert riêng |
| Relation age? | Có query top oldest relations |
| TOAST relation age? | Được bao gồm |
| System catalog age? | Được giám sát |
| Freeze thresholds? | Đã xác minh theo version |
| Autovacuum enabled? | Có |
| Anti-wraparound worker logs? | Có theo dõi |
| Autovacuum workers capacity? | Đủ với throughput |
| Vacuum cost settings? | Phù hợp storage |
| Failsafe age? | Được hiểu, không dùng làm mục tiêu |
| Long transactions? | Alert theo age |
| Idle in transaction? | Có timeout/monitoring |
| Prepared transactions? | Có owner/runbook |
| Replication slots? | Theo dõi active, xmin, catalog_xmin |
| Standby feedback? | Đánh giá horizon impact |
| Partitioned tables? | Theo dõi từng partition |
| Append-only tables? | Vẫn được freeze |
| Table reloptions? | Được kiểm tra |
| Manual VACUUM plan? | Có runbook |
| VACUUM FULL? | Không dùng thay freeze |
| Recovery procedure? | Theo major version |
| System catalog modification? | Cấm sửa thủ công |
| Age sau vacuum? | Có xác minh |
| Storage headroom? | Đủ cho vacuum/WAL |
| Write rate? | Có trend XID allocation |
| MultiXact workload? | Có monitoring |
| Replication lag? | Có theo dõi cùng slot horizon |
| Incident response? | Có người chịu trách nhiệm |
| Backup/restore? | Có kiểm thử recovery |

## 31. Tổng kết

Freezing là cơ chế giúp PostgreSQL tiếp tục diễn giải tuple visibility chính xác khi transaction ID 32-bit quay vòng. VACUUM vì vậy không chỉ phục vụ reclaim dead tuples mà còn bảo vệ tính đúng đắn của toàn database.

Những nguyên tắc cần nhớ:

1. **XID thông thường có 32-bit.** Wraparound là giới hạn thiết kế phải xử lý bằng freezing.
2. **Tuple xmin/xmax chứa transaction metadata.** Không tự sửa system columns.
3. **FrozenTransactionId đánh dấu tuple đã được freeze.** Tuple vẫn có thể được cập nhật sau đó.
4. **relfrozenxid và datfrozenxid là mốc quan trọng.** Dùng `age()` để đo tuổi, không so XID bằng số học thông thường.
5. **MultiXact có vòng đời riêng.** Theo dõi `relminmxid`, `datminmxid` và `mxid_age()`.
6. **Freeze age, aggressive scan age và anti-wraparound age khác nhau.** Hiểu từng setting trước khi tuning.
7. **Bảng append-only vẫn phải freeze.** Dead tuple count thấp không chứng minh XID age an toàn.
8. **All-visible không đồng nghĩa all-frozen.** Aggressive vacuum cần tìm mọi page có thể còn XID chưa freeze.
9. **VACUUM FREEZE khác VACUUM FULL.** Không dùng rewrite/ACCESS EXCLUSIVE lock để thay thế freeze.
10. **Anti-wraparound autovacuum là cơ chế bảo vệ quan trọng.** Không tắt hoặc cancel một cách tùy tiện.
11. **Failsafe là lớp bảo vệ cuối.** Monitoring và capacity phải giúp vacuum hoàn tất trước ngưỡng đó.
12. **Long transactions và replication horizons có thể chặn freezing.** Kiểm tra pg_stat_activity, prepared transactions, slots và standby feedback.
13. **Xem relation age, không chỉ database age.** TOAST và system catalogs cũng cần được theo dõi.
14. **Không tăng freeze_max_age để che vacuum chậm.** Xử lý blockers, throughput và transaction lifetime.
15. **Không reset XID hoặc sửa catalog thủ công.** Khi đã vào vùng từ chối transaction, theo recovery procedure của đúng major version.
16. **Xác minh sau mỗi hành động.** Tuổi XID/MXID phải tiến lên và safety margin phải được phục hồi.

Mô hình điều tra:

```text
Database XID/MXID age tăng
          |
          v
Tìm relation già nhất
          |
          v
VACUUM có chạy và tiến triển?
          |
      +---+---+
      |       |
     Có      Không
      |       |
      v       v
Age có       Tìm blockers:
giảm?        transaction / slot /
      |      prepared xact / capacity
  +---+---+
  |       |
 Có      Không
  |       |
  v       v
Tiếp tục   Khắc phục blocker,
monitor    vacuum theo runbook
          |
          v
   Xác minh safety margin
```

**Câu hỏi review cuối cùng:** “Nếu một bảng gần như không có dead tuples nhưng age(relfrozenxid) vẫn tăng, hệ thống có nhận ra và freeze bảng đó không? Nếu autovacuum không thể tiến lên, chúng ta có tìm được transaction hoặc replication slot đang giữ horizon không? Và nếu database đã gần wraparound, runbook có bảo vệ dữ liệu mà không reset XID thủ công không?” Khi trả lời được các câu hỏi này bằng metrics, catalog queries và quy trình vận hành cụ thể, hệ thống mới có thể chống wraparound an toàn.
