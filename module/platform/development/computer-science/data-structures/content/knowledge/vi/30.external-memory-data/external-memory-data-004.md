# Thiết kế nút theo trang và tận dụng quét liên tiếp

## 1. Vì sao một nút cây trên đĩa không nên chứa đúng một khóa?

Trong RAM, ta thường học cây tìm kiếm nhị phân với một nút gồm một khóa và hai con trỏ. Nếu dữ liệu đủ nhỏ, cách này thuận tiện: đi trái hoặc phải sau một phép so sánh. Nhưng khi mỗi nút nằm trên **một trang dữ liệu ngoài RAM**, một lần đọc nút có thể cần truy cập SSD/HDD.

Hãy so sánh hai cách lưu một triệu khóa:

```text
BST nhị phân trên đĩa:
     [50]
     /  \
   [20] [80]       Mỗi nút ở một trang khác nhau:
   ...  ...        một bước có thể cần một I/O.

B+ tree theo trang:
         [20 | 40 | 60 | 80]
         /    |    |    |    \
      page  page page page   page

Một trang có nhiều khóa phân cách:
đọc một trang để chọn một trong nhiều nhánh.
```

Nếu mỗi lần chạm bộ nhớ ngoài có độ trễ đáng kể, ta muốn **đọc một trang và khai thác càng nhiều thông tin hữu ích càng tốt**. Đây là nền tảng của thiết kế **page-oriented nodes** và việc tận dụng **quét liên tiếp** (*sequential/range scanning*).

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **nút logic**, **trang lưu trữ**, **khối I/O**, **cache line** và **trang bộ nhớ ảo**.
2. Tính số khóa/con trỏ hoặc bản ghi vừa một trang, xét header, slot directory và fill factor.
3. Giải thích bố trí **slotted page** cho bản ghi có độ dài biến thiên, khoảng trống và compaction.
4. Phân biệt **internal page** và **leaf page** của B+ tree; phân tích fanout và chiều cao.
5. Thiết kế và mô phỏng **range scan** bằng linked leaf pages và buffer RAM.
6. Tính **I/O tìm trang bắt đầu + I/O quét lá + I/O lấy bản ghi gốc** với index không bao phủ.
7. Phân biệt **thứ tự khóa logic** và **tính liên tiếp vật lý**; hiểu tác dụng của clustering, read-ahead và prefetch.
8. Nêu các trường hợp khó: split, merge, xóa, fragmentation, overflow, concurrency và recovery.
9. Viết ví dụ Python mô phỏng page layout và scan, kiểm tra bất biến, benchmark theo số lần đọc trang.
10. Chọn cấu trúc theo workload, từ truy vấn điểm và range scan đến đọc tuần tự lượng lớn dữ liệu.

Bài thuộc chương **Dữ liệu ngoài bộ nhớ**, trong học phần **Cấu trúc dữ liệu**: từ mảng, danh sách liên kết, stack, queue và bảng băm đến cây, heap, đồ thị, ta cần hiểu cả **bất biến** lẫn độ phức tạp thời gian/bộ nhớ để chọn cấu trúc phù hợp. Ở đây thước đo quan trọng là **số trang/khối phải truyền giữa thiết bị và bộ nhớ trong**.

## 2. Mô hình hai tầng: N, M, B

Mô hình external memory xem dữ liệu nằm ở **bộ nhớ ngoài** và được đưa vào **bộ nhớ trong** theo những khối gồm `B` phần tử.

```text
    RAM dành cho thuật toán: M phần tử
    +--------------------------------+
    | buffer page | buffer | ...     |
    +--------------------------------+
             ^             |
             |  block I/O  |
             v             v
    SSD/HDD: N phần tử trong các trang
    [page 0] [page 1] [page 2] ...
```

| Ký hiệu | Ý nghĩa | Đơn vị nhất quán trong phân tích |
|---|---|---|
| `N` | Số phần tử/bản ghi trong tập dữ liệu | Phần tử |
| `M` | Dung lượng RAM dành cho thuật toán | Phần tử |
| `B` | Số phần tử mỗi khối truyền | Phần tử/block |
| `P` | Kích thước trang trong ví dụ layout | Byte/page |
| `H` | Header của trang | Byte/page |
| `s` | Kích thước bản ghi cố định | Byte/bản ghi |
| `F` | Số nhánh của internal node | Con/nút |
| `K` | Số bản ghi cần xuất trong range scan | Bản ghi |

Khi một công thức dùng `N/B`, `B` phải là **số phần tử mỗi block**. Nếu biết trang dài `P` byte thì phải tính số bản ghi vừa trang từ `P`, kích thước mỗi bản ghi và overhead, **không được chia số bản ghi trực tiếp cho số byte**.

### Phải phân biệt mô hình và thiết bị thật

Mô hình đếm số **block transfers**. Thời gian thật còn phụ thuộc:

- Một page đang nằm trong OS page cache hoặc buffer pool chưa?
- Thiết bị là HDD hay SSD; dữ liệu vật lý nằm rải rác không?
- Có bao nhiêu yêu cầu I/O đồng thời; request lớn hay nhỏ?
- Cần đọc, ghi, fsync hoặc flush; có nén, giải mã, kiểm tra checksum không?

Do đó, `O(N/B)` I/O là kết quả về **số khối** với giả định đã nêu, không phải lời hứa mọi lần quét mất một số mili-giây cố định.

## 3. Page, block, cache line và memory page không giống nhau

Một trang B+ tree là **đơn vị logic** mà cấu trúc dữ liệu dùng để lưu nhiều khóa/con trỏ hoặc bản ghi. Nó có thể được thiết kế phù hợp với hệ thống I/O, nhưng không phải mọi loại trang đều giống nhau.

| Thuật ngữ | Vai trò | Ví dụ minh họa |
|---|---|---|
| CPU cache line | Chuyển dữ liệu giữa các tầng cache CPU | Thường gặp `64 B` |
| Virtual-memory page | Đơn vị ánh xạ địa chỉ của MMU/OS | Thường gặp `4 KiB` |
| File-system block | Đơn vị cấp phát/tổ chức hệ thống file | Có thể `4 KiB` |
| Database page | Đơn vị trang do database tự quản lý | Có thể `4`, `8` hoặc `16 KiB` |
| Device logical sector | Đơn vị địa chỉ hóa ở giao diện thiết bị | `512 B` hoặc `4 KiB` là các ví dụ |
| I/O request | Lệnh đọc/ghi thực tế của phần mềm | Có thể chứa một hay nhiều trang |
| Block trong I/O model | Đơn vị chuyển lý tưởng trong phân tích | `B` phần tử, sau quy đổi từ byte |

Không được coi một lần truy cập page database luôn tương đương **một** request vật lý. Trang có thể đã trong RAM; một lần đọc có thể được gộp với những trang khác; OS có thể tách hoặc hợp nhất request; trang còn có thể phải đọc nhiều block thiết bị.

### Căn chỉnh (alignment)

Nếu một trang `P` byte bắt đầu ở địa chỉ/bù tệp không căn phù hợp, một lần đọc có thể chạm qua ranh giới các block thấp hơn. Căn chỉnh dữ liệu, kích thước trang và kích thước request phù hợp có thể giúp giảm số lần chạm khối và tránh các hạn chế của direct I/O.

**Đừng tự giả định page = 4096 byte trong mọi hệ thống.** Trong phần tính số sau đây, `4096` chỉ là tham số giả định để minh họa.

## 4. Bố trí trang: header, slot directory, payload và free space

Một node/page thường không chỉ chứa một mảng khóa. Với trang có bản ghi độ dài biến thiên, một bố trí phổ biến là **slotted page**.

```text
Trang P byte
 offset 0                                               P
    |                                                   |
    v                                                   v
    +----------+----------------+..............+--------+
    | HEADER   | SLOT DIRECTORY |   FREE SPACE  | RECORDS|
    +----------+----------------+..............+--------+
                 ----> tăng       <---- tăng

HEADER: page ID, kiểu trang, số slot, free pointers,
        flags, checksum/LSN hoặc metadata khác.

SLOT DIRECTORY:
        slot 0 -> (offset, length)
        slot 1 -> (offset, length)
        ...

RECORDS: payload nằm ở cuối trang, phát triển về đầu.
```

Mỗi **slot** có thể giữ một cặp `(offset,length)` trỏ tới vị trí bản ghi trong trang. Nhờ vậy, khi nén lại các record bên trong trang (**compaction**), có thể đổi offset trong slot mà vẫn giữ số hiệu slot nếu giao thức record ID cần.

### Tại sao không cứ lưu [record0, record1, ...] liên tiếp?

Với record có độ dài khác nhau, xóa hoặc cập nhật record có thể để lại **lỗ trống**. Nếu mọi record phải liền kề từ đầu trang, thay đổi một record có thể buộc dịch chuyển nhiều byte.

Slot directory cho phép:

- Tách **thứ tự logic/ID** khỏi vị trí vật lý hiện tại trong trang.
- Đánh dấu một slot bị xóa mà chưa di chuyển các record còn lại.
- Tổ chức lại payload mà vẫn cập nhật thông qua slot tương ứng.

### Nhưng slot directory cũng tốn chỗ

Nếu mỗi record cần `4` byte slot và payload dài `s` byte, với header `H`, dung lượng trang tối đa trong mô hình record cố định xấp xỉ:

\[
\boxed{L=\left\lfloor\frac{P-H}{s+4}\right\rfloor.}
\]

Ví dụ `P=4096`, `H=96`, record payload `s=120` byte:

\[
L=\left\lfloor\frac{4096-96}{120+4}\right\rfloor
=\left\lfloor\frac{4000}{124}\right\rfloor
=\boxed{32\text{ record/page}.}
\]

Nếu quên `4` byte slot/record, ta sẽ tính sai thành `\lfloor4000/120\rfloor=33`.

## 5. Record ID, slot ID và tính ổn định khi compaction

Một định danh bản ghi vật lý thường có dạng:

```text
RID = (page_id, slot_id)
```

Khi đọc `RID=(17,5)`, hệ thống lấy page `17` vào RAM, xem slot `5`, tìm offset/length và đọc payload tương ứng.

### Compaction

Giả sử trong page có:

```text
slot 0 -> record A: 12 byte
slot 1 -> record B: 50 byte
slot 2 -> record C: 16 byte
```

Sau khi xóa `B`, vùng 50 byte có thể trở thành **lỗ trống không liên tục**. Compaction sao chép các record còn sống vào vùng payload gọn hơn, rồi cập nhật các offset của slot `0` và `2`.

Nếu **slot ID không thay đổi**, RID của A/C vẫn có thể hợp lệ. Nhưng nếu bản ghi được chuyển sang **page khác**, RID cũ có thể cần forwarding pointer hoặc cập nhật các chỉ mục đang tham chiếu tới nó.

### Tombstone và delete

Một slot bị xóa có thể đánh dấu là `deleted/tombstone`. Dữ liệu cũ không còn là record hợp lệ dù byte payload vẫn chưa được thu hồi ngay. Hệ thống phải phân biệt:

- **Logical free space:** tổng byte có thể thu hồi, kể cả các lỗ trống.
- **Contiguous free space:** khoảng trống liền mạch còn đủ để đặt record mới ngay.

Nếu record mới dài `50` byte, page có tổng 60 byte lỗ trống nhưng khoảng trống liền mạch chỉ 20 byte, có thể cần **compaction** trước khi chèn.

## 6. Bản ghi dài biến thiên: kích thước trung bình chưa đủ

