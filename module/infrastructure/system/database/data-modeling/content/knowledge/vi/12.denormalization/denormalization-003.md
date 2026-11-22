# Sao chép thuộc tính hiển thị để giảm phép nối

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận ra khi nào nên xem xét sao chép một thuộc tính **chỉ để hiển thị** như tên danh mục, tên tác giả, nhãn trạng thái hoặc ảnh đại diện sang cấu trúc đọc.
- Phân biệt thuộc tính hiển thị **hiện hành** với bản chụp **tại thời điểm giao dịch**, vì hai loại có quy tắc cập nhật khác nhau.
- Đo lợi ích thực tế của việc bỏ một phép nối (JOIN) so với chi phí duy trì bản sao trên đường ghi.
- Chọn chiến lược đồng bộ phù hợp: cùng giao dịch, trigger, sự kiện bất đồng bộ hoặc tạo riêng mô hình đọc.
- Thiết kế nguồn chuẩn, cơ chế cập nhật, đối soát, backfill và giám sát để bản sao có thể kiểm chứng.

Trong chương **Phi chuẩn hóa** của **DATABASE_DATA_MODELING**, mục tiêu không chỉ là tạo một truy vấn nhanh. Mục tiêu là chuyển yêu cầu nghiệp vụ thành mô hình rõ ràng về thực thể, quan hệ, ràng buộc và lược đồ vật lý; biết khi nào mô hình quan hệ, document, đồ thị hoặc phân tích có thể phục vụ tốt mẫu truy cập mà vẫn dễ thay đổi và kiểm chứng.

## 1. Tình huống: trang sản phẩm cần tên danh mục

Giả sử trang thương mại điện tử hiển thị 40 thẻ sản phẩm. Mỗi thẻ gồm:

- Mã và tên sản phẩm.
- Giá đang hiển thị, ảnh đại diện.
- Tên danh mục như “Văn phòng phẩm”.
- Một số nhãn khác như “Mới”, “Bán chạy”.

Trong mô hình quan hệ chuẩn hóa, sản phẩm lưu **category_id** và tên danh mục nằm tại **categories.display_name**. Khi dựng thẻ, truy vấn nối **products** với **categories**:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.display_price,
    c.display_name AS category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.is_active = TRUE
ORDER BY p.created_at DESC, p.product_id DESC
LIMIT 40;
~~~

Một đề xuất thường gặp là thêm **products.category_name_display** để bỏ JOIN:

~~~sql
SELECT
    product_id,
    product_name,
    display_price,
    category_name_display AS category_name
FROM products
WHERE is_active = TRUE
ORDER BY created_at DESC, product_id DESC
LIMIT 40;
~~~

Truy vấn thứ hai nhìn đơn giản hơn. Tuy nhiên, **bỏ JOIN không tự động có nghĩa là hệ thống nhanh hơn đáng kể**. Nếu chỉ lấy 40 hàng sản phẩm và mỗi hàng nối một danh mục qua khóa chính đã đánh chỉ mục, JOIN có thể rất rẻ. Trong khi đó, sao chép tên danh mục khiến mọi lần đổi tên phải cập nhật toàn bộ sản phẩm liên quan, hoặc chấp nhận kết quả hiển thị cũ.

Vì vậy, câu hỏi thiết kế là:

> Việc giảm chi phí đọc có đủ lớn và đủ thường xuyên để bù chi phí đồng bộ, lưu trữ và rủi ro dữ liệu cũ không?

## 2. Từ nhu cầu hiển thị đến hợp đồng dữ liệu

Một **thuộc tính hiển thị được sao chép** (duplicated display attribute) là giá trị lấy từ một thực thể nhưng được giữ thêm tại nơi phục vụ việc đọc thực thể khác. Ví dụ:

| Thuộc tính nguồn | Bản sao dùng khi hiển thị | Mục đích |
| --- | --- | --- |
| **categories.display_name** | **products.category_name_display** | Hiển thị thẻ sản phẩm không cần nối danh mục |
| **authors.public_name** | **article_cards.author_name_display** | Hiển thị danh sách bài viết |
| **brands.logo_url** | **product_cards.brand_logo_url** | Dựng thẻ sản phẩm từ một mô hình đọc |
| **stores.display_name** | **search_documents.store_name** | Tìm kiếm, lọc, sắp xếp theo thông tin cửa hàng |
| **users.avatar_url** | **comment_cards.author_avatar_url** | Trả về thông tin tác giả cùng danh sách bình luận |

Danh sách này chỉ minh họa kiểu dữ liệu; không có nghĩa mọi thuộc tính trên đều nên sao chép. **Logo, avatar, tên người dùng, thông tin riêng tư và thuộc tính dùng để ra quyết định nghiệp vụ** có mức rủi ro cập nhật, quyền truy cập và thu hồi khác nhau.

Trước khi thêm cột, cần xác định bốn điều:

1. **Nguồn chuẩn:** trường nào là nơi định nghĩa giá trị đúng? Với tên danh mục hiện hành, đó có thể là **categories.display_name**.
2. **Ngữ nghĩa:** bản sao là giá trị hiện hành, giá trị được làm mới định kỳ, hay snapshot tại một sự kiện?
3. **Cửa sổ nhất quán:** khi đổi tên, bản sao phải đúng ngay sau giao dịch hay được phép trễ vài giây/phút?
4. **Khả năng kiểm chứng:** đo được bao nhiêu bản sao lỗi thời, sai giá trị hoặc chưa được tái tạo hay không?

