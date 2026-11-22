# Sắp xếp trộn ngoài bộ nhớ

**Sắp xếp trộn ngoài bộ nhớ** (*external merge sort*) là thuật toán sắp xếp dành cho tập dữ liệu **lớn hơn dung lượng RAM có thể sử dụng**. Thay vì cố tải toàn bộ dữ liệu vào mảng rồi gọi `Arrays.sort`, thuật toán chỉ đọc **một phần vừa bộ nhớ**, sắp xếp phần ấy và ghi ra **run** (một tệp/đoạn đã được sắp xếp). Sau đó nó trộn các run theo **nhiều đường** (*k-way merge*) và, nếu có quá nhiều run so với ngân sách bộ nhớ hoặc số tệp có thể mở, tiếp tục trộn qua **nhiều lượt** (*multi-pass merging*).

Đặc điểm khác biệt của bài toán này là chi phí quan trọng không chỉ là số phép so sánh trong CPU mà còn là **số khối dữ liệu đọc/ghi giữa thiết bị lưu trữ và RAM**. Trong mô hình bộ nhớ ngoài (*external-memory/I/O model*), I/O thường đắt hơn phép so sánh dữ liệu đã ở trong RAM, nên thuật toán cố gắng đọc/ghi **theo chuỗi và theo khối**, tránh truy cập ngẫu nhiên quá nhiều lần.

Bài này giải thích đầy đủ:

- Vì sao sắp xếp nội bộ không đủ khi dữ liệu không vừa RAM.
- Hai giai đoạn **tạo các run ban đầu** và **trộn nhiều run đã sắp xếp**.
- Trộn k-way bằng **min-heap** chỉ giữ một đầu run trong heap.
- Vì sao cần **giới hạn fan-in** và các lượt trộn trung gian.
- Phân tích theo N bản ghi, M bản ghi RAM và B bản ghi mỗi khối I/O; phân biệt I/O complexity và CPU complexity.
- Chứng minh **đúng thứ tự và bảo toàn đủ mọi bản ghi, kể cả phần tử lặp**.
- Giới hạn bộ đệm, file descriptor, tệp tạm, độ ổn định, lỗi I/O và khôi phục.
- Chương trình **Java 17+ độc lập**, sắp xếp các bản ghi `long` 8 byte dạng nhị phân bằng bộ nhớ hữu hạn, tự xóa tệp trung gian, kèm ví dụ và kiểm thử đối chiếu với `Arrays.sort` trên dữ liệu nhỏ.

Mục tiêu không phải gọi mọi thao tác sử dụng đĩa là “external sorting”, mà là thiết kế một quy trình **không yêu cầu n phần tử cùng có mặt trong RAM** và có chi phí I/O được phân tích rõ ràng.

## 1. Khi nào cần sắp xếp ngoài bộ nhớ?

Giả sử phải sắp xếp một tệp có:

\[
N=10^9\text{ bản ghi}.
\]

Nếu mỗi bản ghi dài 8 byte thì riêng dữ liệu có kích thước:

\[
8N=8\cdot10^9\text{ byte}\approx8\text{ GB (hệ thập phân)}.
\]

Nếu chương trình chỉ có 256 MiB RAM dành cho vùng sắp xếp, toàn bộ dữ liệu chắc chắn **không thể được giữ trong một mảng RAM cùng lúc**.

Các tình huống thực tế có thể gặp:

- Sắp xếp log của nhiều tháng trước khi phân tích.
- Sắp xếp các giao dịch theo thời gian hoặc mã khách hàng.
- Chuẩn bị các tệp khóa được sắp xếp phục vụ merge join.
- Sắp xếp dữ liệu trung gian trong cơ sở dữ liệu.
- Sắp xếp danh sách các khóa khi tạo chỉ mục hoặc tái tổ chức tệp.
- Xử lý dữ liệu khoa học lớn hơn giới hạn bộ nhớ một tiến trình.
- Tập dữ liệu phân tán đã có các phần **được sắp xếp cục bộ**, cần tạo kết quả toàn cục.

Trong các trường hợp đó, cách tiếp cận:

~~~java
long[] all = readEntireFileIntoArray();
Arrays.sort(all);
writeEntireArray(all);
~~~

không phù hợp nếu bộ nhớ cần cho `all` vượt giới hạn. Việc đọc tệp bằng stream thay vì `readAllBytes` chỉ là bước đầu; thuật toán còn phải **tránh tích lũy dần toàn bộ dữ liệu ở cấu trúc khác** như `ArrayList<Long>`.

## 2. Hai loại bộ nhớ và sự khác nhau về chi phí

**RAM** có thời gian truy cập nhỏ và phù hợp với thuật toán sắp xếp nội bộ.

**Bộ nhớ ngoài** là SSD/HDD hoặc các thiết bị lưu trữ khác, thường có:

- Dung lượng lớn hơn RAM khả dụng của một tiến trình.
- Truyền dữ liệu hiệu quả hơn khi đọc/ghi theo khối.
- Chi phí mở tệp, seek, chờ I/O, truyền dữ liệu, ghi bộ đệm.
- Giới hạn số luồng đọc/ghi và số file descriptor mở đồng thời.

Một lượt so sánh hai số `long` trong RAM thường rất rẻ so với việc phải thực hiện một lần đọc đĩa không có dữ liệu sẵn trong cache. Vì vậy trong external sorting ta quan tâm nhiều đến **số lần quét tuần tự** và **số lượt trộn**.

### Không nên tuyệt đối hóa điều này

Trên SSD hiện đại, sự khác biệt ngẫu nhiên/tuần tự có thể nhỏ hơn trên HDD; cache hệ điều hành có thể giữ phần lớn dữ liệu; bộ nén, mạng và CPU có thể trở thành nút thắt. Nhưng **mô hình chi phí theo khối** vẫn là công cụ hữu ích để thiết kế thuật toán và tránh các thao tác đĩa O(N²) không cần thiết.

## 3. Các tham số của bài toán

Dùng các ký hiệu:

| Ký hiệu | Ý nghĩa |
|---|---|
| **N** | Tổng số bản ghi cần sắp xếp |
| **M** | Số bản ghi có thể giữ trong RAM dành cho giai đoạn tạo run |
| **B** | Số bản ghi nằm trong một khối truyền I/O hiệu dụng |
| **F** | Số run có thể trộn đồng thời (*fan-in*) |
| **R₀** | Số run ban đầu |
| **P** | Số lượt trộn sau giai đoạn tạo run |

Giả sử:

\[
N\ge0,\qquad M\ge1,\qquad B\ge1,\qquad F\ge2.
\]

Nếu mỗi run ban đầu chứa tối đa M bản ghi, số run là:

\[
\boxed{R_0=\left\lceil\frac{N}{M}\right\rceil.}
\]

Với N=0, quy ước R₀=0.

Ở mỗi lượt trộn có fan-in F, số run giảm xấp xỉ:

\[
R_{t+1}=\left\lceil\frac{R_t}{F}\right\rceil.
\]

Nếu \(R_0>1\), số lượt trộn cần đến khi còn một run là:

\[
\boxed{P=\left\lceil\log_F R_0\right\rceil.}
\]

Nếu \(R_0\in\{0,1\}\), P=0: không cần trộn run.

### M là ngân sách dữ liệu, không nhất thiết là toàn bộ RAM

Trong mã Java minh họa, tham số `chunkRecords` tương ứng M **bản ghi trên một run ban đầu**. Nhưng tiến trình còn cần bộ đệm đọc/ghi, bộ đếm, hàng đợi ưu tiên, đối tượng stream và bộ nhớ của JVM.

Do đó không được đặt:

~~~text
M = 100 triệu bản ghi long
~~~

chỉ vì RAM có 800 MB rồi quên toàn bộ chi phí bổ sung. Phải tính **ngân sách thực tế có phần dự phòng**.

## 4. Hai pha chính của external merge sort

Một kiến trúc dễ hiểu gồm:

**Pha 1 — tạo run (*run generation*):**

1. Đọc tối đa M bản ghi từ tệp đầu vào.
2. Sắp xếp chúng trong RAM.
3. Ghi thành một run trên đĩa.
4. Lặp cho đến khi hết đầu vào.

Mỗi run đã sắp xếp, nhưng các run **chưa chắc đã được sắp xếp so với nhau**.

**Pha 2 — trộn (*merge passes*):**

1. Chọn tối đa F run đã sắp xếp.
2. Mở bộ đọc có đệm cho mỗi run.
3. Dùng min-heap giữ **bản ghi đầu chưa lấy** của mỗi run.
4. Liên tục lấy bản ghi nhỏ nhất và ghi vào run đầu ra.
5. Khi một run còn phần tử, lấy phần tử tiếp theo của chính run đó vào heap.
6. Lặp lại với các nhóm run còn lại.
7. Nếu sau lượt trộn vẫn có nhiều run, thực hiện một lượt tiếp theo.

Tư duy quan trọng là: **trộn các run đã có thứ tự**, không sắp xếp lại toàn bộ dữ liệu bằng một phép sort trong RAM.

~~~text
Tệp đầu vào chưa sắp xếp
       |
       v
[Đọc khối vừa RAM] -> [Sort trong RAM] -> run_0
[Đọc khối vừa RAM] -> [Sort trong RAM] -> run_1
[Đọc khối vừa RAM] -> [Sort trong RAM] -> run_2
...
       |
       v
Trộn nhóm tối đa F run -> các run lớn hơn
       |
       v
Nếu còn nhiều run, trộn tiếp nhiều lượt
       |
       v
Một run đã sắp xếp toàn cục -> tệp kết quả
~~~

## 5. Tạo run ban đầu như thế nào?

Giả sử dữ liệu gồm 17 số và chỉ giữ tối đa 4 bản ghi trong mảng RAM để sắp xếp:

~~~text
12, -3, 7, 7,
0, 18, -10, 4,
4, 99, 1, -1,
5, 3, 8, -10,
2
~~~

Đọc 4 bản ghi một lần, sort rồi ghi:

| Run | Bản ghi gốc | Nội dung run sau khi sort |
|---|---|---|
| R0 | [12,-3,7,7] | [-3,7,7,12] |
| R1 | [0,18,-10,4] | [-10,0,4,18] |
| R2 | [4,99,1,-1] | [-1,1,4,99] |
| R3 | [5,3,8,-10] | [-10,3,5,8] |
| R4 | [2] | [2] |

Số run:

\[
\boxed{R_0=\lceil17/4\rceil=5.}
\]

Mỗi run **đúng thứ tự không giảm**. Nhưng không thể nối trực tiếp:

~~~text
R0 + R1 + R2 + R3 + R4
~~~

vì phần tử -10 ở R1 phải đứng trước nhiều phần tử ở R0.

### Run cuối không đủ M phần tử

Điều này hoàn toàn bình thường. Nếu N không chia hết cho M, run cuối chỉ có:

\[
N\bmod M
\]

phần tử (nếu dư khác 0). Không được thêm các giá trị giả như 0, `Long.MAX_VALUE` hoặc số âm vào run cuối rồi quên xóa; những giá trị ấy có thể trở thành bản ghi thật trong kết quả.

### Run trên đĩa là gì?

Run có thể là:

- Một tệp tạm riêng có các bản ghi đã sắp xếp.
- Một đoạn có offset và length bên trong một tệp lớn.
- Một đối tượng dữ liệu trên hệ lưu trữ phân tán.

Mã Java chọn cách dễ hiểu: **mỗi run là một tệp nhị phân riêng**, mang theo `count` số bản ghi, và tệp trung gian được xóa khi không cần nữa.

## 6. Trộn hai run đã sắp xếp

Trước k-way merge, xét phép trộn hai dãy:

~~~text
A = [-3,  7, 7, 12]
B = [-10, 0, 4, 18]
~~~

Ta giữ **con trỏ** ở đầu mỗi run:

1. So sánh -3 và -10, lấy -10 từ B.
2. So sánh -3 và 0, lấy -3 từ A.
3. So sánh 7 và 0, lấy 0 từ B.
4. So sánh 7 và 4, lấy 4 từ B.
5. So sánh 7 và 18, lấy 7 từ A.
6. Tiếp tục cho đến khi một run hết.
7. Chép phần còn lại của run kia.

Kết quả:

~~~text
[-10, -3, 0, 4, 7, 7, 12, 18]
~~~

Từ đầu đến cuối, ta **không cần đọc toàn bộ hai run vào RAM**. Chỉ cần con trỏ/buffer đầu của mỗi run và buffer đầu ra.

### Trộn hai đường và trộn nhiều đường

Trộn hai đường (*2-way merge*) chỉ mở hai run đầu vào một lúc. Nếu có hàng nghìn run, số lượt trộn có thể lớn:

\[
P\approx\lceil\log_2 R_0\rceil.
\]

Nếu RAM và giới hạn tệp cho phép mở F run đồng thời, trộn F đường giúp giảm số lượt còn:

\[
P\approx\lceil\log_F R_0\rceil.
\]

Chính vì vậy **multiway merge** là tối ưu quan trọng của external merge sort.

## 7. Trộn F run bằng min-heap

Giả sử có F run đã sắp xếp. Mỗi run có một đầu đọc, cùng các bản ghi chưa sử dụng nằm phía sau.

Ta chỉ cần lưu trong min-heap:

\[
(value,\ runId)
\]

ứng với **bản ghi đầu hiện tại** của mỗi run chưa cạn.

Quy trình:

~~~text
for each run i:
    read its first record if present
    put (value, i) into minHeap

while minHeap not empty:
    (value, i) = removeMin()
    write value to output

    if run i still has records:
        next = read next record from run i
        put (next, i) into minHeap
~~~

Kích thước heap:

\[
\boxed{\le F.}
\]

Mỗi bản ghi được **lấy ra đúng một lần** và, trừ trường hợp run rỗng, nguồn vừa được lấy ra được nạp tiếp **tối đa một phần tử**.

### Tại sao phần tử nhỏ nhất đang chờ luôn nằm trong heap?

Mỗi run đã sắp xếp không giảm. Với run i, bản ghi đầu **chưa được xuất** luôn không lớn hơn những bản ghi chưa xuất còn lại của run đó.

Do heap có đúng một đầu hiện tại của mỗi run còn dữ liệu, phần tử nhỏ nhất trên **toàn bộ các run chưa dùng** phải là một trong các đầu ấy. Min-heap chọn nhỏ nhất trong số chúng, nên bản ghi vừa ghi ra **không lớn hơn** bất kỳ bản ghi nào sẽ ghi ra sau.

### Chi phí CPU

Với T bản ghi trong nhóm F run:

- T lần lấy `removeMin`.
- T lần đưa phần tử tiếp theo vào heap, trừ khi run cạn.
- Mỗi thao tác heap tốn O(log F).

Vì vậy:

\[
\boxed{O(T\log F)\text{ phép xử lý heap}}
\]

cho một lần trộn F đường.

Heap chỉ chứa tối đa F phần tử, **không chứa toàn bộ T phần tử**.

## 8. Vì sao cần bộ đệm cho từng run?

Nếu mỗi thao tác `readLong()` khiến hệ thống đọc 8 byte trực tiếp từ đĩa bằng một I/O riêng, chương trình có thể tạo rất nhiều yêu cầu nhỏ. Thiết kế đúng thường cấp phát:

- **Một bộ đệm đầu vào** cho mỗi run đang trộn.
- **Một bộ đệm đầu ra** cho run kết quả.
- **Min-heap** giữ đầu của mỗi run.

Với F luồng đầu vào, mỗi bộ đệm dài \(B_{\text{bytes}}\) byte:

\[
\boxed{\text{RAM buffer trộn}\approx(F+1)B_{\text{bytes}}}
\]

cộng chi phí heap và đối tượng stream.

Trong mô hình theo bản ghi, nếu một khối chứa B bản ghi thì bộ nhớ đệm trộn có bậc:

\[
\boxed{O(FB+F).}
\]

### Một ràng buộc fan-in thực tế

Nếu ngân sách RAM dành cho merge là \(M_{\text{bytes}}\), không thể chọn F lớn tùy ý. Cần ít nhất một buffer cho mỗi đầu vào và một buffer đầu ra, nên ở mức xấp xỉ:

\[
(F+1)B_{\text{bytes}}+\text{overhead}
\le M_{\text{bytes}}.
\]

Ngoài bộ nhớ, hệ điều hành còn giới hạn **số tệp có thể mở đồng thời**, vì mỗi run đầu vào cần file descriptor.

Vì vậy F thường chọn theo **cả ngân sách RAM lẫn file descriptors**. Nếu F quá lớn có thể gây `Too many open files`, hết bộ nhớ buffer hoặc giảm hiệu năng do tranh chấp I/O.

### Giới hạn không nằm ở số bản ghi N

Một tệp chứa 1 tỷ bản ghi không có nghĩa phải mở 1 tỷ đầu đọc. Ta chỉ mở F run một lượt rồi trộn chúng thành những run lớn hơn. Vì thế số descriptor đang mở là O(F), không phải O(R₀) hay O(N).

## 9. Nhiều lượt trộn khi có quá nhiều run

Trở lại ví dụ N=17, M=4:

\[
R_0=5.
\]

Giả sử fan-in F=3. Không thể trộn đồng thời cả 5 run trong một nhóm, vì giới hạn thiết kế chỉ cho 3 đầu vào.

**Lượt trộn thứ nhất:**

- Nhóm 1: trộn R0, R1, R2 → run T0 chứa 12 bản ghi.
- Nhóm 2: trộn R3, R4 → run T1 chứa 5 bản ghi.

Hai run sau lượt 1:

~~~text
T0 = [-10, -3, -1, 0, 1, 4, 4, 7, 7, 12, 18, 99]
T1 = [-10, 2, 3, 5, 8]
~~~

Còn:

\[
R_1=\lceil5/3\rceil=2.
\]

**Lượt trộn thứ hai:**

- Trộn T0 và T1 → một run duy nhất chứa 17 bản ghi.

Kết quả:

~~~text
[-10, -10, -3, -1, 0, 1, 2, 3, 4,
  4, 5, 7, 7, 8, 12, 18, 99]
~~~

Số lượt trộn:

\[
\boxed{P=\lceil\log_3 5\rceil=2.}
\]

Số **nhóm thực sự được trộn** là 3: hai nhóm trong lượt đầu và một nhóm trong lượt sau.

### Nhóm chỉ có một run thì sao?

Nếu một lượt có số run không chia hết F, nhóm cuối có thể chỉ có 1 run.

Ví dụ F=3 và có 7 run:

~~~text
7 -> 3 -> 1
      ^
      nhóm thứ ba ở lượt đầu chỉ có 1 run
~~~

Một run đơn lẻ vốn đã sắp xếp, có thể **chuyển nguyên sang lượt tiếp theo** mà không cần đọc/ghi lại. Bản Java minh họa dùng cách này để giảm I/O không cần thiết.

Tuy nhiên, những run trong nhóm nhiều hơn một phải được trộn thật; không được nối tệp của chúng rồi tuyên bố đã có một run được sắp xếp.

## 10. Số lượt I/O: mô hình N–M–B

Trong mô hình external memory, giả sử:

- N bản ghi cần sắp.
- RAM cho phép xử lý M bản ghi trong lần tạo run.
- Một lần truyền dữ liệu giữa đĩa và bộ nhớ có B bản ghi.
- Fan-in F phù hợp ngân sách buffer/file descriptor.

### A. Tạo run ban đầu

Đọc toàn bộ input một lần và ghi toàn bộ run một lần:

\[
\boxed{\text{I/O generation}=O(N/B)}
\]

tính theo bậc số khối, vì cả đọc và ghi có cùng cỡ N/B (một hệ số 2 không đổi).

### B. Mỗi lượt merge

Khi một lượt trộn đưa toàn bộ run sang thế hệ run mới, mỗi bản ghi về cơ bản:

- Được đọc từ run cũ.
- Được ghi vào run mới.

Do đó mỗi lượt có:

\[
\boxed{O(N/B)\text{ block I/Os}.}
\]

