# Bắt đầu từ phép toán chủ đạo và các bảo đảm cần thiết

Khi thiết kế một hệ thống, câu hỏi đầu tiên không nên là “nên dùng mảng, bảng băm hay cây?”, mà là **“dữ liệu sẽ được thao tác như thế nào, thao tác nào chi phối chi phí, và hành vi nào bắt buộc phải được bảo đảm?”**. Đây là điểm khởi đầu của việc *lựa chọn và thiết kế* cấu trúc dữ liệu.

Ta đã biết các cấu trúc như mảng, danh sách liên kết, stack, queue, bảng băm, cây, heap và đồ thị có những bất biến và độ phức tạp khác nhau. Bước tiếp theo là biến yêu cầu nghiệp vụ thành một bài toán có thể so sánh các phương án: xác định tập phép toán, tần suất, quy mô dữ liệu, đặc tính khóa, yêu cầu về thứ tự, bộ nhớ và mức bảo đảm thời gian. Một lựa chọn tốt phải giải quyết đúng bài toán đó, thay vì chỉ sở hữu một phép toán nhanh trên lý thuyết.

## 1. Xác định phép toán trước khi chọn cấu trúc

Một cấu trúc dữ liệu cung cấp **những phép toán** với **chi phí** và **ngữ nghĩa** cụ thể. Cùng lưu một tập phần tử, nhưng bài toán truy cập phần tử thứ `i` khác hẳn bài toán tìm phần tử nhỏ nhất hoặc liệt kê các phần tử trong một khoảng khóa.

Hãy viết ra các phép toán dưới dạng đủ cụ thể để có thể phân tích:

| Nhu cầu | Phép toán cần mô tả | Điều cần làm rõ |
| --- | --- | --- |
| Tìm đối tượng theo mã | `get(id)`, `contains(id)` | Khóa có duy nhất không? Có cần kết quả theo thứ tự không? |
| Thêm hoặc xóa | `insert(x)`, `delete(id)` | Thao tác ở cuối, đầu, vị trí bất kỳ hay theo khóa? |
| Truy cập theo vị trí | `get(i)`, `set(i, x)` | Chỉ số có ổn định sau khi thêm/xóa không? |
| Xử lý tuần tự | `push`/`pop`, `enqueue`/`dequeue` | LIFO hay FIFO? Có giới hạn dung lượng không? |
| Ưu tiên công việc | `peekMin()`, `extractMin()` | Chỉ cần cực trị hay cần duyệt toàn bộ theo thứ tự? |
| Tra cứu có thứ tự | `lowerBound(k)`, `range(a, b)` | Phải trả theo thứ tự khóa? Cần bao nhiêu kết quả `k`? |
| Tổng hợp theo khoảng | `rangeSum(l, r)`, `update(i, x)` | Dữ liệu tĩnh hay thay đổi liên tục? |
| Tìm theo tiền tố | `prefixSearch(s)` | Chi phí phụ thuộc độ dài khóa hay số bản ghi? |
| Duyệt quan hệ | `neighbors(v)`, `hasEdge(u, v)` | Đồ thị thưa hay dày đặc? |

Không dừng ở tên phép toán. Chẳng hạn, “xóa nhanh” có thể có hai nghĩa hoàn toàn khác nhau:

- `delete(node)`: đã có tham chiếu trực tiếp đến nút cần xóa.
- `delete(key)`: chỉ có khóa; trước hết phải tìm phần tử.

Với danh sách liên kết đôi, trường hợp thứ nhất thường mất `O(1)` nếu đã có nút và các liên kết hợp lệ; trường hợp thứ hai có thể mất `O(n)` để tìm nút. Việc bỏ qua chi phí tìm kiếm dẫn đến lựa chọn sai.

### Ghi lại tải công việc

Một bản mô tả tối thiểu nên trả lời được:

1. **Quy mô:** số phần tử hiện tại, tối đa và tốc độ tăng; có thể ước lượng `n` hay không?
2. **Tần suất:** tỷ lệ đọc, chèn, sửa, xóa, truy vấn khoảng, lấy cực trị; có đợt tăng đột biến không?
3. **Đặc tính dữ liệu:** khóa là số, chuỗi hay tọa độ; có trùng lặp, phân bố lệch hoặc đầu vào đối kháng không?
4. **Cách truy cập:** ngẫu nhiên, tuần tự, theo khóa, theo thứ tự, theo thời gian, hay theo vùng lân cận?
5. **Môi trường:** dữ liệu ở RAM hay phải truy cập đĩa; một luồng hay nhiều luồng; giới hạn dung lượng và thời gian đáp ứng?

