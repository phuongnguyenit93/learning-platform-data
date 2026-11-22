# Cấu trúc trang dữ liệu, hàng và tham chiếu vị trí vật lý trong PostgreSQL

## 1. Từ một câu SELECT đến vị trí của hàng trên đĩa

Khi thực hiện:

~~~sql
SELECT account_id, owner_name, balance
FROM accounts
WHERE account_id = 42;
~~~

PostgreSQL không tìm “hàng thứ 42” theo một thứ tự cố định trong bảng. Hệ quản trị cần xác định **hàng nào phù hợp với điều kiện và phiên bản nào được phép nhìn thấy**, sau đó đọc thông tin ở những trang lưu trữ tương ứng.

Ở góc độ vật lý, một bảng PostgreSQL thông thường được tổ chức như sau:

~~~text
Database
  └── Relation của bảng accounts
        ├── Main fork (dữ liệu bảng)
        │     ├── Page 0
        │     │     ├── Page header
        │     │     ├── Item pointers (line pointers)
        │     │     ├── Free space
        │     │     └── Heap tuples
        │     ├── Page 1
        │     └── Page 2 ...
        ├── Free Space Map (FSM)
        └── Visibility Map (VM)

Index là relation vật lý riêng, với các page và cấu trúc riêng.
~~~

Các khái niệm cần hiểu:

- **Page/block:** đơn vị lưu trữ và truy cập cơ bản của nhiều cấu trúc PostgreSQL; kích thước thường là **8 KiB** ở bản dựng phổ biến.
- **Heap tuple:** một **phiên bản vật lý của hàng** trong heap table.
- **Item pointer/line pointer:** mục trong mảng đầu trang, chỉ tới vị trí các byte của tuple trong trang.
- **TID (Tuple Identifier):** vị trí vật lý kiểu **(block number, offset number)**; offset xác định một mục trong mảng line pointer của block.
- **CTID:** cột hệ thống có thể đọc bằng SQL để thấy TID của **phiên bản hàng đang được trả về**.
- **MVCC:** cơ chế quản lý nhiều phiên bản hàng để các transaction đọc đúng snapshot.
- **TOAST:** cơ chế lưu các giá trị cột lớn, có thể nén hoặc đưa ra một relation phụ.

Bài học không chỉ giải thích một khối dữ liệu có gì. Mục tiêu quan trọng là hiểu vì sao **CTID không phải khóa định danh nghiệp vụ**, vì sao `UPDATE` có thể tạo một tuple mới, tại sao việc dọn dẹp bằng `VACUUM` là cần thiết và cách quan sát các cơ chế này bằng SQL trên PostgreSQL.

> Phạm vi: PostgreSQL sử dụng **heap table** thông thường, không giả định các access method hoặc extensions lưu trữ tùy biến có cùng định dạng. Những số byte cụ thể phụ thuộc bản dựng và phiên bản; ví dụ mặc định 8 KiB chỉ là trường hợp rất phổ biến.

## 2. Từ đối tượng logic đến tệp vật lý

### 2.1. Table không đồng nghĩa một file duy nhất

Trong SQL, ta gọi:

~~~sql
SELECT * FROM public.accounts;
~~~

Nhưng PostgreSQL quản lý một bảng như một **relation** với định danh và metadata riêng trong system catalogs. Nội dung của relation có thể nằm ở nhiều file/fork và nhiều segment. Chỉ mục, TOAST table và TOAST index cũng là các relation riêng.

Ở cấp hệ thống tệp, tên file không nhất thiết bằng tên bảng. PostgreSQL sử dụng các định danh vật lý như **relfilenode/relfilenumber** và layout riêng theo tablespace, database, fork và segment. Một số thao tác rewrite table có thể đổi file vật lý mà tên SQL của bảng vẫn giữ nguyên.

Có thể quan sát đường dẫn *tương đối bên trong data directory* và định danh relation qua:

~~~sql
SELECT
    'public.accounts'::regclass AS relation_name,
    pg_relation_filenode('public.accounts'::regclass) AS relation_filenode,
    pg_relation_filepath('public.accounts'::regclass) AS relative_path;
~~~

Đây là cú pháp minh họa khi bảng đã tồn tại. Phần thực hành bên dưới sẽ tạo `storage_lab.accounts` rồi chạy lệnh tương đương. Các hàm trên trả **thông tin metadata**, không cần tự mở hoặc sửa file dữ liệu của PostgreSQL.

**Không bao giờ tự sửa, xóa hay copy trực tiếp tệp trong data directory** khi server đang chạy chỉ vì đã tìm được đường dẫn. Các file đó còn gắn với WAL, cache, checkpoint, MVCC và quy trình khôi phục của PostgreSQL.

### 2.2. Những fork thường gặp

Một relation heap có thể sử dụng các fork:

| Fork | Vai trò | Đặc điểm cần nhớ |
|---|---|---|
| **main** | Chứa các trang heap tuple | Đây là phần dữ liệu bảng thường được hình dung khi nói “page của bảng” |
| **fsm** | Free Space Map | Theo dõi gần đúng các trang có không gian trống để hỗ trợ chọn nơi ghi |
| **vm** | Visibility Map | Theo dõi thông tin all-visible và all-frozen ở cấp trang |
| **init** | Initialization fork | Có ở một số relation **UNLOGGED**, phục vụ tái khởi tạo khi crash recovery |

Không phải mọi relation đều có đủ bốn fork ở mọi thời điểm. Một index cũng có tổ chức trang riêng và có thể sử dụng fork khác theo access method và yêu cầu quản lý.

`main` lưu row versions. `fsm` **không chứa bản sao đầy đủ của tuple**, và `vm` **không chứa toàn bộ trạng thái MVCC cho từng hàng**. Chúng là metadata hỗ trợ hiệu năng/bảo trì.

### 2.3. Segment của relation

Khi main fork đủ lớn, PostgreSQL có thể chia file thành nhiều **segment**. Cấu hình phổ biến dùng segment khoảng **1 GiB**, nhưng kích thước thực tế phụ thuộc bản dựng. Trong data directory có thể thấy các phần tương ứng với một filenode như:

~~~text
<relfilenode>
<relfilenode>.1
<relfilenode>.2
...
~~~

Tên ví dụ thể hiện khái niệm segment, không phải địa chỉ file được phép thao tác trực tiếp. Một block logic của relation vẫn được đánh số theo chuỗi trang của relation, không yêu cầu ứng dụng tính vị trí trong từng segment.

## 3. Page/block: đơn vị lưu trữ cơ sở

### 3.1. Page thường có kích thước 8 KiB

Ở bản dựng PostgreSQL thường gặp, một page có **8192 byte**. Kích thước này do tham số biên dịch `BLCKSZ` quyết định, **không phải cấu hình SQL có thể tùy ý thay trong session**.

Xem kích thước block đang sử dụng:

~~~sql
SHOW block_size;

SELECT current_setting('block_size')::integer AS block_size_bytes;
~~~

Giá trị thường là `8192`. Nếu được xây dựng với block size khác, ví dụ 16 KiB, các phép tính số trang phải dùng giá trị thực tế thay vì cố định 8192.

Những trang heap thuộc main fork được nhận diện bằng số block:

~~~text
Block 0 → byte range [0, block_size)
Block 1 → byte range [block_size, 2 × block_size)
Block 2 → byte range [2 × block_size, 3 × block_size)
...
~~~

Đây là cách hình dung địa chỉ logic trong **fork của một relation**, không phải offset tuyệt đối trong thiết bị lưu trữ vật lý.

### 3.2. Bố cục page heap

Bố cục chuẩn của một data page:

~~~text
Đầu trang (byte offset 0)
┌─────────────────────────────────────────────────────────┐
│ PageHeaderData                                          │
│ Thường 24 byte ở layout PostgreSQL phổ biến             │
├─────────────────────────────────────────────────────────┤
│ ItemIdData #1  (line pointer)                           │
│ ItemIdData #2                                          │
│ ItemIdData #3                                          │
│ ...                                                     │
│ Mảng line pointer tăng dần từ đầu trang ↓              │
├─────────────────────────────────────────────────────────┤
│                     VÙNG TRỐNG                         │
│            giữa pd_lower và pd_upper                   │
├─────────────────────────────────────────────────────────┤
│ Tuple mới hơn / tuple cũ ...                           │
│ Dữ liệu tuple thường được bố trí từ cuối trang ↑        │
├─────────────────────────────────────────────────────────┤
│ Special space, nếu access method có dùng               │
│ Heap page thông thường không cần nội dung special      │
└─────────────────────────────────────────────────────────┘
Cuối trang (byte offset block_size)
~~~

