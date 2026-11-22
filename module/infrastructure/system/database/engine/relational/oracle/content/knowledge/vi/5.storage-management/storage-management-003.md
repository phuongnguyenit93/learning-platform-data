# Locally managed tablespace và tự động quản lý không gian segment trong Oracle

Khi một ứng dụng ghi thêm dữ liệu vào bảng Oracle, database phải quyết định **lấy không gian ở đâu** và **ghi vào block nào**. Hai câu hỏi nghe giống nhau nhưng thuộc hai cấp quản lý khác nhau:

1. **Locally managed tablespace (LMT)** quản lý việc **cấp phát và thu hồi extent** giữa tablespace và các segment. Oracle dùng các **bitmap** để ghi nhận extent đã được cấp phát hay còn trống.
2. **Automatic Segment Space Management (ASSM)** quản lý **không gian còn khả dụng trong các data block của segment**, để Oracle tìm block thích hợp khi chèn dòng. Oracle cũng dùng bitmap, nhưng bitmap này phục vụ cấp **segment/block**, không phải đánh dấu extent tự do của tablespace.

Đây là những cơ chế nền tảng của lưu trữ Oracle hiện đại. Hiểu đúng ranh giới LMT và ASSM giúp đọc cấu hình tablespace, giải thích vì sao bảng vẫn tăng dung lượng dù đã xóa dữ liệu, nhận diện vấn đề tranh chấp khi insert đồng thời và tránh nhầm lẫn các tùy chọn `AUTOALLOCATE`, `AUTOEXTEND` và `SEGMENT SPACE MANAGEMENT AUTO`.

## 1. Từ tablespace đến block: biết chính xác Oracle quản lý cái gì

Oracle tổ chức lưu trữ dữ liệu quan hệ theo các lớp logic và vật lý:

```text
Oracle Database / PDB
  |
  +-- TABLESPACE app_data       [không gian lưu trữ logic]
        |
        +-- DATAFILE 01.dbf     [file vật lý/được quản lý bởi storage]
        +-- DATAFILE 02.dbf
        |
        +-- SEGMENT của bảng ORDERS
        |     +-- EXTENT 1: nhiều Oracle data block liên tiếp
        |     +-- EXTENT 2: nhiều Oracle data block liên tiếp
        |     +-- ...
        |
        +-- SEGMENT của index IDX_ORDERS_CUSTOMER
              +-- EXTENT 1
              +-- EXTENT 2

        LMT theo dõi extent đã cấp / chưa cấp trong tablespace.
        ASSM theo dõi block còn chỗ ghi trong từng segment.
```

| Thành phần | Vai trò | Câu hỏi thường gặp |
|---|---|---|
| **Tablespace** | Tập hợp không gian logic chứa các segment; thường được hỗ trợ bởi một hay nhiều datafile | Tablespace có còn extent trống để cấp phát không? |
| **Datafile** | File chứa các Oracle block cho một tablespace | File có thể tăng kích thước hoặc thêm file mới không? |
| **Segment** | Đơn vị lưu trữ cho một đối tượng/nhóm dữ liệu như table, index, LOB | Segment đã được cấp phát bao nhiêu byte/extent? |
| **Extent** | Tập các block liền kề trong một datafile, được cấp cho một segment | Khi segment lớn lên, Oracle lấy thêm extent như thế nào? |
| **Data block** | Đơn vị I/O và lưu trữ logic nhỏ hơn bên trong extent | Block nào còn chỗ để insert hoặc cập nhật dòng? |

Một bảng có thể có segment dữ liệu riêng và nhiều segment index/LOB khác nhau. Đối tượng vừa được tạo **chưa chắc đã có segment** nếu cấu hình cho phép *deferred segment creation*: Oracle chỉ cấp phát segment khi cần ghi dữ liệu. Vì vậy, không thấy tên bảng mới trong `USER_SEGMENTS` chưa chắc là lỗi.

**Quy tắc nhớ:** *LMT quyết định extent thuộc segment nào; ASSM giúp xác định block bên trong segment nào có đủ chỗ để ghi.* Hai cơ chế thường cùng được sử dụng nhưng phục vụ hai bài toán khác nhau.

## 2. Locally managed tablespace (LMT) là gì?

**Locally managed tablespace** là tablespace mà trạng thái cấp phát extent được quản lý bằng **bitmap trong cấu trúc lưu trữ của chính tablespace**, thay vì dựa vào các bảng từ điển dữ liệu để ghi nhận từng lần cấp phát extent như mô hình **dictionary-managed tablespace (DMT)** cũ.

Mỗi bitmap biểu diễn trạng thái của một tập đơn vị không gian: phần nào còn sẵn để cấp phát, phần nào đã được phân cho segment. Khi segment cần tăng kích thước, Oracle tham khảo thông tin không gian trống, tìm extent phù hợp, cấp phát và cập nhật metadata tương ứng.

```text
TABLESPACE (LMT)
  Bitmap quản lý extent:
  [USED][USED][FREE][FREE][USED][FREE][...]
            |                   |
      extent đã thuộc       extent có thể
      một segment           cấp phát tiếp

  TABLE ORDERS       -> extent A + extent B
  INDEX ORDERS_IDX   -> extent E
```

Hình chỉ minh họa ý tưởng; cấu trúc bitmap thực tế và đơn vị quản lý có thể khác theo chính sách extent và phiên bản Oracle.

### 2.1. LMT giải quyết vấn đề gì so với DMT?

Trong mô hình dictionary-managed trước đây, metadata extent được quản lý qua các cấu trúc dictionary; việc cấp phát/thu hồi thường làm tăng tác động cập nhật metadata dùng chung. LMT đưa metadata không gian về chính tablespace dưới dạng bitmap, giúp quản lý extent hiệu quả và giảm một số điểm tranh chấp trên dictionary khi nhiều object cùng tăng dung lượng.

Ưu điểm thực tế của LMT:

- **Giảm phụ thuộc vào cập nhật dictionary** cho thao tác cấp phát extent thường xuyên.
- **Quản lý không gian tập trung theo tablespace**, phù hợp với mô hình lưu trữ Oracle hiện đại.
- **Đơn giản hóa quản trị extent**: có thể để Oracle chọn cỡ extent qua `AUTOALLOCATE` hoặc dùng kích thước cố định qua `UNIFORM`.
- **Định vị dung lượng thuận tiện hơn** bằng các view phản ánh datafile, segment, extent và phần không gian trống.

