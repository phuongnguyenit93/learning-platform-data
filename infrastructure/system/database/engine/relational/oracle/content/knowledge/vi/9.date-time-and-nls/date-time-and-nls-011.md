# Collation, so sánh tiếng Việt và lựa chọn quy tắc tìm kiếm

Một ứng dụng dùng Oracle Database có thể lưu tên khách hàng `Hòa`, `Hoà`, `HÒA`, `Hoa`, `Đức` và `Duc`. Khi người dùng gõ `hoa`, hệ thống có nên trả về `Hòa` không? Khi hiển thị danh sách, `Đạt` nên đứng ở đâu so với `Dung`? Nếu hai tài khoản cùng dùng mã đăng nhập `Minh` và `minh`, database có nên cho phép cả hai hay không?

Những câu hỏi này không thể trả lời chỉ bằng kiểu `VARCHAR2` hoặc việc chọn character set `AL32UTF8`. Chúng thuộc về **collation**: quy tắc mà Oracle dùng để **so sánh**, **xếp thứ tự** và, trong những phép toán hỗ trợ collation, **xác định chuỗi nào khớp với chuỗi nào**.

Bài học tập trung vào ba mục tiêu:

1. Phân biệt **binary comparison** với **linguistic comparison** và sự khác nhau giữa phân biệt chữ hoa/thường (**case sensitivity**) và phân biệt dấu (**accent sensitivity**).
2. Áp dụng quy tắc phù hợp cho **tiếng Việt** bằng `NLS_SORT`, `NLS_COMP`, `COLLATE` và `NLSSORT` trong Oracle SQL.
3. Chọn một hợp đồng tìm kiếm rõ ràng cho ứng dụng: **định danh chính xác**, **tra cứu bỏ qua hoa/thường**, **tìm không dấu**, **sắp xếp hiển thị** hay **tìm toàn văn**; đánh giá tác động đến unique constraint và index.

> **Phạm vi phiên bản:** Các ví dụ dùng cú pháp có trong Oracle Database 12.2 trở lên, bao gồm 19c và nhiều release mới hơn. Những đoạn liên quan **data-bound collation** ở cấp cột/bảng có điều kiện cấu hình riêng; các ví dụ truy vấn sử dụng `COLLATE` hoặc `NLSSORT` không yêu cầu phải thay cấu hình toàn database. Tính năng, tên collation và kết quả so sánh cụ thể cần được thử trên release/character set đang dùng.

## 1. Collation thực sự quyết định điều gì?

**Collation** xác định cách diễn giải quan hệ thứ tự và sự tương đương của các **giá trị chuỗi**. Nó ảnh hưởng đến những thao tác phụ thuộc so sánh ký tự như `ORDER BY`, điều kiện `=` / `<` / `>`, `LIKE`, một số hàm tìm chuỗi, nhóm dữ liệu và một số quy tắc khóa/ràng buộc.

Ví dụ với hai chuỗi:

```text
Giá trị A: 'Anh'
Giá trị B: 'anh'
```

- Theo quy tắc **phân biệt hoa/thường**, hai chuỗi không bằng nhau.
- Theo quy tắc **không phân biệt hoa/thường**, hai chuỗi có thể được coi là tương đương khi so sánh.
- Theo quy tắc **không phân biệt dấu và hoa/thường**, `Ánh`, `Anh` và `anh` có thể thuộc cùng một nhóm khớp, tùy collation.

Khi hai giá trị **bằng nhau theo collation**, điều đó **không có nghĩa các byte lưu trong database đã được đổi thành giống nhau**. Oracle vẫn có thể giữ nguyên cách viết của từng giá trị; chỉ một phép so sánh cụ thể sử dụng quy tắc tương đương.

### 1.1. Binary collation

**`BINARY`** so sánh theo biểu diễn nhị phân của các chuỗi trong character set tương ứng. Quy tắc này có ưu điểm đơn giản, có tính xác định và thường thuận lợi cho các mã định danh, nhưng **không phải** thứ tự bảng chữ cái tiếng Việt mà người đọc mong đợi.

Ví dụ, các ký tự `A`, `a` và `Á` có biểu diễn khác nhau; `BINARY` không coi chúng giống nhau chỉ vì cùng chữ cái gốc. Thứ tự hiển thị do binary sorting cũng có thể đặt các ký tự có dấu ở vị trí không tự nhiên đối với từ điển tiếng Việt.

### 1.2. Linguistic collation

**Linguistic collation** dùng quy tắc ngôn ngữ để xác định thứ tự và mức tương đương. Oracle cung cấp các nhóm collation như **monolingual** (theo một ngôn ngữ), **multilingual** và các collation dựa trên **Unicode Collation Algorithm (UCA)**.

Oracle có tên collation **`VIETNAMESE`** trong danh sách monolingual linguistic collations. Khi cần sắp xếp một danh sách tên/từ tiếng Việt theo quy tắc ngôn ngữ, đây là một lựa chọn cần đem ra thử. Với dữ liệu đa ngôn ngữ, có thể đánh giá collation UCA hoặc multilingual được release hỗ trợ.

**Quan trọng:** “sắp xếp tiếng Việt chuẩn” là một yêu cầu nghiệp vụ cần làm rõ. Thứ tự các dấu thanh, nguyên âm `a/ă/â`, chữ `d/đ`, khoảng trắng, dấu gạch nối, họ/tên đệm và quy tắc xếp theo **tên chính** hay **toàn bộ họ tên** đều có thể ảnh hưởng kết quả mà người dùng kỳ vọng. Collation của database là công cụ thực thi một quy tắc được chọn, không tự quyết định toàn bộ quy tắc từ điển hay nghiệp vụ.

## 2. Hai trục: hoa/thường và dấu

| Chế độ | Có phân biệt `A` và `a`? | Có phân biệt `a` và `á`? | Khi nên cân nhắc |
| --- | --- | --- | --- |
| **Case-sensitive, accent-sensitive** | Có | Có | So sánh chính xác, định danh, mã nghiệp vụ |
| **Case-insensitive (CI), accent-sensitive** | Không | Có | Tìm tên không cần nhập đúng chữ hoa nhưng vẫn cần dấu |
| **Case-insensitive, accent-insensitive (AI)** | Không | Không đối với khác biệt dấu mà collation quy định bỏ qua | Ô tìm kiếm tiện dụng cho người nhập không dấu |

Trong tên collation Oracle:

- **`_CI`** thường có nghĩa **case-insensitive**: bỏ qua khác biệt hoa/thường nhưng **vẫn phân biệt dấu**.
- **`_AI`** có nghĩa **accent-insensitive *và* case-insensitive**. Không nên gọi `_AI` là “chỉ bỏ dấu nhưng vẫn phân biệt hoa/thường”.
- Tên không có hậu tố như `VIETNAMESE` thường dùng biến thể phân biệt hoa/thường và dấu theo quy tắc của collation đó.

Các tên thông dụng:

| Collation | Đặc trưng | Lưu ý |
| --- | --- | --- |
| `BINARY` | So sánh binary, phân biệt hoa/thường và dấu | Phù hợp khi cần ranh giới định danh chính xác |
| `BINARY_CI` | Không phân biệt hoa/thường theo nhóm binary collation | Không tự biến thành thứ tự từ điển tiếng Việt |
| `BINARY_AI` | Không phân biệt hoa/thường và dấu theo nhóm binary collation | Không bảo đảm khớp mọi quy ước “bỏ dấu tiếng Việt” của sản phẩm |
| `VIETNAMESE` | Linguistic collation tiếng Việt | Dùng thử cho sắp xếp hiển thị có quy tắc tiếng Việt |
| `VIETNAMESE_CI` | Vietnamese collation không phân biệt hoa/thường | Vẫn phân biệt các dấu theo collation |
| `VIETNAMESE_AI` | Vietnamese collation bỏ qua hoa/thường và khác biệt dấu theo quy tắc | Hữu ích làm ứng viên tìm kiếm không dấu; cần thử dữ liệu thực |

Các tên `VIETNAMESE`, `VIETNAMESE_CI` và `VIETNAMESE_AI` xuất phát từ tên linguistic collation và quy tắc hậu tố Oracle hỗ trợ. Nếu một môi trường cũ không nhận tên collation, xem danh sách hỗ trợ của **release đó**, không tự thay bằng tên tưởng tượng.

### 2.1. Với tiếng Việt, “không dấu” có thể mang nhiều nghĩa

Tiếng Việt có **dấu thanh** (sắc, huyền, hỏi, ngã, nặng), dấu hình thành nguyên âm như **ă, â, ê, ô, ơ, ư**, và chữ cái **đ**. Ở giao diện người dùng, yêu cầu “gõ không dấu vẫn tìm được” có thể được hiểu theo nhiều mức:

1. Gõ `anh` tìm được `Anh` và `Ánh`.
2. Gõ `hoa` tìm được `Hòa` hoặc `Hoà` tùy cách viết.
3. Gõ `duong` tìm được `Dương`.
4. Gõ `duc` có phải tìm được `Đức` không?
5. Gõ sai dấu/vị trí dấu, thừa khoảng trắng hoặc sai một ký tự có phải khớp không?

Ba câu đầu thường nằm trong phạm vi **case/accent-insensitive matching** có thể kiểm tra bằng collation. Riêng `d` và `đ` cần được **kiểm nghiệm** theo collation được chọn: `đ` là chữ cái riêng trong bảng chữ cái tiếng Việt, không thể suy ra từ tên `_AI` rằng mọi quy tắc nghiệp vụ về chuyển `đ` thành `d` đều được đáp ứng. Trường hợp thứ năm thuộc cả **chuẩn hóa đầu vào** hoặc **fuzzy/full-text search**, vượt ra ngoài việc đổi `NLS_SORT`.

**Không nên viết hàm “xóa dấu” bằng một danh sách `REPLACE` ngắn rồi coi đó là tương đương Oracle collation.** Cách đó dễ bỏ sót chữ hoa, tổ hợp ký tự Unicode, `đ/Đ`, dấu đặt theo dạng tổ hợp và các ngôn ngữ khác.

## 3. Character set, NLS và collation là các lớp khác nhau

Trong chương *Ngày giờ và NLS*, cần đặt collation cạnh các tham số NLS khác mà không đánh đồng chúng.

| Khái niệm/tham số | Trả lời câu hỏi gì? | Có tự giải quyết tìm không dấu không? |
| --- | --- | --- |
| **`NLS_CHARACTERSET`** | Database dùng cách mã hóa ký tự nào, ví dụ `AL32UTF8`? | **Không** |
| **`NLS_NCHAR_CHARACTERSET`** | National character types dùng character set nào? | **Không** |
| **`NLS_LANGUAGE`** | Ngôn ngữ mặc định cho một số thông báo, tên ngày/tháng và thiết lập liên quan | Không trực tiếp là chính sách tìm kiếm |
| **`NLS_TERRITORY`** | Quy ước vùng, định dạng số/ngày và mặc định liên quan | Không |
| **`NLS_DATE_LANGUAGE`** | Ngôn ngữ tên thứ/ngày/tháng trong chuyển đổi ngày giờ | Không |
| **`NLS_SORT`** | Collation/sort sequence của session khi phép toán dùng nó | **Có**, nếu phép toán thực sự tham chiếu session collation |
| **`NLS_COMP`** | Cho phép những phép so sánh dùng session linguistic collation theo chế độ legacy/pseudo-collation | **Có thể**, phối hợp với `NLS_SORT` |
| **`COLLATE`** | Gắn collation cho biểu thức hoặc cột để quy định phép so sánh | **Có**, với collation thích hợp |

**Dùng UTF-8 để lưu được dấu tiếng Việt** và **chọn collation để so sánh đúng tiếng Việt** là hai công việc riêng. Một cột `VARCHAR2` trong database `AL32UTF8` vẫn có thể dùng `BINARY` để so sánh case/diacritic-sensitive. Tương tự, `NCHAR`/`NVARCHAR2` không mặc nhiên sắp xếp đúng thứ tự từ điển tiếng Việt.

### 3.1. Đọc thiết lập của phiên và database

Trong SQLcl, SQL Developer hoặc client SQL khác:

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_SORT',
    'NLS_COMP',
    'NLS_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter;

SELECT parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_CHARACTERSET',
    'NLS_NCHAR_CHARACTERSET'
)
ORDER BY parameter;
```

Hoặc đọc trực tiếp một số thuộc tính của session:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'LANGUAGE') AS language_context,
    SYS_CONTEXT('USERENV', 'NLS_SORT') AS nls_sort
FROM dual;
```

`NLS_SESSION_PARAMETERS` cho biết các tham số hiện hành của **session đang chạy câu SQL**. Kết nối từ ứng dụng Java, SQL Developer và một session DBA có thể có giá trị NLS khác nhau dù cùng PDB và cùng bảng. Vì vậy một bug “máy tôi tìm được, máy bạn không tìm được” có thể xuất phát từ thiết lập session hoặc sự khác biệt giữa **declared collation** của các cột.

### 3.2. Mối quan hệ giữa `NLS_SORT` và `NLS_COMP`

Trong mô hình sử dụng **session collation** cổ điển, có thể hình dung:

```text
              NLS_SORT = VIETNAMESE_AI
                         |
           +-------------+---------------+
           |                             |
   ORDER BY kiểu             WHERE name = :keyword
   dùng session collation    nếu cột dùng USING_NLS_COMP
           |                             |
   Sắp xếp theo             NLS_COMP = BINARY
   VIETNAMESE_AI            -> thường so sánh binary
                                         |
                            NLS_COMP = LINGUISTIC
                            -> so sánh linguistic
```

Trong Oracle 12.2+, **data-bound collation** còn tham gia quyết định quy tắc thực sự. Nếu cột được khai báo bằng named collation như `BINARY_CI`, không được suy diễn rằng chỉ cần sửa `NLS_COMP` để thay đổi toàn bộ hành vi cột đó. `USING_NLS_COMP` là một **pseudo-collation** giữ hành vi phụ thuộc session theo cơ chế tương thích.

**Kết luận thực hành:** trước khi dự đoán kết quả, cần biết **collation của biểu thức/cột** *và* các tham số session khi biểu thức dùng pseudo-collation.

## 4. Bài lab SQL với tên tiếng Việt

Các câu lệnh dưới đây dành cho **schema thực hành riêng** và bảng chỉ dùng cho bài học. Không chạy `CREATE`/`DROP` trên schema nghiệp vụ. Client và đường truyền cần hỗ trợ Unicode; tốt nhất database dùng `AL32UTF8`.

