# Bố trí dữ liệu nhận biết bộ nhớ đệm và hướng cache-oblivious

Hai chương trình có cùng độ phức tạp thời gian **O(n)** vẫn có thể chạy nhanh chậm rất khác nhau nếu một chương trình đọc các phần tử liên tiếp, còn chương trình kia liên tục nhảy đến những địa chỉ xa nhau. Lý do nằm ở **hệ phân cấp bộ nhớ**: CPU, các mức cache, RAM và thiết bị lưu trữ không có cùng độ trễ hoặc đơn vị truyền dữ liệu.

Trong chương **Dữ liệu ngoài bộ nhớ**, ta không chỉ đếm số phép so sánh hay số con trỏ mà còn quan tâm đến **số khối dữ liệu phải chuyển giữa các tầng nhớ**. Bài học trình bày hai hướng thiết kế:

- **Cache-aware:** thuật toán hoặc cấu trúc dữ liệu chủ động sử dụng kích thước khối, dung lượng cache/trang và các tham số của hệ thống để bố trí dữ liệu.
- **Cache-oblivious:** thuật toán không nhận các tham số cache làm đầu vào, nhưng tổ chức truy cập có tính cục bộ trên nhiều kích thước khối; dưới những giả thiết chuẩn, một số thuật toán vẫn đạt số lần truyền khối tối ưu về bậc.

Đây là một phần của tư duy chọn **cấu trúc dữ liệu phù hợp**: phải xét bất biến bố trí, thao tác tìm kiếm/cập nhật, chi phí CPU, bộ nhớ và I/O, thay vì chỉ so sánh Big-O trên mô hình RAM.

## 1. Vì sao vị trí dữ liệu lại quan trọng?

Máy tính thường có nhiều tầng lưu trữ, chẳng hạn:

~~~text
         Thanh ghi CPU
               |
           L1 cache
               |
           L2 cache
               |
          L3 / LLC
               |
              RAM
               |
          SSD / HDD

  Càng xuống sâu: dung lượng thường lớn hơn,
  nhưng độ trễ và chi phí chuyển dữ liệu thường cao hơn.
~~~

Đơn vị chuyển dữ liệu thường là **cache line**, **trang** hoặc **khối I/O**, không phải từng biến đơn lẻ. Khi đọc một phần tử từ vùng nhớ chậm, hệ thống thường đưa cả một khối chứa nó vào tầng nhanh hơn. Nếu các phần tử sẽ dùng tiếp nằm gần nhau, nhiều lần truy cập sau có thể tận dụng khối đã chuyển; đây là **tính cục bộ không gian** (*spatial locality*). Nếu cùng dữ liệu được dùng lại trước khi bị đẩy khỏi cache, ta có **tính cục bộ thời gian** (*temporal locality*).

Ví dụ giả sử một cache line dài **64 byte**, còn mỗi số nguyên chiếm **8 byte**. Một line chứa được **8 số nguyên liên tiếp**:

~~~text
Địa chỉ tăng dần:
  [x0 x1 x2 x3 x4 x5 x6 x7] [x8 x9 x10 ...]
  <------- 64 byte -------> <------ line tiếp theo --->
~~~

Đọc tuần tự tám phần tử đầu có thể chỉ cần một lần nạp line từ tầng nhớ bên dưới nếu line chưa có trong cache. Đọc tám vị trí xa nhau có thể cần tám line khác nhau. Con số thực tế phụ thuộc dữ liệu đã có trong cache, cơ chế tiền nạp, chính sách thay thế và ánh xạ cache; ví dụ chỉ minh họa **cách bố trí ảnh hưởng số khối phải nạp**.

Với một mảng lớn hơn cache, chênh lệch này trở nên đáng kể. Cấu trúc dữ liệu dùng mảng liên tiếp thường có lợi khi quét; danh sách liên kết rải rác trên heap có thể phát sinh nhiều lần truy cập bộ nhớ do **pointer chasing** dù cả hai đều duyệt **O(n)** phần tử.

## 2. Mô hình I/O hai tầng: N, M và B

Để phân tích một cách độc lập với hãng CPU hay ổ đĩa, ta xét **mô hình bộ nhớ ngoài** (*external-memory model*, hoặc *I/O model*):

| Ký hiệu | Ý nghĩa |
|---|---|
| **N** | Số phần tử dữ liệu cần xử lý. |
| **M** | Số phần tử chứa được trong bộ nhớ nhanh (cache/RAM đệm). |
| **B** | Số phần tử liên tiếp được truyền trong một lần I/O khối. |
| **N/B** | Số khối cần để chứa một mảng N phần tử, nếu bỏ qua làm tròn và metadata. |

