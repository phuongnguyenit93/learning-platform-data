# list, set, map và lựa chọn cấu trúc dữ liệu trong Apache Cassandra

Trong Apache Cassandra, **`list`**, **`set`** và **`map`** là ba kiểu *collection* của CQL, giúp lưu một nhóm giá trị trong một cột của một hàng. Chúng khác nhau ở **thứ tự**, **khả năng trùng lặp**, **cách tra cứu từng phần tử**, **cách cập nhật** và **chi phí vận hành**. Một `list` không phải bảng lịch sử thu nhỏ; một `set` không phải chỉ mục tìm kiếm theo thẻ; một `map` không tự biến Cassandra thành cơ sở dữ liệu document.

Bài này thuộc chương **Kiểu dữ liệu** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Nội dung đặt các collection vào thiết kế wide-column phân tán: chọn **partition key và clustering columns theo truy vấn**, ghi/đọc bằng CQL, xử lý retry và xung đột, theo dõi tombstone, compaction, repair, replication và ánh xạ sang ứng dụng Java. Nguyên tắc xuyên suốt: **collection phù hợp với một nhóm phần tử nhỏ, có giới hạn và thường được đọc cùng nhau; dữ liệu lớn hoặc tăng vô hạn nên được mô hình hóa thành nhiều hàng**.

## 1. So sánh nhanh list, set và map

| Tiêu chí | `list<T>` | `set<T>` | `map<K,V>` |
|---|---|---|---|
| Mục đích | Dãy phần tử **có thứ tự** | Tập giá trị **không trùng lặp** | Ánh xạ **khóa → giá trị** |
| Có thể chứa phần tử trùng? | **Có** | **Không** | Khóa là duy nhất; giá trị có thể trùng |
| Ý nghĩa thứ tự | Vị trí/thứ tự phần tử có ý nghĩa | Không có thứ tự chèn mang nghĩa nghiệp vụ | Không có thứ tự chèn mang nghĩa nghiệp vụ |
| Truy cập phần tử | Theo vị trí/chỉ số trong các thao tác CQL hỗ trợ | Theo giá trị thành viên | Theo khóa của map |
| Phép cập nhật điển hình | Nối/thêm đầu, xóa giá trị, thay phần tử theo index | Thêm/bớt phần tử | Gán/xóa entry theo key |
| Retry cùng thao tác thêm | **Có thể thêm trùng** khi append/prepend | Thêm cùng thành viên không tạo bản sao logic, nhưng có lưu ý concurrency | Gán cùng khóa/giá trị không tạo khóa trùng, nhưng có lưu ý concurrency |
| Hợp với | Một số ID được ghim theo thứ tự, danh sách bước nhỏ | Thẻ nội bộ, tập tính năng nhỏ | Cấu hình tùy chọn có khóa động, nhỏ |
| Không nên dùng cho | Event log vô hạn, timeline ghi đồng thời | Danh sách thành viên tăng vô hạn | Kho dữ liệu tùy ý không giới hạn số key |

**`T`, `K`, `V` là các kiểu CQL**: ví dụ `list<uuid>`, `set<text>`, `map<text, int>`. Cassandra áp dụng quy tắc kiểu của từng thành phần. Không nên nhét nội dung JSON bất kỳ vào một collection rồi coi đó là lược đồ ổn định.

### 1.1. Chọn collection theo câu hỏi nghiệp vụ

- “Người dùng ghim **ba đoạn trích theo thứ tự**” → `list<uuid>` có thể phù hợp nếu số phần tử được giới hạn và ít ghi đồng thời.
- “Bài viết có các **nhãn không trùng**” → `set<text>`, nếu tập nhãn nhỏ và không cần tìm bài viết toàn cluster chỉ qua nhãn trong cột đó.
- “Mỗi người dùng có **theme**, **font_size**, **language** dưới dạng key/value linh hoạt” → `map<text,text>`, nếu tập cấu hình có giới hạn và được kiểm soát.
- “Ghi **mọi sự kiện click** của người dùng trong nhiều năm” → **bảng nhiều hàng**, dùng khóa phân vùng/bucket và clustering theo thời gian; không dùng `list` phình to.
- “Tìm mọi bài viết có nhãn `cassandra`” → đường truy cập theo nhãn, index được đánh giá theo phiên bản/tải, hoặc **bảng truy vấn riêng**; `set<text>` trong một row không tự giải quyết.

Cần tách hai câu hỏi: **“giá trị được biểu diễn bằng cấu trúc nào?”** và **“Cassandra lấy những hàng nào cho truy vấn này?”**. Collection trả lời câu đầu; partition/clustering/index trả lời câu sau.

## 2. Mô hình lưu trữ: collection nằm trong một row

Một bảng CQL có thể chứa nhiều kiểu dữ liệu:

~~~cql
CREATE TABLE reading_state_by_user_article (
    user_id uuid,
    article_id uuid,
    tags set<text>,
    pinned_highlight_ids list<uuid>,
    display_options map<text, text>,
    updated_at timestamp,
    PRIMARY KEY ((user_id, article_id))
);
~~~

Ở đây, `(user_id, article_id)` là **partition key tổng hợp**. Mỗi cặp người dùng–bài viết là một phân vùng độc lập; cả ba collection là **cột dữ liệu của row đó**, không phải những phân vùng mới. Mẫu truy vấn được phục vụ là **đọc trạng thái một bài viết cụ thể của một người dùng** khi đã biết cả hai ID.

~~~cql
INSERT INTO reading_state_by_user_article (
    user_id, article_id, tags, pinned_highlight_ids,
    display_options, updated_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    {'cassandra', 'java'},
    [33333333-3333-4333-8333-333333333333],
    {'theme': 'dark', 'font_size': '16'},
    '2026-11-21T08:00:00Z'
);

SELECT tags, pinned_highlight_ids, display_options, updated_at
FROM reading_state_by_user_article
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND article_id = 22222222-2222-4222-8222-222222222222;
~~~

Trong ví dụ:

- `{'cassandra', 'java'}` là **set literal**.
- `[uuid]` là **list literal**.
- `{'theme': 'dark', 'font_size': '16'}` là **map literal**.
- Dữ liệu được lấy qua **đầy đủ partition key**; Cassandra không cần dò từng collection trên toàn bộ cluster.

