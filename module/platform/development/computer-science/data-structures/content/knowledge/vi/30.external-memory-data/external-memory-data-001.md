# Phân cấp thanh ghi, bộ nhớ đệm, RAM và thiết bị lưu trữ

## 1. Vì sao cùng một phép đọc dữ liệu lại nhanh hoặc chậm khác nhau?

Hai chương trình cùng thực hiện một triệu phép truy cập phần tử, cùng có độ phức tạp lý thuyết `O(n)`, nhưng thời gian chạy có thể chênh lệch đáng kể. Nguyên nhân là **“đọc một phần tử” không có chi phí cố định trên mọi tầng bộ nhớ**.

Hãy tưởng tượng đang đọc một quyển sách:

- Thông tin đang ghi nhớ trong đầu: truy cập gần như tức thời.
- Một tờ giấy ngay trên bàn: gần, nhưng vẫn cần với tay.
- Cuốn sách trên giá: phải đứng lên lấy.
- Cuốn sách cất trong kho xa: phải chờ vận chuyển.

Máy tính cũng hoạt động theo **phân cấp lưu trữ**:

```text
               Gần CPU, rất nhanh, rất nhỏ
                          │
                    THANH GHI
                      Registers
                          │
                      CACHE L1
                          │
                      CACHE L2
                          │
                   CACHE L3 / LLC
                          │
                         RAM
                          │
             THIẾT BỊ LƯU TRỮ KHỐI
                   SSD / HDD
                          │
           Lưu trữ từ xa / đối tượng / mạng
             Xa CPU, thường chậm hơn nhiều
```

Sơ đồ biểu diễn **xu hướng**, không phải tuyến đường bắt buộc của tất cả máy. Có CPU không có đủ ba cấp cache; hệ thống NUMA, GPU, bộ nhớ gắn qua mạng và nhiều cơ chế DMA có đường đi phức tạp hơn.

**Vấn đề trung tâm:** CPU có thể thực hiện phép tính rất nhanh, nhưng phải chờ dữ liệu nếu dữ liệu không nằm ở tầng lưu trữ gần. Vì thế, thiết kế cấu trúc dữ liệu cần xét **truy cập theo khối, tính cục bộ, chi phí cấp phát và số lần I/O**, không chỉ số phép so sánh trong ký hiệu Big-O.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt chức năng, dung lượng, độ trễ và tính bền vững của **register, CPU cache, RAM, SSD và HDD**.
2. Giải thích **cache line, hit/miss, temporal/spatial locality, prefetch, write-back** và ý nghĩa của cache coherence.
3. Phân biệt **địa chỉ ảo, TLB, trang bộ nhớ, page fault, OS page cache và khối I/O trên thiết bị lưu trữ**.
4. Phân tích vì sao truy cập tuần tự thường khác truy cập ngẫu nhiên, nhưng không tuyệt đối hóa sự khác biệt.
5. Tính một ví dụ **average memory access time (AMAT)** với các tỷ lệ miss có điều kiện.
6. Mô hình hóa **số lần truyền khối I/O** bằng `N,M,B` và so sánh quét, tìm kiếm, sắp xếp ngoài RAM.
7. Hiểu tại sao **B-tree/B+ tree, external merge sort và các cấu trúc dạng khối** phù hợp cho tập dữ liệu lớn.
8. Phân biệt **mô hình tiệm cận** với chi phí phần cứng thật, đánh giá benchmark có xét cache lạnh/nóng, độ trễ và thông lượng.
9. Lựa chọn bố trí dữ liệu phù hợp với workload thay vì coi `O(1)` và `O(\log n)` là toàn bộ câu chuyện.

Đây là bài thuộc chương **Dữ liệu ngoài bộ nhớ** của học phần **Cấu trúc dữ liệu**. Học phần xây dựng nền tảng qua mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, nhấn mạnh bất biến, thao tác, độ phức tạp thời gian và bộ nhớ; bài này bổ sung góc nhìn **dữ liệu thực sự nằm ở đâu và được chuyển giữa các tầng ra sao**.

## 2. Ba đại lượng phải phân biệt: dung lượng, độ trễ và băng thông

Khi so sánh hai tầng bộ nhớ, hãy tách ba câu hỏi:

**Dung lượng (capacity):** tầng này chứa được bao nhiêu dữ liệu?

**Độ trễ (latency):** mất bao lâu từ khi yêu cầu một dữ liệu đến khi dữ liệu cần thiết sẵn sàng? Ví dụ, độ trễ của một lần đọc ngẫu nhiên có thể chi phối dù dữ liệu chỉ vài byte.

**Băng thông (bandwidth/throughput):** có thể truyền bao nhiêu byte trong một giây khi pipeline hoạt động? Băng thông cao không đồng nghĩa một yêu cầu nhỏ đơn lẻ hoàn thành nhanh.

Ngoài ra còn có:

- **Độ bền (persistence/durability):** dữ liệu có tồn tại sau khi mất điện hay tắt tiến trình không?
- **Granularity:** mỗi lần truyền/ánh xạ/xóa dữ liệu thường ở đơn vị nào?
- **Tính chia sẻ và cạnh tranh:** bao nhiêu lõi/tiến trình đang dùng chung tài nguyên?
- **Chi phí năng lượng, giá thành và độ hao mòn:** đặc biệt quan trọng với lưu trữ lâu dài.

### Các bậc độ lớn minh họa

| Tầng | Dung lượng điển hình | Độ trễ minh họa | Vai trò |
|---|---|---|---|
| Thanh ghi CPU | Rất nhỏ, theo kiến trúc | Vài chu kỳ hoặc ít hơn tùy phụ thuộc lệnh | Toán hạng đang xử lý |
| L1 cache | Vài chục KiB mỗi lõi | Cỡ vài chu kỳ | Dữ liệu/lệnh truy cập rất gần |
| L2 cache | Hàng trăm KiB đến vài MiB | Vài đến hơn chục chu kỳ | Cache cấp trung gian |
| L3/LLC | Vài MiB đến hàng chục hoặc nhiều hơn | Hàng chục chu kỳ, phụ thuộc hệ thống | Cache cấp cuối, thường chia sẻ |
| RAM (DRAM) | GiB đến TiB tùy máy | Cỡ hàng chục đến hơn một trăm ns | Bộ nhớ chính đang hoạt động |
| SSD | Hàng trăm GiB đến nhiều TiB | Cỡ hàng chục–hàng trăm µs cho một yêu cầu nhỏ, rất tùy thiết bị | Lưu trữ bền vững, I/O theo khối |
| HDD | Hàng trăm GiB đến nhiều TiB | Thường cỡ vài ms cho truy cập cơ học ngẫu nhiên | Lưu trữ bền vững, truy cập tuần tự thuận lợi hơn |

**Lưu ý:** Đây là **bậc độ lớn để hình dung**, không phải thông số chuẩn cho mọi CPU, mọi SSD hay mọi cấu hình. CPU có nhiều kiểu cache, latency khi hit khác latency toàn hệ thống; NVMe, SATA, bộ điều khiển, tải song song, cache thiết bị và cơ chế flush đều làm kết quả thực tế thay đổi. Hãy đo trên máy và workload mục tiêu khi quyết định tối ưu hóa.

### Ví dụ độ trễ và thông lượng không giống nhau

Giả sử một thao tác đọc `4 KiB` mất `100 µs` nếu thực hiện riêng lẻ, bỏ qua chi phí ngoài thiết bị. Thông lượng của **một yêu cầu tuần tự không chồng lấp** là:

\[
\frac{4\times1024\ \text{byte}}{100\times10^{-6}\ \text{s}}
\approx 40.96\ \text{MB/s}.
\]

Tuy nhiên, thiết bị có thể xử lý **nhiều yêu cầu đồng thời**, giúp thông lượng tổng lớn hơn mức trên. Ngược lại, truyền một tệp lớn tuần tự có thể tận dụng pipeline và băng thông tốt hơn dù mỗi thao tác đọc riêng lẻ vẫn có độ trễ.

**Không dùng thông lượng tối đa quảng cáo để suy ra latency của một lần đọc 4 KiB.**

## 3. Thanh ghi CPU: nơi toán hạng đang được sử dụng

**Thanh ghi** (*register*) là vùng lưu trữ nhỏ gắn trực tiếp với việc thực thi lệnh của lõi CPU. Chúng thường chứa:

- Các toán hạng số nguyên, dấu phẩy động, vector.
- Địa chỉ/con trỏ đang được tính.
- Kết quả trung gian của vòng lặp.
- Trạng thái điều khiển đặc biệt do kiến trúc quy định.

Ví dụ ý tưởng:

```text
sum = 0
for i in range(n):
    sum += A[i]
```

Trong mã máy tối ưu, **biến tích lũy** `sum` có thể giữ trong thanh ghi qua nhiều vòng lặp; các phần tử `A[i]` được nạp từ hệ thống bộ nhớ. Nhưng không có quy tắc “mọi biến cục bộ đều luôn nằm trong thanh ghi”:

- Trình biên dịch hoặc runtime quyết định ánh xạ biến/giá trị vào thanh ghi.
- Nếu số giá trị sống vượt khả năng quản lý thanh ghi, một số giá trị có thể bị **spill** ra vùng nhớ.
- Kiến trúc vector/SIMD có thanh ghi riêng cho nhiều toán hạng.
- Trong Python, biến `sum` ở mức ngôn ngữ là một tham chiếu đối tượng theo mô hình runtime; không thể suy trực tiếp vị trí thanh ghi của nó từ cú pháp nguồn.

**Ý nghĩa với cấu trúc dữ liệu:** nếu một phép xử lý có thể giữ các kết quả trung gian nhỏ gần CPU và duyệt dữ liệu tuần tự, máy có cơ hội tận dụng register/cache tốt hơn. Nếu phải nhảy qua nhiều nút cấp phát rải rác, CPU thường phải chờ dữ liệu từ các tầng xa hơn.

## 4. CPU cache: bản sao của dữ liệu ở tầng gần CPU

**Bộ nhớ đệm CPU (cache)** giữ những bản sao dữ liệu/lệnh từ các tầng nhớ phía sau, giúp nhiều truy cập không phải xuống RAM.

Một sơ đồ khái niệm:

```text
CPU muốn đọc địa chỉ x
        |
        v
  Cache gần nhất có dữ liệu?
      /        \
    Có        Không
    |           |
  HIT         MISS
    |           |
   Đọc      Thử cache cấp sau
              |
          Nếu vẫn miss
              |
              v
           Truy cập RAM
              |
       Nạp khối liên quan
              |
              v
           CPU dùng dữ liệu
```

Với một địa chỉ:

- **Cache hit:** dữ liệu đã ở tầng cache cần xét.
- **Cache miss:** tầng cache không có dữ liệu hợp lệ, phải lấy ở tầng tiếp theo hoặc chờ hệ thống coherence.

Trong CPU hiện đại, các tầng cache có thể **không thuần túy bao hàm nhau**, có đường cấp dữ liệu giữa lõi hoặc prefetch, nên sơ đồ trên chỉ là mô hình đơn giản.

### Vì sao phải có nhiều tầng cache?

Tăng dung lượng cache thường làm tăng chi phí truy cập, điện năng, diện tích chip hoặc độ phức tạp. L1 được thiết kế rất gần và nhanh; L2/L3 thường rộng hơn nhưng có latency lớn hơn. Phân tầng là một cách đánh đổi **tốc độ–dung lượng–chi phí**.

### Cache không phải “RAM thu nhỏ” do lập trình viên phải tự sao chép bằng tay

Với phần lớn mã CPU thông thường, phần cứng quản lý việc nạp/thay thế cache line theo truy cập. Bạn không trực tiếp quyết định chính xác một phần tử nằm ở dòng cache nào. Bạn có thể **tác động gián tiếp** bằng bố trí dữ liệu, thứ tự duyệt, prefetch, alignment, kích thước working set và cách chia công việc.

## 5. Cache line: vì sao đọc một byte có thể mang về cả khối?

CPU cache thường chuyển dữ liệu theo **cache line**, không theo từng biến riêng lẻ. Nhiều CPU phổ biến dùng line dài **64 byte**, nhưng kích thước và chi tiết thay đổi theo kiến trúc.

Giả sử minh họa line `64 byte` và mảng phần tử mỗi phần tử `8 byte` được căn chỉnh phù hợp:

```text
Cache line 64 B
+----+----+----+----+----+----+----+----+
|A[0]|A[1]|A[2]|A[3]|A[4]|A[5]|A[6]|A[7]|
+----+----+----+----+----+----+----+----+
       8 byte mỗi phần tử
```

Lần đầu đọc `A[0]` có thể gây miss và nạp **cả line**. Sau đó `A[1]` đến `A[7]` có cơ hội hit nếu line chưa bị đẩy ra.

Đây là cơ sở của **tính cục bộ không gian** (*spatial locality*): truy cập một địa chỉ thường đi kèm khả năng truy cập các địa chỉ lân cận.

### Cẩn thận với giả định “8 phần tử/line”

Con số ấy chỉ đúng trong ví dụ:

- Mỗi phần tử chiếm đúng `8 byte` trong bộ nhớ liên tiếp.
- Dữ liệu được căn chỉnh để một nhóm tám phần tử khớp line.
- Không có padding hoặc metadata xen vào.

Một `list` Python thông thường giữ **tham chiếu tới đối tượng**, không phải mảng số nguyên `int64` phẳng. Vì vậy, không thể lấy hình trên rồi kết luận `list[int]` Python chắc chắn có tám số nguyên nằm trong một cache line.

### Cache line và page là hai đơn vị khác nhau

Đừng trộn:

- **Cache line:** đơn vị chuyển/lưu trong cache CPU, ví dụ minh họa `64 B`.
- **Trang bộ nhớ ảo (page):** đơn vị ánh xạ và bảo vệ bộ nhớ của hệ điều hành/MMU, ví dụ thường gặp `4 KiB`.
- **Khối I/O của hệ thống file/thiết bị:** đơn vị khác nữa, có thể `4 KiB` hoặc lớn hơn tùy filesystem, giao diện và thao tác.

Các đơn vị có thể chia hết cho nhau trong một máy cụ thể, nhưng **không mang cùng chức năng**.

## 6. Temporal locality và spatial locality

Hai quy luật quan trọng để dự đoán hiệu quả cache:

### Tính cục bộ theo thời gian (temporal locality)

Một dữ liệu vừa được sử dụng có khả năng được sử dụng lại sớm.

```text
counter = counter + 1
counter = counter + 1
counter = counter + 1
```

Nếu `counter` hoặc cache line chứa nó được sử dụng lặp lại và còn trong cache, các truy cập tiếp theo có thể rẻ hơn.

### Tính cục bộ theo không gian (spatial locality)

Sau khi dùng một địa chỉ, chương trình có xu hướng dùng các địa chỉ gần đó.

```text
for i in range(n):
    process(A[i])  # Duyệt mảng liên tiếp.
```

Một lần nạp line có thể phục vụ nhiều phần tử lân cận.

### Ví dụ thiếu cục bộ

```text
p = linked_list.head
while p is not None:
    process(p.value)
    p = p.next
```

Nếu các nút liên kết nằm rải rác, mỗi lần đi `next` có thể trỏ đến một line rất khác và khó dự đoán trước. Dù thuật toán vẫn `O(n)` phép bước qua nút, khả năng tận dụng cache line và prefetch có thể kém hơn mảng liên tiếp.

**Không phải danh sách liên kết luôn chậm hơn mảng trong mọi trường hợp:** kích thước dữ liệu, kiểu thao tác, vị trí cấp phát và chính sách allocator đều ảnh hưởng. Nhưng việc thiếu spatial locality là một đánh đổi cấu trúc đáng được tính đến.

## 7. Cache hit, miss và địa chỉ được thay thế

Cache có dung lượng hữu hạn. Khi muốn nạp một line mới, cache có thể phải **thay thế** line cũ.

Các nhóm miss thường được mô tả bằng mô hình “3C”:

| Nhóm miss | Ý tưởng | Ví dụ |
|---|---|---|
| **Compulsory** (*cold miss*) | Chưa từng nạp line trước đó | Lần đầu quét một mảng |
| **Capacity** | Working set vượt dung lượng cache | Quét lại dữ liệu rất lớn, các line cũ đã bị đẩy |
| **Conflict** | Nhiều địa chỉ cạnh tranh cùng vị trí/set | Các địa chỉ ánh xạ vào cùng cache set |

Trên hệ thống đa lõi, còn có miss hoặc stall do **coherence/invalidations**, nên mô hình 3C không bao trùm mọi nguồn chậm.

### Working set là gì?

**Working set** là tập dữ liệu đang được sử dụng trong một khoảng thời gian. Nếu working set truy cập thường xuyên **vừa trong một tầng cache**, xác suất hit có thể cao hơn. Nếu nó vượt xa dung lượng, số miss có thể tăng mạnh.

Ví dụ:

```text
Mảng A:  32 KiB
Mảng B: 128 MiB
```

Trong một CPU giả định có L1 data cache vài chục KiB, `A` có thể có cơ hội tái sử dụng tốt ở L1 khi truy cập có tính cục bộ, trong khi `B` không thể nằm toàn bộ trong L1. Nhưng kết quả thực tế còn phụ thuộc cache cho mã, dữ liệu khác, associativity, các lõi và thuật toán.

### Replacement policy

Giải thích giáo khoa hay dùng **LRU** (*least recently used*): đẩy line lâu không dùng nhất. Cache CPU thật có thể dùng các biến thể gần LRU hoặc chính sách khác, không nhất thiết là LRU chính xác.

Vì vậy, mô phỏng LRU ở phần thực hành là **mô hình để hiểu locality**, không phải bản sao của một CPU thật.

## 8. Average Memory Access Time (AMAT)

Một phép tính cơ bản giúp hiểu tác động miss:

\[
\boxed{AMAT = \text{Hit time}+\text{Miss rate}\times\text{Miss penalty}.}
\]

Với nhiều tầng cache, ta có thể **lồng chi phí miss**, nhưng phải dùng đúng tỷ lệ miss có điều kiện.

Ví dụ **giả định**:

- L1 hit time: `1 ns`.
- Xác suất miss ở L1: `5\%`.
- Khi miss L1, cần `5 ns` để tra L2.
- Trong **những lần đã miss L1**, xác suất còn miss L2 là `20\%`.
- Khi miss cả L1 và L2, cần thêm `80 ns` lấy từ tầng sâu hơn.

Khi đó:

\[
\begin{aligned}
AMAT
&=1+0.05(5+0.20\times80)\\
&=1+0.05\times21\\
&=\boxed{2.05\text{ ns}}.
\end{aligned}
\]

### Tại sao không cộng mọi latency?

Trong `95\%` truy cập hit L1, không phải chờ toàn bộ L2 hoặc RAM. Chỉ những truy cập miss mới có chi phí tầng sau. Công thức lấy **kỳ vọng** theo xác suất mỗi nhánh.

### L2 local miss rate và global miss rate

- **Local L2 miss rate:** phần trăm miss L2 trong **những truy cập đã đến L2**.
- **Global L2 miss rate:** phần trăm truy cập ban đầu đi đến L1 rồi **miss cả L1 lẫn L2**.

Với ví dụ:

\[
P(\text{miss L1 và L2})=0.05\times0.20=0.01.
\]

Tức **1\% toàn bộ truy cập** phải xuống sâu hơn L2, theo giả định đơn giản.

**AMAT không phải thời gian chạy của cả chương trình.** CPU có thể chồng lấp miss, thực hiện nhiều lệnh độc lập, prefetch, vectorize hoặc bị stall do yếu tố khác. AMAT là một mô hình chi phí truy cập bộ nhớ giúp giải thích tác động của miss rate.

## 9. Một cache miss có thể tốn bao nhiêu chu kỳ CPU?

Giả sử lõi CPU chạy ở tần số **3 GHz** trong một thời điểm:

\[
\text{1 chu kỳ}=\frac{1}{3\times10^9}\text{ s}\approx0.333\text{ ns}.
\]

Theo các số **minh họa**:

| Chờ dữ liệu | Thời gian | Số chu kỳ tương ứng ở 3 GHz |
|---|---:|---:|
| L1 hit giả định | `1 ns` | Khoảng 3 |
| RAM giả định | `100 ns` | Khoảng 300 |
| SSD giả định | `100 µs` | Khoảng 300.000 |
| HDD giả định | `5 ms` | Khoảng 15.000.000 |

Các con số là phép **quy đổi đơn vị**, không khẳng định CPU sẽ thực sự đứng yên đúng từng ấy chu kỳ. Khi I/O chậm, hệ điều hành có thể chạy công việc khác; một luồng có thể ngủ và được đánh thức khi dữ liệu sẵn sàng; CPU có thể thay đổi tần số.

Thông điệp quan trọng: **khoảng cách độ trễ giữa RAM và thiết bị lưu trữ bền vững thường lớn đến mức số lần I/O có thể quyết định thiết kế thuật toán**.

## 10. Đọc trước (prefetch) và che giấu độ trễ

**Hardware prefetcher** cố gắng đoán các địa chỉ sắp được truy cập, đặc biệt các mẫu tuần tự hoặc bước nhảy đều. Khi đoán đúng, nó nạp dữ liệu trước khi lệnh thật cần, làm giảm thời gian chờ.

```text
for i in range(n):
    total += A[i]
```

Mẫu quét tuyến tính có thể giúp prefetcher nhận ra các line kế tiếp. Ngược lại:

```text
index = next[index]  # Vị trí tiếp theo phụ thuộc dữ liệu vừa đọc.
```

Trong một chuỗi **pointer chasing** phụ thuộc nhau, máy có thể không biết địa chỉ tiếp theo trước khi nhận được kết quả đọc hiện tại, khiến nhiều lần miss khó chồng lấp.

### Prefetch không phải lúc nào cũng có ích

- Nạp quá sớm làm line bị thay thế trước khi dùng.
- Nạp dữ liệu không sử dụng gây tốn băng thông.
- Phá locality của workload khác trên cùng cache.
- Một số mẫu truy cập ngẫu nhiên không dự đoán được.

Lập trình viên có thể sử dụng **software prefetch** trong môi trường hỗ trợ, nhưng phải benchmark. Một thuật toán có locality tốt thường dễ tối ưu hơn việc cố sửa mọi miss bằng lệnh prefetch thủ công.

## 11. Ghi dữ liệu: write-through, write-back và chính sách cấp phát

CPU cache không chỉ phục vụ đọc; lệnh ghi dữ liệu cũng đi qua hệ thống bộ nhớ.

### Write-through

Một chiến lược cache có thể cập nhật tầng sau ngay khi ghi (hoặc theo giao thức đảm bảo thông tin truyền xuống tầng sau), giúp đơn giản hóa một số tính chất nhất quán, nhưng làm tăng lưu lượng ghi.

### Write-back

Một chiến lược phổ biến ở cache dữ liệu CPU là giữ line đã sửa thành **dirty**, và chỉ đẩy nội dung về tầng sau khi cần thay thế, đồng bộ hoặc theo giao thức cache.

```text
CPU ghi A[i]
     |
     v
Cache line được sửa / dirty
     |
     |  Có thể chưa ghi ngay xuống tầng sau
     v
Sau đó write-back theo chính sách phần cứng
```

Với write miss, còn có khái niệm **write-allocate** hoặc **no-write-allocate**, chỉ việc có đưa line vào cache hay không; chi tiết tùy loại cache và kiến trúc.

### Cảnh báo đặc biệt: write-back cache CPU không có nghĩa là dữ liệu đã bền vững

Dữ liệu đã nằm trong CPU cache hoặc RAM **chưa đồng nghĩa** với việc nó được lưu an toàn trên SSD/HDD khi mất điện. Bảo đảm durability đòi hỏi giao thức ở các tầng tiếp theo: hệ điều hành, hệ thống file, thiết bị, flush/barrier, cơ chế ghi nhật ký hoặc giao dịch tùy trường hợp.

Đừng suy từ câu “CPU đã ghi xong biến” ra “dữ liệu đã có trên đĩa”.

## 12. Cache coherence và false sharing trên nhiều lõi

Trong hệ thống nhiều lõi, cùng một vị trí bộ nhớ có thể được cache ở nhiều nơi. **Cache coherence** là cơ chế phần cứng giúp quản lý tính nhất quán giữa các bản sao theo giao thức kiến trúc.

### False sharing

Giả sử hai luồng cập nhật hai biến **khác nhau**, nhưng hai biến lại nằm trong **cùng cache line**:

```text
Cache line (minh họa 64 B)
+-------------------------+---------------------------+
| counter_A (luồng 1)     | counter_B (luồng 2)       |
+-------------------------+---------------------------+
          cùng một cache line
```

