# So sánh chi phí xây dựng, cập nhật, duyệt và truy vấn hàng loạt

Một cấu trúc dữ liệu có thể trả lời **một truy vấn** rất nhanh nhưng mất nhiều thời gian để tạo, tiêu tốn bộ nhớ để duy trì hoặc chậm khi có thay đổi. Ngược lại, một cấu trúc đơn giản có thể thích hợp nhất nếu chỉ dùng một lần rồi bỏ. Vì vậy, trong chương **Lựa chọn và thiết kế**, câu hỏi cần trả lời không chỉ là “phép toán này có độ phức tạp bao nhiêu?”, mà còn là **“toàn bộ vòng đời của dữ liệu có chi phí bao nhiêu?”**.

Bài học vận dụng kiến thức về mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị để phân tích bốn nhóm công việc: **xây dựng**, **cập nhật**, **duyệt** và **trả lời nhiều truy vấn**. Đích đến là lựa chọn một thiết kế có bất biến đúng, đủ nhanh trong thời gian chạy thực tế và sử dụng bộ nhớ phù hợp.

## 1. Mô hình hóa chi phí toàn bộ vòng đời

Xét tập `n` phần tử, có `u` lần cập nhật, `q` truy vấn và `d` lần duyệt. Một mô hình gần đúng là:

```text
T_total ≈ B(n)
        + Σ U(n_j, loại_cập_nhật_j)   // j = 1..u
        + Σ Q(n_i, loại_truy_vấn_i)  // i = 1..q
        + Σ D(n_t, kiểu_duyệt_t)     // t = 1..d
        + C_phụ
```

Trong đó:

- `B(n)`: chi phí tạo cấu trúc, sắp xếp, xây chỉ mục hoặc tiền xử lý.
- `U`: chi phí chèn, xóa, sửa, điều chỉnh độ ưu tiên và **duy trì mọi chỉ mục liên quan**.
- `Q`: chi phí tìm kiếm/truy vấn, bao gồm số kết quả phải xuất ra.
- `D`: chi phí duyệt toàn bộ hoặc một phần cấu trúc.
- `C_phụ`: cấp phát bộ nhớ, tái băm, sao chép, đồng bộ, ghi đĩa, chuyển đổi dữ liệu và giải phóng tài nguyên.

Kích thước tập dữ liệu có thể thay đổi sau mỗi cập nhật nên ký hiệu `n_j`/`n_i` nhắc rằng không phải mọi phép toán đều chạy trên cùng một `n`. Để so phương án ban đầu, có thể thay bằng quy mô dự kiến; khi đo thực tế cần dùng chuỗi thao tác thực.

**Đừng cộng độ phức tạp Big-O như một phép tính thời gian chính xác.** `O(n)` và `O(log n)` mô tả xu hướng khi quy mô tăng; chúng không tự cho biết số mili giây, số lần cache miss hay chi phí truy cập SSD. Bảng độ phức tạp dùng để sàng lọc, sau đó đo ở tải tương ứng.

Cùng với thời gian, ghi rõ **bộ nhớ**: dữ liệu gốc, bộ nhớ phụ của chỉ mục, bộ nhớ tạm lúc xây dựng, đỉnh bộ nhớ khi tái cấu trúc và số bản sao được duy trì. Hai thiết kế có `O(n)` bộ nhớ vẫn có thể khác nhau nhiều về số byte trên mỗi phần tử.

### Tải công việc quyết định khoản chi nào lớn nhất

Ví dụ với 100.000 bản ghi:

- **Xây một lần, hỏi một lần:** tiền xử lý đắt có thể không thu hồi được lợi ích.
- **Xây một lần, hỏi hàng triệu lần:** tiền xử lý có thể giúp giảm tổng chi phí đáng kể.
- **Hỏi và cập nhật xen kẽ:** phải tính cả chi phí giữ chỉ mục đúng sau mỗi thay đổi.
- **Duyệt tất cả bản ghi rất thường xuyên:** tính liên tục của bộ nhớ, thứ tự duyệt và chi phí cấp phát có thể quan trọng không kém chi phí tìm một khóa.

Cần xác định thao tác nào là **bắt buộc về ngữ nghĩa** (ví dụ truy vấn khoảng phải chính xác, danh sách phải có thứ tự), rồi mới tối ưu chi phí của các phương án đáp ứng được chúng.

## 2. Chi phí xây dựng: tiền xử lý bao nhiêu là hợp lý?

Bước xây dựng có thể là sao chép từ nguồn dữ liệu, sắp xếp mảng, thêm từng phần tử hoặc dùng thuật toán **xây hàng loạt**. Cùng một cấu trúc, cách xây khác nhau có thể tạo chênh lệch lớn.

