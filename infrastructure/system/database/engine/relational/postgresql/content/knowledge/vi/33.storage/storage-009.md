# Đối tượng lớn (Large Objects) so với BYTEA và vòng đời dữ liệu trong PostgreSQL

Một ứng dụng lưu ảnh đại diện, PDF hợp đồng, file scan hoặc video vào PostgreSQL có hai cách lưu binary phổ biến:

- **`bytea`:** lưu bytes như một giá trị của cột trong một row quan hệ.
- **Large Object (LO):** lưu nội dung trong cơ chế Large Object riêng của PostgreSQL, còn bảng nghiệp vụ giữ một **OID tham chiếu** tới object đó.

Cả hai đều có thể được quản lý trong transaction và được backup cùng database khi dùng công cụ phù hợp. Nhưng chúng khác nhau đáng kể về cách truy cập, kích thước, bảo mật, liên kết dữ liệu và đặc biệt là **vòng đời xóa dữ liệu**.

Ví dụ:

```sql
-- Binary là một phần của row:
CREATE TABLE documents_bytea (
    document_id bigint PRIMARY KEY,
    file_name text NOT NULL,
    content bytea NOT NULL
);

-- Row chỉ lưu OID trỏ tới một Large Object riêng:
CREATE TABLE documents_lo (
    document_id bigint PRIMARY KEY,
    file_name text NOT NULL,
    content_oid oid NOT NULL
);
```

Với `bytea`, khi row bị xóa thì giá trị binary thuộc row đó được PostgreSQL quản lý theo MVCC/TOAST và được thu hồi qua cơ chế lưu trữ bình thường. Với Large Object, **xóa row tham chiếu không tự xóa object**. Ứng dụng phải gọi `lo_unlink`/API tương ứng, dùng trigger quản lý đúng mô hình tham chiếu hoặc có quy trình dọn object mồ côi.

Một lựa chọn đúng không chỉ phụ thuộc vào file lớn bao nhiêu. Cần xem ứng dụng có cần đọc/ghi từng đoạn, có cần chia sẻ một object cho nhiều rows, ai được phép đọc object, cách xử lý khi xóa row, backup/restore và client có dùng JDBC/ORM hay không.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt kiểu dữ liệu `bytea` với Large Object có OID.
2. Giải thích TOAST tự động nén và lưu out-of-line các giá trị lớn của kiểu hỗ trợ TOAST.
3. Nêu giới hạn kích thước logic của TOASTed field/`bytea` (1 GB) và ưu thế Large Object cho nội dung tới 4 TB.
4. Hiểu cách Large Object được chia thành chunks, hỗ trợ streaming và random access.
5. Tạo, mở, đọc, ghi, seek, truncate và unlink Large Object bằng SQL/libpq/pgJDBC.
6. Dùng JDBC `setBytes`/`getBytes`/`setBinaryStream`/`getBinaryStream` cho `bytea`.
7. Truy cập Large Object trong transaction JDBC và giải phóng resource đúng cách.
8. Thiết kế quan hệ metadata–binary, quyền object và ràng buộc nghiệp vụ.
9. Xử lý vòng đời: tạo mới, thay file, xóa row, chia sẻ object, rollback, orphan cleanup.
10. Hiểu module `lo`, kiểu domain `lo`, trigger `lo_manage` và tiện ích `vacuumlo`.
11. Nhận diện nguy cơ bảo mật khi OID được lộ, RLS chỉ bảo vệ row tham chiếu và ACL của LO tách biệt.
12. Thiết kế backup/restore, migration `bytea` ↔ LO, retention và kiểm thử dữ liệu không bị rò rỉ hoặc mất.

## 2. Hai mô hình lưu trữ

### 2.1. BYTEA: binary là một thuộc tính của row

