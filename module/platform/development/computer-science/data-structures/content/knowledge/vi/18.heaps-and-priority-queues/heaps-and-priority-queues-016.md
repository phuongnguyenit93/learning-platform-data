# So sánh cấu trúc theo nhu cầu decrease-key, meld và chi phí cấp phát

## 1. Chọn heap theo thao tác thật sự quan trọng

Giả sử bạn đang thiết kế một bộ điều phối tác vụ. Hệ thống phải lấy yêu cầu khẩn cấp nhất, nhưng đôi khi còn phải giảm mức ưu tiên của một yêu cầu, hủy công việc hoặc **gộp hai hàng đợi** từ hai nhóm xử lý.

Ở hệ thống khác, bạn cần một hàng đợi cho thuật toán Dijkstra: số lần **giảm khóa** (*decrease-key*) có thể lớn hơn rất nhiều số lần **lấy cực trị** (*extract-min*). Một hệ thống thứ ba chỉ thêm và lấy công việc, nhưng bị giới hạn bộ nhớ nghiêm ngặt.

Cả ba đều có thể gọi chung là “hàng đợi ưu tiên”, song **cấu trúc tốt nhất có thể khác nhau**.

Ví dụ:

| Hệ thống | Thao tác nổi bật | Câu hỏi quyết định |
|---|---|---|
| Tác vụ nền đơn giản | Nhiều `push`, `pop` | Mảng heap có đủ nhanh, ít bộ nhớ không? |
| Dijkstra/Prim có cập nhật trực tiếp | Rất nhiều `decrease-key` | Có handle để sửa khóa trong `O(1)` hay `O(\log n)`? |
| Điều phối nhiều hàng đợi con | Nhiều `meld` | Có nối được hai heap mà không duyệt toàn bộ phần tử? |
| Dịch vụ hủy nhiệm vụ theo ID | `remove(id)`, `change(id)` | Tìm đúng phần tử nhanh bằng cách nào? |
| Hàng đợi hàng triệu mục | Mọi thao tác, nhạy bộ nhớ | Có phải cấp phát một nút và nhiều con trỏ cho mỗi phần tử? |

**Điểm chính của bài:** không chỉ so sánh biểu thức Big-O trên giấy. Ta cần tính **tần suất thao tác**, **tiền điều kiện có handle/chỉ số**, **bảo đảm xấu nhất hay khấu hao**, **số lần cấp phát**, **tính cục bộ bộ nhớ** và chi phí duy trì các cấu trúc phụ trợ.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `decrease-key`, `insert`, `extract-min`, `delete`, `meld` và tra cứu theo ID.
2. So sánh heap nhị phân, heap d-nhánh, indexed heap, heap nhị thức, leftist/skew heap, Fibonacci heap và pairing heap.
3. Nêu đúng cận **trường hợp xấu nhất** và **khấu hao**, không nhập nhằng hai loại bảo đảm.
4. Giải thích tại sao một `decrease-key O(1)` theo handle không tự đồng nghĩa với `update(id) O(1)`.
5. Hiểu tại sao `meld` trên hai danh sách gốc có thể `O(1)` nhưng gộp hai bảng ID lại không.
6. Phân tích ảnh hưởng của mảng động, cấp phát nút, cache, GC và phân mảnh bộ nhớ.
7. Cài minh họa bằng Python một hàng đợi có cập nhật lười, một indexed heap và một leftist heap hỗ trợ gộp.
8. Thiết kế một phép đo công bằng và lựa chọn cấu trúc theo yêu cầu thực tế.

Đây là bài trong chương **Heap và hàng đợi ưu tiên** của học phần **Cấu trúc dữ liệu**. Học phần xây dựng tư duy về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị, đặc biệt là bất biến, thao tác, độ phức tạp thời gian và bộ nhớ để chọn cách biểu diễn phù hợp với bài toán.

## 2. Đặt cùng một hợp đồng trước khi so sánh

Để so sánh công bằng, ta xét **min-priority queue**: khóa **nhỏ hơn** mang ưu tiên **cao hơn**.

Các thao tác:

| Ký hiệu | Thao tác | Ý nghĩa |
|---|---|---|
| `insert(x,k)` | Thêm | Đưa phần tử `x` có khóa `k` vào hàng đợi |
| `find-min()` | Xem cực trị | Trả một phần tử có khóa nhỏ nhất, không xóa |
| `extract-min()` | Lấy cực trị | Trả và xóa một phần tử có khóa nhỏ nhất |
| `decrease-key(h,k')` | Giảm khóa | Đổi khóa phần tử được trỏ bởi **handle `h`**, với `k'\le k` |
| `delete(h)` | Xóa theo handle | Xóa đúng phần tử, không nhất thiết ở gốc |
| `meld(H_1,H_2)` | Gộp | Tạo heap chứa toàn bộ mục của cả hai heap |
| `change-key(h,k')` | Thay khóa bất kỳ | Có thể giảm **hoặc tăng**; không đồng nhất với decrease-key |

Trong API nghiệp vụ, người dùng có thể chỉ biết ID:

```text
change_priority("job-218", 1)
cancel("job-047")
```

Khi ấy còn thêm thao tác **`find_handle(id)`** hoặc **`find_position(id)`**. Chi phí tìm phần tử **phải được cộng vào** chi phí cập nhật.

### Các giả định phân tích

Trừ khi nói khác, ta giả định:

- Có `n` mục đang hoạt động; so sánh hai khóa kích thước cố định mất `O(1)`.
- Những heap cần handle được gọi với **handle hợp lệ**, không phải ID chưa định vị.
- Phân tích thao tác cấu trúc tách riêng chi phí cấp phát, GC và cấp phát lại của container.
- `meld` thuần thường là **gộp phá hủy nguồn**: sau thao tác, hai heap nguồn không còn dùng như hai tập chứa độc lập.
- Không có các thao tác đồng thời chưa được đồng bộ.

Nếu bỏ một trong các giả định ấy, kết luận Big-O có thể không còn phản ánh toàn bộ lời gọi trong hệ thống.

## 3. Đừng nhầm decrease-key với tìm kiếm hoặc tăng khóa

Cho min-heap:

```text
             2
           /   \
          5     3
         / \   / \
        9   7 8   4

Mảng: [2,5,3,9,7,8,4]
```

Nếu đã biết phần tử `7` ở chỉ số `4`, giảm nó xuống `1` làm vi phạm cạnh với cha `5`. Ta có thể **sift-up**:

```text
[2,5,3,9,1,8,4]
 -> [2,1,3,9,5,8,4]
 -> [1,2,3,9,5,8,4]
```

Binary heap mất `O(\log n)` bước sửa.

Nhưng nếu chỉ biết `id="C"` và chưa có bảng chỉ mục, phải **quét mảng** để tìm C, có thể mất `O(n)`. Sau đó mới đến phần sift-up `O(\log n)`:

\[
T_{\text{update theo ID}}
=T_{\text{định vị ID}}+T_{\text{sửa heap}}
=O(n)+O(\log n)=O(n).
\]

### Tăng khóa là bài toán khác

Trong min-heap, tăng khóa thường có thể làm vi phạm với **con**, nên cần **sift-down**. Một cấu trúc tối ưu cho `decrease-key` không nhất thiết hỗ trợ `increase-key` cùng chi phí.

Ví dụ Fibonacci heap có `decrease-key` `O(1)` **khấu hao** khi đã có handle, nhưng không có thao tác tăng khóa tổng quát cùng cận trong thiết kế kinh điển. Một giải pháp tăng khóa là **xóa phần tử rồi chèn lại**, có chi phí khấu hao `O(\log n)` do bước xóa.

**Quy tắc phân tích:** luôn nêu rõ là **decrease**, **increase** hay **change** hai chiều; và thao tác được gọi bằng **chỉ số**, **handle** hay **ID**.

## 4. “Nhanh” có ít nhất bốn nghĩa khác nhau

Khi nói một heap có `O(1)` hoặc `O(\log n)`, cần làm rõ loại bảo đảm.

### 4.1. Trường hợp xấu nhất (*worst-case*)

Mỗi lần gọi riêng lẻ được chặn bởi một cận, dưới các giả định mô hình. Ví dụ, `sift-up` trên binary heap có tối đa chiều cao `O(\log n)` lần hoán đổi.

### 4.2. Khấu hao (*amortized*)

Một lần gọi có thể đắt, nhưng **tổng chi phí trên một chuỗi thao tác** được chặn bởi tổng cận khấu hao tương ứng. Ví dụ, `decrease-key` của Fibonacci heap có `O(1)` khấu hao dù một lần gọi có thể cắt nhiều tổ tiên.

### 4.3. Kỳ vọng (*expected*)

Cận dựa trên giả định xác suất hoặc hiệu năng trung bình của một thành phần. Ví dụ, tra bảng băm `id\to index` thường được tính `O(1)` **kỳ vọng**. Không được tự ghi `O(1)` trường hợp xấu nhất cho một bảng băm tổng quát.

### 4.4. Độ trễ thực tế

Các cận trên không đo trực tiếp:

- Thời gian cấp phát và thu hồi bộ nhớ.
- Cache miss khi theo con trỏ.
- Chi phí GC.
- Tái cấp phát mảng động.
- Khóa đồng bộ và cạnh tranh giữa luồng.
- Chi phí so sánh khóa lớn.

Một cấu trúc có cận khấu hao tốt hơn **có thể chậm hơn** trên workload và phần cứng thật.

## 5. Binary heap: đường cơ sở đơn giản, thường rất mạnh

**Binary heap** là cây nhị phân hoàn chỉnh lưu trong mảng, với min-heap-order:

\[
H[parent(i)]\le H[i].
\]

Với chỉ số bắt đầu từ `0`:

\[
parent(i)=\left\lfloor\frac{i-1}{2}\right\rfloor,\quad
left(i)=2i+1,\quad right(i)=2i+2.
\]

### Các thao tác

