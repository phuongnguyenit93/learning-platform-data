# So sánh tra cứu theo chỉ số, khóa, thứ tự, tiền tố và khoảng

Cùng là yêu cầu “tìm dữ liệu”, nhưng **lấy phần tử thứ 25**, **tìm đơn hàng có mã X**, **lấy sản phẩm có giá thấp nhất**, **tìm tên bắt đầu bằng “da”**, và **tính tổng doanh số từ ngày A đến ngày B** là năm bài toán khác nhau. Chúng cần những thông tin đầu vào khác nhau, trả về những kiểu kết quả khác nhau và thường được tối ưu bởi những cấu trúc dữ liệu khác nhau.

Trong chương *Lựa chọn và thiết kế*, việc phân biệt các kiểu tra cứu này giúp chuyển yêu cầu ứng dụng thành đúng phép toán của mảng, bảng băm, cây, trie hay cấu trúc tổng hợp khoảng. Bài học tập trung vào **ngữ nghĩa phép toán, bất biến cần giữ, độ phức tạp thời gian và bộ nhớ**, rồi dùng những yếu tố ấy để chọn thiết kế phù hợp.

## 1. Năm câu hỏi, năm kiểu tra cứu

Giả sử một hệ thống lưu các sản phẩm, mỗi sản phẩm có `sku` (mã duy nhất), `name` (tên) và `price` (giá). Ta có thể hỏi:

| Kiểu tra cứu | Ví dụ | Đầu vào quyết định | Kết quả cần trả |
| --- | --- | --- | --- |
| **Theo chỉ số** | “Sản phẩm ở vị trí 12 là gì?” | Vị trí `i` trong một dãy | Một phần tử theo vị trí |
| **Theo khóa** | “Sản phẩm có `sku = "P104"`?” | Khóa định danh chính xác `k` | Một phần tử hoặc tập phần tử có khóa phù hợp |
| **Theo thứ tự** | “Sản phẩm có giá thấp nhất tiếp theo?” | Quan hệ so sánh toàn phần | Cực trị, phần tử kế tiếp, cận dưới, xếp hạng |
| **Theo tiền tố** | “Tên bắt đầu bằng `"ban"`?” | Phần đầu của chuỗi khóa | Các khóa khớp tiền tố |
| **Theo khoảng** | “Giá từ 100 đến 300?” hoặc “Tổng doanh số ngày 5–10?” | Hai biên `[a,b]` hoặc `[l,r]` | Các bản ghi thuộc khoảng **hoặc** kết quả tổng hợp của đoạn |

Đặc biệt, từ “khoảng” có **hai ý nghĩa cần phân biệt**:

- **Khoảng giá trị khóa:** lấy mọi bản ghi có khóa thỏa `a ≤ key ≤ b`. Số bản ghi được xuất ra ảnh hưởng trực tiếp đến thời gian chạy.
- **Khoảng vị trí cần tổng hợp:** tính tổng, nhỏ nhất, lớn nhất, v.v. của các phần tử `A[l..r]`. Có thể trả một giá trị duy nhất mà không phải xuất toàn bộ phần tử.

Một cấu trúc giải tốt kiểu đầu chưa chắc giải tốt kiểu sau. Chẳng hạn, cây tìm kiếm theo khóa giúp liệt kê các giá trị trong khoảng; segment tree giúp tính tổng một đoạn chỉ số hiệu quả, nhưng không tự tạo chỉ mục tra cứu theo tên.

## 2. Tra cứu theo chỉ số: biết vị trí, truy cập trực tiếp

Dạng điển hình là:

```text
+-------+-------+-------+-------+-------+
| A[0]  | A[1]  | A[2]  | A[3]  | A[4]  |
+-------+-------+-------+-------+-------+
   12      19      23      31      42

get(3) → 31
```

Với **mảng**, địa chỉ của phần tử ở vị trí `i` được tính từ vị trí đầu và kích thước một phần tử; `A[i]` vì vậy có thời gian truy cập **`O(1)`**. **Mảng động** vẫn hỗ trợ điều này dù đôi khi phải cấp phát vùng nhớ mới khi tăng dung lượng.