**Không được suy rằng** bảng này phục vụ tốt câu hỏi “liệt kê tất cả bài viết của một người dùng”: truy vấn chỉ có `user_id` mà thiếu `article_id` không cung cấp đủ partition key. Để liệt kê bài viết theo người dùng hoặc theo thời gian, cần mô hình đọc riêng.

## 3. list<T>: có thứ tự và có thể trùng phần tử

### 3.1. Ngữ nghĩa danh sách

`list<T>` biểu diễn một **dãy**. Hai phần tử cùng giá trị vẫn có thể tồn tại tại hai vị trí khác nhau:

~~~cql
CREATE TABLE demo_lists_by_id (
    id uuid PRIMARY KEY,
    steps list<text>
);

INSERT INTO demo_lists_by_id (id, steps)
VALUES (
    44444444-4444-4444-8444-444444444444,
    ['DRAFT', 'REVIEW', 'REVIEW', 'PUBLISH']
);
~~~

`REVIEW` được lặp lại **hai lần**; đây không phải lỗi kiểu dữ liệu. `list` thích hợp nếu lặp là có nghĩa, chẳng hạn những bước thao tác hoặc các item ghim theo thứ tự do người dùng chọn.

Những điểm cần cân nhắc:

1. Thứ tự trong list được duy trì như một phần ngữ nghĩa danh sách.
2. Thêm/bớt ở đầu có thể làm thay đổi **index** của các phần tử phía sau.
3. Một phần tử có thể xuất hiện nhiều lần; “xóa theo giá trị” khác “xóa đúng một phần tử có ID duy nhất”.
4. List không thay thế **clustering order** để đọc nhiều hàng của một timeline.

### 3.2. CQL append, prepend và xóa phần tử

~~~cql
-- Thêm vào cuối danh sách.
UPDATE demo_lists_by_id
SET steps = steps + ['ARCHIVE']
WHERE id = 44444444-4444-4444-8444-444444444444;

-- Thêm vào đầu danh sách.
UPDATE demo_lists_by_id
SET steps = ['START'] + steps
WHERE id = 44444444-4444-4444-8444-444444444444;

-- Xóa phần tử theo giá trị (không phải theo ID sự kiện).
UPDATE demo_lists_by_id
SET steps = steps - ['REVIEW']
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

Phép trừ theo giá trị có thể loại các phần tử khớp giá trị đang tồn tại. Nếu nghiệp vụ phân biệt “lần REVIEW thứ nhất” và “lần REVIEW thứ hai”, hãy dùng **ID riêng cho từng sự kiện**, thay vì chỉ lưu chuỗi trạng thái trong list.

CQL còn có thao tác theo **chỉ số** cho list không frozen, ví dụ:

~~~cql
-- Minh họa thao tác theo index; kết quả phụ thuộc
-- vị trí phần tử hiện tại và các ghi đồng thời.
UPDATE demo_lists_by_id
SET steps[0] = 'CREATED'
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

**Không coi index là định danh bền vững.** Hai client có thể đọc một list, cùng hiểu “phần tử thứ 0” là A rồi chỉnh list theo thứ tự khác nhau. Các thao tác theo index hoặc xóa phần tử theo giá trị cũng có thể cần đọc trạng thái list và gây chi phí/độ phức tạp hơn thao tác gán một khóa riêng.

### 3.3. Retry append/prepend: nguy cơ thêm trùng

Giả sử worker gửi:

~~~cql
UPDATE demo_lists_by_id
SET steps = steps + ['SEND_EMAIL']
WHERE id = 44444444-4444-4444-8444-444444444444;
~~~

Client nhận **timeout**, nhưng một số replica có thể đã áp dụng mutation. Nếu client chạy lại phép append với cùng nội dung, list có thể nhận **hai phần tử `SEND_EMAIL`**, bởi append không phải phép gán theo khóa phần tử bền vững.

Đây là lý do list không nên dùng làm:

- Hàng đợi công việc phải xử lý **mỗi task đúng một lần**.
- Audit log, event stream hoặc lịch sử thanh toán.
- Bộ đếm số lần hành động.
- Timeline tăng vô hạn với nhiều writer và retry.

Đối với những trường hợp này, chọn **mỗi sự kiện một row với `event_id` ổn định** và clustering theo thời gian hoặc sequence. Không dùng mức nhất quán cao hơn như `LOCAL_QUORUM` để thay thế tính idempotent của ID.

### 3.4. Danh sách nhỏ nào phù hợp?

Ví dụ: một người dùng chọn **tối đa năm highlight ID** để hiển thị theo thứ tự ghim. Với giới hạn rõ ràng, ít cập nhật đồng thời và khả năng xử lý retry, `list<uuid>` có thể là lựa chọn gọn.

Nếu cần ghi chú, trạng thái, tác giả, thời điểm tạo và chỉnh sửa riêng từng highlight, nên lưu mỗi highlight thành **một row**, và list chỉ giữ một danh sách ID ghim nhỏ nếu thật sự cần. Khi user sắp xếp lại danh sách, ứng dụng phải có quy tắc version/concurrency rõ ràng để tránh hai thiết bị ghi đè thứ tự của nhau.

## 4. set<T>: thành viên duy nhất, không có thứ tự chèn

### 4.1. Ngữ nghĩa tập hợp

`set<T>` có **mỗi giá trị tối đa một lần**. Thêm lại cùng một giá trị không tạo bản sao thứ hai về mặt membership:

~~~cql
CREATE TABLE demo_tags_by_article (
    article_id uuid PRIMARY KEY,
    tags set<text>
);

INSERT INTO demo_tags_by_article (article_id, tags)
VALUES (
    55555555-5555-4555-8555-555555555555,
    {'java', 'cassandra'}
);

UPDATE demo_tags_by_article
SET tags = tags + {'cassandra', 'wide-column'}
WHERE article_id = 55555555-5555-4555-8555-555555555555;
~~~

Tập kết quả có các thành viên `java`, `cassandra` và `wide-column` (không có `cassandra` lặp lại). Cassandra tổ chức phần tử set theo comparator của kiểu dữ liệu để phục vụ lưu trữ; **không được phụ thuộc vào thứ tự hiển thị như thứ tự người dùng đã thêm**.

Muốn xóa thành viên:

~~~cql
UPDATE demo_tags_by_article
SET tags = tags - {'java'}
WHERE article_id = 55555555-5555-4555-8555-555555555555;
~~~

