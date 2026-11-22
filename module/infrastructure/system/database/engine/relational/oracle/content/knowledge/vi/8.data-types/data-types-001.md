# Chọn kiểu dữ liệu theo miền giá trị, độ chính xác và nhu cầu truy vấn

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Kiểu dữ liệu  
> **Mục tiêu:** Chọn đúng kiểu dữ liệu cho từng cột Oracle theo **ý nghĩa nghiệp vụ**, **miền giá trị**, **độ chính xác**, **khối lượng lưu trữ** và **cách ứng dụng truy vấn**; biết tránh các lỗi thiết kế gây sai số, mất thông tin thời gian, chuyển kiểu ngầm hoặc khó sử dụng index.

## 1. Vì sao lựa chọn kiểu dữ liệu là quyết định thiết kế?

Giả sử ứng dụng bán hàng có ba giá trị:

```text
"001234"          Mã đơn hàng
1234              Số lượng
1234.00           Giá tiền
```

Ba giá trị có vẻ giống nhau về ký tự, nhưng có **ngữ nghĩa khác nhau**:

- Mã đơn hàng `"001234"` cần giữ số 0 đầu, thường so sánh bằng và không tham gia phép cộng → lưu dạng chuỗi.
- Số lượng `1234` là số đếm nguyên, tham gia tính tồn kho/tổng hợp → lưu kiểu số nguyên chính xác.
- Giá tiền `1234.00` phải giữ đơn vị và quy tắc làm tròn thập phân → lưu kiểu số thập phân chính xác.

Nếu đặt tất cả trong `VARCHAR2`, ứng dụng phải đổi chuỗi thành số để tính toán và dễ gặp lỗi dữ liệu. Nếu đặt tất cả trong `NUMBER`, mã đơn hàng có thể mất số 0 đầu. **Kiểu dữ liệu là cách thể hiện quy tắc nghiệp vụ trong cấu trúc database**, không chỉ là chọn cột có đủ chỗ để lưu.

### Năm câu hỏi trước khi chọn

1. **Giá trị đại diện điều gì?** Tiền, số lượng, mã, tên, sự kiện thời gian, khoảng thời gian, tài liệu, ảnh hay cờ logic?
2. **Miền giá trị hợp lệ là gì?** Có số âm, phần thập phân, dấu `+`, số 0 đầu, chuỗi Unicode, giá trị rỗng hoặc `NULL` không?
3. **Cần chính xác đến đâu?** Chính xác từng đơn vị tiền, đến mili giây, hay chấp nhận sai số dấu phẩy động?
4. **Truy vấn sẽ làm gì?** Tính tổng, lọc khoảng, sắp xếp, join theo khóa, tìm kiếm chuỗi, tìm kiếm JSON hay đọc LOB?
5. **Hệ thống nào đọc/ghi dữ liệu?** Java/JDBC, JSON API, báo cáo BI, bản Oracle đang sử dụng và quy tắc timezone/encoding?

Một lựa chọn phù hợp phải đồng thời giải quyết những câu hỏi này. Chọn kiểu chỉ dựa vào hình thức hiển thị có thể gây sai sót khó khắc phục khi dữ liệu đã lớn.

## 2. Bức tranh các nhóm kiểu dữ liệu Oracle

| Nhóm dữ liệu | Kiểu Oracle thường dùng | Tình huống điển hình | Lưu ý chính |
|---|---|---|---|
| Số thập phân chính xác | `NUMBER(p,s)` | Giá tiền, thuế suất, điểm số, số lượng có phần lẻ | Kiểm soát precision/scale và làm tròn |
| Số nguyên | `NUMBER(p,0)`, `NUMBER`; identity/sequence cho khóa | Số lượng, số thứ tự, ID số | Chọn đủ miền giá trị và không biến mã có số 0 đầu thành số |
| Số gần đúng | `BINARY_FLOAT`, `BINARY_DOUBLE` | Đo lường, thống kê, xử lý khoa học | Dấu phẩy động nhị phân có sai số biểu diễn |
| Chuỗi thay đổi độ dài | `VARCHAR2(n BYTE/CHAR)` | Tên, email, mã nghiệp vụ | Chọn ngữ nghĩa BYTE/CHAR; lưu ý collation và Unicode |
| Chuỗi độ dài cố định | `CHAR(n BYTE/CHAR)` | Mã chuẩn cố định thật sự | Có padding; không mặc định tốt hơn VARCHAR2 |
| Chuỗi charset quốc gia | `NCHAR`, `NVARCHAR2` | Nhu cầu riêng với national character set | Khi database dùng AL32UTF8, nhiều trường hợp VARCHAR2 đã đủ |
| Ngày/giờ đến giây | `DATE` | Ngày sinh, ngày lập chứng từ, ngày có giờ đến giây | Oracle DATE **có giờ/phút/giây**, không có timezone/fractional seconds |
| Thời điểm nhiều độ chính xác | `TIMESTAMP(p)` | Thời gian thao tác nội bộ, event có phần giây | Không tự mang timezone |
| Thời gian có múi giờ | `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE` | Sự kiện toàn cầu, audit, lịch liên múi giờ | Hai kiểu có ngữ nghĩa giữ/hiển thị timezone khác nhau |
| Khoảng thời gian | `INTERVAL YEAR TO MONTH`, `INTERVAL DAY TO SECOND` | Thời lượng xử lý, chu kỳ | Không thay bằng DATE nếu ý nghĩa là khoảng |
| Văn bản lớn | `CLOB`, `NCLOB` | Bài viết, mô tả dài, tài liệu | Truy vấn/index khác chuỗi thông thường |
| Dữ liệu nhị phân lớn | `BLOB` | Ảnh, PDF, tệp nhị phân | Không lưu nhị phân như VARCHAR2 |
| Nhị phân nhỏ / định danh | `RAW(n)` | UUID 16 byte, digest nhị phân | Có thể hiển thị hex qua RAWTOHEX |
| JSON | `JSON` ở phiên bản hỗ trợ; `CLOB`/`VARCHAR2` với `IS JSON` ở bản cũ | Payload linh hoạt | Thuộc tính truy vấn thường xuyên nên thiết kế có chủ đích |
| Boolean | `BOOLEAN` trong SQL ở phiên bản Oracle hỗ trợ; mã hóa có CHECK ở bản cũ | Cờ bật/tắt | Cần xét phiên bản và ngữ nghĩa NULL |
| Định dạng chuyên biệt | `XMLTYPE`, kiểu không gian/`VECTOR` ở phiên bản phù hợp | XML, GIS, tìm kiếm vector | Chỉ chọn khi chức năng và tính năng Oracle hỗ trợ |

**Nguyên tắc:** Ưu tiên kiểu có ý nghĩa sát nhất với dữ liệu. Không lưu mọi thứ thành `VARCHAR2(4000)` chỉ vì cách đó dễ chèn chuỗi ban đầu.

## 3. Miền giá trị là yếu tố đầu tiên

**Miền giá trị (domain)** là tập những giá trị hợp lệ về mặt nghiệp vụ, không chỉ là tập các giá trị mà kiểu dữ liệu có thể biểu diễn.

Ví dụ:

| Trường | Miền nghiệp vụ | Lựa chọn | Ràng buộc cần cân nhắc |
|---|---|---|---|
| `quantity` | Số nguyên không âm, tối đa dự kiến theo thiết kế | `NUMBER(10,0)` | `NOT NULL`, `CHECK (quantity >= 0)` |
| `unit_price` | Số tiền không âm, chính xác 2 chữ số thập phân | `NUMBER(15,2)` | `NOT NULL`, `CHECK (unit_price >= 0)` |
| `phone_number` | Chuỗi ký tự có thể có `+`, `0` đầu và dấu phân cách | `VARCHAR2(32 CHAR)` | Kiểm tra định dạng ở ứng dụng/constraint phù hợp |
| `postal_code` | Mã có thể chứa chữ và số 0 đầu | `VARCHAR2(20 CHAR)` | Không tính toán số học |
| `country_code` | Mã ISO chữ cái có độ dài cố định theo chuẩn | `CHAR(2 CHAR)` | Có thể thêm FK đến bảng mã quốc gia |
| `status` | Một tập trạng thái định danh | `VARCHAR2(20 CHAR)` | `CHECK (... IN (...))` hoặc FK đến bảng danh mục |
| `created_at` | Thời điểm tạo bản ghi theo instant tuyệt đối | `TIMESTAMP WITH TIME ZONE` | Mặc định `SYSTIMESTAMP`, chính sách timezone |
| `birth_date` | Ngày lịch không có ý nghĩa giờ | `DATE` | Chuẩn hóa phần giờ về 00:00:00 khi ghi |
| `attachment` | Nội dung nhị phân | `BLOB` hoặc object storage có metadata trong DB | Chính sách lưu trữ, streaming, bảo mật |
| `is_active` | Đúng/sai, đôi khi có “chưa biết” | `BOOLEAN` ở bản hỗ trợ hoặc `CHAR(1)` | Quy tắc ba trạng thái và `NOT NULL` nếu bắt buộc |

**Kiểu dữ liệu và ràng buộc phối hợp** để bảo vệ miền giá trị. Ví dụ `NUMBER(10,0)` cho phép giá trị âm, vì vậy riêng kiểu số nguyên chưa diễn đạt quy tắc “số lượng không âm”.

Các lớp ràng buộc khác nhau:

- `NOT NULL`: cột bắt buộc có giá trị.
- `CHECK`: điều kiện đơn giản trên giá trị, chẳng hạn không âm hoặc thuộc tập trạng thái.
- `UNIQUE` / `PRIMARY KEY`: tính duy nhất và định danh row.
- `FOREIGN KEY`: giá trị phải tồn tại trong bảng tham chiếu.
- Kiểm tra trong ứng dụng: quy tắc phức tạp, phụ thuộc dữ liệu bên ngoài hoặc cần thông báo lỗi chi tiết.

Không nên dựa hoàn toàn vào validation của UI: dữ liệu còn có thể đi qua ETL, batch, API và các script SQL khác.

## 4. NUMBER: độ chính xác thập phân, precision và scale

### 4.1. NUMBER(p,s) có nghĩa gì?

Kiểu `NUMBER(p,s)` trong Oracle cho phép thiết kế số **thập phân chính xác**:

- `p` (**precision**): tổng số chữ số có nghĩa được phép theo khai báo.
- `s` (**scale**): số chữ số nằm bên phải dấu thập phân theo khai báo khi `s` dương.
- `NUMBER(p,0)`: số nguyên theo nghĩa giá trị cột được lưu không có phần thập phân.
- `NUMBER` không chỉ định `p,s`: kiểu NUMBER linh hoạt hơn, phù hợp khi miền độ chính xác thực sự cần rộng; tuy nhiên với dữ liệu nghiệp vụ cụ thể thường nên khai báo rõ.

Ví dụ:

| Kiểu | Ví dụ hợp lệ | Giới hạn/ý nghĩa minh họa |
|---|---|---|
| `NUMBER(5,0)` | `12345` | Tối đa 5 chữ số nguyên dương, nếu không xét dấu |
| `NUMBER(5,2)` | `999.99` | 3 chữ số trước dấu, 2 chữ số sau dấu |
| `NUMBER(12,2)` | `9999999999.99` | 10 chữ số nguyên, 2 chữ số thập phân |
| `NUMBER(8,4)` | `12.3456` | Tổng 8 chữ số, 4 số sau dấu |
| `NUMBER(10,0)` | `450000` | Dữ liệu số nguyên có miền được ràng buộc |
| `NUMBER` | Giá trị chính xác thập phân trong giới hạn NUMBER | Không tự đặt quy tắc scale tiền tệ |

Oracle NUMBER có thể biểu diễn đến **38 chữ số có nghĩa** khi khai báo precision phù hợp. Với `NUMBER(p,s)`, nếu phần lẻ có nhiều chữ số hơn scale, Oracle có thể **làm tròn** khi lưu; nếu kết quả vượt precision thì có thể báo lỗi như `ORA-01438`.

Ví dụ:

```sql
CREATE TABLE lab_precision (
    amount NUMBER(5,2)
);

INSERT INTO lab_precision VALUES (12.345);
-- Giá trị lưu theo scale 2: có thể thành 12.35.

INSERT INTO lab_precision VALUES (9999.99);
-- Vượt miền NUMBER(5,2): lỗi precision.

ROLLBACK;
```

Vì scale có thể khiến Oracle làm tròn, đừng dùng kiểu dữ liệu như một cách thay thế cho quy tắc kiểm tra “không chấp nhận quá 2 chữ số phần lẻ” nếu nghiệp vụ yêu cầu từ chối dữ liệu đầu vào thay vì làm tròn. Ứng dụng hoặc constraint thích hợp phải xác định rõ chính sách.

### 4.2. Chọn NUMBER cho tiền

Giả sử hệ thống cần lưu giá trị tối đa gần `10^10` đơn vị tiền và hai chữ số phần lẻ:

```sql
amount NUMBER(12,2) NOT NULL
```

Nếu các giao dịch có thể lên tới hàng nghìn tỷ, cần tăng precision phù hợp dựa trên miền giá trị **dự báo trong vòng đời dữ liệu**, tránh chỉ nhìn vào giá trị hiện tại.

Một cột tiền thường cần cả **đơn vị tiền tệ**:

```sql
amount        NUMBER(18,2) NOT NULL,
currency_code CHAR(3 CHAR) NOT NULL
```

Cùng số `100.00` nhưng `VND` và `USD` có ý nghĩa rất khác. Với hệ thống đa tiền tệ, số chữ số phần lẻ còn phụ thuộc quy tắc từng currency và hệ thống kế toán; `NUMBER(18,2)` là ví dụ thiết kế, **không phải quy tắc chung cho mọi đồng tiền**.

Khi Java thao tác với số tiền Oracle NUMBER, nên sử dụng `java.math.BigDecimal` cho giá trị thập phân chính xác, không dùng `double` để cộng/trừ tiền theo cách có thể sinh sai số biểu diễn.

### 4.3. Giá trị số nguyên và khóa kỹ thuật

Với số lượng:

```sql
quantity NUMBER(10,0) DEFAULT 0 NOT NULL
         CHECK (quantity >= 0)
```

Với ID tự sinh:

```sql
id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY
   PRIMARY KEY
```

Identity hỗ trợ tạo giá trị khóa trong database. Nó giải quyết vấn đề **sinh ID**; nó không tự xác nhận ID là mã nghiệp vụ hay giải quyết tất cả yêu cầu phân tán.

Nếu hệ thống phân tán cần mã định danh toàn cục, có thể cân nhắc UUID được lưu bằng `RAW(16)` hoặc chuỗi chuẩn hóa; lựa chọn phụ thuộc hệ thống sinh ID, khả năng join và API.

### 4.4. NUMBER không nên dùng cho mọi chuỗi chữ số

Các giá trị sau thường là **mã**, không phải số:

- Điện thoại `+84901234567`.
- Mã bưu chính `00123`.
- Mã nhân viên `000057`.
- Mã sản phẩm `0123456789012` có check digit và yêu cầu giữ đúng từng ký tự.
- Số tài khoản dài có thể vượt độ chính xác NUMBER hoặc chứa số 0 đầu.

Vì không cần cộng trừ, lưu bằng `VARCHAR2`, cộng thêm constraint/validation nếu cần. Lưu dưới NUMBER có thể làm mất số 0 đầu và biến dữ liệu nhận diện thành đại lượng số học.

## 5. NUMBER và BINARY_FLOAT/BINARY_DOUBLE: chính xác so với gần đúng

### 5.1. Điểm khác biệt về biểu diễn

`NUMBER` là kiểu số thập phân chính xác của Oracle; trong khi:

- `BINARY_FLOAT`: số dấu phẩy động nhị phân, gần với IEEE 754 single precision.
- `BINARY_DOUBLE`: số dấu phẩy động nhị phân, gần với IEEE 754 double precision.

Các giá trị thập phân như `0.1` không biểu diễn chính xác bằng một số hữu hạn bit nhị phân trong nhiều trường hợp. Vì vậy phép tính dấu phẩy động có thể cho kết quả gần đúng.

Bảng lựa chọn:

| Nhu cầu | Nên ưu tiên | Vì sao |
|---|---|---|
| Tiền, số dư, hóa đơn | `NUMBER(p,s)` | Cần độ chính xác thập phân |
| Số nguyên đếm được | `NUMBER(p,0)` | Tránh phần lẻ; dùng CHECK cho miền |
| Thuế suất cần quy tắc làm tròn xác định | `NUMBER(p,s)` với scale phù hợp | Kiểm soát đơn vị tính và rounding |
| Giá trị cảm biến vật lý có sai số đo | `BINARY_DOUBLE` hoặc `NUMBER` tùy yêu cầu | Dấu phẩy động có thể phù hợp tốc độ và miền đo |
| Thuật toán khoa học cần số gần đúng | `BINARY_DOUBLE` | Thích hợp phép tính floating-point |
| Mã sản phẩm là chữ số | `VARCHAR2` | Không phải đại lượng cần tính toán |

Ví dụ:

```sql
CREATE TABLE lab_numeric_types (
    id NUMBER PRIMARY KEY,
    exact_value NUMBER(12,4),
    approximate_value BINARY_DOUBLE
);
```

Một điều cần hiểu là kiểu floating-point có thể biểu diễn giá trị đặc biệt như NaN hoặc vô cực theo khả năng của Oracle. Nếu bài toán yêu cầu giá trị hữu hạn, hợp lệ về đo lường, cần chủ động kiểm soát theo thiết kế.

### 5.2. Khi so sánh số gần đúng

Không nên kỳ vọng mọi phép toán `BINARY_DOUBLE` trả đúng một số thập phân cần so sánh bằng tuyệt đối. Trong xử lý số thực, quy tắc so sánh **sai khác trong ngưỡng chấp nhận được** thường hữu ích hơn `=` với kết quả tính toán.

Nhưng ngưỡng `epsilon` không được chọn tùy tiện: nó cần dựa trên sai số đo, phép biến đổi và yêu cầu khoa học/nghiệp vụ. Với tiền, tốt hơn là **không tạo ra sai số floating-point ngay từ đầu**.

### 5.3. Kiểu NUMBER trong Java

Với JDBC, cột NUMBER có thể được lấy bằng `BigDecimal` khi cần giữ decimal precision:

```java
BigDecimal amount = rs.getBigDecimal("AMOUNT");
```

Với cột số nguyên đã xác định miền nằm trong kiểu Java tương ứng, có thể lấy `int` hoặc `long`; với cột nullable, phải xử lý trường hợp `NULL` để không nhầm NULL thành `0`.

**Không tự suy luận `NUMBER(10)` luôn an toàn với Java `int`:** miền của NUMBER(10,0) lớn hơn miền số nguyên có dấu 32-bit. Kết hợp precision thực, constraint và yêu cầu ứng dụng để chọn kiểu Java.

## 6. CHAR, VARCHAR2 và NVARCHAR2: chuỗi có ý nghĩa gì?

### 6.1. VARCHAR2 là lựa chọn thông dụng cho text thay đổi độ dài

`VARCHAR2(n)` phù hợp với tên, email, mã trạng thái, mã đơn hàng và nhiều trường text ngắn.

Ví dụ:

```sql
customer_name VARCHAR2(150 CHAR) NOT NULL,
email         VARCHAR2(254 CHAR),
order_code    VARCHAR2(40 CHAR)
```

Chuỗi được lưu với độ dài thực tế trong giới hạn khai báo và giới hạn byte của Oracle.

**Vì sao không đặt VARCHAR2(4000) cho tất cả?** Giới hạn quá rộng làm yếu đi khả năng diễn đạt miền giá trị, khiến dữ liệu sai định dạng dễ lọt vào và ảnh hưởng thiết kế index/ứng dụng. Nên dựa trên giới hạn nghiệp vụ: email tối đa theo quy tắc hệ thống, mã đơn hàng theo format, tên người theo yêu cầu hiển thị.

### 6.2. BYTE và CHAR semantics

Trong database sử dụng AL32UTF8, ký tự Unicode có thể chiếm từ một đến nhiều byte. Oracle cho phép khai báo độ dài chuỗi theo:

- `VARCHAR2(30 BYTE)`: tối đa **30 byte**, số ký tự thực tế có thể ít hơn.
- `VARCHAR2(30 CHAR)`: tối đa **30 ký tự** theo character length semantics, nhưng vẫn chịu **giới hạn byte tối đa** của kiểu dữ liệu trong cấu hình database.

Ví dụ:

```sql
CREATE TABLE lab_text_length (
    code      VARCHAR2(30 BYTE),
    full_name VARCHAR2(30 CHAR)
);
```

Nếu cột chứa tiếng Việt hoặc dữ liệu nhiều ngôn ngữ, dùng `CHAR semantics` cho những giới hạn biểu đạt số ký tự thường hợp lý hơn `BYTE semantics`.

Kiểm tra độ dài theo ký tự và byte:

```sql
SELECT LENGTH('Tiếng Việt')  AS char_length,
       LENGTHB('Tiếng Việt') AS byte_length
FROM dual;
```

Trên charset AL32UTF8, nhiều ký tự có dấu chiếm nhiều byte nên hai số đo có thể khác nhau. `LENGTH`/`LENGTHB` hữu ích khi chẩn đoán lỗi vượt giới hạn.

> **Giới hạn thực tế:** Trong cấu hình `MAX_STRING_SIZE=STANDARD`, giá trị `VARCHAR2` trong SQL chịu giới hạn thông dụng **4.000 byte**; ở `EXTENDED` có thể lên tới **32.767 byte** trong các trường hợp được hỗ trợ. `VARCHAR2(4000 CHAR)` không có nghĩa chắc chắn lưu được 4.000 ký tự mỗi ký tự chiếm 4 byte. Cấu hình `MAX_STRING_SIZE` không nên thay đổi chỉ để sửa một cột mà chưa đánh giá ảnh hưởng toàn database.

### 6.3. CHAR: độ dài cố định và padding

`CHAR(n)` dành cho chuỗi độ dài cố định. Oracle đệm khoảng trắng để đạt độ dài khai báo, dẫn đến hành vi so sánh/hiển thị cần chú ý.

Ví dụ:

```sql
country_code CHAR(2 CHAR)
```

Với mã quốc gia chuẩn dài đúng 2 ký tự, `CHAR(2 CHAR)` có thể hợp lý. Nhưng `CHAR(100)` không tốt hơn `VARCHAR2(100 CHAR)` chỉ vì “cấp phát cố định giúp nhanh hơn”; nó có thể tạo padding và gây hiểu nhầm khoảng trắng.

Với trạng thái `'NEW'`, `'PAID'`, `'CANCELLED'` có độ dài khác nhau, ưu tiên `VARCHAR2` và một ràng buộc miền giá trị.

### 6.4. NCHAR và NVARCHAR2

`NCHAR` và `NVARCHAR2` sử dụng **national character set** được cấu hình riêng của Oracle. Chúng phù hợp một số bài toán tương thích/ngôn ngữ có yêu cầu cụ thể.

Nếu database đã được thiết kế với **AL32UTF8**, `VARCHAR2` có thể lưu Unicode cho đa số dữ liệu ứng dụng. Không mặc định chuyển mọi cột tên người sang `NVARCHAR2`; cần xét charset nguồn–đích, JDBC và nhu cầu thực tế. Lựa chọn national charset không thay thế thiết kế collation hoặc chuẩn hóa dữ liệu.

### 6.5. Chuỗi rỗng và NULL trong Oracle

Trong Oracle SQL, chuỗi ký tự độ dài bằng 0 (`''`) hiện được xử lý tương đương `NULL` cho các kiểu ký tự thông thường như `VARCHAR2`. Đây là khác biệt đáng chú ý so với nhiều hệ quản trị khác.

Hệ quả:

- Không thể dùng `''` như một trạng thái riêng biệt với NULL trong cột VARCHAR2 theo hành vi hiện tại.
- `' '` (một dấu cách) **khác** chuỗi rỗng/NULL.
- Dùng `IS NULL` thay vì `= NULL`.
- Nếu nghiệp vụ cần ba trạng thái “chưa nhập”, “rỗng có chủ ý” và “có nội dung”, phải thiết kế thêm cột trạng thái hoặc quy ước khác.

Ví dụ:

```sql
SELECT
    CASE WHEN CAST('' AS VARCHAR2(10)) IS NULL
         THEN 'NULL'
         ELSE 'NOT NULL'
    END AS empty_string_result
FROM dual;
```

### 6.6. Collation, viết hoa/thường và tìm kiếm

Kiểu `VARCHAR2` lưu ký tự, nhưng **quy tắc so sánh/sắp xếp** còn chịu ảnh hưởng collation, `NLS_SORT`, `NLS_COMP` và các khả năng collation theo phiên bản.

Cần xác định nghiệp vụ:

- Email, username có phân biệt hoa/thường hay không?
- Mã nghiệp vụ có chuẩn hóa chữ hoa và có phân biệt dấu không?
- Tìm kiếm tên tiếng Việt có cần bỏ dấu, tìm tiền tố, hay full-text không?
- Sắp xếp theo bảng chữ cái của ngôn ngữ nào?

Không tự giải quyết mọi việc bằng `UPPER(column)` trong truy vấn vì biểu thức trên cột có thể ảnh hưởng khả năng dùng index thường. Nếu truy vấn thực tế liên tục dùng một hàm chuẩn hóa, cân nhắc **function-based index** hoặc collation thiết kế rõ, sau khi kiểm tra query plan.

Ví dụ chuẩn hóa email có thể được áp dụng tại ứng dụng trước khi ghi, hoặc dựa trên index/constraint phù hợp với quy tắc hệ thống. Không có một quy tắc collation duy nhất đúng cho mọi miền nghiệp vụ.

## 7. DATE, TIMESTAMP và timezone: lưu đúng ý nghĩa thời gian

### 7.1. Oracle DATE có gì?

Trong Oracle, `DATE` lưu **năm, tháng, ngày, giờ, phút, giây**. Nó:

- Không lưu phần giây lẻ.
- Không chứa timezone.
- Không đồng nghĩa kiểu `LocalDate` chỉ có ngày trong mọi hệ thống lập trình.

Ví dụ tạo giá trị ngày theo literal độc lập định dạng phiên:

```sql
SELECT DATE '2026-11-14' AS day_value
FROM dual;
```

Literal `DATE 'YYYY-MM-DD'` tạo thời điểm 00:00:00 trong ngày đó, **không tự gắn timezone**.

Với ngày sinh, ngày đến hạn chỉ có ý nghĩa ngày lịch, `DATE` là lựa chọn thường gặp, nhưng ứng dụng phải quy ước **phần giờ = 00:00:00** hoặc ràng buộc rõ nếu chỉ chấp nhận ngày.

### 7.2. TIMESTAMP(p) lưu phần giây nhưng không mang timezone

`TIMESTAMP(p)` có độ chính xác phần giây theo tham số `p`, ví dụ:

```sql
processed_at TIMESTAMP(6)
```

Ví dụ literal:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456'
FROM dual;
```

Phù hợp với thời điểm/timestamp trong một ngữ cảnh mà quy ước timezone đã được quản lý ở ứng dụng, hoặc cần phần giây nhưng không cần lưu timezone trong giá trị.

**Rủi ro:** Nếu client ở Việt Nam ghi `2026-11-14 09:30:45` còn client ở Mỹ ghi cùng chuỗi ký tự, hai giá trị `TIMESTAMP` có thể biểu thị **hai instant thực khác nhau**, vì kiểu này không cho biết timezone.

### 7.3. TIMESTAMP WITH TIME ZONE

`TIMESTAMP WITH TIME ZONE` diễn đạt thời gian cùng thông tin múi giờ hoặc offset thích hợp. Phù hợp khi cần biết một sự kiện xảy ra tại **thời điểm tuyệt đối** và làm việc với các hệ thống ở nhiều múi giờ.

Ví dụ:

```sql
CREATE TABLE lab_event_log (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(100 CHAR) NOT NULL,
    occurred_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL
);
```

Chèn thời gian có offset:

```sql
INSERT INTO lab_event_log (event_name, occurred_at)
VALUES (
    'PAYMENT_CONFIRMED',
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:45 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    )
);

COMMIT;
```

Giá trị có offset giúp xác định instant rõ hơn. Nếu ứng dụng yêu cầu quy tắc giờ mùa hè hay tên vùng địa lý, có thể dùng timezone region được hỗ trợ thay vì chỉ offset, đồng thời quản lý phiên bản timezone file phù hợp.

### 7.4. TIMESTAMP WITH LOCAL TIME ZONE

`TIMESTAMP WITH LOCAL TIME ZONE` có cơ chế chuẩn hóa theo database timezone khi lưu và chuyển sang timezone session khi truy xuất. Nó hữu ích khi muốn người dùng ở nhiều nơi nhìn cùng thời điểm theo **múi giờ của phiên làm việc**, nhưng không cần giữ lại thông tin timezone gốc của input.

So sánh:

| Kiểu | Phần giây | Thông tin timezone | Chọn khi |
|---|---|---|---|
| `DATE` | Không | Không | Ngày lịch, hoặc thời điểm đến giây trong ngữ cảnh xác định |
| `TIMESTAMP(p)` | Có | Không | Timestamp địa phương, ứng dụng quản lý timezone theo quy ước |
| `TIMESTAMP(p) WITH TIME ZONE` | Có | Có thông tin offset/vùng | Sự kiện toàn cầu, đối chiếu múi giờ và instant |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Có | Không giữ timezone gốc theo cùng cách; hiển thị theo session | Dữ liệu timestamp nhiều timezone, muốn chuyển theo timezone session |

Nếu yêu cầu **giữ nguyên timezone nguồn được nhập** như một dữ kiện nghiệp vụ, không chọn `WITH LOCAL TIME ZONE` chỉ vì tên có chữ “TIME ZONE”.

### 7.5. DATE/SYSDATE/SYSTIMESTAMP/CURRENT_TIMESTAMP

Một số hàm dễ nhầm:

- `SYSDATE`: thời gian từ hệ điều hành của database server dưới dạng Oracle `DATE`, chính xác đến giây.
- `SYSTIMESTAMP`: timestamp hiện tại phía database server có thông tin timezone.
- `CURRENT_TIMESTAMP`: timestamp hiện tại theo timezone của session, thuộc kiểu có timezone.
- `LOCALTIMESTAMP`: timestamp hiện tại theo timezone session, **không** mang timezone.

Ví dụ:

```sql
SELECT SYSDATE,
       SYSTIMESTAMP,
       CURRENT_TIMESTAMP,
       LOCALTIMESTAMP