Hai hướng tăng giúp PostgreSQL chèn thêm **line pointer ở phía đầu** và thêm **tuple data từ phía cuối**. Khi dữ liệu tuple bị xóa khỏi vùng sống và trang được compact, phần payload có thể di chuyển **bên trong trang** trong khi line pointer vẫn chỉ đúng đến payload sau khi cập nhật vị trí.

Do đó:

**TID offset number là số thứ tự của line pointer, không phải byte offset của tuple.**

Ví dụ `ctid = '(5,3)'` chỉ đến **item pointer số 3 của block số 5**, không có nghĩa dữ liệu tuple bắt đầu tại byte thứ 3 của block.

### 3.3. PageHeaderData chứa gì?

Một số trường đáng chú ý của page header:

| Trường | Ý nghĩa |
|---|---|
| `pd_lsn` | WAL log sequence number liên quan đến thay đổi page đã ghi |
| `pd_checksum` | Checksum của page khi cluster bật data checksums |
| `pd_flags` | Một số cờ trạng thái page |
| `pd_lower` | Ranh giới cuối vùng line pointers |
| `pd_upper` | Ranh giới bắt đầu vùng tuple data |
| `pd_special` | Ranh giới bắt đầu special space |
| `pd_pagesize_version` | Thông tin kích thước/phiên bản layout page |
| `pd_prune_xid` | Thông tin gợi ý cho việc xem xét pruning các tuple |

Ở page heap thông thường, vùng special không mang nội dung như ở nhiều loại index page, nên `pd_special` thường trỏ tới cuối trang. Với B-tree index, special space được dùng cho cấu trúc riêng của access method.

Nhìn ba mốc:

~~~text
          pd_lower              pd_upper          pd_special
              |                     |                   |
[header][line pointers]  FREE SPACE  [tuple data ...]   [special]
~~~

Dung lượng vùng trống liên tục trong layout page có thể hiểu gần đúng là:

~~~text
pd_upper - pd_lower
~~~

Nhưng đừng nhầm chỉ số này với **tổng dung lượng có thể tái sử dụng** được FSM phản ánh; các tuple chết, line pointer có thể tái dùng, thao tác compact và chính sách fillfactor đều ảnh hưởng không gian ghi thực tế.

### 3.4. Checksum và WAL không phải nội dung hàng

`pd_lsn` và `pd_checksum` là metadata hỗ trợ tính đúng đắn/khôi phục của page; chúng không phải trường SQL người dùng định nghĩa.

- **WAL** giúp PostgreSQL khôi phục những thay đổi đã ghi log khi có sự cố theo bảo đảm durability tương ứng.
- **Page checksum** là tính năng tùy cấu hình cluster; một hệ thống không bật checksum sẽ không có cùng cơ chế phát hiện lỗi qua checksum.
- **Hint bits**, visibility state và các hoạt động bảo trì có thể cập nhật page metadata mà không tương ứng trực tiếp với một lệnh `UPDATE` nghiệp vụ.

Cần phân biệt **dữ liệu của hàng** và **metadata quản lý page**.

## 4. Line pointer: chỉ mục nhỏ bên trong mỗi page

Mỗi mục trong mảng item pointer thường được biểu diễn bằng `ItemIdData`; ở layout phổ biến, mỗi mục chiếm **4 byte**.

Về mặt logic, một line pointer ghi nhận:

- Vị trí byte của tuple (khi có payload).
- Độ dài mục dữ liệu.
- Trạng thái của slot.

Các trạng thái thường gặp trong heap page:

| Ký hiệu | Tên | Cách hiểu |
|---|---|---|
| `LP_UNUSED` | Unused | Slot đang không dùng; có thể tái sử dụng |
| `LP_NORMAL` | Normal | Slot thường trỏ đến một tuple payload |
| `LP_REDIRECT` | Redirect | Dùng để chuyển hướng tới item pointer khác, thường liên quan đến HOT/pruning |
| `LP_DEAD` | Dead | Slot được đánh dấu đã chết theo tiến trình xử lý |

Ý nghĩa chi tiết của các trạng thái cần đặt trong **ngữ cảnh heap page**, vì index page có cách tổ chức và bảo trì khác.

### 4.1. Vì sao phải có line pointer thay vì CTID lưu byte offset?

Giả sử một tuple đang nằm ở byte 7900 và line pointer `#3` trỏ tới đó. Khi PostgreSQL compact page, payload có thể chuyển sang byte 7700. Nếu tham chiếu vật lý đến hàng là **byte 7900**, tất cả nơi tham chiếu phải biết payload đã di chuyển. Với cấu trúc gián tiếp:

~~~text
TID = (block 5, line pointer #3)
                          |
                          v
Line pointer #3: tuple byte offset 7900
                          |
                 Page được compact
                          |
                          v
Line pointer #3: tuple byte offset 7700
~~~

TID vẫn là `(5,3)` trong quá trình sắp xếp payload nội bộ, miễn line pointer tương ứng vẫn có ý nghĩa. Đây là một ưu điểm lớn của lớp gián tiếp qua item pointer.

Tuy vậy, slot **không phải ID vĩnh viễn**: sau khi phiên bản cũ không còn cần thiết, PostgreSQL có thể đánh dấu rồi tái sử dụng line pointer trong các lần ghi khác.

### 4.2. Cùng một page có nhiều phiên bản hàng

Một lệnh `UPDATE` của PostgreSQL thông thường tạo **phiên bản tuple mới** theo MVCC thay vì ghi đè toàn bộ tuple cũ tại chỗ như một thao tác thay vài byte. Nếu có đủ không gian và các điều kiện thỏa mãn, phiên bản mới có thể được đặt ngay trên **cùng heap page**.

Khi đó một trang có thể chứa:

~~~text
Page 5
  LP #2 → phiên bản cũ của account_id=42 (có thể đã chết)
  LP #3 → phiên bản mới của account_id=42
  LP #4 → hàng khác
~~~

Tùy tình trạng transaction và snapshot, một `SELECT` thông thường có thể thấy phiên bản phù hợp, nhưng không phải mọi tuple vật lý cùng tồn tại đều là **hàng đang sống và nhìn thấy** ở snapshot đó.

## 5. Heap tuple: một phiên bản vật lý của hàng

### 5.1. Cấu trúc tổng quát

Một heap tuple có thể được hình dung:

~~~text
┌──────────────────────────────────────────────────┐
│ HeapTupleHeaderData                              │
│   transaction IDs, tuple flags, ctid link, ...   │
├──────────────────────────────────────────────────┤
│ Null bitmap và metadata tùy điều kiện            │
├──────────────────────────────────────────────────┤
│ Padding/alignment để đến t_hoff                  │
├──────────────────────────────────────────────────┤
│ Giá trị các cột được lưu theo định dạng nội bộ   │
│   fixed-width / variable-width / TOAST pointer  │
└──────────────────────────────────────────────────┘
~~~

Phần header cố định thường có độ dài tối thiểu khoảng **23 byte** trước những yêu cầu alignment và dữ liệu tùy chọn. Kích thước thực của `t_hoff` có thể lớn hơn, đặc biệt khi có null bitmap. Vì vậy **“một dòng 3 cột integer = 12 byte” là cách tính thiếu phần overhead**.

Những trường thường được nhắc đến:

| Trường nội bộ | Vai trò |
|---|---|
| `t_xmin` | Transaction ID tạo phiên bản tuple, theo cơ chế MVCC |
| `t_xmax` | Transaction ID hoặc thông tin liên quan đến xóa/cập nhật/khóa phiên bản |
| `t_cid` / metadata liên quan | Thông tin command ID nội bộ tùy trạng thái tuple |
| `t_ctid` | ItemPointer liên kết phiên bản hiện tại hoặc phiên bản kế tiếp khi cập nhật |
| `t_infomask`, `t_infomask2` | Các bit trạng thái MVCC, khóa và đặc tính tuple |
| `t_hoff` | Offset bắt đầu vùng dữ liệu thuộc tính |
| `t_bits` | Null bitmap khi tuple chứa trường NULL |

Không phải mọi tuple đều dùng tất cả trường theo cùng ý nghĩa trực quan. Đặc biệt `t_xmax` **khác 0 không nhất thiết có nghĩa hàng đã bị xóa**: nó còn có thể mã hóa thông tin liên quan đến khóa hoặc một giao dịch không commit. PostgreSQL dùng flags, trạng thái transaction và snapshot để quyết định tính hiển thị.

### 5.2. Cột SQL NULL không phải chuỗi rỗng

Khi một cột có `NULL`, tuple có thể biểu diễn thông tin thiếu qua **null bitmap**, không cần lưu giá trị dữ liệu bình thường cho thuộc tính ấy. Cách lưu các cột tiếp theo còn chịu quy tắc alignment và định dạng kiểu.

- `NULL` là vắng giá trị SQL.
- `''` là một giá trị text độ dài 0.
- `0` là số nguyên/giá trị số bằng không.

Ba trường hợp có ngữ nghĩa khác nhau và có thể có footprint vật lý khác nhau.

### 5.3. Kiểu cố định, kiểu biến độ dài và alignment

Một tuple có thể chứa:

- `smallint`, `integer`, `bigint`, `boolean` và các kiểu có biểu diễn cố định.
- `text`, `varchar`, `bytea`, `jsonb` hoặc các kiểu có độ dài thay đổi.
- `numeric` có biểu diễn nội bộ biến độ dài theo giá trị/precision.
- Pointer tới dữ liệu TOAST khi thuộc tính lớn được lưu bên ngoài.

PostgreSQL cần alignment cho một số kiểu, nên thứ tự cột và cấu trúc tuple có thể ảnh hưởng lượng padding. Nhưng **không nên tự reorder cột trong schema sản xuất chỉ từ một phép tính thủ công**, vì thay đổi schema có chi phí và ứng dụng có thể phụ thuộc cấu trúc hiện hành.

Quan sát footprint ở mức SQL bằng:

~~~sql
SELECT
    account_id,
    pg_column_size(owner_name) AS owner_name_bytes,
    pg_column_size(balance) AS balance_bytes
FROM storage_lab.accounts
ORDER BY account_id;
~~~

`pg_column_size(value)` cho biết kích thước được biểu diễn/lưu trữ đối với giá trị theo ngữ nghĩa của hàm; nó không thay thế đo kích thước tổng heap tuple, page header, line pointers và các relation TOAST. Không cộng tùy ý vài cột rồi kết luận kích thước trên đĩa chính xác.

## 6. TID và CTID: địa chỉ logic của tuple trong heap

### 6.1. Cú pháp hiển thị

Trong PostgreSQL, `ctid` là một **system column** có thể được chọn cùng các cột bình thường:

~~~sql
SELECT ctid, account_id, owner_name
FROM storage_lab.accounts
ORDER BY account_id;
~~~

Ví dụ hình thức kết quả (các giá trị **không được đảm bảo giống trên máy bạn**):

~~~text
 ctid   | account_id | owner_name
--------+------------+-----------
 (0,1)  |          1 | Nguyen An
 (0,2)  |          2 | Tran Binh
 (0,3)  |          3 | Le Chi
~~~

`(0,2)` nghĩa là:

- `0`: **block number**, thường đếm từ 0 trong main fork của relation.
- `2`: **offset number/item pointer number** bên trong page, bắt đầu từ 1.

Không suy luận `account_id = 2` thì CTID phải là `(0,2)`. Đây chỉ là sự trùng hợp thuận tiện trong một ví dụ chèn liên tiếp vào bảng nhỏ.

### 6.2. CTID không đại diện cho “hàng thứ N”

Một bảng không có thứ tự dòng được SQL đảm bảo nếu không dùng `ORDER BY`. CTID là vị trí vật lý của phiên bản tuple; `ORDER BY ctid` chỉ sắp theo vị trí vật lý, **không đồng nghĩa thứ tự nghiệp vụ, thời gian tạo hoặc primary key**.

~~~sql
SELECT account_id, owner_name, ctid
FROM storage_lab.accounts
ORDER BY ctid;
~~~

Câu này có thể có ích để **khảo sát nội bộ**, nhưng không nên sử dụng để đưa người dùng đến “trang 3 của danh sách theo ngày” hoặc đảm bảo thứ tự ổn định lâu dài.

### 6.3. CTID và TID khác gì?

- **TID** là khái niệm/kiểu địa chỉ tuple dạng (block, offset), được index hoặc executor dùng để tham chiếu tới heap tuple.
- **`ctid`** là một cột hệ thống biểu diễn vị trí của phiên bản tuple đang trả về; giá trị có kiểu `tid` trong PostgreSQL.
- **`t_ctid`** là một trường **bên trong header tuple**, có thể tạo liên kết tới phiên bản kế tiếp khi `UPDATE`.

Ba từ liên quan nhưng **không hoàn toàn là cùng một trường**. Đặc biệt, đọc `ctid` qua câu `SELECT` không đồng nghĩa trực tiếp đọc nguyên bit pattern của `t_ctid` trong một tuple cũ bất kỳ.

### 6.4. Vì sao không nên dùng CTID như primary key?

CTID có thể thay đổi khi:

1. Một hàng được `UPDATE`: PostgreSQL tạo phiên bản mới, thường có vị trí tuple mới.
2. Một thao tác **rewrite table** như `VACUUM FULL` hoặc `CLUSTER` sắp xếp/ghi lại dữ liệu.
3. Một số thao tác biến đổi/di chuyển dữ liệu hoặc tạo lại relation diễn ra.
4. Vị trí của các tuple đã chết được dọn và slot có thể **được tái sử dụng** về sau.

Vì vậy:

~~~sql
-- KHÔNG nên lưu CTID làm định danh lâu dài của khách hàng.
SELECT ctid FROM storage_lab.accounts WHERE account_id = 1;
~~~

Nếu một service lưu `'(0,1)'` vào bảng khác rồi dùng nó ở tuần sau để truy cập “khách hàng 1”, nó có thể không còn trỏ tới phiên bản mong đợi.

Ngược lại:

~~~sql
SELECT *
FROM storage_lab.accounts
WHERE account_id = 1;
~~~

Khóa chính `account_id` là **định danh logic ổn định theo chính sách dữ liệu**, độc lập với vị trí heap. Một tuple có thể chuyển chỗ hoặc được thay bằng phiên bản mới mà business ID vẫn giữ nguyên.

### 6.5. CTID hữu ích trong phạm vi nào?

CTID có thể hữu ích khi:

- Gỡ lỗi hoặc tìm hiểu cấu trúc heap.
- Quan sát một thao tác `UPDATE` có sinh vị trí tuple mới hay không.
- Phân tích kế hoạch truy cập dùng `Tid Scan`/`Tid Range Scan` trong những trường hợp PostgreSQL hỗ trợ.
- Nhận diện tạm thời một phiên bản trong **một giao dịch hoặc một bước bảo trì được kiểm soát**, với nhận thức rõ rằng concurrent updates/rewrite có thể làm tham chiếu mất hiệu lực.

Ví dụ câu truy vấn đặc biệt:

~~~sql
SELECT ctid, account_id, owner_name
FROM storage_lab.accounts
WHERE ctid = '(0,1)'::tid;
~~~

Nó chỉ hữu ích nếu **biết chắc** địa chỉ đó tương ứng tuple nào trong phiên bản relation hiện tại. Không hardcode một CTID giả định trong ứng dụng nghiệp vụ.

## 7. Thí nghiệm: quan sát CTID trước và sau UPDATE

### 7.1. Chuẩn bị schema lab

Chỉ thực hiện trong database thực hành, không dùng database production:

~~~sql
CREATE SCHEMA IF NOT EXISTS storage_lab;

CREATE TABLE storage_lab.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_name TEXT NOT NULL,
    balance NUMERIC(12,2) NOT NULL CHECK (balance >= 0),
    note TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
) WITH (fillfactor = 85);

INSERT INTO storage_lab.accounts (owner_name, balance, note)
VALUES
    ('Nguyen An', 1000000.00, 'Khach hang ca nhan'),
    ('Tran Binh', 1500000.00, 'Khach hang doanh nghiep'),
    ('Le Chi',    2500000.00, 'Khach hang uu tien')
RETURNING account_id, ctid, owner_name, balance;
~~~

`fillfactor = 85` cho biết tỷ lệ lấp đầy mục tiêu khi chèn/sắp xếp ở những tình huống được PostgreSQL áp dụng, để dành thêm không gian phục vụ các `UPDATE` trên cùng page. Nó **không bảo đảm** mọi trang luôn đúng 85% hoặc mọi `UPDATE` là HOT.

Không viết tên bảng chưa tạo ở trên vào một database khác: schema `storage_lab` được dùng để cô lập ví dụ.

### 7.2. Ghi lại CTID ban đầu

~~~sql
SELECT
    account_id,
    ctid,
    owner_name,
    balance,
    updated_at
FROM storage_lab.accounts
ORDER BY account_id;
~~~

Hãy **ghi lại CTID thực tế** từ môi trường của bạn. Dữ liệu nhỏ thường cùng block, nhưng không được coi đó là quy tắc bắt buộc.