Với fixed-size records, công thức `\lfloor(P-H)/(s+slot)\rfloor` đơn giản. Với bản ghi dài biến thiên:

\[
\boxed{
H + q\cdot S + \sum_{i=1}^{q}len(record_i)\le P
}
\]

trong đó `S` là số byte cho mỗi slot, `q` là số record trong page.

Ví dụ header `H=96`, slot `S=4`, trang `P=4096`, các payload có độ dài lần lượt `120,60,200,80` byte:

\[
96+4\cdot4+(120+60+200+80)=572\text{ byte}.
\]

Trang vẫn còn `4096-572=3524` byte **theo tổng dung lượng**. Tuy nhiên, nếu đã từng xóa/chèn nhiều lần, vùng trống liền mạch có thể ít hơn.

### Bản ghi vượt một trang

Nếu một record có payload lớn hơn sức chứa một page, những triển khai thực tế có thể:

- Đặt phần record trong trang và phần còn lại ở overflow page.
- Lưu một pointer tới large object đặt riêng.
- Dùng dạng record với các trường dài biến thiên được tách.

Mỗi lựa chọn ảnh hưởng số I/O khi đọc record đầy đủ. Khi phân tích `B` record/page, cần xem **record lớn và overflow** có làm mất giả định sức chứa cố định hay không.

### Nén và prefix compression

Nếu khóa dài có prefix chung, một số index page có thể **nén tiền tố** để chứa nhiều khóa hơn. Điều này làm fanout tăng và giảm I/O, nhưng cần CPU để giải mã/so sánh, có thể làm cập nhật page phức tạp hơn.

Không thể suy fanout chính xác chỉ từ `P` nếu chưa biết **cách mã hóa key, pointer và metadata**.

## 7. Internal page của B+ tree: khóa phân cách và child pointers

Khác với leaf page, internal page thường chứa các **khóa phân cách** và con trỏ tới những trang con.

```text
Node nội bộ:

 child0 | key0 | child1 | key1 | child2 | key2 | child3
         /             /              /
    khóa phân cách, mỗi child dẫn đến một miền khóa.
```

Với `k` khóa phân cách của internal node nhị phân mở rộng, thường có `k+1` child pointers. Nếu:

- Page `P` byte.
- Header `H` byte.
- Mỗi khóa `K_s` byte.
- Mỗi child pointer `C_s` byte.

thì mô hình bố trí mảng đơn giản yêu cầu:

\[
\boxed{
H+kK_s+(k+1)C_s\le P.
}
\]

Suy ra:

\[
\boxed{
k_{\max}=
\left\lfloor\frac{P-H-C_s}{K_s+C_s}\right\rfloor,
\quad
F_{\max}=k_{\max}+1.
}
\]

### Ví dụ 4 KiB

Giả định:

```text
P=4096 byte
H=96 byte
K_s=16 byte/khóa
C_s=8 byte/child pointer
```

\[
k_{\max}=\left\lfloor\frac{4096-96-8}{16+8}\right\rfloor
=\lfloor3992/24\rfloor=\boxed{166}.
\]

Số nhánh tối đa `F_{\max}=167`. Kiểm tra:

\[
96+166\cdot16+167\cdot8=4088\le4096.
\]

**Lưu ý:** ví dụ giả định header chứa toàn bộ metadata khác, không có slot riêng/fragmentation, khóa và pointer cố định. Đây là **fanout tối đa theo kích thước lý thuyết**, không phải fanout hiệu dụng ở một index thực.

## 8. Leaf page: bản ghi hay con trỏ tới bản ghi?

Trong B+ tree, các lá giữ **khóa theo thứ tự**. Dữ liệu gắn với khóa có thể là:

1. **Bản ghi đầy đủ** (*clustered/index-organized storage* trong một số thiết kế).
2. **Cặp key → RID** trỏ sang heap file chứa bản ghi.
3. **Key cùng một số trường INCLUDE** để phục vụ các truy vấn *covering*.
4. **Danh sách posting/RID** nếu khóa có nhiều bản ghi trùng.

### Ví dụ index entry gọn

Giả định `P=4096` byte, `H=96` byte, mỗi leaf entry có:

- `16` byte key.
- `8` byte RID.
- `4` byte slot.

Một entry chiếm `28` byte:

\[
\boxed{L_{\max}=
\left\lfloor\frac{4096-96}{16+8+4}\right\rfloor
=\lfloor4000/28\rfloor
=142\text{ entry/page}.}
\]

### Nếu leaf chứa cả bản ghi dài 200 byte?

Khi leaf entry gồm key `16`, payload `200` và slot `4` byte:

\[
L_{\max}=\left\lfloor\frac{4000}{220}\right\rfloor
=18\text{ entry/page}.
\]

Số bản ghi/trang giảm mạnh. Đổi lại, một range scan có thể **lấy luôn dữ liệu từ leaf** mà không phải thực hiện thêm lookup vào bảng gốc.

### Hai thiết kế cần cân nhắc

- **Entry nhỏ:** cây gọn, fanout/leaf density cao, nhưng trả về full record có thể cần I/O khác.
- **Entry lớn/covering:** ít entry mỗi trang hơn, nhưng một số truy vấn tránh đọc các trang dữ liệu gốc.

Không có một lựa chọn tối ưu cho mọi workload: phụ thuộc tỷ lệ truy vấn chỉ cần key, số trường cần trả, kích thước record, cập nhật và memory budget.

## 9. Fill factor: page hiếm khi luôn đầy 100%

**Fill factor** biểu thị tỷ lệ dung lượng hữu ích được sử dụng khi xây hoặc tổ chức page, nhưng định nghĩa cụ thể khác nhau giữa các engine.

Với ví dụ leaf chứa tối đa `142` entry, nếu mục tiêu lấp đầy là `70\%`:

\[
\text{target entries}\approx\lfloor0.70\cdot142\rfloor
=\boxed{99}.
\]

Để chừa chỗ cho các lần chèn sau, page có thể chỉ được nạp khoảng 99 entry thay vì 142 entry.

### Hệ quả đối với range scan

Muốn đọc `K=1000` entry liên tục:

- Nếu mọi leaf đều có `142` entry phù hợp và bắt đầu ở biên leaf: cần ít nhất `\lceil1000/142\rceil=8` leaf pages.
- Nếu mỗi leaf chỉ có `99` entry và bắt đầu ở biên leaf: cần ít nhất `\lceil1000/99\rceil=11` leaf pages.

Số trên chỉ là **ví dụ dung lượng**, không phải cam kết mọi scan có đúng 8 hoặc 11 reads: vị trí bắt đầu có thể nằm giữa leaf, trang có thể không đều, và cache có thể hit.

### Fill factor và chi phí cập nhật

Lấp đầy quá cao có thể khiến insert thường phải split, tăng số trang và write amplification. Để nhiều khoảng trống giúp insert thuận lợi hơn, nhưng làm chỉ mục lớn hơn, tăng số trang phải quét và có thể tăng chiều cao khi số nút đủ lớn.

Đó là một **đánh đổi đọc–ghi–dung lượng**, cần benchmark theo tỷ lệ insert, delete, point lookup và range scan thực tế.

## 10. Fanout và chiều cao: một page loại bỏ nhiều miền khóa

Giả sử số nhánh hiệu dụng của internal node là `F` và các lá chứa khoảng `L` entry. Một cây cân bằng có thể bao phủ số entry cỡ:

\[
\boxed{N\lesssim L\cdot F^{h-1}}
\]

với `h` là **số cấp trang trên đường từ root đến leaf**, giả định các trang internal đầy đủ và mọi leaf chứa gần `L` entry.

Do đó:

\[
\boxed{
h\approx1+\left\lceil\log_F\left(\frac{N}{L}\right)\right\rceil
}
\]

cho mô hình đầy lý tưởng khi `N>L`; nếu `N\le L` có thể chỉ cần một leaf root. Cách viết chặt tránh log âm:

\[
\boxed{
h_{\mathrm{ideal}}=
1+\left\lceil\log_F\max(1,N/L)\right\rceil
}
\]

trong mô hình số cấp tối thiểu với root có thể là leaf.

### Ví dụ 1.000.000 entry

Giả định `F=167`, `L=142`:

```text
1 leaf:           142 entry
1 internal + lá:  167 * 142 = 23.714 entry
Root + tầng giữa + lá:
                  167 * 167 * 142 = 3.960.238 entry
```

Để chứa 1.000.000 entry, mô hình đầy lý tưởng cần **3 cấp trang** root → internal → leaf. Nhưng thực tế có thể có fill factor thấp, key/pointer biến độ dài, phân phối trang không đều và mức root/internal luôn khác mức lấp đầy.

### Chiều cao không đồng nghĩa số physical reads trong mọi truy vấn

Nếu root và một số internal pages đã nằm trong RAM buffer, một point lookup có thể chỉ tạo **một leaf page miss**, hoặc **0 device reads** nếu leaf đã cache. `O(\log_F N)` là cận cấu trúc/cold path trong mô hình trang, không phải số lần truy cập SSD bắt buộc với cache nóng.

## 11. Từ point lookup đến range scan: hai giai đoạn khác nhau

Một truy vấn theo khoảng khóa `[lo,hi]` trên B+ tree thường gồm:

**Giai đoạn A — định vị trang lá đầu tiên:** đi root → internal pages → leaf chứa khóa đầu đoạn.

**Giai đoạn B — quét kết quả theo thứ tự khóa:** từ leaf đầu, đọc các entry đủ điều kiện rồi di chuyển sang leaf tiếp theo.

```text
                          Root
                           |
             tìm lá chứa khóa bắt đầu
                           v
     [leaf A] -> [leaf B] -> [leaf C] -> [leaf D]
         |          |          |
        (lo)      kết quả    (hi)

       Quét từ khóa lo đến khóa hi.
```

Không phải quay về root cho **mỗi khóa kế tiếp** nếu leaf pages có liên kết/cursor theo thứ tự hợp lệ. Đây là lợi ích nổi bật của B+ tree cho range scan.

### Nếu mỗi leaf giữ `L` entry

Khi có `K` entry cần trả và các leaf có lấp đầy được chặn dưới hợp lý, số leaf pages liên quan có dạng:

\[
\boxed{O(1+K/L)}
\]

với `L` hiểu là **bậc dung lượng/độ lấp đầy hiệu dụng** của các lá trong miền truy vấn.

Phần tìm trang đầu tốn `O(\log_F N)` page accesses, nên tổng:

\[
\boxed{
T_{\mathrm{range}}
=O\left(\log_F N+1+\frac{K}{L}\right)
}
\]

cho phần **duyệt index leaf entries** trong mô hình trang. Nếu bản ghi cần trả không nằm ở index, còn chi phí tìm fetch payload ở bảng gốc.

### Cận cho đoạn nằm giữa một leaf

Ngay cả `K=1`, một truy vấn lạnh vẫn có thể phải đọc leaf chứa entry ấy. Hạng `+1` nhắc rằng **số lần đọc trang là số nguyên** và biên của khoảng có thể chạm thêm trang.

## 12. Truy cập leaf đầu và leaf cuối lệch biên trang

Giả sử leaf pages mỗi trang chứa đúng `L=4` entry liên tiếp theo thứ tự:

```text
Leaf 0: [0,1,2,3]
Leaf 1: [4,5,6,7]
Leaf 2: [8,9,10,11]
```

Đọc `K=6` entry bắt đầu tại vị trí `s=3`:

```text
3 | 4,5,6,7 | 8
^     ^       ^
page0 page1   page2

Tổng: 3 leaf pages.
```

Nếu bắt đầu ở `s=4`:

```text
4,5,6,7 | 8,9
   ^         ^
 page1     page2

Tổng: 2 leaf pages.
```

Với trang đầy đều `L` entry và `K>0`:

\[
\boxed{
\#leafPages(s,K)
=\left\lfloor\frac{s+K-1}{L}\right\rfloor
-\left\lfloor\frac{s}{L}\right\rfloor+1.
}
\]

Đây là **công thức cho mảng entry đặt đều và liên tiếp**, không áp dụng trực tiếp cho B+ tree thật có các leaf độ lấp đầy khác nhau hoặc record có độ dài biến thiên. Nhưng nó giúp hiểu vì sao **đầu/cuối đoạn lệch biên** có thể thêm một lượt đọc trang.

## 13. Logic liên tiếp chưa chắc vật lý liên tiếp

Trong B+ tree, liên kết:

```text
leaf A.next -> leaf B.next -> leaf C.next
```

thường bảo đảm **thứ tự khóa logic** giữa các lá. Điều đó **không bảo đảm** page A/B/C nằm ở **ba block liền kề vật lý** trên SSD/HDD.

Ví dụ:

```text
Thứ tự khóa:       leaf A -> leaf B -> leaf C -> leaf D
Số hiệu trang:     17        804        41        300
```

Đọc tuần tự theo **khóa** có thể vẫn là nhiều lần I/O ngẫu nhiên theo **địa chỉ vật lý**, đặc biệt khi các trang bị tách/chuyển sau nhiều lần cập nhật.

### Vì sao bố trí vật lý quan trọng?

- **HDD:** chuyển vị trí đầu đọc và quay đĩa khiến random I/O đắt.
- **SSD:** không có seek cơ học nhưng vẫn có giới hạn IOPS/latency của request nhỏ, còn request lớn hoặc đa luồng có thể tận dụng băng thông tốt hơn.
- **Filesystem/FTL:** địa chỉ page logic không chắc ánh xạ liền sang block vật lý.

### Các tối ưu thường gặp

- **Clustering:** cố gắng đặt dữ liệu hay được quét cùng nhau gần nhau.
- **Read-ahead/prefetch:** nạp trước các trang được dự đoán sẽ dùng.
- **Batched I/O:** gộp các trang gần nhau vào request lớn.
- **Reorganization/compaction:** cải thiện thứ tự/bố trí hoặc giảm fragmentation theo thời gian.

Các cách này có chi phí riêng và không thể đảm bảo mọi truy vấn chỉ cần một request vật lý. Phải phân biệt **số trang logic cần xét** với **số request/byte trên thiết bị**.

## 14. Clustered và unclustered index: quét leaf chưa phải toàn bộ câu chuyện

Giả sử chỉ mục lá chứa `(key,RID)` và truy vấn yêu cầu trả cả trường `name,address` nằm trong **bảng dữ liệu gốc**.

```text
B+ tree index leaf theo key:
   (10,RID-A) (11,RID-B) (12,RID-C) ...
       |         |         |
       v         v         v
    page 900   page 12   page 541   (các record gốc)
```

Dù index entries nằm liên tiếp theo khóa, những bản ghi gốc có thể **rải rác qua nhiều heap pages**.

### Unclustered secondary index

Với `K` kết quả, trường hợp xấu có thể:

- Đọc cỡ `O(\log_F N+1+K/L)` trang **index**.
- Đọc thêm tới `O(K)` trang **data** khi mỗi RID dẫn tới một trang gốc khác nhau chưa cache.

Hệ quả: quét 10.000 khóa trên index có thể chỉ cần vài chục leaf page reads, nhưng việc lấy đầy đủ 10.000 records có thể tạo hàng nghìn page misses khác.

### Clustered index / dữ liệu được gom theo thứ tự khóa

Nếu bản ghi gốc được sắp gần theo khóa (hoặc leaf chứa trực tiếp dữ liệu), một range scan có thể đọc những trang data gần nhau; số trang bổ sung tiến tới mức theo **dung lượng mỗi trang dữ liệu** thay vì một trang cho mỗi bản ghi.

### Covering index

Nếu index chứa **tất cả những cột mà truy vấn cần trả**, hệ thống có thể thực hiện **index-only scan**, tránh lookup bảng gốc khi các điều kiện visibility/transaction cho phép.

Ví dụ:

```text
INDEX(key, timestamp) INCLUDE(name)

Truy vấn cần key, timestamp, name:
  có thể trả từ index.

Truy vấn còn cần address không nằm trong index:
  thường phải đọc thêm record gốc.
```

**Lưu ý:** “covering” về cột chưa chắc đủ cho mọi engine: một số hệ cần kiểm tra trạng thái hiển thị MVCC ở bảng gốc nếu thông tin visibility chưa sẵn hoặc không được xác nhận ở cấp trang.

### Kết luận

Phân tích range scan phải trả lời: **đọc index entries thôi, hay phải đọc toàn bộ records?** Nếu không làm rõ, công thức `O(K/L)` có thể đánh giá thiếu chi phí lớn nhất của truy vấn.

## 15. Ví dụ số: range scan 1.000 kết quả

Xét một B+ tree có:

```text
Số entry:                  N = 1.000.000
Internal fanout giả định:  F = 167
Leaf capacity tối đa:      Lmax = 142
Leaf occupancy thực:       ~99 entry/page
Số kết quả cần trả:        K = 1.000
Root/internal pages:       giả định 3 cấp tổng cộng
```

### Chi phí tìm điểm bắt đầu

Với cây **3 cấp** root → internal → leaf, đường tìm lạnh hoàn toàn có thể cần **3 page reads**. Nếu root và internal đã cache trong RAM thì có thể chỉ cần **1 leaf read**, thậm chí 0 nếu leaf cũng đã cache.

### Chi phí scan leaf

Nếu bắt đầu **đúng đầu một leaf** và các leaf chứa đúng 99 entry:

\[
\left\lceil\frac{1000}{99}\right\rceil
=11\text{ leaf pages}.
\]

Nếu bắt đầu **ở entry cuối cùng của một leaf**:

\[
\left\lceil\frac{98+1000}{99}\right\rceil
=12\text{ leaf pages}.
\]

Leaf page đầu tiên **đã được đọc trong đường tìm**. Vì vậy, khi tính tổng số pages mới cần nạp, **không cộng 3 page tìm đầu và lại cộng đủ 11 leaf pages như thể leaf đầu chưa được đọc**.

Với ví dụ 11 leaf pages đầy đủ theo mức 99 entry:

- Root + internal = 2 page reads.
- 11 leaf pages chứa kết quả = 11 page reads.
- Tổng đọc index lạnh ≈ **13 page reads**, không phải 14.

Số thực phụ thuộc hit cache và có thể thêm trang metadata hoặc overflow trong thiết kế khác.

### Trường hợp index không covering

Nếu 1.000 records nằm trên 1.000 heap pages khác nhau và đều lạnh, có thể cần **khoảng 1.000 reads bổ sung**. Tổng đọc index chỉ là một phần nhỏ của toàn truy vấn.

Nếu records được cluster cùng nhau và page dữ liệu chứa `D=40` records theo thứ tự truy vấn, phần đọc bảng có thể giảm xuống cỡ:

\[
\left\lceil\frac{1000}{40}\right\rceil=25
\]

data pages (khi bắt đầu ở biên page và layout phù hợp).

**Thông điệp:** locality của **payload gốc** quan trọng không kém locality của các leaf index.

## 16. Quét tuần tự: khi nào bắt đầu và dừng?

Một range scan đúng phải xử lý cả các ca:

- Không có khóa nào trong khoảng `[lo,hi]`.
- Khóa `lo` không tồn tại: bắt đầu từ khóa đầu tiên **lớn hơn `lo`**.
- Khóa `hi` không tồn tại: dừng ở entry đầu tiên **lớn hơn `hi`**.
- Một leaf không đủ chứa hết kết quả: đi tiếp leaf kế bên.
- Nhiều entry có **khóa bằng nhau**: không bỏ sót bản ghi hợp lệ ở ranh giới leaf.
- `lo>hi`: từ chối hoặc trả rỗng theo hợp đồng API.

### Mã giả

```text
RANGE_SCAN(root, lo, hi):
    if lo > hi:
        return empty

    leaf = FIND_FIRST_LEAF_WITH_KEY_AT_LEAST(lo)
    while leaf != null:
        PAGE = READ_OR_PIN(leaf)
        for entry in PAGE.entries_in_key_order:
            if entry.key < lo:
                continue
            if entry.key > hi:
                UNPIN(PAGE)
                return
            emit(entry)
        leaf = PAGE.next_leaf
        UNPIN(PAGE)
```

**Chú ý vòng đời page pin:** nếu cần đọc `next_leaf` từ page hiện tại, phải lấy ID con trỏ trước khi unpin hoặc bảo đảm reference vẫn hợp lệ. Một engine thật cũng phải xử lý các trang đang split, xóa và thay đổi theo transaction, không chỉ chuyển một con trỏ từ page này sang page tiếp.

### Bài toán duplicate keys

Nếu leaf được phân tách tại ranh giới có các khóa bằng nhau, cùng một key có thể xuất hiện ở nhiều leaf. Thuật toán `FIND_FIRST_LEAF_WITH_KEY_AT_LEAST(lo)` phải đưa con trỏ tới **bản ghi đầu tiên hợp lệ theo thứ tự index**.

Trong index composite `(key,RID)` hoặc `(key,unique_id)`, có thể định nghĩa thứ tự toàn phần và dùng *lower_bound* của `(lo,-\infty)`. Nếu chỉ tìm **một leaf bất kỳ chứa `lo`**, scan có thể bỏ sót bản ghi bằng `lo` ở leaf trước.

## 17. Read-ahead và prefetch: che giấu độ trễ khi quét lá

Nếu ta biết leaf `A` sẽ được nối tới leaf `B`, hệ thống có thể **nạp trước** `B` vào RAM trong lúc CPU đang xử lý entries của `A`.

```text
Thời gian
  ------------------------------------------------>
  Đọc A        Xử lý A
                    \________
                     prefetch B ----> B sẵn khi cần
```

### Prefetch có thể cải thiện điều gì?

- Giảm thời gian **chờ** mỗi lần chuyển page.
- Cho phép một số I/O đang chờ cùng lúc.
- Tăng thông lượng của quét dài nếu thiết bị có khả năng song song và bandwidth phù hợp.

### Nhưng không phải lúc nào cũng giảm số block I/O

Nếu tất cả các page đều thực sự cần đọc, prefetch chỉ thay đổi **thời điểm** đọc và khả năng **chồng lấp latency**, không xóa bớt số trang bắt buộc phải xem.

Prefetch quá xa còn có thể:

- Đẩy các trang nóng khác khỏi buffer pool.
- Đọc cả trang nằm **ngoài biên kết quả** khi scan sớm kết thúc.
- Tăng I/O, bộ nhớ và tranh chấp với workload khác.

### Read-ahead theo vật lý hay theo cây?

Nếu các leaf nằm liền vùng file, OS/device có thể nhận ra đọc tuần tự và read-ahead hiệu quả. Nếu leaf page IDs rải rác, scan logic vẫn có thể prefetch **theo next_leaf** nhưng việc gộp thành request vật lý lớn khó hơn.

Lợi thế “quét liên tiếp” vì thế có hai lớp: **liên tiếp logic theo khóa** và **liên tiếp vật lý theo layout**.

## 18. Cache pin/unpin và eviction khi quét

Một **buffer pool** của database giữ các page đang sử dụng trong RAM. Một page có thể có:

- **pin count / latch state:** page đang được dùng, không thể tùy tiện evict.
- **dirty bit:** page đã được sửa, cần write-back theo chính sách.
- **replacement metadata:** recency/frequency hoặc vòng clock.

### Truy cập trong range scan

Quy trình giản lược:

```text
pin(page_id)
  -> nếu hit: dùng page trong RAM
  -> nếu miss: chọn victim, đọc page vào RAM
  -> xử lý entries
  -> ghi nhớ next_page
unpin(page_id)
  -> page có thể được thay thế về sau
```

Nếu chỉ giữ một leaf pinned ở mỗi bước, một scan dài có thể hoạt động với **ít bộ nhớ trong**. Nếu dùng prefetch, cần thêm một số buffer cho các leaf đang nạp.

### Scan lớn có thể làm bẩn cache theo nghĩa “cache pollution”

Một lần scan hàng triệu page có thể đẩy root/internal pages hoặc các page nóng của truy vấn khác khỏi buffer pool nếu chính sách eviction không phân biệt trang quét một lần với trang truy cập lặp.

Nhiều hệ thống dùng **scan-resistant replacement**, phân khu cache, hoặc cách đánh dấu truy cập tuần tự để giảm tác dụng phụ. Không nên tối ưu scan đơn lẻ mà bỏ qua hiệu quả của toàn bộ hệ thống.

### Dirty leaf page

Nếu scan chỉ đọc, nó **không nên tự làm dirty page**. Nếu scan đồng thời thực hiện update, việc đánh dấu dirty và flush phải tuân theo giao thức ghi, logging và concurrency của engine.

## 19. Split leaf khi chèn vào trang đã đầy

Giả sử một leaf chứa các khóa đã sắp:

```text
Leaf A (đầy): [10, 20, 30, 40, 50, 60]
Chèn khóa 35.
```

Một cách xử lý là **leaf split**:

1. Tạo một leaf mới `B`.
2. Phân phối các entry thành hai nhóm theo thứ tự:

   ```text
   Leaf A: [10, 20, 30]
   Leaf B: [35, 40, 50, 60]
   ```

3. Cập nhật liên kết giữa các leaf, ví dụ `A.next=B` và `B.next=old_next`.
4. Đưa **separator key** phù hợp (thường là khóa đầu của leaf bên phải trong mô hình B+ tree đơn giản) lên trang cha.
5. Nếu cha đầy, tiếp tục split lên trên; có thể tạo gốc mới.

### Chi phí I/O

Một lần insert có thể đụng:

- Trang lá bị cập nhật.
- Trang lá mới.
- Trang cha được sửa separator/child pointer.
- Một số trang tổ tiên nếu split lan lên.
- Trang metadata/allocator, WAL và các bước ghi bền vững.

Vì vậy, “insert chỉ ghi một page” không đúng trong mọi trường hợp. Hình thức phân tích chuẩn xét `O(h)` page touches khi split lan theo đường gốc–lá, với `h` là chiều cao cây.

### Mục tiêu split không chỉ là chia đúng số entry

Với record dài biến thiên, cần chia theo **byte occupancy**, không chỉ số record, để cả hai trang đều vừa. Split gần giữa theo **số byte** và duy trì key-order có thể hợp lý hơn split đúng giữa theo số entry.

## 20. Delete, underflow, redistribution và merge

Xóa một entry có thể làm leaf thưa. Có một số cách xử lý:

**Redistribution:** mượn một số entry từ leaf anh em, cập nhật khóa phân cách ở cha.

**Merge:** hợp nhất hai leaf khi tổng payload/entry vừa một page, rồi xóa liên kết con tương ứng trong cha.

**Deferred cleanup:** trì hoãn việc dồn trang, có thể giảm chi phí mỗi lần xóa nhưng để lại nhiều page thưa và tăng chi phí scan.

### Ví dụ

```text
Trước xóa:
 Leaf A: [10,20]       Leaf B: [30,40]

Sau xóa 10,20:
 Leaf A: []            Leaf B: [30,40]

Có thể bỏ leaf A, cập nhật cha/links,
hoặc giữ lại tạm thời tùy chính sách.
```

Một hệ thống thật phải duy trì **bất biến lấp đầy tối thiểu** của biến thể B-tree (nếu có), cập nhật separator keys, sibling links và đảm bảo không làm đứt đường scan của transaction đang chạy.

### Hiệu quả scan sau nhiều lần xóa

Nếu nhiều leaf còn sống nhưng chỉ chứa vài entry, muốn trả `K` records có thể phải đọc **nhiều leaf pages** hơn so với trạng thái gần đầy. Vì thế, kiểm soát fragmentation và occupancy là vấn đề hiệu năng **range scan**, không chỉ vấn đề dung lượng.

## 21. Slotted page compaction khác B+ tree merge

Hai thuật ngữ này dễ bị nhầm:

**Compaction nội trang:** dồn các payload **trong cùng một page**, đổi offset trong slot directory để thu hồi khoảng trống liên tục. Không nhất thiết thay đổi page ID hoặc số leaf pages.

**Merge hai trang cây:** chuyển nhiều entry từ hai page vào một page, cập nhật các liên kết index/parent/leaf chain, có thể giải phóng một page.

Ví dụ:

```text
Compaction:
 Page A: [record X][hole][record Y] -> [record X][record Y][free]

Merge:
 Page A: [10,20]   Page B: [30,40]
      -> Page A: [10,20,30,40], bỏ Page B
```

### Hai loại ID có thể bị ảnh hưởng khác nhau

Compaction có thể giữ nguyên `(page_id,slot_id)` nếu slot vẫn trỏ đúng record sau khi di chuyển byte nội trang.

Merge page thay đổi **page ID của các record chuyển chỗ** trong thiết kế RID vật lý, nên có thể cần sửa mọi tham chiếu tương ứng, forwarding pointer hoặc một lớp định danh logic ổn định.

Không được tuyên bố “compaction luôn O(1)” hoặc “merge luôn chỉ sửa một con trỏ”: phải tính lượng byte sao chép, cập nhật metadata và I/O theo thuật toán cụ thể.

## 22. Đồng thời: scan và split có thể diễn ra cùng lúc

Một range scan có thể đang đi theo liên kết leaf:

```text
Scan đang ở A -> dự định sang B.
Thread khác chèn, B split thành B và C.
```

Nếu dùng mã duyệt con trỏ không có giao thức đồng bộ, scan có thể:

- Bỏ sót một số entry mới.
- Nhìn cùng entry hai lần.
- Theo con trỏ page đã bị giải phóng hoặc tái sử dụng.
- Đọc metadata trang chưa cập nhật đầy đủ.

### Những cơ chế thường được dùng

- **Latches** bảo vệ sửa cấu trúc trang trong lúc người khác đọc/sửa.
- **Latch coupling / crabbing** hoặc các biến thể B-link tree để đi qua các trang an toàn.
- **High-key và right sibling link** giúp định hướng khi page split.
- **MVCC/snapshot** để xác định tập bản ghi nào hiển thị đối với một transaction.
- **Cursor validation/restart** khi cấu trúc thay đổi trong lúc scan.

### Latch khác lock giao dịch

Latch thường bảo vệ **tính nhất quán vật lý của dữ liệu trong page/cấu trúc** trong khoảng rất ngắn. Lock giao dịch hoặc quy tắc MVCC bảo vệ **tính nhất quán logic/isolation** ở mức truy vấn. Có latch đúng chưa đủ để đảm bảo một scan nhìn thấy snapshot logic mong muốn.

Bài này tập trung vào **bố trí page và số I/O**, không triển khai engine đồng thời; muốn dùng trong database thật phải thiết kế thêm những giao thức trên.

## 23. Recovery: thứ tự ghi trang và nhật ký

Khi sửa leaf, việc thay đổi có thể gồm:

```text
leaf A: sửa entries
leaf B: thêm trang mới
parent: thêm separator
leaf chain: cập nhật next/prev
```

Nếu hệ thống mất điện giữa các bước, chỉ một phần cập nhật có thể được ghi bền vững. Cấu trúc cây trên đĩa có nguy cơ **mâu thuẫn liên kết hoặc mất dữ liệu** nếu thiếu giao thức recovery.

### Write-ahead logging (WAL)

Trong nhiều thiết kế database, trước khi ghi một trang dữ liệu dirty xuống thiết bị, những log record cần thiết mô tả thay đổi của trang phải được **ghi bền vững** theo quy tắc WAL.

Các page có thể lưu **LSN** hoặc metadata tương tự để recovery phân biệt thay đổi đã được áp dụng. Các thuật toán split/merge có thể cần cơ chế redo/undo phù hợp với thiết kế.

### Vì sao quan trọng đối với I/O count?

Một insert vừa gây **page writes**, vừa có thể gây **log writes**, checksum, flush và metadata updates. Cận `O(h)` page touches chỉ mô tả **thao tác cấu trúc cơ bản**, không tính toàn bộ chi phí durability của một transaction.

**Đừng hiểu “ghi một trang” trong mô hình I/O là đồng nghĩa “đã commit bền vững và khôi phục an toàn”.**

## 24. Thiết kế node theo byte thay vì số phần tử cố định

Nếu các khóa và payload có độ dài biến thiên, một leaf có thể chứa `50` record ngắn hoặc chỉ `4` record lớn. Khi đó dùng `L=100` entry/page cho toàn bộ phân tích sẽ đánh giá sai.

Một page layout nên theo dõi ít nhất:

- `page_size`.
- `header_size`.
- `slot_count` và kích thước mỗi slot.
- `free_start`, `free_end` hoặc metadata vùng trống.
- Số byte payload còn sống.
- Fragmentation (byte đã xóa nhưng chưa thu hồi thành vùng trống liền mạch).

### Điều kiện chèn có thể viết

Giả sử cần một **slot mới** dài `S` byte và payload mới dài `r` byte:

\[
\boxed{\text{contiguous_free}\ge S+r.}
\]

Nếu điều kiện không thỏa nhưng tổng byte trống sau khi compact đủ, có thể compact rồi thử lại.

Nếu vẫn thiếu chỗ, một B+ tree leaf thường cần **split**, hoặc một engine khác có thể sử dụng overflow/out-of-line storage.

### Phân biệt size và count

Không thể nói “leaf đang chứa 90/100 record nên còn chỗ cho 10 record” nếu 10 record mới rất lớn. Đối với biến thể page chứa record dài biến thiên, **byte occupancy mới là bất biến quyết định**.

## 25. Pagination của kết quả quét: page dữ liệu khác page API

Một API có thể trả kết quả theo trang hiển thị:

```text
GET /records?limit=100&offset=100000
```

Chữ “page” trong API này nghĩa là **một nhóm 100 kết quả gửi cho client**, **không phải** database page `4 KiB`.

### OFFSET lớn

Để lấy 100 kết quả sau 100.000 kết quả đầu, nhiều kế hoạch thực thi phải **duyệt/bỏ qua một lượng lớn entry** trước khi trả kết quả. Dù B+ tree hỗ trợ range scan hiệu quả theo trang lưu trữ, `OFFSET` lớn vẫn có thể có chi phí tỷ lệ với số entry bị bỏ.

### Keyset/cursor pagination

Nếu dữ liệu có thứ tự ổn định theo `(key,unique_id)`, có thể gửi khóa cuối đã đọc:

```text
WHERE (key, unique_id) > (:last_key, :last_id)
ORDER BY key, unique_id
LIMIT 100
```

Động tác tiếp theo là **seek** tới vị trí mới rồi scan 100 entries, không phải quét/bỏ qua 100.000 entries từ đầu.