FROM dual;
```

Trong ứng dụng phân tán, cần quy ước rõ nguồn thời gian chuẩn, timezone session và cách hiển thị theo người dùng.

### 7.6. Truy vấn theo ngày: dùng khoảng nửa mở

Giả sử cột `order_date` là Oracle `DATE` và có index. Muốn tìm mọi đơn hàng trong ngày 14/11/2026:

**Không nên** dùng so sánh bằng với ngày nếu cột có phần giờ:

```sql
WHERE order_date = DATE '2026-11-14'
```

Điều kiện trên chỉ khớp các giá trị đúng `00:00:00` trong ngày đó.

**Nên** dùng khoảng nửa mở:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Cách này:

- Bao gồm toàn bộ thời điểm trong ngày, bất kể giờ/phút/giây.
- Không phải gọi `TRUNC(order_date)` trên cột tại mỗi row.
- Thường tạo điều kiện tốt hơn để optimizer dùng **index range scan** hoặc **partition pruning**, nếu thiết kế và thống kê phù hợp.

Tùy ngữ nghĩa timezone, với cột `TIMESTAMP WITH TIME ZONE` cần chuyển **ranh giới ngày theo đúng múi giờ nghiệp vụ** thành khoảng thời điểm tương ứng. Ngày trong một timezone không mặc định trùng ngày ở timezone khác.

### 7.7. INTERVAL cho thời lượng

Một **thời lượng** không phải một **mốc thời gian**. Oracle có:

- `INTERVAL YEAR TO MONTH`: khoảng theo năm/tháng.
- `INTERVAL DAY TO SECOND`: khoảng theo ngày/giờ/phút/giây, có thể chứa phần giây.

Ví dụ:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:00'
       + INTERVAL '45' MINUTE AS end_time
FROM dual;
```

Nếu yêu cầu lưu thời gian phản hồi đo bằng milliseconds, đôi khi `NUMBER(12,0)` (mili giây) cũng phù hợp hơn `INTERVAL`, nhất là khi cần tính toán thống kê và biểu diễn qua API. Chọn dựa trên ngữ nghĩa và thao tác thực tế, ghi rõ **đơn vị** để tránh nhầm giây với mili giây.

## 8. LOB, RAW và dữ liệu phi cấu trúc

### 8.1. VARCHAR2 hay CLOB?

`VARCHAR2` phù hợp text ngắn hoặc trung bình trong giới hạn cấu hình. `CLOB` dành cho văn bản dài, ví dụ nội dung bài viết, mô tả sản phẩm lớn hoặc tài liệu.

| Đặc tính | VARCHAR2 | CLOB |
|---|---|---|
| Dung lượng | Có giới hạn byte theo cấu hình | Có thể chứa lượng văn bản rất lớn |
| Truy vấn bằng `=` / `ORDER BY` | Thao tác SQL thường trực tiếp | Có các hạn chế/chi phí và hàm xử lý LOB riêng |
| Index B-tree trên cột | Có thể khi độ dài/kiểu index phù hợp | Không xây B-tree trực tiếp trên toàn CLOB như VARCHAR2 |
| Tìm kiếm full-text | Có thể dùng các phương án phù hợp | Thường cân nhắc Oracle Text nếu cần tìm kiếm nội dung |
| Đọc/ghi từ JDBC | String với kích thước phù hợp | Reader/stream hoặc API LOB |
| Mục đích | Tên, mã, ghi chú ngắn | Bài viết, tài liệu, nội dung dài |

Không chọn `CLOB` cho mọi cột chỉ để “khỏi lo kích thước”. Những cột cần so sánh/join/index theo giá trị đầy đủ vẫn nên dùng kiểu dữ liệu có thể khai báo và index hợp lý.

### 8.2. BLOB và file nhị phân

`BLOB` lưu dữ liệu nhị phân như hình ảnh, PDF hoặc nội dung đã nén. Không nên biến bytes thành chuỗi văn bản rồi đặt trong `VARCHAR2` nếu dữ liệu không thực sự là văn bản.

Ví dụ:

```sql
CREATE TABLE lab_attachments (
    attachment_id RAW(16) DEFAULT SYS_GUID() NOT NULL,
    original_name VARCHAR2(255 CHAR) NOT NULL,
    mime_type VARCHAR2(120 CHAR) NOT NULL,
    content BLOB,
    created_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_attachments PRIMARY KEY (attachment_id)
);
```

Chọn lưu BLOB trong database hay đưa file vào object storage, chỉ lưu URL/key và metadata trong Oracle còn phụ thuộc khối lượng, backup, latency, transaction, quản trị truy cập và hạ tầng. `BFILE` là tham chiếu tới file ngoài do server quản lý, có các giới hạn khác BLOB; không dùng như một BLOB giao dịch thông thường.

### 8.3. RAW(16) cho định danh 128 bit

`RAW(n)` lưu byte không qua cơ chế chuyển ký tự. Một UUID/GUID 128 bit có thể lưu trong `RAW(16)` để gọn hơn chuỗi hex định dạng có dấu gạch.

Ví dụ:

```sql
CREATE TABLE lab_uuid_entity (
    entity_id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    title VARCHAR2(120 CHAR) NOT NULL
);

INSERT INTO lab_uuid_entity (title)
VALUES ('Bản ghi thử');

SELECT RAWTOHEX(entity_id) AS entity_id_hex, title
FROM lab_uuid_entity;
```

`SYS_GUID()` sinh định danh RAW 16 byte trong Oracle. Nếu ứng dụng cần đúng tiêu chuẩn/version UUID cụ thể, phải đồng bộ cơ chế sinh ID của hệ thống; không mặc định mọi GUID có cùng phiên bản UUID.

### 8.4. LONG nên tránh cho thiết kế mới

Một số hệ thống cũ có cột `LONG` hoặc `LONG RAW`. Với schema mới, ưu tiên `CLOB` hoặc `BLOB` theo loại dữ liệu, bởi các kiểu LONG có hạn chế lớn trong thao tác SQL và đã được thay thế về mặt thiết kế.

## 9. JSON, XML và kiểu chuyên biệt

### 9.1. JSON: chọn kiểu theo phiên bản và cách truy vấn

Oracle cung cấp các chức năng truy vấn JSON như `JSON_VALUE`, `JSON_EXISTS` và `JSON_TABLE`.

Ở Oracle 19c, JSON thường được lưu trong `VARCHAR2`, `CLOB` hoặc `BLOB` kèm ràng buộc `IS JSON`:

```sql
CREATE TABLE lab_json_legacy (
    id NUMBER PRIMARY KEY,
    payload CLOB
        CONSTRAINT ck_lab_json_valid CHECK (payload IS JSON)
);
```

Ví dụ:

```sql
INSERT INTO lab_json_legacy (id, payload)
VALUES (
    1,
    '{"channel":"WEB","priority":2,"paid":true}'
);

SELECT id,
       JSON_VALUE(payload, '$.channel' RETURNING VARCHAR2(20)) AS channel
FROM lab_json_legacy
WHERE JSON_VALUE(payload, '$.priority' RETURNING NUMBER) >= 2;
```

Trong các phiên bản mới hơn có hỗ trợ **kiểu dữ liệu JSON native** (ví dụ Oracle Database 21c và các bản tiếp theo phù hợp), có thể dùng kiểu `JSON` để Oracle lưu và thao tác dữ liệu JSON theo cơ chế của phiên bản đó.

**Khi nên tách thành cột quan hệ?** Nếu `channel`, `status`, `customer_id` hoặc `created_at` luôn là thuộc tính cốt lõi và thường xuyên lọc/join/index, việc đặt chúng thành cột có kiểu cụ thể giúp ràng buộc miền giá trị và tối ưu hóa dễ hơn.

JSON hữu ích cho phần cấu trúc linh hoạt, không phải lý do để thay mọi cột quan hệ bằng một payload.

### 9.2. Truy vấn JSON và index

Nếu thường lọc:

```sql
WHERE JSON_VALUE(payload, '$.priority' RETURNING NUMBER) >= 2
```

DBA có thể xem xét function-based index, JSON search index hoặc cấu trúc index chuyên biệt được phiên bản hỗ trợ. Quyết định phải dựa trên truy vấn và kế hoạch thực thi; một payload JSON lớn có thể làm truy vấn chậm nếu mọi bản ghi đều phải parse/đánh giá mà không có đường truy cập phù hợp.

### 9.3. XMLTYPE và dữ liệu đặc thù

Nếu nghiệp vụ dùng tài liệu XML và cần thao tác theo cấu trúc XML, `XMLTYPE` cùng hệ hàm XML có thể thích hợp hơn lưu XML như chuỗi không có ràng buộc.

Một số tính năng Oracle còn có kiểu chuyên biệt cho không gian địa lý, vector và các bài toán tìm kiếm khác. Chỉ dùng khi phiên bản/edition hỗ trợ và **miền dữ liệu lẫn nhu cầu truy vấn** thực sự yêu cầu chúng; không thay điểm tọa độ hoặc biểu diễn vector bằng text có dấu phẩy chỉ để tránh học kiểu chuyên biệt.

## 10. BOOLEAN: chọn theo phiên bản Oracle và ba trạng thái logic

### 10.1. SQL BOOLEAN ở Oracle mới

Oracle Database **23c/23ai và các phiên bản mới phù hợp** có hỗ trợ kiểu `BOOLEAN` trong SQL. Cột boolean diễn đạt rõ miền **TRUE, FALSE** và `NULL` (khi nullable).

Ví dụ cú pháp trên phiên bản SQL hỗ trợ BOOLEAN:

```sql
CREATE TABLE lab_flags_new (
    id NUMBER PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);
```

`BOOLEAN` làm rõ ý nghĩa hơn dùng chuỗi `'Y'`/`'N'` cho một cờ logic, nhưng phải kiểm tra tính tương thích khi ứng dụng/database cần hỗ trợ cả 19c hoặc 21c.

### 10.2. Trước SQL BOOLEAN: mã hóa cờ có constraint

