# Tạo tablespace, cấu hình AUTOEXTEND và kiểm soát MAXSIZE trong Oracle Database

Trong Oracle Database, khi cần lưu thêm bảng, chỉ mục hoặc dữ liệu của ứng dụng, quản trị viên thường phải quyết định **tablespace nào sẽ chứa dữ liệu**, **dung lượng ban đầu của datafile** và **mức tăng trưởng tối đa cho phép**. Hai tùy chọn `AUTOEXTEND` và `MAXSIZE` giúp kiểm soát sự mở rộng của file, nhưng không bảo đảm rằng máy chủ luôn còn đủ dung lượng lưu trữ vật lý.

Ví dụ, một datafile được tạo ở kích thước **2 GiB**, đặt `AUTOEXTEND ON NEXT 256M MAXSIZE 10G`. File có thể tăng khi Oracle cần thêm extent, theo các điều kiện áp dụng, nhưng **không được vượt mức 10 GiB** do cấu hình. Nếu không còn chỗ trên filesystem/ASM disk group hoặc vướng giới hạn khác, việc tăng có thể thất bại trước khi đạt 10 GiB.

Bài học này hướng dẫn tạo và quản lý tablespace trong bối cảnh **Database Engine Relational Oracle**, từ cú pháp SQL cơ bản đến quản lý dung lượng thực tế và các tình huống vận hành.

> Các lệnh tạo, tăng, giảm kích thước và thêm datafile **thay đổi cấu trúc lưu trữ**. Hãy thực hành trên database thử nghiệm, dùng đường dẫn hợp lệ của máy chủ, có quyền phù hợp, và kiểm tra quy trình backup/giám sát trước khi áp dụng cho môi trường thật.

## 1. Tablespace là gì?

**Tablespace** là đơn vị **lưu trữ logic** của Oracle Database. Một tablespace có thể chứa các **segments**, ví dụ table segment và index segment; các segment được tổ chức bằng extents và data blocks. Dữ liệu vật lý của một permanent tablespace được lưu trong một hoặc nhiều **datafiles**.

```text
                    ORACLE DATABASE
                          |
                     Tablespace
                    APP_DATA (logic)
                          |
             +------------+------------+
             |                         |
      Datafile 01                  Datafile 02
      app_data01.dbf               app_data02.dbf
      size 2 GiB                   size 2 GiB
      max  10 GiB                  max  10 GiB
             |                         |
             +------------+------------+
                          |
                 Segments / Extents
                 Tables, Indexes, ...
```

Một tablespace **không phải** một thư mục hệ điều hành. Lệnh tạo tablespace chỉ định cách Oracle quản lý đơn vị lưu trữ logic và các file vật lý bên dưới.

### 1.1. Phân biệt các tầng dung lượng

| Tầng | Ví dụ | Đơn vị và ý nghĩa |
| --- | --- | --- |
| Database | `ORCL` hoặc một PDB | Bao gồm nhiều tablespaces phục vụ dữ liệu hệ thống và ứng dụng |
| Tablespace | `APP_DATA` | Nhóm logic chứa các segments |
| Datafile | `app_data01.dbf` | File vật lý có kích thước hiện tại và giới hạn tăng trưởng |
| Segment | Bảng `ORDERS`, index `IDX_ORDERS` | Đối tượng sử dụng các extents trong tablespace |
| Extent | Một tập hợp các Oracle blocks | Đơn vị Oracle cấp phát thêm khi segment cần không gian |
| Oracle block | Ví dụ block 8 KiB | Đơn vị lưu trữ/đọc ghi logic cơ bản bên trong database |

**Datafile đã được cấp phát** khác với **dữ liệu đã sử dụng trong segment**: một file 2 GiB có thể còn nhiều extents trống để Oracle cấp phát mà chưa cần tăng kích thước file.

### 1.2. Ba loại tablespace thường gặp

| Loại | File liên quan | Dùng để làm gì? | Lưu ý khi mở rộng |
| --- | --- | --- | --- |
| **Permanent** | `DATAFILE` | Table, index, materialized view và các segments lâu dài | Có thể `ADD DATAFILE` ở smallfile tablespace |
| **Temporary** | `TEMPFILE` | Không gian tạm cho sort, hash và các tác vụ cần TEMP | Dùng cú pháp `TEMPFILE`; theo dõi dung lượng TEMP riêng |
| **Undo** | Thường là `DATAFILE` | Lưu undo để rollback, read consistency và phục hồi | Phải tính đến undo retention, workload và cấu hình undo |

Không nên tạo một permanent tablespace rồi dùng thay cho temporary tablespace. Các cơ chế quản lý file và không gian khác nhau.

### 1.3. Smallfile và bigfile

Oracle phân biệt hai kiểu cấu trúc tablespace:

- **Smallfile tablespace**: kiểu thông dụng; có thể chứa **nhiều datafiles**. Khi hết khả năng phát triển của từng file, có thể thêm datafile mới nếu giới hạn và hạ tầng cho phép.
- **Bigfile tablespace**: được thiết kế để chứa **một datafile rất lớn** (hoặc một tempfile với bigfile temporary tablespace, theo loại tương ứng). Các thao tác tăng kích thước tập trung vào chính file đó; không thể giải quyết bằng cách thêm datafile thứ hai như smallfile.

Giới hạn kích thước file phụ thuộc vào **Oracle block size** và loại tablespace. Về mặt kiến trúc, smallfile thường có trần khoảng **2²² blocks/file**, còn bigfile khoảng **2³² blocks/file**; với block 8 KiB, mức lý thuyết tương ứng xấp xỉ **32 GiB** và **32 TiB**. Giới hạn chính xác còn phụ thuộc phiên bản, hệ điều hành, storage và khả năng của database, vì vậy không coi các con số làm quota mặc định của mọi hệ thống.

## 2. Chuẩn bị trước khi tạo tablespace

Trước khi chạy `CREATE TABLESPACE` cần xác định:

1. **Đúng database/PDB đích**: trong kiến trúc CDB/PDB, tablespace ứng dụng thông thường nên tạo **trong PDB** chứa dữ liệu của ứng dụng.
2. **Loại tablespace**: permanent, temporary, undo; smallfile hay bigfile.
3. **Vị trí datafile**: đường dẫn filesystem, ASM hoặc Oracle Managed Files (OMF).
4. **Kích thước ban đầu**: `SIZE` cần đáp ứng nhu cầu ban đầu mà không cấp phát quá mức.
5. **Bước tăng**: `NEXT` đủ phù hợp với loại workload và dung lượng còn lại.
6. **Trần tăng trưởng**: `MAXSIZE` cho từng file; tính tổng mức có thể tăng của tablespace.
7. **Điều kiện vận hành**: quyền DBA, dung lượng thực của storage, monitoring, backup và chính sách cấp quota cho schema.

### 2.1. Kiểm tra container và thông số nền

Với SQL*Plus/SQLcl:

```sql
SHOW CON_NAME;

-- Có thể cần quyền xem các view quản trị.
SELECT name, open_mode
FROM   v$pdbs
ORDER  BY name;

SHOW PARAMETER db_block_size;
SHOW PARAMETER db_create_file_dest;
```

Nếu muốn chuyển sang một PDB cụ thể, tài khoản phải có quyền thực hiện:

```sql
-- Ví dụ chỉ dành cho tài khoản quản trị có quyền phù hợp.
ALTER SESSION SET CONTAINER = APPPDB;

SHOW CON_NAME;
```

Tên `APPPDB` chỉ là ví dụ. Nếu thực hiện `CREATE TABLESPACE` ở `CDB$ROOT`, tablespace sẽ nằm trong root theo ngữ cảnh đó, không tự trở thành tablespace ứng dụng của PDB.

### 2.2. Chọn cách quản lý tên file

**Đường dẫn tường minh** phù hợp khi DBA quản lý rõ vị trí datafiles:

```text
/u02/oradata/ORCL/app_data01.dbf
```

Đường dẫn đó phải tồn tại/vị trí cha phải có quyền ghi cho Oracle Database trên **máy chủ database**; không phải thư mục trên laptop chạy SQL Developer.

Với **Oracle Managed Files (OMF)**, Oracle tự tạo tên và quản lý file dưới vị trí được cấu hình (chẳng hạn `DB_CREATE_FILE_DEST`). Ví dụ khi OMF đã cấu hình:

```sql
SELECT name, value
FROM   v$parameter
WHERE  name = 'db_create_file_dest';
```

Sau đó có thể dùng `DATAFILE SIZE ...` không ghi đường dẫn cụ thể. Nếu sử dụng **ASM**, cú pháp và vị trí vật lý phụ thuộc disk group và cơ chế Oracle/ASM quản lý file; không nhập đường dẫn filesystem thông thường vào ASM theo phỏng đoán.

## 3. Tạo permanent tablespace với SIZE, AUTOEXTEND và MAXSIZE

### 3.1. Ví dụ smallfile với đường dẫn cụ thể

Giả sử database dùng filesystem, đường dẫn hợp lệ và đã được chuẩn bị. Tạo tablespace chứa dữ liệu ứng dụng:

```sql
CREATE SMALLFILE TABLESPACE app_data
    DATAFILE '/u02/oradata/ORCL/app_data01.dbf'
        SIZE 2G
        AUTOEXTEND ON
        NEXT 256M
        MAXSIZE 10G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

**Ý nghĩa của từng phần:**

| Thành phần | Ý nghĩa |
| --- | --- |
| `CREATE SMALLFILE TABLESPACE app_data` | Tạo permanent smallfile tablespace tên `APP_DATA` |
| `DATAFILE '...app_data01.dbf'` | Chỉ định file vật lý đầu tiên |
| `SIZE 2G` | Kích thước file lúc tạo là 2 GiB theo đơn vị Oracle diễn giải |
| `AUTOEXTEND ON` | Cho phép file tự tăng khi Oracle cần cấp phát thêm không gian |
| `NEXT 256M` | Bước tăng được cấu hình là 256 MiB |
| `MAXSIZE 10G` | Giới hạn kích thước tối đa của **datafile này**, không phải mọi file trong tablespace |
| `EXTENT MANAGEMENT LOCAL` | Quản lý extents cục bộ bằng metadata của tablespace |
| `SEGMENT SPACE MANAGEMENT AUTO` | Dùng Automatic Segment Space Management, thông thường cho các permanent locally managed tablespaces |

Ví dụ trên không cần một lệnh `ALTER DATABASE DATAFILE` riêng để bật autoextend, vì đã cấu hình ngay khi tạo.

**Chú ý:** `AUTOEXTEND ON` chỉ kích hoạt khả năng tăng nếu còn đủ điều kiện. Nó **không ép file tăng ngay đến `MAXSIZE`** và không bảo đảm rằng mọi yêu cầu mở rộng đều thành công.

### 3.2. Khai báo nhiều datafiles khi tạo

Smallfile tablespace có thể được tạo với nhiều file:

```sql
CREATE SMALLFILE TABLESPACE app_report
    DATAFILE
        '/u02/oradata/ORCL/app_report01.dbf'
            SIZE 1G AUTOEXTEND ON NEXT 128M MAXSIZE 6G,
        '/u03/oradata/ORCL/app_report02.dbf'
            SIZE 1G AUTOEXTEND ON NEXT 128M MAXSIZE 6G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

Cấu hình có **hai file**, mỗi file ban đầu 1 GiB và tối đa 6 GiB. Tổng giới hạn từ hai file có thể đạt khoảng **12 GiB** nếu các điều kiện storage, giới hạn database và cấp phát cho phép.

Không được kết luận rằng `MAXSIZE 6G` có nghĩa **toàn tablespace** chỉ tối đa 6 GiB: tùy chọn này nằm trong mô tả **từng datafile**.

### 3.3. Tạo tablespace với OMF

Nếu `DB_CREATE_FILE_DEST` đã được cấu hình hợp lệ, có thể để Oracle tạo tên datafile:

```sql
CREATE TABLESPACE app_index
    DATAFILE SIZE 1G
        AUTOEXTEND ON NEXT 128M MAXSIZE 6G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

Oracle quyết định tên file trong vị trí OMF đã cấu hình. Phương án này hữu ích để giảm lỗi đặt tên/đường dẫn thủ công và phù hợp nhiều môi trường ASM/cloud.

Không bỏ `DATAFILE` hoặc một tham số quan trọng chỉ vì hệ thống dùng OMF mà chưa xác nhận cú pháp và default của đúng bản Oracle.

### 3.4. Tạo bigfile tablespace

Ví dụ với OMF đã cấu hình:

```sql
CREATE BIGFILE TABLESPACE analytics_data
    DATAFILE SIZE 8G
        AUTOEXTEND ON NEXT 1G MAXSIZE 100G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