Tuy nhiên, dữ liệu cập nhật đồng thời có thể khiến các page kết quả qua nhiều request thay đổi. Nếu cần một snapshot thống nhất, phải có transaction/versioning hoặc semantics thích hợp.

**Không trộn “API page of results” với “storage page of bytes” trong phân tích độ phức tạp I/O.**

## 26. Python: mô phỏng một slotted page có record dài biến thiên

Ví dụ này mô phỏng **đơn vị byte và slot nội trang**. Nó là mô hình trên `bytearray` Python, **không phải database engine hoặc file thật**, không có concurrency, WAL, checksum hay crash recovery.

Quy ước:

- `page_size`: tổng byte của page.
- `header_size`: số byte header được **dành chỗ**.
- `slot_size`: byte cho mỗi slot (giả định hằng số).
- Metadata slot được mô phỏng bằng Python list, đồng thời được **tính chi phí kích thước logic** vào page.
- Payload bắt đầu ở cuối page và phát triển về trái.
- Slot directory bắt đầu sau header và phát triển về phải.

### 26.1. Khai báo record slot và page

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Slot:
    offset: int
    length: int


class SlottedPage:
    """Mô phỏng layout byte, không ghi trực tiếp xuống thiết bị."""

    def __init__(
        self,
        page_size: int = 256,
        header_size: int = 32,
        slot_size: int = 4,
    ) -> None:
        if not (0 < header_size < page_size):
            raise ValueError("Header/page size không hợp lệ")
        if not 0 < slot_size < page_size:
            raise ValueError("Slot size phải dương")

        self.page_size = page_size
        self.header_size = header_size
        self.slot_size = slot_size
        self.data = bytearray(page_size)
        self.slots: list[Slot | None] = []
        self.free_end = page_size

    def free_contiguous(self) -> int:
        directory_end = (
            self.header_size + len(self.slots) * self.slot_size
        )
        return self.free_end - directory_end

    def live_payload_bytes(self) -> int:
        return sum(
            slot.length for slot in self.slots if slot is not None
        )

    def get(self, slot_id: int) -> bytes:
        if not 0 <= slot_id < len(self.slots):
            raise IndexError(slot_id)
        slot = self.slots[slot_id]
        if slot is None:
            raise KeyError("Slot đã bị xóa")
        return bytes(self.data[slot.offset:slot.offset + slot.length])

    def delete(self, slot_id: int) -> None:
        # Chỉ đánh dấu slot; byte payload cũ chưa được thu hồi.
        self.get(slot_id)  # xác minh slot tồn tại, chưa bị xóa
        self.slots[slot_id] = None

    def compact(self) -> None:
        """Dồn payload còn sống, giữ nguyên slot ID."""
        new_data = bytearray(self.page_size)
        new_slots: list[Slot | None] = []
        end = self.page_size

        for slot in self.slots:
            if slot is None:
                new_slots.append(None)
                continue
            payload = bytes(
                self.data[slot.offset:slot.offset + slot.length]
            )
            end -= len(payload)
            new_data[end:end + len(payload)] = payload
            new_slots.append(Slot(end, len(payload)))

        self.data = new_data
        self.slots = new_slots
        self.free_end = end

    def insert(self, payload: bytes) -> int:
        if not isinstance(payload, bytes) or not payload:
            raise ValueError("Payload phải là bytes không rỗng")

        # Bản minh họa luôn cấp slot mới, không tái sử dụng slot None.
        need = len(payload) + self.slot_size
        if self.free_contiguous() < need:
            self.compact()
        if self.free_contiguous() < need:
            raise OverflowError("Trang không còn đủ chỗ")

        self.free_end -= len(payload)
        start = self.free_end
        self.data[start:start + len(payload)] = payload
        slot_id = len(self.slots)
        self.slots.append(Slot(start, len(payload)))
        return slot_id

    def check_invariants(self) -> bool:
        directory_end = (
            self.header_size + len(self.slots) * self.slot_size
        )
        if not directory_end <= self.free_end <= self.page_size:
            return False
        intervals: list[tuple[int, int]] = []
        for slot in self.slots:
            if slot is None:
                continue
            lo = slot.offset
            hi = slot.offset + slot.length
            if not (self.free_end <= lo < hi <= self.page_size):
                return False
            intervals.append((lo, hi))

        intervals.sort()
        for i in range(1, len(intervals)):
            if intervals[i - 1][1] > intervals[i][0]:
                return False
        return True
```

### Những điểm quan trọng trong mã

1. `get(slot_id)` dùng slot để đọc payload nên **offset vật lý có thể đổi** sau compaction mà ID không đổi.
2. `delete` chỉ đánh dấu slot `None`; free space liên tục không tăng ngay.
3. `compact` dồn lại các payload đang sống, giữ nguyên vị trí logic trong mảng slot.
4. `insert` tính đúng cả **bytes mới + slot mới**. Khi thiếu vùng trống liền mạch, compact một lần rồi thử lại.
5. `check_invariants` xác minh vùng slot và payload không chồng lên nhau, offset hợp lệ và các payload sống không đè lên nhau.

### Giới hạn cố ý

Mã **không ghi nội dung slot directory bằng bytes vào page**, chỉ dành chỗ logic cho chúng. Vì vậy đây là **mô phỏng sức chứa/bố trí**, không phải định dạng lưu trữ nhị phân tương thích giữa các hệ thống.

Nó cũng **không tái sử dụng slot bị xóa**: sau quá nhiều lượt insert/delete, slot directory có thể lớn dần dù còn payload trống. Một bản production thường quản lý free-slot list, slot generation, fragmentation và garbage collection.

## 27. Python: thử xóa, compaction và chèn giữa một page

Dùng lớp `SlottedPage` từ phần 26:

```python
page = SlottedPage(page_size=128, header_size=24, slot_size=4)

a = page.insert(b"A" * 20)
b = page.insert(b"B" * 30)
c = page.insert(b"C" * 15)

assert (a, b, c) == (0, 1, 2)
assert page.get(a) == b"A" * 20
assert page.get(c) == b"C" * 15
assert page.check_invariants()

print(page.free_contiguous())  # 27 byte.

page.delete(b)
assert page.check_invariants()
print(page.free_contiguous())  # Vẫn 27: chưa compact.

# Cần 40 byte payload + 4 byte slot, gap 27 không đủ.
# insert() sẽ compact tự động rồi chèn.
d = page.insert(b"D" * 40)

assert d == 3
assert page.get(a) == b"A" * 20
assert page.get(c) == b"C" * 15
assert page.get(d) == b"D" * 40
assert page.check_invariants()

print(page.free_contiguous())  # 13 byte.
```

### Kiểm tra số học

Ban đầu:

\[
24\text{ header}+3\cdot4\text{ slot}
+(20+30+15)\text{ payload}=101\text{ byte}.
\]

Khoảng trống liên tục:

\[
128-101=\boxed{27\text{ byte}}.
\]

Sau xóa payload 30 byte, nếu chưa compact thì **gap vẫn 27 byte**. Sau compact, còn `20+15=35` byte sống và vẫn có 3 slot:

\[
128-(24+12+35)=57\text{ byte gap}.
\]

Chèn payload mới 40 byte và slot 4 byte:

\[
57-44=\boxed{13\text{ byte gap}.}
\]

Không có dòng code nào trong ví dụ được coi là **I/O thiết bị**; đây là **phép tổ chức byte trong một page ở RAM**. Khi page đó được đọc từ/ghi về thiết bị mới phát sinh I/O ở tầng lưu trữ.

## 28. Python: mô phỏng linked leaf pages có khóa tăng dần

Để minh họa quét liên tiếp, ta xây một mô hình **chỉ giữ các leaf**, không triển khai toàn bộ internal B+ tree.

### Hợp đồng

- Input là các cặp `(key,value)`; key kiểu `int`.
- Các record được sắp theo key; **sort ổn định** giữ thứ tự input với khóa bằng nhau.
- Mỗi leaf chứa tối đa `per_leaf` entry; trong mô hình này entry tính **theo số mục**, không kiểm byte.
- Mỗi leaf có `next_page` để đi tới leaf kế tiếp theo thứ tự khóa.
- `max_keys` là metadata **đã ở RAM** để tìm leaf bắt đầu bằng binary search. Nó thay vai trò tìm kiếm root/internal pages nhưng **không tính I/O index nội bộ**.
- `LeafBuffer` là buffer LRU giả lập; `reads` đếm số leaf page misses.

### 28.1. Trang lá

```python
from bisect import bisect_left
from collections import OrderedDict
from dataclasses import dataclass


@dataclass
class LeafPage:
    page_id: int
    records: list[tuple[int, str]]
    next_page: int | None


class LeafBuffer:
    """Buffer pool mô phỏng: mỗi page miss = 1 leaf read."""

    def __init__(
        self, pages: list[LeafPage], capacity: int
    ) -> None:
        if capacity < 1:
            raise ValueError("Cần ít nhất một buffer page")
        self.pages = {page.page_id: page for page in pages}
        self.capacity = capacity
        self.cache: OrderedDict[int, LeafPage] = OrderedDict()
        self.reads = 0

    def load(self, page_id: int) -> LeafPage:
        if page_id in self.cache:
            self.cache.move_to_end(page_id)
            return self.cache[page_id]

        if len(self.cache) == self.capacity:
            self.cache.popitem(last=False)
        page = self.pages[page_id]
        self.cache[page_id] = page
        self.reads += 1
        return page
```

### 28.2. Xây chuỗi leaf và range scan

```python
class LeafChainIndex:
    def __init__(
        self, rows: list[tuple[int, str]], per_leaf: int
    ) -> None:
        if per_leaf < 1:
            raise ValueError("per_leaf phải >= 1")

        ordered = sorted(rows, key=lambda pair: pair[0])
        self.pages: list[LeafPage] = []
        self.max_keys: list[int] = []

        for start in range(0, len(ordered), per_leaf):
            chunk = ordered[start:start + per_leaf]
            page_id = len(self.pages)
            self.pages.append(LeafPage(page_id, chunk, None))
            self.max_keys.append(chunk[-1][0])

        for i in range(len(self.pages) - 1):
            self.pages[i].next_page = i + 1

    def range_scan(
        self, lo: int, hi: int, buffer: LeafBuffer
    ) -> list[tuple[int, str]]:
        """Trả tất cả entry có lo <= key <= hi."""
        if lo > hi:
            return []

        # Tìm TRANG ĐẦU TIÊN có max_key >= lo.
        # Dùng bisect_left để không mất duplicate qua biên page.
        pos = bisect_left(self.max_keys, lo)
        if pos == len(self.pages):
            return []

        result: list[tuple[int, str]] = []
        page_id: int | None = pos
        while page_id is not None:
            page = buffer.load(page_id)
            for key, value in page.records:
                if key < lo:
                    continue
                if key > hi:
                    return result
                result.append((key, value))
            page_id = page.next_page
        return result

    def check_invariants(self) -> bool:
        if len(self.max_keys) != len(self.pages):
            return False
        for i, page in enumerate(self.pages):
            if page.page_id != i or not page.records:
                return False
            if page.records != sorted(
                page.records, key=lambda pair: pair[0]
            ):
                return False
            if self.max_keys[i] != page.records[-1][0]:
                return False
            wanted_next = (
                i + 1 if i + 1 < len(self.pages) else None
            )
            if page.next_page != wanted_next:
                return False
            if i > 0 and self.max_keys[i - 1] > page.records[0][0]:
                return False
        return True