Ở đây **M** và **B cùng được đo bằng số phần tử**. Nếu phần cứng công bố dung lượng theo byte, cần chia cho kích thước mỗi phần tử; không được lấy M bằng byte nhưng B bằng số phần tử trong cùng công thức. Thông thường xét \(1 \le B \le M\).

Chi phí chính là **số lần chuyển khối** giữa hai tầng, còn thao tác CPU trên dữ liệu đã ở bộ nhớ nhanh được xem nhẹ hơn trong mô hình này. Khi truy cập dữ liệu theo thứ tự, một lần **scan** n phần tử cần:

\[
Q_{\text{scan}}(N)=\Theta\left(1+\frac{N}{B}\right)
\]

Đây là cận tối ưu về bậc nếu phải đọc tất cả phần tử: không thể lấy N phần tử mà truyền ít hơn số khối cần chứa chúng. Ngược lại, đọc ngẫu nhiên nhiều phần tử ở các khối khác nhau có thể mất một lần I/O trên mỗi truy cập.

Một ví dụ với trang đĩa **4 KiB** và bản ghi **16 byte**: mỗi trang chứa **256 bản ghi**, bỏ qua header. Quét tuần tự **1.000.000 bản ghi** cần khoảng:

\[
\left\lceil\frac{1\,000\,000}{256}\right\rceil=3907
\]

lượt đọc trang dữ liệu (nếu ban đầu chưa có trang nào trong cache). Nếu phải tìm các bản ghi theo khóa ở những trang rải rác và không có chỉ mục hay cache hữu hiệu, tổng I/O có thể lớn hơn nhiều. Tuy nhiên truy cập ngẫu nhiên **không mặc nhiên** gây một lần đọc đĩa mỗi thao tác: trang có thể đã nằm trong cache và chỉ mục có thể loại bỏ phần lớn ứng viên.

### 2.1. Mô hình lý tưởng khác phần cứng thật thế nào?

Phân tích cache-oblivious thường dùng **ideal-cache model**: cache có sức chứa M phần tử, truyền các block B phần tử, kết hợp hoàn toàn (*fully associative*) và có chính sách thay thế tối ưu. Nhiều chứng minh còn giả sử **tall cache**:

\[
M=\Omega(B^2)
\]

Nghĩa là cache đủ lớn so với kích thước block, khi cả hai được đo bằng **phần tử**. Giả thiết này quan trọng đối với một số cận I/O của thuật toán ma trận, sắp xếp và chia để trị; không phải mọi thuật toán cache-oblivious đều cần cùng điều kiện.

Trong máy thật, cache có mức kết hợp hữu hạn, TLB, phần cứng tiền nạp, các mức cache khác nhau, ghi trả về (*write-back*) và nhiều luồng tranh chấp bộ nhớ. Vì vậy cận I/O lý tưởng giúp **thiết kế và so sánh xu hướng**; tốc độ cuối cùng vẫn cần benchmark.

## 3. Cache-aware: biết kích thước khối để sắp dữ liệu

Một thuật toán **cache-aware** sử dụng trực tiếp các tham số như **B** (kích thước block) hoặc **M** (dung lượng tầng nhớ nhanh), hay giá trị thực nghiệm như **tile size** để chọn cách tổ chức.

Ba ví dụ phổ biến:

1. **B-tree/B+tree trên đĩa:** một nút chứa nhiều khóa và con trỏ, thường được thiết kế để nằm gọn trong một hoặc vài trang. Như vậy một lần đọc trang có thể cung cấp nhiều mốc tìm kiếm.
2. **Blocked/tiled matrix:** ma trận được xử lý thành các ô vuông nhỏ để dữ liệu được dùng nhiều lần khi còn ở cache.
3. **Blocked array hoặc cấu trúc phân trang:** các phần tử được gom theo block để truy cập hàng xóm tiết kiệm I/O và không tạo quá nhiều cấp con trỏ.

Điểm mạnh của cache-aware là có thể tận dụng chi tiết thiết bị. Đổi lại, nếu kích thước cache line, trang SSD, số lõi hay dung lượng cache thay đổi, tham số tối ưu có thể đổi theo.

### 3.1. B+tree nhận biết trang

Nếu một trang chứa được nhiều khóa phân tách và con trỏ con, B+tree sẽ có **hệ số phân nhánh lớn**. Với **b** là số con trung bình trên một nút và N khóa, độ cao tìm kiếm được chặn bởi **O(log_b N)** trong các điều kiện cân bằng thông thường.

Nếu b tỷ lệ với B phần tử/trang, ta có chi phí đọc trang điển hình theo bậc:

\[
Q_{\text{search}}(N)=O(\log_B N)
\]

Ở đây ký hiệu **O** che các hệ số do header, kích thước khóa/con trỏ, mức đầy trang và cache. Không nên đồng nhất **B phần tử/trang** với **đúng B con** trong một nút; kích thước khóa và con trỏ thực tế quyết định fan-out.

