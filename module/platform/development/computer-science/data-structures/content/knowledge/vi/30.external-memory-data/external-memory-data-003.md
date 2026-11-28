# Vì sao số lần đọc trang có thể quan trọng hơn số phép so sánh

> **Chương:** Dữ liệu ngoài bộ nhớ
> **Bài học:** Vì sao số lần đọc trang có thể quan trọng hơn số phép so sánh
> **Mô-đun:** `COMPUTER_SCIENCE_DATA_STRUCTURES`

Một chương trình cần tìm hồ sơ có khóa `user_id = 740000` trong một tệp gồm một triệu bản ghi. Nếu chỉ đếm phép so sánh, thuật toán tìm kiếm nhị phân trên mảng đã sắp chỉ cần khoảng 20 lượt kiểm tra, còn quét tuyến tính có thể cần tới một triệu lượt. Kết luận “nhị phân nhanh hơn khoảng 50.000 lần” vì thế có vẻ hiển nhiên.

Nhưng hãy thay đổi môi trường: các bản ghi nằm trên SSD, mỗi lần truy cập một trang chưa có trong RAM phải đợi I/O; hoặc toàn bộ bản ghi nằm sẵn trong cache và phép quét đọc liên tục từ bộ nhớ. Khi ấy **số phép so sánh không còn đủ để dự đoán thời gian thực tế**. Ta phải trả lời thêm:

- Mỗi phép so sánh chạm vào **trang** nào?
- Trang đó đã ở trong **RAM / buffer pool** hay chưa?
- Truy cập trang là **ngẫu nhiên** hay **tuần tự**?
- Bao nhiêu bản ghi cùng được đưa vào RAM nhờ một lần nạp trang?
- Bộ nhớ đủ giữ bao nhiêu trang, và những truy vấn sau có tái sử dụng chúng không?
- Chỉ mục có lưu khóa riêng hay cần đọc thêm trang dữ liệu để lấy bản ghi thật?

Đây là lý do các cấu trúc dữ liệu ngoài bộ nhớ như **B-tree, B+ tree, chỉ mục băm trên đĩa, LSM-tree và thuật toán sắp xếp trộn ngoài bộ nhớ** được thiết kế quanh **lần truyền trang / block**, không chỉ quanh số phép so sánh.

Bài thuộc mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, với mục tiêu học mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap, đồ thị cùng bất biến và chi phí thời gian–bộ nhớ để chọn cấu trúc phù hợp. Trọng tâm ở đây là chuyển từ câu hỏi **“thuật toán làm bao nhiêu phép toán?”** sang câu hỏi rộng hơn: **“thuật toán buộc hệ thống di chuyển bao nhiêu dữ liệu giữa các tầng lưu trữ?”**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **mô hình chi phí RAM** với **mô hình I/O ngoài bộ nhớ**.
2. Định nghĩa trang, block, page cache, buffer pool, page hit và page miss.
3. Giải thích vì sao một lần đọc trang có thể mang theo nhiều bản ghi.
4. Tính xấp xỉ số trang của một tệp và số lần đọc trang của phép quét.
5. Phân tích tìm kiếm nhị phân trên tệp đã sắp: O(log N) phép so nhưng có thể cần nhiều **trang khác nhau**.
6. Giải thích vì sao B+ tree có **fanout lớn** và chiều cao nhỏ.
7. Phân biệt chi phí **tìm hàng trong chỉ mục** với chi phí **lấy bản ghi dữ liệu**.
8. Phân tích truy vấn điểm, truy vấn khoảng, quét, batch lookup và join theo locality.
9. Hiểu vai trò của cache, đọc trước (*read-ahead*), nén và ghi theo lô.
10. Viết một bộ mô phỏng nhỏ đếm **page miss** độc lập với số phép so sánh.
11. So sánh độ phức tạp I/O của quét, tìm nhị phân, B+ tree và sắp xếp trộn ngoài bộ nhớ.
12. Thiết kế benchmark không trộn kết quả **cold cache** với **warm cache**.
13. Nhận biết những kết luận Big-O đúng về so sánh nhưng có thể sai về hiệu năng ổ đĩa.
14. Đề xuất cấu trúc dữ liệu phù hợp khi ưu tiên số lần I/O, thời gian phản hồi hoặc thông lượng.

## 2. Bức tranh phân cấp bộ nhớ

Một lần truy cập dữ liệu có thể đi qua nhiều tầng:

```text
CPU register
    |
CPU caches (L1 / L2 / L3)
    |
RAM (heap, OS page cache, DB buffer pool)
    |
SSD / HDD / thiết bị lưu trữ
    |
Lưu trữ phân tán / qua mạng (nếu có)
```

Các tầng không có cùng độ trễ, băng thông, kích thước và đơn vị truyền dữ liệu.

Trong các bài cấu trúc dữ liệu trên RAM, ta thường giả sử `A[i]`, so sánh hai khóa hoặc theo con trỏ mất một số đơn vị chi phí hằng số. Đó là mô hình rất hữu ích để học thuật toán, nhưng nó **không mô tả trực tiếp chi phí khi trang chứa `A[i]` chưa ở trong RAM**.

Một phép toán có thể cần:

1. Xác định vị trí bản ghi.
2. Tìm trang trong bộ đệm.
3. Nếu trang chưa có, đọc trang từ SSD/HDD.
4. Chờ nạp trang; có thể kích hoạt giải nén hay kiểm tra checksum.
5. So sánh khóa sau khi trang đã sẵn sàng.

Trong chuỗi công việc ấy, phép so sánh đôi khi rất rẻ so với bước 3–4.

### 2.1. Không được hiểu “chậm hơn” là quy luật tuyệt đối

Độ trễ đọc trang tùy thuộc ổ đĩa, hệ điều hành, cache, queue depth, concurrency, bố trí file, thiết bị mạng và kích thước truyền. Một phép so sánh chuỗi dài hoặc giải nén phức tạp cũng không miễn phí.

Điểm quan trọng là: **khi dữ liệu lớn hơn RAM hoặc có nhiều page miss, số lần nạp trang có thể thống trị chi phí**, nên chỉ đếm so sánh là thiếu một biến quan trọng.

## 3. Trang, block và đơn vị I/O

Một **trang** (*page*) là đơn vị dữ liệu được hệ điều hành hoặc hệ quản trị cơ sở dữ liệu quản lý để chuyển giữa lưu trữ và bộ nhớ. Một **block** trong mô hình I/O là đơn vị truyền trừu tượng.

Các giá trị thường gặp như 4 KiB hay 16 KiB chỉ là ví dụ cấu hình; không phải mọi thiết bị, engine và file đều dùng đúng một kích thước trang.

### 3.1. Ví dụ một trang chứa nhiều bản ghi

Giả sử:

- Mỗi trang chứa tối đa `4096` byte dữ liệu giả định.
- Một bản ghi chiếm đúng `100` byte.
- Bản ghi **không được cắt qua ranh giới trang**.
- Bỏ qua header, slot directory, căn chỉnh và overhead khác.

Số bản ghi một trang:

\[
B=\left\lfloor\frac{4096}{100}\right\rfloor=40.
\]

Một lần đọc trang có thể đưa vào RAM **40 bản ghi**, không chỉ bản ghi được tìm.

Nếu một thuật toán đọc liên tục 40 bản ghi cùng trang, nó có thể chỉ cần **một lần page miss** dù làm 40 phép so sánh.

### 3.2. Tại sao B là đơn vị quan trọng?

Đặt:

- `N`: số bản ghi.
- `B`: số bản ghi hoặc mục chỉ mục trong một block (cần nêu rõ loại).
- `M`: số bản ghi có thể giữ trong bộ nhớ dùng cho thuật toán.
- `P=\lceil N/B\rceil`: số trang trong cách xếp bản ghi cố định lý tưởng.

Mô hình **external-memory / I/O model** thường đo số lần **chuyển block** giữa RAM và bộ nhớ ngoài.

Nếu những bản ghi có độ dài biến thiên hoặc có overhead trong trang, công thức thực tế phải dùng **số trang đã cấp phát và mức lấp đầy**, không chỉ `N/B`.

### 3.3. Page ID không phải record ID

Với trang chứa B bản ghi, bản ghi logic thứ `i` trong file có bố trí cố định có thể nằm ở:

\[
page(i)=\left\lfloor i/B\right\rfloor.
\]

Các bản ghi `i=40,\ldots,79` cùng ở trang 1 khi `B=40`.

Phép tính này chỉ đúng cho bố trí đơn giản theo vị trí. Trong một database có trang slotted, bản ghi biến độ dài, chuyển hàng, heap file hoặc chỉ mục phụ, ánh xạ record ID → page ID cần một tầng lưu trữ thực sự.

## 4. Hai mô hình chi phí khác nhau

### 4.1. Mô hình so sánh / RAM

Với `N` khóa đã sắp:

- Quét tuyến tính: O(N) phép so.
- Tìm kiếm nhị phân: O(log N) phép so.
- BST cân bằng: O(log N) phép so.
- Hash table: tra khóa kỳ vọng O(1) theo giả định băm phù hợp.

Các kết quả ấy nói về **số thao tác trừu tượng**. Chúng không tự cho biết số lần đọc trang.

### 4.2. Mô hình I/O

Trong external-memory model, ta đếm:

\[
I=\text{số block được truyền giữa bộ nhớ ngoài và RAM}.
\]

Chi phí CPU vẫn tồn tại, nhưng ta đặc biệt chú ý `I` vì một lần I/O có thể đắt hơn nhiều phép toán xử lý trên dữ liệu đã có sẵn.

Với bố trí tuần tự:

\[
I_{\mathrm{scan}}=\Theta(\lceil N/B\rceil).
\]

Với B-tree hoặc B+ tree có số khóa/con phù hợp với trang, truy vấn điểm thường có:

\[
I_{\mathrm{Btree}}=O(\log_B N)
\]

trong mô hình lý thuyết có các giả định về fanout và cách lưu nút.

### 4.3. Không so những biểu thức không cùng đơn vị

`O(N)` **phép so** và `O(N/B)` **page transfer** không mâu thuẫn: một thuật toán quét làm khoảng N phép so nhưng đọc khoảng N/B trang. Nếu một bài báo hoặc lời giải dùng Big-O mà không nêu đơn vị, phải kiểm tra họ đang đếm **CPU operations**, **cache misses** hay **disk I/O**.

## 5. Một mô hình thời gian đơn giản nhưng hữu ích

Cho:

- `C`: số phép so sánh.
- `c`: thời gian trung bình giả định của một phép so.
- `I`: số lần phải đọc một trang chưa được cache.
- `\ell`: thời gian khởi động/độ trễ trung bình của một yêu cầu đọc.
- `D`: số byte đọc thực tế.
- `v`: băng thông truyền dữ liệu hiệu dụng.

Một **ước lượng tuyến tính rất giản lược**, khi các bước không chồng lấn:

\[
T \approx Cc+I\ell+\frac{D}{v}
+\text{chi phí giải mã/giải nén/phần mềm}.
\]

Đây **không phải công thức đo thời gian chuẩn cho mọi thiết bị**. Nếu `\ell` đã bao gồm phần truyền dữ liệu, không được cộng lại `D/v` như một chi phí độc lập. I/O bất đồng bộ, nhiều hàng đợi và CPU xử lý song song có thể làm tổng thời gian tường khác tổng từng lần đọc.

### 5.1. Ví dụ có giả định, không phải số đo thiết bị

Giả sử để minh họa:

- Một phép so số nguyên trên dữ liệu có sẵn tốn trung bình **5 ns**.
- Một yêu cầu đọc trang bị page miss và phải phục vụ tuần tự tốn **200 µs**, không kể thời gian CPU.
- So sánh và I/O không chồng lấn.

Một triệu phép so:

\[
10^6\times5\,ns=5\,ms.
\]

Một trăm lần đọc trang:

\[
100\times200\,\mu s=20\,ms.
\]

Trong **bộ giả định này**, chỉ 100 page miss đã tốn gấp bốn lần thời gian của một triệu phép so.

Đây là ví dụ để hiểu **tỉ trọng chi phí**; không được trích 200 µs thành con số chung cho mọi SSD, RAM, HDD hay nền tảng cloud.

### 5.2. Lúc nào chi phí CPU trở lại quan trọng?

Nếu tất cả các trang đã ở RAM, `I=0` đối với tầng disk I/O đang xét. Khi đó số phép so sánh, nhánh điều kiện, cache CPU, xử lý chuỗi dài, giải nén và số byte đọc trong RAM có thể quyết định độ trễ.

Do đó câu hỏi đúng là **“điểm nghẽn hiện tại là gì?”**, không phải “I/O luôn quan trọng hơn CPU”.

## 6. Ví dụ dữ liệu một triệu bản ghi

Giả sử file chứa:

- `N=1\,000\,000` bản ghi.
- Kích thước logic 100 byte/bản ghi.
- Trang 4096 byte.
- Tối đa B=40 bản ghi/trang, không cắt bản ghi.
- Các trang đều được lấp đúng như mô hình lý tưởng, bỏ qua overhead.

Số trang:

\[
P=\left\lceil\frac{1\,000\,000}{40}\right\rceil
=25\,000.
\]

Tổng byte dữ liệu bản ghi là 100.000.000 byte; tổng dung lượng cấp phát theo 25.000 trang là 102.400.000 byte vì mỗi trang thừa 96 byte theo cách bố trí này.

### 6.1. Ba cách tìm một khóa

| Cấu trúc | Công việc chính | Số lần so sánh / đọc trang lý tưởng |
| --- | --- | --- |
| File không có chỉ mục, quét hết | Thăm từng bản ghi | Tối đa 1.000.000 phép so; khoảng 25.000 trang |
| File đã sắp, binary search trực tiếp theo record | Thăm các vị trí giữa | Khoảng 20 phép so; tối đa khoảng 20 trang khác nhau |
| B+ tree, leaf chứa dữ liệu, fanout nội bộ khoảng 100 | Đi từ gốc xuống lá | Khoảng 4 trang trên một đường cold-cache trong ví dụ này |

Bảng chỉ nhằm cho thấy **khác biệt bậc và cấu trúc**; số trang thực tế phụ thuộc có cache hay không, root/inner node được giữ trong RAM không, mức lấp đầy và loại chỉ mục.

### 6.2. Vì sao B+ tree khoảng bốn trang?

Nếu leaf chứa 40 bản ghi:

\[
L=\lceil1\,000\,000/40\rceil=25\,000
\]

trang lá. Giả sử mỗi nút trong chứa tối đa khoảng **100 liên kết con**, số trang từng tầng từ dưới lên có thể là:

```text
Leaf pages:                25,000
Parents of leaves:            250
Next internal level:            3
Root:                           1
---------------------------------
One root-to-leaf path:          4 pages
```

Cấu hình này bỏ qua chi tiết lấp đầy, header, khóa phân cách, kích thước con trỏ và ràng buộc B+ tree thực tế. Nhưng nó giải thích tại sao **fanout lớn làm chiều cao rất nhỏ** so với cây nhị phân.

### 6.3. Chênh lệch lớn không đến từ “số phép so = 4”

Ở mỗi trang trong B+ tree, thuật toán có thể so nhiều khóa phân cách trong RAM — chẳng hạn binary search trong một nút chứa hàng chục hoặc hàng trăm khóa. Chi phí so sánh có thể lớn hơn bốn, nhưng số **trang mới cần nạp** vẫn có thể chỉ khoảng bốn.

Đó là điểm cốt lõi của bài: **một nút/trang chứa nhiều khóa cho phép làm nhiều phép so sau một lần I/O**.

## 7. Quét tuần tự: nhiều phép so nhưng ít I/O tính trên từng bản ghi

Khi quét một tệp đã bố trí tuần tự, thuật toán đọc:

```text
Page 0: record 0 ... record 39
Page 1: record 40 ... record 79
Page 2: record 80 ... record 119
...
```

Nếu cần kiểm tra tất cả các bản ghi, có:

\[
C_{\mathrm{scan}}=\Theta(N)
\]

phép so sánh và:

\[
I_{\mathrm{scan}}=\Theta(N/B)
\]

lần đọc block trong trường hợp toàn bộ dữ liệu ban đầu nằm ngoài RAM.

### 7.1. Mô hình CPU tốt và I/O tốt là hai câu khác nhau

Một phép quét N bản ghi đọc tất cả N nhưng chỉ cần nạp mỗi trang một lần. Nếu truy cập theo thứ tự tăng địa chỉ, OS hoặc DBMS có thể:

- Dùng **read-ahead** để nạp trước các trang kế tiếp.
- Gộp các yêu cầu đọc thành các lần truyền lớn.
- Dùng băng thông tuần tự hiệu quả hơn đọc ngẫu nhiên.
- Duyệt vùng dữ liệu liên tục thuận lợi cho cache CPU.

Vì vậy O(N) phép so không nhất thiết có thời gian thực lớn hơn mọi thuật toán ít phép so nếu thuật toán kia tạo **nhiều truy cập ngẫu nhiên**.

### 7.2. Quét trả kết quả sớm

Nếu một phép tìm có thể dừng ngay khi gặp khóa, số trang đọc là khoảng:

\[
\left\lceil\frac{position+1}{B}\right\rceil
\]

trong bố trí cố định khi bắt đầu ở trang đầu và không có trang cache.

Nhưng nếu mục tiêu là **đếm tất cả bản ghi thỏa điều kiện**, quét phải xem toàn bộ file trừ khi có chỉ mục/metadata khác hỗ trợ.

### 7.3. Quét có ưu thế ở truy vấn độ chọn lọc thấp

Giả sử truy vấn `status="active"` trả 80% các hàng, và dữ liệu được lưu gần liên tục. Một index thứ cấp có thể buộc đọc rất nhiều row page rải rác, trong khi quét toàn bộ bảng chỉ đọc mỗi trang một lần.

Không thể kết luận “có index thì luôn nhanh hơn scan” nếu không tính **số trang dữ liệu cần lấy**, selectivity và locality.

## 8. Tìm nhị phân trên mảng đã sắp: so sánh ít nhưng truy cập rời rạc

Tìm nhị phân chọn vị trí giữa khoảng tìm:

```text
N = 1,024

probe indices khi tìm khóa cuối:
511 -> 767 -> 895 -> 959 -> 991 ->
1007 -> 1015 -> 1019 -> 1021 -> 1022 -> 1023
```

Có **11 phép so sánh**. Với mỗi trang chứa 16 phần tử, chỉ số trang lần lượt:

```text
31 -> 47 -> 55 -> 59 -> 61 ->
62 -> 63 -> 63 -> 63 -> 63 -> 63
```

Nếu cache ban đầu rỗng và không trang nào bị đẩy ra trước lần dùng lại, có **7 trang phân biệt** được nạp, không phải 11 trang.

### 8.1. Điều gì xảy ra trên file lớn?

Lượt dò đầu có thể nhảy giữa các khu vực cách nhau rất xa. Truy cập đó thường khó tận dụng đọc trước tuần tự như phép scan.