Ví dụ, “quản lý 200.000 đơn hàng” chưa đủ để chọn cấu trúc. Mô tả “90% tìm đơn theo `id`, 7% thêm, 2% hủy, 1% lấy 20 đơn được tạo sớm nhất” đã nêu rõ các phép toán có thể đem ra so sánh.

## 2. Phân biệt phép toán chủ đạo và phép toán hiếm nhưng bắt buộc

**Phép toán chủ đạo** là thao tác xảy ra đủ thường xuyên hoặc tốn đủ nhiều tài nguyên để chi phối chi phí vận hành. Nó không nhất thiết là thao tác có tỷ lệ xuất hiện cao nhất: một truy vấn hiếm nhưng quét toàn bộ tập dữ liệu lớn vẫn có thể gây nghẽn.

Giả sử có `m` thao tác; phép toán loại `i` xuất hiện `q_i` lần và chi phí trung bình ước lượng là `C_i(n)`. Một mô hình khởi đầu là:

```text
Tổng chi phí ước lượng ≈ Σ [q_i × C_i(n)]
                         i
```

Nếu biết xác suất xuất hiện `p_i = q_i / m`, có thể xét chi phí bình quân mỗi yêu cầu là `Σ p_i × C_i(n)`. Mô hình này giúp tìm thao tác quan trọng, nhưng chỉ là **ước lượng**, vì độ phức tạp tiệm cận không cho biết hằng số, bộ nhớ đệm CPU, cấp phát hoặc độ trễ chờ khóa.

Để đánh giá hợp lý, hãy quan sát **cả tổng khối lượng lẫn trường hợp xấu**:

- Một truy vấn `O(n log n)` chỉ chiếm 1% vẫn có thể rất đắt khi `n` lớn.
- Một thao tác `O(1)` trung bình có thể đôi lúc phải cấp phát lại bộ nhớ hoặc tái băm.
- Một yêu cầu cần đáp ứng trong thời hạn cứng không thể được đánh giá chỉ bằng mức trung bình của tất cả yêu cầu.

Ví dụ, nếu ứng dụng chỉ thêm sự kiện vào cuối và duyệt tuần tự, mảng động thường phù hợp nhờ thêm cuối có chi phí khấu hao `O(1)` và dữ liệu liên tiếp trong bộ nhớ. Nếu ứng dụng thường xuyên lấy sự kiện cũ nhất rồi bỏ đi, queue dựa trên bộ đệm vòng sẽ khớp phép toán hơn. Cả hai cùng lưu một dãy sự kiện, nhưng tải công việc khác nhau.

## 3. Viết rõ các bảo đảm bắt buộc

Phép toán “nhanh” chỉ có nghĩa khi nó **đáp ứng đúng kết quả mà hệ thống cần**. Trước khi tối ưu, chia yêu cầu thành hai nhóm:

- **Bảo đảm bắt buộc (hard constraints):** vi phạm thì phương án không dùng được, dù rất nhanh ở các mặt khác.
- **Mục tiêu tối ưu (preferences):** giữa các phương án thỏa bảo đảm, ta ưu tiên phương án có chi phí thấp hơn.

| Khía cạnh | Ví dụ bảo đảm phải làm rõ | Ảnh hưởng đến thiết kế |
| --- | --- | --- |
| Tính đúng đắn | Mỗi `id` là duy nhất; xóa xong không còn tra cứu thấy | Chọn ngữ nghĩa set/map, quy tắc cập nhật và bất biến |
| Thứ tự | Trả đúng 20 phần tử nhỏ nhất theo `(createdAt, id)` | Cần cấu trúc có thứ tự hoặc duy trì chỉ mục bổ sung |
| Thời gian | Truy vấn phải có chặn trên thời gian hoặc độ phức tạp ở trường hợp xấu | Không thể suy bảo đảm `O(1)` tệ nhất từ kỳ vọng của bảng băm |
| Bộ nhớ | Không vượt ngân sách RAM ở số phần tử tối đa | Cân nhắc overhead của nút, bảng băm và chỉ mục phụ |
| Cập nhật | Hai chỉ mục phải cùng phản ánh một tập phần tử | Cần bất biến và xử lý cập nhật nguyên tử |
| Đồng thời | Đọc không được nhìn thấy trạng thái cập nhật dở | Cần khóa, snapshot hoặc cơ chế đồng bộ thích hợp |
| Độ chính xác | Kiểm tra tồn tại không được báo nhầm | Bloom filter đơn lẻ không thay thế được tra cứu chính xác |