B+tree thường giữ các khóa ở nút lá theo thứ tự logic, có thể nối các lá để hỗ trợ **RANGE** bằng quét liên tiếp các trang lá. Tính chất này khiến B+tree hữu ích cho cả tìm kiếm điểm và truy vấn khoảng.

## 4. Ví dụ cache-aware: chuyển vị ma trận bằng ô (tiling)

Cho hai ma trận vuông **A** và **T**, cùng có n hàng và n cột, lưu dạng **row-major** (các phần tử cùng hàng nằm liên tiếp trong bộ nhớ). Ta cần:

\[
T[j][i]=A[i][j]
\]

Phiên bản đơn giản:

~~~text
for i = 0 .. n-1:
    for j = 0 .. n-1:
        T[j][i] = A[i][j]
~~~

Lượt đọc **A[i][j]** tăng liên tục theo hàng, nhưng lượt ghi **T[j][i]** nhảy giữa nhiều hàng cách nhau khoảng **n phần tử**. Nếu n lớn, các ghi có thể phải kéo vào cache nhiều line khác nhau rồi đẩy ra trước khi tái sử dụng.

Cách cache-aware là chia ma trận thành các ô vuông kích thước **t × t** và chuyển vị từng ô:

~~~text
function TRANSPOSE_TILED(A, T, n, tile):
    for i0 = 0; i0 < n; i0 += tile:
        for j0 = 0; j0 < n; j0 += tile:
            i1 = min(i0 + tile, n)
            j1 = min(j0 + tile, n)
            for i = i0; i < i1; i++:
                for j = j0; j < j1; j++:
                    T[j][i] = A[i][j]
~~~

Trong một ô, dữ liệu của cả A và T có thể được dùng lại khi còn trong cache. Nếu mỗi phần tử chiếm **s byte** và cache mục tiêu có sức chứa **C byte**, điều kiện sơ bộ để chứa hai ô là:

\[
2t^2s \lesssim C
\]

Ví dụ **s = 8 byte**, **t = 32** thì hai ô chứa \(2\cdot32^2\cdot8=16384\) byte (**16 KiB**). Đây chỉ là ước lượng dung lượng; cần dành chỗ cho dữ liệu khác và cân nhắc cache associativity, alignment, write-allocate, TLB và việc chạy nhiều luồng. Vì vậy t nên được **đo thực nghiệm**, không tự động chọn bằng toàn bộ dung lượng cache.

Trong mô hình I/O với block chứa B phần tử, một cách chọn ô thích hợp để vừa trong bộ nhớ nhanh có thể đưa chi phí chuyển vị ma trận lớn về **O(1 + n²/B)** lần chuyển khối, tức cùng bậc với lượng dữ liệu cần đọc/ghi, dưới các giả thiết bộ nhớ và bố trí phù hợp. Nhược điểm là thuật toán **phải có tham số tile** và hiệu quả có thể thay đổi nếu tham số đó không còn phù hợp với tầng nhớ đang xét.

## 5. Cache-oblivious: chia để trị mà không truyền M, B

Một thuật toán **cache-oblivious** không biết kích thước block B hoặc dung lượng cache M khi chạy. Nó tổ chức truy cập sao cho **những phần dữ liệu liên quan được xử lý gần nhau**, thường dùng chia để trị. Khi đệ quy đến các bài toán con đủ nhỏ để nằm trong bất kỳ tầng cache nào, việc sử dụng lại dữ liệu bên trong bài toán con có thể giảm số lần chuyển khối một cách tự nhiên.

Điều quan trọng là **không truyền tile size phụ thuộc phần cứng**, chứ không phải cấm dùng mảng, cấm cấp phát bộ nhớ hay yêu cầu mọi thuật toán phải đệ quy. Quét tuần tự mảng cũng là một ví dụ đơn giản không cần biết B mà vẫn đạt **Θ(1 + N/B)** I/O.

### 5.1. Chuyển vị ma trận theo đệ quy

Vẫn với A, T lưu dạng row-major. Thay vì đặt trước kích thước ô, thuật toán cắt hình chữ nhật theo chiều dài hơn:

~~~text
function TRANSPOSE_RECURSIVE(A, T, i0, j0, rows, cols):
    if rows == 0 or cols == 0:
        return

    if rows == 1 and cols == 1:
        T[j0][i0] = A[i0][j0]
        return

    if rows >= cols:
        first = floor(rows / 2)
        TRANSPOSE_RECURSIVE(A, T, i0,         j0, first,        cols)
        TRANSPOSE_RECURSIVE(A, T, i0 + first, j0, rows - first, cols)
    else:
        first = floor(cols / 2)
        TRANSPOSE_RECURSIVE(A, T, i0, j0,         rows, first)
        TRANSPOSE_RECURSIVE(A, T, i0, j0 + first, rows, cols - first)

