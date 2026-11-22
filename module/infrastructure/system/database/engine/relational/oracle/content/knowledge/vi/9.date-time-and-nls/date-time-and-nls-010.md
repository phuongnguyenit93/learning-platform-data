# NLS_NUMERIC_CHARACTERS, NLS_SORT và NLS_COMP khi xử lý dữ liệu Oracle

Khi một hệ thống Oracle phục vụ người dùng từ nhiều quốc gia, **cùng một giá trị số có thể được viết thành những chuỗi khác nhau** và **cùng một danh sách tên có thể được sắp xếp hoặc so sánh theo những quy tắc khác nhau**. Ví dụ, chuỗi `1.234,56` thường được hiểu là một nghìn hai trăm ba mươi tư phẩy năm sáu trong một số quy ước, còn `1,234.56` thể hiện cùng giá trị trong quy ước khác. Tương tự, `Lan`, `lan` và `Lân` có thể được xem là khác nhau hay tương đương ở một số thao tác tra cứu tùy quy tắc so sánh.

Oracle Database có hệ thống **National Language Support (NLS)** để điều khiển những khác biệt này. Trong nhóm NLS, ba tham số quan trọng là:

- **`NLS_NUMERIC_CHARACTERS`:** định nghĩa ký tự ngăn phần thập phân và ký tự phân nhóm hàng nghìn khi *chuyển đổi/định dạng số thành chuỗi*.
- **`NLS_SORT`:** chọn quy tắc sắp xếp/ngôn ngữ (collation), ví dụ so sánh theo mã nhị phân hay không phân biệt chữ hoa/chữ thường.
- **`NLS_COMP`:** điều khiển vai trò của các quy tắc so sánh ngôn ngữ trong các điều kiện so sánh SQL; đặc biệt quan trọng khi kết hợp với `NLS_SORT`.

Ba tham số này **không biến một cột NUMBER thành VARCHAR2**, không sửa lại dữ liệu đã lưu mỗi khi phiên đổi NLS, và không đồng nghĩa với mã hóa ký tự của database. Chúng ảnh hưởng đến việc **biểu diễn, phân tích chuỗi và so sánh** ở những ngữ cảnh cụ thể.

Sau bài học, bạn có thể:

1. Đọc giá trị NLS hiện hành của session và phân biệt session với cấu hình mặc định của instance.
2. Chuyển `VARCHAR2` thành `NUMBER` bằng `TO_NUMBER` và số thành văn bản bằng `TO_CHAR` với quy ước dấu thập phân/dấu nhóm được chỉ rõ.
3. Giải thích vì sao SQL numeric literal `1234.56` khác chuỗi ký tự `'1.234,56'`.
4. Phân biệt sắp xếp theo `NLS_SORT` với điều kiện tìm kiếm bằng `=`, `LIKE` và các predicate chịu ảnh hưởng bởi `NLS_COMP`.
5. Chọn kiểu so sánh phân biệt hoặc không phân biệt hoa/thường, dấu; nhận biết tác động tới tìm kiếm, sorting, uniqueness và index.
6. Viết truy vấn và ứng dụng ổn định hơn trước thay đổi NLS của người dùng, client hay connection pool.

> Ghi chú phiên bản: Oracle Database từ 12.2 trở đi hỗ trợ các cơ chế **data-bound collations** và biểu thức `COLLATE` trong những điều kiện thích hợp. Cấu hình collation trực tiếp trên cột/biểu thức có thể có độ ưu tiên khác với các tham số session. Bài học giới thiệu trước mô hình NLS session truyền thống, sau đó nêu điểm cần kiểm tra trên database có collation khai báo riêng. Không nên suy luận rằng mọi object trên mọi phiên bản đều hoàn toàn do `NLS_SORT` và `NLS_COMP` của session quyết định.

## 1. Bức tranh tổng thể của NLS trong Oracle

NLS gồm nhiều nhóm thiết lập, chẳng hạn:

| Nhóm | Ví dụ tham số | Chịu trách nhiệm chính |
| --- | --- | --- |
| Định dạng số | `NLS_NUMERIC_CHARACTERS` | Dấu thập phân và dấu phân nhóm trong biểu diễn số |
| Ngôn ngữ/định dạng ngày | `NLS_DATE_LANGUAGE`, `NLS_DATE_FORMAT` | Tên tháng/ngày, định dạng mặc định khi chuyển ngày sang chuỗi |
| Lãnh thổ | `NLS_TERRITORY` | Một số mặc định liên quan định dạng theo vùng |
| Sắp xếp ngôn ngữ | `NLS_SORT` | Quy tắc collation trong những phép sắp xếp/so sánh thích hợp |
| Chế độ so sánh | `NLS_COMP` | Binary so với linguistic comparisons ở những ngữ cảnh có áp dụng |
| Ngôn ngữ thông báo | `NLS_LANGUAGE` | Nhiều thiết lập ngôn ngữ mặc định và thông báo |

Ba tham số của bài học có liên hệ với nhau nhưng **không thay thế lẫn nhau**:

```text
                  Oracle SQL session
                          │
             ┌────────────┴─────────────┐
             │                          │
       DỮ LIỆU SỐ                   DỮ LIỆU CHỮ
             │                          │
             ▼                          ▼
 NLS_NUMERIC_CHARACTERS         NLS_SORT
  - Decimal separator           - Binary / linguistic
  - Group separator             - Case/accent sensitivity
             │                          │
             ▼                          ▼
  TO_NUMBER / TO_CHAR            ORDER BY / NLSSORT
  (và implicit conversion)              │
                                        ▼
                                     NLS_COMP
                               - Điều kiện so sánh
                               - Binary / linguistic
```

### 1.1. NLS có nhiều cấp thiết lập

Một giá trị NLS có thể có **mặc định** từ cấu hình database/instance, nhưng session do client tạo có thể mang giá trị khác. Driver, SQL client và connection pool cũng có khả năng cấu hình hoặc thay đổi trạng thái NLS của phiên.

Để xem **giá trị session hiện tại**, dùng:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Ví dụ kết quả:

```text
NLS_COMP                BINARY
NLS_NUMERIC_CHARACTERS  .,
NLS_SORT                BINARY
```

Đây là **ví dụ**, không phải các giá trị bắt buộc. Giá trị thật do truy vấn trả về mới là trạng thái của session bạn đang dùng.

