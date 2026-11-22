# Giới hạn dư thừa để mô hình vẫn giải thích và bảo trì được

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích tại sao phi chuẩn hóa **không đồng nghĩa** với sao chép càng nhiều dữ liệu càng tốt.
- Phân định **sự thật nghiệp vụ**, **ảnh chụp lịch sử** và **giá trị dẫn xuất** để không vô tình tạo nhiều nơi cùng có quyền sửa một thuộc tính.
- Thiết lập giới hạn về **phạm vi nhân bản, số bản sao, số phụ thuộc, chi phí cập nhật, độ trễ và khả năng khôi phục** cho từng quyết định phi chuẩn hóa.
- Thiết kế mô hình đọc phục vụ một access pattern cụ thể, có nguồn chuẩn, tên trường rõ nghĩa, phiên bản, trách nhiệm sở hữu và truy vấn đối soát.
- Phát hiện mô hình có thể đọc nhanh nhưng khó giải thích, chẳng hạn chuỗi bản sao của bản sao, bảng chứa quá nhiều chỉ số không rõ công thức hoặc trường được sao chép không có cơ chế làm mới.
- Đưa ra quyết định giữ, thu hẹp hoặc gỡ bỏ dữ liệu dư thừa bằng bằng chứng đo hiệu năng và chi phí bảo trì.

Trong chương **Phi chuẩn hóa** của **DATABASE_DATA_MODELING**, ta học cách chuyển yêu cầu nghiệp vụ thành lược đồ có thực thể, quan hệ, khóa, ràng buộc và chỉ mục rõ ràng. Khi mở rộng sang document, đồ thị hoặc hệ phân tích, nguyên tắc vẫn vậy: **mỗi dữ liệu được lưu thêm phải có lý do, ý nghĩa, người chịu trách nhiệm và cách kiểm chứng**.

## 1. Phi chuẩn hóa có chủ đích cần một ranh giới

Giả sử hệ thống thương mại điện tử quản lý **sản phẩm**, **danh mục**, **đơn hàng** và **đánh giá**. Trang danh sách hiển thị tên sản phẩm, giá, tên danh mục và điểm đánh giá trung bình. Một nhóm đề xuất:

- Sao chép **category_name** vào bảng **products** để bớt JOIN.
- Sao chép **category_name** lần nữa vào bảng **product_cards**.
- Sao chép **category_name** vào từng document tìm kiếm.
- Lưu cùng lúc **review_count**, **rating_sum**, **average_rating** trong nhiều bảng.
- Sao chép **current_price** vào lịch sử đơn hàng và tự động làm mới nó khi giá bán đổi.

Một số yêu cầu đọc có thể nhanh hơn, nhưng câu hỏi khó dần: khi đổi tên danh mục, phải sửa bao nhiêu nơi? **average_rating** tính từ trạng thái đánh giá nào? Nếu mỗi nơi có giá khác nhau, nơi nào đúng? Tại sao giá đơn cũ lại đổi?

Đây là dấu hiệu **dư thừa lan rộng không có hợp đồng**. Tối ưu một SELECT không đủ để biện minh cho việc tạo ra nhiều phiên bản của cùng một sự thật.

Nguyên tắc thực hành:

> **Chỉ lưu giá trị dẫn xuất ở đúng những ranh giới đọc cần nó, với một nguồn có thẩm quyền và một cách tái dựng được chứng minh.**

Giới hạn dư thừa không có nghĩa “chỉ được có một bản sao” hoặc “không bao giờ nhúng dữ liệu”. Có hệ thống tìm kiếm cần search document, dashboard cần bảng tổng hợp, dịch vụ phân tán cần projection riêng. Vấn đề là **mỗi bản sao phải có hợp đồng độc lập và lợi ích đáng chi phí**.

### 1.1. Bốn câu hỏi một người mới phải trả lời được

Khi đọc lược đồ mà không có người tạo ra nó bên cạnh, người khác phải giải thích được:

1. **Trường này có nghĩa gì?** Ví dụ **category_name_current** khác **category_name_at_purchase**.
2. **Nó đến từ đâu?** Bảng/dịch vụ/sự kiện nguồn và công thức hay quy tắc biến đổi.
3. **Nó được cập nhật khi nào và bởi ai?** Cùng transaction, sự kiện bất đồng bộ, refresh định kỳ hoặc bất biến lịch sử.
4. **Nếu sai, làm sao biết và sửa?** Đối soát, làm mới, tái dựng và cách chuyển về đường đọc an toàn.

Nếu một bảng không trả lời được đủ bốn câu hỏi, nó chưa phải một thiết kế phi chuẩn hóa có thể bảo trì, dù hiện tại mọi test API đều xanh.

## 2. Phân loại dữ liệu trước khi tính số lượng bản sao

Không thể giới hạn dư thừa chỉ bằng cách đếm cột trùng tên. Ta cần phân biệt **ngữ nghĩa**:

| Loại dữ liệu | Ví dụ | Quy tắc thay đổi | Cách kiểm chứng |
| --- | --- | --- | --- |
| **Sự thật hiện hành** | **categories.display_name** | Đổi theo quyết định nghiệp vụ từ nơi sở hữu | Ràng buộc và lịch sử thay đổi nguồn |
| **Bản sao hiện hành** | **product_cards.category_name_display** | Làm mới theo nguồn trong độ trễ đã cam kết | So tên/phiên bản, kiểm tra lag |
| **Snapshot lịch sử** | **order_items.product_name_at_confirmation** | Giữ giá trị đã chốt; sửa bằng nghiệp vụ có dấu vết | So chứng từ/sự kiện xác nhận, không so tên hôm nay |
| **Kết quả tổng hợp** | **daily_sales.total_amount** | Tính từ các giao dịch hợp lệ theo grain/công thức | Tính lại từ nguồn theo cùng kỳ, tiền tệ và trạng thái |
| **Giá trị tính trong hàng** | **line_total = quantity × unit_price** | Đổi theo các thuộc tính cùng hàng | Generated column hoặc bất biến tính toán |
| **Cache tạm thời** | Dữ liệu thẻ sản phẩm trong cache | TTL/invalidation theo hợp đồng | Mốc tạo cache, phiên bản và so nguồn khi cần |

