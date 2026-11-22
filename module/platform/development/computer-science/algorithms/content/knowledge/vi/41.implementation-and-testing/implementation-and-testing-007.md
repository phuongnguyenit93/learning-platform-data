# Truy vết một lần chạy bằng bảng trạng thái

## 1. Truy vết là gì và vì sao cần bảng trạng thái?

Trong phần **Cài đặt và kiểm thử** thuật toán, **truy vết một lần chạy (execution trace, dry-run)** là việc theo dõi từng bước quan trọng khi một thuật toán xử lý **một đầu vào cụ thể**. Thay vì chỉ ghi đầu vào và kết quả, ta ghi trạng thái **trước và sau** mỗi bước để hiểu chính xác chương trình đi theo nhánh nào, biến nào thay đổi và tại sao.

Một **bảng trạng thái (state table)** là bản ghi có cấu trúc. Một hàng thường tương ứng với một vòng lặp, một lần lấy phần tử khỏi queue, một lần nới lỏng cạnh, hoặc một chuyển trạng thái DP. Các cột chứa những thông tin tối thiểu đủ giải thích bước ấy.

Ví dụ tìm vị trí đầu tiên có giá trị không nhỏ hơn `key` trong mảng đã sắp xếp:

~~~text
a = [1, 2, 2, 2, 4, 7]
key = 2
~~~

Nếu chỉ ghi `answer = 1`, ta chưa thấy tại sao thuật toán không trả 2 hoặc 3. Bảng trạng thái sẽ cho biết các khoảng tìm kiếm bị loại dần và vị trí cuối cùng là 1.

### Bảng trạng thái giúp trả lời điều gì?

- **Điều kiện khởi tạo:** biến nào có giá trị ban đầu và có đúng quy ước chỉ số không?
- **Nhánh thực thi:** điều kiện nào quyết định bước chuyển?
- **Chuyển trạng thái:** sau một bước, những biến nào thay đổi?
- **Bất biến:** trạng thái có tiếp tục thỏa điều kiện cần cho tính đúng không?
- **Tiến triển:** hàm đo tiến triển có giảm/tăng để chứng minh vòng lặp kết thúc?
- **Kết quả:** trạng thái dừng được chuyển thành đáp án như thế nào?
- **Sai lệch:** dòng nào đầu tiên khác kết quả kỳ vọng hoặc quy tắc đúng?

Một trace là **bằng chứng quan sát cho một input cụ thể**, không tự động là chứng minh đúng với mọi input. Nó bổ sung cho lập luận bất biến, kiểm thử, debug và so sánh với oracle độc lập.

### Hai ví dụ xuyên suốt

Bài dùng hai thuật toán để minh họa nhiều kiểu trạng thái:

1. **Binary search kiểu `lower_bound`**: trạng thái chỉ gồm vài số nguyên và một quyết định nhánh; bảng rất gọn.
2. **BFS trên đồ thị**: trạng thái chứa hàng đợi, tập đã thăm, khoảng cách và cha; cần snapshot hợp lý để tránh nhầm thứ tự.

Có chương trình Java 17 độc lập in hai bảng và tự chạy các phép đối chứng trên input nhỏ.

## 2. Xác định một “bước” trước khi lập bảng

Mỗi thuật toán có **độ hạt (granularity)** khác nhau. Một hàng bảng không nhất thiết là một dòng mã nguồn; nó là một đơn vị có ý nghĩa thuật toán.

| Thuật toán | Đơn vị một hàng thường hợp lý | Trạng thái cần ghi |
| --- | --- | --- |
| Binary search | Một vòng `while` | `lo,hi,mid,a[mid],nhánh` |
| Two pointers | Một lượt di chuyển con trỏ | `left,right,điều kiện,tổng` |
| Sliding window | Một thao tác thêm/bớt | `L,R,windowStatistic` |
| BFS | Một lần lấy đỉnh khỏi queue | `queue,đỉnh lấy,đỉnh mới,dist` |
| DFS | Một sự kiện enter/exit hoặc stack step | `stack,color,parent` |
| Dijkstra | Một lần extract-min hoặc relax | `heap,distance,edge,newDistance` |
| DP | Một lần tính trạng thái | `i,j,giá trị phụ thuộc,dp[i][j]` |
| Union-Find | Một lệnh `union/find` | `parent,rank/size,component` |
| Sorting | Một lần so sánh/hoán đổi có ý nghĩa | `i,j,pivot,đoạn mảng` |

### Quy tắc một hàng, một checkpoint

Chọn một điểm nhất quán để đọc trạng thái, ví dụ:

~~~text
start of loop
    snapshot BEFORE
    evaluate condition
    perform transition
    snapshot AFTER
~~~

Nếu một hàng ghi `lo` **trước** bước nhưng `hi` **sau** bước mà không có nhãn, bảng dễ gây hiểu nhầm. Nên ghi rõ `lo_before`, `hi_before`, `lo_after`, `hi_after`.

### Không nhất thiết ghi tất cả biến cục bộ

Bảng tốt ghi **đủ thông tin giải thích quyết định**, không phải dump mọi object. Chẳng hạn binary search chỉ cần khoảng tìm kiếm, mid, giá trị tại mid, nhánh và khoảng mới. Một log hàng triệu phần tử ở mỗi bước không giúp đọc rõ hơn và có thể làm chương trình chậm hoặc hết RAM.

## 3. Cách chuẩn bị một bảng trạng thái

Trước khi chạy, viết bốn phần:

1. **Hợp đồng đầu vào**: thuật toán nhận gì; input có yêu cầu đã sort, đồ thị hợp lệ hay số không âm không?
2. **Trạng thái ban đầu**: các biến, queue/stack và cách đánh chỉ số.
3. **Quy tắc chuyển trạng thái**: điều kiện nhánh và tác động chính xác.
4. **Điều kiện dừng và đáp án**: vì sao dừng; lấy kết quả từ biến nào.

Mẫu bảng chung:

| Lượt | Trạng thái trước | Thao tác/nhánh | Trạng thái sau | Điều kiện kiểm tra |
| ---: | --- | --- | --- | --- |
| 0 | `S0` | `action0` | `S1` | `invariant(S1)` |
| 1 | `S1` | `action1` | `S2` | `invariant(S2)` |
| ... | ... | ... | ... | ... |
| Dừng | `Sk` | Không thực hiện bước mới | `Sk` | Postcondition |

### Cần xác định quy ước một lần

- Đánh chỉ số **0-based** hay **1-based**?
- Đoạn chỉ số **đóng** `[L,R]` hay **nửa mở** `[L,R)`?
- `mid` được tính theo floor hay ceil?
- Với BFS, `queue_before` là **trước hay sau khi pop**?
- Đồ thị có duyệt neighbor theo thứ tự nào?
- Mỗi hàng chứa **một sự kiện** hay toàn bộ một vòng lặp?
- Nếu lặp không chạy, có cần ghi hàng `INIT/EXIT` không?

