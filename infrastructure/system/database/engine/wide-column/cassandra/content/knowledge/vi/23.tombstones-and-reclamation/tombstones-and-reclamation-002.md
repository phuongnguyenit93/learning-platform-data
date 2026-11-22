# Tombstone ở cấp cell, collection, hàng, khoảng hoặc phân vùng

Trong Apache Cassandra, một lệnh xóa có thể tác động đến **một giá trị cột**, **một phần tử collection**, **một hàng clustering**, **một dải hàng** hoặc **toàn bộ phân vùng**. Mỗi phạm vi có cách biểu diễn dấu xóa (*tombstone*) và hệ quả về đọc, compaction, repair khác nhau. Hiểu đúng **phạm vi của tombstone** giúp tránh hai nhầm lẫn phổ biến: nghĩ rằng `DELETE` luôn xóa vật lý ngay lập tức, hoặc cho rằng mọi thao tác xóa đều tạo một dấu xóa riêng cho từng hàng.

Cassandra là cơ sở dữ liệu **wide-column phân tán**, sử dụng partition key để phân phối dữ liệu tới các replica, clustering columns để tổ chức hàng bên trong partition, và kiến trúc lưu trữ LSM với memtable, SSTable cùng compaction. Khi một giá trị cũ vẫn còn trên SSTable hoặc replica chưa nhận xóa, tombstone với **write timestamp** giúp hệ thống nhận biết phiên bản cũ phải bị che đi. Việc **thu hồi vật lý** chỉ diễn ra khi các điều kiện an toàn được đáp ứng trong compaction.

Bài học thuộc chương **Tombstone và thu hồi** của module Apache Cassandra. Nội dung đi từ CQL đến cách biểu diễn và phạm vi xóa, rồi liên hệ với replication, consistency, compaction, repair, thiết kế partition key và ứng dụng Java.

Sau bài học, bạn có thể:

1. Phân biệt **cell tombstone**, **collection element tombstone**, **complex/collection deletion**, **row tombstone**, **range tombstone** và **partition tombstone**.
2. Giải thích khác biệt giữa **non-frozen collection** và **frozen collection** khi cập nhật hoặc xóa.
3. Dự đoán một câu `DELETE` ảnh hưởng đến giá trị nào dựa trên **partition key**, **clustering columns** và **static columns**.
4. Hiểu quan hệ giữa `NULL`, `UNSET`, TTL, write timestamp và các dấu xóa.
5. Giải thích vì sao range/partition deletion không đồng nghĩa tạo hàng triệu lệnh xóa riêng lẻ hoặc giải phóng dung lượng tức thì.
6. Quan sát dấu hiệu tombstone-heavy queries, chọn cách xóa phù hợp và thử nghiệm qua CQL/Java Driver 4.x.

## 1. Tombstone thuộc về một phạm vi logic

Một phân vùng của Cassandra có thể chứa dữ liệu thường (*regular columns*), dữ liệu tĩnh (*static columns*), nhiều hàng clustering và các collection nhiều phần tử.

```text
Partition key = (tenant='acme', sensor=S1, day=2026-11-21)
│
├── static note = "Ca sáng"
│
├── clustering key (08:00, E1)
│     ├── status = "ok"
│     ├── payload = "temperature=38.1"
│     └── metadata = {"unit":"C", "source":"edge"}
│
├── clustering key (08:05, E2)
│     ├── status = "ok"
│     └── payload = "temperature=38.4"
│
└── clustering key (08:10, E3)
      └── payload = "temperature=38.7"
```

Có thể muốn thực hiện sáu thao tác khác nhau:

- Xóa **chỉ `payload`** của E1.
- Xóa **chỉ phần tử `metadata['source']`** của E1.
- Xóa **toàn bộ collection `metadata`** của E1.
- Xóa **hàng E1** nhưng giữ E2, E3 và `note`.
- Xóa **tất cả hàng trong một đoạn thời gian**.
- Xóa **toàn partition ngày**, kể cả static data.

Những yêu cầu này khác nhau về **phạm vi mutation**. Cassandra có thể biểu diễn chúng bằng các dạng tombstone tương ứng, thay vì luôn duyệt và xóa từng byte đang lưu trên các SSTable.

| Phạm vi | Đơn vị dữ liệu bị che | Dạng biểu diễn thường gặp |
| --- | --- | --- |
| Một scalar value | Một cell trong một hàng | Cell tombstone |
| Một phần tử collection không `frozen` | Phần tử có key/index tương ứng | Element/cell tombstone |
| Toàn collection không `frozen` | Các phần tử cũ của collection | Complex/collection deletion |
| Một `frozen` collection | Một giá trị cell duy nhất | Cell tombstone |
| Một hàng clustering | Dữ liệu và dấu sống của hàng | Row deletion/tombstone |
| Một dải clustering | Các hàng trong khoảng được chỉ định | Range tombstone |
| Toàn partition | Hàng clustering và static data trong partition | Partition deletion/tombstone |

Tên của các loại tombstone phản ánh **mô hình lưu trữ**, không phải các câu lệnh CQL độc lập có tên y hệt. Chi tiết encoding có thể thay đổi theo định dạng SSTable và phiên bản Cassandra.

## 2. Bảng thực hành để phân biệt các loại xóa

Ta dùng một bảng có cả regular column, static column, non-frozen map và frozen map:

```sql
CREATE TABLE observations_by_sensor_day (
    tenant_id       text,
    sensor_id       uuid,
    event_day       date,
    observed_at     timestamp,
    observation_id  uuid,
    status          text,
    payload         text,
    attributes      map<text, text>,
    frozen_attrs    frozen<map<text, text>>,
    day_note        text STATIC,
    PRIMARY KEY (
        (tenant_id, sensor_id, event_day),
        observed_at,
        observation_id
    )
) WITH CLUSTERING ORDER BY (
    observed_at DESC,
    observation_id ASC
);
```

Giải thích cấu trúc:

| Cột | Vai trò |
| --- | --- |
| `(tenant_id, sensor_id, event_day)` | **Partition key ghép**, xác định phân vùng. |
| `observed_at`, `observation_id` | **Clustering columns**, xác định một hàng trong partition. |
| `status`, `payload` | Regular scalar columns. |
| `attributes` | Map **không frozen**, hỗ trợ thao tác trên phần tử. |
| `frozen_attrs` | Map **frozen**, được xử lý như một giá trị nguyên khối. |
| `day_note` | Static column, một giá trị chung của partition. |

Ví dụ khởi tạo ba sự kiện cùng partition:

```sql
INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id,
    status, payload, attributes, frozen_attrs
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'ok',
    'temperature=38.1',
    {'unit':'C', 'source':'edge'},
    {'location':'room-A'}
);

INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id, status, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:05:00Z',
    7c2c4f75-5c44-4be4-99a0-08688b465200,
    'ok',
    'temperature=38.4'
);

INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id, status, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T08:10:00Z',
    4e52e99a-178e-4d5b-9a31-027d5956e5b8,
    'ok',
    'temperature=38.7'
);
```

Ghi static data theo partition key:

```sql
UPDATE observations_by_sensor_day
SET day_note = 'Ca sáng'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

**Lưu ý thực hành:** những ví dụ DELETE sau đây dùng cùng partition để làm rõ sự khác biệt. Nếu muốn so sánh kết quả độc lập, hãy **khởi tạo lại dữ liệu mẫu hoặc dùng các partition keys thử nghiệm riêng** trước mỗi thí nghiệm; không chạy tất cả DELETE liên tiếp rồi mong quan sát được trạng thái ban đầu.

## 3. Cell tombstone: xóa đúng một giá trị cột

Một cell tombstone dùng để che giá trị cũ của một regular column. Ví dụ xóa `payload` của sự kiện E1 nhưng vẫn giữ `status` và `attributes`:

```sql
DELETE payload
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Truy vấn kiểm tra:

```sql
SELECT observed_at, observation_id, status, payload, attributes
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Ở trạng thái xóa đã được quan sát theo consistency level phù hợp, `payload` không còn giá trị hiện hành, trong khi `status` vẫn có thể là `'ok'` và `attributes` vẫn còn. **Cell deletion không tương đương row deletion.**

### Xóa một cột chưa có giá trị

Cassandra không cần kiểm tra trước rằng cell đang tồn tại rồi mới chấp nhận mutation xóa. Xóa một cell chưa có giá trị hiện hành vẫn có thể ghi tombstone để che một phiên bản cũ có thể đến muộn từ SSTable hoặc replica khác.

Điều đó giải thích vì sao một ứng dụng gửi hàng nghìn DELETE “để chắc chắn cột đã rỗng” có thể tạo dấu xóa mặc dù số hàng sống gần như không đổi.

### `NULL` cũng mang ngữ nghĩa xóa cell

```sql
UPDATE observations_by_sensor_day
SET payload = null
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

`payload = null` là yêu cầu xóa giá trị cột, không có nghĩa “bỏ qua cột này”. Cần phân biệt:

- **Cột bị bỏ qua** trong câu INSERT/UPDATE: không tự tạo tombstone vì sự vắng mặt ấy.
- **Bind `UNSET`** cho biến CQL được phép unset: không thực hiện mutation cho cột đó.
- **Ghi `NULL`**: mang ngữ nghĩa xóa giá trị cột, thường tạo cell tombstone.
- **Ghi chuỗi rỗng `''`** vào cột text: lưu một giá trị rỗng, không phải NULL.

Một `SELECT` trả `null` chỉ cho thấy ứng dụng không thấy giá trị sống; **không chứng minh** cell chưa từng tồn tại, bị DELETE, nhận NULL hay đã hết TTL.

## 4. Static-cell tombstone: xóa dữ liệu chung của partition

Cột `day_note text STATIC` thuộc cấp **partition**, không thuộc riêng một clustering row. Khi SELECT nhiều hàng, giá trị static có thể lặp lại trong các hàng kết quả, nhưng không vì thế mà thành nhiều cell độc lập.

Xóa static column chỉ cần **đầy đủ partition key**:

```sql
DELETE day_note
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Lệnh này tác động tới `day_note` chung, **không xóa các hàng E1, E2, E3**. Nó khác với:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Lệnh thứ hai xóa **toàn phân vùng**, gồm cả static data. Nếu chỉ muốn bỏ ghi chú của một ngày, không được dùng lệnh xóa partition.

### Ghi chú về static-only partition

Cassandra có thể lưu static data cho một partition **chưa có clustering row sống**. Khi thiết kế kiểm tra dữ liệu, đừng đồng nhất “không có hàng clustering” với “partition không còn static data”. Ngược lại, sau partition-level DELETE, các static cells cũ cũng bị che bởi dấu xóa partition.

## 5. Element tombstone: xóa một phần tử của non-frozen collection

Các collection CQL như `map`, `set` và `list` có thể được khai báo **không frozen** để hỗ trợ cập nhật ở mức phần tử. Trong lưu trữ, chúng thường được biểu diễn như một tập cell/đường dẫn phần tử, thay vì một blob duy nhất.

Với `attributes map<text, text>`:

```text
attributes:
  "unit"   -> "C"
  "source" -> "edge"
```

Xóa chỉ key `'source'`:

```sql
DELETE attributes['source']
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Hậu quả logic:

```text
Trước:
  attributes = {'unit':'C', 'source':'edge'}

Sau:
  attributes = {'unit':'C'}
```

Lệnh trên không yêu cầu xóa toàn map, không xóa `payload` hoặc `status`, và không xóa hàng E1.

Về mặt lưu trữ, có thể tạo **tombstone của phần tử collection** tương ứng. Một map có nhiều phần tử được thêm/xóa liên tục có thể tích lũy nhiều cell và dấu xóa khác nhau trước khi được compact.

### Cập nhật một phần tử so với thay thế collection

Một cập nhật có phạm vi phần tử:

```sql
UPDATE observations_by_sensor_day
SET attributes['unit'] = 'F'
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Thao tác này khác với gán toàn bộ:

```sql
UPDATE observations_by_sensor_day
SET attributes = {'unit':'F'}
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Gán lại **toàn bộ non-frozen map** cần có semantics thay thế: phần tử cũ không nằm trong tập mới không được giữ lại chỉ vì từng tồn tại trước đó. Cassandra có thể ghi dấu **complex deletion** cho collection cũ cùng các phần tử mới. Vì thế, thay thế một collection lớn liên tục có thể tạo chi phí tombstone đáng kể.

Đừng suy ra “một câu UPDATE = một cell ghi mới” khi thao tác trên collection nhiều phần tử.

## 6. Complex deletion: xóa toàn bộ non-frozen collection

Nếu nghiệp vụ yêu cầu xóa **cả map `attributes`**, có thể viết:

```sql
DELETE attributes
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Về mặt logic, tất cả phần tử của map này không còn giá trị hiện hành, nhưng những cột khác như `payload` hoặc `status` không tự bị xóa.

Đối với **non-frozen collection**, Cassandra có thể biểu diễn việc xóa cả collection qua một dấu **complex deletion** để che các phần tử cũ, không nhất thiết phát một CQL DELETE riêng cho từng phần tử.

```text
Hàng E1
│
├── status                -> vẫn còn
├── payload               -> vẫn còn
└── attributes            -> complex deletion
      ├── "unit"   (phiên bản cũ bị che)
      └── "source" (phiên bản cũ bị che)
```

### Khi nào thường phát sinh complex deletion?

- `DELETE attributes` trên non-frozen collection.
- Gán/ghi đè **toàn bộ** map, set hoặc list không frozen theo semantics thay thế.
- Những thao tác trên collection mà triển khai cần che phiên bản phần tử cũ để có giá trị tập hợp mới.

**Phạm vi hẹp hơn row deletion:** xóa cả collection vẫn không có nghĩa xóa hàng. Nhưng nếu collection này rất lớn, số phần tử và tombstone phải xét khi đọc hoặc compact vẫn có thể đáng kể.

### Không đồng nhất các loại collection

Map, set và list không frozen khác nhau ở cách định danh phần tử và hỗ trợ cập nhật. Đặc biệt, list có các thao tác theo vị trí/giá trị và cấu trúc lưu trữ phức tạp hơn map theo key. Khi cần sửa/xóa hàng nghìn phần tử độc lập, **nên cân nhắc mô hình mỗi phần tử là một hàng CQL**, thay vì cho một collection phình to không giới hạn trong một hàng.

## 7. Frozen collection: một giá trị nguyên khối, không xóa phần tử riêng lẻ

Bảng ví dụ có:

```sql
frozen_attrs frozen<map<text, text>>
```

Với `frozen<map<...>>`, Cassandra xử lý map như **một giá trị CQL duy nhất** khi ghi/xóa. Nó không hỗ trợ thao tác cập nhật/xóa một phần tử bên trong theo cách non-frozen map làm được.

Ví dụ xóa frozen map:

```sql
DELETE frozen_attrs
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Thao tác này mang ngữ nghĩa xóa **một cell chứa frozen value**. Để thay đổi nội dung frozen map, ứng dụng phải tính và ghi lại **toàn bộ map mới**.

So sánh:

| Tình huống | Non-frozen map | Frozen map |
| --- | --- | --- |
| Xóa `'source'` | Có thể thao tác phần tử `map['source']` | Không có thao tác xóa riêng phần tử bằng cú pháp tương đương. |
| Thay toàn bộ map | Có thể phát complex deletion + các phần tử mới | Ghi lại một giá trị cell nguyên khối. |
| Xóa toàn map | Complex/collection deletion | Cell tombstone. |
| Số lượng cell nội bộ | Có thể tăng theo số phần tử | Về mặt CQL value, được lưu như một cell. |
| Khuyến nghị | Collection nhỏ, có nhu cầu sửa từng phần tử | Giá trị nhỏ, ít thay đổi, được xử lý nguyên khối. |

Điểm khác biệt này quan trọng khi đánh giá **tombstone count**: hai schema có cùng JSON/map hiển thị trên API có thể tạo dạng tombstone và chi phí lưu trữ rất khác nhau.

## 8. Row tombstone: xóa một hàng clustering

Một hàng CQL được định danh bằng **toàn bộ primary key**, gồm partition key và tất cả clustering columns.

Để xóa đúng E1:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;
```

Lệnh này không liệt kê cột sau `DELETE`. Nó mang nghĩa **xóa hàng clustering** tại `(08:00, E1)`, bao gồm các regular scalar và collection values ở hàng đó.

```text
Partition (acme, S1, 2026-11-21)
│
├── static day_note = "Ca sáng"        -> không bị xóa
├── (08:00, E1)                         -> row tombstone
├── (08:05, E2)                         -> vẫn còn
└── (08:10, E3)                         -> vẫn còn
```

Cassandra có thể biểu diễn xóa ở mức **row deletion**, thay vì lập danh sách cell cần xóa. Dấu xóa hàng che các cell cũ thuộc hàng đó, trong khi static cells của partition và các hàng clustering khác không bị ảnh hưởng.

### Tại sao xóa row khác xóa tất cả regular columns?

Giả sử một hàng có `status`, `payload` và `attributes`. Việc xóa lần lượt từng cột bằng nhiều lệnh `DELETE column` có thể tạo nhiều cell/complex deletions. `DELETE FROM ... WHERE full_primary_key` diễn đạt rõ hơn rằng **cả hàng** không còn là bản ghi hiện hành.

Tuy nhiên, không nên phát row deletion nếu nghiệp vụ chỉ muốn ẩn `payload` nhưng giữ `status` hoặc các giá trị còn lại. Phạm vi xóa phải khớp chính xác với yêu cầu nghiệp vụ.

### Primary key không bị “đặt thành NULL”

Row deletion không phải cập nhật `observed_at = null` hay `observation_id = null`. Primary key là **tọa độ của hàng**; dấu xóa hàng ghi nhận rằng dữ liệu ở tọa độ đó đã bị xóa theo write timestamp.

Một lần ghi mới vào **cùng full primary key** với timestamp mới hơn dấu xóa có thể tạo dữ liệu sống trở lại. DELETE không tự đặt một cấm vĩnh viễn với khóa này.

## 9. Range tombstone: xóa một khoảng clustering rows

Nếu yêu cầu là xóa tất cả sự kiện từ 08:00 đến trước 09:00 của **một partition ngày**, việc phát một DELETE cho từng observation ID có thể tạo rất nhiều mutation riêng lẻ. Khi CQL/version cho phép điều kiện xóa range tương ứng, Cassandra có thể dùng **range tombstone** để biểu diễn đoạn clustering bị xóa.

Ví dụ ý tưởng với clustering đầu tiên `observed_at`:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at >= '2026-11-21T08:00:00Z'
  AND observed_at <  '2026-11-21T09:00:00Z';
```

Trong những phiên bản/ngữ cảnh CQL hỗ trợ dạng range deletion này, lệnh xác định **một partition key hoàn chỉnh** và một **đoạn clustering**. Cần kiểm chứng giới hạn cú pháp DELETE và quy tắc clustering-prefix trên chính phiên bản Cassandra đang sử dụng.

```text
Partition (acme, S1, 2026-11-21)
│
├── (07:50, Ex)       ngoài khoảng -> giữ
├── [08:00, ...       bắt đầu khoảng xóa
├── (08:05, E2)       thuộc khoảng -> bị che
├── (08:10, E3)       thuộc khoảng -> bị che
├── ... , 09:00)      kết thúc khoảng xóa
└── (09:05, Ey)       ngoài khoảng -> giữ
```