Nếu có những run đơn lẻ được chuyển qua mà không ghi lại, I/O thực tế có thể ít hơn cận trên.

### C. Tổng số lượt

Với:

\[
R_0=\lceil N/M\rceil,\quad
P=\lceil\log_F R_0\rceil
\]

(khi R₀>1), ta có:

\[
\boxed{\text{I/O}=O\left(\frac NB(1+P)\right).}
\]

Một cách viết thường gặp:

\[
\boxed{O\left(
\frac NB
\left[1+\log_F\left(\frac NM\right)\right]
\right)}
\]

với trường hợp N≤M được xử lý riêng, và các giả định số khối được làm tròn phù hợp.

Nếu F có thể chọn khoảng \(M/B\) trong mô hình lý tưởng, cận thường được viết:

\[
\boxed{O\left(
\frac NB \log_{M/B}\frac NB
\right)}
\]

cho miền tham số sắp xếp ngoài bộ nhớ thích hợp, bỏ qua các hằng số, bước quét cơ sở và cách làm tròn.

### D. Bản Java có thêm một bước sao chép cuối

Để dễ hiểu và đảm bảo dọn được toàn bộ tệp tạm, mã Java:

1. Tạo các run tạm.
2. Merge tới **một run tạm cuối**.
3. `Files.copy` run tạm đó sang đường dẫn kết quả do người dùng chọn.

Bước cuối **đọc và ghi thêm toàn bộ N bản ghi**, tức thêm O(N/B) block I/Os. Vì thế:

\[
\boxed{\text{I/O bản demo}=O\left(\frac NB(2+P)\right)}
\]

tính cả generation, các lượt merge và final copy; đây vẫn là **cùng bậc tiệm cận** so với phương án viết thẳng lượt merge cuối vào output, nhưng khác số lượt đọc/ghi thực tế.

Đừng bỏ qua chi phí final copy khi lập kế hoạch cho một tệp hàng trăm GB.

## 11. Phân tích CPU riêng với I/O

**Tạo run:** có R₀ lần gọi sort trong RAM, mỗi run dài tối đa M. Tổng chi phí so sánh thường là:

\[
O(N\log M).
\]

**Một lượt trộn:** mọi bản ghi đi qua heap, mỗi thao tác O(log F), nên:

\[
O(N\log F)
\]

cho một lượt đầy đủ.

**P lượt merge:**

\[
\boxed{O(N\log M+PN\log F)}
\]

phép xử lý/so sánh ở mức mô hình đơn giản.

Nếu F là hằng số và P tăng, thời gian CPU vẫn theo số lượt merge. Nếu tăng F, heap mỗi thao tác đắt hơn nhưng số lượt merge có thể giảm. Bài toán tuning phải cân bằng giữa **số pass**, **số file đang mở**, **buffer** và hiệu quả I/O thực tế.

### Không đồng nhất CPU và I/O complexity

Có thể gặp hai thuật toán đều mất O(N log N) phép so sánh nhưng số lần đọc/ghi đĩa rất khác nhau. Khi dữ liệu lớn hơn RAM nhiều lần, khác biệt I/O thường quyết định hiệu năng.

Mô hình N–M–B tập trung vào **block transfer**, không đưa ra một cam kết thời gian chạy tính bằng giây trên mọi loại SSD, HDD hay cloud storage.

## 12. Bất biến giai đoạn tạo run

Sau khi tạo xong một run chứa m bản ghi:

1. Run đã được sắp xếp không giảm.
2. Run chứa **đúng m bản ghi** đã đọc ở phần input tương ứng, không tự thêm hoặc bỏ.
3. Trong toàn bộ các run, mỗi bản ghi input được ghi ra **đúng một lần**.

**Lý do:**

- Mảng chunk vừa đọc được đưa vào `Arrays.sort`, nên thứ tự của các giá trị trong chunk trở thành không giảm.
- Sắp xếp trong RAM là **một phép hoán vị**, không thay đổi số lượng hay giá trị của các phần tử.
- Các chunk lấy liên tiếp, không chồng lấn, và số bản ghi mỗi chunk được theo dõi rõ ràng, kể cả chunk cuối không đủ M.

Vì vậy hợp tất cả run là **cùng multiset** với tệp đầu vào.

Chỉ “đã sort từng run” chưa đủ để có **tệp toàn cục** sắp xếp; pha merge phải bảo toàn bất biến ấy khi hợp các run.

## 13. Bất biến trộn k-way và chứng minh đúng

Giả sử mỗi run đầu vào đã sắp xếp không giảm.

Bất biến của vòng lặp trộn:

- Heap chứa đúng **bản ghi đầu chưa xuất** của mỗi run còn bản ghi.
- Các bản ghi đã xuất ra output tạo thành một **dãy không giảm**.
- Mỗi bản ghi đã đọc được ghi ra đúng một lần; các bản ghi chưa ghi vẫn nằm ở heap hoặc phía sau trong run tương ứng.

**Bước cơ sở:** chưa xuất bản ghi nào, nên output rỗng mặc nhiên đã sắp xếp. Heap được khởi tạo bằng đầu của mỗi run không rỗng.

**Bước lặp:** đặt h là phần tử nhỏ nhất trong heap. Vì mỗi run đã sort nên phần tử đầu của run đó không lớn hơn bất kỳ phần tử chưa xuất nào trong chính run; và h là nhỏ nhất trong các đầu run. Do đó h là phần tử nhỏ nhất **trong toàn bộ dữ liệu chưa xuất**. Ghi h vào output giữ thứ tự không giảm. Sau đó nạp đầu mới của đúng run vừa lấy, khôi phục bất biến heap.

**Kết thúc:** khi heap rỗng, không run nào còn bản ghi. Mỗi bản ghi đã đi qua đúng một lượt heap hoặc được đọc/ghi tương đương, nên output có **đúng multiset** đầu vào, đã sắp xếp không giảm.

Theo quy nạp, mọi run sinh ra từ một lượt merge cũng đã sắp xếp và giữ đúng multiset của các run nguồn. Sau đủ P lượt còn một run, đó là **tệp sắp xếp toàn cục chính xác**.

### Hai tiêu chí kiểm tra độc lập

Một kết quả sorting đúng cần:

1. **Sortedness:** mọi cặp bản ghi kề nhau \(b[i]\le b[i+1]\).
2. **Permutation/multiset:** mỗi giá trị xuất hiện **đúng số lần như trong input**, không thiếu hay trùng.

Chỉ kiểm sortedness là không đủ: tệp gồm toàn số 0 có thể “đã sort” nhưng sai dữ liệu. Chỉ kiểm tổng số bản ghi hoặc tổng giá trị cũng không đủ: hai multiset khác nhau có thể có cùng số phần tử và tổng.

Trong test nhỏ, `Arrays.sort` tạo oracle có thể so sánh **từng phần tử**; điều này đồng thời kiểm thứ tự và multiset.

## 14. Bản ghi trùng lặp và tính ổn định

### Dữ liệu chỉ có số nguyên long

Nếu hai bản ghi cùng giá trị 7, ta vẫn phải ghi ra **hai lần** số 7. Priority queue không được dùng `Set` hoặc cấu trúc bỏ trùng.

Trong mã Java, heap lưu:

~~~text
(value, runIndex)
~~~

và so sánh `value` trước, sau đó `runIndex` để có lựa chọn xác định khi hai đầu run bằng nhau.

Với **chỉ một số long** trên mỗi bản ghi, tính ổn định (*stability*) không quan sát được: hai bản ghi bằng nhau không mang payload để phân biệt.

### Nếu mỗi bản ghi có key và payload

Ví dụ:

~~~text
(key=7, event="A")
(key=7, event="B")
~~~

Một phép sắp xếp **ổn định** phải giữ A trước B vì cùng key và A xuất hiện trước trong input.

Muốn bảo đảm ổn định qua nhiều run và nhiều lượt merge, có hai hướng:

1. Gắn thêm **vị trí toàn cục ban đầu** `originalOrdinal` và so sánh theo khóa ghép `(key, originalOrdinal)`.
2. Dùng local sort ổn định, giữ các run theo thứ tự nguồn và bảo toàn quy tắc chọn run trước khi bằng key trên mọi lượt merge.

Hướng gắn ordinal thường dễ lập luận, nhưng tăng kích thước bản ghi và chi phí I/O. Mã Java trong bài chỉ sắp **long đơn**, không nhận payload và không tự quảng cáo là ví dụ stable sorting cho các record có key trùng.

## 15. Định dạng tệp: nhị phân cố định hay văn bản?

External merge sort có thể xử lý CSV, JSON Lines, TSV, bản ghi binary, hoặc các page của database. Nhưng lựa chọn định dạng ảnh hưởng đến parsing, bộ nhớ và chi phí I/O.

### Ví dụ dạng văn bản

~~~text
12
-3
7
7
0
~~~

Ưu điểm: con người đọc được, dễ tạo thủ công.

Nhược điểm: độ dài dòng biến đổi; phải parse số; nếu một dòng rất dài hoặc malformed, `BufferedReader.readLine()` có thể cấp phát một chuỗi lớn trước khi phát hiện lỗi nếu không có giới hạn độ dài dòng.

### Ví dụ dạng nhị phân long 8 byte

Mã Java sử dụng chính xác **8 byte cho mỗi bản ghi** dưới dạng `DataOutputStream.writeLong` / `DataInputStream.readLong`, big-endian theo Java Data Streams.

Ưu điểm:

- Mỗi bản ghi có độ dài cố định.
- Không cần parse chuỗi số.
- Có thể tính số bản ghi bằng `Files.size(file)/8`.
- Đọc từng bản ghi bằng bộ đệm, không đòi giữ toàn bộ file.
- Hỗ trợ `Long.MIN_VALUE`, `Long.MAX_VALUE`, giá trị âm và bản ghi lặp.

Một tệp hợp lệ phải có số byte chia hết cho 8. Nếu dư 1..7 byte, dữ liệu có thể bị cắt giữa bản ghi; chương trình **báo lỗi** thay vì lờ đi bản ghi cuối.

### Cảnh báo định dạng