Một số view liên quan:

- `NLS_SESSION_PARAMETERS`: các giá trị mà session đang sử dụng.
- `NLS_INSTANCE_PARAMETERS`: các giá trị NLS ở cấp instance theo view tương ứng.
- `NLS_DATABASE_PARAMETERS`: thông tin tham số NLS của database.

Đừng dùng kết quả view database làm bằng chứng rằng một **connection cụ thể** đang có cùng giá trị. Khi có sự khác biệt khó giải thích, cần xem đúng session và nguồn tạo kết nối.

### 1.2. Thay đổi session để thực hành

`ALTER SESSION` thay đổi thiết lập của **phiên hiện tại**, không yêu cầu cập nhật dữ liệu hoặc thay đổi cấu hình mặc định của toàn bộ database:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;
```

Một phiên khác trong cùng database có thể giữ NLS khác. Khi dùng **connection pool**, phiên vật lý được tái sử dụng: nếu một request thay đổi NLS rồi trả kết nối về pool mà không phục hồi giá trị, request kế tiếp có thể chịu hiệu ứng ngoài ý muốn. Vì vậy, nếu ứng dụng cần session NLS cố định, phải thiết kế cách **khởi tạo và reset trạng thái connection** rõ ràng.

## 2. NLS_NUMERIC_CHARACTERS: phân biệt dấu thập phân và dấu nhóm

Giá trị của `NLS_NUMERIC_CHARACTERS` gồm **hai ký tự theo thứ tự**:

1. Ký tự thứ nhất: **decimal character** (dấu phân cách phần thập phân).
2. Ký tự thứ hai: **group separator** (dấu phân nhóm chữ số, ví dụ hàng nghìn).

Hai ký tự phải khác nhau và đáp ứng những giới hạn Oracle quy định cho bộ ký tự phân cách. Trong thực tế thường dùng:

| Giá trị tham số | Dấu thập phân | Dấu nhóm | Chuỗi số minh họa |
| --- | --- | --- | --- |
| `'.,'` | `.` | `,` | `1,234.56` |
| `',.'` | `,` | `.` | `1.234,56` |

**Thứ tự là quan trọng.** `'.,'` không có cùng ý nghĩa với `',.'`. Không được chọn hai ký tự giống nhau vì Oracle sẽ không thể phân biệt vai trò.

### 2.1. Tác động khi TO_CHAR với format model D và G

Trong format model số của Oracle:

- `D` là vị trí **dấu thập phân theo NLS**.
- `G` là vị trí **dấu nhóm theo NLS**.
- Các ký hiệu `9` và `0` điều khiển vị trí chữ số theo quy tắc format model.
- `FM` thường được dùng để bỏ khoảng trắng padding trong kết quả định dạng.

Ví dụ định dạng cùng một số theo hai quy ước mà **không cần đổi session**:

```sql
SELECT
    TO_CHAR(
        1234.56,
        'FM9G999D00',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
    ) AS format_dot_decimal,
    TO_CHAR(
        1234.56,
        'FM9G999D00',
        'NLS_NUMERIC_CHARACTERS = '',.'''
    ) AS format_comma_decimal
FROM dual;
```

Kết quả dự kiến:

```text
FORMAT_DOT_DECIMAL   FORMAT_COMMA_DECIMAL
------------------   --------------------
1,234.56             1.234,56
```

Tham số thứ ba của `TO_CHAR` ở đây là một **nlsparam string**. Chuỗi SQL `'NLS_NUMERIC_CHARACTERS = '',.'''` chứa các dấu nháy đơn được escape bằng cách viết hai dấu `''` trong một SQL string literal. Nó yêu cầu decimal comma, group dot. Vì quy tắc nằm ngay trong biểu thức, kết quả ít lệ thuộc NLS session hơn.

### 2.2. TO_NUMBER phân tích chuỗi theo dấu tương ứng

Ngược lại, khi dữ liệu đầu vào là **chuỗi**, có thể dùng `TO_NUMBER` với format model cụ thể:

```sql
SELECT
    TO_NUMBER(
        '1,234.56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
    ) AS number_from_us_style,
    TO_NUMBER(
        '1.234,56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS = '',.'''
    ) AS number_from_comma_style
FROM dual;
```

Hai biểu thức trả về giá trị kiểu `NUMBER` bằng **1234.56**. Số đã được chuyển thành `NUMBER` không còn mang theo “dấu phẩy thập phân” hay “dấu chấm thập phân” như thuộc tính lưu trữ. Dấu nào được dùng để hiển thị lại sẽ phụ thuộc format/NLS khi chuyển **NUMBER → text**.

### 2.3. Nếu chỉ thay session thì sao?

Bạn có thể thực hành bằng:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT
    TO_NUMBER('1.234,56', '9G999D99') AS amount,
    TO_CHAR(1234.56, 'FM9G999D00') AS amount_as_text
FROM dual;
```

Trong session có dấu thập phân `,` và dấu nhóm `.`, kết quả text theo format trên là `1.234,56`. Nhưng nếu câu lệnh này được chạy ở một session khác có `NLS_NUMERIC_CHARACTERS='.,'`, chuỗi đầu vào có thể không được diễn giải như ý định, và có thể gặp lỗi chuyển đổi tùy format/đầu vào.

**Khuyến nghị:** đối với tệp dữ liệu, API hoặc giao tiếp giữa các hệ thống, hãy định nghĩa **một định dạng chuẩn** và chuyển đổi có format rõ ràng ở ranh giới nhập/xuất. Không yêu cầu database tự đoán vùng miền từ chuỗi như `1,234`, vì chuỗi đó có thể được hiểu là một nghìn hai trăm ba mươi tư hoặc một phẩy hai ba bốn tùy quy ước.

### 2.4. Numeric literal SQL không phải chuỗi locale

Trong cú pháp SQL Oracle, một **numeric literal** được viết với **dấu chấm** làm dấu thập phân:

```sql
SELECT 1234.56 AS amount
FROM dual;
```

Việc chạy:

```sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
```

**không đổi quy tắc viết numeric literal trong văn bản SQL** thành `1234,56`. Dấu phẩy trong cú pháp SQL còn dùng để phân tách biểu thức; ví dụ `SELECT 1, 5 FROM dual` là truy vấn gồm hai biểu thức, không phải một numeric literal 1,5.

Phân biệt:

| Ví dụ | Bản chất |
| --- | --- |
| `1234.56` trong SQL | Numeric literal, cú pháp SQL |
| `'1234.56'` | Chuỗi ký tự, có thể được chuyển sang số |
| `'1.234,56'` | Chuỗi ký tự có dấu nhóm/thập phân theo một quy ước |
| `:amount` được bind là NUMBER | Giá trị số đã có kiểu, không cần parse dấu phân cách từ văn bản |

Không bao giờ nối văn bản số do người dùng nhập vào SQL để biến nó thành numeric literal. Hãy dùng bind parameter đúng kiểu hoặc parse/validate ở ranh giới nhập liệu rồi bind kiểu NUMBER.

### 2.5. Chuyển kiểu ngầm dễ tạo lỗi khó phát hiện

Ví dụ tưởng vô hại:

```sql
SELECT *
FROM invoices
WHERE total_amount = '1,25';
```

Giả sử `TOTAL_AMOUNT` có kiểu NUMBER. Vì bên phải là chuỗi, Oracle phải áp dụng quy tắc chuyển kiểu ngầm thích hợp. Ở session này `'1,25'` có thể được diễn giải theo dấu phẩy thập phân, ở session khác có thể gây lỗi hoặc mang ý nghĩa khác.

Viết rõ hơn:

```sql
SELECT *
FROM invoices
WHERE total_amount = 1.25;
```

Trong ứng dụng Java/JDBC, nên dùng bind NUMBER:

```java
String sql = "SELECT invoice_id FROM invoices WHERE total_amount = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new java.math.BigDecimal("1.25"));
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý invoice_id.
        }
    }
}
```

Mã Java dùng chuỗi `"1.25"` **chỉ để khởi tạo BigDecimal trong Java**, sau đó gửi giá trị số qua JDBC. Nó không gửi chuỗi locale rồi mong Oracle chuyển kiểu. Nếu giá trị gốc được nhập từ người dùng với dấu phẩy thập phân, ứng dụng phải parse theo locale được xác nhận trước khi tạo BigDecimal, không loại dấu phẩy/dấu chấm một cách máy móc.

### 2.6. Định dạng số cho CSV và báo cáo

Một lỗi thực tế là ghép CSV dùng dấu phẩy làm delimiter với các chuỗi số `1,234.56` chứa dấu phẩy. Nếu không quote/escape field theo chuẩn CSV, hệ thống nhận sẽ coi đó là nhiều cột.

Khi xuất file hoặc JSON:

- Giữ dữ liệu NUMBER ở kiểu số cho các API hỗ trợ giá trị số có kiểu.
- Nếu bắt buộc xuất text, thống nhất format và mã hóa text.
- Với CSV, thực hiện **quote/escape** đúng chuẩn, không chỉ thay dấu phân cách thập phân.
- Khi import, xác định rõ cột, locale, format model, encoding và chính sách xử lý dữ liệu sai.
- Tránh phụ thuộc `ALTER SESSION` của một job khác có thể làm thay đổi cách chuyển đổi ngầm.

## 3. NLS_SORT: quy tắc sắp xếp chuỗi

`NLS_SORT` xác định thứ tự so sánh/sắp xếp dạng **binary** hoặc **linguistic** trong những hoạt động mà Oracle áp dụng collation theo session.

Một số giá trị phổ biến:

| Giá trị | Mục đích khái quát | Ví dụ ảnh hưởng |
| --- | --- | --- |
| `BINARY` | Dựa trên quy tắc thứ tự nhị phân/mã ký tự theo cơ chế Oracle | Hoa/thường, dấu có thể xếp theo thứ tự khác kỳ vọng ngôn ngữ |
| `BINARY_CI` | Binary-style collation **case-insensitive** | `Lan` và `lan` có thể cùng thứ tự/so khớp khi thao tác sử dụng collation |
| `BINARY_AI` | Binary-style collation **accent-insensitive**, thường đồng thời case-insensitive | `Lan`, `Lân` và `lan` có thể được coi tương đương trong so sánh chịu collation |
| Một linguistic sort theo ngôn ngữ | Quy tắc sắp xếp phù hợp ngôn ngữ cụ thể | Xếp từ/tên theo kỳ vọng người dùng của vùng/ngôn ngữ đó |

**`BINARY_CI` không giống `BINARY_AI`.** `CI` là *case-insensitive*; `AI` là *accent-insensitive* (và thông thường không phân biệt case). Không nên lựa chọn `AI` cho một hệ thống nơi dấu tiếng Việt phân biệt từ ngữ hay danh tính nghiệp vụ; bỏ dấu có thể làm những dữ liệu khác ý nghĩa bị coi tương đương trong truy vấn.

Các sort names và phiên bản collation được hỗ trợ thay đổi theo Oracle version/edition/character set. Với dữ liệu tiếng Việt, cần kiểm tra **một linguistic collation phù hợp** và thử các chuỗi có dấu thực tế, không mặc định `BINARY_AI` tương đương thứ tự từ điển tiếng Việt.

### 3.1. Vì sao thứ tự binary khác thứ tự từ điển?

Một thứ tự binary thường dựa trên cách mã hóa/so sánh ký tự, còn từ điển một ngôn ngữ có thể áp dụng quy tắc riêng cho chữ hoa, chữ thường, ký tự có dấu và những tổ hợp ký tự. Ví dụ dữ liệu gồm:

```text
Lan
lan
Lân
Anh
Ánh
Minh
```

Không nên dự đoán chính xác vị trí của từng chuỗi trong mọi collation chỉ bằng mắt. Thay vào đó, hãy chỉ rõ collation dùng cho truy vấn và quan sát thứ tự trên database/phiên bản thật.

### 3.2. Sắp xếp theo NLS_SORT của session

Trong mô hình session NLS thông thường:

```sql
ALTER SESSION SET NLS_SORT = BINARY;

SELECT full_name
FROM lab_nls_people
ORDER BY full_name;
```

Sau đó:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;

SELECT full_name
FROM lab_nls_people
ORDER BY full_name;
```

Quy tắc sorting được áp dụng cho biểu thức tùy loại collation hiệu lực. Trên cơ sở dữ liệu hiện đại có **explicit collation** hay **data-bound collation** của cột, việc đặt `NLS_SORT` trong session có thể không chi phối mọi biểu thức như trong mô hình cũ.

Đừng coi các chuỗi tương đương theo collation là có thứ tự ổn định: nếu `Lan` và `lan` có cùng khóa sắp xếp, database có thể trả chúng theo thứ tự khác nhau giữa các lần chạy. Với ứng dụng phân trang, luôn bổ sung một **tie-breaker** ổn định:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY full_name, id;
```