Một số thuật ngữ về chi phí cần phân biệt:

- **`O(1)` kỳ vọng (expected):** thời gian kỳ vọng theo giả định về hàm băm, khóa hoặc ngẫu nhiên; một thao tác riêng lẻ vẫn có thể chậm hơn.
- **`O(1)` khấu hao (amortized):** tổng chi phí của một chuỗi thao tác được chia đều; một lần thêm vào mảng động vẫn có thể mất `O(n)` khi phải tăng dung lượng.
- **`O(log n)` trường hợp xấu (worst case):** mỗi thao tác riêng lẻ có chặn trên tiệm cận, khi các điều kiện và bất biến của cấu trúc được duy trì; chẳng hạn tra cứu trong cây tìm kiếm tự cân bằng.

Do đó, câu “bảng băm tìm kiếm `O(1)`” chưa đủ chính xác để cam kết thời hạn xử lý. Với các bảng băm thông dụng, tra cứu thường có chi phí kỳ vọng/trung bình `O(1)` dưới giả định thích hợp, nhưng trường hợp xấu có thể là `O(n)`. Nếu yêu cầu thời gian xử lý có chặn cứng, còn phải xét cả triển khai thực tế, cấp phát bộ nhớ, đồng bộ và hành vi của phần cứng.

## 4. Dùng ma trận phép toán để loại ứng viên

Sau khi biết tải công việc và các bảo đảm, mới đưa những cấu trúc có ý nghĩa vào danh sách ứng viên. Bảng sau dùng các giả định phổ biến với `n` phần tử và `k` kết quả được trả về:

| Cấu trúc | Phép toán nổi bật | Chi phí và giới hạn cần nhớ |
| --- | --- | --- |
| **Mảng / mảng động** | Đọc, ghi theo chỉ số; duyệt tuần tự | Truy cập `O(1)`; thêm cuối mảng động khấu hao `O(1)`; chèn/xóa giữa thường `O(n)` |
| **Danh sách liên kết đôi** | Chèn/xóa khi đã có nút | Sửa liên kết `O(1)`; tìm theo khóa hoặc truy cập phần tử thứ `i` thường `O(n)` |
| **Stack / queue / deque** | LIFO, FIFO, thêm/lấy hai đầu | Cài đặt thích hợp có các thao tác đầu mút `O(1)`; cần xác định quy tắc khi đầy |
| **Bảng băm (hash map/set)** | Tra cứu, thêm, xóa theo khóa | Thông thường kỳ vọng `O(1)`; trường hợp xấu có thể `O(n)`; không tự cung cấp thứ tự khóa |
| **Cây tìm kiếm tự cân bằng** | Tra cứu theo khóa, cận dưới, duyệt có thứ tự | Tìm/chèn/xóa `O(log n)` ở trường hợp xấu; truy vấn khoảng thường `O(log n + k)` |
| **Heap nhị phân** | Xem và lấy phần tử ưu tiên cao nhất/thấp nhất | Xem đỉnh `O(1)`, thêm/lấy đỉnh `O(log n)`; tìm phần tử bất kỳ thường `O(n)` |
| **Trie** | Tra cứu khóa chuỗi, tìm theo tiền tố | Chi phí thường gắn với độ dài khóa `L`; có thể dùng nhiều bộ nhớ |
| **Fenwick tree / segment tree** | Tổng hợp và cập nhật theo khoảng trên dãy chỉ số | Nhiều phép toán truy vấn/cập nhật `O(log n)`; phải phù hợp loại tổng hợp cần hỗ trợ |

