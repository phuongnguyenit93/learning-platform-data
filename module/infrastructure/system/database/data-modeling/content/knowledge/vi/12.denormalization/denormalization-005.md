# Ảnh chụp giá hoặc địa chỉ tại thời điểm giao dịch khác với bản sao để tăng tốc

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **ảnh chụp dữ liệu tại thời điểm giao dịch (transaction snapshot)** với **bản sao dữ liệu hiện hành dùng để tăng tốc đọc (read projection)**, dù hai trường có thể mang cùng giá trị lúc đầu.
- Xác định rõ **sự kiện chốt**, thời điểm hiệu lực, nguồn dữ liệu và quy tắc thay đổi đối với giá, tên sản phẩm, địa chỉ giao hàng và địa chỉ xuất hóa đơn.
- Thiết kế mô hình quan hệ lưu giá và địa chỉ đã xác nhận, cùng khóa, ràng buộc, giao dịch và cách kiểm tra phù hợp.
- Tránh lỗi lịch sử bị viết lại khi bảng sản phẩm, hồ sơ khách hàng hoặc bảng địa chỉ hiện hành thay đổi.
- Đánh giá lựa chọn lưu snapshot trong quan hệ, document, sự kiện hay mô hình phân tích; xử lý sửa đơn, hoàn tiền, nhập lại dữ liệu cũ và bảo vệ thông tin cá nhân.

Bài thuộc chương **Phi chuẩn hóa** của **DATABASE_DATA_MODELING**. Việc chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, khóa, chỉ mục và lược đồ vật lý cần dựa trên **ý nghĩa của dữ liệu theo thời gian**. Cách lưu một trường giống nhau về hình thức có thể là thiết kế đúng cho lịch sử giao dịch nhưng lại là dữ liệu dư thừa nguy hiểm khi dùng để sao chép trạng thái hiện hành.

## 1. Câu chuyện của một đơn hàng: cùng giá trị ban đầu, khác quy tắc sống

Ngày 01/10, khách xác nhận mua hai sản phẩm A với **đơn giá 150.000 VND**, giao tới **12 Đường Hoa, Quận X**. Hệ thống ghi một đơn hàng đã xác nhận. Ngày 20/10, cửa hàng tăng giá sản phẩm A lên **180.000 VND**. Ngày 25/10, khách đổi địa chỉ mặc định trong sổ địa chỉ sang **55 Đường Lá, Quận Y**.

Bây giờ có bốn câu hỏi khác nhau:

1. **Trang sản phẩm hôm nay** cần hiển thị giá mới 180.000 VND.
2. **Chi tiết đơn đã xác nhận** cần cho biết đơn giá đã chốt 150.000 VND, không phải giá hôm nay.
3. **Hồ sơ khách hàng** cần hiển thị địa chỉ hiện hành 55 Đường Lá.
4. **Bản ghi xác nhận đơn ngày 01/10** vẫn cần cho biết địa chỉ đã được khách chấp thuận khi đặt là 12 Đường Hoa.

Nếu truy vấn lịch sử đơn hàng bằng cách luôn JOIN về bảng **products.current_price** hoặc **customer_addresses** đang được chỉnh sửa, nội dung đơn cũ sẽ thay đổi ngược theo hồ sơ hiện tại. Lỗi này có thể ảnh hưởng hóa đơn, giải quyết tranh chấp, đối soát tiền, hỗ trợ khách hàng và việc chứng minh đơn đã được xác nhận với thông tin nào.

Ngược lại, khi sao chép tên danh mục hiện hành vào một bảng thẻ sản phẩm chỉ để tránh JOIN, bản sao **phải được cập nhật** khi tên danh mục đổi. Một trường cần **giữ nguyên**, trường kia cần **thay đổi theo nguồn**: đó là khác biệt nền tảng.

> **Snapshot giao dịch trả lời “Điều gì đã được xác nhận khi ấy?”; bản sao tối ưu đọc trả lời “Trạng thái hiện hành là gì, được làm mới đến đâu?”.**

## 2. Phân biệt theo ngữ nghĩa, không theo số lần dữ liệu xuất hiện

| Tiêu chí | Snapshot tại giao dịch | Bản sao để tăng tốc |
| --- | --- | --- |
| Câu hỏi nghiệp vụ | Giá, địa chỉ, điều khoản được chốt tại một sự kiện là gì? | Giá, tên, nhãn hoặc thông tin hiện hành là gì? |
| Ví dụ | **order_items.unit_price_at_confirmation**, **orders.ship_to_line1_at_confirmation** | **product_cards.current_price_display**, **product_cards.category_name_display** |
| Nguồn tạo ban đầu | Giá/địa chỉ đã được xác thực khi xác nhận, có thể kèm ưu đãi và lựa chọn khách hàng | Thuộc tính hiện hành của sản phẩm, danh mục, tác giả hoặc tài khoản |
| Khi nguồn hiện hành đổi | **Không tự đổi** bản đã chốt | **Phải làm mới** theo hợp đồng nhất quán |
| Nguồn chuẩn về sau | Bản ghi giao dịch đã xác nhận là nguồn chuẩn cho sự thật lịch sử đó | Bản ghi nghiệp vụ gốc vẫn là nguồn chuẩn |
| Kiểm chứng | So với điều khoản đã xác nhận, sự kiện hoặc chứng từ; không so với giá hiện tại | So với nguồn hiện hành, xét phiên bản và độ trễ |
| Cách sửa | Hiệu chỉnh có dấu vết, phiên bản hoặc sự kiện bù phù hợp chính sách | Làm mới, đối soát hoặc xây dựng lại từ nguồn |
| Rủi ro nếu cập nhật sai | Viết lại lịch sử, sai số tiền và chứng từ | Trả thông tin cũ, mất đồng bộ giữa các màn hình |
| Rủi ro nếu giữ quá lâu | Lưu thông tin cá nhân quá thời hạn cần thiết | Tồn tại bản sao cũ ngoài phạm vi quyền truy cập |

Cùng một cặp bảng có thể chứa **cả hai loại**:

- **catalog_products.current_price**: giá niêm yết đang có hiệu lực, có thể thay đổi.
- **order_items.unit_price_at_confirmation**: giá áp dụng cho dòng hàng khi xác nhận đơn, được giữ làm căn cứ lịch sử.
- **product_cards.current_price_display**: bản sao giá hiện hành phục vụ thẻ sản phẩm, có thể trễ nếu đồng bộ bất đồng bộ.