Một tệp chứa chuỗi UTF-8 số nguyên **không phải** tệp nhị phân 8 byte. Không được đưa trực tiếp CSV hay file text vào hàm Java của bài rồi mong nhận số đã sort; cần một pha parser/chuyển đổi định dạng có kiểm chứng.

Trong ví dụ chạy tự động, hàm main tạo tệp binary mẫu bằng `writeLong` trước khi gọi external sort.

## 16. Chương trình Java 17+ độc lập

Lưu chương trình dưới tên **ExternalMergeSortDemo.java**. Nó dùng các thành phần thư viện chuẩn:

- `Arrays.sort(long[])` để tạo run trong RAM.
- `BufferedInputStream`, `BufferedOutputStream` và `DataInputStream`/`DataOutputStream` để đọc/ghi tuần tự có đệm.
- `PriorityQueue` làm min-heap chỉ giữ một đầu mỗi run.
- `Path` / `Files` để tạo, trộn, xóa các file tạm.
- `Run(path,count)` ghi rõ mỗi run chứa bao nhiêu bản ghi.
- `SortStats(records,initialRuns,mergePasses,mergeGroups)` để báo số lượt và run.

**Hợp đồng API:**

- `input`: tệp binary hợp lệ gồm N bản ghi signed long 8 byte, không bị tiến trình khác sửa trong lúc sắp.
- `output`: đường dẫn kết quả **khác** input; thư mục cha của output đã tồn tại. Nếu output có sẵn và không phải input, mã có thể thay thế output.
- `chunkRecords>=1` là số bản ghi RAM tối đa trong một lần tạo run.
- `fanIn>=2` là số run tối đa trộn trong một nhóm.
- Tệp tạm được đặt trong thư mục tạm riêng của hệ điều hành và dọn sau thành công hoặc khi có ngoại lệ thông thường.
- Hỗ trợ input rỗng; output khi đó cũng là tệp rỗng.
- **Không bảo đảm output atomic** nếu I/O giữa chừng lỗi; không thiết kế resume hay checkpoint trong bản giáo dục.

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.Random;

public class ExternalMergeSortDemo {
    private static final int BUFFER_BYTES = 8 * 1024;

    record Run(Path path, long count) {}

    record Head(long value, int runIndex) {}

    record SortStats(
        long records, int initialRuns,
        int mergePasses, long mergeGroups
    ) {}

    // A group of open inputs that are all closed even if one
    // reader or the output writer fails.
    static final class Readers implements AutoCloseable {
        private final List<DataInputStream> opened =
            new ArrayList<>();

        DataInputStream open(Path path) throws IOException {
            DataInputStream stream = new DataInputStream(
                new BufferedInputStream(
                    Files.newInputStream(path), BUFFER_BYTES
                )
            );
            opened.add(stream);
            return stream;
        }

        @Override
        public void close() throws IOException {
            IOException problem = null;
            for (DataInputStream stream : opened) {
                try {
                    stream.close();
                } catch (IOException e) {
                    if (problem == null) {
                        problem = e;
                    } else {
                        problem.addSuppressed(e);
                    }
                }
            }
            if (problem != null) {
                throw problem;
            }
        }
    }

    static DataOutputStream openOutput(Path path)
            throws IOException {
        return new DataOutputStream(
            new BufferedOutputStream(
                Files.newOutputStream(path), BUFFER_BYTES
            )
        );
    }

