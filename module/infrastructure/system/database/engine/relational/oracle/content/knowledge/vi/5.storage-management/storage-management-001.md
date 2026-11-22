# Quan hệ giữa tablespace, datafile, segment, extent và data block

## 1. Vì sao phải phân biệt các đơn vị lưu trữ của Oracle?

Khi tạo một bảng trong Oracle Database, bạn thường chỉ viết `CREATE TABLE`, sau đó `INSERT` và `SELECT`. Tuy nhiên, dữ liệu của bảng phải được đặt vào một cấu trúc lưu trữ có tổ chức: bảng thuộc một **tablespace**, dữ liệu được cấp cho **segment** qua các **extent**, mỗi extent gồm nhiều **Oracle data block**, còn các block tồn tại bên trong **datafile** của tablespace đó.

Nếu chưa nắm được mối quan hệ này, bạn dễ nhầm:

- Dung lượng **bảng đang chứa dữ liệu** với dung lượng **segment đã được cấp phát**.
- Dung lượng **datafile hiện có** với không gian **tablespace còn có thể mở rộng**.
- **Tablespace** (đơn vị logic) với **thư mục trên hệ điều hành** (vị trí vật lý).
- **Một bảng** với **một segment duy nhất**; index, LOB và các partition có thể có segment riêng.
- **Block** với **extent**; chúng khác nhau cả về cấp độ và mục đích.

Trong mô hình lưu trữ quan hệ Oracle, các khái niệm này giúp bạn trả lời những câu hỏi thực tế như: “Bảng này nằm trong tablespace nào?”, “Nó đã được cấp phát bao nhiêu MB?”, “Extent của nó ở datafile nào?”, “Vì sao còn dung lượng ổ đĩa mà vẫn gặp lỗi không thể mở rộng segment?” và “Có phải xóa hàng là datafile lập tức nhỏ đi không?”.

Mục tiêu của bài là hiểu được **phân cấp logic và vật lý**, tự đọc được thông tin qua các data dictionary view, và hình dung điều gì xảy ra khi Oracle phân bổ thêm không gian cho bảng hoặc index.

## 2. Bức tranh tổng thể: logic và vật lý

Oracle tổ chức dữ liệu theo hai cách nhìn liên quan chặt chẽ:

1. **Logic**: tablespace → segment → extent → data block.
2. **Vật lý**: tablespace có một hoặc nhiều datafile; các block được phân bổ cho extent nằm **bên trong từng datafile**.

Một sơ đồ đơn giản:

```text
                              ORACLE DATABASE
                                     |
                           TABLESPACE APP_DATA
                                     |
               +---------------------+-------------------+
               |                                         |
          DATAFILE 01                                DATAFILE 02
          (file_id=5)                                (file_id=6)
               |                                         |
        +------+------+                           +------+------+
        |             |                           |             |
    Extent A      Extent B                    Extent C      Extent D
    TABLE_ORDERS  IDX_ORDERS                  TABLE_ORDERS  IDX_ORDERS
        |             |                           |             |
     [block]       [block]                     [block]       [block]
     [block]       [block]                     [block]       [block]
     [block]       [block]                     [block]       [block]

  Segment TABLE_ORDERS = Extent A + Extent C + ...
  Segment IDX_ORDERS   = Extent B + Extent D + ...
```

Sơ đồ không thể hiện đầy đủ phần header, free space và nhiều segment có thể cùng tồn tại trong một file. Nó minh họa một điểm quan trọng: **một segment có thể gồm các extent nằm ở nhiều datafile khác nhau**, miễn các datafile thuộc cùng tablespace; **mỗi extent riêng lẻ nằm trong một datafile**.

### Các mối quan hệ cốt lõi

| Thành phần | Bản chất | Quan hệ trực tiếp | Điều không nên nhầm |
|---|---|---|---|
| **Tablespace** | Đơn vị lưu trữ logic cấp cao của database | Gồm một hay nhiều datafile, hoặc tempfile đối với temporary tablespace; chứa các segment | Không phải thư mục Linux/Windows |
| **Datafile** | Tệp lưu trữ vật lý hoặc tệp do ASM quản lý | Thuộc một tablespace, chứa các block và các extent của nhiều segment | Không nhất thiết mỗi bảng một file |
| **Segment** | Vùng không gian được cấp phát cho một đối tượng/cấu trúc lưu trữ | Thuộc một tablespace, gồm các extent | Không đồng nghĩa một bảng logic luôn chỉ có một segment |
| **Extent** | Nhóm các Oracle block liên tiếp được cấp phát cho một segment | Thuộc một segment, nằm trọn trong một datafile | Không được trải một extent qua hai datafile |
| **Data block** | Đơn vị lưu trữ logic nhỏ nhất Oracle quản lý trong cấu trúc này | Nằm trong datafile; nhiều block tạo thành một extent | Không mặc định bằng một sector/OS block |

Có thể ghi nhớ bằng hai phát biểu:

> **Tablespace** tổ chức không gian logic; **datafile** cung cấp nơi lưu vật lý. **Segment** nhận không gian từ tablespace dưới dạng **extent**, và extent gồm các **data block**.

> Oracle xác định chỗ lưu dữ liệu bằng **file + block**, còn ứng dụng SQL thường làm việc với **bảng, hàng và cột**, không cần biết tọa độ vật lý đó.

## 3. Tablespace: ranh giới quản lý lưu trữ logic

### 3.1. Tablespace là gì?

**Tablespace** là đơn vị logic Oracle sử dụng để nhóm các cấu trúc lưu trữ. Khi tạo bảng hoặc index, bạn có thể chỉ định tablespace cho segment của chúng. Oracle dùng các file gắn với tablespace để cung cấp block chứa dữ liệu.

Ví dụ về cách tổ chức:

```text
DATABASE
  |
  +-- SYSTEM         : đối tượng hệ thống cốt lõi
  +-- SYSAUX         : đối tượng phụ trợ cho thành phần Oracle
  +-- UNDOTBS1       : lưu dữ liệu undo theo cấu hình
  +-- TEMP           : không gian tạm cho thao tác cần work area
  +-- APP_DATA       : bảng ứng dụng (ví dụ tự thiết kế)
  +-- APP_INDEX      : index ứng dụng (ví dụ tự thiết kế)
```

`APP_DATA` và `APP_INDEX` chỉ là tên minh họa. Một ứng dụng có thể đặt bảng và index trong cùng tablespace hoặc phân tách để dễ quản trị, theo dõi dung lượng và chính sách lưu trữ.

Một số loại và vai trò:

| Tablespace | Đặc điểm | Ví dụ sử dụng |
|---|---|---|
| **Permanent** | Lưu segment dữ liệu lâu dài; dùng datafile | Bảng, index, LOB của ứng dụng |
| **Undo** | Chứa undo segment phục vụ rollback, read consistency và các tác vụ khác | Undo do Oracle quản lý theo cơ chế cấu hình |
| **Temporary** | Phục vụ dữ liệu tạm của các thao tác cần không gian bổ sung; dùng tempfile | Sort, hash và thao tác tạm khác khi cần |
| **SYSTEM/SYSAUX** | Tablespace có vai trò đặc biệt đối với hoạt động database | Metadata hệ thống, các thành phần nội bộ |

**Điểm phân biệt:** temporary tablespace thông thường sử dụng **tempfile** thay vì datafile; vẫn có không gian tạm/temporary segment nhưng việc quản lý và các view theo dõi không giống hệt permanent tablespace. Không vì nhìn thấy từ “tablespace” mà mặc định mọi file bên trong đều là `DBA_DATA_FILES`.

### 3.2. Smallfile và bigfile tablespace

Oracle hỗ trợ các kiểu tổ chức tablespace khác nhau:

- **Smallfile tablespace**: có thể chứa nhiều datafile; đây là bố trí phổ biến trong nhiều hệ thống.
- **Bigfile tablespace**: được thiết kế với **một datafile rất lớn** (hoặc một tempfile lớn cho temporary tablespace), đi kèm giới hạn và công cụ quản trị tương ứng.

Như vậy phát biểu “một tablespace có nhiều datafile” là **khả năng**, không phải điều kiện bắt buộc. Một tablespace có thể chỉ có một datafile. Với bigfile tablespace, khả năng mở rộng dựa nhiều vào việc mở rộng file lớn đó.

### 3.3. Tablespace, schema và user không phải một

Một schema có thể sở hữu các bảng ở nhiều tablespace; ngược lại, một tablespace có thể chứa segment thuộc nhiều schema:

```text
SCHEMA SALES:
  SALES.ORDERS        -> segment ở APP_DATA
  SALES.IDX_ORDERS    -> segment ở APP_INDEX

SCHEMA SUPPORT:
  SUPPORT.TICKETS     -> segment ở APP_DATA
```

`DEFAULT TABLESPACE` của user thường được sử dụng khi tạo đối tượng không chỉ rõ tablespace, nhưng DBA có thể cấp quota, thu hồi quyền dùng tablespace hoặc chỉ định tablespace khác cho từng đối tượng. **Tên user, tên schema và tên tablespace không bắt buộc giống nhau.**

## 4. Datafile: tệp vật lý cung cấp block cho tablespace

### 4.1. Một datafile chứa gì?

Datafile được Oracle quản lý. Nó có cấu trúc nội bộ, bao gồm thông tin phục vụ quản trị file và các block có thể được cấp phát cho những segment khác nhau. Oracle đọc/ghi các block này thông qua tầng lưu trữ.

Ví dụ các đường dẫn có thể thấy ở môi trường dùng filesystem:

```text
/u02/oradata/LABDB/app_data01.dbf
/u02/oradata/LABDB/app_data02.dbf
```

Trong hệ thống dùng **Oracle Automatic Storage Management (ASM)**, đường dẫn có thể có dạng:

```text
+DATA/LABDB/DATAFILE/app_data.123.987654321
```

Đây là tên file logic do ASM quản lý, không phải đường dẫn thư mục hệ điều hành để dùng `cp`, `mv`, `rm` như file thường. Với **Oracle Managed Files (OMF)**, Oracle còn có thể tự sinh và quản lý tên file dựa trên cấu hình nơi lưu trữ.

Với datafile bình thường, mối quan hệ là:

- **Mỗi datafile thuộc một tablespace** tại một thời điểm.
- **Một tablespace có thể có nhiều datafile** (trừ giới hạn/mô hình đặc thù như bigfile).
- **Một datafile có thể chứa extent của nhiều segment**.
- **Một segment có thể nhận extent từ nhiều datafile trong cùng tablespace**.
- **Một extent cụ thể không cắt ngang ranh giới datafile**.

Datafile không đồng nghĩa segment, và Oracle không bắt buộc tạo một `.dbf` riêng cho từng bảng.

### 4.2. Kích thước và khả năng tăng trưởng

Khi xem datafile, nên phân biệt:

| Thuộc tính | Ý nghĩa |
|---|---|
| Kích thước hiện tại (`BYTES`) | Dung lượng file đang được Oracle ghi nhận |
| `AUTOEXTENSIBLE` | Oracle có được phép mở rộng file khi cần theo cấu hình hay không |
| `MAXBYTES` | Mức tối đa được cấu hình hoặc giới hạn theo chế độ file |
| Dung lượng trống bên trong tablespace | Các block/extent chưa cấp phát cho segment, theo cơ chế quản lý tablespace |
| Dung lượng trống của hệ thống lưu trữ | Chỗ còn trống trên filesystem/ASM disk group hoặc dịch vụ lưu trữ |

Ví dụ một datafile đang có dung lượng 2 GB và bật autoextend đến 8 GB. Điều đó **không có nghĩa** bạn đang có ngay 6 GB vật lý khả dụng: khả năng mở rộng còn phụ thuộc dung lượng còn lại của hệ thống lưu trữ, quota, giới hạn file, cấu hình và điều kiện tại thời điểm cần mở rộng.

Tương tự, thấy `du` hoặc `ls -lh` báo file lớn không cho biết bao nhiêu hàng đang lưu. Oracle có thể đã cấp phát block cho segment trong khi chỉ một phần block chứa dữ liệu ứng dụng.

### 4.3. Khi nào cần thêm hoặc mở rộng datafile?

Đó là thao tác quản trị khi tablespace thiếu không gian có thể cấp phát. DBA có thể điều chỉnh autoextend, resize file hoặc thêm datafile với **câu lệnh Oracle phù hợp**, tùy loại tablespace và phương án lưu trữ. Ví dụ sau chỉ để đọc cú pháp, **không chạy trên máy thực hành khi chưa có quyền và kế hoạch dung lượng**:

```sql
-- Minh họa một lựa chọn quản trị cho smallfile tablespace.
-- Đường dẫn, kích thước và tên tablespace phải thay bằng cấu hình thật.
ALTER TABLESPACE app_data
  ADD DATAFILE '/u02/oradata/LABDB/app_data03.dbf'
  SIZE 256M AUTOEXTEND ON NEXT 64M MAXSIZE 4G;
```

Thực tế, thêm file cho bigfile tablespace không theo cùng cách; ở môi trường OMF/ASM cú pháp có thể không cần chỉ rõ tên filesystem. Việc mở rộng chỉ thực hiện sau khi DBA xác nhận nơi lưu trữ, giới hạn, chính sách backup và phù hợp quy định vận hành.