Không nên suy rằng cứ có hai cột cùng chứa “150000” là thiết kế vi phạm chuẩn hóa. Dữ liệu lịch sử và dữ liệu hiện hành là **hai sự thật với chiều thời gian khác nhau**. Một số thuộc tính snapshot vẫn tạo ra lặp vật lý, nhưng lý do lưu là **ngữ nghĩa của giao dịch**, không phải chỉ giảm chi phí JOIN.

## 3. Định nghĩa chính xác “tại thời điểm giao dịch”

Cụm “lúc mua” dễ gây hiểu nhầm. Trong luồng thương mại điện tử có nhiều mốc:

~~~text
Xem sản phẩm -> Thêm vào giỏ -> Nhận báo giá
        -> Xác nhận đơn -> Thanh toán -> Giao hàng -> Hoàn tiền
~~~

Giá ở trang sản phẩm, giá được báo trong giỏ, giá khách **đồng ý thanh toán**, số tiền thực tế thu và số tiền cuối cùng sau hoàn có thể khác nhau. Địa chỉ trong sổ địa chỉ, địa chỉ khách xác nhận, địa chỉ trên nhãn giao hàng và địa chỉ cuối cùng đơn vị vận chuyển sử dụng cũng có thể khác nhau.

Vì vậy, trước khi tạo snapshot, cần trả lời:

1. **Sự kiện nào là ranh giới chốt?** Trong ví dụ này là **OrderConfirmed**, tức lúc hệ thống chấp nhận đơn sau khi kiểm tra điều kiện.
2. **Ai sở hữu giá trị cuối cùng?** Hệ thống định giá và đơn hàng xác nhận giá; khách chọn địa chỉ, nhưng máy chủ xác nhận lựa chọn và sao chép các trường cần thiết.
3. **Trường nào phải giữ nguyên?** Đơn giá và địa chỉ được chấp thuận tại sự kiện chốt; thay đổi sau đó được ghi nhận riêng theo quy tắc nghiệp vụ.
4. **Định nghĩa tiền tệ và phép tính là gì?** Giá trước hay sau giảm giá, thuế, phí, đơn vị tiền, mức làm tròn và số lượng.
5. **Có cho phép sửa sau khi xác nhận không?** Nếu có, sửa phần nào, ai duyệt, có phát hành chứng từ thay thế không và lưu lịch sử thay đổi ra sao?

Một lựa chọn thực tế là đặt tên trường kèm ranh giới thời gian: **unit_price_at_confirmation**, **ship_to_line1_at_confirmation**. Tên rõ nghĩa giúp người viết truy vấn không vô tình lấy giá trị hiện hành cho báo cáo lịch sử. Dù đặt tên tốt, vẫn phải có hợp đồng và ràng buộc trong mã ghi.

### 3.1. Snapshot sự kiện khác snapshot kỹ thuật của database

Từ **snapshot** ở đây chỉ **giá trị nghiệp vụ được ghi lại tại sự kiện chốt**. Nó không đồng nghĩa với ảnh chụp toàn cơ sở dữ liệu, snapshot của storage, hoặc isolation level **REPEATABLE READ** trong PostgreSQL.

Một transaction sử dụng **READ COMMITTED** vẫn có thể tạo snapshot nghiệp vụ đúng nếu giá/địa chỉ được xác thực, khóa hoặc kiểm tra phiên bản phù hợp và ghi cùng giao dịch. Ngược lại, chỉ dùng isolation level mạnh hơn mà lấy giá sai thời điểm hoặc tin giá từ client thì chưa tạo được bản chụp nghiệp vụ đáng tin.

## 4. Mô hình quan hệ: giữ dữ liệu hiện hành và dữ liệu đã chốt ở nơi phù hợp

Giả sử yêu cầu là khi xác nhận đơn, lưu **đơn giá, tên sản phẩm và địa chỉ giao hàng đã chọn**. Ví dụ PostgreSQL tối giản:

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    current_unit_price NUMERIC(18, 2) NOT NULL
        CHECK (current_unit_price >= 0),
    currency CHAR(3) NOT NULL,
    price_version BIGINT NOT NULL DEFAULT 1
        CHECK (price_version >= 1)
);