- `find-min`: đọc `H[0]`, `O(1)`.
- `insert`: thêm cuối rồi sift-up, `O(\log n)` cho phần sửa heap.
- `extract-min`: đưa phần tử cuối lên gốc rồi sift-down, `O(\log n)`.
- `decrease-key` tại chỉ số đã biết: sift-up `O(\log n)`.
- `delete` tại chỉ số đã biết: thay bằng cuối, chọn sift-up hoặc sift-down, `O(\log n)`.
- `meld`: không có thao tác nối hai mảng mà tự duy trì heap-order trong `O(1)`. Có thể **nối các phần tử rồi heapify** trong `O(n_1+n_2)`.

### Vì sao binary heap thường nhanh ngoài thực tế?

- Một mảng liên tiếp, ít metadata.
- Các mục hoặc con trỏ tới mục có thể nằm gần nhau, có lợi cho cache.
- Không cần cấp phát **một nút liên kết riêng** cho mỗi phần tử trong thiết kế mảng.
- Thuật toán ngắn, dễ kiểm chứng, dễ dùng thư viện chuẩn như Python `heapq`.

**Giới hạn:** không tự tìm một ID bất kỳ. Một heap chỉ có `priority` và payload không biết công việc `C` đang ở ô nào sau các lần hoán đổi.

## 6. Indexed binary heap: trả thêm bộ nhớ để cập nhật theo ID

**Indexed heap** kết hợp mảng heap với bảng tra cứu:

```text
heap[index] -> (priority, id)
position[id] -> index
```

Bất biến:

\[
\forall i\in[0,n):\quad position[heap[i].id]=i.
\]

Mỗi lần hoán đổi `heap[i]` và `heap[j]` **phải cập nhật vị trí của cả hai ID**.

### Lợi ích

Nếu có ID và bảng băm `position`:

- Tra vị trí `O(1)` kỳ vọng.
- Giảm hoặc tăng khóa bằng sift-up/down `O(\log n)`.
- Xóa theo ID `O(\log n)` kỳ vọng, tính cả tra bảng.

Chi phí bổ sung:

- Bảng băm `O(n)` bộ nhớ ngoài mảng heap `O(n)`.
- Mỗi hoán đổi cần hai phép cập nhật ánh xạ.
- Phải kiểm soát ID duy nhất, vòng đời ID và ánh xạ khi xóa.

Nếu ID là số nguyên dày đặc trong một miền nhỏ `[0,U)`, có thể dùng **mảng `position[id]`** để tra cứu `O(1)` **trường hợp xấu nhất** khi ID hợp lệ, đổi lại dùng `O(U)` bộ nhớ, ngay cả khi chỉ `n\ll U` ID đang hoạt động.

**Đánh đổi:** indexed binary heap là một lựa chọn dễ dự đoán khi ứng dụng cần `decrease-key(id)` thường xuyên nhưng không cần `meld` tốc độ cao.

## 7. Heap d-nhánh: giảm chiều cao nhưng tăng số phép so sánh khi pop

**d-ary heap** mở rộng binary heap thành cây có tối đa `d\ge2` con trên mỗi nút, vẫn lưu bằng mảng.

Với chỉ số từ `0`:

\[
parent(i)=\left\lfloor\frac{i-1}{d}\right\rfloor,\qquad
child(i,k)=di+k\quad(1\le k\le d).
\]

Chiều cao với `d` cố định có cấp độ `\Theta(\log_d n)`.

### Đánh đổi cốt lõi

- **Sift-up:** mỗi tầng chỉ cần so với một cha, `O(\log_d n)`.
- **Sift-down:** mỗi tầng phải tìm con có khóa nhỏ nhất trong tối đa `d` con, `O(d\log_d n)`.
- **Bộ nhớ:** vẫn `O(n)` cho mảng; không phải cấp `d` con trỏ trên mỗi nút.
- **Meld:** khi lưu bằng mảng, vẫn thường cần nối và heapify lại `O(n_1+n_2)`.

Ví dụ với khoảng `65.536` phần tử:

| `d` | Chiều cao cây (cạnh) | Cận thô số so sánh sift-down `d\cdot h` |
|---:|---:|---:|
| 2 | 16 | 32 |
| 4 | 8 | 32 |
| 8 | 6 | 48 |
| 16 | 4 | 64 |

Cột cuối chỉ là **ước lượng cận theo chiều cao**, không phải benchmark. Số con thực tế ở tầng cuối có thể ít hơn `d`, và phần tử có thể dừng sớm.

**Nên cân nhắc d-ary heap khi** có nhiều lần giảm khóa (sift-up) so với lần lấy gốc, hoặc khi quét nhóm con liên tiếp trong mảng phù hợp với cache. Dù vậy, không có giá trị `d` tối ưu phổ quát.

## 8. Lazy insertion: bỏ yêu cầu decrease-key tại chỗ

Một cách khác là **không tìm và sửa mục cũ** khi giảm khóa:

1. Chèn một bản ghi mới với khóa tốt hơn.
2. Ghi nhận rằng bản ghi cũ đã lỗi thời (*stale*).
3. Khi pop, bỏ qua các bản ghi không còn hợp lệ.

Kỹ thuật này thường gọi là **lazy insertion** hoặc **lazy deletion** ở tầng ứng dụng, hay gặp khi dùng `heapq`.

### Ví dụ

```text
Ban đầu:
  A: priority=9, version=1

Cập nhật A xuống priority=3:
  bản ghi (9,1,A) vẫn nằm trong heap, nhưng stale
  bản ghi (3,2,A) mới được push

Khi pop:
  nếu phiên bản không khớp trạng thái hiện hành -> bỏ qua
```

Với `m` là số **bản ghi vật lý** trong heap (kể cả stale):

- Mỗi cập nhật bằng chèn mới: `O(\log(m+1))` thông dụng.
- Đánh dấu hủy trong bảng trạng thái: `O(1)` kỳ vọng nếu dùng bảng băm.
- Một lần pop nghiệp vụ có thể phải bỏ qua **nhiều** bản ghi stale, không có cận `O(\log n)` theo số mục còn hoạt động cho mọi lời gọi.
- Bộ nhớ heap có thể tăng theo **số phiên bản chưa được dọn**, chứ không chỉ số công việc hoạt động.

**Lợi ích:** code đơn giản, không cần duy trì `id\to index` qua mọi lần swap. **Giới hạn:** cập nhật dày đặc tạo nhiều bản ghi rác và công việc dọn ở các lần pop sau.

Không được nhầm kỹ thuật này với **tái cấu trúc lười của Fibonacci heap**, vốn giữ một nút logic và trì hoãn việc gộp các cây.

## 9. Heap nhị thức: kết cấu theo bậc giúp gộp có cấu trúc

**Binomial heap** chứa một tập các **cây nhị thức** có thứ tự heap. Ở trạng thái chuẩn, không có hai cây gốc cùng bậc.

Một cây nhị thức bậc `k` có `2^k` nút. Liên kết hai cây cùng bậc `k` bằng cách đặt gốc có khóa lớn hơn thành con của gốc nhỏ hơn tạo cây bậc `k+1`.

```text
Hai cây bậc 1:

    2       5
    |       |
    7       9

Ghép thành cây bậc 2:

       2
      / \
     7   5
         |
         9
```

### Vì sao meld tương đối nhanh?

Hợp nhất hai binomial heap giống phép **cộng nhị phân** các tập cây theo bậc: khi hai gốc cùng bậc, ghép chúng và có thể tạo “nhớ” sang bậc kế tiếp.

Vì số bậc hiện diện là `O(\log n)`:

- `meld`: `O(\log(n_1+n_2))` trong cài đặt chuẩn.
- `insert`: `O(\log n)` trường hợp xấu nhất khi hợp nhất với cây một nút; một số cách phân tích/biến thể có thể cho `O(1)` khấu hao.
- `extract-min`: `O(\log n)`; cần tìm gốc nhỏ nhất nếu không lưu sẵn con trỏ min, rồi gộp lại các cây con.
- `decrease-key` với handle và cơ chế bảo toàn danh tính phù hợp: `O(\log n)`.

Binomial heap phù hợp khi cần **meld thường xuyên** và muốn một cấu trúc có phân tích theo bậc tương đối quy củ, nhưng không đòi `meld O(1)`.

### Chú ý khi “đổi khóa bằng cách hoán đổi”

Một số mã binomial heap đẩy khóa nhỏ lên bằng cách **hoán đổi khóa hoặc dữ liệu** giữa nút con và nút cha. Nếu ứng dụng giữ `handle` trỏ tới **định danh công việc**, việc đổi payload giữa các nút có thể khiến handle trỏ tới **nút nhưng không còn là công việc cũ**.

Phải quyết định rõ handle đại diện cho **nút vật lý** hay **đối tượng logic**, rồi cập nhật bảng `id\to node` khi cần. Không thể chỉ ghi “decrease-key `O(\log n)`” mà bỏ qua tính đúng của định danh.

## 10. Leftist heap: đường phải ngắn để meld nhanh

**Leftist heap** là một heap liên kết bằng con trỏ, thường là cây nhị phân có bất biến:

1. Min-heap-order: khóa cha không lớn hơn khóa con.
2. **Leftist property:** `npl(left)\ge npl(right)` ở mọi nút.

`npl` (*null path length*) là độ dài ngắn nhất tới một nhánh rỗng theo một quy ước xác định. Dùng quy ước:

\[
npl(null)=-1,\quad
npl(leaf)=0,\quad
npl(x)=1+\min(npl(x.left),npl(x.right)).
\]

Vì nút có nhánh phải là nhánh có `npl` không lớn hơn nhánh trái, **đường đi chỉ theo con phải** bị chặn bởi `O(\log n)`.

### Meld là thao tác lõi

Để gộp hai leftist min-heap:

1. Giữ gốc có khóa nhỏ hơn làm gốc kết quả.
2. Gộp đệ quy **nhánh phải** của gốc ấy với heap còn lại.
3. Nếu cần, hoán đổi hai nhánh con để khôi phục leftist property.
4. Tính lại `npl`.

Chỉ đi theo các đường phải ngắn, nên:

\[
T_{\mathrm{meld}}=O(\log(n_1+n_2))
\]

trong trường hợp xấu nhất theo mô hình con trỏ.

`insert(x)` có thể xem là `meld` với heap một nút; `extract-min` xóa gốc rồi meld hai cây con. Cả hai có `O(\log n)` trường hợp xấu nhất.