Khi hợp đồng bảng rõ từ đầu, bạn có thể đối chiếu code và bảng mà không phải đoán ý nghĩa mỗi cột.

## 4. Ví dụ chính: `lower_bound` với phần tử trùng

Cho mảng **không giảm** `a[0..n−1]` và khóa `key`. Ta cần trả:

~~~text
lowerBound(a,key)
  = chi so nho nhat i trong [0,n)
    sao cho a[i] >= key

Neu khong ton tai, tra n.
~~~

Ví dụ:

~~~text
a   = [1, 2, 2, 2, 4, 7]
key = 2

result = 1
~~~

Đây là **vị trí đầu tiên** có giá trị >=2, không phải bất kỳ vị trí nào chứa 2. Với duplicate, điều kiện dừng và cập nhật biên phải rất chính xác.

### Thuật toán với khoảng nửa mở

~~~text
lo = 0
hi = n

while lo < hi:
    mid = lo + floor((hi-lo)/2)

    if a[mid] < key:
        lo = mid+1
    else:
        hi = mid

return lo
~~~

`hi=n` là **biên không bao gồm**; chương trình không bao giờ đọc `a[n]`. Trong mỗi vòng có `lo<hi`, nên `mid<hi<=n`, chỉ số `a[mid]` hợp lệ.

### Vì sao dùng `hi = mid`, không phải `mid−1`?

Khi `a[mid] >= key`, vị trí mid **vẫn có thể là đáp án đầu tiên**, nên phải giữ nó trong khoảng tìm kiếm mới. Dùng `hi=mid−1` theo thói quen tìm kiếm trong đoạn đóng sẽ làm mất ứng viên đúng.

### Vì sao dùng `mid = lo + (hi−lo)/2`?

Biểu thức `(lo+hi)/2` có thể tràn `int` khi cả lo và hi rất lớn. Cách tính theo hiệu phù hợp khi `0<=lo<=hi<=n` và n nằm trong miền chỉ số mảng Java.

## 5. Bảng truy vết `lower_bound` từng vòng

Dùng:

~~~text
a = [1, 2, 2, 2, 4, 7]
key = 2
n = 6
~~~

**Khởi tạo:** `lo=0`, `hi=6`. Chọn checkpoint trước/sau mỗi vòng.

| t | lo trước | hi trước | mid | a[mid] | Quyết định | lo sau | hi sau |
| ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| 0 | 0 | 6 | 3 | 2 | `hi=mid` | 0 | 3 |
| 1 | 0 | 3 | 1 | 2 | `hi=mid` | 0 | 1 |
| 2 | 0 | 1 | 0 | 1 | `lo=mid+1` | 1 | 1 |

**Dừng:** `lo=hi=1`, trả chỉ số `1`, sau **3 lần so sánh** giá trị với `key`.

### Đọc một hàng thật chính xác

Ở t=0:

~~~text
lo_before = 0
hi_before = 6
mid = 0 + (6-0)/2 = 3
a[3] = 2

a[3] < key  => false

lo_after = 0
hi_after = 3
~~~

Ở t=1, khoảng `[0,3)` vẫn chứa những ứng viên còn lại. `mid=1`, a[1]=2 nên giữ mid làm ứng viên: hi=1.

Ở t=2, mid=0 có a[0]=1<2; tất cả chỉ số <=0 đều không thể là đáp án, nên lo=1.

### Kiểm một lỗi cố ý

Nếu tại t=1 ta sửa `hi=mid−1`, trạng thái sau có thể thành `hi=0`, dừng ở index0; nhưng `a[0]=1<2`, sai hậu điều kiện. Dòng đầu tiên vi phạm bất biến **giúp xác định nguồn lỗi** thay vì chỉ thấy output sai.

### Trường hợp khác

- `a=[]`, key bất kỳ: không vòng lặp, trả 0.
- `key=0`: trả 0.
- `key=2`: trả 1 (duplicate).
- `key=5`: trả 5 (a[5]=7).
- `key=8`: trả 6 (không có phần tử >=8).
- Mọi phần tử bằng nhau: trả đầu mảng nếu key nhỏ hơn/bằng giá trị, hoặc n nếu key lớn hơn.

Một trace trên `key=2` không tự kiểm được `key=8`, input rỗng hoặc sai thứ tự mảng; cần thêm test.

## 6. Bất biến tìm kiếm nhị phân đọc từ bảng

Tại đầu mỗi vòng, duy trì:

~~~text
0 <= lo <= hi <= n

forall i in [0,lo): a[i] < key

forall i in [hi,n): a[i] >= key
~~~

Hai miền trái và phải đã được phân loại đúng; đáp án đầu tiên nếu có nằm trong `[lo,hi)` hoặc chính tại biên `lo=hi` khi kết thúc.

### Cơ sở

`lo=0`, `hi=n`: hai miền đã loại là rỗng. Bất biến hiển nhiên đúng.

### Bước quy nạp

Nếu `a[mid] < key` và mảng không giảm, mọi i<=mid đều có `a[i]<key`. Đặt `lo=mid+1`, giữ hi, nên miền trái đã loại được mở rộng đúng.

Nếu `a[mid] >= key`, mọi i>=mid đều có `a[i]>=key`. Đặt `hi=mid`, giữ lo, nên miền phải đã loại được mở rộng đúng.

Ở cả hai nhánh, bất biến vẫn đúng.

### Tiến triển và kết thúc

Hàm đo:

~~~text
width = hi-lo
~~~

Khi `lo<hi`, mid nằm trong `[lo,hi)`. Ở nhánh đầu, lo tăng qua mid; ở nhánh sau, hi giảm về mid. Do vậy `width` **giảm nghiêm ngặt** nhưng không âm, vòng lặp chắc chắn dừng.

Khi `lo=hi`, mọi chỉ số trước lo có giá trị nhỏ hơn key và mọi chỉ số từ lo trở đi có giá trị không nhỏ hơn key. Do đó lo là lower bound chính xác, kể cả khi bằng n.

**Bảng trạng thái không thay thế chứng minh trên**, nhưng mỗi hàng có thể được kiểm xem các mệnh đề bất biến có tiếp tục đúng hay không.

## 7. Trace với queue: BFS duyệt đồ thị theo lớp

Một thuật toán khác có trạng thái không thể nén thành hai biên là **Breadth-First Search (BFS)**.

Với đồ thị không trọng số, BFS từ đỉnh s:

- Giữ `queue` chứa các đỉnh đã phát hiện nhưng chưa xử lý.
- Giữ `dist[v]` là số cạnh ngắn nhất từ s tới v (hoặc −1 khi chưa đến).
- Giữ `parent[v]` để truy vết một đường đi tìm được (s nhận −1).
- Khi lấy u ra, duyệt hàng xóm v; nếu v chưa phát hiện, đặt `dist[v]=dist[u]+1`, `parent[v]=u`, thêm v vào queue.