function TRANSPOSE(A, T, n):
    TRANSPOSE_RECURSIVE(A, T, 0, 0, n, n)
~~~

Các lượt gọi con phủ **đúng một lần** mỗi phần tử của hình chữ nhật ban đầu, và mỗi phần tử được đưa về vị trí **T[j][i]**. Vì thế thuật toán đúng kể cả khi n không phải lũy thừa của 2. Ví dụ đang dùng **hai ma trận riêng biệt**; chuyển vị ngay trên cùng một vùng nhớ đòi hỏi xử lý hoán đổi và các miền chồng nhau theo cách khác.

Không có giá trị M hay B trong thuật toán. Nhưng giả sử một bài toán con đủ nhỏ để các vùng cần đọc và ghi cùng nằm trong cache: những lần truy cập trong bài toán con có thể dùng lại các line trước khi bị đẩy đi. Đệ quy tiếp tục chia nhỏ ở mọi quy mô, nên có cơ hội tận dụng **L1, L2, L3 và cache phần mềm** mà không chọn một tile riêng cho từng mức.

Với ma trận vuông, **ideal-cache model**, bố trí row-major và điều kiện **tall cache** phù hợp \(M=\Omega(B^2)\), thuật toán chuyển vị cache-oblivious kinh điển có thể đạt:

\[
Q_{\text{transpose}}(n)=O\left(1+\frac{n^2}{B}\right)
\]

lần chuyển khối, cùng bậc với cận dưới phải duyệt và tạo \(n^2\) phần tử. Đây là **cận lý thuyết có điều kiện**, không phải lời hứa rằng mọi cách viết đệ quy sẽ nhanh hơn tiling trong thực tế.

### 5.2. Tại sao không cứ đệ quy là cache-oblivious hiệu quả?

Hãy hình dung một đệ quy duyệt cây mà mỗi nút được cấp phát ở vị trí ngẫu nhiên. Thuật toán không nhận B làm tham số, nhưng những nút liên tiếp trên đường tìm kiếm vẫn có thể nằm trên các line khác nhau. **Không biết cache chưa đủ; bố trí và thứ tự truy cập phải tạo ra tính cục bộ**.

Các chương trình thực tế thường dừng đệ quy ở một bài toán con nhỏ rồi chạy vòng lặp trực tiếp để giảm chi phí gọi hàm. Nếu ngưỡng dừng cố định hoặc được chọn để tối ưu thực nghiệm mà không dựa trên M/B, ý tưởng cache-oblivious cấp cao vẫn còn; tuy nhiên bảo đảm lý thuyết cần được xem lại với cách hiện thực cụ thể.

## 6. Bố trí cây: heap-order, B-tree và van Emde Boas

Với cây tìm kiếm nhị phân cân bằng, một truy vấn đi từ gốc xuống lá qua **O(log₂ N)** nút. Nhưng chi phí I/O còn phụ thuộc cách các nút được đặt trong bộ nhớ.

### 6.1. Ba cách bố trí

| Kiểu bố trí | Cách đặt nút | Ảnh hưởng cục bộ |
|---|---|---|
| **Cấp phát nút rời rạc** | Mỗi nút cấp phát riêng, nối bằng con trỏ. | Đơn giản cho cập nhật nhưng đường đi có thể nhảy qua nhiều khối. |
| **Theo mức (BFS/heap order)** | Gốc, rồi toàn bộ mức kế, rồi mức tiếp theo. | Nút gần gốc có thể nằm gần nhau, nhưng các nhánh sâu có thể xa nhau. |
| **van Emde Boas (vEB) layout** | Chia cây theo chiều cao thành cây phần trên và các cây con phần dưới, bố trí từng phần đệ quy. | Gom các cụm nút thuộc một đường đi ở nhiều thang kích thước khác nhau mà không cần chọn B. |

**vEB layout** là một cách bố trí bộ nhớ, cần phân biệt với **van Emde Boas tree** dùng cho tập khóa nguyên với các phép toán tiền nhiệm/kế nhiệm. Hai khái niệm có liên hệ về ý tưởng đệ quy nhưng không phải cùng một cấu trúc.

Xét cây tìm kiếm nhị phân hoàn chỉnh có 15 khóa:

~~~text
                   8
             /           \
            4             12
          /   \          /  \
         2     6        10   14
        / \   / \       / \   / \
       1   3 5   7     9  11 13 15
~~~

Đây là hai cách tuyến tính hóa tất cả 15 nút vào mảng:

~~~text
BFS:
 [8, 4, 12, 2, 6, 10, 14, 1, 3, 5, 7, 9, 11, 13, 15]