**Hạn chế:** leftist heap không tự có một API `decrease-key` theo ID nhanh. Có thể cần handle và thông tin cha để cắt/sửa, hoặc dùng xóa/chèn hay lazy deletion với các cấu trúc phụ. Không được suy diễn từ `meld O(\log n)` rằng `decrease-key` bất kỳ cũng chắc chắn `O(\log n)` nếu chưa chỉ rõ thuật toán và cách giữ bất biến.

## 11. Skew heap: meld đơn giản hơn, bảo đảm chủ yếu là khấu hao

**Skew heap** cũng là heap liên kết tổ chức xoay quanh phép `meld`, nhưng thường **không lưu npl/rank** như leftist heap.

Trong cách triển khai kinh điển, sau khi gộp đệ quy, hai con của gốc có thể được đổi chỗ để tự điều chỉnh hình dạng. Không duy trì một bất biến hình dạng mạnh như leftist property.

- `meld` có **`O(\log(n_1+n_2))` khấu hao**.
- `insert` và `extract-min` suy ra từ meld, cũng có **`O(\log n)` khấu hao**.
- Một lần meld **riêng lẻ** có thể đi qua nhiều nút hơn cận logarithmic, vì đây là cận **khấu hao**.
- Không có `decrease-key O(1)` được bảo đảm chỉ vì là skew heap.

Skew heap đáng cân nhắc nếu **meld thường xuyên**, muốn code ít metadata hơn leftist heap và chấp nhận bảo đảm khấu hao thay vì cần cận xấu nhất chặt của từng lần meld.

## 12. Fibonacci heap: ưu tiên decrease-key và meld

**Fibonacci heap** là rừng các cây min-heap-order. Các gốc nối bằng danh sách liên kết đôi vòng; heap giữ một con trỏ tới gốc nhỏ nhất.

Nó cố ý **trì hoãn hợp nhất** các cây:

- **Insert:** đưa một nút thành gốc mới; không gom ngay.
- **Meld:** nối hai danh sách gốc; cập nhật con trỏ min.
- **Decrease-key:** nếu khóa mới nhỏ hơn khóa cha, cắt nút cùng cây con lên danh sách gốc; có thể **cắt dây chuyền** các tổ tiên đã được đánh dấu.
- **Extract-min:** chuyển các con của gốc nhỏ nhất thành gốc, rồi **consolidate** để không còn hai gốc cùng bậc.

### Cờ mark và bậc

Một nút không phải gốc có thể mất một con và được đánh dấu. Nếu nó mất thêm con khi vẫn ở dưới cùng cha, nó bị cắt ra làm gốc. Quy tắc ấy giữ một cận dưới liên quan tới số Fibonacci cho kích thước cây theo bậc:

\[
size(\text{cây gốc bậc }k)\ge F_{k+2}.
\]

Suy ra bậc lớn nhất `O(\log n)`, giúp `extract-min` sau hợp nhất còn `O(\log n)` gốc.

### Cận khấu hao

Hàm thế năng kinh điển:

\[
\Phi(H)=t(H)+2m(H),
\]

với `t(H)` là số gốc và `m(H)` là số nút đánh dấu. Các lần `insert` làm tăng thế năng; `extract-min` gom nhiều gốc làm giảm thế năng; cắt dây chuyền có thể được bù bằng việc xóa mark của các tổ tiên.

Do đó:

| Thao tác | Khấu hao trong Fibonacci heap thuần |
|---|---|
| `insert` | `O(1)` |
| `find-min` | `O(1)` |
| `meld` | `O(1)` |
| `decrease-key` với handle | `O(1)` |
| `extract-min` | `O(\log n)` |
| `delete` với handle | `O(\log n)` |

**Cực kỳ quan trọng:** `decrease-key` có thể cắt **nhiều** tổ tiên trong một lần gọi, và `extract-min` có thể phải hợp nhất rất nhiều gốc sau một chuỗi insert. Đây là cận **khấu hao**, không phải thời gian xấu nhất của mỗi lời gọi.

### Hạn chế thực tế

Một nút thường có `parent`, `child`, `left`, `right`, `degree`, `mark` và payload. So với mảng chứa khóa hoặc tham chiếu, đây là overhead lớn:

- Cấp phát nhiều nút riêng.
- Nhiều lần đọc/ghi con trỏ.
- Dữ liệu phân tán, ít thân thiện cache hơn.
- Mã phức tạp, cần kiểm soát handle và vòng đời.

Fibonacci heap có lợi thế lý thuyết khi có **rất nhiều decrease-key**, nhưng không mặc nhiên nhanh hơn `heapq` hoặc indexed d-ary heap trên các tải công việc nhỏ/vừa.

## 13. Pairing heap: meld gọn, nhưng decrease-key cần nêu đúng bảo đảm

**Pairing heap** là một heap cây liên kết có cấu trúc đơn giản hơn Fibonacci heap trong nhiều cách cài đặt.

### Ý tưởng

Phép `meld` hai min-heap:

1. So khóa hai gốc.
2. Gắn gốc khóa lớn hơn làm một con của gốc nhỏ hơn.

Với con trỏ thích hợp, thao tác liên kết gốc này tốn `O(1)` bước.

`extract-min` bỏ gốc, rồi gộp những cây con của nó, thường bằng chiến lược **two-pass pairing**:

```text
Các cây con: T1 T2 T3 T4 T5

Lượt 1 (theo cặp): meld(T1,T2), meld(T3,T4), còn T5
Lượt 2: gộp kết quả từ phải sang trái thành một heap
```

Với biến thể pairing heap hai lượt kinh điển, `delete-min` được phân tích với cận **`O(\log n)` khấu hao**.

### Điều phải nói cẩn thận về decrease-key

Nếu có handle và đủ liên kết để cắt một nút khỏi cây, bước sửa liên kết địa phương có thể đơn giản. **Nhưng không được tự kết luận `decrease-key O(1)` khấu hao cho mọi pairing heap**. Các cận lý thuyết phụ thuộc vào biến thể pairing heap, quy tắc liên kết/cắt và kết quả phân tích cụ thể.

Khi so sánh với Fibonacci heap:

- Pairing heap thường dễ cài hơn, ít metadata hơn.
- Thao tác meld gốc có thể `O(1)`.
- Hiệu năng thực tế có thể tốt trên nhiều workload.
- Không thể sao chép nguyên bảng cận Fibonacci heap sang pairing heap.

**Bài học phương pháp:** với cấu trúc có nhiều biến thể, hãy nêu **đúng biến thể và đúng cận đã được chứng minh**, không chỉ dựa vào tên gọi “heap”.

## 14. Cây tìm kiếm cân bằng: lựa chọn khác khi cần xóa/truy vấn phong phú

Một **cây tìm kiếm cân bằng** (chẳng hạn red-black tree hoặc AVL tree) có thể lưu phần tử theo khóa ghép:

\[
(\text{priority},\text{unique-id hoặc sequence}).
\]

Thao tác:

- Xem nhỏ nhất ở đầu thứ tự: `O(\log n)` nếu đi từ gốc đến nút nhỏ nhất, hoặc `O(1)` nếu cấu trúc duy trì con trỏ đầu.
- Thêm và xóa theo khóa: `O(\log n)` trường hợp xấu nhất cho cây cân bằng thông dụng.
- `change-key`: xóa khóa cũ và chèn khóa mới, `O(\log n)` nếu biết khóa/handle thích hợp.
- Duyệt theo thứ tự, tìm ngưỡng và tìm dải khóa: là khả năng tự nhiên của cây tìm kiếm.
- `meld` của hai cây tổng quát **không tự động `O(1)`**; cần thuật toán gộp đặc thù hoặc chèn lại các mục.

Nếu ứng dụng phải **truy vấn thứ tự toàn phần**, tìm những mục trong một khoảng priority hoặc xóa nhiều khóa cụ thể, cây tìm kiếm có thể phù hợp hơn một heap thuần.

Nhược điểm: nút liên kết, cân bằng và overhead bộ nhớ cũng cao hơn heap mảng đơn giản; và tính năng meld phụ thuộc cách cài/điều kiện phân hoạch khóa.

## 15. Bảng so sánh độ phức tạp: đọc cùng giả định

Các cận dưới đây áp dụng cho **min-priority queue**, `n` phần tử trước thao tác và `n_1,n_2` là kích thước hai heap khi gộp. “Đã biết mục” nghĩa là đã có **chỉ số/handle hợp lệ**. Các chi phí cấp phát/GC được phân tích riêng.

| Cấu trúc | `insert` | `extract-min` | `decrease-key` đã biết mục | `meld` thuần |
|---|---|---|---|---|
| Binary heap mảng | `O(\log n)` | `O(\log n)` | `O(\log n)` | `O(n_1+n_2)` bằng nối + heapify |
| Indexed binary heap | `O(\log n)` kỳ vọng với map băm | `O(\log n)` kỳ vọng | `O(\log n)` kỳ vọng | Thường `O(n_1+n_2)` để dựng lại mảng/map |
| d-ary heap, `d` cố định | `O(\log_d n)` | `O(d\log_d n)` | `O(\log_d n)` khi giảm min-key | `O(n_1+n_2)` bằng heapify |
| Binomial heap chuẩn | `O(\log n)` xấu nhất | `O(\log n)` | `O(\log n)` | `O(\log(n_1+n_2))` |
| Leftist heap | `O(\log n)` xấu nhất | `O(\log n)` xấu nhất | Không có API chuẩn trực tiếp được giả định | `O(\log(n_1+n_2))` xấu nhất |
| Skew heap | `O(\log n)` khấu hao | `O(\log n)` khấu hao | Phụ thuộc thiết kế thêm | `O(\log(n_1+n_2))` khấu hao |
| Fibonacci heap | `O(1)` khấu hao | `O(\log n)` khấu hao | `O(1)` khấu hao | `O(1)` khấu hao |
| Pairing heap hai lượt | `O(1)` thao tác liên kết gốc | `O(\log n)` khấu hao | Phụ thuộc biến thể, không mặc định `O(1)` khấu hao | `O(1)` thao tác liên kết gốc |
| Heap mảng + lazy versions | `O(\log m)` với `m` bản ghi vật lý | Có thể phải bỏ nhiều stale | Thay bằng `push`, `O(\log m)` | Không rẻ nếu phải hợp nhất mảng |

