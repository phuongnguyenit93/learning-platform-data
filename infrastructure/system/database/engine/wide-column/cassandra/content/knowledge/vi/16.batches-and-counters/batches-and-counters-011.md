# COUNTER BATCH và giới hạn kết hợp với dữ liệu thông thường

## Mục tiêu và bối cảnh

Trong Apache Cassandra, dữ liệu được phân phối theo **partition key**, lưu dưới mô hình **wide-column**, và bảng thường được thiết kế từ các truy vấn phải phục vụ. Bên cạnh các cột dữ liệu thông thường, Cassandra cung cấp kiểu `counter` cho nhu cầu tăng hoặc giảm số đếm bằng CQL. Những phép cập nhật này có quy tắc riêng, bao gồm một dạng batch chuyên biệt: **`COUNTER BATCH`**.

Bài học thuộc phạm vi `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`: hiểu kiến trúc phân tán, khóa phân vùng, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi và cách dùng Cassandra từ Java. Sau bài này, bạn cần có khả năng:

- Thiết kế bảng counter hợp lệ và giải thích vì sao phải tách dữ liệu thường sang bảng khác.
- Viết `UPDATE` counter, `BEGIN COUNTER BATCH ... APPLY BATCH` và nhận diện batch không hợp lệ.
- Phân biệt việc **nhóm các cập nhật** với giao dịch ACID hoặc cơ chế chống ghi trùng.
- Chọn partition key, consistency level và cách xử lý timeout/retry phù hợp với yêu cầu độ chính xác của số đếm.

## 1. Counter là kiểu dữ liệu đặc biệt

Counter là một cột số nguyên có dấu dùng cho phép **cộng/trừ một lượng**. Cassandra quản lý việc cập nhật counter theo cơ chế riêng so với thao tác ghi giá trị bình thường.

Ví dụ, ứng dụng theo dõi lượt xem và lượt thích của mỗi bài viết theo ngày và kênh truy cập:

~~~sql
CREATE TABLE article_counters_by_day (
    article_id text,
    day date,
    channel text,
    views counter,
    likes counter,
    PRIMARY KEY ((article_id, day), channel)
);
~~~

Ở đây, `(article_id, day)` là **partition key tổng hợp**, còn `channel` là **clustering column**. Các hàng `channel = 'web'` và `channel = 'all'` của cùng bài viết/ngày nằm trong cùng một partition. Mô hình này phù hợp với truy vấn đọc các chỉ số của một bài viết trong một ngày:

~~~sql
SELECT channel, views, likes
FROM article_counters_by_day
WHERE article_id = 'post-42' AND day = '2026-11-21';
~~~

Counter được thay đổi bằng phép cộng hoặc trừ trong `UPDATE`:

~~~sql
UPDATE article_counters_by_day
SET views = views + 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';

UPDATE article_counters_by_day
SET likes = likes - 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';
~~~

Nếu hàng counter chưa tồn tại, phép cập nhật đầu tiên tính từ giá trị ban đầu bằng 0. Tuy nhiên, trước lần cập nhật đó, `SELECT` có thể không trả về hàng nào; ứng dụng không nên tự suy diễn rằng luôn có một hàng với số đếm 0.

Các quy tắc quan trọng:

| Nội dung | Quy tắc |
| --- | --- |
| Tăng/giảm | Dùng `UPDATE ... SET c = c + n` hoặc `c = c - n`, với `n` là lượng cần thay đổi. |
| Gán trực tiếp | Không dùng `SET views = 100` để khởi tạo hoặc đặt lại counter theo cách ghi cột số thường. |
| Khóa chính | Cột `counter` không được là thành phần của `PRIMARY KEY`. |
| Cột khác trong bảng | Ngoài các cột khóa chính, bảng có counter chỉ được chứa cột counter; không trộn với cột `text`, `timestamp`, `int` thông thường. |
| Thời hạn và thời điểm ghi | Không dùng `USING TTL` hoặc `USING TIMESTAMP` cho cập nhật counter. |
| Điều kiện ghi | Counter không hỗ trợ cập nhật `IF` theo kiểu lightweight transaction (LWT) để bảo đảm tăng một lần. |
| Tính lặp lại | `views = views + 1` **không idempotent**: chạy hai lần thì có thể tăng hai đơn vị. |

## 2. Cú pháp COUNTER BATCH

Khi một sự kiện cần cập nhật **nhiều hàng counter liên quan**, Cassandra cho phép nhóm chúng thành một `COUNTER BATCH`:

~~~sql
BEGIN COUNTER BATCH
    UPDATE article_counters_by_day
    SET views = views + 1
    WHERE article_id = 'post-42'
      AND day = '2026-11-21'
      AND channel = 'web';

    UPDATE article_counters_by_day
    SET views = views + 1
    WHERE article_id = 'post-42'
      AND day = '2026-11-21'
      AND channel = 'all';
APPLY BATCH;
~~~

Sự kiện một người xem bài viết từ website làm tăng cả số đếm riêng của kênh `web` và số đếm tổng `all`. Hai cập nhật trong ví dụ thuộc **cùng partition**, vì vậy tránh được chi phí phân phối một batch ra nhiều partition. Có thể đọc lại bằng truy vấn `SELECT` ở mục trước để thấy các giá trị đã thay đổi.

Một số điểm cần phân biệt:

1. `BEGIN COUNTER BATCH` dành cho **các câu lệnh cập nhật counter**, không phải tên khác của `BEGIN BATCH` thông thường.
2. Batch là một **đơn vị gửi và điều phối các cập nhật**. Nó không biến counter thành giao dịch ACID xuyên nhiều hàng/bảng, không tạo snapshot nhất quán cho người đọc và không cung cấp bảo đảm exactly-once.
3. Một batch nhiều partition có thể gây tải phối hợp, tăng latency và khiến việc xử lý lỗi khó hơn. Batching không phải cách mặc định để đẩy nhanh hàng nghìn phép tăng độc lập.
4. Khi các cột counter của **cùng một hàng** phải tăng cùng lúc, một `UPDATE` thường rõ ràng và gọn hơn:

~~~sql
UPDATE article_counters_by_day
SET views = views + 1,
    likes = likes + 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';
~~~

Chỉ tăng cả `views` và `likes` trong cùng câu lệnh nếu **nghiệp vụ thật sự phát sinh cả hai sự kiện**. Counter batch cũng không tự áp đặt thứ tự thực hiện các câu lệnh trong batch.

## 3. Vì sao không được trộn counter với dữ liệu thông thường?

Giả sử hệ thống còn lưu tiêu đề, tác giả và thời điểm cập nhật bài viết. Đây là dữ liệu thông thường, nên đặt ở một bảng độc lập:

~~~sql
CREATE TABLE article_metadata (
    article_id text PRIMARY KEY,
    title text,
    author text,
    updated_at timestamp
);
~~~

**Thiết kế không hợp lệ** là đưa `title` vào bảng có counter:

~~~sql
-- SAI: bảng counter không thể chứa cột thường ngoài khóa chính.
CREATE TABLE invalid_article (
    article_id text PRIMARY KEY,
    views counter,
    title text
);
~~~

**Batch dưới đây cũng không hợp lệ**, dù các câu lệnh ghi vào hai bảng khác nhau:

~~~sql
-- SAI: COUNTER BATCH không nhận câu lệnh ghi dữ liệu thường.
BEGIN COUNTER BATCH
    UPDATE article_counters_by_day
    SET views = views + 1
    WHERE article_id = 'post-42'
      AND day = '2026-11-21'
      AND channel = 'web';

    UPDATE article_metadata
    SET title = 'Cassandra căn bản'
    WHERE article_id = 'post-42';
APPLY BATCH;
~~~

Chiều ngược lại cũng không hợp lệ: đặt phép tăng counter vào `BEGIN BATCH` thông thường hoặc `BEGIN UNLOGGED BATCH` để tìm cách trộn hai loại cập nhật. Cassandra phân biệt batch counter với batch dành cho thao tác ghi thông thường.

**Giải pháp đúng** là tách hai đường ghi:

~~~sql
-- Đường ghi dữ liệu thường:
UPDATE article_metadata
SET title = 'Cassandra căn bản',
    updated_at = toTimestamp(now())
WHERE article_id = 'post-42';

-- Đường ghi counter:
UPDATE article_counters_by_day
SET views = views + 1
WHERE article_id = 'post-42'
  AND day = '2026-11-21'
  AND channel = 'web';
~~~

Hai câu lệnh trên là **hai thao tác độc lập**. Nếu nghiệp vụ yêu cầu cả cập nhật metadata lẫn cộng counter phải thành công hoặc thất bại cùng nhau, Cassandra không cung cấp giao dịch ACID xuyên hai bảng bằng cách bọc chúng trong `COUNTER BATCH`. Ứng dụng cần quy trình xử lý lỗi, ghi nhận sự kiện, đối soát hoặc lựa chọn mô hình dữ liệu khác tùy mức độ chính xác cần thiết.

## 4. Timeout, retry và giới hạn của tính nhất quán