Ký hiệu `S = Σ |key_i|` là tổng độ dài các khóa chuỗi; các con số sau giả định dữ liệu trong RAM và phép so sánh khóa cơ bản có chi phí `O(1)`, trừ nơi nêu khác.

| Cấu trúc / cách chuẩn bị | Chi phí tạo từ `n` phần tử | Mục đích và điều kiện |
| --- | --- | --- |
| Mảng giữ thứ tự đầu vào | `O(n)` để sao chép; `O(1)` nếu đã có mảng dùng trực tiếp | Phù hợp duyệt tuần tự/truy cập theo vị trí |
| Mảng sắp xếp theo khóa | Thông thường `O(n log n)` để sắp xếp bằng so sánh | Có thể tìm nhị phân, liệt kê theo thứ tự; bộ nhớ phụ tùy thuật toán sắp xếp |
| Hash map/set | Kỳ vọng `O(n)` khi băm và chèn, giả định hàm băm thích hợp | Tạo chỉ mục tra cứu khóa chính xác; cần quản lý va chạm/hệ số tải |
| Cây tìm kiếm tự cân bằng | `O(n log n)` nếu chèn lần lượt; có thể `O(n)` từ dãy khóa **đã sắp** bằng thuật toán xây cân bằng | Hỗ trợ tìm/cập nhật có thứ tự; chi phí sắp dãy ban đầu vẫn phải tính |
| Heap nhị phân | `O(n)` bằng `buildHeap/heapify` kiểu từ dưới lên; thêm `n` lần thường `O(n log n)` | Tốt khi liên tục lấy phần tử có ưu tiên cao nhất/thấp nhất |
| Danh sách liên kết | `O(n)` để tạo và nối các nút | Thêm/xóa nút đã biết nhanh, nhưng tốn liên kết và ít thuận lợi cho truy cập ngẫu nhiên |
| Prefix sum | `O(n)` | Tiền xử lý tổng đoạn của mảng ít thay đổi |
| Fenwick tree | `O(n)` với cách dựng tuyến tính; `O(n log n)` nếu thêm lần lượt | Hỗ trợ cập nhật điểm và tổng tiền tố/đoạn |
| Segment tree | `O(n)` | Lưu tổng hợp các đoạn, hỗ trợ truy vấn/cập nhật có cấu trúc |
| Trie | Thường `O(S)` khi bước qua ký tự/cạnh hiệu quả | Đánh đổi bộ nhớ để truy vấn tiền tố |
| Danh sách kề đồ thị | `O(V+E)` từ `V` đỉnh và `E` cạnh khi thêm cạnh có chi phí phù hợp | Hiệu quả cho duyệt hàng xóm trong đồ thị thưa |

**Bất biến phải đúng ngay sau bước dựng.** Mảng sắp phải thỏa `A[i] ≤ A[i+1]`; heap phải thỏa quan hệ ưu tiên cha–con; cây tìm kiếm phải duy trì thứ tự và điều kiện cân bằng; prefix sum phải thỏa `P[i+1] = P[i] + A[i]`. Nếu khởi tạo sai, độ phức tạp tốt không cứu được kết quả truy vấn.

### Vì sao heap có thể dựng trong `O(n)`?

Một cách đơn giản là thêm từng phần tử bằng `push`, mỗi lần tối đa `O(log n)` nên tổng chặn trên `O(n log n)`. Cách khác là đặt tất cả phần tử vào mảng rồi thực hiện `siftDown` từ các nút không phải lá đi ngược lên gốc.

Phần lớn nút nằm gần lá và phải di chuyển rất ít. Tổng chi phí của các lần `siftDown` theo độ cao nút được chặn bởi `O(n)`. Đây là ví dụ điển hình cho thấy **thuật toán xây hàng loạt** có thể tốt hơn việc gọi thao tác cập nhật riêng lẻ `n` lần.

### Dữ liệu đã có sẵn ở trạng thái nào?

Cần phân biệt hai trường hợp:

1. **Đã có dãy theo đúng thứ tự cần dùng:** binary search có thể chạy ngay; không được cộng thêm chi phí sắp xếp nếu nguồn bảo đảm dữ liệu đã sắp.
2. **Dữ liệu chưa sắp, chỉ có danh sách bản ghi:** muốn tìm nhị phân phải trả chi phí xây/duy trì thứ tự, hoặc tạo chỉ mục riêng.

Trong trường hợp dữ liệu đã sắp, dựng cây cân bằng từ dãy có thể `O(n)`. Nếu phải tự sắp để đạt trạng thái này, tổng công việc thông thường vẫn bao gồm `O(n log n)` sắp xếp. Không nên bỏ công đoạn ấy khỏi bảng so sánh.

## 3. Chi phí cập nhật: tối ưu đọc có thể làm ghi đắt lên