### 4.1. Tạo bảng không khai báo collation riêng

```sql
CREATE TABLE vn_collation_lab (
    id        NUMBER PRIMARY KEY,
    full_name VARCHAR2(100 CHAR) NOT NULL,
    note      VARCHAR2(200 CHAR)
);

INSERT INTO vn_collation_lab VALUES (1,  'Anh',   'Không dấu, chữ hoa đầu');
INSERT INTO vn_collation_lab VALUES (2,  'anh',   'Khác hoa/thường');
INSERT INTO vn_collation_lab VALUES (3,  'Ánh',   'Có dấu sắc');
INSERT INTO vn_collation_lab VALUES (4,  'An',    'Không dấu');
INSERT INTO vn_collation_lab VALUES (5,  'Ân',    'Nguyên âm Â');
INSERT INTO vn_collation_lab VALUES (6,  'Ăn',    'Nguyên âm Ă');
INSERT INTO vn_collation_lab VALUES (7,  'Dung',  'Chữ D không dấu');
INSERT INTO vn_collation_lab VALUES (8,  'Dũng',  'Có dấu ngã');
INSERT INTO vn_collation_lab VALUES (9,  'Đạt',   'Chữ Đ');
INSERT INTO vn_collation_lab VALUES (10, 'Dat',   'Chữ D');
INSERT INTO vn_collation_lab VALUES (11, 'Hoa',   'Không dấu');
INSERT INTO vn_collation_lab VALUES (12, 'Hòa',   'Có dấu huyền');
INSERT INTO vn_collation_lab VALUES (13, 'Nam',   'Không dấu');
INSERT INTO vn_collation_lab VALUES (14, 'Năm',   'Nguyên âm Ă');

COMMIT;
```

Không khai báo `COLLATE` cho từng cột ở bài lab này để dễ minh họa hành vi session. Tuy nhiên **default collation của schema/bảng** có thể đã được thiết lập từ trước trên một database có data-bound collation; hãy dùng phần kiểm tra ở mục 7 để biết thực trạng. Muốn thử rõ nhất `NLS_COMP`/`NLS_SORT`, thực hiện trên schema lab có default `USING_NLS_COMP`.

### 4.2. So sánh thứ tự binary và tiếng Việt

Thay vì dựa vào NLS session hiện tại, dùng **`COLLATE`** ngay trên biểu thức `ORDER BY`:

```sql
-- So sánh binary.
SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name COLLATE BINARY, id;

-- So sánh theo linguistic collation tiếng Việt.
SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name COLLATE VIETNAMESE, id;
```

Hãy tự ghi lại **thứ tự thực tế của 14 hàng** trên môi trường đang dùng; không cần học thuộc một bảng thứ tự Unicode code point. Các ký tự `a/ă/â`, `d/đ` và dấu thanh giúp dễ quan sát khác biệt giữa binary order và linguistic order. Tên collation `VIETNAMESE` có mục đích đặt các ký tự theo quy tắc ngôn ngữ tiếng Việt, còn `BINARY` không được thiết kế để đáp ứng cách xếp từ điển.

**Vì sao thêm `, id`?** Nếu nhiều chuỗi được collation xem như tương đương, `ORDER BY full_name` một mình không bắt buộc cho thứ tự ổn định giữa các hàng bằng nhau. Thêm một khóa phụ **duy nhất** như `ID` giúp phân trang và kết quả lặp lại dễ dự đoán hơn.

### 4.3. So sánh ba mức khớp tên

Tìm `anh` theo quy tắc chính xác:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE BINARY = 'anh'
ORDER BY id;
```

Trường hợp này chỉ lấy tên có nội dung khớp binary, điển hình hàng `anh`. Tìm không phân biệt hoa/thường nhưng **vẫn phân biệt dấu**:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_CI = 'anh'
ORDER BY id;
```

Các biến thể `Anh` và `anh` sẽ là ứng viên khớp; `Ánh` khác dấu nên không được xem là tương đương chỉ vì `_CI`. Tìm không phân biệt hoa/thường và **bỏ qua dấu theo collation**:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI = 'anh'
ORDER BY id;
```

Với `VIETNAMESE_AI`, các biến thể khác nhau ở dấu/hoa như `Ánh` có thể cùng khớp `anh`. Đây là loại so sánh phù hợp cho một ô tìm tên có yêu cầu “gõ không dấu”. **Không dùng truy vấn này để thay thế bước xác nhận danh tính hoặc khóa nghiệp vụ**, vì nó cố ý gom nhiều chuỗi khác nhau thành các giá trị bằng nhau.

### 4.4. Kiểm nghiệm riêng `d` và `đ`

Đừng đoán kết quả chỉ từ `_AI`. Chạy hai phép thử độc lập:

```sql
SELECT
    CASE
        WHEN 'd' COLLATE VIETNAMESE_AI = 'đ'
        THEN 'EQUIVALENT'
        ELSE 'DISTINCT'
    END AS vietnamese_ai_result,
    CASE
        WHEN 'd' COLLATE BINARY_AI = 'đ'
        THEN 'EQUIVALENT'
        ELSE 'DISTINCT'
    END AS binary_ai_result
FROM dual;
```

Sau đó ghi lại điều người dùng sản phẩm kỳ vọng khi gõ `Duc` để tìm `Đức`. **Kết quả thực tế của hai collation** là bằng chứng để lựa chọn; nếu quy tắc nghiệp vụ yêu cầu thêm một phép chuẩn hóa/tìm kiếm đặc thù, hãy thiết kế nó một cách minh bạch và kiểm thử đối với dữ liệu tiếng Việt thật.

## 5. Session NLS: thay đổi cách so sánh mà không đổi cột

Để thấy vai trò của `NLS_COMP` và `NLS_SORT`, sử dụng một **session lab riêng**; ghi lại giá trị ban đầu ở mục 3.1 để trả lại sau bài học.

### 5.1. `NLS_SORT` có thể ảnh hưởng `ORDER BY`

```sql
ALTER SESSION SET NLS_SORT = VIETNAMESE;

SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name, id;
```

Với cột dùng pseudo-collation `USING_NLS_COMP`, `ORDER BY` có thể lấy thứ tự ngôn ngữ từ `NLS_SORT`. Nhưng nếu cột dùng **named collation** (ví dụ `BINARY`), thứ tự được xác định theo quy tắc data-bound thay vì chỉ nhìn vào session.

Vì vậy câu SQL có `COLLATE VIETNAMESE` rõ ràng là cách thí nghiệm có tính dự đoán cao hơn khi không muốn phụ thuộc session hiện tại.

### 5.2. `NLS_COMP = BINARY` với equality

```sql
ALTER SESSION SET NLS_SORT = VIETNAMESE_AI;
ALTER SESSION SET NLS_COMP = BINARY;

SELECT id, full_name
FROM vn_collation_lab
WHERE full_name = 'anh'
ORDER BY id;
```

Khi biểu thức dựa vào `USING_NLS_COMP`, `WHERE full_name = 'anh'` vẫn sử dụng so sánh binary trong chế độ `NLS_COMP=BINARY`, mặc dù `NLS_SORT` đã là `VIETNAMESE_AI`. Đây là lý do **chỉ đổi `NLS_SORT` không đảm bảo một câu `WHERE =` trở thành accent-insensitive**.

### 5.3. `NLS_COMP = LINGUISTIC` với equality

```sql
ALTER SESSION SET NLS_COMP = LINGUISTIC;

