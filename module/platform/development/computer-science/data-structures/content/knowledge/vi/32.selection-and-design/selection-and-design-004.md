# Dữ liệu tĩnh hay động, dày hay thưa, có thứ tự hay ngẫu nhiên

Hai ứng dụng cùng quản lý một triệu phần tử có thể cần những cấu trúc dữ liệu hoàn toàn khác nhau. Một ứng dụng chỉ đọc bảng tra cứu đã xây sẵn; ứng dụng còn lại chèn, xóa và sửa dữ liệu mỗi giây. Một đồ thị có hàng triệu đỉnh nhưng chỉ vài cạnh ở mỗi đỉnh; một đồ thị khác có cạnh giữa phần lớn các cặp đỉnh. Một tập khóa đã sắp xếp theo thời gian; tập khác đến không theo quy luật.

Trong chương **Lựa chọn và thiết kế**, ta cần nhìn vào **hình dạng dữ liệu và cách dữ liệu biến đổi** trước khi quyết định dùng mảng, bảng băm, cây, heap hay biểu diễn đồ thị nào. Bài này phân tích ba trục quan trọng:

1. **Tĩnh hay động:** dữ liệu có thay đổi sau khi tạo chỉ mục không, và thay đổi như thế nào?
2. **Dày hay thưa:** bao nhiêu phần tử, cạnh hoặc ô thực sự tồn tại so với không gian có thể biểu diễn?
3. **Có thứ tự hay ngẫu nhiên:** khóa có sẵn theo một thứ tự hữu ích không, và truy vấn có cần thứ tự ấy không?

Ba trục này **độc lập**. Một đồ thị có thể vừa thưa vừa động; một dãy có thể vừa tĩnh vừa chưa sắp xếp; một bảng khóa có thể dày đặc trong miền số nguyên nhưng được cập nhật liên tục. Phân loại chính xác giúp chọn cấu trúc theo **bất biến, thao tác và chi phí thời gian/bộ nhớ**, thay vì chọn theo tên quen thuộc.

## 1. Bắt đầu bằng mô tả dữ liệu và tải công việc

Hãy mô tả dữ liệu trước khi viết mã:

| Câu hỏi | Ví dụ câu trả lời | Hệ quả thiết kế |
| --- | --- | --- |
| Có bao nhiêu phần tử? | `n = 2.000.000` | Quyết định chi phí quét, kích thước chỉ mục |
| Có bao nhiêu khóa/vị trí có thể có? | `U = 10^9` mã số, chỉ `n = 10^5` mã tồn tại | Mảng tra cứu trực tiếp kích thước `U` có thể lãng phí |
| Dữ liệu có thay đổi không? | Nạp một lần rồi chỉ đọc; hoặc chèn/xóa hàng nghìn lần mỗi phút | Phân biệt tiền xử lý tĩnh với chỉ mục cập nhật |
| Thao tác đọc chính là gì? | Tìm theo `id`, truy vấn tổng đoạn, duyệt hàng xóm, lấy cực trị | Xác định API và độ phức tạp cần tối ưu |
| Khóa được đưa vào theo thứ tự nào? | Tăng dần theo thời gian; ngẫu nhiên; có đợt đến muộn | Ảnh hưởng chi phí xây dựng và duy trì sắp xếp |
| Kết quả cần có thứ tự không? | Trả 20 bản ghi sớm nhất theo `(time,id)` | Bảng băm đơn lẻ thường chưa đủ |
| Có giới hạn gì? | RAM 1 GiB, truy vấn p99 dưới 20 ms, phải chính xác | Loại cấu trúc không đáp ứng bảo đảm |

Viết ra **tập phép toán** và tần suất của chúng: `get(key)`, `get(i)`, `insert`, `delete`, `range`, `sum(l,r)`, `neighbors(v)`, `hasEdge(u,v)`, `min()`, v.v. “Tìm nhanh” chưa đủ rõ để chọn cấu trúc.

Một mô hình sơ bộ cho thời gian toàn vòng đời:

```text
T ≈ T_build
  + q_get    × T_get
  + q_range  × T_range
  + u_insert × T_insert
  + u_delete × T_delete
  + d_scan   × T_scan
  + T_maintenance

Bộ nhớ ≈ dữ liệu gốc + chỉ mục + vùng dự phòng + bộ nhớ tạm
```

Đây là mô hình **ước lượng**, không phải công thức cho thời gian chạy thực tế: các thao tác có thể có đầu vào khác nhau, chi phí trung bình/khấu hao/trường hợp xấu khác nhau và hằng số phụ thuộc CPU, bộ nhớ, I/O. Dẫu vậy, mô hình buộc ta tính cả **xây dựng và duy trì**, không chỉ chi phí của một truy vấn.

## 2. Trục thứ nhất: dữ liệu tĩnh hay động?

### 2.1. “Tĩnh” và “động” nghĩa là gì?

**Dữ liệu tĩnh** trong một giai đoạn xử lý là dữ liệu không thay đổi sau khi khởi tạo. Ta có thể dành thời gian sắp xếp, nén, lập chỉ mục hoặc tính sẵn câu trả lời để phục vụ nhiều lần đọc.

**Dữ liệu động** cho phép thêm, xóa hoặc thay đổi phần tử sau khi cấu trúc được tạo. Khi đó, mọi thao tác ghi phải giữ lại các **bất biến** mà truy vấn dựa vào.