```

### Vì sao dùng `bisect_left(max_keys,lo)`?

`max_keys` là dãy **không giảm** khi các leaf đã được xếp theo khóa. Chỉ số đầu tiên có `max_key\ge lo` chính là leaf đầu tiên **có thể chứa khóa thỏa `key\ge lo`**.

Nếu khóa `lo` xuất hiện ở cả hai leaf liên tiếp, leaf trước có `max_key=lo` nên `bisect_left` chọn leaf trước. Nếu dùng `bisect_right`, ta có thể **bỏ qua các entry bằng `lo`** ở leaf trước.

Điểm này là một ví dụ quan trọng về **bất biến tìm lower bound** trong index có duplicate keys.

### Giới hạn của mô phỏng

`LeafChainIndex` chỉ minh họa range scan trên leaf chain. Nó **không phải B+ tree đầy đủ** vì không có internal nodes, không có xử lý insert/delete/split, không có disk persistence hoặc transaction isolation. Phép tìm trang đầu sử dụng `max_keys` trong RAM, nên **độ phức tạp I/O tìm gốc–lá của B+ tree thật không được tính ở đây**.

## 29. Python: kiểm tra chi phí quét liên tiếp và cache nóng/lạnh

```python
index = LeafChainIndex(
    [(i, f"value-{i}") for i in range(100)],
    per_leaf=10,
)
assert index.check_invariants()

small = LeafBuffer(index.pages, capacity=2)
answer = index.range_scan(25, 74, small)

assert [key for key, _ in answer] == list(range(25, 75))
assert len(answer) == 50
print(small.reads)  # 6 leaf page reads: leaf 2,3,4,5,6,7.

again = index.range_scan(25, 74, small)
assert again == answer
print(small.reads)  # 12: buffer 2 page không giữ được 6 leaf.

large = LeafBuffer(index.pages, capacity=10)
index.range_scan(25, 74, large)
index.range_scan(25, 74, large)
print(large.reads)  # 6: lượt thứ hai hit mọi leaf.

# Duplicate keys có thể nằm ở hai leaf khác nhau.
dups = LeafChainIndex(
    [(1, "A"), (1, "B"), (1, "C"),
     (2, "D"), (2, "E"), (3, "F")],
    per_leaf=2,
)
assert dups.check_invariants()
buf = LeafBuffer(dups.pages, capacity=2)
assert dups.range_scan(1, 1, buf) == [
    (1, "A"), (1, "B"), (1, "C")
]
```

### Giải thích `6` leaf reads

Mỗi leaf chứa đúng 10 khóa:

```text
leaf 2: 20..29  -> lấy 25..29
leaf 3: 30..39
leaf 4: 40..49
leaf 5: 50..59
leaf 6: 60..69
leaf 7: 70..79  -> lấy 70..74 rồi dừng tại 75
```

Tổng 50 kết quả, chạm 6 leaf pages.

Mô phỏng chỉ đếm **leaf buffer misses**, không đếm chi phí của `max_keys` hay đọc heap data pages, và page ID liên tiếp trong mã **không phải cam kết các page vật lý nằm sát nhau trên SSD/HDD**.

## 30. Row storage, column storage và range scan

Thiết kế page phù hợp còn phụ thuộc **các cột nào được đọc cùng nhau**.

### Row-oriented page

```text
Page 0:
  (id0, name0, age0, city0)
  (id1, name1, age1, city1)
  ...
```

Nếu truy vấn đọc **nguyên bản ghi** theo ID hoặc khoảng khóa, bố trí theo hàng có thể giảm số trang cần chạm để lấy đủ trường của một record.

### Column-oriented page

```text
Pages:
  id:   id0 id1 id2 ...
  age:  age0 age1 age2 ...
  city: city0 city1 city2 ...
```

Nếu truy vấn chỉ tính `AVG(age)` trên hàng triệu dòng, đọc riêng các page chứa cột `age` có thể tránh chuyển toàn bộ `name,city` không cần.

### Đánh đổi

| Workload | Layout thường đáng thử | Vì sao |
|---|---|---|
| Lấy đầy đủ một record theo khóa | Row-oriented | Các trường của record gần nhau |
| Quét một cột qua nhiều record | Column-oriented | Tránh đọc cột không dùng |
| Range scan theo khóa + trả vài cột | Covering index/column group | Giảm fetch payload không cần |
| Sửa thường xuyên cả record | Tùy schema và engine, row thường thuận tiện | Không cần đồng bộ nhiều cột rời |
| Phân tích tổng hợp rất lớn | Column, compression, vectorized scan | Tăng mật độ và băng thông hữu ích |

Đây là định hướng, không phải quy luật tuyệt đối. Compression, vectorization, số cột và cache/tần suất cập nhật có thể khiến một layout phù hợp hơn trong từng workload.

## 31. Quét khối theo thứ tự và vectorized processing

Với một page đã nằm trong RAM, tránh xử lý từng record qua một chuỗi lời gọi hàm và con trỏ không cần thiết nếu có thể **xử lý cả một batch**.

Ví dụ ý tưởng:

```text
for page in scan_pages():
    keys = decode_keys(page)        # giải mã cả nhóm
    mask = compare_range(keys)      # so sánh nhiều phần tử
    emit_selected(page, mask)
```

**Vectorization** có thể giảm overhead vòng lặp và tận dụng SIMD/hardware prefetch, nhất là với dữ liệu kiểu cố định và layout gọn. Tuy nhiên, bản thân vectorization **không thay đổi số trang bắt buộc** nếu vẫn phải đọc toàn bộ cùng tập dữ liệu.

### Có thể bỏ qua cả page không?

Nếu page có metadata đáng tin cậy:

```text
page.min_key = 100
page.max_key = 199
```

và truy vấn `key BETWEEN 400 AND 500`, page có thể bị **bỏ qua** mà không cần giải mã nội dung, nếu metadata đã ở RAM hoặc có thể đọc rẻ, và bất biến min/max luôn được cập nhật đúng.

Đây là ý tưởng **zone maps / min-max pruning** trong nhiều hệ thống phân tích. Nó tối ưu số trang được xử lý, nhưng chất lượng phụ thuộc **mức tương quan/sắp xếp của dữ liệu** và độ chính xác của thống kê.

### Bloom filter có giúp range scan không?

Bloom filter thích hợp để **loại trừ khả năng tồn tại của một khóa cụ thể** (có false positives nhưng không có false negatives khi được bảo trì đúng), hữu ích cho lookup chính xác. Bloom filter chuẩn không cho phép khẳng định một **khoảng khóa tùy ý** chắc chắn không có phần tử nếu không thêm cấu trúc/thống kê phù hợp. Với range pruning, min/max hoặc index thứ tự thường trực tiếp hơn.

## 32. Quét toàn bộ file tuần tự và quét range của index khác nhau

### Full sequential file scan

Nếu file có `N` record liền nhau, mỗi page chứa khoảng `L` record và cần đọc tất cả trong trạng thái lạnh:

\[
\boxed{\text{Full scan}\approx\left\lceil N/L\right\rceil\text{ page reads}.}
\]

### Index range scan

Nếu B+ tree chỉ mục chỉ chiếm một tập con của dữ liệu, truy vấn trả `K\ll N` record có thể đọc:

```text
Page tìm điểm bắt đầu
    + các leaf pages chứa K entries
    + các trang payload bổ sung (nếu cần).
```

### Khi K rất lớn

Nếu truy vấn lấy gần **toàn bộ bảng**, sử dụng một secondary index rồi nhảy từ RID này sang RID khác có thể **tốn hơn full sequential table scan** vì quá nhiều random data-page reads.

Hệ quản trị có thể lựa chọn:

- Index range scan khi kết quả chọn lọc và index covering.
- Full table scan khi số hàng cần đọc rất lớn.
- Bitmap/late materialization hoặc gom RID theo data page để giảm đọc ngẫu nhiên.

**Không nên luôn ép dùng index chỉ vì tồn tại index.** Chi phí quét index và lookup payload phải được tính cùng nhau.

## 33. Độ phức tạp: tách index pages và data pages

Gọi:

- `N`: số index entries.
- `F`: fanout hiệu dụng của internal nodes.
- `L`: số leaf entries/page hiệu dụng, có giới hạn lấp đầy.
- `K`: số kết quả.
- `D`: số bản ghi dữ liệu gốc/page.
- `R`: số trang data **khác nhau phải đọc** khi index không covering.

Bỏ các trang đã nằm trong cache, một mô hình chi phí gần đúng:

\[
\boxed{
T_{\mathrm{indexRange}}\approx
\underbrace{O(\log_F N)}_{\text{tìm leaf đầu}}
+\underbrace{O(1+K/L)}_{\text{duyệt leaf}}
+\underbrace{R}_{\text{fetch bảng gốc}}.
}
\]

Với index covering, `R` có thể bằng `0` (khi query/visibility thực sự được xử lý từ index). Với noncovering index:

- Trường hợp payload cluster tốt: `R` có thể gần `K/D` cộng sai lệch biên.
- Trường hợp payload rải rác và lạnh: `R` có thể lên tới `K` (hoặc ít hơn nếu nhiều RID trùng page).

### Tính cả cache

Nếu root/internal pages đã cache:

```text
Số I/O thực = số page miss của các trang cần dùng,
             không phải số page được truy cập logic.
```

Một leaf được đọc trong lúc tìm điểm bắt đầu **không bị tính hai lần** khi scan tiếp. Tương tự, một data page đã có trong RAM không phát sinh device read mới.

### Không được gọi mọi cận là “worst-case O(log n + K/B)”

Cận `O(\log_F N+1+K/L)` của leaf scan yêu cầu một số giả định về **độ lấp đầy tối thiểu**, cấu trúc cân bằng và page layout. Với leaf gần rỗng không được bảo trì, số leaf phải quét để lấy `K` entries có thể lớn hơn nhiều mức `K/L_{\max}`. Khi index không covering, hạng `R` còn có thể chi phối hoàn toàn.

## 34. Bảng đối chiếu các cách đọc dữ liệu theo trang

| Chiến lược | Loại truy vấn mạnh | Page reads trong mô hình | Điểm cần lưu ý |
|---|---|---|---|
| Full scan của file đã xếp liên tiếp | Đọc phần lớn record | `\Theta(N/D)` | Có thể nhanh nhờ request lớn/read-ahead |
| Binary search trên array-on-disk | Tìm khóa tĩnh | `O(\log N)` page touches | Nhảy giữa các page, kém tận dụng mỗi page |
| B+ tree point lookup | Khóa chính xác | `O(\log_F N)` | Root/internal thường cache |
| B+ tree covering range scan | Khoảng khóa trả ít trường | `O(\log_F N+1+K/L)` | Leaf links & occupancy quan trọng |
| Secondary index + RID lookup | Khoảng khóa trả full rows | Index scan + `R` data pages | `R` có thể gần `K` |
| Clustered range scan | Khoảng khóa lấy record gần nhau | Index seek + cỡ `K/D` | Layout vật lý và fragmentation chi phối |
| Columnar scan | Tổng hợp vài cột | Các column pages liên quan | Compression, pruning, vectorization |
| Hash index | Exact-match lookup | Kỳ vọng ít bucket I/O | Không giữ thứ tự cho range scan |

**Bậc chi phí trên là đặc trưng mô hình.** Để đo thời gian, còn cần tính byte đọc, số request vật lý, độ trễ, băng thông, IOPS, concurrency, cache và CPU work.

## 35. Kiểm thử, benchmark và điều kiện đúng của một page-oriented index

Một cấu trúc có ít I/O lý thuyết nhưng **metadata sai** có thể trả thiếu dữ liệu. Vì vậy cần kiểm tra cả hai lớp: **tính đúng** và **hiệu năng**.

### Bất biến cần kiểm tra cho slotted page

1. Header và slot directory không chồng vùng payload.
2. Mọi slot sống chỉ đến một đoạn byte hợp lệ trong page.
3. Các payload sống không chồng byte lên nhau nếu không có chủ đích chia sẻ dữ liệu.
4. Xóa một slot không làm `get` của các slot còn lại đổi nội dung.
5. Compaction không đổi `(page_id,slot_id)` của record sống nếu API hứa giữ RID nội trang.
6. Chèn không vượt `page_size`, và từ chối payload không thể chứa.

### Bất biến cần kiểm tra cho B+ tree leaf chain

1. Các khóa trong từng leaf không giảm.
2. `max_key` của leaf đúng và không giảm dọc theo chuỗi leaf.
3. `next_leaf` dẫn đến đúng leaf kế tiếp và không có vòng lặp, trừ khi một mô hình khác có cơ chế tuần hoàn được định nghĩa rõ.
4. Range scan trả **đủ và đúng** tất cả entry trong `[lo,hi]`, không bỏ duplicate keys ở biên.
5. Với cây đầy đủ: internal separator keys, child pointers, page IDs và điều kiện cân bằng đồng nhất.
6. Với giao dịch: đúng mức isolation và không đi qua page đã bị tái sử dụng sai lúc split/merge.

### Kiểm thử so sánh với mô hình tham chiếu

Trong mô hình `LeafChainIndex` của phần 28:

```python
rows = [
    (1, "a"), (1, "b"), (2, "c"),
    (2, "d"), (2, "e"), (3, "f"),
    (5, "g"), (5, "h"),
]
index = LeafChainIndex(rows, per_leaf=2)
assert index.check_invariants()

