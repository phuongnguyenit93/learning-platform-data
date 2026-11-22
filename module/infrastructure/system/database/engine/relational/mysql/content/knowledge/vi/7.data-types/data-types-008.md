# BINARY, VARBINARY và so sánh theo byte

MySQL có hai nhóm chuỗi thường gặp: chuỗi ký tự được diễn giải theo character set và collation, và chuỗi nhị phân được lưu cũng như so sánh theo byte. `BINARY` và `VARBINARY` thuộc nhóm thứ hai. Chúng phù hợp khi dữ liệu là một dãy byte có ý nghĩa chính xác, chẳng hạn digest, token opaque, mã nhị phân hoặc khóa được mã hóa theo một định dạng đã thống nhất.

Điểm quan trọng khi chọn kiểu dữ liệu là hiểu sự khác nhau giữa độ dài cố định và biến đổi, byte padding, cách so sánh, thứ tự sắp xếp và cách ứng dụng truyền dữ liệu. Một cột `BINARY(32)` không giống `CHAR(64)` chứa chuỗi hex của cùng một digest: cột thứ nhất lưu 32 byte, cột thứ hai lưu 64 ký tự hex. Nếu nhầm hai cách biểu diễn này, bạn có thể tăng gấp đôi dung lượng, tạo index sai kích thước hoặc so sánh dữ liệu không đúng.

Trong module `DATABASE_MYSQL`, việc chọn kiểu dữ liệu chính xác là một phần của thiết kế bảng, khóa và index. Bài này tập trung vào `BINARY`, `VARBINARY`, cách so sánh byte và cách dùng chúng an toàn trong SQL cũng như ứng dụng.

## 1. Chuỗi ký tự và chuỗi nhị phân khác nhau thế nào?

Chuỗi ký tự có character set và collation. Character set quy định cách biểu diễn ký tự thành byte; collation quy định cách so sánh và sắp xếp văn bản. Ví dụ, hai chuỗi `A` và `a` có thể được xem là bằng nhau dưới một collation không phân biệt hoa thường.

Chuỗi nhị phân biểu diễn byte thô. MySQL không áp dụng quy tắc ngôn ngữ, không chuẩn hóa chữ hoa/thường và không diễn giải byte theo một bảng mã văn bản. Việc so sánh được thực hiện dựa trên giá trị byte và độ dài của chuỗi nhị phân.

| Đặc điểm | `CHAR` / `VARCHAR` | `BINARY` / `VARBINARY` |
|---|---|---|
| Ý nghĩa | Văn bản theo character set | Dãy byte |
| Độ dài khai báo | Theo số ký tự tối đa | Theo số byte tối đa |
| Quy tắc so sánh | Theo collation | Theo byte |
| Hoa/thường | Phụ thuộc collation | Phân biệt vì byte khác nhau |
| Khoảng trắng cuối | Phụ thuộc collation và quy tắc PAD SPACE/NO PAD | Là byte dữ liệu, được tính trong phép so sánh |
| Padding của kiểu cố định | `CHAR` dùng khoảng trắng theo quy tắc lưu trữ | `BINARY(n)` thêm byte `0x00` tới đủ độ dài |

Một cột `VARCHAR(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin` vẫn là chuỗi ký tự: nó có character set và collation. Collation `_bin` làm phép so sánh dựa trên mã ký tự theo quy tắc collation, nhưng không biến cột đó thành kiểu chuỗi nhị phân `VARBINARY`. Nếu dữ liệu là byte thô, hãy dùng kiểu nhị phân thực sự.

## 2. `BINARY(n)` — chuỗi nhị phân có độ dài cố định

`BINARY(n)` lưu một giá trị có độ dài cố định `n` byte. Nếu giá trị được gán ngắn hơn `n`, MySQL đệm bên phải bằng byte zero (`0x00`) cho đủ độ dài. Khi đọc lại, các byte padding này vẫn là một phần của giá trị.

Ví dụ:

```sql
CREATE TABLE binary_fixed_demo (
    code BINARY(4) NOT NULL
);

INSERT INTO binary_fixed_demo (code)
VALUES (_binary'AB');

SELECT
    HEX(code) AS stored_bytes,
    LENGTH(code) AS byte_length
FROM binary_fixed_demo;
```

Kết quả thể hiện bốn byte `41 42 00 00`, vì `A` là `0x41`, `B` là `0x42` và hai byte còn lại là padding `0x00`. `LENGTH(code)` trả về `4`.

`BINARY(n)` phù hợp khi mọi giá trị hợp lệ có cùng độ dài, ví dụ digest SHA-256 có đúng 32 byte hoặc một định danh nhị phân có kích thước cố định. Không nên dùng `BINARY(n)` cho dữ liệu có độ dài thay đổi nếu không muốn byte padding trở thành một phần của giá trị.

Độ dài khai báo của `BINARY` tối đa là 255 byte. Nếu bỏ qua độ dài, MySQL dùng độ dài mặc định theo quy tắc của kiểu này; trong thiết kế schema, nên khai báo tường minh để tránh phụ thuộc mặc định.

## 3. `VARBINARY(n)` — chuỗi nhị phân có độ dài biến đổi

`VARBINARY(n)` lưu từ 0 đến `n` byte. Giá trị không được đệm tới đủ `n` byte; MySQL lưu độ dài thực tế cùng nội dung. Vì vậy, hai giá trị có cùng tiền tố nhưng độ dài khác nhau vẫn là hai chuỗi byte khác nhau.

```sql
CREATE TABLE binary_variable_demo (
    code VARBINARY(16) NOT NULL
);

INSERT INTO binary_variable_demo (code)
VALUES (_binary'AB'), (_binary'AB ');

SELECT
    HEX(code) AS stored_bytes,
    LENGTH(code) AS byte_length
FROM binary_variable_demo;
```

Hai hàng lần lượt chứa `41 42` và `41 42 20`; byte `0x20` ở cuối là một phần dữ liệu. `VARBINARY` không tự cắt khoảng trắng cuối và không đệm byte zero như `BINARY(n)`.

Độ dài tối đa khai báo của `VARBINARY` là 65.535 byte, nhưng giới hạn sử dụng thực tế còn phụ thuộc giới hạn kích thước hàng, các cột khác, row format, giới hạn packet và cách dữ liệu lớn được lưu. Nếu cần lưu payload nhị phân lớn, hãy xem xét họ `BLOB` thay vì cố đặt một cột `VARBINARY` sát giới hạn hàng.

## 4. So sánh theo byte

Với chuỗi nhị phân, phép so sánh dựa trên byte. Không có collation không phân biệt hoa thường hoặc quy tắc ngôn ngữ. Ví dụ:

```sql
SELECT
    _binary'ABC' = _binary'ABC' AS exact_match,
    _binary'ABC' = _binary'abc' AS case_sensitive_match,
    _binary'ABC' = _binary'ABC ' AS trailing_byte_match;
```

Kết quả lần lượt là `1`, `0`, `0`. Byte chữ hoa khác byte chữ thường; byte khoảng trắng cuối cũng được tính. Đây là hành vi mong muốn khi so sánh token, digest hoặc mã nhị phân chính xác.

### So sánh theo thứ tự từ điển của byte

Các phép so sánh thứ tự như `<`, `>`, `ORDER BY` và phép tìm khoảng trên chuỗi nhị phân dựa vào thứ tự byte. Khi byte đầu tiên khác nhau, byte có giá trị nhỏ hơn quyết định thứ tự; nếu một chuỗi là tiền tố của chuỗi kia, độ dài cũng ảnh hưởng kết quả.

```sql
SELECT HEX(value_bytes) AS value_hex
FROM (
    SELECT _binary'B' AS value_bytes
    UNION ALL SELECT _binary'A'
    UNION ALL SELECT _binary'AA'
    UNION ALL SELECT _binary'A '
) AS values_to_sort
ORDER BY value_bytes;
```

Thứ tự này không phải thứ tự từ điển theo ngôn ngữ. Nó hữu ích khi định dạng byte được thiết kế có chủ đích, nhưng không nên dùng để sắp xếp văn bản cho người đọc.