Đây là **một file** có kích thước ban đầu 8 GiB và trần cấu hình 100 GiB. Với bigfile tablespace, không dùng `ALTER TABLESPACE ... ADD DATAFILE` để thêm file thứ hai. Thay vào đó, khi cần, tăng kích thước/giới hạn của file hiện tại theo cú pháp được hỗ trợ.

Chọn bigfile dựa trên yêu cầu quản lý dung lượng, hệ thống lưu trữ và giới hạn kiến trúc; không nên nghĩ “bigfile” tự động làm mọi SQL nhanh hơn.

## 4. AUTOEXTEND hoạt động như thế nào?

### 4.1. Phân biệt cấp phát extent và tăng file

Khi một table hoặc index cần thêm chỗ, Oracle cố gắng cấp phát **extent** mới từ phần trống đã có trong tablespace. Nếu không đủ extents để đáp ứng yêu cầu, Oracle có thể mở rộng datafile đã bật `AUTOEXTEND` theo giới hạn được cấu hình.

```text
Đối tượng cần extent mới
          |
          v
Tablespace còn free extents phù hợp?
     |                         |
    Có                       Không
     |                         |
     v                         v
Cấp phát extent         Datafile có AUTOEXTEND ON?
                              |             |
                             Có           Không
                              |             |
                              v             v
                      Còn dưới MAXSIZE?  Có thể gặp
                      Storage còn đủ?    lỗi thiếu extent
                          |       |
                         Có     Không
                          |       |
                          v       v
                    Tăng file  Lỗi mở rộng
                          |
                          v
                    Cấp phát extent
```

Trong thực tế, việc cấp phát còn phụ thuộc kích thước extent, chính sách tablespace, hạ tầng lưu trữ, quotas và giới hạn khác. Sơ đồ mô tả đường xử lý cơ bản.

### 4.2. SIZE, NEXT và MAXSIZE không thay thế nhau

Giả sử:

```text
Datafile:       app_data01.dbf
SIZE:           2 GiB
AUTOEXTEND:     ON
NEXT:           256 MiB
MAXSIZE:        10 GiB
```

Có ba con số phải phân biệt:

- **2 GiB**: dung lượng file được Oracle cấp phát lúc tạo.
- **256 MiB**: mức tăng `NEXT` được cấu hình khi Oracle cần mở rộng file; kích thước thực tế vẫn phải tuân thủ điều kiện cấp phát và giới hạn.
- **10 GiB**: mức trần của file. `MAXSIZE` không phải mức dung lượng đã chiếm ngay trên đĩa khi vừa tạo.

Nếu file đang 2 GiB, biên độ tăng cấu hình còn lại trước trần là **8 GiB**. Tuy nhiên, nếu filesystem/ASM chỉ còn khả dụng 3 GiB, không thể mặc nhiên kỳ vọng file đạt 10 GiB.

### 4.3. AUTOEXTEND ON và OFF

Có thể tạo datafile cố định bằng cách không bật autoextend hoặc đặt rõ:

```sql
CREATE TABLESPACE audit_fixed
    DATAFILE '/u02/oradata/ORCL/audit_fixed01.dbf'
        SIZE 2G
        AUTOEXTEND OFF;
```

Trong trường hợp này, khi hết chỗ cấp phát, Oracle **không tự tăng file**. DBA có thể tăng file bằng lệnh thủ công hoặc thêm datafile mới với smallfile tablespace nếu được phép.

**Lợi ích của AUTOEXTEND ON:** giảm nguy cơ phải can thiệp thủ công cho từng lần dữ liệu tăng.  
**Rủi ro nếu cấu hình thiếu kiểm soát:** file tăng bất ngờ, làm đầy storage dùng chung và có thể ảnh hưởng các database/ứng dụng khác.

Không có lựa chọn tối ưu cho mọi môi trường; thường nên kết hợp `AUTOEXTEND ON` với `MAXSIZE` phù hợp và cảnh báo dung lượng storage.

### 4.4. MAXSIZE UNLIMITED có thực sự không giới hạn?

Ví dụ cú pháp:

```sql
CREATE TABLESPACE growth_test
    DATAFILE '/u02/oradata/ORCL/growth_test01.dbf'
        SIZE 1G
        AUTOEXTEND ON NEXT 128M MAXSIZE UNLIMITED;
```

`UNLIMITED` **không có nghĩa dung lượng vô hạn**. Oracle vẫn chịu giới hạn kiến trúc về số blocks/file, loại bigfile/smallfile, hệ điều hành, filesystem/ASM disk group, chính sách quota, cơ chế cấp phát và tài nguyên còn trống.

Một số hệ thống còn có cấp phát mỏng (**thin provisioning**): chỉ số dung lượng logic hoặc giới hạn ảo có thể lớn hơn dung lượng vật lý khả dụng. Do đó, `MAXSIZE UNLIMITED` không phải là kế hoạch quản lý capacity.

### 4.5. MAXSIZE là thuộc tính của từng datafile

Với cấu hình:

```text
APP_DATA:
  app_data01.dbf   SIZE 2G  MAXSIZE 10G  AUTOEXTEND ON
  app_data02.dbf   SIZE 3G  MAXSIZE 12G  AUTOEXTEND ON

Tổng dung lượng file hiện tại: 5 GiB
Tổng trần cấu hình của 2 file: 22 GiB
Biên độ tăng cấu hình còn lại: 17 GiB
```

**Đây là các phép cộng trên các file được liệt kê**, không phải một trần chắc chắn của toàn tablespace trong mọi hoàn cảnh. Những ràng buộc của tablespace, database, PDB, OS và storage vẫn áp dụng.

Nếu thêm datafile mới có `MAXSIZE` riêng vào smallfile tablespace, tổng trần cấu hình sẽ tăng theo file mới.

## 5. Thay đổi AUTOEXTEND, NEXT và MAXSIZE sau khi tạo