### Đồ thị ví dụ (vô hướng)

~~~text
0: [1, 2]
1: [0, 3, 4]
2: [0, 4]
3: [1, 5]
4: [1, 2, 5]
5: [3, 4]
~~~

Các danh sách kề được duyệt **theo thứ tự tăng**, vì vậy thứ tự enqueue/pop và cây cha được xác định trong ví dụ. Với thứ tự neighbor khác, BFS vẫn tính khoảng cách đúng, nhưng có thể chọn một cây parent và thứ tự pop khác.

### Khởi tạo

~~~text
source = 0
queue = [0]
dist   = [0,-1,-1,-1,-1,-1]
parent = [-1,-1,-1,-1,-1,-1]
~~~

Số −1 được dùng làm sentinel “chưa tới” cho dist và “không có cha” cho parent; không được nhầm nó với một đỉnh hợp lệ.

## 8. Bảng truy vết BFS từng lần pop

Quy ước:

- `queue_before`: trạng thái hàng đợi **ngay trước** khi lấy u.
- `newly_enqueued`: những đỉnh lần đầu được phát hiện khi xử lý u.
- `queue_after`: hàng đợi sau khi pop u và enqueue hết những đỉnh mới.

| t | pop u | queue before | newly enqueued | queue after |
| ---: | ---: | --- | --- | --- |
| 0 | 0 | `[0]` | `[1,2]` | `[1,2]` |
| 1 | 1 | `[1,2]` | `[3,4]` | `[2,3,4]` |
| 2 | 2 | `[2,3,4]` | `[]` | `[3,4]` |
| 3 | 3 | `[3,4]` | `[5]` | `[4,5]` |
| 4 | 4 | `[4,5]` | `[]` | `[5]` |
| 5 | 5 | `[5]` | `[]` | `[]` |

**Điểm quan trọng:** đỉnh 4 đã được khám phá từ đỉnh 1 nên khi đỉnh 2 gặp 4, BFS **không enqueue lại**. Tương tự, đỉnh 5 đã được đỉnh 3 phát hiện, nên đỉnh 4 không enqueue lần thứ hai.

Kết quả:

~~~text
dist   = [0, 1, 1, 2, 2, 3]
parent = [-1,0,0,1,1,3]
popOrder = [0,1,2,3,4,5]
~~~

Một đường đi ngắn nhất từ 0 tới 5 theo cây cha:

~~~text
5 <- 3 <- 1 <- 0

0 -> 1 -> 3 -> 5
length = 3 edges
~~~

### Vì sao queue không chứa duplicate?

Ta đánh dấu `dist[v]` **khi enqueue**, không đợi đến lúc pop. Ngay sau khi một đỉnh được khám phá, lần gặp sau không đưa nó vào queue nữa.

Nếu đánh dấu quá muộn, cùng một đỉnh có thể bị nhiều đỉnh khác enqueue lặp lại, gây dư công việc hoặc thay đổi log và parent.

## 9. Bất biến BFS và cách đối chiếu bảng

Bất biến điển hình khi BFS dùng queue FIFO:

1. Mỗi đỉnh đã được khám phá có `dist[v]>=0`; đỉnh chưa khám phá có dist −1.
2. Mỗi đỉnh được enqueue tối đa một lần.
3. Mỗi đỉnh v khác nguồn khi được phát hiện có `parent[v]=u` với cạnh u–v tồn tại và `dist[v]=dist[u]+1`.
4. Các đỉnh được pop theo **thứ tự khoảng cách không giảm**.
5. Trước khi xử lý u, `queue_before` phản ánh chính xác các đỉnh đã enqueue nhưng chưa pop.

### Vì sao là đường ngắn nhất?

BFS xử lý mọi đỉnh khoảng cách d trước các đỉnh khoảng cách lớn hơn d nhờ FIFO. Đỉnh mới lần đầu được phát hiện qua cạnh từ một đỉnh có khoảng cách d sẽ có đường đi dài d+1. Nếu có đường ngắn hơn tới nó, tầng nhỏ hơn phải được duyệt trước và đã khám phá nó, mâu thuẫn với “lần đầu”.

Do đó `dist[v]` là số cạnh của đường đi ngắn nhất từ nguồn tới v trong đồ thị không trọng số.

### Ghi snapshot hay ghi delta?

Một bảng như phần 8 chỉ cần `queue_before/newly_enqueued/queue_after`; có thể suy ra state thay đổi. Nếu đồ thị rất lớn, lưu **toàn bộ** `dist[]` mỗi bước là quá nặng. Có thể ghi chỉ các cập nhật:

~~~text
t=0: discover 1 (dist=1,parent=0), discover 2 (...)
t=1: discover 3 (dist=2,parent=1), discover 4 (...)
t=3: discover 5 (dist=3,parent=3)
~~~

Cách log theo delta gọn hơn nhưng cần biết cách replay để tái dựng snapshot đầy đủ tại bước bất kỳ.

## 10. Bảng trạng thái khác log, debugger và bằng chứng đúng

### Trace thủ công

Phù hợp khi thuật toán ngắn và input nhỏ. Người học đi theo từng vòng, điền các cột; đây là cách hiểu sâu về flow control.

### Log có cấu trúc

Chương trình tạo mỗi sự kiện:

~~~text
iteration, beforeState, branch, afterState
~~~

Có thể in bảng, xuất CSV/JSON hoặc dùng tracing library. Nếu ghi log từ code, cần thống nhất checkpoint và tránh biến trạng thái bị thay đổi sau khi đã ghi tham chiếu.

### Debugger

Breakpoint và step-through cho phép quan sát stack, locals và heap tại một thời điểm. Debugger rất hữu ích để tìm dòng lỗi, nhưng ảnh chụp tức thời không thay thế bảng ghi toàn chuỗi trạng thái của **một lần chạy**.

### Invariant assertion

Có thể kiểm trực tiếp:

~~~text
assert 0 <= lo <= hi <= n
assert all a[i] < key for i<lo
assert all a[i] >= key for i>=hi
~~~

Trong production, kiểm tất cả phần tử mỗi vòng của binary search khiến thời gian không còn O(log n). Dùng các assertion tốn kém trong test/debug trên input nhỏ hoặc bật có chủ đích, rồi tắt ở đường chạy hiệu năng cao.

### Một trace không phải benchmark

Trace làm thêm I/O, tạo string, copy queue/array, nên thời gian chạy khi trace bật không đại diện cho tốc độ thuật toán gốc. Muốn đánh giá hiệu năng, đo chương trình khi logging phù hợp và đủ lần chạy.

## 11. Chọn “trạng thái đủ” cho các cấu trúc khác

### Two pointers / sliding window

Giả sử tìm đoạn có tổng dưới ngưỡng trong mảng không âm:

~~~text
t | left_before | right | newValue | sum_before | while-shrinks | sum_after | left_after
~~~

Khi phát hiện kết quả sai, bảng cho biết cửa sổ đang chứa những phần tử nào và sau thao tác shrink có thỏa invariant không.

**Điều kiện:** các kỹ thuật cửa sổ dựa vào tổng không giảm khi mở rộng thường cần phần tử không âm. Nếu có số âm, cùng logic có thể không đúng.

### DP

Với trạng thái `dp[i]`, một hàng cần ghi:

~~~text
i | dependencies | old dp[i] | transition | new dp[i]
~~~

Ví dụ Fibonacci:

~~~text
dp[0]=0, dp[1]=1
dp[2]=dp[1]+dp[0]=1
dp[3]=dp[2]+dp[1]=2
dp[4]=dp[3]+dp[2]=3
~~~

Đối với DP 2D, ghi thứ tự duyệt `i,j`, các trạng thái phụ thuộc và quyết định chuyển. Đừng chỉ ghi bảng cuối vì lỗi thường nằm ở thứ tự cập nhật (đặc biệt khi tối ưu từ 2D xuống 1D).

### Heap / Dijkstra

Một bảng trace nên có:

~~~text
step | extractedNode | extractedDistance |
relaxedEdge | oldDist | candidate | newDist | heap
~~~

Cần giải thích lazy deletion của heap nếu có nhiều entry cho một đỉnh. Dijkstra với cạnh trọng số âm **không thỏa điều kiện chuẩn**.

### Union-Find

Ghi `find(x)`, `find(y)`, root trước/sau union, size/rank và số thành phần. Nếu path compression làm thay đổi parent khi gọi find, đó cũng là một chuyển trạng thái cần phân biệt với union.

### Sort

Ghi pivot hoặc lựa chọn cặp so sánh, vùng đã xử lý, trạng thái mảng sau hoán đổi. Với insertion sort, invariant là prefix đã sort. Với merge sort, ghi hai run đầu vào và từng bước merge; không cần dump toàn bộ mảng ở mọi lần so sánh nếu kích thước lớn.

## 12. Chi phí lưu bảng và tính tái lập

Giả sử thuật toán có T bước. Nếu mỗi hàng giữ một số hằng số biến, chi phí bảng khoảng O(T). Nhưng nếu mỗi hàng chụp cả mảng dài n, log cần O(Tn) bộ nhớ và chi phí copy.

### Ví dụ binary search

Thuật toán chuẩn dùng O(1) auxiliary space và O(log(n+1)) lần so sánh. Bản **giữ tất cả `BinaryStep`** dùng O(log(n+1)) bản ghi, còn test bất biến quét n phần tử mỗi hàng có thể tốn O(n log(n+1)) thời gian.

### Ví dụ BFS

BFS cơ bản có O(V+E) thời gian và O(V) trạng thái thêm, với danh sách kề. Nhưng demo sao chụp queue ở mỗi lần pop. Queue có thể lớn O(V), nên **ghi full queue snapshot trong V bước có thể cần O(V²) thời gian/bộ nhớ cho trace**, ngoài chi phí BFS gốc.

Bởi vậy demo BFS với bảng đầy đủ phù hợp cho **đồ thị nhỏ và mục tiêu học/debug**; production nên giới hạn số sự kiện, dùng log theo delta hoặc sampling.

### Điều kiện để replay đáng tin

- Chốt input, cấu hình, seed và phiên bản code.
- Xác định thứ tự duyệt neighbor/pivot/tie-break.
- Gắn step ID, task ID và event type.
- Phân biệt giá trị **trước/sau**, không lưu tham chiếu mutable rồi để nó thay đổi.
- Nếu có concurrency, ghi cả quan hệ thứ tự và thread/task ID; một timestamp tuyệt đối không đủ biểu diễn toàn bộ happens-before.
- Nếu có dữ liệu nhạy cảm, không log plaintext password, token hoặc PII vào trace.

### Không ép tính xác định khi thuật toán cho nhiều đáp án

Nếu BFS thay đổi thứ tự neighbors, có thể có nhiều cây cha đúng nhưng cùng khoảng cách. Test nên kiểm **hợp đồng đúng** (distances, parent edges, reachable), không luôn khóa vào một pop order khi đề không yêu cầu thứ tự ấy.

## 13. Java 17: chương trình xuất bảng trạng thái có thể kiểm

Chương trình sau có hai đường thực thi:

- `lowerBoundTraced` trả chỉ số và danh sách từng vòng với **before/after** rõ ràng. Hàm giả định input sorted, **không scan để validate sorted trong đường thuật toán**, nhằm giữ O(log n) comparisons.
- `bfsTraced` duyệt đồ thị vô hướng **không trọng số**, lưu queue snapshots và các đỉnh mới. Graph demo có adjacency theo thứ tự tăng, nên bảng in ra cố định.
- `auditBinary` đối chiếu từng hàng với công thức chuyển và bất biến, rồi so đáp án với **oracle tìm tuyến tính**.
- `verifySortedArrays` liệt kê mọi mảng không giảm có độ dài 0..7 trên bảng chữ giá trị `{-1,0,1}` và 5 target `{-2,-1,0,1,2}`.
- `verifyAllGraphs` liệt kê mọi đồ thị vô hướng đơn trên 1..5 đỉnh, so các khoảng cách BFS với **Floyd–Warshall độc lập**, kiểm parent và replay trace queue.

Không cần thư viện ngoài JDK. Chỉ số mảng là **0-based**; khoảng binary search nửa mở `[lo,hi)`; queue hiển thị đầu hàng đợi ở bên trái.