SELECT id, full_name
FROM vn_collation_lab
WHERE full_name = 'anh'
ORDER BY id;
```

Nếu phép so sánh dựa vào `USING_NLS_COMP`, lúc này `NLS_COMP=LINGUISTIC` cho phép `WHERE` dùng collation theo `NLS_SORT=VIETNAMESE_AI`; kết quả có thể bao gồm các biến thể như `Anh` và `Ánh`.

**Giới hạn cần nhớ:** Đây là mô hình phù hợp với **pseudo-collation** và hành vi session cổ điển. Kết quả có thể khác nếu cột/biểu thức dùng một **named data-bound collation**. Từ Oracle 12.2, collation của biểu thức được xét theo quy tắc derivation/determination trước khi áp tham số NLS tương ứng.

### 5.4. Kết thúc lab session

Khôi phục các giá trị `NLS_SORT` và `NLS_COMP` bạn đã **ghi lại** trước khi thử. Ví dụ, nếu session ban đầu dùng `BINARY` và `BINARY`:

```sql
ALTER SESSION SET NLS_SORT = BINARY;
ALTER SESSION SET NLS_COMP = BINARY;
```

Trong ứng dụng có **connection pool**, session state có thể bị tái sử dụng. Nếu một request tự `ALTER SESSION SET NLS_COMP=LINGUISTIC` rồi trả kết nối về pool mà không reset, request sau có thể có hành vi so sánh khác. Nên cấu hình session một cách có kiểm soát ở tầng connection pool hoặc dùng `COLLATE` trong query cụ thể để hợp đồng tìm kiếm rõ ràng.

## 6. `COLLATE` cho một truy vấn cụ thể

Từ Oracle 12.2, **`COLLATE` operator** cho phép gắn collation vào biểu thức ký tự trong một phép toán SQL:

```sql
-- Sắp xếp hiển thị theo tiếng Việt.
SELECT id, full_name
FROM vn_collation_lab
ORDER BY full_name COLLATE VIETNAMESE, id;

-- Tìm chính xác, phân biệt chữ hoa/thường và dấu.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE BINARY = :exact_name;

-- Tìm không phân biệt hoa/thường, giữ phân biệt dấu.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_CI = :name;

-- Tìm không phân biệt hoa/thường và dấu theo quy tắc tiếng Việt.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI = :name;
```

`:exact_name` và `:name` là **bind variables**. Trong SQL Developer có thể được yêu cầu nhập giá trị; trong JDBC, giá trị thường truyền bằng `PreparedStatement.setString`, không nối trực tiếp input người dùng vào chuỗi SQL.

**Ưu điểm:** mỗi truy vấn tuyên bố rõ cách so sánh, nên hai màn hình có thể có chính sách khác nhau:

- Form tra cứu bằng **mã đăng nhập** dùng `BINARY`.
- Màn hình danh bạ dùng `VIETNAMESE` để sắp xếp.
- Ô tìm tên “không cần gõ dấu” dùng `VIETNAMESE_AI`.

Đây là một cách tránh thay `NLS_COMP` trên toàn bộ session khi chỉ có **một** phép so sánh cần ngữ nghĩa khác.

### 6.1. `LIKE` và tìm prefix

Ví dụ tìm người có tên bắt đầu bằng cụm `hoa` (theo collation bỏ qua dấu):

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI LIKE 'hoa%'
ORDER BY full_name COLLATE VIETNAMESE, id;
```

`LIKE` sử dụng dấu `%` để khớp chuỗi bất kỳ và dấu `_` để khớp một ký tự theo quy tắc của phép toán. Khi tìm theo input của người dùng, nếu người dùng muốn tìm **ký tự `%` hoặc `_` thật**, cần escape chúng trước khi tạo pattern:

```sql
-- Tìm ký tự % thật; dấu \ được khai báo là escape character.
SELECT id, full_name
FROM vn_collation_lab
WHERE full_name COLLATE VIETNAMESE_AI LIKE '%\%%' ESCAPE '\';
```

Trong ứng dụng, nên **bind toàn bộ pattern** sau khi xây dựng và escape đúng các ký tự đặc biệt. Một chuỗi input `100%` không tự có nghĩa người dùng chủ động muốn wildcard.

**Prefix search và substring search khác nhau về hiệu năng.** `LIKE 'hoa%'` có thể có cách khai thác index thích hợp; `LIKE '%hoa%'` thường khó sử dụng B-tree range scan thông thường vì có wildcard đầu. Với lượng văn bản lớn và nhu cầu tìm từ bên trong chuỗi, nên đánh giá công cụ tìm toàn văn phù hợp.

### 6.2. Đừng đồng nhất accent-insensitive với fuzzy search

Collation `VIETNAMESE_AI` có thể xem `Anh` và `Ánh` là tương đương theo dấu, nhưng không tự sửa lỗi gõ thiếu/đổi ký tự, không tách họ tên, không hiểu nickname hoặc biến `Nguyễn Văn An` thành kết quả của mọi cách viết tắt.

| Mong muốn | Công cụ phù hợp để bắt đầu |
| --- | --- |
| `Anh` = `anh` | Case-insensitive collation |
| `Anh` ≈ `Ánh` | Accent-insensitive collation theo quy tắc được chọn |
| Prefix `hoa...` | `LIKE 'hoa%'` + collation/bind + index có cân nhắc |
| Tìm một từ bất kỳ ở giữa một tài liệu dài | Oracle Text hoặc giải pháp full-text |
| Gõ sai một ký tự, đảo vị trí ký tự | Fuzzy matching/search riêng có đo độ phù hợp |
| Tìm theo tên chính thay vì họ và tên đệm | Mô hình dữ liệu và quy tắc tách tên |
| Chuẩn hóa khoảng trắng, ký tự Unicode tổ hợp | Chính sách chuẩn hóa đầu vào rõ ràng |

## 7. Data-bound collation ở cột và bảng

Ngoài `COLLATE` trong một query, Oracle còn hỗ trợ khai báo **collation gắn với dữ liệu** cho cột/bảng/schema trong các cấu hình thích hợp. Đây là lựa chọn có tác động rộng hơn vì các phép toán trên cột, index và constraint có thể dựa vào declared collation.

### 7.1. Điều kiện quan trọng trước khi dùng DDL

Theo Oracle Globalization Support Guide, để khai báo **data-bound collation** cho các database objects ở các release hỗ trợ, cần:

- `COMPATIBLE >= 12.2`.
- `MAX_STRING_SIZE = EXTENDED`.

**Đây không phải tham số tùy tiện bật trong một bài học.** Thay `MAX_STRING_SIZE` từ `STANDARD` sang `EXTENDED` là tác vụ quản trị database/PDB có yêu cầu nâng cấp/migration và không thể đơn giản đổi ngược theo quy tắc Oracle; cần DBA và quy trình phù hợp. **`COLLATE` operator ở mức biểu thức SQL vẫn dùng được trên release hỗ trợ ngay cả khi không bật data-bound collation cho object.**

### 7.2. Ví dụ khai báo cột

Chỉ chạy đoạn DDL sau trong môi trường lab **đã thỏa điều kiện data-bound collation**:

```sql
CREATE TABLE vn_profile_collated (
    id           NUMBER PRIMARY KEY,
    login_code   VARCHAR2(60 CHAR) COLLATE BINARY NOT NULL,
    display_name VARCHAR2(100 CHAR) COLLATE VIETNAMESE_CI NOT NULL,
    search_name  VARCHAR2(100 CHAR) COLLATE VIETNAMESE_AI
);
```

Ý nghĩa thiết kế:

- `LOGIN_CODE` có collation `BINARY`: phép so sánh ký tự theo quy tắc chính xác; phù hợp nếu nghiệp vụ muốn `ab` khác `AB`.
- `DISPLAY_NAME` có `VIETNAMESE_CI`: bỏ qua hoa/thường nhưng vẫn phân biệt dấu ở các phép toán collation-sensitive.
- `SEARCH_NAME` có `VIETNAMESE_AI`: muốn tìm tên không dấu thông qua quy tắc tiếng Việt.

Đây là **ví dụ phân biệt cơ chế**, không phải khuyến cáo mọi ứng dụng phải lưu cả ba cột hoặc gán collation cố định cho toàn bộ tên người. Nếu sản phẩm có nhiều ngôn ngữ, hoặc các màn hình đòi nhiều chế độ tìm, có thể giữ dữ liệu gốc và dùng `COLLATE` theo từng truy vấn.

### 7.3. Quan sát collation đã khai báo

```sql
SELECT table_name, column_name, data_type, collation
FROM user_tab_cols
WHERE table_name IN ('VN_COLLATION_LAB', 'VN_PROFILE_COLLATED')
  AND data_type IN ('CHAR', 'VARCHAR2', 'NCHAR', 'NVARCHAR2')
ORDER BY table_name, column_name;
```

Hoặc trong một truy vấn có cột ký tự:

```sql
SELECT full_name, COLLATION(full_name) AS derived_collation
FROM vn_collation_lab
WHERE id = 1;
```

**`COLLATION(expression)`** cho biết **derived data-bound collation** của biểu thức, không nhất thiết cho biết **named collation thực sự được session sử dụng** khi biểu thức mang pseudo-collation như `USING_NLS_COMP` hay `USING_NLS_SORT`. Nếu kết quả là `USING_NLS_COMP`, vẫn cần xem `NLS_COMP` và `NLS_SORT` để giải thích hành vi so sánh.

### 7.4. Ràng buộc và index chịu ảnh hưởng của collation

Một column collation có thể tham gia cách Oracle đánh giá **unique constraint/unique index**, tương đương khóa và các cấu trúc lưu trữ phụ thuộc khóa. Ví dụ ở lab đã hỗ trợ data-bound collation:

```sql
CREATE TABLE vn_account_ci (
    account_id NUMBER PRIMARY KEY,
    username   VARCHAR2(60 CHAR) COLLATE BINARY_CI
               NOT NULL UNIQUE
);
```

Khi unique key dùng collation case-insensitive, hai giá trị `Minh` và `minh` có thể bị xem là trùng. Điều đó **phù hợp** với hệ thống định danh username không phân biệt chữ hoa; nhưng sẽ **không phù hợp** nếu nghiệp vụ chủ ý cho phép hai tài khoản khác nhau chỉ nhờ cách viết hoa.

Đổi collation trên một cột đang có dữ liệu và constraint/index là thay đổi về **ngữ nghĩa dữ liệu**, không chỉ giao diện: có thể phát sinh xung đột giá trị trước đây được xem là khác nhau. Với foreign key, cần xét tính tương thích với key được tham chiếu. Không tự đổi collation production chỉ để “fix search” mà chưa kiểm kê dữ liệu trùng và các ràng buộc.

## 8. `NLSSORT`: làm rõ khóa so sánh

Hàm **`NLSSORT`** chuyển một giá trị ký tự thành **collation key** có kiểu `RAW`, có thể đem so sánh theo thứ tự nhị phân để biểu diễn quy tắc collation đã chọn.

```sql
SELECT
    id,
    full_name,
    RAWTOHEX(NLSSORT(full_name, 'NLS_SORT=VIETNAMESE')) AS sort_key_hex
FROM vn_collation_lab
ORDER BY NLSSORT(full_name, 'NLS_SORT=VIETNAMESE'), id;
```

`SORT_KEY_HEX` dùng cho **quan sát kỹ thuật**, không phải chuỗi văn bản đã được chuẩn hóa để hiển thị cho người dùng. Không lấy kết quả `RAWTOHEX` làm tên người đã bỏ dấu hoặc lưu collation key làm định danh vĩnh viễn giữa các phiên bản.

### 8.1. So sánh hai chuỗi bằng cùng một quy tắc

```sql
SELECT
    CASE
        WHEN NLSSORT('Ánh', 'NLS_SORT=VIETNAMESE_AI')
           = NLSSORT('anh', 'NLS_SORT=VIETNAMESE_AI')
        THEN 'EQUIVALENT'
        ELSE 'DISTINCT'
    END AS vietnamese_ai_match
FROM dual;
```

Với các cặp cần thử trong ứng dụng, có thể thay chuỗi vào hai vế, nhưng **hai vế phải dùng cùng collation**. Đem một collation key tạo bởi `BINARY` so với key tạo bởi `VIETNAMESE_AI` không phải cách kiểm tra tương đương hợp lệ.

### 8.2. `NLSSORT` cho điều kiện chính xác về collation

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
    = NLSSORT(:search_name, 'NLS_SORT=VIETNAMESE_AI')
ORDER BY id;
```

Đây là cách diễn đạt bằng **function-based comparison**, có thể hữu ích khi cần một expression tương ứng với index `NLSSORT`. Trên Oracle 12.2+, `WHERE full_name COLLATE VIETNAMESE_AI = :search_name` thường dễ đọc hơn khi mục tiêu chỉ là tuyên bố semantics của query.

**Giới hạn:** `NLSSORT` tạo collation key kiểu `RAW` và có giới hạn độ dài/kích thước key theo release và `MAX_STRING_SIZE`. Với chuỗi cực dài, một số collation có thể tạo khóa bị cắt hoặc gây lỗi như `ORA-12742` tùy cấu hình; không thiết kế so sánh định danh quan trọng dựa trên việc cắt một key quá dài. Tài liệu Oracle mô tả điều kiện cụ thể của từng release.

## 9. Index và hiệu năng tìm kiếm theo collation

Khi chuyển một điều kiện từ binary sang linguistic, Oracle có thể phải chuyển chuỗi thành collation key hoặc dùng một cơ chế index khác. **Không có quy tắc “có index trên cột là mọi loại tìm kiếm đều dùng nhanh”.**

### 9.1. Index thông thường và nhu cầu của phép so sánh

```sql
CREATE INDEX ix_vn_name_binary
ON vn_collation_lab (full_name);
```

Index thông thường trên cột có thể phù hợp với tìm kiếm/ORDER BY theo collation của key. Nếu truy vấn sử dụng **linguistic collation khác**, optimizer có thể cần xử lý `NLSSORT` và **không dùng index binary như một range scan tương đương**.

Trên các release hỗ trợ named data-bound collation, Oracle có thể tổ chức các index trên cột collated như một dạng **function-based index trên collation key**. Vì vậy cần đọc thực tế trong dictionary và execution plan, không áp dụng một quy tắc cứng cho mọi trường hợp.

### 9.2. Function-based index cho chính sách tìm tên không dấu

Với bảng lab, có thể tạo một index cho expression:

```sql
CREATE INDEX ix_vn_name_ai
ON vn_collation_lab (
    NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
);
```

Query có expression phù hợp:

```sql
SELECT id, full_name
FROM vn_collation_lab
WHERE NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
    = NLSSORT(:search_name, 'NLS_SORT=VIETNAMESE_AI')