## 5. Segment: không gian cấp cho bảng, index và các cấu trúc khác

### 5.1. Segment là gì?

**Segment** là tập hợp các extent Oracle đã cấp phát cho một thực thể lưu trữ. Nó là khái niệm phản ánh **dung lượng được cấp phát**, khác với định nghĩa logic của bảng.

Các kiểu segment thường gặp:

| Segment type | Chứa gì? | Ghi chú |
|---|---|---|
| `TABLE` | Dữ liệu của heap table thông thường | Có thể có một segment cho bảng không partition |
| `INDEX` | Cấu trúc chỉ mục | Tách biệt với table segment |
| `LOBSEGMENT` | Dữ liệu LOB được lưu ngoài hàng theo cấu hình | Có thể đi với `LOBINDEX` hoặc cấu trúc phụ trợ |
| `TABLE PARTITION`, `INDEX PARTITION` | Segment của từng partition | Một bảng/index partitioned có thể có nhiều segment |
| `TABLE SUBPARTITION`, `INDEX SUBPARTITION` | Segment ở mức subpartition | Phụ thuộc thiết kế partitioning |
| `UNDO` | Dữ liệu undo | Do cơ chế undo quản lý |
| `TEMPORARY` | Không gian tạm trong quá trình xử lý | Vòng đời và cách theo dõi riêng |

Không phải mọi đối tượng SQL đều có segment riêng:

- **View thông thường** lưu định nghĩa truy vấn, không tự có dữ liệu/segment như table.
- **Sequence**, synonym và metadata có đặc điểm lưu trữ khác; không thể áp dụng máy móc “một object = một segment”.
- **Index** của bảng thường là segment riêng; vì thế tạo `PRIMARY KEY` có thể dẫn đến index segment bên cạnh table segment.
- **Partitioned table** có thể tổ chức dữ liệu thành nhiều segment theo partition/subpartition.
- **LOB** lớn có thể sử dụng segment riêng tùy cấu trúc và cách lưu trữ.
- **Deferred segment creation**: bảng vừa được tạo có thể chưa được cấp phát segment cho đến khi thực sự cần; vì thế có tên trong `USER_TABLES` nhưng chưa có hàng tương ứng trong `USER_SEGMENTS`.

### 5.2. Một segment thuộc tablespace nào?

Thông thường, **mỗi segment thuộc một tablespace** và được phân bổ extent từ các datafile của tablespace đó. Một bảng có thể liên quan đến nhiều segment ở các tablespace khác nhau: table segment trong `APP_DATA`, index segment trong `APP_INDEX`, LOB segment trong `APP_LOB`.

Đừng mô tả “bảng ORDERS nằm trong một datafile” như một quy tắc: bảng có thể có nhiều extent, và các extent của cùng segment có thể nằm rải trên nhiều datafile của tablespace.

### 5.3. Segment được cấp phát và dữ liệu thật có thể chênh lệch

Giả sử `ORDERS` được Oracle cấp phát 128 MB cho table segment, nhưng chỉ có khoảng 75 MB payload và metadata của hàng:

```text
128 MB segment allocated
|-------------------------------|
| dữ liệu + metadata | chỗ trống |
|--------------------|----------|
```

Không nên suy ra số liệu thực tế bằng phép trừ đơn giản vì block còn chứa header, thông tin giao dịch, free space dự trữ và có thể có vùng từng chứa hàng đã bị xóa. `USER_SEGMENTS.BYTES` hoặc `DBA_SEGMENTS.BYTES` chủ yếu cho biết **không gian segment đã được cấp phát**, không phải kích thước dữ liệu hữu ích trên từng hàng.

## 6. Extent: đơn vị cấp phát thêm không gian cho segment

### 6.1. Extent là gì?

**Extent** là một nhóm **Oracle data block liên tiếp trong cùng một datafile** được cấp phát cho **một segment**. Khi segment cần thêm không gian mà các block đã cấp phát không còn đáp ứng, Oracle có thể cấp thêm extent từ phần không gian phù hợp trong tablespace.

Ví dụ một extent gồm 8 block, mỗi block 8 KB:

```text
Extent #0 trong datafile 5:
  block 120  block 121  block 122  block 123
  block 124  block 125  block 126  block 127

  8 block × 8 KB/block = 64 KB
```

Một segment có thể sở hữu nhiều extent:

```text
Segment APP.ORDERS
  Extent 0  -> file 5, block bắt đầu 120, 8 block
  Extent 1  -> file 5, block bắt đầu 256, 8 block
  Extent 2  -> file 6, block bắt đầu 640, 16 block
```

Các số liệu trên chỉ là minh họa. Các extent của segment **không cần nằm cạnh nhau**, cũng không bắt buộc ở cùng datafile; chính mỗi extent mới cần có chuỗi block liên tiếp **trong một file**.

### 6.2. Kích thước extent và cơ chế phân bổ

Oracle có các cơ chế quản lý extent, trong đó phổ biến là **locally managed tablespace (LMT)** với bitmap:

- **`AUTOALLOCATE`**: Oracle lựa chọn kích thước extent dựa trên chính sách/cơ chế phân bổ thích hợp; các extent của một segment có thể không đồng kích thước.
- **`UNIFORM SIZE`**: các extent của tablespace được phân bổ theo kích thước định trước (trong phạm vi quy tắc Oracle cho loại tablespace đó).

Điều này có nghĩa:

- “Extent luôn có 64 KB” là **sai**; 64 KB chỉ là ví dụ.
- “Mọi extent của một segment luôn bằng nhau” cũng **không đúng** trong các bố trí sử dụng autoallocate.
- Số extent nhiều chưa đủ để kết luận có vấn đề hiệu năng; phải xem kiểu truy cập, cấu trúc segment, chiến lược phân bổ và bằng chứng hoạt động thực tế.

Quan sát extents có thể giúp bạn thấy một segment được cấp phát ở bao nhiêu file, tổng dung lượng bao nhiêu, hoặc vị trí block bắt đầu của từng extent.

### 6.3. Oracle cấp thêm extent khi nào?

Một chu trình giản lược với heap table:

```text
INSERT các hàng mới
       |
       v
Oracle tìm block có đủ chỗ trong segment
       |
       +-- Có chỗ --> ghi dữ liệu trong block phù hợp
       |
       +-- Hết chỗ phù hợp
               |
               v
       Oracle cần mở rộng segment
               |
               +-- Tablespace còn extent có thể cấp?
                      |
                      +-- Có --> cấp thêm extent vào segment
                      |
                      +-- Không --> có thể cần mở rộng datafile,
                                      nếu được phép và có tài nguyên
                                      |
                                      +-- Không thể mở rộng --> lỗi
```

