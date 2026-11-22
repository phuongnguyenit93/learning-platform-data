# Khóa phân vùng và khóa phân cụm trong hệ hỗ trợ

## 1. Bài toán đặt ra trong mô hình cột rộng

Một hệ thống học tập ghi nhận hàng triệu sự kiện mỗi ngày: người học mở khóa, bắt đầu bài, hoàn thành bài, làm bài kiểm tra. Câu hỏi thường gặp không phải “tìm mọi sự kiện trên toàn hệ thống” mà là:

- Lấy 20 hoạt động gần nhất của người học L001.
- Hiển thị lịch sử của L001 trong ngày 14/11.
- Lấy các sự kiện của một thiết bị trong khoảng 08:00–09:00.
- Tra cứu tiến độ của người học trong từng khóa.

Với một hệ NoSQL **mô hình cột rộng (wide-column)**, cấu trúc dữ liệu cần giúp máy chủ tìm đúng nhóm bản ghi và đọc theo thứ tự phù hợp, đồng thời phân phối tải qua nhiều máy. Trong các hệ hỗ trợ như **Apache Cassandra** và **ScyllaDB**, hai thành phần có vai trò quan trọng:

1. **Khóa phân vùng (partition key):** Xác định các hàng thuộc cùng một phân vùng logic; trong Cassandra, giá trị khóa được ánh xạ qua partitioner thành token để xác định trách nhiệm lưu trữ và sao chép.
2. **Khóa phân cụm (clustering key, gồm một hoặc nhiều clustering columns):** Xác định thứ tự và danh tính hàng **bên trong cùng phân vùng**.

Một bảng được thiết kế tốt cho câu hỏi “các hoạt động mới nhất của L001 trong ngày D” có thể tìm đến phân vùng dành cho L001/ngày D và đọc hàng theo thời gian giảm dần. Nhưng cùng bảng đó có thể không phù hợp với câu hỏi “mọi sự kiện thuộc khóa học C001 trong tháng”.

**Mục tiêu bài học:** Hiểu hai loại khóa, đọc đúng cú pháp PRIMARY KEY trong CQL, thiết kế bảng theo truy vấn, dự đoán các giới hạn tìm kiếm/sắp xếp và nhận diện rủi ro về phân vùng lớn, điểm nóng, phân trang, tính duy nhất và nhất quán.

> Các ví dụ chính sử dụng ngôn ngữ CQL của Cassandra/ScyllaDB. Các hệ khác thường được xếp vào nhóm wide-column có thể sử dụng row key hoặc sort key với ngữ nghĩa khác. Không áp dụng trực tiếp cú pháp CQL cho mọi sản phẩm.

## 2. Từ phân vùng logic đến phân phối dữ liệu

### 2.1. Partition key tạo nhóm dữ liệu nào?

Giả sử có những hoạt động sau:

| tenantId | learnerId | ngày | thời điểm UTC | hoạt động |
|---|---|---|---|---|
| T1 | L001 | 2026-11-14 | 08:15 | OPEN_COURSE |
| T1 | L001 | 2026-11-14 | 08:19 | START_LESSON |
| T1 | L001 | 2026-11-14 | 08:31 | COMPLETE_LESSON |
| T1 | L001 | 2026-11-15 | 09:40 | LOGIN |
| T1 | L002 | 2026-11-14 | 09:05 | OPEN_COURSE |

Nếu chọn partition key gồm **(tenantId, learnerId, ngày)**, các hàng được nhóm như sau:

~~~text
Partition (T1, L001, 2026-11-14)
    08:31 COMPLETE_LESSON
    08:19 START_LESSON
    08:15 OPEN_COURSE

Partition (T1, L001, 2026-11-15)
    09:40 LOGIN

Partition (T1, L002, 2026-11-14)
    09:05 OPEN_COURSE
~~~

Ba hàng đầu có cùng partition key nên thuộc cùng một **phân vùng logic**, dù giá trị thời điểm và loại hoạt động khác nhau.

### 2.2. Partition không đồng nghĩa với máy chủ

Trong Cassandra, partitioner tính **token** dựa trên khóa phân vùng. Những khoảng token được gán trách nhiệm cho các nút; dữ liệu còn được sao chép tới các replica theo cấu hình. Vì vậy:

- Partition key quyết định cách định vị phân vùng theo cơ chế token.
- Một phân vùng có thể được lưu trên nhiều replica.
- Một node lưu nhiều phân vùng khác nhau.
- Clustering key không tự quyết định phân vùng sẽ nằm trên node nào.

~~~mermaid
flowchart LR
    A["Giá trị partition key"] --> B["Partitioner / token"]
    B --> C["Các replica phụ trách token"]
    C --> D["Các hàng cùng partition"]
    D --> E["Sắp theo clustering columns"]
~~~

Không nên hình dung mỗi người học được gắn cứng với một máy. Việc thêm node, rebalance hoặc thay đổi topology có thể làm vị trí lưu trữ vật lý thay đổi mà partition key của ứng dụng vẫn giữ nguyên.

