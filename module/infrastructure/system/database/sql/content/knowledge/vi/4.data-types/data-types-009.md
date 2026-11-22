# Dữ liệu nhị phân, UUID và định danh đặc thù trong SQL

Không phải dữ liệu nào trong cơ sở dữ liệu quan hệ cũng là chữ, số hay ngày tháng. Ứng dụng còn cần lưu **chuỗi byte** (ảnh, chữ ký số, tài liệu, mã băm), nhận diện bản ghi bằng **UUID**, và đôi khi sử dụng các kiểu định danh được sinh theo thời gian, theo máy hoặc theo quy tắc nghiệp vụ riêng. Chọn kiểu lưu trữ phù hợp sẽ ảnh hưởng đến tính đúng đắn, dung lượng, khả năng truy vấn, hiệu năng chỉ mục và tính tương thích giữa các hệ quản trị cơ sở dữ liệu (DBMS).

Bài học tập trung vào ba câu hỏi:

1. **Dữ liệu nhị phân** khác dữ liệu chuỗi ký tự và chuỗi bit như thế nào; lưu và đọc byte trong SQL ra sao?
2. **UUID** có cấu trúc gì, được sinh thế nào, lưu bằng kiểu nào và nên dùng làm khóa trong trường hợp nào?
3. **Định danh đặc thù** như số tự tăng, sequence, ULID, Snowflake ID, mã băm hay định danh vị trí hàng có vai trò gì và có thể thay thế cho nhau không?

Ví dụ SQL chính sử dụng **PostgreSQL**. Các bảng đối chiếu giới thiệu cách biểu diễn tương ứng trong MySQL, SQL Server và Oracle, bởi tên kiểu dữ liệu và hàm sinh định danh khác nhau theo DBMS và phiên bản.

## 1. Phân biệt byte, văn bản và định danh

Hãy tưởng tượng hệ thống quản lý tài liệu: mỗi tệp có tên, loại MIME, nội dung và một mã để tham chiếu. Bốn thông tin có bản chất khác nhau:

| Dữ liệu | Ví dụ | Kiểu lưu trữ thích hợp |
| --- | --- | --- |
| Tên tệp | `hop_dong.pdf` | Kiểu chuỗi văn bản như `VARCHAR` hoặc `TEXT`. |
| Loại nội dung | `application/pdf` | Chuỗi văn bản. |
| Nội dung tệp | Các byte `25 50 44 46 ...` của một tệp PDF | Kiểu nhị phân như `BYTEA`, `VARBINARY`, `BLOB`. |
| Mã nhận diện tệp | `550e8400-e29b-41d4-a716-446655440000` | Kiểu `UUID` chuyên dụng nếu DBMS hỗ trợ, hoặc biểu diễn tương đương. |

**Byte** là đơn vị gồm 8 bit, có giá trị từ 0 đến 255. Dữ liệu nhị phân là một dãy byte tùy ý, có thể chứa `00`, `FF` và nhiều giá trị không phải ký tự có nghĩa trong một bảng mã văn bản.

**Văn bản** là chuỗi ký tự được biểu diễn bằng một bộ mã (thường là UTF-8 ở tầng trao đổi dữ liệu). Một chuỗi văn bản và một dãy byte có thể liên quan qua thao tác mã hóa/giải mã, nhưng không phải cùng một kiểu về mặt ngữ nghĩa.

**Định danh** là giá trị dùng để xác định hoặc tham chiếu một thực thể. UUID cũng có 16 byte về mặt biểu diễn nhị phân, song **không nên coi UUID chỉ là một khối byte tùy ý**: nó có cấu trúc, quy tắc biểu diễn và ý nghĩa định danh riêng.

## 2. Dữ liệu nhị phân: kiểu BINARY, VARBINARY, BLOB, BYTEA

Các DBMS cung cấp những kiểu dữ liệu dành cho byte, nhưng tên gọi và giới hạn không đồng nhất:

| Hệ quản trị | Kiểu nhị phân thường gặp | Ghi chú |
| --- | --- | --- |
| **PostgreSQL** | `BYTEA` | Dãy byte có độ dài biến đổi; còn có cơ chế *large object* riêng cho các trường hợp đặc thù. |
| **MySQL** | `BINARY(n)`, `VARBINARY(n)`, `TINYBLOB`, `BLOB`, `MEDIUMBLOB`, `LONGBLOB` | `BINARY(n)` có độ dài cố định và có quy tắc đệm; các loại BLOB khác nhau về giới hạn dung lượng. |
| **SQL Server** | `BINARY(n)`, `VARBINARY(n)`, `VARBINARY(MAX)` | `VARBINARY(MAX)` phục vụ chuỗi byte lớn; `IMAGE` là kiểu cũ nên tránh trong thiết kế mới. |
| **Oracle Database** | `RAW(n)`, `BLOB` | `RAW` cho chuỗi byte trong giới hạn loại cột; `BLOB` lưu đối tượng nhị phân lớn. |

### 2.1. Độ dài cố định và độ dài biến đổi

- **Kiểu cố định** như `BINARY(16)` phù hợp khi mỗi giá trị cần đúng 16 byte, chẳng hạn biểu diễn UUID thô trong một số DBMS. Tùy hệ quản trị, giá trị thiếu byte có thể được đệm, vì thế không nên dùng kiểu cố định một cách máy móc cho tệp có kích thước khác nhau.
- **Kiểu biến đổi** như `VARBINARY(n)` hoặc `BYTEA` phù hợp khi mỗi giá trị có kích thước khác nhau.
- **BLOB** (*Binary Large Object*) thường được dùng cho dữ liệu nhị phân lớn. Đọc/ghi BLOB có thể cần API truyền dữ liệu dạng luồng và có hành vi lưu trữ riêng.

Giới hạn `n`, kích thước tối đa một giá trị, cách ghi log và cách đặt dữ liệu trong/ngoài trang lưu trữ phải tra theo **DBMS và phiên bản cụ thể**. Không có một từ khóa `BLOB` với cùng hành vi trên tất cả các hệ quản trị.

### 2.2. Chuỗi bit không phải chuỗi byte