Nếu nhóm chưa thống nhất những điều này, việc thêm cột sẽ tạo **dư thừa chưa được kiểm soát**, dù câu SQL đọc ngắn hơn.

### 2.1. Phân biệt dữ liệu hiển thị hiện hành và lịch sử

Hãy so sánh:

- **products.category_name_display**: nếu có ý nghĩa “tên danh mục hiện nay”, khi **categories.display_name** đổi thì bản sao **phải đổi theo** trong thời gian đã cam kết.
- **order_items.product_name_at_purchase**: nếu có ý nghĩa “tên sản phẩm được xác nhận khi mua”, khi **products.product_name** đổi thì tên trên đơn cũ **phải giữ nguyên**.
- **article_cards.author_name_display**: có thể là tên hiện hành của tác giả hoặc tên tại lúc xuất bản; phải xác định một nghĩa trước khi thiết kế đồng bộ.

Hai trường có cùng chuỗi ký tự không nhất thiết đại diện cho cùng một sự thật nghiệp vụ. Đánh giá chất lượng mô hình phải dựa vào **ý nghĩa và vòng đời dữ liệu**, không chỉ vào số lần một giá trị xuất hiện.

## 3. Mô hình chuẩn hóa làm điểm xuất phát

Một lược đồ PostgreSQL đơn giản:

~~~sql
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    display_version BIGINT NOT NULL DEFAULT 1
        CHECK (display_version >= 1)
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES categories(category_id),
    product_name TEXT NOT NULL,
    display_price NUMERIC(14, 2) NOT NULL
        CHECK (display_price >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_active_created
    ON products (is_active, created_at DESC, product_id DESC);
~~~

**categories** lưu tên danh mục hiện hành. **products.category_id** là quan hệ nhiều sản phẩm thuộc một danh mục. **display_version** là phiên bản tăng khi thuộc tính hiển thị của danh mục đổi; nó hữu ích nếu sau này cần mô hình đọc được cập nhật theo sự kiện.

Trong PostgreSQL, khóa chính tự có chỉ mục phù hợp để tra cứu **categories.category_id**. Khóa ngoại trên **products.category_id** không tự động tạo chỉ mục ở phía tham chiếu; nếu workload thường lọc, cập nhật hàng loạt hoặc JOIN theo trường đó, hãy đo và cân nhắc một chỉ mục riêng. Không nên tạo hàng loạt chỉ mục chỉ vì thấy cột xuất hiện trong JOIN.

Ví dụ một ứng viên truy vấn chọn trước sản phẩm rồi nối danh mục:

~~~sql
WITH recent_products AS (
    SELECT
        product_id,
        product_name,
        display_price,
        category_id,
        created_at
    FROM products
    WHERE is_active = TRUE
    ORDER BY created_at DESC, product_id DESC
    LIMIT 40
)
SELECT
    p.product_id,
    p.product_name,
    p.display_price,
    c.display_name AS category_name
FROM recent_products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
ORDER BY p.created_at DESC, p.product_id DESC;
~~~

Truy vấn này giới hạn về 40 sản phẩm trước khi JOIN. Bộ tối ưu có thể chọn cách thực thi phù hợp; cần dùng **EXPLAIN (ANALYZE, BUFFERS)** và quan sát dữ liệu thật để đánh giá, thay vì suy đoán từ hình thức câu SQL.

Lưu ý: truy vấn sử dụng **INNER JOIN** vì khóa ngoại **category_id** bắt buộc tham chiếu một danh mục hợp lệ trong phạm vi mô hình. Nếu ứng dụng cho phép sản phẩm chưa được phân loại, cách xử lý NULL và loại JOIN phải được thiết kế lại.

## 4. Khi nào bản sao tên danh mục có khả năng hữu ích?

Việc sao chép một thuộc tính nhỏ chỉ tạo lợi ích rõ khi phù hợp với cách dữ liệu được phục vụ. Một số bối cảnh:

- **Danh sách đọc cực kỳ thường xuyên:** một API trả hàng trăm thẻ, phục vụ lưu lượng cao; sau tối ưu chỉ mục và truy vấn, chi phí nối/tra cứu liên quan vẫn là một nút thắt đo được.
- **Mô hình đọc ở kho khác:** search index hoặc bảng projection cần trả về trọn thông tin hiển thị mà không thể JOIN trực tiếp với database giao dịch.
- **Dữ liệu đã được gom theo aggregate/document:** ứng dụng thường đọc cùng một tập thuộc tính và cơ chế cập nhật cho phép duy trì chúng trong cùng phạm vi.
- **API hợp nhất nhiều nguồn:** nếu việc dựng màn hình đòi nhiều cuộc gọi từ các dịch vụ khác nhau, mô hình đọc đã tổng hợp có thể giảm độ trễ mạng và số lần gọi.
- **Truy vấn phân tích:** tên hoặc nhãn được lưu theo ngữ cảnh báo cáo, có mốc dữ liệu và lịch sử hiệu lực rõ ràng.

Ngược lại, với danh mục có vài chục/hàng trăm hàng và màn hình chỉ lấy 40 sản phẩm, JOIN theo khóa chính có thể quá rẻ để việc nhân bản mang lại lợi ích đáng kể.

**Không nên dùng giá trị hiển thị được sao chép làm nguồn quyết định nghiệp vụ** khi yêu cầu giá trị hiện hành tuyệt đối. Ví dụ, tên danh mục có thể chậm vài giây trên trang tìm kiếm, nhưng giá tính tiền, quyền truy cập, trạng thái tài khoản hoặc tồn kho khi xác nhận giao dịch phải theo quy tắc nguồn và nhất quán phù hợp.

## 5. Phương án A: sao chép ngay trong bảng quan hệ

Giả sử số liệu thực tế chứng minh cần giảm truy vấn nối, và đội vận hành chọn cập nhật đồng bộ. Ta có thể mở rộng lược đồ:

~~~sql
ALTER TABLE products
ADD COLUMN category_name_display TEXT;
~~~

Cần làm rõ: đây là **cột dẫn xuất phục vụ đọc**, không được người quản trị chỉnh độc lập với **categories.display_name**.

### 5.1. Thay tên danh mục trong cùng giao dịch

Ở mức minh họa, một thao tác đổi tên cập nhật cả hai nơi:

~~~sql
BEGIN;

UPDATE categories
SET display_name = 'Dụng cụ học tập',
    display_version = display_version + 1
WHERE category_id = 10;

UPDATE products
SET category_name_display = 'Dụng cụ học tập'
WHERE category_id = 10;

COMMIT;
~~~

Vì cùng một transaction trong PostgreSQL, nếu một câu lệnh lỗi và transaction được rollback, cả phần nguồn và bản sao cùng được hoàn tác. Sau commit, người đọc mới theo quy tắc MVCC thích hợp sẽ quan sát trạng thái đã cập nhật.

Nhưng chỉ có đoạn mã trên **chưa bảo đảm tất cả bản sao luôn đúng**: hệ thống còn thao tác tạo sản phẩm, chuyển sản phẩm sang danh mục khác, import hàng loạt, sửa trực tiếp từ công cụ quản trị và nhiều luồng xử lý cùng lúc. Tất cả cần tuân thủ một giao thức.

### 5.2. Kiểm soát tương tranh khi tạo sản phẩm

Một lỗi dễ bỏ sót:

1. Giao dịch A đổi tên danh mục.
2. Giao dịch B đồng thời tạo sản phẩm và đọc tên cũ.
3. Giao dịch A cập nhật những sản phẩm đang có rồi commit.
4. Sản phẩm B xuất hiện với tên danh mục cũ.

Có thể phối hợp quyền khóa trên hàng danh mục để tránh lỗ hổng này. Ví dụ, đường **tạo sản phẩm** đọc và giữ khóa **FOR SHARE** trên danh mục trong cùng transaction, còn đường **đổi tên** cập nhật hàng danh mục nên phải chờ theo quy tắc khóa hàng của PostgreSQL:

~~~sql
BEGIN;

WITH selected_category AS MATERIALIZED (
    SELECT category_id, display_name
    FROM categories
    WHERE category_id = 10
    FOR SHARE
)
INSERT INTO products (
    product_id,
    category_id,
    product_name,
    display_price,
    category_name_display
)
SELECT
    501,
    category_id,
    'Bút chì HB',
    12000.00,
    display_name
FROM selected_category;

COMMIT;
~~~

Đây là mẫu minh họa cho thao tác **INSERT** trên PostgreSQL ở mức cô lập **READ COMMITTED**. Đường **đổi category_id** của sản phẩm cũng phải đọc và khóa danh mục đích theo quy tắc tương ứng. Cần thống nhất thứ tự lấy khóa, xử lý deadlock/retry và bảo đảm các đường ghi không tự ý bỏ qua giao thức.

Trong thực tế, dùng một stored procedure/trigger được kiểm thử, hoặc một dịch vụ duy nhất quản lý mọi đường ghi, có thể dễ kiểm soát hơn việc yêu cầu từng API tự nhớ các bước. **Khóa ngoại chỉ bảo đảm danh mục tồn tại, không tự đồng bộ tên được nhân bản.** Cũng không nên kết luận một giao dịch là đủ nếu vẫn có tác nhân khác ghi ngoài giao thức.

### 5.3. Chi phí của việc đổi tên

Nếu một danh mục có rất nhiều sản phẩm, câu **UPDATE products** có thể chạm lượng lớn hàng, tạo WAL, phát sinh khóa, tăng I/O và làm chậm ghi. Một tên danh mục rất ít thay đổi vẫn có thể tạo một đợt ghi lớn mỗi khi thay đổi.

Có thể hình dung:

> **Fan-out cập nhật = số bản ghi đích bị ảnh hưởng bởi một thay đổi ở nguồn.**

Fan-out là yếu tố quan trọng khi so sánh: JOIN đọc 40 hàng theo khóa chính có thể rẻ, trong khi một lần đổi tên kéo theo cập nhật hàng triệu sản phẩm là rất đắt. Nếu muốn tính nhất quán tức thời mà fan-out quá lớn, cần cân nhắc giữ JOIN hoặc thay đổi cấu trúc đọc.

## 6. Phương án B: mô hình đọc riêng, đồng bộ bất đồng bộ

Giả sử trang tìm kiếm dùng một kho đọc riêng (**product_cards**, search index hoặc document store). Mỗi bản ghi chứa đủ dữ liệu để dựng một thẻ sản phẩm:

~~~text
product_cards
├── product_id
├── product_name
├── display_price
├── category_id
├── category_name_display
├── category_display_version
└── projection_updated_at
~~~

**products** và **categories** vẫn là nguồn nghiệp vụ trong database giao dịch. **product_cards** là projection có thể dựng lại.

Lúc tạo/sửa sản phẩm, projection được tạo theo dữ liệu nguồn. Khi đổi tên danh mục, hệ thống phát một sự kiện có nội dung tương tự:

~~~json
{
  "eventType": "CategoryDisplayNameChanged",
  "categoryId": 10,
  "displayName": "Dụng cụ học tập",
  "displayVersion": 14
}
~~~

Dịch vụ xử lý sự kiện có thể áp dụng quy tắc:

1. Chỉ cập nhật những bản ghi còn thuộc **categoryId** của sự kiện.
2. Chỉ nhận phiên bản mới hơn **category_display_version** đã lưu.
3. Xử lý sự kiện lặp lại mà không thay đổi kết quả đã đúng (idempotent).
4. Ghi lại tiến độ, lỗi, lần thử lại và độ tuổi của bản sao.
5. Có thể phát lại hoặc tái dựng projection từ nguồn chuẩn.

Ví dụ minh họa một lần áp dụng sự kiện vào projection PostgreSQL:

~~~sql
UPDATE product_cards
SET category_name_display = 'Dụng cụ học tập',
    category_display_version = 14,
    projection_updated_at = CURRENT_TIMESTAMP
WHERE category_id = 10
  AND category_display_version < 14;
~~~

Trong ví dụ, **display_version** của danh mục phải tăng đơn điệu mỗi lần tên hiển thị thay đổi. Khi sản phẩm được chuyển sang danh mục khác, projection cũng phải thay **category_id**, tên và phiên bản cùng nhau; điều kiện **WHERE category_id = 10** ngăn sự kiện của danh mục cũ đổi tên cho sản phẩm đã chuyển đi. Để xử lý thay đổi chồng chéo ở cùng một sản phẩm, cần thêm quy tắc về phiên bản sự kiện sản phẩm và thứ tự giữa các luồng sự kiện.

**Bảo đảm phát sự kiện:** nếu sửa DB thành công nhưng gửi sự kiện thất bại, projection có thể cũ mãi. Có thể dùng transactional outbox trong cùng database nguồn, rồi worker chuyển sự kiện tới bộ xử lý. Dù có outbox, hệ thống vẫn phải xử lý sự kiện đến lặp, trễ, sai thứ tự và phục hồi sau gián đoạn.

**Độ tươi:** nếu UI cho phép tên danh mục cũ tối đa 30 giây, hãy đo độ trễ end-to-end từ lúc commit ở nguồn đến lúc bản sao được cập nhật, thay vì chỉ đo thời gian chạy câu UPDATE. Trong đợt cập nhật nhiều sản phẩm, một số bản sao có thể đổi trước những bản còn lại; không thể hứa toàn bộ cùng cập nhật tức thời nếu kiến trúc không bảo đảm điều đó.

### 6.1. Vì sao phiên bản tốt hơn chỉ dùng thời gian?

Sự kiện có thể đến ngược thứ tự. Nếu “Tên A” được phát trước “Tên B” nhưng “Tên A” đến sau, cách cập nhật vô điều kiện sẽ ghi đè tên mới bằng tên cũ.

Số phiên bản tăng theo **mỗi danh mục** cho phép bỏ qua sự kiện cũ:

~~~text
Nguồn danh mục #10:
  v12: Văn phòng phẩm
  v13: Dụng cụ văn phòng
  v14: Dụng cụ học tập

Worker nhận theo thứ tự v14, v13:
  nhận v14 => cập nhật projection lên v14
  nhận v13 => bỏ qua vì 13 < 14
~~~

Một timestamp đơn lẻ chịu ảnh hưởng đồng hồ giữa các máy, định dạng và cách xác định mốc thay đổi. Phiên bản được tạo tuần tự ở nguồn giúp quy tắc so sánh rõ ràng hơn. Vẫn cần tránh hai tác nhân cùng phát ra phiên bản bằng nhau với nội dung khác nhau.

## 7. Phương án C: không nhân bản, nhưng tối ưu truy vấn và dữ liệu trả về

Trước khi tạo thêm dữ liệu, hãy xác minh liệu chi phí đọc có nằm ở JOIN không.

### 7.1. Những tối ưu thường đủ dùng

- **Chỉ chọn cột cần hiển thị:** thay vì SELECT * và trả cả mô tả, blob hoặc thuộc tính hiếm dùng.
- **Giới hạn tập sản phẩm trước khi nối:** dùng bộ lọc, ORDER BY và LIMIT hợp lý.
- **Chỉ mục hỗ trợ bộ lọc/sắp xếp:** tối ưu cho access pattern thực tế; dùng kế hoạch truy vấn để xác nhận.
- **Tránh N+1 query:** tải danh sách sản phẩm và danh mục bằng truy vấn theo tập, thay vì gọi riêng từng danh mục từ ứng dụng.
- **Phân trang ổn định:** keyset pagination có thể giảm chi phí khi duyệt sâu, tùy nhu cầu giao diện.
- **Cache danh mục nhỏ:** cache theo **category_id** cùng chiến lược hết hạn hoặc vô hiệu hóa khi thay đổi nếu chấp nhận độ tươi tương ứng.

Một ứng dụng có thể tải 40 sản phẩm rồi lấy danh mục bằng một truy vấn **WHERE category_id IN (...)**, dựng kết quả ở tầng ứng dụng. Đây cũng là một lựa chọn không cần nhân bản lâu dài vào bảng sản phẩm. Tuy nhiên, nó có thêm round-trip, vì vậy phải đo cùng với phương án JOIN trực tiếp thay vì mặc định nhanh hơn.

### 7.2. Đo kế hoạch truy vấn

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.product_id,
    p.product_name,
    c.display_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.is_active = TRUE
ORDER BY p.created_at DESC, p.product_id DESC
LIMIT 40;
~~~

Khi đọc kết quả, tập trung vào:

| Quan sát | Diễn giải cần kiểm tra |
| --- | --- |
| **Nested Loop + Index Scan** để lấy danh mục | Có thể hoàn toàn phù hợp khi chỉ có 40 sản phẩm và lookup theo PK |
| **Seq Scan** trên sản phẩm với nhiều dữ liệu phải quét | Có thể do thiếu chỉ mục phù hợp, điều kiện ít chọn lọc, hoặc bộ tối ưu đánh giá quét bảng rẻ hơn |
| **Sort** trên rất nhiều hàng | Có thể cần chỉ mục theo bộ lọc + thứ tự hoặc lọc sớm |
| Số **actual rows** khác xa ước lượng | Xem thống kê, phân bố lệch, kế hoạch với tham số đại diện |
| **shared hit/read** cao | Phân tích lượng block đọc và mức sử dụng cache, không suy trực tiếp ra thời gian mạng |
| Thời gian phần JOIN rất nhỏ so với API | Tìm vấn đề ở truy vấn khác, serialization, mạng, N+1 hoặc render |

**EXPLAIN (ANALYZE)** thực sự chạy truy vấn. Ví dụ SELECT có thể dùng trong môi trường thử nghiệm, nhưng phép đo vẫn có overhead. Số **cost** của bộ tối ưu không phải mili giây; nên so số đo thực, mức tài nguyên và latency toàn API.

## 8. So sánh phương án bằng mẫu truy cập và số liệu

Giả sử mô hình đã chuẩn hóa phục vụ 40 sản phẩm/trang. Nhóm đặt mục tiêu **p95 API ≤ 160 ms** và tên danh mục trên trang danh sách được phép trễ tối đa **30 giây**; trang quản trị cần đúng ngay sau khi đổi tên.

**Bảng dưới là số liệu giả định để hướng dẫn ra quyết định, không phải benchmark đã chạy.**

| Chỉ tiêu | JOIN đã tối ưu | Copy trong products, đồng bộ cùng giao dịch | Projection bất đồng bộ |
| --- | ---: | ---: | ---: |
| API danh sách sản phẩm p95 | 118 ms | 109 ms | 83 ms |
| SLO đọc ≤ 160 ms | Đạt | Đạt | Đạt |
| Tên danh mục sau commit | Đọc giá trị nguồn khi truy vấn | Đúng sau commit nếu mọi đường ghi tuân thủ quy tắc | Có thể cũ trong cửa sổ đồng bộ |
| Đổi tên danh mục nhiều sản phẩm | Cập nhật hàng nguồn | Có thể phát sinh rất nhiều hàng ghi và khóa | Phân tán chi phí sang pipeline và kho đọc |
| Chi phí vận hành bổ sung | Ít | Logic cập nhật + đối soát | Outbox/sự kiện, projection, lag monitor, rebuild |
| Điểm cần kiểm chứng | Phần JOIN thực sự tốn bao nhiêu | p95/p99 đường ghi khi đổi tên, tương tranh | Độ trễ dữ liệu cuối đến cuối, backlog, replay |
| Phù hợp màn quản trị đòi tên mới ngay | Có | Có nếu cơ chế nhất quán đúng | Chỉ nếu trang quản trị đọc nguồn hoặc chờ đồng bộ xác nhận |

Kết luận dựa trên giả định trên:

- **JOIN đã tối ưu** đạt mục tiêu, giữ mô hình đơn giản và nhất quán theo nguồn. Có thể là lựa chọn tốt nhất cho màn hình danh sách thông thường.
- **Copy trực tiếp vào products** giảm thêm 9 ms p95 đọc nhưng tăng gánh nặng ghi khi đổi tên. Cần chứng cứ rằng lợi ích đáng để đánh đổi.
- **Projection bất đồng bộ** giảm thời gian đọc hơn trong ví dụ, hợp lý khi đã có search/read model riêng và người dùng chấp nhận độ trễ. Vẫn cần đo thời gian trễ thực để biết có đạt 30 giây không.

Không thể suy ra từ một số p95 duy nhất rằng phương án sẽ tốt ở mọi tải. Phải đo với đồng thời thực tế, dữ liệu nóng/lạnh, cả đợt đổi tên hàng loạt và trường hợp nhóm có số sản phẩm rất lớn.

## 9. Chi phí cần tính ngoài thời gian SELECT

Giá trị hiển thị thường ngắn, nhưng số lượng bản sao có thể rất lớn. Hãy đo cả:

| Nhóm chi phí | Cách phát sinh | Cách kiểm chứng |
| --- | --- | --- |
| Đọc | JOIN, lookup, serialization, network round-trip | p50/p95/p99 API, EXPLAIN, số truy vấn/request |
| Ghi | Một lần đổi nguồn kéo theo nhiều UPDATE hoặc sự kiện | Số hàng bị sửa, độ trễ ghi, throughput |
| Tương tranh | Transaction cập nhật nhiều sản phẩm giữ khóa lâu | Lock waits, deadlock, giao dịch bị retry |
| Lưu trữ | Cột bản sao, index, WAL, tài liệu trong search index | Dung lượng bảng/chỉ mục, tốc độ tăng |
| Đồng bộ | Queue, outbox, worker, invalidation | Độ trễ từ commit đến bản sao mới, backlog, lỗi |
| Độ đúng | Sai tên, ghi đè từ sự kiện cũ, sản phẩm chuyển danh mục | Truy vấn đối soát, số bản ghi lệch |
| Vận hành | Backfill, thay đổi tên hàng loạt, khôi phục projection | Thời gian nạp, thời gian sửa sai, khả năng rollback |

Cần chú ý cả tính **đa ngôn ngữ**. Nếu danh mục có tên tiếng Việt và tiếng Anh, sao chép một cột **category_name_display** không nói rõ đó là ngôn ngữ nào. Một thiết kế có thể cần cặp **(category_id, locale)**, bảng bản dịch, trường với hậu tố locale, hoặc mô hình đọc tạo theo ngôn ngữ. Số lượng bản sao và cách cập nhật tăng theo số bản dịch; cần mô hình hóa trước khi tối ưu.

**Quyền riêng tư và bảo mật:** sao chép thông tin tác giả, ảnh đại diện hoặc thuộc tính có thể thay đổi quyền công khai làm tăng số nơi phải xóa hoặc ẩn dữ liệu khi người dùng thay đổi cài đặt. Dữ liệu hiển thị không mặc nhiên là dữ liệu công khai mãi mãi. Nếu dùng search index hoặc cache bên ngoài, chính sách phân quyền và thu hồi cũng áp dụng cho bản sao.

## 10. Đối soát: làm sao biết bản sao vẫn đúng?

Với cột **products.category_name_display** lưu trong cùng PostgreSQL và cam kết đúng ngay, truy vấn đối soát:

~~~sql
SELECT
    p.product_id,
    p.category_id,
    p.category_name_display AS copied_name,
    c.display_name AS source_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.category_name_display IS DISTINCT FROM c.display_name;
~~~

**IS DISTINCT FROM** bắt được cả trường hợp bản sao NULL, trong khi **<>** có thể không phát hiện đúng vì so sánh với NULL trả UNKNOWN. Nếu truy vấn trả về dòng, bản sao và nguồn hiện khác nhau theo định nghĩa giá trị hiện hành.

Với projection bất đồng bộ có **category_display_version**, cần tách hai loại kiểm tra:

1. **Chưa bắt kịp phiên bản:** số bản ghi có phiên bản thấp hơn nguồn. Chúng có thể là sai khác tạm thời nằm trong giới hạn trễ.
2. **Đã cùng phiên bản nhưng khác tên:** dấu hiệu lỗi đồng bộ hoặc dữ liệu sai, vì cùng phiên bản phải xác định cùng giá trị.

Ví dụ truy vấn phân loại:

~~~sql
SELECT
    pc.product_id,
    pc.category_id,
    pc.category_display_version AS copy_version,
    c.display_version AS source_version,
    CASE
        WHEN pc.category_display_version < c.display_version
            THEN 'LAGGING'
        WHEN pc.category_display_version = c.display_version
             AND pc.category_name_display IS DISTINCT FROM c.display_name
            THEN 'VALUE_MISMATCH'
        WHEN pc.category_display_version > c.display_version
            THEN 'VERSION_AHEAD'
        ELSE 'MATCH'
    END AS sync_state
FROM product_cards AS pc
JOIN categories AS c
    ON c.category_id = pc.category_id;
~~~

Truy vấn này giả định **product_cards** là projection của danh mục hiện hành và mỗi lần đổi tên tăng phiên bản ở nguồn. Nếu phép đo thực hiện khi source đang đổi, kết quả có thể khác nhau theo thời điểm snapshot. Khi đánh giá SLA, cần lưu thời điểm commit hoặc mốc sự kiện để xác định bản sao đã trễ vượt ngưỡng hay chưa.

Phân biệt **độ trễ được cho phép** với **lỗi vĩnh viễn**. Cảnh báo hệ thống có thể dựa vào số lượng bản sao trễ quá 30 giây, số lần worker xử lý lỗi, backlog không giảm và số **VALUE_MISMATCH** sau khi đã cùng phiên bản. Một công việc tính lại từ nguồn chuẩn cần được kiểm thử trước khi sự cố xảy ra.

## 11. Triển khai an toàn và có thể quay lại

Sao chép thuộc tính hiển thị là thay đổi mô hình dữ liệu và đường ghi/đọc. Đối với hệ thống có traffic liên tục, trình tự tham khảo:

1. **Đặc tả hợp đồng:** đặt tên cột rõ là bản sao dùng đọc; nguồn chuẩn, ngữ nghĩa, phiên bản, độ trễ và người sở hữu.
2. **Mở rộng lược đồ:** thêm cột nullable hoặc tạo bảng projection riêng, chưa chuyển đường đọc sang bản sao chưa có dữ liệu.
3. **Kích hoạt cơ chế đồng bộ:** cập nhật lúc nguồn thay đổi, bao gồm thêm/sửa/xóa, chuyển quan hệ, import và retry.
4. **Backfill có kiểm soát:** nạp các bản ghi cũ; bảo vệ chống ghi đè giá trị mới bằng ảnh chụp cũ.
5. **Đối soát:** so với nguồn chuẩn, kiểm tra cả trường hợp NULL, chuyển danh mục, cập nhật hàng loạt và truy cập đồng thời.
6. **Chạy thử đọc song song:** so kết quả từ truy vấn nguồn với bản sao trên tập dữ liệu đại diện; giám sát độ trễ và lỗi.
7. **Chuyển đường đọc dần:** dùng cơ chế rollout phù hợp; theo dõi API latency và tính đúng đắn, có đường quay về JOIN nếu cần.
8. **Đánh giá sau triển khai:** so lợi ích đọc với chi phí ghi, tiến trình đồng bộ, dung lượng và sự cố.

Một điểm dễ sai là chạy:

~~~sql
UPDATE products AS p
SET category_name_display = c.display_name
FROM categories AS c
WHERE p.category_id = c.category_id;
~~~

Câu lệnh trên hữu ích như **backfill minh họa**, nhưng không tự giải quyết việc dữ liệu nguồn tiếp tục đổi trong khi backfill chạy. Nếu đồng bộ theo phiên bản, cần đảm bảo bản ghi cũ không ghi đè phiên bản mới; nếu đồng bộ mạnh, cần phối hợp khóa/giao dịch và thứ tự triển khai. Tối ưu backfill theo lô cũng cần kiểm soát I/O, khóa và kế hoạch tiếp tục nếu dừng giữa chừng.

## 12. Cùng bài toán trong mô hình document, graph và analytics

**Document database:** document **product_card** có thể nhúng **category.displayName** để đáp ứng một lần đọc. Câu hỏi quan trọng là fan-out khi đổi tên, giới hạn kích thước document, update nhiều document có nguyên tử hay không và thời gian cho phép trả tên cũ. Không nên suy từ khả năng nhúng sang kết luận nên nhân bản mọi thuộc tính.

**Graph database:** đỉnh **Product** nối tới đỉnh **Category**, thuộc tính tên nằm ở Category. Nếu truy vấn thường duyệt quan hệ và trả tên danh mục, dữ liệu chuẩn có thể đủ tốt. Sao chép tên sang đỉnh Product giúp truy cập cục bộ trong một số truy vấn nhưng lại tạo fan-out khi đổi tên; cần đo workload traversal và cách cập nhật các đỉnh.

**Hệ phân tích:** báo cáo bán hàng thường dùng bảng **fact** và **dimension**. Nếu yêu cầu tên danh mục hiện hành, có thể nối dimension hiện hành lúc đọc. Nếu yêu cầu tên danh mục **tại thời điểm bán**, cần mô hình lịch sử (chẳng hạn dimension có hiệu lực theo thời gian) hoặc snapshot với mốc rõ ràng. Sao chép tên mà không ghi thời điểm có thể tạo báo cáo lịch sử sai.

Dù dùng relational, document, graph hay analytics, câu hỏi cốt lõi không đổi: **đây là tên hiện hành hay tên lịch sử; nguồn chuẩn ở đâu; khi đổi tên, bao nhiêu bản ghi bị ảnh hưởng; mất bao lâu để đồng bộ; làm sao biết đồng bộ đúng?**

## 13. Checklist quyết định trước khi sao chép thuộc tính

| Câu hỏi | Bằng chứng tối thiểu |
| --- | --- |
| Thuộc tính phục vụ màn hình/luồng đọc nào? | API, query, các trường cần trả về, lưu lượng |
| JOIN hiện tốn bao nhiêu? | EXPLAIN (ANALYZE, BUFFERS), số truy vấn/request, độ trễ API |
| Có tối ưu đơn giản hơn không? | Đo với chỉ mục, lọc sớm, batch, cache |
| Thuộc tính là hiện hành hay snapshot? | Định nghĩa nghiệp vụ khi giá trị nguồn đổi |
| Bản sao nằm ở đâu? | Cột cùng DB hay projection/search/document |
| Nguồn chuẩn và người sở hữu? | Bảng/trường nguồn, nhóm chịu trách nhiệm |
| Độ trễ được phép? | Cam kết quan sát được và cách đo lag |
| Ghi bao nhiêu bản sao khi đổi nguồn? | Fan-out phân vị/thấp nhất/cao nhất, chi phí ghi |
| Cập nhật đồng bộ theo cách nào? | Transaction/trigger hoặc outbox/event/version |
| Xóa, đổi quan hệ, retry, sự kiện đến trễ? | Quy tắc nhất quán và kiểm thử tình huống |
| Phát hiện và sửa sai? | Đối soát, ngưỡng cảnh báo, rebuild |
| Lợi ích có vượt chi phí không? | p95/p99 đọc/ghi, độ đúng, dung lượng, vận hành |

Một quyết định tốt có thể là **không sao chép** khi JOIN đã đáp ứng mục tiêu. Ngược lại, bản sao sẽ là thiết kế hợp lý khi workload thật chứng minh lợi ích, ngữ nghĩa được định nghĩa và cơ chế đồng bộ đủ tin cậy.

## 14. Bài tập tình huống

### Tình huống A — Danh mục ít và trang danh sách ngắn

Bảng **categories** có 80 hàng, trang sản phẩm trả 40 thẻ/lần. p95 của API với JOIN đã có chỉ mục là 95 ms, SLO là 180 ms. Một thử nghiệm thêm **category_name_display** giúp còn 92 ms, nhưng danh mục đôi khi được đổi tên đồng loạt.

**Câu hỏi:** Có nên duy trì bản sao trong bảng sản phẩm chỉ vì giảm được 3 ms p95 không?

### Tình huống B — Tìm kiếm ở kho riêng

Hệ thống có search index lưu hàng triệu thẻ sản phẩm. Nó phải hiển thị tên danh mục và cho phép tên cũ tối đa 60 giây. Sự kiện đổi tên có **categoryId**, **displayName**, **displayVersion**, và cùng sự kiện có thể được giao lại nhiều lần.

**Câu hỏi:** Thiết kế handler tối thiểu gồm những điều kiện nào? Đo độ tươi từ thời điểm nào?

### Tình huống C — Tên tác giả tại thời điểm đăng bài

Một tòa soạn yêu cầu bài xuất bản năm trước giữ nguyên tên bút danh được ghi lúc xuất bản, dù tác giả đổi tên hiển thị trong tài khoản.

**Câu hỏi:** Có nên cập nhật tên trong tài liệu cũ mỗi khi đổi hồ sơ hay không? Vì sao?

### Tình huống D — Bản sao sai sau khi chuyển danh mục

Sản phẩm P được chuyển từ danh mục A sang B. Sau đó worker nhận trễ sự kiện đổi tên của A và vô tình ghi tên A vào bản ghi P trong search index.

**Câu hỏi:** Điều kiện nào giúp tránh lỗi này? Nếu còn các sự kiện cập nhật P đến sai thứ tự thì cần gì thêm?

### Gợi ý lời giải

- **A:** Không có cơ sở mạnh để thêm bản sao: JOIN đạt SLO, mức cải thiện rất nhỏ và đồng bộ khi đổi tên có fan-out. Nên giữ mô hình đơn giản trừ khi có yêu cầu khác được đo.
- **B:** Chỉ cập nhật bản ghi vẫn có **category_id** trùng sự kiện và phiên bản lưu nhỏ hơn **displayVersion** mới; xử lý lặp idempotent, retry, backlog, đối soát và tái dựng. Đo từ **lúc thay đổi được commit ở nguồn đến lúc projection sẵn sàng phục vụ đọc**, gồm cả chờ sự kiện và cập nhật kho đọc.
- **C:** Không cập nhật tên lịch sử nếu yêu cầu giữ nguyên tên lúc xuất bản. Đây là snapshot có ngữ nghĩa riêng; cần mốc chụp rõ ràng và quy trình hiệu chỉnh nếu chính sách xuất bản cho phép.
- **D:** Handler cần kiểm tra **category_id hiện tại của sản phẩm** và phiên bản danh mục. Đồng thời cần phiên bản thay đổi sản phẩm hoặc thứ tự sự kiện theo từng sản phẩm để tránh áp dụng nhầm việc chuyển danh mục cũ.

## 15. Ghi nhớ

**Sao chép một thuộc tính hiển thị là đổi chi phí JOIN ở đường đọc lấy chi phí đồng bộ trên đường ghi.** Quyết định phải dựa trên số liệu: query shape, tần suất đọc, số hàng được JOIN, fan-out cập nhật, p95/p99, mức tăng tải ghi và độ tươi cần đạt.

Nếu bản sao đại diện cho **trạng thái hiện hành**, phải xác định nguồn chuẩn, cập nhật đủ mọi đường ghi, xử lý tương tranh và đối soát. Nếu đó là **snapshot lịch sử**, phải ghi rõ thời điểm và không đồng bộ mù quáng theo giá trị mới.

Câu hỏi cuối cùng trước khi thêm một cột tên, logo hoặc nhãn là: **“Giảm được bao nhiêu chi phí đọc, mỗi lần nguồn thay đổi phải sửa bao nhiêu bản sao, và có thể chứng minh các bản sao đang đúng theo thời điểm cam kết hay không?”**