Chi phí cập nhật gồm hai phần: **thay đổi dữ liệu** và **khôi phục bất biến**. Nếu giữ nhiều chỉ mục, một thay đổi logic có thể biến thành nhiều thay đổi vật lý.

| Cấu trúc | Cập nhật tiêu biểu | Điều cần lưu ý |
| --- | --- | --- |
| Mảng động | Thêm cuối `O(1)` khấu hao; chèn/xóa giữa `O(n)` | Tăng dung lượng gây sao chép hàng loạt; phần tử phía sau có thể đổi chỉ số |
| Danh sách liên kết đôi | Chèn/xóa `O(1)` **khi đã có nút phù hợp** | Tìm nút theo khóa thường `O(n)` nếu không có chỉ mục phụ |
| Hash map | Tìm/thêm/xóa kỳ vọng `O(1)` | Va chạm, tái băm, thay đổi khóa và xử lý trùng lặp |
| Mảng sắp | Thay giá trị không làm đổi khóa `O(1)`; chèn/xóa theo vị trí có thể `O(n)` | Phải giữ nguyên tính sắp xếp |
| Cây tự cân bằng | Chèn/xóa theo khóa `O(log n)` trường hợp xấu | Phải cân bằng và cập nhật metadata của nút |
| Heap | `push`/`popMin` `O(log n)` | Xóa/sửa một phần tử bất kỳ cần biết vị trí hoặc phải tìm |
| Fenwick tree | Cập nhật một điểm `O(log n)` | Bất biến tổng tích lũy trên các đoạn cây |
| Segment tree | Cập nhật một điểm `O(log n)` | Phải cập nhật các nút tổ tiên liên quan |
| Prefix sum | Sửa một `A[i]` thường `O(n)` | Các tổng tiền tố từ `i+1` trở đi có thể thay đổi |

Hai bảo đảm thường bị lẫn:

- **Khấu hao:** mảng động thêm cuối `O(1)` *khấu hao* dù một lần tăng dung lượng có thể `O(n)`. Chi phí của cả chuỗi thao tác mới được chặn.
- **Kỳ vọng:** hash map tra cứu/chèn kỳ vọng `O(1)` với giả định phù hợp về hàm băm/phân bố khóa; một thao tác đơn lẻ có thể tốn nhiều hơn, và trường hợp xấu có thể `O(n)`.

Khi ứng dụng đặt giới hạn độ trễ cho **từng** lần ghi, không thể dùng chặn khấu hao/kỳ vọng để suy ra thời gian tối đa cứng.

### Nhiều chỉ mục: tốc độ đọc đi kèm nghĩa vụ đồng bộ

Giả sử một đơn hàng có mã `id`, thời gian tạo `createdAt`, và hệ thống duy trì:

```text
byId:    HashMap<Id, Order>
byTime:  BalancedBST<(CreatedAt, Id)>
```

Tra cứu theo mã nhanh nhờ `byId`; duyệt theo thời gian nhanh nhờ `byTime`. Nhưng khi xóa đơn:

```text
cancel(id):
    o = byId.get(id)
    if o không tồn tại: return NOT_FOUND

    // Một thao tác logic phải cập nhật cả hai chỉ mục
    xóa (o.createdAt, o.id) khỏi byTime
    xóa o.id khỏi byId

    // Nếu có lỗi giữa chừng, phục hồi hoặc rollback
```

Bất biến phải duy trì: **một đơn đang hoạt động có mặt trong cả hai chỉ mục; một đơn đã xóa không tồn tại trong bất kỳ chỉ mục nào**. Trong môi trường nhiều luồng, cần giao dịch, khóa hoặc snapshot phù hợp để người đọc không quan sát trạng thái cập nhật dở dang.

Chi phí thao tác xóa có thể là một lần tra cứu hash kỳ vọng `O(1)` cộng một lần xóa cây `O(log n)` và một lần xóa hash kỳ vọng `O(1)`. Chỉ tính lần xóa trên hash map sẽ đánh giá thấp tải ghi.

## 4. Chi phí duyệt: cùng `O(n)` nhưng hiệu năng rất khác

Duyệt có thể nhằm đọc mọi phần tử, xuất kết quả có thứ tự, gom thống kê hay xử lý hàng loạt. Dù nhiều cấu trúc cùng có thời gian **`O(n)`** để xem hết `n` phần tử, chi phí thực tế vẫn khác nhau.