Còn những trường hợp nằm giữa:

- **Chỉ thêm (append-only):** không xóa hoặc sửa bản ghi cũ; có thể thuận lợi cho mảng động, log và chỉ mục theo thời gian nếu khóa tăng.
- **Cập nhật điểm:** sửa giá trị ở một vị trí, không thay đổi số phần tử; thuận lợi cho Fenwick tree hoặc segment tree nếu cần tổng hợp đoạn.
- **Thêm/xóa tùy ý:** không thể chỉ dựa vào bản chụp sắp xếp cố định mà không tính chi phí điều chỉnh.
- **Tạo phiên bản theo lô:** dữ liệu có thay đổi giữa các đợt, nhưng mỗi bản snapshot bất biến trong thời gian phục vụ truy vấn.

“Dữ liệu tĩnh” không đồng nghĩa “phải lưu trong bộ nhớ chỉ đọc”, và “dữ liệu động” không đồng nghĩa “kích thước luôn tăng”. Đây là mô tả về **những thao tác được phép** trong tải công việc đang xét.

### 2.2. So sánh trên dãy số

Giả sử lưu dãy `A[0..n-1]` và liên tục hỏi `sum(l,r)`.

**Nếu dãy tĩnh:** xây prefix sum `P`:

```text
P[0] = 0
P[i+1] = P[i] + A[i]

sum(l, r) = P[r+1] - P[l]  // 0 <= l <= r < n
```

Xây dựng `O(n)`, bộ nhớ phụ `O(n)`, sau đó mỗi truy vấn tổng `O(1)`. Bất biến là `P[i]` luôn bằng tổng `i` phần tử đầu tiên.

**Nếu thường xuyên cập nhật `A[i]`:** sửa một phần tử có thể khiến mọi `P[j]` với `j > i` thay đổi, chi phí cập nhật có thể lên tới `O(n)`. Fenwick tree hoặc segment tree hỗ trợ cập nhật điểm và truy vấn tổng đoạn trong `O(log n)`, xây dựng `O(n)` bằng thuật toán thích hợp, bộ nhớ phụ `O(n)`.

| Phương án | Tổng đoạn | Sửa một điểm | Thích hợp khi |
| --- | --- | --- | --- |
| Mảng và cộng trực tiếp | `O(n)` trường hợp xấu | `O(1)` | Ít truy vấn, ưu tiên tối giản |
| Prefix sum | `O(1)` | `O(n)` trường hợp xấu | Dữ liệu tĩnh, nhiều truy vấn tổng |
| Fenwick tree | `O(log n)` | `O(log n)` | Tổng tiền tố/đoạn và cập nhật điểm |
| Segment tree | `O(log n)` | `O(log n)` | Nhiều phép tổng hợp có tính kết hợp |

Với `n` lớn, prefix sum không nên được chọn chỉ vì “truy vấn `O(1)`” nếu mỗi phút có hàng nghìn lần sửa. Ngược lại, nếu dữ liệu bất biến, cây cập nhật có thể tăng độ phức tạp và chi phí bộ nhớ mà không đem lại lợi ích.

### 2.3. Tĩnh hay động ảnh hưởng chi phí tra cứu khóa

Cho `n` bản ghi có mã `id` duy nhất:

| Cách lưu | Chuẩn bị | Tra cứu `id` | Thêm/xóa bản ghi |
| --- | --- | --- | --- |
| Mảng chưa sắp | Sao chép `O(n)` | Quét `O(n)` | Thêm cuối mảng động `O(1)` khấu hao; tìm phần tử cần xóa vẫn tốn chi phí |
| Mảng sắp theo `id` | Sắp `O(n log n)` trong mô hình so sánh | Tìm nhị phân `O(log n)` | Chèn/xóa thường `O(n)` do dời phần tử |
| Hash map | Xây kỳ vọng `O(n)` | Kỳ vọng `O(1)` | Thêm/xóa kỳ vọng `O(1)` dưới giả định phù hợp |
| Cây tìm kiếm tự cân bằng | Chèn từng phần tử `O(n log n)` | `O(log n)` trường hợp xấu | Thêm/xóa `O(log n)`, vẫn duy trì thứ tự |

Nếu tập khóa **tĩnh và đã sắp**, có thể dùng tìm nhị phân ngay mà không sắp lại. Nếu tập khóa **động và cần truy vấn cận dưới, khóa kế tiếp hoặc khoảng**, cây tự cân bằng thường hợp lý hơn mảng sắp phải dời phần tử liên tục.

Bảng băm thích hợp khi thao tác chủ đạo là tra cứu chính xác, còn thứ tự của khóa không bắt buộc. Tính `O(1)` ở đây là bảo đảm **kỳ vọng/trung bình trong điều kiện thích hợp**, không phải chặn thời gian xấu nhất cho mọi lần tra cứu.

### 2.4. Xây lại định kỳ hay duy trì liên tục?

Một phương án thường hữu ích cho dữ liệu **động theo đợt** là:

1. Giữ bản dữ liệu đã sắp hoặc bản snapshot bất biến để phục vụ phần lớn truy vấn.
2. Nhận thay đổi mới vào một vùng cập nhật nhỏ hoặc cấu trúc phụ có thể ghi.
3. Khi đạt một ngưỡng, hợp nhất cập nhật vào snapshot mới.
4. Chuyển các truy vấn sang phiên bản mới bằng cơ chế đồng bộ phù hợp.