Xóa phần tử tạo thông tin xóa/tombstone theo mô hình collection. Một tập thay đổi rất thường xuyên với nhiều lần xóa có thể tích tụ tombstone; cần đo trên workload thực tế.

### 4.2. “Thêm set là idempotent” đúng ở mức nào?

Phép **thêm cùng giá trị vào tập** không tạo hai membership giống hệt nhau, nên thường **dễ retry hơn list append**. Tuy nhiên, không được suy rộng thành:

- Mọi thao tác trên set đều là giao dịch *exactly-once*.
- Một thao tác thêm và xóa cạnh tranh sẽ có kết quả theo thời gian thực do người dùng nhìn thấy.
- Thay toàn bộ set từ hai client sẽ tự hợp nhất hai thay đổi.
- Retry không tác động đến metadata ghi, TTL hoặc các xung đột khác.

Cassandra giải quyết xung đột dựa trên metadata ghi. Nếu việc thêm/bớt một nhãn cần quy tắc thứ tự nghiệp vụ chính xác, dùng event/version hoặc cơ chế điều kiện (LWT) phù hợp. **Idempotency của cấu trúc giá trị** không đồng nghĩa **tính đúng đắn của quy trình phân tán**.

### 4.3. Uniqueness không tự chuẩn hóa dữ liệu

Với `set<text>`, chuỗi `"Java"` và `"java"` là hai giá trị khác nhau. Tương tự, hai chuỗi Unicode có thể hiển thị giống nhau nhưng có dạng NFC/NFD khác byte.

Nếu tag được coi là không phân biệt hoa–thường, hãy tạo **canonical tag** ở biên ứng dụng trước khi bind, chẳng hạn NFC + một chính sách case folding thống nhất. Đừng mong set tự diễn giải `"Café"` và `"café"` (dấu kết hợp) thành một nhãn.

### 4.4. Set không tự tạo chỉ mục ngược

Bảng `demo_tags_by_article` phục vụ truy vấn:

~~~cql
SELECT tags
FROM demo_tags_by_article
WHERE article_id = 55555555-5555-4555-8555-555555555555;
~~~

Nhưng truy vấn “lấy mọi bài viết có tag `cassandra`” không được phục vụ trực tiếp chỉ nhờ có `set<text>`. Một số phiên bản/cấu hình Cassandra cung cấp phương án chỉ mục cho phần tử collection, nhưng **cú pháp và chi phí phụ thuộc phiên bản, cardinality, phân phối dữ liệu và tải**.

Nếu truy vấn theo tag là đường đọc chính ở quy mô lớn, thường nên đánh giá **bảng ngược theo tag + bucket**, như minh họa ở phần thiết kế truy vấn. Không tự thêm `ALLOW FILTERING` trên toàn cluster để thay cho một mô hình dữ liệu phù hợp.

## 5. map<K,V>: các entry theo khóa

### 5.1. Map không phải một JSON document tùy ý

`map<K,V>` lưu các cặp **khóa → giá trị**. Các khóa cùng một map là duy nhất; gán lại một khóa sẽ cập nhật giá trị của entry đó theo quy tắc ghi, không thêm entry có cùng key.

Ví dụ:

~~~cql
CREATE TABLE preferences_by_user (
    user_id uuid PRIMARY KEY,
    options map<text, text>
);

INSERT INTO preferences_by_user (user_id, options)
VALUES (
    66666666-6666-4666-8666-666666666666,
    {'theme': 'dark', 'font_size': '16', 'language': 'vi'}
);
~~~

Map hợp lý vì tập khóa được kiểm soát và người dùng thường đọc **toàn bộ cấu hình nhỏ**. Nó không tự hỗ trợ mọi phép truy vấn/filter như một document database.

Map này không nên trở thành nơi chứa:

- Mọi log message theo key timestamp.
- Hàng trăm nghìn cặp ID → object dài.
- Dữ liệu mỗi key có vòng đời, TTL, phân quyền hoặc mẫu truy vấn hoàn toàn khác.
- Các field có kiểu khác nhau nhưng bị ép hết thành `text`, rồi không còn hợp đồng kiểu rõ ràng.

Nếu cấu trúc là cố định (`theme`, `font_size`, `language`) và cần kiểm tra kiểu độc lập, **các cột riêng hoặc UDT** cũng có thể phù hợp hơn. Map có ích nhất khi key động nhưng **giới hạn**.

### 5.2. Gán một entry, thêm nhiều entry và xóa key

~~~cql
-- Gán một key trong map.
UPDATE preferences_by_user
SET options['theme'] = 'light'
WHERE user_id = 66666666-6666-4666-8666-666666666666;

-- Hợp nhất các entry được nêu vào map.
UPDATE preferences_by_user
SET options = options + {'font_size': '18', 'contrast': 'high'}
WHERE user_id = 66666666-6666-4666-8666-666666666666;

-- Xóa riêng entry theo key.
DELETE options['contrast']
FROM preferences_by_user
WHERE user_id = 66666666-6666-4666-8666-666666666666;
~~~

Điều quan trọng là **phân biệt gán một entry** với **thay toàn bộ map**:

~~~cql
-- Thay thế toàn bộ collection bằng map mới,
-- không phải chỉ sửa một key trong map cũ.
UPDATE preferences_by_user
SET options = {'theme': 'dark'}
WHERE user_id = 66666666-6666-4666-8666-666666666666;
~~~

Sau thao tác thay toàn bộ, các key như `font_size` hay `language` không còn là phần của map mới. Ghi lại nguyên map cũng có thể tạo collection-level tombstone/ảnh hưởng tương tranh; tránh dùng kiểu *read whole map → sửa một key → write whole map* khi nhiều client có thể cập nhật song song.

### 5.3. Retry gán cùng key và xung đột đồng thời

Với thao tác `options['theme'] = 'dark'`, gửi lại cùng key/value không tạo thêm entry trùng key. Nhưng điều đó **không bảo đảm**:

- Retry một mutation sau khi có một cập nhật mới hơn sẽ không gây ảnh hưởng do metadata write timestamp.
- Hai writer thay cùng key luôn tuân theo thứ tự nghiệp vụ ở phía client.
- Ghi nhiều key vào nhiều row/partition sẽ trở thành một giao dịch ACID chung.

