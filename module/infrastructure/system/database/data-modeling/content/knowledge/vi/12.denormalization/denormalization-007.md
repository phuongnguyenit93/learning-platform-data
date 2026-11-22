# Nhất quán tức thời, nhất quán cuối cùng và chi phí cập nhật

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **nhất quán tức thời trong phạm vi một giao dịch** và **nhất quán cuối cùng (eventual consistency)** mà không đánh đồng chúng với việc truy vấn “nhanh” hay “chậm”.
- Phân tích việc sao chép bộ đếm, tổng tiền hoặc thuộc tính hiển thị tác động thế nào đến **đường ghi**, khóa, số lượt cập nhật, tài nguyên và khả năng khôi phục.
- Chọn một ranh giới nhất quán dựa trên **bất biến nghiệp vụ**, độ tươi cho phép và nguồn dữ liệu chuẩn.
- Thiết kế cách cập nhật đồng bộ trong PostgreSQL hoặc truyền sự kiện bất đồng bộ bằng **transactional outbox**, đồng thời xử lý retry, đếm trùng và sai thứ tự.
- Xây dựng phép đối soát, chỉ số đo độ trễ và bộ thử nghiệm để kiểm tra chi phí thực tế trước khi quyết định phi chuẩn hóa.
- So sánh sự đánh đổi tương tự trong dữ liệu quan hệ, document, đồ thị và mô hình phân tích.

Đây là chủ đề trong chương **Phi chuẩn hóa** của **DATABASE_DATA_MODELING**. Việc chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc và lược đồ vật lý chỉ hoàn chỉnh khi ta mô tả được **dữ liệu nào phải đúng ở thời điểm nào, nơi nào sở hữu nó và chi phí để duy trì cam kết ấy**.

## 1. Cùng một bộ đếm nhưng hai hợp đồng khác nhau

Giả sử ứng dụng có nút **Thích** cho bài viết. Dữ liệu gốc là tập quan hệ:

~~~text
post_likes(post_id, user_id)
~~~

Mỗi cặp **(post_id, user_id)** có tối đa một hàng. Tổng lượt thích hiện hành là số hàng của từng **post_id**.

Trang danh sách bài viết có thể phải hiển thị **like_count** hàng nghìn lần mỗi phút. Thay vì chạy COUNT liên tục, nhóm thiết kế đề xuất một bảng **post_like_counts(post_id, like_count)** được lưu sẵn.

Hai nhóm chức năng có thể muốn hai hợp đồng khác nhau:

- **Đường thao tác của chính người dùng:** sau khi API báo “Đã thích”, lượt thích của người ấy phải thực sự tồn tại; nếu giao diện trả số đếm mới, nó không được mâu thuẫn với cam kết của API.
- **Danh sách bài viết công khai:** có thể chấp nhận bộ đếm phản ánh thay đổi sau vài giây, miễn là thông tin mang tính tham khảo và độ trễ có giới hạn.

Một cách triển khai là cập nhật quan hệ và bộ đếm **cùng giao dịch**. Cách khác là ghi quan hệ ở nguồn, phát sự kiện, rồi **cập nhật bộ đếm sau** trong mô hình đọc. Cả hai đều có thể là lựa chọn hợp lệ, nhưng cam kết và chi phí khác nhau.

Điều quan trọng là: **post_likes** xác định ai đang thích bài; **post_like_counts** là dữ liệu dẫn xuất. Nếu bản sao có giá trị khác nguồn, phải có quy tắc giải thích liệu đây là trạng thái đồng bộ tạm thời được chấp nhận hay lỗi cần khắc phục.

## 2. Hiểu chính xác hai mô hình nhất quán

### 2.1. Nhất quán tức thời: đúng sau một ranh giới đã xác định

Trong bài, **nhất quán tức thời** có nghĩa thực dụng sau:

> Khi thao tác ghi đã **commit thành công** trên database sở hữu nguồn và bộ đếm, các truy vấn mới trên **cùng database** theo phạm vi đọc phù hợp phải thấy quan hệ và bộ đếm cùng phản ánh thao tác đó.

Ví dụ: một giao dịch thêm quan hệ thích và tăng bộ đếm. Nếu giao dịch commit, cả hai thay đổi được công bố; nếu rollback, cả hai không được công bố.

Đây là cam kết **trong phạm vi giao dịch**. Nó **không tự động có nghĩa**:

- Một cache cũ, một read replica đang trễ hoặc một database khác cũng thấy dữ liệu mới ngay.
- Một transaction đã mở trước đó ở mức cô lập giữ snapshot sẽ tự đổi kết quả giữa chừng.
- Mọi người dùng trên thế giới đồng thời thấy cùng trạng thái tại đúng một micro giây.
- Bất kỳ hai thao tác đọc/ghi phức tạp nào cũng đạt **linearizability** chỉ vì một bảng có transaction.

**Atomicity** (cùng commit/cùng rollback), **isolation** (cách các transaction nhìn nhau) và **linearizability** (một đặc tính mạnh về thứ tự quan sát các thao tác đồng thời) là những khái niệm khác nhau. Khi yêu cầu đòi bảo đảm mạnh, cần mô tả rõ API, nơi đọc, isolation level và ranh giới thời gian; không dùng chung từ “real-time” thay cho một hợp đồng đo được.

Trong PostgreSQL, với truy vấn mới trên primary ở mức **READ COMMITTED**, một thao tác đã commit thường được quan sát ở snapshot của câu lệnh mới; còn các mức cô lập, kết nối replica và cache có thể có hành vi khác. Lập luận về nhất quán phải gắn với kiến trúc đọc thực tế.

### 2.2. Nhất quán cuối cùng: có thể tạm lệch nhưng phải hội tụ

**Eventual consistency** nghĩa là nếu nguồn ngừng thay đổi và quá trình truyền/áp dụng cập nhật tiếp tục hoạt động theo giả định đã thiết kế, các bản sao sẽ **cuối cùng hội tụ** về trạng thái phản ánh nguồn.