Chi phí của mảng động thường gặp:

| Thao tác | Độ phức tạp |
| --- | --- |
| Đọc/ghi `A[i]` khi chỉ số hợp lệ | `O(1)` |
| Thêm phần tử cuối dãy | `O(1)` **khấu hao**, có lần tăng dung lượng mất `O(n)` |
| Chèn/xóa ở đầu hoặc giữa | `O(n)` vì phải dời phần tử |
| Tìm một giá trị chưa biết vị trí trong mảng không sắp xếp | `O(n)` |
| Duyệt toàn bộ dãy | `O(n)`, thường thuận lợi nhờ tính liên tục bộ nhớ |

**Bất biến:** các phần tử được ánh xạ theo chỉ số trong dải `0..n-1`, thứ tự vật lý/logic được bảo toàn theo giao diện của dãy.

Điểm dễ nhầm là **chỉ số không phải mã định danh ổn định**. Nếu xóa `A[1]` khỏi dãy đang giữ thứ tự, phần tử từng ở `A[2]` sẽ chuyển thành `A[1]`. Bởi vậy, không nên dùng vị trí trong một danh sách thường xuyên chèn/xóa để làm `id` bền vững cho người dùng.

Nếu cần ánh xạ một `id` đến vị trí mảng, có thể duy trì `idToIndex`. Nhưng mọi thao tác khiến vị trí thay đổi phải cập nhật ánh xạ đó. Một phương án khác là dùng các ô cố định với cơ chế quản lý vị trí trống và phiên bản định danh; khi ấy cần thiết kế quy tắc tái sử dụng ô để không truy cập nhầm đối tượng đã bị xóa.

**Khi phù hợp:** mô phỏng dãy số, xử lý theo lô, bảng kích thước cố định, truy cập ngẫu nhiên theo vị trí và duyệt tuần tự. **Khi chưa đủ:** chỉ biết khóa nghiệp vụ như `sku` nhưng không biết phần tử nằm ở vị trí nào.

## 3. Tra cứu theo khóa: tìm đúng định danh

Tra cứu theo khóa có dạng:

```text
getBySku("P104") → Product { sku: "P104", ... }
contains("P104") → true
delete("P104")
```

### Bảng băm: tối ưu truy cập chính xác

**Hash map / hash set** dùng hàm băm để định vị vùng lưu trữ của khóa. Với hàm băm phù hợp, quản lý hệ số tải và xử lý va chạm đúng cách, tra cứu, thêm, xóa theo khóa thường có chi phí **`O(1)` kỳ vọng/trung bình**.

Các điều kiện quan trọng:

- Hàm so sánh bằng nhau và hàm băm phải tương thích: nếu `a == b` thì `hash(a) == hash(b)`.
- Khóa dùng trong bảng phải có biểu diễn/giá trị băm ổn định khi đã được chèn; thay đổi khóa mà không cập nhật bảng có thể khiến mục cũ không tìm thấy.
- Va chạm xảy ra khi các khóa khác nhau rơi vào cùng vị trí; triển khai phải xử lý chính xác.
- Trong trường hợp xấu của bảng băm thông dụng, thời gian một thao tác có thể tăng đến **`O(n)`**. Rehash đôi khi phải xử lý nhiều phần tử cùng lúc.

Tập hợp (set) dùng khi chỉ hỏi “có tồn tại không?”, còn ánh xạ (map) dùng khi từ khóa cần lấy ra dữ liệu gắn với khóa. Nếu nhiều bản ghi cùng khóa là hợp lệ, phải chọn rõ chính sách: `key → danh sách bản ghi`, multimap hoặc khóa ghép có tính duy nhất.

**Không suy ra thứ tự từ bảng băm.** Một hash map thông thường không bảo đảm duyệt khóa tăng dần, tìm `lowerBound` hay lấy các khóa trong khoảng một cách hiệu quả. Có những biến thể duy trì thứ tự chèn, nhưng *thứ tự chèn* cũng không đồng nghĩa *thứ tự tăng dần của khóa*.