Dù không ghi vào cùng một biến, hai lõi có thể liên tục phải trao đổi/invalidating line chứa cả hai biến. Đây là **false sharing**, có thể làm chương trình song song chậm đáng kể.

### Hướng xử lý

- Căn chỉnh/padding để các biến được ghi mạnh bởi các luồng khác nhau không dùng chung line.
- Gom dữ liệu theo luồng, giảm số lần chia sẻ bộ nhớ có ghi.
- Dùng cấu trúc và cơ chế đồng bộ phù hợp, đo bằng profiler/counter.

**Không nhầm false sharing với data race:** false sharing có thể xuất hiện dù mỗi luồng ghi biến riêng, không có race trên hai biến ấy. Ngược lại, không có false sharing cũng không đồng nghĩa chương trình không có data race.

## 13. RAM: bộ nhớ chính và giới hạn dung lượng

**RAM** (*random-access memory*, thường là DRAM trong máy tính phổ biến) chứa dữ liệu và mã đang được dùng, thường **mất nội dung khi mất điện**.

Đặc điểm:

- Dung lượng lớn hơn cache CPU nhiều lần.
- CPU có thể truy cập thông qua hệ thống địa chỉ, MMU, memory controller và cache.
- Độ trễ cao hơn cache gần CPU, nhưng thấp hơn thiết bị lưu trữ bền vững trong phần lớn thao tác thông thường.
- Có **băng thông cao** cho truyền nhiều dữ liệu, chịu ảnh hưởng của kênh nhớ, NUMA, lõi cạnh tranh và truy cập thực tế.

### RAM khác thiết bị lưu trữ ở điểm nào?

RAM thông thường được dùng như **không gian truy cập load/store**, với địa chỉ của từng vùng nhớ ảo được ánh xạ tới trang vật lý. Thiết bị lưu trữ khối thường được truy cập qua các hoạt động **đọc/ghi khối**, hệ thống file, driver và hàng đợi I/O; không phải một lệnh CPU load bình thường tới file tự động tương đương một load vào RAM.

### Chạy nhiều tiến trình

Không nên hiểu dung lượng RAM nhìn thấy từ một tiến trình bằng **toàn bộ RAM vật lý khả dụng**. RAM còn phục vụ:

- Hệ điều hành và các tiến trình khác.
- Page cache và các bộ đệm I/O.
- Vùng nhớ của runtime, heap, stack, shared libraries.
- Trang khóa/cố định, thiết bị và mục đích chuyên biệt.

Khi working set của chương trình vượt nguồn RAM thực sự có thể cấp, hệ thống phải áp dụng các chính sách thu hồi trang, đọc lại dữ liệu hoặc swap; những hiện tượng này có thể làm hiệu năng tụt rất mạnh.

## 14. Bộ nhớ ảo: địa chỉ chương trình không nhất thiết là địa chỉ vật lý

Một chương trình thông thường nhìn thấy **không gian địa chỉ ảo** (*virtual address space*). CPU và hệ điều hành phối hợp chuyển địa chỉ ảo thành địa chỉ vật lý theo các ánh xạ được cấp phép.

```text
Tiến trình yêu cầu đọc địa chỉ ảo V
                   |
                   v
           CPU / MMU tra ánh xạ
                   |
          +--------+--------+
          |                 |
        Có ánh xạ        Chưa có ánh xạ
          |             hợp lệ / hiện diện
          v                 |
     Địa chỉ vật lý         v
          |            Hệ điều hành
          v            xử lý page fault
     Cache / RAM             |
                       Có thể cấp trang,
                       đọc file, swap,
                       hoặc báo lỗi
```

**Mục đích:** tách không gian địa chỉ của các tiến trình, bảo vệ truy cập, quản lý cấp phát và cho phép dùng bộ nhớ linh hoạt. Việc một vùng địa chỉ ảo “tồn tại” không có nghĩa mọi byte của vùng ấy đang nằm sẵn trong RAM vật lý.

### Trang bộ nhớ (page)

Bộ nhớ ảo thường quản lý theo **trang**, ví dụ nhiều hệ thống dùng trang cơ sở `4 KiB`. Một trang có thể:

- Đã ánh xạ tới một frame vật lý.
- Chưa được cấp frame và chỉ cấp khi truy cập.
- Được ánh xạ với dữ liệu từ file hoặc trang được chia sẻ.
- Bị bảo vệ không cho đọc/ghi theo chính sách.
- Được hoán chuyển hoặc cần phục hồi từ nguồn phía sau.

Ngoài trang cơ sở, có thể có **huge pages** hoặc các kích thước trang khác; không được giả định mọi địa chỉ ảo đều luôn dịch theo trang `4 KiB`.

### Trang là đơn vị ánh xạ, không đồng nghĩa đơn vị truyền mọi I/O

Một lần fault có thể dẫn tới nạp thêm dữ liệu ngoài một trang nhờ cơ chế read-ahead, hoặc dữ liệu đã sẵn trong page cache. Dung lượng vật lý thiết bị, kích thước block hệ thống file và kích thước trang ảo **có thể khác nhau**.

## 15. TLB: bộ nhớ đệm của phép dịch địa chỉ

**Translation Lookaside Buffer (TLB)** giữ các kết quả dịch địa chỉ ảo → địa chỉ vật lý gần đây.

Khi chương trình đọc `A[i]`, ngoài câu hỏi “cache CPU có data line chứa `A[i]` không?”, CPU còn cần biết **địa chỉ vật lý** tương ứng.

```text
Địa chỉ ảo
    |
    v
  TLB hit? -------- có --------> Có thông tin ánh xạ
    |
  không
    |
    v
  Page-table walk hoặc cơ chế dịch tương ứng
    |
    +-- ánh xạ hợp lệ --> Bổ sung TLB / tiếp tục
    |
    +-- thiếu hoặc vi phạm --> Page fault / exception
```

### TLB miss không đồng nghĩa page fault

Đây là hai sự kiện khác nhau:

- **TLB miss:** không có bản ghi dịch địa chỉ trong TLB; máy có thể tra bảng trang và **tiếp tục mà không cần I/O đĩa**.
- **Page fault:** một điều kiện cần hệ điều hành can thiệp, có thể do trang chưa có ánh xạ hiện diện, copy-on-write hoặc truy cập vi phạm quyền.

Một page fault cũng **không nhất thiết** phải đọc từ SSD/HDD. Nhiều fault có thể giải quyết bằng trang zero mới, ánh xạ đã nằm trong RAM hoặc copy-on-write.

### Locality theo trang

Nếu quét tuần tự một mảng lớn, các truy cập gần nhau thường nằm trong cùng trang. Sau khi dịch một trang, nhiều truy cập có thể tái sử dụng bản ghi TLB.

Nếu mỗi lần đọc nhảy tới một trang khác trong tập rất lớn, khả năng miss TLB tăng, ngay cả khi dữ liệu tương ứng vẫn ở RAM. Vì vậy, **cache locality và TLB locality** là hai góc nhìn khác nhau, tuy có liên hệ.

## 16. Page fault, swap và hiện tượng thrashing

Một **page fault** xảy ra khi việc dịch/truy cập trang cần cơ chế xử lý đặc biệt của hệ điều hành.

### Minor page fault

Thông thường có thể giải quyết **không cần đọc dữ liệu từ thiết bị lưu trữ**, chẳng hạn thiết lập ánh xạ tới trang đã có trong RAM hoặc cấp trang zero.

### Major page fault

Thường yêu cầu chờ dữ liệu được đọc từ nguồn lưu trữ phía sau, có thể chậm hơn đáng kể so với minor fault.

Những cách phân loại/đếm fault này phụ thuộc hệ điều hành; cần đọc ý nghĩa counter chính xác khi profiling.

### Swap và thiếu RAM

Khi hệ thống thiếu RAM, nó có thể chuyển nội dung một số trang ẩn danh ít dùng sang **swap**, rồi đọc trở lại khi được truy cập, hoặc thu hồi các trang file-backed có thể đọc lại.

Nếu workload liên tục cần nhiều trang hơn lượng RAM có thể giữ, hệ thống có thể rơi vào **thrashing**:

```text
Truy cập trang A -> phải đọc lại A
Truy cập trang B -> thay thế A
Truy cập lại A   -> lại đọc A
...
```

Thay vì làm việc tính toán, hệ thống dành nhiều thời gian xử lý trang và I/O.

### Bài học cho cấu trúc dữ liệu

Một thuật toán đọc ngẫu nhiên hàng triệu nút có thể:

- Gây nhiều miss cache.
- Gây nhiều miss TLB.
- Khi thiếu RAM, gây nhiều lần nạp lại trang từ thiết bị.

Cùng một thuật toán có thể có hiệu năng **khác biệt rất lớn** trước và sau khi working set vượt ngưỡng bộ nhớ. Vì thế, không nên dự đoán tốc độ chỉ bằng `O(n)` hoặc `O(\log n)` mà bỏ qua kích thước dữ liệu và tài nguyên máy.

## 17. Page cache của hệ điều hành khác CPU cache

**OS page cache** là vùng RAM được hệ điều hành dùng để giữ các trang dữ liệu file đã đọc hoặc sắp ghi.

Đường đi điển hình của một `read()` có thể được giản lược:

```text
Ứng dụng yêu cầu đọc file
          |
          v
Hệ điều hành kiểm tra page cache
        /          \
      Hit          Miss
       |             |
       |        Yêu cầu I/O tới SSD/HDD
       |             |
       |       Đưa dữ liệu vào RAM
       |             |
       +-------+-----+
               |
               v
     Dữ liệu được cung cấp cho ứng dụng
               |
               v
   CPU đọc từ vùng nhớ ứng dụng qua CPU cache
```

### Hai loại cache, hai chức năng

| Đặc điểm | CPU cache | OS page cache |
|---|---|---|
| Nằm ở đâu? | Bộ nhớ gần lõi CPU, phần cứng quản lý | RAM, hệ điều hành quản lý |
| Cache cái gì? | Cache line chứa dữ liệu/lệnh | Các trang/bộ đệm dữ liệu file |
| Mục tiêu | Giảm chi phí truy cập RAM | Giảm số lần phải đọc từ thiết bị lưu trữ |
| Đơn vị điển hình | Cache line | Trang hoặc folio/buffer tùy hệ điều hành |
| Vòng đời | Bị thay thế theo hoạt động CPU | Do chính sách reclaim và I/O của OS |

**Ví dụ hai lần đọc cùng tệp:**

- Lần thứ nhất: dữ liệu chưa ở page cache, có thể phải đọc từ SSD/HDD.
- Lần thứ hai: dữ liệu còn ở RAM page cache nên không phải I/O thiết bị.
- Nhưng CPU vẫn có thể bị **cache miss** khi đọc bộ đệm RAM đó.

Do đó, “đọc file lần hai nhanh hơn” không chứng minh CPU cache đã giữ nguyên cả tệp. Tệp lớn có thể vượt xa CPU cache nhưng vẫn nằm trong **OS page cache**.

## 18. Buffered I/O, memory mapping và direct I/O

Ứng dụng có nhiều cách truy cập dữ liệu trong file.

### Buffered I/O thông thường

Ví dụ `read()` qua API hệ điều hành có thể tận dụng page cache, read-ahead và batching. Đường sao chép dữ liệu vào vùng user-space tùy giao diện và hệ điều hành.

### Memory-mapped file (`mmap`)

Hệ điều hành ánh xạ nội dung file vào không gian địa chỉ ảo. Chương trình dùng truy cập bộ nhớ trên vùng ánh xạ, và trang file được nạp/phân giải khi cần.

**Không hiểu sai:** `mmap` **không bắt buộc tải cả file vào RAM ngay khi tạo ánh xạ**. Với file lớn, nhiều trang có thể chưa được nạp. Truy cập ngẫu nhiên trong vùng mapped vẫn có thể gây page fault và I/O.

### Direct I/O

Một số hệ điều hành/API hỗ trợ chế độ hạn chế hoặc bỏ qua **page cache của OS** cho luồng I/O cụ thể. Điều này có ích khi ứng dụng (ví dụ database) tự quản lý buffer pool để tránh cache trùng lặp, nhưng cần chú ý yêu cầu về căn chỉnh, kích thước I/O và tính tương thích.

**Direct I/O không đồng nghĩa “không đi qua mọi bộ đệm”**: vẫn có cache của CPU, thiết bị, bộ điều khiển hoặc cơ chế khác; semantics cụ thể phụ thuộc OS/hardware.

