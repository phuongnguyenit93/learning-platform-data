# TTL ở các thành phần collection/UDT theo cách lưu trữ trong Apache Cassandra

## 1. Một collection có luôn cùng một thời điểm hết hạn không?

Trong **Apache Cassandra**, hệ quản trị cơ sở dữ liệu **wide-column phân tán**, TTL (*time to live*) quy định thời gian một giá trị còn được xem là dữ liệu sống. Ở chương **Timestamp và TTL**, có một chi tiết quan trọng: **đơn vị lưu trữ của giá trị quyết định phạm vi TTL**. Một cột kiểu `map`, `set`, `list` hay **user-defined type (UDT)** có thể được lưu như **nhiều cell** hoặc như **một cell duy nhất** tùy có dùng `frozen` hay không.

Hãy hình dung hai cấu trúc chứa cùng hai thuộc tính:

- `properties map<text, text>` không `frozen`: Cassandra có thể lưu từng phần tử map ở các cell khác nhau. Mỗi phần tử được ghi có thể mang **write timestamp và TTL riêng**.
- `snapshot frozen<map<text, text>>`: toàn bộ giá trị map được tuần tự hóa trong **một cell**. Khi cell này có TTL, cả giá trị `snapshot` hết hạn cùng nhau; không thể gia hạn riêng một phần tử bằng update theo key.

Điều tương tự áp dụng cho **UDT không frozen** (các field có thể được ghi riêng) và **UDT frozen** (cả đối tượng như một giá trị nguyên khối).

TTL là công cụ quản lý vòng đời dữ liệu. Nó **không tự bảo đảm xóa vật lý ngay** khi hết hạn: Cassandra sử dụng thông tin hết hạn/tombstone và cơ chế compaction, repair để tránh replica cũ làm dữ liệu xuất hiện trở lại.

## 2. Phân biệt `frozen` và không `frozen` ở mức lưu trữ

Trong mô hình wide-column, một partition chứa các row, mỗi row có các cell. Với các kiểu phức hợp (*complex types*), CQL có thể ánh xạ **một cột logic** thành **nhiều cell vật lý**.

```text
Row: profile_id = P
|
|-- attributes map<text,text> (KHÔNG frozen)
|     |-- attributes['tier']     -> cell A, write timestamp TA, TTL A
|     |-- attributes['locale']   -> cell B, write timestamp TB, TTL B
|     +-- attributes['temporary']-> cell C, write timestamp TC, TTL C
|
|-- contact address_udt (KHÔNG frozen)
|     |-- contact.street  -> cell D, TTL D
|     |-- contact.city    -> cell E, TTL E
|     +-- contact.country -> cell F, TTL F
|
|-- snapshot frozen<map<text,text>>
|     +-- {tier:'pro', locale:'vi'} -> MỘT cell, MỘT TTL
|
+-- frozen_contact frozen<address_udt>
      +-- {street:...,city:...,country:...} -> MỘT cell, MỘT TTL
```

| Cấu trúc | Hình thức lưu trữ dễ hình dung | Có thể ghi từng thành phần? | Phạm vi TTL của mutation |
|---|---|---|---|
| `map<K,V>` không frozen | Một cell theo key của map | Có: cập nhật key riêng | Các phần tử được mutation ghi |
| `set<T>` không frozen | Một cell theo phần tử set | Có: thêm/xóa phần tử | Các phần tử mới được ghi |
| `list<T>` không frozen | Nhiều cell cho phần tử list | Có: thêm phần tử, một số thao tác theo vị trí | Các phần tử được mutation ghi |
| UDT không frozen | Một cell theo field | Có: cập nhật field riêng | Các field được mutation ghi |
| `frozen<collection>` | Một cell cho cả collection | Không cập nhật riêng phần tử theo cách của non-frozen | Toàn bộ cell frozen |
| `frozen<udt>` | Một cell cho cả UDT | Không cập nhật riêng field | Toàn bộ cell frozen |

**Lưu ý:** bảng trên diễn giải mô hình lưu trữ để hiểu TTL và mutation timestamp. Các chi tiết của cell path, tombstone và serialization có thể khác theo loại collection và phiên bản Cassandra; không tự suy ra cùng một cú pháp cập nhật cho mọi kiểu.

## 3. Khai báo bảng thử nghiệm cho collection và UDT

Thực hành trong **keyspace thử nghiệm** đã được chọn bằng `USE <keyspace>;`. Các lệnh sau sử dụng tên type/table mới; nếu chúng đã tồn tại với schema khác, hãy dùng tên khác thay vì mặc định rằng `IF NOT EXISTS` sẽ thay schema cũ.

### Tạo UDT

```sql
CREATE TYPE IF NOT EXISTS address_udt (
    street text,
    city text,
    country text
);
```