### 3.3. NLSSORT: chọn quy tắc ngay trong biểu thức

Hàm `NLSSORT` tạo **linguistic sort key** (kiểu RAW) theo collation được chỉ định:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id;
```

Ưu điểm: biểu thức có chỉ rõ quy tắc `BINARY_CI` và không phải chỉ dựa vào giá trị `NLS_SORT` ở session. Phần `, id` làm thứ tự ổn định khi hai tên cùng khóa case-insensitive. Khi ứng dụng cần quy tắc khác, ví dụ accent-sensitive hoặc linguistic sort theo ngôn ngữ, chọn collation thích hợp và ghi nhận trong yêu cầu.

`NLSSORT` trả sort key, **không trả lại bản text đã thay đổi**. Dữ liệu lưu trong cột `FULL_NAME` vẫn giữ chữ hoa/chữ thường/dấu theo giá trị ban đầu.

## 4. NLS_COMP: khi nào so sánh SQL dùng quy tắc linguistic?

Đây là phần gây nhầm lẫn nhất. **`NLS_SORT` và `NLS_COMP` phải được xét cùng nhau** khi nói về so sánh `=`, `<`, `>`, `LIKE` và các điều kiện có collation trong mô hình NLS session truyền thống.

### 4.1. NLS_COMP = BINARY

Khi `NLS_COMP=BINARY`, những phép so sánh ký tự thông thường theo mô hình session cổ điển dùng ngữ nghĩa binary, kể cả khi session `NLS_SORT` được đặt là `BINARY_CI`:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan';
```

Với những cột sử dụng collation theo session truyền thống và dữ liệu ví dụ, điều kiện `= 'Lan'` phân biệt chữ hoa/chữ thường. Đó là lý do **đổi mỗi `NLS_SORT` không nhất thiết làm điều kiện WHERE trở thành case-insensitive**.

### 4.2. NLS_COMP = LINGUISTIC

Khi `NLS_COMP=LINGUISTIC`, Oracle có thể dùng `NLS_SORT` để thực hiện linguistic comparisons trong những điều kiện SQL thuộc phạm vi hỗ trợ:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Trong ví dụ dữ liệu `Lan` và `lan`, hai hàng có thể được coi bằng nhau dưới `BINARY_CI`; `Lân` vẫn khác nếu collation đang dùng phân biệt dấu.

Nếu chuyển sang `BINARY_AI`:

```sql
ALTER SESSION SET NLS_SORT = BINARY_AI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Trong phép so sánh chịu `BINARY_AI`, những tên chỉ khác case/dấu như `Lan`, `lan`, `Lân` có thể được xem tương đương. Đây là **lựa chọn nghiệp vụ**, không phải “cải tiến luôn đúng”: với tiếng Việt, dấu có thể phân biệt những từ/định danh hoàn toàn khác nhau.

### 4.3. Bảng phối hợp NLS_SORT và NLS_COMP

| NLS_SORT | NLS_COMP | Tác động mong đợi trong session-style comparison |
| --- | --- | --- |
| `BINARY` | `BINARY` | Sắp xếp và so sánh theo quy tắc binary cơ bản |
| `BINARY_CI` | `BINARY` | Sắp xếp theo case-insensitive khi biểu thức dùng NLS sort; `WHERE col='x'` có thể vẫn binary |
| `BINARY_CI` | `LINGUISTIC` | So sánh áp dụng collation theo session có thể không phân biệt chữ hoa/thường |
| `BINARY_AI` | `LINGUISTIC` | So sánh có thể không phân biệt chữ hoa/thường và dấu |
| Linguistic sort khác | `LINGUISTIC` | So sánh theo quy tắc ngôn ngữ được chọn khi có hiệu lực |

Phải đọc bảng với điều kiện: **cột/biểu thức không có quy tắc collation khác ưu tiên cao hơn**. Trên Oracle 12.2+, explicit collation, declared collation và collation derivation có thể thay đổi kết quả thực tế.

### 4.4. NLS_COMP không đơn giản chỉ là một công tắc đổi chữ hoa/thường

`NLS_COMP` tác động đến cách các điều kiện thích hợp được so sánh theo luật collation. `NLS_SORT` xác định luật đó. Chẳng hạn:

- `BINARY` với `NLS_COMP=LINGUISTIC` vẫn không mặc nhiên trở thành case-insensitive.
- `BINARY_CI` với `NLS_COMP=BINARY` không mặc nhiên đổi mọi `WHERE name='lan'` sang case-insensitive.
- `BINARY_AI` có thể làm những chuỗi khác dấu được xem như cùng khóa so sánh. Điều đó có thể ảnh hưởng hành vi tìm kiếm và kết quả nghiệp vụ.

Các phép toán phức tạp hơn như `LIKE`, `BETWEEN`, `IN`, pattern matching và các quy tắc nhóm/sắp xếp cần được kiểm chứng trên phiên bản và **collation thực tế của biểu thức**, không chỉ nhìn hai tham số rồi áp một phép biến đổi chung cho mọi SQL.

## 5. Ví dụ thực hành: so sánh tên với chữ hoa và dấu

Thực hành trong schema riêng, ví dụ `LAB_USER`, tránh tạo bảng cùng tên với object đang được sử dụng. Bạn có thể chọn một tên bảng khác nếu cần.

### 5.1. Tạo dữ liệu mẫu

```sql
CREATE TABLE lab_nls_people (
    id        NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL
);

INSERT INTO lab_nls_people VALUES (1, 'Lan');
INSERT INTO lab_nls_people VALUES (2, 'lan');
INSERT INTO lab_nls_people VALUES (3, 'Lân');
INSERT INTO lab_nls_people VALUES (4, 'Anh');
INSERT INTO lab_nls_people VALUES (5, 'Ánh');
INSERT INTO lab_nls_people VALUES (6, 'Minh');