### 7.3. Cập nhật trong một transaction và quan sát ngay

~~~sql
BEGIN;

SELECT account_id, ctid, balance
FROM storage_lab.accounts
WHERE account_id = 1;

UPDATE storage_lab.accounts
SET balance = balance + 100000.00,
    updated_at = clock_timestamp()
WHERE account_id = 1
RETURNING account_id, ctid, balance;

SELECT account_id, ctid, balance
FROM storage_lab.accounts
WHERE account_id = 1;

ROLLBACK;
~~~

Điều cần quan sát:

- `UPDATE ... RETURNING ctid` trả **vị trí phiên bản mới**.
- Phiên bản mới có cùng `account_id` nhưng **khác CTID** của phiên bản đang hiện hữu trước khi cập nhật.
- Sau `ROLLBACK`, phiên bản cập nhật không được commit; dữ liệu mà các transaction khác nhìn thấy không trở thành mức tăng vừa thử.
- Việc các vị trí cùng block hay khác block phụ thuộc không gian trang và các điều kiện của PostgreSQL.

Bạn có thể chạy lại:

~~~sql
SELECT account_id, ctid, balance
FROM storage_lab.accounts
WHERE account_id = 1;
~~~

Nó sẽ hiển thị dữ liệu có hiệu lực sau rollback. **CTID không được quy định phải bằng một số cụ thể** giữa các lần thử của những môi trường khác nhau.

### 7.4. Khi COMMIT một UPDATE

Nếu chạy:

~~~sql
UPDATE storage_lab.accounts
SET note = 'Da xac minh thong tin'
WHERE account_id = 2
RETURNING account_id, ctid, note;
~~~

ở chế độ autocommit thông thường, PostgreSQL tạo phiên bản mới và commit thay đổi thành công. Lệnh `UPDATE` tiếp theo lại có thể tạo phiên bản khác. Đây là điều cốt lõi của kiến trúc **multi-version** trên heap.

## 8. CTID, index và hành trình truy cập một hàng

### 8.1. Vì sao B-tree index phải tham chiếu heap?

Giả sử bảng có:

~~~sql
CREATE INDEX idx_accounts_owner_name
ON storage_lab.accounts (owner_name);
~~~

Một secondary B-tree index sắp xếp key theo `owner_name` và lưu tham chiếu phù hợp tới các heap tuples, thường thông qua **heap TID**.

Truy vấn:

~~~sql
SELECT account_id, owner_name, balance
FROM storage_lab.accounts
WHERE owner_name = 'Nguyen An';
~~~

có thể đi theo đường:

~~~text
Query WHERE owner_name = 'Nguyen An'
                    |
                    v
          B-tree Index Scan
                    |
                    v
       Entry: key + heap TID
                    |
                    v
   Heap page tại block số X
                    |
                    v
       Line pointer số Y
                    |
                    v
   Heap tuple / phiên bản phù hợp
                    |
                    v
   Kiểm tra visibility và đọc cột
~~~

Từ index entry có thể tìm đúng page và line pointer thay vì quét toàn bộ heap. Tuy nhiên, optimizer **không bắt buộc** dùng index: trên bảng chỉ ba hàng, `Seq Scan` có thể rẻ hơn.

### 8.2. Vai trò của visibility khi đọc index

Một index entry chỉ giúp tìm các ứng viên. Với MVCC, còn phải quyết định tuple nào **được nhìn thấy trong snapshot của truy vấn**. Một số index entries có thể trỏ tới phiên bản cũ chưa được dọn, hoặc một HOT chain cần theo dấu để tìm phiên bản hợp lệ.

Cần phân biệt:

- **Index lookup:** tìm vị trí có khả năng phù hợp.
- **Heap access:** đọc tuple chứa dữ liệu hoặc kiểm tra trạng thái cần thiết.
- **MVCC visibility:** quyết định phiên bản thuộc kết quả truy vấn hay không.

Không phải cứ tìm được index entry là chắc chắn có một hàng hiện hành nhìn thấy được.

### 8.3. Index Only Scan và Visibility Map

Nếu một index có đủ các cột cần truy vấn, PostgreSQL **có thể** chọn `Index Only Scan`. Nhưng với PostgreSQL heap, index thông thường không mang toàn bộ thông tin visibility của từng tuple. Visibility Map giúp biết trang nào **all-visible** để một số trường hợp không cần truy cập heap nhằm kiểm tra visibility.

Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id
FROM storage_lab.accounts
WHERE account_id BETWEEN 1 AND 3;
~~~

Nếu kế hoạch xuất hiện `Index Only Scan`, xem thêm số **Heap Fetches**: tên node không đảm bảo số lần đọc heap luôn bằng 0. Trên bảng mới ghi hoặc chưa được VACUUM cập nhật visibility map, vẫn có thể cần heap fetches.

Kế hoạch và số liệu của ví dụ phụ thuộc bảng, thống kê và thời điểm chạy; không nên gán trước rằng nó chắc chắn có `Index Only Scan`.

## 9. UPDATE, MVCC và chuỗi phiên bản

### 9.1. Vì sao không cập nhật “đè lên hàng cũ”?

Nếu PostgreSQL thay đổi trực tiếp nội dung tuple cũ trước khi một transaction khác kết thúc đọc, nó phải tìm cách bảo toàn snapshot và đảm bảo recovery. Cơ chế MVCC heap cho phép PostgreSQL giữ **phiên bản cũ** cho các transaction còn cần và tạo **phiên bản mới** cho thay đổi.

Ví dụ:

~~~text
Thời gian →
       T1 đọc balance = 1.000.000
       |
       |        T2 UPDATE balance = 1.100.000
       |                         |
       |                         T2 COMMIT
       |
       T1 có thể tiếp tục đọc phiên bản phù hợp snapshot của T1
       theo mức cô lập/timing của truy vấn
~~~

PostgreSQL dùng thông tin trong heap tuple header như `xmin`, `xmax`, flags và trạng thái transaction để xác định phiên bản nào hợp lệ. Các cột hệ thống `xmin`, `xmax` có thể được truy vấn để học, nhưng **không dùng transaction ID thô như ID nghiệp vụ hoặc đồng hồ thời gian commit**.

### 9.2. CTID mới và liên kết t_ctid

Khi một phiên bản bị cập nhật, header nội bộ của phiên bản cũ có thể chứa `t_ctid` trỏ đến phiên bản tiếp theo. Nếu phiên bản mới lại được cập nhật, có thể hình thành một **chuỗi các phiên bản**.

~~~text
Heap tuple V1 (balance = 1.000.000)
      t_ctid -----> Heap tuple V2 (balance = 1.100.000)
                             t_ctid -----> Heap tuple V3 (...)
~~~

Đây là mô hình khái niệm để hiểu cập nhật. Đừng hiểu chuỗi luôn được giữ nguyên mãi: `VACUUM` và pruning có thể dọn tuple cũ, điều chỉnh line pointer và tái sử dụng không gian khi an toàn.

### 9.3. Tại sao SELECT có thể thấy dữ liệu cũ sau commit?

Mỗi statement/transaction có **snapshot** tùy mức isolation.

- Ở `READ COMMITTED` (mức mặc định thông dụng của PostgreSQL), mỗi câu `SELECT` dùng snapshot phù hợp tại **đầu câu lệnh**. Câu sau trong cùng transaction có thể thấy commit của transaction khác.
- Ở `REPEATABLE READ`, các câu lệnh trong transaction dùng snapshot giao dịch nhất quán theo quy tắc PostgreSQL, nên một commit từ người khác sau mốc snapshot không nhất thiết xuất hiện trong câu đọc tiếp theo.
- Một transaction còn nhìn thấy **thay đổi do chính nó thực hiện** trong phạm vi phù hợp, không bị “đóng băng tuyệt đối” trước các câu ghi của nó.

Điều này lý giải vì sao trên đĩa **nhiều heap tuple versions** có thể cùng tồn tại dù câu SQL bình thường chỉ trả **một phiên bản hợp lệ**.

## 10. HOT Update: tối ưu hóa cập nhật trên cùng trang

### 10.1. HOT là gì?

**HOT (Heap-Only Tuple)** là cơ chế PostgreSQL tối ưu một số `UPDATE` bằng cách tạo phiên bản mới **trên cùng heap page** mà không phải bổ sung một bộ index entries cho phiên bản mới trong các index thông thường.

Ở mức khái niệm, điều kiện quan trọng thường gồm:

1. Giá trị của các cột mà index không thể bỏ qua khi cập nhật **không làm cần cập nhật index**. Cần tính cả các biểu thức/predicate của index khi phù hợp.
2. Heap page hiện tại có đủ không gian cho tuple version mới.
3. Những giới hạn của PostgreSQL/version và access method cho phép dùng HOT.