```sql
CREATE TABLE app.attachments (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content bytea NOT NULL,
    content_length bigint NOT NULL
        CHECK (content_length >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Một row sở hữu nội dung binary của chính nó. Metadata và bytes cùng nằm trong mô hình quan hệ; có thể dùng FK, transaction, RLS và quyền cột theo các quy tắc bảng bình thường.

### 2.2. Large Object: row lưu OID, object tồn tại riêng

```sql
CREATE TABLE app.attachments_lo (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content_oid oid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

`content_oid` là **định danh Large Object**, không phải bytes và cũng không phải đường dẫn file. Nội dung nằm trong hệ thống Large Object của PostgreSQL; ứng dụng phải mở LO bằng OID để đọc/ghi.

### 2.3. So sánh nhanh

| Tiêu chí | `bytea` | Large Object |
| --- | --- | --- |
| Mô hình | Giá trị cột trong row. | Object riêng, row giữ OID. |
| Kích thước logic tối đa | 1 GB cho TOAST-able datum. | Tối đa 4 TB theo tài liệu PostgreSQL. |
| Lưu trữ vật lý | TOAST có thể nén và/hoặc tách chunks ra TOAST table. | Chia chunks trong `pg_largeobject`, metadata trong `pg_largeobject_metadata`. |
| Streaming | JDBC có stream API; bản thân giá trị vẫn là datum `bytea`. | API LO đọc/ghi theo đoạn và seek trực tiếp. |
| Đọc/ghi một vùng | Nhiều thao tác xử lý giá trị như một đơn vị; có tối ưu riêng cho substring trong một số chế độ TOAST. | Hỗ trợ random access/partial read-write rõ ràng. |
| Vòng đời | Theo row/column, tự quản lý bởi PostgreSQL. | Phải unlink hoặc có cơ chế cleanup; xóa row tham chiếu không tự xóa LO. |
| Chia sẻ một nội dung | Có thể copy bytes hoặc thiết kế bảng nội dung riêng. | Nhiều rows có thể tham chiếu cùng OID, nhưng phải quản lý refcount/ownership cẩn thận. |
| Quyền truy cập | Quyền bảng/cột và RLS trên row. | Có ACL/owner riêng cho LO ngoài quyền row chứa OID. |
| Tính quan hệ | Dễ dùng constraint, FK và DML thông thường. | OID không tự tạo FK tới object catalog. |
| Backup | Theo table data. | Là dữ liệu LO riêng; cần bảo đảm công cụ dump bao gồm Large Objects. |
| JDBC | `getBytes`, `setBytes`, binary streams. | pgJDBC LargeObject API hoặc Blob mapping, cần transaction. |
| Độ phức tạp vận hành | Thường thấp hơn. | Cao hơn do lifecycle, ACL, orphan cleanup. |

### 2.4. Quy tắc chọn ban đầu

- File nhỏ/vừa, thường đọc toàn bộ và gắn chặt với row nghiệp vụ: ưu tiên `bytea`.
- File rất lớn, cần seek/đọc từng đoạn hoặc cập nhật một phần: cân nhắc Large Object.
- File được phục vụ qua CDN/object storage, có lifecycle/versioning độc lập: có thể cân nhắc lưu bên ngoài database và chỉ lưu metadata/reference trong PostgreSQL.

Không chọn LO chỉ vì tên “Large Object” nghe phù hợp hơn. Nếu không cần API random access hoặc dung lượng vượt giới hạn `bytea`, chi phí quản lý OID/orphan có thể không đáng.

## 3. BYTEA và TOAST hoạt động như thế nào?

PostgreSQL dùng page kích thước cố định (thông thường 8 kB) và tuple không thể trải dài tùy ý qua nhiều pages. TOAST (The Oversized-Attribute Storage Technique) xử lý các giá trị lớn của những kiểu dữ liệu hỗ trợ bằng cách nén và/hoặc đưa dữ liệu ra một TOAST table liên kết với bảng chính.

**Ứng dụng không phải tự tạo bảng chunks cho `bytea`.** PostgreSQL tự thực hiện việc này khi cần, trong khi SQL vẫn nhìn thấy một giá trị `bytea`.

### 3.1. TOAST không có nghĩa mỗi giá trị trên 2 kB luôn được tách ra

Thông thường TOAST được kích hoạt khi tổng row quá rộng (threshold mặc định khoảng 2 kB). PostgreSQL thử nén các giá trị có thể nén, sau đó đưa một số thuộc tính ra ngoài row nếu vẫn cần giảm kích thước tuple. Chiến lược chính xác phụ thuộc kiểu, cấu hình lưu trữ và dữ liệu thực tế.

### 3.2. Các storage strategy

| Strategy | Hành vi |
| --- | --- |
| `PLAIN` | Không nén, không lưu out-of-line; bắt buộc với kiểu không hỗ trợ TOAST. |
| `EXTENDED` | Cho phép nén và out-of-line; mặc định của đa số kiểu hỗ trợ TOAST. |
| `EXTERNAL` | Cho phép out-of-line nhưng không nén; có thể giúp substring của text/bytea lớn đọc phần cần thiết nhanh hơn, đổi lại tốn dung lượng hơn. |
| `MAIN` | Cho phép nén nhưng ưu tiên giữ inline; vẫn có thể out-of-line như phương án cuối nếu tuple không thể vừa page. |

Ví dụ đổi storage strategy:

```sql
ALTER TABLE app.attachments
ALTER COLUMN content SET STORAGE EXTERNAL;
```

Lệnh này chỉ đặt chiến lược cho **những lần ghi/cập nhật dữ liệu sau**; bản thân `ALTER TABLE ... SET STORAGE` không tự rewrite tất cả dữ liệu hiện có. Không đổi sang EXTERNAL chỉ vì nghĩ “streaming sẽ nhanh hơn”; hãy benchmark workload và dung lượng.

### 3.3. Kích thước BYTEA

TOAST-able datum có giới hạn logical size 1 GB (cụ thể theo biểu diễn varlena). Vì thế `bytea` không phù hợp để lưu một file 3 GB thành một datum duy nhất, ngay cả khi PostgreSQL tự chia TOAST chunks bên dưới.

Ngoài giới hạn server, application có thể gặp giới hạn thấp hơn:

- Java `byte[]` yêu cầu mảng liên tục trong heap.
- ORM có thể materialize toàn bộ giá trị.
- Driver có thể buffer dữ liệu theo cách khiến heap tăng.
- HTTP upload/download có thể hết request timeout.
- Một SELECT trả cột binary lớn có thể chiếm nhiều memory/network.

**TOAST giảm áp lực tuple/page, không làm mọi truy cập binary tự động streaming hoặc miễn phí.**

### 3.4. TOAST table và index

Mỗi bảng có cột TOAST-able có thể có một TOAST table riêng; OID của nó được lưu trong `pg_class.reltoastrelid`. Giá trị out-of-line được chia thành chunks trong TOAST table, có chỉ mục để tìm đúng chunk.

Không truy cập/sửa trực tiếp các bảng hệ thống `pg_toast_*`. Chúng là chi tiết triển khai; dùng SQL trên bảng gốc và để PostgreSQL quản lý.

### 3.5. UPDATE cột khác không nhất thiết ghi lại toàn bộ BYTEA

Khi UPDATE một row nhưng không thay đổi cột binary out-of-line, PostgreSQL thường giữ nguyên TOAST value hiện tại thay vì ghi lại nội dung lớn. Vì vậy không nên kết luận “mọi UPDATE row có BYTEA đều ghi lại toàn bộ file”.

Tuy nhiên nếu thay đổi nội dung `bytea`, PostgreSQL tạo phiên bản dữ liệu theo MVCC và cập nhật TOAST storage tương ứng; vacuum sẽ thu hồi phiên bản cũ khi không còn snapshot nào cần.

## 4. Large Object: object riêng, OID và chunks

Large Object là một cơ chế lưu trữ riêng trong từng database PostgreSQL.

### 4.1. Hai catalog chính

- `pg_largeobject` lưu nội dung LO theo các chunks.
- `pg_largeobject_metadata` lưu OID, owner và ACL của LO.

Ứng dụng thường không thao tác trực tiếp trên hai catalog này; dùng Large Object API hoặc các hàm server-side.

### 4.2. OID là handle tham chiếu

Một giá trị OID trong bảng nghiệp vụ chỉ là số định danh của object:

```sql
SELECT content_oid
FROM app.attachments_lo
WHERE attachment_id = 10;
```

Để đọc bytes, phải dùng API hoặc hàm LO như `lo_get(content_oid)`. SELECT OID không tự tải nội dung.

### 4.3. Object có thể được chia thành nhiều chunks

PostgreSQL lưu LO thành các chunks và có B-tree index để tìm chunk cần đọc/ghi. Các chunks không cần liên tục; LO hỗ trợ seek tới offset và ghi một vùng mà không phải cấp phát toàn bộ khoảng trống trước đó. Những vùng chưa được ghi có thể được đọc như bytes zero theo semantics sparse allocation.

### 4.4. Giới hạn dung lượng

Tài liệu PostgreSQL mô tả Large Object có thể đạt tới **4 TB**. Khi làm việc với object vượt 2 GB, cần dùng các API offset/size 64-bit (ví dụ libpq `lo_lseek64`/`lo_tell64`/`lo_truncate64`; pgJDBC có `seek64`/`size64`/`truncate64`). API 32-bit cũ không thể biểu diễn vị trí lớn hơn 2 GB.

### 4.5. OID không phải foreign key

PostgreSQL không tự tạo FK từ cột `content_oid` sang object catalog. Nếu row bị xóa, LO vẫn tồn tại; nếu LO bị unlink, row có thể còn OID trỏ tới object không tồn tại.

Do đó, ứng dụng cần quy ước:

- Ai sở hữu object?
- Có bao nhiêu row tham chiếu?
- Khi xóa một row có xóa object không?
- Khi thay file, lúc nào unlink object cũ?
- Có cho phép chia sẻ OID không?
- Ai dọn những object không còn tham chiếu?

### 4.6. Không tái sử dụng OID như mã nghiệp vụ

OID do database cấp và có ý nghĩa trong database cụ thể. Không dùng OID làm public ID có thể đoán, không giả định nó ổn định qua export/import hoặc giữa các databases, và không expose OID cho client như một capability bảo mật.

## 5. SQL API cho Large Objects

PostgreSQL cung cấp các hàm server-side để tạo/xóa và đọc/ghi LO. Chúng tiện cho thao tác nhỏ hoặc lab, nhưng các hàm trả `bytea` có thể materialize toàn bộ nội dung và không thay thế streaming API cho file rất lớn.

### 5.1. Tạo LO

```sql
SELECT lo_create(0) AS new_loid;
```

`0` yêu cầu PostgreSQL chọn OID khả dụng và trả về OID mới. Hàm tạo object rỗng.

Một lựa chọn khác nếu đã có dữ liệu `bytea`:

```sql
SELECT lo_from_bytea(0, decode('48656c6c6f', 'hex')) AS new_loid;
```

Kết quả là OID của LO chứa bytes tương ứng chuỗi UTF-8 “Hello”. Ví dụ dùng dữ liệu nhỏ; không chuyển một file vài GB qua `bytea` để gọi `lo_from_bytea`.

### 5.2. Đọc toàn bộ hoặc một đoạn bằng lo_get

```sql
-- Đọc toàn bộ nội dung, trả về bytea:
SELECT lo_get(12345);

-- Đọc 100 bytes từ offset 500 (offset bắt đầu từ 0):
SELECT lo_get(12345, 500, 100);
```

`lo_get` trả `bytea`. Dạng offset/length rất hữu ích cho đoạn nhỏ, nhưng **không dùng để kéo toàn bộ LO 4 TB vào một kết quả bytea**.

### 5.3. Ghi một đoạn bằng lo_put

```sql
SELECT lo_put(
    12345,
    0,
    convert_to('Hello PostgreSQL', 'UTF8')
);
```

`lo_put` ghi bytes bắt đầu ở offset được chỉ định; object được mở rộng nếu cần. Offset là bigint, bắt đầu từ 0.

### 5.4. Xóa LO bằng lo_unlink

```sql
SELECT lo_unlink(12345);
```

Hàm trả 1 nếu xóa thành công, 0 nếu không có object tương ứng theo semantics của hàm. Chỉ owner LO hoặc superuser mới có thể unlink. **Không gọi unlink trước khi xác định không còn row nào cần dùng object**.

### 5.5. Import/export: server-side và client-side khác nhau

Các hàm server-side:

```sql
SELECT lo_import('/server/path/report.pdf');
SELECT lo_export(12345, '/server/path/report-copy.pdf');
```

Chúng truy cập filesystem của **máy chủ PostgreSQL**, dưới quyền OS user chạy server; mặc định bị giới hạn cho superuser vì rủi ro đọc/ghi file trên máy chủ.

Trong `psql`, `\lo_import` và `\lo_export` là meta-commands dùng filesystem **máy client đang chạy psql**. Đừng nhầm hai nhóm chỉ vì tên gần giống nhau.

### 5.6. Không cấp quyền lo_import/lo_export server-side tùy tiện

Grant cho user không tin cậy quyền gọi server-side import/export có thể mở đường đọc/ghi file trên server, gồm các file nhạy cảm. Chỉ cấp qua role vận hành được kiểm soát và đánh giá bảo mật như quyền quản trị đặc biệt.

## 6. BYTEA trong SQL: tạo, ghi, đọc và kiểm tra

### 6.1. Bảng lab

```sql
CREATE SCHEMA IF NOT EXISTS storage_lab;

CREATE TABLE storage_lab.attachments_bytea (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content bytea NOT NULL,
    content_length bigint NOT NULL
        CHECK (content_length >= 0),
    sha256_hex text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (content_length = octet_length(content))
);
```

`octet_length` đếm số bytes, phù hợp cho binary. Không dùng `length` của text để tính kích thước file theo byte khi encoding có thể nhiều bytes cho một ký tự.

### 6.2. Chèn binary nhỏ từ hex

```sql
INSERT INTO storage_lab.attachments_bytea (
    file_name,
    media_type,
    content,
    content_length
)
VALUES (
    'hello.txt',
    'text/plain',
    decode('48656c6c6f', 'hex'),
    5
)
RETURNING attachment_id, file_name, octet_length(content);
```

`decode(...,'hex')` chuyển chuỗi hex thành bytes. Kết quả 5 bytes là “Hello”.

### 6.3. Đọc nội dung dạng hex/base64

```sql
SELECT
    file_name,
    encode(content, 'hex') AS hex_value,
    encode(content, 'base64') AS base64_value,
    octet_length(content) AS bytes
FROM storage_lab.attachments_bytea;
```

Hex/base64 tiện để debug payload nhỏ, nhưng không SELECT/encode một file hàng trăm MB ra console/log.

### 6.4. Lấy một phần binary

```sql
SELECT substring(content FROM 1 FOR 3)
FROM storage_lab.attachments_bytea
WHERE file_name = 'hello.txt';
```

Với `bytea`, các vị trí của hàm substring bắt đầu từ **1**, khác với offset của Large Object API thường bắt đầu từ **0**. Hãy chú ý khác biệt khi chuyển code.

### 6.5. UPDATE binary

```sql
UPDATE storage_lab.attachments_bytea
SET
    content = decode('576f726c64', 'hex'),
    content_length = 5
WHERE file_name = 'hello.txt';
```

Nội dung mới là “World”. `CHECK(content_length=octet_length(content))` giúp ngăn metadata length bị lệch.

### 6.6. Xóa row BYTEA

```sql
DELETE FROM storage_lab.attachments_bytea
WHERE file_name = 'hello.txt';
```

Xóa row đồng thời xóa liên kết tới datum `bytea`. PostgreSQL quản lý việc thu hồi phiên bản vật lý cũ theo MVCC/autovacuum; không cần gọi `lo_unlink` hoặc chạy `vacuumlo` cho `bytea`.

## 7. Large Object trong SQL: bảng tham chiếu và thao tác

### 7.1. Tạo bảng metadata tham chiếu LO

```sql
CREATE TABLE storage_lab.attachments_lo (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content_oid oid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Ở ví dụ cơ bản, dùng `oid` để thể hiện rõ kiểu tham chiếu. Có thể cài module `lo` và dùng domain `lo` để diễn đạt rõ cột này là LO reference; domain không tự giải quyết lifecycle.

### 7.2. Tạo object và row tham chiếu trong cùng transaction

```sql
BEGIN;

WITH new_object AS (
    SELECT lo_from_bytea(
        0,
        convert_to('Large Object demo', 'UTF8')
    ) AS object_oid
)
INSERT INTO storage_lab.attachments_lo (
    file_name,
    media_type,
    content_oid
)
SELECT
    'demo.txt',
    'text/plain',
    object_oid
FROM new_object
RETURNING attachment_id, content_oid;

COMMIT;
```

Object và row tham chiếu được tạo cùng transaction. Nếu INSERT row thất bại và transaction ROLLBACK, việc tạo LO cũng rollback. Đây là cách tránh object mồ côi ngay từ đầu trong một workflow đơn giản.

### 7.3. Đọc LO nhỏ bằng lo_get

```sql
SELECT
    attachment_id,
    file_name,
    convert_from(lo_get(content_oid), 'UTF8') AS content_text
FROM storage_lab.attachments_lo
WHERE file_name = 'demo.txt';
```

Ví dụ LO chứa văn bản UTF-8 nhỏ. Với file binary tổng quát, giữ dữ liệu ở dạng bytea/stream; không dùng `convert_from` nếu bytes không phải text đúng encoding.

### 7.4. Đọc một đoạn LO

```sql
SELECT lo_get(content_oid, 0, 6)
FROM storage_lab.attachments_lo
WHERE file_name = 'demo.txt';
```

Offset 0 lấy sáu bytes đầu. Dùng API này cho preview/chunk nhỏ, không đọc toàn bộ LO lớn vào bộ nhớ.

### 7.5. Thay nội dung LO bằng lo_put

```sql
UPDATE storage_lab.attachments_lo
SET content_oid = lo_from_bytea(
    0,
    convert_to('Replacement content', 'UTF8')
)
WHERE file_name = 'demo.txt'
RETURNING attachment_id, content_oid;
```

**Cảnh báo:** câu UPDATE này tạo một LO mới nhưng không xóa LO cũ. Nó minh họa vì sao lifecycle cần được quản lý; không dùng như mẫu thay file hoàn chỉnh. Phần 12 sẽ trình bày cách xử lý object cũ an toàn.

### 7.6. Xóa object

```sql
-- Thay 12345 bằng OID thực tế:
SELECT lo_unlink(12345);
```

Sau khi unlink, những rows vẫn lưu OID đó sẽ trở thành tham chiếu hỏng. Hãy xóa/thay references trước hoặc trong cùng transaction theo thứ tự và policy đã thiết kế.

## 8. JDBC với BYTEA

pgJDBC hỗ trợ `bytea` bằng các API JDBC chuẩn. Với payload nhỏ đã có trong bộ nhớ, có thể dùng `setBytes`/`getBytes`. Với file lớn hơn, stream API giảm nhu cầu tạo một `byte[]` khổng lồ ở application.

### 8.1. Upload BYTEA bằng InputStream

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

Path file = Path.of("upload/report.pdf");
long fileSize = Files.size(file);

String sql = """
    INSERT INTO storage_lab.attachments_bytea
        (file_name, media_type, content, content_length)
    VALUES (?, ?, ?, ?)
    """;

try (Connection conn = dataSource.getConnection();
     InputStream in = Files.newInputStream(file);
     PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, file.getFileName().toString());
    ps.setString(2, "application/pdf");
    ps.setBinaryStream(3, in, fileSize);
    ps.setLong(4, fileSize);
    ps.executeUpdate();
}
```

Ví dụ dùng text block Java 15+ và overload `setBinaryStream(index, stream, long length)`. Đảm bảo length là chính xác. Tài liệu pgJDBC nêu overload stream có length; driver không có cách tổng quát để biết độ dài một InputStream không xác định trước. Nếu input không có length, ứng dụng có thể cần spool vào file tạm/object staging rồi đo kích thước, hoặc dùng một giao thức upload chunk khác.

### 8.2. Tải BYTEA bằng InputStream

```java
String sql = """
    SELECT content
    FROM storage_lab.attachments_bytea
    WHERE attachment_id = ?
    """;

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, attachmentId);

    try (var rs = ps.executeQuery()) {
        if (rs.next()) {
            try (InputStream in = rs.getBinaryStream("content")) {
                // Stream sang HTTP response/file/consumer.
                // Không cần tạo byte[] cho toàn bộ file.
                in.transferTo(outputStream);
            }
        }
    }
}
```

Đoạn code giả định `outputStream` do tầng gọi sở hữu và còn mở. Không đóng stream ngoài phạm vi method nếu contract không cho phép. Cũng cần bảo đảm ResultSet/Statement/Connection còn hiệu lực trong lúc đọc stream.

### 8.3. getBytes phù hợp với dữ liệu nhỏ

```java
byte[] content = rs.getBytes("content");
```

`getBytes` materialize toàn bộ giá trị vào heap. Dùng cho ảnh nhỏ hoặc dữ liệu có giới hạn kích thước được kiểm soát; không dùng với payload lớn không rõ giới hạn.

### 8.4. Một InputStream không đồng nghĩa không có giới hạn

Stream API tránh bắt buộc application giữ toàn bộ nội dung trong một mảng byte, nhưng vẫn có:

- Giới hạn 1 GB của một `bytea` datum.
- Buffer trong driver, framework, servlet và reverse proxy.
- Request/statement timeout, network bandwidth và memory pressure.
- Yêu cầu giữ ResultSet/Connection mở trong lúc stream được tiêu thụ.

Đặt giới hạn upload ở tầng API, kiểm tra content length, dùng streaming end-to-end và backpressure.

### 8.5. Kiểm tra kích thước và checksum

Có thể lưu `octet_length(content)` hoặc SHA-256 metadata. Nếu hash tính ở application trong lúc stream upload, tránh đọc file lần thứ hai chỉ để tính hash. Hash dùng để kiểm tra tính toàn vẹn; nó không thay thế authorization hoặc malware scanning.

## 9. JDBC với Large Objects

Large Object API của pgJDBC cung cấp hai lớp chính:

- `LargeObjectManager`: tạo, mở, xóa object.
- `LargeObject`: đọc/ghi, stream, seek, truncate và đóng descriptor.

### 9.1. Large Object luôn cần transaction

**Mọi thao tác Large Object API phải diễn ra trong SQL transaction block.** Descriptor mở LO chỉ có hiệu lực trong transaction hiện tại; không sử dụng LO trong connection autocommit như thể nó là một file handle tồn tại độc lập.

```java
conn.setAutoCommit(false);
```

Sau khi hoàn tất, `commit` hoặc `rollback` transaction. Khi connection dùng pool, transaction manager phải trả connection về trạng thái hợp lệ.

### 9.2. Upload bằng pgJDBC LargeObjectManager

Ví dụ sử dụng API thấp hơn để stream file thành từng phần:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

import org.postgresql.PGConnection;
import org.postgresql.largeobject.LargeObject;
import org.postgresql.largeobject.LargeObjectManager;

Path file = Path.of("upload/archive.bin");

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        PGConnection pg = conn.unwrap(PGConnection.class);
        LargeObjectManager manager = pg.getLargeObjectAPI();
        long oid = manager.createLO(
            LargeObjectManager.READWRITE
        );

        try (LargeObject lo = manager.open(
                oid, LargeObjectManager.WRITE);
             InputStream in = Files.newInputStream(file);
             var out = lo.getOutputStream()) {
            in.transferTo(out);
        }

        String sql = """
            INSERT INTO storage_lab.attachments_lo
                (file_name, media_type, content_oid)
            VALUES (?, ?, ?::oid)
            """;
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, file.getFileName().toString());
            ps.setString(2, "application/octet-stream");
            // OID được gửi dưới dạng decimal string để PostgreSQL
            // parse đúng kiểu oid (unsigned 32-bit).
            ps.setString(3, Long.toString(oid));
            ps.executeUpdate();
        }

        conn.commit();
    } catch (Exception ex) {
        try {
            conn.rollback();
        } catch (Exception rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Mẫu minh họa transaction rõ ràng. Trong code production, cần xử lý checked exceptions phù hợp với method signature và không đóng connection do transaction manager quản lý theo cách trái contract. Nếu lỗi xảy ra sau khi tạo LO nhưng trước khi commit, rollback sẽ hoàn tác object mới cùng metadata row.

### 9.3. Vì sao bind OID bằng decimal string?

PostgreSQL `oid` là kiểu OID 32-bit unsigned. Java `int` có dấu; dùng `setInt` có thể gây nhầm khi giá trị OID vượt miền số dương của int. Ví dụ bind `Long.toString(oid)` rồi cast parameter `?::oid` giúp PostgreSQL parse theo kiểu OID. Luôn kiểm tra API pgJDBC/server version cụ thể của dự án.

### 9.4. Download bằng InputStream

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

import org.postgresql.PGConnection;
import org.postgresql.largeobject.LargeObject;
import org.postgresql.largeobject.LargeObjectManager;

Path destination = Path.of("download/archive.bin");

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        long oid;
        try (PreparedStatement ps = conn.prepareStatement("""
                SELECT content_oid
                FROM storage_lab.attachments_lo
                WHERE attachment_id = ?
                """)) {
            ps.setLong(1, attachmentId);
            try (var rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException(
                        "Attachment not found"
                    );
                }
                oid = rs.getLong(1);
            }
        }

        PGConnection pg = conn.unwrap(PGConnection.class);
        LargeObjectManager manager = pg.getLargeObjectAPI();

        try (LargeObject lo = manager.open(
                oid, LargeObjectManager.READ);
             InputStream in = lo.getInputStream();
             var out = Files.newOutputStream(destination)) {
            in.transferTo(out);
        }

        conn.commit();
    } catch (Exception ex) {
        try {
            conn.rollback();
        } catch (Exception rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Chỉ mở OID sau khi đã xác thực user có quyền tải attachment tương ứng. Quyền truy cập row metadata và quyền đọc LO là hai lớp riêng; xem phần bảo mật bên dưới.

### 9.5. Seek và đọc một vùng

```java
try (LargeObject lo = manager.open(
        oid, LargeObjectManager.READ)) {
    lo.seek64(1024L * 1024L, LargeObject.SEEK_SET);
    byte[] chunk = lo.read(64 * 1024);
    // Xử lý chunk; đọc tiếp cho tới EOF nếu cần.
}
```

Ví dụ seek tới offset 1 MiB rồi đọc tối đa 64 KiB. `read(int len)` trả mảng bytes của đoạn đọc; nếu xử lý file rất lớn, đọc theo chunk và tránh tích lũy mọi chunks thành một mảng.

### 9.6. Truncate

```java
try (LargeObject lo = manager.open(
        oid, LargeObjectManager.WRITE)) {
    lo.truncate64(newLength);
}
```

Nếu độ dài mới lớn hơn kích thước hiện tại, phần mở rộng được điền bytes zero theo semantics LO. Thao tác cần transaction và quyền UPDATE trên LO.

### 9.7. Đóng descriptor và stream

`LargeObject` triển khai `AutoCloseable`. Dùng try-with-resources để đóng descriptor và stream. Descriptor còn mở khi transaction kết thúc sẽ được PostgreSQL đóng tự động, nhưng ứng dụng vẫn nên đóng tường minh để quản lý resource và lỗi rõ ràng.

### 9.8. Blob mapping của pgJDBC

pgJDBC cũng hỗ trợ `Blob`/`setBlob`/`getBlob` cho Large Object mapping. Tài liệu driver có ví dụ upload bằng `PreparedStatement.setBlob(index, inputStream, length)` và đọc qua `Blob.getBinaryStream()`. Luôn kiểm tra driver version, transaction mode và kiểu cột `oid`; các API này có semantics khác với `bytea`.

### 9.9. Không dùng một Connection đồng thời từ nhiều threads

`Connection`/LargeObject descriptor gắn với session/transaction cụ thể. Không chia sẻ cùng connection/descriptor để hai threads cùng seek/read/write; đồng bộ hóa hoặc dùng connection riêng theo thiết kế. Một descriptor không phải một file handle thread-safe độc lập.

## 10. So sánh cách ứng dụng truy cập

| Tác vụ | BYTEA | Large Object |
| --- | --- | --- |
| Upload file nhỏ đã có byte[] | `setBytes` | Có thể tạo LO nhưng phức tạp hơn. |
| Upload file qua stream | `setBinaryStream` với length chính xác | `LargeObject.getOutputStream` hoặc Blob API trong transaction. |
| Download file nhỏ | `getBytes` | `lo_get`/Blob, nhưng cần LO transaction. |
| Download file lớn | `getBinaryStream` nếu datum nằm trong giới hạn và driver stream phù hợp | LO stream theo chunks, phù hợp với file rất lớn. |
| Đọc vài bytes tại offset | `substring(bytea...)`/stream logic; phụ thuộc TOAST strategy | `seek64` rồi `read`. |
| Sửa một đoạn tại offset | Thường thay datum `bytea` theo giá trị mới | `seek64` + write. |
| Xóa dữ liệu | DELETE/UPDATE row; PostgreSQL quản lý datum | Phải quản lý reference và `lo_unlink`/cleanup. |
| Chia sẻ cùng binary | Tách bảng tài sản + FK hoặc duplicate bytes | Có thể nhiều rows giữ cùng OID, cần reference lifecycle. |

### 10.1. BYTEA có thể stream mà không cần Large Object

Một điểm dễ nhầm: dùng `getBinaryStream`/`setBinaryStream` trên `bytea` vẫn là JDBC stream API. Bạn không phải chuyển sang LO chỉ để tránh `getBytes`/`byte[]`. Sự khác biệt chính là giới hạn datum 1 GB và khả năng random access/partial write của LO.

### 10.2. LO không tự động nhanh hơn

LO có overhead OID lookup, ACL, descriptor, chunk operations và lifecycle. Nếu ứng dụng luôn tải toàn bộ file 20 KB, `bytea` thường đơn giản hơn. Benchmark với kích thước/độ truy cập thật trước khi chọn.

## 11. Vòng đời Large Object: tạo, tham chiếu, thay thế và xóa

Đây là khác biệt vận hành lớn nhất giữa `bytea` và LO.

### 11.1. Tạo object và tham chiếu phải atomic

Một transaction nên thực hiện:

1. Tạo LO.
2. Ghi nội dung LO.
3. Tạo row metadata tham chiếu OID.
4. Commit cả hai.

Nếu bước 2 hoặc 3 thất bại, rollback phải xóa cả object mới và row chưa hoàn chỉnh. Không commit LO trước rồi mới tạo row trong transaction khác nếu không có workflow phục hồi orphan.

### 11.2. Xóa row tham chiếu không tự unlink object

Ví dụ:

```sql
DELETE FROM storage_lab.attachments_lo
WHERE attachment_id = 10;
```

Lệnh chỉ xóa row. Large Object có OID được lưu trong row **vẫn còn** trong database, chiếm storage cho tới khi được unlink hoặc dọn bằng công cụ quản lý orphan.

Điều này khác `bytea`: bytes là datum của row và PostgreSQL quản lý phiên bản vật lý theo MVCC/TOAST.

### 11.3. Thay file phải xử lý OID cũ

Quy trình an toàn cho một row sở hữu LO độc lập:

1. Tạo LO mới và ghi hoàn chỉnh.
2. Trong cùng transaction, UPDATE row sang OID mới.
3. Unlink OID cũ sau khi đã xác nhận row không còn tham chiếu nó.
4. Commit.

Nếu transaction rollback, cả thay OID và tạo/xóa LO trong transaction đều được hoàn tác. Với nhiều rows có thể chia sẻ OID, **không unlink cũ chỉ vì một row đổi tham chiếu**.

### 11.4. Một object có nhiều references

PostgreSQL cho phép nhiều rows chứa cùng OID. Nhưng Large Object không có automatic reference counting theo bảng nghiệp vụ:

```text
attachments row A ─┐
                  ├── OID 70001 ── Large Object
attachments row B ─┘

DELETE row A
    không được unlink OID 70001
vì row B vẫn đang dùng object.
```

Nếu trigger hoặc ứng dụng unlink khi xóa row A, row B sẽ giữ OID hỏng.

### 11.5. Mô hình metadata trung gian khi cần chia sẻ

Một thiết kế rõ hơn là có một row asset đại diện LO; nhiều attachments tham chiếu asset bằng FK:

```sql
CREATE TABLE storage_lab.large_object_assets (
    asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_oid oid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE storage_lab.asset_attachments (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id bigint NOT NULL
        REFERENCES storage_lab.large_object_assets(asset_id)
        ON DELETE RESTRICT,
    owner_id bigint NOT NULL,
    file_name text NOT NULL
);
```

Mỗi LO có một row trong `large_object_assets`. Các nghiệp vụ khác tham chiếu `asset_id`; khi xóa attachment, object vẫn tồn tại nếu asset còn được dùng. Chỉ xóa asset khi không còn attachment nào tham chiếu, sau đó trigger trên asset mới unlink LO.

### 11.6. Kiểm tra reference count trước khi xóa asset

```sql
BEGIN;

DELETE FROM storage_lab.asset_attachments
WHERE attachment_id = 10;

DELETE FROM storage_lab.large_object_assets AS a
WHERE a.asset_id = 7
  AND NOT EXISTS (
      SELECT 1
      FROM storage_lab.asset_attachments AS x
      WHERE x.asset_id = a.asset_id
  );

COMMIT;
```

Đây là mẫu khái niệm; cần xác thực `asset_id` và thiết kế transaction/locking để đồng bộ với thao tác tạo attachment đồng thời. FK `ON DELETE RESTRICT` bảo vệ khỏi xóa asset đang được tham chiếu. Việc xóa asset chỉ xảy ra khi không còn references.

### 11.7. Race condition khi hai transactions cùng quản lý reference

Nếu một transaction kiểm tra “không còn reference” rồi unlink trong khi transaction khác đồng thời tạo reference mới, có thể xuất hiện dangling OID nếu thiếu đồng bộ. FK trên asset row giúp serialize một số thao tác, nhưng workflow phải được thiết kế để **mọi đường tạo reference đều tham gia cùng quan hệ/lock**. Không cho phép một đường ghi trực tiếp OID bỏ qua asset registry.

### 11.8. Chia sẻ file và quyền

Nếu nhiều tenants/user cùng tham chiếu một LO, quyền object ACL phải phản ánh chính sách chia sẻ. Không chỉ kiểm tra quyền row attachment rồi mặc định quyền LO cũng đã an toàn; xem phần 15.

## 12. Extension lo: domain lo và trigger lo_manage

PostgreSQL cung cấp module `lo` để giúp quản lý LO references trong các bảng.

### 12.1. Cài extension

```sql
CREATE EXTENSION IF NOT EXISTS lo;
```

Module cung cấp:

- Domain `lo` trên kiểu `oid` để phân biệt cột chứa Large Object reference.
- Trigger function `lo_manage` để gọi `lo_unlink` khi row bị xóa hoặc giá trị LO reference bị thay.

### 12.2. Ví dụ bảng có một LO reference duy nhất

```sql
CREATE TABLE storage_lab.images (
    image_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    raster lo NOT NULL
);

CREATE TRIGGER images_raster_lo_cleanup
BEFORE UPDATE OF raster OR DELETE
ON storage_lab.images
FOR EACH ROW
EXECUTE FUNCTION lo_manage(raster);
```

Trigger giả định mỗi LO được tham chiếu **duy nhất trong cột được quản lý bởi trigger**. Khi row bị DELETE hoặc cột raster được thay, trigger unlink LO cũ.

### 12.3. Giới hạn quan trọng của lo_manage

`lo_manage` **không phải garbage collector biết mọi nơi đang tham chiếu OID**. Nó giả định LO chỉ có một reference ở các cột do trigger quản lý. Nếu một OID được dùng chung bởi hai rows, trigger trên row đầu tiên có thể xóa object mà row thứ hai vẫn cần.

Không gắn `lo_manage` vào mọi bảng có OID một cách máy móc. Chỉ dùng khi ownership là unique và đã được ràng buộc bởi thiết kế.

### 12.4. UPDATE không thay cột LO

Có thể giới hạn trigger chỉ chạy khi cột LO đổi bằng `BEFORE UPDATE OF raster`. Trigger chỉ nhận các UPDATE có target list chứa cột này; vẫn phải kiểm tra logic ứng dụng và phiên bản extension cụ thể. Nếu không muốn unlink khi giá trị mới giống giá trị cũ, nên thiết kế luồng thay thế rõ và kiểm thử điều kiện OLD/NEW.

### 12.5. Nhiều cột LO

Nếu một bảng có nhiều cột chứa LO references độc lập, tạo trigger riêng cho từng cột với tên riêng và argument là tên cột tương ứng. Mỗi cột cần ownership/lifecycle rõ.

### 12.6. DROP TABLE và TRUNCATE không chạy row trigger

`lo_manage` là row-level trigger:

- `DROP TABLE` không gọi trigger cho từng row.
- `TRUNCATE` không gọi row-level DELETE triggers.

Hai thao tác này có thể để lại LO mồ côi. Nếu cần xóa rows trước khi drop, dùng `DELETE FROM table` để trigger thực thi, hoặc có quy trình cleanup LO riêng trước/sau thao tác DDL.

### 12.7. Không nhầm domain lo với cleanup tự động

`lo` chỉ là domain trên OID giúp nhận diện kiểu cột. Nó không tự tạo FK tới LO, không tự xóa object khi row bị xóa, và không tự bảo đảm reference count.

## 13. Dọn Large Objects mồ côi bằng vacuumlo

Large Object mồ côi (orphan) là LO không còn OID reference trong những cột được công cụ nhận diện. Chúng chiếm disk dù không còn được ứng dụng dùng.

### 13.1. vacuumlo làm gì?

`vacuumlo` là tiện ích client đi kèm PostgreSQL. Nó:

1. Tạo tập OIDs của các Large Objects trong database.
2. Quét các cột có kiểu `oid` hoặc `lo`.
3. Loại khỏi tập những OID đang được tham chiếu.
4. Unlink các OIDs còn lại được xem là orphan.

Đây là **công cụ xóa dữ liệu thật**, không phải lệnh VACUUM thông thường.

### 13.2. Dry-run trước khi xóa

```bash
vacuumlo -n -v my_database
```

`-n`/`--dry-run` chỉ hiển thị những object sẽ được xóa; không unlink. Xem danh sách và xác minh schema/application references trước khi chạy thật.

### 13.3. Chạy cleanup có giới hạn

```bash
vacuumlo -v -l 1000 my_database
```

`-l` giới hạn số LO bị xóa trong mỗi transaction; mặc định là 1000. PostgreSQL lấy lock theo object bị xóa, nên gom quá nhiều vào một transaction có thể vượt `max_locks_per_transaction`. Dùng batch phù hợp với dung lượng và lịch vận hành.

### 13.4. Các kiểu reference vacuumlo không nhìn thấy

`vacuumlo` quét các cột kiểu `oid` hoặc `lo` theo cách tài liệu mô tả. Nó không hiểu một OID được serialize trong:

- Cột `bigint` hoặc `text`.
- JSON/JSONB.
- Array hoặc custom encoding.
- Domain tự tạo trên OID mà công cụ không nhận diện.
- Hệ thống ngoài database.

Nếu ứng dụng lưu LO OID trong các cấu trúc này, vacuumlo có thể coi object vẫn đang dùng là orphan và xóa nhầm. Ngược lại, các cột OID không phải LO reference có thể giữ lại object không cần thiết vì công cụ thấy OID tồn tại.

### 13.5. Quy trình vận hành an toàn

1. Lập inventory tất cả cột/ứng dụng giữ LO OIDs.
2. Chuẩn hóa references vào cột kiểu `oid`/`lo` hoặc registry table có thể audit.
3. Chạy `vacuumlo -n -v` trước.
4. Kiểm tra các OIDs dự kiến xóa với chủ sở hữu dữ liệu.
5. Backup và xác nhận khả năng restore.
6. Chạy vacuumlo thật với limit phù hợp.
7. Theo dõi dung lượng, thời gian, locks và lỗi ứng dụng sau cleanup.

### 13.6. vacuumlo là backstop, không phải lifecycle chính

Thiết kế đúng nên unlink LO ngay trong transaction xóa/thay thế cuối cùng. `vacuumlo` hữu ích như bước bảo trì định kỳ để phát hiện/dọn orphan do đường code cũ, import lỗi hoặc thao tác DDL, không thay thế việc quản lý reference.

## 14. Xóa và thay file an toàn: các workflow mẫu

### 14.1. Một row sở hữu một LO (không chia sẻ)

Với ownership độc quyền, có thể tạo LO mới, cập nhật row và unlink LO cũ trong cùng transaction:

```sql
BEGIN;

-- Lấy OID cũ và khóa row để tránh hai lần thay file cùng lúc.
SELECT content_oid
FROM storage_lab.attachments_lo
WHERE attachment_id = 10
FOR UPDATE;

-- Ứng dụng tạo LO mới và ghi bytes qua LO API trong transaction.
-- Gọi new_oid là OID mới đã ghi hoàn chỉnh.

UPDATE storage_lab.attachments_lo
SET content_oid = :new_oid
WHERE attachment_id = 10;

-- Chỉ khi xác nhận LO cũ không được share:
SELECT lo_unlink(:old_oid);

COMMIT;
```

Đoạn SQL dùng placeholders `:new_oid`/`:old_oid` để mô tả các giá trị app đã nhận; cú pháp bind thực tế tùy driver. Nếu transaction lỗi, rollback khôi phục row cũ và LO cũ; LO mới được tạo trong transaction cũng rollback.

### 14.2. Xóa row sở hữu LO độc quyền

```sql
BEGIN;

SELECT content_oid
FROM storage_lab.attachments_lo
WHERE attachment_id = 10
FOR UPDATE;

DELETE FROM storage_lab.attachments_lo
WHERE attachment_id = 10;

-- Ứng dụng chỉ gọi khi đã xác minh OID độc quyền:
SELECT lo_unlink(:old_oid);

COMMIT;
```

Thứ tự xóa row rồi unlink giúp không còn row tham chiếu sau commit. Trong transaction, các thao tác đều atomic. Với foreign key/cascade và nhiều bảng tham chiếu, phải đánh giá tất cả references trước khi unlink.

### 14.3. Không unlink khi chỉ thay một trong nhiều references

Nếu cùng OID được tham chiếu từ nhiều rows, cập nhật một row chỉ nên thay reference của row ấy. Chỉ unlink khi reference cuối cùng bị xóa và việc đó được serialize bằng registry/foreign keys hoặc cơ chế refcount.

### 14.4. Soft delete

Nếu ứng dụng đánh dấu `deleted_at` thay vì DELETE, trigger DELETE không chạy và LO vẫn cần tồn tại để phục hồi/retention. Quy định thời gian retention; khi hết hạn mới unlink trong một job có kiểm soát.

### 14.5. Retention và legal hold

Một tài liệu bị ẩn khỏi giao diện không có nghĩa được phép xóa vật lý. Thiết kế trạng thái `active`, `soft_deleted`, `retained`/legal hold và thời điểm purge rõ ràng. Không để vacuumlo xóa object được lưu trong một hệ thống ngoài row references nếu inventory không phản ánh đầy đủ.

### 14.6. Audit và checksum

Metadata nên có:

- Kích thước bytes.
- SHA-256 hoặc checksum phù hợp.
- MIME type đã xác thực/sniffing, không tin hoàn toàn tên file.
- Thời điểm upload, owner/tenant và source.
- Version/retention status.
- Object OID hoặc asset ID (nếu LO).

Checksum giúp phát hiện dữ liệu hỏng khi upload/restore/migration, không phải cơ chế mã hóa.



## 15. Bảo mật: quyền trên row khác quyền trên Large Object

Large Object có owner và ACL riêng. Từ PostgreSQL 9.0, quyền trên LO được quản lý bằng GRANT/REVOKE:

- `SELECT` trên LO: được đọc nội dung.
- `UPDATE` trên LO: được ghi hoặc truncate nội dung.
- Owner (hoặc superuser): có quyền unlink, đổi owner và quản lý object theo các quy tắc tương ứng.

### 15.1. Cấp quyền cho một Large Object

```sql
-- Ví dụ OID 70001 đã tồn tại:
GRANT SELECT
ON LARGE OBJECT 70001
TO app_file_reader;

GRANT UPDATE
ON LARGE OBJECT 70001
TO app_file_writer;
```

Không cần cấp UPDATE cho role chỉ tải file. Không cấp SELECT/UPDATE cho `PUBLIC` nếu không có yêu cầu rõ ràng.

### 15.2. Quyền row không tự cấp quyền LO

Role có thể được SELECT row metadata nhưng không có SELECT privilege trên LO; lúc mở/đọc object, thao tác có thể bị từ chối. Ngược lại, role có quyền SELECT trên một LO và biết OID có thể đọc object theo ACL, dù một row tham chiếu cụ thể bị RLS lọc.

**RLS bảo vệ row trong bảng; ACL của Large Object bảo vệ object riêng.** Hai lớp này không tự đồng bộ.

### 15.3. OID không phải bí mật hay capability

OID có thể xuất hiện trong logs, query results, backups hoặc API. Không coi việc giấu OID là cơ chế authorization. Cần ACL LO đúng, quyền bảng đúng, và kiểm tra người dùng có quyền truy cập metadata asset trước khi cung cấp đường đọc.

### 15.4. Ví dụ tách role

Một mô hình:

| Role | Quyền |
| --- | --- |
| `storage_owner` | Tạo/quản lý LO, sở hữu metadata registry. |
| `app_upload` | Insert metadata và ghi LO mới trong transaction được cấp quyền. |
| `app_download` | SELECT metadata phù hợp và SELECT LO được cấp. |
| `app_reader` | Chỉ SELECT LO, không UPDATE. |
| `maintenance` | Dọn orphan/retention theo quy trình được phê duyệt. |

Không dùng table owner/superuser làm credential chung cho mọi API.

### 15.5. lo_compat_privileges

PostgreSQL có cấu hình `lo_compat_privileges` để tương thích hành vi quyền của các phiên bản cũ. Bật cấu hình này có thể thay đổi việc kiểm tra ACL LO. Không bật để chữa lỗi permission denied; hãy cấp quyền SELECT/UPDATE đúng đối tượng và kiểm thử theo role production.

### 15.6. RLS trên bảng chứa OID

Ví dụ:

```sql
ALTER TABLE app.attachments_lo
ENABLE ROW LEVEL SECURITY;

CREATE POLICY attachments_tenant_read
ON app.attachments_lo
FOR SELECT
TO app_runtime
USING (tenant_id = app.current_tenant_id());
```

Policy lọc rows trong bảng metadata. Nó **không tạo policy row-level trên `pg_largeobject` theo tenant_id**. Nếu OID bị lộ qua một đường khác và role có LO SELECT ACL, người dùng có thể truy cập object. Thiết kế ACL/ownership hoặc lớp dịch vụ phải bảo đảm phạm vi object tương ứng với phạm vi tenant.

### 15.7. Chia sẻ OID giữa tenants là rủi ro thiết kế

Nếu hai tenants cùng tham chiếu một LO, việc cấp SELECT trên LO cho tenant A cũng có thể cho tenant A đọc object mà row tenant B đang tham chiếu. Nếu muốn chia sẻ, hãy mô hình hóa đây là quyền chia sẻ có chủ đích, hoặc copy object thành LO riêng theo tenant.

### 15.8. Import/export server-side

Server-side `lo_import`/`lo_export` đọc/ghi filesystem của database server. Mặc định chỉ superuser dùng được; cấp EXECUTE cho người khác phải được đánh giá như quyền rất mạnh. Ưu tiên client-side stream qua JDBC/pgJDBC hoặc libpq để file đi qua filesystem/application được kiểm soát.

## 16. Transaction, concurrency và tính nhất quán

### 16.1. Tạo LO và metadata trong một transaction

Nếu LO và row metadata được tạo trong cùng transaction, commit thành công công bố cả hai; rollback hoàn tác cả hai. Đây là cách đơn giản nhất để tránh một LO mới không có metadata.

### 16.2. Xóa LO và xóa metadata cùng transaction

Nếu nghiệp vụ xác định LO không còn references, xóa row metadata và gọi `lo_unlink` trong cùng transaction. Nếu một bước thất bại, rollback để trạng thái không bị nửa chừng.

### 16.3. Khóa row metadata trước khi thay reference

Khi nhiều requests có thể thay cùng attachment, dùng `SELECT ... FOR UPDATE` trên row metadata để tuần tự hóa việc đọc OID cũ, tạo OID mới và cập nhật reference. Nếu có nhiều bảng tham chiếu, cần khóa/registry strategy thống nhất.

### 16.4. Không giữ transaction mở trong lúc user tương tác

Upload file có thể kéo dài. Không mở transaction, tạo LO và giữ row locks rồi chờ người dùng nhập metadata hoặc upload qua mạng chậm không giới hạn. Có thể upload vào staging/object tạm, xác minh xong rồi thực hiện transaction publish/attach; phải có TTL và cleanup cho staging.

### 16.5. Snapshot và descriptor

LO descriptor có thời hạn trong transaction. Kết thúc transaction sẽ đóng descriptor; không lưu descriptor trong object Java/session để sử dụng ở request sau. Mỗi request mở LO trong transaction của chính nó.

### 16.6. Cập nhật từng đoạn và tính nhất quán

LO hỗ trợ random writes. Nếu ứng dụng cập nhật nhiều đoạn trong nhiều transactions, readers có thể quan sát các phiên bản theo snapshot/transaction semantics. Nếu file cần thay đổi nguyên tử như một phiên bản hoàn chỉnh, cân nhắc tạo LO mới rồi chuyển metadata reference khi hoàn tất, thay vì ghi đè trực tiếp LO đang được phục vụ.

### 16.7. Versioning file

Một mô hình an toàn:

```text
Document
  |
  +-- active_version_id
           |
           v
      File version row
           |
           v
      BYTEA hoặc LO reference

Upload version mới → kiểm tra/hash → commit metadata
                  → chuyển active_version_id
                  → retention xử lý version cũ
```

Versioning giảm nguy cơ người dùng đọc file đang bị ghi dở và hỗ trợ audit/rollback. Cần định nghĩa retention và quyền truy cập các versions cũ.

## 17. Backup và restore

Large Objects là dữ liệu riêng, không phải chỉ là một OID trong bảng metadata. Backup cần chứa **cả nội dung LO lẫn các rows tham chiếu**.

### 17.1. pg_dump full database

Với dump toàn database, `pg_dump` mặc định bao gồm Large Objects, trừ khi dùng tùy chọn loại bỏ hoặc một dạng dump giới hạn nội dung. Ví dụ:

```bash
pg_dump -Fc -b -f app_backup.dump my_database
```

`-b`/`--large-objects` yêu cầu đưa LO vào archive. Với dump full database, đây thường là mặc định; ghi rõ `-b` giúp thể hiện chủ ý trong runbook.

### 17.2. Dump chọn table/schema

Nếu dùng `--table`, `--schema` hoặc `--schema-only`, LO có thể không được đưa vào theo mặc định như full dump. Một dump chỉ chứa row có OID nhưng không chứa LO sẽ restore thành metadata với reference hỏng.

Khi selective dump cần LO, xem `pg_dump --large-objects` và kiểm tra chính xác nội dung archive; lưu ý tùy chọn có thể đưa tất cả Large Objects trong database vào, không nhất thiết chỉ những LO mà bảng được chọn tham chiếu.

### 17.3. Loại bỏ LO khỏi dump

```bash
pg_dump -B -Fc -f schema_and_tables.dump my_database
```

`-B`/`--no-large-objects` cố ý loại LO. Chỉ dùng khi đã có kế hoạch backup/restore riêng cho file objects và metadata OID không được mong đợi trỏ tới nội dung vắng mặt.

### 17.4. Restore và xác minh

```bash
pg_restore -d restored_database app_backup.dump
```

Sau restore, kiểm tra:

- Rows metadata có tồn tại và OID đúng.
- Large Object thực sự mở/đọc được bằng role ứng dụng.
- Owner/ACL LO phù hợp với role ở môi trường đích.
- File bytes có đúng kích thước và checksum.
- Các row references không trỏ tới LO bị thiếu.

### 17.5. Backup vật lý

Physical backup/base backup và WAL-based recovery lưu database files/catalog/WAL theo cơ chế vật lý; Large Object được chứa trong dữ liệu database như các quan hệ hệ thống. Vẫn cần thực hiện quy trình backup/restore đã kiểm chứng và bảo vệ đầy đủ WAL/base backups.

### 17.6. Logical replication không replicate Large Objects

**PostgreSQL logical replication không replicate Large Objects.** Nếu bảng metadata có cột OID được replicate, giá trị OID có thể xuất hiện ở subscriber nhưng nội dung LO không được replicate theo cơ chế đó. Đây là rủi ro đặc biệt khi dùng logical replication cho failover hoặc read replicas.

Các cột `bytea` là dữ liệu cột của bảng thông thường và được xử lý theo cơ chế logical replication của table rows; vẫn cần xem giới hạn/version/workload, nhưng không gặp hạn chế “LO không được replicate”.

Nếu cần logical replication, lựa chọn:

- Dùng `bytea` khi kích thước/nhu cầu truy cập phù hợp.
- Tự đồng bộ object qua một pipeline có version/checksum/idempotency.
- Lưu file trong object storage bên ngoài và replicate metadata/reference độc lập.

Không giả định chỉ replicate bảng có OID là subscriber có đủ file.

### 17.7. Restore sang database khác

OID là identifier trong phạm vi database. Khi restore, pg_dump/pg_restore có thể tái tạo Large Objects và references trong cùng archive; không lấy một OID từ database A rồi mặc định nó tồn tại với cùng bytes trong database B nếu hai database được đồng bộ riêng.

## 18. Migration giữa BYTEA và Large Object

Migration cần xử lý cả dữ liệu lẫn lifecycle, không chỉ đổi kiểu cột.

### 18.1. BYTEA → LO cho dữ liệu nhỏ hơn giới hạn

Thêm cột OID mới:

```sql
ALTER TABLE storage_lab.attachments_bytea
ADD COLUMN content_oid oid;
```

Với dữ liệu nhỏ/vừa, có thể chuyển trong transaction theo batch:

```sql
UPDATE storage_lab.attachments_bytea
SET content_oid = lo_from_bytea(0, content)
WHERE content_oid IS NULL
RETURNING attachment_id, content_oid;
```

`lo_from_bytea` nhận `bytea`, nên cách này chỉ phù hợp với datum có thể materialize và nằm trong giới hạn `bytea`. Không dùng một UPDATE khổng lồ cho hàng triệu file; chia batch và kiểm tra kết quả.

### 18.2. BYTEA → LO cho file rất lớn

Một file vượt 1 GB không thể nằm trong một datum `bytea`. Nếu nguồn hiện tại là external storage, dùng application stream trực tiếp vào LO. Nếu nguồn là `bytea`, nó vốn đã nằm trong giới hạn đó; dùng JDBC `getBinaryStream` để chuyển theo chunk thay vì `getBytes` nếu không muốn giữ toàn bộ file trong heap.

### 18.3. Xác minh trước khi cutover

Cho mỗi row:

- OID mới không NULL.
- LO mở/đọc được.
- `octet_length`/kích thước LO phù hợp.
- SHA-256 của nội dung mới bằng nguồn.
- Row metadata vẫn đúng tenant/owner/file name.

Chỉ chuyển application sang đọc OID sau khi dữ liệu đã được xác minh theo batch.

### 18.4. BYTEA cũ chỉ xóa sau khi hoàn tất

Giữ cột cũ trong giai đoạn rollback/canary. Sau khi ứng dụng đã dùng LO ổn định và backup/restore được kiểm chứng, mới bỏ cột BYTEA trong migration riêng. Không drop cột cũ trước khi xác minh tất cả references và consumer paths.

### 18.5. LO → BYTEA

Chỉ chuyển LO có kích thước phù hợp giới hạn datum `bytea`. Với object lớn hơn 1 GB, không thể lưu nguyên thành một cột `bytea` duy nhất.

Ví dụ cho LO nhỏ:

```sql
ALTER TABLE storage_lab.attachments_lo
ADD COLUMN content_bytea bytea;

UPDATE storage_lab.attachments_lo
SET content_bytea = lo_get(content_oid)
WHERE content_bytea IS NULL;
```

`lo_get` materialize nội dung thành `bytea`. Chỉ dùng cho objects nhỏ/vừa và kiểm soát memory; với dữ liệu lớn hơn, stream qua application và áp giới hạn kích thước trước khi chuyển.

### 18.6. Unlink LO sau khi chuyển

Chỉ unlink OID cũ sau khi:

1. Nội dung BYTEA mới được ghi và checksum đúng.
2. Tất cả consumers đã chuyển sang cột mới.
3. Không còn row nào khác tham chiếu OID cũ.
4. Backup/rollback window đã hết theo chính sách.

Nếu dùng LO share nhiều references, cần reference registry/refcount chứ không chỉ kiểm tra row hiện tại.

### 18.7. Batch migration và restart

Với hàng triệu rows, migration nên có checkpoint theo khóa chính, batch size, metrics và retry. Mỗi batch commit riêng; thao tác phải idempotent để job chạy lại không tạo LO mới cho row đã migrate hoặc để orphan do OID mới không được ghi metadata. Nếu tạo object rồi lỗi trước khi update row, transaction rollback hoặc job cleanup phải xử lý.

## 19. Hiệu năng và vận hành

### 19.1. Khi BYTEA hiệu quả

- Nội dung tương đối nhỏ/vừa.
- Ứng dụng thường đọc toàn bộ cùng metadata.
- Muốn tận dụng TOAST compression cho file/text có thể nén.
- Cần transaction, FK, RLS và DML chuẩn mà không quản lý OID riêng.
- Không cần seek/write từng đoạn trong object.

### 19.2. Khi Large Object hiệu quả

- Nội dung lớn tới nhiều GB/TB.
- Ứng dụng đọc/ghi theo chunks.
- Có yêu cầu random access/seek.
- Không muốn materialize toàn bộ datum trong một lần.
- Hệ thống chấp nhận chi phí lifecycle, ACL, cleanup và backup riêng.

### 19.3. TOAST compression

`bytea` mặc định thường dùng chiến lược `EXTENDED`; PostgreSQL có thể nén trước khi lưu out-of-line. File đã nén (JPEG, MP4, ZIP, PDF nén) thường ít giảm kích thước thêm. Nén có thể tăng CPU và làm random substring phải giải nén dữ liệu; cân nhắc compression strategy theo workload.

### 19.4. Large Object random access

LO chia chunks và dùng B-tree index để tìm chunk theo vị trí. Điều này phù hợp khi client chỉ cần đọc một đoạn lớn/nhỏ ở offset cụ thể mà không kéo toàn object. Tuy nhiên nhiều lần đọc chunks qua network vẫn có round trips; chọn chunk size ứng dụng và buffer hợp lý.

### 19.5. I/O và WAL

Cả BYTEA và LO đều tạo dữ liệu trong PostgreSQL và chịu WAL, backup, replication vật lý, storage pressure. Một file upload lớn có thể tạo lượng WAL đáng kể. Cần đo:

- Upload/download throughput.
- WAL volume và replication lag.
- Database disk growth.
- Shared buffers/cache hit và I/O.
- Application heap/GC.
- Transaction duration và lock waits.
- Backup size/time và restore time.

### 19.6. Quan sát kích thước bảng

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('storage_lab.attachments_bytea')
    ) AS heap_size,
    pg_size_pretty(
        pg_total_relation_size('storage_lab.attachments_bytea')
    ) AS total_with_toast_indexes;

SELECT
    pg_size_pretty(pg_total_relation_size('pg_largeobject'))
        AS large_object_storage,
    pg_size_pretty(
        pg_total_relation_size('pg_largeobject_metadata')
    ) AS large_object_metadata;
```

Đây là chỉ số mức quan hệ, không phải phép tính chính xác “dung lượng của từng tenant/file”. Quyền đọc catalog/system relations phụ thuộc role. Trên production, dùng quyền giám sát phù hợp.

### 19.7. VACUUM và LO

`lo_unlink` xóa object theo API và xóa các chunks/metadata theo transaction; không đồng nghĩa disk file hệ điều hành thu nhỏ ngay lập tức. MVCC và VACUUM xử lý dead tuples/space reuse theo cơ chế PostgreSQL. `vacuumlo` là tiện ích dọn LO mồ côi; nó khác `VACUUM` thông thường.

### 19.8. Dung lượng không chỉ nằm ở bytes file

Tính cả:

- Metadata rows, indexes và TOAST/LO catalogs.
- Nhiều versions nếu ứng dụng giữ history.
- Orphan objects chưa dọn.
- WAL/archive và backup copies.
- Replica/standby storage.
- Temporary staging và object upload thất bại.

## 20. Khi nào nên lưu file ngoài PostgreSQL?

PostgreSQL rất phù hợp khi file là một phần quan trọng của transaction và quy mô/kích thước phù hợp. Nhưng với video lớn, ảnh phân phối qua CDN hoặc dữ liệu cần lifecycle/tiered storage, object storage có thể phù hợp hơn.

### 20.1. Lưu metadata và object key

```sql
CREATE TABLE app.file_assets (
    asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    storage_provider text NOT NULL,
    object_key text NOT NULL,
    media_type text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    sha256_hex text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (storage_provider, object_key)
);
```

DB lưu metadata/authorization, object store giữ bytes. Backend xác thực quyền rồi cấp signed URL/stream phù hợp.

### 20.2. Giao dịch DB và object store không atomic tự nhiên

Một upload có thể lưu object thành công nhưng INSERT metadata thất bại, hoặc metadata commit nhưng object upload lỗi. Cần workflow staging:

1. Upload vào key tạm.
2. Xác minh size/checksum.
3. Trong transaction DB, tạo metadata trạng thái ready.
4. Promote/copy object hoặc đổi trạng thái theo provider.
5. Có cleanup job cho staging objects mồ côi.

### 20.3. So sánh theo yêu cầu

| Nhu cầu | PostgreSQL BYTEA/LO | Object storage |
| --- | --- | --- |
| Cùng transaction với metadata | Có, trong DB transaction. | Không có atomic transaction chung với DB. |
| Phục vụ file công khai/CDN | Cần app/proxy hoặc gateway. | Thường thuận tiện hơn. |
| SQL constraints/joins với metadata | Trực tiếp. | Metadata trong DB; bytes ngoài. |
| Dung lượng rất lớn và nhiều lượt tải | Tăng tải DB/WAL/backup. | Thường tối ưu hơn cho phân phối object. |
| Backup consistency | Cùng DB backup nếu bao gồm LO/bytea. | Cần backup riêng object và metadata. |
| Lifecycle | Transaction/trigger/cleanup. | Bucket lifecycle, versioning, retention; vẫn cần sync metadata. |

Không có lựa chọn đúng cho mọi hệ thống. Đưa ra quyết định theo workload, RPO/RTO, compliance, chi phí network/storage và khả năng vận hành.

## 21. Case study

### 21.1. Case A: ảnh đại diện 100–500 KB

**Yêu cầu:** ảnh gắn với user, thường tải cùng hồ sơ, có giới hạn kích thước upload và cần transaction với metadata.

**Lựa chọn phù hợp ban đầu:** `bytea`.

Lý do:

- Dễ quản lý bằng một row và FK.
- Xóa user/ảnh theo transaction và FK policy rõ.
- Không cần OID, ACL LO hoặc orphan cleanup.
- TOAST tự xử lý khi row rộng.

Nếu ảnh được phân phối tới hàng triệu requests qua CDN, object storage có thể phù hợp hơn; nhưng không cần Large Object chỉ vì ảnh là binary.

### 21.2. Case B: video 8 GB cần đọc theo offset

**Yêu cầu:** file lớn hơn giới hạn datum `bytea` và API cho phép đọc một đoạn từ offset.

Large Object phù hợp hơn hai kiểu trong PostgreSQL vì có giới hạn tới 4 TB và hỗ trợ seek/read chunks. Cần thiết kế:

- Stream upload/download theo chunks.
- OID metadata, ownership và ACL.
- Lifecycle xóa/thay thế và orphan cleanup.
- Backup/restore đầy đủ LO.
- Lưu ý logical replication không replicate LO.

Nếu cần phân phối video ra Internet/CDN với traffic lớn, object storage có thể là lựa chọn vận hành tốt hơn.

### 21.3. Case C: tài liệu PDF 15 MB, nhiều metadata và audit

Nếu PDF luôn đọc toàn bộ và cần atomic cùng row metadata, `bytea` có thể đơn giản. Nếu hệ thống cần seek/partial range và file sẽ tăng nhiều GB, đánh giá LO hoặc object storage. Đừng chọn chỉ theo số MB; benchmark kiểu truy cập và số lượt tải.

### 21.4. Case D: nhiều records cùng trỏ một file mẫu

**Yêu cầu:** nhiều invoice cùng sử dụng một PDF điều khoản giống nhau.

Có thể dùng một asset row duy nhất, các invoices FK tới asset. Nếu asset giữ LO, xóa LO chỉ khi asset không còn references. Một bảng registry giúp quản lý quyền, retention và lifecycle dễ hơn việc lặp cùng OID trong nhiều bảng.

### 21.5. Case E: logical replication làm subscriber đọc file

Nếu metadata table replicate nhưng LO không replicate, subscriber có thể có OID không đọc được. Cần chuyển binary thành `bytea` trong bảng replicate, dùng object storage đồng bộ riêng, hoặc thiết kế pipeline truyền LO. Không coi row OID replicated là file đã có ở subscriber.

### 21.6. Case F: ứng dụng dùng JDBC và xóa attachment

Một DAO chỉ DELETE row `attachments_lo` rồi kết thúc có thể để lại LO mồ côi. Cần:

- Gọi unlink trong cùng transaction nếu LO độc quyền.
- Hoặc xóa asset registry row cuối cùng để trigger unlink.
- Hoặc chạy cleanup định kỳ đã kiểm tra dry-run.

Kiểm thử xóa, thay file, rollback và nhiều references đồng thời.

## 22. Những sai lầm thường gặp

### Sai lầm 1. Nghĩ BYTEA luôn nằm inline trong heap

BYTEA là giá trị cột về mặt SQL, nhưng TOAST có thể nén và lưu out-of-line. Không tự tạo bảng chunks chỉ để lưu file lớn.

### Sai lầm 2. Nghĩ TOAST làm BYTEA không giới hạn

TOAST-able datum vẫn có giới hạn logic 1 GB. Chia thành chunks vật lý không làm một datum vượt giới hạn này.

### Sai lầm 3. Dùng getBytes cho file rất lớn

`getBytes` materialize toàn bộ dữ liệu vào Java byte array, có thể gây heap pressure/OutOfMemoryError. Dùng stream khi phù hợp và giới hạn kích thước.

### Sai lầm 4. Cho rằng BYTEA stream có nghĩa kích thước không giới hạn

JDBC stream API không bỏ giới hạn 1 GB của một `bytea` datum hoặc giới hạn của driver/application.

### Sai lầm 5. Xóa row LO và nghĩ file tự xóa

OID chỉ là reference. Phải quản lý unlink hoặc cleanup.

### Sai lầm 6. Unlink LO trước khi kiểm tra shared references

Nếu row khác còn tham chiếu cùng OID, row đó sẽ bị dangling reference. Cần unique ownership hoặc registry/refcount.

### Sai lầm 7. Gắn lo_manage vào cột LO dùng chung

Trigger `lo_manage` giả định reference độc quyền trong cột được quản lý. Nếu LO được chia sẻ, trigger có thể xóa object khi một reference bị xóa.

### Sai lầm 8. Tin lo_manage xử lý DROP TABLE/TRUNCATE

Row-level trigger không chạy cho các thao tác đó. Cần DELETE hoặc cleanup riêng.

### Sai lầm 9. Chạy vacuumlo mà không dry-run

Một reference được lưu dưới custom domain/kiểu không được quét có thể khiến vacuumlo coi LO còn dùng là orphan. Dùng `-n` trước và kiểm tra inventory.

### Sai lầm 10. Dùng OID làm authorization token

OID không phải secret/capability. ACL LO, quyền metadata và authorization application phải đúng.

### Sai lầm 11. Nghĩ RLS trên row bảo vệ nội dung LO trực tiếp

RLS lọc row chứa OID; LO có ACL riêng. OID bị lộ cùng quyền LO có thể mở đường truy cập ngoài ý định.

### Sai lầm 12. Chỉ GRANT SELECT trên bảng metadata

Đọc row OID không tự cấp SELECT trên Large Object. Cần GRANT quyền LO phù hợp; đồng thời không cấp quyền rộng.

### Sai lầm 13. Dùng lo_import server-side cho upload web

Hàm server-side truy cập filesystem của PostgreSQL server và có rủi ro cao. Ưu tiên stream từ client/application qua JDBC/LO API.

### Sai lầm 14. Dùng lo_get để tải file nhiều GB

`lo_get` trả `bytea`. Nó phù hợp với nội dung/đoạn nhỏ; dùng LO stream cho file lớn.

### Sai lầm 15. Dùng API 32-bit cho LO lớn hơn 2 GB

`lo_lseek`/`lo_tell`/`lo_truncate` có giới hạn 2 GB. Dùng 64-bit variants và driver API tương ứng.

### Sai lầm 16. Mở Large Object trong autocommit

LO descriptors chỉ hợp lệ trong transaction. Bật autocommit false hoặc dùng transaction manager rõ ràng.

### Sai lầm 17. Giữ descriptor qua nhiều requests

Descriptor gắn với transaction/session. Lưu OID trong metadata, mỗi transaction mở descriptor mới và đóng sau khi dùng.

### Sai lầm 18. Cập nhật OID nhưng quên xóa LO cũ

Row có thể trỏ file mới nhưng file cũ vẫn chiếm storage. Cần workflow replace và cleanup.

### Sai lầm 19. Drop table có trigger cleanup rồi kỳ vọng trigger chạy

DROP TABLE không phát row DELETE triggers. Dùng DELETE trước hoặc cleanup độc lập.

### Sai lầm 20. Nghĩ pg_dump table-only luôn mang LO theo

Selective dump có thể loại LO theo mặc định. Xem tùy chọn `-b` và kiểm tra archive.

### Sai lầm 21. Dùng logical replication và mong LO tự xuất hiện ở subscriber

Large Objects không được logical replication replicate. Cần lựa chọn lưu trữ hoặc pipeline đồng bộ khác.

### Sai lầm 22. Dùng hash làm bằng chứng an toàn tuyệt đối

Hash giúp xác minh integrity nhưng không chứng minh file hợp lệ, không malware và không được upload bởi user có quyền. Cần validation/authorization riêng.

### Sai lầm 23. Chỉ lưu filename và content type từ client

Tên file/MIME type do client gửi có thể giả mạo. Validate extension, sniff content, giới hạn size và lưu metadata đã chuẩn hóa.

### Sai lầm 24. Không tính WAL/backup/replica storage

Binary trong DB làm tăng WAL, backup, restore và disk usage. Đo toàn hệ thống chứ không chỉ thời gian upload.

### Sai lầm 25. Chuyển LO về BYTEA dù object lớn hơn 1 GB

Một LO 4 GB không thể được lưu nguyên thành một `bytea` datum. Chọn object storage hoặc giữ LO; không cố materialize qua `lo_get`.

## 23. Bài tập thực hành

Các bài dùng schema `storage_lab` trong phần 6–7. Chạy trong database lab, không thực hiện unlink/vacuumlo trên production. Các câu có placeholder OID hoặc file path cần thay bằng giá trị hợp lệ của môi trường.

### Bài 1. Mô hình dữ liệu

Giải thích khác nhau giữa cột `content bytea` và `content_oid oid`. Cột nào chứa bytes?

### Bài 2. Giới hạn

Nêu giới hạn logical size của một `bytea` datum và kích thước tối đa Large Object theo tài liệu PostgreSQL.

### Bài 3. TOAST

TOAST có tự động chia một `bytea` lớn thành chunks không? Ứng dụng có cần biết tên TOAST table để đọc file không?

### Bài 4. Storage strategy

Phân biệt `EXTENDED` và `EXTERNAL`. Khi nào EXTERNAL có thể giúp substring?

### Bài 5. BYTEA insert

Viết INSERT dùng `decode(hex,'hex')` để lưu bytes “Hi” và đặt `content_length` đúng.

### Bài 6. BYTEA size

Viết SELECT lấy số bytes của content trong bảng lab bằng hàm phù hợp.

### Bài 7. JDBC BYTEA upload

Viết đoạn Java dùng `setBinaryStream` để upload một file vào cột `bytea`; vì sao phải biết length?

### Bài 8. JDBC BYTEA download

So sánh `getBytes` và `getBinaryStream` về memory.

### Bài 9. Tạo LO

Viết SQL tạo LO rỗng và lấy OID trả về.

### Bài 10. Tạo LO từ BYTEA

Viết câu `lo_from_bytea` tạo object chứa bytes “Hello”.

### Bài 11. Đọc LO

Viết câu `lo_get` đọc 20 bytes đầu từ OID 12345.

### Bài 12. Ghi LO

Viết câu `lo_put` ghi chuỗi UTF-8 “PG” vào offset 0 của OID 12345.

### Bài 13. Unlink

Viết câu xóa Large Object OID 12345 và nêu ai được phép unlink.

### Bài 14. Row delete

Sau `DELETE FROM attachments_lo WHERE attachment_id=10`, Large Object được tham chiếu có tự bị xóa không?

### Bài 15. JDBC LO transaction

Vì sao pgJDBC yêu cầu Large Object API chạy trong transaction? Cần đặt autocommit thế nào?

### Bài 16. LargeObjectManager

Viết Java lấy `LargeObjectManager` từ `PGConnection` và tạo LO mới.

### Bài 17. Seek64

Vì sao file LO lớn hơn 2 GB cần API seek/tell/truncate 64-bit?

### Bài 18. lo_manage

Viết câu tạo extension `lo` và trigger cleanup cho cột `raster lo` khi UPDATE/DELETE.

### Bài 19. Shared OID

Hai rows cùng tham chiếu một OID. Vì sao gắn `lo_manage` trực tiếp lên cả hai có thể xóa nhầm file?

### Bài 20. vacuumlo

Viết lệnh dry-run để liệt kê LO mồ côi; giải thích vì sao cần xem kết quả trước khi xóa thật.

### Bài 21. TRUNCATE

Vì sao `TRUNCATE` bảng có LO OIDs có thể để lại orphan dù đã có lo_manage trigger?

### Bài 22. ACL

Viết GRANT chỉ cho role `app_file_reader` đọc LO OID 12345. Role cần quyền gì để ghi?

### Bài 23. RLS

Bảng metadata có RLS giới hạn tenant. Vì sao điều đó không tự đảm bảo ACL của Large Object cũng được giới hạn theo tenant?

### Bài 24. Backup

Với pg_dump chọn riêng một bảng metadata có OID, cần xem tùy chọn nào để dump cả Large Objects?

### Bài 25. Logical replication

Large Objects có được logical replication replicate không? Nếu subscriber phải tải file, đề xuất hai giải pháp.

### Bài 26. BYTEA → LO

Viết SQL chuyển cột bytea nhỏ sang LO OID mới và nêu điều kiện giới hạn.

### Bài 27. LO → BYTEA

Vì sao không thể chuyển một LO 2 GB thành một cột bytea duy nhất? Viết câu lệnh minh họa cho LO nhỏ.

### Bài 28. Replace file

Nêu trình tự an toàn khi thay LO độc quyền của một attachment, bao gồm rollback.

### Bài 29. Reference registry

Thiết kế một bảng asset và FK để nhiều attachments chia sẻ một LO, nhưng chỉ unlink khi asset cuối cùng bị xóa.

### Bài 30. Lựa chọn công nghệ

Một hệ thống lưu ảnh 200 KB, video 6 GB, cần CDN và logical replication metadata. Chọn BYTEA, LO hay object storage cho từng loại và giải thích.

## 24. Gợi ý lời giải bài tập

### Đáp án 1. Mô hình

`content bytea` chứa trực tiếp binary datum của row. `content_oid oid` chỉ chứa OID tham chiếu tới Large Object riêng; bytes được lưu trong hệ thống LO.

### Đáp án 2. Giới hạn

Một TOAST-able datum như `bytea` có giới hạn logical size **1 GB**. Large Object có thể tới **4 TB** theo tài liệu PostgreSQL; khi vượt 2 GB phải dùng các API offset/size 64-bit.

### Đáp án 3. TOAST

Có. PostgreSQL tự nén và/hoặc chia giá trị lớn thành chunks trong TOAST table khi cần. Ứng dụng vẫn đọc/ghi qua cột `bytea` bình thường; không truy cập trực tiếp TOAST table.

### Đáp án 4. EXTENDED và EXTERNAL

`EXTENDED` cho phép nén và lưu out-of-line; mặc định phổ biến. `EXTERNAL` lưu out-of-line nhưng không nén; có thể giúp thao tác substring trên bytea/text lớn chỉ đọc phần cần thiết, đổi lại tốn storage. Cần benchmark.

### Đáp án 5. BYTEA insert

```sql
INSERT INTO storage_lab.attachments_bytea (
    file_name, media_type, content, content_length
)
VALUES (
    'hi.txt',
    'text/plain',
    decode('4869', 'hex'),
    2
);
```

### Đáp án 6. Kích thước

```sql
SELECT
    attachment_id,
    octet_length(content) AS byte_count
FROM storage_lab.attachments_bytea;
```

### Đáp án 7. JDBC BYTEA upload

```java
long length = Files.size(path);
try (InputStream in = Files.newInputStream(path);
     PreparedStatement ps = conn.prepareStatement(
         "INSERT INTO storage_lab.attachments_bytea " +
         "(file_name,media_type,content,content_length) " +
         "VALUES (?,?,?,?)")) {
    ps.setString(1, path.getFileName().toString());
    ps.setString(2, "application/octet-stream");
    ps.setBinaryStream(3, in, length);
    ps.setLong(4, length);
    ps.executeUpdate();
}
```

Driver cần biết số bytes cần đọc từ stream; không phải mọi overload đều hỗ trợ unknown length. Với BYTEA, vẫn phải nằm trong giới hạn datum 1 GB.

### Đáp án 8. getBytes và getBinaryStream

`getBytes` tạo `byte[]` chứa toàn bộ giá trị trong heap. `getBinaryStream` cho phép consumer đọc dần và giảm nhu cầu giữ một mảng liên tục lớn, nhưng vẫn chịu giới hạn BYTEA, buffering và lifetime của ResultSet/Connection.

### Đáp án 9. Tạo LO

```sql
SELECT lo_create(0) AS new_oid;
```

`0` yêu cầu PostgreSQL tự cấp OID.

### Đáp án 10. lo_from_bytea

```sql
SELECT lo_from_bytea(
    0,
    convert_to('Hello', 'UTF8')
) AS new_oid;
```

Đây là ví dụ payload nhỏ; không dùng bytea trung gian cho file rất lớn.

### Đáp án 11. Đọc LO

```sql
SELECT lo_get(12345, 0, 20);
```

Offset Large Object bắt đầu từ 0; kết quả là bytea của đoạn đọc.

### Đáp án 12. Ghi LO

```sql
SELECT lo_put(
    12345,
    0,
    convert_to('PG', 'UTF8')
);
```

Thao tác phải diễn ra trong transaction và caller cần quyền UPDATE trên LO.

### Đáp án 13. Unlink

```sql
SELECT lo_unlink(12345);
```

Chỉ owner của LO hoặc superuser có quyền unlink. Cần chắc chắn không còn references hợp lệ trước khi xóa.

### Đáp án 14. Row delete

Không. DELETE xóa row tham chiếu, không tự xóa Large Object. Cần gọi `lo_unlink`/trigger phù hợp hoặc cleanup job.

### Đáp án 15. Transaction JDBC

LO descriptor chỉ hợp lệ trong transaction; các API thao tác LO cần transaction block. Đặt `conn.setAutoCommit(false)`, đóng descriptor/stream và commit hoặc rollback.

### Đáp án 16. LargeObjectManager

```java
conn.setAutoCommit(false);
PGConnection pg = conn.unwrap(PGConnection.class);
LargeObjectManager manager = pg.getLargeObjectAPI();
long oid = manager.createLO(
    LargeObjectManager.READWRITE
);
```

Sau đó mở object, ghi bytes, lưu OID vào metadata và commit trong cùng transaction.

### Đáp án 17. Seek64

API offset 32-bit không thể biểu diễn vị trí lớn hơn 2 GB. Dùng `seek64`/`size64`/`truncate64` (pgJDBC) hoặc các hàm libpq 64-bit để truy cập object lớn.

### Đáp án 18. lo_manage

```sql
CREATE EXTENSION IF NOT EXISTS lo;

CREATE TABLE storage_lab.image_files (
    image_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    raster lo NOT NULL
);

CREATE TRIGGER image_files_raster_cleanup
BEFORE UPDATE OF raster OR DELETE
ON storage_lab.image_files
FOR EACH ROW
EXECUTE FUNCTION lo_manage(raster);
```

Chỉ dùng nếu mỗi LO được tham chiếu độc quyền qua cột trigger quản lý.

### Đáp án 19. Shared OID

Trigger trên row A có thể gọi `lo_unlink` khi row A bị xóa, nhưng row B vẫn chứa cùng OID. B sẽ thành dangling reference. `lo_manage` giả định references là unique; dùng asset registry/refcount nếu cần chia sẻ.

### Đáp án 20. vacuumlo

```bash
vacuumlo -n -v my_database
```

Dry-run cho biết objects dự kiến xóa. Kiểm tra trước vì tool chỉ quét các cột `oid`/`lo` được nhận diện, không biết OID được lưu trong text/json/custom type hay hệ thống ngoài.

### Đáp án 21. TRUNCATE

`TRUNCATE` không chạy row-level DELETE triggers. `lo_manage` không được gọi cho từng row nên LO có thể còn lại. Dùng DELETE trước hoặc cleanup riêng; tránh TRUNCATE nếu chưa xử lý LO lifecycle.

### Đáp án 22. ACL

```sql
GRANT SELECT
ON LARGE OBJECT 12345
TO app_file_reader;
```

Để ghi/truncate, role cần `UPDATE` privilege trên LO. Unlink thuộc owner/superuser.

### Đáp án 23. RLS

RLS chỉ lọc row metadata. Large Object có ACL riêng; người biết OID và có SELECT ACL có thể đọc LO dù row metadata cụ thể không hiện theo RLS. Phải kiểm soát object ACL/ownership và không lộ OID.

### Đáp án 24. Backup

Khi dump chọn table/schema, xem `pg_dump --large-objects` hoặc `-b` vì LO có thể không được bao gồm mặc định trong selective dump. Dump full database thường đã bao gồm LO trừ khi loại bỏ; kiểm tra archive/restore.

### Đáp án 25. Logical replication

Không. Large Objects không được logical replication replicate. Giải pháp:

1. Lưu nội dung phù hợp trong `bytea` như một cột của bảng được publish (nếu kích thước phù hợp).
2. Dùng object storage/pipeline đồng bộ LO riêng kèm checksum/version/metadata và xử lý lỗi.

### Đáp án 26. BYTEA sang LO

```sql
ALTER TABLE storage_lab.attachments_bytea
ADD COLUMN content_oid oid;

UPDATE storage_lab.attachments_bytea
SET content_oid = lo_from_bytea(0, content)
WHERE content_oid IS NULL;
```

Chỉ phù hợp khi từng datum BYTEA nằm trong giới hạn 1 GB và có thể materialize. Với dữ liệu lớn/production, batch và kiểm chứng checksum; dùng stream API nếu cần.

### Đáp án 27. LO sang BYTEA

Một `bytea` datum không thể vượt 1 GB. Với LO nhỏ:

```sql
UPDATE storage_lab.attachments_lo
SET content_bytea = lo_get(content_oid)
WHERE attachment_id = 10;
```

Chỉ dùng khi object đủ nhỏ và memory phù hợp; không gọi lo_get để materialize object 2 GB thành bytea.

### Đáp án 28. Replace file

Khóa row metadata; tạo LO mới và stream bytes trong transaction; xác minh size/checksum; UPDATE reference sang OID mới; nếu OID cũ độc quyền thì unlink trong cùng transaction; commit. Nếu lỗi, rollback giữ row/OID cũ và xóa LO mới.

### Đáp án 29. Reference registry

Tạo bảng `assets(asset_id PK, content_oid UNIQUE)`, attachments có FK `asset_id REFERENCES assets ON DELETE RESTRICT`. Chỉ xóa asset khi không còn attachment references; trigger `lo_manage` trên asset row có thể unlink vì mỗi OID chỉ xuất hiện trong registry một lần. Không cho các bảng khác lưu OID trực tiếp ngoài registry.

### Đáp án 30. Lựa chọn công nghệ

- Ảnh 200 KB: `bytea` là lựa chọn đơn giản nếu tải cùng metadata; object storage cũng hợp lý nếu phục vụ CDN nhiều.
- Video 6 GB: không thể lưu thành một `bytea` datum. LO hỗ trợ dung lượng/seek nhưng logical replication không replicate LO và CDN traffic có thể làm DB chịu tải lớn; object storage thường phù hợp hơn.
- Metadata: giữ trong PostgreSQL và logical replication bình thường; đồng bộ object bytes bằng cơ chế object storage/version/checksum riêng.

## 25. Checklist thiết kế BYTEA/LO

### 25.1. Chọn kiểu lưu

1. Kích thước file tối đa và percentile thực tế là bao nhiêu?
2. Ứng dụng đọc toàn bộ hay seek/partial read/write?
3. Có thể dùng `bytea` và TOAST trong giới hạn 1 GB không?
4. LO có thực sự cần thiết so với object storage không?
5. Workload có logical replication/failover subscriber cần binary không?

### 25.2. Metadata và lifecycle

6. Mỗi LO có một owner/reference duy nhất hay được share?
7. Có registry/refcount nếu chia sẻ không?
8. Khi upload lỗi, transaction rollback có xóa LO mới không?
9. Khi replace/delete, OID cũ được unlink khi nào?
10. Có soft delete, retention, legal hold và purge policy không?
11. Có dùng lo_manage đúng giả định unique reference không?
12. Có tránh TRUNCATE/DROP làm orphan không?
13. Có vacuumlo dry-run và inventory references không?

### 25.3. Bảo mật

14. Table permissions/RLS có đúng tenant không?
15. LO ACL SELECT/UPDATE có được cấp tối thiểu không?
16. Có lộ OID ra client/logs không?
17. Có phân biệt quyền đọc row metadata với quyền đọc LO không?
18. Có tránh server-side lo_import/lo_export cho role ứng dụng không?
19. Có kiểm tra content size/type/hash và quét malware phù hợp không?

### 25.4. JDBC và transaction

20. BYTEA upload dùng stream và length chính xác không?
21. Download dùng InputStream thay byte[] cho file lớn không?
22. LO API chạy trong transaction và descriptor/streams được đóng không?
23. Không giữ connection/transaction trong lúc user tương tác hoặc chờ network lâu không?
24. Connection pool/transaction manager có trả connection về trạng thái hợp lệ không?

### 25.5. Backup và vận hành

25. pg_dump selective có include LO không?
26. Restore có xác minh cả metadata, OID, bytes và ACL không?
27. Logical replication có đang cần binary ở subscriber không?
28. WAL/backup/replica storage có được tính vào capacity planning không?
29. Có checksum/metrics upload/download/orphan/cleanup không?
30. Có migration/rollback plan đã được kiểm thử trên bản sao dữ liệu không?

## 26. Tổng kết

**`bytea` và Large Object đều lưu được binary trong PostgreSQL, nhưng có mô hình và trách nhiệm vận hành khác nhau.**

Những điểm cốt lõi:

- `bytea` là giá trị cột, có giới hạn logic 1 GB. TOAST tự nén và/hoặc lưu out-of-line khi row quá lớn; ứng dụng không phải quản lý chunks.
- Large Object lưu nội dung riêng theo OID, chia chunks, hỗ trợ streaming và random access, với kích thước tới 4 TB.
- Với JDBC, `bytea` dùng `setBytes`/`getBytes` hoặc binary streams; LO dùng LargeObject API/Blob mapping và **bắt buộc chạy trong transaction**.
- Xóa row chứa OID **không tự xóa LO**. Phải quản lý `lo_unlink`, reference ownership hoặc cleanup.
- `lo_manage` hữu ích cho unique references, nhưng giả định mỗi LO chỉ có một reference trong cột được quản lý; nó không xử lý DROP TABLE/TRUNCATE.
- `vacuumlo` là backstop để dọn orphan, phải dry-run và bảo đảm mọi OID reference đều nằm trong kiểu cột được tool nhận diện.
- ACL LO tách khỏi table privileges/RLS; OID không phải secret. Bảo vệ object và metadata cùng nhau.
- pg_dump full database thường bao gồm LO, nhưng selective dump cần kiểm tra `-b`; logical replication **không** replicate Large Objects.
- Khi cần CDN, file cực lớn hoặc logical replication, object storage có thể phù hợp hơn, với metadata và lifecycle đồng bộ rõ ràng.

Nguyên tắc thực hành:

> **Chọn BYTEA cho binary gắn với row và dễ quản lý; chọn Large Object khi thật sự cần kích thước lớn hoặc random access, đồng thời thiết kế ownership, ACL và cleanup ngay từ đầu.**

## 27. Tài liệu tham khảo

Tài liệu chính thức; chọn đúng major PostgreSQL và phiên bản pgJDBC đang sử dụng:

- [PostgreSQL — Large Objects: Introduction](https://www.postgresql.org/docs/current/lo-intro.html): mô hình LO, catalog và so sánh TOAST.
- [PostgreSQL — Large Object Implementation Features](https://www.postgresql.org/docs/current/lo-implementation.html): chunks, random access, sparse allocation và ACL.
- [PostgreSQL — Large Object Client Interfaces](https://www.postgresql.org/docs/current/lo-interfaces.html): create/open/read/write/seek/truncate/unlink trong transaction.
- [PostgreSQL — Large Object Server-Side Functions](https://www.postgresql.org/docs/current/lo-funcs.html): `lo_create`, `lo_get`, `lo_put`, `lo_unlink`, `lo_import` và `lo_export`.
- [PostgreSQL — TOAST](https://www.postgresql.org/docs/current/storage-toast.html): giới hạn datum, storage strategy, nén và out-of-line storage.
- [PostgreSQL — lo module](https://www.postgresql.org/docs/current/lo.html): domain `lo`, trigger `lo_manage` và các hạn chế.
- [PostgreSQL — vacuumlo](https://www.postgresql.org/docs/current/vacuumlo.html): dọn orphan Large Objects và dry-run/limit.
- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): tùy chọn `--large-objects`/`--no-large-objects` và selective dumps.
- [PostgreSQL — Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html): Large Objects không được logical replication replicate.
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html): quyền SELECT/UPDATE trên Large Objects.
- [pgJDBC — Storing Binary Data](https://jdbc.postgresql.org/documentation/binary-data/): BYTEA stream, Blob mapping và yêu cầu transaction cho LO.
- [pgJDBC — LargeObject API](https://jdbc.postgresql.org/documentation/publicapi/org/postgresql/largeobject/LargeObject.html): stream, seek, read/write, truncate và close.
- [pgJDBC — LargeObjectManager](https://jdbc.postgresql.org/documentation/publicapi/org/postgresql/largeobject/LargeObjectManager.html): create/open/delete Large Objects từ JDBC.