### Byte zero và khoảng trắng cuối

Chuỗi nhị phân có thể chứa byte `0x00`, byte `0x20` và mọi byte khác trong miền byte. Không được xử lý chúng như chuỗi C kết thúc ở null byte hoặc tự cắt khoảng trắng cuối ở tầng ứng dụng.

```sql
SELECT
    HEX(X'410042') AS bytes_with_zero,
    LENGTH(X'410042') AS bytes_count,
    HEX(X'414220') AS bytes_with_space,
    LENGTH(X'414220') AS bytes_with_space_count;
```

Kết quả minh họa hai dãy byte có byte zero ở giữa và khoảng trắng ở cuối. Độ dài là số byte thực tế. Khi truyền các giá trị này qua driver, dùng API nhị phân và giữ độ dài dữ liệu đi kèm.

## 5. Phân biệt padding của `BINARY(n)` với dữ liệu thực

Padding zero là khác biệt quan trọng nhất giữa hai kiểu. Xem ví dụ kết hợp:

```sql
CREATE TABLE binary_padding_demo (
    fixed_value BINARY(4) NOT NULL,
    variable_value VARBINARY(4) NOT NULL
);

INSERT INTO binary_padding_demo (fixed_value, variable_value)
VALUES (_binary'AB', _binary'AB');

SELECT
    HEX(fixed_value) AS fixed_hex,
    LENGTH(fixed_value) AS fixed_length,
    HEX(variable_value) AS variable_hex,
    LENGTH(variable_value) AS variable_length
FROM binary_padding_demo;
```

Kết quả mong đợi:

| Cột | HEX | Độ dài |
|---|---|---:|
| `fixed_value` | `41420000` | 4 |
| `variable_value` | `4142` | 2 |

Điều này có một số hệ quả:

- Khi dùng `BINARY(n)`, ứng dụng phải biết giá trị trả về có thể chứa byte padding zero.
- Không nên so sánh giá trị `BINARY(n)` với một chuỗi byte ngắn mà không hiểu quy tắc chuyển kiểu và padding.
- Khi cần giữ nguyên độ dài dữ liệu đầu vào, chọn `VARBINARY`.
- Khi giao thức quy định mọi giá trị đúng `n` byte, `BINARY(n)` có thể làm rõ invariant đó ở schema.

Đừng dùng `TRIM()` để loại byte padding của `BINARY`: `TRIM()` chủ yếu xử lý ký tự khoảng trắng, không phải thao tác tổng quát để bỏ byte zero. Nếu cần biểu diễn phần byte có ý nghĩa, hãy lưu kèm độ dài thật hoặc chọn `VARBINARY`.

## 6. Tạo chuỗi nhị phân và chuyển đổi dữ liệu

MySQL có nhiều cách tạo giá trị nhị phân trong SQL:

| Cú pháp | Ý nghĩa |
|---|---|
| `X'4142'` | Hex literal biểu diễn byte `0x41 0x42`. |
| `0x4142` | Hex literal; cách diễn giải phụ thuộc ngữ cảnh biểu thức. |
| `_binary'AB'` | String literal có introducer `binary`, dùng byte của literal thay vì áp dụng collation văn bản. |
| `UNHEX('4142')` | Chuyển chuỗi chữ số hex thành byte. |
| `HEX(binary_column)` | Chuyển byte thành chuỗi hex để quan sát hoặc trao đổi ở dạng văn bản. |

Khi viết ví dụ cần biểu diễn chính xác byte, ưu tiên `X'...'` hoặc `UNHEX()` vì chúng làm rõ nội dung hex. Với `0x...`, cần lưu ý MySQL có thể diễn giải hex literal như số trong ngữ cảnh số học.

Ví dụ chuyển một digest SHA-256 từ chuỗi hex sang 32 byte:

```sql
SELECT
    SHA2('sample payload', 256) AS digest_hex,
    HEX(UNHEX(SHA2('sample payload', 256))) AS round_trip_hex,
    LENGTH(UNHEX(SHA2('sample payload', 256))) AS digest_bytes;
```