Không nên hiểu LMT nghĩa là không còn mọi contention, không bao giờ thiếu không gian hoặc không cần theo dõi datafile. LMT chỉ thay đổi **cách Oracle quản lý việc cấp phát extent**.

### 2.2. `AUTOALLOCATE`: Oracle chọn kích thước extent

Một LMT có thể dùng chế độ cấp phát extent tự động:

```sql
EXTENT MANAGEMENT LOCAL AUTOALLOCATE
```

Trong chế độ này, Oracle quyết định kích thước các extent khi segment phát triển, dựa trên chính sách nội bộ và kích thước/nhu cầu của segment. Extent trong cùng segment **không bắt buộc có cùng kích thước**. Chế độ này thuận tiện khi có nhiều bảng/index với tốc độ phát triển khác nhau.

Điểm cần chú ý:

- `AUTOALLOCATE` nói về **kích thước extent được cấp cho segment**; không nói datafile sẽ tự lớn thêm.
- Thuật toán, các mức kích thước và thời điểm đổi mức là chi tiết triển khai; không nên lập kế hoạch bằng cách giả định một bảng luôn nhận đúng một mức extent cố định.
- Dù chọn extent tự động, segment vẫn cần có **free extent đủ điều kiện** trong tablespace và dung lượng lưu trữ thực tế phù hợp.

### 2.3. `UNIFORM SIZE`: extent có kích thước cố định

Một LMT cũng có thể sử dụng:

```sql
EXTENT MANAGEMENT LOCAL UNIFORM SIZE 1M
```

Khi đó các extent được cấp trong tablespace có cùng kích thước được chỉ định, ở ví dụ là `1M`. Chế độ này giúp dự đoán việc cấp phát hơn, có thể hữu ích với workload hoặc yêu cầu quản trị cụ thể, nhưng có thể dành sẵn nhiều không gian cho đối tượng nhỏ; ví dụ một segment nhỏ được cấp một extent 1 MB vẫn có thể chỉ chứa vài block dữ liệu thực dùng.

**Không có quy tắc “UNIFORM luôn nhanh hơn AUTOALLOCATE”.** Lựa chọn cần dựa trên kiểu object, mẫu tăng trưởng, số lượng segment, quản lý dung lượng và kết quả đo. Với nhiều ứng dụng thông thường, để Oracle quản lý extent qua `AUTOALLOCATE` là điểm khởi đầu hợp lý.

### 2.4. So sánh chính sách LMT

| Thuộc tính | `AUTOALLOCATE` | `UNIFORM SIZE` |
|---|---|---|
| Cỡ extent | Oracle tự chọn theo chính sách và tăng trưởng segment | Cố định theo kích thước chỉ định |
| Độ linh hoạt | Phù hợp khi object có kích thước và nhịp tăng khác nhau | Phù hợp khi muốn kiểm soát đơn vị cấp phát |
| Độ dễ dự đoán | Cỡ extent có thể thay đổi trong vòng đời segment | Mỗi extent có cùng cỡ; dễ ước lượng lượng không gian cấp thêm |
| Rủi ro cần cân nhắc | Không nên dự đoán cỡ extent chỉ từ số dòng | Có thể dư thừa không gian đã cấp cho nhiều object nhỏ |
| Tự mở rộng datafile | **Không**; đây là tính năng riêng | **Không**; đây là tính năng riêng |

Ở hệ thống Oracle hiện đại, LMT là cơ chế chuẩn; DMT chủ yếu gặp trong tài liệu lịch sử hoặc khi nghiên cứu hệ thống cũ. Không nên tự thiết kế tablespace mới theo DMT.

## 3. Automatic Segment Space Management (ASSM) là gì?

**Automatic Segment Space Management** tự động quản lý các **block có khoảng trống phù hợp cho thao tác ghi trong segment**. Khi insert một dòng mới, Oracle cần tìm block còn đủ chỗ, hoặc sử dụng/cấp thêm block từ những extent đã thuộc segment. ASSM duy trì thông tin mức độ đầy/trống của block thông qua **bitmap trong segment**.

```text
SEGMENT của bảng ORDERS
  |
  +-- Bitmap chỉ mức độ còn trống của block
  |       Block A: gần đầy
  |       Block B: còn chỗ
  |       Block C: trống nhiều
  |
  +-- Extent 1
  |     [Block A][Block B][Block C][...]
  +-- Extent 2
        [Block D][Block E][Block F][...]

Khi INSERT -> Oracle tra thông tin mức trống -> chọn block phù hợp.
```

Bitmap của ASSM **không phải** bitmap quản lý extent của LMT: chúng nằm ở các cấp khác nhau và trả lời các câu hỏi khác nhau.

### 3.1. Vì sao cần ASSM thay cho quản lý freelist thủ công?

Trước ASSM, mô hình **manual segment space management (MSSM)** dùng các *freelist* để theo dõi block có thể nhận thêm dòng. DBA có thể phải điều chỉnh `FREELISTS`, `FREELIST GROUPS` cùng các tham số liên quan để cân bằng ghi đồng thời trên nhiều phiên.

ASSM dùng bitmap để Oracle tự duy trì thông tin block có khoảng trống, qua đó giảm nhu cầu cấu hình freelist thủ công và thường hỗ trợ tốt các workload có nhiều session đồng thời insert. Điều đó **không bảo đảm mọi ứng dụng đều hết tranh chấp**: index hot block, khóa giao dịch, ITL, I/O, redo, sequence và cách thiết kế dữ liệu vẫn có thể là điểm nghẽn.

| Tiêu chí | MSSM (Manual) | ASSM (Automatic) |
|---|---|---|
| Theo dõi block còn chỗ | Freelist và cơ chế quản lý thủ công | Bitmap của segment |
| Tham số freelist | Có ý nghĩa với cơ chế manual | Không dùng cơ chế freelist truyền thống cho segment ASSM |
| `PCTUSED` | Tham gia quyết định khi nào block quay lại danh sách có thể insert | Không điều khiển lựa chọn block theo cách của MSSM |
| `PCTFREE` | Có ý nghĩa | **Vẫn có ý nghĩa**, đặc biệt để chừa chỗ cho update làm hàng lớn lên |
| Cấp phát extent | Do cơ chế tablespace, ví dụ LMT | **Không thay thế LMT**; ASSM quản lý block trong segment |
| Vận hành | Cần hiểu và đôi khi tinh chỉnh freelist | Oracle tự động quản lý mức trống của block |

