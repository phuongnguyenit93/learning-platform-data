# Thuộc tính đơn, thuộc tính phức hợp và thuộc tính nhiều giá trị

Trong module **DATABASE_DATA_MODELING**, mô hình dữ liệu bắt đầu từ việc hiểu đối tượng nghiệp vụ, ý nghĩa của dữ liệu và cách các quy tắc được bảo vệ. Sau khi xác định thực thể, bước tiếp theo là mô tả những đặc điểm mà hệ thống cần ghi nhận. Những đặc điểm đó được biểu diễn bằng **thuộc tính**.

Một thuộc tính có thể là một giá trị đơn giản, một cấu trúc gồm nhiều thành phần hoặc một tập hợp nhiều giá trị. Phân biệt đúng ba dạng này giúp mô hình phản ánh đúng nghiệp vụ, tránh nhồi nhiều thông tin vào một trường, tránh tạo cấu trúc lặp khó kiểm soát và lựa chọn cách lưu trữ phù hợp khi chuyển sang mô hình logic, document, đồ thị hoặc phân tích.

Bài học tập trung vào ba dạng thuộc tính:

- **Thuộc tính đơn (simple attribute):** không cần phân rã thành các thành phần độc lập trong phạm vi mô hình hiện tại.
- **Thuộc tính phức hợp (composite attribute):** có thể phân rã thành các thành phần nhỏ hơn, mỗi thành phần có ý nghĩa riêng.
- **Thuộc tính nhiều giá trị (multivalued attribute):** một thực thể có thể có nhiều giá trị cho cùng một loại thuộc tính.

## 1. Thuộc tính mô tả điều gì?

Thuộc tính mô tả một đặc điểm của thực thể hoặc một mối quan hệ. Ví dụ, Khách hàng có mã định danh, tên hiển thị, ngày sinh và địa chỉ liên hệ; Đơn hàng có thời điểm đặt, trạng thái và ghi chú; Dòng đơn hàng có số lượng và đơn giá tại thời điểm mua.

Mỗi thuộc tính cần có định nghĩa rõ ràng. Đừng chỉ ghi tên như “status”, “type”, “date” hoặc “code”. Hãy xác định:

- Thuộc tính mô tả điều gì trong nghiệp vụ?
- Giá trị được đo hoặc biểu diễn theo đơn vị, định dạng và miền nào?
- Giá trị có bắt buộc không, và nếu thiếu thì có ý nghĩa gì?
- Một thực thể có thể có một hay nhiều giá trị?
- Giá trị có thể phân rã thành thành phần nào?
- Ai hoặc hệ thống nào tạo và cập nhật giá trị?
- Giá trị có thay đổi theo thời gian, cần lưu lịch sử hay chỉ cần trạng thái hiện tại?
- Thuộc tính là dữ liệu gốc được ghi nhận hay giá trị suy ra từ dữ liệu khác?

Ví dụ, thuộc tính “địa chỉ giao hàng” cần xác định đó là địa chỉ tại thời điểm đặt đơn hay địa chỉ hiện tại trong hồ sơ khách hàng. Nếu đơn hàng cũ luôn phải giao đến địa chỉ đã xác nhận lúc mua, giá trị này cần được lưu như một snapshot gắn với đơn hàng. Chỉ tham chiếu địa chỉ hiện tại của khách hàng có thể làm thay đổi ý nghĩa lịch sử.

### Thuộc tính và miền giá trị

**Miền giá trị (domain)** là tập các giá trị được phép theo ý nghĩa nghiệp vụ. Miền không chỉ là kiểu kỹ thuật như VARCHAR hay INTEGER. Ví dụ:

| Thuộc tính | Miền nghiệp vụ | Kiểu triển khai có thể dùng |
|---|---|---|
| Số lượng đặt mua | Số nguyên lớn hơn 0 | INTEGER với CHECK |
| Ngày sinh | Ngày hợp lệ, có thể chưa biết | DATE, cho phép NULL nếu nghiệp vụ cho phép |
| Mã quốc gia | Mã thuộc bộ mã được chọn | CHAR/VARCHAR có quy tắc và bảng tham chiếu |
| Giá tiền | Số tiền không âm, gắn với một loại tiền | DECIMAL và currency_code |
| Trạng thái đơn | Một tập trạng thái đã định nghĩa | ENUM, VARCHAR kèm CHECK hoặc bảng danh mục |
| Điểm đánh giá | Số trong thang điểm được công bố | SMALLINT/DECIMAL với CHECK |