CREATE TABLE customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    recipient_name TEXT NOT NULL,
    line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    client_request_id TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    currency CHAR(3) NOT NULL,
    source_address_id BIGINT NULL
        REFERENCES customer_addresses(address_id)
        ON DELETE SET NULL,
    ship_to_name_at_confirmation TEXT NOT NULL,
    ship_to_line1_at_confirmation TEXT NOT NULL,
    ship_to_city_at_confirmation TEXT NOT NULL,
    ship_to_country_at_confirmation CHAR(2) NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('CONFIRMED', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NULL
        REFERENCES catalog_products(product_id)
        ON DELETE SET NULL,
    product_name_at_confirmation TEXT NOT NULL,
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    product_price_version_at_confirmation BIGINT NOT NULL
        CHECK (product_price_version_at_confirmation >= 1),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_subtotal NUMERIC(22, 2)
        GENERATED ALWAYS AS
        (quantity * unit_price_at_confirmation) STORED
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
~~~

Đây là **lược đồ minh họa**, chưa phải mô hình thanh toán sản xuất hoàn chỉnh. Nó cố ý chưa chứa giảm giá, thuế, vận chuyển, tỷ giá, hoàn tiền và nhiều dòng tiền tệ trên một đơn. Trong hệ thống thật, cần mô hình các khoản ấy theo nghiệp vụ và kiểm tra loại tiền tương thích. **line_subtotal** ở đây chỉ là **quantity × unit_price_at_confirmation**; không tự đại diện cho số tiền khách phải trả.

### 4.1. Vì sao vẫn lưu product_id và source_address_id?

Các khóa tham chiếu trả lời **“giao dịch này liên quan thực thể nào?”**, còn snapshot trả lời **“giá trị nào đã được chốt?”**. Việc giữ cả hai có lợi:

- **product_id** giúp điều hướng đến sản phẩm hiện hành, thống kê theo sản phẩm hoặc xác định mã hàng, nếu sản phẩm vẫn tồn tại.
- **product_name_at_confirmation** và **unit_price_at_confirmation** giữ nội dung đơn cũ kể cả khi tên, giá sản phẩm đổi.
- **source_address_id** cho biết khách đã chọn địa chỉ nào trong sổ địa chỉ tại thời điểm ấy, nếu tham chiếu còn tồn tại.
- **ship_to_*_at_confirmation** giữ nội dung đã xác nhận ngay cả khi địa chỉ trong sổ bị chỉnh sửa hoặc xóa.

Trong ví dụ, **ON DELETE SET NULL** cho phép bỏ tham chiếu đến bản ghi hiện hành khi bản ghi ấy được xóa mà vẫn giữ thông tin đã chốt. Đây là **một lựa chọn mô hình hóa**, không phải quy định lưu trữ mặc định. Nếu yêu cầu quyền riêng tư hoặc thời hạn lưu dữ liệu buộc xóa/ẩn snapshot, phải thực hiện theo chính sách đã xác định; không dùng khóa ngoại để giả định snapshot được lưu vô thời hạn.

### 4.2. Không lưu một địa chỉ duy nhất cho mọi vai trò

**Địa chỉ nhận hàng**, **địa chỉ xuất hóa đơn** và **địa chỉ liên hệ** có thể khác nhau. Một schema dùng **orders.address** chung cho tất cả mục đích dễ dẫn đến sai quy trình. Nếu nghiệp vụ cần nhiều loại địa chỉ, lưu các nhóm snapshot hoặc một bảng **order_address_snapshots** có **(order_id, address_role)** làm khóa duy nhất, với vai trò như **SHIPPING**, **BILLING**.

Nếu một đơn có nhiều kiện giao đến nhiều địa chỉ, grain snapshot có thể là **mỗi shipment** thay vì mỗi order. Chọn grain theo đối tượng thực sự được chốt, không theo cách thuận tiện để thiết kế một bảng.

## 5. Xác nhận đơn phải tạo bản chụp trong một quy trình đáng tin cậy

Một lỗi nghiêm trọng là để trình duyệt gửi **unit_price = 150000** và chép nguyên giá trị ấy vào đơn, vì khách có thể sửa request. Máy chủ phải xác thực lựa chọn sản phẩm, giá áp dụng, ưu đãi và địa chỉ trước khi ghi.

Với luồng tối giản gồm một sản phẩm và một địa chỉ, ví dụ PostgreSQL có thể ghi snapshot bằng **một câu lệnh** bên trong transaction:

~~~sql
BEGIN;

WITH selected_product AS MATERIALIZED (
    SELECT
        product_id, display_name, current_unit_price,
        currency, price_version
    FROM catalog_products
    WHERE product_id = 501
    FOR SHARE
),
selected_address AS MATERIALIZED (
    SELECT
        address_id, recipient_name, line1, city, country_code
    FROM customer_addresses
    WHERE address_id = 77
      AND customer_id = 42
    FOR SHARE
),
created_order AS (
    INSERT INTO orders (
        order_id,
        client_request_id,
        customer_id,
        confirmed_at,
        currency,
        source_address_id,
        ship_to_name_at_confirmation,
        ship_to_line1_at_confirmation,
        ship_to_city_at_confirmation,
        ship_to_country_at_confirmation,
        status
    )
    SELECT
        9001,
        'request-42-9001',
        42,
        clock_timestamp(),
        p.currency,
        a.address_id,
        a.recipient_name,
        a.line1,
        a.city,
        a.country_code,
        'CONFIRMED'
    FROM selected_product AS p
    CROSS JOIN selected_address AS a
    RETURNING order_id
)
INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    product_name_at_confirmation,
    unit_price_at_confirmation,
    product_price_version_at_confirmation,
    quantity
)
SELECT
    9101,
    o.order_id,
    p.product_id,
    p.display_name,
    p.current_unit_price,
    p.price_version,
    2
FROM created_order AS o
CROSS JOIN selected_product AS p
RETURNING order_item_id, unit_price_at_confirmation, line_subtotal;

COMMIT;
~~~

**Cách đọc ví dụ:** phần **selected_product** chọn giá và phiên bản đang được chấp nhận; **selected_address** chọn địa chỉ thuộc đúng khách hàng; **created_order** ghi địa chỉ đã chọn; bước cuối ghi tên/giá/phiên bản sản phẩm vào dòng hàng. Các phần cùng thuộc một statement, nên ghi đơn và dòng hàng là nguyên tử ở mức câu lệnh.

**Điều kiện cần bổ sung ở ứng dụng:** kiểm tra có **đúng một dòng hàng** được trả về trước khi commit; nếu sản phẩm/địa chỉ không tồn tại hoặc không hợp lệ, **ROLLBACK**. Ví dụ dùng mã cố định để dễ đọc; hệ thống thật dùng tham số có kiểm soát, kiểm tra quyền truy cập, tình trạng hàng, số lượng, tiền tệ và giá sau mọi điều chỉnh. Cần xử lý lỗi khóa, deadlock, giao dịch trùng và retries theo quy tắc nghiệp vụ.

### 5.1. Vì sao có FOR SHARE?

Trong PostgreSQL, khóa hàng **FOR SHARE** trên nguồn giúp việc cập nhật giá hoặc địa chỉ tương tranh phải phối hợp với quá trình xác nhận khi cùng đụng bản ghi đã khóa. Ở mức cô lập mặc định **READ COMMITTED**, câu lệnh có thể chờ các giao dịch cập nhật rồi đọc phiên bản phù hợp theo quy tắc PostgreSQL.

Điều này giảm rủi ro lấy giá cũ khi quy trình xác nhận và đổi giá xảy ra đồng thời. Tuy nhiên, **khóa là cơ chế kỹ thuật, không tự quyết định hợp đồng kinh doanh**: một báo giá có hiệu lực 15 phút, chương trình khuyến mãi theo khách, tồn kho giữ chỗ hoặc tỷ giá thời điểm khác đều cần quy tắc riêng. Trong hệ phân tán, khóa hàng của một database không bảo vệ được mọi nguồn nằm ở dịch vụ khác; cần báo giá có định danh/phiên bản, cơ chế xác nhận hoặc giao dịch nghiệp vụ thích hợp.

Cột **price_version** giúp lưu dấu phiên bản giá hiện hành đã được đọc, nhưng **chỉ lưu số phiên bản không thay thế việc lưu giá đã chốt**. Nếu bảng giá thay đổi và không giữ đủ lịch sử, một phiên bản đơn lẻ không giúp tái tạo số tiền của giao dịch.

