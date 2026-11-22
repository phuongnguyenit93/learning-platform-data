# Phi chuẩn hóa có chủ đích khác với thiết kế dư thừa ngoài kiểm soát

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt một bản sao dữ liệu được thiết kế có chủ đích với dữ liệu lặp lại do thiếu kỷ luật mô hình hóa.
- Chỉ ra nguồn dữ liệu chuẩn, ý nghĩa nghiệp vụ, quy tắc đồng bộ và mức độ nhất quán của từng trường phi chuẩn hóa.
- Phân tích chi phí đọc, ghi, lưu trữ, sửa lỗi và vận hành trước khi quyết định lưu dữ liệu suy ra.
- Thiết kế một trường tổng hợp có cơ chế cập nhật, đối soát và khôi phục khi xảy ra sai lệch.
- Nhận diện khi nào dữ liệu trông giống nhau nhưng thực chất mang **hai ý nghĩa nghiệp vụ khác nhau**, đặc biệt với dữ liệu lịch sử.

Bài học thuộc phạm vi **Database Data Modeling**: chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, ràng buộc và lược đồ vật lý; cân nhắc giữa mô hình quan hệ, document, đồ thị và phân tích sao cho cấu trúc dễ kiểm chứng và tiến hóa.

## 1. Cùng một dữ liệu lặp lại, hai chất lượng thiết kế khác nhau

Một cửa hàng trực tuyến lưu danh mục sản phẩm và đơn hàng. Tên danh mục nằm trong bảng **categories** nhưng cũng xuất hiện trong hàng nghìn bản ghi **products**. Mỗi lần đổi tên danh mục, có sản phẩm hiện tên mới, có sản phẩm vẫn hiện tên cũ.

Ở một màn hình khác, hệ thống lưu **orders.total_amount** dù tổng tiền cũng tính được bằng cách cộng các dòng **order_items**. Trường này có thể là một quyết định tốt: trang danh sách đơn hàng đọc rất thường xuyên, trong khi tổng tiền chỉ thay đổi khi dòng hàng thay đổi. Tuy nhiên, điều đó chỉ đúng khi hệ thống có quy tắc cập nhật, kiểm tra và sửa sai rõ ràng.

Vấn đề không nằm ở việc dữ liệu có bị lặp hay không. Vấn đề là **mỗi giá trị được lưu nhằm phục vụ yêu cầu nào, ai chịu trách nhiệm duy trì nó và điều gì xảy ra khi dữ liệu nguồn thay đổi**.

**Chuẩn hóa** tổ chức các phụ thuộc dữ liệu để hạn chế bất thường khi thêm, sửa, xóa. Ví dụ, nếu mỗi mã danh mục xác định duy nhất một tên danh mục hiện hành, ta thường lưu tên trong **categories** và cho **products** tham chiếu qua khóa ngoại. Những dạng chuẩn như 3NF là công cụ lý giải các phụ thuộc này; chúng không có nghĩa là mọi truy vấn phải chạy thật nhiều phép nối, cũng không cấm lưu dữ liệu dẫn xuất khi có lý do xác đáng.

**Phi chuẩn hóa có chủ đích (intentional denormalization)** là quyết định đưa một bản sao hoặc giá trị dẫn xuất vào mô hình lưu trữ nhằm đáp ứng nhu cầu đo được, đồng thời đặt ra hợp đồng duy trì tính đúng đắn của nó.

**Dư thừa ngoài kiểm soát (uncontrolled redundancy)** xảy ra khi cùng một sự thật nghiệp vụ được sao chép qua nhiều nơi nhưng thiếu quy tắc về nguồn chuẩn, thời điểm cập nhật, tính nhất quán và xử lý sai lệch. Hệ thống có thể hoạt động bình thường trong thời gian ngắn; lỗi thường lộ ra khi nghiệp vụ thay đổi.