**Lưu mã thành `StateTableTraceDemo.java`:**

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class StateTableTraceDemo {

    record BinaryStep(
            int t, int loBefore, int hiBefore,
            int mid, int value, String branch,
            int loAfter, int hiAfter) {}

    record BinaryTrace(int index, List<BinaryStep> steps) {}

    record BfsStep(
            int t, int popped,
            List<Integer> queueBefore,
            List<Integer> discovered,
            List<Integer> queueAfter) {}

    record BfsTrace(
            int[] distance, int[] parent,
            List<Integer> popOrder,
            List<BfsStep> steps) {}

    static final class Counts {
        int sortedArrays;
        int binaryCases;
        int binaryRows;
        int graphs;
        int bfsRootCases;
    }

    // Sorted input is a precondition; [lo,hi) is half-open.
    static BinaryTrace lowerBoundTraced(int[] a, int key) {
        Objects.requireNonNull(a, "a");
        int lo = 0, hi = a.length;
        List<BinaryStep> steps = new ArrayList<>();

        while (lo < hi) {
            int oldLo = lo, oldHi = hi;
            int mid = lo + (hi - lo) / 2;
            int value = a[mid];
            String branch;

            if (value < key) {
                lo = mid + 1;
                branch = "lo=mid+1";
            } else {
                hi = mid;
                branch = "hi=mid";
            }

            steps.add(new BinaryStep(
                    steps.size(), oldLo, oldHi,
                    mid, value, branch, lo, hi));
        }
        return new BinaryTrace(lo, List.copyOf(steps));
    }

    static int linearLowerBound(int[] a, int key) {
        for (int i = 0; i < a.length; i++) {
            if (a[i] >= key) {
                return i;
            }
        }
        return a.length;
    }

    // Test-only: scans the whole array to audit the invariant.
    static void auditBinary(
            int[] a, int key, BinaryTrace trace) {
        int lo = 0, hi = a.length, t = 0;

        for (BinaryStep s : trace.steps()) {
            if (s.t() != t
                    || s.loBefore() != lo
                    || s.hiBefore() != hi
                    || !(lo < hi)) {
                throw new AssertionError("bad trace checkpoint");
            }
            for (int i = 0; i < lo; i++) {
                if (a[i] >= key) {
                    throw new AssertionError(
                            "left invariant broken");
                }
            }
            for (int i = hi; i < a.length; i++) {
                if (a[i] < key) {
                    throw new AssertionError(
                            "right invariant broken");
                }
            }

            int mid = lo + (hi - lo) / 2;
            int oldWidth = hi - lo;
            int nextLo = a[mid] < key ? mid + 1 : lo;
            int nextHi = a[mid] < key ? hi : mid;
            String branch = a[mid] < key
                    ? "lo=mid+1" : "hi=mid";

            if (s.mid() != mid || s.value() != a[mid]
                    || !s.branch().equals(branch)
                    || s.loAfter() != nextLo
                    || s.hiAfter() != nextHi
                    || nextHi - nextLo >= oldWidth) {
                throw new AssertionError(
                        "incorrect trace transition");
            }

            lo = nextLo;
            hi = nextHi;
            t++;
        }

        if (lo != hi || lo != trace.index()
                || lo != linearLowerBound(a, key)) {
            throw new AssertionError(
                    "wrong lower bound or termination");
        }
    }

    // Explicitly copies queue snapshots: meant for small graphs.
    static BfsTrace bfsTraced(int[][] graph, int source) {
        Objects.requireNonNull(graph, "graph");
        int n = graph.length;
        if (source < 0 || source >= n) {
            throw new IllegalArgumentException(
                    "source out of bounds");
        }

        int[] dist = new int[n];
        int[] parent = new int[n];
        Arrays.fill(dist, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        List<BfsStep> steps = new ArrayList<>();
        List<Integer> order = new ArrayList<>();
        dist[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            List<Integer> before =
                    List.copyOf(new ArrayList<>(queue));
            int u = queue.removeFirst();
            List<Integer> added = new ArrayList<>();

            for (int v : graph[u]) {
                if (dist[v] == -1) {
                    dist[v] = dist[u] + 1;
                    parent[v] = u;
                    queue.addLast(v);
                    added.add(v);
                }
            }

            order.add(u);
            steps.add(new BfsStep(
                    steps.size(), u, before,
                    List.copyOf(added),
                    List.copyOf(new ArrayList<>(queue))));
        }
        return new BfsTrace(
                dist, parent, List.copyOf(order),
                List.copyOf(steps));
    }

    // Replay snapshots for small graphs; not a production hot path.
    static void auditBfsQueue(
            int[][] graph, int source, BfsTrace trace) {
        ArrayDeque<Integer> queue = new ArrayDeque<>();
        boolean[] seen = new boolean[graph.length];
        queue.addLast(source);
        seen[source] = true;
        List<Integer> order = new ArrayList<>();

        for (BfsStep step : trace.steps()) {
            if (step.t() != order.size()
                    || !step.queueBefore().equals(
                            new ArrayList<>(queue))) {
                throw new AssertionError(
                        "BFS queue-before mismatch");
            }
            int popped = queue.removeFirst();
            if (step.popped() != popped) {
                throw new AssertionError("BFS pop mismatch");
            }
            order.add(popped);
            List<Integer> added = new ArrayList<>();

            for (int v : graph[popped]) {
                if (!seen[v]) {
                    seen[v] = true;
                    added.add(v);
                    queue.addLast(v);
                }
            }
            if (!step.discovered().equals(added)
                    || !step.queueAfter().equals(
                            new ArrayList<>(queue))) {
                throw new AssertionError(
                        "BFS state transition mismatch");
            }
        }

        if (!queue.isEmpty()
                || !order.equals(trace.popOrder())) {
            throw new AssertionError(
                    "BFS trace failed to terminate");
        }
    }

    static void enumerateSorted(
            int[] a, int at, int minimum, Counts c) {
        if (at == a.length) {
            c.sortedArrays++;
            for (int target = -2; target <= 2; target++) {
                BinaryTrace trace =
                        lowerBoundTraced(a, target);
                auditBinary(a, target, trace);
                c.binaryCases++;
                c.binaryRows += trace.steps().size();
            }
            return;
        }

        for (int value = minimum; value <= 1; value++) {
            a[at] = value;
            enumerateSorted(a, at + 1, value, c);
        }
    }

    static void verifySortedArrays(Counts c) {
        for (int n = 0; n <= 7; n++) {
            enumerateSorted(new int[n], 0, -1, c);
        }
    }

    static void verifyAllGraphs(Counts c) {
        final int INF = 1_000_000;

        // All simple undirected graphs on 1..5 vertices.
        for (int n = 1; n <= 5; n++) {
            List<int[]> edges = new ArrayList<>();
            for (int u = 0; u < n; u++) {
                for (int v = u + 1; v < n; v++) {
                    edges.add(new int[] {u, v});
                }
            }

            int graphCount = 1 << edges.size();
            for (int mask = 0; mask < graphCount; mask++) {
                boolean[][] adjacent = new boolean[n][n];
                int[][] shortest = new int[n][n];

                for (int i = 0; i < n; i++) {
                    for (int j = 0; j < n; j++) {
                        shortest[i][j] =
                                i == j ? 0 : INF;
                    }
                }

                for (int bit = 0; bit < edges.size(); bit++) {
                    if ((mask & (1 << bit)) != 0) {
                        int[] edge = edges.get(bit);
                        int u = edge[0], v = edge[1];
                        adjacent[u][v] = true;
                        adjacent[v][u] = true;
                        shortest[u][v] = 1;
                        shortest[v][u] = 1;
                    }
                }

                int[][] graph = new int[n][];
                for (int u = 0; u < n; u++) {
                    int degree = 0;
                    for (int v = 0; v < n; v++) {
                        if (adjacent[u][v]) {
                            degree++;
                        }
                    }
                    graph[u] = new int[degree];
                    int j = 0;
                    for (int v = 0; v < n; v++) {
                        if (adjacent[u][v]) {
                            graph[u][j++] = v;
                        }
                    }
                }

                // Floyd-Warshall: independent distance oracle.
                for (int k = 0; k < n; k++) {
                    for (int i = 0; i < n; i++) {
                        for (int j = 0; j < n; j++) {
                            shortest[i][j] = Math.min(
                                    shortest[i][j],
                                    shortest[i][k]
                                            + shortest[k][j]);
                        }
                    }
                }

                for (int root = 0; root < n; root++) {
                    BfsTrace trace = bfsTraced(graph, root);
                    auditBfsQueue(graph, root, trace);

                    for (int v = 0; v < n; v++) {
                        int expected = shortest[root][v]
                                == INF ? -1
                                : shortest[root][v];

                        if (trace.distance()[v] != expected) {
                            throw new AssertionError(
                                    "BFS disagrees with Floyd");
                        }
                        int parent = trace.parent()[v];
                        if (v == root || expected == -1) {
                            if (parent != -1) {
                                throw new AssertionError(
                                        "invalid root/unreachable parent");
                            }
                        } else if (parent < 0
                                || !adjacent[parent][v]
                                || trace.distance()[parent] + 1
                                   != expected) {
                            throw new AssertionError(
                                    "invalid BFS parent");
                        }
                    }
                    c.bfsRootCases++;
                }
                c.graphs++;
            }
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 2, 2, 4, 7};
        BinaryTrace binary = lowerBoundTraced(a, 2);

        System.out.println(
                "Lower bound trace: a="
                + Arrays.toString(a) + ", key=2");
        System.out.println(
                "t | lo | hi | mid | a[mid] | branch | newLo | newHi");
        for (BinaryStep s : binary.steps()) {
            System.out.println(
                    s.t() + " | " + s.loBefore() + " | "
                    + s.hiBefore() + " | " + s.mid() + " | "
                    + s.value() + " | " + s.branch()
                    + " | " + s.loAfter() + " | "
                    + s.hiAfter());
        }
        System.out.println(
                "lower_bound = " + binary.index()
                + "; comparisons = " + binary.steps().size());

        int[][] graph = {
                {1, 2},
                {0, 3, 4},
                {0, 4},
                {1, 5},
                {1, 2, 5},
                {3, 4}
        };
        BfsTrace bfs = bfsTraced(graph, 0);
        System.out.println("BFS trace: source=0");
        System.out.println(
                "t | pop | queue_before | discovered | queue_after");
        for (BfsStep s : bfs.steps()) {
            System.out.println(
                    s.t() + " | " + s.popped() + " | "
                    + s.queueBefore() + " | "
                    + s.discovered() + " | "
                    + s.queueAfter());
        }
        System.out.println(
                "BFS distances = "
                + Arrays.toString(bfs.distance()));
        System.out.println(
                "BFS parents = "
                + Arrays.toString(bfs.parent()));
        System.out.println(
                "BFS pop order = " + bfs.popOrder());

        System.out.println(
                "empty lower bound = "
                + lowerBoundTraced(new int[0], 2).index());
        try {
            bfsTraced(graph, 6);
            throw new AssertionError(
                    "invalid BFS source accepted");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid BFS source: "
                    + error.getMessage());
        }

        Counts counts = new Counts();
        verifySortedArrays(counts);
        verifyAllGraphs(counts);
        if (counts.sortedArrays != 120
                || counts.binaryCases != 600
                || counts.binaryRows != 1561
                || counts.graphs != 1099
                || counts.bfsRootCases != 5405) {
            throw new AssertionError(
                    "exhaustive counts mismatch");
        }
        System.out.println(
                "sorted arrays audited = "
                + counts.sortedArrays);
        System.out.println(
                "binary search target cases = "
                + counts.binaryCases);
        System.out.println(
                "binary trace rows audited = "
                + counts.binaryRows);
        System.out.println(
                "undirected graphs audited = "
                + counts.graphs);
        System.out.println(
                "BFS root cases audited = "
                + counts.bfsRootCases);
        System.out.println("all checks passed = true");
    }
}
~~~