Tình huống dễ gây lỗi nhất là **client không biết phép tăng đã được áp dụng hay chưa**:

| Thời điểm | Sự việc | Hệ quả có thể xảy ra |
| --- | --- | --- |
| T0 | Counter đang là 100. | Đây là giá trị trước sự kiện. |
| T1 | Ứng dụng gửi `views = views + 1`. | Một hay nhiều replica có thể đã xử lý yêu cầu. |
| T2 | Client nhận timeout. | Timeout không chứng minh phép tăng đã thất bại. |
| T3 | Ứng dụng gửi lại `+1` mà không kiểm tra nghiệp vụ. | Nếu lần đầu thực ra đã thành công, counter có thể thành 102 cho chỉ một lượt xem. |

Vì vậy:

- **Không tự động retry một phép tăng counter như thể nó idempotent.** Kiểm tra chính sách retry của client/driver và xác định cách xử lý khi kết quả ghi không rõ ràng.
- `LOCAL_QUORUM` hoặc `QUORUM` có thể được chọn để đạt mức xác nhận đọc/ghi thích hợp với replication và datacenter đang dùng; chúng **không** biến `+1` thành phép ghi exactly-once, cũng không khắc phục việc gửi trùng.
- `COUNTER BATCH` không làm biến mất rủi ro này. Nếu batch timeout và bị gửi lại, một hoặc nhiều số đếm có thể tăng thêm lần nữa.
- Repair giúp xử lý sự lệch nhau của dữ liệu giữa replica theo cơ chế của Cassandra; repair không nhận biết được hai lần `+1` thực chất xuất phát từ cùng một sự kiện nghiệp vụ để tự giảm về một lần.

Nếu số đếm chỉ dùng làm **chỉ số gần đúng**, chẳng hạn lượt xem cho dashboard, counter có thể là lựa chọn phù hợp. Nếu số đếm tác động tới **tiền, hạn mức, tồn kho, quyền sử dụng hoặc nghiệp vụ bắt buộc đúng tuyệt đối**, nên cân nhắc mô hình lưu từng sự kiện với `event_id` duy nhất và một quy trình tổng hợp/đối soát có thể phục hồi. Việc lưu `event_id` rồi cập nhật counter ở hai bảng khác nhau vẫn **không tự tạo ra giao dịch nguyên tử**; cần thiết kế rõ trạng thái xử lý và đường khôi phục.

## 5. Lựa chọn partition key, replication và hiệu năng

Cassandra phân phối dữ liệu theo partition key. Trong ví dụ, `(article_id, day)` gom các kênh của cùng bài/ngày để phục vụ truy vấn và cập nhật liên quan. Điều này tiện cho một sự kiện tăng hai hàng `web` và `all` trong cùng partition, nhưng có thể tạo **điểm nóng** nếu một bài viết nhận lượng truy cập cực lớn.

Khi tải cao, một phương án là chia counter ra các **shard nằm ở nhiều partition key**:

~~~sql
CREATE TABLE article_views_by_day_shard (
    article_id text,
    day date,
    shard smallint,
    views counter,
    PRIMARY KEY ((article_id, day, shard))
);
~~~

Mỗi sự kiện chọn một `shard` trong dải cố định, rồi tăng counter của partition đó. Khi đọc tổng, ứng dụng lấy dữ liệu từ **tất cả shard** và cộng lại. Đưa `shard` vào **partition key** là điểm cốt lõi; chỉ đưa nó vào clustering key vẫn giữ mọi shard trên cùng một partition và không phân tán điểm nóng. Đổi lại, số lượt đọc và việc tổng hợp tăng theo số shard.

Các quyết định vận hành nên dựa trên truy vấn và tải thực tế:

| Tình huống | Cách tiếp cận phù hợp |
| --- | --- |
| Tăng một counter trên một hàng | Một câu `UPDATE` counter. |
| Tăng hai counter cùng một hàng | Một `UPDATE` với hai biểu thức cộng/trừ. |
| Tăng các hàng counter liên quan trong cùng partition | Cân nhắc `COUNTER BATCH` nhỏ, đo hiệu năng thực tế. |
| Tăng số lượng lớn counter độc lập ở nhiều partition | Các `UPDATE` riêng, thực thi song song có giới hạn và backpressure; tránh batch khổng lồ. |
| Ghi metadata và tăng counter | Hai bảng, hai đường ghi; xây xử lý lỗi theo nghiệp vụ. |
| Một partition nhận rất nhiều lượt tăng | Xem xét shard theo partition key và tổng hợp khi đọc. |
| Cần xóa/đặt lại thống kê theo kỳ | Thiết kế counter theo ngày/kỳ/phiên mới; không coi `SET counter = 0` là thao tác hợp lệ. |

