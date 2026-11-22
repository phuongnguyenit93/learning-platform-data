# Xây cơ sở dữ liệu quản lý đơn hàng với schema và ràng buộc

Một hệ thống quản lý đơn hàng cần lưu khách hàng, sản phẩm, tồn kho, đơn hàng, từng dòng hàng và thanh toán. Các dữ liệu này có quan hệ chặt chẽ: đơn hàng phải thuộc về một khách hàng, dòng hàng phải trỏ đến sản phẩm hợp lệ, số lượng phải dương, giá tại thời điểm mua phải được giữ lại và số lượng tồn kho không được âm. Nếu chỉ dựa vào code ứng dụng để kiểm tra, một lỗi ở một API, worker hoặc script quản trị có thể tạo dữ liệu không nhất quán.

PostgreSQL cho phép mô hình hóa các quy tắc này ngay trong database bằng schema, primary key, foreign key, unique constraint, check constraint, default, generated column và index. Transaction kết hợp các ràng buộc giúp nhiều thay đổi liên quan được commit hoặc rollback cùng nhau. Bài học này xây dựng một mô hình quản lý đơn hàng từ đầu, giải thích quyết định thiết kế và thực hành các thao tác tạo đơn, giữ tồn kho, thanh toán, truy vấn, kiểm thử và thay đổi schema an toàn.

## 1. Xác định yêu cầu và quy tắc nghiệp vụ

Trước khi tạo bảng, cần mô tả dữ liệu và các quy tắc mà hệ thống phải giữ đúng. Một mô hình cơ bản gồm sáu thực thể:

| Thực thể | Lưu thông tin | Quan hệ chính |
|---|---|---|
| customers | Khách hàng và email liên hệ | Một khách hàng có nhiều đơn hàng |
| products | SKU, tên, giá hiện tại và trạng thái kinh doanh | Một sản phẩm xuất hiện trong nhiều dòng đơn |
| inventory | Số lượng hàng có thể bán | Mỗi sản phẩm có một bản ghi tồn kho |
| orders | Đơn hàng, khách mua, trạng thái, tiền tệ và địa chỉ giao hàng | Một đơn hàng có nhiều dòng hàng và nhiều lần thanh toán |
| order_items | Sản phẩm, số lượng và giá được chụp tại thời điểm đặt | Mỗi dòng thuộc một đơn hàng và tham chiếu một sản phẩm |
| payments | Các lần yêu cầu hoặc ghi nhận thanh toán | Một đơn hàng có thể có nhiều lần thử thanh toán |

Các quy tắc nghiệp vụ ban đầu:

1. Mỗi khách hàng có một email không rỗng; email được so sánh không phân biệt chữ hoa và chữ thường.
2. Mỗi sản phẩm có SKU không rỗng; SKU không trùng theo cách viết hoa/thường.
3. Giá sản phẩm không âm. Một sản phẩm ngừng bán vẫn được giữ trong database để bảo toàn lịch sử đơn hàng.
4. Số lượng tồn kho không âm.
5. Đơn hàng phải thuộc một khách hàng tồn tại và có mã đơn duy nhất.
6. Mỗi dòng đơn có số lượng lớn hơn 0, giá tại thời điểm mua không âm và không lặp cùng một sản phẩm trong một đơn.
7. Đơn hàng lưu ảnh chụp tên, SKU và giá của sản phẩm tại thời điểm đặt. Thay đổi tên hoặc giá sản phẩm về sau không được làm thay đổi lịch sử đơn cũ.
8. Mỗi lần gửi yêu cầu tạo đơn có một idempotency key ổn định để client thử lại mà không tạo đơn trùng.
9. Các thao tác tạo đơn, giữ tồn kho và ghi dòng đơn phải nằm trong một transaction.
10. Thanh toán cần có mã tham chiếu từ nhà cung cấp để nhận diện callback hoặc webhook gửi lặp.

Đây là mô hình minh họa cho một cửa hàng dùng một loại tiền tệ trên mỗi đơn hàng. Nếu hệ thống cần nhiều kho, nhiều địa chỉ giao hàng, thuế theo vùng, coupon, hoàn hàng hoặc thanh toán nhiều loại tiền, có thể mở rộng bằng các bảng riêng. Không nên nhồi tất cả dữ liệu vào một bảng lớn hoặc một cột JSONB chỉ vì muốn giảm số bảng.

## 2. Thiết kế schema và quan hệ

Trong PostgreSQL, schema là namespace chứa các đối tượng như table, view, sequence, function và type. Tách bảng ứng dụng vào schema riêng giúp tránh xung đột tên với extension hoặc đối tượng của hệ thống, đồng thời hỗ trợ phân quyền theo nhóm đối tượng.

Tạo schema:

    CREATE SCHEMA shop;

Tên shop được dùng xuyên suốt bài học. Trong ứng dụng thực tế, schema có thể mang tên theo bounded context hoặc module nghiệp vụ, chẳng hạn sales, catalog hoặc commerce.

### Sơ đồ quan hệ

    customers 1 ─────── N orders
                           │
                           │ 1
                           │
                           N
                       order_items N ─────── 1 products
                                                   │
                                                   │ 1
                                                   │
                                                   1
                                               inventory

    orders 1 ─────── N payments

Mỗi đơn hàng có thể có nhiều dòng hàng. Một sản phẩm có thể xuất hiện trong nhiều đơn khác nhau. Bảng inventory giữ trạng thái số lượng hiện tại, còn order_items lưu dữ liệu lịch sử tại thời điểm mua. Bảng payments tách các lần thanh toán khỏi đơn hàng vì một đơn có thể có lần thử thất bại, lần thử thành công hoặc hoàn tiền.

### Chọn khóa chính

Các bảng sử dụng bigint GENERATED ALWAYS AS IDENTITY để PostgreSQL sinh khóa số tự tăng. Identity column là cách khai báo hiện đại, gắn với sequence do PostgreSQL quản lý. Khóa số nội bộ nhỏ gọn, thuận tiện cho foreign key và join.

Không nên dùng email, SKU hoặc order_number làm primary key vì các giá trị nghiệp vụ có thể thay đổi hoặc cần chuẩn hóa. Chúng vẫn có thể được bảo vệ bằng unique constraint hoặc unique index.

Có thể dùng UUID làm khóa chính nếu cần tạo ID ở nhiều node mà không phụ thuộc sequence trung tâm. Trong ví dụ này, UUID được dùng cho idempotency key vì key đại diện cho một ý định request từ client, còn khóa số vẫn phù hợp cho quan hệ nội bộ.

## 3. Tạo bảng khách hàng và sản phẩm

### Bảng customers

    CREATE TABLE shop.customers (
        customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        email text NOT NULL,
        full_name text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT customers_email_not_blank
            CHECK (btrim(email) <> ''),
        CONSTRAINT customers_name_not_blank
            CHECK (btrim(full_name) <> '')
    );