| Tiêu chí | Phi chuẩn hóa có chủ đích | Dư thừa ngoài kiểm soát |
| --- | --- | --- |
| Lý do tồn tại | Có yêu cầu đọc, báo cáo, lịch sử hoặc giới hạn hiệu năng cụ thể | Sao chép cho tiện, tránh viết truy vấn hoặc phát sinh qua nhiều lần sửa |
| Ý nghĩa dữ liệu | Được định nghĩa chính xác: hiện hành, tại thời điểm giao dịch hay giá trị tổng hợp | Tên trường giống nhau nhưng ngữ nghĩa không rõ |
| Nguồn chuẩn | Biết bản ghi/trường nào là nguồn chuẩn và trường nào là bản sao | Nhiều nơi cùng được xem là “đúng” |
| Cập nhật | Có giao thức khi thêm, sửa, xóa, đổi trạng thái và thử lại | Chỗ cập nhật, chỗ bỏ quên |
| Độ trễ cho phép | Được công bố, ví dụ trong cùng giao dịch hoặc tối đa vài phút | Không biết dữ liệu có thể cũ đến khi nào |
| Kiểm chứng | Có bất biến, phép đối soát, giám sát và phương án tái tạo | Phát hiện sai khi người dùng báo lỗi |
| Sở hữu và thay đổi | Có đơn vị sở hữu và quy trình nâng cấp lược đồ | Mỗi thành phần tự tạo quy tắc riêng |

**Điểm mấu chốt:** một cột dữ liệu giống hệt nhau về mặt vật lý có thể là thiết kế tốt hoặc xấu tùy vào ngữ nghĩa và cơ chế vận hành bao quanh nó.

## 2. Bắt đầu từ mô hình dữ liệu có nguồn chuẩn

Xét mô hình quan hệ tối giản cho danh mục, sản phẩm, đơn hàng và dòng hàng:

~~~sql
-- Ví dụ theo cú pháp PostgreSQL.
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES categories(category_id),
    name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL CHECK (current_price >= 0)
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_purchase NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_at_purchase >= 0),
    product_name_at_purchase TEXT NOT NULL
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
~~~

Mô hình phân biệt ba loại sự thật:

1. **categories.name** và **products.name/current_price** là thông tin *hiện hành* của danh mục, sản phẩm.
2. **order_items.unit_price_at_purchase** và **product_name_at_purchase** là thông tin *tại thời điểm xác nhận đơn hàng*. Chúng cần được giữ cho hóa đơn hoặc lịch sử, kể cả khi sản phẩm đổi tên hay giá.
3. Tổng tiền của đơn, theo quy ước đơn giản trong ví dụ, **bằng tổng quantity × unit_price_at_purchase của các dòng hiện có**. Giá trị này có thể tính khi đọc.

Trường có hậu tố *at_purchase* không đơn thuần là bản sao sai chuẩn của tên/giá hiện hành. Nó biểu diễn một **sự thật lịch sử khác**. Nếu chỉ nối về bảng **products** để hiện giá hiện tại trên hóa đơn cũ, kết quả mới là sai nghiệp vụ.

Trong hệ thống thật, tổng thanh toán có thể còn bao gồm giảm giá, thuế, vận chuyển, hoàn tiền và làm tròn. Trước khi lưu tổng, phải định nghĩa rõ **tổng nào** đang được tính. Ở các ví dụ dưới đây, **total_amount** chỉ là tổng thành tiền của các dòng hàng đang có, chưa bao gồm các thành phần khác.

Khi chưa lưu sẵn tổng, truy vấn có thể viết:

~~~sql
SELECT
    o.order_id,
    COALESCE(SUM(oi.quantity * oi.unit_price_at_purchase), 0) AS total_amount
FROM orders AS o
LEFT JOIN order_items AS oi ON oi.order_id = o.order_id
WHERE o.order_id = 1001
GROUP BY o.order_id;
~~~

Đây là điểm xuất phát để đo hiệu năng. Cần xem kế hoạch thực thi, chỉ mục, số dòng trên mỗi đơn và tần suất truy vấn trước khi kết luận phép tính tổng là nút thắt. Một truy vấn chậm có thể xuất phát từ N+1 query, thiếu chỉ mục hoặc lấy quá nhiều dữ liệu, chứ chưa chắc vì thiếu phi chuẩn hóa.

## 3. Ví dụ tốt: lưu tổng đơn hàng như dữ liệu dẫn xuất có kiểm soát

Giả sử trang danh sách đơn hàng được truy cập với lưu lượng lớn, và việc tính tổng cho hàng trăm đơn trong mỗi lần tải tạo ra chi phí đáng kể ngay cả sau khi tối ưu truy vấn. Nhóm phát triển chọn lưu tổng thành tiền vào **orders** để đọc nhanh.

### 3.1. Công bố bất biến

Hệ thống thống nhất:

> Với mỗi đơn hàng, **orders.total_amount = SUM(order_items.quantity × order_items.unit_price_at_purchase)**, trong đó tập dòng hàng và quy tắc tính tiền được định nghĩa rõ.