Mô hình này xuất hiện trong chỉ mục phân đoạn và nhiều hệ thống lưu trữ. Tuy nhiên, nếu đọc cần thấy mọi thay đổi mới nhất, **truy vấn phải kết hợp snapshot với vùng cập nhật**, đồng thời xử lý xóa/ghi đè đúng ngữ nghĩa. Việc chỉ đọc snapshot cũ sẽ cho kết quả sai.

Điểm quyết định là tỷ lệ **đọc so với ghi**, giới hạn độ trễ cho từng thao tác và chi phí xây lại. Tính toán chi phí tổng thể thay vì mặc định “tĩnh thì luôn dùng mảng” hoặc “động thì luôn dùng cây”.

## 3. Trục thứ hai: dữ liệu dày hay thưa?

“Dày” và “thưa” chỉ có nghĩa sau khi đã định nghĩa **không gian có thể có dữ liệu**. Hai ngữ cảnh phổ biến là **đồ thị** và **miền khóa/ma trận**.

### 3.1. Đồ thị thưa và đồ thị dày

Cho đồ thị có `V` đỉnh và `E` cạnh. Với **đồ thị vô hướng đơn, không có cạnh khuyên**, số cạnh tối đa là:

```text
E_max = V × (V - 1) / 2
density = E / E_max
```

Với **đồ thị có hướng đơn, không có cạnh khuyên**, số cung tối đa là `V(V-1)`. Mật độ được đo tương đối so với số cạnh tối đa của **đúng loại đồ thị**; không có một ngưỡng phần trăm duy nhất áp dụng cho mọi ứng dụng.

- **Thưa:** `E` rất nhỏ so với `V²`; trong nhiều trường hợp `E = O(V)`.
- **Dày:** `E` tiến gần bậc `V²`; mỗi đỉnh có thể liên kết với rất nhiều đỉnh khác.

Ba cách lưu thường gặp:

**Danh sách kề (adjacency list):** mỗi đỉnh lưu danh sách đỉnh hàng xóm. Với đồ thị vô hướng, mỗi cạnh thường được ghi ở hai danh sách. Bộ nhớ `O(V+E)`, duyệt hàng xóm đỉnh `u` mất `O(deg(u))`.

**Ma trận kề (adjacency matrix):** `M[u][v]` cho biết có cạnh `u→v` hay không (hoặc lưu trọng số). Bộ nhớ `O(V²)`, kiểm tra có cạnh `O(1)` và duyệt toàn bộ hàng xóm của một đỉnh thường tốn `O(V)` vì phải xem cả các ô trống.

**CSR — Compressed Sparse Row:** nén các danh sách kề vào mảng `offsets` và `neighbors` liên tiếp. Bộ nhớ `O(V+E)`; rất thuận lợi cho đồ thị thưa, ít thay đổi và duyệt hàng xóm thường xuyên. Thêm/xóa cạnh tùy ý có thể phải dịch chuyển hoặc xây lại các mảng, nên CSR cơ bản không phù hợp với tải cập nhật liên tục nếu thiếu cơ chế bổ sung.

| Phép toán / tính chất | Danh sách kề | Ma trận kề | CSR |
| --- | --- | --- | --- |
| Bộ nhớ | `O(V+E)` | `O(V²)` | `O(V+E)` |
| Duyệt hàng xóm `u` | `O(deg(u))` | `O(V)` | `O(deg(u))` |
| Kiểm tra `(u,v)` có cạnh | Thường `O(deg(u))` nếu danh sách không có chỉ mục phụ | `O(1)` | Thường `O(deg(u))`; có thể tìm nhị phân `O(log deg(u))` nếu đoạn đã sắp |
| Thêm cạnh | Có thể `O(1)` khi thêm cuối danh sách và không cần kiểm tra trùng | `O(1)` | Không thuận tiện, có thể cần xây lại `O(V+E)` |
| Xóa cạnh | Thường `O(deg(u))` để tìm; có thể sửa nhanh hơn nếu biết vị trí | `O(1)` | Có thể cần dịch chuyển/xây lại |
| BFS/DFS từ mọi đỉnh | `O(V+E)` | Thường `O(V²)` | `O(V+E)` |

Các chặn trên giả định biểu diễn thông dụng. Nếu danh sách kề dùng **hash set theo hàng xóm**, kiểm tra cạnh có thể kỳ vọng `O(1)` nhưng tăng chi phí bộ nhớ; nếu có cạnh trùng hoặc cạnh khuyên, chính sách biểu diễn và bất biến phải được nêu rõ.

Ví dụ, với đồ thị vô hướng `V = 10.000`, `E = 20.000`, mật độ rất thấp: danh sách kề chỉ lưu khoảng `2E = 40.000` mục hàng xóm và dữ liệu đỉnh, còn ma trận có `10^8` ô. Một ma trận bit tối giản đã cần khoảng 12,5 MB chưa kể metadata, trong khi ma trận byte cần khoảng 100 MB. Danh sách kề có overhead riêng, nhưng thường hợp lý hơn cho đồ thị kiểu này.

