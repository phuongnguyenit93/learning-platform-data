# Tiền tệ, đại lượng đo và yêu cầu gắn đơn vị với giá trị

Một con số không tự nói lên ý nghĩa của nó. Giá trị 100 có thể là 100.000 đồng, 100 đô la, 100 gram, 100 kilôgam, 100 phần trăm hoặc 100 sản phẩm. Nếu lưu số mà không gắn đơn vị và ngữ cảnh, dữ liệu có thể được cộng, so sánh hoặc chuyển đổi sai mà hệ thống vẫn không báo lỗi.

Trong **data modeling**, tiền tệ và đại lượng đo cần được xem là giá trị có kiểu và đơn vị. Số tiền luôn đi cùng mã tiền tệ; đại lượng vật lý luôn đi cùng đơn vị đo và chiều đại lượng. Giá bán theo kilôgam khác giá bán theo chiếc. Khối lượng không thể cộng trực tiếp với thể tích. Khi chuyển đổi tiền tệ hoặc đơn vị, hệ thống còn phải lưu quy tắc, tỷ giá hoặc hệ số, thời điểm áp dụng và cách làm tròn.

Bài học này giải thích cách mô hình hóa giá trị tiền tệ và đại lượng đo, cách bảo vệ tính nhất quán bằng schema và quy tắc nghiệp vụ, cùng các tình huống thường gặp trong bán hàng, kho vận và phân tích dữ liệu.

## 1. Vì sao phải gắn đơn vị với giá trị?

Hãy tưởng tượng hai sản phẩm có khối lượng lần lượt là 2 và 500. Nếu chỉ lưu hai số này, người đọc không biết sản phẩm đầu nặng 2 kg hay 2 g, sản phẩm sau nặng 500 g hay 500 kg. Tương tự, số tiền 1.000 có thể đại diện cho nhiều loại tiền khác nhau.

Một giá trị đo lường nên được hiểu là cặp:

**Giá trị số + đơn vị đo**

Một khoản tiền nên được hiểu là:

**Số tiền + mã tiền tệ**

Trong một số trường hợp cần thêm ngữ cảnh:

- Giá bán: số tiền, tiền tệ, đơn vị tính giá và thời điểm hiệu lực.
- Khối lượng: giá trị, đơn vị, đối tượng được đo và thời điểm đo.
- Tỷ giá: cặp tiền tệ, chiều quy đổi, tỷ giá, nguồn và thời điểm.
- Nhiệt độ: giá trị, thang đo và vị trí/thời điểm đo.
- Tốc độ: giá trị, đơn vị chiều dài và đơn vị thời gian.

Một thiết kế lưu riêng con số mà bỏ mất đơn vị sẽ khiến ý nghĩa phụ thuộc vào tài liệu hoặc quy ước ngầm trong mã ứng dụng. Quy ước ngầm dễ bị phá vỡ khi có hệ thống mới, dữ liệu import hoặc báo cáo do nhóm khác xây dựng.

### 1.1. Một số lỗi do thiếu đơn vị

- Cộng 2 kg với 500 g mà không quy đổi.
- So sánh 1 lít nước với 900 gram nước như thể hai số có cùng chiều đại lượng.
- Hiển thị giá 20.000 mà không biết đó là VND, USD hay giá cho mỗi chiếc.
- Cộng doanh thu USD và VND trong cùng một báo cáo.
- Chuyển 100 độ Fahrenheit sang Celsius bằng cách chỉ nhân với một hệ số, bỏ qua độ lệch.
- Làm tròn từng bước chuyển đổi khiến tổng tiền lệch so với quy tắc kế toán.

Các lỗi này không chỉ là lỗi giao diện. Chúng bắt nguồn từ mô hình dữ liệu chưa thể hiện đầy đủ kiểu, đơn vị và ngữ cảnh của giá trị.

## 2. Mô hình hóa tiền tệ

### 2.1. Số tiền luôn đi cùng mã tiền tệ

Không nên lưu một cột amount mà không có thông tin currency. Cùng một giá trị số có thể mang ý nghĩa khác nhau:

| Giá trị | Mã tiền tệ | Ý nghĩa |
|---:|---|---|
| 100 | VND | 100 đồng |
| 100 | USD | 100 đô la Mỹ |
| 100 | JPY | 100 yên Nhật |
| 100 | EUR | 100 euro |

Đơn vị tiền tệ nên được biểu diễn bằng mã chuẩn, thường là mã ba chữ cái theo ISO 4217, thay vì chỉ lưu ký hiệu hiển thị như $, ¥ hoặc €. Một ký hiệu có thể được nhiều loại tiền sử dụng; mã tiền tệ làm rõ loại tiền.

Tên và ký hiệu tiền tệ dùng cho giao diện có thể thay đổi theo ngôn ngữ hoặc vùng. Chúng không thay thế mã tiền tệ trong dữ liệu giao dịch.

### 2.2. Không dùng số thực nhị phân cho tiền

Các kiểu số thực như FLOAT hoặc DOUBLE thường biểu diễn số theo dạng nhị phân gần đúng. Nhiều số thập phân thông thường không thể biểu diễn chính xác trong dạng này. Khi thực hiện nhiều phép cộng, nhân hoặc chia, sai số nhỏ có thể tích lũy và ảnh hưởng đến kết quả tiền.

Với giá trị tiền và phép tính tài chính, thường dùng:

- Kiểu số thập phân chính xác như NUMERIC hoặc DECIMAL.
- Số nguyên theo đơn vị nhỏ nhất của tiền tệ, nếu quy trình nghiệp vụ phù hợp.