NOT NULL ngăn giá trị SQL NULL. CHECK ngăn chuỗi rỗng hoặc chỉ chứa khoảng trắng. Hai quy tắc này khác nhau: một chuỗi rỗng không phải NULL, vì vậy chỉ đặt NOT NULL là chưa đủ.

Email thường được xem là không phân biệt chữ hoa/thường trong nghiệp vụ đăng nhập. Ta tạo unique index trên biểu thức chuẩn hóa:

    CREATE UNIQUE INDEX customers_email_ci_uq
        ON shop.customers (lower(btrim(email)));

Index này vừa hỗ trợ tra cứu theo email đã chuẩn hóa, vừa ngăn hai bản ghi có User@example.com và user@example.com. Một unique constraint thông thường trên cột text sẽ phân biệt hai chuỗi đó theo phép so sánh mặc định.

Trong hệ thống lớn, cần xác định chính sách chuẩn hóa email rõ ràng. Không nên tự ý thay đổi các quy tắc Unicode hoặc xử lý phần local-part/domain nếu nghiệp vụ chưa quy định.

### Bảng products

    CREATE TABLE shop.products (
        product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        sku text NOT NULL,
        product_name text NOT NULL,
        description text,
        unit_price numeric(12, 2) NOT NULL,
        currency char(3) NOT NULL DEFAULT 'VND',
        is_active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT products_sku_not_blank
            CHECK (btrim(sku) <> ''),
        CONSTRAINT products_name_not_blank
            CHECK (btrim(product_name) <> ''),
        CONSTRAINT products_price_nonnegative
            CHECK (unit_price >= 0),
        CONSTRAINT products_currency_format
            CHECK (btrim(currency) ~ '^[A-Z]{3}$')
    );

    CREATE UNIQUE INDEX products_sku_ci_uq
        ON shop.products (lower(btrim(sku)));

numeric(12,2) lưu giá trị thập phân chính xác đến hai chữ số sau dấu phẩy, phù hợp hơn kiểu floating point cho giá tiền. Không dùng real hoặc double precision cho số tiền cần đối chiếu chính xác vì chúng biểu diễn số nhị phân gần đúng.

is_active cho biết sản phẩm có được bán mới hay không. Khi sản phẩm đã xuất hiện trong đơn hàng, nên chuyển sang inactive thay vì xóa. Foreign key ở bảng order_items sẽ bảo vệ lịch sử tham chiếu.

currency được lưu để xác định đơn vị tiền của giá. Hệ thống thực tế cần xác thực rằng tiền tệ của sản phẩm tương thích với tiền tệ của đơn hàng trong transaction tạo đơn. Một CHECK constraint không thể truy vấn bảng khác để kiểm tra điều đó.

### Bảng inventory

    CREATE TABLE shop.inventory (
        product_id bigint PRIMARY KEY
            REFERENCES shop.products(product_id)
            ON DELETE RESTRICT,
        available_qty integer NOT NULL DEFAULT 0,
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT inventory_available_nonnegative
            CHECK (available_qty >= 0)
    );

Mỗi sản phẩm có tối đa một bản ghi tồn kho. Khóa chính product_id đồng thời là foreign key tới products. ON DELETE RESTRICT ngăn xóa sản phẩm khi còn bản ghi tồn kho tham chiếu.

Trong mô hình đơn giản này, available_qty là số lượng có thể bán. Nếu cần phân biệt hàng thực tế, hàng đã giữ, hàng đang vận chuyển và hàng lỗi, nên mở rộng thành các trường hoặc ledger tồn kho riêng, đồng thời định nghĩa invariant giữa các trạng thái.

## 4. Tạo bảng orders và order_items

### Bảng orders

    CREATE TABLE shop.orders (
        order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        order_number text NOT NULL UNIQUE,
        customer_id bigint NOT NULL
            REFERENCES shop.customers(customer_id)
            ON DELETE RESTRICT,
        status text NOT NULL DEFAULT 'pending',
        currency char(3) NOT NULL,
        shipping_address jsonb NOT NULL,
        idempotency_key uuid NOT NULL UNIQUE,
        request_hash bytea NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT orders_number_not_blank
            CHECK (btrim(order_number) <> ''),
        CONSTRAINT orders_status_valid
            CHECK (status IN (
                'pending',
                'paid',
                'processing',
                'shipped',
                'completed',
                'cancelled'
            )),
        CONSTRAINT orders_currency_format
            CHECK (btrim(currency) ~ '^[A-Z]{3}$'),
        CONSTRAINT orders_shipping_address_object
            CHECK (jsonb_typeof(shipping_address) = 'object'),
        CONSTRAINT orders_request_hash_sha256
            CHECK (octet_length(request_hash) = 32)
    );

Một đơn hàng cần giữ địa chỉ giao hàng tại thời điểm đặt. Nếu chỉ lưu customer_id rồi join tới địa chỉ hiện tại của khách, việc khách thay đổi địa chỉ có thể khiến đơn cũ hiển thị sai nơi giao. shipping_address là JSONB có cấu trúc để lưu snapshot của địa chỉ; các trường có cấu trúc cố định và cần truy vấn thường xuyên có thể được tách thành các cột riêng hoặc bảng snapshot.

idempotency_key nhận diện một yêu cầu tạo đơn. request_hash lưu SHA-256 của payload nghiệp vụ đã chuẩn hóa. Khi client gửi lại cùng key, ứng dụng so sánh hash để xác nhận đó là cùng một yêu cầu. Cùng key nhưng payload khác phải bị từ chối.

CHECK trên status chỉ giới hạn tập giá trị hợp lệ. Nó không bảo đảm chuyển trạng thái đúng quy trình. Ví dụ, CHECK cho phép cả pending và completed, nhưng không ngăn ứng dụng chuyển thẳng từ pending sang completed. Quy tắc chuyển trạng thái cần được bảo vệ bằng câu UPDATE có điều kiện, service transaction hoặc trigger nếu muốn áp dụng tập trung ở database.

### Bảng order_items

    CREATE TABLE shop.order_items (
        order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        order_id bigint NOT NULL
            REFERENCES shop.orders(order_id)
            ON DELETE CASCADE,
        product_id bigint NOT NULL
            REFERENCES shop.products(product_id)
            ON DELETE RESTRICT,
        sku_snapshot text NOT NULL,
        product_name_snapshot text NOT NULL,
        quantity integer NOT NULL,
        unit_price numeric(12, 2) NOT NULL,
        line_total numeric(22, 2)
            GENERATED ALWAYS AS (
                quantity::numeric * unit_price
            ) STORED,
        CONSTRAINT order_items_quantity_positive
            CHECK (quantity > 0),
        CONSTRAINT order_items_price_nonnegative
            CHECK (unit_price >= 0),
        CONSTRAINT order_items_unique_product
            UNIQUE (order_id, product_id)
    );