### Cây tìm kiếm: đổi chi phí để có thứ tự

Với **cây tìm kiếm nhị phân tự cân bằng** như AVL hoặc red-black tree, nếu khóa có thứ tự so sánh nhất quán, `find(k)`, `insert(k)`, `delete(k)` đều có chặn trên **`O(log n)` trường hợp xấu**. Đổi lại, cây thường phải lưu thêm liên kết/cấu trúc nút và có chi phí so sánh, cân bằng.

Nếu yêu cầu chỉ là tra cứu khóa chính xác và chấp nhận bảo đảm kỳ vọng, bảng băm thường là ứng viên mạnh. Nếu còn cần duyệt có thứ tự, cận dưới hoặc khoảng khóa, cây có thứ tự có lợi thế rõ ràng.

## 4. Tra cứu theo thứ tự: cực trị, cận, kế tiếp và xếp hạng

Khi ứng dụng cần so sánh phần tử, phải xác định **thứ tự nào** đang được dùng. Với sản phẩm, có thể là `(price, sku)` thay vì chỉ `price`, vì nhiều sản phẩm có cùng giá.

Ví dụ các phép toán:

- `min()`, `max()`: phần tử nhỏ nhất/lớn nhất.
- `lowerBound(x)`: phần tử đầu tiên có khóa **≥ `x`**.
- `upperBound(x)`: phần tử đầu tiên có khóa **> `x`**.
- `predecessor(x)`, `successor(x)`: phần tử liền trước/liền sau theo thứ tự.
- `rank(x)`: có bao nhiêu phần tử nhỏ hơn `x`.
- `select(i)`: phần tử có thứ hạng `i` (cần quy ước xếp hạng từ 0 hay 1).

Giả sử các khóa đã được sắp:

```text
[10, 20, 20, 35, 80]

lowerBound(20) → vị trí 1
upperBound(20) → vị trí 3
lowerBound(21) → giá trị 35
```

**Mảng sắp xếp** rất hợp nếu ít cập nhật: tìm nhị phân `O(log n)` lần so sánh, nhưng chèn/xóa vẫn có thể phải dịch `O(n)` phần tử. Các khóa trùng nhau đòi hỏi quy tắc vị trí bắt đầu/kết thúc rõ ràng.

**Cây tìm kiếm tự cân bằng** hợp khi vừa phải cập nhật, vừa phải hỏi cận/kế tiếp: tìm cận dưới `O(log n)`; chèn/xóa `O(log n)`; duyệt `k` phần tử liên tiếp từ một cận có thể thực hiện trong `O(log n + k)` với bộ duyệt phù hợp.

**Heap** chỉ tối ưu một phần của truy vấn có thứ tự: min-heap có `peekMin() = O(1)` và `extractMin() = O(log n)`, nhưng không hỗ trợ tìm tùy ý theo khóa, `lowerBound` hay duyệt tăng dần hiệu quả như cây tìm kiếm. Việc thay đổi độ ưu tiên của một phần tử tùy ý cũng đòi hỏi cách tìm vị trí của phần tử đó.

**Xếp hạng và chọn theo thứ hạng cần chú ý:** cây tìm kiếm tự cân bằng thông thường không tự bảo đảm `rank`/`select` trong `O(log n)`. Muốn vậy có thể bổ sung **kích thước cây con** ở mỗi nút, duy trì kích thước khi thêm/xóa/xoay; đây là *order-statistic tree*. Tính đúng đắn của kích thước cây con là một bất biến mới, cần kiểm thử riêng.

### Chọn khóa so sánh để tránh kết quả mơ hồ

Nếu cần “20 sản phẩm rẻ nhất”, so sánh chỉ theo `price` có thể bỏ mất các phần tử cùng giá trong một tập không cho khóa trùng. Khóa ghép `(price, sku)` tạo thứ tự xác định khi `sku` duy nhất.