Vì vậy `UPDATE` thay đổi chỉ một cột **không nằm trong các index liên quan** là ứng viên HOT, nhưng không có cam kết HOT chắc chắn. Nếu page đầy hoặc có index expression phụ thuộc cột ấy, cơ chế có thể khác.

### 10.2. Cách HOT giảm chi phí index

Không có HOT:

~~~text
B-tree index
    ├── key → TID V1
    └── key → TID V2  (có thể cần entry mới)

Heap
    ├── V1
    └── V2
~~~

Với HOT, minh họa:

~~~text
B-tree index
    └── key → root TID trong Heap Page A
                      |
                      v
                 HOT chain
                 V1 → V2 → V3
                 (trong cùng page)
~~~

Khi các phiên bản cũ đủ điều kiện dọn, PostgreSQL có thể dùng **redirect line pointer** để duy trì đường đi từ index tới phiên bản còn hợp lệ. Điều này giảm churn ở index và có thể giảm lượng công việc VACUUM tương ứng.

**HOT vẫn tạo phiên bản heap tuple mới và CTID phiên bản mới có thể khác.** Nó không biến `UPDATE` thành ghi đè tại chỗ theo nghĩa SQL.

### 10.3. Quan sát số HOT updates

Có thể xem thống kê:

~~~sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab'
  AND relname = 'accounts';
~~~

- `n_tup_upd`: bộ đếm thống kê về những tuple đã update.
- `n_tup_hot_upd`: số lần update được ghi nhận là HOT.
- `n_dead_tup`: ước lượng số dead tuples.

Chỉ số có thể cần thời gian để cập nhật trong statistics collector và phụ thuộc lịch sử từ khi thống kê được reset; không dùng một phép chia trên vài dòng để kết luận hệ thống đang đạt tỷ lệ HOT tối ưu.

### 10.4. Fillfactor và không gian cho HOT

PostgreSQL hỗ trợ tùy chọn lưu trữ bảng:

~~~sql
ALTER TABLE storage_lab.accounts SET (fillfactor = 80);
~~~

Trong quá trình ghi dữ liệu hoặc rewrite theo các cơ chế phù hợp, fillfactor thấp hơn để lại thêm không gian trên page, làm HOT khả thi hơn khi cập nhật nhiều. Tuy vậy:

- Thay tùy chọn fillfactor **không lập tức tổ chức lại toàn bộ những page đã ghi**.
- Fillfactor thấp làm bảng có thể chiếm **nhiều page hơn**, tăng I/O scan.
- Nếu cập nhật chủ yếu thay đổi cột index hoặc hàng quá lớn, thêm không gian chưa chắc đủ.
- Cần đo workload ghi/đọc, tỷ lệ HOT, page bloat và kích thước bảng.

Không có một fillfactor tối ưu cho mọi hệ thống. Bảng append-only/ít update và bảng update liên tục có đặc điểm khác nhau.

## 11. VACUUM, pruning và tái sử dụng vị trí

### 11.1. UPDATE và DELETE tạo ra lịch sử cần dọn

Các thao tác ghi trong hệ thống MVCC có thể để lại các phiên bản tuple không còn cần cho query mới nhưng vẫn phải giữ cho snapshot cũ. Khi không còn transaction nào cần một phiên bản cũ, PostgreSQL có thể **dọn dẹp và tái sử dụng không gian** theo cơ chế bảo trì.

Hai khái niệm liên quan:

- **Page pruning:** dọn các version cũ trong page khi có cơ hội và an toàn, có thể gắn với hoạt động truy cập/update.
- **VACUUM:** xử lý tuple chết, cập nhật các cấu trúc phụ và hỗ trợ tái sử dụng không gian, đồng thời xử lý các nhiệm vụ liên quan tới transaction ID wraparound/freeze.

Thử trên lab:

~~~sql
VACUUM (VERBOSE) storage_lab.accounts;
~~~

Lệnh này là thao tác bảo trì nên **không chạy trên production** nếu chưa được phép. `VACUUM` thông thường có thể được chạy bởi autovacuum theo chính sách của server; không nhất thiết cần DBA tự gọi sau mỗi update.

### 11.2. VACUUM thường không xếp lại toàn bộ bảng

Một `VACUUM` thông thường chủ yếu thu hồi không gian **để tái sử dụng bên trong relation**; nó không mặc định nén toàn bộ bảng vào một tệp liên tục nhỏ nhất hoặc sắp xếp lại các hàng còn sống.

Một số không gian cuối relation có thể được trả về hệ điều hành trong điều kiện phù hợp. Nhưng phần lớn không gian được thu hồi thường dành cho **lần ghi tiếp theo** trong PostgreSQL.

**`VACUUM FULL` thì khác:** nó **rewrite table**, có thể làm kích thước file gọn hơn nhưng cần khóa chặt và tài nguyên bổ sung, và có thể làm thay đổi CTID hàng loạt.

### 11.3. Các thao tác nào ảnh hưởng CTID?

| Thao tác | Ảnh hưởng điển hình |
|---|---|
| `SELECT` | Không tạo tuple mới chỉ do việc trả kết quả; có thể cập nhật hint bits/page metadata |
| `INSERT` | Tạo tuple mới tại một vị trí hợp lệ |
| `UPDATE` | Tạo phiên bản tuple mới; CTID của phiên bản mới có thể khác |
| `DELETE` | Đánh dấu phiên bản theo MVCC, sau đó mới đủ điều kiện dọn |
| `VACUUM` thường | Prune/dọn dead tuples, tái sử dụng slot; không chủ động rewrite mọi live tuple |
| `VACUUM FULL` | Rewrite table; có thể đổi CTID của các live tuples |
| `CLUSTER` | Rewrite table theo thứ tự index; CTID có thể đổi |
| `REINDEX` | Xây lại index; không mặc định rewrite heap table |
| `TRUNCATE` | Loại bỏ dữ liệu và dùng cơ chế storage mới, mọi TID cũ không còn hữu ích |

Bảng nhằm hình thành quy tắc vận hành. Không nên dùng CTID làm khóa ổn định chỉ vì “hôm nay chỉ chạy VACUUM thường”: về lâu dài UPDATE hoặc table rewrite có thể xảy ra.

### 11.4. Vì sao transaction dài nguy hiểm?

Một transaction đọc giữ snapshot cũ lâu có thể khiến PostgreSQL chưa được phép dọn các tuple mà snapshot ấy vẫn có khả năng nhìn thấy. Khi ứng dụng để kết nối ở trạng thái `idle in transaction` quá lâu:

- Dead tuples có thể tích tụ.
- Heap và index có thể phình to (bloat).
- Vacuum và freezing có thể gặp khó khăn.
- Query/ghi có thể chịu thêm I/O và chi phí bảo trì.

MVCC mang lại đồng thời tốt hơn, nhưng có **chi phí duy trì phiên bản** cần được quản lý bằng transaction boundary và VACUUM.

## 12. Free Space Map và Visibility Map

### 12.1. FSM giúp tìm page có chỗ trống

Khi chèn hoặc cập nhật một tuple, PostgreSQL cần chọn page có đủ chỗ chứa tuple và một line pointer hợp lệ. **Free Space Map** ghi thông tin gần đúng về khả năng có không gian trống trong các page của relation.

Nếu một page không đủ chỗ, tuple có thể phải đặt ở page khác. Đó là một lý do UPDATE tạo CTID thuộc block mới.

FSM không phải danh sách chính xác của toàn bộ các row rảnh và không có nghĩa một page có **nhiều dead tuples** đã ngay lập tức có đúng lượng free space cho phép tái sử dụng: còn phụ thuộc pruning/VACUUM và tình trạng từng tuple.

### 12.2. VM lưu hai ý nghĩa quan trọng

Visibility Map duy trì thông tin ở cấp page, trong đó hai khái niệm thường gặp:

- **All-visible:** theo điều kiện của PostgreSQL, mọi tuple liên quan trong page đều nhìn thấy được với các transaction hiện hành cần xét, giúp một số hoạt động bỏ qua kiểm tra heap visibility.
- **All-frozen:** những tuple trong page đã đủ điều kiện frozen theo cơ chế chống transaction ID wraparound.

VM không giống FSM: một page có thể **không còn nhiều không gian trống** nhưng lại all-visible, hoặc có free space nhưng không all-visible.

### 12.3. Vì sao VM liên quan Index Only Scan?