ORDER BY id;
```

Optimizer **có thể** dùng function-based index tùy số hàng, selectivity, thống kê, cấu hình và cost model. Với một bảng lab 14 hàng, full table scan có thể hoàn toàn hợp lý. Đừng đánh giá index qua thời gian chạy của vài hàng.

Lưu ý khi thiết kế index thực:

- Index dùng collation key có thể cần thêm dung lượng và tăng chi phí `INSERT`/`UPDATE`.
- Một collation key có thể dài hơn chuỗi gốc; với khóa lớn phải xét giới hạn **maximum index key length** và độ dài `NLSSORT`.
- Expression trong query và expression trong index cần tương thích để optimizer khai thác hiệu quả.
- Nếu collation hoặc session settings tác động đến expression, cần kiểm soát môi trường và tính ổn định của index/query.
- Với data-bound collation và index tự sinh trên key, xem dictionary để tránh tạo trùng index có chức năng tương đương.

### 9.3. Xem execution plan, không đoán

```sql
EXPLAIN PLAN FOR
SELECT id, full_name
FROM vn_collation_lab
WHERE NLSSORT(full_name, 'NLS_SORT=VIETNAMESE_AI')
    = NLSSORT('anh', 'NLS_SORT=VIETNAMESE_AI');

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` là **kế hoạch dự kiến**; không tự chứng minh runtime đã thực hiện đúng như vậy. Trong phân tích chuyên sâu, DBA có thể kiểm tra **cursor plan** và actual row counts/I/O bằng công cụ phù hợp quyền. Trên bảng nhỏ, việc Oracle không dùng index không chứng minh index “sai”.

### 9.4. B-tree index không thay thế tìm toàn văn

Tìm tên bắt đầu bằng một prefix và tìm **một từ nằm ở bất kỳ vị trí** trong nội dung là hai truy vấn khác nhau:

```sql
-- Prefix search: có thể cân nhắc index thích hợp.
WHERE full_name COLLATE VIETNAMESE_AI LIKE 'hoa%'

-- Substring search: thường không tận dụng B-tree range scan đơn giản.
WHERE full_name COLLATE VIETNAMESE_AI LIKE '%hoa%'
```

Nếu tài liệu rất dài hoặc cần tìm từ/cụm từ, phân tách từ tiếng Việt, fuzzy và xếp hạng kết quả, đánh giá **Oracle Text** hoặc dịch vụ search chuyên biệt. Khả năng phân đoạn từ, hỗ trợ tiếng Việt, dấu và mức độ tương đương là đặc tính **của lexer/index/cấu hình tìm kiếm**, không thể suy ra từ việc có `NLS_SORT=VIETNAMESE_AI`.

## 10. Chọn chính sách so sánh theo loại dữ liệu và use case

| Dữ liệu / tình huống | Đặc tính tìm kiếm cần có | Chính sách gợi ý |
| --- | --- | --- |
| UUID, mã hệ thống, token, checksum dạng text | So sánh chính xác, không gộp biến thể | `BINARY`; cân nhắc lưu binary khi thích hợp |
| Username không phân biệt hoa/thường | `Minh` = `minh` nhưng các dấu còn ý nghĩa nếu nghiệp vụ chọn vậy | `BINARY_CI` hoặc collation CI được chọn; kiểm soát unique constraint |
| Họ tên khi hiển thị danh sách tiếng Việt | Sắp xếp theo quy tắc ngôn ngữ | `ORDER BY full_name COLLATE VIETNAMESE` với tie-breaker |
| Tìm tên có nhập sai chữ hoa/thường | Không gộp các tên khác dấu | `VIETNAMESE_CI` |
| Ô tìm tên có tùy chọn “không cần gõ dấu” | Bỏ qua dấu/hoa theo định nghĩa đã thống nhất | Thử `VIETNAMESE_AI` hoặc `BINARY_AI` và bộ test tiếng Việt |
| Địa danh `Hòa Bình`, `Đà Nẵng` | Người dùng có thể nhập không dấu, có khoảng trắng | Collation AI **kết hợp** chuẩn hóa input và quy tắc riêng khi cần |
| Tài liệu nhiều ngôn ngữ | Thứ tự và tương đương đa ngôn ngữ | Đánh giá collation UCA/multilingual theo release |
| Tìm từ trong hàng nghìn tài liệu | Full-text, rank và phân đoạn từ | Oracle Text/giải pháp tìm kiếm chuyên dụng |
| Tìm tên theo gõ gần đúng | Sửa lỗi chính tả, thiếu ký tự, nickname | Fuzzy search riêng, không chỉ collation |
| Xác minh danh tính/kết nối khóa ngoại | Không vô ý gộp hai giá trị pháp lý khác nhau | Khóa kỹ thuật và quy tắc equality/unique có chủ đích |

### 10.1. Mã đăng nhập và họ tên không nên dùng cùng một quy tắc

Giả sử hệ thống có:

```text
account_id = 42
login_code = "minh.nd"
full_name  = "Nguyễn Đức Minh"
```

`LOGIN_CODE` là **định danh đăng nhập**; `FULL_NAME` là **thông tin trình bày và tìm kiếm**. Có thể cần:

- Kiểm tra `LOGIN_CODE` theo chính sách uniqueness nhất quán.
- Hiển thị `FULL_NAME` đúng nguyên gốc người dùng cung cấp.
- Tìm `FULL_NAME` bỏ qua hoa/thường và dấu theo tùy chọn.
- Sắp xếp `FULL_NAME` theo collation tiếng Việt.

Nếu sử dụng một cột `FULL_NAME COLLATE VIETNAMESE_AI UNIQUE` để làm định danh người, tên khác dấu có thể bị xem là trùng. Đó thường không phải nghiệp vụ phù hợp. **Tìm kiếm khoan dung** và **ràng buộc dữ liệu duy nhất** phải được quyết định riêng.

### 10.2. Đặt lựa chọn ở đúng lớp

```text
Người dùng nhập "hoa"
          |
          v
Ứng dụng nhận input + xác thực + chuẩn hóa mức UI
          |
          v
SQL có bind parameter và collation tìm kiếm rõ ràng
          |
          v
Oracle so sánh theo collation, có thể sử dụng index
          |
          v
Trả kết quả + sắp xếp hiển thị theo policy tương ứng
          |
          v