Một số DBMS có kiểu **bit string**, ví dụ `BIT(n)` hoặc `BIT VARYING` trong PostgreSQL, để lưu các dãy bit `0`/`1` dùng làm cờ hoặc mặt nạ. Cần phân biệt:

- `BIT(8)`: biểu diễn 8 bit có ý nghĩa như bit.
- `BYTEA`: biểu diễn một hoặc nhiều **byte nguyên vẹn**.
- `BOOLEAN`: biểu diễn trạng thái logic đúng/sai, có thể có `NULL`.

Tên kiểu `BIT` cũng có ý nghĩa khác nhau theo DBMS; ví dụ `BIT` của SQL Server thường dùng như giá trị boolean. Khi lưu tệp, mã băm, khóa mật mã hoặc dữ liệu giao thức, kiểu byte thường phù hợp hơn kiểu bit.

### 2.3. Hex và Base64 là cách **biểu diễn** byte

Dữ liệu nhị phân có thể được **hiển thị** dưới dạng:

- **Hex (hệ thập lục phân):** mỗi byte thành hai ký tự `0`–`9`, `a`–`f`. Ví dụ ba byte `00 FF 10` thành chuỗi `00ff10`.
- **Base64:** gom byte thành chuỗi ký tự ASCII an toàn cho nhiều kênh văn bản, chẳng hạn JSON. Ba byte `00 FF 10` thành `AP8Q`.
- **Chuỗi ký tự theo encoding:** chỉ hợp lý khi dãy byte thực sự mã hóa văn bản theo một encoding đã biết.

Hex cần **hai ký tự cho mỗi byte**; Base64 thường tăng kích thước biểu diễn khoảng **33%** trước khi xét ký tự đệm và chi tiết truyền tải. Đây là **cách mã hóa để biểu diễn/truyền dữ liệu**, không phải kiểu dữ liệu nhị phân tự thân, cũng không phải nén hay mã hóa bảo mật.

Ví dụ PostgreSQL:

~~~sql
SELECT
    decode('00FF10', 'hex') AS du_lieu_nhi_phan,
    octet_length(decode('00FF10', 'hex')) AS so_byte,
    encode(decode('00FF10', 'hex'), 'hex') AS dang_hex,
    encode(decode('00FF10', 'hex'), 'base64') AS dang_base64;
~~~

Hàm `decode(..., 'hex')` chuyển **chuỗi hex** thành `BYTEA`. Hàm `encode(..., 'hex')` hoặc `encode(..., 'base64')` chuyển byte sang dạng văn bản để hiển thị. `octet_length` đếm số **byte**, không phải số ký tự trong bản hex/Base64. Với ba byte mẫu trên, `so_byte` là `3`, `dang_hex` là `00ff10`, `dang_base64` là `AP8Q`.

Một hệ thống có thể hiển thị byte dưới dạng `\\x00ff10` trong công cụ truy vấn PostgreSQL. Tiền tố `\\x` thuộc **cách hiển thị hexadecimal của `BYTEA`**, không phải hai byte bổ sung trong dữ liệu gốc.

## 3. Thực hành PostgreSQL: lưu và truy vấn dữ liệu nhị phân

Giả sử ứng dụng cần lưu một lượng nhỏ tệp đính kèm ngay trong database. Ta thiết kế bảng:

~~~sql
CREATE TABLE tep_dinh_kem (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ten_tep TEXT NOT NULL,
    loai_mime TEXT NOT NULL,
    noi_dung BYTEA NOT NULL,
    ma_bam_sha256 BYTEA,
    CONSTRAINT ck_ma_bam_32_byte
        CHECK (
            ma_bam_sha256 IS NULL
            OR octet_length(ma_bam_sha256) = 32
        )
);
~~~

Trong ví dụ này:

- `id UUID` là mã bản ghi có kiểu UUID chuyên dụng, sẽ được phân tích ở phần tiếp theo.
- `DEFAULT gen_random_uuid()` để PostgreSQL sinh UUID ngẫu nhiên cho bản ghi nếu không truyền `id`. Hàm này có sẵn trong PostgreSQL hiện đại (PostgreSQL 13 trở lên); bản cũ có thể cần extension phù hợp.
- `noi_dung BYTEA` lưu các byte của tệp, không cố biến byte thành ký tự.
- `ma_bam_sha256 BYTEA` dành cho **giá trị băm SHA-256 dài 32 byte** nếu ứng dụng tính và lưu mã băm. Ràng buộc chỉ kiểm tra độ dài, **không chứng minh mã băm tương ứng với nội dung**.

Chèn một dãy byte mẫu:

~~~sql
INSERT INTO tep_dinh_kem (ten_tep, loai_mime, noi_dung)
VALUES (
    'chu_ky_png.bin',
    'application/octet-stream',
    decode('89504E470D0A1A0A', 'hex')
)
RETURNING id, octet_length(noi_dung) AS kich_thuoc_byte;
~~~

Chuỗi hex trên là **8 byte chữ ký đầu tệp PNG**, chỉ dùng để minh họa lưu byte; **nó không phải một tệp ảnh PNG hoàn chỉnh**. Vì vậy ví dụ đặt tên `chu_ky_png.bin` và loại MIME `application/octet-stream`, thay vì khẳng định đã lưu một ảnh hợp lệ. Câu lệnh `RETURNING` trả về UUID được sinh và kích thước `8` byte.

Đọc metadata và một phần dữ liệu dưới dạng hex:

~~~sql
SELECT
    id,
    ten_tep,
    loai_mime,
    octet_length(noi_dung) AS kich_thuoc_byte,
    encode(substring(noi_dung FROM 1 FOR 8), 'hex') AS tam_byte_dau
FROM tep_dinh_kem;
~~~

Trong PostgreSQL, `substring` trên `BYTEA` thao tác theo byte, còn `encode` trả về một chuỗi có thể hiển thị. Để lấy **toàn bộ tệp thực**, ứng dụng thường đọc cột nhị phân bằng API của driver dưới dạng mảng byte hoặc stream; không cần chuyển toàn bộ sang hex chỉ để đưa dữ liệu trở lại ứng dụng.

### 3.1. Khi nào lưu trực tiếp tệp trong DB?