### Tạo bảng với cả cột frozen và non-frozen

```sql
CREATE TABLE IF NOT EXISTS ttl_shapes_by_id (
    profile_id uuid PRIMARY KEY,
    attributes map<text, text>,
    labels set<text>,
    milestones list<text>,
    contact address_udt,
    frozen_contact frozen<address_udt>,
    frozen_attributes frozen<map<text, text>>,
    note text
);
```

Trong bảng:

- `attributes`, `labels`, `milestones` là collection **không frozen** để minh họa các thành phần có vòng đời khác nhau.
- `contact` là UDT **không frozen**, có thể cập nhật một field.
- `frozen_contact` và `frozen_attributes` là các giá trị được lưu như **một cell**, thuận lợi cho cập nhật/đọc nguyên đối tượng nhưng không hỗ trợ thao tác phần tử độc lập như dạng non-frozen.
- `note` là cột scalar thông thường để giữ row còn dữ liệu sống và làm mốc quan sát độc lập.

Chèn một row khởi tạo:

```sql
INSERT INTO ttl_shapes_by_id (profile_id, note)
VALUES (
    99999999-9999-4999-8999-999999999999,
    'row kept for demonstrations'
);
```

Các đoạn sau sử dụng chung UUID trên và giả định thực hiện **theo thứ tự nêu trong bài**, đủ nhanh để các TTL ngắn chưa hết trước khi bạn đọc lại. Khi thử độc lập hoặc chạy lại, nên dùng UUID mới để tránh timestamp/tombstone từ lần cũ tác động đến kết quả.

## 4. `map` không frozen: TTL khác nhau cho từng key

Một map không frozen được lưu theo các phần tử gắn với từng **key của map**. Nếu các key được ghi trong các mutation khác nhau với TTL khác nhau, thời điểm hết hạn của chúng có thể khác nhau.

### 4.1. Ghi key sống lâu và key tạm thời

```sql
-- Key tier sống 1 giờ từ lần cập nhật này.
UPDATE ttl_shapes_by_id
USING TTL 3600
SET attributes['tier'] = 'pro'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

-- Key otp_hint chỉ sống 60 giây từ lần cập nhật riêng.
UPDATE ttl_shapes_by_id
USING TTL 60
SET attributes['otp_hint'] = 'expires-soon'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT attributes, note
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Ngay sau hai lệnh, `attributes` có thể chứa:

```text
{'tier': 'pro', 'otp_hint': 'expires-soon'}
```

Sau khi quá 60 giây, key `otp_hint` không còn là thành phần sống của map, trong khi `tier` vẫn có thể tồn tại cho đến khi hết 3.600 giây. **Đây là một map logic nhưng hai phần tử có TTL khác nhau.**

### 4.2. Cập nhật đúng một key

```sql
-- Ghi lại key tier thành một phiên bản không có TTL.
UPDATE ttl_shapes_by_id
USING TTL 0
SET attributes['tier'] = 'enterprise'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Nếu mutation mới thắng theo **write timestamp**, key `tier` nhận giá trị mới và không hết hạn theo TTL. Việc này **không gia hạn** key `otp_hint`. Tương tự, ghi lại `otp_hint` với TTL mới chỉ thay TTL của phần tử được ghi đó.

**Cảnh báo thực hành:** `USING TTL 0` nghĩa là không TTL đối với giá trị vừa ghi. Nó không phải cách xóa phần tử. Xóa key map được thực hiện bằng thao tác cập nhật/xóa tương ứng:

```sql
DELETE attributes['otp_hint']
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Xóa tạo tombstone phù hợp với phạm vi phần tử, giúp replica cũ không đưa key đã xóa trở lại khi hòa giải.

### 4.3. Ghi nhiều key trong cùng mutation

```sql
UPDATE ttl_shapes_by_id
USING TTL 120
SET attributes = attributes + {
    'region': 'apac',
    'channel': 'mobile'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Hai key được ghi trong cùng mutation thường có write timestamp/TTL tương ứng với mutation đó. Nhưng các key khác trong map đã tồn tại **không bị reset TTL** chỉ vì hai key mới được thêm vào.

## 5. `set` không frozen: vòng đời theo phần tử

Với `set<text>` không frozen, mỗi phần tử được biểu diễn bởi dữ liệu mà Cassandra có thể hòa giải riêng. Hai phần tử được thêm vào bằng hai mutation có TTL khác nhau có thể hết hạn vào hai thời điểm khác nhau.

```sql
UPDATE ttl_shapes_by_id
USING TTL 300
SET labels = labels + {'subscribed'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

UPDATE ttl_shapes_by_id
USING TTL 30
SET labels = labels + {'currently-online'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT labels
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Ngay sau ghi, có thể thấy cả `subscribed` và `currently-online`. Sau TTL 30 giây, phần tử `currently-online` hết hạn trong khi `subscribed` vẫn có thể còn sống.

Nếu một phần tử set **đã tồn tại**, thêm lại cùng phần tử có thể trở thành mutation mới đối với chính cell của phần tử ấy; nếu mutation thắng, metadata TTL/timestamp của phần tử đó được cập nhật. Vì thế retry không được quản lý tốt có thể kéo dài TTL ngoài dự kiến.

Để xóa riêng phần tử set:

```sql
UPDATE ttl_shapes_by_id
SET labels = labels - {'currently-online'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Không xem phép trừ set là “đợi TTL đến hạn”; đây là thao tác xóa với tombstone. Cũng đừng dùng set làm hệ thống đếm số lần xảy ra sự kiện: set **không chứa hai phần tử trùng nhau**, nên không lưu lịch sử xuất hiện lặp lại.

## 6. `list` không frozen: mỗi phần tử có thể hết hạn riêng nhưng vị trí không ổn định

`list<text>` không frozen có thể lưu các phần tử ở những cell riêng. Một list được **append** qua nhiều mutation với TTL khác nhau có thể mất từng phần tử khi hết hạn.

```sql
UPDATE ttl_shapes_by_id
USING TTL 30
SET milestones = milestones + ['started']
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

UPDATE ttl_shapes_by_id
USING TTL 300
SET milestones = milestones + ['ready']
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT milestones
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Ngay sau ghi, list có thể hiển thị `['started', 'ready']`; sau khi phần tử `started` hết TTL, list quan sát có thể chỉ còn `['ready']`. Thời điểm hết hạn khác nhau làm **vị trí index của các phần tử còn sống thay đổi** theo kết quả đọc.

Đây là một lý do không nên dùng list Cassandra như hàng đợi công việc có thứ tự chặt chẽ, hoặc phụ thuộc vào `milestones[0]` làm định danh ổn định dưới ghi đồng thời/TTL. Một số thao tác sửa/xóa theo vị trí list có chi phí đọc trước khi ghi và hành vi dễ gây bất ngờ khi concurrent writes.

Với dữ liệu sự kiện thực sự cần lịch sử, thường nên dùng **mỗi sự kiện là một row** có clustering key theo thời gian hoặc sequence được quản lý, thay vì nhồi cả lịch sử vào một list lớn.

## 7. UDT không frozen: TTL ở từng field

**User-defined type (UDT)** gom những thuộc tính có quan hệ gần nhau vào một kiểu dữ liệu. Nếu cột UDT **không frozen**, Cassandra có thể lưu từng field như cell riêng. Việc cập nhật một field không mặc nhiên làm mới TTL của mọi field khác.

### 7.1. Ghi UDT đầy đủ ở lần đầu

```sql
UPDATE ttl_shapes_by_id
SET contact = {
    street: '12 Nguyen Trai',
    city: 'Ha Noi',
    country: 'VN'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT contact
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Trong bảng thử nghiệm không có TTL mặc định, các field mới ghi trên `contact` không tự hết hạn khi mutation này không gắn `USING TTL`.

### 7.2. Đặt TTL riêng cho field `city`

```sql
UPDATE ttl_shapes_by_id
USING TTL 60
SET contact.city = 'Da Nang'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT contact
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Ngay sau ghi, kết quả logic gần như:

```text
{street: '12 Nguyen Trai', city: 'Da Nang', country: 'VN'}
```

Sau 60 giây, **field `city` có thể trở thành `null` hoặc không còn giá trị sống** trong đối tượng đọc được; `street` và `country` không tự hết hạn vì thao tác trên chỉ tác động field `city`. Để một UDT luôn hợp lệ theo nghiệp vụ, ứng dụng phải sẵn sàng xử lý **field thiếu giá trị** trong những UDT không frozen có TTL khác nhau.

### 7.3. Gán lại toàn bộ UDT

```sql
UPDATE ttl_shapes_by_id
USING TTL 180
SET contact = {
    street: '5 Le Loi',
    city: 'Hue',
    country: 'VN'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Đây là thao tác gán **toàn bộ giá trị UDT**, khác với `SET contact.city = ...`. Cassandra phải xử lý những field cũ không còn nằm trong giá trị thay thế theo quy tắc của UDT và tombstone; các field được ghi mới có TTL theo mutation này. Khi nghiệp vụ chỉ muốn thay đổi `city`, nên dùng cú pháp field cho UDT không frozen để giảm ghi lại những field không liên quan.

## 8. `frozen<map>` và `frozen<UDT>`: TTL cho cả đối tượng

**Frozen** biến một tập giá trị thành **một cell duy nhất**. Điều này thay đổi cả cách cập nhật và cách TTL tác động.

### 8.1. Frozen map

```sql
UPDATE ttl_shapes_by_id
USING TTL 90
SET frozen_attributes = {
    'locale': 'vi',
    'tier': 'pro'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT frozen_attributes
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

`frozen_attributes` được lưu nguyên như một giá trị. Khi TTL 90 giây hết, **cả frozen map** không còn sống. Không thể làm riêng key `locale` hết hạn sau 30 giây và `tier` sau 90 giây **bằng cách sửa trực tiếp phần tử của cùng frozen cell**.

Muốn thay đổi một key, ứng dụng phải **tạo giá trị frozen map mới** và ghi lại **toàn bộ cell**; mutation mới có timestamp và TTL áp dụng cho cả giá trị mới.

### 8.2. Frozen UDT

```sql
UPDATE ttl_shapes_by_id
USING TTL 120
SET frozen_contact = {
    street: '1 Bach Dang',
    city: 'Da Nang',
    country: 'VN'
}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;

SELECT frozen_contact
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Cả `frozen_contact` tồn tại như **một cell** với TTL 120 giây; không thể viết `SET frozen_contact.city = ...` như với non-frozen UDT. Muốn cập nhật `city`, cần tạo lại toàn bộ giá trị UDT và ghi đè một cell frozen.

### Lựa chọn frozen theo nghiệp vụ

| Nhu cầu | Lựa chọn cần cân nhắc |
|---|---|
| Mỗi field UDT/key map có thời hạn khác nhau | Non-frozen, cập nhật đúng thành phần |
| Mọi thành phần phải hết hạn cùng lúc | Frozen, ghi và hết hạn cả giá trị |
| Muốn cập nhật thường xuyên một key map | Non-frozen map hoặc bảng riêng theo key |
| Muốn bảo toàn snapshot bất biến của đối tượng | Frozen UDT/map phù hợp hơn |
| Collection có khả năng tăng rất lớn | Cân nhắc mô hình **row theo từng phần tử**, giới hạn partition và kích thước đọc/ghi |

**Cassandra không tự chuyển giá trị non-frozen sang frozen khi chạy truy vấn.** Đây là lựa chọn lúc định nghĩa schema; cần thiết kế và kiểm thử đường cập nhật tương ứng.

## 9. TTL mặc định ở bảng, `USING TTL` và `TTL 0` áp dụng ra sao?

Ngoài `USING TTL N` trên mutation, Cassandra hỗ trợ `default_time_to_live` ở cấp bảng. **Mỗi cell được mutation ghi** chọn TTL theo chính sách của mutation tại thời điểm đó:

| TTL mặc định bảng | Mutation | Hiệu lực với collection/UDT |
|---|---|---|
| `0` (không mặc định) | Không có `USING TTL` | Các thành phần/cell mới ghi không TTL |
| `300` | Không có `USING TTL` | Thành phần/cell mới ghi nhận mặc định khoảng 300 giây |
| `300` | `USING TTL 60` | Thành phần/cell mới ghi nhận TTL 60 giây |
| `300` | `USING TTL 0` | Cell mới ghi không TTL |
| Bất kỳ | Ghi một field UDT không frozen | TTL của những field khác không tự thay đổi |
| Bất kỳ | Ghi lại frozen UDT/map | Toàn bộ frozen cell nhận TTL của phiên bản mới |

Ví dụ với một bảng khác có TTL mặc định:

```sql
CREATE TABLE IF NOT EXISTS ttl_collection_default_by_id (
    id uuid PRIMARY KEY,
    attrs map<text, text>,
    snapshot frozen<map<text, text>>,
    note text
) WITH default_time_to_live = 600;

INSERT INTO ttl_collection_default_by_id (id, attrs, note)
VALUES (
    aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa,
    {'source': 'api', 'kind': 'temporary'},
    'default TTL demo'
);

-- Key pinned là một phần tử được ghi mới không có TTL.
UPDATE ttl_collection_default_by_id
USING TTL 0
SET attrs['pinned'] = 'true'
WHERE id = aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa;

-- Frozen snapshot sống 120 giây như một cell.
UPDATE ttl_collection_default_by_id
USING TTL 120
SET snapshot = {'source': 'api', 'kind': 'temporary'}
WHERE id = aaaaaaaa-9999-4999-8999-aaaaaaaaaaaa;
```

Sau khoảng 600 giây tính từ lần `INSERT`, các phần tử `source`/`kind` được ghi khi dùng mặc định có thể đã hết hạn. Key `pinned` vừa được ghi với `USING TTL 0` không bị hết hạn theo TTL, còn frozen `snapshot` hết hạn sau khoảng 120 giây kể từ mutation của nó. Một bảng có TTL mặc định **không có nghĩa mọi thành phần của cùng một row luôn hết hạn đồng thời**.

Khi `ALTER TABLE ... WITH default_time_to_live = ...` thay đổi mặc định, các cell/element đã có TTL không được Cassandra viết lại hàng loạt. Chỉ các **mutation tiếp theo** mới dùng default mới nếu không chỉ định TTL riêng.

## 10. Thay thế toàn bộ collection khác với thêm/sửa một phần tử

Đây là điểm dễ tạo lỗi dữ liệu khó chẩn đoán. Xét một map non-frozen chứa `tier` và `locale`:

```sql
-- Thay riêng một key (mutation tác động đúng thành phần đó).
UPDATE ttl_shapes_by_id
USING TTL 60
SET attributes['locale'] = 'en'
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Khác với thay **toàn bộ giá trị map**:

```sql
-- Thay toàn bộ map, không mang các key cũ sang giá trị mới.
UPDATE ttl_shapes_by_id
USING TTL 600
SET attributes = {'tier': 'basic'}
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Lệnh thứ hai có semantics **thay thế collection**: Cassandra cần xử lý việc xóa các phần tử thuộc giá trị cũ và ghi các phần tử mới. Các key như `locale` có thể biến mất, dù trước đó TTL của chúng còn thời gian sống. Không nên mô tả thao tác này như “chỉ sửa key `tier`”.

Tương tự:

- Gán toàn bộ non-frozen UDT khác với cập nhật một field.
- Với frozen collection/UDT, **mọi lần cập nhật đều mang tính thay cả cell**.
- Với set và list, toán tử thêm phần tử (`+`) khác với thay toàn bộ collection bằng một literal mới.

**Hệ quả vận hành:** các thao tác thay toàn bộ collection hoặc xóa phạm vi rộng có thể sinh tombstone; dùng collection rất lớn, cập nhật thường xuyên và TTL ngắn có thể tăng áp lực compaction/đọc. Khi từng thành phần có vòng đời/khả năng truy vấn độc lập và tăng trưởng không giới hạn, nên cân nhắc bảng lưu từng item theo row.

## 11. Last-write-wins, tombstone và TTL ở cell phức hợp

TTL không quyết định một phiên bản thắng khi hai writer xung đột. Cassandra vẫn hòa giải dựa trên **mutation timestamp**, đơn vị **micro giây**, và các quy tắc tombstone liên quan.

Một số tình huống tiêu biểu:

| Cạnh tranh ghi | Kết quả cần hiểu |
|---|---|
| Hai writer sửa **cùng key map** | So sánh write timestamp/tombstone của thành phần đó |
| Hai writer sửa **hai key map khác nhau** | Có thể cùng tồn tại, mỗi key giữ metadata riêng |
| Hai writer sửa **hai field UDT không frozen khác nhau** | Hai field có thể nhận giá trị và TTL từ hai mutation khác nhau |
| Hai writer thay **cùng frozen UDT** | So sánh các phiên bản của **một cell frozen**; một bản thắng toàn bộ |
| Xóa một key rồi ghi lại key đó với timestamp thấp hơn tombstone | Giá trị cũ hơn bị tombstone che |
| Thay toàn bộ non-frozen collection | Phải xét tombstone ở phạm vi collection và timestamp của các phần tử |

Ví dụ không đồng nhất về TTL trong một map:

```text
attributes['tier']   = 'pro'        @ timestamp 100, TTL 3600
attributes['locale'] = 'vi'         @ timestamp 200, TTL  120
attributes['otp']    = 'temporary'  @ timestamp 300, TTL   30

Sau khi otp hết TTL, tier và locale có thể vẫn còn sống.
Nếu writer khác ghi lại otp với timestamp 250, nó có thể
thua tombstone/metadata hết hạn có timestamp 300.
```

**Đồng hồ sai lệch** cũng gây vấn đề ở đây: client có timestamp xa tương lai có thể khiến cập nhật cùng key/field sau đó thua theo LWW. Việc dùng TTL không tự sửa clock skew, và tăng consistency level không thay đổi luật phân xử timestamp.

## 12. Đọc và kiểm tra TTL của collection/UDT

Với cột scalar thông thường, có thể đọc:

```sql
SELECT note, writetime(note), ttl(note)
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

`writetime(note)` trả metadata write timestamp tính theo **micro giây**, còn `ttl(note)` trả **giây còn lại** nếu cell `note` có TTL. Nhưng **không nên giả định có thể gọi `ttl(attributes)` hoặc `writetime(contact)` để lấy mọi timestamp/TTL của tất cả thành phần non-frozen collection/UDT**. Một cột logic có thể chứa nhiều cell với metadata khác nhau; các hàm CQL và cách selector hoạt động trên kiểu phức hợp còn có ràng buộc theo loại dữ liệu/phiên bản Cassandra.

Để quan sát ở mức ứng dụng:

1. **Đọc giá trị hiện tại** theo partition key: `SELECT attributes, labels, milestones, contact, frozen_contact ...`.
2. **Ghi log đường mutation:** phần tử/field nào được ghi, TTL của request, mutation timestamp nếu do client tự đặt, event ID và lần retry.
3. **Đọc lại sau khoảng TTL ngắn trong môi trường thử nghiệm**, kiểm tra key/field/element còn sống đúng kỳ vọng.
4. Khi cần điều tra **TTL và tombstone cụ thể ở từng cell**, dùng công cụ quản trị/SSTable của phiên bản Cassandra tương ứng, trong quy trình vận hành được kiểm soát.

```sql
SELECT attributes, labels, milestones,
       contact, frozen_contact, frozen_attributes, note
FROM ttl_shapes_by_id
WHERE profile_id = 99999999-9999-4999-8999-999999999999;
```

Đừng diễn giải một collection không còn phần tử như bằng chứng duy nhất để phân biệt **chưa ghi**, **đã xóa** và **đã hết TTL**. Cần đối chiếu lịch sử request; tùy kiểu, phiên bản và cách client hiển thị, collection rỗng hoặc không còn dữ liệu sống có thể được biểu diễn khác nhau.

## 13. Ứng dụng Java: ghi một key map và một field UDT có TTL

Trong Java dùng **Apache/DataStax Cassandra Java Driver 4.x**, prepared statement giúp cập nhật đúng một phần tử/field mà không cần ghi lại toàn bộ collection hay UDT. TTL được bind bằng **số giây**; cần lưu ý xử lý lỗi và retry trong hệ thống thực.

```java
import java.util.Map;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ProfileTtlRepository {
    private final CqlSession session;
    private final PreparedStatement updateLocale;
    private final PreparedStatement updateCity;
    private final PreparedStatement readProfile;

    public ProfileTtlRepository(CqlSession session) {
        this.session = session;
        this.updateLocale = session.prepare(
            "UPDATE ttl_shapes_by_id USING TTL ? " +
            "SET attributes['locale'] = ? WHERE profile_id = ?"
        );
        this.updateCity = session.prepare(
            "UPDATE ttl_shapes_by_id USING TTL ? " +
            "SET contact.city = ? WHERE profile_id = ?"
        );
        this.readProfile = session.prepare(
            "SELECT attributes, contact FROM ttl_shapes_by_id " +
            "WHERE profile_id = ?"
        );
    }

    public void setLocale(UUID id, String locale, int ttlSeconds) {
        requirePositiveTtl(ttlSeconds);
        session.execute(updateLocale.bind(ttlSeconds, locale, id));
    }

    public void setCity(UUID id, String city, int ttlSeconds) {
        requirePositiveTtl(ttlSeconds);
        session.execute(updateCity.bind(ttlSeconds, city, id));
    }

    public Map<String, String> getAttributes(UUID id) {
        Row row = session.execute(readProfile.bind(id)).one();
        return row == null ? null
            : row.getMap("attributes", String.class, String.class);
    }

    private static void requirePositiveTtl(int ttlSeconds) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("TTL must be positive");
        }
    }
}
```

`setLocale` dùng TTL cho **key `locale`** vừa được ghi; `setCity` dùng TTL cho **field `city`** của UDT non-frozen. Method không chạm những thành phần khác nên không chủ ý reset TTL của chúng. Đoạn mã giả định bảng/UDT đã tồn tại và `CqlSession` đã kết nối đúng keyspace.

Khi đọc, một key map hoặc field UDT đã hết hạn có thể không còn hiện diện. Code Java phải xử lý **map thiếu key, field `null`, row `null`** thay vì giả định mọi đối tượng luôn đầy đủ. Nếu muốn ghi frozen UDT, cần bind **toàn bộ UDT value** theo codec/API của driver và đặt TTL cho cell frozen đó.

Nếu thời gian sống có ý nghĩa chính xác với nghiệp vụ (ví dụ OTP hoặc khóa phiên), nên lưu thêm thời điểm hết hạn từ **nguồn thời gian đáng tin cậy** và kiểm tra điều kiện nghiệp vụ; TTL của Cassandra không thay thế logic chống dùng lại hay LWT/compare-and-set.

## 14. Chọn mô hình dữ liệu theo vòng đời và truy vấn

Collection có thể thuận tiện để đọc một nhóm thông tin nhỏ cùng một partition. Nhưng collection không phù hợp khi chứa số lượng phần tử tăng không giới hạn, mỗi phần tử phải được truy vấn/lọc độc lập hoặc thường xuyên được cập nhật/xóa với TTL khác nhau.

Ví dụ nghiệp vụ cần truy vấn thông báo của một người dùng theo ngày và thời gian mới nhất:

```sql
CREATE TABLE IF NOT EXISTS notifications_by_account_day (
    account_id uuid,
    notification_day date,
    event_time timeuuid,
    payload text,
    PRIMARY KEY ((account_id, notification_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

-- Mỗi event là một row riêng, có thể nhận TTL riêng khi INSERT.
INSERT INTO notifications_by_account_day (
    account_id, notification_day, event_time, payload
) VALUES (
    22222222-8888-4888-8888-222222222222,
    '2026-11-21',
    now(),
    'New event'
)
USING TTL 3600;
```

Mỗi hàng sự kiện có clustering key riêng; TTL gắn với cell mới trong row đó, thay vì phải giải quyết TTL ở hàng nghìn phần tử trong một list/map. Với dữ liệu có lưu lượng lớn, chọn **time bucket** phù hợp để partition không phát triển quá lớn.

| Yêu cầu nghiệp vụ | Thiết kế đáng cân nhắc |
|---|---|
| Một nhóm thuộc tính nhỏ, key cập nhật độc lập | Non-frozen map |
| UDT có từng field thay đổi và có thể hết hạn riêng | Non-frozen UDT, xử lý field thiếu |
| Snapshot nhất quán như một giá trị, hết hạn cùng lúc | Frozen UDT hoặc frozen collection |
| Lịch sử sự kiện có nhiều phần tử, truy vấn theo thời gian | Bảng row theo event với clustering key |
| Các phần tử cần tìm/xóa theo nhiều chiều truy vấn | Bảng riêng được thiết kế theo từng truy vấn |

**Không dùng mutation timestamp làm clustering key ngầm.** Nếu cần truy vấn theo thứ tự sự kiện, hãy lưu thời gian nghiệp vụ hoặc sequence làm dữ liệu khóa. Mutation timestamp dùng cho LWW ở cell, còn TTL điều khiển thời hạn sống của phiên bản cell.

## 15. Vận hành: tombstone, compaction, repair và replication

Các cell có TTL hết hạn được xử lý như dữ liệu đã xóa; Cassandra cần tombstone/expiration metadata để không làm sống lại dữ liệu cũ từ replica chưa được đồng bộ. Trong một map hoặc UDT có nhiều cell, các thành phần có thể hết hạn vào nhiều thời điểm, gây thêm **tombstone và chi phí đọc/compaction**.

- **Replication factor** quyết định số replica giữ partition; **consistency level** như `ONE`, `QUORUM`, `ALL` quyết định yêu cầu đọc/ghi, nhưng không chuyển TTL riêng của các phần tử thành TTL chung.
- **Repair** giúp các replica hội tụ. Nếu tombstone bị dọn thiếu an toàn khi replica khác vẫn giữ bản cũ, có nguy cơ **zombie data**.
- **Compaction** hợp nhất SSTable và có thể dọn dữ liệu/tombstone khi đủ điều kiện; TTL hết không có nghĩa ngay lập tức giải phóng dung lượng đĩa.
- **Clock skew** giữa host tạo mutation timestamp hoặc node tính expiration có thể ảnh hưởng đến kết quả đọc, thứ tự LWW và nhận thức về thời gian còn sống.
- **Thay toàn bộ collection** hoặc tạo/loại bỏ nhiều phần tử liên tục có thể tăng tombstone. Collection lớn còn gây overhead khi client phải đọc/ghi toàn bộ giá trị frozen.

Trong production, giám sát dung lượng, tombstone, độ trễ đọc, tỷ lệ compaction, repair và độ lớn partition. Không tự giảm `gc_grace_seconds` hoặc xóa SSTable chỉ để rút ngắn thời gian dọn TTL: các thay đổi này liên quan trực tiếp tới an toàn replication.

## 16. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Giải thích có thể có | Cách kiểm tra |
|---|---|---|
| Một key map biến mất trong khi key khác vẫn còn | Các key được ghi với TTL khác nhau | Xem lịch sử `UPDATE map['key']`, TTL của từng mutation |
| Một field UDT thành `null`, field còn lại vẫn có | UDT không frozen, TTL theo field | Xem schema và các lệnh `UPDATE udt.field` |
| Cả frozen map biến mất cùng lúc | Frozen map là một cell với một TTL | Xem lần ghi gần nhất của frozen cell |
| Sửa một key nhưng mất các key khác | Có thể đã **thay toàn bộ map** thay vì sửa phần tử | So sánh `SET map = {...}` với `SET map['k'] = ...` |
| List mất phần tử khiến index thay đổi | Các cell phần tử hết TTL hoặc bị xóa | Không dựa vào index như định danh ổn định |
| Ghi mới nhưng thành phần cũ vẫn thắng | Mutation timestamp thấp hơn hoặc tombstone mới hơn | Kiểm tra nguồn timestamp, retry và clock skew |
| Ghi TTL nhưng đọc thấy không TTL | Mutation thua LWW, hoặc phiên bản mới hơn có `TTL 0` | Lần theo timestamp/TTL của các mutation |
| Dữ liệu hết TTL vẫn chiếm ổ đĩa | Tombstone/dữ liệu chờ compaction an toàn | Quan sát SSTable, compaction, repair và cấu hình grace |

Một quy trình chẩn đoán có hiệu quả:

1. Xác định **schema chính xác**: cột là frozen hay non-frozen, collection loại gì, UDT có field gì, bảng có `default_time_to_live` không.
2. Xác định **phạm vi mutation**: thay toàn bộ collection/UDT hay chỉ key/element/field.
3. Kiểm tra **TTL và timestamp được gán** cho request; xác nhận đơn vị TTL là giây và write timestamp là micro giây.
4. Truy vấn đúng **partition key**, đọc giá trị còn sống; so với log hoạt động và mốc thời gian dự kiến.
5. Nếu nghi ngờ replica/tombstone, đối chiếu CL, health, repair và sử dụng công cụ Cassandra phù hợp với môi trường.

## 17. Bài tập tự kiểm tra

**Câu 1.** Map non-frozen có `['a']` được ghi với TTL 30 giây và `['b']` với TTL 300 giây. Sau 45 giây, chuyện gì có thể xảy ra?

**Đáp án:** Key `a` đã hết hạn và không còn trong kết quả đọc, trong khi `b` vẫn có thể tồn tại. Hai key có metadata TTL riêng.

**Câu 2.** Ghi `frozen<map<text,text>>` có hai key bằng một `UPDATE ... USING TTL 60`. Có thể làm một key hết hạn ở 30 giây chỉ bằng sửa riêng key đó không?

**Đáp án:** Không. Frozen map là một cell. Muốn đổi dữ liệu/TTL phải ghi lại **toàn bộ cell frozen** hoặc thay mô hình thành non-frozen/bảng riêng.

**Câu 3.** UDT non-frozen gồm `street`, `city`, `country`. `UPDATE ... USING TTL 30 SET contact.city = 'Hue'` có gia hạn TTL của `street` không?

**Đáp án:** Không. Mutation cập nhật đúng field `city`; các field khác giữ metadata của phiên bản tương ứng.

**Câu 4.** List chứa `['a','b']`, phần tử `a` hết TTL trước `b`. Có thể coi index 0 luôn là `a` không?

**Đáp án:** Không. Sau khi phần tử `a` không còn sống, list quan sát có thể chỉ còn `b` và index thay đổi.

**Câu 5.** Bảng có `default_time_to_live = 600`. Ghi thêm một phần tử set bằng `USING TTL 0` sẽ làm toàn bộ set không có TTL?

**Đáp án:** Không. Chỉ những cell/phần tử được mutation đó ghi nhận TTL 0; các phần tử cũ giữ metadata riêng.

**Câu 6.** Khi thay `attributes = {'tier': 'basic'}`, vì sao key `locale` có thể biến mất mặc dù TTL còn?

**Đáp án:** Đây là thao tác **thay toàn bộ collection** với semantics xóa các phần tử cũ không được giữ lại, không đơn thuần là cập nhật key `tier`.

**Câu 7.** Có thể dùng `ttl(attributes)` để lấy đầy đủ bảng TTL theo từng key map không?

**Đáp án:** Không nên xem đó là API quan sát metadata từng phần tử. Map non-frozen có nhiều cell với TTL khác nhau; cần kiểm tra khả năng của phiên bản Cassandra và dùng lịch sử mutation/công cụ chẩn đoán thích hợp.

**Câu 8.** Một collection rất lớn, cần truy vấn phần tử mới nhất theo thời gian. Nên tiếp tục thêm vào list hay thiết kế bảng khác?

**Đáp án:** Cân nhắc **row riêng theo sự kiện**, partition theo khóa + time bucket và clustering key theo thời gian/sequence. Thiết kế theo truy vấn thường hiệu quả hơn cho dữ liệu tăng không giới hạn.

---

**Ghi nhớ:** Với **collection/UDT không frozen**, Cassandra có thể lưu **từng phần tử hoặc field như các cell**, nên các thành phần được ghi ở những mutation khác nhau có thể có **TTL và mutation timestamp khác nhau**. Với **frozen collection/UDT**, toàn bộ giá trị là **một cell**, được ghi và hết hạn như một đơn vị. `USING TTL` áp dụng cho thành phần/cell được mutation tác động, kết hợp với `default_time_to_live` và quy tắc last-write-wins. Hiểu cách lưu trữ là điều kiện để dự đoán khi nào từng giá trị hết hạn, tránh tombstone không cần thiết và thiết kế bảng Cassandra theo truy vấn phù hợp.