`SHA2(..., 256)` trả về 64 ký tự hex; `UNHEX()` chuyển chúng thành 32 byte; `HEX()` chuyển ngược lại để hiển thị. Khi lưu digest, cột `BINARY(32)` tránh phải lưu 64 ký tự hex.

`HEX()` rất hữu ích để debug, nhưng không nên bọc cột index bằng `HEX()` trong điều kiện lọc thông thường:

```sql
-- Nên: so sánh trực tiếp với giá trị nhị phân
SELECT id
FROM file_objects
WHERE content_sha256 = UNHEX(SHA2('sample payload', 256));

-- Tránh nếu cần tận dụng index thông thường trên content_sha256
SELECT id
FROM file_objects
WHERE HEX(content_sha256) = SHA2('sample payload', 256);
```

Điều kiện đầu cho phép optimizer xem xét index trên cột gốc. Điều kiện thứ hai áp dụng hàm lên từng giá trị cột và thường không tận dụng được index B-tree thông thường như phép so sánh trực tiếp.

### Chuyển byte thành văn bản

Khi một cột nhị phân thực chất chứa dữ liệu văn bản được mã hóa theo một charset đã biết, có thể chuyển đổi tường minh:

```sql
SELECT CONVERT(text_bytes USING utf8mb4)
FROM imported_payloads;
```

Chỉ thực hiện khi biết byte đầu vào được mã hóa theo UTF-8 hoặc tương thích với `utf8mb4`. Nếu byte không phải văn bản hợp lệ, việc diễn giải thành ký tự có thể tạo ký tự thay thế, cảnh báo hoặc kết quả không mong muốn tùy phép chuyển đổi. Không dùng `CONVERT` như một cách xác minh payload nhị phân.

## 7. Chọn `BINARY`, `VARBINARY` hay `BLOB`

Chọn theo kích thước, độ dài và ý nghĩa dữ liệu:

| Kiểu | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| `BINARY(n)` | Đúng `n` byte, đệm zero nếu đầu vào ngắn | Digest cố định, mã định danh nhị phân có kích thước cố định. |
| `VARBINARY(n)` | 0 đến `n` byte, giữ độ dài thực | Token, khóa opaque, mã thiết bị, dữ liệu nhị phân ngắn hoặc vừa. |
| `TINYBLOB` | Binary large object nhỏ | Payload nhị phân nhỏ cần lưu như BLOB. |
| `BLOB` | Binary large object | Nội dung nhị phân lớn hơn, ví dụ file nhỏ hoặc payload. |
| `MEDIUMBLOB` / `LONGBLOB` | Giới hạn lớn hơn theo họ BLOB | Nội dung nhị phân lớn, khi có lý do lưu trong database. |

Các kiểu BLOB cũng là chuỗi nhị phân và so sánh theo byte. Tuy nhiên, chúng có giới hạn kích thước lớn và cách lưu/truyền có thể khác so với cột `VARBINARY` nhỏ. Khi lưu file lớn, hãy cân nhắc việc lưu file ở object storage hoặc file service và chỉ giữ metadata, checksum, kích thước cùng định danh trong MySQL. Quyết định phụ thuộc yêu cầu backup, transaction, phân quyền, truy xuất và vòng đời dữ liệu.

Một vài nguyên tắc:

- Dùng `BINARY(n)` khi độ dài luôn cố định và padding zero là chấp nhận được.
- Dùng `VARBINARY(n)` khi độ dài thay đổi và cần bảo toàn byte đầu vào chính xác.
- Dùng BLOB khi payload vượt phạm vi hợp lý của `VARBINARY` hoặc được xem là một đối tượng nhị phân lớn.
- Không lưu văn bản có thể tìm kiếm, sắp xếp theo ngôn ngữ trong kiểu nhị phân chỉ vì muốn phân biệt hoa/thường; hãy chọn character set và collation phù hợp.

## 8. Ví dụ thiết kế bảng lưu digest và token

