# Chuyển miền dữ liệu và quan hệ nghiệp vụ thành bảng MySQL

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt thực thể, thuộc tính, quan hệ và quy tắc nghiệp vụ trong mô hình miền.
- Xác định bảng, cột, khóa chính, khóa ngoại và các ràng buộc phù hợp.
- Chuyển quan hệ một-một, một-nhiều và nhiều-nhiều thành cấu trúc quan hệ.
- Chọn khóa tự nhiên, khóa thay thế và khóa ghép theo vòng đời dữ liệu.
- Chuẩn hóa dữ liệu để hạn chế lặp, cập nhật lệch và xóa nhầm.
- Dùng kiểu dữ liệu và constraint để bảo vệ tính hợp lệ ngay tại MySQL.
- Kiểm tra mô hình bằng các truy vấn và tình huống nghiệp vụ thực tế.

Thiết kế bảng bắt đầu từ cách nghiệp vụ vận hành, không bắt đầu từ việc chọn tên cột. Trước khi tạo CREATE TABLE, cần hiểu hệ thống quản lý những đối tượng nào, mỗi đối tượng có định danh ra sao, chúng liên hệ với nhau thế nào và quy tắc nào phải luôn đúng. Khi mô hình miền được chuyển thành bảng hợp lý, truy vấn rõ ràng hơn, dữ liệu ít mâu thuẫn hơn và thay đổi nghiệp vụ dễ kiểm soát hơn.

Bài học dùng một hệ thống bán hàng làm ví dụ xuyên suốt, nhưng quy trình có thể áp dụng cho quản lý học viên, kho hàng, đặt lịch, hỗ trợ khách hàng và các hệ thống nghiệp vụ khác.

## 1. Bắt đầu từ miền nghiệp vụ

### 1.1. Tìm danh từ, động từ và quy tắc

Hãy đọc yêu cầu nghiệp vụ và xác định:

- **Danh từ:** những đối tượng cần lưu lâu dài, ví dụ khách hàng, sản phẩm, đơn hàng, thanh toán, danh mục.
- **Động từ:** những hành động và quan hệ, ví dụ khách hàng đặt đơn, đơn hàng chứa sản phẩm, sản phẩm thuộc danh mục, đơn hàng nhận thanh toán.
- **Quy tắc:** điều kiện phải đúng, ví dụ một đơn hàng thuộc về một khách hàng, số lượng đặt phải lớn hơn 0, mã sản phẩm không được trùng, một dòng đơn hàng phải tham chiếu đến một sản phẩm.

Ví dụ yêu cầu:

> Khách hàng có thể lưu nhiều địa chỉ. Một khách hàng có thể đặt nhiều đơn hàng. Mỗi đơn hàng chứa một hoặc nhiều dòng hàng. Mỗi dòng hàng tham chiếu một sản phẩm và lưu số lượng cùng đơn giá tại thời điểm đặt. Một sản phẩm có thể thuộc nhiều danh mục; một danh mục có thể chứa nhiều sản phẩm. Một đơn hàng có thể được thanh toán thành nhiều lần.

Từ yêu cầu trên, ta nhận diện các thực thể và quan hệ:

| Thành phần nghiệp vụ | Cách biểu diễn ban đầu |
|---|---|
| Khách hàng | CUSTOMER |
| Địa chỉ của khách hàng | CUSTOMER_ADDRESS |
| Sản phẩm | PRODUCT |
| Danh mục | CATEGORY |
| Đơn hàng | SALES_ORDER |
| Dòng hàng trong đơn | ORDER_ITEM |
| Thanh toán | PAYMENT |
| Quan hệ sản phẩm - danh mục | PRODUCT_CATEGORY |

Đây mới là mô hình ban đầu. Cần kiểm tra tiếp cardinality, tính bắt buộc, định danh và vòng đời trước khi chốt bảng.

### 1.2. Thực thể và value object

**Thực thể (entity)** có danh tính riêng và tồn tại qua thời gian. Hai thực thể có thể có các thuộc tính giống nhau nhưng vẫn là hai đối tượng khác nhau. Ví dụ, hai khách hàng có cùng tên vẫn là hai khách hàng khác nhau.

**Value object** được nhận diện bằng giá trị của nó trong một ngữ cảnh, không nhất thiết có danh tính độc lập. Ví dụ, địa chỉ giao hàng được chụp lại tại thời điểm đặt đơn có thể là một tập giá trị gồm người nhận, đường, quận, thành phố và mã bưu chính.

Một địa chỉ có thể được mô hình thành bảng CUSTOMER_ADDRESS nếu khách hàng quản lý, sửa, chọn lại hoặc gắn nhãn nhiều địa chỉ. Ngược lại, thông tin giao hàng trên đơn hàng thường cần là snapshot: nếu khách hàng sửa địa chỉ mặc định sau này, hóa đơn hoặc lịch sử đơn cũ vẫn phải giữ địa chỉ đã dùng khi đặt hàng.

Do đó, không phải mọi nhóm thuộc tính đều cần trở thành bảng riêng. Hãy tạo bảng riêng khi nhóm dữ liệu có danh tính, vòng đời, quan hệ hoặc nhu cầu truy vấn/quản lý độc lập. Có thể giữ một value object dưới dạng các cột cùng bảng khi nó chỉ có ý nghĩa trong phạm vi đối tượng cha.