Với đồ thị có hướng `V = 1.000` và khoảng `E = 400.000` cung, ma trận có một triệu ô, tương đương khoảng 125 KB nếu dùng bitset thuần hoặc 1 MB nếu dùng một byte mỗi ô. Danh sách kề phải lưu 400.000 đích cạnh cùng metadata. Khi kiểm tra có cạnh rất thường xuyên, **ma trận kề trở thành ứng viên đáng xét**.

Các con số chỉ minh họa kích thước phần lưu trữ nguyên thủy, không phải footprint chính xác của một ngôn ngữ hoặc thư viện. Trong hệ thống thực tế, kiểu trọng số, cách cấp phát và mật độ cạnh mới quyết định điểm chuyển đổi.

### 3.2. Dày/thưa trong miền khóa số nguyên

Giả sử có `n` mã số đang dùng, mỗi mã nằm trong miền `0..U-1`.

- **Đánh địa chỉ trực tiếp:** mảng `table[0..U-1]` dùng mã làm chỉ số; truy cập `O(1)`, nhưng bộ nhớ `O(U)` ngay cả khi chỉ dùng vài khóa.
- **Bitset:** nếu chỉ cần biết một mã có tồn tại hay không, dùng khoảng `U` bit, có thể ít hơn nhiều so với mảng đối tượng. Chi phí truy cập theo vị trí `O(1)` trong mô hình thao tác từ máy và `U` phải đủ nhỏ để cấp phát.
- **Hash map:** lưu các khóa đang tồn tại, bộ nhớ kỳ vọng/tổng thể tỷ lệ `O(n)`; tra cứu kỳ vọng `O(1)`.
- **Cây cân bằng:** lưu `O(n)` nút, tra cứu `O(log n)`; hữu ích khi còn cần thứ tự và khoảng khóa.

Nếu `U = 1.000.000.000` nhưng chỉ `n = 10.000` khóa tồn tại, tạo một tỷ ô để lưu trực tiếp có thể gây lãng phí nghiêm trọng. Nếu `U = 20.000` và gần như mọi mã đều có bản ghi, mảng trực tiếp có thể rất gọn và nhanh.

**Mật độ khóa** ở đây là `n/U`, khác mật độ cạnh trong đồ thị. Ngoài ra, cần xét giá trị mã lớn nhất và có cần ánh xạ mã thưa sang chỉ số liên tục hay không. **Nén tọa độ** ánh xạ các giá trị khóa đang có sang `0..n-1` và có thể tiết kiệm bộ nhớ cho dữ liệu tĩnh, nhưng nếu thêm khóa mới chưa biết trước, ánh xạ và thứ tự có thể phải được cập nhật.

### 3.3. Ma trận dữ liệu nhiều ô trống

Với ma trận `R×C` mà chỉ có `z` giá trị khác 0:

- Mảng hai chiều dày lưu `O(RC)` ô, cho phép truy cập `A[r][c]` trực tiếp trong `O(1)`.
- Biểu diễn thưa kiểu danh sách bộ ba `(r,c,value)` lưu `O(z)` phần tử nhưng tìm một ô bất kỳ có thể phải tìm kiếm.
- CSR cho ma trận thưa lưu `O(R+z)` phần tử/phụ trợ; nhân ma trận thưa với vector có thể tận dụng việc chỉ đi qua các giá trị khác 0. Truy cập/cập nhật ô bất kỳ phụ thuộc biểu diễn và cách sắp các chỉ số cột.

Biểu diễn thưa tiết kiệm khi `z ≪ RC`, nhưng cần xác định **số 0 có mang ý nghĩa dữ liệu không**. Nếu một ô “không có bản ghi” khác với “có bản ghi giá trị 0”, cấu trúc phải giữ riêng hai trạng thái ấy.

## 4. Trục thứ ba: có thứ tự hay ngẫu nhiên?

Từ “có thứ tự” thường bị dùng cho ba đặc điểm khác nhau:

1. **Dữ liệu đầu vào đã sắp theo khóa:** ví dụ các `timestamp` trong file tăng dần.
2. **Ứng dụng cần đầu ra có thứ tự:** ví dụ yêu cầu 20 đơn sớm nhất, ngay cả khi đầu vào chưa sắp.
3. **Khóa được phân bố thế nào:** ngẫu nhiên, tăng tuần tự, lệch về vài khóa hoặc được tạo có chủ ý để gây va chạm.

Phải phân biệt chúng. **Ngẫu nhiên** về thứ tự đến không có nghĩa các khóa không thể so sánh, và **đã sắp** không có nghĩa một hash map tự duy trì thứ tự ấy.

### 4.1. Mảng đã sắp: tận dụng tiền xử lý

Với dãy `[2, 4, 4, 9, 15, 21]` đã sắp:

```text
lowerBound(4) = vị trí 1
upperBound(4) = vị trí 3
lowerBound(10) = vị trí 4 (giá trị 15)
```

Tìm nhị phân cần `O(log n)` **lần so sánh**. Nếu khóa là chuỗi dài, một lần so sánh có thể tốn thời gian theo độ dài phần chuỗi phải xem; không nên tự động coi mọi so sánh là `O(1)`.