### 3.2. ASSM phân loại block theo mức độ còn trống

Thông tin bitmap giúp Oracle nhận biết nhóm block còn khoảng trống khác nhau mà không cần lưu một danh sách block trống thủ công như MSSM. Khi cần quan sát sâu, gói `DBMS_SPACE.SPACE_USAGE` có thể cung cấp nhóm block theo các dải dung lượng trống, thường biểu diễn bằng `FS1` đến `FS4` và `FULL`:

| Nhóm thông tin | Mức độ trống xấp xỉ |
|---|---|
| `FS1` | 0–25% không gian trống |
| `FS2` | 25–50% không gian trống |
| `FS3` | 50–75% không gian trống |
| `FS4` | 75–100% không gian trống |
| `FULL` | Block được coi là đầy theo tiêu chí quản lý |

Các nhóm là một **cách quan sát trạng thái**, không thay cho phép đo chính xác từng byte có thể sử dụng cho mọi loại dòng. Metadata và overhead của block cũng chiếm không gian. `DBMS_SPACE.SPACE_USAGE` cần quyền và cách gọi phù hợp với loại segment; không mặc định tài khoản ứng dụng được phép truy vấn tất cả segment của database.

### 3.3. `PCTFREE` vẫn quan trọng trong ASSM

`PCTFREE` xác định mức không gian trên data block dành lại để hỗ trợ các thao tác **cập nhật hàng đã có** (nhất là khi dữ liệu hàng tăng độ dài). Ví dụ:

```sql
CREATE TABLE lab_customer (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(200 CHAR),
    address     VARCHAR2(500 CHAR)
)
PCTFREE 20;
```

Với `PCTFREE 20`, Oracle hướng tới việc để lại một phần dung lượng block nhằm có chỗ cho các update, dù giá trị không nên diễn giải như cam kết 20% số byte luôn không dùng cho mọi thời điểm. Nếu `address` thường từ `NULL` trở thành chuỗi dài, có thể cần chừa thêm chỗ để hạn chế row migration; ngược lại, giá trị quá cao có thể làm tăng số block cần đọc.

**`PCTUSED` khác `PCTFREE`.** Trong MSSM, `PCTUSED` quyết định thời điểm block sau delete/update quay lại khả dụng cho insert thông qua freelist. Trong ASSM, Oracle sử dụng bitmap để xác định mức trống nên `PCTUSED` không còn là nút điều chỉnh tương ứng. Khi tinh chỉnh, phải quan sát dữ liệu và workload thay vì sao chép cấu hình freelist từ tài liệu Oracle đời cũ.

## 4. LMT và ASSM phối hợp như thế nào khi insert dữ liệu?

Giả sử ứng dụng thực hiện `INSERT` vào bảng `ORDERS` trong tablespace có `EXTENT MANAGEMENT LOCAL AUTOALLOCATE` và `SEGMENT SPACE MANAGEMENT AUTO`.

1. Oracle cần tìm một block của segment bảng còn đủ chỗ để ghi dòng; **ASSM** hỗ trợ tìm block bằng bitmap mức độ đầy/trống.
2. Nếu cần thêm block mà segment đang có thể sử dụng từ extent đã cấp, Oracle dùng không gian đó và cập nhật metadata tương ứng.
3. Nếu segment cần mở rộng bằng extent mới, **LMT** tìm và cấp phát extent trống trong tablespace; với `AUTOALLOCATE`, Oracle quyết định cỡ extent theo chính sách của nó.
4. ASSM tiếp tục quản lý các block được đưa vào sử dụng trong segment để hỗ trợ các lần insert tiếp theo.
5. Nếu tablespace không đủ extent hợp lệ, datafile không thể mở rộng hoặc có giới hạn/quota khác, thao tác có thể thất bại dù ASSM vẫn hoạt động bình thường.

```text
INSERT dữ liệu
      |
      v
ASSM: segment còn block phù hợp? -- Có --> ghi vào block, cập nhật bitmap
      |
     Không
      v
Segment còn block chưa dùng trong extent? -- Có --> đưa block vào sử dụng
      |
     Không
      v
LMT: cấp thêm extent từ tablespace -- Thành công --> ASSM quản lý block mới
      |
     Không
      v
Kiểm tra tablespace/datafile/quota/giới hạn -> có thể phát sinh ORA thiếu space
```

Sơ đồ nhằm giải thích cấp trách nhiệm, không mô tả từng bước nội bộ của optimizer hoặc buffer manager. Ngoài data segment, Oracle còn có index/LOB/undo/temporary segment với đặc điểm và chính sách riêng.

## 5. Không nhầm `AUTOALLOCATE`, `AUTOEXTEND`, ASSM và Oracle ASM

Tên các cơ chế gần giống nhau nhưng công việc hoàn toàn khác:

| Cơ chế | Cấp quản lý | Ý nghĩa |
|---|---|---|
| `EXTENT MANAGEMENT LOCAL` | Tablespace | Theo dõi trạng thái extent bằng bitmap cục bộ của tablespace |
| `AUTOALLOCATE` | Extent | Oracle chọn kích thước extent khi segment cần tăng không gian |
| `UNIFORM SIZE` | Extent | Chọn kích thước extent cố định trong tablespace |
| `SEGMENT SPACE MANAGEMENT AUTO` (ASSM) | Segment/block | Oracle dùng bitmap để quản lý block còn chỗ ghi |
| `AUTOEXTEND ON` | Datafile | Cho phép file tăng kích thước theo bước, trong giới hạn được cấu hình và dung lượng thực tế |
| **ASM – Automatic Storage Management** | Lưu trữ vật lý | Oracle quản lý disk group và phân bố file database trên hạ tầng lưu trữ; **không phải ASSM** |
| Automatic Undo Management | Undo | Quản lý undo theo chế độ tự động; không phải cơ chế tìm block của user table |