vEB (chia 4 mức thành hai mức trên + các cây con hai mức):
 [8, 4, 12 | 2, 1, 3 | 6, 5, 7 | 10, 9, 11 | 14, 13, 15]
~~~

Trong layout vEB, phần cây trên **[8, 4, 12]** nằm cạnh nhau; các cây con gốc **2**, **6**, **10**, **14** cũng được xếp thành cụm, rồi có thể áp dụng cùng nguyên tắc ở quy mô lớn hơn.

Giả sử rất đơn giản rằng **mỗi block chứa 3 nút**, các block bắt đầu tại vị trí đầu mảng, và bộ nhớ nhanh chưa chứa khối nào. Tìm khóa **5** đi qua các nút **8 → 4 → 6 → 5**:

- **BFS:** lần lượt chạm block chứa [8,4,12], block [2,6,10] rồi block [5,7,9] → **3 block khác nhau**.
- **vEB:** chạm block [8,4,12] rồi block [6,5,7] → **2 block khác nhau**.

Ví dụ chỉ minh họa **một đường đi, một kích thước block**; không khẳng định mọi truy vấn vEB đều ít lần đọc hơn BFS ở mọi B. Kết quả quan trọng hơn là tính chất **đệ quy ở nhiều chiều cao** của vEB layout.

### 6.2. Cận I/O của tìm kiếm theo vEB layout

Khi cây cân bằng có hình dạng phù hợp, kích thước nút đồng đều và được bố trí theo vEB, đường tìm kiếm có thể đạt:

\[
Q_{\text{tree-search}}(N)=O(1+\log_B N)
\]

lượt chuyển block trong mô hình bộ nhớ lý tưởng, dù mã bố trí **không biết B**. Trực giác: ở một độ sâu nào đó, cụm cây con đủ nhỏ để nằm trong số ít block; mỗi khi đi qua một số mức xấp xỉ \(\log_2 B\) của cây mới cần chuyển sang các cụm block khác. Đường đi tổng cộng có **O(log₂ N)** mức, nên chia cho chiều cao cụm cho ta bậc **O(log_B N)**.

Không nên diễn giải công thức là **mọi thao tác trên mọi cây nhị phân cache-oblivious đều O(log_B N)**. Bảo đảm trên giả định bố trí vEB phù hợp và cây cân bằng; **chèn/xóa động** có thể buộc sắp lại các vùng, phát sinh chi phí cập nhật và độ phức tạp bảo trì riêng.

Ngược lại, B-tree đạt bậc I/O tương tự nhờ **đặt nhiều khóa trong một nút bằng cỡ trang B đã biết**, thay vì đóng gói một cây nhị phân thành các cụm đa tỉ lệ.

## 7. Bố trí đệ quy, truy vấn khoảng và dữ liệu động

Không phải mọi thao tác hưởng lợi như nhau từ vEB layout:

- **GET một khóa:** các nút trên đường gốc–lá có thể được gom gần nhau theo nhiều thang block.
- **RANGE(lo, hi):** truy vấn cần duyệt các khóa liền kề trong thứ tự sắp xếp. vEB layout của cây nhị phân **không bảo đảm** mọi khóa liên tiếp nằm liên tục trong mảng vật lý, nên quét khoảng không tự động đạt chi phí **O(k/B)** với k kết quả.
- **INSERT/DELETE:** chèn một nút mới có thể phá hình dạng cây tĩnh hoặc vị trí các cụm. Muốn duy trì tính chất cache-oblivious khi cập nhật, thường cần kỹ thuật riêng về **packed-memory array**, tái cân bằng, bộ đệm hoặc cấu trúc động phức tạp hơn.

Trong B+tree, các lá có thể liên kết theo thứ tự khóa và lưu nhiều khóa trong cùng trang. Vì vậy B+tree thường là lựa chọn tự nhiên cho ứng dụng cần **tìm kiếm điểm, chèn/xóa và quét khoảng** trên đĩa. Tìm kiếm tốt của một layout cây tĩnh chưa đủ để kết luận nó phù hợp hơn B+tree cho hệ thống giao dịch.

Ở một hướng khác, **cache-oblivious lookahead array** và các cấu trúc cache-oblivious động kết hợp nhiều lớp dữ liệu có thể đạt những cận I/O đáng chú ý, nhưng phải phân tích riêng từng phép toán và giả thiết, không suy từ ví dụ vEB tĩnh.

## 8. Bố trí theo hàng, theo cột và dữ liệu liền kề

Bên cạnh cây, lựa chọn bố trí dữ liệu bản ghi cũng ảnh hưởng rõ đến cache:

~~~text
Array of Structures (AoS):
 [id0, x0, y0] [id1, x1, y1] [id2, x2, y2] ...