Các cột snapshot bảo toàn thông tin sản phẩm tại thời điểm mua. unit_price trong products là giá hiện tại; unit_price trong order_items là giá đã chốt cho đơn cụ thể. Không join về giá hiện tại để tính lại giá của đơn cũ.

line_total là generated column STORED. PostgreSQL tự tính giá trị từ quantity và unit_price khi insert hoặc update. Ứng dụng không thể ghi trực tiếp vào cột generated. Điều này giúp tránh trường hợp client gửi quantity và unit_price nhưng tự gửi line_total sai.

Ràng buộc UNIQUE (order_id, product_id) quy định một sản phẩm chỉ có một dòng trong mỗi đơn. Nếu giao diện cho phép nhiều dòng cùng sản phẩm với thuộc tính khác nhau, chẳng hạn size hoặc customization, cần mở rộng khóa duy nhất bằng các thuộc tính phân biệt hoặc dùng line number.

ON DELETE CASCADE ở order_items có nghĩa xóa order sẽ xóa các dòng con. Với hệ thống thương mại điện tử, thường nên hủy đơn hoặc lưu trạng thái lưu trữ thay vì xóa lịch sử. Cascade ở đây minh họa quan hệ phụ thuộc; chính sách quyền ứng dụng có thể cấm DELETE trên orders. Các bảng lịch sử thanh toán vẫn có thể khiến thao tác xóa bị chặn.

## 5. Tạo bảng payments

Một đơn hàng có thể có nhiều lần thử thanh toán. Không nên ghi đè trạng thái một lần thử cũ bằng lần thử mới vì lịch sử đối soát và callback cần giữ được.

    CREATE TABLE shop.payments (
        payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        order_id bigint NOT NULL
            REFERENCES shop.orders(order_id)
            ON DELETE RESTRICT,
        provider text NOT NULL,
        provider_reference text,
        amount numeric(14, 2) NOT NULL,
        currency char(3) NOT NULL,
        status text NOT NULL DEFAULT 'pending',
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT payments_provider_not_blank
            CHECK (btrim(provider) <> ''),
        CONSTRAINT payments_amount_nonnegative
            CHECK (amount >= 0),
        CONSTRAINT payments_currency_format
            CHECK (btrim(currency) ~ '^[A-Z]{3}$'),
        CONSTRAINT payments_status_valid
            CHECK (status IN (
                'pending',
                'authorized',
                'captured',
                'failed',
                'refunded'
            )),
        CONSTRAINT payments_provider_reference_unique
            UNIQUE (provider, provider_reference)
    );

Unique constraint trên (provider, provider_reference) ngăn cùng một giao dịch do nhà cung cấp phát hành bị ghi nhận hai lần. PostgreSQL cho phép nhiều NULL trong unique constraint mặc định, nên nhiều payment chưa có provider_reference vẫn có thể tồn tại. Nếu nghiệp vụ yêu cầu mọi giao dịch đã được gửi tới provider phải có reference, hãy kiểm tra điều kiện đó trong luồng cập nhật hoặc dùng constraint phù hợp.

Một callback từ cổng thanh toán có thể được gửi nhiều lần. Ứng dụng cần dùng provider reference làm khóa deduplication, kiểm tra trạng thái hiện tại và thực hiện cập nhật trong transaction. Không cộng tiền hoặc đánh dấu đơn hàng đã thanh toán nhiều lần chỉ vì webhook được nhận nhiều lần.

## 6. Tạo index cho truy vấn thường dùng

Primary key và unique constraint tạo index tương ứng. Các foreign key ở phía tham chiếu không tự động được PostgreSQL tạo index. Vì vậy, cần xem các truy vấn và thao tác xóa/cập nhật khóa cha để quyết định index.

    CREATE INDEX orders_customer_created_idx
        ON shop.orders (customer_id, created_at DESC);

    CREATE INDEX orders_status_created_idx
        ON shop.orders (status, created_at DESC);

    CREATE INDEX order_items_product_idx
        ON shop.order_items (product_id);

    CREATE INDEX payments_order_idx
        ON shop.payments (order_id);

Index orders_customer_created_idx hỗ trợ lấy đơn gần nhất của một khách hàng. Index status hỗ trợ trang quản trị lọc đơn theo trạng thái và thời gian. Index product_id giúp tra cứu các đơn có chứa sản phẩm hoặc kiểm tra các dòng tham chiếu khi cần thao tác với sản phẩm. Index payments_order hỗ trợ lấy lịch sử thanh toán của một đơn.

Unique index (order_id, product_id) trên order_items đã có cột order_id ở vị trí đầu nên có thể hỗ trợ truy vấn theo order_id. Không cần tạo thêm index đơn trên order_id nếu workload không cho thấy lợi ích riêng.

Index tăng tốc truy vấn đọc nhưng làm tăng chi phí INSERT, UPDATE, DELETE và dung lượng. Không tạo index cho mọi cột. Hãy căn cứ truy vấn thực tế, cardinality, selectivity, tần suất ghi và kế hoạch thực thi.

Xem index hiện có:

    SELECT
        schemaname,
        tablename,
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname = 'shop'
    ORDER BY tablename, indexname;

Dùng EXPLAIN để xem PostgreSQL dự kiến thực hiện truy vấn như thế nào:

    EXPLAIN
    SELECT order_id, order_number, status, created_at
    FROM shop.orders
    WHERE customer_id = 42
    ORDER BY created_at DESC
    LIMIT 20;

EXPLAIN ANALYZE thực thi câu lệnh để đo thời gian và số dòng thực tế. Chỉ dùng trên truy vấn an toàn trong môi trường phù hợp; với câu UPDATE/DELETE, nó thực sự thực hiện thay đổi trừ khi được đặt trong transaction rồi ROLLBACK.

## 7. Kiểm tra schema và constraint sau khi tạo

Có thể dùng psql để xem cấu trúc bảng:

    \dn
    \dt shop.*
    \d shop.orders
    \d shop.order_items

Các lệnh bắt đầu bằng dấu gạch chéo ngược là meta-command của psql, không phải SQL gửi trực tiếp tới PostgreSQL server.

Để truy vấn constraint qua catalog:

    SELECT
        conrelid::regclass AS table_name,
        conname,
        contype,
        pg_get_constraintdef(oid) AS definition,
        convalidated
    FROM pg_constraint
    WHERE connamespace = 'shop'::regnamespace
    ORDER BY conrelid::regclass::text, conname;