### Chọn cách truy cập dựa trên workload

- Tệp được dùng lại thường xuyên và tương đối nhỏ: page cache có thể rất hiệu quả.
- Quét tệp cực lớn chỉ một lần: read-ahead/streaming và buffer hợp lý có thể tốt hơn đọc ngẫu nhiên.
- Cơ sở dữ liệu quản lý bộ nhớ riêng: buffer pool và một số đường I/O đặc biệt có thể kiểm soát caching tốt hơn.

Đừng tuyên bố một cơ chế luôn nhanh hơn: phải xét caching, kích thước request, độ đồng thời, hệ thống file và phép đo thực tế.

## 19. SSD và HDD: cùng lưu bền vững, nhưng đặc tính khác nhau

### HDD: đĩa từ với bộ phận cơ học

HDD có đầu đọc/ghi và đĩa quay. Đọc ngẫu nhiên có thể phải chờ:

- Đầu đọc/ghi di chuyển tới vùng dữ liệu (*seek*).
- Đĩa quay tới vị trí cần đọc (*rotational latency*).
- Truyền dữ liệu sau khi định vị.

Vì vậy, một chuỗi các truy cập **ngẫu nhiên rải rác** thường có độ trễ cao hơn đọc các khối **liên tiếp**.

### SSD: bộ nhớ flash và bộ điều khiển

SSD không có thời gian seek cơ học như HDD. Nó có thể xử lý ngẫu nhiên tốt hơn nhiều, nhưng vẫn phải:

- Định địa chỉ và đọc/ghi qua controller.
- Quản lý flash translation layer (*FTL*).
- Xử lý erase block, wear leveling, garbage collection.
- Đợi hàng đợi I/O, giao diện PCIe/NVMe/SATA và phần mềm.

**SSD không biến một lần I/O thành một lần load RAM.** Độ trễ giữa lưu trữ và RAM vẫn thường chênh lệch nhiều bậc.

### Sequential vs random là xu hướng, không phải kết luận tuyệt đối

Truy cập tuần tự thường giúp:

- Gộp nhiều byte trong một yêu cầu.
- Dễ read-ahead.
- Giảm overhead định vị trên HDD.
- Tận dụng pipeline và băng thông thiết bị.

Nhưng SSD có thể xử lý nhiều I/O ngẫu nhiên song song, và hệ thống file/caching có thể biến pattern quan sát ở ứng dụng thành pattern khác trên thiết bị. Do đó, benchmark cần **kích thước khối, queue depth và số outstanding requests** cùng độ trễ/throughput, không chỉ nhãn “random” hay “sequential”.

## 20. Đọc và ghi file: từ syscall tới block I/O

Một quy trình đọc file đơn giản hóa:

```text
Ứng dụng đọc một vùng file
  -> Giao diện thư viện / system call
  -> Hệ thống file tìm vị trí dữ liệu
  -> Kiểm tra page cache / buffer
  -> Nếu thiếu: xếp I/O vào hàng đợi thiết bị
  -> Controller đọc dữ liệu vào bộ nhớ
  -> Hệ điều hành đánh dấu dữ liệu sẵn sàng
  -> Ứng dụng tiếp tục xử lý
```

### Vì sao đọc từng byte qua I/O riêng là tệ?

Giả sử cần đọc `1 MiB` dữ liệu. Nếu mỗi lần `read` yêu cầu đúng một byte, có tới hơn một triệu lần gọi API, tạo overhead lớn ở tầng phần mềm, dù hệ điều hành có thể tối ưu một phần nhờ buffer.

Nếu đọc thành các khối `64 KiB`, số lời gọi xấp xỉ:

\[
\frac{1\,\text{MiB}}{64\,\text{KiB}}=16.
\]

Đây là minh họa cho **batching**: giảm số lần giao tiếp với tầng I/O và tạo cơ hội truyền theo khối.

### Không phải mọi lần read() đều là một I/O vật lý

Một lời gọi `read(64 KiB)` có thể:

- Chỉ copy dữ liệu đã nằm trong page cache.
- Kéo theo nhiều request vật lý.
- Được chia nhỏ theo giới hạn thiết bị.
- Được phục vụ bởi read-ahead đã diễn ra trước.

Vì vậy, **số syscall, số lần page fault và số I/O thiết bị là ba đại lượng khác nhau**.

### Ghi dữ liệu và durability

Ghi file thông thường có thể đi qua **dirty pages** trong page cache. Hệ điều hành có thể trì hoãn ghi xuống thiết bị rồi flush theo chính sách.

Muốn dữ liệu quan trọng tồn tại sau sự cố, ứng dụng cần hiểu hợp đồng của `flush/fsync`, giao dịch, journaling, cache thiết bị và thứ tự ghi. Tên API khác nhau giữa hệ điều hành và môi trường; lời gọi ghi thành công **không nên bị đồng nhất** với một cam kết durability mạnh hơn những gì API thực sự bảo đảm.

## 21. Mô hình external memory: đếm lần truyền khối thay vì chỉ đếm lệnh

Khi dữ liệu quá lớn để nằm hoàn toàn trong RAM, một mô hình hữu ích là **I/O model** hay **external-memory model** (thường gắn với Aggarwal–Vitter).

Ký hiệu:

- `N`: số **bản ghi/phần tử** cần xử lý.
- `M`: số phần tử có thể giữ trong **bộ nhớ trong** (RAM khả dụng cho thuật toán).
- `B`: số phần tử truyền trong **một khối I/O**.
- Giả thiết thường có `1\le B\le M`, và một thao tác chuyển **một khối `B` phần tử** giữa bộ nhớ ngoài và bộ nhớ trong tốn một đơn vị I/O.

**Quan trọng về đơn vị:** nếu `B` tính bằng **byte** nhưng `N` là **số bản ghi**, phải chuyển về cùng đơn vị trước khi dùng công thức. Trong bài này, khi viết `N/B`, cả `N` và `B` đều đang tính theo **phần tử**.

### Vì sao cần mô hình mới?

Trong mô hình RAM cổ điển, một phép truy cập mảng được xem là `O(1)`. Nhưng nếu dữ liệu ở SSD/HDD, việc truy cập một phần tử có thể buộc phải đọc **cả khối** chứa nó, và chi phí ấy lớn hơn nhiều phép toán CPU.

I/O model bỏ qua phần lớn chi phí tính toán bên trong RAM để tập trung vào:

\[
\boxed{\text{Số lần chuyển khối giữa RAM và lưu trữ ngoài}.}
\]

Mục tiêu là **tận dụng mỗi khối vừa đọc được để xử lý nhiều phần tử trước khi thay nó**.

### Mô hình là công cụ phân tích, không phải toàn bộ hiệu năng thật

Một I/O thực tế có thể khác một I/O khác về:

- Độ trễ seek/hàng đợi.
- Kích thước request.
- Mức song song và băng thông.
- Compression, caching, read-ahead.
- Loại SSD/HDD, hệ thống file và workload cạnh tranh.

I/O model giúp so sánh thuật toán ở mức **tiệm cận số khối**, nhưng để dự đoán thời gian thực phải bổ sung các thông số thiết bị.

## 22. SCAN: quét tuần tự cần bao nhiêu I/O?

Giả sử có `N` phần tử nằm liên tiếp trong file và một I/O đọc được `B` phần tử. Nếu dữ liệu chưa được cache, số khối tối thiểu cần đọc để xem mọi phần tử xấp xỉ:

\[
\boxed{\operatorname{Scan}(N)=\Theta\left(\left\lceil\frac NB\right\rceil\right).}
\]

Ví dụ, `N=1{,}000{,}000` phần tử, `B=1000` phần tử/khối:

\[
\left\lceil\frac{1{,}000{,}000}{1000}\right\rceil=1000\text{ khối}.
\]

### So sánh với truy cập rời rạc

Nếu chọn ngẫu nhiên một phần tử rồi đọc khối chứa nó, các phần tử được chọn có thể nằm trong **nhiều khối khác nhau**. Nếu cache giữ không đủ và gần như mỗi lần chọn gây một miss, `q` lần truy cập có thể cần tới cỡ `q` I/O.

Ngược lại, nếu sắp xếp các yêu cầu theo **vị trí file** trước khi thực hiện hoặc gom những yêu cầu chung khối, số I/O có thể giảm.

**Không suy rằng mọi truy cập ngẫu nhiên đều phát sinh đúng một I/O:** có thể hit cache, trùng khối hoặc được hệ điều hành/thiết bị gộp lại. Con số `q` là một kịch bản biên có ý nghĩa, không phải đẳng thức phổ quát.

### Vì sao duyệt mảng theo khối có lợi?

Khi đã đọc một khối, ta có thể xử lý `B` phần tử **ngay trong RAM**, thay vì bỏ khối rồi phải đọc lại. Thiết kế thuật toán có chi phí I/O tốt thường khai thác nguyên tắc này.

## 23. Truy cập ngẫu nhiên, tìm kiếm nhị phân và I/O

Giả sử `N` phần tử đã sắp tăng, nhưng nằm trên thiết bị lưu trữ ngoài RAM.

### Tìm kiếm nhị phân trên mảng

Trong mô hình RAM, binary search thực hiện `O(\log_2 N)` phép so sánh.

Nhưng các phần tử giữa ở mỗi bước thường thuộc **những khối cách xa nhau**. Nếu không có cache hữu ích, có thể cần `O(\log N)` lần đọc khối ngẫu nhiên, **không phải tự nhiên `O(\log_B N)`**.

Ví dụ `N=1{,}000{,}000`, binary search cần khoảng `20` bước so sánh. Khi dữ liệu lạnh, đây có thể là nhiều lần truy cập những khối ở xa nhau, đặc biệt bất lợi trên HDD.

### B-tree/B+ tree

Cây B có thể đặt **nhiều khóa và nhánh trong cùng một trang**. Một lần đọc trang cho phép quyết định nhánh tiếp theo trong số hàng chục/hàng trăm con, thay vì chỉ hai con.

Với hệ số phân nhánh hiệu quả `F`, số tầng có dạng:

\[
\boxed{h=O(\log_F N)}
\]

trong giả định cây được giữ cân bằng và mỗi nút đủ đầy theo bất biến của cấu trúc.

Khi thiết kế nút gần bằng kích thước block I/O và `F` tỉ lệ với số khóa/con trỏ có thể đặt trong một block, cận I/O tìm kiếm thường được viết **`O(\log_B N)`** trong mô hình external memory với giả thiết kích thước bản ghi cố định và `B` hợp lý.

### Chi tiết cần nói rõ

`F` không phải đúng bằng `B` nếu `B` là **số byte**; mỗi key, pointer và metadata chiếm dung lượng. Trong phân tích đơn giản, `B` có thể được tính bằng **số mục vừa một block**, và khi ấy `F=\Theta(B)`.

Nếu các nút phía trên đã nằm trong RAM buffer pool, số lần I/O thật có thể nhỏ hơn số tầng cây. Nếu tất cả trang cần thiết đều ở RAM, một lần tìm kiếm có thể không cần I/O thiết bị.

## 24. Tại sao B+ tree tối ưu cho cả tìm kiếm và quét khoảng?

Trong nhiều hệ thống lưu trữ chỉ mục, **B+ tree** sắp khóa theo thứ tự:

- Các **nút trong** giữ khóa phân cách và con trỏ để điều hướng.
- Các **nút lá** chứa cặp khóa→bản ghi hoặc con trỏ tới bản ghi (tùy thiết kế).
- Các lá thường được tổ chức thuận tiện cho quét **tăng dần theo khóa**, có thể có liên kết giữa lá.

Ví dụ ý tưởng:

```text
                 [ 20 | 40 | 60 ]
                 /     |    |    \
         [0..19] [20..39] [40..59] [60..]
           L0 ------ L1 ------ L2 ------ L3
                   các trang lá theo thứ tự
```

### Truy vấn một khóa

Đi từ gốc qua các trang nút trong tới trang lá chứa khóa. Mỗi trang được chọn cho phép loại bỏ nhiều khoảng khóa không cần xét.

### Truy vấn đoạn khóa

Với `[lo,hi]`:

1. Tìm trang lá chứa vị trí bắt đầu `lo`.
2. Quét các trang lá tiếp theo theo thứ tự khóa.
3. Dừng khi khóa đã vượt `hi`.

Nếu cần xuất `K` bản ghi và mỗi trang lá chứa cỡ `B` bản ghi, trong mô hình lý tưởng với các lá được truy cập tuần tự, chi phí I/O có dạng:

\[
\boxed{O(\log_B N + K/B + 1)}
\]

với giả thiết hợp lý về lấp đầy trang, layout và I/O. Công thức này cho thấy khác biệt giữa **tìm một vị trí** và **đọc một khoảng lớn**.

**Đừng hiểu mọi leaf của B+ tree luôn nằm liên tiếp vật lý trên SSD/HDD.** Liên kết logic theo khóa không bảo đảm vị trí vật lý liền nhau; fragmentation và layout vẫn ảnh hưởng thông lượng thực tế.

## 25. External merge sort: sắp xếp dữ liệu không đủ RAM

Giả sử tệp có `N` bản ghi nhưng RAM cho thuật toán chỉ giữ được `M` bản ghi, với `N\gg M`.

Nếu cố nạp tất cả vào RAM rồi dùng `sort()`, chương trình có thể không đủ bộ nhớ hoặc gây swap mạnh. **External merge sort** chia bài toán thành nhiều lượt xử lý khối.

### Giai đoạn 1 — tạo các run đã sắp

1. Đọc một nhóm tối đa `M` bản ghi vào RAM.
2. Sắp xếp nhóm ấy bằng thuật toán nội bộ.
3. Ghi nhóm đã sắp ra đĩa thành một **run**.
4. Lặp lại đến hết `N` bản ghi.

Số run ban đầu xấp xỉ:

\[
R=\left\lceil\frac{N}{M}\right\rceil.
\]

Trong mô hình block I/O, đọc và ghi toàn dữ liệu trong giai đoạn này tốn xấp xỉ:

\[
2\left\lceil\frac NB\right\rceil
\]

I/O khối, bỏ qua làm tròn và metadata.

### Giai đoạn 2 — gộp nhiều run có thứ tự

Giữ một buffer đọc cho mỗi run đầu vào và một buffer ghi cho đầu ra; dùng heap nhỏ để chọn bản ghi kế tiếp:

```text
Run A: [1, 4, 9, 20]
Run B: [2, 5, 11, 18]
Run C: [3, 6, 10, 19]

Merge:
[1, 2, 3, 4, 5, 6, 9, 10, 11, 18, 19, 20]
```

Nếu RAM có thể giữ `M/B` khối, một lượt gộp có thể xử lý khoảng **`M/B-1` run đầu vào** (dành ít nhất một block output), với một số buffer/overhead phụ.

### Tổng số lượt I/O

Trong mô hình external memory và những giả thiết kích thước thông thường, độ phức tạp I/O của sắp xếp tổng quát bằng so sánh có dạng:

\[
\boxed{
\operatorname{Sort}(N)
=\Theta\left(
\frac NB\log_{M/B}\frac NB
\right)
}
\]

trong miền tham số phù hợp; thường dùng dạng chính xác hơn để thể hiện chi phí quét tối thiểu:

\[
\boxed{
\Theta\left(
\frac NB\left(1+\log_{M/B}\frac NB\right)
\right).
}
\]

Các biểu thức viết gọn bỏ dấu trần, giả định `M/B>1` và chú ý chi phí đọc/ghi từng pass. Khi số run đã vừa trong các buffer gộp, số lượt merge có thể rất ít; các hệ thống thực tế còn dùng batching, compression, checksums và bộ đệm phức tạp hơn.

**Ý tưởng cốt lõi:** thay vì nhiều lần truy cập ngẫu nhiên để sắp từng bản ghi ngoài RAM, external merge sort **đọc và ghi tuần tự theo khối qua một số lượt**.

## 26. Ghi ngẫu nhiên, write amplification và ý tưởng LSM-tree

Đối với workload ghi nhiều bản ghi nhỏ, truy cập **ngẫu nhiên** có thể dẫn đến overhead lớn:

- Một thao tác thay đổi nhỏ có thể buộc đọc/sửa/ghi lại cả block hoặc page ở lớp lưu trữ.
- B-tree có thể phải sửa trang lá, nhật ký WAL và đôi khi tách/gộp trang.
- SSD flash thường ghi ở đơn vị trang và xóa ở đơn vị lớn hơn; bộ điều khiển có thể phải sắp xếp lại dữ liệu trong quá trình garbage collection.

**Write amplification** thường chỉ mức lượng dữ liệu thực sự được ghi ở một tầng lớn hơn lượng dữ liệu người dùng yêu cầu cập nhật. Nhưng cần nêu rõ **đang đo ở tầng nào**: write amplification ở engine cơ sở dữ liệu khác với write amplification nội bộ SSD/FTL.

### Ý tưởng LSM-tree

Một **log-structured merge tree (LSM-tree)** gom nhiều lần ghi nhỏ vào bộ nhớ:

```text
Ghi key/value
     |
     v
Memtable trong RAM (+ ghi log bền vững khi cần)
     |
     | đủ lớn
     v
Flush thành bảng có thứ tự trên thiết bị
     |
     v
Các file/bảng theo mức hoặc nhóm
     |
     v
Compaction để gộp và loại bản ghi cũ
```

Mục tiêu là biến nhiều cập nhật nhỏ thành những lượt ghi **tuần tự/gộp theo khối**. Đổi lại:

- Truy vấn đọc có thể phải kiểm tra nhiều mức/file và bộ lọc.
- **Compaction** có thể ghi lại dữ liệu nhiều lần.
- Có write amplification, read amplification và space amplification, với đánh đổi theo thiết kế cấp tầng/size ratio và workload.

### B-tree và LSM-tree không có một “người thắng” chung

| Khía cạnh | B-tree/B+ tree | LSM-tree |
|---|---|---|
| Cấu trúc trên đĩa | Trang cây có thứ tự, tìm theo đường gốc–lá | Memtable + các run/file có thứ tự được merge |
| Truy vấn khóa/đoạn | Điều hướng cây và quét lá | Tra memtable và các mức/file liên quan |
| Ghi nhỏ | Có thể sửa trang tương đối ngẫu nhiên | Thường gom/batch thành ghi tuần tự |
| Bảo trì | Tách/gộp trang, vacuum tùy hệ | Flush và compaction |
| Chi phí phụ | Page churn, WAL, cache | Compaction và write/read amplification |

Đây là so sánh **ý tưởng**, không phải cam kết mọi sản phẩm dùng các kỹ thuật ấy có cùng hiệu năng. Trong thực tế, caching, bộ lọc Bloom, layout file, WAL, SSD và chính sách compaction ảnh hưởng mạnh.

## 27. Buffer pool và chính sách thay thế trang

Một cơ sở dữ liệu thường quản lý **buffer pool** trong RAM để giữ các trang dữ liệu/chỉ mục đang dùng. Nhờ đó, một lần tìm kiếm B+ tree không nhất thiết phải đọc mọi tầng từ thiết bị.

Ví dụ:

```text
     B+ tree có 4 tầng

    Root page          <- thường rất nóng, dễ được cache
       |
   Internal page       <- có thể được cache
       |
   Internal page
       |
    Leaf page          <- phụ thuộc khóa truy vấn
```

Nếu ba tầng trên đã nằm trong buffer pool, lần tìm có thể chỉ cần nạp trang lá, hoặc **không cần I/O thiết bị** nếu trang lá cũng đã được cache.

### Khi RAM không đủ giữ mọi trang

Buffer pool phải chọn những trang sẽ đẩy ra. Các chiến lược có thể dựa trên LRU gần đúng, clock, tần suất, phân nhóm nóng/lạnh hoặc kiến thức truy vấn.

Một trang **dirty** đang chờ ghi không thể luôn bị hủy đơn giản như trang chỉ đọc sạch; hệ thống cần bảo đảm thứ tự lưu và hợp đồng durability.

### Tại sao một lần scan lớn có thể làm giảm cache hit?

Giả sử một chỉ mục “nóng” nhỏ đang được cache. Nếu ứng dụng quét một tệp rất lớn và cho phép mọi trang scan chen vào buffer pool, các trang index hữu ích có thể bị đẩy ra. Workload sau đó phải nạp lại index.

Nhiều hệ thống dùng chiến lược quản lý **scan/resistance** hoặc phân khu cache để tránh một luồng scan phá dữ liệu nóng của truy vấn điểm.

**Bài học:** locality cần xem theo **toàn workload**, không chỉ một hàm đơn lẻ. Một truy vấn tối ưu cho riêng nó có thể gây tác dụng phụ lên các truy vấn đang chạy song song.

## 28. Cache-aware và cache-oblivious: biết kích thước B, M hay không?

### Thuật toán cache-aware

Thuật toán được thiết kế với thông tin như:

- `B` — kích thước block/cache line hoặc đơn vị I/O quan tâm.
- `M` — dung lượng bộ nhớ nhanh có thể sử dụng.

Ví dụ **external merge sort** chọn số buffer theo `M/B`, hoặc phép nhân ma trận **blocking** chia dữ liệu thành tile đủ vừa cache.

### Thuật toán cache-oblivious

Thuật toán không cần biết trực tiếp `B` và `M` tại thời điểm thiết kế/cấu hình; thường dùng **phân chia đệ quy** để tạo locality ở nhiều cấp kích thước khác nhau.

Ví dụ ý tưởng:

```text
Xử lý ma trận lớn
    |
    +-- Chia thành các phần nhỏ
          |
          +-- Tiếp tục chia
                |
                +-- Mỗi phần cuối cùng vừa một tầng cache nào đó
```

Các phân tích cache-oblivious chuẩn thường cần một số giả định mô hình (ví dụ *tall-cache assumption* trong những bài toán nhất định). **Không phải cứ viết đệ quy là mặc nhiên cache-optimal**; thứ tự chia, cách bố trí dữ liệu và kích thước tác vụ vẫn quyết định hiệu quả.

### Ý nghĩa đối với phân cấp nhiều tầng

Trong một máy có L1, L2, L3, RAM và thiết bị lưu trữ, một thuật toán được thiết kế để khai thác dữ liệu theo khối có thể tận dụng **nhiều tầng** tốt hơn một thuật toán truy cập rải rác. Tuy nhiên, kích thước page và cache line không đồng nhất; kỹ thuật tối ưu một tầng đôi khi tăng chi phí ở tầng khác.

## 29. Bố trí dữ liệu: mảng, danh sách liên kết, AoS và SoA

### 29.1. Mảng liên tiếp

Mảng có bố trí phần tử liên tiếp (ví dụ `array` số nguyên có kiểu cố định) thường thuận lợi cho:

- Quét tuyến tính.
- Vectorization/SIMD.
- Hardware prefetch.
- Truy cập nhiều phần tử trên cùng cache line.

Đổi lại, chèn/xóa ở giữa thường dịch chuyển phần tử `O(n)`.

### 29.2. Danh sách liên kết

Một nút có thể chứa `value` và `next`. Nếu các nút cấp phát rời nhau:

- Đi qua các nút có thể gây cache/TLB miss.
- Khó prefetch khi địa chỉ nút tiếp theo phụ thuộc nút hiện tại.
- Có overhead con trỏ và bộ cấp phát.

Đổi lại, khi **đã có con trỏ đến vị trí** và có thể sửa liên kết an toàn, một số thao tác thêm/xóa không cần dịch chuyển `O(n)` phần tử như mảng. Nếu phải tìm vị trí từ đầu trước, tổng thời gian vẫn có thể `O(n)`.

### 29.3. Array of Structures (AoS)

Giả sử mỗi bản ghi gồm ba trường:

```text
struct Particle:
    x, y, z

AoS:
[(x0,y0,z0), (x1,y1,z1), (x2,y2,z2), ...]
```

Nếu thuật toán luôn sử dụng **cả x,y,z của một phần tử**, AoS có thể có locality phù hợp vì các trường liên quan nằm gần nhau.

### 29.4. Structure of Arrays (SoA)

```text
SoA:
x = [x0, x1, x2, ...]
y = [y0, y1, y2, ...]
z = [z0, z1, z2, ...]
```

Nếu thuật toán chỉ cần trường `x` của hàng triệu phần tử, SoA giúp quét một luồng dữ liệu gọn, hạn chế nạp các trường `y,z` không cần dùng.

### Đánh đổi