**Lưu trực tiếp bằng `BYTEA`/BLOB** có thể thuận tiện khi nội dung nhỏ hoặc vừa, cần sao lưu và giao dịch cùng metadata, kiểm soát truy cập qua cơ sở dữ liệu và triển khai đơn giản.

Với **tệp rất lớn, số lượng lớn hoặc luồng phát nội dung chuyên biệt**, một kiến trúc khác là đặt tệp trong object storage và lưu trong SQL các trường `id`, `storage_key`, `ten_tep`, `kich_thuoc`, `ma_bam`, `loai_mime`. Khi đó cần thiết kế riêng cho quyền truy cập, cập nhật đồng bộ, xóa mồ côi, sao lưu và khôi phục; giao dịch database không tự động commit/rollback dữ liệu ở object storage.

Việc lựa chọn phụ thuộc kích thước, lưu lượng, chính sách sao lưu, nhu cầu truy vấn và hạ tầng hiện có. **BLOB không mặc nhiên là lựa chọn sai**, nhưng cũng không có nghĩa mọi tệp nên đặt trong một cột BLOB.

## 4. UUID: định danh 128 bit

**UUID (Universally Unique Identifier)** là một giá trị định danh gồm **128 bit = 16 byte**. Quy ước biểu diễn phổ biến là 32 chữ số hex chia thành các nhóm `8-4-4-4-12`:

~~~text
550e8400-e29b-41d4-a716-446655440000
|------|----|----|----|------------|
   8    4    4    4       12  chữ số hex
~~~

Các dấu gạch nối giúp con người đọc UUID dễ hơn; chúng **không làm UUID trở thành dữ liệu dài hơn 128 bit**. Chuỗi hiển thị chuẩn có 36 ký tự (32 chữ số hex và 4 dấu `-`), trong khi giá trị nhị phân chỉ có 16 byte. Dung lượng thực tế của cột và chỉ mục còn phụ thuộc cấu trúc lưu trữ của DBMS.

UUID được chuẩn hóa trong RFC 9562 (thay thế RFC 4122 cho phiên bản hiện hành của đặc tả). UUID giúp nhiều máy hoặc dịch vụ **tự sinh định danh** mà không cần cùng xin một bộ đếm tăng dần từ một máy chủ trung tâm. Nó làm xác suất trùng cực nhỏ khi sinh đúng cách, **không tạo bảo đảm toán học rằng mọi UUID trên thế giới đều duy nhất**.

### 4.1. Những phiên bản UUID cần biết

| Phiên bản | Nguyên tắc sinh | Điểm đáng chú ý |
| --- | --- | --- |
| **UUIDv1** | Dựa vào thời gian và thông tin nút/máy cùng các thành phần khác. | Có yếu tố thời gian; có thể làm lộ metadata tùy cách sinh, nên thận trọng. |
| **UUIDv3** | Tính từ namespace + tên bằng MD5. | Cùng namespace và tên cho cùng kết quả; không phù hợp nếu cần tính bảo mật của mã băm. |
| **UUIDv4** | Chủ yếu là bit ngẫu nhiên. | Phổ biến, không cần bộ cấp số trung tâm; cần nguồn ngẫu nhiên tốt. |
| **UUIDv5** | Tính từ namespace + tên bằng SHA-1. | Hữu ích cho định danh có tính tái lập; SHA-1 không nên dùng cho yêu cầu chống va chạm mật mã mạnh. |
| **UUIDv6** | Sắp xếp lại thành phần thời gian từ mô hình v1. | Hướng đến khả năng sắp thứ tự tốt hơn. |
| **UUIDv7** | Có phần timestamp theo Unix milliseconds và phần còn lại theo quy tắc sinh của v7. | Có xu hướng tăng theo thời gian, thuận lợi hơn cho nhiều kiểu chỉ mục. |
| **UUIDv8** | Định dạng dành cho cơ chế sinh tùy biến. | Cần hiểu quy tắc riêng của bên tạo, không thể suy mọi tính chất chỉ từ tên phiên bản. |

Trong thực tế, **v4** và **v7** thường là hai lựa chọn đáng cân nhắc:

- **v4**: phù hợp khi cần định danh độc lập, khó dự đoán khi sinh bằng nguồn ngẫu nhiên tốt và không quan tâm thứ tự thời gian của khóa.
- **v7**: phù hợp khi muốn định danh có khuynh hướng được sắp xếp theo thời gian tạo, giúp giảm hiện tượng chèn ngẫu nhiên vào nhiều vị trí của chỉ mục B-tree so với v4.

UUIDv7 **không thay thế một cột thời gian nghiệp vụ**. Timestamp trong định danh có độ phân giải, nguồn đồng hồ và quy tắc sinh riêng; đồng hồ có thể lệch và nhiều UUID có thể được sinh trong cùng mili giây. Để lập báo cáo theo thời điểm tạo thực tế, vẫn nên lưu cột `created_at`/thời điểm giao dịch riêng.

### 4.2. UUID không phải cơ chế cấp quyền

Một UUID v4 có thể khó đoán khi sinh bằng bộ tạo ngẫu nhiên thích hợp, nhưng **“khó đoán URL” không đồng nghĩa “được quyền truy cập”**. API vẫn phải kiểm tra xác thực, phân quyền và ranh giới dữ liệu của người dùng. UUIDv7 bộc lộ thông tin thời gian tạo trong bản thân giá trị; cả v4 lẫn v7 đều không nên được xem là bí mật hay token truy cập lâu dài.

## 5. Lưu và sinh UUID trong SQL

### 5.1. PostgreSQL: sử dụng kiểu UUID chuyên dụng

Ví dụ bảng có khóa chính UUID:

~~~sql
CREATE TABLE phieu_yeu_cau (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tieu_de TEXT NOT NULL,
    thoi_diem_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO phieu_yeu_cau (tieu_de)
VALUES ('Yeu cau ho tro')
RETURNING id, thoi_diem_tao;
~~~

Cột `id` là kiểu `UUID`, không phải `VARCHAR(36)`. PostgreSQL nhận nhiều cách viết đầu vào hợp lệ của UUID rồi lưu dưới dạng UUID nội bộ; khi trả kết quả, hệ quản trị trình bày theo định dạng UUID quen thuộc.

Lọc theo UUID:

~~~sql
-- Thay UUID mẫu bằng id thực tế mà INSERT ... RETURNING trả về.
SELECT id, tieu_de
FROM phieu_yeu_cau
WHERE id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
~~~

Nếu không có bản ghi mang UUID ví dụ, truy vấn chỉ trả về **0 dòng**. Ép kiểu `::uuid` trong PostgreSQL làm rõ ý nghĩa của giá trị so sánh; ở ứng dụng thật, nên bind tham số UUID qua driver/ORM.

Việc **sinh UUID** có thể thực hiện ở DB hoặc ứng dụng:

- Sinh tại **DB** bằng `DEFAULT gen_random_uuid()`: mọi luồng ghi vào bảng có cùng giá trị mặc định, tiện khi thao tác SQL trực tiếp.
- Sinh tại **ứng dụng**: dịch vụ biết ID trước khi lưu, thuận tiện khi cần dùng ID cho sự kiện, đối tượng liên quan hoặc thao tác phân tán.

Không bắt buộc phải chọn một cách cho mọi bảng, nhưng cần tránh để hai bên sinh giá trị mà ứng dụng không xác định nguồn sự thật và cách xử lý khi có trùng khóa.

### 5.2. So sánh biểu diễn UUID theo DBMS

| Hệ quản trị | Kiểu nên cân nhắc | Hàm/cơ chế thường gặp |
| --- | --- | --- |
| **PostgreSQL** | `UUID` | `gen_random_uuid()` để sinh UUID ngẫu nhiên; tính năng UUID khác có thể phụ thuộc phiên bản/extension. |
| **MySQL** | `BINARY(16)` hoặc `CHAR(36)` | `UUID()`, `UUID_TO_BIN()`, `BIN_TO_UUID()` trên phiên bản hỗ trợ. |
| **SQL Server** | `UNIQUEIDENTIFIER` | `NEWID()`, `NEWSEQUENTIALID()` (có điều kiện sử dụng riêng, điển hình trong `DEFAULT`). |
| **Oracle Database** | Thường dùng `RAW(16)` hoặc biểu diễn chuỗi theo yêu cầu ứng dụng | `SYS_GUID()` trả về `RAW(16)`; không nên mặc định mọi kết quả có tính chất phiên bản UUID như v4/v7. |

**Ví dụ MySQL 8.0+** lưu UUID bằng 16 byte:

~~~sql
CREATE TABLE yeu_cau_mysql (
    id BINARY(16) PRIMARY KEY,
    tieu_de VARCHAR(200) NOT NULL
);

INSERT INTO yeu_cau_mysql (id, tieu_de)
VALUES (UUID_TO_BIN(UUID()), 'Yeu cau ho tro');

SELECT BIN_TO_UUID(id) AS id_hien_thi, tieu_de
FROM yeu_cau_mysql;
~~~

MySQL có tham số tùy chọn **`swap_flag`** của `UUID_TO_BIN`/`BIN_TO_UUID` để biến đổi vị trí một số byte nhằm phục vụ kiểu UUID có bố cục thời gian tương ứng (đặc biệt trường hợp UUIDv1). Nếu dùng cờ này thì thao tác chuyển đi/chuyển về phải **nhất quán**. Không tự bật cờ cho UUIDv4, UUIDv7 hoặc dữ liệu đã có mà chưa hiểu định dạng, vì giá trị có thể bị giải mã không đúng UUID gốc.

**Ví dụ SQL Server**:

~~~sql
CREATE TABLE dbo.yeu_cau_sqlserver (
    id UNIQUEIDENTIFIER NOT NULL
        CONSTRAINT df_yeu_cau_id DEFAULT NEWID(),
    tieu_de NVARCHAR(200) NOT NULL,
    CONSTRAINT pk_yeu_cau_sqlserver PRIMARY KEY (id)
);
~~~

`NEWSEQUENTIALID()` có thể giảm vấn đề chèn khóa ngẫu nhiên ở một số trường hợp nhưng có giới hạn vị trí sử dụng và tính dự đoán; không nên coi nó là hàm thay thế tùy ý cho `NEWID()`.

**Ví dụ Oracle** (mẫu dùng `RAW(16)`):

~~~sql
CREATE TABLE yeu_cau_oracle (
    id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    tieu_de VARCHAR2(200) NOT NULL
);
~~~

Kiểu dữ liệu, hàm UUID và cách hiển thị/so sánh UUID thay đổi giữa DBMS. Đặc biệt, **thứ tự sắp xếp của UUID** qua các hàm so sánh/collation của một DBMS không nhất thiết trùng với việc sắp xếp chuỗi UUID chuẩn hay so sánh từng byte theo RFC. Nếu ứng dụng dựa vào thứ tự thời gian của UUIDv7, cần xác nhận cách DBMS và driver lưu, chuyển đổi và `ORDER BY`.

### 5.3. UUID dạng chuỗi hay 16 byte?

| Tiêu chí | Kiểu UUID/nhị phân 16 byte | `CHAR(36)`/`VARCHAR(36)` chứa UUID |
| --- | --- | --- |
| Ý nghĩa kiểu | `UUID` chuyên dụng có kiểm tra định dạng; `BINARY(16)` chỉ là byte, cần quy ước chuyển đổi | Văn bản; có thể chứa giá trị sai định dạng nếu thiếu ràng buộc. |
| Dung lượng giá trị | 16 byte dữ liệu định danh (chưa tính overhead cột/chỉ mục) | 36 ký tự định dạng chuẩn; dung lượng byte thực tế tùy charset/kiểu/collation. |
| So sánh và chỉ mục | Thường gọn hơn cách biểu diễn văn bản; cách sắp xếp phụ thuộc DBMS | Có thể chịu ảnh hưởng quy tắc so sánh chuỗi/collation. |
| Khả năng đọc bằng mắt | Cần chuyển thành chuỗi ở công cụ hoặc driver | Có thể đọc ngay dạng `8-4-4-4-12`. |
| Tính phù hợp | Ưu tiên kiểu `UUID` khi DBMS hỗ trợ; `BINARY(16)` khi thiết kế quy ước chuyển đổi rõ | Hữu ích ở hệ thống tương thích cũ hoặc công cụ chỉ hỗ trợ văn bản. |

**Tối ưu hóa không chỉ là chọn kiểu 16 byte**. Khóa UUID ngẫu nhiên trên chỉ mục B-tree còn có thể khiến chèn dữ liệu phân tán hơn số tự tăng. UUIDv7 có thể giúp tăng tính cục bộ của bản ghi mới, nhưng hiệu quả thực tế phụ thuộc kích thước bảng, kiến trúc chỉ mục, tình huống ghi và cách DBMS tổ chức dữ liệu. Cần đo theo workload thay vì khẳng định mọi UUID đều chậm hoặc mọi UUIDv7 đều nhanh.

## 6. “Định danh đặc thù” là gì?

Ngoài UUID, hệ thống còn dùng những định danh có đặc tính khác nhau về **phạm vi duy nhất**, **khả năng tự sinh**, **thứ tự**, **kích thước** và **mục đích**:

| Loại định danh | Ý tưởng | Trường hợp phù hợp | Điều cần lưu ý |
| --- | --- | --- | --- |
| **Số nguyên tự tăng / IDENTITY** | DB cấp một số theo cơ chế sinh số | Khóa nội bộ, bảng có nhiều truy vấn/quan hệ | Thường cần DB/sequence cấp số; ID có thể bị đoán; không bảo đảm liên tục. |
| **Sequence** | Đối tượng cấp số theo quy tắc riêng | Phân phối số dùng chung nhiều bảng/luồng, thiết kế linh hoạt | Có thể có khoảng trống do rollback/cache; không phải đồng hồ thời gian. |
| **UUIDv4/v7** | Định danh 128 bit với cách sinh theo phiên bản | Nhiều dịch vụ tự sinh, khóa công khai, đồng bộ dữ liệu | Lớn hơn số nguyên phổ biến; không phải quyền truy cập. |
| **ULID** | Định danh 128 bit với thời gian và phần ngẫu nhiên; hay biểu diễn Base32 26 ký tự | Cần ID dễ trao đổi bằng text và có xu hướng sắp theo thời gian | Không phải kiểu SQL chuẩn phổ biến; tính thứ tự còn phụ thuộc cách sinh/collation. |
| **Snowflake-style ID** | ID số thường khoảng 64 bit ghép thời gian, định danh nút và sequence | Phát ID phân tán với kích thước gọn, có thứ tự tương đối | Phải quản lý node ID, đồng hồ và quy tắc khi tràn bộ đếm; không có một chuẩn Snowflake SQL thống nhất. |
| **Khóa tự nhiên / khóa ghép** | Dựa trên thuộc tính nghiệp vụ hoặc nhiều cột | Dữ liệu có tổ hợp duy nhất, ổn định | Quy tắc nghiệp vụ có thể đổi, độ rộng khóa ngoại có thể lớn. |
| **Mã băm nội dung** | Tính fingerprint từ dữ liệu, ví dụ SHA-256 | Kiểm tra toàn vẹn, deduplication, tham chiếu theo nội dung | Cùng nội dung cho cùng mã; không mô tả danh tính nghiệp vụ; va chạm lý thuyết vẫn có thể. |
| **Row locator / version token** | Giá trị nội bộ của DBMS để tìm/vet phiên bản hàng | Tối ưu nội bộ, hỗ trợ concurrency theo DBMS | Không nên mặc định làm khóa nghiệp vụ bền vững. |

Các lựa chọn này **không tương đương** chỉ vì đều có thể đặt trong cột `PRIMARY KEY`. Chẳng hạn, số tự tăng chỉ cần duy nhất trong phạm vi do DB cấp; UUID có thể được sinh độc lập trên nhiều máy; mã băm gắn với **nội dung** chứ không nhất thiết với **một bản ghi**.

### 6.1. Số tự tăng và sequence

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten TEXT NOT NULL
);