Một snapshot của đơn hàng **không phải** bản sao cần đồng bộ với sản phẩm hiện tại. Một bảng tổng hợp **không phải** nơi người dùng tự nhập giá trị doanh số tùy ý. Phân loại sai sẽ dẫn đến sửa sai bằng cách “đồng bộ cho giống nhau” nhưng lại làm hỏng lịch sử.

### 2.1. Ranh giới sự thật nên nằm ở mức thuộc tính và thời điểm

Nói “bảng products là nguồn chuẩn” vẫn có thể chưa đủ. Giá hiện hành có thể thuộc dịch vụ định giá, tên hiển thị thuộc Catalog; giá đã chấp nhận thuộc giao dịch đơn hàng. Khi nhiều hệ thống cùng lưu **price**, cần đặt tên và hợp đồng chính xác:

- **current_list_price**: giá niêm yết đang có hiệu lực.
- **product_cards.list_price_display**: bản sao của giá niêm yết dành cho hiển thị, có phiên bản.
- **order_items.unit_price_at_confirmation**: đơn giá áp dụng khi xác nhận, bất biến theo nghiệp vụ.
- **daily_revenue.net_amount**: chỉ số tính theo định nghĩa doanh thu đã công bố, không phải sao chép giá niêm yết.

Lưu nhiều trường cùng có kiểu **NUMERIC** không nhất thiết là dư thừa sai; **tự ý cho nhiều dịch vụ cùng quyết định một giá trị theo cùng ngữ nghĩa** mới là rủi ro lớn.

## 3. Đặt “ngân sách dư thừa” trước khi thêm cấu trúc

Một nhóm có thể dùng **ngân sách dư thừa (redundancy budget)** như công cụ review kiến trúc. Đây không phải một công thức tiêu chuẩn hay giới hạn cố định; nó là các ràng buộc cụ thể để tránh thiết kế tăng mãi mà không ai nhận trách nhiệm.

### 3.1. Sáu chiều phải ước lượng

| Chiều | Câu hỏi kiểm soát | Dấu hiệu vượt khả năng duy trì |
| --- | --- | --- |
| **Phạm vi** | Có bao nhiêu field thực sự cần cho access pattern? | Sao chép toàn bộ bản ghi “để phòng sau này” |
| **Số điểm lưu** | Có bao nhiêu nơi giữ cùng thuộc tính hiện hành? | Mỗi API tạo thêm một bản sao riêng mà không có nhu cầu riêng |
| **Fan-out** | Một thay đổi nguồn ảnh hưởng bao nhiêu hàng/document đích? | Đổi một tên làm ghi hàng triệu document trong lúc người dùng chờ |
| **Độ tươi/nhất quán** | Bản sao có thể cũ bao lâu? Ai đo? | “Gần thời gian thực” nhưng không có ngưỡng hay metric |
| **Chi phí vận hành** | Ai xử lý lỗi, backfill, schema evolution, replay? | Có pipeline nhưng không có người sở hữu hay cách khôi phục |
| **Giá trị đo được** | Giảm bao nhiêu độ trễ/tải/round-trip cho luồng nào? | Bỏ JOIN mà p95 hầu như không thay đổi, trong khi chi phí ghi tăng |

Ngoài ra, phải xem **quyền riêng tư và phạm vi truy cập**: nhân bản dữ liệu nhạy cảm có thể làm tăng điểm rò rỉ, yêu cầu xóa và trách nhiệm kiểm soát, ngay cả khi chi phí CPU nhỏ.

**Không có ngưỡng phổ quát** kiểu “tối đa ba bảng được phép lặp một cột”. Một search index và một cache có thể đều cần cùng trường vì có vòng đời và mục tiêu khác nhau. Ngược lại, **một** bản sao duy nhất nhưng không có nguồn chuẩn hoặc cách cập nhật cũng đã là lỗi thiết kế.

### 3.2. Dùng fan-out để nhận diện rủi ro ẩn

Giả sử:

- Một danh mục có **600.000** sản phẩm.
- Trang danh sách thường trả **40** sản phẩm.
- Tên danh mục đổi trung bình **vài lần mỗi tháng**.
- Nếu tên được nhúng vào mỗi product document trong kho tìm kiếm, một lần đổi tên có thể phải ghi **600.000 document**.

Nếu giữ mô hình quan hệ chuẩn hóa, trang danh sách có thể JOIN danh mục theo khóa chính sau khi giới hạn 40 sản phẩm; chi phí đọc có thể rất nhỏ. Nếu tạo bản nhúng, hệ thống trả thêm chi phí cập nhật hàng trăm nghìn document, lag, retry và đối soát.

Vì vậy, trước khi chép một trường từ quan hệ **1:N**, hãy đo ít nhất **phân bố N**: trung vị, p95/p99 và cực đại; không chỉ số trung bình. Một “điểm nóng” với hàng triệu bản ghi con có thể chi phối chi phí duy trì dù đa số thực thể chỉ có vài chục bản ghi con.

Fan-out không chỉ nằm ở UPDATE; nó còn bao gồm **số message, kích thước index, WAL, cache invalidation và thời gian tái dựng**. Đếm byte của một chuỗi tên không đủ để đánh giá chi phí thực.

### 3.3. Ưu tiên bản sao có vòng đời rõ thay vì bản sao phát sinh ngẫu nhiên

Một read model riêng có thể là nơi tập trung các trường cần cho **một dạng truy cập**. Nếu đã có bảng **product_cards** để phục vụ trang danh sách, không nên ngay lập tức thêm **category_name** vào **products**, **product_search_cache** và **homepage_cards** chỉ vì mỗi màn hình dùng tên danh mục.

Đó không phải lệnh cấm tối ưu chuyên biệt. Nếu search index cần document riêng hoặc màn hình có độ tươi khác nhau, có thể thêm projection khác; nhưng **mỗi bản mới phải được chứng minh bằng workload và hợp đồng riêng**, đồng thời cập nhật sơ đồ lineage.

## 4. Tìm nút thắt trước khi làm mô hình phức tạp

Một phép JOIN được viết trong SQL không phải bằng chứng rằng JOIN là nút thắt. Đường đọc có thể chậm vì:

- Trả quá nhiều cột, thiếu LIMIT/phân trang hoặc chọn sai tập dữ liệu trước khi JOIN.
- Không có chỉ mục phù hợp bộ lọc và ORDER BY.
- Ứng dụng gây **N+1 query**: lấy 40 sản phẩm rồi gọi thêm 40 truy vấn danh mục.
- Dữ liệu phân bố lệch khiến kế hoạch truy vấn không phù hợp một số trường hợp.
- Serialization, network, cache miss hoặc gọi liên dịch vụ chiếm phần lớn thời gian.