Kiểu dữ liệu kỹ thuật cần đủ sức biểu diễn miền nghiệp vụ và không làm mất thông tin. Ngược lại, kiểu quá rộng mà không có ràng buộc có thể cho phép dữ liệu vô nghĩa. Ví dụ, cột quantity kiểu INTEGER vẫn có thể nhận số âm nếu không có CHECK hoặc logic bảo vệ tương ứng.

## 2. Thuộc tính đơn

**Thuộc tính đơn** là thuộc tính được xem như một giá trị không cần tách thành các thành phần độc lập trong phạm vi và mục đích của mô hình. Ví dụ: số lượng, mã màu theo danh mục đã thống nhất, ngày tạo, trạng thái hoặc mã định danh.

“Đơn” không có nghĩa giá trị chỉ gồm một ký tự hoặc không thể phân tích về mặt vật lý. Một số điện thoại gồm mã quốc gia, mã vùng và số thuê bao, nhưng nếu hệ thống chỉ xác thực và gửi tin nhắn theo toàn bộ số đã chuẩn hóa, nó có thể được xem là một thuộc tính đơn trong mô hình đó. Nếu nghiệp vụ cần tìm kiếm theo mã quốc gia, phân tích vùng hoặc lưu phần mở rộng, số điện thoại có thể cần cấu trúc chi tiết hơn.

Tính đơn phụ thuộc vào cách sử dụng. Một thuộc tính có thể đơn trong mô hình này nhưng phức hợp trong mô hình khác. Vì vậy, không nên áp dụng một quy tắc phân rã cứng nhắc chỉ vì giá trị có thể được chia thành chuỗi con.

### Dấu hiệu một thuộc tính nên được xem là đơn

- Người sử dụng thường đọc, ghi và kiểm tra toàn bộ giá trị như một đơn vị.
- Các phần bên trong không có quy tắc nghiệp vụ hoặc vòng đời độc lập.
- Không cần lọc, sắp xếp, xác thực hay báo cáo riêng trên từng thành phần.
- Việc tách giá trị không làm mô hình rõ hơn hoặc không tạo thêm khả năng cần thiết.

Ví dụ:

| Thực thể | Thuộc tính đơn | Ý nghĩa |
|---|---|---|
| Đơn hàng | placed_at | Thời điểm đơn được đặt |
| Dòng đơn hàng | quantity | Số lượng sản phẩm trên dòng |
| Sản phẩm | sku | Mã sản phẩm trong phạm vi quy tắc đã xác định |
| Khách hàng | display_name | Tên hiển thị được dùng như một chuỗi |
| Bài đánh giá | rating_score | Điểm đánh giá theo thang điểm quy định |

Thuộc tính đơn vẫn cần kiểu dữ liệu, miền giá trị, tính bắt buộc và quy tắc chuẩn hóa. Chẳng hạn, mã SKU là chuỗi chứ không phải số nếu các số 0 ở đầu có ý nghĩa. Không nên chuyển một mã như “00125” thành số 125 rồi mất định dạng ban đầu.

## 3. Thuộc tính phức hợp

**Thuộc tính phức hợp** là thuộc tính có thể chia thành các thành phần mang ý nghĩa riêng. Mỗi thành phần có thể được sử dụng, kiểm tra hoặc trình bày độc lập.

Ví dụ, địa chỉ có thể gồm:

- Số nhà và tên đường.
- Phường/xã.
- Quận/huyện.
- Tỉnh/thành phố.
- Mã bưu chính.
- Quốc gia.

Tên người có thể gồm tên gọi, tên đệm và họ tùy quy ước đặt tên. Khoảng thời gian có thể gồm thời điểm bắt đầu và kết thúc. Thông tin liên hệ có thể gồm kênh, giá trị và nhãn sử dụng.

~~~mermaid
flowchart TD
    A["Địa chỉ giao hàng"] --> B["Số nhà, tên đường"]
    A --> C["Phường / xã"]
    A --> D["Quận / huyện"]
    A --> E["Tỉnh / thành phố"]
    A --> F["Mã bưu chính"]
    A --> G["Quốc gia"]
~~~

Khi mô hình hóa, có thể biểu diễn thuộc tính phức hợp như một nhóm thành phần trong sơ đồ khái niệm. Các thành phần có thể tiếp tục được phân rã nếu có ý nghĩa và nhu cầu thực tế. Tuy nhiên, không nên chia đến mức vụn vặt nếu các phần không được sử dụng riêng.