**Range tombstone không nhất thiết tạo một tombstone riêng cho mỗi hàng nằm trong khoảng**. Nó mô tả một đoạn dữ liệu cần bị che ở timestamp xóa. Tuy nhiên, khi đọc một slice giao với đoạn xóa hoặc trong compaction, Cassandra vẫn phải xét các marker và dữ liệu liên quan.

### Giới hạn phạm vi của range deletion

- Nó áp dụng **bên trong partition key đã chỉ định**, không tự xóa các phân vùng ngày khác.
- Điều kiện khoảng phải tuân theo **thứ tự/clustering-prefix** được CQL hỗ trợ.
- Thứ tự `CLUSTERING ORDER BY DESC` thay đổi thứ tự duyệt trong partition, nhưng không làm một điều kiện thời gian `[08:00,09:00)` trở thành điều kiện trên nhiều partition.
- Xóa theo khoảng và xóa từng hàng có thể cho trạng thái logic giống nhau đối với một tập hàng, nhưng biểu diễn tombstone và chi phí ghi/compaction có thể khác.

### Khi không nên xóa theo range

Nếu khoảng thời gian chứa cả dữ liệu cần giữ và dữ liệu cần xóa theo điều kiện nghiệp vụ không trùng với dải clustering, một range tombstone sẽ xóa **quá rộng**. Ví dụ yêu cầu “chỉ xóa sự kiện có `status='failed'` trong giờ 08” không thể tùy tiện dùng DELETE theo giờ rồi mong chỉ những hàng failed bị xóa.

Cassandra thiết kế bảng theo truy vấn; nếu cần xóa chọn lọc theo loại sự kiện, phải biết đúng full keys hoặc có đường truy cập/bảng riêng tương ứng.

## 10. Partition tombstone: xóa toàn phân vùng và static data

Một partition key có thể chứa hàng nghìn clustering rows và các static columns. Nếu yêu cầu xóa **toàn bộ dữ liệu trong partition ngày**, câu lệnh là:

```sql
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Không có điều kiện clustering hoặc danh sách cột: đây là **partition deletion**.

```text
Partition (acme, S1, 2026-11-21)
│
├── static day_note     -> bị che
├── (08:00, E1)         -> bị che
├── (08:05, E2)         -> bị che
└── (08:10, E3)         -> bị che

Dấu xóa ở cấp partition che các phiên bản cũ
thuộc partition đó theo write timestamp.
```

Dấu xóa ở mức partition có thể biểu diễn toàn bộ phạm vi mà **không cần đọc trước mọi clustering row**. Đây là lợi thế về số mutation cần phát so với xóa từng hàng trong partition rất lớn.

Tuy nhiên, nó **không phải** thao tác “xóa toàn bộ SSTable ngay tại thời điểm nhận lệnh”. Các phiên bản cũ trong SSTable vẫn có thể tồn tại đến khi compaction thu hồi an toàn. Query/repair/streaming phải xử lý trạng thái deletion tương ứng trong thời gian chuyển tiếp.

### Phân biệt xóa partition và `TRUNCATE`

`TRUNCATE` là thao tác quản trị ở **phạm vi bảng**, không phải partition deletion. Không dùng `TRUNCATE` để “xóa dữ liệu của một tenant/ngày”: nó ảnh hưởng dữ liệu của toàn bảng và có các điều kiện vận hành/khôi phục riêng.

Ngược lại, một partition-level `DELETE` chỉ xác định **một giá trị partition key hoàn chỉnh**, không xóa các partition khác.

### Xóa một partition đã hết dữ liệu sống

Ngay cả khi SELECT không còn thấy hàng sống trong partition, Cassandra vẫn có thể cần ghi dấu xóa để bảo vệ ngữ nghĩa với các phiên bản cũ. Không nên spam DELETE lặp lại chỉ để mong tiết kiệm dung lượng; các mutation/timestamps mới có thể khiến việc dọn dữ liệu khó dự đoán hơn.

## 11. Bảng đối chiếu phạm vi xóa, dữ liệu còn lại và chi phí

| Yêu cầu nghiệp vụ | Dạng thao tác | Dữ liệu còn lại | Điều cần chú ý |
| --- | --- | --- | --- |
| Xóa payload của E1 | `DELETE payload` với full primary key | Các cột khác, các hàng khác, static data | Cell tombstone; NULL cũng có semantics xóa. |
| Xóa key `'source'` của map E1 | `DELETE attributes['source']` | Các phần tử khác và cột khác | Element tombstone trong non-frozen map. |
| Xóa toàn map E1 | `DELETE attributes` | Các regular columns còn lại | Complex deletion của non-frozen collection. |
| Xóa frozen map E1 | `DELETE frozen_attrs` | Các cột khác | Frozen map như một cell. |
| Xóa note chung | `DELETE day_note` với partition key | Các hàng clustering vẫn sống | Static-cell tombstone. |
| Xóa E1 | `DELETE FROM` với full primary key | E2/E3 và static note | Row tombstone. |
| Xóa sự kiện 08:00–09:00 | `DELETE FROM` với partition key + clustering range | Các hàng ngoài khoảng, static note | Range tombstone nếu cú pháp được hỗ trợ. |
| Xóa ngày của sensor | `DELETE FROM` với partition key | Các partition ngày khác | Partition tombstone, static data cũng bị che. |

Không thể kết luận số tombstone vật lý chính xác chỉ bằng cách đếm số câu CQL đã thực hiện. Một thao tác trên collection có thể liên quan nhiều cell, một range tombstone có thể che nhiều hàng, và trạng thái cuối còn phụ thuộc write timestamps, TTL, SSTable/compaction và định dạng lưu trữ.

## 12. Write timestamp: dấu xóa không đơn thuần là trạng thái Boolean

Tombstone có write timestamp để hòa giải với dữ liệu cũ. Trong Cassandra, một giá trị sống và dấu xóa có thể đến các replica theo thứ tự khác nhau nhưng vẫn được so sánh theo timestamp khi đọc/merge.

Ví dụ minh họa:

```text
Timestamp 100: status = "pending"
Timestamp 150: status = "processed"
Timestamp 200: DELETE status

=> Tombstone tại 200 che các giá trị cũ tại 100 và 150.