Giả sử hệ thống lưu metadata của file và cần so sánh checksum SHA-256. Digest SHA-256 có 256 bit, tương đương 32 byte. Có thể thiết kế:

```sql
CREATE TABLE file_objects (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    object_key VARBINARY(512) NOT NULL,
    content_sha256 BINARY(32) NOT NULL,
    content_size BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_file_objects_object_key (object_key),
    KEY idx_file_objects_sha256 (content_sha256)
) ENGINE=InnoDB;
```

Trong thiết kế này:

- `object_key` là định danh opaque có độ dài thay đổi, nên dùng `VARBINARY(512)` để so sánh đúng byte và giữ độ dài thực.
- `content_sha256` luôn có đúng 32 byte, nên dùng `BINARY(32)`.
- `content_size` là số byte không âm; `BIGINT UNSIGNED` hỗ trợ phạm vi kích thước lớn.
- Index duy nhất trên `object_key` yêu cầu toàn bộ byte của khóa phải duy nhất.
- Index trên digest hỗ trợ tìm các file có cùng checksum.

Chèn dữ liệu thử nghiệm:

```sql
INSERT INTO file_objects (
    object_key,
    content_sha256,
    content_size
)
VALUES (
    X'666F6C6465722F66696C652E62696E',
    UNHEX(SHA2('sample payload', 256)),
    OCTET_LENGTH('sample payload')
);
```

Truy vấn và hiển thị:

```sql
SELECT
    id,
    HEX(object_key) AS object_key_hex,
    HEX(content_sha256) AS sha256_hex,
    content_size
FROM file_objects
WHERE content_sha256 = UNHEX(SHA2('sample payload', 256));
```

Lưu ý: checksum dùng để nhận diện nội dung hoặc kiểm tra toàn vẹn; không nên dùng SHA-256 đơn thuần làm cơ chế lưu mật khẩu. Mật khẩu cần password hashing chuyên dụng có salt và cost factor, chẳng hạn Argon2id hoặc bcrypt, thường được quản lý ở tầng ứng dụng.

## 9. Index và truy vấn trên dữ liệu nhị phân

Index B-tree trên `BINARY` hoặc `VARBINARY` sắp xếp và tìm kiếm theo byte. Điều này phù hợp với phép so sánh chính xác, tra cứu token hoặc tìm digest. Cần bảo đảm ứng dụng bind đúng byte; cùng một chuỗi hiển thị ở terminal chưa chắc là cùng dãy byte nếu encoding khác nhau.

### Index đầy đủ và index tiền tố

Nếu độ dài cột phù hợp, có thể tạo index đầy đủ:

```sql
CREATE INDEX idx_file_objects_sha256
ON file_objects (content_sha256);
```

Với cột nhị phân dài, có thể cân nhắc prefix index:

```sql
CREATE INDEX idx_payload_prefix
ON imported_payloads (payload_bytes(32));
```

Prefix index chỉ lưu một phần đầu của giá trị trong index. Nó có thể giúp lọc ứng viên, nhưng server vẫn cần kiểm tra phần còn lại để xác nhận phép so sánh đầy đủ. Đặc biệt, unique prefix index buộc phần tiền tố phải duy nhất: hai giá trị đầy đủ khác nhau nhưng có cùng tiền tố vẫn bị từ chối. Vì vậy, nó không phải cách thay thế tương đương cho unique index trên toàn bộ giá trị. Nếu yêu cầu nghiệp vụ là toàn bộ byte phải duy nhất, hãy dùng unique index đầy đủ khi khả thi hoặc thiết kế một khóa/digest bổ trợ cùng bước xác minh nội dung.

### Tìm kiếm theo byte và kế hoạch thực thi

Hãy so sánh trực tiếp cột với literal hoặc parameter có kiểu nhị phân:

```sql
EXPLAIN
SELECT id, object_key
FROM file_objects
WHERE content_sha256 = UNHEX(SHA2('sample payload', 256));
```

Kiểm tra cột `key` trong kết quả `EXPLAIN` để xem optimizer có chọn index digest hay không. Với bảng nhỏ, optimizer vẫn có thể chọn table scan vì chi phí thấp hơn; hãy kiểm tra trên dữ liệu gần thực tế trước khi kết luận index không hiệu quả.