Ví dụ:

~~~text
T0    Người dùng thích bài, nguồn commit thành công
T0+1s Event đã vào hàng đợi, bản đếm còn cũ
T0+3s Consumer áp dụng thay đổi lên bảng đếm
T0+4s Trang danh sách trả về số mới
~~~

Trong khoảng từ **T0** đến lúc bản sao cập nhật, việc đọc từ nguồn và đọc từ bộ đếm có thể khác nhau. Điều đó chỉ được coi là **bình thường** nếu nằm trong hợp đồng nhất quán đã công bố.

Nhất quán cuối cùng **không tự bảo đảm trễ tối đa vài giây**. Nếu event bị mất, worker ngừng vĩnh viễn hoặc không có cơ chế đối soát, bản sao có thể sai mãi; khi ấy hệ thống không đạt mục tiêu hội tụ. Để có cam kết thời gian cụ thể, phải thiết kế **SLO độ tươi**, cơ chế phát lại và giám sát.

### 2.3. Các cam kết mà người dùng thực sự nhìn thấy

| Mong muốn người dùng | Cần thiết kế gì? | Lưu ý |
| --- | --- | --- |
| Thao tác thích thành công thì trạng thái “đã thích” đúng ngay | Ghi quan hệ nguồn có xác nhận commit; đọc lại nguồn hoặc trả trạng thái từ kết quả ghi | Không nhất thiết phải chờ mọi bảng đếm công khai |
| Sau khi bấm thích, người đó thấy bộ đếm tăng | Cập nhật đồng bộ, hoặc hiển thị dự kiến có xử lý rollback, hoặc chờ projection bắt kịp | Tránh trình bày số dự kiến như số đã xác nhận trên nguồn |
| Người khác thấy số lượt thích trong vài chục giây | Eventual projection và độ tươi được đo | Nêu rõ ngưỡng và cách phục hồi khi trễ |
| Không bao giờ bán vượt tồn kho đã cam kết | Kiểm tra/giữ chỗ/trừ tồn ở nguồn trong ranh giới nhất quán phù hợp | Không ra quyết định từ bộ đếm cache có thể cũ |
| Báo cáo doanh thu cập nhật định kỳ | Bảng tổng hợp hoặc materialized view với thời gian làm mới | Cần watermark, định nghĩa tiền và kỳ dữ liệu |

Một hệ thống có thể chọn **nhất quán mạnh trên đường ghi quyết định nghiệp vụ** và **nhất quán cuối cùng trên đường đọc tham khảo**. Không cần áp một mức nhất quán duy nhất lên toàn bộ module.

## 3. Đặt bất biến nghiệp vụ trước khi chọn cách cập nhật

Với nút thích, giả sử:

- Mỗi người dùng thích một bài tối đa một lần tại cùng thời điểm.
- Bỏ thích nghĩa là quan hệ không còn tồn tại.
- Bộ đếm, khi đã ở trạng thái đồng bộ, bằng số hàng **post_likes** của bài.
- Bộ đếm không âm.
- Thao tác lặp do retry không tự tăng/giảm thêm lần nữa.

Ta có thể viết bất biến:

~~~text
like_count(post_id)
  = COUNT(post_likes WHERE post_likes.post_id = post_id)
~~~

Ở chế độ đồng bộ, bất biến phải đúng sau khi mỗi giao dịch được commit. Ở chế độ bất đồng bộ, bất biến có thể tạm không đúng tại thời điểm đọc; thay vào đó cần hợp đồng **độ trễ tối đa**, phương pháp ghi mốc và cách tính lại từ nguồn.

Đối với tiền thanh toán, địa chỉ giao hàng, số dư hoặc số tồn kho, bất biến có thể nhạy cảm hơn. Không thể lấy ví dụ like_count mang tính tham khảo để suy rằng **mọi bộ đếm đều phù hợp eventual consistency**.

### 3.1. Nguồn dữ liệu chuẩn có thể khác nhau theo ngữ nghĩa

- **post_likes** là nguồn chuẩn về quan hệ thích hiện tại.
- **post_like_counts** là bộ đếm dẫn xuất, có thể xây dựng lại.
- **order_items.unit_price_at_confirmation** là nguồn chuẩn cho giá đã chốt ở giao dịch quá khứ.
- **catalog_products.current_price** là nguồn chuẩn cho giá niêm yết hiện hành; bản sao trên thẻ sản phẩm cần cập nhật khi giá đổi.
- **daily_sales_summary** là giá trị dẫn xuất từ các giao dịch theo grain và công thức đã công bố.

Giá đã chốt không được “đồng bộ” theo giá niêm yết mới. Sự khác biệt giữa snapshot lịch sử và projection hiện hành **là khác biệt ngữ nghĩa**, không phải hai mức độ chậm trễ của cùng một bản sao.

## 4. Phương án A: duy trì bộ đếm đồng bộ trong PostgreSQL

Ví dụ tối giản:

~~~sql
CREATE TABLE posts (
    post_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL
);