Trong Oracle 19c và nhiều hệ thống đang sử dụng, **SQL column BOOLEAN** không được hỗ trợ như kiểu cột bình thường, dù **PL/SQL BOOLEAN** có tồn tại trong ngôn ngữ PL/SQL.

Cách phổ biến:

```sql
CREATE TABLE lab_flags_legacy (
    id NUMBER PRIMARY KEY,
    is_active CHAR(1 CHAR) DEFAULT 'Y' NOT NULL,
    CONSTRAINT ck_lab_is_active
        CHECK (is_active IN ('Y', 'N'))
);
```

Hoặc:

```sql
is_active NUMBER(1,0) DEFAULT 1 NOT NULL
          CHECK (is_active IN (0,1))
```

Giá trị `NULL` chỉ nên được phép nếu nghiệp vụ thực sự có trạng thái “không biết/chưa quyết định”. Nếu cột đại diện cờ bắt buộc, dùng `NOT NULL`.

**Quan trọng:** `CHECK (is_active IN (...))` không tự cấm NULL vì kết quả UNKNOWN vẫn có thể thỏa quy tắc CHECK của SQL; cần thêm `NOT NULL` nếu yêu cầu cấm NULL.

## 11. Bảng chọn kiểu theo tình huống nghiệp vụ

| Dữ liệu | Kiểu đề xuất | Vì sao | Không nên |
|---|---|---|---|
| ID bản ghi nội bộ | `NUMBER`/`NUMBER(p,0)` với identity/sequence hoặc `RAW(16)` nếu dùng GUID | Khóa có chiến lược sinh phù hợp | Dùng tên người/email làm khóa chính mặc định |
| Mã đơn `0000123` | `VARCHAR2(30 CHAR)` | Giữ số 0 đầu và định dạng | `NUMBER` |
| Số lượng tồn kho | `NUMBER(10,0)` + CHECK | Đếm số nguyên, không âm | `VARCHAR2` |
| Giá bán | `NUMBER(18,2)` hoặc scale phù hợp | Chính xác decimal | `BINARY_DOUBLE` cho tiền |
| Tỷ lệ có bốn chữ số thập phân | `NUMBER(p,4)` với p đủ rộng | Định nghĩa rõ precision | `FLOAT` không xác định quy tắc rounding |
| Số đo cảm biến | `BINARY_DOUBLE` hoặc `NUMBER(p,s)` | Phụ thuộc sai số/tính toán | Mặc định chọn tiền tệ-style scale nếu không phù hợp |
| Điện thoại | `VARCHAR2(32 CHAR)` | Có `+`, số 0 đầu, ký tự định dạng | `NUMBER` |
| Mã bưu chính | `VARCHAR2(20 CHAR)` | Có thể có chữ, số 0 đầu | `NUMBER` |
| Tên khách hàng tiếng Việt | `VARCHAR2(150 CHAR)` | Độ dài theo ký tự và Unicode | `CHAR(150)` |
| Mã tiền tệ ISO | `CHAR(3 CHAR)` + FK/CHECK | Độ dài cố định chuẩn | `NUMBER` |
| Ngày sinh | `DATE`, quy ước bỏ giờ | Ngày lịch | `VARCHAR2('dd/mm/yyyy')` |
| Audit event toàn cầu | `TIMESTAMP(6) WITH TIME ZONE` | Instant rõ ràng và timezone | `VARCHAR2` hoặc TIMESTAMP không quy ước múi giờ |
| Thời lượng xử lý | `INTERVAL DAY TO SECOND` hoặc `NUMBER` kèm đơn vị | Duration khác timestamp | `DATE` |
| Ghi chú ngắn | `VARCHAR2(1000 CHAR)` khi byte limit phù hợp | Truy cập text ngắn | `CLOB` không cần thiết |
| Nội dung bài viết dài | `CLOB` | Văn bản lớn | `VARCHAR2` vượt giới hạn |
| Ảnh/tệp PDF | `BLOB` hoặc storage ngoài + metadata | Nhị phân | `VARCHAR2` |
| UUID 128 bit | `RAW(16)` hoặc chuỗi chuẩn nếu cần tương thích | Byte chính xác, gọn | `NUMBER` không xét cách biểu diễn |
| Payload linh hoạt | `JSON` hoặc kiểu lưu JSON có `IS JSON` theo bản | Tài liệu có cấu trúc | Text không kiểm tra định dạng |
| Cờ bật/tắt | `BOOLEAN` khi được hỗ trợ hoặc `CHAR(1)` + CHECK | Miền logic rõ ràng | `VARCHAR2(100)` không constraint |

Các giá trị `p,s,n` trong bảng là **minh họa thiết kế**. Dự án thực tế phải xác định giới hạn dựa trên phân tích nghiệp vụ, dữ liệu đã có và dự kiến tăng trưởng.

## 12. Ví dụ thiết kế một schema đơn hàng có kiểu dữ liệu nhất quán

Giả sử hệ thống cần lưu:

- ID nội bộ do Oracle sinh.
- Mã đơn hiển thị, có thể chứa số 0 đầu và ký tự.
- ID khách hàng dạng số.
- Tổng tiền và currency.
- Thời điểm tạo có timezone.
- Kênh đặt hàng thuộc tập giá trị hữu hạn.
- Ghi chú văn bản dài tùy chọn.

DDL:

```sql
CREATE TABLE app_orders (
    order_id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    order_code VARCHAR2(40 CHAR) NOT NULL,
    customer_id NUMBER(19,0) NOT NULL,
    total_amount NUMBER(18,2) NOT NULL,
    currency_code CHAR(3 CHAR) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    sales_channel VARCHAR2(12 CHAR) NOT NULL,
    note_text CLOB,

    CONSTRAINT pk_app_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_app_orders_code UNIQUE (order_code),
    CONSTRAINT ck_app_orders_total CHECK (total_amount >= 0),
    CONSTRAINT ck_app_orders_channel
        CHECK (sales_channel IN ('WEB', 'APP', 'STORE'))
);
```

Trong ứng dụng thật, `CUSTOMER_ID` thường có **foreign key** đến bảng khách hàng, `CURRENCY_CODE` có thể có FK đến bảng danh mục đơn vị tiền và các ràng buộc khác liên quan quy tắc giao dịch. Ví dụ tập trung vào chọn kiểu dữ liệu.

Thêm hai đơn hàng:

```sql
INSERT INTO app_orders (
    order_code, customer_id, total_amount, currency_code,
    created_at, sales_channel, note_text
) VALUES (
    '00001582', 1001, 125000.00, 'VND',
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ),
    'WEB', 'Giao trong giờ hành chính'
);

INSERT INTO app_orders (
    order_code, customer_id, total_amount, currency_code,
    created_at, sales_channel
) VALUES (
    '00001583', 1002, 89000.00, 'VND',
    TO_TIMESTAMP_TZ(
        '2026-11-14 10:00:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ),
    'APP'
);

COMMIT;
```

Những thuộc tính đáng chú ý:

- `order_code` giữ nguyên chuỗi `00001582`.
- `total_amount` là decimal chính xác, phù hợp tổng hợp tiền có cùng currency.
- `created_at` giữ thông tin offset khi ghi; truy vấn theo timezone cần có ranh giới đúng.
- `sales_channel` được giới hạn ở `WEB`, `APP`, `STORE`.
- `note_text` chấp nhận NULL khi không có ghi chú.
- `order_id` là khóa kỹ thuật, tách khỏi mã đơn nghiệp vụ.

### 12.1. Tổng hợp tiền đúng đơn vị

```sql
SELECT currency_code,
       SUM(total_amount) AS total_amount
FROM app_orders
GROUP BY currency_code;
```

Không cộng `100 USD` với `100 VND` thành tổng `200` nếu chưa chuyển đổi theo tỷ giá và quy tắc nghiệp vụ. Kiểu `NUMBER` bảo đảm phép cộng thập phân phù hợp; việc hiểu **đơn vị** vẫn thuộc mô hình nghiệp vụ.

### 12.2. Truy vấn mã đơn bằng chính kiểu chuỗi

```sql
SELECT order_id, order_code, total_amount
FROM app_orders
WHERE order_code = '00001582';
```

Cột `ORDER_CODE` là chuỗi. Không viết `WHERE order_code = 1582` vì chuyển kiểu ngầm có thể làm sai ngữ nghĩa số 0 đầu, gây lỗi với mã có chữ, và ảnh hưởng cách optimizer sử dụng index.

### 12.3. Truy vấn thời gian theo đúng timezone

Ví dụ yêu cầu dữ liệu trong ngày **14/11/2026 theo UTC+07:00**, dùng ranh giới hai thời điểm có offset rõ ràng:

```sql
SELECT order_code, created_at
FROM app_orders
WHERE created_at >= TO_TIMESTAMP_TZ(
          '2026-11-14 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND created_at < TO_TIMESTAMP_TZ(
          '2026-11-15 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      );
```

Cách dùng ranh giới phù hợp ngữ nghĩa ngày tại offset đã chọn. Với vùng giờ có DST, nên dùng **timezone region** và quy tắc chuyển đổi phù hợp, bởi một ngày địa phương không nhất thiết luôn dài 24 giờ.

## 13. Kiểu dữ liệu ảnh hưởng đến optimizer, index và truy vấn thế nào?

### 13.1. So sánh phải đồng nhất kiểu

SQL:

```sql
SELECT *
FROM app_orders
WHERE customer_id = 1001;
```

phù hợp vì `CUSTOMER_ID` là NUMBER.

Ngược lại:

```sql
WHERE customer_id = '1001'
```

có thể khiến Oracle thực hiện **implicit conversion** từ chuỗi sang số, phụ thuộc ngữ cảnh. Dù đôi khi cho kết quả đúng, ứng dụng nên dùng bind variable đúng kiểu số để tránh NLS/cast ngầm và lỗi dữ liệu.

Với cột chuỗi:

```sql
WHERE order_code = '00001582'
```

đừng truyền giá trị là số nguyên chỉ vì mã đơn trông giống số. Việc Oracle chuyển **cột** bằng `TO_NUMBER(order_code)` có thể gây lỗi khi tồn tại mã không thuần số và khiến index thường khó dùng.