### 5.1. Bật autoextend hoặc điều chỉnh mức trần

Dùng `ALTER DATABASE DATAFILE` đối với một datafile permanent/undo đã tồn tại:

```sql
ALTER DATABASE DATAFILE
    '/u02/oradata/ORCL/app_data01.dbf'
    AUTOEXTEND ON NEXT 256M MAXSIZE 16G;
```

Ý nghĩa: cho phép file tăng với bước cấu hình 256 MiB và mức tối đa mới 16 GiB, **nếu giới hạn của loại file và môi trường cho phép**.

Lệnh này **không tự thay đổi kích thước hiện tại thành 16 GiB**. Giá trị `MAXSIZE` là giới hạn trên chứ không phải thao tác `RESIZE`.

### 5.2. Tắt tự mở rộng

```sql
ALTER DATABASE DATAFILE
    '/u02/oradata/ORCL/app_data01.dbf'
    AUTOEXTEND OFF;
```

Việc tắt autoextend **không thu nhỏ file**. Datafile giữ kích thước hiện tại; Oracle chỉ ngừng tự mở rộng file theo cơ chế autoextend.

Nếu cần tăng trưởng sau khi tắt, DBA phải cấp phát thêm bằng lệnh thủ công hoặc thay đổi cấu hình.

### 5.3. Tăng kích thước file ngay bằng RESIZE

Khác với đặt MAXSIZE, `RESIZE` thay đổi **kích thước hiện tại**:

```sql
ALTER DATABASE DATAFILE
    '/u02/oradata/ORCL/app_data01.dbf'
    RESIZE 4G;
```

Nếu file đang 2 GiB và storage cho phép, lệnh trên cố tăng lên 4 GiB ngay. Nếu file đang lớn hơn 4 GiB, đây là yêu cầu **thu nhỏ**, và chỉ thành công khi các block/extent đang sử dụng cho phép thu nhỏ đến mức đó.

Lỗi khi thu nhỏ thường xảy ra vì có dữ liệu đã được cấp phát ở phần cuối file. `DBA_FREE_SPACE` báo còn chỗ trống không có nghĩa mọi phần cuối file đều trống và có thể `RESIZE` tùy ý.

### 5.4. Thêm datafile cho smallfile tablespace

```sql
ALTER TABLESPACE app_data
    ADD DATAFILE '/u03/oradata/ORCL/app_data02.dbf'
        SIZE 2G
        AUTOEXTEND ON NEXT 256M MAXSIZE 12G;
```

Thao tác này tăng dung lượng hiện tại của tablespace bằng một datafile mới và thiết lập thêm một trần tăng trưởng riêng cho file đó. Với bigfile tablespace, lệnh **ADD DATAFILE** thứ hai không phù hợp: phải thay đổi file lớn hiện hữu.

### 5.5. Cân nhắc cách chọn lệnh khi gần hết dung lượng

| Tình huống | Hướng xử lý thường gặp | Điểm cần kiểm tra |
| --- | --- | --- |
| Còn storage, file gần `MAXSIZE`, smallfile TS | Tăng `MAXSIZE` của file nếu giới hạn cho phép, hoặc thêm datafile | Loại smallfile, giới hạn file, chỗ trên storage |
| File `AUTOEXTEND OFF` nhưng cần tăng | `RESIZE` hoặc `AUTOEXTEND ON ... MAXSIZE` | Quy hoạch dung lượng và quyền thực hiện |
| Bigfile TS gần trần hiện tại | Tăng `MAXSIZE` hoặc `RESIZE` của file duy nhất nếu được hỗ trợ | Block size và giới hạn vật lý/kiến trúc |
| Tablespace còn dung lượng nhưng schema báo không tạo được đối tượng | Kiểm tra **user quota**, quyền và đối tượng | Không mặc định lỗi luôn do datafile |
| Storage đang cạn | Giải quyết capacity vật lý, cleanup, di chuyển, thêm storage theo kế hoạch | Tăng `MAXSIZE` không tạo ra dung lượng vật lý |
| TEMP thiếu chỗ | Phân tích workload TEMP và các **tempfiles** | Không sửa permanent datafile để chữa mọi lỗi TEMP |

## 6. Tạo và quản lý temporary tablespace

Temporary tablespace dùng **tempfiles** và phục vụ các nhu cầu tạm, ví dụ hoạt động sort/hash có dữ liệu vượt bộ nhớ làm việc.

Ví dụ với filesystem:

```sql
CREATE TEMPORARY TABLESPACE app_temp
    TEMPFILE '/u02/oradata/ORCL/app_temp01.dbf'
        SIZE 1G
        AUTOEXTEND ON NEXT 128M MAXSIZE 8G
    EXTENT MANAGEMENT LOCAL;
```

Một cấu hình tương ứng có thể dùng OMF nếu môi trường đã thiết lập. Khi cần sửa cấu hình autoextend cho tempfile, dùng **`ALTER DATABASE TEMPFILE`**, ví dụ:

```sql
ALTER DATABASE TEMPFILE
    '/u02/oradata/ORCL/app_temp01.dbf'
    AUTOEXTEND ON NEXT 256M MAXSIZE 12G;
```

Đối với tempfiles, kiểm tra qua `DBA_TEMP_FILES`. Không chỉ tra `DBA_DATA_FILES` vì view này dành cho **datafiles**, trong khi tempfiles được theo dõi riêng.

### 6.1. Vì sao TEMP vẫn có thể hết chỗ?

Một truy vấn có `ORDER BY`, `GROUP BY`, hash join hoặc thao tác tương tự có thể cần TEMP lớn khi dữ liệu tràn khỏi vùng nhớ làm việc. Nhiều truy vấn đồng thời cũng làm tổng nhu cầu tăng.

Ngay cả khi `AUTOEXTEND ON`, TEMP vẫn có thể đầy nếu:

- các tempfiles đạt `MAXSIZE`;
- filesystem/ASM không còn dung lượng;
- mức sử dụng TEMP đồng thời quá lớn;
- cấu hình giới hạn PDB hoặc nền tảng không cho phép tăng thêm.

Không nên chỉ bật `MAXSIZE UNLIMITED` cho TEMP để xử lý mọi sự cố: cần xác định truy vấn đang tiêu thụ TEMP và nguyên nhân.