Tương tự, truy vấn “20 đơn hàng mới nhất” nên định nghĩa rõ thứ tự như `(createdAt DESC, orderId DESC)` và cách xử lý các bản ghi có cùng thời điểm.

## 5. Tra cứu theo tiền tố: đi theo phần đầu của chuỗi

Tra cứu tiền tố hỏi liệu một chuỗi có bắt đầu bằng một chuỗi khác:

```text
Keys = {"ban", "banana", "bank", "cat", "cater"}
prefixSearch("ban") → {"ban", "banana", "bank"}
prefixSearch("ca")  → {"cat", "cater"}
prefixSearch("an")  → ∅   // "an" là chuỗi con, không phải tiền tố
```

**Trie** (cây tiền tố) lưu các cạnh theo ký tự/đơn vị của khóa; những khóa cùng tiền tố chia sẻ đường đi chung. Nút kết thúc khóa cần được đánh dấu để phân biệt `"ban"` với `"banana"`.

Với tiền tố có độ dài `L`:

- Tìm vị trí nút biểu diễn tiền tố cần đi qua khoảng `L` bước trong mô hình trie có truy cập cạnh hiệu quả.
- Kiểm tra một khóa đầy đủ cũng phụ thuộc độ dài khóa.
- Liệt kê tất cả kết quả phải trả thêm chi phí duyệt các nhánh và **xuất kết quả**; không thể gọi toàn bộ `prefixSearch` là `O(L)` nếu có hàng nghìn kết quả.
- Bộ nhớ phụ thuộc số nút/cạnh và cách biểu diễn con: mảng con kích thước bảng chữ cái truy cập đơn giản nhưng có thể tốn bộ nhớ; map cạnh tiết kiệm ô trống hơn nhưng thêm chi phí tra cứu.

Cụ thể, nếu đường đi qua tiền tố có `L` đơn vị và phải thăm `S` nút dưới nhánh tương ứng để tạo kết quả, mô hình đơn giản có chi phí `O(L + S)` khi mỗi bước tìm cạnh là `O(1)`. Với trie nén (radix tree), số nút và cách so sánh đoạn chuỗi thay đổi.

### Tiền tố trên dữ liệu đã sắp xếp

Không nhất thiết phải dùng trie. Nếu các chuỗi được lưu theo **thứ tự từ điển**, những khóa cùng tiền tố tạo thành một đoạn liên tiếp. Có thể:

1. Dùng tìm kiếm nhị phân để xác định khóa đầu tiên không nhỏ hơn tiền tố.
2. Duyệt tiếp trong đoạn trong khi khóa còn bắt đầu bằng tiền tố.
3. Dừng ở khóa đầu tiên không khớp.

Với `n` chuỗi, bước tìm ranh giới dùng `O(log n)` lần so sánh; **mỗi lần so sánh chuỗi** lại có thể mất thời gian theo độ dài phần được so sánh. Việc liệt kê còn mất thời gian theo số khóa/độ dài dữ liệu xuất ra.

Cách này thuận lợi khi đã có chỉ mục chuỗi có thứ tự hoặc khi dữ liệu ít thay đổi. Trie đáng cân nhắc khi các truy vấn tiền tố rất thường xuyên hoặc khi cần mở rộng chức năng gợi ý theo cây tiền tố.

### Chuẩn hóa chuỗi là một phần của tính đúng

Với tên tiếng Việt, phải quyết định rõ:

- Có phân biệt chữ hoa và chữ thường không?
- Có phân biệt dấu thanh/dấu phụ không?
- Chuỗi Unicode được chuẩn hóa theo dạng nào (ví dụ NFC)?
- Độ dài khóa `L` đếm byte UTF-8, mã điểm Unicode hay ký tự người dùng cảm nhận?

Nếu dữ liệu được chuẩn hóa khi lưu nhưng không chuẩn hóa khi hỏi, `prefixSearch` có thể bỏ sót kết quả. Cần dùng **cùng quy tắc biến đổi và so sánh** ở cả lúc tạo chỉ mục lẫn lúc tra cứu. Trie thông thường chỉ xử lý **tiền tố**; tìm chuỗi con, từ gần đúng hoặc tìm kiếm toàn văn là các bài toán khác.

