# Biểu diễn thuộc tính nhiều giá trị và thuộc tính phức hợp

Trong quá trình chuyển yêu cầu nghiệp vụ thành mô hình quan hệ, hai câu rất dễ xuất hiện:

- “Một khách hàng có **nhiều số điện thoại**.”
- “Một địa chỉ gồm **số nhà/đường, khu vực, thành phố, mã bưu chính và quốc gia**.”

Câu thứ nhất mô tả **thuộc tính nhiều giá trị (multivalued attribute)**; câu thứ hai mô tả **thuộc tính phức hợp (composite attribute)**. Chúng giải quyết **hai trục khác nhau**: *một thực thể có bao nhiêu giá trị?* và *một giá trị được cấu thành từ những phần nào?* Một thuộc tính có thể đồng thời nhiều giá trị **và** phức hợp, ví dụ một khách hàng có nhiều địa chỉ, mỗi địa chỉ lại gồm nhiều thành phần.

Bài học trong chương **Mô hình quan hệ** của module **DATABASE_DATA_MODELING** tập trung vào cách nhận diện đúng ngữ nghĩa, chuyển mô hình khái niệm thành bảng, khóa và ràng buộc, chuẩn hóa những nhóm giá trị lặp, thiết kế chỉ mục và đối chiếu với document, đồ thị hoặc mô hình phân tích khi cần.

## 1. Phân biệt bằng ví dụ nghiệp vụ

Giả sử một hệ thống bán hàng lưu thông tin khách hàng:

~~~text
Khách hàng 101: Lan
  Tên hiển thị: "Nguyễn Thị Lan"
  Số điện thoại:
    +84901234567  (di động, chính)
    +842838221100 (cơ quan)
  Địa chỉ giao hàng:
    Địa chỉ 1:
      Dòng địa chỉ: "12 Nguyễn Huệ"
      Thành phố: "TP. Hồ Chí Minh"
      Quốc gia: "VN"
    Địa chỉ 2:
      Dòng địa chỉ: "8 Trần Phú"
      Thành phố: "Đà Nẵng"
      Quốc gia: "VN"
~~~

Có ba nhận định độc lập:

1. **Số điện thoại là nhiều giá trị:** một khách hàng có thể có 0, 1 hoặc nhiều số; mỗi số có thể có nhãn và trạng thái “số chính”.
2. **Địa chỉ là phức hợp:** mỗi địa chỉ có nhiều trường con với ý nghĩa và quy tắc riêng.
3. **Danh sách địa chỉ là nhiều giá trị của một cấu trúc phức hợp:** khách hàng có thể có nhiều *bộ* địa chỉ, và các thành phần của một bộ phải được giữ **đi cùng nhau**.

| Khái niệm | Ví dụ | Bản chất | Câu hỏi cần hỏi |
| --- | --- | --- | --- |
| Thuộc tính đơn giá trị | Ngày sinh (theo hồ sơ hiện tại) | Tối đa một giá trị cho một thực thể | Có bắt buộc có giá trị không? |
| Thuộc tính nhiều giá trị | Các số điện thoại liên hệ | Một tập hoặc danh sách giá trị theo chủ thể | Số lượng tối đa? Có cho lặp? Có thứ tự? |
| Thuộc tính phức hợp | Một địa chỉ bưu chính | Một giá trị gồm nhiều thành phần | Cần tra cứu, kiểm tra hoặc cập nhật phần nào? |
| Phức hợp và nhiều giá trị | Các địa chỉ giao hàng | Nhiều bộ giá trị có cấu trúc | Nhóm trường nào thuộc cùng một địa chỉ? |
| Thuộc tính có cấu trúc nhưng là thực thể | Một OrderLine có sản phẩm, số lượng và giá | Có định danh/quan hệ/vòng đời riêng | Có nên tách thành thực thể thay vì coi là thuộc tính? |

Trong ERD kiểu Chen, thuộc tính nhiều giá trị thường được vẽ bằng **hình elip đôi**; thuộc tính phức hợp là **một thuộc tính được nối với các thuộc tính thành phần**. Ký pháp khác nhau giữa công cụ, nên các ràng buộc số lượng, bắt buộc và định danh vẫn cần được ghi rõ bằng lời.

## 2. Thuộc tính nhiều giá trị: không phải “một chuỗi chứa nhiều phần tử”

### 2.1. Định nghĩa và số lượng được phép

Với khách hàng \(c\), đặt \(Phones(c)\) là tập số điện thoại hợp lệ của người đó. Nếu nghiệp vụ cho phép nhiều số, thì:

- \( |Phones(c)| = 0 \): khách hàng chưa cung cấp số, **nếu nghiệp vụ cho phép**.
- \( |Phones(c)| = 1 \): có một số.
- \( |Phones(c)| \ge 2 \): có nhiều số.

“Tập” là cách hình dung thường dùng trong mô hình khái niệm; trong hệ thống thật phải quyết định **có phân biệt thứ tự, nhãn, nguồn, thời điểm và bản ghi lặp** không. Ví dụ, các số điện thoại có thể được sắp theo ưu tiên liên hệ; thứ tự ưu tiên là **một thuộc tính riêng** của từng mối liên hệ, không được suy ra từ vị trí hàng trong bảng.

Có thể mô tả bội số bằng các khoảng:

| Bội số theo nghiệp vụ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| 0..1 | Tùy chọn, tối đa một | Mã số thuế cá nhân nếu không phải ai cũng có |
| 1..1 | Bắt buộc, đúng một | Mã tiền tệ của một khoản tiền hợp lệ |
| 0..N | Không bắt buộc, có thể nhiều | Số điện thoại liên hệ |
| 1..N | Ít nhất một, có thể nhiều | Một đơn hàng **đã xác nhận** phải có ít nhất một dòng hàng |
| 0..K | Có thể nhiều nhưng giới hạn K | Tối đa ba liên hệ khẩn cấp nếu chính sách quy định |

Cần xác định bội số **theo đối tượng và thời điểm**. Một đơn hàng ở trạng thái bản nháp có thể có 0 dòng; cùng đơn hàng khi đã xác nhận có thể bắt buộc có từ 1 dòng trở lên.

### 2.2. Ba cách lưu dễ nhầm lẫn