INSERT INTO khach_hang (ho_ten)
VALUES ('Nguyen Van A')
RETURNING id;
~~~

`GENERATED ALWAYS AS IDENTITY` biểu thị cột được cấp giá trị tự động theo cơ chế identity. MySQL thường dùng `AUTO_INCREMENT`; SQL Server dùng `IDENTITY`; Oracle và PostgreSQL cũng có cơ chế identity/sequence. Cú pháp và quyền sửa trực tiếp giá trị tùy hệ quản trị.

**Không dùng số tự tăng như cam kết số thứ tự không có lỗ hổng.** Sequence có thể cấp số rồi giao dịch rollback, cache có thể mất số khi hệ thống khởi động lại, hoặc ứng dụng chủ động bỏ một mã. Số tăng liên tục cũng không bảo đảm phản ánh tuyệt đối thứ tự **commit** của các giao dịch chạy song song.

### 6.2. Khóa tự nhiên, khóa thay thế và khóa ghép

Một hệ thống đăng ký học phần có thể cần duy nhất cặp sinh viên–môn học:

~~~sql
CREATE TABLE dang_ky_mon_hoc (
    sinh_vien_id BIGINT NOT NULL,
    mon_hoc_id BIGINT NOT NULL,
    ngay_dang_ky DATE NOT NULL DEFAULT CURRENT_DATE,
    PRIMARY KEY (sinh_vien_id, mon_hoc_id)
);
~~~

Cặp `(sinh_vien_id, mon_hoc_id)` là **khóa ghép**. Thiết kế này phù hợp nếu nghiệp vụ không cho đăng ký cùng môn hai lần trong bảng; nếu cần ghi lịch sử nhiều lần đăng ký, khóa ghép đó không còn phù hợp với phạm vi duy nhất và phải thay đổi mô hình.

Có thể dùng một khóa thay thế `id` (BIGINT/UUID) và giữ ràng buộc `UNIQUE (sinh_vien_id, mon_hoc_id)` khi quy tắc nghiệp vụ vẫn yêu cầu không trùng cặp. **Một khóa thay thế tự sinh không thay thế được các ràng buộc duy nhất quan trọng của nghiệp vụ.**

### 6.3. ULID và Snowflake ID