## 6. Tra cứu theo khoảng: phân biệt “liệt kê” và “tổng hợp”

### 6.1. Liệt kê bản ghi có khóa trong khoảng

Ví dụ: `rangeByPrice(100, 300)` trả tất cả sản phẩm có `100 ≤ price ≤ 300`, sắp theo giá tăng dần.

- **Mảng không sắp:** phải kiểm tra `n` phần tử → `O(n)` rồi thêm chi phí xuất kết quả.
- **Mảng sắp theo giá:** tìm biên bằng tìm nhị phân, sau đó duyệt `k` kết quả → `O(log n + k)` theo số phép so sánh/truy cập, nhưng cập nhật vị trí có thể `O(n)`.
- **Cây tìm kiếm tự cân bằng theo `(price, sku)`:** tìm biên và duyệt `k` phần tử → `O(log n + k)`, đồng thời thêm/xóa `O(log n)`.
- **Hash map theo `sku`:** không có thông tin về khoảng giá; để trả đúng mọi kết quả thường phải duyệt toàn bộ `O(n)`.

Ở đây `k` là số **bản ghi thực sự trả về**. Nếu trả 50.000 bản ghi, bất kỳ phương án nào cũng phải dành ít nhất `Ω(k)` thời gian để xuất 50.000 bản ghi. Tối ưu chủ yếu là tránh kiểm tra các bản ghi ngoài khoảng.

### 6.2. Tổng hợp giá trị trên đoạn chỉ số

Giả sử `A[i]` là doanh số ngày thứ `i`. Bài toán:

```text
A = [4, 7, 2, 9, 5, 3]
sum(1, 4) = 7 + 2 + 9 + 5 = 23    // biên đóng
update(2, 10)                     // thay A[2] từ 2 thành 10
sum(1, 4) = 7 + 10 + 9 + 5 = 31
```

Có nhiều ứng viên tùy **tần suất cập nhật** và **phép tổng hợp**:

| Cấu trúc | Tiền xử lý | Tổng đoạn `[l,r]` | Cập nhật một điểm | Bộ nhớ phụ |
| --- | --- | --- | --- | --- |
| Mảng gốc, cộng trực tiếp | `O(1)` | `O(r-l+1)` | `O(1)` | `O(1)` |
| Prefix sum | `O(n)` | `O(1)` | `O(n)` khi cập nhật giá trị bất kỳ | `O(n)` |
| Fenwick tree (BIT) cho tổng | `O(n)` với cách xây dựng tuyến tính | `O(log n)` | `O(log n)` | `O(n)` |
| Segment tree cho tổng | `O(n)` | `O(log n)` | `O(log n)` | `O(n)` |

**Prefix sum** lưu `P[0]=0` và `P[i+1]=P[i]+A[i]`. Khi đó:

```text
sum(l, r) = P[r + 1] - P[l]   // 0 ≤ l ≤ r < n
```

Công thức đúng nhờ phép cộng có phép trừ tương ứng. Nếu bài toán là `min(l,r)` thay vì tổng, không thể thay bằng “hiệu hai prefix-min”.

**Fenwick tree** đặc biệt gọn cho cập nhật điểm và truy vấn tổng tiền tố/tổng đoạn; thông thường truy vấn tổng đoạn thực hiện qua hiệu hai tổng tiền tố.

**Segment tree** hỗ trợ nhiều phép tổng hợp có tính kết hợp (associative) như tổng, min, max, gcd, cùng phần tử đơn vị thích hợp. Nút cha lưu kết quả gộp từ hai nút con; nếu cập nhật một điểm, các nút trên đường đi đến gốc phải được cập nhật để giữ bất biến này.

Với truy vấn tổng hợp trên **giá trị khóa** không phải chỉ số nguyên liên tiếp, có thể cần nén tọa độ hoặc một cây tìm kiếm có thông tin tổng hợp ở cây con. Segment tree trên chỉ số không tự giải quyết việc ánh xạ một giá trị khóa tùy ý sang vị trí.