**Cách dùng bảng:**

- Cận `O(\log n)` cho binary heap là phần **khôi phục heap-order**; một lần thêm có thể chịu chi phí cấp phát lại mảng động. Thêm cuối thường `O(1)` **khấu hao**.
- Cột indexed dùng bảng băm để tra ID nên phát biểu **kỳ vọng**; dùng mảng vị trí theo ID nguyên có thể tránh kỳ vọng băm nếu miền ID hợp lệ.
- Cột Fibonacci chủ yếu là **khấu hao**. Một lần `extract-min` cụ thể có thể đắt hơn `O(\log n)` thực tế.
- `meld` thuần không tính việc gộp thêm hai bảng ID, thay đổi ID trùng hoặc tái cấp phát bộ nhớ cho lớp bao.
- Không đánh đồng “một bước liên kết gốc `O(1)`” với “mọi thao tác decrease-key của pairing heap đều có cận khấu hao `O(1)`”.
- Trong hàng lazy, `m` có thể lớn hơn số `n` công việc đang hoạt động rất nhiều.

## 16. Cấp phát mảng động: ít nút, nhưng có lúc phải sao chép

Heap mảng lưu phần tử trong một vùng liên tiếp hoặc một mảng động các **tham chiếu** tới phần tử. Khi hết sức chứa, mảng động thường:

1. Cấp phát một vùng mới lớn hơn.
2. Chuyển hoặc sao chép các ô tham chiếu/phần tử.
3. Giải phóng vùng cũ khi không còn dùng.

Ví dụ:

```text
capacity=8, size=8:
[a b c d e f g h]

push(i) có thể buộc tăng capacity:
[a b c d e f g h i _ _ _ ...]
```

Một lần `append` riêng lẻ có thể tốn `O(n)` công di chuyển ô nếu có tái cấp phát. Nhưng với chính sách tăng sức chứa theo tỷ lệ, **tổng chi phí cấp phát lại trên nhiều lần append** được phân bổ để mỗi `append` có `O(1)` **khấu hao**.

Tổng `push` binary heap thường được mô tả `O(\log n)` khấu hao khi tính cả append động theo mô hình này, do phần sift-up mất `O(\log n)`.

### Cần phân biệt hai loại “di chuyển”

- Mảng của các **giá trị nhỏ**: có thể phải sao chép trực tiếp nhiều giá trị.
- Mảng của các **con trỏ/tham chiếu**: vùng mảng chứa tham chiếu đổi vị trí, nhưng đối tượng được trỏ tới không nhất thiết bị di chuyển theo.

Đối tượng Python trong một `list` thường được giữ thông qua các tham chiếu. Tái cấp phát vùng chứa tham chiếu không đồng nghĩa mỗi object Python bên dưới phải được tạo lại.

**Hệ quả:** với `n` rất lớn, mảng động có thể chịu một số lần tái cấp phát đắt, nhưng đa số thao tác vẫn hưởng lợi từ truy cập vùng nhớ liên tục.

## 17. Chi phí cấp phát từng nút: con trỏ và phân mảnh

Các heap liên kết như binomial, leftist, skew, pairing và Fibonacci thường tạo một **nút riêng** cho mỗi phần tử.

Một nút Fibonacci điển hình có thể giữ:

```text
key
payload / handle / id
parent pointer
child pointer
left sibling pointer
right sibling pointer
degree
mark
```

Trong khi đó, một heap mảng có thể chỉ cần:

```text
array of keys
hoặc
array of pointers to payload
```

### Các loại chi phí thực tế

**1. Cấp phát riêng:** tạo mỗi nút có thể đi qua bộ cấp phát nhiều lần; cấp phát thường xuyên gây overhead và cạnh tranh tài nguyên.

**2. Metadata:** bốn con trỏ, degree và mark có thể tăng đáng kể số byte trên mỗi mục, cộng chi phí căn chỉnh của object/runtime.

**3. Phân mảnh:** những nút sống lâu và chết xen kẽ có thể để lại vùng nhớ khó sử dụng tối ưu.

**4. Pointer chasing:** khi thao tác qua `parent`/`child`/`left`/`right`, CPU có thể phải theo con trỏ tới vị trí xa; cache miss và TLB miss có thể tăng.

**5. Bộ thu gom rác:** runtime có GC có thể phải duyệt nhiều object/liên kết hơn; các vòng liên kết cũng ảnh hưởng cách quản lý vòng đời.

**6. Giải phóng:** khi pop/delete, phải quản lý tính hợp lệ của các handle đang trỏ tới nút; tránh dùng sau khi xóa.

**Không có công thức Big-O chung** biến số lượng con trỏ thành một số mili-giây nhất định. Cần đo trên runtime và cấu hình bộ nhớ thực tế.

## 18. Tại sao cache locality có thể quan trọng hơn một hệ số log?

Một CPU thường truy cập **một dòng cache** chứa nhiều byte dữ liệu liên tiếp. Vì vậy:

- Với heap mảng, các con của một nút d-ary thường nằm trong một **đoạn liên tiếp**.
- Với heap liên kết, các nút con có thể được cấp phát ở những địa chỉ khác nhau.
- Một phép so sánh khóa đơn giản rất rẻ nếu dữ liệu đã nằm trong cache, nhưng đắt hơn nhiều nếu phải chờ tải bộ nhớ.

### Ví dụ minh họa, không phải benchmark

Giả sử một ứng dụng có một triệu mục, mỗi mục heap mảng chỉ lưu một tham chiếu `8` byte trong một hệ thống 64-bit. Riêng vùng tham chiếu liên tiếp có quy mô **xấp xỉ `8` MB**, chưa tính payload, dung lượng dự phòng và metadata.

Nếu một heap liên kết lưu thêm bốn con trỏ kích thước `8` byte mỗi nút, riêng bốn trường ấy đã tương đương **`32` MB** với một triệu nút, chưa tính key, payload, bậc, mark, căn chỉnh và overhead cấp phát.

Đây là **ước lượng dung lượng các trường**, không phải số đo footprint của một thư viện hay ngôn ngữ cụ thể. Các runtime có thể tổ chức object rất khác nhau.

### Quy tắc thực hành

Khi hai phương án có thời gian tiệm cận gần nhau:

1. Đo tổng bộ nhớ cư trú, số object/nút và dung lượng peak.
2. Đo số lần cấp phát, thời gian cấp phát/giải phóng.
3. Quan sát cache miss hoặc CPU counters nếu có công cụ.
4. Đo độ trễ từng thao tác **cũng như** throughput toàn chuỗi.

Vì lý do này, một indexed binary heap có `decrease-key O(\log n)` thường có thể cạnh tranh rất tốt với Fibonacci heap `O(1)` khấu hao trên khối lượng thực tế.

## 19. Object pool và arena: giảm cấp phát nhưng không xóa hết đánh đổi

Một cách tối ưu heap liên kết là dùng **pool/arena allocator**:

- Cấp một khối chứa nhiều nút.
- Tái sử dụng các nút đã được giải phóng.
- Cấp phát từng nút từ pool thay vì gọi allocator tổng quát mỗi lần.
- Bố trí các nút gần nhau hơn để cải thiện locality nếu khả thi.

Ưu điểm: giảm số lần cấp phát tổng quát, có thể giảm phân mảnh và cải thiện tính dự đoán.

Nhưng vẫn cần chú ý:

- Pool có thể giữ **dung lượng chưa dùng** và tăng peak memory.
- Các con trỏ nội bộ vẫn tồn tại, cùng logic bảo trì chúng.
- Handle trỏ tới ô đã được tái sử dụng có nguy cơ **ABA**: nút cũ bị xóa, vị trí được gán cho một đối tượng mới.
- Nếu pool muốn **di chuyển nút** để nén bộ nhớ, phải có cơ chế cập nhật tất cả con trỏ/handle, hoặc dùng indirection.
- Pool dùng chung nhiều luồng cần thiết kế đồng bộ hoặc phân vùng theo luồng.

Một handle dạng `(slot,generation)` có thể tránh việc sự kiện cũ vô tình tác động vào mục mới dùng lại cùng slot.

**Kết luận:** pool có thể cải thiện phần cấp phát, nhưng không tự biến Fibonacci heap thành một mảng liên tiếp hay giải quyết các vấn đề handle/GC.

## 20. Gộp hai heap: API thuần và hệ thống có ID là hai bài toán

`meld(H_1,H_2)` thường được hiểu là tạo một heap chứa toàn bộ phần tử của hai heap, **không** duy trì hai heap nguồn độc lập.

### 20.1. Binary heap mảng

Có thể lấy hai mảng và xây một mảng hợp nhất:

```python
import heapq


def merge_numeric_heaps(a: list[int], b: list[int]) -> list[int]:
    merged = a + b
    heapq.heapify(merged)
    return merged


a = [2, 5, 3]  # Min-heap hợp lệ.
b = [1, 7, 4]  # Min-heap hợp lệ.
result = merge_numeric_heaps(a, b)

assert result[0] == 1
print([heapq.heappop(result) for _ in range(len(result))])
# [1, 2, 3, 4, 5, 7]
```

Nối mảng rồi `heapify` tốn `O(n_1+n_2)` thời gian; phiên bản tạo `a+b` còn cấp một mảng kết quả mới `O(n_1+n_2)` ô, ngoài hai mảng nguồn đang tồn tại.

### 20.2. Heap có hỗ trợ meld tự nhiên

- Leftist heap: gộp theo các đường phải ngắn, `O(\log(n_1+n_2))` xấu nhất.
- Skew heap: `O(\log(n_1+n_2))` khấu hao.
- Binomial heap: `O(\log(n_1+n_2))` với hợp nhất theo bậc.
- Fibonacci heap: nối root list `O(1)` trên cấu trúc thuần.
- Pairing heap: liên kết hai gốc `O(1)`.

### 20.3. Nhưng ứng dụng còn có bảng tra cứu ID

Giả sử mỗi heap có:

```text
heap_data
id_to_handle hoặc id_to_index
```