Đó là **bất biến (invariant)**. Nó biến một ý định tối ưu mơ hồ thành điều kiện có thể kiểm tra được. **order_items** là nguồn chuẩn cho tổng thành tiền; **orders.total_amount** là giá trị dẫn xuất phục vụ đọc.

Trong một hệ thống có thanh toán thực, cần phân biệt tổng đang tính này với số tiền đã thu và số dư phải hoàn. Không thể tự động dùng một trường tổng cho tất cả các khái niệm tài chính.

### 3.2. Tạo cột và nạp dữ liệu ban đầu

~~~sql
ALTER TABLE orders
ADD COLUMN total_amount NUMERIC(14, 2) NOT NULL DEFAULT 0
    CHECK (total_amount >= 0);

UPDATE orders AS o
SET total_amount = COALESCE(
    (
        SELECT SUM(oi.quantity * oi.unit_price_at_purchase)
        FROM order_items AS oi
        WHERE oi.order_id = o.order_id
    ),
    0
);
~~~

**Lưu ý triển khai:** đoạn SQL trên minh họa lược đồ và backfill. Khi hệ thống vẫn đang ghi dữ liệu, không được chạy backfill tách rời rồi giả định mọi giá trị vẫn đúng. Cần phối hợp việc kích hoạt cơ chế cập nhật mới, backfill và đối soát (ví dụ bằng giao dịch, khóa hoặc kế hoạch chuyển đổi từng bước) để tránh ghi đè giá trị mới bằng ảnh chụp cũ.

### 3.3. Ghi thay đổi trong cùng giao dịch

Khi thêm dòng hàng, ứng dụng phải tăng tổng bằng **số tiền thực sự ghi**. Với PostgreSQL có thể minh họa cách này:

~~~sql
BEGIN;

WITH inserted_line AS (
    INSERT INTO order_items (
        order_item_id,
        order_id,
        product_id,
        quantity,
        unit_price_at_purchase,
        product_name_at_purchase
    )
    VALUES (7001, 1001, 501, 2, 150000.00, 'Sổ tay A')
    RETURNING order_id, quantity * unit_price_at_purchase AS line_amount
)
UPDATE orders AS o
SET total_amount = o.total_amount + inserted_line.line_amount
FROM inserted_line
WHERE o.order_id = inserted_line.order_id;

COMMIT;
~~~

Câu lệnh **UPDATE** tăng giá trị dựa trên giá trị hiện tại trong cơ sở dữ liệu, giúp tránh kiểu ghi đè sai khi hai giao dịch cùng đọc một số tổng cũ rồi tự tính ở phía ứng dụng. Giao dịch đảm bảo hai thay đổi cùng thành công hoặc cùng được hoàn tác. Đây là **một minh họa cho trường hợp thêm dòng hàng**, chưa phải toàn bộ cơ chế vận hành của hệ thống bán hàng.

Để triển khai đầy đủ, phải thiết kế thêm:

- **Sửa dòng hàng:** tính chênh lệch giữa thành tiền mới và cũ, rồi cập nhật tổng với đúng chênh lệch.
- **Xóa hoặc hủy dòng hàng:** trừ thành tiền tương ứng nếu quy tắc tổng coi dòng đó không còn hiệu lực.
- **Đổi giá, giảm giá, trả hàng:** xác định trường hợp nào làm thay đổi tổng và trường hợp nào tạo nghiệp vụ độc lập.
- **Thử lại yêu cầu hoặc xử lý sự kiện trùng:** có khóa yêu cầu duy nhất, ràng buộc hoặc cách xử lý idempotent để tránh cộng tiền hai lần.
- **Mọi đường ghi:** web, tác vụ nền, import, công cụ quản trị và tiến trình sửa dữ liệu phải tuân thủ cùng một quy tắc.
- **Tương tranh:** cập nhật, xóa và đọc giá trị cũ phải được bảo vệ bởi giao dịch/khóa thích hợp; kiểm thử nhiều giao dịch đồng thời.

Có thể đặt logic tại tầng dịch vụ, stored procedure hoặc trigger. Việc lựa chọn tùy vào số lượng đường ghi, khả năng quản trị, ranh giới giao dịch và cách triển khai. Không có giải pháp nào tự nhiên đúng nếu còn đường ghi bỏ qua quy tắc.