### 2.3. Phân vùng là phạm vi quan trọng khi đọc

Khi biết đầy đủ partition key, một truy vấn có thể xác định nhóm dữ liệu cần đọc. Nếu không biết giá trị khóa phân vùng, hệ thống có thể cần chỉ mục khác, đường truy cập khác, hoặc phép quét tốn kém.

Ví dụ “lịch sử L001 trong ngày D” phù hợp với (tenantId, learnerId, ngày). Nhưng nếu chỉ biết tenantId mà muốn tìm hoạt động của mọi người học, ta không có một giá trị partition key đầy đủ; phải xem lại đường truy cập thay vì mặc định WHERE tùy ý giống SQL.

## 3. Đọc cú pháp PRIMARY KEY trong CQL

### 3.1. Dạng tổng quát

~~~sql
PRIMARY KEY (
    (partition_col_1, partition_col_2),
    clustering_col_1,
    clustering_col_2
)
~~~

Trong trường hợp này:

| Thành phần | Chức năng |
|---|---|
| partition_col_1 + partition_col_2 | Một **khóa phân vùng ghép** (composite partition key) |
| clustering_col_1 | Tiêu chí phân cụm đầu tiên trong partition |
| clustering_col_2 | Tiêu chí phân cụm tiếp theo nếu cột trước bằng nhau |
| Toàn bộ các cột trên | **Primary key đầy đủ** định danh một hàng |

Điều quan trọng là **dấu ngoặc**. Hai khai báo:

~~~sql
PRIMARY KEY (tenant_id, learner_id, occurred_at)

PRIMARY KEY ((tenant_id, learner_id), occurred_at)
~~~

khác nhau:

- Dòng đầu: partition key chỉ là **tenant_id**; clustering columns lần lượt là learner_id và occurred_at.
- Dòng thứ hai: partition key là **(tenant_id, learner_id)**; clustering column là occurred_at.

Với dòng đầu, mọi dữ liệu của một tenant có thể nằm trong cùng phân vùng logic, dù có nhiều learner. Với dòng thứ hai, mỗi cặp tenant–learner có một phân vùng riêng.

### 3.2. Trường hợp chỉ có partition key

~~~sql
CREATE TABLE learner_profile (
    learner_id text PRIMARY KEY,
    display_name text,
    level text
);
~~~

Bảng này có một hàng cho mỗi learner_id. Không có các hàng cùng partition được phân biệt bằng clustering columns.

### 3.3. Trường hợp một partition key và một clustering column

~~~sql
CREATE TABLE course_progress_by_learner (
    learner_id text,
    course_id text,
    progress_percent int,
    updated_at timestamp,
    PRIMARY KEY (learner_id, course_id)
);
~~~

Ở đây **learner_id** là partition key; **course_id** là clustering column. Các hàng tiến độ của cùng một learner được nhóm chung; mỗi course_id giúp phân biệt một hàng.

### 3.4. Trường hợp partition key ghép và nhiều clustering columns