| Cấu trúc | Duyệt đầy đủ | Thứ tự & đặc trưng bộ nhớ |
| --- | --- | --- |
| Mảng/mảng động | `O(n)` | Dữ liệu liền kề, thường tận dụng cache và prefetch tốt |
| Danh sách liên kết | `O(n)` | Theo liên kết; nhiều truy cập con trỏ và cấp phát nút |
| Hash map | Thường `O(n + c)` nếu phải quét `c` ô/bucket | Thứ tự tùy triển khai; không mặc định tăng dần |
| Cây tìm kiếm cân bằng | `O(n)` | Duyệt trung thứ tự cho khóa tăng dần, thường cần đi theo con trỏ |
| Heap nhị phân | `O(n)` để quét mảng bên trong | Dãy trong heap **không được sắp toàn bộ** |
| Trie | `O(N_\mathrm{node} + S_\mathrm{out})` khi duyệt mọi nút và tạo kết quả | Thứ tự tùy cách duyệt cạnh; có thể tận dụng tiền tố chung |
| Danh sách kề đồ thị | `O(V+E)` để thăm tất cả đỉnh/cạnh | DFS/BFS cần cấu trúc hỗ trợ và đánh dấu đã thăm |

Ở hàng hash map, `c` là số ô/bucket trong bảng. Khi hệ số tải được giới hạn thích hợp, `c = O(n)` thường cho duyệt `O(n)`. Nhưng nếu cấp sẵn một bảng rất lớn so với số phần tử, việc quét toàn bộ các ô có thể đắt. Chi phí duyệt còn tùy API/triển khai cụ thể.

Cần tách **duyệt** khỏi **sắp xếp để xuất**:

- Duyệt mảng có `n` phần tử: `O(n)`.
- Nếu mảng **chưa sắp** nhưng cần xuất tăng dần: thường phải sắp `O(n log n)` trước khi duyệt.
- Duyệt trung thứ tự của cây tìm kiếm: `O(n)` và nhận ngay thứ tự khóa.
- Quét toàn bộ mảng heap: `O(n)` nhưng **không** bảo đảm tăng dần; muốn lấy lần lượt theo ưu tiên, phải thực hiện `extractMin`, tổng cộng `O(n log n)` cho `n` lần (và làm thay đổi heap hoặc cần bản sao).

**Ngưỡng dưới về đầu ra:** nếu một truy vấn phải trả `k` phần tử, riêng việc tạo/xuất `k` phần tử đã cần ít nhất `Ω(k)` công việc trong mô hình chi phí thông thường. Không thể hứa một truy vấn liệt kê 50.000 kết quả hoàn tất trong `O(log n)` chỉ nhờ tìm thấy điểm bắt đầu nhanh.

### Khi duyệt nhiều lần, bố cục dữ liệu trở thành yếu tố chính

Nếu chạy 100 vòng thống kê trên dữ liệu không thay đổi, tổng duyệt có thể là `O(100n)`. Mảng có thể có lợi nhờ dữ liệu liên tục và ít overhead; cây hoặc danh sách thường chịu thêm chi phí đi theo con trỏ. Đổi cấu trúc có thể cải thiện tốc độ dù không thay đổi Big-O, nhưng cần benchmark theo loại phần tử, kích thước cache, kiến trúc phần cứng và bộ nhớ thực tế.

## 5. Truy vấn hàng loạt: có nên trả phí xây chỉ mục trước?

**Truy vấn hàng loạt** là việc trả lời nhiều yêu cầu trên cùng một tập dữ liệu hoặc các phiên bản gần nhau của nó. Chúng có thể xuất hiện đồng thời, nối tiếp hoặc đã biết trước (*offline*). Điểm then chốt là tận dụng phần việc đã làm ở các truy vấn trước.

### 5.1. Truy vấn khóa chính xác: quét hay tạo hash map?

Giả sử một danh sách có `n` phần tử và có `q` câu hỏi “có khóa `k` không?”.

**Không tạo chỉ mục:**

```text
for mỗi query k:
    quét danh sách đến khi tìm thấy k
```

Trong trường hợp xấu, tổng chi phí `O(qn)`.

**Tạo chỉ mục hash một lần:**

```text
index = HashMap()
for item in items:
    index[item.id] = item

for k in queries:
    answer(index.get(k))
```

Chi phí xây kỳ vọng `O(n)` và `q` tra cứu kỳ vọng `O(q)`, tổng **`O(n+q)` kỳ vọng**, đổi lại bộ nhớ chỉ mục `O(n)`. Trường hợp xấu phụ thuộc vào triển khai bảng băm và phân bố khóa.

Nếu `q=1`, quét tuyến tính có thể tốt hơn vì khỏi phải xây và cấp phát bảng băm. Nếu `q` rất lớn trên tập dữ liệu ổn định, tiền xử lý thường có lợi. **Không có một giá trị `q` hòa vốn cố định suy ra chỉ từ Big-O**; cần đo hằng số thời gian và lượng bộ nhớ.

Một mô hình kiểm tra điểm hòa vốn bằng thời gian đo:

```text
Không chỉ mục: T_scan  ≈ q × t_scan(n)
Có chỉ mục:    T_index ≈ t_build(n) + q × t_lookup(n)

Chọn chỉ mục nếu:
t_build(n) < q × [t_scan(n) - t_lookup(n)]
```

Điều kiện giả định các chi phí bình quân đủ ổn định và bỏ qua cập nhật. Nếu có ghi, phải thêm chi phí duy trì chỉ mục vào phía `T_index`.

### 5.2. Truy vấn nhiều lần trên mảng tĩnh: prefix sum

Giả sử có `n` số nguyên, hỏi tổng trên `q` đoạn chỉ số `[l,r]`.

- **Cộng trực tiếp mỗi lần:** chi phí `O(\sum_i (r_i-l_i+1))`, trường hợp xấu `O(qn)`.
- **Tạo prefix sum:** dựng `O(n)`, mỗi truy vấn `O(1)`, tổng `O(n+q)` và bộ nhớ thêm `O(n)`.

Ví dụ:

```text
A = [3, 2, 8, 5, 1]
P = [0, 3, 5, 13, 18, 19]

sum(1, 3) = P[4] - P[1] = 18 - 3 = 15
sum(2, 4) = P[5] - P[2] = 19 - 5 = 14
```

Mã giả với biên đóng:

```text
buildPrefix(A):
    P = array(n + 1)
    P[0] = 0
    for i in 0..n-1:
        P[i+1] = P[i] + A[i]
    return P

rangeSum(P, l, r):     // 0 <= l <= r < n
    return P[r+1] - P[l]
```

Bất biến cần giữ: `P[i]` là tổng `i` phần tử đầu tiên. Nếu sửa một giá trị `A[i]`, mọi tổng tiền tố sau vị trí đó có thể đổi; cập nhật trực tiếp prefix sum có thể cần **`O(n)`**. Với dữ liệu cập nhật thường xuyên, Fenwick tree hoặc segment tree có thể cân bằng chi phí.

### 5.3. Nhiều truy vấn tổng đoạn và nhiều cập nhật: Fenwick/segment tree

Với `n` phần tử, `u` cập nhật điểm và `q` truy vấn tổng:

| Phương án | Xây dựng | `u` cập nhật | `q` truy vấn | Tổng ước lượng |
| --- | --- | --- | --- | --- |
| Mảng + cộng trực tiếp | Có sẵn mảng | `O(u)` | Xấu nhất `O(qn)` | `O(u + qn)` |
| Prefix sum | `O(n)` | Xấu nhất `O(un)` | `O(q)` | `O(n + un + q)` |
| Fenwick tree | `O(n)` nếu dựng tuyến tính | `O(u log n)` | `O(q log n)` | `O(n + (u+q)log n)` |
| Segment tree (tổng) | `O(n)` | `O(u log n)` | `O(q log n)` | `O(n + (u+q)log n)` |

Bảng trên là **chặn thời gian tổng thể**, không phải dự báo tuyệt đối về tốc độ. Với `u` rất nhỏ và `q` rất lớn, prefix sum có thể tốt. Khi `u` tăng đáng kể, phải cân nhắc chi phí làm mới prefix sum sau mỗi sửa.

Fenwick tree đặc biệt gọn cho tổng tiền tố và cập nhật điểm; segment tree linh hoạt hơn nếu bài toán đổi thành `min`/`max`, tổng hợp tùy biến hoặc cần một số dạng cập nhật đoạn với kỹ thuật phù hợp.

**Lưu ý:** phép `min` không thể tính từ hiệu hai “prefix min”; các cấu trúc tổng hợp cần phép kết hợp thích hợp và bất biến tương ứng.

### 5.4. Truy vấn khoảng khóa: đã sắp và số kết quả trả về

Với `q` truy vấn `range(a_i,b_i)` trên tập `n` khóa, gọi `k_i` là số kết quả của truy vấn thứ `i`.

- Không có thứ tự/chỉ mục: trường hợp xấu quét `O(qn)`.
- Mảng sắp: xây `O(n log n)`; mỗi truy vấn tìm biên và liệt kê `O(log n + k_i)`; tổng `O(n log n + q log n + \sum_i k_i)`.
- Cây tìm kiếm tự cân bằng: xây bằng chèn `O(n log n)`; mỗi truy vấn `O(log n + k_i)`. Nếu có cập nhật xen kẽ, thêm/xóa `O(log n)` một lần theo khóa.

Nếu `\sum_i k_i` rất lớn, thời gian xuất kết quả có thể lớn hơn toàn bộ phần tìm vị trí bắt đầu. Khi ứng dụng chỉ cần **đếm** số phần tử trong khoảng thay vì liệt kê, có thể dùng cấu trúc có thông tin thứ hạng, ví dụ cây lưu kích thước cây con, để tránh xuất từng phần tử. Khi đó cần thêm bất biến và chi phí cập nhật metadata.