Nếu gộp hai heap mảng có bảng vị trí, hầu hết vị trí có thể thay đổi sau `heapify`, nên cần **xây lại ánh xạ `id\to index`**.

Nếu gộp hai Fibonacci heap có bảng `id\to node`, nối hai root list chỉ `O(1)`, nhưng còn phải:

- Quyết định bảng ID hợp nhất đặt ở đâu.
- Kiểm tra ID trùng và quy tắc xử lý xung đột.
- Gộp các mục của hai bảng nếu muốn tra cứu trong **một** bảng mới.
- Chuyển quyền sở hữu handle và ngăn heap nguồn sửa tiếp các nút đã chuyển.

Việc gộp bảng có thể cần `\Omega(n_1+n_2)` công việc nếu thực sự phải tạo một bảng độc lập mới chứa tất cả các mục. Một thiết kế giữ nhiều bảng/phân vùng có thể trì hoãn hoặc thay đổi chi phí, nhưng lại phát sinh chi phí lookup và quản lý owner.

**Không được quảng bá `meld O(1)` của heap thuần như một bảo đảm `mergeQueues O(1)` của toàn bộ dịch vụ.**

## 21. Tính ổn định và comparator cũng ảnh hưởng phép meld

Hai heap chỉ nên gộp trực tiếp khi chúng dùng **thứ tự so sánh tương thích**:

- Cả hai là min-heap hoặc cùng một chính sách thứ tự.
- Cùng tiêu chí priority và quy tắc hòa.
- Không trộn comparator bất nhất như một heap dùng deadline tăng dần, heap kia dùng deadline giảm dần.

### Hai heap cùng dùng sequence từ 0 có thể đụng nhau

Ví dụ:

```text
H1: (priority=2, sequence=0, A)
H2: (priority=2, sequence=0, B)
```

Nếu sequence chỉ duy nhất **trong từng heap**, sau meld hai khóa có thể hòa nhau, và “FIFO toàn cục” chưa được xác định.

Giải pháp tùy nghiệp vụ:

1. Cấp sequence từ **cùng một nguồn duy nhất** ngay từ đầu.
2. Dùng khóa có tie-breaker toàn cục `(priority, arrival, source_id, local_sequence)` nếu hợp đồng định nghĩa rõ.
3. Xác định thứ tự meld và **đánh số lại** những mục cần tái lập thứ tự toàn cục; việc này có chi phí duyệt nút, không còn `O(1)`.

Nếu nhiều máy enqueue đồng thời, phải xác định “đến trước” nghĩa là thứ tự log, thứ tự bộ cấp ticket hoặc một quy tắc sắp thứ tự khác. Heap không tự giải quyết vấn đề trật tự phân tán.

## 22. Mô hình tổng chi phí theo workload

Gọi:

- `I`: số lần thêm.
- `X`: số lần lấy cực trị.
- `D`: số lần giảm khóa.
- `M`: số lần gộp heap.
- `Q`: số lần tìm phần tử theo ID hoặc thực hiện xóa/cập nhật ID.
- `A`: số lần cấp phát/thu hồi hoặc chi phí cấp phát tích lũy.

Một mô hình khái niệm:

\[
C_{\mathrm{total}}
\approx I\,c_{\mathrm{insert}}
+X\,c_{\mathrm{extract}}
+D\,c_{\mathrm{decrease}}
+M\,c_{\mathrm{meld}}
+Q\,c_{\mathrm{lookup}}
+C_{\mathrm{allocate}}
+C_{\mathrm{cache/GC}}.
\]

Các `c` là chi phí trung bình **trên đúng workload** hoặc hệ số mô hình, không phải số đo mặc định của bất kỳ ngôn ngữ nào.

### Áp dụng cận tiệm cận

Với indexed binary heap:

\[
C_{\mathrm{heap}}=
O((I+X+D)\log(n+1))
\]

trong mô hình độ dài heap đại diện và tra bảng băm `O(1)` kỳ vọng, **chưa tính meld**.

Với indexed d-ary heap, `d` cố định:

\[
C_{\mathrm{heap}}=
O((I+D)\log_d(n+1)+Xd\log_d(n+1)).
\]

Với Fibonacci heap thuần có sẵn handle:

\[
C_{\mathrm{heap,amortized}}
=O(I+D+X\log(n+1)+M),
\]

với quy ước `M` là số phép meld thuần.

Các công thức cho biết **xu hướng**: khi `D` áp đảo `X`, Fibonacci heap có lợi thế lý thuyết; khi `M` áp đảo, heap liên kết có thao tác meld tốt đáng xem xét. Tuy nhiên, chi phí cấp phát và bảng ID có thể làm thứ tự lựa chọn thực tế khác đi.

## 23. Tình huống A: rất nhiều decrease-key trong Dijkstra

Giả sử đồ thị có:

- `V` đỉnh.
- `E` cạnh với trọng số **không âm**.
- Mỗi đỉnh có một bản ghi đang hoạt động trong hàng đợi và có handle/chỉ số định vị.

Trong Dijkstra:

- Có `O(V)` lần `extract-min`.
- Có tối đa `O(E)` lần cải thiện khoảng cách dẫn tới `decrease-key`.

### Indexed binary heap

\[
O((V+E)\log V).
\]

### Indexed d-ary heap

\[
O(Vd\log_d V+E\log_d V)
\]

với `d` cố định và phân tích phần thao tác heap.

### Fibonacci heap

\[
O(V\log V+E)
\]

khấu hao cho thao tác hàng đợi.

### Ví dụ có nhiều cạnh

Nếu `E\gg V`, hệ số logarithm nhân với phần lớn số lần giảm khóa của binary heap có thể tạo khoảng cách lý thuyết đáng kể so với Fibonacci heap.

Nhưng phải tính:

- Bảng `vertex\to node` hoặc mảng `position[vertex]`.
- Chi phí cấp phát/giải phóng nút.
- Cache locality của adjacency list và heap.
- Số lần **giảm khóa thành công** có thể ít hơn `E`.

**Điều kiện quan trọng:** heap Fibonacci không làm Dijkstra đúng với cạnh âm. Bảo đảm thuật toán đường đi phụ thuộc điều kiện trọng số không âm, độc lập với loại heap.

## 24. Tình huống B: rất nhiều meld nhưng ít cập nhật khóa

Một ứng dụng mô phỏng chạy các tiến trình con. Mỗi tiến trình có một hàng đợi sự kiện; khi hợp nhất tiến trình, hai hàng đợi phải được gộp.

```text
Run-1 events: heap H1
Run-2 events: heap H2
Merge process -> H = meld(H1, H2)
```

Nếu phải gộp rất nhiều lần:

- Mảng heap có thể lặp lại việc **nối và heapify** nhiều lần.
- Leftist/skew/binomial heap tránh phải chép toàn bộ mỗi lần meld, với cận logarithmic.
- Fibonacci/pairing heap có phép nối gốc rất rẻ.

### Nhưng kiểm tra ba điều trước khi chọn

1. **Meld thực sự thường xuyên?** Nếu chỉ gộp một lần sau khi mọi dữ liệu sẵn sàng, nối mảng rồi heapify `O(n)` có thể rất tốt và đơn giản.
2. **Có phải chuyển ownership và ID?** Nếu cần hợp nhất bảng định danh, chi phí thực tế có thể vẫn tuyến tính.
3. **Có yêu cầu giữ ổn định toàn cục?** Nếu hai nguồn dùng sequence riêng, có thể phải giải quyết tie-breaker hoặc đánh số lại.

Vì vậy, “nhiều meld” là một tín hiệu, **không phải kết luận tự động** rằng Fibonacci heap luôn tốt nhất.

## 25. Tình huống C: hàng đợi chỉ thêm/lấy, nhạy bộ nhớ

Một máy chủ quản lý hàng triệu yêu cầu; mỗi yêu cầu chỉ được thêm một lần và lấy một lần. Hầu như không có `decrease-key` hoặc `meld`.

Lựa chọn thực tế đáng cân nhắc đầu tiên thường là **binary heap mảng**:

- Code ngắn, có sẵn trong thư viện.
- Một vùng tham chiếu/khóa liên tục.
- Ít metadata mỗi mục.
- `push/pop` `O(\log n)` và cache locality tốt.

Fibonacci heap không khai thác được lợi thế decrease-key nếu **không có decrease-key**. Trong khi đó, các nút liên kết gây nhiều allocation và overhead.

Một benchmark có thể đo:

| Chỉ số | Ý nghĩa |
|---|---|
| Throughput `push/pop` | Số thao tác mỗi giây trên một chuỗi tương ứng workload |
| p50/p95/p99 latency | Độ trễ điển hình và độ trễ đuôi của từng loại thao tác |
| Peak memory | Dung lượng cực đại khi heap lớn |
| Allocations per operation | Số lượt cấp phát mỗi thao tác |
| GC time | Thời gian thu gom rác nếu runtime có GC |
| Cache misses | Chi phí đọc dữ liệu từ cấp bộ nhớ chậm |

Không nên chọn heap liên kết chỉ vì `insert O(1)` khấu hao khi phần lớn chi phí thời gian và bộ nhớ đến từ cấp phát và `extract-min`.

## 26. Tình huống D: cần deadline cứng và độ trễ dự đoán được

Trong hệ thống thời gian thực, vấn đề không chỉ là throughput hay tổng thời gian **khấu hao**.

Một lần `extract-min` của Fibonacci heap có thể phải hợp nhất rất nhiều gốc sau một chuỗi insert, dù chi phí khấu hao của nó chỉ `O(\log n)`. Nếu deadline của **mỗi** lần pop quan trọng, độ trễ một lần gọi như vậy có thể là rủi ro.

Một số nguyên tắc:

- Ưu tiên cấu trúc có cận **trường hợp xấu nhất** rõ ràng cho thao tác quan trọng.
- Kiểm soát chính sách cấp phát (có thể cấp phát trước hoặc dùng pool).
- Tránh các chu kỳ GC không thể dự đoán nếu hệ thống không cho phép.
- Đo **độ trễ đuôi**, không chỉ trung bình.
- Nếu dùng cấu trúc có cận khấu hao, phải chứng minh thời gian một lần gọi vẫn phù hợp deadline, hoặc dùng biến thể/cơ chế phân bổ công việc khác.