### 5.2. Thử lại request không được tạo hai đơn

**client_request_id** có UNIQUE để cùng một request xác nhận không thể tạo thêm đơn khác với cùng ID. Nếu request được gửi lại sau timeout, một thao tác **INSERT** mới có thể gặp xung đột khóa duy nhất. Ứng dụng cần đọc đơn đã tạo, kiểm tra request trùng có cùng ý định nghiệp vụ và trả lại kết quả phù hợp; **không tự dùng ID khác để tạo thêm đơn**.

Trong hệ thống thật, idempotency key có thể cần phạm vi theo **customer_id** hoặc tenant, thời hạn giữ và lưu dấu payload; cũng phải phân biệt retry với yêu cầu khách thực sự tạo một đơn mới. Một giao dịch SQL đúng về khóa vẫn có thể sai nghiệp vụ nếu quy tắc xác định một lần đặt hàng không rõ.

## 6. Giá tại giao dịch không phải lúc nào cũng là giá niêm yết

Ví dụ trên dùng **current_unit_price** chỉ để minh họa bản chụp. Trong thực tế, giá khách chấp thuận có thể là kết quả của nhiều thành phần:

~~~text
Giá niêm yết / giá theo khách
          |
          v
Khuyến mãi và mã giảm giá
          |
          v
Quy tắc thuế, phí và làm tròn
          |
          v
Báo giá được xác nhận
          |
          v
Giá và các khoản mục tại giao dịch
~~~

Để lưu đúng, cần xác định:

- **Đơn vị tiền:** VND, USD hoặc loại tiền khác; quy ước số chữ số thập phân và làm tròn. Không cộng trực tiếp hai loại tiền.
- **Giá đơn vị:** trước hay sau chiết khấu, đã gồm thuế hay chưa. Tên **unit_price** một mình chưa đủ ngữ nghĩa.
- **Số lượng và đơn vị tính:** chiếc, kg, giờ; khi thay đổi số lượng có áp lại bậc giá không?
- **Ưu đãi:** mã khuyến mãi, quy tắc phân bổ giảm giá cho từng dòng, phần giảm thuộc đơn hay phí vận chuyển.
- **Thuế:** thuế suất và số tiền theo quy tắc áp dụng khi chốt, căn cứ chịu thuế và làm tròn. Thuế suất hiện hành không thể dùng để viết lại thuế trên chứng từ cũ.
- **Tỷ giá:** nếu chuyển đổi tiền tệ, cần mốc thời gian, nguồn tỷ giá, tiền gốc, tiền quy đổi và cách làm tròn.
- **Số tiền đã thu:** có thể khác số tiền dự kiến khi xác nhận do thanh toán một phần, điều chỉnh hoặc hoàn tiền.

Một mô hình mở rộng có thể giữ **list_unit_price_at_confirmation**, **discount_amount_at_confirmation**, **tax_amount_at_confirmation**, **final_line_amount** và **currency**, kèm chứng cứ chính sách khi cần. Không nhất thiết lưu mọi kết quả trung gian nếu được bảo đảm tái lập đúng; nhưng không được hy vọng tính lại từ **giá/thuế/khuyến mãi hiện hành** để có kết quả lịch sử.

**Bất biến phù hợp phải viết theo hợp đồng giá thực tế.** Ví dụ đơn giản: **line_subtotal = quantity × unit_price_at_confirmation**. Nếu có giảm giá và thuế, phải thêm các thành phần và thứ tự làm tròn để tái lập tổng chính xác đến đơn vị nhỏ của tiền. Một trường “total_amount” không có định nghĩa sẽ dẫn đến đối soát sai, dù code cập nhật không lỗi.

### 6.1. Giá thay đổi sau xác nhận: giữ lịch sử

Ví dụ kiểm tra:

~~~sql
-- Giá danh mục hôm nay:
UPDATE catalog_products
SET current_unit_price = 180000.00,
    price_version = price_version + 1
WHERE product_id = 501;

-- Dòng đơn đã xác nhận vẫn giữ giá cũ:
SELECT
    oi.order_item_id,
    oi.product_name_at_confirmation,
    oi.unit_price_at_confirmation,
    oi.quantity,
    oi.line_subtotal
FROM order_items AS oi
WHERE oi.order_id = 9001;
~~~

Nếu đơn được xác nhận khi giá 150.000 VND, truy vấn dòng đơn tiếp tục trả **150.000** và thành tiền hai sản phẩm **300.000 VND** theo ví dụ. Câu **UPDATE catalog_products** không tác động lên **order_items**; đó chính là yêu cầu lịch sử.

Không viết một job “làm mới toàn bộ giá cũ” bằng giá danh mục hiện tại. Làm vậy phá ý nghĩa **at_confirmation**, cho dù dữ liệu trông nhất quán giữa hai bảng.

## 7. Địa chỉ tại giao dịch cần được mô hình hóa như chứng cứ nghiệp vụ

Một địa chỉ không chỉ là một chuỗi duy nhất. Tùy nhu cầu giao hàng và hóa đơn, có thể cần:

- Người nhận và phương thức liên hệ.
- Số nhà/đường, thông tin căn hộ, khu vực, tỉnh/thành và mã quốc gia.
- Mã bưu chính khi áp dụng.
- Địa chỉ xuất hóa đơn, tên pháp nhân hoặc thông tin thuế riêng.
- Phiên bản chuẩn hóa địa chỉ hoặc kết quả xác minh của dịch vụ giao vận.
- Thời điểm khách chấp thuận và phương thức xác thực lựa chọn.

Sao chép địa chỉ từ **customer_addresses** sang **orders.ship_to_*_at_confirmation** nhằm ghi lại điều khách chấp thuận. Việc khách sửa địa chỉ mặc định sau đó không cập nhật nội dung đã chốt trong đơn.

**Cần phân biệt địa chỉ đã xác nhận và địa chỉ thực tế dùng để giao.** Nếu khách đổi nơi nhận sau khi đơn đã xác nhận và người bán đồng ý, có thể tạo một bản **shipping_instruction_revision** hoặc **shipment_address_snapshot** mới. Không nên âm thầm ghi đè bản xác nhận ban đầu khiến mất dấu thay đổi.