for lo in range(0, 7):
    for hi in range(lo, 7):
        buffer = LeafBuffer(index.pages, capacity=2)
        actual = index.range_scan(lo, hi, buffer)
        expected = [
            pair for pair in sorted(rows, key=lambda p: p[0])
            if lo <= pair[0] <= hi
        ]
        assert actual == expected
```

Điểm mạnh của kiểm thử này là nó đối chiếu **toàn bộ khoảng nhỏ**, bao gồm duplicate keys và những khoảng không có kết quả. Với cấu trúc page động, còn phải sinh các chuỗi `insert → split → delete → merge → scan`.

### Benchmark theo workload thực

| Chỉ số | Câu hỏi muốn trả lời |
|---|---|
| Pages touched | Có bao nhiêu trang được thuật toán đi qua? |
| Buffer pool misses | Có bao nhiêu trang thật sự phải nạp từ tầng ngoài? |
| Device bytes read/written | Mỗi thao tác kéo theo bao nhiêu byte vật lý? |
| Leaf occupancy và page count | Có nhiều trang thưa/fragmented không? |
| Tree height và fanout | Tốn bao nhiêu lần đi trang từ root đến leaf? |
| Range scan throughput | Có thể trả bao nhiêu records/s hoặc MiB/s? |
| Point-lookup latency p50/p95/p99 | Các truy vấn nhỏ có đuôi chậm không? |
| IOPS, request size, queue depth | Truy cập thiết bị là nhiều request nhỏ hay ít request lớn? |
| Split/merge/compaction rate | Có phí bảo trì bị che trong microbenchmark không? |
| CPU decode / decompression time | Tối ưu I/O có làm tăng CPU work quá nhiều không? |

### Benchmark nóng và lạnh

Một lần quét đầu có thể nạp leaf pages vào buffer. Quét lại cùng đoạn sẽ nhanh hơn nếu các trang còn ở đó; nhưng nếu đoạn dài hơn sức chứa buffer, chúng có thể bị evict.

**Đừng tuyên bố “range scan chỉ mất 6 I/O” mà quên nói buffer đang rỗng hay nóng, index metadata ở RAM hay trên disk, và có đọc heap payload không.**

## 36. Những lỗi thường gặp

| Lỗi/ngộ nhận | Vì sao nguy hiểm? | Cách xử lý |
|---|---|---|
| Dùng một khóa cho một disk page | Fanout nhỏ, độ sâu và I/O cao | Đóng gói nhiều khóa/con vào page |
| Chia `N` bản ghi cho `4096` byte rồi gọi là số block | Sai đơn vị | Chuyển `P` byte thành số record/page |
| Quên header và slot directory | Đếm thừa record/page | Tính `H+qS+\sum len(record_i)\le P` |
| Tưởng mọi record có kích thước trung bình | Record dài có thể gây split/overflow | Theo dõi byte occupancy thực |
| Nhầm contiguous free với tổng free | Chèn thất bại dù có lỗ trống | Compact nếu đủ tổng byte |
| Xóa slot nhưng giữ payload và coi nó còn sống | Trả dữ liệu đã xóa | Tombstone/free-slot semantics rõ |
| Di chuyển record nhưng không cập nhật slot | RID trỏ sai byte | Cập nhật offset khi compact |
| Di chuyển record sang page khác nhưng giữ RID cũ | Tham chiếu bên ngoài có thể sai | Forwarding hoặc sửa index |
| Tính fanout bằng số byte mà không trừ pointer | Cây thực chứa ít nhánh hơn | Dùng `H+kK_s+(k+1)C_s\le P` |
| Giả định page luôn lấp đầy 100% | Ước lượng thiếu số page | Tính fill factor và tình trạng xóa |
| Dùng `K/L_{\max}` như cận scan khi leaf rất thưa | Bỏ qua nhiều page trung gian | Bảo trì occupancy hoặc dùng `L_{\mathrm{effective}}` |
| Cho rằng `next_leaf` logic là địa chỉ vật lý kế tiếp | Có thể đọc ngẫu nhiên rải rác | Đo layout, clustering, fragmentation |
| Quay về root cho mỗi entry kế tiếp | Lãng phí thao tác/page touches | Duyệt liên kết leaf đúng cách |
| Tìm một leaf chứa `lo` mà bỏ duplicate ở leaf trước | Trả thiếu dữ liệu | Tìm lower bound toàn bộ index |
| Dùng `bisect_right` cho duplicate boundary | Có thể bỏ các khóa bằng `lo` | Dùng `bisect_left` với khóa phù hợp |
| Đếm lại leaf đầu sau khi đã đọc để seek | Cộng đúp chi phí I/O | Kế toán page đọc một lần/hit cache |
| Chỉ đếm index pages, quên heap pages | Unclustered scan tốn nhiều I/O hơn dự kiến | Thêm hạng `R` data-page misses |
| Coi index có đủ cột là luôn index-only | Một số engine cần check visibility | Xét MVCC/visibility của engine |
| Coi prefetch giúp giảm số page cần đọc | Prefetch chủ yếu che latency | Tách page count và wall-clock |
| Prefetch quá xa | Cache pollution hoặc I/O không cần | Giới hạn lookahead theo workload |
| Quên unpin trang đã duyệt | Buffer không thể evict, deadlock/tắc nghẽn | Quản lý pin/unpin đúng |
| Chỉ chia leaf, quên separator/parent | Đường tìm đi sai trang | Bảo trì toàn bộ bất biến cây |
| Xóa nhiều nhưng không compact/merge | Page thưa khiến scan chậm | Chọn chính sách reorganization |
| Tuyên bố một phép insert chỉ có 1 page write | Split có thể lan lên cha/gốc, thêm WAL | Tính các page và log tương ứng |
| Tưởng latch đủ bảo đảm truy vấn nhất quán | Còn transaction isolation/MVCC | Thiết kế cả physical và logical concurrency |
| Ghi trang dữ liệu trước log theo thiết kế WAL | Crash có thể không recovery đúng | Tuân thủ WAL ordering |
| Đo một scan nóng rồi suy ra tốc độ scan lạnh | Khác buffer hits | Báo cáo cold/warm rõ |
| Nhầm API pagination với database page | Đơn vị 100 rows khác 4 KiB | Phân biệt kết quả logic và trang lưu trữ |
| Dùng `OFFSET` quá lớn mà coi là seek `O(1)` | Có thể cần bỏ qua rất nhiều entry | Cân nhắc keyset pagination |
| Chọn index cho mọi truy vấn | Full scan có thể tốt hơn khi `K` lớn | Dùng cost model và benchmark |
| Lấy kết quả mô phỏng Python làm I/O vật lý | Dữ liệu Python ở RAM, không đo SSD | Chỉ dùng làm mô hình logic |

## 37. Bài tập tự kiểm tra

**Bài 1.** Vì sao đặt mỗi khóa của cây tìm kiếm trên một page riêng có thể không hiệu quả khi dữ liệu ở SSD/HDD?

**Bài 2.** Phân biệt **logical tree node**, **database page**, **CPU cache line** và **virtual-memory page**.

**Bài 3.** Trong I/O model, ký hiệu `N,M,B` có đơn vị gì? Vì sao không chia số bản ghi cho kích thước trang tính bằng byte?

**Bài 4.** Một page `P=4096` byte, header `H=96` byte, mỗi record payload `120` byte và slot `4` byte. Tính số record tối đa/page.

**Bài 5.** Trong page của bài 4, nếu không có slot directory, số record tối đa theo mô hình fixed-size là bao nhiêu? Vì sao con số khác?

**Bài 6.** Một page có `H=96`, `q=4` slot, slot `4` byte, record payload dài `120,60,200,80` byte. Tổng số byte dùng là bao nhiêu?

**Bài 7.** Trong slotted page, vì sao compaction có thể giữ nguyên `(page_id,slot_id)` của các record sống?

**Bài 8.** Một page có 60 byte trống tổng cộng nhưng gap liên tục chỉ 20 byte. Chèn payload 45 byte + slot 4 byte cần làm gì?

**Bài 9.** Internal B+ tree page `P=4096,H=96,K_s=16,C_s=8`. Tính số khóa phân cách tối đa và fanout tối đa.

**Bài 10.** Tại sao một internal node có `k` khóa thường có `k+1` child pointers?

**Bài 11.** Leaf page `P=4096,H=96` chứa entry `16` byte key, `8` byte RID, `4` byte slot. Tính số entry tối đa.

**Bài 12.** Nếu leaf entry gồm key `16`, payload `200` và slot `4` byte, số entry tối đa là bao nhiêu? Điều gì đổi so với bài 11?

**Bài 13.** Với leaf capacity tối đa `142`, lấp đầy mục tiêu `70%`, số entry mục tiêu mỗi leaf xấp xỉ bao nhiêu?

**Bài 14.** Với `N=1{,}000{,}000`, `F=167`, `L=142`, một cây đầy lý tưởng có thể chứa tập dữ liệu trên mấy cấp trang?

**Bài 15.** Phát biểu hai giai đoạn chính của range scan trên B+ tree và vì sao không phải quay lại root cho mỗi entry.

**Bài 16.** Mỗi leaf có đúng `4` entry. Đọc 6 entry liên tục bắt đầu tại vị trí `s=3` chạm mấy leaf? Nếu `s=4` thì sao?

**Bài 17.** Với `1000` kết quả và mỗi leaf chứa đúng `99` entry, bắt đầu tại **đầu leaf** cần mấy leaf pages? Bắt đầu tại **entry cuối leaf** cần mấy leaf?

**Bài 18.** Đường tìm từ root đến leaf có 3 cấp, trang root và internal lạnh; một scan đụng tổng 11 leaf (bao gồm leaf đầu). Tại sao tổng index reads là 13 chứ không phải 14?

**Bài 19.** Nêu sự khác nhau giữa thứ tự leaf **logic theo khóa** và vị trí leaf **vật lý trên thiết bị**.

**Bài 20.** Phân biệt *clustered index*, *unclustered secondary index* và *covering index* đối với range scan.

**Bài 21.** Range scan trả `K=1000` bản ghi, index leaf scan cần 13 reads; dữ liệu gốc ở 1000 heap pages khác nhau, tất cả lạnh. Có thể phải đọc tổng khoảng bao nhiêu pages?

**Bài 22.** Nếu 1000 bản ghi cùng nằm gần nhau theo khóa, mỗi data page chứa 40 bản ghi và truy vấn bắt đầu ở biên page, cần khoảng bao nhiêu data-page reads?

**Bài 23.** Vì sao chỉ tìm một leaf **bất kỳ** chứa khóa `lo` có thể bỏ sót các khóa bằng nhau? Việc tìm lower_bound giúp gì?

**Bài 24.** Prefetch các leaf tiếp theo có luôn làm giảm **số trang cần đọc** không? Lợi ích chính là gì?

**Bài 25.** Phân biệt *in-page compaction*, *leaf split* và *leaf merge*.

**Bài 26.** Sau khi xóa nhiều entry, một B+ tree có rất nhiều leaf thưa. Điều này ảnh hưởng thế nào đến range scan?

**Bài 27.** Tại sao split leaf có thể yêu cầu sửa cả parent, sibling links và WAL, không chỉ sửa một leaf?

**Bài 28.** Tại sao latch bảo vệ một page trong lúc sửa chưa đủ đảm bảo một truy vấn thấy một snapshot nhất quán?

**Bài 29.** Trong mã `SlottedPage`, trang `128` byte, header `24`, slot `4`, lần lượt thêm payload `20,30,15` byte. Gap liên tục còn bao nhiêu?

**Bài 30.** Sau bài 29, xóa payload 30 byte, compact, thêm payload 40 byte và slot mới 4 byte. Gap còn bao nhiêu?

**Bài 31.** Mô hình `LeafChainIndex` có 100 khóa `0..99`, mỗi leaf 10 khóa. Quét `[25,74]` chạm mấy leaf? Tại sao khi buffer chỉ giữ 2 leaf thì quét lần hai vẫn có thể miss mọi leaf?

**Bài 32.** Một index scan trả rất nhiều hàng nhưng cần đọc các cột không nằm trong index. Vì sao full sequential table scan đôi khi nhanh hơn?

**Bài 33.** Một API dùng `limit=100,offset=100000`. Tại sao 100 kết quả cuối chưa chắc chỉ cần đọc một vài database page? Cách pagination nào thường tránh được việc quét bỏ nhiều entry?

**Bài 34.** Nếu page có min_key=100 và max_key=199, truy vấn `key BETWEEN 400 AND 500` có thể loại page bằng cách nào? Cần giả định gì về metadata?

## 38. Đáp án và giải thích

**Bài 1.** Mỗi lần đọc page chỉ đem về một khóa, phải đi qua nhiều trang nếu cây cao; latency I/O có thể chi phối. Một node nhiều khóa dùng cả page và cho fanout lớn hơn.

**Bài 2.** Node là đơn vị **logic** của cấu trúc; database page là đơn vị layout/buffer của engine; cache line là đơn vị chuyển trong CPU cache; VM page là đơn vị ánh xạ/protection của MMU. Không bắt buộc cùng kích thước.

**Bài 3.** `N`, `M` đều tính bằng **phần tử**, `B` là **phần tử mỗi block**. Số bản ghi chia số byte cho kết quả sai đơn vị; cần quy đổi byte/page thành số record/page.

**Bài 4.** `\lfloor(4096-96)/(120+4)\rfloor=\lfloor4000/124\rfloor=\boxed{32}` record/page.

**Bài 5.** Không có slot, `\lfloor4000/120\rfloor=33` record/page. Slot directory tiêu tốn 4 byte cho mỗi record nên dung lượng giảm.

**Bài 6.** `96+4\cdot4+120+60+200+80=\boxed{572\text{ byte}}`.

**Bài 7.** Slot giữ **vị trí trừu tượng** và offset; compaction di chuyển payload bên trong trang nhưng cập nhật offset tại cùng slot ID, nên RID không cần đổi nếu chưa đổi page.

**Bài 8.** Tổng 60 byte đủ cho 49 byte mới, nhưng gap 20 byte không đủ. Có thể compact page để gom lỗ trống thành vùng liền mạch rồi chèn, nếu sau compaction còn đủ.

**Bài 9.** `k_{\max}=\lfloor(4096-96-8)/(16+8)\rfloor=\lfloor3992/24\rfloor=166`, `F_{\max}=167`.

**Bài 10.** Các khóa phân cách chia miền khóa thành `k+1` khoảng, mỗi khoảng có một child pointer trong bố trí internal node cơ bản.

**Bài 11.** `\lfloor4000/(16+8+4)\rfloor=\lfloor4000/28\rfloor=142` entry/page.

**Bài 12.** `\lfloor4000/(16+200+4)\rfloor=\lfloor4000/220\rfloor=18` entry/page. Leaf dày payload làm giảm mật độ entry nhưng có thể tránh đọc bảng gốc nếu query được bao phủ.

**Bài 13.** `\lfloor0.70\cdot142\rfloor=99` entry/page theo ví dụ.

**Bài 14.** `167\cdot142=23714` chưa đủ một triệu, nhưng `167^2\cdot142=3{,}960{,}238` đủ, nên cần **3 cấp** root → internal → leaf trong mô hình đầy lý tưởng.

**Bài 15.** Tìm leaf bắt đầu từ root, rồi duyệt các leaf theo thứ tự khóa qua sibling link/cursor đến hết khoảng. Không cần về root cho mỗi entry nếu liên kết và bất biến scan được duy trì.

**Bài 16.** `s=3`, 6 entry là `3..8`, đụng leaf 0,1,2 → **3 leaf**. `s=4` là `4..9`, đụng leaf 1,2 → **2 leaf**.

**Bài 17.** Bắt đầu ở biên: `\lceil1000/99\rceil=11` leaf. Bắt đầu ở entry cuối: `\lceil(98+1000)/99\rceil=12` leaf.

**Bài 18.** Đường tìm đọc root, internal và **leaf đầu**. Trong 11 leaf pages đã kể cả leaf đầu, chỉ có 10 leaf còn lại cần đọc thêm. Tổng `2+11=13` reads.

**Bài 19.** Liên kết leaf theo key-order là **logic**. Page ID và block vật lý có thể rải rác; scan logic theo khóa không đảm bảo đọc vật lý tuần tự. Fragmentation, clustering và cấp phát page ảnh hưởng.

**Bài 20.** Clustered index đặt bản ghi gốc gần hoặc theo thứ tự key; unclustered secondary index có thể chỉ chứa key→RID và phải lấy payload rải rác; covering index chứa đủ trường query cần để có thể tránh heap fetch nếu visibility cho phép.

**Bài 21.** `13` index reads + tới `1000` heap reads = khoảng **1013 page reads**, nếu không có page hit và không có nhiều RID cùng trang.

**Bài 22.** `\lceil1000/40\rceil=\boxed{25}` data pages, với data được cluster đúng cách và bắt đầu tại biên.

**Bài 23.** Khóa bằng `lo` có thể kéo dài qua nhiều leaf. Nếu tìm leaf muộn, entry ở leaf trước bị bỏ; lower_bound bảo đảm bắt đầu từ entry đầu tiên có khóa `\ge lo`.

**Bài 24.** Không. Prefetch chủ yếu **chồng lấp/chủ động đưa I/O lên trước**, giảm chờ. Nếu đọc thừa leaf không dùng còn có thể tăng I/O và cache pollution.

**Bài 25.** Compaction gom payload trong **một trang**, giữ page/slot ID nếu thiết kế cho phép; split tạo một leaf mới và chia entries, sửa cha/links; merge hợp nhất hai leaf và có thể bỏ một page.

**Bài 26.** Độ lấp đầy thấp khiến cùng `K` kết quả trải qua nhiều leaf hơn, tăng page touches, cache footprint và có thể tăng I/O. Có thể cần redistribution/merge/reorganization theo chính sách.

**Bài 27.** Split thay đổi ranh giới key, con trỏ cha và linked leaves; nếu split lan lên có thể sửa tổ tiên. WAL và flush ordering cần cho recovery, không chỉ update một page.

**Bài 28.** Latch bảo vệ nhất quán **vật lý** trong khoảng ngắn; isolation/snapshot cần MVCC, transaction locks hoặc giao thức khác để quyết định record nào được thấy khi cấu trúc thay đổi.

**Bài 29.** Dung lượng đã dùng: `24+3\cdot4+(20+30+15)=101` byte; gap `128-101=\boxed{27\text{ byte}}`.

**Bài 30.** Sau xóa+compact, payload sống `20+15=35` byte, 3 slot chiếm 12 byte, header 24: gap `128-(24+12+35)=57`. Thêm payload 40 và slot 4: gap `57-44=\boxed{13\text{ byte}}`.

**Bài 31.** Khóa `25..74` chạm leaf mang `20..29`, `30..39`, `40..49`, `50..59`, `60..69`, `70..79`: **6 leaf**. Buffer 2 chỉ giữ hai leaf cuối, quay về leaf đầu sẽ evict dần và miss cả sáu ở lượt sau.

**Bài 32.** Index chỉ đưa ra RIDs; lấy payload gốc từ nhiều heap pages ngẫu nhiên có thể tốn tới `O(K)` page misses. Nếu đọc gần toàn bảng, full scan tuần tự có thể tận dụng băng thông/read-ahead hơn.

**Bài 33.** Để bỏ 100.000 entry, kế hoạch OFFSET có thể phải scan nhiều leaf/data pages trước khi trả 100 entry. **Keyset/cursor pagination** seek từ `(last_key,unique_id)` và đọc tiếp, không quét bỏ từ đầu; vẫn cần xét snapshot/concurrent updates.

**Bài 34.** Vì `[100,199]` không giao `[400,500]`, có thể prune page dựa vào min/max đã lưu. Metadata cần được bảo trì đúng, có ngữ nghĩa khóa/ordering nhất quán và sẵn có trước khi quyết định skip.

## 39. Ghi nhớ

**Thiết kế nút theo trang** giúp cấu trúc dữ liệu ngoài RAM **tận dụng từng lần chuyển khối I/O**: internal B+ tree page chứa nhiều khóa phân cách và child pointers để có **fanout lớn**; leaf page chứa các entry theo thứ tự khóa, có thể nối thành một chuỗi thuận tiện cho **range scan**. Một page cần dành chỗ cho **header, slot directory, payload và khoảng trống**; với record biến độ dài phải bảo trì đúng byte occupancy, offset/length, tombstone, compaction và chính sách split/merge. Cận lý tưởng cho index range scan là **`O(\log_F N+1+K/L)` page touches**, nhưng nếu index không bao phủ trường cần trả còn phải cộng **`R` data pages** có thể gần `K` trong trường hợp payload rải rác. **Liên tiếp theo thứ tự khóa không đồng nghĩa các block nằm liền nhau vật lý**: clustering, read-ahead, cache và layout quyết định khả năng tận dụng đọc tuần tự thật. Khi đánh giá một cấu trúc, hãy tính cùng lúc **fanout, fill factor, page bytes, chi phí duyệt leaf, payload fetch, cập nhật, concurrency/recovery và số block misses**; chỉ sau đó mới đưa ra quyết định dựa trên phép đo workload thực tế.