Khi cần liệt kê `k` bản ghi nằm trong khoảng khóa, mảng sắp có thể tìm biên rồi duyệt liên tiếp trong khoảng `O(log n+k)` với khóa so sánh chi phí hằng số. Đây là lựa chọn rất tốt cho **tập tĩnh, đọc nhiều và cần duyệt thứ tự**.

Nhưng với mảng vẫn phải giữ sắp xếp, chèn một phần tử vào giữa thường cần dịch phần tử, tốn `O(n)`. Nếu dữ liệu **đến theo thứ tự tăng dần và chỉ thêm cuối**, việc duy trì dãy sắp có thể đơn giản hơn nhiều; nếu có bản ghi đến muộn làm đảo thứ tự, cần chèn đúng chỗ, giữ vùng delta hoặc tổ chức lại.

### 4.2. Khóa đến ngẫu nhiên: hash map hay cây?

**Hash map** thường hỗ trợ thêm/tìm/xóa theo khóa với thời gian kỳ vọng `O(1)`, thuận lợi khi không cần duyệt theo thứ tự. Tuy nhiên, không nên dựa vào thứ tự duyệt ngẫu nhiên hoặc thứ tự chèn của một hash map để suy ra thứ tự khóa.

**Cây tìm kiếm tự cân bằng** duy trì thứ tự khóa và chặn trên `O(log n)` cho tìm/chèn/xóa ngay cả khi khóa đến tăng dần hoặc ngược dần, miễn triển khai duy trì đúng bất biến cân bằng.

**Cây tìm kiếm nhị phân không cân bằng** có thể có chiều cao `O(n)` nếu chèn các khóa `1,2,3,...,n` theo thứ tự. Khi đó tra cứu suy biến thành `O(n)`. Việc đầu vào *thường* ngẫu nhiên không phải lý do đủ mạnh để bảo đảm chiều cao luôn thấp, nhất là khi dữ liệu có thể do bên ngoài kiểm soát.

Nếu yêu cầu thời gian chặn trên trường hợp xấu, hãy đánh giá chặn **trường hợp xấu** của cấu trúc, chứ không thay thế nó bằng giả định phân bố khóa thuận lợi.

### 4.3. Thứ tự cần duy trì là gì?

Mỗi kiểu “thứ tự” dẫn đến giao diện khác nhau:

| Yêu cầu | Gợi ý cấu trúc | Lưu ý |
| --- | --- | --- |
| Giữ thứ tự chèn, duyệt tuần tự | Mảng động, danh sách, queue tùy thao tác | Thứ tự chèn không phải thứ tự giá trị khóa |
| Tìm chính xác theo khóa, không cần thứ tự | Hash map/set | Kỳ vọng `O(1)`; trường hợp xấu có thể chậm hơn |
| Tìm `lowerBound`, `successor`, duyệt tăng dần | Mảng sắp nếu ít cập nhật; cây cân bằng nếu cập nhật thường xuyên | Tính cả chi phí dựng và giữ sắp xếp |
| Luôn lấy phần tử ưu tiên nhỏ nhất | Min-heap | `peekMin = O(1)`; `extractMin = O(log n)`; không sắp toàn bộ |
| Tìm khóa chuỗi theo tiền tố | Trie hoặc chỉ mục chuỗi sắp từ điển | Độ dài khóa và số kết quả được liệt kê ảnh hưởng chi phí |
| Chỉ cần xử lý FIFO/LIFO | Queue/stack | Có thể hiện thực bằng mảng vòng hoặc cấu trúc khác |

Nếu nhiều phần tử có cùng giá trị so sánh, phải định nghĩa quy tắc trùng lặp và phá hòa. Ví dụ, thay vì sắp đơn chỉ theo `createdAt`, có thể dùng khóa ghép `(createdAt, id)` để xác định thứ tự đầy đủ mà không làm mất các đơn cùng thời điểm.

### 4.4. “Ngẫu nhiên” có thể gây ra những rủi ro nào?

Một số giả định tưởng vô hại có thể thất bại:

- **Va chạm băm:** nhiều khóa khác nhau có cùng giá trị băm, làm tăng chi phí tìm/chèn của nhiều bảng băm thông dụng.
- **Khóa có tính chu kỳ hoặc phân bố lệch:** nhiều lần truy cập cùng vài khóa có thể tác động đến cache và cấu trúc hỗ trợ.
- **Đầu vào đã sắp khi cấu trúc chỉ hoạt động tốt với đầu vào ngẫu nhiên:** cây BST không cân bằng có thể trở thành danh sách.
- **Khóa thay đổi sau khi chèn:** bất biến của hash map hoặc cây theo khóa có thể bị phá nếu đối tượng thay đổi trường dùng làm khóa mà không cập nhật chỉ mục.

Các quyết định về hàm băm, cân bằng cây, chuẩn hóa chuỗi, khóa ghép và xử lý lỗi phải xuất phát từ bảo đảm thực tế cần cung cấp, không phải dự đoán mọi dữ liệu sẽ “ngẫu nhiên đẹp”.

## 5. Giao điểm của ba trục: ma trận lựa chọn

Một trục hiếm khi đủ để quyết định; hãy kết hợp cả ba với phép toán chủ đạo.