Ví dụ mô hình bổ sung cho các lần thay đổi chỉ dẫn giao hàng:

~~~sql
CREATE TABLE order_shipping_revisions (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    recorded_at TIMESTAMPTZ NOT NULL,
    approved_by TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    change_reason TEXT NOT NULL,
    PRIMARY KEY (order_id, revision_no)
);
~~~

Bảng này ghi mỗi phiên bản được chấp thuận. Nếu giao dịch đầu tiên đã có snapshot ở **orders**, quy ước rõ phiên bản nào là bản ban đầu, phiên bản nào dùng cho giao vận, và cách chọn phiên bản có hiệu lực. Cần kiểm soát thứ tự phiên bản khi hai tác nhân cùng sửa; ràng buộc UNIQUE không tự bảo đảm chọn đúng phiên bản tiếp theo nếu ứng dụng cấp số phiên bản bằng cách đọc-ghi thiếu khóa.

### 7.1. Không xem snapshot là giấy phép lưu dữ liệu cá nhân mãi mãi

Địa chỉ, tên người nhận và số điện thoại là dữ liệu cá nhân. Nhu cầu chứng minh giao dịch có thể yêu cầu lưu một số trường trong thời gian phù hợp, nhưng phải có **căn cứ, giới hạn truy cập, thời hạn lưu, quy trình xóa/ẩn và kiểm soát bản sao** theo yêu cầu áp dụng.

Một hệ thống có thể cần:

- Hạn chế ai được đọc toàn bộ địa chỉ giao hàng cũ.
- Mã hóa, ghi nhật ký truy cập và che dữ liệu trong giao diện hỗ trợ khi không cần thiết.
- Đặt thời hạn giữ cho từng loại chứng từ và dữ liệu vận hành.
- Tránh phát tán địa chỉ lịch sử vào search index/cache/phân tích nếu không có nhu cầu.
- Có quy trình xử lý yêu cầu xóa hoặc ẩn theo chính sách, bao gồm bản sao và hệ thống lưu trữ phụ trợ.

**Giữ nguyên sự thật lịch sử** không có nghĩa là mọi trường PII phải tồn tại vĩnh viễn dưới dạng có thể đọc công khai. Mô hình dữ liệu cần phân biệt bảo toàn ý nghĩa giao dịch với chính sách lưu giữ và bảo vệ dữ liệu.

## 8. Những cách JOIN làm sai lịch sử

### 8.1. Lấy giá hiện tại cho hóa đơn cũ

~~~sql
-- Sai khi cần giá đã chốt:
SELECT
    oi.order_item_id,
    oi.quantity,
    p.current_unit_price,
    oi.quantity * p.current_unit_price AS line_amount
FROM order_items AS oi
JOIN catalog_products AS p ON p.product_id = oi.product_id
WHERE oi.order_id = 9001;
~~~

Truy vấn này thay giá lịch sử bằng giá hiện hành. Nó còn có thể **mất dòng** nếu sản phẩm hiện tại đã bị xóa và **product_id** thành NULL. Cách phù hợp cho hóa đơn cũ là đọc các trường **unit_price_at_confirmation**, **product_name_at_confirmation**, **quantity** và số tiền đã được xác nhận trong bản ghi giao dịch.

Nếu muốn hiển thị **thêm** giá hiện tại để người dùng so sánh, có thể LEFT JOIN sản phẩm hiện hành và đặt tên hai trường khác nhau rõ ràng; không ghi đè giá lịch sử.

### 8.2. Lấy địa chỉ hiện tại cho đơn đã xác nhận

~~~sql
-- Sai khi cần địa chỉ khách đã xác nhận ở quá khứ:
SELECT a.line1, a.city
FROM orders AS o
JOIN customer_addresses AS a
    ON a.address_id = o.source_address_id
WHERE o.order_id = 9001;
~~~

Nếu khách sửa địa chỉ trong sổ, truy vấn sẽ trả dữ liệu mới; nếu địa chỉ đã xóa, có thể không trả dòng nào. Để kiểm tra xác nhận ban đầu, đọc **orders.ship_to_line1_at_confirmation** và các trường snapshot tương ứng.

Một truy vấn khác có thể cố ý lấy địa chỉ hiện hành để hỗ trợ khách chọn lại khi đặt đơn mới; điều đó không sai nếu **use case** thực sự là địa chỉ hiện hành.

### 8.3. “Đồng bộ” ảnh chụp bằng trigger cập nhật hàng loạt

Nếu đổi giá sản phẩm mà trigger tự cập nhật **mọi order_items.unit_price_at_confirmation** của sản phẩm ấy, hệ thống đang viết lại lịch sử. Cơ chế đó có thể đúng cho **read projection** nhưng sai cho **snapshot**. Trước khi viết trigger, phải hỏi bản sao đang trả lời câu hỏi nghiệp vụ nào.

## 9. Cách kiểm chứng snapshot khác cách kiểm chứng bản sao hiện hành

Với bản sao tăng tốc như **product_cards.current_price_display**, bất biến có thể là:

> Khi projection đã xử lý đến phiên bản giá V, giá hiển thị phải bằng giá nguồn của đúng phiên bản V.

Kiểm chứng bằng cách so giá/phiên bản, độ trễ và sự kiện đã xử lý. Nếu lệch, làm mới hoặc xây dựng lại projection.

Với snapshot giá trên dòng đơn, **không có bất biến “giá giao dịch = giá danh mục hôm nay”**. Các bất biến phù hợp hơn là:

- Số lượng của dòng đã xác nhận **lớn hơn 0**.
- Đơn giá tại xác nhận và loại tiền đáp ứng hợp đồng giao dịch; tổng dòng khớp công thức được chốt.
- Giá và địa chỉ của đơn đã hoàn thành không bị một luồng cập nhật danh mục/hồ sơ tự ý thay đổi.
- Nếu có hiệu chỉnh, hệ thống có thể truy ra giá trị ban đầu, thay đổi, người/tác nhân thực hiện và lý do.
- Mỗi **client_request_id** đại diện cho một thao tác đặt hàng được xử lý theo quy tắc chống lặp.

Ví dụ kiểm tra tính toán trong schema minh họa:

~~~sql
SELECT
    oi.order_item_id,
    oi.line_subtotal,
    oi.quantity * oi.unit_price_at_confirmation
        AS expected_subtotal