Với replication nhiều datacenter, kiểm tra replication factor, mức nhất quán và yêu cầu đọc mới đến đâu. Số đếm vẫn chịu các đặc điểm của một hệ phân tán: replica có thể tạm thời chưa đồng bộ, sự cố kết nối có thể khiến kết quả ghi mơ hồ, và consistency level cao hơn thường đổi lấy latency/tính sẵn sàng dưới một số dạng lỗi.

## 6. Dùng COUNTER BATCH từ Java

Ví dụ với **Apache Cassandra Java Driver 4.x**, giả sử `CqlSession session` đã được cấu hình kết nối tới keyspace phù hợp:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.LocalDate;

// session được tạo/cấu hình ở lớp quản lý kết nối của ứng dụng.
void recordWebView(CqlSession session, String articleId, LocalDate day) {
    PreparedStatement increment = session.prepare(
        "UPDATE article_counters_by_day " +
        "SET views = views + ? " +
        "WHERE article_id = ? AND day = ? AND channel = ?");

    BoundStatement web = increment.bind(1L, articleId, day, "web");
    BoundStatement total = increment.bind(1L, articleId, day, "all");

    BatchStatement batch = BatchStatement.builder(DefaultBatchType.COUNTER)
        .addStatement(web)
        .addStatement(total)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setIdempotence(false)
        .build();

    session.execute(batch);
}
~~~

Đoạn mã biểu diễn một sự kiện lượt xem làm tăng hai hàng counter. Dấu `?` dùng tham số của prepared statement, tránh nối trực tiếp đầu vào người dùng vào CQL. `LOCAL_QUORUM` chỉ là **ví dụ cấu hình**; cần chọn consistency level theo replication, datacenter và mục tiêu độ trễ của hệ thống.

Trong ứng dụng thật, chuẩn bị statement một lần và tái sử dụng; cấu hình timeout, retry, giám sát lỗi và giới hạn lượng request đang chạy. Đặt `setIdempotence(false)` làm rõ rằng batch này không an toàn để phát lại tùy ý. Nếu `session.execute(batch)` ném timeout, ứng dụng phải xử lý trạng thái **chưa biết chắc kết quả**, thay vì lập tức cộng lại.

## 7. Thực hành và cách kiểm tra

1. Tạo bảng `article_counters_by_day` ở mục 1. Thực thi `COUNTER BATCH` ở mục 2 một lần; đọc hai hàng `web` và `all`. Nếu bảng mới tạo và chưa có cập nhật nào khác, mỗi hàng có `views = 1`.
2. Thực thi đúng batch đó thêm một lần; quan sát số đếm tăng tiếp. Đây là bằng chứng trực tiếp cho tính **không idempotent**, không phải lỗi Cassandra.
3. Tạo `article_metadata` và thử batch trộn counter với cập nhật `title` ở mục 3. Cassandra phải từ chối batch không hợp lệ; lưu thông báo lỗi để nhận diện quy tắc áp dụng.
4. So sánh một `UPDATE` tăng hai cột trên cùng hàng với hai `UPDATE` riêng. Chọn cách diễn đạt khớp một sự kiện nghiệp vụ, tránh cộng hai chỉ số không liên quan.
5. Tự đặt tình huống batch timeout sau khi đã gửi: ghi ra chiến lược nghiệp vụ cho số đếm gần đúng và cho số đếm bắt buộc chính xác. Chú ý rằng đọc lại counter sau timeout **không luôn đủ** để chứng minh một sự kiện cụ thể đã được áp dụng đúng một lần khi nhiều client cùng tăng.

Khi kiểm tra trên môi trường nhiều replica, theo dõi cả số lượng timeout, retry, mức nhất quán, tải trên partition nóng và độ trễ. Không dùng việc một lần `SELECT` trả đúng số dự kiến làm bằng chứng rằng hệ thống đã cung cấp exactly-once.

## Ghi nhớ

**`COUNTER BATCH` chỉ dành cho cập nhật counter; dữ liệu thông thường phải ở bảng/đường ghi riêng.** Hãy thiết kế partition key theo truy vấn, giữ batch nhỏ, xem phép `+1` là không idempotent và xử lý timeout theo nhu cầu chính xác của nghiệp vụ. Batch giúp nhóm thao tác liên quan, nhưng không thay thế giao dịch ACID hay cơ chế loại trùng sự kiện.