Các cấu trúc trên cũng không phải luôn là các lựa chọn loại trừ nhau. **Stack** và **queue** mô tả giao diện, trong khi mảng động, danh sách liên kết hay bộ đệm vòng là các cách hiện thực hóa giao diện đó. Một hệ thống có thể dùng nhiều chỉ mục, mỗi chỉ mục phục vụ một nhóm phép toán.

Với đồ thị, nguyên tắc tương tự: nếu thao tác chính là duyệt hàng xóm trong đồ thị thưa, danh sách kề thường tiết kiệm `O(V + E)` bộ nhớ; nếu cần kiểm tra một cạnh trực tiếp rất thường xuyên và số đỉnh đủ nhỏ, ma trận kề cho phép kiểm tra `O(1)` nhưng tốn `O(V²)` bộ nhớ. Quyết định phải dựa trên tỷ lệ `E/V²` và phép toán thực tế.

### Thứ tự ưu tiên để so sánh

Hãy áp dụng quy tắc sau cho từng ứng viên:

1. **Loại phương án không đáp ứng ngữ nghĩa hoặc bảo đảm cứng.** Hash map đơn lẻ không đáp ứng truy vấn “trả về các khóa nhỏ nhất theo thứ tự” một cách trực tiếp.
2. **Ước tính chi phí trên toàn bộ tải công việc**, gồm cả tạo cấu trúc ban đầu, cập nhật và duy trì chỉ mục.
3. **Kiểm tra bộ nhớ và chi phí hệ thống:** độ phân mảnh, locality, tăng kích thước, thu gom rác, I/O.
4. **Đo ở quy mô và phân bố dữ liệu tương ứng**, rồi chọn phương án đơn giản nhất vẫn đạt yêu cầu.

Nếu một phương án đủ nhanh và có ít bất biến hơn phải duy trì, độ đơn giản cũng là lợi ích đáng kể: ít lỗi, dễ kiểm thử và dễ thay đổi hơn.

## 5. Ví dụ xuyên suốt: chỉ mục đơn hàng đang mở

Giả sử hệ thống quản lý tối đa `n = 200.000` đơn hàng đang mở. Các phép toán dự kiến là:

| Phép toán | Tỷ lệ | Yêu cầu |
| --- | ---: | --- |
| `getById(id)` | 90% | Tìm đúng đơn theo mã duy nhất |
| `create(order)` | 7% | Thêm đơn mới, từ chối `id` trùng |
| `cancel(id)` | 2% | Xóa đơn khỏi tập đang mở |
| `earliest(20)` | 1% | Trả đúng tối đa 20 đơn tạo sớm nhất, theo thứ tự |

Bảo đảm bắt buộc: không có `id` trùng; kết quả `earliest(20)` chính xác; một đơn đã hủy không được xuất hiện trong bất kỳ chỉ mục nào. Giả sử hệ thống chấp nhận thời gian tra cứu kỳ vọng và có đủ bộ nhớ cho một chỉ mục thứ hai.

### Xem từng phương án

**Chỉ dùng hash map theo `id`.** `getById`, thêm, xóa đều rất phù hợp. Nhưng mỗi truy vấn `earliest(20)` phải kiểm tra nhiều đơn và chọn theo thời gian. Cách đơn giản là sắp xếp `n` bản ghi, mất `O(n log n)`; dù dùng một thuật toán chọn top-20 tốt hơn, vẫn phải xét `n` phần tử nếu không có chỉ mục theo thời gian.

**Chỉ dùng cây tìm kiếm theo `(createdAt, id)`.** Duyệt các đơn cũ nhất hiệu quả, nhưng `getById(id)` không có lợi thế vì khóa sắp xếp bắt đầu bằng thời gian, trong khi yêu cầu tra cứu chỉ cung cấp `id`. Không thể khẳng định tìm theo `id` là `O(log n)` trên cây này.

**Duy trì hai chỉ mục.** Kết hợp:

- `byId: HashMap<Id, Order>`, phục vụ truy cập theo mã.
- `byTime: BalancedBST<(CreatedAt, Id)>`, phục vụ duyệt thứ tự thời gian; dùng cặp `(createdAt, id)` để phân biệt các đơn cùng thời điểm.

Các thao tác có chi phí dự kiến:

| Phép toán | Với hai chỉ mục |
| --- | --- |
| `getById(id)` | Kỳ vọng `O(1)` |
| `create(order)` | Kỳ vọng `O(1)` ở hash map và `O(log n)` ở cây ⇒ `O(log n)` kỳ vọng tổng thể |
| `cancel(id)` | Tìm bằng hash map, xóa khóa `(createdAt, id)` khỏi cây ⇒ `O(log n)` kỳ vọng tổng thể |
| `earliest(k)` | Bắt đầu từ phần tử nhỏ nhất và lấy `k` kết quả ⇒ chặn trên `O(log n + k)` |
| Bộ nhớ phụ | Hai chỉ mục đều `O(n)`, ngoài dữ liệu bản ghi |

Hai chỉ mục nhanh ở những hướng truy cập khác nhau, nhưng phải được duy trì theo **một bất biến chung**:

> Với mọi đơn đang mở `o`, `byId[o.id]` tồn tại **khi và chỉ khi** khóa `(o.createdAt, o.id)` tồn tại trong `byTime`. Không chỉ mục nào được chứa đơn đã hủy.

Phác thảo cập nhật:

```text
create(o):
    nếu byId chứa o.id: báo lỗi trùng mã
    thêm (o.createdAt, o.id) vào byTime
    thêm o vào byId
    nếu một bước thất bại: khôi phục cả hai chỉ mục

cancel(id):
    o = byId.get(id)
    nếu không tìm thấy: trả về "không tồn tại"
    xóa (o.createdAt, id) khỏi byTime
    xóa id khỏi byId
    nếu một bước thất bại: khôi phục tính nhất quán

earliest(k):
    duyệt byTime từ khóa nhỏ nhất, lấy tối đa k khóa
    đọc bản ghi tương ứng từ byId và trả theo thứ tự
```

Đây là **mã giả về ý tưởng**; “khôi phục” phải được hiện thực bằng cơ chế giao dịch/rollback phù hợp. Nếu nhiều luồng đọc và ghi đồng thời, cả cập nhật hai chỉ mục lẫn truy vấn phải có cơ chế đồng bộ hoặc snapshot để không nhìn thấy trạng thái dở dang. Nếu cho phép thay đổi `createdAt`, thao tác cập nhật cũng phải xóa khóa thời gian cũ và chèn khóa mới.

### Khi yêu cầu đổi, cấu trúc cũng có thể đổi

- Nếu bỏ hoàn toàn `earliest(k)`, chỉ mục `byTime` có thể trở nên thừa: một hash map đơn giản hơn.
- Nếu `getById` phải có chặn trên trường hợp xấu `O(log n)` ở cấp thuật toán, có thể thay `byId` bằng cây tìm kiếm tự cân bằng theo `id`, với chi phí truy cập tăng lên.
- Nếu chỉ cần xem đơn cũ nhất và xóa đúng đơn đó, không cần duyệt khoảng hay xóa bất kỳ theo `id`, một min-heap có thể phù hợp. Nhưng hủy một đơn tùy ý sẽ cần một chỉ mục vị trí bổ sung hoặc chiến lược xóa lười có kiểm soát.

Điểm cốt lõi không nằm ở tên cấu trúc thắng cuộc, mà ở **quan hệ giữa phép toán, bảo đảm và chi phí duy trì dữ liệu**.

## 6. Các bẫy thường gặp

**Chỉ nhìn vào một phép toán.** Mảng có truy cập theo chỉ số `O(1)`, nhưng nếu chương trình liên tục chèn đầu dãy, phần lớn phần tử phải dịch chuyển. Heap có `extractMin` tốt, nhưng không thay được map khi cần tìm một khóa bất kỳ.

**Đồng nhất ba loại bảo đảm thời gian.** Khấu hao, kỳ vọng và trường hợp xấu trả lời ba câu hỏi khác nhau. Hãy ghi rõ loại chặn và các giả định, đặc biệt với bảng băm, mảng động và cấu trúc ngẫu nhiên.

**Bỏ qua điều kiện đi kèm độ phức tạp.** Xóa nút danh sách liên kết `O(1)` chỉ khi đã có nút; truy vấn khoảng trong cây là `O(log n + k)` vì việc xuất `k` kết quả tự nó cần ít nhất `Ω(k)` thời gian.