### 5.5. Truy vấn biết trước: sắp xếp câu hỏi để dùng chung công việc

Trong chế độ *offline*, ta biết trước tất cả câu hỏi và không cần trả lời theo đúng thứ tự nhận ngay lập tức. Có thể sắp xếp hoặc gom nhóm chúng, rồi trả kết quả về vị trí yêu cầu ban đầu.

Ví dụ: với `n` giá trị `x_j`, có `q` câu hỏi “bao nhiêu `x_j ≤ t_i`?”.

Một cách:

1. Sắp các giá trị `x_j` tăng dần.
2. Sắp các cặp `(t_i, originalIndex_i)` tăng dần theo `t_i`.
3. Dùng một con trỏ chạy từ trái sang phải trên dãy `x`; với mỗi `t_i`, tăng con trỏ đến khi gặp giá trị lớn hơn `t_i`.
4. Ghi số phần tử đã đi qua vào `answer[originalIndex_i]`.

```text
values = sort(values)
requests = sort([(threshold, originalIndex) ...])

j = 0
for (t, originalIndex) in requests:
    while j < n and values[j] <= t:
        j += 1
    answer[originalIndex] = j
```

Chi phí sắp xếp là `O(n log n + q log q)`; bước quét đồng thời chỉ `O(n+q)`. Mấu chốt: con trỏ `j` **không quay lại đầu dãy cho mỗi câu hỏi**. Đây là cách dùng chung công việc giữa các truy vấn, khác với chạy độc lập `q` lần.

Nếu `values` đã sắp, bước sắp xếp nó không cần lặp lại. Nếu còn có các cập nhật chen giữa các truy vấn và kết quả phải phản ánh đúng trạng thái tức thời, cách offline này không thể áp dụng nguyên trạng; cần xét lại thiết kế.

### 5.6. Nhiều lần lấy phần tử nhỏ nhất: heap và sắp xếp

Với `n` phần tử chưa sắp:

- **Chỉ lấy giá trị nhỏ nhất một lần:** quét `O(n)`, ít chi phí chuẩn bị.
- **Lấy `k` giá trị nhỏ nhất lần lượt:** dựng min-heap `O(n)` rồi `k` lần `popMin`, tổng `O(n + k log n)`.
- **Muốn toàn bộ phần tử theo thứ tự:** một thuật toán sắp xếp so sánh có thể dùng `O(n log n)`, sau đó duyệt `O(n)`.

Heap phù hợp khi liên tục nhận phần tử mới và lấy cực trị; mảng sắp phù hợp nếu muốn duyệt có thứ tự nhiều lần trên tập tĩnh. Đừng nhầm **heap có phần tử nhỏ nhất ở gốc** với **mọi phần tử trong mảng heap đều đã sắp**.

## 6. Ví dụ số: một triệu bản ghi, nhiều truy vấn trên dữ liệu tĩnh

Cho `n = 1.000.000` giá trị doanh số theo thời điểm. Cần trả `q = 20.000` truy vấn tổng đoạn. Giả sử mỗi đoạn trung bình dài 500.000 phần tử và dữ liệu không cập nhật.

**Phương án A — cộng lại đoạn:** khoảng

```text
20.000 × 500.000 = 10.000.000.000
```

lượt cộng số trong mô hình đơn giản, chưa tính chi phí đọc bộ nhớ và xuất kết quả.

**Phương án B — prefix sum:** khoảng một triệu phép cộng để dựng mảng `P`, sau đó 20.000 phép trừ để trả lời truy vấn; cần thêm `n+1` ô lưu tổng tiền tố. Tổng số phép tính chính **có thể giảm nhiều bậc độ lớn** khi số câu hỏi lớn.

Tuy nhiên, nếu thêm `5.000` lần sửa dữ liệu xen kẽ với truy vấn, cập nhật prefix sum bằng cách sửa mọi phần tử phía sau có thể phải làm công việc tuyến tính nhiều lần. Khi đó bảng so sánh `O(n+(u+q)log n)` của Fenwick/segment tree trở nên đáng cân nhắc.

Ví dụ dùng **số phép toán giả định để minh họa**, không phải kết quả benchmark: phép cộng, bộ nhớ và cấu trúc triển khai có chi phí khác nhau, và cần kiểm tra tràn số khi tổng tích lũy vượt miền số nguyên.

## 7. Thiết kế tổng thể: so chi phí cập nhật và truy vấn cùng lúc

Giả sử danh mục có `n = 200.000` sản phẩm, chủ yếu:

- Tìm đúng sản phẩm theo `sku`.
- Liệt kê các sản phẩm thuộc khoảng giá, theo giá tăng dần.
- Cập nhật giá và thêm/xóa sản phẩm.
- Chạy báo cáo duyệt tất cả sản phẩm hằng ngày.