### 13.2. Giữ cột truy vấn ở dạng nguyên thủy khi lọc range

Với `DATE`:

```sql
-- Ít thuận lợi cho index thường nếu không có function-based index:
WHERE TRUNC(order_date) = DATE '2026-11-14'

-- Thường tốt hơn cho lọc range:
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Không có quy tắc “dùng hàm trên cột là luôn chậm”; Oracle có function-based indexes và optimizer transformations. Nhưng predicate trực tiếp trên cột và bind có kiểu phù hợp thường dễ tối ưu hơn.

### 13.3. Sắp xếp số và chuỗi khác nhau

Giả sử có các giá trị:

```text
"2", "10", "100"
```

Lưu trong `VARCHAR2` và sắp theo từ điển có thể cho `"10", "100", "2"`; lưu trong `NUMBER` và `ORDER BY` theo số cho `2, 10, 100`.

Nên hỏi: đây là **mã** hay **độ lớn số học**? Không chọn NUMBER chỉ để “ORDER BY ra đúng” nếu dữ liệu thực chất là mã có quy tắc riêng. Khi mã cần sắp theo phần số, thiết kế cột sort riêng hoặc quy tắc tách/chuẩn hóa phù hợp.

### 13.4. Kích thước khóa và index

Cột dùng làm **primary key**, **foreign key** hoặc cột join thường xuất hiện trong index. Kiểu quá lớn có thể làm tăng kích thước index và chi phí bộ nhớ/I/O.

Ví dụ:

- ID ngắn bằng `NUMBER`/`RAW(16)` thường gọn hơn một chuỗi ID dài vài trăm ký tự.
- Nếu khóa là mã nghiệp vụ có độ dài vừa phải, `VARCHAR2` vẫn có thể phù hợp.
- Cột `CLOB` không phù hợp để dùng trực tiếp làm B-tree primary key.
- Chuỗi có so sánh không phân biệt hoa/thường cần chiến lược chuẩn hóa/collation/index tương ứng.

Không cần ép tất cả khóa thành NUMBER; cần xét khả năng ổn định, tính duy nhất, miền dữ liệu và cách tích hợp.

### 13.5. Lựa chọn kiểu dữ liệu và partitioning

Partition theo ngày thường yêu cầu cột mang giá trị thời gian có ý nghĩa. Nếu lưu `created_at` thành chuỗi `'14/11/2026 09:30'`, việc filter tháng/quý, sắp xếp và quản lý partition trở nên khó hơn và dễ phụ thuộc NLS.

Với cột thời gian đúng kiểu, có thể thiết kế **range partitioning** theo thời gian hoặc các chiến lược được Oracle hỗ trợ; tối ưu hay không vẫn phụ thuộc workload và phiên bản.

### 13.6. Thống kê và cardinality

Optimizer sử dụng thống kê, histogram, mật độ dữ liệu và thông tin về kiểu cột để ước lượng số row thỏa điều kiện. Một cột trạng thái chỉ có vài giá trị rất khác với cột UUID gần như duy nhất.

Kiểu dữ liệu đúng cùng **constraint**, **statistics** và index thích hợp giúp Oracle tối ưu chính xác hơn. Tuy nhiên, không thể kết luận chỉ đổi kiểu là mọi truy vấn sẽ nhanh: cần xem execution plan và số liệu I/O thực tế.

## 14. NULL, giá trị mặc định và ý nghĩa thiếu dữ liệu

`NULL` biểu thị **không có giá trị đã biết/được cung cấp**, khác với `0`, `FALSE`, chuỗi dấu cách hay một ngày mặc định.

Ví dụ:

- `discount_amount = 0`: đã xác định không giảm giá.
- `discount_amount IS NULL`: chưa có thông tin giảm giá, hoặc không áp dụng theo quy tắc hệ thống.
- `birth_date IS NULL`: không biết ngày sinh.
- `is_active = FALSE`: xác định là không hoạt động.
- `is_active IS NULL`: trạng thái chưa biết, nếu thiết kế cho phép.

Không đặt ngày mặc định `DATE '1900-01-01'` hoặc số `-1` làm mã “không biết” khi chúng có thể bị hiểu là giá trị hợp lệ. Nếu cần trạng thái “không áp dụng” khác “chưa biết”, có thể bổ sung cột trạng thái rõ ràng.

### DEFAULT không thay NOT NULL

Ví dụ:

```sql
quantity NUMBER(10,0) DEFAULT 0 NOT NULL
```

`DEFAULT 0` cung cấp giá trị khi ứng dụng bỏ qua cột trong INSERT (tùy cú pháp/configuration), còn `NOT NULL` cấm giá trị NULL. Nếu cần thay NULL tường minh bằng default trong một số tình huống, các phiên bản Oracle có cú pháp `DEFAULT ON NULL` thích hợp.

Với cột thời gian audit:

```sql
created_at TIMESTAMP(6) WITH TIME ZONE
    DEFAULT SYSTIMESTAMP NOT NULL
```

Cần xác định ứng dụng có được phép ghi đè thời điểm này hay nên để database/triggers quản lý hoàn toàn. Bài học về kiểu dữ liệu và quy tắc ghi không nên trộn lẫn.

### SQL ba giá trị logic

Ví dụ:

```sql
SELECT *
FROM app_orders
WHERE sales_channel <> 'WEB';
```

Nếu `sales_channel` nullable, các row `NULL` không tự được chọn bởi phép so sánh `<>`, vì kết quả điều kiện là UNKNOWN. Để bao gồm các row NULL cần mô tả rõ, ví dụ:

```sql
WHERE sales_channel <> 'WEB'
   OR sales_channel IS NULL
```

Thiết kế `NOT NULL` phù hợp có thể đơn giản hóa các truy vấn; không nên tự cấm NULL ở mọi cột khi miền nghiệp vụ có thông tin chưa biết hợp lệ.

## 15. Thiết kế kiểu dữ liệu với Java/JDBC

Ứng dụng Java cần ánh xạ giá trị Oracle sang kiểu Java thích hợp. Bảng dưới là định hướng phổ biến; chi tiết mapping còn tùy JDBC driver, Oracle version và quy ước timezone của ứng dụng.

| Oracle | Kiểu Java thường gặp | Điều cần chú ý |
|---|---|---|
| `NUMBER(p,s)` với phần thập phân | `BigDecimal` | Giữ exact decimal và chính sách scale |
| `NUMBER(p,0)` | `Integer`, `Long` hoặc `BigDecimal` tùy miền | NULL và overflow; NUMBER lớn có thể vượt long |
| `BINARY_DOUBLE` | `Double` | Chấp nhận sai số floating-point |
| `VARCHAR2` / `CHAR` | `String` | Unicode, padding CHAR, nullable |
| `DATE` | `java.sql.Timestamp`/`Date` hoặc mapping java.time phù hợp | Oracle DATE có giờ đến giây; đừng vô ý đánh mất time component |
| `TIMESTAMP` | `LocalDateTime` hoặc đối tượng JDBC tương ứng | Không có timezone |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` hoặc Oracle JDBC timezone API phù hợp | Cần kiểm tra hỗ trợ driver, offset/region semantics |
| `CLOB` | `Clob`, `Reader` hoặc `String` khi kích thước nhỏ | Streaming, memory, lifetime của connection |
| `BLOB` | `Blob`/`InputStream` | Streaming và giới hạn kích thước |
| `RAW(16)` | `byte[]`/mã hóa ID ứng dụng | Cẩn thận thứ tự byte và định dạng UUID |
| `BOOLEAN` SQL ở bản hỗ trợ | `Boolean` tùy JDBC driver | SQL BOOLEAN và PL/SQL BOOLEAN theo phiên bản |

Ví dụ dùng bind variable, không ghép string:

```java
String sql = """
    INSERT INTO app_orders (
        order_code, customer_id, total_amount,
        currency_code, sales_channel
    ) VALUES (?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "00001584");
    ps.setLong(2, 1003L);
    ps.setBigDecimal(3, new BigDecimal("153000.00"));
    ps.setString(4, "VND");
    ps.setString(5, "WEB");
    ps.executeUpdate();
}
```

**Vì sao dùng `PreparedStatement`?**

- Giá trị bind được truyền theo kiểu/định dạng phù hợp thay vì nối SQL.
- Tránh SQL injection khi truyền input.
- Giảm phụ thuộc cách Oracle hiểu chuỗi ngày/số theo NLS.
- Tăng khả năng reuse SQL cursor khi truy vấn tham số thay đổi.

Trong code mẫu dùng Java text block, cần Java phiên bản hỗ trợ tính năng đó; thay bằng chuỗi thông thường nếu môi trường cũ. `setBigDecimal` cùng `new BigDecimal("153000.00")` giữ giá trị decimal theo string.

### Ngày giờ trong JDBC

Một lỗi thực tế là ghi thời gian địa phương vào một `TIMESTAMP` không timezone, sau đó ứng dụng ở máy khác diễn giải theo timezone khác. Cần xác định **contract** cho mỗi cột:

- Cột này lưu **calendar date** hay **instant**?
- Giá trị đến từ database hay client?
- Giá trị được chuẩn hóa theo UTC hay lưu offset/timezone?
- Trình điều khiển và phiên làm việc Oracle dùng session timezone nào?
- API trả ISO-8601 kèm offset hay chỉ một chuỗi ngày giờ?

Việc trả lời các câu hỏi này quan trọng hơn việc “dùng TIMESTAMP vì tên có vẻ hiện đại hơn DATE”.

## 16. Chuyển kiểu tường minh và tránh phụ thuộc NLS

### 16.1. Date literal và TO_DATE

Không nên viết:

```sql
WHERE order_date = '14/11/2026'
```

Chuỗi này có thể được Oracle chuyển ngầm dựa vào `NLS_DATE_FORMAT` của session; chạy ở môi trường khác có thể lỗi hoặc hiểu sai.

Nên dùng:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Hoặc nếu đầu vào là chuỗi có định dạng rõ:

```sql
TO_DATE('14/11/2026', 'DD/MM/YYYY')
```

Với timestamp có timezone, dùng `TO_TIMESTAMP_TZ` và format mask thể hiện offset hoặc vùng. Trong ứng dụng JDBC, ưu tiên bind giá trị ngày giờ bằng API có kiểu phù hợp hơn là chuyển tất cả thành string.