Sơ đồ chỉ mô tả ý tưởng phân bổ dung lượng, không phải thuật toán nội bộ chi tiết cho mọi loại segment. Không phải **mỗi lần `INSERT`** là Oracle tạo extent mới. Nhiều hàng dùng chung một data block; nhiều block cùng nằm trong một extent đã có.

### 6.4. Vì sao xóa hàng không giải phóng ngay extent?

`DELETE` xóa hàng về mặt logic và tạo undo cần thiết, nhưng không mặc định thu hồi extent từ segment trả lại tablespace. Chỗ trống sau xóa thường có thể được **tái sử dụng bên trong segment**, tùy tổ chức block và các cơ chế quản lý không gian.

`TRUNCATE` có đặc tính khác `DELETE`, thường đưa high water mark về trạng thái phù hợp và có thể giải phóng extent theo tùy chọn lưu trữ (`DROP STORAGE`/`REUSE STORAGE`), nhưng là DDL và có hành vi commit ngầm. Các lệnh thay đổi cấu trúc như `ALTER TABLE ... MOVE`, shrink và các phương án reclaim cần xem điều kiện áp dụng, tác động đến index/ROWID và được DBA đánh giá trước khi sử dụng.

**Không dùng lệnh hệ điều hành để xóa từng “extent”**: extent là đơn vị Oracle quản lý **bên trong datafile**, không phải tệp riêng được liệt kê bằng `ls`.

## 7. Data block: đơn vị lưu trữ logic nhỏ nhất trong chuỗi

### 7.1. Oracle data block chứa gì?

**Oracle data block** là đơn vị logic nhỏ nhất dùng để quản lý không gian lưu trữ dữ liệu trong mô hình này. Nhiều block hợp thành một extent; nhiều extent hợp thành một segment.

Một data block có thể chứa:

- **Block header** và metadata quản lý block.
- **Thông tin giao dịch/transaction entries** để hỗ trợ quản lý thay đổi đồng thời.
- **Row directory** để Oracle định vị hàng trong block.
- **Row data** đối với block dữ liệu của heap table.
- **Free space** cho thao tác ghi/sửa trong tương lai.

Mô hình đơn giản:

```text
  +----------------------------------------------------+
  | Block header + thông tin giao dịch                 |
  +----------------------------------------------------+
  | Row directory / thông tin định vị                 |
  +----------------------------------------------------+
  | Row data (các hàng hoặc phần hàng)                |
  |                                                    |
  +----------------------------------------------------+
  | Free space                                         |
  +----------------------------------------------------+
```

Kích thước vùng header, cấu trúc block và cách tổ chức dữ liệu phụ thuộc loại segment, block format và tình trạng hoạt động. Index block và undo block không có cách bố trí giống hoàn toàn heap table block.

### 7.2. Block size khác sector và OS block size

Kích thước Oracle data block thông dụng trong nhiều môi trường là **8 KB**, nhưng giá trị thật được xác định bằng cấu hình database/tablespace. Đa số tablespace sử dụng block size chuẩn `DB_BLOCK_SIZE`, còn một số cấu hình hỗ trợ tablespace với nonstandard block size khi thỏa điều kiện tương ứng.

Ví dụ:

| Giả định | Tính toán |
|---|---|
| 1 Oracle block = 8 KB | 8.192 byte/block |
| 1 extent = 64 KB | 8 Oracle block |
| 1 extent = 1 MB | 128 Oracle block |
| Segment có 4 extent 1 MB | 4 MB không gian được cấp phát cho segment |

Các phép tính trên mô tả **dung lượng block được cấp phát**, chưa trừ phần không gian quản lý trong block và chưa phản ánh bao nhiêu dữ liệu hàng thực sự đang có. Kích thước I/O trong thực tế có thể bao gồm nhiều Oracle block; không nên nhầm Oracle data block với kích thước đơn vị đọc của filesystem.

### 7.3. `PCTFREE`, chèn hàng và cập nhật hàng

Với heap table block, Oracle có các cơ chế quản lý chỗ trống. Thuộc tính **`PCTFREE`** cho biết tỉ lệ không gian trong block được dành cho việc tăng kích thước hàng do cập nhật, theo chính sách sử dụng block.

Ví dụ nếu bảng lưu thông tin khách hàng và sau đó cập nhật trường mô tả dài hơn, việc giữ lại free space trong block có thể giúp tránh di chuyển hàng sang block khác. Khi một hàng cập nhật không còn vừa vị trí cũ, **row migration** có thể xảy ra; khi dữ liệu của một hàng cần nhiều block ngay từ đầu, có thể gặp **row chaining**.

`PCTFREE` không nói rằng “10% toàn bộ tablespace luôn trống” hay “mỗi extent chỉ dùng tối đa 90%”. Đây là thuộc tính quản lý **khả năng sử dụng của block** đối với những segment phù hợp, không phải chỉ tiêu dung lượng tablespace.

### 7.4. High Water Mark (HWM) liên quan block như thế nào?

**High Water Mark** biểu diễn ranh giới những block đã từng được sử dụng/định dạng trong phạm vi quản lý của segment theo cơ chế Oracle. Một số thao tác quét đầy đủ bảng (full table scan) có thể phải xét vùng block bên dưới HWM, ngay cả khi sau đó nhiều hàng đã bị `DELETE`.

Vì vậy sau khi xóa nhiều hàng:

1. Số hàng giảm.
2. `USER_SEGMENTS.BYTES` có thể vẫn giữ nguyên.
3. Số extent có thể vẫn giữ nguyên.
4. Không gian rỗng trong segment có thể tái sử dụng.
5. Datafile không tự co nhỏ theo đúng số byte dữ liệu đã xóa.

Đây là một trong những lý do cần phân biệt **dữ liệu logic**, **block đã được sử dụng**, **segment allocated space** và **file size**.

## 8. Phân cấp lưu trữ qua một ví dụ số học

Giả sử database có tablespace `APP_DATA` gồm hai datafile và block size 8 KB:

```text
APP_DATA
  |
  +-- app_data01.dbf      512 MB
  +-- app_data02.dbf      512 MB
```

Giả sử một table segment `ORDERS` được phân bổ:

```text
Extent 0:  64 KB =   8 block, file 1
Extent 1:  64 KB =   8 block, file 1
Extent 2: 1 MB   = 128 block, file 2
Extent 3: 1 MB   = 128 block, file 2
```

Tổng dung lượng extent đã cấp cho segment trong ví dụ:

```text
  64 KB + 64 KB + 1024 KB + 1024 KB = 2176 KB
  Tổng block = 8 + 8 + 128 + 128 = 272 block
```

Từ đó suy ra:

- `ORDERS` có **4 extent** và **272 block được cấp phát** trong ví dụ.
- Tổng không gian segment được cấp qua các extent là **2.125 MB** (2.176 KB chia 1.024).
- Segment dùng **hai datafile** nhưng vẫn **thuộc một tablespace** là `APP_DATA`.
- Hai datafile có tổng kích thước hiện tại **1.024 MB**, nhưng không có nghĩa tất cả số đó còn trống cho `ORDERS`: các segment khác, metadata và phần đã cấp phát đều dùng chung tablespace.
- Không thể suy ra số hàng trong `ORDERS` chỉ từ 272 block vì số hàng/block phụ thuộc kích thước hàng, header, độ trống, loại block và tình trạng dữ liệu.

Đây là ví dụ số học minh họa cho quan hệ cấu trúc, không phải cam kết Oracle sẽ cấp phát đúng chuỗi extent 64 KB, 64 KB, 1 MB, 1 MB trong mọi phiên bản/cấu hình.

## 9. Một bảng có thể liên quan đến những segment nào?

Hãy xét một schema bán hàng:

```text
TABLE: ORDERS
    |-- Table segment (dữ liệu hàng)
    |-- Primary key index segment
    |-- Index trên CUSTOMER_ID
    |-- LOB segment cho cột ATTACHMENT (nếu có)
    |-- Các segment partition riêng (nếu partitioning)
```

Ví dụ thiết kế bảng và index ở hai tablespace riêng:

```sql
-- Chỉ để minh họa DDL; cần có tablespace và quota tương ứng.
CREATE TABLE orders (
    order_id     NUMBER NOT NULL,
    customer_id  NUMBER NOT NULL,
    total_amount NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (order_id)
)
TABLESPACE app_data;

CREATE INDEX idx_orders_customer
    ON orders(customer_id)
    TABLESPACE app_index;
```

Chú ý: `PRIMARY KEY` thường được Oracle thực thi với index. Nếu bạn không quy định tablespace của index cho constraint, index đó có thể được tạo trong tablespace theo quy tắc mặc định/cấu hình. Vì vậy, ngay cả ví dụ này cũng có thể tạo **nhiều segment** ở các vị trí khác nhau.

Nếu bảng được partition theo tháng:

```text
ORDERS (logical table)
   |
   +-- ORDERS_P202601 : table partition segment
   +-- ORDERS_P202602 : table partition segment
   +-- ORDERS_P202603 : table partition segment
```

Mỗi partition có thể có segment riêng và có thể được đặt ở tablespace riêng theo cấu hình. Không thể kết luận rằng `USER_SEGMENTS` phải có đúng một dòng `SEGMENT_NAME = 'ORDERS'` cho mọi bảng partitioned; cần xem cả `SEGMENT_TYPE` và `PARTITION_NAME` (khi có) để hiểu cấu trúc.

## 10. Đọc cấu trúc thực tế qua các data dictionary view

Oracle cung cấp các view cho phép xem tablespace, file, segment và extent. Đây là cách quan sát đáng tin cậy hơn việc đoán từ tên tệp `.dbf`.

### 10.1. Những view cần nhớ

| View | Đối tượng | Quyền truy cập điển hình |
|---|---|---|
| `USER_TABLES` | Bảng thuộc schema đang đăng nhập | Người dùng thông thường |
| `USER_SEGMENTS` | Segment thuộc schema đang đăng nhập | Người dùng thông thường |
| `USER_EXTENTS` | Các extent của segment thuộc schema đang đăng nhập | Người dùng thông thường |
| `USER_INDEXES` | Thông tin index trong schema | Người dùng thông thường |
| `DBA_TABLESPACES` | Thông tin tablespace trong database/container đang truy vấn | Cần quyền xem dictionary phù hợp |
| `DBA_DATA_FILES` | Datafile và dung lượng liên quan permanent/undo tablespace | Cần quyền xem dictionary phù hợp |
| `DBA_TEMP_FILES` | Tempfile của temporary tablespace | Cần quyền xem dictionary phù hợp |
| `DBA_SEGMENTS` | Segment thuộc nhiều schema | Cần quyền xem dictionary phù hợp |
| `DBA_EXTENTS` | Extent thuộc nhiều schema | Cần quyền xem dictionary phù hợp |
| `DBA_FREE_SPACE` | Các extent không gian trống trong permanent tablespace theo view | Cần quyền xem dictionary phù hợp |

Ví dụ sau được viết cho Oracle SQL*Plus/SQLcl hoặc công cụ có thể chạy SQL. Nếu dùng kiến trúc CDB/PDB, kết quả phụ thuộc **container/PDB đang kết nối** và quyền; tài khoản ở một PDB không có nghĩa sẽ nhìn được toàn bộ database khác.

### 10.2. Xem segment thuộc schema hiện tại

```sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks,
       extents
FROM user_segments
ORDER BY tablespace_name, segment_type, segment_name;
```

Ý nghĩa các cột chính:

- `SEGMENT_NAME`: tên segment hoặc đối tượng lưu trữ liên quan.
- `SEGMENT_TYPE`: TABLE, INDEX, LOBSEGMENT, các biến thể PARTITION...
- `TABLESPACE_NAME`: tablespace chứa segment.
- `BYTES`: tổng số byte đã được cấp cho segment.
- `BLOCKS`: tổng số block đã được cấp cho segment.
- `EXTENTS`: số extent đã cấp cho segment.

Không nên hiểu `BYTES` là “tổng kích thước dữ liệu của mọi hàng”. Nó phản ánh **dung lượng đã được cấp phát** cho segment ở thời điểm truy vấn.

### 10.3. Xem từng extent của một segment

Đối với một bảng không partition tên `DEMO_STORAGE`:

```sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       extent_id,
       file_id,
       block_id,
       blocks,
       bytes
FROM user_extents
WHERE segment_name = 'DEMO_STORAGE'
ORDER BY extent_id;
```

Giải thích:

| Cột | Ý nghĩa |
|---|---|
| `EXTENT_ID` | Số thứ tự extent trong segment |
| `FILE_ID` | Định danh datafile được Oracle dùng cho extent |
| `BLOCK_ID` | Block bắt đầu của extent trong datafile đó |
| `BLOCKS` | Số block trong extent |
| `BYTES` | Kích thước extent theo byte |

Nếu `FILE_ID` thay đổi giữa các hàng, bạn đã thấy các extent của một segment được cấp trong **nhiều datafile**. Nếu `BLOCKS` của các extent khác nhau, nhiều khả năng đây là tablespace dùng cơ chế cấp phát có kích thước extent thay đổi.