CREATE TABLE post_likes (
    post_id BIGINT NOT NULL REFERENCES posts(post_id),
    user_id BIGINT NOT NULL,
    liked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE post_like_counts (
    post_id BIGINT PRIMARY KEY REFERENCES posts(post_id),
    like_count BIGINT NOT NULL DEFAULT 0
        CHECK (like_count >= 0)
);
~~~

Ví dụ giả định **user_id** đã được xác thực, và các ràng buộc về tài khoản hợp lệ được quản lý ở phần khác của hệ thống. **post_like_counts** ban đầu có thể chưa có hàng cho bài chưa ai thích; cách đọc phải coi thiếu hàng là **0**, hoặc khởi tạo hàng **0** cho mỗi bài một cách nhất quán.

### 4.1. Tăng đúng một lần khi thực sự thêm quan hệ

Dùng một câu SQL có CTE thay vì hai thao tác đọc số cũ rồi ghi lại:

~~~sql
WITH added AS (
    INSERT INTO post_likes (post_id, user_id)
    VALUES ($1, $2)
    ON CONFLICT (post_id, user_id) DO NOTHING
    RETURNING post_id
)
INSERT INTO post_like_counts AS counters (
    post_id, like_count
)
SELECT post_id, 1
FROM added
ON CONFLICT (post_id)
DO UPDATE SET
    like_count = counters.like_count + EXCLUDED.like_count;
~~~

Giả sử câu lệnh được chạy và commit trên PostgreSQL:

1. Lần thích mới chèn **post_likes** thành công; CTE **added** trả một hàng và bộ đếm tăng 1.
2. Nếu chính người ấy đã thích, khóa chính ngăn tạo quan hệ trùng. **added** không trả hàng, bộ đếm không tăng.
3. Nếu nhiều người thích cùng bài đồng thời, nhánh **DO UPDATE** cộng dựa trên giá trị được bảo vệ bởi khóa hàng, thay vì ghi đè một số đếm đọc từ trước.
4. Nếu câu lệnh lỗi và transaction rollback, thay đổi nguồn và bộ đếm cùng được hoàn tác.

Điều này giúp bảo đảm **hiệu ứng một lần cho thao tác thêm cùng cặp (post_id, user_id)**. Nó không giải quyết mọi tình huống ứng dụng: phải xử lý lỗi giao dịch, quyền ghi, xóa bài, dữ liệu được nhập bằng công cụ khác và khả năng bộ đếm đã lệch từ trước.

**Không nên viết:**

~~~sql
-- Ví dụ sai dưới tương tranh nếu ứng dụng đã đọc N trước đó:
UPDATE post_like_counts
SET like_count = $old_count_plus_one
WHERE post_id = $post_id;
~~~

Hai request có thể cùng đọc N rồi cùng ghi N+1, làm mất một lần tăng. Phép cộng nguyên tử ngay trên hàng dữ liệu giảm nguy cơ **lost update** trong mẫu này.

### 4.2. Giảm bộ đếm khi bỏ thích

Đường bỏ thích phải đi theo nguyên tắc đối xứng: chỉ trừ khi **DELETE** thực sự xóa quan hệ.

~~~sql
BEGIN;

DELETE FROM post_likes
WHERE post_id = $1 AND user_id = $2
RETURNING post_id;

-- Chỉ thực hiện khi DELETE đã trả đúng một hàng:
UPDATE post_like_counts
SET like_count = like_count - 1
WHERE post_id = $1
  AND like_count > 0
RETURNING like_count;

-- Nếu đã DELETE một hàng nhưng UPDATE không trả một hàng:
-- ROLLBACK và điều tra; không được commit trạng thái lệch.
COMMIT;
~~~

Các câu SQL trên minh họa **giao thức của ứng dụng**, không phải một script có điều kiện tự thực thi. Ứng dụng phải kiểm tra kết quả từng lệnh và chọn **COMMIT/ROLLBACK** phù hợp. Khi **DELETE** không xóa hàng nào, không thực hiện phép trừ và có thể trả kết quả “đã bỏ thích” theo tính idempotent của API.

Cần kiểm tra các cuộc đua **thích → bỏ thích → thích lại** cùng người/bài, trạng thái hiện hành, thứ tự khóa và retry khi deadlock. Nếu một đường ghi bỏ qua việc cập nhật bộ đếm, schema có khóa chính và CHECK vẫn không đủ để tự nhận biết SUM/COUNT khác nguồn.

### 4.3. Lợi ích và chi phí

**Lợi ích:** Sau commit, hai bảng cùng một PostgreSQL có thể được đọc ở trạng thái phù hợp với transaction. Không cần queue hay worker để tạo hiệu ứng đếm.

**Chi phí:** Mỗi lượt thích/bỏ thích không chỉ ghi một quan hệ mà còn cập nhật thêm một hàng bộ đếm. Việc update có thể phát sinh WAL, thay đổi index/row version, giữ khóa và làm tăng độ trễ ghi. Với bài “nóng”, rất nhiều người cùng cập nhật **post_like_counts** trên một hàng, tạo **hot row**.

Vì thế, nhất quán tức thời không có giá cố định. Nó có thể rất hợp lý ở tần suất nhỏ, nhưng khó đáp ứng throughput lớn nếu toàn bộ cập nhật tập trung vào một hàng.

## 5. Phương án B: ghi nguồn ngay, làm mới bộ đếm bất đồng bộ

Một kiến trúc khác:

~~~text
API Like
   |
   v
[PostgreSQL nguồn]
  post_likes (nguồn chuẩn)
  like_event_outbox (ghi cùng transaction)
   |
   | Publisher gửi sự kiện; có thể gửi lại
   v
[Queue / stream]
   |
   | Consumer có dedupe, retry và giám sát
   v
[Kho đọc]
  post_like_counts (projection)
   |
   v
Trang danh sách có thể thấy bộ đếm cũ tạm thời
~~~

Ở phương án này, **API xác nhận thành công sau khi quan hệ thích và outbox đã commit**, không phải sau khi mọi bảng đếm đã cập nhật. Đó là quyết định hợp đồng rất quan trọng: trạng thái “người dùng đã thích” đúng tại nguồn, trong khi số đếm công khai có thể còn cũ.

### 5.1. Outbox: không được commit nguồn rồi hy vọng gửi event thành công

Ví dụ trong database nguồn:

~~~sql
CREATE TABLE like_event_outbox (
    event_id UUID PRIMARY KEY,
    post_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('LikeAdded', 'LikeRemoved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);
~~~

Khi có lượt thích mới:

~~~sql
WITH added AS (
    INSERT INTO post_likes (post_id, user_id)
    VALUES ($1, $2)
    ON CONFLICT (post_id, user_id) DO NOTHING
    RETURNING post_id, user_id
)
INSERT INTO like_event_outbox (
    event_id, post_id, user_id, event_type
)
SELECT
    $3::UUID,
    post_id,
    user_id,
    'LikeAdded'
FROM added;
~~~

Nếu cặp quan hệ đã tồn tại thì **không phát một sự kiện tăng giả**. Nếu có thêm quan hệ mới, sự kiện được ghi **nguyên tử cùng thay đổi nguồn** trong câu lệnh.

Publisher đọc các hàng chưa phát, gửi message rồi đánh dấu đã phát. Có thể có trường hợp message đã gửi nhưng publisher dừng trước khi đánh dấu: event sẽ bị gửi lại. Đó là lý do người tiêu thụ phải **idempotent**; outbox không tạo hiệu ứng exactly-once xuyên các thành phần một cách tự động.

Đường **bỏ thích** cũng phải phát **LikeRemoved** chỉ khi quan hệ thật sự bị xóa, trong cùng ranh giới giao dịch. Nếu có nhập dữ liệu, xóa bài, khôi phục dữ liệu hay thay đổi quan hệ bằng đường khác, mọi đường ấy cần tạo sự kiện hoặc có quy trình rebuild.

### 5.2. Consumer chống nhận lại một sự kiện

Giả sử **kho đọc** cũng là PostgreSQL và có bảng:

Nếu kho đọc là **database riêng**, bảng **post_like_counts** tại đó phải có lược đồ phù hợp với kho đọc; không thể dùng khóa ngoại tham chiếu trực tiếp tới **posts** chỉ tồn tại trong database nguồn. Các ví dụ cập nhật bên dưới minh họa SQL chạy tại nơi lưu projection, không phải một giao dịch xuyên hai database.

~~~sql
CREATE TABLE applied_like_events (
    event_id UUID PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Với sự kiện **LikeAdded** đã được kiểm tra, một câu lệnh minh họa cách lưu dấu và tăng bộ đếm trong cùng transaction của kho đọc:

~~~sql
WITH first_application AS (
    INSERT INTO applied_like_events (event_id)
    VALUES ($1::UUID)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
)
INSERT INTO post_like_counts AS counters (
    post_id, like_count
)
SELECT $2::BIGINT, 1
FROM first_application
ON CONFLICT (post_id)
DO UPDATE SET
    like_count = counters.like_count + EXCLUDED.like_count;
~~~

Nếu cùng **event_id** được phát lại, **first_application** không trả hàng, bộ đếm không tăng lần hai. Bản ghi chống trùng và tăng tổng phải cùng commit/rollback; nếu ghi dấu ở một database còn tăng tổng ở database khác không có cơ chế phù hợp, vẫn có thể xuất hiện lỗi một phần.

Ví dụ này **chỉ minh họa sự kiện tăng**. Khi phải xử lý **LikeRemoved**, thứ tự sự kiện **thích/bỏ thích** theo cùng người và bài là điều quan trọng; nếu event giảm được áp dụng trước event tăng trong khi bộ đếm đang bằng 0, ràng buộc không âm có thể chặn cập nhật. Các lựa chọn gồm:

- Giữ thứ tự xử lý theo **post_id** trong pipeline khi mô hình dùng delta tăng/giảm, đồng thời xử lý retry và sự kiện đến muộn.
- Phát **trạng thái hoặc số đếm tuyệt đối kèm phiên bản tăng đơn điệu** của nguồn rồi chỉ nhận phiên bản mới hơn.
- Tái tính **COUNT** từ tập quan hệ nguồn để sửa projection, khi chi phí và quyền truy cập cho phép.
- Phân vùng/shard bộ đếm hoặc gom lô sự kiện với giao thức duy trì kết quả không trùng và không thiếu.

**Event ID chỉ giải quyết việc áp dụng lặp cùng một event, không giải quyết event mất, event sai thứ tự hoặc hai event khác ID đại diện cùng một thao tác nghiệp vụ.** Những ràng buộc đó phải được thiết kế riêng.

### 5.3. Nhất quán cuối cùng cần điều kiện hội tụ và khả năng phục hồi

Nếu worker chết nhưng event còn trong outbox/queue và consumer có thể khởi động lại, bản sao còn cơ hội bắt kịp. Nếu event bị mất và hệ thống không phát hiện, bộ đếm có thể lệch vô thời hạn.

Một hợp đồng thực dụng cần nêu:

- **Nguồn chuẩn** và công thức tính lại.
- **Cách truyền** sự kiện có thể retry, phát lại hoặc lấy lại thay đổi nguồn.
- **Idempotency** và thứ tự áp dụng.
- **Độ tươi tối đa hoặc mục tiêu phân vị** theo use case.
- **Đối soát định kỳ** và quy trình bù trừ/rebuild.
- **Hành vi giao diện** khi quá thời gian đồng bộ: hiển thị dữ liệu cũ có nhãn, ẩn số, đọc trực tiếp nguồn hoặc báo đang cập nhật.

Không thể nói eventual consistency “đảm bảo đúng trong 5 giây” nếu không đo được và không có khả năng duy trì giới hạn ấy khi tải tăng hoặc một thành phần lỗi.

## 6. Chi phí cập nhật: lợi ích đọc đi kèm nghĩa vụ ghi

Phi chuẩn hóa thường **đổi công việc thực hiện khi đọc lấy công việc phát sinh khi ghi**. Một sơ đồ đánh đổi:

~~~text
Không lưu tổng:
  READ: SELECT ... COUNT/SUM/JOIN nhiều bản ghi
  WRITE: ghi quan hệ hoặc sự kiện nguồn

Lưu tổng đồng bộ:
  READ: đọc một bản ghi đã tổng hợp
  WRITE: nguồn + tổng + index/WAL/khóa trong transaction

Lưu tổng bất đồng bộ:
  READ: đọc projection, có thể cũ
  WRITE: nguồn + outbox; sau đó consumer cập nhật projection
  OPS: queue, retry, lag, dedupe, đối soát, rebuild
~~~

### 6.1. Write amplification và fan-out

**Write amplification** trong ngữ cảnh mô hình dữ liệu là mức tăng công việc ghi do một thay đổi nguồn kéo theo các bản sao, chỉ mục hoặc phép tổng hợp cần cập nhật.

Ví dụ:

- Thêm một lượt thích: một quan hệ + một hàng đếm nếu đồng bộ.
- Đổi tên danh mục: có thể phải sửa **hàng trăm nghìn sản phẩm** nếu tên được sao chép vào mỗi thẻ sản phẩm.
- Sửa trạng thái một giao dịch: có thể phải bù nhiều nhóm tổng hợp ngày, tiền tệ hoặc trạng thái.
- Thay quyền công khai: có thể phải xóa/ẩn nhiều bản sao trong search index, cache hoặc hệ phân tích.

**Fan-out** đo số bản ghi đích bị tác động bởi một thay đổi nguồn. Một sự kiện đổi tên ít xảy ra vẫn có thể tạo một đợt ghi rất lớn khi fan-out cao. Cần đo cả số hàng cập nhật và thời gian hoàn tất, không chỉ số byte của trường được sao chép.

### 6.2. Hot row, lock contention và độ trễ ghi

Bộ đếm lưu trên một hàng duy nhất có lợi cho đọc, nhưng nhiều giao dịch cùng tăng hàng ấy phải phối hợp khóa. Dưới tải cao, thời gian chờ khóa có thể tăng nhanh; một transaction dài còn kéo theo hàng đợi các transaction khác.

Các chỉ số nên đo: **p95/p99 ghi**, thời gian chờ khóa, deadlock, số retry, throughput, CPU, WAL, I/O và độ tăng kích thước bảng/index. Không suy rằng truy vấn đọc nhanh hơn 20 ms thì toàn hệ thống “nhanh hơn 20 ms”: tải ghi và tài nguyên nền có thể tăng.

Một số giải pháp chỉ hợp lý theo từng điều kiện:

- **Giữ tính lại khi đọc** nếu COUNT theo chỉ mục vẫn đủ nhanh.
- **Batch updates** nếu nghiệp vụ chấp nhận trễ.
- **Sharded counters** khi một hàng quá nóng: phân tán cập nhật nhưng phải tổng hợp nhiều shard và quản lý chống trùng.
- **Projection riêng** nếu đọc nhiều, dữ liệu khác kho và có thể chậm.
- **Chuyển trách nhiệm tổng hợp sang hệ phân tích/stream** khi cần nhiều chiều và tải lớn.

Sharding không tự sửa lỗi đếm trùng; batch không tự bảo đảm độ tươi; dùng queue không tự giảm tổng tài nguyên cần xử lý. Đây đều là đánh đổi phải đo.

### 6.3. Materialized view và bảng tổng hợp

Một dashboard doanh số theo ngày có thể chọn:

- **Tính SUM/COUNT khi đọc:** đúng theo nguồn tại snapshot truy vấn, nhưng có thể quét nhiều bản ghi.
- **Materialized view:** đọc nhanh theo dữ liệu ở lần REFRESH gần nhất; refresh có thể phải quét/tính lại nhiều dữ liệu.
- **Bảng tổng hợp tăng dần trong transaction:** ghi mỗi sự kiện và cập nhật tổng cùng nhau, nhưng có thể tạo hàng nóng.
- **Bảng tổng hợp từ sự kiện bất đồng bộ:** giảm áp lực lên đường giao dịch chính, đổi lại có lag, event đến muộn, đối soát và rebuild.

Bảng tổng hợp còn phải định nghĩa **grain** (ví dụ ngày × loại tiền), timezone, trạng thái và quy tắc xử lý refund. Không có các định nghĩa ấy thì dữ liệu có thể nhất quán về cập nhật nhưng sai về ý nghĩa.

## 7. Bảng lựa chọn theo rủi ro nghiệp vụ

| Use case | Độ tươi/nhất quán thường cần | Hướng thiết kế cần đánh giá |
| --- | --- | --- |
| Xác nhận trừ tồn kho để cam kết bán | Không được dựa vào số cũ làm vượt hạn mức | Quy trình kiểm tra/giữ chỗ/trừ nguồn có kiểm soát tương tranh |
| Số dư khả dụng để phê duyệt chi tiền | Phải dựa trên nghĩa vụ giao dịch đã xác nhận | Ledger/nguồn giao dịch và cơ chế quyết định nhất quán |
| Trạng thái “tôi đã thích bài này” sau khi API thành công | Phải phù hợp thao tác người dùng vừa commit | Đọc quan hệ nguồn hoặc kết quả ghi |
| Số lượt thích trên danh sách công khai | Có thể trễ nếu đã công bố và đo được | Counter đồng bộ hoặc projection eventual |
| Tên danh mục trên trang tìm kiếm | Có thể trễ có giới hạn nếu nghiệp vụ cho phép | JOIN, cache hoặc projection phiên bản hóa |
| Quyền truy cập hoặc yêu cầu gỡ thông tin | Không được giả định trễ là chấp nhận được | Kiểm tra quyền tại điểm quyết định, ưu tiên thu hồi an toàn |
| Dashboard vận hành mỗi 5 phút | Có thể cho phép chậm theo SLO | Materialized view, pre-aggregation hoặc streaming |
| Giá/địa chỉ được chốt trên đơn cũ | Phải bảo toàn sự thật tại thời điểm giao dịch | Snapshot lịch sử, không cập nhật theo hồ sơ hiện hành |

**Không có quy tắc “mọi dữ liệu tài chính luôn cần một transaction SQL duy nhất”**. Một hệ thống tài chính phân tán có thể dùng ledger, quy trình bù và nhiều cơ chế khác. Điều không thay đổi là **quyết định làm phát sinh nghĩa vụ phải dựa trên trạng thái đã được xác thực với bất biến phù hợp**, chứ không từ read projection có thể cũ.

### 7.1. Ranh giới trong document, graph và analytics

Trong **document database**, nếu bài viết và bộ đếm cùng nằm trong một document, một cập nhật nguyên tử trên document có thể phù hợp nhưng không tự bảo đảm trạng thái từ tập quan hệ nằm ở nhiều document. Cần xác định ranh giới transaction và fan-out nếu cập nhật nhiều tài liệu.

Trong **graph database**, số bạn bè dẫn xuất từ số cạnh liên kết. Ghi thêm cạnh và sửa bộ đếm trên đỉnh có thể cần transaction; nếu bộ đếm được xây bất đồng bộ, truy vấn trực tiếp cạnh và đọc thuộc tính đếm có thể khác nhau tạm thời. Đỉnh có bậc rất cao có thể thành điểm nóng.

Trong **hệ phân tích**, dữ liệu bán hàng theo ngày được nạp theo lô hoặc stream; dashboard có thể đọc rất nhanh nhưng cần watermark, quy tắc event đến muộn và phiên bản công thức. Nếu đọc một khoản tiền theo nhiều loại tiền tệ, phải có dimension currency và quy tắc quy đổi trước khi tổng hợp.

Các cơ chế cụ thể khác nhau giữa hệ quản trị. Đừng lấy cam kết transaction một document hay một hàng SQL rồi suy rộng sang mọi bản sao nằm ở nhiều dịch vụ.

## 8. Đối soát: khi nào bộ đếm lệch là lỗi?

Có thể tính lại số lượt thích từ quan hệ nguồn:

~~~sql
WITH actual AS (
    SELECT
        p.post_id,
        COUNT(l.user_id)::BIGINT AS exact_count
    FROM posts AS p
    LEFT JOIN post_likes AS l
        ON l.post_id = p.post_id
    GROUP BY p.post_id
)
SELECT
    COALESCE(a.post_id, c.post_id) AS post_id,
    a.exact_count,
    c.like_count AS stored_count
FROM actual AS a
FULL OUTER JOIN post_like_counts AS c
    ON c.post_id = a.post_id
WHERE a.post_id IS NULL
   OR c.post_id IS NULL
   OR a.exact_count IS DISTINCT FROM c.like_count
ORDER BY post_id;
~~~

**COUNT(l.user_id)** thay vì **COUNT(*)** để một bài chưa ai thích được đếm bằng 0 ngay cả khi có một hàng sinh ra từ **LEFT JOIN**. **FULL OUTER JOIN** bắt được cả trường hợp bảng đếm thiếu hàng hoặc có hàng thừa.

Cần đọc kết quả trong đúng bối cảnh:

- **Đồng bộ trong một PostgreSQL:** nếu giao dịch ghi đã commit, mọi đường ghi đều tuân thủ hợp đồng và phép so đọc cùng snapshot hợp lệ, một sai lệch là dấu hiệu cần điều tra.
- **Bất đồng bộ:** bảng đếm có thể tạm cũ. Không được gọi mọi sai lệch tức thời là lỗi; cần so tại cùng **watermark/phiên bản** hoặc chỉ xét các cập nhật đã vượt cửa sổ đồng bộ cho phép.
- **Hai database khác nhau:** không thể giả định SQL JOIN trực tiếp thực hiện được, hay hai lệnh đọc độc lập ở hai nơi đã lấy cùng snapshot thời gian.
- **Trong migration/backfill:** dữ liệu chưa chuyển xong cần được phân loại riêng, không lẫn với lỗi đồng bộ khi hệ thống đã đi vào vận hành bình thường.

Nếu đã chứng minh projection lệch, cần **sửa lại từ nguồn chuẩn** hoặc phát lại phần thay đổi có kiểm soát. Không nên sửa tùy ý các con số trong bảng tổng mà không xác định nguyên nhân; lỗi có thể tái xuất hiện khi worker chạy tiếp.

### 8.1. Thước đo độ trễ cần đo từ đâu tới đâu?

Ví dụ yêu cầu “bộ đếm công khai không cũ quá 30 giây”:

~~~text
T0 = nguồn commit thao tác thích
T1 = outbox được publisher gửi thành công
T2 = consumer nhận event
T3 = projection đã commit thay đổi
T4 = API đọc được giá trị mới
~~~

Từ **T0 đến T4** phản ánh độ trễ người đọc quan sát; đo **T2 đến T3** chỉ là thời gian xử lý bên consumer và có thể bỏ qua thời gian chờ publisher/queue.

Các chỉ số đáng theo dõi:

| Chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| End-to-end freshness lag | Thay đổi nguồn mất bao lâu để xuất hiện ở API đọc? |
| Outbox oldest pending age | Có sự kiện đã commit nhưng chưa phát quá lâu không? |
| Queue/consumer backlog | Worker có bị tụt so với lưu lượng ghi không? |
| Applied event count và duplicate count | Có xử lý lặp nhiều, phát lại bất thường không? |
| Reconciliation mismatch | Bao nhiêu bản đếm không khớp sau cửa sổ cho phép? |
| Retry/dead-letter count | Có sự kiện luôn thất bại mà không được xử lý không? |
| p95/p99 read/write latency | Đổi kiến trúc có đạt SLO cả hai đường không? |
| Rebuild time và recovery progress | Sau sự cố có bắt kịp nguồn trong thời gian cho phép không? |

**p95 lag = 5 giây không chứng minh lag tối đa nhỏ hơn 30 giây.** Nếu SLA nói “tối đa 30 giây”, cần kiểm tra phần đuôi hoặc cực đại quan sát được và phương án xử lý khi vi phạm. Nếu chỉ dùng mục tiêu phân vị, phải công bố cụ thể tỷ lệ và cửa sổ đo.

## 9. Một thí nghiệm lựa chọn dựa trên số liệu

Giả sử một dịch vụ đọc số lượt thích có mục tiêu:

- **API đọc danh sách:** p95 không quá **120 ms**.
- **API thêm/bỏ thích:** p95 không quá **160 ms**.
- **Bộ đếm công khai:** được phép chậm tối đa **30 giây**.
- **Quan hệ “người dùng này đã thích”:** phải đúng theo nguồn khi thao tác thành công.

Nhóm đo ba phương án dưới **cùng một tải đại diện**. Các con số sau là **giả định dùng để học cách ra quyết định**, không phải benchmark thật:

| Kết quả đo giả định | COUNT từ nguồn | Tổng đồng bộ cùng DB | Tổng eventual qua event |
| --- | ---: | ---: | ---: |
| API danh sách p95 | 155 ms | 78 ms | 73 ms |
| API thích p95 | 95 ms | 210 ms | 103 ms |
| Độ trễ bản đếm cực đại quan sát | Không có projection | Không có projection khác | 46 giây |
| Điểm nghẽn quan sát | Đọc COUNT lặp nhiều | Hot row của bài phổ biến | Queue lag giờ cao điểm |
| Chi phí bổ sung | CPU/IO đọc nguồn | WAL, khóa và ghi bộ đếm | Outbox, consumer, bảng đếm, retry |
| Đạt tất cả điều kiện trên? | **Không**: đọc chậm | **Không**: ghi chậm | **Không**: bản đếm trễ quá mức |

Kết luận đúng **không phải** “chọn eventual vì p95 đọc thấp nhất”. Cả ba phương án đều còn một điểm chưa đạt. Nhóm có thể thử:

1. Tối ưu COUNT theo access pattern và chỉ mục để xem liệu phương án từ nguồn đủ tốt không.
2. Với tổng đồng bộ, đo số bài có hot row và thử chia tải nếu cần.
3. Với eventual, giảm backlog, theo dõi outbox và đo lại độ trễ tối đa; hoặc thương lượng giới hạn trễ nếu nghiệp vụ thật sự cho phép.
4. Tách trạng thái “tôi đã thích” đọc từ nguồn khỏi số tổng công khai, không dùng bảng eventual làm bằng chứng rằng thao tác cá nhân đã commit.

**Không cộng/trừ các số p95 từ các bảng khác nhau để suy ra p95 toàn luồng.** Mỗi chỉ số là phân vị được đo trực tiếp trên một nhóm yêu cầu; khi thay đổi tỷ lệ đọc/ghi, phân phối đầu vào và tải đồng thời, phải đo lại.

## 10. Backfill và triển khai an toàn khi đổi mức nhất quán

Giả sử hệ thống trước đây chạy COUNT từ nguồn; nay muốn thêm **post_like_counts** phục vụ đọc. Không nên tạo bảng trống rồi lập tức chuyển toàn bộ API sang đọc bảng ấy.

Một trình tự tham khảo:

1. **Chốt nguồn chuẩn và bất biến:** quan hệ trong **post_likes**; định nghĩa like_count là COUNT các quan hệ hiện hành.
2. **Chọn hợp đồng nhất quán:** cập nhật trong cùng transaction hay eventual; ai sở hữu đường ghi/projection, SLO ra sao.
3. **Chuẩn bị lược đồ và index:** đặt khóa duy nhất, CHECK không âm, kiểm tra quyền ghi và truy vấn truy cập.
4. **Kích hoạt ghi thay đổi hoặc thu sự kiện:** đảm bảo không bỏ thay đổi phát sinh trong lúc nạp lịch sử.
5. **Backfill vào bảng mới từ snapshot nguồn có mốc rõ ràng:** kiểm soát tính đồng thời và lượng dữ liệu phải quét.
6. **Bắt kịp những cập nhật sau mốc:** với eventual cần checkpoint/replay, xử lý lặp và thứ tự; với đồng bộ cần bảo vệ tránh backfill ghi đè giá trị đang được cập nhật.
7. **Đối soát số liệu:** kiểm tra bài không có like, bài cực nhiều like, thao tác thích/bỏ thích liên tiếp, xóa bài và sự kiện bị thử lại.
8. **Chuyển đọc dần:** so câu trả lời từ nguồn với bản dẫn xuất, quan sát latency và lag; có đường quay lại nguồn khi lỗi.
9. **Thử phục hồi:** dừng worker, replay event, rebuild và xác nhận hệ thống hội tụ.

Nếu backfill đọc số đếm khi bài có 100 like, sau đó consumer đã áp dụng sự kiện tăng lên 101 mà một job cũ ghi lại **100**, projection bị lùi. Cần chiến lược version/checkpoint hoặc nạp bảng song song rồi chuyển có kiểm soát. Chỉ “chạy UPDATE tất cả” không chứng minh được an toàn khi nguồn đang thay đổi.

### 10.1. Khi bỏ một bản sao

Phi chuẩn hóa phải có khả năng được đánh giá lại. Nếu việc tối ưu truy vấn nguồn làm COUNT đủ nhanh, hoặc chi phí vận hành queue/hot row vượt lợi ích, có thể quay về tính khi đọc. Tuy nhiên, cần xác nhận không còn API, batch, báo cáo hay dịch vụ nào phụ thuộc vào bảng đếm trước khi ngừng cập nhật hoặc xóa.

## 11. Thực hành: viết hợp đồng cho một trường dẫn xuất

Ví dụ bản hợp đồng rút gọn cho **post_like_counts.like_count**:

| Mục | Giá trị cần ghi rõ |
| --- | --- |
| Nguồn chuẩn | **post_likes**, khóa **(post_id, user_id)** |
| Công thức | COUNT số quan hệ thích hiện còn tồn tại theo post_id |
| Consumer | Dịch vụ tạo bảng đếm hoặc giao dịch đồng bộ cùng DB |
| Thao tác phát sinh | Like, unlike, xóa bài, nhập liệu/khôi phục liên quan |
| Nhất quán | Đồng bộ sau commit cùng DB, hoặc eventual với SLO rõ |
| Phát sự kiện nếu eventual | Outbox ghi cùng thay đổi nguồn |
| Chống trùng | PK quan hệ + event ID/định danh xử lý |
| Thứ tự | Quy tắc xử lý thích/bỏ thích, version hoặc partition |
| Tính đúng | COUNT lại nguồn trên cùng snapshot/checkpoint |
| Tài nguyên | p95/p99 ghi/đọc, lock waits, backlog, WAL |
| Khả năng phục hồi | Replay/backfill, rebuild bảng, xác nhận hội tụ |
| Trách nhiệm | Nhóm nguồn sở hữu quan hệ; nhóm đọc sở hữu projection và giám sát |

Bất kỳ dòng nào trong bảng hợp đồng chưa có câu trả lời đều là một rủi ro thiết kế cần được giải quyết trước khi phụ thuộc hoàn toàn vào dữ liệu dẫn xuất.

## 12. Bài tập vận dụng

### Bài 1 — Nút thích và màn hình danh sách

Người dùng bấm thích một bài. API ghi quan hệ vào nguồn và trả thành công, nhưng danh sách công khai vẫn cho thấy bộ đếm cũ thêm 4 giây. Hợp đồng giao diện cho phép số đếm công khai trễ 15 giây.

**Câu hỏi:** Đây có nhất thiết là lỗi không? Trạng thái “tôi đã thích” nên lấy từ đâu?

### Bài 2 — Bộ đếm gấp đôi sau retry

Một consumer đã tăng bộ đếm cho **LikeAdded event-123**, sau đó crash trước khi ACK. Queue phát lại đúng event này và consumer tăng thêm 1.

**Câu hỏi:** Thiết kế thiếu điều gì? Nếu cùng thao tác được phát thành hai event ID khác nhau thì cần kiểm tra thêm ở đâu?

### Bài 3 — Hot row khi phát hành bài mới

Một bài nổi tiếng có 25.000 lượt thích mỗi giây. Bộ đếm được cập nhật cùng transaction với mỗi INSERT quan hệ và p99 API thích tăng mạnh, nhưng API đọc rất nhanh.

**Câu hỏi:** Vì sao hệ thống bị nghẽn? Nêu hai phương án đánh đổi khác nhau và điều kiện chấp nhận.

### Bài 4 — Độ trễ của dashboard

Dashboard doanh số đọc bảng tổng hợp eventual có p95 dữ liệu trễ 8 giây nhưng từng có lúc trễ 90 giây. Nghiệp vụ quy định **không chậm hơn 60 giây**.

**Câu hỏi:** Có đạt SLO không? Cần đo và cảnh báo ở những khâu nào?

### Bài 5 — Giá đã chốt hay giá hiện hành?

Một người đề xuất cập nhật **order_items.unit_price_at_confirmation** mỗi khi **catalog_products.current_price** đổi để “dữ liệu luôn nhất quán”.

**Câu hỏi:** Quy tắc đó đúng hay sai? Vì sao khác với việc đồng bộ **product_cards.current_price_display**?

### Bài 6 — Đối soát 100 khác 101

Nguồn ghi nhận bài P có 101 lượt thích; bảng đếm eventual là 100. Consumer đang xử lý event mới, nhưng không có thông tin thời điểm commit hay checkpoint.

**Câu hỏi:** Có thể kết luận vi phạm SLO trễ 30 giây không? Cần metadata gì?

### Gợi ý lời giải

1. **Không nhất thiết là lỗi** nếu số đếm trễ 4 giây trong hợp đồng 15 giây và cuối cùng hội tụ. Trạng thái cá nhân nên dựa trên quan hệ nguồn hoặc kết quả thao tác đã commit; có thể hiển thị trạng thái dự kiến với cơ chế phục hồi khi thao tác lỗi.
2. Cần **dedupe/idempotency** bằng event ID, lưu dấu xử lý và cập nhật tổng trong cùng transaction của consumer. Nếu hai ID khác nhau đại diện một thao tác, phải có **định danh nghiệp vụ và ràng buộc duy nhất** ở nguồn, hoặc cơ chế xử lý tương đương.
3. Cùng một hàng bộ đếm bị cập nhật liên tục, tạo tranh chấp khóa và hàng đợi giao dịch. Có thể thử **sharded counter** (phức tạp khi đọc và đối soát) hoặc **eventual/batch aggregation** (cần chấp nhận độ trễ và xử lý sự kiện). Cần đo p95/p99 ghi, độ tươi, tính đúng và tài nguyên.
4. **Chưa đạt** vì đã quan sát 90 giây vượt 60 giây, dù p95 tốt. Theo dõi commit nguồn → outbox → queue → consumer → projection → API, oldest pending age, backlog, retry và số liệu lệch.
5. **Sai** với giá đã xác nhận: đó là sự thật lịch sử phải được giữ hoặc điều chỉnh bằng nghiệp vụ có dấu vết. **product_cards.current_price_display** là projection của giá hiện hành nên cần làm mới theo nguồn.
6. **Chưa thể kết luận theo thời gian** chỉ từ chênh số 1. Cần biết sự kiện nào đã commit, mốc áp dụng của projection, tuổi sự kiện còn thiếu, lag toàn pipeline và cách đo ngưỡng. Có thể đang đồng bộ hợp lệ hoặc đã mất event.

## 13. Ghi nhớ

**Nhất quán tức thời** là cam kết đúng trong một phạm vi ghi/đọc đã định sau commit; **nhất quán cuối cùng** chấp nhận khoảng lệch tạm thời với điều kiện hệ thống có thể hội tụ và đáp ứng độ tươi được thỏa thuận. Hai khái niệm không quyết định sẵn dữ liệu nào quan trọng: đó là việc của bất biến nghiệp vụ.

**Phi chuẩn hóa giảm chi phí đọc bằng cách chuyển một phần công việc sang ghi, đồng bộ và vận hành.** Bản sao có thể tạo nhiều lượt ghi, hot row, event retry, độ trễ, dữ liệu cũ hoặc nhu cầu rebuild. Một phương án chỉ đáng chọn khi **cả độ trễ đọc, độ trễ ghi, tính đúng và chi phí phục hồi** đều phù hợp.

Trước khi lưu thêm một bộ đếm, tổng tiền hoặc thông tin hiển thị, hãy tự hỏi: **“Sau thao tác nào dữ liệu bắt buộc phải đúng? Nếu được phép cũ thì cũ bao lâu? Mỗi lần nguồn đổi ta trả chi phí gì, và khi sai làm sao biết để sửa?”**