### 16.2. TO_CHAR dùng để hiển thị

`TO_CHAR` hữu ích cho format đầu ra:

```sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'DD/MM/YYYY'
       ) AS formatted_date
FROM dual;
```

Tuy nhiên, `'14/11/2026'` là cách **hiển thị**, không phải kiểu lưu trữ ngày. Ngày được lưu trong cột `DATE` nên được filter, tính toán và sắp xếp như giá trị thời gian.

### 16.3. Chuỗi số và dấu phân cách thập phân

Trong môi trường có NLS khác nhau, giá trị chuỗi `'1,23'` có thể được hiểu khác về dấu thập phân/dấu phân tách nhóm. Để lưu kiểu NUMBER, ứng dụng nên dùng bind số hoặc chuyển tường minh với format/NLS phù hợp theo yêu cầu.

Ví dụ khái quát:

```sql
SELECT TO_NUMBER(
           '1234.56',
           '9999D99',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS parsed_amount
FROM dual;
```

Trong ví dụ, `D` là dấu thập phân theo cấu hình NLS chỉ định. Không lưu số tiền dưới dạng `'1.234,56'` rồi mong mọi client tự hiểu cùng một cách.

## 17. Kiểm tra kiểu dữ liệu hiện có trong schema Oracle

Có thể xem metadata cột bằng `USER_TAB_COLUMNS`:

```sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       char_used,
       char_length,
       data_precision,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name = 'APP_ORDERS'
ORDER BY column_id;
```

Các cột metadata cần biết:

- `DATA_TYPE`: kiểu dữ liệu Oracle, ví dụ NUMBER, VARCHAR2, TIMESTAMP WITH TIME ZONE.
- `DATA_LENGTH`: độ dài theo byte trong metadata.
- `CHAR_USED`: với cột ký tự thích hợp, `B` cho byte semantics, `C` cho char semantics.
- `CHAR_LENGTH`: độ dài ký tự khai báo của cột hỗ trợ semantics.
- `DATA_PRECISION` và `DATA_SCALE`: thông tin precision/scale với số.
- `NULLABLE`: có cho NULL theo metadata hay không.

Muốn đọc metadata schema khác khi có quyền:

```sql
SELECT owner, table_name, column_name, data_type
FROM all_tab_columns
WHERE owner = 'APP_SCHEMA'
  AND table_name = 'APP_ORDERS'
ORDER BY column_id;
```

`USER_TAB_COLUMNS` thường xem được đối tượng của schema hiện tại; `ALL_TAB_COLUMNS` hiển thị phạm vi đối tượng người dùng có quyền thấy. Tên đối tượng không đặt trong dấu nháy kép thường được Oracle chuẩn hóa uppercase trong data dictionary.

### Kiểm tra ràng buộc

```sql
SELECT constraint_name, constraint_type, status
FROM user_constraints
WHERE table_name = 'APP_ORDERS'
ORDER BY constraint_name;
```

Ví dụ loại constraint: `P` = primary key, `U` = unique, `C` = check (bao gồm nhiều NOT NULL constraints được phản ánh theo cấu trúc), `R` = foreign key. Muốn xem biểu thức CHECK chi tiết, cần tra metadata theo khả năng và kiểu cột trong phiên bản đang dùng.

### Hiểu statistics

Sau `DBMS_STATS`, các thống kê như `NUM_DISTINCT`, `NUM_NULLS` và histogram có thể hỗ trợ phân tích cách optimizer nhìn cột. Chúng không thay cho business domain: “cột hiện chỉ có ba trạng thái” không có nghĩa thiết kế được phép tự ý thêm trạng thái thứ tư, và “giá tiền hiện chỉ dưới một triệu” không có nghĩa miền NUMBER phải giới hạn ở một triệu.

## 18. Anti-pattern thiết kế và cách thay thế

### 18.1. Dùng VARCHAR2 cho ngày giờ

**Vấn đề:** Chuỗi `'31/12/2026'` khó tính khoảng thời gian, dễ phụ thuộc format, sắp xếp theo chuỗi có thể sai về thời gian.

**Thay thế:** `DATE`, `TIMESTAMP` hoặc `TIMESTAMP WITH TIME ZONE` theo ngữ nghĩa; dùng định dạng trong tầng hiển thị.

### 18.2. Dùng BINARY_DOUBLE cho tiền

**Vấn đề:** Biểu diễn gần đúng nhị phân có thể phát sinh sai số khi tính toán.

**Thay thế:** `NUMBER(p,s)` và `BigDecimal` phía Java; quy định scale/rounding rõ.

### 18.3. Dùng NUMBER cho mã có số 0 đầu

**Vấn đề:** `001234` trở thành `1234`, gây mất thông tin định danh.

**Thay thế:** `VARCHAR2` cùng constraint format/uniqueness.

### 18.4. Dùng CHAR quá dài cho tên hoặc mô tả

**Vấn đề:** Padding và kích thước cố định gây phiền phức so sánh/hiển thị.

**Thay thế:** `VARCHAR2(n CHAR)` cho text độ dài biến đổi.

### 18.5. Dùng CLOB cho trường thường xuyên join/sort

**Vấn đề:** CLOB không có khả năng B-tree index và so sánh thông thường như cột chuỗi nhỏ.

**Thay thế:** Đưa khóa/cột tra cứu ngắn ra `VARCHAR2`/NUMBER riêng; giữ CLOB cho nội dung lớn.

### 18.6. Dùng magic value thay NULL

**Vấn đề:** `-1`, `1900-01-01` hoặc `'UNKNOWN'` có thể bị xem là dữ liệu thật và làm sai thống kê/tính toán.

**Thay thế:** NULL khi dữ liệu thực sự chưa biết; trạng thái riêng hoặc bảng danh mục khi nghiệp vụ cần phân biệt nhiều tình huống.

### 18.7. Không có CHECK cho cột miền hẹp

**Vấn đề:** `status VARCHAR2(100)` cho phép nhập các giá trị sai như `'PADI'` mà database không chặn.

**Thay thế:**

```sql
status VARCHAR2(20 CHAR) NOT NULL
       CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
```

Với trạng thái thường xuyên được cập nhật hoặc có metadata riêng, dùng bảng tham chiếu và foreign key thay cho danh sách hard-code dài.

### 18.8. Lưu mọi thông tin trong JSON

**Vấn đề:** Thuộc tính quan hệ cốt lõi khó ràng buộc FK, khó tối ưu join/range query nếu chỉ nằm trong payload.

**Thay thế:** Cột quan hệ cho trường được truy vấn thường xuyên và JSON cho thông tin linh hoạt.

### 18.9. Chuyển kiểu ngầm ở điều kiện WHERE

**Vấn đề:** Sai NLS, lỗi chuyển đổi ở dữ liệu không hợp lệ, index sử dụng không như mong muốn.

**Thay thế:** Bind đúng kiểu và chuyển đổi tường minh một lần ở ranh giới nhập dữ liệu.

## 19. Quy trình chọn kiểu dữ liệu cho một cột mới

Khi thiết kế cột mới, có thể đi theo quy trình sau:

### Bước 1 — Viết một câu mô tả nghiệp vụ

Ví dụ: “`discount_rate` là tỷ lệ giảm giá từ 0 đến 1, cần tối đa bốn chữ số sau dấu thập phân”.

Câu này tốt hơn “discount_rate là một con số” vì chứa miền giá trị và độ chính xác.

### Bước 2 — Chọn nhóm kiểu theo bản chất

- Số chính xác → `NUMBER`.
- Số gần đúng → `BINARY_DOUBLE` khi hợp lý.
- Chuỗi → `VARCHAR2` hoặc `CHAR` khi thật sự cố định.
- Ngày/thời điểm/thời lượng → một trong các kiểu thời gian.
- Nội dung dài, bytes, JSON → kiểu phù hợp tính chất.

### Bước 3 — Định giới hạn chính xác

Ví dụ tỷ lệ từ 0 đến 1 với bốn chữ số phần lẻ:

```sql
discount_rate NUMBER(5,4) DEFAULT 0 NOT NULL
              CHECK (discount_rate BETWEEN 0 AND 1)
```

`NUMBER(5,4)` có một chữ số trước dấu và bốn chữ số phần lẻ, đủ cho giá trị `1.0000`. Nếu business định nghĩa phần trăm 0–100 thay vì tỷ lệ 0–1, cần một miền và precision khác; phải đặt tên/đơn vị rõ.

### Bước 4 — Chọn quy tắc NULL và default

Hỏi giá trị có bắt buộc không, và thiếu dữ liệu có khác `0`/`FALSE` không. Thêm `NOT NULL`, `DEFAULT` hoặc cột trạng thái theo nghĩa nghiệp vụ, không theo thói quen.

### Bước 5 — Xem cách truy vấn và index

- Thường lọc theo `customer_id` → kiểu ID nhất quán với bảng tham chiếu và có index phù hợp.
- Thường tìm theo ngày → DATE/TIMESTAMP đúng ngữ nghĩa, predicate khoảng và partitioning nếu phù hợp.
- Thường tìm chuỗi không phân biệt dấu/hoa → chiến lược collation/index.
- Thường tìm trong nội dung văn bản lớn → cân nhắc Oracle Text.
- Thường lọc JSON key → cân nhắc cột riêng hoặc JSON index.

### Bước 6 — Xác minh khả năng tích hợp

Kiểm tra mapping Java/JDBC, JSON serialization, giới hạn byte/Unicode, timezone, compatibility của bản Oracle triển khai và cách migrate schema khi dữ liệu đã tồn tại.

## 20. Bài thực hành tổng hợp

### Bài 1 — Chọn kiểu cho một bảng người dùng

Thiết kế các trường:

1. `user_id`: ID nội bộ tự sinh.
2. `display_name`: tên Unicode tối đa 120 ký tự.
3. `phone`: số điện thoại có thể bắt đầu `+84`.
4. `birth_date`: ngày sinh không có giờ nghiệp vụ.
5. `registered_at`: thời điểm đăng ký, lưu đúng timezone.
6. `active_flag`: chỉ có Y/N, hỗ trợ Oracle 19c.
7. `profile_description`: mô tả có thể dài hàng chục nghìn ký tự.

Gợi ý DDL:

```sql
CREATE TABLE lab_users (
    user_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name VARCHAR2(120 CHAR) NOT NULL,
    phone VARCHAR2(32 CHAR),
    birth_date DATE,
    registered_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    active_flag CHAR(1 CHAR) DEFAULT 'Y' NOT NULL,
    profile_description CLOB,
    CONSTRAINT ck_lab_users_active CHECK (active_flag IN ('Y', 'N'))
);
```

Thảo luận: có nên đặt `phone` là `UNIQUE` hay không? Câu trả lời phụ thuộc quy tắc số điện thoại được dùng lại, tài khoản gia đình, chuẩn hóa quốc tế và dữ liệu NULL, **không** thể quyết định từ riêng kiểu `VARCHAR2`.

### Bài 2 — Tìm lỗi trong thiết kế ban đầu

Giả sử có schema:

```sql
CREATE TABLE bad_orders (
    order_code NUMBER,
    price BINARY_DOUBLE,
    created_at VARCHAR2(30),
    customer_phone NUMBER,
    status VARCHAR2(4000)
);
```

Yêu cầu:

- Liệt kê ít nhất năm rủi ro.
- Đề xuất kiểu thay thế.
- Thêm ràng buộc để bảo vệ miền.
- Giải thích truy vấn theo ngày sẽ bị ảnh hưởng thế nào.
- Cho biết nên dùng kiểu Java nào cho giá tiền.

**Định hướng:** Mã đơn và điện thoại nên dùng VARCHAR2, price NUMBER(p,s), created_at kiểu thời gian, status VARCHAR2 vừa đủ cùng CHECK/FK; Java BigDecimal cho giá tiền.

### Bài 3 — Phân biệt kết quả NUMBER và BINARY_DOUBLE

Tạo bảng:

```sql
CREATE TABLE lab_math (
    id NUMBER PRIMARY KEY,
    exact_value NUMBER(12,2),
    float_value BINARY_DOUBLE
);

INSERT INTO lab_math VALUES (1, 0.10, 0.10);
INSERT INTO lab_math VALUES (2, 0.20, 0.20);
COMMIT;

SELECT SUM(exact_value) AS exact_total,
       SUM(float_value) AS approximate_total
FROM lab_math;
```

Giải thích vì sao không nên suy ra một thuật toán tiền tệ có thể dùng floating-point chỉ vì kết quả hiển thị được làm tròn thành `0.3`. Cần phân biệt **giá trị nội bộ gần đúng** với **định dạng hiển thị**.

### Bài 4 — Chọn kiểu thời gian và truy vấn đủ một ngày

Có bảng:

```sql
CREATE TABLE lab_visits (
    visit_id NUMBER PRIMARY KEY,
    visited_at DATE NOT NULL
);

INSERT INTO lab_visits VALUES (
    1,
    TO_DATE('14/11/2026 08:15:00', 'DD/MM/YYYY HH24:MI:SS')
);

INSERT INTO lab_visits VALUES (
    2,
    TO_DATE('14/11/2026 23:59:59', 'DD/MM/YYYY HH24:MI:SS')
);

COMMIT;
```

Viết truy vấn lấy đủ mọi `VISITED_AT` trong ngày 14/11/2026, không bỏ sót các hàng có giờ khác 00:00:00:

```sql
SELECT *
FROM lab_visits
WHERE visited_at >= DATE '2026-11-14'
  AND visited_at <  DATE '2026-11-15';
```

Thảo luận: nếu dữ liệu là timestamp với timezone và khách hàng ở nhiều khu vực, cần biết múi giờ nào định nghĩa khái niệm “trong ngày”.

### Bài 5 — Đọc metadata thay vì đoán

Tạo bảng mẫu với NUMBER, VARCHAR2 CHAR semantics và TIMESTAMP. Dùng:

```sql
SELECT column_name, data_type,
       data_precision, data_scale,
       data_length, char_used, char_length
FROM user_tab_columns
WHERE table_name = 'LAB_USERS'
ORDER BY column_id;
```

Yêu cầu giải thích vì sao `DATA_LENGTH` và `CHAR_LENGTH` không phải lúc nào cũng giống nhau, và tại sao `DATA_PRECISION/DATA_SCALE` cần xem khi đọc kiểu NUMBER.

### Bài 6 — Chọn kiểu cho dữ liệu cảm biến

Hệ thống nhận:

- `sensor_code` dạng `"0008-A"`.
- `measured_at` là thời điểm đo chính xác đến mili giây, máy nằm ở nhiều quốc gia.
- `temperature_c` có thể âm và có sai số đo.
- `battery_pct` là số từ 0 đến 100, cần một chữ số sau dấu.
- `raw_packet` là bytes gốc của thiết bị.

Hướng đề xuất:

| Cột | Kiểu khả thi |
|---|---|
| `sensor_code` | `VARCHAR2(32 CHAR)` |
| `measured_at` | `TIMESTAMP(3) WITH TIME ZONE` |
| `temperature_c` | `BINARY_DOUBLE` hoặc `NUMBER(p,s)` theo đặc tính phép đo |
| `battery_pct` | `NUMBER(4,1) CHECK (battery_pct BETWEEN 0 AND 100)` |
| `raw_packet` | `BLOB` hoặc `RAW(n)` nếu packet có giới hạn nhỏ, cố định |

Câu hỏi: vì sao cần kiểm soát miền đo của `temperature_c` bằng logic/constraint thích hợp ngay cả khi kiểu số đã biểu diễn được số âm?

## 21. Sơ đồ quyết định chọn kiểu dữ liệu

```text
Giá trị cần lưu là gì?
|
+-- Đại lượng số cần tính toán?
|      |
|      +-- Cần chính xác thập phân (tiền, số đếm)?
|      |      └── NUMBER(p,s), constraint miền giá trị
|      |
|      +-- Chấp nhận sai số floating-point?
|             └── BINARY_DOUBLE / BINARY_FLOAT
|
+-- Chuỗi ký tự hoặc mã định danh?
|      |
|      +-- Độ dài thay đổi, Unicode?
|      |      └── VARCHAR2(n CHAR), charset/collation phù hợp
|      |
|      +-- Độ dài cố định theo chuẩn?
|      |      └── CHAR(n CHAR) khi padding phù hợp
|      |
|      +-- Văn bản dài?
|             └── CLOB
|
+-- Thời gian?
|      |
|      +-- Ngày lịch / đến giây, không cần timezone?
|      |      └── DATE (quy ước rõ phần giờ)
|      |
|      +-- Cần phần giây, không cần timezone?
|      |      └── TIMESTAMP(p)
|      |
|      +-- Cần instant/timezone rõ?
|      |      └── TIMESTAMP WITH TIME ZONE
|      |
|      +-- Muốn hiển thị theo timezone session?
|      |      └── TIMESTAMP WITH LOCAL TIME ZONE
|      |
|      +-- Là khoảng thời gian?
|             └── INTERVAL hoặc NUMBER kèm đơn vị
|
+-- Dữ liệu nhị phân?
|      |
|      +-- Nhỏ/cố định (UUID)?
|      |      └── RAW(n)
|      |
|      +-- Tệp/bytes lớn?
|             └── BLOB
|
+-- Dữ liệu có cấu trúc linh hoạt?
|      |
|      +-- JSON: JSON native hoặc CLOB/VARCHAR2/BLOB + IS JSON
|      +-- XML: XMLTYPE khi phù hợp
|
+-- Giá trị đúng/sai?
       └── BOOLEAN SQL ở bản hỗ trợ,
           hoặc CHAR(1)/NUMBER(1) với CHECK
```

Sau khi chọn nhóm kiểu, **vẫn phải** kiểm tra: có cần `NOT NULL` không, miền giá trị/precision/scale đủ chưa, index/join có hợp lý không, byte/Unicode/timezone có được hiểu thống nhất không, và ứng dụng Java/JDBC có truyền đúng kiểu hay không.

---

## 22. Ghi nhớ khi thiết kế bảng Oracle

Một cột Oracle tốt thể hiện được ý nghĩa của dữ liệu và giúp database bảo vệ quy tắc nghiệp vụ:

- **Tiền, số lượng, tỷ lệ thập phân:** dùng `NUMBER` với precision/scale theo miền giá trị; tiền cần quy tắc làm tròn và currency.
- **Số đo gần đúng:** cân nhắc `BINARY_DOUBLE` và đặc tính sai số của phép tính.
- **Mã định danh chứa chữ/số 0 đầu:** dùng chuỗi; không ép NUMBER chỉ vì có chữ số.
- **Text Unicode:** thiết kế `VARCHAR2(n CHAR)` và charset phù hợp; phân biệt byte limit với character limit.
- **Ngày và thời điểm:** phân biệt ngày lịch, timestamp không timezone, instant có timezone và duration.
- **Văn bản/bytes lớn:** dùng `CLOB`/`BLOB` hoặc giải pháp storage phù hợp; không ép vào cột nhỏ.
- **Cờ/JSON/kiểu chuyên biệt:** đối chiếu phiên bản SQL và cách ứng dụng truy vấn.
- **Hiệu năng truy vấn:** tránh implicit conversion, chọn bind variable đúng kiểu, kiểm tra index/partition và execution plan trên workload thật.

### Tài liệu tham khảo Oracle

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — mục **Data Types**, **Datetime and Interval Data Types**, **SQL Conditions**, **CREATE TABLE**.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — dữ liệu ký tự, encoding, độ chính xác số, storage và schema objects.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/) — `AL32UTF8`, byte/character semantics, collation và NLS.
- [Oracle Database JSON Developer's Guide](https://docs.oracle.com/en/database/) — kiểu JSON theo phiên bản và truy vấn `JSON_VALUE`/`JSON_TABLE`.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/) — ánh xạ kiểu Oracle/Java, binding, LOB và datetime.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — predicate, implicit conversion, index và optimizer.

Tên kiểu, giới hạn, khả năng SQL `BOOLEAN`/`JSON` và hành vi chuyển đổi thời gian có thể phụ thuộc **phiên bản Oracle, cấu hình database, client driver và phiên làm việc**. Khi thiết kế một schema cần vận hành trên nhiều phiên bản, phải lấy phiên bản cũ nhất trong phạm vi hỗ trợ làm căn cứ tương thích.