### 1.3. Mỗi bảng cần trả lời một câu hỏi rõ ràng

Một bảng nên mô tả một loại đối tượng hoặc một loại quan hệ nhất quán. Nếu một bảng vừa lưu khách hàng, vừa lưu đơn hàng, vừa lưu danh sách sản phẩm bằng các cột lặp lại, bảng đó đang trộn nhiều khái niệm và khó duy trì.

Hãy mô tả bảng bằng một câu:

- CUSTOMER lưu danh tính và thông tin liên hệ cơ bản của khách hàng.
- PRODUCT lưu thông tin sản phẩm hiện hành.
- SALES_ORDER lưu một lần đặt hàng và trạng thái của đơn.
- ORDER_ITEM lưu từng dòng hàng thuộc một đơn.
- PAYMENT lưu một lần thanh toán hoặc một lần ghi nhận tiền cho đơn.
- PRODUCT_CATEGORY liên kết sản phẩm với danh mục.

Nếu khó mô tả một bảng bằng một câu, hãy xem lại bảng có đang chứa nhiều thực thể hoặc nhiều loại quan hệ hay không.

## 2. Xác định thuộc tính và kiểu dữ liệu

Sau khi nhận diện thực thể, liệt kê thuộc tính và xác định kiểu dữ liệu dựa trên miền giá trị, độ chính xác và cách sử dụng.

| Thuộc tính nghiệp vụ | Kiểu MySQL thường dùng | Lý do |
|---|---|---|
| ID số tăng tự động | BIGINT UNSIGNED | Dải giá trị lớn, phù hợp khóa thay thế |
| Mã SKU hoặc mã đơn | VARCHAR(n) | Độ dài biến đổi, có thể chứa chữ và số |
| Tên, mô tả ngắn | VARCHAR(n) | Chuỗi có giới hạn |
| Nội dung dài | TEXT | Văn bản dài |
| Số lượng | INT hoặc DECIMAL | Chọn theo việc hàng hóa có thể chia lẻ hay không |
| Giá tiền | DECIMAL(p,s) | Tránh sai số nhị phân của FLOAT/DOUBLE |
| Tỷ lệ | DECIMAL(p,s) | Kiểm soát số chữ số thập phân |
| Ngày sinh hoặc ngày nghiệp vụ | DATE | Chỉ cần ngày lịch |
| Thời điểm tạo đơn | DATETIME hoặc TIMESTAMP | Chọn theo quy ước lưu instant và timezone |
| Trạng thái hoạt động | BOOLEAN/TINYINT hoặc chuỗi có constraint | Miền giá trị nhỏ, cần quy ước rõ |
| Ghi chú tùy chọn | TEXT NULL | Có thể không có nội dung |

Đừng chọn kiểu dữ liệu chỉ theo ví dụ hiện tại. Ví dụ, mã bưu chính có thể bắt đầu bằng số 0 nên thường phải lưu dạng chuỗi. Số điện thoại cũng không phải đại lượng để cộng trừ; lưu bằng VARCHAR giúp giữ dấu cộng, số 0 đầu và định dạng quốc tế.

### 2.1. Giá trị nghiệp vụ và snapshot

Một đơn hàng cần giữ đơn giá tại thời điểm đặt. Nếu chỉ lưu product_id rồi luôn join sang PRODUCT để lấy giá hiện hành, báo cáo lịch sử có thể thay đổi khi giá sản phẩm được cập nhật.

Vì vậy, ORDER_ITEM thường lưu cả product_id và unit_price_at_order. Đây là dữ liệu snapshot có chủ đích. Tên sản phẩm tại thời điểm đặt cũng có thể được chụp lại nếu chứng từ cần giữ nguyên mô tả đã bán.

Việc lặp một giá trị snapshot không giống lặp dữ liệu danh mục một cách vô ý. Snapshot ghi nhận sự thật tại một thời điểm; dữ liệu hiện hành của sản phẩm tiếp tục được quản lý trong PRODUCT.

## 3. Xác định định danh và khóa

### 3.1. Khóa chính (PRIMARY KEY)

Mỗi bảng cần một cách nhận diện duy nhất mỗi hàng. Khóa chính:

- Không trùng lặp.
- Không nhận NULL.
- Ổn định trong suốt vòng đời bản ghi.
- Được dùng để tham chiếu từ bảng khác.

Ví dụ, customer_id là khóa chính của CUSTOMER. Không nên dùng tên khách hàng làm khóa chính vì tên có thể trùng và thay đổi.

### 3.2. Khóa tự nhiên và khóa thay thế

**Khóa tự nhiên (natural key)** là thuộc tính hoặc tập thuộc tính có ý nghĩa nghiệp vụ và có thể định danh đối tượng, ví dụ mã SKU, mã số thuế hoặc mã đơn hàng.

**Khóa thay thế (surrogate key)** là định danh được tạo ra chủ yếu để liên kết dữ liệu, ví dụ BIGINT AUTO_INCREMENT.

Một thiết kế thường dùng cả hai:

- product_id là PRIMARY KEY ổn định.
- sku có UNIQUE để bảo đảm mã SKU không trùng.

Nếu SKU thay đổi do quy tắc kinh doanh, product_id vẫn giữ nguyên để các bảng lịch sử không phải đổi khóa ngoại. Khóa thay thế không thay thế ràng buộc nghiệp vụ; nếu SKU phải duy nhất, vẫn cần UNIQUE.

Không phải mọi bảng đều cần AUTO_INCREMENT. Bảng liên kết thuần túy có thể dùng khóa chính ghép từ hai khóa ngoại. Một số miền có mã tự nhiên bất biến và ổn định có thể dùng trực tiếp, nhưng phải cân nhắc kích thước index, khả năng thay đổi và cách các hệ thống tham chiếu.

### 3.3. Khóa ứng viên và khóa thay thế duy nhất

Một bảng có thể có nhiều thuộc tính hoặc nhóm thuộc tính đủ điều kiện định danh duy nhất. Chúng là các khóa ứng viên. Chọn một làm PRIMARY KEY; các khóa còn lại có thể được bảo vệ bằng UNIQUE.

Ví dụ:

- customer_id là PRIMARY KEY.
- email có thể UNIQUE nếu nghiệp vụ yêu cầu mỗi email chỉ gắn với một tài khoản.
- external_customer_code có thể UNIQUE nếu được cấp bởi hệ thống tích hợp và có quy tắc ổn định.

Chỉ thêm UNIQUE sau khi xác định rõ phạm vi duy nhất: toàn hệ thống, theo tenant, theo chi nhánh hay theo một khoảng thời gian. Một mã duy nhất trong từng tenant cần unique key ghép (tenant_id, code), không phải UNIQUE(code) toàn bảng.

### 3.4. Khóa ghép

Khóa ghép (composite key) gồm nhiều cột. Ví dụ, mỗi đơn hàng có nhiều dòng và line_no chỉ duy nhất trong phạm vi đơn hàng:

~~~sql
PRIMARY KEY (order_id, line_no)
~~~

Cặp (order_id, line_no) xác định một dòng hàng. line_no = 1 có thể xuất hiện ở nhiều đơn khác nhau.

Khóa ghép phù hợp với bảng liên kết hoặc thực thể phụ thuộc vào cha. Tuy nhiên, khóa ghép dài có thể làm index và khóa ngoại ở bảng khác lớn hơn. Nếu bảng được tham chiếu rộng rãi hoặc cần một ID đơn giản cho API, có thể dùng surrogate key và thêm UNIQUE cho cặp nghiệp vụ.

## 4. Chuyển các loại quan hệ thành bảng

Cardinality cho biết mỗi phía có thể liên hệ với bao nhiêu đối tượng. Optionality cho biết quan hệ có bắt buộc hay không. Hai yếu tố này quyết định vị trí foreign key, UNIQUE và NULL.

### 4.1. Quan hệ một-nhiều (1:N)

Ví dụ một khách hàng có thể có nhiều địa chỉ, nhưng mỗi địa chỉ thuộc về đúng một khách hàng.

Đặt khóa ngoại ở phía nhiều, tức CUSTOMER_ADDRESS có customer_id tham chiếu CUSTOMER.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email (email)
) ENGINE = InnoDB;