Timestamp 250: status = "reopened"
=> Giá trị 250 có thể lại được xem là sống.
```

Tương tự:

- **Cell tombstone** che phiên bản cũ của một cell.
- **Complex deletion** che các phần tử cũ thuộc collection ở phạm vi của nó.
- **Row tombstone** che cell cũ thuộc hàng.
- **Range tombstone** che hàng/cell cũ thuộc đoạn clustering.
- **Partition tombstone** che các hàng và static data cũ trong partition.

Ở timestamp bằng nhau, Cassandra còn dùng các quy tắc giải quyết hòa; vì vậy **không nên cố tạo write timestamps trùng nhau** cho các thao tác xung đột rồi dựa vào thứ tự request để suy ra trạng thái cuối.

### Hai khái niệm thời gian khác nhau

| Thời gian | Mục đích |
| --- | --- |
| **Write timestamp** (thường có độ phân giải microsecond) | Hòa giải dữ liệu sống và tombstone, quyết định phiên bản nào thắng. |
| **Local deletion time / thời gian ghi nhận xóa hoặc hết hạn** | Tham gia đánh giá tuổi tombstone và điều kiện garbage collection. |

Không nhầm `observed_at` (thời gian sự kiện nghiệp vụ, đồng thời là clustering column trong bảng) với **write timestamp** của mutation. Sự kiện cũ được ghi hôm nay có thể mang write timestamp mới, dù `observed_at` là ngày hôm qua.

### DELETE không có nghĩa “không được ghi vào khóa này nữa”

Nếu ứng dụng ghi dữ liệu mới có timestamp mới hơn dấu xóa vào cùng primary key, Cassandra có thể cho dữ liệu xuất hiện trở lại. Nếu nghiệp vụ cần cấm tái sử dụng một định danh, phải thiết kế **cơ chế quyền sở hữu/claim hoặc trạng thái nghiệp vụ** thích hợp, không dựa vào tombstone như một danh sách cấm vĩnh viễn.

## 13. TTL hết hạn tương tác với từng phạm vi dữ liệu

TTL là một nguồn tạo trạng thái tombstone thường gặp trong dữ liệu time-series. Khi cell mang TTL hết hạn, Cassandra coi giá trị đó là không còn sống; **không cần một client gửi `DELETE` mới** vào đúng giây hết hạn.

Ví dụ:

```sql
INSERT INTO observations_by_sensor_day (
    tenant_id, sensor_id, event_day,
    observed_at, observation_id, status, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21',
    '2026-11-21T09:00:00Z',
    142dd6ae-6706-4f2c-a5e8-61cdd9c22cad,
    'temporary',
    'expire-in-10-min'
) USING TTL 600;
```

Sau **600 giây kể từ lúc ghi theo semantics TTL**, các giá trị có TTL không còn sống. Điều này không đồng nghĩa cả partition ngày bị xóa. Các hàng khác, static data hoặc các cell không có TTL có thể vẫn còn.

### TTL và non-frozen collection

Một collection không frozen gồm nhiều phần tử/cell. Các thao tác ghi có TTL có thể áp dụng vòng đời cho các cell/phần tử được ghi, trong khi các phần tử được ghi ở thời điểm khác có thời hạn khác.

Điều đó khiến một map trông như còn ít phần tử sống nhưng vẫn có lịch sử cell hết hạn và tombstone trên SSTable. Không thể chỉ nhìn số key hiện hành trong một `SELECT attributes` để biết chi phí lưu trữ nội bộ.

### TTL và frozen collection

Frozen map là một giá trị cell nguyên khối; nếu cell đó mang TTL, **toàn bộ frozen value** hết hạn theo vòng đời của cell. Nó không có expiration độc lập cho từng phần tử bên trong giống một non-frozen map được ghi theo nhiều thao tác.

### TTL không đồng nghĩa row tombstone hay partition tombstone

Khi TTL của một số regular cells hết hạn, đó là trạng thái expiring cell. Cassandra còn có khái niệm **row liveness marker** và metadata liên quan việc xác định hàng còn sống; không được suy luận đơn giản rằng “TTL của payload hết hạn tức là có DELETE cả hàng” hoặc “mọi cell trong ngày hết TTL nên đã sinh partition deletion”.

Cần xem toàn bộ dữ liệu sống trong hàng/partition và cách giá trị được ghi trước khi kết luận một hàng có còn xuất hiện trong SELECT hay không.

### Kiểm tra TTL theo CQL

```sql
SELECT observed_at, observation_id,
       payload,
       TTL(payload),
       WRITETIME(payload)
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T09:00:00Z'
  AND observation_id = 142dd6ae-6706-4f2c-a5e8-61cdd9c22cad;
```

`TTL(payload)` cho thời gian còn lại khi cell sống và có TTL; `WRITETIME(payload)` cho write timestamp khi khả dụng. Chúng **không** phải công cụ liệt kê chính xác mọi tombstone vật lý sau khi dữ liệu hết hạn.

## 14. Vì sao range/partition tombstone vẫn có chi phí đọc?

Một cách giải thích sai thường gặp là: “Nếu DELETE cả partition chỉ tạo một tombstone, truy vấn sau đó chắc chắn rẻ”. Số lượng **mutation xóa** và lượng việc **đọc/compaction** không phải cùng đại lượng.

Cassandra có thể cần:

1. Đọc/ghép thông tin partition và clustering ranges từ nhiều SSTable.
2. So sánh tombstone với các cell/hàng cũ theo write timestamp.
3. Xác định giá trị nào còn sống để trả về.
4. Giữ lại dấu xóa khi vẫn cần che bản cũ trên SSTable hoặc replica khác.
5. Chỉ loại tombstone và dữ liệu tương ứng khi compaction thỏa điều kiện thu hồi an toàn.

```text
SSTable-A: hàng E1, E2, E3 (timestamp cũ)
SSTable-B: range tombstone [08:00,09:00)
SSTable-C: một số giá trị ghi mới hơn trong cùng partition

Khi đọc:
  phải hòa giải các marker, timestamp và dữ liệu tương ứng.
```

Một range tombstone có thể **tiết kiệm số lệnh DELETE** so với xóa từng hàng, nhưng đọc một đoạn giao nhiều tombstone và một lượng lớn dữ liệu cũ vẫn có thể tốn tài nguyên. Partition tombstone có phạm vi rộng hơn, làm các phiên bản cũ thuộc partition không còn sống, nhưng không làm các SSTable chứa chúng tự biến mất ngay.

### `LIMIT` không giới hạn số tombstone phải xét

```sql
SELECT observed_at, observation_id, status
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;
```

`LIMIT 20` giới hạn số hàng **kết quả**, không bảo đảm replica chỉ xét 20 cell/hàng nội bộ. Khi dải mới nhất có nhiều dữ liệu xóa/hết TTL, Cassandra có thể phải đọc qua nhiều marker trước khi trả đủ số hàng sống.

Một truy vấn trả 0 hàng nhưng cần xử lý nhiều tombstone vẫn có thể chậm.

## 15. Tombstone reclamation: khi nào dấu xóa được dọn?

Xóa logic xảy ra khi dữ liệu cũ bị dấu xóa thắng theo timestamp. **Thu hồi vật lý** là bước về sau, chủ yếu qua compaction, với yêu cầu không làm dữ liệu cũ “sống lại”.

```text
DELETE / NULL / TTL expiry
            |
            v