Ba ứng viên minh họa:

| Phương án | Xây dựng ban đầu | Tra cứu theo `sku` | Khoảng giá có thứ tự | Sửa giá |
| --- | --- | --- | --- | --- |
| Mảng bản ghi không sắp | `O(n)` | `O(n)` nếu quét | `O(n)` để lọc, có thể cần sắp kết quả | `O(1)` nếu biết vị trí |
| Hash map theo `sku` | Kỳ vọng `O(n)` | Kỳ vọng `O(1)` | Vẫn cần quét và sắp kết quả nếu muốn tăng dần | Kỳ vọng `O(1)` để tìm và sửa |
| Hash map theo `sku` + cây cân bằng theo `(price,sku)` | Kỳ vọng `O(n)` cho hash và `O(n log n)` khi xây cây bằng chèn | Kỳ vọng `O(1)` | `O(log n+k)` | Tìm bản ghi, xóa khóa cũ và thêm khóa mới vào cây: `O(log n)` kỳ vọng tổng thể |

Ở phương án thứ ba, `(price,sku)` tạo thứ tự nhất quán và cho phép các sản phẩm trùng giá vẫn có khóa phân biệt. Hai chỉ mục cùng tham chiếu bản ghi logic; mọi sửa giá phải đồng bộ khóa trong cây, mọi xóa phải xóa khỏi cả hai. Nếu thường xuyên đổi `sku`, thao tác đó cũng cần cập nhật khóa trong hash map và cây.

Ngoài bảng, hãy đo **bộ nhớ phụ** của hash table và nút cây, **độ trễ cập nhật** khi phải sửa hai chỉ mục và **chi phí duyệt** trong mỗi báo cáo. Nếu khoảng giá hiếm khi được hỏi, chỉ mục cây có thể không xứng đáng với chi phí duy trì. Nếu báo cáo cần duyệt toàn bộ theo `sku`, một mảng hoặc bản sao kết quả định kỳ có thể thuận lợi hơn về cache; khi ấy lại phát sinh chi phí xây/làm mới bản sao.

### Cách lập bảng quyết định theo tải thực tế

Với mỗi ứng viên, ghi lại:

```text
B(n)       : xây chỉ mục một lần
U(n)       : chi phí cập nhật, tính tất cả cấu trúc phụ
Q_exact(n) : chi phí tra cứu chính xác
Q_range(n,k): chi phí truy vấn khoảng và xuất k kết quả
D(n)       : duyệt / xuất báo cáo
M(n)       : bộ nhớ thường trực + bộ nhớ đỉnh khi dựng lại
Guarantee  : expected / amortized / worst-case; kết quả có thứ tự?
Invariant  : các trạng thái luôn phải nhất quán
```

Điền tần suất của từng loại thao tác vào mô hình tổng chi phí, loại phương án vi phạm bảo đảm, sau đó thử dữ liệu đủ đại diện. Cách làm này cũng áp dụng cho **stack/queue**: nếu dữ liệu xử lý LIFO/FIFO, hãy ưu tiên cấu trúc hỗ trợ các thao tác đầu/cuối đúng giao diện; việc chọn giữa mảng vòng và danh sách liên kết phụ thuộc số lần cấp phát, giới hạn dung lượng và nhu cầu duyệt.

## 8. Những lỗi phân tích chi phí thường gặp

**1. Chỉ lấy độ phức tạp của truy vấn.** Nói “tìm nhị phân `O(log n)` nên tốt hơn quét” mà bỏ `O(n log n)` sắp xếp hoặc `O(n)` chi phí chèn mảng là so sánh thiếu.

**2. Cộng thời gian mà quên bộ nhớ.** Hai chỉ mục có thể giúp tra cứu nhanh nhưng tăng bộ nhớ và chi phí khi dữ liệu thay đổi; cần tính cả chỉ mục, bản sao tạm và dữ liệu trung gian.

**3. Giả sử thêm `n` phần tử luôn bằng thời gian tối ưu của xây hàng loạt.** Dựng heap từ mảng `O(n)` khác với `n` lần `push` `O(n log n)`. Dựng Fenwick tuyến tính khác với cập nhật từng điểm.

**4. Nhầm kỳ vọng, khấu hao và trường hợp xấu.** Một lần tăng kích thước mảng động hoặc rehash có thể làm độ trễ tăng mạnh, dù chi phí bình quân tốt. Không suy ra bảo đảm thời gian cứng cho từng thao tác.

**5. Bỏ số kết quả được trả.** Truy vấn khoảng trên cây có chặn `O(log n+k)`, không thể bỏ `k` nếu phải thực sự trả đủ các phần tử.