FROM order_items AS oi
WHERE oi.line_subtotal IS DISTINCT FROM
      oi.quantity * oi.unit_price_at_confirmation;
~~~

Với generated column như định nghĩa trong bài, giá trị thường được database duy trì. Truy vấn vẫn minh họa **đúng dạng bất biến**: so cùng dữ liệu đã chốt, không so với giá sản phẩm hiện hành.

Nếu cần so với bản báo giá đã được duyệt, bảng **approved_quotes**, **quote_lines** hoặc event **OrderConfirmed** có thể giữ nội dung cam kết tại sự kiện. Quy tắc so sánh phải xác định rõ khi nào báo giá đã hết hạn hoặc bị thay thế. Không mặc định mọi quote là giao dịch đã xác nhận.

### 9.1. Dấu vết chỉnh sửa và ranh giới bất biến

Một snapshot thông thường được hiểu là **bất biến sau khi xác nhận**, nhưng có trường hợp nghiệp vụ đòi sửa lỗi nhập địa chỉ, xuất chứng từ điều chỉnh hoặc hủy và lập lại đơn. Có thể chọn:

- **Giữ bản ban đầu + bản sửa có phiên bản**: phù hợp khi cần xem chính xác lịch sử thay đổi.
- **Ghi sự kiện bù/điều chỉnh**: phù hợp với các luồng thanh toán, hoàn tiền hoặc sổ cái.
- **Lưu tài liệu mới thay thế**: phù hợp với quy trình có chứng từ thay thế, phải giữ liên kết và trạng thái giữa các tài liệu.
- **Hạn chế UPDATE trực tiếp** bằng quyền ứng dụng, dịch vụ sở hữu, trigger có kiểm soát hoặc mô hình append-only khi cần.

Các lựa chọn này không có nghĩa mọi snapshot đều phải bất biến về vật lý trong tất cả tình huống. Điều quan trọng là **sự thật đã chốt và các lần hiệu chỉnh có thể phân biệt, truy vết và tái lập theo chính sách**.

## 10. Khi nào có thể chỉ giữ lịch sử giá/địa chỉ và truy vấn theo thời gian?

Một phản biện hợp lý là: “Nếu có bảng lịch sử giá với khoảng hiệu lực, sao không JOIN để tìm giá tại lúc xác nhận thay vì chép giá vào dòng đơn?”

Có thể dùng **bảng lịch sử hiệu lực (temporal price history)** hoặc **Slowly Changing Dimension Type 2**:

~~~text
product_price_history
  product_id
  effective_from
  effective_to
  unit_price
  currency
  price_policy_id
~~~

Khi đó, một giao dịch có thể JOIN theo **product_id** và thời điểm **effective_from ≤ confirmed_at < effective_to** để truy giá lịch sử. Tuy nhiên, cách này chỉ tái tạo đúng nếu:

1. Mọi phiên bản giá từng áp dụng đều được lưu đầy đủ, không có khoảng thiếu/đè lấn không được xử lý.
2. Giá có hiệu lực thực sự là giá giao dịch, không bị ưu đãi riêng, thương lượng, thuế, tỷ giá hay điều chỉnh khác làm khác đi.
3. Thời điểm xác nhận và quy tắc ưu tiên phiên bản được định nghĩa nhất quán.
4. Chỉnh sửa hồi tố đối với bảng giá không làm thay đổi kết quả cần bảo toàn, hoặc lịch sử thay đổi được ghi đủ.
5. Sản phẩm và điều khoản vẫn có thể được tham chiếu dù danh mục hiện tại đã thay đổi hoặc bị xóa.

Nếu các điều kiện đó thỏa mãn và nhu cầu nghiệp vụ chỉ cần tái lập từ hệ thống giá có kiểm soát, truy vấn theo thời gian có thể phù hợp. Nhưng nhiều đơn hàng có **giá đã chấp thuận riêng**; vì vậy lưu trực tiếp số tiền trên chứng từ vẫn là cách rõ ràng để giữ sự thật giao dịch. Bảng giá lịch sử và snapshot có thể bổ trợ nhau: một bên nói **giá công bố có hiệu lực**, bên kia nói **giá thực tế đã áp dụng cho giao dịch**.

**Hai chiều thời gian:** với dữ liệu sửa hồi tố, đôi khi cần phân biệt **valid time** (khi dữ liệu được xem là có hiệu lực trong nghiệp vụ) và **transaction/recorded time** (khi hệ thống biết hoặc ghi nhận điều đó). Mô hình bitemporal thích hợp cho bài toán truy vết phức tạp; nó không tự thay thế bản cam kết giá của từng giao dịch.

## 11. Thay đổi sau khi xác nhận: tạo nghiệp vụ mới, đừng sửa quá khứ mù quáng

Một vài tình huống phổ biến:

| Tình huống | Cách xử lý dữ liệu gợi ý | Điều cần tránh |
| --- | --- | --- |
| Giá danh mục tăng sau đặt hàng | Giữ giá trên dòng đơn cũ, áp giá mới cho giao dịch mới | UPDATE giá của toàn bộ dòng đơn đã chốt |
| Khách sửa địa chỉ mặc định | Cập nhật sổ địa chỉ hiện hành; giữ snapshot đơn cũ | JOIN hồ sơ hiện tại để hiển thị lại lịch sử |
| Khách đổi địa chỉ giao hàng sau xác nhận và được duyệt | Tạo revision/chỉ dẫn giao vận mới, giữ lịch sử phê duyệt | Xóa dấu vết địa chỉ đã xác nhận ban đầu |
| Khách đổi số lượng trước xác nhận | Tính lại báo giá, xin xác nhận lại nếu cần | Coi tổng trong giỏ cũ vẫn là giá đã chốt |
| Trả hàng một phần | Lưu dòng trả/hoàn và số tiền hoàn theo chính sách | Âm thầm sửa giá gốc để “khớp tiền còn lại” |
| Đơn bị hủy | Ghi trạng thái và sự kiện hủy, xử lý nghĩa vụ thanh toán | Xóa snapshot cần cho đối soát mà không có quy trình |
| Điều chỉnh chứng từ | Tạo chứng từ điều chỉnh hoặc phiên bản có tham chiếu | Viết đè mọi chứng từ cũ mà không truy vết |