Một index chứa đủ các cột để trả kết quả vẫn phải đảm bảo row version nhìn thấy với snapshot. Khi VM đánh dấu heap page all-visible, PostgreSQL có thể bỏ qua một số lần quay về heap để kiểm tra visibility.

Với trang vừa được INSERT/UPDATE, trạng thái VM có thể chưa phải all-visible. `VACUUM` thường là phần quan trọng của việc thiết lập lại bit này sau khi đủ điều kiện.

Cơ chế này giải thích tại sao **cùng một index** đôi khi có số `Heap Fetches` khác nhau giữa hai lần đo, dù SQL không đổi.

## 13. TOAST: vì sao một hàng có TEXT rất dài vẫn tồn tại?

### 13.1. Giới hạn của page và vấn đề giá trị lớn

Nếu page chỉ khoảng 8 KiB, ta có thể hỏi:

> Một hàng có cột `text` dài hàng trăm kilobyte hoặc `jsonb` lớn thì PostgreSQL chứa nó thế nào?

PostgreSQL có cơ chế **TOAST (The Oversized-Attribute Storage Technique)** để xử lý các thuộc tính biến độ dài lớn. Tùy kiểu dữ liệu, storage strategy, kích thước giá trị và tình trạng tuple, PostgreSQL có thể:

1. Lưu giá trị **trực tiếp trong heap tuple** khi đủ nhỏ.
2. **Nén** giá trị khi có lợi và kiểu cho phép.
3. **Đẩy dữ liệu ra TOAST table** ở một relation phụ, để heap tuple chính giữ thông tin tham chiếu.
4. Kết hợp các bước theo chính sách lưu trữ.

Không phải mọi cột `text` đều được đẩy sang TOAST. Một chuỗi ngắn thường nằm trực tiếp trong tuple, còn một chuỗi dài mới có thể làm PostgreSQL xem xét nén/đưa ra ngoài theo các ngưỡng và chính sách lưu trữ.

### 13.2. Hình dung quan hệ TOAST

~~~text
Heap table: documents
  Page 10
    LP #4
      Tuple
        id = 7
        title = "Huong dan"
        body = [TOAST external pointer]
                      |
                      v
TOAST relation phụ
   chunk 1, chunk 2, chunk 3, ...
   dữ liệu phần lớn của body
~~~

TOAST table có cấu trúc và index riêng để quản lý các phần dữ liệu lớn. Vì vậy footprint của một cột `text` dài có thể không nằm hoàn toàn trong `main fork` của bảng gốc.

### 13.3. Kiểm tra trên SQL

Có thể tạo bảng lab:

~~~sql
CREATE TABLE storage_lab.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

INSERT INTO storage_lab.documents (title, body)
VALUES (
    'Van ban dai',
    repeat('Noi dung huong dan PostgreSQL. ', 10000)
);

SELECT
    document_id,
    pg_column_size(body) AS stored_value_bytes,
    length(body) AS logical_characters,
    octet_length(body) AS logical_bytes
FROM storage_lab.documents;
~~~

Giải thích:

- `length(body)` là số ký tự của chuỗi.
- `octet_length(body)` là số byte của nội dung chuỗi theo encoding.
- `pg_column_size(body)` phản ánh kích thước lưu trữ/biểu diễn theo cơ chế PostgreSQL, có thể thấp hơn logical bytes do nén.

Chuỗi `repeat` có tính lặp cao, nên **đặc biệt dễ nén**. Vì vậy ví dụ này không phải cách đáng tin để đo throughput TOAST thực tế của dữ liệu không nén. Chọn dữ liệu đại diện khi benchmark.

Quan sát TOAST relation:

~~~sql
SELECT
    c.oid::regclass AS table_name,
    c.reltoastrelid::regclass AS toast_relation,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass;
~~~

Một bảng có thể có TOAST relation được thiết lập theo đặc tính schema, nhưng **không nhất thiết** đã lưu giá trị bên ngoài lớn. Quan sát metadata của TOAST relation không tự chứng minh mọi hàng đang dùng external TOAST.

### 13.4. TOAST và chi phí truy vấn

Truy vấn chỉ cần ID và title:

~~~sql
SELECT document_id, title
FROM storage_lab.documents
WHERE document_id = 1;
~~~

không nhất thiết phải giải nén/đọc toàn bộ `body` nếu phần đó không cần cho kết quả.

Ngược lại:

~~~sql
SELECT document_id, body
FROM storage_lab.documents
WHERE document_id = 1;
~~~

có thể cần xử lý giá trị lớn từ TOAST, làm tăng CPU, I/O và lượng dữ liệu gửi qua mạng.

Đây là lý do trên bảng có `text/jsonb/bytea` rất lớn nên **chọn đúng cột cần trả về**, tránh `SELECT *` theo thói quen.

## 14. Quan sát page và tuple bằng extension pageinspect

### 14.1. Khi nào cần pageinspect?

Các cột hệ thống `ctid` và thống kê SQL giúp quan sát ở mức cao. Nếu cần **nhìn trực tiếp header page và line pointers** để học kiến trúc, PostgreSQL cung cấp extension `pageinspect` trong các bản phân phối có đóng gói extension này.

> **Phần này chỉ dành cho lab/DBA được cấp quyền.** `pageinspect` đọc nội dung page ở mức thấp, có thể tiết lộ thông tin và thường yêu cầu đặc quyền phù hợp. Không tự tạo extension hay cấp quyền rộng trên production để học.

Khi được phép:

~~~sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
~~~

Lệnh này áp dụng vào **database hiện tại**, có yêu cầu quyền/extension availability riêng. Nếu gặp lỗi thiếu extension hoặc không có quyền, hãy dùng các cách SQL read-only ở phần khác thay vì cố mở quyền quản trị.

### 14.2. Xem PageHeaderData của block 0

Giả sử `storage_lab.accounts` đã được nạp và block 0 tồn tại:

~~~sql
SELECT *
FROM page_header(
    get_raw_page('storage_lab.accounts', 0)
);
~~~

Tùy phiên bản extension, kết quả có thể bao gồm:

- `lsn`
- `checksum`
- `flags`
- `lower`
- `upper`
- `special`
- `pagesize`
- `version`
- `prune_xid`

Có thể đối chiếu `lower` và `upper` với sơ đồ vùng trống của page. **Không có một bộ giá trị lower/upper cụ thể nào phải khớp trên mọi lần chạy**, vì heap page thay đổi theo INSERT/UPDATE/VACUUM.

### 14.3. Liệt kê line pointer và tuple header ở page 0

~~~sql
SELECT
    lp,
    lp_off,
    lp_flags,
    lp_len,
    t_xmin,
    t_xmax,
    t_ctid,
    t_hoff
FROM heap_page_items(
    get_raw_page('storage_lab.accounts', 0)
)
ORDER BY lp;
~~~

Ý nghĩa:

- `lp`: item pointer number trong page.
- `lp_off`: vị trí byte mà line pointer chỉ đến, khi có payload phù hợp.
- `lp_flags`: trạng thái `LP_UNUSED`, `LP_NORMAL`, `LP_REDIRECT`, `LP_DEAD` theo mã nội bộ.
- `lp_len`: kích thước payload theo item pointer.
- `t_xmin`, `t_xmax`: metadata giao dịch khi tuple header có thể đọc được.
- `t_ctid`: item pointer liên quan đến chuỗi phiên bản.
- `t_hoff`: byte offset bắt đầu vùng thuộc tính bên trong tuple.

Một line pointer không ở trạng thái `LP_NORMAL` không nhất thiết có tuple header có thể diễn giải thành một hàng SQL thông thường. Đừng coi mọi dòng của `heap_page_items` là một hàng người dùng đang tồn tại.

### 14.4. Đối chiếu ctid từ SQL với lp từ pageinspect

Đầu tiên:

~~~sql
SELECT ctid, account_id, owner_name
FROM storage_lab.accounts
ORDER BY account_id;
~~~

Nếu một hàng có CTID `(0,3)`, nó được tham chiếu qua **line pointer 3 của block 0**. Trong `heap_page_items(get_raw_page(..., 0))` hãy tìm `lp=3`.

Nhưng khi update/rollback/VACUUM xảy ra, raw page có thể chứa tuple chết hoặc chưa hiển thị theo snapshot. Lệnh `get_raw_page` đọc dữ liệu page vật lý, **không áp dụng toàn bộ MVCC visibility theo góc nhìn SQL như một `SELECT` bình thường**.

### 14.5. Những điều không nên kết luận từ raw page