**ULID** thường gồm 128 bit: phần thời gian tính bằng mili giây và phần ngẫu nhiên; bản biểu diễn thông dụng dài 26 ký tự theo bảng chữ cái Base32 của ULID. Nó hữu ích khi muốn ID có thể được đọc/truyền bằng chuỗi và có xu hướng sắp theo thời gian. Tuy nhiên, không phải mọi DBMS đều có kiểu hoặc hàm `ULID` tích hợp; thường cần thư viện ứng dụng, extension hoặc lưu theo định dạng được thống nhất.

**Snowflake-style ID** thường đóng gói timestamp, mã máy/nút và số thứ tự trong một số nguyên. Nó nhỏ gọn hơn UUID 128 bit và có thể sinh phân tán, nhưng yêu cầu **đồng bộ quy tắc cấp node**, xử lý trùng node, đồng hồ đi lùi và giới hạn số ID tạo trong một đơn vị thời gian. Hai hệ thống đều gọi ID của mình là “Snowflake” chưa chắc dùng cùng cấu trúc bit hay cùng cách giải mã.

Khi lưu ULID/Snowflake trong SQL:

- ULID có thể được lưu dưới dạng chuỗi có collation nhất quán hoặc nhị phân 16 byte theo định dạng mà thư viện của ứng dụng quy định.
- Snowflake ID thường phù hợp với `BIGINT`, nhưng phải xác nhận giá trị nằm trong dải số nguyên có dấu và cách các ngôn ngữ/ứng dụng truyền số lớn. Chẳng hạn JavaScript `Number` không biểu diễn chính xác mọi số nguyên 64 bit; ở API có thể cần truyền ID dạng chuỗi.

### 6.4. Mã băm có thể là dấu vân tay dữ liệu, chưa chắc là ID bản ghi

Với tệp đính kèm, ta có thể tính:

~~~text
sha256(noi_dung_tep) -> 32 byte mã băm
~~~

Nếu hai bản ghi có byte nội dung hoàn toàn giống nhau, chúng có cùng mã băm SHA-256. Điều này có ích cho kiểm tra toàn vẹn hoặc nhận diện nội dung trùng, nhưng **không có nghĩa hai bản ghi có cùng quyền truy cập, chủ sở hữu hay vòng đời**. Một bản ghi có thể cần UUID độc lập, trong khi `ma_bam_sha256` chỉ là metadata bổ sung. Dùng mã băm để so khớp tệp cần tính đúng trên byte gốc; so sánh chuỗi Base64 hay thay đổi encoding trước khi băm có thể làm sai ý định.

### 6.5. Định danh hàng nội bộ và token phiên bản

Một vài DBMS có kiểu/giá trị đặc biệt:

- **PostgreSQL `ctid`:** vị trí vật lý của một phiên bản hàng; có thể thay đổi khi cập nhật và tái tổ chức bảng. Không thích hợp làm ID ổn định cho API hoặc khóa nghiệp vụ.
- **Oracle `ROWID`:** định vị hàng trong cơ chế lưu trữ tương ứng; có thể hữu ích trong truy cập nội bộ nhưng không nên xem là khóa nghiệp vụ bất biến trong mọi thao tác di chuyển/tổ chức lại dữ liệu.
- **SQL Server `rowversion`:** giá trị nhị phân thay đổi tự động khi hàng được ghi, thường dùng để phát hiện cập nhật đồng thời (*optimistic concurrency*). **`rowversion` không phải kiểu thời gian thực**, dù tên tương đương cũ là `timestamp`, và không thay thế một cột `created_at` hay UUID.

Ví dụ sử dụng `rowversion` ở SQL Server:

~~~sql
CREATE TABLE dbo.tai_khoan (
    id BIGINT IDENTITY(1, 1) PRIMARY KEY,
    ten NVARCHAR(100) NOT NULL,
    phien_ban ROWVERSION
);
~~~

Khi cập nhật, ứng dụng có thể đưa giá trị `phien_ban` đã đọc vào điều kiện `WHERE`. Nếu bản ghi bị phiên khác sửa, giá trị cũ không còn khớp, lệnh có thể ảnh hưởng 0 dòng, và ứng dụng cần xử lý xung đột. `rowversion` là **dấu hiệu thay đổi phiên bản**, không phải mã nhận diện người dùng.

## 7. Chọn kiểu định danh dựa trên mục tiêu

Không có loại khóa tốt nhất cho mọi hệ thống. Có thể ra quyết định từ các yêu cầu cụ thể:

| Yêu cầu ưu tiên | Phương án đáng cân nhắc | Vì sao |
| --- | --- | --- |
| Bảng nội bộ một DB, quan hệ nhiều, cần chỉ mục gọn | `BIGINT IDENTITY`/sequence | Giá trị ngắn, so sánh và khóa ngoại gọn; vận hành đơn giản. |
| Nhiều dịch vụ tự tạo bản ghi trước khi ghi DB | UUID v4/v7 | Không cần mỗi lần liên hệ một nơi cấp số; xác suất trùng rất nhỏ nếu sinh đúng. |
| ID phân tán và muốn tính cục bộ theo thời gian | UUIDv7, ULID, Snowflake-style | Có thể hỗ trợ thứ tự/tính cục bộ; cần xác nhận cách sinh và so sánh. |
| Muốn đặt điều kiện duy nhất theo nghiệp vụ | `UNIQUE`/khóa tự nhiên hoặc khóa ghép | Bảo vệ quy tắc nghiệp vụ bất kể dùng khóa thay thế nào. |
| Kiểm tra hai nội dung tệp có giống nhau | Mã băm nội dung | Fingerprint phục vụ so sánh/deduplication; cần xét va chạm và metadata. |
| Phát hiện bản ghi bị sửa từ lần đọc trước | Version counter, `rowversion`, điều kiện optimistic lock | Phát hiện cập nhật cạnh tranh, không cần thay đổi ID bản ghi. |

Với khóa chính UUID, nên tạo **ràng buộc `PRIMARY KEY` hoặc `UNIQUE` tại database** ngay cả khi bộ sinh UUID tốt: đây là tuyến phòng vệ cuối khi có lỗi sinh, nhập liệu hoặc hợp nhất dữ liệu. Khóa ngoại phải sử dụng kiểu dữ liệu tương thích với khóa được tham chiếu; không lưu một bên là `BIGINT` rồi một bên là UUID mà không có mô hình liên kết rõ ràng.