Với N phần tử, tìm nhị phân có O(log N) phép so, và chặn số lần đọc trang cold theo lượt dò cũng O(log N); nhưng **số page miss thực tế** có thể thấp hơn nếu nhiều lượt dò rơi vào cùng trang hoặc trang đã được cache.

### 8.2. Vài chục trang khác nhau có thể vẫn đắt

Nếu lần đọc là random miss phải chờ thiết bị, vài chục trang vẫn có thể tạo độ trễ đáng kể. Còn nếu tất cả trong RAM, cùng các phép so ấy thường rất nhanh.

Vì thế cần phân biệt:

- `comparison count`: 11.
- `page references`: 11.
- `distinct pages cold`: 7.
- `physical page reads`: có thể ít hơn hoặc khác tùy cache, prefetch và tổ chức thiết bị.

### 8.3. Không phải mọi truy vấn binary search đều có cùng tập trang

Các truy vấn khác nhau thường dùng lại những trang gần các điểm chia đầu tiên của phép tìm. Nếu nhiều truy vấn liên tiếp, **một số trang đầu trở thành trang nóng**, giảm page miss.

Một chỉ mục được xây theo **bố trí phân tầng với nhiều khóa trong mỗi trang** khai thác ý tưởng này rõ ràng hơn.

## 9. B+ tree: tổ chức để giảm đường đi giữa các trang

**B+ tree** là một cây tìm kiếm cân bằng có fanout cao, thường dùng làm chỉ mục on-disk.

Ý tưởng:

- Mỗi nút trong được lưu trong một trang hoặc một vùng tương đương trang.
- Nút trong giữ **khóa phân cách** và liên kết tới nhiều trang con.
- Các khóa/bản ghi hoặc tham chiếu bản ghi được lưu ở **tầng lá**.
- Các lá thường có liên kết để quét theo thứ tự khóa.
- Các lá ở cùng độ sâu trong cây chuẩn.

### 9.1. Sơ đồ

```text
                    [root page]
           /             |             \
     [internal]      [internal]      [internal]
      / | ... \       / | ... \       / | ... \
    [leaf pages]   [leaf pages]    [leaf pages]
          <------ linked leaf sequence ------->
```

Mỗi lần đi xuống cần đọc **một nút trang** ở mức tiếp theo nếu trang chưa có trong cache. Sau khi trang hiện diện, có thể so nhiều separator key mà **không đọc thêm trang**.

### 9.2. Fanout quyết định chiều cao

Gọi:

- `F`: số con trung bình/mức nội bộ trong mô hình lý tưởng.
- `L`: số bản ghi hoặc entry mỗi trang lá.
- `N`: tổng entry.

Số lá xấp xỉ `N/L`. Số tầng trang trên đường từ gốc đến lá xấp xỉ:

\[
H\approx1+\left\lceil\log_F\left(\left\lceil N/L\right\rceil\right)\right\rceil,
\]

với lưu ý công thức đếm tầng có thể khác một đơn vị ở các biên do định nghĩa root/leaf và làm tròn. Tốt nhất hãy **đếm trực tiếp các tầng thật** trong cấu hình cụ thể.

Để tránh nhầm dấu cộng khi `N/L` là lũy thừa đúng của F, có thể dùng cách xây tầng từ dưới lên: bắt đầu bằng số lá `L_0=\lceil N/L\rceil`, lặp `L_{i+1}=\lceil L_i/F\rceil` đến 1; **số phần tử của dãy tầng** chính là số trang trên một đường root-to-leaf khi cây đầy cân đối trong mô hình lý tưởng.

### 9.3. Không phải mọi B+ tree page chứa cùng số khóa

Nút nội bộ chứa separator key và child pointer; nút lá chứa key cộng row locator hoặc dữ liệu. Kích thước entry khác nhau, nên **fanout nội bộ F** và **sức chứa lá L** thường khác.

Cấu trúc thực tế cũng có header, slot directory, fill factor, khóa biến độ dài và split page. Không thể thay cả F và L bằng đúng `4096/100` nếu separator key nhỏ hơn record.

### 9.4. Bất biến giúp truy vấn đúng

Trong B+ tree, mỗi separator phân hoạch miền khóa của các trang con; các trang lá được sắp, và khi split/merge phải giữ:

- Thứ tự separator.
- Giới hạn số khóa/con mỗi nút theo quy tắc engine.
- Mọi bản ghi tìm được từ đúng đường.
- Các lá cùng độ sâu.
- Liên kết leaf phục vụ range scan không bỏ sót và không lặp.

Đếm I/O chỉ có nghĩa khi **bất biến chỉ mục vẫn đúng sau cập nhật**.

## 10. Vì sao cây tìm kiếm nhị phân không đủ cho on-disk?

Một BST cân bằng trên N khóa có chiều cao O(log N). Nếu mỗi nút nằm ở một trang khác nhau và trang chưa được cache, tìm một khóa có thể phải đọc O(log N) trang.

Trái lại, B+ tree đưa **nhiều separator key vào cùng một trang**. Nó có thể so thêm vài chục khóa trong RAM để quyết định chỉ một trang con tiếp theo.

Với ví dụ một triệu khóa:

```text
BST cân bằng:      khoảng 20 nút trên đường
B+ tree fanout 100: khoảng 4 trang trên đường
```

Đây là phép so **minh họa dưới giả định bố trí nút**; BST cũng có thể được pack nhiều nút vào một trang theo layout chuyên biệt, và tầng trên B+ tree có thể nằm trong RAM. Vì vậy cần so chi phí trên **biểu diễn thực tế**.

### 10.1. Tối ưu fanout không miễn phí

Trang/nút lớn có thể:

- Giảm chiều cao.
- Tăng số byte phải đọc trong một miss.
- Tốn CPU để so/search trong trang.
- Tăng write amplification khi split hoặc cập nhật.
- Tương tác với cache và page size.

Do đó không nên cứ tăng kích thước trang vô hạn. Fanout là một đánh đổi giữa **số tầng, dung lượng trang, locality và cập nhật**.

## 11. Index lookup khác đọc bản ghi dữ liệu

Một chỉ mục có thể chỉ chứa:

```text
(search_key, record_location)
```

sau đó phải dùng `record_location` để lấy payload từ trang dữ liệu.

Ví dụ tìm `employee_id=740000`:

1. Đọc các trang B+ tree để tìm entry.
2. Đọc **trang dữ liệu** chứa bản ghi nếu payload không nằm trong entry chỉ mục.

Nếu đường index gồm bốn trang cold, và trang dữ liệu ở chỗ khác, tổng có thể là **năm trang**. Nếu index leaf lưu đủ các cột cần trả (*covering index*), có thể không phải đọc trang dữ liệu.

### 11.1. Clustered và secondary index

- Với một kiểu **clustered index**, thứ tự dữ liệu và khóa chỉ mục có quan hệ locality thuận lợi.
- Với **secondary/nonclustered index**, các bản ghi ứng với khóa gần nhau có thể nằm rải rác trong nhiều data page.

Vì vậy cùng O(log_B N) cho phần **tìm index entry** không bảo đảm cùng số trang **đọc để trả toàn bộ bản ghi**.

### 11.2. Truy vấn trả một cột khác

```sql
SELECT email
FROM users
WHERE id = 740000;
```

Nếu leaf index chỉ có `id` và row ID, vẫn cần fetch `email` ở trang dữ liệu. Nếu index bao gồm `email` và chính sách lưu cho phép, index có thể **cover** truy vấn.

Lợi ích này phải được tính cùng **chi phí lưu thêm cột trong index**, ảnh hưởng fanout và số trang khi cập nhật.

## 12. Truy vấn khoảng: trang liên tục là lợi thế lớn

Giả sử cần các bản ghi có khóa trong khoảng `[10000,10800)`, tổng 800 bản ghi.

Trong một B+ tree có các lá sắp theo khóa:

1. Đi root-to-leaf tới khóa đầu: khoảng H trang cold.
2. Duyệt các trang lá kế tiếp theo thứ tự.
3. Xuất K bản ghi.

Nếu mỗi lá giữ 40 record, 800 record cần **khoảng 20–21 trang lá** tùy vị trí bắt đầu trong trang.

Chi phí I/O thường được mô hình hóa:

\[
I_{\mathrm{range}}
=O\left(\log_F N+\left\lceil K/L\right\rceil+1\right)
\]

khi dữ liệu cần trả **nằm ngay ở lá** hoặc được lưu theo thứ tự cụm phù hợp.

### 12.1. Vì sao có thể là 21 chứ không phải đúng 20?

Nếu đoạn 800 record bắt đầu ở đầu một trang, nó có thể phủ đúng 20 trang. Nếu bắt đầu ở giữa trang, nó có thể cần thêm trang cuối: **21 trang**.

Dùng `ceil(K/L)` chỉ là xấp xỉ khi không nêu vị trí bắt đầu; biểu thức có cộng hằng số sẽ bao quát lệch biên.

### 12.2. Range scan qua secondary index

Nếu 800 kết quả trỏ tới 800 trang dữ liệu khác nhau, phần fetch payload có thể tốn thêm gần **800 data page miss**, dù quét index leaf chỉ khoảng 20 trang.

Đây là lý do optimizer đôi khi chọn **full table scan** thay vì dùng secondary index đối với truy vấn trả quá nhiều dòng.

### 12.3. Khi query chỉ trả COUNT

Nếu chỉ hỏi `COUNT(*)` trên khoảng, một index có metadata đếm vùng hoặc cấu trúc bổ trợ có thể tránh việc fetch payload; nhưng không được tự suy mọi B+ tree có thể trả count của một khoảng bất kỳ trong O(log_B N) nếu **không lưu subtree counts** hoặc metadata tương đương.