### Khi nào nên phân rã?

Nên phân rã khi một hoặc nhiều điều kiện sau xuất hiện:

- Người dùng cần tìm kiếm hoặc lọc theo thành phần.
- Mỗi thành phần có định dạng, miền giá trị hoặc quy tắc xác thực riêng.
- Một thành phần có thể được cập nhật độc lập.
- Hệ thống cần chuẩn hóa hoặc đối chiếu từng phần với danh mục chuẩn.
- Báo cáo cần tổng hợp theo thành phần.
- Các hệ thống tích hợp trao đổi từng thành phần theo hợp đồng dữ liệu.

Ví dụ, nếu cần lọc khách hàng theo tỉnh/thành phố để phân bổ khu vực bán hàng, lưu toàn bộ địa chỉ trong một chuỗi sẽ gây khó khăn. Tách tỉnh/thành phố thành thành phần có định nghĩa chuẩn sẽ hỗ trợ lọc và đối chiếu tốt hơn.

### Khi nào nên giữ nguyên một giá trị?

Nếu địa chỉ chỉ được lưu để in lên nhãn giao hàng, không có nhu cầu lọc theo từng phần và hệ thống không có danh mục địa chỉ chuẩn, một chuỗi địa chỉ tự do có thể phù hợp. Nếu sau này cần phân tích theo tỉnh/thành, nhóm có thể bổ sung các thành phần đã chuẩn hóa hoặc quy trình phân tích địa chỉ.

Đừng nhầm “thuộc tính phức hợp” với “nhiều thuộc tính độc lập”. Nếu một thực thể có địa chỉ thanh toán và địa chỉ giao hàng, đó có thể là hai thuộc tính phức hợp có vai trò khác nhau. Nếu một người có nhiều địa chỉ giao hàng, đó lại là một thuộc tính nhiều giá trị hoặc một tập thực thể Địa chỉ có quan hệ với người đó. Cần phân biệt cấu trúc bên trong của một giá trị với số lượng giá trị được phép.

### Thành phần có ý nghĩa riêng và ranh giới thực thể

Một thành phần không tự động trở thành thực thể chỉ vì có nhiều trường. Địa chỉ có thể là đối tượng giá trị gắn với khách hàng; nhưng nếu địa chỉ được chia sẻ, có trạng thái xác minh, lịch sử hiệu lực hoặc cần được tham chiếu độc lập, có thể cần mô hình hóa nó thành thực thể.

Hãy hỏi: thành phần có danh tính riêng không, có vòng đời độc lập không, có quan hệ với nhiều thực thể không và có cần được tham chiếu ở nơi khác không? Nếu không, giữ nó như thành phần của giá trị phức hợp thường đơn giản hơn.

## 4. Thuộc tính nhiều giá trị

**Thuộc tính nhiều giá trị** là thuộc tính mà một thực thể có thể có nhiều giá trị thuộc cùng một loại. Ví dụ:

- Một khách hàng có nhiều số điện thoại.
- Một nhân viên có nhiều chứng chỉ.
- Một sản phẩm có nhiều ảnh.
- Một bài viết có nhiều thẻ.
- Một người dùng tham gia nhiều nhóm.

Trong sơ đồ khái niệm, thuộc tính nhiều giá trị thường được ký hiệu bằng hình oval kép theo một số quy ước ERD. Dạng ký hiệu có thể khác nhau giữa công cụ, nhưng ý nghĩa vẫn là một thực thể có một tập giá trị cho thuộc tính đó.

~~~mermaid
flowchart TD
    C["Khách hàng"] --> N["Tên hiển thị"]
    C --> P[["Số điện thoại (nhiều giá trị)"]]
    C --> E["Email chính"]
~~~

Cần xác định rõ các quy tắc của tập giá trị:

- Có thể có tối đa bao nhiêu giá trị?
- Có bắt buộc ít nhất một giá trị không?
- Các giá trị có được trùng nhau không?
- Có thứ tự hay không?
- Có một giá trị chính/ưu tiên không?
- Mỗi giá trị có nhãn hoặc trạng thái riêng không?
- Giá trị có thời hạn hiệu lực hoặc lịch sử thay đổi không?