contype thường có các giá trị p (primary key), f (foreign key), u (unique), c (check) và x (exclusion). convalidated cho biết constraint đã được kiểm tra trên toàn bộ dữ liệu hiện có hay chưa. Đây là thông tin hữu ích khi triển khai migration bằng NOT VALID.

Xem cột, kiểu dữ liệu và nullability:

    SELECT
        table_name,
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_schema = 'shop'
    ORDER BY table_name, ordinal_position;

Việc kiểm tra catalog nên trở thành một phần của migration test hoặc deployment verification. Không nên chỉ dựa vào việc migration tool báo thành công.

## 8. Thêm dữ liệu mẫu và kiểm tra các ràng buộc

Tạo một khách hàng:

    INSERT INTO shop.customers (email, full_name)
    VALUES ('lan@example.com', 'Nguyen Thi Lan')
    RETURNING customer_id;

Tạo sản phẩm:

    INSERT INTO shop.products (
        sku, product_name, unit_price, currency
    )
    VALUES
        ('KB-001', 'Ban phim co', 850000.00, 'VND'),
        ('MS-002', 'Chuot khong day', 420000.00, 'VND')
    RETURNING product_id, sku;

Giả sử hai sản phẩm được trả về ID 1 và 2 trong database thử nghiệm, tạo tồn kho:

    INSERT INTO shop.inventory (product_id, available_qty)
    VALUES
        (1, 50),
        (2, 80);

Trong môi trường dùng chung, không nên giả định identity luôn bắt đầu từ 1. Hãy lấy ID thực tế từ RETURNING hoặc tra cứu bằng SKU. Giá trị ID trong ví dụ chỉ để minh họa.

Thử vi phạm các quy tắc:

    -- quantity phải lớn hơn 0
    INSERT INTO shop.order_items (
        order_id, product_id, sku_snapshot,
        product_name_snapshot, quantity, unit_price
    )
    VALUES (1, 1, 'KB-001', 'Ban phim co', 0, 850000.00);

Câu lệnh trên phải thất bại với check constraint order_items_quantity_positive.

    -- product_id phải tham chiếu sản phẩm tồn tại
    INSERT INTO shop.inventory (product_id, available_qty)
    VALUES (999999, 10);

Câu lệnh này phải thất bại do foreign key.

    -- Email không phân biệt chữ hoa/thường
    INSERT INTO shop.customers (email, full_name)
    VALUES ('LAN@EXAMPLE.COM', 'Lan Duplicate');

Nếu email lan@example.com đã có, unique index biểu thức sẽ từ chối bản ghi trùng. SQLSTATE thường là 23505 (unique_violation).

Thử các trường hợp hợp lệ và không hợp lệ là cách kiểm tra constraint thực sự được thực thi ở database. Không chỉ kiểm thử validation trong form giao diện vì các luồng import, batch job và script quản trị có thể bỏ qua form.

## 9. Tạo đơn hàng trong một transaction

Tạo đơn là một quy trình gồm nhiều bước: nhận diện request, tạo header, kiểm tra sản phẩm, giữ tồn kho và ghi dòng hàng. Nếu một bước thất bại, các bước trước đó phải được rollback.

### Vì sao cần transaction?

Giả sử ứng dụng giảm tồn kho trước, sau đó insert order_items nhưng insert thất bại. Nếu hai thao tác không nằm trong cùng transaction, tồn kho có thể bị giảm dù không có đơn hàng. Tương tự, đơn hàng có thể tồn tại mà không có đủ dòng hàng nếu tiến trình dừng giữa các bước.

Transaction bảo đảm các thay đổi thuộc một đơn được commit cùng nhau hoặc rollback cùng nhau:

    BEGIN;

    -- Tạo order header.
    -- Giữ tồn kho.
    -- Ghi order_items.
    -- Kiểm tra kết quả.

    COMMIT;

Nếu bất kỳ bước nào không đạt, ứng dụng thực hiện ROLLBACK. Trong code ứng dụng, nên dùng transaction API của driver hoặc framework để bảo đảm rollback khi exception.

### Idempotency khi tạo đơn

Client tạo idempotency key một lần khi bắt đầu yêu cầu và gửi lại đúng key khi retry. Request hash được tính từ payload nghiệp vụ đã chuẩn hóa, gồm khách hàng, tiền tệ, địa chỉ và các dòng hàng. Không đưa request timestamp hoặc thông tin tracing thay đổi theo lần thử vào hash.