Đối với cấu hình không nhạy cảm, mô hình last-write-wins có thể chấp nhận. Với định mức tiền, quyền truy cập, trạng thái phê duyệt hoặc dữ liệu cần kiểm soát concurrency, nên dùng mô hình cụ thể và điều kiện ghi phù hợp, không chỉ dựa vào map.

### 5.4. Map không có “thứ tự ưu tiên” mặc định

Map có thể được đọc/hiển thị theo comparator của kiểu khóa, nhưng **không mang ý nghĩa thứ tự chèn**. Nếu nghiệp vụ cần cấu hình được sắp theo độ ưu tiên, hãy lưu thứ tự **tường minh** hoặc mô hình một hàng mỗi bước với clustering key `priority`.

`map<text,text>` cũng không tự kiểm tra `theme` thuộc `dark/light` hay `font_size` là số nguyên hợp lệ. Những ràng buộc này cần validation trước khi bind, hoặc chọn schema có các cột được typed rõ ràng.

## 6. Non-frozen và frozen collection: khác biệt thiết yếu

Trong Cassandra, collection có thể lưu theo mô hình **non-frozen** hoặc **frozen**. Đây là quyết định về **cách cập nhật và so sánh**, không chỉ cú pháp type.

| Tính chất | Non-frozen (thông dụng) | `frozen<...>` |
|---|---|---|
| Biểu diễn logic | Có thể cập nhật các phần tử/entry riêng | Cả collection là **một giá trị** |
| Cập nhật một phần tử `set`/`map` | Có, theo thao tác được CQL hỗ trợ | Không cập nhật riêng phần tử; thay **cả giá trị** |
| Xóa entry/element riêng | Có theo cú pháp tương ứng | Thay cả giá trị; không DELETE riêng entry |
| Đổi collection | Có thể thay toàn bộ | Có thể thay toàn bộ |
| Tombstone | Có thể có tombstone ở mức element/collection | Xóa/thay giá trị ở cấp cell; không có mutation element riêng |
| Phù hợp | Nhóm phần tử nhỏ cần sửa từng thành viên | Một cấu trúc nhỏ, bất biến theo nghiệp vụ và thường thay toàn bộ |

Ví dụ:

~~~cql
CREATE TABLE visual_presets_by_id (
    preset_id uuid PRIMARY KEY,
    preset_name text,
    colors frozen<map<text, text>>
);

INSERT INTO visual_presets_by_id (preset_id, preset_name, colors)
VALUES (
    77777777-7777-4777-8777-777777777777,
    'Dark',
    {'background': '#111111', 'foreground': '#eeeeee'}
);
~~~

Cột `colors` là **frozen map**: có thể `SET colors = { ... }` để thay toàn bộ, nhưng **không được** kỳ vọng cập nhật `colors['background']` riêng như với map non-frozen.

~~~cql
UPDATE visual_presets_by_id
SET colors = {'background': '#000000', 'foreground': '#ffffff'}
WHERE preset_id = 77777777-7777-4777-8777-777777777777;
~~~

Một số kiểu collection **frozen** có thể hợp lệ trong các vị trí/kiểu lồng nhau mà non-frozen bị hạn chế; tuy nhiên, **không nên dùng collection lớn làm primary key** chỉ để bỏ qua giới hạn của collection thường. Khóa cần ổn định, có domain rõ ràng và phục vụ truy vấn; `uuid`, `text`, `timestamp` hay một khóa tổng hợp thường dễ vận hành hơn.

### 6.1. Nested collection và UDT

Nếu cần một `list` các object nhỏ, có thể dùng **frozen UDT** hoặc collection lồng nhau theo cú pháp hỗ trợ của phiên bản CQL, nhưng cần xem lại yêu cầu trước khi đi sâu:

- **UDT** phù hợp cho một cấu trúc có tên field và schema ổn định.
- **Map** phù hợp cho nhóm thuộc tính đồng kiểu, key động và có giới hạn.
- **List/set** phù hợp cho các phần tử cùng kiểu với ngữ nghĩa thứ tự/tập hợp.
- **Bảng riêng** phù hợp khi mỗi phần tử cần ID, TTL, cập nhật, truy vấn hay vòng đời độc lập.

Lồng nhiều tầng collection không khiến Cassandra tự trở thành document store: cập nhật, tombstone, dung lượng một row và cách truy vấn vẫn là những giới hạn quan trọng.

## 7. Giới hạn dữ liệu trong collection: nhỏ và có biên

Đây là quy tắc thiết kế quan trọng hơn việc chọn list hay set theo cú pháp.

**Collection dùng tốt nhất khi:**

1. Số phần tử có **giới hạn xác định** bằng nghiệp vụ.
2. Mỗi phần tử **nhỏ** và thường được trả cùng row.
3. Ứng dụng không cần page qua từng phần tử như qua nhiều row.
4. Không có yêu cầu ghi vô hạn hoặc concurrency cao trên từng entry.
5. Không cần tra cứu toàn cluster theo từng phần tử mà không có đường truy cập khác.

Một vài ví dụ định lượng *minh họa*, không phải giới hạn tối đa của Cassandra:

| Dữ liệu | Quy tắc nghiệp vụ | Lựa chọn |
|---|---|---|
| 5 highlight ID được ghim | Tối đa 5, người dùng sắp thứ tự | `list<uuid>` |
| 10 thẻ phân loại trên một bài | Tối đa 10, không trùng | `set<text>` |
| 15 tùy chọn giao diện | Tối đa 15 key động, giá trị ngắn | `map<text,text>` |
| 50.000 click mỗi ngày và tăng mãi | Không có biên nhỏ | **Bảng nhiều row** |
| Hàng triệu key/value cấu hình cho tenant | Mỗi key có vòng đời/query độc lập | **Bảng theo tenant + key/bucket** |

CQL collection không phải một danh sách có thể **phân trang tùy ý theo phần tử** với throughput tương đương bảng có clustering key. Đọc collection lớn có thể kéo nhiều dữ liệu không cần thiết qua coordinator và driver, làm tăng network/GC, kích thước cell/row và chi phí compaction/repair.

**Tác động của việc xóa:** xóa một phần tử trong non-frozen set/map hoặc thay/xóa collection có thể sinh tombstone; list thay đổi thường xuyên cũng có chi phí mutation phức tạp. Đừng xây một collection lớn rồi hy vọng compaction sẽ tự biến nó thành bảng tối ưu.