Ví dụ, một datafile có `AUTOEXTEND OFF` vẫn có thể phục vụ nhiều lần insert nếu còn extents trống. Ngược lại, file có `AUTOEXTEND ON` không bảo đảm mở rộng vô hạn: `MAXSIZE`, khả năng lưu trữ thực, quota của user hoặc các hạn chế khác vẫn có thể chặn quá trình cấp phát.

LMT được gọi là “locally managed” vì **metadata extent nằm trong tablespace**; từ “local” không có nghĩa database phải chạy trên ổ đĩa gắn trực tiếp hoặc không được dùng SAN, NFS hay Oracle ASM.

## 6. Tạo tablespace LMT kết hợp ASSM

Các ví dụ dưới đây dành cho **môi trường lab DEV/TEST** và người đã được DBA cấp quyền phù hợp. Tạo tablespace có thể yêu cầu quyền `CREATE TABLESPACE`, không gian hạ tầng, quyền truy cập thư mục hoặc cấu hình Oracle Managed Files (OMF). Không thực thi trên production chỉ để làm bài thực hành.

### 6.1. Ví dụ `AUTOALLOCATE` + ASSM

```sql
-- Ví dụ dành cho Oracle database/PDB lab có đường dẫn datafile hợp lệ.
CREATE TABLESPACE lmt_assm_lab
DATAFILE '/u02/oradata/DEV_PDB/lmt_assm_lab01.dbf' SIZE 256M
    AUTOEXTEND ON NEXT 64M MAXSIZE 2G
EXTENT MANAGEMENT LOCAL AUTOALLOCATE
SEGMENT SPACE MANAGEMENT AUTO;
```

Đọc từng phần:

- `CREATE TABLESPACE lmt_assm_lab`: tạo tablespace lưu dữ liệu ứng dụng.
- `DATAFILE ... SIZE 256M`: cấp một datafile ban đầu 256 MB. Đường dẫn trên là **đường dẫn giả định**, phải thay bằng đường dẫn thực do DBA quản lý.
- `AUTOEXTEND ON NEXT 64M MAXSIZE 2G`: cho phép datafile tăng từng bước 64 MB khi cần, tối đa đến giới hạn cấu hình; vẫn phụ thuộc vào hạ tầng.
- `EXTENT MANAGEMENT LOCAL AUTOALLOCATE`: LMT quản lý extent bằng bitmap, Oracle chọn kích thước extent.
- `SEGMENT SPACE MANAGEMENT AUTO`: ASSM quản lý không gian block trong segment.

Nếu database sử dụng **Oracle Managed Files**, DBA có thể chọn cú pháp không nêu đường dẫn cụ thể khi các tham số đích tạo file đã được thiết lập; nếu dùng **Oracle ASM**, đường dẫn file có thể thuộc disk group. Chọn cách tạo file theo cấu hình Oracle đang chạy, không sao chép nguyên đường dẫn từ ví dụ.

### 6.2. Ví dụ `UNIFORM` + ASSM

```sql
CREATE TABLESPACE lmt_uniform_lab
DATAFILE '/u02/oradata/DEV_PDB/lmt_uniform_lab01.dbf' SIZE 256M
    AUTOEXTEND OFF
EXTENT MANAGEMENT LOCAL UNIFORM SIZE 1M
SEGMENT SPACE MANAGEMENT AUTO;
```

Ở đây, tất cả extent cấp phát trong tablespace sử dụng cỡ 1 MB, trong khi ASSM vẫn tự tìm block có chỗ ghi. `AUTOEXTEND OFF` nghĩa là datafile không tự tăng; nó **không vô hiệu hóa ASSM** và cũng không ngăn Oracle phân thêm extent từ không gian trống còn lại trong file.

### 6.3. Cấp quota cho schema được phép thực hành

Một user cần quyền tạo đối tượng phù hợp và quota trên tablespace để lưu segment. Ví dụ dành cho DBA hoặc người quản trị có quyền:

```sql
ALTER USER lab_app QUOTA 128M ON lmt_assm_lab;
```

Quyền `CREATE TABLE` hoặc các quyền tạo object khác cần được cấp theo mục đích. Quota khác với phần không gian trống của tablespace: một tablespace vẫn có dung lượng nhưng user có thể hết quota. Không cấp `UNLIMITED TABLESPACE` hoặc quyền quản trị cao cho tài khoản ứng dụng chỉ để bài lab chạy được.

**Bối cảnh multitenant:** ở kiến trúc CDB/PDB, cần tạo và quan sát tablespace trong **đúng PDB**. Kiểm tra `CON_NAME`/service của session trước khi chạy DDL; việc đăng nhập nhầm CDB root hay PDB khác có thể khiến thao tác không đúng phạm vi.

## 7. Kiểm tra một tablespace đang dùng LMT và ASSM hay không

DBA hoặc người có quyền truy vấn dictionary thích hợp có thể dùng view `DBA_TABLESPACES`:

```sql
SELECT
    tablespace_name,
    contents,
    extent_management,
    allocation_type,
    segment_space_management
FROM dba_tablespaces
WHERE tablespace_name IN ('LMT_ASSM_LAB', 'LMT_UNIFORM_LAB');
```

Các cột cần hiểu:

| Cột | Ý nghĩa khi đọc |
|---|---|
| `EXTENT_MANAGEMENT` | Giá trị `LOCAL` cho biết tablespace dùng quản lý extent kiểu LMT |
| `ALLOCATION_TYPE` | Cho biết chiến lược cấp phát extent, ví dụ `SYSTEM` cho cấp phát tự động hoặc `UNIFORM` cho cỡ cố định |
| `SEGMENT_SPACE_MANAGEMENT` | Giá trị `AUTO` cho biết ASSM; với một số loại tablespace cơ chế này không có cùng ý nghĩa như permanent tablespace thông thường |
| `CONTENTS` | Nhận biết tablespace `PERMANENT`, `TEMPORARY` hoặc loại khác trước khi diễn giải các tham số |

Đừng suy luận chỉ từ tên `LMT_ASSM_LAB`: tên là do con người đặt, còn **giá trị dictionary phản ánh cấu hình thực tế**. Các view `DBA_*` không mặc định mở cho user ứng dụng. Nếu tài khoản không có quyền, yêu cầu DBA cung cấp kết quả; không cấp quyền `DBA` để chạy một truy vấn kiểm tra.