### Lệnh biên dịch và chạy

~~~bash
javac StateTableTraceDemo.java
java StateTableTraceDemo
~~~

### Stdout dự kiến, đúng từng dòng

~~~text
Lower bound trace: a=[1, 2, 2, 2, 4, 7], key=2
t | lo | hi | mid | a[mid] | branch | newLo | newHi
0 | 0 | 6 | 3 | 2 | hi=mid | 0 | 3
1 | 0 | 3 | 1 | 2 | hi=mid | 0 | 1
2 | 0 | 1 | 0 | 1 | lo=mid+1 | 1 | 1
lower_bound = 1; comparisons = 3
BFS trace: source=0
t | pop | queue_before | discovered | queue_after
0 | 0 | [0] | [1, 2] | [1, 2]
1 | 1 | [1, 2] | [3, 4] | [2, 3, 4]
2 | 2 | [2, 3, 4] | [] | [3, 4]
3 | 3 | [3, 4] | [5] | [4, 5]
4 | 4 | [4, 5] | [] | [5]
5 | 5 | [5] | [] | []
BFS distances = [0, 1, 1, 2, 2, 3]
BFS parents = [-1, 0, 0, 1, 1, 3]
BFS pop order = [0, 1, 2, 3, 4, 5]
empty lower bound = 0
invalid BFS source: source out of bounds
sorted arrays audited = 120
binary search target cases = 600
binary trace rows audited = 1561
undirected graphs audited = 1099
BFS root cases audited = 5405
all checks passed = true
~~~

Đầu ra không dựa vào **thời gian CPU, random seed hay thứ tự thread**; mọi bảng được tạo theo thứ tự hoàn toàn xác định.

## 14. Vì sao chương trình tạo bảng đáng tin hơn việc ghi kết quả cuối?

### Kết quả binary search

Trong `lowerBoundTraced`, bản ghi `BinaryStep` chứa đầy đủ:

~~~text
turn
lo_before
hi_before
mid
inspected_value
branch
lo_after
hi_after
~~~

Nhờ đó có thể phát hiện sai khác ở bước chuyển **trước khi** kết quả cuối bị sai. `auditBinary` đọc lại các hàng và tái dựng quá trình theo quy tắc từ đầu.

### Nhưng kiểm thử không nên chỉ dùng lại cùng thuật toán

`auditBinary` kiểm tính nhất quán nội bộ của bảng. Để tránh trường hợp cả thuật toán và bộ kiểm cùng mắc một lỗi, chương trình còn dùng `linearLowerBound` — **quét lần lượt từ trái sang phải** để tìm phần tử đầu tiên >=key. Đây là oracle khác chiến lược nhị phân.

### Kết quả BFS

`auditBfsQueue` tái dựng hàng đợi từ các neighbor để kiểm `before/discovered/after`. Ngoài ra, chương trình dùng **Floyd–Warshall** trên các đồ thị nhỏ để tính khoảng cách ngắn nhất độc lập với BFS. Nó còn kiểm mỗi parent là một cạnh hợp lệ và khoảng cách cha đúng ít hơn một.