### 7.1. Empty, NULL và UNSET cần phân biệt

Ở một **non-frozen collection**, giá trị rỗng có thể không tồn tại như một cell “rỗng có nội dung” độc lập; cách CQL và driver hiển thị một tập rỗng, null hoặc giá trị chưa lưu phụ thuộc dạng thao tác và phiên bản. Với một collection **frozen**, cả giá trị được lưu thành một cell nên cần xem quy tắc biểu diễn empty ở cấp giá trị đó.

Vì vậy, nếu hệ thống phải phân biệt chặt chẽ:

- Chưa từng cấu hình tag.
- Đã cấu hình và cố ý chọn **0 tag**.
- Đã xóa toàn bộ tag.

thì **không nên dùng sự khác nhau giữa empty collection và NULL làm nguồn chân lý duy nhất**. Hãy lưu một trường trạng thái/phiên bản riêng, hoặc mô hình sự kiện rõ ràng. Với PATCH, **UNSET** nghĩa là không sửa cột; **NULL** có nghĩa xóa trong mutation; giá trị rỗng mang ý nghĩa theo quy tắc collection/cell, không nên suy đoán thay thế.

### 7.2. NULL không phải phần tử hợp lệ

Không nên đưa **null element** vào `list`/`set`, hoặc null key/value vào `map` rồi mong có ý nghĩa “trường thiếu” tương tự JSON. Collection trong Cassandra có quy tắc chặt chẽ về kiểu phần tử; một phần tử hoặc key null không phải giá trị thành viên thông thường.

Nếu cần một field tùy chọn bên trong một cấu trúc, xem xét UDT với các field nullable theo quy tắc CQL, hoặc dùng bảng/cột riêng có mô hình dữ liệu rõ ràng; không sử dụng null sentinel tùy tiện trong collection.

## 8. Java Driver 4.x: ánh xạ các collection

Với Apache Cassandra Java Driver 4.x, những ánh xạ thường gặp:

| CQL | Kiểu Java | Ghi với `BoundStatementBuilder` | Đọc với `Row` |
|---|---|---|---|
| `list<uuid>` | `List<UUID>` | `setList(index, list, UUID.class)` | `getList("column", UUID.class)` |
| `set<text>` | `Set<String>` | `setSet(index, set, String.class)` | `getSet("column", String.class)` |
| `map<text,text>` | `Map<String,String>` | `setMap(index, map, String.class, String.class)` | `getMap("column", String.class, String.class)` |

Các generic type ở Java không tự xác định kiểu dữ liệu CQL khi runtime type erasure xảy ra, vì vậy các phương thức cần **class của phần tử**, hoặc bạn dùng `GenericType` phù hợp với type phức tạp theo driver.

### 8.1. Ghi cả ba collection bằng prepared statement

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

// CqlSession session = ...; // Đã cấu hình cluster/keyspace.

UUID userId = UUID.fromString("11111111-1111-4111-8111-111111111111");
UUID articleId = UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID highlightId = UUID.fromString("33333333-3333-4333-8333-333333333333");

Set<String> tags = Set.of("cassandra", "java");
List<UUID> pinned = List.of(highlightId);
Map<String, String> options = Map.of(
    "theme", "dark",
    "font_size", "16"
);