### 6.3. Khi khoảng là nhiều chiều

“Tìm mọi địa điểm trong hình chữ nhật” khác với khoảng một chiều: cần kiểm tra nhiều tọa độ, đôi khi dùng k-d tree, R-tree hoặc chỉ mục không gian khác. Chi phí phụ thuộc kích thước dữ liệu, phân bố điểm và hình dạng truy vấn. Không nên áp dụng nguyên xi bảo đảm `O(log n + k)` của cây một chiều cho mọi truy vấn không gian.

## 7. Đặt cạnh nhau: chọn theo phép toán

Bảng dưới dùng mô hình dữ liệu trong RAM và bỏ qua chi phí xuất chuỗi dài; `n` là số phần tử, `k` là số kết quả. Ký hiệu “—” chỉ rằng cấu trúc không hỗ trợ trực tiếp theo mục tiêu tra cứu đó, chứ không phải bất khả thi.

| Phép toán chủ đạo | Ứng viên thường phù hợp | Chi phí tra cứu tiêu biểu | Lưu ý quan trọng |
| --- | --- | --- | --- |
| `A[i]` | Mảng / mảng động | `O(1)` | Vị trí có thể thay đổi khi chèn/xóa |
| `get(key)` chính xác | Hash map | Kỳ vọng `O(1)` | Không mặc định có thứ tự; có thể `O(n)` trường hợp xấu |
| `get(key)` và duyệt tăng dần | Cây tìm kiếm tự cân bằng | `O(log n)` | Cần thứ tự so sánh nhất quán |
| `lowerBound(key)` | Mảng sắp / cây cân bằng | `O(log n)` | Mảng sắp có cập nhật `O(n)` |
| `rank(key)` / `select(i)` khi cập nhật thường xuyên | Cây thứ tự thống kê | `O(log n)` | Phải duy trì kích thước cây con |
| `peekMin()` rồi `extractMin()` | Min-heap | `O(1)` / `O(log n)` | Không thay thế chỉ mục tìm khóa bất kỳ |
| `startsWith(prefix)` | Trie / chỉ mục chuỗi sắp | Phụ thuộc `L`, số nút duyệt và kết quả | Cần chuẩn hóa và so sánh chuỗi nhất quán |
| `range(a,b)` liệt kê bản ghi | Cây cân bằng / mảng sắp | `O(log n + k)` | Phải chọn khóa sắp phù hợp |
| `sum(l,r)`, dữ liệu tĩnh | Prefix sum | `O(1)` sau xây dựng `O(n)` | Cập nhật một điểm có thể `O(n)` |
| `sum(l,r)` và cập nhật điểm | Fenwick / segment tree | `O(log n)` | Cần giữ bất biến tổng hợp |
| `min(l,r)` và cập nhật điểm | Segment tree | `O(log n)` | Prefix sum thông thường không đáp ứng |

**Quy tắc:** trước tiên loại ứng viên không thỏa ngữ nghĩa và bảo đảm bắt buộc, rồi so *chi phí của toàn bộ tải công việc* (tra cứu, cập nhật, bộ nhớ và quản lý các chỉ mục phụ). Một truy vấn rất nhanh nhưng khiến tất cả cập nhật tốn kém chưa chắc là lựa chọn tốt.

## 8. Ví dụ thiết kế: danh mục sản phẩm nhiều cách tìm

Hệ thống có 300.000 sản phẩm. Các yêu cầu:

1. Tìm sản phẩm chính xác theo `sku` rất thường xuyên.
2. Liệt kê các sản phẩm có giá trong `[minPrice, maxPrice]`, sắp tăng dần; giá có thể trùng.
3. Gợi ý tên sản phẩm theo tiền tố đã chuẩn hóa.
4. Đọc phần tử thứ `i` trong **danh sách kết quả của một truy vấn phân trang**, chứ không mặc định `i` là định danh sản phẩm.
5. Thêm, sửa giá, sửa tên, xóa sản phẩm trong lúc hệ thống hoạt động.