**Coi đầu vào là phân bố đều khi thực tế không phải vậy.** Khóa có thể lặp lại, bị lệch, hoặc do người dùng chủ động tạo. Giả định về hàm băm, số lượng phần tử và độ dài chuỗi ảnh hưởng đến hiệu quả.

**Quên chi phí duy trì bất biến.** Thêm chỉ mục có thể tăng tốc truy vấn, nhưng mỗi lần chèn/xóa phải cập nhật nhiều nơi; lỗi giữa chừng tạo dữ liệu không nhất quán.

**Chỉ so Big-O mà bỏ qua chi phí thực tế.** Với dữ liệu nhỏ, một mảng được sắp xếp có thể nhanh nhờ locality dù thao tác chèn là `O(n)`. Với dữ liệu rất lớn hoặc ở đĩa, số lần truy cập khối dữ liệu và mức sử dụng bộ nhớ có thể quan trọng hơn số phép so sánh.

## 7. Quy trình quyết định có thể áp dụng lại

Khi nhận một bài toán mới, hãy viết một “phiếu lựa chọn” ngắn trước khi cài đặt:

```text
Đối tượng dữ liệu:
    Phần tử, khóa, quy tắc trùng lặp và bất biến.

Quy mô:
    n hiện tại / n tối đa, tăng trưởng, phân bố dữ liệu.

Tải công việc:
    Phép toán, đầu vào của từng phép toán, tần suất, số kết quả k.

Bảo đảm:
    Thứ tự, tính chính xác, thời gian trường hợp xấu,
    giới hạn RAM, nhất quán, đồng thời.

Ứng viên:
    Chọn 2–3 cấu trúc đáp ứng ngữ nghĩa.
    Với mỗi cấu trúc, ghi chi phí T(n), bộ nhớ M(n),
    giả định và bất biến phải duy trì.

Quyết định:
    Loại ứng viên vi phạm bảo đảm.
    Ước tính tổng chi phí theo tải công việc.
    Đo và kiểm chứng trên dữ liệu tương ứng.
```

Việc đo nên bao gồm kích thước nhỏ và lớn, tỷ lệ đọc/ghi thực tế, khóa có phân bố xấu, thời gian của các thao tác hiếm, bộ nhớ đỉnh và chi phí tái cấu trúc. Nếu có mục tiêu độ trễ như p95/p99, hãy đo trực tiếp các chỉ số đó; Big-O là công cụ sàng lọc, không phải cam kết về mili giây.

### Hai tình huống ngắn để tự áp dụng

**Tình huống A — hàng đợi tác vụ:** các tác vụ đến ở cuối và luôn được xử lý theo thứ tự đến trước; không cần tìm hay xóa một tác vụ bất kỳ. Phép toán chủ đạo là `enqueue`/`dequeue`. Một queue hiện thực bằng bộ đệm vòng là ứng viên tự nhiên; giới hạn dung lượng và hành vi khi đầy phải được quyết định rõ.

**Tình huống B — điểm số thay đổi, liên tục hỏi tổng đoạn:** có `n` vị trí, thường xuyên cập nhật một điểm và hỏi tổng trên `[l, r]`. Nếu chỉ lưu mảng, cập nhật điểm `O(1)` nhưng tính tổng mỗi lần có thể `O(n)`. Fenwick tree hoặc segment tree thường hỗ trợ cập nhật và truy vấn tổng trong `O(log n)`, đổi lại bộ nhớ phụ và công sức duy trì cấu trúc. Nếu mảng bất biến, prefix sum có thể cho truy vấn `O(1)` sau tiền xử lý `O(n)` và là lựa chọn đơn giản hơn.

## Kết luận

Chọn cấu trúc dữ liệu là một quyết định thiết kế có thể giải thích và kiểm chứng: **liệt kê phép toán → nhận diện tải công việc chủ đạo → nêu bảo đảm bắt buộc → so chi phí của các ứng viên → đo trong điều kiện thực tế**. Bất biến giúp khẳng định kết quả đúng; độ phức tạp và ngân sách tài nguyên giúp đánh giá chi phí. Khi hai yếu tố này được viết rõ trước, việc chọn mảng, bảng băm, cây, heap hay phối hợp nhiều chỉ mục trở thành một lập luận kỹ thuật thay vì một thói quen.