PreparedStatement insert = session.prepare(
    "INSERT INTO reading_state_by_user_article "
  + "(user_id, article_id, tags, pinned_highlight_ids, "
  + " display_options, updated_at) "
  + "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.boundStatementBuilder()
    .setUuid(0, userId)
    .setUuid(1, articleId)
    .setSet(2, tags, String.class)
    .setList(3, pinned, UUID.class)
    .setMap(4, options, String.class, String.class)
    .setInstant(5, Instant.parse("2026-11-21T08:00:00Z"))
    .build();

session.execute(bound);
~~~

Dùng `Set.of`/`Map.of` (Java 9+) để tạo dữ liệu đầu vào nhỏ, bất biến; nếu cần hỗ trợ Java cũ hơn, có thể thay bằng `HashSet`/`HashMap` với validation tương ứng. Với ứng dụng async, không chỉnh sửa collection nguồn hoặc object có thể được codec sử dụng khi thao tác chưa hoàn tất; tạo snapshot bất biến khi cần.

### 8.2. Đọc và kiểm tra NULL

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

PreparedStatement find = session.prepare(
    "SELECT tags, pinned_highlight_ids, display_options "
  + "FROM reading_state_by_user_article "
  + "WHERE user_id = ? AND article_id = ?");

Row row = session.execute(find.bind(userId, articleId)).one();

if (row == null) {
    // Không có row tương ứng khóa này.
} else {
    Set<String> storedTags = row.isNull("tags")
        ? null : row.getSet("tags", String.class);

    List<UUID> storedPinned = row.isNull("pinned_highlight_ids")
        ? null : row.getList("pinned_highlight_ids", UUID.class);

    Map<String, String> storedOptions = row.isNull("display_options")
        ? null : row.getMap("display_options", String.class, String.class);

    // Phân biệt row vắng mặt với cột chưa có giá trị.
}
~~~

Nếu cần thay đổi collection sau khi đọc, nên tạo bản sao hoặc cấu trúc DTO phù hợp thay vì phụ thuộc object mà driver trả về có mutable hay không. Với map, kiểm tra key tồn tại và giá trị hợp lệ theo hợp đồng: `get("theme") == null` không tự chứng minh user đã chủ động xóa theme.

### 8.3. Cập nhật riêng một thành viên qua Java

Để tránh đọc cả set và ghi lại toàn bộ set, sử dụng mutation CQL có toán tử collection:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.Set;

PreparedStatement addTag = session.prepare(
    "UPDATE reading_state_by_user_article "
  + "SET tags = tags + ? "
  + "WHERE user_id = ? AND article_id = ?");

session.execute(
    addTag.boundStatementBuilder()
        .setSet(0, Set.of("wide-column"), String.class)
        .setUuid(1, userId)
        .setUuid(2, articleId)
        .build()
);
~~~

Câu lệnh thêm một thành viên không yêu cầu client **đọc set hiện tại rồi ghi toàn bộ set**. Tuy vậy, khi nhiều writer đồng thời thêm/xóa cùng phần tử, kết quả vẫn chịu quy tắc concurrency/write timestamp của Cassandra. Không tự suy rằng thao tác an toàn tuyệt đối cho mọi nghiệp vụ chỉ vì không có read-modify-write ở client.

Với map:

~~~java
PreparedStatement updateTheme = session.prepare(
    "UPDATE reading_state_by_user_article "
  + "SET display_options['theme'] = ? "
  + "WHERE user_id = ? AND article_id = ?");

session.execute(
    updateTheme.bind("light", userId, articleId)
);
~~~

Nếu chỉ muốn cập nhật một key, cách này rõ ràng hơn việc đọc cả map, thay key trong Java rồi ghi nguyên map trở lại.

### 8.4. Xử lý các trường PATCH tùy chọn

Khi REST API chỉ gửi một phần fields, phải phân biệt:

- **Không được gửi**: giữ nguyên cột/collection bằng cách không đưa vào mutation hoặc dùng **UNSET** trên prepared statement.
- **Được gửi với giá trị mới**: ghi collection hoặc cập nhật element tương ứng.
- **Được gửi với explicit null**: nếu hợp đồng định nghĩa là clear, chủ động xóa (NULL/DELETE), hiểu rõ tombstone sinh ra.

Không dùng `setToNull` cho tất cả trường không được gửi trong PATCH. Với non-frozen collections, một lần thay toàn bộ hoặc xóa phải được nhìn nhận khác một lần thêm entry.

## 9. Concurrency: tại sao thay nguyên collection dễ mất cập nhật?

Giả sử ban đầu:

~~~text
tags = {'java'}
~~~

Hai client cùng đọc trạng thái này:

~~~text
Client A: muốn thêm 'cassandra' -> tính {'java','cassandra'}
Client B: muốn thêm 'database'  -> tính {'java','database'}
~~~

Nếu cả hai chạy `SET tags = {...}` để **thay toàn bộ collection**, một lần ghi có thể thắng hoặc làm thay đổi kết quả cuối khiến tag mà client khác mới thêm biến mất. Tính toán read–modify–write tại client **không được Cassandra tự khóa tuần tự như một transaction SQL**.

Tùy mục đích, có thể chọn:

1. **Mutation ở mức phần tử** như `tags = tags + {'cassandra'}`: tránh ghi lại toàn bộ collection chỉ vì thêm một tag, giảm phạm vi tác động.
2. **Điều kiện ghi** với lightweight transaction `IF` hoặc version rõ ràng nếu một quy trình cần so sánh trạng thái trước khi cập nhật; phải đánh giá hiệu năng và khả năng biểu đạt của CQL.
3. **Event log với ID bất biến** rồi tổng hợp trạng thái nếu cần lịch sử/audit hoặc chống ghi trùng nghiêm ngặt.
4. **Một hàng mỗi thành viên** nếu số phần tử lớn và mỗi phần tử có concurrency/TTL/truy vấn độc lập.

**Đặc biệt đối với list**, phép append mang tính thêm phần tử mới và có thể trùng khi retry. Nếu một người dùng nhấn “thêm highlight” rồi client timeout, cần `highlight_id` ổn định và một row riêng nếu yêu cầu là “một highlight thực tồn tại tối đa một lần”.

### 9.1. Không đánh đồng consistency level với transaction

Chẳng hạn `LOCAL_QUORUM` yêu cầu đủ replica xác nhận theo replication strategy. Nó **không** có nghĩa:

- Hai client thay nguyên map được hợp nhất từng key theo ý định.
- Một list append được thực hiện *exactly once* sau retry.
- Ghi sang hai bảng theo hai partition sẽ tự có rollback như transaction ACID.
- Đọc một collection rồi cập nhật sau đó được bảo vệ khỏi client khác sửa.

Mỗi yêu cầu nghiệp vụ cần chọn một mức đảm bảo thích hợp: có thể chấp nhận last-write-wins cho tùy chọn giao diện, nhưng không nên dùng cùng cách đó cho sổ cái, hạn mức tín dụng hay phân quyền.

## 10. Thiết kế bảng thay collection tăng vô hạn

### 10.1. Bài toán: highlight có nội dung và lịch sử

Một người dùng có thể tạo hàng nghìn highlight cho một bài trong thời gian dài. Mỗi highlight có ID, ngày tạo, nội dung, trạng thái riêng; cần đọc 50 highlight mới nhất trong một ngày.

**Không nên** gộp mọi highlight vào `list<frozen<...>>` hoặc `map<uuid,text>` của một row tăng mãi. Thay vào đó:

~~~cql
CREATE TABLE highlights_by_user_article_day (
    user_id uuid,
    article_id uuid,
    highlight_day date,
    highlighted_at timestamp,
    highlight_id uuid,
    excerpt text,
    PRIMARY KEY (
        (user_id, article_id, highlight_day),
        highlighted_at, highlight_id
    )
) WITH CLUSTERING ORDER BY (highlighted_at DESC, highlight_id ASC);
~~~

Một truy vấn phù hợp:

~~~cql
SELECT highlighted_at, highlight_id, excerpt
FROM highlights_by_user_article_day
WHERE user_id = 11111111-1111-4111-8111-111111111111
  AND article_id = 22222222-2222-4222-8222-222222222222
  AND highlight_day = '2026-11-21'
LIMIT 50;
~~~

Ưu điểm:

- Mỗi highlight có **primary key riêng** và dễ dùng lại khi retry.
- Có thể lấy **50 dòng đầu** theo clustering order mà không đọc một collection khổng lồ.
- Có thể cập nhật/xóa riêng từng highlight, theo dõi tombstone ở mức hàng.
- Có thể điều chỉnh bucket theo ngày/giờ khi dữ liệu tăng.

Cần bảo đảm `highlight_day` được tính từ `highlighted_at` theo **timezone quy ước**; nếu ngày theo UTC khi ghi và theo địa phương khi đọc, client có thể truy vấn sai partition. Khi số sự kiện rất lớn ngay trong một ngày, hãy đo kích thước partition và cân nhắc shard/bucket nhỏ hơn.

### 10.2. Bài toán: tìm bài viết theo tag

Nếu truy vấn chủ đạo là “tìm các bài được gắn tag `cassandra` trong một ngày của tenant”, một đường truy cập rõ ràng là:

~~~cql
CREATE TABLE article_refs_by_tenant_tag_day (
    tenant_id uuid,
    tag text,
    tag_day date,
    tagged_at timestamp,
    article_id uuid,
    PRIMARY KEY ((tenant_id, tag, tag_day), tagged_at, article_id)
) WITH CLUSTERING ORDER BY (tagged_at DESC, article_id ASC);
~~~

Truy vấn:

~~~cql
SELECT tagged_at, article_id
FROM article_refs_by_tenant_tag_day
WHERE tenant_id = 88888888-8888-4888-8888-888888888888
  AND tag = 'cassandra'
  AND tag_day = '2026-11-21'
LIMIT 50;
~~~

Đây là **bảng đảo chiều** phục vụ đường đọc theo tag, không phải bản sao tự động của `set<text>`. Khi thêm/bớt tag, hệ thống phải cập nhật mapping và xử lý retry, đối soát, xóa/TTL theo chính sách.

Nếu có hàng triệu bài cùng tag trong một ngày, partition `(tenant_id, tag, tag_day)` có thể vẫn lớn hoặc nóng; cần thiết kế bucket/shard và mô hình phân trang dựa trên workload. Một bảng theo truy vấn không phải giải pháp miễn phí cho mọi trường hợp; phải đo throughput và kích thước partition thực tế.

### 10.3. Bảng riêng hay index?

Không có một đáp án tuyệt đối. Cassandra có các cơ chế secondary index/Storage-Attached Index (SAI) tùy phiên bản và triển khai, và một số cơ chế hỗ trợ truy vấn trên collection. Tuy nhiên cần xác nhận **phiên bản Cassandra**, kiểu collection được index, toán tử hỗ trợ, cardinality, độ chọn lọc, kích thước phân vùng và chi phí ghi/đọc.

Đối với đường truy vấn thiết yếu, thường nên bắt đầu từ một bảng có **partition key phù hợp**. Chỉ chọn index khi đã kiểm thử đúng tải, có kế hoạch vận hành và hiểu tác động đến replication, compaction và repair.

## 11. Collection và tombstone, TTL, compaction, repair

### 11.1. Tombstone ở cấp element và collection

Cassandra dùng tombstone để ghi nhận xóa trong hệ thống nhiều replica. Với collection:

- Xóa một phần tử khỏi `set` hoặc một key khỏi `map` tạo thông tin xóa tương ứng để tránh dữ liệu cũ hiện lại.
- Thay nguyên một **non-frozen collection** có thể dùng collection-level tombstone để che các phần tử cũ không còn thuộc tập mới.
- Với `list`, việc thêm/xóa theo vị trí/giá trị và sắp xếp nội bộ có thể tạo chi phí và tombstone phức tạp hơn kỳ vọng “một mảng Java”.
- Với **frozen**, collection được xử lý như một giá trị hoàn chỉnh thay vì các mutation element độc lập.

Việc tạo nhiều tombstone là bình thường khi nghiệp vụ thực sự xóa dữ liệu. Nhưng một hệ thống liên tục xóa/viết lại map 10.000 key để đổi duy nhất `theme` tạo tải không cần thiết so với cập nhật một entry.

### 11.2. TTL và vòng đời dữ liệu

TTL trong Cassandra được xác định theo **giây** cho dữ liệu ghi, và hết hạn có thể dẫn tới tombstone. Với collection không frozen, mỗi mutation/element có thể có vòng đời lưu trữ chịu tác động của các câu lệnh ghi tương ứng. Không giả định tất cả phần tử luôn có cùng thời gian hết hạn nếu chúng được thêm ở những thời điểm khác nhau.

Nếu các phần tử có **lịch sử/TTL riêng**, cần kiểm tra cách cập nhật CQL có áp dụng TTL theo ý định hay không; đôi khi một hàng cho mỗi phần tử là thiết kế dễ hiểu hơn. Với nghiệp vụ cần “chính xác thời điểm hết hạn của từng item”, thiết kế một `expires_at timestamp` và đường truy vấn theo deadline có thể thích hợp hơn việc trông chờ TTL như một scheduler.

### 11.3. Replication và repair không tự gỡ lỗi logic

- **Replication** lưu các mutation/giá trị trên nhiều replica theo partition key.
- **Repair** giúp replica đồng bộ trạng thái, không phục hồi phần tử mà ứng dụng vô tình thay nguyên collection.
- **Compaction** tổ chức lại SSTable và xử lý tombstone theo điều kiện dọn dẹp; không biến collection lớn thành bảng được phân vùng tốt.
- **Consistency level** điều chỉnh mức xác nhận, không loại được list append trùng hoặc lost update do read–modify–write.

Nếu hệ thống đồng bộ collection giữa nhiều vùng hoặc nhiều client offline, phải quy định rõ chiến lược merge/conflict/version. Một collection của Cassandra không tự là CRDT list/map/set đầy đủ đáp ứng mọi kịch bản đồng bộ ngoại tuyến.

## 12. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `list` lưu mọi click/log | Collection lớn vô hạn, khó page và sửa từng sự kiện | Một row mỗi sự kiện, clustering theo thời gian |
| Retry `list = list + [x]` sau timeout | Có thể xuất hiện x hai lần | ID sự kiện ổn định, bảng sự kiện riêng nếu cần |
| Dùng `set` khi cần thứ tự chèn | Không có thứ tự nghiệp vụ | `list` nhỏ hoặc bảng có clustering order |
| Dùng `list` khi cần uniqueness | Có thể thêm giá trị trùng | `set` hoặc ID/khóa ổn định trong bảng |
| Giả định `map` giữ thứ tự ưu tiên | Không có insertion order | Lưu thứ tự/priority riêng |
| Ghi toàn bộ map khi sửa một key | Gây ghi đè không chủ ý/tombstone | `map['key'] = value` với non-frozen |
| Thay toàn bộ set từ hai client cạnh tranh | Có thể mất thành viên mới | Update phần tử hoặc version/điều kiện ghi |
| Dùng collection non-frozen như primary key | Không hợp lệ theo ràng buộc kiểu | Khóa scalar phù hợp, collection làm cột dữ liệu |
| Cập nhật entry của `frozen<map<...>>` | Không hỗ trợ mutation riêng entry | Ghi thay toàn bộ frozen value hoặc dùng non-frozen |
| Xem hai tag khác Unicode normalization là một | Set có thể chứa hai biến thể | Canonicalize trước khi bind |
| Lưu `null` làm element/key | Không phải phần tử bình thường hợp lệ | Mô hình trạng thái/cột/UDT riêng |
| Xem empty collection như trạng thái nghiệp vụ chắc chắn | Empty/null có thể nhập nhằng | Lưu cờ/trạng thái riêng nếu cần |
| Truy vấn toàn cluster theo `tags CONTAINS ...` mà không thiết kế index | Không phù hợp/chi phí lớn | Bảng truy vấn theo tag hoặc index đã benchmark |
| Để collection quá lớn trong một row | Tăng network, GC, I/O, compaction/repair | Giới hạn kích thước, tách thành nhiều row |
| Coi `LOCAL_QUORUM` là exactly-once | Lỗi retry/concurrency vẫn tồn tại | Idempotency, stable key, version/LWT phù hợp |

## 13. Bài tập thực hành

### Bài 1 — Chọn kiểu phù hợp

Một hệ thống đọc sách có:

1. Tối đa 4 highlight ID mà người dùng ghim theo thứ tự.
2. Tối đa 8 nhãn phân loại không được trùng.
3. 12 lựa chọn giao diện tùy theo key.
4. Hàng triệu sự kiện cuộn trang cần xem theo thời gian.

**Đáp án gợi ý:** (1) `list<uuid>` nếu đã kiểm soát concurrency/retry; (2) `set<text>`; (3) `map<text,text>` hoặc các cột/UDT nếu schema cố định; (4) **bảng sự kiện nhiều row** có partition bucket và clustering thời gian.

### Bài 2 — Retry list

Client gửi `UPDATE ... SET pinned_ids = pinned_ids + [id]`, nhận timeout rồi thử lại.

**Câu hỏi:** client có thể dựa vào list để chắc chắn `id` chỉ xuất hiện một lần không?

**Đáp án:** không. Append có thể được áp dụng nhiều lần. Nếu cần chỉ có một highlight theo ID, dùng row với khóa `highlight_id` ổn định hoặc cơ chế idempotency riêng; `set<uuid>` chỉ phù hợp khi không cần giữ thứ tự.

### Bài 3 — Set và Unicode

Một set `set<text>` nhận `"Java"`, `"java"`, `"café"` (NFC) và `"café"` (NFD).

**Câu hỏi:** Cassandra có tự coi hai cặp tên nhìn tương đương là một thành viên không?

**Đáp án:** không. Set ngăn trùng theo giá trị CQL, không tự chuẩn hóa chữ hoa–thường hoặc Unicode. Ứng dụng cần một quy tắc canonicalization nhất quán.

### Bài 4 — Map update hay replace?

Ban đầu:

~~~text
options = {'theme': 'dark', 'font_size': '16'}
~~~

Dùng:

~~~cql
UPDATE preferences_by_user
SET options = {'theme': 'light'}
WHERE user_id = 66666666-6666-4666-8666-666666666666;
~~~

**Câu hỏi:** `font_size` có được giữ lại chắc chắn không?

**Đáp án:** không. Lệnh gán **toàn bộ map** thay collection bằng map chỉ còn `theme`. Muốn thay riêng theme, dùng `SET options['theme'] = 'light'`.

### Bài 5 — Thiết kế truy vấn theo nhãn

Schema `articles_by_id(article_id uuid PRIMARY KEY, tags set<text>)`; yêu cầu “50 bài viết mới nhất có tag `cassandra` theo tenant/ngày”.

**Câu hỏi:** chỉ đổi `set<text>` thành `list<text>` có giải quyết không?

**Đáp án:** không. Cần đường truy cập theo `tenant + tag + day` với clustering theo thời điểm, hoặc index được chứng minh hỗ trợ và đủ hiệu năng; collection type không tự quyết định khả năng truy vấn này.

## 14. Checklist khi review collection Cassandra

- [ ] Dữ liệu cần **thứ tự**, **uniqueness** hay **key → value**?
- [ ] Có giới hạn cụ thể về **số phần tử**, kích thước mỗi phần tử và kích thước cả collection?
- [ ] Có cần query/page/cập nhật riêng hàng nghìn phần tử? Nếu có, đã cân nhắc **bảng nhiều row**?
- [ ] Có chọn **list** mà yêu cầu idempotent dưới retry? Đã xử lý nguy cơ append/prepend trùng?
- [ ] Có chọn **set** nhưng kỳ vọng thứ tự chèn hoặc tự động case folding/Unicode normalization?
- [ ] Map có thật sự cần key động, hay nên dùng các cột typed/UDT để có schema rõ ràng?
- [ ] Đã hiểu **frozen = thay cả giá trị**, non-frozen có thao tác per-element theo cú pháp hỗ trợ?
- [ ] Có tránh read-modify-write rồi ghi lại nguyên map/set khi nhiều client có thể cập nhật cùng lúc?
- [ ] Có phân biệt **NULL, UNSET, empty** theo hợp đồng nghiệp vụ?
- [ ] Mọi thao tác đều có **đầy đủ partition key**; có cần bảng/index ngược để tìm theo phần tử?
- [ ] Java Driver có dùng `setList/getList`, `setSet/getSet`, `setMap/getMap` với đúng kiểu generic?
- [ ] TTL, tombstone, compaction, repair và tính nhất quán có được đo/thiết kế theo vòng đời từng phần tử?
- [ ] Retry giữ ID/khóa nghiệp vụ ổn định, không dựa vào consistency level để bảo đảm exactly-once?
- [ ] Đã có giới hạn tăng trưởng partition và kế hoạch migration nếu collection vượt tải dự kiến?

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Types, Collections](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/types.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html).
- [Apache Cassandra Java Driver 4.x — Object Mapping / CQL to Java](https://apache.github.io/cassandra-java-driver/4.18.0/core/data_types/).

**Ghi nhớ:** dùng **`list`** cho một dãy **nhỏ, có thứ tự**, **`set`** cho tập **nhỏ, không trùng**, **`map`** cho các cặp **key/value nhỏ, có giới hạn**. Non-frozen có thể cập nhật phần tử theo cú pháp hỗ trợ; frozen là một giá trị phải thay cả cụm. Khi cần nhiều phần tử, lịch sử dài, phân trang hoặc truy vấn theo thành viên, hãy dùng **những hàng Cassandra có primary key và clustering columns thiết kế theo truy vấn**, đồng thời xử lý retry, concurrency, tombstone và repair đúng ngữ nghĩa phân tán.