Ứng dụng giữ nguyên tên gốc, không ghi đè thành "hoa"
```

Nếu sản phẩm cho người dùng chọn **“Phân biệt dấu / Không phân biệt dấu”**, có thể chọn giữa **hai câu SQL** hoặc hai expression được thiết kế sẵn, với cùng bind parameter an toàn. Đừng nhận tên collation bất kỳ từ input rồi nối trực tiếp vào SQL: `COLLATE` nhận tên collation ở cú pháp SQL, **không phải nơi tự động bind như một giá trị dữ liệu**. Các lựa chọn phải được kiểm soát theo allowlist.

## 11. Unicode normalization và khoảng trắng: collation không giải quyết toàn bộ

Một ký tự có dấu có thể tồn tại dưới dạng **ký tự Unicode dựng sẵn (precomposed)** hoặc **chuỗi ký tự cơ sở + combining mark (decomposed)**. Ví dụ một chữ `ò` có thể được biểu diễn bằng ký tự đơn hoặc `o` cộng dấu huyền tổ hợp.

Trong một số linguistic/UCA collations, những biểu diễn tương đương theo Unicode được xử lý phù hợp, nhưng **không được mặc định mọi binary comparison hoặc mọi collation đều cho kết quả giống nhau**. Khi phát triển chức năng tìm tên tiếng Việt:

1. Chọn chính sách normalization (thường cân nhắc **NFC**) nhất quán ở biên nhận dữ liệu và indexing nếu nghiệp vụ cần.
2. Bảo toàn giá trị người dùng nhập để hiển thị hoặc audit khi cần, không tự xóa dấu khỏi dữ liệu gốc.
3. Xác định cách xử lý khoảng trắng lặp, khoảng trắng cuối chuỗi, dấu câu, dấu gạch nối và tên có nhiều thành phần.
4. Kiểm tra dữ liệu Unicode thật, trong đó có `ă/â/ê/ô/ơ/ư/đ`, chữ hoa, tổ hợp dấu thanh, và các chuỗi dùng **combining mark**.
5. Nếu dùng thêm một cột/search key được chuẩn hóa bởi ứng dụng, quản lý cách cập nhật và xây dựng lại index khi đổi thuật toán.

Oracle cũng có khác biệt ngữ nghĩa chuỗi giữa `CHAR` và `VARCHAR2` trong xử lý khoảng trắng cuối, và Oracle SQL thường xem chuỗi rỗng `''` là `NULL`. Vì vậy “hai chuỗi có vẻ giống nhau khi nhìn trên UI” không đồng nghĩa mọi kiểu dữ liệu/phép so sánh sẽ trả về bằng nhau.

### Ví dụ tạo dấu tổ hợp để quan sát

Oracle có thể tạo ký tự tổ hợp Unicode bằng `UNISTR`. Ví dụ:

```sql
SELECT
    DUMP('ò', 1016)                         AS precomposed_dump,
    DUMP('o' || UNISTR('\0300'), 1016)      AS decomposed_dump
FROM dual;
```

Hai biểu diễn có thể trông giống nhau khi render nhưng dãy code point khác. Hãy thử so sánh dưới `BINARY`, `VIETNAMESE` và một UCA collation mà release hỗ trợ, rồi ghi nhận kết quả. Đó là cách xác định giới hạn **thực tế** của một quy tắc đã chọn.

## 12. Những lỗi triển khai thường gặp

| Nhận định/hiện tượng | Vì sao có thể sai | Cách xử lý |
| --- | --- | --- |
| “Database dùng `AL32UTF8` nên đã tìm không dấu được.” | Character set quyết định mã hóa, không tự quyết định matching | Dùng collation/phương pháp search phù hợp |
| “Đặt `NLS_SORT=VIETNAMESE_AI` sẽ làm mọi `WHERE =` không phân biệt dấu.” | Với `USING_NLS_COMP`, `NLS_COMP=BINARY` vẫn có thể dùng binary equality | Kiểm tra `NLS_COMP`/declared collation hoặc dùng `COLLATE` explicit |
| “`_CI` cũng bỏ dấu.” | CI chỉ bỏ qua hoa/thường | Dùng AI khi yêu cầu bỏ dấu |
| “`_AI` chỉ bỏ dấu nhưng vẫn phân biệt chữ hoa.” | Oracle `_AI` cũng không phân biệt hoa/thường | Cân nhắc quy tắc custom nếu thật sự cần kết hợp khác |
| “`BINARY_AI` chắc chắn xếp tên theo bảng chữ cái tiếng Việt.” | Binary AI và Vietnamese linguistic sort không cùng mục tiêu | Thử `VIETNAMESE`/`VIETNAMESE_AI` theo use case |
| “`Đ` chắc chắn đồng nhất với `D` trong mọi AI collation.” | Quy tắc một chữ cái riêng không suy ra hoàn toàn từ hậu tố | Thử `d/đ` và tập dữ liệu sản phẩm |
| “Thay `NLS_LANGUAGE` thành Vietnamese là đủ.” | `NLS_LANGUAGE` không phải hợp đồng đầy đủ cho equality/sort của mỗi biểu thức | Chọn `COLLATE` hoặc NLS settings có kiểm soát |
| “Thay session NLS ở một request không ảnh hưởng request khác.” | Connection pool tái sử dụng session | Reset session hoặc dùng collation explicit ở query |
| “Index trên `FULL_NAME` chắc chắn dùng cho `VIETNAMESE_AI`.” | Lingustic comparison có thể cần collation key/expression index | Xem execution plan và tạo index đúng policy |
| “`LIKE '%hoa%'` sẽ nhanh nếu có B-tree index.” | Wildcard đầu thường ngăn range scan thông thường | Cân nhắc full-text/search index phù hợp |
| “`LOWER(name)` giải quyết mọi kiểu case/accent của tiếng Việt.” | Case conversion không đồng nghĩa accent normalization hoặc linguistic collation | Chọn collations và API ngôn ngữ phù hợp |
| “Đổi collation không ảnh hưởng unique key.” | Giá trị từng phân biệt có thể trở nên tương đương | Kiểm kê dữ liệu, constraint, index trước migration |
| “`COLLATION(column)` luôn hiển thị `NLS_SORT` thực tế.” | Hàm cho derived collation; pseudo cần kết hợp session settings | Đọc `USER_TAB_COLS.COLLATION` và NLS session |
| “Search bỏ dấu sẽ tự sửa lỗi chính tả hoặc tìm synonym.” | Collation xử lý so sánh ký tự, không phải hệ thống semantic/fuzzy search | Tạo lớp search riêng nếu sản phẩm yêu cầu |

## 13. Bài tập thực hành có đáp án định hướng

### Bài 1 — So sánh thứ tự

Sau khi tạo `VN_COLLATION_LAB`:

1. Chạy `ORDER BY FULL_NAME COLLATE BINARY, ID`.
2. Chạy `ORDER BY FULL_NAME COLLATE VIETNAMESE, ID`.
3. Chạy `ORDER BY FULL_NAME COLLATE VIETNAMESE_AI, ID`.
4. Ghi lại thứ tự của `An`, `Ân`, `Ăn`, `Dung`, `Dũng`, `Dat` và `Đạt`.
5. Giải thích tại sao một collation AI có thể tạo nhiều **nhóm giá trị tương đương**, và vì sao `ID` là tie-breaker hữu ích.

**Đáp án định hướng:** ba câu query cùng đọc dữ liệu gốc, chỉ khác quy tắc sắp xếp. Nếu một số tên tương đương theo AI, không tự khẳng định chúng có thứ tự cố định khi thiếu khóa phụ.

### Bài 2 — So sánh equality ở ba mức

Viết ba query tìm `anh` bằng `BINARY`, `VIETNAMESE_CI` và `VIETNAMESE_AI`. Sau đó trả lời:

- Vì sao `Anh` và `anh` có thể khớp ở CI nhưng không khớp ở BINARY?
- Vì sao `Ánh` có thể khớp ở AI nhưng không khớp ở CI?
- Nếu hệ thống có người tên `Anh` và người tên `Ánh`, có nên dùng collation AI để quyết định hai người là một không?

**Đáp án định hướng:** CI gộp khác biệt hoa/thường, AI còn gộp khác biệt dấu theo policy; khớp để tìm kiếm **không phải bằng chứng hai record đại diện cùng một con người**.

### Bài 3 — Xác nhận hành vi `d/đ`

Thực hiện query mục 4.4 và ghi lại `VIETNAMESE_AI_RESULT`, `BINARY_AI_RESULT` của môi trường. Tạo thêm thử nghiệm với `Duc` và `Đức`, `Da Nang` và `Đà Nẵng`.

**Đáp án định hướng:** trước khi hứa hẹn UX “gõ không dấu”, phải có bộ test thể hiện đúng kỳ vọng về `đ`, dấu thanh và nguyên âm. Nếu collation không thực hiện chính xác chính sách sản phẩm, cần bổ sung thuật toán khác có kiểm thử, thay vì sửa dữ liệu gốc.

### Bài 4 — Session NLS khác named collation

1. Đọc `NLS_SESSION_PARAMETERS`.
2. Đổi session `NLS_SORT=VIETNAMESE_AI` và `NLS_COMP=BINARY` trong lab.
3. Chạy `WHERE FULL_NAME='anh'`.
4. Đổi `NLS_COMP=LINGUISTIC` và chạy lại.
5. Chạy một query sử dụng `FULL_NAME COLLATE BINARY = 'anh'`.
6. Trả lại NLS settings ban đầu.

**Đáp án định hướng:** với cột `USING_NLS_COMP`, `NLS_COMP` làm thay đổi cách equality dùng session `NLS_SORT`. Explicit `COLLATE BINARY` cho điều kiện cố định và không phụ thuộc lựa chọn linguistic của session.

### Bài 5 — Lựa chọn theo quy tắc nghiệp vụ

Một CRM có ba trường:

```text
CUSTOMER_ID  NUMBER         -- khóa kỹ thuật
LOGIN_CODE   VARCHAR2(60)   -- mã người dùng dùng đăng nhập
FULL_NAME    VARCHAR2(150)  -- tên hiển thị
```

Hãy thiết kế:

1. Chính sách equality và unique cho `LOGIN_CODE`.
2. Cách hiển thị danh sách `FULL_NAME` theo tiếng Việt.
3. Ô tìm tên có hai lựa chọn “Phân biệt dấu” và “Không phân biệt dấu”.
4. Phương án index cho các truy vấn thường xuyên, biết có 5 triệu khách hàng.
5. Bộ dữ liệu kiểm tra các tên `Anh`, `Ánh`, `Đức`, `Duc`, `Hòa`, `Hoa` và chữ Unicode tổ hợp.

**Đáp án định hướng:** dùng khóa kỹ thuật cho identity, định nghĩa rõ ràng uniqueness của login, dùng collation linguistic cho hiển thị, CI/AI có chọn lọc cho tìm kiếm và đánh giá index bằng workload thực. Đừng gán unique accent-insensitive trên toàn bộ họ tên.

### Bài 6 — Phân biệt prefix và full-text

Viết câu SQL tìm tên bắt đầu bằng `hoa` và một câu tìm `hoa` xuất hiện ở giữa tên. Giải thích sự khác nhau về khả năng dùng B-tree range scan. Khi tìm nhiều trang văn bản tiếng Việt, đề xuất hướng dùng Oracle Text và những hành vi cần kiểm thử với lexer/index.

### Dọn lab

Chỉ chạy trong schema học tập và sau khi đã hoàn tất các bài tập:

```sql
DROP TABLE vn_collation_lab PURGE;