## 13. Chỉ mục băm ngoài bộ nhớ: điểm mạnh và giới hạn

Một chỉ mục băm trên đĩa chia khóa vào bucket/page theo hash.

Với giả định bucket đủ chỗ, bảng băm được thiết kế phù hợp và directory có thể truy cập nhanh, tra cứu **khóa chính xác** có thể cần rất ít lần đọc bucket page — đôi khi gần **một lần đọc dữ liệu bucket** sau khi biết địa chỉ.

### 13.1. Tại sao không luôn dùng hash?

Hash **không giữ thứ tự khóa**. Những khóa từ 10000 tới 10800 có thể nằm ở rất nhiều bucket không liên tiếp.

Để làm range query, bảng băm thường không có cách đi qua một đoạn page theo thứ tự khóa; có thể phải quét nhiều bucket hoặc dùng index khác.

### 13.2. Collision và overflow

Khi bucket đầy, có thể xuất hiện overflow page; khi chia lại bucket hoặc resize, có thêm I/O. Do đó không được diễn giải “expected O(1) hash lookup” thành “luôn đúng một lần đọc trang”.

### 13.3. Hash page cũng có cache

Directory và một số bucket nóng có thể nằm trong RAM. Truy vấn nhiều lần cùng khóa có thể không phải đọc thiết bị. Đo page miss thực tế tốt hơn lấy số thao tác hash làm số trang đọc.

## 14. Số phép so không quyết định số I/O của nhiều truy vấn

Một workload thường là **hàng nghìn truy vấn liên tiếp**, không phải một truy vấn đứng một mình.

Giả sử cần tìm 5.000 khóa trong một file đã sắp.

Cách A: chạy 5.000 binary search độc lập, mỗi lần có thể chạm nhiều trang rải rác.

Cách B: sắp 5.000 khóa truy vấn, quét chúng cùng dữ liệu nguồn theo kiểu merge (nếu điều kiện phù hợp), hoặc nhóm những truy vấn nhắm cùng trang rồi xử lý cùng nhau.

Cách B có thể:

- Tăng số phép so thao tác gom nhóm/sort.
- Giảm số lần một trang bị đẩy ra rồi phải đọc lại.
- Chuyển nhiều random read thành scan.
- Tận dụng batching và locality.

### 14.1. Đánh đổi độ trễ với thông lượng

Batch thường tăng **throughput** nhưng có thể làm một yêu cầu riêng phải chờ tới khi gom đủ batch. Một ứng dụng tương tác yêu cầu latency thấp có thể chọn chiến lược khác với hệ thống phân tích offline.

### 14.2. Hash join và sort-merge join

Trong join lớn ngoài bộ nhớ, các thuật toán có thể ưu tiên:

- Phân hoạch dữ liệu theo hash để các nhóm nhỏ hơn vừa RAM.
- Sort hai đầu vào rồi merge tuần tự.
- Quét các block thay vì tra từng hàng riêng.

Mục tiêu là **giới hạn I/O ngẫu nhiên và số lần đọc lại**, ngay cả khi số thao tác CPU có thể tăng.

## 15. Vì sao sắp xếp ngoài bộ nhớ khác sắp xếp mảng trong RAM?

Với N bản ghi vượt quá RAM, không thể giữ cả mảng để chạy một `sort` thông thường mà không dùng I/O bổ sung.

**External merge sort** là ví dụ kinh điển cho việc thiết kế thuật toán quanh trang.

Giả sử RAM dùng cho thuật toán giữ được M bản ghi, đĩa có N bản ghi, mỗi block B bản ghi.

### 15.1. Giai đoạn 1: tạo các run đã sắp

1. Đọc tối đa M bản ghi từ đĩa vào RAM.
2. Sắp bằng thuật toán nội bộ.
3. Ghi thành một **run đã sắp** trên đĩa.
4. Lặp cho đến hết input.

Số run đầu xấp xỉ:

\[
R=\left\lceil\frac{N}{M}\right\rceil.
\]

Mỗi bản ghi được đọc và ghi một lần trong giai đoạn này, nên số block transfer xấp xỉ:

\[
2\left\lceil\frac{N}{B}\right\rceil
\]

nếu bỏ qua trang cuối không đầy, metadata và tối ưu ghi đầu ra trực tiếp.

### 15.2. Giai đoạn 2: merge nhiều run cùng lúc

Nếu bộ nhớ có thể giữ một block đầu vào cho mỗi run đang merge và một block đầu ra, số run có thể trộn đồng thời xấp xỉ:

\[
F\le\left\lfloor\frac{M}{B}\right\rfloor-1.
\]

Với F≥2, mỗi lượt merge tạo các run lớn hơn; số lượt cần là khoảng:

\[
\left\lceil\log_F R\right\rceil.
\]

Mỗi lượt thường đọc và ghi toàn bộ dữ liệu, khoảng `2N/B` block transfer.

### 15.3. Độ phức tạp I/O

Trong các giả định ngoại bộ phù hợp, chặn tổng quát của external sorting thường viết:

\[
\Theta\left(
\frac NB
\left(1+\log_{M/B}\frac NB\right)
\right)
\]

I/O cho dữ liệu lớn hơn RAM, hiểu rằng ký hiệu log được xử lý cùng các điều kiện biên và `M/B` đủ lớn để thực hiện multiway merge.

Điều đáng chú ý: thuật toán có thể làm nhiều phép so sánh trong RAM, nhưng thiết kế chủ yếu cố gắng giảm **số lượt quét đĩa**.

### 15.4. Ví dụ số trang

Cho tệp 100.000 trang, RAM cho phép giữ 1.000 trang:

- Có khoảng 100 run đầu, mỗi run 1.000 trang.
- Một lượt merge có thể xử lý tới khoảng 999 input run với các buffer một trang/nhánh và một output buffer.
- Vì chỉ có 100 run, **một lượt merge là đủ**.

Số page transfer lý tưởng:

```text
Run generation: 100,000 read + 100,000 write
Merge:         100,000 read + 100,000 write
Total:         400,000 page transfers
```

Ví dụ không tính trang metadata, thực hiện flush, filesystem cache hoặc tối ưu pipeline. Điều quan trọng là sắp xếp sử dụng **đọc và ghi liên tục theo lượt**, tránh việc phải đọc/ghi ngẫu nhiên một trang cho từng phép so.

## 16. Buffer pool, cache hit và cold/warm access

Một DBMS thường giữ một **buffer pool** chứa các trang vừa truy cập hoặc dự đoán sẽ cần. Hệ điều hành cũng có **page cache**, tùy chế độ I/O và engine.

Định nghĩa:

- **Page reference:** thuật toán yêu cầu truy cập một trang.
- **Page hit:** trang đã ở tầng cache đang xét.
- **Page miss:** không có trang, cần lấy từ tầng phía dưới.
- **Eviction:** đẩy một trang ra để có chỗ cho trang khác.

### 16.1. Một trang có thể được tham chiếu nhiều lần nhưng đọc một lần

Giả sử 40 phép so liên tiếp đều dùng bản ghi trong trang 7:

```text
Page references: 40
Cold page misses: 1
Cache hits after first load: 39
```

Nếu thiết bị/OS còn cache trang 7 từ trước, thậm chí miss đầu tiên ở tầng disk cũng không xảy ra.

### 16.2. Cold cache và warm cache

- **Cold cache:** bắt đầu khi các trang liên quan chưa ở cache đang đo.
- **Warm cache:** đã thực hiện truy vấn hoặc workload đủ để nhiều trang liên quan được giữ lại.

Một benchmark cold và một benchmark warm có thể cho thời gian chênh lệch rất lớn dù thuật toán không thay đổi.

### 16.3. Cache có dung lượng hữu hạn

Nếu bộ đệm chỉ giữ được 8 trang, rồi chương trình lần lượt duyệt 100 trang, các trang đầu có thể bị evict. Quay lại trang đầu có thể tạo miss mới.

Do đó số **trang phân biệt** không luôn bằng số **page miss** trong một workload dài: cùng một trang có thể bị nạp **nhiều lần** sau khi bị đẩy ra.

### 16.4. Chính sách thay thế

LRU (*least recently used*), CLOCK và các chiến lược thích ứng có thể dẫn tới số miss khác nhau. Một phép quét lớn còn có thể làm ô nhiễm cache nếu không có chính sách chống scan pollution.

Để benchmark, cần ghi **dung lượng buffer pool, chính sách cache và điều kiện khởi tạo**.

## 17. Sequential I/O, random I/O và đọc trước

Không phải mọi yêu cầu đọc cùng kích thước đều có chi phí giống nhau.

### 17.1. Truy cập tuần tự

Khi đọc các trang có địa chỉ liên tiếp, hệ thống có thể:

- Gom thành yêu cầu lớn.
- Prefetch các trang phía sau.
- Sử dụng băng thông truyền cao.
- Giảm overhead trên mỗi page.

Một scan 25.000 trang **không nhất thiết bằng** 25.000 lần chịu toàn bộ độ trễ của một random read độc lập.

### 17.2. Truy cập ngẫu nhiên

Khi truy cập trang 10, rồi 9000, rồi 200, rồi 7000, khó tận dụng đọc trước tuần tự. Trên HDD có thể có chi phí seek/rotational latency lớn; trên SSD không có đầu đọc cơ học nhưng random I/O vẫn chịu overhead controller, queue, firmware và phần mềm.

### 17.3. Đồng thời và queue depth

Thiết bị hiện đại có thể xử lý nhiều yêu cầu I/O đồng thời. Nếu ứng dụng phát nhiều read bất đồng bộ, thời gian tường **không bằng** số read nhân độ trễ một read.