Structure of Arrays (SoA):
 [id0, id1, id2, ...]
 [x0,  x1,  x2,  ...]
 [y0,  y1,  y2,  ...]
~~~

Với phép toán cần đọc **toàn bộ thông tin của từng bản ghi**, AoS có thể thuận tiện và có cục bộ tốt. Với phép toán chỉ tính tổng cột **x** trên hàng triệu bản ghi, SoA đặt các giá trị x liên tục, tránh kéo nhiều byte của id và y không cần thiết vào cache, đồng thời có thể thuận lợi cho SIMD.

Tuy nhiên SoA không luôn thắng: nếu mỗi thao tác cần mọi trường, việc chuyển giữa nhiều mảng có thể làm tăng số luồng đọc và áp lực cache/TLB. Với dữ liệu lớn, còn phải tính **alignment**, padding, kích thước bản ghi và cách nén.

Hai kiểu này không tự động là thuật toán cache-oblivious; chúng là ví dụ về **bất biến bố trí** tác động đến hiệu quả bộ nhớ. Một cấu trúc có thể kết hợp các quyết định bố trí mức bản ghi với blocked layout hoặc thuật toán đệ quy ở mức cao hơn.

## 9. So sánh theo phép toán và độ phức tạp I/O

Bảng dưới dùng N phần tử, B phần tử/block, k kết quả của truy vấn khoảng. Các cận là **mô hình hóa điển hình** với dữ liệu lớn hơn cache, không bao gồm mọi chi phí CPU, đồng bộ và cập nhật:

| Cấu trúc/thuật toán | Đặc trưng bố trí | Chi phí I/O điển hình | Điều kiện/giới hạn |
|---|---|---|---|
| Quét mảng liên tiếp | Phần tử ở cạnh nhau | **Θ(1 + N/B)** | Áp dụng khi phải đi qua toàn bộ N phần tử. |
| Tìm nhị phân trong mảng tăng dần | Mảng liên tục, nhảy tới mốc giữa | **O(1 + log₂ N)** trong trường hợp xấu, có thể tốt hơn nhờ cache | Mỗi phép so sánh có thể chạm block mới ở đoạn sâu; không tự có cận O(log_B N). |
| B-tree/B+tree | Nút gói theo trang | **O(1 + log_B N)** cho tìm kiếm | Fan-out tỷ lệ B và cây cân bằng; thiết kế dựa trên kích thước trang. |
| Cây nhị phân cân bằng bố trí vEB | Các cây con đa tỉ lệ nằm gần nhau | **O(1 + log_B N)** cho đường tìm kiếm | Chủ yếu minh họa cây tĩnh/bố trí thích hợp; cập nhật động cần phân tích riêng. |
| Chuyển vị ma trận kiểu naive | Đọc tuần tự nhưng ghi bước nhảy xa | Có thể phát sinh nhiều cache miss | Phụ thuộc n, M, B và cache chính sách ghi. |
| Chuyển vị ma trận theo ô hoặc đệ quy | Xử lý vùng nhỏ gần nhau | **O(1 + n²/B)** dưới các điều kiện phù hợp | Tiling cần chọn t; bản đệ quy cần giả thiết ideal cache/tall cache cho cận nêu trên. |

Ở các truy vấn RANGE, thường có phần chi phí tìm điểm bắt đầu cộng với số khối chứa kết quả; chẳng hạn **B+tree với các lá được duyệt hiệu quả** có xu hướng:

\[
Q_{\text{range}}(N,k)=O\left(1+\log_B N+\frac{k}{B}\right)
\]

trong mô hình phù hợp. Không nên gán cận này cho bất kỳ cây nhị phân nào chỉ vì nó cũng duy trì thứ tự khóa logic.

## 10. Chọn hướng thiết kế cho một bài toán

### Trường hợp A — Chỉ mục trên ổ đĩa với cập nhật liên tục

Một kho khóa–giá trị cần **GET, PUT, DELETE, RANGE** trên hàng triệu bản ghi; trang SSD và kích thước khóa khá ổn định. **B+tree bố trí theo trang** thường là một lựa chọn nền tảng đáng xét, vì fan-out cao, các nút có thứ tự và có cơ chế chèn/xóa/duyệt lá đã được phát triển rộng rãi. Nếu tải ưu tiên ghi lớn, các tổ chức khác như LSM-tree và compaction cũng có thể phù hợp; phải so thông lượng ghi, read/write amplification và độ trễ.

Đây là quyết định **cache-aware**, vì thiết kế nút và hệ số phân nhánh dựa trên kích thước trang/khối mục tiêu.

### Trường hợp B — Tính toán ma trận trên nhiều thế hệ CPU