Nếu dữ liệu nguồn và bản sao nằm ở **hai kho dữ liệu khác nhau**, một giao dịch SQL như trên thường không bao trùm được cả hai. Khi đó cần mô hình cập nhật bất đồng bộ (ví dụ outbox + bộ xử lý sự kiện), thứ tự sự kiện, xử lý lặp, khả năng phát lại và định nghĩa thời gian trễ cho phép.

### 3.4. Đối soát độc lập với đường ghi

Một trường tổng không thể chỉ được tin tưởng vì mã cập nhật “trông có vẻ đúng”. Hãy kiểm tra trực tiếp từ dữ liệu nguồn:

~~~sql
SELECT
    o.order_id,
    o.total_amount AS stored_total,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_purchase),
        0
    ) AS calculated_total
FROM orders AS o
LEFT JOIN order_items AS oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount <> COALESCE(
    SUM(oi.quantity * oi.unit_price_at_purchase),
    0
);
~~~

Nếu truy vấn trả về dòng, giá trị lưu và giá trị tính lại đang khác nhau theo bất biến đã công bố. Hệ thống cần ghi nhận số đơn lệch, biên độ lệch, nguyên nhân, thời điểm và phương án sửa có kiểm soát. Khi đồng bộ bất đồng bộ, chỉ đánh giá bản ghi đã qua ngưỡng trễ cho phép; sai khác tạm thời trong cửa sổ đồng bộ chưa đủ để kết luận có lỗi.

**Một phép CHECK thông thường trên cột total_amount chỉ kiểm tra được điều kiện trong hàng**, chẳng hạn không âm. Nó không tự bảo đảm tổng bằng dữ liệu ở bảng khác. Vì vậy, kiểm tra đối soát là thành phần riêng của thiết kế.

## 4. Ví dụ xấu: nhân bản tên danh mục mà không có hợp đồng đồng bộ

Giả sử nhóm phát triển thêm một trường để trang danh sách sản phẩm không phải nối bảng **categories**:

~~~sql
ALTER TABLE products ADD COLUMN category_name TEXT;

UPDATE products AS p
SET category_name = c.name
FROM categories AS c
WHERE p.category_id = c.category_id;
~~~

Ở thời điểm vừa nạp dữ liệu, **products.category_name** khớp với **categories.name**. Sau đó có thao tác:

~~~sql
UPDATE categories
SET name = 'Đồ dùng học tập'
WHERE category_id = 10;
~~~

Nếu không có bước cập nhật sản phẩm, cùng một danh mục có **hai tên hiện hành khác nhau**. Sau một lần import hay một dịch vụ mới ra đời, dữ liệu có thể sai theo cách khó nhìn thấy.

Một vài hậu quả thực tế:

- Trang chi tiết nối **categories** hiển thị tên mới; trang tìm kiếm đọc **products.category_name** hiển thị tên cũ.
- Báo cáo nhóm theo tên danh mục bị tách thành hai nhóm.
- Chạy backfill ngẫu hứng sửa một phần dữ liệu nhưng lần đổi tên tiếp theo lại tái diễn vấn đề.
- Không ai biết nên sửa **categories.name** hay **products.category_name** khi phát hiện sai.

**Có phải mọi trường products.category_name đều sai?** Không. Nếu nhóm có bằng chứng đây là một tối ưu cần thiết, công bố **categories.name** là nguồn chuẩn, chọn cách cập nhật/độ trễ cụ thể, có giám sát và có thể tái tạo bản sao, thì nó đã trở thành phi chuẩn hóa có kiểm soát. **Cấu trúc bảng không đủ để đánh giá chất lượng của quyết định.**

Với tên danh mục vốn ít bản ghi và dễ nối bằng khóa ngoại, phương án tốt ban đầu thường là dùng phép JOIN và chỉ mục phù hợp. Việc tên thay đổi hiếm không tự động làm bản sao an toàn: một lần đổi tên vẫn có thể ảnh hưởng hàng triệu sản phẩm.

## 5. Đừng nhầm bản chụp lịch sử với dữ liệu trùng sai ngữ nghĩa

So sánh hai trường:

| Trường | Câu hỏi nghiệp vụ mà trường trả lời | Khi tên sản phẩm hiện tại đổi |
| --- | --- | --- |
| **products.name** | Sản phẩm đang được gọi là gì? | Được cập nhật |
| **order_items.product_name_at_purchase** | Tên hiển thị khi khách xác nhận mua là gì? | Giữ nguyên |
| **products.category_name** (nếu được sao chép) | Tên danh mục hiện tại là gì? | Phải đồng bộ theo quy tắc đã chọn |