COMMIT;
```

Mục đích chỉ là minh họa case/accents. Các kết quả phụ thuộc **collation của cột `FULL_NAME`**, database và session. Nếu database của bạn khai báo collation trực tiếp trên cột khác với luật session, các kết luận về `WHERE` bên dưới cần được kiểm tra theo collation hiệu lực.

### 5.2. Đọc trạng thái session ban đầu

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN ('NLS_SORT', 'NLS_COMP')
ORDER BY parameter;
```

Ghi lại hai giá trị để phục hồi sau khi thử nghiệm.

### 5.3. Thử tìm kiếm binary

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Với dữ liệu được lưu và cột mặc định dùng so sánh binary theo session truyền thống, chỉ tên khớp đúng `Lan` được chọn.

### 5.4. Thử linguistic, case-insensitive

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Trong trường hợp collation chịu NLS session, `Lan` và `lan` được chọn, còn `Lân` không nhất thiết được chọn vì khác dấu.

### 5.5. Thử linguistic, accent-insensitive

```sql
ALTER SESSION SET NLS_SORT = BINARY_AI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Bạn có thể quan sát thêm những tên khác dấu trong kết quả. Với dữ liệu nhạy cảm về tên riêng, khóa nhận dạng hoặc từ tiếng Việt, cần cân nhắc liệu phép so sánh **bỏ dấu** là mong muốn hay không.

### 5.6. Cố định phép sắp xếp trong từng truy vấn

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id;
```

Sau đó thử:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_AI'),
    id;
```

So sánh vị trí các tên. Kết quả có thể khác nhau do những chữ có dấu được quy đổi vào cùng nhóm đối với `BINARY_AI`; `ID` quyết định thứ tự khi các tên có cùng sort key.

### 5.7. Phục hồi session

Trong môi trường thực hành, nếu bạn muốn quay lại giá trị cơ bản để không ảnh hưởng bài khác:

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
```

Ba giá trị trên là **ví dụ giá trị cơ bản**, **không được xem là khôi phục chính xác trạng thái ban đầu** nếu session ban đầu của bạn dùng quy ước khác. Nếu muốn phục hồi thực sự, dùng những giá trị đã ghi ở bước 5.2 và `NLS_NUMERIC_CHARACTERS` ban đầu hoặc tạo một session mới theo chính sách khởi tạo của ứng dụng.

## 6. Sắp xếp, tìm kiếm và tính duy nhất là ba bài toán khác nhau

Ba yêu cầu nghiệp vụ sau thường bị trộn lẫn:

1. **Sắp xếp tên để hiển thị:** có thể ưu tiên thứ tự từ điển, không phân biệt hoa/thường.
2. **Tìm tên nhập từ ô tìm kiếm:** có thể cho phép bỏ dấu, bỏ case để tăng khả năng tìm thấy.
3. **Xác định hai định danh có trùng nhau không:** phải theo quy tắc identity/uniqueness nghiêm ngặt.

Ví dụ dữ liệu `Lan` và `Lân` có thể được trả chung trong **tìm kiếm gần đúng**, nhưng không nên mặc định là cùng một người hay cùng username. Cơ chế collation phục vụ tìm kiếm không thay thế một khóa nhận dạng ổn định.

### 6.1. NLS session có làm UNIQUE constraint tự đổi quy tắc không?

**Không nên suy đoán rằng thay `NLS_COMP`/`NLS_SORT` trong session sẽ làm mọi unique constraint trong database coi `Lan` và `lan` là trùng nhau.** Ràng buộc duy nhất và index của nó chịu quy tắc collation/định nghĩa object và phiên bản Oracle.

Trong Oracle hiện đại có **data-bound collations**, một cột được khai báo case-insensitive có thể mang ngữ nghĩa khác với cột được khai báo binary. Tính duy nhất cần được thiết kế ở **schema/index/constraint phù hợp** và kiểm tra bằng thử nghiệm có kiểm soát, không phó mặc cho người dùng thay đổi NLS session.

### 6.2. Khi cần tìm kiếm không phân biệt case

Có nhiều hướng, phụ thuộc phiên bản và yêu cầu:

- Thiết lập collation phù hợp ở cột/biểu thức nếu hệ thống hỗ trợ và việc thay đổi schema được quản trị.
- Sử dụng `NLSSORT` hoặc `COLLATE` trong biểu thức theo cách được phiên bản hỗ trợ.
- Dùng biểu thức chuẩn hóa như `UPPER(column)` với function-based index trong một số bài toán đơn giản.
- Dùng chức năng tìm kiếm/chỉ mục thích hợp cho yêu cầu search phức tạp.

Ví dụ `UPPER(name) = UPPER(:search_name)` có thể hỗ trợ so sánh case-insensitive cơ bản, nhưng **không tương đương hoàn toàn** với mọi linguistic collation: các quy tắc chữ hoa/thường và ký tự đặc biệt thay đổi theo ngôn ngữ. `BINARY_AI` cũng không thay thế một chuẩn hóa dữ liệu định danh nhất quán.

## 7. Tác động đến index và hiệu năng

Oracle có thể cần tạo **linguistic sort keys** để thực hiện sorting hoặc so sánh theo collation khác binary. Nếu một truy vấn trước đó sử dụng B-tree index theo thứ tự binary, chuyển sang linguistic comparison có thể khiến optimizer chọn plan khác, cần sort thêm hoặc dùng index tương thích với biểu thức so sánh.

### 7.1. Function-based index cho một quy tắc sắp xếp

Ví dụ trên bảng lab:

```sql
CREATE INDEX idx_lab_nls_people_ci
ON lab_nls_people (
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI')
);
```

Index này lưu khóa từ biểu thức `NLSSORT(...BINARY_CI)`. Nó có thể hỗ trợ những truy vấn tương ứng nếu optimizer xác định có lợi và các điều kiện về expression/metadata/stats thỏa mãn. **Không hứa rằng cứ tạo index thì Oracle chắc chắn sử dụng nó**; phải xem execution plan và số lượng dòng thực tế.

Trong production, function-based index làm tăng chi phí ghi và lưu trữ, cần thống kê phù hợp và có thể chịu giới hạn độ dài sort key. Không tạo hàng loạt index `BINARY_CI` và `BINARY_AI` chỉ để thử mà không biết workload.

### 7.2. Truy vấn SQL và session state ảnh hưởng kế hoạch chạy

Giả sử SQL:

```sql
SELECT id
FROM lab_nls_people
WHERE full_name = :full_name;
```