### 7.1. Quan sát datafile và khả năng mở rộng

```sql
SELECT
    tablespace_name,
    file_name,
    bytes / 1024 / 1024 AS allocated_mb,
    autoextensible,
    maxbytes / 1024 / 1024 AS max_mb
FROM dba_data_files
WHERE tablespace_name = 'LMT_ASSM_LAB';
```

`BYTES` là kích thước datafile hiện tại; `MAXBYTES` liên quan giới hạn mở rộng cấu hình, không bảo đảm storage thực sự có sẵn đến con số đó. Để giám sát sức chứa cần đối chiếu nhiều nguồn: dung lượng còn trống trong tablespace, tăng trưởng segment, cấu hình datafile và năng lực lưu trữ hệ điều hành/ASM.

### 7.2. Phân biệt dung lượng đã cấp phát cho segment với free extent

```sql
-- Extent còn trống trong tablespace (mức tablespace).
SELECT tablespace_name,
       SUM(bytes) / 1024 / 1024 AS free_extent_mb
FROM dba_free_space
WHERE tablespace_name = 'LMT_ASSM_LAB'
GROUP BY tablespace_name;

-- Dung lượng và số extent đã cấp cho từng segment (mức segment).
SELECT owner, segment_name, segment_type,
       extents, bytes / 1024 / 1024 AS allocated_mb
FROM dba_segments
WHERE tablespace_name = 'LMT_ASSM_LAB'
ORDER BY bytes DESC;
```

**`DBA_FREE_SPACE` phản ánh extent chưa cấp phát trong tablespace**, không phải tổng số byte chưa dùng bên trong từng block của mọi bảng. Ngược lại, `DBA_SEGMENTS.BYTES` là dung lượng đã cấp phát cho segment, **không bằng kích thước dữ liệu hữu ích của tất cả dòng**. Một bảng có nhiều dòng bị delete vẫn có thể giữ các extent đã cấp.

Với người dùng schema thông thường, `USER_SEGMENTS` và `USER_EXTENTS` giúp xem segment/extent mình sở hữu nếu có quyền truy cập object tương ứng; ví dụ:

```sql
SELECT segment_name, segment_type, tablespace_name,
       extents, bytes / 1024 / 1024 AS allocated_mb
FROM user_segments
WHERE tablespace_name = 'LMT_ASSM_LAB';
```

Không có dòng trong `DBA_FREE_SPACE` cho tablespace không đồng nghĩa query bị lỗi; cần xác minh tổng thể, bao gồm khả năng không còn free extent để liệt kê, quyền xem hoặc trạng thái file liên quan.

## 8. Bài thực hành: quan sát cấp phát extent khi bảng phát triển

Bài lab sau minh họa cách **LMT và ASSM cùng vận hành**. Giả định tài khoản `LAB_APP` đã được cấp quyền tạo table và quota trên `LMT_ASSM_LAB`; người chạy đang kết nối vào đúng PDB DEV/TEST.

### Bước 1 – Kiểm tra môi trường trước khi ghi dữ liệu

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

Xác nhận các giá trị khớp môi trường lab đã được cấp. Mọi dữ liệu trong các bước tiếp theo đều là dữ liệu tổng hợp.

### Bước 2 – Tạo bảng trong tablespace ASSM

```sql
CREATE TABLE lab_orders_space (
    order_id NUMBER PRIMARY KEY,
    status   VARCHAR2(20 CHAR) NOT NULL,
    payload  VARCHAR2(400 CHAR)
)
TABLESPACE lmt_assm_lab
PCTFREE 15;
```

Primary key có thể tạo một segment index riêng; để tránh nhầm khi đo dung lượng, hãy quan sát rõ `SEGMENT_TYPE` của từng đối tượng. Ở cấu hình cho phép *deferred segment creation*, bảng vừa tạo có thể chưa xuất hiện trong `USER_SEGMENTS` cho tới khi có dữ liệu.

### Bước 3 – Chèn dữ liệu tổng hợp có kiểm soát

```sql
INSERT INTO lab_orders_space (order_id, status, payload)
SELECT LEVEL,
       'NEW',
       RPAD('LAB', 300, 'x')
FROM dual
CONNECT BY LEVEL <= 5000;

COMMIT;

SELECT COUNT(*) AS total_rows
FROM lab_orders_space;
```

Lệnh trên dùng cú pháp Oracle `CONNECT BY LEVEL` để tạo 5.000 dòng giả. Dung lượng thực tế và số extent khác nhau theo block size, metadata, edition/phiên bản, chính sách cấp phát và trạng thái tablespace. Không nên ấn định trước số extent như một đáp án bất biến.

### Bước 4 – Xem segment và extent sau khi insert

```sql
SELECT segment_name, segment_type, extents,
       bytes / 1024 AS allocated_kb
FROM user_segments
WHERE segment_name = 'LAB_ORDERS_SPACE';

SELECT extent_id, file_id, block_id,
       blocks, bytes / 1024 AS extent_kb
FROM user_extents
WHERE segment_name = 'LAB_ORDERS_SPACE'
ORDER BY extent_id;
```

Kết quả `USER_SEGMENTS` cho biết segment đã được cấp phát bao nhiêu extent/byte; `USER_EXTENTS` cho thấy từng extent. Với `AUTOALLOCATE`, số block mỗi extent **có thể khác nhau**. Nếu thử một bảng tương tự trong tablespace `UNIFORM SIZE 1M`, các extent của nó có kích thước cố định theo chính sách tablespace.

### Bước 5 – Xóa dữ liệu rồi quan sát lại

```sql
DELETE FROM lab_orders_space
WHERE MOD(order_id, 2) = 0;

COMMIT;

SELECT COUNT(*) AS remaining_rows
FROM lab_orders_space;

SELECT segment_name, extents, bytes / 1024 AS allocated_kb
FROM user_segments
WHERE segment_name = 'LAB_ORDERS_SPACE';
```

Số dòng giảm, nhưng **`USER_SEGMENTS.BYTES` thường không giảm tương ứng**. `DELETE` giải phóng không gian cho việc sử dụng lại **bên trong segment** theo quy tắc quản lý block, chứ không mặc nhiên trả toàn bộ extent về tablespace hoặc thu nhỏ datafile. ASSM cập nhật thông tin block có thể nhận thêm dữ liệu; LMT vẫn xem các extent đang thuộc segment đó.