Ví dụ kết quả **minh họa**, không phải output đã chạy:

```text
EXTENT_ID  FILE_ID  BLOCK_ID  BLOCKS  BYTES
---------  -------  --------  ------  -------
        0        7       128       8    65536
        1        7       256       8    65536
        2        8      1024     128  1048576
```

Kết quả trên có nghĩa extent 0 nằm ở file 7, từ block 128 và gồm 8 block; extent 2 nằm trọn trong file 8. Nó **không** có nghĩa Oracle đã lưu “mỗi hàng vào một extent”.

### 10.4. Liên hệ `FILE_ID` với tên datafile

Để xem tên file vật lý/logical của file mà extent đang sử dụng, DBA có thể dùng:

```sql
SELECT e.owner,
       e.segment_name,
       e.segment_type,
       e.extent_id,
       e.file_id,
       f.file_name,
       e.block_id,
       e.blocks,
       e.bytes
FROM dba_extents e
JOIN dba_data_files f
  ON f.file_id = e.file_id
 AND f.tablespace_name = e.tablespace_name
WHERE e.owner = 'APP'
  AND e.segment_name = 'DEMO_STORAGE'
ORDER BY e.extent_id;
```

Trong ví dụ, `'APP'` là schema giả định cần thay bằng schema đang xem; câu lệnh đòi quyền phù hợp trên các `DBA_` view. Đối với các đối tượng partitioned hoặc LOB, nên mở rộng điều kiện/lựa chọn cột để xem đúng segment và partition. Temporary space không tra cứu theo cách này vì dùng tempfile và các view quản lý riêng.

### 10.5. Xem tablespace và datafile

Để biết cấu hình tablespace:

```sql
SELECT tablespace_name,
       contents,
       block_size,
       extent_management,
       allocation_type,
       segment_space_management,
       bigfile
FROM dba_tablespaces
ORDER BY tablespace_name;
```

Để biết các datafile:

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
ORDER BY tablespace_name, file_id;
```

Và đối với tempfile:

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_temp_files
ORDER BY tablespace_name, file_id;
```

`BLOCK_SIZE` giúp bạn biết đơn vị Oracle block của tablespace; `ALLOCATION_TYPE` liên quan cách phân bổ extent; `SEGMENT_SPACE_MANAGEMENT` cho biết cơ chế quản lý chỗ trống trong segment. Đây là **các khái niệm khác nhau**: phân bổ extent diễn ra ở cấp tablespace/segment, còn quản lý chỗ trống trong block diễn ra ở cấp segment.

### 10.6. Xem không gian free của permanent tablespace

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

Query này cho thấy tổng các extent trống được báo qua `DBA_FREE_SPACE`, **không nhất thiết là toàn bộ dung lượng có thể tăng trưởng trong tương lai**. Nó chưa cộng dung lượng autoextend chưa sử dụng, không phản ánh đầy đủ giới hạn filesystem/ASM và có các khác biệt trong cách ghi nhận với temporary tablespace. Những tablespace không có hàng trong view có thể không xuất hiện trong kết quả tổng hợp, cần xem thêm file và tình trạng không gian.

Đừng đánh đồng:

```text
Datafile hiện có  ≠  Segment đã cấp phát  ≠  Dữ liệu hữu ích đang lưu

Free extents trong tablespace
    ≠ Free space trong các block đã cấp cho segment
    ≠ Dung lượng storage còn có thể mở rộng file
```

## 11. Thực hành: nhìn thấy mối quan hệ từ một bảng thật

Phần này hướng đến một schema thực hành có quyền `CREATE TABLE` và quota phù hợp trên tablespace mặc định. Chỉ thực hiện trong schema được phép tạo đối tượng. Nếu bạn chỉ có quyền đọc, hãy bỏ phần DDL/DML và thực hiện các câu `SELECT` trên đối tượng sẵn có mà bạn được cấp quyền.

### Bước 1. Tạo bảng nhỏ, yêu cầu cấp segment ngay

```sql
CREATE TABLE demo_storage (
    id      NUMBER NOT NULL,
    payload VARCHAR2(100),
    CONSTRAINT pk_demo_storage PRIMARY KEY (id)
)
SEGMENT CREATION IMMEDIATE;
```

Lưu ý `PRIMARY KEY` có thể làm Oracle tạo thêm một **index segment**. `SEGMENT CREATION IMMEDIATE` được sử dụng để tập trung vào việc quan sát table segment ngay sau khi tạo, thay vì phụ thuộc thời điểm Oracle trì hoãn cấp phát segment. DDL có hành vi commit ngầm; không sử dụng bảng thật để thử thao tác này.

### Bước 2. Xem bảng, index và tablespace

```sql
SELECT table_name, tablespace_name
FROM user_tables
WHERE table_name = 'DEMO_STORAGE';

SELECT index_name, index_type, tablespace_name
FROM user_indexes
WHERE table_name = 'DEMO_STORAGE';
```

Nếu chưa quy định `TABLESPACE` trong DDL, Oracle dùng quy tắc mặc định và quyền/quota của user để chọn tablespace. Index có thể là một segment riêng, và tablespace của index không nhất thiết là lựa chọn người học tưởng tượng.

### Bước 3. Xem các segment đã được cấp phát

```sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       extents,
       blocks,
       bytes
FROM user_segments
WHERE segment_name = 'DEMO_STORAGE'
   OR segment_name IN (
       SELECT index_name
       FROM user_indexes
       WHERE table_name = 'DEMO_STORAGE'
   )
ORDER BY segment_type, segment_name;
```

Bạn có thể quan sát ít nhất cấu trúc liên quan table và index khi các segment đã được cấp phát theo điều kiện của database. Nếu index segment không xuất hiện ngay, cần xét cơ chế tạo/cấp phát thực tế; không suy ra chỉ từ tên đối tượng rằng một hàng trong dictionary phải tồn tại trước mọi thao tác.

### Bước 4. Xem chi tiết các extent của table segment

```sql
SELECT segment_name,
       extent_id,
       file_id,
       block_id,
       blocks,
       bytes
FROM user_extents
WHERE segment_name = 'DEMO_STORAGE'
  AND segment_type = 'TABLE'
ORDER BY extent_id;
```

Ghi lại `EXTENT_ID`, `FILE_ID`, `BLOCK_ID`, `BLOCKS`. Mỗi dòng tương ứng một extent và cho thấy nó được ánh xạ tới vị trí trong datafile nào.

### Bước 5. Thêm dữ liệu rồi quan sát lại