| Workload | Biểu diễn thường đáng xem xét |
|---|---|
| Đọc đủ toàn bộ trường của từng bản ghi | AoS |
| Quét một hoặc vài cột trên toàn bộ bản ghi | SoA |
| Cập nhật/chèn nhiều bản ghi trọn vẹn | Phụ thuộc tổ chức, AoS có thể đơn giản hơn |
| Xử lý vector/SIMD một trường | SoA thường thuận lợi |
| Truy vấn theo ID nhưng cần đọc toàn bộ bản ghi | Chỉ mục + layout thích hợp; không chỉ AoS/SoA |

**Không có bảo đảm SoA luôn nhanh hơn:** chi phí nhiều mảng, truy cập kết hợp giữa các trường, alignment và cấu trúc thuật toán đều phải tính. Với ngôn ngữ có object references, cần xem bố trí **thực tế trong bộ nhớ**, không chỉ cú pháp khai báo.

## 30. Ma trận row-major, column-major và thứ tự duyệt

Xét ma trận `n\times n` được lưu **row-major** (các phần tử của một hàng nằm liên tiếp):

```text
A[0,0] A[0,1] ... A[0,n-1]
A[1,0] A[1,1] ... A[1,n-1]
...
A[n-1,0] ...

Trong bộ nhớ row-major:
A[0,0], A[0,1], ..., A[0,n-1], A[1,0], ...
```

### Duyệt theo hàng

```python
def sum_row_major(flat: list[int], n: int) -> int:
    answer = 0
    for i in range(n):
        for j in range(n):
            answer += flat[i * n + j]
    return answer
```

### Duyệt theo cột

```python
def sum_column_order(flat: list[int], n: int) -> int:
    answer = 0
    for j in range(n):
        for i in range(n):
            answer += flat[i * n + j]
    return answer
```

Hai hàm đều tính tổng `n^2` phần tử, đều `O(n^2)` theo số phép cộng, nhưng thứ tự truy cập khác nhau:

- **Theo hàng:** các chỉ số của `flat` tăng liên tiếp, thường thuận lợi cho cache line.
- **Theo cột:** khoảng cách giữa hai phần tử liên tiếp trong vòng trong là `n` phần tử, có thể nhảy qua nhiều line/trang.

Đối với ma trận **column-major**, kết luận thuận lợi có thể đảo chiều.

**Cần phân biệt mã nguồn và layout thật:** một `list[list[int]]` Python là danh sách các danh sách có tham chiếu, không nhất thiết là một ma trận số nguyên phẳng row-major như hình. Mã `flat` trên minh họa **thứ tự index**; để đo cache locality của số `int64` phẳng, nên dùng một vùng typed array hay cấu trúc dữ liệu phẳng phù hợp.

## 31. Blocking/tiling: chia vấn đề lớn thành các phần vừa cache

Nếu truy cập toàn bộ ma trận nhiều lần, một cách giảm cache miss là **chia thành các tile**.

Ví dụ, xử lý mỗi khối `T\times T` thay vì đi xuyên qua toàn bộ ma trận theo một thứ tự gây bước nhảy lớn.

### Mã giả xử lý theo tile

```text
for row0 in 0, T, 2T, ...:
    for col0 in 0, T, 2T, ...:
        for i in [row0, min(row0+T,n)):
            for j in [col0, min(col0+T,n)):
                process(A[i,j])
```

Với phép toán đơn giản **chỉ đọc mỗi phần tử một lần**, chia tile không nhất thiết tốt hơn quét hàng row-major liên tiếp. Lợi ích lớn hơn khi một tile được **tái sử dụng nhiều lần**, ví dụ nhân ma trận hoặc một số phép biến đổi hai chiều.

### Ví dụ nhân ma trận

Trong phép tính `C=A\times B`, công thức:

\[
C[i,j]=\sum_{k=0}^{n-1}A[i,k]\cdot B[k,j]
\]

có thể khiến cùng phần dữ liệu của `A` và `B` được nạp lại nhiều lần nếu thứ tự vòng lặp không phù hợp. Tiling cố gắng giữ các submatrix đang cần trong tầng nhớ nhanh đủ lâu để **tái sử dụng** trước khi chuyển sang tile khác.

### Chọn kích thước tile

Tile cần đủ nhỏ để working set liên quan vừa tài nguyên nhanh (cache/RAM buffer), nhưng không quá nhỏ đến mức overhead vòng lặp và chuyển tile chiếm ưu thế. Tối ưu thực tế cần xét dữ liệu đầu vào, layout, vectorization và kích thước cache.

**Đây là ví dụ điển hình nơi tối ưu locality có thể cải thiện thời gian mà không đổi bậc số phép tính `O(n^3)` của phép nhân ma trận cổ điển.**

## 32. Mô phỏng cache line LRU bằng Python để hiểu locality

Để trực quan hóa **vì sao thứ tự truy cập ảnh hưởng số miss**, ta viết một bộ mô phỏng **cache lý tưởng hóa**, không phải CPU thật.

Giả định:

1. Mỗi cache line chứa `elements_per_line` phần tử liên tiếp.
2. Có `capacity_lines` line trong cache.
3. Cache **fully associative**, thay thế **LRU chính xác**.
4. Không mô phỏng prefetch, cache coherence, TLB, write-back hoặc lệnh CPU.

### Mã Python

```python
from collections import OrderedDict


def count_lru_line_misses(
    addresses: list[int],
    elements_per_line: int,
    capacity_lines: int,
) -> tuple[int, int]:
    """Trả (hits, misses) của mô hình LRU đơn giản."""
    if elements_per_line <= 0 or capacity_lines <= 0:
        raise ValueError("Kích thước line và capacity phải dương")

    cache: OrderedDict[int, None] = OrderedDict()
    hits = 0
    misses = 0

    for address in addresses:
        if address < 0:
            raise ValueError("Địa chỉ phần tử phải >= 0")
        line_id = address // elements_per_line

        if line_id in cache:
            hits += 1
            cache.move_to_end(line_id)
        else:
            misses += 1
            if len(cache) == capacity_lines:
                cache.popitem(last=False)
            cache[line_id] = None

    return hits, misses


n = 8
row_order = [
    i * n + j
    for i in range(n)
    for j in range(n)
]
column_order = [
    i * n + j
    for j in range(n)
    for i in range(n)
]

print(count_lru_line_misses(row_order, 4, 4))
# (48, 16)

print(count_lru_line_misses(column_order, 4, 4))
# (0, 64)
```

### Vì sao kết quả khác nhau?

- Có `8\times8=64` phần tử.
- Mỗi line chứa `4` phần tử nên có `16` line khác nhau.
- Duyệt theo hàng: mỗi line lần đầu miss, ba phần tử tiếp theo hit ⇒ `16` miss và `48` hit.
- Duyệt theo cột: các lần truy cập kế tiếp cách nhau `8` phần tử = `2` line; có nhiều line tranh chỗ trong cache chỉ giữ `4` line. Trước khi quay lại một line ở cột kế tiếp, nó đã bị đẩy, nên `64` lần đều miss.

Đây là **kết quả của mô hình giả định**, không phải dự đoán máy thật sẽ có đúng `0` hit khi duyệt ma trận 8×8: trên CPU thật, toàn bộ ví dụ có thể vừa cache lớn hơn, hardware prefetch có thể hoạt động, và `list[int]` Python có layout khác.

### Thay đổi capacity để thấy ảnh hưởng working set

Nếu thay `capacity_lines=16`, cache mô phỏng giữ được tất cả `16` line. Khi đó cả duyệt hàng và duyệt cột đều chỉ miss lần đầu cho mỗi line, tổng `16` miss. Thuật toán không đổi, **chỉ working set so với cache capacity thay đổi**.

Đây là ví dụ nhỏ cho lý do benchmark cùng mã trên tập dữ liệu kích thước khác nhau có thể cho xu hướng rất khác.

## 33. Mã Python ước tính I/O khối và so sánh mô hình

Để tập tư duy external-memory, ta có thể tính những số khối tối thiểu cần quét và độ cao mô hình của cây có hệ số phân nhánh `F`.

### Mã Python

```python
from math import ceil


def scan_blocks(item_count: int, items_per_block: int) -> int:
    if item_count < 0 or items_per_block <= 0:
        raise ValueError("Tham số không hợp lệ")
    return (item_count + items_per_block - 1) // items_per_block


def ideal_tree_levels(item_count: int, fanout: int) -> int:
    """
    Số mức tối thiểu của cây F-nhánh lý tưởng có item_count
    vị trí lá, không phải số I/O thật của một B+ tree.
    """
    if item_count < 0 or fanout < 2:
        raise ValueError("Tham số không hợp lệ")
    if item_count == 0:
        return 0

    levels = 1
    capacity = 1
    while capacity < item_count:
        capacity *= fanout
        levels += 1
    return levels


N = 1_000_000
B = 1_000
F = 100

print(scan_blocks(N, B))       # 1000
print(ideal_tree_levels(N, F)) # 4
```

### Ý nghĩa và giới hạn

- `scan_blocks` chỉ tính số **khối cần chứa `N` phần tử**, không tính cache, overhead file hoặc block đầu/cuối bị chia.
- `ideal_tree_levels` là **mô hình cây F-nhánh lý tưởng** với `item_count` vị trí lá. Nó **không mô phỏng cấu trúc B+ tree thực**: trang lá chứa nhiều bản ghi, fanout nút trong khác số mục/lá, có hệ số lấp đầy và phần trang có thể ở RAM.
- Không được lấy kết quả `4` ở đây rồi tuyên bố một B+ tree thực chứa một triệu **bản ghi** chắc chắn cần đúng bốn lần đọc khối.

Bài tập quan trọng là chuyển được từ **đơn vị byte sang số phần tử/block** một cách có lý do, rồi lựa chọn mô hình phù hợp với tầng bộ nhớ quan tâm.

## 34. Đánh giá hiệu năng: đừng chỉ đo một lần

Để so sánh hai cấu trúc dữ liệu hoặc thuật toán, hãy mô tả **đúng workload**:

1. Dữ liệu lớn bao nhiêu byte, bao nhiêu phần tử, mỗi phần tử chiếm bao nhiêu byte?
2. Workload là đọc, ghi, cập nhật hay hỗn hợp?
3. Truy cập tuần tự, ngẫu nhiên độc lập, theo cụm hay có phân bố nóng/lạnh?
4. Có bao nhiêu tiến trình/lõi cùng hoạt động? Bao nhiêu yêu cầu I/O đồng thời?
5. Dữ liệu đã nằm trong CPU cache/RAM/page cache hay mới đọc lần đầu?
6. API trả kết quả gì, có phải copy/giải nén/giải mã dữ liệu?
7. Có thao tác bảo trì như compaction, garbage collection, fsync hoặc flush giữa các lần đo không?

### Cold cache và warm cache

**Warm cache:** nhiều dữ liệu cần dùng đã có mặt trong tầng cache tương ứng. Ví dụ một truy vấn chỉ mục thực hiện nhiều lần thường tái dùng các nút gốc của B+ tree trong RAM.

**Cold cache:** dữ liệu chưa có hoặc đã bị thay thế trong cache mục tiêu. Một lần truy vấn có thể cần đọc từ tầng xa hơn.

**Quan trọng:** “cold CPU cache” không đồng nghĩa “cold page cache”; “tệp chưa từng đọc bởi tiến trình này” cũng không bảo đảm dữ liệu vắng mặt trong page cache của toàn hệ thống.

Không nên tự ý xóa cache hệ thống khi benchmark trên máy dùng chung; thao tác đó có thể ảnh hưởng các ứng dụng khác. Nếu cần kiểm soát điều kiện cold/warm, dùng môi trường đo chuyên dụng và phương pháp được phép, ghi rõ giả định.

### Đo latency và throughput riêng

Với truy cập điểm:

- Đo **độ trễ trung vị**, p95/p99 nếu workload có đuôi dài.
- Ghi số yêu cầu đồng thời.
- Đo kích thước một request và tỉ lệ cache hit.

Với quét file lớn:

- Đo byte/s hoặc GiB/s.
- Đo tổng thời gian đọc/ghi.
- Quan sát mức sử dụng CPU, băng thông thiết bị và thời gian chờ.

Một cấu hình có **throughput cao** dưới concurrency lớn có thể vẫn có **độ trễ một yêu cầu cao**. Tránh kết luận thay thế cấu trúc dữ liệu dựa trên đúng một con số.

### Counter/profiler liên quan

Tùy hệ điều hành và phần cứng, có thể quan sát:

| Phép đo | Dùng để trả lời |
|---|---|
| L1/L2/LLC cache misses | Dữ liệu có cục bộ ở tầng cache nào? |
| TLB misses | Truy cập có nhảy qua nhiều trang không? |
| Minor/major page faults | Bao nhiêu lần cần OS xử lý trang? Có phải chờ đọc file/swap? |
| Bytes read/written ở thiết bị | Workload thật sự tạo ra bao nhiêu I/O? |
| IOPS, request size, queue depth | Lưu trữ đang chịu mẫu yêu cầu nào? |
| CPU time, wall-clock time | Thời gian tính toán và thời gian chờ chênh nhau ra sao? |
| Allocations, RSS, peak memory | Layout có tiêu tốn bộ nhớ hoặc gây reclaim không? |
| p50/p95/p99 latency | Độ trễ thường gặp và đuôi dài ra sao? |

Một số counter chỉ là **ước lượng** hoặc không được phần cứng hỗ trợ ở mọi môi trường; cần hiểu định nghĩa metric và overhead công cụ đo.

### Đo đủ chuỗi thao tác

Nếu cấu trúc A cho `insert` nhanh nhưng phải `compact` sau mỗi một triệu insert, benchmark phải tính cả giai đoạn ấy. Nếu cấu trúc B quét nhanh nhưng xây chỉ mục lâu, hãy đo cả **build + query + update + memory** theo nhu cầu.

**Tối ưu hóa đúng là tối ưu tổng công việc của ứng dụng**, không chỉ tối ưu một câu lệnh đứng riêng.

## 35. Những lỗi nhận thức thường gặp

| Ngộ nhận | Thực tế | Cách tránh |
|---|---|---|
| “`O(1)` truy cập nào cũng nhanh như nhau” | Cache/RAM/SSD có độ trễ khác nhau | Xét locality và tầng dữ liệu |
| “`O(n)` nghĩa là cùng thời gian trên hai layout” | Một layout quét tuần tự, layout khác pointer-chase | Đo cache misses và byte truy cập |
| “CPU đọc từng byte thì chỉ nạp một byte” | Cache thường chuyển theo line | Ước lượng số line bị chạm |
| “Mọi cache CPU đều có line 64 B” | 64 B phổ biến, nhưng không bắt buộc | Kiểm tra kiến trúc mục tiêu |
| “Mọi trang VM đều 4 KiB” | Có nhiều page size, huge pages | Không hard-code khi mô hình đòi chính xác |
| “Truy cập hit cache L1 thì cần thêm RAM latency” | Hit ở tầng gần không đợi tầng sâu | Dùng AMAT có điều kiện |
| “L2 miss rate luôn tính trên tất cả access” | Có local/global miss rates | Ghi rõ mẫu số |
| “TLB miss là page fault” | TLB miss có thể giải quyết bằng page-table walk | Phân biệt sự kiện |
| “Page fault luôn đọc SSD” | Nhiều fault giải quyết trong RAM | Phân biệt minor/major và nguồn fault |
| “Dữ liệu đọc file lần hai chắc còn trong CPU cache” | OS page cache là RAM, không phải CPU cache | Phân biệt các tầng cache |
| “`mmap` tải toàn bộ file ngay lúc gọi” | Trang có thể nạp theo nhu cầu | Đo fault/I/O khi truy cập |
| “Direct I/O bỏ qua mọi cache” | Thường chỉ thay đường page cache OS | Hiểu hợp đồng API/thiết bị |
| “Ghi vào RAM nghĩa là đã bền vững” | RAM/cache volatile; flush/durability riêng | Thiết kế giao dịch/ghi bền vững |
| “SSD không quan tâm tuần tự hay ngẫu nhiên” | SSD vẫn có giới hạn IOPS/queue/read/write | Đo với request size và queue depth |
| “Một syscall bằng một I/O đĩa” | Buffering, read-ahead và cache làm chúng khác nhau | Đo ở đúng tầng |
| “B có đơn vị byte còn N là số record vẫn chia được” | Đơn vị không đồng nhất | Quy đổi về số record/block |
| “Binary search trên đĩa luôn `O(\log_B N)` I/O” | Các bước trên mảng có thể ở khối xa nhau | Xét B-tree/block layout |
| “B+ tree lá liên kết đồng nghĩa vật lý liền nhau” | Liên kết logic không đảm bảo vị trí vật lý | Đo fragmentation/range scan |
| “Sắp xếp ngoài RAM chỉ cần gọi sort()” | Dữ liệu có thể không vừa RAM | Tạo run + external merge |
| “LSM-tree luôn giảm mọi chi phí ghi” | Compaction có write amplification | Xét loại workload và policy |
| “Cache-oblivious = đệ quy bất kỳ” | Cần cách phân chia và chứng minh locality | Kiểm tra giả định mô hình |
| “AoS luôn tốt hơn SoA hoặc ngược lại” | Phụ thuộc số trường được dùng, vectorization, update | Đo layout theo workload |
| “Row-major và column-major có cùng locality” | Thứ tự duyệt khác stride bộ nhớ | Xét cách trải phẳng dữ liệu |
| “Tăng concurrency làm từng request nhanh hơn” | Có thể tăng throughput nhưng tăng latency khi queue đầy | Đo cả p95/p99 |
| “Mảng vừa RAM nghĩa là chắc vừa CPU cache” | Cache nhỏ hơn RAM nhiều | Xét working set từng tầng |
| “Benchmark có một lần chạy là đủ” | Warm-up, cache, GC, OS scheduling gây nhiễu | Lặp lại, ghi phương pháp |
| “Thiết bị quảng cáo 7 GB/s thì đọc 4 KiB tức thì” | Bandwidth tối đa khác latency request nhỏ | Đo latency và kích thước request |
| “Index đã tạo xong nên truy vấn không tốn bộ nhớ” | Page cache/buffer pool lưu index, con trỏ và metadata | Tính tổng footprint |

## 36. Quy trình chọn cấu trúc dữ liệu theo phân cấp bộ nhớ

Khi gặp một bài toán mới, có thể ra quyết định theo thứ tự:

**Bước 1 — Xác định dữ liệu hiện ở đâu.** Dữ liệu vừa cache CPU, vừa RAM, hay vượt RAM và nằm trên SSD/HDD? Nó là dữ liệu nóng hay chủ yếu quét một lần?

**Bước 2 — Xác định thao tác chủ đạo.** Nhiều point lookup, range scan, insert, delete, sort hay xử lý hàng loạt? Có yêu cầu cập nhật bền vững không?

**Bước 3 — Xác định kích thước và đơn vị.** `N` phần tử, `s` byte/phần tử, `N\cdot s` byte tổng. Nếu dùng I/O model, chuyển block `b` byte thành số bản ghi/block theo layout thực và overhead.

**Bước 4 — Chọn biểu diễn và layout.** Mảng liên tiếp, mảng trường SoA, B+ tree dạng trang, LSM-tree ghi theo lô, file có thứ tự hay cấu trúc khác? Có cần chỉ mục phụ?

**Bước 5 — Phân tích hai lớp chi phí.**

- **CPU/RAM:** số phép toán, số truy cập line, locality, allocation.
- **External I/O:** số block đọc/ghi, kích thước request, độ ngẫu nhiên và số pass.

**Bước 6 — Tính cả bảo trì và độ bền.** Cần buffer pool, write-back, flush/fsync, compaction, tái cân bằng, recovery hay không?

**Bước 7 — Benchmark bằng workload đại diện.** Đo warm/cold cache, throughput/latency, memory, cache miss, I/O, write amplification và biến động ở đuôi dài.

### Ví dụ quyết định

| Workload | Hướng lựa chọn ban đầu | Lý do |
|---|---|---|
| Quét các bản ghi số liên tiếp trong RAM | Mảng phẳng, layout cục bộ | Cache line/prefetch thuận lợi |
| Chèn rất nhiều phần tử ở giữa một mảng nhỏ | Tùy kích thước, vẫn benchmark mảng | Overhead cây có thể lớn hơn chi phí dịch chuyển nhỏ |
| Tìm khóa chính xác trên kho dữ liệu lớn | B+ tree hoặc chỉ mục khối phù hợp | Nhiều nhánh/trang, hạn chế I/O |
| Lọc một khoảng khóa trên dữ liệu có thứ tự | B+ tree + quét lá | Tìm đầu đoạn rồi đọc các trang tiếp theo |
| Ghi key/value cường độ cao và chấp nhận compaction | Cân nhắc LSM-tree | Gom ghi nhỏ, đánh đổi chi phí đọc/gộp |
| Sắp xếp file vượt RAM | External merge sort | Sử dụng run và lượt merge tuần tự |
| Thực hiện tính toán ma trận tái sử dụng dữ liệu | Blocking/tiling | Tăng tái sử dụng dữ liệu trong cache |

Đây là **điểm xuất phát để khảo sát**, không phải quyết định tuyệt đối cho mọi môi trường. Cần xét thiết bị, phần mềm, độ lớn dữ liệu, ràng buộc nghiệp vụ và cách triển khai cụ thể.

## 37. Bài tập tự kiểm tra

**Bài 1.** Sắp xếp register, L1 cache, RAM, SSD, HDD theo xu hướng tốc độ truy cập từ gần CPU đến xa CPU. Tại sao thứ tự này chỉ là xu hướng?

**Bài 2.** Phân biệt **độ trễ** và **băng thông**. Nếu một lần đọc `4 KiB` giả định mất `100 µs`, thông lượng của một chuỗi yêu cầu **không chồng lấp** xấp xỉ bao nhiêu MB/s thập phân?

**Bài 3.** Một cache line giả định dài `64 B` và mỗi phần tử mảng phẳng chiếm `8 B`. Khi dữ liệu căn chỉnh phù hợp, một line chứa bao nhiêu phần tử?

**Bài 4.** Giải thích temporal locality và spatial locality, mỗi loại cho một ví dụ.

**Bài 5.** Vì sao duyệt một danh sách liên kết có các nút cấp phát rời rạc có thể gây nhiều cache miss hơn duyệt mảng liên tiếp, dù cả hai `O(n)`?

**Bài 6.** Nêu ba nhóm cache miss theo mô hình 3C. Hệ thống nhiều lõi còn có thể có nguồn miss/stall nào khác?

**Bài 7.** Với L1 hit time `1 ns`, L1 miss rate `5\%`, L2 hit time `5 ns`, L2 local miss rate `20\%`, penalty tầng sâu `80 ns`, hãy tính AMAT.

**Bài 8.** Theo số giả định ở bài 7, bao nhiêu phần trăm **toàn bộ** truy cập phải xuống sâu hơn L2?

**Bài 9.** Tại sao `AMAT=2.05 ns` không có nghĩa mỗi lệnh của chương trình chạy đúng `2.05 ns`?

**Bài 10.** Phân biệt cache line và page. Kích thước `64 B` và `4 KiB` tương ứng với đơn vị nào trong ví dụ phổ biến?

**Bài 11.** Phân biệt TLB miss và page fault. Mọi page fault có phải đọc từ SSD không?

**Bài 12.** Lần đọc thứ hai của một file nhanh hơn lần thứ nhất. Điều này có đủ chứng minh file nằm trong L1 cache không?

**Bài 13.** Mô tả khác biệt giữa buffered I/O, `mmap` và direct I/O ở mức ý tưởng. `mmap` có buộc tải toàn bộ file vào RAM ngay không?

**Bài 14.** Vì sao đọc file từng byte bằng nhiều lời gọi `read` thường có overhead cao hơn đọc theo khối? Có phải mỗi `read` luôn tạo I/O vật lý?

**Bài 15.** Nếu CPU đã ghi vào RAM, có thể khẳng định file tương ứng đã bền vững khi mất điện không? Cần quan tâm thêm cơ chế nào?

**Bài 16.** Tại sao HDD thường chịu bất lợi lớn khi phải đọc ngẫu nhiên nhiều khối nhỏ? SSD có loại bỏ hoàn toàn chi phí random I/O không?

**Bài 17.** Trong external-memory model, `N`, `M`, `B` biểu diễn gì? Tại sao đơn vị của `N` và `B` phải nhất quán?

**Bài 18.** Với `N=1{,}000{,}000` bản ghi, một I/O chứa `B=1000` bản ghi, quét toàn bộ file cần bao nhiêu block đọc trong mô hình?

**Bài 19.** Dữ liệu có `100{,}000{,}000` bản ghi, mỗi bản ghi `100 B`, trang dữ liệu `4096 B` và không tính header/padding. Tính số bản ghi **nguyên vẹn tối đa trên một trang** và số trang tối thiểu để chứa tất cả bản ghi nếu không cho bản ghi vượt biên trang.