-- Chỉ drop nếu chính bạn đã tạo trong môi trường
-- có data-bound collation.
DROP TABLE vn_profile_collated PURGE;
DROP TABLE vn_account_ci PURGE;
```

Nếu không tạo hai bảng tùy chọn vì môi trường không bật data-bound collation, **không chạy hai lệnh DROP tương ứng**. `PURGE` bỏ qua recycle bin; không dùng đối với bảng cần khôi phục.

## 14. Tổng kết cách áp dụng

Khi xử lý văn bản tiếng Việt trong Oracle, hãy tách bốn quyết định:

1. **Lưu được dữ liệu gốc:** character set Unicode và xử lý encoding chính xác từ client đến database.
2. **Sắp xếp cho người đọc:** đánh giá linguistic collation `VIETNAMESE` và thêm tie-breaker trong `ORDER BY`.
3. **Tìm kiếm theo kỳ vọng:** dùng case-insensitive (`_CI`) hoặc case-and-accent-insensitive (`_AI`) khi phù hợp, kiểm thử riêng các trường hợp tiếng Việt như `ă/â/ơ/ư/đ` và Unicode normalization.
4. **Bảo đảm tính đúng của dữ liệu:** thiết kế PK/unique/FK và index có chủ đích; không lấy quy tắc tìm kiếm dễ dãi để quyết định identity hoặc trùng lặp pháp lý.

Về mặt kỹ thuật, `NLS_SORT`/`NLS_COMP` giúp điều khiển các phép toán dùng session collation; `COLLATE` giúp biểu thức SQL có chính sách rõ ràng; `NLSSORT` biểu diễn collation key và hỗ trợ các tình huống index; data-bound collation đưa quy tắc xuống cột/bảng nhưng đòi điều kiện cấu hình và cân nhắc constraint/index. Đó là các công cụ để thực thi **một quyết định nghiệp vụ được định nghĩa trước**.

## Tài liệu Oracle để tra cứu

- [Oracle Database Globalization Support Guide — Linguistic Sorting and Matching (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/linguistic-sorting-and-matching.html) — binary, monolingual, UCA, case/accent sensitivity, data-bound collation, linguistic index.
- [Oracle Database Globalization Support Guide — Locale Data (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/appendix-A-locale-data.html) — danh sách các linguistic collations, gồm `VIETNAMESE`.
- [Oracle Database Globalization Support Guide — SQL and PL/SQL Programming in a Global Environment (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/sql-and-plsql-programming-in-global-environment.html) — tác động của `NLS_COMP`/`NLS_SORT`, `ORDER BY` và điều kiện so sánh.
- [Oracle Database SQL Language Reference — COLLATION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COLLATION.html) — derived collation của biểu thức.
- [Oracle Database SQL Language Reference — NLSSORT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NLSSORT.html) — collation key, tham số `NLS_SORT` và giới hạn.
- [Oracle Database SQL Language Reference — CREATE TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html) — `COLLATE` cột, default collation và điều kiện `MAX_STRING_SIZE=EXTENDED`.
- [Oracle Database Reference — ALL_TAB_COLS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_TAB_COLS.html) — xem metadata `COLLATION` của cột.

Mọi ví dụ về kết quả tương đương, đặc biệt với **`đ/Đ`, dấu tiếng Việt và các biến thể Unicode**, cần xác nhận trên chính Oracle release, character set và policy sản phẩm đang sử dụng trước khi áp vào tìm kiếm hoặc unique constraint của ứng dụng thật.