Khi đo, nên phân biệt:

- Số yêu cầu I/O.
- Số byte đọc.
- Độ trễ trung bình và tail latency.
- Queue depth và mức đồng thời.
- Thông lượng (bytes/s, IOPS).
- Số page miss tại tầng cache được xét.

### 17.4. Dữ liệu ngoài bộ nhớ có thể nằm trên mạng

Nếu trang nằm ở remote object store hoặc một hệ thống phân tán, chi phí mỗi request còn có thể gồm RTT, phí gọi API, phân mảnh network và retry. Khi ấy **giảm số lần yêu cầu nhỏ** có thể quan trọng hơn việc tiết kiệm vài phép so sánh cục bộ.


## 18. Khi trang được ghi: dirty page và write amplification

Tập trung vào đọc trang không có nghĩa ghi trang là miễn phí. Với cập nhật bản ghi hoặc cấu trúc chỉ mục, DBMS thường đánh dấu trang là **dirty** và ghi lại sau.

### 18.1. Thay đổi vài byte có thể cần ghi cả trang

Trong nhiều engine, sửa một trường nhỏ có thể dẫn đến ghi page chứa trường ấy. Cơ chế ghi vật lý còn phụ thuộc WAL, redo log, copy-on-write, SSD filesystem và checkpoint.

Vì vậy một thao tác `update` chỉ so vài khóa có thể tạo:

- Ghi vào log.
- Sửa trang dữ liệu.
- Sửa một hoặc nhiều trang chỉ mục.
- Ghi trang ra thiết bị ở thời điểm khác.
- Split node hoặc ghi thêm metadata.

### 18.2. B+ tree và LSM-tree tối ưu những kiểu I/O khác nhau

B+ tree thường thuận tiện cho tra theo thứ tự và cập nhật page có cấu trúc ổn định, nhưng insert có thể chạm đường từ root tới leaf, split page và cập nhật cha.

LSM-tree (*Log-Structured Merge-Tree*) thường gom các cập nhật vào cấu trúc trong RAM rồi ghi **run sắp xếp** theo lô. Nó có thể giảm random write trong một số workload, nhưng phát sinh:

- **Compaction:** đọc và ghi lại dữ liệu để hợp nhất run.
- **Write amplification:** một bản ghi có thể được ghi nhiều lần trong vòng đời.
- **Read amplification:** truy vấn có thể cần xem nhiều run/tầng nếu thiếu index/filter/caching thích hợp.
- **Space amplification:** có thể có bản sao dữ liệu giữa các tầng trong quá trình merge.

Không nên suy “LSM luôn ít I/O hơn B+ tree”; đúng hơn, chúng phân phối chi phí đọc/ghi khác nhau và cần được so theo workload.

### 18.3. Chi phí của thiết bị không chỉ là page read

Một benchmark hoàn chỉnh có thể theo dõi **page reads, page writes, bytes moved, cache misses, flushes, compaction bytes** và độ trễ phân vị cao. Thuật toán giảm so sánh nhưng tăng nhiều lần ghi trang có thể kém phù hợp cho hệ thống ghi thường xuyên.

## 19. Đọc trước, nén và bộ nhớ đệm làm thay đổi đánh đổi

Hai cấu trúc có cùng số page miss logic vẫn có thể khác thời gian vì cách bố trí dữ liệu trong từng trang.

### 19.1. Nén dữ liệu

Nếu nén giảm số byte phải đọc, cùng một khối vật lý có thể chứa nhiều bản ghi logic hơn:

- **Ít page/byte I/O hơn** khi dữ liệu nén được tốt.
- **Tốn CPU** để giải nén.
- Có thể phải giải nén cả chunk để đọc một record nhỏ.
- Mức độ nén khác nhau theo loại dữ liệu, encoding và phân bố giá trị.

Vì thế chỉ nhìn số phép so sánh không thể dự đoán hiệu quả nén; cũng không nên chỉ nhìn số byte đã nén mà bỏ chi phí CPU.

### 19.2. Columnar storage

Một truy vấn chỉ cần cột `status` và `created_at` có thể được phục vụ từ **các trang/chunk chỉ chứa hai cột này**, thay vì đọc toàn bộ row payload.

Điều đó có thể làm giảm số byte/trang cần đọc, dù số hàng phải xét về mặt logic không thay đổi.

### 19.3. Read-ahead

Nếu engine biết sẽ đọc tiếp các trang kế nhau, nó có thể nạp sẵn. Read-ahead tăng tốc scan nhờ băng thông, nhưng có thể lãng phí tài nguyên với một truy vấn chỉ cần một record hiếm.

### 19.4. Gợi ý chọn kích thước trang

Không có page size tối ưu cố định:

- Trang nhỏ có thể tránh kéo quá nhiều dữ liệu không dùng khi truy vấn điểm.
- Trang lớn giúp giảm số lần xử lý header/truyền yêu cầu và tăng fanout.
- Trang lớn có thể gây read amplification và làm bộ đệm giữ được ít đơn vị cache hơn.
- Thiết bị và database engine thường có giới hạn riêng.

Lựa chọn cần đo theo **loại truy vấn, kích thước bản ghi, mức lấp đầy, băng thông và cache**, không chỉ theo công thức log.

## 20. Mô phỏng page cache để thấy rõ hai loại chi phí

Ta xây một mô hình học tập, **không đọc SSD/HDD thật**. Mỗi bản ghi chiếm một vị trí trong mảng; một trang chứa `records_per_page` vị trí liên tiếp. Bộ cache có dung lượng cố định và dùng **LRU**.

Ta đếm độc lập:

- `comparisons`: số bản ghi được so với khóa tìm.
- `page_references`: số lần thuật toán yêu cầu một trang.
- `page_hits`: số lần trang đang ở cache LRU.
- `page_misses`: số lần trang không có trong cache và được mô phỏng như phải nạp.

### 20.1. Vì sao cần mô phỏng?

Nếu chỉ dùng `time.perf_counter()` trên Python `list`, ta không biết một phép chạm vào list có tương ứng với **đọc thiết bị** hay không: dữ liệu có thể đã ở RAM từ đầu.

Mô phỏng giúp minh họa chính xác sự khác nhau giữa **lượt đọc bản ghi** và **lượt nạp trang**, không giả vờ đây là benchmark I/O vật lý.

### 20.2. Cài đặt LRU đơn giản

```python
from collections import OrderedDict


class PageLRU:
    """Mô phỏng bộ đệm tối đa capacity trang.

    Không đọc file, không đo disk latency thực.
    """

    def __init__(self, capacity):
        if type(capacity) is not int or capacity < 0:
            raise ValueError("capacity phải là int >= 0")

        self.capacity = capacity
        self.pages = OrderedDict()
        self.references = 0
        self.hits = 0
        self.misses = 0

    def touch(self, page_id):
        """Yêu cầu một page; ghi nhận hit/miss."""
        self.references += 1

        if page_id in self.pages:
            self.hits += 1
            self.pages.move_to_end(page_id)
            return

        self.misses += 1

        # Capacity 0: mọi tham chiếu đều là miss.
        if self.capacity == 0:
            return

        self.pages[page_id] = None

        if len(self.pages) > self.capacity:
            self.pages.popitem(last=False)

    def reset_stats(self):
        """Giữ cache hiện tại, xóa các bộ đếm."""
        self.references = 0
        self.hits = 0
        self.misses = 0

    def clear(self):
        """Xóa cache và bộ đếm để trở về cold."""
        self.pages.clear()
        self.reset_stats()
```

### 20.3. Ý nghĩa của từng phép `touch`

Mỗi lượt `touch(page_id)` chỉ đại diện một **yêu cầu truy cập trang ở tầng mô phỏng**. Nếu trang đang ở `pages`, đó là hit; nếu không, miss và thêm trang vào LRU.

Mô hình bỏ qua:

- OS page cache nằm ngoài buffer pool.
- Bộ nhớ CPU cache line.
- Read-ahead và ghi dirty page.
- Đọc bất đồng bộ, compression, filesystem.
- Chi phí eviction thực tế.

Vì vậy `PageLRU.misses` không tự là số lệnh đọc thiết bị mà một database thật sẽ phát ra.

## 21. Hai thuật toán tìm, cùng bảng dữ liệu mô phỏng

Ta dùng `values` đã sắp và giả định bản ghi thứ `i` thuộc trang:

\[
page(i)=\lfloor i/B\rfloor.
\]

### 21.1. Quét tuyến tính

```python
def linear_search(values, target, records_per_page, cache):
    """Trả (index, comparisons); -1 nếu thiếu."""
    if records_per_page <= 0:
        raise ValueError("records_per_page phải dương")

    comparisons = 0

    for i, value in enumerate(values):
        cache.touch(i // records_per_page)
        comparisons += 1

        if value == target:
            return i, comparisons

    return -1, comparisons
```

### 21.2. Tìm nhị phân trên mảng sắp

```python
def binary_search(values, target, records_per_page, cache):
    """Trả (index, comparisons); values phải tăng."""
    if records_per_page <= 0:
        raise ValueError("records_per_page phải dương")

    low = 0
    high = len(values) - 1
    comparisons = 0

    while low <= high:
        mid = (low + high) // 2

        cache.touch(mid // records_per_page)
        comparisons += 1

        if values[mid] == target:
            return mid, comparisons

        if values[mid] < target:
            low = mid + 1
        else:
            high = mid - 1

    return -1, comparisons
```

Mỗi vòng có một **lần so sánh ba ngả về mặt logic** để quyết định bằng/nhỏ/lớn. Mã Python có thể thực hiện hai phép toán `==` và `<`, vì vậy `comparisons` ở đây là số **lượt kiểm tra một record**, không phải tổng số lệnh so sánh máy thực thi.