**6. So số phép toán nhưng bỏ môi trường chạy.** Một mảng liên tục có thể duyệt nhanh hơn danh sách liên kết dù cả hai cùng `O(n)`. Với bộ nhớ ngoài, số lần đọc/ghi khối và cấu trúc như B-tree/B+ tree có thể quan trọng hơn chi phí so sánh đơn lẻ.

**7. Không tính chi phí duy trì bất biến.** Sửa một thuộc tính được dùng làm khóa sắp xếp không chỉ là phép gán; phải di chuyển khóa trong chỉ mục. Trong hệ thống có đồng thời, còn phải xử lý cập nhật nguyên tử và quan sát nhất quán.

**8. Giả sử mọi truy vấn độc lập.** Khi câu hỏi đã biết trước và được phép trả kết quả sau, sắp xếp truy vấn, quét chung hoặc tiền xử lý có thể giảm tổng công việc. Nhưng nếu có cập nhật xen giữa hoặc phải trả lời trực tuyến, cần giữ đúng ngữ nghĩa thời điểm.

## 9. Tự kiểm tra quyết định

### Bài 1 — Một truy vấn và một triệu truy vấn

Có mảng chưa sắp `n` phần tử, tìm theo khóa chính xác.

**a)** Chỉ có một câu hỏi. Có chắc phải tạo hash map trước không?

**b)** Có `10^6` câu hỏi trên mảng bất biến. Nếu đủ RAM, phương án nào đáng thử?

*Gợi ý:* a) Quét một lần có thể tiết kiệm chi phí xây; b) Hash map kỳ vọng `O(n+q)` tổng thể thay vì trường hợp xấu `O(nq)`. Muốn kết luận hiệu năng thực tế phải đo.

### Bài 2 — Heap và dữ liệu đã sắp

Bạn có 500.000 điểm số, cần lần lượt lấy 100 điểm nhỏ nhất rồi dừng. Giữa hai đợt không có cập nhật.

*Định hướng:* Quét chọn nhỏ nhất 100 lần từ mảng chưa sắp có thể tốn `O(100n)`; build min-heap `O(n)` rồi lấy 100 lần `O(100 log n)`. Sắp toàn bộ mất `O(n log n)` dù không dùng hết thứ tự. Cân nhắc thuật toán chọn top-`k` khác nếu chỉ cần tập 100 phần tử và thứ tự đầu ra không bắt buộc.

### Bài 3 — Prefix sum có đủ không?

Có dãy `n` số, mỗi phút 1.000 truy vấn tổng đoạn và 500 cập nhật điểm. Có nên dùng prefix sum thuần túy?

*Định hướng:* Tính tổng chi phí của cập nhật prefix sum `O(n)` và so với Fenwick tree/segment tree `O(log n)` cho cả cập nhật và truy vấn. Số lượng phần tử, độ trễ tối đa và tính chất số học quyết định lựa chọn cuối cùng.

### Bài 4 — Báo cáo theo thứ tự

Một hash map đủ nhanh cho việc tìm đơn theo `id`, nhưng báo cáo cuối ngày cần xuất mọi đơn tăng dần theo `createdAt`.

*Định hướng:* Chọn giữa (a) sao chép rồi sắp một lần mỗi ngày và (b) giữ cây theo `(createdAt,id)` trong suốt ngày. Với phương án (a), cộng chi phí sắp `O(n log n)` mỗi kỳ; với (b), cộng chi phí duy trì cây `O(log n)` mỗi lần thêm/xóa và bộ nhớ thường trực. Tần suất báo cáo và số lần cập nhật quyết định phương án kinh tế hơn.

## Kết luận

**Chi phí của cấu trúc dữ liệu là chi phí của cả vòng đời.** Muốn so sánh chính xác, phải biết dữ liệu được xây như thế nào, cập nhật ra sao, duyệt bao nhiêu lần, cần trả bao nhiêu truy vấn và mỗi truy vấn xuất bao nhiêu phần tử. Xây chỉ mục có thể đắt nhưng giúp tiết kiệm khi truy vấn lặp lại; cấu trúc tối ưu đọc có thể làm ghi nặng hơn; những cấu trúc cùng `O(n)` khi duyệt vẫn khác nhau về cache và bộ nhớ.

Một quy trình có thể áp dụng cho mọi bài toán là **mô tả tải công việc → nêu bất biến và bảo đảm → lập bảng chi phí xây/cập nhật/duyệt/truy vấn → tính tổng theo tần suất → đo trên dữ liệu thực tế**. Nhờ vậy, việc chọn mảng, bảng băm, cây, heap, Fenwick/segment tree hoặc nhiều chỉ mục là quyết định có căn cứ, thay vì dựa trên một độ phức tạp riêng lẻ.