| Tình huống | Đặc tính dữ liệu | Phép toán quan trọng | Ứng viên đáng xét |
| --- | --- | --- | --- |
| Danh mục phiên bản cố định, tra cứu theo mã | Tĩnh; khóa bất kỳ; không cần thứ tự | `get(id)` rất nhiều | Hash map xây một lần hoặc mảng sắp để tìm nhị phân |
| Bảng số nguyên có miền khóa nhỏ, chiếm nhiều ô | Dày trong miền khóa; có thể động | Truy cập theo khóa số | Mảng đánh địa chỉ trực tiếp hoặc bitset nếu chỉ cần tồn tại |
| Mã số trải rộng trên miền rất lớn | Thưa trong miền khóa; động | Thêm/tìm/xóa chính xác | Hash map; cây cân bằng nếu cần thứ tự |
| Dãy số bất biến, hỏi tổng đoạn | Tĩnh; chỉ số dày, liên tục | `sum(l,r)` | Prefix sum |
| Dãy số cập nhật điểm liên tục | Động; chỉ số dày, liên tục | `update(i)`, `sum(l,r)` | Fenwick tree/segment tree |
| Đồ thị mạng xã hội rất thưa | Thưa; thường động | Thêm cạnh, duyệt hàng xóm | Danh sách kề; có thể kết hợp hash set cho từng đỉnh |
| Đồ thị có rất nhiều cạnh, ít đỉnh | Dày | `hasEdge(u,v)` thường xuyên | Ma trận kề, bitset theo hàng |
| Đồ thị thưa cố định, truy vấn BFS nhiều lần | Thưa và tĩnh | Duyệt cạnh/hàng xóm | CSR hoặc danh sách kề |
| Dữ liệu giá được nạp một lần | Tĩnh, có yêu cầu thứ tự giá | `range(lo,hi)` | Mảng sắp theo `(price,id)` |
| Cập nhật giá, vẫn phải tìm khoảng giá | Động, cần duy trì thứ tự | `insert/delete/range` | Cây tìm kiếm tự cân bằng theo `(price,id)` |
| Luồng tác vụ có thứ tự ưu tiên | Động, đầu vào bất kỳ | `push`, `extractMin` | Heap, kèm chỉ mục nếu phải xóa tùy ý |

Bảng chỉ định **ứng viên**, không khẳng định một cấu trúc luôn thắng. Ví dụ, một hash map có thể tra cứu chính xác tốt hơn nhưng không giúp tìm phần tử nhỏ nhất; ma trận kề có thể kiểm tra cạnh nhanh nhưng hao bộ nhớ nếu `V` lớn và đồ thị thưa.

## 6. Ví dụ thiết kế 1: luồng sự kiện theo thời gian

Một dịch vụ lưu sự kiện với `eventId`, `timestamp` và `payload`. Yêu cầu:

- Nhận nhiều sự kiện mới trong ngày.
- Tìm sự kiện chính xác theo `eventId`.
- Lấy các sự kiện trong đoạn thời gian `[t1,t2]` theo thứ tự.
- Cuối ngày khóa dữ liệu ngày cũ thành snapshot chỉ đọc.

### Khi thời gian đến tăng dần

Nếu **mọi** sự kiện mới có `timestamp` không nhỏ hơn sự kiện trước, có thể lưu sự kiện trong mảng động theo thứ tự thời gian. Thêm cuối `O(1)` khấu hao; tìm biên thời gian bằng binary search `O(log n)` và xuất `k` kết quả `O(k)`. Duy trì thêm hash map `eventId → vị trí hoặc tham chiếu` nếu tra cứu theo ID rất thường xuyên.

Bất biến: dãy `timestamp` không giảm, và `eventId` là duy nhất. Nếu hash map lưu chỉ số, **mọi thay đổi vị trí phải được phản ánh** trong hash map.

### Khi có sự kiện đến muộn

Ví dụ nhận timestamp `10, 11, 15, 12` thì mảng append-only không còn sắp theo thời gian. Có các lựa chọn:

1. Chèn sự kiện đến muộn vào vị trí đúng trong mảng sắp, chi phí dịch chuyển xấu nhất `O(n)`.
2. Dùng cây tìm kiếm cân bằng theo `(timestamp,eventId)`, mỗi lần chèn `O(log n)`, truy vấn khoảng `O(log n+k)`.
3. Gom sự kiện mới vào vùng delta, sắp/hợp nhất định kỳ với các đoạn tĩnh; truy vấn phải kết hợp các đoạn và delta theo thứ tự chính xác.

Nếu hàng ngày tạo snapshot bất biến, các đoạn cũ có thể nén, sắp và tối ưu truy vấn. Nhưng **sự kiện đang nhận vẫn là dữ liệu động**, nên phải quyết định cách đọc kết quả cập nhật mới nhất, xử lý bản ghi trùng, xóa và lỗi khi hợp nhất.

### Khi cần tổng hợp theo thời gian

Nếu timestamp đã được chia thành các bucket liên tục và câu hỏi chủ yếu là “tổng lượt xem từ ngày `l` tới ngày `r`”, prefix sum trên các bucket ngày đã khóa là ứng viên tốt. Nếu số lượt xem của ngày hiện tại thay đổi liên tục và cần báo cáo tổng ngay, Fenwick tree/segment tree trên các bucket có thể phù hợp hơn.

Bài toán lúc này không còn là **liệt kê sự kiện** mà là **tổng hợp khoảng**: hai phép toán khác nhau có thể cần hai chỉ mục khác nhau.