Đây là quy ước đo cố ý: ta muốn đối chiếu số **record probes** với số page miss.

### 21.3. Thử nghiệm 1.024 bản ghi, 16 bản ghi/trang

```python
values = list(range(1024))
records_per_page = 16

scan_cache = PageLRU(capacity=8)
position_scan, comparisons_scan = linear_search(
    values, 1023, records_per_page, scan_cache
)

assert position_scan == 1023
assert comparisons_scan == 1024
assert scan_cache.references == 1024
assert scan_cache.misses == 64

binary_cache = PageLRU(capacity=8)
position_bin, comparisons_bin = binary_search(
    values, 1023, records_per_page, binary_cache
)

assert position_bin == 1023
assert comparisons_bin == 11
assert binary_cache.references == 11
assert binary_cache.misses == 7
```

Kết quả:

| Thuật toán | Lượt so record | Page references | LRU page misses cold |
| --- | ---: | ---: | ---: |
| Linear scan đến cuối | 1.024 | 1.024 | 64 |
| Binary search khóa cuối | 11 | 11 | 7 |

Trong mô hình này, binary search vừa ít phép so vừa ít page miss. Điểm rút ra là **11 phép so không đồng nghĩa 11 lần nạp trang**, và **1.024 phép so không đồng nghĩa 1.024 lần nạp trang**.

### 21.4. Vì sao binary search chỉ có bảy miss?

Các vị trí thử lần lượt:

```text
511  767  895  959  991  1007  1015  1019  1021  1022  1023
```

Chúng thuộc các trang:

```text
31   47   55   59   61   62    63    63    63    63    63
```

Chỉ có bảy trang phân biệt. Bộ LRU sức chứa tám trang không phải đẩy trang nào trong bảy trang ấy ra, nên có bảy miss.

### 21.5. Thử warm cache với cùng truy vấn

```python
binary_cache.reset_stats()

position_again, comparisons_again = binary_search(
    values, 1023, records_per_page, binary_cache
)

assert position_again == 1023
assert comparisons_again == 11
assert binary_cache.references == 11
assert binary_cache.misses == 0
assert binary_cache.hits == 11
```

Cùng **11 lượt so sánh**, nhưng truy vấn thứ hai có **0 miss ở cache LRU này** vì tất cả trang đã ở trong bộ đệm.

Đó là một minh họa trực tiếp cho việc **số phép so không đủ dự đoán số lần truy cập lưu trữ ngoài**.

## 22. Một trường hợp nhiều phép so nhưng ít page miss hơn

Xét **một bảng có 100 trang**, mỗi trang chứa 100 bản ghi: tổng 10.000 bản ghi. Một truy vấn cần trả **200 bản ghi**, phân bố đúng **hai bản ghi khớp trên mỗi trang**. Chỉ mục phụ biết 200 vị trí record nhưng **không chứa payload** cần trả.

### 22.1. Dùng secondary index không covering

Giả sử thứ tự record ID lấy từ chỉ mục khiến các **data page references** lần lượt là:

```text
0, 1, 2, ..., 99, 0, 1, 2, ..., 99
```

Đây là **200 lượt tham chiếu đến 100 trang phân biệt**, không phải 200 trang khác nhau. Nếu bộ đệm chỉ chứa tám trang, ban đầu rỗng và dùng LRU, khi quay lại trang 0 thì trang ấy đã bị đẩy ra từ lâu. Theo mô hình LRU này:

- 200 lượt fetch data page tạo **200 page miss ở tầng bộ đệm mô phỏng**.
- Cần thêm chi phí đọc các trang của secondary index.
- Số phép so sánh khóa trong phần index có thể ít hơn nhiều so với quét bảng.

### 22.2. Quét tuần tự cùng bảng

Một phép full scan đọc các trang `0,1,ldots,99` đúng một lần:

- Đánh giá điều kiện trên 10.000 record.
- Nạp **100 trang** khi cold trong mô hình ấy.
- Xuất chính 200 record khớp, không bỏ sót bản ghi nào.
- Có thể tận dụng đọc trước và truy cập tuần tự.

Ở đây phương án **so nhiều record hơn** lại **ít page miss hơn**: 100 thay vì 200, theo đúng giả định truy cập và dung lượng cache đã nêu.

### 22.3. Những điều kiện có thể đảo kết quả

Kết luận trên **không phải định luật chung**:

- Nếu optimizer gom/sắp row ID theo page, mỗi data page có thể chỉ nạp một lần.
- Nếu OS cache chứa các trang, page miss ở buffer pool không tương ứng cùng số lần đọc vật lý.
- Nếu index có đủ payload (*covering index*), không cần fetch 200 record từ data pages.
- Nếu bảng lớn hơn nhiều hoặc truy vấn chỉ trả vài record, index seek có thể thắng.
- Nếu phải trả kết quả theo thứ tự cụ thể, còn có thể phát sinh chi phí sắp xếp.

Ví dụ này chứng minh một ý chính: **đếm số phép so sánh không cho biết số lần page miss**, vì page có thể được chia sẻ, cache lại hoặc bị đẩy ra rồi nạp lại.

## 23. Một mô hình minh họa rõ hơn về chọn lọc và locality

Hãy xét một bảng có 1.000 trang, mỗi trang 40 record, tổng 40.000 record. Có chỉ mục phụ theo `status`.

### 23.1. Truy vấn điểm, chọn lọc rất cao

```sql
SELECT * FROM events WHERE event_id = 12345;
```

Nếu `event_id` là khóa có index tốt, cần tìm một hoặc rất ít record. Đọc vài trang index cộng một data page thường thuận lợi hơn quét 1.000 trang.

### 23.2. Truy vấn trả gần toàn bảng

```sql
SELECT * FROM events WHERE status = 'active';
```

Giả sử 90% record là active và các record phân tán. Tra secondary index để lấy từng row có thể tạo nhiều lần đọc data page, trong khi full scan đọc 1.000 trang tuần tự.

Nếu dùng index-only scan mà leaf chứa đủ các cột cần trả, kết luận có thể khác; phải kiểm tra **covering** và bố trí thật.

### 23.3. Truy vấn chỉ trả count

```sql
SELECT COUNT(*) FROM events WHERE status = 'active';
```

Nếu index cho phép đọc **chỉ các entry cần thiết** mà không phải fetch payload, việc quét index có thể rẻ hơn scan bảng vì index entry nhỏ hơn record đầy đủ.

Nhưng không mặc định một B+ tree có **subtree count** sẵn để trả ngay một số mà không đọc index entries: cần nêu metadata/thực thi cụ thể.

### 23.4. Cùng một câu SQL cũng có thể đổi kế hoạch

Query optimizer dựa trên:

- Phân bố khóa và ước lượng selectivity.
- Kích thước hàng và index.
- Page counts, clustering factor.
- Cache, chi phí random/sequential và số cột cần trả.
- Hỗ trợ index-only scan, sorting hoặc parallel scan.

Do đó kế hoạch tốt ở dữ liệu 10.000 record không chắc còn tốt ở 100 triệu record.

## 24. Bloom filter: tránh một số lần đọc trang không cần thiết

Một **Bloom filter** là cấu trúc xác suất hỗ trợ kiểm tra *có thể có khóa* hay *chắc chắn không có khóa* theo giả định cấu trúc được xây và duy trì đúng.

Khi tra một khóa không có trong tập:

- Nếu Bloom filter nói **không có**, có thể bỏ qua việc đọc bucket/run ở tầng lưu trữ.
- Nếu Bloom filter nói **có thể có**, vẫn phải đọc cấu trúc chính để xác minh.

### 24.1. Vì sao hữu ích ngoài bộ nhớ?

Bloom filter thường được thiết kế để ở RAM và dùng ít byte trên mỗi khóa. Nó có thể làm thêm nhiều phép băm trong CPU nhưng **tránh một lần đọc trang đắt tiền** cho một truy vấn âm.

Đây là một ví dụ rõ rằng tối ưu I/O có thể chủ động **tăng số phép toán CPU**.

### 24.2. Không được suy tính chất khi xóa sai cách

Bloom filter chuẩn không hỗ trợ xóa tùy ý bằng cách xóa bit trực tiếp: nhiều khóa có thể chia sẻ bit. Muốn xóa, cần biến thể phù hợp hoặc rebuild theo dữ liệu.

Khẳng định “không false negative” chỉ đúng khi dữ liệu và filter được duy trì theo đúng hợp đồng. Nếu filter bị stale sau ghi/xóa, tính chất có thể không còn.

### 24.3. False positive vẫn tạo I/O

Bloom filter có thể trả “có thể có” cho một khóa thật ra không tồn tại. Khi đó engine vẫn phải đọc dữ liệu để xác minh, nên filter **giảm kỳ vọng I/O** chứ không bảo đảm mỗi truy vấn âm có 0 disk I/O.

## 25. Mô hình độ phức tạp I/O: bảng so sánh

Quy ước:

- N record/entry.
- B entry mỗi trang trong mô hình lý tưởng.
- M entry RAM dùng cho thuật toán.
- K số record kết quả.
- F fanout của nút trong B+ tree.
- L entry mỗi trang lá.
- Cấu trúc chỉ mục đã được xây, cache không chứa trang dữ liệu liên quan.