**Cẩn thận:** ngay cả binary heap với `O(\log n)` phép so sánh cũng không tự có deadline cứng nếu mỗi lần gọi có thể kích hoạt cấp phát mảng động, page fault hoặc lock contention. Bảo đảm thời gian thực đòi phân tích cả **hệ thống thực thi**, không chỉ heap-order.

## 27. Cài Python: binary heap với cập nhật lười và version

Để có ví dụ chạy được và minh họa đánh đổi một cách rõ ràng, lớp sau dùng `heapq` kết hợp:

- Bảng `active[id]` cho khóa và phiên bản mới nhất.
- Một số thứ tự `arrival` cố định để giữ FIFO khi priority bằng nhau.
- Một số `version` mới mỗi lần cập nhật để nhận diện stale.

Không cần biết chỉ số vật lý của mục trong heap.

```python
import heapq
from itertools import count


class LazyMinQueue:
    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int, str]] = []
        self._active: dict[str, tuple[int, int, int]] = {}
        self._arrival = count()
        self._version = count()

    def __len__(self) -> int:
        return len(self._active)

    def push(self, job_id: str, priority: int) -> None:
        if job_id in self._active:
            raise ValueError("ID đang hoạt động")
        arrival = next(self._arrival)
        version = next(self._version)
        self._active[job_id] = (priority, arrival, version)
        heapq.heappush(
            self._heap, (priority, arrival, version, job_id)
        )

    def change_priority(self, job_id: str, priority: int) -> None:
        _, arrival, _ = self._active[job_id]
        version = next(self._version)
        self._active[job_id] = (priority, arrival, version)
        heapq.heappush(
            self._heap, (priority, arrival, version, job_id)
        )

    def cancel(self, job_id: str) -> None:
        del self._active[job_id]

    def pop(self) -> tuple[str, int]:
        while self._heap:
            p, arrival, version, job_id = heapq.heappop(self._heap)
            if self._active.get(job_id) == (p, arrival, version):
                del self._active[job_id]
                return job_id, p
        raise IndexError("Không còn công việc hợp lệ")

    def physical_size(self) -> int:
        # Bao gồm các mục lỗi thời chưa được dọn.
        return len(self._heap)


q = LazyMinQueue()
q.push("A", 8)
q.push("B", 3)
q.change_priority("A", 1)
q.cancel("B")

print(len(q))            # 1: một công việc đang hoạt động.
print(q.physical_size()) # 3: nhiều bản ghi vật lý.
print(q.pop())           # ('A', 1)
```

**Quan sát:** `cancel` chỉ sửa bảng băm, nhưng các bản ghi cũ chưa được thu hồi khỏi heap. Số thao tác heap thực tế trong `pop` phụ thuộc số stale ở đầu; vì vậy phải tính `m=physical_size()` khi phân tích bộ nhớ và độ trễ.

Nếu dùng lâu dài, có thể **lọc bản ghi còn hiệu lực** rồi gọi `heapq.heapify` một lần; công xây lại thường `O(m)` tại thời điểm dọn.

## 28. Cài Python: indexed min-heap sửa khóa tại chỗ

Nếu cập nhật theo ID thường xuyên và cần **xóa vật lý ngay**, một indexed heap tránh tích lũy stale.

Mã sau dùng `(priority,sequence,id)` để giữ thứ tự đến, nhưng so sánh chỉ hai trường đầu. Bảng `pos` được đồng bộ khi đổi chỗ.

```python
from itertools import count


class IndexedMinQueue:
    def __init__(self) -> None:
        self._heap: list[tuple[int, int, str]] = []
        self._pos: dict[str, int] = {}
        self._seq = count()

    def __len__(self) -> int:
        return len(self._heap)

    def _key(self, i: int) -> tuple[int, int]:
        priority, sequence, _ = self._heap[i]
        return priority, sequence

    def _swap(self, i: int, j: int) -> None:
        self._heap[i], self._heap[j] = self._heap[j], self._heap[i]
        self._pos[self._heap[i][2]] = i
        self._pos[self._heap[j][2]] = j

    def _up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._key(parent) <= self._key(i):
                break
            self._swap(parent, i)
            i = parent

    def _down(self, i: int) -> None:
        n = len(self._heap)
        while True:
            left = 2 * i + 1
            if left >= n:
                break
            right = left + 1
            best = left
            if right < n and self._key(right) < self._key(left):
                best = right
            if self._key(i) <= self._key(best):
                break
            self._swap(i, best)
            i = best

    def _repair(self, i: int) -> None:
        if i > 0 and self._key(i) < self._key((i - 1) // 2):
            self._up(i)
        else:
            self._down(i)

    def push(self, job_id: str, priority: int) -> None:
        if job_id in self._pos:
            raise ValueError("ID đang hoạt động")
        i = len(self._heap)
        self._heap.append((priority, next(self._seq), job_id))
        self._pos[job_id] = i
        self._up(i)

    def change_priority(self, job_id: str, priority: int) -> None:
        i = self._pos[job_id]  # KeyError nếu không tồn tại.
        _, sequence, _ = self._heap[i]
        self._heap[i] = (priority, sequence, job_id)
        self._repair(i)

    def _remove_at(self, i: int) -> tuple[str, int]:
        removed = self._heap[i]
        last = self._heap.pop()
        del self._pos[removed[2]]
        if i < len(self._heap):
            self._heap[i] = last
            self._pos[last[2]] = i
            self._repair(i)
        return removed[2], removed[0]

    def cancel(self, job_id: str) -> tuple[str, int]:
        return self._remove_at(self._pos[job_id])

    def pop(self) -> tuple[str, int]:
        if not self._heap:
            raise IndexError("Hàng đợi rỗng")
        return self._remove_at(0)

    def peek(self) -> tuple[str, int]:
        if not self._heap:
            raise IndexError("Hàng đợi rỗng")
        p, _, job_id = self._heap[0]
        return job_id, p


q = IndexedMinQueue()
q.push("A", 8)
q.push("B", 3)
q.push("C", 4)
q.change_priority("A", 1)

print(q.pop())         # ('A', 1)
print(q.cancel("C"))   # ('C', 4)
print(q.pop())         # ('B', 3)
print(len(q))          # 0
```

### So với lớp lazy

| Thuộc tính | `LazyMinQueue` | `IndexedMinQueue` |
|---|---|---|
| Cập nhật `A` | Thêm bản ghi mới, cũ thành stale | Sửa bản ghi hiện tại |
| Hủy `A` | Xóa trạng thái active | Xóa vật lý ngay |
| Tìm vị trí heap theo ID | Không cần | Bảng `pos[id]` |
| Bảng phụ | `active` với version | `pos` với chỉ số |
| Số bản ghi trong heap | Có thể lớn hơn số ID hoạt động | Đúng bằng số ID hoạt động |
| Độ phức tạp cập nhật | `O(\log m)` | `O(\log n)` kỳ vọng tính cả map |
| Chi phí pop | Có thể bỏ nhiều stale | Một lần sửa heap `O(\log n)` |
| Bộ nhớ bổ sung | Lưu các stale chưa dọn | Bảng vị trí `O(n)` |

Không nên sửa trực tiếp `_heap` của indexed heap từ bên ngoài; một swap không cập nhật `_pos` có thể khiến lần đổi khóa sau sửa nhầm công việc.

## 29. Cài Python: leftist heap hỗ trợ meld

Ví dụ sau cho thấy một heap **liên kết** xử lý phép gộp bằng cách sửa con trỏ, không nối mảng rồi heapify.

Ta dùng quy ước `npl(None)=-1` và `npl(leaf)=0`; lớp chỉ hỗ trợ khóa số nguyên và các thao tác **push, peek, pop, meld**. Không tuyên bố hỗ trợ `decrease-key` theo ID.

```python
from dataclasses import dataclass


@dataclass
class LeftistNode:
    key: int
    left: "LeftistNode | None" = None
    right: "LeftistNode | None" = None
    npl: int = 0


def npl(node: LeftistNode | None) -> int:
    return -1 if node is None else node.npl


def merge_nodes(
    a: LeftistNode | None,
    b: LeftistNode | None,
) -> LeftistNode | None:
    if a is None:
        return b
    if b is None:
        return a

    if b.key < a.key:
        a, b = b, a

    # Gốc nhỏ hơn giữ vai trò cha, gộp phía phải.
    a.right = merge_nodes(a.right, b)

    if npl(a.left) < npl(a.right):
        a.left, a.right = a.right, a.left
    a.npl = 1 + npl(a.right)
    return a


class LeftistMinHeap:
    def __init__(self) -> None:
        self.root: LeftistNode | None = None
        self.size = 0

    def __len__(self) -> int:
        return self.size

    def push(self, value: int) -> None:
        self.root = merge_nodes(self.root, LeftistNode(value))
        self.size += 1

    def peek(self) -> int:
        if self.root is None:
            raise IndexError("Heap rỗng")
        return self.root.key

    def pop(self) -> int:
        if self.root is None:
            raise IndexError("Heap rỗng")
        result = self.root.key
        self.root = merge_nodes(self.root.left, self.root.right)
        self.size -= 1
        return result

    def meld(self, other: "LeftistMinHeap") -> None:
        if self is other:
            raise ValueError("Không gộp heap với chính nó")
        self.root = merge_nodes(self.root, other.root)
        self.size += other.size
        other.root = None
        other.size = 0  # Chuyển quyền sở hữu toàn bộ nút.


a = LeftistMinHeap()
b = LeftistMinHeap()
for x in [7, 3, 11]:
    a.push(x)
for x in [8, 1, 5]:
    b.push(x)

a.meld(b)
print(len(a), len(b))  # 6 0
print([a.pop() for _ in range(len(a))])
# [1, 3, 5, 7, 8, 11]
```

### Điều cần quan sát

- `meld` không yêu cầu duyệt toàn bộ phần tử để cấp một mảng mới.
- Các nút được **tái sử dụng**, chỉ thay liên kết trong những đường được đi qua.
- `npl(left)\ge npl(right)` được sửa sau mỗi lần gộp nhánh.
- Gộp hai heap dùng **ownership phá hủy nguồn**: `b` trở thành rỗng.
- Mỗi `push` vẫn tạo **một nút**; đây là nơi overhead allocator xuất hiện.