Nếu chỉ dùng mảng các sản phẩm, mỗi truy vấn theo `sku` hoặc tiền tố phải tìm tuyến tính khi không có chỉ mục. Nếu chỉ dùng hash map theo `sku`, truy vấn khoảng giá và gợi ý tiền tố vẫn khó. Một phương án dùng **nhiều chỉ mục chuyên biệt**:

```text
sourceOfTruth: các Product theo sku
bySku:   HashMap<SKU, ProductRef>
byPrice: BalancedBST<(Price, SKU)>
byName:  Trie<NormalizedName, Set<SKU>>

Khi tìm SKU:          bySku.get(sku)
Khi lọc theo giá:     byPrice.range((lo, -∞), (hi, +∞))
Khi gợi ý tên:        byName.prefixSearch(normalize(prefix))
Khi truy cập vị trí:  resultPage[i]  // mảng kết quả đã được xác định trước
```

`ProductRef` là tham chiếu đến bản ghi sản phẩm; không bắt buộc sao chép toàn bộ đối tượng vào mọi chỉ mục. `Set<SKU>` trong trie giúp xử lý nhiều sản phẩm có cùng tên. Ký hiệu `-∞` và `+∞` ở mã giả chỉ các cận so sánh bao gồm mọi `sku` có thể có với cùng một mức giá; triển khai thực tế cần định nghĩa khóa sentinel hoặc dùng phương thức so sánh cận tương đương.

**Bất biến liên chỉ mục:** với mỗi sản phẩm `p` đang tồn tại, `bySku[p.sku]` phải trỏ đúng `p`, `byPrice` phải chứa duy nhất khóa `(p.price, p.sku)`, và nhánh tên chuẩn hóa tương ứng trong `byName` phải chứa `p.sku`. Sản phẩm không còn tồn tại không được xuất hiện trong chỉ mục nào.

Khi sửa giá, quy trình hợp lệ về mặt logic là **xóa khóa giá cũ, cập nhật sản phẩm, thêm khóa giá mới**. Khi sửa tên, cũng phải xóa liên kết tiền tố cũ và chèn liên kết mới. Cần dùng giao dịch, khóa hoặc cơ chế snapshot phù hợp để thao tác đồng thời không quan sát trạng thái cập nhật dở dang; nếu có lỗi giữa chừng phải phục hồi tính nhất quán.

Về độ phức tạp dưới các giả định điển hình:

| Thao tác | Chi phí nổi bật |
| --- | --- |
| Tìm theo `sku` | Kỳ vọng `O(1)` trên hash map |
| Liệt kê `k` sản phẩm theo khoảng giá | `O(log n + k)` trên cây |
| Tìm nút tiền tố độ dài `L` | Khoảng `O(L)` với tra cứu cạnh hiệu quả, **cộng** công sức liệt kê kết quả |
| Sửa giá | Ít nhất các thao tác cập nhật cây `O(log n)`, cùng chi phí cập nhật các nơi liên quan |
| Sửa tên | Chi phí phụ thuộc độ dài tên cũ/mới và cách trie lưu danh sách `sku` |
| Xem `resultPage[i]` | `O(1)` sau khi danh sách kết quả đã được tạo |

Thiết kế này có thêm bộ nhớ và chi phí duy trì nhiều bất biến, nên **không phải lựa chọn mặc định cho mọi ứng dụng**. Nếu chỉ có vài trăm sản phẩm, số truy vấn thấp hoặc sản phẩm không bao giờ được tìm theo tiền tố, một danh sách và một hash map có thể hợp lý hơn.

## 9. Bài tập suy luận và kiểm tra bất biến

**Bài 1 — Mảng có thay được map?** Có một mảng 50.000 người dùng, mỗi người có `userId` ngẫu nhiên và thường tìm theo `userId`. Phần tử thứ `i` không liên quan `userId=i`. Chỉ ra vì sao truy cập `A[i]` `O(1)` không giải quyết `getByUserId`. Hãy đề xuất một chỉ mục và nêu chi phí cập nhật khi xóa người dùng.