Sự kết hợp này mạnh hơn so sánh một mảng kết quả với chính kết quả do cùng code in lại.

### Điều chưa được kiểm

Chương trình không xác nhận hiệu năng trên đồ thị lớn, không tự validate adjacency đầu vào ở mọi dòng code và không giải bài có trọng số cạnh. Phần `bfsTraced` giả định adjacency là các chỉ số đỉnh hợp lệ; trên input sai định dạng phải kiểm từ biên hệ thống.

## 15. Bộ test liệt kê trường hợp nhỏ

### Tất cả mảng đã sắp xếp độ dài 0..7

Chọn các giá trị từ `{-1,0,1}` và cho phép trùng. Mảng phải **không giảm**, nên số mảng độ dài n là số cách chọn có lặp:

~~~text
C(n+2,2)
~~~

Cộng n=0..7:

~~~text
1+3+6+10+15+21+28+36
= 120 arrays
~~~

Với mỗi mảng, thử năm key `{-2,-1,0,1,2}`:

~~~text
120 * 5 = 600 lower_bound cases
~~~

Tổng các vòng binary search thực sự được log là:

~~~text
1561 BinaryStep rows
~~~

Mỗi case kiểm đáp án với linear oracle, từng checkpoint với bất biến và khoảng tìm kiếm giảm. Bao gồm input rỗng, toàn phần tử bằng nhau, key nhỏ hơn phần tử đầu, key lớn hơn phần tử cuối và duplicate.

### Tất cả đồ thị vô hướng đơn trên 1..5 đỉnh

Đồ thị vô hướng không self-loop có `n(n−1)/2` cạnh khả dĩ. Mỗi cạnh có thể có hoặc không, nên số đồ thị trên n đỉnh là:

~~~text
2^(n*(n-1)/2)
~~~

Tổng số đồ thị:

~~~text
n=1:    1
n=2:    2
n=3:    8
n=4:   64
n=5: 1024

total = 1099 graphs
~~~

Với mỗi đồ thị, thử BFS từ **mọi gốc**:

~~~text
1*1 + 2*2 + 8*3 + 64*4 + 1024*5
= 5405 root cases
~~~

Floyd–Warshall tính all-pairs shortest distances làm oracle, nên kiểm được cả đồ thị không liên thông. Với đỉnh không thể tới được, dist phải −1, parent phải −1. Với đỉnh tới được khác nguồn, parent phải kề trực tiếp và có dist nhỏ hơn đúng 1.

### Truy vết chỉ một lần có đủ không?

**Không.** Bảng chính chỉ minh họa một lần chạy cụ thể để tìm nguyên nhân/hiểu từng bước. Bộ exhaustive ở đây phục vụ **kiểm chứng nhiều lần chạy** và không thay thế chứng minh bất biến tổng quát.

## 16. Tìm bug bằng dòng sai đầu tiên

Một quy trình debug bằng bảng trạng thái:

1. Chọn **input nhỏ nhất tái hiện lỗi**; cố giảm kích thước mà vẫn sai.
2. Đặt đúng precondition và expected output.
3. Lập bảng theo checkpoint thống nhất.
4. Tính một bảng **kỳ vọng** từ quy tắc chuyển/bất biến hoặc oracle độc lập.
5. So bảng thực tế với bảng kỳ vọng **từng hàng**.
6. Tìm **dòng đầu tiên** khác biệt; lỗi thường nằm trong thao tác tạo ra dòng đó.
7. Sửa mã, chạy lại input tối thiểu và toàn bộ bộ test regression.

### Ví dụ lỗi binary search

Đổi `hi=mid` thành `hi=mid−1` trong một hàm dùng đoạn nửa mở. Bảng ở t=0 có thể vẫn trông hợp lý, nhưng ở t=1 hoặc t=2 ứng viên hợp lệ bị loại. So cột `hi_after` với bất biến sẽ phát hiện đầu tiên.

### Ví dụ lỗi BFS

Đánh dấu `visited[v]` khi pop thay vì lúc enqueue mà không kiểm trùng trên queue. Trong trace, một đỉnh có thể xuất hiện **hai lần trong queue**, đặc biệt khi có nhiều đường đến cùng đỉnh. Cột `newly_enqueued` là dấu hiệu nhanh.

### Regression test

Sau khi sửa, lưu **input gây lỗi** trong bộ test. Một bug từng xuất hiện thường có điều kiện biên riêng (duplicate, array empty, đỉnh không liên thông), vì vậy chỉ chạy lại demo “đẹp” là không đủ.

### Trace không được làm thay đổi ngữ nghĩa

Thêm `println`, sleep hoặc khóa chỉ để log có thể làm thay đổi interleaving trong chương trình đa luồng. Với concurrency, một số bug biến mất khi bật debug (heisenbug). Cần log ít xâm lấn, event IDs, và công cụ race detection khi thích hợp.

## 17. Lỗi thường gặp khi thiết kế bảng trạng thái

| Lỗi | Hậu quả | Khắc phục |
| --- | --- | --- |
| Không ghi precondition | Trace chạy trên input không hợp lệ | Ghi rõ sorted/graph rules |
| Không xác định 0/1-based | Off-by-one | Ghi quy ước chỉ số |
| Trộn biến trước/sau vào cùng cột | Không đọc được chuyển trạng thái | Tách `_before/_after` |
| Chỉ ghi output cuối | Không tìm được bước lỗi | Có checkpoint |
| Dùng `mid=(lo+hi)/2` | Nguy cơ overflow | Dùng `lo+(hi-lo)/2` |
| Dùng `hi=mid−1` trong lower_bound nửa mở | Loại mất ứng viên | Giữ `hi=mid` |
| Quên hi=n là sentinel | Đọc a[n] sai | Chỉ truy cập a[mid] khi lo<hi |
| Không ghi nhánh so sánh | Không giải thích cập nhật | Ghi value/branch |
| Không kiểm width giảm | Vòng lặp vô hạn | Theo dõi `hi−lo` |
| Lấy queue snapshot sau pop nhưng gọi trước | Hiểu sai BFS | Chốt checkpoint |
| Đánh dấu BFS lúc pop | Enqueue duplicate | Mark khi enqueue |
| Không cố định thứ tự neighbor khi so text | Diff không ổn định | Sắp xếp/ghi thứ tự |
| Giữ tham chiếu mutable làm snapshot | Lịch sử bị sửa theo state mới | Deep/shallow copy đúng |
| Dump mảng lớn mỗi bước | Tốn O(Tn) | Ghi delta/sampling |
| Không ghi task ID trong parallel trace | Ghép nhầm các event | Correlation ID |
| So log float mà đòi cùng bit trong mọi thứ tự | Sai số rounding | Định nghĩa tolerance/order |
| Gọi trace là chứng minh đúng mọi input | Quá khẳng định | Invariant + tests |
| Oracle dùng lại chính thuật toán | Lỗi chung có thể bị bỏ sót | Quét tuyến tính/Floyd |
| Chỉ test một input không có duplicate | Không thấy boundary bug | Chọn adversarial cases |
| Thêm logging vào benchmark | Sai số runtime | Benchmark riêng |
| Ghi payload nhạy cảm | Rủi ro dữ liệu | Redact/sanitize |
| Không có giới hạn log | Hết RAM/disk | Event cap/retention |
| Dùng thời gian tường làm thứ tự tuyệt đối của distributed events | Kết luận sai | Dùng sequence/happens-before |
| Không nêu điều kiện dừng | Không chứng minh termination | Theo dõi measure |