## 7. Kiểm tra cấu hình bằng các data dictionary views

Các ví dụ SQL sau là **read-only**. Cần quyền truy cập phù hợp đối với các DBA views và nên thực thi trong đúng PDB/container đích.

### 7.1. Xem tablespace được tạo và loại file

```sql
SELECT tablespace_name,
       contents,
       status,
       bigfile,
       block_size
FROM   dba_tablespaces
WHERE  tablespace_name IN (
           'APP_DATA',
           'APP_REPORT',
           'APP_INDEX',
           'ANALYTICS_DATA',
           'APP_TEMP'
       )
ORDER  BY tablespace_name;
```

Diễn giải:

- `CONTENTS`: `PERMANENT`, `TEMPORARY` hoặc `UNDO` theo loại.
- `BIGFILE`: xác định tablespace thuộc loại bigfile hay không.
- `BLOCK_SIZE`: block size của tablespace, cần khi tính dung lượng từ số blocks.
- `STATUS`: trạng thái tablespace, chẳng hạn online/offline tùy tình huống.

### 7.2. Kiểm tra AUTOEXTEND và MAXSIZE của datafiles

```sql
SELECT df.tablespace_name,
       df.file_id,
       df.file_name,
       ROUND(df.bytes / 1024 / 1024, 1) AS allocated_mb,
       df.autoextensible,
       ROUND(df.maxbytes / 1024 / 1024, 1) AS max_mb,
       ROUND(df.increment_by * ts.block_size / 1024 / 1024, 1) AS next_mb
FROM   dba_data_files df
JOIN   dba_tablespaces ts
       ON ts.tablespace_name = df.tablespace_name
WHERE  df.tablespace_name = 'APP_DATA'
ORDER  BY df.file_id;
```

Những cột quan trọng:

| Cột | Ý nghĩa |
| --- | --- |
| `BYTES` | Kích thước file hiện tại trong Oracle |
| `AUTOEXTENSIBLE` | `YES` hoặc `NO`, file có được tự tăng hay không |
| `MAXBYTES` | Trần mở rộng được Oracle báo cáo, **không phải kích thước hiện tại** |
| `INCREMENT_BY` | Bước tăng tính theo **số Oracle blocks**, không phải MiB |
| `BLOCK_SIZE` | Kích thước block dùng quy đổi `INCREMENT_BY` thành byte |

Nếu file đang `AUTOEXTENSIBLE='NO'`, đừng lấy `MAXBYTES` làm hạn mức phát triển hữu dụng mà bỏ qua trạng thái này. Với việc tính **dung lượng file có thể đạt được theo cấu hình hiện hành**, file không autoextend nên được coi là có trần bằng **`BYTES` hiện tại** (trừ khi DBA thay đổi cấu hình/thêm file).

Câu truy vấn dưới đây tính sơ bộ dung lượng hiện tại và trần cấu hình trên các datafiles:

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / POWER(1024, 3), 2) AS allocated_gib,
       ROUND(
         SUM(
           CASE
             WHEN autoextensible = 'YES' THEN maxbytes
             ELSE bytes
           END
         ) / POWER(1024, 3), 2
       ) AS potential_file_limit_gib
FROM   dba_data_files
WHERE  tablespace_name = 'APP_DATA'
GROUP  BY tablespace_name;
```

`POTENTIAL_FILE_LIMIT_GIB` **không phải lượng trống thực sự có thể sử dụng ngay**, vì chỉ cộng các trần file, chưa xét mức segment đã cấp phát và giới hạn storage thực tế.

### 7.3. Xem phần extents còn trống trong datafiles hiện tại

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / POWER(1024, 3), 2) AS free_gib
FROM   dba_free_space
WHERE  tablespace_name = 'APP_DATA'
GROUP  BY tablespace_name;
```

`DBA_FREE_SPACE` cho biết các vùng trống theo extents trong datafiles đã được cấp phát và đang có thể được view báo cáo. Nó **không bao gồm toàn bộ khoảng tăng trưởng tương lai** từ `AUTOEXTEND`; cũng không đồng nghĩa filesystem còn ngần ấy dung lượng.

Khi tablespace hoàn toàn không có free extent mà view không trả dòng, câu truy vấn trên có thể không trả kết quả. Để báo cáo chắc chắn hơn, có thể tổng hợp file và free space bằng `LEFT JOIN`/`NVL` rồi đối chiếu trạng thái tablespace.

### 7.4. Theo dõi mức sử dụng tablespace tổng hợp

Một view hữu ích là `DBA_TABLESPACE_USAGE_METRICS`:

```sql
SELECT tablespace_name,
       used_space,
       tablespace_size,
       used_percent
FROM   dba_tablespace_usage_metrics
WHERE  tablespace_name = 'APP_DATA';
```

Các giá trị kích thước trong view này được tính theo blocks và có logic xác định capacity của Oracle; `TABLESPACE_SIZE`/`USED_PERCENT` có thể tính đến khả năng autoextend và giới hạn storage theo cơ chế view/phiên bản. Không suy ra trực tiếp chỉ từ phần trăm này rằng volume của hệ điều hành còn bao nhiêu GiB.

Để kết luận đủ capacity phải **kết hợp**: extents trống, kích thước file hiện tại, trần autoextend, free space filesystem/ASM, workload tăng trưởng và các hạn chế quản trị.

### 7.5. Kiểm tra tempfiles

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       ROUND(bytes / 1024 / 1024, 1)    AS allocated_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024, 1) AS max_mb
FROM   dba_temp_files
WHERE  tablespace_name = 'APP_TEMP'
ORDER  BY file_id;
```

Đây là cấu hình file TEMP, chưa phản ánh đầy đủ **TEMP đang bị SQL nào tiêu thụ**. Khi cần điều tra sâu hơn, DBA có thể dùng các view thống kê về TEMP như `V$TEMP_SPACE_HEADER`, `V$TEMPSEG_USAGE` hoặc các view phù hợp của release hiện hành.

### 7.6. Trong CDB/PDB: xem đúng container

Nếu làm việc trong một **PDB**, các DBA views thông thường phản ánh đối tượng của container hiện tại theo quyền và ngữ cảnh truy vấn. Nếu DBA ở `CDB$ROOT` muốn quan sát toàn CDB, có thể sử dụng các **CDB_** views tương ứng cùng cột `CON_ID` theo phiên bản/quyền:

```sql
-- Chạy ở root bằng tài khoản có quyền thích hợp.
SELECT con_id,
       tablespace_name,
       file_name,
       ROUND(bytes / 1024 / 1024, 1) AS allocated_mb