Nếu chỉ so chuỗi ký tự, cả ba có thể giống nhau ngay lúc đặt hàng. Nhưng **giống giá trị tại một thời điểm không có nghĩa là giống sự thật nghiệp vụ**.

Với hóa đơn, tên/giá/địa chỉ giao hàng tại thời điểm xác nhận thường cần được giữ như bản chụp lịch sử. Điều này vẫn cần quy tắc: chụp khi nào, giá trị nào là đã được xác nhận, có được hiệu chỉnh không và ai có quyền thay đổi. Còn việc sao chép tên danh mục hiện hành để hiển thị nhanh lại là một bản sao phải duy trì theo nguồn.

Một câu hỏi rất hữu ích khi thẩm định mô hình:

> “Nếu dữ liệu gốc thay đổi vào ngày mai, trường được sao chép này **nên thay đổi theo** hay **phải giữ lại giá trị cũ**?”

- **Nên thay đổi theo:** có khả năng đó là một bản sao/projection của trạng thái hiện hành; cần cơ chế đồng bộ hoặc làm mới.
- **Phải giữ giá trị cũ:** có khả năng đó là snapshot sự kiện hoặc một sự thật có hiệu lực theo thời gian; cần định nghĩa ranh giới thời điểm và quy tắc lịch sử.
- **Không ai trả lời được:** chưa đủ thông tin để quyết định cấu trúc lưu trữ.

## 6. Phi chuẩn hóa đi kèm lựa chọn về tính nhất quán

Bản sao có thể cập nhật cùng lúc với dữ liệu nguồn hoặc cập nhật sau. Cần chọn theo hệ quả nghiệp vụ của việc đọc một giá trị cũ.

| Cơ chế | Đặc tính | Ví dụ thích hợp | Giới hạn cần xử lý |
| --- | --- | --- | --- |
| Cập nhật cùng giao dịch | Nguồn và bản sao cùng commit hoặc rollback trong một DB | Tổng dòng hàng của đơn phải khớp ngay sau ghi | Ghi phức tạp hơn, khóa lâu hơn, nhiều đường ghi cần tuân thủ |
| Trigger/stored procedure trong DB | Tập trung cập nhật cho nhiều tác nhân ghi | Bộ đếm hoặc tổng đơn trong cùng DB | Cần kiểm soát đệ quy, khóa, hiệu năng và khó khăn khi debug |
| Projection qua sự kiện/outbox | Cập nhật bất đồng bộ, cho phép trễ hữu hạn | Mô hình đọc tìm kiếm, bảng tổng hợp phân tích | Xử lý trùng/lệch thứ tự, phát lại, theo dõi độ trễ |
| Materialized view hoặc bảng tổng hợp làm mới định kỳ | Dễ truy vấn tổng hợp, dữ liệu mang tính ảnh chụp | Doanh số theo ngày, dashboard nội bộ | Xác định lịch làm mới và thời điểm dữ liệu có hiệu lực |
| Cache có TTL/invalidation | Tăng tốc cho truy vấn lặp nhiều | Trang danh mục phổ biến | Hết hạn, xóa cache, cache stampede, dữ liệu cũ |

Ví dụ, dashboard marketing cho phép số lượng đơn chậm tối đa 5 phút có thể dùng bảng tổng hợp bất đồng bộ. Nhưng nếu giá trị ấy dùng để quyết định có giao hàng khi khách vừa trả tiền hay không, trễ 5 phút có thể sai quy trình. Một chỉ tiêu “nhanh” không đủ để chọn cơ chế.

**Tính nhất quán phải được diễn đạt bằng hành vi quan sát được**, chẳng hạn “sau khi cập nhật dòng hàng thành công, đọc tổng trong cùng cơ sở dữ liệu cho kết quả đã cập nhật” hoặc “dashboard có độ trễ tối đa 5 phút trong điều kiện hoạt động bình thường, và sẽ cảnh báo nếu vượt ngưỡng”. Tránh các mô tả không kiểm chứng được như “gần thời gian thực”.

## 7. Cân nhắc chi phí toàn vòng đời, không chỉ thời gian SELECT

Phi chuẩn hóa thường tiết kiệm CPU/I/O ở đường đọc, đổi lại chi phí khác:

- **Ghi nhiều hơn:** một thay đổi nguồn có thể cần cập nhật nhiều bản sao; một cập nhật tên danh mục có thể ảnh hưởng số lượng sản phẩm rất lớn.
- **Tăng cạnh tranh khóa:** các giao dịch cùng tăng **orders.total_amount** hoặc bộ đếm chung có thể tranh chấp một hàng.
- **Tăng dung lượng và chi phí chỉ mục:** cả dữ liệu lặp và chỉ mục của nó đều chiếm tài nguyên.
- **Rủi ro dữ liệu cũ:** lỗi mạng, sự kiện bị xử lý trùng, worker dừng hoặc đường import bỏ qua đồng bộ.
- **Khó thay đổi nghiệp vụ:** thêm khuyến mãi, thay định nghĩa “đơn hoàn tất” hoặc đổi cách tính thuế có thể buộc backfill toàn bộ dữ liệu dẫn xuất.
- **Tăng phạm vi dữ liệu cần quản lý:** sao chép thông tin nhạy cảm sang nhiều bảng hoặc hệ thống kéo theo quyền truy cập, thời hạn lưu và thao tác xóa/sửa phức tạp hơn.

Không nên coi “giảm một phép JOIN” là giá trị tự thân. Với khóa ngoại và chỉ mục tốt, phép nối có thể rất rẻ; ngược lại, aggregate trên tập dữ liệu lớn hoặc mô hình đọc đặc thù có thể thật sự cần lưu trước kết quả.

Trước khi quyết định, hãy so sánh phương án phi chuẩn hóa với các lựa chọn đơn giản hơn: viết lại truy vấn, loại bỏ N+1 query, bổ sung chỉ mục thích hợp, giới hạn số bản ghi, dùng covering index, phân trang, cache hoặc materialized view.

Ví dụ về **thí nghiệm đánh giá** (số liệu minh họa, không phải ngưỡng chung): trang danh sách đơn đo được p95 là 420 ms trên tải đại diện; sau khi thêm chỉ mục và sửa truy vấn còn 150 ms; khi thử lưu tổng còn 105 ms nhưng tăng 30 ms cho đường ghi và gây khóa chờ khi cập nhật đơn nhiều dòng. Quyết định cuối phải dựa trên mục tiêu dịch vụ và chi phí vận hành thực tế, không chỉ chênh lệch 45 ms ở đường đọc.

## 8. Bản sao có chủ đích trong các mô hình dữ liệu khác

Nguyên lý nguồn chuẩn, ngữ nghĩa, cập nhật và đối soát vẫn đúng ngoài cơ sở dữ liệu quan hệ.

| Kiểu mô hình | Cách lặp dữ liệu thường gặp | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Quan hệ (relational)** | Lưu tổng, bộ đếm, cột tên tra cứu, bảng tổng hợp | Có bất biến nào nối bản sao với bảng nguồn? Giao dịch và khóa bảo vệ được gì? |
| **Document** | Nhúng thông tin sản phẩm/địa chỉ vào document đơn hàng hoặc nhân bản thông tin tác giả vào bài viết | Đây là snapshot lịch sử hay dữ liệu hiện hành? Khi cập nhật, cần sửa bao nhiêu document? |
| **Đồ thị (graph)** | Lưu thêm thuộc tính tổng hợp trên đỉnh/cạnh để tăng tốc truy vấn hành trình | Thuộc tính dẫn xuất từ những đỉnh/cạnh nào? Khi thêm/xóa quan hệ, ai tái tính? |
| **Phân tích (analytics)** | Star schema, bảng fact tổng hợp, materialized view, bản chụp dimension theo thời gian | Dữ liệu có hiệu lực tại thời điểm nào, cập nhật gia tăng ra sao, backfill và tái lập kết quả thế nào? |

Trong document database, việc nhúng **địa chỉ giao hàng tại lúc đặt hàng** có thể là một thiết kế đúng vì document đơn hàng giữ snapshot. Nhưng nếu cùng nhúng **tên thương hiệu hiện tại** vào hàng triệu document chỉ để giảm một truy vấn, bài toán cập nhật đồng loạt rất khác.

Trong data warehouse, việc chủ động tổ chức dimension hoặc bảng tổng hợp để phục vụ truy vấn phân tích là phổ biến. Tuy nhiên, hệ thống vẫn cần định nghĩa kỳ dữ liệu, quy tắc làm mới, xử lý sự kiện đến muộn và cách tái tạo số liệu.

Không có định dạng dữ liệu nào tự động biến dư thừa thành hợp lệ. Điều quyết định vẫn là **ý nghĩa và giao thức duy trì tính đúng đắn**.