Dấu xóa/expired cell có hiệu lực logic
            |
            +--> replica khác có thể còn dữ liệu cũ
            |
            v
Dữ liệu cũ và dấu xóa còn trên SSTable
            |
            v
Đủ điều kiện về grace, SSTable overlap, repair và an toàn
            |
            v
Compaction có thể purge tombstone + phiên bản đã bị che
```

### Vai trò của `gc_grace_seconds`

`gc_grace_seconds` là tham số của bảng giúp xác định **thời gian bảo vệ** tombstone trước khi đủ điều kiện thu hồi theo cơ chế phiên bản. Nó liên quan đến nguy cơ replica bị ngắt kết nối bỏ lỡ deletion và sau đó quay lại với dữ liệu cũ.

Nếu một replica đã bỏ lỡ xóa, trong khi các replica khác đã dọn tombstone quá sớm, bản cũ có thể được lan truyền và xuất hiện lại — thường được gọi là **zombie data**. Vì vậy, lịch repair, cấu hình grace và việc dọn tombstone phải được thiết kế chung.

**Nhưng `gc_grace_seconds` không phải bộ đếm “đến giờ sẽ xóa”:**

- Hết khoảng grace **không bảo đảm** tombstone được purge ngay.
- Một SSTable khác có thể còn phiên bản cũ mà tombstone phải che.
- Chiến lược compaction và điều kiện overlap ảnh hưởng khả năng purge.
- Trạng thái replica/repair và cơ chế tombstone garbage collection tùy phiên bản cũng có vai trò.

Không giảm `gc_grace_seconds` chỉ vì log có nhiều tombstone, đặc biệt ở cluster mà replica có thể offline lâu hoặc repair chưa được bảo đảm.

### Tại sao thao tác xóa không làm dung lượng đĩa giảm ngay?

Trong LSM, một DELETE ban đầu có thể **ghi thêm** tombstone vào commit log/memtable/SSTable. Byte vật lý trên đĩa có thể tạm tăng. Khi compaction đủ điều kiện dọn dữ liệu bị che và marker, footprint mới có thể giảm. Không kết luận DELETE thất bại chỉ vì số byte SSTable chưa giảm ngay sau khi CQL trả thành công.

## 16. Quan sát: đo tombstone theo truy vấn và bảng

Khi thấy SELECT trả ít hàng mà p99 tăng, cần chẩn đoán thay vì chỉ đo số hàng sống.

### Thống kê bảng

```bash
nodetool tablestats app_ks.observations_by_sensor_day
nodetool tablehistograms app_ks observations_by_sensor_day
```

Các trường được hỗ trợ tùy phiên bản, có thể gồm:

- **Average tombstones per slice** và live cells per slice.
- **Read latency**, SSTables per read, SSTable count.
- **Partition size / cell count histogram**.
- Metrics liên quan tombstone, compaction backlog, read timeouts và tải node.

Các số liệu này có thể ở phạm vi **bảng và node**, không phải số tombstone chính xác của một full primary key. Partition size lớn, cell count cao, TTL nhiều và hot partition có thể xuất hiện cùng lúc, nên cần kết hợp số liệu.

### Tracing truy vấn giới hạn

Trong môi trường có kiểm soát:

```sql
TRACING ON;

SELECT observed_at, observation_id, status
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing có thể chỉ ra read path và lượng dữ liệu/tombstone được xét khi phiên bản cung cấp thông tin. Tracing có overhead; **không** bật mọi request production.

### Ngưỡng cảnh báo và lỗi do tombstone

Một số phiên bản Cassandra có các cấu hình như `tombstone_warn_threshold` và `tombstone_failure_threshold` cho truy vấn đọc. Tên, mặc định, phạm vi và semantics có thể thay đổi theo phiên bản/phân phối. Cần kiểm tra chính xác hệ đang chạy thay vì sao chép ngưỡng từ môi trường khác.

**Không tăng ngưỡng thất bại như một cách sửa tận gốc**: nó có thể chỉ cho phép một truy vấn tiếp tục quét nhiều dữ liệu hơn và làm tăng CPU/I/O.

### Vì sao `COUNT(*)` không đo tombstone?

```sql
SELECT COUNT(*)
FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

`COUNT(*)` trả số hàng nhìn thấy theo semantics đọc, không đếm mọi tombstone vật lý. Đếm trên partition lớn có thể tạo tải nặng. Dùng metrics/tracing/histogram hoặc phân tích SSTable bằng công cụ phù hợp trong môi trường an toàn để điều tra sâu hơn.

## 17. Java Driver 4.x: thể hiện phạm vi xóa trong API

Một repository nên tách rõ các thao tác xóa **cell**, **hàng** và **partition**, thay vì cung cấp một method có tham số boolean khó hiểu.

Ví dụ:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class ObservationRepository {
    private final CqlSession session;
    private final PreparedStatement deletePayload;
    private final PreparedStatement deleteRow;
    private final PreparedStatement deletePartition;

    public ObservationRepository(CqlSession session) {
        this.session = session;

        this.deletePayload = session.prepare(
            "DELETE payload FROM observations_by_sensor_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ? " +
            "AND observed_at = ? AND observation_id = ?"
        );

        this.deleteRow = session.prepare(
            "DELETE FROM observations_by_sensor_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ? " +
            "AND observed_at = ? AND observation_id = ?"
        );

        this.deletePartition = session.prepare(
            "DELETE FROM observations_by_sensor_day " +
            "WHERE tenant_id = ? AND sensor_id = ? AND event_day = ?"
        );
    }

    public void removePayload(
            String tenantId, UUID sensorId, LocalDate day,
            Instant observedAt, UUID observationId) {
        session.execute(deletePayload.bind(
            tenantId, sensorId, day, observedAt, observationId
        ));
    }

    public void removeObservation(
            String tenantId, UUID sensorId, LocalDate day,
            Instant observedAt, UUID observationId) {
        session.execute(deleteRow.bind(
            tenantId, sensorId, day, observedAt, observationId
        ));
    }

    // Thao tác nguy hiểm: xóa cả static data và mọi hàng trong ngày.
    // Chỉ gọi sau khi xác thực/ủy quyền và kiểm tra chính sách nghiệp vụ.
    public void removeWholeDay(
            String verifiedTenantId, UUID sensorId, LocalDate day) {
        session.execute(deletePartition.bind(
            verifiedTenantId, sensorId, day
        ));
    }
}
```