Không tạo index chỉ vì cột có kiểu `BINARY`. Index phải phục vụ một mẫu truy vấn thực tế. Mỗi index làm tăng dung lượng và chi phí ghi, đặc biệt khi payload lớn hoặc có nhiều index trên cùng bảng.

## 10. Làm việc với `BINARY` và `VARBINARY` từ ứng dụng Java

Với JDBC, dữ liệu nhị phân nên được truyền bằng API byte array hoặc binary stream. Không chuyển byte thành chuỗi tùy tiện rồi gọi `setString()`, vì driver có thể mã hóa chuỗi theo connection character set và làm thay đổi byte.

Ví dụ dùng `PreparedStatement.setBytes()` và `ResultSet.getBytes()`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public class FileDigestRepository {
    private final DataSource dataSource;

    public FileDigestRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public byte[] findObjectKeyByDigest(byte[] sha256) throws SQLException {
        String sql = "SELECT object_key FROM file_objects "
                + "WHERE content_sha256 = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setBytes(1, sha256);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    return null;
                }
                return resultSet.getBytes("object_key");
            }
        }
    }
}
```

Phương thức giả định `sha256` có đúng 32 byte và schema có thể có nhiều hàng cùng digest; ví dụ trả về khóa của hàng đầu tiên theo kết quả truy vấn. Trong ứng dụng thật, cần quy định rõ nếu digest trùng nhiều file thì xử lý tất cả hay chọn một hàng theo tiêu chí xác định. Nếu cần truyền payload lớn, xem xét `setBinaryStream()` và cách driver stream dữ liệu.

Một số lưu ý khi dùng JDBC:

- Dùng `setBytes()` cho giá trị nhị phân nhỏ hoặc vừa; dùng `setBinaryStream()` cho stream lớn.
- Dùng `getBytes()` hoặc `getBinaryStream()` để đọc dữ liệu nhị phân.
- Đóng `ResultSet`, `Statement` và `Connection` bằng try-with-resources.
- Không dùng `new String(bytes)` nếu chưa xác định encoding; constructor này có thể diễn giải byte bằng charset mặc định.
- Kiểm tra độ dài trước khi ghi, ví dụ digest SHA-256 phải đúng 32 byte.
- Với cột `BINARY(n)`, nhớ rằng dữ liệu trả về có thể gồm byte zero padding; ứng dụng cần xử lý theo hợp đồng schema.

## 11. Lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Lưu 32 byte digest vào `CHAR(64)` nhưng không chuyển hex | Dữ liệu sai định dạng hoặc bị chuyển đổi ngoài ý muốn | Chọn `BINARY(32)` cho byte digest hoặc `CHAR(64)` cho chuỗi hex và thống nhất biểu diễn. |
| Dùng `BINARY(64)` để chứa 64 ký tự hex nhưng ứng dụng gửi 32 byte | Giá trị bị đệm zero và độ dài khác mong đợi | Phân biệt rõ byte digest với chuỗi hex. |
| Dùng `BINARY(n)` cho token có độ dài thay đổi | Padding zero có thể làm thay đổi phép so sánh hoặc dữ liệu trả về | Dùng `VARBINARY(n)`. |
| Dùng `VARCHAR` cho byte tùy ý | Charset conversion có thể làm thay đổi byte hoặc từ chối dữ liệu | Dùng kiểu nhị phân và API bind byte. |
| So sánh qua `HEX(column)` trong mọi truy vấn | Có thể không dùng được index cột gốc | Chuyển tham số hex thành byte bằng `UNHEX()` rồi so sánh trực tiếp. |
| Tạo unique prefix index và nghĩ toàn bộ payload đã duy nhất | Hai giá trị khác nhau có cùng tiền tố vẫn có thể tồn tại | Dùng unique index đầy đủ nếu phù hợp hoặc thiết kế khóa riêng. |
| Coi BINARY là mã hóa | Dữ liệu vẫn có thể đọc được dưới dạng byte/hex | Dùng mã hóa phù hợp và quản lý khóa riêng. |
| Chuyển byte thành String bằng charset mặc định | Byte có thể bị thay đổi hoặc thay thế | Giữ `byte[]`; chỉ decode khi biết encoding. |

## 12. Bài tập thực hành

### Bài tập A — Quan sát padding

1. Tạo một bảng có `BINARY(4)` và `VARBINARY(4)`.
2. Chèn cùng giá trị `_binary'AB'` vào hai cột.
3. Dùng `HEX()` và `LENGTH()` để quan sát khác biệt.
4. Chèn thêm giá trị có byte zero và khoảng trắng cuối bằng hex literal.
5. Giải thích vì sao `BINARY(4)` luôn trả về bốn byte trong khi `VARBINARY(4)` giữ độ dài thực.

### Bài tập B — Kiểm tra so sánh theo byte

1. So sánh `_binary'Key'` với `_binary'key'`.
2. So sánh `_binary'AB'` với `_binary'AB '`.
3. So sánh `X'410042'` với `X'4100'`.
4. Dùng `ORDER BY` trên các giá trị hex khác nhau.
5. Giải thích kết quả dựa trên byte đầu tiên khác nhau và độ dài.

### Bài tập C — Lưu digest và dùng index

1. Tạo bảng có cột `content_sha256 BINARY(32)` và index.
2. Lưu `UNHEX(SHA2(payload, 256))`.
3. Tra cứu bằng phép so sánh trực tiếp với `UNHEX()`.
4. Chạy `EXPLAIN` và quan sát index được chọn.
5. So sánh với truy vấn dùng `HEX(content_sha256)` trong điều kiện `WHERE`.

### Bài tập D — Truyền byte qua JDBC

1. Tạo repository method nhận `byte[]`.
2. Bind bằng `PreparedStatement.setBytes()`.
3. Đọc lại bằng `ResultSet.getBytes()`.
4. So sánh hai mảng byte bằng `Arrays.equals()` thay vì chuyển sang String.
5. Thử payload có byte `0x00` ở giữa để bảo đảm code không cắt chuỗi tại null byte.

Bạn hoàn thành bài khi có thể giải thích chính xác byte padding của `BINARY(n)`, phân biệt độ dài thực của `VARBINARY(n)`, dự đoán kết quả so sánh byte, chọn đúng kiểu cho digest/token/payload, và truyền dữ liệu nhị phân qua ứng dụng mà không làm thay đổi nội dung.

## 13. Nguyên tắc cần ghi nhớ

- `BINARY(n)` có độ dài cố định và được đệm bên phải bằng `0x00`.
- `VARBINARY(n)` giữ độ dài byte thực tế và không tự padding.
- So sánh chuỗi nhị phân dựa trên byte; hoa/thường, byte zero và khoảng trắng cuối đều có ý nghĩa.
- `CHAR`/`VARCHAR` với collation `_bin` vẫn là chuỗi ký tự, không tương đương `BINARY`/`VARBINARY`.
- Dùng `HEX()` để quan sát và `UNHEX()` để chuyển hex thành byte; ưu tiên so sánh trực tiếp cột nhị phân để index có thể được sử dụng.
- Trong Java, dùng `byte[]`, `setBytes()` và `getBytes()` cho dữ liệu nhị phân; tránh decode nếu chưa biết charset.
- Chọn `BLOB` cho payload lớn và cân nhắc object storage nếu việc lưu file trong database không phù hợp với yêu cầu vận hành.
- Kiểu nhị phân không cung cấp mã hóa hay bảo vệ bí mật; hãy thiết kế bảo mật riêng cho dữ liệu nhạy cảm.

Khi nắm rõ cách MySQL lưu và so sánh byte, bạn có thể chọn kiểu dữ liệu phù hợp, thiết kế index đúng mục tiêu và giữ nguyên dữ liệu khi trao đổi giữa database với ứng dụng. Đây là nền tảng để tránh lỗi chuyển mã, padding ngoài ý muốn và phép so sánh sai trong các hệ thống lưu token, digest và payload nhị phân.