## 7. Ví dụ thiết kế 2: bản đồ liên kết giữa các dịch vụ

Giả sử hệ thống mô tả các dịch vụ và kết nối có hướng giữa chúng.

**Giai đoạn A:** có `V = 50.000` dịch vụ nhưng `E = 100.000` kết nối. Đồ thị rất thưa. Nhiệm vụ chính là tìm đường đi và duyệt các dịch vụ mà một dịch vụ gọi tới.

- Với danh sách kề, lưu `O(V+E)` và BFS/DFS toàn đồ thị có chặn `O(V+E)`.
- Với ma trận kề, cần `V² = 2.500.000.000` ô; một bitset thuần đã cần khoảng 312,5 MB, còn ma trận byte cần khoảng 2,5 GB, chưa kể overhead. Với `V` lớn, lựa chọn này có thể không phù hợp ngân sách RAM.

**Giai đoạn B:** chỉ có `V = 800` dịch vụ nhưng gần như mọi dịch vụ đều có thể gọi mọi dịch vụ khác. Nhiệm vụ chính là kiểm tra `hasEdge(u,v)` hàng triệu lần. Ma trận bit theo hàng sử dụng khoảng `800×800/8 = 80.000` byte để ghi trạng thái có/không, cho phép kiểm tra bằng truy cập chỉ số và bit.

**Nếu các kết nối thay đổi liên tục:** danh sách kề thường dễ thêm/xóa, nhưng nếu cần kiểm tra cạnh tức thì thì có thể dùng tập hàng xóm dạng hash set cho mỗi đỉnh; vẫn phải tính chi phí thêm/xóa và bộ nhớ. CSR thích hợp hơn cho đợt phân tích dữ liệu đã đóng băng, ít sửa.

Đây là cùng một khái niệm “đồ thị”, nhưng mật độ, số đỉnh, phép toán và tần suất thay đổi dẫn đến quyết định khác nhau.

## 8. Mã giả cho quy trình chọn cấu trúc

Trước khi chọn thuật toán, hãy điền phiếu phân tích:

```text
Data:
    item, key, n, universe_size U (nếu có)
    V, E (nếu là đồ thị)
    duplicate_policy, order_relation

Changes:
    static / append_only / point_update / arbitrary_insert_delete
    write_frequency, consistency_requirement

Queries:
    exact_key / by_index / order_range / prefix / aggregate_range
    neighbors / edge_exists / traversal / priority
    frequency, result_count k, latency_budget

Guarantees:
    correctness, ordering, worst_case_or_expected
    memory_budget, concurrency, snapshot_policy

Candidates:
    construction_cost
    query_cost
    update_cost
    traversal_cost
    persistent_memory + peak_memory
    invariants_to_maintain

Decision:
    discard candidates violating guarantees
    compare total cost under actual workload
    benchmark on representative and adversarial inputs
```

Ví dụ nhánh quyết định cho **đồ thị**:

```text
if V * V fits memory
   and edge-existence queries dominate:
    consider adjacency matrix / bitset
else if E is small relative to V * V
        and graph is mostly static:
    consider CSR
else:
    consider adjacency lists
    if membership queries dominate:
        evaluate per-vertex hash sets
```

Đây là **heuristic** định hướng, không phải thuật toán tự động luôn đúng. Với đồ thị có trọng số, nhiều cạnh trùng hoặc các thao tác đặc biệt, cần tính thêm cách lưu trọng số, ngữ nghĩa trùng cạnh và chi phí cập nhật.

Một bản đánh giá đủ dùng thường có bảng:

| Phương án | Xây dựng | Truy vấn chính | Cập nhật | Bộ nhớ | Bất biến cần giữ |
| --- | --- | --- | --- | --- | --- |
| A | `B_A(n)` | `Q_A(n,k)` | `U_A(n)` | `M_A(n)` | Quy tắc A |
| B | `B_B(n)` | `Q_B(n,k)` | `U_B(n)` | `M_B(n)` | Quy tắc B |

Nếu một truy vấn phải trả `k` phần tử, không thể bỏ chi phí đầu ra tối thiểu `Ω(k)`. Nếu một cập nhật phải đồng bộ nhiều chỉ mục, phải tính cả chi phí đồng bộ vào `U(n)` và kiểm tra bất biến của tất cả chỉ mục.

## 9. Các nhầm lẫn thường gây chọn sai cấu trúc

**Nhầm “tĩnh” với “chỉ có một cách lưu”.** Dữ liệu tĩnh cho phép tiền xử lý mạnh, nhưng vẫn phải chọn chỉ mục đúng với phép toán: prefix sum cho tổng, mảng sắp cho khoảng khóa, hash map cho tra cứu chính xác.

**Nhầm “thưa” với “ít phần tử”.** Một đồ thị có hàng triệu cạnh vẫn có thể thưa nếu `V²` lớn hơn rất nhiều. Một ma trận 10×10 có 60 ô khác 0 có thể dày dù tổng số phần tử nhỏ.

**Chọn ma trận kề chỉ vì kiểm tra cạnh `O(1)`.** Khi `V` rất lớn, `O(V²)` bộ nhớ có thể vượt ngân sách; quét hàng xóm phải kiểm tra cả các ô không có cạnh.