Trong ứng dụng thực tế:

1. **Full primary key** cần được bind đủ khi xóa một hàng hoặc cell; partition deletion chỉ dùng **đầy đủ partition key**.
2. `tenantId` phải đến từ ngữ cảnh đã xác thực/ủy quyền, không tin tùy ý chuỗi người dùng gửi.
3. Cần quyền/đường gọi riêng cho **partition deletion**, vì phạm vi ảnh hưởng lớn hơn xóa cột.
4. Cùng khóa và ngữ nghĩa mutation phải được giữ ổn định khi retry. Timeout không chứng minh server chưa áp dụng DELETE.
5. Nếu dùng write timestamp do client chỉ định, cần quản lý thứ tự mutation; timestamp lệch có thể làm dữ liệu cũ thắng hoặc dấu xóa che các lần ghi mới.
6. Repository không nên biến field vắng mặt trong API PATCH thành `null` rồi ghi tombstone. Hãy phân biệt **không cập nhật**, **gán giá trị** và **xóa có chủ đích**.
7. Xóa các row trong nhiều partitions không trở thành transaction nguyên tử chỉ vì Java gọi tuần tự các prepared statements.

### Khi cần xóa một map key

Phía ứng dụng nên có một method riêng như `removeAttribute(key)`, xây dựng prepared CQL hợp lệ cho phiên bản đang dùng và bind đúng key phần tử lẫn full primary key. Đừng dùng `DELETE attributes` khi chỉ muốn xóa một key, vì nó làm mất toàn bộ collection.

## 18. Các anti-pattern liên quan phạm vi tombstone

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Gửi `null` cho mọi field không có trong PATCH | Cell tombstones ngoài ý muốn | Phân biệt absent, UNSET, explicit delete. |
| Xóa từng hàng khi nghiệp vụ muốn xóa trọn partition | Nhiều mutation/row tombstones; công việc ghi tăng | Dùng partition-level deletion khi **thực sự được phép** xóa cả partition. |
| Xóa cả partition khi chỉ cần xóa một cột | Mất dữ liệu hợp lệ, cả static data | Giữ phạm vi delete tối thiểu đúng nghiệp vụ. |
| Xóa map key bằng cách gán lại toàn bộ map lớn liên tục | Complex deletion và nhiều cell/tombstones | Sửa phần tử khi cần, hoặc mô hình hóa phần tử thành hàng. |
| Dùng frozen collection nhưng lại cần xóa từng phần tử | Buộc thay cả giá trị, cập nhật tốn chi phí | Chọn non-frozen nhỏ hoặc bảng con theo phần tử. |
| TTL cực ngắn trên dữ liệu ghi rất dày | Nhiều expired cells và chi phí đọc/compaction | Thiết kế bucket/vòng đời và thử tải TTL. |
| Cho rằng `LIMIT 10` có nghĩa chỉ đọc 10 cell | Có thể quét rất nhiều tombstone | Đo scanned tombstones và thu hẹp clustering range. |
| Giảm `gc_grace_seconds` để “xóa nhanh” | Nguy cơ zombie data nếu replica bỏ lỡ delete | Đồng bộ repair, cân nhắc an toàn theo phiên bản. |
| Tăng tombstone warning threshold để giảm log | Che dấu gốc của read amplification | Sửa pattern DELETE/TTL/query/schema trước. |
| Thay collection bằng dữ liệu lớn không giới hạn | Overhead/tombstones phình to | Giới hạn collection, tách sang bảng theo truy vấn. |

Mục đích không phải “không bao giờ có tombstone”. Cassandra **cần tombstone** để xóa dữ liệu đúng trong môi trường phân tán. Mục tiêu là **đúng phạm vi, có vòng đời và không gây chi phí bất ngờ**.

## 19. Bài tập tình huống và đáp án

Một hệ thống lưu dữ liệu thiết bị có partition `(tenant_id='acme', sensor=S1, event_day=2026-11-21)` và:

- Static column `day_note = 'Ca sáng'`.
- Hàng E1 lúc 08:00 có `status='ok'`, `payload='T=38.1'`, `attributes={'unit':'C','source':'edge'}` và `frozen_attrs={'location':'room-A'}`.
- Hàng E2 lúc 08:05 có `status='ok'`, `payload='T=38.4'`.
- Hàng E3 lúc 08:10 có `status='ok'`, `payload='T=38.7'`.

Các thao tác sau được xét **độc lập từ cùng trạng thái ban đầu**, trừ khi câu hỏi nói khác.

**Câu hỏi:**

1. `DELETE payload` ở full primary key E1 tạo phạm vi xóa nào? E1 còn có thể được đọc ra không?
2. `DELETE attributes['source']` ở E1 khác gì `DELETE attributes`?
3. Xóa `frozen_attrs` có thể chỉ xóa key `'location'` mà giữ các key khác không?
4. `DELETE FROM ... WHERE full_primary_key_of_E1` khác gì `DELETE payload`?
5. Xóa E1 có tự xóa `day_note` không?
6. `DELETE day_note ... WHERE partition_key` xóa gì? E2/E3 còn sống không?
7. Xóa một khoảng `[08:00, 08:10)` tác động tới E1, E2, E3 như thế nào?
8. Xóa **toàn partition ngày** có giữ static `day_note` không?
9. Vì sao range tombstone có thể che 100.000 hàng mà không nhất thiết có 100.000 lệnh DELETE?
10. Nếu `payload` được ghi với TTL 600 giây, hết TTL có tự tạo một lệnh DELETE mới từ ứng dụng không?
11. Có thể suy ra số lượng tombstone trên SSTable từ `COUNT(*)` hay `TTL(payload)` không?
12. Nếu một replica bỏ lỡ xóa và quay lại sau khi tombstone ở các replica khác được purge không an toàn, rủi ro gì xuất hiện?
13. Nếu ghi lại `payload` ở E1 với write timestamp lớn hơn cell tombstone, điều gì có thể xảy ra?
14. Khi một DTO Java không chứa field `status`, nên bind `null` hay bỏ qua mutation nếu ý định là “giữ nguyên status”?

**Đáp án:**