Ví dụ, khách hàng có thể có nhiều số điện thoại, nhưng mỗi số có thể có loại (di động, bàn), nhãn (cá nhân, công việc), trạng thái xác minh và thời điểm xác minh. Khi đó, thuộc tính “số điện thoại” không chỉ là một danh sách chuỗi. Có thể cần một thực thể liên kết ContactPoint để quản lý từng giá trị và metadata của nó.

### Không nhầm thuộc tính nhiều giá trị với thuộc tính phức hợp

Hai khái niệm trả lời hai câu hỏi khác nhau:

- **Phức hợp:** một giá trị được tạo thành từ những thành phần nào?
- **Nhiều giá trị:** một thực thể có bao nhiêu giá trị cùng loại?

Ví dụ, một địa chỉ là phức hợp vì có số nhà, đường, thành phố và quốc gia. Một khách hàng có nhiều địa chỉ là nhiều giá trị vì có nhiều địa chỉ khác nhau. Một khách hàng có nhiều địa chỉ, mỗi địa chỉ lại gồm nhiều thành phần: đây là thuộc tính nhiều giá trị mà mỗi phần tử lại là một giá trị phức hợp.

~~~mermaid
flowchart TD
    C["Khách hàng"] --> A1["Địa chỉ 1"]
    C --> A2["Địa chỉ 2"]
    C --> A3["Địa chỉ 3"]
    A1 --> S1["Số nhà / đường"]
    A1 --> D1["Quận / thành phố"]
    A1 --> K1["Quốc gia"]
    A2 --> S2["Số nhà / đường"]
    A2 --> D2["Quận / thành phố"]
    A2 --> K2["Quốc gia"]
~~~

## 5. Biểu diễn ba dạng thuộc tính trong mô hình khái niệm

Khi dựng ERD, hãy thể hiện thuộc tính theo ý nghĩa, không theo cách lưu trữ đã chọn:

| Dạng thuộc tính | Cách mô tả | Ví dụ |
|---|---|---|
| Đơn | Một tên thuộc tính và miền giá trị | quantity, placed_at, rating_score |
| Phức hợp | Một thuộc tính cha và các thành phần con | address gồm street, ward, city, country |
| Nhiều giá trị | Ký hiệu hoặc ghi chú thể hiện có tập giá trị | phone_numbers, certifications, product_images |

Một thực thể có thể đồng thời có cả ba dạng. Ví dụ Khách hàng có customer_code (đơn), legal_name (phức hợp theo quy ước tên), và contact_points (nhiều giá trị). Mô hình cần nói rõ thuộc tính nào bắt buộc, thuộc tính nào có thể thiếu và các ràng buộc trên từng thành phần hoặc từng phần tử.

Đối với một giá trị phức hợp, hãy xác định thành phần nào là bắt buộc và thành phần nào tùy chọn. Ví dụ địa chỉ quốc tế có thể không có mã bưu chính ở một số quốc gia. Không nên đặt NOT NULL cho mọi thành phần chỉ vì một ví dụ địa chỉ cụ thể có đủ thông tin.

Đối với thuộc tính nhiều giá trị, hãy ghi nhận cardinality (số lượng tối thiểu/tối đa), quy tắc duy nhất và thứ tự nếu nghiệp vụ cần. Nếu danh sách có vị trí ưu tiên, phải mô hình hóa vị trí hoặc cờ chính một cách rõ ràng; không dựa vào thứ tự ngẫu nhiên của kết quả truy vấn.

## 6. Chuyển từ khái niệm sang mô hình quan hệ

Trong mô hình quan hệ, mỗi thuộc tính cần được ánh xạ thành một hoặc nhiều cột hoặc bảng tùy cấu trúc và quy tắc.

### Thuộc tính đơn

Thuộc tính đơn thường được ánh xạ thành một cột với kiểu dữ liệu phù hợp:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    birth_date DATE,
    CONSTRAINT uq_customer_code UNIQUE (customer_code)
);
~~~

Ở đây customer_code, display_name và birth_date là các cột đơn. Kiểu dữ liệu, nullability và ràng buộc phải phản ánh miền giá trị nghiệp vụ. Ví dụ, birth_date có thể cho phép NULL nếu ngày sinh không bắt buộc phải cung cấp.

### Thuộc tính phức hợp

Một thuộc tính phức hợp thường được phân rã thành nhiều cột nếu các thành phần cần được truy vấn hoặc kiểm soát riêng:

~~~sql
CREATE TABLE customer_address (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    address_type VARCHAR(20) NOT NULL,
    street_line VARCHAR(200) NOT NULL,
    ward VARCHAR(120),
    district VARCHAR(120),
    city VARCHAR(120) NOT NULL,
    postal_code VARCHAR(20),
    country_code CHAR(2) NOT NULL,
    CONSTRAINT fk_address_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
~~~

Trong ví dụ, địa chỉ được mô hình hóa thành một bảng vì một khách hàng có thể có nhiều địa chỉ. Bên trong mỗi địa chỉ, các thành phần được biểu diễn thành cột. Nếu mỗi khách hàng chỉ có một địa chỉ và địa chỉ không có vòng đời riêng, các cột địa chỉ có thể được đặt trực tiếp trong bảng khách hàng. Nếu địa chỉ là snapshot giao hàng, chúng có thể nằm trong cấu trúc đơn hàng để giữ lịch sử.

### Thuộc tính nhiều giá trị

Trong mô hình quan hệ chuẩn, không nên lưu danh sách giá trị độc lập trong một cột dạng chuỗi phân cách như "090..., 091..., 028...". Thay vào đó, tạo bảng riêng với một hàng cho mỗi giá trị:

~~~sql
CREATE TABLE customer_phone (
    customer_id BIGINT NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    phone_type VARCHAR(20) NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMP,
    CONSTRAINT pk_customer_phone
        PRIMARY KEY (customer_id, phone_number),
    CONSTRAINT fk_phone_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id)
);
~~~

Bảng này biểu diễn quan hệ một-nhiều từ khách hàng đến số điện thoại. Khóa chính ghép ngăn cùng một số xuất hiện lặp trong một khách hàng theo giả định của ví dụ. Nếu số điện thoại có thể được dùng chung hoặc có nhiều bản ghi lịch sử cho cùng một số, cần thay đổi khóa và mô hình thời gian phù hợp. Nếu mỗi khách hàng chỉ được có một số chính, có thể cần thêm cơ chế bảo vệ quy tắc này, chẳng hạn unique filtered/partial index tùy hệ quản trị hoặc một thiết kế lưu định danh chính rõ ràng.

### Tại sao không nên nhét danh sách vào một cột?

Một cột như phones = "090...,091..." gây khó khăn khi:

- Tìm tất cả khách hàng có một số cụ thể.
- Bảo đảm một số không bị lặp trong cùng khách hàng.
- Gắn loại, trạng thái xác minh hoặc thời hạn cho từng số.
- Cập nhật hoặc xóa một số mà không phân tích chuỗi.
- Nối với bảng danh mục hoặc hệ thống xác minh số điện thoại.
- Thống kê số lượng số điện thoại theo khách hàng.

Nếu danh sách chỉ là dữ liệu phụ được đọc/ghi cùng một aggregate và không cần ràng buộc hay truy vấn từng phần, cấu trúc mảng trong document có thể phù hợp. Lựa chọn phải theo cách sử dụng và yêu cầu nhất quán.

## 7. Biểu diễn trong document, đồ thị và mô hình phân tích

Cùng một thuộc tính nghiệp vụ có thể được biểu diễn khác nhau theo họ mô hình. Ý nghĩa phải giữ nhất quán ngay cả khi cấu trúc lưu trữ khác nhau.

| Họ mô hình | Thuộc tính đơn | Thuộc tính phức hợp | Thuộc tính nhiều giá trị |
|---|---|---|---|
| Quan hệ | Một cột | Nhiều cột hoặc bảng đối tượng giá trị | Bảng con có FK |
| Document | Trường scalar | Object lồng nhau | Array hoặc collection lồng |
| Đồ thị | Thuộc tính của node/edge | Nhiều thuộc tính hoặc node giá trị có cấu trúc | Nhiều edge hoặc tập node liên quan |
| Phân tích | Cột dimension/fact | Các cột thành phần theo grain | Bridge table hoặc dimension đa trị |

### Ví dụ document

Một document khách hàng có thể biểu diễn địa chỉ và số điện thoại như sau:

~~~json
{
  "customerId": "cus_8f2a",
  "displayName": "Nguyen An",
  "address": {
    "streetLine": "12 Le Loi",
    "city": "Da Nang",
    "countryCode": "VN"
  },
  "phones": [
    {
      "number": "+84901234567",
      "type": "MOBILE",
      "isPrimary": true,
      "verified": true
    },
    {
      "number": "+84236345678",
      "type": "WORK",
      "isPrimary": false,
      "verified": false
    }
  ]
}
~~~