Một thư viện xử lý ma trận cần chạy trên máy có dung lượng L1/L2 khác nhau. **Chuyển vị đệ quy cache-oblivious** cho cách tổ chức không buộc người dùng chọn sẵn t cho từng máy. Đổi lại, overhead đệ quy, SIMD và độ phù hợp với bộ nhớ cache cụ thể có thể khiến một triển khai **tiled, autotuned** chạy nhanh hơn trên cấu hình mục tiêu.

### Trường hợp C — Cây tra cứu tĩnh, rất nhiều truy vấn

Một bộ từ điển khóa được xây dựng một lần rồi đọc nhiều lần, ít hoặc không cập nhật. **Cây cân bằng tuyến tính hóa theo vEB** là hướng đáng thử nếu truy cập chủ yếu đi theo đường gốc–lá và muốn tránh điều chỉnh theo B. Nếu ứng dụng còn cần xuất hàng loạt khóa theo thứ tự, phải benchmark quét khoảng; có thể cần bố trí lá hoặc một cấu trúc khác.

## 11. Đo đạc trên hệ thống thật

Một triển khai có cận I/O tốt trong ideal-cache model vẫn có thể chậm bởi phân nhánh, CPU, cấp phát và đặc điểm phần cứng. Khi benchmark, nên:

1. **Giữ bài toán như nhau:** cùng dữ liệu, truy vấn, kiểu phần tử, mức tối ưu biên dịch và kiểm tra kết quả đầu ra.
2. **Đo dữ liệu đủ lớn:** so trường hợp vừa L1, vừa LLC và lớn hơn RAM/cache liên quan; tốc độ có thể đổi chiều giữa các kích thước.
3. **Phân biệt truy vấn nóng/lạnh:** lặp một khóa nhiều lần có thể khiến tất cả cấu trúc cùng trúng cache; dùng thêm tải với khóa phân tán.
4. **Theo dõi nhiều số liệu:** thời gian, throughput, p95/p99 độ trễ, cache miss, TLB miss, byte chuyển từ DRAM, page fault và I/O khối của SSD khi phù hợp.
5. **Tính cả xây dựng/cập nhật:** một bố trí rất tốt cho tìm kiếm tĩnh có thể tốn nhiều thời gian tái bố trí khi INSERT/DELETE.
6. **Kiểm tra độ bền hiệu năng:** thay B, M, kích thước bản ghi, tỷ lệ GET/RANGE và phân phối khóa; đừng chỉ thử một cấu hình.

Khi tối ưu cụ thể, cũng cần xem xét tính gần nhau về **vị trí vật lý** chứ không chỉ số lượng phần tử: mảng các **con trỏ** liên tục không bảo đảm đối tượng mà chúng trỏ đến cũng liên tục. Một bản ghi lớn có thể vượt quá một cache line; cột dữ liệu nén có thể cần giải nén; các luồng ghi vào cùng line có thể chịu **false sharing**. Các chi phí này có thể chi phối kết quả thực tế.

## 12. Những ngộ nhận thường gặp

**“Thuật toán O(n) luôn nhanh như nhau khi dữ liệu cùng kích thước.”** Sai. Cùng số phần tử nhưng số block phải nạp có thể khác lớn do trình tự và bố trí truy cập.

**“Cache-oblivious nghĩa là không dùng cache.”** Sai. Thuật toán tận dụng cache nhờ tính cục bộ mà không biết tham số cache; chính cache phần cứng/phần mềm vẫn thực hiện lưu và thay thế khối.

**“Bất kỳ mã đệ quy nào cũng tự tối ưu cache.”** Sai. Chia để trị chỉ có ích khi các bài toán con và dữ liệu của chúng được xử lý, bố trí sao cho tái sử dụng phần đã nạp.

**“Cache-aware luôn nhanh hơn cache-oblivious vì biết nhiều thông tin hơn.”** Không có bảo đảm như vậy. Tối ưu phụ thuộc tải và mức độ phù hợp của tham số đã chọn; cache-aware có thể tận dụng phần cứng tốt hơn trong một cấu hình, còn cache-oblivious có thể thích ứng tốt trên nhiều tầng nhớ.

**“Cận O(log_B N) cho GET cũng đảm bảo RANGE O(k/B).”** Sai. Tính liên tục của các khóa trong bộ nhớ vật lý và khả năng đi qua lá liên tiếp mới quyết định hiệu quả scan khoảng.

**“Giảm cache miss là đủ để đạt thời gian thấp nhất.”** Chưa đủ. Một thuật toán có thể giảm miss nhưng tăng số lệnh, nhánh khó dự đoán, chi phí đệ quy hoặc đồng bộ. Cần đo **thời gian thực**, không chỉ một bộ đếm phần cứng.

## 13. Bài tập tự kiểm tra có lời giải