*Gợi ý đáp án:* cần ánh xạ từ `userId` sang bản ghi hoặc vị trí. Với hash map, tra cứu kỳ vọng `O(1)`. Nếu map lưu **vị trí**, việc xóa và dồn mảng khiến nhiều chỉ số đổi, phải cập nhật map; nếu map lưu **tham chiếu bền vững**, phải quản lý vòng đời đối tượng để không giữ tham chiếu không hợp lệ.

**Bài 2 — Số kết quả ảnh hưởng ra sao?** Truy vấn `range(100,200)` trên cây cân bằng trả 40.000 bản ghi. Có thể cam kết tổng thời gian `O(log n)` không?

*Đáp án:* không. Duyệt và trả `k=40.000` kết quả yêu cầu tối thiểu `Ω(k)` thao tác xuất kết quả; chặn phù hợp là `O(log n+k)` trong mô hình cây cân bằng và bộ duyệt hiệu quả.

**Bài 3 — Thứ hạng có miễn phí?** Cây AVL chỉ lưu `key` và liên kết trái/phải. Muốn trả phần tử nhỏ thứ 1.000 bằng `O(log n)` thì thiếu thông tin gì?

*Đáp án:* thiếu kích thước cây con. Phải bổ sung và duy trì kích thước ấy qua thao tác chèn/xóa/xoay để đi xuống cây theo thứ hạng.

**Bài 4 — Tổng đoạn thay đổi theo thời gian.** Có một triệu số, 70% truy vấn tổng đoạn và 30% cập nhật điểm. Nên dùng prefix sum thuần túy hay Fenwick tree?

*Định hướng:* prefix sum trả lời nhanh nhưng mỗi cập nhật có thể buộc sửa `O(n)` tổng tiền tố; Fenwick tree cho cả cập nhật và truy vấn khoảng `O(log n)`. Đánh giá thêm bộ nhớ, số phép toán, giới hạn thời gian và dữ liệu thực tế.

## 10. Quy trình chốt lựa chọn

Hãy ghi mô tả truy vấn trước khi chọn tên cấu trúc:

```text
Dữ liệu:       n phần tử; có thể trùng khóa không?
Đầu vào:       vị trí i / khóa k / cận x / tiền tố p / đoạn [l,r]?
Đầu ra:        một phần tử, danh sách k phần tử, hay một giá trị tổng hợp?
Thứ tự:        có cần sắp tăng dần, có quy tắc phá hòa không?
Cập nhật:      thêm/xóa/sửa xảy ra bao nhiêu lần?
Bảo đảm:       kỳ vọng, khấu hao hay trường hợp xấu?
Bộ nhớ:        tối đa được duy trì bao nhiêu chỉ mục?
Bất biến:      điều gì phải luôn đúng sau mọi thao tác?
```

Sau đó chọn hai hoặc ba ứng viên, tính cả chi phí xây dựng và duy trì chỉ mục, rồi kiểm tra lại bằng dữ liệu có quy mô và phân bố phù hợp. Với hệ thống lưu trữ trên đĩa, B-tree/B+ tree có thể được dùng để giảm số lần đọc khối; với hệ thống nhiều luồng, thời gian khóa và tính nhất quán có thể chi phối hơn khác biệt `O(1)` so với `O(log n)`.

**Điều cần nhớ:** “tra cứu” không phải một phép toán duy nhất. Theo **chỉ số** cần vị trí; theo **khóa** cần định danh; theo **thứ tự** cần quan hệ so sánh; theo **tiền tố** cần cấu trúc của chuỗi; theo **khoảng** phải xác định trả các phần tử hay tổng hợp một đoạn. Khi nêu đúng đầu vào, đầu ra, bất biến và loại bảo đảm độ phức tạp, ta có cơ sở vững chắc để lựa chọn mảng, bảng băm, cây, trie, Fenwick tree, segment tree hoặc phối hợp nhiều chỉ mục.