Object address thể hiện thuộc tính phức hợp. Array phones thể hiện thuộc tính nhiều giá trị, trong đó mỗi phần tử lại là một cấu trúc có nhiều trường. Cách này thuận tiện nếu các số điện thoại được đọc và cập nhật cùng hồ sơ khách hàng. Nếu cần quản lý từng số độc lập, tham chiếu từ nhiều thực thể hoặc có lịch sử dài, có thể tách thành collection riêng.

### Ví dụ đồ thị

Trong mô hình đồ thị, một khách hàng có thể liên kết với nhiều điểm liên hệ qua các cạnh. Mỗi điểm liên hệ có thể là node nếu cần danh tính, xác minh hoặc chia sẻ giữa các hồ sơ:

~~~mermaid
flowchart LR
    C["(:Customer)"] -->|HAS_CONTACT| P1["(:ContactPoint)"]
    C -->|HAS_CONTACT| P2["(:ContactPoint)"]
    P1 --> T1["type: MOBILE"]
    P2 --> T2["type: WORK"]
~~~

Nếu các điểm liên hệ chỉ là thuộc tính đơn giản, lưu nhiều cạnh hoặc node có thể tạo thêm độ phức tạp không cần thiết. Chỉ nên biến một giá trị thành node khi nó có ý nghĩa quan hệ hoặc vòng đời riêng.

### Ví dụ mô hình phân tích

Khi phân tích khách hàng theo thành phố, các thành phần địa chỉ cần được chuẩn hóa thành dimension có định nghĩa nhất quán. Khi phân tích theo nhiều chứng chỉ hoặc nhiều sở thích, một fact hoặc dimension có thể cần bridge table để tránh nhân bản dòng khi join. Phải xác định grain của fact và cách phân bổ số đo nếu một bản ghi liên kết với nhiều giá trị.

Ví dụ, nếu một đơn hàng được gắn với ba thẻ chiến dịch, join trực tiếp bảng đơn hàng với bảng thẻ có thể làm doanh thu bị cộng ba lần. Mô hình phân tích phải định nghĩa liệu doanh thu được phân bổ theo tỷ lệ, đếm toàn bộ cho từng thẻ hay chỉ gắn một thẻ chính.

## 8. Các quy tắc cần xác định cho thuộc tính

Phân loại đơn, phức hợp hay nhiều giá trị mới chỉ là bước đầu. Mỗi thuộc tính cần thêm các quy tắc sau:

| Quy tắc | Câu hỏi | Ví dụ |
|---|---|---|
| Tính bắt buộc | Có thể thiếu giá trị không? | Số điện thoại tùy chọn, mã khách hàng bắt buộc |
| Cardinality | Có tối thiểu/tối đa bao nhiêu giá trị? | Khách hàng có 0..N số liên hệ |
| Tính duy nhất | Giá trị có được lặp lại không? | Email đã xác minh có thể duy nhất theo chính sách |
| Thứ tự | Các giá trị có thứ tự có ý nghĩa không? | Danh sách địa chỉ ưu tiên |
| Đơn vị | Giá trị đo theo đơn vị nào? | Khối lượng tính bằng gram hay kilogram |
| Độ chính xác | Cần bao nhiêu chữ số? | Giá tiền dùng DECIMAL theo quy tắc tiền tệ |
| Chuẩn hóa | Có quy tắc viết hoa, khoảng trắng, mã vùng không? | Mã quốc gia viết hoa theo bộ mã đã chọn |
| Lịch sử | Có cần lưu giá trị cũ và thời điểm hiệu lực không? | Địa chỉ giao hàng đã xác nhận |
| Nguồn dữ liệu | Ai được quyền tạo hoặc sửa? | Mã sản phẩm do hệ thống danh mục cấp |

### Null, rỗng và không xác định

Không nên xem NULL, chuỗi rỗng và giá trị mặc định là tương đương:

- **NULL:** không có giá trị được ghi nhận, chưa biết hoặc không áp dụng tùy quy ước.
- **Chuỗi rỗng:** một giá trị chuỗi có độ dài bằng không.
- **Giá trị mặc định:** giá trị được gán khi không cung cấp đầu vào; phải có ý nghĩa nghiệp vụ rõ.
- **Không áp dụng:** một trạng thái ngữ nghĩa; có thể biểu diễn bằng NULL kèm quy ước, trạng thái riêng hoặc mô hình phù hợp hơn.