FROM   cdb_data_files
WHERE  tablespace_name = 'APP_DATA'
ORDER  BY con_id, file_name;
```

Các PDB khác nhau có thể có **tablespace cùng tên**. Vì vậy khi tính capacity trên toàn CDB cần phân biệt bằng `CON_ID`, không gộp tùy tiện tất cả dòng có tên `APP_DATA`.

## 8. Quota người dùng khác với MAXSIZE của datafile

Một tablespace có thể còn dung lượng, nhưng một schema không được phép cấp phát extent vì chưa có **quota** hoặc đã vượt quota dành cho user đó.

Ví dụ (giả định user `APP_USER` đã tồn tại trong PDB và người thao tác có quyền):

```sql
ALTER USER app_user
    QUOTA 1G ON app_data;
```

Điều này đặt **quota sử dụng tablespace cho user** ở mức 1 GiB. Nó **không thay đổi file size**, không thay `MAXSIZE` và không bảo đảm rằng schema có 1 GiB dung lượng vật lý trống thực tế.

Ba giới hạn cần kiểm tra độc lập:

```text
Database user quota
        |
        v
Free space trong tablespace / datafiles
        |
        v
AUTOEXTEND + MAXSIZE của từng datafile
        |
        v
Dung lượng thật trên filesystem / ASM / storage
```

Nếu gặp lỗi như `ORA-01950: no privileges on tablespace`, cần kiểm tra quota/quyền. Nếu gặp lỗi không thể cấp phát extent, cần kiểm tra free extents, trạng thái file, autoextend, maxsize và storage vật lý.

Không tăng bừa quota hay `MAXSIZE` mà chưa xác định tầng giới hạn.

## 9. Lập kế hoạch capacity theo ví dụ

Giả sử ứng dụng có một permanent smallfile tablespace `APP_DATA` với hai datafiles:

| Datafile | Kích thước hiện tại | AUTOEXTEND | NEXT | MAXSIZE |
| --- | ---: | --- | ---: | ---: |
| `app_data01.dbf` | 2 GiB | ON | 256 MiB | 10 GiB |
| `app_data02.dbf` | 3 GiB | ON | 256 MiB | 12 GiB |
| **Tổng** | **5 GiB** | | | **22 GiB** |

Tính sơ bộ:

- **Đã cấp phát ở mức file:** 5 GiB.
- **Trần cấu hình của hai file:** 10 + 12 = 22 GiB.
- **Biên độ file có thể tăng về mặt cấu hình:** 22 − 5 = 17 GiB.

Tuy nhiên, để dự báo **còn bao lâu trước khi đầy**, cần biết:

- Dung lượng các segments thực sự đã sử dụng và free extents trong 5 GiB hiện tại.
- Tốc độ tăng trung bình mỗi ngày/tuần, sự kiện batch và biến động theo mùa.
- Dung lượng storage vật lý còn trống và khả năng tăng storage.
- Các đối tượng lớn (LOB, partition, index) và nhu cầu tạo/rebuild đột biến.
- Quota schema, số lượng datafiles và các giới hạn kiến trúc.

### 9.1. Ước lượng thời gian bằng số liệu minh họa

Giả định kết quả đo đạc cho biết:

```text
Free extents trong files hiện tại:       1 GiB
Biên độ autoextend còn lại theo cấu hình: 17 GiB
Storage thật sự còn cấp được:             9 GiB
Tăng trưởng dữ liệu quy đổi:              0.25 GiB/ngày
```

Nếu giả định workload đều, mọi giới hạn khác cho phép và 9 GiB storage khả dụng có thể dành cho các file này, thì khả năng tăng trưởng từ lúc đo có thể xấp xỉ **1 + min(17, 9) = 10 GiB**, tương đương khoảng **40 ngày** ở tốc độ 0.25 GiB/ngày.

Đây chỉ là minh họa toán học, **không phải cam kết sẽ chạy được 40 ngày**. Mức tăng extent, dữ liệu phát sinh đột biến, autoextend granularity, file allocation overhead, storage dùng chung và workload khác có thể khiến hệ thống cạn tài nguyên sớm hơn. Khi giám sát, nên đặt cảnh báo sớm để có thời gian xử lý.

### 9.2. Các chỉ số cần theo dõi

| Chỉ số | Lý do |
| --- | --- |
| Datafile `BYTES` hiện tại | Storage đã cấp phát cho files |
| Datafile `AUTOEXTENSIBLE`, `MAXBYTES` | Biên độ tăng có thể được Oracle cho phép |
| Free extents và mức sử dụng tablespace | Khoảng trống logic dành cho cấp phát segment |
| Filesystem/ASM free capacity | Khả năng mở rộng vật lý thực sự |
| Tốc độ tăng theo thời gian | Dự báo ngày chạm ngưỡng cảnh báo |
| Số kết nối, job batch, index rebuild | Giải thích tăng trưởng đột biến |
| User quota và PDB limits | Ngăn chặn mở rộng dù files chưa đạt trần |
| Thời gian phục hồi, backup và monitoring | Đảm bảo ứng phó được khi sự cố capacity xảy ra |

Giám sát ở **cả hai cấp tablespace và storage**, bởi một tablespace còn có thể autoextend nhưng storage dùng chung đã gần cạn.

## 10. Xử lý lỗi thiếu không gian thường gặp

### 10.1. ORA-01653 và ORA-01654

Các lỗi thường gặp:

- **`ORA-01653`**: không thể mở rộng table segment trong tablespace.
- **`ORA-01654`**: không thể mở rộng index segment trong tablespace.

Một cách phân tích:

1. Xác định **tablespace** và **segment** được nêu trong lỗi.
2. Kiểm tra free extents và cấu hình các datafiles bằng `DBA_FREE_SPACE`, `DBA_DATA_FILES`.
3. Kiểm tra file đã đạt `MAXSIZE` chưa và `AUTOEXTENSIBLE` có bật hay không.
4. Kiểm tra dung lượng filesystem/ASM và các giới hạn khác.
5. Chọn giải pháp: tăng `MAXSIZE`, thêm datafile (smallfile), tăng storage, giải phóng/tổ chức lại dữ liệu nếu phù hợp, hoặc xử lý quota nếu đây là nguyên nhân.

Không mặc định mọi `ORA-01653` đều được giải quyết bằng một lệnh `MAXSIZE UNLIMITED`.

### 10.2. ORA-01652 liên quan temporary segment

`ORA-01652` thông báo không thể mở rộng temporary segment theo ngữ cảnh được chỉ ra. Trước tiên kiểm tra **tablespace mà lỗi nêu**, bởi temporary segments có thể phát sinh trong nhiều thao tác, và các truy vấn sort/hash thường liên quan đến TEMP.

Cách xử lý:

- Xem tempfiles và `MAXSIZE` bằng `DBA_TEMP_FILES`.
- Kiểm tra việc tiêu thụ TEMP theo session/SQL khi được cấp quyền.
- Đánh giá execution plan, parallelism và mức concurrency.
- Tăng hoặc điều chỉnh tempfiles nếu storage và chính sách cho phép.

Tăng permanent datafile của `APP_DATA` sẽ không nhất thiết giải quyết lỗi phát sinh ở `TEMP`.

### 10.3. Đạt giới hạn file hoặc storage

Khi datafile không thể tăng, nguyên nhân có thể nằm ở:

- `MAXSIZE` đã chạm trần;
- trần số blocks/file theo smallfile/bigfile;
- hết dung lượng, quota hoặc quyền ghi của storage;
- giới hạn database/PDB;
- lỗi I/O hoặc file không ở trạng thái có thể mở rộng.

Oracle có các mã lỗi khác nhau tùy nguyên nhân và giai đoạn thao tác (chẳng hạn yêu cầu `RESIZE` vượt giới hạn file); hãy đọc **mã lỗi đầy đủ và trace/alert log** trước khi chọn giải pháp.

### 10.4. Vì sao ALTER RESIZE giảm kích thước bị lỗi?

Datafile không phải chuỗi byte có thể cắt tùy ý mà không xét vị trí các extents đang sử dụng. Nếu các blocks ở gần cuối file vẫn thuộc một segment, việc giảm file xuống dưới vị trí đó không được phép. Dù tablespace có nhiều free extents ở vùng giữa, **vùng cuối file chưa chắc trống**.

Muốn reclaim storage cần đánh giá vị trí extents, phương án di chuyển/shrink segments, ảnh hưởng lock/redo và chính sách bảo trì. Không thực hiện shrink/resize theo phỏng đoán trên dữ liệu sản xuất.

## 11. Thực hành theo từng bước trên môi trường thử nghiệm

Giả sử thực hành trong PDB `APPPDB`, người thực hiện có quyền tạo/đổi tablespace và storage đã được cấp.

### Bước 1 — Xác nhận đúng môi trường

```sql
SHOW CON_NAME;
SHOW PARAMETER db_create_file_dest;
```

Nếu OMF đã cấu hình hợp lệ, có thể chọn ví dụ không ghi đường dẫn vật lý.

### Bước 2 — Tạo tablespace với trần cụ thể

```sql
CREATE TABLESPACE lab_data
    DATAFILE SIZE 512M
        AUTOEXTEND ON NEXT 64M MAXSIZE 2G
    EXTENT MANAGEMENT LOCAL
    SEGMENT SPACE MANAGEMENT AUTO;