### Bài 1 — Tính số khối khi quét

Một mảng có **4096** phần tử, mỗi phần tử 8 byte. Mỗi cache line chứa **64 byte**; lúc bắt đầu không có dữ liệu nào của mảng trong cache. Nếu đọc mảng tuần tự một lần và bỏ qua các lần đẩy/đọc lặp lại, tối thiểu phải nạp bao nhiêu line?

**Lời giải:** Mỗi line chứa \(64/8=8\) phần tử. Vì \(4096/8=512\), cần **512 line** dữ liệu. Điều này giả sử mảng được căn chỉnh phù hợp; nếu đầu mảng lệch khỏi ranh giới line thì có thể chạm thêm một line.

### Bài 2 — Đọc theo bước nhảy

Vẫn với mảng trên, chương trình đọc các phần tử **a[0], a[8], a[16], ...**. Nếu tất cả lần đọc cần lấy từ tầng nhớ bên dưới, mỗi phần tử truy cập nằm trên một line khác nhau; chỉ đọc **512 phần tử** nhưng có thể phải nạp **512 line**. So với việc đọc 512 phần tử liên tiếp (có thể chỉ cần 64 line), lịch truy cập nào sử dụng băng thông hiệu quả hơn?

**Lời giải:** Đọc **liên tiếp** tốt hơn về cục bộ không gian trong điều kiện đã nêu; cùng số phần tử dùng hữu ích nhưng ít line cần chuyển hơn. Nếu line đã ở cache hoặc phần cứng prefetch tốt, chênh lệch thời gian thực có thể giảm.

### Bài 3 — Phân biệt cache-aware và cache-oblivious

Một thuật toán chuyển vị ma trận có tham số **tile=32**, được đo để phù hợp với L1 của máy hiện tại. Một thuật toán khác cứ chia đôi vùng lớn hơn cho đến khi còn một ô **1 × 1**, không đọc kích thước cache. Thuật toán nào thuộc hướng nào?

**Lời giải:** Bản dùng tile cấu hình theo cache là **cache-aware**; bản chia để trị không dùng M/B là **cache-oblivious về thiết kế**. Chỉ bản cache-oblivious có dạng đệ quy chưa đủ để kết luận tối ưu I/O: còn phải xét bố trí ma trận và chứng minh cận.

### Bài 4 — Đánh giá bố trí cây

Trong cây 15 nút của mục 6, block chứa ba nút liên tiếp. Với truy vấn khóa **5**, vì sao vEB layout ví dụ cần chạm hai block trong khi BFS cần ba? Có thể suy ra vEB luôn nhanh gấp 1,5 lần không?

**Lời giải:** vEB đặt **6** và **5** gần nhau trong cùng một nhóm con; BFS tách chúng sang các mức khác nhau. Không thể suy tốc độ gấp 1,5 lần: ví dụ chỉ đếm block của một đường đi và một kích thước block, không tính cache đã nóng, CPU, TLB hay các truy vấn khác.

### Bài 5 — Chọn cấu trúc

Một hệ thống phải xử lý hàng triệu truy vấn **RANGE(lo, hi)** trên khóa đã sắp thứ tự, đồng thời có INSERT và DELETE. Một cây nhị phân bố trí vEB tĩnh có đường tìm kiếm điểm tốt. Có đủ bằng chứng để chọn nó thay B+tree không?

**Lời giải:** **Chưa.** Cần đánh giá chi phí đi qua các khóa liên tiếp và cập nhật bố trí khi cây đổi hình dạng. B+tree có các trang lá chứa nhiều khóa và cơ chế duyệt lá hiệu quả; đó là ưu điểm có liên quan trực tiếp với RANGE và cập nhật.

## 14. Ghi nhớ

**Cache-aware** biết B/M hoặc tham số phần cứng để chọn cách chia khối; **cache-oblivious** tạo tính cục bộ ở nhiều quy mô mà không cần truyền các tham số đó. Mảng quét tuần tự đạt **Θ(1 + N/B)** I/O, B-tree dựa vào fan-out theo trang để đạt **O(1 + log_B N)** lượt đọc tìm kiếm, còn một cây tĩnh bố trí **van Emde Boas** có thể đạt cận tìm kiếm tương tự mà không biết B.

Khi thiết kế cấu trúc dữ liệu, hãy hỏi **những phần tử nào được truy cập cùng nhau, chúng nằm trên bao nhiêu block, và thao tác cập nhật có phá bố trí đó không**. Các câu hỏi này kết nối trực tiếp tính đúng đắn của bất biến với độ phức tạp thời gian, bộ nhớ và I/O, giúp lựa chọn giải pháp dựa trên **kiểu truy vấn thực tế** thay vì chỉ vào ký hiệu Big-O.