Tạo order header:

    INSERT INTO shop.orders (
        order_number,
        customer_id,
        status,
        currency,
        shipping_address,
        idempotency_key,
        request_hash
    )
    VALUES (
        $1, $2, 'pending', $3, $4::jsonb, $5, $6
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING order_id;

Nếu câu lệnh trả về một order_id, transaction hiện tại đã tạo được yêu cầu mới và có thể tiếp tục xử lý. Nếu không trả về dòng nào, ứng dụng đọc đơn đã tồn tại theo key:

    SELECT order_id, request_hash, status
    FROM shop.orders
    WHERE idempotency_key = $1;

Nếu hash trùng, đây là lần gửi lại cùng yêu cầu; trả kết quả hiện có theo chính sách API. Nếu hash khác, từ chối vì một key đã bị dùng cho payload khác. Với isolation READ COMMITTED, câu SELECT ở statement tiếp theo nhận snapshot mới và có thể thấy transaction đã commit đang giữ key. Ở isolation REPEATABLE READ hoặc SERIALIZABLE, xung đột đồng thời có thể dẫn đến serialization failure; khi đó cần retry toàn transaction theo chính sách.

Không tiếp tục giữ tồn kho hoặc ghi order_items nếu INSERT header không tạo được dòng mới. Nếu không, một request trùng vẫn có thể trừ kho lần nữa.

### Giữ tồn kho an toàn khi có request đồng thời

Không nên làm theo hai bước tách rời kiểu:

1. SELECT available_qty.
2. Nếu đủ thì UPDATE available_qty = available_qty - quantity.

Hai request có thể cùng đọc một số lượng cũ trước khi request nào cập nhật. Cả hai đều nghĩ còn hàng và cùng bán vượt tồn.

Hãy dùng một UPDATE có điều kiện nguyên tử:

    UPDATE shop.inventory
    SET available_qty = available_qty - $1,
        updated_at = now()
    WHERE product_id = $2
      AND $1 > 0
      AND available_qty >= $1
    RETURNING product_id, available_qty;

Nếu trả về một dòng, số lượng đã được giữ thành công. Nếu không trả về dòng nào, sản phẩm không tồn tại trong inventory hoặc không đủ hàng hoặc quantity không hợp lệ. Ứng dụng cần phân biệt các trường hợp nếu thông báo nghiệp vụ yêu cầu, nhưng trong cả ba trường hợp phải rollback transaction tạo đơn.

PostgreSQL khóa hàng được cập nhật và kiểm tra điều kiện phù hợp khi xử lý concurrent update. CHECK (available_qty >= 0) là lớp bảo vệ bổ sung nếu có luồng ghi khác cố đưa tồn kho xuống số âm.

### Chụp giá và tên sản phẩm

Trong transaction tạo đơn, lấy thông tin sản phẩm từ database thay vì tin giá do client gửi. Có thể đọc và khóa hàng sản phẩm trước khi tạo dòng:

    SELECT product_id, sku, product_name, unit_price, currency
    FROM shop.products
    WHERE product_id = $1
      AND is_active
    FOR SHARE;

Sau khi xác nhận sản phẩm tồn tại, đang bán và có currency phù hợp với đơn, ứng dụng giữ tồn kho và insert order_items bằng giá trị vừa đọc:

    INSERT INTO shop.order_items (
        order_id,
        product_id,
        sku_snapshot,
        product_name_snapshot,
        quantity,
        unit_price
    )
    VALUES ($1, $2, $3, $4, $5, $6);

FOR SHARE giữ khóa chia sẻ trên hàng sản phẩm đến khi transaction kết thúc, ngăn một transaction khác cập nhật hoặc xóa hàng đó trong thời gian chụp giá. Khi xử lý nhiều sản phẩm, hãy lấy khóa theo thứ tự product_id tăng dần để giảm khả năng deadlock.

Mỗi sản phẩm phải được kiểm tra và giữ tồn kho. Nếu một dòng không đủ hàng hoặc không còn active, rollback toàn bộ đơn. Không commit một đơn có một nửa số dòng hàng nếu nghiệp vụ yêu cầu đặt hàng nguyên tử.

### Quy trình tổng quát ở tầng ứng dụng

Pseudocode:

    BEGIN;

    1. Tính request_hash từ payload chuẩn hóa.
    2. INSERT orders với idempotency_key.
    3. Nếu key đã tồn tại:
         đọc order hiện có;
         so sánh request_hash;
         nếu trùng, trả kết quả cũ;
         nếu khác, trả lỗi xung đột key;
         không thay đổi tồn kho.
    4. Chuẩn hóa các dòng hàng, gộp sản phẩm lặp nếu mô hình yêu cầu.
    5. Xử lý sản phẩm theo product_id tăng dần:
         đọc sản phẩm FOR SHARE;
         kiểm tra is_active và currency;
         UPDATE inventory có điều kiện;
         nếu không đủ hàng, ROLLBACK;
         INSERT order_items với giá và tên snapshot.
    6. COMMIT;

    Nếu có lỗi:
         ROLLBACK;
         phân loại lỗi;
         chỉ retry theo chính sách và dùng lại cùng idempotency_key.

Pseudocode thể hiện thứ tự nghiệp vụ. Trong ứng dụng thực tế, cần xác định rõ cách trả kết quả khi key đã tồn tại, cách xử lý order_number xung đột, deadline và retry toàn transaction. Không retry bằng một idempotency key mới.

## 10. Tính tổng đơn và truy vấn lịch sử

Tổng đơn có thể được tính từ các dòng hàng:

    SELECT
        o.order_id,
        o.order_number,
        o.status,
        o.currency,
        o.created_at,
        COALESCE(sum(oi.line_total), 0) AS order_total
    FROM shop.orders AS o
    LEFT JOIN shop.order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_id = $1
    GROUP BY
        o.order_id,
        o.order_number,
        o.status,
        o.currency,
        o.created_at;

Không dùng CHECK trên orders để kiểm tra tổng của order_items vì CHECK constraint không được thiết kế để truy vấn các hàng hoặc bảng khác. Nếu cần lưu tổng tiền đã chốt, hãy tính và ghi trong cùng transaction tạo đơn, rồi có cơ chế đối soát với tổng dòng hàng. Nếu tổng chỉ là dữ liệu dẫn xuất, tính khi truy vấn hoặc tạo view để tránh lưu trùng dữ liệu.

### Danh sách đơn của một khách hàng

    SELECT
        order_id,
        order_number,
        status,
        currency,
        created_at
    FROM shop.orders
    WHERE customer_id = $1
    ORDER BY created_at DESC
    LIMIT 50;

Index (customer_id, created_at DESC) hỗ trợ mẫu truy vấn này.

### Chi tiết một đơn

    SELECT
        oi.order_item_id,
        oi.sku_snapshot,
        oi.product_name_snapshot,
        oi.quantity,
        oi.unit_price,
        oi.line_total
    FROM shop.order_items AS oi
    WHERE oi.order_id = $1
    ORDER BY oi.order_item_id;

Dùng snapshot để hiển thị lịch sử. Nếu cần thêm thông tin sản phẩm hiện tại như ảnh hoặc trạng thái active, có thể join sang products nhưng không thay thế các giá trị lịch sử.

### Lịch sử thanh toán

    SELECT
        payment_id,
        provider,
        provider_reference,
        amount,
        currency,
        status,
        created_at
    FROM shop.payments
    WHERE order_id = $1
    ORDER BY created_at, payment_id;

Mỗi payment là một lần thử hoặc một sự kiện thanh toán. Việc tổng hợp tiền đã capture cần dựa trên trạng thái và quy tắc hoàn tiền rõ ràng; không cộng mọi payment row một cách mù quáng.

## 11. Cập nhật trạng thái đơn hàng và ghi nhận thanh toán

CHECK constraint bảo đảm status thuộc danh sách cho phép, nhưng chuyển trạng thái phải có điều kiện. Ví dụ, chỉ chuyển từ pending sang paid nếu trạng thái hiện tại vẫn là pending:

    UPDATE shop.orders
    SET status = 'paid'
    WHERE order_id = $1
      AND status = 'pending'
    RETURNING order_id, status;

Nếu không trả về dòng nào, đơn có thể đã được thanh toán, đã hủy hoặc ở trạng thái không phù hợp. Ứng dụng cần đọc trạng thái hiện tại và xử lý idempotently.

Khi nhận webhook từ provider:

1. Xác thực chữ ký và nguồn gửi.
2. Xác định provider_reference và đơn hàng tương ứng.
3. Bắt đầu transaction.
4. Ghi nhận hoặc tra cứu payment theo provider/reference.
5. Nếu event đã xử lý, không lặp lại tác động.
6. Kiểm tra amount, currency và trạng thái đơn.
7. Cập nhật payment và order theo điều kiện.
8. Commit; nếu cần phát event cho hệ thống khác, ghi outbox trong cùng transaction.

Unique constraint (provider, provider_reference) giúp chặn một callback bị ghi nhận thành hai payment record. Tuy nhiên, nó không tự bảo đảm mọi chuyển trạng thái nghiệp vụ hợp lệ. Cần kiểm tra amount/currency và quy tắc trạng thái trong transaction.

Nếu gọi API thanh toán bên ngoài, không giữ transaction PostgreSQL mở trong suốt thời gian chờ HTTP. Có thể tạo payment intent và outbox event trong transaction, sau đó worker gọi provider bằng idempotency key ổn định. Khi provider trả kết quả, worker cập nhật database bằng transaction khác. Mô hình này tránh giữ connection và lock lâu, đồng thời cho phép retry an toàn.

## 12. Ràng buộc dữ liệu: chọn đúng loại

PostgreSQL cung cấp nhiều cơ chế bảo vệ dữ liệu. Chọn đúng loại giúp quy tắc dễ đọc, dễ kiểm thử và khó bị bỏ qua.

| Cơ chế | Dùng khi | Ví dụ trong schema |
|---|---|---|
| PRIMARY KEY | Mỗi hàng cần định danh duy nhất, không NULL | customer_id, order_id |
| FOREIGN KEY | Giá trị phải tham chiếu hàng tồn tại | orders.customer_id, order_items.product_id |
| UNIQUE | Không cho phép giá trị hoặc tổ hợp trùng | order_number, idempotency_key |
| CHECK | Điều kiện trên chính hàng đang ghi | quantity > 0, unit_price >= 0 |
| NOT NULL | Bắt buộc có giá trị | email, status |
| DEFAULT | Giá trị mặc định khi caller bỏ qua cột | created_at, status |
| GENERATED | Giá trị được tính từ các cột cùng hàng | line_total |
| EXCLUDE | Ngăn các giá trị/range xung đột theo toán tử | Có thể dùng cho lịch đặt chỗ hoặc khoảng hiệu lực |

### CHECK không thay thế foreign key

Không viết trigger hoặc CHECK phức tạp để tự kiểm tra sự tồn tại của customer nếu foreign key đã biểu diễn đúng quan hệ. Foreign key được PostgreSQL kiểm tra nhất quán khi insert/update và xử lý các hành vi xóa/cập nhật theo khai báo.

### CHECK không kiểm tra tổng nhiều dòng

Điều kiện như “tổng line_total của các order_items không vượt hạn mức khách hàng” liên quan nhiều hàng. CHECK không hỗ trợ truy vấn bảng khác một cách an toàn. Dùng transaction, khóa phù hợp, trigger có thiết kế đồng thời đúng hoặc một mô hình dữ liệu khác để bảo đảm invariant đó.

### DEFERRABLE khi cần kiểm tra cuối transaction

Một số UNIQUE, PRIMARY KEY, FOREIGN KEY hoặc EXCLUDE constraint có thể được khai báo DEFERRABLE để trì hoãn kiểm tra đến cuối transaction. Điều này hữu ích cho một số thao tác đổi khóa hoặc cập nhật quan hệ nhiều bước. CHECK và NOT NULL không có cơ chế DEFERRABLE tương tự.

Không trì hoãn constraint nếu không có nhu cầu rõ ràng. Kiểm tra ngay thường giúp phát hiện lỗi sớm hơn.

### ON DELETE và ON UPDATE

- RESTRICT/NO ACTION: ngăn xóa hoặc cập nhật hàng cha khi còn hàng con tham chiếu, tùy thời điểm kiểm tra constraint.
- CASCADE: tự động xóa hoặc cập nhật hàng con theo hàng cha.
- SET NULL: đặt khóa ngoại ở hàng con thành NULL; chỉ phù hợp nếu cột cho phép NULL và nghiệp vụ chấp nhận.
- SET DEFAULT: đặt giá trị mặc định; giá trị đó vẫn phải thỏa foreign key nếu constraint còn áp dụng.

Chọn hành vi theo vòng đời dữ liệu. Với lịch sử đơn hàng, thường nên giữ khách hàng và sản phẩm tham chiếu bằng RESTRICT, dùng trạng thái inactive hoặc soft delete. Cascade phù hợp hơn với dữ liệu con thực sự không có ý nghĩa độc lập khi hàng cha bị xóa.

## 13. Kiểm thử ràng buộc và các trường hợp biên

Một bộ kiểm thử schema cần bao gồm cả trường hợp hợp lệ, vi phạm và cạnh tranh đồng thời.

### Kiểm thử NOT NULL và CHECK

- Insert khách hàng không có email: phải thất bại.
- Insert email chỉ có khoảng trắng: phải thất bại.
- Insert sản phẩm có giá âm: phải thất bại.
- Insert tồn kho âm: phải thất bại.
- Insert dòng đơn có quantity bằng 0 hoặc âm: phải thất bại.
- Insert payment có amount âm: phải thất bại.

### Kiểm thử UNIQUE

- Tạo hai khách hàng có email khác chữ hoa/thường nhưng cùng địa chỉ chuẩn hóa: lần thứ hai phải thất bại.
- Tạo hai sản phẩm cùng SKU không phân biệt chữ hoa/thường: lần thứ hai phải thất bại.
- Tạo hai đơn cùng order_number: lần thứ hai phải thất bại.
- Tạo hai đơn với cùng idempotency key: chỉ một đơn được tạo; request lặp phải đọc lại đơn hiện có.
- Tạo hai payment cùng provider và provider_reference: bản ghi thứ hai phải bị từ chối.

### Kiểm thử FOREIGN KEY

- Tạo order với customer_id không tồn tại: thất bại.
- Tạo order_item với order_id hoặc product_id không tồn tại: thất bại.
- Xóa sản phẩm đã có order_item: bị RESTRICT.
- Xóa khách hàng đã có đơn hàng: bị RESTRICT.
- Xóa order có order_items: các dòng con bị CASCADE theo thiết kế minh họa; kiểm tra chính sách ứng dụng có cho phép thao tác này không.

### Kiểm thử transaction rollback

Bắt đầu transaction, giảm tồn kho rồi cố insert dòng đơn không hợp lệ. Rollback và xác nhận số lượng tồn kho trở lại giá trị ban đầu. Kiểm tra cả đơn hàng header không còn tồn tại. Điều này chứng minh các bước nằm trong cùng transaction.

### Kiểm thử cạnh tranh tồn kho

Giả sử inventory.available_qty = 5. Mở hai session và đồng thời thử đặt quantity = 4 cho cùng sản phẩm. Dùng UPDATE có điều kiện:

    UPDATE shop.inventory
    SET available_qty = available_qty - 4
    WHERE product_id = 1
      AND available_qty >= 4
    RETURNING available_qty;

Chỉ một session có thể giữ được 4 đơn vị. Session còn lại phải chờ khóa, sau đó điều kiện được đánh giá trên giá trị mới và không trả về hàng vì chỉ còn 1. Kết quả tồn kho không âm và không thể bán tổng cộng 8 đơn vị từ số lượng ban đầu là 5.

### Kiểm thử request lặp

Gửi cùng idempotency key và payload đồng thời từ nhiều client. Xác nhận chỉ một order header được tạo và chỉ một lần giữ tồn kho. Gửi lại key với payload khác và xác nhận API từ chối. Đừng chỉ kiểm tra HTTP response; hãy truy vấn orders, order_items và inventory để xác nhận trạng thái cuối.

### Kiểm thử callback thanh toán lặp

Gửi lại cùng webhook nhiều lần. Xác nhận chỉ có một payment theo provider/reference và order không bị cập nhật hoặc phát event nhiều lần. Nếu có outbox, kiểm tra event được deduplicate ở consumer.

## 14. Tổ chức migration schema an toàn

Schema sẽ thay đổi khi sản phẩm phát triển. Migration cần có phiên bản, thứ tự, khả năng chạy lặp theo công cụ triển khai và kế hoạch tương thích với ứng dụng đang chạy.

### Thêm cột mới

Nếu cần thêm phone_number có thể NULL ban đầu:

    ALTER TABLE shop.customers
    ADD COLUMN phone_number text;

Ứng dụng phiên bản cũ vẫn có thể hoạt động vì cột mới không bắt buộc. Sau khi code mới ghi dữ liệu, có thể backfill và thêm constraint theo từng bước.

### Thêm CHECK constraint cho bảng đã có dữ liệu

Có thể thêm constraint NOT VALID để tránh quét và xác thực toàn bộ dữ liệu ngay tại thời điểm ADD:

    ALTER TABLE shop.products
    ADD CONSTRAINT products_price_nonnegative_v2
    CHECK (unit_price >= 0) NOT VALID;

Constraint NOT VALID vẫn được áp dụng với các hàng được insert hoặc update sau đó, nhưng chưa kiểm tra toàn bộ dữ liệu cũ. Sau khi sửa dữ liệu vi phạm, chạy:

    ALTER TABLE shop.products
    VALIDATE CONSTRAINT products_price_nonnegative_v2;

VALIDATE kiểm tra dữ liệu hiện có mà không cần giữ lock mạnh như một số thao tác ALTER TABLE khác. Vẫn cần đánh giá lock, tải và thời gian thực thi theo kích thước bảng.

### Thêm foreign key cho bảng lớn

Tương tự, có thể thêm foreign key NOT VALID rồi VALIDATE sau khi xử lý dữ liệu mồ côi:

    ALTER TABLE shop.order_items
    ADD CONSTRAINT order_items_product_fk_v2
    FOREIGN KEY (product_id)
    REFERENCES shop.products(product_id)
    NOT VALID;

    ALTER TABLE shop.order_items
    VALIDATE CONSTRAINT order_items_product_fk_v2;

### Tạo index trên bảng đang phục vụ traffic

CREATE INDEX CONCURRENTLY giảm thời gian chặn thao tác ghi so với tạo index thông thường trên bảng lớn, nhưng có chi phí I/O và có thể kéo dài. Lệnh này không được chạy bên trong transaction block:

    CREATE INDEX CONCURRENTLY orders_created_idx
        ON shop.orders (created_at DESC);

Nếu tạo index concurrently thất bại, có thể còn lại index invalid. Hãy kiểm tra catalog và xử lý index đó trước khi chạy lại. Migration tool cần hỗ trợ đánh dấu migration không transactional cho câu lệnh này.

### Expand-contract

Khi đổi tên hoặc thay kiểu cột đang được ứng dụng sử dụng, triển khai theo nhiều giai đoạn:

1. Expand: thêm cột mới hoặc cấu trúc mới, giữ cột cũ.
2. Deploy code tương thích cả hai dạng hoặc dual-write theo quy trình có kiểm soát.
3. Backfill dữ liệu cũ sang cấu trúc mới theo batch.
4. Kiểm tra parity và chuyển đọc sang cột mới.
5. Ngừng ghi cột cũ khi mọi instance ứng dụng đã được nâng cấp.
6. Contract: xóa cột cũ trong một migration riêng sau khi xác minh không còn dependency.

Không gộp thêm cột, backfill, chuyển ứng dụng và drop cột vào một thay đổi lớn khiến rollback khó khăn.

## 15. Phân quyền theo schema

Không nên để ứng dụng kết nối bằng superuser hoặc role sở hữu schema. Tách role sở hữu đối tượng khỏi role runtime:

    CREATE ROLE shop_owner NOLOGIN;
    CREATE ROLE shop_app LOGIN;

    ALTER SCHEMA shop OWNER TO shop_owner;

    GRANT USAGE ON SCHEMA shop TO shop_app;

    GRANT SELECT, INSERT, UPDATE
    ON shop.customers, shop.products, shop.inventory,
       shop.orders, shop.order_items, shop.payments
    TO shop_app;

    GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA shop
    TO shop_app;

Đây là ví dụ khởi tạo trong môi trường mới. Nếu role hoặc schema đã tồn tại, cần kiểm tra trạng thái trước khi chạy; không chạy lặp CREATE ROLE một cách mù quáng. Cấp quyền cụ thể theo use case: worker thanh toán có thể chỉ cần đọc đơn và cập nhật payments/orders; service catalog có thể cập nhật products nhưng không cần quyền trên payments.

Để quyền sequence áp dụng cho đối tượng tạo về sau, owner có thể cấu hình default privileges:

    ALTER DEFAULT PRIVILEGES
    FOR ROLE shop_owner
    IN SCHEMA shop
    GRANT SELECT, INSERT, UPDATE ON TABLES TO shop_app;

    ALTER DEFAULT PRIVILEGES
    FOR ROLE shop_owner
    IN SCHEMA shop
    GRANT USAGE, SELECT ON SEQUENCES TO shop_app;

Default privileges chỉ áp dụng cho đối tượng được tạo bởi role được chỉ định và sau khi lệnh được thiết lập. Nếu migration chạy dưới role khác, cần cấu hình tương ứng.

Không cấp DELETE nếu service không cần xóa lịch sử. Cũng không cấp CREATE trên schema cho role runtime. Hãy bảo đảm search_path của ứng dụng được cấu hình có chủ đích; tránh để schema do user không tin cậy kiểm soát xuất hiện trước schema chứa function hoặc object nhạy cảm.

## 16. Các lỗi thiết kế thường gặp

**Đặt tất cả dữ liệu vào một bảng orders.** Lặp email, tên sản phẩm và địa chỉ ở nhiều dòng gây bất thường khi cập nhật. Tách thực thể theo quan hệ và lưu snapshot ở nơi cần bảo toàn lịch sử.

**Dùng giá hiện tại để hiển thị đơn cũ.** Giá sản phẩm có thể thay đổi. order_items phải lưu giá đã chốt tại thời điểm đặt.

**Dùng floating point cho tiền.** Sai số biểu diễn có thể làm tổng tiền và đối soát không chính xác. Dùng numeric với precision/scale phù hợp và xác định quy tắc làm tròn.

**Chỉ kiểm tra tồn kho bằng SELECT rồi UPDATE.** Hai request đồng thời có thể cùng bán một lượng hàng. Dùng UPDATE có điều kiện hoặc khóa hàng trong transaction.

**Dựa hoàn toàn vào validation của ứng dụng.** Batch job, script và API khác có thể ghi trực tiếp. Đưa các invariant cơ bản vào constraint của database.

**Dùng CHECK để kiểm tra bảng khác.** CHECK không phải công cụ cho tổng nhiều hàng hoặc quan hệ liên bảng. Dùng foreign key, transaction, trigger được thiết kế đúng hoặc mô hình dữ liệu khác.

**Xóa sản phẩm đã có đơn.** Có thể làm mất khả năng tra cứu lịch sử. Chuyển is_active thành false và giữ foreign key.

**Tạo index mọi cột.** Index làm tăng dung lượng và chi phí ghi. Dựa trên query plan và workload.

**Dùng idempotency key mới khi retry.** Mỗi lần thử sẽ trở thành một đơn hàng mới. Key phải ổn định theo ý định request.

**Không kiểm thử concurrency.** Một bộ test tuần tự không phát hiện overselling, deadlock hoặc request trùng. Cần test nhiều session đồng thời.

**Thêm constraint trên bảng lớn mà không có kế hoạch lock.** Migration có thể chặn traffic hoặc quét bảng lâu. Dùng chiến lược NOT VALID/VALIDATE và CREATE INDEX CONCURRENTLY khi phù hợp.

## 17. Bài thực hành tổng hợp

Hãy triển khai mô hình trong một database PostgreSQL thử nghiệm. Dùng schema shop và các bảng đã định nghĩa trong bài.

### Phần A: Dựng cấu trúc

1. Tạo schema và sáu bảng theo đúng thứ tự phụ thuộc.
2. Tạo các primary key, foreign key, unique index, CHECK constraint và index truy vấn.
3. Kiểm tra catalog để xác nhận mọi constraint tồn tại và đã validated.
4. Tạo role owner và role ứng dụng với quyền tối thiểu.

### Phần B: Nạp dữ liệu

1. Thêm ít nhất ba khách hàng và năm sản phẩm.
2. Tạo inventory cho từng sản phẩm.
3. Thử email và SKU trùng không phân biệt chữ hoa/thường.
4. Thử giá âm, quantity bằng 0, currency sai định dạng và foreign key không tồn tại.
5. Ghi nhận SQLSTATE và tên constraint của từng lỗi.

### Phần C: Tạo đơn

1. Tạo một đơn gồm hai sản phẩm.
2. Giữ tồn kho bằng UPDATE có điều kiện.
3. Lưu snapshot SKU, tên và giá vào order_items.
4. Tính tổng đơn bằng SUM(line_total).
5. Gửi lại cùng idempotency key và xác nhận không giữ tồn kho lần hai.
6. Gửi cùng key nhưng payload khác và xác nhận bị từ chối.

### Phần D: Kiểm thử cạnh tranh

1. Đặt tồn kho một sản phẩm bằng 5.
2. Mở hai session, đồng thời thử đặt 4 sản phẩm ở mỗi session.
3. Xác nhận chỉ một transaction thành công.
4. Kiểm tra tồn kho không âm và chỉ có đơn hợp lệ được commit.
5. Tạo tình huống hai transaction khóa nhiều sản phẩm theo thứ tự khác nhau, quan sát deadlock và sửa thứ tự lấy khóa.

### Phần E: Thanh toán

1. Tạo payment pending cho một đơn.
2. Mô phỏng callback thành công từ provider.
3. Gửi callback cùng provider_reference nhiều lần.
4. Xác nhận chỉ có một payment record và trạng thái order được cập nhật đúng một lần.
5. Thử callback có amount hoặc currency không khớp và xác nhận không đánh dấu đơn đã thanh toán.

### Phần F: Migration

1. Thêm một cột tùy chọn vào customers.
2. Backfill theo batch.
3. Thêm CHECK constraint NOT VALID, xử lý dữ liệu cũ và VALIDATE.
4. Tạo index CONCURRENTLY trên bảng thử nghiệm lớn.
5. Viết kế hoạch expand-contract cho một lần đổi tên cột.
6. Kiểm tra ứng dụng phiên bản cũ và mới trong thời gian migration.

## 18. Tiêu chí hoàn thành bài thực hành

Một mô hình quản lý đơn hàng đạt yêu cầu khi có thể chứng minh các điều sau:

- Các bảng có khóa chính rõ ràng và quan hệ được bảo vệ bằng foreign key.
- Email, SKU, order number, idempotency key và provider reference được bảo vệ theo quy tắc duy nhất.
- Các giá trị quantity, price, amount và available stock không thể âm hoặc bằng 0 trái quy tắc.
- Đơn hàng lưu snapshot sản phẩm và địa chỉ tại thời điểm tạo.
- Tạo đơn và giữ tồn kho nằm trong cùng transaction.
- Hai request đồng thời không thể bán vượt tồn kho.
- Retry cùng idempotency key không tạo đơn hoặc tác động tồn kho trùng.
- Callback thanh toán lặp không ghi nhận thanh toán nhiều lần.
- Các truy vấn chính có index phù hợp và được kiểm tra bằng EXPLAIN.
- Migration có chiến lược cho dữ liệu hiện có và traffic đang chạy.
- Role ứng dụng chỉ có quyền cần thiết.
- Các trường hợp hợp lệ, vi phạm constraint, rollback và concurrency đều được kiểm thử.

## 19. Tài liệu tham khảo PostgreSQL

Đối chiếu tài liệu theo major version đang triển khai để xác nhận cú pháp và hành vi cụ thể:

- PostgreSQL Documentation — Schemas: https://www.postgresql.org/docs/current/ddl-schemas.html
- PostgreSQL Documentation — Data Definition: https://www.postgresql.org/docs/current/ddl.html
- PostgreSQL Documentation — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL Documentation — Generated Columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL Documentation — Transactions: https://www.postgresql.org/docs/current/tutorial-transactions.html
- PostgreSQL Documentation — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL Documentation — Indexes: https://www.postgresql.org/docs/current/indexes.html
- PostgreSQL Documentation — CREATE INDEX: https://www.postgresql.org/docs/current/sql-createindex.html
- PostgreSQL Documentation — ALTER TABLE: https://www.postgresql.org/docs/current/sql-altertable.html
- PostgreSQL Documentation — Privileges: https://www.postgresql.org/docs/current/ddl-priv.html