Phiên bản dùng đệ quy để ngắn gọn. Độ sâu lời gọi do chiều dài đường phải quyết định, `O(\log n)` với leftist property; cần tính bộ nhớ ngăn xếp **`O(\log n)`**, không tự ghi `O(1)` bộ nhớ phụ cho bản cài đặt đệ quy này.

## 30. Cách benchmark các heap mà không thiên vị

Một kết luận có ý nghĩa cần dựa trên **cùng workload và cùng hợp đồng**.

### 30.1. Định nghĩa tập thao tác

Ví dụ:

```text
Tập A:
  100.000 push
  100.000 pop
  0 decrease-key
  0 meld

Tập B:
  20.000 push
  300.000 decrease-key
  20.000 pop
  0 meld

Tập C:
  Nhiều heap nhỏ được tạo riêng
  50.000 meld giữa các heap
  Sau đó pop hết các mục
```

Đây là **ví dụ thiết kế workload**, không phải số đo thực nghiệm. Cần tránh tạo các thao tác vô nghĩa (như giảm khóa trên mục đã bị xóa).

### 30.2. Chuẩn hóa chức năng

Nếu so indexed heap với heap Fibonacci:

- Cả hai phải nhận **cùng ID** và cập nhật **đúng phần tử**.
- Nếu một bên giữ bảng ID, bên kia cũng phải tính **chi phí tạo/duy trì handle**.
- Cùng quy tắc khi priority bằng nhau, hoặc bỏ yêu cầu ổn định cho cả hai.
- Các heap đã meld phải chuyển ownership theo cùng hợp đồng.
- Cùng số mục hoạt động và cùng dữ liệu đầu vào.

Không công bằng nếu một bên được đưa **handle sẵn**, còn bên kia phải quét mảng tìm ID.

### 30.3. Đo nhiều lớp chi phí

| Chỉ số đo | Điều cần hiểu |
|---|---|
| Tổng thời gian | Hệ thống hoàn tất cùng workload nhanh đến đâu |
| Độ trễ từng thao tác | `push`, `pop`, `decrease`, `meld` đắt ở đâu |
| p95/p99 | Có các lần pop hoặc cấp phát bất thường không |
| Tổng cấp phát | Số allocation và byte được cấp |
| Peak memory | Phân mảnh, metadata và stale ảnh hưởng ra sao |
| Cache misses | Pointer chasing hay quét mảng chi phối |
| Số so sánh khóa | Tách chi phí thuật toán khỏi overhead runtime |
| Tính đúng | Mỗi lần pop và sửa ID trả đúng kết quả |

Nên có giai đoạn warm-up phù hợp, nhiều lần chạy, cố định hoặc ghi rõ cấu hình máy/runtime và tránh đo chung việc tạo dữ liệu đầu vào nếu không thuộc thao tác cần so.

### 30.4. Không chạy benchmark chỉ để xác nhận Big-O

Một phép đo nhỏ không thể chứng minh cận tiệm cận. Ngược lại, cận tiệm cận không nói chắc loại heap nào nhanh hơn trên dữ liệu thực. Cần dùng **cả phân tích lẫn đo kiểm**.

## 31. Quy trình lựa chọn trong thực tế

### Bước 1 — thống kê thao tác

Đếm `push`, `pop`, `decrease-key`, `increase-key`, `delete(id)` và `meld`. Phân biệt số thao tác gọi với số lần cập nhật thực sự làm đổi vị trí.

### Bước 2 — xác định cách định vị phần tử

Người gọi có **chỉ số**, **handle ổn định** hay chỉ **ID**? Nếu chỉ có ID, cần tra cứu phù hợp và cộng chi phí vào mô hình.

### Bước 3 — chốt loại bảo đảm

Hệ thống chấp nhận **khấu hao** và vài lần gọi chậm, hay phải bảo đảm thời gian xấu nhất? Có yêu cầu về thứ tự ổn định khi khóa hòa không?

### Bước 4 — đo bộ nhớ

Ước lượng số mục cực đại, kích thước entry, bảng ID, số nút, metadata, pool và số bản ghi stale tồn đọng.

### Bước 5 — chọn một đường cơ sở đơn giản

Thông thường bắt đầu với **binary heap mảng** hoặc **indexed binary heap**, vì dễ cài và kiểm thử. Chỉ chuyển sang d-ary, leftist/skew, pairing hoặc Fibonacci khi workload cho thấy lợi ích đáng kể.

### Bước 6 — benchmark theo đúng tình huống

Đo cả throughput và tail latency, peak memory và allocation. Không chỉ đo `decrease-key` đơn lẻ nếu ứng dụng còn `pop`/`meld`.

### Bước 7 — tính chi phí duy trì mã

Nhiều nút và con trỏ đồng nghĩa nhiều bất biến hơn, khả năng lỗi handle/ownership lớn hơn. Một thiết kế dễ kiểm chứng đôi khi đáng giá hơn một cải thiện Big-O không tạo khác biệt thực tế.

## 32. Cây quyết định ngắn

```text
Có cần meld rất thường xuyên?
 |
 +-- Có --> Cần meld O(1) trên heap thuần?
 |           |
 |           +-- Có --> Xem Fibonacci / pairing (kiểm tra các thao tác khác).
 |           |
 |           +-- Không --> Xem leftist / skew / binomial.
 |
 +-- Không --> Có rất nhiều decrease-key?
             |
             +-- Có --> Có handle/index theo ID?
             |           |
             |           +-- Không --> Thiết kế bảng ID / lazy version trước.
             |           |
             |           +-- Có --> So indexed d-ary / binary với Fibonacci.
             |
             +-- Không --> Ưu tiên binary heap mảng làm baseline.

Sau đó: kiểm tra cấp phát, bộ nhớ, cache, worst-case và benchmark.
```

Đây là **sơ đồ định hướng**, không phải thuật toán chọn tự động. Ví dụ, một ứng dụng cần nhiều meld nhưng có giới hạn bộ nhớ nghiêm ngặt vẫn có thể chọn mảng nếu tổng số phép meld nhỏ hoặc có thể gộp theo lô.

## 33. Những lỗi khi so sánh hoặc sử dụng heap

| Sai lầm | Vì sao sai? | Cách khắc phục |
|---|---|---|
| “Mọi heap đều hỗ trợ decrease-key theo ID trong `O(\log n)`.” | Heap-order không phải chỉ mục ID | Nêu tiền điều kiện handle/index; thêm bảng ID |
| “Decreasing key và increasing key cùng chi phí.” | Hướng sửa khác, đặc biệt với Fibonacci | Tách decrease/increase/change-key |
| “Fibonacci decrease-key là `O(1)` mỗi lần.” | Có thể cắt dây chuyền | Nói rõ **khấu hao** |
| “Fibonacci extract-min luôn `O(\log n)` thực tế.” | Có thể nhiều gốc trước consolidation | Cận `O(\log n)` là khấu hao |
| “Pairing heap có cùng cận Fibonacci.” | Phân tích decrease-key phụ thuộc biến thể | Dẫn đúng bảo đảm của biến thể dùng |
| “Meld hai indexed heap mất `O(1)` chỉ vì root list nối được.” | Còn gộp bảng ID, ownership, ID trùng | Đo toàn bộ API meld |
| “Binomial heap có `meld O(1)` như Fibonacci.” | Hợp nhất bậc có thể lan truyền | Cận chuẩn `O(\log n)` |
| “Leftist và skew heap có bảo đảm worst-case giống nhau.” | Skew kinh điển chủ yếu có cận khấu hao | Phân biệt worst-case và amortized |
| “Heap mảng luôn không cấp phát gì lúc push.” | Vùng chứa có thể phải tăng sức chứa | Tính append khấu hao và peak memory |
| “Heap liên kết có `O(n)` bộ nhớ nên tốn như heap mảng.” | Big-O che giấu con trỏ và overhead allocator | Đo byte/object và phân mảnh |
| “Heap d-nhánh tăng `d` thì pop luôn nhanh hơn.” | Mỗi tầng cần so nhiều con hơn | Tính `d\log_d n` và benchmark |
| “Cùng priority không cần xét thứ tự.” | Hợp đồng có thể đòi FIFO | Khóa ghép với sequence duy nhất |
| “Meld hai heap có sequence cục bộ vẫn FIFO toàn cục.” | Sequence có thể trùng | Thiết kế tie-breaker toàn cục |
| “Một handle có thể dùng sau khi xóa/meld tùy ý.” | Dễ sai owner, use-after-free | Quy tắc vòng đời/generation |
| “Lazy deletion không làm tăng bộ nhớ.” | Stale giữ nhiều bản ghi vật lý | Theo dõi `m`, dọn định kỳ |
| “Chỉ cần thử một lần benchmark.” | Nhiễu warm-up, GC và hệ thống | Đo lặp lại, ghi rõ workload |
| “Mã nhanh trên tập nhỏ sẽ nhanh trên mọi kích thước.” | Cache và allocation đổi khi quy mô tăng | Thử nhiều `n` và phân bố thao tác |
| “Khấu hao là trung bình xác suất.” | Khấu hao không yêu cầu đầu vào ngẫu nhiên | Dùng thế năng/tổng chi phí chuỗi |
| “Meld heap với chính nó là một trường hợp thường.” | Có thể tạo vòng/trùng quyền sở hữu | Từ chối hoặc xử lý riêng |
| “Heap Fibonacci thay được điều kiện đúng của Dijkstra.” | Thuật toán đường đi vẫn cần cạnh không âm | Tách điều kiện thuật toán khỏi hàng đợi |

## 34. Bài tập tự kiểm tra

**Bài 1.** Giải thích sự khác nhau giữa `decrease-key(handle,k)` và `change_priority(id,k)`. Vì sao không thể lấy trực tiếp cận của thao tác thứ nhất cho thao tác thứ hai?

**Bài 2.** Với min-heap `[2,5,3,9,7,8,4]` và đã biết phần tử cần sửa ở chỉ số `4`, giảm khóa từ `7` xuống `1`. Hãy cho biết hướng sửa và mảng cuối.