| Thuật toán / thao tác | So sánh / công việc RAM | I/O trang điển hình |
| --- | --- | --- |
| Quét tất cả N record | Θ(N) lần kiểm tra | Θ(N/B) đọc tuần tự |
| Binary search trực tiếp trên file đã sắp | O(log N) lượt dò, mỗi so có chi phí khóa | O(log N) random page upper bound |
| B+ tree lookup | So separator tại mỗi tầng | O(log_F(N/L)+1) trang, thường gần O(log_B N) |
| B+ tree range K entry clustered/covering | Đi tới leaf rồi quét K entry | O(log_F(N/L)+K/L+1) |
| Secondary index range không covering | Truy vấn index + fetch payload | Thêm tới O(K) data-page I/O trong tình huống phân tán |
| Hash on-disk exact match | Kỳ vọng lookup tốt khi phân bố ổn | Có thể rất ít bucket I/O; phụ thuộc overflow/directory |
| Hash range query | Không có thứ tự khóa | Có thể cần quét nhiều bucket |
| External merge sort | Nhiều phép so trong RAM khi tạo/merge run | O((N/B)(1+log_{M/B}(N/B))) theo điều kiện mô hình |

**Đọc bảng đúng cách:** các công thức I/O đo **block transfer**, không đo số lệnh máy. Một page miss ở tầng DB buffer pool cũng không chắc dẫn đến đúng một lệnh đọc vật lý nếu OS cache hoặc read-ahead còn hoạt động.

### 25.1. Không dùng log_B nếu B không có cùng đơn vị

Trong B-tree lý thuyết, B thường là số **key/pointer có thể chứa trong một block**. Nếu trong ví dụ B lại là số **record payload 100 byte trên một trang**, không được mặc định internal node cũng chứa đúng B separator.

Dùng F (fanout) và L (entry/page lá) khi cần tính cụ thể hơn.

### 25.2. Truy vấn trả dữ liệu dài vẫn có cận dưới

Nếu cần trả K record, ứng dụng ít nhất phải xuất số byte tương ứng. Ngay cả khi index lookup mất O(1) I/O trong một tình huống cache thuận lợi, việc **materialize và truyền kết quả** không trở thành O(1).

## 26. Một quy trình benchmark thực tế

Benchmark cần trả lời **vấn đề vận hành nào**. Không nên chỉ chạy một vòng rồi kết luận cấu trúc A luôn tốt hơn B.

### 26.1. Xác định workload trước

Ghi lại:

- Tổng số record, kích thước trung bình và phân bố kích thước.
- Bố trí dữ liệu: clustered/unclustered, row/column store.
- Loại truy vấn: point, range, count, aggregation, batch lookup.
- Độ chọn lọc, số lượng kết quả, độ dài khóa.
- Tỉ lệ đọc/ghi và độ đồng thời.
- Bộ nhớ có sẵn, page size và cấu hình cache.

### 26.2. Đo cả CPU và I/O

Ít nhất nên quan sát:

| Nhóm | Đại lượng |
| --- | --- |
| CPU | Thời gian CPU, số record/key kiểm tra nếu đo được |
| Buffer cache | Page hits, page misses, evictions |
| Storage | Physical reads/writes, bytes, latency, throughput |
| Thời gian | Wall-clock latency, median, p95/p99 nếu cần |
| Dữ liệu | Pages allocated, fill factor, index size |
| Đầu ra | Số record trả về, bytes truyền, có sort hay không |
| Ghi | WAL bytes, page flush, compaction/rewrite khi phù hợp |

**Không đồng nhất logical reads với physical reads.** Có những hệ thống thống kê “logical page reads” là số lần engine tham chiếu trang đã có thể nằm trong buffer cache.

### 26.3. Thử cold và warm riêng

Với cold test, phải biết liệu cache nào thực sự lạnh:

- DB buffer pool.
- OS page cache.
- Cache controller/storage/network.
- Cache ở lớp ứng dụng.

Khởi động lại query không nhất thiết làm mọi cache lạnh. Tương tự, một phương pháp xóa OS cache có thể cần quyền hệ thống và ảnh hưởng tiến trình khác; không nên thao tác tùy tiện trên máy production.

### 26.4. Đo lặp lại và kiểm soát nhiễu

- Chạy nhiều vòng với cùng dataset.
- Trộn thứ tự chạy các phương án để giảm ảnh hưởng “phương án chạy sau hưởng cache”.
- Tách thời gian xây index khỏi thời gian query nếu cần.
- Giữ kết quả đầu ra và độ chọn lọc như nhau.
- Báo median/p95 thay vì chỉ một phép đo.
- Ghi cấu hình phần cứng/phần mềm kèm số đo.

### 26.5. Xem kế hoạch thực thi

Trong DBMS, kiểm tra **query plan** và thông số I/O do engine cung cấp. Một câu SQL khác có thể khiến optimizer đổi từ index seek sang table scan; nếu không đọc plan, rất dễ quy sai nguyên nhân cho thuật toán lý thuyết.

## 27. Những kết luận sai phổ biến

| Nhận định | Vấn đề | Điều cần làm rõ |
| --- | --- | --- |
| “O(log N) luôn nhanh hơn O(N).” | Big-O đếm thao tác gì? dữ liệu ở đâu? | Phân biệt CPU và page I/O |
| “Mỗi phép so sánh là một lần đọc đĩa.” | Nhiều record cùng một page | Đếm page miss |
| “Một triệu phép so tương đương một triệu page read.” | Scan dùng lại page | Tính N/B |
| “B+ tree chỉ cần bốn phép so.” | Một node/page chứa nhiều separator | Bốn là số trang trên đường ví dụ |
| “B+ tree luôn phải đọc bốn trang từ SSD.” | Root/internal page có thể cache | Đo cold/warm và page hits |
| “Index seek không phải đọc table.” | Secondary index có thể thiếu payload | Kiểm tra covering |
| “Index luôn thắng full scan.” | Selectivity thấp, random fetch nhiều | Đo data pages |
| “Range K record luôn K lần đọc.” | Các record có thể cùng page | Xét clustering |
| “Các page read có cùng thời gian.” | Random/sequential khác latency | Đo bytes/s và IOPS |
| “25.000 page read tuần tự = 25.000 random read.” | Read-ahead và batching | Phân biệt kiểu I/O |
| “Page miss luôn là physical disk read.” | OS cache hoặc tầng khác có thể hit | Ghi tầng cache được đo |
| “Cùng O(N) bộ nhớ là cùng byte.” | Trang, header, pointer và fill factor | Đo allocated pages |
| “B càng lớn càng tốt.” | Read amplification và CPU có thể tăng | Benchmark page size |
| “Hash luôn một I/O.” | Collision, overflow, directory | Nêu giả định |
| “Bloom filter có thể thay dữ liệu thật.” | Có false positive | Luôn xác minh positive |
| “Bloom filter xóa khóa bằng xóa bit.” | Gây false negative cho khóa khác | Dùng biến thể hỗ trợ xóa |
| “External sort chỉ cần O(N log N) so sánh.” | Bỏ số lượt đọc/ghi run | Phân tích N/B và M/B |
| “Time = I/O count × một hằng số đoán trước.” | Đồng thời, prefetch, bandwidth | Đo wall time thật |
| “So một query là đủ chọn index.” | Cache, phân bố và concurrency khác | Đo workload đại diện |
| “Mô phỏng LRU là số disk read thật.” | Mô hình bỏ OS, read-ahead và thiết bị | Ghi rõ tính minh họa |

## 28. Ba tình huống quyết định cấu trúc

### 28.1. Hệ thống tra hồ sơ theo ID

**Yêu cầu:** hàng chục triệu record, đa số point lookup theo `id`, cần độ trễ thấp.

**Lựa chọn cần đánh giá:** B+ tree hoặc chỉ mục băm phù hợp; giữ tầng root/directory nóng trong RAM; nếu cần toàn record, xem xét clustered/covering index.

**Không nên:** quét toàn bảng cho từng ID nếu chỉ có một kết quả và dữ liệu không nằm hết RAM.

### 28.2. Hệ thống báo cáo quét nhiều bản ghi

**Yêu cầu:** tính tổng, thống kê và lọc các trường trên phần lớn dữ liệu.

**Lựa chọn cần đánh giá:** scan tuần tự, columnar layout, predicate pushdown, nén và batch processing.

**Không nên:** mặc định dùng secondary index rồi fetch từng hàng nếu truy vấn chạm quá nhiều data page rải rác.

### 28.3. Hệ thống ghi sự kiện liên tục

**Yêu cầu:** rất nhiều append, batch write, đôi khi đọc theo khoảng thời gian.

**Lựa chọn cần đánh giá:** cấu trúc log/LSM, dữ liệu phân vùng theo thời gian, index hỗ trợ range scan và compaction phù hợp.

**Không nên:** chỉ đếm phép so sánh của insert mà bỏ WAL, ghi trang, compaction và write amplification.

## 29. Bài tập có gợi ý giải

### Bài 1 — Một trang chứa bao nhiêu record?

Mỗi record 100 byte, trang 4096 byte, không tính overhead và không cắt record qua trang. Một trang chứa tối đa bao nhiêu record?

**Gợi ý:** `floor(4096/100)=40`.

### Bài 2 — Số trang quét

Có một triệu record, 40 record/trang. Quét hết cần đọc khoảng bao nhiêu trang cold?

**Gợi ý:** `1,000,000/40=25,000` trang.

### Bài 3 — Phép so và page miss

Quét 40 record cùng một trang cold. Có 40 phép kiểm tra. Số page miss lý tưởng là bao nhiêu?

**Gợi ý:** Một miss khi nạp trang, những record tiếp theo có thể hit.

### Bài 4 — Binary search truy cập trang

Mảng 1024 record, 16 record/trang. Khi tìm 1023 bằng binary search, có 11 lượt dò nhưng bảy trang phân biệt. Tại sao?

**Gợi ý:** Các lượt dò cuối cùng đều thuộc trang 63.