CREATE TABLE customer_address (
    address_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    recipient_name VARCHAR(150) NOT NULL,
    address_line VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (address_id),
    KEY idx_customer_address_customer (customer_id),
    CONSTRAINT fk_customer_address_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

Một customer có thể có 0, 1 hoặc nhiều address. Mỗi address bắt buộc có một customer vì customer_id là NOT NULL và có foreign key.

UNIQUE(email) tuân theo collation của cột. Trước khi áp dụng, cần thống nhất email được so sánh có phân biệt chữ hoa/chữ thường hay không và chuẩn hóa đầu vào theo cùng quy tắc. Ví dụ DDL trên cố ý để cột kế thừa collation của schema; trong hệ thống thật, hãy chọn collation phù hợp với chính sách định danh và kiểm tra dữ liệu trùng trước khi tạo UNIQUE.

Nếu customer_id cho phép NULL, mô hình sẽ cho phép một địa chỉ không thuộc khách hàng nào. Chỉ làm vậy khi nghiệp vụ thật sự có địa chỉ dùng chung hoặc địa chỉ chưa gắn chủ sở hữu; không dùng NULL để che một quan hệ bắt buộc chưa được thiết kế rõ.

Cột is_default chỉ lưu một cờ trên từng địa chỉ; nó không tự bảo đảm mỗi khách hàng có tối đa một địa chỉ mặc định. Nếu cần bất biến đó, phải thiết kế thêm cơ chế duy nhất theo customer_id (chẳng hạn generated column có giá trị chỉ cho hàng mặc định rồi đặt UNIQUE) hoặc điều phối cập nhật trong transaction với ràng buộc phù hợp. Một CHECK trên từng hàng không thể kiểm tra các hàng khác.

### 4.2. Quan hệ một-một (1:1)

Ví dụ mỗi khách hàng có tối đa một hồ sơ tùy chọn chứa thông tin bổ sung. Dùng customer_id vừa là PRIMARY KEY của bảng con, vừa là FOREIGN KEY:

~~~sql
CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL,
    birth_date DATE NULL,
    preferred_language VARCHAR(20) NULL,
    profile_note TEXT NULL,
    PRIMARY KEY (customer_id),
    CONSTRAINT fk_customer_profile_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

Vì customer_id là khóa chính, mỗi khách hàng có tối đa một profile. Một customer có thể chưa có hàng trong CUSTOMER_PROFILE; quan hệ là tùy chọn từ phía customer. Nếu có hàng profile, nó bắt buộc thuộc về đúng một customer.

Nếu dùng một cột customer_id trong bảng con thay vì làm PRIMARY KEY, cần đặt UNIQUE(customer_id) để giới hạn tối đa một hàng con cho mỗi customer.

Lưu ý: foreign key ở bảng con không tự bảo đảm mọi customer đều phải có profile. Nếu nghiệp vụ yêu cầu hai phía luôn tồn tại đúng một-một, cần kiểm soát ở transaction/application hoặc xem lại cách hợp nhất dữ liệu vào cùng một bảng. Ràng buộc FK đơn phương không thể tự ép mọi hàng cha phải có hàng con.

### 4.3. Quan hệ nhiều-nhiều (M:N)

Một sản phẩm có thể thuộc nhiều danh mục; một danh mục có thể chứa nhiều sản phẩm. Không đặt một danh sách category_id phân cách bằng dấu phẩy trong PRODUCT. Tạo bảng liên kết PRODUCT_CATEGORY:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    current_price DECIMAL(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_sku (sku),
    CONSTRAINT chk_product_current_price
        CHECK (current_price >= 0)
) ENGINE = InnoDB;

CREATE TABLE category (
    category_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_name VARCHAR(120) NOT NULL,
    slug VARCHAR(140) NOT NULL,
    PRIMARY KEY (category_id),
    UNIQUE KEY uq_category_slug (slug)
) ENGINE = InnoDB;

CREATE TABLE product_category (
    product_id BIGINT UNSIGNED NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,
    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id, category_id),
    KEY idx_product_category_category (category_id, product_id),
    CONSTRAINT fk_product_category_product
        FOREIGN KEY (product_id)
        REFERENCES product (product_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_product_category_category
        FOREIGN KEY (category_id)
        REFERENCES category (category_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

PRIMARY KEY(product_id, category_id) ngăn cùng một sản phẩm được gắn cùng danh mục nhiều lần. Index đảo chiều (category_id, product_id) hỗ trợ truy vấn từ danh mục tìm sản phẩm.

Nếu quan hệ có thuộc tính riêng, đặt thuộc tính đó trong bảng liên kết. Ví dụ assigned_at là thời điểm gắn danh mục. Nếu cần lưu người gắn, thứ tự ưu tiên, trạng thái hoặc thời hạn hiệu lực, các cột đó cũng thuộc PRODUCT_CATEGORY.

### 4.4. Thực thể phụ thuộc và bảng chi tiết

Một dòng hàng không có ý nghĩa độc lập nếu không thuộc một đơn hàng. Đây là ví dụ thực thể phụ thuộc (dependent entity). Có thể dùng khóa ghép order_id + line_no:

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no VARCHAR(40) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    ordered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    order_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_sales_order_no (order_no),
    KEY idx_sales_order_customer_date (customer_id, ordered_at),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;

CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    product_name_at_order VARCHAR(200) NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price_at_order DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_item_product (product_id),
    CONSTRAINT chk_order_item_line_no
        CHECK (line_no > 0),
    CONSTRAINT chk_order_item_quantity
        CHECK (quantity > 0),
    CONSTRAINT chk_order_item_unit_price
        CHECK (unit_price_at_order >= 0),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_order_item_product
        FOREIGN KEY (product_id)
        REFERENCES product (product_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

Một đơn hàng có thể có nhiều dòng; mỗi dòng có số thứ tự riêng trong đơn. order_id là FK đến SALES_ORDER. product_id là FK đến PRODUCT. product_name_at_order và unit_price_at_order là snapshot để giữ nội dung đã bán kể cả khi tên hoặc giá sản phẩm hiện hành thay đổi.

Trong ví dụ, xóa đơn hàng sẽ xóa các dòng chi tiết nhờ ON DELETE CASCADE. Xóa sản phẩm đang được tham chiếu bởi dòng đơn hàng bị từ chối bởi RESTRICT để bảo toàn lịch sử. Trong nhiều hệ thống, sản phẩm được ngừng kinh doanh bằng is_active = FALSE thay vì xóa vật lý.

## 5. Ràng buộc giúp bảo vệ quy tắc nghiệp vụ

Constraint là quy tắc do database kiểm tra khi ghi dữ liệu. Không nên chỉ dựa vào giao diện hoặc service để bảo đảm dữ liệu hợp lệ, vì dữ liệu có thể được ghi từ nhiều ứng dụng, batch job, script hoặc công cụ quản trị.

### 5.1. NOT NULL

Dùng NOT NULL khi thuộc tính bắt buộc phải có.

Ví dụ order_item.product_id phải tồn tại và quantity phải có giá trị. Nếu quantity NULL, phép tính tổng tiền và báo cáo có thể cho kết quả không mong muốn.

Không biến mọi cột thành NOT NULL theo thói quen. Một cột NULL nên thể hiện trạng thái “chưa biết”, “chưa có” hoặc “không áp dụng” có ý nghĩa rõ. Hãy phân biệt NULL với chuỗi rỗng hoặc số 0.

### 5.2. PRIMARY KEY và UNIQUE

PRIMARY KEY định danh hàng; UNIQUE bảo đảm không có hai hàng trùng theo quy tắc so sánh của các cột trong key.

Ví dụ SKU phải duy nhất:

~~~sql
ALTER TABLE product
    ADD UNIQUE KEY uq_product_sku (sku);
~~~

Trước khi thêm UNIQUE vào bảng đang có dữ liệu, hãy tìm các nhóm trùng theo đúng collation đích và xử lý trước. Cột nullable trong UNIQUE có thể có nhiều hàng NULL; nếu nghiệp vụ yêu cầu mọi hàng có mã duy nhất, kết hợp UNIQUE với NOT NULL.

### 5.3. FOREIGN KEY

Foreign key bảo đảm giá trị ở bảng con tham chiếu đến hàng hợp lệ trong bảng cha. Ví dụ order_item.order_id phải tồn tại trong sales_order.

Khi thiết kế FK:

- Hai cột cần có kiểu dữ liệu tương thích; với kiểu số, phải chú ý signed/unsigned và kích thước.
- Với cột chuỗi, cần chú ý character set và collation tương thích.
- Bảng liên quan nên dùng InnoDB để có transaction và referential integrity.
- Cột được tham chiếu cần có index phù hợp, thường là PRIMARY KEY hoặc UNIQUE.
- Cột ở phía tham chiếu cần index; InnoDB có thể tự tạo index nếu chưa có index phù hợp, nhưng nên kiểm tra và thiết kế index theo truy vấn thực tế.

Không dùng FK chỉ để mô tả quan hệ trên sơ đồ. FK là ràng buộc thực thi ở database, giúp ngăn dữ liệu mồ côi.

### 5.4. ON DELETE và ON UPDATE

Các hành động tham chiếu phổ biến:

| Hành động | Ý nghĩa | Khi cân nhắc |
|---|---|---|
| RESTRICT | Từ chối xóa/sửa khóa cha nếu còn hàng con tham chiếu | Bảo vệ dữ liệu lịch sử |
| NO ACTION | Trong InnoDB có hành vi tương đương RESTRICT ở thời điểm kiểm tra | Thường không cần chọn riêng |
| CASCADE | Xóa hoặc cập nhật hàng con theo hàng cha | Bảng liên kết hoặc chi tiết có vòng đời phụ thuộc rõ |
| SET NULL | Đặt FK phía con thành NULL khi hàng cha bị xóa/cập nhật | Chỉ khi cột FK nullable và quan hệ có thể mất liên kết |

Ví dụ, xóa một sản phẩm có thể xóa các hàng liên kết PRODUCT_CATEGORY vì đó là quan hệ phụ thuộc. Nhưng không nên xóa một sản phẩm đã xuất hiện trong ORDER_ITEM nếu cần giữ lịch sử giao dịch. Dùng RESTRICT và trạng thái ngừng bán thường an toàn hơn.

Không chọn CASCADE theo thói quen. Một thao tác xóa cha có thể lan qua nhiều tầng và xóa lượng dữ liệu lớn. Hãy vẽ đường cascade, ước lượng phạm vi và thử trên dữ liệu đại diện.

### 5.5. CHECK

CHECK biểu diễn điều kiện phải đúng cho từng hàng:

~~~sql
quantity DECIMAL(12, 3) NOT NULL,
CONSTRAINT chk_quantity_positive CHECK (quantity > 0)
~~~

MySQL thực thi CHECK từ phiên bản 8.0.16 trở lên. Nếu hệ thống dùng phiên bản cũ hơn, không được giả định constraint đã được thực thi; hãy kiểm tra phiên bản và cơ chế bảo vệ thay thế. CHECK không thay thế quy tắc cần kiểm tra nhiều hàng hoặc nhiều bảng, chẳng hạn tổng số tiền của các dòng phải bằng tổng đơn hàng.

### 5.6. DEFAULT

DEFAULT cung cấp giá trị khi câu lệnh INSERT không chỉ định cột đó. Ví dụ order_status mặc định là pending hoặc created_at mặc định CURRENT_TIMESTAMP.

DEFAULT không có nghĩa mọi giá trị được gửi rõ ràng là NULL sẽ tự đổi thành giá trị mặc định. Nếu cột cho phép NULL và ứng dụng gửi NULL, MySQL lưu NULL. Hãy phân biệt “không truyền giá trị” với “truyền NULL”.

## 6. Chuẩn hóa để giảm dữ liệu lặp

Chuẩn hóa (normalization) tổ chức dữ liệu sao cho mỗi sự kiện được lưu ở nơi phù hợp, giảm phụ thuộc bất thường và giữ tính nhất quán.

### 6.1. Dạng chuẩn thứ nhất (1NF)

Mỗi ô dữ liệu nên chứa một giá trị thuộc miền cột, không nhét một danh sách nhiều giá trị vào một ô.

Thiết kế không phù hợp:

| order_id | product_ids |
|---:|---|
| 1001 | 12,18,25 |

Thiết kế quan hệ:

| order_id | line_no | product_id |
|---:|---:|---:|
| 1001 | 1 | 12 |
| 1001 | 2 | 18 |
| 1001 | 3 | 25 |

Cấu trúc thứ hai có thể join đến PRODUCT, đặt FK, index và truy vấn từng sản phẩm. Chuỗi phân cách bằng dấu phẩy không có FK cho từng phần tử và khó bảo đảm không trùng.

### 6.2. Dạng chuẩn thứ hai (2NF)

Với bảng có khóa chính ghép, thuộc tính không khóa phải phụ thuộc vào toàn bộ khóa, không chỉ một phần của khóa.

Giả sử bảng ORDER_ITEM có khóa (order_id, line_no). quantity phụ thuộc vào cả dòng hàng trong đơn. Nhưng order_date chỉ phụ thuộc order_id, không phụ thuộc line_no. Đưa order_date vào mỗi dòng sẽ lặp lại dữ liệu đơn hàng; nên lưu order_date trong SALES_ORDER.

### 6.3. Dạng chuẩn thứ ba (3NF)

Thuộc tính không khóa nên phụ thuộc vào khóa, không phụ thuộc bắc cầu qua thuộc tính không khóa khác.

Ví dụ nếu bảng PRODUCT lưu category_id và category_name, category_name thực ra phụ thuộc category_id. Khi tên danh mục đổi, nhiều sản phẩm phải cập nhật. Tách CATEGORY và giữ category_id trong bảng liên kết giúp dữ liệu danh mục có một nguồn quản lý.

### 6.4. Không chuẩn hóa quá mức

Chuẩn hóa không có nghĩa mọi cột đều phải tách thành bảng riêng. Nếu địa chỉ giao hàng là snapshot bất biến của một đơn, lưu các trường snapshot cùng đơn có thể phù hợp hơn join đến địa chỉ hiện tại của khách hàng.

Một số dữ liệu tổng hợp như order_total có thể được lưu để tối ưu báo cáo hoặc làm snapshot chứng từ, nhưng cần xác định nguồn sự thật và cách giữ đồng bộ với các dòng hàng, giảm giá, thuế và phí. Không lưu một giá trị dẫn xuất nếu không có quy tắc cập nhật rõ ràng.

Mục tiêu là mô hình phản ánh đúng nghiệp vụ, bảo đảm tính nhất quán và hỗ trợ truy vấn cần thiết. Tối ưu đọc có thể yêu cầu denormalization có chủ đích, nhưng phải đo lường và quản lý đồng bộ.

## 7. Ghép mô hình bán hàng thành schema hoàn chỉnh

Sơ đồ quan hệ khái quát:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : has
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    PRODUCT ||--o{ PRODUCT_CATEGORY : assigned
    CATEGORY ||--o{ PRODUCT_CATEGORY : groups
    SALES_ORDER ||--o{ PAYMENT : receives
~~~

Quan hệ trong sơ đồ:

- CUSTOMER có thể có nhiều địa chỉ và nhiều đơn hàng.
- SALES_ORDER có ít nhất một ORDER_ITEM theo quy tắc nghiệp vụ; FK đơn thuần không tự bảo đảm tối thiểu một dòng hàng.
- Mỗi ORDER_ITEM thuộc đúng một đơn hàng và tham chiếu một sản phẩm.
- PRODUCT và CATEGORY có quan hệ nhiều-nhiều qua PRODUCT_CATEGORY.
- Một đơn hàng có thể có nhiều lần thanh toán, ví dụ đặt cọc và thanh toán phần còn lại.

Bảng PAYMENT minh họa:

~~~sql
CREATE TABLE payment (
    payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    payment_ref VARCHAR(80) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    payment_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    paid_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (payment_id),
    UNIQUE KEY uq_payment_ref (payment_ref),
    KEY idx_payment_order_created (order_id, created_at),
    CONSTRAINT chk_payment_amount CHECK (amount > 0),
    CONSTRAINT fk_payment_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

Nếu mỗi đơn chỉ được có một bản ghi thanh toán, có thể thêm UNIQUE(order_id). Nhưng nếu hỗ trợ nhiều lần thanh toán, hoàn tiền hoặc nhiều phương thức, cần mô hình hóa giao dịch tiền theo quy tắc cụ thể; không áp đặt 1:1 khi nghiệp vụ là 1:N.

DDL PAYMENT ở trên minh họa khoản thu có amount dương. Nếu cần lưu hoàn tiền, hãy mô hình hóa rõ loại sự kiện và chiều tiền (hoặc dùng bảng REFUND riêng, có tham chiếu đến khoản thanh toán gốc); không âm thầm ghi amount âm vào bảng đang có CHECK(amount > 0).

## 8. Truy vấn để kiểm chứng mô hình

### 8.1. Lấy đơn hàng cùng khách hàng

~~~sql
SELECT
    o.order_id,
    o.order_no,
    o.ordered_at,
    o.order_status,
    c.customer_id,
    c.full_name,
    c.email
FROM sales_order AS o
JOIN customer AS c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 1001;
~~~

INNER JOIN trả về đơn hàng có khách hàng tương ứng. FK bảo đảm không có hàng sales_order mồ côi nếu constraint được bật và dữ liệu được ghi qua MySQL.

### 8.2. Lấy các dòng hàng của một đơn

~~~sql
SELECT
    oi.order_id,
    oi.line_no,
    oi.product_id,
    oi.product_name_at_order,
    oi.quantity,
    oi.unit_price_at_order,
    oi.quantity * oi.unit_price_at_order AS line_amount
FROM order_item AS oi
WHERE oi.order_id = 1001
ORDER BY oi.line_no;
~~~

Dùng giá snapshot trong ORDER_ITEM để tính lại giá trị tại thời điểm đặt. Nếu join PRODUCT để lấy current_price, kết quả có thể khác giá lịch sử.

### 8.3. Tìm sản phẩm theo danh mục

~~~sql
SELECT
    p.product_id,
    p.sku,
    p.product_name
FROM product AS p
JOIN product_category AS pc
  ON pc.product_id = p.product_id
WHERE pc.category_id = 5
  AND p.is_active = TRUE;
~~~

Index bắt đầu bằng category_id hỗ trợ truy vấn từ danh mục sang sản phẩm. Nếu thường xuyên truy vấn từ product_id tìm danh mục, khóa chính (product_id, category_id) đã hỗ trợ chiều đó.

### 8.4. Tìm bản ghi không có quan hệ

Ví dụ khách hàng chưa có đơn hàng:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
LEFT JOIN sales_order AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Truy vấn dạng anti-join này hữu ích để kiểm tra dữ liệu và nghiệp vụ. Cũng có thể dùng NOT EXISTS. Index trên sales_order.customer_id hỗ trợ tìm kiếm quan hệ.

## 9. Index phải phục vụ truy vấn và quan hệ

Primary key và unique key tạo index tương ứng. Foreign key thường cần index ở phía bảng con; InnoDB có thể tự tạo index phù hợp nếu chưa có. Ngoài các index phục vụ constraint, hãy dựa trên truy vấn thực tế.

Ví dụ:

- CUSTOMER: tìm theo email → UNIQUE(email).
- SALES_ORDER: liệt kê đơn của khách theo thời gian → INDEX(customer_id, ordered_at).
- ORDER_ITEM: lấy dòng của đơn → PRIMARY KEY(order_id, line_no).
- ORDER_ITEM: tìm các đơn có sản phẩm → INDEX(product_id).
- PRODUCT_CATEGORY: tìm danh mục của sản phẩm → PRIMARY KEY(product_id, category_id).
- PRODUCT_CATEGORY: tìm sản phẩm trong danh mục → INDEX(category_id, product_id).
- PAYMENT: liệt kê thanh toán của đơn theo thời gian → INDEX(order_id, created_at).

Thứ tự cột trong composite index rất quan trọng. Index (customer_id, ordered_at) hỗ trợ truy vấn lọc theo customer_id và có thể hỗ trợ sắp xếp theo ordered_at trong phạm vi customer đó. Nó không tương đương index chỉ có ordered_at cho mọi truy vấn.

Không thêm index cho mọi cột. Index chiếm dung lượng và làm tăng chi phí INSERT, UPDATE, DELETE. Dùng EXPLAIN, thống kê truy vấn và workload thật để xác định index cần thiết.

## 10. Quy trình thiết kế từ yêu cầu đến DDL

Có thể lặp lại quy trình sau cho mỗi tính năng:

1. **Viết quy tắc nghiệp vụ:** đối tượng nào tồn tại, ai sở hữu, điều gì bắt buộc, điều gì được phép lặp.
2. **Liệt kê thực thể:** phân biệt entity, value object, danh mục và quan hệ.
3. **Xác định thuộc tính:** miền giá trị, độ dài, độ chính xác, bắt buộc hay tùy chọn.
4. **Xác định định danh:** khóa chính, khóa tự nhiên, khóa ứng viên và phạm vi UNIQUE.
5. **Vẽ cardinality và optionality:** 1:1, 1:N, M:N; quan hệ có bắt buộc ở mỗi phía hay không.
6. **Chuyển quan hệ:** FK ở phía nhiều; bảng liên kết cho M:N; UNIQUE cho phía con của 1:1.
7. **Chuẩn hóa:** loại bỏ nhóm lặp, phụ thuộc từng phần và phụ thuộc bắc cầu.
8. **Thêm constraint:** NOT NULL, PK, UNIQUE, FK, CHECK và DEFAULT.
9. **Thiết kế index theo truy vấn:** lọc, join, sắp xếp và phân trang.
10. **Kiểm thử dữ liệu biên:** NULL, trùng, xóa cha, cập nhật khóa, số lượng 0/âm, chuỗi dài và transaction lỗi.
11. **Review migration:** đánh giá dữ liệu hiện có, metadata lock, thời gian DDL và khả năng tương thích ứng dụng.

## 11. Những lỗi mô hình thường gặp

| Lỗi | Vấn đề phát sinh | Hướng sửa |
|---|---|---|
| Lưu nhiều ID trong một cột dạng CSV | Không có FK cho từng phần tử, khó join và lọc | Dùng bảng liên kết |
| Dùng tên làm PRIMARY KEY | Tên trùng hoặc đổi làm hỏng tham chiếu | Dùng khóa ổn định và UNIQUE cho mã nghiệp vụ |
| Lặp thông tin khách hàng trong mỗi đơn | Cập nhật lệch và dư thừa | Tham chiếu customer_id; giữ snapshot chỉ khi cần lịch sử |
| Lưu giá hiện hành thay cho giá tại thời điểm bán | Lịch sử đơn thay đổi khi giá sản phẩm đổi | Lưu unit_price_at_order |
| Dùng CASCADE trên mọi FK | Xóa một hàng có thể xóa dây chuyền dữ liệu lịch sử | Chọn hành động theo vòng đời và yêu cầu lưu trữ |
| Dùng NULL để biểu diễn nhiều trạng thái không rõ | Khó hiểu và khó kiểm tra nghiệp vụ | Xác định ý nghĩa NULL, tách trạng thái nếu cần |
| Không đặt UNIQUE cho mã nghiệp vụ | Dữ liệu trùng dù có khóa chính | Thêm candidate key/unique constraint |
| Chỉ kiểm tra quan hệ ở ứng dụng | Script hoặc service khác có thể tạo dữ liệu mồ côi | Dùng FK tại database |
| Tách mọi thuộc tính thành bảng riêng | JOIN phức tạp và mô hình khó hiểu | Tách khi có vòng đời/quan hệ/quản lý độc lập |
| Dùng một bảng EAV cho mọi loại thuộc tính | Mất kiểu dữ liệu và constraint rõ ràng | Dùng cột có kiểu hoặc mô hình mở rộng có chủ đích |

## 12. Bài tập thực hành

### Bài 1: Phân tích yêu cầu

Thiết kế hệ thống đặt lịch khám gồm bệnh nhân, bác sĩ, chuyên khoa, lịch hẹn và phòng khám. Liệt kê thực thể, thuộc tính, quy tắc và cardinality. Xác định bệnh nhân có thể có nhiều lịch hẹn hay không và một lịch hẹn có thể có nhiều bác sĩ hay không.

### Bài 2: Mô hình quan hệ M:N

Thiết kế hệ thống khóa học: một học viên đăng ký nhiều khóa học, một khóa học có nhiều học viên. Tạo bảng STUDENT, COURSE và ENROLLMENT. Đặt khóa ghép hoặc surrogate key kèm UNIQUE; thêm enrollment_date và enrollment_status.

### Bài 3: Kiểm tra 1:1 và optionality

Tạo CUSTOMER_PROFILE dùng customer_id làm PK/FK. Thử tạo hai profile cho cùng một customer và quan sát constraint. Thử xóa customer đang có profile để kiểm tra hành động FK.

### Bài 4: Kiểm tra constraint

Tạo ORDER_ITEM với CHECK quantity > 0 và NOT NULL. Thử ghi quantity bằng 0, số âm và NULL. Xác nhận phiên bản MySQL thực thi CHECK.

### Bài 5: Phát hiện dữ liệu phi chuẩn hóa

Tạo một bảng lưu đơn hàng có cột product_ids dạng chuỗi phân cách bằng dấu phẩy. Viết các truy vấn cần thiết để tìm sản phẩm, sau đó chuyển sang ORDER_ITEM và so sánh độ phức tạp cùng khả năng đặt FK.

### Bài 6: Thiết kế snapshot

Tạo sản phẩm với current_price = 100.000, đặt đơn với unit_price_at_order = 100.000, sau đó đổi current_price thành 120.000. Viết truy vấn chứng minh lịch sử đơn vẫn giữ giá 100.000.

### Bài 7: Review schema

Chọn một tính năng trong dự án cá nhân. Viết mô tả mỗi bảng bằng một câu, vẽ quan hệ, liệt kê PK/FK/UNIQUE/CHECK và giải thích vì sao từng index tồn tại. Nhờ một người khác thử đưa ra các trường hợp dữ liệu sai để kiểm tra mô hình.

## Kết luận

Chuyển miền nghiệp vụ thành bảng MySQL là quá trình xác định thực thể, thuộc tính, định danh, quan hệ và các quy tắc phải luôn đúng. Khóa chính định danh hàng; khóa ngoại bảo vệ quan hệ; UNIQUE và CHECK giữ các bất biến; chuẩn hóa giảm dữ liệu lặp; index phục vụ truy vấn.

Một schema tốt phải phản ánh đúng vòng đời dữ liệu. Hãy phân biệt dữ liệu hiện hành với snapshot lịch sử, xác định rõ quan hệ bắt buộc hay tùy chọn, và chọn hành động xóa/cập nhật theo nghiệp vụ. Khi mô hình được thiết kế từ yêu cầu và được kiểm chứng bằng truy vấn cùng dữ liệu biên, MySQL có thể bảo vệ tính nhất quán ngay tại nơi dữ liệu được lưu.