Ví dụ PostgreSQL, giả sử có **products(category_id)** và **categories(category_id)**:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.product_id,
    p.product_name,
    p.current_price,
    c.display_name AS category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.is_active = TRUE
ORDER BY p.created_at DESC, p.product_id DESC
LIMIT 40;
~~~

Cần đọc **actual rows**, **actual time**, buffer hit/read, dạng scan/sort/JOIN và số lượt gọi API. Nếu chỉ nối 40 hàng vào danh mục có chỉ mục khóa chính, **Nested Loop + Index Scan** có thể hoàn toàn phù hợp. Đừng nhận định một kế hoạch là xấu chỉ bởi tên node.

**EXPLAIN (ANALYZE)** thực sự chạy câu lệnh; chỉ dùng phù hợp môi trường, và nhớ “cost” của bộ tối ưu là ước lượng tương đối, không phải mili giây. Muốn so hệ thống phải đo **p50/p95/p99 toàn API** cùng CPU/I/O, throughput và tải ghi trong kịch bản đại diện.

### 4.1. Thứ tự thử phương án

Một trình tự hợp lý cho trường hợp danh sách sản phẩm là:

1. Viết lại truy vấn chọn đúng các cột, lọc và phân trang phù hợp.
2. Kiểm tra chỉ mục hỗ trợ bộ lọc/sắp xếp, tránh tạo chỉ mục trùng lặp.
3. Gộp truy vấn N+1 hoặc thử batch theo tập nếu ứng dụng đang gọi nhiều lần.
4. Đánh giá cache cho dữ liệu thay đổi ít nếu yêu cầu độ tươi cho phép.
5. Chỉ khi vẫn không đạt mục tiêu hoặc dữ liệu ở kho khác, cân nhắc projection/phi chuẩn hóa.
6. Đo lại **đọc, ghi, độ đúng, độ tươi và chi phí phục hồi**.

Nếu phương án chuẩn hóa đã đạt SLO, **không thêm bản sao** là kết luận hợp lệ và thường giúp mô hình dễ bảo trì hơn.

## 5. Thiết kế một projection có giới hạn: ví dụ sản phẩm và danh mục

Xét hệ thống với nguồn hiện hành trong PostgreSQL:

~~~sql
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    display_version BIGINT NOT NULL DEFAULT 1
        CHECK (display_version >= 1)
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL
        REFERENCES categories(category_id),
    product_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL
        CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    product_version BIGINT NOT NULL DEFAULT 1
        CHECK (product_version >= 1)
);
~~~

**categories.display_name** là nguồn chuẩn của tên danh mục hiện hành. **products.category_id** giữ quan hệ sản phẩm–danh mục. **products.current_price** là giá niêm yết hiện hành **trong ví dụ này**; hệ thống thực có thể có nguồn định giá riêng.

Giả sử yêu cầu đã chứng minh cần một read model dành cho trang danh sách. Ta thêm **một projection** có phạm vi đúng với trường cần đọc:

~~~sql
CREATE TABLE product_cards (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL,
    category_id BIGINT NOT NULL,
    category_name_display TEXT NOT NULL,
    product_version BIGINT NOT NULL
        CHECK (product_version >= 1),
    category_display_version BIGINT NOT NULL
        CHECK (category_display_version >= 1),
    projected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Không tạo thêm một **products.category_name** chỉ để projection đọc được tên: projection có thể nhận tên bằng JOIN lúc khởi tạo và được đồng bộ khi nguồn đổi. **products** giữ mô hình quan hệ bình thường; **product_cards** là một cấu trúc tối ưu đọc với mục đích rõ ràng.

Trong cùng PostgreSQL, có thể tạo lại dữ liệu ban đầu từ một truy vấn nguồn:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.current_price,
    p.currency,
    p.is_active,
    p.category_id,
    c.display_name AS category_name_display,
    p.product_version,
    c.display_version AS category_display_version
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id;
~~~

Truy vấn trên là **nguồn phép biến đổi để xây projection**, không phải lệnh backfill trực tiếp đủ an toàn khi có ghi đồng thời. Để đưa vào sản xuất, cần chốt mốc dữ liệu, nạp theo cơ chế không ghi lùi, phát các thay đổi trong lúc nạp và đối soát trước khi chuyển đường đọc.

### 5.1. Chỉ một nơi được sửa mỗi sự thật hiện hành

Trong thiết kế này:

- Thay tên danh mục: ghi **categories** và tăng **display_version**.
- Thay tên, giá, trạng thái hoặc danh mục của sản phẩm: ghi **products** và tăng **product_version**.
- Thay trường trên **product_cards**: chỉ pipeline đồng bộ/read model được làm, không phải giao diện quản trị chỉnh trực tiếp.
- Sửa giá trong đơn cũ: **không** ghi lại theo nguồn hiện hành; giá tại giao dịch là loại dữ liệu lịch sử khác.

Việc phân quyền ghi và tên bảng/cột phải củng cố quy tắc này. Nếu cho phép sửa **product_cards.category_name_display** trực tiếp rồi để worker sau đó ghi đè, hệ thống có hai người quyết định một giá trị nhưng không có cách giải thích ai đúng.

### 5.2. Giới hạn một lần đổi tên danh mục

Ví dụ một consumer đã nhận sự kiện tên danh mục có **category_id**, **display_name** và **display_version**; câu SQL tại projection PostgreSQL:

~~~sql
UPDATE product_cards
SET category_name_display = $2,
    category_display_version = $3,
    projected_at = CURRENT_TIMESTAMP
WHERE category_id = $1
  AND category_display_version < $3;
~~~

Điều kiện phiên bản giúp tránh event cũ ghi đè tên mới, điều kiện **category_id** tránh đổi tên cho sản phẩm đã chuyển sang danh mục khác. Tuy nhiên, nó **chưa giải quyết toàn bộ tương tranh**: khi sự kiện chuyển danh mục của sản phẩm đến trễ so với sự kiện đổi tên, hệ thống cần quy tắc về **product_version** và cách xây bản snapshot của cả hai thực thể.

Một phương án an toàn hơn trong một số kiến trúc là nhận sự kiện sản phẩm có version, cập nhật **thông tin sản phẩm** bằng điều kiện version cao hơn, rồi làm mới phần danh mục từ **trạng thái nguồn hiện tại hoặc một snapshot có mốc nhất quán**. Không được khẳng định chỉ một điều kiện version trên danh mục đủ bảo đảm toàn bộ product card đúng.

Với danh mục có fan-out quá lớn, việc UPDATE hàng trăm nghìn card có thể không đạt mục tiêu vận hành. Khi đó nên cân nhắc:

- Giữ JOIN với danh mục trong database quan hệ khi đọc.
- Dùng cache danh mục nhỏ tại tầng ứng dụng.
- Dùng một **category display map** tham chiếu theo ID trong hệ tìm kiếm nếu nền tảng và query shape hỗ trợ.
- Chấp nhận projection bất đồng bộ với kế hoạch làm mới theo lô và độ tươi được đo, **nếu nghiệp vụ cho phép**.

Không có lựa chọn nào miễn phí. Mỗi lựa chọn đều cần đo thời gian đọc, fan-out ghi, độ tươi và cách khôi phục.

## 6. Giới hạn bằng hợp đồng dữ liệu: ghi để người khác còn hiểu

Mỗi read model nên có một **hợp đồng ngắn, ổn định và kiểm chứng được**. Ví dụ cho **product_cards**:

| Trường hợp đồng | Giá trị trong ví dụ |
| --- | --- |
| Tên và mục đích | **product_cards** phục vụ thẻ sản phẩm trên trang danh sách |
| Grain | Một hàng cho mỗi **product_id** |
| Các nguồn chuẩn | **products** cho thuộc tính sản phẩm; **categories** cho tên danh mục hiện hành |
| Công thức biến đổi | Chọn trường sản phẩm và tên danh mục đang tham chiếu |
| Phạm vi dữ liệu | Chỉ field cần để dựng thẻ; không nhúng toàn bộ mô tả, địa chỉ khách, dữ liệu riêng tư |
| Quyền ghi | Pipeline projection; ứng dụng nghiệp vụ chỉ sửa nguồn |
| Ranh giới phiên bản | **product_version** và **category_display_version** có ý nghĩa theo từng thực thể |
| Nhất quán | Eventual trên trang danh sách, nếu được chấp nhận |
| Độ tươi | Ví dụ tên danh mục cũ tối đa **30 giây**; phải đo end-to-end |
| Xóa/sửa quan hệ | Bỏ/ẩn sản phẩm đúng cách; xử lý đổi **category_id**, xóa/ẩn danh mục |
| Đối soát | So theo nguồn cùng mốc/phiên bản; đo bản ghi thiếu, dư và lệch |
| Phục hồi | Tái dựng từ nguồn + replay thay đổi với checkpoint nhất quán |
| Chủ sở hữu | Nhóm nguồn và nhóm projection có trách nhiệm được phân định |
| Lý do tồn tại | Phương án chuẩn hóa chưa đạt SLO ở workload ghi nhận được |
| Điều kiện gỡ bỏ | Không còn consumer, hoặc giải pháp đơn giản hơn đạt các mục tiêu |

Không cần một tài liệu dài hàng trăm trang mới gọi là có hợp đồng. Quan trọng là **tên trường, truy vấn nguồn, bất biến, độ tươi, người sở hữu và cách sửa sai** đủ để một người khác triển khai, kiểm thử và vận hành.

### 6.1. Quy tắc đặt tên giúp tránh nhầm lẫn ngữ nghĩa

Ưu tiên tên thể hiện vai trò:

- **category_id**: quan hệ tới danh mục, không phải bản sao tên.
- **category_name_display** hoặc **category_name_cached**: dữ liệu hiển thị dẫn xuất.
- **category_display_version**: phiên bản nguồn đã được áp dụng cho tên.
- **product_name_at_purchase**: ảnh chụp tên tại sự kiện mua.
- **review_count_visible**: số đánh giá được phép hiển thị; khác tổng mọi đánh giá.
- **average_rating_visible**: trung bình theo những đánh giá hợp lệ có cùng định nghĩa với count.

Không dùng một cột **name**, **count** hoặc **total** thiếu ngữ cảnh để đại diện cho nhiều ý nghĩa. Ví dụ, một đơn có số tiền trước giảm giá, sau giảm giá và thực thu; đặt cả ba là **total** tại ba bảng khác nhau rồi trộn chúng trong báo cáo dễ gây lỗi dù mọi câu SQL đều chạy.

### 6.2. Giữ phép biến đổi càng ít tầng càng tốt

Sơ đồ khó bảo trì:

~~~text
categories.display_name (nguồn)
       |
       v
products.category_name (bản sao 1)
       |
       v
product_cards.category_name (bản sao 2)
       |
       v
search_documents.category_name (bản sao 3)
       |
       v
cache.category_name (bản sao 4)
~~~

Vấn đề không chỉ là bốn bản sao. Một lỗi tại **bản sao 1** lan qua các tầng sau; việc dựng lại search index có thể tái tạo từ nguồn đã sai. Để kiểm chứng, người vận hành phải lần ngược nhiều tầng mới thấy bản gốc.

Nếu có thể, để các mô hình đọc **dẫn xuất từ nguồn có thẩm quyền**, hoặc từ một sự kiện/snapshot đã được quản lý hợp đồng và xác minh. Trường hợp cần một pipeline nhiều bước vì quy mô hoặc kiến trúc, phải có lineage rõ, checkpoint, phép đo và nơi có thể tái dựng. **Giảm số tầng biến đổi độc lập** thường có giá trị bảo trì lớn hơn việc giảm một dòng JOIN.

## 7. Giới hạn số liệu tính sẵn: lưu đủ để đúng, không lưu mọi biến thể

Dư thừa không chỉ là sao chép tên. Các trường **review_count**, **rating_sum**, **average_rating**, **one_star_count**, **positive_rating_percent** cũng cần kiểm soát.

Giả sử một product có đánh giá với **rating** từ 1 đến 5, có trạng thái hiển thị. Màn hình cần **số đánh giá hợp lệ** và **điểm trung bình**.

Một thiết kế tổng hợp tối giản có thể lưu:

~~~text
product_rating_stats
  product_id                 -- grain: một sản phẩm
  visible_review_count       -- COUNT đánh giá được hiển thị
  visible_rating_sum         -- SUM điểm của đánh giá được hiển thị
  source_checkpoint          -- đã xử lý dữ liệu nguồn đến đâu
  calculated_at              -- thời điểm cập nhật
~~~

Khi đọc, nếu **visible_review_count > 0** thì tính **visible_rating_sum / visible_review_count**; nếu không có đánh giá thì trả giá trị chưa có điểm, không tự gán điểm trung bình bằng 0 nếu nghiệp vụ phân biệt hai trường hợp.

Một cách truy vấn trong PostgreSQL:

~~~sql
SELECT
    product_id,
    visible_review_count,
    CASE
        WHEN visible_review_count > 0
            THEN visible_rating_sum::NUMERIC
                 / visible_review_count
        ELSE NULL
    END AS average_rating
FROM product_rating_stats
WHERE product_id = $1;
~~~

Vì điểm trung bình phụ thuộc vào **SUM và COUNT**, lưu thêm trường **average_rating** chỉ để thuận tiện có thể làm tăng một bất biến phải duy trì. Nếu cần index/sort theo trung bình ở quy mô lớn, bản sao trung bình có thể được cân nhắc, nhưng phải có cách tính và làm mới nhất quán với hai thành phần nguồn.

### 7.1. Không “bù đại” khi trạng thái đánh giá đổi

Nếu một review đang hiển thị bị ẩn, bộ đếm hợp lệ giảm 1 và tổng điểm hợp lệ giảm đúng số điểm của review ấy. Nếu review sửa điểm từ 4 thành 2, **COUNT không đổi**, còn **SUM giảm 2**. Nếu review bị xóa hoặc phục hồi, cần xử lý tương ứng.

Đừng chỉ tăng count ở sự kiện **ReviewCreated** rồi bỏ qua **ReviewHidden**, **ReviewRestored** hoặc **ReviewRatingChanged**. Dữ liệu có thể ngày càng lệch trong khi giao diện đọc rất nhanh.

Nếu projection được làm mới theo sự kiện bất đồng bộ, phải có **định danh sự kiện, thứ tự hoặc phiên bản, quy tắc idempotency và khả năng đối soát**. Nếu yêu cầu chính xác tức thời và nguồn ở cùng DB, có thể cập nhật trong một giao dịch, nhưng phải đo contention trên hàng tổng hợp của sản phẩm được đánh giá nhiều.

### 7.2. Mỗi chiều tổng hợp thêm vào là một cam kết mới

Ví dụ dashboard bán hàng theo ngày và loại tiền:

~~~text
daily_sales_summary
  business_day
  currency
  order_count
  captured_amount
~~~

Grain là **(business_day, currency)**. Nếu thêm **store_id**, **channel**, **promotion_id**, số nhóm và số chiều phân tích thay đổi; phải định nghĩa xem một giao dịch thuộc một hay nhiều nhóm. Sao chép tất cả chiều có thể làm số tổ hợp phình to và tăng chi phí ghi/backfill.

**Không cộng trực tiếp VND và USD.** Không cộng các số **COUNT(DISTINCT customer_id)** của từng ngày để suy ra khách duy nhất cả tháng. Nếu hệ thống cần số liệu nhiều chiều trên lịch sử rất lớn, dùng kho phân tích, fact/dimension hoặc pre-aggregation đúng grain có thể phù hợp hơn việc thêm vô hạn cột tổng vào bảng giao dịch.

## 8. Kiểm soát bản sao trong hệ quan hệ, document, đồ thị và phân tích

### 8.1. Quan hệ: ít JOIN không phải thước đo duy nhất

Trong relational model, nguồn chuẩn có thể được mô hình hóa rõ bằng **PK, FK, UNIQUE, CHECK** và các bảng theo phụ thuộc nghiệp vụ. Phi chuẩn hóa tạo thêm cột/bảng dẫn xuất để đáp ứng workload cụ thể.

Giới hạn cần kiểm tra: bộ lọc đã có chỉ mục tốt chưa; bản sao có ràng buộc cục bộ gì; ai cập nhật khi nguồn INSERT/UPDATE/DELETE; có truy vấn đối soát; có thể bỏ bản sao để quay lại JOIN hay không.

Một **CHECK** trên hàng dẫn xuất không tự chứng minh giá trị bằng nguồn bảng khác. Khóa ngoại bảo đảm quan hệ tham chiếu nhưng **không tự đồng bộ tên hay số tổng**. Vì vậy, số lượng ràng buộc SQL nhiều chưa chắc bằng quản trị dữ liệu đúng.

### 8.2. Document: nhúng đúng ranh giới aggregate, cảnh giác document phình to

Nhúng dòng hàng cùng đơn hàng có thể hợp lý nếu chúng được đọc/chốt cùng một sự kiện. Nhúng **tên tác giả hiện hành** vào hàng triệu document bài viết tạo fan-out khi đổi tên và rủi ro sai sau khi quyền hiển thị thay đổi.

Cần xem giới hạn kích thước document, mức tăng danh sách con, khả năng cập nhật nguyên tử của hệ quản trị, phân bố fan-out và cách tái dựng. Nếu **comments** tăng không giới hạn, nhúng tất cả comment vào một document bài viết có thể làm việc đọc/ghi tệ hơn, dù ban đầu giảm JOIN.

### 8.3. Đồ thị: sao chép thuộc tính hay số cạnh đều có giá

Trong graph database, **Product – BELONGS_TO – Category** lưu quan hệ; một truy vấn traversal có thể đọc tên từ đỉnh Category. Sao chép tên sang mỗi đỉnh Product chỉ đáng làm nếu workload chứng minh lợi ích đáng kể và có cách cập nhật fan-out. Tương tự, **friend_count** trên đỉnh người dùng là giá trị dẫn xuất từ các cạnh, cần xử lý thêm/xóa cạnh và đỉnh bậc cao.

### 8.4. Analytics: mô hình đọc riêng nhưng lineage vẫn phải đi được về nguồn

Trong hệ phân tích, một fact table và dimension có thể được tổ chức khác OLTP để phục vụ quét và tổng hợp. Materialized view và bảng tổng hợp là công cụ hợp lệ, nhưng phải biết **grain, kỳ dữ liệu, timezone, loại tiền, valid time, dimension đổi theo thời gian và phép sửa dữ liệu đến muộn**.

Một dashboard dùng cùng từ **revenue** cho “tiền đã thu” và “giá trị đơn đã đặt” là khó giải thích dù có thể tính cực nhanh. Với dữ liệu phân tích, **sự rõ nghĩa của công thức** quan trọng ngang với hiệu năng.

## 9. Đối soát: phát hiện lệch, thiếu, dư và ghi lùi

Với **product_cards** nằm trong cùng PostgreSQL để dễ minh họa, có thể phân loại sai lệch giữa các trường danh mục:

~~~sql
SELECT
    p.product_id,
    p.category_id AS source_category_id,
    pc.category_id AS copied_category_id,
    c.display_version AS source_version,
    pc.category_display_version AS copied_version,
    CASE
        WHEN pc.product_id IS NULL
            THEN 'MISSING_PROJECTION'
        WHEN pc.category_id IS DISTINCT FROM p.category_id
            THEN 'RELATION_MISMATCH'
        WHEN pc.category_display_version > c.display_version
            THEN 'VERSION_AHEAD'
        WHEN pc.category_display_version < c.display_version
            THEN 'LAGGING'
        WHEN pc.category_name_display IS DISTINCT FROM c.display_name
            THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS sync_state
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
LEFT JOIN product_cards AS pc
    ON pc.product_id = p.product_id;
~~~

**MISSING_PROJECTION**: nguồn có sản phẩm nhưng card chưa có. **RELATION_MISMATCH**: card còn liên kết danh mục khác. **LAGGING**: version danh mục của card cũ hơn; có thể hợp lệ trong cửa sổ bất đồng bộ. **VALUE_MISMATCH**: card đã ở cùng version nhưng tên khác nguồn; thường cần điều tra mapping, sửa thủ công hoặc sự kiện lỗi.

Đây là ví dụ **đối soát phần danh mục**, chưa kiểm tra **product_name, price, currency, is_active** hay các card **mồ côi** không còn sản phẩm nguồn. Đối soát tổng thể phải bao gồm các trường mà hợp đồng yêu cầu, cách xử lý xóa và các trường hợp bản ghi chỉ xuất hiện ở projection. Với hai database khác nhau, không thể mặc định chạy JOIN trực tiếp; cần cơ chế đối chiếu có mốc dữ liệu chung.

**Quan trọng:** nếu eventual consistency cho phép chậm 30 giây, version thấp hơn nguồn **chưa đủ** kết luận vi phạm. Muốn xác định quá hạn cần thời gian nguồn commit, mốc xử lý event/checkpoint, tuổi bản sao và đo đến nơi người đọc thật sự truy cập. So hai snapshot không cùng thời điểm có thể tạo chênh lệch tạm thời dù hệ thống hoạt động đúng.

### 9.1. Tái dựng phải từ nguồn, không từ bản sao bị nghi sai

Khi thấy một tên danh mục trong search document sai, không nên tự copy từ **product_cards** sang search index nếu product_cards cũng là bản sao có thể sai. Cần lần về **categories** hoặc sự kiện snapshot được xác thực, rồi tái dựng theo pipeline có lineage rõ.

Một quy trình backfill an toàn phải:

1. Chọn một mốc snapshot/checkpoint đáng tin.
2. Nạp dữ liệu nguồn và phiên bản của từng thực thể.
3. Bắt kịp những thay đổi phát sinh trong lúc nạp.
4. Không cho bản snapshot cũ ghi đè dữ liệu projection mới hơn.
5. Đối soát số bản ghi, nội dung, phiên bản và các trường hợp xóa.
6. Chuyển đường đọc dần, có phương án quay về nguồn khi lỗi.

Chỉ tăng version ở một bảng mà không biết event đang nằm ở đâu **không đủ** để chứng minh không mất cập nhật. Với nhiều thực thể nguồn tham gia một card, còn phải xử lý thứ tự chồng chéo giữa các luồng thay đổi sản phẩm và danh mục.

## 10. Giới hạn dư thừa bằng kỷ luật triển khai và sở hữu

Một projection có thể được xây dựng ban đầu bởi một người; chi phí bảo trì tồn tại lâu hơn người ấy. Cần quy định:

| Vai trò | Trách nhiệm |
| --- | --- |
| **Chủ sở hữu nghiệp vụ** | Quy định ngữ nghĩa tên, giá, trạng thái, công thức báo cáo và dữ liệu nào phải là lịch sử |
| **Chủ sở hữu nguồn** | Bảo vệ quyền ghi, phát thay đổi từ mọi đường ghi, version và hợp đồng sự kiện |
| **Chủ sở hữu projection** | Định nghĩa field tối thiểu, xử lý retry/sai thứ tự, kiểm soát cập nhật và khả năng tái dựng |
| **Chủ sở hữu API đọc** | Dùng projection trong đúng phạm vi, có fallback/nhãn độ tươi khi cần |
| **Vận hành/đảm bảo dữ liệu** | Giám sát lag, mismatch, backlog, runbook, rebuild và báo cáo sự cố |
| **Bảo mật/quyền riêng tư** | Kiểm soát quyền truy cập, retention, xóa/ẩn bản sao và dữ liệu trong log/event |

Một lỗi thường gặp là **chủ nguồn thay đổi ý nghĩa trường** (ví dụ định nghĩa “đánh giá hợp lệ”) nhưng không thông báo cho projection. Nếu schema không đổi, consumer vẫn chạy và báo cáo trông bình thường, song số liệu sai. Do đó, hợp đồng cần có **phiên bản phép biến đổi/công thức**, quy trình thông báo và khả năng tính lại lịch sử.

### 10.1. Review trước khi thêm một cột dẫn xuất

Mẫu câu hỏi ngắn:

- **Vì sao?** Use case nào, SLO nào đang không đạt, baseline đo lúc nào?
- **Cái gì?** Field, ngữ nghĩa, grain và dữ liệu nguồn nào?
- **Ở đâu?** Bao nhiêu bản sao, có mô hình đọc hiện có dùng lại được không?
- **Ai?** Chủ nguồn, chủ projection, người xử lý sự cố là ai?
- **Khi nào?** Đồng bộ sau commit hay eventual; độ trễ cho phép bao lâu?
- **Nếu đổi?** Xử lý tạo, sửa, xóa, đổi quan hệ, nhập liệu và sửa hồi tố ra sao?
- **Nếu sai?** Đối soát, khôi phục, rollback và rebuild thế nào?
- **Nếu không cần nữa?** Dấu hiệu, phép đo và kế hoạch gỡ bỏ?

Thiếu thông tin về nguồn chuẩn hoặc xử lý sai lệch là **lý do dừng thiết kế để làm rõ**, không phải chi tiết có thể bỏ qua sau khi deploy.

## 11. So sánh phương án bằng chi phí tổng thể

Giả sử một màn hình danh sách sản phẩm có mục tiêu **p95 không quá 150 ms**. Các con số sau **hoàn toàn giả định** để minh họa cách quyết định; không phải kết quả đo trên hệ thống thật.

| Chỉ số | JOIN tối ưu từ nguồn | Sao chép category_name vào products | Read model product_cards |
| --- | ---: | ---: | ---: |
| API danh sách p95 | 118 ms | 111 ms | 96 ms |
| Tăng tốc so với JOIN | Mốc so sánh | 7 ms | 22 ms |
| SLO p95 ≤ 150 ms | Đạt | Đạt | Đạt |
| Khi đổi tên danh mục | Cập nhật một hàng nguồn | Ghi nhiều sản phẩm | Cập nhật các card hoặc rebuild |
| Rủi ro fan-out | Thấp khi lookup theo PK | Cao nếu danh mục rất lớn | Cao trong pipeline nếu nhúng vào mọi card |
| Chi phí giữ nhất quán | Truy vấn JOIN | Mọi đường ghi + transaction/trigger | Consumer/queue/version/lag/đối soát |
| Độ đúng | Nguồn tại thời điểm đọc | Chỉ đúng nếu đồng bộ mạnh đủ các đường | Tùy độ tươi hợp đồng |
| Phương án đề xuất trong ví dụ | **Giữ** | Không cần thêm | Chưa có lý do đủ mạnh nếu chỉ phục vụ API này |

Trong giả định, **JOIN đã đạt SLO**, nên thêm bản sao chưa được biện minh bằng nhu cầu của màn hình này. Một khác biệt nhỏ vài mili giây còn phải xem độ biến động giữa các lượt đo, tải ghi và chi phí vận hành.

Tuy nhiên, nếu một **search engine ở kho riêng** phải trả dữ liệu thẻ mà không có khả năng JOIN trực tiếp tới database nguồn, read model có thể là thành phần cần thiết về mặt kiến trúc dù JOIN trong PostgreSQL nhanh. Khi đó hãy lập **hợp đồng khác** cho search document: access pattern, độ tươi, phạm vi field, phiên bản, quyền truy cập và phép đối soát; không dùng bảng so sánh trên để bác bỏ mọi mô hình đọc.

### 11.1. Đo cả đường ghi và khả năng phục hồi

Một quyết định nên xét:

- **Đọc:** p50/p95/p99 API, throughput, số query/request, CPU và I/O.
- **Ghi:** INSERT/UPDATE/DELETE p95/p99, lock waits, WAL, số hàng hoặc document bị sửa mỗi thay đổi nguồn.
- **Tính đúng:** bản ghi trễ quá hạn, mismatch ở cùng phiên bản, bản ghi thiếu/dư, sai quy tắc nghiệp vụ.
- **Vận hành:** độ tuổi event chưa phát, backlog, thời gian refresh, rebuild, triển khai schema mới.
- **Tăng trưởng:** khi lượng sản phẩm, số đánh giá, số tenant, số ngôn ngữ và fan-out tăng.
- **Dữ liệu nhạy cảm:** các nơi sao chép, quyền đọc và chi phí xóa/ẩn khi nguồn bị thu hồi.

Nếu không đo đường ghi, một bản sao giúp đọc nhanh có thể biến thành nút nghẽn khi đồng loạt đổi tên, cập nhật giá hoặc có sự kiện rất phổ biến.

## 12. Cách thu hẹp hoặc gỡ bỏ dư thừa đã có

Trong hệ thống lâu năm, bản sao thường được thêm vào qua nhiều đợt tối ưu. Cần một quy trình rút gọn thay vì xóa ngẫu nhiên:

1. **Lập bản đồ dòng dữ liệu:** liệt kê nguồn, projection, cache, search index, bảng tổng hợp và người dùng của từng bản sao.
2. **Đánh dấu loại dữ liệu:** sự thật hiện hành, snapshot lịch sử hay dẫn xuất. Không xóa lịch sử cần bảo toàn chỉ vì nó giống dữ liệu nguồn hôm nay.
3. **Tìm tất cả đường đọc/ghi phụ thuộc:** API, batch, báo cáo, truy vấn ad hoc và hệ thống ngoài.
4. **Đo lại workload thật:** có thể JOIN/chỉ mục/cache chung đã đáp ứng SLO mà không cần bản sao đặc thù không?
5. **Chuyển đọc theo từng nhóm:** thử đường chuẩn hóa hoặc projection hợp nhất, so kết quả trong phạm vi nghiệp vụ tương ứng.
6. **Ngừng người ghi thừa trước khi xóa cấu trúc:** bảo đảm không còn tiến trình làm mới hoặc dashboard dùng bản sao.
7. **Gỡ bỏ sau xác minh:** theo kế hoạch migration có rollback, theo dõi lỗi và tải nguồn.

Việc hợp nhất các bảng tổng hợp cần đặc biệt thận trọng với **grain**. Hai bảng có tên gần giống nhưng một bảng theo ngày thanh toán và một bảng theo ngày đặt đơn không thể gộp chỉ vì cùng có trường **total_amount**.

### 12.1. Chú ý schema evolution và đa ngôn ngữ

Nếu tên danh mục được dịch theo **locale**, một cột **category_name_display** không có locale dễ sai khi thẻ được trả bằng nhiều ngôn ngữ. Có thể cần mô hình theo **(category_id, locale)** hoặc tạo projection theo locale có giới hạn. **Mỗi ngôn ngữ mới** có thể làm số bản sao và fan-out tăng, nên đây là phần của ngân sách dư thừa ngay từ đầu.

Khi đổi định nghĩa công thức (ví dụ đánh giá bị ẩn không còn tính vào rating), hãy gắn version của phép biến đổi, chuẩn bị backfill và đối soát. Một consumer chạy thành công với payload hợp lệ **không chứng minh** số liệu còn đúng theo quy tắc nghiệp vụ mới.

### 12.2. Đừng nhân bản thông tin cá nhân nếu màn hình không cần

Thông tin người dùng như địa chỉ, email hoặc ảnh đại diện có thể thay đổi quyền công khai hoặc bị yêu cầu xóa theo chính sách. Nếu được sao chép vào nhiều read model, tất cả bản sao, cache, log và dữ liệu phân tích phải đáp ứng quyền truy cập và thời hạn lưu phù hợp.

Có trường hợp chỉ cần lưu **user_id** và lấy thông tin đã được phân quyền khi đọc. Đó có thể là lựa chọn an toàn và dễ duy trì hơn việc nhúng toàn bộ hồ sơ vào mọi document.

## 13. Bài tập tình huống

### Bài 1 — Ba nơi cùng giữ tên danh mục

Bảng **products** vừa có **category_id**, vừa có **category_name**; bảng **product_cards** lại giữ **category_name**; search index cũng giữ tên. Trang danh sách PostgreSQL với JOIN đã có p95 = 105 ms, SLO = 180 ms. Khi đổi tên một danh mục, nhóm phải cập nhật 450.000 sản phẩm.

**Câu hỏi:** Đâu là vấn đề chính? Hãy đề xuất ranh giới dư thừa tối thiểu.

### Bài 2 — Điểm trung bình luôn lệch một ít

Một bảng **product_rating_stats** lưu **visible_review_count**, **visible_rating_sum** và **average_rating**. Khi ẩn review, code trừ count và sum nhưng quên tính lại average.

**Câu hỏi:** Nếu giao diện không cần lọc/sắp xếp theo average, nên lưu những trường nào? Điều gì phải xảy ra khi review đổi điểm?

### Bài 3 — Người mới không biết sửa trường nào

Trong bảng **orders** có **total_amount**, bảng **customer_orders** cũng có **total_amount**, dashboard có **order_total**. Không tài liệu nào nói tổng gồm thuế và giảm giá hay chưa, hoặc tính tại thời điểm nào.

**Câu hỏi:** Trước khi thay lược đồ, cần xác minh và ghi lại những định nghĩa nào?

### Bài 4 — Snapshot bị coi là cache

Bản ghi **order_items.product_name_at_confirmation** giữ tên đã chốt trong đơn một năm trước. Một job mới phát hiện tên này khác **products.product_name** và “sửa” về tên hiện tại.

**Câu hỏi:** Đây có phải một trường hợp dư thừa cần dọn bỏ không?

### Bài 5 — Chuyển danh mục trùng lúc đổi tên

Sản phẩm P đang ở danh mục A, sau đó chuyển sang B. Event đổi tên A đến trễ. Consumer chỉ kiểm tra **event_version** của A trước khi ghi **product_cards.category_name_display**.

**Câu hỏi:** Còn thiếu điều kiện nào để không gắn tên A lên sản phẩm đã chuyển sang B? Khi event sản phẩm và danh mục đến sai thứ tự, cần thiết kế thêm gì?

### Bài 6 — Một bản sao có thể không cần nữa

Một projection được tạo vì dashboard trước đây chậm 3 giây. Sau khi chuyển báo cáo sang kho phân tích, không còn API nào dùng projection; nhưng worker refresh mỗi phút vẫn chạy, chiếm CPU và ghi liên tục.

**Câu hỏi:** Nhóm nên kiểm tra và thực hiện những bước gì trước khi xóa projection?

### Gợi ý lời giải

1. Mô hình tạo nhiều bản sao không có lợi ích đo được tương xứng; JOIN đã đạt SLO nhưng đổi tên gây fan-out cao. Giữ **categories.display_name** là nguồn chuẩn, **products.category_id** là quan hệ; chỉ giữ read model/search document thật sự cần thiết theo access pattern khác và có hợp đồng, đối soát.
2. Có thể chỉ lưu **visible_review_count** và **visible_rating_sum**, tính trung bình lúc đọc bằng phép chia có xử lý count = 0. Khi review đổi điểm từ x sang y, nếu vẫn hiển thị, sum thay đổi **y − x** và count giữ nguyên; khi ẩn review, trừ cả count và điểm cũ một lần, có xử lý retry.
3. Phải chốt **ngữ nghĩa tiền**, grain, loại tiền, thời điểm, thuế, giảm giá, vận chuyển, hoàn tiền, nguồn chuẩn, công thức, trạng thái, vai trò của snapshot/bản sao và ai sở hữu. Sau đó mới xác định nơi nào có thể bỏ hoặc hợp nhất.
4. **Không.** Đây là ảnh chụp lịch sử tại xác nhận đơn; nó không cần bằng tên sản phẩm hôm nay. Job đang dùng sai bất biến và có thể viết lại lịch sử. Chỉ sửa nếu có quy trình hiệu chỉnh giao dịch có dấu vết theo chính sách.
5. Phải kiểm tra **category_id hiện tại của card** khớp ID của event và version danh mục tăng. Đồng thời cần quản lý **product_version**, thứ tự xử lý chuyển quan hệ, và có thể làm mới từ snapshot nguồn nhất quán khi sự kiện chồng chéo.
6. Xác minh **mọi consumer và phụ thuộc**, hợp đồng báo cáo đã thay thế, SLO của đường đọc mới, dữ liệu đã lưu và chính sách retention. Ngừng chuyển đọc, theo dõi, ngừng worker ghi, kiểm tra khả năng rollback rồi mới gỡ projection/schema theo kế hoạch.

## 14. Ghi nhớ

**Giới hạn dư thừa là giới hạn số sự thật phải duy trì đồng thời, không chỉ là giảm số cột.** Một bản sao tốt có mục đích đọc cụ thể, nguồn chuẩn, lineage, phiên bản/độ tươi, quyền ghi rõ ràng và đường đối soát, phục hồi.

**Mô hình dễ giải thích** cho biết vì sao từng field tồn tại, mang nghĩa ở thời điểm nào và thuộc trách nhiệm ai. **Mô hình dễ bảo trì** cho phép thêm tính năng, thay đổi công thức, cập nhật schema hoặc bỏ một projection mà không phải đoán những nơi có thể bị ảnh hưởng.

Trước khi thêm một bản sao, hãy hỏi: **“Nếu ngày mai thuộc tính nguồn đổi, những nơi nào phải đổi theo, ai đảm bảo chúng đúng, chi phí là bao nhiêu, và nếu bỏ bản sao này hệ thống có vẫn đáp ứng nhu cầu không?”**. Khi trả lời được bằng hợp đồng và phép đo, phi chuẩn hóa mới là một lựa chọn có kiểm soát.