### Bài 5 — Warm cache

Chạy lại cùng binary search khi cả bảy trang còn trong bộ đệm. Số phép so và số miss là gì?

**Gợi ý:** Vẫn 11 lượt so record; 0 miss ở cache đang xét.

### Bài 6 — Chi phí CPU giả định

Một triệu phép so mất 5 ns/lượt trong mô hình đơn giản. Tổng thời gian bao nhiêu?

**Gợi ý:** 5 ms; đây là giả định minh họa, không phải benchmark.

### Bài 7 — Chi phí đọc ngẫu nhiên giả định

Có 100 lần đọc tuần tự độc lập, mỗi lần giả định 200 µs và không chồng lấn. Tổng thời gian?

**Gợi ý:** 20 ms. Nếu concurrent hoặc sequential readahead, không nên nhân máy móc.

### Bài 8 — B+ tree fanout

Có 25.000 trang lá, fanout 100. Hãy tìm số trang ở mỗi tầng phía trên.

**Gợi ý:** 250 trang cha, rồi 3, rồi 1 root; một đường có bốn trang.

### Bài 9 — Tại sao B+ tree không chỉ so bốn lần?

Giả sử đường root-to-leaf dài bốn trang. Tại sao số phép so khóa có thể lớn hơn bốn?

**Gợi ý:** Mỗi trang có nhiều separator; có thể phải so nhiều separator trước khi chọn con.

### Bài 10 — Secondary index

Một index lookup đã tìm row ID nhưng truy vấn yêu cầu một cột không có trong index. Còn phải làm gì?

**Gợi ý:** Đọc data page chứa payload, trừ khi có cách truy xuất khác/covering index.

### Bài 11 — Range scan

800 record liên tiếp, 40 record/trang. Số trang lá tối thiểu và mức chênh nếu bắt đầu giữa trang?

**Gợi ý:** 20 trang nếu căn đúng biên; có thể 21 trang nếu lệch.

### Bài 12 — Index vs scan

Truy vấn trả 90% bảng, dữ liệu rải rác. Vì sao full scan có thể hợp lý?

**Gợi ý:** Đọc tuần tự một lần có thể rẻ hơn nhiều random fetch sau secondary index.

### Bài 13 — Hash và range

Tại sao hash table trên đĩa thường tốt cho exact match nhưng không thuận tiện cho range query?

**Gợi ý:** Hash phá thứ tự khóa; các giá trị trong khoảng không ở những bucket liền nhau.

### Bài 14 — External sorting

Tệp 100.000 trang, RAM giữ 1000 trang, mỗi run 1000 trang. Có bao nhiêu run đầu?

**Gợi ý:** 100 run.

### Bài 15 — Số lượt merge

RAM giữ 1000 trang; để một output buffer và một input buffer/run, có thể merge cùng lúc tối đa bao nhiêu run theo mô hình đơn giản?

**Gợi ý:** Khoảng 999 run; nhiều hơn 100 run đầu của Bài 14, nên chỉ cần một lượt merge.

### Bài 16 — Page transfers của external sort

Trong Bài 14–15, nếu tạo run đọc+ghi toàn bộ và một lượt merge cũng đọc+ghi toàn bộ, số lần truyền trang?

**Gợi ý:** `4×100,000=400,000` block transfers lý tưởng.

### Bài 17 — Distinct pages và misses

Bộ cache chỉ chứa hai trang, chương trình tham chiếu `1,2,3,1`. Có bao nhiêu trang phân biệt, và bao nhiêu miss dưới LRU cold?

**Gợi ý:** Ba trang phân biệt nhưng bốn miss: trang 1 đã bị evict trước khi quay lại.

### Bài 18 — Bloom filter

Tại sao thêm các phép băm trong RAM có thể làm truy vấn âm nhanh hơn?

**Gợi ý:** Có thể tránh đọc trang dữ liệu khi filter chắc chắn báo không tồn tại.

### Bài 19 — False positive

Bloom filter báo “có thể có”. Có được trả True cho truy vấn membership ngay không?

**Gợi ý:** Không; phải kiểm tra dữ liệu thật vì có false positive.

### Bài 20 — Row store và column store

Một truy vấn chỉ cần hai cột trong record có 40 cột. Vì sao column store có thể tiết kiệm I/O?

**Gợi ý:** Chỉ đọc cột cần dùng, giảm byte/trang vận chuyển.

### Bài 21 — Chọn cache measurement

Một truy vấn có 100 logical page reads nhưng 0 physical reads. Điều gì có thể xảy ra?

**Gợi ý:** Các trang đã có trong DB buffer pool hoặc OS cache; khái niệm logical/physical tùy engine.

### Bài 22 — Ghi ngoài bộ nhớ

Một insert chỉ cần vài phép so nhưng phát sinh WAL, page split hoặc compaction. Tại sao không nên chỉ đếm so sánh?

**Gợi ý:** Chi phí ghi trang và I/O làm thay đổi độ trễ/throughput.

### Bài 23 — Xác định nút thắt

Một hệ chạy chậm nhưng gần như mọi trang đều hit RAM, CPU 100%. Có nên tối ưu số disk page reads trước không?

**Gợi ý:** Có thể không; cần đo CPU, so sánh khóa, giải nén và cache line. Tối ưu đúng bottleneck.

### Bài 24 — Mô hình đọc đồng thời

Tại sao 100 I/O yêu cầu không nhất thiết tốn 100 lần thời gian của một yêu cầu?

**Gợi ý:** Queue depth, bất đồng bộ và song song hóa; số I/O và wall time là hai đại lượng khác nhau.

## 30. Checklist khi phân tích thuật toán ngoài bộ nhớ

```text
1. Hợp đồng:
   - Point lookup, range, count hay scan?
   - Có cần trả toàn record hay chỉ một vài cột?
   - Kết quả có cần thứ tự tăng?
   - Tỉ lệ đọc/ghi và độ đồng thời là bao nhiêu?

2. Dữ liệu:
   - N record; kích thước phân bố của record?
   - Trang B byte; số entry thực trên một trang?
   - Fill factor, header, slot directory đã tính?
   - Dữ liệu clustered hay unclustered?
   - Index entry có cover truy vấn không?

3. Mô hình chi phí:
   - Đang đếm comparisons, page references hay page misses?
   - Page miss ở DB buffer hay physical storage?
   - Có tính bytes read và sequential/random không?
   - CPU và I/O có thể overlap không?
   - Có tính chi phí kết quả K record?

4. Cấu trúc:
   - B+ tree fanout F và leaf capacity L?
   - Root/upper levels có thường nằm RAM không?
   - Hash có bucket overflow/directory read không?
   - LSM có compaction và filter không?
   - Range scan có thể duyệt leaf liên tiếp không?

5. Cache:
   - Buffer pool bao nhiêu trang?
   - Cold hay warm workload?
   - Có readahead hoặc OS cache riêng?
   - Trang bị evict rồi đọc lại bao nhiêu lần?
   - Một lần benchmark có làm nóng lần sau không?

6. Đo:
   - Có số liệu logical reads / physical reads?
   - Có đo wall-clock latency và throughput?
   - Có tách build index và query?
   - Có giữ cùng số record/byte kết quả?
   - Có chạy nhiều vòng và báo phân vị?
   - Query plan có đúng chiến lược được so không?

7. Kết luận:
   - Đã giải thích vì sao chọn cấu trúc?
   - Đã nêu giả định trang/B/M/F/L?
   - Có tránh so Big-O khác đơn vị?
   - Có đo bộ nhớ đỉnh/giữ lại nếu liên quan?
   - Có dự báo khi n, cache và selectivity đổi?
```

## 31. Tổng kết

**Số lần đọc trang có thể quan trọng hơn số phép so sánh vì một lần I/O chuyển một đơn vị dữ liệu lớn và có thể mang chi phí trễ cao**, trong khi nhiều phép so trên dữ liệu đã ở RAM tương đối rẻ. Trong một page chứa B record, quét B record có thể cần B phép so nhưng chỉ **một lần nạp page**.

Những hệ quả quan trọng:

- **Quét tuần tự** có thể dùng O(N) phép so nhưng chỉ O(N/B) page transfers, thường tận dụng locality và read-ahead.
- **Binary search** dùng O(log N) lượt so nhưng có thể nhảy qua nhiều trang khác nhau; mức độ cache quyết định số miss thật.
- **B+ tree** gom nhiều separator key trong một trang, tăng fanout và giảm số trang trên đường root-to-leaf, thường gần O(log_B N) I/O.
- **Secondary index** có thể giúp định vị hàng nhanh nhưng vẫn phải fetch data page, nhất là khi query không được cover.
- **Truy vấn khoảng và batch** cần xét clustering, thứ tự truy cập và kích thước kết quả, không chỉ số phép so.
- **External merge sort** tổ chức thành những lượt đọc/ghi tuần tự vì block transfers là tài nguyên chi phối.
- **Cache, SSD/HDD, nén, ghi trang và mức đồng thời** quyết định sự khác biệt giữa số miss logic và thời gian vật lý.

Khi chọn cấu trúc dữ liệu, hãy hỏi trước **dữ liệu nằm ở đâu, một trang chứa gì, truy vấn chạm những trang nào và bao nhiêu trang có thể nằm sẵn trong RAM**. Chỉ khi đó phép đếm so sánh mới được đặt vào đúng bối cảnh.

Một thiết kế tốt không nhất thiết giảm mọi phép toán CPU; đôi khi nó **chủ động làm nhiều phép so hơn trên một trang vừa nạp** để tránh phải chờ nhiều lần đọc trang từ bộ nhớ ngoài.