Ví dụ, ngày kết thúc hợp đồng NULL có thể có nghĩa hợp đồng chưa kết thúc. Nếu cần phân biệt “chưa biết ngày kết thúc” với “hợp đồng không có ngày kết thúc”, một trường nullable duy nhất có thể không đủ; cần trạng thái hoặc quy tắc bổ sung.

Với thuộc tính nhiều giá trị, tập rỗng có thể khác với tập chưa biết. Nếu khách hàng đã xác nhận không có số điện thoại phụ, đó là tập rỗng. Nếu dữ liệu chưa được thu thập, trạng thái chưa biết có thể cần được phân biệt. Mô hình phải phản ánh sự khác biệt khi nghiệp vụ quan tâm.

### Thứ tự và giá trị chính

Một tập nhiều giá trị theo bản chất có thể không có thứ tự. Nếu giao diện cần sắp xếp, hãy xác định thứ tự đó là thứ tự nghiệp vụ hay chỉ là thứ tự hiển thị. Nếu có một giá trị chính, hãy định nghĩa quy tắc chọn duy nhất một giá trị chính hoặc cho phép chưa có giá trị chính.

Không nên dựa vào vị trí phần tử trong mảng hoặc thứ tự hàng được trả về nếu hệ thống không có cam kết về thứ tự. Hãy lưu position, priority hoặc is_primary khi cần.

## 9. Những lỗi mô hình hóa thường gặp

1. **Gộp nhiều giá trị vào một chuỗi:** làm mất khả năng kiểm tra, tìm kiếm và cập nhật từng giá trị.
2. **Phân rã quá mức:** tạo cột cho những thành phần không có ý nghĩa độc lập, khiến mô hình khó đọc và khó nhập dữ liệu.
3. **Coi mọi cấu trúc lồng nhau là thực thể:** thêm ID và bảng cho dữ liệu chỉ cần sống cùng chủ thể mà không có vòng đời riêng.
4. **Coi mọi danh sách là nhiều giá trị đơn giản:** bỏ qua metadata của từng phần tử, ví dụ loại, trạng thái, thời hạn và thứ tự.
5. **Bỏ qua cardinality:** không xác định tối thiểu/tối đa, dẫn đến giao diện và dữ liệu không nhất quán.
6. **Dùng kiểu kỹ thuật thay cho miền nghiệp vụ:** ví dụ lưu mã có số 0 đầu bằng kiểu số, hoặc lưu tiền bằng FLOAT.
7. **Đồng nhất NULL với rỗng:** khiến hệ thống không phân biệt chưa biết, không áp dụng và không có giá trị.
8. **Không lưu snapshot:** làm thay đổi ý nghĩa lịch sử khi thuộc tính nguồn thay đổi.
9. **Lặp thông tin không có nguồn chuẩn:** ví dụ lưu địa chỉ ở nhiều nơi nhưng không xác định bản nào là chuẩn và bản nào là snapshot.
10. **Bỏ qua quy tắc duy nhất cho phần tử:** cho phép một số điện thoại hoặc chứng chỉ bị lặp trong cùng một thực thể khi nghiệp vụ cấm.

## 10. Quy trình phân tích một thuộc tính

Khi gặp một thuộc tính trong yêu cầu nghiệp vụ, hãy thực hiện lần lượt:

1. Xác định thực thể hoặc quan hệ mà thuộc tính mô tả.
2. Viết định nghĩa ngắn và ví dụ hợp lệ/không hợp lệ.
3. Xác định thuộc tính là đơn, phức hợp hay nhiều giá trị theo mục tiêu mô hình.
4. Nếu phức hợp, liệt kê thành phần và lý do cần truy cập riêng.
5. Nếu nhiều giá trị, xác định cardinality, trùng lặp, thứ tự, giá trị chính và metadata của phần tử.
6. Xác định miền giá trị, đơn vị, độ chính xác, chuẩn hóa và tính bắt buộc.
7. Xác định dữ liệu gốc, dữ liệu suy ra, nguồn tạo và nhu cầu lưu lịch sử.
8. Kiểm tra các trường hợp biên và quy tắc liên quan.
9. Chọn cách biểu diễn logic phù hợp; trì hoãn kiểu và tối ưu vật lý cho đến khi có workload.
10. Ghi lại quyết định để người khác có thể phản biện và kiểm chứng.

### Mẫu từ điển thuộc tính