```

`LAB_DATA` bắt đầu với 512 MiB, cấu hình tăng mỗi bước 64 MiB và trần file là 2 GiB (tùy các điều kiện cho phép). Nếu môi trường không dùng OMF, phải thay phần `DATAFILE SIZE ...` bằng `DATAFILE 'đường_dẫn_hợp_lệ' SIZE ...`.

### Bước 3 — Quan sát dữ liệu thực tế

```sql
SELECT file_name,
       ROUND(bytes / 1024 / 1024) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024) AS max_mb,
       increment_by
FROM   dba_data_files
WHERE  tablespace_name = 'LAB_DATA';
```

Lưu lại `FILE_NAME` Oracle đã tạo. Với OMF, tên thực tế là tên được Oracle sinh, không phải một chuỗi cố định trong tài liệu.

### Bước 4 — Điều chỉnh trần

Sau khi biết `FILE_NAME` thật từ bước 3, trên môi trường test có thể điều chỉnh bằng:

```sql
-- Thay tên file bằng giá trị FILE_NAME thực tế từ bước 3.
ALTER DATABASE DATAFILE
    '<actual_datafile_name>'
    AUTOEXTEND ON NEXT 128M MAXSIZE 4G;
```

`<actual_datafile_name>` chỉ là **placeholder**, không chạy nguyên văn. Kích thước hiện tại không tự nhảy lên 4 GiB vì mới đổi `MAXSIZE`.

### Bước 5 — Quan sát sau khi đổi

```sql
SELECT file_name,
       ROUND(bytes / 1024 / 1024) AS current_mb,
       autoextensible,
       ROUND(maxbytes / 1024 / 1024) AS max_mb