### Bước 6 – Thảo luận và thu dọn trong lab

Hãy thử insert thêm các dòng có key mới rồi quan sát `USER_SEGMENTS`: Oracle có thể tái sử dụng không gian trong các block hiện có trước khi cần cấp thêm extent, tùy kích thước dòng và trạng thái block.

Chỉ sau khi xác nhận đây là bảng do mình tạo trong **DEV/TEST**, mới thu dọn nếu được phép:

```sql
DROP TABLE lab_orders_space PURGE;
```

`DROP TABLE ... PURGE` loại bỏ đối tượng mà không đưa vào recycle bin; đây là thao tác phá hủy dữ liệu lab và là DDL thường có implicit commit. Không áp dụng lên dữ liệu thật hoặc dùng bảng có tên tương tự ở production. Nếu tổ chức yêu cầu giữ dữ liệu thực hành, bỏ bước thu dọn.

## 9. Vì sao xóa nhiều dòng nhưng tablespace vẫn “đầy”?

Một nhầm lẫn phổ biến là: “Đã `DELETE` 80% số dòng, vậy phải trả lại 80% dung lượng cho tablespace”. Thực tế có **ít nhất ba mức dung lượng**:

1. **Dung lượng đã dùng của datafile trên storage:** file đã tăng kích thước sẽ không tự co lại chỉ vì nhiều dòng bị xóa.
2. **Extent đã cấp cho segment:** Oracle giữ extent trong segment cho tới khi có thao tác/điều kiện giải phóng phù hợp; `DBA_SEGMENTS.BYTES` thể hiện dung lượng cấp phát này.
3. **Không gian trong các block đã cấp:** ASSM có thể quản lý khoảng trống bên trong block để các insert/update tiếp theo sử dụng lại.

```text
DATAFILE đã cấp phát 1024 MB
  |
  +-- 800 MB extents đã thuộc nhiều segment
  |      |
  |      +-- Dòng dữ liệu hiện tại và block metadata
  |      +-- Khoảng trống trong block do DELETE/UPDATE
  |          (ASSM quản lý, chưa phải extent FREE của tablespace)
  |
  +-- 224 MB extents chưa cấp cho segment
         (LMT có thể cấp phát khi cần)
```

Các con số chỉ để minh họa, không tính mọi overhead. LMT và ASSM **không phải công cụ tự động nén, xóa bản ghi cũ, trả mọi extent về tablespace hoặc giảm kích thước file vật lý**.

### 9.1. High Water Mark và truy vấn full table scan

**High Water Mark (HWM)** là ranh giới gắn với mức block đã sử dụng trong segment. Khi nhiều dòng bị xóa, HWM có thể không giảm, nên một số kiểu quét bảng vẫn phải xét các block dưới HWM dù hiện còn ít dòng. ASSM biết block nào còn chỗ cho insert, nhưng việc đó không đồng nghĩa HWM tự hạ hoặc full scan luôn đọc ít hơn.

Nếu cần thu hồi hoặc sắp xếp lại không gian, DBA/developer có thể đánh giá các kỹ thuật như **segment shrink**, `MOVE`, tái xây dựng object hoặc chính sách partition/data retention. Ví dụ, với loại heap table được hỗ trợ, trong ASSM và khi thỏa điều kiện thao tác:

```sql
-- Chỉ là ví dụ thao tác bảo trì cho bảng được phép.
ALTER TABLE lab_orders_space ENABLE ROW MOVEMENT;
ALTER TABLE lab_orders_space SHRINK SPACE;
```

Không phải mọi bảng/LOB/index đều được shrink theo cùng cách; thao tác có giới hạn và hệ quả với rowid, index, khóa, ứng dụng phụ thuộc rowid, tải và khả năng thực hiện online. Trước khi áp dụng production, phải xem tài liệu phù hợp với phiên bản Oracle, kiểm thử, lập kế hoạch và theo dõi sau thay đổi. **Không mặc định shrink sẽ giảm kích thước datafile ở hệ điều hành**.

### 9.2. Điều gì quyết định một row có thể nằm trong block hiện tại?

Ngoài bitmap ASSM, Oracle còn xét kích thước dòng, phần metadata/transaction trong block, `PCTFREE`, kiểu dữ liệu, cập nhật tăng chiều dài, block size và tình trạng khác. Một update làm hàng lớn hơn có thể dẫn tới **row migration** nếu block hiện tại không còn đủ chỗ; hiện tượng này có thể tăng I/O ở những truy vấn truy cập qua ROWID/index. ASSM giúp chọn block nhưng không loại bỏ hoàn toàn row migration hay mọi dạng phân mảnh dữ liệu.

## 10. Các lỗi không gian Oracle và cách phân loại

Nhóm lỗi liên quan tablespace/segment thường xuất hiện khi ứng dụng ghi dữ liệu hoặc khi chạy DDL. Đọc mã lỗi cùng tên segment/tablespace trong thông điệp để phân công xử lý:

| Mã lỗi ví dụ | Ý nghĩa định hướng | Kiểm tra phù hợp |
|---|---|---|
| `ORA-01653` | Không mở rộng được table segment bằng extent cần thiết | Free extent, datafile/maxsize, quota, tăng trưởng bảng |
| `ORA-01654` | Không mở rộng được index segment | Tablespace chứa index, dung lượng và workload index |
| `ORA-01652` | Không mở rộng được temporary segment | Temporary tablespace, temp usage, SQL/sort/hash workload |
| `ORA-01536` | Vượt tablespace quota được cấp cho user | Quota của schema, việc cấp phát object và chính sách quyền |
| `ORA-01658` | Không tạo được initial extent cho segment tại tablespace | Free extent hợp lệ và kích thước extent/giới hạn file |

`ORA-01653` **không mặc định đồng nghĩa ổ đĩa đã đầy**. Có thể tablespace không có đủ khoảng trống cấp extent, datafile đã chạm `MAXSIZE`, autoextend bị tắt, storage cấp dưới không còn sức chứa hoặc user đang bị giới hạn. Với `UNIFORM SIZE`, cần đủ không gian cho đơn vị extent được chọn; với `AUTOALLOCATE`, kích thước extent tiếp theo phụ thuộc chính sách Oracle.