| Trường tài liệu | Nội dung |
|---|---|
| Tên thuộc tính | Tên chuẩn, thống nhất trong nhóm |
| Định nghĩa | Ý nghĩa nghiệp vụ chính xác |
| Chủ thể | Thực thể hoặc quan hệ sở hữu thuộc tính |
| Dạng | Đơn, phức hợp hoặc nhiều giá trị |
| Thành phần | Danh sách phần con nếu phức hợp |
| Cardinality | Số lượng tối thiểu và tối đa nếu nhiều giá trị |
| Miền giá trị | Giá trị hợp lệ, đơn vị và định dạng |
| Bắt buộc | Bắt buộc, tùy chọn hoặc phụ thuộc trạng thái |
| Quy tắc | Duy nhất, thứ tự, mặc định, kiểm tra |
| Nguồn | Hệ thống hoặc vai trò được phép cập nhật |
| Lịch sử | Có lưu thay đổi và thời điểm hiệu lực không |
| Ghi chú triển khai | Để dành cho giai đoạn logic/vật lý, không chi phối định nghĩa |

## 11. Bài tập thực hành và tiêu chí đánh giá

### Bài 1 — Hồ sơ khách hàng

Một khách hàng có tên pháp lý, tên hiển thị, ngày sinh, nhiều số điện thoại và nhiều địa chỉ. Một địa chỉ có thể được đánh dấu là mặc định.

Hãy phân loại từng thuộc tính thành đơn, phức hợp hoặc nhiều giá trị. Xác định thành phần của địa chỉ, cardinality của số điện thoại và địa chỉ, quy tắc chọn địa chỉ mặc định, cùng những dữ liệu cần giữ snapshot khi tạo đơn hàng.

### Bài 2 — Sản phẩm

Một sản phẩm có SKU, tên, kích thước, màu sắc, nhiều ảnh và nhiều chứng nhận. Kích thước gồm chiều dài, chiều rộng, chiều cao và đơn vị đo.

Hãy xác định:

- Thuộc tính nào đơn?
- Kích thước có phải thuộc tính phức hợp không?
- Màu sắc là một hay nhiều giá trị theo nghiệp vụ?
- Ảnh và chứng nhận có metadata riêng không?
- Khi nào chứng nhận cần trở thành thực thể có định danh?

### Bài 3 — Thiết kế mô hình quan hệ

Từ hồ sơ khách hàng ở Bài 1, hãy đề xuất các bảng và khóa ngoại để lưu nhiều địa chỉ và số điện thoại. Viết ít nhất ba ràng buộc: không lặp số trong phạm vi khách hàng, tối đa một địa chỉ mặc định đang hoạt động và mã quốc gia thuộc miền hợp lệ.

### Bài 4 — Chuyển sang document và phân tích

Biểu diễn cùng hồ sơ khách hàng dưới dạng document. Sau đó đề xuất cách phân tích khách hàng theo tỉnh/thành và theo loại số điện thoại. Giải thích vì sao cách lưu document phù hợp hoặc không phù hợp với từng truy vấn.

### Rubric tự đánh giá

| Tiêu chí | Đạt yêu cầu khi |
|---|---|
| Phân loại | Phân biệt đúng cấu trúc bên trong với số lượng giá trị |
| Ngữ nghĩa | Định nghĩa thuộc tính và miền giá trị rõ ràng |
| Cardinality | Nêu được số lượng tối thiểu/tối đa và quy tắc trùng lặp |
| Ranh giới thực thể | Chỉ tạo thực thể riêng khi có danh tính, vòng đời hoặc quan hệ độc lập |
| Ánh xạ | Chuyển đúng sang cột, bảng con, object hoặc array |
| Toàn vẹn | Có ràng buộc và cách kiểm tra phù hợp |
| Tiến hóa | Xem xét lịch sử, snapshot, nguồn dữ liệu và thay đổi nghiệp vụ |

Một mô hình thuộc tính tốt không chỉ lưu được giá trị. Nó phải diễn tả rõ giá trị đại diện cho điều gì, được phép có bao nhiêu phần tử, các thành phần nào cần được sử dụng riêng và dữ liệu thay đổi theo thời gian ra sao. Khi phân biệt được thuộc tính đơn, phức hợp và nhiều giá trị, nhóm có thể xây mô hình logic rõ ràng, chọn cách biểu diễn phù hợp cho từng họ cơ sở dữ liệu và kiểm chứng dữ liệu theo quy tắc nghiệp vụ.