1. **Cell tombstone** cho `payload` của E1. E1 vẫn có thể tồn tại nhờ `status` hoặc các giá trị sống khác.
2. Lệnh đầu xóa **một phần tử** của non-frozen map; lệnh sau xóa **toàn collection**, có thể qua complex deletion.
3. **Không theo semantics cập nhật phần tử của frozen value.** Frozen map là một giá trị nguyên khối, phải thay hoặc xóa cả cell.
4. Lệnh đầu xóa **cả hàng E1** qua row deletion, còn lệnh sau chỉ xóa `payload`.
5. **Không.** Static data thuộc partition, không thuộc riêng E1.
6. Xóa **static cell** của partition; các hàng E2/E3 không tự bị xóa.
7. Nếu phạm vi range được hỗ trợ với điều kiện đó, E1 và E2 thuộc `[08:00,08:10)`, còn E3 đúng 08:10 nằm **ngoài khoảng**, vẫn giữ.
8. **Không.** Partition deletion che cả dữ liệu static và clustering rows thuộc partition.
9. Vì range tombstone biểu diễn một **đoạn clustering** có timestamp xóa, không cần mutation riêng cho mỗi hàng.
10. **Không.** Cell hết hạn theo TTL và được xử lý như dữ liệu đã xóa, không phải job DELETE mới.
11. **Không.** COUNT(*) đếm hàng nhìn thấy; TTL() cho metadata còn lại của giá trị, không liệt kê tombstone vật lý.
12. **Zombie data**: bản cũ có nguy cơ xuất hiện lại nếu thông tin xóa bị thu hồi trước khi replica được đồng bộ an toàn.
13. Giá trị mới **có thể sống trở lại** nếu thắng theo timestamp và các quy tắc hòa giải liên quan.
14. **Bỏ qua mutation** cho `status`, hoặc dùng UNSET đúng API/phiên bản; bind NULL có semantics xóa và có thể tạo tombstone.

### Thực hành thêm

Hãy tạo bảng `observations_by_sensor_day` trong keyspace thử nghiệm, ghi cùng một partition với ba hàng như phần 2. Sau đó làm ba lượt thí nghiệm riêng:

```sql
-- Lượt A: xóa một cell.
DELETE payload FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;

-- Lượt B: xóa một hàng.
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
  AND observed_at = '2026-11-21T08:00:00Z'
  AND observation_id = 8817a208-1858-4144-86e9-b24d9083e478;

-- Lượt C: xóa toàn partition.
DELETE FROM observations_by_sensor_day
WHERE tenant_id = 'acme'
  AND sensor_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21';
```

Trước mỗi lượt, khôi phục dữ liệu mẫu. Đọc lại theo full partition key và so sánh số hàng/giá trị static còn sống. Nếu có quyền vận hành môi trường lab, quan sát thêm thống kê tombstone và SSTable qua công cụ phù hợp. **Đừng thực hiện xóa toàn partition trên dữ liệu production chỉ để thử nghiệm.**

## 20. Checklist chọn đúng cấp tombstone

- [ ] Xác định **full partition key** và các clustering columns của bảng.
- [ ] Xác định yêu cầu nghiệp vụ xóa **cell, phần tử, collection, row, range hay partition**.
- [ ] Kiểm tra cột cần xóa là **regular, static, non-frozen collection hay frozen value**.
- [ ] Với range deletion, xác nhận cú pháp và quy tắc clustering prefix trên **phiên bản Cassandra đang dùng**.
- [ ] Không nhầm **NULL** với **UNSET** hoặc cột bị bỏ qua trong mutation.
- [ ] Đánh giá **write timestamp** khi có ghi/xóa đồng thời hoặc retry.
- [ ] Kiểm tra TTL và vòng đời cell/collection, không suy mọi TTL expiry là row/partition DELETE.
- [ ] Với lệnh xóa phạm vi rộng, xác nhận tất cả dữ liệu bị che **đều được phép xóa**, kể cả static data.
- [ ] Khi điều tra chi phí, đo **tombstones scanned**, số SSTable/read latency và compaction, không chỉ COUNT(*).
- [ ] Duy trì lịch repair và cấu hình grace an toàn để giảm nguy cơ zombie data.
- [ ] Không trông đợi compaction hoặc DELETE giải phóng byte SSTable ngay tức thì.
- [ ] Ở Java, tách API xóa cell/hàng/partition, áp dụng phân quyền tenant và giới hạn thao tác nguy hiểm.
- [ ] Dùng môi trường lab cùng workload TTL/DELETE để kiểm tra trước khi can thiệp production.

## 21. Ghi nhớ

- **Cell tombstone** che một giá trị cột; **static-cell tombstone** che giá trị chung ở mức partition.
- **Non-frozen collection** có thể có **element tombstone** và **complex deletion**; **frozen collection** được xử lý như một giá trị cell nguyên khối.
- **Row tombstone** che một hàng clustering; nó không tự xóa static data và các hàng khác cùng partition.
- **Range tombstone** che một đoạn clustering trong **một partition**, không mặc nhiên tạo một tombstone riêng cho từng hàng.
- **Partition tombstone** che cả hàng clustering và static values thuộc **một partition key hoàn chỉnh**.
- **NULL, DELETE và TTL hết hạn** đều có thể dẫn tới trạng thái xóa, nhưng phạm vi và cách hình thành khác nhau.
- Tombstone mang **write timestamp**, cần được hòa giải với phiên bản dữ liệu sống trước khi quyết định kết quả đọc.
- **Xóa logic trước, thu hồi vật lý sau**: compaction, `gc_grace_seconds`, trạng thái replica và SSTable overlap quyết định thời điểm có thể dọn.
- **Nhiều tombstone có thể làm SELECT chậm dù LIMIT nhỏ**, vì Cassandra phải xét các marker và dữ liệu cũ để tìm hàng sống.
- Giải pháp bền vững là chọn **đúng phạm vi xóa**, quản lý collection/TTL, thiết kế partition key phù hợp và theo dõi hiệu năng thay vì chỉ nới ngưỡng tombstone.

Nắm rõ tombstone từ cấp cell đến cấp partition giúp bạn đưa ra quyết định chính xác khi xóa dữ liệu Cassandra: chỉ xóa phần được yêu cầu, tránh che dữ liệu còn hợp lệ và dự đoán được tác động lên read path, compaction, repair, replication và các thao tác từ Java. Đây cũng là nền tảng để hiểu sâu hơn quy trình **tombstone reclamation** và xử lý lỗi trong cơ sở dữ liệu wide-column phân tán.