- `t_xmax` có giá trị khác 0 không tự chứng minh tuple đã bị xóa thành công.
- Nhiều line pointers không đồng nghĩa có cùng số hàng SQL nhìn thấy.
- Một trang có vùng trống không đảm bảo chèn được bất kỳ hàng có kích thước nào.
- Page checksum hiện 0 không tự động là dữ liệu hỏng nếu checksum không được bật.
- Raw page giúp học cấu trúc nhưng không phải giao diện API ổn định cho truy vấn nghiệp vụ.

Để chẩn đoán hỏng trang, lỗi checksum hoặc sự cố WAL thật, cần runbook bảo trì/khôi phục riêng, không chỉ dựa trên một lệnh `pageinspect` trong phòng lab.

## 15. Đo kích thước relation và số page bằng SQL

### 15.1. Kích thước main fork

~~~sql
SELECT
    pg_relation_size('storage_lab.accounts'::regclass) AS main_bytes,
    current_setting('block_size')::integer AS block_bytes,
    pg_relation_size('storage_lab.accounts'::regclass)
        / current_setting('block_size')::integer AS main_pages;
~~~

Với heap table thông thường, `pg_relation_size(relation)` đo kích thước main fork nếu không chỉ định fork. Phép chia cho block size cho biết số block đang được phân bổ trong main fork tại thời điểm quan sát.

### 15.2. So sánh table, index và tổng lưu trữ

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('storage_lab.accounts'::regclass)
    ) AS main_heap_size,
    pg_size_pretty(
        pg_indexes_size('storage_lab.accounts'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('storage_lab.accounts'::regclass)
    ) AS total_relation_size;
~~~

`pg_total_relation_size` gồm nhiều thành phần hơn main heap như index, TOAST và auxiliary forks, tùy relation. Do đó không nên lấy **dung lượng main heap** làm “toàn bộ ổ đĩa mà bảng sử dụng”.

### 15.3. FSM và VM

~~~sql
SELECT
    pg_relation_size('storage_lab.accounts'::regclass, 'main')
        AS main_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'fsm')
        AS fsm_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'vm')
        AS vm_bytes;
~~~

Các auxiliary forks có thể chưa tồn tại hoặc nhỏ tùy trạng thái bảng. Chúng có thể được tạo/cập nhật bởi PostgreSQL khi cần. Không lấy việc một fork có size nhỏ hoặc bằng 0 để suy luận không có dead tuples hoặc không có MVCC.

### 15.4. pg_class: relpages và reltuples là thống kê

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.relpages,
    c.reltuples
FROM pg_class AS c
WHERE c.oid = 'storage_lab.accounts'::regclass;
~~~

- `relpages`: số trang ước lượng/stats liên quan đến relation.
- `reltuples`: số tuple sống ước lượng theo thống kê của planner.

Các giá trị này có thể chưa cập nhật ngay sau INSERT/UPDATE. Không dùng `reltuples` như `COUNT(*)` chính xác.

Khi được phép trên lab:

~~~sql
ANALYZE storage_lab.accounts;
~~~

`ANALYZE` cập nhật statistics phục vụ planner; nó không thay đổi việc PostgreSQL dùng page/block và không phải lệnh tạo index. Trên production, thao tác này có chi phí và ảnh hưởng kế hoạch truy vấn nên cần quản lý theo quy trình vận hành.

## 16. Những sai lầm thường gặp khi nói về vị trí vật lý

### Sai lầm 1: “CTID là số hàng”

Sai. CTID là `(block number, line pointer number)`. Không có thứ tự hàng SQL ổn định khi không dùng `ORDER BY`, và CTID không biểu diễn ID nghiệp vụ.

### Sai lầm 2: “Offset trong CTID là byte offset”

Sai. Offset thứ hai là **số mục line pointer**. Vị trí byte payload do line pointer quản lý.

### Sai lầm 3: “Mỗi UPDATE sửa thẳng một hàng cũ”

Sai theo mô hình heap MVCC phổ biến: UPDATE tạo phiên bản mới; phiên bản cũ được giữ tới lúc có thể dọn. HOT là tối ưu **giảm index churn**, không phải bỏ qua việc tạo heap tuple version.

### Sai lầm 4: “Mỗi UPDATE đều phải thêm index entries mới”

Không hẳn. Nếu đủ điều kiện **HOT**, PostgreSQL có thể tạo phiên bản mới cùng page mà không thêm bộ index entries mới theo cách của non-HOT update.

### Sai lầm 5: “VACUUM luôn làm bảng nhỏ đi trên đĩa”

`VACUUM` thường chủ yếu làm không gian **có thể tái sử dụng** trong relation. `VACUUM FULL` rewrite và có thể thu gọn, nhưng cần khóa chặt và có thể đổi CTID.

### Sai lầm 6: “Line pointer không đổi thì hàng được định danh mãi mãi”

Line pointer có thể tồn tại trong quá trình compact/HOT, nhưng slot có thể được tái sử dụng về sau. Chỉ dùng primary key hoặc unique business key cho tham chiếu bền vững.

### Sai lầm 7: “Một hàng VARCHAR/TEXT dài phải nằm trọn trong 8 KiB”

TOAST có thể nén hoặc lưu thuộc tính lớn ngoài heap tuple. Giá trị biến độ dài không được phép làm một heap tuple vượt quá khả năng bố trí page; cơ chế lưu trữ giải quyết nhiều tình huống.

### Sai lầm 8: “Index Only Scan không bao giờ đọc heap”

PostgreSQL cần thông tin visibility; khi VM chưa đủ all-visible, `Index Only Scan` có thể có **Heap Fetches**.

### Sai lầm 9: “Một tuple vật lý tương đương một hàng nhìn thấy ở SELECT”

Trong hệ thống MVCC, page có thể chứa phiên bản cũ, mới, chưa commit hoặc đã chết. Snapshot và transaction status quyết định SQL thấy gì.

### Sai lầm 10: “Có thể đọc raw page trên production như SELECT bình thường”

`pageinspect` là công cụ thấp cấp cần quyền, có thể lộ thông tin vật lý và không tự lọc theo visibility SQL. Chỉ dùng có mục đích, trên môi trường được phép.

### Sai lầm 11: “Một bảng = một file duy nhất”

Relation có fork, segment, index riêng và có thể có TOAST relation. Physical layout nhiều thành phần hơn một file heap.

### Sai lầm 12: “Có ctid rồi thì không cần PRIMARY KEY”

Primary key giải quyết định danh logic, toàn vẹn và quan hệ giữa các bảng. CTID chỉ là vị trí phiên bản vật lý, không có những bảo đảm tương đương.

## 17. Sơ đồ tổng hợp: từ index đến tuple và MVCC

~~~mermaid
flowchart TD
    A["SELECT ... WHERE account_id = 42"] --> B{"Planner chọn đường truy cập"}
    B -- "Index Scan" --> C["B-tree index lookup"]
    B -- "Seq Scan" --> D["Duyệt các heap pages"]
    C --> E["Heap TID: (block, line pointer)"]
    E --> F["Đọc page và line pointer"]
    D --> F
    F --> G["Heap tuple / HOT chain khi cần"]
    G --> H{"Phiên bản hợp lệ với snapshot?"}
    H -- "Có" --> I["Đọc thuộc tính, TOAST nếu cần"]
    H -- "Không" --> J["Bỏ qua / theo phiên bản phù hợp"]
    J --> G
    I --> K["Trả hàng kết quả SQL"]
~~~

Sơ đồ nhằm thể hiện **các lớp khái niệm**. Executor PostgreSQL có nhiều tối ưu hóa, ví dụ bitmap scan, index-only scan và nhiều kiểu index access. Không phải truy vấn nào cũng đi đúng một tuyến cố định.

## 18. Bài tập thực hành

Các bài dùng bảng `storage_lab.accounts` từ mục 7, và `storage_lab.documents` từ mục 13 nếu cần. Không thực hiện những thao tác thay đổi/khảo sát raw page trên production chưa được phép.

### Bài 1 — Xác định block size

Viết câu SQL lấy block size PostgreSQL đang dùng. Nếu main fork của bảng có 1.638.400 byte và block size là 8192 byte, bảng chứa bao nhiêu page main fork?

### Bài 2 — Giải thích CTID

Một hàng trả `ctid='(12,7)'`. Giải thích chính xác hai con số, và vì sao không được suy luận đó là “hàng thứ 7 của khách hàng số 12”.

### Bài 3 — Quan sát cập nhật

Chọn `account_id=1`, ghi CTID ban đầu, chạy một `UPDATE` có `RETURNING ctid` trong transaction rồi rollback. Nêu những điều được phép kết luận từ CTID mới.

### Bài 4 — Tại sao có line pointer?

Giả sử payload của tuple thay đổi vị trí byte bên trong cùng page do compact. Vì sao một tham chiếu (block, line pointer number) giúp tránh phải sửa mọi tham chiếu bên ngoài page?