### Tình huống A – Tablespace LMT + ASSM nhưng insert báo `ORA-01653`

1. **Developer** xác định table/index nào tăng nhanh, SQL nào tạo tải, migration hoặc batch job vừa chạy, số dòng và nhu cầu dung lượng dự kiến.
2. **DBA** kiểm tra `DBA_SEGMENTS`, `DBA_FREE_SPACE`, datafile/autoextend, quota, trạng thái PDB và khả năng cấp extent mới.
3. **Operations** kiểm tra storage/disk group, cảnh báo, tăng trưởng và khả năng thêm năng lực hạ tầng theo quy trình.
4. Nhóm chọn giải pháp dựa trên bằng chứng: thêm file/tăng giới hạn được phê duyệt, điều chỉnh quota phù hợp, xử lý dữ liệu theo chính sách hoặc sửa ứng dụng tạo dữ liệu bất thường.

Việc bật ASSM không cấp thêm dung lượng. `AUTOEXTEND ON` cũng không bảo đảm disk luôn còn chỗ.

### Tình huống B – Nhiều session INSERT đồng thời vẫn chậm

Một hệ thống chuyển sang LMT + ASSM mà các insert vẫn tăng latency. Cần kiểm tra wait event, contention trên index tăng dần/hot block, khóa giao dịch, redo log, CPU, I/O, số lượng connection, batch size và cách commit. ASSM giảm nhu cầu điều chỉnh freelist trong một số workload, nhưng **không tự giải quyết bottleneck của toàn bộ transaction**.

### Tình huống C – Xóa dữ liệu rồi dung lượng của bảng không giảm

Developer xóa dữ liệu thử nghiệm; `COUNT(*)` giảm, còn `DBA_SEGMENTS.BYTES` gần như không đổi. Đây có thể là hành vi dự kiến: segment vẫn giữ extent để tái sử dụng. Nếu cần giảm footprint, phải cân nhắc HWM, khả năng shrink, index/LOB/partition và chính sách thu hồi; không nên phát hành `DROP`, `TRUNCATE` hoặc `SHRINK` trên production khi chưa đánh giá ảnh hưởng.

## 11. Vận hành LMT và ASSM: chỉ số nào thực sự có ích?

### 11.1. Theo dõi không gian ở từng cấp

| Muốn biết | Nguồn quan sát thường dùng | Cẩn trọng khi diễn giải |
|---|---|---|
| Tablespace có bao nhiêu free extent? | `DBA_FREE_SPACE` | Không tính khoảng trống bên trong block đã thuộc segment |
| Datafile đang lớn bao nhiêu, có autoextend không? | `DBA_DATA_FILES` | `MAXBYTES` là giới hạn cấu hình, không bảo đảm storage còn chỗ |
| Segment đã được cấp bao nhiêu byte, bao nhiêu extent? | `DBA_SEGMENTS`, `USER_SEGMENTS` | Kích thước cấp phát không bằng số byte dữ liệu hữu ích |
| Các extent của một segment lớn cỡ nào? | `DBA_EXTENTS`, `USER_EXTENTS` | Cỡ extent phụ thuộc chiến lược allocation, không phải ASSM |
| Mức độ đầy/trống của block trong segment ASSM? | `DBMS_SPACE.SPACE_USAGE` với quyền và loại segment phù hợp | Cần hiểu dải fullness và các giới hạn của API |
| Dung lượng tổng thể và xu hướng sử dụng? | Metric tablespace/storage, `DBA_TABLESPACE_USAGE_METRICS` và monitoring được triển khai | Phải đối chiếu autoextend, quota, reserved space, loại tablespace và thực tế hạ tầng |

Đặt cảnh báo theo xu hướng tăng trưởng và thời gian còn lại trước khi đạt giới hạn thường hữu ích hơn chỉ nhìn số MB trống ở một thời điểm. Với tablespace phục vụ ứng dụng quan trọng, cần tính thêm backup, khả năng khôi phục, lưu lượng batch và growth khi có release lớn.

### 11.2. Đừng bỏ qua giới hạn của tài khoản và loại tablespace

- **Quota:** schema có thể hết quota dù tablespace còn không gian; xem chính sách cấp quota trước khi tăng quyền.
- **Index và LOB:** bảng có thể nằm trong một tablespace trong khi index/LOB ở tablespace khác; lỗi có thể đến từ segment phụ trợ.
- **Temporary tablespace:** sort/hash và hoạt động tạm sử dụng quản lý temp riêng; đừng áp dụng nguyên văn ý nghĩa ASSM của permanent table data block cho temp.
- **Undo tablespace:** phục vụ MVCC/transaction recovery, có chính sách undo riêng; không nhầm với ASSM của bảng nghiệp vụ.
- **CDB/PDB:** xem đúng container khi tra catalog; cùng tên tablespace ở các PDB có thể là những đối tượng độc lập.
- **Quyền truy cập:** query dictionary hoặc thao tác `ALTER TABLESPACE` cần người có quyền phù hợp; developer cung cấp số liệu nghiệp vụ, DBA chịu trách nhiệm thay đổi lưu trữ theo quy trình.

## 12. Chọn `AUTOALLOCATE` hay `UNIFORM`, và khi nào nghĩ tới ASSM?

Một quyết định hợp lý bắt đầu từ workload, không từ một tên tham số:

**Trường hợp 1 – Nhiều bảng và index có kích thước khác nhau.** LMT `AUTOALLOCATE` thường là lựa chọn đơn giản vì Oracle tự chọn cỡ extent; ASSM giúp quản lý block cho workload ghi phổ biến. Theo dõi số extent/dung lượng thực tế thay vì cố điều chỉnh mọi thông số ngay từ đầu.

**Trường hợp 2 – Workload có yêu cầu đơn vị extent cố định.** Có thể cân nhắc `UNIFORM SIZE` khi cần hành vi cấp phát dự đoán được và hiểu rõ chi phí không gian dành sẵn cho các segment nhỏ. ASSM vẫn dùng bình thường để quản lý block; hai lựa chọn không loại trừ nhau.