~~~sql
CREATE TABLE activity_by_learner_day (
    tenant_id text,
    learner_id text,
    activity_day date,
    occurred_at timestamp,
    event_id uuid,
    course_id text,
    activity_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, learner_id, activity_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Cách phân tích:

~~~text
Partition key  : (tenant_id, learner_id, activity_day)
Clustering     : (occurred_at, event_id)
Full primary key: (tenant_id, learner_id, activity_day,
                   occurred_at, event_id)
~~~

- Các sự kiện của một người học trong một ngày thuộc cùng partition.
- **occurred_at DESC** sắp những sự kiện mới hơn trước trong partition.
- **event_id ASC** phân biệt hai hàng nếu occurred_at giống nhau và xác định thứ tự phụ.
- **course_id, activity_type, payload** là những cột dữ liệu thông thường. Chúng không tự tạo đường tìm kiếm hiệu quả theo course_id hoặc activity_type.

Clustering columns là một phần của primary key, **không phải chỉ mục phụ**. Chỉ mục phụ là một cơ chế riêng có chi phí và giới hạn truy vấn riêng.

## 4. Tính duy nhất của một hàng

Trong Cassandra, một hàng được định danh theo **full primary key**. Với bảng activity_by_learner_day:

~~~text
(T1, L001, 2026-11-14, 08:15, E01) -> hàng thứ nhất
(T1, L001, 2026-11-14, 08:15, E02) -> hàng thứ hai
(T1, L001, 2026-11-14, 08:19, E03) -> hàng thứ ba
~~~

Hai hàng có thể cùng tenant, learner, ngày và thời điểm, miễn là **event_id khác nhau**. Nếu hai yêu cầu dùng **chính xác cùng full primary key**, chúng hướng tới cùng hàng logic.

Trong CQL, INSERT thông thường có ngữ nghĩa **upsert**: nếu khóa đã tồn tại, dữ liệu có thể được cập nhật theo quy tắc ghi của hệ thống. Đừng mặc định INSERT luôn từ chối khóa trùng như một số câu lệnh SQL có unique constraint.

Ví dụ minh họa chèn sự kiện:

~~~sql
INSERT INTO activity_by_learner_day (
    tenant_id, learner_id, activity_day,
    occurred_at, event_id, course_id,
    activity_type, payload
) VALUES (
    'T1', 'L001', '2026-11-14',
    '2026-11-14T08:15:00Z',
    550e8400-e29b-41d4-a716-446655440001,
    'C001', 'OPEN_COURSE',
    '{"source":"dashboard"}'
);
~~~

Nếu muốn thao tác **chỉ tạo khi hàng chưa tồn tại**, các hệ CQL hỗ trợ có thể dùng điều kiện:

~~~sql
INSERT INTO activity_by_learner_day (
    tenant_id, learner_id, activity_day,
    occurred_at, event_id, activity_type
) VALUES (
    'T1', 'L001', '2026-11-14',
    '2026-11-14T08:15:00Z',
    550e8400-e29b-41d4-a716-446655440001,
    'OPEN_COURSE'
) IF NOT EXISTS;
~~~

Trong Cassandra, điều kiện này dùng cơ chế **lightweight transaction (LWT)**, có chi phí cao hơn ghi thông thường. Cần quyết định có thật sự cần điều kiện duy nhất tại điểm ghi, hay có thể dùng full key ổn định và ghi idempotent.

**Quan trọng:** Nếu retry cùng một sự kiện nhưng ứng dụng sinh event_id hoặc occurred_at mới, nó có thể tạo hàng thứ hai dù nghiệp vụ chỉ có một sự kiện. Khóa phân cụm phải được chọn cùng quy tắc định danh và retry.

## 5. Clustering columns giúp lọc và sắp xếp thế nào?

### 5.1. Thứ tự chỉ tồn tại trong một partition

Trong bảng activity_by_learner_day, các hàng L001 ngày 14/11 có thể được đọc theo:

~~~text
08:31 COMPLETE_LESSON
08:19 START_LESSON
08:15 OPEN_COURSE
~~~

Truy vấn:

~~~sql
SELECT occurred_at, event_id, activity_type
FROM activity_by_learner_day
WHERE tenant_id = 'T1'
  AND learner_id = 'L001'
  AND activity_day = '2026-11-14'
LIMIT 20;
~~~

Câu lệnh chọn **một partition**, rồi đọc các hàng theo thứ tự clustering đã khai báo. Đây là đường truy cập phù hợp cho “20 sự kiện gần nhất trong ngày”.

Tuy nhiên, sự kiện của ngày 15/11 nằm trong **partition khác**. Clustering order không tạo một danh sách thời gian toàn cục qua nhiều ngày, nhiều người học hoặc nhiều partition.

### 5.2. Lọc một khoảng của clustering column đầu

~~~sql
SELECT occurred_at, event_id, activity_type
FROM activity_by_learner_day
WHERE tenant_id = 'T1'
  AND learner_id = 'L001'
  AND activity_day = '2026-11-14'
  AND occurred_at >= '2026-11-14T08:00:00Z'
  AND occurred_at < '2026-11-14T09:00:00Z';
~~~

Ví dụ này xác định đủ partition key rồi dùng điều kiện phạm vi trên **occurred_at**, clustering column đầu tiên.

### 5.3. Thứ tự khai báo clustering columns quyết định đường đọc

So sánh:

~~~sql
-- Mô hình A: nhóm theo khóa học trước, rồi theo thời gian
PRIMARY KEY ((learner_id), course_id, occurred_at)

-- Mô hình B: nhóm thời gian trước
PRIMARY KEY ((learner_id, activity_day), occurred_at, event_id)
~~~

Mô hình A thích hợp hơn cho câu hỏi “Lịch sử của L001 trong riêng khóa C007”. Nhưng nếu muốn “Hoạt động mới nhất của L001 trên mọi khóa”, vì course_id đứng trước occurred_at nên các dòng không tạo một chuỗi thời gian chung thuận tiện.

Mô hình B thuận lợi cho lịch sử theo người và ngày, nhưng không tối ưu việc đọc riêng một khóa học nếu không lọc thêm hoặc xây bảng đọc khác.

### 5.4. Quy tắc tiền tố trong điều kiện clustering

Với schema:

~~~sql
PRIMARY KEY ((tenant_id, learner_id),
             course_id, occurred_at, event_id)
~~~

Một truy vấn theo tiền tố thường phù hợp:

~~~sql
SELECT *
FROM activity_by_course_for_learner
WHERE tenant_id = 'T1'
  AND learner_id = 'L001'
  AND course_id = 'C001'
  AND occurred_at >= '2026-11-01T00:00:00Z';
~~~

Đây là **mẫu hình minh họa** với giả định bảng activity_by_course_for_learner có schema trên. course_id được ràng buộc trước khi lọc phạm vi trên occurred_at.

Ngược lại, nếu chỉ lọc occurred_at mà bỏ qua course_id đứng trước, đường truy cập từ primary key hiện tại không phù hợp. CQL có những quy tắc cụ thể về đẳng thức, phạm vi và thứ tự clustering; không nên suy rằng có thể bỏ qua một cột đứng trước và vẫn tìm tối ưu theo cột sau.

## 6. Truy vấn nào phù hợp, truy vấn nào cần thiết kế khác?

Với bảng:

~~~sql
PRIMARY KEY ((tenant_id, learner_id, activity_day),
             occurred_at, event_id)
~~~

| Câu hỏi | Khóa có phù hợp không? | Cách xử lý |
|---|---|---|
| Lịch sử L001 trong một ngày | Có | Chọn đủ partition key, LIMIT theo clustering |
| Sự kiện L001 trong giờ 08–09 ngày D | Có | Partition key đầy đủ + range occurred_at |
| Lịch sử L001 qua 30 ngày | Cần nhiều partition | Đọc các bucket ngày, ghép kết quả |
| Mọi sự kiện của khóa C001 | Không trực tiếp | Cần mô hình đọc theo course_id hoặc đường tìm kiếm khác |
| Mọi lỗi của tenant T1 trong tháng | Không trực tiếp | Có thể dùng bảng theo tenant + loại sự kiện + thời gian, hoặc pipeline phân tích |
| Top 10 khóa hoạt động nhiều nhất hôm nay | Không trực tiếp | Thường cần bảng tổng hợp hoặc hệ phân tích |

Ví dụ sai nếu kỳ vọng được hỗ trợ hiệu quả chỉ bằng primary key hiện tại:

~~~sql
-- Thiếu learner_id và activity_day của partition key ghép:
SELECT *
FROM activity_by_learner_day
WHERE tenant_id = 'T1';

-- Lọc theo cột thường không nằm trong khóa truy cập:
SELECT *
FROM activity_by_learner_day
WHERE course_id = 'C001';
~~~

Tùy phiên bản, các câu truy vấn có thể bị từ chối vì thiếu khóa/chỉ mục hoặc đòi hỏi lọc rộng. Dùng **ALLOW FILTERING** không biến phép quét nhiều dữ liệu thành thiết kế tốt. Cần xây đường đọc dựa trên khóa truy vấn thực tế.

Một bảng phụ:

~~~sql
CREATE TABLE activity_by_course_day (
    course_id text,
    activity_day date,
    occurred_at timestamp,
    event_id uuid,
    learner_id text,
    activity_type text,
    PRIMARY KEY (
        (course_id, activity_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Bảng này phù hợp hơn cho sự kiện theo khóa học và ngày. Một sự kiện có thể được ghi vào **hai bảng đọc**, nên hệ thống cần quy tắc cập nhật và đối soát khi có ghi lỗi, retry hoặc xóa sự kiện.

### 6.1. Thiết kế theo query pattern

Một bảng wide-column thường được chọn từ yêu cầu:

1. **Ai hỏi?** Người học, giảng viên, hệ thống vận hành hay báo cáo?
2. **Biết khóa nào?** learnerId, courseId, tenantId, day?
3. **Lọc ra sao?** Đẳng thức, khoảng thời gian, trạng thái?
4. **Sắp xếp thế nào?** Mới nhất trước, điểm cao nhất trước hay theo tên?
5. **Lấy bao nhiêu?** Một item, 20 dòng, hay hàng triệu bản ghi?
6. **Dữ liệu tăng thế nào?** Một đối tượng có thể sinh bao nhiêu sự kiện trong mỗi bucket?

Một ứng dụng có thể có các bảng phục vụ đọc khác nhau: activity_by_learner_day, activity_by_course_day, summary_by_tenant_day. Đó là quyết định có chủ đích để tránh query tùy ý trên một bảng không phù hợp.

## 7. Phân vùng quá lớn và điểm nóng

### 7.1. Vì sao chỉ partition theo tenant nguy hiểm?

Giả sử bảng nhật ký có:

~~~sql
PRIMARY KEY ((tenant_id), occurred_at, event_id)
~~~

Nếu một tenant phát sinh hàng triệu sự kiện/ngày, mọi sự kiện của tenant có chung partition key. Điều đó tạo ra nguy cơ **large partition**, **hot partition** và tốn kém khi truy vấn một người học nhỏ trong toàn tenant.

Tăng số node không tự giúp chia một partition logic thành các partition nhỏ độc lập theo cách ứng dụng cần. Đó là lý do cần chọn partition key có phân bố hợp lý thay vì chỉ chọn một trường có mặt trong mọi bản ghi.

### 7.2. Bucket theo thời gian

Một cách phổ biến để giới hạn kích thước partition là thêm **time bucket**:

~~~text
(T1, L001, 2026-11)        bucket tháng
(T1, L001, 2026-11-14)     bucket ngày
(T1, L001, 2026-11-14-08)  bucket giờ
~~~

Đánh đổi:

| Bucket | Ưu điểm | Chi phí |
|---|---|---|
| Tháng | Ít partition phải tìm khi đọc nhiều ngày | Có thể quá lớn khi lượng ghi cao |
| Ngày | Giới hạn tăng trưởng theo ngày | Xem nhiều ngày phải đọc nhiều partition |
| Giờ | Giảm kích thước mỗi partition ở lưu lượng rất cao | Fan-out nhiều partition và phân trang khó hơn |

Không có ngưỡng bucket chung phù hợp mọi hệ thống. Cần tính tải dự kiến, kích thước hàng, số hàng/partition, số partition/truy vấn và khả năng compaction.

Một công thức ước lượng:

\[
\text{bytes/partition} \approx
\text{events/bucket} \times \text{average bytes/event}
\]

Ví dụ một thiết bị ghi 1.000 bản ghi/giây sẽ ghi khoảng:

\[
1.000 \times 86.400 = 86.400.000\ \text{bản ghi/ngày}.
\]

Nếu trung bình phần dữ liệu ứng dụng là 200 byte/bản ghi, dung lượng thô khoảng 17,28 GB/ngày, chưa kể overhead và replication. Một partition theo thiết bị/ngày có nguy cơ quá lớn; cần cân nhắc bucket nhỏ hơn hoặc chia tải.

### 7.3. Shard phụ để phân phối ghi

Với một người/thiết bị quá nóng dù đã bucket, có thể thêm **shard_id**:

~~~sql
PRIMARY KEY (
    (tenant_id, learner_id, activity_day, shard_id),
    occurred_at,
    event_id
)
~~~

Ứng dụng phân phối sự kiện qua nhiều shard_id bằng quy tắc ổn định. Cách này giúp tạo nhiều partition logic, nhưng “20 sự kiện mới nhất” có thể phải đọc tất cả shard liên quan rồi hợp nhất theo thời gian.

~~~text
Read shard 0 -> candidates
Read shard 1 -> candidates
Read shard 2 -> candidates
Merge by occurred_at DESC, event_id
Return first 20
~~~

Phân tán ghi tốt hơn có thể đổi lấy **fan-out đọc**, tiêu tốn truy vấn và trạng thái phân trang phức tạp hơn. Phải đánh giá theo tải đo được và yêu cầu đọc.

### 7.4. Partition key ngẫu nhiên cũng có bất lợi

Nếu lấy event_id ngẫu nhiên làm partition key, mỗi sự kiện có thể phân bố sang partition khác nhau, nhưng khi hỏi “lịch sử L001”, hệ thống không biết phải tìm ở những partition nào. Độ phân bố cao chưa đủ; **dữ liệu thường được đọc cùng nhau** phải có đường truy cập rõ ràng.

## 8. Phân trang và thứ tự trên nhiều partition

### 8.1. LIMIT không tương đương OFFSET

~~~sql
SELECT occurred_at, event_id, activity_type
FROM activity_by_learner_day
WHERE tenant_id = 'T1'
  AND learner_id = 'L001'
  AND activity_day = '2026-11-14'
LIMIT 20;
~~~

Truy vấn trả tối đa 20 hàng trong partition theo clustering order. Để lấy trang sau, các driver Cassandra thường hỗ trợ **paging state**. Không nên mặc định có cú pháp OFFSET hiệu quả như cách hay dùng trong SQL.

Một lựa chọn khác là **keyset pagination**, dùng full clustering key của hàng cuối làm mốc. Nếu hai sự kiện có cùng occurred_at, chỉ ghi nhớ timestamp có thể bỏ sót hoặc lặp bản ghi ở ranh giới trang. Cần giữ event_id và so sánh theo đúng thứ tự khai báo.

### 8.2. Nhiều ngày cần ghép kết quả

Với partition theo ngày, 20 sự kiện mới nhất của một người trong 30 ngày đòi hỏi:

1. Đọc partition của ngày gần nhất.
2. Nếu chưa đủ kết quả, đọc những ngày trước.
3. Ghép theo (occurred_at, event_id) theo thứ tự đã thống nhất.
4. Lưu trạng thái phân trang đủ để tiếp tục từ nhiều partition.

Không được coi clustering order là một thứ tự toàn cục. Khi dữ liệu mới liên tục được ghi, trang sau cũng không tự phản ánh snapshot cố định của trang đầu. Nếu cần danh sách nhất quán ở thời điểm T, phải định nghĩa mốc dữ liệu và quy tắc sự kiện đến muộn.

## 9. Tính nhất quán không được suy ra từ cách đặt khóa

Cassandra/ScyllaDB phân phối và sao chép dữ liệu. **Partition key** xác định nhóm replica, còn **clustering key** phục vụ truy cập trong partition; cả hai không tự quyết định mọi bảo đảm đọc/ghi.

- Một thao tác ghi thành công với consistency level nào đó không đồng nghĩa mọi replica ở mọi nơi đều đã cập nhật cùng lúc.
- Một truy vấn đọc từ replica có thể quan sát dữ liệu khác thời điểm tùy mức consistency và trạng thái replication.
- Hai hàng ở cùng partition không có nghĩa mọi thao tác trên hai hàng đó đều được commit/rollback như một transaction SQL tổng quát.
- Clustering theo timestamp không phải thứ tự nhân quả hoặc thứ tự commit toàn cụm. Các sự kiện có thể đến muộn, đồng hồ có thể lệch và hai sự kiện có thể trùng timestamp.

Các bất biến như “mỗi mã giao dịch chỉ được tạo một lần” cần thao tác điều kiện hoặc cơ chế đồng bộ phù hợp. Các bất biến trải trên nhiều hệ thống còn cần quy trình xử lý lỗi và đối soát. **Thiết kế khóa giúp tìm và sắp xếp dữ liệu, nhưng không thay thế thiết kế nhất quán nghiệp vụ.**

### 9.1. TTL và tombstone cũng ảnh hưởng thiết kế partition

Nhiều bảng sự kiện cần xóa dữ liệu sau một khoảng thời gian. Ví dụ:

~~~sql
INSERT INTO activity_by_learner_day (
    tenant_id, learner_id, activity_day,
    occurred_at, event_id, activity_type
) VALUES (
    'T1', 'L001', '2026-11-14',
    '2026-11-14T08:15:00Z',
    550e8400-e29b-41d4-a716-446655440001,
    'OPEN_COURSE'
) USING TTL 2592000;
~~~

TTL 2.592.000 giây tương đương 30 ngày theo thời gian 24 giờ/ngày. Trong các hệ lưu trữ dạng LSM như Cassandra, xóa và hết hạn có thể để lại **tombstone** cần được xử lý qua compaction và cơ chế bảo trì dữ liệu. Không nên mặc định dữ liệu biến mất vật lý ngay khi hết hạn.

TTL thường tính theo thời điểm ghi, có thể khác thời điểm xảy ra sự kiện. Nếu dữ liệu đến muộn và cần lưu “30 ngày kể từ khi đo”, phải tính toán quy tắc retention tương ứng. Những quyết định này ảnh hưởng kích thước partition, số bản ghi còn hiệu lực và hiệu năng đọc.

## 10. So sánh với hệ hỗ trợ khóa dạng khác

Tên gọi **wide-column** được dùng cho một họ hệ thống có cách tổ chức khác nhau; không phải tất cả đều cung cấp cú pháp clustering như CQL.

### 10.1. DynamoDB: partition key và sort key

DynamoDB có bảng với **partition key** và tùy chọn **sort key**. Ví dụ:

~~~text
PK = USER#L001
SK = ACTIVITY#2026-11-14T08:31:00Z#E003
~~~

API Query có thể đọc các item cùng PK và dùng điều kiện trên SK trong phạm vi hỗ trợ. Ý tưởng nhóm theo khóa và sắp bên trong nhóm có nét tương đồng với CQL, nhưng DynamoDB không có cú pháp nhiều clustering columns theo cách Cassandra khai báo PRIMARY KEY. Khả năng truy vấn, giới hạn kích thước, thông lượng, consistency và transaction phải đánh giá theo riêng DynamoDB.

### 10.2. Bigtable: row key có thứ tự

Google Cloud Bigtable dùng **row key** được sắp theo thứ tự từ điển, cùng column families, qualifiers và các phiên bản giá trị. Có thể mã hóa người học và thời gian vào row key:

~~~text
L001#20261114#reverseTimestamp#E003
~~~

Thiết kế như vậy giúp định hướng range scan, nhưng đó không phải khai báo partition key + clustering columns theo CQL. Một tiền tố row key quá tập trung hoặc timestamp tăng liên tục có thể gây hot range tùy cách dữ liệu được phân bố.

### 10.3. HBase: row key và region

Apache HBase tổ chức theo **row key**, column families và qualifiers. Các region quản lý những dải hàng theo thứ tự row key. Muốn tra cứu theo người học/thời gian, nhà thiết kế phải chọn cấu trúc row key phù hợp. HBase không cung cấp cùng kiểu khai báo clustering columns như Cassandra.

| Hệ | Cấu trúc khóa tiêu biểu | Điều cần nhớ |
|---|---|---|
| Cassandra / ScyllaDB | Partition key + clustering columns | Hàng được nhóm và sắp trong mỗi partition theo PRIMARY KEY |
| DynamoDB | Partition key + sort key (tùy chọn) | API Query theo PK/SK; không áp dụng nguyên xi CQL |
| Bigtable | Row key | Quét theo dải row key được sắp từ điển |
| HBase | Row key | Row key quyết định dải dữ liệu trong các region |

## 11. Thực hành: Telemetry theo thiết bị và thời gian

Giả sử một dịch vụ thu thập:

~~~text
deviceId
siteId
recordedAt
temperature
humidity
readingId
~~~

Người vận hành muốn: (1) 100 bản ghi gần nhất của một thiết bị; (2) dữ liệu trong một giờ; (3) thiết bị vượt ngưỡng nhiệt độ tại một site; (4) lưu lịch sử 90 ngày.

### 11.1. Bảng theo thiết bị/ngày

~~~sql
CREATE TABLE telemetry_by_device_day (
    device_id text,
    recorded_day date,
    recorded_at timestamp,
    reading_id uuid,
    site_id text,
    temperature double,
    humidity double,
    PRIMARY KEY (
        (device_id, recorded_day),
        recorded_at,
        reading_id
    )
) WITH CLUSTERING ORDER BY (
    recorded_at DESC,
    reading_id ASC
);
~~~

- Partition key (device_id, recorded_day) giữ các bản ghi một thiết bị trong một ngày.
- Clustering (recorded_at, reading_id) cho phép lấy gần nhất trước và phân biệt những lần đo cùng timestamp.
- site_id và temperature là cột thường; không tự tạo đường truy vấn tối ưu để tìm mọi thiết bị tại một site có nhiệt độ cao.

### 11.2. Truy vấn một giờ

~~~sql
SELECT recorded_at, temperature, humidity
FROM telemetry_by_device_day
WHERE device_id = 'dev-17'
  AND recorded_day = '2026-11-14'
  AND recorded_at >= '2026-11-14T08:00:00Z'
  AND recorded_at < '2026-11-14T09:00:00Z';
~~~

Đây là truy vấn phù hợp: chọn đầy đủ partition key và điều kiện phạm vi trên clustering đầu.

### 11.3. Cảnh báo theo site cần đường đọc khác

Câu hỏi “Trong 10 phút gần nhất, thiết bị nào ở site S có nhiệt độ trên 40°C?” không phù hợp chỉ với bảng telemetry_by_device_day vì không có device_id đầu vào.

Có thể thiết kế mô hình **latest_reading_by_site_device** để tra cứu trạng thái mới nhất theo site, hoặc xử lý stream tạo sự kiện cảnh báo, hoặc đưa telemetry tới hệ phân tích phù hợp. Lựa chọn phụ thuộc việc cần kết quả chính xác đến đâu, tải đọc/ghi, độ mới và khả năng chấp nhận đồng bộ trễ.

### 11.4. Sự kiện đến muộn

Nếu thiết bị mất mạng rồi gửi dữ liệu đã ghi từ hôm trước:

- **recorded_day** nên được tính từ recordedAt theo một múi giờ đã thống nhất, thường dùng UTC trong hệ thống phân tán.
- reading_id cần ổn định qua các lần retry.
- TTL tính theo thời điểm ghi có thể khiến thời gian lưu kể từ thời điểm đo khác dự kiến.
- Nếu dữ liệu quá hạn nhưng mới đến, ứng dụng cần có chính sách nhận, bỏ qua hoặc lưu vào kho khác.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Nhầm PRIMARY KEY (a,b) và PRIMARY KEY ((a,b)) | Khác hẳn partition key, dẫn tới phân bố sai | Đọc chính xác dấu ngoặc và vai trò từng cột |
| Chọn tenantId làm partition key duy nhất cho tập log khổng lồ | Partition lớn và nóng | Thêm khóa theo người/thiết bị và bucket thời gian |
| Cho rằng clustering sắp toàn bộ bảng | Truy vấn nhiều partition không có thứ tự toàn cục | Hợp nhất có chủ đích, dùng cursor phù hợp |
| Lọc cột thường mà không có đường đọc | Phải quét hoặc bị hệ quản trị từ chối | Thiết kế bảng theo truy vấn |
| Đưa course_id trước occurred_at khi cần lịch sử thời gian tổng hợp | Không có thứ tự thời gian thuận lợi qua nhiều khóa | Đổi thứ tự khóa hoặc thêm bảng đọc khác |
| Chỉ dùng timestamp làm khóa để phân biệt sự kiện | Hai sự kiện cùng thời điểm ghi vào một hàng | Thêm event_id ổn định |
| Sinh event_id mới mỗi khi retry | Dữ liệu bị nhân đôi | Giữ định danh sự kiện nhất quán |
| Bucket quá nhỏ chỉ để tăng phân tán | Fan-out đọc và phân trang phức tạp | Cân bằng kích thước partition và truy vấn |
| Dùng TTL và quên tombstone | Độ trễ truy vấn, compaction tốn kém | Tính cả retention và xử lý xóa trong thiết kế |
| Cho rằng cùng partition bảo đảm transaction nhiều hàng | Bất biến có thể bị phá | Chọn cơ chế ghi/điều kiện phù hợp |
| Mang nguyên mô hình CQL sang Bigtable hoặc HBase | Hiểu sai row key và thứ tự lưu | Thiết kế lại theo API của từng hệ |

## 13. Bài tập vận dụng

### Bài 1: Đọc khóa chính

Cho bảng:

~~~sql
CREATE TABLE comments_by_post (
    post_id text,
    created_at timestamp,
    comment_id uuid,
    author_id text,
    content text,
    PRIMARY KEY ((post_id), created_at, comment_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    comment_id ASC
);
~~~

Hãy xác định partition key, clustering columns, full primary key. Giải thích liệu hai bình luận có thể cùng created_at trên một post không; nếu có, yếu tố nào phân biệt chúng? Viết truy vấn lấy 10 bình luận mới nhất của một bài.

**Gợi ý:** Partition key là post_id; hai clustering columns là created_at và comment_id. Hai bình luận cùng thời điểm hợp lệ khi comment_id khác. SELECT theo post_id và LIMIT 10 tận dụng thứ tự đã khai báo.

### Bài 2: Phân biệt dấu ngoặc

So sánh:

~~~sql
PRIMARY KEY (tenant_id, learner_id, created_at)
PRIMARY KEY ((tenant_id, learner_id), created_at)
~~~

Giải thích tại sao dòng đầu chỉ có tenant_id làm partition key trong khi dòng thứ hai dùng cặp tenant_id + learner_id. Nếu yêu cầu là “lịch sử hoạt động của một người trong một tenant”, thiết kế nào phù hợp hơn? Với hàng triệu hoạt động/người, cần bổ sung thành phần nào?

### Bài 3: Từ truy vấn đến bảng

Một cửa hàng có nhu cầu:

1. Lấy 20 đơn gần nhất của customer C17.
2. Tra cứu chi tiết đơn bằng orderId.
3. Liệt kê đơn đang chờ xử lý theo storeId.

Hãy đề xuất một bảng orders_by_customer_month với partition key (customerId, month) và clustering theo thời gian giảm dần; sau đó đề xuất đường đọc theo orderId và storeId. Giải thích chi phí khi nhân dữ liệu vào nhiều mô hình đọc và cách đối soát lúc cập nhật trạng thái đơn.

### Bài 4: Tính kích thước phân vùng

Một thiết bị ghi 5.000 mẫu/giây, mỗi mẫu chứa trung bình 200 byte dữ liệu ứng dụng. Hỏi:

1. Trong 24 giờ có bao nhiêu bản ghi?
2. Tổng dung lượng thô xấp xỉ bao nhiêu?
3. Bucket theo thiết bị/ngày có thể gây vấn đề gì?
4. Nếu chuyển sang bucket phút hoặc bổ sung shard_id, truy vấn “100 mẫu mới nhất” thay đổi ra sao?

**Gợi ý:**

\[
5.000 \times 86.400 = 432.000.000\ \text{bản ghi/ngày}
\]

\[
432.000.000 \times 200 = 86.400.000.000\ \text{byte}
\]

Con số này chưa tính metadata, compression và replication. Khi chia nhỏ partition, cần đổi lại bằng việc đọc/ghép nhiều partition hơn.

### Bài 5: Quy tắc thiết kế

Với bảng activity_by_learner_day, đánh giá tính phù hợp của những yêu cầu:

| Yêu cầu | Nhận định |
|---|---|
| Lịch sử L001 trong một ngày | Phù hợp |
| Lịch sử L001 trong một khoảng giờ cùng ngày | Phù hợp |
| Mọi sự kiện ERROR trên toàn tenant | Không có đường truy cập trực tiếp theo khóa |
| Mọi sự kiện của course C001 | Cần mô hình đọc/chỉ mục khác |
| 20 sự kiện mới nhất qua nhiều ngày | Cần truy vấn và ghép nhiều partition |

Với từng trường hợp cần mô hình khác, hãy nêu khóa đầu vào, thứ tự kết quả và chi phí cập nhật.

## 14. Tổng kết

Trong Cassandra và ScyllaDB, **partition key** xác định những hàng thuộc cùng một partition logic và hỗ trợ định vị qua token; **clustering columns** định danh và sắp xếp hàng **bên trong partition**. Toàn bộ tổ hợp đó là **primary key**.

Khi thiết kế, hãy đi theo trình tự:

1. Viết câu hỏi nghiệp vụ cùng điều kiện lọc, sắp xếp, giới hạn và tần suất.
2. Chọn partition key sao cho dữ liệu thường được đọc cùng nhau nằm trong nhóm có kích thước và lưu lượng chấp nhận được.
3. Chọn clustering columns theo thứ tự lọc, sắp xếp, có khóa phụ để phân biệt các hàng nếu cần.
4. Xác định truy vấn nào cần bảng đọc hoặc hệ chỉ mục khác; không dựa vào ALLOW FILTERING làm chiến lược chính.
5. Tính đến hotspot, bucket, fan-out, phân trang, TTL, tombstone, retry và consistency.
6. Kiểm tra lại ngữ nghĩa cụ thể của hệ quản trị: CQL clustering columns không giống hệt DynamoDB sort key hay Bigtable/HBase row key.

Khóa tốt không đơn giản là trường có nhiều giá trị khác nhau. Nó phải định vị đúng dữ liệu theo nhu cầu truy vấn, duy trì thứ tự hữu ích trong phạm vi phù hợp và tránh phân vùng mất cân bằng khi hệ thống tăng trưởng.