Giả sử lưu số điện thoại vào bảng \`customers\`.

**Cách A — gộp thành chuỗi:**

~~~text
customer_id | phones
101         | "+84901234567,+842838221100"
~~~

Dễ nhập ban đầu nhưng khó bảo đảm từng phần tử hợp lệ, chống trùng, gán nhãn và tìm kiếm chính xác. Nếu dữ liệu có dấu phân cách nằm trong giá trị, việc tách chuỗi càng dễ sai.

**Cách B — thêm cột lặp:**

~~~text
customer_id | phone_1      | phone_2       | phone_3
101         | +84901234567 | +842838221100  | NULL
~~~

Thiết kế buộc một giới hạn số lượng cứng, phải thay lược đồ khi xuất hiện \`phone_4\`, khó kiểm tra duy nhất trên tất cả vị trí và làm truy vấn tìm số phức tạp. Nhiều cột cùng ý nghĩa chỉ khác số thứ tự là dấu hiệu nên xem lại mô hình.

**Cách C — tách thành quan hệ con:**

~~~text
customers
  101 | Nguyễn Thị Lan

customer_phones
  101 | +84901234567  | MOBILE | chính
  101 | +842838221100 | WORK   | phụ
~~~

Mỗi hàng biểu diễn **một giá trị trong ngữ cảnh khách hàng**. Một khóa ghép hoặc khóa riêng có ràng buộc duy nhất bảo vệ việc lưu trùng, còn cột metadata diễn đạt nhãn, ưu tiên và trạng thái.

Tách bảng là lựa chọn phổ biến cho một thuộc tính nhiều giá trị cần **lọc, ràng buộc, cập nhật độc lập hoặc tham chiếu riêng**. Nó không đồng nghĩa rằng mọi cặp cha–con đều phải xóa cùng nhau; đó là quyết định về vòng đời và chính sách lưu trữ.

## 3. Thuộc tính phức hợp: chia thành phần theo cách sử dụng

Một thuộc tính phức hợp đại diện cho **một giá trị có cấu trúc nội bộ**. Ví dụ \`postal_address\` có:

~~~text
PostalAddress
├── recipient_name
├── address_line1
├── address_line2 (tùy chọn)
├── locality / city
├── region (tùy quốc gia)
├── postal_code (tùy quốc gia)
└── country_code
~~~

Nếu cần tra cứu theo quốc gia, xác minh mã bưu chính, tạo nhãn giao hàng hoặc thống kê theo thành phố, những thành phần này cần ý nghĩa riêng và có thể được lưu thành các cột riêng.

### 3.1. Không phải cứ có cấu trúc là cần bảng riêng

Một khách hàng có **đúng một địa chỉ đăng ký** và mọi trường được đọc/cập nhật cùng hồ sơ, có thể lưu:

~~~sql
CREATE TABLE registered_customers (
    customer_id     BIGINT PRIMARY KEY,
    customer_name   TEXT NOT NULL,
    address_line1   TEXT NOT NULL,
    address_line2   TEXT,
    city            TEXT NOT NULL,
    region          TEXT,
    postal_code     TEXT,
    country_code    VARCHAR(2) NOT NULL
                    CHECK (country_code ~ '^[A-Z]{2}$')
);
~~~

Các cột địa chỉ mô tả **một địa chỉ** của **một khách hàng**. Chúng không tự làm bảng vi phạm chuẩn hóa chỉ vì có nhiều cột cùng nhóm.

Tách địa chỉ thành bảng riêng phù hợp hơn khi địa chỉ:

- có **nhiều bản ghi** trên một khách hàng;
- có **định danh riêng** hoặc được nhiều đối tượng tham chiếu;
- có **vòng đời riêng** như xác minh, khóa, lịch sử;
- có quan hệ riêng tới khu vực/đơn vị hành chính;
- cần cập nhật hoặc phân quyền khác hồ sơ khách hàng.

### 3.2. Tránh chia thành phần quá mức

Không phải lúc nào tách \`full_name\` thành \`first_name\` và \`last_name\` cũng phản ánh đúng các hệ tên gọi trên thế giới. Cũng không phải địa chỉ ở mọi quốc gia đều có số nhà, phường, quận và mã bưu chính theo cùng một cấu trúc.

Quy tắc thực tế: **tách khi thành phần có ý nghĩa nghiệp vụ, cần kiểm tra riêng hoặc thường xuyên được tìm kiếm/cập nhật riêng**. Giữ trường tự do như \`address_line1\` khi dữ liệu không thể phân tách đáng tin cậy. Tránh áp các ràng buộc địa phương cho toàn bộ khách hàng quốc tế.

Mã bưu chính nên dùng **chuỗi ký tự**, không phải số nguyên: nó có thể chứa số 0 ở đầu, chữ cái, khoảng trắng hoặc dấu gạch theo quốc gia.

### 3.3. Khi trường phức hợp là giá trị không thể tách tùy tiện

Một khoản tiền thường được hiểu là bộ **(giá trị số, đơn vị tiền tệ)**. Hai trường có thể lưu trên cùng hàng, nhưng phải **đi cùng nhau** và không được hiểu số tiền nếu mất đơn vị.

~~~sql
CREATE TABLE product_prices (
    product_id   BIGINT PRIMARY KEY,
    amount       NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    currency     VARCHAR(3) NOT NULL
                 CHECK (currency ~ '^[A-Z]{3}$')
);
~~~

Nếu giá là tùy chọn trong một mô hình khác, cần quyết định liệu hai thành phần đều NULL hay đều có giá trị. Một cách kiểm soát tính có/không đồng thời là:

~~~sql
-- Ví dụ khi amount và currency đều được phép NULL:
CHECK ((amount IS NULL) = (currency IS NULL))
~~~

Ràng buộc này ngăn có amount mà thiếu currency hoặc ngược lại; nó **không thay thế** kiểm tra miền tiền tệ, độ chính xác và chính sách giá của hệ thống.

## 4. Thuộc tính vừa nhiều giá trị vừa phức hợp

“Một khách hàng có nhiều địa chỉ” là ví dụ điển hình. Không thể biến mỗi thành phần thành một mảng riêng:

~~~json
{
  "streets": ["12 Nguyễn Huệ", "8 Trần Phú"],
  "cities": ["TP. Hồ Chí Minh", "Đà Nẵng"]
}
~~~

Vì khi thêm/xóa/sắp xếp một mảng mà quên mảng kia, hệ thống sẽ ghép sai đường với thành phố. Mỗi **bộ địa chỉ** phải được lưu như một đơn vị có cấu trúc:

~~~json
{
  "addresses": [
    {
      "line1": "12 Nguyễn Huệ",
      "city": "TP. Hồ Chí Minh",
      "country": "VN"
    },
    {
      "line1": "8 Trần Phú",
      "city": "Đà Nẵng",
      "country": "VN"
    }
  ]
}
~~~

Trong quan hệ, cách biểu diễn phổ biến là **một hàng cho mỗi địa chỉ**, mỗi hàng có các cột thành phần và một khóa trỏ tới khách hàng.

Đây là điểm quan trọng về **ràng buộc nhóm**: phải biết thành phần nào thuộc **cùng một lần xuất hiện** của giá trị phức hợp. Không nên tách thành các bảng \`customer_streets\` và \`customer_cities\` độc lập nếu chúng không có khóa liên kết cho từng bộ địa chỉ.

## 5. Thiết kế lược đồ PostgreSQL cho khách hàng, điện thoại và địa chỉ

Ví dụ sau có các giả định cụ thể:

- Mỗi khách hàng có thể có **0..N số điện thoại**.
- Với một khách hàng, cùng số chuẩn hóa chỉ xuất hiện **một lần**.
- Mỗi khách hàng có **tối đa một số điện thoại chính**, nhưng có thể chưa chọn số chính.
- Mỗi khách hàng có thể có **0..N địa chỉ**; mỗi địa chỉ có định danh riêng và nhiều trường thành phần.
- Một địa chỉ có loại \`SHIPPING\`, \`BILLING\` hoặc \`OTHER\`. Với **mỗi loại địa chỉ** của một khách hàng, được phép có **tối đa một địa chỉ mặc định**.
- Số điện thoại có thể được **nhiều khách hàng cùng sử dụng** (gia đình, tổng đài); không đặt UNIQUE toàn hệ thống trên số.

### 5.1. Các bảng và ràng buộc

~~~sql
-- PostgreSQL. BY DEFAULT cho phép gán ID cố định trong ví dụ học tập.
CREATE TABLE customers (
    customer_id  BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL
                 CHECK (btrim(display_name) <> '')
);

CREATE TABLE customer_phones (
    customer_id BIGINT NOT NULL
                REFERENCES customers(customer_id) ON DELETE CASCADE,
    phone_e164  TEXT NOT NULL
                CHECK (phone_e164 ~ '^\+[1-9][0-9]{1,14}$'),
    phone_kind  TEXT NOT NULL DEFAULT 'OTHER'
                CHECK (phone_kind IN ('MOBILE', 'WORK', 'HOME', 'OTHER')),
    is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (customer_id, phone_e164)
);

CREATE UNIQUE INDEX uq_customer_one_primary_phone
ON customer_phones (customer_id)
WHERE is_primary;

CREATE TABLE customer_addresses (
    address_id     BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id    BIGINT NOT NULL
                   REFERENCES customers(customer_id) ON DELETE CASCADE,
    address_kind   TEXT NOT NULL
                   CHECK (address_kind IN ('SHIPPING', 'BILLING', 'OTHER')),
    recipient_name TEXT NOT NULL
                   CHECK (btrim(recipient_name) <> ''),
    address_line1  TEXT NOT NULL
                   CHECK (btrim(address_line1) <> ''),
    address_line2  TEXT,
    city           TEXT NOT NULL
                   CHECK (btrim(city) <> ''),
    region         TEXT,
    postal_code    TEXT,
    country_code   VARCHAR(2) NOT NULL
                   CHECK (country_code ~ '^[A-Z]{2}$'),
    is_default     BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE UNIQUE INDEX uq_customer_default_address_by_kind
ON customer_addresses (customer_id, address_kind)
WHERE is_default;

CREATE INDEX idx_customer_addresses_customer_kind
ON customer_addresses (customer_id, address_kind);
~~~

Phân tích:

| Cơ chế | Bảo vệ điều gì? | Điều **chưa** được bảo vệ |
| --- | --- | --- |
| PK \`customers.customer_id\` | Mỗi khách hàng có một định danh | Khách hàng bắt buộc có điện thoại hay không |
| PK \`customer_phones(customer_id, phone_e164)\` | Không lặp cùng số với cùng khách hàng | Không cấm số đó thuộc nhiều khách hàng |
| FK \`customer_phones.customer_id\` | Không có điện thoại mồ côi | Số chính phải tồn tại khi khách hàng hoạt động |
| Unique index có \`WHERE is_primary\` | Tối đa một số chính cho mỗi khách hàng | **Ít nhất một** số chính |
| PK \`customer_addresses.address_id\` | Mỗi bản ghi địa chỉ có định danh riêng | Hai địa chỉ vật lý giống nhau có được trùng hay không |
| Unique index \`(customer_id, address_kind)\` khi \`is_default\` | Tối đa một địa chỉ mặc định **trong mỗi loại** | Khách hàng bắt buộc có địa chỉ mặc định |
| Các \`CHECK\` thành phần | Mã loại, khuôn dạng cơ bản, trường bắt buộc | Xác minh số điện thoại thật hoặc phát được thư đến địa chỉ |

Biểu thức số điện thoại chỉ kiểm tra **hình dạng gần với E.164**: có dấu \`+\`, mã số hợp lệ về hình thức và tổng số chữ số giới hạn. Nó không kiểm chứng số được cấp phát, số đang hoạt động hoặc số thuộc quốc gia nào. Quy trình xác thực số liên hệ có thể cần OTP, trạng thái xác minh và lịch sử riêng.

\`ON DELETE CASCADE\` trong bài thể hiện chính sách: khi **xóa vật lý hồ sơ khách hàng**, các điểm liên hệ phụ thuộc bị xóa theo. Đây **không phải lựa chọn bắt buộc** trong mọi hệ thống. Nếu địa chỉ/số điện thoại phải phục vụ kiểm toán hoặc hồ sơ pháp lý, cần quyết định bảo tồn, ẩn danh hoặc hạn chế xóa tùy nghiệp vụ.

### 5.2. Dữ liệu ví dụ và các truy vấn

~~~sql
INSERT INTO customers (customer_id, display_name)
VALUES (101, 'Nguyễn Thị Lan');

INSERT INTO customer_phones
    (customer_id, phone_e164, phone_kind, is_primary)
VALUES
    (101, '+84901234567', 'MOBILE', TRUE),
    (101, '+842838221100', 'WORK', FALSE);

INSERT INTO customer_addresses
    (address_id, customer_id, address_kind, recipient_name,
     address_line1, city, country_code, is_default)
VALUES
    (501, 101, 'SHIPPING', 'Nguyễn Thị Lan',
     '12 Nguyễn Huệ', 'TP. Hồ Chí Minh', 'VN', TRUE),
    (502, 101, 'SHIPPING', 'Nguyễn Thị Lan',
     '8 Trần Phú', 'Đà Nẵng', 'VN', FALSE);
~~~

Lấy các số của khách hàng:

~~~sql
SELECT phone_e164, phone_kind, is_primary
FROM customer_phones
WHERE customer_id = 101
ORDER BY is_primary DESC, phone_e164;
~~~

Lấy địa chỉ giao hàng mặc định:

~~~sql
SELECT address_id, recipient_name, address_line1,
       city, region, postal_code, country_code
FROM customer_addresses
WHERE customer_id = 101
  AND address_kind = 'SHIPPING'
  AND is_default;
~~~

Tìm khách hàng có số điện thoại nhất định:

~~~sql
SELECT c.customer_id, c.display_name
FROM customers AS c
JOIN customer_phones AS p ON p.customer_id = c.customer_id
WHERE p.phone_e164 = '+84901234567';
~~~

Vì khóa chính của \`customer_phones\` bắt đầu bằng \`customer_id\`, nó hỗ trợ tốt truy vấn số điện thoại theo **một khách hàng**. Nếu thường xuyên tra cứu theo **số điện thoại trước**, cân nhắc chỉ mục đảo:

~~~sql
CREATE INDEX idx_customer_phones_by_phone
ON customer_phones (phone_e164, customer_id);
~~~

Không cần tạo thêm chỉ mục chỉ trên \`customer_id\` của bảng \`customer_phones\` nếu khóa chính ghép \`(customer_id, phone_e164)\` đã đáp ứng truy vấn. Đánh giá chỉ mục từ truy vấn thực tế và \`EXPLAIN\`, vì thêm chỉ mục cũng làm tăng chi phí ghi.

### 5.3. Chuyển số điện thoại chính một cách nhất quán

Với ràng buộc **tối đa một số chính**, để đổi số chính sang một số đã tồn tại, một giao dịch có thể xóa cờ cũ trước rồi đặt cờ mới:

~~~sql
BEGIN;

-- Tuần tự hóa việc đổi số chính của cùng khách hàng,
-- với điều kiện mọi luồng cập nhật đều tuân thủ quy ước này.
SELECT customer_id
FROM customers
WHERE customer_id = 101
FOR UPDATE;

UPDATE customer_phones
SET is_primary = FALSE
WHERE customer_id = 101 AND is_primary;

UPDATE customer_phones
SET is_primary = TRUE
WHERE customer_id = 101
  AND phone_e164 = '+842838221100';

-- Ứng dụng cần xác nhận UPDATE thứ hai tác động đúng một hàng.
COMMIT;
~~~

Nếu số đích không tồn tại, lệnh UPDATE thứ hai sẽ tác động **0 hàng**, và kết quả có thể không còn số chính. Phải kiểm tra số hàng được cập nhật, điều kiện trạng thái và **rollback** nếu thao tác không đạt quy tắc nghiệp vụ. Phép khóa hàng khách hàng làm các luồng tham gia cùng quy ước cập nhật tuần tự hơn; nếu có writer bỏ qua quy ước, phải có cơ chế bảo vệ nhất quán khác.

Nếu nghiệp vụ đòi **mọi khách hàng đã kích hoạt có ít nhất một số chính**, unique index ở trên **không đủ**: nó kiểm soát mức tối đa, không kiểm soát mức tối thiểu. Quy tắc “ít nhất một hàng con đạt điều kiện” là ràng buộc **xuyên bảng/nhiều hàng**, thường cần thiết kế lại, quy trình chuyển trạng thái và cơ chế kiểm tra giao dịch phù hợp.

## 6. Nhận diện các quan hệ có thuộc tính riêng

Một giá trị lặp đơn giản thường có thể lưu bằng \`(owner_id, value)\`, nhưng khi **bản ghi lặp** có nhiều thuộc tính, quan hệ hoặc vòng đời, nên xét mô hình thực thể liên kết.

### 6.1. Sở thích hoặc nhãn từ một danh mục dùng chung

Giả sử mỗi sản phẩm có nhiều nhãn và một nhãn được gán cho nhiều sản phẩm. Đây là quan hệ **nhiều–nhiều**, không phải một chuỗi nhãn trên Product:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name       TEXT NOT NULL
);

CREATE TABLE tags (
    tag_id BIGINT PRIMARY KEY,
    tag_name TEXT NOT NULL UNIQUE
);

CREATE TABLE product_tags (
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    tag_id     BIGINT NOT NULL REFERENCES tags(tag_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id, tag_id)
);

CREATE INDEX idx_product_tags_tag_product
ON product_tags (tag_id, product_id);
~~~

\`product_tags\` lưu **tư cách gán nhãn**; \`assigned_at\` là thuộc tính của lần liên kết. \`tags\` cho phép kiểm soát tên nhãn và chia sẻ cùng một định danh nhãn giữa nhiều sản phẩm.

Nếu thực tế chỉ là các từ khóa văn bản tự do không dùng chung danh mục, một bảng \`product_keywords(product_id, keyword)\` có thể đủ. Nên chọn cấu trúc theo ngữ nghĩa và yêu cầu truy vấn, không mặc định cứ thấy danh sách là cần một bảng danh mục dùng chung.

### 6.2. Dòng đơn hàng không chỉ là “mảng sản phẩm”

Một đơn hàng có nhiều dòng; mỗi dòng chứa số lượng, đơn giá tại thời điểm mua, chiết khấu và có thể cùng một sản phẩm xuất hiện ở nhiều dòng theo ngữ cảnh.

~~~sql
CREATE TABLE order_lines (
    order_id    BIGINT NOT NULL,
    line_no     INTEGER NOT NULL CHECK (line_no > 0),
    product_id  BIGINT NOT NULL REFERENCES products(product_id),
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Bảng minh họa chưa có bảng Orders nên chưa khai báo FK cho \`order_id\`; trong lược đồ đầy đủ phải có FK đến Order tương ứng. Khóa \`(order_id, line_no)\` biểu diễn vị trí dòng **trong đơn hàng**. Nếu chỉ dùng \`(order_id, product_id)\`, ta đang áp giả định mỗi sản phẩm xuất hiện tối đa một lần trong một đơn — không phải hệ thống nào cũng có quy tắc đó.

Thuộc tính \`unit_price\` thuộc **giao dịch**, không nên thay thế bằng giá sản phẩm hiện tại. Một trường hợp lặp có cấu trúc và có lịch sử riêng thường đáng được xem như **thực thể chi tiết**, không chỉ là thuộc tính nhiều giá trị.

## 7. Tránh nhân bản dòng khi truy vấn nhiều thuộc tính nhiều giá trị

Một khách hàng có **2 điện thoại** và **2 địa chỉ**. Nếu nối cả hai bảng con bằng JOIN rồi đếm, một khách hàng có thể tạo ra **2 × 2 = 4 dòng**:

~~~sql
SELECT c.customer_id, p.phone_e164, a.address_id
FROM customers AS c
LEFT JOIN customer_phones AS p
  ON p.customer_id = c.customer_id
LEFT JOIN customer_addresses AS a
  ON a.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

Đây là **tổ hợp các phần tử độc lập** của hai tập, không có nghĩa khách hàng có bốn số điện thoại hoặc bốn địa chỉ. Nếu tính số lượng bằng \`COUNT(p.phone_e164)\` trên JOIN này, kết quả sẽ sai.

### 7.1. Đếm riêng từng quan hệ

~~~sql
SELECT c.customer_id, c.display_name,
       (SELECT COUNT(*)
        FROM customer_phones AS p
        WHERE p.customer_id = c.customer_id) AS phone_count,
       (SELECT COUNT(*)
        FROM customer_addresses AS a
        WHERE a.customer_id = c.customer_id) AS address_count
FROM customers AS c
WHERE c.customer_id = 101;
-- 2 số điện thoại, 2 địa chỉ.
~~~

Truy vấn con tương quan, tổng hợp trước khi JOIN hoặc các phép \`EXISTS\` thường rõ nghĩa hơn khi kiểm tra tập con độc lập. \`COUNT(DISTINCT ...)\` cũng có thể sửa một số trường hợp, nhưng không thay thế được việc xác định đúng **mức hạt dữ liệu**.

### 7.2. Trả kết quả dạng document ở lớp đọc

Một API cần một bản ghi khách hàng cùng hai danh sách có thể tổng hợp từng tập trước:

~~~sql
SELECT c.customer_id, c.display_name,
       COALESCE(p.phones, '[]'::jsonb) AS phones,
       COALESCE(a.addresses, '[]'::jsonb) AS addresses
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               jsonb_build_object(
                   'number', ph.phone_e164,
                   'kind', ph.phone_kind,
                   'isPrimary', ph.is_primary
               )
               ORDER BY ph.phone_e164
           ) AS phones
    FROM customer_phones AS ph
    WHERE ph.customer_id = c.customer_id
) AS p ON TRUE
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               jsonb_build_object(
                   'id', ad.address_id,
                   'line1', ad.address_line1,
                   'city', ad.city,
                   'country', ad.country_code
               )
               ORDER BY ad.address_id
           ) AS addresses
    FROM customer_addresses AS ad
    WHERE ad.customer_id = c.customer_id
) AS a ON TRUE
WHERE c.customer_id = 101;
~~~

Ở đây \`jsonb_agg\` là **định dạng kết quả truy vấn** cho ứng dụng, không bắt buộc phải thay đổi cách lưu cơ sở dữ liệu. Mỗi tập được tổng hợp riêng nên không nhân hai bảng con với nhau.

## 8. Liên hệ với chuẩn hóa và phụ thuộc hàm

### 8.1. Chuẩn 1 (1NF) cần được hiểu đúng

Trong giới thiệu mô hình quan hệ, người ta thường mô tả 1NF là các ô chứa giá trị **nguyên tử theo miền đã chọn** và không có nhóm cột lặp. Vì vậy bảng có \`phone_1, phone_2, phone_3\` hoặc một chuỗi ghép nhiều số thường là dấu hiệu mô hình chưa thuận tiện để diễn đạt **quan hệ một–nhiều**.

Tuy nhiên, “nguyên tử” **phụ thuộc miền và phép toán cần hỗ trợ**. Trong các hệ SQL hiện đại, \`ARRAY\`, \`JSON\` hoặc giá trị phức hợp có thể là **một giá trị có kiểu** được lưu trong một ô. Không nên khẳng định máy móc “mọi JSON/ARRAY đều vi phạm 1NF” mà không nêu mô hình quan hệ và cách sử dụng. Câu hỏi thực tiễn quan trọng hơn là:

- Cần **lọc/ghép** theo từng phần tử không?
- Cần **FK, UNIQUE, CHECK, index** ở mức phần tử không?
- Cần **cập nhật một phần tử** độc lập hoặc ghi lịch sử riêng không?
- Có cần biểu diễn **một–nhiều/nhiều–nhiều** và giới hạn bội số không?
- Dữ liệu phức hợp có thật sự là **một giá trị** hay đang che giấu nhiều thực thể?

Nếu câu trả lời nghiêng về thao tác quan hệ trên phần tử, bảng con thường cung cấp cơ chế toàn vẹn và truy vấn rõ ràng hơn.

### 8.2. Phụ thuộc hàm và khóa

Trong bảng \`customers\`, ta kỳ vọng:

~~~text
customer_id → display_name
~~~

Trong \`customer_phones\`, sau khi quy định một số chuẩn hóa xuất hiện tối đa một lần trong một khách hàng:

~~~text
(customer_id, phone_e164) → phone_kind, is_primary
~~~

**Không** có phụ thuộc hàm \`customer_id → phone_e164\`, vì một khách hàng có thể có nhiều số. Việc nhét phone_e164 vào một hàng khách hàng duy nhất dưới dạng một thuộc tính đơn sẽ khiến biểu diễn không tương ứng với bội số nghiệp vụ.

Với \`customer_addresses\`, có thể dùng:

~~~text
address_id → customer_id, address_kind, recipient_name,
             address_line1, city, region, postal_code,
             country_code, is_default
~~~

Không nên mặc định **(customer_id, address_line1, city)** là khóa duy nhất: có thể có hai mục đích/phiên bản hoặc hai bộ địa chỉ cố ý giống phần hiển thị. Khóa tự nhiên chỉ nên chọn khi thực sự ổn định và duy nhất theo quy tắc.

### 8.3. Khi hai tập thuộc tính nhiều giá trị độc lập

Giả sử hệ thống lưu **nhiều số điện thoại** và **nhiều chứng chỉ** của một nhân viên. Hai tập độc lập, không có mối quan hệ ghép cặp từng số với từng chứng chỉ. Nếu dồn tất cả vào bảng:

~~~text
employee_id | phone | certificate
7           | P1    | C1
7           | P1    | C2
7           | P2    | C1
7           | P2    | C2
~~~

Bảng nhân tích Descartes tạo dữ liệu dư thừa. Việc xóa chứng chỉ C2 sẽ phải xóa hai hàng; thêm một số điện thoại mới có thể cần sao chép toàn bộ chứng chỉ.

Điều này liên quan đến **phụ thuộc đa trị (multivalued dependency)** và lý do thực tế để tách các quan hệ độc lập, có liên hệ với **chuẩn 4 (4NF)**. Cách diễn đạt đúng là:

~~~text
employee_phones(employee_id, phone)
employee_certificates(employee_id, certificate_id)
~~~

Ngược lại, nếu mỗi số điện thoại thực sự gắn với **một chứng chỉ xác minh riêng**, có một liên hệ giữa hai thứ và không thể tách tùy tiện. Chuẩn hóa phải dựa trên **phụ thuộc nghiệp vụ thật**, không chỉ từ sự xuất hiện của nhiều cột.

## 9. Tính tùy chọn, NULL, danh sách rỗng và lịch sử

### 9.1. Không có hàng con khác với một hàng con có giá trị NULL

Nếu khách hàng **không có số điện thoại**, thông thường bảng \`customer_phones\` không có hàng tương ứng. Không nên thêm:

~~~text
customer_id=101, phone_e164=NULL
~~~

rồi coi đó là “một số chưa biết”, nhất là khi khóa và ràng buộc đã xác định một hàng phải là **một số hợp lệ**.

Các trạng thái có thể cần phân biệt:

- **Chưa cung cấp:** không có hàng; có thể theo dõi trạng thái yêu cầu bổ sung.
- **Không áp dụng:** nghiệp vụ xác nhận đối tượng không cần thông tin này.
- **Chưa xác minh:** có hàng với giá trị và trường \`verification_status\` riêng.
- **Đã ngừng sử dụng:** giữ hàng lịch sử hoặc có \`valid_to\`, không nhất thiết xóa mất dấu vết.

Cần phát biểu rõ hệ thống có cho phép 0 số/địa chỉ và tại thời điểm nào. Nếu trạng thái ACTIVE bắt buộc có số liên hệ đã xác minh, đây là điều kiện **xuyên bảng và theo trạng thái**, không phải chỉ cần \`NOT NULL\` trên bảng con.

### 9.2. Giá trị thay đổi theo thời gian

Số điện thoại, địa chỉ nhận hàng và người nhận có thể thay đổi. Nếu phải biết **số nào hợp lệ tại thời điểm t**, cần mô hình thời gian:

~~~sql
-- Minh họa một hướng lưu lịch sử của các giai đoạn sử dụng số.
CREATE TABLE customer_phone_periods (
    period_id  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    phone_e164 TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to   TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

Ví dụ chỉ kiểm tra khoảng thời gian mỗi hàng hợp lệ; **chưa cấm các khoảng chồng lấp** cho cùng khách hàng/số. Nếu nghiệp vụ cần một số chỉ có một giai đoạn hiệu lực tại mỗi thời điểm, phải bổ sung kiểm soát chồng lấp khoảng bằng cơ chế tương ứng của DBMS (chẳng hạn exclusion constraint trong PostgreSQL), hoặc giao dịch đảm bảo nhất quán.

Một **địa chỉ giao hàng đã dùng trong đơn hàng** thường cần được lưu thành **bản chụp giao dịch (snapshot)** hoặc tham chiếu tới một **phiên bản địa chỉ bất biến**. Nếu chỉ tham chiếu địa chỉ “hiện tại” của khách hàng, khi khách sửa địa chỉ có thể làm mất sự thật về nơi đã giao hàng trước đây.

### 9.3. Số lượng tối thiểu là quy tắc của tập hàng

\`UNIQUE ... WHERE is_primary\` chỉ giới hạn **tối đa một số chính**; nó không bắt buộc **phải có một số chính**. Tương tự, FK từ \`customer_phones\` lên \`customers\` chỉ xác nhận mỗi số thuộc một khách hàng tồn tại, **không** xác nhận mọi khách hàng có ít nhất một số.

Khi nghiệp vụ yêu cầu mức tối thiểu **1..N**, hãy xác định điều kiện áp dụng (ví dụ chỉ với tài khoản đã kích hoạt) và dùng cơ chế đáng tin cậy: thay đổi cấu trúc để kiểm soát cùng hàng khi thích hợp, quy trình ghi trong giao dịch có kiểm tra cuối giao dịch, hoặc constraint trigger được thiết kế cho thao tác thêm/sửa/xóa và cập nhật đồng thời.

Một thao tác DELETE số cuối cùng hoặc xóa địa chỉ mặc định cũng có thể khiến dữ liệu vi phạm, dù bản ghi lúc tạo ban đầu hợp lệ.

## 10. ARRAY/JSON, bảng con hay giá trị nhúng?

Một hệ quản trị hiện đại có thể lưu danh sách và đối tượng trong **một cột**. Đó có thể là lựa chọn hợp lý tùy trường hợp.

| Tiêu chí | Bảng con quan hệ | ARRAY/JSON trong một cột | Cột thành phần trên cùng bảng |
| --- | --- | --- | --- |
| Biểu diễn 0..N giá trị | Tự nhiên, mỗi giá trị một hàng | Tự nhiên trong mảng | Thường cần cột lặp hoặc giới hạn cố định |
| Thuộc tính phức hợp đơn giá trị | Có thể, nhưng thêm bảng/JOIN | Lưu thành object | **Rất phù hợp** khi cấu trúc ổn định |
| FK tới từng phần tử | FK thông thường | Thường cần cơ chế kiểm tra riêng | Có thể dùng FK nếu phần tử là cột |
| Unique ở mức từng phần tử | PK/UNIQUE | Phụ thuộc loại dữ liệu và logic | Khó nếu phần tử nằm ở nhiều cột |
| Truy vấn/tổng hợp theo phần tử | JOIN, GROUP BY, index | Hàm JSON/ARRAY và index chuyên dụng | Lọc theo cột trực tiếp |
| Cập nhật một phần tử | UPDATE/DELETE hàng tương ứng | Cập nhật document/mảng theo công nghệ | UPDATE cột |
| Thay đổi schema dữ liệu con | ALTER bảng khi thêm trường | Linh hoạt hơn, cần quản lý schema logic | ALTER bảng khi thêm trường |
| Tối ưu đọc nguyên cụm | Cần JOIN/aggregation | Có thể đọc cùng một document | Đọc một hàng |

Ví dụ một JSON document trong PostgreSQL:

~~~sql
CREATE TABLE customer_preferences (
    customer_id BIGINT PRIMARY KEY REFERENCES customers(customer_id),
    settings JSONB NOT NULL DEFAULT '{}'::jsonb
);

INSERT INTO customer_preferences (customer_id, settings)
VALUES (101, '{"notifications": {"email": true, "sms": false},
               "theme": "dark"}'::jsonb);
~~~

Một nhóm **cấu hình nhỏ, đọc cùng nhau, ít ràng buộc xuyên phần tử** có thể thích hợp lưu JSONB. Nhưng danh sách điện thoại được dùng để liên hệ, xác minh, tìm kiếm, đảm bảo duy nhất và lập lịch sử riêng thường có lợi hơn khi tách thành quan hệ con.

Nếu chọn JSONB hoặc ARRAY cho số điện thoại, cần thiết kế rõ: kiểm tra schema, phần tử trùng, chuẩn hóa số, thao tác cập nhật đồng thời, index cho tìm kiếm và phương án chuyển sang bảng quan hệ khi nhu cầu thay đổi.

## 11. Cùng một yêu cầu dưới mô hình document, đồ thị và phân tích

**Ngữ nghĩa nghiệp vụ** không đổi khi thay đổi công nghệ:

| Mô hình | Nhiều giá trị | Phức hợp | Điểm cần kiểm chứng |
| --- | --- | --- | --- |
| **Quan hệ** | Bảng con 1–N hoặc bảng liên kết N–N | Các cột cùng hàng hoặc bảng có cấu trúc | PK/FK, UNIQUE theo chủ thể, bội số, giao dịch |
| **Document** | Mảng phần tử | Object có các trường con | Schema validation, trùng phần tử, kích thước document, cập nhật nguyên tử |
| **Đồ thị** | Nhiều cạnh tới node liên hệ/địa chỉ | Thuộc tính node hoặc node địa chỉ | Loại cạnh, bội số, định danh, hạn chế cạnh lặp |
| **Phân tích/warehouse** | Bridge giữa thực thể và nhiều phân loại | Dimension các thành phần địa chỉ/khu vực | Grain của fact, nguy cơ nhân bản số liệu khi JOIN nhiều bảng con |

### 11.1. Document có mảng object

~~~json
{
  "customerId": 101,
  "name": "Nguyễn Thị Lan",
  "phones": [
    {"number": "+84901234567", "kind": "MOBILE", "primary": true},
    {"number": "+842838221100", "kind": "WORK", "primary": false}
  ],
  "addresses": [
    {
      "kind": "SHIPPING",
      "line1": "12 Nguyễn Huệ",
      "city": "TP. Hồ Chí Minh",
      "countryCode": "VN"
    }
  ]
}
~~~

Cấu trúc này **giữ mỗi địa chỉ thành một object** và nhiều số thành **một mảng**. Nếu hệ thống có cơ chế ghi document nguyên tử và thường đọc cả hồ sơ, cách tổ chức thuận tiện. Nhưng vẫn phải xác minh “tối đa một phone primary” trên **toàn mảng** và không để hai tiến trình cập nhật mất thay đổi của nhau. Không mặc định JSON Schema thông dụng sẽ tự thực thi mọi quy tắc liên phần tử.

### 11.2. Đồ thị: đừng biến dữ liệu liên hệ thành graph vô cớ

Một người dùng có nhiều số điện thoại có thể là thuộc tính mảng trên node \`Customer\`, hoặc có cạnh \`HAS_PHONE\` tới các node \`Phone\`. Chọn node/cạnh khi số điện thoại có **quan hệ riêng**, được **chia sẻ**, cần truy vấn theo mạng liên hệ hoặc có metadata của cạnh.

Nếu chỉ cần lưu vài số để gọi điện, graph database thường không đem lại giá trị rõ ràng so với bảng con hoặc document. Trong mọi trường hợp, cần đảm bảo quan hệ tới đúng chủ thể, không trùng cạnh ngoài chính sách, và kiểm soát số lượng/tính xác minh.

### 11.3. Phân tích: kiểm tra mức hạt

Một fact doanh thu ở mức **một OrderLine** nối tới Customer. Nếu nối tiếp tới bảng nhiều điện thoại và nhiều địa chỉ để phân nhóm mà không xác định mục đích, mỗi OrderLine có thể bị nhân bản trước khi tính \`SUM(amount)\`.

Phải chọn một cách kết hợp hợp lý: chỉ nối điện thoại chính/địa chỉ giao dịch cụ thể, tổng hợp ở mức khách hàng trước khi JOIN, dùng bridge và trọng số phân bổ khi có nhiều nhóm hợp lệ, hoặc khử trùng theo **fact_id** và đúng ngữ nghĩa chỉ tiêu. Không nên “chữa” bằng \`SUM(DISTINCT amount)\`: hai giao dịch khác nhau có cùng số tiền vẫn phải được đếm hai lần.

## 12. Quy trình chuyển yêu cầu thành lược đồ

Khi gặp một trường như “địa chỉ”, “số điện thoại”, “nhãn”, “kỹ năng”, “giá trị đo”, hãy làm tuần tự:

1. **Xác định chủ thể và ngữ cảnh:** giá trị thuộc Customer, Order, nhân viên, hợp đồng hay một sự kiện?
2. **Xác định bội số:** 0..1, 1..1, 0..N, 1..N hay một mức tối đa K?
3. **Tách những thành phần có ý nghĩa:** một địa chỉ gồm những trường nào, có bắt buộc theo quốc gia hay theo vai trò không?
4. **Xác định danh tính của một phần tử:** hai số giống nhau có coi là cùng một điểm liên hệ? Một địa chỉ có cần address_id không?
5. **Xác định có thứ tự hay không:** nếu có ưu tiên hoặc vị trí, lưu cột \`priority\`/\`position\` và ràng buộc thích hợp; không dựa vào thứ tự tự nhiên của hàng SQL.
6. **Tìm thuộc tính của mối liên hệ:** nhãn, thời điểm gán, trạng thái chính, hiệu lực và người xác minh thuộc về phần tử hay quan hệ?
7. **Quyết định cấu trúc:** cột đơn, nhiều cột thành phần, bảng con, bảng nối, JSON/ARRAY hoặc một thực thể độc lập.
8. **Viết ràng buộc:** PK/FK, CHECK, UNIQUE theo đúng phạm vi, số lượng tối thiểu/tối đa và quy tắc khi xóa/sửa.
9. **Thiết kế truy vấn và chỉ mục:** đọc cả tập, tra theo phần tử, tìm một phần tử mặc định, đếm, phân trang và tổng hợp.
10. **Thử dữ liệu biên và biến đổi theo thời gian:** tập rỗng, một giá trị, nhiều giá trị, số trùng, thành phần thiếu, hai thao tác đồng thời, đổi giá trị chính, lịch sử giao dịch.

Nếu có dữ liệu cũ dạng \`phone_1, phone_2\` hoặc chuỗi phân cách, việc chuyển sang bảng con nên thực hiện theo các bước: xác định quy tắc tách/chuẩn hóa; rà soát giá trị bất thường; tạo bảng và ràng buộc; chuyển dữ liệu; đối chiếu **số chủ thể**, **số phần tử hợp lệ** và các bản ghi bị loại; chuyển đường ghi/đọc có kế hoạch; cuối cùng mới loại bỏ các cột cũ. Không tự suy đoán dấu phân cách hoặc quy tắc chuẩn hóa khi dữ liệu không nhất quán.

## 13. Bài tập có hướng dẫn giải

### Bài 1. Nhận diện loại thuộc tính

**Đề bài:** Một sinh viên có một mã sinh viên, nhiều email liên hệ, một địa chỉ cư trú gồm đường–thành phố–quốc gia và nhiều chứng chỉ (mỗi chứng chỉ có mã, tổ chức cấp, ngày cấp).

**Gợi ý giải:** Mã sinh viên là đơn giá trị và có thể là khóa. Email là thuộc tính nhiều giá trị. Địa chỉ cư trú là phức hợp đơn giá trị nếu yêu cầu chỉ một địa chỉ hiện tại. Chứng chỉ là tập các phần tử có cấu trúc và vòng đời riêng, nên cân nhắc bảng \`student_certificates\`, có khóa riêng hoặc khóa ghép theo định danh chứng chỉ thực tế.

### Bài 2. Tối đa một giá trị chính

**Đề bài:** Một Customer có thể có nhiều email nhưng nhiều nhất một email chính. Bảng \`customer_emails(customer_id, email, is_primary)\` nên có những ràng buộc nào?

**Gợi ý giải:** FK tới Customer, khóa chính hoặc UNIQUE trên \`(customer_id, email)\`, \`is_primary NOT NULL DEFAULT FALSE\`, và một **partial unique index** trên \`customer_id WHERE is_primary\` trong PostgreSQL. Các ràng buộc đó chưa bảo đảm Customer luôn có một email chính.

### Bài 3. Hai tập nhiều giá trị độc lập

**Đề bài:** Nhân viên có 3 số điện thoại và 4 kỹ năng. Nếu JOIN cả hai bảng con trực tiếp rồi COUNT, có thể xuất hiện bao nhiêu hàng?

**Gợi ý giải:** **3 × 4 = 12 hàng** cho một nhân viên. Muốn số điện thoại = 3 và kỹ năng = 4, hãy tổng hợp riêng từng bảng con hoặc dùng hai truy vấn con. Khi báo cáo theo kỹ năng, không nên JOIN điện thoại nếu không có mục đích phân tích rõ ràng.

### Bài 4. Một thuộc tính phức hợp hay một thực thể?

**Đề bài:** Địa chỉ của đơn hàng cần lưu người nhận, số điện thoại, các trường đường–thành phố–quốc gia; đơn hàng phải giữ địa chỉ đã sử dụng ngay cả khi khách hàng đổi địa chỉ trong hồ sơ.

**Gợi ý giải:** Địa chỉ nhận hàng ở đây là **thông tin của giao dịch**, cần snapshot hoặc phiên bản bất biến gắn với Order. Có thể lưu các cột địa chỉ trên Order hoặc bảng \`order_shipping_addresses\` quan hệ 1–1, tùy vòng đời và số điểm giao. Không nên chỉ trỏ tới \`customer_addresses\` hiện tại rồi để thay đổi về sau làm sai lịch sử.

### Bài 5. Chọn bảng nối hay mảng JSON

**Đề bài:** Một Product có nhiều danh mục, danh mục dùng chung cho nhiều sản phẩm; cần lọc sản phẩm theo danh mục và bảo đảm danh mục tồn tại. Nên dùng gì?

**Gợi ý giải:** \`products\`, \`categories\` và bảng \`product_categories(product_id, category_id)\` với hai FK và khóa ghép là một lựa chọn mạnh. Mảng ID trong JSON có thể lưu nhưng FK tới **từng** category và việc duy trì ràng buộc thường khó hơn; chỉ chọn khi lợi ích cụ thể vượt chi phí đó.

### Bài 6. Phân biệt trùng giá trị và trùng thực thể

**Đề bài:** Hai khách hàng có cùng số tổng đài công ty. Có nên đặt UNIQUE toàn bảng trên \`phone_e164\` không?

**Gợi ý giải:** **Không**, trừ khi nghiệp vụ thật sự cấm chia sẻ số. Nếu quy tắc chỉ là “mỗi khách hàng không lưu một số hai lần”, hãy dùng UNIQUE hoặc PK trên \`(customer_id, phone_e164)\`. Cần định nghĩa đúng phạm vi duy nhất thay vì lấy giá trị trông có vẻ định danh làm khóa toàn cục.

## 14. Ghi nhớ

- **Nhiều giá trị** trả lời *một chủ thể có bao nhiêu phần tử*; **phức hợp** trả lời *mỗi phần tử có những thành phần nào*. Một thuộc tính có thể thuộc cả hai nhóm.
- Một tập phần tử cần **khóa, bội số, metadata và vòng đời** rõ ràng. Bảng con/bảng nối thường thuận tiện khi phải truy vấn và ràng buộc từng phần tử.
- Một giá trị phức hợp **đơn** có thể nằm ở nhiều cột trên **cùng một hàng**; không cần tách bảng chỉ vì nó có cấu trúc. Một danh sách các giá trị phức hợp cần giữ từng **bộ** thành phần đi cùng nhau.
- \`UNIQUE\`, \`NOT NULL\`, \`CHECK\` và FK bảo vệ những quy tắc khác nhau. “Tối đa một” không đồng nghĩa “ít nhất một”, và khóa ngoại từ con lên cha không tự buộc cha có con.
- JOIN hai tập nhiều giá trị độc lập có thể **nhân bản dòng**. Luôn xác định đúng hạt dữ liệu trước khi đếm hoặc cộng.
- ARRAY/JSON, bảng quan hệ, document và graph đều là những cách lưu hợp lệ trong hoàn cảnh thích hợp; quyết định cuối cùng phải dựa trên **ngữ nghĩa nghiệp vụ, khả năng cưỡng chế ràng buộc, kiểu truy vấn và cách dữ liệu thay đổi theo thời gian**.