### Tự kiểm bảng trước khi sử dụng

Ở mỗi hàng hãy tự hỏi:

~~~text
1. State BEFORE có khớp State AFTER của hàng trước?
2. Branch có phù hợp với điều kiện trên BEFORE?
3. AFTER có đúng tác động của branch?
4. Bất biến còn đúng không?
5. Một đại lượng tiến triển có thay đổi đúng hướng?
~~~

Nếu năm câu hỏi được trả lời rõ, bảng không chỉ là “ghi chép” mà là công cụ kiểm chứng từng chuyển trạng thái.

## 18. Bài tập thực hành và tổng kết

### Bài tập

1. Định nghĩa một lần chạy của thuật toán và execution trace.
2. Phân biệt bảng trạng thái với output cuối.
3. Chọn checkpoint cho vòng `while` hai biến.
4. Giải thích tại sao tách trạng thái trước/sau quan trọng.
5. Điền bảng lower_bound cho `[1,2,2,2,4,7]`, key=2.
6. Giải thích vì sao kết quả không phải index2 hoặc 3.
7. Vẽ khoảng nửa mở `[lo,hi)` sau từng vòng.
8. Chứng minh `hi=n` không dẫn tới truy cập a[n].
9. Giải thích `hi=mid` đúng cho lower_bound.
10. Tìm input khiến `hi=mid−1` trả sai.
11. Chứng minh ba phần của bất biến binary search.
12. Chứng minh `width=hi−lo` giảm.
13. Lập bảng cho key=5 trên mảng ví dụ.
14. Lập bảng cho key=8 và kiểm trả n.
15. Truy vết mảng rỗng, 0 vòng.
16. Viết linear oracle tìm lower bound.
17. Sinh mọi mảng sorted độ dài tối đa 5 với giá trị −1,0,1.
18. Kiểm exhaustive mọi target trên các mảng đó.
19. Điền bảng queue trước/sau pop cho đồ thị BFS của bài.
20. Tính `dist,parent` ở từng sự kiện khám phá.
21. Giải thích vì sao đỉnh 4 không enqueue lại từ đỉnh 2.
22. Giải thích vì sao đỉnh 5 không enqueue lại từ đỉnh 4.
23. Từ parent tìm một đường ngắn nhất 0→5.
24. Đổi thứ tự neighbors và quan sát popOrder thay đổi.
25. Chứng minh khoảng cách BFS vẫn đúng khi thứ tự neighbors đổi.
26. Đổi source BFS thành 5 và điền bảng mới.
27. Tạo đồ thị có một đỉnh cô lập và ghi dist=-1.
28. Cài log theo delta thay vì copy toàn queue.
29. So chi phí O(V+E) BFS với trace full queue O(V²+E).
30. Tạo một lỗi cố ý đánh dấu BFS lúc pop và tìm dòng sai.
31. Dùng Floyd–Warshall để đối chiếu BFS trên đồ thị nhỏ.
32. Liệt kê số đồ thị đơn có n=4 đỉnh (64).
33. Giải thích tổng 1.099 đồ thị với n=1..5.
34. Giải thích tổng 5.405 BFS root cases.
35. Cài quy trình diff hai bảng theo thứ tự step ID.
36. Cần copy object/mảng như thế nào để snapshot bất biến?
37. Tạo bảng two pointers với cột điều kiện và thao tác.
38. Tạo bảng DP Fibonacci với giá trị phụ thuộc.
39. Tạo bảng Dijkstra một lần extract-min và một lần relax.
40. Nêu cách trace Union-Find khi có path compression.
41. Vì sao một trace không đủ chứng minh đúng?
42. Vì sao oracle độc lập có giá trị hơn tự so lại cùng code?
43. Thiết kế input tối thiểu cho một bug off-by-one.
44. Biến bug đó thành regression test sau khi sửa.
45. Phân biệt trace debug với benchmark hiệu năng.
46. Tính kích thước log khi mỗi bước copy n phần tử.
47. Nêu cách giới hạn log và tránh ghi dữ liệu nhạy cảm.
48. Nêu khó khăn khi trace nhiều thread theo thời gian.
49. Viết checklist precondition/invariant/transition/termination cho một thuật toán tự chọn.
50. So sánh trace thủ công, structured logs và debugger cho cùng bài toán.

### Checklist cuối bài

- Đã ghi **input cụ thể** và precondition?
- Đã chọn đúng checkpoint một hàng và thứ tự before/after?
- Đã thống nhất hệ chỉ số, khoảng đóng/nửa mở và sentinel?
- Có cột thể hiện **điều kiện nhánh**?
- Mỗi hàng có đúng **chuyển trạng thái** của thuật toán?
- Có kiểm bất biến tại đầu/sau bước?
- Có đại lượng chứng minh vòng lặp tiến tới kết thúc?
- Khi dừng, hậu điều kiện đã được suy ra từ state cuối?
- Với queue/heap/map, snapshot có bị thay đổi về sau không?
- Với nhiều thread, có ghi event/task ID và thứ tự thích hợp?
- Có tránh log toàn trạng thái quá lớn và dữ liệu nhạy cảm?
- Có oracle độc lập và bộ test nhiều đầu vào, ngoài một trace?
- Có lưu lại input gây lỗi thành regression test?
- Đã phân biệt tracing với profiling/benchmark?

**Kết luận:** lập bảng trạng thái là cách biến một lần chạy vốn khó quan sát thành chuỗi các **chuyển trạng thái có thể kiểm từng bước**. Bắt đầu từ input và precondition, chọn checkpoint, ghi before/branch/after, theo dõi invariant và điều kiện kết thúc, rồi đối chiếu với oracle độc lập. Với `lower_bound`, bảng cho thấy các khoảng bị loại dần mà không mất ứng viên đầu tiên; với BFS, bảng cho thấy queue và những lần khám phá không trùng. Một trace giúp **hiểu và chẩn đoán một lần chạy**, còn tính đúng tổng quát cần **chứng minh bất biến và kiểm thử nhiều trường hợp**.