FROM   dba_data_files
WHERE  tablespace_name = 'LAB_DATA';
```

So sánh `CURRENT_MB` và `MAX_MB` để nhận ra sự khác biệt giữa **dung lượng đã cấp phát** với **dung lượng có thể tăng theo cấu hình**.

### Bước 6 — Thu dọn bài thực hành (chỉ khi dữ liệu không cần giữ)

Nếu đây thực sự là tablespace thử nghiệm và đã được xác nhận không chứa dữ liệu cần giữ, DBA có thể dọn theo quy trình riêng:

```sql
-- THAO TÁC PHÁ HỦY: chỉ dùng trên LAB_DATA được tạo riêng cho bài thực hành.
DROP TABLESPACE lab_data INCLUDING CONTENTS AND DATAFILES;
```

Lệnh trên xóa cả đối tượng thuộc tablespace và các datafiles tương ứng theo cơ chế Oracle; **không chạy trên tablespace có dữ liệu sản xuất**. Trên môi trường do tổ chức quản lý, việc dọn dẹp cần tuân thủ quy trình và xác nhận ownership.

## 12. Những ngộ nhận cần tránh

**“`MAXSIZE 10G` nghĩa là Oracle chiếm sẵn 10 GiB.”**  
Không. `SIZE` là kích thước ban đầu; `MAXSIZE` là giới hạn trên của file nếu autoextend được bật.

**“`AUTOEXTEND ON` bảo đảm không bao giờ hết chỗ.”**  
Không. Datafile có thể đạt `MAXSIZE` hoặc storage vật lý có thể đầy.

**“`MAXSIZE` là giới hạn của cả tablespace.”**  
Không trực tiếp. Tùy chọn `MAXSIZE` được đặt theo **datafile/tempfile**; smallfile tablespace có thể chứa nhiều file.

**“`AUTOEXTEND ON` làm file to lên ngay.”**  
Không. Việc tăng thường phát sinh khi cần cấp phát thêm; dùng `RESIZE` nếu mục tiêu là thay đổi kích thước hiện tại ngay.

**“Tắt AUTOEXTEND sẽ trả lại dung lượng storage đã cấp phát.”**  
Không. `AUTOEXTEND OFF` chỉ dừng tự tăng; kích thước hiện tại không tự giảm.

**“Còn free extents trong tablespace là storage OS cũng còn trống.”**  
Không. Free extents nằm **bên trong datafiles đã cấp phát**, còn free filesystem/ASM là tài nguyên bên ngoài database; hai chỉ số khác nhau.

**“Datafile đầy thì phải tăng MAXSIZE lên UNLIMITED.”**  
Không nhất thiết. Có thể thêm file cho smallfile, tối ưu dữ liệu, mở rộng storage, điều chỉnh quota hoặc xem lại thiết kế segment, tùy nguyên nhân.

**“Một PDB không cần quan tâm container khi tạo tablespace.”**  
Sai. Tablespace tạo trong container nào có phạm vi theo container đó. Luôn xác nhận `SHOW CON_NAME`.

## 13. Câu hỏi tự kiểm tra

1. Một datafile có `SIZE 1G`, `AUTOEXTEND ON NEXT 128M MAXSIZE 8G`. Chỉ từ cấu hình này, có thể khẳng định file hiện đã chiếm 8 GiB trên filesystem không?
2. Một smallfile tablespace chứa 3 datafiles, mỗi file `MAXSIZE 5G`. Có nên gọi đây là “tablespace chỉ tối đa 5 GiB” không?
3. File `APP_DATA01.DBF` đang 6 GiB và `AUTOEXTEND OFF`. Chạy `ALTER DATABASE DATAFILE ... AUTOEXTEND OFF` thêm lần nữa có giải phóng được 2 GiB không?
4. Vì sao `DBA_FREE_SPACE` có thể báo còn free extents nhưng cảnh báo storage của hệ điều hành vẫn ở mức cao?
5. Một bảng báo lỗi không thể mở rộng extent. Cần xem cả `DBA_DATA_FILES`, `DBA_FREE_SPACE` và filesystem/ASM vì lý do gì?
6. Khi cần tăng một **bigfile tablespace**, có thể dùng `ALTER TABLESPACE ... ADD DATAFILE` như smallfile không?
7. Khi `RESIZE` file từ 10 GiB xuống 6 GiB bị lỗi, tại sao không thể kết luận tablespace hoàn toàn không có chỗ trống?
8. Vì sao việc thay `MAXSIZE` của datafile không thay thế việc cấp quota cho schema?

**Gợi ý đáp án:**

1. Không; `SIZE` ban đầu là 1 GiB, `MAXSIZE` chỉ là trần tăng trưởng.
2. Không; các file có giới hạn riêng, tổng mức trần cấu hình từ ba file có thể là 15 GiB nếu điều kiện cho phép.
3. Không; tắt autoextend không shrink file.
4. Free extents là không gian logic **bên trong các file đã chiếm storage**, không phải free capacity ngoài Oracle.
5. Để phân biệt khoảng trống hiện tại, khả năng file tự tăng, trần cấu hình và khả năng storage thực sự đáp ứng.
6. Không; bigfile tablespace tập trung vào một file lớn, cần điều chỉnh file đó theo cơ chế được hỗ trợ.
7. Có thể còn các extents trống ở giữa file, nhưng phần cuối file đang được segment sử dụng.
8. Quota là giới hạn theo **database user**, còn `MAXSIZE` giới hạn theo **file**, hai tầng quản lý khác nhau.

## 14. Tài liệu Oracle nên tham khảo

- [Oracle Database SQL Language Reference — CREATE TABLESPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLESPACE.html): cú pháp tạo permanent, temporary, smallfile và bigfile tablespace.
- [Oracle Database SQL Language Reference — ALTER TABLESPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLESPACE.html): thay đổi thuộc tính tablespace và bổ sung datafile.
- [Oracle Database SQL Language Reference — ALTER DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-DATABASE.html): các mệnh đề `DATAFILE`/`TEMPFILE` và `RESIZE`/`AUTOEXTEND`.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản lý tablespaces, datafiles, tempfiles, Oracle Managed Files và dung lượng.
- [Oracle Database Reference — DBA_DATA_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DATA_FILES.html): `BYTES`, `MAXBYTES`, `AUTOEXTENSIBLE`, `INCREMENT_BY`.
- [Oracle Database Reference — DBA_TEMP_FILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TEMP_FILES.html): các thuộc tính tương ứng của tempfiles.
- [Oracle Database Reference — DBA_TABLESPACE_USAGE_METRICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TABLESPACE_USAGE_METRICS.html): số liệu mức sử dụng và dung lượng tablespace.
- [Oracle Database Reference — DBA_FREE_SPACE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_FREE_SPACE.html): free extents theo tablespace/file.

Khi tạo và vận hành tablespace, hãy quản lý đồng thời **kích thước file hiện tại (`SIZE`/`BYTES`)**, **bước tăng (`NEXT`)**, **trần file (`MAXSIZE`)**, **phần trống trong tablespace** và **dung lượng storage còn thực sự khả dụng**. Chỉ khi đọc chung các thông tin đó mới biết database còn có thể tăng bao nhiêu và cần can thiệp trước khi hệ thống hết không gian.