## 9. Quy trình quyết định trước khi thêm một trường phi chuẩn hóa

### Bước 1 — Xác định vấn đề đo được

Viết cụ thể truy vấn hoặc luồng nghiệp vụ đang chậm, số lần gọi, thời gian phản hồi p50/p95/p99, dung lượng dữ liệu và mục tiêu mong muốn. Xem kế hoạch thực thi và thử tối ưu mô hình chuẩn hóa trước.

### Bước 2 — Xác định ngữ nghĩa và nguồn chuẩn

Trả lời: trường này là **giá trị hiện hành**, **snapshot tại một sự kiện**, **giá trị dẫn xuất** hay **chỉ số được tính theo khoảng thời gian**? Trường nào/bảng nào quyết định giá trị đúng? Có trường hợp hai bản ghi cùng giá trị nhưng phải thay đổi độc lập không?

### Bước 3 — Viết bất biến hoặc hợp đồng độ trễ

Với đồng bộ mạnh, viết công thức có thể đối soát. Với đồng bộ bất đồng bộ, công bố mốc dữ liệu, độ trễ được phép và điều kiện hết hạn. Không nên ghi “luôn đồng bộ” nếu kiến trúc thực chất có cửa sổ dữ liệu cũ.

### Bước 4 — Thiết kế tất cả thay đổi ở đường ghi

Liệt kê đầy đủ INSERT, UPDATE, DELETE, hủy, hoàn tác, thử lại, import, job nền và cập nhật hàng loạt. Quy định giao dịch, chống xử lý trùng, sự kiện đến lệch thứ tự và trách nhiệm của từng thành phần.

### Bước 5 — Chuẩn bị cách phát hiện và phục hồi

Xây phép đối soát độc lập, số liệu theo dõi sai khác, cảnh báo khi trễ, kế hoạch tính lại từ nguồn chuẩn và chiến lược backfill khi nâng cấp lược đồ. Kiểm tra khả năng khôi phục bằng dữ liệu mẫu trước khi triển khai rộng.

### Bước 6 — Đo lại và ra quyết định

So sánh độ trễ đọc, độ trễ ghi, thông lượng, lock contention, chi phí lưu trữ và tần suất sai lệch sau khi dùng bản sao. Nếu lợi ích không còn vượt chi phí, cân nhắc bỏ trường dẫn xuất hoặc thay bằng cơ chế khác.

Một **hợp đồng dữ liệu dẫn xuất** ngắn gọn có thể ghi như sau:

| Thành phần | Ví dụ: orders.total_amount |
| --- | --- |
| Mục đích | Phục vụ danh sách đơn hàng thường xuyên, tránh tổng hợp toàn bộ dòng hàng mỗi lần đọc |
| Ngữ nghĩa | Tổng quantity × unit_price_at_purchase của các dòng hợp lệ |
| Nguồn chuẩn | order_items |
| Bản sao | orders.total_amount |
| Kiểu nhất quán | Cùng giao dịch trong PostgreSQL |
| Điểm cập nhật | Tạo/sửa/xóa dòng hàng và các chuyển trạng thái có ảnh hưởng |
| Chống cập nhật lặp | Mã thao tác duy nhất + quy tắc xử lý thử lại |
| Đối soát | Tính SUM từ order_items và so sánh tổng đã lưu |
| Chủ sở hữu | Nhóm chịu trách nhiệm nghiệp vụ đơn hàng |
| Phục hồi | Tạm dừng hoặc phối hợp ghi, tính lại tổng, đối soát rồi tiếp tục |
| Tiêu chí xem xét lại | Lợi ích đọc giảm, ghi bị nghẽn hoặc xuất hiện sai lệch vượt ngưỡng |

Đây là mẫu thảo luận thiết kế; mỗi hệ thống phải thay bằng định nghĩa và phương án có thể thực hiện được trong kiến trúc của mình.

## 10. Những dấu hiệu cần xem lại thiết kế

Một thiết kế có nguy cơ dư thừa ngoài kiểm soát khi gặp một hoặc nhiều dấu hiệu sau:

1. Cùng một thuộc tính được sửa tại nhiều bảng mà không xác định đâu là nguồn chuẩn.
2. Mã cập nhật dữ liệu nguồn không biết đến các bản sao, hoặc mỗi dịch vụ tự đồng bộ một kiểu.
3. Không ai trả lời được dữ liệu hiển thị là hiện hành, theo thời điểm giao dịch hay bản tổng hợp.
4. Có job “sửa dữ liệu hằng đêm” nhưng không điều tra lý do sai lệch phát sinh.
5. Một trường tổng được cập nhật khi INSERT nhưng bị bỏ sót khi UPDATE/DELETE hoặc xử lý lại sự kiện.
6. Tính đúng đắn chỉ được kiểm tra bằng cách mở giao diện xem vài bản ghi.
7. Bản sao làm hệ thống chậm hơn ở đường ghi, trong khi cải thiện đường đọc chưa từng được đo.

Các dấu hiệu này không buộc phải xóa ngay mọi bản sao. Chúng cho thấy thiết kế đang thiếu chứng cứ hoặc thiếu cơ chế vận hành, cần xác định lại ý nghĩa, bất biến, trách nhiệm và kết quả đo.

## 11. Bài tập tình huống

**Tình huống A — Lịch sử hóa đơn.** Một khách đặt chiếc áo tên “Áo xanh” với giá 250.000 đồng. Tháng sau, cửa hàng đổi tên sản phẩm thành “Áo biển” và giá thành 280.000 đồng. Đơn hàng cũ vẫn phải hiển thị “Áo xanh”, 250.000 đồng. Nên nối bảng sản phẩm hiện tại hay lưu trường tại thời điểm đặt hàng?

**Tình huống B — Tên danh mục.** Bảng **products** có **category_name** để trang tìm kiếm đọc nhanh, nhưng tên danh mục chỉ được cập nhật trong **categories**. Việc này thuộc loại gì? Có thể giữ cột ấy trong điều kiện nào?

**Tình huống C — Báo cáo ngày.** Nhóm phân tích lưu **daily_order_count** làm mới 5 phút/lần. Người dùng được thông báo dashboard trễ tối đa 10 phút, có cảnh báo nếu job chậm và có thể tái tính từ đơn hàng gốc. Đây có phải một quyết định phi chuẩn hóa hợp lý?

**Tình huống D — Bộ đếm đơn.** Bảng **customers** lưu **order_count**, tăng khi tạo đơn nhưng không giảm khi đơn bị hủy, trong khi báo cáo định nghĩa bộ đếm là “số đơn còn hiệu lực”. Vì sao truy vấn nhanh không đồng nghĩa thiết kế đúng?

### Gợi ý đáp án

- **A:** Lưu tên và giá *tại lúc xác nhận mua* trong dòng đơn hàng. Đây là dữ liệu lịch sử có ngữ nghĩa riêng; phải định nghĩa chính xác mốc chụp và điều kiện điều chỉnh hóa đơn.
- **B:** Hiện tại là dư thừa ngoài kiểm soát. Có thể giữ nếu có chứng cứ hiệu năng, một nguồn chuẩn, cơ chế cập nhật hoặc hết hạn xác định, đối soát và phương án backfill.
- **C:** Có thể hợp lý cho truy vấn phân tích chấp nhận trễ, nếu chỉ số được định nghĩa thống nhất, pipeline xử lý trùng và trễ, đồng thời ngưỡng trễ được theo dõi. Nếu dùng cho nghiệp vụ đòi hỏi số liệu tức thời, cần cơ chế khác.
- **D:** **order_count** đã vi phạm định nghĩa khi đơn bị hủy. Phải sửa quy tắc tăng/giảm theo vòng đời đơn, hoặc đổi lại ngữ nghĩa thành “tổng số lần tạo đơn” nếu đó mới là chỉ tiêu mong muốn; cả hai lựa chọn đều phải đối soát được.

## 12. Ghi nhớ để áp dụng

**Phi chuẩn hóa có chủ đích = nhu cầu đã đo + ngữ nghĩa rõ + nguồn chuẩn + cơ chế cập nhật + đối soát + khả năng phục hồi.**

**Dư thừa ngoài kiểm soát = nhiều bản sao của cùng sự thật nhưng không rõ nơi nào đúng hoặc không có cách giữ chúng nhất quán.**

Khi thiết kế dữ liệu, đừng chỉ hỏi “có thể bỏ JOIN bằng cách thêm cột không?”. Hãy hỏi tiếp: **“Nếu sự thật nghiệp vụ thay đổi, mọi bản sao sẽ đúng trở lại bằng cơ chế nào, trong bao lâu, và ta biết điều đó nhờ phép kiểm tra nào?”** Câu trả lời quyết định tính bền vững của mô hình nhiều hơn bản thân cột được thêm vào.