## 8. Nhị phân và định danh trong ứng dụng: các lưu ý kỹ thuật

### 8.1. Truyền giá trị bằng tham số thay vì ghép chuỗi SQL

Khi ứng dụng Java/JDBC ghi dữ liệu nhị phân và UUID vào PostgreSQL:

~~~java
UUID id = UUID.randomUUID(); // UUIDv4 do ứng dụng sinh.
byte[] noiDung = docNoiDungTep(); // Hàm ứng dụng tự cung cấp.

String sql = """
    INSERT INTO tep_dinh_kem (id, ten_tep, loai_mime, noi_dung)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, id);
    ps.setString(2, "hop_dong.pdf");
    ps.setString(3, "application/pdf");
    ps.setBytes(4, noiDung);
    ps.executeUpdate();
}
~~~

Đây là đoạn minh họa đặt trong phương thức Java đã có `connection`, hàm `docNoiDungTep()` và các import JDBC/UUID thích hợp. Đoạn mã dùng `setObject(UUID)` của PostgreSQL JDBC và `setBytes(byte[])`; với DBMS/driver khác có thể cần cơ chế bind UUID đặc thù. Với tệp lớn, cân nhắc `setBinaryStream` hoặc API stream/large object của driver để không phải giữ toàn bộ nội dung trong bộ nhớ.

Các tham số `?` đại diện cho **giá trị**, không phải tên bảng/cột. Truyền byte, UUID và văn bản qua API bind giúp tránh lỗi escape/encoding và bảo vệ câu lệnh khỏi SQL injection do nối dữ liệu đầu vào.

### 8.2. Kiểm tra byte theo byte, không dựa vào ảnh hiển thị

Các thao tác như tạo thumbnail ảnh, nén, giải mã rồi mã hóa lại hoặc chuẩn hóa file có thể làm **dãy byte thay đổi** ngay cả khi người dùng nhìn thấy nội dung có vẻ giống nhau. Vì vậy:

- Kiểm tra **số byte** bằng hàm kiểu `octet_length`/`DATALENGTH`/hàm tương ứng của DBMS;
- Nếu cần kiểm tra dữ liệu không đổi, tính mã băm trên **cùng một dãy byte gốc** ở hai đầu;
- Ghi rõ encoding/định dạng khi chuyển giữa byte và văn bản;
- Không tự diễn giải UUID binary bằng `CAST` bất kỳ nếu DBMS/driver không có quy ước byte order phù hợp.

Mã băm giúp phát hiện sai lệch dữ liệu; nếu cần **xác thực nguồn gốc/chống giả mạo**, phải xem xét chữ ký số hoặc mã xác thực thông điệp với quản lý khóa phù hợp. Bản thân SHA-256 của một tệp không cung cấp kiểm soát truy cập.

### 8.3. Quyền truy cập và dữ liệu nhạy cảm

Nội dung BLOB có thể chứa thông tin cá nhân, hợp đồng hoặc dữ liệu bí mật. Cần giới hạn quyền đọc/ghi ở cả ứng dụng và DB, cân nhắc mã hóa khi truyền và khi lưu, quản lý sao lưu/log và chính sách xóa dữ liệu. Không nên log nguyên giá trị `BYTEA`/BLOB hay xuất mã băm bí mật của dữ liệu nhạy cảm chỉ để debug. **UUID không che được nội dung** và cũng không thay thế phân quyền.

### 8.4. Bản ghi, nội dung tệp và giao dịch

Nếu nội dung tệp nằm trong một cột SQL, việc ghi metadata và nội dung có thể cùng thuộc một giao dịch DB:

~~~sql
BEGIN;

INSERT INTO tep_dinh_kem (ten_tep, loai_mime, noi_dung)
VALUES (
    'mau.bin',
    'application/octet-stream',
    decode('000102ff', 'hex')
);

-- Thực hiện các thao tác SQL có liên quan nếu cần.
COMMIT;
~~~

Nếu nội dung nằm trong object storage bên ngoài, `COMMIT` của database **không tự hoàn tác thao tác đã ghi lên dịch vụ lưu trữ khác**. Ứng dụng cần thiết kế cách xử lý lỗi, trạng thái tạm, kiểm tra lại và dọn tệp không còn tham chiếu.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Hex/Base64 là dữ liệu nhị phân giống `BLOB`.” | Hex/Base64 là biểu diễn bằng ký tự của một dãy byte; cần decode nếu muốn byte gốc. |
| “Cột `BIT` dùng để lưu tệp giống `BLOB`.” | Kiểu chuỗi bit và chuỗi byte có ngữ nghĩa khác nhau; lựa chọn tùy loại dữ liệu. |
| “UUID có 36 byte.” | UUID là 128 bit = 16 byte; bản chuỗi chuẩn có 36 ký tự. |
| “UUID chắc chắn không bao giờ trùng.” | Cơ chế sinh tốt làm xác suất trùng rất thấp; DB vẫn cần ràng buộc duy nhất. |
| “UUIDv7 là timestamp chính xác của nghiệp vụ.” | UUIDv7 mang thông tin thời gian theo quy tắc sinh, không thay cột thời gian được quản lý riêng. |
| “UUID bí mật nên ai biết ID cũng được xem dữ liệu.” | ID không phải quyền truy cập; API vẫn phải xác thực và kiểm tra phân quyền. |
| “`BINARY(16)` ở mọi DBMS lưu/đọc UUID giống nhau.” | Cần nhất quán byte order và hàm chuyển đổi, nhất là các cờ chuyển byte ở MySQL hay xử lý trong ứng dụng. |
| “Số `IDENTITY` phải liên tiếp và phản ánh thứ tự commit.” | Bộ cấp số có thể bỏ số và không bảo đảm thứ tự commit trong môi trường đồng thời. |
| “`ROWID`, `ctid`, `rowversion` đều là primary key lâu dài.” | Đây là các giá trị nội bộ/chỉ dấu phiên bản có mục đích riêng; không nên gán làm ID nghiệp vụ bền vững. |
| “Mã băm SHA-256 của tệp là mã người dùng.” | Mã băm nhận diện nội dung, không tự nhận diện người sở hữu hay quyền của một bản ghi. |

## 10. Bài tập áp dụng

### Bài 1: Lưu ảnh và metadata

Một ứng dụng lưu ảnh đại diện, tên tệp, thời gian tạo và mã ảnh. Hãy chọn kiểu dữ liệu trong PostgreSQL.

**Gợi ý lời giải:**

~~~sql
CREATE TABLE anh_dai_dien (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ten_tep TEXT NOT NULL,
    noi_dung BYTEA NOT NULL,
    thoi_diem_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Ở đây `UUID` xác định bản ghi, `TEXT` lưu tên và `BYTEA` lưu byte ảnh. Với hệ thống ảnh lớn, có thể thay `noi_dung` bằng key tham chiếu object storage sau khi cân nhắc cách triển khai.

### Bài 2: Chuyển dữ liệu hex

Giả sử SQL trả về `encode(decode('DEADBEEF', 'hex'), 'hex')`. Kết quả là gì, dữ liệu gốc có bao nhiêu byte?

**Đáp án:** chuỗi `deadbeef`; dữ liệu gốc dài **4 byte** (`DE`, `AD`, `BE`, `EF`). Chuỗi hex hiển thị có tám ký tự.

### Bài 3: Chọn khóa cho hệ thống phân tán

Ba dịch vụ cần tự tạo mã đơn hàng trước khi liên hệ database. Dùng `BIGINT IDENTITY` thuần túy tại một database có đáp ứng việc **tự sinh ID ở từng dịch vụ** không?

**Đáp án:** Không trực tiếp, vì IDENTITY thường do DB cấp số khi ghi. Có thể thiết kế bộ cấp ID phân tán, dùng UUIDv4/v7 hoặc một cơ chế Snowflake-style được vận hành đúng. Với UUID, vẫn cần `PRIMARY KEY` hoặc `UNIQUE` ở DB và cơ chế xử lý lỗi trùng hiếm gặp.

### Bài 4: Nhận biết “định danh” và “dấu hiệu phiên bản”

Một hàng có `id UUID`, `noi_dung BYTEA`, `ma_bam_sha256 BYTEA` và `phien_ban ROWVERSION` trong SQL Server (cú pháp kiểu UUID/nhị phân điều chỉnh theo SQL Server). Thành phần nào dùng để:

1. Truy cập chính xác một bản ghi?
2. Phát hiện thay đổi từ lần đọc trước?
3. Kiểm tra byte nội dung có cùng fingerprint?

**Đáp án:** (1) `id`; (2) `phien_ban`; (3) `ma_bam_sha256`. Cần dùng kiểu `UNIQUEIDENTIFIER` cho UUID và `VARBINARY` cho dữ liệu byte nếu triển khai trực tiếp trên SQL Server.

### Bài 5: Thiết kế khóa và tính duy nhất nghiệp vụ

Bảng đăng ký học phần có `id UUID PRIMARY KEY`, `sinh_vien_id` và `mon_hoc_id`. Nếu mỗi sinh viên chỉ được có một đăng ký cho mỗi môn thì khóa UUID đã đủ chưa?

**Đáp án:** Chưa. UUID chỉ bảo đảm từng bản ghi có ID riêng; phải đặt thêm `UNIQUE (sinh_vien_id, mon_hoc_id)` hoặc dùng chính cặp đó làm khóa ghép khi phù hợp. Nếu nghiệp vụ cho đăng ký lại theo học kỳ, điều kiện duy nhất cần bổ sung thành phần học kỳ hoặc thiết kế bảng lịch sử riêng.

### Bài 6: UUIDv7 và sắp xếp

Có thể bỏ `thoi_diem_tao` rồi luôn `ORDER BY id` để lấy danh sách đơn hàng mới nhất khi chuyển sang UUIDv7 không?

**Đáp án:** Không nên mặc định. UUIDv7 có thành phần thời gian và thường hỗ trợ thứ tự gần với thời điểm sinh, nhưng còn phụ thuộc clock, thuật toán sinh trong cùng mili giây, biểu diễn/so sánh UUID của DBMS và thời điểm **ghi/commit**. Nếu thứ tự theo thời gian nghiệp vụ là yêu cầu, cần cột thời gian riêng và thứ tự phụ để xử lý trường hợp bằng nhau.

## 11. Kết nối ba khái niệm trong một mô hình

Giả sử hệ thống quản lý tệp và phiên bản tệp:

~~~mermaid
flowchart TD
    A["Ứng dụng nhận tệp dưới dạng byte"] --> B{"Vị trí lưu nội dung?"}
    B -->|"Lưu trong DB"| C["Cột BYTEA / BLOB"]
    B -->|"Object storage"| D["Khóa tham chiếu lưu trong DB"]
    C --> E["Bản ghi metadata"]
    D --> E
    E --> F["UUID / BIGINT làm khóa chính"]
    E --> G["Mã băm: nhận diện nội dung"]
    E --> H["Version token: phát hiện thay đổi"]
    F --> I["Khóa ngoại / API tham chiếu"]
    G --> J["Kiểm tra toàn vẹn, trùng nội dung"]
    H --> K["Xử lý cập nhật đồng thời"]
~~~

Ba lớp giá trị có thể cùng xuất hiện trên một bảng nhưng phục vụ **ba trách nhiệm khác nhau**:

- **Kiểu nhị phân** lưu đúng byte của thông tin gốc hoặc mã băm.
- **UUID hay định danh thay thế** nhận diện bản ghi và giúp các bảng/ứng dụng tham chiếu nó.
- **Định danh đặc thù, mã băm hoặc version token** bổ sung khả năng tạo ID phân tán, nhận diện nội dung và kiểm soát cập nhật tùy nhu cầu.

Khi thiết kế dữ liệu SQL, hãy xác định trước một giá trị dùng để **lưu nội dung, nhận diện bản ghi, kiểm tra nội dung hay theo dõi phiên bản**. Từ trách nhiệm đó mới chọn `BYTEA`/BLOB, `UUID`, `BIGINT`, khóa ghép, mã băm hoặc token thích hợp. Cách phân biệt này giúp schema rõ nghĩa, ứng dụng xử lý dữ liệu đúng và tránh nhầm một dạng biểu diễn kỹ thuật với một quy tắc nghiệp vụ.