    // Phase 1: load at most chunkRecords longs into one array.
    static List<Run> generateRuns(
        Path input, long recordCount, int chunkRecords,
        Path tempDir, List<Path> allTempFiles
    ) throws IOException {
        List<Run> runs = new ArrayList<>();

        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(
                    Files.newInputStream(input), BUFFER_BYTES
                ))) {

            long remaining = recordCount;
            while (remaining > 0L) {
                int take = (int) Math.min(
                    remaining, (long) chunkRecords
                );
                long[] chunk = new long[take];
                for (int i = 0; i < take; i++) {
                    chunk[i] = in.readLong();
                }

                Arrays.sort(chunk);

                Path runPath = Files.createTempFile(
                    tempDir, "run-", ".bin"
                );
                allTempFiles.add(runPath);

                try (DataOutputStream out =
                        openOutput(runPath)) {
                    for (long value : chunk) {
                        out.writeLong(value);
                    }
                }

                runs.add(new Run(runPath, take));
                remaining -= take;
            }
        }
        return runs;
    }

    // Merge between 2 and fanIn sorted runs.
    // Only one current head per input run is in the heap.
    static Run mergeGroup(List<Run> group, Path target)
            throws IOException {
        int f = group.size();
        long[] remaining = new long[f];
        DataInputStream[] inputStreams =
            new DataInputStream[f];

        long totalRecords = 0L;
        for (Run run : group) {
            totalRecords = Math.addExact(
                totalRecords, run.count()
            );
        }

        PriorityQueue<Head> heap = new PriorityQueue<>(
            Comparator.comparingLong(Head::value)
                .thenComparingInt(Head::runIndex)
        );

        try (Readers readers = new Readers();
                DataOutputStream out = openOutput(target)) {

            for (int i = 0; i < f; i++) {
                inputStreams[i] = readers.open(group.get(i).path());
                remaining[i] = group.get(i).count();

                if (remaining[i] > 0L) {
                    long first = inputStreams[i].readLong();
                    remaining[i]--;
                    heap.add(new Head(first, i));
                }
            }

            while (!heap.isEmpty()) {
                Head head = heap.remove();
                out.writeLong(head.value());

                int source = head.runIndex();
                if (remaining[source] > 0L) {
                    long next = inputStreams[source].readLong();
                    remaining[source]--;
                    heap.add(new Head(next, source));
                }
            }
        }
        return new Run(target, totalRecords);
    }

    // Called when temporary runs are no longer needed.
    static void cleanTemp(List<Path> paths, Path dir)
            throws IOException {
        IOException problem = null;

        for (int i = paths.size() - 1; i >= 0; i--) {
            try {
                Files.deleteIfExists(paths.get(i));
            } catch (IOException e) {
                if (problem == null) {
                    problem = e;
                } else {
                    problem.addSuppressed(e);
                }
            }
        }

        try {
            Files.deleteIfExists(dir);
        } catch (IOException e) {
            if (problem == null) {
                problem = e;
            } else {
                problem.addSuppressed(e);
            }
        }

        if (problem != null) {
            throw problem;
        }
    }

    // External merge sort for a binary long file (8 bytes/record).
    static SortStats externalSort(
        Path input, Path output,
        int chunkRecords, int fanIn
    ) throws IOException {
        if (chunkRecords < 1) {
            throw new IllegalArgumentException(
                "chunkRecords must be positive"
            );
        }
        if (fanIn < 2) {
            throw new IllegalArgumentException(
                "fanIn must be at least 2"
            );
        }
        if (!Files.isRegularFile(input)) {
            throw new IOException(
                "input must be an existing regular file"
            );
        }

        Path absoluteInput = input.toAbsolutePath().normalize();
        Path absoluteOutput = output.toAbsolutePath().normalize();
        if (absoluteInput.equals(absoluteOutput)
                || (Files.exists(output)
                    && Files.isSameFile(input, output))) {
            throw new IllegalArgumentException(
                "input and output must be different files"
            );
        }

        long inputBytes = Files.size(input);
        if (inputBytes % Long.BYTES != 0L) {
            throw new IOException(
                "binary file length must be a multiple of 8"
            );
        }

        long records = inputBytes / Long.BYTES;
        Path scratch = Files.createTempDirectory(
            "external-merge-"
        );
        List<Path> allTempFiles = new ArrayList<>();

        try {
            List<Run> runs = generateRuns(
                input, records, chunkRecords,
                scratch, allTempFiles
            );
            int initialRuns = runs.size();
            int passes = 0;
            long mergedGroups = 0L;

            while (runs.size() > 1) {
                List<Run> nextRuns = new ArrayList<>();

                for (int first = 0; first < runs.size();) {
                    // Difference first..end <= fanIn.
                    // This formulation avoids first+fanIn overflow.
                    int end = first + Math.min(
                        fanIn, runs.size() - first
                    );
                    List<Run> group = runs.subList(first, end);

                    if (group.size() == 1) {
                        // Already sorted: carry without rereading.
                        nextRuns.add(group.get(0));
                    } else {
                        Path mergedFile = Files.createTempFile(
                            scratch, "merged-", ".bin"
                        );
                        allTempFiles.add(mergedFile);

                        Run merged = mergeGroup(
                            group, mergedFile
                        );
                        nextRuns.add(merged);
                        mergedGroups++;

                        // Their data is already in mergedFile.
                        for (Run old : group) {
                            Files.deleteIfExists(old.path());
                        }
                    }

                    first = end;
                }

                runs = nextRuns;
                passes++;
            }

            if (runs.isEmpty()) {
                // A valid empty input produces an empty output.
                Files.write(output, new byte[0]);
            } else {
                // Simple final copy adds one sequential I/O pass.
                Files.copy(
                    runs.get(0).path(), output,
                    StandardCopyOption.REPLACE_EXISTING
                );
            }

            return new SortStats(
                records, initialRuns, passes, mergedGroups
            );
        } finally {
            // Successful and failed operations both clean scratch.
            // A cleanup exception can replace the original exception.
            cleanTemp(allTempFiles, scratch);
        }
    }

    // DEMO/TEST ONLY: materializes a small array to make an oracle.
    // Never use this helper to load a truly huge output file.
    static long[] readSmallForDemo(Path file)
            throws IOException {
        long bytes = Files.size(file);
        if (bytes % Long.BYTES != 0L
                || bytes / Long.BYTES > 2000L) {
            throw new IOException(
                "demo reader only accepts <=2000 long records"
            );
        }

        long[] result = new long[(int) (bytes / Long.BYTES)];
        try (DataInputStream in = new DataInputStream(
                new BufferedInputStream(
                    Files.newInputStream(file), BUFFER_BYTES
                ))) {
            for (int i = 0; i < result.length; i++) {
                result[i] = in.readLong();
            }
        }
        return result;
    }

    // DEMO/TEST ONLY: create small, known binary inputs.
    static void writeSmallForDemo(Path file, long[] values)
            throws IOException {
        try (DataOutputStream out = openOutput(file)) {
            for (long value : values) {
                out.writeLong(value);
            }
        }
    }

    // Compare actual external sort to independent in-memory
    // Arrays.sort, on SMALL inputs only.
    static void verifyRandomCases() throws IOException {
        Random random = new Random(513L);
        Path dir = Files.createTempDirectory("merge-test-");
        Path input = dir.resolve("input.bin");
        Path output = dir.resolve("output.bin");

        try {
            for (int test = 0; test < 200; test++) {
                int n = random.nextInt(120);
                long[] values = new long[n];

                for (int i = 0; i < n; i++) {
                    int type = random.nextInt(8);
                    if (type == 0) {
                        values[i] = Long.MIN_VALUE;
                    } else if (type == 1) {
                        values[i] = Long.MAX_VALUE;
                    } else {
                        values[i] = random.nextInt(301) - 150;
                    }
                }

                int chunk = 1 + random.nextInt(17);
                int fanIn = 2 + random.nextInt(6);
                writeSmallForDemo(input, values);

                SortStats stats = externalSort(
                    input, output, chunk, fanIn
                );
                long[] expected = values.clone();
                Arrays.sort(expected);
                long[] actual = readSmallForDemo(output);

                if (!Arrays.equals(actual, expected)) {
                    throw new AssertionError(
                        "sorted output differs on test " + test
                    );
                }
                int expectedRuns =
                    (n + chunk - 1) / chunk;
                if (stats.records() != n
                        || stats.initialRuns() != expectedRuns
                        || Files.size(output)
                            != (long) n * Long.BYTES) {
                    throw new AssertionError(
                        "record/run count differs on test " + test
                    );
                }

                int expectedPasses = 0;
                int countRuns = expectedRuns;
                while (countRuns > 1) {
                    countRuns = (countRuns + fanIn - 1)
                        / fanIn;
                    expectedPasses++;
                }
                if (stats.mergePasses() != expectedPasses) {
                    throw new AssertionError(
                        "merge passes differ on test " + test
                    );
                }
            }
            System.out.println(
                "Random file-sorting checks: PASS (200 cases)"
            );
        } finally {
            Files.deleteIfExists(input);
            Files.deleteIfExists(output);
            Files.deleteIfExists(dir);
        }
    }

    public static void main(String[] args) throws IOException {
        long[] sample = {
            12, -3, 7, 7, 0, 18, -10, 4, 4,
            99, 1, -1, 5, 3, 8, -10, 2
        };
        Path dir = Files.createTempDirectory(
            "merge-demo-"
        );
        Path input = dir.resolve("input.bin");
        Path output = dir.resolve("sorted.bin");
        Path emptyInput = dir.resolve("empty.bin");
        Path emptyOutput = dir.resolve("empty-sorted.bin");
        Path singleInput = dir.resolve("single.bin");
        Path singleOutput = dir.resolve("single-sorted.bin");
        Path truncated = dir.resolve("truncated.bin");

        try {
            writeSmallForDemo(input, sample);

            SortStats stats = externalSort(
                input, output, 4, 3
            );
            long[] sorted = readSmallForDemo(output);
            long[] reference = sample.clone();
            Arrays.sort(reference);

            System.out.println(
                "Source: " + Arrays.toString(sample)
            );
            System.out.println(
                "Sorted: " + Arrays.toString(sorted)
            );
            System.out.println("Records: " + stats.records());
            System.out.println(
                "Initial runs: " + stats.initialRuns()
            );
            System.out.println(
                "Merge passes: " + stats.mergePasses()
            );
            System.out.println(
                "Merge groups: " + stats.mergeGroups()
            );
            System.out.println(
                "Matches Arrays.sort: "
                + Arrays.equals(sorted, reference)
            );

            writeSmallForDemo(emptyInput, new long[0]);
            SortStats emptyStats = externalSort(
                emptyInput, emptyOutput, 4, 3
            );
            System.out.println(
                "Empty input: records=" + emptyStats.records()
                + ", runs=" + emptyStats.initialRuns()
                + ", passes=" + emptyStats.mergePasses()
                + ", bytes=" + Files.size(emptyOutput)
            );

            writeSmallForDemo(
                singleInput, new long[] {11, -2, 5}
            );
            SortStats singleStats = externalSort(
                singleInput, singleOutput, 4, 3
            );
            System.out.println(
                "Single run: records=" + singleStats.records()
                + ", runs=" + singleStats.initialRuns()
                + ", passes=" + singleStats.mergePasses()
                + ", result="
                + Arrays.toString(readSmallForDemo(singleOutput))
            );

            try {
                externalSort(
                    input, dir.resolve("rejected.bin"), 4, 1
                );
            } catch (IllegalArgumentException e) {
                System.out.println(
                    "Invalid fan-in rejected: " + e.getMessage()
                );
            }

            Files.write(truncated, new byte[] {1, 2, 3});
            try {
                externalSort(
                    truncated, dir.resolve("broken-output.bin"),
                    4, 3
                );
            } catch (IOException e) {
                System.out.println(
                    "Truncated record rejected: " + e.getMessage()
                );
            }
        } finally {
            Files.deleteIfExists(input);
            Files.deleteIfExists(output);
            Files.deleteIfExists(emptyInput);
            Files.deleteIfExists(emptyOutput);
            Files.deleteIfExists(singleInput);
            Files.deleteIfExists(singleOutput);
            Files.deleteIfExists(truncated);
            Files.deleteIfExists(dir);
        }

        verifyRandomCases();
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 ExternalMergeSortDemo.java
java ExternalMergeSortDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
Source: [12, -3, 7, 7, 0, 18, -10, 4, 4, 99, 1, -1, 5, 3, 8, -10, 2]
Sorted: [-10, -10, -3, -1, 0, 1, 2, 3, 4, 4, 5, 7, 7, 8, 12, 18, 99]
Records: 17
Initial runs: 5
Merge passes: 2
Merge groups: 3
Matches Arrays.sort: true
Empty input: records=0, runs=0, passes=0, bytes=0
Single run: records=3, runs=1, passes=0, result=[-2, 5, 11]
Invalid fan-in rejected: fanIn must be at least 2
Truncated record rejected: binary file length must be a multiple of 8
Random file-sorting checks: PASS (200 cases)
~~~

**Phân biệt tệp mẫu và tệp ngoài bộ nhớ thật:** hàm `readSmallForDemo` cố ý cấp phát một mảng để đối chiếu kết quả **trên tối đa 2.000 bản ghi**. Hàm này **không thuộc đường đi sắp xếp chính** và không được sử dụng để kiểm một tệp nhiều GB. Trong ứng dụng thật, để xác minh output lớn, cần dùng các lượt **streaming** kiểm từng cặp kề nhau và các cơ chế kiểm multiset/checksum đáng tin theo yêu cầu.

## 17. Giải thích chi tiết thiết kế Java

### A. Bản ghi long cố định 8 byte

`DataOutputStream.writeLong` và `DataInputStream.readLong` dùng cùng định dạng Java Data Streams. Điều này tránh phụ thuộc parsing văn bản và giúp đếm bản ghi bằng kích thước tệp.

Nếu nguồn có 3 byte thì:

\[
3\bmod8\ne0.
\]

Chương trình ném IOException với thông báo về kích thước thay vì đọc “nửa bản ghi”. Trong tình huống tệp bị thay đổi sau khi kiểm kích thước, một `readLong` vẫn có thể ném EOFException; đây là lỗi I/O hợp lệ cần chuyển cho caller.

### B. Bản ghi Run gồm đường dẫn và số phần tử

`Run(Path path,long count)` giúp giới hạn số `readLong` của từng run, kể cả khi run rỗng hoặc ở đoạn cuối.

Đối với run ban đầu, count là số bản ghi đã đọc từ chunk; đối với run sau merge, count bằng tổng count của các run nguồn.

Không nên dựa vào sentinel `Long.MAX_VALUE` để đánh dấu “đã hết run”, vì `Long.MAX_VALUE` có thể là **giá trị đầu vào hợp lệ**.

### C. Heap giữ một đầu trên mỗi run

`Head(value,runIndex)` chỉ ra bản ghi hiện tại và nguồn gốc. Khi heap lấy ra một Head, ta nạp **đúng một giá trị tiếp theo từ runIndex đó**, nếu còn.

Nếu nạp tất cả bản ghi của các run vào heap, sẽ trở lại tình trạng bộ nhớ O(N), trái mục tiêu external sort.

### D. So sánh số signed long đúng cách

`Comparator.comparingLong(Head::value)` dùng so sánh giá trị long đúng.

Không nên viết:

~~~java
(a, b) -> (int) (a.value() - b.value())
~~~

vì hiệu hai `long` có thể tràn và ép sang `int` còn có thể bỏ mất bit quan trọng. Comparator sai sẽ phá quy tắc min-heap, đặc biệt với `Long.MIN_VALUE` và `Long.MAX_VALUE`.

### E. Run đơn lẻ được chuyển tiếp

Nếu ở một lượt chỉ còn một run trong nhóm cuối, nó đã sort và được đưa thẳng sang `nextRuns`. Không đọc rồi ghi một bản sao vô ích.

Đây là một tối ưu I/O nhỏ nhưng có ý nghĩa khi N lớn. Vòng lặp vẫn giảm số run trong mỗi lượt vì fanIn≥2 và còn ít nhất hai run lúc bắt đầu một lượt.

### F. Xóa run nguồn sau khi merge

Sau khi `mergeGroup` đã ghi và đóng tệp run mới thành công, các run cũ trong nhóm được xóa. Nếu không xóa, dung lượng tệp tạm có thể tăng qua nhiều lượt.

Tất cả đường dẫn được lưu trong danh sách `allTempFiles` để `finally` thử xóa tiếp khi thành công hoặc lỗi. Việc gọi `deleteIfExists` trên một run đã xóa ở lượt trước là hợp lệ.

### G. Bảo vệ input/output khác nhau

Cần tránh sort trực tiếp từ một tệp đồng thời ghi đè cùng tệp ấy, vì ghi output có thể phá dữ liệu đầu vào chưa đọc.

Mã so cả đường dẫn chuẩn hóa và sử dụng `Files.isSameFile` khi output đã tồn tại để hạn chế trường hợp hai đường dẫn trỏ cùng tệp. Trong ứng dụng production, còn cần quy định rõ symlink, hard link, quyền ghi và tính nguyên tử khi xuất.

### H. Số file mở đồng thời

Ở pha merge nhóm f run:

- f `DataInputStream`.
- Một `DataOutputStream`.

Tổng tối đa khoảng f+1 stream của nhóm cộng các tài nguyên nội bộ. Chương trình chỉ mở **một nhóm** tại một thời điểm, không mở toàn bộ run ban đầu.

### I. Bước copy cuối

Khi còn một run, `Files.copy` sang output. Cách này dễ hiểu, nhưng thêm **một lượt truyền N bản ghi** và không có cơ chế xuất atomic trong trường hợp lỗi. Trong một sản phẩm thật, có thể trực tiếp ghi run cuối ra tệp tạm bên cạnh output rồi thực hiện **rename/atomic move** khi filesystem hỗ trợ, hoặc thiết kế commit hai giai đoạn.

## 18. Kiểm thử bằng oracle độc lập

Chương trình tạo 200 bộ test có seed `513L`:

- n được chọn trong \([0,119]\).
- Giá trị được lấy ngẫu nhiên từ khoảng nhỏ có số âm, phần tử lặp và đôi khi đúng `Long.MIN_VALUE` hoặc `Long.MAX_VALUE`.
- `chunkRecords` từ 1 tới 17.
- `fanIn` từ 2 tới 7.
- Ghi mỗi test thành tệp binary nhỏ.
- Chạy **chính hàm externalSort** (thật sự tạo run và merge qua tệp).
- Đọc output nhỏ và so với `Arrays.sort(values.clone())`.
- Kiểm tổng bản ghi, số run đầu, số lượt trộn và số byte output.

Oracle `Arrays.sort` trên mảng nhỏ là cách giải **độc lập với cấu trúc k-way merge**. Nếu kết quả bằng từng phần tử, nó xác nhận cả thứ tự lẫn multiset.

### Vì sao có cả giá trị cực tiểu/cực đại của long?

Một comparator viết bằng phép trừ có thể tràn khi so sánh hai số xa nhau. Các giá trị `Long.MIN_VALUE` và `Long.MAX_VALUE` làm lộ các lỗi này nhanh hơn chỉ dùng số 1..100.

### Vì sao có chunkRecords=1?

Khi chunk chỉ có một phần tử, số run ban đầu bằng n, làm xuất hiện nhiều lượt merge hơn. Đây là trường hợp kiểm tốt cho:

- Tính toán R₀ và P.
- Nhóm cuối có một run.
- Trộn run rất ngắn.
- Dọn tệp tạm qua nhiều lượt.

### Vì sao có fanIn=2?

Fan-in nhỏ nhất hợp lệ tạo nhiều lượt merge nhất trong cùng input, giúp kiểm logic **multi-pass**. Nếu code vô tình chỉ merge **một lượt**, test kiểu này thường phát hiện lỗi.

### Vì sao không chỉ kiểm tệp đã sort?

Một output có thể đã không giảm nhưng bị mất bản ghi hoặc nhân đôi bản ghi. Việc so với `Arrays.sort` xác nhận **từng vị trí sau sort** đúng, không chỉ kiểm có `a[i]\le a[i+1]`.

### Bài test bổ sung nên có ở hệ thống thật

- Tệp hàng chục/hàng trăm GB thực sự vượt RAM.
- Giới hạn file descriptors thấp và fan-in lớn.
- Disk gần đầy, lỗi đọc/ghi, mất kết nối tới storage.
- Tệp nguồn bị thay đổi khi đang sort.
- Cắt ngắn một tệp run ở giữa merge.
- Output đã tồn tại và bị khóa bởi tiến trình khác.
- Tệp có nhiều khóa trùng, hoặc toàn một giá trị.
- Bộ đệm tối thiểu, tốc độ đĩa thấp, số run rất lớn.
- Gián đoạn giữa các lượt để thử khả năng restart/cleanup.
- Quyền truy cập, symlink và output/input trùng đường dẫn.
- Kiểm đối chiếu multiset trên dữ liệu lớn, với hash/checksum và cách xác minh đủ mạnh cho mục đích sử dụng.

**Lưu ý:** 200 test nhỏ kiểm logic và I/O cục bộ, **không chứng minh** hiệu năng hay độ tin cậy trên dữ liệu lớn nhất định. Phần chứng minh đúng tổng quát dựa trên bất biến run và merge.

## 19. Kiểm thử toàn bộ tổ hợp nhỏ theo mô hình thuật toán

Để hiểu rõ tính đúng của **quy tắc trộn**, còn có thể kiểm độc lập **mô hình toán học** của các run bằng cách liệt kê mọi chuỗi ngắn từ một bảng giá trị nhỏ.

Ví dụ lấy bảng giá trị:

\[
\{-2,-1,0,1,2\}
\]

và mọi độ dài n từ 0 đến 5, số dãy là:

\[
\sum_{n=0}^{5}5^n
=1+5+25+125+625+3125
=\boxed{3906}.
\]

Thử `chunkRecords` từ 1 đến 4 (4 lựa chọn) và fan-in từ 2 đến 4 (3 lựa chọn), sẽ có:

\[
3906\cdot4\cdot3=\boxed{46872}
\]

tổ hợp cần đối chiếu.

Trên từng tổ hợp:

1. Chia input thành các chunk theo đúng giới hạn.
2. Sort từng chunk.
3. Trộn theo nhóm fan-in, chuyển tiếp nhóm có một run.
4. Lặp tới khi còn một run.
5. So với `Arrays.sort` trên toàn input nhỏ.

Đây là cách **kiểm thử mô hình thuật toán** không cần tạo 46.872 nhóm tệp thật. Nó rất hữu ích để phát hiện sai về nhóm cuối, trùng lặp và số lượt merge, nhưng không thay thế bài kiểm Java có đường đi I/O thực và cũng không thay thế chứng minh bất biến.

## 20. Tối ưu hiệu năng đọc/ghi

### A. Đọc/ghi tuần tự theo khối

Ưu tiên `BufferedInputStream`/`BufferedOutputStream` hoặc cơ chế I/O theo page phù hợp. Trong mô hình lý tưởng, mỗi lần xử lý một khối B bản ghi giúp giảm số thao tác I/O so với yêu cầu 8 byte một lần.

### B. Chọn M vừa RAM

M càng lớn, số run đầu R₀ càng nhỏ, thường giảm số lượt merge. Nhưng M quá lớn có thể dẫn đến swapping, GC nặng hoặc OutOfMemoryError, khiến tổng thời gian tệ hơn.

Nên chọn M theo **phần RAM chắc chắn khả dụng** cho chunk, không phải tổng RAM của máy.

### C. Chọn F theo tổng buffer

Fan-in lớn làm giảm số pass nhưng tốn nhiều input buffer, heap và file descriptor. Nếu F quá lớn, mỗi buffer phải quá nhỏ hoặc hệ điều hành không đủ descriptor.

### D. Tách vùng tạm và vùng output

Nếu hệ thống có SSD tạm đủ nhanh và dung lượng, tệp run trung gian có thể được đặt trên ổ thích hợp. Nếu output nằm trên hệ lưu trữ khác, bước copy/commit cuối có chi phí riêng.

### E. Dùng file binary khi có thể

Bản ghi cố định có ưu thế về parsing và kích thước. Nhưng nếu các tệp đầu vào và đầu ra phải tương thích CSV/JSON hoặc một hệ format như Parquet, cần tính thêm bước chuyển mã, serialization và chi phí codec.

### F. Cân bằng CPU với băng thông I/O

Với mỗi lượt merge, heap dùng khoảng O(log F) thao tác cho mỗi bản ghi. Nếu storage rất nhanh và CPU trở thành giới hạn, có thể dùng cấu trúc trộn tối ưu hơn như **loser tree/tournament tree** hoặc tối ưu cách đọc buffer. Nhưng mọi lựa chọn phải được benchmark trên workload thật.

## 21. Replacement selection và các biến thể mở rộng

Khi tạo run ban đầu, cách đơn giản nhất là đọc M bản ghi rồi sort. Run có độ dài tối đa M.

Một kỹ thuật nâng cao là **replacement selection**:

- Duy trì một heap chứa các bản ghi đang chờ.
- Ghi phần tử nhỏ nhất thích hợp ra run hiện tại.
- Khi một bản ghi mới quá nhỏ để giữ thứ tự run hiện tại, đánh dấu nó thuộc run kế tiếp.
- Tiếp tục cho đến khi run hiện tại kết thúc.

Với phân phối đầu vào độc lập gần ngẫu nhiên và giả định phù hợp, chiều dài run trung bình có thể vào khoảng **2M**, giúp giảm R₀ và số lượt merge. Nhưng:

- Đây là **kỳ vọng trong một mô hình dữ liệu**, không phải bảo đảm mọi input.
- Với chuỗi đầu vào giảm dần, run có thể ngắn hơn kỳ vọng.
- Cài đặt phức tạp hơn sort từng chunk.

Bản Java dùng **fixed-size chunk sorting** để có ranh giới RAM, số run và bằng chứng đúng đơn giản.

### Balanced merge và polyphase merge

Có nhiều cách tổ chức các lượt trộn trên các băng/tệp/ổ khác nhau, chẳng hạn balanced multiway merge hoặc polyphase merge. Chúng quyết định cách **phân phối và tái sử dụng vùng lưu trữ run**. Trọng tâm của bài là tổ chức **nhóm fan-in F và trộn cho tới một run**, không triển khai lịch trình polyphase.

## 22. Vấn đề ổ đĩa tạm và khả năng thất bại

External sort cần không gian để chứa các run trung gian. Vì các run mang theo toàn bộ các bản ghi, không gian tạm có bậc:

\[
\boxed{O(N)\text{ bản ghi}}
\]

và trong thực tế có thể cần **một hoặc nhiều lần dung lượng input**, tùy cách tổ chức merge, việc giữ run cũ, run mới, output và chính sách checkpoint.

### Tình huống disk full

Nếu ổ tạm hết chỗ khi tạo một run, việc mở/ghi tệp có thể ném IOException.

Nếu run merge đang ghi dở mà disk full, tệp output tạm có thể chứa dữ liệu chưa hoàn chỉnh; không được dùng nó như một run đã sắp xếp đủ bản ghi.

Trong mã demo, ngoại lệ sẽ làm dừng thuật toán và `finally` cố xóa tệp tạm. Output cuối chỉ được viết sau khi có một run hợp lệ, nhưng việc `Files.copy` thất bại có thể để lại output không đầy đủ hoặc cũ tùy hệ điều hành/triển khai.

### Kiến trúc production có thể cần

- Viết output vào **tệp staging** rồi commit bằng rename khi phù hợp.
- Ghi **manifest** cho run: path, số bản ghi, kích thước, checksum, mức merge.
- Kiểm checksum hoặc count trước khi chuyển run thành trạng thái hợp lệ.
- Ghi checkpoint sau những nhóm merge đã hoàn thành.
- Khôi phục sau khi dừng đột ngột mà không trộn trùng hoặc mất run.
- Quản lý quota vùng tạm và tài nguyên file descriptors.
- Kiểm soát xóa tệp tạm không còn tham chiếu.

Mã Java trong bài **không tự cung cấp transaction, resume hay crash recovery**; đây là những mối quan tâm triển khai nâng cao.

## 23. Những tình huống biên cần xét

| Tình huống | Hành vi đúng |
|---|---|
| N=0 | Không có run; xuất tệp rỗng |
| N=1 | Một run; không cần merge |
| N≤M | Một run đã sort, P=0 |
| N=M+1 | Hai run, cần ít nhất một lượt trộn nếu F≥2 |
| N không chia hết M | Run cuối chỉ chứa số bản ghi còn lại |
| F=1 | Không giảm số run; phải từ chối |
| F≥R₀ | Có thể trộn thành một run sau một lượt nếu R₀>1 |
| Tất cả số bằng nhau | Output có đủ N bản ghi bằng nhau |
| Có nhiều số âm | Sắp xếp theo signed long, không coi âm là sentinel |
| Có Long.MIN_VALUE | Vẫn là giá trị hợp lệ và nhỏ nhất của kiểu |
| Có Long.MAX_VALUE | Vẫn là giá trị hợp lệ và lớn nhất của kiểu |
| Tệp có số byte không chia hết 8 | Báo lỗi dữ liệu cắt giữa bản ghi |
| Đầu vào đang bị sửa trong lúc sort | Không thuộc hợp đồng; có thể lỗi hoặc kết quả không nhất quán |
| Output trùng input | Phải từ chối hoặc có cơ chế staging an toàn |
| M quá lớn so RAM | Có thể hết bộ nhớ khi tạo chunk |
| F quá lớn | Có thể hết buffer hoặc file descriptors |
| Lỗi ghi run | Không dùng run chưa hoàn chỉnh làm nguồn hợp lệ |
| Một nhóm chỉ có 1 run | Chuyển tiếp không cần copy |
| Một nhóm cuối có ít hơn F run | Trộn đúng số run còn lại |
| N rất lớn | Chọn số đếm `long`, không ép toàn bộ N về int |
| Dữ liệu chứa payload | Cần comparator/key format, cân nhắc stable sorting |
| Tệp text thay vì binary | Phải parse/chuyển đổi, không đọc trực tiếp bằng `readLong` |

### Đầu vào đã sắp xếp tăng dần thì sao?

Fixed-size chunk sorting vẫn tạo R₀ run, rồi trộn chúng. Thuật toán vẫn đúng nhưng có thể thực hiện nhiều I/O không cần thiết so với một thuật toán phát hiện dữ liệu đã sort toàn cục.

Trong một hệ thống tối ưu cao, có thể phát hiện các run tự nhiên hoặc dùng replacement selection. Đây là cơ hội tối ưu, **không phải lỗi** của external merge sort cơ bản.

### Đầu vào đảo ngược thì sao?

Mỗi chunk được sắp xếp lại, run vẫn đúng. K-way merge không dựa vào input gốc tăng dần. Bài vẫn chạy đúng, chỉ có việc tạo run không tận dụng được thứ tự tự nhiên.

## 24. So sánh với những cách sắp xếp khác

| Cách tiếp cận | RAM yêu cầu | I/O/dữ liệu lớn | Phù hợp |
|---|---|---|---|
| `Arrays.sort` toàn mảng | O(N) | Phải nạp toàn bộ input | N vừa RAM |
| Merge sort nội bộ | O(N) bộ nhớ phụ trong bản chuẩn | Không tự xử lý tệp lớn | Dữ liệu đã ở RAM |
| External merge sort | RAM hữu hạn theo chunk và fan-in | Quét theo run, số lượt logarithmic theo R₀ | N vượt RAM |
| Heap sort từng bản ghi | O(N) nếu giữ toàn bộ heap | Không tự giải quyết giới hạn RAM | Dữ liệu ở RAM |
| Trộn hai tệp đã sort | O(B) buffers | Một lượt tuần tự | Chỉ hai run |
| K-way merge đã có F run | O(FB) buffers | Một lượt tuần tự | Dữ liệu đã chia thành run |
| External radix sort | Phụ thuộc bảng chữ cái, số pass và đệm | Có thể hiệu quả cho khóa độ dài cố định | Kiểu khóa/định dạng phù hợp |
| Distributed sort | Bộ nhớ cục bộ từng máy, mạng | Thêm chi phí shuffle/network | Dữ liệu phân tán, quy mô rất lớn |

External merge sort là phương án tổng quát có lợi thế khi so sánh được khóa của mọi record và có thể đọc/ghi run tuần tự. Với khóa nguyên cố định, external radix sort có thể cạnh tranh, nhưng có những giả định và chi phí truyền dữ liệu khác.

### Liên hệ database ORDER BY

Hệ quản trị cơ sở dữ liệu thường cần sort cho `ORDER BY`, `GROUP BY`, merge join hoặc xây chỉ mục. Khi vùng memory grant không đủ, một trình xử lý có thể **spill ra disk** và dùng dạng external merge.

Nhưng không nên khẳng định mọi `ORDER BY` đều chạy đúng chương trình Java này: database còn có sort operator riêng, page buffer, quản lý giao dịch, nén và parallelism.

## 25. Sai lầm phổ biến

1. **Đọc toàn bộ tệp vào ArrayList trước khi sort**, không còn là external sort thực chất.
2. **Chỉ dùng BufferedReader nhưng vẫn giữ mọi bản ghi trong một Map/list**, bộ nhớ vẫn O(N).
3. **Nối các run đã sort thay vì merge**, output toàn cục không được sort.
4. **Đưa toàn bộ bản ghi của mọi run vào heap**, heap tăng O(N).
5. **Cho rằng heap có tối đa N phần tử**, trong k-way merge đúng nó chỉ cần tối đa F đầu run.
6. **Không theo dõi run nào vừa cung cấp phần tử**, không biết từ run nào cần đọc tiếp.
7. **Không nạp phần tử tiếp theo sau khi pop heap**, làm mất bản ghi.
8. **Nạp hai lần cùng bản ghi từ một run**, tạo bản ghi trùng.
9. **Dùng sentinel Long.MAX_VALUE thay hết tệp**, nhầm với giá trị hợp lệ.
10. **Dùng phép trừ long rồi ép int để so sánh**, comparator có thể tràn.
11. **Dùng Set để bỏ trùng trong output**, sai bài sorting cho multiset.
12. **Bỏ run cuối vì không đủ M bản ghi**, mất dữ liệu.
13. **Đệm quá nhiều run vượt RAM/file descriptor**, thất bại khi trộn.
14. **Giả định F luôn bằng R₀**, trong thực tế không thể mở mọi run.
15. **Không làm lượt merge tiếp theo khi vẫn còn nhiều run**, output không toàn cục.
16. **Đặt fanIn=1**, vòng merge không giảm số run.
17. **Dùng chia nguyên N/M thay ceil**, đếm thiếu run cuối.
18. **Đếm lượt merge bằng log rồi bỏ làm tròn**, sai với R₀ không phải lũy thừa F.
19. **Nhầm number of merged groups với number of passes**, hai chỉ số khác nhau.
20. **Không tính final copy trong I/O thực tế**, đánh giá thấp lượng truyền dữ liệu.
21. **Coi chi phí heap O(log N)** khi chỉ có F đầu, cận sát hơn là O(log F).
22. **Không tính sort trong RAM của từng chunk**, bỏ quên CPU O(N log M).
23. **Chỉ tối ưu so sánh mà bỏ chi phí I/O nhiều lượt**, không tận dụng bộ đệm.
24. **Dùng buffer quá nhỏ**, tạo nhiều yêu cầu đọc/ghi không cần thiết.
25. **Dùng buffer rất lớn cho hàng nghìn run**, tổng buffer vượt giới hạn.
26. **Không xóa tệp tạm đã merge xong**, dung lượng disk tăng theo số pass.
27. **Xóa run nguồn trước khi run đích ghi thành công**, có thể mất dữ liệu.
28. **Ghi đè input ngay trong quá trình đọc**, làm hỏng dữ liệu chưa đọc.
29. **Đọc text bằng `DataInputStream.readLong`**, hiểu sai định dạng.
30. **Không kiểm tệp dài bội số 8 byte**, bỏ qua dữ liệu cuối bị cắt.
31. **Tự cho rằng output được ghi atomic**, dù copy có thể dừng giữa chừng.
32. **Cho rằng `finally` xử lý cả crash/mất điện**, thực tế không.
33. **Chỉ kiểm output sorted mà không kiểm số lượng/multiset**, không phát hiện thiếu/trùng.
34. **Cho rằng các bản ghi trùng làm thuật toán sai**, trong khi duplicates là dữ liệu bình thường.
35. **Gọi sort long không payload là minh chứng cho stable sort record**, thiếu thứ tự nguồn để kiểm.
36. **Gọi trộn hai run là external merge sort đầy đủ**, bỏ qua pha tạo run và số lượt khi R₀ lớn.
37. **Không phân biệt N bản ghi với N byte**, làm sai M/B và phép tính file length.
38. **Không tính độ dài record**, nhầm 8 byte với 8 bit.
39. **Quên rằng file descriptor là tài nguyên hữu hạn**, O(F) RAM chưa đủ bảo đảm chạy được.
40. **Giữ file reader mở sau khi nhóm đã merge**, khiến chạm trần descriptors ở lượt kế tiếp.
41. **Cho rằng mọi sort ngoài bộ nhớ luôn nhanh hơn sort nội bộ**, kể cả khi dữ liệu vừa RAM.
42. **Bỏ qua chi phí serialization/parse** khi chuyển CSV sang run binary.
43. **Kết luận timing từ một mẫu 17 phần tử**, không phản ánh thời gian trên SSD/HDD.
44. **Không thống nhất endian giữa producer và consumer**, làm giá trị binary sai.
45. **Đếm record count bằng int** cho tệp có thể vượt 2³¹ bản ghi.
46. **Không có giới hạn memory chunk do caller chỉ định**, có thể cấp phát mảng quá lớn.
47. **Nhầm độ ổn định với sắp xếp không giảm**, hai tính chất khác nhau.
48. **Cố copy run đơn lẻ ở mọi lượt**, tạo I/O dư không cần thiết.
49. **Không test N=0, N=1, số âm, duplicates và fanIn=2**, để sót lỗi biên.
50. **Không công bố giới hạn phục hồi khi lỗi disk**, khó dùng trong ứng dụng thật.

## 26. Câu hỏi và bài tập tự luyện

**Bài 1.** External merge sort dùng khi nào?

*Đáp án:* Khi dữ liệu lớn hơn RAM khả dụng và cần sắp xếp bằng cách tạo run trên bộ nhớ ngoài rồi trộn.

**Bài 2.** Hai giai đoạn chính là gì?

*Đáp án:* **Tạo run đã sort trong RAM**, rồi **trộn các run** thành một run cuối.

**Bài 3.** Nếu N=17 và M=4 thì có bao nhiêu run ban đầu?

*Đáp án:* \(\lceil17/4\rceil=5\).

**Bài 4.** Run cuối của ví dụ trên có bao nhiêu bản ghi?

*Đáp án:* 1 bản ghi.

**Bài 5.** Có thể nối trực tiếp hai run đã sort để được một run sort không?

*Đáp án:* Không trong trường hợp tổng quát; phải merge theo thứ tự giá trị.

**Bài 6.** Khi trộn F run, min-heap giữ tối đa bao nhiêu đầu run?

*Đáp án:* Tối đa **F**.

**Bài 7.** Mỗi lần heap lấy ra bản ghi từ run i, làm gì tiếp?

*Đáp án:* Ghi bản ghi đó và, nếu run i còn dữ liệu, đọc đầu tiếp theo của **chính run i** đưa vào heap.

**Bài 8.** Với 5 run và fan-in 3, cần bao nhiêu lượt merge?

*Đáp án:* **2** lượt.

**Bài 9.** Số run sau một lượt merge fan-in F được tính thế nào?

*Đáp án:* \(\lceil R/F\rceil\).

**Bài 10.** Vì sao cần F≥2?

*Đáp án:* Nếu F=1 thì số run không giảm, không thể hợp nhiều run thành một run.

**Bài 11.** Mỗi lượt merge đọc/ghi dữ liệu theo bậc I/O bao nhiêu?

*Đáp án:* \(O(N/B)\) block I/Os trong mô hình quét tuần tự.

**Bài 12.** Tổng I/O của generation và P lượt merge theo bậc là gì?

*Đáp án:* \(O((N/B)(1+P))\).

**Bài 13.** Nếu chương trình copy run cuối sang output, thêm bao nhiêu I/O?

*Đáp án:* Thêm \(O(N/B)\) block I/Os cho một lượt đọc và ghi.

**Bài 14.** CPU chi phí trộn một nhóm T bản ghi và F run là gì?

*Đáp án:* \(O(T\log F)\).

**Bài 15.** CPU tạo các run trong RAM có cận nào?

*Đáp án:* \(O(N\log M)\) theo cách sort chunk chuẩn.

**Bài 16.** Vì sao không thể mở đồng thời quá nhiều run?

*Đáp án:* Vì giới hạn số file descriptors và RAM cho bộ đệm đầu vào/đầu ra.

**Bài 17.** Nếu một nhóm merge chỉ có một run thì làm sao?

*Đáp án:* Chuyển run ấy sang lượt sau, không cần copy vì nó vốn đã sort.

**Bài 18.** Chứng minh output sorted cần bất biến heap gì?

*Đáp án:* Heap chứa đầu chưa xuất của mọi run chưa cạn; min trong heap là min toàn bộ dữ liệu chưa xuất.

**Bài 19.** Chứng minh không mất bản ghi dựa trên điều gì?

*Đáp án:* Mỗi bản ghi input được ghi đúng một run ban đầu và mỗi lượt merge lấy/ghi mỗi bản ghi đúng một lần.

**Bài 20.** Nếu có hai số 7 trong input, output phải có bao nhiêu số 7?

*Đáp án:* **Hai**; sắp xếp không loại trùng.

**Bài 21.** Sắp xếp ổn định có nghĩa gì?

*Đáp án:* Những bản ghi có key bằng nhau giữ nguyên thứ tự tương đối như trong input gốc.

**Bài 22.** Vì sao cần originalOrdinal nếu muốn sort ổn định key/payload qua nhiều run?

*Đáp án:* Nó cung cấp thứ tự toàn cục để phá hòa giữa các record cùng key.

**Bài 23.** Định dạng binary long trong bài dùng mấy byte mỗi bản ghi?

*Đáp án:* **8 byte**, big-endian theo Java Data Streams.

**Bài 24.** Vì sao không được đọc tệp CSV trực tiếp bằng readLong?

*Đáp án:* readLong giải mã 8 byte nhị phân, không parse chữ số/đấu phẩy của CSV.

**Bài 25.** Nếu input có 19 byte, có thể chứa toàn bộ các bản ghi long 8 byte hợp lệ không?

*Đáp án:* Không, vì 19 không chia hết cho 8; tệp bị cắt giữa bản ghi hoặc sai định dạng.

**Bài 26.** N=0, số run và số lượt merge là bao nhiêu?

*Đáp án:* R₀=0, P=0; output là tệp rỗng.

**Bài 27.** Nếu N≤M thì cần bao nhiêu lượt merge?

*Đáp án:* P=0; một run đã sort đủ cho toàn dữ liệu không rỗng.

**Bài 28.** Vì sao external merge sort không yêu cầu giữ N bản ghi trong RAM?

*Đáp án:* Chỉ giữ tối đa M bản ghi khi tạo run, rồi các buffer và tối đa F đầu run trong heap khi merge.

**Bài 29.** Tệp tạm có thể chiếm bao nhiêu không gian theo bậc?

*Đáp án:* O(N) bản ghi, hệ số tùy cách giữ run cũ/mới và output.

**Bài 30.** Nếu output đã sort không giảm nhưng thiếu bản ghi, thuật toán có đúng không?

*Đáp án:* Không; phải bảo toàn multiset và đủ số bản ghi.

**Bài 31.** Để đối chiếu kết quả trên input nhỏ, nên dùng oracle nào trong Java?

*Đáp án:* `Arrays.sort` trên bản sao mảng nhỏ, sau đó so output từng phần tử.

**Bài 32.** Khi N lớn hơn RAM thật, có nên gọi `readSmallForDemo` trên output không?

*Đáp án:* Không; phải dùng kiểm chứng streaming phù hợp, vì helper đó tải dữ liệu vào RAM và chỉ dành cho test nhỏ.

**Bài 33.** Muốn giảm số lượt merge, tăng M hay F có tác dụng gì?

*Đáp án:* Tăng M giảm R₀, tăng F giảm số lượt cần thiết; cả hai bị giới hạn bởi RAM và I/O resources.

**Bài 34.** Vì sao tăng F không phải lúc nào cũng tốt?

*Đáp án:* Tăng số input buffer, file descriptors và chi phí heap; có thể vượt ngân sách hoặc giảm hiệu năng.

**Bài 35.** Nếu bị mất điện trong lúc merge, `finally` có bảo đảm khôi phục không?

*Đáp án:* Không; muốn phục hồi phải có manifest/checkpoint và chiến lược commit riêng.

**Bài 36.** Một ứng dụng dùng external merge để ORDER BY mọi truy vấn có tối ưu không?

*Đáp án:* Không nhất thiết; cần xét kích thước dữ liệu, index, đã sort sẵn hay chưa, memory grant và chi phí I/O của workload.

**Tổng kết:** External merge sort giải bài toán sắp xếp tập dữ liệu **lớn hơn RAM** bằng hai bước: tạo các **run đã sắp xếp** từ từng chunk tối đa M bản ghi, rồi **k-way merge** các run bằng min-heap tối đa F đầu và buffer tuần tự. Nếu \(R_0=\lceil N/M\rceil\) run lớn hơn fan-in, trộn qua \(P=\lceil\log_F R_0\rceil\) lượt khi R₀>1. Trong mô hình mỗi I/O truyền B bản ghi, tổng chi phí có bậc \(O((N/B)(1+P))\), cộng thêm một lượt copy trong bản Java minh họa; CPU có thành phần \(O(N\log M+PN\log F)\). Bất biến của run generation và k-way merge bảo đảm output **không giảm và giữ nguyên multiset**, kể cả phần tử lặp/âm. Java 17 dùng tệp long 8 byte, buffer, PriorityQueue, giới hạn chunk/fan-in, xóa file tạm và oracle Arrays.sort trên dữ liệu nhỏ; để dùng trong hệ thống thật còn cần chọn bộ nhớ, file descriptors, vùng tạm, định dạng tệp, kiểm lỗi và cơ chế commit/khôi phục phù hợp.