```sql
INSERT INTO demo_storage (id, payload)
SELECT LEVEL, RPAD('x', 100, 'x')
FROM dual
CONNECT BY LEVEL <= 1000;

COMMIT;
```

Sau đó chạy lại hai truy vấn `USER_SEGMENTS` và `USER_EXTENTS` ở trên. **Không đảm bảo** sẽ thấy thêm extent, vì kết quả tùy dung lượng được cấp sẵn, block size, thiết lập không gian và cấu trúc segment. Điều bạn cần nhận biết là **số hàng tăng không kéo theo số extent tăng theo tỉ lệ 1:1**.

Có thể xem số hàng bằng:

```sql
SELECT COUNT(*) AS row_count
FROM demo_storage;
```

Đồng thời, `USER_SEGMENTS.BYTES` có thể lớn hơn đáng kể phần payload `1000 × 100 byte`: đó là hiện tượng bình thường vì còn metadata, chỉ mục, free space và phân bổ theo block/extent.

### Bước 6. Xóa một phần hàng rồi xem extent

```sql
DELETE FROM demo_storage
WHERE id <= 500;

COMMIT;
```

Chạy lại:

```sql
SELECT COUNT(*) AS row_count FROM demo_storage;

SELECT segment_name, extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'DEMO_STORAGE';
```

Nếu số hàng đã giảm nhưng `EXTENTS` và `BYTES` không giảm, điều đó minh họa khác biệt giữa **hàng đang tồn tại** và **không gian segment đã được cấp phát**. Không nên cố điều chỉnh file trên hệ điều hành để “thu nhỏ” bằng tay.

### Bước 7. Dọn đối tượng thực hành khi không còn cần

Chỉ trong schema thực hành và sau khi xác nhận đúng đối tượng do chính bạn tạo:

```sql
DROP TABLE demo_storage PURGE;
```

`PURGE` bỏ qua recycle bin cho bảng này theo cơ chế tương ứng, vì vậy **không nên dùng với bảng cần khôi phục**. Thao tác drop có tính phá hủy và DDL có commit ngầm. Nếu không được phép hoặc không chắc schema, hãy để DBA/người quản lý môi trường xử lý.

### Ghi lại kết quả của bài thực hành

| Chỉ số | Sau CREATE | Sau INSERT | Sau DELETE |
|---|---|---|---|
| Số hàng `COUNT(*)` | 0 | ... | ... |
| Số extent của table segment | ... | ... | ... |
| Số block đã cấp cho table segment | ... | ... | ... |
| Số byte đã cấp cho table segment | ... | ... | ... |
| Có index segment riêng? | ... | ... | ... |

Mục tiêu là **quan sát quan hệ lưu trữ**, không phải dự đoán số lượng extent cố định. Kết quả thực tế thay đổi theo phiên bản và cấu hình Oracle.

## 12. Các tình huống vận hành liên quan trực tiếp đến quan hệ lưu trữ

### 12.1. `ORA-01653`: không thể mở rộng table segment

Một lỗi dạng:

```text
ORA-01653: unable to extend table ... in tablespace ...
```

thường báo Oracle không thể cấp thêm extent phù hợp cho table segment trong tablespace được nêu. Nguyên nhân cần kiểm tra bao gồm:

1. Tablespace còn extent trống phù hợp không?
2. Datafile có được phép autoextend không và có chạm giới hạn không?
3. Filesystem hoặc ASM disk group có đủ dung lượng không?
4. Có giới hạn quota, tablespace/file hoặc chính sách quản trị liên quan không?
5. Segment cụ thể có đặc điểm lưu trữ nào cần chú ý không?

Không thể sửa lỗi chỉ bằng việc tăng `PCTFREE` hoặc tạo thêm index; vấn đề trọng tâm là **khả năng cấp phát extent cho segment**.

### 12.2. `ORA-01654`: không thể mở rộng index segment

Index cũng có segment/extent riêng. Nếu index được đặt ở tablespace khác table, tablespace index có thể thiếu chỗ dù tablespace của bảng còn dư. Vì vậy hãy tra `USER_INDEXES`, `USER_SEGMENTS` hoặc `DBA_SEGMENTS` để xem index thuộc tablespace nào.

### 12.3. `ORA-01652`: không thể mở rộng temporary segment

Một số truy vấn sort/join/operations cần không gian tạm. Lỗi dạng `ORA-01652` liên quan không thể cấp phát đủ không gian cho temporary segment. Khi đó cần xem **temporary tablespace, tempfile, các phiên dùng TEMP và dung lượng khả dụng**, không nên chỉ chăm chú vào datafile của tablespace lưu bảng.

### 12.4. Vì sao tablespace trống nhưng DML vẫn bị lỗi?

Dung lượng tổng thể là một trong nhiều điều kiện. Bối cảnh cụ thể còn phụ thuộc kích thước extent cần cấp, trạng thái file, giới hạn maxsize/autoextend, quota, chính sách tablespace và vị trí trong mô hình lưu trữ. Kết quả `DBA_FREE_SPACE` cần được đặt cạnh thông tin datafile và lỗi thực tế; không nên dựa vào một con số “free MB” duy nhất để kết luận.

### 12.5. Vì sao một bảng vài nghìn hàng có segment khá lớn?

Có thể do **extent được cấp theo bậc**, block chưa dùng hết, free space dành cho update, dữ liệu từng bị xóa, index/LOB riêng, hoặc các đặc điểm tổ chức bảng. Khi đo dung lượng, cần xác định bạn đang đo **table segment riêng**, **tất cả segment liên quan** hay **dữ liệu hàng hữu ích**.

### 12.6. Vì sao database còn rất nhiều chỗ trên ổ nhưng tablespace hết dung lượng?

Ổ đĩa và tablespace là hai lớp riêng. Datafile có thể đang ở kích thước giới hạn, tắt autoextend, đạt maxsize, hoặc storage cấu hình cho tablespace cụ thể không thể tăng thêm theo cách thông thường. Thấy filesystem trống chưa có nghĩa segment có thể nhận thêm extent.

## 13. Quản lý không gian extent và block: những cơ chế cần biết

Hai tên thường gặp trong mô tả lưu trữ Oracle:

| Cơ chế | Phạm vi | Ý nghĩa |
|---|---|---|
| **Locally Managed Tablespace (LMT)** | Quản lý cấp phát extent ở tablespace | Dùng metadata/bitmap phù hợp để ghi nhận extent đã cấp và còn trống |
| **Automatic Segment Space Management (ASSM)** | Quản lý chỗ trống bên trong segment | Dùng bitmap để quản lý block theo mức chỗ trống có thể sử dụng |