### Bài 5 — MVCC và số lượng tuple

Một bảng có 100 hàng logic hiện hành. Vì sao một công cụ raw page có thể nhìn thấy nhiều hơn 100 tuple headers? Tại sao `SELECT COUNT(*)` không nhất thiết bằng số dòng `heap_page_items`?

### Bài 6 — Chọn HOT hay non-HOT

Bảng có index trên `account_id` và `owner_name`. Bạn cập nhật chỉ cột `note`; trong tình huống nào cập nhật có thể là HOT? Nếu cập nhật `owner_name` thì sao? Vai trò của free space trên page là gì?

### Bài 7 — VACUUM và CTID

So sánh `VACUUM` thường, `VACUUM FULL` và `CLUSTER` theo: có rewrite toàn bảng không, có thể đổi CTID của live tuples không, có thể giảm file size không và có ảnh hưởng vận hành gì?

### Bài 8 — TOAST

Một bảng có cột `body TEXT` dài 300 KiB. Tại sao vẫn có thể lưu giá trị dù page size là 8 KiB? Trình bày hai cơ chế chính của TOAST và lý do `SELECT id, title` có thể rẻ hơn `SELECT *`.

### Bài 9 — Quan sát size và forks

Viết SQL lấy kích thước main, FSM, VM, indexes và tổng dung lượng relation. Chỉ rõ vì sao tổng có thể lớn hơn main fork nhiều lần.

### Bài 10 — Index Only Scan

Một query chỉ chọn cột trong B-tree index nhưng `EXPLAIN ANALYZE` báo `Heap Fetches > 0`. Điều đó có nhất thiết là index hỏng không? Vai trò của Visibility Map?

### Bài 11 — Tìm thông tin page bằng pageinspect

Trên một database lab được DBA cho phép, dùng `page_header(get_raw_page(...,0))` và `heap_page_items(...)` để lấy các mốc `lower`, `upper`, `lp`, `lp_off`. Vì sao phải xem `lp_flags` trước khi diễn giải tuple header?

### Bài 12 — Lựa chọn khóa cho ứng dụng

Một lập trình viên muốn lưu `orders.ctid` vào bảng `payments` làm khóa ngoại vì CTID “tra nhanh”. Giải thích ít nhất bốn rủi ro và đề xuất thiết kế phù hợp.

## 19. Gợi ý lời giải

### Bài 1

~~~sql
SELECT current_setting('block_size')::integer AS bytes_per_page;
~~~

Nếu block size bằng 8192 byte:

~~~text
1.638.400 / 8.192 = 200 page
~~~

Đây là phép tính minh họa; cần dùng block size thực tế và kiểm tra main fork đúng relation.

### Bài 2

`(12,7)` là **block 12, item pointer/line pointer số 7 trong block ấy**. Offset không phải byte offset hoặc business ID. Vị trí này có thể thay đổi theo update/rewrite và không xác định thứ tự nghiệp vụ.

### Bài 3

~~~sql
BEGIN;
SELECT account_id, ctid
FROM storage_lab.accounts
WHERE account_id = 1;

UPDATE storage_lab.accounts
SET note = note || ' - kiem tra'
WHERE account_id = 1
RETURNING account_id, ctid;

ROLLBACK;
~~~

UPDATE tạo phiên bản mới với CTID của phiên bản đó; giá trị cụ thể có thể cùng block hoặc khác block, phụ thuộc page. Rollback loại bỏ thay đổi chưa commit theo ngữ nghĩa giao dịch. Không lưu CTID mới vào một bảng khác như định danh lâu dài.

### Bài 4

Line pointer giữ lớp gián tiếp giữa TID và byte offset tuple. Khi compact page, PostgreSQL có thể cập nhật offset trong line pointer mà không đổi (block number, line pointer number) trong những tham chiếu còn hợp lệ.

### Bài 5

UPDATE/DELETE theo MVCC có thể để lại **các phiên bản cũ chưa được dọn**, cùng với tuple chưa commit hoặc không còn hiện hành. `COUNT(*)` xét hàng **nhìn thấy theo snapshot SQL**, không phải đếm mọi item pointer của raw page.

### Bài 6

Cập nhật `note` có thể là HOT nếu không ảnh hưởng tới key/expression/predicate của index cần cập nhật và **có đủ không gian trong cùng page**. Cập nhật `owner_name` đang được index thường cần bảo trì index nên không phải HOT theo cùng cách. Fillfactor thấp có thể dành thêm không gian nhưng không đảm bảo HOT.

### Bài 7

- `VACUUM` thường: dọn dead tuples và làm không gian có thể tái dùng; không rewrite toàn bộ live tuples như một bảng mới.
- `VACUUM FULL`: rewrite table, có thể thu gọn kích thước, cần khóa mạnh và có thể đổi CTID.
- `CLUSTER`: rewrite/sắp xếp lại heap theo index được chọn, có thể đổi CTID và tác động lớn đến hoạt động hệ thống.

Không chạy hai lệnh cuối trên production chỉ để kiểm tra CTID.

### Bài 8

TOAST có thể **nén** và/hoặc lưu dữ liệu lớn **ở relation phụ**, để tuple chính giữ thông tin tham chiếu. `SELECT id,title` không nhất thiết phải đọc và detoast toàn bộ `body` khi không dùng đến. `SELECT *` có thể tốn thêm I/O/CPU/network.

### Bài 9

~~~sql
SELECT
    pg_relation_size('storage_lab.accounts'::regclass, 'main') AS main_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'fsm') AS fsm_bytes,
    pg_relation_size('storage_lab.accounts'::regclass, 'vm') AS vm_bytes,
    pg_indexes_size('storage_lab.accounts'::regclass) AS index_bytes,
    pg_total_relation_size('storage_lab.accounts'::regclass) AS total_bytes;
~~~

Tổng có thể gồm indexes, TOAST, auxiliary forks và thành phần khác, nên lớn hơn main heap.

### Bài 10

Không nhất thiết hỏng. `Index Only Scan` cần bảo đảm visibility; khi page chưa all-visible trong Visibility Map, executor có thể phải truy cập heap. `Heap Fetches > 0` là hiện tượng hợp lệ.

### Bài 11

~~~sql
SELECT lower, upper, special, pagesize
FROM page_header(get_raw_page('storage_lab.accounts', 0));

SELECT lp, lp_off, lp_flags, lp_len, t_ctid
FROM heap_page_items(get_raw_page('storage_lab.accounts', 0))
ORDER BY lp;
~~~

Các slot `LP_UNUSED/LP_REDIRECT/LP_DEAD` không có cùng ý nghĩa với `LP_NORMAL`; không được diễn giải mọi dòng kết quả thành một tuple SQL hợp lệ.

### Bài 12

CTID có thể thay đổi sau UPDATE, VACUUM FULL và CLUSTER, slot có thể tái sử dụng, không có đảm bảo định danh giữa các lần chạy/quan hệ/partition, và không thể thay thế FK logic. Nên dùng `orders.order_id` là primary key, `payments.order_id` là foreign key tới khóa ấy.

## 20. Kết luận

PostgreSQL tổ chức heap table thành **những trang (pages/blocks)** có page header, mảng **line pointers**, vùng trống và **heap tuples**. Mỗi tuple là một **phiên bản vật lý của hàng** với metadata MVCC và các giá trị thuộc tính. Vị trí tuple được tham chiếu bằng **TID dạng (block, offset)**; cột hệ thống `ctid` cho phép quan sát vị trí phiên bản hàng đang đọc.

Line pointer giúp PostgreSQL di chuyển payload bên trong page mà không cần đổi ngay tham chiếu đến slot. Nhưng CTID **không bền vững như khóa nghiệp vụ**: cập nhật sinh tuple version mới, thao tác rewrite đổi vị trí, và slot cũ có thể được tái sử dụng. MVCC, HOT, VACUUM, FSM, VM và TOAST bổ sung cho nhau để phục vụ **tính đúng đắn, đồng thời và hiệu quả lưu trữ**.

Khi cần quan sát, hãy bắt đầu bằng SQL an toàn như `SELECT ctid`, `pg_relation_size`, `pg_class` và `EXPLAIN`. `pageinspect` chỉ sử dụng ở môi trường có quyền phù hợp để đi sâu tới header và item pointers. Hiểu cấu trúc này giúp lý giải vì sao index trỏ tới heap, tại sao `UPDATE` tạo lịch sử phiên bản, vì sao `VACUUM` quan trọng và vì sao **primary key vẫn là cách định danh lâu dài đúng đắn cho dữ liệu ứng dụng**.