**Bài 20.** Vì sao binary search trên mảng lưu ngoài RAM có thể tốn `O(\log N)` I/O, trong khi B-tree có thể đạt cận dạng `O(\log_B N)` dưới giả định phù hợp?

**Bài 21.** Trong B+ tree, để lấy `K` bản ghi ở một khoảng khóa liên tục, mô tả hai giai đoạn chính của truy vấn.

**Bài 22.** Dữ liệu có `N=1{,}000{,}000` bản ghi, RAM giữ `M=100{,}000` bản ghi và block `B=1000` bản ghi. External merge sort tạo bao nhiêu run ban đầu? Một lượt merge có thể gộp các run này nếu dùng một buffer đọc/run và một buffer ghi không?

**Bài 23.** Với giả thiết bài 22, bỏ qua overhead/làm tròn nhỏ, tổng số I/O khối đọc + ghi để tạo run và thực hiện đúng **một lượt merge cuối** xấp xỉ bao nhiêu?

**Bài 24.** Giải thích sự khác nhau giữa B+ tree và LSM-tree về ghi nhỏ và chi phí bảo trì. Vì sao LSM không mặc nhiên có write amplification thấp?

**Bài 25.** Nêu ví dụ workload phù hợp với AoS và ví dụ workload phù hợp với SoA.

**Bài 26.** Mảng `8\times8` phẳng row-major, mỗi cache line mô phỏng chứa 4 phần tử và cache LRU chỉ giữ 4 line. Duyệt theo hàng và cột lần lượt có bao nhiêu miss theo mô hình ở bài?

**Bài 27.** Nếu tăng cache mô phỏng ở bài 26 lên 16 line, vì sao hai thứ tự duyệt cùng có thể chỉ còn 16 miss?

**Bài 28.** Khi tính tổng mỗi phần tử của ma trận đúng một lần, có phải chia tile luôn nhanh hơn duyệt row-major tuyến tính không? Khi nào tiling hữu ích hơn?

**Bài 29.** Giải thích vì sao direct I/O, CPU cache và OS page cache không phải ba cách gọi cho một cơ chế.

**Bài 30.** Khi benchmark một chỉ mục trên SSD, tại sao cần ghi kích thước request, queue depth, warm/cold cache và latency p95/p99 thay vì chỉ báo MB/s?

**Bài 31.** Một ứng dụng chỉ đọc tuần tự file khổng lồ một lần, một ứng dụng khác truy vấn nhiều lần cùng vùng nhỏ. Hai ứng dụng nên kỳ vọng gì khác nhau từ caching?

**Bài 32.** Nêu ba tình huống mà độ phức tạp Big-O trên RAM không đủ để chọn cấu trúc dữ liệu và cần phân tích thêm chi phí phân cấp bộ nhớ.

## 38. Đáp án và giải thích

**Bài 1.** Thứ tự xu hướng: register → cache gần (L1, L2, L3) → RAM → SSD → HDD. Đó chỉ là xu hướng bởi kiến trúc, thiết bị, caching, concurrency và pattern I/O thực tế khác nhau; SSD vẫn có thể chậm hơn nhiều trường hợp tùy request, HDD tuần tự có thể tốt hơn một workload random SSD kém cấu hình.

**Bài 2.** Latency là thời gian hoàn thành một yêu cầu; bandwidth là tổng byte truyền trên đơn vị thời gian. Với `4 KiB/100 µs`: `4096/(100\times10^{-6})=40{,}960{,}000 B/s=40.96 MB/s` cho chuỗi yêu cầu không chồng lấp.

**Bài 3.** `64/8=8` phần tử nếu layout đúng như giả định và không bị cắt giữa hai line do alignment.

**Bài 4.** Temporal locality: đọc lại biến hoặc vùng dữ liệu vừa dùng, ví dụ lặp tăng một counter. Spatial locality: dùng địa chỉ gần địa chỉ vừa đọc, ví dụ quét mảng liên tiếp.

**Bài 5.** Một cache line mang về nhiều phần tử mảng kề nhau, còn con trỏ danh sách có thể nhảy sang line/trang xa; pointer chasing khó prefetch. Cả hai vẫn cùng bậc `O(n)` bước ở RAM model.

**Bài 6.** Compulsory, capacity và conflict misses. Trong hệ đa lõi, coherence invalidation và tranh chấp tài nguyên còn gây miss/stall.

**Bài 7.** `AMAT=1+0.05(5+0.20\times80)=2.05 ns`.

**Bài 8.** `0.05\times0.20=0.01=1\%` toàn bộ truy cập (L2 miss rate là có điều kiện trên L1 misses).

**Bài 9.** AMAT là kỳ vọng chi phí truy cập theo mô hình; chương trình còn có tính toán, phụ thuộc dữ liệu, truy cập song song, prefetch, stalls và cache/memory-level parallelism.

**Bài 10.** Cache line thường là đơn vị chuyển/lưu ở cache CPU; page là đơn vị ánh xạ bộ nhớ ảo. Ví dụ `64 B` tương ứng cache line, `4 KiB` tương ứng page cơ sở phổ biến, nhưng cấu hình khác vẫn có thể tồn tại.

**Bài 11.** TLB miss chỉ là thiếu bản ghi dịch địa chỉ và có thể giải quyết bằng page-table walk. Page fault cần OS xử lý một điều kiện ánh xạ/truy cập; nhiều minor fault không cần đọc SSD/HDD.

**Bài 12.** Không. Dữ liệu có thể còn trong OS page cache ở RAM nhưng không trong L1; phần cứng, bộ đệm thư viện và tầng khác cũng có thể góp phần.

**Bài 13.** Buffered I/O sử dụng bộ đệm/page cache thông thường; `mmap` ánh xạ file vào địa chỉ ảo và nạp trang khi cần; direct I/O có thể hạn chế/bỏ qua page cache của OS cho I/O tương ứng. `mmap` không đòi nạp toàn file ngay.

**Bài 14.** Gọi `read` rất nhiều lần làm tăng overhead API/syscall và chuyển chế độ; đọc theo block giảm số lượt giao tiếp. Không, một syscall có thể hit page cache hoặc tạo nhiều/không tạo I/O vật lý.

**Bài 15.** Không. CPU cache/RAM thường volatile, dữ liệu cần được truyền xuống tầng lưu trữ và tuân hợp đồng durability của hệ điều hành/hệ thống file/thiết bị, ví dụ cơ chế đồng bộ, flush/fsync và giao dịch phù hợp.

**Bài 16.** HDD phải chờ seek và quay đĩa, khiến random I/O nhiều khối nhỏ đắt. SSD bỏ cơ học nhưng vẫn có controller, hàng đợi, FTL, giới hạn IOPS và chi phí quản lý flash.

**Bài 17.** `N` là số mục, `M` là số mục vừa bộ nhớ trong, `B` là số mục mỗi block truyền; nếu `N` là bản ghi mà `B` là byte thì `N/B` vô nghĩa về đơn vị cho số block.

**Bài 18.** `\lceil1{,}000{,}000/1000\rceil=1000` block đọc, theo giả định mỗi khối mang 1000 bản ghi và không tính caching.

**Bài 19.** Một trang `4096 B` chứa tối đa `\lfloor4096/100\rfloor=40` bản ghi nguyên vẹn. Cần ít nhất `\lceil100{,}000{,}000/40\rceil=2{,}500{,}000` trang, tức số trang tối thiểu trong mô hình không vượt biên và bỏ overhead.

**Bài 20.** Binary search trên mảng chọn các phần tử giữa, có thể chạm các block ngẫu nhiên khác nhau ở mỗi lần so sánh. B-tree đặt nhiều khóa/con trong một block và loại nhiều nhánh sau mỗi I/O nên chiều cao theo fanout `F=\Theta(B)` có thể là `O(\log_B N)`.

**Bài 21.** Trước hết điều hướng cây từ gốc tới lá bắt đầu của đoạn; sau đó quét các trang lá theo thứ tự khóa tới khi vượt biên phải, lợi dụng batching và locality của các trang lá.

**Bài 22.** `R=\lceil1{,}000{,}000/100{,}000\rceil=10` run. Bộ nhớ chứa `M/B=100` buffer một block; có thể dùng `10` buffer đầu vào + một output, nên gộp 10 run trong một lượt.

**Bài 23.** Mỗi pass đọc `1000` block và ghi `1000` block, tức `2000` I/O. Giai đoạn tạo run và một lượt merge là hai pass: khoảng `4000` I/O khối (bỏ overhead).

**Bài 24.** B+ tree cập nhật trang cây/nhật ký theo khóa; LSM thường ghi vào memtable/log rồi flush theo run tuần tự, nhưng compaction có thể phải đọc/ghi lại cùng dữ liệu nhiều lần nên vẫn có write amplification đáng kể.

**Bài 25.** AoS thuận lợi nếu mỗi lần xử lý một bản ghi cần toàn bộ các trường `x,y,z`. SoA thuận lợi nếu quét một trường như `x` trên toàn bộ bản ghi, tránh đọc các trường không dùng.

**Bài 26.** Trong mô hình LRU của phần 32: duyệt theo hàng `16` miss, `48` hit; duyệt theo cột `64` miss, `0` hit. Đây là mô phỏng với working set và cache capacity giả định, không phải số đo CPU thật.

**Bài 27.** Có tổng cộng `16` line; cache giữ được tất cả nên mỗi line chỉ miss **một lần đầu**, bất kể thứ tự duyệt, nếu không có dữ liệu khác chen vào.

**Bài 28.** Không. Nếu chỉ đọc mỗi phần tử một lần, quét row-major liên tiếp đã có locality tốt; tiling hữu ích hơn khi cùng submatrix được tái sử dụng nhiều lần, chẳng hạn nhân ma trận.

**Bài 29.** Direct I/O điều chỉnh con đường I/O qua bộ đệm hệ điều hành; CPU cache là tầng phần cứng gần lõi; OS page cache là vùng RAM giữ dữ liệu file. Chúng hoạt động ở các tầng và theo cơ chế khác nhau.

**Bài 30.** MB/s không cho biết độ trễ mỗi truy vấn nhỏ, hàng đợi chờ, cache hit hay đuôi latency. Kích thước request/queue depth và điều kiện cold/warm làm thay đổi mạnh kết quả; p95/p99 cho biết trải nghiệm trường hợp chậm.

**Bài 31.** Quét file lớn một lần có thể tận dụng read-ahead/streaming, nhưng không cần giữ toàn bộ file lâu trong cache. Truy vấn lặp vùng nhỏ hưởng lợi nhiều từ temporal locality ở page cache, RAM hoặc CPU cache.

**Bài 32.** Ví dụ: (1) quét mảng liên tiếp so với danh sách liên kết phân tán; (2) binary search trên file đĩa so với B+ tree theo trang; (3) dữ liệu vừa RAM so với vượt RAM gây swap; (4) xử lý AoS chỉ dùng một trường so với SoA; (5) sort trong RAM so với external merge sort.

## 39. Ghi nhớ

**Phân cấp lưu trữ** gồm các tầng có **dung lượng, độ trễ, băng thông và tính bền vững khác nhau**: thanh ghi phục vụ toán hạng đang dùng, L1/L2/L3 giữ các cache line gần CPU, RAM là bộ nhớ chính, còn SSD/HDD lưu dữ liệu bền vững qua I/O theo khối. Hiệu năng không chỉ phụ thuộc **số phép toán Big-O** mà còn phụ thuộc **locality**, tỷ lệ cache hit/miss, prefetch, TLB, page fault, page cache, cách đọc/ghi và kích thước working set. Trong dữ liệu ngoài RAM, mô hình external memory dùng **`N` phần tử, `M` phần tử vừa RAM, `B` phần tử/block** để đếm số truyền khối: quét tuần tự có **`\Theta(N/B)` I/O**, B-tree tận dụng fanout lớn để giảm chiều cao, còn external merge sort sắp dữ liệu vượt RAM bằng các lượt đọc/ghi tuần tự. Trong RAM, bố trí mảng/AoS/SoA và chia tile thay đổi tính cục bộ dù bậc phép toán có thể giữ nguyên. Khi chọn cấu trúc dữ liệu, hãy cùng lúc hỏi **dữ liệu ở tầng nào, thao tác chủ đạo là gì, kích thước mỗi block và working set bao nhiêu, cách cập nhật/bảo đảm durability thế nào và benchmark đã phản ánh workload thực tế chưa**.