**Bài 3.** Cho biết chi phí chính của `insert`, `extract-min` và `decrease-key` tại chỉ số đã biết trong binary heap mảng.

**Bài 4.** Một indexed heap có `n` mục và bảng băm `id\to index`. Khi cập nhật một ID, vì sao phải tính tới chi phí kỳ vọng của bảng băm? Bộ nhớ bảng phụ là bao nhiêu?

**Bài 5.** Với heap d-nhánh có `d=4`, vì sao `decrease-key` trong min-heap có thể giảm số tầng so với binary heap nhưng `extract-min` không nhất thiết nhanh hơn?

**Bài 6.** Gộp hai binary min-heap mảng có `n_1` và `n_2` phần tử bằng cách nối mảng rồi heapify. Thời gian và bộ nhớ phụ của cách tạo mảng mới là bao nhiêu?

**Bài 7.** Tại sao `meld` của binomial heap kinh điển có thể ví với phép cộng nhị phân?

**Bài 8.** Nêu bất biến `npl(left)\ge npl(right)` của leftist heap và giải thích tác dụng đối với meld.

**Bài 9.** Leftist heap và skew heap khác nhau thế nào về metadata hình dạng và loại cận cho meld?

**Bài 10.** Vì sao nói `meld O(1)` của Fibonacci heap không tự bảo đảm `mergeQueues O(1)` khi mỗi queue còn có một bảng tra ID?

**Bài 11.** Một Fibonacci heap vừa trải qua nhiều `insert`, tạo nhiều cây gốc. Vì sao một lần `extract-min` tiếp theo có thể đắt dù cận khấu hao vẫn `O(\log n)`?

**Bài 12.** Phát biểu lợi thế lý thuyết của Fibonacci heap so với indexed binary heap khi Dijkstra có rất nhiều lần giảm khóa. Nêu một điều kiện tiền đề.

**Bài 13.** Vì sao pairing heap không nên được giới thiệu là luôn có `decrease-key O(1)` khấu hao giống Fibonacci heap?

**Bài 14.** Một hệ thống chỉ `push/pop` hàng triệu công việc, gần như không có decrease-key hoặc meld. Hãy chọn một baseline và nêu hai lý do liên quan tới bộ nhớ.

**Bài 15.** Mỗi phần tử Fibonacci heap có thêm bốn con trỏ, mỗi con trỏ `8` byte. Riêng bốn trường ấy tốn bao nhiêu MB thập phân khi có một triệu phần tử? Vì sao đó chưa phải tổng footprint?

**Bài 16.** Vì sao một lần `push` vào mảng động có thể phải dời `O(n)` ô nhưng `append` vẫn `O(1)` khấu hao?

**Bài 17.** Với lazy queue, `n` ID còn hoạt động nhưng `m` bản ghi vật lý chưa dọn. Một lần đổi khóa và một lần `pop` nghiệp vụ phụ thuộc `n` hay `m`? Vì sao?

**Bài 18.** Hai heap muốn meld đều dùng khóa `(priority,sequence)` nhưng sequence của mỗi heap bắt đầu từ `0`. Có rủi ro nào về ổn định? Đề xuất một cách giải quyết.

**Bài 19.** Một hệ thống yêu cầu p99 của mỗi lần pop thật thấp, không chấp nhận một lần gọi cực đắt. Vì sao không nên chọn Fibonacci heap chỉ vì `extract-min O(\log n)` khấu hao?

**Bài 20.** Nếu dùng pool để cấp phát nút, hai lợi ích và hai rủi ro còn lại là gì?

**Bài 21.** Chọn cấu trúc đáng thử đầu tiên cho ba trường hợp: (a) nhiều meld, ít decrease-key; (b) nhiều decrease-key, đã có handle; (c) memory-sensitive push/pop. Giải thích rằng đó mới là **điểm khởi đầu để đo**, không phải kết luận chung.

**Bài 22.** Thiết kế một benchmark để so binary, indexed d-ary và Fibonacci heap công bằng khi workload có `20.000` insert, `300.000` decrease-key và `20.000` extract-min. Phải đồng nhất những gì?

### Đáp án và giải thích

1. `decrease-key(handle,k)` giả định đã có handle đúng và chỉ giảm khóa; `change_priority(id,k)` còn phải tìm vị trí/handle theo ID và có thể tăng khóa. Không thể bỏ chi phí định vị hoặc hướng sửa.
2. Dùng `sift-up`: `[2,5,3,9,1,8,4]\to[2,1,3,9,5,8,4]\to[1,2,3,9,5,8,4]`.
3. Phần sửa heap của cả ba thao tác là `O(\log n)` xấu nhất khi vị trí đã biết; `insert` còn có chi phí `append` khấu hao của mảng động.
4. `position[id]` thường dùng bảng băm nên tra/cập nhật `O(1)` kỳ vọng, không mặc nhiên xấu nhất. Bảng chiếm `O(n)` bộ nhớ phụ.
5. Sift-up so với một cha trên đường dài khoảng `\log_d n`; sift-down phải chọn nhỏ nhất trong tối đa `d` con mỗi tầng, nên `O(d\log_d n)`.
6. `O(n_1+n_2)` thời gian nối+heapify; cách `a+b` tạo mảng mới cần `O(n_1+n_2)` bộ nhớ cho kết quả, bên cạnh hai mảng nguồn.
7. Mỗi bậc biểu diễn một cây kích thước `2^k`, nên gộp hai cây cùng bậc tạo một cây bậc cao hơn như thao tác nhớ sang bit kế tiếp.
8. Nhánh phải có npl không lớn hơn nhánh trái, nên đường phải dài `O(\log n)`; meld chỉ đi theo những đường ngắn ấy.
9. Leftist lưu `npl/rank` để giữ leftist property, có meld `O(\log n)` xấu nhất; skew không cần metadata hình dạng ấy và có meld `O(\log n)` khấu hao.
10. Nối root list là thao tác trên heap thuần. Gộp các bảng `id\to node`, giải quyết ID trùng và chuyển ownership có thể tốn nhiều thời gian bổ sung.
11. Insert chưa hợp nhất nên số gốc có thể `\Theta(n)`. Extract-min phải duyệt/gộp nhiều gốc trong một lần; thế năng tích lũy từ các lần insert bù vào cận khấu hao.
12. Indexed binary heap giảm khóa `O(\log V)`, Fibonacci `O(1)` khấu hao khi có handle; Dijkstra trên cạnh không âm có cận `O((V+E)\log V)` so với `O(E+V\log V)` theo mô hình thông dụng.
13. Các biến thể pairing heap có phân tích decrease-key riêng; thao tác cắt/liên kết đơn giản không tự chứng minh cận `O(1)` khấu hao của toàn chuỗi.
14. Binary heap mảng; ít metadata, không cấp nút liên kết riêng cho mỗi phần tử và tận dụng locality của mảng.
15. `4\times8\times10^6=32.000.000` byte, tức khoảng **32 MB** thập phân; chưa tính khóa, payload, degree, mark, alignment, allocator và metadata của runtime.
16. Tăng sức chứa theo tỷ lệ làm các lần phải sao chép cả mảng thưa dần; tổng số ô dịch chuyển trong nhiều lần append bị chặn tuyến tính theo số lần append.
17. Cập nhật bằng push một bản ghi mất `O(\log(m+1))`. Pop nghiệp vụ có thể phải bỏ nhiều stale, nên số bước phụ thuộc `m` và vị trí các stale; không chỉ `n`.
18. Hai mục có thể cùng `priority` và cùng `sequence` nhưng đến từ hai heap khác nhau, làm thứ tự toàn cục mơ hồ. Dùng nguồn cấp ticket toàn cục, khóa phụ phân biệt nguồn theo hợp đồng, hoặc đánh số lại có kiểm soát.
19. Một lần extract-min có thể duyệt rất nhiều gốc, dù tổng chi phí được khấu hao. Cần phân tích và đo độ trễ riêng từng lời gọi, gồm cấp phát và GC.
20. Lợi ích: giảm số lần gọi allocator chung, có thể cải thiện locality. Rủi ro: giữ dung lượng dự phòng và handle trỏ tới slot được tái sử dụng (ABA); thêm nữa vẫn phải bảo trì nhiều con trỏ.
21. (a) Thử leftist/skew/binomial hoặc Fibonacci/pairing tùy mức meld yêu cầu; (b) thử indexed d-ary và Fibonacci; (c) binary heap mảng. Sau đó cần benchmark đúng workload và đo bộ nhớ.
22. Dùng cùng chuỗi thao tác hợp lệ, cùng ID/priority và quy tắc hòa, cùng hình thức định vị mục (handle hoặc map), cùng trạng thái đầu, kiểm tra kết quả pop, đo thời gian từng thao tác, allocation/peak memory/GC, lặp nhiều lần và ghi cấu hình runtime.

## 35. Ghi nhớ

**Không tồn tại một heap tối ưu cho mọi hàng đợi ưu tiên.** Binary heap mảng đơn giản, ít metadata và thân thiện cache, nhưng `decrease-key` tại vị trí đã biết mất `O(\log n)` và `meld` thường cần `O(n_1+n_2)` bằng nối mảng rồi heapify. Indexed heap thêm ánh xạ ID để cập nhật nhanh theo tên công việc; d-ary heap giảm chiều cao cho sift-up nhưng tăng số so sánh khi sift-down. Binomial, leftist và skew heap đặt trọng tâm vào **meld**, với bảo đảm logarithmic thích hợp; Fibonacci heap có **`insert`, `meld` và `decrease-key` `O(1)` khấu hao**, đổi lại cấu trúc con trỏ phức tạp và `extract-min` có thể đắt trong một lần gọi. Pairing heap gọn hơn nhưng cận decrease-key phải gắn với đúng biến thể. Khi so sánh, luôn cộng **chi phí định vị ID/handle**, **chi phí gộp bảng tra cứu**, **cấp phát và thu hồi nút**, **bộ nhớ đệm**, **độ trễ đuôi** và **hợp đồng ổn định/ownership**. Hãy chọn bằng cả **phân tích tiệm cận, tần suất thao tác và đo kiểm trên workload thực tế**, thay vì chỉ nhìn một ô `O(1)` trong bảng Big-O.