**Điều chỉnh số tiền sau giao dịch** không nhất thiết làm thay đổi số tiền đã xác nhận ban đầu. Ví dụ, khách mua 300.000 VND rồi hoàn 100.000 VND: báo cáo “giá trị đã đặt” và báo cáo “doanh thu ròng” là hai chỉ số khác nhau. Việc dùng cùng một cột cho cả hai sẽ làm sai thiết kế và báo cáo.

## 12. Cách xử lý khi hệ thống cũ chưa lưu snapshot

Đây là tình huống di trú dữ liệu khó hơn việc chỉ thêm cột. Giả sử hệ thống cũ chỉ lưu **order_items.product_id** và tính giá đơn từ **catalog_products.current_unit_price**. Sau nhiều lần đổi giá, không thể suy ra chắc chắn giá khách đã thanh toán chỉ từ dữ liệu hiện hành.

Một quy trình có kiểm soát:

1. **Định nghĩa yêu cầu mới** và thời điểm hệ thống bắt đầu lưu snapshot chính thức.
2. **Thêm cột mới** theo kiểu cho phép giai đoạn chuyển tiếp; có thể để nullable và lưu trạng thái chất lượng dữ liệu trong phương án di trú phù hợp.
3. **Bật ghi snapshot cho đơn mới**, kiểm soát mọi đường xác nhận đơn; bảo đảm không bỏ sót từ thời điểm chuyển đổi.
4. **Tìm nguồn chứng cứ cho đơn cũ:** hóa đơn đã phát hành, payment capture, lịch sử giá thực có đủ hiệu lực, báo giá hoặc bản ghi sự kiện.
5. **Backfill chỉ khi có căn cứ** và ghi rõ nguồn gốc, phương pháp, độ tin cậy; các trường không thể phục hồi cần được đánh dấu chưa xác minh theo thiết kế.
6. **Đối soát** với chứng từ và tổng tiền giao dịch; kiểm tra dữ liệu bị lệch, tiền tệ, làm tròn và trường hợp nhiều lần chỉnh sửa.
7. **Chuyển đường đọc** cho đơn mới và đơn cũ theo mức độ đầy đủ của dữ liệu, có đường xử lý riêng cho bản ghi thiếu chứng cứ.

**Tuyệt đối không mặc định:** giá sản phẩm hôm nay là giá của giao dịch năm trước; hoặc địa chỉ mặc định hôm nay là địa chỉ giao hàng cũ. Backfill theo cách đó có thể làm báo cáo “có đủ dữ liệu” nhưng thực chất là **bịa ra lịch sử**.

Trong giai đoạn chuyển tiếp, một trường nullable mang nghĩa “chưa biết” khác với số 0; không được thay NULL bằng 0 nếu 0 là một giá trị tiền hợp lệ. Nếu cần ràng buộc **NOT NULL** cho đơn mới, có thể triển khai từng bước sau khi xác minh dữ liệu và đường ghi.

## 13. Snapshot trong mô hình document, graph và analytics

Nguyên tắc phân biệt trạng thái hiện hành với sự thật theo thời điểm vẫn áp dụng khi rời mô hình quan hệ.

| Mô hình | Cách biểu diễn snapshot giao dịch | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Relational** | Cột **at_confirmation** trên dòng đơn hoặc bảng snapshot có khóa ngoại về đơn | JOIN nhầm bảng hiện hành, bỏ sót đường ghi, giao dịch xác nhận thiếu nguyên tử |
| **Document** | Document **order** nhúng dòng hàng, đơn giá và địa chỉ đã chốt | Ghi đè snapshot khi đồng bộ hồ sơ; giới hạn document và độ nguyên tử khi dữ liệu chia kho |
| **Graph** | Cạnh **Order–Product** mang giá tại sự kiện hoặc đỉnh **OrderLine** chứa điều khoản đã chốt | Lấy thuộc tính giá hiện tại từ đỉnh Product thay cho điều khoản của cạnh/sự kiện |
| **Analytics** | Fact bán hàng giữ số tiền tại thời điểm giao dịch; dimension theo lịch sử hiệu lực để phân tích bối cảnh | Dùng dimension hiện hành để tái lập phân loại quá khứ không đúng yêu cầu |
| **Event log** | **OrderConfirmed** chứa thông tin đã chốt; điều chỉnh là sự kiện tiếp theo | Thiếu version/schema, không bảo đảm phát sự kiện, replay sai thứ tự hoặc thiếu dữ liệu |

Trong document database, **nhúng địa chỉ giao hàng vào document đơn hàng** thường thuận tiện vì thông tin này được đọc cùng giao dịch và cần giữ thời điểm chốt. Ngược lại, nhúng **địa chỉ hiện hành của khách** vào hàng triệu document để hiển thị hồ sơ là một bài toán đồng bộ khác.

Trong đồ thị, thuộc tính giá hiện tại trên đỉnh Product có thể thay đổi theo thời gian; **giá giao dịch** nên gắn với thực thể/cạnh thể hiện sự kiện mua hoặc dòng hàng. Nếu chỉ lần theo cạnh đến giá hiện tại, mô hình vẫn mắc lỗi lịch sử.

Trong phân tích, câu hỏi “Doanh số theo danh mục **hiện tại**” khác “Doanh số theo danh mục **tại thời điểm bán**”. Dữ liệu tiền đã chốt có thể là fact; thuộc tính phân loại cần áp dụng mô hình dimension hiện hành hoặc có hiệu lực theo thời gian tùy câu hỏi. Không nên tạo một bảng tổng hợp rồi dùng cho cả hai cách hiểu mà không ghi rõ.

## 14. Khung ra quyết định: snapshot, bản sao tăng tốc hay cả hai?

Trước khi quyết định tạo một cột lặp, hãy lập bảng cho **từng thuộc tính**:

| Câu hỏi | Nếu là snapshot tại giao dịch | Nếu là bản sao tối ưu đọc |
| --- | --- | --- |
| Cần trả lời điều gì? | Giá/địa chỉ đã được xác nhận khi nào? | Giá/địa chỉ/tên hiện hành đang hiển thị? |
| Sự kiện chốt là gì? | OrderConfirmed, InvoiceIssued, ShipmentDispatched... | Không nhất thiết có một sự kiện chốt bất biến |
| Nguồn tạo giá trị | Điều khoản và dữ liệu đã xác thực tại sự kiện | Bảng/dịch vụ hiện hành có quyền định nghĩa thuộc tính |
| Khi nguồn hiện hành đổi | Giữ nguyên, hoặc tạo hiệu chỉnh có dấu vết | Đồng bộ theo quy tắc và độ trễ được phép |
| Đo tính đúng thế nào? | Đối chiếu chứng từ/điều khoản/sự kiện và công thức tiền | Đối chiếu nguồn hiện tại, phiên bản và mức lag |
| Cần bảo vệ điều gì? | Lịch sử giao dịch, PII, tính toàn vẹn tài chính | Tính nhất quán, quyền truy cập, độ tươi của cache/projection |
| Có cần đánh đổi hiệu năng? | Lưu để giữ sự thật lịch sử, dù JOIN nhanh hay chậm | Chỉ sao chép nếu workload và phép đo biện minh |
| Khi bị sai xử lý ra sao? | Điều tra bằng chứng, lập chỉnh sửa có lịch sử | Làm mới hoặc tái dựng từ nguồn chuẩn |

Hệ thống hoàn toàn có thể cần **cả ba nơi**: **catalog_products.current_unit_price** cho giá hiện hành; **order_items.unit_price_at_confirmation** cho giao dịch đã chốt; và **product_cards.current_price_display** cho trang tìm kiếm. Ba cột không có chung hợp đồng cập nhật, nên không thể áp một quy tắc đồng bộ cho cả ba.

## 15. Bài tập vận dụng

### Bài 1 — Giá thay đổi trước khi giao hàng

Khách xác nhận đơn mua 3 chiếc bút, giá 20.000 VND/chiếc, chưa gồm thành phần phí khác. Hai ngày sau giá niêm yết tăng lên 25.000 VND/chiếc, đơn chưa giao.

**Câu hỏi:** Trong chi tiết đơn đã xác nhận, nên lấy giá ở bảng sản phẩm hiện tại hay giá trong dòng đơn? Thành tiền của ba chiếc bút là bao nhiêu theo ví dụ?

### Bài 2 — Thay địa chỉ mặc định

Khách đặt đơn với địa chỉ A. Sau đó sửa địa chỉ mặc định thành B. Bộ phận hỗ trợ cần xác minh lúc đặt hàng khách đã chấp thuận giao đến đâu; màn hình chọn địa chỉ khi mua tiếp cần gợi ý địa chỉ nào?

**Câu hỏi:** Hai màn hình phải đọc dữ liệu từ đâu?

### Bài 3 — Giá báo trước và ưu đãi

Sản phẩm có giá niêm yết 500.000 VND nhưng khách được áp mã giảm 50.000 VND và đã xác nhận giá cuối 450.000 VND trước thuế. Hệ thống chỉ lưu **product_id** và **price_version** của bảng giá chung.

**Câu hỏi:** Vì sao chưa đủ để tái lập số tiền giao dịch? Nên ghi thêm gì?

### Bài 4 — Backfill dữ liệu cũ

Có 200.000 đơn lịch sử chỉ lưu product_id, không có giá lúc chốt. Bảng giá hiện nay đã đổi nhiều lần; nhóm muốn chạy **UPDATE order_items SET unit_price_at_confirmation = products.current_unit_price**.

**Câu hỏi:** Cách này có đáng tin không? Nếu không có chứng từ lịch sử, dữ liệu cũ nên được xử lý thế nào?

### Bài 5 — Địa chỉ giao hàng sau xác nhận

Đơn hàng đã xác nhận địa chỉ A nhưng khách gọi đổi sang B trước khi giao. Nhân viên duyệt và đơn vị vận chuyển thực sự giao đến B.

**Câu hỏi:** Nên sửa đè địa chỉ snapshot ban đầu thành B hay tạo thêm bản ghi? Cần lưu tối thiểu những thông tin nào để giải thích sự khác nhau?

### Gợi ý đáp án

1. Đọc **unit_price_at_confirmation** trên dòng đơn: **3 × 20.000 = 60.000 VND** theo giả định chưa có giảm giá, phí hay thuế. Giá 25.000 VND là giá niêm yết cho thời điểm mới.
2. Bộ phận hỗ trợ đọc **snapshot địa chỉ tại xác nhận đơn** (A); màn hình mua tiếp có thể đọc **sổ địa chỉ hiện hành** (B). Nếu có thay đổi chỉ dẫn giao thực tế, xem thêm phiên bản vận chuyển có hiệu lực.
3. Phiên bản bảng giá chung không phản ánh mã giảm giá riêng và điều khoản khách đã chấp thuận. Cần lưu giá/chiết khấu đã chốt hoặc nguồn chứng cứ đủ để tái lập công thức, loại tiền, thuế và quy tắc làm tròn.
4. Không đáng tin: giá hiện tại không chứng minh giá quá khứ. Tìm hóa đơn, lịch sử thanh toán, báo giá hoặc nguồn chứng cứ khác; nếu không có, đánh dấu **không xác minh được** theo chính sách chuyển đổi, không tự điền giá hiện hành như sự thật.
5. Giữ dấu vết **A đã được chấp thuận ban đầu** và tạo **revision/chỉ dẫn giao hàng B** đã được duyệt; lưu thời gian, người/tác nhân duyệt, lý do, địa chỉ có hiệu lực và liên kết với shipment. Quy tắc chọn địa chỉ thực giao phải rõ ràng.

## 16. Ghi nhớ

**Ảnh chụp giá hoặc địa chỉ tại thời điểm giao dịch là một sự thật lịch sử có ranh giới nghiệp vụ.** Nó có thể chứa bản sao vật lý của dữ liệu từng tồn tại trong bảng sản phẩm/hồ sơ, nhưng không được cập nhật theo thay đổi hiện hành chỉ để hai bảng trông giống nhau.

**Bản sao để tăng tốc là mô hình đọc của một sự thật đang thay đổi.** Nó cần nguồn chuẩn, cơ chế làm mới, quy tắc độ trễ và đối soát; tạo bản sao chỉ nên là quyết định dựa trên mẫu truy cập cùng bằng chứng đo lường.

Khi thiết kế, hãy hỏi: **“Trường này phải trả lời sự thật tại thời điểm nào, thay đổi nguồn sau đó có được phép làm đổi câu trả lời không, và ta có chứng cứ gì để kiểm tra?”** Trả lời rõ ba câu ấy sẽ ngăn lỗi viết lại lịch sử và giúp mô hình dữ liệu tiến hóa an toàn.