Nếu collation hiệu lực thay đổi, tập giá trị được xem là bằng nhau có thể khác đi. Điều đó tác động **cardinality** và cách dùng index. Không nên cache kết quả ứng dụng như thể `'Lan'` luôn mang một định nghĩa so sánh cố định khi những request/connection có thể dùng NLS khác nhau.

Các câu SQL đang được tái sử dụng trong shared pool có ngữ cảnh môi trường của phiên; thay đổi thiết lập session có thể ảnh hưởng khả năng dùng lại cursor và plan theo quy tắc của Oracle. Với connection pool, nên đặt **một chính sách NLS nhất quán**, kiểm soát các thay đổi ở phạm vi request và thu thập execution plan khi có vấn đề.

### 7.3. Kết quả ORDER BY có thể có các khóa bằng nhau

Nếu `NLS_SORT=BINARY_CI`, tên `ALPHA` và `alpha` có thể cùng khóa sắp xếp. `ORDER BY name` không định nghĩa thứ tự phụ giữa hai hàng đó. Một trang hiển thị có phân trang `OFFSET/FETCH` có thể thiếu ổn định nếu order key không duy nhất.

Hãy thêm primary key hoặc một tiêu chí sắp xếp phụ:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
```

Kết quả thứ tự ổn định hơn khi `ID` là khóa duy nhất; các giá trị chữ gần nhau theo collation vẫn được liệt kê theo thứ tự nhất quán.

## 8. Data-bound collation và COLLATE trong Oracle mới

Từ Oracle Database 12.2, hệ thống hỗ trợ cơ chế collation được gắn với một số đối tượng/biểu thức SQL. Vì vậy, kết quả so sánh thực tế có thể được quyết định bởi:

- **Explicit collation:** chỉ rõ trong biểu thức SQL bằng `COLLATE` ở những phiên bản/kiểu dữ liệu hỗ trợ.
- **Declared/data-bound collation:** thuộc tính collation của cột hoặc schema/object.
- **Các quy tắc suy diễn collation** của expression.
- **Session NLS parameters:** đặc biệt đối với biểu thức sử dụng dạng collation theo session, tùy ngữ cảnh.

Ví dụ **minh họa cú pháp** ở phiên bản cho phép `COLLATE`:

```sql
SELECT id, full_name
FROM lab_nls_people
WHERE full_name COLLATE BINARY_CI = 'lan'
ORDER BY id;
```

Mục đích là thể hiện yêu cầu so sánh case-insensitive **ngay trong expression**, không cần đổi toàn bộ NLS session. Tính hợp lệ của câu lệnh, cách suy diễn collation và khả năng sử dụng index phải được xác minh với version/cấu hình thật.

Để xem collation khai báo của các cột ở phiên bản có metadata tương ứng, người quản trị có thể kiểm tra view dictionary như `USER_TAB_COLUMNS` (cột `COLLATION` nếu hỗ trợ) hoặc metadata schema. Nếu view hiện tại không có cột `COLLATION`, không tự kết luận database bị lỗi: đó có thể là khác biệt phiên bản/tính năng.

**Quy tắc quan trọng:** khi chẩn đoán hiện tượng “đã `ALTER SESSION SET NLS_COMP=LINGUISTIC` nhưng `WHERE` không thay đổi”, đừng chỉ tiếp tục thử NLS values; hãy xem **collation thực sự của cột/biểu thức** và cơ chế phiên bản Oracle đang dùng.

## 9. Các bẫy phổ biến trong nhập/xuất dữ liệu

### 9.1. Một cột NUMBER nhưng dữ liệu gốc là text

File nhận từ đối tác có:

```text
invoice_id;amount_text
1001;1.234,56
1002;99,50
```

Nếu dấu `;` được dùng làm delimiter, việc parse `AMOUNT_TEXT` phải xác định đúng dấu thập phân/dấu nhóm. Một số chuỗi không hợp lệ nên được báo lỗi để kiểm tra, **không tự bỏ mọi dấu `.` hoặc `,` rồi đoán giá trị**.

Ví dụ chuyển đổi chủ đích:

```sql
SELECT
    TO_NUMBER(
        '1.234,56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS parsed_amount
FROM dual;
```

Kết quả NUMBER là 1234.56. Mặt khác, nếu đầu vào `'1.234'` chưa có hợp đồng định dạng, không thể biết chắc đó là một nghìn hai trăm ba mươi tư hay một phẩy hai ba bốn.

### 9.2. Dữ liệu được đọc từ REST API/JSON

Giá trị JSON dạng number như:

```json
{"amount":1234.56}
```

khác với JSON string:

```json
{"amount":"1.234,56"}
```

Nếu API dùng number có kiểu, không cần chuyển văn bản theo locale để biểu diễn chính giá trị số. Nếu API dùng string đã format để hiển thị, phải có hợp đồng locale/format và kiểm tra chuyển đổi ở tầng thích hợp.

**Không dựa vào locale hiển thị frontend để đoán giá trị của toàn bộ backend.** Một ứng dụng có người dùng tiếng Việt và tiếng Anh vẫn có thể lưu NUMBER giống nhau; chỉ cách hiển thị text ở giao diện cần thay đổi.

### 9.3. So sánh tên người, tên sản phẩm và định danh

Những thao tác sau có yêu cầu khác nhau:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Sắp xếp tên để hiển thị | Collation theo ngôn ngữ phù hợp, có tie-breaker |
| Tìm tên không phân biệt hoa/thường | `BINARY_CI` hoặc collation tương đương được xác nhận |
| Tìm tên gần đúng không phân biệt dấu | Chỉ dùng accent-insensitive khi nghiệp vụ chấp nhận kết quả gần đúng |
| Kiểm tra username duy nhất | Ràng buộc/chuẩn hóa nhận dạng theo chính sách schema và ứng dụng |
| So sánh mã nghiệp vụ phân biệt chính xác ký tự | Chọn binary/explicit semantics phù hợp, không dùng lại search collation một cách tùy tiện |

Đặc biệt với ngôn ngữ có dấu, việc bỏ dấu có thể gộp các từ/người khác nhau. Không nên xem accent-insensitive như một phép chuẩn hóa dữ liệu vô hại.

## 10. Bài thực hành tổng hợp trên DUAL và dữ liệu mẫu

Phần đầu không tạo bảng, phù hợp SQL Developer/SQLcl/SQL*Plus. Phần tìm tên dùng bảng `LAB_NLS_PEOPLE` đã tạo ở mục 5 hoặc có thể điều chỉnh bằng CTE.

### Bước A — Ghi nhận và quan sát NLS session

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_SORT',
    'NLS_COMP'
)
ORDER BY parameter;
```

Ghi lại kết quả thật trước khi tiếp tục.

### Bước B — Hai cách hiển thị cùng một NUMBER

```sql
SELECT
    TO_CHAR(
        9876.5,
        'FM99G999D00',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS dot_decimal,
    TO_CHAR(
        9876.5,
        'FM99G999D00',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS comma_decimal
FROM dual;
```

Dự đoán: `9,876.50` và `9.876,50`. Kiểm tra xem NUMBER đầu vào có thay đổi không; nó vẫn là 9876.5.

### Bước C — Hai chuỗi số khác nhau quy ước

```sql
SELECT
    TO_NUMBER(
        '9,876.50',
        '99G999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS n1,
    TO_NUMBER(
        '9.876,50',
        '99G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ) AS n2
FROM dual;
```

Hai giá trị NUMBER phải tương đương nhau theo quy ước được chỉ rõ. Hãy giải thích vì sao bạn không nên truyền nguyên `'9.876,50'` vào phép tính và phụ thuộc session của một app server không được kiểm soát.

### Bước D — So sánh thay đổi sau NLS_SORT và NLS_COMP

Giả sử bảng lab có `Lan`, `lan`, `Lân`:

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Tiếp tục:

```sql
ALTER SESSION SET NLS_SORT = BINARY_CI;
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Cuối cùng:

```sql
ALTER SESSION SET NLS_SORT = BINARY_AI;

SELECT id, full_name
FROM lab_nls_people
WHERE full_name = 'Lan'
ORDER BY id;
```

Trả lời: tổ hợp nào có thể so khớp `lan`? Tổ hợp nào có thể so khớp `Lân`? Khi kết quả khác dự đoán, kiểm tra **collation của cột** và phiên bản trước khi kết luận session setting không hoạt động.

### Bước E — Kiểm soát ORDER BY trong từng SQL

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_CI'),
    id;
```

So với:

```sql
SELECT id, full_name
FROM lab_nls_people
ORDER BY
    NLSSORT(full_name, 'NLS_SORT=BINARY_AI'),
    id;
```

Quan sát tên có cùng sort key và vai trò của `id` khi phân trang.

### Bước F — Phục hồi môi trường

Khôi phục các tham số session theo số liệu đã ghi ở bước A, hoặc đóng connection lab và tạo connection mới với cấu hình chuẩn của client/ứng dụng. Nếu bảng lab không cần nữa, chỉ người sở hữu lab mới nên xóa nó trong đúng schema; không gỡ object ngoài phạm vi bài học.

## 11. Chẩn đoán lỗi thực tế

| Triệu chứng | Nguyên nhân cần kiểm tra | Bước chẩn đoán |
| --- | --- | --- |
| `ORA-01722: invalid number` khi lọc cột NUMBER bằng chuỗi | Chuyển kiểu ngầm, dữ liệu text hoặc dấu phân cách không phù hợp | Kiểm tra kiểu cột/bind, `NLS_NUMERIC_CHARACTERS` và `TO_NUMBER` format |
| Cùng một amount hiển thị `1,234.56` ở máy A và `1.234,56` ở máy B | Format hoặc NLS session khác nhau | Kiểm tra `NLS_SESSION_PARAMETERS`, `TO_CHAR` format và cấu hình client |
| Export/import số bị biến đổi | Không xác định locale hoặc separator | Xác nhận hợp đồng dữ liệu; parse rõ ràng và so sánh giá trị NUMBER |
| `ORDER BY name` thay đổi sau đổi NLS | Collation/sort key khác | Kiểm tra `NLS_SORT`, collation cột và `NLSSORT` |
| `WHERE name='Lan'` vẫn phân biệt hoa/thường khi `NLS_SORT=BINARY_CI` | `NLS_COMP=BINARY` hoặc collation của biểu thức ưu tiên khác | Kiểm tra `NLS_COMP` và data-bound/explicit collation |
| Tên có dấu bị coi trùng trong kết quả tìm kiếm | Collation accent-insensitive | Đối chiếu `BINARY_AI` và yêu cầu nghiệp vụ |
| Truy vấn sau thay NLS chậm hơn | Optimizer không còn dùng index/path cũ, sort cost tăng | Xem plan, statistics và index/expression phù hợp |
| Phân trang bị lặp/bỏ hàng khi sắp xếp tên | Những tên khác nhau có cùng linguistic sort key | Thêm tiêu chí phụ duy nhất `ORDER BY ... , id` |
| Request kế tiếp trong connection pool có kết quả khác | Session state NLS bị thay đổi nhưng không reset | Kiểm tra code khởi tạo/reset connection và dữ liệu quan sát từng session |
| Đã đặt NLS_COMP/LINGUISTIC nhưng predicate không thay đổi | Cột/biểu thức có collation khai báo riêng | Kiểm tra metadata collation và quy tắc phiên bản |

### 11.1. Quy trình điều tra gọn

```text
Sai giá trị số hay sai thứ tự/tìm kiếm?
                 │
        ┌────────┴──────────┐
        ▼                   ▼
     DỮ LIỆU SỐ          DỮ LIỆU CHỮ
        │                   │
 Kiểu NUMBER hay text?   Sắp xếp hay WHERE?
        │                   │
 NLS_NUMERIC_CHARACTERS  NLS_SORT / NLS_COMP
        │                   │
 TO_NUMBER/TO_CHAR       Collation cột/biểu thức
        │                   │
 Bind typed NUMBER       NLSSORT / COLLATE
        │                   │
        └────────┬──────────┘
                 ▼
       Kiểm tra đúng session
                 │
                 ▼
  Đối chiếu kết quả và execution plan
```

Trong cả hai trường hợp, xác định **kiểu dữ liệu thực**, **giá trị session**, **cấu hình cột/biểu thức** và **format trong SQL/app** trước khi sửa hệ thống. Việc đổi global NLS setting để sửa một báo cáo có thể vô tình thay đổi kết quả truy vấn của ứng dụng khác.

## 12. Thực hành tốt khi thiết kế hệ thống đa ngôn ngữ

### 12.1. Dữ liệu số: lưu kiểu số, định dạng ở ranh giới

- Lưu tiền, số lượng, tỷ lệ bằng kiểu dữ liệu số phù hợp và quy tắc precision/scale rõ ràng.
- Dùng bind parameters có kiểu `NUMBER`/`BigDecimal` cho dữ liệu số, tránh SQL nối chuỗi.
- Dùng `TO_NUMBER(text, mask, nlsparam)` khi cần parse text theo một nguồn được xác nhận.
- Dùng `TO_CHAR(number, mask, nlsparam)` cho kết quả text hoặc báo cáo cần một quy ước cố định.
- Không dùng `NLS_NUMERIC_CHARACTERS` để thay quy tắc cú pháp numeric literal SQL.
- Với JSON/CSV, định nghĩa contract về kiểu dữ liệu và dấu phân tách; ghi rõ locale nếu dữ liệu được truyền dưới dạng string.

### 12.2. Dữ liệu chữ: chọn collation đúng nghiệp vụ

- Tách **sort cho giao diện**, **tìm kiếm không phân biệt case/dấu** và **kiểm tra identity/uniqueness** thành ba yêu cầu.
- Không dùng accent-insensitive cho định danh cần phân biệt chính xác dấu hoặc ký tự.
- Thêm khóa phụ duy nhất khi `ORDER BY` có thể tạo các nhóm cùng sort key.
- Với Oracle có declared collation, kiểm tra collation thực thay vì chỉ nhìn session NLS.
- Xem execution plan/index khi áp dụng linguistic predicates cho lượng dữ liệu lớn.
- Thử với dữ liệu thực tế có dấu tiếng Việt, case, Unicode và những chuỗi trùng khóa so sánh.

### 12.3. Session và connection pool: nhất quán là quan trọng

- Ghi nhận các NLS thiết yếu ngay khi tạo connection nếu ứng dụng phụ thuộc chúng.
- Reset trạng thái trước khi đưa session về pool; tránh tác động xuyên request.
- Ưu tiên **định dạng rõ trong SQL hoặc tầng ứng dụng** cho các giao thức trao đổi dữ liệu.
- Không cho phép một request đổi `NLS_COMP` để tìm kiếm rồi để nguyên session phục vụ các câu SQL nghiệp vụ khác có yêu cầu so sánh khác.
- Kiểm thử trên cùng phiên bản/collation của môi trường production; không chỉ dựa trên cài đặt Oracle ở máy phát triển.

## 13. Câu hỏi tự kiểm tra

1. Với `NLS_NUMERIC_CHARACTERS=',.'`, dấu nào là decimal, dấu nào là group? Chuỗi `1.234,56` được hiểu như thế nào khi dùng đúng format model?
2. Vì sao `SELECT 1234.56 FROM dual` vẫn là numeric literal hợp lệ sau khi session chuyển sang dấu phẩy thập phân?
3. Dùng `TO_CHAR` và format `FM9G999D00`, làm sao tạo hai chuỗi `1,234.56` và `1.234,56` từ **cùng một giá trị NUMBER** mà không thay session?
4. Vì sao không nên viết `WHERE total_amount = '1,25'` khi `TOTAL_AMOUNT` là NUMBER trong ứng dụng đa vùng miền?
5. Nếu `NLS_SORT=BINARY_CI` nhưng `NLS_COMP=BINARY`, bạn có thể suy ra `WHERE name='Lan'` sẽ không phân biệt hoa/thường không? Vì sao?
6. Trong mô hình session-style collation, cần điều kiện nào để `BINARY_AI` áp dụng cho phép so sánh trong `WHERE`?
7. Vì sao `BINARY_AI` có thể không phù hợp làm quy tắc xác định hai username hoặc hai tên người là giống nhau?
8. `NLSSORT` trả về nội dung gì? Nó có sửa dữ liệu lưu ở cột không?
9. Khi hai tên có cùng linguistic sort key, vì sao cần thêm `id` trong `ORDER BY` khi phân trang?
10. Trên Oracle 12.2+ vì sao một cột được khai báo collation riêng có thể không đổi kết quả tìm kiếm sau `ALTER SESSION SET NLS_COMP=LINGUISTIC`?
11. Cần kiểm tra gì khi một request thay `NLS_SORT` và các request sau trên connection pool cho kết quả khác?
12. Khi nào nên tăng cường index cho tìm kiếm theo linguistic collation, và vì sao phải xem execution plan?

## 14. Tổng kết

```text
NLS_NUMERIC_CHARACTERS = '.,'
  ├── decimal = '.'
  └── group   = ','
             ↓
TO_NUMBER / TO_CHAR với D, G
  → cách đọc/hiển thị số dạng text
  → không thay kiểu NUMBER và cú pháp numeric literal SQL

NLS_SORT = BINARY / BINARY_CI / BINARY_AI / linguistic
             ↓
  Quy tắc collation/sắp xếp
             │
             ▼
NLS_COMP = BINARY hoặc LINGUISTIC
  → điều khiển so sánh binary/linguistic trong phạm vi áp dụng
  → không thay thế explicit/data-bound collation ở phiên bản mới
```

Ba nguyên tắc then chốt:

1. **NLS_NUMERIC_CHARACTERS phục vụ chuyển đổi/định dạng số dạng chuỗi, không phải thay đổi giá trị số đã lưu.** Khi truyền giá trị số giữa các hệ thống, ưu tiên kiểu dữ liệu số và chuyển đổi rõ ràng.
2. **NLS_SORT mô tả quy tắc collation; NLS_COMP quyết định vai trò của linguistic comparison trong các điều kiện SQL phù hợp.** Không mặc định chỉ đổi `NLS_SORT` là đủ để đổi hành vi `WHERE`.
3. **Kết quả phụ thuộc ngữ cảnh phiên và collation của biểu thức/cột.** Khi xây hệ thống đa ngôn ngữ, hãy phân biệt hiển thị, tìm kiếm và tính duy nhất; kiểm soát session NLS, kiểm thử ký tự có dấu và đo lại hiệu năng nếu thay đổi collation.

Nắm vững ba tham số này giúp bạn giải thích các lỗi chuyển đổi số theo vùng miền, các thứ tự sắp xếp bất ngờ và sự khác biệt giữa “tìm kiếm không phân biệt chữ hoa/chữ thường” với “so sánh chính xác dữ liệu” trong Oracle Database.