**Trường hợp 3 – Ghi đồng thời nhiều session.** ASSM là cơ chế phù hợp trong nhiều hệ thống vì tự quản lý free block; tuy nhiên hiệu năng còn phụ thuộc index, câu SQL, commit, latch/wait và cấu hình hạ tầng. Kiểm chứng bằng benchmark đại diện và AWR/ASH hoặc công cụ chẩn đoán được cấp phép nếu môi trường cho phép.

**Trường hợp 4 – Bảng tăng nhanh hoặc dữ liệu thường bị xóa.** Cần đánh giá quản lý retention/partition, HWM, free extent, growth và chi phí bảo trì. ASSM không thay cho chiến lược vòng đời dữ liệu, và LMT không thu nhỏ file hệ điều hành một cách tự động.

Đối với môi trường Oracle hiện đại, kết hợp **LMT + ASSM** là cấu hình phổ biến cho permanent tablespace ứng dụng. Chỉ chọn cơ chế khác khi có điều kiện kỹ thuật được tài liệu hóa và kiểm chứng trên phiên bản/loại segment đang dùng.

## 13. Các hiểu lầm thường gặp

| Phát biểu sai hoặc thiếu | Cách hiểu chính xác |
|---|---|
| “LMT và ASSM đều dùng bitmap nên là cùng một chức năng.” | LMT quản lý **extent của tablespace**; ASSM quản lý **block còn chỗ bên trong segment**. |
| “Locally managed là chỉ dùng ổ đĩa local.” | “Local” là metadata extent được lưu/quản lý trong tablespace; storage có thể do ASM hoặc nền tảng khác cung cấp. |
| “AUTOALLOCATE tự tăng kích thước datafile.” | AUTOALLOCATE chọn cỡ extent; AUTOEXTEND quyết định datafile có được phép tăng hay không. |
| “ASSM nghĩa là mọi INSERT đều nhanh và hết tranh chấp.” | ASSM giảm cấu hình freelist thủ công; hot index, transaction, I/O, redo và giới hạn tài nguyên vẫn ảnh hưởng. |
| “Bật ASSM thì không cần quan tâm PCTFREE.” | `PCTFREE` vẫn ảnh hưởng không gian dành cho update và mật độ dòng/block. |
| “PCTUSED phải tinh chỉnh để ASSM tìm block trống.” | ASSM dùng bitmap; cơ chế `PCTUSED`/freelist truyền thống thuộc MSSM. |
| “DELETE 90% dòng là trả lại 90% dung lượng cho tablespace.” | Khoảng trống thường được tái sử dụng trong segment; extent và kích thước datafile chưa chắc giảm. |
| “DBA_FREE_SPACE là tổng số không gian trống trong mọi bảng.” | View này phản ánh extent còn tự do ở cấp tablespace, không cộng toàn bộ byte trống trong các block đã cấp cho segment. |
| “ORA-01653 tức là ASSM lỗi.” | Phải kiểm tra khả năng cấp extent, datafile, quota và hạ tầng, cũng như segment nào đang tăng. |
| “ASM và ASSM là hai cách viết cùng một chức năng.” | ASM là quản lý storage/disk group; ASSM là quản lý block trong segment. |

## 14. Bài tập tự kiểm tra kiến thức

### Câu hỏi 1 – Hai bảng dùng chung tablespace

Trong `APP_DATA`, bảng A dùng 20 extent và bảng B dùng 3 extent. Cơ chế nào ghi nhận extent đã được cấp cho các segment? Nếu B cần thêm một extent, cơ chế nào có vai trò trong việc cấp phát? **Trả lời:** LMT và bitmap quản lý extent của tablespace.

### Câu hỏi 2 – Bảng đã có extent, insert cần một block còn chỗ

Ứng dụng thêm một dòng mới nhưng segment vẫn còn các block có khoảng trống. Cơ chế nào giúp Oracle xác định block phù hợp? **Trả lời:** ASSM; nó quản lý thông tin free space trong block bằng bitmap của segment.

### Câu hỏi 3 – `AUTOEXTEND OFF` nhưng INSERT vẫn thành công

Vì sao datafile không được mở rộng mà bảng vẫn ghi thêm được? **Trả lời:** Tablespace có thể còn extent trống đã nằm trong datafile, hoặc segment còn block có thể sử dụng trong các extent đã cấp. `AUTOEXTEND` chỉ kiểm soát việc tăng **file vật lý**, không trực tiếp kiểm soát mọi insert.

### Câu hỏi 4 – `DELETE` một triệu dòng nhưng `DBA_SEGMENTS.BYTES` không giảm

Có chắc là `DELETE` thất bại? **Trả lời:** Không. Kiểm tra số dòng còn lại, giao dịch đã commit và phạm vi xóa. Extent có thể vẫn thuộc segment; ASSM có thể tái sử dụng block trống mà không trả extent về tablespace.

### Câu hỏi 5 – Chọn các cấu hình cho tablespace ứng dụng

Giả sử có nhiều bảng nhỏ/lớn, lượng ghi đồng thời vừa phải và không có yêu cầu extent cố định. Một điểm khởi đầu có thể là `EXTENT MANAGEMENT LOCAL AUTOALLOCATE` và `SEGMENT SPACE MANAGEMENT AUTO`. Quyết định `AUTOEXTEND`, `MAXSIZE`, quota, backup và cảnh báo dung lượng phải được thiết kế **riêng** theo ngân sách storage và yêu cầu vận hành.

## Kết luận

**LMT quản lý extent ở cấp tablespace; ASSM quản lý không gian trống trong block ở cấp segment.** `AUTOALLOCATE` hoặc `UNIFORM` quyết định cách cấp extent trong LMT; `PCTFREE` vẫn ảnh hưởng tổ chức block khi sử dụng ASSM; `AUTOEXTEND` và Oracle ASM là những lớp chức năng khác. Quan sát đúng cấp thông qua `DBA_TABLESPACES`, `DBA_SEGMENTS`, `DBA_EXTENTS`, `DBA_FREE_SPACE` và chỉ số datafile giúp giải thích tăng trưởng dung lượng, lỗi `ORA-01653`, khả năng tái sử dụng không gian sau `DELETE` và tác động của các thay đổi lưu trữ. Khi vận hành Oracle thật, phải kết hợp cơ chế tự động với theo dõi dung lượng, phân quyền và kế hoạch bảo trì có kiểm soát.
