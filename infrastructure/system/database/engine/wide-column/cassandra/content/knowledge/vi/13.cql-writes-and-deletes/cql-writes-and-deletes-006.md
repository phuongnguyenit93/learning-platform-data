# UPDATE collection và thao tác trên từng phần tử trong Apache Cassandra

Trong Apache Cassandra, một cột có thể chứa **collection**: `map` (ánh xạ khóa–giá trị), `set` (tập phần tử không trùng) hoặc `list` (dãy phần tử có thứ tự). CQL cho phép **gán lại cả collection** hoặc **thay đổi một phần nội dung** của collection không `frozen`. Chọn sai thao tác có thể làm mất những phần tử đang có, tạo nhiều tombstone hoặc gây xung đột khi nhiều client ghi đồng thời.

Bài này thuộc chương **Ghi và xóa bằng CQL** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trong Cassandra, **partition key** xác định phân vùng và replica lưu dữ liệu; **full primary key** xác định hàng cần cập nhật. Các collection vẫn tuân theo cơ chế ghi phân tán, timestamp, TTL và consistency level. Vì vậy, thiết kế cập nhật collection cần xét cả ngữ nghĩa CQL và cách ứng dụng Java thực thi.

Sau bài học, bạn có thể:

- Phân biệt `map<k,v>`, `set<t>` và `list<t>`, biết trường hợp nào nên dùng mỗi loại.
- Viết `UPDATE` thay cả collection, thêm/xóa phần tử và cập nhật phần tử theo khóa hoặc vị trí.
- Giải thích sự khác nhau giữa **bỏ qua cột**, **gán NULL**, **gán collection mới** và **sửa từng phần tử**.
- Nhận biết hạn chế của collection `frozen`, nguy cơ tranh chấp với `list` và tác động của tombstone/TTL.
- Dùng prepared statement của Java Driver để sửa collection an toàn.

## 1. Mô hình dữ liệu và bảng thử nghiệm

Giả sử dịch vụ hồ sơ người dùng cần lưu một tập nhỏ các tùy chọn, nhãn và danh sách thao tác gần đây. Keyspace `demo` được giả định đã tồn tại:

```sql
CREATE TABLE demo.user_collections_by_id (
    user_id       uuid PRIMARY KEY,
    attributes    map<text, text>,
    tags          set<text>,
    recent_steps  list<text>,
    version       int,
    updated_at    timestamp
);
```

Với bảng này, `user_id` là **partition key** và cũng là **full primary key**. Mỗi lệnh `UPDATE ... WHERE user_id = ...` định vị một hàng logic; ba collection là cột thường, không phải thành phần primary key.

Khởi tạo dữ liệu:

```sql
INSERT INTO demo.user_collections_by_id (
    user_id, attributes, tags, recent_steps, version
)
VALUES (
    11111111-1111-4111-8111-111111111111,
    {'theme': 'light', 'locale': 'vi-VN'},
    {'trial', 'newsletter'},
    ['login', 'browse'],
    1
);

SELECT attributes, tags, recent_steps, version
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Kết quả kỳ vọng (thứ tự trình bày của `map` và `set` không mang ý nghĩa nghiệp vụ):

| Cột | Giá trị ban đầu | Ý nghĩa |
| --- | --- | --- |
| `attributes` | `{'theme': 'light', 'locale': 'vi-VN'}` | Tra cứu giá trị theo khóa cấu hình |
| `tags` | `{'trial', 'newsletter'}` | Nhãn không trùng, không có thứ tự cố định |
| `recent_steps` | `['login', 'browse']` | Danh sách có thứ tự, có thể có phần tử trùng |
| `version` | `1` | Cột thường dùng minh họa điều kiện ghi |

Các ví dụ phần 2–5 **minh họa độc lập về cách viết lệnh**; nếu chạy nhiều lệnh nối tiếp, trạng thái trước mỗi lệnh sẽ là kết quả của tất cả lệnh đã chạy. Phần thực hành cuối bài có chuỗi lệnh và kết quả dự kiến rõ ràng.

### Chọn kiểu collection theo yêu cầu

| Kiểu | Đặc điểm | Cách truy cập/cập nhật điển hình |
| --- | --- | --- |
| `map<text,text>` | Khóa duy nhất, mỗi khóa có một giá trị | `attributes['theme'] = 'dark'` |
| `set<text>` | Không trùng phần tử, không dựa vào vị trí | `tags = tags + {'vip'}` |
| `list<text>` | Có thứ tự và có thể chứa giá trị lặp | `recent_steps = recent_steps + ['checkout']`; `recent_steps[0] = 'open'` |

Collection nên **nhỏ và có giới hạn rõ ràng**. Một luồng sự kiện tăng mãi theo thời gian không phù hợp để nhét vào một `list` lớn của một hàng. Thay vào đó, dùng bảng theo truy vấn với partition key và clustering column, chẳng hạn phân vùng theo người dùng + ngày và các sự kiện được sắp bằng thời gian.

## 2. Gán cả collection khác với cập nhật một phần

Gán trực tiếp một collection bằng `SET column = <collection literal>` có nghĩa **thay thế nội dung của cột collection**:

```sql
UPDATE demo.user_collections_by_id
SET attributes = {'theme': 'dark'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Nếu trước lệnh có `{'theme': 'light', 'locale': 'vi-VN'}`, sau khi gán mới map chỉ còn `{'theme': 'dark'}`; khóa `'locale'` bị loại bỏ. Trong một collection không `frozen`, thay thế toàn bộ thường được biểu diễn bằng dấu xóa phạm vi collection và các phần tử mới.

Điều tương tự đúng với `set` và `list`:

```sql
-- Thay toàn bộ set; các nhãn cũ không nêu sẽ biến mất.
UPDATE demo.user_collections_by_id
SET tags = {'vip'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Thay toàn bộ list bằng hai phần tử theo đúng thứ tự mới.
UPDATE demo.user_collections_by_id
SET recent_steps = ['open', 'checkout']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

**Quy tắc:** `SET tags = {'vip'}` là **replace**, còn `SET tags = tags + {'vip'}` là **thêm vào collection đang có**. Đừng dùng cú pháp replace cho endpoint chỉ muốn “thêm một nhãn”.

### Không nêu cột collection thì sao?

```sql
UPDATE demo.user_collections_by_id
SET version = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Lệnh chỉ ghi `version`; nó **không thay đổi** `attributes`, `tags` hay `recent_steps` vì chúng không có trong `SET`. Trường bị bỏ qua khác với một collection mới rỗng hoặc `NULL`. Quy tắc này cũng áp dụng cho `INSERT` upsert thông thường theo danh sách cột.

## 3. UPDATE map: thêm, sửa và xóa một khóa

Với `map` **không frozen**, Cassandra cho phép cập nhật giá trị tại một khóa mà không phải truyền lại toàn bộ map.

### 3.1. Gán hoặc thêm một cặp khóa–giá trị

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'dark'
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.user_collections_by_id
SET attributes['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

- Nếu khóa `'theme'` đã tồn tại, giá trị ở khóa đó được ghi lại.
- Nếu khóa `'timezone'` chưa tồn tại, Cassandra thêm cặp khóa/giá trị mới.
- Các khóa khác trong `attributes` **không bị chính các mutation này xóa**.

Ví dụ, từ map ban đầu `{'theme':'light','locale':'vi-VN'}`, hai lệnh trên tạo ra map có `theme = dark`, `locale = vi-VN` và `timezone = Asia/Ho_Chi_Minh`.

### 3.2. Thêm nhiều cặp vào map đang có

```sql
UPDATE demo.user_collections_by_id
SET attributes = attributes + {'theme': 'dark', 'lang': 'vi'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Toán tử `+` với map thực hiện **thêm/cập nhật các khóa được nêu** trong map bên phải; nó không xóa những khóa khác. Nếu `theme` đã tồn tại, giá trị của khóa này được ghi lại; `lang` được thêm nếu chưa có.

So sánh:

| CQL | `theme` | `locale` đang tồn tại | `lang` |
| --- | --- | --- | --- |
| `SET attributes = {'theme':'dark', 'lang':'vi'}` | Thay bằng dark | **Bị loại khỏi map** | Được thêm |
| `SET attributes = attributes + {'theme':'dark', 'lang':'vi'}` | Thay bằng dark | **Giữ nguyên** | Được thêm |
| `SET attributes['theme'] = 'dark'` | Thay bằng dark | **Giữ nguyên** | Không ảnh hưởng |

### 3.3. Xóa một khóa khỏi map

```sql
DELETE attributes['locale']
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Lệnh chỉ **xóa phần tử map có khóa `'locale'`**, không xóa toàn bộ cột `attributes`. Cassandra ghi thông tin xóa cho phần tử để các bản dữ liệu cũ hơn không xuất hiện lại khi đọc.

Có thể dùng phép trừ tập các khóa khỏi map:

```sql
UPDATE demo.user_collections_by_id
SET attributes = attributes - {'locale', 'lang'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Trong biểu thức này, vế phải là **set các khóa cần loại bỏ**, không phải một map mới. Việc xóa khóa không có trong map không có nghĩa lỗi “khóa không tồn tại” như xóa một phần tử mảng bắt buộc phải có vị trí.

### 3.4. NULL và khóa map

Không dùng `NULL` làm **map key**. Nếu muốn bỏ cặp `'theme'`, dùng `DELETE attributes['theme']` hoặc một phép cập nhật loại khóa. Nếu gán `attributes = NULL`, ý định là **xóa cả collection**, khác hoàn toàn với xóa riêng một cặp.

Map rất phù hợp cho tập tùy chọn **nhỏ**, nhưng nếu muốn truy vấn tất cả người dùng có `theme='dark'`, một map nằm trong hàng theo `user_id` không tự tạo đường truy cập phân tán hiệu quả theo giá trị đó. Thiết kế Cassandra phải bắt đầu từ truy vấn: có thể cần một bảng khác theo khóa truy vấn phù hợp.

## 4. UPDATE set: thêm và loại phần tử không trùng

`set<text>` lưu tập các giá trị **không lặp**, không có ý nghĩa thứ tự hoặc chỉ số. Với `set` không `frozen`, Cassandra hỗ trợ phép hợp và phép trừ tập hợp.

### Thêm một hoặc nhiều phần tử

```sql
UPDATE demo.user_collections_by_id
SET tags = tags + {'vip'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.user_collections_by_id
SET tags = tags + {'active', 'newsletter'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Nếu tập ban đầu là `{'trial','newsletter'}`, thao tác thêm `'vip'` đưa `'vip'` vào tập; thao tác tiếp theo đưa thêm `'active'`. Việc thêm lại `'newsletter'` không tạo bản sao thứ hai vì đây là `set`.

Thứ tự hiển thị `tags` trong kết quả CQL không phải lịch sử thêm phần tử. Nếu cần biết thứ tự thao tác, `set` không đáp ứng yêu cầu đó.

### Loại bỏ một hoặc nhiều phần tử

```sql
UPDATE demo.user_collections_by_id
SET tags = tags - {'trial'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

UPDATE demo.user_collections_by_id
SET tags = tags - {'vip', 'active'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Các phần tử không nằm trong tập cần xóa không bị tác động bởi hai mutation này. Với set, **không có** cú pháp hợp lệ kiểu `tags[0]` để chỉ phần tử “đầu tiên”, bởi set không được định nghĩa theo vị trí.

### Gán một tập mới hoặc NULL

```sql
-- Thay thế toàn bộ tập bằng các nhãn dưới đây.
UPDATE demo.user_collections_by_id
SET tags = {'vip'}
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Xóa cả giá trị cột collection.
UPDATE demo.user_collections_by_id
SET tags = NULL
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Gán `NULL` có nghĩa yêu cầu xóa giá trị collection; không phải thao tác “bỏ qua trường”. Xóa cả cột còn có thể viết dưới dạng:

```sql
DELETE tags
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Các thao tác xóa trong Cassandra tạo dấu xóa phù hợp với phạm vi dữ liệu bị xóa. Nếu API chỉ muốn gỡ nhãn `'trial'`, hãy dùng `tags = tags - {'trial'}` thay vì gán lại toàn bộ set theo dữ liệu mà client tình cờ đang giữ.

## 5. UPDATE list: vị trí, nối, chèn đầu và xóa

`list<text>` lưu dãy **có thứ tự**, cho phép giá trị trùng nhau. Điều này tạo ra các thao tác không có trên set, đồng thời khiến việc chỉnh phần tử theo vị trí nhạy cảm với ghi cạnh tranh.

### 5.1. Thêm vào cuối danh sách

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps + ['checkout']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Với trạng thái đầu `['login','browse']`, kết quả dự kiến sau lệnh là `['login','browse','checkout']`.

Có thể nối nhiều phần tử cùng lúc:

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps + ['pay', 'confirm']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Những phần tử mới được nối vào danh sách hiện tại; `list` **không** tự loại giá trị trùng nhau.

### 5.2. Thêm vào đầu danh sách

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = ['open'] + recent_steps
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Phép nối đặt một list ở bên trái để đưa phần tử vào đầu. Thêm vào đầu danh sách thường phức tạp và tốn kém hơn thêm vào cuối vì cần xác định thứ tự đối với các phần tử hiện có. Không nên dùng một list ngày càng dài làm nhật ký sự kiện hoặc hàng đợi nhiều producer.

### 5.3. Sửa phần tử tại chỉ số

```sql
-- Chỉ số list bắt đầu từ 0.
UPDATE demo.user_collections_by_id
SET recent_steps[1] = 'search'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Nếu ngay trước thao tác list là `['login','browse']`, chỉ số `1` chỉ phần tử thứ hai và kết quả dự kiến là `['login','search']`. Cập nhật theo chỉ số cần biết **vị trí đang tồn tại**; chọn chỉ số ngoài danh sách hoặc vị trí không còn hợp lệ có thể dẫn tới lỗi.

### 5.4. Xóa phần tử theo chỉ số hoặc theo giá trị

```sql
-- Xóa phần tử đang ở chỉ số 0.
DELETE recent_steps[0]
FROM demo.user_collections_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;

-- Loại phần tử có giá trị 'browse' khỏi list.
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps - ['browse']
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Hai lệnh thể hiện ý nghĩa khác nhau. Xóa theo chỉ số đụng tới **phần tử ở vị trí xác định tại thời điểm thao tác được thực thi**. Xóa theo giá trị hướng tới **các phần tử mang giá trị** trong list, vì list có thể chứa giá trị lặp.

### Vì sao phải cẩn thận với chỉ số list?

Giả sử client A đọc `['login','browse']`, dự định cập nhật vị trí `1`. Trước khi A ghi, client B chèn `'open'` vào đầu hoặc xóa một phần tử. Chỉ số `1` có thể không còn trỏ tới hành động mà A dự kiến. Cơ chế cập nhật theo vị trí cũng có thể cần đọc trạng thái list và không phù hợp với tải ghi cạnh tranh mạnh.

**Khuyến nghị:** chỉ dùng list cho danh sách ngắn, ít tranh chấp và cần giữ thứ tự. Nếu cần cập nhật/xóa sự kiện theo ID một cách ổn định, thiết kế bảng với **clustering key là mã hoặc thời điểm sự kiện** thường phù hợp hơn. Chẳng hạn bảng `events_by_user_day` có partition key `(user_id, event_day)` và clustering key `event_id` hoặc `event_time`, thay vì một list không giới hạn trong một hàng.

## 6. Collection frozen và giới hạn cập nhật từng phần tử

`frozen` thay đổi cách Cassandra xem một collection: toàn bộ collection được xử lý như **một giá trị nguyên khối**. Đọc/ghi cả giá trị thì hợp lệ, nhưng **không** dùng các thao tác sửa từng phần tử như với collection không `frozen`.

Ví dụ bảng có frozen map:

```sql
CREATE TABLE demo.user_frozen_profile_by_id (
    user_id uuid PRIMARY KEY,
    settings frozen<map<text, text>>
);

INSERT INTO demo.user_frozen_profile_by_id (user_id, settings)
VALUES (
    22222222-2222-4222-8222-222222222222,
    {'theme': 'light', 'locale': 'vi-VN'}
);
```

Ghi cả frozen map:

```sql
UPDATE demo.user_frozen_profile_by_id
SET settings = {'theme': 'dark', 'locale': 'vi-VN'}
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Không áp dụng:

```sql
-- SAI: frozen map không hỗ trợ cập nhật trực tiếp phần tử.
UPDATE demo.user_frozen_profile_by_id
SET settings['theme'] = 'dark'
WHERE user_id = 22222222-2222-4222-8222-222222222222;
```

Muốn thay một trường trong `frozen` map, ứng dụng thường phải tạo **giá trị map hoàn chỉnh mới** rồi gán lại. Nếu hai client cùng đọc bản cũ và cùng viết lại toàn bộ map, một cập nhật có thể đè mất phần không liên quan do client kia vừa sửa. Khi có tải ghi cạnh tranh, cân nhắc mô hình cột thường, map không frozen hoặc điều kiện LWT thích hợp.

| Thao tác | `map<text,text>` | `frozen<map<text,text>>` |
| --- | --- | --- |
| Gán toàn bộ map | Có | Có |
| `map_col['k'] = 'v'` | Có | Không |
| `DELETE map_col['k']` | Có | Không |
| Gán `NULL` để xóa cả cột | Có | Có |
| Đơn vị hòa giải điển hình | Theo từng phần tử và dấu xóa collection | Giá trị collection nguyên khối |

Không nên chọn `frozen` chỉ vì tên nghe giống “ít thay đổi”: đó là quyết định **mô hình lưu trữ và phạm vi mutation** cần gắn với kiểu truy cập của ứng dụng.

## 7. NULL, UNSET, tombstone và TTL của collection

Collection không `frozen` thường được Cassandra lưu với thông tin ở mức **phần tử**, thay vì chỉ một blob đại diện cho toàn bộ giá trị. Điều này cho phép cập nhật một phần, nhưng cũng có ảnh hưởng đến tombstone và TTL.

### 7.1. Không gửi cột, gán NULL và gán collection mới

Xét hàng đã có `attributes`, `tags` và `recent_steps`:

| Mutation | Tác động lên collection |
| --- | --- |
| `SET version = 3`, không nhắc `tags` | Không ghi lại `tags` |
| `SET tags = tags + {'vip'}` | Thêm phần tử, giữ phần tử khác |
| `SET tags = {'vip'}` | Thay toàn bộ tập; phần tử cũ không nêu bị loại bỏ |
| `SET tags = NULL` | Xóa giá trị cột collection |
| Prepared statement với marker `tags = UNSET` | Bỏ qua việc ghi cột `tags` |

`NULL` **không giống UNSET**. Gán `NULL` tạo dấu xóa cho cột; `UNSET` là trạng thái tham số của prepared statement để tránh mutation ở cột đó. Khi ứng dụng Java nhận request JSON chỉ có `attributes.theme`, không được tự động bind `tags = NULL` chỉ vì client không gửi tags.

### 7.2. Tombstone ở mức phần tử và toàn collection

Xóa `attributes['locale']` tạo thông tin xóa cho phần tử map, còn gán lại cả map hoặc xóa cả cột cần đánh dấu phạm vi dữ liệu cũ rộng hơn. Việc xóa không có nghĩa Cassandra lập tức loại bỏ mọi bản ghi cũ khỏi SSTable trên tất cả replica.

Trong hệ thống phân tán, một replica có thể tạm thời chưa nhận mutation xóa. **Tombstone** mang timestamp cho phép Cassandra che các giá trị cũ trong quá trình đọc/hòa giải. Repair giúp các replica hội tụ; compaction có thể thu gom dấu xóa và dữ liệu cũ khi đáp ứng điều kiện an toàn. Việc tạo quá nhiều tombstone (ví dụ liên tục replace một collection lớn) có thể khiến truy vấn đọc nặng và gây áp lực cho compaction.

### 7.3. TTL khi ghi phần tử

TTL được chỉ định bằng giây:

```sql
UPDATE demo.user_collections_by_id USING TTL 600
SET attributes['temporary_status'] = 'online'
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Với collection không `frozen`, ghi phần tử bằng TTL có thể làm **phần tử vừa ghi** hết hạn sau 600 giây; các phần tử map khác không tự nhận TTL của lần ghi này. Tương tự, `UPDATE ... USING TTL ... SET tags = tags + {'temporary'}` tác động đến phần tử được thêm; các phần tử cũ không vì thế được gia hạn TTL. Một thao tác **gán lại toàn bộ** collection có phạm vi ghi rộng hơn và có thể ảnh hưởng TTL của nhiều phần tử.

Không dùng TTL như cơ chế “tự dọn ngay tệp dữ liệu”: khi hết hạn, giá trị không còn được đọc như giá trị sống; Cassandra cần xử lý thông tin hết hạn trong quá trình lưu trữ và compaction.

### 7.4. Write timestamp và các phần tử cạnh tranh

Một map không `frozen` có thể nhận hai mutation vào hai khóa khác nhau:

```text
Client A ghi attributes['theme']    = 'dark'
Client B ghi attributes['timezone'] = 'Asia/Ho_Chi_Minh'
```

Nếu hai lần ghi đều thành công, các giá trị ở **hai khóa map khác nhau** có thể cùng tồn tại vì chúng không trực tiếp tranh chấp cùng phần tử. Nhưng hai client cùng ghi `attributes['theme']` thì phiên bản thắng phụ thuộc **timestamp** của phần tử và cơ chế hòa giải dữ liệu Cassandra. Một phép **replace toàn map** cạnh tranh với phép sửa phần tử riêng cũng có thể xóa hoặc che các giá trị ngoài dự kiến.

Lệnh cập nhật collection thông thường không tự kiểm tra trạng thái đã đọc trước đó. Nếu bắt buộc “chỉ sửa khi phiên bản hồ sơ đang là 1”, hãy dùng điều kiện phù hợp, ví dụ lightweight transaction (LWT):

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'dark',
    version = 2
WHERE user_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
```

Kết quả có cột `[applied]` để ứng dụng biết điều kiện có được thỏa không. Cập nhật theo điều kiện thường có chi phí và độ trễ cao hơn mutation không điều kiện; chỉ dùng LWT khi thật sự cần bảo vệ ràng buộc nghiệp vụ.

### 7.5. Consistency level và retry

Replication giúp cùng phân vùng tồn tại trên nhiều node; consistency level quy định mức xác nhận khi đọc/ghi. Ví dụ với replication factor 3, `QUORUM` thông thường yêu cầu hai replica xác nhận trong phạm vi quorum tương ứng. Tuy nhiên, **QUORUM không tự biến các thao tác đọc rồi ghi thành giao dịch có điều kiện**.

Khi client nhận timeout, một số replica có thể đã nhận mutation. Thử lại phép thêm nhãn vào `set` với cùng giá trị thường không tạo nhãn trùng, nhưng thử lại thao tác ghi vào `list` có thể **thêm sự kiện thêm lần nữa**. Đối với những thao tác đòi hỏi “thực hiện chính xác một lần”, cần thiết kế idempotency hoặc lưu mỗi sự kiện bằng một primary key ổn định trong bảng riêng; không nên dựa vào retry mù quáng trên list.

## 8. Java Driver: prepared statement cho từng thao tác

Với Apache Cassandra Java Driver 4.x, nên dùng prepared statement và bind **giá trị**. Các ví dụ sau giả định đã có `CqlSession session` và `UUID userId` hợp lệ; các import được lược bỏ để tập trung vào câu CQL.

### 8.1. Ghi một khóa map

```java
PreparedStatement updateAttribute = session.prepare(
    "UPDATE demo.user_collections_by_id " +
    "SET attributes[:attr_key] = :attr_value " +
    "WHERE user_id = :user_id"
);

BoundStatement updateTheme = updateAttribute.boundStatementBuilder()
    .setString("attr_key", "theme")
    .setString("attr_value", "dark")
    .setUuid("user_id", userId)
    .build();

session.execute(updateTheme);
```

`attr_key` và `attr_value` là **giá trị được bind**, nên không cần nối chuỗi CQL với key và value lấy từ HTTP request. Nếu cho phép client sửa map tùy ý, hãy kiểm tra danh sách khóa được hỗ trợ, giới hạn độ dài và validate giá trị.

### 8.2. Thêm một nhãn vào set

```java
PreparedStatement addTags = session.prepare(
    "UPDATE demo.user_collections_by_id " +
    "SET tags = tags + :to_add " +
    "WHERE user_id = :user_id"
);

BoundStatement addVip = addTags.boundStatementBuilder()
    .setSet("to_add", java.util.Set.of("vip"), String.class)
    .setUuid("user_id", userId)
    .build();

session.execute(addVip);
```

Sử dụng `setSet(...)` phù hợp với CQL `set<text>`. Câu lệnh thêm phần tử được chọn cho yêu cầu “thêm nhãn”; nếu API muốn **thay tất cả nhãn**, mới dùng dạng `SET tags = :new_tags`.

### 8.3. Nối một phần tử vào list

```java
PreparedStatement appendStep = session.prepare(
    "UPDATE demo.user_collections_by_id " +
    "SET recent_steps = recent_steps + :new_steps " +
    "WHERE user_id = :user_id"
);

BoundStatement append = appendStep.boundStatementBuilder()
    .setList("new_steps", java.util.List.of("checkout"), String.class)
    .setUuid("user_id", userId)
    .build();

session.execute(append);
```

Không mặc định retry thao tác nối list sau timeout: gửi lại cùng request có thể nối thêm cùng phần tử lần thứ hai. Nếu nhật ký sự kiện không được phép trùng, mô hình bảng theo event ID thường là lựa chọn phù hợp hơn.

### 8.4. Đọc collection và kiểm tra kết quả

```java
PreparedStatement select = session.prepare(
    "SELECT attributes, tags, recent_steps " +
    "FROM demo.user_collections_by_id WHERE user_id = ?"
);

Row row = session.execute(select.bind(userId)).one();
if (row != null) {
    java.util.Map<String, String> attrs =
        row.getMap("attributes", String.class, String.class);
    java.util.Set<String> labels =
        row.getSet("tags", String.class);
    java.util.List<String> steps =
        row.getList("recent_steps", String.class);
    // Xu ly null va gia tri vắng mat theo hop dong API.
}
```

Đọc `null` từ collection có thể có nghĩa cột chưa được ghi, đã bị xóa hoặc toàn bộ giá trị đã hết hạn. Không nên tự suy diễn trạng thái nghiệp vụ từ riêng kết quả `null`.

### 8.5. Phân biệt collection bị thiếu với JSON null

Ví dụ PATCH:

```json
{
  "attributes": {
    "theme": "dark"
  }
}
```

Hợp đồng API cần làm rõ đây là **merge một phần tử** hay **replace toàn map**. Nếu là patch, backend nên phát sinh `attributes['theme'] = :value`; nó không được tự xóa `locale`. Nếu khách gửi:

```json
{
  "attributes": null
}
```

thì ứng dụng phải quyết định API có cho phép xóa toàn map hay cần trả lỗi validation. **Trường không xuất hiện**, **trường có mặt với null** và **trường có mặt với map rỗng** là ba tình huống khác nhau. Jackson `JsonNode.has(...)`/`isNull()` hoặc field mask có thể giúp giữ nguyên thông tin về sự hiện diện của trường.

Với prepared statement có marker cho cả cột, `UNSET` giúp bỏ qua cập nhật; bind `NULL` mang ý định xóa cột. Khi chỉ sửa một phần tử map hoặc set, nên dùng mẫu câu CQL cụ thể cho thao tác đó để tránh phải đọc và ghi lại toàn bộ collection.

## 9. Thực hành: cập nhật collection từng phần tử

Các bước sau sử dụng **một UUID thực hành riêng** để có thể đối chiếu trạng thái sau từng mutation. Chạy tuần tự trên môi trường thử nghiệm với bảng `demo.user_collections_by_id` đã tạo ở phần 1.

### Bước 1 — Khởi tạo trạng thái

```sql
INSERT INTO demo.user_collections_by_id (
    user_id, attributes, tags, recent_steps, version
)
VALUES (
    33333333-3333-4333-8333-333333333333,
    {'theme': 'light', 'locale': 'vi-VN'},
    {'trial', 'newsletter'},
    ['open', 'browse'],
    1
);

SELECT attributes, tags, recent_steps, version
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Kỳ vọng:** map có hai khóa, set có hai nhãn, list có hai bước theo thứ tự, `version = 1`.

### Bước 2 — Thay một giá trị map và thêm khóa mới

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'dark'
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET attributes['timezone'] = 'Asia/Ho_Chi_Minh'
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Kỳ vọng:** `attributes` có `theme=dark`, `locale=vi-VN` và `timezone=Asia/Ho_Chi_Minh`. Khóa `locale` không bị xóa vì cả hai lần ghi chỉ sửa một khóa map.

### Bước 3 — Thêm và gỡ nhãn set

```sql
UPDATE demo.user_collections_by_id
SET tags = tags + {'vip'}
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET tags = tags - {'trial'}
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Kỳ vọng:** set có `'newsletter'` và `'vip'`; `'trial'` đã bị loại bỏ, không có phần tử trùng.

### Bước 4 — Thêm và sửa phần tử list

```sql
UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps + ['checkout']
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET recent_steps[1] = 'search'
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Kỳ vọng:** list là `['open', 'search', 'checkout']`. Chỉ số `1` trỏ tới phần tử thứ hai của trạng thái sau lệnh nối.

### Bước 5 — Xóa phần tử map và list

```sql
DELETE attributes['locale']
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;

UPDATE demo.user_collections_by_id
SET recent_steps = recent_steps - ['search']
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Kỳ vọng:** map không còn `locale`; list còn `['open', 'checkout']`. Hai thao tác xóa phần tử không xóa cột `version` hay toàn bộ các collection.

### Bước 6 — Đổi map với điều kiện version

```sql
UPDATE demo.user_collections_by_id
SET attributes['theme'] = 'contrast',
    version = 2
WHERE user_id = 33333333-3333-4333-8333-333333333333
IF version = 1;
```

**Kỳ vọng:** lần đầu điều kiện thỏa (nếu không có client khác ghi), `[applied] = true`; `theme = 'contrast'` và `version = 2`. Chạy lại **cùng** câu trên, điều kiện `version = 1` không còn thỏa, nên dự kiến `[applied] = false`. Đây là cách nhận biết một cập nhật bị từ chối vì trạng thái cũ đã thay đổi.

### Bước 7 — Quan sát toàn bộ dữ liệu

```sql
SELECT attributes, tags, recent_steps, version
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

| Thuộc tính | Kết quả dự kiến sau bước 6 |
| --- | --- |
| `attributes` | `{'theme':'contrast', 'timezone':'Asia/Ho_Chi_Minh'}` |
| `tags` | `{'newsletter','vip'}`; thứ tự không quan trọng |
| `recent_steps` | `['open','checkout']` |
| `version` | `2` |

Các kết quả trên giả định không có mutation từ client khác, không có TTL, và các lệnh ghi hoàn tất bình thường.

### Thử khác biệt giữa “thay cả map” và “sửa một phần tử”

Chỉ trên dữ liệu thực hành có thể thay đổi, chạy:

```sql
UPDATE demo.user_collections_by_id
SET attributes = {'theme': 'light'}
WHERE user_id = 33333333-3333-4333-8333-333333333333;

SELECT attributes
FROM demo.user_collections_by_id
WHERE user_id = 33333333-3333-4333-8333-333333333333;
```

**Kỳ vọng:** `timezone` biến mất khỏi map; đây là hành vi **replace toàn collection**, không giống `SET attributes['theme'] = 'light'`. Nếu một client chỉ muốn đổi theme và vô tình ghi câu replace, client đó có thể làm mất những tùy chọn khác.

## 10. Những lỗi thường gặp

| Cách viết hoặc giả định | Rủi ro | Cách xử lý |
| --- | --- | --- |
| `SET attributes = {'theme':'dark'}` để chỉ sửa theme | Làm mất các khóa map còn lại | Dùng `attributes['theme'] = 'dark'` hoặc map merge |
| `SET tags = {'vip'}` để thêm một nhãn | Xóa các nhãn cũ | Dùng `tags = tags + {'vip'}` |
| Dùng `tags[0]` | Set không có chỉ số có ý nghĩa | Thêm/xóa theo giá trị phần tử |
| Cập nhật `recent_steps[1]` dựa trên list đọc từ lâu | Vị trí có thể đã thay đổi | Tránh cập nhật list theo chỉ số khi có ghi cạnh tranh |
| Dùng `list` cho nhật ký vô hạn | Collection lớn, ghi/đọc tốn kém và khó xử lý retry | Thiết kế bảng sự kiện riêng với clustering key |
| Sửa `settings['theme']` khi `settings` là frozen map | Không hỗ trợ cập nhật phần tử | Gán toàn bộ giá trị frozen hoặc đổi mô hình |
| Bind `NULL` cho collection không được gửi trong PATCH | Xóa dữ liệu không mong muốn, tạo tombstone | Dùng UNSET hoặc không đưa cột vào CQL |
| Retry append list sau timeout | Có thể nối phần tử lặp | Dùng event ID ổn định và mô hình idempotent |
| Replace collection lớn nhiều lần | Nhiều tombstone, tăng chi phí đọc và compaction | Sửa phần tử nếu phù hợp; giới hạn kích thước collection |
| Dựa vào `QUORUM` để đảm bảo read-modify-write nguyên tử | Hai client vẫn có thể tranh chấp | Dùng LWT/`IF` khi cần điều kiện hoặc mô hình riêng |

## 11. Câu hỏi kiểm tra và nguyên tắc thiết kế

1. **Khác biệt giữa `SET attributes = {'theme':'dark'}` và `SET attributes['theme'] = 'dark'`?** Lệnh đầu thay **toàn bộ map**, lệnh sau chỉ sửa khóa `theme`.
2. **Thêm nhãn vào set có làm trùng nhãn không?** Không; `set` chỉ chứa giá trị duy nhất.
3. **Có thể cập nhật `set` bằng chỉ số như list không?** Không, vì `set` không có thứ tự vị trí.
4. **`DELETE recent_steps[0]` khác `recent_steps = recent_steps - ['open']` thế nào?** Lệnh đầu xóa phần tử ở vị trí `0`; lệnh sau loại phần tử theo giá trị `'open'`.
5. **Có thể sửa trực tiếp một phần tử của `frozen<map<text,text>>` không?** Không; cần gán lại cả giá trị hoặc chọn schema không frozen.
6. **Gán `tags = NULL` có giống bỏ trường tags khỏi PATCH không?** Không; `NULL` có ý nghĩa xóa collection, còn bỏ qua hoặc bind UNSET là không cập nhật.
7. **Tại sao không nên nối một sự kiện vào list rồi retry vô điều kiện khi timeout?** Vì mutation trước có thể đã thành công, nên retry có thể ghi sự kiện lần thứ hai.
8. **Hai client cùng sửa khóa map `theme` thì ai thắng?** Kết quả phụ thuộc cơ chế hòa giải theo timestamp; nếu yêu cầu dựa vào giá trị cũ, dùng LWT phù hợp.

Khi thiết kế bảng Cassandra phục vụ ứng dụng Java, hãy đặt câu hỏi: collection có thực sự **nhỏ, giới hạn và thường được đọc cùng một hàng** không? Có cần truy vấn hoặc cập nhật **từng phần tử theo định danh ổn định** không? Có nhiều writer hoặc cần retry khi mạng lỗi không? Nếu câu trả lời cho các câu sau là có, một bảng riêng với partition key và clustering key có thể phù hợp hơn việc nhét tất cả phần tử vào một collection.

**Ghi nhớ:** `UPDATE` collection có hai phạm vi rất khác nhau: **thay toàn bộ giá trị** hoặc **thao tác trên phần tử**. `Map` phù hợp với sửa theo khóa, `set` phù hợp với thêm/gỡ giá trị không trùng, còn `list` phù hợp với dữ liệu ngắn có thứ tự nhưng cần thận trọng với chỉ số và retry. Tách rõ NULL/UNSET, frozen/non-frozen, TTL/tombstone và yêu cầu đồng thời giúp các mutation CQL chính xác trong hệ thống Cassandra phân tán.