LMT giải quyết câu hỏi: “**Extent nào của tablespace** có thể cấp cho segment?”. ASSM giải quyết câu hỏi: “**Block nào trong segment** có không gian phù hợp để ghi dữ liệu?”. Đây là hai tầng quản lý khác nhau.

Một số thuộc tính thường thấy:

```sql
SELECT tablespace_name,
       extent_management,
       allocation_type,
       segment_space_management
FROM dba_tablespaces
WHERE tablespace_name = 'APP_DATA';
```

`EXTENT_MANAGEMENT`, `ALLOCATION_TYPE` và `SEGMENT_SPACE_MANAGEMENT` giải thích nhiều hành vi phân bổ có thể thấy khi quan sát extent/block. Cần quyền xem dictionary phù hợp.

## 14. Những phát biểu dễ gây nhầm lẫn

| Phát biểu | Đúng hay sai? | Giải thích |
|---|---|---|
| “Mỗi bảng trong Oracle có một datafile riêng.” | Sai | Nhiều segment có thể chia sẻ datafile; một segment cũng có thể trải trên nhiều datafile qua các extent |
| “Một extent trải qua hai datafile nếu thiếu chỗ.” | Sai | Extent gồm các block liên tiếp **trong một datafile** |
| “Một segment chỉ nằm trong một tablespace.” | Về nguyên tắc đúng với từng segment | Các extent của segment được cấp trong một tablespace; một đối tượng logic có thể có nhiều segment ở nhiều tablespace |
| “Một datafile thuộc nhiều tablespace cùng lúc.” | Sai theo mô hình thông thường | Datafile được gắn với một tablespace |
| “`USER_SEGMENTS.BYTES` chính là dung lượng các hàng đang lưu.” | Sai | Đó là không gian segment đã cấp phát |
| “Xóa 90% hàng sẽ làm datafile nhỏ đi 90%.” | Sai | Không gian bên trong segment có thể được tái sử dụng mà file không co |
| “Một `INSERT` tạo một extent.” | Sai | Nhiều hàng có thể dùng chung block/extent đã cấp |
| “Tablespace chỉ là một thư mục lưu `.dbf`.” | Sai | Tablespace là đối tượng logic; datafile/ASM file là biểu diễn lưu trữ |
| “Tất cả tablespace có datafile như nhau.” | Sai | Temporary tablespace thường sử dụng tempfile |
| “Tăng datafile là cách duy nhất để sửa vấn đề không gian.” | Sai | Cần phân tích nguyên nhân, khả năng tái sử dụng/reclaim, autoextend, giới hạn và thiết kế lưu trữ |
| “Block luôn bằng 8 KB.” | Sai | 8 KB là giá trị thường gặp, không phải quy tắc cho mọi tablespace |
| “Một bảng `CREATE TABLE` phải lập tức xuất hiện trong `USER_SEGMENTS`.” | Không luôn đúng | Deferred segment creation có thể trì hoãn cấp phát |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Tablespace `APP_DATA` có hai datafile. Segment `ORDERS` có thể nhận extent ở cả hai file không?

**Trả lời:** Có, trong mô hình phù hợp; segment vẫn thuộc một tablespace, và mỗi extent được cấp trong một datafile cụ thể.

**Câu 2.** Extent A chứa 16 block kích thước 8 KB. Extent đó có bao nhiêu KB không gian được cấp phát?

**Trả lời:** `16 × 8 KB = 128 KB`. Đây là dung lượng extent, không có nghĩa toàn bộ 128 KB đều là dữ liệu hàng hữu ích.

**Câu 3.** Table `CUSTOMERS` có 10 MB data, còn `USER_SEGMENTS.BYTES` báo 16 MB. Có mâu thuẫn không?

**Trả lời:** Không. Segment được cấp phát theo extent/block và có metadata, free space, vùng dự trữ hoặc không gian từng sử dụng.

**Câu 4.** Vì sao một index có thể gặp lỗi thiếu không gian khi tablespace của table còn trống?

**Trả lời:** Index là segment riêng và có thể được đặt trong tablespace khác. Cần kiểm tra tablespace/index segment tương ứng.

**Câu 5.** Datafile 1 đã đạt giới hạn, nhưng datafile 2 cùng tablespace còn không gian thích hợp. Segment có bắt buộc dừng tăng trưởng không?

**Trả lời:** Không nhất thiết. Oracle có thể cấp extent từ datafile khác **cùng tablespace** khi đáp ứng điều kiện. Quyết định thực tế phụ thuộc cấu hình lưu trữ, loại tablespace và khả năng cấp phát.

**Câu 6.** Tại sao bạn không tìm được dữ liệu từng hàng bằng cách mở `app_data01.dbf` bằng text editor?

**Trả lời:** Datafile là định dạng lưu trữ do Oracle quản lý với block, metadata và cấu trúc nội bộ; truy xuất dữ liệu phải qua SQL và engine Oracle. Tự sửa nội dung file có thể phá hỏng database.

**Câu 7.** Có thể tính số hàng trong một segment chỉ từ `EXTENTS`, `BLOCKS` và `BYTES` không?

**Trả lời:** Không. Các số liệu đó mô tả không gian cấp phát; số hàng phụ thuộc đặc điểm dữ liệu và tổ chức block. Dùng SQL phù hợp, thống kê đáng tin cậy hoặc công cụ phân tích dành riêng để xác định.

## 16. Kết luận

Mối quan hệ lưu trữ của Oracle có thể ghi nhớ theo một trục:

```text
                      [TABLESPACE]
                      /          \
                     /            \
               [SEGMENTS]      [DATAFILES]
                   |               ^
               [EXTENTS] ---------+
                   |
              [DATA BLOCKS]
```

**Tablespace** là không gian logic, **datafile** là nơi lưu trữ vật lý của các block, **segment** là không gian dành cho bảng/index/cấu trúc lưu trữ, **extent** là đơn vị phân bổ gồm các block liên tiếp trong một datafile và **data block** là đơn vị lưu trữ logic nhỏ nhất mà Oracle quản lý trong mô hình này. Một segment có thể nhận nhiều extent ở nhiều file thuộc cùng tablespace; nhiều segment cùng chia sẻ các file.

Khi đánh giá dung lượng hay xử lý lỗi mở rộng, cần tách bạch **file size**, **extent trống của tablespace**, **segment đã được cấp phát**, **block còn sử dụng được** và **dữ liệu thực tế trong hàng**. Cách tiếp cận này giúp bạn đọc `USER_SEGMENTS`, `USER_EXTENTS`, `DBA_DATA_FILES` và `DBA_TABLESPACES` đúng ý nghĩa, đồng thời hiểu rõ hơn quyết định lưu trữ của Oracle Database.