Ví dụ, 125.000 VND có thể lưu là số nguyên 125000 nếu đơn vị lưu là đồng. 12,34 USD có thể lưu là 1234 cent nếu hệ thống quy định USD có hai chữ số thập phân. Cách lưu số nguyên cần đi cùng mã tiền tệ và quy tắc xác định số chữ số nhỏ nhất.

Không được mặc định mọi loại tiền có hai chữ số thập phân. Một số mã tiền tệ không dùng phần thập phân, một số dùng ba chữ số, và có những trường hợp quy tắc xử lý đặc biệt theo nghiệp vụ. Hãy quản lý metadata tiền tệ từ nguồn chuẩn và kiểm tra theo mã tiền tệ.

### 2.3. Chọn NUMERIC hay đơn vị nhỏ nhất?

| Cách lưu | Phù hợp khi | Cần lưu ý |
|---|---|---|
| NUMERIC/DECIMAL | Giá đơn vị, thuế, chiết khấu hoặc phép tính cần độ chính xác thập phân | Chọn precision/scale đủ lớn; quy định lúc nào làm tròn |
| Số nguyên đơn vị nhỏ nhất | Số tiền đã chốt để thanh toán hoặc ghi sổ | Phải biết currency và số chữ số nhỏ nhất |
| FLOAT/DOUBLE | Mô phỏng hoặc phân tích số thực không yêu cầu chính xác tiền | Không dùng làm biểu diễn chuẩn của số tiền cần đối soát |

Một hệ thống có thể dùng NUMERIC cho đơn giá và các giá trị trung gian, sau đó chuyển thành số nguyên đơn vị nhỏ nhất khi chốt khoản phải thu hoặc thanh toán. Cần định nghĩa rõ thời điểm làm tròn và lưu giá trị đã chốt để có thể đối soát.

Không nên lưu đồng thời hai dạng số tiền mà không có quy tắc đồng bộ. Nếu vừa lưu amount_decimal vừa lưu amount_minor_units, cần xác định trường nào là nguồn sự thật và kiểm tra chúng luôn tương ứng.

### 2.4. Precision, scale và làm tròn

Precision là tổng số chữ số có thể biểu diễn; scale là số chữ số sau dấu thập phân. Chọn kiểu NUMERIC cần xét:

- Giá trị lớn nhất dự kiến.
- Số chữ số thập phân của đơn giá.
- Số lượng có thể là phân số hay không.
- Phép nhân đơn giá với số lượng tạo ra bao nhiêu chữ số.
- Thuế, chiết khấu và tỷ giá cần độ chính xác trung gian ra sao.
- Kết quả cuối cùng phải làm tròn theo quy tắc nào.

Ví dụ, đơn giá 12.345,6789 VND cho mỗi kg nhân với 0,375 kg tạo ra số tiền có phần thập phân. Hệ thống phải xác định làm tròn ở cấp dòng hàng, cấp hóa đơn hay cấp tổng thanh toán. Các cách làm tròn khác nhau có thể cho kết quả cuối cùng khác nhau.

Quy tắc làm tròn có thể gồm:

- Làm tròn gần nhất, trường hợp đúng giữa hai giá trị thì chọn hướng nào.
- Làm tròn lên hoặc xuống theo chính sách.
- Làm tròn ở từng dòng hàng hay chỉ khi cộng tổng.
- Cách xử lý số âm khi hoàn tiền hoặc điều chỉnh.
- Số chữ số thập phân hợp lệ theo tiền tệ và loại giao dịch.

Không nên để mỗi màn hình hoặc mỗi dịch vụ tự chọn cách làm tròn. Quy tắc phải được thống nhất và kiểm thử bằng các ví dụ biên.

### 2.5. Phân biệt số tiền, đơn giá và tỷ lệ

Các giá trị sau đều có thể là NUMERIC nhưng mang ý nghĩa khác:

- 100.000 VND: số tiền.
- 100.000 VND trên mỗi chiếc: đơn giá.
- 10%: tỷ lệ phần trăm.
- 1,08: hệ số nhân.
- 1,08 USD cho mỗi EUR: tỷ giá theo một chiều xác định.

Không nên đặt tên chung là value hoặc rate mà thiếu đơn vị và chiều ý nghĩa. Ví dụ, các tên price_per_kg, discount_percent, tax_rate và exchange_rate_quote_per_base giúp người đọc hiểu hơn.

### 2.6. Mô hình hóa metadata tiền tệ

Một bảng tiền tệ có thể lưu mã và số chữ số của đơn vị nhỏ nhất:

~~~sql
CREATE TABLE currencies (
    currency_code CHAR(3) PRIMARY KEY,
    currency_name VARCHAR(100) NOT NULL,
    minor_unit_digits SMALLINT NOT NULL
        CHECK (minor_unit_digits BETWEEN 0 AND 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE payment_postings (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    minor_unit_digits_at_posting SMALLINT NOT NULL
        CHECK (minor_unit_digits_at_posting BETWEEN 0 AND 4),
    amount_minor_units BIGINT NOT NULL
        CHECK (amount_minor_units >= 0),
    posting_kind VARCHAR(20) NOT NULL
        CHECK (posting_kind IN ('capture', 'refund', 'adjustment')),
    posted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong ví dụ, payment_postings lưu khoản tiền đã chốt theo đơn vị nhỏ nhất và chụp lại số chữ số thập phân được áp dụng tại thời điểm ghi sổ. Khi tạo posting, transaction lấy minor_unit_digits từ danh mục currencies và lưu snapshot này; ứng dụng không nên tự nhập một giá trị tùy ý. Điều này giúp dữ liệu lịch sử không bị diễn giải lại nếu metadata tiền tệ được cập nhật. Khi hiển thị, ứng dụng dùng minor_unit_digits_at_posting để đặt dấu thập phân và định dạng. Bảng currencies ở đây chỉ chứa các loại tiền được hỗ trợ thanh toán và có số chữ số đơn vị nhỏ nhất xác định. Dữ liệu thực tế cần được nạp và quản lý từ danh mục tiền tệ có thẩm quyền; không nên tự suy ra số chữ số từ ký hiệu. Số tiền được lưu như độ lớn không âm; posting_kind cho biết đây là thu tiền, hoàn tiền hay điều chỉnh. Một sổ cái có thể dùng quy ước dấu riêng, nhưng phải nhất quán.

Nếu cần lưu số tiền trung gian có độ chính xác cao, có thể dùng NUMERIC và currency_code:

~~~sql
CREATE TABLE price_quotes (
    price_quote_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    amount NUMERIC(24, 10) NOT NULL CHECK (amount >= 0),
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
~~~

Ví dụ này lưu giá trị thập phân có độ chính xác cao để tính toán. Khi giá được dùng cho giao dịch đã chốt, cần áp dụng quy tắc làm tròn và ghi lại số tiền cuối cùng theo chính sách kế toán của hệ thống.

## 3. Mô hình hóa đại lượng đo

### 3.1. Giá trị đo cần có đơn vị

Đại lượng vật lý không chỉ là một con số. Một phép đo nên chứa:

- Giá trị số.
- Đơn vị đo.
- Chiều đại lượng hoặc loại đại lượng.
- Đối tượng được đo.
- Thời điểm đo nếu giá trị thay đổi theo thời gian.
- Phương pháp hoặc thiết bị đo nếu cần truy xuất nguồn gốc.

Ví dụ, khối lượng của một kiện hàng là 12,5 kg. Nhiệt độ trong kho là 4 °C lúc 08:30. Chiều dài sản phẩm là 120 cm. Nếu chỉ lưu 12.5, 4 hoặc 120, dữ liệu thiếu thông tin để diễn giải.

### 3.2. Chiều đại lượng và đơn vị đo

Đơn vị thuộc về một chiều đại lượng. Một số ví dụ:

| Chiều đại lượng | Đơn vị ví dụ | Quan hệ chuyển đổi |
|---|---|---|
| Chiều dài | m, cm, mm, km | 1 m = 100 cm |
| Khối lượng | kg, g, mg | 1 kg = 1.000 g |
| Thể tích | L, mL, m³ | 1 L = 1.000 mL |
| Thời gian | s, min, h | 1 h = 3.600 giây |
| Diện tích | m², cm² | 1 m² = 10.000 cm² |
| Nhiệt độ | K, °C, °F | Có cả hệ số và độ lệch |
| Tốc độ | m/s, km/h | Kết hợp chiều dài và thời gian |

Hai giá trị chỉ có thể so sánh hoặc cộng trực tiếp khi chúng cùng chiều đại lượng và đã được quy đổi về cùng đơn vị hoặc cùng biểu diễn chuẩn.

Không thể cộng 3 kg với 2 lít vì khối lượng và thể tích là hai chiều đại lượng khác nhau. Muốn đổi thể tích sang khối lượng cần thêm thông tin về mật độ của chất và điều kiện liên quan; không có một hệ số chung áp dụng cho mọi chất.

### 3.3. Đơn vị cơ sở và biểu diễn chuẩn

Đối với nhiều đại lượng, hệ thống có thể chọn một đơn vị chuẩn nội bộ để lưu hoặc tính toán. Ví dụ:

- Chiều dài chuẩn theo mét.
- Khối lượng chuẩn theo kilôgam.
- Thời gian chuẩn theo giây.
- Thể tích chuẩn theo mét khối.

Lưu hoặc chuyển đổi về đơn vị chuẩn giúp so sánh và tổng hợp nhất quán. Tuy nhiên, vẫn nên giữ đơn vị gốc khi nó có ý nghĩa đối với người nhập, nhãn sản phẩm, chứng từ hoặc truy xuất nguồn gốc.

Ví dụ, người dùng nhập 250 cm. Hệ thống có thể chuẩn hóa thành 2,5 m để tính toán, nhưng cần biết giá trị nhập ban đầu và đơn vị gốc nếu muốn hiển thị đúng cách người dùng đã khai báo.

### 3.4. Chuyển đổi tuyến tính và chuyển đổi có độ lệch

Nhiều đơn vị có thể chuyển đổi bằng hệ số nhân:

**giá trị chuẩn = giá trị gốc × hệ số**

Ví dụ:

- 1 kg = 1.000 g.
- 1 km = 1.000 m.
- 1 giờ = 3.600 giây.

Nhưng không phải mọi chuyển đổi chỉ là phép nhân. Nhiệt độ Celsius và Fahrenheit cần hệ số cùng độ lệch:

**°F = °C × 9/5 + 32**

**K = °C + 273,15**

Vì vậy, bảng chuyển đổi tổng quát cần mô tả loại phép biến đổi hoặc phải dùng logic chuyên biệt cho những đơn vị có độ lệch. Một cột factor duy nhất không thể biểu diễn mọi chuyển đổi.

### 3.5. Đơn vị phụ thuộc ngữ cảnh

Một số đơn vị hoặc phép quy đổi cần thêm ngữ cảnh:

- Thể tích sang khối lượng cần mật độ.
- Kích thước quy đổi sang trọng lượng tính cước cần quy tắc của hãng vận chuyển.
- Đơn vị đóng gói như thùng, hộp hoặc pallet phụ thuộc số lượng bên trong.
- Đơn vị năng lượng hoặc công suất có thể phụ thuộc điều kiện đo.

Không nên ghi một hệ số chuyển đổi toàn cục nếu hệ số thay đổi theo sản phẩm, lô hàng, nhiệt độ hoặc quy định đối tác. Khi quy đổi phụ thuộc ngữ cảnh, cần lưu dữ liệu ngữ cảnh và phiên bản quy tắc được áp dụng.

## 4. Mô hình đơn vị và đại lượng trong schema

### 4.1. Danh mục chiều đại lượng và đơn vị

Có thể quản lý đơn vị bằng danh mục có mã ổn định, chiều đại lượng và quy tắc chuyển về đơn vị chuẩn:

~~~sql
CREATE TABLE measure_dimensions (
    dimension_code VARCHAR(30) PRIMARY KEY,
    dimension_name VARCHAR(100) NOT NULL
);

CREATE TABLE measure_units (
    unit_code VARCHAR(20) PRIMARY KEY,
    dimension_code VARCHAR(30) NOT NULL
        REFERENCES measure_dimensions(dimension_code),
    unit_symbol VARCHAR(20) NOT NULL,
    factor_to_base NUMERIC(30, 15) NOT NULL
        CHECK (factor_to_base > 0),
    offset_to_base NUMERIC(30, 15) NOT NULL DEFAULT 0,
    UNIQUE (unit_code, dimension_code)
);
~~~

Quy ước chuyển đổi của bảng này là:

**giá trị chuẩn = giá trị đơn vị × factor_to_base + offset_to_base**

Quy ước phải được áp dụng nhất quán và đơn vị chuẩn phải được xác định cho từng dimension. Đối với các đơn vị có hệ số tuần hoàn hoặc yêu cầu độ chính xác cao, nên lưu hệ số dưới dạng phân số chính xác hoặc dùng độ chính xác đủ lớn theo miền nghiệp vụ thay vì làm tròn tùy tiện.

### 4.2. Gắn đơn vị với thuộc tính đo

Giả sử sản phẩm có các thông số như khối lượng, chiều dài và thể tích. Có thể định nghĩa trước thuộc tính nào thuộc chiều đại lượng nào:

Ví dụ dưới đây giả định hệ thống đã có bảng products và các bảng danh mục chiều đại lượng/đơn vị được tạo trước.

~~~sql
CREATE TABLE measurement_attributes (
    attribute_code VARCHAR(40) PRIMARY KEY,
    dimension_code VARCHAR(30) NOT NULL
        REFERENCES measure_dimensions(dimension_code),
    UNIQUE (attribute_code, dimension_code)
);

CREATE TABLE product_measurements (
    product_id BIGINT NOT NULL REFERENCES products(id),
    attribute_code VARCHAR(40) NOT NULL,
    dimension_code VARCHAR(30) NOT NULL,
    measured_value NUMERIC(24, 10) NOT NULL,
    unit_code VARCHAR(20) NOT NULL,
    measured_at TIMESTAMPTZ,
    PRIMARY KEY (product_id, attribute_code),
    FOREIGN KEY (attribute_code, dimension_code)
        REFERENCES measurement_attributes(attribute_code, dimension_code),
    FOREIGN KEY (unit_code, dimension_code)
        REFERENCES measure_units(unit_code, dimension_code)
);
~~~

Hai khóa ngoại ghép giúp kiểm tra thuộc tính và đơn vị cùng thuộc một chiều đại lượng. Ví dụ, nếu attribute_code là net_weight có dimension là MASS, không thể gắn đơn vị L thuộc dimension VOLUME.

Ví dụ này giả định mỗi sản phẩm có một giá trị hiện tại cho mỗi thuộc tính. Nếu cần nhiều lần đo, nhiều phương pháp đo hoặc lịch sử theo lô, hãy dùng measurement_id riêng và lưu từng lần đo thay vì dùng product_id cùng attribute_code làm khóa chính.

### 4.3. Đơn vị hiển thị và đơn vị tính toán

Người dùng có thể nhập theo đơn vị quen thuộc trong khi hệ thống lưu thêm giá trị chuẩn để tính toán. Cần xác định:

- Giá trị nhập gốc và đơn vị gốc có cần lưu không?
- Giá trị chuẩn được tính khi nhập hay khi truy vấn?
- Khi danh mục hệ số chuyển đổi thay đổi, dữ liệu cũ có được tính lại không?
- Đơn vị nào được dùng trong hợp đồng, nhãn hàng hoặc báo cáo?
- Có cần hiển thị số chữ số thập phân theo đơn vị không?

Nếu phép đo là bằng chứng hoặc dữ liệu kiểm định, nên giữ giá trị gốc, đơn vị gốc, thời điểm và phương pháp đo. Giá trị chuẩn có thể là dữ liệu dẫn xuất được tính theo phiên bản quy tắc đã lưu.

### 4.4. Kiểm tra giá trị hợp lệ

Một số thuộc tính có miền giá trị:

- Khối lượng hàng hóa phải lớn hơn hoặc bằng không.
- Chiều dài bao bì phải lớn hơn không.
- Nhiệt độ vận hành phải nằm trong phạm vi thiết bị hỗ trợ.
- Phần trăm chiết khấu thường nằm trong khoảng quy định.
- Số lượng tồn kho có thể không âm, trừ khi nghiệp vụ cho phép backorder.

CHECK constraint có thể kiểm tra điều kiện trên cùng hàng. Những quy tắc phụ thuộc danh mục đơn vị, sản phẩm hoặc cấu hình khác cần được bảo vệ bằng khóa ngoại, transaction, trigger hoặc lớp nghiệp vụ phù hợp. Không nên giả định một CHECK có thể truy vấn tùy ý bảng khác.

## 5. Giá bán và đơn vị tính giá

Một mức giá không chỉ gồm số tiền và tiền tệ. Nó còn có thể được tính theo một đơn vị cơ sở:

- 25.000 VND mỗi chiếc.
- 80.000 VND mỗi kg.
- 12 USD mỗi mét.
- 5 EUR mỗi lít.

Giá 80.000 VND/kg không tương đương 80.000 VND/g. Nếu hệ thống chỉ lưu amount và currency mà không lưu đơn vị tính giá, việc áp dụng giá cho lượng hàng khác đơn vị có thể sai nhiều bậc độ lớn.

Một cấu trúc giá nên xác định:

- Số tiền.
- Mã tiền tệ.
- Đơn vị tính giá.
- Số lượng cơ sở của đơn vị giá nếu không phải một đơn vị.
- Khoảng thời gian hiệu lực.
- Phạm vi áp dụng: sản phẩm, khách hàng, khu vực hoặc bảng giá.

Ví dụ, giá 120.000 VND cho hộp 6 chai khác giá 120.000 VND mỗi chai. Nếu lưu giá theo gói, cần thể hiện package_quantity = 6 và package_unit = chai.

### 5.1. Ví dụ giá theo đơn vị

~~~sql
CREATE TABLE product_prices (
    product_price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    price_amount NUMERIC(24, 10) NOT NULL
        CHECK (price_amount >= 0),
    price_unit_code VARCHAR(20) NOT NULL
        REFERENCES measure_units(unit_code),
    basis_quantity NUMERIC(24, 10) NOT NULL DEFAULT 1
        CHECK (basis_quantity > 0),
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
~~~

Ví dụ này biểu diễn số tiền cho một lượng cơ sở của đơn vị. Nếu price_amount là 120.000 VND, price_unit_code là BOTTLE và basis_quantity là 6, giá áp dụng là 120.000 VND cho 6 chai. Khi tính giá cho 1 chai, hệ thống chia theo quy tắc chính xác và làm tròn đã định nghĩa.

Đơn vị đếm như chiếc, hộp hoặc thùng cũng cần mã và quy tắc chuyển đổi. Tuy nhiên, một thùng có thể chứa số lượng thay đổi theo sản phẩm hoặc lô. Vì vậy, không phải mọi quan hệ đóng gói đều là hệ số cố định trong danh mục đơn vị chung; có thể cần bảng quy cách đóng gói theo sản phẩm.

Nếu mỗi sản phẩm chỉ được có một mức giá hiệu lực cho một tiền tệ và đơn vị tính tại một thời điểm, cần thêm cơ chế ngăn các khoảng hiệu lực chồng lấn. Tùy hệ quản trị, có thể dùng exclusion constraint trên khoảng thời gian hoặc transaction/trigger có khóa phù hợp. CHECK trên một hàng chỉ kiểm tra được effective_to lớn hơn effective_from, không phát hiện được hai hàng giá chồng lấn.

### 5.2. Số lượng phân số và số lượng nguyên

Không phải số lượng nào cũng là số nguyên. Hàng bán theo cân có thể có 0,375 kg; hàng cắt theo chiều dài có thể có 1,25 m. Ngược lại, số lượng thiết bị hoặc vé thường phải là số nguyên.

Kiểu dữ liệu cần phản ánh quy tắc:

- Số nguyên cho đối tượng không thể chia nhỏ theo nghiệp vụ.
- NUMERIC cho khối lượng, chiều dài hoặc lượng có phần thập phân.
- Không dùng FLOAT cho số lượng cần quy đổi và đối soát chính xác.

Nếu đơn vị nhập khác đơn vị lưu kho, cần lưu rõ phép quy đổi. Ví dụ, nhập 2 thùng, mỗi thùng 12 chai, có thể tăng tồn kho thêm 24 chai. Quy cách 12 chai/thùng phải được xác định tại thời điểm nhập nếu quy cách có thể thay đổi về sau.

## 6. Chuyển đổi tiền tệ và tỷ giá

### 6.1. Tỷ giá có chiều

Tỷ giá phải nói rõ một đơn vị tiền gốc đổi được bao nhiêu đơn vị tiền đích. Ví dụ:

**1 USD = 25.000 VND**

Trong đó USD là base currency, VND là quote currency và rate là 25.000 VND cho mỗi USD. Nếu đảo chiều, tỷ giá là 1/25.000 USD cho mỗi VND, không phải cùng một con số.

Tên trường nên làm rõ chiều, ví dụ quote_per_base. Không nên chỉ đặt tên rate nếu schema không có base_currency và quote_currency.

### 6.2. Lưu nguồn và thời điểm tỷ giá

Tỷ giá thay đổi theo thời gian và nguồn. Một giao dịch đã quy đổi cần biết tỷ giá nào đã được áp dụng, không nên tính lại bằng tỷ giá mới nhất khi xem lịch sử.

Một bảng tỷ giá có thể có:

~~~sql
CREATE TABLE exchange_rates (
    base_currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    quote_currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    quote_per_base NUMERIC(30, 15) NOT NULL
        CHECK (quote_per_base > 0),
    observed_at TIMESTAMPTZ NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    rate_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (
        base_currency_code,
        quote_currency_code,
        observed_at,
        source_name,
        rate_type
    ),
    CHECK (base_currency_code <> quote_currency_code)
);
~~~

observed_at cho biết thời điểm tỷ giá được ghi nhận. Một hệ thống còn có thể cần thời điểm hiệu lực, múi giờ nguồn, loại tỷ giá mua/bán/trung bình, ngày giao dịch và phiên bản nguồn dữ liệu. Không nên dùng một cột timestamp mơ hồ cho cả thời điểm công bố và thời điểm áp dụng.

### 6.3. Ghi lại tỷ giá thực tế của giao dịch

Khi một khoản tiền được thanh toán hoặc ghi sổ bằng loại tiền khác, nên lưu:

- Số tiền và tiền tệ nguồn.
- Số tiền và tiền tệ đích.
- Tỷ giá đã áp dụng và chiều tỷ giá.
- Nguồn hoặc căn cứ tỷ giá.
- Thời điểm áp dụng.
- Quy tắc làm tròn.

Không nên chỉ lưu số tiền đã quy đổi rồi bỏ mất số tiền gốc. Khi cần đối soát hoặc giải thích chênh lệch, phải biết giá trị ban đầu và tỷ giá được sử dụng.

### 6.4. Không cộng nhiều loại tiền trực tiếp

Doanh thu 100 USD và 2.000.000 VND không thể cộng thành 2.000.100 theo nghĩa tổng doanh thu. Muốn tổng hợp cần chọn đồng tiền báo cáo và quy tắc quy đổi:

1. Chọn đồng tiền báo cáo.
2. Chọn nguồn tỷ giá và loại tỷ giá.
3. Xác định thời điểm tỷ giá: thời điểm giao dịch, cuối ngày, cuối tháng hay ngày báo cáo.
4. Chuyển đổi từng khoản theo quy tắc.
5. Làm tròn ở cấp phù hợp.
6. Lưu dấu vết để có thể tái lập báo cáo.

Trong kho phân tích, có thể giữ cả số tiền gốc và số tiền đã quy đổi sang đồng tiền báo cáo. Cần ghi rõ ngày tỷ giá, loại tỷ giá và phiên bản quy tắc.

## 7. Những trường hợp chuyển đổi đơn vị dễ sai

### 7.1. Không trộn các chiều đại lượng

Khối lượng, thể tích, chiều dài, diện tích và thời gian là các chiều khác nhau. Hệ thống nên kiểm tra dimension trước khi thực hiện phép tính.

Các phép toán hợp lệ phụ thuộc loại đại lượng:

- Cộng hai khối lượng sau khi quy đổi về cùng đơn vị.
- Chia khối lượng cho thể tích để tính mật độ.
- Nhân chiều dài với chiều rộng để tính diện tích.
- Không cộng khối lượng với chiều dài.

Một giá trị số và ký hiệu đơn vị hợp lệ về cú pháp vẫn có thể sai về ngữ nghĩa. Ví dụ, nhập 10 kg cho trường chiều dài phải bị từ chối.

### 7.2. Đổi thể tích sang khối lượng cần mật độ

Với một chất đồng nhất trong điều kiện xác định:

**khối lượng = thể tích × mật độ**

Nhưng mật độ phụ thuộc chất, nhiệt độ, áp suất và thành phần. Một lít nước không thể được quy đổi thành cùng khối lượng với một lít dầu hoặc một lít dung dịch có nồng độ khác.

Nếu cần quy đổi, phải lưu mật độ, đơn vị của mật độ, điều kiện đo và nguồn dữ liệu. Kết quả nên được ghi là giá trị tính toán với phương pháp và thời điểm cụ thể.

### 7.3. Nhiệt độ có độ lệch

Không thể chuyển Celsius sang Fahrenheit bằng cách chỉ nhân với 1,8; phải cộng thêm 32. Điều này cho thấy đơn vị có thể có quy tắc chuyển đổi affine, không chỉ là hệ số nhân.

Nếu hệ thống quản lý nhiệt độ, hãy chọn một thang chuẩn nội bộ và lưu thang đo gốc khi cần truy xuất. Với các phép tính chênh lệch nhiệt độ, cần phân biệt nhiệt độ tuyệt đối với khoảng chênh lệch nhiệt độ.

### 7.4. Đơn vị đóng gói và quy cách sản phẩm

Một hộp có thể chứa 10 sản phẩm ở một phiên bản bao bì và 12 sản phẩm ở phiên bản khác. Nếu chỉ lưu conversion factor cố định cho đơn vị HỘP, dữ liệu lịch sử có thể bị diễn giải sai.

Hãy gắn quy cách đóng gói với sản phẩm và thời điểm hiệu lực. Phiếu nhập hàng cũ phải giữ số lượng và quy cách đã áp dụng lúc nhập, ngay cả khi nhà sản xuất đổi bao bì.

### 7.5. Tốc độ, năng suất và đại lượng dẫn xuất

Một đại lượng dẫn xuất kết hợp nhiều đơn vị. Ví dụ:

- Tốc độ: km/h hoặc m/s.
- Mật độ: kg/m³.
- Công suất: W hoặc kW.
- Năng suất: sản phẩm/giờ.

Schema cần biểu diễn đơn vị của tử số và mẫu số hoặc dùng mã đơn vị dẫn xuất có định nghĩa rõ. Không nên lưu giá trị 60 rồi gọi chung là speed nếu không biết 60 km/h hay 60 m/s.

## 8. Quy tắc nghiệp vụ và kiểm tra tính nhất quán

### 8.1. Ràng buộc ở đúng lớp

Một số quy tắc có thể đặt trong schema:

- Currency code phải tham chiếu danh mục tiền tệ.
- Số tiền không âm đối với giao dịch thu tiền.
- Đơn vị phải thuộc chiều đại lượng của thuộc tính.
- Giá trị đo phải có đơn vị.
- Khoảng hiệu lực phải có thời điểm kết thúc sau thời điểm bắt đầu.

Những quy tắc phụ thuộc nhiều hàng hoặc chính sách phức tạp có thể cần transaction, trigger hoặc lớp nghiệp vụ. Ví dụ, một dòng hóa đơn và tổng hóa đơn phải nhất quán; một tỷ giá được chọn phải thuộc đúng cặp tiền và thời điểm.

Không nên lặp lại currency_code trên từng dòng nếu hóa đơn luôn chỉ có một loại tiền, trừ khi có lý do rõ. Nếu lưu currency ở cả header và line, cần ràng buộc để không thể có dòng tiền khác loại với hóa đơn.

### 8.2. Bảo vệ giá trị và đơn vị thành một cặp

Một cột quantity không được tồn tại mà không biết đơn vị. Nếu unit_code là NULL nhưng quantity có giá trị, hệ thống không thể diễn giải. Ngược lại, đơn vị có mặt mà giá trị chưa có cũng cần ý nghĩa rõ.

Có thể dùng CHECK để bảo vệ tính đầy đủ của cặp giá trị/đơn vị:

~~~sql
CHECK (
    (measured_value IS NULL AND unit_code IS NULL)
    OR
    (measured_value IS NOT NULL AND unit_code IS NOT NULL)
)
~~~

Với thuộc tính bắt buộc, nên dùng NOT NULL cho cả giá trị và đơn vị. Với thuộc tính tùy chọn, CHECK trên giúp tránh trạng thái chỉ có một nửa thông tin.

### 8.3. Kiểm thử chuyển đổi

Các phép chuyển đổi cần kiểm thử:

- Giá trị 0, giá trị âm và giá trị cực đại.
- Đơn vị cơ sở và đơn vị nhỏ hơn/lớn hơn.
- Hệ số chuyển đổi có nhiều chữ số thập phân.
- Chuyển đổi hai chiều và sai số làm tròn.
- Nhiệt độ có độ lệch.
- Đơn vị không cùng dimension.
- Thiếu đơn vị hoặc mã tiền tệ không hợp lệ.
- Tỷ giá bằng 0, âm hoặc sai chiều.
- Giao dịch hoàn tiền và số tiền âm theo chính sách.

Một kiểm thử hữu ích là chuyển đổi A sang B rồi quay lại A. Kết quả có thể sai khác trong giới hạn làm tròn được chấp nhận; giới hạn đó cần được định nghĩa, không nên bỏ qua sai số.

## 9. Sử dụng tiền tệ và đại lượng trong báo cáo

### 9.1. Báo cáo tiền tệ

Không cộng trực tiếp các số tiền có mã tiền tệ khác nhau. Báo cáo phải chọn đồng tiền chuẩn hoặc hiển thị từng loại tiền thành nhóm riêng. Nếu quy đổi, cần ghi rõ tỷ giá và thời điểm.

Các chỉ số như doanh thu, lợi nhuận, giá trị tồn kho và công nợ có thể dùng thời điểm quy đổi khác nhau theo chính sách kế toán. Không nên áp dụng tỷ giá mới nhất cho mọi giao dịch lịch sử.

### 9.2. Báo cáo đại lượng đo

Khi tổng hợp khối lượng hoặc thể tích, cần quy đổi về đơn vị chuẩn trong cùng dimension. Nếu báo cáo so sánh các sản phẩm có đơn vị bán khác nhau, phải xác định đang so sánh số lượng gói, số lượng đơn vị cơ sở hay giá trị quy đổi.

Ví dụ, 10 hộp và 100 chiếc không thể cộng trực tiếp nếu mỗi hộp có số chiếc khác nhau. Cần dùng quy cách đóng gói tại thời điểm giao dịch để chuyển đổi.

### 9.3. Lưu cả giá trị nguồn và giá trị chuẩn

Trong phân tích, có thể lưu:

- Giá trị đo gốc.
- Đơn vị gốc.
- Giá trị chuẩn đã quy đổi.
- Đơn vị chuẩn.
- Hệ số hoặc phiên bản quy tắc chuyển đổi.
- Thời điểm và nguồn đo.

Giá trị chuẩn hỗ trợ tổng hợp, còn dữ liệu gốc giúp truy xuất và kiểm tra. Không nên ghi đè dữ liệu nguồn nếu việc chuyển đổi có thể thay đổi theo phiên bản danh mục hoặc quy tắc.

## 10. Tiến hóa danh mục tiền tệ và đơn vị

Danh mục tiền tệ, mã đơn vị và quy tắc chuyển đổi cũng có vòng đời. Một đơn vị có thể bị ngừng sử dụng, một mã tiền tệ có thể được thay thế, hoặc quy tắc đóng gói của sản phẩm có thể đổi.

Khi thay đổi danh mục:

- Không tái sử dụng mã đơn vị cho ý nghĩa khác.
- Đánh dấu mã cũ không còn dùng cho giao dịch mới nhưng vẫn đọc được dữ liệu lịch sử.
- Lưu thời điểm hiệu lực của quy tắc chuyển đổi.
- Ghi phiên bản hoặc nguồn metadata.
- Với khoản tiền lưu theo đơn vị nhỏ nhất, giữ lại số chữ số thập phân hoặc phiên bản metadata đã áp dụng tại thời điểm ghi sổ.
- Không tự động tính lại giao dịch đã chốt nếu nghiệp vụ không yêu cầu.
- Có kế hoạch chuyển đổi và đối soát nếu mã cũ cần ánh xạ sang mã mới.

Ví dụ, nếu sản phẩm đổi từ hộp 10 chiếc sang hộp 12 chiếc, các giao dịch cũ vẫn phải dùng quy cách hộp 10 chiếc. Quy cách mới chỉ áp dụng từ thời điểm hiệu lực mới.

## 11. Những sai lầm thường gặp

**Lưu số tiền không có mã tiền tệ.** Giá trị số không đủ để hiểu khoản tiền. Luôn gắn currency code với khoản tiền hoặc với thực thể cha có quy tắc một loại tiền rõ ràng.

**Dùng FLOAT cho số tiền cần đối soát.** Sai số nhị phân có thể làm kết quả lệch. Dùng NUMERIC/DECIMAL hoặc số nguyên đơn vị nhỏ nhất theo chính sách.

**Giả định mọi tiền tệ có hai chữ số thập phân.** Số chữ số đơn vị nhỏ nhất phụ thuộc mã tiền tệ. Quản lý metadata và kiểm tra theo currency.

**Làm tròn ở nhiều nơi mà không thống nhất.** Đơn hàng, hóa đơn và thanh toán có thể ra tổng khác nhau. Quy định cấp làm tròn và dùng chung logic.

**Lưu số lượng nhưng không lưu đơn vị.** Không thể so sánh hoặc chuyển đổi đáng tin cậy. Giá trị đo phải đi cùng unit code.

**Coi mọi phép đổi đơn vị là nhân một hệ số.** Nhiệt độ có độ lệch; thể tích sang khối lượng cần mật độ; đóng gói phụ thuộc sản phẩm. Mô hình hóa quy tắc chuyển đổi phù hợp.

**Cộng các đại lượng khác chiều.** Kilôgam và lít không thể cộng trực tiếp. Kiểm tra dimension trước khi tính toán.

**Dùng ký hiệu hiển thị làm mã.** Ký hiệu có thể trùng hoặc thay đổi theo locale. Dùng mã ổn định, định dạng ký hiệu ở giao diện.

**Chỉ lưu kết quả quy đổi.** Khi không còn giá trị gốc, đơn vị gốc và tỷ giá, việc đối soát trở nên khó khăn. Giữ nguồn và quy tắc đã áp dụng khi cần truy xuất.

**Sửa danh mục làm thay đổi lịch sử.** Thay hệ số hoặc quy cách mới không được làm giao dịch cũ bị diễn giải lại ngoài ý muốn. Lưu hiệu lực và phiên bản.

## 12. Quy trình thiết kế giá trị có đơn vị

Khi gặp một trường tiền tệ hoặc đại lượng đo, hãy đi theo trình tự:

1. **Xác định ý nghĩa:** đây là số tiền, đơn giá, tỷ lệ, khối lượng, thể tích hay đại lượng dẫn xuất?
2. **Xác định đơn vị:** mã tiền tệ hoặc mã đơn vị nào được phép?
3. **Xác định dimension:** đại lượng thuộc chiều nào và có thể chuyển đổi với những đơn vị nào?
4. **Xác định độ chính xác:** miền giá trị, precision, scale và số chữ số thập phân cần thiết.
5. **Xác định quy tắc làm tròn:** thời điểm và phương pháp làm tròn, đặc biệt với giao dịch tài chính.
6. **Xác định ngữ cảnh:** đơn giá theo đơn vị nào, tỷ giá theo chiều nào, phép đo được thực hiện khi nào?
7. **Chọn cách lưu:** NUMERIC, số nguyên đơn vị nhỏ nhất, giá trị gốc hay giá trị chuẩn.
8. **Thiết kế ràng buộc:** bắt buộc đơn vị, mã hợp lệ, cùng dimension và miền giá trị.
9. **Xác định lịch sử:** lưu tỷ giá, quy tắc chuyển đổi, quy cách hoặc snapshot nào đã áp dụng?
10. **Kiểm thử:** thử giá trị biên, chuyển đổi hai chiều, đơn vị sai dimension và phép làm tròn.

## 13. Checklist đánh giá schema

- [ ] Mỗi khoản tiền có currency code rõ ràng.
- [ ] Không dùng số thực nhị phân cho số tiền cần đối soát.
- [ ] Số chữ số đơn vị nhỏ nhất được xác định theo mã tiền tệ.
- [ ] Đơn giá thể hiện đơn vị tính giá và lượng cơ sở.
- [ ] Quy tắc precision, scale và rounding được thống nhất.
- [ ] Mỗi đại lượng đo có unit code.
- [ ] Đơn vị thuộc đúng dimension của thuộc tính.
- [ ] Quy tắc chuyển đổi tuyến tính và có độ lệch được phân biệt.
- [ ] Phép đổi phụ thuộc ngữ cảnh có lưu dữ liệu ngữ cảnh.
- [ ] Tỷ giá có base, quote, chiều, nguồn và thời điểm.
- [ ] Giao dịch đã chốt giữ tỷ giá và số tiền thực tế đã áp dụng.
- [ ] Báo cáo không cộng các loại tiền hoặc dimension khác nhau trực tiếp.
- [ ] Giá trị nguồn và quy tắc chuyển đổi được giữ khi cần truy xuất.
- [ ] Danh mục và quy cách có thời điểm hiệu lực, không làm sai lịch sử.

## Kết luận

Tiền tệ và đại lượng đo là những giá trị có đơn vị, không phải những con số độc lập. Một khoản tiền cần mã tiền tệ; một phép đo cần đơn vị và chiều đại lượng; một đơn giá còn cần đơn vị tính giá; một tỷ giá cần chiều quy đổi, nguồn và thời điểm. Mô hình dữ liệu phải thể hiện các thông tin này để ngăn việc so sánh, cộng hoặc chuyển đổi sai.

Hãy chọn kiểu số chính xác phù hợp, quy định precision và rounding, quản lý danh mục mã tiền tệ và đơn vị, đồng thời bảo vệ cặp giá trị/đơn vị bằng ràng buộc. Khi chuyển đổi, giữ lại dữ liệu gốc và quy tắc đã áp dụng nếu cần đối soát. Khi danh mục hoặc quy cách thay đổi, dùng thời điểm hiệu lực để dữ liệu lịch sử tiếp tục mang đúng ý nghĩa.