**Chọn danh sách kề mà quên phép `hasEdge`.** Nếu một đỉnh có hàng trăm nghìn hàng xóm và truy vấn kiểm tra cạnh liên tục, tìm tuyến tính trong danh sách có thể tốn kém. Có thể cần hash set hoặc một chỉ mục cạnh bổ sung.

**Cho rằng đầu vào ngẫu nhiên đồng nghĩa thuật toán có bảo đảm tốt.** BST thường có chiều cao thấp với đầu vào ngẫu nhiên phù hợp, nhưng không cân bằng vẫn có thể đạt `O(n)`. Bảng băm có thể gặp va chạm và rehash; phải nêu rõ loại bảo đảm.

**Cho rằng dữ liệu “đã sắp” sẽ mãi sắp.** Một cập nhật giá, một bản ghi đến muộn hoặc thay đổi trường khóa có thể phá bất biến. Cấu trúc phải được cập nhật hoặc xây lại.

**Chỉ đếm thời gian truy vấn mà quên vòng đời dữ liệu.** Sắp mảng tốn chi phí trước nhưng có lợi cho truy vấn lặp lại; duy trì cây giúp cập nhật có thứ tự nhưng tăng chi phí ghi và bộ nhớ.

**Đồng nhất biểu diễn thưa với giá trị bằng 0.** Một mục vắng mặt, một cạnh không tồn tại và một giá trị số 0 có thể có ngữ nghĩa khác nhau. Thiết kế phải lưu được sự khác biệt nếu yêu cầu nghiệp vụ cần.

## 10. Tự kiểm tra bằng bốn tình huống

### Tình huống 1 — Tra cứu mã sinh viên

Có 50.000 mã số nguyên nằm rải rác trong miền 0 đến một tỷ. Chương trình phải thêm, xóa và hỏi “mã có tồn tại không?” rất thường xuyên, không cần xuất theo thứ tự.

**Hỏi:** Mảng trực tiếp, mảng sắp hay hash set là ứng viên tự nhiên nhất?

**Gợi ý giải:** hash set thường phù hợp hơn: bộ nhớ tỷ lệ số khóa hiện có và tra cứu/thêm/xóa kỳ vọng `O(1)`. Mảng trực tiếp có thể tiêu tốn `O(U)` quá lớn; mảng sắp phải dịch phần tử khi chèn/xóa. Nếu có yêu cầu chặn trên trường hợp xấu hoặc thứ tự khóa, cân nhắc cây cân bằng.

### Tình huống 2 — Đồ thị thưa, chỉ dùng để phân tích mỗi đêm

Đồ thị có 100.000 đỉnh và 200.000 cạnh, sau khi nạp sẽ chạy BFS nhiều lần, không cập nhật cạnh.

**Hỏi:** Danh sách kề, CSR hay ma trận kề?

**Gợi ý giải:** CSR/danh sách kề có bộ nhớ `O(V+E)`, duyệt hàng xóm nhanh và BFS `O(V+E)`. CSR hấp dẫn khi đã đóng băng dữ liệu và muốn bố cục liên tiếp; ma trận kề cần `O(V²)` bộ nhớ nên khó phù hợp.

### Tình huống 3 — Dãy tĩnh nhưng giá trị đến không theo thứ tự

Có một triệu giá ngẫu nhiên, sau đó 100.000 lần hỏi “các giá trong `[a,b]` theo thứ tự tăng dần”.

**Hỏi:** Có cần duy trì cây cân bằng để giải quyết truy vấn không?

**Gợi ý giải:** không nhất thiết. Vì dữ liệu tĩnh, có thể sắp mảng một lần trong `O(n log n)`, rồi tìm hai biên và xuất `k` kết quả trong `O(log n+k)` mỗi lần. Cây có lợi hơn nếu còn cập nhật thường xuyên.

### Tình huống 4 — Dãy có nhiều cập nhật

Có 500.000 phần tử, mỗi giây 2.000 cập nhật điểm và 3.000 truy vấn tổng đoạn.

**Hỏi:** Prefix sum có phải lựa chọn tốt chỉ vì truy vấn `O(1)` không?

**Gợi ý giải:** phải tính cả cập nhật `O(n)` của prefix sum. Fenwick tree/segment tree cho mỗi cập nhật và truy vấn `O(log n)`, thường là ứng viên phù hợp hơn. Đo ở quy mô thực và kiểm tra ràng buộc thời gian/bộ nhớ trước khi chốt.

## Kết luận

**Tĩnh hay động** cho biết có thể tiền xử lý và giữ nguyên chỉ mục hay phải duy trì chúng sau mỗi thay đổi. **Dày hay thưa** quyết định có nên cấp phát toàn bộ không gian dữ liệu hay chỉ lưu phần thực sự tồn tại. **Có thứ tự hay ngẫu nhiên** giúp đánh giá tìm nhị phân, cây cân bằng, bảng băm, heap và rủi ro từ phân bố khóa.

Khi kết hợp ba trục với **phép toán chủ đạo, bất biến, độ phức tạp thời gian và bộ nhớ**, việc chọn cấu trúc dữ liệu trở thành một quyết định thiết kế có thể giải thích và kiểm chứng. Hãy đo trên tải công việc đại diện, tính cả chi phí xây dựng/cập nhật/duyệt và đổi cấu trúc khi đặc điểm dữ liệu thay đổi đáng kể.
